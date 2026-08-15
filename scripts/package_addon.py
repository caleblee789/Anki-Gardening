from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
DIST = ROOT / "dist"
OUTPUT = DIST / "anki_garden.ankiaddon"

PRODUCTION_BUILD = "production"
CAPTURE_BUILD = "capture"
BUILD_MODES = {PRODUCTION_BUILD, CAPTURE_BUILD}
CAPABILITY_MODULE = "build_capabilities.py"
CAPTURE_HARNESS = "capture_ui_faces.py"
PACKAGE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PACKAGE_FILE_MODE = 0o644
MAX_COMPRESSION_LEVEL = 9

EXCLUDED_PARTS = {"__pycache__", "cache", "metadata"}
EXCLUDED_NAMES = {"meta.json", "garden_state.json", "asset_metadata.json", ".DS_Store"}


def runtime_asset_paths() -> set[str]:
    """Return the complete, manifest-owned runtime asset set."""
    payload = json.loads((ADDON / "assets" / "manifest.json").read_text("utf-8"))
    referenced: set[str] = {"assets/manifest.json"}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif isinstance(value, str) and value.startswith("assets/"):
            referenced.add(value)

    collect(payload)
    missing = sorted(path for path in referenced if not (ADDON / path).is_file())
    if missing:
        raise FileNotFoundError(f"runtime asset paths are missing: {', '.join(missing)}")
    return referenced


def _normalized_build_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in BUILD_MODES:
        expected = ", ".join(sorted(BUILD_MODES))
        raise ValueError(f"unsupported package mode {mode!r}; expected one of: {expected}")
    return normalized


def build_capabilities_source(mode: str) -> str:
    """Return the immutable capability module injected into one archive."""

    normalized = _normalized_build_mode(mode)
    capture_enabled = normalized == CAPTURE_BUILD
    return (
        '"""Capabilities fixed when the add-on archive is built.\n\n'
        "The source checkout uses the fail-closed production defaults. The package\n"
        "builder replaces this module only for an explicitly requested capture build.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n\n"
        f'BUILD_MODE = "{normalized}"\n'
        f"CAPTURE_HARNESS_ENABLED = {capture_enabled!r}\n"
        f"DEVELOPMENT_MUTATION_ENABLED = {capture_enabled!r}\n\n"
    )


def package_payload(path: Path, mode: str = PRODUCTION_BUILD) -> bytes:
    """Return the exact bytes that ``path`` contributes to an archive."""

    normalized = _normalized_build_mode(mode)
    archive_name = path.relative_to(ADDON).as_posix()
    if archive_name == CAPABILITY_MODULE:
        return build_capabilities_source(normalized).encode("utf-8")
    return path.read_bytes()


def _raw_deflated_size(payload: bytes) -> int:
    compressor = zlib.compressobj(
        MAX_COMPRESSION_LEVEL,
        zlib.DEFLATED,
        -15,
    )
    return len(compressor.compress(payload) + compressor.flush())


def _compression_for(payload: bytes) -> int:
    """Use maximum DEFLATE unless storing the payload is strictly smaller."""

    return (
        zipfile.ZIP_STORED
        if len(payload) < _raw_deflated_size(payload)
        else zipfile.ZIP_DEFLATED
    )


def _archive_info(name: str, compression: int) -> zipfile.ZipInfo:
    """Return stable ZIP metadata so identical source yields identical bytes."""

    info = zipfile.ZipInfo(str(name), date_time=PACKAGE_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = PACKAGE_FILE_MODE << 16
    return info


def package_files(mode: str = PRODUCTION_BUILD) -> list[Path]:
    normalized = _normalized_build_mode(mode)
    files: list[Path] = []
    runtime_assets = runtime_asset_paths()
    for path in ADDON.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ADDON)
        if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.as_posix() == CAPTURE_HARNESS and normalized != CAPTURE_BUILD:
            continue
        if rel.parts and rel.parts[0] == "assets" and rel.as_posix() not in runtime_assets:
            continue
        if "user_files" in rel.parts and path.name != "README.txt":
            continue
        files.append(path)
    return sorted(files)


def _target_for(mode: str, output: Path | None) -> Path:
    normalized = _normalized_build_mode(mode)
    if output is None:
        if normalized == CAPTURE_BUILD:
            raise ValueError("capture builds require an explicit output path")
        return OUTPUT

    target = Path(output)
    if (
        normalized == CAPTURE_BUILD
        and target.resolve(strict=False) == OUTPUT.resolve(strict=False)
    ):
        raise ValueError("capture builds cannot overwrite the production artifact")
    return target


def _write_archive(target: Path, mode: str) -> None:
    with zipfile.ZipFile(target, "w", allowZip64=True) as archive:
        for path in package_files(mode):
            archive_name = path.relative_to(ADDON).as_posix()
            payload = package_payload(path, mode)
            compression = _compression_for(payload)
            info = _archive_info(archive_name, compression)
            if compression == zipfile.ZIP_DEFLATED:
                archive.writestr(
                    info,
                    payload,
                    compresslevel=MAX_COMPRESSION_LEVEL,
                )
            else:
                archive.writestr(info, payload)


def _validate_archive(target: Path, mode: str) -> None:
    expected_files = package_files(mode)
    expected_names = [path.relative_to(ADDON).as_posix() for path in expected_files]
    with zipfile.ZipFile(target) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if names != expected_names:
            raise ValueError("package entries do not match the expected ordered file set")
        if len(names) != len(set(names)):
            raise ValueError("package contains duplicate entries")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"package contains a corrupt entry: {corrupt}")
        for path, info in zip(expected_files, infos):
            expected = package_payload(path, mode)
            if archive.read(info) != expected:
                raise ValueError(f"package payload differs from source: {info.filename}")
            if info.date_time != PACKAGE_TIMESTAMP:
                raise ValueError(f"package timestamp is not deterministic: {info.filename}")
            if info.compress_type not in {zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED}:
                raise ValueError(f"package uses an unsupported compression method: {info.filename}")


def build(
    mode: str = PRODUCTION_BUILD,
    *,
    output: Path | None = None,
) -> Path:
    normalized = _normalized_build_mode(mode)
    manifest = json.loads((ADDON / "manifest.json").read_text("utf-8"))
    required = {"package", "name", "human_version", "min_point_version", "max_point_version"}
    missing = required.difference(manifest)
    if missing:
        raise ValueError(f"manifest.json missing: {', '.join(sorted(missing))}")

    target = _target_for(normalized, output)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _write_archive(temporary, normalized)
        _validate_archive(temporary, normalized)
        temporary.chmod(0o644)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def package_report(output: Path, mode: str = PRODUCTION_BUILD) -> dict[str, Any]:
    """Describe a completed package without writing a nondeterministic sidecar."""

    normalized = _normalized_build_mode(mode)
    target = Path(output)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    with zipfile.ZipFile(target) as archive:
        infos = archive.infolist()
        expected_capabilities = build_capabilities_source(normalized).encode("utf-8")
        try:
            archived_capabilities = archive.read(CAPABILITY_MODULE)
        except KeyError as exc:
            raise ValueError("package report requires build capabilities") from exc
        if archived_capabilities != expected_capabilities:
            raise ValueError(
                f"package capabilities do not describe a {normalized} build"
            )
        largest = sorted(
            infos,
            key=lambda item: (-item.file_size, item.filename),
        )[:10]
        return {
            "archive_sha256": digest.hexdigest(),
            "archive_size_bytes": target.stat().st_size,
            "deflated_entries": sum(
                info.compress_type == zipfile.ZIP_DEFLATED for info in infos
            ),
            "file_count": len(infos),
            "largest_entries": [
                {
                    "compressed_bytes": info.compress_size,
                    "name": info.filename,
                    "size_bytes": info.file_size,
                }
                for info in largest
            ],
            "mode": normalized,
            "output": str(target),
            "payload_compressed_bytes": sum(info.compress_size for info in infos),
            "payload_uncompressed_bytes": sum(info.file_size for info in infos),
            "stored_entries": sum(
                info.compress_type == zipfile.ZIP_STORED for info in infos
            ),
        }


def _requested_cli_build(
    arguments: Sequence[str] | None = None,
) -> tuple[str, Path | None]:
    parser = argparse.ArgumentParser(
        description="Build the Anki Garden add-on archive.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--production",
        action="store_true",
        help="build the distributable production archive (default)",
    )
    mode.add_argument(
        "--capture",
        action="store_true",
        help="include the isolated UI-capture harness and development seed capability",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="explicit capture archive path (required with --capture)",
    )
    parsed = parser.parse_args(arguments)
    mode_name = CAPTURE_BUILD if parsed.capture else PRODUCTION_BUILD
    if mode_name == CAPTURE_BUILD and parsed.output is None:
        parser.error("--capture requires --output")
    if mode_name == PRODUCTION_BUILD and parsed.output is not None:
        parser.error("--output is reserved for explicit capture builds")
    return mode_name, parsed.output


def _requested_cli_mode(arguments: Sequence[str] | None = None) -> str:
    """Compatibility helper for callers that need only the explicit mode."""

    return _requested_cli_build(arguments)[0]


if __name__ == "__main__":
    requested_mode, requested_output = _requested_cli_build()
    built = build(requested_mode, output=requested_output)
    print(json.dumps(package_report(built, requested_mode), sort_keys=True))
