from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .audit import AuditResult
from .contract import clamp_state
from .package_loader import RoleCardPackage
from .predicate import matches, value_at

DAILY_LIMITS = {
    "trust": (-3, 2),
    "dependency": (-3, 2),
    "feminine_acceptance": (0, 1),
    "lust": (0, 3),
}


class _ConditionSyntaxError(ValueError):
    pass


class _ConditionParser:
    TOKEN = re.compile(
        r"\s*(===|!==|==|!=|>=|<=|&&|\|\||[()<>]|"
        r"-?(?:\d+(?:\.\d*)?|\.\d+)|"
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    )

    def __init__(self, expression: str, state: dict[str, Any], signals: dict[str, Any]):
        self.tokens: list[str] = []
        position = 0
        while position < len(expression):
            token = self.TOKEN.match(expression, position)
            if token is None:
                raise _ConditionSyntaxError("Unsupported condition syntax")
            self.tokens.append(token.group(1))
            position = token.end()
        self.position = 0
        self.state = state
        self.signals = signals

    def parse(self) -> bool:
        value = self._or()
        if self.position != len(self.tokens):
            raise _ConditionSyntaxError("Unexpected condition token")
        return value

    def _accept(self, token: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position] == token:
            self.position += 1
            return True
        return False

    def _or(self) -> bool:
        value = self._and()
        while self._accept("||"):
            right = self._and()
            value = value or right
        return value

    def _and(self) -> bool:
        value = self._comparison()
        while self._accept("&&"):
            right = self._comparison()
            value = value and right
        return value

    def _comparison(self) -> bool:
        if self._accept("("):
            value = self._or()
            if not self._accept(")"):
                raise _ConditionSyntaxError("Missing closing parenthesis")
            return value
        left = self._operand()
        operators = ("===", "!==", "==", "!=", ">=", "<=", ">", "<")
        operator = next((item for item in operators if self._accept(item)), None)
        if operator is None:
            raise _ConditionSyntaxError("Missing comparison operator")
        right = self._operand()
        if isinstance(left, bool) and isinstance(right, bool):
            equal = left is right
        elif (
            isinstance(left, (int, float)) and not isinstance(left, bool)
            and isinstance(right, (int, float)) and not isinstance(right, bool)
        ):
            equal = left == right
        else:
            return False
        if operator in ("===", "=="):
            return equal
        if operator in ("!==", "!="):
            return not equal
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        return left < right

    def _operand(self) -> Any:
        if self.position == len(self.tokens):
            raise _ConditionSyntaxError("Missing comparison operand")
        token = self.tokens[self.position]
        self.position += 1
        if token in ("true", "false"):
            return token == "true"
        if token.startswith("state."):
            return value_at(self.state, token[len("state."):])
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            return self.signals.get(token)
        if re.fullmatch(r"-?(?:\d+(?:\.\d*)?|\.\d+)", token):
            return float(token)
        raise _ConditionSyntaxError("Unsupported comparison operand")


def _condition_matches(condition: Any, state: dict[str, Any], signals: dict[str, Any]) -> bool:
    if condition is None or condition == "":
        return True
    if isinstance(condition, (dict, list)):
        return matches(state, condition)
    if not isinstance(condition, str):
        return False
    expression = condition.strip()
    if not expression:
        return True
    try:
        return _ConditionParser(expression, state, signals).parse()
    except _ConditionSyntaxError:
        return False


def _guard_matches(state: dict[str, Any], event: dict[str, Any]) -> bool:
    guard = event["guard"]
    if guard.get("stage") is not None and state.get("relation_stage") != guard["stage"]:
        return False
    for guard_key, state_key in (
        ("trust_min", "trust"),
        ("dependency_min", "dependency"),
        ("feminine_acceptance_min", "feminine_acceptance"),
        ("lust_min", "lust"),
    ):
        minimum = guard.get(guard_key)
        if minimum is not None and (state.get(state_key) is None or state[state_key] < minimum):
            return False
    for key, expected in guard.get("flags_required", {}).items():
        if state.get("flags", {}).get(key) is not expected:
            return False
    completed_exclude = guard.get("completed_events_exclude", [])
    if any(item in state.get("completed_events", []) for item in completed_exclude):
        return False
    if any(item not in state.get("completed_events", []) for item in guard.get("completed_events_required", [])):
        return False
    if not event["repeatable"] and event["id"] in state.get("completed_events", []):
        return False
    pool = event.get("pool", {})
    last_turn = state.get("event_history", {}).get(event["id"])
    if last_turn is not None and state.get("turn_count", 0) - last_turn < pool.get("cooldown_turns", 0):
        return False
    return matches(state, pool.get("condition"))


def eligible_events(package: RoleCardPackage, state: dict[str, Any], *, nsfw_enabled: bool, private_chat: bool) -> list[dict[str, Any]]:
    if state.get("active_event") is not None:
        return []
    candidates = [event for event in package.events if _guard_matches(state, event)]
    if nsfw_enabled and private_chat:
        candidates.extend(event for event in package.adult_events if _guard_matches(state, event))
    return sorted(candidates, key=lambda event: event.get("pool", {}).get("priority", 0), reverse=True)


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


def _apply_delta(current: Any, change: Any) -> int | float:
    if isinstance(change, (int, float)) and not isinstance(change, bool):
        return change
    if not isinstance(change, str):
        return current
    text = change.strip()
    try:
        if text.startswith("+="):
            return _number(current) + float(text[2:].strip())
        if text.startswith("-="):
            return _number(current) - float(text[2:].strip())
        return float(text)
    except ValueError:
        return current


def _apply_mutation(
    state: dict[str, Any],
    mutation: dict[str, Any],
    *,
    allow_stage_change: bool = False,
) -> None:
    for key in ("active_event", "event_step"):
        if key in mutation and key in state:
            state[key] = mutation[key]
    if allow_stage_change and "relation_stage" in mutation:
        state["relation_stage"] = mutation["relation_stage"]
    for key in ("trust", "dependency", "feminine_acceptance", "lust"):
        if key in mutation:
            state[key] = _apply_delta(state.get(key), mutation[key])
    flags = mutation.get("flags")
    if isinstance(flags, dict):
        for key, value in flags.items():
            if key in state["flags"] and isinstance(value, bool):
                state["flags"][key] = value
    completed = mutation.get("completed_events")
    if isinstance(completed, list):
        state["completed_events"].extend(str(item) for item in completed)
    elif isinstance(completed, str) and "push(" in completed:
        state["completed_events"].extend(
            re.findall(r"push\(\s*['\"]([^'\"]+)['\"]", completed)
        )


def _stage_transition_allowed(
    package: RoleCardPackage,
    previous_stage: Any,
    next_stage: Any,
) -> bool:
    if previous_stage == next_stage:
        return True
    stage_ids = [stage["id"] for stage in package.stages]
    try:
        return stage_ids.index(next_stage) == stage_ids.index(previous_stage) + 1
    except ValueError:
        return False


def _apply_daily_deltas(state: dict[str, Any], deltas: dict[str, Any]) -> None:
    for key, (minimum, maximum) in DAILY_LIMITS.items():
        value = deltas.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        value = max(minimum, min(maximum, value))
        state[key] = _number(state.get(key)) + value


def _settle_event(
    package: RoleCardPackage,
    state: dict[str, Any],
    event_id: str,
    mutation: dict[str, Any],
    *,
    allow_stage_change: bool,
) -> None:
    previous_stage = state.get("relation_stage")
    _apply_mutation(state, mutation, allow_stage_change=allow_stage_change)
    if not _stage_transition_allowed(package, previous_stage, state.get("relation_stage")):
        state["relation_stage"] = previous_stage
    if previous_stage not in {"恋爱", "公开恋爱", "in_love", "public_relationship"} and state.get("relation_stage") in {"恋爱", "公开恋爱", "in_love", "public_relationship"}:
        state["lust"] = 0
    state["active_event"] = None
    if "event_step" not in mutation:
        state["event_step"] = 0
    state.setdefault("event_history", {})[event_id] = state["turn_count"]


def apply_audit(
    package: RoleCardPackage,
    previous: dict[str, Any],
    result: AuditResult,
    *,
    nsfw_enabled: bool,
    private_chat: bool,
    candidate_ids: list[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    state = deepcopy(previous)
    active_id = state.get("active_event")
    event_map = {event["id"]: event for event in package.events + package.adult_events}
    changed_event: str | None = None

    if active_id:
        event = event_map.get(active_id)
        if event is None or (active_id in {item["id"] for item in package.adult_events} and not (nsfw_enabled and private_chat)):
            state["active_event"] = None
            state["event_step"] = 0
            clamp_state(state, package.stages)
            return state, None
        if result.event_id != active_id or result.action not in {"none", "step", "success", "fail", "branch"}:
            return state, None
        branch = None
        if result.action == "branch":
            branch = event.get("branches", {}).get(result.branch_id)
            if branch is None:
                return state, None
        condition_state = deepcopy(state)
        state["turn_count"] = state.get("turn_count", 0) + 1
        if result.action in {"success", "fail", "branch"}:
            if branch is not None:
                condition = branch.get("condition")
                mutation = branch.get("mutation", {})
            else:
                outcome = "failure" if result.action == "fail" else "success"
                condition = event.get(f"{outcome}_condition")
                mutation = event[outcome]
            if _condition_matches(condition, condition_state, result.signals):
                _settle_event(package, state, active_id, mutation, allow_stage_change=result.action != "fail")
                changed_event = active_id
        elif result.action == "step":
            state["event_step"] = max(1, int(state.get("event_step", 0)) + 1)
            changed_event = active_id
        clamp_state(state, package.stages)
        return state, changed_event

    candidates = eligible_events(package, state, nsfw_enabled=nsfw_enabled, private_chat=private_chat)
    allowed_ids = {event["id"] for event in candidates}
    if candidate_ids is not None:
        allowed_ids.intersection_update(candidate_ids)
    if result.action == "trigger" and result.event_id in allowed_ids:
        state["active_event"] = result.event_id
        state["event_step"] = 1
        changed_event = result.event_id
    elif result.action == "none" and result.event_id is None:
        _apply_daily_deltas(state, result.deltas)
    else:
        return state, None
    state["turn_count"] = state.get("turn_count", 0) + 1
    clamp_state(state, package.stages)
    return state, changed_event


def event_guard_as_predicate(event: dict[str, Any]) -> dict[str, Any]:
    guard = event["guard"]
    conditions: list[dict[str, Any]] = []
    if guard.get("stage") is not None:
        conditions.append({"path": "relation_stage", "op": "equals", "value": guard["stage"]})
    for guard_key, state_key in (
        ("trust_min", "trust"),
        ("dependency_min", "dependency"),
        ("feminine_acceptance_min", "feminine_acceptance"),
        ("lust_min", "lust"),
    ):
        if guard.get(guard_key) is not None:
            conditions.append({"path": state_key, "op": "gte", "value": guard[guard_key]})
    for key, value in guard.get("flags_required", {}).items():
        conditions.append({"path": f"flags.{key}", "op": "equals", "value": value})
    for event_id in guard.get("completed_events_required", []):
        conditions.append({"path": "completed_events", "op": "contains", "value": event_id})
    for event_id in guard.get("completed_events_exclude", []):
        conditions.append({"path": "completed_events", "op": "not_contains", "value": event_id})
    return {"all": conditions}

