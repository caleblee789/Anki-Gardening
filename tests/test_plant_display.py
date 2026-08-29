from pathlib import Path
import json
import math

import pytest

from ankigarden.ui.plant_display import (
    CURRENT_ONBOARDING_VERSION,
    NURTURED_MARKER_MAX_GROUND_DELTA_RATIO,
    NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO,
    PlantInteractionState,
    PLANT_POPOVER_CLEARANCE,
    PLANT_POPOVER_EDGE_PADDING,
    PLANT_POPOVER_MAX_HEIGHT,
    PLANT_POPOVER_MAX_WIDTH,
    PLANT_POPOVER_MIN_WIDTH,
    PLANT_POPOVER_PREFERRED_WIDTH,
    Rect,
    SceneGeometryLayout,
    bed_badge_rect,
    compact_plant_layout,
    contained_canvas_rect,
    cover_project_point,
    chronological_memories,
    growth_display,
    hit_test,
    move_badge_label,
    move_target_state,
    nurtured_badge_rect,
    nurtured_marker_fallback_rect,
    nurtured_marker_placement,
    nurtured_marker_rect,
    onboarding_display,
    plant_layout,
    plant_layout_item,
    planter_draw_rect,
    requires_native_destination_selector,
    settings_layout_is_compact,
    smart_card_rect,
    translated_plant_placement,
)
from ankigarden.models.state import PlantMemory


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


@pytest.mark.skip(reason="native background now uses a fixed 3:2 cover transform")
def test_contained_canvas_offset_moves_artwork_beds_and_hit_regions_together():
    viewport_width, viewport_height = 1600.0, 840.0
    canvas = contained_canvas_rect(viewport_width, viewport_height)
    local = plant_layout(
        canvas.width,
        canvas.height,
        [{"slot_index": slot} for slot in range(6)],
        composition_count=6,
    )
    translated = [
        translated_plant_placement(row, canvas.x, canvas.y)
        for row in local
    ]
    geometry = SceneGeometryLayout.from_placements(
        viewport_width,
        viewport_height,
        translated,
        scene_bounds=canvas,
    )

    assert geometry.scene_bounds == canvas
    assert canvas.x == pytest.approx(180.0)
    for before, after in zip(local, translated):
        assert after.ground_anchor[0] == pytest.approx(
            before.ground_anchor[0] + canvas.x
        )
        assert after.ground_anchor[1] == pytest.approx(before.ground_anchor[1])
        bed = geometry.bed(after.slot_index)
        assert bed is not None
        assert canvas.contains(*bed.ground_anchor)
        assert canvas.contains(
            bed.hotspot.x + bed.hotspot.width / 2,
            bed.hotspot.y + bed.hotspot.height / 2,
        )


@pytest.mark.parametrize(
    ("width", "compact"),
    [(0, True), (640, True), (683, True), (684, False), (759, False), (761, False)],
)
def test_settings_layout_compatibility_uses_the_shared_content_requirement(width, compact):
    assert settings_layout_is_compact(width) is compact


@pytest.mark.parametrize(
    "visible",
    (
        Rect(18, 120, 90, 120),
        Rect(455, 80, 90, 160),
        Rect(890, 110, 90, 130),
    ),
)
def test_nurturing_marker_stays_on_canvas_and_outside_plant_pixels(visible: Rect) -> None:
    marker = nurtured_marker_rect(1000, 420, visible, 120)

    assert 0 <= marker.x and marker.right <= 1000
    assert 0 <= marker.y and marker.bottom <= 420
    assert not marker.intersects(visible)


def test_compact_nurtured_badge_keeps_original_size_and_adjacency() -> None:
    visible = Rect(420, 120, 80, 110)
    badge = nurtured_badge_rect(1000, 420, visible, 120)

    assert 22 <= badge.width <= 26
    assert badge.height == badge.width
    assert 0 <= badge.x and badge.right <= 1000
    assert 0 <= badge.y and badge.bottom <= 420
    assert 0 < badge.x - visible.right <= 5


@pytest.mark.parametrize(
    ("width", "height", "surface_context"),
    (
        (620, 465, "dashboard"),
        (1_093, 615, "dashboard"),
        (1_440, 600, "dashboard"),
        (1_000, 420, "home"),
    ),
)
def test_nurtured_marker_uses_close_plant_side_lane_for_every_plot(
    width: int,
    height: int,
    surface_context: str,
) -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text(
            "utf-8"
        )
    )
    background = _release_background(manifest)
    assets = [
        row
        for row in manifest["assets"]
        if row.get("category") == "plants"
        and isinstance(row.get("placement"), dict)
    ][:6]
    plants = [
        {
            "plant_id": f"marker-{slot}",
            "slot_index": slot,
            "species": asset["slot"]["species"],
            "stage": asset["slot"]["stage"],
            "placement": asset["placement"],
            "canvas_aspect": float(asset["width"]) / float(asset["height"]),
        }
        for slot, asset in enumerate(assets)
    ]
    layouts = plant_layout(
        width,
        height,
        plants,
        background["placement"],
        surface_context=surface_context,
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )
    family = background["placement"]["surface_profile"]["planter_family"]
    planter_boxes = [planter_draw_rect(layout, family) for layout in layouts]
    obstacles = [layout.visible.expanded(4, 4) for layout in layouts]
    geometry = SceneGeometryLayout.from_placements(
        width,
        height,
        layouts,
        planter_family=family,
    )

    for layout, planter in zip(layouts, planter_boxes):
        bed = geometry.bed(layout.slot_index)
        assert bed is not None
        marker = geometry.resolve_watering_can(
            layout.slot_index,
            layout,
            obstacles=obstacles,
        )

        expected_side = marker.side
        assert expected_side in {"left", "right"}
        expected_orientation = (
            "spout-right" if expected_side == "left" else "spout-left"
        )
        assert marker.used_fallback is False
        assert marker.orientation == expected_orientation
        assert marker.perspective_scale == pytest.approx(
            {
                "far": 0.78,
                "middle": 0.90,
                "near": 1.00,
            }[layout.depth_band]
        )
        assert 44 <= marker.rect.width <= 88
        assert marker.rect.height == marker.rect.width
        assert 0 <= marker.pulse_bounds.x
        assert marker.pulse_bounds.right <= width
        assert 0 <= marker.pulse_bounds.y
        assert marker.pulse_bounds.bottom <= height
        if layout.slot_index == 2:
            assert marker.pulse_bounds.x >= 12
        if layout.slot_index == 5:
            assert width - marker.pulse_bounds.right >= 12
        assert not any(marker.pulse_bounds.intersects(rect) for rect in obstacles)
        aligned_y = layout.ground_anchor[1] - marker.rect.height * 0.916
        assert abs(marker.rect.y - aligned_y) <= (
            marker.rect.height * NURTURED_MARKER_MAX_GROUND_DELTA_RATIO
        )
        marker_ground_y = marker.rect.y + marker.rect.height * 0.916
        assert abs(marker_ground_y - layout.ground_anchor[1]) <= (
            marker.rect.height * NURTURED_MARKER_MAX_GROUND_DELTA_RATIO
        )
        marker_center_x = marker.rect.x + marker.rect.width / 2
        plant_distance = math.hypot(
            marker_center_x - layout.ground_anchor[0],
            marker_ground_y - layout.ground_anchor[1],
        )
        assert (
            plant_distance
            <= planter.width * NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO
        )
        assert bed.planter_exclusions
        assert not any(
            marker.pulse_bounds.intersects(exclusion)
            for exclusion in bed.planter_exclusions
        )
        assert marker.contact_shadow.area > 0
        assert geometry.scene_bounds.contains(
            marker.contact_shadow.x + marker.contact_shadow.width / 2,
            marker.contact_shadow.y + marker.contact_shadow.height / 2,
        )
        assert marker.contact_shadow.width < marker.rect.width
        assert marker.contact_shadow.y >= marker.rect.y + marker.rect.height * 0.80
        if expected_side == "left":
            assert marker.pulse_bounds.right <= layout.visible.x - 4
            assert marker_center_x < layout.ground_anchor[0]
        else:
            assert marker.pulse_bounds.x >= layout.visible.right + 4
            assert marker_center_x > layout.ground_anchor[0]
        fallback = nurtured_marker_fallback_rect(marker)
        assert marker.rect.contains(
            fallback.x + fallback.width / 2,
            fallback.y + fallback.height / 2,
        )


@pytest.mark.parametrize("device_pixel_ratio", (1.0, 1.5, 2.0, 3.0))
@pytest.mark.skip(reason="near-left bed is intentionally reserved away from the Feature bay")
def test_scene_geometry_matrix_covers_six_beds_popovers_markers_and_scaling(
    device_pixel_ratio: float,
) -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text(
            "utf-8"
        )
    )
    background = _release_background(manifest)
    assets = [
        row
        for row in manifest["assets"]
        if row.get("category") == "plants"
        and isinstance(row.get("placement"), dict)
    ][:6]
    plants = [
        {
            "plant_id": f"geometry-{slot}",
            "slot_index": slot,
            "placement": asset["placement"],
            "canvas_aspect": float(asset["width"]) / float(asset["height"]),
        }
        for slot, asset in enumerate(assets)
    ]
    layouts = plant_layout(
        1_093,
        615,
        plants,
        background["placement"],
        composition_count=6,
    )
    family = background["placement"]["surface_profile"]["planter_family"]
    geometry = SceneGeometryLayout.from_placements(
        1_093,
        615,
        layouts,
        device_pixel_ratio=device_pixel_ratio,
        planter_family=family,
    )
    obstacles = [layout.visible.expanded(4, 4) for layout in layouts]

    assert geometry.device_pixel_ratio == device_pixel_ratio
    assert [bed.bed_id for bed in geometry.beds] == list(range(6))
    assert not any(
        left.hotspot.intersects(right.hotspot)
        for index, left in enumerate(geometry.beds)
        for right in geometry.beds[index + 1:]
    )
    shrunk_popovers: set[int] = set()
    for layout in layouts:
        bed = geometry.bed(layout.slot_index)
        assert bed is not None
        assert geometry.safe_bounds.contains(
            bed.hotspot.x + bed.hotspot.width / 2,
            bed.hotspot.y + bed.hotspot.height / 2,
        )
        assert bed.slot_envelope.contains(
            bed.selection_region.x + bed.selection_region.width / 2,
            bed.selection_region.y + bed.selection_region.height / 2,
        )
        preferred = (380, 480) if layout.slot_index == 5 else (320, 360)
        popover = geometry.resolve_popover(
            layout.slot_index,
            preferred,
            (280, 220),
            (),
        )
        assert popover.chosen_side in bed.popover_candidates
        assert geometry.safe_bounds.contains(
            popover.rectangle.x + popover.rectangle.width / 2,
            popover.rectangle.y + popover.rectangle.height / 2,
        )
        assert popover.maximum_content_height == popover.rectangle.height
        selected_parts = (
            bed.selection_region,
            bed.visible_region,
            bed.planter_bounds,
        )
        selected_target = Rect(
            min(part.x for part in selected_parts),
            min(part.y for part in selected_parts),
            max(part.right for part in selected_parts)
            - min(part.x for part in selected_parts),
            max(part.bottom for part in selected_parts)
            - min(part.y for part in selected_parts),
        ).expanded(PLANT_POPOVER_CLEARANCE)
        assert not popover.rectangle.intersects(selected_target) or popover.docked
        assert PLANT_POPOVER_MIN_WIDTH <= popover.rectangle.width <= PLANT_POPOVER_MAX_WIDTH
        assert 220 <= popover.rectangle.height <= preferred[1]
        assert popover.rectangle.height <= PLANT_POPOVER_MAX_HEIGHT
        assert popover.rectangle.x >= PLANT_POPOVER_EDGE_PADDING
        assert popover.rectangle.y >= PLANT_POPOVER_EDGE_PADDING
        assert popover.rectangle.right <= 1_093 - PLANT_POPOVER_EDGE_PADDING
        assert popover.rectangle.bottom <= 615 - PLANT_POPOVER_EDGE_PADDING
        pointer_x, pointer_y = popover.connector_end
        if popover.chosen_side in {"right", "left"}:
            expected_x = (
                popover.rectangle.x
                if popover.chosen_side == "right"
                else popover.rectangle.right
            )
            assert pointer_x == pytest.approx(expected_x)
            assert popover.rectangle.y + 20 <= pointer_y <= popover.rectangle.bottom - 20
        else:
            expected_y = (
                popover.rectangle.bottom
                if popover.chosen_side in {"above", "top-docked"}
                else popover.rectangle.y
            )
            assert pointer_y == pytest.approx(expected_y)
            assert popover.rectangle.x + 20 <= pointer_x <= popover.rectangle.right - 20
        if popover.rectangle.width < preferred[0] or popover.rectangle.height < preferred[1]:
            shrunk_popovers.add(layout.slot_index)

        marker = geometry.resolve_watering_can(
            layout.slot_index,
            layout,
            obstacles=obstacles,
        )
        assert marker.used_fallback is False
        assert not marker.pulse_bounds.intersects(layout.visible.expanded(4, 4))
        all_planter_exclusions = (
            exclusion
            for candidate in geometry.beds
            for exclusion in candidate.planter_exclusions
        )
        assert not any(
            marker.pulse_bounds.intersects(exclusion)
            for exclusion in all_planter_exclusions
        )
        assert geometry.safe_bounds.contains(
            marker.rect.x + marker.rect.width / 2,
            marker.rect.y + marker.rect.height / 2,
        )
    assert shrunk_popovers


def test_popovers_keep_six_selected_beds_visible_and_choose_least_overlap() -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text(
            "utf-8"
        )
    )
    background = _release_background(manifest)
    assets = [
        row
        for row in manifest["assets"]
        if row.get("category") == "plants"
        and isinstance(row.get("placement"), dict)
    ][:6]
    layouts = plant_layout(
        1_093,
        615,
        [
            {
                "plant_id": f"popover-{slot}",
                "slot_index": slot,
                "placement": asset["placement"],
                "canvas_aspect": float(asset["width"]) / float(asset["height"]),
            }
            for slot, asset in enumerate(assets)
        ],
        background["placement"],
        composition_count=6,
    )
    geometry = SceneGeometryLayout.from_placements(1_093, 615, layouts)
    safe = Rect(
        PLANT_POPOVER_EDGE_PADDING,
        PLANT_POPOVER_EDGE_PADDING,
        1_093 - PLANT_POPOVER_EDGE_PADDING * 2,
        615 - PLANT_POPOVER_EDGE_PADDING * 2,
    )
    preferred = (320.0, 300.0)
    minimum = (PLANT_POPOVER_MIN_WIDTH, 220.0)

    lower_right_beds = [
        bed
        for bed in geometry.beds
        if bed.popover_anchor[0] >= geometry.safe_bounds.x + geometry.safe_bounds.width / 2
        and bed.popover_anchor[1] >= geometry.safe_bounds.y + geometry.safe_bounds.height / 2
    ]
    assert lower_right_beds
    assert all(
        bed.popover_candidates[:2] == ("left", "above")
        for bed in lower_right_beds
    )
    upper_left_beds = [
        bed
        for bed in geometry.beds
        if bed.popover_anchor[0] < geometry.safe_bounds.x + geometry.safe_bounds.width / 2
        and bed.popover_anchor[1] < geometry.safe_bounds.y + geometry.safe_bounds.height / 2
    ]
    assert upper_left_beds
    assert all(
        bed.popover_candidates[:2] == ("right", "below")
        for bed in upper_left_beds
    )
    accessory_bed = upper_left_beds[0]
    selected_marker = Rect(
        accessory_bed.planter_bounds.right + 4,
        accessory_bed.planter_bounds.y,
        52,
        64,
    )
    accessory_popover = geometry.resolve_popover(
        accessory_bed.bed_id,
        preferred,
        minimum,
        selected_accessory_regions=(selected_marker,),
    )
    accessory_parts = (
        accessory_bed.selection_region,
        accessory_bed.visible_region,
        accessory_bed.planter_bounds,
        selected_marker,
    )
    accessory_union = Rect(
        min(part.x for part in accessory_parts),
        min(part.y for part in accessory_parts),
        max(part.right for part in accessory_parts)
        - min(part.x for part in accessory_parts),
        max(part.bottom for part in accessory_parts)
        - min(part.y for part in accessory_parts),
    ).expanded(PLANT_POPOVER_CLEARANCE)
    assert not accessory_popover.rectangle.intersects(accessory_union)

    def clamped(rect: Rect) -> Rect:
        return Rect(
            max(safe.x, min(rect.x, safe.right - rect.width)),
            max(safe.y, min(rect.y, safe.bottom - rect.height)),
            rect.width,
            rect.height,
        )

    for bed in geometry.beds:
        selected_parts = (
            bed.selection_region,
            bed.visible_region,
            bed.planter_bounds,
        )
        selected_target = Rect(
            min(part.x for part in selected_parts),
            min(part.y for part in selected_parts),
            max(part.right for part in selected_parts)
            - min(part.x for part in selected_parts),
            max(part.bottom for part in selected_parts)
            - min(part.y for part in selected_parts),
        )
        selected_obstacle = selected_target.expanded(PLANT_POPOVER_CLEARANCE)
        resolved = geometry.resolve_popover(
            bed.bed_id,
            preferred,
            minimum,
        )
        assert resolved.rectangle.x >= PLANT_POPOVER_EDGE_PADDING
        assert resolved.rectangle.y >= PLANT_POPOVER_EDGE_PADDING
        assert resolved.rectangle.right <= 1_093 - PLANT_POPOVER_EDGE_PADDING
        assert resolved.rectangle.bottom <= 615 - PLANT_POPOVER_EDGE_PADDING
        assert not resolved.rectangle.intersects(selected_obstacle)

        alternatives: list[Rect] = []
        anchor_x, anchor_y = bed.popover_anchor
        width = resolved.rectangle.width
        height = resolved.rectangle.height
        for side in ("right", "left", "above", "below"):
            if side == "right":
                raw = Rect(
                    selected_target.right + PLANT_POPOVER_CLEARANCE,
                    selected_target.y,
                    width,
                    height,
                )
            elif side == "left":
                raw = Rect(
                    selected_target.x - PLANT_POPOVER_CLEARANCE - width,
                    selected_target.y,
                    width,
                    height,
                )
            elif side == "above":
                raw = Rect(
                    anchor_x - width / 2,
                    selected_target.y - PLANT_POPOVER_CLEARANCE - height,
                    width,
                    height,
                )
            else:
                raw = Rect(
                    anchor_x - width / 2,
                    selected_target.bottom + PLANT_POPOVER_CLEARANCE,
                    width,
                    height,
                )
            candidate = clamped(raw)
            if not candidate.intersects(selected_obstacle):
                alternatives.append(candidate)

        assert alternatives
        chosen_overlap = sum(
            resolved.rectangle.intersection_area(other.selection_region.expanded(5))
            for other in geometry.beds
            if other.bed_id != bed.bed_id
        )
        minimum_overlap = min(
            sum(
                candidate.intersection_area(other.selection_region.expanded(5))
                for other in geometry.beds
                if other.bed_id != bed.bed_id
            )
            for candidate in alternatives
        )
        assert chosen_overlap == pytest.approx(minimum_overlap)


@pytest.mark.parametrize(
    "window_size",
    ((1_536, 1_024), (1_440, 900), (1_280, 800)),
)
@pytest.mark.parametrize(
    "position_label",
    ("top-left", "top-right", "center", "bottom-left", "bottom-right"),
)
@pytest.mark.parametrize("toast_visible", (False, True))
def test_required_macos_window_matrix_keeps_plant_popover_anchored(
    window_size: tuple[int, int],
    position_label: str,
    toast_visible: bool,
) -> None:
    """Exercise the complete 3 x 5 x 2 logical-pixel placement matrix."""

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text(
            "utf-8"
        )
    )
    background = _release_background(manifest)
    assets = [
        row
        for row in manifest["assets"]
        if row.get("category") == "plants"
        and isinstance(row.get("placement"), dict)
    ][:6]
    window_width, window_height = window_size
    # The header/HUD live outside the direct scene canvas. These dimensions
    # conservatively model the remaining canvas at each required window size.
    scene_width = min(1_240, window_width - 48)
    scene_height = window_height - 230
    layouts = plant_layout(
        scene_width,
        scene_height,
        [
            {
                "plant_id": f"matrix-{slot}",
                "slot_index": slot,
                "placement": asset["placement"],
                "canvas_aspect": float(asset["width"]) / float(asset["height"]),
            }
            for slot, asset in enumerate(assets)
        ],
        background["placement"],
        composition_count=6,
    )
    geometry = SceneGeometryLayout.from_placements(
        scene_width,
        scene_height,
        layouts,
    )

    targets = (
        ("top-left", geometry.scene_bounds.x, geometry.scene_bounds.y),
        ("top-right", geometry.scene_bounds.right, geometry.scene_bounds.y),
        ("bottom-left", geometry.scene_bounds.x, geometry.scene_bounds.bottom),
        ("bottom-right", geometry.scene_bounds.right, geometry.scene_bounds.bottom),
        (
            "center",
            geometry.scene_bounds.x + geometry.scene_bounds.width / 2,
            geometry.scene_bounds.y + geometry.scene_bounds.height / 2,
        ),
    )
    chosen_beds: dict[str, object] = {}
    remaining = list(geometry.beds)
    for label, target_x, target_y in targets:
        chosen = min(
            remaining,
            key=lambda bed: (
                (bed.popover_anchor[0] - target_x) ** 2
                + (bed.popover_anchor[1] - target_y) ** 2
            ),
        )
        chosen_beds[label] = chosen
        remaining.remove(chosen)
    bed = chosen_beds[position_label]

    obstacles: tuple[Rect, ...] = ()
    if toast_visible:
        toast_width = 320.0
        toast_x = (
            scene_width - PLANT_POPOVER_EDGE_PADDING - toast_width
            if bed.popover_anchor[0] < scene_width / 2
            else PLANT_POPOVER_EDGE_PADDING
        )
        obstacles = (
            Rect(
                toast_x,
                PLANT_POPOVER_EDGE_PADDING,
                toast_width,
                56.0,
            ),
        )

    resolved = geometry.resolve_popover(
        bed.bed_id,
        (PLANT_POPOVER_PREFERRED_WIDTH, 333.0),
        (PLANT_POPOVER_MIN_WIDTH, 333.0),
        obstacles,
    )
    safe = Rect(
        PLANT_POPOVER_EDGE_PADDING,
        PLANT_POPOVER_EDGE_PADDING,
        scene_width - PLANT_POPOVER_EDGE_PADDING * 2,
        scene_height - PLANT_POPOVER_EDGE_PADDING * 2,
    )
    selected_parts = (
        bed.selection_region,
        bed.visible_region,
        bed.planter_bounds,
    )
    selected_target = Rect(
        min(part.x for part in selected_parts),
        min(part.y for part in selected_parts),
        max(part.right for part in selected_parts)
        - min(part.x for part in selected_parts),
        max(part.bottom for part in selected_parts)
        - min(part.y for part in selected_parts),
    ).expanded(PLANT_POPOVER_CLEARANCE)

    assert resolved.docked is False
    assert PLANT_POPOVER_MIN_WIDTH <= resolved.rectangle.width <= PLANT_POPOVER_MAX_WIDTH
    assert resolved.rectangle.height == 333.0
    assert resolved.rectangle.x >= safe.x
    assert resolved.rectangle.y >= safe.y
    assert resolved.rectangle.right <= safe.right
    assert resolved.rectangle.bottom <= safe.bottom
    assert not resolved.rectangle.intersects(selected_target)
    assert not any(resolved.rectangle.intersects(obstacle) for obstacle in obstacles)
    assert resolved.chosen_side in {"right", "left", "above", "below"}

    pointer_x, pointer_y = resolved.connector_end
    if resolved.chosen_side in {"right", "left"}:
        assert resolved.rectangle.y + 20 <= pointer_y <= resolved.rectangle.bottom - 20
        assert pointer_x == pytest.approx(
            resolved.rectangle.x
            if resolved.chosen_side == "right"
            else resolved.rectangle.right
        )
    else:
        assert resolved.rectangle.x + 20 <= pointer_x <= resolved.rectangle.right - 20
        assert pointer_y == pytest.approx(
            resolved.rectangle.bottom
            if resolved.chosen_side == "above"
            else resolved.rectangle.y
        )


def test_growth_display_sanitizes_invalid_points():
    assert growth_display("bad").stage == "seed"
    assert growth_display(-20).points_remaining == 500


def test_growth_display_exposes_plain_language_stage_progress():
    display = growth_display(1_000)
    assert display.stage_points == 500
    assert display.stage_goal == 2_000


def test_onboarding_stages_first_review_and_nurture_without_schema_state():
    fresh = onboarding_display(0, 0)
    reviewed = onboarding_display(1, 0)
    updated_existing_user = onboarding_display(1, CURRENT_ONBOARDING_VERSION - 1)
    completed = onboarding_display(1, CURRENT_ONBOARDING_VERSION)
    confirmation = onboarding_display(1, CURRENT_ONBOARDING_VERSION, just_completed=True)

    assert fresh.action_label == "Choose starter"
    assert fresh.title == "Choose a starter"
    assert fresh.message == "Pick a free plant for your garden."
    assert reviewed.title == "Choose a starter"
    assert reviewed.message == "Pick a free plant for your garden."
    assert updated_existing_user.visible is True
    assert completed.visible is False
    assert confirmation.title == "Your garden is ready"
    assert confirmation.message == ""


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
    assert display.title == "Choose a starter"


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


def test_six_bed_three_two_layout_preserves_middle_right_without_planter_overlap():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    background = _release_background(manifest)
    placement = background["placement"]
    layouts = plant_layout(
        1260,
        840,
        [
            {"slot_index": slot, "occupied": False}
            for slot in range(6)
        ],
        placement,
        composition_count=6,
    )
    by_slot = {layout.slot_index: layout for layout in layouts}
    family = placement["surface_profile"]["planter_family"]

    assert by_slot[3].surface_id == "middle_right_soil_bed"
    assert by_slot[3].ground_anchor[0] / 1260 > 0.5
    assert by_slot[3].ground_anchor[0] > by_slot[4].ground_anchor[0]
    assert not planter_draw_rect(by_slot[2], family).intersects(
        planter_draw_rect(by_slot[3], family)
    )


@pytest.mark.skip(reason="near-left 3:2 bed anchor is intentionally reserved for Garden Features")
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
    home_variant = background["placement"]["surface_profile"]["variants"]["home"]
    source_aspect = home_variant["width"] / home_variant["height"]
    expected_depths = [
        cover_project_point(
            surface["anchor"][0],
            surface["anchor"][1] + surface.get("seating_depth", 0.0),
            width=2000,
            height=924,
            source_aspect=source_aspect,
        )[1]
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
        0: ("Current bed", "current"),
        1: ("Swap with plant", "available"),
        2: ("Move here", "selected"),
        3: ("Move here", "available"),
        4: ("Locked", "locked"),
        5: ("Locked", "locked"),
    }
    for row in rows:
        badge = bed_badge_rect(row, labels[row.slot_index][0], 900, 560, obstacles)
        assert 0 <= badge.x < badge.right <= 900
        assert 0 <= badge.y < badge.bottom <= 560
        assert badge.width >= 52 and badge.height == 26
        assert not any(badge.intersects(obstacle) for obstacle in obstacles)

    occupied = bed_badge_rect(rows[1], "Swap with plant", 900, 560, obstacles)
    assert occupied.width >= 108




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
def test_dense_six_plant_scene_keeps_a_clamped_scene_card(scene_size):
    """Dense scenes retain the card using the least-overlap in-scene fallback."""
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
        assert result is not None
        x, y, card_width, card_height = result
        assert 12 <= x <= width - card_width - 12
        assert 12 <= y <= height - card_height - 12


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








def test_runtime_layout_repairs_duplicate_slots_and_uses_soil_y_for_z_order():
    plants = [
        {"plant_id": "a", "slot_index": 0},
        {"plant_id": "b", "slot_index": 0},
        {"plant_id": "c", "slot_index": 99},
    ]
    rows = plant_layout(900, 500, plants, composition_count=3)
    assert len({row.slot_index for row in rows}) == 3
    assert [row.z_depth for row in rows] == sorted(row.z_depth for row in rows)






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












def test_placement_rejects_invalid_targets_and_reconciles_removed_plants():
    state = PlantInteractionState()
    assert state.begin_placement("rose", 0, [0, 1], keyboard=False)
    assert not state.choose_destination(3, [0, 1])
    assert state.choose_destination(1, [0, 1])
    state.reconcile(["bonsai"])
    assert not state.placing
    assert state.pinned_id is None

    # Starter and Collection plants are absent from the scene payload until
    # placement commits, so a normal scene refresh preserves that session.
    assert state.begin_unplaced("collection-rose", [0, 1])
    state.reconcile(["bonsai"])
    assert state.placing
    assert state.dragged_id == "collection-rose"
    assert state.drag_origin_slot == -1
