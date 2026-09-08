"""Read-only bed progression shared by Garden and Progress presentations.

Legacy milestone IDs remain the reward ledger identities. Nothing in this
module evaluates grants or mutates the profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .achievements import ACHIEVEMENTS_BY_ID, achievement_objective
from .balance_catalog import BED_UNLOCKS
from .models.state import CURRENT_CATALOG_SPECIES_ORDER, GROWTH_STAGES, GROWTH_THRESHOLDS


def species_progress_counts(state: object) -> tuple[int, int]:
    """Count saved species, including stored plants and stages past Mature."""
    species = set(CURRENT_CATALOG_SPECIES_ORDER)
    plants = tuple(getattr(state, "plants", ()))
    mature_threshold = GROWTH_THRESHOLDS[GROWTH_STAGES.index("mature")]
    mature = {plant.species for plant in plants
              if plant.species in species and plant.growth_points >= mature_threshold}
    bloom = {plant.species for plant in plants
             if plant.species in species and plant.fully_grown}
    return len(mature), len(bloom)


def _milestone_id(definition: object) -> str:
    value = definition.source_achievement_id
    return str(getattr(value, "value", value) or "")


def earned_bed_numbers(state: object) -> frozenset[int]:
    """Union legacy entitlements without imposing new sequential criteria."""
    slots = int(getattr(state, "unlocked_slots", 0))
    earned = set(getattr(state, "earned_bed_unlocks", ()))
    achievements = getattr(state, "achievements", {})
    return frozenset(item.bed_number for item in BED_UNLOCKS
                     if item.included or item.bed_number <= slots
                     or item.bed_number in earned
                     or bool(getattr(achievements.get(_milestone_id(item)), "unlocked", False)))


@dataclass(frozen=True)
class PlantBedProgress:
    bed_id: str
    bed_number: int
    milestone_id: str
    starter: bool
    requirement: str
    current: int
    target: int
    unlocked: bool
    next_bed: bool
    unlocked_at: str | None
    bonus_items: tuple[tuple[str, int], ...]
    bonus_received: bool

    @property
    def progress(self) -> float:
        return min(1.0, max(0.0, self.current / self.target)) if self.target else 0.0

    @property
    def status(self) -> str:
        return "Unlocked" if self.unlocked else "Next unlock" if self.next_bed else "Locked"


def plant_bed_progress(state: object) -> tuple[PlantBedProgress, ...]:
    mature, bloom = species_progress_counts(state)
    earned = earned_bed_numbers(state)
    next_bed = next((item.bed_number for item in BED_UNLOCKS if item.bed_number not in earned), None)
    achievements = getattr(state, "achievements", {})
    receipts = tuple(getattr(state, "recent_reward_receipts", ()))
    rows = []
    for item in BED_UNLOCKS:
        milestone_id = _milestone_id(item)
        definition = ACHIEVEMENTS_BY_ID.get(milestone_id)
        saved = achievements.get(milestone_id)
        event_key = f"achievement:{milestone_id}"
        bonus = tuple(definition.reward.inventory_items.items()) if definition else ()
        # The timestamp plus the canonical grant identity survives receipt
        # pruning and item consumption. Migration bed_claim markers do not
        # prove that the milestone's bonus was ever granted.
        granted = bool(bonus) and (
            bool(getattr(saved, "rewarded_at", None))
            and getattr(saved, "reward_event_key", "") == event_key
            or all(any(receipt.event_key == event_key
                       and receipt.reward_type == "inventory_item"
                       and receipt.item_id == item_id and receipt.amount >= quantity
                       for receipt in receipts) for item_id, quantity in bonus)
        )
        unlocked_at = None
        if item.bed_number in earned and saved is not None:
            recorded = getattr(saved, "unlocked_at", None)
            synthetic = (getattr(saved, "historical_backfill", False)
                         or str(getattr(saved, "reward_event_key", "")).startswith("migration:"))
            if recorded and not synthetic:
                try:
                    datetime.fromisoformat(recorded)
                except (ValueError, TypeError):
                    pass
                else:
                    unlocked_at = recorded
        rows.append(PlantBedProgress(
            bed_id=f"bed_{item.bed_number}", bed_number=item.bed_number,
            milestone_id=milestone_id, starter=item.included,
            requirement=achievement_objective(definition) if definition else "Available from the start",
            current=(mature if definition.progress_metric.value == "mature_plants" else bloom) if definition else 0,
            target=definition.progress_target if definition else 0,
            unlocked=item.bed_number in earned, next_bed=item.bed_number == next_bed,
            unlocked_at=unlocked_at, bonus_items=bonus, bonus_received=bool(granted),
        ))
    return tuple(rows)
