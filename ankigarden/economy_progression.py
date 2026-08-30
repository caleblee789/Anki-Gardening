"""Pure Garden Landmark and Cultivation Mastery transaction contracts.

The engine owns mutable state, persistence, and resource ledgers.  This module
accepts immutable snapshots and canonical UUID requests, then returns quotes or
projected outcomes without mutating anything.  Growth is always represented in
exact hundredth-Growth integer units.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Optional
from uuid import UUID

from .balance_catalog import (
    CURRENT_CATALOG_SPECIES_ORDER,
    GROWTH_UNITS_PER_POINT,
    LANDMARKS,
    MASTERY_RANKS,
)


ECONOMY_PROGRESSION_CONTRACT_VERSION = 1

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
            message="Not enough Coins to complete this Landmark.",
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
            message="Not enough Coins for this Mastery rank.",
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


def request_fingerprint(request: LandmarkRequest | MasteryRequest) -> str:
    if isinstance(request, (LandmarkRequest, MasteryRequest)):
        return request.fingerprint
    raise TypeError("request must be a LandmarkRequest or MasteryRequest")


__all__ = [
    "ACTIVE_SPECIES",
    "ECONOMY_PROGRESSION_CONTRACT_VERSION",
    "LANDMARK_BY_ID",
    "LANDMARK_GROWTH_COST_UNITS",
    "LANDMARK_ORDER",
    "MASTERY_GROWTH_COST_UNITS",
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
    "ProgressionDisposition",
    "canonical_request_id",
    "landmark_snapshot",
    "mastery_snapshot",
    "next_landmark_id",
    "next_mastery_rank_id",
    "project_landmark_request",
    "project_mastery_request",
    "quote_landmark_request",
    "quote_mastery_request",
    "request_fingerprint",
    "validate_landmark_snapshot",
    "validate_mastery_snapshot",
]
