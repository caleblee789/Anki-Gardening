"""Read-only, card-counted effects shared by the reviewer and its summary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .formatters import format_plant_name


@dataclass(frozen=True)
class ActiveConsumable:
    family: str
    item_id: str
    name: str
    remaining_cards: int
    target_id: str
    target_name: str
    source_event_ids: tuple[str, ...] = ()

    @property
    def artwork_ref(self) -> str:
        return self.item_id


def project_active_consumables(engine: Any, *, now_ms: int | None = None) -> tuple[ActiveConsumable, ...]:
    """Only applied effects, including extensions; inventory and queued tiers stay out."""
    resolver = getattr(engine, "active_plant", None)
    plant = resolver() if callable(resolver) else None
    state = getattr(engine, "state", None)
    owner_resolver = getattr(engine, "_effect_owner", None)
    clock = getattr(engine, "_now_ms", None)
    event_ms = now_ms if now_ms is not None else clock() if callable(clock) else None
    activation = getattr(engine, "_batch_activation_ms", None)
    rows = []
    for family in ("fertilizer", "booster"):
        owner = owner_resolver(plant, family) if callable(owner_resolver) else plant
        batches = tuple(batch for batch in getattr(owner, f"{family}_card_batches", ())
                        if int(getattr(batch, "remaining_cards", 0)) > 0
                        and (event_ms is None or not callable(activation) or activation(batch) <= event_ms))
        if not batches:
            continue
        item_id = "booster_potion" if family == "booster" else str(batches[0].effect_id)
        active = tuple(batch for batch in batches if str(getattr(batch, "effect_id", item_id)) == item_id)
        garden = owner is getattr(state, "garden_card_effects", None)
        tier = item_id.removeprefix("fertilizer_")
        name = ("Booster Potion" if family == "booster" else
                {"basic": "Basic Fertilizer", "quality": "Quality Fertilizer", "premium": "Magical Fertilizer"}.get(tier, "Fertilizer"))
        rows.append(ActiveConsumable(
            family, item_id, name, sum(int(batch.remaining_cards) for batch in active),
            str(getattr(engine, "GARDEN_SUPPLY_TARGET", "garden:overflow")) if garden else str(getattr(owner, "plant_id", "")),
            "Garden" if garden else format_plant_name(owner),
            tuple(dict.fromkeys(str(batch.source_event_key) for batch in active if getattr(batch, "source_event_key", ""))),
        ))
    return tuple(rows)
