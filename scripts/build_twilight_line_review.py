from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from build_release_placement_review import _font, render_scene


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
LAYOUTS = (
    ("4:3 dashboard", 960, 720, "dashboard"),
    ("16:9 dashboard", 960, 540, "dashboard"),
    ("Home widget", 960, 400, "home"),
)


def _tile(image: Image.Image, label: str, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", (size[0], size[1] + 38), "#101b18")
    tile.paste(image.resize(size, Image.Resampling.LANCZOS), (0, 0))
    ImageDraw.Draw(tile).text(
        (12, size[1] + 9), label, font=_font(15, bold=True), fill="#eef6ed"
    )
    return tile


def _stage_matrix(rows: list[dict], species: str, output: Path) -> Path:
    tile_size = (480, 300)
    sheet = Image.new(
        "RGB",
        (tile_size[0] * len(LAYOUTS), (tile_size[1] + 38) * len(STAGES)),
        "#081310",
    )
    for row_index, stage in enumerate(STAGES):
        for column, (layout_name, width, height, context) in enumerate(LAYOUTS):
            scene = render_scene(
                rows,
                "verdant_twilight",
                width,
                height,
                [species],
                [stage],
                context=context,
            )
            tile = _tile(scene, f"{stage.title()} · {layout_name}", tile_size)
            sheet.paste(tile, (column * tile_size[0], row_index * (tile_size[1] + 38)))
    path = output / f"{species}_responsive_stage_matrix.png"
    sheet.save(path, "PNG", optimize=True)
    return path


def _progression_strip(rows: list[dict], species: str, output: Path) -> Path:
    tile_size = (640, 400)
    sheet = Image.new("RGB", (tile_size[0] * len(LAYOUTS), tile_size[1] + 38), "#081310")
    for column, (layout_name, width, height, context) in enumerate(LAYOUTS):
        scene = render_scene(
            rows,
            "verdant_twilight",
            width,
            height,
            [species] * 6,
            list(STAGES),
            context=context,
        )
        tile = _tile(scene, layout_name, tile_size)
        sheet.paste(tile, (column * tile_size[0], 0))
    path = output / f"{species}_growth_progression_all_layouts.png"
    sheet.save(path, "PNG", optimize=True)
    return path


def _alpha_strip(species: str, output: Path) -> Path:
    runtime_plants = (
        ROOT / "ankigarden" / "assets" / "v6_storybook_gouache" / "plants" / species
    )
    tile_size = (300, 300)
    sheet = Image.new("RGB", (tile_size[0] * len(STAGES), tile_size[1] + 38), "#081310")
    for column, stage in enumerate(STAGES):
        source = runtime_plants / stage / f"{species}_{stage}_twilight_v6.webp"
        if not source.is_file():
            raise FileNotFoundError(f"Missing runtime asset: {source}")
        with Image.open(source) as image:
            rgba = image.convert("RGBA")
        checker = Image.new("RGB", rgba.size, "#d8d8d8")
        pixels = checker.load()
        block = 48
        for y in range(checker.height):
            for x in range(checker.width):
                if (x // block + y // block) % 2:
                    pixels[x, y] = (238, 238, 238)
        checker.paste(rgba, mask=rgba.getchannel("A"))
        tile = _tile(checker, stage.title(), tile_size)
        sheet.paste(tile, (column * tile_size[0], 0))
    path = output / f"{species}_alpha_and_growth_line.png"
    sheet.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Verdant Twilight plant-line review gate.")
    parser.add_argument("--species", required=True)
    args = parser.parse_args()
    species = args.species.strip().lower()
    output = ROOT / "build" / f"twilight-{species}-pilot"
    output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    outputs = [
        _alpha_strip(species, output),
        _progression_strip(rows, species, output),
        _stage_matrix(rows, species, output),
    ]
    for path in outputs:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
