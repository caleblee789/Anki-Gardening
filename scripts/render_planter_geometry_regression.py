from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
OUTPUT_ROOT = ROOT / "build" / "planter-geometry-regression"
BASE_SIZE = (800, 450)
SCALES = (0.75, 1.0, 1.25, 1.5)
FIXTURES = (
    ("bonsai", "seed"),
    ("rose", "sprout"),
    ("sunflower", "young"),
    ("lavender", "mature"),
    ("hydrangea", "flowering"),
    ("wisteria", "rare"),
)


def _load_contract() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    from ankigarden.ui.plant_display import plant_layout_item

    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    background = next(
        row
        for row in rows
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
    )
    plants: list[dict[str, Any]] = []
    for slot, (species, stage) in enumerate(FIXTURES):
        asset = next(
            row
            for row in rows
            if row.get("category") == "plants"
            and (row.get("slot") or {}).get("species") == species
            and (row.get("slot") or {}).get("stage") == stage
            and bool(row.get("release_preferred"))
        )
        item = {
            "plant_id": f"planter-regression-{slot}",
            "slot_index": slot,
            "species": species,
            "stage": stage,
            "asset_id": asset["asset_id"],
            "file": asset["file"],
            "placement": asset["placement"],
            "canvas_aspect": float(asset["width"]) / float(asset["height"]),
        }
        plants.append(plant_layout_item(item, slot))
    return background, plants, background["placement"]


def _variant(placement: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    from ankigarden.ui.plant_display import scene_surface_variant

    _name, selected = scene_surface_variant(placement, width, height, "dashboard")
    return selected


def _cover(path: Path, size: tuple[int, int]) -> Image.Image:
    source = Image.open(path).convert("RGBA")
    return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _paste_box(canvas: Image.Image, source: Image.Image, box: tuple[float, float, float, float]) -> None:
    left, top, width, height = box
    target_size = (max(1, round(width)), max(1, round(height)))
    resized = source.resize(target_size, Image.Resampling.LANCZOS)
    canvas.alpha_composite(resized, (round(left), round(top)))


def _trace_planter_outline(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[float, float, float, float],
    *,
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    """Mirror the runtime's alpha-following planter selection contour."""

    left, top, draw_width, draw_height = box
    target_size = (max(1, round(draw_width)), max(1, round(draw_height)))
    resized = source.resize(target_size, Image.Resampling.LANCZOS)
    alpha = resized.getchannel("A")
    radius = max(1, int(width))
    dilated = alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    edge_alpha = ImageChops.subtract(dilated, alpha).point(
        lambda value: round(value * color[3] / 255)
    )
    edge = Image.new("RGBA", target_size, (*color[:3], 0))
    edge.putalpha(edge_alpha)
    canvas.alpha_composite(edge, (round(left), round(top)))


def _plant_box(layout: Any, plant: dict[str, Any]) -> tuple[float, float, float, float]:
    left, top, width, height = layout.draw.x, layout.draw.y, layout.draw.width, layout.draw.height
    if str(plant.get("stage", "")).lower() == "seed":
        width *= 1.12
        height *= 1.12
        left = layout.draw.x + (layout.draw.width - width) / 2
        top = layout.draw.bottom - height
    return left, top, width, height


def _planter_spec(profile: dict[str, Any], depth_band: str) -> dict[str, Any] | None:
    family = profile.get("planter_family", {})
    variants = family.get("variants", {}) if isinstance(family, dict) else {}
    key = {"far": "back", "middle": "middle", "near": "front"}.get(depth_band, "")
    value = variants.get(key) if isinstance(variants, dict) else None
    if not isinstance(value, dict):
        return None
    return {**family, **value}


def _planter_box(layout: Any, spec: dict[str, Any]) -> tuple[float, float, float, float]:
    canvas = spec.get("canvas", [1024, 512])
    soil_anchor = spec.get("soil_anchor", [0.5, 220 / 512])
    width_multiplier = float(spec.get("width_multiplier", 1.28))
    draw_width = layout.bed_footprint.width * width_multiplier
    draw_height = draw_width * float(canvas[1]) / max(1.0, float(canvas[0]))
    return (
        layout.ground_anchor[0] - float(soil_anchor[0]) * draw_width,
        layout.ground_anchor[1] - float(soil_anchor[1]) * draw_height,
        draw_width,
        draw_height,
    )


def _geometry_row(plant: dict[str, Any], layout: Any) -> dict[str, Any]:
    def rect(value: Any) -> list[float]:
        return [round(value.x, 9), round(value.y, 9), round(value.width, 9), round(value.height, 9)]

    return {
        "slot": layout.slot_index,
        "bed_id": layout.surface_id,
        "assignment": plant["plant_id"],
        "anchor": [round(value, 9) for value in layout.ground_anchor],
        "scale": round(layout.scale, 9),
        "transform_origin": list(plant["placement"]["soil_contact"]),
        "z_index": round(layout.z_depth, 9),
        "draw": rect(layout.draw),
        "visible": rect(layout.visible),
        "hitbox": rect(layout.hit),
        "hit_center": [
            round(layout.hit.x + layout.hit.width / 2, 9),
            round(layout.hit.y + layout.hit.height / 2, 9),
        ],
        "label_anchor": [round(value, 9) for value in layout.label_anchor],
        "card_anchor": rect(layout.smart_card_anchor),
        "bed_footprint": rect(layout.bed_footprint),
    }


def render(label: str) -> Path:
    from ankigarden.ui.plant_display import plant_layout, scene_render_trace

    background, plants, placement = _load_contract()
    profile = placement["surface_profile"]
    destination = OUTPUT_ROOT / label
    destination.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"label": label, "fixtures": list(FIXTURES), "scales": {}}
    for scale in SCALES:
        width = round(BASE_SIZE[0] * scale)
        height = round(BASE_SIZE[1] * scale)
        scale_name = f"{round(scale * 100)}pct"
        variant = _variant(placement, width, height)
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
        scene = _cover(ADDON / variant["file"], (width, height))
        plant_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        def draw_plant(slot: int) -> None:
            plant = plants[slot]
            artwork = Image.open(ADDON / plant["file"]).convert("RGBA")
            _paste_box(plant_layer, artwork, _plant_box(by_slot[slot], plant))
            _paste_box(scene, artwork, _plant_box(by_slot[slot], plant))

        family = profile.get("planter_family")
        if isinstance(family, dict) and family.get("variants"):
            for band in ("far", "middle", "near"):
                slots = [slot for slot, row in by_slot.items() if row.depth_band == band]
                for slot in slots:
                    spec = _planter_spec(profile, band)
                    if spec:
                        _paste_box(scene, Image.open(ADDON / spec["file"]).convert("RGBA"), _planter_box(by_slot[slot], spec))
                for slot in slots:
                    draw_plant(slot)
                for slot in slots:
                    spec = _planter_spec(profile, band)
                    if spec and spec.get("foreground_file"):
                        _paste_box(scene, Image.open(ADDON / spec["foreground_file"]).convert("RGBA"), _planter_box(by_slot[slot], spec))
        else:
            for slot in (0, 1, 2, 3):
                draw_plant(slot)
            rear = (variant.get("occlusion_layers") or {}).get("rear")
            if rear:
                scene.alpha_composite(_cover(ADDON / rear, (width, height)))
            for slot in (4, 5):
                draw_plant(slot)
            front = (variant.get("occlusion_layers") or {}).get("front")
            if front:
                scene.alpha_composite(_cover(ADDON / front, (width, height)))

        selected_spec = _planter_spec(profile, by_slot[0].depth_band)
        if selected_spec:
            _trace_planter_outline(
                scene,
                Image.open(ADDON / selected_spec["file"]).convert("RGBA"),
                _planter_box(by_slot[0], selected_spec),
                color=(140, 224, 218, 235),
                width=max(2, round(scale * 2)),
            )
        draw = ImageDraw.Draw(scene, "RGBA")
        active = by_slot[0].visible
        radius = max(7, round(9 * scale))
        marker_x = min(width - radius - 3, round(active.right + radius + 3))
        marker_y = max(radius + 3, round(active.y + radius * 0.35))
        draw.ellipse(
            (marker_x - radius, marker_y - radius, marker_x + radius, marker_y + radius),
            fill=(226, 185, 76, 245),
            outline=(76, 62, 24, 245),
            width=max(1, round(scale)),
        )
        locked_x, locked_y = by_slot[5].label_anchor
        label = "Locked"
        font = ImageFont.load_default()
        text_box = draw.textbbox((0, 0), label, font=font)
        label_w = max(44, text_box[2] - text_box[0] + 12)
        label_h = max(20, text_box[3] - text_box[1] + 8)
        draw.rounded_rectangle(
            (locked_x - label_w / 2, locked_y - label_h / 2, locked_x + label_w / 2, locked_y + label_h / 2),
            radius=7,
            fill=(26, 34, 33, 190),
            outline=(158, 169, 164, 100),
        )
        draw.text((locked_x - label_w / 2 + 6, locked_y - 5), label, font=font, fill=(215, 224, 220, 210))

        scene.save(destination / f"scene-{scale_name}.png")
        plant_layer.save(destination / f"plants-{scale_name}.png")
        geometry = [_geometry_row(plants[slot], by_slot[slot]) for slot in range(6)]
        report["scales"][scale_name] = {
            "width": width,
            "height": height,
            "geometry": geometry,
            "render_order": list(scene_render_trace(layouts)),
        }
    report_path = destination / "geometry.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path


def compare(before: str, after: str) -> Path:
    before_dir, after_dir = OUTPUT_ROOT / before, OUTPUT_ROOT / after
    before_geometry = json.loads((before_dir / "geometry.json").read_text(encoding="utf-8"))
    after_geometry = json.loads((after_dir / "geometry.json").read_text(encoding="utf-8"))
    logical_match = before_geometry["scales"] == after_geometry["scales"]
    comparison_dir = OUTPUT_ROOT / f"{before}-vs-{after}"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for scale in SCALES:
        name = f"{round(scale * 100)}pct"
        first = Image.open(before_dir / f"plants-{name}.png").convert("RGBA")
        second = Image.open(after_dir / f"plants-{name}.png").convert("RGBA")
        difference = ImageChops.difference(first, second)
        difference.save(comparison_dir / f"plant-diff-{name}.png")
        a = first.getchannel("A")
        b = second.getchannel("A")
        overlay = Image.merge("RGBA", (a, b, b, ImageChops.lighter(a, b)))
        overlay.save(comparison_dir / f"plant-overlay-{name}.png")
        extrema = difference.getextrema()
        max_difference = max(channel[1] for channel in extrema)
        changed_pixels = sum(1 for pixel in difference.getdata() if any(pixel))
        rows.append({"scale": name, "max_channel_difference": max_difference, "changed_pixels": changed_pixels})
    result = {
        "before": before,
        "after": after,
        "logical_geometry_identical": logical_match,
        "plant_pixel_comparisons": rows,
    }
    if not logical_match or any(row["max_channel_difference"] > 1 for row in rows):
        raise SystemExit(json.dumps(result, indent=2))
    report_path = comparison_dir / "comparison.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", choices=("before", "after"))
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    if args.compare:
        print(compare("before", "after"))
    elif args.snapshot:
        print(render(args.snapshot))
    else:
        parser.error("use --snapshot before|after or --compare")


if __name__ == "__main__":
    main()
