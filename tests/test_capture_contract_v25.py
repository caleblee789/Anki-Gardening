from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.capture.acquisition import (
    AcquisitionCandidate,
    AcquisitionIdentity,
    select_candidate,
)
from ankigarden.capture.contract import (
    compile_contract,
    contract_diff,
    load_compiled_contract,
)
from ankigarden.capture.lifecycle import FailureLedger, build_capture_plan
from ankigarden.capture.model import CaptureResult, ProfilePlacement
from ankigarden.capture.registry import REGISTRY, SurfaceRegistry
from scripts import capture_sequence
from scripts.package_addon import CAPTURE_BUILD, PRODUCTION_BUILD, package_files
from scripts.validate_ui_capture import (
    DEFAULT_CAPTURE_SOURCE,
    load_capture_contract,
    load_expected_state_evidence_contracts,
)


def _candidate(backend: str, **changes: object) -> AcquisitionCandidate:
    values: dict[str, object] = {
        "backend": backend,
        "pixmap": object(),
        "semantic_state_valid": True,
        "overlay_pixels_present": True,
    }
    values.update(changes)
    return AcquisitionCandidate(**values)


def _result(
    surface_id: str,
    *,
    accepted: bool,
    classification: str,
) -> CaptureResult:
    return CaptureResult(
        surface_id=surface_id,
        accepted=accepted,
        backend="qt-widget-grab",
        rejected_candidates=(),
        process_id=1,
        window_id=2,
        window_role="dialog",
        logical_geometry=(0, 0, 10, 10),
        pixel_geometry=(10, 10),
        device_pixel_ratio=1.0,
        checkpoint=REGISTRY[surface_id].checkpoint,
        semantic_audit={"passed": accepted},
        pixel_audit={"passed": accepted},
        dependency_digest=REGISTRY.surface_digest(surface_id),
        failure_classification=classification,
    )


def _replace_full_placement(
    stable_id: str,
    placement: ProfilePlacement,
):
    surface = REGISTRY[stable_id]
    return replace(
        surface,
        placements=tuple(
            placement if current.profile == "full" else current
            for current in surface.placements
        ),
    )


def test_compiled_contract_is_current_and_validator_consumes_it() -> None:
    compiled = load_compiled_contract()

    assert compiled == compile_contract()
    assert compiled["contract_version"] == 25
    full = load_capture_contract(DEFAULT_CAPTURE_SOURCE, profile="full")
    states = load_expected_state_evidence_contracts(
        DEFAULT_CAPTURE_SOURCE,
        contract=full,
    )
    assert full.labels == REGISTRY.profile_labels("full")
    assert set(states) == set(full.labels)


def test_current_topology_is_dynamic_and_redundant_ids_stay_reserved() -> None:
    compiled = load_compiled_contract()

    assert compiled["surface_count"] == len(REGISTRY.active_surfaces)
    assert compiled["profiles"]["representative"]["surface_count"] == len(
        REGISTRY.profile_labels("representative")
    )
    assert compiled["profiles"]["full"]["surface_count"] == len(
        REGISTRY.profile_labels("full")
    )
    assert set(compiled["retired_ids"]) == {
        surface.stable_id for surface in REGISTRY.retired_surfaces
    }
    assert {
        surface.stable_id
        for surface in REGISTRY.surfaces
        if surface.stable_id.startswith("watering-can-")
    } <= set(compiled["retired_ids"])
    assert not any(
        stable_id.startswith("watering-can-")
        for stable_id in REGISTRY.profile_labels("full")
    )


def test_adding_one_surface_changes_topology_without_invalidating_existing_pixels() -> None:
    base = REGISTRY["starter-garden-onboarding"]
    last = REGISTRY[REGISTRY.profile_labels("full")[-1]]
    last_full = next(item for item in last.placements if item.profile == "full")
    added = replace(
        base,
        stable_id="future-surface",
        placements=(ProfilePlacement(
            "full",
            last_full.group,
            last_full.group_order,
            last_full.order + 1,
            last_full.within_group_order + 1,
        ),),
        prerequisites=(),
        state_contract={
            **base.state_contract,
            "profile": {
                **base.state_contract["profile"],
                "profile_id": "future-surface",
            },
        },
    )
    expanded = REGISTRY.add(added)

    assert expanded.profile_labels("full")[-1] == "future-surface"
    assert expanded.surface_digest(base.stable_id) == REGISTRY.surface_digest(
        base.stable_id
    )
    assert contract_diff(compile_contract(REGISTRY), compile_contract(expanded))["added"] == [
        "future-surface"
    ]


def test_retired_ids_are_reserved_and_no_longer_active() -> None:
    stable_id = REGISTRY.profile_labels("full")[-1]
    retired = REGISTRY.retire(stable_id, "surface removed from the product")

    assert stable_id not in retired.profile_labels("full")
    assert retired[stable_id].retired_reason
    with pytest.raises(ValueError, match="permanently reserved"):
        retired.add(REGISTRY[stable_id])


def test_reordering_changes_only_profile_topology() -> None:
    first_id, second_id = REGISTRY.profile_labels("full")[:2]
    first = next(item for item in REGISTRY[first_id].placements if item.profile == "full")
    second = next(item for item in REGISTRY[second_id].placements if item.profile == "full")
    swapped = SurfaceRegistry(
        _replace_full_placement(second_id, replace(first, profile="full"))
        if surface.stable_id == second_id
        else _replace_full_placement(first_id, replace(second, profile="full"))
        if surface.stable_id == first_id
        else surface
        for surface in REGISTRY.surfaces
    )

    assert swapped.profile_labels("full")[:2] == (second_id, first_id)
    assert swapped.surface_digest(first_id) == REGISTRY.surface_digest(first_id)
    assert swapped.profile_digest("full") != REGISTRY.profile_digest("full")


def test_profile_rejects_a_dependency_after_its_dependent_surface() -> None:
    prerequisite_id = "selected-plant-nurtured"
    dependent_id = "active-deck-browser-home-after-nurture"
    prerequisite = next(
        item for item in REGISTRY[prerequisite_id].placements if item.profile == "full"
    )
    dependent = next(
        item for item in REGISTRY[dependent_id].placements if item.profile == "full"
    )

    with pytest.raises(ValueError, match="places prerequisite"):
        SurfaceRegistry(
            _replace_full_placement(
                prerequisite_id,
                replace(prerequisite, order=dependent.order),
            )
            if surface.stable_id == prerequisite_id
            else _replace_full_placement(
                dependent_id,
                replace(dependent, order=prerequisite.order),
            )
            if surface.stable_id == dependent_id
            else surface
            for surface in REGISTRY.surfaces
        )


def test_native_dialog_grab_is_fail_closed_without_screen_fallback() -> None:
    spec = REGISTRY["starter-garden-onboarding"]
    semantic_advisory = select_candidate(
        spec,
        (
            _candidate(
                "qt-widget-grab",
                semantic_state_valid=False,
                overlay_pixels_present=False,
            ),
        ),
    )
    decision = select_candidate(
        spec,
        (
            _candidate("qt-widget-grab", blank=True),
            _candidate("foreground-screen-region"),
        ),
    )

    assert semantic_advisory.accepted is not None
    assert decision.accepted is None
    assert decision.failure_reason == "blank-pixmap"
    assert {row.reason for row in decision.rejected} == {
        "backend-not-allowed",
        "blank-pixmap",
    }


def test_home_prefers_app_owned_webview_and_requires_exact_fallback_identity() -> None:
    spec = REGISTRY["starter-deck-browser-home"]
    identity = AcquisitionIdentity(11, 22, "main-window", (1, 2, 800, 600), 1.0)
    native = _candidate("qt-shell-with-webview")
    fallback = _candidate(
        "foreground-screen-region",
        process_id=11,
        window_id=22,
        window_role="main-window",
        bounds=(1, 2, 800, 600),
    )

    assert select_candidate(
        spec,
        (fallback, native),
        expected_identity=identity,
    ).accepted is native
    rejected = select_candidate(
        spec,
        (replace(native, blank=True), replace(fallback, process_id=99)),
        expected_identity=identity,
    )
    assert rejected.accepted is None
    assert rejected.failure_reason == "no-verified-capture-candidate"
    assert [row.reason for row in rejected.rejected] == [
        "blank-pixmap",
        "process-id-mismatch",
    ]


def test_capture_plan_keeps_checkpoint_domains_inside_one_session() -> None:
    requested = (
        "starter-garden-onboarding",
        "selected-plant-nurtured",
        "reviewer-find-stacked-sync",
    )
    plan = build_capture_plan(REGISTRY, profile="representative", requested=requested)

    assert plan.requested == requested
    assert [name for name, _labels in plan.cohorts] == [
        "starter",
        "nurtured",
        "reviewer-transaction",
    ]
    assert tuple(label for _name, labels in plan.cohorts for label in labels) == requested


def test_failure_ledger_isolates_local_checkpoint_and_run_gate_failures() -> None:
    local_id = "starter-garden-onboarding"
    checkpoint_id = "selected-plant-nurtured"
    ledger = FailureLedger(REGISTRY)

    ledger.record(_result(local_id, accepted=False, classification="surface-local"))
    assert ledger.may_continue(local_id, cleanup_restored=True)
    assert not ledger.may_continue(local_id, cleanup_restored=False)

    ledger.record(
        _result(checkpoint_id, accepted=False, classification="checkpoint-domain")
    )
    cohort = REGISTRY[checkpoint_id].checkpoint_cohort
    assert all(
        ledger.blocked.get(surface.stable_id) == checkpoint_id
        for surface in REGISTRY.active_surfaces
        if surface.checkpoint_cohort == cohort and surface.stable_id != checkpoint_id
    )

    ledger.record(_result("reviewer-find-stacked-sync", accepted=False, classification="run-gate"))
    assert ledger.release_blockers == ["reviewer-find-stacked-sync"]


def test_inspection_cli_is_non_mutating_and_registry_derived(capsys: pytest.CaptureFixture[str]) -> None:
    contract_path = Path(capture_sequence.CAPTURE_CONTRACT_PATH)
    before = contract_path.read_bytes()

    assert capture_sequence.main(["--list-surfaces"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in listed["surfaces"]] == list(
        REGISTRY.profile_labels("full")
    )
    assert capture_sequence.main([
        "--plan-only",
        "--surface",
        "starter-garden-onboarding",
    ]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["process_count"] == 1
    assert planned["process_strategy"] == "single-session"
    assert planned["run_gate_process"] == "same-session-or-zero-surface-when-reused"
    assert contract_path.read_bytes() == before


def test_production_package_excludes_complete_capture_subtree() -> None:
    production = {
        path.relative_to(Path(capture_sequence.REPO_ROOT) / "ankigarden").as_posix()
        for path in package_files(PRODUCTION_BUILD)
    }
    capture = {
        path.relative_to(Path(capture_sequence.REPO_ROOT) / "ankigarden").as_posix()
        for path in package_files(CAPTURE_BUILD)
    }

    assert "capture_ui_faces.py" not in production
    assert not any(name.startswith("capture/") for name in production)
    assert "capture_ui_faces.py" in capture
    assert "capture/runtime.py" in capture
    assert "capture/capture-contract-v25.json" in capture
    assert production < capture
