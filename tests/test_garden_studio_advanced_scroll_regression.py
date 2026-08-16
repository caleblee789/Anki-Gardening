from __future__ import annotations

import ast
import os
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


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


class _OuterScroll(_Recorder):
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
def test_advanced_expansion_grows_the_non_scrolling_viewport_in_both_modes(
    compact: bool,
) -> None:
    finish_update = _compiled_finish_method()
    studio = _Studio(compact=compact)

    finish_update(studio, True)

    assert studio.controls_scroll.viewport_height == 572
    assert ("setMinimumHeight", (572,)) in studio.controls_scroll.calls
    assert ("updateGeometry", ()) in studio.controls_scroll.calls
    assert (
        "ensureWidgetVisible",
        (studio.advanced_panel, 12, 12),
    ) in studio.outer_scroll.calls


def test_nursery_scroll_regions_have_stable_accessible_names() -> None:
    nursery = _class_source(DASHBOARD_PATH, "NurseryDialog")

    for name in (
        "Plants catalog",
        "Fertilizer and Boosters catalog",
        "Garden Spaces catalog",
        "Weather and Scenery catalog",
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


def test_settings_troubleshooting_actions_reflow_from_their_own_viewport() -> None:
    settings = _class_source(DASHBOARD_PATH, "GardenSettingsDialog")

    assert '"settings.troubleshooting-actions"' in settings
    assert "self.troubleshooting_scroll.viewport()" in settings
    assert "QBoxLayout.Direction.TopToBottom" in settings
    assert "QBoxLayout.Direction.LeftToRight" in settings
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
            StarterConfirmationDialog,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    owner = QWidget()
    owner.resize(1400, 900)
    owner.show()
    dashboard = GardenDashboard(owner, engine, storage, config)

    starter = StarterConfirmationDialog(dashboard, engine, "rose")
    replacement = FertilizerReplacementDialog(
        dashboard,
        current_name="Basic Fertilizer",
        current_effect="+1 Growth per answer",
        remaining_time="59 minutes",
        new_name="Magical Fertilizer",
        new_effect="+3 Growth per answer",
        cost=150,
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
        "Fertilizer and Boosters catalog",
        "Garden Spaces catalog",
        "Weather and Scenery catalog",
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
            "starter",
            starter,
            ((starter.actions_responsive, "starter-actions"),),
            (447, 449),
            "layoutMode",
            "wide",
        ),
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
            ((customize.customize_responsive, "customize-workspace"),),
            (867, 869),
            "workspaceMode",
            "compact",
        ),
    )

    shared_controllers = (
        settings.report_actions_responsive,
        dashboard.collection_filter_responsive,
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

    dashboard._fertilizer_timer.stop()
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
    dashboard._fertilizer_timer.stop()
    dashboard.hide()
    owner.close()
    application.processEvents()


def test_live_qt_settings_details_rewrap_to_full_height_when_available(
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

    assert narrow_height > wide_height
    assert narrow_height >= required_height
    assert (
        settings.debug_report.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
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


def test_live_qt_named_dialog_scroll_and_footer_contracts_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise every release scroll owner at natural and forced-long heights."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QAbstractScrollArea, QPoint, QTimer, Qt, QWidget
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
        current_name="Basic Fertilizer",
        current_effect="+1 Growth per answer",
        remaining_time="59 minutes",
        new_name="Magical Fertilizer",
        new_effect="+3 Growth per answer",
        cost=150,
    )
    story = PlantStoryDialog(dashboard, engine, "p1")
    nursery = NurseryDialog(dashboard, engine, storage)
    species = dashboard._build_species_overview_dialog(
        "bonsai",
        parent=dashboard,
    )
    assert species is not None
    settings = GardenSettingsDialog(dashboard, engine, config)
    progress = dashboard.progress_dialog
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
    for index, expected_name in enumerate(
        (
            "Plants catalog",
            "Fertilizer and Boosters catalog",
            "Garden Spaces catalog",
            "Weather and Scenery catalog",
        )
    ):
        nursery.catalog_tabs.setCurrentIndex(index)
        application.processEvents()
        application.processEvents()
        assert active_region(nursery, f"Nursery tab {index}").accessibleName() == expected_name
        assert not capture_auditor._find_geometry_layout_warnings(nursery), expected_name
    nursery.hide()
    assert_surface(fertilizer_selection, "Fertilizer selection")
    assert_surface(replacement, "Fertilizer replacement")
    assert_surface(story, "Plant Story")
    assert_surface(species, "Species overview")
    settings.tabs.setCurrentIndex(1)
    settings.report_details_toggle.setChecked(True)
    application.processEvents()
    assert_surface(settings, "Settings")

    progress.navigation.set_current("overview")
    assert_surface(progress, "Garden Progress overview")
    progress.navigation.set_current("collection")
    assert_surface(progress, "Collection")

    customize.prepare_to_show()
    assert_surface(customize, "Customize Garden")

    assert set(natural_ranges) == {
        "Nursery",
        "Fertilizer selection",
        "Fertilizer replacement",
        "Plant Story",
        "Species overview",
        "Settings",
        "Garden Progress overview",
        "Collection",
        "Customize Garden",
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
    dashboard._fertilizer_timer.stop()
    dashboard.hide()
    owner.close()
    application.processEvents()
