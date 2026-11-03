from __future__ import annotations

import ast
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from astrbot_plugin_rolecard_runtime.audit import AuditError, build_audit_prompt, parse_audit_response
from astrbot_plugin_rolecard_runtime.event_engine import apply_audit
from astrbot_plugin_rolecard_runtime.ejs_runtime import TemplateError
from astrbot_plugin_rolecard_runtime.mvu import UPDATE_OUTPUT, apply_variable_patch, extract_update
from astrbot_plugin_rolecard_runtime.package_loader import load_zip
from astrbot_plugin_rolecard_runtime.state_store import StateStore
from test_ejs_mvu import ejs_files, make_zip


def _extract_hook_class() -> type:
    source_path = Path(__file__).parents[1] / "astrbot_plugin_rolecard_runtime" / "main.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    source_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RoleCardRuntimePlugin")
    selected = {
        "_session_identity",
        "_bound_package",
        "prepare_mvu_generation",
        "on_llm_request",
        "on_llm_response",
    }
    methods = []
    for node in source_class.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in selected:
            node.decorator_list = []
            methods.append(node)
    extracted = ast.ClassDef(
        name="ExtractedRuntimeHooks",
        bases=[],
        keywords=[],
        decorator_list=[],
        body=methods,
    )
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), extracted],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {
        "asyncio": asyncio,
        "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
        "AuditError": AuditError,
        "TemplateError": TemplateError,
        "UPDATE_OUTPUT": UPDATE_OUTPUT,
        "apply_audit": apply_audit,
        "apply_variable_patch": apply_variable_patch,
        "build_audit_prompt": build_audit_prompt,
        "build_runtime_prompt": __import__(
            "astrbot_plugin_rolecard_runtime.prompt_builder",
            fromlist=["build_runtime_prompt"],
        ).build_runtime_prompt,
        "extract_update": extract_update,
        "parse_audit_response": parse_audit_response,
    }
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["ExtractedRuntimeHooks"]


HookPlugin = _extract_hook_class()


class FakeEvent:
    def __init__(self, message: str = "画夹"):
        self.unified_msg_origin = "session"
        self.message_str = message
        self._extras: dict[str, object] = {}
        self.result = None
        self.stopped = False

    def get_sender_id(self) -> str:
        return "member"

    def get_sender_name(self) -> str:
        return "用户"

    def is_private_chat(self) -> bool:
        return True

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def plain_result(self, text: str):
        return SimpleNamespace(text=text)

    def set_result(self, result) -> None:
        self.result = result

    def stop_event(self) -> None:
        self.stopped = True


class FakeProvider:
    def __init__(self, completion_text: str = "{\"action\":\"none\"}"):
        self.completion_text = completion_text
        self.calls: list[dict[str, object]] = []

    async def llm_generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(completion_text=self.completion_text)


def _package(*, update_mode: str = "audit", invalid_pool: bool = False):
    files = ejs_files()
    manifest = yaml.safe_load(files["manifest.yaml"])
    manifest["state"]["update_mode"] = update_mode
    if invalid_pool:
        files["runtime/pool.ejs"] = "不是JSON"
    files["manifest.yaml"] = yaml.safe_dump(manifest, allow_unicode=True)
    return load_zip(make_zip(files))


def _plugin(tmp_path: Path, package, *, audit_provider_id: str = "", provider_text: str = "{\"action\":\"none\"}"):
    store = StateStore(tmp_path / "runtime.sqlite3")
    store.bind("session", package.package_id)
    plugin = HookPlugin.__new__(HookPlugin)
    plugin.config = {"audit_provider_id": audit_provider_id}
    plugin.enabled = True
    plugin.status_image_enabled = False
    plugin.store = store
    plugin.repository = SimpleNamespace(get=lambda package_id: package if package_id == package.package_id else None)
    plugin.pending = {}
    plugin.context = FakeProvider(provider_text)
    return plugin, store


def _request(plugin, event: FakeEvent):
    request = SimpleNamespace(system_prompt="base")
    asyncio.run(plugin.on_llm_request(event, request))
    return request


def _response(plugin, event: FakeEvent, text: str):
    response = SimpleNamespace(completion_text=text)
    asyncio.run(plugin.on_llm_response(event, response))
    return response


def test_audit_hook_uses_real_provider_and_saves_scene_patch(tmp_path: Path):
    package = _package()
    plugin, store = _plugin(
        tmp_path,
        package,
        audit_provider_id="audit-model",
        provider_text='{"action":"none","patches":[{"op":"replace","path":"/stat_data/scene/count","value":2}]}'
    )
    try:
        event = FakeEvent()
        request = _request(plugin, event)
        response = _response(plugin, event, "正文")

        assert request.system_prompt.startswith("base\n\n")
        assert response.completion_text == "正文"
        state = store.state("session", "member", package.package_id, package.initial_state)
        assert state["scene"]["count"] == 2
        assert plugin.context.calls[0]["chat_provider_id"] == "audit-model"
        assert plugin.context.calls[0]["stream"] is False
    finally:
        store.close()


def test_audit_without_provider_does_not_update_state(tmp_path: Path):
    package = _package()
    plugin, store = _plugin(tmp_path, package, provider_text='{"action":"none"}')
    try:
        event = FakeEvent()
        _request(plugin, event)
        before = copy.deepcopy(store.state("session", "member", package.package_id, package.initial_state))
        _response(plugin, event, "正文")

        assert store.state("session", "member", package.package_id, package.initial_state) == before
        assert plugin.context.calls == []
        assert store.recent_audits(1)[0]["action"] == "unavailable"
    finally:
        store.close()


def test_mvu_hook_parses_update_without_audit_provider_and_removes_block(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        response = _response(
            plugin,
            event,
            '正文<UpdateVariable><JSONPatch>[{"op":"replace","path":"/stat_data/scene/count","value":2}]</JSONPatch>'
            '<EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>',
        )

        assert response.completion_text == "正文"
        assert plugin.context.calls == []
        state = store.state("session", "member", package.package_id, package.initial_state)
        assert state["scene"]["count"] == 2
        assert state["turn_count"] == 1
    finally:
        store.close()


def test_mvu_schema_error_rolls_back_the_whole_turn(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        response = _response(
            plugin,
            event,
            '正文<UpdateVariable><JSONPatch>[{"op":"replace","path":"/stat_data/scene/location","value":"invented"}]</JSONPatch>'
            '<EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>',
        )

        assert response.completion_text == "正文"
        assert store.state("session", "member", package.package_id, package.initial_state) == package.initial_state
        assert store.recent_audits(1)[0]["action"] == "error"
    finally:
        store.close()


def test_ejs_template_failure_stops_event(tmp_path: Path):
    package = _package(invalid_pool=True)
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        request = _request(plugin, event)

        assert request.system_prompt == "base"
        assert event.stopped is True
        assert "模板加载失败" in event.result.text
        assert plugin.pending == {}
    finally:
        store.close()


def test_stale_response_does_not_overwrite_newer_state(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        newer = copy.deepcopy(package.initial_state)
        newer["scene"]["count"] = 9
        store.save_state("session", "member", package.package_id, newer)

        _response(
            plugin,
            event,
            '正文<UpdateVariable><JSONPatch>[{"op":"replace","path":"/stat_data/scene/count","value":2}]</JSONPatch>'
            '<EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>',
        )

        state = store.state("session", "member", package.package_id, package.initial_state)
        assert state["scene"]["count"] == 9
        assert store.recent_audits(1)[0]["action"] == "stale"
    finally:
        store.close()


def test_prepare_mvu_generation_disables_streaming_only_for_mvu_package(tmp_path: Path):
    mvu_package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, mvu_package)
    try:
        event = FakeEvent()
        asyncio.run(plugin.prepare_mvu_generation(event))
        assert event.get_extra("enable_streaming") is False
    finally:
        store.close()


def test_unclosed_mvu_update_is_hidden_and_not_saved(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        response = _response(plugin, event, '正文<UpdateVariable><JSONPatch>[{"op":"replace"')
        assert response.completion_text == "正文"
        assert store.state("session", "member", package.package_id, package.initial_state) == package.initial_state
    finally:
        store.close()


def test_response_after_unbinding_cannot_write_state(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        store.bind("session", None)
        _response(plugin, event, '正文<UpdateVariable><JSONPatch>[]</JSONPatch><EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>')
        assert store.state_rows() == []
    finally:
        store.close()


def test_invalid_event_and_scene_patch_are_rejected_together(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        _request(plugin, event)
        _response(plugin, event, '正文<UpdateVariable><JSONPatch>[{"op":"replace","path":"/scene/count","value":5}]</JSONPatch><EventUpdate>{"action":"trigger","event_id":"forged"}</EventUpdate></UpdateVariable>')
        assert store.state_rows() == []
        assert store.recent_audits(1)[0]["action"] == "error"
    finally:
        store.close()


def test_response_after_permission_change_cannot_write_state(tmp_path: Path):
    package = _package(update_mode="mvu")
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        store.set_nsfw("session", "member", True)
        _request(plugin, event)
        store.set_nsfw("session", "member", False)
        _response(plugin, event, '正文<UpdateVariable><JSONPatch>[]</JSONPatch><EventUpdate>{"action":"none"}</EventUpdate></UpdateVariable>')
        assert store.state_rows() == []
        assert store.recent_audits(1)[0]["action"] == "stale"
    finally:
        store.close()


@pytest.mark.parametrize("update_mode", ["audit", "mvu"])
def test_prepare_mvu_generation_leaves_audit_package_unchanged(tmp_path: Path, update_mode: str):
    package = _package(update_mode=update_mode)
    plugin, store = _plugin(tmp_path, package)
    try:
        event = FakeEvent()
        asyncio.run(plugin.prepare_mvu_generation(event))
        if update_mode == "audit":
            assert event.get_extra("enable_streaming") is None
    finally:
        store.close()
