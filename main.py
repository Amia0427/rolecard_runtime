from .astrbot_plugin_rolecard_runtime.main import RoleCardRuntimePlugin
from .astrbot_plugin_rolecard_runtime.handler_binding import bind_plugin_handlers

from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry

bind_plugin_handlers(
    RoleCardRuntimePlugin,
    __name__,
    star_map,
    star_handlers_registry,
)

__all__ = ["RoleCardRuntimePlugin"]
