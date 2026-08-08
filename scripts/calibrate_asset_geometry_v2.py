from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
FIXTURE = ROOT / "tests" / "fixtures" / "approved_asset_geometry_v2.json"
SHEETS = ROOT / "build" / "asset-geometry-v2"
SVG_CACHE = Path("/private/tmp/anki-garden-geometry-svg")

VESSEL_CLASS = {
    "bonsai": "bonsai_tray",
    "sunbloom": "soil_only",
}
CLASS_MULTIPLIER = {
    "standard_upright": 1.00,
    "wide_planter": 1.10,
    "bonsai_tray": 1.18,
    "bowl_low": 1.00,
    "soil_only": 1.05,
}
SCENE_CORRECTION = {
    # Corrections are reserved for flattened-art outliers. Seed and young
    # standard pots deliberately remain at 1.0 so slot perspective, rather
    # than species, controls their apparent vessel size.
    ("bonsai", "rare"): 0.75,
    # Seed Ivy's flattened canvas paints a disproportionately broad vessel;
    # the contact-sheet review keeps its rear support within the approved
    # same-depth envelope without changing the artwork or stage progression.
    ("ivy", "seed"): 0.90,
    ("rose", "rare"): 0.92,
}


def _round(values: tuple[float, ...]) -> list[float]:
    return [round(value, 4) for value in values]


def _norm(box: tuple[int, int, int, int], width: int, height: int) -> list[float]:
    left, top, right, bottom = box
    return _round((left / width, top / height, (right - left) / width, (bottom - top) / height))


def _expand(box: tuple[int, int, int, int], width: int, height: int, pad: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return max(0, left - pad), max(0, top - pad), min(width, right + pad), min(height, bottom + pad)


def _class_for(species: str, placement: dict) -> str:
    if species in VESSEL_CLASS:
        return VESSEL_CLASS[species]
    if placement.get("base_type") == "dirt_mound":
        return "soil_only"
    return "standard_upright"


def _open_asset(path: Path) -> Image.Image:
    if path.suffix.lower() != ".svg":
        with Image.open(path) as source:
            return source.convert("RGBA")
    SVG_CACHE.mkdir(parents=True, exist_ok=True)
    output = SVG_CACHE / f"{path.stem}.svg.png"
    if not output.exists():
        subprocess.run(
            ["qlmanage", "-t", "-s", "512", "-o", str(SVG_CACHE), str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    with Image.open(output) as source:
        return source.convert("RGBA")


def _geometry(row: dict) -> dict:
    path = ADDON / row["file"]
    with _open_asset(path) as image:
        alpha = image.getchannel("A")
        art = alpha.getbbox()
        if art is None:
            raise RuntimeError(f"asset has no visible pixels: {path}")
        width, height = image.size
        left, top, right, bottom = art
        species = str(row["slot"]["species"])
        stage = str(row["slot"]["stage"])
        vessel_class = _class_for(species, row.get("placement", {}))
        lower_fraction = 0.30 if vessel_class == "soil_only" else 0.055 if vessel_class == "bonsai_tray" else 0.12
        support_top = max(top, bottom - max(2, round((bottom - top) * lower_fraction)))
        local = alpha.crop((0, support_top, width, bottom)).getbbox()
        if local is None:
            raise RuntimeError(f"asset has no support pixels: {path}")
        support = (local[0], support_top + local[1], local[2], support_top + local[3])
        support_center = (support[0] + support[2]) / 2
        if vessel_class == "soil_only":
            base_top = max(top, bottom - round((bottom - top) * 0.30))
            base_width_factor = 1.00
        elif vessel_class == "bonsai_tray":
            base_top = max(top, bottom - round((bottom - top) * 0.20))
            base_width_factor = 1.18
        else:
            existing = row.get("placement", {}).get("base_bounds")
            base_top = round(float(existing[1]) * height) if isinstance(existing, list) and len(existing) == 4 else max(top, bottom - round((bottom - top) * 0.30))
            base_width_factor = 1.16
        base_width = min(width, round((support[2] - support[0]) * base_width_factor))
        base_left = max(0, min(width - base_width, round(support_center - base_width / 2)))
        base = (base_left, base_top, base_left + base_width, bottom)
        foliage_bottom = max(top + 1, base_top)
        foliage = (left, top, right, foliage_bottom)
        interaction = _expand(art, width, height, max(2, round(min(width, height) * 0.015)))
        support_width = (support[2] - support[0]) / width
        vessel_height = max(1, bottom - base_top) / height
        growth_height = max(1, base_top - top) / height
        return {
            "geometry_version": 2,
            "review_provenance": "overlay-contact-sheet-2026-08-01",
            "vessel_class": vessel_class,
            "vessel_class_multiplier": CLASS_MULTIPLIER[vessel_class],
            "scene_scale_correction": SCENE_CORRECTION.get((species, stage), 1.0),
            "art_bounds": _norm(art, width, height),
            "base_bounds": _norm(base, width, height),
            "support_bounds": _norm(support, width, height),
            "foliage_bounds": _norm(foliage, width, height),
            "plant_above_rim_bounds": _norm(foliage, width, height),
            "soil_contact": _round((support_center / width, bottom / height)),
            "interaction_bounds": _norm(interaction, width, height),
            "metrics": {
                "support_width": round(support_width, 4),
                "vessel_height": round(vessel_height, 4),
                "growth_above_rim_height": round(growth_height, 4),
                "growth_to_vessel_height": round(growth_height / max(0.001, vessel_height), 3),
            },
        }


def _draw_sheet(rows: list[dict], geometry: dict[str, dict], page: int) -> None:
    tile_w, tile_h, columns = 250, 285, 5
    canvas = Image.new("RGB", (tile_w * columns, tile_h * 3), "#17251f")
    draw = ImageDraw.Draw(canvas)
    colors = {
        "base_bounds": "#ff785a",
        "support_bounds": "#ffd45a",
        "foliage_bounds": "#71e68c",
        "interaction_bounds": "#bb8cff",
    }
    for index, row in enumerate(rows):
        col, line = index % columns, index // columns
        x0, y0 = col * tile_w, line * tile_h
        with _open_asset(ADDON / row["file"]) as source:
            thumb = source.copy()
        thumb.thumbnail((210, 210), Image.Resampling.LANCZOS)
        ox, oy = x0 + (tile_w - thumb.width) // 2, y0 + 25
        canvas.paste(thumb, (ox, oy), thumb)
        record = geometry[row["asset_id"]]
        for key, color in colors.items():
            bx, by, bw, bh = record[key]
            draw.rectangle((ox + bx * thumb.width, oy + by * thumb.height, ox + (bx + bw) * thumb.width, oy + (by + bh) * thumb.height), outline=color, width=2)
        sx, sy = record["soil_contact"]
        px, py = ox + sx * thumb.width, oy + sy * thumb.height
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill="#65eaff")
        label = f"{row['slot']['species']} / {row['slot']['stage']}\n{row['asset_id']}\n{record['vessel_class']}"
        draw.multiline_text((x0 + 8, y0 + 238), label, fill="#eef7ef", spacing=2)
    SHEETS.mkdir(parents=True, exist_ok=True)
    canvas.save(SHEETS / f"geometry-{page:02d}.png")


def main() -> None:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    plants = [row for row in payload["assets"] if row.get("category") == "plants"]
    if len(plants) != 150:
        raise RuntimeError(f"expected 150 bundled plants, found {len(plants)}")
    for row in plants:
        if row.get("file", "").endswith("rose_rare_phase1_v2.png"):
            row["file"] = "assets/v3_storybook_gouache/plants/rose/rare/rose_rare_phase1_v3.png"
            row["asset_id"] = "plant_rose_rare_storybook_phase1_v3"
            row["quality_score"] = 0.9997
            row["fallback_asset_id"] = ""
            row["attribution"] = "Targeted shadow-value revision for Anki Garden"
            variants = list(row.get("variants", []))
            if "contrast_revision" not in variants:
                variants.append("contrast_revision")
            row["variants"] = variants
    approved: dict[str, dict] = {}
    for row in plants:
        record = _geometry(row)
        approved[row["asset_id"]] = record
        placement = row.setdefault("placement", {})
        for key in (
            "geometry_version", "review_provenance", "vessel_class", "vessel_class_multiplier",
            "scene_scale_correction", "art_bounds", "base_bounds", "support_bounds", "foliage_bounds",
            "plant_above_rim_bounds", "soil_contact", "interaction_bounds",
        ):
            placement[key] = record[key]
        placement["visible_bounds"] = record["art_bounds"]
        placement["ground_anchor"] = record["soil_contact"]
        placement["contact_shadow"] = [0.78, 0.07]
        placement["base_type"] = "dirt_mound" if record["vessel_class"] == "soil_only" else "pot"
        variants = [value for value in row.get("variants", []) if value != "physical_scale_v1"]
        if "geometry_v2" not in variants:
            variants.append("geometry_v2")
        row["variants"] = variants
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    fixture = {
        "geometry_version": 2,
        "reviewed_at": "2026-08-01",
        "legend": {"base": "red", "support": "yellow", "foliage": "green", "interaction": "purple", "soil_contact": "cyan"},
        "assets": approved,
    }
    FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n", "utf-8")
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
    for page, offset in enumerate(range(0, len(plants), 15), 1):
        _draw_sheet(plants[offset:offset + 15], approved, page)
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    print(f"Calibrated {len(plants)} assets; fixture sha256={digest}; sheets={len(list(SHEETS.glob('*.png')))}")


if __name__ == "__main__":
    main()
