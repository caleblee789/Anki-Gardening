from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_bundled_plants_match_independent_geometry_v2_fixture():
    manifest = json.loads((ROOT / "ankigarden/assets/manifest.json").read_text("utf-8"))
    fixture = json.loads((ROOT / "tests/fixtures/approved_asset_geometry_v2.json").read_text("utf-8"))
    plants = [row for row in manifest["assets"] if row.get("category") == "plants"]
    assert len(plants) == len(fixture["assets"]) == 150
    geometry_keys = {
        "geometry_version", "review_provenance", "vessel_class",
        "vessel_class_multiplier", "scene_scale_correction", "art_bounds",
        "base_bounds", "support_bounds", "foliage_bounds",
        "plant_above_rim_bounds", "soil_contact", "interaction_bounds",
    }
    for row in plants:
        approved = fixture["assets"][row["asset_id"]]
        placement = row["placement"]
        assert {key: placement[key] for key in geometry_keys} == {
            key: approved[key] for key in geometry_keys
        }, row["asset_id"]


def test_species_stage_readability_metrics_are_positive_and_reviewed():
    fixture = json.loads((ROOT / "tests/fixtures/approved_asset_geometry_v2.json").read_text("utf-8"))
    for asset_id, geometry in fixture["assets"].items():
        metrics = geometry["metrics"]
        assert metrics["support_width"] > 0.02, asset_id
        assert metrics["vessel_height"] > 0.01, asset_id
        assert metrics["growth_above_rim_height"] > 0.001, asset_id
        assert geometry["review_provenance"], asset_id
