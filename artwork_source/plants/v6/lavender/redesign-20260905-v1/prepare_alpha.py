"""Reproduce Lavender transparency cleanup using the existing repository helpers."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "ankigarden").is_dir())
EXTRACTOR = ROOT / "scripts/process_direct_soil_asset.py"
ALPHA_HELPER = Path("/Users/test/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py")
SOURCES = {
    "seed": ("seed-generated-v1.png", 24, 42),
    "sprout": ("sprout-generated-v1.png", 26, 44),
    "young": ("young-generated-v1.png", 24, 42),
    "mature": ("mature-generated-v3.png", 16, 34),
    "flowering": ("flowering-generated-v1.png", None, None),
    "rare": ("rare-generated-v1.png", 26, 44),
}
def main():
    records = {}
    for stage, (name, transparent, connected) in SOURCES.items():
        source = HERE / name
        output = HERE / f"lavender_{stage}_alpha.png"
        if transparent is None:
            # Hard matching of the unused pure-magenta key only; retain native
            # color/alpha except the helper's existing <=8 alpha-noise floor.
            args = [sys.executable, str(ALPHA_HELPER), "--input", str(source),
                    "--out", str(output), "--key-color", "#ff00ff",
                    "--tolerance", "0", "--force"]
        else:
            # The existing connected-chroma helper uses color distance without
            # channel-dominance despill, which would damage pale botanical art
            # against a neutral white source background.
            args = [sys.executable, str(EXTRACTOR), "--input", str(source),
                    "--out", str(output), "--transparent-threshold", str(transparent),
                    "--connection-threshold", str(connected)]
        subprocess.run(args, check=True)
        with Image.open(output) as im:
            rgba = im.convert("RGBA")
            if rgba.size != (1254, 1254):
                raise ValueError(f"Unexpected canvas for {stage}: {rgba.size}")
            alpha = rgba.getchannel("A")
            if alpha.getextrema() != (0, 255):
                raise ValueError(f"Invalid transparent silhouette for {stage}")
            records[stage] = {
                "source": name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "output": output.name, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "command": args, "alpha_bounds": alpha.getbbox(),
                "confident_bounds": alpha.point(lambda a: 255 if a >= 192 else 0).getbbox(),
                "alpha_histogram": {"clear": alpha.histogram()[0],
                                    "partial": sum(alpha.histogram()[1:255]),
                                    "opaque": alpha.histogram()[255]},
            }
    (HERE / "alpha-processing.json").write_text(json.dumps(records, indent=2) + "\n")
    print("Prepared six transparent Lavender masters", flush=True)
if __name__ == "__main__":
    main()
