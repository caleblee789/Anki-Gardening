"""Pure, shared presentation projections for plant-specific Garden surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
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
    seconds_remaining: int

    @property
    def active(self) -> bool:
        return self.phase == "active"


def fertilizer_status(
    engine: Any,
    plant: Any,
    *,
    now: float,
    description: str = (
        "Fertilizer temporarily adds Growth to each card answer."
    ),
) -> FertilizerStatus:
    """Project one fertilizer into stable visible and accessible fields."""

    fertilizer = getattr(plant, "fertilizer", None)
    if fertilizer is None:
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
    effect = f"+{growth:,} Growth per answer"
    seconds = max(0, int(ceil(float(getattr(fertilizer, "expires_at", 0) or 0) - float(now))))
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
    )
