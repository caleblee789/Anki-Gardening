#!/usr/bin/env python3
"""Build, capture, and contact-sheet every UI face in Anki Garden."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import os
import pickle
import re
import signal
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


CONTACT_SHEET_PREFIX = "anki-garden-ui-contact-sheet-"
CONTACT_SHEET_RETENTION = 3
CONTACT_SHEET_COLUMNS = 2
CONTACT_SHEET_MAX_ROWS = 5
CAPTURE_UI_SCALE = 1.0
CAPTURE_SEQUENCE_PREFIX = "capture-sequence-"
CAPTURE_ARCHIVE_PREFIX = "anki-garden-ui-faces-"
CAPTURE_SEQUENCE_NAME = re.compile(
    rf"^{re.escape(CAPTURE_SEQUENCE_PREFIX)}(?P<stamp>\d{{8}}-\d{{6}})$"
)
CONTACT_SHEET_SET_NAME = re.compile(
    rf"^{re.escape(CONTACT_SHEET_PREFIX)}"
    r"(?P<version>[A-Za-z0-9._-]+)-(?P<stamp>\d{8}-\d{6})$"
)
LEGACY_CONTACT_SHEET_NAME = re.compile(
    rf"^{re.escape(CONTACT_SHEET_PREFIX)}"
    r"(?:[A-Za-z0-9._-]+-)?(?P<stamp>\d{8}-\d{6})\.png$"
)
PACKAGE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CAPTURE_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"


class CaptureError(RuntimeError):
    """Report a capture that cannot satisfy the UI-face contract."""


class RestrictedUnpickler(pickle.Unpickler):
    """Read Anki's primitive profile dictionaries without loading classes."""

    def find_class(self, module: str, name: str) -> Any:
        raise pickle.UnpicklingError(
            f"global {module}.{name} is not permitted in disposable profile metadata"
        )


def run(command: list[str], *, cwd: Path, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout or ""


def json_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    output = run(command, cwd=cwd, capture=True)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"Expected JSON from {' '.join(command)}, received: {output}") from exc


def command_python(repo: Path) -> str:
    venv_python = repo / ".venv" / "bin" / "python"
    return str(venv_python if venv_python.is_file() else Path(sys.executable))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_package(
    repo: Path,
    python: str,
    output: Path,
) -> tuple[Path, str, dict[str, Any]]:
    package = output.resolve()
    run(
        [
            python,
            "scripts/package_addon.py",
            "--capture",
            "--output",
            str(package),
        ],
        cwd=repo,
    )
    if not package.is_file():
        raise CaptureError(f"Package build did not produce {package}")
    with zipfile.ZipFile(package) as archive:
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise CaptureError("The built package has no valid manifest.json") from exc
        names = set(archive.namelist())
        required_capture_entries = {
            "capture_ui_faces.py",
            "capture/runtime.py",
            "capture/capture-contract-v27.json",
        }
        if not required_capture_entries.issubset(names):
            raise CaptureError(
                "The built package does not contain the complete v27 capture runtime"
            )
    package_id = str(manifest.get("package", "")).strip()
    if not package_id or any(part in package_id for part in ("/", "\\", "..")):
        raise CaptureError("The built package has an unsafe or missing package identifier")
    return package, package_id, manifest


def capture_derivative_report(
    repo: Path,
    production_package: Path,
    capture_package: Path,
) -> dict[str, Any]:
    """Load the repository-owned production-to-capture archive proof."""

    package_script = repo / "scripts" / "package_addon.py"
    spec = importlib.util.spec_from_file_location(
        "_anki_garden_capture_package_addon",
        package_script,
    )
    if spec is None or spec.loader is None:
        raise CaptureError(f"Could not load package verifier: {package_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verifier = getattr(module, "capture_derivative_report", None)
    if not callable(verifier):
        raise CaptureError("Package builder has no capture derivative verifier")
    try:
        report = verifier(production_package, capture_package)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise CaptureError(f"Capture derivative verification failed: {error}") from error
    if not isinstance(report, dict):
        raise CaptureError("Capture derivative verifier returned an invalid report")
    retired_capture_entries = {
        str(entry)
        for entry in getattr(module, "PRODUCTION_RETIRED_MODULES", ())
    }
    if (
        report.get("shared_payloads_identical") is not True
        or "capture_ui_faces.py" not in report.get("capture_only_entries", ())
        or "capture/runtime.py" not in report.get("capture_only_entries", ())
        or any(
            entry != "capture_ui_faces.py"
            and not str(entry).startswith("capture/")
            and str(entry) not in retired_capture_entries
            for entry in report.get("capture_only_entries", ())
        )
        or report.get("mode_specific_entries") != ["build_capabilities.py"]
    ):
        raise CaptureError("Capture derivative verifier did not prove the allowed delta")
    for field in (
        "capture_archive_sha256",
        "production_archive_sha256",
        "shared_payload_sha256",
    ):
        value = report.get(field)
        if not isinstance(value, str) or PACKAGE_SHA256.fullmatch(value) is None:
            raise CaptureError(f"Capture derivative report has an invalid {field}")
    count = report.get("shared_payload_entry_count")
    if type(count) is not int or count < 1:
        raise CaptureError("Capture derivative report has no shared package payloads")
    return report


def extract_package(package: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise CaptureError(f"Package contains an unsafe path: {member.filename}")
        archive.extractall(destination)


def set_disposable_ui_scale(run_root: Path, scale: float = CAPTURE_UI_SCALE) -> None:
    """Set Anki's global profile scale in the cloned disposable base."""
    prefs = run_root / "prefs21.db"
    if not prefs.is_file():
        raise CaptureError(f"Disposable Anki preferences are missing: {prefs}")
    connection = sqlite3.connect(prefs, timeout=5)
    try:
        connection.execute("begin immediate")
        row = connection.execute(
            "select data from profiles where name = '_global'"
        ).fetchone()
        if row is None:
            raise CaptureError("Disposable Anki preferences have no _global profile row")
        try:
            metadata = RestrictedUnpickler(io.BytesIO(bytes(row[0]))).load()
        except (EOFError, pickle.UnpicklingError, ValueError) as exc:
            raise CaptureError("Cannot safely decode disposable Anki metadata") from exc
        if not isinstance(metadata, dict) or not all(
            isinstance(key, str) for key in metadata
        ):
            raise CaptureError("Disposable Anki metadata is not a primitive dictionary")
        metadata["uiScale"] = float(scale)
        connection.execute(
            "update profiles set data = ? where name = '_global'",
            (pickle.dumps(metadata, protocol=4),),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    with sqlite3.connect(prefs) as verification:
        row = verification.execute(
            "select data from profiles where name = '_global'"
        ).fetchone()
    if row is None:
        raise CaptureError("Disposable Anki scale verification could not read metadata")
    verified = RestrictedUnpickler(io.BytesIO(bytes(row[0]))).load()
    if not isinstance(verified, dict) or float(verified.get("uiScale", 0)) != float(scale):
        raise CaptureError("Disposable Anki UI scale did not persist")


def find_manifest(capture_dir: Path) -> Path | None:
    manifests = sorted(capture_dir.glob("*/manifest.json"))
    return manifests[-1] if manifests else None


def capture_groups(payload: dict[str, Any]) -> list[tuple[str, list[str]]]:
    raw_groups = payload.get("capture_groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise CaptureError("Capture manifest has no grouped UI-surface contract")
    groups: list[tuple[str, list[str]]] = []
    for item in raw_groups:
        if not isinstance(item, dict):
            raise CaptureError("Capture manifest contains an invalid surface group")
        name = str(item.get("name", "")).strip()
        labels = item.get("labels")
        if not name or not isinstance(labels, list) or not labels:
            raise CaptureError("Capture manifest contains an incomplete surface group")
        normalized = [str(label).strip() for label in labels]
        if any(not label for label in normalized):
            raise CaptureError(f"Capture group {name!r} contains an empty label")
        groups.append((name, normalized))
    return groups


def _capture_display_report_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve legacy display reporting and carry the optional display history."""

    fields: dict[str, Any] = {
        "capture_display": payload.get("capture_display", "primary"),
    }
    if "capture_displays" in payload:
        fields["capture_displays"] = payload["capture_displays"]
    return fields


def validate_manifest(
    path: Path,
) -> tuple[dict[str, Any], list[Path], list[tuple[str, list[str]]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaptureError(f"Invalid capture manifest: {path}") from exc
    details: list[str] = []
    if int(payload.get("capture_contract_version", 0) or 0) < 2:
        details.append("capture contract version 2 or newer is required")

    expected = payload.get("expected_faces")
    if not isinstance(expected, list) or not expected:
        details.append("expected_faces is missing or empty")
        expected_labels: list[str] = []
    else:
        expected_labels = [str(label).strip() for label in expected]
        if any(not label for label in expected_labels):
            details.append("expected_faces contains an empty label")
        if len(expected_labels) != len(set(expected_labels)):
            details.append("expected_faces contains duplicate labels")

    groups = capture_groups(payload)
    grouped_labels = [label for _name, labels in groups for label in labels]
    if grouped_labels != expected_labels:
        details.append("capture_groups does not exactly match expected_faces")

    raw_screenshots = payload.get("screenshots")
    screenshots = (
        [Path(str(item)).expanduser() for item in raw_screenshots]
        if isinstance(raw_screenshots, list)
        else []
    )
    records = payload.get("captures")
    records = records if isinstance(records, list) else []
    captured_labels = [
        str(record.get("label", "")).strip()
        for record in records
        if isinstance(record, dict)
    ]
    record_paths = [
        Path(str(record.get("path", ""))).expanduser()
        for record in records
        if isinstance(record, dict)
    ]
    if captured_labels != expected_labels:
        missing = [label for label in expected_labels if label not in captured_labels]
        unexpected = [label for label in captured_labels if label not in expected_labels]
        if missing:
            details.append("missing faces: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected faces: " + ", ".join(unexpected))
        if not missing and not unexpected:
            details.append("captured faces are out of contract order")
    if len(screenshots) != len(expected_labels):
        details.append(
            f"expected {len(expected_labels)} screenshots, found {len(screenshots)}"
        )
    if len(record_paths) != len(screenshots):
        details.append("capture records and screenshot list have different lengths")
    elif [item.resolve() for item in record_paths] != [item.resolve() for item in screenshots]:
        details.append("capture record paths do not match the screenshot list")

    session_root = path.parent.resolve()
    missing_files: list[str] = []
    invalid_files: list[str] = []
    for image in screenshots:
        resolved = image.resolve()
        if session_root not in resolved.parents:
            invalid_files.append(str(image))
            continue
        if not resolved.is_file():
            missing_files.append(str(image))
            continue
        try:
            with resolved.open("rb") as handle:
                if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                    invalid_files.append(str(image))
        except OSError:
            invalid_files.append(str(image))
    if missing_files:
        details.append("missing files: " + ", ".join(missing_files))
    if invalid_files:
        details.append("invalid PNG files: " + ", ".join(invalid_files))

    expected_count = int(payload.get("expected_count", 0) or 0)
    if expected_count != len(expected_labels):
        details.append(
            f"manifest expected_count is {expected_count}, contract has {len(expected_labels)} faces"
        )
    failures = payload.get("failures") or []
    if failures:
        details.append(f"capture reported {len(failures)} UI failure(s)")
    if payload.get("capture_profile") != "representative":
        details.append("capture_profile must be 'representative' for release evidence")
    if payload.get("complete") is not True:
        details.append("capture manifest is not marked complete")
    requested_scale = str(payload.get("requested_scale_factor", ""))
    if requested_scale not in {"1", "1.0", "1.00", "1.000"}:
        details.append("capture did not run at the required 100 percent UI scale")
    if details:
        raise CaptureError("; ".join(details))
    return payload, screenshots, groups


def _load_font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        if bold else Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _display_label(label: str) -> str:
    words = []
    for word in label.split("-"):
        words.append({"anki": "Anki", "ui": "UI"}.get(word, word.capitalize()))
    return " ".join(words)


def paginate_contact_sheet_groups(
    groups: list[tuple[str, list[str]]],
    *,
    columns: int = CONTACT_SHEET_COLUMNS,
    max_rows: int = CONTACT_SHEET_MAX_ROWS,
) -> list[list[tuple[str, list[str]]]]:
    """Pack whole UI groups into readable pages without exceeding max_rows."""
    if columns < 1 or max_rows < 1:
        raise CaptureError("Contact-sheet columns and rows must be positive")

    pages: list[list[tuple[str, list[str]]]] = []
    current: list[tuple[str, list[str]]] = []
    current_rows = 0
    capacity = columns * max_rows

    for group_name, source_labels in groups:
        labels = list(source_labels)
        if not labels:
            continue
        if len(labels) > capacity:
            if current:
                pages.append(current)
                current = []
                current_rows = 0
            for offset in range(0, len(labels), capacity):
                chunk = labels[offset : offset + capacity]
                suffix = "" if offset == 0 else " (continued)"
                pages.append([(f"{group_name}{suffix}", chunk)])
            continue

        group_rows = math.ceil(len(labels) / columns)
        if current and current_rows + group_rows > max_rows:
            pages.append(current)
            current = []
            current_rows = 0
        current.append((group_name, labels))
        current_rows += group_rows

    if current:
        pages.append(current)
    if not pages:
        raise CaptureError("Cannot render an empty contact-sheet set")
    return pages


def _page_slug(page_groups: list[tuple[str, list[str]]]) -> str:
    raw = "-".join(name.replace(" (continued)", "") for name, _labels in page_groups)
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "ui-surfaces"


def _canonical_json_text(value: Any) -> str:
    """Serialize provenance metadata without whitespace or ordering drift."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _contact_page_surface_identity_map(
    page: list[tuple[str, list[str]]],
    records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return the exact v27 scenario identity for every surface on one page."""

    identity_map: dict[str, dict[str, Any]] = {}
    for _group_name, labels in page:
        for label in labels:
            record = records.get(label)
            if record is None:
                raise CaptureError(f"Contact-sheet record disappeared: {label}")
            scenario_id = record.get("scenario_id")
            fixture_id = record.get("fixture_id")
            scenario_step = record.get("scenario_step")
            if not isinstance(scenario_id, str) or not scenario_id.strip():
                raise CaptureError(
                    f"Contact-sheet record has no scenario_id: {label}"
                )
            if not isinstance(fixture_id, str) or not fixture_id.strip():
                raise CaptureError(
                    f"Contact-sheet record has no fixture_id: {label}"
                )
            if type(scenario_step) is not int or scenario_step < 1:
                raise CaptureError(
                    f"Contact-sheet record has an invalid scenario_step: {label}"
                )
            identity_map[label] = {
                "scenario_id": scenario_id,
                "fixture_id": fixture_id,
                "scenario_step": scenario_step,
            }
    return identity_map


def render_contact_sheets(
    *,
    payload: dict[str, Any],
    groups: list[tuple[str, list[str]]],
    package_manifest: dict[str, Any],
    package_sha256: str,
    output_root: Path,
    stamp: str,
) -> tuple[Path, list[Path], Path]:
    try:
        from PIL import Image, ImageDraw, ImageOps, PngImagePlugin
    except ImportError as exc:
        raise CaptureError(
            "Pillow is required to build the UI contact sheet"
        ) from exc

    records = {
        str(record["label"]): record
        for record in payload.get("captures", [])
        if isinstance(record, dict) and record.get("label") and record.get("path")
    }
    colors = {
        "canvas": "#081814",
        "panel": "#102923",
        "panel_border": "#315247",
        "preview": "#d8d1be",
        "preview_outline": "#9e947c",
        "screenshot_outline": "#49665c",
        "title": "#f4f3df",
        "muted": "#9fb4a7",
        "accent": "#d2ad67",
        "line": "#315247",
    }
    version = str(package_manifest.get("human_version", "unknown")).strip() or "unknown"
    captured_at = str(payload.get("captured_at", "unknown time"))
    capture_display = str(payload.get("capture_display", "primary"))
    expected_count = len(payload.get("expected_faces", []))
    warning_count = len(payload.get("text_layout_warnings") or [])
    quality_copy = (
        "Visual review required"
        if warning_count else
        "Clean geometry audit"
    )
    contact_dir = output_root / "contact-sheets"
    contact_dir.mkdir(parents=True, exist_ok=True)
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", version).strip("-_") or "unknown"
    set_dir = contact_dir / f"{CONTACT_SHEET_PREFIX}{safe_version}-{stamp}"
    set_dir.mkdir(parents=False, exist_ok=False)

    page_groups = paginate_contact_sheet_groups(groups)
    number_by_label = {
        label: index
        for index, label in enumerate(
            (label for _group_name, labels in groups for label in labels),
            start=1,
        )
    }
    ordinal_width = max(2, len(str(expected_count)))
    columns = CONTACT_SHEET_COLUMNS
    canvas_width = 3000
    margin = 64
    gutter = 32
    header_height = 250
    group_header_height = 84
    cell_height = 930
    group_gap = 30
    preview_inset = 8
    screenshot_outline_width = 3
    cell_width = (canvas_width - (margin * 2) - (gutter * (columns - 1))) // columns
    title_font = _load_font(56, bold=True)
    subtitle_font = _load_font(31)
    meta_font = _load_font(23)
    group_font = _load_font(38, bold=True)
    label_font = _load_font(30, bold=True)
    tile_meta_font = _load_font(22)
    outputs: list[Path] = []
    page_index_records: list[dict[str, Any]] = []

    for page_number, page in enumerate(page_groups, start=1):
        surface_identity_map = _contact_page_surface_identity_map(page, records)
        surface_ids = list(surface_identity_map)
        identity_field_maps = {
            identity_field: {
                label: identity[identity_field]
                for label, identity in surface_identity_map.items()
            }
            for identity_field in ("scenario_id", "fixture_id", "scenario_step")
        }
        total_height = header_height + margin
        for _name, labels in page:
            total_height += group_header_height
            total_height += math.ceil(len(labels) / columns) * cell_height
            total_height += group_gap

        sheet = Image.new("RGB", (canvas_width, total_height), colors["canvas"])
        draw = ImageDraw.Draw(sheet)
        page_surface_count = sum(len(labels) for _name, labels in page)
        draw.text(
            (margin, 48),
            f"Anki Garden UI Contact Sheets · {page_number} of {len(page_groups)}",
            font=title_font,
            fill=colors["title"],
        )
        draw.text(
            (margin, 119),
            f"Release {version} · {page_surface_count} on this sheet · {expected_count} total · {quality_copy}",
            font=subtitle_font,
            fill=colors["accent"],
        )
        draw.text(
            (margin, 177),
            f"Captured {captured_at} on {capture_display} display · Package SHA-256 {package_sha256[:16]}…",
            font=meta_font,
            fill=colors["muted"],
        )

        y = header_height
        for group_name, labels in page:
            draw.text(
                (margin, y + 12),
                group_name,
                font=group_font,
                fill=colors["title"],
            )
            count_copy = f"{len(labels)} surface{'s' if len(labels) != 1 else ''}"
            count_box = draw.textbbox((0, 0), count_copy, font=meta_font)
            draw.text(
                (canvas_width - margin - (count_box[2] - count_box[0]), y + 22),
                count_copy,
                font=meta_font,
                fill=colors["muted"],
            )
            draw.line(
                (margin, y + 68, canvas_width - margin, y + 68),
                fill=colors["line"],
                width=3,
            )
            y += group_header_height

            for group_index, label in enumerate(labels):
                row = group_index // columns
                column = group_index % columns
                x = margin + column * (cell_width + gutter)
                tile_y = y + row * cell_height
                draw.rounded_rectangle(
                    (x, tile_y, x + cell_width, tile_y + cell_height - 20),
                    radius=20,
                    fill=colors["panel"],
                    outline=colors["panel_border"],
                    width=3,
                )
                draw.text(
                    (x + 24, tile_y + 20),
                    (
                        f"{number_by_label[label]:0{ordinal_width}d}. "
                        f"{_display_label(label)}"
                    ),
                    font=label_font,
                    fill=colors["title"],
                )
                record = records[label]
                width = int(record.get("width", 0) or 0)
                height = int(record.get("height", 0) or 0)
                draw.text(
                    (x + 24, tile_y + 68),
                    f"{width:,} × {height:,} px · {record.get('widget', 'Qt surface')}",
                    font=tile_meta_font,
                    fill=colors["muted"],
                )
                preview_box = (
                    x + 22,
                    tile_y + 110,
                    x + cell_width - 22,
                    tile_y + cell_height - 40,
                )
                draw.rounded_rectangle(
                    preview_box,
                    radius=12,
                    fill=colors["preview"],
                    outline=colors["preview_outline"],
                    width=3,
                )
                with Image.open(Path(str(record["path"]))) as source:
                    source = ImageOps.exif_transpose(source).convert("RGB")
                    max_width = preview_box[2] - preview_box[0] - preview_inset * 2
                    max_height = preview_box[3] - preview_box[1] - preview_inset * 2
                    preview = ImageOps.contain(
                        source,
                        (min(source.width, max_width), min(source.height, max_height)),
                        method=Image.Resampling.LANCZOS,
                    )
                preview_x = preview_box[0] + (preview_box[2] - preview_box[0] - preview.width) // 2
                preview_y = preview_box[1] + preview_inset
                draw.rectangle(
                    (
                        preview_x - screenshot_outline_width,
                        preview_y - screenshot_outline_width,
                        preview_x + preview.width + screenshot_outline_width - 1,
                        preview_y + preview.height + screenshot_outline_width - 1,
                    ),
                    outline=colors["screenshot_outline"],
                    width=screenshot_outline_width,
                )
                sheet.paste(preview, (preview_x, preview_y))
            y += math.ceil(len(labels) / columns) * cell_height + group_gap

        slug = _page_slug(page)
        output = set_dir / f"{page_number:02d}-{slug}.png"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Anki Garden release", version)
        metadata.add_text("Package SHA-256", package_sha256)
        metadata.add_text("Capture manifest", str(payload.get("manifest", "")))
        metadata.add_text("Contact sheet page", f"{page_number} of {len(page_groups)}")
        metadata.add_text("surface_ids", _canonical_json_text(surface_ids))
        metadata.add_text(
            "surface_identity_map",
            _canonical_json_text(surface_identity_map),
        )
        for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
            metadata.add_text(
                identity_field,
                _canonical_json_text(identity_field_maps[identity_field]),
            )
        sheet.save(output, format="PNG", optimize=True, pnginfo=metadata)
        with Image.open(output) as rendered:
            rendered.verify()
        outputs.append(output)
        page_index_records.append(
            {
                "file": output.name,
                "groups": [name for name, _labels in page],
                "page": page_number,
                **identity_field_maps,
                "surface_identity_map": surface_identity_map,
                "surface_ids": surface_ids,
                "surface_count": page_surface_count,
            }
        )

    index_path = set_dir / "contact-sheet-set.json"
    index_payload = {
        "capture_manifest": str(payload.get("manifest", "")),
        "complete": True,
        "package_sha256": package_sha256,
        "package_version": version,
        "page_count": len(outputs),
        "pages": page_index_records,
        "surface_count": expected_count,
    }
    index_path.write_text(
        json.dumps(index_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return set_dir, outputs, index_path


def _validated_stamp(match: re.Match[str] | None) -> str | None:
    if match is None:
        return None
    stamp = match.group("stamp")
    try:
        parsed = datetime.strptime(stamp, CAPTURE_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return stamp if parsed.strftime(CAPTURE_TIMESTAMP_FORMAT) == stamp else None


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_complete_png(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        if path.stat().st_size < len(PNG_SIGNATURE) + len(PNG_IEND):
            return False
        with path.open("rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                return False
            handle.seek(-len(PNG_IEND), os.SEEK_END)
            return handle.read(len(PNG_IEND)) == PNG_IEND
    except OSError:
        return False


def _complete_contact_sheet_stamp(path: Path) -> str | None:
    if path.is_symlink():
        return None
    if path.is_file():
        stamp = _validated_stamp(LEGACY_CONTACT_SHEET_NAME.fullmatch(path.name))
        return stamp if stamp is not None and _is_complete_png(path) else None
    if not path.is_dir():
        return None

    match = CONTACT_SHEET_SET_NAME.fullmatch(path.name)
    stamp = _validated_stamp(match)
    if match is None or stamp is None:
        return None
    payload = _load_json_object(path / "contact-sheet-set.json")
    if payload is None or payload.get("complete") is not True:
        return None

    package_version = payload.get("package_version")
    if not isinstance(package_version, str) or not package_version.strip():
        return None
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", package_version).strip("-_") or "unknown"
    if match.group("version") != safe_version:
        return None
    package_sha256 = payload.get("package_sha256")
    if not isinstance(package_sha256, str) or PACKAGE_SHA256.fullmatch(package_sha256) is None:
        return None
    capture_manifest = payload.get("capture_manifest")
    if not isinstance(capture_manifest, str) or not capture_manifest.strip():
        return None

    page_count = payload.get("page_count")
    surface_count = payload.get("surface_count")
    pages = payload.get("pages")
    if (
        type(page_count) is not int
        or page_count < 1
        or type(surface_count) is not int
        or surface_count < 1
        or not isinstance(pages, list)
        or len(pages) != page_count
    ):
        return None

    files: list[str] = []
    counted_surfaces = 0
    for expected_page, page in enumerate(pages, start=1):
        if not isinstance(page, dict) or page.get("page") != expected_page:
            return None
        page_surfaces = page.get("surface_count")
        if type(page_surfaces) is not int or page_surfaces < 1:
            return None
        counted_surfaces += page_surfaces
        filename = page.get("file")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() != ".png"
            or filename in files
            or not _is_complete_png(path / filename)
        ):
            return None
        files.append(filename)
    if counted_surfaces != surface_count:
        return None
    actual_pngs = {
        child.name
        for child in path.iterdir()
        if not child.is_symlink()
        and child.is_file()
        and child.suffix.lower() == ".png"
    }
    return stamp if actual_pngs == set(files) else None


def enforce_contact_sheet_retention(
    contact_dir: Path,
    *,
    keep: int = CONTACT_SHEET_RETENTION,
) -> tuple[list[Path], list[Path]]:
    """Inventory complete sheet sets without deleting presentation evidence.

    Superseded sets are removed only by the explicit, evidence-backed release
    cleanup after the replacement full set has passed independent validation.
    """

    del keep
    candidates: list[tuple[str, Path]] = []
    for path in contact_dir.iterdir():
        stamp = _complete_contact_sheet_stamp(path)
        if stamp is not None:
            candidates.append((stamp, path))
    newest_first = sorted(
        candidates,
        key=lambda item: (item[0], item[1].name),
        reverse=True,
    )
    retained = [path for _stamp, path in newest_first]
    return retained, []


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=8)
        return
    except subprocess.TimeoutExpired:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


def zip_capture(
    capture_dir: Path,
    output_root: Path,
    stamp: str,
    *,
    package: Path,
) -> Path:
    archive_path = output_root / f"anki-garden-ui-faces-{stamp}.zip"
    excluded = package.resolve()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(capture_dir.rglob("*")):
            if path.is_file() and path.resolve() != excluded:
                archive.write(path, path.relative_to(output_root))
    return archive_path


def _path_from_report(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        return None
    return path


def _complete_capture_stamp(path: Path, output_root: Path) -> str | None:
    if path.is_symlink() or not path.is_dir():
        return None
    match = CAPTURE_SEQUENCE_NAME.fullmatch(path.name)
    stamp = _validated_stamp(match)
    if stamp is None:
        return None
    report = _load_json_object(path / "capture-report.json")
    if report is None or report.get("capture_complete") is not True:
        return None

    capture_contract = report.get("capture_contract_version")
    screenshot_count = report.get("screenshot_count")
    warning_count = report.get("text_layout_warning_count")
    screenshots = report.get("screenshots")
    package_sha256 = report.get("package_sha256")
    if (
        type(capture_contract) is not int
        or capture_contract < 2
        or type(screenshot_count) is not int
        or screenshot_count < 1
        or type(warning_count) is not int
        or warning_count < 0
        or not isinstance(screenshots, list)
        or len(screenshots) != screenshot_count
        or not isinstance(package_sha256, str)
        or PACKAGE_SHA256.fullmatch(package_sha256) is None
        or not isinstance(report.get("package_version"), str)
        or not str(report.get("package_version", "")).strip()
        or not isinstance(report.get("capture_groups"), list)
        or not report.get("capture_groups")
        or report.get("quality_status") not in {"clean", "review-required"}
    ):
        return None

    run_root = path.resolve()
    manifest = _path_from_report(report.get("manifest"))
    if (
        manifest is None
        or manifest.is_symlink()
        or not manifest.is_file()
        or run_root not in manifest.resolve().parents
    ):
        return None
    resolved_screenshots: list[Path] = []
    for value in screenshots:
        screenshot = _path_from_report(value)
        if (
            screenshot is None
            or screenshot.is_symlink()
            or not _is_complete_png(screenshot)
            or run_root not in screenshot.resolve().parents
        ):
            return None
        resolved_screenshots.append(screenshot)
    if len(resolved_screenshots) != len(
        {screenshot.resolve() for screenshot in resolved_screenshots}
    ):
        return None

    archive = _path_from_report(report.get("archive"))
    expected_archive = output_root / f"{CAPTURE_ARCHIVE_PREFIX}{stamp}.zip"
    if (
        archive is None
        or archive.is_symlink()
        or archive.resolve() != expected_archive.resolve()
        or expected_archive.is_symlink()
        or not expected_archive.is_file()
    ):
        return None
    return stamp


def enforce_capture_retention(
    output_root: Path,
    keep: int = CONTACT_SHEET_RETENTION,
) -> tuple[list[Path], list[Path], list[Path]]:
    """Inventory complete capture runs while preserving every raw artifact."""

    del keep

    complete: list[tuple[str, Path]] = []
    for path in output_root.iterdir():
        stamp = _complete_capture_stamp(path, output_root)
        if stamp is not None:
            complete.append((stamp, path))

    newest_first = sorted(
        complete,
        key=lambda item: (item[0], item[1].name),
        reverse=True,
    )
    retained = [path for _stamp, path in newest_first]
    return retained, [], []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--anki-version", default="26.8")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-secondary-monitor", action="store_true")
    arguments = parser.parse_args()

    repo = arguments.repo.expanduser().resolve()
    if not (repo / "scripts" / "package_addon.py").is_file() or not (repo / "ankigarden" / "capture_ui_faces.py").is_file():
        raise CaptureError(f"{repo} is not an Anki Garden repository with UI capture support")
    production_package = repo / "dist" / "anki_garden.ankiaddon"
    if production_package.is_symlink() or not production_package.is_file():
        raise CaptureError(
            "Build the exact production archive before capture: "
            f"{production_package}"
        )
    production_package = production_package.resolve()

    output_root = (arguments.output_dir or repo / "build" / "ui-face-captures").expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = output_root / f"capture-sequence-{stamp}"
    capture_dir.mkdir(parents=True, exist_ok=False)
    log_path = capture_dir / "anki.log"

    prepare = Path.home() / ".codex" / "skills" / "launch-isolated-anki" / "scripts" / "prepare_fast_run.py"
    if not prepare.is_file():
        raise CaptureError(f"Missing isolated-Anki helper: {prepare}")

    python = command_python(repo)
    package, package_id, package_manifest = archive_package(
        repo,
        python,
        capture_dir / "anki_garden_capture.ankiaddon",
    )
    package_sha256 = file_hash(package)
    derivative = capture_derivative_report(repo, production_package, package)
    if derivative["capture_archive_sha256"] != package_sha256:
        raise CaptureError("Capture derivative report does not match the capture archive")
    production_package_sha256 = str(derivative["production_archive_sha256"])
    helper = [sys.executable, str(prepare)]
    seed_status = json_command(helper + ["seed-status", "--anki-version", arguments.anki_version], cwd=repo)
    if seed_status.get("status") != "ready":
        raise CaptureError(f"The isolated Anki seed is not ready: {seed_status}")

    profile = f"Capture Sequence {stamp}"
    created = json_command(
        helper + ["create-run", "--anki-version", arguments.anki_version, "--profile", profile],
        cwd=repo,
    )
    run_root = Path(str(created["run_root"])).resolve()
    extract_package(package, run_root / "addons21" / package_id)
    set_disposable_ui_scale(run_root)
    prelaunch = json_command(helper + ["verify-prelaunch", "--run-root", str(run_root)], cwd=repo)
    if prelaunch.get("status") != "prelaunch-ready":
        raise CaptureError(f"The isolated Anki run is not ready: {prelaunch}")

    launch = created["launch"]
    environment = os.environ.copy()
    environment.pop("ANKI_GARDEN_SKIP_STARTUP", None)
    environment.update({str(key): str(value) for key, value in launch["env"].items()})
    environment.update(
        {
            "ANKI_GARDEN_CAPTURE_UI_FACES": "1",
            "ANKI_GARDEN_CAPTURE_DIR": str(capture_dir),
            "ANKI_GARDEN_UI_CAPTURE_DIR": str(capture_dir),
            "ANKI_GARDEN_CAPTURE_PROFILE": "representative",
            "ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE": "1",
            "ANKI_GARDEN_CAPTURE_SECOND_MONITOR": "0" if arguments.no_secondary_monitor else "1",
            "QT_SCALE_FACTOR": str(CAPTURE_UI_SCALE),
        }
    )

    process: subprocess.Popen[str] | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [str(item) for item in launch["argv"]],
                cwd=repo,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + max(30, arguments.timeout)
            manifest: Path | None = None
            while time.monotonic() < deadline:
                manifest = find_manifest(capture_dir)
                if manifest is not None:
                    payload, screenshots, groups = validate_manifest(manifest)
                    break
                if process.poll() is not None:
                    raise CaptureError(f"Anki exited before capture completed; see {log_path}")
                time.sleep(0.5)
            else:
                raise CaptureError(f"Capture timed out after {arguments.timeout} seconds; see {log_path}")
    finally:
        if process is not None:
            stop_process(process)

    if file_hash(package) != package_sha256:
        raise CaptureError("Capture package changed while the UI capture was running")
    if file_hash(production_package) != production_package_sha256:
        raise CaptureError("Production package changed while the UI capture was running")
    payload["manifest"] = str(manifest)
    contact_sheet_set, contact_sheets, contact_sheet_index = render_contact_sheets(
        payload=payload,
        groups=groups,
        package_manifest=package_manifest,
        package_sha256=package_sha256,
        output_root=output_root,
        stamp=stamp,
    )
    release_validation = json_command(
        [
            python,
            "scripts/validate_ui_capture.py",
            str(manifest),
            "--capture-source",
            str(repo / "ankigarden" / "capture_ui_faces.py"),
            "--contact-sheet-set",
            str(contact_sheet_index),
        ],
        cwd=repo,
    )
    if release_validation.get("status") != "valid":
        raise CaptureError("Independent release capture validation did not pass")
    final_derivative = capture_derivative_report(
        repo,
        production_package,
        package,
    )
    if final_derivative != derivative:
        raise CaptureError(
            "Production or capture package changed before the evidence report"
        )
    derivative = final_derivative
    retained_contact_sheet_sets, pruned_contact_sheet_sets = enforce_contact_sheet_retention(
        contact_sheet_set.parent
    )
    text_layout_warning_count = len(payload.get("text_layout_warnings") or [])
    quality_status = "review-required" if text_layout_warning_count else "clean"
    archive_path = output_root / f"anki-garden-ui-faces-{stamp}.zip"
    report = {
        "archive": str(archive_path),
        "capture_complete": True,
        "capture_contract_version": payload.get("capture_contract_version"),
        **_capture_display_report_fields(payload),
        "capture_groups": [
            {"name": name, "labels": labels}
            for name, labels in groups
        ],
        "contact_sheet": str(contact_sheets[0]),
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_index": str(contact_sheet_index),
        "contact_sheet_set": str(contact_sheet_set),
        "contact_sheets": [str(path) for path in contact_sheets],
        "contact_sheet_retention": CONTACT_SHEET_RETENTION,
        "manifest": str(manifest),
        "package": str(package),
        "package_derivative": derivative,
        "package_sha256": package_sha256,
        "package_version": str(package_manifest.get("human_version", "unknown")),
        "production_package": str(production_package),
        "production_package_sha256": production_package_sha256,
        "pruned_contact_sheet_sets": [str(path) for path in pruned_contact_sheet_sets],
        "quality_status": quality_status,
        "requested_scale_factor": payload.get("requested_scale_factor"),
        "release_validation": release_validation,
        "retained_contact_sheet_sets": [str(path) for path in retained_contact_sheet_sets],
        "screenshot_count": len(screenshots),
        "screenshots": [str(path) for path in screenshots],
        "text_layout_warning_count": text_layout_warning_count,
    }
    report_path = capture_dir / "capture-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive = zip_capture(
        capture_dir,
        output_root,
        stamp,
        package=package,
    )
    retained_capture_sets, pruned_capture_sets, pruned_capture_archives = (
        enforce_capture_retention(output_root)
    )
    report.update(
        {
            "capture_retention": CONTACT_SHEET_RETENTION,
            "pruned_capture_archives": [
                str(path) for path in pruned_capture_archives
            ],
            "pruned_capture_sets": [str(path) for path in pruned_capture_sets],
            "retained_capture_sets": [str(path) for path in retained_capture_sets],
        }
    )
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    archive = zip_capture(
        capture_dir,
        output_root,
        stamp,
        package=package,
    )
    print(
        json.dumps(
            {
                "archive": str(archive),
                "capture_dir": str(capture_dir),
                "capture_complete": True,
                **_capture_display_report_fields(report),
                "contact_sheet": str(contact_sheets[0]),
                "contact_sheet_count": len(contact_sheets),
                "contact_sheet_index": str(contact_sheet_index),
                "contact_sheet_set": str(contact_sheet_set),
                "contact_sheets": report["contact_sheets"],
                "contact_sheet_retention": CONTACT_SHEET_RETENTION,
                "capture_retention": CONTACT_SHEET_RETENTION,
                "manifest": str(manifest),
                "package": str(package),
                "package_derivative": derivative,
                "package_sha256": package_sha256,
                "package_version": report["package_version"],
                "production_package": str(production_package),
                "production_package_sha256": production_package_sha256,
                "pruned_contact_sheet_sets": report["pruned_contact_sheet_sets"],
                "pruned_capture_archives": report["pruned_capture_archives"],
                "pruned_capture_sets": report["pruned_capture_sets"],
                "quality_status": quality_status,
                "report": str(report_path),
                "requested_scale_factor": report["requested_scale_factor"],
                "release_validation": release_validation,
                "retained_contact_sheet_sets": report["retained_contact_sheet_sets"],
                "retained_capture_sets": report["retained_capture_sets"],
                "screenshot_count": report["screenshot_count"],
                "status": "completed",
                "text_layout_warning_count": text_layout_warning_count,
            },
            sort_keys=True,
        )
    )
    return 0


def _repository_owned_main() -> int:
    """Delegate orchestration to the checked-in v27 runner, or fail closed."""

    repo = Path.cwd()
    for index, argument in enumerate(sys.argv[1:], start=1):
        if argument == "--repo" and index + 1 < len(sys.argv):
            repo = Path(sys.argv[index + 1])
            break
        if argument.startswith("--repo="):
            repo = Path(argument.split("=", 1)[1])
            break
    delegate = repo.expanduser().resolve() / "scripts" / "capture_sequence.py"
    if not delegate.is_file():
        raise CaptureError(
            "The repository-owned v27 capture runner is required: "
            f"{delegate}"
        )
    os.environ["ANKI_GARDEN_CAPTURE_SKILL_RUNNER"] = str(Path(__file__).resolve())
    __import__("runpy").run_path(str(delegate), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_repository_owned_main())
    except (CaptureError, subprocess.CalledProcessError, OSError) as error:
        print(json.dumps({"error": str(error), "status": "failed"}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
