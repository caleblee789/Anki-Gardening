#!/usr/bin/env python3
"""Assemble review sheets from actual Anki captures; never redraw the garden."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THEMES = ('default', 'spring', 'summer', 'autumn', 'snowy',
          'rainbow_horizon', 'halloween', 'full_moon', 'eclipse')
FEATURES = ('seedling_sign', 'wind_chime', 'harvest_bell', 'watering_station',
            'herbalist_hourglass', 'firefly_lantern', 'prism_trellis')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contact_sheet(frames: list[tuple[str, Path]], destination: Path, *, home=False) -> None:
    width, height = (640, 124) if home else (630, 420)
    columns = 1 if home else 2
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new('RGB', (width * columns, (height + 32) * rows), '#10231a')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, path) in enumerate(frames):
        with Image.open(path) as source:
            tile = source.convert('RGB')
            tile.thumbnail((width, height), Image.Resampling.LANCZOS)
        x, y = (index % columns) * width, (index // columns) * (height + 32)
        draw.text((x + 12, y + 10), label, fill='#e9dfbc', font=font)
        sheet.paste(tile, (x + (width - tile.width) // 2, y + 32))
    sheet.save(destination, 'PNG')


def build(output: Path, captures: Path) -> dict:
    report = json.loads((captures / 'first.json').read_text())
    if not report.get('passed'):
        raise ValueError('Native capture checks must pass before assembling final evidence')
    output.mkdir(parents=True, exist_ok=True)
    records, sheets, home_frames = [], [], []
    for theme in THEMES:
        native_frames = []
        for feature in (*FEATURES, 'hidden'):
            path = captures / f'matrix-native-{theme}-{feature}.png'
            with Image.open(path) as frame:
                dimensions = list(frame.size)
            records.append({'surface': 'native_garden', 'scenery': theme,
                            'decoration': feature, 'png': str(path),
                            'dimensions': dimensions, 'sha256': sha256(path)})
            native_frames.append((f'{theme} / {feature}', path))
        sheet = output / f'garden-{theme}.png'
        contact_sheet(native_frames, sheet)
        sheets.append(str(sheet))
        path = captures / f'matrix-home-{theme}-hidden.png'
        records.append({'surface': 'home_preview', 'scenery': theme,
                        'decoration': 'omitted', 'png': str(path), 'sha256': sha256(path)})
        home_frames.append((f'{theme} / Home preview without decorations', path))
    sheet = output / 'home-previews.png'
    contact_sheet(home_frames, sheet, home=True)
    sheets.append(str(sheet))
    manifest = {'schema': 'garden-feature-native-evidence-v2',
                'quality_status': 'review-required', 'release_ready': False,
                'native_visible_combinations': 63, 'native_hidden_baselines': 9,
                'home_previews_without_decorations': 9,
                'frame_count': len(records), 'records': records, 'sheets': sheets,
                'capture_report': str(captures / 'first.json'),
                'capture_report_sha256': sha256(captures / 'first.json')}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--captures', required=True, type=Path,
                        help='Completed isolated-Anki capture directory')
    args = parser.parse_args()
    manifest = build(args.output.resolve(), args.captures.resolve())
    print(json.dumps({key: manifest[key] for key in
                      ('frame_count', 'quality_status', 'release_ready')}))


if __name__ == '__main__':
    main()
