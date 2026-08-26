"""Failure isolation and resumable planning for one capture session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .model import CaptureResult, SurfaceSpec
from .registry import SurfaceRegistry


RUN_GATE_FAILURE_LABELS = frozenset({
    "capture-calibration",
    "capture-display",
    "capture-profile",
    "capture-provenance",
    "capture-registry",
    "capture-scenario-registry",
    "capture-selection",
    "dialog-scroll-audits",
    "responsive-stability",
})


def classify_failure(
    registry: SurfaceRegistry,
    *,
    label: str,
    reason: str,
    fatal_checkpoint_restore: bool = False,
) -> str:
    """Classify one runtime failure without depending on Qt or wording copy."""

    normalized_reason = reason.casefold()
    if fatal_checkpoint_restore or any(
        token in normalized_reason
        for token in (
            "checkpoint restoration",
            "fixture state restoration",
            "checkpoint could not be restored",
        )
    ):
        return "checkpoint-domain"
    if label in RUN_GATE_FAILURE_LABELS:
        return "run-gate"
    try:
        surface = registry[label]
    except KeyError:
        return "run-gate"
    return "surface-local" if surface.active else "run-gate"


@dataclass(frozen=True)
class CapturePlan:
    requested: tuple[str, ...]
    execution: tuple[str, ...]
    reused: tuple[str, ...]
    cohorts: tuple[tuple[str, tuple[str, ...]], ...]


def build_capture_plan(
    registry: SurfaceRegistry,
    *,
    profile: str,
    requested: Iterable[str] | None = None,
    reusable_digests: Mapping[str, str] | None = None,
) -> CapturePlan:
    profile_labels = registry.profile_labels(profile)
    requested_set = set(profile_labels if requested is None else requested)
    unknown = requested_set.difference(profile_labels)
    if unknown:
        raise ValueError("unknown requested surfaces: " + ", ".join(sorted(unknown)))

    execution_set = set(requested_set)
    changed = True
    while changed:
        changed = False
        for stable_id in tuple(execution_set):
            for prerequisite in registry[stable_id].prerequisites:
                if prerequisite not in execution_set:
                    execution_set.add(prerequisite)
                    changed = True

    reusable = reusable_digests or {}
    reused = tuple(
        stable_id for stable_id in profile_labels
        if stable_id in requested_set
        and reusable.get(stable_id) == registry.surface_digest(stable_id)
    )
    execution = tuple(
        stable_id for stable_id in profile_labels
        if stable_id in execution_set and stable_id not in reused
    )
    cohort_order = (
        "starter",
        "planted-base",
        "nurtured",
        "development-stress",
        "reviewer-transaction",
    )
    cohorts = tuple(
        (cohort, tuple(
            stable_id for stable_id in profile_labels
            if stable_id in requested_set
            and registry[stable_id].checkpoint_cohort == cohort
        ))
        for cohort in cohort_order
        if any(
            stable_id in requested_set
            and registry[stable_id].checkpoint_cohort == cohort
            for stable_id in profile_labels
        )
    )
    return CapturePlan(tuple(
        stable_id for stable_id in profile_labels if stable_id in requested_set
    ), execution, reused, cohorts)


@dataclass
class FailureLedger:
    """Apply v25 continuation and circuit-break rules without Qt."""

    registry: SurfaceRegistry
    results: dict[str, CaptureResult] = field(default_factory=dict)
    blocked: dict[str, str] = field(default_factory=dict)
    release_blockers: list[str] = field(default_factory=list)

    def record(self, result: CaptureResult) -> None:
        self.results[result.surface_id] = result
        classification = result.failure_classification
        if classification == "checkpoint-domain":
            cohort = self.registry[result.surface_id].checkpoint_cohort
            for spec in self.registry.active_surfaces:
                if spec.checkpoint_cohort == cohort and spec.stable_id not in self.results:
                    self.blocked[spec.stable_id] = result.surface_id
        elif classification == "run-gate":
            self.release_blockers.append(result.surface_id)

    def may_continue(self, stable_id: str, *, cleanup_restored: bool) -> bool:
        if stable_id in self.blocked:
            return False
        latest = self.results.get(stable_id)
        if latest is None or latest.accepted:
            return True
        return latest.failure_classification == "surface-local" and cleanup_restored
