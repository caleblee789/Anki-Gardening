"""Renderer-neutral Growth allocation and Growth Charge contracts."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .balance_catalog import (
    GROWTH_UNITS_PER_POINT,
    STAGES as BALANCE_STAGES,
    StageId,
)

# ``rare`` remains the durable runtime/artwork identifier for Full Bloom.
# Every threshold and presentation name comes from the canonical catalog.
GROWTH_STAGES = [
    "rare" if stage.stage_id is StageId.FULL_BLOOM else str(stage.stage_id)
    for stage in BALANCE_STAGES
]
GROWTH_THRESHOLDS = [stage.threshold_growth for stage in BALANCE_STAGES]


@dataclass(frozen=True)
class StagePresentation:
    """Canonical user-facing identity for one internal Growth stage."""

    stage_id: str
    display_name: str
    display_ordinal: int
    display_total: int
    threshold: int


_STAGE_DISPLAY_NAMES = {
    runtime_id: stage.display_name
    for runtime_id, stage in zip(GROWTH_STAGES, BALANCE_STAGES)
}

CANONICAL_STAGE_PROJECTION = tuple(
    StagePresentation(
        stage_id=stage_id,
        display_name=_STAGE_DISPLAY_NAMES[stage_id],
        display_ordinal=index + 1,
        display_total=len(GROWTH_STAGES),
        threshold=GROWTH_THRESHOLDS[index],
    )
    for index, stage_id in enumerate(GROWTH_STAGES)
)


def canonical_stage_projection() -> tuple[StagePresentation, ...]:
    """Return the six-stage player-facing contract in progression order."""

    return CANONICAL_STAGE_PROJECTION


def stage_presentation(value: Any) -> StagePresentation | None:
    """Resolve an internal or visible stage name without changing its ID."""

    normalized = str(value or "").replace("_", " ").strip().casefold()
    if normalized == "full bloom":
        normalized = "rare"
    return next(
        (
            item
            for item in CANONICAL_STAGE_PROJECTION
            if item.stage_id == normalized
        ),
        None,
    )


@dataclass(frozen=True)
class StageProgress:
    """One renderer-neutral projection of total and within-stage Growth."""

    stage: str
    stage_index: int
    next_stage: str | None
    stage_start: int
    next_threshold: int | None
    points_remaining: int
    progress: float
    fully_grown: bool
    stage_points: int
    stage_goal: int
    total_growth: int
    projected_total: int
    projected_stage: str
    completed_stages: tuple[str, ...]
    will_transition: bool
    rare_stage_unlocked: bool

    @property
    def current_stage(self) -> str:
        return self.stage

    @property
    def within_stage_growth(self) -> int:
        return self.stage_points

    @property
    def goal(self) -> int:
        return self.stage_goal


def stage_progress(
    total_growth: Any,
    projected_total: Any | None = None,
) -> StageProgress:
    """Return the single stage calculation used by model, game, and UI.

    ``projected_total`` is optional because most callers render current state.
    Transaction previews pass it to receive the exact crossed-stage and rare
    unlock projection without reproducing threshold logic.
    """

    try:
        total = max(0, int(total_growth))
    except (TypeError, ValueError):
        total = 0
    try:
        projected = (
            total
            if projected_total is None
            else max(total, max(0, int(projected_total)))
        )
    except (TypeError, ValueError):
        projected = total

    def stage_index_for(value: int) -> int:
        resolved = 0
        for index, threshold in enumerate(GROWTH_THRESHOLDS):
            if value >= threshold:
                resolved = index
        return resolved

    stage_index = stage_index_for(total)
    projected_index = stage_index_for(projected)
    stage = GROWTH_STAGES[stage_index]
    projected_stage = GROWTH_STAGES[projected_index]
    fully_grown = stage_index >= len(GROWTH_STAGES) - 1
    stage_start = GROWTH_THRESHOLDS[stage_index]
    if fully_grown:
        next_stage = None
        next_threshold = None
        points_remaining = 0
        stage_points = 0
        stage_goal = 0
        progress = 1.0
    else:
        next_stage = GROWTH_STAGES[stage_index + 1]
        next_threshold = GROWTH_THRESHOLDS[stage_index + 1]
        stage_points = max(0, total - stage_start)
        stage_goal = max(1, next_threshold - stage_start)
        points_remaining = max(0, next_threshold - total)
        progress = max(0.0, min(1.0, stage_points / stage_goal))
    completed_stages = tuple(
        GROWTH_STAGES[index]
        for index in range(stage_index + 1, projected_index + 1)
    )
    return StageProgress(
        stage=stage,
        stage_index=stage_index,
        next_stage=next_stage,
        stage_start=stage_start,
        next_threshold=next_threshold,
        points_remaining=points_remaining,
        progress=progress,
        fully_grown=fully_grown,
        stage_points=stage_points,
        stage_goal=stage_goal,
        total_growth=total,
        projected_total=projected,
        projected_stage=projected_stage,
        completed_stages=completed_stages,
        will_transition=projected_index > stage_index,
        rare_stage_unlocked="rare" in completed_stages,
    )


@dataclass(frozen=True)
class GrowthAllocation:
    """One plant's result from an already-calculated study Growth event."""

    plant_id: str
    role: str
    exact_fifths: int
    credited_growth: int
    residual_before_fifths: int = 0
    residual_after_fifths: int = 0
    requested_units: int = 0
    applied_units: int = 0
    redirected: bool = False

    @property
    def applied_growth(self) -> float:
        units = int(self.applied_units)
        if units <= 0:
            return float(max(0, int(self.credited_growth)))
        return units / GROWTH_UNITS_PER_POINT


@dataclass(frozen=True)
class GrowthGrantResult:
    """One conserved Growth transaction routed across plants and storage."""

    requested_units: int
    applied_units: int
    stored_units: int
    allocations: tuple[GrowthAllocation, ...] = ()
    original_target_id: str = ""
    active_target_id: str = ""
    auto_selected_target_id: str = ""
    landmark_units: int = 0

    @property
    def conserved(self) -> bool:
        return max(0, int(self.requested_units)) == (
            max(0, int(self.applied_units))
            + max(0, int(self.stored_units))
            + max(0, int(self.landmark_units))
        )

    @property
    def requested_growth(self) -> float:
        return max(0, int(self.requested_units)) / GROWTH_UNITS_PER_POINT

    @property
    def applied_growth(self) -> float:
        return max(0, int(self.applied_units)) / GROWTH_UNITS_PER_POINT

    @property
    def stored_growth(self) -> float:
        return max(0, int(self.stored_units)) / GROWTH_UNITS_PER_POINT


@dataclass(frozen=True)
class StageRewardProjection:
    stage: str
    garden_coins: int

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "garden_coins": self.garden_coins}

    @staticmethod
    def from_dict(value: Any) -> "StageRewardProjection | None":
        if not isinstance(value, dict):
            return None
        stage = value.get("stage")
        coins = value.get("garden_coins")
        if (
            not isinstance(stage, str)
            or not stage
            or not isinstance(coins, int)
            or isinstance(coins, bool)
            or coins < 0
        ):
            return None
        return StageRewardProjection(stage, coins)


class GrowthChargeStatus(str, Enum):
    READY = "ready"
    SUCCESS = "success"
    EMPTY_INVENTORY = "empty_inventory"
    TARGET_INVALID = "target_invalid"
    STALE_INVENTORY = "stale_inventory"
    STALE_TARGET = "stale_target"
    PERSISTENCE_FAILURE = "persistence_failure"
    REQUEST_ID_CONFLICT = "request_id_conflict"


class GrowthChargeTargetState(str, Enum):
    """Renderer-neutral eligibility state for the quoted target plant."""

    ELIGIBLE = "eligible"
    UNAVAILABLE = "unavailable"
    STORED = "stored"
    FULLY_GROWN = "fully_grown"


@dataclass(frozen=True)
class GrowthChargeProjection:
    """Pure transaction projection for one attempted Growth Charge use.

    ``applied_growth`` is the portion that fits on the selected plant.
    ``overflow_growth`` remains available to the engine's normal conserved
    routing, while a rejected attempt keeps all requested Growth unconsumed.
    """

    status: GrowthChargeStatus
    target_state: GrowthChargeTargetState
    current_growth: int
    requested_growth: int
    applied_growth: int
    overflow_growth: int
    unconsumed_growth: int
    projected_growth: int
    current_stage: str
    projected_stage: str
    completed_stages: tuple[str, ...]
    will_transition: bool
    inventory_before: int
    inventory_after: int
    next_stage: str | None
    stage_points_after: int
    stage_goal_after: int

    @property
    def ready(self) -> bool:
        return self.status is GrowthChargeStatus.READY

    @property
    def granted_growth(self) -> int:
        return self.applied_growth + self.overflow_growth

    @property
    def conserved(self) -> bool:
        return self.requested_growth == (
            self.applied_growth
            + self.overflow_growth
            + self.unconsumed_growth
        )


def project_growth_charge_application(
    current_growth: Any,
    requested_growth: Any,
    inventory_before: Any,
    *,
    target_state: GrowthChargeTargetState = GrowthChargeTargetState.ELIGIBLE,
) -> GrowthChargeProjection:
    """Project one Charge use without mutating inventory or plant state."""

    def nonnegative(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    current = nonnegative(current_growth)
    requested = nonnegative(requested_growth)
    inventory = nonnegative(inventory_before)
    try:
        resolved_target = GrowthChargeTargetState(target_state)
    except (TypeError, ValueError):
        resolved_target = GrowthChargeTargetState.UNAVAILABLE

    before = stage_progress(current)
    if before.fully_grown:
        resolved_target = GrowthChargeTargetState.FULLY_GROWN
    if resolved_target is not GrowthChargeTargetState.ELIGIBLE or requested <= 0:
        status = GrowthChargeStatus.TARGET_INVALID
    elif inventory <= 0:
        status = GrowthChargeStatus.EMPTY_INVENTORY
    else:
        status = GrowthChargeStatus.READY

    accepted = status is GrowthChargeStatus.READY
    capacity = max(0, GROWTH_THRESHOLDS[-1] - current)
    applied = min(requested, capacity) if accepted else 0
    overflow = max(0, requested - applied) if accepted else 0
    unconsumed = 0 if accepted else requested
    projected = current + applied
    after = stage_progress(projected)
    transition = stage_progress(current, projected)
    return GrowthChargeProjection(
        status=status,
        target_state=resolved_target,
        current_growth=current,
        requested_growth=requested,
        applied_growth=applied,
        overflow_growth=overflow,
        unconsumed_growth=unconsumed,
        projected_growth=projected,
        current_stage=before.stage,
        projected_stage=after.stage,
        completed_stages=transition.completed_stages,
        will_transition=transition.will_transition,
        inventory_before=inventory,
        inventory_after=max(0, inventory - (1 if accepted else 0)),
        next_stage=after.next_stage,
        stage_points_after=after.stage_points,
        stage_goal_after=after.stage_goal,
    )


@dataclass(frozen=True)
class GrowthChargeQuote:
    status: GrowthChargeStatus
    charge_id: str
    charge_name: str
    target_id: str
    target_name: str
    target_species: str
    target_stage: str
    target_state: GrowthChargeTargetState
    current_growth: int
    requested_growth: int
    granted_growth: int
    projected_growth: int
    projected_stage: str
    completed_stages: tuple[str, ...]
    rewards: tuple[StageRewardProjection, ...]
    inventory_before: int
    inventory_after: int
    quote_token: str
    message: str = ""

    @property
    def ready(self) -> bool:
        return self.status is GrowthChargeStatus.READY


@dataclass(frozen=True)
class GrowthChargeRequest:
    request_id: str
    charge_id: str
    target_id: str
    quote_token: str
    expected_inventory: int
    expected_growth: int

    @staticmethod
    def from_quote(
        quote: GrowthChargeQuote,
        *,
        request_id: str | None = None,
    ) -> "GrowthChargeRequest":
        return GrowthChargeRequest(
            request_id=str(request_id or uuid.uuid4()),
            charge_id=quote.charge_id,
            target_id=quote.target_id,
            quote_token=quote.quote_token,
            expected_inventory=quote.inventory_before,
            expected_growth=quote.current_growth,
        )

    def fingerprint(self) -> str:
        payload = {
            "charge_id": self.charge_id,
            "target_id": self.target_id,
            "quote_token": self.quote_token,
            "expected_inventory": self.expected_inventory,
            "expected_growth": self.expected_growth,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class GrowthChargeOutcome:
    status: GrowthChargeStatus
    charge_id: str
    charge_name: str
    target_id: str
    target_name: str
    previous_growth: int
    resulting_growth: int
    growth_granted: int
    previous_stage: str
    resulting_stage: str
    completed_stages: tuple[str, ...]
    rewards: tuple[StageRewardProjection, ...]
    inventory_remaining: int
    message: str

    @property
    def success(self) -> bool:
        return self.status is GrowthChargeStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "charge_id": self.charge_id,
            "charge_name": self.charge_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "previous_growth": self.previous_growth,
            "resulting_growth": self.resulting_growth,
            "growth_granted": self.growth_granted,
            "previous_stage": self.previous_stage,
            "resulting_stage": self.resulting_stage,
            "completed_stages": list(self.completed_stages),
            "rewards": [reward.to_dict() for reward in self.rewards],
            "inventory_remaining": self.inventory_remaining,
            "message": self.message,
        }

    @staticmethod
    def from_dict(value: Any) -> "GrowthChargeOutcome | None":
        if not isinstance(value, dict):
            return None
        try:
            status = GrowthChargeStatus(str(value.get("status", "")))
        except ValueError:
            return None
        strings = (
            "charge_id",
            "charge_name",
            "target_id",
            "target_name",
            "previous_stage",
            "resulting_stage",
            "message",
        )
        if any(not isinstance(value.get(key), str) for key in strings):
            return None
        integers = (
            "previous_growth",
            "resulting_growth",
            "growth_granted",
            "inventory_remaining",
        )
        if any(
            not isinstance(value.get(key), int)
            or isinstance(value.get(key), bool)
            or int(value[key]) < 0
            for key in integers
        ):
            return None
        stages = value.get("completed_stages", [])
        raw_rewards = value.get("rewards", [])
        if (
            not isinstance(stages, list)
            or any(not isinstance(stage, str) for stage in stages)
            or not isinstance(raw_rewards, list)
        ):
            return None
        rewards = tuple(
            reward
            for raw in raw_rewards
            if (reward := StageRewardProjection.from_dict(raw)) is not None
        )
        if len(rewards) != len(raw_rewards):
            return None
        return GrowthChargeOutcome(
            status=status,
            charge_id=str(value["charge_id"]),
            charge_name=str(value["charge_name"]),
            target_id=str(value["target_id"]),
            target_name=str(value["target_name"]),
            previous_growth=int(value["previous_growth"]),
            resulting_growth=int(value["resulting_growth"]),
            growth_granted=int(value["growth_granted"]),
            previous_stage=str(value["previous_stage"]),
            resulting_stage=str(value["resulting_stage"]),
            completed_stages=tuple(stages),
            rewards=rewards,
            inventory_remaining=int(value["inventory_remaining"]),
            message=str(value["message"]),
        )


@dataclass(frozen=True)
class CompletedGrowthChargeRequest:
    request_id: str
    request_fingerprint: str
    outcome: GrowthChargeOutcome
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "outcome": self.outcome.to_dict(),
            "occurred_at": self.occurred_at,
        }

    @staticmethod
    def from_dict(value: Any) -> "CompletedGrowthChargeRequest | None":
        if not isinstance(value, dict):
            return None
        request_id = value.get("request_id")
        fingerprint = value.get("request_fingerprint")
        occurred_at = value.get("occurred_at")
        outcome = GrowthChargeOutcome.from_dict(value.get("outcome"))
        try:
            canonical_id = str(uuid.UUID(str(request_id)))
        except (ValueError, TypeError, AttributeError):
            return None
        if (
            not isinstance(request_id, str)
            or request_id != canonical_id
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not isinstance(occurred_at, str)
            or not occurred_at
            or outcome is None
        ):
            return None
        return CompletedGrowthChargeRequest(
            request_id=request_id,
            request_fingerprint=fingerprint,
            outcome=outcome,
            occurred_at=occurred_at,
        )
