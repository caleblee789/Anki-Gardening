from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from ankigarden.models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt
from ankigarden.reward_presentation import (
    RewardLine,
    achievement_presentations,
    lookup,
    project_growth_allocations,
    recent_reward_summaries,
    recurring_reward_presentations,
)


def test_recent_reward_summaries_groups_atomic_receipt_lines_without_cross_event_joining() -> None:
    state = GardenState(recent_reward_receipts=[
        RewardReceipt(
            "bundle:1", "coins", "achievement", "streak_30", "2026-08-20",
            "answer:1", "2026-08-20T12:00:00+00:00", amount=100,
            title="Thirty-day streak",
        ),
        RewardReceipt(
            "achievement:streak_30", "inventory_item", "achievement", "streak_30", "2026-08-20",
            "answer:1", "2026-08-20T12:00:00+00:00", amount=1,
            item_id="growth_charge_small",
        ),
        RewardReceipt(
            "garden_find:answer:1:standard", "inventory_item", "garden_find",
            "find_fertilizer", "2026-08-20", "answer:1",
            "2026-08-20T12:00:00+00:00", amount=1,
            item_id="fertilizer_basic", title="Rich Compost",
        ),
        RewardReceipt(
            "all_due:2026-08-20", "growth", "all_due", "2026-08-20", "2026-08-20",
            "answer:1", "2026-08-20T12:00:00+00:00", amount=5,
            plant_id="plant:1",
        ),
        RewardReceipt(
            "bundle:2", "coins", "daily_activity", "2026-08-20", "2026-08-20",
            "answer:2", "2026-08-20T12:01:00+00:00", amount=2,
        ),
    ])

    summaries = recent_reward_summaries(state)

    assert len(summaries) == 2
    assert summaries[0].event_keys == (
        "bundle:1", "achievement:streak_30", "garden_find:answer:1:standard",
        "all_due:2026-08-20",
    )
    assert summaries[0].correlation_id == "answer:1"
    assert summaries[0].amounts == {
        "coins": 100,
        "inventory_item": 2,
        "growth": 5,
    }
    assert summaries[0].coins_total == 100
    assert summaries[0].inventory_totals == (
        ("fertilizer_basic", 1),
        ("growth_charge_small", 1),
    )
    assert summaries[0].title == "Thirty-day streak"
    assert [line.item_id for line in summaries[0].lines] == [
        "", "growth_charge_small", "fertilizer_basic", "",
    ]
    assert summaries[0].learner_text == (
        "+100 Garden Coins, +1 Small Growth Charge, +1 Basic Fertilizer, and "
        "+5 Growth"
    )
    assert summaries[1].event_key == "bundle:2"
    assert RewardLine(
        "inventory_item", 2, item_id="growth_charge_small"
    ).learner_text == "+2 Small Growth Charges"

    target = SimpleNamespace(target_type="mastery", target_id="rose")
    track = SimpleNamespace(
        target=target,
        tiers=(SimpleNamespace(can_claim_now=True, claimable=True),),
        display_name="Rose Cultivation Mastery",
    )
    project = project_growth_allocations(
        (SimpleNamespace(target_type="mastery", target_id="rose", units=100),),
        SimpleNamespace(active_target=target, mastery_track=lambda _species: track),
    )[0]
    assert project.status == "Active project · Ready to claim"


def test_garden_find_lookup_joins_registry_metadata_and_hides_non_hits() -> None:
    hit = GardenFindOutcome(
        "answer:4", "2026-08-20", "hit", "standard", "standard-v1",
        "2026-08-20T12:00:00+00:00", reward_id="find_coin_sprout",
        reward_type="coins", amount=7,
        display_name="Coin Sprout", description="+2 Garden Coins",
        tier="Common", artwork_ref="garden_coin",
        localization_key="garden_find.coin_sprout",
    )
    miss = GardenFindOutcome(
        "answer:5", "2026-08-20", "miss", "standard", "standard-v1",
        "2026-08-20T12:01:00+00:00",
    )

    presentation = lookup(hit)

    assert presentation is not None
    assert presentation.display_name == "Coin Sprout"
    assert presentation.description == "+2 Garden Coins"
    assert presentation.amount == 7  # persisted outcome amount is authoritative
    assert lookup(miss) is None
    preserved = lookup(hit, registry={})
    assert preserved is not None
    assert preserved.display_name == "Coin Sprout"
    assert preserved.description == "+2 Garden Coins"
    assert preserved.amount == 7

    environment_hit = GardenFindOutcome(
        "answer:6", "2026-08-20", "hit", "environment", "environment-v1",
        "2026-08-20T12:02:00+00:00", reward_id="fireflies",
        reward_type="environment_item", amount=1, item_id="fireflies",
    )
    environment_presentation = lookup(environment_hit)
    assert environment_presentation is not None
    assert environment_presentation.description == "Added to Garden decorations"

    scenery_hit = GardenFindOutcome(
        "answer:6b", "2026-08-20", "hit", "environment", "environment-v1",
        "2026-08-20T12:02:30+00:00", reward_id="rainbow_horizon",
        reward_type="environment_item", amount=1, item_id="rainbow_horizon",
    )
    scenery_presentation = lookup(scenery_hit)
    assert scenery_presentation is not None
    assert scenery_presentation.description == "Added to Scenery"

    persisted_growth = GardenFindOutcome(
        "answer:7", "2026-08-20", "hit", "standard", "standard-v1",
        "2026-08-20T12:03:00+00:00", reward_id="find_morning_dew",
        reward_type="growth", amount=40, display_name="Morning Dew",
        description="+40 Growth",
    )
    persisted_growth_presentation = lookup(persisted_growth)
    assert persisted_growth_presentation.description == "+40 Growth"
    assert persisted_growth_presentation.artwork_ref == "morning_dew"
    registry_growth = GardenFindOutcome(
        "answer:8", "2026-08-20", "hit", "standard", "standard-v1",
        "2026-08-20T12:04:00+00:00", reward_id="find_sun_patch",
        reward_type="growth", amount=60,
    )
    assert lookup(registry_growth).description == (
        "+60 Growth"
    )

    state = GardenState(garden_find_outcomes={
        persisted_growth.outcome_key: persisted_growth,
    })
    assert lookup(state, persisted_growth.answer_key) == lookup(persisted_growth)
    assert lookup(state, persisted_growth.outcome_key) == lookup(persisted_growth)

    second_pool_hit = GardenFindOutcome(
        persisted_growth.answer_key, "2026-08-20", "hit", "environment",
        "environment-v1", "2026-08-20T12:05:00+00:00",
        reward_id="fireflies", reward_type="environment_item", amount=1,
        item_id="fireflies",
    )
    state.garden_find_outcomes[second_pool_hit.outcome_key] = second_pool_hit
    with pytest.raises(ValueError, match="pool-qualified"):
        lookup(state, persisted_growth.answer_key)
    assert lookup(state, persisted_growth.outcome_key) == lookup(persisted_growth)
    assert lookup(state, second_pool_hit.outcome_key) == lookup(second_pool_hit)


def test_achievement_presentations_join_definition_identity_to_persisted_progress_metadata() -> None:
    state = GardenState(achievements={
        "streak_7": Achievement(
            "streak_7", "Stale name", "Stale description", unlocked=True,
            progress=0.75, unlocked_at="2026-08-20T12:00:00+00:00",
            rewarded_at="2026-08-20T12:00:00+00:00", reward_event_key="achievement:streak_7",
            historical_backfill=True,
        ),
    })

    projection = next(item for item in achievement_presentations(state) if item.achievement_id == "streak_7")

    assert projection.name == "7-Day Anki Streak"
    assert projection.description == "Reach a 7-day Anki streak."
    assert projection.progress == 0.75
    assert projection.progress_target == 7
    assert projection.unlocked is True
    assert projection.reward_event_key == "achievement:streak_7"
    assert projection.reward_coins == 10
    assert projection.historical_backfill is True
    assert replace(
        projection,
        reward_coins=1,
        reward_small_growth_charges=2,
        reward_standard_growth_charges=1,
    ).reward_summary == (
        "1 Garden Coin and 2 Small Growth Charges and 1 Standard Growth Charge"
    )

    assert "retention_90" not in {
        item.achievement_id for item in achievement_presentations(state)
    }
    absent_but_derivable = next(
        item for item in achievement_presentations(state)
        if item.achievement_id == "streak_30"
    )
    assert absent_but_derivable.historical_backfill is False


def test_recurring_reward_presentations_read_exact_engine_rules_and_committed_state() -> None:
    state = GardenState(streak_days=6)
    state.daily_stats.day = "2026-08-20"
    state.recent_reward_receipts = [RewardReceipt(
        "daily_activity:2026-08-20",
        "coins",
        "daily_activity",
        "2026-08-20",
        "2026-08-20",
        "answer:1",
        "2026-08-20T12:00:00+00:00",
        amount=2,
    )]
    all_due_calls = []

    def all_due_rewards() -> tuple[int, int]:
        all_due_calls.append(True)
        return 12, 5

    engine = SimpleNamespace(
        DAILY_ACTIVITY_COINS=2,
        WEEKLY_STREAK_COINS=10,
        ALL_DUE_BASE_COINS=10,
        all_due_rewards=all_due_rewards,
    )

    rules = {
        item.rule_id: item
        for item in recurring_reward_presentations(state, engine)
    }

    assert rules["daily_activity"].reward_summary == "+2 Garden Coins"
    assert rules["daily_activity"].title == "First card today"
    assert rules["daily_activity"].trigger == "Complete your first card today."
    assert rules["daily_activity"].status == "Earned today"
    assert rules["all_due"].title == "Today’s Cards"
    assert rules["all_due"].trigger == "Complete today’s cards."
    assert rules["all_due"].reward_summary == (
        "+12 Garden Coins and +5 Growth"
    )
    assert all_due_calls == [True]
    assert rules["weekly_streak"].reward_summary == "+10 Garden Coins"
    assert rules["weekly_streak"].next_streak_day == 7
    assert rules["weekly_streak"].streak_days_remaining == 1

    state.streak_days = 3
    missed_day_rules = {
        item.rule_id: item
        for item in recurring_reward_presentations(
            state,
            engine,
            current_streak_days=0,
        )
    }
    assert missed_day_rules["weekly_streak"].next_streak_day == 7
    assert missed_day_rules["weekly_streak"].streak_days_remaining == 7
    assert missed_day_rules["weekly_streak"].status == (
        "Next on Day 7, 7 streak days to go"
    )
    state.streak_days = 6

    state.recent_reward_receipts.extend((
        RewardReceipt(
            "all_due:2026-08-20", "coins", "all_due", "2026-08-20",
            "2026-08-20", "answer:2", "2026-08-20T12:01:00+00:00",
            amount=12,
        ),
        RewardReceipt(
            "all_due:2026-08-20", "growth", "all_due", "2026-08-20",
            "2026-08-20", "answer:2", "2026-08-20T12:01:00+00:00",
            amount=5, plant_id="plant:1",
        ),
    ))
    all_due_calls.clear()
    committed_rules = {
        item.rule_id: item
        for item in recurring_reward_presentations(state, engine)
    }
    assert committed_rules["all_due"].awarded_today is True
    assert committed_rules["all_due"].reward_summary == (
        "+12 Garden Coins and +5 Growth"
    )
    assert all_due_calls == []

    def unavailable_all_due_rewards() -> tuple[int, int]:
        raise RuntimeError("resolver unavailable")

    state.recent_reward_receipts = [
        receipt
        for receipt in state.recent_reward_receipts
        if receipt.source != "all_due"
    ]
    fallback = SimpleNamespace(
        DAILY_ACTIVITY_COINS=2,
        WEEKLY_STREAK_COINS=10,
        ALL_DUE_BASE_COINS=10,
        all_due_rewards=unavailable_all_due_rewards,
    )
    fallback_rules = {
        item.rule_id: item
        for item in recurring_reward_presentations(state, fallback)
    }
    assert fallback_rules["all_due"].reward_coins == 10
    assert fallback_rules["all_due"].reward_growth == 0
