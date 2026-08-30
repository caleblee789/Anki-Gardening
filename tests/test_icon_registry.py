from __future__ import annotations

import sys
import types
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

import ankigarden.ui.icons as icons
from ankigarden.ui.icons import (
    GARDEN_ICON_PATHS,
    ICON_STROKE_WIDTH,
    ICON_VIEWBOX,
    clear_garden_icon_pixmap_cache,
    garden_icon_pixmap,
    garden_icon_svg,
)


def test_release_icons_share_one_grid_and_stroke_contract() -> None:
    assert ICON_VIEWBOX == 24
    assert ICON_STROKE_WIDTH == 1.8
    assert {
        "close",
        "open-garden",
        "check",
        "chevron",
        "chevron-left",
        "chevron-right",
        "chevron-up",
        "chevron-down",
        "rename",
        "coin",
        "currency",
        "growth",
        "environment-discovery",
        "streak",
        "stage",
        "collection",
        "completed-collection",
        "completed-beds",
        "lock",
        "settings",
        "refresh",
        "overflow",
        "nursery",
        "plant",
        "warning",
        "info",
        "help",
    } <= set(GARDEN_ICON_PATHS)
    for name in GARDEN_ICON_PATHS:
        payload = garden_icon_svg(name, color="#123456")
        assert 'viewBox="0 0 24 24"' in payload
        assert 'stroke="#123456"' in payload
        assert 'stroke="currentColor"' not in payload
        assert 'stroke-width="1.8"' in payload
        root = ET.fromstring(payload)
        assert root.tag.endswith("svg")
        assert root.attrib["viewBox"] == "0 0 24 24"


def test_environment_discovery_icon_is_not_a_generic_image_frame() -> None:
    payload = GARDEN_ICON_PATHS["environment-discovery"]

    assert "<rect" not in payload
    assert "M17.5 3.5v5" in payload


def test_settings_icon_is_a_closed_cog_not_a_weather_sunburst() -> None:
    payload = GARDEN_ICON_PATHS["settings"]

    assert '<circle cx="12" cy="12" r="3.1"/>' in payload
    assert "M9.7 2.8h4.6" in payload
    assert "M12 2.5v3" not in payload




def test_qt_icon_renderer_falls_back_to_pyqt6_qtsvg(monkeypatch) -> None:
    rendered_payloads: list[bytes] = []

    class FakePixmap:
        def __init__(self, width: int, height: int) -> None:
            self.width = width
            self.height = height
            self.rendered = False
            self.painter_ended = False
            self.device_pixel_ratio = 1.0
            self.device_pixel_ratio_when_rendered: float | None = None

        def fill(self, _color: object) -> None:
            return None

        def setDevicePixelRatio(self, value: float) -> None:
            self.device_pixel_ratio = value

        def isNull(self) -> bool:
            return False

    class FakePainter:
        def __init__(self, pixmap: FakePixmap) -> None:
            self.pixmap = pixmap

        def end(self) -> None:
            self.pixmap.painter_ended = True

    class FakeIcon:
        def __init__(self, pixmap: FakePixmap | None = None) -> None:
            self.source = pixmap

    class FakeSvgRenderer:
        def __init__(self, payload: bytes) -> None:
            rendered_payloads.append(payload)

        def isValid(self) -> bool:
            return True

        def render(self, painter: FakePainter) -> None:
            painter.pixmap.device_pixel_ratio_when_rendered = (
                painter.pixmap.device_pixel_ratio
            )
            painter.pixmap.rendered = True

    aqt_module = types.ModuleType("aqt")
    qt_module = types.ModuleType("aqt.qt")
    qt_module.QByteArray = lambda payload: payload
    qt_module.QIcon = FakeIcon
    qt_module.QPainter = FakePainter
    qt_module.QPixmap = FakePixmap
    qt_module.QSvgRenderer = None
    qt_module.Qt = SimpleNamespace(
        GlobalColor=SimpleNamespace(transparent=object())
    )
    aqt_module.qt = qt_module

    pyqt6_module = types.ModuleType("PyQt6")
    qtsvg_module = types.ModuleType("PyQt6.QtSvg")
    qtsvg_module.QSvgRenderer = FakeSvgRenderer
    pyqt6_module.QtSvg = qtsvg_module

    monkeypatch.setitem(sys.modules, "aqt", aqt_module)
    monkeypatch.setitem(sys.modules, "aqt.qt", qt_module)
    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6_module)
    monkeypatch.setitem(sys.modules, "PyQt6.QtSvg", qtsvg_module)

    clear_garden_icon_pixmap_cache()
    icon = icons.garden_icon(
        "close",
        color="#abcdef",
        logical_size=20,
        device_pixel_ratio=2.0,
    )

    assert isinstance(icon, FakeIcon)
    assert icon.source is not None
    assert (icon.source.width, icon.source.height) == (40, 40)
    assert icon.source.device_pixel_ratio == 2.0
    assert icon.source.device_pixel_ratio_when_rendered == 1.0
    assert icon.source.rendered is True
    assert icon.source.painter_ended is True
    assert rendered_payloads
    assert b'stroke="#abcdef"' in rendered_payloads[0]
    assert GARDEN_ICON_PATHS["close"].encode("utf-8") in rendered_payloads[0]

    cached = garden_icon_pixmap(
        "close",
        20,
        color="#abcdef",
        device_pixel_ratio=2.0,
    )
    assert cached is icon.source
    assert len(rendered_payloads) == 1

    different_dpr = garden_icon_pixmap(
        "close",
        20,
        color="#abcdef",
        device_pixel_ratio=1.0,
    )
    assert different_dpr is not cached
    assert (different_dpr.width, different_dpr.height) == (20, 20)
    assert len(rendered_payloads) == 2
    clear_garden_icon_pixmap_cache()


def test_close_svg_has_two_centered_diagonals_at_dpr_1_and_2() -> None:
    payload = garden_icon_svg("close", color="#ffffff")
    paths = re.findall(
        r'<path d="M(\d+) (\d+)L(\d+) (\d+)"/>',
        payload,
    )
    assert paths == [
        ("6", "6", "18", "18"),
        ("18", "6", "6", "18"),
    ]

    for dpr in (1, 2):
        logical_size = 18
        physical_size = logical_size * dpr
        image = Image.new("L", (physical_size, physical_size), 0)
        draw = ImageDraw.Draw(image)
        scale = physical_size / 24
        for x1, y1, x2, y2 in paths:
            draw.line(
                tuple(
                    round(int(value) * scale)
                    for value in (x1, y1, x2, y2)
                ),
                fill=255,
                width=max(1, round(1.8 * scale)),
            )
        center = (physical_size - 1) / 2
        pixels = [
            (x, y)
            for y in range(physical_size)
            for x in range(physical_size)
            if image.getpixel((x, y))
        ]
        quadrant_counts = (
            sum(x < center and y < center for x, y in pixels),
            sum(x > center and y < center for x, y in pixels),
            sum(x < center and y > center for x, y in pixels),
            sum(x > center and y > center for x, y in pixels),
        )
        assert all(count >= 2 for count in quadrant_counts)
        bounds = image.getbbox()
        assert bounds is not None
        left, top, right, bottom = bounds
        assert abs(((left + right - 1) / 2) - center) <= 1
        assert abs(((top + bottom - 1) / 2) - center) <= 1
