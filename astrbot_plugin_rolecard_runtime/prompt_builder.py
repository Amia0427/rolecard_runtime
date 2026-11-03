from __future__ import annotations

import json
import re
from typing import Any

from .event_engine import eligible_events
from .generation_self_check import build_generation_self_check
from .ejs_runtime import TemplateError, render_templates
from .mvu import update_instructions
from .package_loader import RoleCardPackage
from .predicate import matches


def _replace_user(text: str, user_name: str) -> str:
    return text.replace("{{user}}", user_name or "用户").replace("{{char}}", "角色")


def _worldbook_matches(entry: dict[str, Any], state: dict[str, Any], user_text: str) -> bool:
    mode = entry.get("mode")
    if mode == "ejs":
        return False
    if mode == "resident":
        return True
    if mode == "keyword":
        keywords = entry.get("keywords") or [entry.get("name", "")]
        return any(str(keyword).lower() in user_text.lower() for keyword in keywords if keyword)
    if isinstance(entry.get("condition"), (dict, list)):
        return matches(state, entry["condition"])
    condition = str(entry.get("condition") or "")
    if not condition:
        return False
    condition = condition.replace("{stage}", str(state.get("relation_stage", "")))
    condition = condition.replace("{min}", "0").replace("{max}", "100")
    stage_match = re.fullmatch(r"\s*relation_stage\s*==\s*['\"](.*?)['\"]\s*", condition)
    if not stage_match:
        stage_match = re.fullmatch(r"\s*state\.relation_stage\s*===\s*['\"](.*?)['\"]\s*", condition)
    if stage_match:
        return state.get("relation_stage") == stage_match.group(1)
    range_match = re.fullmatch(
        r"\s*feminine_acceptance\s*>=\s*(\d+)\s*&&\s*feminine_acceptance\s*<=\s*(\d+)\s*",
        condition,
    )
    return bool(
        range_match
        and int(range_match.group(1)) <= state.get("feminine_acceptance", 0) <= int(range_match.group(2))
    )


def _conditional_content(entry: dict[str, Any], state: dict[str, Any]) -> str:
    content = entry["content"]
    if entry.get("mode") != "conditional":
        return content
    blocks = re.split(r"(?m)^###\s+【([^】]+)】.*$", content)
    if len(blocks) < 3:
        return content
    target = str(state.get("relation_stage", ""))
    for index in range(1, len(blocks), 2):
        if blocks[index].startswith(target) or target in blocks[index]:
            return blocks[index + 1].strip()
        range_match = re.search(
            r"(\d+)\s*[\-\u2010\u2011\u2012\u2013\u2014]\s*(\d+)",
            blocks[index],
        )
        if range_match:
            acceptance = state.get("feminine_acceptance")
            if isinstance(acceptance, (int, float)) and int(range_match.group(1)) <= acceptance <= int(range_match.group(2)):
                return blocks[index + 1].strip()
    return ""


def build_prompt(
    package: RoleCardPackage,
    state: dict[str, Any],
    user_text: str,
    user_name: str,
    *,
    nsfw_enabled: bool,
    private_chat: bool,
    selected_candidates: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    stage = next((item for item in package.stages if item["id"] == state.get("relation_stage")), package.stages[0])
    worldbook = [entry for entry in package.worldbook if (package.runtime.get("keyword_matching", True) or entry.get("mode") != "keyword") and _worldbook_matches(entry, state, user_text)]
    candidates = selected_candidates if selected_candidates is not None else eligible_events(package, state, nsfw_enabled=nsfw_enabled, private_chat=private_chat)
    adult_ids = {event["id"] for event in package.adult_events}
    active = next(
        (
            event
            for event in package.events + package.adult_events
            if event["id"] == state.get("active_event")
            and (event["id"] not in adult_ids or (nsfw_enabled and private_chat))
        ),
        None,
    )

    sections = [
        "[角色卡运行时]\n" + _replace_user(package.core_prompt, user_name),
        "[当前阶段人设]\n" + _replace_user(stage["content"], user_name),
        build_generation_self_check(package.display_name),
    ]
    if worldbook:
        sections.append(
            "[当前世界书]\n"
            + "\n\n".join(
                _replace_user(_conditional_content(entry, state), user_name)
                for entry in worldbook
                if _conditional_content(entry, state)
            )
        )
    if active:
        sections.append("[当前进行中的事件]\n" + _replace_user(active["content"], user_name))
    else:
        event_index = "\n".join(f"- {event['id']}: {event['title']}" for event in candidates)
        if event_index:
            sections.append("[当前可触发事件索引]\n" + event_index)
        if package.runtime.get("engine") == "ejs" and candidates:
            sections.append("[本轮候选事件]\n" + "\n\n".join(_replace_user(event["content"], user_name) for event in candidates))
    sections.append("[运行时状态]\n" + json.dumps(state, ensure_ascii=False, indent=2))
    if state.get("active_event") is None:
        event_rule = "按本轮变量选出的候选自然呈现事件开端，允许日常情境自行发生；不得替用户做决定，不得跳过事件步骤或提前写成成功。" if package.runtime.get("engine") == "ejs" else "只有用户明确推动候选事件时才进入事件；不要自行跳过事件步骤或替用户做决定。"
        sections.append("[事件规则]\n" + event_rule)
    if package.update_mode == "mvu":
        sections.append(update_instructions(package.writable_paths, package.state_schema))
        event_rules = [active] if active else candidates
        sections.append("[事件结算条件]\n" + json.dumps([
            {key: event.get(key) for key in ("id", "success_condition", "failure_condition", "branches")}
            for event in event_rules
        ], ensure_ascii=False))
    return "\n\n".join(sections), candidates


async def build_runtime_prompt(
    package: RoleCardPackage,
    state: dict[str, Any],
    user_text: str,
    user_name: str,
    *,
    nsfw_enabled: bool,
    private_chat: bool,
    node_executable: str = "node",
) -> tuple[str, list[dict[str, Any]]]:
    options = {"nsfw_enabled": nsfw_enabled, "private_chat": private_chat}
    if package.runtime.get("engine") != "ejs":
        return build_prompt(package, state, user_text, user_name, **options)
    candidates = eligible_events(package, state, **options)
    events = package.events + (package.adult_events if nsfw_enabled and private_chat else [])
    active = next((event for event in events if event["id"] == state.get("active_event")), None)
    context = {"state": state, "events": events, "eligible_events": candidates, "active_event": active, "runtime": options}
    worldbook = {entry["name"]: entry["content"] for entry in package.worldbook}
    if package.event_pool and active is None:
        rendered = await render_templates([package.event_pool], context, worldbook, node_executable=node_executable)
        try:
            ids = json.loads(rendered[0])
        except json.JSONDecodeError as exc:
            raise TemplateError("事件池 EJS 必须输出 JSON 事件 ID 数组") from exc
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
            raise TemplateError("事件池 EJS 必须输出 JSON 事件 ID 数组")
        allowed = {event["id"]: event for event in candidates}
        candidates = [allowed[event_id] for event_id in dict.fromkeys(ids) if event_id in allowed]
    prompt, candidates = build_prompt(package, state, user_text, user_name, selected_candidates=candidates, **options)
    entries = [entry for entry in package.worldbook if entry["mode"] == "ejs" and matches(state, entry.get("condition"))]
    if entries:
        rendered = await render_templates([entry["content"] for entry in entries], context, worldbook, node_executable=node_executable)
        content = "\n\n".join(_replace_user(text.strip(), user_name) for text in rendered if text.strip())
        if content:
            prompt += "\n\n[动态世界书]\n" + content
    return prompt, candidates

