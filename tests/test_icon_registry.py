from __future__ import annotations

import sys
import types
import re
from pathlib import Path
from types import SimpleNamespace

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
        "check",
        "chevron",
        "rename",
        "coin",
        "growth",
        "streak",
        "stage",
        "collection",
        "lock",
        "settings",
        "nursery",
        "plant",
        "warning",
        "info",
        "help",
    } <= set(GARDEN_ICON_PATHS)
    for name in GARDEN_ICON_PATHS:
        payload = garden_icon_svg(name, color="#123456")
        assert 'viewBox="0 0 24 24"' in payload
        assert 'style="color:#123456"' in payload
        assert 'stroke="currentColor"' in payload
        assert 'stroke-width="1.8"' in payload




def test_qt_icon_renderer_falls_back_to_pyqt6_qtsvg(monkeypatch) -> None:
    rendered_payloads: list[bytes] = []

    class FakePixmap:
        def __init__(self, width: int, height: int) -> None:
            self.width = width
            self.height = height
            self.rendered = False
            self.painter_ended = False
            self.device_pixel_ratio = 1.0

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
    assert icon.source.rendered is True
    assert icon.source.painter_ended is True
    assert rendered_payloads
    assert b'style="color:#abcdef"' in rendered_payloads[0]
    assert b'stroke="currentColor"' in rendered_payloads[0]
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
