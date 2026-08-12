#!/usr/bin/env python3
"""Finish generated catalog art with deterministic labels and transparent framing."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LABEL_SPECS = {
    "basic": {
        "lines": ("Basic", "FERTILIZER"),
        "box": (0.29, 0.43, 0.72, 0.73),
        "color": "#49351f",
    },
    "quality": {
        "lines": ("Quality", "FERTILIZER"),
        "box": (0.29, 0.48, 0.73, 0.76),
        "color": "#24433c",
    },
    "premium": {
        "lines": ("Magical", "FERTILIZER"),
        "box": (0.30, 0.46, 0.72, 0.73),
        "color": "#4b2a53",
    },
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    maximum_size: int,
    color: str,
) -> None:
    left, top, right, bottom = box
    available_width = right - left
    available_height = bottom - top
    font = _font(maximum_size)
    while maximum_size > 18:
        bounds = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        if bounds[2] - bounds[0] <= available_width and bounds[3] - bounds[1] <= available_height:
            break
        maximum_size -= 2
        font = _font(maximum_size)
    bounds = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        (left + (available_width - width) / 2, top + (available_height - height) / 2 - bounds[1]),
        text,
        font=font,
        fill=color,
        stroke_width=1,
        stroke_fill="#f4dfad",
    )


def _label_bag(image: Image.Image, key: str) -> Image.Image:
    spec = LABEL_SPECS[key]
    draw = ImageDraw.Draw(image)
    width, height = image.size
    left, top, right, bottom = (
        round(value * (width if index % 2 == 0 else height))
        for index, value in enumerate(spec["box"])
    )
    middle = round(top + (bottom - top) * 0.53)
    _centered_text(
        draw,
        spec["lines"][0],
        (left, top, right, middle),
        maximum_size=86,
        color=spec["color"],
    )
    _centered_text(
        draw,
        spec["lines"][1],
        (left, middle, right, bottom),
        maximum_size=48,
        color=spec["color"],
    )
    return image


def _frame(image: Image.Image, *, size: int = 512) -> Image.Image:
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("Generated artwork has no visible pixels")
    left, top, right, bottom = bounds
    padding = round(max(right - left, bottom - top) * 0.04)
    crop = image.crop((
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    ))
    crop.thumbnail((size - 24, size - 24), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((size - crop.width) // 2, (size - crop.height) // 2))
    return canvas


def render(source: Path, destination: Path, *, label_key: str | None = None) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    if label_key is not None:
        image = _label_bag(image, label_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _frame(image).save(
        destination,
        format="WEBP",
        lossless=True,
        quality=100,
        method=6,
        exact=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basic", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--magical", type=Path, required=True)
    parser.add_argument("--booster", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    render(args.basic, args.output_dir / "fertilizer_basic.webp", label_key="basic")
    render(args.quality, args.output_dir / "fertilizer_quality.webp", label_key="quality")
    render(args.magical, args.output_dir / "fertilizer_premium.webp", label_key="premium")
    render(args.booster, args.output_dir / "booster_potion.webp")


if __name__ == "__main__":
    main()
