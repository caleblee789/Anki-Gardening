from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
POTTED_SPECIES = {"bonsai", "rose", "cactus", "orchid", "moonflower", "fern", "ivy"}
STAGES = {"seed", "sprout", "young", "mature", "flowering", "rare"}


def _round(values: tuple[float, ...]) -> list[float]:
    return [round(value, 4) for value in values]


def main() -> None:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    selected: dict[tuple[str, str], dict] = {}
    for row in payload["assets"]:
        slot = row.get("slot", {})
        key = (str(slot.get("species", "")), str(slot.get("stage", "")))
        if key[0] not in POTTED_SPECIES or key[1] not in STAGES:
            continue
        placement = row.get("placement", {})
        if placement.get("base_type") != "pot":
            continue
        current = selected.get(key)
        if current is None or float(row.get("quality_score", 0)) > float(current.get("quality_score", 0)):
            selected[key] = row
    if len(selected) != 42:
        raise RuntimeError(f"expected 42 selected potted assets, found {len(selected)}")

    for row in selected.values():
        path = ROOT / "ankigarden" / row["file"]
        with Image.open(path) as image:
            alpha = image.convert("RGBA").getchannel("A")
            bounds = alpha.getbbox()
            if bounds is None:
                raise RuntimeError(f"asset has no visible pixels: {path}")
            width, height = image.size
        left, top, right, bottom = bounds
        art = (left / width, top / height, (right - left) / width, (bottom - top) / height)
        placement = row["placement"]
        scale = float(placement.get("display_scale", placement.get("scale", 1.0)))
        base_width = min(0.9, 0.39 / max(0.25, scale))
        base_height = min(art[3] * 0.42, base_width * 0.68)
        base_x = max(0.0, min(1.0 - base_width, 0.5 - base_width / 2))
        base_y = max(art[1], bottom / height - base_height)
        foliage_height = max(0.01, base_y - art[1])
        base = (base_x, base_y, base_width, base_height)
        placement.update({
            "art_bounds": _round(art),
            "visible_bounds": _round(art),
            "base_bounds": _round(base),
            "foliage_bounds": _round((art[0], art[1], art[2], foliage_height)),
            "soil_contact": _round((base_x + base_width / 2, base_y + base_height)),
            "ground_anchor": _round((base_x + base_width / 2, base_y + base_height)),
            "interaction_bounds": _round((max(0.0, art[0] - 0.015), max(0.0, art[1] - 0.015), min(1.0 - max(0.0, art[0] - 0.015), art[2] + 0.03), min(1.0 - max(0.0, art[1] - 0.015), art[3] + 0.03))),
            "contact_shadow": _round((min(1.0, base_width * 1.18), 0.045)),
        })
        variants = list(row.get("variants", []))
        if "phase2_grounded" not in variants:
            variants.append("phase2_grounded")
        row["variants"] = variants
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
