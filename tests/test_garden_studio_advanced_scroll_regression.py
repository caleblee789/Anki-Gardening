from __future__ import annotations

import ast
import os
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


pytestmark = pytest.mark.release_evidence


ROOT = Path(__file__).resolve().parents[1]
STUDIO_PATH = ROOT / "ankigarden" / "ui" / "garden_studio.py"
DASHBOARD_PATH = ROOT / "ankigarden" / "ui" / "dashboard.py"


def _method_source(method_name: str) -> str:
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
        if isinstance(node, ast.FunctionDef) and node.name == method_name
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
        "SETTINGS_CONTROLS_WIDE_MIN_WIDTH": 190,
        "SETTINGS_CONTROLS_WIDE_MAX_WIDTH": 220,
        "SETTINGS_SCENERY_WIDE_MIN_WIDTH": 180,
        "SETTINGS_SCENERY_WIDE_MAX_WIDTH": 220,
        "COMPACT_MODE": "compact",
    }
    exec(
        textwrap.dedent(_method_source("_apply_studio_layout_mode")),
        scope,
    )
    return scope["_apply_studio_layout_mode"]


def _class_source(path: Path, class_name: str) -> str:
    source = path.read_text("utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any) -> None:
            self.calls.append((name, args))

        return record


class _ResponsiveRecorder(_Recorder):
    def sizeHint(self) -> Any:
        self.calls.append(("sizeHint", ()))
        return SimpleNamespace(height=lambda: 520)


def test_settings_layout_keeps_the_preview_free_vertical_organization() -> None:
    apply_layout = _compiled_responsive_method()
    controls = _ResponsiveRecorder()
    root_layout = _ResponsiveRecorder()
    widget = _ResponsiveRecorder()
    widget._compact_layout = None
    widget.controls = controls
    widget.controls_scroll = _ResponsiveRecorder()
    widget.root_layout = root_layout
    widget.theme_card = _ResponsiveRecorder()

    apply_layout(widget, "wide")
    assert ("setDirection", ("stacked",)) in root_layout.calls
    assert ("setMinimumWidth", (0,)) in controls.calls
    assert ("setMaximumWidth", (16_777_215,)) in controls.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in controls.calls
    assert ("setMaximumHeight", (16_777_215,)) in widget.controls_scroll.calls
    assert ("setVerticalScrollBarPolicy", ("off",)) in widget.controls_scroll.calls
    assert ("setMinimumWidth", (0,)) in widget.theme_card.calls
    assert ("setMaximumWidth", (16_777_215,)) in widget.theme_card.calls

    apply_layout(widget, "compact")
    assert ("setDirection", ("stacked",)) in root_layout.calls
    assert ("setMinimumWidth", (0,)) in controls.calls
    assert ("setMaximumWidth", (16_777_215,)) in controls.calls
    assert ("setSizePolicy", ("expanding", "preferred")) in controls.calls
    assert ("setVerticalScrollBarPolicy", ("off",)) in widget.controls_scroll.calls
    assert ("setMinimumHeight", (520,)) in widget.controls_scroll.calls
    assert ("setMaximumHeight", (16_777_215,)) in widget.controls_scroll.calls
    assert (
        "setSizePolicy",
        ("expanding", "preferred"),
    ) in widget.controls_scroll.calls
    assert "self.preview_panel" not in _class_source(
        STUDIO_PATH,
        "GardenStudioWidget",
    )
    assert ("updateGeometry", ()) in widget.calls


class _Controls(_Recorder):
    def __init__(self, content_height: int) -> None:
        super().__init__()
        self.content_height = content_height

    def sizeHint(self) -> Any:
        self.calls.append(("sizeHint", ()))
        return SimpleNamespace(height=lambda: self.content_height)


class _ControlsScroll(_Recorder):
    def __init__(self, viewport_height: int) -> None:
        super().__init__()
        self.viewport_height = viewport_height

    def setMinimumHeight(self, height: int) -> None:
        self.viewport_height = int(height)
        self.calls.append(("setMinimumHeight", (int(height),)))


class _ScrollBar(_Recorder):
    def maximum(self) -> int:
        return 0


class _OuterScroll(_Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.bar = _ScrollBar()

    def verticalScrollBar(self) -> _ScrollBar:
        return self.bar

    def parentWidget(self) -> None:
        return None


class _Studio(_Recorder):
    def __init__(self, *, compact: bool) -> None:
        super().__init__()
        self._compact_layout = compact
        self.controls_layout = _Recorder()
        self.advanced_panel = _Recorder()
        self.advanced_toggle = _Recorder()
        self.controls = _Controls(content_height=572)
        self.controls_scroll = _ControlsScroll(viewport_height=487)
        self.outer_scroll = _OuterScroll()

    def parentWidget(self) -> _OuterScroll:
        return self.outer_scroll

    def _scroll_controls_to(self, target: Any, expanded: bool) -> None:
        self.calls.append(("_scroll_controls_to", (target, expanded)))


def _compiled_finish_method() -> Any:
    class _ImmediateTimer:
        @staticmethod
        def singleShot(_delay: int, callback: Any) -> None:
            callback()

    scope: dict[str, Any] = {
        "QScrollArea": _OuterScroll,
        "QTimer": _ImmediateTimer,
    }
    exec(
        textwrap.dedent(_method_source("_finish_advanced_layout_update")),
        scope,
    )
    return scope["_finish_advanced_layout_update"]


@pytest.mark.parametrize("compact", [False, True], ids=["wide", "compact"])
def test_advanced_expansion_grows_the_non_scrolling_viewport_without_repositioning(
    compact: bool,
) -> None:
    finish_update = _compiled_finish_method()
    studio = _Studio(compact=compact)

    finish_update(studio, True)

    assert studio.controls_scroll.viewport_height == 572
    assert ("setMinimumHeight", (572,)) in studio.controls_scroll.calls
    assert ("updateGeometry", ()) in studio.controls_scroll.calls
    assert not any(
        name == "ensureWidgetVisible" for name, _args in studio.outer_scroll.calls
    )
    assert ("setValue", (0,)) in studio.outer_scroll.bar.calls


def test_nursery_scroll_regions_have_stable_accessible_names() -> None:
    nursery = _class_source(DASHBOARD_PATH, "NurseryDialog")

    for name in (
        "Plants catalog",
        "Fertilizers and boosts catalog",
        "Garden beds catalog",
        "Garden Decorations and Scenery catalog",
    ):
        assert f'"{name}"' in nursery
    assert nursery.count("setAccessibleName") >= 8


def test_dialog_state_preserves_the_declared_ready_focus_contract() -> None:
    shell = _class_source(DASHBOARD_PATH, "DialogShell")
    dialog = _class_source(DASHBOARD_PATH, "GardenDialog")

    assert "def _policy_focus_target" in shell
    assert "InitialFocusPolicy.FIRST_EDITABLE" in shell
    assert "InitialFocusPolicy.SELECTED_ROUTE" in shell
    assert "InitialFocusPolicy.SAFE_ACTION" in shell
    assert "self._state_focus_target = None" in dialog
    assert "self.set_initial_focus(self.state_retry)" not in dialog
    assert "self.set_initial_focus(self.top_close)" not in dialog


def test_settings_diagnostics_actions_reflow_from_their_own_viewport() -> None:
    settings = _class_source(DASHBOARD_PATH, "GardenSettingsDialog")

    assert '"settings.diagnostics-actions"' in settings
    assert "self.diagnostics_scroll.viewport()" in settings
    assert "QBoxLayout.Direction.LeftToRight" in settings
    assert "QBoxLayout.Direction.TopToBottom" not in settings
    assert '"refresh-diagnostics"' in settings
    assert '"copy-report"' in settings
    assert '"technical-details"' in settings


def test_live_qt_advanced_content_stays_inside_inner_viewport_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real QScrollArea geometry in Anki-enabled test environments."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QScrollArea
        from ankigarden.config import DEFAULT_CONFIG
        from ankigarden.ui.garden_studio import GardenStudioWidget
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    class _Config:
        def value(self, key: str, default: Any = None) -> Any:
            return DEFAULT_CONFIG.get(key, default)

        def nested(self, *keys: str, default: Any = None) -> Any:
            node: Any = DEFAULT_CONFIG
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node

    application = QApplication.instance() or QApplication([])
    for width, expected_mode in ((960, "wide"), (600, "compact")):
        studio = GardenStudioWidget(_Config())
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setWidget(studio)
        outer.resize(width, 520)
        outer.show()
        application.processEvents()

        studio.advanced_toggle.setChecked(True)
        application.processEvents()
        application.processEvents()

        assert studio.property("studioMode") == expected_mode
        assert studio.controls_scroll.minimumHeight() >= studio.controls.sizeHint().height()
        assert (
            studio.controls_scroll.viewport().height()
            >= studio.advanced_panel.geometry().bottom()
        )
        outer.close()
        studio.deleteLater()
        application.processEvents()


def test_live_qt_focus_policy_and_state_restoration_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import (
            QApplication,
            QEvent,
            QKeyEvent,
            QLineEdit,
            QPushButton,
            QTabWidget,
            QVBoxLayout,
            QWidget,
            Qt,
        )
        from ankigarden.ui.dashboard import GardenDialog
        from ankigarden.ui.dialog_foundations import (
            DialogViewState,
            InitialFocusPolicy,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(900, 700)
    owner_layout = QVBoxLayout(owner)
    invoker = QPushButton("Open focus probe")
    owner_layout.addWidget(invoker)
    owner.show()
    invoker.setFocus()
    dialog = GardenDialog(owner, "Focus policy probe", show_close=False)
    dialog.remember_invoker(invoker)
    body = QWidget()
    layout = QVBoxLayout(body)
    editable = QLineEdit()
    route = QTabWidget()
    route.addTab(QWidget(), "Route")
    route.setFixedHeight(96)
    destructive = QPushButton("Delete")
    destructive.setProperty("variant", "destructive")
    safe = QPushButton("Cancel")
    safe.setProperty("variant", "secondary")
    body.setMinimumHeight(260)
    layout.addWidget(editable)
    layout.addWidget(route)
    layout.addWidget(destructive)
    layout.addWidget(safe)
    dialog.set_body_widget(body)
    dialog.resize(600, 500)
    dialog.show()
    application.processEvents()

    dialog.set_initial_focus(None, InitialFocusPolicy.FIRST_EDITABLE)
    assert dialog._policy_focus_target(dialog._focusable_descendants()) is editable
    dialog.set_initial_focus(None, InitialFocusPolicy.SELECTED_ROUTE)
    assert dialog._policy_focus_target(dialog._focusable_descendants()) is route
    dialog.set_initial_focus(None, InitialFocusPolicy.SAFE_ACTION)
    assert dialog._policy_focus_target(dialog._focusable_descendants()) is safe

    dialog.set_initial_focus(editable, InitialFocusPolicy.FIRST_EDITABLE)
    ready_target = dialog._initial_focus_target
    ready_policy = dialog._initial_focus_policy
    dialog.set_dialog_state(DialogViewState.LOADING, "Loading focus probe.")
    application.processEvents()
    assert dialog.focusWidget() is dialog.state_message
    assert dialog._initial_focus_target is ready_target
    assert dialog._initial_focus_policy is ready_policy
    dialog.set_dialog_state(DialogViewState.READY)
    application.processEvents()
    assert dialog.focusWidget() is editable

    dialog.set_dialog_state(
        DialogViewState.ERROR,
        "The focus probe failed.",
        retry=lambda: None,
    )
    application.processEvents()
    assert dialog.focusWidget() is dialog.state_retry
    assert dialog._initial_focus_target is ready_target
    assert dialog._initial_focus_policy is ready_policy

    dialog.set_dialog_state(DialogViewState.READY)
    application.processEvents()
    assert dialog._state_focus_target is None
    assert dialog.focusWidget() is editable

    focusable = dialog._focusable_descendants()
    assert editable in focusable
    assert safe in focusable
    focusable[-1].setFocus()
    assert dialog.focusNextPrevChild(True)
    assert dialog.focusWidget() is focusable[0]
    focusable[0].setFocus()
    assert dialog.focusNextPrevChild(False)
    assert dialog.focusWidget() is focusable[-1]

    escape = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )
    dialog.keyPressEvent(escape)
    # The offscreen platform does not activate the exposed owner when a tool
    # window hides, so mirror the native window manager before the queued
    # restoration callback runs.
    owner.activateWindow()
    application.processEvents()
    assert escape.isAccepted()
    assert not dialog.isVisible()
    assert application.focusWidget() is invoker

    owner.close()
    application.processEvents()


def _live_engine_fixture() -> tuple[Any, Any, Any]:
    from copy import deepcopy
    from datetime import date

    from ankigarden.config import DEFAULT_CONFIG
    from ankigarden.game import GardenGameEngine
    from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
    from ankigarden.storage import DueObligationStatus

    class _Config:
        def __init__(self) -> None:
            self.data = deepcopy(DEFAULT_CONFIG)

        def value(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def nested(self, *keys: str, default: Any = None) -> Any:
            node: Any = self.data
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node

    class _Storage:
        def __init__(self) -> None:
            self.day = date.today().isoformat()
            self.now_ms = 1_786_150_000_000
            self.day_start_ms = self.now_ms - 12 * 60 * 60 * 1000
            self.state = GardenState(
                plants=[Plant("p1", "bonsai", "Bonsai Plant", 0)],
                active_plant_id="p1",
                daily_stats=DailyStats(day=self.day),
                last_active_day=self.day,
                active_plant_periods=[
                    ActivePlantPeriod(self.day, "p1", self.now_ms - 10_000)
                ],
            )
            self.addon_dir = ROOT / "ankigarden"
            self.assets_root = self.addon_dir / "assets"
            self.cache_dir = self.addon_dir / "user_files" / "cache"
            self.save_count = 0

        def save(self) -> None:
            self.save_count += 1

        def current_scheduler_day(self) -> str:
            return self.day

        def current_day_start_ms(self) -> int:
            return self.day_start_ms

        def current_day_end_ms(self) -> int:
            return self.day_start_ms + 24 * 60 * 60 * 1000

        def current_time_ms(self) -> int:
            return self.now_ms

        def due_obligations(self) -> Any:
            return DueObligationStatus()

        def load_asset_metadata(self) -> dict[str, Any]:
            return {}

        def save_asset_metadata(self, _data: Any) -> None:
            return None

    config = _Config()
    storage = _Storage()
    return config, storage, GardenGameEngine(config, storage)


def _live_replacement_quote(engine: Any, storage: Any) -> Any:
    from ankigarden.models.state import Fertilizer
    from ankigarden.purchases import PurchaseKind

    storage.state.currency_balance = 500
    plant = storage.state.plants[0]
    now = engine._now_seconds()
    plant.fertilizer = Fertilizer("basic", 1, now + 3_400, now - 200)
    return engine.quote_purchase(
        PurchaseKind.FERTILIZER,
        "premium",
        target_id=plant.plant_id,
    )


def test_collection_landmark_bottom_anchor_contains_intersecting_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 950x570 Collection endgame fold must not expose clipped actions."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )
    try:
        from aqt.qt import (
            QAbstractButton,
            QApplication,
            QCoreApplication,
            QEvent,
            QFrame,
            QWidget,
        )
        from ankigarden.growth import GROWTH_THRESHOLDS, GROWTH_UNITS_PER_POINT
        from ankigarden.models.state import GardenProjectState
        from ankigarden.ui.dashboard import GardenDashboard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    plant = storage.state.plants[0]
    plant.growth_units = GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT
    plant.slot_index = 0
    storage.state.starter_selection_complete = True
    storage.state.garden_project = GardenProjectState(
        completed_project_ids=["mossy_stone_path"],
        displayed_project_id="mossy_stone_path",
    )

    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard._refresh_collection_list()
    progress = dashboard.progress_dialog
    progress.navigation.set_current("collection")
    progress.resize(950, 570)
    progress.show()
    for _iteration in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        application.processEvents()

    collection = dashboard.collection_list
    assert collection.grid.contentsMargins().bottom() == 28
    scroll = collection.scroll
    viewport = scroll.viewport()
    bar = scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    application.processEvents()

    completed_row = next(
        candidate
        for candidate in collection.findChildren(QFrame)
        if bool(candidate.property("completedLandmark"))
        and str(candidate.property("landmarkId") or "") == "mossy_stone_path"
    )

    def viewport_bounds(widget: QWidget) -> tuple[int, int, int, int]:
        origin = widget.mapTo(viewport, widget.rect().topLeft())
        return (
            int(origin.x()),
            int(origin.y()),
            int(widget.width()),
            int(widget.height()),
        )

    def intersects_viewport(bounds: tuple[int, int, int, int]) -> bool:
        x, y, width, height = bounds
        return bool(
            x < int(viewport.width())
            and x + width > 0
            and y < int(viewport.height())
            and y + height > 0
        )

    landmark_bounds = viewport_bounds(completed_row)
    assert intersects_viewport(landmark_bounds)
    landmark_x, landmark_y, landmark_width, landmark_height = landmark_bounds
    assert landmark_x >= 0
    assert landmark_y >= 0
    assert landmark_x + landmark_width <= int(viewport.width())
    assert landmark_y + landmark_height <= int(viewport.height())

    intersecting_buttons = [
        (button, viewport_bounds(button))
        for button in collection.findChildren(QAbstractButton)
        if button.isVisibleTo(viewport)
        and intersects_viewport(viewport_bounds(button))
    ]
    assert intersecting_buttons
    for button, (x, y, width, height) in intersecting_buttons:
        assert x >= 0, button.text()
        assert y >= 0, button.text()
        assert x + width <= int(viewport.width()), button.text()
        assert y + height <= int(viewport.height()), button.text()

    progress.close()
    owner.close()
    application.processEvents()


def test_species_purchase_receipt_uses_seed_art_and_routes_by_bed_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.models.state import CURRENT_CATALOG_SPECIES_ORDER, Plant
        from ankigarden.presentation import project_collection
        from ankigarden.purchases import (
            PurchaseKind,
            PurchaseRequest,
            purchase_presentation,
        )
        from ankigarden.ui.dashboard import NurseryDialog
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    _config, storage, engine = _live_engine_fixture()
    species = [
        item for item in CURRENT_CATALOG_SPECIES_ORDER
        if item != "sunflower"
    ]
    plants = [
        Plant(
            f"surface32-{item}",
            item,
            f"{item.replace('_', ' ').title()} Plant",
            index if index < 6 else None,
        )
        for index, item in enumerate(species)
    ]
    state = storage.state
    state.plants = plants
    state.unlocked_species = list(species)
    state.unlocked_slots = 6
    state.active_plant_id = plants[0].plant_id
    state.starter_selection_complete = True
    state.currency_balance = 5_000

    quote = engine.quote_purchase(PurchaseKind.SPECIES, "sunflower")
    outcome = engine.confirm_purchase(PurchaseRequest.from_quote(quote))
    assert outcome.success
    assert outcome.message == "Sunflower added."
    assert project_collection(state).species_text == "10 of 10 species discovered"

    displaced = plants[1]
    displaced_slot = int(displaced.slot_index)
    assert engine.move_to_collection(displaced.plant_id)[0]
    owner = QWidget()
    owner.show()
    placement = NurseryDialog(owner, engine, storage)
    placement._show_purchase_receipt(
        outcome,
        purchase_presentation(quote, ignore_status=True),
    )
    placement.show()
    application.processEvents()

    icon = placement.nursery_toast.icon
    icon_pixmap = icon.pixmap()
    assert placement.nursery_toast.message.text() == "Sunflower added."
    assert placement.nursery_toast.action.text() == "Place in garden"
    assert placement.nursery_toast.property("receiptPrimaryRoute") == "Place in garden"
    assert icon.accessibleName() == "Sunflower Seed artwork"
    assert icon_pixmap is not None and not icon_pixmap.isNull()

    placement.nursery_toast.action.click()
    application.processEvents()
    sunflower = engine.plant_story(str(outcome.result_id))
    assert sunflower is not None
    assert sunflower.slot_index == displaced_slot
    assert engine.move_to_collection(sunflower.plant_id)[0]
    assert engine.plant_from_collection(displaced.plant_id, displaced_slot)[0]
    placement.hide()
    placement.deleteLater()

    no_bed = NurseryDialog(owner, engine, storage)
    no_bed._show_purchase_receipt(
        outcome,
        purchase_presentation(quote, ignore_status=True),
    )
    no_bed.show()
    application.processEvents()
    assert no_bed.nursery_toast.message.text() == "Sunflower added."
    assert no_bed.nursery_toast.action.text() == "Open garden"
    assert no_bed.nursery_toast.property("receiptPrimaryRoute") == "Open garden"

    no_bed.hide()
    no_bed.deleteLater()
    owner.close()
    application.processEvents()


def _focus_signature(surface: Any) -> tuple[tuple[str, str, str, str], ...]:
    """Return stable control identity without relying on transient PyQt wrappers."""

    signature: list[tuple[str, str, str, str]] = []
    for widget in surface._focusable_descendants():
        text_reader = getattr(widget, "text", None)
        text = str(text_reader()) if callable(text_reader) else ""
        signature.append(
            (
                type(widget).__name__,
                str(widget.objectName() or ""),
                str(widget.accessibleName() or ""),
                text,
            )
        )
    return tuple(signature)


def test_live_qt_surface_breakpoints_are_stable_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the release surfaces against Anki Qt when that runtime is present."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import (
            FertilizerReplacementDialog,
            GardenDashboard,
            GardenSettingsDialog,
            NurseryDialog,
            PlantStoryDialog,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    from ankigarden.models.state import CurrencyTransaction

    storage.state.currency_balance = 5
    storage.state.currency_transactions = [
        CurrencyTransaction(
            "tx-1",
            "event-1",
            "First card today",
            10,
            10,
            "2026-08-24T10:00:00",
        ),
        CurrencyTransaction(
            "tx-2",
            "event-2",
            "Nursery purchase",
            -5,
            5,
            "2026-08-24T11:00:00",
        ),
    ]
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)

    replacement = FertilizerReplacementDialog(
        dashboard,
        engine,
        _live_replacement_quote(engine, storage),
    )
    story = PlantStoryDialog(dashboard, engine, "p1")
    nursery = NurseryDialog(dashboard, engine, storage)
    assert nursery.currently_growing_strip is not None
    assert tuple(
        region.accessibleName()
        for region in (
            nursery.scroll,
            nursery.supplements_scroll,
            nursery.upgrades_scroll,
            nursery.environment_scroll,
        )
    ) == (
        "Plants catalog",
        "Magical Fertilizer and boosts catalog",
        "Garden Spaces catalog",
        "Garden Decorations and Scenery catalog",
    )
    progress = dashboard.progress_dialog
    customize = dashboard.customize_dialog
    settings = GardenSettingsDialog(dashboard, engine, config)
    dashboard._refresh_collection_list()
    assert dashboard.collection_filter_responsive is not None
    assert nursery.catalog_content_responsive
    nursery_controllers = (
        (nursery.hero_responsive, "nursery-hero"),
        (nursery.receipt_responsive, "nursery-receipt"),
        (
            nursery.currently_growing_strip.responsive,
            "nursery-current-plant",
        ),
    ) + tuple(
        (controller, f"nursery-content-{index}")
        for index, controller in enumerate(nursery.catalog_content_responsive)
    )

    surfaces = (
        (
            "replacement",
            replacement,
            (
                (replacement.comparison_responsive, "replacement-comparison"),
                (replacement.actions_responsive, "replacement-actions"),
            ),
            (443, 445),
            "comparisonMode",
            "compact",
        ),
        (
            "story",
            story,
            ((story.hero_responsive, "story-hero"),),
            (587, 589),
            "heroMode",
            "wide",
        ),
        (
            "nursery",
            nursery,
            nursery_controllers,
            (795, 797),
            "heroMode",
            "wide",
        ),
        (
            "progress",
            progress,
            ((progress.navigation_responsive, "progress-navigation"),),
            (867, 869),
            "navigationMode",
            "wide",
        ),
        (
            "customize",
            customize,
            ((customize.collection_detail_responsive, "collection-detail-workspace"),),
            (867, 869),
            "workspaceMode",
            "compact",
        ),
    )

    shared_controllers = (
        settings.report_actions_responsive,
        dashboard.collection_filter_responsive,
        dashboard.garden_stats_bar.growth_identity_responsive,
    )
    for controller in shared_controllers:
        threshold = controller.evaluate(100_000).threshold_width
        assert [
            controller.evaluate(threshold + offset).mode
            for offset in (-2, -1, 0, 1, 2)
        ] == ["compact", "compact", "wide", "wide", "wide"]

    for _label, surface, controllers, historical, property_name, expected in surfaces:
        surface.show()
        application.processEvents()
        focus_order = _focus_signature(surface)
        for controller, _controller_label in controllers:
            threshold = controller.evaluate(100_000).threshold_width
            modes = [
                controller.evaluate(threshold + offset).mode
                for offset in (-2, -1, 0, 1, 2)
            ]
            assert modes == ["compact", "compact", "wide", "wide", "wide"]
            assert controller.region_order == controller.telemetry.region_order
            assert _focus_signature(surface) == focus_order

        observed: list[str] = []
        for width in historical:
            surface.resize(width, max(surface.minimumHeight(), 620))
            application.processEvents()
            observed.append(str(surface.property(property_name)))
        assert observed == [expected, expected]
        surface.hide()

    settings.show()
    application.processEvents()
    settings_focus_order = _focus_signature(settings)
    for controller in (
        settings.behavior.studio_responsive,
        settings.settings_footer_responsive,
    ):
        threshold = controller.evaluate(100_000).threshold_width
        assert [
            controller.evaluate(threshold + offset).mode
            for offset in (-2, -1, 0, 1, 2)
        ] == ["compact", "compact", "wide", "wide", "wide"]
        assert _focus_signature(settings) == settings_focus_order
    for width in (807, 809):
        settings.resize(width, 620)
        application.processEvents()
        assert settings.behavior.property("studioMode") == "wide"
        assert settings.property("footerMode") == "wide"
    settings.resize(1020, 690)
    settings.behavior.advanced_toggle.setChecked(True)
    application.processEvents()
    application.processEvents()
    display_scroll = settings.active_vertical_scroll_regions()[0]
    assert display_scroll.widget().width() <= display_scroll.viewport().width()
    settings.hide()

    dashboard.show()
    application.processEvents()
    dashboard.garden_stats_bar._growth_value_full_text = (
        "29,975 / 30,000 Growth"
    )
    dashboard.garden_stats_bar._refresh_growth_value_copy()
    dashboard_controllers = {
        "header_full": dashboard.dashboard_header_full,
        "title_actions": dashboard.dashboard_header_title_actions,
        "metrics": dashboard.dashboard_metrics_responsive,
        "milestone": dashboard.dashboard_milestone_responsive,
        "rearrange": dashboard.dashboard_rearrange_responsive,
    }
    dashboard_focus_order = _focus_signature(dashboard)
    header_inset = (
        dashboard.header_grid.contentsMargins().left()
        + dashboard.header_grid.contentsMargins().right()
    )
    header_controller_names = {"header_full", "title_actions", "metrics"}
    for target_name, controller in dashboard_controllers.items():
        threshold = controller.evaluate(100_000).threshold_width
        owning_inset = header_inset if target_name in header_controller_names else 0
        snapshots: list[dict[str, str]] = []
        for offset in (-2, -1, 0, 1, 2):
            dashboard._apply_responsive_layout(threshold + owning_inset + offset)
            snapshots.append(
                {
                    name: str(candidate.telemetry.mode)
                    for name, candidate in dashboard_controllers.items()
                }
            )
        assert snapshots[0][target_name] == "compact"
        assert snapshots[1][target_name] == "compact"
        assert snapshots[2][target_name] == "wide"
        assert snapshots[3][target_name] == "wide"
        assert snapshots[4][target_name] == "wide"
        for other_name in dashboard_controllers.keys() - {target_name}:
            assert snapshots[1][other_name] == snapshots[2][other_name]
        assert _focus_signature(dashboard) == dashboard_focus_order

    historical_dashboard = {
        596: ("compact", "compact", "compact", "wide"),
        699: ("compact", "compact", "compact", "wide"),
        701: ("compact", "compact", "compact", "wide"),
        819: ("compact", "compact", "wide", "wide"),
        821: ("compact", "compact", "wide", "wide"),
        899: ("compact", "compact", "wide", "wide"),
        901: ("compact", "compact", "wide", "wide"),
        999: ("compact", "wide", "wide", "wide"),
        1001: ("compact", "wide", "wide", "wide"),
        1216: ("compact", "wide", "wide", "wide"),
        1359: ("compact", "wide", "wide", "wide"),
        1361: ("compact", "wide", "wide", "wide"),
        1700: ("wide", "wide", "wide", "wide"),
    }
    for width, expected_modes in historical_dashboard.items():
        dashboard._apply_responsive_layout(width)
        assert (
            str(dashboard.dashboard_header_full.telemetry.mode),
            str(dashboard.dashboard_metrics_responsive.telemetry.mode),
            str(dashboard.dashboard_milestone_responsive.telemetry.mode),
            str(dashboard.dashboard_rearrange_responsive.telemetry.mode),
        ) == expected_modes

        dashboard.resize(width + 24, 700)
        application.processEvents()
        assert dashboard.title_stack_widget.width() >= 230
        assert (
            dashboard.garden_stats_bar.streak_label.width()
            >= dashboard.garden_stats_bar.streak_label.sizeHint().width()
        )
        assert (
            dashboard.garden_stats_bar.streak_bonus.width()
            >= dashboard.garden_stats_bar.streak_bonus.sizeHint().width()
        )
        assert (
            dashboard.garden_stats_bar.growth_value.width()
            >= dashboard.garden_stats_bar.growth_value.sizeHint().width()
        )
        assert (
            dashboard.customize_btn.width()
            >= dashboard.customize_btn.sizeHint().width()
        )

    dashboard.hide()
    owner.close()
    application.processEvents()


def test_live_qt_dashboard_does_not_adopt_nested_dialog_scrolls_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep each native dialog's scroll and pinned-footer contract isolated."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import GardenDashboard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard.show()
    application.processEvents()

    def assert_owner_does_not_adopt(child: Any) -> None:
        child_regions = child.active_vertical_scroll_regions()
        assert child_regions
        clearance_before = tuple(
            region.property("footerClearance") for region in child_regions
        )

        dashboard_regions = dashboard.active_vertical_scroll_regions()
        dashboard._sync_footer_clearance()
        dashboard.resize(dashboard.width() + 2, dashboard.height())
        application.processEvents()

        assert all(region.window() is child for region in child_regions)
        assert all(
            not any(region is candidate for candidate in dashboard_regions)
            for region in child_regions
        )
        assert all(
            not any(
                region is candidate
                for candidate in dashboard._registered_scroll_regions
            )
            for region in child_regions
        )
        assert all(
            region.window() is dashboard
            for region in dashboard._registered_scroll_regions
        )
        assert tuple(
            region.property("footerClearance") for region in child_regions
        ) == clearance_before

    progress = dashboard.progress_dialog
    progress.show()
    application.processEvents()
    assert_owner_does_not_adopt(progress)
    progress.hide()

    customize = dashboard.customize_dialog
    customize.prepare_to_show()
    customize.show()
    application.processEvents()
    assert customize.body_scroll.property("footerClearance") is not None
    assert int(customize.body_scroll.property("footerClearance")) == int(
        customize.footer.height()
    )
    assert_owner_does_not_adopt(customize)

    customize.hide()
    dashboard.hide()
    owner.close()
    application.processEvents()


def test_live_qt_canonical_dashboard_contains_scene_without_outer_scroll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the 1240 by 840 release viewport on one complete Garden surface."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import GardenDashboard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(1280, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard.resize(1240, 840)
    dashboard.show()
    application.processEvents()
    application.processEvents()
    dashboard._update_scene_height(840)
    application.processEvents()

    viewport = dashboard.dashboard_page
    origin = dashboard.scene.mapTo(
        viewport,
        dashboard.scene.rect().topLeft(),
    )
    scene_bottom = int(origin.y()) + int(dashboard.scene.height())

    assert dashboard.active_vertical_scroll_regions() == ()
    assert not hasattr(dashboard, "dashboard_scroll")
    assert int(origin.y()) >= 0
    assert scene_bottom <= int(viewport.height())
    assert int(dashboard.scene.maximumHeight()) == 16777215
    assert int(dashboard.scene.property("viewportHeightLimit")) >= int(
        dashboard.scene.minimumHeight()
    )

    dashboard.hide()
    owner.close()
    application.processEvents()


def test_live_qt_plant_popover_state_matrix_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove anatomy and action geometry across the existing plant states."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import PlantInfoCard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(640, 520)
    owner.show()
    card = PlantInfoCard(owner)

    def payload(**overrides: Any) -> dict[str, Any]:
        values: dict[str, Any] = {
            "plant_id": "rose",
            "name": "Rose Plant",
            "species": "rose",
            "stage": "sprout",
            "next_stage": "young",
            "growth_points": 500,
            "stage_points": 0,
            "stage_goal": 2_000,
            "fully_grown": False,
            "is_active": True,
            "fertilizer_status": {"phase": "inactive"},
            "growth_today": 0,
            "asset": None,
        }
        values.update(overrides)
        return values

    def settle(values: dict[str, Any]) -> int:
        card.set_selected(values)
        card.setFixedWidth(304)
        card.layout().invalidate()
        card.layout().activate()
        card.adjustSize()
        card.show()
        application.processEvents()
        application.processEvents()
        return card.height()

    active_height = settle(payload())
    assert card.width() == 304
    assert 300 <= active_height <= 325
    assert card.artwork.size().width() == card.artwork.size().height() == 48
    assert card.close_btn.size().width() == card.close_btn.size().height() == 32
    assert card.identity.y() == card.nurtured_badge.y()
    assert card.identity.geometry().right() + 6 <= card.nurtured_badge.geometry().left()
    heading_right = card.heading.mapTo(card, card.heading.rect().topRight()).x()
    close_left = card.close_btn.mapTo(card, card.close_btn.rect().topLeft()).x()
    assert heading_right + 10 <= close_left
    assert card.stage_progress.label.text() == "Growth toward Young"
    assert card.stage_progress.value_label.text() == "0 / 2,000"
    assert card.stage_progress.bar.minimum() == 0
    assert card.stage_progress.bar.maximum() == 2_000
    assert card.stage_progress.bar.value() == 0

    assert card.growth_charge.height() == 36
    assert card.fertilize.height() == card.move.height() == 36
    assert card.move.width() == 84
    assert card.fertilize.geometry().right() + 8 == card.move.geometry().left()
    assert card.growth_charge.geometry().left() == card.fertilize.geometry().left()
    assert card.growth_charge.geometry().right() == card.move.geometry().right()
    assert card.story.height() == card.nurture.height() == 36
    assert card.story.geometry().left() == card.nurture.geometry().left()
    assert card.story.geometry().right() == card.nurture.geometry().right()
    assert card.story.property("navigationRow") is True
    assert card.danger_section.isVisibleTo(card)

    stable_geometry = card.growth_charge.geometry()
    card.growth_charge.setEnabled(False)
    card._repolish(card.growth_charge)
    application.processEvents()
    assert card.growth_charge.geometry() == stable_geometry
    card.growth_charge.setEnabled(True)
    card.set_action_busy("growth_charge", True)
    application.processEvents()
    assert card.growth_charge.geometry() == stable_geometry
    card.set_action_busy("growth_charge", False)

    for current in (0, 1_000, 2_000):
        settle(payload(stage_points=current))
        assert card.stage_progress.bar.value() == current
        assert card.stage_progress.value_label.text() == f"{current:,} / 2,000"

    fertilizer_height = settle(payload(
        fertilizer_status={
            "phase": "active",
            "name": "Premium Fertilizer",
            "duration": "12 min left",
            "accessible_text": "Premium Fertilizer, 12 min left",
        },
    ))
    assert card.status_row.isVisibleTo(card)
    assert card.status_value.text() == "Premium Fertilizer · 12 min left"
    assert fertilizer_height <= 420

    long_height = settle(payload(
        name="Extraordinarily Long Rose Plant Name",
        stage="ancient bloom",
        next_stage="evergreen canopy",
        stage_points=1_500,
    ))
    assert card.heading.height() <= card.heading.fontMetrics().lineSpacing() * 2 + 2
    heading_right = card.heading.mapTo(card, card.heading.rect().topRight()).x()
    close_left = card.close_btn.mapTo(card, card.close_btn.rect().topLeft()).x()
    assert heading_right + 10 <= close_left
    assert card.badge_container.geometry().right() <= card.identity_region.width()
    assert long_height <= 420

    inactive_height = settle(payload(is_active=False))
    assert card.nurture.text() == "Nurture"
    assert card.nurture.isVisibleTo(card)
    assert not card.growth_charge.isVisibleTo(card)
    assert not card.fertilize.isVisibleTo(card)
    assert not card.danger_section.isVisibleTo(card)
    assert card.move.geometry().left() == card.nurture.geometry().left()
    assert card.move.geometry().right() == card.nurture.geometry().right()
    assert inactive_height < active_height

    final_height = settle(payload(
        fully_grown=True,
        is_active=False,
        stage="rare flowering",
        next_stage=None,
    ))
    assert not card.progress_region.isVisibleTo(card)
    assert card.choose_another.isVisibleTo(card)
    assert card.move.isVisibleTo(card)
    assert card.story.isVisibleTo(card)
    assert not card.nurture.isVisibleTo(card)
    assert not card.danger_section.isVisibleTo(card)
    assert final_height < active_height

    card.set_selected(None)
    card.hide()
    owner.close()
    application.processEvents()


def test_live_qt_settings_details_stay_bounded_and_scroll_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, Qt, QWidget
        from ankigarden.ui.dashboard import GardenSettingsDialog
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, _storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(900, 700)
    owner.show()
    settings = GardenSettingsDialog(owner, engine, config)
    settings.setMinimumWidth(1)
    settings.tabs.setCurrentIndex(1)
    settings.report_details_toggle.setChecked(True)
    settings.debug_report.setPlainText(
        "\n".join(
            f"Diagnostic {index}: " + "responsive layout evidence " * 10
            for index in range(40)
        )
    )
    settings.show()
    assert settings.footer.isVisible()
    assert settings.settings_footer_actions.isVisible()

    settings.resize(720, 620)
    application.processEvents()
    application.processEvents()
    settings._sync_debug_report_height()
    wide_height = settings.debug_report.height()

    settings.resize(360, 620)
    application.processEvents()
    application.processEvents()
    settings._sync_debug_report_height()
    narrow_height = settings.debug_report.height()
    required_height = (
        int(settings.debug_report.document().size().height())
        + 2 * int(settings.debug_report.frameWidth())
        + 16
    )

    assert 96 <= wide_height <= 240
    assert 96 <= narrow_height <= 240
    assert narrow_height <= required_height
    assert (
        settings.debug_report.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    regions = settings.active_vertical_scroll_regions()
    assert len(regions) == 1
    outer_scroll = regions[0]
    assert settings.report_actions_panel.width() <= outer_scroll.viewport().width()
    assert settings.report_actions_panel.property("troubleshootingActionsMode") == "compact"
    assert outer_scroll.verticalScrollBar().maximum() > 0
    outer_scroll.verticalScrollBar().setValue(
        outer_scroll.verticalScrollBar().maximum()
    )
    assert (
        outer_scroll.verticalScrollBar().value()
        == outer_scroll.verticalScrollBar().maximum()
    )

    settings.close()
    owner.close()
    application.processEvents()


def test_live_qt_compact_progress_navigation_wraps_complete_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QLabel
        from ankigarden.ui.dashboard import GardenSideNavigation
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    navigation = GardenSideNavigation()
    labels = (
        "Overview",
        "Plant Growth",
        "Anki Streak",
        "Garden Coins",
        "Achievements",
        "Collection",
    )
    for index, label in enumerate(labels):
        navigation.add_page(str(index), label, QLabel(label))
    navigation.set_compact(True)
    navigation.resize(680, 400)
    navigation.show()
    application.processEvents()
    application.processEvents()

    assert navigation._rail_columns == 3
    assert navigation.rail.property("navigationRows") == 2
    assert navigation.rail.height() >= (
        2 * 44 + navigation.rail_layout.verticalSpacing()
    )
    positions = []
    for label, button in zip(labels, navigation.buttons.values()):
        assert button.text() == label
        assert button.width() >= button.fontMetrics().horizontalAdvance(label) + 36
        assert navigation.rail.rect().contains(button.geometry())
        positions.append((button.y(), button.x()))
    assert positions == sorted(positions)

    navigation.close()
    application.processEvents()


def test_live_qt_growth_identity_preserves_short_name_and_numeric_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QPoint
        from ankigarden.ui.dashboard import GardenStatsStrip
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    strip = GardenStatsStrip()
    strip.set_compact(True)
    strip.set_growth_details(
        plant_name="Peony Plant",
        stage="Sprout",
        next_stage="Young",
        total_growth=0,
        current=0,
        maximum=2_000,
        remaining=2_000,
        fully_grown=False,
        accessible_text="Peony Plant has 0 of 2,000 Growth.",
    )
    strip.resize(620, 120)
    strip.show()
    application.processEvents()
    application.processEvents()
    strip._sync_growth_identity_layout()
    application.processEvents()

    assert strip.growth_name.text() == "Peony Plant"
    assert strip.growth_value.text() == "0 / 2,000 Growth to Young"
    assert strip.growth_value.accessibleName() == "0 / 2,000 Growth to Young"
    assert strip.cells["growth"].property("growthIdentityMode") == "compact"
    growth_cell = strip.cells["growth"]
    for label in (strip.growth_name, strip.growth_value):
        origin = label.mapTo(growth_cell, QPoint(0, 0))
        assert origin.x() >= 0
        assert origin.x() + label.width() <= growth_cell.contentsRect().right() + 1
        assert label.width() >= label.fontMetrics().horizontalAdvance(label.text())

    strip.close()
    application.processEvents()


def test_live_qt_named_dialog_scroll_and_footer_contracts_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise every release scroll owner at natural and forced-long heights."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import (
            QApplication,
            QAbstractScrollArea,
            QFrame,
            QLabel,
            QPoint,
            QPushButton,
            QTimer,
            Qt,
            QWidget,
        )
        from ankigarden.ui.dashboard import (
            DialogShell,
            FertilizerReplacementDialog,
            GardenDashboard,
            GardenSettingsDialog,
            NurseryDialog,
            PlantStoryDialog,
        )
        from ankigarden.capture_ui_faces import _UiFaceCaptureRunner
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard.show()
    application.processEvents()

    # Build the selection shell without entering its nested modal event loop.
    monkeypatch.setattr(DialogShell, "exec", lambda _dialog: 0)
    dashboard._open_fertilizer_menu("p1")
    fertilizer_selection = dashboard.fertilizer_dialog
    assert isinstance(fertilizer_selection, DialogShell)
    assert fertilizer_selection.fertilizer_option_responsive
    for controller in fertilizer_selection.fertilizer_option_responsive:
        threshold = controller.evaluate(100_000).threshold_width
        assert [
            controller.evaluate(threshold + offset).mode
            for offset in (-2, -1, 0, 1, 2)
        ] == ["compact", "compact", "wide", "wide", "wide"]

    replacement = FertilizerReplacementDialog(
        dashboard,
        engine,
        _live_replacement_quote(engine, storage),
    )
    story = PlantStoryDialog(dashboard, engine, "p1")
    nursery = NurseryDialog(dashboard, engine, storage)
    species = dashboard._build_species_overview_dialog(
        "bonsai",
        parent=dashboard,
    )
    assert species is not None
    replacement.resize(820, replacement.height())
    replacement.show()
    application.processEvents()
    application.processEvents()
    assert replacement.minimumHeight() <= replacement.maximumHeight() <= 660
    assert replacement.property("comparisonMode") == "wide"
    assert replacement.minimumHeight() == min(
        replacement._comparison_policy_minimum_height,
        400,
    )
    assert replacement.maximumHeight() == replacement.property(
        "contentBoundedMaximumHeight"
    )
    assert replacement.maximumHeight() == max(
        replacement.minimumHeight(),
        min(660, replacement.property("contentNaturalHeight") + 10),
    )
    assert species.minimumHeight() == 260
    assert 260 <= species.maximumHeight() <= 900
    species.show()
    application.processEvents()
    application.processEvents()
    assert 400 <= species.height() <= 470
    species_scrolls = species.active_vertical_scroll_regions()
    assert len(species_scrolls) == 1
    species_scroll = species_scrolls[0]
    assert species_scroll.verticalScrollBar().maximum() == 0
    assert not species_scroll.verticalScrollBar().isVisible()
    species_section = next(
        frame
        for frame in species.findChildren(QFrame)
        if bool(frame.property("speciesPlantList"))
    )
    section_top = species_section.mapTo(
        species_scroll.viewport(),
        species_section.rect().topLeft(),
    ).y()
    assert 0 <= section_top < species_scroll.viewport().height()
    species.hide()

    progress = dashboard.progress_dialog
    progress.navigation.set_current("currency")
    application.processEvents()
    application.processEvents()
    currency_scroll = progress.body_scrolls["currency"]
    assert (
        currency_scroll.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert currency_scroll.verticalScrollBar().maximum() == 0
    assert len([
        frame
        for frame in currency_scroll.findChildren(QFrame)
        if frame.property("coinTransactionDivider")
    ]) == 1

    wide_bound = replacement.maximumHeight()
    comparison_threshold = replacement.comparison_responsive.evaluate(
        100_000
    ).threshold_width
    margins = replacement.layout().contentsMargins()
    compact_width = max(
        replacement.minimumWidth(),
        comparison_threshold - 2 + margins.left() + margins.right(),
    )
    replacement.resize(compact_width, wide_bound)
    application.processEvents()
    application.processEvents()
    assert replacement.property("comparisonMode") == "compact"
    assert (
        replacement.minimumHeight()
        == replacement._comparison_policy_minimum_height
    )
    assert replacement.minimumHeight() <= replacement.maximumHeight() <= 660
    assert replacement.maximumHeight() >= wide_bound
    compact_bound = replacement.maximumHeight()
    replacement.resize(820, compact_bound)
    application.processEvents()
    application.processEvents()
    assert replacement.property("comparisonMode") == "wide"
    assert replacement.minimumHeight() == min(
        replacement._comparison_policy_minimum_height,
        400,
    )
    assert abs(replacement.maximumHeight() - wide_bound) <= 2
    settings = GardenSettingsDialog(dashboard, engine, config)
    customize = dashboard.customize_dialog

    natural_ranges: dict[str, int] = {}
    capture_auditor = _UiFaceCaptureRunner.__new__(_UiFaceCaptureRunner)

    def active_region(dialog: Any, label: str) -> Any:
        regions = dialog.active_vertical_scroll_regions()
        assert len(regions) == 1, (
            label,
            tuple(region.accessibleName() for region in regions),
        )
        return regions[0]

    def assert_footer_geometry(dialog: Any, scroll: Any, label: str) -> None:
        footer = dialog._pinned_footer
        if footer is None or not footer.isVisible():
            return
        assert int(scroll.property("footerClearance") or 0) == int(
            footer.height()
        ), label
        viewport = scroll.viewport()
        viewport_bottom = viewport.mapTo(
            dialog,
            QPoint(0, viewport.height()),
        ).y()
        footer_top = footer.mapTo(dialog, QPoint(0, 0)).y()
        assert viewport_bottom <= footer_top + 1, (
            label,
            viewport_bottom,
            footer_top,
        )

    def assert_complete_nursery_fold(scroll: Any, label: str) -> None:
        application.processEvents()
        application.processEvents()
        assert not bool(
            scroll.property("completeRowLargeCorrectionNeeded")
        ), label
        assert int(scroll.property("completeRowBottomGutter") or 0) == 0, label
        content = scroll.widget()
        assert content is not None
        viewport_height = int(scroll.viewport().height())
        partial_rows: list[tuple[int, int]] = []
        for card in content.findChildren(QWidget):
            if not bool(card.property("nurseryCatalogCard")):
                continue
            top = int(card.mapTo(content, QPoint(0, 0)).y())
            bottom = top + int(card.height())
            if top < viewport_height < bottom:
                partial_rows.append((top, bottom))
        assert not partial_rows, (label, viewport_height, partial_rows)

    def assert_surface(dialog: Any, label: str) -> None:
        dialog.show()
        application.processEvents()
        application.processEvents()
        vertical_owners = tuple(
            region
            for region in dialog.findChildren(QAbstractScrollArea)
            if region.window() is dialog
            and region.isVisibleTo(dialog)
            and region.verticalScrollBarPolicy()
            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert len(vertical_owners) == 1, (
            label,
            tuple(type(region).__name__ for region in vertical_owners),
        )
        scroll = active_region(dialog, label)
        assert_footer_geometry(dialog, scroll, label)

        # Recheck the same owner at the surface's supported minimum height.
        dialog.resize(dialog.width(), max(1, dialog.minimumHeight()))
        application.processEvents()
        application.processEvents()
        assert active_region(dialog, label) is scroll
        assert_footer_geometry(dialog, scroll, label)
        assert not capture_auditor._find_geometry_layout_warnings(dialog), label

        bar = scroll.verticalScrollBar()
        natural_ranges[label] = int(bar.maximum())
        content = scroll.widget()
        assert content is not None
        original_minimum = content.minimumHeight()
        forced_height = max(
            original_minimum,
            int(content.sizeHint().height()),
            int(scroll.viewport().height()) + 480,
        )
        content.setMinimumHeight(forced_height)
        content.updateGeometry()
        scroll.updateGeometry()
        application.processEvents()
        application.processEvents()

        assert bar.maximum() > 0, label
        bar.setValue(bar.maximum())
        application.processEvents()
        assert bar.value() == bar.maximum(), label
        viewport = scroll.viewport()
        content_bottom = content.mapTo(
            viewport,
            content.rect().bottomLeft(),
        ).y()
        assert abs(content_bottom - (viewport.height() - 1)) <= 2, (
            label,
            content_bottom,
            viewport.height(),
            bar.maximum(),
        )
        content_layout = content.layout()
        if content_layout is not None:
            layout_bottom = content.mapTo(
                viewport,
                QPoint(0, content_layout.geometry().bottom()),
            ).y()
            assert layout_bottom <= viewport.height() + 1, (
                label,
                layout_bottom,
                viewport.height(),
            )
        assert_footer_geometry(dialog, scroll, label)
        assert not capture_auditor._find_geometry_layout_warnings(dialog), label

        content.setMinimumHeight(original_minimum)
        content.updateGeometry()
        bar.setValue(0)
        dialog.hide()
        application.processEvents()

    assert_surface(nursery, "Nursery")
    nursery.show()
    for index, expected_name, width_range, height_range in (
        (0, "Plants catalog", (930, 970), (520, 570)),
        (1, "Fertilizers and boosts catalog", (930, 970), (540, 570)),
        (2, "Garden Spaces catalog", (900, 950), (340, 370)),
        (3, "Garden Decorations and Scenery catalog", (930, 970), (500, 550)),
    ):
        nursery.catalog_tabs.setCurrentIndex(index)
        application.processEvents()
        application.processEvents()
        region = active_region(nursery, f"Nursery tab {index}")
        assert region.accessibleName() == expected_name
        assert width_range[0] <= nursery.width() <= width_range[1]
        assert height_range[0] <= nursery.height() <= height_range[1]
        assert_complete_nursery_fold(region, expected_name)
        assert not capture_auditor._find_geometry_layout_warnings(nursery), expected_name
    nursery.hide()

    _starter_config, starter_storage, starter_engine = _live_engine_fixture()
    starter_storage.state.starter_selection_complete = False
    starter_nursery = NurseryDialog(dashboard, starter_engine, starter_storage)
    starter_nursery.show()
    application.processEvents()
    application.processEvents()
    assert 925 <= starter_nursery.width() <= 950
    assert 370 <= starter_nursery.height() <= 410
    assert starter_nursery.scroll.verticalScrollBar().maximum() == 0
    assert_complete_nursery_fold(starter_nursery.scroll, "Starter Nursery")
    starter_nursery.hide()

    _final_config, final_storage, final_engine = _live_engine_fixture()
    monkeypatch.setattr(
        final_engine,
        "catalog_summary",
        lambda: {
            "available_species": [],
            "owned_count": 10,
            "available_count": 0,
            "release_ready_species": [f"species-{index}" for index in range(10)],
        },
    )
    monkeypatch.setattr(
        "ankigarden.ui.dashboard.project_collection",
        lambda _state: SimpleNamespace(
            species_text="10 of 10 species discovered",
            collection_entries_text="30 of 93 collection entries discovered",
            collection_complete=True,
        ),
    )
    final_nursery = NurseryDialog(dashboard, final_engine, final_storage)
    final_nursery.show()
    application.processEvents()
    application.processEvents()
    assert 925 <= final_nursery.width() <= 950
    assert 300 <= final_nursery.height() <= 330
    assert_complete_nursery_fold(final_nursery.scroll, "Final Nursery")
    final_labels = {
        label.text()
        for label in final_nursery.findChildren(QLabel)
        if label.isVisibleTo(final_nursery)
    }
    final_actions = [
        button.text()
        for button in final_nursery.findChildren(QPushButton)
        if button.isVisibleTo(final_nursery)
    ]
    assert "10 of 10 species discovered" in final_labels
    assert "30 of 93 collection entries discovered" in final_labels
    assert final_actions.count("View collection") == 1
    final_nursery.hide()
    assert_surface(fertilizer_selection, "Fertilizer selection")
    assert_surface(replacement, "Fertilizer replacement")
    assert_surface(story, "Plant Story")
    assert_surface(species, "Species overview")
    settings.tabs.setCurrentIndex(1)
    settings.report_details_toggle.setChecked(True)
    application.processEvents()
    assert_surface(settings, "Settings")

    progress.navigation.set_current("growth")
    assert_surface(progress, "Garden Progress Plant Growth")
    progress.navigation.set_current("collection")
    assert_surface(progress, "Collection")

    customize.prepare_to_show()
    assert_surface(customize, "Collection loadout details")

    assert set(natural_ranges) == {
        "Nursery",
        "Fertilizer selection",
        "Fertilizer replacement",
        "Plant Story",
        "Species overview",
        "Settings",
        "Garden Progress Plant Growth",
        "Collection",
        "Collection loadout details",
    }
    # On a normal logical desktop the matrix includes naturally short and
    # naturally overflowing bodies. A 200%-scale offscreen desktop exposes
    # only about 400 logical px of height, where every named surface may
    # legitimately need its one scroll owner even before forced-long content.
    available_height = application.primaryScreen().availableGeometry().height()
    if available_height >= 500:
        assert any(value == 0 for value in natural_ranges.values())
    assert any(value > 0 for value in natural_ranges.values())

    for timer in fertilizer_selection.findChildren(QTimer):
        timer.stop()
    dashboard.hide()
    owner.close()
    application.processEvents()
