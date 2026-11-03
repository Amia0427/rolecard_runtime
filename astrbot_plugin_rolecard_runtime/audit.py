from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_ACTIONS = {"none", "trigger", "step", "success", "fail", "branch"}
ALLOWED_DELTAS = {"trust", "dependency", "feminine_acceptance", "lust"}


@dataclass(frozen=True)
class AuditResult:
    action: str
    event_id: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    deltas: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    branch_id: str | None = None
    patches: list[dict[str, Any]] = field(default_factory=list)


class AuditError(ValueError):
    pass


def parse_audit_response(text: str) -> AuditResult:
    clean = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", clean, re.S | re.I)
    if fenced:
        clean = fenced.group(1).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AuditError("审计模型没有返回有效 JSON") from exc
    if not isinstance(data, dict) or data.get("action") not in ALLOWED_ACTIONS:
        raise AuditError("审计结果 action 无效")
    event_id = data.get("event_id")
    if event_id is not None and not isinstance(event_id, str):
        raise AuditError("审计结果 event_id 无效")
    raw_deltas = data.get("deltas", {})
    if not isinstance(raw_deltas, dict):
        raise AuditError("审计结果 deltas 无效")
    deltas = {}
    for key, value in raw_deltas.items():
        if key not in ALLOWED_DELTAS:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            deltas[key] = float(value)
    signals = data.get("signals", {})
    if not isinstance(signals, dict):
        signals = {}
    evidence = data.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    patches = data.get("patches", [])
    branch_id = data.get("branch_id")
    if not isinstance(patches, list) or (branch_id is not None and not isinstance(branch_id, str)):
        raise AuditError("审计结果 patches 或 branch_id 无效")
    return AuditResult(data["action"], event_id, signals, deltas, [str(item) for item in evidence[:8]], branch_id, patches)


def build_audit_prompt(
    package_prompt: str,
    state: dict[str, Any],
    user_text: str,
    assistant_text: str,
    candidates: list[dict[str, Any]],
    writable_paths: list[str] | None = None,
    state_schema: dict[str, Any] | None = None,
) -> str:
    candidate_text = json.dumps([
        {key: event.get(key) for key in ("id", "title", "content", "success_condition", "failure_condition", "branches")}
        for event in candidates
    ], ensure_ascii=False, indent=2)
    return f"""{package_prompt}

你只能输出一个 JSON 对象，不能输出解释文字。输出格式：
{{"action":"none|trigger|step|success|fail|branch","event_id":null,"branch_id":null,"signals":{{}},"deltas":{{"trust":0,"dependency":0,"feminine_acceptance":0,"lust":0}},"evidence":[],"patches":[]}}

patches 使用 JSONPatch 数组，只能更新 {json.dumps(writable_paths or [], ensure_ascii=False)}；没有明确事实就保留原值。
变量 schema：{json.dumps(state_schema or {}, ensure_ascii=False)}

当前状态：
{json.dumps(state, ensure_ascii=False, indent=2)}

当前可触发事件：
{candidate_text}

用户本轮输入：
{user_text}

角色本轮回复：
{assistant_text}

规则：
1. 只依据用户本轮真实行为和本轮正文中的客观事实判断，不能依据角色内心戏自充。
2. 当前 active_event 不为空时，只能返回该事件的 none、step、success、fail 或 branch；不能触发其他事件。
3. 当前 active_event 为空时，只有本轮明确启动了候选事件，才返回 trigger；否则返回 none。
4. 普通 none 轮次的数值变化必须克制，审计结果会由 Python 再次限制范围。
5. event_id 必须是当前 active_event 或候选列表中的 ID，没有事件时必须为 null。
6. success/fail/branch 必须给出对应 condition 所需 signals 和原文 evidence；不能把条件文字当成已经发生的事实。
"""

