from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "artwork_source" / "plants" / "v6"
DEFAULT_HELPER = (
    Path.home()
    / ".codex"
    / "skills"
    / ".system"
    / "imagegen"
    / "scripts"
    / "remove_chroma_key.py"
)
SPECIES = (
    "rose",
    "bonsai",
    "sunflower",
    "lavender",
    "hydrangea",
    "peony",
    "foxglove",
    "japanese_maple",
    "wisteria",
    "dahlia",
)
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
KEY = (255, 0, 255)


def _sources() -> list[Path]:
    return [
        SOURCE_ROOT / species / f"{species}_{stage}_chroma.png"
        for species in SPECIES
        for stage in STAGES
    ]


def _verify(path: Path) -> float:
    with Image.open(path) as source:
        rgb = source.convert("RGB")
    width, height = rgb.size
    border = (
        [rgb.getpixel((x, 0)) for x in range(width)]
        + [rgb.getpixel((x, height - 1)) for x in range(width)]
        + [rgb.getpixel((0, y)) for y in range(height)]
        + [rgb.getpixel((width - 1, y)) for y in range(height)]
    )
    if set(border) != {KEY}:
        raise RuntimeError(f"non-uniform chroma border: {path}")
    exact = sum(count for count, color in rgb.getcolors(width * height) or [] if color == KEY)
    ratio = exact / (width * height)
    if ratio < 0.45:
        raise RuntimeError(f"exact chroma coverage too small ({ratio:.3f}): {path}")
    return ratio


def _normalize(path: Path, mask_path: Path, helper: Path) -> tuple[Path, float]:
    subprocess.run(
        [
            sys.executable,
            str(helper),
            "--input",
            str(path),
            "--out",
            str(mask_path),
            "--auto-key",
            "border",
            "--soft-matte",
            "--transparent-threshold",
            "12",
            "--opaque-threshold",
            "220",
            "--force",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with Image.open(path) as source, Image.open(mask_path) as keyed:
        rgb = source.convert("RGB")
        alpha = keyed.convert("RGBA").getchannel("A")
    background = alpha.point(lambda value: 255 if value == 0 else 0)
    normalized = Image.composite(Image.new("RGB", rgb.size, KEY), rgb, background)
    pixels = normalized.load()
    for x in range(normalized.width):
        pixels[x, 0] = KEY
        pixels[x, normalized.height - 1] = KEY
    for y in range(normalized.height):
        pixels[0, y] = KEY
        pixels[normalized.width - 1, y] = KEY
    temporary = path.with_name(f".{path.name}.normalized.tmp.png")
    normalized.save(temporary, "PNG", optimize=True)
    temporary.replace(path)
    return path, _verify(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canonicalize the 60 approved V6 source backgrounds to exact #FF00FF."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--helper", type=Path, default=DEFAULT_HELPER)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    sources = _sources()
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("Missing canonical sources: " + ", ".join(map(str, missing)))

    if args.check:
        ratios = [_verify(path) for path in sources]
    else:
        if not args.helper.is_file():
            raise SystemExit(f"ImageGen chroma helper not found: {args.helper}")
        with tempfile.TemporaryDirectory(prefix="twilight-v6-chroma-") as temp:
            mask_root = Path(temp)
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                results = list(
                    pool.map(
                        lambda item: _normalize(item[1], mask_root / f"mask-{item[0]}.png", args.helper),
                        enumerate(sources),
                    )
                )
        ratios = [ratio for _path, ratio in results]

    print(
        f"Verified {len(sources)} V6 chroma masters: exact #FF00FF coverage "
        f"{min(ratios):.1%}..{max(ratios):.1%}."
    )


if __name__ == "__main__":
    main()
