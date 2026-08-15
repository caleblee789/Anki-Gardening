from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "artwork_source" / "ui" / "nurtured_marker"
SOURCE = SOURCE_DIR / "watering_can_source.png"
MASTER = SOURCE_DIR / "nurtured_marker_master.png"
MIRRORED_MASTER = SOURCE_DIR / "nurtured_marker_spout_right_master.png"
REPORT = SOURCE_DIR / "nurtured-marker.json"
OUTPUT = (
    ROOT
    / "ankigarden"
    / "assets"
    / "v6_storybook_gouache"
    / "ui"
    / "nurtured_marker.webp"
)
MIRRORED_OUTPUT = (
    ROOT
    / "ankigarden"
    / "assets"
    / "v6_storybook_gouache"
    / "ui"
    / "nurtured_marker_spout_right.webp"
)
CANVAS_SIZE = (512, 512)
LABEL_TEXT = "Nurturing"
# Connected-component analysis of the source's light cream pixels identifies
# this inner painted field. Center against the actual blank space, not the
# wider gold trim and surrounding vines.
PANEL_BOUNDS_RATIO = (557 / 1254, 629 / 1254, 983 / 1254, 942 / 1254)
FONT_CANDIDATES = (
    (Path("/System/Library/Fonts/MarkerFelt.ttc"), 1),
    (Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"), 0),
    (Path("/System/Library/Fonts/Supplemental/ChalkboardSE.ttc"), 2),
    (Path("/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf"), 0),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font(
    size: int,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str]:
    for candidate, face_index in FONT_CANDIDATES:
        if candidate.is_file():
            font = ImageFont.truetype(str(candidate), size, index=face_index)
            family, style = font.getname()
            return font, f"{family} {style}".strip()
    try:
        return ImageFont.load_default(size=size), "Pillow default"
    except TypeError:
        return ImageFont.load_default(), "Pillow default"


def _paint_centered_label(
    source: Image.Image,
    panel_bounds_ratio: tuple[float, float, float, float] = PANEL_BOUNDS_RATIO,
) -> tuple[Image.Image, dict[str, object]]:
    """Paint one clear exact label centered in the can's cream front panel."""

    width, height = source.size
    font, font_name = _font(max(16, round(width * 96 / 1254)))
    stroke_width = max(2, round(width * 2 / 1254))
    panel_bounds = tuple(
        round(value * extent)
        for value, extent in zip(panel_bounds_ratio, (width, height, width, height))
    )
    panel_center = (
        (panel_bounds[0] + panel_bounds[2]) / 2,
        (panel_bounds[1] + panel_bounds[3]) / 2,
    )

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_bounds = probe.textbbox(
        (0, 0),
        LABEL_TEXT,
        font=font,
        stroke_width=stroke_width,
    )
    inset = max(8, round(width * 12 / 1254))
    text_width = text_bounds[2] - text_bounds[0]
    text_height = text_bounds[3] - text_bounds[1]
    tile = Image.new(
        "RGBA",
        (text_width + inset * 2, text_height + inset * 2),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(tile)
    origin = (inset - text_bounds[0], inset - text_bounds[1])
    # A very small inset shadow and warm highlight keep the stronger lettering
    # integrated with the painted metal instead of reading as a flat UI label.
    draw.text(
        (origin[0] + 2, origin[1] + 2),
        LABEL_TEXT,
        font=font,
        fill=(11, 47, 42, 105),
        stroke_width=stroke_width,
        stroke_fill=(11, 47, 42, 70),
    )
    draw.text(
        (origin[0] - 1, origin[1] - 1),
        LABEL_TEXT,
        font=font,
        fill=(255, 246, 207, 92),
    )
    draw.text(
        origin,
        LABEL_TEXT,
        font=font,
        fill=(22, 72, 62, 255),
        stroke_width=stroke_width,
        stroke_fill=(11, 48, 42, 230),
    )

    layer = Image.new("RGBA", source.size, (0, 0, 0, 0))
    tile_bounds = tile.getchannel("A").getbbox()
    if tile_bounds is None:
        raise RuntimeError("Nurturing label did not render")
    tile_center = (
        (tile_bounds[0] + tile_bounds[2]) / 2,
        (tile_bounds[1] + tile_bounds[3]) / 2,
    )
    layer.alpha_composite(
        tile,
        (
            round(panel_center[0] - tile_center[0]),
            round(panel_center[1] - tile_center[1]),
        ),
    )

    label_bounds = layer.getchannel("A").getbbox()
    if label_bounds is None:
        raise RuntimeError("Nurturing label did not render")
    label_center = (
        (label_bounds[0] + label_bounds[2]) / 2,
        (label_bounds[1] + label_bounds[3]) / 2,
    )
    target_center = panel_center
    centered_layer = Image.new("RGBA", source.size, (0, 0, 0, 0))
    centered_layer.alpha_composite(
        layer,
        (
            round(target_center[0] - label_center[0]),
            round(target_center[1] - label_center[1]),
        ),
    )

    panel_mask = Image.new("L", source.size, 0)
    mask_draw = ImageDraw.Draw(panel_mask)
    mask_draw.ellipse(panel_bounds, fill=255)
    transparent = Image.new("L", source.size, 0)
    centered_layer.putalpha(
        Image.composite(centered_layer.getchannel("A"), transparent, panel_mask)
    )
    result = source.copy()
    result.alpha_composite(centered_layer)
    final_bounds = centered_layer.getchannel("A").getbbox()
    if final_bounds is None:
        raise RuntimeError("Centered Nurturing label did not render")
    final_center = (
        (final_bounds[0] + final_bounds[2]) / 2,
        (final_bounds[1] + final_bounds[3]) / 2,
    )
    panel_width = panel_bounds[2] - panel_bounds[0]
    panel_height = panel_bounds[3] - panel_bounds[1]
    return result, {
        "font": font_name,
        "font_size": font.size if hasattr(font, "size") else None,
        "label_bounds": list(final_bounds),
        "label_center": [round(final_center[0], 3), round(final_center[1], 3)],
        "panel_bounds": list(panel_bounds),
        "panel_center": [
            round((panel_bounds[0] + panel_bounds[2]) / 2, 3),
            round((panel_bounds[1] + panel_bounds[3]) / 2, 3),
        ],
        "center_error_pixels": [
            round(final_center[0] - target_center[0], 3),
            round(final_center[1] - target_center[1], 3),
        ],
        "label_width_ratio": round((final_bounds[2] - final_bounds[0]) / panel_width, 4),
        "label_height_ratio": round((final_bounds[3] - final_bounds[1]) / panel_height, 4),
        "label_margins": {
            "left": final_bounds[0] - panel_bounds[0],
            "top": final_bounds[1] - panel_bounds[1],
            "right": panel_bounds[2] - final_bounds[2],
            "bottom": panel_bounds[3] - final_bounds[3],
        },
    }


def _render_variant(
    source: Image.Image,
    *,
    master_path: Path,
    output_path: Path,
    panel_bounds_ratio: tuple[float, float, float, float],
    asset_id: str,
    orientation: str,
) -> dict[str, object]:
    lettered, label_metrics = _paint_centered_label(source, panel_bounds_ratio)
    pad = max(32, round(source.width * 80 / 1254))
    master = Image.new(
        "RGBA",
        (source.width + pad * 2, source.height + pad * 2),
        (0, 0, 0, 0),
    )
    master.alpha_composite(lettered, (pad, pad - round(source.height * 18 / 1254)))
    master_path.parent.mkdir(parents=True, exist_ok=True)
    master.save(master_path, "PNG", optimize=True)

    runtime = master.resize(CANVAS_SIZE, Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.save(
        output_path,
        "WEBP",
        lossless=True,
        quality=100,
        method=6,
        exact=True,
    )
    spout_tip_x = 47 / 512 if orientation == "spout-left" else 465 / 512
    body_contact_x = 0.70 if orientation == "spout-left" else 0.30
    return {
        "asset_id": asset_id,
        "orientation": orientation,
        "label_text": LABEL_TEXT,
        "master": master_path.relative_to(ROOT).as_posix(),
        "master_sha256": _sha256(master_path),
        "file": output_path.relative_to(ROOT / "ankigarden").as_posix(),
        "sha256": _sha256(output_path),
        "canvas": list(CANVAS_SIZE),
        "alpha_bounds": list(runtime.getchannel("A").getbbox() or (0, 0, 0, 0)),
        "ground_contact": [body_contact_x, 469 / 512],
        "spout_tip": [spout_tip_x, 0.57],
        **label_metrics,
    }


def main() -> None:
    if not SOURCE.is_file():
        raise RuntimeError(f"Missing generated watering-can source: {SOURCE}")
    source = Image.open(SOURCE).convert("RGBA")
    alpha = source.getchannel("A")
    if alpha.getbbox() is None:
        raise RuntimeError("Generated watering-can source has no visible pixels")
    corners = (
        (0, 0),
        (source.width - 1, 0),
        (0, source.height - 1),
        (source.width - 1, source.height - 1),
    )
    if any(alpha.getpixel(point) for point in corners):
        raise RuntimeError("Generated watering-can source must have transparent corners")

    left = _render_variant(
        source,
        master_path=MASTER,
        output_path=OUTPUT,
        panel_bounds_ratio=PANEL_BOUNDS_RATIO,
        asset_id="ui_nurtured_marker",
        orientation="spout-left",
    )
    mirrored_ratio = (
        1.0 - PANEL_BOUNDS_RATIO[2],
        PANEL_BOUNDS_RATIO[1],
        1.0 - PANEL_BOUNDS_RATIO[0],
        PANEL_BOUNDS_RATIO[3],
    )
    right = _render_variant(
        ImageOps.mirror(source),
        master_path=MIRRORED_MASTER,
        output_path=MIRRORED_OUTPUT,
        panel_bounds_ratio=mirrored_ratio,
        asset_id="ui_nurtured_marker_spout_right",
        orientation="spout-right",
    )
    report = {
        **left,
        "label_target_center": [
            round((left["panel_bounds"][0] + left["panel_bounds"][2]) / (2 * source.width), 6),
            round((left["panel_bounds"][1] + left["panel_bounds"][3]) / (2 * source.height), 6),
        ],
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": _sha256(SOURCE),
        "variants": {
            "spout_left": left,
            "spout_right": right,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
