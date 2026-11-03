from __future__ import annotations

from typing import Any


def value_at(state: dict[str, Any], path: str) -> Any:
    value: Any = state
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def matches(state: dict[str, Any], predicate: Any) -> bool:
    """Evaluate a declarative predicate against runtime state."""
    if predicate is None or predicate == {}:
        return True
    if isinstance(predicate, list):
        return all(matches(state, item) for item in predicate)
    if not isinstance(predicate, dict):
        return False
    if "all" in predicate:
        return all(matches(state, item) for item in predicate["all"])
    if "any" in predicate:
        return any(matches(state, item) for item in predicate["any"])
    if "not" in predicate:
        return not matches(state, predicate["not"])

    path = predicate.get("path")
    op = predicate.get("op", "equals")
    actual = value_at(state, str(path)) if path else None
    expected = predicate.get("value")
    if op == "equals":
        return actual == expected
    if op == "gte":
        return isinstance(actual, (int, float)) and actual >= expected
    if op == "lte":
        return isinstance(actual, (int, float)) and actual <= expected
    if op == "contains":
        return isinstance(actual, (str, list, tuple, set)) and expected in actual
    if op == "not_contains":
        return not (isinstance(actual, (str, list, tuple, set)) and expected in actual)
    return False

