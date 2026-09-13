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
    shell = _class_source(DASHBOARD_PATH, "_ShellBehavior")
    dialog = _class_source(DASHBOARD_PATH, "_GardenContent")

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
    assert "self.behavior_scroll.viewport()" in settings
    assert "QBoxLayout.Direction.LeftToRight" in settings
    assert "QBoxLayout.Direction.TopToBottom" not in settings
    assert '"refresh-diagnostics"' in settings
    assert '"copy-report"' in settings
    assert 'self.report_details_toggle.setProperty("disclosureRow", True)' in settings


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
    for width in (960, 600):
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

        assert studio.controls.width() <= studio.controls_scroll.viewport().width()
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

        def update(self, payload: dict[str, Any]) -> None:
            self.data.update(deepcopy(payload))

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

        def activity_entries(self, **_kwargs: Any) -> tuple[Any, ...]:
            return ()

        def activity_day_totals(self, _day: str) -> dict[str, int]:
            return {}

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
    assert outcome.message == "Sunflower Seed added."
    assert project_collection(state).species_text == "10 of 10 species discovered"

    displaced = plants[1]
    displaced_slot = int(displaced.slot_index)
    assert engine.move_to_collection(displaced.plant_id)[0]
    owner = QWidget()
    collection_routes = []
    owner.open_section = lambda *args, **kwargs: collection_routes.append((args, kwargs))
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
    assert placement.nursery_toast.message.text() == "Added to your collection."
    assert placement.nursery_toast.action.text() == "Plant in garden"
    assert placement.nursery_toast.property("receiptPrimaryRoute") == "Plant in garden"
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
    assert no_bed.nursery_toast.message.text() == "Added to your collection. No empty bed is available."
    assert no_bed.nursery_toast.action.text() == "View in Collection"
    assert no_bed.nursery_toast.property("receiptPrimaryRoute") == "View in Collection"
    no_bed.nursery_toast.action.click()
    application.processEvents()
    assert collection_routes == [
        (("collection", "plants"), {"item_id": "sunflower", "plant_id": outcome.result_id}),
    ]
    assert sunflower.slot_index is None

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


@pytest.mark.parametrize("width", (640, 1040))
def test_live_qt_surface_breakpoints_are_stable_when_available(
    monkeypatch: pytest.MonkeyPatch, width: int,
) -> None:
    """Resize real current surfaces without depending on retired controllers."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import (
            FertilizerReplacementDialog, GardenDashboard, GardenSettingsDialog,
            NurseryDialog, PlantStoryDialog,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")
    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    storage.state.starter_selection_complete = True
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    surfaces = (
        FertilizerReplacementDialog(dashboard, engine, _live_replacement_quote(engine, storage)),
        PlantStoryDialog(dashboard, engine, "p1"),
        NurseryDialog(dashboard, engine, storage),
        GardenSettingsDialog(dashboard, engine, config),
    )
    try:
        for surface in surfaces:
            surface.show()
            surface.resize(width, 620)
            for _ in range(4):
                application.processEvents()
            for scroll in surface.active_vertical_scroll_regions():
                assert scroll.widget().width() <= scroll.viewport().width()
                assert scroll.horizontalScrollBar().maximum() == 0
            surface.hide()
        dashboard.show()
        dashboard.resize(width, 700)
        dashboard.open_section("collection", "plants")
        for _ in range(4):
            application.processEvents()
        workspace = dashboard.collection_plants_workspace
        assert workspace.species_page is not None
        assert workspace.selected_species == "bonsai"
        assert workspace.gallery.scroll.widget().width() <= workspace.gallery.scroll.viewport().width()
        if workspace._wide:
            assert workspace.rect().contains(workspace.detail_host.geometry())
            scroll = workspace.species_page.collection_scroll
            assert scroll.widget().width() <= scroll.viewport().width()
        else:
            workspace.show_species("bonsai")
            for _ in range(4):
                application.processEvents()
            assert workspace.detail_dialog is None
            assert workspace.detail_host.isVisibleTo(workspace)
            assert workspace.rect().contains(workspace.detail_host.geometry())
    finally:
        for surface in surfaces:
            surface.close()
        dashboard.close()
        owner.close()
        application.processEvents()


def test_live_qt_dashboard_does_not_adopt_nested_dialog_scrolls_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Share mounted page scrolls while keeping native Settings isolated."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QPoint, QWidget
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
    dashboard.open_section("progress", "today")
    application.processEvents()
    assert dashboard.workspace_stack.currentWidget() is progress
    assert progress.window() is dashboard
    progress_scroll = progress.body_scrolls["today"]
    assert dashboard.active_vertical_scroll_regions() == (progress_scroll,)
    assert progress_scroll.horizontalScrollBar().maximum() == 0
    assert dashboard.workspace_stack.contentsRect().contains(progress.geometry())

    dashboard._open_settings()
    application.processEvents()
    settings = dashboard.settings_dialog
    assert settings is not None and settings.isVisible()
    assert_owner_does_not_adopt(settings)
    # The footer is a layout sibling: it must not overlap the body or add a
    # second footer-height strip to the scrollable content.
    assert int(settings.behavior_scroll.property("footerClearance")) == 0
    body_bottom = (
        settings.behavior_scroll.mapTo(settings, QPoint(0, 0)).y()
        + settings.behavior_scroll.height()
    )
    footer_top = settings.footer.mapTo(settings, QPoint(0, 0)).y()
    assert body_bottom <= footer_top
    assert footer_top + settings.footer.height() <= settings.height()

    settings.hide()
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
    storage.state.garden_name = "Moss and Moon"
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

    assert dashboard.title_label.text() == "Anki Garden"
    assert dashboard.title_label.accessibleName() == "Anki Garden"
    assert dashboard.title_label.toolTip() == "Anki Garden"
    assert dashboard.windowTitle() == "Anki Garden"
    assert storage.state.garden_name == "Moss and Moon"
    assert dashboard.active_vertical_scroll_regions() == ()
    assert not hasattr(dashboard, "dashboard_scroll")
    assert int(origin.y()) >= 0
    assert scene_bottom <= int(viewport.height())
    assert int(origin.x()) >= 0
    assert int(origin.x()) + dashboard.scene.width() <= viewport.width()
    assert int(dashboard.scene.property("viewportHeightLimit")) >= int(
        dashboard.scene.minimumHeight()
    )

    dashboard.hide()
    owner.close()
    application.processEvents()


def test_live_qt_plant_popover_state_matrix_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep actions usable and Growth truthful across selected-plant states."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.ui.dashboard import PlantInfoCard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")
    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.show()
    card = PlantInfoCard(owner)
    base = dict(plant_id="rose", name="Rose Plant", species="rose", stage="sprout",
                next_stage="young", stage_points=0, stage_goal=2000, is_active=True,
                fully_grown=False, fertilizer_status={"phase": "inactive"}, asset=None,
                next_checkpoint_growth_remaining=100, next_checkpoint_base_coins=1)

    def settle(**changes: Any) -> None:
        card.set_selected({**base, **changes})
        card.resize(304, card.preferred_height(304))
        card.show()
        for _ in range(3):
            application.processEvents()
        assert card.content_scroll.horizontalScrollBar().maximum() == 0
        assert card.content_scroll.verticalScrollBar().maximum() == 0
        assert card.close_btn.isVisibleTo(card)
        assert not any(widget.isVisibleTo(card) and widget.property("fertilizerStatusBlock")
                       for widget in card.findChildren(QWidget))
        assert not any("checkpoint" in str(getattr(widget, "text", lambda: "")()).lower()
                       for widget in card.findChildren(QWidget))

    for current in (0, 1000, 2000):
        settle(stage_points=current)
        assert card.stage_progress.bar.value() == current
        assert card.stage_progress.value_label.text() == f"{current:,} / 2,000 Growth to Young"
        assert card.fertilize.isVisibleTo(card) and card.fertilize.isEnabled()
        assert any(action.text() == "Move" and action.isVisible() for action in card.more.menu().actions())
        assert card.story.isVisibleTo(card)
        assert card.more.isVisibleTo(card)
        assert not card.growth_charge.isVisibleTo(card)
    stable = card.fertilize.geometry()
    card.set_action_busy("fertilize", True)
    application.processEvents()
    assert card.fertilize.geometry() == stable
    card.set_action_busy("fertilize", False)
    settle(fertilizer_status={"phase": "active", "name": "Magical Fertilizer", "duration": "100 cards remaining"})
    assert card.status_value.text() == "Magical Fertilizer · 100 cards remaining"
    assert card.status_row.isVisibleTo(card)
    card.hide()
    settle(fertilizer_status={"phase": "active", "name": "Magical Fertilizer", "duration": "99 cards remaining"})
    assert card.status_value.text() == "Magical Fertilizer · 99 cards remaining"
    settle(name="An extraordinarily long name for this particular Rose Plant")
    assert card.heading.property("fullText") == "Rose Sprout"
    assert not card.artwork.pixmap().isNull()
    settle(is_active=False)
    assert card.nurture.isVisibleTo(card) and card.nurture.isEnabled()
    assert not card.fertilize.isVisibleTo(card)
    assert card.more.isVisibleTo(card)
    settle(fully_grown=True, is_active=False, stage="rare", next_stage=None)
    assert card.heading.property("fullText") == "Full Bloom Rose"
    assert not card.identity.isVisibleTo(card)
    assert not card.stage_progress.isVisibleTo(card)
    assert any(action.text() == "Choose another plant" and action.isVisible() for action in card.more.menu().actions())
    assert not card.nurture.isVisibleTo(card)
    settle()
    card.resize(304, 100)
    application.processEvents()
    assert card.close_btn.isVisibleTo(card)
    assert card.content_scroll.verticalScrollBar().maximum() > 0
    assert card.content_scroll.horizontalScrollBar().maximum() == 0
    card.set_selected(None)
    assert not card.isVisible()
    owner.close()


def test_live_qt_inspection_and_refresh_preserve_nurtured_plant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inspection, dismissal, and explicit nurture remain separate operations."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QLabel, QWidget, Qt
        from PyQt6.QtTest import QTest
        from ankigarden.ui.dashboard import GardenDashboard, GardenDialog
        from ankigarden.models.state import OnboardingStep, Plant
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")
    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    config.data["enable_animations"] = False
    storage.state.plants[0].slot_index = 0
    storage.state.plants.append(Plant("p2", "rose", "Rose Plant", 1))
    storage.state.starter_selection_complete = True
    storage.state.onboarding.step = OnboardingStep.DONE
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard.show()

    def settle() -> None:
        for _ in range(4):
            application.processEvents()

    try:
        settle()
        bar = dashboard.nurtured_plant_bar
        assert bar.plant_id == "p1"
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        target = dashboard.scene.plant_geometry("p2").center().toPoint()
        QTest.mouseMove(dashboard.scene, target)
        settle()
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        QTest.mouseClick(dashboard.scene, Qt.MouseButton.LeftButton, pos=target)
        settle()
        assert dashboard.plant_card.isVisibleTo(dashboard)
        assert dashboard.plant_card.plant_id == "p2"
        assert bar.plant_id == storage.state.active_plant_id == "p1"
        dashboard.refresh_all()
        settle()
        assert dashboard.plant_card.plant_id == "p2" and bar.plant_id == "p1"
        assert dashboard.plant_card.content_scroll.horizontalScrollBar().maximum() == 0
        assert dashboard.plant_card.content_scroll.verticalScrollBar().maximum() == 0
        dashboard.plant_card.close_btn.click()
        dashboard.refresh_all()
        settle()
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        target = dashboard.scene.plant_geometry("p1").center().toPoint()
        QTest.mouseClick(dashboard.scene, Qt.MouseButton.LeftButton, pos=target)
        settle()
        QTest.mouseClick(dashboard.scene, Qt.MouseButton.LeftButton, pos=target)
        settle()
        assert dashboard.scene.selected_plant_id() == "p1"
        assert dashboard.plant_card.isVisibleTo(dashboard)
        menu = dashboard.plant_card.more.menu()
        menu.popup(dashboard.plant_card.more.mapToGlobal(dashboard.plant_card.more.rect().bottomLeft()))
        settle()
        QTest.keyClick(menu, Qt.Key.Key_Escape)
        assert dashboard.scene.selected_plant_id() == "p1"

        def close_owned_dialog(dialog: Any) -> int:
            dialog.show()
            settle()
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            assert dashboard.scene.selected_plant_id() == "p1"
            return 0

        monkeypatch.setattr(GardenDialog, "exec", close_owned_dialog)
        QTest.mouseClick(dashboard.plant_card.story, Qt.MouseButton.LeftButton)
        settle()
        assert dashboard._workspace_section == "collection"
        assert dashboard.collection_plants_workspace.selected_species == "bonsai"
        assert dashboard.collection_plants_workspace.detail_dialog is None
        dashboard.open_section("garden")
        dashboard.scene.keep_card_open("p1")
        dashboard._on_scene_selection("p1")
        settle()
        assert dashboard.plant_card.isVisibleTo(dashboard)
        QTest.mouseClick(dashboard.plant_card.fertilize, Qt.MouseButton.LeftButton)
        settle()
        assert dashboard.plant_card.isVisibleTo(dashboard)
        next(action for action in dashboard.plant_card.more.menu().actions() if action.text() == "Move").trigger()
        settle()
        assert dashboard.scene._interaction.placing
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        QTest.keyClick(dashboard.scene, Qt.Key.Key_Escape)
        settle()
        assert not dashboard.scene._interaction.placing
        assert dashboard.plant_card.isVisibleTo(dashboard)
        QTest.keyClick(dashboard.scene, Qt.Key.Key_Escape)
        settle()
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        QTest.keyClick(dashboard.scene, Qt.Key.Key_Return)
        settle()
        assert dashboard.plant_card.isVisibleTo(dashboard)
        dashboard.scene.keep_card_open("p2")
        dashboard.plant_card.nurture.click()
        settle()
        assert bar.plant_id == storage.state.active_plant_id == "p2"
        dashboard._undo_nurture()
        settle()
        assert bar.plant_id == storage.state.active_plant_id == "p1"
        dashboard.open_section("collection")
        assert dashboard.scene.selected_plant_id() is None
        dashboard.open_section("garden")
        dashboard.refresh_all()
        settle()
        assert not dashboard.plant_card.isVisibleTo(dashboard)
        engine.set_active_plant(None)
        dashboard.refresh_all()
        settle()
        assert not bar.plant_id and bar.heading.text() == "No plant is being nurtured"
        target = dashboard.scene.plant_geometry("p1").center().toPoint()
        QTest.mouseClick(dashboard.scene, Qt.MouseButton.LeftButton, pos=target)
        settle()
        assert dashboard.plant_card.isVisibleTo(dashboard)
        assert storage.state.active_plant_id is None
        # Plant supplies can create its helper without loading Shop catalogs.
        shop = dashboard._shop
        assert shop is not None
        assert shop.catalog_layout.count() == shop.supplements_layout.count() == 0
        dashboard.open_section("shop", "supplies", plant_id="p2")
        assert shop.catalog_layout.count() == shop.upgrades_layout.count() == 0
        assert shop.supply_context.isHidden()  # Inspection does not choose a fertilizer target.
        first_catalog = shop.supplements_layout.itemAt(0).widget()
        dashboard.open_section("garden")
        dashboard.open_section("shop", "supplies", plant_id="p2")
        assert shop.supplements_layout.itemAt(0).widget() is first_catalog
        dashboard._mark_progress_pages_dirty()
        dashboard.open_section("shop", "supplies", plant_id="p2")
        assert shop.supplements_layout.itemAt(0).widget() is not first_catalog
        assert shop.catalog_layout.count() == shop.upgrades_layout.count() == 0
    finally:
        dashboard.close()
        owner.close()
        settle()



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
    settings.diagnostics_toggle.setChecked(True)
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

    assert wide_height >= 100
    assert narrow_height >= wide_height
    assert narrow_height <= 220 < required_height
    assert (
        settings.debug_report.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    report_scroll = settings.debug_report.verticalScrollBar()
    assert report_scroll.maximum() > 0
    report_scroll.setValue(report_scroll.maximum())
    assert report_scroll.value() == report_scroll.maximum()
    regions = settings.active_vertical_scroll_regions()
    assert len(regions) == 1
    outer_scroll = regions[0]
    assert settings.report_actions_panel.width() <= outer_scroll.viewport().width()
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

    assert 1 <= navigation._rail_columns < len(labels)
    assert navigation.rail.property("navigationRows") == 2
    assert navigation.rail.height() >= (
        2 * next(iter(navigation.buttons.values())).height() + navigation.rail_layout.verticalSpacing()
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
    """Current modal surfaces retain one scroll owner and reachable footers."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QAbstractScrollArea, QLabel, QPoint, Qt, QWidget
        from ankigarden.ui.dashboard import (
            DialogShell, GardenDashboard, GardenSettingsDialog,
            PlantStoryDialog,
        )
        from ankigarden.capture.runtime import _UiFaceCaptureRunner
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    storage.state.consumables.update(fertilizer_basic=2, growth_charge_small=2)
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)
    dashboard.show()
    auditor = _UiFaceCaptureRunner.__new__(_UiFaceCaptureRunner)
    checked = set()

    def settle() -> None:
        for _ in range(3):
            application.processEvents()

    def assert_surface(dialog: Any, label: str) -> None:
        dialog.show()
        settle()
        dialog.resize(dialog.width(), max(1, dialog.minimumHeight()))
        settle()
        owners = tuple(region for region in dialog.findChildren(QAbstractScrollArea)
            if region.window() is dialog and region.isVisibleTo(dialog)
            and region.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        assert len(owners) == 1, (label, owners)
        scroll = owners[0]
        assert dialog.active_vertical_scroll_regions() == (scroll,), label
        assert not auditor._find_geometry_layout_warnings(dialog), (label, [row["kind"] for row in auditor._find_geometry_layout_warnings(dialog)])

        def assert_footer() -> None:
            footer = dialog._pinned_footer
            if footer is None or not footer.isVisible():
                return
            viewport = scroll.viewport()
            viewport_bottom = viewport.mapTo(dialog, QPoint(0, viewport.height())).y()
            assert viewport_bottom <= footer.mapTo(dialog, QPoint(0, 0)).y() + 1, label

        assert_footer()
        content = scroll.widget()
        extra_rows = [QLabel(f"Additional report detail {index + 1}.", content) for index in range(60)]
        for extra in extra_rows:
            content.layout().addWidget(extra)
        content.updateGeometry()
        settle()
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0, label
        bar.setValue(bar.maximum())
        settle()
        assert bar.value() == bar.maximum(), label
        content_bottom = content.mapTo(scroll.viewport(), content.rect().bottomLeft()).y()
        assert abs(content_bottom - (scroll.viewport().height() - 1)) <= 2, label
        assert_footer()
        # The capture scenario's row inventory describes the original body.
        # Check the actual added final row directly in this long-content case.
        final_row = extra_rows[-1]
        top = final_row.mapTo(scroll.viewport(), QPoint(0, 0)).y()
        assert top >= 0 and top + final_row.height() <= scroll.viewport().height(), label
        for extra in extra_rows:
            content.layout().removeWidget(extra)
            extra.setParent(None)
            extra.deleteLater()
        bar.setValue(0)
        dialog.hide()
        settle()
        checked.add(label)

    # Inspect Plant supplies while its public modal handler owns the dialog;
    # it now disposes the dialog when exec returns.
    def inspect_supplies(dialog: Any) -> int:
        assert_surface(dialog, "Plant supplies")
        return 0

    monkeypatch.setattr(DialogShell, "exec", inspect_supplies)
    surfaces = []
    try:
        dashboard._open_fertilizer_menu("p1")
        assert dashboard.fertilizer_dialog is None
        species = dashboard._build_species_overview_dialog("bonsai", parent=dashboard)
        assert species is not None
        settings = GardenSettingsDialog(dashboard, engine, config)
        settings.tabs.setCurrentIndex(1)
        settings.report_details_toggle.setChecked(True)
        surfaces = [(PlantStoryDialog(dashboard, engine, "p1"), "Plant story"),
                    (species, "Species overview"), (settings, "Settings")]
        for dialog, label in surfaces:
            assert_surface(dialog, label)
        assert checked == {"Plant supplies", "Plant story", "Species overview", "Settings"}
    finally:
        for dialog, _label in surfaces:
            dialog.close()
        dashboard.close()
        owner.close()
        settle()


@pytest.mark.parametrize("scale", (1.0, 1.5, 2.0))
@pytest.mark.parametrize("width", (380, 1040))
def test_live_welcome_and_trophies_keep_text_and_actions_reachable(
    monkeypatch: pytest.MonkeyPatch, scale: float, width: int,
) -> None:
    """Exercise actual enlarged widget fonts, including the compact viewport."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QLabel, QPushButton, QWidget
        from ankigarden.models.welcome import WelcomeReceipt, WelcomeReward
        from ankigarden.ui.trophy_room import TrophyRoomPage
        from ankigarden.ui.welcome import WelcomeCard
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    _config, _storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(width, 600)
    owner.show()
    welcome = WelcomeCard(owner, lambda: None, engine)
    welcome.set_receipt(WelcomeReceipt(
        gift_rewards=(WelcomeReward("gift-growth", "growth", 100),
                      WelcomeReward("gift-coins", "coins", 50)),
        history_review_count=5000,
        history_rewards=(WelcomeReward("history-coins", "coins", 135),
                         WelcomeReward("history-small", "inventory_item", 1, "growth_charge_small"),
                         WelcomeReward("history-standard", "inventory_item", 1, "growth_charge_standard")),
        achievement_ids=("first", "second", "third", "fourth"),
    ))
    trophies = TrophyRoomPage(engine, lambda: None)
    trophies.resize(width, 600)
    try:
        for surface in (welcome, trophies):
            surface.ensurePolished()
            for widget in (*surface.findChildren(QLabel), *surface.findChildren(QPushButton)):
                base = max(12, widget.fontMetrics().height() - 2)
                widget.setStyleSheet(f"font-size:{round(base * scale)}px;")
            surface.show()
        welcome._toggle_details()
        for _ in range(4):
            application.processEvents()
            welcome.reposition()
            trophies.showcase._reflow()
            trophies._sync_header()
        assert owner.rect().contains(welcome.geometry())
        for button in (welcome.close_button, welcome.view_rewards):
            assert welcome.rect().contains(button.geometry())
        assert welcome.view_rewards.height() >= welcome.view_rewards.fontMetrics().height()
        assert welcome.details.widget().width() <= welcome.details.viewport().width()
        assert trophies.widget().width() <= trophies.viewport().width()
        assert trophies.horizontalScrollBar().maximum() == 0
        for surface in (welcome, trophies):
            for label in surface.findChildren(QLabel):
                if not label.isVisible() or not label.text() or not label.wordWrap():
                    continue
                required = label.heightForWidth(label.width())
                assert label.height() + 2 >= required, label.text()
        welcome.details.verticalScrollBar().setValue(welcome.details.verticalScrollBar().maximum())
        trophies.verticalScrollBar().setValue(trophies.verticalScrollBar().maximum())
        assert welcome.start_gardening.text() == "Start gardening"
        assert "rewards are already saved" in welcome.start_gardening.accessibleDescription()
    finally:
        welcome.close()
        trophies.close()
        owner.close()
        application.processEvents()


@pytest.mark.parametrize("ending", ("complete", "skip", "escape", "hide", "disable_motion", "dismiss"))
def test_live_welcome_reveal_settles_and_recovers_without_replaying(
    monkeypatch: pytest.MonkeyPatch, ending: str,
) -> None:
    """Every exit from the reward reveal restores a usable, fully visible receipt."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QWidget
        from ankigarden.models.state import GardenState
        from ankigarden.ui.dashboard import GardenDashboard
        from ankigarden.ui import welcome as welcome_module
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    storage.state = GardenState()
    engine = type(engine)(config, storage)
    if ending == "complete":
        from ankigarden.ui.dashboard import GardenSettingsDialog

        settings_owner = QWidget()
        settings = GardenSettingsDialog(settings_owner, engine, config)
        settings.garden_name_edit.setText("My first garden")
        settings.save_settings.click()
        assert storage.state.garden_name == "My first garden"
        assert storage.state.garden_setup_version == 0
        settings.close()
        settings_owner.close()
    ok, _, plant = engine.choose_starter("bonsai")
    assert ok and engine.set_active_plant(plant.plant_id)[0]
    assert engine.finish_onboarding()[0]
    balances = storage.state.currency_balance, plant.growth_points
    assert balances == (51, 100)
    now = [100.0]
    monkeypatch.setattr(welcome_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    owner = QWidget()
    dashboard = GardenDashboard(owner, engine, storage, config)
    try:
        dashboard.show()
        application.processEvents()
        welcome = dashboard.welcome
        dashboard.scene.scene["motion_enabled"] = True
        welcome.maybe_present()
        assert welcome.timer.isActive()
        now[0] += 2.8
        welcome.timer.timeout.emit()
        assert welcome.card.isVisible()
        if ending == "complete":
            now[0] += 1.0
            welcome.timer.timeout.emit()
        elif ending == "skip":
            welcome.skip.click()
        elif ending == "escape":
            assert welcome.handle_escape()
        elif ending == "hide":
            dashboard.hide()
            dashboard.show()
            application.processEvents()
        elif ending == "disable_motion":
            dashboard.scene.scene["motion_enabled"] = False
            welcome.timer.timeout.emit()
        else:
            welcome.card.start_gardening.click()
        assert not welcome.timer.isActive()
        assert welcome.card.graphicsEffect() is None
        assert welcome.card.isVisible() == (ending != "dismiss")
        assert dashboard.nurtured_plant_bar.progress.value() == 10000
        dashboard.hide()
        dashboard.show()
        application.processEvents()
        assert not welcome.timer.isActive()
        assert welcome.card.isVisible() == (ending != "dismiss")
        assert (storage.state.currency_balance, plant.growth_points) == balances
    finally:
        dashboard.close()
        owner.close()
        application.processEvents()


def test_live_toggle_retains_help_and_state_after_keyboard_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, Qt
        from PyQt6.QtTest import QTest
        from ankigarden.ui.controls import GardenToggleSwitch
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")
    application = QApplication.instance() or QApplication([])
    switch = GardenToggleSwitch("Reward notifications")
    switch.setAccessibleDescription("Show new rewards while studying.")
    switch.show()
    try:
        switch.setFocus()
        application.processEvents()
        for expected in (True, False):
            QTest.keyClick(switch, Qt.Key.Key_Space)
            assert switch.isChecked() is expected
            assert "Show new rewards while studying." in switch.accessibleDescription()
            assert switch.accessibleDescription().endswith("On." if expected else "Off.")
        switch.setEnabled(False)
        assert "Show new rewards while studying." in switch.accessibleDescription()
    finally:
        switch.close()
        application.processEvents()
