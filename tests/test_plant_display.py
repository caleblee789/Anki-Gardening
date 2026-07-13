from pathlib import Path

import pytest

from ankigarden.ui.plant_display import (
    PlantInteractionState,
    achievement_progress_display,
    compact_plant_layout,
    growth_display,
    hit_test,
    plant_health_display,
    plant_layout,
    plant_layout_item,
    settings_layout_is_compact,
    smart_card_rect,
)
from ankigarden.models.state import Achievement, DailyStats, GardenState


@pytest.mark.parametrize(
    ("points", "stage", "next_stage", "remaining"),
    [
        (0, "seed", "sprout", 80),
        (79, "seed", "sprout", 1),
        (80, "sprout", "young", 140),
        (899, "mature", "flowering", 1),
        (900, "flowering", "rare", 500),
    ],
)
def test_growth_display_reports_next_stage(points, stage, next_stage, remaining):
    display = growth_display(points)
    assert display.stage == stage
    assert display.next_stage == next_stage
    assert display.points_remaining == remaining
    assert 0.0 <= display.progress <= 1.0


def test_growth_display_handles_fully_grown_and_rare_override():
    grown = growth_display(1400)
    rare = growth_display(12, rare_variant=True)
    assert grown.fully_grown is True
    assert grown.next_stage is None
    assert grown.progress == 1.0
    assert rare.stage == "rare"
    assert rare.fully_grown is True


@pytest.mark.parametrize(
    ("width", "compact"),
    [(0, True), (640, True), (719, True), (720, False), (920, False)],
)
def test_settings_layout_breakpoint_is_deterministic(width, compact):
    assert settings_layout_is_compact(width) is compact


def test_growth_display_sanitizes_invalid_points():
    assert growth_display("bad").stage == "seed"
    assert growth_display(-20).points_remaining == 80


def test_growth_display_exposes_plain_language_stage_progress():
    display = growth_display(105)
    assert display.stage_points == 25
    assert display.stage_goal == 140


@pytest.mark.parametrize(
    ("vitality", "label", "percent"),
    [(1.0, "Thriving", 100), (0.84, "Healthy", 84), (0.64, "Needs care", 64)],
)
def test_plant_health_display_uses_plain_language_states(vitality, label, percent):
    display = plant_health_display(vitality)
    assert display.label == label
    assert display.percent == percent


def test_achievement_progress_adapter_exposes_numeric_criteria_without_schema_changes():
    state = GardenState(streak_days=5, total_reviews=412, daily_stats=DailyStats(reviewed=18, correct=16, wrong=2))
    streak = achievement_progress_display(Achievement("streak_7", "Rhythm", ""), state)
    retention = achievement_progress_display(Achievement("retention_90", "Recall", ""), state)
    total = achievement_progress_display(Achievement("reviews_1000_total", "Roots", ""), state)

    assert (streak.current, streak.target, streak.value_text) == (5, 7, "5 / 7 days")
    assert retention.value_text == "89 / 90% accuracy; 18 / 20 reviews"
    assert (total.current, total.target) == (412, 1000)


def test_layout_is_responsive_and_hit_areas_are_generous():
    rows = plant_layout(760, 320, 3)
    assert len(rows) == 3
    assert all(row.hit.width >= row.visible.width and row.hit.height >= row.visible.height for row in rows)
    assert hit_test(rows, rows[1].visible.x + rows[1].visible.width / 2, rows[1].depth - 20) == 1
    assert hit_test(rows, -100, -100) is None


def test_layout_handles_empty_and_narrow_scenes():
    assert plant_layout(400, 300, 0) == []
    row = plant_layout(200, 180, 1)[0]
    assert row.visible.x >= 0
    assert row.visible.right <= 200


def test_two_plants_stay_in_the_compositional_center():
    rows = plant_layout(900, 360, 2)
    centers = sorted(row.visible.x + row.visible.width / 2 for row in rows)
    assert centers == pytest.approx([370.1664, 529.8336])
    assert rows[0].depth == pytest.approx(rows[1].depth)


def test_declared_ground_anchor_lands_on_scene_baseline():
    placement = {
        "visible_bounds": [0.1, 0.3, 0.8, 0.55],
        "ground_anchor": [0.47, 0.82],
        "display_scale": 0.8,
    }
    row = plant_layout(900, 500, [{"slot_index": 0, "placement": placement}])[0]
    anchor_x = row.draw.x + row.draw.width * placement["ground_anchor"][0]
    anchor_y = row.draw.y + row.draw.height * placement["ground_anchor"][1]
    assert anchor_x == pytest.approx(row.footprint.x + row.footprint.width / 2)
    assert anchor_y == pytest.approx(row.depth)
    assert row.footprint.y + row.footprint.height / 2 == pytest.approx(row.depth)


def test_contact_shadow_uses_asset_specific_grounded_dimensions():
    placement = {
        "visible_bounds": [0.1, 0.1, 0.8, 0.85],
        "ground_anchor": [0.5, 0.95],
        "display_scale": 0.8,
        "base_type": "pot",
        "contact_shadow": [0.46, 0.045],
    }
    row = plant_layout(900, 500, [{"slot_index": 0, "placement": placement}])[0]

    assert row.footprint.width == pytest.approx(row.visible.width * 0.46)
    assert row.footprint.height == pytest.approx(max(3.0, row.visible.height * 0.045))
    assert row.footprint.y < row.depth < row.footprint.bottom


def test_resolved_asset_placement_is_promoted_before_dashboard_layout():
    placement = {
        "visible_bounds": [0.063, 0.4992, 0.8676, 0.3517],
        "ground_anchor": [0.4968, 0.8509],
        "contact_shadow": [0.64, 0.045],
        "base_type": "pot",
    }
    item = plant_layout_item({"plant_id": "bonsai", "asset": {"path": "bonsai.png", "placement": placement}}, 2)

    assert item["slot_index"] == 2
    assert item["placement"] == placement
    assert item["placement"] is not placement


@pytest.mark.parametrize("count", [1, 2, 4, 6])
def test_compact_layout_keeps_all_plants_grounded_and_visible(count):
    plants = [
        {"slot_index": index, "placement": {
            "visible_bounds": [0.08, 0.04, 0.84, 0.92],
            "ground_anchor": [0.5, 0.96],
            "display_scale": 0.7,
        }}
        for index in range(count)
    ]
    rows = compact_plant_layout(1000, 420, plants)
    assert len(rows) == count
    assert all(0 <= row.visible.x < row.visible.right <= 1000 for row in rows)
    assert all(0 <= row.visible.y < row.visible.bottom <= 420 for row in rows)


@pytest.mark.parametrize("size", [(420, 315), (760, 570), (1200, 900), (1600, 900), (320, 240)])
@pytest.mark.parametrize("count", range(1, 7))
def test_natural_composition_geometry_is_safe(size, count):
    width, height = size
    plants = [{"slot_index": index, "placement": {"visible_bounds": [0.08, 0.04, 0.84, 0.92]}}
              for index in range(count)]
    rows = plant_layout(width, height, plants)
    assert len(rows) == count
    assert [row.depth for row in rows] == sorted(row.depth for row in rows)
    for row in rows:
        assert row.visible.x >= 0 and row.visible.y >= 0
        assert row.visible.right <= width and row.visible.bottom <= height
        assert row.hit.x <= row.visible.x and row.hit.y <= row.visible.y
        assert row.hit.right >= row.visible.right and row.hit.bottom >= row.visible.bottom
    motion_extrema = [row.visible.expanded(max(6, row.visible.width * .08), max(3, row.visible.height * .04)) for row in rows]
    assert all(not left.intersects(right) for index, left in enumerate(motion_extrema) for right in motion_extrema[index + 1:])


def test_smart_card_is_constrained_to_scene_edges():
    for anchor_x in (20, 380, 740):
        x, y, width, height = smart_card_rect(760, 320, anchor_x, 250)
        assert 0 <= x <= 760 - width
        assert 0 <= y <= 320 - height


@pytest.mark.parametrize("size", [(150, 150), (220, 160), (252, 184)])
def test_smart_card_shrinks_to_unusually_small_scenes(size):
    width, height = size
    x, y, card_width, card_height = smart_card_rect(width, height, width / 2, height / 2)
    assert x >= 0 and y >= 0
    assert x + card_width <= width
    assert y + card_height <= height


def test_hover_pin_transfer_and_dismissal():
    state = PlantInteractionState()
    state.hover("rose")
    assert state.active_id == "rose"
    state.toggle_pin("rose")
    state.hover("fern")
    assert state.active_id == "rose"
    state.toggle_pin("fern")
    assert state.active_id == "fern"
    state.dismiss()
    assert state.active_id is None


def test_keyboard_focus_cycles_and_reconciles_removed_plants():
    state = PlantInteractionState()
    ids = ["rose", "fern", "bonsai"]
    assert state.cycle_focus(ids, 1) == "rose"
    assert state.cycle_focus(ids, -1) == "bonsai"
    state.toggle_pin("bonsai")
    state.reconcile(["rose"])
    assert state.pinned_id is None
    assert state.focused_index == 0


def test_keyboard_placement_cycles_confirms_and_cancels():
    state = PlantInteractionState()
    assert state.begin_placement("rose", 0, [0, 1, 2], keyboard=True)
    assert state.cycle_destination([0, 1, 2], 1) == 1
    assert state.complete_placement() == ("rose", 1)
    assert state.placing is False
    state.begin_placement("rose", 1, [0, 1, 2], keyboard=True)
    state.cancel_placement()
    assert state.complete_placement() is None


def test_invalid_placement_destination_is_not_selected():
    state = PlantInteractionState()
    state.begin_placement("rose", 0, [0, 1], keyboard=False)
    assert state.choose_destination(4, [0, 1]) is False
    assert state.destination_slot == 0


def test_dashboard_uses_scene_cards_instead_of_bottom_roster():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "_plant_scene_payload" in dashboard
    assert '"points_remaining"' in dashboard
    assert "roster_grid" not in dashboard
    assert "_refresh_roster_cards" not in dashboard
    assert "Nurture selected plant" not in dashboard
    assert "plant_interaction_hint_seen" in dashboard


def test_dashboard_is_garden_first_with_compact_secondary_tabs():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "root.addWidget(hero_card)" in dashboard
    assert 'self.daily_progress = LabeledProgress("Daily growth")' in dashboard
    assert 'self.milestone_progress = LabeledProgress("Next plant choice")' in dashboard
    assert "self.details_tabs = QTabWidget()" in dashboard
    assert 'self.details_tabs.addTab(self.quest_list' in dashboard
    assert 'self.quest_list = ProgressList("Quest progress")' in dashboard
    assert "self.hero_summary" not in dashboard
    assert "self.streak_chip" not in dashboard


def test_selected_state_and_contact_shadow_share_the_ground_footprint():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert "painter.drawEllipse(footprint.adjusted(-10, -4, 10, 4))" in scene
    assert "painter.drawEllipse(footprint)" in scene
    assert "footprint.translate" not in scene


def test_nurtured_plant_does_not_add_a_second_scene_highlight():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert "_draw_nurture_badge" not in scene
    render_loop = scene.split("def paintEvent", 1)[1].split("def _draw_status_overlay", 1)[0]
    assert "is_focus" not in render_loop


def test_keyboard_move_cycles_places_and_cancels_without_losing_selection():
    state = PlantInteractionState()
    assert state.begin_placement("rose", 0, [0, 1, 2], keyboard=True)
    assert state.cycle_destination([0, 1, 2], 1) == 1
    assert state.complete_placement() == ("rose", 1)
    assert not state.placing
    assert state.pinned_id == "rose"
    assert state.begin_placement("rose", 1, [0, 1, 2], keyboard=True)
    state.cancel_placement()
    assert not state.placing
    assert state.pinned_id == "rose"


def test_statistics_help_is_explicit_hidden_and_keyboard_focusable():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert 'setAccessibleName("About garden statistics")' in scene
    assert "self._stats_help_visible = False" in scene
    assert "self._draw_stats_help(painter, r)" in scene
    assert "self._stats_help_button.clicked.connect(self._focus_stats_help)" in scene
    assert "QEvent.Type.Enter, QEvent.Type.FocusIn" in scene
    assert "QToolTip" not in scene


def test_plants_have_no_idle_or_drag_lift_transforms():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    for retired in ("sway =", "pulse_alpha", "_transition_scale", "scale(1.06", "base_y - 8", "for i in range(16)"):
        assert retired not in scene
    assert "painter.setOpacity(0.78)" in scene
    assert "painter.translate(target_x - x, target_y - base_y)" in scene


def test_dashboard_exposes_accessible_plant_story_and_inline_rename():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "class PlantStoryDialog(QDialog):" in dashboard
    assert 'setAccessibleName("Plant memory timeline")' in dashboard
    assert 'setAccessibleName("Rename plant")' in dashboard
    assert "More memories will appear as this plant grows." in dashboard
    assert "event.key() == Qt.Key.Key_Escape" in dashboard
    assert "self.engine.rename_plant" in dashboard
    assert "self.scene.storyRequested.connect(self._open_plant_story)" in dashboard


def test_dialog_class_boundaries_keep_appearance_ui_out_of_story_refresh():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    settings_block = dashboard.split("class GardenSettingsDialog", 1)[1].split("class PlantStoryDialog", 1)[0]
    story_block = dashboard.split("class PlantStoryDialog", 1)[1].split("class GardenDashboard", 1)[0]
    assert "GardenStudioWidget(self.config" in settings_block
    assert "self.engine.resolve_preview_assets" in settings_block
    assert "GardenStudioWidget(" not in story_block
    assert "asset_resolver=engine" not in story_block


def test_placement_rejects_invalid_targets_and_reconciles_removed_plants():
    state = PlantInteractionState()
    assert state.begin_placement("rose", 0, [0, 1], keyboard=False)
    assert not state.choose_destination(3, [0, 1])
    assert state.choose_destination(1, [0, 1])
    state.reconcile(["bonsai"])
    assert not state.placing
    assert state.pinned_id is None


def test_settings_expose_daily_goal_home_visibility_and_transaction_errors():
    root = Path(__file__).resolve().parents[1]
    studio = (root / "ankigarden/ui/garden_studio.py").read_text()
    dashboard = (root / "ankigarden/ui/dashboard.py").read_text()
    assert '"daily_goal": self.daily_goal.value()' in studio
    assert '"show_home_widget": self.show_home_widget.isChecked()' in studio
    assert "behavior_scroll.setWidgetResizable(True)" in dashboard
    assert 'QPushButton("Save settings")' in dashboard
    assert 'QPushButton("Restore defaults")' in dashboard
    assert '"Garden settings"' in dashboard
    assert "except ConfigError as exc:" in dashboard
    assert "QMessageBox.warning" not in dashboard
    assert 'self.save_status.setText("Saved")' in dashboard
    assert 'self.save_status.setText("Unsaved changes")' in dashboard
    assert "self.behavior.reset_preview_defaults()" in dashboard
    assert "self.config.update(old_payload)" in dashboard
    assert "self.particle_slider.setRange(20, 125)" in studio
    assert "self._update_motion_controls" in studio
    assert 'return "Standard"' in studio


def test_dashboard_compact_action_bar_and_inline_move_guidance_are_real_controls():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert 'self.nurturing_pill = QLabel("Nurturing")' in dashboard
    assert 'self.nurture = QPushButton("Nurture")' in dashboard
    assert 'self.move = QPushButton("Move")' in dashboard
    assert 'self.story = QPushButton("Story")' in dashboard
    assert 'move_title = QLabel("Move a plant")' in dashboard
    assert "Press Enter to place, Escape to cancel, or Undo after the move." in dashboard
    assert 'self.cancel_move = QPushButton("Cancel move")' in dashboard
    assert "QMessageBox.information(\n            self,\n            \"How to use the garden\"" not in dashboard
    assert "Selected-plant details and real keyboard-focusable actions" in scene


def test_settings_sections_and_preview_only_controls_match_persistence_contract():
    studio = (Path(__file__).resolve().parents[1] / "ankigarden/ui/garden_studio.py").read_text()
    for title in ("Appearance", "Motion and weather", "Progress", "Anki integration", "Preview only"):
        assert f'"{title}"' in studio
    assert "These demonstration controls update the preview and are never saved." in studio
    assert '"weather"' not in studio.split("def build_theme_payload", 1)[1].split("def _normalize_theme", 1)[0]
    assert '"growth_stage"' not in studio.split("def build_theme_payload", 1)[1].split("def _normalize_theme", 1)[0]
    assert '"animations_label": "Animate weather"' in studio
    assert '"animation_label": "Weather motion"' in studio


def test_future_features_records_layered_foliage_motion_without_shipping_it():
    root = Path(__file__).resolve().parents[1]
    backlog = (root / "docs/future-features.md").read_text()
    docs_index = (root / "docs/README.md").read_text()
    assert "Layered foliage wind animation" in backlog
    assert "pot, soil mound, and stem base fixed" in backlog
    assert "future-features.md" in docs_index


def test_supported_ui_copy_does_not_restore_retired_boost_language():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "inventory boosts" not in dashboard.lower()
    assert "No collected garden items yet." in dashboard


def test_dashboard_uses_explicit_main_window_refresh_after_mutations():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "self.mw_window = mw_window" in dashboard
    assert "def refresh_external_surfaces" in dashboard
    assert "parent.parent()" not in dashboard
    assert dashboard.count("self.refresh_external_surfaces()") >= 4
