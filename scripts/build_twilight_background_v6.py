from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = (
    ROOT
    / "artwork_source"
    / "backgrounds"
    / "bedless_v6"
    / "verdant_twilight"
)
PROFILE_PATH = ROOT / "tests" / "fixtures" / "verdant_twilight_surface_v6.json"
MANIFEST_PATH = ROOT / "ankigarden" / "assets" / "manifest.json"
ASSET_DIR = Path(
    "assets/v6_storybook_gouache/backgrounds/verdant_twilight/soil_master"
)
GUIDE_DIR = ROOT / "build" / "twilight-background-v6" / "guides"
ASSET_ID = "bg_verdant_twilight_any_soil_master_v6"

LAYER_NAMES = (
    "sky", "foliage", "ground", "architecture", "cottage_light",
    "nursery_light", "weather",
)

VARIANTS: dict[str, dict[str, Any]] = {
    "4:3": {
        "slug": "4x3",
        "source": SOURCE_DIR / "verdant_twilight_4x3.png",
        "beds": (
            ((0.266, 0.394, 0.437, 0.450), (0.284, 0.403, 0.420, 0.440)),
            ((0.566, 0.394, 0.737, 0.450), (0.584, 0.403, 0.720, 0.440)),
            ((0.143, 0.543, 0.356, 0.626), (0.164, 0.552, 0.335, 0.611)),
            ((0.443, 0.543, 0.656, 0.626), (0.464, 0.552, 0.635, 0.611)),
            ((0.329, 0.725, 0.573, 0.817), (0.351, 0.738, 0.551, 0.800)),
            ((0.629, 0.725, 0.873, 0.817), (0.651, 0.738, 0.851, 0.800)),
        ),
        "nursery": [0.077, 0.150, 0.145, 0.170],
    },
    "16:9": {
        "slug": "16x9",
        "source": SOURCE_DIR / "verdant_twilight_16x9.png",
        "beds": (
            ((0.330, 0.424, 0.456, 0.480), (0.344, 0.433, 0.442, 0.469)),
            ((0.548, 0.424, 0.674, 0.480), (0.562, 0.433, 0.660, 0.469)),
            ((0.242, 0.568, 0.398, 0.653), (0.256, 0.578, 0.384, 0.637)),
            ((0.460, 0.568, 0.616, 0.653), (0.474, 0.578, 0.602, 0.637)),
            ((0.374, 0.742, 0.554, 0.840), (0.390, 0.754, 0.538, 0.821)),
            ((0.592, 0.742, 0.772, 0.840), (0.608, 0.754, 0.756, 0.821)),
        ),
        "nursery": [0.196, 0.183, 0.105, 0.170],
    },
    "home": {
        "slug": "home",
        "source": SOURCE_DIR / "verdant_twilight_home.png",
        "beds": (
            ((0.360, 0.434, 0.463, 0.496), (0.373, 0.444, 0.450, 0.484)),
            ((0.535, 0.434, 0.638, 0.496), (0.548, 0.444, 0.625, 0.484)),
            ((0.291, 0.590, 0.417, 0.685), (0.305, 0.602, 0.403, 0.668)),
            ((0.466, 0.590, 0.592, 0.685), (0.480, 0.602, 0.578, 0.668)),
            ((0.397, 0.773, 0.543, 0.884), (0.413, 0.787, 0.527, 0.864)),
            ((0.572, 0.773, 0.718, 0.884), (0.588, 0.787, 0.702, 0.864)),
        ),
        "nursery": [0.224, 0.169, 0.080, 0.173],
    },
}

PLANTER_FAMILY: dict[str, Any] = {
    "family_id": "storybook_stone_planter_v1",
    "background_contract": "bedless_v1",
    "canvas": [1024, 512],
    "soil_anchor": [0.5, 220 / 512],
    "width_multiplier": 1.28,
    "replace_surface_occlusion": True,
    "variants": {
        row: {
            "file": (
                f"assets/v6_storybook_gouache/planters/stone_family_v1/"
                f"stone_planter_{row}.webp"
            ),
            "foreground_file": (
                f"assets/v6_storybook_gouache/planters/stone_family_v1/"
                f"stone_planter_{row}_foreground.webp"
            ),
            "width_multiplier": 1.28,
        }
        for row in ("back", "middle", "front")
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _point(value: float, extent: int) -> int:
    return int(round(float(value) * extent))


def _runtime_surface(
    slot: int,
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> dict[str, Any]:
    left, top, right, bottom = inner
    anchor = [(left + right) / 2, top + (bottom - top) * 0.52]
    depth_band = ("far", "far", "middle", "middle", "near", "near")[slot]
    row = "front" if depth_band == "near" else "rear"
    depth_scale = (0.84, 0.84, 0.92, 0.92, 1.0, 1.0)[slot]
    surface_id = (
        "far_left_soil_bed", "far_right_soil_bed",
        "middle_left_soil_bed", "middle_right_soil_bed",
        "near_left_soil_bed", "near_right_soil_bed",
    )[slot]
    width = right - left
    height = bottom - top
    return {
        "slot": slot,
        "surface_id": surface_id,
        "anchor": [round(anchor[0], 6), round(anchor[1], 6)],
        "depth_band": depth_band,
        "row": row,
        "surface_kind": "soil",
        "allowed_base_types": ["direct_soil"],
        "depth_scale": depth_scale,
        "contact_plane": [left, top, width, height],
        "support_line": [
            [round(left + width * 0.28, 6), round(anchor[1], 6)],
            [round(right - width * 0.28, 6), round(anchor[1], 6)],
        ],
        "shadow_plane": [[left, top], [right, top], [right, bottom], [left, bottom]],
        "physical_width_ratio": 0.16,
        "footprint": [right - outer[0], bottom - outer[1]],
        "label_anchor": [round(anchor[0], 6), round(bottom + 0.035, 6)],
        "shadow_opacity": (0.24, 0.24, 0.29, 0.29, 0.34, 0.34)[slot],
        "shadow_color": "#17201d",
        "light_direction": [-0.18, 0.14],
        "occlusion_id": f"{surface_id}_front_rim",
        "outer_bounds": list(outer),
        "inner_bounds": list(inner),
    }


def _bed_anchor(surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "x": surface["anchor"][0],
        "y": surface["anchor"][1],
        "depth": surface["anchor"][1],
        "plant_scale": surface["depth_scale"],
        "footprint": surface["footprint"],
        "label_anchor": surface["label_anchor"],
        "physical_width_ratio": surface["physical_width_ratio"],
        "surface_id": surface["surface_id"],
        "contact_plane": surface["contact_plane"],
        "shadow_plane": surface["shadow_plane"],
        "support_line": surface["support_line"],
        "shadow_depth": surface["row"],
        "shadow_opacity": surface["shadow_opacity"],
        "occlusion_id": surface["occlusion_id"],
        "surface_kind": "soil",
        "allowed_base_types": ["direct_soil"],
        "seating_depth": 0.0,
        "depth_band": surface["depth_band"],
        "shadow_color": surface["shadow_color"],
        "light_direction": surface["light_direction"],
    }


def _profile() -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for name, spec in VARIANTS.items():
        source = Image.open(spec["source"])
        width, height = source.size
        slug = spec["slug"]
        base = ASSET_DIR / f"verdant_twilight_{slug}"
        surfaces = [
            _runtime_surface(slot, outer, inner)
            for slot, (outer, inner) in enumerate(spec["beds"])
        ]
        variants[name] = {
            "file": str(base.with_suffix(".webp")),
            "occlusion_file": str(base.parent / f"verdant_twilight_{slug}_occlusion.webp"),
            "occlusion_layers": {
                row: str(base.parent / f"verdant_twilight_{slug}_{row}_occlusion.webp")
                for row in ("rear", "front")
            },
            "surface_masks": {
                surface["surface_id"]: str(
                    base.parent / "masks" / f"verdant_twilight_{slug}_{surface['surface_id']}.png"
                )
                for surface in surfaces
            },
            "layer_masks": {
                layer: str(
                    base.parent / "masks" / "layers" / f"verdant_twilight_{slug}_{layer}.png"
                )
                for layer in LAYER_NAMES
            },
            "width": width,
            "height": height,
            "focal_point": [0.5, 0.5],
            "planting_zone": {"left": 0.12, "right": 0.88, "far_y": 0.36, "near_y": 0.89},
            "plant_card_safe_areas": [],
            "surfaces": surfaces,
        }
    profile = {
        "profile_id": "verdant_twilight_surface_v6",
        "geometry_version": 6,
        "theme": "verdant_twilight",
        "light_direction": [-0.18, 0.14],
        "key_light_origins": {"4:3": [0.50, 0.24], "16:9": [0.50, 0.24], "home": [0.50, 0.24]},
        "appearance": {
            "ambient_tint": "#7888aa", "key_tint": "#e6a46f",
            "rear_contrast": 0.97, "front_contrast": 0.99,
            "rear_saturation": 0.94, "front_saturation": 0.97,
            "rear_exposure": -0.025, "front_exposure": -0.008,
            "base_tint_alpha": 0.010, "distance_tint_alpha": 0.028,
            "base_key_strength": 0.014, "distance_key_strength": 0.035,
            "rear_base_ao": 0.050, "front_base_ao": 0.040,
            "contact_shadow_color": "#17201d", "cast_shadow_color": "#1d2822",
        },
        "variant_contract": {
            "environment_id": "verdant_twilight_v6", "season": "any",
            "art_time": "twilight", "supported_times": ["twilight"],
            "weather": "any", "weather_mode": "separate_overlay",
            "coordinate_contract": "aspect_locked_normalized_v3",
            "spatial_blueprint": "verdant_twilight_v6_six_soil_beds",
            "surface_geometry_reused_for_future_variants": False,
        },
        "layer_contract": {
            "required_masks": list(LAYER_NAMES),
            "invariant_geometry": ["planting_surfaces", "landmarks"],
            "variant_layers": ["sky", "foliage", "ground", "architecture", "weather"],
            "plant_contact_shadows_baked": False,
        },
        "planter_family": PLANTER_FAMILY,
        "landmarks": [{
            "landmark_id": "nursery_entrance", "action_id": "garden.nursery.open",
            "label": "Nursery", "tooltip": "Nursery — coming soon", "role": "button",
            "supported_variants": ["4:3", "16:9", "home"],
            "variants": {
                name: {
                    "bounds": list(spec["nursery"]),
                    "polygon": [
                        [spec["nursery"][0], spec["nursery"][1]],
                        [spec["nursery"][0] + spec["nursery"][2], spec["nursery"][1]],
                        [spec["nursery"][0] + spec["nursery"][2], spec["nursery"][1] + spec["nursery"][3]],
                        [spec["nursery"][0], spec["nursery"][1] + spec["nursery"][3]],
                    ],
                }
                for name, spec in VARIANTS.items()
            },
        }],
        "variant_breakpoints": {"four_three_max": 1.42, "ultrawide_min": 2.05},
        "variants": variants,
    }
    # Landmark polygons and preview crops are accepted product contracts that
    # may be refined independently of this raster builder. Preserve them when
    # rebuilding the same geometry profile instead of reverting those edits.
    if PROFILE_PATH.is_file():
        try:
            existing = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing_landmarks = existing.get("landmarks") if isinstance(existing, dict) else None
        if isinstance(existing_landmarks, list) and existing_landmarks:
            profile["landmarks"] = existing_landmarks
        existing_variants = existing.get("variants", {}) if isinstance(existing, dict) else {}
        if isinstance(existing_variants, dict):
            for variant_name, variant in variants.items():
                existing_variant = existing_variants.get(variant_name)
                if isinstance(existing_variant, dict) and isinstance(existing_variant.get("preview_crop"), dict):
                    variant["preview_crop"] = dict(existing_variant["preview_crop"])
    return profile


def _build_surface_mask(path: Path, surface: dict[str, Any], size: tuple[int, int]) -> None:
    width, height = size
    x, y, w, h = surface["contact_plane"]
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (_point(x, width), _point(y, height), _point(x + w, width), _point(y + h, height)),
        radius=max(3, _point(h * 0.40, height)), fill=255,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(path, "PNG", optimize=True)


def _build_layer_mask(path: Path, layer: str, size: tuple[int, int]) -> None:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if layer == "sky":
        draw.rectangle((0, 0, width, _point(0.31, height)), fill=255)
    elif layer == "ground":
        draw.rectangle((0, _point(0.27, height), width, height), fill=255)
    elif layer == "foliage":
        draw.rectangle((0, _point(0.05, height), width, _point(0.38, height)), fill=255)
        draw.rectangle((0, _point(0.78, height), width, height), fill=190)
    elif layer == "architecture":
        draw.rectangle((0, _point(0.08, height), _point(0.34, width), _point(0.38, height)), fill=255)
        draw.rectangle((_point(0.66, width), _point(0.06, height), width, _point(0.39, height)), fill=255)
    elif layer == "cottage_light":
        draw.ellipse((_point(.66, width), _point(.08, height), _point(.94, width), _point(.40, height)), fill=255)
    elif layer == "nursery_light":
        draw.ellipse((_point(.06, width), _point(.08, height), _point(.34, width), _point(.42, height)), fill=255)
    elif layer == "weather":
        draw.rectangle((0, 0, width, height), fill=255)
    path.parent.mkdir(parents=True, exist_ok=True)
    mask.filter(ImageFilter.GaussianBlur(max(1.0, height * 0.004))).save(path, "PNG", optimize=True)


def _build_occlusion(
    background: Image.Image,
    path: Path,
    surfaces: list[dict[str, Any]],
) -> None:
    width, height = background.size
    mask = Image.new("L", background.size, 0)
    draw = ImageDraw.Draw(mask)
    for surface in surfaces:
        outer = surface["outer_bounds"]
        inner = surface["inner_bounds"]
        outer_box = tuple(_point(value, width if index % 2 == 0 else height) for index, value in enumerate(outer))
        inner_box = tuple(_point(value, width if index % 2 == 0 else height) for index, value in enumerate(inner))
        outer_height = max(1, outer_box[3] - outer_box[1])
        inner_height = max(1, inner_box[3] - inner_box[1])
        draw.rounded_rectangle(outer_box, radius=max(3, outer_height // 2), fill=255)
        draw.rounded_rectangle(inner_box, radius=max(3, inner_height // 2), fill=0)
        draw.rectangle((outer_box[0], outer_box[1], outer_box[2], _point(surface["anchor"][1], height)), fill=0)
    pixels = background.convert("RGBA")
    pixels.putalpha(mask.filter(ImageFilter.GaussianBlur(max(0.55, height * 0.00045))))
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels.save(
        path,
        "WEBP",
        lossless=True,
        quality=100,
        method=6,
        exact=False,
    )


def _build_guide(background: Image.Image, path: Path, variant: dict[str, Any]) -> None:
    image = background.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    for surface in variant["surfaces"]:
        x, y, w, h = surface["contact_plane"]
        draw.rounded_rectangle(
            (_point(x, image.width), _point(y, image.height), _point(x + w, image.width), _point(y + h, image.height)),
            radius=max(3, _point(h * .4, image.height)),
            fill=(80, 210, 235, 48), outline=(105, 235, 255, 230), width=2,
        )
        ax, ay = _point(surface["anchor"][0], image.width), _point(surface["anchor"][1], image.height)
        draw.line((ax - 9, ay, ax + 9, ay), fill=(255, 80, 95, 255), width=3)
        draw.line((ax, ay - 9, ax, ay + 9), fill=(255, 80, 95, 255), width=3)
        draw.text((ax + 12, ay - 14), f"S{surface['slot']} {surface['surface_id']}", font=font, fill=(255, 255, 245, 255), stroke_width=2, stroke_fill=(8, 18, 18, 230))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, "JPEG", quality=92, optimize=True)


def _placement(profile: dict[str, Any]) -> dict[str, Any]:
    layouts: dict[str, Any] = {}
    for layout_name, variant_name in {"4:3": "4:3", "3:2": "4:3", "16:9": "16:9", "home": "home"}.items():
        variant = profile["variants"][variant_name]
        anchors = [_bed_anchor(surface) for surface in variant["surfaces"]]
        layouts[layout_name] = {
            "surface_variant": variant_name,
            "coordinate_space": "source",
            "source_aspect_ratio": variant["width"] / variant["height"],
            "focal_point": variant["focal_point"],
            "planting_zone": variant["planting_zone"],
            "compositions": {str(count): [dict(anchor) for anchor in anchors] for count in range(1, 7)},
        }
    return {
        "anchor_x": 0.5, "baseline_y": 0.5, "scale": 1.0,
        "crop": "contain", "layer": "background",
        "focal_point": profile["variants"]["16:9"]["focal_point"],
        "planting_zone": profile["variants"]["16:9"]["planting_zone"],
        "bed_anchors": layouts["16:9"]["compositions"]["6"],
        "layout_profiles": layouts,
        "surface_profile": profile,
    }


def _install_manifest(profile: dict[str, Any]) -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = payload.setdefault("assets", [])
    for row in rows:
        if row.get("category") == "backgrounds":
            row["release_preferred"] = row.get("asset_id") == ASSET_ID
    entry = {
        "asset_id": ASSET_ID,
        "category": "backgrounds",
        "slot": {"season": "any", "weather": "any", "time_of_day": "any", "theme": "verdant_twilight"},
        "variants": ["storybook_gouache", "surface_v6", "direct_soil", "aspect_locked", "weather_overlay_ready"],
        "file": profile["variants"]["4:3"]["file"],
        "width": profile["variants"]["4:3"]["width"],
        "height": profile["variants"]["4:3"]["height"],
        "format": "webp", "alpha": False, "style_family": "storybook_gouache",
        "release_preferred": True, "quality_tier": "ultra", "quality_score": 0.995,
        "source": "User-supplied Verdant Twilight six-bed background with ImageGen-matched responsive outpaints",
        "attribution": "Original artwork supplied for Anki Garden and bundled with the add-on",
        "source_master_sha256": {
            name: _sha256(spec["source"]) for name, spec in VARIANTS.items()
        },
        "placement": _placement(profile),
    }
    existing = next((index for index, row in enumerate(rows) if row.get("asset_id") == ASSET_ID), None)
    if existing is None:
        rows.append(entry)
    else:
        rows[existing] = entry
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for spec in VARIANTS.values():
        if not spec["source"].is_file():
            raise RuntimeError(f"Missing approved V6 source: {spec['source']}")
    profile = _profile()
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    for name, variant in profile["variants"].items():
        spec = VARIANTS[name]
        source = Image.open(spec["source"]).convert("RGB")
        output = ROOT / "ankigarden" / variant["file"]
        output.parent.mkdir(parents=True, exist_ok=True)
        source.save(output, "WEBP", quality=95, method=6)
        for surface in variant["surfaces"]:
            _build_surface_mask(
                ROOT / "ankigarden" / variant["surface_masks"][surface["surface_id"]],
                surface,
                source.size,
            )
        for layer, relative in variant["layer_masks"].items():
            _build_layer_mask(ROOT / "ankigarden" / relative, layer, source.size)
        for row, relative in variant["occlusion_layers"].items():
            _build_occlusion(
                source,
                ROOT / "ankigarden" / relative,
                [surface for surface in variant["surfaces"] if surface["row"] == row],
            )
        _build_occlusion(source, ROOT / "ankigarden" / variant["occlusion_file"], variant["surfaces"])
        _build_guide(
            source,
            GUIDE_DIR / f"verdant_twilight_v6_{spec['slug']}_guide.jpg",
            variant,
        )
    _install_manifest(profile)
    print(f"Built and installed {profile['profile_id']} ({ASSET_ID}).")


if __name__ == "__main__":
    main()
