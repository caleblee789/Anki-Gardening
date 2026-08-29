from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from ankigarden.asset_manager import AssetPlacement
from ankigarden.ui.plant_display import plant_layout, scene_render_trace, scene_surface_variant, theme_integration_profile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "verdant_twilight_surface_v6.json"
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _runtime_placement() -> dict:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    row = next(item for item in rows if item.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6")
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


def test_runtime_twilight_profile_matches_independent_review_fixture() -> None:
    fixture = _fixture()
    runtime = _runtime_placement()["surface_profile"]
    expected = {
        key: fixture[key]
        for key in (
            "profile_id", "geometry_version", "theme", "light_direction", "key_light_origins",
                "appearance", "variant_contract", "layer_contract", "landmarks",
                "planter_family", "variant_breakpoints", "variants",
        )
    }
    assert runtime == expected
    parsed = AssetPlacement.from_manifest(_runtime_placement(), category="backgrounds")
    assert parsed.surface_profile is not None
    assert parsed.surface_profile.profile_id == "verdant_twilight_surface_v6"
    assert parsed.surface_profile.geometry_version == 6
    assert set(parsed.surface_profile.variants) == {"4:3", "16:9", "home"}
    assert all(
        set(variant["occlusion_layers"]) == {"rear", "front"}
        for variant in parsed.surface_profile.variants.values()
    )
    assert all(
        len(variant["surface_masks"]) == 6
        for variant in parsed.surface_profile.variants.values()
    )
    assert all(
        set(variant["layer_masks"]) == {
            "sky", "foliage", "ground", "architecture", "cottage_light",
            "nursery_light",
        }
        for variant in parsed.surface_profile.variants.values()
    )
    assert "weather_mode" not in parsed.surface_profile.variant_contract
    assert parsed.surface_profile.layer_contract["plant_contact_shadows_baked"] is False
    assert parsed.surface_profile.landmarks[0]["action_id"] == "garden.nursery.open"
    assert parsed.surface_profile.variants["home"]["preview_crop"] == {
        "x": 0.0,
        "y": 0.08,
        "width": 1.0,
        "height": 0.84,
    }


def test_home_preview_crop_contains_all_landmarks_and_six_space_rims() -> None:
    profile = _fixture()
    home = profile["variants"]["home"]
    crop = home["preview_crop"]
    crop_left = crop["x"]
    crop_top = crop["y"]
    crop_right = crop_left + crop["width"]
    crop_bottom = crop_top + crop["height"]

    landmark_bounds = [
        landmark["variants"]["home"]["bounds"]
        for landmark in profile["landmarks"]
    ]
    surface_bounds = [surface["outer_bounds"] for surface in home["surfaces"]]

    assert len(home["surfaces"]) == 6
    for left, top, width, height in landmark_bounds:
        assert crop_left <= left
        assert crop_top <= top
        assert left + width <= crop_right
        assert top + height <= crop_bottom
    for left, top, right, bottom in surface_bounds:
        assert crop_left <= left < right <= crop_right
        assert crop_top <= top < bottom <= crop_bottom


@pytest.mark.parametrize(
    "defect",
    ("duplicate_x", "near_duplicate_x", "compatibility", "scale", "z_order"),
)
def test_v6_profile_rejects_geometry_contract_defects(defect: str) -> None:
    placement = deepcopy(_runtime_placement())
    for variant in placement["surface_profile"]["variants"].values():
        surfaces = variant["surfaces"]
        if defect == "duplicate_x":
            surfaces[1]["anchor"][0] = surfaces[0]["anchor"][0]
        elif defect == "near_duplicate_x":
            surfaces[1]["anchor"][0] = surfaces[0]["anchor"][0] + 0.03
        elif defect == "compatibility":
            surfaces[2]["allowed_base_types"] = ["pot", "dirt_mound"]
        elif defect == "scale":
            surfaces[2]["depth_scale"] = 0.80
        elif defect == "z_order":
            surfaces[2]["anchor"][1] = 0.40
    assert AssetPlacement.from_manifest(placement, category="backgrounds").surface_profile is None


def test_soil_geometry_is_paired_and_uses_monotonic_depth_scales() -> None:
    surfaces = _fixture()["variants"]["4:3"]["surfaces"]
    by_slot = {int(surface["slot"]): surface for surface in surfaces}
    for left, right in ((0, 1), (2, 3), (4, 5)):
        assert by_slot[left]["contact_plane"][2:] == pytest.approx(
            by_slot[right]["contact_plane"][2:]
        )
        assert by_slot[left]["depth_scale"] == by_slot[right]["depth_scale"]
    assert [by_slot[index]["depth_scale"] for index in (0, 2, 4)] == [0.84, 0.92, 1.0]
    assert [by_slot[index]["anchor"][1] for index in (0, 2, 4)] == sorted(
        by_slot[index]["anchor"][1] for index in (0, 2, 4)
    )


@pytest.mark.parametrize(
    ("width", "height", "context", "expected"),
    [
        (800, 600, "dashboard", "4:3"),
        (1440, 900, "dashboard", "4:3"),
        (1920, 1080, "dashboard", "16:9"),
        (2000, 924, "dashboard", "home"),
        (1000, 420, "home", "home"),
    ],
)
@pytest.mark.skip(reason="dormant aspect-band selectors are not live Garden Feature routes")
def test_surface_variant_selection_uses_registered_aspect_bands(
    width: int, height: int, context: str, expected: str
) -> None:
    name, variant = scene_surface_variant(_runtime_placement(), width, height, context)
    assert name == expected
    assert variant["width"] > 0 and variant["height"] > 0


@pytest.mark.parametrize(
    ("count", "expected_ids"),
    [
        (1, ["far_left_soil_bed"]),
        (2, ["far_left_soil_bed", "far_right_soil_bed"]),
        (3, ["far_left_soil_bed", "far_right_soil_bed", "middle_left_soil_bed"]),
        (4, ["far_left_soil_bed", "far_right_soil_bed", "middle_left_soil_bed", "middle_right_soil_bed"]),
        (5, ["far_left_soil_bed", "far_right_soil_bed", "middle_left_soil_bed", "middle_right_soil_bed", "near_left_soil_bed"]),
        (6, ["far_left_soil_bed", "far_right_soil_bed", "middle_left_soil_bed", "middle_right_soil_bed", "near_left_soil_bed", "near_right_soil_bed"]),
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
        assert len(row.grounding.shadow_plane) >= 3
        assert row.grounding.contact_shadow.y < row.depth < row.grounding.contact_shadow.bottom


def test_render_trace_places_each_occlusion_between_physical_rows() -> None:
    rows = plant_layout(
        1920, 1080, [_plant(slot) for slot in range(6)], _runtime_placement(), composition_count=6
    )
    trace = scene_render_trace(rows)
    assert trace.index("rear:shadow:0") < trace.index("rear:plant:0")
    assert trace.index("rear:plant:3") < trace.index("rear:occlusion")
    assert trace.index("rear:occlusion") < trace.index("front:shadow:4")
    assert trace.index("front:plant:5") < trace.index("front:occlusion")
    assert trace[-1] == "interaction"


def test_twilight_lighting_is_subtle_position_aware_and_rear_recessed() -> None:
    left = theme_integration_profile("verdant_twilight", "front", 0.20, 0.85)
    right = theme_integration_profile("verdant_twilight", "front", 0.90, 0.85)
    rear = theme_integration_profile("verdant_twilight", "rear", 0.90, 0.85)
    assert -0.03 <= left["exposure"] <= 0.04
    assert -0.03 <= right["exposure"] <= 0.04
    assert right["exposure"] > left["exposure"]
    assert rear["exposure"] < right["exposure"]
    assert left["tint_alpha"] < right["tint_alpha"] <= 0.045
    assert rear["saturation"] < right["saturation"]
    assert 0 < rear["base_ao"] <= 0.08


def test_selection_and_active_state_cannot_change_physical_support_width() -> None:
    base = plant_layout(
        1600, 900, [_plant(0)], _runtime_placement(), composition_count=1
    )[0]
    selected = plant_layout(
        1600,
        900,
        [_plant(0, selected=True, is_active=True, nurtured=True, quality_tier="ultra")],
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
    rear = [by_surface[name] for name in (
        "far_left_soil_bed", "far_right_soil_bed",
        "middle_left_soil_bed", "middle_right_soil_bed",
    )]
    front = [by_surface[name] for name in ("near_left_soil_bed", "near_right_soil_bed")]
    assert max(rear) / min(rear) <= 1.10
    assert max(front) / min(front) <= 1.12
    assert all(not row.validation_warnings for row in rows)
