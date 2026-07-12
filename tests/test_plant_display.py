from pathlib import Path

import pytest

from ankigarden.ui.plant_display import (
    PlantInteractionState,
    growth_display,
    hit_test,
    plant_layout,
    smart_card_rect,
)


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


def test_growth_display_sanitizes_invalid_points():
    assert growth_display("bad").stage == "seed"
    assert growth_display(-20).points_remaining == 80


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


def test_dashboard_uses_scene_cards_instead_of_bottom_roster():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "_plant_scene_payload" in dashboard
    assert '"points_remaining"' in dashboard
    assert "roster_grid" not in dashboard
    assert "_refresh_roster_cards" not in dashboard


def test_dashboard_is_garden_first_with_compact_secondary_tabs():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "root.addWidget(hero_card, 4)" in dashboard
    assert "self.details_tabs = QTabWidget()" in dashboard
    assert 'self.details_tabs.addTab(self.quest_list' in dashboard
    assert "self.hero_summary" not in dashboard
    assert "self.streak_chip" not in dashboard
