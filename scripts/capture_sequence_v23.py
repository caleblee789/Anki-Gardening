#!/usr/bin/env python3
"""Run the v23 incremental Anki Garden capture and final evidence pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.capture_evidence import (
    CaptureEvidenceError,
    assemble_capture_manifest,
    atomic_json,
    build_render_input_catalog,
    plan_incremental_capture,
    sha256_file,
    surface_validation_report,
)
from scripts.validate_ui_capture import (
    CaptureValidationError,
    load_capture_contract,
    load_expected_renderer_families,
    validate_capture_manifest,
    validate_contact_sheet_set,
)


def _load_skill_base() -> ModuleType:
    source = Path(
        os.environ.get(
            "ANKI_GARDEN_CAPTURE_SKILL_RUNNER",
            str(
                Path.home()
                / ".codex"
                / "skills"
                / "capture-sequence"
                / "scripts"
                / "capture_anki_garden.py"
            ),
        )
    ).expanduser().resolve()
    spec = importlib.util.spec_from_file_location("_anki_garden_capture_skill_base", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load capture skill runner: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_skill_base()
CaptureError = BASE.CaptureError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--anki-version", default="26.8")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--no-secondary-monitor", action="store_true")
    parser.add_argument("--resume-from", type=Path)
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


def _find_completion(capture_dir: Path) -> Path | None:
    matches = sorted(capture_dir.glob("*/capture-complete.json"))
    return matches[-1] if matches else None


def _load_completion(path: Path) -> tuple[dict[str, Any], Path]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"Invalid capture completion record: {path}") from exc
    manifest = Path(str(payload.get("manifest", ""))).expanduser().resolve()
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
    log_path: Path,
) -> tuple[dict[str, Any], Path, int]:
    deadline = time.monotonic() + max(30, int(timeout))
    completion_path: Path | None = None
    while time.monotonic() < deadline:
        completion_path = _find_completion(capture_dir)
        if completion_path is not None:
            break
        if process.poll() is not None:
            completion_path = _find_completion(capture_dir)
            if completion_path is None:
                raise CaptureError(
                    f"Anki exited before capture finalized; see {log_path}"
                )
            break
        time.sleep(0.1)
    if completion_path is None:
        raise CaptureError(f"Capture timed out after {timeout} seconds; see {log_path}")
    completion, manifest = _load_completion(completion_path)
    try:
        exit_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        BASE.stop_process(process)
        exit_code = int(process.returncode or 0)
    intended = int(completion.get("exit_code", 1))
    # Qt/macOS can normalize an intentional surface-local failure exit to 0.
    # The atomic completion record remains authoritative for whether this
    # patch scope passed. Only reject an abnormal shutdown after a sentinel
    # that claimed the scope was clean; failed surfaces must remain available
    # for incremental classification and assembly.
    if bool(completion.get("scope_complete")) and exit_code != intended:
        raise CaptureError(
            f"Anki exit code {exit_code} did not match finalized result {intended}"
        )
    return completion, manifest, exit_code


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
        "contact_sheet_count": 0,
        "manifest": str(manifest),
        "recapture_required": surface_report.get("recapture_required", []),
        "report": str(report_path),
        "status": "review-required",
    }, sort_keys=True))
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repo = arguments.repo.expanduser().resolve()
    capture_source = repo / "ankigarden" / "capture_ui_faces.py"
    validator_source = repo / "scripts" / "validate_ui_capture.py"
    if not (repo / "scripts" / "package_addon.py").is_file() or not capture_source.is_file():
        raise CaptureError(f"{repo} is not an Anki Garden repository with UI capture support")
    production_package = (repo / "dist" / "anki_garden.ankiaddon").resolve()
    if production_package.is_symlink() or not production_package.is_file():
        raise CaptureError(
            f"Build the exact production archive before capture: {production_package}"
        )

    output_root = (
        arguments.output_dir or repo / "build" / "ui-face-captures"
    ).expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = output_root / f"capture-sequence-{stamp}"
    capture_dir.mkdir(parents=True, exist_ok=False)
    log_path = capture_dir / "anki.log"
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

    contract = load_capture_contract(capture_source)
    renderer_families = load_expected_renderer_families(
        capture_source,
        contract=contract,
    )
    render_inputs = build_render_input_catalog(
        production_package,
        capture_source=capture_source,
        validator_source=validator_source,
        labels=contract.labels,
        renderer_families=renderer_families,
    )
    render_inputs_path = capture_dir / "render-inputs.json"
    atomic_json(render_inputs_path, render_inputs)

    if arguments.resume_from is not None:
        reuse_plan = plan_incremental_capture(
            base_manifest=arguments.resume_from,
            current_render_inputs=render_inputs,
            expected_labels=contract.labels,
            contract_version=contract.version,
            explicit_surfaces=arguments.surface,
        )
        requested_faces = list(reuse_plan["recapture_required"])
    else:
        explicit = set(arguments.surface)
        unknown = explicit - set(contract.labels)
        if unknown:
            raise CaptureError("Unknown surface(s): " + ", ".join(sorted(unknown)))
        requested_faces = [
            label for label in contract.labels
            if not explicit or label in explicit
        ]
        reuse_plan = {
            "base_manifest": None,
            "capture_contract_version": contract.version,
            "recapture_required": requested_faces,
            "reused": [],
            "reasons": {
                label: ["initial-capture" if not explicit else "explicitly-requested"]
                for label in requested_faces
            },
            "status": "ready",
        }
    atomic_json(capture_dir / "capture-plan.json", reuse_plan)
    if not requested_faces:
        raise CaptureError("Reuse plan is already complete; no surfaces require capture")

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
        helper + ["seed-status", "--anki-version", arguments.anki_version],
        cwd=repo,
    )
    if seed_status.get("status") != "ready":
        raise CaptureError(f"The isolated Anki seed is not ready: {seed_status}")
    profile = f"Capture Sequence {stamp}"
    created = BASE.json_command(
        helper + [
            "create-run",
            "--anki-version",
            arguments.anki_version,
            "--profile",
            profile,
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
    environment.update({str(key): str(value) for key, value in launch["env"].items()})
    environment.update({
        "ANKI_GARDEN_CAPTURE_UI_FACES": "1",
        "ANKI_GARDEN_CAPTURE_DIR": str(capture_dir),
        "ANKI_GARDEN_UI_CAPTURE_DIR": str(capture_dir),
        "ANKI_GARDEN_CAPTURE_PROFILE": "representative",
        "ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE": "1",
        "ANKI_GARDEN_CAPTURE_SECOND_MONITOR": (
            "0" if arguments.no_secondary_monitor else "1"
        ),
        "ANKI_GARDEN_CAPTURE_SURFACES_JSON": json.dumps(requested_faces),
        "ANKI_GARDEN_INVALIDATED_SURFACES_JSON": json.dumps(
            reuse_plan.get("recapture_required", ())
        ),
        "ANKI_GARDEN_RENDER_INPUTS_PATH": str(render_inputs_path),
        "ANKI_GARDEN_PRODUCTION_PACKAGE_SHA256": production_package_sha256,
        "ANKI_GARDEN_CAPTURE_ENVIRONMENT_DIGEST": str(
            render_inputs["environment_digest"]
        ),
        "ANKI_GARDEN_CAPTURE_FOREGROUND_POLICY": arguments.foreground_policy,
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
            )
            _completion, attempt_manifest, _exit_code = _wait_for_capture(
                process,
                capture_dir=capture_dir,
                timeout=arguments.timeout,
                log_path=log_path,
            )
    finally:
        if process is not None and process.poll() is None:
            BASE.stop_process(process)

    if BASE.file_hash(package) != package_sha256:
        raise CaptureError("Capture package changed while capture was running")
    if BASE.file_hash(production_package) != production_package_sha256:
        raise CaptureError("Production package changed while capture was running")

    candidate_manifest = attempt_manifest
    if arguments.resume_from is not None:
        candidate_manifest = assemble_capture_manifest(
            base_manifest=arguments.resume_from,
            patch_manifest=attempt_manifest,
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
            "capture_plan": reuse_plan,
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
            "release_validation": release_validation,
            "surface_validation": surface_report,
        }
        atomic_json(report_path, report)
        print(json.dumps({
            "capture_complete": False,
            "capture_dir": str(capture_dir),
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
    contact_sheet_set, contact_sheets, contact_sheet_index = BASE.render_contact_sheets(
        payload=payload,
        groups=groups,
        package_manifest=package_manifest,
        package_sha256=package_sha256,
        output_root=output_root,
        stamp=stamp,
    )
    contact_validation = validate_contact_sheet_set(
        contact_sheet_index,
        manifest_path=candidate_manifest,
        capture_source=capture_source,
    )
    retained_contact_sets, pruned_contact_sets = BASE.enforce_contact_sheet_retention(
        contact_sheet_set.parent
    )

    report_path = capture_dir / "capture-report.json"
    screenshots = [str(value) for value in payload.get("screenshots", ())]
    report = {
        "archive": str(output_root / f"anki-garden-ui-faces-{stamp}.zip"),
        "capture_complete": True,
        "capture_contract_version": contract.version,
        "capture_display": payload.get("capture_display"),
        "capture_displays": payload.get("capture_displays", []),
        "capture_groups": [
            {"name": name, "labels": labels}
            for name, labels in groups
        ],
        "capture_plan": reuse_plan,
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
        "quality_status": "clean",
        "requested_scale_factor": payload.get("requested_scale_factor"),
        "release_validation": release_validation,
        "retained_contact_sheet_sets": [str(path) for path in retained_contact_sets],
        "screenshot_count": len(screenshots),
        "screenshots": screenshots,
        "surface_validation": surface_report,
        "text_layout_warning_count": 0,
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
    retained_runs, pruned_runs, pruned_archives = BASE.enforce_capture_retention(
        output_root
    )
    report["retained_capture_sets"] = [str(path) for path in retained_runs]
    report["pruned_capture_sets"] = [str(path) for path in pruned_runs]
    report["pruned_capture_archives"] = [str(path) for path in pruned_archives]
    atomic_json(report_path, report)
    print(json.dumps({
        "archive": str(archive),
        "archive_sha256": report["archive_sha256"],
        "capture_complete": True,
        "capture_dir": str(capture_dir),
        "captured_faces": report["captured_faces"],
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_index": str(contact_sheet_index),
        "contact_sheets": report["contact_sheets"],
        "manifest": str(candidate_manifest),
        "package_sha256": package_sha256,
        "production_package_sha256": production_package_sha256,
        "quality_status": "clean",
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
