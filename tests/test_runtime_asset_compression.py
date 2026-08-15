from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
BASELINE = ROOT / "tests" / "fixtures" / "runtime_lossless_webp_pixels.json"


def _visible_rgba_bytes(image: Image.Image) -> bytes:
    pixels = bytearray(image.convert("RGBA").tobytes())
    for offset in range(0, len(pixels), 4):
        if pixels[offset + 3] == 0:
            pixels[offset : offset + 3] = b"\0\0\0"
    return bytes(pixels)


def _asset_paths(value: object) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            paths.update(_asset_paths(nested))
    elif isinstance(value, list):
        for nested in value:
            paths.update(_asset_paths(nested))
    elif isinstance(value, str) and value.startswith("assets/"):
        paths.add(value)
    return paths


def test_lossless_webp_runtime_assets_retain_exact_rgba_pixels() -> None:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    manifest = json.loads((ADDON / "assets" / "manifest.json").read_text(encoding="utf-8"))
    primary = {
        str(row["file"])
        for row in manifest["assets"]
        if row.get("category") in {"plants", "ui", "decorations"}
    }
    occlusions = {
        path for path in _asset_paths(manifest) if path.endswith("_occlusion.webp")
    }
    assert len(expected) == 151
    assert set(expected) == primary | occlusions
    assert all(path.endswith(".webp") for path in expected)

    for relative, record in expected.items():
        path = ADDON / relative
        assert path.is_file(), relative
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            assert rgba.format is None
            assert rgba.size == (record["width"], record["height"]), relative
            assert (
                hashlib.sha256(_visible_rgba_bytes(rgba)).hexdigest()
                == record["visible_rgba_sha256"]
            ), relative
