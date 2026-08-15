from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _relative_luminance(color: str) -> float:
    value = color.removeprefix("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _theme_scope() -> dict[str, object]:
    return runpy.run_path(str(ROOT / "ankigarden/ui/theme.py"))


def test_button_targets_and_shared_state_contract_are_consistent() -> None:
    scope = _theme_scope()
    stylesheet = scope["button_stylesheet"]()

    assert scope["BUTTON_MIN_HEIGHT"] == 44
    assert scope["COMPACT_BUTTON_HEIGHT"] == 40
    assert scope["PLANT_ACTION_MIN_HEIGHT"] == 44
    assert scope["ICON_BUTTON_SIZE"] == 44
    assert scope["SCENE_HELP_BUTTON_SIZE"] == 44
    assert "QPushButton {" in stylesheet
    assert "min-height: 44px" in stylesheet
    assert "QPushButton[variant='primary']" in stylesheet
    assert "QPushButton[variant='secondary']" in stylesheet
    assert "QPushButton[variant='tertiary']" in stylesheet
    assert "QPushButton:disabled" in stylesheet
    assert "QPushButton:focus" in stylesheet


def test_action_text_keeps_wcag_aa_contrast_in_every_interaction_state() -> None:
    palette = _theme_scope()["GARDEN_THEME"]
    combinations = (
        (palette["action_text"], palette["action_accent"]),
        (palette["action_text"], palette["action_hover"]),
        (palette["action_text"], palette["action_pressed"]),
        (palette["text_primary"], palette["secondary_action"]),
        (palette["text_primary"], palette["secondary_hover"]),
        (palette["text_primary"], palette["secondary_pressed"]),
        (palette["disabled_text"], palette["disabled_surface"]),
    )

    assert all(_contrast(foreground, background) >= 4.5 for foreground, background in combinations)


def test_home_and_native_actions_share_the_same_visual_roles() -> None:
    home = (ROOT / "ankigarden/ui/home_widget.py").read_text("utf-8")
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")
    studio = (ROOT / "ankigarden/ui/garden_studio.py").read_text("utf-8")

    assert "min-height:44px !important" in home
    assert "background:#5CC58B" in home
    assert "background:#71D39C" in home
    assert "outline:3px solid #82E2AC" in home
    assert "button.setFixedSize(84, BUTTON_MIN_HEIGHT)" in dashboard
    assert "_set_button_variant(copy_debug, BUTTON_VARIANT_SECONDARY)" in dashboard
    assert "min-height:44px; max-height:44px; min-width:44px" in dashboard
    assert "tool_button_stylesheet()" in studio


def test_metric_cards_use_adaptive_height_without_compressing_text_rows() -> None:
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")
    stats = dashboard.split("class GardenStatsStrip", 1)[1].split(
        "class RearrangeBar", 1
    )[0]

    assert "growth_layout.addLayout(growth_heading)" in stats
    assert "growth_layout.addLayout(growth_identity)" in stats
    assert "growth_layout.addWidget(self.growth_support)" in stats
    assert "streak_layout.addWidget(self.streak_support)" in stats
    assert "currency_layout.addWidget(self.currency_support)" in stats
    assert "QLabel(METRIC_AFFORDANCE)" not in stats
    assert "cell.setMinimumHeight(96)" in stats
    assert "growth_layout.setContentsMargins(16, 10, 16, 11)" in stats
    assert "growth_layout.setSpacing(5)" in stats
    assert "growth_bar.setFixedHeight(10)" in stats
    assert "self.growth_support.setWordWrap(True)" in stats
    assert "self.streak_support.setWordWrap(True)" in stats
    assert "self.currency_support.setWordWrap(True)" in stats
    assert stats.count("setMinimumWidth(0)") >= 3
    assert stats.count("QSizePolicy.Policy.Ignored") >= 3
    assert "stretches = (1, 1, 1, 1)" in stats
    assert "def _sync_header_minimum_heights" in dashboard
    assert "64 if guided else (96 if metrics_compact else 104)" in dashboard
    assert "self.garden_stats_bar.setFixedHeight" not in dashboard


def test_minimum_width_layouts_reserve_space_for_long_copy_and_actions() -> None:
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split(
        "class MemoryTimeline", 1
    )[0]

    assert "self.top_bar.setMinimumHeight(minimum)" in dashboard
    assert "154 if self._header_narrow_layout else" in dashboard
    assert "128 if self._header_compact_layout else" in dashboard
    assert "168 if self._header_compact_layout and metrics_compact else" in dashboard
    assert "top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)" in dashboard
    assert "self.top_bar.setFixedHeight" not in dashboard
    assert "self.feedback_panel.hide()" in dashboard
    assert "self._sync_feedback_panel_visibility()" in dashboard
    assert dashboard.count("QSizePolicy.Policy.Maximum") >= 8
    assert "self.title_stack_widget.setMinimumWidth(0)" in dashboard
    assert "self.title_label.setMinimumWidth(0)" in dashboard
    assert "self.top_bar.adjustSize()" in dashboard
    assert "self.header_grid.addWidget(self.garden_stats_bar" in dashboard
    assert "compact = int(width) < 700" in settings
    assert "self.settings_footer_grid.addWidget(self.cancel_settings, 0, 0)" in settings
    assert "self.settings_footer_grid.addWidget(self.save_settings, 0, 1)" in settings
    assert "garden_name_panel.setMinimumHeight(96)" in settings


def test_capture_manifest_records_native_text_geometry_warnings() -> None:
    capture = (ROOT / "ankigarden/capture_ui_faces.py").read_text("utf-8")

    assert "def _find_text_layout_warnings" in capture
    assert "metrics.tightBoundingRect" in capture
    assert "available_height = max(1, int(candidate.height()))" in capture
    assert "QAbstractScrollArea" in capture
    assert "scroll_ancestor = candidate.parentWidget()" in capture
    assert "checks_paint_boundary" in capture
    assert "ancestor_clip_vertical" in capture
    assert "candidate.mapTo(" in capture
    assert '"text_layout_warnings": text_layout_warnings' in capture
    assert '"text_layout_warnings": self._text_layout_warnings' in capture


def test_tabs_and_form_controls_do_not_fall_back_to_platform_gray() -> None:
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")

    assert "QTabBar {{ background:{t['dialog_surface']}" in dashboard
    assert "background:#10241f" in dashboard
    assert "QLineEdit, QTextEdit" in dashboard
    assert "QScrollBar::handle:vertical" in dashboard
    assert '"Fertilizer and Boosters"' in dashboard
