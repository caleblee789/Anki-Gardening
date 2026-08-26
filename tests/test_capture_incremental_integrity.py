from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scripts.capture_evidence import (
    CaptureEvidenceError,
    assemble_capture_manifest,
    plan_incremental_capture,
    recover_progress_manifest,
    surface_validation_report,
)


LABEL = "surface-a"
CONTRACT_VERSION = 24
ENVIRONMENT_DIGEST = "1" * 64
RENDER_DIGEST = "2" * 64
SCENARIO_DIGEST = "3" * 64
SURFACE_DIGEST = "4" * 64
SCHEMA_DIGEST = "5" * 64
RUN_DIGEST = "6" * 64
PACKAGE_DIGEST = "7" * 64
CONTRACT_DIGEST = "8" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\natomic-capture-evidence"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seal(manifest: Path) -> None:
    _write_json(manifest.parent / "capture-complete.json", {
        "complete": True,
        "exit_code": 0,
        "manifest": manifest.name,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "scope_complete": True,
    })


def _record(*, path: str = f"{LABEL}.png") -> dict[str, object]:
    return {
        "audit": {"passed": True},
        "capture_environment_digest": ENVIRONMENT_DIGEST,
        "capture_id": 1,
        "evidence_schema_digest": SCHEMA_DIGEST,
        "evidence_status": "captured",
        "fixture_validation": {"passed": True},
        "geometry_layout_warnings": [],
        "label": LABEL,
        "lineage": {
            "evidence_status": "captured",
            "source_package_sha256": PACKAGE_DIGEST,
            "source_run_id": "fixture-run",
        },
        "path": path,
        "png_sha256": hashlib.sha256(PNG_BYTES).hexdigest(),
        "render_input_count": 1,
        "render_input_digest": RENDER_DIGEST,
        "scenario_identity_digest": SCENARIO_DIGEST,
        "source_package_sha256": PACKAGE_DIGEST,
        "surface_contract_digest": SURFACE_DIGEST,
        "text_layout_warnings": [],
    }


def _payload(
    *,
    captures: list[dict[str, object]] | None = None,
    failures: list[dict[str, str]] | None = None,
    invalidated: list[str] | None = None,
    run_passed: bool = True,
    scope_complete: bool = True,
) -> dict[str, object]:
    records = [_record()] if captures is None else captures
    return {
        "capture_calibration": {"passed": True},
        "capture_contract_digest": CONTRACT_DIGEST,
        "capture_contract_version": CONTRACT_VERSION,
        "capture_environment_digest": ENVIRONMENT_DIGEST,
        "capture_groups": [{"name": "Test", "labels": [LABEL]}],
        "capture_profile": "representative",
        "capture_scope": "full",
        "captures": records,
        "complete": scope_complete and not failures,
        "expected_count": 1,
        "expected_faces": [LABEL],
        "failures": failures or [],
        "foreground_policy": "required-only",
        "foreground_requests": [],
        "invalidated_faces": invalidated or [],
        "production_package_sha256": PACKAGE_DIGEST,
        "requested_faces": [LABEL],
        "requested_scale_factor": "1.0",
        "run_level_evidence": {
            "clean_shutdown": {
                "capture_environment_digest": ENVIRONMENT_DIGEST,
                "passed": run_passed,
                "required": True,
                "run_level_digest": RUN_DIGEST,
                "status": "passed" if run_passed else "failed",
            },
        },
        "scope_complete": scope_complete,
        "text_layout_warnings": [],
    }


def _manifest(
    root: Path,
    *,
    payload: dict[str, object] | None = None,
    name: str = "manifest.json",
    seal: bool = True,
) -> tuple[Path, dict[str, object]]:
    root.mkdir(parents=True)
    (root / f"{LABEL}.png").write_bytes(PNG_BYTES)
    manifest_payload = _payload() if payload is None else payload
    manifest = root / name
    _write_json(manifest, manifest_payload)
    if seal:
        _seal(manifest)
    return manifest, manifest_payload


def _render_inputs() -> dict[str, object]:
    return {
        "capture_contract_digest": CONTRACT_DIGEST,
        "capture_profile": "representative",
        "dialog_scroll_contract": {},
        "environment_digest": ENVIRONMENT_DIGEST,
        "evidence_schema_digest": SCHEMA_DIGEST,
        "production_archive_sha256": PACKAGE_DIGEST,
        "run_level_digest": RUN_DIGEST,
        "surfaces": {
            LABEL: {
                "digest": RENDER_DIGEST,
                "environment_digest": ENVIRONMENT_DIGEST,
                "input_count": 1,
                "scenario_identity_digest": SCENARIO_DIGEST,
                "surface_contract_digest": SURFACE_DIGEST,
            },
        },
    }


def _plan(*manifests: Path, explicit: tuple[str, ...] = ()) -> dict[str, object]:
    return plan_incremental_capture(
        evidence_manifests=list(manifests),
        current_render_inputs=_render_inputs(),
        expected_labels=(LABEL,),
        contract_version=CONTRACT_VERSION,
        contract_digest=CONTRACT_DIGEST,
        profile="representative",
        explicit_surfaces=explicit,
    )


def test_review_audits_do_not_invalidate_valid_pixels(tmp_path: Path) -> None:
    record = _record()
    record["text_layout_warnings"] = [{"kind": "text-fit", "capture": LABEL}]
    record["geometry_layout_warnings"] = [
        {"kind": "scroll-detail", "capture": LABEL}
    ]
    payload = _payload(captures=[record])
    payload["capture_advisories"] = [
        {
            "label": LABEL,
            "reason": "semantic audit did not pass",
            "severity": "advisory",
        }
    ]
    payload["text_layout_warnings"] = record["text_layout_warnings"]
    manifest, _ = _manifest(tmp_path / "advisory", payload=payload)

    report = surface_validation_report(manifest)

    assert report["status"] == "valid"
    assert report["reusable_faces"] == [LABEL]
    assert report["recapture_required"] == []
    assert report["surfaces"][LABEL]["advisories"]


def test_assembly_rejects_coherently_rewritten_selected_manifest(
    tmp_path: Path,
) -> None:
    manifest, payload = _manifest(tmp_path / "source")
    plan = _plan(manifest)

    record = copy.deepcopy(payload["captures"][0])
    assert isinstance(record, dict)
    record["capture_ms"] = 12.0
    payload["captures"] = [record]
    _write_json(manifest, payload)
    _seal(manifest)

    with pytest.raises(CaptureEvidenceError, match="manifest changed after planning"):
        assemble_capture_manifest(
            reuse_plan=plan,
            current_render_inputs=_render_inputs(),
            output_dir=tmp_path / "assembled",
        )
    assert not (tmp_path / "assembled").exists()


def test_assembly_binds_selected_record_sha_independently(
    tmp_path: Path,
) -> None:
    manifest, payload = _manifest(tmp_path / "source")
    plan = _plan(manifest)
    original_record_sha = plan["selected_sources"][LABEL]["record_sha256"]

    record = copy.deepcopy(payload["captures"][0])
    assert isinstance(record, dict)
    record["capture_ms"] = 24.0
    payload["captures"] = [record]
    _write_json(manifest, payload)
    _seal(manifest)
    current_manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    plan["selected_sources"][LABEL]["manifest_sha256"] = current_manifest_sha
    plan["selected_run_level_source"]["manifest_sha256"] = current_manifest_sha
    assert plan["selected_sources"][LABEL]["record_sha256"] == original_record_sha

    with pytest.raises(CaptureEvidenceError, match="record changed after planning"):
        assemble_capture_manifest(
            reuse_plan=plan,
            current_render_inputs=_render_inputs(),
            output_dir=tmp_path / "assembled",
        )


def test_assembly_rejects_rewritten_selected_run_manifest(tmp_path: Path) -> None:
    surface, _surface_payload = _manifest(
        tmp_path / "surface-source",
        payload=_payload(run_passed=False),
    )
    run_source, run_payload = _manifest(tmp_path / "run-source")
    plan = _plan(surface, run_source)
    assert plan["selected_sources"][LABEL]["manifest"] == str(surface.resolve())
    assert plan["selected_run_level_source"]["manifest"] == str(
        run_source.resolve()
    )

    run_evidence = run_payload["run_level_evidence"]
    assert isinstance(run_evidence, dict)
    run_evidence["note"] = "coherent rewrite"
    _write_json(run_source, run_payload)
    _seal(run_source)

    with pytest.raises(
        CaptureEvidenceError,
        match="run-level manifest changed after planning",
    ):
        assemble_capture_manifest(
            reuse_plan=plan,
            current_render_inputs=_render_inputs(),
            output_dir=tmp_path / "assembled",
        )


def test_assembly_binds_selected_run_evidence_sha_independently(
    tmp_path: Path,
) -> None:
    surface, _surface_payload = _manifest(
        tmp_path / "surface-source",
        payload=_payload(run_passed=False),
    )
    run_source, run_payload = _manifest(tmp_path / "run-source")
    plan = _plan(surface, run_source)

    run_evidence = run_payload["run_level_evidence"]
    assert isinstance(run_evidence, dict)
    run_evidence["note"] = "coherent rewrite"
    _write_json(run_source, run_payload)
    _seal(run_source)
    plan["selected_run_level_source"]["manifest_sha256"] = hashlib.sha256(
        run_source.read_bytes()
    ).hexdigest()

    with pytest.raises(
        CaptureEvidenceError,
        match="run-level evidence changed after planning",
    ):
        assemble_capture_manifest(
            reuse_plan=plan,
            current_render_inputs=_render_inputs(),
            output_dir=tmp_path / "assembled",
        )


def test_failed_recapture_tombstone_blocks_older_evidence_until_newer_pass(
    tmp_path: Path,
) -> None:
    old_manifest, _old_payload = _manifest(tmp_path / "old")
    first_plan = _plan(old_manifest, explicit=(LABEL,))
    assert first_plan["recapture_required"] == [LABEL]

    failed_payload = _payload(
        captures=[],
        failures=[{"label": LABEL, "reason": "capture failed"}],
        invalidated=[LABEL],
        scope_complete=False,
    )
    failed_manifest, _ = _manifest(
        tmp_path / "failed-replacement",
        payload=failed_payload,
    )
    blocked = _plan(failed_manifest, old_manifest)
    assert blocked["reused"] == []
    assert blocked["recapture_required"] == [LABEL]
    assert blocked["reasons"][LABEL] == [
        "failed-recapture-tombstone",
    ]

    newer_manifest, _newer_payload = _manifest(tmp_path / "newer-pass")
    cleared = _plan(newer_manifest, failed_manifest, old_manifest)
    assert cleared["reused"] == [LABEL]
    assert cleared["selected_sources"][LABEL]["manifest"] == str(
        newer_manifest.resolve()
    )


def test_representative_shutdown_evidence_is_bound_to_run_level_digest(
    tmp_path: Path,
) -> None:
    manifest, _payload_value = _manifest(tmp_path / "old-package")
    changed_inputs = copy.deepcopy(_render_inputs())
    changed_inputs["run_level_digest"] = "9" * 64

    plan = plan_incremental_capture(
        evidence_manifests=(manifest,),
        current_render_inputs=changed_inputs,
        expected_labels=(LABEL,),
        contract_version=CONTRACT_VERSION,
        contract_digest=CONTRACT_DIGEST,
        profile="representative",
    )

    assert plan["reused"] == [LABEL]
    assert plan["recapture_required"] == []
    assert plan["selected_run_level_source"] is None
    assert plan["run_level_recapture_required"] is True


def test_relocated_lineage_remains_reusable_across_three_assemblies(
    tmp_path: Path,
) -> None:
    raw_manifest, _raw_payload = _manifest(tmp_path / "raw")
    first_manifest = assemble_capture_manifest(
        reuse_plan=_plan(raw_manifest),
        current_render_inputs=_render_inputs(),
        output_dir=tmp_path / "first",
    )
    second_manifest = assemble_capture_manifest(
        reuse_plan=_plan(first_manifest),
        current_render_inputs=_render_inputs(),
        output_dir=tmp_path / "second",
    )

    relocated = tmp_path / "relocated-second"
    shutil.move(str(second_manifest.parent), relocated)
    relocated_manifest = relocated / "manifest.json"
    third_manifest = assemble_capture_manifest(
        reuse_plan=_plan(relocated_manifest),
        current_render_inputs=_render_inputs(),
        output_dir=tmp_path / "third",
    )

    third_payload = json.loads(third_manifest.read_text(encoding="utf-8"))
    assert third_payload["complete"] is True
    assert len(third_payload["source_manifests"]) == 3
    assert all(
        (third_manifest.parent / row["path"]).is_file()
        for row in third_payload["source_manifests"]
    )


@pytest.mark.parametrize(
    "completion_state",
    ("missing", "empty", "mismatched", "contradictory"),
)
def test_unsealed_normal_manifest_cannot_seed_surface_or_run_reuse(
    tmp_path: Path,
    completion_state: str,
) -> None:
    manifest, _payload_value = _manifest(tmp_path / completion_state)
    completion = manifest.parent / "capture-complete.json"
    if completion_state == "missing":
        completion.unlink()
    elif completion_state == "empty":
        _write_json(completion, {})
    elif completion_state == "mismatched":
        completion_payload = json.loads(completion.read_text(encoding="utf-8"))
        completion_payload["manifest_sha256"] = "0" * 64
        _write_json(completion, completion_payload)
    else:
        completion_payload = json.loads(completion.read_text(encoding="utf-8"))
        completion_payload.update({
            "complete": False,
            "exit_code": 1,
            "scope_complete": False,
        })
        _write_json(completion, completion_payload)

    report = surface_validation_report(manifest)
    assert report["surfaces"][LABEL]["status"] == "failed"
    plan = _plan(manifest)
    assert plan["reused"] == []
    assert plan["recapture_required"] == [LABEL]
    assert plan["run_level_recapture_required"] is True


def test_unsealed_recovered_partial_salvages_only_atomic_surfaces(
    tmp_path: Path,
) -> None:
    payload = _payload(scope_complete=False)
    payload["capture_scope"] = "recovered-partial"
    manifest, _ = _manifest(
        tmp_path / "recovered",
        payload=payload,
        name="manifest.recovered.json",
        seal=False,
    )

    report = surface_validation_report(manifest)
    assert report["surfaces"][LABEL]["status"] == "passed"
    plan = _plan(manifest)
    assert plan["reused"] == [LABEL]
    assert plan["run_level_recapture_required"] is True


def test_duplicate_capture_labels_are_rejected_as_ambiguous(
    tmp_path: Path,
) -> None:
    payload = _payload(captures=[_record(), copy.deepcopy(_record())])
    manifest, _ = _manifest(tmp_path / "duplicate-records", payload=payload)

    with pytest.raises(CaptureEvidenceError, match="Duplicate capture label"):
        surface_validation_report(manifest)
    plan = _plan(manifest)
    assert plan["reused"] == []
    assert "Duplicate capture label" in plan["rejected_manifests"][0]["reason"]


def test_duplicate_recovery_sidecars_fail_closed(tmp_path: Path) -> None:
    capture_dir = tmp_path / "capture"
    progress = capture_dir / "progress"
    progress.mkdir(parents=True)
    png = capture_dir / f"{LABEL}.png"
    png.write_bytes(PNG_BYTES)
    partial_payload = _payload(captures=[])
    _write_json(capture_dir / "manifest.partial.json", partial_payload)
    record = _record()
    _write_json(progress / "first.json", {"record": record})
    _write_json(progress / "second.json", {"record": copy.deepcopy(record)})

    with pytest.raises(CaptureEvidenceError, match="Duplicate recovered capture label"):
        recover_progress_manifest(capture_dir)
