from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "ankigarden" / "ui" / "dashboard.py"
CAPTURE = ROOT / "ankigarden" / "capture_ui_faces.py"


def _method_source(class_name: str, method_name: str) -> str:
    source = DASHBOARD.read_text("utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    return ast.get_source_segment(source, method) or ""


def test_collection_no_matches_keeps_one_filter_action_and_sparse_profile() -> None:
    refresh = _method_source("GardenDashboard", "_refresh_collection_list")
    page_changed = _method_source("GardenProgressDialog", "_page_changed")
    profile = _method_source("GardenProgressDialog", "_view_profile_for_page")
    capture = CAPTURE.read_text("utf-8")

    assert "action=clear_filters" not in refresh
    assert 'self.collection_list.setProperty("emptyResult", is_empty)' in refresh
    assert "progress_dialog._view_profile_for_page" in refresh
    assert "self._view_profile_for_page(str(key))" in page_changed
    assert '"collection-empty"' in profile
    assert 'annotation.get("empty_state_actions") == []' in capture
    assert 'annotation.get("filter_clear_visible", False)' in capture


def test_compound_achievements_render_complete_conditions_without_one_axis_bar() -> None:
    refresh = _method_source("GardenDashboard", "_refresh_achievement_list")

    assert "len(condition_lines) > 1" not in refresh
    assert "line != projection.criteria_text" in refresh
    assert '"compoundConditionsVisible"' in refresh
    assert "for condition_line in condition_lines" in refresh
    assert 'conditions.setProperty("achievementConditions", True)' in refresh
    assert "elif not progress_conditions:" in refresh


def test_odd_achievement_cards_span_the_category_row_only_when_opted_in() -> None:
    source = DASHBOARD.read_text("utf-8")
    grid = source.split("class ProgressCardGrid", 1)[1].split(
        "class ResponsiveTileGrid", 1
    )[0]

    assert "span_singleton_rows: bool = False" in grid
    assert "self._span_singleton_rows = bool(span_singleton_rows)" in grid
    assert "next_is_boundary" in grid
    assert "and self._columns == 2" in grid
    assert 'widget.setProperty("spansSingletonRow", spans_singleton_row)' in grid
    assert '"Achievement progress", span_singleton_rows=True' in source
    assert '"Collectible collection",' in source
    assert "wide_columns=4" in source
    assert "minimum_item_width=180" in source
    assert "minimum_card_height=224" in source

    capture = CAPTURE.read_text("utf-8")
    assert 'candidate.property("spansSingletonRow")' in capture
    assert '"singleton_span_cards"' in capture
    assert '"singleton_spans_passed"' in capture
    assert 'annotation.get("achievement_grid_columns", 0)' in capture
    assert 'dashboard._achievement_filter = "completed"' in capture
    assert 'dashboard._achievement_filter = "in_progress"' in capture
    assert 'annotation.get("achievement_filter") == "completed"' in capture
    assert 'annotation.get("achievement_filter") == "in_progress"' in capture


def test_reset_streak_uses_first_positive_bonus_but_keeps_zero_percent_row() -> None:
    streak = _method_source("GardenDetailsDialog", "_refresh_streak")

    assert "positive_bonus_tiers = tuple(" in streak
    assert "if percent > 0" in streak
    assert "display_bonus_tiers = tuple(STREAK_BONUS_TIERS)" in streak
    assert "if days > 0 and days_to_next > 0:" in streak
    assert "f\"{'+' if percent > 0 else ''}{percent}% Growth\"" in streak


def test_collection_cards_use_truthful_total_and_separate_readable_captions() -> None:
    refresh = _method_source("GardenDashboard", "_refresh_collection_list")

    assert (
        'f"{collected} of {len(registry_views)} collectibles collected"'
        in refresh
    )
    assert 'format_status_label(highest_stage)' in refresh
    assert '_plant_count(len(instances)) if collected_species else ""' in refresh
    assert "layout.addWidget(stage_copy)" in refresh
    assert "layout.addWidget(instances_copy)" in refresh
    assert "minimum_card_height=224" in DASHBOARD.read_text("utf-8")
    assert '"Clear filters to see all collectibles."' in refresh


def test_species_and_environment_actions_are_compact_normal_flow_actions() -> None:
    species = _method_source("GardenDashboard", "_build_species_overview_dialog")
    environment = _method_source("GardenDashboard", "_environment_collection_card")
    metadata = _method_source("GardenDashboard", "_collection_environment_metadata")

    assert '"collected" if collected else "uncollected"' in species
    assert 'empty_footer.setProperty("speciesUncollectedFooter", True)' in species
    assert "empty_footer_layout.addStretch(1)" in species
    assert "nursery.setMaximumWidth(140)" in species
    assert "actions = QHBoxLayout()" in environment
    assert "actions.addStretch(1)" in environment
    assert "BUTTON_VARIANT_PRIMARY if owned" not in environment
    assert 'f"Available every day\\nOnly one {kind} can be equipped"' in metadata
    for backend_copy in ("Duration:", "Stacking:", "Replacement:"):
        assert backend_copy not in metadata
