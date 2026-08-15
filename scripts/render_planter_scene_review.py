from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.ui.plant_display import plant_layout


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
BEDLESS_REPORT = (
    ROOT
    / "artwork_source"
    / "backgrounds"
    / "bedless_v6"
    / "bedless-backgrounds.json"
)
OUTPUT_ROOT = ROOT / "build" / "planter-background-cleanup"

SCENES = (
    "verdant_twilight",
    "spring",
    "summer",
    "autumn",
    "snowy",
    "rainbow_horizon",
    "halloween",
    "full_moon",
    "eclipse",
)
VARIANTS = ("4x3", "16x9", "home")
HOVER_COLOR = (215, 237, 207)
HOVER_DESIRED_WIDTH = 1.65
HOVER_OPACITY = 0.55


def _canonical_placement() -> dict[str, object]:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    return next(
        row["placement"]
        for row in rows
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
    )


def _paste_layer(
    target: Image.Image,
    sprite: Image.Image,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    draw_width = max(1, round(width))
    draw_height = max(1, round(height))
    rendered = sprite.resize(
        (draw_width, draw_height),
        Image.Resampling.LANCZOS,
    )
    target.alpha_composite(rendered, (round(left), round(top)))


def _composite(
    background_path: Path,
    placement: dict[str, object],
    variant: str,
) -> Image.Image:
    background = Image.open(background_path).convert("RGBA")
    width, height = background.size
    family = placement["surface_profile"]["planter_family"]  # type: ignore[index]
    canvas_width, canvas_height = family["canvas"]
    soil_x, soil_y = family["soil_anchor"]
    variant_for_band = {"far": "back", "middle": "middle", "near": "front"}
    layouts = plant_layout(
        width,
        height,
        [{"slot_index": slot, "occupied": False} for slot in range(6)],
        placement,
        surface_context="home" if variant == "home" else "dashboard",
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )
    sprites: dict[tuple[str, str], Image.Image] = {}
    for family_variant, record in family["variants"].items():
        sprites[(family_variant, "base")] = Image.open(
            ADDON / record["file"]
        ).convert("RGBA")
        sprites[(family_variant, "foreground")] = Image.open(
            ADDON / record["foreground_file"]
        ).convert("RGBA")

    for band in ("far", "middle", "near"):
        family_variant = variant_for_band[band]
        record = family["variants"][family_variant]
        for layer_name in ("base", "foreground"):
            for layout in sorted(layouts, key=lambda row: row.z_depth):
                if layout.depth_band != band:
                    continue
                draw_width = (
                    layout.bed_footprint.width
                    * float(record.get("width_multiplier", family["width_multiplier"]))
                )
                draw_height = draw_width * canvas_height / canvas_width
                _paste_layer(
                    background,
                    sprites[(family_variant, layer_name)],
                    left=layout.ground_anchor[0] - float(soil_x) * draw_width,
                    top=layout.ground_anchor[1] - float(soil_y) * draw_height,
                    width=draw_width,
                    height=draw_height,
                )
    return background.convert("RGB")


def _review_sheet(
    variant: str,
    composites: list[tuple[str, Image.Image]],
) -> Path:
    cell_width = 720
    label_height = 44
    first = composites[0][1]
    cell_height = round(cell_width * first.height / first.width)
    sheet = Image.new(
        "RGB",
        (cell_width * 3, (cell_height + label_height) * 3),
        (14, 28, 25),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (scene, composite) in enumerate(composites):
        left = (index % 3) * cell_width
        top = (index // 3) * (cell_height + label_height)
        sheet.paste(
            composite.resize((cell_width, cell_height), Image.Resampling.LANCZOS),
            (left, top),
        )
        draw.text(
            (left + 16, top + cell_height + 15),
            f"{scene.replace('_', ' ').title()} - {variant} - six planters",
            font=font,
            fill=(236, 244, 232),
        )
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_ROOT / f"planter-family-{variant}-all-scenes.png"
    sheet.save(output, "PNG", optimize=True)
    return output


def _plant_box(layout: object, plant: dict[str, object]) -> tuple[float, float, float, float]:
    draw = layout.draw  # type: ignore[attr-defined]
    left, top, width, height = draw.x, draw.y, draw.width, draw.height
    if str(plant.get("stage", "")).lower() == "seed":
        width *= 1.12
        height *= 1.12
        left = draw.x + (draw.width - width) / 2
        top = draw.bottom - height
    return left, top, width, height


def _outer_contour(source: Image.Image, radius: int) -> Image.Image:
    radius = max(1, min(12, radius))
    alpha = source.getchannel("A")
    padding = radius + 1
    padded = Image.new("L", (source.width + padding * 2, source.height + padding * 2))
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            shifted = Image.new("L", padded.size)
            shifted.paste(alpha, (padding + dx, padding + dy))
            padded = ImageChops.lighter(padded, shifted)
    original = Image.new("L", padded.size)
    original.paste(alpha, (padding, padding))
    edge_alpha = ImageChops.subtract(padded, original).point(
        lambda value: round(value * HOVER_OPACITY)
    )
    edge = Image.new("RGBA", padded.size, (*HOVER_COLOR, 0))
    edge.putalpha(edge_alpha)
    return edge


def _render_hover_scene(placement: dict[str, object], *, hovered: bool) -> Image.Image:
    from scripts.render_planter_geometry_regression import _load_contract

    background_record, plants, _placement = _load_contract()
    variant = placement["surface_profile"]["variants"]["16:9"]  # type: ignore[index]
    scene = Image.open(ADDON / variant["file"]).convert("RGBA")
    width, height = scene.size
    layouts = plant_layout(
        width,
        height,
        plants,
        placement,
        composition_count=6,
        protected_status=False,
    )
    by_slot = {layout.slot_index: layout for layout in layouts}
    family = placement["surface_profile"]["planter_family"]  # type: ignore[index]
    canvas_width, canvas_height = family["canvas"]
    soil_x, soil_y = family["soil_anchor"]
    variant_for_band = {"far": "back", "middle": "middle", "near": "front"}
    del background_record

    for band in ("far", "middle", "near"):
        family_variant = variant_for_band[band]
        record = family["variants"][family_variant]
        base = Image.open(ADDON / record["file"]).convert("RGBA")
        foreground = Image.open(ADDON / record["foreground_file"]).convert("RGBA")
        band_slots = [
            slot for slot, layout in by_slot.items() if layout.depth_band == band
        ]
        for slot in band_slots:
            layout = by_slot[slot]
            draw_width = (
                layout.bed_footprint.width
                * float(record.get("width_multiplier", family["width_multiplier"]))
            )
            draw_height = draw_width * canvas_height / canvas_width
            _paste_layer(
                scene,
                base,
                left=layout.ground_anchor[0] - float(soil_x) * draw_width,
                top=layout.ground_anchor[1] - float(soil_y) * draw_height,
                width=draw_width,
                height=draw_height,
            )
        for slot in band_slots:
            layout = by_slot[slot]
            plant = plants[slot]
            artwork = Image.open(ADDON / plant["file"]).convert("RGBA")
            left, top, draw_width, draw_height = _plant_box(layout, plant)
            if hovered and slot == 0:
                scale = draw_width / max(1, artwork.width)
                radius = max(1, min(12, round(HOVER_DESIRED_WIDTH / max(0.01, scale))))
                edge = _outer_contour(artwork, radius)
                padding = radius + 1
                _paste_layer(
                    scene,
                    edge,
                    left=left - padding * scale,
                    top=top - padding * scale,
                    width=draw_width + padding * scale * 2,
                    height=draw_height + padding * scale * 2,
                )
            _paste_layer(
                scene,
                artwork,
                left=left,
                top=top,
                width=draw_width,
                height=draw_height,
            )
        for slot in band_slots:
            layout = by_slot[slot]
            draw_width = (
                layout.bed_footprint.width
                * float(record.get("width_multiplier", family["width_multiplier"]))
            )
            draw_height = draw_width * canvas_height / canvas_width
            _paste_layer(
                scene,
                foreground,
                left=layout.ground_anchor[0] - float(soil_x) * draw_width,
                top=layout.ground_anchor[1] - float(soil_y) * draw_height,
                width=draw_width,
                height=draw_height,
            )
    return scene.convert("RGB")


def _hover_review(placement: dict[str, object]) -> Path:
    normal = _render_hover_scene(placement, hovered=False)
    hovered = _render_hover_scene(placement, hovered=True)
    display_width = 1000
    display_height = round(display_width * normal.height / normal.width)
    canvas = Image.new(
        "RGB",
        (display_width * 2, display_height + 430),
        (14, 28, 25),
    )
    canvas.paste(normal.resize((display_width, display_height), Image.Resampling.LANCZOS), (0, 0))
    canvas.paste(hovered.resize((display_width, display_height), Image.Resampling.LANCZOS), (display_width, 0))
    crop = (500, 255, 820, 520)
    crop_width = 760
    crop_height = 360
    normal_crop = normal.crop(crop).resize((crop_width, crop_height), Image.Resampling.LANCZOS)
    hovered_crop = hovered.crop(crop).resize((crop_width, crop_height), Image.Resampling.LANCZOS)
    canvas.paste(normal_crop, (210, display_height + 52))
    canvas.paste(hovered_crop, (1030, display_height + 52))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((20, display_height + 18), "Normal", font=font, fill=(236, 244, 232))
    draw.text((display_width + 20, display_height + 18), "Hover outline", font=font, fill=(236, 244, 232))
    output = OUTPUT_ROOT / "hover-outline-final-review.png"
    canvas.save(output, "PNG", optimize=True)
    return output


def main() -> None:
    placement = _canonical_placement()
    report = json.loads(BEDLESS_REPORT.read_text(encoding="utf-8"))
    backgrounds = {
        (row["scene"], row["variant"]): ROOT / row["runtime"]
        for row in report["assets"]
    }
    for variant in VARIANTS:
        composites = [
            (
                scene,
                _composite(backgrounds[(scene, variant)], placement, variant),
            )
            for scene in SCENES
        ]
        print(_review_sheet(variant, composites))
    print(_hover_review(placement))


if __name__ == "__main__":
    main()
