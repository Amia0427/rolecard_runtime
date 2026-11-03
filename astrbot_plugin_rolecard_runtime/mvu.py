from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

import jsonpatch
from jsonpointer import JsonPointerException
from jsonpointer import resolve_pointer
from jsonschema import ValidationError
from jsonschema.validators import validator_for

UPDATE_BLOCK = re.compile(r"<UpdateVariable>\s*(.*?)\s*</UpdateVariable>", re.S)
UPDATE_OUTPUT = re.compile(r"<UpdateVariable>.*?(?:</UpdateVariable>|\Z)", re.S)


class VariableUpdateError(ValueError):
    pass


def extract_update(text: str) -> tuple[str, list[dict[str, Any]], str | None]:
    blocks = list(UPDATE_BLOCK.finditer(text))
    if not blocks:
        return text, [], None
    if len(blocks) != 1:
        raise VariableUpdateError("每轮只能输出一个 UpdateVariable")
    block = blocks[0].group(1)
    patch_block = re.search(r"<JSONPatch>\s*(.*?)\s*</JSONPatch>", block, re.S)
    event_block = re.search(r"<EventUpdate>\s*(.*?)\s*</EventUpdate>", block, re.S)
    try:
        patches = json.loads(patch_block.group(1)) if patch_block else []
    except json.JSONDecodeError as exc:
        raise VariableUpdateError("JSONPatch 不是有效 JSON") from exc
    if not isinstance(patches, list):
        raise VariableUpdateError("JSONPatch 必须是操作数组")
    return UPDATE_BLOCK.sub("", text).strip(), patches, event_block.group(1) if event_block else None


def apply_variable_patch(
    state: dict[str, Any],
    patches: list[dict[str, Any]],
    writable_paths: list[str],
    schema: dict[str, Any],
) -> dict[str, Any]:
    allowed = ["/" + path.replace(".", "/").strip("/") for path in writable_paths]
    operations = deepcopy(patches)
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") not in {"add", "remove", "replace", "move", "copy", "test", "delta", "insert"}:
            raise VariableUpdateError("JSONPatch 操作无效")
        if operation["op"] == "move" and "to" in operation:
            operation["path"] = operation.pop("to")
        for field in ("path", "from") if operation["op"] in {"move", "copy"} else ("path",):
            path = operation.get(field, "")
            if not isinstance(path, str):
                raise VariableUpdateError("JSONPatch 路径必须是字符串")
            if path.startswith("/stat_data/"):
                path = path[len("/stat_data"):]
            if not any(path == root or path.startswith(root + "/") for root in allowed):
                raise VariableUpdateError(f"变量路径不允许更新：{path}")
            operation[field] = path
    updated = deepcopy(state)
    try:
        for operation in operations:
            if operation["op"] == "insert":
                operation["op"] = "add"
            elif operation["op"] == "delta":
                value = resolve_pointer(updated, operation["path"])
                delta = operation.get("value")
                if type(value) not in (int, float) or type(delta) not in (int, float):
                    raise VariableUpdateError("delta 只能更新数值变量")
                operation.update(op="replace", value=value + delta)
            updated = jsonpatch.apply_patch(updated, [operation], in_place=False)
    except (jsonpatch.JsonPatchException, JsonPointerException) as exc:
        raise VariableUpdateError(f"JSONPatch 执行失败：{exc}") from exc
    validate_state(updated, schema)
    return updated


def validate_state(state: dict[str, Any], schema: dict[str, Any]) -> None:
    if not schema:
        return
    try:
        validator_for(schema)(schema).validate(state)
    except ValidationError as exc:
        raise VariableUpdateError(f"变量不符合 schema：{exc.message}") from exc


def update_instructions(writable_paths: list[str], schema: dict[str, Any]) -> str:
    return f"""[MVU 变量更新协议]
在回复末尾输出一个 <UpdateVariable> 块，其中包含：
<JSONPatch>[{{"op":"replace","path":"/stat_data/可写路径","value":"新值"}}]</JSONPatch>
<EventUpdate>{{"action":"none|trigger|step|success|fail|branch","event_id":null,"branch_id":null,"signals":{{}},"deltas":{{}},"evidence":[]}}</EventUpdate>
没有变化时 JSONPatch 输出 []。EventUpdate 必须依据本轮真实事实；success/fail/branch 的 signals 必须满足对应结算条件。
JSONPatch 只可写：{json.dumps(writable_paths, ensure_ascii=False)}。
阶段、数值、事件与 flags 只由事件结算和受限日常增量更新，不得在补丁中改动。
变量 schema：{json.dumps(schema, ensure_ascii=False)}
"""
