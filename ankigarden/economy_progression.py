"""Pure Garden Landmark and Cultivation Mastery transaction contracts.

The engine owns mutable state, persistence, and resource ledgers.  This module
accepts immutable snapshots and canonical UUID requests, then returns quotes or
projected outcomes without mutating anything.  Growth is always represented in
exact hundredth-Growth integer units.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Optional
from uuid import UUID

from .balance_catalog import (
    CURRENT_CATALOG_SPECIES_ORDER,
    GARDEN_LEGACY,
    GROWTH_UNITS_PER_POINT,
    LANDMARKS,
    MASTERY_RANKS,
    SPECIES_BY_ID,
    catalog_snapshot,
)


ECONOMY_PROGRESSION_CONTRACT_VERSION = 2

LANDMARK_ORDER = tuple(item.landmark_id.value for item in LANDMARKS)
LANDMARK_BY_ID = MappingProxyType({
    item.landmark_id.value: item
    for item in LANDMARKS
})
LANDMARK_GROWTH_COST_UNITS = MappingProxyType({
    item.landmark_id.value: item.growth_cost * GROWTH_UNITS_PER_POINT
    for item in LANDMARKS
})

MASTERY_RANK_ORDER = tuple(item.rank_id.value for item in MASTERY_RANKS)
MASTERY_RANK_BY_ID = MappingProxyType({
    item.rank_id.value: item
    for item in MASTERY_RANKS
})
MASTERY_GROWTH_COST_UNITS = MappingProxyType({
    item.rank_id.value: item.growth_cost * GROWTH_UNITS_PER_POINT
    for item in MASTERY_RANKS
})
LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS = MappingProxyType({
    item.landmark_id.value: (
        item.cumulative_growth_threshold * GROWTH_UNITS_PER_POINT
    )
    for item in LANDMARKS
})
MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS = MappingProxyType({
    item.rank_id.value: (
        item.cumulative_growth_threshold * GROWTH_UNITS_PER_POINT
    )
    for item in MASTERY_RANKS
})
LANDMARK_MAX_GROWTH_UNITS = sum(LANDMARK_GROWTH_COST_UNITS.values())
MASTERY_MAX_GROWTH_UNITS = sum(MASTERY_GROWTH_COST_UNITS.values())
GARDEN_LEGACY_LEVEL_COST_UNITS = (
    GARDEN_LEGACY.growth_cost_per_level * GROWTH_UNITS_PER_POINT
)
ACTIVE_SPECIES = frozenset(CURRENT_CATALOG_SPECIES_ORDER)
_SPECIES_INDEX = {
    species_id: index
    for index, species_id in enumerate(CURRENT_CATALOG_SPECIES_ORDER)
}


class StableStringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class LandmarkAction(StableStringEnum):
    SELECT = "select"
    CONTRIBUTE = "contribute"
    COMPLETE = "complete"


class ProgressionDisposition(StableStringEnum):
    APPROVED = "approved"
    APPLIED = "applied"
    ALREADY_SELECTED = "already_selected"
    ALREADY_COMPLETE = "already_complete"
    NO_CHANGE = "no_change"
    INVALID_ORDER = "invalid_order"
    INSUFFICIENT_GROWTH = "insufficient_growth"
    INSUFFICIENT_COINS = "insufficient_coins"
    NOT_READY = "not_ready"


def _require_nonnegative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value


def canonical_request_id(value: object) -> str:
    """Return a canonical lowercase, hyphenated UUID or raise ``ValueError``."""

    if not isinstance(value, str) or not value:
        raise TypeError("request_id must be a nonempty string")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError("request_id must be a canonical UUID") from error
    canonical = str(parsed)
    if value != canonical:
        raise ValueError("request_id must use canonical lowercase UUID form")
    return canonical


def _stable_fingerprint(request_type: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {
            "contract_version": ECONOMY_PROGRESSION_CONTRACT_VERSION,
            "request_type": request_type,
            **payload,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def economy_catalog_digest() -> str:
    encoded = json.dumps(
        catalog_snapshot(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LandmarkProjectSnapshot:
    selected_landmark_id: str = ""
    contributed_growth_units: int = 0
    ready_to_complete: bool = False
    completed_landmark_ids: tuple[str, ...] = ()
    displayed_landmark_id: str = ""

    def __post_init__(self) -> None:
        validate_landmark_snapshot(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_landmark_id": self.selected_landmark_id,
            "contributed_growth_units": self.contributed_growth_units,
            "ready_to_complete": self.ready_to_complete,
            "completed_landmark_ids": list(self.completed_landmark_ids),
            "displayed_landmark_id": self.displayed_landmark_id,
        }


def validate_landmark_snapshot(snapshot: LandmarkProjectSnapshot) -> None:
    if not isinstance(snapshot, LandmarkProjectSnapshot):
        raise TypeError("snapshot must be a LandmarkProjectSnapshot")
    if not isinstance(snapshot.completed_landmark_ids, tuple):
        raise TypeError("completed Landmark IDs must be an immutable tuple")
    if any(item_id not in LANDMARK_BY_ID for item_id in snapshot.completed_landmark_ids):
        raise ValueError("completed Landmark IDs must be canonical catalog IDs")
    if len(snapshot.completed_landmark_ids) != len(set(snapshot.completed_landmark_ids)):
        raise ValueError("completed Landmark IDs cannot contain duplicates")
    completed_count = len(snapshot.completed_landmark_ids)
    if snapshot.completed_landmark_ids != LANDMARK_ORDER[:completed_count]:
        raise ValueError("completed Landmarks must be the canonical sequence prefix")
    _require_nonnegative_integer(
        snapshot.contributed_growth_units,
        "contributed_growth_units",
    )
    if not isinstance(snapshot.ready_to_complete, bool):
        raise TypeError("ready_to_complete must be a boolean")
    if snapshot.selected_landmark_id:
        if completed_count >= len(LANDMARK_ORDER):
            raise ValueError("a completed Landmark sequence cannot retain a selection")
        expected = LANDMARK_ORDER[completed_count]
        if snapshot.selected_landmark_id != expected:
            raise ValueError("selected Landmark must be the next canonical Landmark")
        required_units = LANDMARK_GROWTH_COST_UNITS[expected]
        if snapshot.contributed_growth_units > required_units:
            raise ValueError("contributed Growth cannot exceed the Landmark cost")
        expected_ready = snapshot.contributed_growth_units == required_units
        if snapshot.ready_to_complete != expected_ready:
            raise ValueError("ready_to_complete must match the exact Growth cost")
    elif snapshot.contributed_growth_units or snapshot.ready_to_complete:
        raise ValueError("an empty Landmark selection cannot retain contribution state")
    if snapshot.displayed_landmark_id:
        if snapshot.displayed_landmark_id not in snapshot.completed_landmark_ids:
            raise ValueError("displayed Landmark must already be complete")


def landmark_snapshot(
    *,
    selected_landmark_id: object = "",
    contributed_growth_units: object = 0,
    ready_to_complete: object = False,
    completed_landmark_ids: object = (),
    displayed_landmark_id: object = "",
) -> LandmarkProjectSnapshot:
    """Normalize a persistence projection into an immutable contract."""

    if isinstance(completed_landmark_ids, str):
        raise TypeError("completed Landmark IDs must be an iterable of IDs")
    return LandmarkProjectSnapshot(
        selected_landmark_id=str(selected_landmark_id or ""),
        contributed_growth_units=_require_nonnegative_integer(
            contributed_growth_units,
            "contributed_growth_units",
        ),
        ready_to_complete=ready_to_complete,
        completed_landmark_ids=tuple(str(value) for value in completed_landmark_ids),
        displayed_landmark_id=str(displayed_landmark_id or ""),
    )


def next_landmark_id(snapshot: LandmarkProjectSnapshot) -> Optional[str]:
    validate_landmark_snapshot(snapshot)
    completed_count = len(snapshot.completed_landmark_ids)
    if completed_count >= len(LANDMARK_ORDER):
        return None
    return LANDMARK_ORDER[completed_count]


@dataclass(frozen=True)
class LandmarkRequest:
    request_id: str
    action: LandmarkAction
    landmark_id: str
    growth_units: int = 0

    def __post_init__(self) -> None:
        canonical_request_id(self.request_id)
        if not isinstance(self.action, LandmarkAction):
            raise TypeError("action must be a LandmarkAction")
        if self.landmark_id not in LANDMARK_BY_ID:
            raise ValueError("landmark_id must be a canonical Landmark ID")
        _require_nonnegative_integer(self.growth_units, "growth_units")
        if self.action is LandmarkAction.CONTRIBUTE:
            if self.growth_units <= 0:
                raise ValueError("Landmark contributions must be positive")
        elif self.growth_units:
            raise ValueError("only contribution requests may include Growth")

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint("landmark", self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action.value,
            "landmark_id": self.landmark_id,
            "growth_units": self.growth_units,
        }


@dataclass(frozen=True)
class LandmarkQuote:
    request_id: str
    request_fingerprint: str
    action: LandmarkAction
    landmark_id: str
    disposition: ProgressionDisposition
    can_apply: bool
    message: str
    growth_cost_units: int
    coin_cost: int
    contributed_before_units: int
    growth_spend_units: int
    contributed_after_units: int
    remaining_growth_units: int
    ready_to_complete_after: bool
    coin_spend: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "action": self.action.value,
            "landmark_id": self.landmark_id,
            "disposition": self.disposition.value,
            "can_apply": self.can_apply,
            "message": self.message,
            "growth_cost_units": self.growth_cost_units,
            "coin_cost": self.coin_cost,
            "contributed_before_units": self.contributed_before_units,
            "growth_spend_units": self.growth_spend_units,
            "contributed_after_units": self.contributed_after_units,
            "remaining_growth_units": self.remaining_growth_units,
            "ready_to_complete_after": self.ready_to_complete_after,
            "coin_spend": self.coin_spend,
        }


@dataclass(frozen=True)
class LandmarkOutcome:
    request_id: str
    request_fingerprint: str
    action: LandmarkAction
    landmark_id: str
    disposition: ProgressionDisposition
    applied: bool
    growth_spent_units: int
    coins_spent: int
    snapshot: LandmarkProjectSnapshot
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "action": self.action.value,
            "landmark_id": self.landmark_id,
            "disposition": self.disposition.value,
            "applied": self.applied,
            "growth_spent_units": self.growth_spent_units,
            "coins_spent": self.coins_spent,
            "snapshot": self.snapshot.to_dict(),
            "message": self.message,
        }


def _landmark_quote(
    request: LandmarkRequest,
    *,
    disposition: ProgressionDisposition,
    can_apply: bool,
    message: str,
    contributed_before: int,
    growth_spend: int = 0,
    contributed_after: Optional[int] = None,
    ready_after: bool = False,
    coin_spend: int = 0,
) -> LandmarkQuote:
    cost_units = LANDMARK_GROWTH_COST_UNITS[request.landmark_id]
    after = contributed_before if contributed_after is None else contributed_after
    return LandmarkQuote(
        request_id=request.request_id,
        request_fingerprint=request.fingerprint,
        action=request.action,
        landmark_id=request.landmark_id,
        disposition=disposition,
        can_apply=can_apply,
        message=message,
        growth_cost_units=cost_units,
        coin_cost=LANDMARK_BY_ID[request.landmark_id].coin_cost,
        contributed_before_units=contributed_before,
        growth_spend_units=growth_spend,
        contributed_after_units=after,
        remaining_growth_units=max(0, cost_units - after),
        ready_to_complete_after=ready_after,
        coin_spend=coin_spend,
    )


def quote_landmark_request(
    snapshot: LandmarkProjectSnapshot,
    request: LandmarkRequest,
    *,
    available_growth_units: int = 0,
    available_coins: int = 0,
) -> LandmarkQuote:
    """Validate a Landmark request and quote its exact resource spend."""

    validate_landmark_snapshot(snapshot)
    if not isinstance(request, LandmarkRequest):
        raise TypeError("request must be a LandmarkRequest")
    available_growth = _require_nonnegative_integer(
        available_growth_units,
        "available_growth_units",
    )
    coins = _require_nonnegative_integer(available_coins, "available_coins")
    contributed = snapshot.contributed_growth_units

    if request.landmark_id in snapshot.completed_landmark_ids:
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.ALREADY_COMPLETE,
            can_apply=False,
            message="Landmark is already complete.",
            contributed_before=contributed,
            ready_after=snapshot.ready_to_complete,
        )

    expected = next_landmark_id(snapshot)
    if request.landmark_id != expected:
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.INVALID_ORDER,
            can_apply=False,
            message="Landmarks must be completed in catalog order.",
            contributed_before=contributed,
            ready_after=snapshot.ready_to_complete,
        )

    if request.action is LandmarkAction.SELECT:
        if snapshot.selected_landmark_id == request.landmark_id:
            return _landmark_quote(
                request,
                disposition=ProgressionDisposition.ALREADY_SELECTED,
                can_apply=False,
                message="Landmark is already selected.",
                contributed_before=contributed,
                ready_after=snapshot.ready_to_complete,
            )
        if snapshot.selected_landmark_id:
            return _landmark_quote(
                request,
                disposition=ProgressionDisposition.INVALID_ORDER,
                can_apply=False,
                message="Complete the selected Landmark first.",
                contributed_before=contributed,
                ready_after=snapshot.ready_to_complete,
            )
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.APPROVED,
            can_apply=True,
            message="Landmark can be selected.",
            contributed_before=0,
        )

    if snapshot.selected_landmark_id != request.landmark_id:
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.INVALID_ORDER,
            can_apply=False,
            message="Select the next Landmark before contributing or completing.",
            contributed_before=contributed,
            ready_after=snapshot.ready_to_complete,
        )

    if request.action is LandmarkAction.CONTRIBUTE:
        cost_units = LANDMARK_GROWTH_COST_UNITS[request.landmark_id]
        remaining = max(0, cost_units - contributed)
        if remaining == 0:
            return _landmark_quote(
                request,
                disposition=ProgressionDisposition.NO_CHANGE,
                can_apply=False,
                message="Landmark already has its full Growth contribution.",
                contributed_before=contributed,
                ready_after=True,
            )
        spend = min(request.growth_units, remaining)
        if available_growth < spend:
            return _landmark_quote(
                request,
                disposition=ProgressionDisposition.INSUFFICIENT_GROWTH,
                can_apply=False,
                message="Not enough stored Growth for this contribution.",
                contributed_before=contributed,
                ready_after=False,
            )
        after = contributed + spend
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.APPROVED,
            can_apply=True,
            message="Growth contribution can be applied.",
            contributed_before=contributed,
            growth_spend=spend,
            contributed_after=after,
            ready_after=after == cost_units,
        )

    if not snapshot.ready_to_complete:
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.NOT_READY,
            can_apply=False,
            message="Finish the Growth contribution before completing this Landmark.",
            contributed_before=contributed,
            ready_after=False,
        )
    coin_cost = LANDMARK_BY_ID[request.landmark_id].coin_cost
    if coins < coin_cost:
        return _landmark_quote(
            request,
            disposition=ProgressionDisposition.INSUFFICIENT_COINS,
            can_apply=False,
            message="Not enough Garden Coins to complete this Landmark.",
            contributed_before=contributed,
            ready_after=True,
        )
    return _landmark_quote(
        request,
        disposition=ProgressionDisposition.APPROVED,
        can_apply=True,
        message="Landmark can be completed.",
        contributed_before=contributed,
        ready_after=True,
        coin_spend=coin_cost,
    )


def project_landmark_request(
    snapshot: LandmarkProjectSnapshot,
    request: LandmarkRequest,
    *,
    available_growth_units: int = 0,
    available_coins: int = 0,
) -> LandmarkOutcome:
    """Return the deterministic post-request snapshot and exact spends."""

    quote = quote_landmark_request(
        snapshot,
        request,
        available_growth_units=available_growth_units,
        available_coins=available_coins,
    )
    if not quote.can_apply:
        return LandmarkOutcome(
            request.request_id,
            request.fingerprint,
            request.action,
            request.landmark_id,
            quote.disposition,
            False,
            0,
            0,
            snapshot,
            quote.message,
        )

    if request.action is LandmarkAction.SELECT:
        projected = LandmarkProjectSnapshot(
            selected_landmark_id=request.landmark_id,
            completed_landmark_ids=snapshot.completed_landmark_ids,
            displayed_landmark_id=snapshot.displayed_landmark_id,
        )
    elif request.action is LandmarkAction.CONTRIBUTE:
        projected = LandmarkProjectSnapshot(
            selected_landmark_id=request.landmark_id,
            contributed_growth_units=quote.contributed_after_units,
            ready_to_complete=quote.ready_to_complete_after,
            completed_landmark_ids=snapshot.completed_landmark_ids,
            displayed_landmark_id=snapshot.displayed_landmark_id,
        )
    else:
        projected = LandmarkProjectSnapshot(
            completed_landmark_ids=(
                *snapshot.completed_landmark_ids,
                request.landmark_id,
            ),
            displayed_landmark_id=request.landmark_id,
        )
    return LandmarkOutcome(
        request.request_id,
        request.fingerprint,
        request.action,
        request.landmark_id,
        ProgressionDisposition.APPLIED,
        True,
        quote.growth_spend_units,
        quote.coin_spend,
        projected,
        quote.message,
    )


@dataclass(frozen=True)
class MasterySnapshot:
    highest_rank_by_species: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        validate_mastery_snapshot(self)

    def rank_for(self, species_id: str) -> Optional[str]:
        return dict(self.highest_rank_by_species).get(species_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "highest_rank_by_species": {
                species_id: rank_id
                for species_id, rank_id in self.highest_rank_by_species
            }
        }


def validate_mastery_snapshot(snapshot: MasterySnapshot) -> None:
    if not isinstance(snapshot, MasterySnapshot):
        raise TypeError("snapshot must be a MasterySnapshot")
    if not isinstance(snapshot.highest_rank_by_species, tuple):
        raise TypeError("Mastery entries must be an immutable tuple")
    species_ids = tuple(item[0] for item in snapshot.highest_rank_by_species)
    if len(species_ids) != len(set(species_ids)):
        raise ValueError("Mastery species cannot contain duplicates")
    if any(species_id not in ACTIVE_SPECIES for species_id in species_ids):
        raise ValueError("Mastery is available only for active catalog species")
    if any(rank_id not in MASTERY_RANK_BY_ID for _, rank_id in snapshot.highest_rank_by_species):
        raise ValueError("Mastery entries require canonical rank IDs")
    expected_order = tuple(sorted(species_ids, key=_SPECIES_INDEX.__getitem__))
    if species_ids != expected_order:
        raise ValueError("Mastery entries must use canonical species order")


def mastery_snapshot(highest_rank_by_species: Mapping[object, object]) -> MasterySnapshot:
    """Normalize a persisted Mastery mapping into canonical species order."""

    if not isinstance(highest_rank_by_species, Mapping):
        raise TypeError("highest_rank_by_species must be a mapping")
    normalized = {
        str(species_id): str(rank_id)
        for species_id, rank_id in highest_rank_by_species.items()
    }
    unknown_species = set(normalized).difference(ACTIVE_SPECIES)
    if unknown_species:
        raise ValueError("Mastery is available only for active catalog species")
    return MasterySnapshot(tuple(
        (species_id, normalized[species_id])
        for species_id in CURRENT_CATALOG_SPECIES_ORDER
        if species_id in normalized
    ))


def next_mastery_rank_id(snapshot: MasterySnapshot, species_id: str) -> Optional[str]:
    validate_mastery_snapshot(snapshot)
    if species_id not in ACTIVE_SPECIES:
        raise ValueError("species_id must be an active catalog species")
    current = snapshot.rank_for(species_id)
    if current is None:
        return MASTERY_RANK_ORDER[0]
    current_index = MASTERY_RANK_ORDER.index(current)
    if current_index + 1 >= len(MASTERY_RANK_ORDER):
        return None
    return MASTERY_RANK_ORDER[current_index + 1]


@dataclass(frozen=True)
class MasteryRequest:
    request_id: str
    species_id: str
    rank_id: str

    def __post_init__(self) -> None:
        canonical_request_id(self.request_id)
        if self.species_id not in ACTIVE_SPECIES:
            raise ValueError("species_id must be an active catalog species")
        if self.rank_id not in MASTERY_RANK_BY_ID:
            raise ValueError("rank_id must be a canonical Mastery rank")

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint("mastery", self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "species_id": self.species_id,
            "rank_id": self.rank_id,
        }


@dataclass(frozen=True)
class MasteryQuote:
    request_id: str
    request_fingerprint: str
    species_id: str
    rank_id: str
    disposition: ProgressionDisposition
    can_apply: bool
    message: str
    next_rank_id: Optional[str]
    growth_spend_units: int
    coin_spend: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "species_id": self.species_id,
            "rank_id": self.rank_id,
            "disposition": self.disposition.value,
            "can_apply": self.can_apply,
            "message": self.message,
            "next_rank_id": self.next_rank_id,
            "growth_spend_units": self.growth_spend_units,
            "coin_spend": self.coin_spend,
        }


@dataclass(frozen=True)
class MasteryOutcome:
    request_id: str
    request_fingerprint: str
    species_id: str
    rank_id: str
    disposition: ProgressionDisposition
    applied: bool
    growth_spent_units: int
    coins_spent: int
    snapshot: MasterySnapshot
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "species_id": self.species_id,
            "rank_id": self.rank_id,
            "disposition": self.disposition.value,
            "applied": self.applied,
            "growth_spent_units": self.growth_spent_units,
            "coins_spent": self.coins_spent,
            "snapshot": self.snapshot.to_dict(),
            "message": self.message,
        }


def _mastery_quote(
    request: MasteryRequest,
    *,
    disposition: ProgressionDisposition,
    can_apply: bool,
    message: str,
    next_rank_id: Optional[str],
    spend: bool = False,
) -> MasteryQuote:
    return MasteryQuote(
        request.request_id,
        request.fingerprint,
        request.species_id,
        request.rank_id,
        disposition,
        can_apply,
        message,
        next_rank_id,
        MASTERY_GROWTH_COST_UNITS[request.rank_id] if spend else 0,
        MASTERY_RANK_BY_ID[request.rank_id].coin_cost if spend else 0,
    )


def quote_mastery_request(
    snapshot: MasterySnapshot,
    request: MasteryRequest,
    *,
    available_growth_units: int,
    available_coins: int,
) -> MasteryQuote:
    """Quote an atomic dual-resource purchase of one species' next rank."""

    validate_mastery_snapshot(snapshot)
    if not isinstance(request, MasteryRequest):
        raise TypeError("request must be a MasteryRequest")
    growth = _require_nonnegative_integer(
        available_growth_units,
        "available_growth_units",
    )
    coins = _require_nonnegative_integer(available_coins, "available_coins")
    current = snapshot.rank_for(request.species_id)
    requested_index = MASTERY_RANK_ORDER.index(request.rank_id)
    current_index = -1 if current is None else MASTERY_RANK_ORDER.index(current)
    next_rank = next_mastery_rank_id(snapshot, request.species_id)
    if requested_index <= current_index:
        return _mastery_quote(
            request,
            disposition=ProgressionDisposition.ALREADY_COMPLETE,
            can_apply=False,
            message="This species already has that Mastery rank.",
            next_rank_id=next_rank,
        )
    if requested_index != current_index + 1:
        return _mastery_quote(
            request,
            disposition=ProgressionDisposition.INVALID_ORDER,
            can_apply=False,
            message="Cultivation Mastery ranks must be purchased in order.",
            next_rank_id=next_rank,
        )
    growth_cost = MASTERY_GROWTH_COST_UNITS[request.rank_id]
    if growth < growth_cost:
        return _mastery_quote(
            request,
            disposition=ProgressionDisposition.INSUFFICIENT_GROWTH,
            can_apply=False,
            message="Not enough stored Growth for this Mastery rank.",
            next_rank_id=next_rank,
        )
    coin_cost = MASTERY_RANK_BY_ID[request.rank_id].coin_cost
    if coins < coin_cost:
        return _mastery_quote(
            request,
            disposition=ProgressionDisposition.INSUFFICIENT_COINS,
            can_apply=False,
            message="Not enough Garden Coins for this Mastery rank.",
            next_rank_id=next_rank,
        )
    return _mastery_quote(
        request,
        disposition=ProgressionDisposition.APPROVED,
        can_apply=True,
        message="Cultivation Mastery rank can be purchased.",
        next_rank_id=next_rank,
        spend=True,
    )


def project_mastery_request(
    snapshot: MasterySnapshot,
    request: MasteryRequest,
    *,
    available_growth_units: int,
    available_coins: int,
) -> MasteryOutcome:
    """Return the deterministic post-purchase Mastery snapshot and spends."""

    quote = quote_mastery_request(
        snapshot,
        request,
        available_growth_units=available_growth_units,
        available_coins=available_coins,
    )
    if not quote.can_apply:
        return MasteryOutcome(
            request.request_id,
            request.fingerprint,
            request.species_id,
            request.rank_id,
            quote.disposition,
            False,
            0,
            0,
            snapshot,
            quote.message,
        )
    projected_map = dict(snapshot.highest_rank_by_species)
    projected_map[request.species_id] = request.rank_id
    projected = mastery_snapshot(projected_map)
    return MasteryOutcome(
        request.request_id,
        request.fingerprint,
        request.species_id,
        request.rank_id,
        ProgressionDisposition.APPLIED,
        True,
        quote.growth_spend_units,
        quote.coin_spend,
        projected,
        quote.message,
    )


class GrowthTargetType(StableStringEnum):
    LANDMARK = "landmark"
    MASTERY = "mastery"
    LEGACY = "legacy"


class GrowthProjectAction(StableStringEnum):
    ACTIVATE = "activate"
    CONTRIBUTE = "contribute"
    CLAIM = "claim"


class ContributionMode(StableStringEnum):
    NONE = "none"
    SPECIFIED = "specified"
    NEXT_THRESHOLD = "next_threshold"
    MAXIMUM = "maximum"


@dataclass(frozen=True)
class GrowthTargetRef:
    target_type: GrowthTargetType
    target_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_type, GrowthTargetType):
            raise TypeError("target_type must be a GrowthTargetType")
        valid = (
            self.target_id == "garden_landmark"
            if self.target_type is GrowthTargetType.LANDMARK
            else self.target_id in ACTIVE_SPECIES
            if self.target_type is GrowthTargetType.MASTERY
            else self.target_id == "garden_legacy"
        )
        if not valid:
            raise ValueError("target_id is not valid for that Growth target type")

    def to_dict(self) -> dict[str, str]:
        return {
            "target_type": self.target_type.value,
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class ProjectGrowthAllocation:
    target_type: GrowthTargetType
    target_id: str
    units: int

    def __post_init__(self) -> None:
        GrowthTargetRef(self.target_type, self.target_id)
        _require_nonnegative_integer(self.units, "units")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "units": self.units,
        }


@dataclass(frozen=True)
class ProjectTierProjection:
    tier_id: str
    display_name: str
    artwork_id: str
    effect_description: str
    acquisition_route: str
    cumulative_growth_threshold_units: int
    remaining_growth_units: int
    coin_cost: int
    funded: bool
    claimed: bool
    claimable: bool
    can_claim_now: bool
    state: str
    allowed_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier_id": self.tier_id,
            "display_name": self.display_name,
            "artwork_id": self.artwork_id,
            "effect_description": self.effect_description,
            "acquisition_route": self.acquisition_route,
            "cumulative_growth_threshold_units": (
                self.cumulative_growth_threshold_units
            ),
            "remaining_growth_units": self.remaining_growth_units,
            "coin_cost": self.coin_cost,
            "funded": self.funded,
            "claimed": self.claimed,
            "claimable": self.claimable,
            "can_claim_now": self.can_claim_now,
            "state": self.state,
            "allowed_actions": list(self.allowed_actions),
        }


@dataclass(frozen=True)
class ProjectTrackProjection:
    target: GrowthTargetRef
    display_name: str
    artwork_id: str
    effect_description: str
    acquisition_route: str
    growth_units_funded: int
    maximum_growth_units: Optional[int]
    remaining_capacity_units: Optional[int]
    highest_claimed_id: str
    tiers: tuple[ProjectTierProjection, ...]
    level: int = 0
    level_progress_units: int = 0
    allowed_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "display_name": self.display_name,
            "artwork_id": self.artwork_id,
            "effect_description": self.effect_description,
            "acquisition_route": self.acquisition_route,
            "growth_units_funded": self.growth_units_funded,
            "maximum_growth_units": self.maximum_growth_units,
            "remaining_capacity_units": self.remaining_capacity_units,
            "highest_claimed_id": self.highest_claimed_id,
            "tiers": [tier.to_dict() for tier in self.tiers],
            "level": self.level,
            "level_progress_units": self.level_progress_units,
            "allowed_actions": list(self.allowed_actions),
        }


@dataclass(frozen=True)
class GrowthTargetChoice:
    target: GrowthTargetRef
    display_name: str
    artwork_id: str
    available: bool
    blocking_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "display_name": self.display_name,
            "artwork_id": self.artwork_id,
            "available": self.available,
            "blocking_reason": self.blocking_reason,
        }


@dataclass(frozen=True)
class GrowthProjectsSnapshot:
    state_revision: int
    unlocked: bool
    prompt_required: bool
    active_target: Optional[GrowthTargetRef]
    active_target_activation_identity: str
    stored_balance_units: int
    wallet_balance_coins: int
    full_bloom_species: tuple[str, ...]
    landmark_track: ProjectTrackProjection
    mastery_tracks_by_species: tuple[tuple[str, ProjectTrackProjection], ...]
    legacy_track: ProjectTrackProjection
    target_choices: tuple[GrowthTargetChoice, ...]
    coins_required_for_claimable_content: int

    def mastery_track(self, species_id: str) -> ProjectTrackProjection:
        try:
            return dict(self.mastery_tracks_by_species)[species_id]
        except KeyError as error:
            raise ValueError("species_id must be an active catalog species") from error

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_revision": self.state_revision,
            "unlocked": self.unlocked,
            "prompt_required": self.prompt_required,
            "active_target": (
                self.active_target.to_dict() if self.active_target else None
            ),
            "active_target_activation_identity": (
                self.active_target_activation_identity
            ),
            "stored_balance_units": self.stored_balance_units,
            "wallet_balance_coins": self.wallet_balance_coins,
            "full_bloom_species": list(self.full_bloom_species),
            "landmark_track": self.landmark_track.to_dict(),
            "mastery_tracks_by_species": {
                species_id: track.to_dict()
                for species_id, track in self.mastery_tracks_by_species
            },
            "legacy_track": self.legacy_track.to_dict(),
            "target_choices": [choice.to_dict() for choice in self.target_choices],
            "coins_required_for_claimable_content": (
                self.coins_required_for_claimable_content
            ),
        }


def _tier_state(*, funded: bool, claimed: bool, claimable: bool) -> str:
    if claimed:
        return "claimed"
    if claimable:
        return "claimable"
    if funded:
        return "funded_waiting_previous"
    return "funding"


def build_growth_projects_snapshot(
    *,
    state_revision: int,
    stored_balance_units: int,
    wallet_balance_coins: int,
    full_bloom_species: tuple[str, ...] | list[str] = (),
    active_target: Optional[GrowthTargetRef] = None,
    active_target_activation_identity: str = "",
    landmark_growth_units_funded: int = 0,
    landmark_highest_claimed_tier: int = 0,
    mastery_growth_units_funded_by_species: Optional[Mapping[str, int]] = None,
    mastery_highest_claimed_rank_by_species: Optional[Mapping[str, str]] = None,
    garden_legacy_level: int = 0,
    garden_legacy_progress_units: int = 0,
) -> GrowthProjectsSnapshot:
    """Build one immutable renderer-neutral endgame projection."""

    revision = _require_nonnegative_integer(state_revision, "state_revision")
    stored = _require_nonnegative_integer(
        stored_balance_units, "stored_balance_units"
    )
    wallet = _require_nonnegative_integer(
        wallet_balance_coins, "wallet_balance_coins"
    )
    bloom = tuple(
        species_id for species_id in CURRENT_CATALOG_SPECIES_ORDER
        if species_id in set(full_bloom_species)
    )
    if len(bloom) != len(set(full_bloom_species)):
        raise ValueError("full_bloom_species must contain canonical unique IDs")
    if set(full_bloom_species).difference(ACTIVE_SPECIES):
        raise ValueError("full_bloom_species contains an unsupported species")
    unlocked = bool(bloom)
    landmark_funded = _require_nonnegative_integer(
        landmark_growth_units_funded, "landmark_growth_units_funded"
    )
    if landmark_funded > LANDMARK_MAX_GROWTH_UNITS:
        raise ValueError("Landmark Growth exceeds the cumulative maximum")
    claimed_tier = _require_nonnegative_integer(
        landmark_highest_claimed_tier, "landmark_highest_claimed_tier"
    )
    if claimed_tier > len(LANDMARK_ORDER):
        raise ValueError("Landmark claimed tier exceeds the catalog")
    if claimed_tier:
        floor = LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
            LANDMARK_ORDER[claimed_tier - 1]
        ]
        if landmark_funded < floor:
            raise ValueError("claimed Landmark tier lacks cumulative Growth")

    landmark_rows: list[ProjectTierProjection] = []
    next_claim_index = claimed_tier
    for index, definition in enumerate(LANDMARKS):
        item_id = definition.landmark_id.value
        threshold = LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[item_id]
        funded = landmark_funded >= threshold
        claimed = index < claimed_tier
        claimable = funded and index == next_claim_index
        landmark_rows.append(ProjectTierProjection(
            tier_id=item_id,
            display_name=definition.display_name,
            artwork_id=definition.asset_id,
            effect_description=definition.effect_description,
            acquisition_route=definition.how_to_acquire,
            cumulative_growth_threshold_units=threshold,
            remaining_growth_units=max(0, threshold - landmark_funded),
            coin_cost=definition.coin_cost,
            funded=funded,
            claimed=claimed,
            claimable=claimable,
            can_claim_now=claimable and wallet >= definition.coin_cost,
            state=_tier_state(
                funded=funded, claimed=claimed, claimable=claimable
            ),
            allowed_actions=("claim",) if claimable else (),
        ))
    landmark_target = GrowthTargetRef(
        GrowthTargetType.LANDMARK, "garden_landmark"
    )
    landmark_track = ProjectTrackProjection(
        target=landmark_target,
        display_name="Garden Landmark",
        artwork_id=(LANDMARKS[-1].asset_id),
        effect_description="A cumulative cosmetic construction track.",
        acquisition_route="Fund with Growth, then claim each visual tier with Garden Coins.",
        growth_units_funded=landmark_funded,
        maximum_growth_units=LANDMARK_MAX_GROWTH_UNITS,
        remaining_capacity_units=LANDMARK_MAX_GROWTH_UNITS - landmark_funded,
        highest_claimed_id=(
            LANDMARK_ORDER[claimed_tier - 1] if claimed_tier else ""
        ),
        tiers=tuple(landmark_rows),
        allowed_actions=(
            ("contribute",)
            if active_target == landmark_target else ("activate",)
        ) if unlocked and landmark_funded < LANDMARK_MAX_GROWTH_UNITS else (),
    )

    raw_mastery_funding = dict(mastery_growth_units_funded_by_species or {})
    raw_mastery_claims = dict(mastery_highest_claimed_rank_by_species or {})
    unknown = set(raw_mastery_funding).union(raw_mastery_claims).difference(
        ACTIVE_SPECIES
    )
    if unknown:
        raise ValueError("Mastery mappings contain an unsupported species")
    mastery_tracks: list[tuple[str, ProjectTrackProjection]] = []
    for species_id in CURRENT_CATALOG_SPECIES_ORDER:
        funded_units = _require_nonnegative_integer(
            raw_mastery_funding.get(species_id, 0),
            f"mastery Growth for {species_id}",
        )
        if funded_units > MASTERY_MAX_GROWTH_UNITS:
            raise ValueError("Mastery Growth exceeds the per-species maximum")
        claimed_rank = str(raw_mastery_claims.get(species_id, "") or "")
        if claimed_rank and claimed_rank not in MASTERY_RANK_ORDER:
            raise ValueError("Mastery claim mapping contains an unsupported rank")
        claimed_index = (
            MASTERY_RANK_ORDER.index(claimed_rank) + 1 if claimed_rank else 0
        )
        if claimed_rank and funded_units < (
            MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[claimed_rank]
        ):
            raise ValueError("claimed Mastery rank lacks cumulative Growth")
        rows: list[ProjectTierProjection] = []
        for index, definition in enumerate(MASTERY_RANKS):
            rank_id = definition.rank_id.value
            threshold = MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[rank_id]
            funded = funded_units >= threshold
            claimed = index < claimed_index
            claimable = funded and index == claimed_index
            rows.append(ProjectTierProjection(
                tier_id=rank_id,
                display_name=definition.display_name,
                artwork_id=definition.asset_id,
                effect_description=definition.effect_description,
                acquisition_route=definition.how_to_acquire,
                cumulative_growth_threshold_units=threshold,
                remaining_growth_units=max(0, threshold - funded_units),
                coin_cost=definition.coin_cost,
                funded=funded,
                claimed=claimed,
                claimable=claimable,
                can_claim_now=claimable and wallet >= definition.coin_cost,
                state=_tier_state(
                    funded=funded, claimed=claimed, claimable=claimable
                ),
                allowed_actions=("claim",) if claimable else (),
            ))
        species_name = SPECIES_BY_ID[species_id].display_name
        mastery_target = GrowthTargetRef(GrowthTargetType.MASTERY, species_id)
        mastery_tracks.append((species_id, ProjectTrackProjection(
            target=mastery_target,
            display_name=f"{species_name} Cultivation Mastery",
            artwork_id=(
                MASTERY_RANK_BY_ID[claimed_rank].asset_id
                if claimed_rank else MASTERY_RANKS[0].asset_id
            ),
            effect_description="Cosmetic recognition for a Full Bloom species.",
            acquisition_route="Fund with Growth, then claim ranks with Garden Coins.",
            growth_units_funded=funded_units,
            maximum_growth_units=MASTERY_MAX_GROWTH_UNITS,
            remaining_capacity_units=MASTERY_MAX_GROWTH_UNITS - funded_units,
            highest_claimed_id=claimed_rank,
            tiers=tuple(rows),
            allowed_actions=(
                ("contribute",)
                if active_target == mastery_target else ("activate",)
            ) if species_id in bloom and funded_units < MASTERY_MAX_GROWTH_UNITS
            else (),
        )))

    finite_funded = (
        landmark_funded == LANDMARK_MAX_GROWTH_UNITS
        and all(
            track.growth_units_funded == MASTERY_MAX_GROWTH_UNITS
            for _species_id, track in mastery_tracks
        )
    )
    legacy_level = _require_nonnegative_integer(
        garden_legacy_level, "garden_legacy_level"
    )
    legacy_progress = _require_nonnegative_integer(
        garden_legacy_progress_units, "garden_legacy_progress_units"
    )
    if legacy_progress >= GARDEN_LEGACY_LEVEL_COST_UNITS:
        raise ValueError("Garden Legacy progress must be below one level cost")
    legacy_target = GrowthTargetRef(
        GrowthTargetType.LEGACY, GARDEN_LEGACY.legacy_id
    )
    legacy_track = ProjectTrackProjection(
        target=legacy_target,
        display_name=GARDEN_LEGACY.display_name,
        artwork_id=GARDEN_LEGACY.asset_id,
        effect_description=GARDEN_LEGACY.effect_description,
        acquisition_route=GARDEN_LEGACY.how_to_acquire,
        growth_units_funded=(
            legacy_level * GARDEN_LEGACY_LEVEL_COST_UNITS + legacy_progress
        ),
        maximum_growth_units=None,
        remaining_capacity_units=None,
        highest_claimed_id=str(legacy_level),
        tiers=(),
        level=legacy_level,
        level_progress_units=legacy_progress,
        allowed_actions=(
            ("contribute",)
            if active_target == legacy_target else ("activate",)
        ) if finite_funded else (),
    )

    choices: list[GrowthTargetChoice] = [GrowthTargetChoice(
        landmark_track.target,
        landmark_track.display_name,
        landmark_track.artwork_id,
        unlocked and landmark_funded < LANDMARK_MAX_GROWTH_UNITS,
        "" if unlocked and landmark_funded < LANDMARK_MAX_GROWTH_UNITS else (
            "Landmark track is fully funded."
            if unlocked else "Reach Full Bloom first."
        ),
    )]
    for species_id, track in mastery_tracks:
        available = (
            species_id in bloom
            and track.growth_units_funded < MASTERY_MAX_GROWTH_UNITS
        )
        choices.append(GrowthTargetChoice(
            track.target,
            track.display_name,
            track.artwork_id,
            available,
            "" if available else (
                "This species must reach Full Bloom first."
                if species_id not in bloom else "This Mastery track is fully funded."
            ),
        ))
    choices.append(GrowthTargetChoice(
        legacy_track.target,
        legacy_track.display_name,
        legacy_track.artwork_id,
        finite_funded,
        "" if finite_funded else "Fund all Landmark and Mastery tracks first.",
    ))
    if active_target is not None:
        matching = next(
            (choice for choice in choices if choice.target == active_target), None
        )
        if matching is None:
            raise ValueError("active target is not in the target catalog")
    claimable_cost = sum(
        tier.coin_cost for tier in landmark_rows
        if tier.funded and not tier.claimed
    ) + sum(
        tier.coin_cost
        for _species_id, track in mastery_tracks
        for tier in track.tiers
        if tier.funded and not tier.claimed
    )
    prompt_required = unlocked and active_target is None and any(
        choice.available for choice in choices
    )
    return GrowthProjectsSnapshot(
        state_revision=revision,
        unlocked=unlocked,
        prompt_required=prompt_required,
        active_target=active_target,
        active_target_activation_identity=(
            str(active_target_activation_identity or "") if active_target else ""
        ),
        stored_balance_units=stored,
        wallet_balance_coins=wallet,
        full_bloom_species=bloom,
        landmark_track=landmark_track,
        mastery_tracks_by_species=tuple(mastery_tracks),
        legacy_track=legacy_track,
        target_choices=tuple(choices),
        coins_required_for_claimable_content=claimable_cost,
    )


@dataclass(frozen=True)
class GrowthProjectRequest:
    request_id: str
    expected_state_revision: int
    action: GrowthProjectAction
    target: GrowthTargetRef
    contribution_mode: ContributionMode = ContributionMode.NONE
    specified_growth_units: int = 0
    claim_id: str = ""

    def __post_init__(self) -> None:
        canonical_request_id(self.request_id)
        _require_nonnegative_integer(
            self.expected_state_revision, "expected_state_revision"
        )
        if not isinstance(self.action, GrowthProjectAction):
            raise TypeError("action must be a GrowthProjectAction")
        if not isinstance(self.target, GrowthTargetRef):
            raise TypeError("target must be a GrowthTargetRef")
        if not isinstance(self.contribution_mode, ContributionMode):
            raise TypeError("contribution_mode must be a ContributionMode")
        _require_nonnegative_integer(
            self.specified_growth_units, "specified_growth_units"
        )
        if self.action is GrowthProjectAction.CONTRIBUTE:
            if self.contribution_mode is ContributionMode.NONE:
                raise ValueError("contributions require a contribution mode")
            if (
                self.contribution_mode is ContributionMode.SPECIFIED
                and self.specified_growth_units <= 0
            ):
                raise ValueError("specified contributions must be positive")
            if (
                self.contribution_mode is not ContributionMode.SPECIFIED
                and self.specified_growth_units
            ):
                raise ValueError("only specified contributions include an amount")
            if self.claim_id:
                raise ValueError("contributions cannot include a claim ID")
        elif self.action is GrowthProjectAction.CLAIM:
            if self.contribution_mode is not ContributionMode.NONE:
                raise ValueError("claims cannot include a contribution mode")
            if not self.claim_id:
                raise ValueError("claims require a claim ID")
            if self.target.target_type is GrowthTargetType.LEGACY:
                raise ValueError("Garden Legacy has no claim operation")
        elif (
            self.contribution_mode is not ContributionMode.NONE
            or self.specified_growth_units
            or self.claim_id
        ):
            raise ValueError("activation requests contain only a target")

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint("growth_project", self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "expected_state_revision": self.expected_state_revision,
            "action": self.action.value,
            "target": self.target.to_dict(),
            "contribution_mode": self.contribution_mode.value,
            "specified_growth_units": self.specified_growth_units,
            "claim_id": self.claim_id,
        }


@dataclass(frozen=True)
class GrowthProjectQuote:
    request_id: str
    request_fingerprint: str
    quote_fingerprint: str
    expected_state_revision: int
    action: GrowthProjectAction
    target: GrowthTargetRef
    disposition: ProgressionDisposition
    can_apply: bool
    blocking_reason: str
    stored_balance_before_units: int
    stored_balance_after_units: int
    project_funded_before_units: int
    project_funded_after_units: int
    accepted_growth_units: int
    remaining_capacity_units: Optional[int]
    crossed_threshold_ids: tuple[str, ...]
    claim_id: str
    coin_cost: int
    wallet_balance_before_coins: int
    wallet_balance_after_coins: int
    catalog_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "quote_fingerprint": self.quote_fingerprint,
            "expected_state_revision": self.expected_state_revision,
            "action": self.action.value,
            "target": self.target.to_dict(),
            "disposition": self.disposition.value,
            "can_apply": self.can_apply,
            "blocking_reason": self.blocking_reason,
            "stored_balance_before_units": self.stored_balance_before_units,
            "stored_balance_after_units": self.stored_balance_after_units,
            "project_funded_before_units": self.project_funded_before_units,
            "project_funded_after_units": self.project_funded_after_units,
            "accepted_growth_units": self.accepted_growth_units,
            "remaining_capacity_units": self.remaining_capacity_units,
            "crossed_threshold_ids": list(self.crossed_threshold_ids),
            "claim_id": self.claim_id,
            "coin_cost": self.coin_cost,
            "wallet_balance_before_coins": self.wallet_balance_before_coins,
            "wallet_balance_after_coins": self.wallet_balance_after_coins,
            "catalog_digest": self.catalog_digest,
        }


@dataclass(frozen=True)
class GrowthProjectConfirmation:
    request_id: str
    request_fingerprint: str
    quote_fingerprint: str

    @classmethod
    def from_quote(cls, quote: GrowthProjectQuote) -> "GrowthProjectConfirmation":
        if not isinstance(quote, GrowthProjectQuote):
            raise TypeError("quote must be a GrowthProjectQuote")
        return cls(
            quote.request_id,
            quote.request_fingerprint,
            quote.quote_fingerprint,
        )


@dataclass(frozen=True)
class GrowthProjectOutcome:
    request_id: str
    request_fingerprint: str
    quote_fingerprint: str
    disposition: ProgressionDisposition
    applied: bool
    stored_balance_delta_units: int
    coins_spent: int
    allocation: Optional[ProjectGrowthAllocation]
    snapshot: GrowthProjectsSnapshot
    message: str
    ledger_identity: str = ""
    state_revision_before: int = 0
    state_revision_after: int = 0
    catalog_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "quote_fingerprint": self.quote_fingerprint,
            "disposition": self.disposition.value,
            "applied": self.applied,
            "stored_balance_delta_units": self.stored_balance_delta_units,
            "coins_spent": self.coins_spent,
            "allocation": self.allocation.to_dict() if self.allocation else None,
            "snapshot": self.snapshot.to_dict(),
            "message": self.message,
            "ledger_identity": self.ledger_identity,
            "state_revision_before": self.state_revision_before,
            "state_revision_after": self.state_revision_after,
            "catalog_digest": self.catalog_digest,
        }


def _track_for_target(
    snapshot: GrowthProjectsSnapshot,
    target: GrowthTargetRef,
) -> ProjectTrackProjection:
    if target.target_type is GrowthTargetType.LANDMARK:
        return snapshot.landmark_track
    if target.target_type is GrowthTargetType.MASTERY:
        return snapshot.mastery_track(target.target_id)
    return snapshot.legacy_track


def _quote_digest(
    snapshot: GrowthProjectsSnapshot,
    request: GrowthProjectRequest,
    payload: Mapping[str, Any],
) -> str:
    return _stable_fingerprint("growth_project_quote", {
        "request_fingerprint": request.fingerprint,
        "snapshot": snapshot.to_dict(),
        **payload,
    })


def quote_growth_project_request(
    snapshot: GrowthProjectsSnapshot,
    request: GrowthProjectRequest,
) -> GrowthProjectQuote:
    """Quote activation, contribution, or claim against one fresh snapshot."""

    if not isinstance(snapshot, GrowthProjectsSnapshot):
        raise TypeError("snapshot must be a GrowthProjectsSnapshot")
    if not isinstance(request, GrowthProjectRequest):
        raise TypeError("request must be a GrowthProjectRequest")
    track = _track_for_target(snapshot, request.target)
    before_funded = track.growth_units_funded
    stored_after = snapshot.stored_balance_units
    funded_after = before_funded
    accepted = 0
    crossed: tuple[str, ...] = ()
    claim_cost = 0
    can_apply = True
    disposition = ProgressionDisposition.APPROVED
    reason = ""

    if request.expected_state_revision != snapshot.state_revision:
        can_apply = False
        disposition = ProgressionDisposition.NO_CHANGE
        reason = "The Garden changed. Refresh this quote before continuing."
    elif request.action is GrowthProjectAction.ACTIVATE:
        choice = next(
            item for item in snapshot.target_choices if item.target == request.target
        )
        if not choice.available:
            can_apply = False
            disposition = ProgressionDisposition.NOT_READY
            reason = choice.blocking_reason
        elif snapshot.active_target == request.target:
            can_apply = False
            disposition = ProgressionDisposition.ALREADY_SELECTED
            reason = "This Growth project is already active."
    elif request.action is GrowthProjectAction.CONTRIBUTE:
        if snapshot.active_target != request.target:
            can_apply = False
            disposition = ProgressionDisposition.INVALID_ORDER
            reason = "Choose this Growth project before contributing."
        elif track.remaining_capacity_units == 0:
            can_apply = False
            disposition = ProgressionDisposition.NO_CHANGE
            reason = "This Growth project is fully funded."
        else:
            if request.contribution_mode is ContributionMode.SPECIFIED:
                requested = request.specified_growth_units
            elif request.contribution_mode is ContributionMode.MAXIMUM:
                requested = snapshot.stored_balance_units
            else:
                thresholds = [
                    tier.cumulative_growth_threshold_units
                    for tier in track.tiers
                    if tier.cumulative_growth_threshold_units > before_funded
                ]
                requested = (
                    min(thresholds) - before_funded
                    if thresholds else
                    GARDEN_LEGACY_LEVEL_COST_UNITS - track.level_progress_units
                )
            if track.remaining_capacity_units is not None:
                requested = min(requested, track.remaining_capacity_units)
            if requested <= 0:
                can_apply = False
                disposition = ProgressionDisposition.NO_CHANGE
                reason = "There is no Growth to contribute."
            elif snapshot.stored_balance_units < requested:
                can_apply = False
                disposition = ProgressionDisposition.INSUFFICIENT_GROWTH
                reason = "Not enough Stored Growth for this contribution."
            else:
                accepted = requested
                stored_after -= accepted
                funded_after += accepted
                crossed = tuple(
                    tier.tier_id for tier in track.tiers
                    if (
                        before_funded < tier.cumulative_growth_threshold_units
                        <= funded_after
                    )
                )
    else:
        tier = next(
            (item for item in track.tiers if item.tier_id == request.claim_id),
            None,
        )
        if tier is None:
            can_apply = False
            disposition = ProgressionDisposition.INVALID_ORDER
            reason = "That claim does not belong to this Growth project."
        else:
            # The quote always exposes the canonical claim price, including
            # when the wallet is short or an earlier tier still blocks the
            # action. Renderers must never infer it from catalog ordering.
            claim_cost = tier.coin_cost
        if tier is not None and tier.claimed:
            can_apply = False
            disposition = ProgressionDisposition.ALREADY_COMPLETE
            reason = "This tier is already claimed."
        elif tier is not None and not tier.claimable:
            can_apply = False
            disposition = ProgressionDisposition.NOT_READY
            reason = "Fund and claim earlier tiers first."
        elif tier is not None and not tier.can_claim_now:
            can_apply = False
            disposition = ProgressionDisposition.INSUFFICIENT_COINS
            reason = "Not enough Garden Coins to claim this tier."

    payload = {
        "can_apply": can_apply,
        "stored_after": stored_after,
        "funded_after": funded_after,
        "accepted": accepted,
        "claim_cost": claim_cost,
        "crossed": list(crossed),
        "disposition": disposition.value,
        "catalog_digest": economy_catalog_digest(),
    }
    remaining = track.remaining_capacity_units
    if remaining is not None:
        remaining = max(0, remaining - accepted)
    return GrowthProjectQuote(
        request_id=request.request_id,
        request_fingerprint=request.fingerprint,
        quote_fingerprint=_quote_digest(snapshot, request, payload),
        expected_state_revision=request.expected_state_revision,
        action=request.action,
        target=request.target,
        disposition=disposition,
        can_apply=can_apply,
        blocking_reason=reason,
        stored_balance_before_units=snapshot.stored_balance_units,
        stored_balance_after_units=stored_after,
        project_funded_before_units=before_funded,
        project_funded_after_units=funded_after,
        accepted_growth_units=accepted,
        remaining_capacity_units=remaining,
        crossed_threshold_ids=crossed,
        claim_id=request.claim_id,
        coin_cost=claim_cost,
        wallet_balance_before_coins=snapshot.wallet_balance_coins,
        wallet_balance_after_coins=(
            snapshot.wallet_balance_coins - claim_cost
            if can_apply else snapshot.wallet_balance_coins
        ),
        catalog_digest=economy_catalog_digest(),
    )


def project_growth_project_request(
    snapshot: GrowthProjectsSnapshot,
    request: GrowthProjectRequest,
) -> GrowthProjectOutcome:
    """Return an exact deterministic outcome; persistence remains engine-owned."""

    quote = quote_growth_project_request(snapshot, request)
    if not quote.can_apply:
        return GrowthProjectOutcome(
            request.request_id,
            request.fingerprint,
            quote.quote_fingerprint,
            quote.disposition,
            False,
            0,
            0,
            None,
            snapshot,
            quote.blocking_reason,
            ledger_identity=f"growth-project:{request.request_id}",
            state_revision_before=snapshot.state_revision,
            state_revision_after=snapshot.state_revision,
            catalog_digest=quote.catalog_digest,
        )

    active_target = snapshot.active_target
    activation_identity = snapshot.active_target_activation_identity
    landmark_funded = snapshot.landmark_track.growth_units_funded
    landmark_claimed = sum(
        1 for tier in snapshot.landmark_track.tiers if tier.claimed
    )
    mastery_funding = {
        species_id: track.growth_units_funded
        for species_id, track in snapshot.mastery_tracks_by_species
    }
    mastery_claims = {
        species_id: track.highest_claimed_id
        for species_id, track in snapshot.mastery_tracks_by_species
        if track.highest_claimed_id
    }
    legacy_level = snapshot.legacy_track.level
    legacy_progress = snapshot.legacy_track.level_progress_units
    allocation: Optional[ProjectGrowthAllocation] = None

    if request.action is GrowthProjectAction.ACTIVATE:
        active_target = request.target
        activation_identity = request.request_id
    elif request.action is GrowthProjectAction.CONTRIBUTE:
        allocation = ProjectGrowthAllocation(
            request.target.target_type,
            request.target.target_id,
            quote.accepted_growth_units,
        )
        if request.target.target_type is GrowthTargetType.LANDMARK:
            landmark_funded = quote.project_funded_after_units
        elif request.target.target_type is GrowthTargetType.MASTERY:
            mastery_funding[request.target.target_id] = (
                quote.project_funded_after_units
            )
        else:
            total = legacy_progress + quote.accepted_growth_units
            gained, legacy_progress = divmod(
                total, GARDEN_LEGACY_LEVEL_COST_UNITS
            )
            legacy_level += gained
    elif request.target.target_type is GrowthTargetType.LANDMARK:
        landmark_claimed += 1
    else:
        mastery_claims[request.target.target_id] = request.claim_id

    projected = build_growth_projects_snapshot(
        state_revision=snapshot.state_revision + 1,
        stored_balance_units=quote.stored_balance_after_units,
        wallet_balance_coins=quote.wallet_balance_after_coins,
        full_bloom_species=snapshot.full_bloom_species,
        active_target=active_target,
        active_target_activation_identity=activation_identity,
        landmark_growth_units_funded=landmark_funded,
        landmark_highest_claimed_tier=landmark_claimed,
        mastery_growth_units_funded_by_species=mastery_funding,
        mastery_highest_claimed_rank_by_species=mastery_claims,
        garden_legacy_level=legacy_level,
        garden_legacy_progress_units=legacy_progress,
    )
    return GrowthProjectOutcome(
        request.request_id,
        request.fingerprint,
        quote.quote_fingerprint,
        ProgressionDisposition.APPLIED,
        True,
        quote.stored_balance_after_units - quote.stored_balance_before_units,
        quote.coin_cost,
        allocation,
        projected,
        "Growth project change applied.",
        ledger_identity=f"growth-project:{request.request_id}",
        state_revision_before=snapshot.state_revision,
        state_revision_after=projected.state_revision,
        catalog_digest=quote.catalog_digest,
    )


def growth_target_ref_from_dict(value: Mapping[str, Any]) -> GrowthTargetRef:
    if not isinstance(value, Mapping):
        raise TypeError("Growth target payload must be a mapping")
    return GrowthTargetRef(
        GrowthTargetType(str(value.get("target_type", ""))),
        str(value.get("target_id", "")),
    )


def growth_project_request_from_dict(
    value: Mapping[str, Any],
) -> GrowthProjectRequest:
    if not isinstance(value, Mapping):
        raise TypeError("Growth project request payload must be a mapping")
    return GrowthProjectRequest(
        request_id=str(value.get("request_id", "")),
        expected_state_revision=_require_nonnegative_integer(
            value.get("expected_state_revision"), "expected_state_revision"
        ),
        action=GrowthProjectAction(str(value.get("action", ""))),
        target=growth_target_ref_from_dict(value.get("target", {})),
        contribution_mode=ContributionMode(
            str(value.get("contribution_mode", "none"))
        ),
        specified_growth_units=_require_nonnegative_integer(
            value.get("specified_growth_units", 0), "specified_growth_units"
        ),
        claim_id=str(value.get("claim_id", "")),
    )


def growth_projects_snapshot_from_dict(
    value: Mapping[str, Any],
) -> GrowthProjectsSnapshot:
    """Restore and revalidate a snapshot using current catalog authority."""

    if not isinstance(value, Mapping):
        raise TypeError("Growth projects snapshot payload must be a mapping")
    active_raw = value.get("active_target")
    active = (
        growth_target_ref_from_dict(active_raw)
        if isinstance(active_raw, Mapping) else None
    )
    landmark = value.get("landmark_track", {})
    if not isinstance(landmark, Mapping):
        raise ValueError("landmark_track must be a mapping")
    landmark_tiers = landmark.get("tiers", [])
    if not isinstance(landmark_tiers, list):
        raise ValueError("Landmark tiers must be a list")
    landmark_claimed = sum(
        1 for tier in landmark_tiers
        if isinstance(tier, Mapping) and tier.get("claimed") is True
    )
    raw_mastery = value.get("mastery_tracks_by_species", {})
    if not isinstance(raw_mastery, Mapping):
        raise ValueError("mastery_tracks_by_species must be a mapping")
    mastery_funding: dict[str, int] = {}
    mastery_claims: dict[str, str] = {}
    for species_id, raw_track in raw_mastery.items():
        if not isinstance(raw_track, Mapping):
            raise ValueError("Mastery track must be a mapping")
        mastery_funding[str(species_id)] = _require_nonnegative_integer(
            raw_track.get("growth_units_funded", 0),
            f"mastery Growth for {species_id}",
        )
        claimed = str(raw_track.get("highest_claimed_id", "") or "")
        if claimed:
            mastery_claims[str(species_id)] = claimed
    legacy = value.get("legacy_track", {})
    if not isinstance(legacy, Mapping):
        raise ValueError("legacy_track must be a mapping")
    bloom_raw = value.get("full_bloom_species", [])
    if not isinstance(bloom_raw, list):
        raise ValueError("full_bloom_species must be a list")
    return build_growth_projects_snapshot(
        state_revision=_require_nonnegative_integer(
            value.get("state_revision"), "state_revision"
        ),
        stored_balance_units=_require_nonnegative_integer(
            value.get("stored_balance_units"), "stored_balance_units"
        ),
        wallet_balance_coins=_require_nonnegative_integer(
            value.get("wallet_balance_coins"), "wallet_balance_coins"
        ),
        full_bloom_species=tuple(str(item) for item in bloom_raw),
        active_target=active,
        active_target_activation_identity=str(
            value.get("active_target_activation_identity", "") or ""
        ),
        landmark_growth_units_funded=_require_nonnegative_integer(
            landmark.get("growth_units_funded", 0),
            "landmark_growth_units_funded",
        ),
        landmark_highest_claimed_tier=landmark_claimed,
        mastery_growth_units_funded_by_species=mastery_funding,
        mastery_highest_claimed_rank_by_species=mastery_claims,
        garden_legacy_level=_require_nonnegative_integer(
            legacy.get("level", 0), "garden_legacy_level"
        ),
        garden_legacy_progress_units=_require_nonnegative_integer(
            legacy.get("level_progress_units", 0),
            "garden_legacy_progress_units",
        ),
    )


def growth_project_outcome_from_dict(
    value: Mapping[str, Any],
) -> GrowthProjectOutcome:
    """Restore a permanent idempotency outcome without recalculating resources."""

    if not isinstance(value, Mapping):
        raise TypeError("Growth project outcome payload must be a mapping")
    allocation_raw = value.get("allocation")
    allocation = None
    if isinstance(allocation_raw, Mapping):
        target = growth_target_ref_from_dict(allocation_raw)
        allocation = ProjectGrowthAllocation(
            target.target_type,
            target.target_id,
            _require_nonnegative_integer(allocation_raw.get("units"), "units"),
        )
    stored_delta = value.get("stored_balance_delta_units", 0)
    if isinstance(stored_delta, bool) or not isinstance(stored_delta, int):
        raise ValueError("stored_balance_delta_units must be an integer")
    return GrowthProjectOutcome(
        request_id=canonical_request_id(str(value.get("request_id", ""))),
        request_fingerprint=str(value.get("request_fingerprint", "")),
        quote_fingerprint=str(value.get("quote_fingerprint", "")),
        disposition=ProgressionDisposition(str(value.get("disposition", ""))),
        applied=bool(value.get("applied", False)),
        stored_balance_delta_units=int(stored_delta),
        coins_spent=_require_nonnegative_integer(
            value.get("coins_spent", 0), "coins_spent"
        ),
        allocation=allocation,
        snapshot=growth_projects_snapshot_from_dict(value.get("snapshot", {})),
        message=str(value.get("message", "")),
        ledger_identity=str(value.get("ledger_identity", "") or ""),
        state_revision_before=_require_nonnegative_integer(
            value.get("state_revision_before", 0), "state_revision_before"
        ),
        state_revision_after=_require_nonnegative_integer(
            value.get("state_revision_after", 0), "state_revision_after"
        ),
        catalog_digest=str(value.get("catalog_digest", "") or ""),
    )


def request_fingerprint(
    request: LandmarkRequest | MasteryRequest | GrowthProjectRequest,
) -> str:
    if isinstance(request, (LandmarkRequest, MasteryRequest, GrowthProjectRequest)):
        return request.fingerprint
    raise TypeError(
        "request must be a LandmarkRequest, MasteryRequest, or GrowthProjectRequest"
    )


__all__ = [
    "ACTIVE_SPECIES",
    "ECONOMY_PROGRESSION_CONTRACT_VERSION",
    "GARDEN_LEGACY_LEVEL_COST_UNITS",
    "LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS",
    "LANDMARK_MAX_GROWTH_UNITS",
    "LANDMARK_BY_ID",
    "LANDMARK_GROWTH_COST_UNITS",
    "LANDMARK_ORDER",
    "MASTERY_GROWTH_COST_UNITS",
    "MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS",
    "MASTERY_MAX_GROWTH_UNITS",
    "MASTERY_RANK_BY_ID",
    "MASTERY_RANK_ORDER",
    "LandmarkAction",
    "LandmarkOutcome",
    "LandmarkProjectSnapshot",
    "LandmarkQuote",
    "LandmarkRequest",
    "MasteryOutcome",
    "MasteryQuote",
    "MasteryRequest",
    "MasterySnapshot",
    "ContributionMode",
    "GrowthProjectAction",
    "GrowthProjectConfirmation",
    "GrowthProjectOutcome",
    "GrowthProjectQuote",
    "GrowthProjectRequest",
    "GrowthProjectsSnapshot",
    "GrowthTargetChoice",
    "GrowthTargetRef",
    "GrowthTargetType",
    "ProjectGrowthAllocation",
    "ProjectTierProjection",
    "ProjectTrackProjection",
    "ProgressionDisposition",
    "canonical_request_id",
    "economy_catalog_digest",
    "build_growth_projects_snapshot",
    "growth_project_outcome_from_dict",
    "growth_project_request_from_dict",
    "growth_projects_snapshot_from_dict",
    "growth_target_ref_from_dict",
    "landmark_snapshot",
    "mastery_snapshot",
    "next_landmark_id",
    "next_mastery_rank_id",
    "project_landmark_request",
    "project_mastery_request",
    "project_growth_project_request",
    "quote_landmark_request",
    "quote_mastery_request",
    "quote_growth_project_request",
    "request_fingerprint",
    "validate_landmark_snapshot",
    "validate_mastery_snapshot",
]
