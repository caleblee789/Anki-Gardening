"""Qt-free value objects shared by capture planning and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping


SURFACE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ACQUISITION_POLICIES = frozenset({
    "qt-widget-grab",
    "qt-shell-webview-verified",
})
FAILURE_CLASSIFICATIONS = frozenset({
    "none",
    "surface-local",
    "checkpoint-domain",
    "run-gate",
})


def _json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, tuple):
        return all(_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _json_value(item)
            for key, item in value.items()
        )
    return False


def _json_copy(value: Any) -> Any:
    """Return the immutable declaration as its canonical JSON value shape."""

    if isinstance(value, tuple):
        return [_json_copy(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class ProfilePlacement:
    profile: str
    group: str
    group_order: int
    order: int
    within_group_order: int

    def __post_init__(self) -> None:
        if not self.profile.strip() or not self.group.strip():
            raise ValueError("profile placement requires a profile and group")
        if min(self.group_order, self.order, self.within_group_order) < 0:
            raise ValueError("profile placement ordinals must be nonnegative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "group": self.group,
            "group_order": self.group_order,
            "order": self.order,
            "within_group_order": self.within_group_order,
        }


@dataclass(frozen=True)
class SurfaceSpec:
    """One stable, extensible UI-surface capture declaration."""

    stable_id: str
    active: bool
    placements: tuple[ProfilePlacement, ...]
    executor: str
    arguments: tuple[Any, ...]
    renderer_family: str
    acquisition_policy: str
    allow_foreground_fallback: bool
    checkpoint_cohort: str
    checkpoint: str
    prerequisites: tuple[str, ...]
    internal_setups: tuple[str, ...]
    readiness: tuple[str, ...]
    cleanup: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    owned_dependency_groups: tuple[str, ...]
    owned_module_dependencies: tuple[str, ...]
    state_contract: Mapping[str, Any] = field(default_factory=dict)
    retired_reason: str = ""

    def __post_init__(self) -> None:
        if SURFACE_ID.fullmatch(self.stable_id) is None:
            raise ValueError(f"invalid stable capture ID: {self.stable_id!r}")
        if self.active and self.retired_reason:
            raise ValueError(f"active surface {self.stable_id!r} has a retirement reason")
        if not self.active and not self.retired_reason.strip():
            raise ValueError(f"retired surface {self.stable_id!r} needs a reason")
        if self.active and not self.placements:
            raise ValueError(f"active surface {self.stable_id!r} has no profile")
        if not self.active and self.placements:
            raise ValueError(f"retired surface {self.stable_id!r} remains in a profile")
        if not self.executor.strip():
            raise ValueError(f"surface {self.stable_id!r} has no executor")
        if not _json_value(self.arguments):
            raise ValueError(f"surface {self.stable_id!r} arguments are not immutable JSON")
        if not self.renderer_family.strip():
            raise ValueError(f"surface {self.stable_id!r} has no renderer family")
        if self.acquisition_policy not in ACQUISITION_POLICIES:
            raise ValueError(
                f"surface {self.stable_id!r} has unknown acquisition policy "
                f"{self.acquisition_policy!r}"
            )
        if self.allow_foreground_fallback != (
            self.acquisition_policy == "qt-shell-webview-verified"
        ):
            raise ValueError(
                f"surface {self.stable_id!r} has an inconsistent fallback policy"
            )
        for name, values in (
            ("checkpoint cohort", (self.checkpoint_cohort,)),
            ("checkpoint", (self.checkpoint,)),
            ("internal setup", self.internal_setups),
            ("readiness", self.readiness),
            ("cleanup", self.cleanup),
            ("evidence requirement", self.evidence_requirements),
        ):
            if not values or any(not str(value).strip() for value in values):
                raise ValueError(f"surface {self.stable_id!r} has invalid {name} metadata")
        profiles = [placement.profile for placement in self.placements]
        if len(profiles) != len(set(profiles)):
            raise ValueError(f"surface {self.stable_id!r} repeats a profile")
        if self.active:
            if not _json_value(self.state_contract):
                raise ValueError(
                    f"surface {self.stable_id!r} has a non-JSON state contract"
                )
            profile = self.state_contract.get("profile")
            if not isinstance(profile, Mapping) or (
                profile.get("profile_id") != self.stable_id
            ):
                raise ValueError(
                    f"surface {self.stable_id!r} has a mismatched state profile"
                )
            if profile.get("window_family") != self.renderer_family:
                raise ValueError(
                    f"surface {self.stable_id!r} has a mismatched renderer family"
                )

    @property
    def profiles(self) -> tuple[str, ...]:
        return tuple(placement.profile for placement in self.placements)

    def pixel_contract(self) -> dict[str, Any]:
        """Return fields that can change the pixels or their acceptance.

        Profile membership and presentation order are deliberately absent, so
        adding, retiring, or reordering unrelated surfaces does not invalidate
        an accepted PNG.
        """

        return {
            "stable_id": self.stable_id,
            "executor": self.executor,
            "arguments": _json_copy(self.arguments),
            "renderer_family": self.renderer_family,
            "acquisition_policy": self.acquisition_policy,
            "allow_foreground_fallback": self.allow_foreground_fallback,
            "checkpoint_cohort": self.checkpoint_cohort,
            "checkpoint": self.checkpoint,
            "prerequisites": list(self.prerequisites),
            "internal_setups": list(self.internal_setups),
            "readiness": list(self.readiness),
            "cleanup": list(self.cleanup),
            "evidence_requirements": list(self.evidence_requirements),
            "owned_dependency_groups": list(self.owned_dependency_groups),
            "owned_module_dependencies": list(self.owned_module_dependencies),
            "state_contract": _json_copy(self.state_contract),
        }

    def as_dict(self) -> dict[str, Any]:
        pixel_contract = self.pixel_contract()
        pixel_contract.pop("stable_id")
        return {
            "id": self.stable_id,
            "active": self.active,
            "retired_reason": self.retired_reason,
            "placements": [placement.as_dict() for placement in self.placements],
            **pixel_contract,
        }


@dataclass(frozen=True)
class CandidateRejection:
    backend: str
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CaptureResult:
    surface_id: str
    accepted: bool
    backend: str
    rejected_candidates: tuple[CandidateRejection, ...]
    process_id: int | None
    window_id: int | None
    window_role: str
    logical_geometry: tuple[int, int, int, int]
    pixel_geometry: tuple[int, int]
    device_pixel_ratio: float
    checkpoint: str
    semantic_audit: Mapping[str, Any]
    pixel_audit: Mapping[str, Any]
    dependency_digest: str
    failure_classification: str = "none"
    blocked_by: str = ""

    def __post_init__(self) -> None:
        if self.failure_classification not in FAILURE_CLASSIFICATIONS:
            raise ValueError("unknown capture failure classification")
        if self.accepted and self.failure_classification != "none":
            raise ValueError("accepted capture cannot carry a failure classification")
        if not self.accepted and self.failure_classification == "none":
            raise ValueError("rejected capture must be classified")
        if self.device_pixel_ratio <= 0:
            raise ValueError("device pixel ratio must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "accepted": self.accepted,
            "backend": self.backend,
            "rejected_candidates": [item.as_dict() for item in self.rejected_candidates],
            "process_id": self.process_id,
            "window_id": self.window_id,
            "window_role": self.window_role,
            "logical_geometry": list(self.logical_geometry),
            "pixel_geometry": list(self.pixel_geometry),
            "device_pixel_ratio": self.device_pixel_ratio,
            "checkpoint": self.checkpoint,
            "semantic_audit": dict(self.semantic_audit),
            "pixel_audit": dict(self.pixel_audit),
            "dependency_digest": self.dependency_digest,
            "failure_classification": self.failure_classification,
            "blocked_by": self.blocked_by,
        }


@dataclass(frozen=True)
class RunGateResult:
    package_sha256: str
    contract_digest: str
    environment_digest: str
    evidence_digest: str
    memory_evidence: Mapping[str, Any]
    shutdown_evidence: Mapping[str, Any]
    release_eligible: bool
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("package_sha256", self.package_sha256),
            ("contract_digest", self.contract_digest),
            ("environment_digest", self.environment_digest),
            ("evidence_digest", self.evidence_digest),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if self.release_eligible != (not self.issues):
            raise ValueError("release eligibility must match the issue set")

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_sha256": self.package_sha256,
            "contract_digest": self.contract_digest,
            "environment_digest": self.environment_digest,
            "evidence_digest": self.evidence_digest,
            "memory_evidence": dict(self.memory_evidence),
            "shutdown_evidence": dict(self.shutdown_evidence),
            "release_eligible": self.release_eligible,
            "issues": list(self.issues),
        }
