from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import zipfile

from jsonschema import ValidationError
from jsonschema.validators import validator_for
import pytest
import yaml

from astrbot_plugin_rolecard_runtime.audit import AuditResult, parse_audit_response
from astrbot_plugin_rolecard_runtime.event_engine import apply_audit
from astrbot_plugin_rolecard_runtime.mvu import apply_variable_patch, extract_update, validate_state
from astrbot_plugin_rolecard_runtime.package_loader import load_directory, load_json, load_zip
from astrbot_plugin_rolecard_runtime.prompt_builder import build_runtime_prompt
from astrbot_plugin_rolecard_runtime.repository import PackageRepository
from scripts import build_example


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "minimal"
OPTIONS = {"nsfw_enabled": False, "private_chat": True}


@pytest.fixture
def artifacts(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setattr(build_example, "ROOT", tmp_path)
    return build_example.build_example()


def runtime_prompt(package, state):
    return asyncio.run(build_runtime_prompt(package, state, "随便看看", "读者", **OPTIONS))


def apply_result(package, state, result, candidate_ids=None):
    updated, changed = apply_audit(package, state, result, candidate_ids=candidate_ids, **OPTIONS)
    validate_state(updated, package.state_schema)
    return updated, changed


def test_public_manifest_matches_schema_and_short_example() -> None:
    schema = json.loads((ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((EXAMPLE / "manifest.yaml").read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(manifest)
    assert manifest == yaml.safe_load((ROOT / "examples" / "manifest.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("engine", [None, "declarative"])
def test_manifest_schema_requires_ejs_for_event_pool(engine: str | None) -> None:
    manifest = yaml.safe_load((EXAMPLE / "manifest.yaml").read_text(encoding="utf-8"))
    if engine is None:
        manifest["runtime"].pop("engine")
    else:
        manifest["runtime"]["engine"] = engine
    with pytest.raises(ValidationError):
        build_example._validate_manifest(manifest)


def test_example_archives_preserve_directory_and_survive_repository_reload(artifacts, tmp_path: Path) -> None:
    zip_path, json_path = artifacts
    original = load_directory(EXAMPLE)
    card = json.loads(json_path.read_text(encoding="utf-8"))
    embedded = card["data"]["extensions"]["astrbot_runtime"]["files"]
    expected_files = set(build_example.EXAMPLE_FILES) | {"LICENSE"}
    assert set(embedded) == expected_files
    assert embedded["LICENSE"] == (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "astrbot_runtime" not in json.loads(embedded["card/character.json"])["data"].get("extensions", {})
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == expected_files
        for relative in expected_files:
            assert archive.read(relative).decode("utf-8") == embedded[relative]

    packages = [load_zip(zip_path.read_bytes()), load_json(json_path.read_bytes())]
    for name, method, payload in (
        ("directory", "import_directory", EXAMPLE),
        ("zip", "import_zip", zip_path.read_bytes()),
        ("json", "import_json", json_path.read_bytes()),
    ):
        repository = PackageRepository(tmp_path / name)
        getattr(repository, method)(payload)
        repository.reload()
        assert repository.diagnostics == []
        packages.append(repository.get("example-card"))
    for package in packages:
        assert replace(package, source=original.source) == original


def test_example_ejs_welcome_requires_evidence_before_stage_advance() -> None:
    package = load_directory(EXAMPLE)
    prompt, candidates = runtime_prompt(package, package.initial_state)
    ids = [event["id"] for event in candidates]
    assert ids == ["welcome"]
    assert "[动态世界书]" in prompt
    assert "当前在书店内" in prompt
    assert "店员问 读者" in prompt
    assert "<%" not in prompt

    state, changed = apply_result(package, package.initial_state, AuditResult("trigger", "welcome"), ids)
    assert changed == "welcome"
    assert state["event_step"] == 1
    active_prompt, active_candidates = runtime_prompt(package, state)
    assert active_candidates == []
    assert "[当前进行中的事件]" in active_prompt
    assert "[本轮候选事件]" not in active_prompt

    pending, changed = apply_result(package, state, AuditResult("success", "welcome"))
    assert changed is None
    assert pending["active_event"] == "welcome"
    settled, changed = apply_result(
        package, pending, AuditResult("success", "welcome", signals={"helped": True}),
    )
    assert changed == "welcome"
    assert settled["relation_stage"] == "familiar"
    assert settled["trust"] == 5
    assert settled["flags"] == {"welcome_done": True}
    assert settled["completed_events"] == ["welcome"]
    assert settled["active_event"] is None
    assert settled["event_history"] == {"welcome": 3}
    assert runtime_prompt(package, settled)[1] == []
    assert package.initial_state["relation_stage"] == "first_meeting"


def test_example_restock_pause_success_and_cooldown() -> None:
    package = load_directory(EXAMPLE)
    state = deepcopy(package.initial_state)
    state.update(relation_stage="familiar", flags={"welcome_done": True}, completed_events=["welcome"])
    state = apply_variable_patch(
        state, [{"op": "replace", "path": "/scene/activity", "value": "sorting"}],
        package.writable_paths, package.state_schema,
    )
    prompt, candidates = runtime_prompt(package, state)
    assert [event["id"] for event in candidates] == ["restock"]
    assert "当前正在整理书架" in prompt
    state, _ = apply_result(package, state, AuditResult("trigger", "restock"), ["restock"])
    state, _ = apply_result(
        package, state, AuditResult("branch", "restock", signals={"paused": True}, branch_id="pause"),
    )
    assert state["active_event"] is None
    assert state["completed_events"] == ["welcome"]
    assert state["event_history"] == {"restock": 2}
    for _ in range(2):
        assert runtime_prompt(package, state)[1] == []
        state, _ = apply_result(package, state, AuditResult("none"))
    assert [event["id"] for event in runtime_prompt(package, state)[1]] == ["restock"]
    state, _ = apply_result(package, state, AuditResult("trigger", "restock"), ["restock"])
    state, changed = apply_result(package, state, AuditResult("success", "restock", signals={"sorted": True}))
    assert changed == "restock"
    assert state["trust"] == 1
    assert state["completed_events"] == ["welcome", "restock"]
    assert state["event_history"] == {"restock": 6}


def test_example_mvu_protocol_updates_scene_for_next_pool_round() -> None:
    package = replace(load_directory(EXAMPLE), update_mode="mvu")
    state = deepcopy(package.initial_state)
    state.update(relation_stage="familiar", flags={"welcome_done": True}, completed_events=["welcome"])
    prompt, candidates = runtime_prompt(package, state)
    assert candidates == []
    assert "[MVU 变量更新协议]" in prompt
    assert "<EventUpdate>" in prompt
    assert package.audit_prompt not in prompt
    response = (
        '店员开始整理书架。<UpdateVariable>'
        '<JSONPatch>[{"op":"replace","path":"/stat_data/scene/activity","value":"sorting"}]</JSONPatch>'
        '<EventUpdate>{"action":"none","event_id":null,"signals":{},"deltas":{},"evidence":[]}</EventUpdate>'
        '</UpdateVariable>'
    )
    clean, patches, event = extract_update(response)
    updated, _ = apply_result(package, state, parse_audit_response(event), [])
    updated = apply_variable_patch(updated, patches, package.writable_paths, package.state_schema)
    assert clean == "店员开始整理书架。"
    assert state["scene"]["activity"] == "browsing"
    assert updated["scene"]["activity"] == "sorting"
    assert [event["id"] for event in runtime_prompt(package, updated)[1]] == ["restock"]
