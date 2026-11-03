from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import yaml

from astrbot_plugin_rolecard_runtime.package_loader import load_directory, load_json, load_zip, parse_event
from astrbot_plugin_rolecard_runtime.prompt_builder import build_prompt
from astrbot_plugin_rolecard_runtime.repository import PackageRepository


def standard_files() -> dict[str, str]:
    initial = {
        "relation_stage": "初识",
        "trust": 0,
        "dependency": 0,
        "feminine_acceptance": 10,
        "lust": None,
        "active_event": None,
        "event_step": 0,
        "completed_events": [],
        "flags": {"icebreaking_done": False},
    }
    manifest = {
        "schema": "astrbot-rolecard/v1",
        "package_id": "sample-card",
        "display_name": "示例卡",
        "version": "1.2.0",
        "card": {"path": "card/character.json"},
        "state": {"contract": "state/contract.yaml", "audit_prompt": "state/audit_system_prompt.md"},
        "stages": [
            {"id": "初识", "name": "初识", "path": "prompts/stage_1.md"},
            {"id": "恋爱", "name": "恋爱", "path": "prompts/stage_2.md"},
        ],
        "worldbook": [
            {"name": "常驻", "path": "worldbook/core.md", "mode": "resident"},
            {"name": "阶段差异", "path": "worldbook/stages.md", "mode": "conditional", "condition": "relation_stage == '{stage}'"},
            {"name": "关键词", "path": "worldbook/keyword.md", "mode": "keyword", "keywords": ["画夹"]},
            {"name": "接受度", "path": "worldbook/acceptance.md", "mode": "conditional", "condition": "feminine_acceptance >= {min} && feminine_acceptance <= {max}"},
        ],
        "events": [{"path": "events/icebreaking.md"}],
        "adult_events": [{"path": "adult_events/adult.md"}],
        "greeting": "greetings/first_mes.md",
    }
    card = {
        "spec": "chara_card_v2",
        "data": {
            "name": "示例卡",
            "personality": "核心人设",
            "scenario": "合租场景",
            "extensions": {"mvu": {"initial_variables": initial}},
        },
    }
    return {
        "manifest.yaml": yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        "card/character.json": json.dumps(card, ensure_ascii=False),
        "state/contract.yaml": yaml.safe_dump({"initial_state": initial}, allow_unicode=True),
        "state/audit_system_prompt.md": "只输出审计 JSON。",
        "prompts/stage_1.md": "阶段一 {{user}}",
        "prompts/stage_2.md": "阶段二 {{user}}",
        "worldbook/core.md": "核心世界书",
        "worldbook/stages.md": "### 【初识阶段】\n初识内容\n### 【恋爱阶段】\n恋爱内容",
        "worldbook/keyword.md": "画夹世界书",
        "worldbook/acceptance.md": "### 【0–19 分段】\n低接受度\n### 【20–39 分段】\n中接受度",
        "events/icebreaking.md": event_text("icebreaking", "初识", "恋爱"),
        "adult_events/adult.md": event_text("adult", "恋爱", "恋爱事件"),
        "greetings/first_mes.md": "你好，{{user}}。",
    }


def event_text(event_id: str, stage: str, title: str) -> str:
    metadata = {
        "event_id": event_id,
        "title": title,
        "target_stage": stage,
        "is_repeatable": False,
        "guard": {"flags_required": {"icebreaking_done": False}},
        "lifecycle": {"on_success_mutation": {"relation_stage": "恋爱", "trust": "+= 10", "flags": {"icebreaking_done": True}, "completed_events": f"push('{event_id}')"}},
    }
    return f"---\n{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}---\n事件正文"


def legacy_files() -> dict[str, str]:
    initial = json.loads(standard_files()["card/character.json"])["data"]["extensions"]["mvu"]["initial_variables"]
    card = {
        "spec": "chara_card_v2",
        "data": {
            "name": "sample-card",
            "personality": "通用示例角色",
            "first_mes": "你好，{{user}}。",
            "extensions": {"mvu": {"initial_variables": initial}},
        },
    }
    return {
        "card.json": json.dumps(card, ensure_ascii=False),
        "prompt/stage_1_初识.md": "初识阶段：与 {{user}} 初次交谈。",
        "prompt/stage_2_熟悉.md": "熟悉阶段：与 {{user}} 分享日常。",
        "worldbook/constant.md": "---\ntype: constant\ntitle: 示例常驻世界书\n---\n通用常驻世界书",
        "event/example.md": "---\nevent_id: example\ntitle: 示例事件\ntarget_stage: 初识\nlifecycle:\n  on_success_mutation:\n    relation_stage: 熟悉\n---\n通用事件正文",
        "up/updater_system_prompt.md": "只输出审计 JSON。",
    }


def make_zip(files: dict[str, str], prefix: str = "") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, text in files.items():
            archive.writestr(prefix + name, text)
    return stream.getvalue()


def test_standard_manifest_loads_from_directory_and_zip(tmp_path: Path) -> None:
    files = standard_files()
    directory = tmp_path / "card"
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    from_directory = load_directory(directory)
    from_zip = load_zip(make_zip(files, "nested/"), "sample.zip")
    assert from_directory.package_id == "sample-card"
    assert from_zip.display_name == "示例卡"
    assert [stage["id"] for stage in from_zip.stages] == ["初识", "恋爱"]
    assert from_zip.events[0]["id"] == "icebreaking"
    assert from_zip.adult_events[0]["id"] == "adult"

    repository = PackageRepository(tmp_path / "packages")
    imported = repository.import_zip(make_zip(files, "nested/"), "sample.zip")
    repository.reload()
    assert repository.get(imported.package_id) is not None
    assert repository.get(imported.package_id).stages[0]["id"] == "初识"


def test_v2_card_field_mapping_and_legacy_guard_expression() -> None:
    card = {"spec": "chara_card_v2", "data": {"name": "V2 角色", "description": "描述", "personality": "性格", "scenario": "场景", "first_mes": "问候", "extensions": {"mvu": {"initial_variables": {"relation_stage": "初识", "trust": 4}}}}}
    package = load_zip(make_zip({"card.json": json.dumps(card, ensure_ascii=False)}))
    assert package.package_id == "V2 角色"
    assert "描述" in package.core_prompt
    assert package.greeting == "问候"
    assert package.initial_state["trust"] == 4
    event = parse_event("---\nevent_id: sketchbook\ntarget_stage: 暗恋挣扎\nguard:\n  trigger_expression: \"state.relation_stage === '暗恋挣扎' && state.trust >= 30 && state.feminine_acceptance >= 40 && !state.flags.sketchbook_found && !state.completed_events.includes('sketchbook')\"\n---\n正文", "fallback")
    assert event["guard"]["stage"] == "暗恋挣扎"
    assert event["guard"]["trust_min"] == 30
    assert event["guard"]["feminine_acceptance_min"] == 40
    assert event["guard"]["flags_required"] == {"sketchbook_found": False}
    assert event["guard"]["completed_events_exclude"] == ["sketchbook"]


def test_standalone_v2_json_can_be_imported_and_reloaded(tmp_path: Path) -> None:
    card = {
        "spec": "chara_card_v2",
        "data": {
            "name": "独立 JSON 角色",
            "description": "基础描述",
            "first_mes": "你好，{{user}}。",
            "extensions": {
                "mvu": {
                    "initial_variables": {
                        "relation_stage": "初识",
                        "trust": 2,
                    }
                }
            },
        },
    }
    data = json.dumps(card, ensure_ascii=False).encode("utf-8")
    package = load_json(data, "character.json")
    assert package.package_id == "独立 JSON 角色"
    assert package.initial_state["trust"] == 2
    assert package.stages[0]["id"] == "初识"

    repository = PackageRepository(tmp_path / "packages")
    imported = repository.import_json(data, "character.json")
    repository.reload()
    assert repository.get(imported.package_id) is not None
    assert repository.get(imported.package_id).greeting == "你好，{{user}}。"


def test_legacy_layout_compatibility_and_current_stage_prompt() -> None:
    package = load_zip(make_zip(legacy_files()), "sample-legacy.zip")
    assert package.package_id == "sample-card"
    assert [stage["id"] for stage in package.stages] == ["初识", "熟悉"]
    assert [event["id"] for event in package.events] == ["example"]
    assert package.adult_events == []
    assert package.worldbook[0]["mode"] == "resident"
    assert package.audit_prompt == "只输出审计 JSON。"
    prompt, candidates = build_prompt(package, package.initial_state, "你好", "用户", nsfw_enabled=False, private_chat=True)
    stage_text = prompt.split("[当前阶段人设]", 1)[1].split("[当前世界书]", 1)[0]
    assert "初识阶段：与 用户 初次交谈。" in stage_text
    assert "熟悉阶段" not in stage_text
    assert "通用常驻世界书" in prompt
    assert [event["id"] for event in candidates] == ["example"]
