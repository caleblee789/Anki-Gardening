from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STUDIO_PATH = ROOT / "ankigarden" / "ui" / "garden_studio.py"


def _compiled_layout_method() -> Any:
    source = STUDIO_PATH.read_text("utf-8")
    tree = ast.parse(source)
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenStudioWidget"
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_apply_studio_layout_mode"
    )
    segment = ast.get_source_segment(source, method)
    assert segment is not None

    class Direction:
        TopToBottom = "stacked"
        LeftToRight = "columns"

    class Policy:
        Expanding = "expanding"
        Preferred = "preferred"

    scope: dict[str, Any] = {
        "QBoxLayout": SimpleNamespace(Direction=Direction),
        "QSizePolicy": SimpleNamespace(Policy=Policy),
        "Qt": SimpleNamespace(
            ScrollBarPolicy=SimpleNamespace(ScrollBarAlwaysOff="off")
        ),
        "SETTINGS_CONTROLS_WIDE_MIN_WIDTH": 190,
        "SETTINGS_CONTROLS_WIDE_MAX_WIDTH": 220,
        "SETTINGS_SCENERY_WIDE_MIN_WIDTH": 180,
        "SETTINGS_SCENERY_WIDE_MAX_WIDTH": 220,
        "COMPACT_MODE": "compact",
    }
    exec(textwrap.dedent(segment), scope)
    return scope["_apply_studio_layout_mode"]


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any) -> None:
            self.calls.append((name, args))

        return record

    def sizeHint(self) -> Any:
        self.calls.append(("sizeHint", ()))
        return SimpleNamespace(height=lambda: 520)


def test_settings_layout_keeps_the_preview_free_vertical_organization() -> None:
    apply_layout = _compiled_layout_method()
    widget = _Recorder()
    widget._compact_layout = None
    widget.controls = _Recorder()
    widget.controls_scroll = _Recorder()
    widget.root_layout = _Recorder()
    widget.theme_card = _Recorder()

    apply_layout(widget, "wide")
    assert ("setDirection", ("stacked",)) in widget.root_layout.calls
    assert ("setMinimumWidth", (0,)) in widget.controls.calls
    assert ("setMaximumWidth", (16_777_215,)) in widget.controls.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in widget.controls.calls
    assert ("setMinimumHeight", (520,)) in widget.controls_scroll.calls
    assert ("setMaximumHeight", (16_777_215,)) in widget.controls_scroll.calls
    assert ("setVerticalScrollBarPolicy", ("off",)) in widget.controls_scroll.calls
    assert ("setMinimumWidth", (0,)) in widget.theme_card.calls
    assert ("setMaximumWidth", (16_777_215,)) in widget.theme_card.calls

    apply_layout(widget, "compact")
    assert ("setDirection", ("stacked",)) in widget.root_layout.calls
    assert ("setMinimumWidth", (0,)) in widget.controls.calls
    assert ("setMaximumWidth", (16_777_215,)) in widget.controls.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in widget.controls.calls
    assert ("setMinimumHeight", (520,)) in widget.controls_scroll.calls
    assert ("setMaximumHeight", (16_777_215,)) in widget.controls_scroll.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in (
        widget.controls_scroll.calls
    )
    assert "self.preview_panel" not in STUDIO_PATH.read_text("utf-8")
    assert ("updateGeometry", ()) in widget.calls


def test_settings_dialog_clamps_the_studio_to_visible_content() -> None:
    dashboard = (
        ROOT / "ankigarden" / "ui" / "dashboard.py"
    ).read_text("utf-8")

    assert "def _sync_behavior_content_height(self)" in dashboard
    assert "if widget is None or widget.isHidden():" in dashboard
    assert "self.behavior.setMaximumHeight(target_height)" in dashboard
    assert "self.behavior.show_home_widget.toggled.connect(" not in dashboard
