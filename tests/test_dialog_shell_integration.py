from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "ankigarden" / "ui" / "dashboard.py"
STUDIO = ROOT / "ankigarden" / "ui" / "garden_studio.py"
CAPTURE = ROOT / "ankigarden" / "capture_ui_faces.py"


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


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text("utf-8")
    tree = ast.parse(source)
    owner = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    node = next(
        item
        for item in owner.body
        if isinstance(item, ast.FunctionDef) and item.name == method_name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def test_dialog_shell_owns_focus_escape_restoration_and_scroll_contracts() -> None:
    shell = _class_source(DASHBOARD, "DialogShell")
    assert "def focusNextPrevChild" in shell
    assert "focusable[(index + 1) % len(focusable)]" in shell
    assert "focusable[(index - 1) % len(focusable)]" in shell
    assert "Qt.Key.Key_Escape" in shell
    assert "QTimer.singleShot(0, restore)" in shell
    assert "QApplication.focusWidget()" in shell
    assert "def register_scroll_region" in shell
    assert "def register_pinned_footer" in shell
    assert "clearance = 0" in shell
    assert "base[3] + clearance" in shell
    assert "def active_vertical_scroll_regions" in shell
    assert "scroll.isVisibleTo(self)" in shell
    assert shell.count("scroll.window()") >= 3


def test_dialog_shell_applies_every_view_profile_through_one_central_path() -> None:
    apply_view = _method_source(
        DASHBOARD,
        "DialogShell",
        "apply_view_size_profile",
    )
    fit_content = _method_source(
        DASHBOARD,
        "DialogShell",
        "fit_content_to_family",
    )

    assert "dialog_height_profile(size_class, view_key)" in apply_view
    assert "self._dialog_view_key" in apply_view
    assert "self.setMinimumSize(minimum_width, minimum)" in apply_view
    assert "self.setMaximumSize(maximum_width, max(minimum, maximum))" in apply_view
    assert 'self.schedule_content_fit(' in apply_view
    assert '"view-profile"' in apply_view
    assert "QTimer.singleShot(0, self._recenter_over_parent)" in apply_view
    assert "dialog_height_profile(" in fit_content
    assert "self._dialog_view_key" in fit_content
    assert "height_profile.min_height" in fit_content
    assert "height_profile.max_height" in fit_content


def test_shared_dialog_state_supports_transaction_states_and_retry() -> None:
    dialog = _class_source(DASHBOARD, "GardenDialog")
    assert "DialogViewState.READY" in dialog
    assert "dialog_view_policy(state)" in dialog
    assert 'self.setProperty("dialogBusy", policy.busy)' in dialog
    assert 'self.setProperty("dialogFeedbackTone", policy.feedback_tone)' in dialog
    assert "policy.retryable and retry is not None" in dialog
    assert "if policy.assertive" in dialog
    assert 'retry_label: str = "Try again"' in dialog
    assert 'self.state_retry = QPushButton("Try again")' in dialog
    assert "AnnouncementPriority.ASSERTIVE" in dialog
    assert "text_column_width(" in dialog
    assert "setMaximumWidth(readable_header_width)" in dialog


def test_dialog_close_policy_is_opt_in_and_preserves_reject_overrides() -> None:
    shell = _class_source(DASHBOARD, "DialogShell")
    dialog = _class_source(DASHBOARD, "GardenDialog")

    assert "self._close_policy = DialogClosePolicy()" in shell
    assert "def configure_close_policy" in shell
    assert "def set_dialog_dirty" in shell
    assert "def set_dialog_in_flight" in shell
    assert "def evaluate_close_request" in shell
    assert "def confirm_dirty_close" in shell
    assert "def close_request_blocked" in shell
    assert "def request_close" in shell
    assert "self.reject()" in _method_source(DASHBOARD, "DialogShell", "request_close")
    assert "DialogCloseReason.WINDOW_CLOSE" in _method_source(
        DASHBOARD,
        "DialogShell",
        "closeEvent",
    )
    assert "DialogCloseReason.ESCAPE" in _method_source(
        DASHBOARD,
        "DialogShell",
        "keyPressEvent",
    )
    assert "DialogCloseReason.CLOSE_BUTTON" in shell
    assert 'top_close.setProperty("closeBlockedInFlight", protected)' in shell
    assert "create_inline_close_button" in shell
    assert "self.register_pinned_footer(self.footer)" in dialog


def test_settings_and_collection_detail_have_one_active_vertical_scroll_owner() -> None:
    settings = _class_source(DASHBOARD, "GardenSettingsDialog")
    shell_overflow = _method_source(
        DASHBOARD,
        "DialogShell",
        "_sync_overflow_owner",
    )
    studio = _class_source(STUDIO, "GardenStudioWidget")
    customize = _class_source(DASHBOARD, "CollectibleDetailDialog")
    option_page = _method_source(DASHBOARD, "CollectibleDetailDialog", "_option_page")
    studio_scroll = _method_source(STUDIO, "GardenStudioWidget", "_scroll_controls_to")

    assert "self.controls_scroll.setVerticalScrollBarPolicy(" in studio
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in studio
    assert "self.controls_scroll.verticalScrollBar()" not in studio_scroll
    assert "parent is not self.controls_scroll" in studio_scroll
    assert 'self.tabs.addTab(self.behavior_scroll, "Display")' in settings
    assert "self.tabs.addTab(advanced," in settings
    assert "scroll.isVisibleTo(self)" in shell_overflow
    assert "Qt.ScrollBarPolicy.ScrollBarAsNeeded" in shell_overflow
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in shell_overflow
    assert "self.body_scroll = QScrollArea()" in customize
    assert "QScrollArea" not in option_page
    assert "host = QWidget()" in option_page


def test_settings_technical_details_remeasure_after_narrow_rewrap() -> None:
    resize = _method_source(DASHBOARD, "GardenSettingsDialog", "resizeEvent")
    refresh = _method_source(
        DASHBOARD,
        "GardenSettingsDialog",
        "_refresh_debug_report",
    )
    sync_height = _method_source(
        DASHBOARD,
        "GardenSettingsDialog",
        "_sync_debug_report_height",
    )
    toggle = _method_source(
        DASHBOARD,
        "GardenSettingsDialog",
        "_toggle_debug_report",
    )

    assert "QTimer.singleShot(0, self._sync_debug_report_height)" in resize
    assert "self._sync_debug_report_height()" in refresh
    assert "self.debug_report.viewport().width()" in sync_height
    assert "max(320" not in sync_height
    assert "self.debug_report.setFixedHeight(report_height)" in sync_height
    assert "QTimer.singleShot(0, self._sync_debug_report_height)" in toggle


def test_fixed_footers_and_scroll_regions_are_registered_on_catalog_dialogs() -> None:
    purchase = _class_source(DASHBOARD, "PurchaseConfirmationDialog")
    nursery = _class_source(DASHBOARD, "NurseryDialog")
    dashboard = _class_source(DASHBOARD, "GardenDashboard")

    assert "self.register_scroll_region(self.content_scroll)" in purchase
    assert "self.register_pinned_footer(self.action_footer)" in purchase
    assert "self.register_pinned_footer(self.nursery_footer)" in nursery
    assert "self.register_scroll_region(scroll_region)" in nursery
    assert "dialog.register_scroll_region(options_scroll)" in dashboard
    assert "dialog.register_pinned_footer(footer_frame)" in dashboard


def test_capture_gate_rejects_nested_scroll_and_footer_clearance_failures() -> None:
    capture = CAPTURE.read_text("utf-8")
    assert '"multiple-active-vertical-scroll-regions"' in capture
    assert '"insufficient-footer-scroll-clearance"' in capture
    assert 'scroll.property("footerClearance")' in capture
    assert "footer.height()" in capture
    assert "dialog_scroll_geometry_issue_codes(" in capture


def test_semantic_size_classes_keep_confirmations_compact_and_previews_roomy() -> None:
    source = DASHBOARD.read_text("utf-8")
    expected = {
        "PurchaseConfirmationDialog": "DialogSizeClass.TRANSACTION",
        "PlantStoryDialog": "DialogSizeClass.PLANT_STORY",
        "StarterConfirmationDialog": "DialogSizeClass.COMPACT_STATUS",
        "NurseryDialog": "DialogSizeClass.NURSERY",
        "GardenProgressDialog": "DialogSizeClass.PROGRESS",
        "CollectibleDetailDialog": "DialogSizeClass.LOADOUT",
    }
    for class_name, size_class in expected.items():
        assert size_class in _class_source(DASHBOARD, class_name)
    assert "min(policy.max_width, screen_max_width)" in source
    starter = _class_source(DASHBOARD, "StarterConfirmationDialog")
    assert 'self.setProperty("actionMode", actions.mode)' in starter
    assert 'self.setProperty("summaryMode", summary.mode)' in starter
    assert 'self.setProperty("layoutMode", mode)' in starter
    assert "size=64" in starter
    assert 'floor=64' in starter
    assert 'floor=240' in starter
    assert "compact_direction=QBoxLayout.Direction.LeftToRight" in starter
    assert 'f"Adds {species_name} permanently.\\n"' in starter
    assert '"You can move the plant later."' in starter
    assert 'self.choose_action = QPushButton(f"Choose {species_name}")' in starter
    assert "Free permanent starter species" not in starter
    assert "Other species remain available in Nursery" not in starter


def test_named_detail_dialogs_use_content_fit_classes_and_view_profiles() -> None:
    shell = _method_source(
        DASHBOARD,
        "DialogShell",
        "set_content_bounded_maximum_height",
    )
    purchase = _class_source(DASHBOARD, "PurchaseConfirmationDialog")
    species = _method_source(
        DASHBOARD,
        "GardenDashboard",
        "_build_species_overview_dialog",
    )

    assert "natural_height + max(0, int(breathing_room))" in shell
    assert 'self.setProperty("contentNaturalHeight", natural_height)' in shell
    assert 'self.setProperty("contentBoundedMaximumHeight", bounded)' in shell
    assert "self.fit_content_to_family(" in purchase
    assert "breathing_room=8" in purchase
    assert "self.comparison_responsive.evaluate(available)" in purchase
    assert 'self.setProperty("comparisonMode", comparison.mode)' in purchase
    assert 'self.setProperty("decisionSummaryCondensed", False)' in purchase
    assert "self.content_scroll.show()" in purchase
    assert "preserve_transition=not self.presentation.terminal" in purchase
    assert "DialogSizeClass.SPECIES_DETAIL" in species
    assert 'dialog.apply_view_size_profile("default")' in species
    assert "preferred_height=720" not in species
    assert "dialog.set_content_bounded_maximum_height" not in species


def test_multi_view_dialogs_route_view_changes_through_shared_profiles() -> None:
    settings_tab = _method_source(
        DASHBOARD,
        "GardenSettingsDialog",
        "_sync_settings_tab",
    )
    diagnostics = _method_source(
        DASHBOARD,
        "GardenSettingsDialog",
        "_toggle_debug_report",
    )
    nursery = _method_source(DASHBOARD, "NurseryDialog", "_sync_catalog_intro")
    progress = _method_source(DASHBOARD, "GardenProgressDialog", "_page_changed")
    loadout = _method_source(DASHBOARD, "CollectibleDetailDialog", "__init__")
    plant_story = _method_source(DASHBOARD, "PlantStoryDialog", "__init__")
    species = _method_source(
        DASHBOARD,
        "GardenDashboard",
        "_build_species_overview_dialog",
    )

    for view_key in (
        "display",
        "advanced",
        "diagnostics-clean",
        "diagnostics-expanded",
    ):
        assert f'"{view_key}"' in settings_tab + diagnostics
    assert "self.apply_view_size_profile(" in settings_tab
    assert "self.apply_view_size_profile(" in diagnostics
    for view_key in ("starter", "plants", "fertilizer", "spaces", "weather", "empty"):
        assert f'"{view_key}"' in nursery
    assert "self.apply_view_size_profile(view_key)" in nursery
    assert (
        "self.apply_view_size_profile(self._view_profile_for_page(str(key)))"
        in progress
    )
    assert 'self.apply_view_size_profile("default")' in loadout
    assert "DialogSizeClass.PLANT_STORY" in plant_story
    assert 'self.apply_view_size_profile("default")' in plant_story
    assert "DialogSizeClass.SPECIES_DETAIL" in species
    assert 'dialog.apply_view_size_profile("default")' in species


def test_dialogs_do_not_override_small_screen_clamping_with_hard_window_minima() -> None:
    constructors = (
        ("GardenSettingsDialog", "DialogSizeClass.SETTINGS"),
        ("GardenDetailsDialog", "DialogSizeClass.STANDARD_TEXT"),
        ("GardenProgressDialog", "DialogSizeClass.PROGRESS"),
    )
    for class_name, size_class in constructors:
        constructor = _method_source(DASHBOARD, class_name, "__init__")
        assert "apply_size_policy(" in constructor
        assert size_class in constructor
        assert "self.setMinimumSize(" not in constructor

    species = _method_source(
        DASHBOARD,
        "GardenDashboard",
        "_build_species_overview_dialog",
    )
    fertilizer = _method_source(
        DASHBOARD,
        "GardenDashboard",
        "_open_fertilizer_menu",
    )
    assert "dialog.apply_size_policy(" in species
    assert "dialog.setMinimumSize(" not in species
    assert "dialog.apply_size_policy(" in fertilizer
    assert "dialog.setMinimumSize(" not in fertilizer


def test_nursery_open_releases_each_rebuilt_catalog_after_exec() -> None:
    opener = _method_source(DASHBOARD, "GardenDashboard", "_open_nursery")

    assert "dialog = NurseryDialog(self, self.engine, self.storage)" in opener
    assert "self.nursery_dialog = dialog" in opener
    assert "try:\n            result = dialog.exec()\n        finally:" in opener
    assert "if self.nursery_dialog is dialog:" in opener
    assert "self.nursery_dialog = None" in opener
    assert opener.index("dialog.hide()") < opener.index("dialog.setParent(None)")
    assert opener.index("dialog.setParent(None)") < opener.index("dialog.deleteLater()")


def test_content_fit_is_coalesced_and_publishes_native_capture_evidence() -> None:
    shell = _class_source(DASHBOARD, "DialogShell")
    schedule = _method_source(
        DASHBOARD,
        "DialogShell",
        "schedule_content_fit",
    )
    event_filter = _method_source(
        DASHBOARD,
        "DialogShell",
        "eventFilter",
    )
    fit = _method_source(
        DASHBOARD,
        "DialogShell",
        "fit_content_to_family",
    )
    telemetry = _method_source(
        DASHBOARD,
        "DialogShell",
        "_publish_capture_telemetry",
    )

    assert "self._content_fit_timer.setSingleShot(True)" in shell
    assert "if not self._content_fit_timer.isActive()" in schedule
    assert "merge_content_fit_preservation(" in schedule
    for event_name in (
        "LayoutRequest",
        "Show",
        "Hide",
        "FontChange",
        "StyleChange",
        "ContentsRectChange",
    ):
        assert f"QEvent.Type.{event_name}" in event_filter
    assert "watched is not self" in event_filter
    assert "should_preserve_transition_height(" in fit
    assert "self._content_fit_running" in fit
    for evidence in (
        "clientSurfaceFill",
        "nurseryRootOffset",
        "contentToFooterGap",
        "maximumActionWidthRatio",
        "scrollRangeMaximum",
        "scrollbarVisible",
        "renderedTextSizePx",
        "tooltipPresent",
    ):
        assert evidence in telemetry
