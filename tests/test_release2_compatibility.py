from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_plugin_rolecard_runtime.package_loader import load_zip
from astrbot_plugin_rolecard_runtime.prompt_builder import build_prompt
from astrbot_plugin_rolecard_runtime.repository import PackageRepository
from test_package_loader import legacy_files, make_zip


@pytest.mark.parametrize("prefix", ["", "nested/"])
def test_legacy_zip_import_and_reload(tmp_path: Path, prefix: str) -> None:
    files = legacy_files()
    repository = PackageRepository(tmp_path / "packages")
    imported = repository.import_file(make_zip(files, prefix), "sample-legacy.zip")
    assert imported.package_id == "sample-card"
    for name, text in files.items():
        assert (repository.root / imported.package_id / name).read_text(encoding="utf-8") == text

    repository.reload()
    package = repository.get(imported.package_id)
    assert package is not None
    assert repository.diagnostics == []
    assert package.stages == imported.stages
    assert package.initial_state == imported.initial_state
    assert package.worldbook == imported.worldbook
    assert package.events == imported.events
    assert package.audit_prompt == imported.audit_prompt
    assert package.greeting == "你好，{{user}}。"


def test_legacy_directory_import_and_reload(tmp_path: Path) -> None:
    directory = tmp_path / "legacy-card"
    for name, text in legacy_files().items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    repository = PackageRepository(tmp_path / "packages")
    imported = repository.import_directory(directory)
    repository.reload()
    package = repository.get(imported.package_id)
    assert package is not None
    assert package.package_id == "sample-card"
    assert [stage["id"] for stage in package.stages] == ["初识", "熟悉"]
    assert package.events[0]["success"]["relation_stage"] == "熟悉"
    assert repository.diagnostics == []


@pytest.mark.parametrize("stage, other_stage, event_ids", [
    ("初识", "熟悉", ["example"]),
    ("熟悉", "初识", []),
])
def test_legacy_stage_and_event_routing(stage: str, other_stage: str, event_ids: list[str]) -> None:
    files = legacy_files()
    package = load_zip(make_zip(files), "sample-legacy.zip")
    state = {**package.initial_state, "relation_stage": stage}
    prompt, candidates = build_prompt(package, state, "你好", "用户", nsfw_enabled=False, private_chat=True)
    stage_text = prompt.split("[当前阶段人设]", 1)[1].split("[当前世界书]", 1)[0]
    assert f"{stage}阶段：与 用户" in stage_text
    assert f"{other_stage}阶段" not in stage_text
    assert "通用常驻世界书" in prompt
    assert [event["id"] for event in candidates] == event_ids
