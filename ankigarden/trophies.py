"""Catalog-backed permanent effects and the shared Trophy Room presentation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .balance_catalog import (
    ACHIEVEMENT_BY_ID,
    ACHIEVEMENT_TROPHIES,
    COMPLETION_TRIGGER_COPY,
    SHARED_GROWTH_DENOMINATOR,
    SHARED_GROWTH_NUMERATOR,
)
from .achievements import achievement_objective, achievement_progress_units


@dataclass(frozen=True)
class TrophyEffects:
    review_growth: int = 0
    completion_coins: int = 0
    shared_growth_numerator: int = SHARED_GROWTH_NUMERATOR
    shared_growth_denominator: int = SHARED_GROWTH_DENOMINATOR

    @property
    def shared_growth_percent(self) -> int:
        return 100 * self.shared_growth_numerator // self.shared_growth_denominator


def initialize_trophy_activations(state: Any, event_ms: int) -> None:
    """Adopt existing unlocks once, within the caller's save transaction."""
    for trophy in ACHIEVEMENT_TROPHIES:
        achievement = state.achievements.get(str(trophy.source_achievement_id))
        if achievement is not None and achievement.unlocked:
            state.trophy_activation_ms.setdefault(
                str(trophy.cosmetic_id), max(1, int(event_ms))
            )


def trophy_effects(state: Any, *, event_ms: int | None = None) -> TrophyEffects:
    """Effects depend on committed unlocks, never equipment or visibility.

    Historical events at or before activation receive no trophy benefits.
    Omitting event_ms projects the permanently active, current UI state.
    """
    growth = coins = 0
    numerator, denominator = SHARED_GROWTH_NUMERATOR, SHARED_GROWTH_DENOMINATOR
    for trophy in ACHIEVEMENT_TROPHIES:
        achievement = state.achievements.get(str(trophy.source_achievement_id))
        activated = getattr(state, "trophy_activation_ms", {}).get(
            str(trophy.cosmetic_id), 0
        )
        if (achievement is None or not achievement.unlocked or not activated
                or (event_ms is not None and event_ms <= activated)):
            continue
        growth += trophy.review_growth
        coins += trophy.completion_coins
        if trophy.shared_growth_numerator * denominator > numerator * trophy.shared_growth_denominator:
            numerator, denominator = trophy.shared_growth_numerator, trophy.shared_growth_denominator
    return TrophyEffects(growth, coins, numerator, denominator)


@dataclass(frozen=True)
class TrophyPresentation:
    trophy_id: str
    achievement_id: str
    name: str
    asset_id: str
    unlocked: bool
    requirement: str
    progress: int
    target: int
    buff: str
    obtained_at: str = ""

    @property
    def status(self) -> str:
        return "Unlocked" if self.unlocked else "Locked"

    @property
    def progress_text(self) -> str:
        return f"{self.progress:,} of {self.target:,} {achievement_progress_units(self.achievement_id)}"


def trophy_effect_description(trophy: Any) -> str:
    """Describe catalog effect values, including the resulting sharing rate."""
    if trophy.review_growth:
        return f"+{trophy.review_growth:,} Growth per card"
    if trophy.completion_coins:
        return f"{COMPLETION_TRIGGER_COPY}: +{trophy.completion_coins:,} Coins"
    percent = 100 * trophy.shared_growth_numerator // trophy.shared_growth_denominator
    return f"{percent}% Shared Growth per other planted plant\nFull Bloom shares move to unfinished plants."


def trophy_presentations(state: Any) -> tuple[TrophyPresentation, ...]:
    result = []
    for trophy in ACHIEVEMENT_TROPHIES:
        trophy_id = str(trophy.cosmetic_id)
        achievement_id = str(trophy.source_achievement_id)
        definition = ACHIEVEMENT_BY_ID[achievement_id]
        achievement = state.achievements.get(achievement_id)
        unlocked = bool(achievement and achievement.unlocked)
        fraction = 1.0 if unlocked else float(getattr(achievement, "progress", 0) or 0)
        obtained_at = str(getattr(achievement, "unlocked_at", "") or "") if unlocked else ""
        if obtained_at and getattr(achievement, "historical_backfill", False):
            obtained_at = obtained_at[:10]
        result.append(TrophyPresentation(
            trophy_id, achievement_id, trophy.display_name, trophy.asset_id,
            unlocked, achievement_objective(achievement_id),
            min(definition.progress_target, max(0, round(fraction * definition.progress_target))),
            definition.progress_target, trophy_effect_description(trophy),
            obtained_at,
        ))
    return tuple(result)
