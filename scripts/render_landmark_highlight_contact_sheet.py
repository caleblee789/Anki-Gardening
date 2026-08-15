from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.asset_manager import AssetManager
from ankigarden.environment import SCENERY_CATALOG
from ankigarden.ui.landmarks import (
    project_landmark_outline_paths,
    resolve_scene_landmarks,
)


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "build" / "landmark-highlight-review"

SCENERIES = (
    ("default", "bg_verdant_twilight_any_soil_master_v6"),
    ("spring", "bg_spring_any_soil_master_v6"),
    ("summer", "bg_summer_any_soil_master_v6"),
    ("autumn", "bg_autumn_any_soil_master_v6"),
    ("snowy", "bg_snowy_any_soil_master_v6"),
    ("rainbow_horizon", "bg_rainbow_horizon_any_soil_master_v6"),
    ("halloween", "bg_halloween_any_soil_master_v6"),
    ("full_moon", "bg_full_moon_any_soil_master_v6"),
    ("eclipse", "bg_eclipse_any_soil_master_v6"),
)

VARIANTS = (
    ("4:3", "4:3"),
    ("16:9", "16:9"),
)

CANVAS_COLOR = (9, 28, 25)
CARD_COLOR = (18, 42, 37)
CAPTION_COLOR = (14, 35, 31)
TEXT_COLOR = (241, 244, 232)
MUTED_TEXT_COLOR = (174, 196, 183)
DIVIDER_COLOR = (66, 98, 87)
HOVER_COLOR = (244, 213, 138, 235)
HOVER_BORDER = (244, 213, 138)


def _contour_label(scenery_id: str, variant: str) -> str:
    if scenery_id == "autumn":
        return "Measured scenery contour"
    return "Asset-verified contour"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


TITLE_FONT = _font(48, bold=True)
SUBTITLE_FONT = _font(24)
CELL_TITLE_FONT = _font(27, bold=True)
CELL_META_FONT = _font(20)
MATRIX_ROW_FONT = _font(22, bold=True)
MATRIX_META_FONT = _font(17)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fit_box_to_aspect(
    box: tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
    target_aspect: float,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    width = max(1.0, right - left)
    height = max(1.0, bottom - top)
    current_aspect = width / height
    if current_aspect < target_aspect:
        expanded = height * target_aspect
        left -= (expanded - width) / 2
        right += (expanded - width) / 2
    elif current_aspect > target_aspect:
        expanded = width / target_aspect
        top -= (expanded - height) / 2
        bottom += (expanded - height) / 2

    width = right - left
    height = bottom - top
    if left < 0:
        right -= left
        left = 0
    if right > image_width:
        left -= right - image_width
        right = image_width
    if top < 0:
        bottom -= top
        top = 0
    if bottom > image_height:
        top -= bottom - image_height
        bottom = image_height
    left = max(0.0, left)
    top = max(0.0, top)
    right = min(float(image_width), max(left + width, right))
    bottom = min(float(image_height), max(top + height, bottom))
    return (
        int(round(left)),
        int(round(top)),
        int(round(right)),
        int(round(bottom)),
    )


def _rounded_line(
    overlay: Image.Image,
    points: list[tuple[float, float]],
    *,
    width: int,
) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(overlay)
    draw.line(points, fill=HOVER_COLOR, width=width, joint="curve")
    radius = width / 2
    for x, y in points:
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=HOVER_COLOR,
        )


def _render_house_crop(
    *,
    image: Image.Image,
    landmark: Any,
    variant: dict[str, Any],
    target_size: tuple[int, int],
) -> tuple[Image.Image, dict[str, Any]]:
    width, height = image.size
    source_aspect = float(variant["width"]) / float(variant["height"])
    focal_raw = variant.get("focal_point", [0.5, 0.5])
    focal = (float(focal_raw[0]), float(focal_raw[1]))
    paths = project_landmark_outline_paths(
        landmark,
        width=width,
        height=height,
        source_aspect=source_aspect,
        focal=focal,
    )
    if len(paths) != 3 or any(len(path) < 2 for path in paths):
        raise RuntimeError("Garden Progress house does not expose three visible-edge paths")

    xs = [x for path in paths for x, _y in path]
    ys = [y for path in paths for _x, y in path]
    hit_left, hit_top, hit_width, hit_height = landmark.bounds
    hit_right = (hit_left + hit_width) * width
    hit_bottom = (hit_top + hit_height) * height
    visible_box = (
        min(xs) - width * 0.045,
        min(ys) - height * 0.035,
        max(max(xs), hit_right) + width * 0.035,
        max(max(ys), hit_bottom) + height * 0.06,
    )
    crop_box = _fit_box_to_aspect(
        visible_box,
        image_width=width,
        image_height=height,
        target_aspect=target_size[0] / target_size[1],
    )
    left, top, right, bottom = crop_box
    crop = image.crop(crop_box).convert("RGBA").resize(
        target_size,
        Image.Resampling.LANCZOS,
    )
    scale_x = target_size[0] / max(1, right - left)
    scale_y = target_size[1] / max(1, bottom - top)
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
    rendered_paths: list[list[list[float]]] = []
    for path in paths:
        rendered = [
            ((x - left) * scale_x, (y - top) * scale_y)
            for x, y in path
        ]
        _rounded_line(overlay, rendered, width=6)
        rendered_paths.append([[round(x, 2), round(y, 2)] for x, y in rendered])
    crop.alpha_composite(overlay)
    return crop.convert("RGB"), {
        "source_dimensions": [width, height],
        "crop_box": list(crop_box),
        "outline_path_lengths": [len(path) for path in paths],
        "rendered_paths": rendered_paths,
    }


def _draw_header(
    sheet: Image.Image,
    *,
    title: str,
    subtitle: str,
    height: int,
) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.text((60, 38), title, font=TITLE_FONT, fill=TEXT_COLOR)
    draw.text((62, 104), subtitle, font=SUBTITLE_FONT, fill=MUTED_TEXT_COLOR)
    draw.line((60, height - 18, sheet.width - 60, height - 18), fill=DIVIDER_COLOR, width=2)


def _build_summary(
    records: list[dict[str, Any]],
    output: Path,
) -> None:
    width = 3000
    header_height = 180
    margin = 54
    gap = 30
    cell_width = (width - 2 * margin - 2 * gap) // 3
    image_height = round(cell_width * 550 / 980)
    caption_height = 74
    cell_height = image_height + caption_height
    sheet_height = header_height + margin + cell_height * 3 + gap * 2 + margin
    sheet = Image.new("RGB", (width, sheet_height), CANVAS_COLOR)
    _draw_header(
        sheet,
        title="Garden Progress House Hover Highlight",
        subtitle="All nine Sceneries • highlight-enabled 16:9 Full Garden artwork • foliage-aware visible edges",
        height=header_height,
    )
    draw = ImageDraw.Draw(sheet)
    summary_records = [record for record in records if record["variant"] == "16:9"]
    for index, record in enumerate(summary_records):
        column = index % 3
        row = index // 3
        left = margin + column * (cell_width + gap)
        top = header_height + margin + row * (cell_height + gap)
        draw.rounded_rectangle(
            (left, top, left + cell_width, top + cell_height),
            radius=18,
            fill=CARD_COLOR,
            outline=DIVIDER_COLOR,
            width=2,
        )
        rendered = Image.open(record["render_path"]).convert("RGB").resize(
            (cell_width, image_height), Image.Resampling.LANCZOS
        )
        sheet.paste(rendered, (left, top))
        draw.rectangle(
            (left, top + image_height, left + cell_width, top + cell_height),
            fill=CAPTION_COLOR,
        )
        draw.text(
            (left + 24, top + image_height + 18),
            record["scenery_name"],
            font=CELL_TITLE_FONT,
            fill=TEXT_COLOR,
        )
        meta = _contour_label(record["scenery_id"], record["variant"])
        meta_width = draw.textlength(meta, font=CELL_META_FONT)
        draw.text(
            (left + cell_width - meta_width - 24, top + image_height + 23),
            meta,
            font=CELL_META_FONT,
            fill=HOVER_BORDER,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)


def _build_responsive_matrix(
    records: list[dict[str, Any]],
    output: Path,
) -> None:
    width = 2400
    header_height = 235
    margin = 44
    label_width = 260
    gap = 24
    cell_width = (
        width - margin * 2 - label_width - gap * len(VARIANTS)
    ) // len(VARIANTS)
    image_height = round(cell_width * 550 / 980)
    row_gap = 18
    row_height = image_height + row_gap
    sheet_height = header_height + row_height * 9 + margin
    sheet = Image.new("RGB", (width, sheet_height), CANVAS_COLOR)
    _draw_header(
        sheet,
        title="House Highlight Enabled-Surface Matrix",
        subtitle="Each row resolves its own Scenery asset; columns verify the highlight-enabled 4:3 and 16:9 Garden surfaces",
        height=180,
    )
    draw = ImageDraw.Draw(sheet)
    columns_left = margin + label_width + gap
    for column, (_variant, label) in enumerate(VARIANTS):
        left = columns_left + column * (cell_width + gap)
        draw.text(
            (left + 12, 188),
            label,
            font=CELL_TITLE_FONT,
            fill=HOVER_BORDER,
        )
    by_key = {
        (record["scenery_id"], record["variant"]): record
        for record in records
    }
    for row_index, (scenery_id, _asset_id) in enumerate(SCENERIES):
        top = header_height + row_index * row_height
        name = SCENERY_CATALOG[scenery_id].name
        label_top = top + image_height // 2 - 34
        draw.text((margin, label_top), name, font=MATRIX_ROW_FONT, fill=TEXT_COLOR)
        contour = "Measured overrides" if scenery_id == "autumn" else "Asset-verified geometry"
        draw.text(
            (margin, label_top + 36),
            contour,
            font=MATRIX_META_FONT,
            fill=HOVER_BORDER if scenery_id == "autumn" else MUTED_TEXT_COLOR,
        )
        for column, (variant_name, _label) in enumerate(VARIANTS):
            record = by_key[(scenery_id, variant_name)]
            left = columns_left + column * (cell_width + gap)
            draw.rounded_rectangle(
                (left, top, left + cell_width, top + image_height),
                radius=14,
                fill=CARD_COLOR,
                outline=DIVIDER_COLOR,
                width=2,
            )
            rendered = Image.open(record["render_path"]).convert("RGB").resize(
                (cell_width, image_height), Image.Resampling.LANCZOS
            )
            sheet.paste(rendered, (left, top))
        draw.line(
            (margin, top + image_height + row_gap // 2, width - margin, top + image_height + row_gap // 2),
            fill=DIVIDER_COLOR,
            width=1,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)


def render(output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = {
        str(row.get("asset_id", "")): row
        for row in manifest.get("assets", [])
        if isinstance(row, dict) and row.get("category") == "backgrounds"
    }
    manager = object.__new__(AssetManager)
    manager._catalog_by_asset_id = {
        ("backgrounds", asset_id): row for asset_id, row in rows.items()
    }

    rendered_root = output_dir / "cells"
    rendered_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    canonical_geometry: dict[str, Any] = {}
    for scenery_id, asset_id in SCENERIES:
        row = rows.get(asset_id)
        if row is None:
            raise RuntimeError(f"Missing background manifest row: {asset_id}")
        placement = manager._placement_for_entry(row, "backgrounds")
        surface_profile = placement.get("surface_profile", {})
        variants = surface_profile.get("variants", {}) if isinstance(surface_profile, dict) else {}
        for variant_name, variant_label in VARIANTS:
            variant = variants.get(variant_name)
            if not isinstance(variant, dict):
                raise RuntimeError(f"Missing {variant_name} surface variant for {asset_id}")
            source_path = ADDON / str(variant.get("file", ""))
            if not source_path.is_file():
                raise RuntimeError(f"Missing scenery source: {source_path}")
            image = Image.open(source_path).convert("RGB")
            expected = (int(variant["width"]), int(variant["height"]))
            if image.size != expected:
                raise RuntimeError(
                    f"Scenery dimensions drifted: {scenery_id}/{variant_name} {image.size} != {expected}"
                )
            landmarks = resolve_scene_landmarks(
                placement,
                width=image.width,
                height=image.height,
                interactive=True,
            )
            house = next(
                (landmark for landmark in landmarks if landmark.landmark_id == "garden_house"),
                None,
            )
            if house is None:
                raise RuntimeError(f"Missing Garden Progress landmark: {scenery_id}/{variant_name}")
            crop, geometry = _render_house_crop(
                image=image,
                landmark=house,
                variant=variant,
                target_size=(980, 550),
            )
            render_path = rendered_root / f"{scenery_id}-{variant_name.replace(':', 'x')}.png"
            crop.save(render_path, "PNG", optimize=True)
            outline_geometry = [
                [[round(x, 6), round(y, 6)] for x, y in path]
                for path in house.outline_paths
            ]
            if scenery_id == "default":
                canonical_geometry[variant_name] = outline_geometry
            elif scenery_id == "autumn":
                if outline_geometry == canonical_geometry.get(variant_name):
                    raise RuntimeError(
                        f"Scenery contour override did not resolve: {scenery_id}/{variant_name}"
                    )
            elif outline_geometry != canonical_geometry.get(variant_name):
                raise RuntimeError(
                    f"Unexpected landmark geometry drift: {scenery_id}/{variant_name}"
                )
            records.append({
                "scenery_id": scenery_id,
                "scenery_name": SCENERY_CATALOG[scenery_id].name,
                "asset_id": asset_id,
                "variant": variant_name,
                "variant_label": variant_label,
                "source": source_path.relative_to(ROOT).as_posix(),
                "render_path": str(render_path),
                "outline_geometry": outline_geometry,
                **geometry,
            })

    summary = output_dir / "house-highlight-all-sceneries-16x9.png"
    matrix = output_dir / "house-highlight-all-sceneries-responsive.png"
    _build_summary(records, summary)
    _build_responsive_matrix(records, matrix)
    report_path = output_dir / "house-highlight-contact-sheet-report.json"
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "contract": "manifest-resolved-interactive-landmark-highlight-review-v1",
        "native_anki_capture": False,
        "excluded_surface_variants": ["home (non-interactive preview)"],
        "scenery_count": len(SCENERIES),
        "variant_count": len(VARIANTS),
        "cell_count": len(records),
        "summary_contact_sheet": str(summary),
        "responsive_contact_sheet": str(matrix),
        "summary_dimensions": list(Image.open(summary).size),
        "responsive_dimensions": list(Image.open(matrix).size),
        "summary_sha256": _sha256(summary),
        "responsive_sha256": _sha256(matrix),
        "records": records,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {**report, "report": str(report_path)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render manifest-resolved Garden Progress highlights for every Scenery."
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        DEFAULT_OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    report = render(output_dir.resolve())
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "generated_at",
                    "contract",
                    "native_anki_capture",
                    "excluded_surface_variants",
                    "scenery_count",
                    "variant_count",
                    "cell_count",
                    "summary_contact_sheet",
                    "responsive_contact_sheet",
                    "summary_dimensions",
                    "responsive_dimensions",
                    "summary_sha256",
                    "responsive_sha256",
                    "report",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
