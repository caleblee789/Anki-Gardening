from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.ui.plant_display import partition_scene_rows, plant_layout, scene_profile_name, scene_surface_variant


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
OUTPUT = ROOT / "build" / "release-placement-review"
THEMES = ("verdant_twilight",)
SPECIES = ("bonsai", "rose")
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
MIXED_GARDENS = (
    (
        "Mixed species and stages",
        ("bonsai", "rose", "bonsai", "rose", "bonsai", "rose"),
        ("rare", "young", "flowering", "mature", "sprout", "flowering"),
    ),
    (
        "Large beside small",
        ("rose", "bonsai", "bonsai", "rose", "rose", "bonsai"),
        ("rare", "seed", "rare", "seed", "sprout", "young"),
    ),
    (
        "Wide canopies",
        ("bonsai", "rose", "bonsai", "rose", "bonsai", "rose"),
        ("flowering", "rare", "flowering", "flowering", "rare", "rare"),
    ),
    (
        "Direct-soil scale",
        ("rose", "bonsai", "rose", "bonsai", "rose", "bonsai"),
        ("mature", "mature", "mature", "mature", "mature", "mature"),
    ),
    (
        "Early progression",
        ("bonsai", "rose", "rose", "bonsai", "rose", "bonsai"),
        ("sprout", "young", "sprout", "young", "young", "sprout"),
    ),
    (
        "Rare collection",
        ("bonsai", "rose", "bonsai", "rose", "bonsai", "rose"),
        ("rare", "rare", "rare", "rare", "rare", "rare"),
    ),
    (
        "Depth stress",
        ("rose", "bonsai", "rose", "bonsai", "rose", "bonsai"),
        ("rare", "flowering", "rare", "seed", "sprout", "young"),
    ),
    (
        "All growth bands",
        ("bonsai", "rose", "bonsai", "rose", "bonsai", "rose"),
        ("seed", "sprout", "young", "mature", "flowering", "rare"),
    ),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cover(image: Image.Image, size: tuple[int, int], focal: tuple[float, float]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = round((resized.width - width) * focal[0])
    top = round((resized.height - height) * focal[1])
    return resized.crop((left, top, left + width, top + height))


def _grade(sprite: Image.Image, layout: Any) -> Image.Image:
    profile = layout.grounding.lighting
    rgba = sprite.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = ImageEnhance.Contrast(rgba.convert("RGB")).enhance(float(profile.contrast))
    rgb = ImageEnhance.Color(rgb).enhance(float(profile.saturation))
    rgb = ImageEnhance.Brightness(rgb).enhance(1.0 + float(profile.exposure))
    tint = Image.new("RGB", rgb.size, ImageColor.getrgb(str(profile.tint)))
    rgb = Image.blend(rgb, tint, float(profile.tint_alpha))
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def _background(rows: list[dict[str, Any]], theme: str) -> dict[str, Any]:
    candidates = [
        row for row in rows
        if row.get("category") == "backgrounds"
        and (row.get("slot") or {}).get("theme") == theme
        and row.get("style_family") == "storybook_gouache"
    ]
    return max(
        candidates,
        key=lambda row: (
            bool(row.get("release_preferred", False)),
            float(row.get("quality_score", 0)),
            str(row.get("asset_id", "")),
        ),
    )


def _plant(rows: list[dict[str, Any]], species: str, stage: str) -> dict[str, Any]:
    candidates = [
        row for row in rows
        if row.get("category") == "plants"
        and row.get("style_family") == "storybook_gouache"
        and (row.get("slot") or {}).get("species") == species
        and (row.get("slot") or {}).get("stage") == stage
    ]
    return max(
        candidates,
        key=lambda row: (
            bool(row.get("release_preferred", False)),
            "continuity_v4" in row.get("variants", []),
            "continuity_v3" in row.get("variants", []),
            float(row.get("quality_score", 0)),
        ),
    )


def _background_layer(
    background: dict[str, Any], width: int, height: int, context: str
) -> tuple[Image.Image, dict[str, Path], tuple[float, float]]:
    placement = background.get("placement", {})
    _variant_name, variant = scene_surface_variant(placement, width, height, context)
    path = ADDON / str(variant.get("file") or background["file"])
    profile_name = scene_profile_name(width, height, context)
    profiles = placement.get("layout_profiles", {}) if isinstance(placement, dict) else {}
    profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
    focal_raw = variant.get("focal_point", profile.get("focal_point", placement.get("focal_point", [0.5, 0.5])))
    focal = (
        float(focal_raw[0]), float(focal_raw[1])
    ) if isinstance(focal_raw, (list, tuple)) and len(focal_raw) == 2 else (0.5, 0.5)
    with Image.open(path) as source:
        canvas = _cover(source.convert("RGB"), (width, height), focal).convert("RGBA")
    occlusions: dict[str, Path] = {}
    raw_layers = variant.get("occlusion_layers", {})
    if isinstance(raw_layers, dict):
        for row in ("rear", "front"):
            value = raw_layers.get(row)
            candidate = ADDON / str(value) if value else None
            if candidate is not None and candidate.is_file():
                occlusions[row] = candidate
    if not occlusions:
        value = variant.get("occlusion_file")
        candidate = ADDON / str(value) if value else None
        if candidate is not None and candidate.is_file():
            occlusions["legacy"] = candidate
    return canvas, occlusions, focal


def _contact_shadow(canvas: Image.Image, layout: Any) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    cast = layout.grounding.cast_shadow
    draw.ellipse(
        (round(cast.x), round(cast.y), round(cast.right), round(cast.bottom)),
        fill=(67, 43, 27, round(float(layout.grounding.cast_opacity) * 255)),
    )
    contact = layout.grounding.contact_shadow
    draw.ellipse(
        (round(contact.x), round(contact.y), round(contact.right), round(contact.bottom)),
        fill=(72, 47, 30, round(float(layout.grounding.contact_opacity) * 255)),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(max(0.8, contact.height * .22)))
    if layout.grounding.shadow_plane:
        clip = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(clip).polygon(
            [(round(x), round(y)) for x, y in layout.grounding.shadow_plane], fill=255
        )
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), clip))
    canvas.alpha_composite(layer)


def render_scene(
    rows: list[dict[str, Any]], theme: str, width: int, height: int,
    species: list[str], stages: list[str], *, context: str = "dashboard",
) -> Image.Image:
    background = _background(rows, theme)
    canvas, occlusions, focal = _background_layer(background, width, height, context)
    items: list[dict[str, Any]] = []
    paths: dict[int, Path] = {}
    for slot in range(6):
        asset = _plant(rows, species[slot % len(species)], stages[slot % len(stages)])
        paths[slot] = ADDON / str(asset["file"])
        items.append(
            {
                "plant_id": f"review-{slot}",
                "slot_index": slot,
                "species": (asset.get("slot") or {}).get("species"),
                "stage": (asset.get("slot") or {}).get("stage"),
                "placement": asset.get("placement", {}),
                "canvas_aspect": float(asset["width"]) / max(1.0, float(asset["height"])),
            }
        )
    layouts = plant_layout(
        width,
        height,
        items,
        background.get("placement", {}),
        surface_context=context,
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )
    layout_rows = partition_scene_rows([({"slot_index": layout.slot_index}, layout) for layout in layouts])
    if "legacy" in occlusions:
        with Image.open(occlusions["legacy"]) as source:
            canvas.alpha_composite(_cover(source.convert("RGBA"), (width, height), focal))
    for row_name in ("rear", "front"):
        for _item, layout in layout_rows[row_name]:
            _contact_shadow(canvas, layout)
        for _item, layout in layout_rows[row_name]:
            with Image.open(paths[layout.slot_index]) as source:
                sprite = _grade(source, layout)
            sprite = sprite.resize(
                (max(1, round(layout.draw.width)), max(1, round(layout.draw.height))),
                Image.Resampling.LANCZOS,
            )
            canvas.alpha_composite(sprite, (round(layout.draw.x), round(layout.draw.y)))
        if row_name in occlusions:
            with Image.open(occlusions[row_name]) as source:
                canvas.alpha_composite(_cover(source.convert("RGBA"), (width, height), focal))
    return canvas.convert("RGB")


def _labeled_tile(image: Image.Image, label: str, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", (size[0], size[1] + 34), "#101b18")
    tile.paste(image.resize(size, Image.Resampling.LANCZOS), (0, 0))
    draw = ImageDraw.Draw(tile)
    draw.text((10, size[1] + 8), label, font=_font(14, bold=True), fill="#edf5ea")
    return tile


def build_species_stage_sheets(rows: list[dict[str, Any]]) -> list[Path]:
    outputs: list[Path] = []
    tile_size = (480, 270)
    for theme in THEMES:
        sheet = Image.new("RGB", (tile_size[0] * len(STAGES), (tile_size[1] + 34) * len(SPECIES)), "#081310")
        for row_index, species in enumerate(SPECIES):
            for column, stage in enumerate(STAGES):
                scene = render_scene(rows, theme, 960, 540, [species], [stage])
                tile = _labeled_tile(scene, f"{species.title()} · {stage.title()}", tile_size)
                sheet.paste(tile, (column * tile_size[0], row_index * (tile_size[1] + 34)))
        path = OUTPUT / f"{theme}_all_species_stages.png"
        sheet.save(path, "PNG", optimize=True)
        outputs.append(path)
    return outputs


def build_responsive_sheet(rows: list[dict[str, Any]]) -> Path:
    jobs = (("4:3", 960, 720, "dashboard"), ("16:9", 960, 540, "dashboard"), ("home", 960, 400, "home"))
    tile_size = (640, 420)
    sheet = Image.new("RGB", (tile_size[0] * len(jobs), (tile_size[1] + 34) * len(THEMES)), "#081310")
    mixed_species = list(SPECIES[:6])
    mixed_stages = list(STAGES)
    for row_index, theme in enumerate(THEMES):
        for column, (label, width, height, context) in enumerate(jobs):
            scene = render_scene(rows, theme, width, height, mixed_species, mixed_stages, context=context)
            tile = _labeled_tile(scene, f"{theme.replace('_', ' ').title()} · {label}", tile_size)
            sheet.paste(tile, (column * tile_size[0], row_index * (tile_size[1] + 34)))
    path = OUTPUT / "responsive_verdant_twilight.png"
    sheet.save(path, "PNG", optimize=True)
    return path


def build_mixed_garden_sheet(rows: list[dict[str, Any]]) -> Path:
    tile_size = (480, 270)
    columns = 4
    rows_count = (len(MIXED_GARDENS) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (tile_size[0] * columns, (tile_size[1] + 34) * rows_count),
        "#081310",
    )
    for index, (label, species, stages) in enumerate(MIXED_GARDENS):
        scene = render_scene(
            rows,
            "verdant_twilight",
            960,
            540,
            list(species),
            list(stages),
        )
        tile = _labeled_tile(scene, label, tile_size)
        sheet.paste(
            tile,
            ((index % columns) * tile_size[0], (index // columns) * (tile_size[1] + 34)),
        )
    path = OUTPUT / "verdant_twilight_mixed_gardens.png"
    sheet.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    outputs = build_species_stage_sheets(rows)
    outputs.append(build_responsive_sheet(rows))
    outputs.append(build_mixed_garden_sheet(rows))
    for path in outputs:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
