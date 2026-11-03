from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def bind_plugin_handlers(
    plugin_class: type,
    module_path: str,
    plugin_map: MutableMapping[str, Any],
    handler_registry: Any,
) -> None:
    original_module = plugin_class.__module__
    if original_module == module_path:
        return

    metadata = plugin_map.pop(original_module, None)
    if metadata is not None:
        metadata.module_path = module_path
        metadata.star_cls_type = plugin_class
        plugin_map[module_path] = metadata
    plugin_class.__module__ = module_path

    for handler in handler_registry:
        if handler.handler_module_path != original_module:
            continue

        handler_registry.star_handlers_map.pop(handler.handler_full_name, None)
        handler.handler_module_path = module_path
        handler.handler_full_name = f"{module_path}_{handler.handler_name}"
        handler_registry.star_handlers_map[handler.handler_full_name] = handler
