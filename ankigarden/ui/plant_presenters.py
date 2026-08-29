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
        "Fertilizer adds Growth per card for a limited time."
    ),
) -> FertilizerStatus:
    """Project one fertilizer into stable visible and accessible fields."""

    scheduler = getattr(engine, "fertilizer_schedule", None)
    queued: tuple[Any, ...] = ()
    if callable(scheduler):
        try:
            fertilizer, queued = scheduler(plant, now=float(now))
        except Exception:
            fertilizer, queued = getattr(plant, "fertilizer", None), ()
    else:
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
    effect = f"+{growth:,} Growth per card"
    effective_end = float(getattr(fertilizer, "expires_at", 0) or 0)
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
    )
