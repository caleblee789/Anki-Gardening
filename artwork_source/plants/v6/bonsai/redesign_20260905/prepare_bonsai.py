"""Compile only Bonsai artwork and write a guarded central-integration handoff.

Creative changes are ImageGen-authored. This script only cleans alpha/edges,
normalizes the sprite canvas, measures geometry, and exports lossless assets.
Run using the bundled Python runtime with Pillow and NumPy installed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "build/bonsai-redesign/20260905-v1"
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
TARGET_HEIGHTS = dict(zip(STAGES, (34.0, 50.0, 72.0, 100.0, 120.0, 124.0)))
CANVAS = 1254
BASELINE = 1179

os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")
sys.path.insert(0, str(OUT / "source-snapshot"))
from ankigarden.asset_manager import AssetPlacement  # noqa: E402
from ankigarden.ui.plant_display import plant_layout  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_rect(bounds):
    x0, y0, x1, y1 = bounds
    return [round(x0 / CANVAS, 6), round(y0 / CANVAS, 6),
            round((x1 - x0) / CANVAS, 6), round((y1 - y0) / CANVAS, 6)]


def clean_alpha(stage: str) -> tuple[Image.Image, dict]:
    source = Image.open(HERE / "alpha" / f"bonsai_{stage}_alpha_v1.png").convert("RGBA")
    pixels = np.array(source)
    original = pixels.copy()
    alpha = pixels[:, :, 3]
    alpha[alpha < 12] = 0
    # Opaque plant interiors must not inherit the generator's near-opaque haze.
    interior = np.asarray(Image.fromarray(alpha).filter(ImageFilter.MinFilter(5))) >= 240
    alpha[interior] = 255
    # Cyan is used only as a technical background, never in this plant palette.
    # Decontaminate at most three boundary pixels; leave interior RGB untouched.
    near_empty = np.asarray(Image.fromarray(alpha).filter(ImageFilter.MinFilter(7))) == 0
    rgb = pixels[:, :, :3].astype(np.int16)
    cyan = (np.minimum(rgb[:, :, 1], rgb[:, :, 2]) - rgb[:, :, 0] > 25)
    cyan &= rgb[:, :, 2] > 105
    candidates = (alpha > 0) & near_empty & (cyan | (alpha < 96))
    clean = (alpha >= 240) & ~cyan
    repaired = np.zeros(alpha.shape, dtype=bool)
    # Take the closest clean foreground RGB, preserving the original edge alpha.
    offsets = sorted(((dx * dx + dy * dy, dx, dy) for dy in range(-6, 7)
                      for dx in range(-6, 7) if dx or dy))
    for _, dx, dy in offsets:
        available = np.roll(clean, (-dy, -dx), axis=(0, 1))
        if dy > 0: available[-dy:, :] = False
        if dy < 0: available[:-dy, :] = False
        if dx > 0: available[:, -dx:] = False
        if dx < 0: available[:, :-dx] = False
        take = candidates & ~repaired & available
        if np.any(take):
            colors = np.roll(original[:, :, :3], (-dy, -dx), axis=(0, 1))
            pixels[take, :3] = colors[take]
            repaired |= take
        if np.all(repaired[candidates]): break
    alpha[candidates & ~repaired] = 0
    pixels[alpha == 0, :3] = 0
    result = Image.fromarray(pixels, "RGBA")
    confident = result.getchannel("A").point(lambda v: 255 if v >= 192 else 0)
    bounds = confident.getbbox()
    assert bounds is not None
    # Trim only empty/faint residue outside the actual subject; keep a soft edge.
    x0, y0, x1, y1 = bounds
    crop = (max(0, x0 - 4), max(0, y0 - 4), min(CANVAS, x1 + 4), min(CANVAS, y1 + 4))
    result = result.crop(crop)
    h = result.height
    root_band = confident.crop((0, max(0, y1 - max(24, round((y1-y0)*.06))), CANVAS, y1)).getbbox()
    root_center = (root_band[0] + root_band[2]) / 2 - crop[0]
    factor = min(1092 / result.height, 1092 / result.width)
    # The final crown shares Flowering's width but earns a modest height lift.
    vertical_factor = 1.05 if stage == "rare" else 1.0
    new_size = (round(result.width * factor), round(result.height * factor * vertical_factor))
    resized = result.convert("RGBa").resize(new_size, Image.Resampling.LANCZOS).convert("RGBA")
    box = resized.getchannel("A").point(lambda v: 255 if v >= 192 else 0).getbbox()
    ox = round(CANVAS / 2 - root_center * factor)
    oy = BASELINE - (box[3] - 1)
    assert 0 <= ox and ox + resized.width <= CANVAS and 0 <= oy and oy + resized.height <= CANVAS
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(resized, (ox, oy))
    untouched = ~repaired & (original[:, :, 3] > 0)
    assert np.array_equal(pixels[:, :, :3][untouched & (alpha > 0)], original[:, :, :3][untouched & (alpha > 0)])
    return canvas, {"edge_rgb_pixels_repaired": int(repaired.sum()),
                    "opaque_interior_rgb_preserved": True,
                    "source_alpha_mode": source.mode,
                    "scale": factor, "vertical_factor": vertical_factor, "offset": [ox, oy]}


def main():
    if (OUT / "COMPLETE.json").exists():
        raise SystemExit("This review is sealed. Choose a new output version before regenerating it.")
    previous = json.loads((OUT / "baseline/prior-bonsai-entries.json").read_text())
    frozen = OUT / "source-snapshot/ankigarden/assets/manifest.json"
    manifest = json.loads(frozen.read_text())
    background = next(a for a in manifest["assets"] if a.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6")
    patches = {}
    report = {}
    for stage in STAGES:
        art, cleanup = clean_alpha(stage)
        master = HERE / f"bonsai_{stage}_master_v1.png"
        art.save(master, "PNG", optimize=True)
        runtime = OUT / "candidate-runtime" / f"bonsai_{stage}_twilight_v6.webp"
        art.save(runtime, "WEBP", lossless=True, quality=100, method=6, exact=True)
        with Image.open(runtime) as loaded:
            assert loaded.mode == "RGBA" and loaded.size == (CANVAS, CANVAS)
            assert loaded.tobytes() == art.tobytes()
        asset_id = f"plant_bonsai_{stage}_twilight_v6"
        row = copy.deepcopy(previous[asset_id]["entry"])
        row["source_master_file"] = master.relative_to(ROOT).as_posix()
        row["source_master_sha256"] = sha(master)
        row["source"] = "ImageGen cohesive Bonsai redesign; approved alpha/edge cleanup; lossless RGBA export"
        p = row["placement"]
        alpha = art.getchannel("A")
        bounds = alpha.point(lambda v: 255 if v >= 24 else 0).getbbox()
        solid = alpha.point(lambda v: 255 if v >= 192 else 0).getbbox()
        x0, y0, x1, y1 = bounds
        band_height = max(24, round((solid[3]-solid[1]) * .06))
        roots = alpha.crop((0, solid[3] - band_height, CANVAS, solid[3])).point(lambda v: 255 if v >= 192 else 0).getbbox()
        support = [roots[0], BASELINE - band_height, roots[2], BASELINE]
        vb = normalized_rect(bounds)
        p.update({"anchor_x": .5, "baseline_y": BASELINE/CANVAS,
                  "ground_anchor": [.5, round(BASELINE/CANVAS, 6)],
                  "ground_anchor_x": .5, "ground_anchor_y": round(BASELINE/CANVAS, 6),
                  "soil_contact": [.5, round(BASELINE/CANVAS, 6)],
                  "art_bounds": vb, "visible_bounds": vb, "foliage_bounds": vb,
                  "plant_above_rim_bounds": vb, "interaction_bounds": vb,
                  "visual_center": [round((x0+x1)/2/CANVAS, 6), round((y0+y1)/2/CANVAS, 6)],
                  "base_bounds": normalized_rect(support), "support_bounds": normalized_rect(support),
                  "contact_shadow": [.82, .075], "shadow_offset": [0.0, 0.0],
                  "thumbnail_bounds": vb, "thumbnail_optical_center": [round((x0+x1)/2/CANVAS, 6), round((y0+y1)/2/CANVAS, 6)],
                  "thumbnail_safe_padding": .10,
                  "review_provenance": "bonsai-redesign-20260905-v1"})
        p.pop("thumbnail_scale", None)
        if stage == "seed":
            p["scene_scale_correction"] = .5
        # Calibrate physical height independently from the generous source canvas.
        for _ in range(3):
            item={"slot_index":0,"species":"bonsai","stage":stage,"placement":p,"canvas_aspect":1,"occupied":True}
            layout=plant_layout(1260,840,[item],background["placement"],composition_count=6,protected_status=False)[0]
            p["visual_scale_correction"] = max(.5,min(1.5,p["visual_scale_correction"]*TARGET_HEIGHTS[stage]/layout.visible.height))
        p["visual_scale_correction"] = round(p["visual_scale_correction"],6)
        if stage == "rare":
            flowering=patches["plant_bonsai_flowering_twilight_v6"]["replacement"]["placement"]
            p["visual_scale_correction"] = flowering["scene_scale_correction"]*flowering["visual_scale_correction"]/p["scene_scale_correction"]
        normalized = AssetPlacement.from_manifest(p,category="plants").to_dict()
        layout=plant_layout(1260,840,[{"slot_index":0,"species":"bonsai","stage":stage,"placement":normalized,"canvas_aspect":1,"occupied":True}],background["placement"],composition_count=6,protected_status=False)[0]
        patches[asset_id] = {"prior_entry_sha256": previous[asset_id]["entry_sha256"],
                             "prior_runtime_sha256": previous[asset_id]["runtime_sha256"],
                             "runtime_candidate": runtime.relative_to(ROOT).as_posix(),
                             "runtime_sha256": sha(runtime), "replacement": row}
        report[stage] = {**cleanup,"visible_scene_px":[layout.visible.width,layout.visible.height],
                         "root_support_px":[layout.support_rect.width,layout.support_rect.height],
                         "contact_shadow_px":[layout.grounding.contact_shadow.width,layout.grounding.contact_shadow.height],
                         "source_bounds":list(bounds),"warnings":list(layout.validation_warnings),
                         "thumbnail_scale": normalized["thumbnail_scale"],"rgba_lossless_pixel_parity":True}
        dest=OUT/"source-snapshot/ankigarden"/row["file"]
        dest.write_bytes(runtime.read_bytes())
    mapping={key:entry["replacement"] for key,entry in patches.items()}
    manifest["assets"]=[mapping.get(a["asset_id"],a) for a in manifest["assets"]]
    frozen.write_text(json.dumps(manifest,indent=2)+"\n")
    (OUT/"handoff/bonsai-manifest-replacements.json").write_text(json.dumps({"species":"bonsai","entry_hash_serialization":"json.dumps(entry,sort_keys=True,separators=(',',':')) UTF-8","replacements":patches},indent=2)+"\n")
    (OUT/"preparation-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
