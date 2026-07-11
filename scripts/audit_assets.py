from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
SUPPORTED_FORMATS = {"svg", "png", "webp"}


def audit() -> dict[str, int]:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    rows = payload.get("assets", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("asset manifest is empty")

    seen: set[str] = set()
    counts: Counter[str] = Counter()
    for row in rows:
        rel = str(row.get("file", ""))
        category = str(row.get("category", ""))
        if not rel or not category:
            raise ValueError(f"invalid manifest row: {row!r}")
        if rel in seen:
            raise ValueError(f"duplicate asset path: {rel}")
        seen.add(rel)
        path = ADDON / rel
        if not path.is_file():
            raise FileNotFoundError(path)
        declared_format = str(row.get("format", "")).lower()
        if declared_format not in SUPPORTED_FORMATS or path.suffix.lower() != f".{declared_format}":
            raise ValueError(f"unsupported or mismatched asset format: {rel}")
        if declared_format == "svg":
            root = ET.parse(path).getroot()
            if not root.tag.endswith("svg") or not root.attrib.get("viewBox"):
                raise ValueError(f"SVG lacks a valid viewBox: {rel}")
        elif declared_format == "png" and path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"invalid PNG signature: {rel}")
        elif declared_format == "webp":
            signature = path.read_bytes()[:12]
            if signature[:4] != b"RIFF" or signature[8:] != b"WEBP":
                raise ValueError(f"invalid WebP signature: {rel}")
        if int(row.get("width", 0)) <= 0 or int(row.get("height", 0)) <= 0:
            raise ValueError(f"manifest dimensions are invalid: {rel}")
        counts[category] += 1

    expected = {"backgrounds": 76, "decorations": 5, "plants": 57, "ui": 3, "weather": 10}
    if dict(counts) != expected:
        raise ValueError(f"asset coverage changed: expected {expected}, got {dict(counts)}")
    return dict(counts)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
