from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class TemplateError(ValueError):
    pass


async def render_templates(
    templates: list[str],
    context: dict[str, Any],
    worldbook: dict[str, str],
    *,
    node_executable: str = "node",
    timeout: float = 5,
) -> list[str]:
    bridge = Path(__file__).with_name("ejs_bridge.cjs")
    try:
        process = await asyncio.create_subprocess_exec(
            node_executable, str(bridge),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise TemplateError("EJS 需要 Node.js；请安装或配置 node_executable") from exc
    payload = json.dumps({"templates": templates, "context": context, "worldbook": worldbook}, ensure_ascii=False).encode("utf-8")
    try:
        output, error = await asyncio.wait_for(process.communicate(payload), timeout)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise TemplateError(error.decode("utf-8", errors="replace").strip())
    return json.loads(output)
