from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from build_release_placement_review import _font, render_scene


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
RUNTIME_ROOT = ADDON / "assets" / "v6_storybook_gouache" / "plants"
DEFAULT_OUTPUT = ROOT / "build" / "twilight-full-library-review"

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
LAYOUTS = (
    ("4:3 dashboard", 960, 720, "dashboard"),
    ("16:9 dashboard", 960, 540, "dashboard"),
    ("Home widget", 960, 400, "home"),
)


def _display_name(value: str) -> str:
    return value.replace("_", " ").title()


@dataclass(frozen=True)
class StageInventory:
    species: str
    stage: str
    asset: dict[str, Any] | None
    path: Path
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.asset is not None and self.path.is_file() and not self.issues


def _expected_file(species: str, stage: str) -> Path:
    return RUNTIME_ROOT / species / stage / f"{species}_{stage}_twilight_v6.png"


def inventory(rows: list[dict[str, Any]]) -> dict[str, dict[str, StageInventory]]:
    """Return exact V6 inventory without ever accepting a legacy fallback."""
    result: dict[str, dict[str, StageInventory]] = {}
    for species in SPECIES:
        stages: dict[str, StageInventory] = {}
        for stage in STAGES:
            asset_id = f"plant_{species}_{stage}_twilight_v6"
            matches = [row for row in rows if row.get("asset_id") == asset_id]
            expected = _expected_file(species, stage)
            issues: list[str] = []
            asset: dict[str, Any] | None = matches[0] if len(matches) == 1 else None
            if len(matches) > 1:
                issues.append(f"{len(matches)} manifest entries")
            elif not matches:
                issues.append("manifest entry missing")

            path = expected
            if asset is not None:
                declared = ADDON / str(asset.get("file", ""))
                path = declared
                if declared != expected:
                    issues.append("noncanonical runtime file")
                slot = asset.get("slot") or {}
                if slot.get("species") != species or slot.get("stage") != stage:
                    issues.append("stage mapping mismatch")
                if asset.get("release_preferred") is not True:
                    issues.append("not release preferred")
                if asset.get("alpha") is not True:
                    issues.append("alpha metadata false")
            if not path.is_file():
                if expected.is_file() and path != expected:
                    path = expected
                else:
                    issues.append("runtime file missing")
            stages[stage] = StageInventory(species, stage, asset, path, tuple(issues))
        result[species] = stages
    return result


def _line_ready(stages: dict[str, StageInventory]) -> bool:
    return all(stages[stage].ready for stage in STAGES)


def _line_issue(stages: dict[str, StageInventory]) -> str:
    missing = [stage for stage in STAGES if not stages[stage].ready]
    if not missing:
        return "Ready"
    return "Needs: " + ", ".join(_display_name(stage) for stage in missing)


def _checker(size: tuple[int, int], block: int = 24) -> Image.Image:
    image = Image.new("RGB", size, "#d8d8d8")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle(
                    (x, y, min(size[0], x + block), min(size[1], y + block)),
                    fill="#eeeeee",
                )
    return image


def _fit(image: Image.Image, size: tuple[int, int], background: str = "#101b18") -> Image.Image:
    canvas = Image.new("RGB", size, background)
    contained = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
    canvas.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    return canvas


def _fit_rgba_on_checker(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = _checker(size)
    contained = ImageOps.contain(image.convert("RGBA"), size, Image.Resampling.LANCZOS)
    canvas.paste(
        contained,
        ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2),
        contained,
    )
    return canvas


def _placeholder(size: tuple[int, int], title: str, detail: str) -> Image.Image:
    image = Image.new("RGB", size, "#211b1d")
    draw = ImageDraw.Draw(image)
    for offset in range(-size[1], size[0], 28):
        draw.line((offset, 0, offset + size[1], size[1]), fill="#342629", width=5)
    draw.rectangle((4, 4, size[0] - 5, size[1] - 5), outline="#8d6165", width=2)
    draw.text((16, 16), title, font=_font(16, bold=True), fill="#ffe9e9")
    detail_lines = textwrap.wrap(detail, width=max(18, size[0] // 10))[:5]
    draw.multiline_text(
        (16, 47), "\n".join(detail_lines), font=_font(13), fill="#dcbfc2", spacing=4
    )
    return image


def _title_bar(
    sheet: Image.Image,
    title: str,
    subtitle: str,
    *,
    height: int,
) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((0, 0, sheet.width, height), fill="#0b1714")
    draw.text((22, 16), title, font=_font(24, bold=True), fill="#f0f6ee")
    draw.text((22, 51), subtitle, font=_font(14), fill="#adc4b8")


def _render_rows(
    rows: list[dict[str, Any]],
    selected: list[StageInventory],
) -> list[dict[str, Any]]:
    backgrounds = [row for row in rows if row.get("category") == "backgrounds"]
    assets = [state.asset for state in selected if state.ready and state.asset is not None]
    return backgrounds + assets


def build_alpha_sheet(
    catalog: dict[str, dict[str, StageInventory]], output: Path
) -> tuple[Path, list[str]]:
    title_height = 104
    label_width = 190
    cell_width, cell_height = 210, 238
    sheet = Image.new(
        "RGB",
        (label_width + cell_width * len(STAGES), title_height + cell_height * len(SPECIES)),
        "#081310",
    )
    _title_bar(
        sheet,
        "Verdant Twilight V6 · Full-library alpha and growth lines",
        "Checkerboard reveals transparency. Missing or unintegrated V6 stages are shown explicitly.",
        height=title_height,
    )
    draw = ImageDraw.Draw(sheet)
    for column, stage in enumerate(STAGES):
        draw.text(
            (label_width + column * cell_width + 12, title_height - 28),
            _display_name(stage),
            font=_font(14, bold=True),
            fill="#dbe9df",
        )

    errors: list[str] = []
    for row_index, species in enumerate(SPECIES):
        y = title_height + row_index * cell_height
        ready = _line_ready(catalog[species])
        draw.rectangle((0, y, label_width, y + cell_height), fill="#10221d")
        draw.text((18, y + 18), _display_name(species), font=_font(17, bold=True), fill="#f0f6ee")
        draw.multiline_text(
            (18, y + 50),
            "Complete V6 line" if ready else _line_issue(catalog[species]),
            font=_font(12),
            fill="#8fceb0" if ready else "#d9a6aa",
            spacing=3,
        )
        for column, stage in enumerate(STAGES):
            state = catalog[species][stage]
            x = label_width + column * cell_width
            art_size = (cell_width - 16, cell_height - 46)
            if state.path.is_file():
                try:
                    with Image.open(state.path) as source:
                        cell = _fit_rgba_on_checker(source.convert("RGBA"), art_size)
                except (OSError, ValueError) as error:
                    message = f"{species}/{stage}: unreadable image: {error}"
                    errors.append(message)
                    cell = _placeholder(art_size, "Unreadable", str(error))
            else:
                cell = _placeholder(art_size, "Missing V6", "; ".join(state.issues))
            sheet.paste(cell, (x + 8, y + 6))
            status = "Ready" if state.ready else "; ".join(state.issues)
            draw.text(
                (x + 10, y + cell_height - 32),
                status[:30],
                font=_font(11, bold=state.ready),
                fill="#9dd5b9" if state.ready else "#e0aeb1",
            )
            draw.rectangle((x, y, x + cell_width, y + cell_height), outline="#243c34", width=1)

    path = output / "twilight_full_library_alpha_and_growth_lines.png"
    sheet.save(path, "PNG", optimize=True)
    return path, errors


def build_progression_sheet(
    rows: list[dict[str, Any]],
    catalog: dict[str, dict[str, StageInventory]],
    output: Path,
) -> tuple[Path, list[str]]:
    title_height = 112
    label_width = 190
    cell_width, cell_height = 450, 300
    sheet = Image.new(
        "RGB",
        (label_width + cell_width * len(LAYOUTS), title_height + cell_height * len(SPECIES)),
        "#081310",
    )
    _title_bar(
        sheet,
        "Verdant Twilight V6 · Full-library growth progression",
        "Each ready row seats Seed → Sprout → Young → Mature → Flowering → Rare across the six beds.",
        height=title_height,
    )
    draw = ImageDraw.Draw(sheet)
    for column, (layout_name, _width, _height, _context) in enumerate(LAYOUTS):
        draw.text(
            (label_width + column * cell_width + 12, title_height - 28),
            layout_name,
            font=_font(14, bold=True),
            fill="#dbe9df",
        )

    errors: list[str] = []
    for row_index, species in enumerate(SPECIES):
        y = title_height + row_index * cell_height
        stages = catalog[species]
        ready = _line_ready(stages)
        draw.rectangle((0, y, label_width, y + cell_height), fill="#10221d")
        draw.text((18, y + 18), _display_name(species), font=_font(17, bold=True), fill="#f0f6ee")
        draw.multiline_text(
            (18, y + 50),
            "Complete V6 line" if ready else _line_issue(stages),
            font=_font(12),
            fill="#8fceb0" if ready else "#d9a6aa",
            spacing=3,
        )
        selected = [stages[stage] for stage in STAGES]
        render_rows = _render_rows(rows, selected)
        for column, (layout_name, width, height, context) in enumerate(LAYOUTS):
            x = label_width + column * cell_width
            if ready:
                try:
                    scene = render_scene(
                        render_rows,
                        "verdant_twilight",
                        width,
                        height,
                        [species] * 6,
                        list(STAGES),
                        context=context,
                    )
                    cell = _fit(scene, (cell_width, cell_height), "#101b18")
                except (OSError, ValueError, KeyError, RuntimeError) as error:
                    message = f"{species}/{layout_name}: render failed: {error}"
                    errors.append(message)
                    cell = _placeholder((cell_width, cell_height), "Render failed", str(error))
            else:
                cell = _placeholder((cell_width, cell_height), "Incomplete V6 line", _line_issue(stages))
            sheet.paste(cell, (x, y))
            draw.rectangle((x, y, x + cell_width, y + cell_height), outline="#243c34", width=1)

    path = output / "twilight_full_library_growth_progression_all_layouts.png"
    sheet.save(path, "PNG", optimize=True)
    return path, errors


def build_responsive_matrix(
    rows: list[dict[str, Any]],
    catalog: dict[str, dict[str, StageInventory]],
    output: Path,
) -> tuple[Path, list[str]]:
    title_height = 112
    label_width = 190
    cell_width, cell_height = 340, 212
    species_header_height = 38
    species_block_height = species_header_height + cell_height * len(STAGES)
    sheet = Image.new(
        "RGB",
        (
            label_width + cell_width * len(LAYOUTS),
            title_height + species_block_height * len(SPECIES),
        ),
        "#081310",
    )
    _title_bar(
        sheet,
        "Verdant Twilight V6 · Full-library responsive stage matrix",
        "Every ready stage is repeated on all six beds in 4:3, 16:9, and Home layouts.",
        height=title_height,
    )
    draw = ImageDraw.Draw(sheet)
    for column, (layout_name, _width, _height, _context) in enumerate(LAYOUTS):
        draw.text(
            (label_width + column * cell_width + 12, title_height - 28),
            layout_name,
            font=_font(14, bold=True),
            fill="#dbe9df",
        )

    errors: list[str] = []
    for species_index, species in enumerate(SPECIES):
        block_y = title_height + species_index * species_block_height
        stages = catalog[species]
        ready = _line_ready(stages)
        draw.rectangle((0, block_y, sheet.width, block_y + species_header_height), fill="#132820")
        draw.text(
            (18, block_y + 9),
            f"{_display_name(species)} · {'Complete V6 line' if ready else _line_issue(stages)}",
            font=_font(14, bold=True),
            fill="#dff2e5" if ready else "#e2b4b7",
        )
        for stage_index, stage in enumerate(STAGES):
            state = stages[stage]
            y = block_y + species_header_height + stage_index * cell_height
            draw.rectangle((0, y, label_width, y + cell_height), fill="#10221d")
            draw.text((18, y + 18), _display_name(stage), font=_font(15, bold=True), fill="#f0f6ee")
            draw.multiline_text(
                (18, y + 47),
                "Ready" if state.ready else "; ".join(state.issues),
                font=_font(11),
                fill="#8fceb0" if state.ready else "#d9a6aa",
                spacing=3,
            )
            render_rows = _render_rows(rows, [state])
            for column, (layout_name, width, height, context) in enumerate(LAYOUTS):
                x = label_width + column * cell_width
                if state.ready:
                    try:
                        scene = render_scene(
                            render_rows,
                            "verdant_twilight",
                            width,
                            height,
                            [species],
                            [stage],
                            context=context,
                        )
                        cell = _fit(scene, (cell_width, cell_height), "#101b18")
                    except (OSError, ValueError, KeyError, RuntimeError) as error:
                        message = f"{species}/{stage}/{layout_name}: render failed: {error}"
                        errors.append(message)
                        cell = _placeholder((cell_width, cell_height), "Render failed", str(error))
                else:
                    cell = _placeholder((cell_width, cell_height), "Stage unavailable", "; ".join(state.issues))
                sheet.paste(cell, (x, y))
                draw.rectangle((x, y, x + cell_width, y + cell_height), outline="#243c34", width=1)

    path = output / "twilight_full_library_responsive_stage_matrix.png"
    sheet.save(path, "PNG", optimize=True)
    return path, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the three final Verdant Twilight V6 ten-species review sheets."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory (default: build/twilight-full-library-review).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Generate the sheets, then fail when any V6 stage is missing or invalid.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    catalog = inventory(rows)
    results = [
        build_alpha_sheet(catalog, output),
        build_progression_sheet(rows, catalog, output),
        build_responsive_matrix(rows, catalog, output),
    ]
    paths = [path for path, _errors in results]
    errors = [error for _path, render_errors in results for error in render_errors]
    complete = [species for species in SPECIES if _line_ready(catalog[species])]
    incomplete = [species for species in SPECIES if species not in complete]

    for path in paths:
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    print(f"Complete V6 lines: {len(complete)}/{len(SPECIES)} ({', '.join(map(_display_name, complete)) or 'none'})")
    for species in incomplete:
        print(f"INCOMPLETE {_display_name(species)}: {_line_issue(catalog[species])}")
    for error in errors:
        print(f"RENDER ERROR: {error}")
    if args.strict and (incomplete or errors):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
