from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageChops

from ankigarden.asset_manager import AssetManager, SceneSurfaceProfile
from ankigarden.ui.plant_display import plant_layout, scene_render_trace
from scripts.render_planter_geometry_regression import (
    FIXTURES,
    SCALES,
    BASE_SIZE,
    _geometry_row,
    _load_contract,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "tests" / "fixtures" / "verdant_twilight_surface_v6.json"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "planter_geometry_baseline.json"
ADDON = ROOT / "ankigarden"
BEDLESS_REPORT = (
    ROOT
    / "artwork_source"
    / "backgrounds"
    / "bedless_v6"
    / "bedless-backgrounds.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _current_geometry() -> dict[str, object]:
    background, plants, placement = _load_contract()
    del background
    scales: dict[str, object] = {}
    for scale in SCALES:
        width = round(BASE_SIZE[0] * scale)
        height = round(BASE_SIZE[1] * scale)
        name = f"{round(scale * 100)}pct"
        layouts = plant_layout(
            width,
            height,
            plants,
            placement,
            surface_context="dashboard",
            composition_count=6,
            protected_status=False,
        )
        by_slot = {row.slot_index: row for row in layouts}
        scales[name] = {
            "width": width,
            "height": height,
            "geometry": [
                _geometry_row(plants[slot], by_slot[slot])
                for slot in range(6)
            ],
            "render_order": list(scene_render_trace(layouts)),
        }
    return {
        "label": "before",
        "fixtures": [list(value) for value in FIXTURES],
        "scales": scales,
    }


def test_planter_change_preserves_prechange_geometry_at_all_required_scales() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert _current_geometry() == baseline


def test_planter_metadata_cannot_influence_plant_layout() -> None:
    _background, plants, placement = _load_contract()
    without_planters = copy.deepcopy(placement)
    without_planters["surface_profile"].pop("planter_family", None)
    for scale in SCALES:
        width = round(BASE_SIZE[0] * scale)
        height = round(BASE_SIZE[1] * scale)
        with_family = plant_layout(
            width,
            height,
            plants,
            placement,
            composition_count=6,
            protected_status=False,
        )
        without_family = plant_layout(
            width,
            height,
            plants,
            without_planters,
            composition_count=6,
            protected_status=False,
        )
        assert with_family == without_family


def test_planter_family_maps_rows_without_changing_bed_ids() -> None:
    raw_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile = SceneSurfaceProfile.from_manifest(raw_profile)
    assert profile is not None
    family = profile.to_dict()["planter_family"]
    assert family["family_id"] == "storybook_stone_planter_v1"
    assert family["background_contract"] == "bedless_v1"
    assert family["canvas"] == [1024, 512]
    assert family["soil_anchor"] == [0.5, 0.4296875]
    assert list(family["variants"]) == ["back", "middle", "front"]

    expected_ids = [
        "far_left_soil_bed",
        "far_right_soil_bed",
        "middle_left_soil_bed",
        "middle_right_soil_bed",
        "near_left_soil_bed",
        "near_right_soil_bed",
    ]
    expected_bands = ["far", "far", "middle", "middle", "near", "near"]
    for variant in profile.variants.values():
        surfaces = sorted(variant["surfaces"], key=lambda row: int(row["slot"]))
        assert [row["surface_id"] for row in surfaces] == expected_ids
        assert [row["depth_band"] for row in surfaces] == expected_bands
        assert [row["depth_scale"] for row in surfaces] == [0.84, 0.84, 0.92, 0.92, 1.0, 1.0]


def test_every_scenery_reskin_inherits_the_one_global_planter_family() -> None:
    rows = json.loads(
        (ADDON / "assets" / "manifest.json").read_text(encoding="utf-8")
    )["assets"]
    backgrounds = {
        str(row.get("asset_id", "")): row
        for row in rows
        if row.get("category") == "backgrounds"
    }
    canonical_id = "bg_verdant_twilight_any_soil_master_v6"
    scenery = [
        row
        for row in backgrounds.values()
        if "scenery_reskin" in row.get("variants", [])
    ]
    assert len(scenery) == 8

    # Exercise the same placement_ref merge used by runtime resolution. Each
    # scenery choice changes its responsive background files and may refine a
    # landmark contour; the shared planter mapping remains global and is never
    # a per-bed preference.
    manager = object.__new__(AssetManager)
    manager._catalog_by_asset_id = {  # type: ignore[attr-defined]
        ("backgrounds", asset_id): row for asset_id, row in backgrounds.items()
    }
    for row in scenery:
        assert row["placement_ref"] == canonical_id
        placement = manager._placement_for_entry(row, "backgrounds")
        family = placement["surface_profile"]["planter_family"]
        assert family["family_id"] == "storybook_stone_planter_v1"
        assert family["background_contract"] == "bedless_v1"
        assert list(family["variants"]) == ["back", "middle", "front"]


def test_every_scenery_and_aspect_uses_an_approved_bedless_master() -> None:
    report = json.loads(BEDLESS_REPORT.read_text(encoding="utf-8"))
    assert report["contract"] == "bedless_v1"
    assert report["scene_count"] == 9
    assert report["variant_count"] == 3
    assert report["asset_count"] == 27
    expected_dimensions = {
        "4x3": (1280, 960),
        "16x9": (1672, 941),
        "home": (1942, 809),
    }
    records = {
        (row["scene"], row["variant"]): row
        for row in report["assets"]
    }
    assert len(records) == 27
    for (scene, variant), row in records.items():
        assert scene in {
            "verdant_twilight", "spring", "summer", "autumn", "snowy",
            "rainbow_horizon", "halloween", "full_moon", "eclipse",
        }
        source = ROOT / row["source"]
        runtime = ROOT / row["runtime"]
        assert source.is_file()
        assert runtime.is_file()
        assert tuple(row["dimensions"]) == expected_dimensions[variant]
        assert Image.open(source).size == expected_dimensions[variant]
        assert Image.open(runtime).size == expected_dimensions[variant]
        assert _sha256(source) == row["source_sha256"]
        assert _sha256(runtime) == row["runtime_sha256"]

    rows = json.loads(
        (ADDON / "assets" / "manifest.json").read_text(encoding="utf-8")
    )["assets"]
    backgrounds = {
        str(row.get("asset_id", "")): row
        for row in rows
        if row.get("category") == "backgrounds"
    }
    manager = object.__new__(AssetManager)
    manager._catalog_by_asset_id = {  # type: ignore[attr-defined]
        ("backgrounds", asset_id): row for asset_id, row in backgrounds.items()
    }
    scenery = [
        backgrounds["bg_verdant_twilight_any_soil_master_v6"],
        *[
            row
            for row in backgrounds.values()
            if "scenery_reskin" in row.get("variants", [])
        ],
    ]
    resolved_files = set()
    for row in scenery:
        placement = manager._placement_for_entry(row, "backgrounds")
        profile = placement["surface_profile"]
        assert profile["planter_family"]["background_contract"] == "bedless_v1"
        resolved_files.update(
            "ankigarden/" + variant["file"]
            for variant in profile["variants"].values()
        )
    assert resolved_files == {row["runtime"] for row in report["assets"]}


def test_bedless_planter_scene_never_draws_legacy_surface_occlusion() -> None:
    source = (ROOT / "ankigarden" / "ui" / "scene.py").read_text(encoding="utf-8")
    assert 'family.get("background_contract") != "bedless_v1"' in source
    assert 'planter_family.get("background_contract") == "bedless_v1"' in source
    assert "if not replaces_surface_occlusion and not split_occlusion:" in source


def test_partial_planter_loss_keeps_the_family_and_routes_to_graphical_fallback(
    tmp_path: Path,
) -> None:
    family = {
        "family_id": "storybook_stone_planter_v1",
        "background_contract": "bedless_v1",
        "replace_surface_occlusion": True,
        "canvas": [1024, 512],
        "soil_anchor": [0.5, 0.4296875],
        "variants": {
            band: {
                "file": f"planters/{band}.webp",
                "foreground_file": f"planters/{band}-foreground.webp",
            }
            for band in ("back", "middle", "front")
        },
    }
    for variant in family["variants"].values():
        for relative in variant.values():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"placeholder")
    (tmp_path / family["variants"]["middle"]["foreground_file"]).unlink()
    fake_scene = SimpleNamespace(
        scene={
            "asset_paths": {
                "background": {
                    "asset_root": str(tmp_path),
                    "placement": {
                        "surface_profile": {"planter_family": family}
                    },
                }
            }
        }
    )

    source = (ROOT / "ankigarden" / "ui" / "scene.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(source)
    scene_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenSceneWidget"
    )
    record_method = next(
        node
        for node in scene_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_planter_family_record"
    )
    probe = copy.deepcopy(record_method)
    probe.name = "_probe_planter_family_record"
    namespace = {"Path": Path, "Any": object}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[probe], type_ignores=[])),
            "<planter-family-record>",
            "exec",
        ),
        namespace,
    )
    resolved = namespace["_probe_planter_family_record"](fake_scene)

    assert resolved["background_contract"] == "bedless_v1"
    assert resolved["degraded"] is True
    assert resolved["variants"]["middle"]["foreground_file"] == ""
    assert resolved["variants"]["middle"]["file"].endswith("middle.webp")

    draw_band = source.split("def _draw_planter_family_band", 1)[1].split(
        "def _has_split_surface_occlusion", 1
    )[0]
    assert "if not layer_drawn:" in draw_band
    assert "self._draw_planter_fallback(" in draw_band


def test_planter_assets_share_canvas_and_foreground_masks_are_non_destructive() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    family = profile["planter_family"]
    visible_heights: list[int] = []
    for variant_name in ("back", "middle", "front"):
        variant = family["variants"][variant_name]
        base = Image.open(ADDON / variant["file"]).convert("RGBA")
        foreground = Image.open(ADDON / variant["foreground_file"]).convert("RGBA")
        assert base.size == foreground.size == (1024, 512)
        assert all(
            base.getchannel("A").getpixel(point) == 0
            for point in ((0, 0), (1023, 0), (0, 511), (1023, 511))
        )
        bounds = base.getchannel("A").getbbox()
        assert bounds is not None
        exclusion = variant["accessory_exclusions"]
        assert len(exclusion) == 1
        assert exclusion[0]["kind"] == "planter-and-soil"
        expected_bounds = [
            bounds[0] / base.width,
            bounds[1] / base.height,
            (bounds[2] - bounds[0]) / base.width,
            (bounds[3] - bounds[1]) / base.height,
        ]
        assert exclusion[0]["bounds"] == expected_bounds
        visible_heights.append(bounds[3] - bounds[1])
        # A foreground mask may remove pixels, but it must never invent or
        # recolor artwork that is absent from the common base sprite.
        leaked = ImageChops.subtract(foreground.getchannel("A"), base.getchannel("A"))
        assert leaked.getbbox() is None
        assert foreground.getchannel("A").getbbox() is not None
    assert visible_heights[0] < visible_heights[1] < visible_heights[2]


def test_selection_and_move_outlines_trace_the_exact_rendered_planter_asset() -> None:
    source = (ROOT / "ankigarden" / "ui" / "scene.py").read_text(
        encoding="utf-8"
    )
    outline = source.split("def _draw_planter_asset_outline", 1)[1].split(
        "def _draw_planter_fallback", 1
    )[0]
    selected = source.split("def _draw_selected_bed_ring", 1)[1].split(
        "def _draw_nurtured_marker", 1
    )[0]
    placeholders = source.split("def _draw_slot_placeholders", 1)[1].split(
        "def _draw_move_preview", 1
    )[0]
    band = source.split("def _draw_planter_family_band", 1)[1].split(
        "def _has_split_surface_occlusion", 1
    )[0]

    assert "self._planter_layer_record(" in outline
    assert "foreground=False" in outline
    assert "self._highlight_pixmap_for(" in outline
    assert "painter.drawPixmap(edge_target" in outline
    assert "_draw_planter_asset_outline" in selected
    assert "_draw_planter_asset_outline" in placeholders
    assert "if not outline_drawn:" in placeholders
    assert placeholders.index("if not outline_drawn:") < placeholders.index(
        "painter.drawEllipse(move_footprint)"
    )
    assert "self._planter_layer_record(" in band

    regression_source = (
        ROOT / "scripts" / "render_planter_geometry_regression.py"
    ).read_text(encoding="utf-8")
    assert "def _trace_planter_outline(" in regression_source
    assert "ImageFilter.MaxFilter" in regression_source
    assert "_trace_planter_outline(" in regression_source.split(
        "def render", 1
    )[1]
