"""Pure, shared presentation projections for plant-specific Garden surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

def _label(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title()


@dataclass(frozen=True)
class FertilizerStatus:
    phase: str
    name: str
    effect: str
    duration: str
    description: str
    accessible_text: str
    # ``seconds_remaining`` remains a compatibility field for schema-25 UI
    # fixtures.  Release 2.2 Fertilizer is card-counted, so new projections
    # always leave it at zero and use the exact card fields below.
    seconds_remaining: int = 0
    cards_remaining: int = 0
    total_cards: int = 0
    queued_doses: int = 0

    @property
    def active(self) -> bool:
        return self.phase == "active"


def fertilizer_status(
    engine: Any,
    plant: Any,
    *,
    now: float,
    description: str = (
        "Fertilizer adds Growth per eligible card answer for a fixed number of cards."
    ),
) -> FertilizerStatus:
    """Project the authoritative FIFO card queue into stable UI fields.

    Elapsed wall-clock time is intentionally ignored.  Closing Anki, pausing,
    or reading slowly cannot change this presentation or consume value.
    """

    del now
    active = tuple(
        batch
        for batch in (getattr(plant, "fertilizer_card_batches", ()) or ())
        if max(0, int(getattr(batch, "remaining_cards", 0) or 0)) > 0
    )
    queued = tuple(
        batch
        for batch in (getattr(plant, "fertilizer_card_queue", ()) or ())
        if max(0, int(getattr(batch, "remaining_cards", 0) or 0)) > 0
    )
    if not active:
        return FertilizerStatus(
            "inactive",
            "No active Fertilizer",
            "",
            "",
            description,
            "No active Fertilizer.",
            0,
        )

    fertilizer = active[0]
    effect_id = str(getattr(fertilizer, "effect_id", "") or "")
    tier = effect_id.removeprefix("fertilizer_")
    spec = getattr(engine, "FERTILIZERS", {}).get(tier)
    name = str(getattr(spec, "name", "") or _label(tier) or "Fertilizer")
    growth_units = max(
        0,
        int(getattr(fertilizer, "growth_per_card_units", 0) or 0),
    )
    growth = growth_units // 100
    effect = f"+{growth:,} Growth per eligible card answer"
    matching_active = tuple(
        batch for batch in active
        if str(getattr(batch, "effect_id", "") or "") == effect_id
    )
    cards = sum(
        max(0, int(getattr(batch, "remaining_cards", 0) or 0))
        for batch in matching_active
    )
    total_cards = sum(
        max(0, int(getattr(batch, "total_cards", 0) or 0))
        for batch in matching_active
    )
    duration = f"{cards:,} {'card' if cards == 1 else 'cards'} left"
    queued_count = len(queued)
    queue_copy = (
        f" {queued_count:,} queued {'dose' if queued_count == 1 else 'doses'}."
        if queued_count else ""
    )
    return FertilizerStatus(
        "active",
        name,
        effect,
        duration,
        description,
        f"Fertilized with {name}. {effect}. {duration}.{queue_copy}",
        0,
        cards,
        max(cards, total_cards),
        queued_count,
    )
