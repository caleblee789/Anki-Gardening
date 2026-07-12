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
    asset_ids = {str(row.get("asset_id", "")) for row in rows if isinstance(row, dict)}
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
        elif declared_format == "png":
            png_header = path.read_bytes()[:26]
            if png_header[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"invalid PNG signature: {rel}")
            if row.get("alpha") is True and (len(png_header) < 26 or png_header[25] not in {4, 6}):
                raise ValueError(f"PNG declared alpha but has no alpha channel: {rel}")
        elif declared_format == "webp":
            signature = path.read_bytes()[:12]
            if signature[:4] != b"RIFF" or signature[8:] != b"WEBP":
                raise ValueError(f"invalid WebP signature: {rel}")
        if int(row.get("width", 0)) <= 0 or int(row.get("height", 0)) <= 0:
            raise ValueError(f"manifest dimensions are invalid: {rel}")
        fallback_id = str(row.get("fallback_asset_id", ""))
        if fallback_id and fallback_id not in asset_ids:
            raise ValueError(f"missing fallback asset {fallback_id!r}: {rel}")
        placement = row.get("placement")
        if placement is not None:
            if not isinstance(placement, dict):
                raise ValueError(f"invalid placement metadata: {rel}")
            for key in ("anchor_x", "baseline_y", "scale"):
                try:
                    value = float(placement[key])
                except (KeyError, TypeError, ValueError):
                    raise ValueError(f"invalid placement {key}: {rel}")
                if key != "scale" and not 0.0 <= value <= 1.0:
                    raise ValueError(f"placement {key} out of range: {rel}")
                if key == "scale" and not 0.1 <= value <= 2.5:
                    raise ValueError(f"placement scale out of range: {rel}")
            if placement.get("crop") not in {"contain", "cover"} or not placement.get("layer"):
                raise ValueError(f"invalid placement crop/layer: {rel}")
        if category in {"plants", "backgrounds"}:
            # Every production profile must be resolvable to the complete
            # category contract, including assets that rely on legacy defaults.
            resolved = dict(placement or {})
            if category == "plants":
                resolved.setdefault("visible_bounds", [0.08, 0.04, 0.84, 0.92])
                resolved.setdefault("ground_anchor", [0.5, 0.96])
                resolved.setdefault("display_scale", resolved.get("scale", 1.0))
                resolved.setdefault("base_type", "legacy")
                required = {"visible_bounds", "ground_anchor", "display_scale", "base_type", "layer"}
            else:
                resolved.setdefault("focal_point", [0.5, 0.43])
                resolved.setdefault("planting_zone", {"left": 0.08, "right": 0.92, "far_y": 0.62, "near_y": 0.91})
                required = {"focal_point", "planting_zone", "layer"}
            resolved.setdefault("layer", "plants" if category == "plants" else "background")
            if not required.issubset(resolved):
                raise ValueError(f"resolved production placement metadata incomplete: {rel}")
        counts[category] += 1

    expected = {"backgrounds": 78, "decorations": 5, "plants": 69, "ui": 3, "weather": 10}
    if dict(counts) != expected:
        raise ValueError(f"asset coverage changed: expected {expected}, got {dict(counts)}")
    return dict(counts)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
