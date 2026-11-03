from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import SchemaError, ValidationError
from jsonschema.validators import validator_for

from .contract import clamp_state, initial_state

MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 80 * 1024 * 1024


@dataclass
class RoleCardPackage:
    package_id: str
    display_name: str
    version: str
    core_prompt: str
    greeting: str
    stages: list[dict[str, str]]
    initial_state: dict[str, Any]
    worldbook: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    adult_events: list[dict[str, Any]] = field(default_factory=list)
    audit_prompt: str = ""
    source: str = ""
    runtime: dict[str, Any] = field(default_factory=dict)
    state_schema: dict[str, Any] = field(default_factory=dict)
    writable_paths: list[str] = field(default_factory=list)
    update_mode: str = "audit"
    event_pool: str = ""


class PackageError(ValueError):
    pass


def _safe_archive_files(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError("ZIP 超过 20 MB")
    files: dict[str, bytes] = {}
    unpacked = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                    or re.match(r"^[A-Za-z]:", info.filename)
                ):
                    raise PackageError(f"ZIP 包含非法路径：{info.filename}")
                if info.is_dir():
                    continue
                unpacked += info.file_size
                if unpacked > MAX_UNPACKED_BYTES:
                    raise PackageError("ZIP 解压后超过 80 MB")
                files[info.filename] = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise PackageError("文件不是有效 ZIP") from exc
    return files


def _text_files(files: dict[str, bytes]) -> dict[str, str]:
    result = {}
    for name, data in files.items():
        try:
            result[name] = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
    return result


def load_zip(data: bytes, source: str = "") -> RoleCardPackage:
    files = _text_files(_safe_archive_files(data))
    root = _find_manifest_root(files)
    if root is not None:
        return _load_manifest(files, root, source)
    legacy_root = _find_legacy_root(files)
    if legacy_root:
        files = {
            name[len(legacy_root) + 1 :]: text
            for name, text in files.items()
            if name.startswith(legacy_root + "/")
        }
    if any(name.startswith("prompt/") for name in files):
        return _load_legacy(files, source)
    return _load_v2_json(files, source)


def load_json(data: bytes, source: str = "") -> RoleCardPackage:
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError("JSON 超过 20 MB")
    try:
        card = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError("文件不是有效的角色卡 JSON") from exc
    if not isinstance(card, dict):
        raise PackageError("角色卡 JSON 必须是对象")
    return _load_v2_card(card, source)


def load_directory(path: Path) -> RoleCardPackage:
    if not path.is_dir():
        raise PackageError(f"卡包目录不存在：{path}")
    files: dict[str, str] = {}
    for item in path.rglob("*"):
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            try:
                files[relative] = item.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
    if "manifest.yaml" in files:
        return _load_manifest(files, "", str(path))
    if any(name.startswith("prompt/") for name in files):
        return _load_legacy(files, str(path))
    return _load_v2_json(files, str(path))


def _join(root: str, name: str) -> str:
    return f"{root}/{name}" if root else name


def _find_manifest_root(files: dict[str, Any]) -> str | None:
    roots = {"/".join(PurePosixPath(name).parts[:-1]) for name in files}
    return next(
        (candidate for candidate in ("", *sorted(roots, key=len)) if _join(candidate, "manifest.yaml") in files),
        None,
    )


def _find_legacy_root(files: dict[str, Any]) -> str:
    roots = {"/".join(PurePosixPath(name).parts[:-1]) for name in files}
    return next(
        (
            candidate
            for candidate in ("", *sorted(roots, key=len))
            if any(name.startswith(_join(candidate, "prompt") + "/") for name in files)
        ),
        "",
    )


def _yaml(text: str, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise PackageError(f"{label} YAML 格式错误：{exc}") from exc
    if not isinstance(value, dict):
        raise PackageError(f"{label} 必须是 YAML 对象")
    return value


def _read(files: dict[str, str], root: str, name: str) -> str:
    path = _join(root, name)
    if path not in files:
        raise PackageError(f"缺少卡包文件：{path}")
    return files[path]


def _load_manifest(files: dict[str, str], root: str, source: str) -> RoleCardPackage:
    manifest = _yaml(_read(files, root, "manifest.yaml"), "manifest")
    if manifest.get("schema") != "astrbot-rolecard/v1":
        raise PackageError("不支持的卡包 schema")
    card = json.loads(_read(files, root, manifest.get("card", {}).get("path", "card/character.json")))
    data = card.get("data", card)
    state_config = manifest.get("state", {})
    initial = _yaml(_read(files, root, state_config.get("contract", "state/contract.yaml")), "state contract").get("initial_state")
    if not isinstance(initial, dict):
        initial = data.get("extensions", {}).get("mvu", {}).get("initial_variables")
    if not isinstance(initial, dict):
        raise PackageError("卡包没有有效的初始状态")

    stages = []
    for stage in manifest.get("stages", []):
        stages.append({"id": str(stage["id"]), "name": str(stage.get("name", stage["id"])), "content": _read(files, root, stage["path"])})
    if not stages:
        raise PackageError("manifest 至少要声明一个阶段")

    worldbook = []
    for entry in manifest.get("worldbook", []):
        _, content = _frontmatter(_read(files, root, entry["path"]))
        worldbook.append({"name": entry.get("name", Path(entry["path"]).stem), "mode": entry.get("mode", "resident"), "keywords": entry.get("keywords", []), "condition": entry.get("condition"), "content": content.strip()})
    events = _load_event_paths(files, root, manifest.get("events", []))
    adult_events = _load_event_paths(files, root, manifest.get("adult_events", []))
    audit_path = state_config.get("audit_prompt", "state/audit_system_prompt.md")
    audit_prompt = files.get(_join(root, audit_path), "")
    core = "\n\n".join(str(data[key]) for key in ("system_prompt", "personality", "scenario", "description", "post_history_instructions") if data.get(key))
    package_id = _package_id(manifest["package_id"])
    normalized_initial = initial_state(initial)
    clamp_state(normalized_initial, stages)
    runtime = manifest.get("runtime", {})
    engine = runtime.get("engine", "declarative")
    if engine not in {"declarative", "ejs"}:
        raise PackageError(f"不支持的模板引擎：{engine}")
    update_mode = state_config.get("update_mode", "audit")
    if update_mode not in {"audit", "mvu"}:
        raise PackageError(f"不支持的状态更新模式：{update_mode}")
    state_schema = json.loads(_read(files, root, state_config["schema"])) if state_config.get("schema") else {}
    if state_schema:
        validator = validator_for(state_schema)
        try:
            validator.check_schema(state_schema)
            validator(state_schema).validate(normalized_initial)
        except (ValidationError, SchemaError) as exc:
            raise PackageError(f"初始状态不符合 schema：{exc.message}") from exc
    event_pool = _read(files, root, runtime["event_pool"]) if runtime.get("event_pool") else ""
    if event_pool and engine != "ejs":
        raise PackageError("event_pool 必须声明 runtime.engine: ejs")
    return RoleCardPackage(
        package_id=package_id,
        display_name=str(manifest.get("display_name", data.get("name", package_id))),
        version=str(manifest.get("version", "1.0.0")),
        core_prompt=core,
        greeting=files.get(_join(root, manifest.get("greeting", "greetings/first_mes.md")), str(data.get("first_mes", ""))),
        stages=stages,
        initial_state=normalized_initial,
        worldbook=worldbook,
        events=events,
        adult_events=adult_events,
        audit_prompt=audit_prompt,
        source=source,
        runtime=runtime,
        state_schema=state_schema,
        writable_paths=state_config.get("writable_paths", []),
        update_mode=update_mode,
        event_pool=event_pool,
    )


def _package_id(value: Any) -> str:
    package_id = str(value).strip()
    if not package_id or package_id in {".", ".."} or re.search(r"[\\/]", package_id):
        raise PackageError("package_id 必须是非空目录名")
    return package_id


def _load_v2_json(files: dict[str, str], source: str) -> RoleCardPackage:
    card_path = next((name for name in files if name.lower().endswith(".json")), None)
    if not card_path:
        raise PackageError("未找到 manifest.yaml 或 V2 JSON 卡片")
    try:
        card = json.loads(files[card_path])
    except json.JSONDecodeError as exc:
        raise PackageError("角色卡 JSON 格式错误") from exc
    if not isinstance(card, dict):
        raise PackageError("角色卡 JSON 必须是对象")
    return _load_v2_card(card, source)


def _load_v2_card(card: dict[str, Any], source: str) -> RoleCardPackage:
    data = card.get("data", card)
    if not isinstance(data, dict):
        raise PackageError("角色卡 JSON 的 data 字段必须是对象")
    embedded = data.get("extensions", {}).get("astrbot_runtime", {}).get("files")
    if isinstance(embedded, dict):
        if not all(isinstance(name, str) and isinstance(text, str) for name, text in embedded.items()):
            raise PackageError("内嵌运行时 files 必须是路径到 UTF-8 文本的对象")
        return _load_manifest(embedded, "", source)
    initial = data.get("extensions", {}).get("mvu", {}).get("initial_variables")
    if not isinstance(initial, dict):
        initial = {
            "relation_stage": "默认",
            "trust": 0,
            "dependency": 0,
            "feminine_acceptance": 0,
            "lust": None,
            "active_event": None,
            "event_step": 0,
            "completed_events": [],
            "flags": {},
        }
    name = str(data.get("name") or Path(source).stem or "rolecard")
    package_id = _package_id(name)
    core = "\n\n".join(str(data.get(key, "")) for key in ("description", "personality", "scenario") if data.get(key))
    stages = [{"id": str(initial.get("relation_stage", "默认")), "name": str(initial.get("relation_stage", "默认")), "content": ""}]
    normalized_initial = initial_state(initial)
    clamp_state(normalized_initial, stages)
    return RoleCardPackage(
        package_id,
        name,
        str(card.get("spec", "chara_card_v2")),
        core,
        str(data.get("first_mes", "")),
        stages,
        normalized_initial,
        audit_prompt="你负责客观提取本轮证据，并只输出规定的状态审计 JSON。",
        source=source,
    )


def _load_event_paths(files: dict[str, str], root: str, entries: list[Any]) -> list[dict[str, Any]]:
    result = []
    for entry in entries:
        path = entry if isinstance(entry, str) else entry["path"]
        content = _read(files, root, path)
        event = parse_event(content, Path(path).stem)
        result.append(event)
    return result


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n)?", text, re.S)
    if not match:
        return {}, text
    return _yaml(match.group(1), "front matter"), text[match.end():]


def parse_event(text: str, fallback_id: str) -> dict[str, Any]:
    meta, body = _frontmatter(text)
    event_id = str(meta.get("event_id", fallback_id))
    guard = meta.get("guard", {}) or {}
    lifecycle = meta.get("lifecycle", {}) or {}
    conditions = {
        "stage": guard.get("relation_stage", meta.get("target_stage")),
        "trust_min": guard.get("trust_min"),
        "dependency_min": guard.get("dependency_min"),
        "feminine_acceptance_min": guard.get("feminine_acceptance_min"),
        "lust_min": guard.get("lust_min"),
        "flags_required": guard.get("flags_required", {}),
        "completed_events_exclude": guard.get("completed_events_exclude", []),
        "completed_events_required": guard.get("completed_events_required", []),
    }
    _merge_expression_guard(conditions, str(guard.get("trigger_expression", "")))
    return {
        "id": event_id,
        "title": str(meta.get("title", fallback_id)),
        "stage": conditions["stage"],
        "exclusive": bool(meta.get("exclusive", True)),
        "repeatable": bool(meta.get("is_repeatable", False)),
        "guard": conditions,
        "success": lifecycle.get("on_success_mutation", {}) or {},
        "failure": lifecycle.get("on_fail_mutation", {}) or {},
        "success_condition": lifecycle.get("on_success_condition", ""),
        "failure_condition": lifecycle.get("on_fail_condition", ""),
        "branches": lifecycle.get("branches", {}) or {},
        "pool": meta.get("pool", {}) or {},
        "content": body.strip(),
    }


def _merge_expression_guard(guard: dict[str, Any], expression: str) -> None:
    """Extract the small declarative subset used by legacy card guards."""
    if not expression:
        return
    stage = re.search(r"state\.relation_stage\s*===\s*['\"]([^'\"]+)['\"]", expression)
    if stage and guard.get("stage") is None:
        guard["stage"] = stage.group(1)
    for field in ("trust", "dependency", "feminine_acceptance", "lust"):
        match = re.search(rf"state\.{field}\s*>=\s*(\d+)", expression)
        if match:
            guard[f"{field}_min"] = int(match.group(1))
    required = dict(guard.get("flags_required") or {})
    for field in re.findall(r"state\.flags\.([A-Za-z0-9_]+)", expression):
        if re.search(rf"!\s*state\.flags\.{re.escape(field)}", expression) or re.search(
            rf"state\.flags\.{re.escape(field)}\s*===\s*false", expression
        ):
            required[field] = False
        elif re.search(rf"state\.flags\.{re.escape(field)}\s*===\s*true", expression):
            required[field] = True
    guard["flags_required"] = required
    excluded = list(guard.get("completed_events_exclude") or [])
    for completed_id in re.findall(
        r"!\s*state\.completed_events\.includes\(\s*['\"]([^'\"]+)['\"]\s*\)", expression
    ):
        if completed_id not in excluded:
            excluded.append(completed_id)
    guard["completed_events_exclude"] = excluded
    required_events = list(guard.get("completed_events_required", []))
    for match in re.finditer(r"(!\s*)?state\.completed_events\.includes\(\s*['\"]([^'\"]+)['\"]\s*\)", expression):
        if not match[1] and match[2] not in required_events:
            required_events.append(match[2])
    guard["completed_events_required"] = required_events


def _load_legacy(files: dict[str, str], source: str) -> RoleCardPackage:
    card_path = next((name for name in files if name.lower().endswith(".json") and "/" not in name), None)
    if not card_path:
        raise PackageError("未找到 manifest.yaml 或根目录的 V2 JSON 卡片")
    card = json.loads(files[card_path])
    data = card.get("data", card)
    initial = data.get("extensions", {}).get("mvu", {}).get("initial_variables")
    if not isinstance(initial, dict):
        raise PackageError("V2 卡片缺少 extensions.mvu.initial_variables")

    stage_files = sorted(
        name
        for name in files
        if re.match(r"prompt/stage_\d+_.+\.md$", name, re.I)
    )
    stages = []
    for index, name in enumerate(stage_files, 1):
        match = re.search(r"stage_\d+_(.+)\.md$", name)
        stage_id = match.group(1) if match else f"stage_{index}"
        stages.append({"id": stage_id, "name": stage_id, "content": files[name]})
    if not stages:
        raise PackageError("旧卡包没有 prompt/stage_*.md 阶段人设")

    worldbook = []
    for name, text in sorted(files.items()):
        if not name.startswith("worldbook/") or not name.lower().endswith(".md"):
            continue
        meta, body = _frontmatter(text)
        mode = "resident" if meta.get("type") == "constant" else "conditional" if meta.get("type") == "conditional" else "keyword"
        worldbook.append({"name": str(meta.get("title", Path(name).stem)), "mode": mode, "keywords": meta.get("keywords", meta.get("keys", [])), "condition": meta.get("condition"), "content": body.strip(), "source": name})

    events = []
    adult_events = []
    for name, text in sorted(files.items()):
        if not (name.startswith("event/") or name.startswith("nsfw/")):
            continue
        event = parse_event(text, Path(name).stem)
        (adult_events if name.startswith("nsfw/") else events).append(event)

    greeting = files.get("greetings/first_mes.md", str(data.get("first_mes", "")))
    core_parts = [str(data.get("personality", "")), str(data.get("scenario", "")), str(data.get("creator_notes", ""))]
    for name in ("worldbook/01_常驻_核心基础人设.md", "worldbook/02_常驻_语言风格与微动作规范.md"):
        if name in files:
            _, body = _frontmatter(files[name])
            core_parts.append(body.strip())
    rule_sources = (
        "design/state-contract.md",
        "up/event_rules.md",
        "up/delta_constraints.md",
    )
    audit_prompt = "\n\n".join(
        files[name] for name in ("up/updater_system_prompt.md", *rule_sources) if name in files
    )
    if not audit_prompt:
        raise PackageError("旧卡包缺少 up/updater_system_prompt.md")
    package_id = _package_id(re.sub(r"[\\/]+", "-", str(data.get("name", Path(card_path).stem))).strip() or "rolecard")
    normalized_initial = initial_state(initial)
    clamp_state(normalized_initial, stages)
    return RoleCardPackage(package_id, str(data.get("name", Path(card_path).stem)), str(card.get("spec", "chara_card_v2")), "\n\n".join(part for part in core_parts if part), greeting, stages, normalized_initial, worldbook, events, adult_events, audit_prompt, source)

