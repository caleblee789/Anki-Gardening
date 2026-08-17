from __future__ import annotations

import copy
import json
import struct
import zlib
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image, ImageOps, PngImagePlugin

from scripts.validate_ui_capture import (
    CaptureValidationError,
    expected_contact_sheet_pages,
    expected_contact_sheet_dimensions,
    expected_contact_sheet_page_groups,
    expected_resize_geometry_acceptance,
    load_capture_contract,
    load_dialog_scroll_capture_coverage,
    load_expected_renderer_families,
    load_expected_resize_layout_modes,
    load_expected_state_evidence_contracts,
    validate_capture_manifest,
    validate_contact_sheet_set,
)


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SOURCE = ROOT / "ankigarden" / "capture_ui_faces.py"
_PNG_CACHE: dict[tuple[int, int, int, bool], bytes] = {}


def _png_bytes(
    width: int,
    height: int,
    *,
    marker: int = 0,
    rich_content: bool = True,
) -> bytes:
    cache_key = (width, height, marker, rich_content)
    cached = _PNG_CACHE.get(cache_key)
    if cached is not None:
        return cached

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind)
        checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    if rich_content:
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
        row_patterns = tuple(
            bytes(((x // 8 + phase) % 8) * 31 for x in range(width))
            for phase in range(8)
        )
        first_row = bytearray(row_patterns[0])
        for bit in range(min(24, width)):
            if marker & (1 << bit):
                first_row[bit] = 255
        rows = [b"\x00" + bytes(first_row)]
        rows.extend(
            b"\x00" + row_patterns[(y // 8) % 8]
            for y in range(1, height)
        )
        scanlines = b"".join(rows)
    else:
        ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
        row_bytes = (width + 7) // 8
        first_row = bytearray(row_bytes)
        for bit in range(min(24, width)):
            if marker & (1 << bit):
                first_row[bit // 8] |= 1 << (7 - bit % 8)
        scanlines = b"\x00" + bytes(first_row)
        if height > 1:
            scanlines += (b"\x00" + bytes(row_bytes)) * (height - 1)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )
    _PNG_CACHE[cache_key] = payload
    return payload


def _png_with_corrupt_idat(width: int, height: int) -> bytes:
    payload = bytearray(_png_bytes(width, height))
    offset = 8
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = bytes(payload[offset + 4 : offset + 8])
        if kind == b"IDAT":
            data_start = offset + 8
            payload[data_start : data_start + length] = b"\x00" * length
            checksum = zlib.crc32(kind)
            checksum = zlib.crc32(
                payload[data_start : data_start + length], checksum
            ) & 0xFFFFFFFF
            payload[data_start + length : data_start + length + 4] = struct.pack(
                ">I", checksum
            )
            return bytes(payload)
        offset += length + 12
    raise AssertionError("test PNG had no IDAT chunk")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _valid_capture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    contract = load_capture_contract(CAPTURE_SOURCE)
    renderer_families = load_expected_renderer_families(
        CAPTURE_SOURCE,
        contract=contract,
    )
    resize_layout_modes = load_expected_resize_layout_modes(CAPTURE_SOURCE)
    state_contracts = load_expected_state_evidence_contracts(
        CAPTURE_SOURCE,
        contract=contract,
    )
    scroll_coverage = load_dialog_scroll_capture_coverage(
        CAPTURE_SOURCE,
        contract=contract,
    )
    scroll_by_label = {
        label: (surface, semantic)
        for surface, labels in scroll_coverage.items()
        for label, semantic in labels.items()
    }
    screenshots: list[str] = []
    records: list[dict[str, object]] = []
    for capture_id, label in enumerate(contract.labels, start=1):
        path = tmp_path / f"{capture_id:02d}-{label}.png"
        fixture_source = f"ordered-step-{capture_id:03d}:fixture"
        family = renderer_families[label]
        state_contract = state_contracts[label]
        expected_profile = state_contract["profile"]
        logical_size = (
            tuple(expected_profile["declared_client_size"])
            if label in resize_layout_modes
            else (620, 520)
            if label == "display-scaling-200-qt-representative"
            else (100, 100)
        )
        dpr = 1.0
        physical_size = (
            round(logical_size[0] * dpr),
            round(logical_size[1] * dpr),
        )
        path.write_bytes(
            _png_bytes(*physical_size, marker=capture_id)
        )
        screenshots.append(str(path))
        postcondition_kind = state_contract["kind"]
        postcondition_facts = {
            fact_name: True
            for fact_name in state_contract["required_facts"]
        }
        postcondition_facts.update(state_contract["expected_fact_values"])
        if (
            state_contract["fact_constraints"].get(
                "keyboard_focus_fixture_cleared"
            ) == "focus-cleared-object"
        ):
            postcondition_facts["keyboard_focus_fixture_cleared"] = {
                "focus_owner": "",
                "progress_button_has_focus": False,
            }
        geometry_acceptance: dict[str, object] = {}
        layout_mode = "default"
        if label in resize_layout_modes:
            layout_mode = resize_layout_modes[label]
            geometry_acceptance = expected_resize_geometry_acceptance(
                label=label,
                declared_size=logical_size,
                actual_size=logical_size,
                minimum_size=(100, 100),
                maximum_size=(2000, 2000),
                screen_limited=False,
                constraint_limited=False,
                native_normalized=False,
                normalization_reason="",
            )
            postcondition_facts["layout_mode"] = layout_mode
            postcondition_facts["geometry_acceptance"] = geometry_acceptance
            postcondition_facts["declared_client_size"] = list(logical_size)
            postcondition_facts["requested_client_size"] = list(logical_size)
        fixture_validation = {
            "capture_id": capture_id,
            "fixture_id": label,
            "fixture_source": fixture_source,
            "expected_window_family": family,
            "actual_window_family": family,
            "state_profile": label,
            "postcondition": {
                "profile_id": label,
                "kind": postcondition_kind,
                "facts": postcondition_facts,
                "issues": [],
                "passed": True,
            },
            "passed": True,
        }
        scroll_expectation = scroll_by_label.get(label)
        if scroll_expectation is None:
            dialog_scroll_audit: dict[str, object] = {
                "applicable": False,
                "registered_count": 0,
                "active_count": 0,
                "issues": [],
                "passed": True,
            }
        else:
            surface, page_semantic = scroll_expectation
            dialog_scroll_audit = {
                "applicable": True,
                "surface": surface,
                "expected_page_semantic": page_semantic,
                "actual_page_semantic": page_semantic,
                "scroll_name": f"{surface} scroll",
                "registered_count": 1,
                "active_count": 1,
                "footer_visible": True,
                "footer_height": 64,
                "footer_top": 400,
                "viewport_top": 100,
                "viewport_height": 300,
                "viewport_bottom": 400,
                "declared_clearance": 64,
                "layout_clearance": 64,
                "content_height": 300,
                "content_size_hint_height": 280,
                "content_minimum_size_hint_height": 260,
                "scroll_minimum": 0,
                "scroll_maximum": 0,
                "required_content_height": 300,
                "reachable_content_height": 300,
                "issues": [],
                "passed": True,
            }
        records.append({
            "audit": {
                "fixture_identity": fixture_validation,
                "passed": True,
            },
            "actual_client_size": list(logical_size),
            "capture_id": capture_id,
            "capture_display": "primary",
            "capture_duration_ms": 1.0,
            "constraint_limited": False,
            "declared_client_size": list(logical_size),
            "device_pixel_ratio": dpr,
            "dialog_scroll_audit": dialog_scroll_audit,
            "exact_size_reached": True,
            "fixture_source": fixture_source,
            "fixture_validation": fixture_validation,
            "frame_size": list(logical_size),
            "frame_overhead": [0, 0],
            "geometry_acceptance": geometry_acceptance,
            "geometry_drift_accepted": False,
            "geometry_layout_warnings": [],
            "height": logical_size[1],
            "label": label,
            "layout_mode": layout_mode,
            "native_normalized": False,
            "normalization_reason": "",
            "path": str(path),
            "ready_to_capture_ms": 2.0,
            "requested_client_size": list(logical_size),
            "screen_limited": False,
            "text_layout_warnings": [],
            "transition_path": (
                expected_profile["transition_path"]
                if label in resize_layout_modes
                else "canonical-open"
            ),
            "width": logical_size[0],
            "window_family": family,
        })
    records_by_label = {str(record["label"]): record for record in records}
    scroll_summary_records: list[dict[str, object]] = []
    for surface, labels in scroll_coverage.items():
        for label, semantic in labels.items():
            record_audit = records_by_label[label]["dialog_scroll_audit"]
            assert isinstance(record_audit, dict)
            scroll_summary_records.append({
                "label": label,
                "surface": surface,
                "expected_page_semantic": semantic,
                "actual_page_semantic": semantic,
                **{
                    field: record_audit[field]
                    for field in (
                        "registered_count",
                        "active_count",
                        "footer_height",
                        "viewport_height",
                        "declared_clearance",
                        "layout_clearance",
                        "required_content_height",
                        "reachable_content_height",
                    )
                },
                "issues": [],
                "passed": True,
            })
    payload: dict[str, object] = {
        "capture_contract_version": contract.version,
        "capture_profile": "full",
        "capture_display": "primary",
        "capture_displays": ["primary"],
        "capture_groups": [
            {"name": name, "labels": list(labels)}
            for name, labels in contract.groups
        ],
        "expected_faces": list(contract.labels),
        "screenshots": screenshots,
        "captures": records,
        "text_layout_warnings": [],
        "failures": [],
        "expected_count": len(contract.labels),
        "requested_scale_factor": "1.5",
        "dialog_memory_probe": {
            "status": "measured",
            "cycles": 12,
            "visible_cycles": 12,
            "closed_cycles": 12,
            "cycle_observations": [
                {
                    "cycle": cycle,
                    "visible": True,
                    "closed": True,
                    "dialog_class": "NurseryDialog",
                }
                for cycle in range(1, 13)
            ],
            "passed": True,
            "measurement": "QApplication.allWidgets plus process peak RSS",
            "current_rss_available": False,
            "peak_rss_before_kib": 1000,
            "peak_rss_after_kib": 1004,
            "widget_count_before": 10,
            "widget_count_after": 10,
            "watched_class_counts_before": {
                "NurseryDialog": 0,
                "DialogShell": 1,
                "PlantStoryDialog": 0,
                "GardenDialog": 0,
            },
            "watched_class_counts_after": {
                "NurseryDialog": 0,
                "DialogShell": 1,
                "PlantStoryDialog": 0,
                "GardenDialog": 0,
            },
            "watched_class_delta": {
                "NurseryDialog": 0,
                "DialogShell": 0,
                "PlantStoryDialog": 0,
                "GardenDialog": 0,
            },
        },
        "dialog_memory_probe_complete": True,
        "dialog_scroll_audits": {
            "required": True,
            "required_count": len(scroll_summary_records),
            "records": scroll_summary_records,
            "passed": True,
        },
        "dialog_scroll_audits_complete": True,
        "fixture_validations_complete": True,
        "complete": True,
    }
    manifest = tmp_path / "manifest.json"
    _write_json(manifest, payload)
    return manifest, payload


def _set_resize_geometry(
    payload: dict[str, object],
    *,
    label: str,
    declared: tuple[int, int],
    actual: tuple[int, int],
    screen_limited: bool,
    native_normalized: bool,
    normalization_reason: str,
) -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    index = contract.labels.index(label)
    records = payload["captures"]
    screenshots = payload["screenshots"]
    assert isinstance(records, list)
    assert isinstance(screenshots, list)
    record = records[index]
    assert isinstance(record, dict)
    acceptance = expected_resize_geometry_acceptance(
        label=label,
        declared_size=declared,
        actual_size=actual,
        minimum_size=(100, 100),
        maximum_size=(1000, 1000),
        screen_limited=screen_limited,
        constraint_limited=False,
        native_normalized=native_normalized,
        normalization_reason=normalization_reason,
    )
    record.update({
        "actual_client_size": list(actual),
        "declared_client_size": list(declared),
        "requested_client_size": list(declared),
        "width": actual[0],
        "height": actual[1],
        "frame_size": list(actual),
        "screen_limited": screen_limited,
        "native_normalized": native_normalized,
        "normalization_reason": normalization_reason,
        "exact_size_reached": acceptance["exact"],
        "geometry_drift_accepted": bool(
            acceptance["accepted"] and not acceptance["exact"]
        ),
        "geometry_acceptance": acceptance,
    })
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    facts = postcondition["facts"]
    assert isinstance(facts, dict)
    facts["geometry_acceptance"] = acceptance
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    dpr = float(record["device_pixel_ratio"])
    Path(screenshots[index]).write_bytes(
        _png_bytes(
            round(actual[0] * dpr),
            round(actual[1] * dpr),
            marker=index + 1,
        )
    )


def _valid_contact_sheets(tmp_path: Path, manifest: Path) -> Path:
    contract = load_capture_contract(CAPTURE_SOURCE)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    records = {
        record["label"]: record
        for record in manifest_payload["captures"]
    }
    set_dir = tmp_path / "contact-sheets"
    set_dir.mkdir()
    pages: list[dict[str, object]] = []
    label_pages = expected_contact_sheet_page_groups(contract)
    for page, topology in enumerate(expected_contact_sheet_pages(contract), start=1):
        group_names = [name for name, _count in topology]
        slug = "-".join(
            "".join(character if character.isalnum() else "-" for character in name.lower())
            .replace("--", "-")
            .strip("-")
            for name in (group.replace(" (continued)", "") for group in group_names)
        )
        while "--" in slug:
            slug = slug.replace("--", "-")
        filename = f"{page:02d}-{slug}.png"
        width, height = expected_contact_sheet_dimensions(topology)
        sheet = Image.new("RGB", (width, height), "#081814")
        cell_width = (3000 - 64 * 2 - 32) // 2
        y = 250
        for _group_name, labels in label_pages[page - 1]:
            y += 84
            for group_index, label in enumerate(labels):
                row = group_index // 2
                column = group_index % 2
                x = 64 + column * (cell_width + 32)
                tile_y = y + row * 930
                preview_box = (
                    x + 22,
                    tile_y + 110,
                    x + cell_width - 22,
                    tile_y + 930 - 40,
                )
                with Image.open(Path(records[label]["path"])) as opened:
                    source = ImageOps.exif_transpose(opened).convert("RGB")
                    max_width = preview_box[2] - preview_box[0] - 16
                    max_height = preview_box[3] - preview_box[1] - 16
                    preview = ImageOps.contain(
                        source,
                        (min(source.width, max_width), min(source.height, max_height)),
                        method=Image.Resampling.LANCZOS,
                    )
                preview_x = preview_box[0] + (
                    preview_box[2] - preview_box[0] - preview.width
                ) // 2
                preview_y = preview_box[1] + (
                    preview_box[3] - preview_box[1] - preview.height
                ) // 2
                sheet.paste(preview, (preview_x, preview_y))
            y += ((len(labels) + 1) // 2) * 930 + 30
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Anki Garden release", "2.1.0")
        metadata.add_text("Package SHA-256", "a" * 64)
        metadata.add_text("Capture manifest", str(manifest.resolve()))
        metadata.add_text("Contact sheet page", f"{page} of {len(label_pages)}")
        sheet.save(set_dir / filename, format="PNG", pnginfo=metadata)
        pages.append({
            "file": filename,
            "groups": group_names,
            "page": page,
            "surface_count": sum(count for _name, count in topology),
        })
    index = set_dir / "contact-sheet-set.json"
    _write_json(index, {
        "capture_manifest": str(manifest),
        "complete": True,
        "package_sha256": "a" * 64,
        "package_version": "2.1.0",
        "page_count": len(pages),
        "pages": pages,
        "surface_count": len(contract.labels),
    })
    return index


def test_complete_capture_and_contact_sheet_set_pass_strict_validation(
    tmp_path: Path,
) -> None:
    manifest, _payload = _valid_capture(tmp_path)
    contact_sheets = _valid_contact_sheets(tmp_path, manifest)

    capture_result = validate_capture_manifest(manifest)
    sheet_result = validate_contact_sheet_set(
        contact_sheets,
        manifest_path=manifest,
    )

    assert capture_result["status"] == "valid"
    assert capture_result["capture_count"] == 183
    assert sheet_result == {
        "contact_sheet_set": str(contact_sheets.resolve()),
        "page_count": 24,
        "surface_count": 183,
        "status": "valid",
    }


def test_contact_sheet_topology_is_two_columns_by_five_rows() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    pages = expected_contact_sheet_pages(contract)

    assert [sum(count for _name, count in page) for page in pages] == [
        8, 9, 2, 10, 7, 5, 10, 6, 10, 2, 7, 9, 5, 10, 10, 10, 10, 10,
        9, 8, 10, 10, 4, 2,
    ]
    assert pages[6:10] == (
        (("Release stress — Garden", 10),),
        (("Release stress — Garden (continued)", 6),),
        (("Watering can — all six plots", 10),),
        (("Watering can — all six plots (continued)", 2),),
    )
    assert [expected_contact_sheet_dimensions(page)[1] for page in pages] == [
        4262, 5078, 1358, 5078, 4262, 3218, 5078, 3218, 5078, 1358,
        4148, 5192, 3218, 5078, 5078, 5078, 5078, 5078, 5078, 4148,
        5078, 5078, 2288, 1358,
    ]


def test_renderer_families_are_derived_from_source_for_all_183_faces() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    families = load_expected_renderer_families(CAPTURE_SOURCE, contract=contract)

    assert tuple(families) == contract.labels
    assert Counter(families.values()) == Counter({
        "GardenDashboard": 48,
        "GardenProgressDialog": 25,
        "GardenSettingsDialog": 17,
        "NurseryDialog": 20,
        "AnkiQt": 15,
        "CollectibleDetailDialog": 9,
        "FertilizerDialog": 7,
        "StarterConfirmationDialog": 6,
        "PlantStoryDialog": 6,
        "FertilizerReplacementDialog": 11,
        "SpeciesOverviewDialog": 5,
        "PurchaseConfirmationDialog": 14,
    })
    assert families["popover-plot-6"] == "GardenDashboard"
    assert families["watering-can-garden-plot-6"] == "GardenDashboard"
    assert families["resize-species-overview-large"] == "SpeciesOverviewDialog"
    resize_modes = load_expected_resize_layout_modes(CAPTURE_SOURCE)
    assert len(resize_modes) == 64
    assert resize_modes["resize-dashboard-content-819"] == "compact"
    assert resize_modes["resize-dashboard-content-821"] == "compact"
    assert resize_modes["resize-progress-default"] == "wide"


def test_state_evidence_contracts_are_derived_for_all_183_faces() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    states = load_expected_state_evidence_contracts(
        CAPTURE_SOURCE,
        contract=contract,
    )

    assert tuple(states) == contract.labels
    assert Counter(state["kind"] for state in states.values()) == Counter({
        "resize": 64,
        "dashboard": 35,
        "progress": 17,
        "home": 15,
        "nursery": 15,
        "settings": 10,
        "dialog": 23,
        "collectible-detail": 4,
    })
    assert states["watering-can-overview-plot-6"]["profile"] == {
        "profile_id": "watering-can-overview-plot-6",
        "window_family": "AnkiQt",
        "kind": "home",
        "surface": "overview",
        "fixture_state": "nurtured-active",
        "active_slot": 5,
    }
    assert states["growth-zero"]["profile"]["page"] == "growth"
    assert states["nursery-item-locked"]["profile"]["tab"] == 1
    assert states["nursery-item-locked"]["profile"]["starter_mode"] is False
    assert states["resize-progress-default"]["profile"] == {
        "profile_id": "resize-progress-default",
        "window_family": "GardenProgressDialog",
        "kind": "resize",
        "resize_family": "progress",
        "transition_path": "minimum-to-default",
        "declared_client_size": [940, 680],
        "layout_mode": "wide",
        "canonical_page": "overview",
    }


def test_accessibility_fixture_ownership_and_cleanup_are_source_bound() -> None:
    states = load_expected_state_evidence_contracts(CAPTURE_SOURCE)

    reduced_motion_values = states["reduced-motion-enabled"][
        "expected_fact_values"
    ]
    assert {
        key: reduced_motion_values[key]
        for key in ("reduced_motion_checked", "reduced_motion_config_enabled")
    } == {
        "reduced_motion_checked": True,
        "reduced_motion_config_enabled": True,
    }
    keyboard_values = states["keyboard-focus-state"]["expected_fact_values"]
    assert {
        key: keyboard_values[key]
        for key in (
            "reduced_motion_baseline_restored",
            "keyboard_focus_visible",
            "keyboard_focus_owner",
        )
    } == {
        "reduced_motion_baseline_restored": False,
        "keyboard_focus_visible": True,
        "keyboard_focus_owner": "progress_btn",
    }
    cleanup_labels = (
        "narrow-window-responsive",
        "display-scaling-150",
        "display-scaling-200-qt-representative",
        "resize-dashboard-minimum",
        "resize-dashboard-large",
    )
    for label in cleanup_labels:
        assert states[label]["expected_fact_values"][
            "reduced_motion_baseline_restored"
        ] is False
        assert states[label]["fact_constraints"] == {
            "keyboard_focus_fixture_cleared": "focus-cleared-object",
        }
    assert "reduced_motion_baseline_restored" not in states[
        "resize-settings-minimum"
    ]["required_facts"]
    assert "keyboard_focus_fixture_cleared" not in states[
        "resize-settings-minimum"
    ]["required_facts"]


def test_state_profile_loader_tracks_source_mapping_and_fails_closed(
    tmp_path: Path,
) -> None:
    source = CAPTURE_SOURCE.read_text(encoding="utf-8")
    changed_mapping = source.replace(
        '"growth" if label.startswith("growth-") else',
        '"streak" if label.startswith("growth-") else',
        1,
    )
    changed_source = tmp_path / "changed_capture_ui_faces.py"
    changed_source.write_text(changed_mapping, encoding="utf-8")
    changed = load_expected_state_evidence_contracts(changed_source)
    assert changed["growth-zero"]["profile"]["page"] == "streak"
    assert changed["growth-zero"]["expected_fact_values"]["progress_page"] == "streak"

    unsupported = source.replace(
        "family = expected_capture_window_family(label)",
        "family = tuple([expected_capture_window_family(label)])[0]",
        1,
    )
    unsupported_source = tmp_path / "unsupported_capture_ui_faces.py"
    unsupported_source.write_text(unsupported, encoding="utf-8")
    with pytest.raises(CaptureValidationError, match="unsupported state-profile expression"):
        load_expected_state_evidence_contracts(unsupported_source)

    nested_require = source.replace(
        '        require(\n            "ordered_fixture_label",',
        '        for _ in (0,):\n            require(\n                "ordered_fixture_label",',
        1,
    )
    nested_source = tmp_path / "nested_capture_ui_faces.py"
    nested_source.write_text(nested_require, encoding="utf-8")
    with pytest.raises(CaptureValidationError, match="unsupported For control flow"):
        load_expected_state_evidence_contracts(nested_source)


def test_renderer_source_parser_fails_closed_on_unsupported_declaration(
    tmp_path: Path,
) -> None:
    source = CAPTURE_SOURCE.read_text(encoding="utf-8")
    altered = source.replace(
        '*(f"popover-plot-{slot}" for slot in range(1, 7)),',
        '*(f"popover-plot-{slot}" for slot in sorted((1, 2, 3, 4, 5, 6))),',
    )
    capture_source = tmp_path / "capture_ui_faces.py"
    capture_source.write_text(altered, encoding="utf-8")

    with pytest.raises(CaptureValidationError, match="static range"):
        load_expected_renderer_families(capture_source)


def test_manifest_rejects_incomplete_warning_and_fixture_identity_drift(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    broken = copy.deepcopy(payload)
    broken["complete"] = False
    broken["fixture_validations_complete"] = False
    broken["text_layout_warnings"] = [{"text": "clipped"}]
    broken["failures"] = [{"label": "fixture", "reason": "wrong state"}]
    records = broken["captures"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    fixture["passed"] = False
    _write_json(manifest, broken)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "not marked complete" in message
    assert "fixture_validations_complete is not true" in message
    assert "reports 1 failure" in message
    assert "reports 1 text-layout warning" in message
    assert "fixture validation did not pass" in message


def test_manifest_rejects_renderer_provenance_not_owned_by_source(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record["window_family"] = "WrongDialog"
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    fixture["expected_window_family"] = "WrongDialog"
    fixture["actual_window_family"] = "WrongDialog"
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="source-owned AnkiQt"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_top_level_fixture_source_racing_nested_identity(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[6]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    assert record["fixture_source"] == fixture["fixture_source"]
    record["fixture_source"] = "ordered-step-002:_capture_overview"
    _write_json(manifest, payload)

    with pytest.raises(
        CaptureValidationError,
        match="capture 007 deck-browser-home: fixture sources disagree",
    ):
        validate_capture_manifest(manifest)


def test_manifest_rejects_incomplete_or_mismatched_state_postcondition(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    fixture["state_profile"] = "wrong-profile"
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    postcondition.update({
        "profile_id": "wrong-profile",
        "kind": "unknown-kind",
        "facts": {},
        "issues": ["not-ready"],
        "passed": False,
    })
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "state_profile must match" in message
    assert "postcondition profile_id must match" in message
    assert "postcondition kind must be 'home'" in message
    assert "postcondition facts must be nonempty" in message
    assert "postcondition issues must be empty" in message
    assert "postcondition did not pass" in message


def test_manifest_rejects_resize_postcondition_without_expected_layout_mode(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    resize_index = contract.labels.index("resize-dashboard-content-821")
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[resize_index]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    facts = postcondition["facts"]
    assert isinstance(facts, dict)
    facts["layout_mode"] = "narrow"
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="layout_mode fact must be 'compact'"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_same_renderer_state_schema_substitution(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    zero = records[contract.labels.index("growth-zero")]
    nonzero = records[contract.labels.index("growth-nonzero")]
    assert isinstance(zero, dict) and isinstance(nonzero, dict)
    zero_fixture = zero["fixture_validation"]
    nonzero_fixture = nonzero["fixture_validation"]
    assert isinstance(zero_fixture, dict) and isinstance(nonzero_fixture, dict)
    zero_postcondition = zero_fixture["postcondition"]
    nonzero_postcondition = nonzero_fixture["postcondition"]
    assert isinstance(zero_postcondition, dict) and isinstance(nonzero_postcondition, dict)
    zero_postcondition["facts"] = copy.deepcopy(nonzero_postcondition["facts"])
    zero_audit = zero["audit"]
    assert isinstance(zero_audit, dict)
    zero_audit["fixture_identity"] = copy.deepcopy(zero_fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="postcondition fact schema mismatch"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_accessibility_owner_and_cleanup_state_substitution(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)

    substitutions = (
        ("reduced-motion-enabled", "settings-menu-display"),
        ("keyboard-focus-state", "narrow-window-responsive"),
    )
    for target_label, source_label in substitutions:
        target = records[contract.labels.index(target_label)]
        source = records[contract.labels.index(source_label)]
        assert isinstance(target, dict) and isinstance(source, dict)
        target_fixture = target["fixture_validation"]
        source_fixture = source["fixture_validation"]
        assert isinstance(target_fixture, dict) and isinstance(source_fixture, dict)
        target_postcondition = target_fixture["postcondition"]
        source_postcondition = source_fixture["postcondition"]
        assert isinstance(target_postcondition, dict)
        assert isinstance(source_postcondition, dict)
        target_postcondition["facts"] = copy.deepcopy(source_postcondition["facts"])
        target_audit = target["audit"]
        assert isinstance(target_audit, dict)
        target_audit["fixture_identity"] = copy.deepcopy(target_fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "capture 086 reduced-motion-enabled: postcondition fact schema mismatch" in message
    assert "capture 087 keyboard-focus-state: postcondition fact schema mismatch" in message


def test_manifest_rejects_forged_accessibility_cleanup_fact_value(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[contract.labels.index("narrow-window-responsive")]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    facts = postcondition["facts"]
    assert isinstance(facts, dict)
    facts["keyboard_focus_fixture_cleared"] = {
        "focus_owner": "QPushButton",
        "progress_button_has_focus": True,
    }
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="must prove the Progress button"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_fabricated_resize_size_despite_self_consistent_record(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    label = "resize-dashboard-large"
    _set_resize_geometry(
        payload,
        label=label,
        declared=(100, 100),
        actual=(100, 100),
        screen_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[contract.labels.index(label)]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    facts = postcondition["facts"]
    assert isinstance(facts, dict)
    facts["declared_client_size"] = [100, 100]
    facts["requested_client_size"] = [100, 100]
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="must match source profile"):
        validate_capture_manifest(manifest)


def test_manifest_accepts_provenance_backed_bounded_resize_height_drift(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    _set_resize_geometry(
        payload,
        label="resize-dashboard-content-821",
        declared=(845, 720),
        actual=(845, 600),
        screen_limited=True,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    _write_json(manifest, payload)

    assert validate_capture_manifest(manifest)["status"] == "valid"


def test_manifest_rejects_unexplained_resize_drift(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    _set_resize_geometry(
        payload,
        label="resize-dashboard-content-821",
        declared=(845, 720),
        actual=(845, 600),
        screen_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="unexplained or unsafe"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_breakpoint_resize_width_drift_over_one_pixel(
    tmp_path: Path,
) -> None:
    measured_breakpoint = expected_resize_geometry_acceptance(
        label="purchase-confirmation-breakpoint-low",
        declared_size=(517, 520),
        actual_size=(517, 520),
        minimum_size=(420, 400),
        maximum_size=(820, 660),
        screen_limited=False,
        constraint_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    assert measured_breakpoint["accepted"] is True
    assert measured_breakpoint["breakpoint_fixture"] is True
    manifest, payload = _valid_capture(tmp_path)
    _set_resize_geometry(
        payload,
        label="resize-dashboard-content-821",
        declared=(845, 720),
        actual=(842, 600),
        screen_limited=True,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="unexplained or unsafe"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_scale_display_geometry_layout_and_memory_drift(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["requested_scale_factor"] = "2.0"
    payload["capture_display"] = "secondary"
    payload["capture_displays"] = ["secondary"]
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    probe["status"] = "error"
    probe["cycles"] = 3
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record["layout_mode"] = ""
    record["device_pixel_ratio"] = float("inf")
    record["actual_client_size"] = [101, 100]
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "numeric-equivalent to 1.5" in message
    assert "status must be 'measured'" in message
    assert "cycles must be 12" in message
    assert "actual_client_size must match" in message
    assert "device_pixel_ratio is invalid" in message
    assert "layout_mode is missing" in message
    assert "capture_displays does not match" in message
    assert "capture_display does not match" in message


def test_manifest_rejects_memory_probe_bad_class_delta(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    deltas = probe["watched_class_delta"]
    assert isinstance(deltas, dict)
    deltas["NurseryDialog"] = 1
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="delta for NurseryDialog"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_internally_consistent_nursery_retention(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    after = probe["watched_class_counts_after"]
    deltas = probe["watched_class_delta"]
    assert isinstance(after, dict)
    assert isinstance(deltas, dict)
    after["NurseryDialog"] = 1
    deltas["NurseryDialog"] = 1
    _write_json(manifest, payload)

    with pytest.raises(
        CaptureValidationError,
        match="NurseryDialog delta must be exactly zero",
    ):
        validate_capture_manifest(manifest)


def test_manifest_rejects_incomplete_or_fabricated_memory_cycles(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["dialog_memory_probe_complete"] = False
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    probe["passed"] = False
    probe["visible_cycles"] = 11
    probe["closed_cycles"] = 11
    observations = probe["cycle_observations"]
    assert isinstance(observations, list)
    observations.pop()
    first = observations[0]
    assert isinstance(first, dict)
    first.update({
        "cycle": 2,
        "visible": False,
        "closed": False,
        "dialog_class": "WrongDialog",
        "close_error": "still open",
    })
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "dialog_memory_probe_complete must be true" in message
    assert "dialog_memory_probe passed must be true" in message
    assert "visible_cycles must be 12" in message
    assert "closed_cycles must be 12" in message
    assert "cycle_observations must contain 12 records" in message


def test_manifest_rejects_order_path_and_unowned_png_drift(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    screenshots = payload["screenshots"]
    records = payload["captures"]
    assert isinstance(screenshots, list)
    assert isinstance(records, list)
    screenshots[0], screenshots[1] = screenshots[1], screenshots[0]
    first_record = records[0]
    assert isinstance(first_record, dict)
    first_record["capture_id"] = 99
    (tmp_path / "unowned.png").write_bytes(_png_bytes(100, 100, marker=999))
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "screenshot filename must be" in message
    assert "record path does not match screenshots" in message
    assert "capture_id must be 1" in message
    assert "session contains unowned PNG files" in message


def test_contact_sheet_set_rejects_page_file_and_count_drift(tmp_path: Path) -> None:
    manifest, _payload = _valid_capture(tmp_path)
    index = _valid_contact_sheets(tmp_path, manifest)
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["complete"] = False
    payload["page_count"] += 1
    payload["surface_count"] -= 1
    payload["pages"][0]["surface_count"] -= 1
    payload["pages"][0]["groups"] = ["First run"]
    first_page = index.parent / payload["pages"][0]["file"]
    first_page.write_bytes(_png_bytes(3000, 1))
    (index.parent / "unindexed.png").write_bytes(_png_bytes(100, 100))
    _write_json(index, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_contact_sheet_set(index, manifest_path=manifest)

    message = str(raised.value)
    assert "not marked complete" in message
    assert "page_count does not match" in message
    assert "surface_count must be 183" in message
    assert "pages account for 182 surfaces" in message
    assert "PNG dimensions must be 3000x4262px" in message
    assert "groups do not match deterministic topology" in message
    assert "contains unindexed PNG files" in message


def test_contact_sheet_set_rejects_blank_and_reordered_preview_pixels(
    tmp_path: Path,
) -> None:
    manifest, _payload = _valid_capture(tmp_path)
    index = _valid_contact_sheets(tmp_path, manifest)
    index_payload = json.loads(index.read_text(encoding="utf-8"))
    first_page = index.parent / index_payload["pages"][0]["file"]

    with Image.open(first_page) as opened:
        opened.load()
        metadata = dict(opened.text)
        blank = Image.new("RGB", opened.size, "#081814")
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        pnginfo.add_text(key, value)
    blank.save(first_page, format="PNG", pnginfo=pnginfo)
    with pytest.raises(CaptureValidationError, match="pixels do not match manifest screenshot"):
        validate_contact_sheet_set(index, manifest_path=manifest)

    reordered_root = tmp_path / "reordered"
    reordered_root.mkdir()
    index = _valid_contact_sheets(reordered_root, manifest)
    index_payload = json.loads(index.read_text(encoding="utf-8"))
    first_page = index.parent / index_payload["pages"][0]["file"]
    with Image.open(first_page) as opened:
        opened.load()
        metadata = dict(opened.text)
        reordered = opened.convert("RGB")
    first_box = (724, 784, 824, 884)
    second_box = (2176, 784, 2276, 884)
    first_pixels = reordered.crop(first_box)
    second_pixels = reordered.crop(second_box)
    reordered.paste(second_pixels, first_box[:2])
    reordered.paste(first_pixels, second_box[:2])
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        pnginfo.add_text(key, value)
    reordered.save(first_page, format="PNG", pnginfo=pnginfo)
    with pytest.raises(CaptureValidationError, match="pixels do not match manifest screenshot"):
        validate_contact_sheet_set(index, manifest_path=manifest)


def test_contact_sheet_set_rejects_wrong_release_png_provenance(tmp_path: Path) -> None:
    manifest, _payload = _valid_capture(tmp_path)
    index = _valid_contact_sheets(tmp_path, manifest)
    index_payload = json.loads(index.read_text(encoding="utf-8"))
    first_page = index.parent / index_payload["pages"][0]["file"]
    with Image.open(first_page) as opened:
        opened.load()
        page = opened.convert("RGB")
        metadata = dict(opened.text)
    metadata["Package SHA-256"] = "b" * 64
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        pnginfo.add_text(key, value)
    page.save(first_page, format="PNG", pnginfo=pnginfo)

    with pytest.raises(CaptureValidationError, match="Package SHA-256"):
        validate_contact_sheet_set(index, manifest_path=manifest)


def test_manifest_rejects_truncated_png_even_with_a_valid_signature(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    first_page = Path(screenshots[0])
    first_page.write_bytes(_png_bytes(100, 100)[:24])

    with pytest.raises(CaptureValidationError, match="missing or not a valid PNG"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_crc_valid_png_with_corrupt_idat(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    Path(screenshots[0]).write_bytes(_png_with_corrupt_idat(100, 100))

    with pytest.raises(CaptureValidationError, match="missing or not a valid PNG"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_png_physical_dimensions_beyond_dpr_tolerance(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    Path(screenshots[0]).write_bytes(_png_bytes(102, 100, marker=1))

    with pytest.raises(CaptureValidationError, match="do not match logical size and DPR"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_solid_or_near_blank_decoded_pixels(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    Path(screenshots[0]).write_bytes(
        _png_bytes(100, 100, rich_content=False)
    )

    with pytest.raises(CaptureValidationError, match="screenshot lacks visual content"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_unapproved_duplicate_visual_evidence(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    streak_index = contract.labels.index("streak-reward-earned-next")
    resize_index = contract.labels.index("resize-progress-default")
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    Path(screenshots[resize_index]).write_bytes(
        Path(screenshots[streak_index]).read_bytes()
    )

    with pytest.raises(CaptureValidationError, match="unapproved duplicate visual evidence"):
        validate_capture_manifest(manifest)


def test_manifest_accepts_documented_duplicate_with_required_audit(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    first_index = contract.labels.index("starter-nursery-plants")
    action_index = contract.labels.index("starter-action-above-footer")
    screenshots = payload["screenshots"]
    records = payload["captures"]
    assert isinstance(screenshots, list)
    assert isinstance(records, list)
    Path(screenshots[action_index]).write_bytes(Path(screenshots[first_index]).read_bytes())
    action_record = records[action_index]
    assert isinstance(action_record, dict)
    action_audit = action_record["audit"]
    assert isinstance(action_audit, dict)
    action_audit.update({
        "nursery_footer_clearance_audited": True,
        "catalog_row": "first",
        "action_count": 1,
    })
    _write_json(manifest, payload)

    assert validate_capture_manifest(manifest)["status"] == "valid"


def test_manifest_accepts_qt_proxy_duplicate_with_explicit_provenance(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    scaling_index = contract.labels.index("display-scaling-200-qt-representative")
    resize_index = contract.labels.index("resize-dashboard-minimum")
    screenshots = payload["screenshots"]
    records = payload["captures"]
    assert isinstance(screenshots, list)
    assert isinstance(records, list)
    Path(screenshots[resize_index]).write_bytes(
        Path(screenshots[scaling_index]).read_bytes()
    )
    scaling_record = records[scaling_index]
    assert isinstance(scaling_record, dict)
    scaling_audit = scaling_record["audit"]
    assert isinstance(scaling_audit, dict)
    scaling_audit.update({
        "representative_kind": "deterministic-qt-logical-viewport",
        "effective_scale_percent": 200,
        "os_display_scaling_changed": False,
    })
    _write_json(manifest, payload)

    assert validate_capture_manifest(manifest)["status"] == "valid"


def test_manifest_rejects_scroll_geometry_and_collection_page_drift(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    index = contract.labels.index("progress-collection")
    record = records[index]
    assert isinstance(record, dict)
    scroll_audit = record["dialog_scroll_audit"]
    assert isinstance(scroll_audit, dict)
    scroll_audit.update({
        "actual_page_semantic": "GardenProgressDialog:overview",
        "declared_clearance": 63,
        "content_height": 301,
        "required_content_height": 301,
    })
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "actual-scroll-page-semantic-mismatch" in message
    assert "footer-clearance-mismatch" in message
    assert "unreachable-scroll-content" in message


def test_manifest_accepts_preferred_scroll_height_above_reachable_minimum(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    record = next(
        item
        for item in payload["captures"]
        if item["dialog_scroll_audit"].get("applicable") is True
    )
    audit = record["dialog_scroll_audit"]
    audit["content_size_hint_height"] = 360
    _write_json(manifest, payload)

    assert validate_capture_manifest(manifest)["status"] == "valid"


def test_manifest_rejects_missing_positive_scroll_summary(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["dialog_scroll_audits_complete"] = False
    summary = payload["dialog_scroll_audits"]
    assert isinstance(summary, dict)
    summary["passed"] = False
    summary["records"] = []
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "dialog_scroll_audits_complete must be true" in message
    assert "dialog_scroll_audits passed must be true" in message
    assert "dialog_scroll_audits records must contain" in message
