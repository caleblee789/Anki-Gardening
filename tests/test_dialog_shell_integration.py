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
    assert "base[3] + clearance" in shell
    assert "def active_vertical_scroll_regions" in shell
    assert shell.count("scroll.window()") >= 3


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
    assert "DialogCloseReason.CLOSE_BUTTON" in dialog
    assert 'top_close.setProperty("closeBlockedInFlight", protected)' in dialog
    assert "self.register_pinned_footer(self.footer)" in dialog


def test_settings_and_collection_detail_have_one_active_vertical_scroll_owner() -> None:
    studio = _class_source(STUDIO, "GardenStudioWidget")
    customize = _class_source(DASHBOARD, "CollectibleDetailDialog")
    option_page = _method_source(DASHBOARD, "CollectibleDetailDialog", "_option_page")
    studio_scroll = _method_source(STUDIO, "GardenStudioWidget", "_scroll_controls_to")

    assert "self.controls_scroll.setVerticalScrollBarPolicy(" in studio
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in studio
    assert "self.controls_scroll.verticalScrollBar()" not in studio_scroll
    assert "parent is not self.controls_scroll" in studio_scroll
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
        "PurchaseConfirmationDialog": "DialogSizeClass.COMPARISON",
        "PlantStoryDialog": "DialogSizeClass.STANDARD_TEXT",
        "StarterConfirmationDialog": "DialogSizeClass.COMPACT_CONFIRMATION",
        "NurseryDialog": "DialogSizeClass.CATALOG",
        "GardenProgressDialog": "DialogSizeClass.CATALOG",
            "CollectibleDetailDialog": "DialogSizeClass.PREVIEW",
    }
    for class_name, size_class in expected.items():
        assert size_class in _class_source(DASHBOARD, class_name)
    assert "self.setMaximumSize(policy.max_width, policy.max_height)" in source
    starter = _class_source(DASHBOARD, "StarterConfirmationDialog")
    assert 'self.setProperty("actionMode", actions.mode)' in starter
    assert 'self.setProperty("summaryMode", summary.mode)' in starter
    assert 'self.setProperty("layoutMode", mode)' in starter
    assert "size=64" in starter
    assert 'floor=64' in starter
    assert 'floor=240' in starter
    assert "compact_direction=QBoxLayout.Direction.LeftToRight" in starter
    assert 'f"Species: {species_name}\\n"' in starter
    assert '"Species choice is permanent.\\n"' in starter


def test_short_detail_dialogs_use_targeted_content_bounded_height_caps() -> None:
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
    assert "minimum_height=self._comparison_policy_minimum_height" in purchase
    assert "breathing_room=6" in purchase
    assert "compact = comparison.mode == COMPACT_MODE" in purchase
    assert "660 if comparison.mode == COMPACT_MODE else 561" in purchase
    assert "and int(width) >= 760" in purchase
    assert "and not self.presentation.terminal" in purchase
    assert "preferred = max(535, bounded)" in purchase
    assert "dialog.set_content_bounded_maximum_height(540)" in species


def test_dialogs_do_not_override_small_screen_clamping_with_hard_window_minima() -> None:
    constructors = (
        ("GardenSettingsDialog", "DialogSizeClass.CATALOG"),
        ("GardenDetailsDialog", "DialogSizeClass.STANDARD_TEXT"),
        ("GardenProgressDialog", "DialogSizeClass.CATALOG"),
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
