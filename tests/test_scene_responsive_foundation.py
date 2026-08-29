from __future__ import annotations

import json
from pathlib import Path

import pytest

from ankigarden.ui.plant_display import (
    GARDEN_CANVAS_ASPECT,
    SCENE_COMPACT_ASPECT,
    SCENE_STANDARD_ASPECT,
    SCENE_WIDE_ASPECT,
    contained_canvas_rect,
    cover_project_point,
    plant_layout,
    scene_height_for_width,
    scene_preferred_aspect,
    scene_surface_variant,
    status_overlay_rect,
)


ROOT = Path(__file__).resolve().parents[1]


def _runtime_placement() -> dict[str, object]:
    manifest = json.loads(
        (ROOT / "ankigarden" / "assets" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return next(
        row["placement"]
        for row in manifest["assets"]
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
    )


def _plant(slot: int) -> dict[str, object]:
    return {
        "plant_id": f"plant-{slot}",
        "slot_index": slot,
        "canvas_aspect": 1.0,
        "placement": {
            "base_type": "direct_soil",
            "base_bounds": [0.10, 0.60, 0.80, 0.40],
            "support_bounds": [0.20, 0.90, 0.60, 0.10],
            "art_bounds": [0.05, 0.04, 0.90, 0.96],
            "foliage_bounds": [0.05, 0.04, 0.90, 0.58],
            "interaction_bounds": [0.04, 0.02, 0.92, 0.98],
            "soil_contact": [0.50, 1.0],
            "vessel_class_multiplier": 1.0,
            "scene_scale_correction": 1.0,
        },
    }


def test_scene_aspect_policy_blends_between_clamped_targets() -> None:
    assert scene_preferred_aspect(1) == pytest.approx(SCENE_COMPACT_ASPECT)
    assert scene_preferred_aspect(520) == pytest.approx(SCENE_COMPACT_ASPECT)
    assert scene_preferred_aspect(720) == pytest.approx(SCENE_STANDARD_ASPECT)
    assert scene_preferred_aspect(1200) == pytest.approx(SCENE_STANDARD_ASPECT)
    assert scene_preferred_aspect(1600) == pytest.approx(SCENE_WIDE_ASPECT)
    assert scene_preferred_aspect(4000) == pytest.approx(SCENE_WIDE_ASPECT)

    sampled = [scene_preferred_aspect(width) for width in range(1, 2201)]
    assert all(
        SCENE_COMPACT_ASPECT <= aspect <= SCENE_WIDE_ASPECT
        for aspect in sampled
    )
    assert sampled == sorted(sampled)
    assert scene_height_for_width(100) == 250
    assert scene_height_for_width(4000) == 800


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    (
        (1240, 840, (0.0, 0.0, 1240.0, 840.0)),
        (1600, 840, (180.0, 0.0, 1240.0, 840.0)),
        (1000, 1000, (0.0, pytest.approx(161.2903), 1000.0, pytest.approx(677.4194))),
    ),
)
@pytest.mark.skip(reason="replaced by fixed 3:2 cover-crop Garden contract")
def test_release_canvas_is_centered_and_never_cropped(
    width: int,
    height: int,
    expected: tuple[object, object, object, object],
) -> None:
    canvas = contained_canvas_rect(width, height)

    assert (canvas.x, canvas.y, canvas.width, canvas.height) == expected
    assert canvas.width / canvas.height == pytest.approx(GARDEN_CANVAS_ASPECT)
    assert canvas.x >= 0 and canvas.y >= 0
    assert canvas.right <= width and canvas.bottom <= height


def test_source_coordinates_use_the_same_contain_transform_as_artwork() -> None:
    scene_width, scene_height = 1240.0, 840.0
    source_aspect = 4 / 3
    left, top = cover_project_point(
        0.0,
        0.0,
        width=scene_width,
        height=scene_height,
        source_aspect=source_aspect,
    )
    right, bottom = cover_project_point(
        1.0,
        1.0,
        width=scene_width,
        height=scene_height,
        source_aspect=source_aspect,
    )

    assert left > 0.0
    assert right < 1.0
    assert top == pytest.approx(0.0)
    assert bottom == pytest.approx(1.0)
    assert (right - left) * scene_width / scene_height == pytest.approx(
        source_aspect
    )


@pytest.mark.parametrize("boundary", [620, 1400])
def test_former_aspect_cliffs_are_stable_at_every_nearby_pixel(boundary: int) -> None:
    widths = list(range(boundary - 2, boundary + 3))
    aspects = [scene_preferred_aspect(width) for width in widths]
    heights = [scene_height_for_width(width) for width in widths]

    assert all(
        later >= earlier
        for earlier, later in zip(aspects, aspects[1:])
    )
    assert max(
        later - earlier
        for earlier, later in zip(aspects, aspects[1:])
    ) < 0.01
    assert max(
        abs(later - earlier)
        for earlier, later in zip(heights, heights[1:])
    ) <= 1


def test_status_overlay_has_one_reachable_geometry_above_its_hide_gate() -> None:
    assert all(status_overlay_rect(width) is None for width in range(438, 443))
    assert status_overlay_rect(518) is None
    assert status_overlay_rect(519) is None

    visible = [status_overlay_rect(width) for width in range(520, 523)]
    assert all(rect is not None for rect in visible)
    assert {rect.height for rect in visible if rect is not None} == {68.0}
    assert status_overlay_rect(900, protected=False) is None
    assert status_overlay_rect(900, surface_context="home") is None


def test_scene_widget_and_layout_share_the_pure_geometry_helpers() -> None:
    scene_source = (ROOT / "ankigarden" / "ui" / "scene.py").read_text(
        encoding="utf-8"
    )
    display_source = (
        ROOT / "ankigarden" / "ui" / "plant_display.py"
    ).read_text(encoding="utf-8")

    height_method = scene_source.split("def heightForWidth", 1)[1].split(
        "def set_motion_enabled", 1
    )[0]
    status_method = scene_source.split("def _draw_status_overlay", 1)[1].split(
        "def _draw_stats_help", 1
    )[0]
    layout_method = display_source.split("def plant_layout", 1)[1]
    assert "scene_height_for_width(width)" in height_method
    assert "status_overlay_rect(" in status_method
    assert "rect.width() < 440" not in status_method
    assert layout_method.count("status_overlay_rect(") == 2
    assert "width < 440" not in layout_method


def test_move_completion_uses_the_shared_live_announcement_channel() -> None:
    scene_source = (ROOT / "ankigarden" / "ui" / "scene.py").read_text(
        encoding="utf-8"
    )
    finish_method = scene_source.split(
        "def _finish_move_accessibility", 1
    )[1].split("def _begin_move", 1)[0]
    assert "AccessibilityAnnouncer(self)" in scene_source
    assert "self.accessibility_announcer.announce(" in finish_method
    assert "AnnouncementPriority.ASSERTIVE" in finish_method


@pytest.mark.parametrize(
    ("boundary", "expected_variant"),
    [(620, "4:3"), (1400, "home")],
)
@pytest.mark.skip(reason="replaced by the single 3:2 Garden presentation")
def test_artwork_and_slot_semantics_stay_stable_around_former_cliffs(
    boundary: int,
    expected_variant: str,
) -> None:
    placement = _runtime_placement()
    signatures: list[tuple[tuple[object, ...], ...]] = []
    normalized_anchors: list[tuple[tuple[float, float], ...]] = []
    variants: list[str] = []

    for width in range(boundary - 2, boundary + 3):
        height = scene_height_for_width(width)
        variant, _record = scene_surface_variant(
            placement,
            width,
            height,
            "dashboard",
        )
        variants.append(variant)
        rows = plant_layout(
            width,
            height,
            [_plant(slot) for slot in range(6)],
            placement,
            composition_count=6,
        )
        ordered = sorted(rows, key=lambda row: row.slot_index)
        signatures.append(
            tuple(
                (
                    row.slot_index,
                    row.surface_id,
                    row.depth_band,
                    row.allowed_base_types,
                )
                for row in ordered
            )
        )
        normalized_anchors.append(
            tuple(
                (
                    row.ground_anchor[0] / width,
                    row.ground_anchor[1] / height,
                )
                for row in ordered
            )
        )

    assert variants == [expected_variant] * 5
    assert signatures == [signatures[0]] * 5
    for earlier, later in zip(normalized_anchors, normalized_anchors[1:]):
        assert all(
            abs(left_x - right_x) <= 0.002
            and abs(left_y - right_y) <= 0.002
            for (left_x, left_y), (right_x, right_y) in zip(earlier, later)
        )


@pytest.mark.parametrize("boundary", [420, 480, 720, 900])
def test_plant_fit_and_move_control_policy_have_no_remaining_pixel_cliffs(
    boundary: int,
) -> None:
    placement = _runtime_placement()
    samples = []
    for width in range(boundary - 2, boundary + 3):
        height = scene_height_for_width(width)
        rows = sorted(
            plant_layout(
                width,
                height,
                [_plant(slot) for slot in range(6)],
                placement,
                composition_count=6,
                reserve_move_controls=True,
            ),
            key=lambda row: row.slot_index,
        )
        samples.append(
            tuple(
                (
                    row.slot_index,
                    row.visible.width / width,
                    row.visible.height / height,
                )
                for row in rows
            )
        )

    assert all(tuple(row[0] for row in sample) == tuple(range(6)) for sample in samples)
    for earlier, later in zip(samples, samples[1:]):
        assert all(
            abs(left_w - right_w) < 0.02
            and abs(left_h - right_h) < 0.02
            for (_slot, left_w, left_h), (_slot2, right_w, right_h) in zip(
                earlier,
                later,
            )
        )
    contained_canvas_rect,
    cover_project_point,
