from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "artwork_source" / "backgrounds" / "bedless_v6"
RUNTIME_ROOT = (
    ROOT
    / "ankigarden"
    / "assets"
    / "v6_storybook_gouache"
    / "backgrounds"
)
REVIEW_ROOT = ROOT / "build" / "planter-background-cleanup"

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
VARIANTS = {
    "4x3": (1280, 960),
    "16x9": (1672, 941),
    "home": (1942, 809),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_source(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if image.size != expected_size:
        image = ImageOps.fit(
            image,
            expected_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        image.save(path, "PNG", optimize=True)
    return image


def _runtime_path(scene: str, variant: str) -> Path:
    return RUNTIME_ROOT / scene / "soil_master" / f"{scene}_{variant}.webp"


def _build_review_sheet(
    variant: str,
    images: list[tuple[str, Image.Image]],
) -> Path:
    cell_width = 720
    label_height = 44
    target_height = round(cell_width * VARIANTS[variant][1] / VARIANTS[variant][0])
    columns = 3
    rows = 3
    canvas = Image.new(
        "RGB",
        (cell_width * columns, (target_height + label_height) * rows),
        (14, 28, 25),
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, (scene, image) in enumerate(images):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * (target_height + label_height)
        thumbnail = image.resize((cell_width, target_height), Image.Resampling.LANCZOS)
        canvas.paste(thumbnail, (left, top))
        draw.rectangle(
            (left, top + target_height, left + cell_width, top + target_height + label_height),
            fill=(14, 28, 25),
        )
        draw.text(
            (left + 16, top + target_height + 15),
            f"{scene.replace('_', ' ').title()} - {variant}",
            font=font,
            fill=(236, 244, 232),
        )
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    path = REVIEW_ROOT / f"bedless-backgrounds-{variant}-review.png"
    canvas.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    records: list[dict[str, object]] = []
    review_images: dict[str, list[tuple[str, Image.Image]]] = {
        variant: [] for variant in VARIANTS
    }
    for scene in SCENES:
        for variant, expected_size in VARIANTS.items():
            source = SOURCE_ROOT / scene / f"{scene}_{variant}.png"
            if not source.is_file():
                raise RuntimeError(f"Missing approved bedless source: {source}")
            image = _normalize_source(source, expected_size)
            if image.size != expected_size:
                raise RuntimeError(
                    f"Bedless source has wrong dimensions: {source} {image.size}"
                )
            runtime = _runtime_path(scene, variant)
            runtime.parent.mkdir(parents=True, exist_ok=True)
            image.save(
                runtime,
                "WEBP",
                lossless=True,
                quality=100,
                method=6,
                exact=False,
            )
            installed = Image.open(runtime)
            if installed.size != expected_size:
                raise RuntimeError(
                    f"Installed background has wrong dimensions: {runtime} {installed.size}"
                )
            review_images[variant].append((scene, image.copy()))
            records.append(
                {
                    "scene": scene,
                    "variant": variant,
                    "dimensions": list(expected_size),
                    "source": source.relative_to(ROOT).as_posix(),
                    "source_sha256": _sha256(source),
                    "runtime": runtime.relative_to(ROOT).as_posix(),
                    "runtime_sha256": _sha256(runtime),
                }
            )

    review_sheets = [
        _build_review_sheet(variant, review_images[variant]).relative_to(ROOT).as_posix()
        for variant in VARIANTS
    ]
    report = {
        "contract": "bedless_v1",
        "scene_count": len(SCENES),
        "variant_count": len(VARIANTS),
        "asset_count": len(records),
        "review_sheets": review_sheets,
        "assets": records,
    }
    report_path = SOURCE_ROOT / "bedless-backgrounds.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)
    for review in review_sheets:
        print(ROOT / review)


if __name__ == "__main__":
    main()
