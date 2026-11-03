from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from astrbot_plugin_rolecard_runtime.audit import AuditResult
from astrbot_plugin_rolecard_runtime.contract import DEFAULT_STATE
from astrbot_plugin_rolecard_runtime.event_engine import apply_audit, eligible_events, event_guard_as_predicate
from astrbot_plugin_rolecard_runtime.package_loader import RoleCardPackage
from astrbot_plugin_rolecard_runtime.predicate import matches


def make_event(event_id: str, **values: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": event_id,
        "title": event_id,
        "repeatable": True,
        "guard": {},
        "success": {},
        "failure": {},
        "success_condition": "",
        "failure_condition": "",
        "branches": {},
        "pool": {},
    }
    event.update(values)
    return event


def make_package(*events: dict[str, Any]) -> RoleCardPackage:
    return RoleCardPackage(
        package_id="test",
        display_name="test",
        version="1",
        core_prompt="",
        greeting="",
        stages=[{"id": "one", "name": "one"}, {"id": "two", "name": "two"}],
        initial_state=make_state(),
        events=list(events),
    )


def make_state(**values: Any) -> dict[str, Any]:
    state = deepcopy(DEFAULT_STATE)
    state.update(relation_stage="one", turn_count=0, event_history={})
    state.update(values)
    return state


def test_success_condition_requires_signals_and_supports_boolean_expressions() -> None:
    event = make_event(
        "conditional",
        success={"trust": 10},
        success_condition="signal_a === true || (signal_b === true && state.trust >= 10)",
    )
    package = make_package(event)
    state = make_state(active_event="conditional", event_step=1, custom_field={"items": [1]})

    pending, changed = apply_audit(
        package,
        state,
        AuditResult("success", "conditional"),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert pending["active_event"] == "conditional"
    assert pending["trust"] == 0
    assert pending["turn_count"] == 1
    assert pending["custom_field"] == {"items": [1]}
    assert pending["event_history"] == {}

    below_threshold, changed = apply_audit(
        package,
        pending,
        AuditResult("success", "conditional", signals={"signal_b": True}),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert below_threshold["active_event"] == "conditional"
    assert below_threshold["trust"] == 0
    assert below_threshold["turn_count"] == 2

    below_threshold["trust"] = 10
    settled, changed = apply_audit(
        package,
        below_threshold,
        AuditResult("success", "conditional", signals={"signal_b": True}),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed == "conditional"
    assert settled["active_event"] is None
    assert settled["trust"] == 10
    assert settled["turn_count"] == 3
    assert settled["event_history"] == {"conditional": 3}
    settled["custom_field"]["items"].append(2)
    assert state["custom_field"] == {"items": [1]}


@pytest.mark.parametrize(
    ("condition", "signals", "trust", "expected"),
    [
        ("signal_a === true || signal_b === true && state.trust >= 10", {"signal_a": True}, 0, True),
        ("(signal_a === true || signal_b === true) && state.trust >= 10", {"signal_a": True}, 0, False),
        ("signal_a === true && signal_b === true || signal_c === true", {"signal_c": True}, 0, True),
        ("signal_a === true && (signal_b === true || signal_c === true)", {"signal_c": True}, 0, False),
        ("declined === false", {"declined": False}, 0, True),
        ("declined === false", {}, 0, False),
        ("accepted === true", {"accepted": 1}, 0, False),
        ("accepted === true", {"accepted": "true"}, 0, False),
        ("state.trust >= 10 && state.trust <= 20", {}, 10, True),
        ("state.trust > -1 && state.trust < 10.5", {}, 10, True),
        ("state.trust === 10 && state.trust !== 20", {}, 10, True),
        ("state.missing >= 0", {}, 0, False),
        ("state.custom.value >= 2", {}, 0, True),
        ("signal_a === true || (signal_b === true)", {"signal_a": True}, 0, True),
    ],
)
def test_success_condition_honors_boolean_precedence_and_types(
    condition: str, signals: dict[str, Any], trust: int, expected: bool,
) -> None:
    event = make_event(
        "conditional",
        success_condition=condition,
    )
    package = make_package(event)
    state = make_state(active_event="conditional", trust=trust, custom={"value": 2})

    settled, changed = apply_audit(
        package,
        state,
        AuditResult("success", "conditional", signals=signals),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed == ("conditional" if expected else None)
    assert settled["active_event"] == (None if expected else "conditional")
    assert settled["turn_count"] == 1


def test_branch_requires_matching_condition_and_only_moves_one_stage() -> None:
    event = make_event(
        "choice",
        branches={
            "advance": {"condition": "accepted === true", "mutation": {"relation_stage": "two", "trust": "+= 5"}},
            "skip": {"condition": "skip === true", "mutation": {"relation_stage": "three"}},
        },
    )
    package = make_package(event)
    state = make_state(active_event="choice")

    pending, changed = apply_audit(
        package,
        state,
        AuditResult("branch", "choice", branch_id="advance"),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert pending["active_event"] == "choice"
    assert pending["turn_count"] == 1

    settled, changed = apply_audit(
        package,
        pending,
        AuditResult("branch", "choice", branch_id="advance", signals={"accepted": True}),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed == "choice"
    assert settled["relation_stage"] == "two"
    assert settled["trust"] == 5
    assert settled["active_event"] is None
    assert settled["event_history"] == {"choice": 2}


def test_required_events_priority_and_cooldown_filtering() -> None:
    delayed = make_event(
        "delayed",
        pool={"priority": 100, "cooldown_turns": 2},
        guard={"completed_events_required": ["prerequisite", "second"]},
    )
    high = make_event("high", pool={"priority": 10, "condition": {"path": "flags.ready", "op": "equals", "value": True}})
    low = make_event("low", pool={"priority": -1})
    package = make_package(low, delayed, high)
    state = make_state(turn_count=9, event_history={"delayed": 8}, flags={"ready": True})

    assert [event["id"] for event in eligible_events(package, state, nsfw_enabled=False, private_chat=True)] == ["high", "low"]

    state["completed_events"] = ["prerequisite"]
    state["turn_count"] = 10
    assert [event["id"] for event in eligible_events(package, state, nsfw_enabled=False, private_chat=True)] == ["high", "low"]

    state["completed_events"] = ["prerequisite", "second"]
    assert [event["id"] for event in eligible_events(package, state, nsfw_enabled=False, private_chat=True)] == ["delayed", "high", "low"]

    state["turn_count"] = 9
    assert [event["id"] for event in eligible_events(package, state, nsfw_enabled=False, private_chat=True)] == ["high", "low"]
    state["flags"]["ready"] = False
    assert [event["id"] for event in eligible_events(package, state, nsfw_enabled=False, private_chat=True)] == ["low"]


def test_candidate_ids_cannot_trigger_events_outside_the_selected_pool() -> None:
    package = make_package(make_event("eligible"), make_event("other"))
    state = make_state()
    audit = AuditResult("trigger", "other")

    unchanged, changed = apply_audit(
        package,
        state,
        audit,
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=["eligible"],
    )
    assert changed is None
    assert unchanged == state

    triggered, changed = apply_audit(
        package,
        state,
        AuditResult("trigger", "eligible"),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=["eligible"],
    )
    assert changed == "eligible"
    assert triggered["active_event"] == "eligible"
    assert triggered["turn_count"] == 1


@pytest.mark.parametrize("event_id", [None, "other"])
def test_active_event_requires_its_own_id_for_an_audit_action(event_id: str | None) -> None:
    package = make_package(make_event("active"))
    state = make_state(active_event="active", event_step=1, turn_count=4)

    unchanged, changed = apply_audit(
        package,
        state,
        AuditResult("step", event_id),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert unchanged == state


@pytest.mark.parametrize("candidate_ids", [None, ["eligible", "other"]])
def test_selected_or_legacy_candidates_can_trigger(candidate_ids: list[str] | None) -> None:
    package = make_package(make_event("eligible"), make_event("other"))
    state, changed = apply_audit(
        package,
        make_state(),
        AuditResult("trigger", "other"),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=candidate_ids,
    )
    assert changed == "other"
    assert state["active_event"] == "other"
    assert state["turn_count"] == 1


def test_empty_candidate_ids_reject_new_trigger_without_advancing_turn() -> None:
    package = make_package(make_event("event"))
    state = make_state()
    unchanged, changed = apply_audit(
        package,
        state,
        AuditResult("trigger", "event"),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=[],
    )
    assert changed is None
    assert unchanged == state


@pytest.mark.parametrize(
    "event",
    [
        make_event("blocked", guard={"completed_events_required": ["required"]}),
        make_event("blocked", pool={"condition": {"path": "trust", "op": "gte", "value": 10}}),
        make_event("blocked", pool={"cooldown_turns": 2}),
        make_event("blocked", repeatable=False),
    ],
)
def test_candidate_ids_still_require_native_eligibility(event: dict[str, Any]) -> None:
    package = make_package(event)
    state = make_state(turn_count=9, event_history={"blocked": 8}, completed_events=["blocked"])
    unchanged, changed = apply_audit(
        package,
        state,
        AuditResult("trigger", "blocked"),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=["blocked"],
    )
    assert changed is None
    assert unchanged == state


@pytest.mark.parametrize("action", ["success", "fail", "branch"])
def test_settlement_records_latest_end_turn_and_drives_cooldown(action: str) -> None:
    event = make_event("repeat", branches={"done": {"condition": "", "mutation": {}}}, pool={"cooldown_turns": 2})
    package = make_package(event)
    state = make_state(active_event="repeat", event_step=1, turn_count=4, event_history={"repeat": 1, "other": 2})
    settled, changed = apply_audit(
        package,
        state,
        AuditResult(action, "repeat", branch_id="done" if action == "branch" else None),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=[],
    )
    assert changed == "repeat"
    assert settled["active_event"] is None
    assert settled["event_step"] == 0
    assert settled["completed_events"] == []
    assert settled["turn_count"] == 5
    assert settled["event_history"] == {"repeat": 5, "other": 2}
    assert eligible_events(package, settled, nsfw_enabled=False, private_chat=True) == []

    for _ in range(2):
        settled, changed = apply_audit(
            package,
            settled,
            AuditResult("none"),
            nsfw_enabled=False,
            private_chat=True,
        )
        assert changed is None
    assert settled["turn_count"] == 7
    assert [event["id"] for event in eligible_events(package, settled, nsfw_enabled=False, private_chat=True)] == ["repeat"]


def test_failure_condition_requires_explicit_false_signal() -> None:
    package = make_package(make_event("event", failure_condition="accepted === false", failure={"trust": "-= 2"}))
    state = make_state(active_event="event", trust=10)
    pending, changed = apply_audit(
        package,
        state,
        AuditResult("fail", "event"),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert pending["active_event"] == "event"
    assert pending["trust"] == 10
    assert pending["turn_count"] == 1
    assert pending["event_history"] == {}

    settled, changed = apply_audit(
        package,
        pending,
        AuditResult("fail", "event", signals={"accepted": False}),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed == "event"
    assert settled["trust"] == 8
    assert settled["event_history"] == {"event": 2}


@pytest.mark.parametrize("action", ["success", "branch"])
@pytest.mark.parametrize("next_stage", ["one", "two", "three", "unknown"])
def test_stage_mutations_only_allow_the_same_or_next_stage(action: str, next_stage: str) -> None:
    mutation = {"relation_stage": next_stage, "trust": "+= 5"}
    package = make_package(make_event("event", success=mutation, branches={"advance": {"mutation": mutation}}))
    package.stages.append({"id": "three", "name": "three"})
    settled, changed = apply_audit(
        package,
        make_state(active_event="event"),
        AuditResult(action, "event", branch_id="advance" if action == "branch" else None),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed == "event"
    assert settled["relation_stage"] == (next_stage if next_stage in {"one", "two"} else "one")
    assert settled["trust"] == 5


@pytest.mark.parametrize("action", ["none", "step"])
def test_active_non_settlement_turn_keeps_history_and_extra_state(action: str) -> None:
    package = make_package(make_event("event"))
    previous = make_state(active_event="event", event_step=1, event_history={"old": 2}, extra={"nested": [1]})
    state, changed = apply_audit(
        package,
        previous,
        AuditResult(action, "event", deltas={"trust": 99}),
        nsfw_enabled=False,
        private_chat=True,
        candidate_ids=[],
    )
    assert changed == ("event" if action == "step" else None)
    assert state["active_event"] == "event"
    assert state["event_step"] == (2 if action == "step" else 1)
    assert state["trust"] == 0
    assert state["turn_count"] == 1
    assert state["event_history"] == {"old": 2}
    assert state["extra"] == {"nested": [1]}


@pytest.mark.parametrize("branch_id", [None, "unknown"])
def test_unknown_branch_does_not_settle_or_advance_turn(branch_id: str | None) -> None:
    package = make_package(make_event("event", branches={"known": {"mutation": {"trust": 10}}}))
    previous = make_state(active_event="event")
    state, changed = apply_audit(
        package,
        previous,
        AuditResult("branch", "event", branch_id=branch_id),
        nsfw_enabled=False,
        private_chat=True,
    )
    assert changed is None
    assert state == previous


def test_guard_predicate_includes_required_and_excluded_completed_events() -> None:
    event = make_event("event", guard={"completed_events_required": ["first", "second"], "completed_events_exclude": ["excluded"]})
    predicate = event_guard_as_predicate(event)
    assert not matches(make_state(completed_events=["first"]), predicate)
    assert matches(make_state(completed_events=["first", "second"]), predicate)
    assert not matches(make_state(completed_events=["first", "second", "excluded"]), predicate)
