from __future__ import annotations

from ankigarden.models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt
from ankigarden.reward_presentation import (
    achievement_presentations,
    lookup,
    recent_reward_summaries,
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
            "bundle:2", "coins", "daily_activity", "2026-08-20", "2026-08-20",
            "answer:2", "2026-08-20T12:01:00+00:00", amount=2,
        ),
    ])

    summaries = recent_reward_summaries(state)

    assert len(summaries) == 2
    assert summaries[0].event_keys == ("bundle:1", "achievement:streak_30")
    assert summaries[0].correlation_id == "answer:1"
    assert summaries[0].amounts == {"coins": 100, "inventory_item": 1}
    assert summaries[0].coins_total == 100
    assert summaries[0].inventory_totals == (("growth_charge_small", 1),)
    assert summaries[0].title == "Thirty-day streak"
    assert [line.item_id for line in summaries[0].lines] == ["", "growth_charge_small"]
    assert summaries[1].event_key == "bundle:2"


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
    assert projection.description == "Reach a 7-day active Anki streak."
    assert projection.progress == 0.75
    assert projection.progress_target == 7
    assert projection.unlocked is True
    assert projection.reward_event_key == "achievement:streak_7"
    assert projection.reward_coins == 10
