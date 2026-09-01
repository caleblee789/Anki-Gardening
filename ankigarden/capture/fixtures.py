"""Pure deterministic release-capture fixture contracts."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, TypedDict


CAPTURE_DATE = date(2026, 8, 28)

# One uninterrupted 365-day streak beginning 2025-08-29 reaches each
# milestone on these days, inclusive. These dates are capture evidence only;
# production achievement history remains derived from authoritative revlog.
STREAK_MILESTONE_DATES: dict[str, date] = {
    "streak_7": date(2025, 9, 4),
    "streak_30": date(2025, 9, 27),
    "streak_100": date(2025, 12, 6),
    "streak_365": CAPTURE_DATE,
}


class RepresentativeCollectionInventoryPlan(TypedDict):
    garden_features: tuple[str, ...]
    scenery: tuple[str, ...]
    consumables: dict[str, int]


def achievement_completion_schedule(
    achievement_ids: Iterable[str],
) -> dict[str, date]:
    """Assign distinct, chronological, non-future capture completion dates."""

    requested = tuple(dict.fromkeys(str(value) for value in achievement_ids))
    schedule: dict[str, date] = {
        achievement_id: STREAK_MILESTONE_DATES[achievement_id]
        for achievement_id in requested
        if achievement_id in STREAK_MILESTONE_DATES
    }
    reserved = set(schedule.values())
    candidate = date(2026, 8, 1)
    for achievement_id in requested:
        if achievement_id in schedule:
            continue
        while candidate in reserved:
            candidate += timedelta(days=1)
        if candidate > CAPTURE_DATE:
            raise ValueError("capture achievement schedule exceeds the capture date")
        schedule[achievement_id] = candidate
        reserved.add(candidate)
        candidate += timedelta(days=1)
    return schedule


def validate_achievement_completion_schedule(
    schedule: dict[str, date],
) -> bool:
    """Return whether a schedule satisfies the frozen release fixture."""

    if any(day > CAPTURE_DATE for day in schedule.values()):
        return False
    if len(set(schedule.values())) != len(schedule):
        return False
    return all(
        schedule.get(achievement_id) == expected
        for achievement_id, expected in STREAK_MILESTONE_DATES.items()
        if achievement_id in schedule
    )


def representative_collection_inventory_plan() -> RepresentativeCollectionInventoryPlan:
    """Return the real owned-item seed for the canonical 30-of-93 face.

    The release catalog adds cosmetic, Landmark, and Cultivation Mastery
    entries to the earlier environment and consumable collection. This seed
    still derives the visible owned count from real state instead of receiving
    capture-only display copy.
    """

    from ..environment import (
        GARDEN_FEATURE_CATALOG,
        GROWTH_CHARGES,
        SCENERY_CATALOG,
    )

    return {
        "garden_features": tuple(
            item_id
            for item_id, item in GARDEN_FEATURE_CATALOG.items()
            if not bool(item.drop_only)
        ),
        "scenery": tuple(
            item_id
            for item_id, item in SCENERY_CATALOG.items()
            if not bool(item.drop_only)
        ),
        "consumables": {
            "fertilizer_basic": 0,
            "fertilizer_quality": 0,
            "fertilizer_premium": 0,
            "booster_potion": 1,
            **{charge_id: 1 for charge_id in GROWTH_CHARGES},
        },
    }


__all__ = [
    "CAPTURE_DATE",
    "STREAK_MILESTONE_DATES",
    "achievement_completion_schedule",
    "representative_collection_inventory_plan",
    "validate_achievement_completion_schedule",
]
