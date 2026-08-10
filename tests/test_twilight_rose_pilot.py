from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ankigarden.asset_manager import AssetPlacement
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    CURRENT_CATALOG_SPECIES_ORDER,
    HISTORICAL_PLANT_SPECIES_ORDER,
    PLANT_SPECIES,
)
from ankigarden.ui.plant_display import plant_layout


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
FIXTURE = ROOT / "tests" / "fixtures" / "verdant_twilight_surface_v6.json"
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SIZES = ((960, 720, "dashboard"), (960, 540, "dashboard"), (960, 400, "home"))


def _rows() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]


def _background(rows: list[dict]) -> dict:
    matches = [
        row for row in rows
        if row.get("category") == "backgrounds" and row.get("release_preferred") is True
    ]
    assert [row["asset_id"] for row in matches] == ["bg_verdant_twilight_any_soil_master_v6"]
    return matches[0]


def _rose(rows: list[dict], stage: str) -> dict:
    matches = [
        row for row in rows
        if row.get("asset_id") == f"plant_rose_{stage}_twilight_v6"
    ]
    assert len(matches) == 1
    return matches[0]


def test_v6_background_matches_the_review_fixture_and_is_direct_soil_only() -> None:
    background = _background(_rows())
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert background["placement"]["surface_profile"] == fixture
    parsed = AssetPlacement.from_manifest(background["placement"], category="backgrounds")
    assert parsed.surface_profile is not None
    assert parsed.surface_profile.profile_id == "verdant_twilight_surface_v6"
    assert parsed.surface_profile.geometry_version == 6
    for variant in parsed.surface_profile.variants.values():
        assert len(variant["surfaces"]) == 6
        assert all(surface["surface_kind"] == "soil" for surface in variant["surfaces"])
        assert all(surface["allowed_base_types"] == ["direct_soil"] for surface in variant["surfaces"])


def test_rose_pilot_has_six_clean_direct_soil_assets_with_monotonic_growth() -> None:
    rows = _rows()
    scales: list[float] = []
    areas: list[float] = []
    for stage in STAGES:
        asset = _rose(rows, stage)
        placement = asset["placement"]
        assert asset["release_preferred"] is True
        assert asset["alpha"] is True
        assert placement["base_type"] == "direct_soil"
        assert placement["ground_anchor"] == placement["soil_contact"]
        assert placement["release_layout_candidate"] is True
        path = ROOT / "ankigarden" / asset["file"]
        with Image.open(path) as image:
            confident = image.getchannel("A").point(lambda value: 255 if value >= 192 else 0)
            left, top, right, bottom = confident.getbbox() or (0, 0, 0, 0)
        confident_bounds = [
            left / asset["width"], top / asset["height"],
            (right - left) / asset["width"], (bottom - top) / asset["height"],
        ]
        expected = placement["visible_bounds"]
        assert 0 < expected[0] < expected[0] + expected[2] < 1
        assert 0 < expected[1] < expected[1] + expected[3] < 1
        assert confident_bounds[0] - 0.01 <= expected[0]
        assert confident_bounds[1] - 0.01 <= expected[1]
        assert expected[0] + expected[2] <= confident_bounds[0] + confident_bounds[2] + 0.01
        assert expected[1] + expected[3] <= confident_bounds[1] + confident_bounds[3] + 0.01
        assert placement["art_bounds"] == pytest.approx(confident_bounds, abs=1e-6)
        scales.append(placement["scene_scale_correction"] * placement["visual_scale_correction"])
        areas.append(expected[2] * expected[3])
    assert scales[:-1] == sorted(scales[:-1])
    assert all(right >= left * 1.14 for left, right in zip(scales, scales[1:5]))
    assert scales[-1] == pytest.approx(scales[-2], rel=0.03)
    assert areas[:5] == sorted(areas[:5])
    # Rare reorganizes the natural peak into an open prestige tree with a
    # dominant crown bloom. Its source-square occupancy may trade a sliver of
    # area for branch windows, but it must still read as a full reward stage.
    assert areas[-1] >= areas[-2] * 0.95


@pytest.mark.parametrize("stage", STAGES)
def test_each_rose_stage_is_centered_and_seated_on_all_six_beds(stage: str) -> None:
    rows = _rows()
    background = _background(rows)
    asset = _rose(rows, stage)
    items = [
        {
            "plant_id": f"rose-{stage}-{slot}",
            "slot_index": slot,
            "species": "rose",
            "stage": stage,
            "placement": asset["placement"],
            "canvas_aspect": asset["width"] / asset["height"],
        }
        for slot in range(6)
    ]
    for width, height, context in SIZES:
        layouts = plant_layout(
            width,
            height,
            items,
            background["placement"],
            surface_context=context,
            composition_count=6,
            protected_status=False,
            reserve_move_controls=False,
        )
        assert len(layouts) == 6
        assert [layout.z_depth for layout in layouts] == sorted(layout.z_depth for layout in layouts)
        for layout in layouts:
            assert layout.surface_kind == "soil"
            assert layout.allowed_base_types == ("direct_soil",)
            assert layout.contact_plane.contains(*layout.ground_anchor)
            assert layout.base_rect.x >= layout.contact_plane.x - 0.5
            assert layout.base_rect.right <= layout.contact_plane.right + 0.5
            assert layout.target_error <= 0.01
            assert layout.visible.x >= 0 and layout.visible.right <= width
            assert layout.visible.y >= 0 and layout.visible.bottom <= height
            assert not layout.validation_warnings
            if stage == "seed":
                assert layout.visible.width >= 18
                assert layout.visible.height >= 14


def test_rare_uses_detail_not_scale_and_stays_inside_the_flowering_footprint() -> None:
    rows = _rows()
    background = _background(rows)
    flowering = _rose(rows, "flowering")
    rare = _rose(rows, "rare")
    assert rare["placement"]["visual_scale_correction"] < 1.10
    for width, height, context in SIZES:
        def layouts(asset: dict) -> list:
            return plant_layout(
                width,
                height,
                [
                    {
                        "plant_id": f"{asset['slot']['stage']}-{slot}",
                        "slot_index": slot,
                        "placement": asset["placement"],
                        "canvas_aspect": asset["width"] / asset["height"],
                    }
                    for slot in range(6)
                ],
                background["placement"],
                surface_context=context,
                composition_count=6,
                protected_status=False,
                reserve_move_controls=False,
            )

        flowering_rows = layouts(flowering)
        rare_rows = layouts(rare)
        for flowering_layout, rare_layout in zip(flowering_rows, rare_rows):
            assert rare_layout.visible.width <= flowering_layout.visible.width
            assert rare_layout.visible.height <= flowering_layout.visible.height * 1.08
            assert rare_layout.slot_envelope.contains(
                rare_layout.visible.x + rare_layout.visible.width / 2,
                rare_layout.visible.y + rare_layout.visible.height / 2,
            )
            assert not rare_layout.validation_warnings


def test_catalog_and_economy_expose_ten_acquirable_species_without_retiring_saved_species() -> None:
    assert CURRENT_CATALOG_SPECIES_ORDER == (
        "bonsai", "rose", "sunflower", "lavender", "hydrangea", "peony",
        "foxglove", "japanese_maple", "wisteria", "dahlia",
    )
    assert GardenGameEngine.SPECIES_PRICES == {
        "bonsai": 100,
        "rose": 100,
        "sunflower": 150,
        "lavender": 200,
        "hydrangea": 250,
        "peony": 300,
        "foxglove": 350,
        "japanese_maple": 400,
        "wisteria": 500,
        "dahlia": 600,
    }
    assert set(CURRENT_CATALOG_SPECIES_ORDER).issubset(PLANT_SPECIES)
    assert set(HISTORICAL_PLANT_SPECIES_ORDER).issubset(PLANT_SPECIES)
