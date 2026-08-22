from __future__ import annotations

from dataclasses import replace

import ankigarden.garden_finds as garden_finds
from ankigarden.garden_finds import (
    FALLBACK_REWARD_ID,
    KNOWN_INVENTORY_ITEM_IDS,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_DAILY_CAP,
    STANDARD_FIND_REGISTRY,
    consumption_id,
    deterministic_token,
    eligible_standard_rewards,
    prepare_reward_registry,
    resolve_environment_find,
    resolve_standard_find,
    simulate_standard_find_economy,
    stable_answer_event_identity,
    standard_chance_for_answer,
    ultra_denominator,
)


def test_v1_registry_and_drought_schedule_match_the_approved_contract():
    assert [
        (
            reward.reward_id,
            reward.display_name,
            reward.reward_kind,
            reward.amount,
            reward.inventory_item_id,
            reward.tier,
            reward.weight_tenths,
        )
        for reward in STANDARD_FIND_REGISTRY
    ] == [
        ("find_coin_sprout", "Coin Sprout", "coins", 2, None, "Common", 180),
        ("find_coin_pouch", "Garden Pouch", "coins", 4, None, "Common", 170),
        ("find_morning_dew", "Morning Dew", "growth", 40, None, "Common", 200),
        ("find_sun_patch", "Sun Patch", "growth", 60, None, "Common", 150),
        ("find_coin_cache", "Hidden Coin Cache", "coins", 8, None, "Uncommon", 90),
        ("find_growth_burst", "Growth Burst", "growth", 100, None, "Uncommon", 90),
        (
            "find_small_charge",
            "Charged Seed",
            "inventory_item",
            1,
            "growth_charge_small",
            "Uncommon",
            60,
        ),
        ("find_buried_coins", "Buried Coin Cache", "coins", 20, None, "Rare", 20),
        (
            "find_fertilizer",
            "Rich Compost",
            "inventory_item",
            1,
            "fertilizer_basic",
            "Rare",
            15,
        ),
        (
            "find_booster",
            "Bottled Rain",
            "inventory_item",
            1,
            "booster_potion",
            "Rare",
            15,
        ),
        (
            "find_standard_charge",
            "Root Core",
            "inventory_item",
            1,
            "growth_charge_standard",
            "Exceptional",
            6,
        ),
        ("find_coin_treasury", "Garden Treasury", "coins", 40, None, "Exceptional", 4),
    ]
    assert sum(reward.weight_tenths for reward in STANDARD_FIND_REGISTRY) == 1_000
    assert {
        tier: sum(
            reward.weight_tenths
            for reward in STANDARD_FIND_REGISTRY
            if reward.tier == tier
        )
        for tier in ("Common", "Uncommon", "Rare", "Exceptional")
    } == {"Common": 700, "Uncommon": 240, "Rare": 50, "Exceptional": 10}

    assert [
        (
            answer,
            standard_chance_for_answer(answer).numerator,
            standard_chance_for_answer(answer).denominator,
        )
        for answer in (1, 40, 41, 60, 61, 74, 75, 76)
    ] == [
        (1, 1, 100),
        (40, 1, 100),
        (41, 1, 40),
        (60, 1, 40),
        (61, 1, 20),
        (74, 1, 20),
        (75, 1, 1),
        (76, 1, 1),
    ]


def test_standard_roll_is_deterministic_namespaced_and_pauses_at_daily_cap():
    identity = stable_answer_event_identity(101, card_id=12, answered_at_ms=101)
    lineage_identity = stable_answer_event_identity(202, lineage_id="undo-lineage-7")
    assert lineage_identity == stable_answer_event_identity(303, lineage_id="undo-lineage-7")
    assert consumption_id(identity) == consumption_id(identity)
    assert deterministic_token("secret", identity, "standard:chance") != deterministic_token(
        "secret", identity, "standard:selection"
    )
    assert deterministic_token("secret", identity, "standard:chance") != deterministic_token(
        "secret", identity, "environment:chance"
    )

    first = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=74,
        finds_today=0,
    )
    replay = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=74,
        finds_today=0,
    )
    assert first == replay
    assert first.attempted and first.hit and first.reward is not None
    assert first.next_drought_misses == 0

    capped = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=37,
        finds_today=STANDARD_DAILY_CAP,
    )
    assert not capped.attempted and capped.capped and not capped.hit
    assert capped.next_drought_misses == 37


def test_registry_validation_disables_bad_entries_and_restores_a_safe_fallback():
    fallback, pouch = STANDARD_FIND_REGISTRY[:2]
    invalid_kind = replace(pouch, reward_id="bad_kind", reward_kind="mystery")
    invalid_item = replace(
        STANDARD_FIND_REGISTRY[6],
        reward_id="bad_item",
        inventory_item_id="unknown_item",
    )
    invalid_amount = replace(pouch, reward_id="bad_amount", amount="many")
    prepared = prepare_reward_registry(
        (pouch, invalid_kind, invalid_item, invalid_amount, pouch)
    )

    assert prepared.fallback_added
    assert prepared.rewards[0].reward_id == FALLBACK_REWARD_ID
    assert [issue.code for issue in prepared.issues] == [
        "unknown_kind",
        "invalid_inventory_item",
        "invalid_amount",
        "duplicate_id",
        "fallback_restored",
    ]
    assert set(KNOWN_INVENTORY_ITEM_IDS) == {
        "growth_charge_small",
        "growth_charge_standard",
        "fertilizer_basic",
        "booster_potion",
    }

    all_invalid = prepare_reward_registry((invalid_kind,))
    assert all_invalid.used_default_registry
    assert all_invalid.rewards == STANDARD_FIND_REGISTRY

    limited = replace(pouch, reward_id="limited_pouch", per_day_limit=1)
    limited_pool = prepare_reward_registry((fallback, limited))
    eligible_ids = {
        reward.reward_id
        for reward in eligible_standard_rewards(
            limited_pool,
            growth_available=True,
            reward_daily_counts={"limited_pouch": 1},
            scheduler_day="2026-08-21",
            addon_version="2.1.0",
        )
    }
    assert eligible_ids == {FALLBACK_REWARD_ID}

    # Conditional Growth and inventory entries are excluded before normalized
    # selection; a successful find still resolves to a valid Coin reward.
    coin_only = resolve_standard_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(404),
        drought_misses=74,
        finds_today=0,
        growth_available=False,
        available_inventory_item_ids=(),
    )
    assert coin_only.reward is not None
    assert coin_only.reward.reward_kind == "coins"
    assert fallback.enabled and fallback.eligibility_rule == "always"


def test_special_environment_pool_prioritizes_rarest_unowned_hit(monkeypatch):
    monkeypatch.setattr(garden_finds, "_draw_below", lambda *args, **kwargs: True)
    identity = stable_answer_event_identity(505)

    ultra = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=(),
        ultra_pity_misses=75_000,
    )
    assert ultra.hit and ultra.tier == "ultra_environment"
    assert ultra.item in SPECIAL_ENVIRONMENT_POOL
    assert ultra.next_ultra_pity_misses == 0
    assert len([ultra.item]) == 1

    owned_ultra = {
        item.item_id for item in SPECIAL_ENVIRONMENT_POOL
        if item.tier == "ultra_environment"
    }
    very_rare = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=owned_ultra,
        ultra_pity_misses=12,
    )
    assert very_rare.hit and very_rare.tier == "very_rare_environment"
    assert very_rare.next_ultra_pity_misses == 13

    all_owned = {item.ownership_key for item in SPECIAL_ENVIRONMENT_POOL}
    none = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=all_owned,
        ultra_pity_misses=99,
    )
    assert not none.hit and none.item is None
    assert none.next_ultra_pity_misses == 100


def test_special_environment_denominators_and_pool_are_exact_and_independent():
    assert [(item.item_id, item.environment_kind, item.tier) for item in SPECIAL_ENVIRONMENT_POOL] == [
        ("fireflies", "weather", "rare_environment"),
        ("rainbow_horizon", "scenery", "rare_environment"),
        ("rainbow_sunshower", "weather", "very_rare_environment"),
        ("halloween", "scenery", "very_rare_environment"),
        ("full_moon", "scenery", "ultra_environment"),
        ("eclipse", "scenery", "ultra_environment"),
    ]
    assert [
        (misses, ultra_denominator(misses))
        for misses in (0, 74_999, 75_000, 84_999, 85_000, 94_999, 95_000, 104_999, 105_000, 114_999, 115_000)
    ] == [
        (0, 100_000),
        (74_999, 100_000),
        (75_000, 90_000),
        (84_999, 90_000),
        (85_000, 80_000),
        (94_999, 80_000),
        (95_000, 70_000),
        (104_999, 70_000),
        (105_000, 60_000),
        (114_999, 60_000),
        (115_000, 50_000),
    ]

    # Standard cap state is intentionally absent from the special-pool API, and
    # both pools share the version-independent consumption key while drawing
    # from separate keyed namespaces.
    identity = stable_answer_event_identity(606)
    standard = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=8,
        finds_today=STANDARD_DAILY_CAP,
    )
    special = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=(),
        ultra_pity_misses=8,
    )
    assert standard.consumption_id == special.consumption_id
    assert standard.capped
    assert special.next_ultra_pity_misses in (0, 9)


def test_100k_simulation_stays_within_find_and_economy_budgets():
    result = simulate_standard_find_economy(
        eligible_answers=100_000,
        answers_per_day=50,
    )

    assert 45 <= result.average_answers_per_find <= 55
    assert result.max_drought_misses <= 74
    assert result.max_daily_finds <= STANDARD_DAILY_CAP
    assert result.coins_per_100_answers <= 5
    assert result.direct_growth_percent_of_base <= 6
    assert 700 <= 100_000 / result.inventory_counts["growth_charge_small"] <= 900
    assert (
        result.inventory_counts["fertilizer_basic"]
        + result.inventory_counts["booster_potion"]
        < result.inventory_counts["growth_charge_small"]
    )
    assert (
        result.inventory_counts["growth_charge_standard"]
        < result.inventory_counts["fertilizer_basic"]
        < result.inventory_counts["growth_charge_small"]
    )
    assert set(result.reward_counts) == {
        reward.reward_id for reward in STANDARD_FIND_REGISTRY
    }
