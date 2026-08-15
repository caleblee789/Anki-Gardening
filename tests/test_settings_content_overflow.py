from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STUDIO_PATH = ROOT / "ankigarden/ui/garden_studio.py"


def _source() -> str:
    return STUDIO_PATH.read_text("utf-8")


def _class_source(class_name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def _method_source(class_name: str, method_name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    class_node = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    method = next(
        item
        for item in class_node.body
        if isinstance(item, ast.FunctionDef) and item.name == method_name
    )
    segment = ast.get_source_segment(source, method)
    assert segment is not None
    return segment


def _compiled_responsive_method() -> Any:
    class Direction:
        TopToBottom = "stacked"
        LeftToRight = "columns"

    class Policy:
        Expanding = "expanding"
        Preferred = "preferred"

    class ScrollBarPolicy:
        ScrollBarAlwaysOff = "off"
        ScrollBarAsNeeded = "as-needed"

    scope: dict[str, Any] = {
        "QBoxLayout": SimpleNamespace(Direction=Direction),
        "QSizePolicy": SimpleNamespace(Policy=Policy),
        "Qt": SimpleNamespace(ScrollBarPolicy=ScrollBarPolicy),
        "SETTINGS_CONTROLS_WIDE_MIN_WIDTH": 280,
        "SETTINGS_CONTROLS_WIDE_MAX_WIDTH": 380,
        "settings_layout_is_compact": lambda width: max(0, int(width)) < 760,
    }
    exec(textwrap.dedent(_method_source("GardenStudioWidget", "_apply_responsive_layout")), scope)
    return scope["_apply_responsive_layout"]


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


def test_home_preview_dynamic_copy_wraps_and_does_not_set_a_width_floor() -> None:
    preview = _class_source("HomeGardenPreview")
    title = preview.split('self.title = QLabel("My Garden")', 1)[1].split(
        "self.support = QLabel", 1
    )[0]
    support = preview.split("self.support = QLabel", 1)[1].split(
        "identity.addWidget", 1
    )[0]

    for label in (title, support):
        assert ".setWordWrap(True)" in label
        assert ".setMinimumWidth(0)" in label
        assert "QSizePolicy.Policy.Ignored" in label

    assert "scene.setMinimumWidth(0)" in preview
    assert "self.scrim.setMinimumWidth(0)" in preview


def test_settings_columns_release_implicit_qt_minimum_widths() -> None:
    studio = _class_source("GardenStudioWidget")
    toggle_row = _class_source("ToggleSettingRow")

    assert "self.setMinimumWidth(0)" in studio
    assert "self.controls.setMinimumWidth(0)" in studio
    assert "self.controls.setMinimumWidth(340)" not in studio
    assert "self.preview_panel.setMinimumWidth(0)" in studio
    assert "QSizePolicy.Policy.Ignored" in studio
    assert "form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)" in studio
    assert "self.setMinimumWidth(0)" in toggle_row
    assert "note.setMinimumWidth(0)" in toggle_row


def test_normal_settings_viewport_stays_two_column_and_narrow_width_stacks() -> None:
    apply_layout = _compiled_responsive_method()
    controls = _Recorder()
    root_layout = _Recorder()
    preview_panel = _Recorder()
    widget = _Recorder()
    widget._compact_layout = None
    widget.controls = controls
    widget.controls_scroll = _Recorder()
    widget.root_layout = root_layout
    widget.preview_panel = preview_panel

    # A 980 px dialog leaves roughly 880 px for the scrolled Display body
    # after the shell, tab, and body margins. That is ample for 280 px
    # controls plus a shrinkable preview, so it should not need horizontal
    # scrolling or premature stacking.
    apply_layout(widget, 880)
    assert ("setDirection", ("columns",)) in root_layout.calls
    assert ("setMinimumWidth", (280,)) in controls.calls
    assert ("setMaximumWidth", (380,)) in controls.calls
    assert ("setSizePolicy", ("preferred", "preferred")) in controls.calls
    assert ("setMaximumHeight", (420,)) in widget.controls_scroll.calls

    apply_layout(widget, 700)
    assert ("setDirection", ("stacked",)) in root_layout.calls
    assert ("setMinimumWidth", (0,)) in controls.calls
    assert ("setMaximumWidth", (16777215,)) in controls.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in controls.calls
    assert ("setVerticalScrollBarPolicy", ("off",)) in widget.controls_scroll.calls
    assert ("setMinimumHeight", (520,)) in widget.controls_scroll.calls
    assert ("setMaximumHeight", (16777215,)) in widget.controls_scroll.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in widget.controls_scroll.calls
    assert ("updateGeometry", ()) in preview_panel.calls
    assert ("updateGeometry", ()) in widget.calls


def test_advanced_controls_scroll_independently_from_the_preview() -> None:
    studio = _class_source("GardenStudioWidget")
    advanced_finish = _method_source(
        "GardenStudioWidget",
        "_finish_advanced_layout_update",
    )

    assert "self.controls_scroll = QScrollArea()" in studio
    assert "self.controls_scroll.setWidget(self.controls)" in studio
    assert "self.root_layout.addWidget(self.controls_scroll, 0)" in studio
    assert "QLayout.SizeConstraint.SetMinAndMaxSize" in studio
    assert "self.controls.adjustSize()" in advanced_finish
    assert "parent.ensureWidgetVisible(target, 12, 12)" in advanced_finish
    assert "self._scroll_controls_to(" in advanced_finish

    final_scroll = _method_source(
        "GardenStudioWidget",
        "_scroll_controls_to",
    )
    assert "self.controls_scroll.verticalScrollBar()" in final_scroll
    assert "target_bottom - viewport_height + 12" in final_scroll


def test_compact_settings_delegate_vertical_scroll_to_the_outer_page() -> None:
    responsive = _method_source(
        "GardenStudioWidget",
        "_apply_responsive_layout",
    )
    final_scroll = _method_source(
        "GardenStudioWidget",
        "_scroll_controls_to",
    )

    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in responsive
    assert "self.controls.sizeHint().height() if compact else 0" in responsive
    assert "self.controls_scroll.setMaximumHeight(16777215 if compact else 420)" in responsive
    assert "QSizePolicy.Policy.Preferred if compact" in responsive
    assert "if self._compact_layout:\n            return" in final_scroll
