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
    garden_icon_svg,
)


def test_release_icons_share_one_grid_and_stroke_contract() -> None:
    assert ICON_VIEWBOX == 24
    assert ICON_STROKE_WIDTH == 1.8
    assert {
        "close",
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


def test_literal_icon_consumers_are_registered() -> None:
    root = Path(__file__).resolve().parents[1] / "ankigarden"
    requested: set[str] = set()
    consumer_pattern = re.compile(
        r'(?:GardenIconButton|garden_icon|garden_icon_svg)\(\s*"([^"]+)"'
    )
    for path in root.rglob("*.py"):
        requested.update(consumer_pattern.findall(path.read_text("utf-8")))

    assert "help" in requested
    assert requested <= set(GARDEN_ICON_PATHS)


def test_qt_icon_renderer_falls_back_to_pyqt6_qtsvg(monkeypatch) -> None:
    rendered_payloads: list[bytes] = []

    class FakePixmap:
        def __init__(self, width: int, height: int) -> None:
            self.width = width
            self.height = height
            self.rendered = False
            self.painter_ended = False

        def fill(self, _color: object) -> None:
            return None

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

    icon = icons.garden_icon("close", color="#abcdef")

    assert isinstance(icon, FakeIcon)
    assert icon.source is not None
    assert icon.source.rendered is True
    assert icon.source.painter_ended is True
    assert rendered_payloads
    assert b'style="color:#abcdef"' in rendered_payloads[0]
    assert b'stroke="currentColor"' in rendered_payloads[0]
    assert GARDEN_ICON_PATHS["close"].encode("utf-8") in rendered_payloads[0]
