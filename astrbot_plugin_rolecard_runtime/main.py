from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.components import File, Image, Reply
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.star.filter.permission import PermissionType

from .audit import AuditError, build_audit_prompt, parse_audit_response
from .event_engine import apply_audit
from .ejs_runtime import TemplateError
from .package_loader import PackageError
from .prompt_builder import build_runtime_prompt
from .mvu import UPDATE_OUTPUT, apply_variable_patch, extract_update
from .repository import PackageRepository
from .status_image import append_status_image, build_status_image_component
from .state_store import StateStore

PLUGIN_NAME = "astrbot_plugin_rolecard_runtime"
PLUGIN_VERSION = "0.2.0"


@register(
    "RoleCardRuntime",
    "rolecard_runtime contributors",
    "为 AstrBot 提供可导入的分阶段角色卡、世界书和事件池运行时。",
    PLUGIN_VERSION,
    "https://github.com/Amia0427/rolecard_runtime",
)
class RoleCardRuntimePlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.status_image_enabled = bool(self.config.get("status_image_enabled", True))
        self.status_font_path = str(self.config.get("status_font_path", "")).strip() or None
        self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        packages_dir = Path(self.config.get("packages_dir") or (self.data_dir / "packages"))
        self.repository = PackageRepository(packages_dir)
        self.store = StateStore(self.data_dir / "runtime.sqlite3")
        self.pending: dict[int, dict[str, Any]] = {}
        self._register_web_api()

    async def terminate(self) -> None:
        self.store.close()

    def _register_web_api(self) -> None:
        if not hasattr(self.context, "register_web_api"):
            return
        from .page_api import RoleCardPageApi

        self.page_api = RoleCardPageApi(self)
        self.page_api.register_routes()

    def _session_identity(self, event: AstrMessageEvent) -> tuple[str, str, bool]:
        return event.unified_msg_origin, event.get_sender_id(), event.is_private_chat()

    def _bound_package(self, event: AstrMessageEvent):
        package_id = self.store.binding(event.unified_msg_origin)
        return self.repository.get(package_id) if package_id else None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=50000)
    async def prepare_mvu_generation(self, event: AstrMessageEvent) -> None:
        package = self._bound_package(event) if self.enabled else None
        if package and package.update_mode == "mvu":
            event.set_extra("enable_streaming", False)

    @filter.on_llm_request(priority=50000)
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        if not self.enabled:
            return
        package = self._bound_package(event)
        if not package:
            return
        session_id, member_id, private_chat = self._session_identity(event)
        event.set_extra("rolecard_status_image", None)
        state = self.store.state(session_id, member_id, package.package_id, package.initial_state)
        revision = self.store.revision(session_id, member_id, package.package_id)
        nsfw_enabled = private_chat and self.store.nsfw_enabled(session_id, member_id)
        try:
            prompt, candidates = await build_runtime_prompt(
                package,
                state,
                event.message_str,
                event.get_sender_name(),
                nsfw_enabled=nsfw_enabled,
                private_chat=private_chat,
                node_executable=str(self.config.get("node_executable") or "node"),
            )
        except (TemplateError, TimeoutError) as exc:
            logger.warning("角色卡 EJS 渲染失败：%s", exc)
            event.set_result(event.plain_result(f"角色卡模板加载失败：{exc}"))
            event.stop_event()
            return
        req.system_prompt = f"{req.system_prompt}\n\n{prompt}".strip()
        self.pending[id(event)] = {
            "package_id": package.package_id,
            "session_id": session_id,
            "member_id": member_id,
            "private_chat": private_chat,
            "nsfw_enabled": nsfw_enabled,
            "user_text": event.message_str,
            "state": state,
            "revision": revision,
            "candidates": candidates,
        }

    @filter.on_llm_response(priority=50000)
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse) -> None:
        if not self.enabled:
            return
        pending = self.pending.pop(id(event), None)
        if pending is None:
            return
        package = self.repository.get(pending["package_id"])
        provider_id = str(self.config.get("audit_provider_id", "")).strip()
        if package is None or (package.update_mode == "audit" and not provider_id):
            self.store.audit(pending["session_id"], pending["member_id"], pending["package_id"], "unavailable", None, False, "未配置专用审计模型或卡包已卸载")
            return

        active = pending["state"].get("active_event")
        candidates = pending["candidates"]
        if active:
            candidates = [item for item in package.events + package.adult_events if item["id"] == active]
        audit_prompt = build_audit_prompt(
            package.audit_prompt,
            pending["state"],
            pending["user_text"],
            resp.completion_text or "",
            candidates,
            package.writable_paths,
            package.state_schema,
        )
        try:
            clean_text, patches, event_update = extract_update(resp.completion_text or "")
            resp.completion_text = clean_text
            if package.update_mode == "mvu":
                if event_update is None:
                    raise AuditError("MVU 回复缺少 EventUpdate")
                audit = parse_audit_response(event_update)
            else:
                result = await asyncio.wait_for(
                    self.context.llm_generate(
                        chat_provider_id=provider_id,
                        prompt=audit_prompt,
                        system_prompt="你是角色卡状态审计器，只输出符合要求的 JSON。",
                        stream=False,
                    ),
                    timeout=max(1, int(self.config.get("audit_timeout_seconds", 60))),
                )
                audit = parse_audit_response(result.completion_text or "")
                patches = audit.patches
            new_state, changed_event = apply_audit(
                package,
                pending["state"],
                audit,
                nsfw_enabled=pending["nsfw_enabled"],
                private_chat=pending["private_chat"],
                candidate_ids=[candidate["id"] for candidate in pending["candidates"]],
            )
            if new_state.get("turn_count", 0) == pending["state"].get("turn_count", 0):
                raise AuditError("事件动作与当前候选或活动事件不匹配")
            new_state = apply_variable_patch(new_state, patches, package.writable_paths, package.state_schema)
        except Exception as exc:
            resp.completion_text = UPDATE_OUTPUT.sub("", resp.completion_text or "").strip()
            logger.warning("角色卡状态审计未完成：%s", exc)
            self.store.audit(pending["session_id"], pending["member_id"], pending["package_id"], "error", active, False, str(exc))
            return

        if self.store.binding(pending["session_id"]) != pending["package_id"]:
            return
        current_nsfw = pending["private_chat"] and self.store.nsfw_enabled(pending["session_id"], pending["member_id"])
        if current_nsfw != pending["nsfw_enabled"]:
            self.store.audit(pending["session_id"], pending["member_id"], pending["package_id"], "stale", active, False, "本轮成人事件许可已变化")
            return
        if not self.store.save_turn(pending["session_id"], pending["member_id"], pending["package_id"], pending["state"], new_state, package.initial_state, expected_revision=pending["revision"]):
            self.store.audit(pending["session_id"], pending["member_id"], pending["package_id"], "stale", active, False, "当前状态已变化，未覆盖较新的轮次")
            return
        self.store.audit(pending["session_id"], pending["member_id"], pending["package_id"], audit.action, changed_event, True)
        if self.status_image_enabled:
            event.set_extra(
                "rolecard_status_image",
                {"package": package, "state": new_state},
            )

    @filter.on_decorating_result(priority=50000)
    async def append_status_image(self, event: AstrMessageEvent) -> None:
        if not self.enabled or not self.status_image_enabled:
            return
        result = event.get_result()
        pending = event.get_extra("rolecard_status_image")
        if result is None or not result.chain or pending is None:
            return
        if result.result_content_type not in {
            ResultContentType.LLM_RESULT,
            ResultContentType.STREAMING_FINISH,
        }:
            return
        event.set_extra("rolecard_status_image", None)
        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            component = build_status_image_component(
                pending["package"],
                pending["state"],
                enabled=True,
                font_path=self.status_font_path,
                image_component_factory=Image.fromBytes,
            )
            if component is not None:
                try:
                    await event.send(MessageChain(chain=[component]))
                except Exception:
                    logger.warning("角色卡状态图片发送失败", exc_info=True)
            return
        append_status_image(
            result,
            pending["package"],
            pending["state"],
            enabled=True,
            font_path=self.status_font_path,
            image_component_factory=Image.fromBytes,
        )

    @filter.command("角色卡列表")
    async def list_cards(self, event: AstrMessageEvent):
        cards = self.repository.list()
        if not cards:
            text = "当前没有已安装的角色卡包。"
            if self.repository.diagnostics:
                text += "\n\n未启用卡包：\n" + "\n".join(
                    f"{item['path']}：{item['reason']}" for item in self.repository.diagnostics
                )
            yield event.plain_result(text)
            return
        rows = [f"{item.package_id} | {item.display_name} | v{item.version} | 阶段 {len(item.stages)} / 事件 {len(item.events)} / 成人事件 {len(item.adult_events)}" for item in cards]
        if self.repository.diagnostics:
            rows.append("\n未启用卡包：")
            rows.extend(f"{item['path']}：{item['reason']}" for item in self.repository.diagnostics)
        yield event.plain_result("\n".join(rows))

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("角色卡导入")
    async def import_card(self, event: AstrMessageEvent, path: str | None = None):
        try:
            if path:
                source = Path(path).expanduser()
                if source.is_dir():
                    package = self.repository.import_directory(source)
                elif source.is_file() and source.suffix.lower() in {".zip", ".json"}:
                    package = self.repository.import_file(source.read_bytes(), str(source))
                else:
                    yield event.plain_result("请输入 ZIP/JSON 文件路径或已解压卡包目录。")
                    return
            else:
                file_comp = self._replied_file(event)
                if not file_comp or not file_comp.url:
                    yield event.plain_result("请引用卡包 ZIP/JSON 文件，或提供 AstrBot 本机上的 ZIP/目录路径。")
                    return
                async with aiohttp.ClientSession() as client:
                    async with client.get(file_comp.url) as response:
                        response.raise_for_status()
                        data = await response.content.read(20 * 1024 * 1024 + 1)
                package = self.repository.import_file(data, str(file_comp.name or "upload.zip"))
        except (PackageError, ValueError, OSError, aiohttp.ClientError) as exc:
            yield event.plain_result(f"卡包导入失败：{exc}")
            return
        yield event.plain_result(f"已导入 {package.display_name}（{package.package_id}），阶段 {len(package.stages)} 个，普通事件 {len(package.events)} 个，成人事件 {len(package.adult_events)} 个。")

    @staticmethod
    def _replied_file(event: AstrMessageEvent) -> File | None:
        chain = event.get_messages()
        reply = next((item for item in chain if isinstance(item, Reply)), None)
        if not reply:
            return next((item for item in chain if isinstance(item, File)), None)
        reply_chain = getattr(reply, "chain", []) or []
        return next((item for item in reply_chain if isinstance(item, File)), None)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("角色卡删除")
    async def delete_card(self, event: AstrMessageEvent, package_id: str):
        if self.store.binding(event.unified_msg_origin) == package_id:
            yield event.plain_result("当前会话正在使用该卡，请先执行“角色卡停止”。")
            return
        if not self.repository.delete(package_id):
            yield event.plain_result(f"没有找到卡包：{package_id}")
            return
        yield event.plain_result(f"已删除卡包：{package_id}")

    @filter.command("角色卡使用")
    async def use_card(self, event: AstrMessageEvent, package_id: str):
        package = self.repository.get(package_id)
        if not package:
            yield event.plain_result(f"没有找到卡包：{package_id}")
            return
        self.store.bind(event.unified_msg_origin, package_id)
        greeting = package.greeting.replace("{{user}}", event.get_sender_name() or "用户")
        yield event.plain_result(
            f"当前会话已启用 {package.display_name}。\n\n{greeting}".strip()
        )

    @filter.command("角色卡停止")
    async def stop_card(self, event: AstrMessageEvent):
        self.store.bind(event.unified_msg_origin, None)
        yield event.plain_result("当前会话已停止角色卡运行。")

    @filter.command("角色卡状态")
    async def card_status(self, event: AstrMessageEvent):
        package = self._bound_package(event)
        if not package:
            yield event.plain_result("当前会话没有启用角色卡。")
            return
        session_id, member_id, _ = self._session_identity(event)
        state = self.store.state(session_id, member_id, package.package_id, package.initial_state)
        yield event.plain_result(f"{package.display_name}\n阶段：{state.get('relation_stage')}\n信任：{state.get('trust')} | 依赖：{state.get('dependency')} | 女性化接受度：{state.get('feminine_acceptance')} | 情欲：{state.get('lust')}\n进行中事件：{state.get('active_event') or '无'}\n已完成事件：{len(state.get('completed_events', []))}")

    @filter.command("角色卡重置")
    async def reset_card(self, event: AstrMessageEvent):
        package = self._bound_package(event)
        if not package:
            yield event.plain_result("当前会话没有启用角色卡。")
            return
        session_id, member_id, _ = self._session_identity(event)
        self.store.reset_state(session_id, member_id, package.package_id)
        yield event.plain_result(f"{package.display_name} 的当前成员状态已重置。")

    @filter.command("角色卡解锁成人")
    async def enable_nsfw(self, event: AstrMessageEvent):
        if not event.is_private_chat():
            yield event.plain_result("成人事件仅能在私聊中启用。")
            return
        session_id, member_id, _ = self._session_identity(event)
        self.store.set_nsfw(session_id, member_id, True)
        yield event.plain_result("本私聊已允许成人事件进入候选。")

    @filter.command("角色卡关闭成人")
    async def disable_nsfw(self, event: AstrMessageEvent):
        session_id, member_id, _ = self._session_identity(event)
        self.store.set_nsfw(session_id, member_id, False)
        package = self._bound_package(event)
        if package:
            state = self.store.state(session_id, member_id, package.package_id, package.initial_state)
            if any(item["id"] == state.get("active_event") for item in package.adult_events):
                state["active_event"] = None
                state["event_step"] = 0
                self.store.save_state(session_id, member_id, package.package_id, state)
        yield event.plain_result("本会话的成人事件已关闭。")

