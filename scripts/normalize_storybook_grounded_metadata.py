from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
SEMANTIC_KEYS = ("art_bounds", "base_bounds", "foliage_bounds", "soil_contact", "interaction_bounds")


def _rounded(values: tuple[float, ...]) -> list[float]:
    return [round(value, 4) for value in values]


def _alpha_art(row: dict) -> tuple[float, float, float, float]:
    path = ROOT / "ankigarden" / row["file"]
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        bounds = alpha.getbbox()
        width, height = image.size
    if bounds is None:
        raise RuntimeError(f"asset has no visible pixels: {path}")
    left, top, right, bottom = bounds
    return left / width, top / height, (right - left) / width, (bottom - top) / height


def _sunbloom_geometry(row: dict) -> dict[str, list[float]]:
    """Measure the broad lower dirt mound without treating the sprout as its base."""
    path = ROOT / "ankigarden" / row["file"]
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        art_pixels = alpha.getbbox()
        if art_pixels is None:
            raise RuntimeError(f"asset has no visible pixels: {path}")
        width, height = image.size
        left, top, right, bottom = art_pixels
        mound_top = max(top, bottom - max(2, round((bottom - top) * 0.30)))
        mound = alpha.crop((0, mound_top, width, bottom)).getbbox()
    if mound is None:
        raise RuntimeError(f"asset has no grounded pixels: {path}")
    mound_left, mound_y, mound_right, mound_bottom = mound
    mound_y += mound_top
    mound_bottom += mound_top
    art = (left / width, top / height, (right - left) / width, (bottom - top) / height)
    base = (
        mound_left / width,
        mound_y / height,
        (mound_right - mound_left) / width,
        (mound_bottom - mound_y) / height,
    )
    interaction_x = max(0.0, art[0] - 0.015)
    interaction_y = max(0.0, art[1] - 0.015)
    return {
        "art_bounds": _rounded(art),
        "visible_bounds": _rounded(art),
        "base_bounds": _rounded(base),
        "foliage_bounds": _rounded((art[0], art[1], art[2], max(0.01, base[1] - art[1]))),
        "soil_contact": _rounded((base[0] + base[2] / 2, base[1] + base[3])),
        "ground_anchor": _rounded((base[0] + base[2] / 2, base[1] + base[3])),
        "interaction_bounds": _rounded((
            interaction_x, interaction_y,
            min(1.0 - interaction_x, art[2] + 0.03),
            min(1.0 - interaction_y, art[3] + 0.03),
        )),
        "contact_shadow": [0.80, 0.075],
    }


def main() -> None:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    storybook = [
        row for row in payload["assets"]
        if row.get("category") == "plants" and row.get("style_family") == "storybook_gouache"
    ]
    references: dict[tuple[str, str], dict] = {}
    for row in storybook:
        placement = row.get("placement", {})
        if all(key in placement for key in SEMANTIC_KEYS):
            key = (str(row["slot"]["species"]), str(row["slot"]["stage"]))
            current = references.get(key)
            if current is None or float(row.get("quality_score", 0)) > float(current.get("quality_score", 0)):
                references[key] = row

    updated = 0
    for row in storybook:
        placement = row.setdefault("placement", {})
        if all(key in placement for key in SEMANTIC_KEYS):
            placement["contact_shadow"] = [0.80, 0.075]
            continue
        species = str(row["slot"]["species"])
        stage = str(row["slot"]["stage"])
        if placement.get("base_type") == "dirt_mound":
            placement.update(_sunbloom_geometry(row))
        else:
            reference = references.get((species, stage))
            if reference is None:
                raise RuntimeError(f"no semantic reference for {species}/{stage}")
            source = reference["placement"]
            for key in (*SEMANTIC_KEYS, "visible_bounds", "ground_anchor"):
                placement[key] = deepcopy(source[key])
            placement["contact_shadow"] = [0.80, 0.075]
        variants = list(row.get("variants", []))
        if "physical_scale_v1" not in variants:
            variants.append("physical_scale_v1")
        row["variants"] = variants
        updated += 1

    if len(storybook) != 99 or any(
        not all(key in row.get("placement", {}) for key in SEMANTIC_KEYS) for row in storybook
    ):
        raise RuntimeError("storybook semantic normalization is incomplete")
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
    print(f"Normalized {updated} storybook assets; verified {len(storybook)} semantic contracts.")


if __name__ == "__main__":
    main()
