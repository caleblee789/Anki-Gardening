#!/usr/bin/env python3
"""Migrate large runtime PNGs to pixel-identical lossless WebP files."""

from __future__ import annotations

import argparse
import hashlib
import json
import io
import zlib
from concurrent.futures import ProcessPoolExecutor
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


def _zip_payload_size(payload: bytes) -> int:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return min(len(payload), len(compressor.compress(payload) + compressor.flush()))


def _exact_image_record(payload: bytes) -> dict[str, object]:
    with Image.open(io.BytesIO(payload)) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Only static runtime artwork can be re-encoded")
        return {
            "dimensions": list(image.size),
            "rgba_sha256": hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest(),
            "metadata": {
                key: hashlib.sha256(image.info[key]).hexdigest()
                for key in ("icc_profile", "exif", "xmp") if image.info.get(key)
            },
        }


def _compare_asset(job: tuple[str, str, str]) -> dict[str, object]:
    addon, destination, relative = job
    original = (Path(addon) / relative).read_bytes()
    record = _exact_image_record(original)
    best, setting = original, "original"
    best_size = _zip_payload_size(original)
    trials: list[dict[str, object]] = []
    with Image.open(io.BytesIO(original)) as image:
        rgba = image.convert("RGBA")
        metadata = {key: image.info[key] for key in ("icc_profile", "exif", "xmp") if image.info.get(key)}
        for quality, method in ((60, 6), (100, 4), (100, 6)):
            output = io.BytesIO()
            rgba.save(output, format="WEBP", lossless=True, exact=True,
                      quality=quality, method=method, **metadata)
            candidate = output.getvalue()
            if _exact_image_record(candidate) != record:
                raise RuntimeError(f"Exact RGBA/metadata verification failed: {relative}")
            size = _zip_payload_size(candidate)
            trials.append({"quality": quality, "method": method, "zip_bytes": size})
            if size < best_size and len(candidate) <= len(original):
                best, setting = candidate, f"quality={quality},method={method}"
                best_size = size
    target = Path(destination) / relative
    if best != original:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(best)
    return {
        "path": relative, "original_sha256": hashlib.sha256(original).hexdigest(),
        "candidate_sha256": hashlib.sha256(best).hexdigest(),
        "original_bytes": len(original), "candidate_bytes": len(best),
        "original_zip_bytes": _zip_payload_size(original),
        "candidate_zip_bytes": _zip_payload_size(best),
        "pixels": record, "setting": setting, "trials": trials,
    }


def compare_runtime_assets(destination: Path, *, workers: int = 4) -> Path:
    """Stage smaller exact lossless encodings; never modify runtime assets."""
    destination = destination.resolve()
    if destination == ADDON or ADDON in destination.parents:
        raise ValueError("Comparison output must be outside the runtime add-on")
    destination.mkdir(parents=True, exist_ok=False)
    manifest_bytes = MANIFEST.read_bytes()
    paths = sorted(value for value in _collect_strings(json.loads(manifest_bytes))
                   if value.startswith("assets/") and value.endswith(".webp"))
    jobs = [(str(ADDON), str(destination), path) for path in paths]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        for row in pool.map(_compare_asset, jobs):
            rows.append(row)
            print(f"{len(rows)}/{len(paths)} {row['path']}: "
                  f"{row['original_zip_bytes'] - row['candidate_zip_bytes']:,} bytes saved", flush=True)
    report = destination / "comparison.json"
    report.write_text(json.dumps({
        "schema_version": 1, "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "assets": rows,
        "zip_bytes_saved": sum(row["original_zip_bytes"] - row["candidate_zip_bytes"] for row in rows),
        "installed_bytes_saved": sum(row["original_bytes"] - row["candidate_bytes"] for row in rows),
    }, indent=2) + "\n", encoding="utf-8")
    return report


def apply_runtime_comparison(report: Path) -> None:
    """Apply staged winners only after the complete source and pixel preflight."""
    report = report.resolve()
    payload = json.loads(report.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported comparison schema")
    if hashlib.sha256(MANIFEST.read_bytes()).hexdigest() != payload["manifest_sha256"]:
        raise RuntimeError("Asset manifest changed since comparison")
    replacements = []
    for row in payload["assets"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "assets":
            raise ValueError("Invalid runtime asset path")
        source = ADDON / relative
        original = source.read_bytes()
        if hashlib.sha256(original).hexdigest() != row["original_sha256"]:
            raise RuntimeError(f"Asset changed since comparison: {relative}")
        if row["setting"] == "original":
            continue
        candidate = (report.parent / relative).read_bytes()
        if (hashlib.sha256(candidate).hexdigest() != row["candidate_sha256"]
                or _exact_image_record(candidate) != _exact_image_record(original)
                or _zip_payload_size(candidate) >= _zip_payload_size(original)
                or len(candidate) > len(original)):
            raise RuntimeError(f"Candidate verification failed: {relative}")
        replacements.append((source, candidate))
    for source, candidate in replacements:
        staged = source.with_suffix(".webp.tmp")
        try:
            staged.write_bytes(candidate)
            staged.replace(source)
        finally:
            staged.unlink(missing_ok=True)
    print(f"Applied {len(replacements)} pixel-identical smaller assets")


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--repack-occlusions", action="store_true")
    modes.add_argument("--compare-output", type=Path)
    modes.add_argument("--apply-comparison", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.compare_output:
        print(compare_runtime_assets(args.compare_output, workers=args.workers))
        return
    if args.apply_comparison:
        apply_runtime_comparison(args.apply_comparison)
        return
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
