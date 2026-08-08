from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "verdant_dusk_surface_v1.json"
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
GUIDES = ROOT / "build" / "dusk-surface-pilot" / "guides"
TARGET_ASSET_ID = "bg_verdant_dusk_summer_storybook_v3"


def _point(value: float, extent: int) -> int:
    return int(round(float(value) * extent))


def _irregular_band(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    surface: dict[str, Any],
) -> None:
    x, y = (float(item) for item in surface["anchor"])
    plane_x, _plane_y, plane_w, _plane_h = (float(item) for item in surface["contact_plane"])
    rear = surface["row"] == "rear"
    band_w = plane_w * (0.80 if rear else 0.52)
    left = _point(max(plane_x, x - band_w / 2), width)
    right = _point(min(plane_x + plane_w, x + band_w / 2), width)
    top_y = _point(y - (0.004 if rear else 0.0025), height)
    bottom_y = _point(y + (0.014 if rear else 0.008), height)
    span = max(4, right - left)
    jitter = [0, -2, 1, -1, 2, 0, -1]
    top = [
        (left + int(span * index / (len(jitter) - 1)), top_y + value)
        for index, value in enumerate(jitter)
    ]
    polygon = top + [(right, bottom_y), (left, bottom_y)]
    draw.polygon(polygon, fill=225 if rear else 118)


def build_occlusion(background_path: Path, output_path: Path, variant: dict[str, Any]) -> None:
    with Image.open(background_path) as source:
        background = source.convert("RGBA")
    mask = Image.new("L", background.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    for surface in variant["surfaces"]:
        _irregular_band(mask_draw, width=background.width, height=background.height, surface=surface)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, background.height * 0.0014)))
    pixels = ImageEnhance.Brightness(background).enhance(0.94)
    transparent = Image.new("RGBA", background.size, (0, 0, 0, 0))
    pixels = Image.composite(pixels, transparent, mask)
    pixels.putalpha(mask)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixels.save(output_path, "PNG", optimize=True)


def build_guide(background_path: Path, output_path: Path, variant: dict[str, Any]) -> None:
    with Image.open(background_path) as source:
        image = source.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    for surface in variant["surfaces"]:
        px, py, pw, ph = surface["contact_plane"]
        box = (
            _point(px, image.width),
            _point(py, image.height),
            _point(px + pw, image.width),
            _point(py + ph, image.height),
        )
        color = (87, 220, 156, 74) if surface["row"] == "front" else (238, 190, 96, 82)
        outline = (103, 255, 185, 230) if surface["row"] == "front" else (255, 209, 120, 230)
        draw.rounded_rectangle(box, radius=max(4, image.height // 150), fill=color, outline=outline, width=max(2, image.height // 450))
        ax = _point(surface["anchor"][0], image.width)
        ay = _point(surface["anchor"][1], image.height)
        radius = max(6, image.height // 100)
        draw.line((ax - radius, ay, ax + radius, ay), fill=(255, 244, 210, 255), width=max(2, image.height // 400))
        draw.line((ax, ay - radius, ax, ay + radius), fill=(255, 244, 210, 255), width=max(2, image.height // 400))
        draw.text((ax + radius + 3, ay - radius), surface["surface_id"], fill=(255, 255, 245, 255), font=font, stroke_width=2, stroke_fill=(8, 20, 19, 230))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "JPEG", quality=90, optimize=True)


def _anchor(surface: dict[str, Any]) -> dict[str, Any]:
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
        "shadow_depth": surface["row"],
        "shadow_opacity": surface["shadow_opacity"],
        "occlusion_id": surface["occlusion_id"],
    }


def _composition_anchor(surface: dict[str, Any], *, count: int) -> dict[str, Any]:
    """Keep small gardens centered while six plants use the reviewed stagger."""
    anchor = _anchor(surface)
    surface_id = str(surface["surface_id"])
    requested_x: float | None = None
    if count == 1 and surface_id == "front_center":
        requested_x = 0.50
    elif count in {2, 3} and surface_id == "front_left":
        requested_x = 0.335
    elif count in {2, 3} and surface_id == "front_right":
        requested_x = 0.665
    elif count == 3 and surface_id == "rear_center":
        requested_x = 0.50
    elif count == 4 and surface_id == "front_right":
        requested_x = 0.59
    if requested_x is not None:
        delta = requested_x - float(anchor["x"])
        anchor["x"] = requested_x
        anchor["label_anchor"] = [
            round(float(anchor["label_anchor"][0]) + delta, 6),
            anchor["label_anchor"][1],
        ]
        anchor["contact_plane"] = [
            round(float(anchor["contact_plane"][0]) + delta, 6),
            anchor["contact_plane"][1],
            anchor["contact_plane"][2],
            anchor["contact_plane"][3],
        ]
    return anchor


def _compositions(profile: dict[str, Any], count_slots: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    surfaces = {surface["surface_id"]: surface for surface in profile["surfaces"]}
    fallback = [surface["surface_id"] for surface in profile["surfaces"]]
    compositions: dict[str, list[dict[str, Any]]] = {}
    for count in range(1, 7):
        ordered = list(count_slots[str(count)])
        unused = [surface_id for surface_id in fallback if surface_id not in ordered]
        compositions[str(count)] = [
            _composition_anchor(surfaces[surface_id], count=count)
            for surface_id in (ordered + unused)
        ]
    return compositions


def install_profile(payload: dict[str, Any]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = manifest.get("assets", [])
    target = next((row for row in rows if row.get("asset_id") == TARGET_ASSET_ID), None)
    if target is None:
        raise RuntimeError(f"Missing manifest asset {TARGET_ASSET_ID}")
    placement = target.setdefault("placement", {})
    runtime_profile = {
        "profile_id": payload["profile_id"],
        "geometry_version": payload["geometry_version"],
        "theme": payload["theme"],
        "light_direction": payload["light_direction"],
        "variant_breakpoints": payload["variant_breakpoints"],
        "variants": payload["variants"],
    }
    placement["surface_profile"] = runtime_profile
    layouts: dict[str, Any] = {}
    selection = {"4:3": "4:3", "3:2": "16:9", "16:9": "16:9", "home": "home"}
    for layout_name, variant_name in selection.items():
        variant = payload["variants"][variant_name]
        layouts[layout_name] = {
            "surface_variant": variant_name,
            "coordinate_space": "source",
            "source_aspect_ratio": variant["width"] / variant["height"],
            "focal_point": variant["focal_point"],
            "planting_zone": variant["planting_zone"],
            "compositions": _compositions(variant, payload["count_surface_slots"]),
        }
    placement["layout_profiles"] = layouts
    placement["bed_anchors"] = layouts["16:9"]["compositions"]["6"]
    placement["planting_zone"] = payload["variants"]["16:9"]["planting_zone"]
    placement["focal_point"] = payload["variants"]["16:9"]["focal_point"]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    GUIDES.mkdir(parents=True, exist_ok=True)
    for variant_name, variant in payload["variants"].items():
        background_path = ROOT / "ankigarden" / variant["file"]
        occlusion_path = ROOT / "ankigarden" / variant["occlusion_file"]
        if not background_path.exists():
            raise RuntimeError(f"Missing generated Dusk background: {background_path}")
        with Image.open(background_path) as image:
            if image.size != (variant["width"], variant["height"]):
                raise RuntimeError(f"Unexpected size for {background_path}: {image.size}")
        build_occlusion(background_path, occlusion_path, variant)
        guide_name = variant_name.replace(":", "x")
        build_guide(background_path, GUIDES / f"verdant_dusk_{guide_name}_guide.jpg", variant)
    install_profile(payload)
    print(f"Installed {payload['profile_id']} and rebuilt {len(payload['variants'])} occlusion overlays.")


if __name__ == "__main__":
    main()
