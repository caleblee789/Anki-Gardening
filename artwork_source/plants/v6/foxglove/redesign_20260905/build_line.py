"""Reproduce Foxglove's species-only staging bundle; never rewrite the shared catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.process_direct_soil_asset import remove_connected_chroma, _despill_transparency_boundary, _border_key
from scripts.install_direct_soil_catalog_v6 import _largest_component_bounds

STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SELECTED = {s: s for s in STAGES} | {"young": "young_chroma", "flowering": "flowering_chroma"}
ENVELOPES = {"seed": (360, 215), "sprout": (420, 410), "young": (760, 580),
             "mature": (1030, 1180), "flowering": (1030, 1180), "rare": (1030, 1180)}
CANVAS = 1254
BASELINE = 1200


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_relative(stage: str) -> Path:
    return Path("ankigarden/assets/v6_storybook_gouache/plants/foxglove") / stage / f"foxglove_{stage}_twilight_v6.webp"


def clear_key_fringe(source: Image.Image, rgba: Image.Image) -> tuple[Image.Image, int]:
    """Clear magenta background gradients connected to the known chroma matte.

    The generated violet bells have more blue than red. Requiring nearly equal
    red/blue protects that pigment while following the pink background between
    bells. Connectivity is established from the raw RGB, before edge despill.
    Deep subject pixels outside this connected mask remain untouched.
    """
    rgb = source.convert("RGB")
    key = _border_key(rgb)
    width, height = rgb.size
    pixels = list(rgb.getdata())
    eligible = bytearray(width * height)
    mask = bytearray(width * height)
    queue = deque()
    for index, (r, g, b) in enumerate(pixels):
        near_key = sum((c-k)**2 for c, k in zip((r, g, b), key)) <= 64**2
        pink_matte = r >= 185 and b >= 165 and g <= 155 and min(r, b)-g >= 80 and r >= 0.90*b
        eligible[index] = near_key or pink_matte
        if near_key:
            mask[index] = 1
            queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        neighbors = []
        if x: neighbors.append(index-1)
        if x+1 < width: neighbors.append(index+1)
        if y: neighbors.append(index-width)
        if y+1 < height: neighbors.append(index+width)
        for other in neighbors:
            if eligible[other] and not mask[other]:
                mask[other] = 1
                queue.append(other)
    alpha = bytearray(rgba.getchannel("A").tobytes())
    changed = sum(bool(value and mask[index]) for index, value in enumerate(alpha))
    for index, selected in enumerate(mask):
        if selected:
            alpha[index] = 0
    result = rgba.copy()
    result.putalpha(Image.frombytes("L", rgba.size, bytes(alpha)))
    return result, changed


def soften_key_edge(rgba: Image.Image) -> tuple[Image.Image, int]:
    """Restore edge pigment from nearby clean subject RGB, preserving alpha."""
    def spill(p):
        r, g, b, a = p
        return a >= 16 and r >= 120 and b >= 100 and r >= .90*b and min(r, b)-g >= 35
    near = rgba.getchannel("A").point(lambda a: 255 if a < 16 else 0).filter(ImageFilter.MaxFilter(5))
    source, proximity = rgba.load(), near.load()
    result = rgba.copy()
    target = result.load()
    changed = 0
    for y in range(rgba.height):
        for x in range(rgba.width):
            if not proximity[x, y] or not spill(source[x, y]):
                continue
            replacement = None
            for radius in range(1, 13):
                choices = []
                for yy in range(max(0, y-radius), min(rgba.height, y+radius+1)):
                    for xx in range(max(0, x-radius), min(rgba.width, x+radius+1)):
                        pixel = source[xx, yy]
                        if max(abs(xx-x), abs(yy-y)) == radius and pixel[3] >= 192 and not spill(pixel):
                            choices.append((not proximity[xx, yy], pixel[3], -yy, -xx, pixel))
                if choices:
                    replacement = max(choices)[-1]
                    break
            if replacement is None:
                raise ValueError(f"No clean edge pigment near {(x, y)}")
            target[x, y] = (*replacement[:3], source[x, y][3])
            changed += 1
    assert result.getchannel("A").tobytes() == rgba.getchannel("A").tobytes()
    return result, changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    records = json.loads((run / "generation-record.json").read_text())
    by_key = {r["key"]: r for r in records}
    version = Path(__file__).resolve().parent
    (version / "generated").mkdir(exist_ok=True)
    (run / "extracted").mkdir(exist_ok=True)
    candidate = run / "candidate"
    report = {}
    for stage in STAGES:
        row = by_key[SELECTED[stage]]
        master = version / "generated" / f"foxglove_{stage}_generated.png"
        if not master.exists():
            shutil.copy2(row["generated_path"], master)
        source = Image.open(master)
        native_alpha = "A" in source.getbands() and source.getchannel("A").getextrema()[0] == 0
        extracted = run / "extracted" / f"foxglove_{stage}_alpha.png"
        if native_alpha:
            rgba = source.convert("RGBA")
            rgba.save(extracted)
            matte_pixels = 0
        else:
            # The generator's nominally flat key has a small corner gradient.
            # These bounds remove that background without touching the much
            # more distant green, coral, umber, or violet botanical pigments.
            remove_connected_chroma(master, extracted, transparent_threshold=36.0, connection_threshold=64.0)
            rgba = Image.open(extracted).convert("RGBA")
            rgba, matte_pixels = clear_key_fringe(source, rgba)
            rgba, _ = _despill_transparency_boundary(rgba, boundary_radius=4)
            rgba.save(extracted)
        bounds = _largest_component_bounds(rgba.getchannel("A"))
        if bounds is None:
            raise ValueError(f"No primary plant component: {stage}")
        left, top, right, bottom = bounds
        crop = rgba.crop((max(0, left - 4), max(0, top - 4), min(rgba.width, right + 4), min(rgba.height, bottom + 4)))
        target_w, target_h = ENVELOPES[stage]
        factor = min(1.0, target_w / crop.width, target_h / crop.height)
        resized = crop.convert("RGBa").resize((round(crop.width * factor), round(crop.height * factor)), Image.Resampling.LANCZOS).convert("RGBA")
        final = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        final.alpha_composite(resized, ((CANVAS - resized.width) // 2, BASELINE - resized.height))
        # Resampling can amplify trace edge RGB at very low alpha. The
        # existing final boundary pass changes edge RGB while preserving alpha.
        final, final_despilled = _despill_transparency_boundary(final, boundary_radius=4)
        if not native_alpha:
            final, subtle_fringe_pixels = soften_key_edge(final)
        else:
            subtle_fringe_pixels = 0
        runtime = candidate / stage_relative(stage)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        final.save(runtime, "WEBP", lossless=True, exact=True, method=6)
        alpha_master = version / f"foxglove_{stage}_alpha.png"
        final.save(alpha_master, "PNG", optimize=True)
        chroma = Image.new("RGB", final.size, (255, 0, 255))
        chroma.paste(final, mask=final.getchannel("A"))
        canonical = candidate / "artwork_source/plants/v6/foxglove" / f"foxglove_{stage}_chroma.png"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        chroma.save(canonical, "PNG", optimize=True)
        report[stage] = {"selected_generation_key": SELECTED[stage], "native_alpha": native_alpha,
                         "generated_master": str(master.relative_to(ROOT)), "generated_sha256": sha(master),
                         "runtime": str(runtime.relative_to(run)), "runtime_sha256": sha(runtime),
                         "alpha_master_sha256": sha(alpha_master), "source_master_sha256": sha(canonical),
                         "post_resize_boundary_pixels": final_despilled,
                         "connected_key_fringe_pixels_cleared": matte_pixels,
                         "subtle_fringe_rgb_pixels_corrected": subtle_fringe_pixels,
                         "source_crop": [left, top, right, bottom], "uniform_scale": factor,
                         "dimensions": list(final.size), "visible_alpha_bounds": final.getchannel("A").getbbox()}
        print(stage, report[stage]["visible_alpha_bounds"], flush=True)
    (version / "generation-record.json").write_text(json.dumps(records, indent=2) + "\n")
    (run / "export-report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
