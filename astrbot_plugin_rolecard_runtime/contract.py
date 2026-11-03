from __future__ import annotations

from copy import deepcopy
from typing import Any

STATE_FIELDS = (
    "relation_stage",
    "trust",
    "dependency",
    "feminine_acceptance",
    "lust",
    "active_event",
    "event_step",
    "completed_events",
    "flags",
    "turn_count",
    "event_history",
)

DEFAULT_STATE: dict[str, Any] = {
    "relation_stage": "默认",
    "trust": 0,
    "dependency": 0,
    "feminine_acceptance": 0,
    "lust": None,
    "active_event": None,
    "event_step": 0,
    "completed_events": [],
    "flags": {},
    "turn_count": 0,
    "event_history": {},
}


def initial_state(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(DEFAULT_STATE)
    result.update(deepcopy(value))
    if not isinstance(result.get("completed_events"), list):
        result["completed_events"] = []
    if not isinstance(result.get("flags"), dict):
        result["flags"] = {}
    return result


def normalize_state(state: dict[str, Any], initial: dict[str, Any]) -> dict[str, Any]:
    normalized = initial_state(initial)
    for key in normalized:
        if key == "flags":
            continue
        if key in state:
            normalized[key] = deepcopy(state[key])
    if isinstance(state.get("flags"), dict) and isinstance(normalized.get("flags"), dict):
        normalized["flags"].update(
            {
                key: value
                for key, value in state["flags"].items()
                if key in normalized["flags"]
            }
        )
    return normalized


def clamp_state(state: dict[str, Any], stages: list[dict[str, str]]) -> dict[str, Any]:
    if state.get("relation_stage") not in {stage["id"] for stage in stages}:
        state["relation_stage"] = stages[0]["id"]

    for key in ("trust", "dependency", "feminine_acceptance"):
        state[key] = max(0, min(100, int(state.get(key, 0))))

    if state["relation_stage"] not in {"恋爱", "公开恋爱", "in_love", "public_relationship"}:
        state["lust"] = None
    elif state["lust"] is None:
        state["lust"] = 0
    else:
        state["lust"] = max(0, min(100, int(state["lust"])))

    state["event_step"] = max(0, int(state.get("event_step", 0)))
    state["completed_events"] = list(dict.fromkeys(state.get("completed_events", [])))
    return state

