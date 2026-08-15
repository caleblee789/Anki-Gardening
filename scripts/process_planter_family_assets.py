from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "artwork_source" / "planters" / "stone_family_v1"
OUTPUT_DIR = (
    ROOT
    / "ankigarden"
    / "assets"
    / "v6_storybook_gouache"
    / "planters"
    / "stone_family_v1"
)
CANVAS_SIZE = (1024, 512)
VISIBLE_WIDTH = 900
SOIL_ANCHOR = (512, 220)
VARIANTS = ("back", "middle", "front")

# The source soil center is measured within the alpha-bounded illustration.
# Normalizing that point onto one shared canvas lets the runtime align planter
# art to a fixed slot anchor without consulting the image's natural bounds.
SOIL_CENTER_Y_RATIOS = {
    "back": 0.46,
    "middle": 0.39,
    "front": 0.39,
}
FOREGROUND_START_Y = {
    "back": 235,
    "middle": 250,
    "front": 250,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize(source_path: Path, output_path: Path, variant: str) -> dict[str, object]:
    source = Image.open(source_path).convert("RGBA")
    alpha = source.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise RuntimeError(f"Planter source has no visible pixels: {source_path}")
    if any(alpha.getpixel(point) for point in ((0, 0), (source.width - 1, 0), (0, source.height - 1), (source.width - 1, source.height - 1))):
        raise RuntimeError(f"Planter source corners must be transparent: {source_path}")

    cropped = source.crop(bounds)
    scale = VISIBLE_WIDTH / max(1, cropped.width)
    target_height = max(1, round(cropped.height * scale))
    resized = cropped.resize((VISIBLE_WIDTH, target_height), Image.Resampling.LANCZOS)
    left = SOIL_ANCHOR[0] - VISIBLE_WIDTH // 2
    top = round(SOIL_ANCHOR[1] - target_height * SOIL_CENTER_Y_RATIOS[variant])
    if left < 0 or top < 0 or left + VISIBLE_WIDTH > CANVAS_SIZE[0] or top + target_height > CANVAS_SIZE[1]:
        raise RuntimeError(f"Normalized {variant} planter does not fit the shared canvas")

    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(resized, (left, top))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output_path,
        "WEBP",
        lossless=True,
        quality=100,
        method=6,
        exact=True,
    )
    foreground = canvas.copy()
    foreground_alpha = foreground.getchannel("A")
    foreground_alpha.paste(0, (0, 0, CANVAS_SIZE[0], FOREGROUND_START_Y[variant]))
    foreground.putalpha(foreground_alpha)
    foreground_path = output_path.with_name(f"{output_path.stem}_foreground.webp")
    foreground.save(
        foreground_path,
        "WEBP",
        lossless=True,
        quality=100,
        method=6,
        exact=True,
    )
    final_alpha = canvas.getchannel("A")
    return {
        "variant": variant,
        "source": source_path.relative_to(ROOT).as_posix(),
        "source_sha256": _sha256(source_path),
        "file": output_path.relative_to(ROOT / "ankigarden").as_posix(),
        "sha256": _sha256(output_path),
        "foreground_file": foreground_path.relative_to(ROOT / "ankigarden").as_posix(),
        "foreground_sha256": _sha256(foreground_path),
        "canvas": list(CANVAS_SIZE),
        "soil_anchor": [
            SOIL_ANCHOR[0] / CANVAS_SIZE[0],
            SOIL_ANCHOR[1] / CANVAS_SIZE[1],
        ],
        "visible_bounds": list(final_alpha.getbbox() or (0, 0, 0, 0)),
    }


def main() -> None:
    records = []
    for variant in VARIANTS:
        source = SOURCE_DIR / f"stone_planter_{variant}_alpha.png"
        if not source.is_file():
            raise RuntimeError(f"Missing chroma-removed planter source: {source}")
        output = OUTPUT_DIR / f"stone_planter_{variant}.webp"
        records.append(_normalize(source, output, variant))
    report = {
        "family_id": "storybook_stone_planter_v1",
        "canvas": list(CANVAS_SIZE),
        "soil_anchor": [
            SOIL_ANCHOR[0] / CANVAS_SIZE[0],
            SOIL_ANCHOR[1] / CANVAS_SIZE[1],
        ],
        "variants": records,
    }
    report_path = SOURCE_DIR / "planter-family.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
