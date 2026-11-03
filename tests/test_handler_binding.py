from __future__ import annotations

from types import SimpleNamespace

from astrbot_plugin_rolecard_runtime.handler_binding import bind_plugin_handlers


class HandlerRegistry(list):
    def __init__(self, handlers):
        super().__init__(handlers)
        self.star_handlers_map = {
            handler.handler_full_name: handler for handler in handlers
        }


def test_plugin_handlers_bind_to_astrbot_entry_module() -> None:
    original_module = "data.plugins.rolecard.astrbot_plugin_rolecard_runtime.main"
    entry_module = "data.plugins.rolecard.main"

    class RoleCardRuntimePlugin:
        pass

    RoleCardRuntimePlugin.__module__ = original_module
    metadata = SimpleNamespace(module_path=original_module, star_cls_type=None)
    plugin_map = {original_module: metadata}
    handlers = [
        SimpleNamespace(
            handler_name=name,
            handler_module_path=original_module,
            handler_full_name=f"{original_module}_{name}",
        )
        for name in (
            "use_card",
            "on_llm_request",
            "on_llm_response",
            "append_status_image",
        )
    ]
    registry = HandlerRegistry(handlers)

    bind_plugin_handlers(RoleCardRuntimePlugin, entry_module, plugin_map, registry)

    assert RoleCardRuntimePlugin.__module__ == entry_module
    assert plugin_map == {entry_module: metadata}
    assert metadata.module_path == entry_module
    assert metadata.star_cls_type is RoleCardRuntimePlugin
    assert all(handler.handler_module_path == entry_module for handler in handlers)
    assert {
        handler.handler_name
        for handler in registry.star_handlers_map.values()
    } == {
        "use_card",
        "on_llm_request",
        "on_llm_response",
        "append_status_image",
    }
    assert all(
        handler.handler_full_name.startswith(f"{entry_module}_")
        for handler in handlers
    )
