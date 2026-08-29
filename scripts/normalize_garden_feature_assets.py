#!/usr/bin/env python3
"""Normalize generated Garden Feature art into the one runtime contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


FEATURE_SIZE = 1024
CONTACT_X = 0.500
CONTACT_Y = 0.880
MAX_ART_WIDTH = 720
MAX_ART_HEIGHT = 820
ALPHA_THRESHOLD = 20


def visible_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    alpha = image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("source contains no visible pixels")
    return bbox


def normalize_feature(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGBA")
    crop = image.crop(visible_bbox(image))
    scale = min(MAX_ART_WIDTH / crop.width, MAX_ART_HEIGHT / crop.height)
    size = (
        max(1, round(crop.width * scale)),
        max(1, round(crop.height * scale)),
    )
    crop = crop.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (FEATURE_SIZE, FEATURE_SIZE))
    contact_x = round(FEATURE_SIZE * CONTACT_X)
    contact_y = round(FEATURE_SIZE * CONTACT_Y)
    left = contact_x - crop.width // 2
    top = contact_y - crop.height
    canvas.alpha_composite(crop, (left, top))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "WEBP", lossless=True, method=6)


def normalize_pad(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGBA")
    crop = image.crop(visible_bbox(image))
    scale = min(960 / crop.width, 184 / crop.height)
    crop = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (1024, 256))
    canvas.alpha_composite(crop, ((1024 - crop.width) // 2, (256 - crop.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "WEBP", lossless=True, method=6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("destination_root", type=Path)
    args = parser.parse_args()
    for item_id in (
        "seedling_sign",
        "wind_chime",
        "harvest_bell",
        "watering_station",
        "herbalist_hourglass",
        "firefly_lantern",
        "prism_trellis",
    ):
        normalize_feature(
            args.source_root / f"{item_id}.png",
            args.destination_root / f"{item_id}.webp",
        )
    normalize_pad(
        args.source_root / "feature_pad.png",
        args.destination_root / "feature_pad.webp",
    )


if __name__ == "__main__":
    main()
