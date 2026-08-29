from __future__ import annotations

import pytest

from scripts.simulate_balance_profiles import (
    PROFILE_CARDS_PER_DAY,
    REVIEW_SPEEDS_CARDS_PER_HOUR,
    simulate_profiles,
)


@pytest.fixture(scope="module")
def balance_report():
    return simulate_profiles()


def test_365_day_profiles_cover_release_volumes_and_progression_targets(balance_report):
    assert tuple(profile.cards_per_day for profile in balance_report.profiles) == (
        PROFILE_CARDS_PER_DAY
    )

    for profile in balance_report.profiles:
        assert profile.cards_completed == profile.cards_per_day * 365
        assert profile.first_plant_stage_cards["sprout"] <= 50
        assert profile.first_plant_full_bloom_day is not None

    hundred = next(
        profile for profile in balance_report.profiles
        if profile.cards_per_day == 100
    )
    assert 30 <= hundred.first_plant_full_bloom_day <= 60


def test_standard_find_release_limits_hold_for_every_profile(balance_report):
    for profile in balance_report.profiles:
        assert profile.finds.maximum_attempted_card_gap <= 75
        assert profile.finds.maximum_per_day <= 3
        assert profile.finds.total == sum(profile.finds.reward_counts.values())
        assert 0 < profile.finds.average_per_day <= 3


def test_coin_sources_purchase_policy_and_completion_share_are_reconciled(balance_report):
    for profile in balance_report.profiles:
        assert profile.gross_coins == sum(profile.coins_by_source.values())
        assert profile.coins_by_source["Today’s Cards"] == 3_650
        assert 0 < profile.completion_reward_share_percent < 60
        assert profile.purchase_completion_day["all species"] is not None
        assert profile.purchase_completion_day["all beds"] is not None
        assert profile.purchase_completion_day["purchasable Weather"] is not None

    for profile in balance_report.profiles:
        if profile.cards_per_day >= 100:
            assert profile.purchase_completion_day["all modeled Coin unlocks"] <= 365


def test_consumable_acquisition_use_and_inventory_are_conserved(balance_report):
    for profile in balance_report.profiles:
        consumables = profile.consumables
        for item_id, acquired in consumables.acquired.items():
            assert acquired == (
                consumables.used.get(item_id, 0)
                + consumables.inventory_remaining.get(item_id, 0)
            )
        assert all(value >= 0 for value in consumables.effect_cards_remaining.values())
        assert all(
            value >= 0
            for value in consumables.timed_effect_seconds_remaining.values()
        )


def test_six_beds_keep_200_percent_output_until_every_plant_is_complete(balance_report):
    for profile in balance_report.profiles:
        six_beds = profile.six_bed_garden
        assert six_beds.passive_plants_at_start == 5
        assert six_beds.output_percent_while_growth_available == 200
        assert six_beds.first_full_bloom_day is not None
        if profile.cards_per_day >= 50:
            assert six_beds.plants_in_full_bloom_after_365_days == 6
            assert six_beds.all_six_full_bloom_day is not None


def test_environment_pity_and_random_power_are_bounded_and_visible(balance_report):
    assert {
        pity.tier: pity.force_threshold_cards
        for pity in balance_report.environment_pity
    } == {
        "rare_environment": 5_000,
        "very_rare_environment": 20_000,
        "ultra_environment": 50_000,
    }
    assert max(balance_report.environment_growth_equivalent_at_100_cards.values()) == 200
    hundred = next(
        profile for profile in balance_report.profiles
        if profile.cards_per_day == 100
    )
    assert hundred.maximum_random_environment_advantage_percent <= 20


def test_timed_fertilizer_prices_anchor_to_growth_charges_at_100_cards_per_hour(
    balance_report,
):
    assert REVIEW_SPEEDS_CARDS_PER_HOUR == (30, 100, 300)
    by_tier = {row.tier: row for row in balance_report.timed_fertilizer_value}

    assert by_tier["Basic"].growth_per_coin_by_speed[100] == pytest.approx(100 / 30)
    assert by_tier["Quality"].growth_per_coin_by_speed[100] == 4
    assert by_tier["Magical"].growth_per_coin_by_speed[100] == 4

    for row in by_tier.values():
        assert row.growth_per_coin_by_speed[30] < row.growth_per_coin_by_speed[100]
        assert row.growth_per_coin_by_speed[300] > row.growth_per_coin_by_speed[100]
