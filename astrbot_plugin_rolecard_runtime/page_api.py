from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api.web import error_response, json_response, request

PAGE_PREFIX = "/astrbot_plugin_rolecard_runtime"


class RoleCardPageApi:
    def __init__(self, plugin):
        self.plugin = plugin

    def register_routes(self) -> None:
        register = self.plugin.context.register_web_api
        routes = (
            (f"{PAGE_PREFIX}/page/cards", self.cards_page, ["GET"], "角色卡运行时管理页面"),
            (f"{PAGE_PREFIX}/cards", self.cards, ["GET"], "列出已安装角色卡"),
            (f"{PAGE_PREFIX}/cards/import", self.import_card, ["POST"], "上传角色卡 ZIP 或 JSON"),
            (f"{PAGE_PREFIX}/cards/<package_id>", self.delete_card, ["DELETE"], "删除角色卡"),
            (f"{PAGE_PREFIX}/cards/<package_id>/delete", self.delete_card, ["POST"], "删除角色卡"),
            (f"{PAGE_PREFIX}/state", self.state, ["GET"], "查询角色卡状态"),
            (f"{PAGE_PREFIX}/state/reset", self.reset_state, ["POST"], "重置角色卡状态"),
            (f"{PAGE_PREFIX}/state/nsfw", self.nsfw, ["POST"], "设置成人事件开关"),
            (f"{PAGE_PREFIX}/binding", self.binding, ["POST"], "设置会话角色卡绑定"),
            (f"{PAGE_PREFIX}/audits", self.audits, ["GET"], "查询角色卡审计记录"),
        )
        for route, handler, methods, description in routes:
            register(route, handler, methods, description)

    async def cards_page(self):
        page = Path(__file__).resolve().parents[1] / "pages" / "角色卡面板" / "index.html"
        return page.read_text(encoding="utf-8")

    async def cards(self):
        return json_response(
            {
                "cards": [self._card_payload(card) for card in self.plugin.repository.list()],
                "diagnostics": self.plugin.repository.diagnostics,
            }
        )

    async def import_card(self):
        if not self._is_dashboard_admin():
            return error_response("只有 AstrBot 管理员可以导入卡包", status_code=403)
        files = await request.files()
        upload = files.get("file")
        if upload is None:
            return error_response("缺少 file 上传字段", status_code=400)
        data = await upload.read(20 * 1024 * 1024 + 1)
        try:
            package = self.plugin.repository.import_file(data, upload.filename or "upload.zip")
        except (ValueError, OSError) as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"card": self._card_payload(package)})

    async def delete_card(self, package_id: str = ""):
        package_id = str(request.path_params.get("package_id", package_id) or "").strip()
        if not package_id:
            return error_response("package_id 不能为空", status_code=400)
        if not self._is_dashboard_admin():
            return error_response("只有 AstrBot 管理员可以删除卡包", status_code=403)
        if self.plugin.store.has_binding(package_id):
            return error_response("当前会话正在使用该卡，请先解除绑定", status_code=409)
        if not self.plugin.repository.delete(package_id):
            return error_response("卡包不存在", status_code=404)
        return json_response({"deleted": package_id})

    async def state(self):
        session_id = str(request.query.get("session_id", "")).strip() or None
        member_id = str(request.query.get("member_id", "")).strip() or None
        package_id = str(request.query.get("package_id", "")).strip() or None
        return json_response(
            {
                "states": self.plugin.store.state_rows(session_id, member_id, package_id),
                "bindings": self.plugin.store.binding_rows(session_id),
            }
        )

    async def reset_state(self):
        payload = await request.json({})
        session_id = str(payload.get("session_id", "")).strip()
        member_id = str(payload.get("member_id", "")).strip()
        package_id = str(payload.get("package_id", "")).strip()
        if not all((session_id, member_id, package_id)):
            return error_response("session_id、member_id、package_id 均不能为空", status_code=400)
        self.plugin.store.reset_state(session_id, member_id, package_id)
        return json_response({"reset": True})

    async def nsfw(self):
        payload = await request.json({})
        session_id = str(payload.get("session_id", "")).strip()
        member_id = str(payload.get("member_id", "")).strip()
        enabled = bool(payload.get("enabled", False))
        if not session_id or not member_id:
            return error_response("session_id 和 member_id 不能为空", status_code=400)
        if self._is_group_session(session_id):
            return error_response("群聊永久禁止成人事件", status_code=403)
        self.plugin.store.set_nsfw(session_id, member_id, enabled)
        if not enabled:
            package_id = self.plugin.store.binding(session_id)
            package = self.plugin.repository.get(package_id) if package_id else None
            if package:
                state = self.plugin.store.state(session_id, member_id, package.package_id, package.initial_state)
                if any(item["id"] == state.get("active_event") for item in package.adult_events):
                    state["active_event"] = None
                    state["event_step"] = 0
                    self.plugin.store.save_state(session_id, member_id, package.package_id, state)
        return json_response({"enabled": enabled})

    async def binding(self):
        payload = await request.json({})
        session_id = str(payload.get("session_id", "")).strip()
        package_id = str(payload.get("package_id", "")).strip() or None
        if not session_id:
            return error_response("session_id 不能为空", status_code=400)
        if package_id and not self.plugin.repository.get(package_id):
            return error_response("卡包不存在", status_code=404)
        self.plugin.store.bind(session_id, package_id)
        return json_response({"session_id": session_id, "package_id": package_id})

    async def audits(self):
        return json_response({"audits": self.plugin.store.recent_audits()})

    @staticmethod
    def _card_payload(card) -> dict[str, Any]:
        return {
            "package_id": card.package_id,
            "display_name": card.display_name,
            "version": card.version,
            "stages": len(card.stages),
            "events": len(card.events),
            "adult_events": len(card.adult_events),
            "source": card.source,
        }

    @staticmethod
    def _is_group_session(session_id: str) -> bool:
        return session_id.split(":", 2)[1:2] == ["GroupMessage"]

    def _is_dashboard_admin(self) -> bool:
        username = str(request.username or "").strip()
        if not username:
            return False
        config_getter = getattr(self.plugin.context, "get_config", None)
        if not callable(config_getter):
            return False
        config = config_getter()
        dashboard = config.get("dashboard", {}) if isinstance(config, dict) else {}
        expected = dashboard.get("username", "") if isinstance(dashboard, dict) else ""
        return bool(expected and username == str(expected).strip())

