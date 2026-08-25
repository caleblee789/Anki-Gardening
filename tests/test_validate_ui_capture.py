from __future__ import annotations

import copy
import hashlib
import json
import struct
import zlib
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageOps, PngImagePlugin

from scripts.capture_evidence import (
    assemble_capture_manifest,
    plan_incremental_capture,
    surface_validation_report,
)
from scripts.validate_ui_capture import (
    CONTACT_SHEET_OUTLINE_WIDTH,
    CONTACT_SHEET_PREVIEW_FRAME_FILL,
    CONTACT_SHEET_PREVIEW_FRAME_OUTLINE,
    CONTACT_SHEET_PREVIEW_INSET,
    CONTACT_SHEET_SCREENSHOT_OUTLINE,
    CaptureValidationError,
    expected_contact_sheet_pages,
    expected_contact_sheet_dimensions,
    expected_contact_sheet_page_groups,
    expected_resize_geometry_acceptance,
    load_capture_contract,
    load_capture_layout_contract,
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
    completion = path.parent / "capture-complete.json"
    if path.name == "manifest.json" and completion.is_file():
        completion_payload = json.loads(completion.read_text(encoding="utf-8"))
        completion_payload["manifest_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        completion.write_text(
            json.dumps(completion_payload, indent=2) + "\n",
            encoding="utf-8",
        )


def _valid_visual_contract(
    label: str,
    state_kind: str,
    window_family: str,
) -> tuple[dict[str, object], dict[str, object]]:
    if state_kind in {"home", "reviewer"}:
        visual: dict[str, object] = {
            "applicable": False,
            "controls": [],
            "close_icons": [],
            "primary_action_count": 0,
            "visible_horizontal_scrollbars": [],
            "largest_unexplained_gap": 0,
            "screen_contained": True,
            "popover": {"applicable": False, "passed": True},
            "issues": [],
            "passed": True,
        }
    else:
        requires_inline_close = window_family != "GardenDashboard"
        close_control = {
            "text": "",
            "accessible_name": "Close dialog",
            "bounds": [68, 4, 28, 28],
            "icon_only": True,
            "visual_size": 28,
            "icon_size": [14, 14],
            "size_passed": True,
            "contained": True,
            "footer_action": False,
            "text_width": 0,
            "available_text_width": 0,
            "text_fit_passed": True,
        }
        visual = {
            "applicable": True,
            "controls": [close_control] if requires_inline_close else [],
            "control_sizes_passed": True,
            "requires_inline_close": requires_inline_close,
            "close_icons": [{
                "accessible_name": "Close dialog",
                "bounds": [68, 4, 28, 28],
                "glyph_pixels_present": True,
                "capture_pixels_present": True,
                "passed": True,
            }] if requires_inline_close else [],
            "close_icons_passed": True,
            "primary_actions": [],
            "primary_action_count": 0,
            "primary_action_groups": [],
            "max_primary_actions_per_group": 0,
            "footer_actions": [],
            "footer_actions_contained": True,
            "action_text_fits": True,
            "visible_horizontal_scrollbars": [],
            "largest_unexplained_gap": 0,
            "screen_contained": True,
            "popover": {
                "applicable": label.startswith("popover-plot-"),
                "contained_in_scene": True,
                "page_scroll_value": 0,
                "passed": True,
            },
            "issues": [],
            "passed": True,
        }

    audit: dict[str, object] = {"visual_contract": copy.deepcopy(visual)}
    if state_kind == "home":
        rendered_text = (
            "Anki Garden Loading garden..."
            if label == "home-preview-loading" else
            "Anki Garden Garden preview unavailable Open Garden Try again"
            if label == "home-preview-error" else
            "Garden Moonlit Garden Bonsai Seed Growth 25 of 100 "
            "Ready to nurture Open Garden"
        )
        normal_open_action = not label.startswith("starter-") and label != (
            "home-preview-loading"
        )
        audit["compact_home_copy"] = {
            "rendered_text": rendered_text,
            "banned_terms": [],
            "compact_fields_present": True,
            "support_text": "Bonsai · Seed · 25 / 100 Growth",
            "action_text": "Open Garden" if normal_open_action else "Choose starter",
            "action_width": 112 if normal_open_action else None,
            "action_height": 36 if normal_open_action else None,
            "information_model_passed": True,
            "geometry_passed": True,
            "passed": True,
        }
    if label == "full-garden":
        audit["steady_state_visual"] = {
            "overlay_free": True,
            "visible_overlays": [],
            "scene_contained": True,
            "onboarding_step": "done",
            "page_scroll_value": 0,
            "passed": True,
        }
    if label == "progress-overview-redirect-growth":
        audit["direct_growth_visual"] = {
            "label": "Rewards and charges",
            "amount": 31,
            "label_bounds": [10, 10, 100, 24],
            "value_bounds": [120, 10, 40, 24],
            "label_contained": True,
            "value_contained": True,
            "passed": True,
        }
    if label == "collection-preview-restored":
        audit["restored_preview_visual"] = {
            "text": "Preview reset.",
            "visible": True,
            "bounds": [20, 20, 300, 40],
            "contained": True,
            "passed": True,
        }
        audit["restored_preview_dirty_cleared"] = True
    if label == "nursery-item-owned":
        contained = {
            "bounds": [10, 10, 300, 80],
            "container_size": [900, 600],
            "visible": True,
            "intersects": True,
            "contained": True,
        }
        audit["owned_item_visual"] = {
            "item_id": "dev_bonsai",
            "item_name": "Bonsai Plant",
            "action": "Store plant",
            "card": copy.deepcopy(contained),
            "title": copy.deepcopy(contained),
            "action_bounds": copy.deepcopy(contained),
            "passed": True,
        }
    if state_kind == "reviewer":
        width = 360 if label == "reviewer-find-stacked-sync" else 344
        height = 74
        audit["reviewer_overlay_geometry"] = {
            "parent_is_reviewer_webview": True,
            "overlay_bounds": [604, 16, width, height],
            "viewport_size": [1000, 700],
            "viewport_contained": True,
            "width": width,
            "height": height,
            "size_in_range": True,
            "control_rects": [{
                "name": "reviewer-answer-and-toolbar-reserved-band",
                "bounds": [0, 572, 1000, 128],
                "source": "reviewer-viewport-contract",
            }],
            "minimum_control_clearance": 460,
            "passed": True,
        }
        audit["required_overlay_pixels_present"] = True
    if label == "missing-artwork-graphical-fallback":
        types = ["plant", "fertilizer", "weather", "scenery", "growth-charge"]
        contained = {
            "bounds": [5, 5, 100, 100],
            "container_size": [900, 600],
            "visible": True,
            "intersects": True,
            "contained": True,
        }
        entries = []
        for artwork_type in types:
            entries.append({
                "type": artwork_type,
                "source_path": f"/capture-missing/{artwork_type}.webp",
                "accessible_name": f"{artwork_type} preview",
                "accessible_description": "Artwork unavailable; fallback shown.",
                "semantic_role": "missing-art",
                "graphic_present": True,
                "aspect_ratio_preserved": True,
                "diagnostic_path_logged": True,
                "passed": True,
            })
        audit["missing_artwork_matrix"] = {
            "types": types,
            "entries": entries,
            "missing_source_paths": {
                artwork_type: f"/capture-missing/{artwork_type}.webp"
                for artwork_type in types
            },
            "diagnostic_log_fingerprints": [
                [
                    artwork_type.replace("-", "_"),
                    artwork_type,
                    f"/capture-missing/{artwork_type}.webp",
                ]
                for artwork_type in types
            ],
            "visible_card": copy.deepcopy(contained),
            "visible_preview": copy.deepcopy(contained),
            "visible_missing_preview_count": 1,
            "passed": True,
        }
    if label == "collection-environment-mechanics":
        keys = [
            "toolbar",
            "summary_title",
            "summary_selection",
            "edit_appearance",
            "item_title",
            "item_status",
            "effect",
            "mechanics",
        ]
        audit["environment_mechanics_visual"] = {
            "required_keys": keys,
            "required_bounds": [
                {
                    "key": key,
                    "text": (
                        "Available every day\nOnly one weather can be equipped"
                        if key == "mechanics" else key.replace("_", " ")
                    ),
                    "bounds": [10, 10, 200, 30],
                    "container_size": [900, 600],
                    "visible": True,
                    "intersects": True,
                    "contained": True,
                }
                for key in keys
            ],
            "viewport_size": [900, 600],
            "passed": True,
        }
        audit["mechanics_always_visible"] = True
        audit["compact_environment_actions"] = True
    if label == "collection-loadout-persistence-error":
        audit["error_copy"] = (
            "Could not save changes. Your current Garden appearance is unchanged."
        )
        audit["rendered_state"] = {
            "scene_bounds": {
                "bounds": [10, 100, 600, 300],
                "visible": True,
                "contained": True,
            },
            "feedback_bounds": {
                "bounds": [10, 40, 600, 44],
                "visible": True,
                "contained": True,
            },
            "feedback_text": (
                "Could not save changes. Your current Garden appearance is unchanged."
            ),
            "feedback_outside_artwork": True,
            "passed": True,
        }
    rendered_pixel_keys = {
        "full-garden": ["full-garden-scene"],
        "progress-overview-redirect-growth": [
            "direct-growth-label",
            "direct-growth-value",
        ],
        "collection-preview-restored": ["restored-preview-banner"],
        "nursery-item-owned": ["owned-item-card"],
        "missing-artwork-graphical-fallback": ["missing-art-weather"],
        "collection-environment-mechanics": [
            "environment-toolbar",
            "environment-summary-title",
            "environment-summary-selection",
            "environment-edit-appearance",
            "environment-item-title",
            "environment-item-status",
            "environment-effect",
            "environment-mechanics",
        ],
        "collection-loadout-persistence-error": [
            "loadout-preview-scene",
            "loadout-persistence-error",
        ],
    }.get(label, [])
    if rendered_pixel_keys:
        audit["rendered_pixel_evidence"] = {
            "required_keys": rendered_pixel_keys,
            "results": [
                {
                    "key": key,
                    "bounds": [10, 10, 100, 30],
                    "visible": True,
                    "contained": True,
                    "capture_pixels_present": True,
                    "passed": True,
                }
                for key in rendered_pixel_keys
            ],
            "passed": True,
        }
    return visual, audit


def _valid_native_layout_telemetry(
    *,
    label: str,
    window_family: str,
) -> dict[str, object]:
    if window_family in {"AnkiQt", "GardenDashboard"}:
        return {
            "applicable": False,
            "source": "",
            "issues": [],
            "passed": True,
        }
    limits, button_heights, tabular_labels = load_capture_layout_contract(
        CAPTURE_SOURCE
    )
    tabular_required = label in tabular_labels
    tabular_rows = (
        [{
            "widget": "QLabel",
            "objectName": "metric",
            "text": "1,250 Growth",
        }]
        if tabular_required else []
    )
    return {
        "applicable": True,
        "source": "DialogShell.capture_layout_telemetry",
        "clientSurfaceFill": 0.96,
        "nurseryRootOffset": 8 if window_family == "NurseryDialog" else None,
        "contentToFooterGap": 12,
        "maximumActionWidthRatio": 0.32,
        "scrollbars": [],
        "minimumRenderedTextSize": 13.0,
        "tooltipWidgetCount": 1,
        "elidedWidgetCount": 1,
        "elisionWithoutTooltipCount": 0,
        "overflowOwnerCount": 0,
        "clientWidth": 100,
        "clientGutterPx": 4,
        "buttonRecords": [{
            "text": "",
            "buttonSize": "icon",
            "height": 32,
            "width": 32,
            "expectedHeight": 30,
            "expectedOuterHeight": 32,
            "visualControlSize": 30,
            "outerBorderAllowance": 2,
            "renderedTextSize": 13.0,
            "passed": True,
        }],
        "tabularNumeralWidgets": tabular_rows,
        "tabularNumeralWidgetCount": len(tabular_rows),
        "tabularNumeralsRequired": tabular_required,
        "limits": limits,
        "buttonHeights": button_heights,
        "issues": [],
        "passed": True,
    }


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
    environment_digest = "a" * 64
    production_package_sha256 = "b" * 64
    render_surfaces: dict[str, dict[str, object]] = {}
    for capture_id, label in enumerate(contract.labels, start=1):
        path = tmp_path / f"{capture_id:02d}-{label}.png"
        fixture_source = f"ordered-step-{capture_id:03d}:fixture"
        family = renderer_families[label]
        state_contract = state_contracts[label]
        expected_profile = state_contract["profile"]
        logical_size = (
            tuple(expected_profile["declared_client_size"])
            if label in resize_layout_modes
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
        png_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        render_digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
        render_surfaces[label] = {
            "digest": render_digest,
            "environment_digest": environment_digest,
            "input_count": 1,
            "inputs": {"fixture": render_digest},
        }
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
            if "declared_client_size" in state_contract["required_facts"]:
                postcondition_facts["declared_client_size"] = list(logical_size)
            if "requested_client_size" in state_contract["required_facts"]:
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
                "declared_clearance": 0,
                "layout_clearance": 0,
                "content_height": 300,
                "content_size_hint_height": 280,
                "content_minimum_size_hint_height": 260,
                "scroll_minimum": 0,
                "scroll_maximum": 0,
                "last_body_child_bottom": 300,
                "last_body_child_bottom_at_scroll_end": 400,
                "require_no_scroll": bool(
                    label.startswith("purchase-confirmation-")
                    or label.startswith("purchase-error-")
                    or label.startswith("growth-charge-")
                ),
                "required_content_height": 300,
                "reachable_content_height": 300,
                "issues": [],
                "passed": True,
            }
        visual_contract, visual_audit = _valid_visual_contract(
            label,
            str(postcondition_kind),
            family,
        )
        native_layout_telemetry = _valid_native_layout_telemetry(
            label=label,
            window_family=family,
        )
        records.append({
            "audit": {
                "fixture_identity": fixture_validation,
                "native_layout_telemetry": copy.deepcopy(
                    native_layout_telemetry
                ),
                **visual_audit,
                "passed": True,
            },
            "actual_client_size": list(logical_size),
            "capture_id": capture_id,
            "capture_display": "primary",
            "capture_environment_digest": environment_digest,
            "capture_method": "qt-widget-grab",
            "capture_duration_ms": 1.0,
            "capture_ms": 1.0,
            "audit_ms": 1.0,
            "cleanup_ms": 1.0,
            "constraint_limited": False,
            "declared_client_size": list(logical_size),
            "device_pixel_ratio": dpr,
            "dialog_scroll_audit": dialog_scroll_audit,
            "native_layout_telemetry": native_layout_telemetry,
            "exact_size_reached": True,
            "fixture_source": fixture_source,
            "fixture_validation": fixture_validation,
            "frame_size": list(logical_size),
            "frame_overhead": [0, 0],
            "geometry_acceptance": geometry_acceptance,
            "geometry_drift_accepted": False,
            "geometry_layout_warnings": [],
            "height": logical_size[1],
            "evidence_status": "captured",
            "label": label,
            "lineage": {
                "evidence_status": "captured",
                "source_package_sha256": production_package_sha256,
                "source_run_id": "fixture-run",
            },
            "layout_mode": layout_mode,
            "native_normalized": False,
            "normalization_reason": "",
            "path": str(path),
            "png_sha256": png_sha256,
            "ready_to_capture_ms": 2.0,
            "semantic_ready_ms": 1.0,
            "stable": True,
            "stable_frame_count": 2,
            "stable_ms": 1.0,
            "render_input_count": 1,
            "render_input_digest": render_digest,
            "source_package_sha256": production_package_sha256,
            "requested_client_size": list(logical_size),
            "screen_limited": False,
            "text_layout_warnings": [],
            "transition_path": (
                expected_profile["transition_path"]
                if label in resize_layout_modes
                else "canonical-open"
            ),
            "visual_contract_audit": visual_contract,
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
                        "last_body_child_bottom",
                        "last_body_child_bottom_at_scroll_end",
                    )
                },
                "issues": [],
                "passed": True,
            })
    payload: dict[str, object] = {
        "capture_contract_version": contract.version,
        "capture_profile": "representative",
        "capture_scope": "full",
        "capture_display": "primary",
        "capture_displays": ["primary"],
        "capture_calibration": {"passed": True, "issues": []},
        "capture_environment_digest": environment_digest,
        "foreground_policy": "required-only",
        "foreground_requests": [],
        "capture_groups": [
            {"name": name, "labels": list(labels)}
            for name, labels in contract.groups
        ],
        "expected_faces": list(contract.labels),
        "requested_faces": list(contract.labels),
        "captured_faces": list(contract.labels),
        "reused_faces": [],
        "invalidated_faces": [],
        "screenshots": screenshots,
        "captures": records,
        "text_layout_warnings": [],
        "failures": [],
        "expected_count": len(contract.labels),
        "requested_scale_factor": "1.0",
        "dialog_memory_probe": {"status": "not-run", "cycles": 0},
        "dialog_memory_probe_complete": True,
        "dialog_scroll_audits": {
            "required": False,
            "required_count": 0,
            "records": [],
            "passed": True,
        },
        "dialog_scroll_audits_complete": True,
        "fixture_validations_complete": True,
        "production_package_sha256": production_package_sha256,
        "render_inputs": {
            "environment_digest": environment_digest,
            "production_archive_sha256": production_package_sha256,
            "surfaces": render_surfaces,
        },
        "scope_complete": True,
        "complete": True,
    }
    manifest = tmp_path / "manifest.json"
    _write_json(manifest, payload)
    _write_json(tmp_path / "capture-complete.json", {
        "complete": True,
        "exit_code": 0,
        "manifest": str(manifest),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "scope_complete": True,
    })
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
        draw = ImageDraw.Draw(sheet)
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
                draw.rounded_rectangle(
                    preview_box,
                    radius=12,
                    fill=CONTACT_SHEET_PREVIEW_FRAME_FILL,
                    outline=CONTACT_SHEET_PREVIEW_FRAME_OUTLINE,
                    width=CONTACT_SHEET_OUTLINE_WIDTH,
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
                preview_y = preview_box[1] + CONTACT_SHEET_PREVIEW_INSET
                draw.rectangle(
                    (
                        preview_x - CONTACT_SHEET_OUTLINE_WIDTH,
                        preview_y - CONTACT_SHEET_OUTLINE_WIDTH,
                        preview_x + preview.width + CONTACT_SHEET_OUTLINE_WIDTH - 1,
                        preview_y + preview.height + CONTACT_SHEET_OUTLINE_WIDTH - 1,
                    ),
                    outline=CONTACT_SHEET_SCREENSHOT_OUTLINE,
                    width=CONTACT_SHEET_OUTLINE_WIDTH,
                )
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
    assert capture_result["capture_count"] == 26
    assert sheet_result == {
        "contact_sheet_set": str(contact_sheets.resolve()),
        "page_count": 4,
        "surface_count": 26,
        "status": "valid",
    }


def test_incremental_plan_and_assembly_reuse_unaffected_surfaces(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    base_manifest, base_payload = _valid_capture(base_dir)
    contract = load_capture_contract(CAPTURE_SOURCE)
    selected = list(contract.labels[3:8])
    plan = plan_incremental_capture(
        base_manifest=base_manifest,
        current_render_inputs=base_payload["render_inputs"],
        expected_labels=contract.labels,
        contract_version=contract.version,
        explicit_surfaces=selected,
    )
    assert plan["recapture_required"] == selected
    assert plan["reused"] == [
        label for label in contract.labels if label not in selected
    ]

    patch_dir = tmp_path / "patch"
    patch_dir.mkdir()
    patch_payload = copy.deepcopy(base_payload)
    patch_records = []
    patch_screenshots = []
    base_records = {
        str(record["label"]): record
        for record in base_payload["captures"]
    }
    for label in selected:
        record = copy.deepcopy(base_records[label])
        source = Path(str(record["path"]))
        destination = patch_dir / source.name
        destination.write_bytes(source.read_bytes())
        record["path"] = str(destination)
        patch_records.append(record)
        patch_screenshots.append(str(destination))
    patch_payload.update({
        "capture_scope": "patch",
        "requested_faces": selected,
        "captured_faces": selected,
        "reused_faces": [],
        "invalidated_faces": selected,
        "captures": patch_records,
        "screenshots": patch_screenshots,
        "scope_complete": True,
        "complete": False,
    })
    patch_manifest = patch_dir / "manifest.json"
    _write_json(patch_manifest, patch_payload)
    _write_json(patch_dir / "capture-complete.json", {
        "complete": False,
        "exit_code": 0,
        "manifest": str(patch_manifest),
        "manifest_sha256": hashlib.sha256(patch_manifest.read_bytes()).hexdigest(),
        "scope_complete": True,
    })
    assert surface_validation_report(patch_manifest)["status"] == "valid"

    assembled = assemble_capture_manifest(
        base_manifest=base_manifest,
        patch_manifest=patch_manifest,
        reuse_plan=plan,
        current_render_inputs=base_payload["render_inputs"],
        output_dir=tmp_path / "assembled",
    )
    assembled_payload = json.loads(assembled.read_text(encoding="utf-8"))
    assert assembled_payload["captured_faces"] == selected
    assert assembled_payload["reused_faces"] == plan["reused"]
    assert validate_capture_manifest(assembled)["status"] == "valid"


def test_contact_sheet_topology_is_two_columns_by_five_rows() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    pages = expected_contact_sheet_pages(contract)

    assert [sum(count for _name, count in page) for page in pages] == [9, 5, 6, 6]
    assert pages[0] == (("First run", 3), ("Home and Garden", 6))
    assert [expected_contact_sheet_dimensions(page)[1] for page in pages] == [
        5192, 3218, 3218, 3218,
    ]


def test_renderer_families_are_derived_for_every_representative_face() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    families = load_expected_renderer_families(CAPTURE_SOURCE, contract=contract)

    assert tuple(families) == contract.labels
    assert Counter(families.values()) == Counter({
        "GardenDashboard": 4,
        "GardenProgressDialog": 5,
        "GardenSettingsDialog": 2,
        "NurseryDialog": 6,
        "AnkiQt": 2,
        "CollectibleDetailDialog": 1,
        "FertilizerDialog": 1,
        "StarterConfirmationDialog": 1,
        "PlantStoryDialog": 1,
        "SpeciesOverviewDialog": 1,
        "PurchaseConfirmationDialog": 1,
        "GrowthChargeConfirmationDialog": 1,
    })
    assert families["full-garden"] == "GardenDashboard"
    assert families["growth-charge-use-ready"] == "GrowthChargeConfirmationDialog"
    assert "resize-species-overview-large" not in families
    resize_modes = load_expected_resize_layout_modes(CAPTURE_SOURCE)
    assert len(resize_modes) == 65
    assert resize_modes["resize-dashboard-content-819"] == "compact"
    assert resize_modes["resize-dashboard-content-821"] == "compact"
    assert resize_modes["resize-progress-default"] == "wide"


def test_state_evidence_contracts_are_derived_for_every_representative_face() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    states = load_expected_state_evidence_contracts(
        CAPTURE_SOURCE,
        contract=contract,
    )

    assert tuple(states) == contract.labels
    assert Counter(state["kind"] for state in states.values()) == Counter({
        "dashboard": 4,
        "progress": 5,
        "home": 1,
        "nursery": 6,
        "settings": 2,
        "reviewer": 1,
        "dialog": 6,
        "collectible-detail": 1,
    })
    assert states["growth-nonzero"]["profile"]["page"] == "growth"
    assert states["nursery-fertilizer-booster"]["profile"]["tab"] == 1
    assert states["nursery-fertilizer-booster"]["profile"]["starter_mode"] is False
    assert "resize-progress-default" not in states
    assert states["growth-charge-use-ready"]["profile"][
        "growth_charge_status"
    ] == "ready"


def test_accessibility_fixture_ownership_and_cleanup_are_source_bound() -> None:
    states = load_expected_state_evidence_contracts(CAPTURE_SOURCE)

    settings_values = states["settings-unsaved-changes"]["expected_fact_values"]
    assert settings_values["settings_tab"] == 0
    assert states["reviewer-find-environment"]["kind"] == "reviewer"
    assert "reduced-motion-enabled" not in states
    assert "keyboard-focus-state" not in states
    assert "narrow-window-responsive" not in states
    assert "display-scaling-150" not in states
    assert "display-scaling-200-qt-representative" not in states


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
    assert changed["growth-nonzero"]["profile"]["page"] == "streak"
    assert changed["growth-nonzero"]["expected_fact_values"]["progress_page"] == "streak"

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


def test_manifest_rejects_high_risk_visual_state_and_geometry_regressions(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    by_label = {
        str(record["label"]): record
        for record in records
        if isinstance(record, dict)
    }

    by_label["full-garden"]["audit"]["steady_state_visual"][
        "overlay_free"
    ] = False
    by_label["full-garden"]["audit"]["rendered_pixel_evidence"][
        "results"
    ][0]["capture_pixels_present"] = False
    by_label["reviewer-find-environment"]["audit"][
        "reviewer_overlay_geometry"
    ]["viewport_contained"] = False
    by_label["reviewer-find-environment"]["audit"][
        "required_overlay_pixels_present"
    ] = False
    by_label["active-deck-browser-home-after-nurture"]["audit"]["compact_home_copy"][
        "rendered_text"
    ] += " Hidden Garden Coins 999"

    generic = by_label["starter-selection-confirmation"]
    generic_visual = generic["visual_contract_audit"]
    assert isinstance(generic_visual, dict)
    generic_visual["primary_actions"] = ["Confirm", "Purchase"]
    generic_visual["primary_action_count"] = 2
    generic_visual["primary_action_groups"] = [{
        "scope": "actionFooter-1",
        "actions": ["Confirm", "Purchase"],
        "count": 2,
        "passed": False,
    }]
    generic_visual["max_primary_actions_per_group"] = 2
    generic_visual["close_icons"][0]["glyph_pixels_present"] = False
    generic_visual["close_icons"][0]["passed"] = False
    generic_audit = generic["audit"]
    assert isinstance(generic_audit, dict)
    generic_audit["visual_contract"] = copy.deepcopy(generic_visual)

    _write_json(manifest, payload)
    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    for expected in (
        "full Garden does not prove a clean contained steady state",
        "required state widgets are absent from captured pixels",
        "Reviewer card lacks full containment or control clearance",
        "Reviewer card is absent from captured pixels",
        "compact Home rendered or accessibility copy contains banned terms",
        "at most one filled primary action",
        "close icon has blank pixels or invalid bounds",
    ):
        assert expected in message


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

    with pytest.raises(CaptureValidationError, match="source-owned GardenDashboard"):
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
        match="capture 007 fertilizer-affordable: fixture sources disagree",
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
    assert "postcondition kind must be 'dashboard'" in message
    assert "postcondition facts must be nonempty" in message
    assert "postcondition issues must be empty" in message
    assert "postcondition did not pass" in message


def test_resize_layout_modes_remain_a_non_visual_automated_contract() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    resize_modes = load_expected_resize_layout_modes(CAPTURE_SOURCE)

    assert "resize-dashboard-content-821" not in contract.labels
    assert resize_modes["resize-dashboard-content-821"] == "compact"
    assert resize_modes["resize-progress-default"] == "wide"


def test_manifest_rejects_same_renderer_state_schema_substitution(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    growth = records[contract.labels.index("growth-nonzero")]
    streak = records[contract.labels.index("streak-active")]
    assert isinstance(growth, dict) and isinstance(streak, dict)
    growth_fixture = growth["fixture_validation"]
    streak_fixture = streak["fixture_validation"]
    assert isinstance(growth_fixture, dict) and isinstance(streak_fixture, dict)
    growth_postcondition = growth_fixture["postcondition"]
    streak_postcondition = streak_fixture["postcondition"]
    assert isinstance(growth_postcondition, dict) and isinstance(streak_postcondition, dict)
    growth_postcondition["facts"] = copy.deepcopy(streak_postcondition["facts"])
    growth_audit = growth["audit"]
    assert isinstance(growth_audit, dict)
    growth_audit["fixture_identity"] = copy.deepcopy(growth_fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="postcondition fact schema mismatch"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_representative_owner_state_substitution(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)

    substitutions = (
        ("settings-unsaved-changes", "diagnostics-warning"),
        ("reviewer-find-environment", "active-deck-browser-home-after-nurture"),
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
    assert "settings-unsaved-changes: postcondition fact schema mismatch" in message
    assert "reviewer-find-environment: postcondition fact schema mismatch" in message


def test_manifest_rejects_forged_reviewer_visibility_fact_value(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    records = payload["captures"]
    assert isinstance(records, list)
    record = records[contract.labels.index("reviewer-find-environment")]
    assert isinstance(record, dict)
    fixture = record["fixture_validation"]
    assert isinstance(fixture, dict)
    postcondition = fixture["postcondition"]
    assert isinstance(postcondition, dict)
    facts = postcondition["facts"]
    assert isinstance(facts, dict)
    facts["reward_toast_visible"] = False
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["fixture_identity"] = copy.deepcopy(fixture)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="reward_toast_visible.*True"):
        validate_capture_manifest(manifest)


def test_resize_geometry_rejects_fabricated_size() -> None:
    result = expected_resize_geometry_acceptance(
        label="resize-dashboard-large",
        declared_size=(1440, 960),
        actual_size=(100, 100),
        minimum_size=(100, 100),
        maximum_size=(2000, 2000),
        screen_limited=False,
        constraint_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    assert result["drifted"] is True
    assert result["accepted"] is False
    assert result["provenance_explains_drift"] is False


def test_resize_geometry_accepts_provenance_backed_bounded_height_drift() -> None:
    result = expected_resize_geometry_acceptance(
        label="resize-dashboard-content-821",
        declared_size=(845, 720),
        actual_size=(845, 600),
        minimum_size=(100, 100),
        maximum_size=(2000, 2000),
        screen_limited=True,
        constraint_limited=False,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    assert result["accepted"] is True
    assert result["provenance_explains_drift"] is True


def test_resize_geometry_rejects_unexplained_drift() -> None:
    result = expected_resize_geometry_acceptance(
        label="resize-dashboard-content-821",
        declared_size=(845, 720),
        actual_size=(845, 600),
        minimum_size=(100, 100),
        maximum_size=(2000, 2000),
        screen_limited=False,
        constraint_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    assert result["accepted"] is False
    assert result["provenance_explains_drift"] is False


def test_resize_geometry_rejects_breakpoint_width_drift_over_one_pixel() -> None:
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
    drifted_breakpoint = expected_resize_geometry_acceptance(
        label="resize-dashboard-content-821",
        declared_size=(845, 720),
        actual_size=(842, 600),
        minimum_size=(100, 100),
        maximum_size=(2000, 2000),
        screen_limited=True,
        constraint_limited=False,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    assert drifted_breakpoint["breakpoint_fixture"] is True
    assert drifted_breakpoint["breakpoint_width_within_one"] is False
    assert drifted_breakpoint["accepted"] is False


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
    assert "numeric-equivalent to 1.0" in message
    assert "status must be 'not-run'" in message
    assert "cycles must be 0" in message
    assert "actual_client_size must match" in message
    assert "device_pixel_ratio is invalid" in message
    assert "layout_mode is missing" in message
    assert "capture_displays does not match" in message
    assert "capture_display does not match" in message


def test_manifest_rejects_unexpected_release_memory_probe(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    probe.update({"status": "measured", "cycles": 12})
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)
    message = str(raised.value)
    assert "status must be 'not-run'" in message
    assert "cycles must be 0" in message


def test_manifest_rejects_invalid_native_dialog_layout_telemetry(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    record = next(
        item
        for item in records
        if isinstance(item, dict)
        and item.get("label") == "growth-charge-use-ready"
    )
    telemetry = record["native_layout_telemetry"]
    assert isinstance(telemetry, dict)
    telemetry.update({
        "clientSurfaceFill": 0.50,
        "clientGutterPx": 50,
        "contentToFooterGap": 49,
        "maximumActionWidthRatio": 0.51,
        "minimumRenderedTextSize": 11.9,
        "elisionWithoutTooltipCount": 1,
        "tabularNumeralWidgets": [],
        "tabularNumeralWidgetCount": 0,
        "passed": True,
        "issues": [],
    })
    buttons = telemetry["buttonRecords"]
    assert isinstance(buttons, list)
    button = buttons[0]
    assert isinstance(button, dict)
    button["height"] = 35
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["native_layout_telemetry"] = copy.deepcopy(telemetry)
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "client gutter exceeds" in message
    assert "content-to-footer gap exceeds" in message
    assert "action width ratio exceeds" in message
    assert "rendered text is below" in message
    assert "elision is missing tooltip" in message
    assert "button geometry or text size" in message
    assert "tabular numeral evidence is incomplete" in message


def test_manifest_accepts_hidden_range_positive_non_owner_scrollbar(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    records = payload["captures"]
    assert isinstance(records, list)
    record = next(
        item
        for item in records
        if isinstance(item, dict)
        and item.get("label") == "progress-collection"
    )
    telemetry = record["native_layout_telemetry"]
    assert isinstance(telemetry, dict)
    telemetry["scrollbars"] = [
        {
            "minimum": 0,
            "maximum": 0,
            "value": 0,
            "visible": False,
            "overflowOwner": True,
        },
        {
            "minimum": 0,
            "maximum": 737,
            "value": 0,
            "visible": False,
            "overflowOwner": False,
        },
    ]
    telemetry["overflowOwnerCount"] = 1
    audit = record["audit"]
    assert isinstance(audit, dict)
    audit["native_layout_telemetry"] = copy.deepcopy(telemetry)
    _write_json(manifest, payload)

    validate_capture_manifest(manifest)

    telemetry["scrollbars"][1]["visible"] = True
    audit["native_layout_telemetry"] = copy.deepcopy(telemetry)
    _write_json(manifest, payload)
    with pytest.raises(
        CaptureValidationError,
        match="native non-owner scrollbar is visible",
    ):
        validate_capture_manifest(manifest)


def test_manifest_rejects_nonrepresentative_release_profile(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["capture_profile"] = "full"
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError, match="must be 'representative'"):
        validate_capture_manifest(manifest)


def test_manifest_rejects_incomplete_or_fabricated_memory_cycles(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["dialog_memory_probe_complete"] = False
    probe = payload["dialog_memory_probe"]
    assert isinstance(probe, dict)
    probe["status"] = "measured"
    probe["cycles"] = 12
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "dialog_memory_probe_complete must be true" in message
    assert "dialog_memory_probe status must be 'not-run'" in message
    assert "dialog_memory_probe cycles must be 0" in message


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
    assert "surface_count must be 26" in message
    assert "pages account for 25 surfaces" in message
    assert "PNG dimensions must be 3000x5192px" in message
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


def test_contact_sheet_set_rejects_centering_missing_outline_and_dark_frame(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    index = _valid_contact_sheets(tmp_path, manifest)
    index_payload = json.loads(index.read_text(encoding="utf-8"))
    first_page = index.parent / index_payload["pages"][0]["file"]
    with Image.open(first_page) as opened:
        opened.load()
        original = opened.convert("RGB")
        metadata = dict(opened.text)
    records = payload["captures"]
    assert isinstance(records, list)
    first_record = records[0]
    assert isinstance(first_record, dict)
    with Image.open(Path(str(first_record["path"]))) as opened_source:
        source = opened_source.convert("RGB")

    preview_box = (86, 444, 1462, 1224)
    preview_x = preview_box[0] + (preview_box[2] - preview_box[0] - source.width) // 2
    top_y = preview_box[1] + CONTACT_SHEET_PREVIEW_INSET
    centered_y = preview_box[1] + (
        preview_box[3] - preview_box[1] - source.height
    ) // 2

    def save(page: Image.Image) -> None:
        pnginfo = PngImagePlugin.PngInfo()
        for key, value in metadata.items():
            pnginfo.add_text(key, value)
        page.save(first_page, format="PNG", pnginfo=pnginfo)

    centered = original.copy()
    draw = ImageDraw.Draw(centered)
    draw.rounded_rectangle(
        preview_box,
        radius=12,
        fill=CONTACT_SHEET_PREVIEW_FRAME_FILL,
        outline=CONTACT_SHEET_PREVIEW_FRAME_OUTLINE,
        width=CONTACT_SHEET_OUTLINE_WIDTH,
    )
    draw.rectangle(
        (
            preview_x - CONTACT_SHEET_OUTLINE_WIDTH,
            centered_y - CONTACT_SHEET_OUTLINE_WIDTH,
            preview_x + source.width + CONTACT_SHEET_OUTLINE_WIDTH - 1,
            centered_y + source.height + CONTACT_SHEET_OUTLINE_WIDTH - 1,
        ),
        outline=CONTACT_SHEET_SCREENSHOT_OUTLINE,
        width=CONTACT_SHEET_OUTLINE_WIDTH,
    )
    centered.paste(source, (preview_x, centered_y))
    save(centered)
    with pytest.raises(CaptureValidationError) as raised:
        validate_contact_sheet_set(index, manifest_path=manifest)
    assert "pixels do not match manifest screenshot" in str(raised.value)

    missing_outline = original.copy()
    draw = ImageDraw.Draw(missing_outline)
    draw.rectangle(
        (
            preview_x - CONTACT_SHEET_OUTLINE_WIDTH,
            top_y - CONTACT_SHEET_OUTLINE_WIDTH,
            preview_x + source.width + CONTACT_SHEET_OUTLINE_WIDTH - 1,
            top_y + source.height + CONTACT_SHEET_OUTLINE_WIDTH - 1,
        ),
        outline=CONTACT_SHEET_PREVIEW_FRAME_FILL,
        width=CONTACT_SHEET_OUTLINE_WIDTH,
    )
    missing_outline.paste(source, (preview_x, top_y))
    save(missing_outline)
    with pytest.raises(CaptureValidationError, match="screenshot outline is missing"):
        validate_contact_sheet_set(index, manifest_path=manifest)

    wrong_frame = original.copy()
    wrong_frame.putpixel(
        (
            (preview_box[0] + preview_box[2]) // 2,
            preview_box[1] + CONTACT_SHEET_OUTLINE_WIDTH + 1,
        ),
        (7, 18, 15),
    )
    save(wrong_frame)
    with pytest.raises(CaptureValidationError, match="distinct light fill"):
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
    first_box = (724, 452, 824, 552)
    second_box = (2176, 452, 2276, 552)
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
    streak_index = contract.labels.index("streak-active")
    coins_index = contract.labels.index("coins-activity")
    screenshots = payload["screenshots"]
    assert isinstance(screenshots, list)
    Path(screenshots[coins_index]).write_bytes(
        Path(screenshots[streak_index]).read_bytes()
    )

    with pytest.raises(CaptureValidationError, match="unapproved duplicate visual evidence"):
        validate_capture_manifest(manifest)


def test_representative_contract_omits_redundant_duplicate_capture(
    tmp_path: Path,
) -> None:
    manifest, payload = _valid_capture(tmp_path)
    contract = load_capture_contract(CAPTURE_SOURCE)
    assert "starter-nursery-plants" in contract.labels
    assert "starter-action-above-footer" not in contract.labels
    assert validate_capture_manifest(manifest)["status"] == "valid"


def test_contract_excludes_resize_and_scale_visual_proxies() -> None:
    contract = load_capture_contract(CAPTURE_SOURCE)
    assert "display-scaling-150" not in contract.labels
    assert "display-scaling-200-qt-representative" not in contract.labels
    assert "resize-dashboard-minimum" not in contract.labels
    assert "growth-charge-minimum-responsive" not in contract.labels


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
        "actual_page_semantic": "GardenProgressDialog:growth",
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


def test_manifest_rejects_nonempty_representative_scroll_summary(tmp_path: Path) -> None:
    manifest, payload = _valid_capture(tmp_path)
    payload["dialog_scroll_audits_complete"] = False
    summary = payload["dialog_scroll_audits"]
    assert isinstance(summary, dict)
    summary["required"] = True
    summary["passed"] = False
    summary["required_count"] = 1
    summary["records"] = [{}]
    _write_json(manifest, payload)

    with pytest.raises(CaptureValidationError) as raised:
        validate_capture_manifest(manifest)

    message = str(raised.value)
    assert "dialog_scroll_audits_complete must be true" in message
    assert "dialog_scroll_audits required must be false" in message
    assert "dialog_scroll_audits passed must be true" in message
    assert "dialog_scroll_audits required_count must be 0" in message
    assert "dialog_scroll_audits records must be empty" in message
