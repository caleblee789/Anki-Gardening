from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
import os

import pytest


os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden import balance_catalog  # noqa: E402
from ankigarden.achievements import (  # noqa: E402
    ACHIEVEMENT_DEFINITIONS,
    ACHIEVEMENTS_BY_ID,
    FULL_BLOOM_ACHIEVEMENTS,
    LIFETIME_ANSWER_ACHIEVEMENTS,
    VALID_COMPLETION_ACHIEVEMENTS,
    AchievementProgressMetric,
    AchievementProgressValues,
    HistoricalReview,
    RewardBundle,
    achievement_progress_value,
    analyze_history,
)


EXPECTED_IDS = [
    "streak_7",
    "streak_30",
    "streak_100",
    "streak_365",
    "reviews_100_day",
    "reviews_1000_total",
    "all_due_done",
    "first_canopy",
    "first_full_bloom",
    "growing_garden",
    "flourishing_garden",
    "botanical_collection",
    "ten_harvests",
    "fifty_harvests",
    "hundred_harvests",
    "year_of_harvests",
    "deep_canopy",
    "established_roots",
    "old_growth",
    "ancient_garden",
]


def test_registry_adapts_all_twenty_canonical_definitions() -> None:
    assert [item.achievement_id for item in ACHIEVEMENT_DEFINITIONS] == EXPECTED_IDS
    assert [item.achievement_id.value for item in balance_catalog.ACHIEVEMENTS] == EXPECTED_IDS
    assert len(ACHIEVEMENTS_BY_ID) == 20
    for domain, canonical in zip(
        ACHIEVEMENT_DEFINITIONS,
        balance_catalog.ACHIEVEMENTS,
    ):
        assert domain.achievement_id == canonical.achievement_id.value
        assert domain.name == canonical.display_name
        assert domain.description == canonical.description
        assert domain.category.value == canonical.category.value
        assert domain.evaluation_mode.value == canonical.evaluation_mode.value
        assert domain.progress_metric.value == canonical.progress_metric.value
        assert domain.progress_target == canonical.progress_target
        assert domain.historical_backfill == canonical.historical_backfill


def test_existing_seven_rewards_remain_backward_compatible() -> None:
    assert EXPECTED_IDS[:7] == [
        "streak_7",
        "streak_30",
        "streak_100",
        "streak_365",
        "reviews_100_day",
        "reviews_1000_total",
        "all_due_done",
    ]
    assert {
        achievement_id: (
            ACHIEVEMENTS_BY_ID[achievement_id].reward.coins,
            ACHIEVEMENTS_BY_ID[achievement_id].reward.small_growth_charges,
            ACHIEVEMENTS_BY_ID[achievement_id].reward.standard_growth_charges,
        )
        for achievement_id in EXPECTED_IDS[:7]
    } == {
        "streak_7": (10, 0, 0),
        "streak_30": (100, 1, 0),
        "streak_100": (300, 0, 0),
        "streak_365": (1_000, 0, 0),
        "reviews_100_day": (25, 0, 0),
        "reviews_1000_total": (0, 0, 1),
        "all_due_done": (5, 0, 0),
    }


def test_new_reward_bundle_fields_cover_beds_grand_charges_and_cosmetics() -> None:
    assert ACHIEVEMENTS_BY_ID["first_canopy"].reward == RewardBundle(
        bed_unlocks=(3,)
    )
    assert ACHIEVEMENTS_BY_ID["flourishing_garden"].reward == RewardBundle(
        standard_growth_charges=1,
        bed_unlocks=(6,),
    )
    assert ACHIEVEMENTS_BY_ID["botanical_collection"].reward == RewardBundle(
        grand_growth_charges=1,
        cosmetic_ids=("botanists_plaque",),
    )
    assert ACHIEVEMENTS_BY_ID["year_of_harvests"].reward == RewardBundle(
        coins=300,
        cosmetic_ids=("garden_journal",),
    )
    assert ACHIEVEMENTS_BY_ID["old_growth"].reward == RewardBundle(
        coins=200,
        grand_growth_charges=1,
    )
    assert ACHIEVEMENTS_BY_ID["ancient_garden"].reward == RewardBundle(
        cosmetic_ids=("golden_trowel",),
    )
    assert dict(ACHIEVEMENTS_BY_ID["botanical_collection"].reward.inventory_items) == {
        "growth_charge_grand": 1,
    }


def test_progress_metrics_dispatch_all_new_runtime_counters() -> None:
    values = AchievementProgressValues(
        streak_days=8,
        daily_answers=123,
        lifetime_answers=27_000,
        consecutive_non_again=12,
        valid_all_due_days=1,
        mature_species=2,
        full_bloom_species=4,
        valid_completions=67,
    )
    assert achievement_progress_value(ACHIEVEMENTS_BY_ID["first_canopy"], values) == 2
    assert achievement_progress_value(
        ACHIEVEMENTS_BY_ID["botanical_collection"], values
    ) == 4
    assert achievement_progress_value(
        ACHIEVEMENTS_BY_ID["year_of_harvests"], values
    ) == 67
    assert achievement_progress_value(ACHIEVEMENTS_BY_ID["deep_canopy"], values) == 27_000
    assert achievement_progress_value(ACHIEVEMENTS_BY_ID["all_due_done"], values) == 1
    assert AchievementProgressMetric.MATURE_PLANTS is AchievementProgressMetric.MATURE_SPECIES
    assert (
        AchievementProgressMetric.UNIQUE_FULL_BLOOMS
        is AchievementProgressMetric.FULL_BLOOM_SPECIES
    )
    assert [item.achievement_id for item in FULL_BLOOM_ACHIEVEMENTS] == [
        "first_full_bloom",
        "growing_garden",
        "flourishing_garden",
        "botanical_collection",
    ]
    assert [item.achievement_id for item in VALID_COMPLETION_ACHIEVEMENTS] == [
        "ten_harvests",
        "fifty_harvests",
        "hundred_harvests",
        "year_of_harvests",
    ]


def test_history_backfills_every_lifetime_answer_milestone() -> None:
    start = date(2026, 1, 1)

    def scheduler_day_for(answer_number: int) -> str:
        offset = (
            0
            if answer_number < 10_000
            else 1
            if answer_number < 25_000
            else 2
            if answer_number < 50_000
            else 3
            if answer_number < 100_000
            else 4
        )
        return (start + timedelta(days=offset)).isoformat()

    history = analyze_history(
        (
            HistoricalReview(
                event_id=answer_number,
                answered_at_ms=answer_number,
                scheduler_day=scheduler_day_for(answer_number),
                rating=3,
            )
            for answer_number in range(1, 100_001)
        ),
        current_open_day=(start + timedelta(days=5)).isoformat(),
    )

    assert history.lifetime_answers == 100_000
    assert {
        achievement_id: history.unlock_day(achievement_id)
        for achievement_id in (
            "reviews_1000_total",
            "deep_canopy",
            "established_roots",
            "old_growth",
            "ancient_garden",
        )
    } == {
        "reviews_1000_total": start.isoformat(),
        "deep_canopy": (start + timedelta(days=1)).isoformat(),
        "established_roots": (start + timedelta(days=2)).isoformat(),
        "old_growth": (start + timedelta(days=3)).isoformat(),
        "ancient_garden": (start + timedelta(days=4)).isoformat(),
    }
    assert [
        (item.achievement_id, item.progress_target)
        for item in LIFETIME_ANSWER_ACHIEVEMENTS
    ] == [
        ("reviews_1000_total", 1_000),
        ("deep_canopy", 10_000),
        ("established_roots", 25_000),
        ("old_growth", 50_000),
        ("ancient_garden", 100_000),
    ]


def test_reward_and_progress_contracts_are_frozen_and_validate_inputs() -> None:
    with pytest.raises(TypeError):
        ACHIEVEMENTS_BY_ID["new"] = ACHIEVEMENT_DEFINITIONS[0]
    with pytest.raises(FrozenInstanceError):
        ACHIEVEMENT_DEFINITIONS[0].progress_target = 8
    with pytest.raises(TypeError):
        RewardBundle(coins=True)
    with pytest.raises(ValueError):
        RewardBundle(grand_growth_charges=-1)
    with pytest.raises(ValueError):
        RewardBundle(bed_unlocks=(2,))
    with pytest.raises(ValueError):
        RewardBundle(cosmetic_ids=("garden_journal", "garden_journal"))
    with pytest.raises(ValueError):
        AchievementProgressValues(valid_completions=-1)
