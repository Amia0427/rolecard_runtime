from __future__ import annotations

import importlib.util
import io
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from PIL import ImageDraw, ImageFont

from .package_loader import RoleCardPackage

WIDTH = 920
HEIGHT = 440
LOGGER = logging.getLogger(__name__)
ASSETS_DIR = Path(__file__).with_name("assets")
BUNDLED_FONT = ASSETS_DIR / "LXGWWenKaiLite-Regular.ttf"
BACKGROUND = "#eef2ef"
PANEL = "#ffffff"
TEXT = "#26352f"
MUTED = "#74827b"
ACCENT = "#287963"
TRACK = "#e5ebe7"


@dataclass(frozen=True)
class StatusMetric:
    label: str
    value: str
    progress: float | None


@dataclass(frozen=True)
class StatusBarView:
    display_name: str
    stage: str
    metrics: tuple[StatusMetric, ...]
    active_event: str
    event_step: str
    completed_events: int


def _metric(label: str, value: Any, *, unavailable: str = "—") -> StatusMetric:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return StatusMetric(label, unavailable, None)
    if not math.isfinite(value):
        return StatusMetric(label, unavailable, None)
    display = str(int(value)) if isinstance(value, int) or value.is_integer() else f"{value:g}"
    return StatusMetric(label, display, max(0, min(100, float(value))))


def build_status_view(package: RoleCardPackage, state: dict[str, Any]) -> StatusBarView:
    stages = {stage["id"]: stage["name"] for stage in package.stages}
    event_titles = {
        event["id"]: event["title"]
        for event in package.events + package.adult_events
    }
    active_event = state.get("active_event")
    completed = state.get("completed_events")
    event_step = state.get("event_step", 0)

    return StatusBarView(
        display_name=package.display_name,
        stage=stages.get(state.get("relation_stage")) or str(state.get("relation_stage") or "未知阶段"),
        metrics=(
            _metric("信任", state.get("trust")),
            _metric("依赖", state.get("dependency")),
            _metric("女性化接受度", state.get("feminine_acceptance")),
            _metric("情欲", state.get("lust"), unavailable="未启用"),
        ),
        active_event=event_titles.get(active_event, str(active_event)) if active_event else "无",
        event_step=f"第 {event_step} 步" if active_event else "待机",
        completed_events=len(completed) if isinstance(completed, list) else 0,
    )


def _font_candidates(configured_path: str | Path | None) -> list[Path]:
    candidates = [Path(configured_path).expanduser()] if configured_path else []
    candidates.append(BUNDLED_FONT)
    pillowmd = importlib.util.find_spec("pillowmd")
    if pillowmd and pillowmd.origin:
        candidates.append(Path(pillowmd.origin).parent / "data" / "fonts" / "yahei.ttf")
    candidates.extend(
        Path(path)
        for path in (
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        )
    )
    return candidates


def _font(size: int, configured_path: str | Path | None, font_module: Any) -> Any:
    for path in _font_candidates(configured_path):
        if path.is_file():
            try:
                return font_module.truetype(str(path), size)
            except OSError:
                continue
    return font_module.load_default()


def _draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    fill: str,
) -> None:
    suffix = "..."
    visible = text
    while visible and draw.textlength(visible, font=font) > max_width:
        visible = visible[:-1]
    if visible != text:
        while visible and draw.textlength(visible + suffix, font=font) > max_width:
            visible = visible[:-1]
        visible += suffix
    draw.text(position, visible, font=font, fill=fill)


def render_status_image(
    package: RoleCardPackage,
    state: dict[str, Any],
    font_path: str | Path | None = None,
) -> bytes:
    view = build_status_view(package, state)
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), radius=18, fill=PANEL)

    title_font = _font(28, font_path, ImageFont)
    label_font = _font(16, font_path, ImageFont)
    value_font = _font(25, font_path, ImageFont)
    small_font = _font(17, font_path, ImageFont)

    draw.text((48, 42), "关系状态", font=label_font, fill=MUTED)
    _draw_fitted_text(draw, view.display_name, (48, 70), title_font, 500, TEXT)

    stage_width = min(250, int(draw.textlength(view.stage, font=small_font)) + 38)
    stage_left = WIDTH - 48 - stage_width
    draw.rounded_rectangle((stage_left, 52, WIDTH - 48, 92), radius=20, fill="#e5f1eb")
    _draw_fitted_text(
        draw,
        view.stage,
        (stage_left + 19, 62),
        small_font,
        stage_width - 38,
        ACCENT,
    )

    card_left = 48
    card_top = 132
    card_width = 190
    card_height = 142
    gap = 14
    for index, metric in enumerate(view.metrics):
        left = card_left + index * (card_width + gap)
        draw.rounded_rectangle(
            (left, card_top, left + card_width, card_top + card_height),
            radius=12,
            fill="#f7f9f7",
            outline="#e5ebe7",
            width=1,
        )
        draw.text((left + 16, card_top + 17), metric.label, font=label_font, fill=MUTED)
        draw.text((left + 16, card_top + 52), metric.value, font=value_font, fill=TEXT)
        if metric.progress is not None:
            bar_left = left + 16
            bar_top = card_top + 105
            bar_width = card_width - 32
            draw.rounded_rectangle(
                (bar_left, bar_top, bar_left + bar_width, bar_top + 8),
                radius=4,
                fill=TRACK,
            )
            fill_width = int(bar_width * metric.progress / 100)
            if fill_width:
                draw.rounded_rectangle(
                    (bar_left, bar_top, bar_left + fill_width, bar_top + 8),
                    radius=4,
                    fill=ACCENT,
                )

    footer_top = 310
    draw.line((48, footer_top, WIDTH - 48, footer_top), fill="#e5ebe7", width=1)
    draw.text((48, footer_top + 20), "进行中事件", font=label_font, fill=MUTED)
    _draw_fitted_text(draw, view.active_event, (48, footer_top + 49), small_font, 590, TEXT)
    draw.text((48, footer_top + 79), view.event_step, font=label_font, fill=MUTED)
    draw.text(
        (WIDTH - 245, footer_top + 37),
        f"已完成事件  {view.completed_events}",
        font=small_font,
        fill=TEXT,
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def append_status_image(
    message_chain: Any,
    package: RoleCardPackage,
    state: dict[str, Any],
    *,
    enabled: bool,
    font_path: str | Path | None,
    image_component_factory: Callable[[bytes], Any],
) -> bool:
    if not enabled:
        return False
    try:
        component = build_status_image_component(
            package,
            state,
            enabled=True,
            font_path=font_path,
            image_component_factory=image_component_factory,
        )
        if component is None:
            return False
        message_chain.chain.append(component)
    except Exception:
        LOGGER.warning("角色卡状态图片生成失败", exc_info=True)
        return False
    return True


def build_status_image_component(
    package: RoleCardPackage,
    state: dict[str, Any],
    *,
    enabled: bool,
    font_path: str | Path | None,
    image_component_factory: Callable[[bytes], Any],
) -> Any | None:
    if not enabled:
        return None
    try:
        return image_component_factory(render_status_image(package, state, font_path))
    except Exception:
        LOGGER.warning("角色卡状态图片生成失败", exc_info=True)
        return None
