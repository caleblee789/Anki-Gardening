from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import capture_sequence_v23 as runner
from scripts.capture_evidence import atomic_json, sha256_file


PNG = runner.BASE.PNG_SIGNATURE + runner.BASE.PNG_IEND


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)


def _fixture_render_inputs(
    labels: list[str],
    *,
    profile: str,
    contract_digest: str,
) -> dict[str, Any]:
    environment_digest = "d" * 64
    run_level_digest = "e" * 64
    evidence_schema_digest = "f" * 64
    surfaces: dict[str, dict[str, Any]] = {}
    for label in labels:
        digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
        surfaces[label] = {
            "digest": digest,
            "environment_digest": environment_digest,
            "input_count": 1,
            "scenario_identity_digest": digest,
            "surface_contract_digest": digest,
        }
    return {
        "capture_contract_digest": contract_digest,
        "capture_profile": profile,
        "dialog_scroll_contract": (
            {"FixtureDialog": {labels[0]: "bottom"}}
            if profile == "full"
            else {}
        ),
        "environment_digest": environment_digest,
        "evidence_schema_digest": evidence_schema_digest,
        "production_archive_sha256": "b" * 64,
        "run_level_digest": run_level_digest,
        "scenario_contract_digest": "c" * 64,
        "scenario_schema_version": 1,
        "surfaces": surfaces,
    }


def _write_reusable_manifest(
    manifest: Path,
    *,
    profile: str,
    labels: list[str],
    render_inputs: dict[str, Any],
    groups: list[dict[str, Any]],
    full_run_level: bool,
) -> Path:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    screenshots: list[str] = []
    records: list[dict[str, Any]] = []
    surfaces = render_inputs["surfaces"]
    assert isinstance(surfaces, dict)
    for index, label in enumerate(labels, start=1):
        screenshot = manifest.parent / f"{index:03d}-{label}.png"
        _write_png(screenshot)
        screenshots.append(screenshot.name)
        current = surfaces[label]
        record: dict[str, Any] = {
            "audit": {"passed": True},
            "capture_display": "primary",
            "capture_environment_digest": current["environment_digest"],
            "capture_id": index,
            "evidence_schema_digest": render_inputs["evidence_schema_digest"],
            "fixture_validation": {"passed": True},
            "geometry_layout_warnings": [],
            "label": label,
            "lineage": {"source_run_id": manifest.parent.name},
            "path": screenshot.name,
            "png_sha256": sha256_file(screenshot),
            "render_input_digest": current["digest"],
            "scenario_identity_digest": current["scenario_identity_digest"],
            "surface_contract_digest": current["surface_contract_digest"],
            "text_layout_warnings": [],
        }
        if profile == "full" and index == 1:
            record["dialog_scroll_audit"] = {
                "actual_page_semantic": "bottom",
                "issues": [],
                "passed": True,
                "surface": "FixtureDialog",
            }
        records.append(record)
    run_level: dict[str, Any] = {
        "clean_shutdown": {
            "capture_environment_digest": render_inputs["environment_digest"],
            "passed": True,
            "run_level_digest": render_inputs["run_level_digest"],
        },
    }
    if full_run_level:
        run_level["dialog_memory_probe"] = {
            "passed": True,
            "result": {"cycles": 12, "status": "passed"},
            "run_level_digest": render_inputs["run_level_digest"],
        }
    payload = {
        "capture_calibration": {"passed": True},
        "capture_contract_digest": render_inputs["capture_contract_digest"],
        "capture_contract_version": 24,
        "capture_display": "primary",
        "capture_displays": ["primary"],
        "capture_groups": groups,
        "capture_profile": profile,
        "capture_scope": "full",
        "captured_faces": labels,
        "captures": records,
        "complete": True,
        "expected_count": len(labels),
        "expected_faces": labels,
        "production_package_sha256": render_inputs["production_archive_sha256"],
        "render_inputs": render_inputs,
        "requested_faces": labels,
        "requested_scale_factor": "1.0",
        "reused_faces": [],
        "run_level_evidence": run_level,
        "scenario_contract_digest": render_inputs["scenario_contract_digest"],
        "scenario_schema_version": 1,
        "scope_complete": True,
        "screenshots": screenshots,
        "source_manifests": [],
    }
    atomic_json(manifest, payload)
    atomic_json(manifest.parent / "capture-complete.json", {
        "complete": True,
        "exit_code": 0,
        "manifest": manifest.name,
        "manifest_sha256": sha256_file(manifest),
        "scope_complete": True,
    })
    return manifest


def _write_complete_profile_run(
    output_root: Path,
    *,
    profile: str,
    stamp: str,
) -> Path:
    screenshot_count, sheet_count = runner._PROFILE_EVIDENCE_COUNTS[profile]
    # This helper deliberately models frozen v24 evidence. Its topology must
    # not follow the smaller registry-derived v25 contract.
    labels = [f"legacy-v24-{profile}-{index:03d}" for index in range(screenshot_count)]
    contract_digest = hashlib.sha256(
        f"legacy-v24-{profile}".encode("utf-8")
    ).hexdigest()
    groups = [{"name": "Legacy v24", "labels": labels}]
    render_inputs = _fixture_render_inputs(
        labels,
        profile=profile,
        contract_digest=contract_digest,
    )
    run = output_root / f"capture-sequence-{stamp}"
    manifest = run / "assembled" / "manifest.json"
    _write_reusable_manifest(
        manifest,
        profile=profile,
        labels=labels,
        render_inputs=render_inputs,
        groups=groups,
        full_run_level=True,
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    screenshots = list(manifest_payload["screenshots"])

    sheet_set = (
        output_root
        / "contact-sheets"
        / f"anki-garden-ui-contact-sheet-2.1.0-{stamp}"
    )
    contact_sheets: list[str] = []
    pages: list[dict[str, Any]] = []
    remaining = screenshot_count
    for index in range(sheet_count):
        sheet = sheet_set / f"sheet-{index + 1:02d}.png"
        _write_png(sheet)
        contact_sheets.append(str(sheet.relative_to(output_root)))
        pages_left = sheet_count - index
        page_surfaces = remaining // pages_left
        remaining -= page_surfaces
        pages.append({
            "file": sheet.name,
            "groups": ["Contract"],
            "page": index + 1,
            "surface_count": page_surfaces,
        })
    contact_index = sheet_set / "contact-sheet-set.json"
    atomic_json(contact_index, {
        "capture_contract_digest": contract_digest,
        "capture_manifest": str(manifest),
        "capture_profile": profile,
        "complete": True,
        "package_sha256": "a" * 64,
        "package_version": "2.1.0",
        "page_count": sheet_count,
        "pages": pages,
        "surface_count": screenshot_count,
    })

    archive = output_root / f"anki-garden-ui-faces-{stamp}.zip"
    with zipfile.ZipFile(archive, "w") as evidence:
        evidence.writestr("assembled/manifest.json", manifest.read_bytes())
    surface_report = runner.surface_validation_report(manifest)
    atomic_json(run / "capture-report.json", {
        "archive": str(archive.relative_to(output_root)),
        "archive_sha256": sha256_file(archive),
        "capture_complete": True,
        "capture_contract_digest": contract_digest,
        "capture_contract_version": 24,
        "capture_groups": groups,
        "capture_profile": profile,
        "contact_sheet_count": sheet_count,
        "contact_sheet_index": str(contact_index.relative_to(output_root)),
        "contact_sheet_set": str(sheet_set.relative_to(output_root)),
        "contact_sheet_validation": {
            "capture_profile": profile,
            "contact_sheet_set": str(contact_index),
            "page_count": sheet_count,
        },
        "contact_sheets": contact_sheets,
        "manifest": str(manifest.relative_to(run)),
        "package_sha256": "a" * 64,
        "package_version": "2.1.0",
        "quality_status": "review-required",
        "release_validation": {
            "capture_contract_version": 24,
            "capture_count": screenshot_count,
            "capture_profile": profile,
            "status": "valid",
        },
        "screenshot_count": screenshot_count,
        "screenshots": screenshots,
        "surface_validation": surface_report,
        "text_layout_warning_count": 0,
    })
    return run


def test_discovery_scans_both_profiles_and_rejects_competing_authorities(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    representative = evidence_root / "representative" / "run-a" / "manifest.json"
    full = evidence_root / "full" / "run-b" / "manifest.json"
    atomic_json(representative, {"capture_profile": "representative"})
    atomic_json(full, {"capture_profile": "full"})
    os.utime(representative, ns=(10, 10))
    os.utime(full, ns=(20, 20))

    assert runner._discover_evidence_manifests(evidence_root, []) == [
        full.resolve(),
        representative.resolve(),
    ]

    recovered = representative.with_name("manifest.recovered.json")
    atomic_json(recovered, {"capture_profile": "representative", "recovered": True})
    with pytest.raises(runner.CaptureError, match="competing final and recovered"):
        runner._discover_evidence_manifests(evidence_root, [])


def test_discovery_rejects_every_equal_recency_tie(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    first = root / "representative" / "run-a" / "manifest.json"
    second = root / "full" / "run-b" / "manifest.json"
    atomic_json(first, {"capture_profile": "representative"})
    atomic_json(second, {"capture_profile": "full"})
    os.utime(first, ns=(42, 42))
    os.utime(second, ns=(42, 42))
    with pytest.raises(runner.CaptureError, match="multiple manifests with equal recency"):
        runner._discover_evidence_manifests(root, [])

    second.write_bytes(first.read_bytes())
    os.utime(second, ns=(42, 42))
    with pytest.raises(runner.CaptureError, match="multiple manifests with equal recency"):
        runner._discover_evidence_manifests(root, [])


def test_fresh_baseline_skips_discovery_and_requires_every_surface_and_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = ["face-a", "face-b", "face-c"]
    render_inputs = _fixture_render_inputs(
        labels,
        profile="full",
        contract_digest="c" * 64,
    )
    real_planner = runner.plan_incremental_capture
    planner_evidence: list[list[Path]] = []

    def plan(**kwargs: Any) -> dict[str, Any]:
        planner_evidence.append(list(kwargs["evidence_manifests"]))
        return real_planner(**kwargs)

    monkeypatch.setattr(runner, "plan_incremental_capture", plan)
    monkeypatch.setattr(
        runner,
        "_discover_evidence_manifests",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fresh baseline must not discover evidence")
        ),
    )

    evidence, capture_plan = runner._capture_reuse_plan(
        evidence_root=tmp_path / "historical-evidence",
        explicit_manifests=[],
        explicit_only_manifests=[],
        current_render_inputs=render_inputs,
        expected_labels=labels,
        contract_version=24,
        contract_digest="c" * 64,
        profile="full",
        explicit_surfaces=[],
        fresh_baseline=True,
    )

    assert evidence == []
    assert planner_evidence == [[]]
    assert capture_plan["reused"] == []
    assert capture_plan["recapture_required"] == labels
    assert capture_plan["run_level_recapture_required"] is True
    assert capture_plan["selected_run_level_source"] is None
    assert capture_plan["selection_policy"] == {
        "mode": "fresh-baseline",
        "reason": "explicitly-requested-no-historical-reuse",
        "evidence_discovery_skipped": True,
    }


@pytest.mark.parametrize(
    "conflicting_arguments,expected_option",
    [
        (["--reuse-from", "manifest.json"], "--reuse-from"),
        (["--surface", "face-a"], "--surface"),
    ],
)
def test_fresh_baseline_rejects_reuse_and_surface_overrides(
    conflicting_arguments: list[str],
    expected_option: str,
) -> None:
    with pytest.raises(
        runner.CaptureError,
        match=rf"--fresh-baseline cannot be combined with {expected_option}",
    ):
        runner.main(["--fresh-baseline", *conflicting_arguments])


def test_explicit_only_reuse_salvages_passed_partial_faces_and_forces_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = ["face-a", "face-b", "face-c"]
    render_inputs = _fixture_render_inputs(
        labels,
        profile="representative",
        contract_digest="c" * 64,
    )
    manifest = _write_reusable_manifest(
        tmp_path / "partial" / "manifest.json",
        profile="representative",
        labels=labels,
        render_inputs=render_inputs,
        groups=[{"name": "Fixture", "labels": labels}],
        full_run_level=False,
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.update({
        "captured_faces": labels[:2],
        "captures": payload["captures"][:2],
        "complete": False,
        "failures": [{"label": labels[2], "reason": "fixture failed"}],
        "invalidated_faces": [labels[2]],
        "scope_complete": False,
        "screenshots": payload["screenshots"][:2],
    })
    atomic_json(manifest, payload)
    atomic_json(manifest.parent / "capture-complete.json", {
        "complete": False,
        "exit_code": 1,
        "manifest": manifest.name,
        "manifest_sha256": sha256_file(manifest),
        "scope_complete": False,
    })
    monkeypatch.setattr(
        runner,
        "_discover_evidence_manifests",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit-only reuse must not discover evidence")
        ),
    )

    evidence, capture_plan = runner._capture_reuse_plan(
        evidence_root=tmp_path / "unrelated-history",
        explicit_manifests=[],
        explicit_only_manifests=[manifest, manifest],
        current_render_inputs=render_inputs,
        expected_labels=labels,
        contract_version=24,
        contract_digest="c" * 64,
        profile="representative",
        explicit_surfaces=[],
        fresh_baseline=False,
    )

    assert evidence == [manifest.resolve()]
    assert capture_plan["reused"] == labels[:2]
    assert capture_plan["recapture_required"] == labels[2:]
    assert capture_plan["reasons"] == {
        labels[2]: ["failed-recapture-tombstone"],
    }
    assert capture_plan["run_level_recapture_required"] is True
    assert capture_plan["selected_run_level_source"] is None
    assert capture_plan["selection_policy"] == {
        "mode": "explicit-only-reuse",
        "reason": "caller-supplied-manifests-only",
        "evidence_discovery_skipped": True,
    }

    _evidence, targeted = runner._capture_reuse_plan(
        evidence_root=tmp_path / "unrelated-history",
        explicit_manifests=[],
        explicit_only_manifests=[manifest],
        current_render_inputs=render_inputs,
        expected_labels=labels,
        contract_version=24,
        contract_digest="c" * 64,
        profile="representative",
        explicit_surfaces=[labels[0]],
        fresh_baseline=False,
    )
    assert targeted["reused"] == [labels[1]]
    assert targeted["recapture_required"] == [labels[0], labels[2]]
    assert targeted["reasons"][labels[0]] == ["explicitly-requested"]


@pytest.mark.parametrize(
    "arguments,expected_message",
    [
        (
            ["--fresh-baseline", "--reuse-only-from", "manifest.json"],
            "--fresh-baseline cannot be combined with --reuse-only-from",
        ),
        (
            [
                "--reuse-from",
                "first.json",
                "--reuse-only-from",
                "second.json",
            ],
            "--reuse-from cannot be combined with --reuse-only-from",
        ),
    ],
)
def test_explicit_only_reuse_rejects_competing_evidence_modes(
    arguments: list[str],
    expected_message: str,
) -> None:
    with pytest.raises(runner.CaptureError, match=expected_message):
        runner.main(arguments)


def test_profile_retention_preserves_all_raw_and_sheet_evidence_per_profile(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    profiles: dict[str, list[Path]] = {}
    for profile in ("representative", "full"):
        output_root = evidence_root / profile
        output_root.mkdir(parents=True)
        profiles[profile] = [
            _write_complete_profile_run(
                output_root,
                profile=profile,
                stamp=f"20260824-00000{index}",
            )
            for index in range(1, 5)
        ]
        partial = output_root / "capture-sequence-20260824-000000"
        partial.mkdir()
        atomic_json(partial / "capture-report.json", {"capture_complete": False})

    representative_root = evidence_root / "representative"
    (
        retained,
        pruned,
        pruned_archives,
        retained_sheets,
        pruned_sheets,
    ) = runner._enforce_profile_evidence_retention(
        representative_root
    )
    assert [path.name for path in retained] == [
        "capture-sequence-20260824-000004",
        "capture-sequence-20260824-000003",
        "capture-sequence-20260824-000002",
        "capture-sequence-20260824-000001",
    ]
    assert pruned == []
    assert pruned_archives == []
    assert len(retained_sheets) == 4
    assert pruned_sheets == []
    assert profiles["representative"][0].exists()
    assert (
        representative_root
        / "contact-sheets"
        / "anki-garden-ui-contact-sheet-2.1.0-20260824-000001"
    ).exists()
    assert all(path.exists() for path in profiles["full"])
    assert (representative_root / "capture-sequence-20260824-000000").exists()

    full_root = evidence_root / "full"
    (
        retained_full,
        pruned_full,
        _archives,
        retained_full_sheets,
        pruned_full_sheets,
    ) = runner._enforce_profile_evidence_retention(
        full_root
    )
    assert len(retained_full) == 4
    assert len(retained_full_sheets) == 4
    assert pruned_full == []
    assert pruned_full_sheets == []
    assert profiles["full"][0].exists()


def test_profile_retention_preserves_malformed_fake_complete_artifacts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "evidence" / "representative"
    output_root.mkdir(parents=True)
    valid_runs = [
        _write_complete_profile_run(
            output_root,
            profile="representative",
            stamp=f"20260824-00000{index}",
        )
        for index in range(1, 4)
    ]
    malformed = _write_complete_profile_run(
        output_root,
        profile="representative",
        stamp="20260824-000000",
    )
    report_path = malformed / "capture-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    archive = output_root / "anki-garden-ui-faces-20260824-000000.zip"
    archive.write_bytes(b"not a zip")
    report["archive_sha256"] = sha256_file(archive)
    atomic_json(report_path, report)

    retained, pruned, pruned_archives = runner._enforce_profile_capture_retention(
        output_root
    )
    assert len(retained) == 3
    assert pruned == []
    assert pruned_archives == []
    assert malformed.exists()
    assert archive.exists()
    assert all(path.exists() for path in valid_runs)


def test_profile_retention_uses_the_current_v29_contract() -> None:
    assert runner.CONTRACT_VERSION == 29
    assert runner._profile_evidence_counts(29, "representative") == (22, 5)
    assert runner._profile_evidence_counts(29, "full") == (50, 5)
    assert runner._profile_evidence_counts(25, "full") is None
    assert runner._profile_evidence_counts(24, "representative") == (26, 4)


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stopped = False

    def poll(self) -> int | None:
        return self.returncode


class _CompletedProcess(_FakeProcess):
    def __init__(self, exit_code: int) -> None:
        super().__init__()
        self.returncode = int(exit_code)

    def wait(self, timeout: int) -> int:
        assert timeout == 30
        return int(self.returncode or 0)


def test_finalized_capture_reports_shutdown_signal_separately(
    tmp_path: Path,
) -> None:
    session = tmp_path / "capture" / "session"
    session.mkdir(parents=True)
    manifest = session / "manifest.json"
    atomic_json(manifest, {"complete": False})
    completion_path = session / "capture-complete.json"
    atomic_json(completion_path, {
        "complete": False,
        "exit_code": 1,
        "manifest": str(manifest),
        "manifest_sha256": sha256_file(manifest),
        "scope_complete": False,
    })

    completion, returned_manifest, exit_code, lifecycle = runner._wait_for_capture(
        _CompletedProcess(-11),  # type: ignore[arg-type]
        capture_dir=tmp_path / "capture",
        timeout=30,
        inactivity_timeout=30,
        log_path=tmp_path / "anki.log",
    )

    assert completion["scope_complete"] is False
    assert returned_manifest == manifest
    assert exit_code == -11
    assert lifecycle["passed"] is False
    assert lifecycle["reason"] == "shutdown-signal"
    assert lifecycle["shutdown_signal"] == 11


def test_timeout_stops_process_and_recovers_atomic_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = tmp_path / "capture" / "session"
    partial = session / "manifest.partial.json"
    atomic_json(partial, {"complete": False})
    recovered = session / "manifest.recovered.json"
    atomic_json(recovered, {"complete": False, "recovered": True})
    process = _FakeProcess()
    ticks = iter((0.0, 100.0, 200.0, 300.0, 400.0))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runner,
        "recover_progress_manifest",
        lambda _session: recovered,
    )

    def stop(target: _FakeProcess) -> None:
        target.stopped = True
        target.returncode = -9

    monkeypatch.setattr(runner.BASE, "stop_process", stop)
    completion, manifest, exit_code, lifecycle = runner._wait_for_capture(
        process,  # type: ignore[arg-type]
        capture_dir=tmp_path / "capture",
        timeout=1,
        inactivity_timeout=1,
        log_path=tmp_path / "anki.log",
    )
    assert process.stopped is True
    assert manifest == recovered
    assert exit_code == -9
    assert completion["scope_complete"] is False
    assert lifecycle["status"] == "failed"
    assert lifecycle["reason"] in {"inactivity-timeout", "absolute-timeout"}


def test_run_attempt_stops_process_when_session_discovery_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "isolated"
    run_root.mkdir()
    process = _FakeProcess()

    def json_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
        del cwd
        if "seed-status" in command:
            return {"status": "ready"}
        if "create-run" in command:
            return {
                "run_root": str(run_root),
                "launch": {"env": {}, "argv": ["Anki"]},
            }
        return {"status": "prelaunch-ready"}

    monkeypatch.setattr(runner.BASE, "json_command", json_command)
    monkeypatch.setattr(runner.Path, "is_file", lambda _path: True)
    monkeypatch.setattr(runner.BASE, "extract_package", lambda *_args: None)
    monkeypatch.setattr(runner.BASE, "set_disposable_ui_scale", lambda *_args: None)
    popen_kwargs: dict[str, Any] = {}

    def popen(*_args: Any, **kwargs: Any) -> _FakeProcess:
        popen_kwargs.update(kwargs)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    monkeypatch.setattr(
        runner,
        "_wait_for_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            runner.CaptureError("multiple active session directories")
        ),
    )

    def stop(target: _FakeProcess) -> None:
        target.stopped = True
        target.returncode = -9

    monkeypatch.setattr(runner.BASE, "stop_process", stop)
    package = tmp_path / "capture.ankiaddon"
    package.write_bytes(b"capture")
    render_inputs = tmp_path / "render-inputs.json"
    atomic_json(render_inputs, {})
    with pytest.raises(runner.CaptureError, match="multiple active"):
        runner._run_capture_attempt(
            repo=tmp_path,
            capture_dir=tmp_path / "capture",
            package=package,
            package_id="pkg",
            anki_version="26.8.1",
            stamp="20260824-000000",
            profile="full",
            requested_faces=("face",),
            invalidated_faces=("face",),
            render_inputs_path=render_inputs,
            production_package_sha256="a" * 64,
            environment_digest="b" * 64,
            foreground_policy="required-only",
            no_secondary_monitor=True,
            timeout=30,
            inactivity_timeout=30,
            log_path=tmp_path / "anki.log",
        )
    assert process.stopped is True
    assert popen_kwargs["restore_signals"] is False


def test_real_planner_reuses_only_representative_overlap_for_full_profile(
    tmp_path: Path,
) -> None:
    representative_labels = [f"face-{index:03d}" for index in range(26)]
    full_labels = representative_labels + [
        f"full-only-{index:03d}" for index in range(100)
    ]
    representative_inputs = _fixture_render_inputs(
        representative_labels,
        profile="representative",
        contract_digest="a" * 64,
    )
    full_inputs = _fixture_render_inputs(
        full_labels,
        profile="full",
        contract_digest="c" * 64,
    )
    representative_manifest = _write_reusable_manifest(
        tmp_path / "representative" / "manifest.json",
        profile="representative",
        labels=representative_labels,
        render_inputs=representative_inputs,
        groups=[{"name": "Representative", "labels": representative_labels}],
        full_run_level=False,
    )

    plan = runner.plan_incremental_capture(
        evidence_manifests=[representative_manifest],
        current_render_inputs=full_inputs,
        expected_labels=full_labels,
        contract_version=24,
        contract_digest="c" * 64,
        profile="full",
    )
    assert plan["reused"] == representative_labels
    assert plan["recapture_required"] == full_labels[26:]
    assert plan["run_level_recapture_required"] is True


@pytest.mark.parametrize("fresh_baseline", [False, True])
def test_full_runner_keeps_capture_and_gates_in_one_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fresh_baseline: bool,
) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "ankigarden").mkdir()
    (repo / "dist").mkdir()
    (repo / "scripts" / "package_addon.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "scripts" / "validate_ui_capture.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "ankigarden" / "capture_ui_faces.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "ankigarden" / "capture").mkdir()
    (repo / "ankigarden" / "capture" / "runtime.py").write_text(
        "# fixture\n",
        encoding="utf-8",
    )
    production = repo / "dist" / "anki_garden.ankiaddon"
    production.write_bytes(b"production")
    evidence_root = tmp_path / "evidence"
    full_manifest = (
        evidence_root
        / "full"
        / "capture-sequence-20260824-000000"
        / "assembled"
        / "manifest.json"
    )
    # Keep the legacy run-gate policy fixture, but execute the actual current
    # inventory so fresh mode schedules all 51 registry-bound surfaces.
    full_labels = list(runner.REGISTRY.profile_labels("full"))
    render_inputs = _fixture_render_inputs(
        full_labels,
        profile="full",
        contract_digest="c" * 64,
    )
    _write_reusable_manifest(
        full_manifest,
        profile="full",
        labels=full_labels,
        render_inputs=render_inputs,
        groups=[{"name": "Full", "labels": full_labels}],
        full_run_level=True,
    )

    def archive_package(
        _repo: Path,
        _python: str,
        output: Path,
    ) -> tuple[Path, str, dict[str, Any]]:
        output.write_bytes(b"capture")
        return output, "pkg", {"human_version": "2.1.0"}

    monkeypatch.setattr(runner.BASE, "command_python", lambda _repo: sys.executable)
    monkeypatch.setattr(runner.BASE, "archive_package", archive_package)
    monkeypatch.setattr(
        runner.BASE,
        "capture_derivative_report",
        lambda _repo, production_path, capture_path: {
            "capture_archive_sha256": sha256_file(capture_path),
            "production_archive_sha256": sha256_file(production_path),
        },
    )
    contract = SimpleNamespace(labels=tuple(full_labels), version=24, digest="c" * 64)
    monkeypatch.setattr(runner, "load_capture_contract", lambda *_args, **_kwargs: contract)
    monkeypatch.setattr(
        runner,
        "load_compiled_contract",
        lambda: {
            "contract_digest": contract.digest,
            "profiles": {},
            "surfaces": [
                {"id": label, "active": True, "dependency_digest": "a" * 64}
                for label in full_labels
            ],
        },
    )
    monkeypatch.setattr(
        runner,
        "load_expected_renderer_families",
        lambda *_args, **_kwargs: {label: "Fixture" for label in full_labels},
    )
    monkeypatch.setattr(
        runner,
        "load_capture_scenario_contracts",
        lambda *_args, **_kwargs: {label: {} for label in full_labels},
    )
    monkeypatch.setattr(
        runner,
        "load_dialog_scroll_capture_coverage",
        lambda *_args, **_kwargs: render_inputs["dialog_scroll_contract"],
    )
    monkeypatch.setattr(
        runner,
        "build_render_input_catalog",
        lambda *_args, **_kwargs: render_inputs,
    )
    launches: list[dict[str, Any]] = []

    expected_fresh = full_labels if fresh_baseline else []

    def run_attempt(**kwargs: Any) -> tuple[Path, dict[str, Any]]:
        launches.append(kwargs)
        assert list(kwargs["requested_faces"]) == expected_fresh
        assert list(kwargs["invalidated_faces"]) == expected_fresh
        manifest = Path(kwargs["capture_dir"]) / "test-session" / "manifest.json"
        _write_reusable_manifest(
            manifest,
            profile="full",
            labels=expected_fresh,
            render_inputs=render_inputs,
            groups=[{"name": "Full", "labels": full_labels}] if fresh_baseline else [],
            full_run_level=True,
        )
        return manifest, {"status": "complete"}

    monkeypatch.setattr(runner, "_run_capture_attempt", run_attempt)

    monkeypatch.setattr(
        runner,
        "validate_capture_manifest",
        lambda *_args, **_kwargs: {
            "capture_contract_version": 24,
            "capture_count": len(full_labels),
            "capture_profile": "full",
            "status": "valid",
        },
    )

    assert runner.main([
        "--repo",
        str(repo),
        "--output-dir",
        str(evidence_root),
        "--profile",
        "full",
        "--defer-contact-sheets",
        *(["--fresh-baseline"] if fresh_baseline else []),
    ]) == 0
    reports = list((evidence_root / "full").glob("*/capture-report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["captured_faces"] == expected_fresh
    assert report["reused_faces"] == ([] if fresh_baseline else full_labels)
    assert report["capture_plan"]["recapture_required"] == expected_fresh
    assert report["capture_plan"]["run_level_recapture_required"] is True
    assert report["capture_plan"]["run_level_reuse_policy"] == (
        "current-session-required"
    )
    assert len(launches) == 1
