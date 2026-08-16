"""Pure, shared presentation projections for plant-specific Garden surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from ..models.state import GROWTH_STAGES, GROWTH_THRESHOLDS


CURRENT_RATE_TOOLTIP = "Based on the current Growth per card"


def _label(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title()


@dataclass(frozen=True)
class GrowthForecast:
    text: str
    accessible_text: str
    cards_left: int | None
    next_stage: str | None
    growth_per_card: int
    depends_on_active_buffs: bool
    tooltip: str = ""
    fully_grown: bool = False


def growth_forecast(
    engine: Any,
    plant: Any,
    *,
    now: float | None = None,
) -> GrowthForecast:
    """Describe cards left using the engine's next-card Growth projection."""

    growth_points = max(0, int(getattr(plant, "growth_points", 0) or 0))
    fully_grown = bool(
        getattr(plant, "fully_grown", False)
        or growth_points >= GROWTH_THRESHOLDS[-1]
    )
    if fully_grown:
        return GrowthForecast(
            "Fully grown",
            f"Fully grown with {growth_points:,} total Growth.",
            None,
            None,
            0,
            False,
            fully_grown=True,
        )

    state = getattr(engine, "state", None)
    active_plant_id = getattr(state, "active_plant_id", None)
    if str(active_plant_id or "") != str(getattr(plant, "plant_id", "") or ""):
        text = "Nurture to start earning Growth"
        return GrowthForecast(text, text, None, None, 0, False)

    stage = str(getattr(plant, "growth_stage", "seed") or "seed").lower()
    try:
        stage_index = GROWTH_STAGES.index(stage)
    except ValueError:
        stage_index = max(
            0,
            min(
                len(GROWTH_STAGES) - 2,
                sum(growth_points >= threshold for threshold in GROWTH_THRESHOLDS) - 1,
            ),
        )
    next_index = min(stage_index + 1, len(GROWTH_STAGES) - 1)
    next_stage = str(GROWTH_STAGES[next_index])
    remaining = max(0, int(GROWTH_THRESHOLDS[next_index]) - growth_points)
    award = engine.project_review_growth(plant, now=now)
    rate = max(0, int(getattr(award, "total_growth", 0) or 0))
    if rate <= 0:
        text = str(getattr(award, "paused_reason", "") or "Growth is paused")
        return GrowthForecast(text, text, None, next_stage, 0, False)

    cards_left = max(0, int(ceil(remaining / rate)))
    unit = "card" if cards_left == 1 else "cards"
    stage_label = next_stage.replace("_", " ").lower()
    text = f"{cards_left:,} {unit} left to {stage_label}"
    depends_on_buffs = bool(
        int(getattr(award, "bonus_percent", 0) or 0) > 0
        or int(getattr(award, "bonus_growth", 0) or 0) > 0
    )
    tooltip = CURRENT_RATE_TOOLTIP if depends_on_buffs else ""
    accessible = (
        f"{text}. {CURRENT_RATE_TOOLTIP}."
        if tooltip else
        f"{text}."
    )
    return GrowthForecast(
        text,
        accessible,
        cards_left,
        next_stage,
        rate,
        depends_on_buffs,
        tooltip,
    )


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
        "Fertilizer temporarily adds Growth to each eligible Anki card answer."
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
    effect = f"+{growth:,} Growth per card"
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
        duration = "Under 1 minute remaining"
    else:
        total_minutes = int(ceil(seconds / 60))
        hours, minutes = divmod(total_minutes, 60)
        duration = (
            f"{hours}h {minutes:02d}m remaining"
            if hours else
            f"{minutes}m remaining"
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
