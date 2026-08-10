from pathlib import Path
import json

import pytest

from ankigarden.ui.plant_display import (
    CURRENT_ONBOARDING_VERSION,
    PlantInteractionState,
    Rect,
    achievement_progress_display,
    bed_badge_rect,
    compact_plant_layout,
    chronological_memories,
    growth_display,
    hit_test,
    move_badge_label,
    move_target_state,
    onboarding_display,
    plant_layout,
    plant_layout_item,
    requires_native_destination_selector,
    settings_layout_is_compact,
    smart_card_rect,
)
from ankigarden.models.state import Achievement, DailyStats, GardenState, PlantMemory


def _release_background(manifest: dict) -> dict:
    matches = [
        row for row in manifest["assets"]
        if row.get("category") == "backgrounds"
        and row.get("release_preferred") is True
    ]
    assert [row["asset_id"] for row in matches] == [
        "bg_verdant_twilight_any_soil_master_v6"
    ]
    return matches[0]


@pytest.mark.parametrize(
    ("points", "stage", "next_stage", "remaining"),
    [
        (0, "seed", "sprout", 500),
        (499, "seed", "sprout", 1),
        (500, "sprout", "young", 2_000),
        (7_999, "young", "mature", 1),
        (20_000, "flowering", "rare", 30_000),
    ],
)
def test_growth_display_reports_next_stage(points, stage, next_stage, remaining):
    display = growth_display(points)
    assert display.stage == stage
    assert display.next_stage == next_stage
    assert display.points_remaining == remaining
    assert 0.0 <= display.progress <= 1.0


def test_growth_display_handles_fully_grown_without_parallel_rare_override():
    grown = growth_display(50_000)
    assert grown.fully_grown is True
    assert grown.next_stage is None
    assert grown.progress == 1.0


@pytest.mark.parametrize(
    ("width", "compact"),
    [(0, True), (640, True), (719, True), (720, False), (920, False)],
)
def test_settings_layout_breakpoint_is_deterministic(width, compact):
    assert settings_layout_is_compact(width) is compact


def test_growth_display_sanitizes_invalid_points():
    assert growth_display("bad").stage == "seed"
    assert growth_display(-20).points_remaining == 500


def test_growth_display_exposes_plain_language_stage_progress():
    display = growth_display(1_000)
    assert display.stage_points == 500
    assert display.stage_goal == 2_000


def test_achievement_progress_adapter_exposes_numeric_criteria_without_schema_changes():
    state = GardenState(streak_days=5, total_reviews=412, daily_stats=DailyStats(reviewed=18, correct=16, wrong=2))
    streak = achievement_progress_display(Achievement("streak_7", "Rhythm", ""), state)
    retention = achievement_progress_display(Achievement("retention_90", "Recall", ""), state)
    total = achievement_progress_display(Achievement("reviews_1000_total", "Roots", ""), state)

    assert (streak.current, streak.target, streak.value_text) == (5, 7, "5 of 7 Anki days")
    assert retention.value_text == "89 of 90% accuracy; 18 of 20 card answers"
    assert (total.current, total.target) == (412, 1000)


def test_onboarding_stages_first_review_and_nurture_without_schema_state():
    fresh = onboarding_display(0, 0)
    reviewed = onboarding_display(1, 0)
    updated_existing_user = onboarding_display(1, CURRENT_ONBOARDING_VERSION - 1)
    completed = onboarding_display(1, CURRENT_ONBOARDING_VERSION)
    confirmation = onboarding_display(1, CURRENT_ONBOARDING_VERSION, just_completed=True)

    assert fresh.action_label == "Return to studying"
    assert "first card" in fresh.message
    assert reviewed.title == "Choose a plant to nurture"
    assert "Nurture" in reviewed.message
    assert "future card answers" in reviewed.message
    assert updated_existing_user.visible is True
    assert completed.visible is False
    assert confirmation.title == "Your garden is ready"


def test_story_memories_are_chronological_and_stable_within_the_same_day():
    planted = PlantMemory("planted", "planted", "2026-08-08")
    first_nurture = PlantMemory("nurture:first", "first_nurture", "2026-08-08")
    earlier = PlantMemory("reviews:10", "reviews", "2026-08-07", value=10)

    ordered = chronological_memories([planted, first_nurture, earlier])

    assert [memory.memory_id for memory in ordered] == [
        "reviews:10", "planted", "nurture:first",
    ]


def test_onboarding_handles_malformed_presentation_inputs() -> None:
    display = onboarding_display("not-a-count", "not-a-version")

    assert display.visible is True
    assert display.title == "Grow your first plant"


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


def test_move_destinations_always_remain_in_scene_at_compact_sizes():
    roomy = plant_layout(1200, 700, 6)
    narrow = plant_layout(480, 320, 6)

    assert requires_native_destination_selector(roomy, 1200, 700, range(6)) is False
    assert requires_native_destination_selector(narrow, 480, 320, range(6)) is False


def test_registered_beds_keep_fixed_physical_surfaces_for_every_count():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    background = _release_background(manifest)
    placement = background["placement"]
    one = plant_layout(640, 480, [{"slot_index": 0}], placement, composition_count=1)
    two = plant_layout(640, 480, [{"slot_index": 0}, {"slot_index": 1}], placement, composition_count=2)
    three = plant_layout(
        640, 480, [{"slot_index": 0}, {"slot_index": 1}, {"slot_index": 2}],
        placement, composition_count=3,
    )
    one_by_slot = {row.slot_index: row for row in one}
    two_by_slot = {row.slot_index: row for row in two}
    three_by_slot = {row.slot_index: row for row in three}

    assert one[0].depth == pytest.approx(one[0].base_rect.bottom)
    assert one_by_slot[0].surface_id == two_by_slot[0].surface_id == three_by_slot[0].surface_id == "far_left_soil_bed"
    assert two_by_slot[1].surface_id == three_by_slot[1].surface_id == "far_right_soil_bed"
    assert three_by_slot[2].surface_id == "middle_left_soil_bed"
    assert [row.surface_kind for row in three] == ["soil", "soil", "soil"]
    assert all(row.allowed_base_types == ("direct_soil",) for row in three)


def test_storybook_profiles_use_registered_source_soil_contact_coordinates():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    background = _release_background(manifest)
    placement = background["placement"]
    profile = placement["layout_profiles"]["16:9"]

    row = plant_layout(800, 450, [{"slot_index": 0}], placement, composition_count=1)[0]

    registered = profile["compositions"]["1"][0]
    assert row.ground_anchor[0] / 800 == pytest.approx(registered["x"], abs=0.002)
    assert row.depth / 450 == pytest.approx(
        registered["y"] + registered["seating_depth"], abs=0.002
    )
    assert row.grounding.support_line
    assert profile["coordinate_space"] == "source"
    assert profile["surface_variant"] == "16:9"


def test_empty_logical_beds_do_not_shrink_or_collide_with_visible_plants():
    visible = {"slot_index": 0, "placement": {"display_scale": 0.9}, "occupied": True}
    empty = [
        {"slot_index": slot, "placement": {"display_scale": 2.0}, "occupied": False}
        for slot in range(1, 6)
    ]
    only = plant_layout(800, 450, [visible], composition_count=1)[0]
    with_empty = next(
        row for row in plant_layout(800, 450, [visible, *empty], composition_count=1)
        if row.slot_index == 0
    )

    assert with_empty.draw == only.draw
    assert with_empty.effective_scale == pytest.approx(only.effective_scale)


def test_unlocking_preserves_surface_identity_and_each_count_is_deterministic():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    background = _release_background(manifest)
    placement = background["placement"]
    first_two = {row.slot_index: row for row in plant_layout(900, 360, 2, placement)}
    first_two_again = {row.slot_index: row for row in plant_layout(900, 360, 2, placement)}
    all_six = {row.slot_index: row for row in plant_layout(900, 360, 6, placement)}

    assert set(first_two) == {0, 1}
    assert first_two == first_two_again
    assert all(first_two[slot].surface_id == all_six[slot].surface_id for slot in first_two)
    assert first_two[0].depth == pytest.approx(first_two[1].depth)
    assert first_two[0].bed_footprint.x < first_two[1].bed_footprint.x


def test_dashboard_and_explicit_home_profiles_preserve_logical_slot_identity():
    plants = [
        {"slot_index": index, "placement": {
            "visible_bounds": [0.1, 0.06, 0.8, 0.9],
            "ground_anchor": [0.5, 0.96],
            "display_scale": 0.76,
        }}
        for index in range(6)
    ]
    dashboard = {row.slot_index: row for row in plant_layout(1000, 420, plants)}
    home = {row.slot_index: row for row in compact_plant_layout(1000, 420, plants)}

    assert dashboard.keys() == home.keys()
    assert [row.slot_index for row in sorted(dashboard.values(), key=lambda row: row.slot_index)] == list(range(6))
    assert [row.slot_index for row in sorted(home.values(), key=lambda row: row.slot_index)] == list(range(6))
    assert home == {row.slot_index: row for row in compact_plant_layout(1000, 420, plants)}


def test_declared_ground_anchor_lands_on_scene_baseline():
    placement = {
        "visible_bounds": [0.1, 0.3, 0.8, 0.55],
        "ground_anchor": [0.47, 0.82],
        "display_scale": 0.8,
    }
    row = plant_layout(900, 500, [{"slot_index": 0, "placement": placement}])[0]
    anchor_x = row.draw.x + row.draw.width * placement["ground_anchor"][0]
    anchor_y = row.draw.y + row.draw.height * placement["ground_anchor"][1]
    assert anchor_x == pytest.approx(row.draw.x + row.draw.width * placement["ground_anchor"][0])
    assert anchor_y == pytest.approx(row.depth)
    assert anchor_y == pytest.approx(row.depth)


def test_semantic_soil_contact_overrides_trailing_art_bottom():
    placement = {
        "visible_bounds": [0.08, 0.04, 0.84, 0.94],
        "ground_anchor": [0.5, 0.98],
        "art_bounds": [0.08, 0.04, 0.84, 0.94],
        "base_bounds": [0.32, 0.66, 0.36, 0.18],
        "foliage_bounds": [0.08, 0.04, 0.84, 0.94],
        "soil_contact": [0.5, 0.84],
        "interaction_bounds": [0.06, 0.02, 0.88, 0.97],
        "display_scale": 1.0,
    }
    row = plant_layout(900, 500, [{"slot_index": 0, "placement": placement}])[0]

    assert row.draw.y + row.draw.height * placement["soil_contact"][1] == pytest.approx(row.depth)
    assert row.base_rect.bottom == pytest.approx(row.depth)
    assert row.foliage_rect.bottom > row.depth  # trailing leaves do not alter grounding


def test_active_state_does_not_change_physical_scale_or_soil_anchor():
    placement = {"visible_bounds": [0.1, 0.06, 0.8, 0.9], "ground_anchor": [0.5, 0.96], "display_scale": 0.8}
    normal = compact_plant_layout(1000, 420, [{"slot_index": 0, "placement": placement}])[0]
    focused = compact_plant_layout(1000, 420, [{"slot_index": 0, "placement": placement, "is_active": True}])[0]

    assert focused.effective_scale == pytest.approx(normal.effective_scale)
    assert focused.depth == pytest.approx(normal.depth)
    assert focused.draw.y + focused.draw.height * placement["ground_anchor"][1] == pytest.approx(focused.depth)


def test_contact_shadow_uses_asset_specific_grounded_dimensions():
    placement = {
        "visible_bounds": [0.1, 0.1, 0.8, 0.85],
        "ground_anchor": [0.5, 0.95],
        "display_scale": 0.8,
        "base_type": "pot",
        "contact_shadow": [0.46, 0.045],
    }
    row = plant_layout(900, 500, [{"slot_index": 0, "placement": placement}])[0]

    assert row.footprint.width == pytest.approx(row.support_rect.width * 0.46)
    assert row.footprint.height == pytest.approx(max(2.0, row.support_rect.width * 0.045))
    assert row.footprint.y < row.depth < row.footprint.bottom


@pytest.mark.parametrize("canvas_aspect", [0.5, 1.0, 2.0])
@pytest.mark.parametrize("display_scale", [0.55, 1.0, 1.45])
def test_grounded_physical_base_width_ignores_canvas_art_and_progression(canvas_aspect, display_scale):
    placement = {
        "art_bounds": [0.02, 0.08, 0.96, 0.84],
        "base_bounds": [0.30, 0.66, 0.40, 0.20],
        "foliage_bounds": [0.02, 0.08, 0.96, 0.58],
        "soil_contact": [0.50, 0.86],
        "interaction_bounds": [0.01, 0.04, 0.98, 0.88],
        "display_scale": display_scale,
        "base_type": "pot",
    }
    row = plant_layout(2000, 924, [{
        "slot_index": 3,
        "placement": placement,
        "canvas_aspect": canvas_aspect,
        "stage": "rare" if display_scale > 1 else "seed",
        "is_active": display_scale == 1,
    }])[0]

    assert row.base_rect.width == pytest.approx(924 * 0.155, abs=0.1)
    assert row.base_rect.bottom == pytest.approx(row.depth)


@pytest.mark.parametrize("support_width", [0.12, 0.24, 0.36])
def test_calibrated_lower_support_is_the_physical_width_authority(support_width):
    placement = {
        "art_bounds": [0.02, 0.04, 0.96, 0.92],
        "base_bounds": [0.25, 0.66, 0.50, 0.25],
        "support_bounds": [(1 - support_width) / 2, 0.86, support_width, 0.05],
        "foliage_bounds": [0.10, 0.04, 0.80, 0.62],
        "soil_contact": [0.50, 0.91],
        "interaction_bounds": [0.01, 0.02, 0.98, 0.91],
        "geometry_version": 2,
        "vessel_class": "standard_upright",
        "vessel_class_multiplier": 1.0,
        "scene_scale_correction": 1.0,
        "base_type": "pot",
    }
    row = plant_layout(2000, 924, [{
        "slot_index": 3, "placement": placement, "canvas_aspect": 1.0,
    }])[0]
    target_support_width = 924 * .155
    assert row.support_rect.width == pytest.approx(target_support_width * row.fit_scale, abs=.1)
    assert row.base_rect.width == pytest.approx(
        target_support_width * row.fit_scale * .50 / support_width,
        abs=.1,
    )
    assert .92 <= row.fit_scale <= 1.0


def test_mixed_release_catalog_arrangement_stays_grounded_on_v6_soil():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    assets = json.loads(manifest_path.read_text("utf-8"))["assets"]
    background = _release_background({"assets": assets})
    stages = ("seed", "sprout", "young", "mature", "flowering", "rare")
    stages_by_species: dict[str, set[str]] = {}
    for row in assets:
        if (
            row.get("category") == "plants"
            and row.get("release_preferred") is True
            and "continuity_v6" in row.get("variants", [])
            and row.get("placement", {}).get("release_layout_candidate") is True
        ):
            slot = row.get("slot", {})
            stages_by_species.setdefault(str(slot.get("species", "")), set()).add(
                str(slot.get("stage", ""))
            )
    release_species = sorted(
        species for species, available_stages in stages_by_species.items()
        if available_stages == set(stages)
    )
    assert {"bonsai", "rose"}.issubset(release_species)
    arrangement = tuple(
        (release_species[slot % len(release_species)], stage)
        for slot, stage in enumerate(("rare", "seed", "sprout", "young", "flowering", "mature"))
    )
    items = []
    for slot, (species, stage) in enumerate(arrangement):
        candidates = [
            row for row in assets
            if row.get("category") == "plants"
            and row.get("release_preferred") is True
            and "continuity_v6" in row.get("variants", [])
            and row.get("slot", {}).get("species") == species
            and row.get("slot", {}).get("stage") == stage
            and row.get("placement", {}).get("release_layout_candidate") is True
        ]
        assert len(candidates) == 1
        asset = candidates[0]
        items.append({
            "slot_index": slot,
            "species": species,
            "placement": asset["placement"],
            "canvas_aspect": asset["width"] / asset["height"],
        })

    rows = plant_layout(2000, 924, items, background["placement"], composition_count=6)
    by_slot = {row.slot_index: row for row in rows}
    assert all(row.surface_kind == "soil" for row in rows)
    assert all(row.allowed_base_types == ("direct_soil",) for row in rows)
    assert all(row.contact_plane.contains(*row.ground_anchor) for row in rows)
    assert all(row.support_rect.x >= row.contact_plane.x - 0.5 for row in rows)
    assert all(row.support_rect.right <= row.contact_plane.right + 0.5 for row in rows)
    assert all(not row.validation_warnings for row in rows)
    assert all(
        not left.base_rect.intersects(right.base_rect)
        for index, left in enumerate(rows) for right in rows[index + 1:]
    )
    assert all(
        left.foliage_rect.intersection_area(right.foliage_rect)
        / max(1.0, min(left.foliage_rect.area, right.foliage_rect.area))
        <= 0.60
        for index, left in enumerate(rows) for right in rows[index + 1:]
    )
    assert [row.depth for row in rows] == sorted(row.depth for row in rows)
    home_surfaces = background["placement"]["surface_profile"]["variants"]["home"]["surfaces"]
    expected_depths = [
        surface["anchor"][1] + surface.get("seating_depth", 0.0)
        for surface in home_surfaces
    ]
    assert [by_slot[index].depth / 924 for index in range(6)] == pytest.approx(
        expected_depths, abs=.001
    )


def test_move_badges_use_dedicated_anchors_and_compact_semantic_states():
    rows = plant_layout(900, 560, 6)
    obstacles = [row.visible.expanded(3, 2) for row in rows]
    labels = {
        slot: move_badge_label(
            slot,
            origin_slot=0,
            destination_slot=2,
            unlocked_slots=4,
            occupied_slots={0, 1},
        )
        for slot in range(6)
    }

    assert labels == {
        0: ("Current location", "current"),
        1: ("Swap with plant", "available"),
        2: ("Move here", "active"),
        3: ("Move here", "available"),
        4: ("Locked", "locked"),
        5: ("Locked", "locked"),
    }
    for row in rows:
        badge = bed_badge_rect(row, labels[row.slot_index][0], 900, 560, obstacles)
        assert 0 <= badge.x < badge.right <= 900
        assert 0 <= badge.y < badge.bottom <= 560
        assert badge.width >= 44 and badge.height >= 44
        assert not any(badge.intersects(obstacle) for obstacle in obstacles)


def test_seed_stage_uses_bundled_artwork_without_drawn_or_emoji_cues():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    home = (Path(__file__).resolve().parents[1] / "ankigarden/ui/home_widget.py").read_text()
    assert "def _draw_seedling_cue" not in scene
    assert "ag-home__seedling-cue" not in home
    assert "🌱" not in home


def test_resolved_asset_placement_is_promoted_before_dashboard_layout():
    placement = {
        "visible_bounds": [0.063, 0.4992, 0.8676, 0.3517],
        "ground_anchor": [0.4968, 0.8509],
        "contact_shadow": [0.64, 0.045],
        "base_type": "pot",
    }
    item = plant_layout_item({"plant_id": "bonsai", "asset": {
        "path": "bonsai.png", "placement": placement, "metadata": {"width": 1200, "height": 800},
    }}, 2)

    assert item["slot_index"] == 2
    assert item["placement"] == placement
    assert item["placement"] is not placement
    assert item["canvas_aspect"] == pytest.approx(1.5)


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
    assert all(
        not left.base_rect.intersects(right.base_rect)
        for index, left in enumerate(rows) for right in rows[index + 1:]
    )
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            overlap = left.foliage_rect.intersection_area(right.foliage_rect)
            ratio = overlap / max(1, min(left.foliage_rect.area, right.foliage_rect.area))
            assert ratio <= 0.121
    assert all("unresolved base overlap" not in row.validation_warnings for row in rows)


def test_smart_card_is_constrained_to_scene_edges():
    for anchor_x in (20, 380, 740):
        result = smart_card_rect(760, 320, anchor_x, 250)
        assert result is not None
        x, y, width, height = result
        assert 0 <= x <= 760 - width
        assert 0 <= y <= 320 - height


@pytest.mark.parametrize("size", [(150, 150), (220, 160), (252, 184)])
def test_smart_card_shrinks_to_unusually_small_scenes(size):
    width, height = size
    result = smart_card_rect(width, height, width / 2, height / 2)
    assert result is not None
    x, y, card_width, card_height = result
    assert x >= 0 and y >= 0
    assert x + card_width <= width
    assert y + card_height <= height


def test_smart_card_uses_a_clear_side_lane_without_covering_selected_plant():
    row = plant_layout(
        1093,
        615,
        [{"slot_index": 0, "placement": {"visible_bounds": [0.08, 0.04, 0.84, 0.92]}}],
    )[0]
    selected_plant = row.hit.expanded(8, 8)
    anchor_x = row.smart_card_anchor.x + row.smart_card_anchor.width / 2

    result = smart_card_rect(
        1093,
        615,
        anchor_x,
        row.smart_card_anchor.y,
        card_width=360,
        card_height=220,
        obstacles=[selected_plant],
    )

    assert result is not None
    assert not Rect(*result).intersects(selected_plant)


@pytest.mark.parametrize("scene_size", [(568, 426), (1093, 615)])
def test_dense_six_plant_scene_requests_external_card_dock(scene_size):
    """Cover the 620x520 minimum window's scene and a normal wide scene."""
    width, height = scene_size
    rows = plant_layout(
        width,
        height,
        [
            {"slot_index": slot, "placement": {"visible_bounds": [0.08, 0.04, 0.84, 0.92]}}
            for slot in range(6)
        ],
    )
    obstacles = [row.hit.expanded(8, 8) for row in rows]

    for selected in rows:
        anchor_x = selected.smart_card_anchor.x + selected.smart_card_anchor.width / 2
        result = smart_card_rect(
            width,
            height,
            anchor_x,
            selected.smart_card_anchor.y,
            card_width=360,
            card_height=220,
            obstacles=obstacles,
        )
        assert result is None


def test_move_target_state_distinguishes_valid_locked_and_unavailable_spaces():
    contract = {
        "origin_slot": 0,
        "valid_destination_slots": [1, 2],
        "unlocked_slots": 4,
    }
    assert move_target_state(None, **contract) == "outside"
    assert move_target_state(0, **contract) == "current"
    assert move_target_state(1, **contract) == "valid"
    assert move_target_state(3, **contract) == "unavailable"
    assert move_target_state(4, **contract) == "locked"


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
    assert 'self.config.value("onboarding_version", 0)' in dashboard
    assert 'QPushButton("Dismiss tips")' in dashboard
    assert "self._complete_first_nurture_guidance()" in dashboard
    focused_branch = dashboard.split("def _nurture_plant", 1)[1].split("ok, message =", 1)[0]
    assert "self._complete_first_nurture_guidance()" in focused_branch
    assert "_onboarding_confirmation_generation" in dashboard
    assert "generation != self._onboarding_confirmation_generation" in dashboard
    assert 'self._onboarding_save_error or (' in dashboard
    assert '"The glowing Nursery building' in dashboard
    assert "cardOpened.connect" not in dashboard
    assert "QMessageBox" not in dashboard.split("def _refresh_onboarding", 1)[1].split("def _clear_layout", 1)[0]


def test_dashboard_is_garden_first_with_compact_secondary_tabs():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "from .formatters import format_status_label" in dashboard
    assert "root.addWidget(hero_card)" in dashboard
    assert 'self.garden_stats_bar = GardenStatsStrip()' in dashboard
    assert '("growth", "Plant Growth"' in dashboard
    assert '("currency", "Garden Coins"' in dashboard
    assert "self.streak_ticks = QLabel" not in dashboard
    assert "self.details_tabs = QTabWidget()" in dashboard
    assert 'self.details_tabs.addTab(self.today_list' in dashboard
    assert 'self.details_tabs.addTab(self.collection_list, "Collection")' in dashboard
    assert 'self.today_list = ProgressList("Today progress")' in dashboard
    assert 'QLabel("Recent Garden Coins")' in dashboard
    assert "transaction.reason" in dashboard
    assert "transaction.balance" in dashboard
    assert "class ProgressList(QWidget):" in dashboard
    assert "class ProgressList(QScrollArea):" not in dashboard
    assert 'self.details_tabs.setTabToolTip(0, "See today’s card answers, Growth, and Garden Coin rewards.")' in dashboard
    assert 'self.details_tabs.setTabToolTip(1, "View long-term milestones and unlocked achievements.")' in dashboard
    assert 'QLabel("Today’s progress")' in dashboard
    assert "self._position_plant_card" in dashboard
    assert "self.hero_summary" not in dashboard
    assert "self.streak_chip" not in dashboard
    assert 'self.progress_toggle = QPushButton("Progress")' in dashboard
    assert "self.details_tabs.hide()" in dashboard


def test_selected_state_traces_artwork_without_a_detached_ground_ring():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert "CompositionMode_DestinationOut" in scene
    assert "desired_width = 2.0 if emphasized else 1.15" in scene
    assert "edge = QPixmap(source.width() + padding * 2" in scene
    assert "painter.setOpacity(0.62 if emphasized else 0.34 * hovered)" in scene
    assert "layout.grounding.shadow_plane" in scene
    assert "layout.grounding.cast_shadow" in scene
    assert "_draw_plant_interaction_base" not in scene
    assert "Selected and keyboard-focus contours are a final UI layer" in scene
    assert "_draw_selected_vessel_edge" not in scene
    assert "footprint.translate" not in scene


def test_runtime_layout_repairs_duplicate_slots_and_uses_soil_y_for_z_order():
    plants = [
        {"plant_id": "a", "slot_index": 0},
        {"plant_id": "b", "slot_index": 0},
        {"plant_id": "c", "slot_index": 99},
    ]
    rows = plant_layout(900, 500, plants, composition_count=3)
    assert len({row.slot_index for row in rows}) == 3
    assert [row.z_depth for row in rows] == sorted(row.z_depth for row in rows)


def test_phase2_copy_states_and_single_scroll_contract_are_explicit():
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "ankigarden/ui/dashboard.py").read_text()
    scene = (root / "ankigarden/ui/scene.py").read_text()
    assert "self.milestone_card.hide()" in dashboard
    assert 'f"{_plant_count(len(state.plants))} collected. "' in dashboard
    assert 'f"{_plant_count(available_count)} available now. "' in dashboard
    assert "STREAK_BONUS_TIERS" not in dashboard
    assert '"streak_bonus_percent": streak_bonus' in dashboard
    assert "Garden daily goal" not in dashboard
    assert '"locked" if display.current' not in dashboard
    assert '"in_progress" if display.current > 0 else "locked"' in dashboard
    # Avoid the platform-specific ``%-d`` directive (unsupported on Windows)
    # while keeping the learner-facing long month/day/year format.
    assert "f\"{parsed.strftime('%B')} {parsed.day}, {parsed.year}\"" in dashboard
    assert "STATS_HELP_TEXT = PROGRESSION_SUMMARY" in scene
    assert 'streak_label = "Study today to start your Anki streak"' in scene
    assert 'f"{streak_days}-day Anki streak with "' in scene
    assert '"No streak yet\\nStudy today to start"' in dashboard
    assert "if streak_days == 0" in dashboard
    assert '"\\n".join(labels)' in scene
    assert "path.cubicTo(" in scene
    assert "self._draw_garden_overlay_asset(painter, r)" not in scene.split("def paintEvent", 1)[1].split("def _draw_status_overlay", 1)[0]


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
    assert "This garden space has not been unlocked yet." in scene


def test_scene_landmarks_are_registered_accessible_and_disabled_while_rearranging():
    root = Path(__file__).resolve().parents[1]
    scene = (root / "ankigarden/ui/scene.py").read_text()
    landmarks = (root / "ankigarden/ui/landmarks.py").read_text()
    dashboard = (root / "ankigarden/ui/dashboard.py").read_text()
    assert "landmarkActivated = pyqtSignal(str)" in scene
    assert 'self._nursery_hotspot.setAccessibleName("Nursery")' in scene
    assert 'self._nursery_hotspot.setAccessibleDescription("Open Nursery")' in scene
    assert "Qt.CursorShape.PointingHandCursor" in scene
    assert "if self._interaction.placing:" in scene
    assert "normalized_id not in self._landmark_actions" in scene
    assert '"garden.nursery.open": LandmarkAction(' in landmarks
    assert 'tooltip="Open Nursery"' in landmarks
    assert "if not interactive" in landmarks
    assert "self._interaction.dismiss()" in scene.split("def _activate_landmark", 1)[1]
    assert 'handlers = {"garden.nursery.open": self._open_nursery}' in dashboard
    assert "QMessageBox" not in dashboard.split("def _on_landmark_activated", 1)[1].split(
        "def _on_placement_state", 1
    )[0]


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
    assert "This story is just beginning." in dashboard
    assert 'QLabel("Up next")' in dashboard
    assert "reverse=True" not in dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    assert "event.key() == Qt.Key.Key_Escape" in dashboard
    assert "self.engine.rename_plant" in dashboard
    assert "self.plant_card.story.clicked.connect" in dashboard


def test_dialog_class_boundaries_keep_appearance_ui_out_of_story_refresh():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    settings_block = dashboard.split("class GardenSettingsDialog", 1)[1].split("class PlantStoryDialog", 1)[0]
    story_block = dashboard.split("class PlantStoryDialog", 1)[1].split("class GardenDashboard", 1)[0]
    assert "self.behavior = GardenStudioWidget(" in settings_block
    assert "garden_snapshot_provider=snapshot_provider" in settings_block
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


def test_settings_expose_home_visibility_and_transaction_errors():
    root = Path(__file__).resolve().parents[1]
    studio = (root / "ankigarden/ui/garden_studio.py").read_text()
    dashboard = (root / "ankigarden/ui/dashboard.py").read_text()
    assert '"daily_goal"' not in studio
    assert '"show_home_widget": self.show_home_widget.isChecked()' in studio
    assert "behavior_scroll.setWidgetResizable(True)" in dashboard
    assert 'QPushButton("Save settings")' in dashboard
    assert 'QPushButton("Restore defaults")' in dashboard
    assert '"Garden settings"' in dashboard
    assert "except ConfigError as exc:" in dashboard
    settings_block = dashboard.split("class GardenSettingsDialog", 1)[1].split("class PlantStoryDialog", 1)[0]
    assert "QMessageBox.warning" not in settings_block
    assert 'self.save_status.setText("Saved")' in dashboard
    assert 'self.save_status.setText("Unsaved changes")' in dashboard
    assert "self.behavior.reset_preview_defaults()" in dashboard
    assert "self.config.update(old_payload)" in dashboard
    assert "self.particle_slider.setRange(10, 200)" in studio
    assert "self._update_motion_controls" in studio
    assert 'return "Standard"' in studio


def test_dashboard_floating_plant_card_and_distinct_rearrange_bar_are_real_controls():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    assert "class PlantInfoCard(QFrame):" in dashboard
    assert 'self.nurture = QPushButton("Nurture")' in dashboard
    assert 'self.fertilize = QPushButton("Fertilize")' in dashboard
    assert 'self.move = QPushButton("Move")' in dashboard
    assert 'self.story = QPushButton("Story")' in dashboard
    assert 'self.nurture.setText("Nurturing" if active else "Nurture")' in dashboard
    assert "class RearrangeBar(QFrame):" in dashboard
    assert 'title = QLabel("Move plant")' in dashboard
    assert 'self.cancel = QPushButton("Cancel")' in dashboard
    assert 'self.done = QPushButton("Done")' not in dashboard
    assert "destination_selector" not in dashboard
    assert "self.engine.commit_placement_draft(draft)" in dashboard
    assert "COMPACT_LAYOUT_WIDTH = 900" in dashboard
    assert "self.onboarding_layout.setDirection(direction)" in dashboard
    assert "self.milestone_layout.setDirection(direction)" in dashboard
    assert "self.rearrange_bar.set_compact(compact)" in dashboard
    assert "self.page_scroll.ensureWidgetVisible(self.plant_card, 12, 12)" in dashboard
    assert "self.today_summary.setWordWrap(True)" in dashboard
    assert "QMessageBox.information(\n            self,\n            \"How to use the garden\"" not in dashboard
    assert "def card_geometry" in scene
    assert "self.selectionChanged.emit(\"\")" in scene
    assert "for index in range(6)" in scene
    assert "move_badge_label(" in scene
    assert 'f"Bed {slot + 1}: {label}"' in scene
    assert "self._interaction.placing and not self._drag_started" in scene
    assert "slot < unlocked" in scene


def test_every_weather_has_procedural_motion_and_respects_motion_toggle():
    scene = (Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py").read_text()
    motion = scene.split("def _draw_weather_motion", 1)[1].split("def _draw_decoration_asset", 1)[0]
    for weather in ("gentle_rain", "fireflies", "cloudy", "breeze", "sunny"):
        assert weather in motion
    render = scene.split("def paintEvent", 1)[1].split("def _draw_status_overlay", 1)[0]
    assert 'if bool(self.scene.get("motion_enabled", True)):' in render
    assert "self._draw_weather_motion" in render


def test_settings_sections_and_preview_only_controls_match_persistence_contract():
    studio = (Path(__file__).resolve().parents[1] / "ankigarden/ui/garden_studio.py").read_text()
    for title in ("Verdant Twilight", "Current garden style", "Motion", "Garden display", "Fine tune"):
        assert f'"{title}"' in studio
    assert "one-option" not in studio
    assert "self.theme_combo" not in studio
    assert "Adjust artwork and weather detail only when you need to." in studio
    assert '"weather"' not in studio.split("def build_theme_payload", 1)[1].split("def _normalize_theme", 1)[0]
    assert '"growth_stage"' not in studio.split("def build_theme_payload", 1)[1].split("def _normalize_theme", 1)[0]
    assert '"animations_label": "Animate weather"' in studio
    assert '"animation_label": "Weather motion"' in studio


def test_nursery_is_artwork_driven_data_driven_and_not_a_toolbar_menu():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    assert "class NurseryDialog(QDialog):" in dashboard
    nursery = dashboard.split("class NurseryDialog", 1)[1].split("class PlantInfoCard", 1)[0]
    assert "self.engine.catalog_summary()" in nursery
    assert "self.engine.choose_starter(species)" in nursery
    assert "self.engine.release_ready_species" not in nursery  # summary owns readiness
    assert 'self._plant_artwork(species, "seed")' in nursery
    assert 'QLabel("Available now")' not in nursery  # section helper owns the label
    assert 'self._section_label("Available now")' in nursery
    assert "QComboBox" not in dashboard
    assert "QMenu" not in dashboard
    assert "QTimer.singleShot(0, self._open_nursery)" in dashboard
    assert 'handlers = {"garden.nursery.open": self._open_nursery}' in dashboard


def test_dashboard_close_and_reopen_manage_timer_filter_and_transient_interaction_state():
    dashboard = (Path(__file__).resolve().parents[1] / "ankigarden/ui/dashboard.py").read_text()
    show_block = dashboard.split("def showEvent", 1)[1].split("def _recommended_window_size", 1)[0]
    done_block = dashboard.split("def done", 1)[1].split("def _update_scene_height", 1)[0]

    assert "self._install_application_filter()" in show_block
    assert "self._fertilizer_timer.start()" in show_block
    assert "self._fertilizer_timer.stop()" in done_block
    assert "self._cancel_move()" in done_block
    assert "self.scene.dismiss_selection()" in done_block
    assert "application.removeEventFilter(self)" in done_block


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
    assert "def _refresh_after_commit" in dashboard
    assert "parent.parent()" not in dashboard
    assert dashboard.count('self._refresh_after_commit("') >= 5
    done_block = dashboard.split("def done(self, result: int)", 1)[1].split("def _update_scene_height", 1)[0]
    assert "super().done(result)" in done_block
    assert "QTimer.singleShot(0, self.refresh_external_surfaces)" in done_block
    refresh_block = dashboard.split("def refresh_external_surfaces", 1)[1].split("def show_same_day_catchup_feedback", 1)[0]
    assert '{"deckBrowser": "deckBrowser", "overview": "overview"}' in refresh_block
    assert "refresh()" in refresh_block
    story_block = dashboard.split("def _open_plant_story", 1)[1].split("def _place_plant", 1)[0]
    assert 'self._refresh_after_commit("Plant Story")' in story_block
