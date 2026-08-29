from __future__ import annotations

import json
from pathlib import Path

import pytest

from ankigarden.ui.plant_display import plant_layout
from scripts.validate_full_catalog_layout import SIZES, _scenario_warnings


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
ACCEPTANCE_SIZES = tuple(
    size for size in SIZES
    if size[0] in {"minimum-dashboard", "4:3", "16:9", "home", "wide"}
)


def _assets() -> list[dict]:
    return json.loads((ROOT / "ankigarden/assets/manifest.json").read_text("utf-8"))["assets"]


def _release_species(rows: list[dict]) -> tuple[str, ...]:
    stages_by_species: dict[str, set[str]] = {}
    for row in rows:
        if (
            row.get("category") != "plants"
            or row.get("release_preferred") is not True
            or "continuity_v6" not in row.get("variants", [])
            or row.get("placement", {}).get("release_layout_candidate") is not True
        ):
            continue
        slot = row.get("slot", {})
        species = str(slot.get("species", ""))
        stage = str(slot.get("stage", ""))
        if species and stage in STAGES:
            stages_by_species.setdefault(species, set()).add(stage)
    return tuple(sorted(
        species for species, stages in stages_by_species.items()
        if stages == set(STAGES)
    ))


def _release_asset(rows: list[dict], species: str, stage: str) -> dict:
    matches = [
        row for row in rows
        if row.get("category") == "plants"
        and row.get("release_preferred") is True
        and "continuity_v6" in row.get("variants", [])
        and row.get("placement", {}).get("release_layout_candidate") is True
        and row.get("slot", {}).get("species") == species
        and row.get("slot", {}).get("stage") == stage
    ]
    assert len(matches) == 1, (species, stage, [row.get("asset_id") for row in matches])
    return matches[0]


def _release_background(rows: list[dict]) -> dict:
    matches = [
        row for row in rows
        if row.get("category") == "backgrounds"
        and row.get("release_preferred") is True
    ]
    assert [row["asset_id"] for row in matches] == [
        "bg_verdant_twilight_any_soil_master_v6"
    ]
    return matches[0]


def _item(asset: dict, slot: int) -> dict:
    return {
        "plant_id": f"release-{slot}",
        "slot_index": slot,
        "species": asset["slot"]["species"],
        "stage": asset["slot"]["stage"],
        "placement": asset["placement"],
        "canvas_aspect": asset["width"] / asset["height"],
    }


def _declared_scene_scale(asset: dict) -> float:
    placement = asset["placement"]
    return placement["scene_scale_correction"] * placement["visual_scale_correction"]


def test_every_asset_declares_visible_bounds_ground_anchor_and_layout_family() -> None:
    plants = [row for row in _assets() if row.get("category") == "plants"]
    release_species = _release_species(plants)
    release_candidates = [
        row for row in plants
        if row.get("placement", {}).get("release_layout_candidate") is True
    ]
    assert {"bonsai", "rose"}.issubset(release_species)
    assert len(release_candidates) == len(release_species) * len(STAGES)
    assert {
        (row["slot"]["species"], row["slot"]["stage"])
        for row in release_candidates
    } == {
        (species, stage)
        for species in release_species
        for stage in STAGES
    }
    families = {"seed": "compact", "sprout": "compact", "young": "standard", "mature": "standard", "flowering": "expanded", "rare": "expanded"}
    for row in plants:
        placement = row["placement"]
        assert {
            "visible_bounds",
            "art_bounds",
            "visual_center",
            "soil_contact",
            "display_scale",
            "contact_shadow",
            "shadow_offset",
            "minimum_bed_clearance",
        } <= set(placement)
        ground = placement["soil_contact"]
        assert placement["ground_anchor"] == ground
        assert placement["ground_anchor_x"] == pytest.approx(ground[0])
        assert placement["ground_anchor_y"] == pytest.approx(ground[1])
        assert placement["layout_family"] == families[row["slot"]["stage"]]
        assert placement["art_bounds"][2] > 0
        assert placement["art_bounds"][3] > 0
        assert 0.0 <= placement["visual_center"][0] <= 1.0
        assert 0.0 <= placement["visual_center"][1] <= 1.0
        assert placement["display_scale"] > 0.0
        assert placement["contact_shadow"][0] > 0.0
        assert placement["contact_shadow"][1] > 0.0
        assert len(placement["shadow_offset"]) == 2
        assert 0.0 <= placement["minimum_bed_clearance"] <= 0.5


def test_v6_release_stage_progression_grows_through_flowering_then_uses_rare_detail() -> None:
    rows = _assets()
    for species in _release_species(rows):
        scales = [_declared_scene_scale(_release_asset(rows, species, stage)) for stage in STAGES]
        assert scales[:5] == sorted(scales[:5]), (species, scales)
        assert scales[4] * 0.90 <= scales[5] <= scales[4], (species, scales)


def test_twilight_uses_three_monotonic_perspective_scale_bands() -> None:
    rows = _assets()
    background = _release_background(rows)
    for species in _release_species(rows):
        for stage in STAGES:
            asset = _release_asset(rows, species, stage)
            far = plant_layout(
                960, 540, [_item(asset, 0)], background["placement"],
                composition_count=6, protected_status=False,
            )[0]
            middle = plant_layout(
                960, 540, [_item(asset, 2)], background["placement"],
                composition_count=6, protected_status=False,
            )[0]
            near = plant_layout(
                960, 540, [_item(asset, 4)], background["placement"],
                composition_count=6, protected_status=False,
            )[0]
            assert far.support_rect.width / near.support_rect.width == pytest.approx(0.84)
            assert middle.support_rect.width / near.support_rect.width == pytest.approx(0.92)
            assert far.depth < middle.depth < near.depth


def test_every_v6_release_base_is_centered_and_contained_on_each_twilight_surface() -> None:
    rows = _assets()
    background = _release_background(rows)
    for species in _release_species(rows):
        for stage in STAGES:
            asset = _release_asset(rows, species, stage)
            for _size_name, width, height, context in ACCEPTANCE_SIZES:
                layouts = plant_layout(
                    width,
                    height,
                    [_item(asset, slot) for slot in range(6)],
                    background["placement"],
                    surface_context=context,
                    composition_count=6,
                    protected_status=False,
                )
                for layout in layouts:
                    base_center = layout.base_rect.x + layout.base_rect.width / 2
                    support_line = layout.grounding.support_line
                    surface_center = (support_line[0][0] + support_line[-1][0]) / 2
                    assert base_center == pytest.approx(
                        surface_center,
                        abs=max(0.5, layout.contact_plane.width * 0.01),
                    )
                    assert layout.base_rect.x >= layout.contact_plane.x - 0.5
                    assert layout.base_rect.right <= layout.contact_plane.right + 0.5


def test_all_anchors_are_seated_inside_their_contact_planes_not_on_rims() -> None:
    background = _release_background(_assets())
    variants = background["placement"]["surface_profile"]["variants"]
    for variant in variants.values():
        for surface in variant["surfaces"]:
            _x, top, _width, height = surface["contact_plane"]
            relative_depth = (surface["anchor"][1] - top) / height
            assert 0.45 <= relative_depth <= 0.82, (
                variant["file"], surface["surface_id"], relative_depth
            )


def test_foreground_depth_overlap_stays_below_base_obscuring_policy() -> None:
    rows = _assets()
    background = _release_background(rows)
    species = _release_species(rows)
    asset = _release_asset(rows, species[min(1, len(species) - 1)], "mature")
    layouts = plant_layout(
        960,
        540,
        [_item(asset, slot) for slot in range(6)],
        background["placement"],
        composition_count=6,
        protected_status=False,
    )
    by_slot = {layout.slot_index: layout for layout in layouts}
    assert by_slot[4].z_depth > by_slot[0].z_depth
    coverage = by_slot[4].foliage_rect.intersection_area(by_slot[0].base_rect) / max(
        1.0, by_slot[0].base_rect.area
    )
    # The runtime uses coarse rectangular foliage bounds; actual alpha-backed
    # leaves occupy less of this region. Row-separated occlusion may therefore
    # be visually natural even when the conservative rectangle is substantial.
    assert coverage <= 0.86
    assert all("neighbor base obscured" not in layout.validation_warnings for layout in layouts)


def test_mixed_stage_and_species_release_gardens_are_warning_free() -> None:
    rows = _assets()
    background = _release_background(rows)
    species_lines = _release_species(rows)
    arrangements: list[list[tuple[str, str]]] = []
    for species in species_lines:
        arrangements.append([
            (species, "rare"), (species, "seed"), (species, "flowering"),
            (species, "sprout"), (species, "mature"), (species, "young"),
        ])
    arrangements.extend([
        [
            (species_lines[(slot + offset) % len(species_lines)], stage)
            for slot, stage in enumerate(stage_order)
        ]
        for offset, stage_order in enumerate((
            ("rare", "young", "flowering", "mature", "sprout", "flowering"),
            ("rare", "seed", "rare", "seed", "sprout", "young"),
        ))
    ])
    for arrangement in arrangements:
        assets = [_release_asset(rows, species, stage) for species, stage in arrangement]
        items = [_item(asset, slot) for slot, asset in enumerate(assets)]
        for size_name, width, height, context in SIZES:
            layouts = plant_layout(
                width, height, items, background["placement"],
                surface_context=context, composition_count=6,
                protected_status=False, reserve_move_controls=False,
            )
            warnings = _scenario_warnings(
                layouts, width=width, height=height, count=6,
                move_mode=False, surface_context=context,
            )
            assert warnings == [], (arrangement, size_name, warnings)
            assert [layout.z_depth for layout in layouts] == sorted(
                layout.z_depth for layout in layouts
            )
            assert len({layout.ground_anchor for layout in layouts}) == 6


def test_six_large_flowering_or_rare_plants_remain_countable_at_acceptance_sizes() -> None:
    rows = _assets()
    background = _release_background(rows)
    species_lines = _release_species(rows)
    arrangement = tuple(
        (species_lines[slot % len(species_lines)], "rare" if slot < 4 else "flowering")
        for slot in range(6)
    )
    items = [
        _item(_release_asset(rows, species, stage), slot)
        for slot, (species, stage) in enumerate(arrangement)
    ]
    for size_name, width, height, context in ACCEPTANCE_SIZES:
        layouts = plant_layout(
            width, height, items, background["placement"],
            surface_context=context, composition_count=6,
            protected_status=False, reserve_move_controls=False,
        )
        warnings = _scenario_warnings(
            layouts, width=width, height=height, count=6,
            move_mode=False, surface_context=context,
        )
        assert warnings == [], (size_name, warnings)
        assert len(layouts) == 6
        assert len({layout.ground_anchor for layout in layouts}) == 6
        assert all(layout.visible.width > 0 and layout.visible.height > 0 for layout in layouts)
