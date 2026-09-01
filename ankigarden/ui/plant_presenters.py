"""Pure, shared presentation projections for plant-specific Garden surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any


FERTILIZER_CARD_DESCRIPTION = (
    "Fertilizer adds Growth per card for a fixed number of cards."
)


def _label(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title()


@dataclass(frozen=True)
class FertilizerQueueItem:
    """One renderer-neutral queued dose group in FIFO display order."""

    tier_id: str
    name: str
    effect: str
    cards: int
    total_cards: int
    starts_after: str = ""

    @property
    def duration(self) -> str:
        noun = "card" if self.cards == 1 else "cards"
        return f"{self.cards:,} {noun} queued"


@dataclass(frozen=True)
class FertilizerStatus:
    phase: str
    name: str
    effect: str
    duration: str
    description: str
    accessible_text: str
    seconds_remaining: int
    expires_at_epoch_seconds: int | None = None
    tier_id: str = ""
    cards_remaining: int = 0
    total_cards: int = 0
    queued_cards: int = 0
    expires_at_ms: int | None = None
    queued_items: tuple[FertilizerQueueItem, ...] = ()

    @property
    def active(self) -> bool:
        return self.phase == "active"

    @property
    def queued_next(self) -> FertilizerQueueItem | None:
        return self.queued_items[0] if self.queued_items else None


def _queued_fertilizer_items(
    engine: Any,
    queued_batches: tuple[Any, ...],
    *,
    starts_after: str = "",
) -> tuple[FertilizerQueueItem, ...]:
    """Group consecutive queue batches without changing their FIFO meaning."""

    grouped: list[FertilizerQueueItem] = []
    for batch in queued_batches:
        effect_id = str(getattr(batch, "effect_id", "") or "")
        tier = effect_id.removeprefix("fertilizer_")
        spec = getattr(engine, "FERTILIZERS", {}).get(tier)
        name = str(getattr(spec, "name", "") or _label(tier) or "Fertilizer")
        growth_units = max(
            0,
            int(getattr(batch, "growth_per_card_units", 0) or 0),
        )
        item = FertilizerQueueItem(
            tier_id=tier,
            name=name,
            effect=f"+{growth_units // 100:,} Growth per card",
            cards=max(0, int(getattr(batch, "remaining_cards", 0) or 0)),
            total_cards=max(0, int(getattr(batch, "total_cards", 0) or 0)),
        )
        if grouped and grouped[-1].tier_id == item.tier_id:
            previous = grouped[-1]
            grouped[-1] = FertilizerQueueItem(
                tier_id=previous.tier_id,
                name=previous.name,
                effect=previous.effect,
                cards=previous.cards + item.cards,
                total_cards=previous.total_cards + item.total_cards,
                starts_after=previous.starts_after,
            )
        else:
            grouped.append(item)
    ordered: list[FertilizerQueueItem] = []
    predecessor = str(starts_after or "")
    for item in grouped:
        ordered.append(FertilizerQueueItem(
            tier_id=item.tier_id,
            name=item.name,
            effect=item.effect,
            cards=item.cards,
            total_cards=item.total_cards,
            starts_after=predecessor,
        ))
        predecessor = item.name
    return tuple(ordered)


def fertilizer_status(
    engine: Any,
    plant: Any,
    *,
    now: float,
    description: str = FERTILIZER_CARD_DESCRIPTION,
) -> FertilizerStatus:
    """Project one fertilizer into stable visible and accessible fields."""

    active_batches = tuple(
        batch
        for batch in tuple(
            getattr(plant, "fertilizer_card_batches", ()) or ()
        )
        if max(0, int(getattr(batch, "remaining_cards", 0) or 0)) > 0
    )
    queued_batches = tuple(
        batch
        for batch in tuple(getattr(plant, "fertilizer_card_queue", ()) or ())
        if max(0, int(getattr(batch, "remaining_cards", 0) or 0)) > 0
    )
    if active_batches:
        first = active_batches[0]
        effect_id = str(getattr(first, "effect_id", "") or "")
        tier = effect_id.removeprefix("fertilizer_")
        spec = getattr(engine, "FERTILIZERS", {}).get(tier)
        name = str(getattr(spec, "name", "") or _label(tier) or "Fertilizer")
        queued_items = _queued_fertilizer_items(
            engine,
            queued_batches,
            starts_after=name,
        )
        growth_units = max(
            0,
            int(getattr(first, "growth_per_card_units", 0) or 0),
        )
        growth = growth_units // 100
        effect = f"+{growth:,} Growth per card"
        current = tuple(
            batch
            for batch in active_batches
            if str(getattr(batch, "effect_id", "") or "") == effect_id
        )
        cards_remaining = sum(
            max(0, int(getattr(batch, "remaining_cards", 0) or 0))
            for batch in current
        )
        total_cards = sum(
            max(0, int(getattr(batch, "total_cards", 0) or 0))
            for batch in current
        )
        queued_cards = sum(
            max(0, int(getattr(batch, "remaining_cards", 0) or 0))
            for batch in queued_batches
        )
        noun = "card" if cards_remaining == 1 else "cards"
        duration = f"{cards_remaining:,} {noun} remaining"
        queue_copy = (
            f" {queued_cards:,} cards queued after this dose."
            if queued_cards else ""
        )
        return FertilizerStatus(
            "active",
            name,
            effect,
            duration,
            FERTILIZER_CARD_DESCRIPTION,
            f"Fertilized with {name}. {effect}. {duration}.{queue_copy}",
            0,
            None,
            tier,
            cards_remaining,
            max(cards_remaining, total_cards),
            queued_cards,
            None,
            queued_items,
        )

    if queued_batches:
        queued_items = _queued_fertilizer_items(engine, queued_batches)
        first = queued_batches[0]
        effect_id = str(getattr(first, "effect_id", "") or "")
        tier = effect_id.removeprefix("fertilizer_")
        spec = getattr(engine, "FERTILIZERS", {}).get(tier)
        name = str(getattr(spec, "name", "") or _label(tier) or "Fertilizer")
        growth_units = max(
            0,
            int(getattr(first, "growth_per_card_units", 0) or 0),
        )
        growth = growth_units // 100
        effect = f"+{growth:,} Growth per card"
        queued_cards = sum(
            max(0, int(getattr(batch, "remaining_cards", 0) or 0))
            for batch in queued_batches
        )
        noun = "card" if queued_cards == 1 else "cards"
        duration = f"{queued_cards:,} {noun} queued"
        return FertilizerStatus(
            "queued",
            name,
            effect,
            duration,
            FERTILIZER_CARD_DESCRIPTION,
            f"{name}. {effect}. {duration}.",
            0,
            None,
            tier,
            0,
            0,
            queued_cards,
            None,
            queued_items,
        )

    scheduler = getattr(engine, "fertilizer_schedule", None)
    queued: tuple[Any, ...] = ()
    if callable(scheduler):
        try:
            fertilizer, queued = scheduler(plant, now=float(now))
        except Exception:
            fertilizer, queued = getattr(plant, "fertilizer", None), ()
    else:
        fertilizer = getattr(plant, "fertilizer", None)
    expires_at_ms = getattr(fertilizer, "expires_at_ms", None)
    if (
        fertilizer is None
        or isinstance(expires_at_ms, bool)
        or not isinstance(expires_at_ms, int)
        or expires_at_ms <= 0
    ):
        return FertilizerStatus(
            "inactive",
            "No active Fertilizer",
            "",
            "",
            description,
            "No active Fertilizer.",
            0,
        )

    tier = str(getattr(fertilizer, "tier", "") or "")
    spec = getattr(engine, "FERTILIZERS", {}).get(tier)
    name = str(getattr(spec, "name", "") or _label(tier) or "Fertilizer")
    growth = max(0, int(getattr(fertilizer, "growth_per_answer", 0) or 0))
    effect = f"+{growth:,} Growth per card"
    # Timed Fertilizer is compatibility-only. Enter this branch only when its
    # renderer-neutral projection supplies an explicit positive epoch value.
    effective_end = float(expires_at_ms) / 1000
    # Consecutive doses of the same tier are one visible extension even though
    # their separate windows remain persisted for dose-cap accounting.
    for period in queued:
        starts_at = float(getattr(period, "started_at", 0) or 0)
        if (
            str(getattr(period, "tier", "") or "") != tier
            or starts_at > effective_end
        ):
            break
        effective_end = max(
            effective_end,
            float(getattr(period, "expires_at", 0) or 0),
        )
    seconds = max(0, int(ceil(effective_end - float(now))))
    if seconds <= 0:
        return FertilizerStatus(
            "expired",
            name,
            effect,
            "Expired",
            description,
            f"{name}. {effect}. Expired.",
            0,
        )
    if seconds < 60:
        duration = f"{seconds} {'second' if seconds == 1 else 'seconds'} left"
    else:
        total_minutes = int(ceil(seconds / 60))
        hours, minutes = divmod(total_minutes, 60)
        duration = (
            f"{hours}h {minutes:02d}m left"
            if hours and minutes else
            f"{hours} {'hour' if hours == 1 else 'hours'} left"
            if hours else
            f"{minutes} min left"
        )
    return FertilizerStatus(
        "active",
        name,
        effect,
        duration,
        description,
        f"Fertilized with {name}. {effect}. {duration}.",
        seconds,
        max(0, int(effective_end)),
        tier,
        0,
        0,
        0,
        int(expires_at_ms),
    )
