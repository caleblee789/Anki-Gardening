from __future__ import annotations

import hashlib
import json
from collections import deque
from itertools import product
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ankigarden.ui.plant_display import plant_layout
from scripts.install_direct_soil_catalog_v6 import REVIEWED_CATALOG, _metadata
from scripts.process_direct_soil_asset import (
    despill_transparency_boundary,
    normalize_transparent_height,
)


pytestmark = pytest.mark.release_evidence


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
RUNTIME_ROOT = ADDON / "assets" / "v6_storybook_gouache" / "plants"
SOURCE_ROOT = ROOT / "artwork_source" / "plants" / "v6"
SPECIES = (
    "rose",
    "bonsai",
    "sunflower",
    "lavender",
    "hydrangea",
    "peony",
    "foxglove",
    "japanese_maple",
    "wisteria",
    "dahlia",
)
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SIZES = ((1260, 840, "dashboard"), (960, 640, "dashboard"), (1000, 420, "home"))


def _rows() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]


def _expected_file(species: str, stage: str) -> Path:
    return RUNTIME_ROOT / species / stage / f"{species}_{stage}_twilight_v6.webp"


def _expected_source(species: str, stage: str) -> Path:
    reviewed = REVIEWED_CATALOG[f"plant_{species}_{stage}_twilight_v6"]
    return ROOT / reviewed["source_master_file"]


def _matches(rows: list[dict], species: str, stage: str) -> list[dict]:
    asset_id = f"plant_{species}_{stage}_twilight_v6"
    return [row for row in rows if row.get("asset_id") == asset_id]


def _completed_species() -> tuple[str, ...]:
    rows = _rows()
    return tuple(
        species
        for species in SPECIES
        if all(
            len(_matches(rows, species, stage)) == 1 and _expected_file(species, stage).is_file()
            for stage in STAGES
        )
    )


COMPLETED_SPECIES = _completed_species()
COMPLETED_STAGE_CASES = tuple(
    (species, stage) for species in COMPLETED_SPECIES for stage in STAGES
)


def _background(rows: list[dict]) -> dict:
    matches = [
        row
        for row in rows
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
        and row.get("release_preferred") is True
    ]
    assert len(matches) == 1
    return matches[0]


def _asset(rows: list[dict], species: str, stage: str) -> dict:
    matches = _matches(rows, species, stage)
    assert len(matches) == 1
    return matches[0]


def _layouts(
    rows: list[dict], species: str, stage: str, width: int, height: int, context: str
) -> list:
    asset = _asset(rows, species, stage)
    return plant_layout(
        width,
        height,
        [
            {
                "plant_id": f"qa-{species}-{stage}-{slot}",
                "slot_index": slot,
                "species": species,
                "stage": stage,
                "placement": asset["placement"],
                "canvas_aspect": asset["width"] / asset["height"],
            }
            for slot in range(6)
        ],
        _background(rows)["placement"],
        surface_context=context,
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )


def _normalized_primary_silhouette(species: str, stage: str) -> set[int]:
    """Return a scale/aspect-normalized mask of the main connected plant.

    Normalizing both bounds deliberately prevents a simple resize, palette
    swap, detached sparkle field, or glow from satisfying the Rare structure
    gate. The remaining comparison reflects branches, canopy, blooms, and
    foliage arrangement.
    """
    with Image.open(_expected_file(species, stage)) as source:
        alpha = source.convert("RGBA").getchannel("A")
    scale = min(1.0, 256 / max(alpha.size))
    alpha = alpha.resize(
        (max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale))),
        Image.Resampling.NEAREST,
    ).point(lambda value: 255 if value >= 192 else 0)
    width, height = alpha.size
    data = alpha.tobytes()
    visited = bytearray(width * height)
    largest: list[int] = []
    for start, value in enumerate(data):
        if value == 0 or visited[start]:
            continue
        visited[start] = 1
        queue: deque[int] = deque([start])
        component: list[int] = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for candidate in (index - 1, index + 1, index - width, index + width):
                if (
                    candidate < 0
                    or candidate >= len(data)
                    or visited[candidate]
                    or data[candidate] == 0
                ):
                    continue
                candidate_x, candidate_y = candidate % width, candidate // width
                if abs(candidate_x - x) + abs(candidate_y - y) != 1:
                    continue
                visited[candidate] = 1
                queue.append(candidate)
        if len(component) > len(largest):
            largest = component
    assert largest
    mask = Image.new("1", (width, height))
    pixels = mask.load()
    for index in largest:
        pixels[index % width, index // width] = 1
    bounds = mask.getbbox()
    assert bounds is not None
    normalized = mask.crop(bounds).resize((88, 88), Image.Resampling.NEAREST)
    return {index for index, value in enumerate(normalized.getdata()) if value}


def _primary_silhouette_iou(species: str, left_stage: str, right_stage: str) -> float:
    left = _normalized_primary_silhouette(species, left_stage)
    right = _normalized_primary_silhouette(species, right_stage)
    return len(left & right) / len(left | right)


def test_runtime_geometry_normalizer_removes_tiny_border_artifacts_and_preserves_contact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    main = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(main)
    draw.ellipse((10, 7, 29, 34), fill=(80, 130, 70, 255))
    main_bounds = main.getchannel("A").getbbox()
    assert main_bounds is not None
    image = main.copy()
    draw = ImageDraw.Draw(image)
    draw.point((0, 39), fill=(255, 255, 255, 255))
    image.save(source, "PNG")

    normalize_transparent_height(
        source,
        output,
        vertical_scale=0.90,
        remove_small_border_components=True,
    )

    normalized = Image.open(output).convert("RGBA")
    confident = normalized.getchannel("A").point(
        lambda value: 255 if value >= 192 else 0
    )
    bounds = confident.getbbox()
    assert bounds is not None
    assert normalized.size == image.size
    assert bounds[0] > 0 and bounds[2] < image.width
    assert bounds[3] == main_bounds[3]
    assert bounds[3] - bounds[1] < 28
    assert max(
        list(normalized.getchannel("A").crop((0, 0, image.width, 1)).getdata())
        + list(normalized.getchannel("A").crop((0, image.height - 1, image.width, image.height)).getdata())
        + list(normalized.getchannel("A").crop((0, 0, 1, image.height)).getdata())
        + list(normalized.getchannel("A").crop((image.width - 1, 0, image.width, image.height)).getdata())
    ) == 0


def test_v6_library_has_no_duplicate_exact_stage_ids() -> None:
    rows = _rows()
    for species in SPECIES:
        for stage in STAGES:
            assert len(_matches(rows, species, stage)) <= 1


def test_final_v6_library_contains_every_approved_line() -> None:
    """The completed release must fail closed if any approved line disappears."""
    assert COMPLETED_SPECIES == SPECIES


@pytest.mark.parametrize(
    "species,stage",
    tuple(product(SPECIES, STAGES)),
    ids=[f"{species}-{stage}" for species, stage in product(SPECIES, STAGES)],
)
def test_final_v6_source_master_has_clean_alpha_and_exact_runtime_pixels(
    species: str, stage: str
) -> None:
    path = _expected_source(species, stage)
    assert path.is_file()
    with Image.open(path) as source, Image.open(_expected_file(species, stage)) as runtime:
        assert source.mode == "RGBA"
        assert source.size == runtime.size == (1254, 1254)
        assert source.getchannel("A").getextrema() == (0, 255)
        assert source.tobytes() == runtime.convert("RGBA").tobytes()


def test_runtime_complete_lines_are_fully_integrated_in_the_manifest() -> None:
    """A six-file line is not complete until all six exact metadata rows exist."""
    rows = _rows()
    for species in SPECIES:
        files_complete = all(_expected_file(species, stage).is_file() for stage in STAGES)
        metadata_complete = all(len(_matches(rows, species, stage)) == 1 for stage in STAGES)
        if files_complete or metadata_complete:
            assert files_complete, f"{species} has complete metadata but missing runtime stages"
            assert metadata_complete, f"{species} has six runtime stages but incomplete metadata"


@pytest.mark.parametrize(
    "species,stage",
    tuple(product(SPECIES, STAGES)),
    ids=[f"{species}-{stage}" for species, stage in product(SPECIES, STAGES)],
)
def test_final_v6_manifest_matches_idempotent_installer_metadata(
    species: str, stage: str
) -> None:
    """Lock runtime geometry, source hashes, stage mapping, and installer parity."""
    rows = _rows()
    current = _asset(rows, species, stage)
    regenerated = _metadata(species, stage, _expected_file(species, stage))
    assert current == regenerated


@pytest.mark.parametrize(
    "species,stage",
    tuple(product(SPECIES, STAGES)),
    ids=[f"{species}-{stage}" for species, stage in product(SPECIES, STAGES)],
)
def test_final_v6_manifest_points_to_canonical_source_master(
    species: str, stage: str
) -> None:
    """Source metadata must identify the selected versioned alpha master."""
    source = _expected_source(species, stage)
    asset = _asset(_rows(), species, stage)
    assert asset["source_master_file"] == source.relative_to(ROOT).as_posix()
    assert asset["source_master_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_boundary_despill_repairs_color_without_eroding_a_synthetic_leaf_edge(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dirty-edge.png"
    output = tmp_path / "clean-edge.png"
    image = Image.new("RGBA", (9, 9), (255, 0, 255, 0))
    for y in range(3, 6):
        for x in range(3, 6):
            image.putpixel((x, y), (55, 118, 61, 255))
    image.putpixel((3, 4), (244, 12, 238, 255))
    image.save(source, "PNG")
    original_alpha = image.getchannel("A").tobytes()

    despill_transparency_boundary(source, output)
    with Image.open(output) as opened:
        cleaned = opened.convert("RGBA")
    assert cleaned.getchannel("A").tobytes() == original_alpha
    assert cleaned.getpixel((3, 4)) == (55, 118, 61, 255)


def test_v6_early_stage_metadata_is_measured_from_the_revised_assets() -> None:
    """Do not freeze tiny Seed/Sprout geometry from an earlier art pass."""
    rows = _rows()
    for species in SPECIES:
        for stage in ("seed", "sprout"):
            current = _asset(rows, species, stage)
            regenerated = _metadata(species, stage, _expected_file(species, stage))
            assert regenerated["placement"] == current["placement"]
            placement = current["placement"]
            assert placement["ground_anchor"] == placement["soil_contact"]
            assert placement["ground_anchor_x"] == placement["ground_anchor"][0]
            assert 0.0 < placement["ground_anchor_x"] < 1.0


@pytest.mark.parametrize("species", COMPLETED_SPECIES)
def test_completed_v6_line_has_six_unique_direct_soil_stages(species: str) -> None:
    rows = _rows()
    assets = [_asset(rows, species, stage) for stage in STAGES]
    assert [asset["slot"]["stage"] for asset in assets] == list(STAGES)
    assert all(asset["slot"]["species"] == species for asset in assets)
    assert len({asset["asset_id"] for asset in assets}) == 6
    assert len({asset["file"] for asset in assets}) == 6

    visible_areas: list[float] = []
    for stage, asset in zip(STAGES, assets):
        placement = asset["placement"]
        assert asset["release_preferred"] is True
        assert asset["alpha"] is True
        assert asset["file"] == _expected_file(species, stage).relative_to(
            ADDON
        ).as_posix()
        assert placement["base_type"] == "direct_soil"
        assert placement["release_layout_candidate"] is True
        assert placement["review_provenance"] == REVIEWED_CATALOG[asset["asset_id"]]["placement"]["review_provenance"]
        assert placement["ground_anchor"] == placement["soil_contact"]
        assert placement["ground_anchor_x"] == placement["ground_anchor"][0]
        assert placement["anchor_x"] == placement["ground_anchor"][0]
        base_bounds = placement["base_bounds"]
        assert base_bounds[0] <= placement["ground_anchor_x"] <= base_bounds[0] + base_bounds[2]
        visible = placement["visible_bounds"]
        assert 0 < visible[0] < visible[0] + visible[2] < 1
        assert 0 < visible[1] < visible[1] + visible[3] < 1
        # Scale coefficients alone cannot compare a broad Sprout with a tall
        # Young silhouette. Compare the actual reference-size plant mass.
        visible_areas.append(_layouts(rows, species, stage, 1260, 840, "dashboard")[0].visible.area)
    assert visible_areas[:5] == sorted(visible_areas[:5])
    assert visible_areas[-1] >= visible_areas[-2] * 0.88


@pytest.mark.parametrize(
    "species,stage",
    COMPLETED_STAGE_CASES,
    ids=[f"{species}-{stage}" for species, stage in COMPLETED_STAGE_CASES],
)
def test_completed_v6_stage_has_clean_padded_alpha_and_matching_metadata(
    species: str, stage: str
) -> None:
    rows = _rows()
    asset = _asset(rows, species, stage)
    path = ADDON / asset["file"]
    assert path == _expected_file(species, stage)
    with Image.open(path) as source:
        assert source.mode == "RGBA"
        rgba = source.convert("RGBA")
    assert rgba.size == (asset["width"], asset["height"])
    red, green, blue, alpha = rgba.split()
    assert alpha.getextrema() == (0, 255)
    confident = alpha.point(lambda value: 255 if value >= 192 else 0)
    bounds = confident.getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    assert left > 0 and top > 0 and right < rgba.width and bottom < rgba.height

    visible_alpha = alpha.point(lambda value: 255 if value >= 16 else 0)
    visible_bounds = visible_alpha.getbbox()
    assert visible_bounds is not None
    visible_left, visible_top, visible_right, visible_bottom = visible_bounds
    assert (
        visible_left > 0
        and visible_top > 0
        and visible_right < rgba.width
        and visible_bottom < rgba.height
    )

    # Pure or nearly-pure chroma-key pixels must not survive with visible alpha.
    magenta = ImageChops.multiply(
        ImageChops.multiply(
            red.point(lambda value: 255 if value >= 245 else 0),
            green.point(lambda value: 255 if value <= 20 else 0),
        ),
        ImageChops.multiply(
            blue.point(lambda value: 255 if value >= 245 else 0),
            alpha.point(lambda value: 255 if value >= 16 else 0),
        ),
    )
    assert magenta.getbbox() is None

    broad_magenta_count = sum(
        1
        for pixel in rgba.crop(visible_bounds).getdata()
        if 16 <= pixel[3] < 240
        and pixel[0] >= 220
        and pixel[2] >= 180
        and pixel[1] <= 75
        and min(pixel[0], pixel[2]) - pixel[1] >= 125
    )
    assert broad_magenta_count == 0

    expected_art_bounds = [
        left / rgba.width,
        top / rgba.height,
        (right - left) / rgba.width,
        (bottom - top) / rgba.height,
    ]
    # Authored bounds may include up to three source pixels of edge padding.
    assert asset["placement"]["art_bounds"] == pytest.approx(expected_art_bounds, abs=3 / rgba.width + 1e-6)


@pytest.mark.parametrize(
    "species,stage",
    COMPLETED_STAGE_CASES,
    ids=[f"{species}-{stage}" for species, stage in COMPLETED_STAGE_CASES],
)
def test_completed_v6_stage_is_centered_seated_and_contained_on_every_bed_and_layout(
    species: str, stage: str
) -> None:
    rows = _rows()
    for width, height, context in SIZES:
        layouts = _layouts(rows, species, stage, width, height, context)
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
            assert layout.slot_envelope.contains(
                layout.visible.x + layout.visible.width / 2,
                layout.visible.y + layout.visible.height / 2,
            )
            # Home explicitly retains the original scale with the reviewed
            # artwork. Its small Young silhouettes may report readability;
            # native Garden must meet the floor. Geometry stays strict in both.
            allowed = {"below readable minimum"} if context == "home" and stage == "young" else set()
            assert set(layout.validation_warnings) <= allowed
            if stage in {"seed", "sprout"}:
                # Early stages must survive the smallest Home render without
                # relying on zoom. Seeds may remain compact, while Sprouts
                # need enough additional mass to read as the next stage.
                minimum = 20 if stage == "seed" else 23
                assert max(layout.visible.width, layout.visible.height) >= minimum


@pytest.mark.parametrize("species", COMPLETED_SPECIES)
def test_completed_v6_line_uses_one_physical_anchor_across_all_stages(species: str) -> None:
    rows = _rows()
    for width, height, context in SIZES:
        by_stage = {
            stage: _layouts(rows, species, stage, width, height, context) for stage in STAGES
        }
        for slot in range(6):
            anchors = [by_stage[stage][slot].ground_anchor for stage in STAGES]
            assert all(anchor == pytest.approx(anchors[0], abs=0.01) for anchor in anchors[1:])


@pytest.mark.parametrize("species", COMPLETED_SPECIES)
def test_completed_v6_full_bloom_remains_visible_and_within_its_slot(species: str) -> None:
    rows = _rows()
    for width, height, context in SIZES:
        flowering = _layouts(rows, species, "flowering", width, height, context)
        rare = _layouts(rows, species, "rare", width, height, context)
        for flowering_layout, rare_layout in zip(flowering, rare):
            # Rare is a reward stage, not a smaller recolor. It may trade some
            # width for a taller or more intricate silhouette, but its overall
            # rendered impact must remain close to the natural peak.
            assert rare_layout.visible.width >= flowering_layout.visible.width * 0.90
            assert rare_layout.visible.height >= flowering_layout.visible.height * 0.90
            assert rare_layout.visible.area >= flowering_layout.visible.area * 0.88
            # Approved Full Bloom redraws include wider branching crowns and a
            # taller payoff. Constrain their impact and physical slot, rather
            # than the previous library's nearly equal Flowering/Rare sizes.
            assert rare_layout.visible.width <= flowering_layout.visible.width * 1.60
            assert rare_layout.visible.height <= flowering_layout.visible.height * 1.25
            assert rare_layout.visible.area <= flowering_layout.visible.area * 2.00
            assert rare_layout.slot_envelope.contains(
                rare_layout.visible.x + rare_layout.visible.width / 2,
                rare_layout.visible.y + rare_layout.visible.height / 2,
            )
            assert not rare_layout.validation_warnings


@pytest.mark.parametrize("species", COMPLETED_SPECIES)
def test_completed_v6_rare_has_a_related_but_distinct_primary_silhouette(
    species: str,
) -> None:
    silhouette_iou = _primary_silhouette_iou(species, "flowering", "rare")

    # The upper bound fails recolors, effects-only variants, and simple resizes.
    # The permissive lower bound is only a coarse continuity check; the review
    # sheets remain the species-identity and smallest-Home visual authority.
    assert 0.12 <= silhouette_iou <= 0.82


@pytest.mark.parametrize("species", COMPLETED_SPECIES)
def test_completed_v6_flowering_has_a_visible_silhouette_payoff_over_mature(
    species: str,
) -> None:
    """Catch near-identical Mature/Flowering shapes such as the old Maple.

    A modest allowance is needed for broad shrubs such as Hydrangea, where
    the botanical payoff comes from replacing the same crown's tight green
    buds with colored mopheads as well as from the runtime scale increase.
    """
    assert _primary_silhouette_iou(species, "mature", "flowering") <= 0.93


@pytest.mark.parametrize("left_species,right_species", product(SPECIES, repeat=2))
@pytest.mark.parametrize("left_stage,right_stage", product(("flowering", "rare"), repeat=2))
def test_final_v6_peak_stages_do_not_intrude_into_adjacent_species_slots(
    left_species: str,
    right_species: str,
    left_stage: str,
    right_stage: str,
) -> None:
    """Exercise real mixed-species neighbors, not six copies of one sprite."""
    rows = _rows()
    background = _background(rows)
    for width, height, context in SIZES:
        for left_slot, right_slot in ((0, 1), (2, 3), (4, 5)):
            left_asset = _asset(rows, left_species, left_stage)
            right_asset = _asset(rows, right_species, right_stage)
            layouts = plant_layout(
                width,
                height,
                [
                    {
                        "plant_id": "qa-left",
                        "slot_index": left_slot,
                        "species": left_species,
                        "stage": left_stage,
                        "placement": left_asset["placement"],
                        "canvas_aspect": left_asset["width"] / left_asset["height"],
                    },
                    {
                        "plant_id": "qa-right",
                        "slot_index": right_slot,
                        "species": right_species,
                        "stage": right_stage,
                        "placement": right_asset["placement"],
                        "canvas_aspect": right_asset["width"] / right_asset["height"],
                    },
                ],
                background["placement"],
                surface_context=context,
                composition_count=6,
                protected_status=False,
                reserve_move_controls=False,
            )
            assert len(layouts) == 2
            by_slot = {layout.slot_index: layout for layout in layouts}
            left = by_slot[left_slot]
            right = by_slot[right_slot]
            assert not left.visible.intersects(right.visible)
            assert not left.validation_warnings
            assert not right.validation_warnings
