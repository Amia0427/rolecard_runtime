from __future__ import annotations

import io
import json
from types import SimpleNamespace
from pathlib import Path

from PIL import Image

import astrbot_plugin_rolecard_runtime.status_image as status_image
from astrbot_plugin_rolecard_runtime.status_image import (
    append_status_image,
    build_status_image_component,
    build_status_view,
    render_status_image,
)
from test_package_loader import make_zip, standard_files
from astrbot_plugin_rolecard_runtime.package_loader import load_zip


def package():
    return load_zip(make_zip(standard_files()))


def test_status_view_maps_card_fields_and_keeps_lust_unavailable() -> None:
    card = package()
    state = dict(card.initial_state)
    state.update(
        {
            "relation_stage": "恋爱",
            "trust": 36,
            "dependency": 48,
            "feminine_acceptance": 63,
            "active_event": "icebreaking",
            "event_step": 2,
            "completed_events": ["old-event", "another-event"],
        }
    )
    state["lust"] = None

    view = build_status_view(card, state)

    assert view.display_name == "示例卡"
    assert view.stage == "恋爱"
    assert [(metric.label, metric.value) for metric in view.metrics] == [
        ("信任", "36"),
        ("依赖", "48"),
        ("女性化接受度", "63"),
        ("情欲", "未启用"),
    ]
    assert view.active_event == card.events[0]["title"]
    assert view.event_step == "第 2 步"
    assert view.completed_events == 2


def test_long_stage_name_falls_back_to_the_card_state() -> None:
    card = package()
    card.stages[0]["name"] = ""
    state = dict(card.initial_state)

    assert build_status_view(card, state).stage == "初识"


def test_render_status_image_creates_png_without_changing_state() -> None:
    card = package()
    state = dict(card.initial_state)
    state.update({"trust": 140, "active_event": "icebreaking", "event_step": 1})
    original = dict(state)

    view = build_status_view(card, state)
    output = render_status_image(card, state, r"C:\Windows\Fonts\msyh.ttc")
    rendered = Image.open(io.BytesIO(output))

    assert rendered.format == "PNG"
    assert rendered.size == (920, 440)
    assert view.metrics[0].value == "140"
    assert view.metrics[0].progress == 100
    assert state == original


def test_append_status_image_preserves_existing_reply_components() -> None:
    card = package()
    text = object()
    existing_image = object()
    chain = SimpleNamespace(chain=[text, existing_image])
    component = object()

    appended = append_status_image(
        chain,
        card,
        card.initial_state,
        enabled=True,
        font_path=None,
        image_component_factory=lambda _: component,
    )

    assert appended
    assert chain.chain == [text, existing_image, component]


def test_disabled_or_failed_image_does_not_change_reply_chain(monkeypatch) -> None:
    card = package()
    text = object()
    chain = SimpleNamespace(chain=[text])
    factory_calls = []

    assert not append_status_image(
        chain,
        card,
        card.initial_state,
        enabled=False,
        font_path=None,
        image_component_factory=lambda _: factory_calls.append("image"),
    )
    assert factory_calls == []
    assert chain.chain == [text]

    monkeypatch.setattr(
        status_image,
        "render_status_image",
        lambda *_: (_ for _ in ()).throw(RuntimeError("render failed")),
    )
    assert not append_status_image(
        chain,
        card,
        card.initial_state,
        enabled=True,
        font_path=None,
        image_component_factory=lambda _: None,
    )
    assert chain.chain == [text]


def test_image_component_failure_leaves_original_reply_unchanged() -> None:
    card = package()
    text = object()
    chain = SimpleNamespace(chain=[text])

    assert not append_status_image(
        chain,
        card,
        card.initial_state,
        enabled=True,
        font_path=r"C:\Windows\Fonts\msyh.ttc",
        image_component_factory=lambda _: (_ for _ in ()).throw(ValueError("bad image")),
    )
    assert chain.chain == [text]


def test_build_status_image_component_respects_disabled_setting() -> None:
    card = package()
    factory_calls = []

    component = build_status_image_component(
        card,
        card.initial_state,
        enabled=False,
        font_path=None,
        image_component_factory=lambda image: factory_calls.append(image),
    )

    assert component is None
    assert factory_calls == []


def test_status_image_settings_default_to_enabled_and_system_font() -> None:
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert config["status_image_enabled"]["default"] is True
    assert config["status_font_path"]["default"] == ""
