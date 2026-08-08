from __future__ import annotations

import json
from pathlib import Path

import pytest

from ankigarden.asset_manager import AssetPlacement
from ankigarden.ui.plant_display import plant_layout, scene_surface_variant


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "verdant_dusk_surface_v1.json"
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _runtime_placement() -> dict:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    row = next(item for item in rows if item.get("asset_id") == "bg_verdant_dusk_summer_storybook_v3")
    return row["placement"]


def _plant(slot: int, **overrides: object) -> dict:
    item = {
        "plant_id": f"plant-{slot}",
        "slot_index": slot,
        "canvas_aspect": 1.0,
        "placement": {
            "base_type": "pot",
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
    item.update(overrides)
    return item


def test_runtime_dusk_profile_matches_independent_review_fixture() -> None:
    fixture = _fixture()
    runtime = _runtime_placement()["surface_profile"]
    expected = {
        key: fixture[key]
        for key in (
            "profile_id", "geometry_version", "theme", "light_direction",
            "variant_breakpoints", "variants",
        )
    }
    assert runtime == expected
    parsed = AssetPlacement.from_manifest(_runtime_placement(), category="backgrounds")
    assert parsed.surface_profile is not None
    assert parsed.surface_profile.profile_id == "verdant_dusk_surface_v1"
    assert set(parsed.surface_profile.variants) == {"4:3", "16:9", "home"}


@pytest.mark.parametrize(
    ("width", "height", "context", "expected"),
    [
        (800, 600, "dashboard", "4:3"),
        (1440, 900, "dashboard", "16:9"),
        (1920, 1080, "dashboard", "16:9"),
        (2000, 924, "dashboard", "home"),
        (1000, 420, "home", "home"),
    ],
)
def test_surface_variant_selection_uses_registered_aspect_bands(
    width: int, height: int, context: str, expected: str
) -> None:
    name, variant = scene_surface_variant(_runtime_placement(), width, height, context)
    assert name == expected
    assert variant["width"] > 0 and variant["height"] > 0


@pytest.mark.parametrize(
    ("count", "expected_ids"),
    [
        (1, ["front_center"]),
        (2, ["front_left", "front_right"]),
        (3, ["rear_center", "front_left", "front_right"]),
        (4, ["rear_left", "rear_right", "front_left", "front_right"]),
        (5, ["rear_left", "rear_right", "front_left", "front_center", "front_right"]),
        (6, ["rear_left", "rear_center", "rear_right", "front_left", "front_center", "front_right"]),
    ],
)
def test_every_count_maps_to_real_painted_surfaces(count: int, expected_ids: list[str]) -> None:
    rows = plant_layout(
        1920,
        1080,
        [_plant(slot) for slot in range(count)],
        _runtime_placement(),
        composition_count=count,
    )
    by_slot = {row.slot_index: row for row in rows}
    assert [by_slot[slot].surface_id for slot in range(count)] == expected_ids
    assert all(row.contact_plane.contains(row.support_rect.x, row.depth) for row in rows)
    assert all(row.hit.width >= 44 and row.hit.height >= 44 for row in rows)


def test_registered_soil_y_is_immutable_and_z_order_uses_it_exclusively() -> None:
    rows = plant_layout(
        2000,
        924,
        [_plant(slot) for slot in range(6)],
        _runtime_placement(),
        composition_count=6,
    )
    assert [row.z_depth for row in rows] == sorted(row.z_depth for row in rows)
    for row in rows:
        assert abs(row.support_rect.bottom - row.depth) < 0.01
        assert row.contact_plane.y <= row.depth <= row.contact_plane.bottom


def test_selection_nurture_and_focus_cannot_change_physical_support_width() -> None:
    base = plant_layout(
        1600, 900, [_plant(0)], _runtime_placement(), composition_count=1
    )[0]
    selected = plant_layout(
        1600,
        900,
        [_plant(0, selected=True, is_focus=True, nurtured=True, quality_tier="ultra")],
        _runtime_placement(),
        composition_count=1,
    )[0]
    assert selected.support_rect.width == pytest.approx(base.support_rect.width)
    assert selected.depth == pytest.approx(base.depth)
    assert selected.effective_scale == pytest.approx(base.effective_scale)


def test_same_row_support_targets_remain_balanced() -> None:
    rows = plant_layout(
        2560,
        1440,
        [_plant(slot) for slot in range(6)],
        _runtime_placement(),
        composition_count=6,
    )
    by_surface = {row.surface_id: row.support_rect.width for row in rows}
    rear = [by_surface[name] for name in ("rear_left", "rear_center", "rear_right")]
    front = [by_surface[name] for name in ("front_left", "front_center", "front_right")]
    assert max(rear) / min(rear) <= 1.10
    assert max(front) / min(front) <= 1.12
    assert all(not row.validation_warnings for row in rows)
