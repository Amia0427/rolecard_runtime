from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
import yaml

from astrbot_plugin_rolecard_runtime.audit import build_audit_prompt, parse_audit_response
from astrbot_plugin_rolecard_runtime.ejs_runtime import TemplateError, render_templates
from astrbot_plugin_rolecard_runtime.mvu import VariableUpdateError, apply_variable_patch, extract_update
from astrbot_plugin_rolecard_runtime.package_loader import load_json, load_zip
from astrbot_plugin_rolecard_runtime.prompt_builder import build_runtime_prompt
from astrbot_plugin_rolecard_runtime.state_store import StateStore
from test_package_loader import make_zip, standard_files


def ejs_files():
    files = standard_files()
    manifest = yaml.safe_load(files["manifest.yaml"])
    manifest["runtime"] = {"engine": "ejs", "event_pool": "runtime/pool.ejs", "keyword_matching": False}
    manifest["state"].update(schema="runtime/schema.json", writable_paths=["scene"])
    manifest["worldbook"].append({"name": "动态", "path": "runtime/world.ejs", "mode": "ejs", "condition": {"path": "scene.location", "value": "living_room"}})
    initial = yaml.safe_load(files["state/contract.yaml"])["initial_state"]
    initial["scene"] = {"location": "living_room", "activity": "idle", "count": 0, "items": []}
    schema = {"type": "object", "properties": {"scene": {"type": "object", "required": ["location"], "properties": {"location": {"enum": ["living_room", "kitchen"]}}}}}
    files.update({
        "manifest.yaml": yaml.safe_dump(manifest, allow_unicode=True),
        "state/contract.yaml": yaml.safe_dump({"initial_state": initial}),
        "runtime/schema.json": json.dumps(schema),
        "runtime/pool.ejs": '<%- JSON.stringify(eligible_events.map(e => e.id).concat(["adult", "forged"])) %>',
        "runtime/world.ejs": '<% if(getvar("stat_data.scene.location") === "living_room") { %><%- await getwi("常驻") %><% } %>',
    })
    return files


def test_real_ejs_await_worldbook_and_keyword_disabled():
    card = load_zip(make_zip(ejs_files()))
    prompt, events = asyncio.run(build_runtime_prompt(card, card.initial_state, "画夹", "用户", nsfw_enabled=False, private_chat=True))
    assert [event["id"] for event in events] == ["icebreaking"]
    assert "[动态世界书]\n核心世界书" in prompt
    assert "画夹世界书" not in prompt
    assert "<%" not in prompt
    assert "[本轮候选事件]\n事件正文" in prompt
    assert "成人事件正文" not in prompt


def test_ejs_rejects_invalid_pool_and_reports_template_error():
    files = ejs_files()
    files["runtime/pool.ejs"] = "不是JSON"
    card = load_zip(make_zip(files))
    with pytest.raises(TemplateError, match="事件 ID 数组"):
        asyncio.run(build_runtime_prompt(card, card.initial_state, "", "用户", nsfw_enabled=False, private_chat=True))
    with pytest.raises(TemplateError):
        asyncio.run(render_templates(['<%- await getwi("不存在") %>'], {"state": {}}, {}))


def test_standalone_json_embeds_full_runtime():
    files = ejs_files()
    card = json.loads(files["card/character.json"])
    card["data"]["extensions"]["astrbot_runtime"] = {"files": files}
    package = load_json(json.dumps(card).encode())
    assert package.event_pool
    assert len(package.stages) == 2
    assert len(package.events) == 1


def test_mvu_extract_apply_validate_and_preserve_original():
    card = load_zip(make_zip(ejs_files()))
    previous = deepcopy(card.initial_state)
    text = '正文<UpdateVariable><Analysis>事实</Analysis><JSONPatch>[{"op":"replace","path":"/stat_data/scene/location","value":"kitchen"}]</JSONPatch><EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>'
    clean, patches, event = extract_update(text)
    assert clean == "正文"
    assert parse_audit_response(event).action == "none"
    updated = apply_variable_patch(previous, patches, card.writable_paths, card.state_schema)
    assert updated["scene"]["location"] == "kitchen"
    assert previous == card.initial_state
    with pytest.raises(VariableUpdateError, match="不允许"):
        apply_variable_patch(previous, [{"op": "replace", "path": "/trust", "value": 100}], card.writable_paths, card.state_schema)
    with pytest.raises(VariableUpdateError, match="schema"):
        apply_variable_patch(previous, [{"op": "replace", "path": "/scene/location", "value": "invented"}], card.writable_paths, card.state_schema)


def test_mvu_extensions_are_applied_in_order_atomically():
    card = load_zip(make_zip(ejs_files()))
    operations = [
        {"op": "delta", "path": "/scene/count", "value": 2},
        {"op": "insert", "path": "/scene/items/-", "value": "画夹"},
        {"op": "move", "from": "/scene/activity", "to": "/scene/previous_activity"},
    ]
    state = apply_variable_patch(card.initial_state, operations, ["scene"], card.state_schema)
    assert state["scene"]["count"] == 2
    assert state["scene"]["items"] == ["画夹"]
    assert state["scene"]["previous_activity"] == "idle"
    assert card.initial_state["scene"]["count"] == 0
    with pytest.raises(VariableUpdateError):
        apply_variable_patch(card.initial_state, operations + [{"op": "remove", "path": "/scene/missing"}], ["scene"], card.state_schema)
    assert card.initial_state["scene"]["items"] == []


def test_store_keeps_scene_history_and_rejects_stale_turn(tmp_path):
    card = load_zip(make_zip(ejs_files()))
    store = StateStore(tmp_path / "test.sqlite3")
    before = store.state("session", "a", card.package_id, card.initial_state)
    after = apply_variable_patch(before, [{"op": "replace", "path": "/scene/location", "value": "kitchen"}], ["scene"], card.state_schema)
    assert store.save_turn("session", "a", card.package_id, before, after, card.initial_state)
    assert not store.save_turn("session", "a", card.package_id, before, before, card.initial_state)
    assert store.state("session", "a", card.package_id, card.initial_state)["scene"]["location"] == "kitchen"
    assert store.state("session", "b", card.package_id, card.initial_state)["scene"]["location"] == "living_room"
    assert store.db.execute("SELECT COUNT(*) FROM state_history").fetchone()[0] == 1
    store.close()


def test_audit_sees_lifecycle_and_writable_scene_schema():
    card = load_zip(make_zip(ejs_files()))
    card.events[0]["success_condition"] = "helped === true"
    prompt = build_audit_prompt("规则", card.initial_state, "输入", "回复", card.events, card.writable_paths, card.state_schema)
    assert "helped === true" in prompt
    assert "事件正文" in prompt
    assert '"patches"' in prompt
    assert "kitchen" in prompt


def test_reset_invalidates_even_a_response_started_from_initial_state(tmp_path):
    card = load_zip(make_zip(ejs_files()))
    store = StateStore(tmp_path / "test.sqlite3")
    initial = card.initial_state
    revision = store.revision("s", "a", card.package_id)
    store.reset_state("s", "a", card.package_id)
    assert not store.save_turn("s", "a", card.package_id, initial, initial, initial, expected_revision=revision)
    assert store.revision("s", "a", card.package_id) == 1
    store.close()
