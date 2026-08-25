#!/usr/bin/env python3
"""Incremental evidence planning and assembly for Anki Garden UI captures.

This module is deliberately Qt-free.  The disposable Anki process owns raw
capture; this module decides which existing records remain trustworthy and
assembles one self-contained, canonically ordered evidence directory.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class CaptureEvidenceError(ValueError):
    """Raised when incremental evidence cannot be trusted or assembled."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_manifest_path(value: object, root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _top_level_fragments(source: bytes) -> dict[str, bytes]:
    """Return stable source fragments for module-level symbols."""

    text = source.decode("utf-8")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    fragments: dict[str, bytes] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        if not names or not hasattr(node, "end_lineno"):
            continue
        fragment = "".join(lines[node.lineno - 1 : int(node.end_lineno)]).encode(
            "utf-8"
        )
        for name in names:
            fragments[name] = fragment
    return fragments


_DASHBOARD_COMMON_SYMBOLS = frozenset({
    "UI_TEXT",
    "_FocusTooltipFilter",
    "_set_focus_accessible_tooltip",
    "ElidingLabel",
    "set_button_size",
    "_set_button_variant",
    "_set_compact_row_action",
    "DialogShell",
    "GardenDialogHeader",
    "GardenDialogFooter",
    "GardenButton",
    "GardenIconButton",
    "GardenDialog",
    "_garden_dialog_stylesheet",
    "ToastRegion",
    "apply_explanatory_tooltip",
    "GardenImageFrame",
    "ArtworkThumbnail",
    "_button_stylesheet",
    "GardenTabs",
    "SectionCard",
    "GardenBadge",
    "GardenStatusBanner",
    "EmptyState",
    "ActionFooter",
})

_DASHBOARD_FAMILY_SYMBOLS: dict[str, frozenset[str]] = {
    "AnkiQt": frozenset({"GardenDashboard"}),
    "GardenDashboard": frozenset({
        "GardenDashboard",
        "GardenPlantSummary",
        "GardenSceneOverlay",
        "GardenPopover",
        "GardenStatsStrip",
        "RearrangeBar",
        "GardenSideNavigation",
    }),
    "GardenProgressDialog": frozenset({
        "GardenProgressDialog",
        "GardenDetailsDialog",
        "_TabbedProgressShell",
        "LabeledProgress",
        "ProgressBar",
        "ProgressRow",
        "ProgressCardGrid",
        "ResponsiveTileGrid",
        "CollectionFilterControls",
        "DataTable",
    }),
    "GardenSettingsDialog": frozenset({
        "GardenSettingsDialog",
        "ToggleSwitch",
    }),
    "NurseryDialog": frozenset({
        "NurseryDialog",
        "ResponsiveTileGrid",
        "ResponsiveActionCard",
        "GardenOutcomePreview",
        "_asset_preview_label",
        "_item_preview_label",
        "_missing_artwork_pixmap",
        "_environment_preview_pixmap",
        "_garden_bed_purchase_preview",
    }),
    "CollectibleDetailDialog": frozenset({
        "CollectibleDetailDialog",
        "CollectionFilterControls",
        "ResponsiveSplit",
    }),
    "FertilizerDialog": frozenset({
        "FertilizerStatusBlock",
        "FertilizerReplacementDialog",
    }),
    "StarterConfirmationDialog": frozenset({"StarterConfirmationDialog"}),
    "PlantStoryDialog": frozenset({"PlantStoryDialog", "MemoryTimeline"}),
    # The species dialog is constructed by GardenDashboard and uses the
    # shared detail shell. Keep both authorities in its dependency closure.
    "SpeciesOverviewDialog": frozenset({
        "GardenDashboard",
        "GardenDetailsDialog",
    }),
    "PurchaseConfirmationDialog": frozenset({
        "PurchaseConfirmationDialog",
        "ConfirmationDialog",
        "GardenOutcomePreview",
    }),
    "GrowthChargeConfirmationDialog": frozenset({
        "GrowthChargeConfirmationDialog",
        "GardenOutcomePreview",
    }),
}


# Audited source-owned transitions for the first v23 patch run.  Each entry
# names one exact old/new render input pair and the only surfaces whose pixels
# or deterministic fixture state can change. Unknown source, harness, or
# validator drift remains global and therefore cannot silently reuse evidence.
_INPUT_IMPACT_TRANSITIONS: dict[
    tuple[str, str, str],
    frozenset[str],
] = {
    (
        "capture-source",
        "0dd0b0ae855b0c96cbb17691f6bd14737087851cbce3122c96d4cd8399d33ff0",
        "9346e212cfd74f8a861f8c667f00b96808e3cbbdeb8e901d5ac977ff40d5824e",
    ): frozenset({
        "progress-collection",
        "reviewer-find-environment",
        "purchase-confirmation-growth-charge",
        "purchase-success-inventory-collection",
        "growth-charge-use-ready",
    }),
    (
        "archive:ui/dashboard.py#GardenDetailsDialog",
        "a66e23281b6b19f46aa19a7fc213647c53b260d884276aea20fcf0ac7b3df7a9",
        "48f3be4c5c1017c25a6ff26b163cac1d52c218f49950bf6c5e8c122b38d50b05",
    ): frozenset({"coins-activity"}),
    (
        "archive:ui/dashboard.py#GardenDashboard",
        "0498dc1b1fd6c4fdf03a0035752341604977af04ef33ceabc47e660cedbf702f",
        "5c7e56ad22f665f0f2e7c31042e3705b85c15b61cca6af9eb27f1853d12d9eeb",
    ): frozenset({"collection-species-overview"}),
    # v23.0 did not yet declare GardenDashboard as a species-dialog input.
    (
        "archive:ui/dashboard.py#GardenDashboard",
        "",
        "5c7e56ad22f665f0f2e7c31042e3705b85c15b61cca6af9eb27f1853d12d9eeb",
    ): frozenset({"collection-species-overview"}),
    (
        "archive:ui/dashboard.py#GardenDashboard",
        "0fa295aeec9b1a8a26b54fe7de2229e46afc1529eb89cd852c94f89c4f548aec",
        "5c7e56ad22f665f0f2e7c31042e3705b85c15b61cca6af9eb27f1853d12d9eeb",
    ): frozenset({"collection-species-overview"}),
    (
        "archive:ui/dashboard.py#NurseryDialog",
        "7483729f0790792373f478c19054d0e1164a62e1f8bbf7555316b30b95f32117",
        "4bdf751823b057e3d64566a98df74d9f782a62279b4e030c97ad383c7f62a3bf",
    ): frozenset({"purchase-success-inventory-collection"}),
    (
        "archive:ui/dashboard.py#NurseryDialog",
        "7ec55f24d9d6f11f9b6406bee9d20637dbd473d9cef888afb536f424afab4cfc",
        "4bdf751823b057e3d64566a98df74d9f782a62279b4e030c97ad383c7f62a3bf",
    ): frozenset({"purchase-success-inventory-collection"}),
    (
        "archive:ui/dashboard.py#NurseryDialog",
        "0ece95d47cde119fee8b5d53d8721eecccafb6c90b8c451323b574e86551c8db",
        "4bdf751823b057e3d64566a98df74d9f782a62279b4e030c97ad383c7f62a3bf",
    ): frozenset({"purchase-success-inventory-collection"}),
    (
        "archive:ui/dashboard.py#NurseryDialog",
        "82e7d81e9434806d931c18f806177bdeb4497555d6090215e401dcbd5055edfe",
        "4bdf751823b057e3d64566a98df74d9f782a62279b4e030c97ad383c7f62a3bf",
    ): frozenset({"purchase-success-inventory-collection"}),
}


def _input_transition_compatibility(
    *,
    label: str,
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Prove that every changed input is mapped away from ``label``."""

    previous_inputs = previous.get("inputs")
    current_inputs = current.get("inputs")
    if not isinstance(previous_inputs, dict) or not isinstance(current_inputs, dict):
        return False, []
    transitions: list[dict[str, Any]] = []
    for key in sorted(set(previous_inputs) | set(current_inputs)):
        old = str(previous_inputs.get(key, "") or "")
        new = str(current_inputs.get(key, "") or "")
        if old == new:
            continue
        affected = _INPUT_IMPACT_TRANSITIONS.get((key, old, new))
        if affected is None or label in affected:
            return False, []
        transitions.append({
            "input": key,
            "old": old,
            "new": new,
            "affected_faces": sorted(affected),
        })
    return bool(transitions), transitions


def _label_bucket(label: str) -> str:
    if label.startswith("starter-"):
        return "starter"
    if label in {
        "full-garden",
        "selected-plant-nurtured",
        "active-deck-browser-home-after-nurture",
        "fertilizer-affordable",
        "move-mode",
        "plant-story",
    }:
        return "home-garden"
    if label.startswith("growth-") or label.startswith("streak-") or label in {
        "coins-activity",
        "progress-achievements",
        "progress-collection",
    }:
        return "progress"
    if label.startswith("collection-") or label.startswith("nursery-"):
        return "collection-nursery"
    return "settings-transactions"


def _entry_buckets(name: str) -> frozenset[str] | None:
    """Return affected buckets; None means global/fail-safe impact."""

    global_entries = {
        "__init__.py",
        "addon.py",
        "build_capabilities.py",
        "config.py",
        "config.json",
        "display_telemetry.py",
        "manifest.json",
        "terminology.py",
        "ui/__init__.py",
        "ui/accessibility.py",
        "ui/copy.py",
        "ui/dialog_foundations.py",
        "ui/icons.py",
        "ui/responsive.py",
        "ui/state.py",
        "ui/state_contracts.py",
        "ui/theme.py",
        "assets/manifest.json",
    }
    if name in global_entries:
        return None
    if name == "ui/dashboard.py":
        return frozenset()
    if name.startswith("assets/v6_storybook_gouache/plants/"):
        return frozenset({"starter", "home-garden", "collection-nursery"})
    if name.startswith("assets/v6_storybook_gouache/backgrounds/"):
        return frozenset({"home-garden", "collection-nursery"})
    if name.startswith("assets/v6_storybook_gouache/ui/"):
        return frozenset({"home-garden", "collection-nursery", "settings-transactions"})
    if name.startswith("assets/support/"):
        return frozenset({"home-garden", "collection-nursery"})
    exact: dict[str, frozenset[str]] = {
        "achievements.py": frozenset({"progress", "settings-transactions"}),
        "collectibles.py": frozenset({"collection-nursery"}),
        "environment.py": frozenset({"home-garden", "collection-nursery"}),
        "game.py": frozenset({"starter", "home-garden", "progress", "collection-nursery"}),
        "garden_finds.py": frozenset({"settings-transactions"}),
        "growth.py": frozenset({"home-garden", "progress", "settings-transactions"}),
        "purchases.py": frozenset({"home-garden", "collection-nursery", "settings-transactions"}),
        "reward_ledger.py": frozenset({"progress", "settings-transactions"}),
        "reward_presentation.py": frozenset({"settings-transactions"}),
        "ui/garden_studio.py": frozenset({"home-garden"}),
        "ui/home_widget.py": frozenset({"starter", "home-garden"}),
        "ui/landmarks.py": frozenset({"home-garden"}),
        "ui/plant_display.py": frozenset({"starter", "home-garden", "collection-nursery"}),
        "ui/plant_presenters.py": frozenset({"starter", "home-garden", "collection-nursery"}),
        "ui/scene.py": frozenset({"home-garden"}),
        "hooks/reviewer.py": frozenset({"settings-transactions"}),
    }
    if name in exact:
        return exact[name]
    if name.startswith("models/") or name in {"storage.py", "asset_manager.py"}:
        return None
    # Unknown payloads are deliberately global. A new packaged file can never
    # slip past reuse merely because no impact rule has been written for it.
    return None


def build_render_input_catalog(
    production_archive: Path,
    *,
    capture_source: Path,
    validator_source: Path,
    labels: Sequence[str],
    renderer_families: Mapping[str, str],
) -> dict[str, Any]:
    """Build fail-safe, per-surface render dependency digests."""

    environment_inputs = {
        "capture-source": sha256_file(capture_source),
        "validator-source": sha256_file(validator_source),
    }
    environment_digest = canonical_json_sha256(environment_inputs)
    with zipfile.ZipFile(production_archive) as archive:
        entries = {
            info.filename: sha256_bytes(archive.read(info.filename))
            for info in archive.infolist()
            if not info.is_dir()
        }
        dashboard_source = archive.read("ui/dashboard.py")
    dashboard_fragments = _top_level_fragments(dashboard_source)

    catalog: dict[str, Any] = {}
    for label in labels:
        bucket = _label_bucket(label)
        family = str(renderer_families.get(label, ""))
        inputs = dict(environment_inputs)
        for name, digest in entries.items():
            affected = _entry_buckets(name)
            if affected is None or bucket in affected:
                inputs[f"archive:{name}"] = digest
        symbols = _DASHBOARD_COMMON_SYMBOLS | _DASHBOARD_FAMILY_SYMBOLS.get(
            family,
            frozenset(),
        )
        missing_symbols: list[str] = []
        for symbol in sorted(symbols):
            fragment = dashboard_fragments.get(symbol)
            if fragment is None:
                missing_symbols.append(symbol)
                continue
            inputs[f"archive:ui/dashboard.py#{symbol}"] = sha256_bytes(fragment)
        # A missing declared symbol is part of the digest and therefore fails
        # reuse deterministically rather than silently weakening provenance.
        if missing_symbols:
            inputs["dashboard-missing-symbols"] = canonical_json_sha256(
                missing_symbols
            )
        catalog[label] = {
            "bucket": bucket,
            "renderer_family": family,
            "environment_digest": environment_digest,
            "input_count": len(inputs),
            "inputs": dict(sorted(inputs.items())),
            "digest": canonical_json_sha256(inputs),
        }
    return {
        "environment_digest": environment_digest,
        "environment_inputs": environment_inputs,
        "production_archive_sha256": sha256_file(production_archive),
        "surfaces": catalog,
    }


def _load_manifest(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path.expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureEvidenceError(f"Invalid capture manifest: {resolved}") from exc
    if not isinstance(payload, dict):
        raise CaptureEvidenceError(f"Capture manifest is not an object: {resolved}")
    return resolved, payload


def surface_validation_report(manifest_path: Path) -> dict[str, Any]:
    """Classify an attempt or assembled manifest without discarding good faces."""

    manifest_path, payload = _load_manifest(manifest_path)
    session_root = manifest_path.parent.resolve()
    expected = [str(value) for value in payload.get("expected_faces", ())]
    requested = [str(value) for value in payload.get("requested_faces", expected)]
    records = {
        str(record.get("label", "")): record
        for record in payload.get("captures", ())
        if isinstance(record, dict) and str(record.get("label", ""))
    }
    failure_map: dict[str, list[str]] = {label: [] for label in expected}
    global_issues: list[str] = []
    # A partial attempt is globally incomplete, but that does not make each
    # already-written surface untrustworthy.  Keep truly run-wide integrity
    # failures separate so a later patch run can reuse clean records while
    # still reporting the incomplete attempt as invalid overall.
    reuse_barrier_issues: list[str] = []
    if payload.get("capture_profile") != "representative":
        issue = "capture profile is not representative"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    try:
        scale = float(payload.get("requested_scale_factor"))
    except (TypeError, ValueError):
        scale = 0.0
    if scale != 1.0:
        issue = "capture scale is not 1.0"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    calibration = payload.get("capture_calibration")
    if not isinstance(calibration, dict) or calibration.get("passed") is not True:
        issue = "capture calibration did not pass"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    if payload.get("scope_complete") is not True:
        global_issues.append("capture scope did not complete")
    completion_path = session_root / "capture-complete.json"
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        completion = {}
        issue = "capture completion record is missing or invalid"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    if completion:
        if completion.get("manifest_sha256") != sha256_file(manifest_path):
            issue = "capture completion manifest hash does not match"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
        referenced = Path(str(completion.get("manifest", ""))).expanduser()
        try:
            referenced = referenced.resolve()
        except OSError:
            referenced = Path()
        if referenced != manifest_path:
            issue = "capture completion references another manifest"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
    for failure in payload.get("failures", ()):
        if not isinstance(failure, dict):
            global_issues.append("malformed-capture-failure")
            continue
        label = str(failure.get("label", ""))
        reason = str(failure.get("reason", "capture failure"))
        if label in requested:
            failure_map.setdefault(label, []).append(reason)
        else:
            global_issues.append(f"{label or 'capture'}: {reason}")
    for warning in payload.get("text_layout_warnings", ()):
        if not isinstance(warning, dict):
            global_issues.append("malformed-layout-warning")
            continue
        label = str(warning.get("capture", ""))
        kind = str(warning.get("kind", "layout-warning"))
        if label in requested:
            failure_map.setdefault(label, []).append(kind)
        else:
            global_issues.append(f"{label or 'capture'}: {kind}")

    surfaces: dict[str, Any] = {}
    for label in expected:
        issues = list(failure_map.get(label, ()))
        record = records.get(label)
        if label not in requested and record is None:
            surfaces[label] = {
                "status": "not-requested",
                "issues": [],
            }
            continue
        if record is None:
            issues.append("capture record is missing")
        else:
            path = _safe_manifest_path(record.get("path"), session_root)
            if path is None or not path.is_file():
                issues.append("PNG is missing or outside the session")
            else:
                try:
                    with path.open("rb") as handle:
                        if handle.read(8) != PNG_SIGNATURE:
                            issues.append("PNG signature is invalid")
                    actual_sha = sha256_file(path)
                    if record.get("png_sha256") != actual_sha:
                        issues.append("PNG SHA-256 does not match the record")
                except OSError:
                    issues.append("PNG could not be read")
            for field in ("render_input_digest", "capture_environment_digest"):
                value = record.get(field)
                if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                    issues.append(f"{field} is missing or invalid")
            fixture = record.get("fixture_validation")
            if not isinstance(fixture, dict) or fixture.get("passed") is not True:
                issues.append("fixture validation did not pass")
            audit = record.get("audit")
            if not isinstance(audit, dict) or audit.get("passed") is not True:
                issues.append("capture audit did not pass")
            if record.get("text_layout_warnings"):
                issues.append("record reports text-layout warnings")
            if record.get("geometry_layout_warnings"):
                issues.append("record reports geometry warnings")
            lineage = record.get("lineage")
            if not isinstance(lineage, dict) or not lineage.get("source_run_id"):
                issues.append("capture lineage is missing")
        # Move mode intentionally cancels an in-place Dashboard interaction;
        # the Dashboard remains visible by design.  Older v23 attempts called
        # that a close timeout even when the mode was restored successfully.
        if label in {"move-mode", "reviewer-find-environment"}:
            issues = [
                issue for issue in issues
                if issue != "Capture surface did not close within 1500 ms"
            ]
        surfaces[label] = {
            "status": "failed" if issues or reuse_barrier_issues else "passed",
            "issues": list(dict.fromkeys(issues)),
            "capture_id": record.get("capture_id") if record else None,
            "path": record.get("path") if record else None,
        }

    reusable = [
        label for label in expected
        if surfaces.get(label, {}).get("status") == "passed"
    ]
    recapture = [
        label for label in expected
        if label in requested and surfaces.get(label, {}).get("status") != "passed"
    ]
    return {
        "capture_contract_version": payload.get("capture_contract_version"),
        "capture_scope": payload.get("capture_scope", "full"),
        "global_issues": list(dict.fromkeys(global_issues)),
        "reuse_barrier_issues": list(dict.fromkeys(reuse_barrier_issues)),
        "manifest": str(manifest_path),
        "recapture_required": recapture,
        "requested_faces": requested,
        "reusable_faces": reusable,
        "status": "valid" if not global_issues and not recapture else "invalid",
        "surfaces": surfaces,
    }


def plan_incremental_capture(
    *,
    base_manifest: Path,
    current_render_inputs: Mapping[str, Any],
    expected_labels: Sequence[str],
    contract_version: int,
    explicit_surfaces: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the minimum safe recapture set for the current package."""

    base_path, base_payload = _load_manifest(base_manifest)
    base_report = surface_validation_report(base_path)
    explicit = {str(label) for label in explicit_surfaces}
    unknown = explicit - set(expected_labels)
    if unknown:
        raise CaptureEvidenceError(
            "Unknown capture surface(s): " + ", ".join(sorted(unknown))
        )
    records = {
        str(record.get("label", "")): record
        for record in base_payload.get("captures", ())
        if isinstance(record, dict)
    }
    current_surfaces = current_render_inputs.get("surfaces")
    if not isinstance(current_surfaces, dict):
        raise CaptureEvidenceError("Current render-input catalog is invalid")

    reusable: list[str] = []
    recapture: list[str] = []
    reasons: dict[str, list[str]] = {}
    compatibility: dict[str, list[dict[str, Any]]] = {}
    previous_surfaces = (
        base_payload.get("render_inputs", {}).get("surfaces", {})
        if isinstance(base_payload.get("render_inputs"), dict)
        else {}
    )
    contract_changed = base_payload.get("capture_contract_version") != contract_version
    global_invalid = bool(base_report.get("reuse_barrier_issues"))
    for label in expected_labels:
        label_reasons: list[str] = []
        if label in explicit:
            label_reasons.append("explicitly-requested")
        if contract_changed:
            label_reasons.append("capture-contract-changed")
        if global_invalid:
            label_reasons.append("base-run-global-failure")
        state = base_report.get("surfaces", {}).get(label, {})
        if state.get("status") != "passed":
            label_reasons.append("previous-evidence-invalid")
        record = records.get(label, {})
        current = current_surfaces.get(label, {})
        render_changed = record.get("render_input_digest") != current.get("digest")
        environment_changed = record.get("capture_environment_digest") != current.get(
            "environment_digest"
        )
        compatible_transition = False
        transitions: list[dict[str, Any]] = []
        if render_changed or environment_changed:
            previous = (
                previous_surfaces.get(label, {})
                if isinstance(previous_surfaces, dict) else {}
            )
            compatible_transition, transitions = _input_transition_compatibility(
                label=label,
                previous=previous,
                current=current,
            )
        if render_changed and not compatible_transition:
            label_reasons.append("render-inputs-changed")
        if environment_changed and not compatible_transition:
            label_reasons.append("capture-environment-changed")
        if compatible_transition:
            compatibility[label] = transitions
        if label_reasons:
            recapture.append(label)
            reasons[label] = list(dict.fromkeys(label_reasons))
        else:
            reusable.append(label)
    return {
        "base_manifest": str(base_path),
        "capture_contract_version": contract_version,
        "recapture_required": recapture,
        "reused": reusable,
        "reasons": reasons,
        "reuse_compatibility": compatibility,
        "status": "ready",
    }


def _record_digest(record: Mapping[str, Any]) -> str:
    normalized = copy.deepcopy(dict(record))
    normalized.pop("path", None)
    normalized.pop("lineage", None)
    return canonical_json_sha256(normalized)


def _copy_png(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def assemble_capture_manifest(
    *,
    base_manifest: Path,
    patch_manifest: Path,
    reuse_plan: Mapping[str, Any],
    current_render_inputs: Mapping[str, Any],
    output_dir: Path,
) -> Path:
    """Assemble latest valid records into one self-contained manifest."""

    base_path, base = _load_manifest(base_manifest)
    patch_path, patch = _load_manifest(patch_manifest)
    base_report = surface_validation_report(base_path)
    patch_report = surface_validation_report(patch_path)
    expected = [str(value) for value in patch.get("expected_faces", ())]
    if expected != [str(value) for value in base.get("expected_faces", ())]:
        raise CaptureEvidenceError("Base and patch manifests use different contracts")
    reusable = set(str(value) for value in reuse_plan.get("reused", ()))
    patch_requested = set(str(value) for value in patch.get("requested_faces", ()))
    base_records = {
        str(record.get("label", "")): record
        for record in base.get("captures", ())
        if isinstance(record, dict)
    }
    patch_records = {
        str(record.get("label", "")): record
        for record in patch.get("captures", ())
        if isinstance(record, dict)
    }
    current_surfaces = current_render_inputs.get("surfaces", {})
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    lineage_dir = output_dir / "lineage"
    lineage_dir.mkdir()

    source_manifest_hashes: dict[Path, str] = {}
    for source in (base_path, patch_path):
        digest = sha256_file(source)
        source_manifest_hashes[source] = digest
        shutil.copyfile(source, lineage_dir / f"manifest-{digest}.json")

    captures: list[dict[str, Any]] = []
    screenshots: list[str] = []
    captured_faces: list[str] = []
    reused_faces: list[str] = []
    failures: list[dict[str, str]] = []
    for capture_id, label in enumerate(expected, start=1):
        source_path: Path | None = None
        source_payload: dict[str, Any] | None = None
        source_record: dict[str, Any] | None = None
        evidence_status = ""
        if label in patch_requested:
            if patch_report.get("surfaces", {}).get(label, {}).get("status") == "passed":
                source_path = patch_path
                source_payload = patch
                source_record = patch_records.get(label)
                evidence_status = "captured"
                captured_faces.append(label)
            else:
                failures.append({
                    "label": label,
                    "reason": "Replacement capture did not pass; prior evidence was not reused",
                })
        elif label in reusable:
            if base_report.get("surfaces", {}).get(label, {}).get("status") == "passed":
                source_path = base_path
                source_payload = base
                source_record = base_records.get(label)
                evidence_status = "reused"
                reused_faces.append(label)
        if source_record is None or source_path is None or source_payload is None:
            if not any(item["label"] == label for item in failures):
                failures.append({"label": label, "reason": "No valid evidence is available"})
            continue
        source_png = _safe_manifest_path(source_record.get("path"), source_path.parent)
        if source_png is None or not source_png.is_file():
            failures.append({"label": label, "reason": "Source PNG is unavailable"})
            continue
        destination = output_dir / f"{capture_id:02d}-{label}.png"
        _copy_png(source_png, destination)
        copied_sha = sha256_file(destination)
        if copied_sha != source_record.get("png_sha256"):
            raise CaptureEvidenceError(f"Copied PNG hash changed for {label}")
        record = copy.deepcopy(source_record)
        record.update({
            "capture_id": capture_id,
            "evidence_status": evidence_status,
            "label": label,
            "path": str(destination),
            "png_sha256": copied_sha,
            "render_input_digest": current_surfaces.get(label, {}).get("digest"),
            "render_input_count": current_surfaces.get(label, {}).get("input_count"),
            "capture_environment_digest": current_surfaces.get(label, {}).get(
                "environment_digest"
            ),
            "lineage": {
                "evidence_status": evidence_status,
                "reuse_compatibility": list(
                    reuse_plan.get("reuse_compatibility", {}).get(label, ())
                ),
                "source_manifest_sha256": source_manifest_hashes[source_path],
                "source_package_sha256": source_record.get(
                    "source_package_sha256",
                    source_payload.get("production_package_sha256", ""),
                ),
                "source_record_sha256": _record_digest(source_record),
                "source_run_id": source_path.parent.name,
            },
        })
        captures.append(record)
        screenshots.append(str(destination))

    complete = not failures and len(captures) == len(expected)
    displays = list(dict.fromkeys(
        str(record.get("capture_display", ""))
        for record in captures
        if str(record.get("capture_display", "")) in {"primary", "secondary"}
    ))
    payload = copy.deepcopy(patch)
    payload.update({
        "capture_scope": "assembled",
        "capture_display": displays[0] if len(displays) == 1 else "mixed",
        "capture_displays": displays,
        "requested_faces": expected,
        "captured_faces": captured_faces,
        "reused_faces": reused_faces,
        "invalidated_faces": list(reuse_plan.get("recapture_required", ())),
        "screenshots": screenshots,
        "captures": captures,
        "failures": failures,
        "text_layout_warnings": [],
        "expected_count": len(expected),
        "fixture_validations_complete": complete,
        "scope_complete": complete,
        "complete": complete,
        "production_package_sha256": current_render_inputs.get(
            "production_archive_sha256"
        ),
        "capture_environment_digest": current_render_inputs.get(
            "environment_digest"
        ),
        "render_inputs": current_render_inputs,
        "source_manifests": [
            {
                "path": str(lineage_dir / f"manifest-{digest}.json"),
                "sha256": digest,
            }
            for digest in source_manifest_hashes.values()
        ],
    })
    manifest = output_dir / "manifest.json"
    atomic_json(manifest, payload)
    manifest_sha = sha256_file(manifest)
    atomic_json(output_dir / "capture-complete.json", {
        "complete": complete,
        "exit_code": 0 if complete else 1,
        "manifest": str(manifest),
        "manifest_sha256": manifest_sha,
        "scope_complete": complete,
    })
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("manifest", type=Path)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("base_manifest", type=Path)
    plan_parser.add_argument("render_inputs", type=Path)
    plan_parser.add_argument("--contract-version", type=int, required=True)
    plan_parser.add_argument("--surface", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "inspect":
        result = surface_validation_report(arguments.manifest)
    else:
        base_path, base = _load_manifest(arguments.base_manifest)
        del base_path
        current = json.loads(arguments.render_inputs.read_text(encoding="utf-8"))
        result = plan_incremental_capture(
            base_manifest=arguments.base_manifest,
            current_render_inputs=current,
            expected_labels=[str(value) for value in base.get("expected_faces", ())],
            contract_version=arguments.contract_version,
            explicit_surfaces=arguments.surface,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CaptureEvidenceError as error:
        print(json.dumps({"error": str(error), "status": "failed"}), file=sys.stderr)
        raise SystemExit(1)
