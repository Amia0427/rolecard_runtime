from __future__ import annotations

from astrbot_plugin_rolecard_runtime.audit import AuditError, parse_audit_response
from astrbot_plugin_rolecard_runtime.event_engine import apply_audit, eligible_events
from astrbot_plugin_rolecard_runtime.generation_self_check import build_generation_self_check
from astrbot_plugin_rolecard_runtime.package_loader import load_zip
from astrbot_plugin_rolecard_runtime.predicate import matches
from astrbot_plugin_rolecard_runtime.prompt_builder import build_prompt

from test_package_loader import make_zip, standard_files


def package():
    return load_zip(make_zip(standard_files()))


def test_generation_self_check_uses_role_name_and_light_chat_guidance() -> None:
    prompt = build_generation_self_check("示例卡")

    assert prompt.startswith("<生成前自检>")
    assert prompt.endswith("</生成前自检>")
    assert "你是示例卡" in prompt
    assert "{角色名}" not in prompt
    assert "简短、平淡、岔开话题" in prompt
    assert "不必每句都解释、安慰、总结或推进话题" in prompt


def test_build_prompt_includes_generation_self_check_without_changing_event_filtering() -> None:
    card = package()
    state = dict(card.initial_state)
    state["relation_stage"] = "恋爱"

    prompt, candidates = build_prompt(card, state, "", "用户", nsfw_enabled=False, private_chat=True)

    assert "<生成前自检>" in prompt
    assert "你是示例卡" in prompt
    assert "阶段二 用户" in prompt
    assert "核心世界书" in prompt
    assert all(item["id"] != "adult" for item in candidates)
    assert "成人事件正文" not in prompt


def test_predicate_supports_boolean_and_collection_operators() -> None:
    state = {"trust": 30, "flags": {"ready": True}, "completed_events": ["old"]}
    assert matches(state, {"all": [{"path": "trust", "op": "gte", "value": 20}, {"path": "flags.ready", "op": "equals", "value": True}]})
    assert matches(state, {"any": [{"path": "trust", "op": "lte", "value": 1}, {"path": "trust", "op": "gte", "value": 30}]})
    assert matches(state, {"not": {"path": "completed_events", "op": "contains", "value": "new"}})
    assert matches(state, {"path": "completed_events", "op": "not_contains", "value": "new"})


def test_event_trigger_success_transition_initializes_lust() -> None:
    card = package()
    state = dict(card.initial_state)
    trigger = parse_audit_response('{"action":"trigger","event_id":"icebreaking"}')
    state, changed = apply_audit(card, state, trigger, nsfw_enabled=False, private_chat=True)
    assert changed == "icebreaking"
    assert state["active_event"] == "icebreaking"

    success = parse_audit_response('{"action":"success","event_id":"icebreaking"}')
    state, changed = apply_audit(card, state, success, nsfw_enabled=False, private_chat=True)
    assert changed == "icebreaking"
    assert state["relation_stage"] == "恋爱"
    assert state["trust"] == 10
    assert state["lust"] == 0
    assert state["completed_events"] == ["icebreaking"]


def test_active_event_is_mutex_and_failed_event_uses_declared_completion_only() -> None:
    card = package()
    state = dict(card.initial_state)
    state["active_event"] = "icebreaking"
    state["event_step"] = 1
    invalid = parse_audit_response('{"action":"trigger","event_id":"adult"}')
    unchanged, changed = apply_audit(card, state, invalid, nsfw_enabled=True, private_chat=True)
    assert unchanged == state
    assert changed is None

    failure = parse_audit_response('{"action":"fail","event_id":"icebreaking"}')
    state, changed = apply_audit(card, state, failure, nsfw_enabled=False, private_chat=True)
    assert changed == "icebreaking"
    assert state["active_event"] is None
    assert state["completed_events"] == []


def test_daily_deltas_are_limited_and_adult_events_are_private_opt_in() -> None:
    card = package()
    state = dict(card.initial_state)
    none = parse_audit_response('{"action":"none","deltas":{"trust":99,"dependency":-99,"feminine_acceptance":99,"lust":99}}')
    state, _ = apply_audit(card, state, none, nsfw_enabled=False, private_chat=True)
    assert state["trust"] == 2
    assert state["dependency"] == 0
    assert state["feminine_acceptance"] == 11
    assert state["lust"] is None

    adult_state = dict(card.initial_state)
    adult_state["relation_stage"] = "恋爱"
    prompt, candidates = build_prompt(card, adult_state, "", "用户", nsfw_enabled=False, private_chat=True)
    assert all(item["id"] != "adult" for item in candidates)
    assert "成人事件正文" not in prompt
    _, candidates = build_prompt(card, adult_state, "", "用户", nsfw_enabled=True, private_chat=True)
    assert any(item["id"] == "adult" for item in candidates)
    _, candidates = build_prompt(card, adult_state, "", "用户", nsfw_enabled=True, private_chat=False)
    assert all(item["id"] != "adult" for item in candidates)


def test_non_repeatable_completed_event_is_filtered() -> None:
    card = package()
    state = dict(card.initial_state)
    state["completed_events"] = ["icebreaking"]
    assert all(item["id"] != "icebreaking" for item in eligible_events(card, state, nsfw_enabled=False, private_chat=True))


def test_numeric_and_flag_guards_are_enforced() -> None:
    card = package()
    event = card.events[0]
    event["guard"]["trust_min"] = 30
    event["guard"]["flags_required"] = {"icebreaking_done": False}
    state = dict(card.initial_state)
    assert all(item["id"] != "icebreaking" for item in eligible_events(card, state, nsfw_enabled=False, private_chat=True))
    state["trust"] = 30
    assert any(item["id"] == "icebreaking" for item in eligible_events(card, state, nsfw_enabled=False, private_chat=True))


def test_audit_parser_accepts_code_block_and_rejects_invalid_json() -> None:
    result = parse_audit_response("```json\n{\"action\":\"none\",\"event_id\":null}\n```")
    assert result.action == "none"
    assert result.event_id is None
    try:
        parse_audit_response("not json")
    except AuditError:
        pass
    else:
        raise AssertionError("非法审计结果应被拒绝")
