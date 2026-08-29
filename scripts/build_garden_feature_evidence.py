#!/usr/bin/env python3
"""Build the static two-layout Garden Decoration visual review lane."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "ankigarden/assets/v6_storybook_gouache"
FEATURE_ROOT = ASSET_ROOT / "garden_features"
THEMES = (
    "verdant_twilight", "spring", "summer", "autumn", "snowy",
    "rainbow_horizon", "halloween", "full_moon", "eclipse",
)
FEATURES = (
    "seedling_sign", "wind_chime", "harvest_bell", "watering_station",
    "herbalist_hourglass", "firefly_lantern", "prism_trellis",
)
STATES = (*FEATURES, "hidden")
LAYOUTS = {
    "home": (960, 400),
    "native_3_2": (1260, 840),
}
LIGHT_THEMES = {"spring", "summer", "autumn", "snowy", "rainbow_horizon"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def background(theme: str, layout: str, size: tuple[int, int]) -> Image.Image:
    source_name = "home" if layout == "home" else "4x3"
    source = Image.open(
        ASSET_ROOT / "backgrounds" / theme / "soil_master"
        / f"{theme}_{source_name}.webp"
    ).convert("RGB")
    width, height = size
    if layout == "home":
        return source.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    scale = max(width / source.width, height / source.height)
    draw_size = (round(source.width * scale), round(source.height * scale))
    resized = source.resize(draw_size, Image.Resampling.LANCZOS)
    left = round((draw_size[0] - width) * 0.50)
    top = round((draw_size[1] - height) * 0.48)
    return resized.crop((left, top, left + width, top + height)).convert("RGBA")


def paste_contain(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, width, height = box
    scale = min(width / source.width, height / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas.alpha_composite(
        resized,
        (left + (width - resized.width) // 2, top + (height - resized.height) // 2),
    )


def feature_boxes(width: int, height: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    size = height * 0.25
    feature = (
        round(width * 0.215 - size * 0.500),
        round(height * 0.830 - size * 0.880),
        round(size),
        round(size),
    )
    pad_width = height * 0.28
    pad_height = height * 0.07
    pad = (
        round(width * 0.215 - pad_width * 0.5),
        round(height * 0.842 - pad_height * 0.5),
        round(pad_width),
        round(pad_height),
    )
    return feature, pad


def add_local_shadow(
    canvas: Image.Image,
    feature: Image.Image,
    box: tuple[int, int, int, int],
    *,
    dark: bool,
) -> None:
    left, top, width, height = box
    resized = feature.resize((width, height), Image.Resampling.LANCZOS)
    alpha = resized.getchannel("A").filter(
        ImageFilter.GaussianBlur(max(1.0, height * 0.018))
    )
    opacity = 110 if dark else 66
    alpha = alpha.point(lambda value: value * opacity // 255)
    shadow = Image.new("RGBA", resized.size, (4, 9, 8, 0))
    shadow.putalpha(alpha)
    canvas.alpha_composite(shadow, (left, top + round(height * 0.028)))


def render(theme: str, layout: str, state: str) -> Image.Image:
    width, height = LAYOUTS[layout]
    result = background(theme, layout, (width, height))
    if state == "hidden":
        return result
    feature_box, pad_box = feature_boxes(width, height)
    pad = Image.open(FEATURE_ROOT / "feature_pad.webp").convert("RGBA")
    feature = Image.open(FEATURE_ROOT / f"{state}.webp").convert("RGBA")
    paste_contain(result, pad, pad_box)
    add_local_shadow(result, feature, feature_box, dark=theme not in LIGHT_THEMES)
    paste_contain(result, feature, feature_box)
    return result


def contact_sheet(
    theme: str,
    layout: str,
    frames: list[tuple[str, Path]],
    destination: Path,
) -> None:
    source_width, source_height = LAYOUTS[layout]
    tile_width = 630 if layout == "native_3_2" else 480
    tile_height = round(source_height * tile_width / source_width)
    header = 48
    sheet = Image.new("RGB", (tile_width * len(frames), tile_height + header), "#101916")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (state, path) in enumerate(frames):
        image = Image.open(path).convert("RGB").resize(
            (tile_width, tile_height), Image.Resampling.LANCZOS
        )
        x = index * tile_width
        sheet.paste(image, (x, header))
        label = f"{theme.replace('_', ' ').title()} · {layout} · {state.replace('_', ' ').title()}"
        draw.text((x + 12, 16), label, fill="#eef5e8", font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, "PNG", optimize=True)


def build(output: Path) -> dict:
    frames_dir = output / "frames"
    sheets_dir = output / "contact_sheets"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for layout, (width, height) in LAYOUTS.items():
        for theme in THEMES:
            row: list[tuple[str, Path]] = []
            for state in STATES:
                path = frames_dir / f"{layout}__{theme}__{state}.png"
                render(theme, layout, state).save(path, "PNG", optimize=True)
                row.append((state, path))
                feature_box, pad_box = feature_boxes(width, height)
                records.append({
                    "layout": layout,
                    "theme": theme,
                    "feature": state,
                    "visible": state != "hidden",
                    "dimensions": [width, height],
                    "placement_profile": "home" if layout == "home" else "3:2",
                    "artwork_variant": "home" if layout == "home" else "4:3",
                    "background_position": "dedicated-home" if layout == "home" else "50% 48%",
                    "feature_box": list(feature_box),
                    "pad_box": list(pad_box),
                    "png": str(path.relative_to(output)),
                    "png_sha256": sha256(path),
                })
            contact_sheet(
                theme,
                layout,
                row,
                sheets_dir / f"{layout}__{theme}.png",
            )
    manifest = {
        "schema": "garden-feature-evidence-v1",
        "quality_status": "review-required",
        "release_ready": False,
        "visible_combinations": 9 * 2 * 7,
        "hidden_combinations": 9 * 2,
        "frame_count": len(records),
        "contact_sheet_count": len(THEMES) * len(LAYOUTS),
        "records": records,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = build(args.output.resolve())
    print(json.dumps({key: manifest[key] for key in (
        "frame_count", "visible_combinations", "hidden_combinations",
        "contact_sheet_count", "quality_status", "release_ready",
    )}, indent=2))


if __name__ == "__main__":
    main()
