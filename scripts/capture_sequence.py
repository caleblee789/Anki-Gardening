#!/usr/bin/env python3
"""Run the repository-owned v25 incremental Garden capture pipeline."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.capture.contract import (
    CAPTURE_CONTRACT_PATH,
    compile_contract,
    contract_diff,
    load_compiled_contract,
)
from ankigarden.capture.lifecycle import build_capture_plan
from ankigarden.capture.model import RunGateResult
from ankigarden.capture.registry import REGISTRY
from scripts import capture_support as BASE

from scripts.capture_evidence import (
    CaptureEvidenceError,
    assemble_capture_manifest,
    atomic_json,
    build_render_input_catalog,
    canonical_json_sha256,
    plan_incremental_capture,
    recover_progress_manifest,
    sha256_file,
    surface_validation_report,
)
from scripts.validate_ui_capture import (
    CaptureValidationError,
    CONTACT_SHEET_FRAME_OUTLINE_WIDTH,
    CONTACT_SHEET_OUTLINE_WIDTH,
    CONTACT_SHEET_PADDING_LEGEND,
    CONTACT_SHEET_PREVIEW_FRAME_FILL,
    CONTACT_SHEET_PREVIEW_FRAME_OUTLINE,
    CONTACT_SHEET_PREVIEW_INSET,
    CONTACT_SHEET_QUALITY_STATUS,
    load_capture_contract,
    load_capture_scenario_contracts,
    load_dialog_scroll_capture_coverage,
    load_expected_renderer_families,
    validate_capture_manifest,
    validate_contact_sheet_set,
)


CaptureError = BASE.CaptureError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--anki-version", default="26.8")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--profile",
        choices=("representative", "full"),
        default="representative",
        help="representative preflight or full release evidence",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="check the contract, package boundary, and local prerequisites without writing",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the registry-derived execution plan without writing or launching Anki",
    )
    parser.add_argument(
        "--list-surfaces",
        action="store_true",
        help="list active surfaces and their profile membership without writing",
    )
    parser.add_argument(
        "--explain-surface",
        metavar="ID",
        help="print the complete registry entry and dependency digest for one surface",
    )
    parser.add_argument(
        "--diff-contract",
        type=Path,
        metavar="MANIFEST",
        help="compare a prior compiled contract or manifest snapshot without writing",
    )
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="run only the zero-surface clean-shutdown gate in a fresh process",
    )
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--inactivity-timeout", type=int, default=60)
    parser.add_argument("--no-secondary-monitor", action="store_true")
    parser.add_argument(
        "--reuse-from",
        dest="reuse_from",
        action="append",
        type=Path,
        default=[],
        help="Evidence manifest to consider, newest first; repeat as needed",
    )
    parser.add_argument(
        "--fresh-baseline",
        action="store_true",
        help=(
            "Skip historical evidence discovery and capture every surface in "
            "the selected profile with fresh run-level gates"
        ),
    )
    parser.add_argument(
        "--reuse-only-from",
        dest="reuse_only_from",
        action="append",
        type=Path,
        default=[],
        help=(
            "Reuse only the explicitly named evidence manifest(s), without "
            "scanning the shared evidence root; repeat as needed"
        ),
    )
    parser.add_argument(
        "--resume-from",
        dest="reuse_from",
        action="append",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--surface",
        action="append",
        default=[],
        help="Explicitly recapture one contract surface; repeat as needed",
    )
    parser.add_argument(
        "--foreground-policy",
        choices=("required-only", "never"),
        default="required-only",
    )
    parser.add_argument(
        "--defer-contact-sheets",
        action="store_true",
        help=(
            "Stop after assembling and validating raw PNGs so they can be "
            "reviewed before the one permitted contact-sheet render"
        ),
    )
    return parser


def _inspection_mode(arguments: argparse.Namespace) -> int | None:
    requested = [
        bool(arguments.doctor),
        bool(arguments.plan_only),
        bool(arguments.list_surfaces),
        bool(arguments.explain_surface),
        bool(arguments.diff_contract),
    ]
    if sum(requested) > 1:
        raise CaptureError("choose only one non-mutating inspection command")
    if not any(requested):
        return None

    if arguments.list_surfaces:
        print(json.dumps({
            "contract_version": 25,
            "profiles": {
                profile: list(REGISTRY.profile_labels(profile))
                for profile in ("representative", "full")
            },
            "surfaces": [
                {
                    "id": surface.stable_id,
                    "profiles": list(surface.profiles),
                    "renderer_family": surface.renderer_family,
                    "checkpoint_cohort": surface.checkpoint_cohort,
                }
                for surface in (
                    REGISTRY[stable_id]
                    for stable_id in REGISTRY.profile_labels("full")
                )
            ],
        }, indent=2, sort_keys=True))
        return 0

    if arguments.explain_surface:
        try:
            surface = REGISTRY[str(arguments.explain_surface)]
        except KeyError as error:
            raise CaptureError(str(error)) from error
        print(json.dumps({
            **surface.as_dict(),
            "dependency_digest": REGISTRY.surface_digest(surface.stable_id),
        }, indent=2, sort_keys=True))
        return 0

    if arguments.diff_contract:
        path = arguments.diff_contract.expanduser().resolve()
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CaptureError(f"could not read prior contract {path}: {error}") from error
        if not isinstance(previous, dict):
            raise CaptureError("prior contract must contain a JSON object")
        render_inputs = previous.get("render_inputs")
        snapshot = previous.get(
            "capture_contract_snapshot",
            render_inputs.get("capture_contract_snapshot")
            if isinstance(render_inputs, dict) else previous,
        )
        if not isinstance(snapshot, dict) or "surfaces" not in snapshot:
            raise CaptureError(
                "manifest has no capture_contract_snapshot; a digest alone cannot be diffed"
            )
        print(json.dumps(contract_diff(snapshot), indent=2, sort_keys=True))
        return 0

    if arguments.plan_only:
        plan = build_capture_plan(
            REGISTRY,
            profile=arguments.profile,
            requested=arguments.surface or None,
        )
        print(json.dumps({
            "profile": arguments.profile,
            "requested": list(plan.requested),
            "execution": list(plan.execution),
            "reused": list(plan.reused),
            "checkpoint_domains": [
                {"name": name, "surfaces": list(labels)}
                for name, labels in plan.cohorts
            ],
            "process_count": 1 if plan.execution else 0,
            "process_strategy": "single-session",
            "run_gate_process": "same-session-or-zero-surface-when-reused",
        }, indent=2, sort_keys=True))
        return 0

    current = compile_contract()
    issues: list[str] = []
    try:
        compiled = load_compiled_contract()
    except ValueError as error:
        compiled = {}
        issues.append(str(error))
    if compiled != current:
        issues.append(f"compiled contract is stale: {CAPTURE_CONTRACT_PATH}")
    repo = arguments.repo.expanduser().resolve()
    required = (
        repo / "scripts" / "package_addon.py",
        repo / "scripts" / "capture_sequence.py",
        repo / "ankigarden" / "capture_ui_faces.py",
        repo / "ankigarden" / "capture" / "runtime.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        issues.append("missing capture files: " + ", ".join(missing))
    production = repo / "dist" / "anki_garden.ankiaddon"
    production_capture_entries: list[str] = []
    if production.is_file():
        try:
            with zipfile.ZipFile(production) as archive:
                production_capture_entries = sorted(
                    name for name in archive.namelist()
                    if name == "capture_ui_faces.py" or name.startswith("capture/")
                )
        except zipfile.BadZipFile as error:
            issues.append(f"production archive is invalid: {error}")
        if production_capture_entries:
            issues.append("production archive contains capture-only entries")
    else:
        issues.append(f"production archive is missing: {production}")
    print(json.dumps({
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "contract_digest": current["contract_digest"],
        "surface_counts": {
            profile: current["profiles"][profile]["surface_count"]
            for profile in ("representative", "full")
        },
        "contact_sheet_page_counts": {
            profile: current["profiles"][profile]["contact_sheet_page_count"]
            for profile in ("representative", "full")
        },
        "production_capture_entries": production_capture_entries,
        "repository_owned_runner": True,
    }, indent=2, sort_keys=True))
    return 0 if not issues else 1


def _find_completion(capture_dir: Path) -> Path | None:
    matches = sorted(capture_dir.glob("*/capture-complete.json"))
    if len(matches) > 1:
        raise CaptureError(
            "Capture produced multiple session completion records: "
            + ", ".join(str(path.parent.name) for path in matches)
        )
    return matches[0] if matches else None


def _find_active_session(capture_dir: Path) -> Path | None:
    candidates = {
        path.parent.resolve()
        for pattern in ("*/manifest.partial.json", "*/capture-complete.json")
        for path in capture_dir.glob(pattern)
        if path.is_file()
    }
    if len(candidates) > 1:
        raise CaptureError(
            "Capture produced multiple active session directories: "
            + ", ".join(sorted(path.name for path in candidates))
        )
    return next(iter(candidates), None)


def _load_completion(path: Path) -> tuple[dict[str, Any], Path]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"Invalid capture completion record: {path}") from exc
    manifest = Path(str(payload.get("manifest", ""))).expanduser()
    if not manifest.is_absolute():
        manifest = path.parent / manifest
    manifest = manifest.resolve()
    if manifest.parent != path.parent.resolve() or not manifest.is_file():
        raise CaptureError("Capture completion references an invalid manifest")
    if payload.get("manifest_sha256") != sha256_file(manifest):
        raise CaptureError("Capture completion manifest hash does not match")
    return payload, manifest


def _wait_for_capture(
    process: subprocess.Popen[str],
    *,
    capture_dir: Path,
    timeout: int,
    inactivity_timeout: int,
    log_path: Path,
) -> tuple[dict[str, Any], Path, int, dict[str, Any]]:
    deadline = time.monotonic() + max(30, int(timeout))
    inactivity_deadline = time.monotonic() + max(30, int(inactivity_timeout))
    last_progress_ns = -1
    completion_path: Path | None = None
    while time.monotonic() < deadline:
        completion_path = _find_completion(capture_dir)
        if completion_path is not None:
            break
        active_session = _find_active_session(capture_dir)
        progress_paths = (
            [
                active_session / "manifest.partial.json",
                *(active_session / "progress").glob("*.json"),
            ]
            if active_session is not None else []
        )
        progress_ns = max(
            (
                path.stat().st_mtime_ns
                for path in progress_paths
                if path.is_file()
            ),
            default=-1,
        )
        if progress_ns > last_progress_ns:
            last_progress_ns = progress_ns
            inactivity_deadline = time.monotonic() + max(
                30,
                int(inactivity_timeout),
            )
        if process.poll() is not None:
            completion_path = _find_completion(capture_dir)
            if completion_path is None:
                break
            break
        if time.monotonic() >= inactivity_deadline:
            break
        time.sleep(0.1)
    if completion_path is None:
        reason = (
            "process-exit"
            if process.poll() is not None
            else "inactivity-timeout"
            if time.monotonic() >= inactivity_deadline
            else "absolute-timeout"
        )
        if process.poll() is None:
            BASE.stop_process(process)
        active_session = _find_active_session(capture_dir)
        partial = (
            active_session / "manifest.partial.json"
            if active_session is not None else capture_dir / "manifest.partial.json"
        )
        if not partial.is_file():
            raise CaptureError(
                f"Capture ended without atomic progress ({reason}); see {log_path}"
            )
        recovered = recover_progress_manifest(partial.parent)
        exit_code = int(process.returncode if process.returncode is not None else -1)
        lifecycle = {
            "status": "failed",
            "passed": False,
            "reason": reason,
            "process_exit_code": exit_code,
            "graceful_exit_timeout_seconds": 30,
        }
        return ({
            "complete": False,
            "exit_code": exit_code,
            "manifest": str(recovered),
            "scope_complete": False,
        }, recovered, exit_code, lifecycle)
    completion, manifest = _load_completion(completion_path)
    try:
        exit_code = process.wait(timeout=30)
        exited_naturally = True
    except subprocess.TimeoutExpired:
        BASE.stop_process(process)
        exit_code = int(process.returncode if process.returncode is not None else -1)
        exited_naturally = False
    intended = int(completion.get("exit_code", 1))
    shutdown_signal = abs(int(exit_code)) if exited_naturally and exit_code < 0 else None
    lifecycle_reason = (
        "graceful-process-exit"
        if exited_naturally and exit_code >= 0
        else "shutdown-signal"
        if exited_naturally and exit_code < 0
        else "shutdown-timeout"
    )
    lifecycle = {
        "status": "passed" if exited_naturally and exit_code >= 0 else "failed",
        "passed": bool(exited_naturally and exit_code >= 0),
        "reason": lifecycle_reason,
        "process_exit_code": exit_code,
        "shutdown_signal": shutdown_signal,
        "finalized_exit_code": intended,
        "graceful_exit_timeout_seconds": 30,
    }
    return completion, manifest, exit_code, lifecycle


def _annotate_process_lifecycle(
    manifest_path: Path,
    *,
    lifecycle: dict[str, Any],
    environment_digest: str,
) -> None:
    """Bind post-process shutdown evidence to an otherwise finalized attempt."""

    _path, payload = _load_manifest_for_runner(manifest_path)
    run_level = payload.get("run_level_evidence")
    if not isinstance(run_level, dict):
        run_level = {}
    render_inputs = payload.get("render_inputs")
    run_level_digest = (
        str(render_inputs.get("run_level_digest", ""))
        if isinstance(render_inputs, dict) else ""
    )
    run_level["clean_shutdown"] = {
        "required": True,
        "status": "passed" if lifecycle.get("passed") is True else "failed",
        "passed": lifecycle.get("passed") is True,
        "zero_surface": not bool(payload.get("requested_faces")),
        "capture_environment_digest": environment_digest,
        "run_level_digest": run_level_digest,
        "lifecycle": dict(lifecycle),
    }
    payload["run_level_evidence"] = run_level
    atomic_json(manifest_path, payload)
    completion_path = manifest_path.parent / "capture-complete.json"
    if completion_path.is_file():
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        completion["manifest_sha256"] = sha256_file(manifest_path)
        atomic_json(completion_path, completion)


def _load_manifest_for_runner(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path.expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureError(f"Invalid capture manifest: {resolved}") from error
    if not isinstance(payload, dict):
        raise CaptureError(f"Capture manifest is not an object: {resolved}")
    return resolved, payload


def _write_archive_once(
    capture_dir: Path,
    output_root: Path,
    stamp: str,
    *,
    package: Path,
) -> Path:
    archive_path = output_root / f"anki-garden-ui-faces-{stamp}.zip"
    temporary = archive_path.with_name(f".{archive_path.name}.tmp")
    excluded = package.resolve()
    with zipfile.ZipFile(temporary, "w") as archive:
        for path in sorted(capture_dir.rglob("*")):
            if not path.is_file() or path.resolve() == excluded:
                continue
            compression = (
                zipfile.ZIP_STORED
                if path.suffix.casefold() == ".png"
                else zipfile.ZIP_DEFLATED
            )
            archive.write(
                path,
                path.relative_to(output_root),
                compress_type=compression,
            )
    os.replace(temporary, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        corrupt = archive.testzip()
    if corrupt is not None:
        raise CaptureError(f"Evidence archive failed integrity at {corrupt}")
    return archive_path


def _discover_evidence_manifests(
    output_root: Path,
    explicit: Sequence[Path],
) -> list[Path]:
    """Return explicit then newest unambiguous local evidence.

    A finalized and recovered manifest in the same capture session are two
    competing authorities, not two reusable candidates. Likewise, two
    different auto-discovered manifests with the exact same filesystem
    recency have no defensible newest-first ordering. Both cases fail closed.
    Even byte-identical manifests can bind to different session-relative PNGs,
    completion sentinels, and lineage, so bytes alone cannot break a tie.
    """

    candidates: list[Path] = []
    for path in explicit:
        candidates.append(path.expanduser().resolve())
    discovered: list[Path] = []
    if output_root.is_dir():
        by_session: dict[Path, list[Path]] = {}
        for name in ("manifest.json", "manifest.recovered.json"):
            for path in output_root.rglob(name):
                if "lineage" in path.parts or not path.is_file():
                    continue
                resolved = path.resolve()
                by_session.setdefault(resolved.parent, []).append(resolved)
        ambiguous_sessions = {
            parent: paths
            for parent, paths in by_session.items()
            if len({path.name for path in paths}) > 1
        }
        if ambiguous_sessions:
            details = "; ".join(
                f"{parent}: {', '.join(sorted(path.name for path in paths))}"
                for parent, paths in sorted(
                    ambiguous_sessions.items(),
                    key=lambda item: str(item[0]),
                )
            )
            raise CaptureError(
                "Capture evidence has competing final and recovered manifests: "
                + details
            )
        discovered = [paths[0] for paths in by_session.values()]

    by_recency: dict[int, list[Path]] = {}
    for path in discovered:
        by_recency.setdefault(path.stat().st_mtime_ns, []).append(path)
    for modified_ns, paths in by_recency.items():
        if len(paths) > 1:
            raise CaptureError(
                "Capture evidence has multiple manifests with equal recency "
                f"{modified_ns}: "
                + ", ".join(sorted(str(path) for path in paths))
            )
    discovered = sorted(
        discovered,
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
        reverse=True,
    )
    candidates.extend(discovered)
    result: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _capture_reuse_plan(
    *,
    evidence_root: Path,
    explicit_manifests: Sequence[Path],
    explicit_only_manifests: Sequence[Path],
    current_render_inputs: dict[str, Any],
    expected_labels: Sequence[str],
    contract_version: int,
    contract_digest: str,
    profile: str,
    explicit_surfaces: Sequence[str],
    fresh_baseline: bool,
) -> tuple[list[Path], dict[str, Any]]:
    """Plan incremental reuse or one explicit, auditable fresh baseline."""

    if fresh_baseline:
        evidence_manifests: list[Path] = []
        selection_policy = {
            "mode": "fresh-baseline",
            "reason": "explicitly-requested-no-historical-reuse",
            "evidence_discovery_skipped": True,
        }
    elif explicit_only_manifests:
        evidence_manifests = list(dict.fromkeys(
            path.expanduser().resolve()
            for path in explicit_only_manifests
        ))
        selection_policy = {
            "mode": "explicit-only-reuse",
            "reason": "caller-supplied-manifests-only",
            "evidence_discovery_skipped": True,
        }
    else:
        evidence_manifests = _discover_evidence_manifests(
            evidence_root,
            explicit_manifests,
        )
        selection_policy = {
            "mode": "incremental-reuse",
            "reason": "newest-compatible-evidence-per-surface",
            "evidence_discovery_skipped": False,
        }
    reuse_plan = plan_incremental_capture(
        evidence_manifests=evidence_manifests,
        current_render_inputs=current_render_inputs,
        expected_labels=expected_labels,
        contract_version=contract_version,
        contract_digest=contract_digest,
        profile=profile,
        explicit_surfaces=explicit_surfaces,
    )
    reuse_plan["selection_policy"] = selection_policy
    return evidence_manifests, reuse_plan


# Frozen solely for recognizing and retaining historical v24 evidence.  v25
# capture, validation, and contact-sheet totals are registry-derived.
_PROFILE_EVIDENCE_COUNTS: dict[str, tuple[int, int]] = {
    "representative": (26, 4),
    "full": (126, 17),
}


def _report_path(value: object, *, relative_to: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = relative_to / candidate
    return candidate.resolve()


def _json_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _ordered_group_labels(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    labels: list[str] = []
    for group in value:
        if not isinstance(group, dict) or not isinstance(group.get("labels"), list):
            return None
        group_labels = group["labels"]
        if not group_labels or any(not isinstance(label, str) for label in group_labels):
            return None
        labels.extend(group_labels)
    return labels


def _valid_evidence_archive(path: Path, expected_sha256: object) -> bool:
    if (
        path.is_symlink()
        or not path.is_file()
        or not isinstance(expected_sha256, str)
        or BASE.PACKAGE_SHA256.fullmatch(expected_sha256) is None
        or sha256_file(path) != expected_sha256
    ):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or archive.testzip() is not None:
                return False
            for member in members:
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    return False
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False
    return True


def _profile_complete_capture_stamp(
    path: Path,
    output_root: Path,
) -> str | None:
    """Recognize one complete relocatable v25 profile run for retention."""

    if path.is_symlink() or not path.is_dir():
        return None
    match = BASE.CAPTURE_SEQUENCE_NAME.fullmatch(path.name)
    if match is None:
        return None
    stamp = str(match.groupdict().get("stamp", ""))
    try:
        datetime.strptime(stamp, BASE.CAPTURE_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None
    report_path = path / "capture-report.json"
    report = _json_object(report_path)
    if report is None or report.get("capture_complete") is not True:
        return None
    profile = str(report.get("capture_profile", ""))
    report_version = int(report.get("capture_contract_version", 0) or 0)
    if report_version == 25:
        try:
            compiled_contract = load_compiled_contract()
            profile_contract = compiled_contract["profiles"][profile]
            expected_screenshots = int(profile_contract["surface_count"])
            expected_sheets = int(profile_contract["contact_sheet_page_count"])
        except (KeyError, TypeError, ValueError):
            return None
    elif report_version == 24 and profile in _PROFILE_EVIDENCE_COUNTS:
        expected_screenshots, expected_sheets = _PROFILE_EVIDENCE_COUNTS[profile]
    else:
        return None
    if output_root.name != profile:
        return None
    screenshots = report.get("screenshots")
    contact_sheets = report.get("contact_sheets")
    if (
        not isinstance(report.get("capture_contract_digest"), str)
        or BASE.PACKAGE_SHA256.fullmatch(
            str(report.get("capture_contract_digest", ""))
        ) is None
        or report.get("screenshot_count") != expected_screenshots
        or not isinstance(screenshots, list)
        or len(screenshots) != expected_screenshots
        or report.get("contact_sheet_count") != expected_sheets
        or not isinstance(contact_sheets, list)
        or len(contact_sheets) != expected_sheets
        or type(report.get("text_layout_warning_count")) is not int
        or int(report.get("text_layout_warning_count", -1)) < 0
        or report.get("quality_status") not in {"clean", "review-required"}
        or not isinstance(report.get("package_version"), str)
        or not str(report.get("package_version", "")).strip()
        or not isinstance(report.get("package_sha256"), str)
        or BASE.PACKAGE_SHA256.fullmatch(str(report.get("package_sha256"))) is None
    ):
        return None

    run_root = path.resolve()
    manifest = _report_path(report.get("manifest"), relative_to=run_root)
    if (
        manifest is None
        or manifest.is_symlink()
        or not manifest.is_file()
        or run_root not in manifest.parents
    ):
        return None
    manifest_payload = _json_object(manifest)
    if manifest_payload is None:
        return None
    if report_version == 25:
        try:
            contract = load_capture_contract(
                REPO_ROOT / "ankigarden" / "capture" / "runtime.py",
                profile=profile,
            )
        except (OSError, CaptureValidationError, ValueError):
            return None
        expected_labels = list(contract.labels)
        expected_contract_digest = contract.digest
    else:
        raw_expected = manifest_payload.get("expected_faces")
        if not isinstance(raw_expected, list) or any(
            not isinstance(label, str) or not label for label in raw_expected
        ):
            return None
        expected_labels = list(raw_expected)
        expected_contract_digest = str(report.get("capture_contract_digest", ""))
    capture_records = manifest_payload.get("captures")
    manifest_screenshots = manifest_payload.get("screenshots")
    captured_faces = manifest_payload.get("captured_faces")
    reused_faces = manifest_payload.get("reused_faces")
    if (
        len(expected_labels) != expected_screenshots
        or manifest_payload.get("capture_contract_version") != report_version
        or manifest_payload.get("capture_contract_digest") != expected_contract_digest
        or report.get("capture_contract_digest") != expected_contract_digest
        or manifest_payload.get("capture_profile") != profile
        or manifest_payload.get("complete") is not True
        or manifest_payload.get("scope_complete") is not True
        or manifest_payload.get("capture_scope") not in {"full", "assembled"}
        or manifest_payload.get("expected_count") != expected_screenshots
        or manifest_payload.get("expected_faces") != expected_labels
        or manifest_payload.get("requested_faces") != expected_labels
        or not isinstance(capture_records, list)
        or len(capture_records) != expected_screenshots
        or [
            record.get("label") if isinstance(record, dict) else None
            for record in capture_records
        ] != expected_labels
        or not isinstance(manifest_screenshots, list)
        or len(manifest_screenshots) != expected_screenshots
        or not isinstance(captured_faces, list)
        or not isinstance(reused_faces, list)
        or sorted(captured_faces + reused_faces) != sorted(expected_labels)
        or len(captured_faces) + len(reused_faces) != expected_screenshots
        or _ordered_group_labels(report.get("capture_groups")) != expected_labels
        or _ordered_group_labels(manifest_payload.get("capture_groups"))
        != expected_labels
    ):
        return None
    completion = _json_object(manifest.parent / "capture-complete.json")
    if completion is None:
        return None
    completion_manifest = _report_path(
        completion.get("manifest"),
        relative_to=manifest.parent,
    )
    if (
        completion.get("complete") is not True
        or completion.get("scope_complete") is not True
        or completion.get("exit_code") != 0
        or completion_manifest != manifest
        or completion.get("manifest_sha256") != sha256_file(manifest)
    ):
        return None
    try:
        surface_report = surface_validation_report(manifest)
    except CaptureEvidenceError:
        return None
    if (
        surface_report.get("status") != "valid"
        or surface_report.get("capture_profile") != profile
        or surface_report.get("reusable_faces") != expected_labels
    ):
        return None
    release_validation = report.get("release_validation")
    if (
        not isinstance(release_validation, dict)
        or release_validation.get("status") != "valid"
        or release_validation.get("capture_contract_version") != report_version
        or release_validation.get("capture_profile") != profile
        or release_validation.get("capture_count") != expected_screenshots
    ):
        return None
    resolved_screenshots: list[Path] = []
    for report_value, manifest_value in zip(screenshots, manifest_screenshots):
        manifest_screenshot = _report_path(
            manifest_value,
            relative_to=manifest.parent,
        )
        report_screenshot = _report_path(
            report_value,
            relative_to=manifest.parent,
        )
        if manifest_screenshot != report_screenshot:
            return None
        screenshot = report_screenshot
        if (
            screenshot is None
            or screenshot.is_symlink()
            or run_root not in screenshot.parents
            or not BASE._is_complete_png(screenshot)
        ):
            return None
        resolved_screenshots.append(screenshot)
    if len(resolved_screenshots) != len(set(resolved_screenshots)):
        return None

    contact_root = (output_root / "contact-sheets").resolve()
    resolved_sheets: list[Path] = []
    for value in contact_sheets:
        sheet = _report_path(value, relative_to=output_root)
        if (
            sheet is None
            or sheet.is_symlink()
            or contact_root not in sheet.parents
            or not BASE._is_complete_png(sheet)
        ):
            return None
        resolved_sheets.append(sheet)
    if len(resolved_sheets) != len(set(resolved_sheets)):
        return None
    contact_index = _report_path(
        report.get("contact_sheet_index"),
        relative_to=output_root,
    )
    if (
        contact_index is None
        or contact_index.is_symlink()
        or not contact_index.is_file()
        or contact_root not in contact_index.parents
    ):
        return None
    contact_payload = _json_object(contact_index)
    if contact_payload is None:
        return None
    pages = contact_payload.get("pages")
    if (
            contact_payload.get("complete") is not True
            or contact_payload.get("capture_profile") != profile
            or contact_payload.get("capture_contract_digest")
            != expected_contract_digest
        or contact_payload.get("page_count") != expected_sheets
        or contact_payload.get("surface_count") != expected_screenshots
        or not isinstance(pages, list)
        or len(pages) != expected_sheets
    ):
        return None
    indexed_sheets: list[Path] = []
    counted_surfaces = 0
    for page_number, page in enumerate(pages, start=1):
        if not isinstance(page, dict) or page.get("page") != page_number:
            return None
        page_surfaces = page.get("surface_count")
        if type(page_surfaces) is not int or page_surfaces < 1:
            return None
        counted_surfaces += page_surfaces
        sheet = _report_path(page.get("file"), relative_to=contact_index.parent)
        if (
            sheet is None
            or sheet.parent != contact_index.parent
            or not BASE._is_complete_png(sheet)
        ):
            return None
        indexed_sheets.append(sheet)
    contact_validation = report.get("contact_sheet_validation")
    validation_index = (
        _report_path(
            contact_validation.get("contact_sheet_set"),
            relative_to=contact_index.parent,
        )
        if isinstance(contact_validation, dict)
        else None
    )
    if (
        counted_surfaces != expected_screenshots
        or len(indexed_sheets) != len(set(indexed_sheets))
        or indexed_sheets != resolved_sheets
        or not isinstance(contact_validation, dict)
        or contact_validation.get("capture_profile") != profile
        or contact_validation.get("page_count") != expected_sheets
        or validation_index != contact_index
    ):
        return None

    archive = _report_path(report.get("archive"), relative_to=output_root)
    expected_archive = (
        output_root / f"{BASE.CAPTURE_ARCHIVE_PREFIX}{stamp}.zip"
    ).resolve()
    if (
        archive is None
        or archive != expected_archive
        or not _valid_evidence_archive(
            expected_archive,
            report.get("archive_sha256"),
        )
    ):
        return None
    return stamp


def _enforce_profile_capture_retention(
    output_root: Path,
    *,
    keep: int = BASE.CONTACT_SHEET_RETENTION,
) -> tuple[list[Path], list[Path], list[Path]]:
    """Retain three complete runs per profile and preserve every partial."""

    complete: list[tuple[str, Path]] = []
    for path in output_root.iterdir():
        stamp = _profile_complete_capture_stamp(path, output_root)
        if stamp is not None:
            complete.append((stamp, path))
    newest_first = sorted(
        complete,
        key=lambda item: (item[0], item[1].name),
        reverse=True,
    )
    retained = [path for _stamp, path in newest_first[: max(0, int(keep))]]
    pruned = [path for _stamp, path in newest_first[max(0, int(keep)) :]]
    pruned_archives: list[Path] = []
    root = output_root.resolve()
    for path in pruned:
        stamp = _profile_complete_capture_stamp(path, output_root)
        resolved = path.resolve()
        if path.is_symlink() or resolved.parent != root or stamp is None:
            raise CaptureError(f"Refusing to prune unexpected capture path: {path}")
        archive = output_root / f"{BASE.CAPTURE_ARCHIVE_PREFIX}{stamp}.zip"
        if archive.is_symlink() or not archive.is_file():
            raise CaptureError(f"Refusing to prune unexpected capture archive: {archive}")
        archive.unlink()
        pruned_archives.append(archive)
        shutil.rmtree(path)
    return retained, pruned, pruned_archives


def _enforce_profile_evidence_retention(
    output_root: Path,
) -> tuple[list[Path], list[Path], list[Path], list[Path], list[Path]]:
    """Prune paired runs before their contact sheets can lose completeness."""

    retained_runs, pruned_runs, pruned_archives = (
        _enforce_profile_capture_retention(output_root)
    )
    retained_sheets, pruned_sheets = BASE.enforce_contact_sheet_retention(
        output_root / "contact-sheets"
    )
    return (
        retained_runs,
        pruned_runs,
        pruned_archives,
        retained_sheets,
        pruned_sheets,
    )


def _clarify_contact_sheet_padding(
    *,
    payload: dict[str, Any],
    groups: list[tuple[str, list[str]]],
    contact_sheets: Sequence[Path],
    contact_sheet_index: Path,
    package_version: str,
) -> None:
    """Make sheet-only padding unmistakable without touching preview pixels."""

    try:
        from PIL import Image, ImageDraw, ImageOps, PngImagePlugin
    except ImportError as error:
        raise CaptureError("Pillow is required to clarify contact sheets") from error
    page_groups = BASE.paginate_contact_sheet_groups(groups)
    if len(page_groups) != len(contact_sheets):
        raise CaptureError("Contact-sheet pages changed during padding clarification")
    records = {
        str(record.get("label", "")): record
        for record in payload.get("captures", ())
        if isinstance(record, dict)
    }
    canvas_width = 3000
    margin = 64
    gutter = 32
    header_height = 250
    group_header_height = 84
    cell_height = 930
    group_gap = 30
    preview_inset = CONTACT_SHEET_PREVIEW_INSET
    columns = 2
    cell_width = (canvas_width - margin * 2 - gutter) // columns
    subtitle_font = BASE._load_font(31)
    meta_font = BASE._load_font(23)
    canvas = (8, 24, 20)
    accent = (210, 173, 103)
    muted = (159, 180, 167)
    cream = (216, 209, 190)
    screenshot_outline = (73, 102, 92)
    expected_count = len(payload.get("expected_faces", ()))
    contract_digest = str(payload.get("capture_contract_digest", ""))
    profile = str(payload.get("capture_profile", ""))
    for page_number, (page_path, page) in enumerate(
        zip(contact_sheets, page_groups),
        start=1,
    ):
        with Image.open(page_path) as opened:
            opened.load()
            metadata_values = dict(opened.text)
            sheet = opened.convert("RGB")
        draw = ImageDraw.Draw(sheet)
        page_surface_count = sum(len(labels) for _name, labels in page)
        # The old status could imply human acceptance. Replace it with the
        # exact automation boundary and add a visible padding legend.
        draw.rectangle((0, 108, canvas_width, 164), fill=canvas)
        draw.text(
            (margin, 119),
            (
                f"Release {package_version} · {page_surface_count} on this sheet · "
                f"{expected_count} total · {CONTACT_SHEET_QUALITY_STATUS}"
            ),
            font=subtitle_font,
            fill=accent,
        )
        legend_copy = "Cream swatch = contact-sheet padding outside captured UI"
        legend_box = draw.textbbox((0, 0), legend_copy, font=meta_font)
        legend_width = legend_box[2] - legend_box[0]
        legend_x = canvas_width - margin - legend_width
        draw.rectangle((legend_x - 44, 174, legend_x - 14, 202), fill=cream)
        draw.text((legend_x, 177), legend_copy, font=meta_font, fill=muted)

        y = header_height
        for _group_name, labels in page:
            y += group_header_height
            for group_index, label in enumerate(labels):
                record = records.get(label)
                if record is None:
                    raise CaptureError(f"Contact-sheet record disappeared: {label}")
                row = group_index // columns
                column = group_index % columns
                x = margin + column * (cell_width + gutter)
                tile_y = y + row * cell_height
                preview_box = (
                    x + 22,
                    tile_y + 110,
                    x + cell_width - 22,
                    tile_y + cell_height - 40,
                )
                draw.rounded_rectangle(
                    preview_box,
                    radius=12,
                    fill=CONTACT_SHEET_PREVIEW_FRAME_FILL,
                    outline=CONTACT_SHEET_PREVIEW_FRAME_OUTLINE,
                    width=CONTACT_SHEET_FRAME_OUTLINE_WIDTH,
                )
                with Image.open(Path(str(record["path"]))) as opened_source:
                    opened_source.load()
                    source = ImageOps.exif_transpose(opened_source)
                    max_width = preview_box[2] - preview_box[0] - preview_inset * 2
                    max_height = preview_box[3] - preview_box[1] - preview_inset * 2
                    preview = ImageOps.contain(
                        source,
                        (min(source.width, max_width), min(source.height, max_height)),
                        method=Image.Resampling.LANCZOS,
                    )
                preview_x = (
                    preview_box[0]
                    + (preview_box[2] - preview_box[0] - preview.width) // 2
                )
                preview_y = preview_box[1] + preview_inset
                # Draw each line wholly outside the pasted screenshot. The raw
                # pixels remain byte-derived from their manifest-owned source.
                for offset in range(1, CONTACT_SHEET_OUTLINE_WIDTH + 1):
                    draw.rectangle(
                        (
                            preview_x - offset,
                            preview_y - offset,
                            preview_x + preview.width + offset - 1,
                            preview_y + preview.height + offset - 1,
                        ),
                        outline=screenshot_outline,
                        width=1,
                    )
                sheet.paste(preview.convert("RGB"), (preview_x, preview_y))
            y += ((len(labels) + columns - 1) // columns) * cell_height + group_gap

        metadata_values.update({
            "Capture profile": profile,
            "Capture contract digest": contract_digest,
            "Padding legend": CONTACT_SHEET_PADDING_LEGEND,
            "Quality status": CONTACT_SHEET_QUALITY_STATUS,
        })
        png_info = PngImagePlugin.PngInfo()
        for key, value in metadata_values.items():
            png_info.add_text(str(key), str(value))
        temporary = page_path.with_name(f".{page_path.name}.tmp")
        sheet.save(temporary, format="PNG", optimize=True, pnginfo=png_info)
        os.replace(temporary, page_path)

    index_payload = json.loads(contact_sheet_index.read_text(encoding="utf-8"))
    index_payload.update({
        "capture_profile": profile,
        "capture_contract_digest": contract_digest,
        "padding_legend": CONTACT_SHEET_PADDING_LEGEND,
        "quality_status": CONTACT_SHEET_QUALITY_STATUS,
    })
    atomic_json(contact_sheet_index, index_payload)


def _raw_failure_result(
    *,
    capture_dir: Path,
    manifest: Path,
    package: Path,
    production_package: Path,
    derivative: dict[str, Any],
    package_manifest: dict[str, Any],
    plan: dict[str, Any],
    surface_report: dict[str, Any],
    log_path: Path,
) -> int:
    report_path = capture_dir / "capture-report.json"
    report = {
        "capture_complete": False,
        "capture_contract_version": surface_report.get("capture_contract_version"),
        "capture_plan": plan,
        "capture_policy": plan.get("selection_policy"),
        "contact_sheet_count": 0,
        "contact_sheets": [],
        "log": str(log_path),
        "manifest": str(manifest),
        "package": str(package),
        "package_derivative": derivative,
        "package_sha256": sha256_file(package),
        "package_version": str(package_manifest.get("human_version", "unknown")),
        "production_package": str(production_package),
        "production_package_sha256": sha256_file(production_package),
        "quality_status": "review-required",
        "surface_validation": surface_report,
    }
    atomic_json(report_path, report)
    print(json.dumps({
        "capture_complete": False,
        "capture_dir": str(capture_dir),
        "capture_policy": plan.get("selection_policy"),
        "contact_sheet_count": 0,
        "manifest": str(manifest),
        "recapture_required": surface_report.get("recapture_required", []),
        "report": str(report_path),
        "status": "review-required",
    }, sort_keys=True))
    return 1


def _run_capture_attempt(
    *,
    repo: Path,
    capture_dir: Path,
    package: Path,
    package_id: str,
    anki_version: str,
    stamp: str,
    profile: str,
    requested_faces: Sequence[str],
    invalidated_faces: Sequence[str],
    render_inputs_path: Path,
    production_package_sha256: str,
    environment_digest: str,
    foreground_policy: str,
    no_secondary_monitor: bool,
    timeout: int,
    inactivity_timeout: int,
    log_path: Path,
) -> tuple[Path, dict[str, Any]]:
    prepare = (
        Path.home()
        / ".codex"
        / "skills"
        / "launch-isolated-anki"
        / "scripts"
        / "prepare_fast_run.py"
    )
    if not prepare.is_file():
        raise CaptureError(f"Missing isolated-Anki helper: {prepare}")
    helper = [sys.executable, str(prepare)]
    seed_status = BASE.json_command(
        helper + ["seed-status", "--anki-version", anki_version],
        cwd=repo,
    )
    if seed_status.get("status") != "ready":
        raise CaptureError(f"The isolated Anki seed is not ready: {seed_status}")
    anki_profile = f"Capture {profile.title()} {stamp}"
    created = BASE.json_command(
        helper + [
            "create-run",
            "--anki-version",
            anki_version,
            "--profile",
            anki_profile,
        ],
        cwd=repo,
    )
    run_root = Path(str(created["run_root"])).resolve()
    BASE.extract_package(package, run_root / "addons21" / package_id)
    BASE.set_disposable_ui_scale(run_root)
    prelaunch = BASE.json_command(
        helper + ["verify-prelaunch", "--run-root", str(run_root)],
        cwd=repo,
    )
    if prelaunch.get("status") != "prelaunch-ready":
        raise CaptureError(f"The isolated Anki run is not ready: {prelaunch}")

    launch = created["launch"]
    environment = os.environ.copy()
    # This runner suppresses the add-on's ordinary source-checkout import while
    # planning. The disposable packaged Anki process must perform real startup.
    environment.pop("ANKI_GARDEN_SKIP_STARTUP", None)
    environment.update({str(key): str(value) for key, value in launch["env"].items()})
    environment.update({
        "ANKI_GARDEN_CAPTURE_UI_FACES": "1",
        "ANKI_GARDEN_CAPTURE_DIR": str(capture_dir),
        "ANKI_GARDEN_UI_CAPTURE_DIR": str(capture_dir),
        "ANKI_GARDEN_CAPTURE_PROFILE": profile,
        "ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE": "1",
        "ANKI_GARDEN_CAPTURE_SECOND_MONITOR": (
            "0" if no_secondary_monitor else "1"
        ),
        "ANKI_GARDEN_CAPTURE_SURFACES_JSON": json.dumps(list(requested_faces)),
        "ANKI_GARDEN_INVALIDATED_SURFACES_JSON": json.dumps(
            list(invalidated_faces)
        ),
        "ANKI_GARDEN_RENDER_INPUTS_PATH": str(render_inputs_path),
        "ANKI_GARDEN_PRODUCTION_PACKAGE_SHA256": production_package_sha256,
        "ANKI_GARDEN_CAPTURE_ENVIRONMENT_DIGEST": environment_digest,
        "ANKI_GARDEN_CAPTURE_FOREGROUND_POLICY": foreground_policy,
        "QT_SCALE_FACTOR": str(BASE.CAPTURE_UI_SCALE),
    })
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
                # Python ignores SIGPIPE, but Popen restores it by default
                # before exec. The native macOS Anki launcher does not
                # consistently reinstall that handler, so a closed internal
                # WebEngine/media pipe can otherwise terminate the whole
                # disposable capture process with exit -13.
                restore_signals=False,
            )
            _completion, attempt_manifest, _exit_code, lifecycle = _wait_for_capture(
                process,
                capture_dir=capture_dir,
                timeout=timeout,
                inactivity_timeout=inactivity_timeout,
                log_path=log_path,
            )
    finally:
        if process is not None and process.poll() is None:
            BASE.stop_process(process)
    _annotate_process_lifecycle(
        attempt_manifest,
        lifecycle=lifecycle,
        environment_digest=environment_digest,
    )
    return attempt_manifest, lifecycle


def _gate_result(
    manifest_path: Path,
    *,
    profile: str,
    production_package_sha256: str,
    contract_digest: str,
    environment_digest: str,
    run_level_digest: str,
) -> RunGateResult:
    """Validate one zero-surface shutdown process against the release inputs."""

    _path, payload = _load_manifest_for_runner(manifest_path)
    run_level = payload.get("run_level_evidence")
    if not isinstance(run_level, dict):
        run_level = {}
    memory = run_level.get("dialog_memory_probe")
    shutdown = run_level.get("clean_shutdown")
    memory_payload = dict(memory) if isinstance(memory, dict) else {}
    shutdown_payload = dict(shutdown) if isinstance(shutdown, dict) else {}
    issues: list[str] = []
    if payload.get("requested_faces") != []:
        issues.append("gate process was not zero-surface")
    if payload.get("production_package_sha256") != production_package_sha256:
        issues.append("gate package binding did not match")
    if payload.get("capture_contract_digest") != contract_digest:
        issues.append("gate contract binding did not match")
    if payload.get("capture_environment_digest") != environment_digest:
        issues.append("gate environment binding did not match")
    if not (
        shutdown_payload.get("passed") is True
        and shutdown_payload.get("zero_surface") is True
        and shutdown_payload.get("capture_environment_digest") == environment_digest
        and shutdown_payload.get("run_level_digest") == run_level_digest
    ):
        issues.append("clean shutdown evidence did not pass")
    return RunGateResult(
        package_sha256=production_package_sha256,
        contract_digest=contract_digest,
        environment_digest=environment_digest,
        evidence_digest=canonical_json_sha256(run_level),
        memory_evidence=memory_payload,
        shutdown_evidence=shutdown_payload,
        release_eligible=not issues,
        issues=tuple(issues),
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    inspection_result = _inspection_mode(arguments)
    if inspection_result is not None:
        return inspection_result
    if arguments.gate_only:
        if (
            arguments.surface
            or arguments.reuse_from
            or arguments.reuse_only_from
            or arguments.fresh_baseline
            or arguments.defer_contact_sheets
        ):
            raise CaptureError(
                "--gate-only cannot be combined with capture or reuse options"
            )
        arguments.profile = "full"
    if arguments.fresh_baseline and arguments.reuse_from:
        raise CaptureError(
            "--fresh-baseline cannot be combined with --reuse-from"
        )
    if arguments.fresh_baseline and arguments.surface:
        raise CaptureError(
            "--fresh-baseline cannot be combined with --surface"
        )
    if arguments.fresh_baseline and arguments.reuse_only_from:
        raise CaptureError(
            "--fresh-baseline cannot be combined with --reuse-only-from"
        )
    if arguments.reuse_from and arguments.reuse_only_from:
        raise CaptureError(
            "--reuse-from cannot be combined with --reuse-only-from"
        )
    repo = arguments.repo.expanduser().resolve()
    capture_bootstrap = repo / "ankigarden" / "capture_ui_faces.py"
    capture_source = repo / "ankigarden" / "capture" / "runtime.py"
    validator_source = repo / "scripts" / "validate_ui_capture.py"
    if not (
        (repo / "scripts" / "package_addon.py").is_file()
        and capture_bootstrap.is_file()
        and capture_source.is_file()
    ):
        raise CaptureError(f"{repo} is not an Anki Garden repository with UI capture support")
    production_package = (repo / "dist" / "anki_garden.ankiaddon").resolve()
    if production_package.is_symlink() or not production_package.is_file():
        raise CaptureError(
            f"Build the exact production archive before capture: {production_package}"
        )

    evidence_root = (
        arguments.output_dir or repo / "build" / "ui-face-captures"
    ).expanduser().resolve()
    output_root = evidence_root / arguments.profile
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = output_root / f"capture-sequence-{stamp}"
    capture_dir.mkdir(parents=True, exist_ok=False)
    log_path = capture_dir / "attempt-log-index.json"
    python = BASE.command_python(repo)

    package, package_id, package_manifest = BASE.archive_package(
        repo,
        python,
        capture_dir / "anki_garden_capture.ankiaddon",
    )
    package_sha256 = BASE.file_hash(package)
    derivative = BASE.capture_derivative_report(repo, production_package, package)
    if derivative["capture_archive_sha256"] != package_sha256:
        raise CaptureError("Capture derivative report does not match the capture archive")
    production_package_sha256 = str(derivative["production_archive_sha256"])

    compiled_contract = load_compiled_contract()
    active_surface_specs = {
        str(row["id"]): row
        for row in compiled_contract["surfaces"]
        if isinstance(row, dict) and row.get("active") is True
    }
    contract = load_capture_contract(capture_source, profile=arguments.profile)
    surface_specs = {
        label: active_surface_specs[label]
        for label in contract.labels
    }
    renderer_families = load_expected_renderer_families(
        capture_source,
        contract=contract,
    )
    scenario_contracts = load_capture_scenario_contracts(
        capture_source,
        contract=contract,
    )
    dialog_scroll_contract = load_dialog_scroll_capture_coverage(
        capture_source,
        contract=contract,
    )
    render_inputs = build_render_input_catalog(
        production_package,
        capture_source=capture_source,
        validator_source=validator_source,
        labels=contract.labels,
        renderer_families=renderer_families,
        profile=arguments.profile,
        contract_digest=contract.digest,
        scenario_contracts=scenario_contracts,
        runtime_inputs={
            "anki_version": str(arguments.anki_version),
            "architecture": platform.machine(),
            "capture_scale_factor": str(BASE.CAPTURE_UI_SCALE),
            "foreground_policy": arguments.foreground_policy,
            "platform": sys.platform,
        },
        dialog_scroll_contract=dialog_scroll_contract,
        surface_specs=surface_specs,
    )
    render_inputs["capture_contract_snapshot"] = compiled_contract
    render_inputs_path = capture_dir / "render-inputs.json"
    atomic_json(render_inputs_path, render_inputs)

    if arguments.gate_only:
        gate_root = capture_dir / "attempts" / "00-run-gate"
        gate_root.mkdir(parents=True)
        gate_log = gate_root / "anki.log"
        timeout = int(arguments.timeout) if arguments.timeout is not None else 360
        gate_manifest, lifecycle = _run_capture_attempt(
            repo=repo,
            capture_dir=gate_root,
            package=package,
            package_id=package_id,
            anki_version=arguments.anki_version,
            stamp=f"{stamp}-gate",
            profile=arguments.profile,
            requested_faces=(),
            invalidated_faces=(),
            render_inputs_path=render_inputs_path,
            production_package_sha256=production_package_sha256,
            environment_digest=str(render_inputs["environment_digest"]),
            foreground_policy=arguments.foreground_policy,
            no_secondary_monitor=arguments.no_secondary_monitor,
            timeout=timeout,
            inactivity_timeout=arguments.inactivity_timeout,
            log_path=gate_log,
        )
        gate = _gate_result(
            gate_manifest,
            profile=arguments.profile,
            production_package_sha256=production_package_sha256,
            contract_digest=contract.digest,
            environment_digest=str(render_inputs["environment_digest"]),
            run_level_digest=str(render_inputs["run_level_digest"]),
        )
        gate_report = {
            **gate.as_dict(),
            "manifest": str(gate_manifest),
            "log": str(gate_log),
            "process_lifecycle": lifecycle,
            "capture_package_sha256": package_sha256,
        }
        atomic_json(capture_dir / "run-gate-report.json", gate_report)
        print(json.dumps({
            "status": "passed" if gate.release_eligible else "failed",
            "capture_dir": str(capture_dir),
            "gate_report": str(capture_dir / "run-gate-report.json"),
            "issues": list(gate.issues),
            "release_eligible": gate.release_eligible,
        }, sort_keys=True))
        return 0 if gate.release_eligible else 1

    evidence_manifests, reuse_plan = _capture_reuse_plan(
        # Incremental mode searches the shared root so a normal full run
        # automatically sees exact overlapping evidence from the sibling
        # representative preflight. Explicit fresh-baseline mode skips that scan.
        evidence_root=evidence_root,
        explicit_manifests=arguments.reuse_from,
        explicit_only_manifests=arguments.reuse_only_from,
        current_render_inputs=render_inputs,
        expected_labels=contract.labels,
        contract_version=contract.version,
        contract_digest=contract.digest,
        profile=arguments.profile,
        explicit_surfaces=arguments.surface,
        fresh_baseline=arguments.fresh_baseline,
    )
    requested_faces = list(reuse_plan["recapture_required"])
    atomic_json(capture_dir / "capture-plan.json", reuse_plan)
    run_level_required = bool(reuse_plan.get("run_level_recapture_required"))
    launch_required = bool(requested_faces or run_level_required)

    attempt_manifests: list[Path] = []
    attempt_rows: list[dict[str, Any]] = []
    if launch_required:
        capture_plan = build_capture_plan(
            REGISTRY,
            profile=arguments.profile,
            requested=requested_faces,
        )
        session_faces = tuple(capture_plan.requested)
        session_name = "capture-session" if session_faces else "run-gate"
        attempt_root = capture_dir / "attempts" / f"01-{session_name}"
        attempt_root.mkdir(parents=True)
        attempt_log = attempt_root / "anki.log"
        timeout = (
            int(arguments.timeout)
            if arguments.timeout is not None
            else 180 + 8 * len(session_faces)
        )
        attempt_manifest, lifecycle = _run_capture_attempt(
            repo=repo,
            capture_dir=attempt_root,
            package=package,
            package_id=package_id,
            anki_version=arguments.anki_version,
            stamp=f"{stamp}-{session_name}",
            profile=arguments.profile,
            requested_faces=session_faces,
            invalidated_faces=session_faces,
            render_inputs_path=render_inputs_path,
            production_package_sha256=production_package_sha256,
            environment_digest=str(render_inputs["environment_digest"]),
            foreground_policy=arguments.foreground_policy,
            no_secondary_monitor=arguments.no_secondary_monitor,
            timeout=timeout,
            inactivity_timeout=arguments.inactivity_timeout,
            log_path=attempt_log,
        )
        attempt_manifests.append(attempt_manifest)
        attempt_rows.append({
            "session": session_name,
            "checkpoint_domains": [name for name, _faces in capture_plan.cohorts],
            "surfaces": list(session_faces),
            "manifest": str(attempt_manifest),
            "log": str(attempt_log),
            "process_lifecycle": lifecycle,
        })
        atomic_json(log_path, {"attempts": attempt_rows})
    else:
        atomic_json(log_path, {
            "attempts": [],
            "status": "no-launch-exact-evidence-reused",
        })

    if BASE.file_hash(package) != package_sha256:
        raise CaptureError("Capture package changed while capture was running")
    if BASE.file_hash(production_package) != production_package_sha256:
        raise CaptureError("Production package changed while capture was running")

    candidate_manifest = assemble_capture_manifest(
        patch_manifests=attempt_manifests,
        evidence_manifests=evidence_manifests,
        reuse_plan=reuse_plan,
        current_render_inputs=render_inputs,
        output_dir=capture_dir / "assembled",
    )
    surface_report = surface_validation_report(candidate_manifest)
    candidate_payload = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if candidate_payload.get("complete") is not True or surface_report.get("status") != "valid":
        return _raw_failure_result(
            capture_dir=capture_dir,
            manifest=candidate_manifest,
            package=package,
            production_package=production_package,
            derivative=derivative,
            package_manifest=package_manifest,
            plan=reuse_plan,
            surface_report=surface_report,
            log_path=log_path,
        )

    try:
        release_validation = validate_capture_manifest(
            candidate_manifest,
            capture_source=capture_source,
        )
    except CaptureValidationError as error:
        surface_report["independent_errors"] = list(error.issues)
        surface_report["status"] = "invalid"
        return _raw_failure_result(
            capture_dir=capture_dir,
            manifest=candidate_manifest,
            package=package,
            production_package=production_package,
            derivative=derivative,
            package_manifest=package_manifest,
            plan=reuse_plan,
            surface_report=surface_report,
            log_path=log_path,
        )

    payload = candidate_payload
    if arguments.defer_contact_sheets:
        report_path = capture_dir / "capture-report.json"
        report = {
            "archive": None,
            "capture_complete": False,
            "capture_contract_version": contract.version,
            "capture_contract_digest": contract.digest,
            "capture_plan": reuse_plan,
            "capture_policy": reuse_plan.get("selection_policy"),
            "capture_profile": arguments.profile,
            "capture_scope": payload.get("capture_scope"),
            "captured_faces": payload.get("captured_faces", []),
            "reused_faces": payload.get("reused_faces", []),
            "contact_sheet_count": 0,
            "contact_sheets": [],
            "log": str(log_path),
            "manifest": str(candidate_manifest),
            "package": str(package),
            "package_derivative": derivative,
            "package_sha256": package_sha256,
            "package_version": str(package_manifest.get("human_version", "unknown")),
            "production_package": str(production_package),
            "production_package_sha256": production_package_sha256,
            "quality_status": "raw-review-ready",
            "release_ready": False,
            "release_validation": release_validation,
            "surface_validation": surface_report,
        }
        atomic_json(report_path, report)
        print(json.dumps({
            "capture_complete": False,
            "capture_dir": str(capture_dir),
            "capture_policy": reuse_plan.get("selection_policy"),
            "captured_faces": report["captured_faces"],
            "contact_sheet_count": 0,
            "manifest": str(candidate_manifest),
            "quality_status": "raw-review-ready",
            "report": str(report_path),
            "reused_faces": report["reused_faces"],
            "status": "raw-review-ready",
        }, sort_keys=True))
        return 0

    payload["manifest"] = str(candidate_manifest)
    groups = BASE.capture_groups(payload)
    # The assembled manifest intentionally stores movable relative paths.
    # The legacy sheet renderer receives an in-memory absolute-path view only;
    # the evidence manifest itself remains relocatable.
    render_payload = json.loads(json.dumps(payload))
    render_payload["manifest"] = str(candidate_manifest)
    render_payload["screenshots"] = [
        str((candidate_manifest.parent / str(value)).resolve())
        if not Path(str(value)).is_absolute() else str(value)
        for value in payload.get("screenshots", ())
    ]
    for record in render_payload.get("captures", ()):
        if not isinstance(record, dict):
            continue
        value = Path(str(record.get("path", "")))
        if not value.is_absolute():
            record["path"] = str((candidate_manifest.parent / value).resolve())
    contact_sheet_set, contact_sheets, contact_sheet_index = BASE.render_contact_sheets(
        payload=render_payload,
        groups=groups,
        package_manifest=package_manifest,
        package_sha256=package_sha256,
        output_root=output_root,
        stamp=stamp,
    )
    _clarify_contact_sheet_padding(
        payload=render_payload,
        groups=groups,
        contact_sheets=contact_sheets,
        contact_sheet_index=contact_sheet_index,
        package_version=str(package_manifest.get("human_version", "unknown")),
    )
    contact_validation = validate_contact_sheet_set(
        contact_sheet_index,
        manifest_path=candidate_manifest,
        capture_source=capture_source,
    )
    retained_contact_sets: list[Path] = []
    pruned_contact_sets: list[Path] = []

    report_path = capture_dir / "capture-report.json"
    screenshots = [str(value) for value in payload.get("screenshots", ())]
    report = {
        "archive": str(output_root / f"anki-garden-ui-faces-{stamp}.zip"),
        "capture_complete": True,
        "capture_contract_version": contract.version,
        "capture_contract_digest": contract.digest,
        "capture_display": payload.get("capture_display"),
        "capture_displays": payload.get("capture_displays", []),
        "capture_groups": [
            {"name": name, "labels": labels}
            for name, labels in groups
        ],
        "capture_plan": reuse_plan,
        "capture_policy": reuse_plan.get("selection_policy"),
        "capture_profile": arguments.profile,
        "capture_scope": payload.get("capture_scope"),
        "captured_faces": payload.get("captured_faces", []),
        "reused_faces": payload.get("reused_faces", []),
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet": str(contact_sheets[0]),
        "contact_sheet_index": str(contact_sheet_index),
        "contact_sheet_set": str(contact_sheet_set),
        "contact_sheets": [str(path) for path in contact_sheets],
        "contact_sheet_validation": contact_validation,
        "log": str(log_path),
        "manifest": str(candidate_manifest),
        "package": str(package),
        "package_derivative": derivative,
        "package_sha256": package_sha256,
        "package_version": str(package_manifest.get("human_version", "unknown")),
        "production_package": str(production_package),
        "production_package_sha256": production_package_sha256,
        "pruned_contact_sheet_sets": [str(path) for path in pruned_contact_sets],
        "evidence_tier": (
            "final-release" if arguments.profile == "full" else "preflight"
        ),
        "quality_status": "review-required",
        "automated_release_gate_passed": arguments.profile == "full",
        "release_ready": False,
        "requested_scale_factor": payload.get("requested_scale_factor"),
        "release_validation": release_validation,
        "retained_contact_sheet_sets": [str(path) for path in retained_contact_sets],
        "screenshot_count": len(screenshots),
        "screenshots": screenshots,
        "surface_validation": surface_report,
        "audit_advisory_count": len(
            release_validation.get("audit_advisories", ())
        ),
        "text_layout_warning_count": len(
            payload.get("text_layout_warnings", ())
        ),
    }
    atomic_json(report_path, report)
    archive = _write_archive_once(
        capture_dir,
        output_root,
        stamp,
        package=package,
    )
    report["archive"] = str(archive)
    report["archive_sha256"] = sha256_file(archive)
    # The current report must bind the completed archive before it can enter
    # retention. Run pruning must happen while every paired contact-sheet set
    # still exists; pruning sheets first would make the oldest run look partial
    # and strand its directory and ZIP forever.
    atomic_json(report_path, report)
    (
        retained_runs,
        pruned_runs,
        pruned_archives,
        retained_contact_sets,
        pruned_contact_sets,
    ) = _enforce_profile_evidence_retention(
        output_root,
    )
    report["retained_capture_sets"] = [str(path) for path in retained_runs]
    report["pruned_capture_sets"] = [str(path) for path in pruned_runs]
    report["pruned_capture_archives"] = [str(path) for path in pruned_archives]
    report["retained_contact_sheet_sets"] = [
        str(path) for path in retained_contact_sets
    ]
    report["pruned_contact_sheet_sets"] = [
        str(path) for path in pruned_contact_sets
    ]
    atomic_json(report_path, report)
    print(json.dumps({
        "archive": str(archive),
        "archive_sha256": report["archive_sha256"],
        "capture_complete": True,
        "capture_dir": str(capture_dir),
        "capture_policy": reuse_plan.get("selection_policy"),
        "captured_faces": report["captured_faces"],
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_index": str(contact_sheet_index),
        "contact_sheets": report["contact_sheets"],
        "manifest": str(candidate_manifest),
        "package_sha256": package_sha256,
        "production_package_sha256": production_package_sha256,
        "evidence_tier": report["evidence_tier"],
        "quality_status": "review-required",
        "release_ready": report["release_ready"],
        "report": str(report_path),
        "reused_faces": report["reused_faces"],
        "screenshot_count": len(screenshots),
        "status": "completed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CaptureError,
        CaptureEvidenceError,
        CaptureValidationError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(json.dumps({"error": str(error), "status": "failed"}), file=sys.stderr)
        raise SystemExit(1)
