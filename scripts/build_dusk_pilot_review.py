from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from ankigarden.ui.plant_display import (
    plant_layout,
    scene_surface_variant,
    theme_integration_profile,
)


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
OUTPUT = ROOT / "build" / "dusk-surface-pilot" / "review"
BACKGROUND_ID = "bg_verdant_dusk_summer_storybook_v3"
ARRANGEMENT = (
    ("bonsai", "rare", "Cinder"),
    ("ivy", "seed", "Ivy"),
    ("fern", "seed", "Fern"),
    ("cactus", "young", "Moss"),
    ("rose", "rare", "Briar"),
    ("sunbloom", "seed", "Sunbloom"),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rows() -> tuple[list[dict[str, Any]], dict[str, Any], dict[int, Path]]:
    assets = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    background = next(row for row in assets if row.get("asset_id") == BACKGROUND_ID)
    items: list[dict[str, Any]] = []
    paths: dict[int, Path] = {}
    for slot, (species, stage, name) in enumerate(ARRANGEMENT):
        candidates = [
            row for row in assets
            if row.get("category") == "plants"
            and row.get("style_family") == "storybook_gouache"
            and (row.get("slot") or {}).get("species") == species
            and (row.get("slot") or {}).get("stage") == stage
        ]
        asset = max(
            candidates,
            key=lambda row: (
                "continuity_v4" in row.get("variants", []),
                "continuity_v3" in row.get("variants", []),
                float(row.get("quality_score", 0.0)),
            ),
        )
        paths[slot] = ADDON / asset["file"]
        items.append(
            {
                "asset_id": asset["asset_id"],
                "plant_id": f"pilot-{slot}",
                "slot_index": slot,
                "name": name,
                "species": species,
                "stage": stage,
                "is_focus": slot == 4,
                "placement": asset["placement"],
                "canvas_aspect": float(asset["width"]) / max(1.0, float(asset["height"])),
            }
        )
    return items, background["placement"], paths


def _rect_payload(rect: Any) -> dict[str, float]:
    return {
        "x": round(float(rect.x), 3),
        "y": round(float(rect.y), 3),
        "width": round(float(rect.width), 3),
        "height": round(float(rect.height), 3),
    }


def build_diagnostics() -> Path:
    items, placement, _paths = _rows()
    surfaces: dict[str, Any] = {}
    for label, width, height, context in (
        ("4:3", 2048, 1536, "dashboard"),
        ("16:9", 2560, 1440, "dashboard"),
        ("home", 2880, 1200, "home"),
        ("exact_app_scene", 1922, 800, "dashboard"),
    ):
        layouts = plant_layout(
            width,
            height,
            items,
            placement,
            surface_context=context,
            composition_count=6,
        )
        by_slot = {int(item["slot_index"]): item for item in items}
        records: list[dict[str, Any]] = []
        for layout in layouts:
            item = by_slot[layout.slot_index]
            geometry = item["placement"]
            records.append(
                {
                    "slot_index": layout.slot_index,
                    "surface_id": layout.surface_id,
                    "asset_id": item["asset_id"],
                    "species": item["species"],
                    "stage": item["stage"],
                    "vessel_class": geometry.get("vessel_class", "legacy"),
                    "calibrated_geometry": {
                        key: geometry.get(key)
                        for key in (
                            "base_bounds",
                            "support_bounds",
                            "soil_contact",
                            "foliage_bounds",
                            "interaction_bounds",
                        )
                    },
                    "ideal_physical_scale": round(layout.ideal_physical_scale, 5),
                    "depth_scale": round(layout.depth_scale, 5),
                    "vessel_class_multiplier": round(layout.vessel_class_multiplier, 5),
                    "asset_correction": round(layout.asset_correction, 5),
                    "fit_scale": round(layout.fit_scale, 5),
                    "effective_scale": round(layout.effective_scale, 5),
                    "target_error": round(layout.target_error, 6),
                    "fit_reason": layout.adjustment_reason,
                    "final_soil_contact": [round(layout.draw.x + float(geometry["soil_contact"][0]) * layout.draw.width, 3), round(layout.depth, 3)],
                    "z_order": round(layout.z_depth, 3),
                    "draw": _rect_payload(layout.draw),
                    "base": _rect_payload(layout.base_rect),
                    "support": _rect_payload(layout.support_rect),
                    "foliage": _rect_payload(layout.foliage_rect),
                    "hit": _rect_payload(layout.hit),
                    "contact_plane": _rect_payload(layout.contact_plane),
                    "warnings": list(layout.validation_warnings),
                }
            )
        collisions: list[dict[str, Any]] = []
        for first_index, first in enumerate(layouts):
            for second in layouts[first_index + 1:]:
                if first.base_rect.intersects(second.base_rect) or first.foliage_rect.intersects(second.foliage_rect):
                    collisions.append(
                        {
                            "first_slot": first.slot_index,
                            "second_slot": second.slot_index,
                            "base_overlap": round(first.base_rect.intersection_area(second.base_rect), 3),
                            "foliage_overlap": round(first.foliage_rect.intersection_area(second.foliage_rect), 3),
                        }
                    )
        surfaces[label] = {
            "width": width,
            "height": height,
            "context": context,
            "items": records,
            "collisions": collisions,
        }
    path = OUTPUT / "layout_diagnostics.json"
    path.write_text(
        json.dumps(
            {
                "profile_id": "verdant_dusk_surface_v1",
                "application_window": {"width": 1982, "height": 1279},
                "scene_rectangle": {"x": 30, "y": 130, "width": 1922, "height": 800},
                "selected_plant": {"slot_index": 4, "name": "Briar"},
                "surfaces": surfaces,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return path


def _cover(image: Image.Image, size: tuple[int, int], focal: tuple[float, float]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
        Image.Resampling.LANCZOS,
    )
    left = int(round((resized.width - width) * focal[0]))
    top = int(round((resized.height - height) * focal[1]))
    return resized.crop((left, top, left + width, top + height))


def _grade(sprite: Image.Image, depth: str) -> Image.Image:
    profile = theme_integration_profile("verdant_dusk", depth)
    rgba = sprite.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(float(profile["contrast"]))
    rgb = ImageEnhance.Color(rgb).enhance(float(profile["saturation"]))
    tint = Image.new("RGB", rgb.size, ImageColor.getrgb(str(profile["tint"])))
    rgb = Image.blend(rgb, tint, float(profile["tint_alpha"]))
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def _shadow(layer: Image.Image, layout: Any) -> None:
    width = max(5, int(round(layout.footprint.width)))
    height = max(3, int(round(layout.footprint.height)))
    left = int(round(layout.support_rect.x + layout.support_rect.width / 2 - width * 0.58))
    top = int(round(layout.depth - height * 0.38))
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow, "RGBA")
    alpha = int(round(float(layout.shadow_opacity) * 255))
    draw.ellipse((left, top, left + width, top + height), fill=(72, 45, 27, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.2, height * 0.32)))
    layer.alpha_composite(shadow)


def _selected_ring(layer: Image.Image, layout: Any) -> None:
    draw = ImageDraw.Draw(layer, "RGBA")
    box = (
        int(layout.footprint.x - 8),
        int(layout.depth - layout.footprint.height * 0.15),
        int(layout.footprint.right + 8),
        int(layout.depth + layout.footprint.height * 0.72),
    )
    draw.arc(box, 5, 176, fill=(232, 188, 105, 132), width=max(2, int(layout.footprint.height * 0.12)))


def render_scene(width: int, height: int, *, context: str = "dashboard", status: bool = True) -> Image.Image:
    items, placement, paths = _rows()
    _variant_name, variant = scene_surface_variant(placement, width, height, context)
    if not variant:
        raise RuntimeError("Verdant Dusk surface variant did not resolve")
    focal_raw = variant.get("focal_point", [0.5, 0.5])
    focal = (float(focal_raw[0]), float(focal_raw[1]))
    with Image.open(ADDON / variant["file"]) as source:
        scene = _cover(source.convert("RGB"), (width, height), focal).convert("RGBA")
    layouts = plant_layout(
        width,
        height,
        items,
        placement,
        surface_context=context,
        composition_count=6,
    )
    by_slot = {int(item["slot_index"]): item for item in items}
    for layout in layouts:
        item = by_slot[layout.slot_index]
        if item.get("is_focus"):
            _selected_ring(scene, layout)
        _shadow(scene, layout)
        with Image.open(paths[layout.slot_index]) as source:
            sprite = _grade(source, layout.shadow_depth)
        target_size = (max(1, int(round(layout.draw.width))), max(1, int(round(layout.draw.height))))
        sprite = sprite.resize(target_size, Image.Resampling.LANCZOS)
        scene.alpha_composite(sprite, (int(round(layout.draw.x)), int(round(layout.draw.y))))
    occlusion_path = ADDON / str(variant.get("occlusion_file", ""))
    if occlusion_path.is_file():
        with Image.open(occlusion_path) as source:
            occlusion = _cover(source.convert("RGBA"), (width, height), focal)
        scene.alpha_composite(occlusion)
    if status and width >= 520:
        draw = ImageDraw.Draw(scene, "RGBA")
        panel_w = min(430, width - 32)
        draw.rounded_rectangle((16, 14, 16 + panel_w, 82), radius=14, fill=(7, 25, 21, 205), outline=(147, 176, 148, 100), width=1)
        draw.text((32, 25), "Your garden", font=_font(18, bold=True), fill=(239, 247, 232, 255))
        draw.text((32, 53), "1 day streak  ·  31% daily goal  ·  67% vitality", font=_font(14), fill=(202, 221, 207, 255))
    return scene.convert("RGB")


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str, outline: str, radius: int = 14) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def build_dashboard() -> Path:
    width, height = 1982, 1279
    canvas = Image.new("RGB", (width, height), "#0a1715")
    draw = ImageDraw.Draw(canvas)
    draw.text((34, 16), "Anki Garden", font=_font(24, bold=True), fill="#edf5ea")
    draw.text((34, 46), "A living record of your study rhythm", font=_font(13), fill="#aac0b1")
    _rounded(draw, (1810, 14, 1946, 60), fill="#1d3935", outline="#42675a", radius=11)
    draw.text((1840, 28), "Settings", font=_font(15, bold=True), fill="#edf5ea")
    card = (20, 72, 1962, 1054)
    _rounded(draw, card, fill="#102622", outline="#345348", radius=16)
    _rounded(draw, (30, 82, 1952, 122), fill="#0d211e", outline="#27443a", radius=10)
    draw.text((46, 94), "Your garden", font=_font(14, bold=True), fill="#edf5ea")
    draw.text((174, 95), "1 day streak  ·  31% daily goal  ·  67% vitality", font=_font(13), fill="#aac0b1")
    scene = render_scene(1922, 800, context="dashboard", status=False)
    canvas.paste(scene, (30, 130))
    draw.line((34, 942, 1948, 942), fill="#345348", width=1)
    draw.text((46, 955), "Briar", font=_font(17, bold=True), fill="#edf5ea")
    draw.text((46, 981), "Rose · Rare stage · 65,526 growth", font=_font(13), fill="#aac0b1")
    draw.text((690, 955), "Growth stage", font=_font(13, bold=True), fill="#dce9df")
    draw.text((1350, 955), "Fully grown", font=_font(13), fill="#b9cec0")
    draw.rounded_rectangle((690, 985, 1430, 993), radius=4, fill="#58b77b")
    for index, (label, primary) in enumerate((("Nurtured plant", True), ("Rearrange", False), ("View Story", False))):
        x = 1450 + index * 160
        _rounded(draw, (x, 951, x + 145, 997), fill="#5a4824" if primary else "#1d3935", outline="#8a6b34" if primary else "#42675a", radius=11)
        draw.text((x + 14, 965), label, font=_font(14, bold=True), fill="#f5e5ba" if primary else "#edf5ea")
    draw.text((46, 1008), "Today's growth", font=_font(13, bold=True), fill="#dce9df")
    draw.text((1758, 1008), "43 of 140", font=_font(13), fill="#aac0b1")
    draw.rounded_rectangle((46, 1030, 1934, 1038), radius=4, fill="#183029")
    draw.rounded_rectangle((46, 1030, 625, 1038), radius=4, fill="#58b77b")
    _rounded(draw, (20, 1068, 1962, 1122), fill="#102622", outline="#345348", radius=14)
    draw.text((42, 1082), "All 6 garden spaces unlocked", font=_font(15, bold=True), fill="#edf5ea")
    draw.text((315, 1084), "Every planting surface is available for rearranging.", font=_font(13), fill="#aac0b1")
    _rounded(draw, (20, 1138, 1962, 1260), fill="#102622", outline="#345348", radius=14)
    draw.text((42, 1152), "Quests", font=_font(15, bold=True), fill="#edf5ea")
    draw.text((116, 1154), "0 of 3 completed", font=_font(12), fill="#aac0b1")
    for row, (title, value, progress) in enumerate((("Complete 50 reviews", "13 of 50", .26), ("Earn 140 growth", "43 of 140", .31))):
        top = 1178 + row * 38
        _rounded(draw, (36, top, 1946, top + 32), fill="#0d211e", outline="#27443a", radius=9)
        draw.text((52, top + 5), title, font=_font(12, bold=True), fill="#edf5ea")
        draw.text((1845, top + 5), value, font=_font(11), fill="#aac0b1")
        draw.rounded_rectangle((52, top + 24, 1930, top + 28), radius=2, fill="#183029")
        draw.rounded_rectangle((52, top + 24, 52 + int(1878 * progress), top + 28), radius=2, fill="#58b77b")
    path = OUTPUT / "dashboard_1982x1279.png"
    canvas.save(path, "PNG", optimize=True)
    return path


def build_home_card() -> Path:
    width, height = 1920, 520
    canvas = Image.new("RGB", (width, height), "#081310")
    draw = ImageDraw.Draw(canvas)
    card = (28, 24, 1892, 496)
    _rounded(draw, card, fill="#0d201d", outline="#76977e", radius=18)
    scene = render_scene(1120, 466, context="home", status=False)
    canvas.paste(scene, (31, 27))
    draw.rectangle((1151, 27, 1889, 493), fill="#0d231f")
    draw.line((1151, 27, 1151, 493), fill="#345348", width=1)
    draw.text((1180, 54), "NURTURED PLANT", font=_font(11, bold=True), fill="#d8b875")
    draw.text((1180, 78), "Briar", font=_font(27, bold=True), fill="#edf5ea")
    draw.text((1180, 116), "Rare · Rose", font=_font(13), fill="#b9cec0")
    _rounded(draw, (1675, 54, 1855, 102), fill="#24583f", outline="#618a6e", radius=11)
    draw.text((1710, 69), "Open Garden", font=_font(15, bold=True), fill="#edf5ea")
    metrics = (("REVIEWS TODAY", "121"), ("DAILY GROWTH", "43 of 140"), ("GARDEN VITALITY", "67%"))
    for index, (label, value) in enumerate(metrics):
        top = 158 + index * 99
        _rounded(draw, (1180, top, 1855, top + 82), fill="#0a1d19", outline="#29483c", radius=11)
        draw.text((1198, top + 13), label, font=_font(10, bold=True), fill="#8eab9a")
        draw.text((1198, top + 33), value, font=_font(18, bold=True), fill="#edf5ea")
        if index == 1:
            draw.rounded_rectangle((1198, top + 66, 1837, top + 72), radius=3, fill="#1a342c")
            draw.rounded_rectangle((1198, top + 66, 1394, top + 72), radius=3, fill="#58b77b")
    path = OUTPUT / "home_card_1920x520.png"
    canvas.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    scene_jobs = (
        ("scene_4x3_2048x1536.png", 2048, 1536, "dashboard"),
        ("scene_16x9_2560x1440.png", 2560, 1440, "dashboard"),
        ("scene_home_2880x1200.png", 2880, 1200, "home"),
    )
    outputs: list[Path] = []
    for name, width, height, context in scene_jobs:
        path = OUTPUT / name
        render_scene(width, height, context=context).save(path, "PNG", optimize=True)
        outputs.append(path)
    outputs.extend((build_dashboard(), build_home_card(), build_diagnostics()))
    for path in outputs:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
