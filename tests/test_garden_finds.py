from __future__ import annotations

from dataclasses import replace

import ankigarden.garden_finds as garden_finds
from ankigarden.garden_finds import (
    ENVIRONMENT_POOL_VERSION,
    ENVIRONMENT_TIER_COMPLETION_PITY,
    ENVIRONMENT_TIER_RULES,
    FALLBACK_REWARD_ID,
    KNOWN_INVENTORY_ITEM_IDS,
    LEGACY_ENVIRONMENT_POOL_VERSION,
    LEGACY_STANDARD_POOL_VERSION,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_DAILY_CAP,
    STANDARD_FIND_REGISTRY,
    STANDARD_POOL_VERSION,
    consumption_id,
    deterministic_token,
    eligible_standard_rewards,
    prepare_reward_registry,
    resolve_environment_find,
    resolve_environment_completion_pity,
    resolve_standard_find,
    simulate_standard_find_economy,
    stable_answer_event_identity,
    standard_find_artwork_ref,
    standard_find_status,
    standard_daily_cap,
    standard_chance_for_answer,
    ultra_denominator,
)


def test_v2_registry_and_drought_schedule_match_the_approved_contract():
    assert LEGACY_STANDARD_POOL_VERSION == "standard-v1"
    assert STANDARD_POOL_VERSION == "standard-v2"
    assert LEGACY_ENVIRONMENT_POOL_VERSION == "environment-v1"
    assert ENVIRONMENT_POOL_VERSION == "environment-v2"
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
    artwork_by_reward = {
        reward.reward_id: reward.artwork_ref
        for reward in STANDARD_FIND_REGISTRY
    }
    assert artwork_by_reward["find_coin_pouch"] == "garden_pouch"
    assert artwork_by_reward["find_morning_dew"] == "morning_dew"
    assert standard_find_artwork_ref("find_morning_dew", "growth") == "morning_dew"
    assert standard_find_artwork_ref("unknown", "fallback") == "fallback"
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

    status = standard_find_status(finds_today=2, drought_misses=74)
    assert status.finds_today == 2
    assert status.daily_cap == 3
    assert status.next_card_guaranteed
    assert not status.daily_limit_reached
    assert not hasattr(status, "drought_misses")

    capped_status = standard_find_status(finds_today=3, drought_misses=74)
    assert capped_status.daily_limit_reached and capped_status.rolls_paused
    assert not capped_status.next_card_guaranteed


def test_stepped_daily_cap_pauses_and_resumes_the_preserved_drought(
    monkeypatch,
) -> None:
    assert [
        (answers, standard_daily_cap(answers))
        for answers in (0, 199, 200, 399, 400, 10_000)
    ] == [
        (0, 3),
        (199, 3),
        (200, 4),
        (399, 4),
        (400, 5),
        (10_000, 5),
    ]
    identity = stable_answer_event_identity(909)
    paused = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=37,
        finds_today=3,
        eligible_answers_today=199,
    )
    assert paused.capped and not paused.attempted
    assert paused.next_drought_misses == 37

    monkeypatch.setattr(garden_finds, "_draw_below", lambda *args, **kwargs: False)
    resumed = resolve_standard_find(
        secret="profile-secret",
        answer_identity=identity,
        drought_misses=paused.next_drought_misses,
        finds_today=3,
        eligible_answers_today=200,
    )
    assert resumed.attempted and not resumed.capped and not resumed.hit
    assert resumed.drought_answer_number == 38
    assert resumed.next_drought_misses == 38


def test_natural_environment_ties_award_rarest_only_but_forced_ties_award_all(
    monkeypatch,
) -> None:
    monkeypatch.setattr(garden_finds, "_draw_below", lambda *args, **kwargs: True)
    natural = resolve_environment_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(910),
        owned_environment_ids=(),
        tier_pity_misses={tier: 0 for tier in ENVIRONMENT_TIER_RULES},
    )
    assert natural.hit and not natural.forced_by_pity
    assert len(natural.items) == 1
    assert natural.tier == "ultra_environment"

    forced = resolve_environment_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(911),
        owned_environment_ids=(),
        tier_pity_misses={
            tier: rule.hard_pity_answers - 1
            for tier, rule in ENVIRONMENT_TIER_RULES.items()
        },
    )
    assert forced.forced_by_pity
    assert {item.tier for item in forced.items} == set(ENVIRONMENT_TIER_RULES)


def test_completion_day_environment_pity_uses_60_180_365_and_forces_all_ties() -> None:
    assert ENVIRONMENT_TIER_COMPLETION_PITY == {
        "rare_environment": 60,
        "very_rare_environment": 180,
        "ultra_environment": 365,
    }
    decision = resolve_environment_completion_pity(
        secret="profile-secret",
        completion_identity="today-cards:2026-08-30",
        owned_environment_ids=(),
        tier_completion_misses={
            tier: threshold - 1
            for tier, threshold in ENVIRONMENT_TIER_COMPLETION_PITY.items()
        },
    )
    assert set(decision.forced_tiers) == set(ENVIRONMENT_TIER_COMPLETION_PITY)
    assert {item.tier for item in decision.items} == set(
        ENVIRONMENT_TIER_COMPLETION_PITY
    )
    assert all(
        decision.next_tier_completion_misses[tier] == 0
        for tier in ENVIRONMENT_TIER_COMPLETION_PITY
    )


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

    # A missing nurture target never removes Growth outcomes or changes their
    # normalized weights. The engine stores an awarded Growth Find if needed.
    with_target = eligible_standard_rewards(
        prepare_reward_registry(),
        growth_available=True,
    )
    without_target = eligible_standard_rewards(
        prepare_reward_registry(),
        growth_available=False,
    )
    assert without_target == with_target
    assert {reward.reward_kind for reward in without_target} == {
        "coins", "growth", "inventory_item"
    }

    # The 75th eligible card is guaranteed and cannot resolve to Common.
    guaranteed = resolve_standard_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(404),
        drought_misses=74,
        finds_today=0,
        growth_available=False,
        available_inventory_item_ids=(),
    )
    assert guaranteed.reward is not None
    assert guaranteed.reward.tier in {"Uncommon", "Rare", "Exceptional"}
    guaranteed_with_target = resolve_standard_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(404),
        drought_misses=74,
        finds_today=0,
        growth_available=True,
        available_inventory_item_ids=(),
    )
    assert guaranteed_with_target == guaranteed
    assert fallback.enabled and fallback.eligibility_rule == "always"


def test_special_environment_pool_prioritizes_rarest_unowned_hit(monkeypatch):
    monkeypatch.setattr(garden_finds, "_draw_below", lambda *args, **kwargs: True)
    identity = stable_answer_event_identity(505)

    ultra = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=(),
        tier_pity_misses={
            "rare_environment": 7,
            "very_rare_environment": 11,
            "ultra_environment": 13,
        },
    )
    assert ultra.hit and ultra.tier == "ultra_environment"
    assert ultra.item in SPECIAL_ENVIRONMENT_POOL
    assert ultra.next_ultra_pity_misses == 0
    assert ultra.next_tier_pity_misses == {
        "rare_environment": 8,
        "very_rare_environment": 12,
        "ultra_environment": 0,
    }
    assert len([ultra.item]) == 1

    owned_ultra = {
        item.item_id for item in SPECIAL_ENVIRONMENT_POOL
        if item.tier == "ultra_environment"
    }
    very_rare = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=owned_ultra,
        tier_pity_misses={
            "rare_environment": 7,
            "very_rare_environment": 11,
            "ultra_environment": 13,
        },
    )
    assert very_rare.hit and very_rare.tier == "very_rare_environment"
    assert very_rare.next_tier_pity_misses == {
        "rare_environment": 8,
        "very_rare_environment": 0,
        "ultra_environment": 13,
    }

    all_owned = {item.ownership_key for item in SPECIAL_ENVIRONMENT_POOL}
    none = resolve_environment_find(
        secret="profile-secret",
        answer_identity=identity,
        owned_environment_ids=all_owned,
        tier_pity_misses={
            "rare_environment": 7,
            "very_rare_environment": 11,
            "ultra_environment": 13,
        },
    )
    assert not none.hit and none.item is None
    assert none.next_tier_pity_misses == {
        "rare_environment": 7,
        "very_rare_environment": 11,
        "ultra_environment": 13,
    }


def test_special_environment_denominators_hard_pity_and_pool_are_exact_and_independent(monkeypatch):
    assert [(item.item_id, item.environment_kind, item.tier) for item in SPECIAL_ENVIRONMENT_POOL] == [
        ("firefly_lantern", "garden_feature", "rare_environment"),
        ("rainbow_horizon", "scenery", "rare_environment"),
        ("prism_trellis", "garden_feature", "very_rare_environment"),
        ("halloween", "scenery", "very_rare_environment"),
        ("full_moon", "scenery", "ultra_environment"),
        ("eclipse", "scenery", "ultra_environment"),
    ]
    assert {
        tier: (rule.base_denominator, rule.hard_pity_answers)
        for tier, rule in ENVIRONMENT_TIER_RULES.items()
    } == {
        "rare_environment": (2_500, 10_000),
        "very_rare_environment": (10_000, 40_000),
        "ultra_environment": (25_000, 50_000),
    }
    assert ultra_denominator(0) == ultra_denominator(1_000_000) == 25_000

    monkeypatch.setattr(garden_finds, "_draw_below", lambda *args, **kwargs: False)
    pity = resolve_environment_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(605),
        owned_environment_ids=(),
        tier_pity_misses={
            "rare_environment": 9_999,
            "very_rare_environment": 2,
            "ultra_environment": 3,
        },
    )
    assert pity.hit and pity.tier == "rare_environment"
    assert pity.forced_by_pity
    assert pity.next_tier_pity_misses["rare_environment"] == 0

    for index, tier in enumerate((
        "rare_environment",
        "very_rare_environment",
        "ultra_environment",
    ), start=1):
        owned_other_tiers = {
            item.item_id
            for item in SPECIAL_ENVIRONMENT_POOL
            if item.tier != tier
        }
        counters = {
            candidate_tier: 0
            for candidate_tier in ENVIRONMENT_TIER_RULES
        }
        counters[tier] = ENVIRONMENT_TIER_RULES[tier].hard_pity_answers - 1
        tier_pity = resolve_environment_find(
            secret="profile-secret",
            answer_identity=stable_answer_event_identity(700 + index),
            owned_environment_ids=owned_other_tiers,
            tier_pity_misses=counters,
        )
        assert tier_pity.hit and tier_pity.tier == tier
        assert tier_pity.forced_by_pity
        assert tier_pity.next_tier_pity_misses[tier] == 0

    simultaneous_counters = {
        tier: rule.hard_pity_answers - 1
        for tier, rule in ENVIRONMENT_TIER_RULES.items()
    }
    simultaneous = resolve_environment_find(
        secret="profile-secret",
        answer_identity=stable_answer_event_identity(799),
        owned_environment_ids=(),
        tier_pity_misses=simultaneous_counters,
    )
    assert simultaneous.hit and simultaneous.forced_by_pity
    assert {item.tier for item in simultaneous.items} == set(
        ENVIRONMENT_TIER_RULES
    )
    assert len(simultaneous.items) == len(ENVIRONMENT_TIER_RULES)
    assert all(
        simultaneous.next_tier_pity_misses[tier] == 0
        for tier in ENVIRONMENT_TIER_RULES
    )

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
        tier_pity_misses={"ultra_environment": 8},
    )
    assert standard.consumption_id == special.consumption_id
    assert standard.capped
    assert special.next_ultra_pity_misses == 9


def test_100k_simulation_stays_within_find_and_economy_budgets():
    result = simulate_standard_find_economy(
        eligible_answers=100_000,
        answers_per_day=50,
    )

    assert 45 <= result.average_answers_per_find <= 55
    assert result.max_drought_misses <= 74
    assert result.max_daily_finds <= STANDARD_DAILY_CAP
    assert result.coins_per_100_answers <= 6
    assert result.direct_growth_percent_of_base <= 6
    assert 500 <= 100_000 / result.inventory_counts["growth_charge_small"] <= 650
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
