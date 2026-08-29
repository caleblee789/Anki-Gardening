#!/usr/bin/env python3
"""Migrate large runtime PNGs to pixel-identical lossless WebP files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
PIXEL_BASELINE = ROOT / "tests" / "fixtures" / "runtime_lossless_webp_pixels.json"


def _collect_strings(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            found.update(_collect_strings(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_collect_strings(nested))
    elif isinstance(value, str):
        found.add(value)
    return found


def _visible_rgba_bytes(image: Image.Image) -> bytes:
    pixels = bytearray(image.convert("RGBA").tobytes())
    for offset in range(0, len(pixels), 4):
        if pixels[offset + 3] == 0:
            pixels[offset : offset + 3] = b"\0\0\0"
    return bytes(pixels)


def _pixel_record(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return {
            "width": rgba.width,
            "height": rgba.height,
            "visible_rgba_sha256": hashlib.sha256(_visible_rgba_bytes(rgba)).hexdigest(),
        }


def _target_pngs(payload: dict[str, Any]) -> list[str]:
    primary = {
        str(row["file"])
        for row in payload.get("assets", [])
        if isinstance(row, dict) and row.get("format") == "png"
    }
    occlusions = {
        value
        for value in _collect_strings(payload)
        if value.startswith("assets/") and value.endswith("_occlusion.png")
    }
    targets = sorted(primary | occlusions)
    missing = [relative for relative in targets if not (ADDON / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"missing PNG migration sources: {', '.join(missing)}")
    return targets


def _write_baseline(paths: list[str]) -> None:
    baseline = {relative: _pixel_record(ADDON / relative) for relative in paths}
    PIXEL_BASELINE.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _repack_occlusions(payload: dict[str, Any]) -> None:
    paths = sorted(
        value
        for value in _collect_strings(payload)
        if value.startswith("assets/") and value.endswith("_occlusion.webp")
    )
    for relative in paths:
        source = ADDON / relative
        before = _pixel_record(source)
        staged = source.with_suffix(".webp.tmp")
        with Image.open(source) as image:
            image.convert("RGBA").save(
                staged,
                format="WEBP",
                lossless=True,
                quality=100,
                method=6,
                exact=False,
            )
        if _pixel_record(staged) != before:
            staged.unlink(missing_ok=True)
            raise RuntimeError(f"visible-pixel verification failed: {relative}")
        staged.replace(source)

    primary = [
        str(row["file"])
        for row in payload.get("assets", [])
        if isinstance(row, dict)
        and row.get("category") in {"plants", "ui"}
        and str(row.get("file", "")).endswith(".webp")
    ]
    _write_baseline(sorted(set(primary) | set(paths)))
    print(f"repacked and verified {len(paths)} occlusion assets")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repack-occlusions", action="store_true")
    args = parser.parse_args()
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.repack_occlusions:
        _repack_occlusions(payload)
        return
    targets = _target_pngs(payload)
    if not targets:
        raise RuntimeError("manifest contains no runtime PNG migration targets")

    replacements: dict[str, str] = {}
    baseline: dict[str, dict[str, object]] = {}
    temporary: list[tuple[Path, Path, dict[str, object]]] = []
    for relative in targets:
        source = ADDON / relative
        destination = source.with_suffix(".webp")
        staged = destination.with_suffix(".webp.tmp")
        before = _pixel_record(source)
        with Image.open(source) as image:
            image.convert("RGBA").save(
                staged,
                format="WEBP",
                lossless=True,
                quality=100,
                method=6,
                exact=not relative.endswith("_occlusion.png"),
            )
        after = _pixel_record(staged)
        if after != before:
            staged.unlink(missing_ok=True)
            raise RuntimeError(f"lossless verification failed: {relative}")
        new_relative = destination.relative_to(ADDON).as_posix()
        replacements[relative] = new_relative
        baseline[new_relative] = before
        temporary.append((source, staged, before))

    for source, staged, _before in temporary:
        destination = staged.with_suffix("")
        staged.replace(destination)
        source.unlink()

    manifest_text = MANIFEST.read_text(encoding="utf-8")
    for old, new in replacements.items():
        manifest_text = manifest_text.replace(old, new)
    manifest_text = manifest_text.replace('"format": "png"', '"format": "webp"')
    MANIFEST.write_text(manifest_text, encoding="utf-8")
    PIXEL_BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"converted and verified {len(targets)} runtime assets")


if __name__ == "__main__":
    main()
