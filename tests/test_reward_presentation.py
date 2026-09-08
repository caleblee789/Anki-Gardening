from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from ankigarden.models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt


def test_plant_beds_starters_and_visible_catalog_preserve_internal_records():
    from ankigarden.achievements import ACHIEVEMENT_DEFINITIONS, BED_MILESTONES
    from ankigarden.plant_beds import plant_bed_progress

    state = GardenState()
    rows = plant_bed_progress(state)
    assert [row.bed_id for row in rows] == [f"bed_{n}" for n in range(1, 7)]
    assert all(row.unlocked and row.requirement == "Available from the start"
               and row.unlocked_at is None and row.target == 0 for row in rows[:2])
    assert rows[2].next_bed
    state.achievements = {definition.achievement_id:
                          Achievement(definition.achievement_id, definition.name, definition.description,
                                      unlocked=True, progress=1.0)
                          for definition in ACHIEVEMENT_DEFINITIONS}
    views = achievement_presentations(state)
    assert len(views) == sum(view.unlocked for view in views) == 16
    assert not set(BED_MILESTONES).intersection(view.achievement_id for view in views)
    assert "botanical_collection" in {view.achievement_id for view in views}
    assert set(BED_MILESTONES).issubset(state.achievements)
from ankigarden.reward_presentation import (
    RewardLine,
    achievement_presentations,
    lookup,
    project_growth_allocations,
    recent_reward_summaries,
    recurring_reward_presentations,
)


@pytest.mark.parametrize("count, expected", ((0, "0 cards studied"), (1, "1 card studied"), (1_234_567, "1,234,567 cards studied")))
def test_past_study_receipt_copy_counts_reviews_and_never_promises_unearned_rewards(count, expected):
    from ankigarden.models.welcome import WelcomeReceipt
    from ankigarden.welcome_presentation import present_welcome

    view = present_welcome(WelcomeReceipt(history_review_count=count))
    assert expected == view.history_intro
    assert "earned you" not in view.history_intro
    assert view.show_history == bool(count)
    assert not view.history and view.achievement_count == 0


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
            "garden_find:answer:1:standard", "inventory_item", "standard_find",
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
    assert summaries[0].garden_find_ids == ("find_fertilizer",)
    assert summaries[0].inventory_totals == (
        ("fertilizer_basic", 1),
        ("growth_charge_small", 1),
    )
    assert summaries[0].title == "Thirty-day streak"
    assert [line.item_id for line in summaries[0].lines] == [
        "", "growth_charge_small", "fertilizer_basic", "",
    ]
    assert summaries[0].learner_text == (
        "+100 Coins, +1 Small Growth Charge, +1 Basic Fertilizer, and "
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
    projects = project_growth_allocations(
        (SimpleNamespace(target_type="mastery", target_id="rose", units=100),),
        SimpleNamespace(active_target=target, mastery_track=lambda _species: track),
    )
    assert projects == ()


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
            requirement="Complete 7 eligible card answers.",
            rewarded_at="2026-08-20T12:00:00+00:00", reward_event_key="achievement:streak_7",
            historical_backfill=True,
        ),
    })

    projection = next(item for item in achievement_presentations(state) if item.achievement_id == "streak_7")

    assert projection.name == "7-Day Anki Streak"
    assert "total +5% bonus to base Growth from card answers" in projection.description
    assert projection.criteria_text == "Complete 7 cards."
    assert projection.progress == 0.75
    assert projection.progress_target == 7
    assert projection.unlocked is True
    assert projection.reward_event_key == "achievement:streak_7"
    assert projection.reward_coins == 0
    assert projection.permanent_growth_percent == 5
    assert projection.historical_backfill is True
    assert replace(
        projection,
        reward_coins=1,
        reward_small_growth_charges=2,
        reward_standard_growth_charges=1,
    ).reward_summary == (
        "Total permanent Growth bonus: +5% and 1 Coin and 2 Small Growth Charges and 1 Standard Growth Charge"
    )

    assert "retention_90" not in {
        item.achievement_id for item in achievement_presentations(state)
    }
    absent_but_derivable = next(
        item for item in achievement_presentations(state)
        if item.achievement_id == "streak_30"
    )
    assert absent_but_derivable.historical_backfill is False
    deep_canopy = next(
        item for item in achievement_presentations(state)
        if item.achievement_id == "deep_canopy"
    )
    assert deep_canopy.criteria_text == "Complete 10,000 cards."


def test_recurring_reward_presentations_read_exact_engine_rules_and_committed_state() -> None:
    from test_engine import make_engine, answer
    engine, storage = make_engine()
    state = storage.state
    state.loadout.active_scenery_effect_id = "autumn"
    state.autumn_coin_carry_units = 90
    before = state.to_dict()
    summary = engine.study_rewards_summary()
    assert summary["first_coins"] == 5
    assert not summary["first_earned"]
    assert state.to_dict() == before

    answer(engine, storage)
    state.loadout.active_scenery_effect_id = "default"
    before = state.to_dict()
    rules = {item.rule_id: item for item in recurring_reward_presentations(state, engine)}
    assert set(rules) == {"daily_activity", "all_due"}
    assert rules["daily_activity"].title == "Study 1 card"
    assert rules["daily_activity"].reward_coins == 5
    assert rules["daily_activity"].awarded_today
    assert rules["all_due"].title == "Finish all cards due today"
    assert rules["all_due"].reward_coins == 16
    assert not rules["all_due"].awarded_today
    assert state.to_dict() == before

    # A baseline eligibility marker has no committed amount to display.
    state.currency_transactions.clear()
    summary = engine.study_rewards_summary()
    assert summary["first_earned"]
    assert summary["first_coins"] is None


def test_dormant_reward_details_are_hidden_without_rewriting_history():
    from copy import deepcopy
    from ankigarden.models.state import FeedbackEvent
    from ankigarden.reward_presentation import reward_content_visible

    allocations = (
        SimpleNamespace(target_type="landmark", target_id="garden_landmark", units=250),
        SimpleNamespace(target_type="mastery", target_id="rose", units=100),
        SimpleNamespace(target_type="legacy", target_id="garden_legacy", units=100),
    )
    rows = project_growth_allocations(allocations, landmark_growth_units=300)
    assert rows == ()
    hidden = RewardReceipt(
        "landmark:1", "inventory_item", "landmark", "mossy_stone_path", "2026-09-05",
        "landmark:1", "2026-09-05T12:00:00+00:00", item_id="mossy_stone_path",
        title="Mossy Stone Path", description="Garden Landmark completed.",
    )
    visible = replace(hidden, event_key="daily:1", reward_type="coins", source="daily_activity",
                      source_id="2026-09-05", correlation_id="answer:1", item_id="", amount=4,
                      title="Daily activity", description="")
    state = GardenState(recent_reward_receipts=[hidden, visible])
    before = deepcopy(state.to_dict())
    summaries = recent_reward_summaries(state)
    assert len(summaries) == 1 and summaries[0].receipts == (visible,)
    assert state.to_dict() == before
    assert not reward_content_visible(FeedbackEvent("landmark:1", "landmark", hidden.description, hidden.occurred_at))
    assert not reward_content_visible(FeedbackEvent("mastery:1", "mastery", "Cultivation Mastery unlocked.", hidden.occurred_at))
    assert not reward_content_visible({"event_kind": "growth_project_claim"})
    assert reward_content_visible({"source": "legacy", "reward_type": "coins"})


def test_live_reward_feed_groups_only_consecutive_growth_and_preserves_distinct_rewards():
    from ankigarden.reward_presentation import RewardBundleProjection, RewardFeedHistory, RewardHero, RewardItemProjection

    def bundle(key, *items):
        return RewardBundleProjection(key, "2026-09-06T12:00:00Z", items)

    def growth(key, units):
        return RewardItemProjection(key, RewardHero.ROUTINE_GROWTH, "Growth", "Routine Growth", growth_units=units)

    history = RewardFeedHistory()
    first = bundle("answer-1", growth("growth-1", 1200))
    history.append(first)
    history.append(bundle("answer-2", growth("growth-2", 800)))
    history.append(bundle("answer-3", RewardItemProjection("bloom", RewardHero.FULL_BLOOM, "Bonsai reached Full Bloom", "Milestone", garden_coins=30), RewardItemProjection("find", RewardHero.ENVIRONMENT_DISCOVERY, "Firefly Lantern", "Discovery", artwork_ref="garden_feature_firefly_lantern")))
    history.append(bundle("answer-4", growth("growth-4", 500)))
    history.append(first)
    history.append(bundle("duplicate-event", growth("growth-2", 800)))
    assert [entry.item.event_id for entry in history.entries] == ["growth-1", "find", "bloom", "growth-4"]
    assert [entry.item.growth_units for entry in history.entries] == [2000, 0, 0, 500]
    assert history.entries[0].event_count == 2
    assert history.entries[2].item.garden_coins == 30
    stored = RewardItemProjection("stored-1", RewardHero.ROUTINE_GROWTH, "Stored Growth", "Routine Growth", growth_units=1, artwork_ref="stored_growth")
    history.append(bundle("answer-5", stored))
    history.append(bundle("answer-6", growth("growth-6", 500)))
    assert history.entries[-2].item == stored
    assert history.entries[-1].item.event_id == "growth-6"
