"""Renderer-neutral semantic rows for committed Garden UI outcomes.

The reward and growth engines remain authoritative for every value.  These
records only carry those committed values between presenters and Qt widgets so
renderers never have to recover mechanics from learner-facing copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class EventPresentationKind(str, Enum):
    FULL_BLOOM = "full_bloom"
    DISCOVERY = "discovery"
    STAGE_CHANGE = "stage_change"
    STANDARD_FIND = "standard_find"
    EFFECT_REMAINING = "effect_remaining"


class EventPresentationUnit(str, Enum):
    GARDEN_COINS = "garden_coins"
    GROWTH = "growth"
    DISCOVERIES = "discoveries"
    STANDARD_FINDS = "standard_finds"
    CARDS = "cards"
    SECONDS = "seconds"
    ITEMS = "items"
    NONE = "none"


@dataclass(frozen=True)
class SourceQuantityContribution:
    """One ordered contribution to a consolidated inventory quantity."""

    label: str
    quantity: int
    event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        label = str(self.label or "").strip()
        quantity = max(0, int(self.quantity or 0))
        event_ids = tuple(dict.fromkeys(
            str(event_id or "").strip()
            for event_id in self.event_ids
            if str(event_id or "").strip()
        ))
        if not label:
            raise ValueError("source contribution label must not be empty")
        if quantity <= 0:
            raise ValueError("source contribution quantity must be positive")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "event_ids", event_ids)


@dataclass(frozen=True)
class EventRowPresentation:
    """One explicitly typed row backed by committed engine output."""

    kind: EventPresentationKind
    title: str
    amount: int | float | None
    unit: EventPresentationUnit
    source_label: str
    artwork_reference: str
    included_in_total: bool | None
    event_ids: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        try:
            kind = (
                self.kind
                if isinstance(self.kind, EventPresentationKind)
                else EventPresentationKind(str(self.kind))
            )
            unit = (
                self.unit
                if isinstance(self.unit, EventPresentationUnit)
                else EventPresentationUnit(str(self.unit))
            )
        except ValueError as exc:
            raise ValueError("unsupported semantic event presentation value") from exc
        title = str(self.title or "").strip()
        source_label = str(self.source_label or "").strip()
        artwork_reference = str(self.artwork_reference or "").strip()
        detail = str(self.detail or "").strip()
        event_ids = tuple(dict.fromkeys(
            str(event_id or "").strip()
            for event_id in self.event_ids
            if str(event_id or "").strip()
        ))
        amount = self.amount
        if amount is not None:
            if isinstance(amount, bool):
                raise TypeError("semantic event amount must be numeric")
            amount = float(amount) if isinstance(amount, float) else int(amount)
            if amount < 0:
                raise ValueError("semantic event amount must not be negative")
        if kind is EventPresentationKind.EFFECT_REMAINING and unit not in {
            EventPresentationUnit.CARDS,
            EventPresentationUnit.SECONDS,
        }:
            raise ValueError("effect remaining rows require card or second units")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "source_label", source_label)
        object.__setattr__(self, "artwork_reference", artwork_reference)
        object.__setattr__(self, "detail", detail)
        object.__setattr__(self, "event_ids", event_ids)
        object.__setattr__(self, "amount", amount)
        if self.included_in_total is not None:
            object.__setattr__(
                self,
                "included_in_total",
                bool(self.included_in_total),
            )

    @property
    def tone(self) -> str:
        return event_presentation_tone(self.kind)


def event_presentation_tone(kind: EventPresentationKind | str) -> str:
    """Return the shared semantic color role for an event kind."""

    try:
        normalized = (
            kind
            if isinstance(kind, EventPresentationKind)
            else EventPresentationKind(str(kind))
        )
    except ValueError:
        return "neutral"
    if normalized is EventPresentationKind.FULL_BLOOM:
        return "violet"
    if normalized in {
        EventPresentationKind.DISCOVERY,
        EventPresentationKind.STANDARD_FIND,
    }:
        return "aqua"
    if normalized is EventPresentationKind.EFFECT_REMAINING:
        return "sage"
    return "mint"


def committed_reward_event_rows(bundle: Any) -> tuple[EventRowPresentation, ...]:
    """Project typed atomic bundle items without parsing any display copy."""

    items = tuple(
        getattr(bundle, "all_items", None)
        or getattr(bundle, "items", None)
        or ()
    )
    rows: list[EventRowPresentation] = []
    for item in items:
        raw_kind = getattr(item, "kind", "")
        kind_value = str(getattr(raw_kind, "value", raw_kind) or "").replace("-", "_")
        event_id = str(getattr(item, "event_id", "") or "")
        title = str(getattr(item, "title", "") or "")
        source_label = str(getattr(item, "category_label", "") or "")
        artwork = str(
            getattr(item, "artwork_ref", "")
            or getattr(item, "art_asset", "")
            or ""
        )
        detail = str(getattr(item, "detail", "") or "")
        if kind_value == "full_bloom":
            rows.append(EventRowPresentation(
                EventPresentationKind.FULL_BLOOM,
                title,
                max(0, int(getattr(item, "garden_coins", 0) or 0)),
                EventPresentationUnit.GARDEN_COINS,
                source_label or "Full Bloom",
                artwork,
                True,
                (event_id,),
                detail,
            ))
        elif kind_value == "environment_discovery":
            rows.append(EventRowPresentation(
                EventPresentationKind.DISCOVERY,
                title,
                1,
                EventPresentationUnit.DISCOVERIES,
                source_label or "Discovery",
                artwork,
                None,
                (event_id,),
                detail,
            ))
        elif kind_value == "garden_find":
            rows.append(EventRowPresentation(
                EventPresentationKind.STANDARD_FIND,
                title,
                1,
                EventPresentationUnit.STANDARD_FINDS,
                source_label or "Standard Find",
                artwork,
                None,
                (event_id,),
                detail,
            ))
        elif kind_value == "stage_change":
            rows.append(EventRowPresentation(
                EventPresentationKind.STAGE_CHANGE,
                title,
                max(0, int(getattr(item, "garden_coins", 0) or 0)),
                (
                    EventPresentationUnit.GARDEN_COINS
                    if int(getattr(item, "garden_coins", 0) or 0) > 0
                    else EventPresentationUnit.NONE
                ),
                source_label or "Stage change",
                artwork,
                True if int(getattr(item, "garden_coins", 0) or 0) > 0 else None,
                (event_id,),
                detail,
            ))
    return tuple(rows)


def event_amount_total(
    rows: Iterable[EventRowPresentation],
    *,
    kind: EventPresentationKind,
    unit: EventPresentationUnit,
) -> int | float:
    """Aggregate matching committed rows for a compact presentation."""

    return sum(
        row.amount or 0
        for row in rows
        if row.kind is kind and row.unit is unit
    )


__all__ = [
    "EventPresentationKind",
    "EventPresentationUnit",
    "EventRowPresentation",
    "SourceQuantityContribution",
    "committed_reward_event_rows",
    "event_amount_total",
    "event_presentation_tone",
]
