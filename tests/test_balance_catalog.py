from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path

import pytest


os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden import balance_catalog as catalog  # noqa: E402


def grant_signature(grant: catalog.RewardGrant) -> tuple[str, int, str | None]:
    return grant.kind.value, grant.amount, grant.item_id


def effects_by_id() -> dict[str, catalog.EffectDefinition]:
    return {
        effect.effect_id: effect
        for item in (*catalog.GARDEN_BONUSES, *catalog.SCENERIES)
        for effect in item.effects
    }


def test_core_growth_species_stages_and_permanent_tiers_are_exact() -> None:
    assert catalog.BALANCE_CATALOG_VERSION == "2.2.0"
    assert catalog.BASE_GROWTH_PER_REVIEW == 10
    assert (
        catalog.SHARED_GROWTH_NUMERATOR,
        catalog.SHARED_GROWTH_DENOMINATOR,
    ) == (1, 10)
    assert catalog.GROWTH_STAGES == (
        "seed",
        "sprout",
        "young",
        "mature",
        "flowering",
        "full_bloom",
    )
    assert catalog.GROWTH_THRESHOLDS == (0, 400, 2_000, 6_000, 15_000, 35_000)
    assert [item.checkpoint_coin_rewards for item in catalog.STAGES] == [
        (),
        (1, 1, 1, 2),
        (2, 2, 2, 4),
        (4, 4, 4, 8),
        (7, 7, 7, 14),
        (10, 10, 10, 20),
    ]
    assert [item.total_coin_reward for item in catalog.STAGES] == [0, 5, 10, 20, 35, 50]
    assert catalog.STAGE_CHECKPOINT_PERCENTAGES == (25, 50, 75)
    assert catalog.STAGE_REWARD_CHECKPOINT_PERCENTAGES == (25, 50, 75, 100)
    assert catalog.CURRENT_CATALOG_SPECIES_ORDER == (
        "bonsai",
        "rose",
        "sunflower",
        "lavender",
        "hydrangea",
        "peony",
        "foxglove",
        "japanese_maple",
        "wisteria",
        "dahlia",
    )
    assert all(item.starter_eligible for item in catalog.SPECIES)
    assert {item.purchase_price_coins for item in catalog.SPECIES} == {250}
    assert [item.species_id.value for item in catalog.CATALOG.historical_species] == [
        "fern",
        "ivy",
        "cactus",
        "orchid",
        "sunbloom",
        "moonflower",
        "marigold",
        "strawberry",
        "pumpkin",
    ]
    assert [(item.progress_target, item.permanent_growth_percent)
            for item in catalog.STREAK_ACHIEVEMENTS] == [(7, 5), (30, 10), (100, 15), (365, 20)]


def test_consumables_have_exact_card_counts_growth_and_prices() -> None:
    actual = {
        item.consumable_id.value: (
            item.price_coins,
            item.growth_per_card,
            item.card_count,
            item.instant_growth,
            item.purchasable,
        )
        for item in catalog.CONSUMABLES
    }
    assert actual == {
        "fertilizer_basic": (30, 1, 100, 0, True),
        "fertilizer_quality": (100, 2, 200, 0, True),
        "fertilizer_premium": (300, 3, 400, 0, True),
        "booster_potion": (None, 5, 100, 0, False),
        "growth_charge_small": (30, 0, 0, 100, True),
        "growth_charge_standard": (125, 0, 0, 500, True),
        "growth_charge_grand": (None, 0, 0, 2_000, False),
    }
    assert catalog.canonical_consumable_id("magical") == "fertilizer_premium"
    assert catalog.canonical_consumable_id("premium") == "fertilizer_premium"
    assert catalog.RICH_COMPOST_CONSUMABLE_ID == "fertilizer_basic"
    assert catalog.CONSUMABLE_BY_ID["booster_potion"].acquisition == (
        catalog.AcquisitionKind.FIND,
        catalog.AcquisitionKind.ENVIRONMENT_REWARD,
    )
    assert catalog.AcquisitionKind.ENVIRONMENT_REWARD in catalog.CONSUMABLE_BY_ID[
        "growth_charge_small"
    ].acquisition


def test_environment_prices_effects_and_persistent_contracts_are_exact() -> None:
    assert {
        item.bonus_id.value: item.price_coins for item in catalog.GARDEN_BONUSES
    } == {
        "seedling_sign": None,
        "wind_chime": 100,
        "harvest_bell": 175,
        "watering_station": 250,
        "herbalist_hourglass": 350,
        "firefly_lantern": None,
        "prism_trellis": None,
    }
    assert {item.scenery_id.value: item.price_coins for item in catalog.SCENERIES} == {
        "default": None,
        "spring": 400,
        "summer": 600,
        "autumn": 500,
        "snowy": 1_200,
        "rainbow_horizon": None,
        "halloween": None,
        "full_moon": None,
        "eclipse": None,
    }

    effects = effects_by_id()
    assert grant_signature(effects["growth_every_10_plus_1"].grant) == (
        "growth",
        1,
        None,
    )
    assert effects["growth_every_10_plus_1"].cadence.every_n == 5
    watering = effects["growth_every_5_first_100_plus_1"]
    assert (watering.cadence.every_n, watering.cadence.first_n_per_day) == (2, 200)
    hourglass = effects["hourglass_completion_booster"]
    assert (hourglass.cadence.every_n, grant_signature(hourglass.grant)) == (
        15,
        ("consumable", 1, "booster_potion"),
    )
    assert all(effect.cadence.active_only for effect in effects.values())
    assert hourglass.cadence.active_only
    firefly = effects["instant_growth_every_5_plus_3_nurtured"]
    assert firefly.cadence.every_n == 5
    assert firefly.target_policy is catalog.TargetPolicy.ACTIVE_PLANT
    assert firefly.target_tie_break is (
        catalog.TargetTieBreak.NONE
    )
    prism = effects["prism_completion_growth_100"]
    assert (
        prism.cadence.first_n_per_day,
        prism.bank_cap_growth,
        prism.release_trigger,
        prism.release_active_only,
    ) == (None, None, None, False)
    assert prism.trigger is catalog.TriggerKind.VALID_COMPLETION
    assert grant_signature(prism.grant) == ("instant_growth", 100, None)

    assert grant_signature(effects["spring_growth_first_20"].grant) == (
        "growth",
        2,
        None,
    )
    assert effects["summer_growth_every_2_first_120"].cadence.first_n_per_day == 120
    assert grant_signature(effects["autumn_earned_coin_percent"].grant) == (
        "earned_coin_percent",
        15,
        None,
    )
    assert effects["snowy_completion_growth"].cadence.every_n == 1
    assert grant_signature(effects["snowy_completion_growth"].grant) == ("instant_growth", 50, None)
    assert effects["rainbow_horizon_growth_first_75"].cadence.first_n_per_day == 75
    assert [
        (weighted.grant.item_id, weighted.weight_percent)
        for weighted in effects["halloween_completion_gift"].weighted_grants
    ] == [
        ("growth_charge_small", 95),
        ("growth_charge_standard", 4),
        ("booster_potion", 1),
    ]
    assert effects["full_moon_booster_every_4_completions"].cadence.every_n == 4
    assert effects["eclipse_growth_first_125"].cadence.first_n_per_day == 125


@pytest.mark.parametrize(
    ("answers_today", "expected_cap"),
    [(n, None) for n in (0, 1, 199, 200, 399, 400, 10_000)],
)
def test_standard_find_daily_cap_is_unlimited(answers_today: int, expected_cap: int | None) -> None:
    assert catalog.standard_find_daily_cap(answers_today) == expected_cap


def test_standard_find_pool_schedule_and_rewards_are_exact() -> None:
    assert catalog.STANDARD_POOL_VERSION == "standard-v2"
    assert catalog.ENVIRONMENT_POOL_VERSION == "environment-v2"
    assert sum(item.weight_tenths for item in catalog.STANDARD_FINDS) == 1_000
    assert [(item.reward_id.value, item.weight_tenths) for item in catalog.STANDARD_FINDS] == [
        ("find_coin_sprout", 180),
        ("find_coin_pouch", 170),
        ("find_morning_dew", 200),
        ("find_sun_patch", 150),
        ("find_coin_cache", 90),
        ("find_growth_burst", 90),
        ("find_small_charge", 60),
        ("find_buried_coins", 20),
        ("find_fertilizer", 15),
        ("find_booster", 15),
        ("find_standard_charge", 6),
        ("find_coin_treasury", 4),
    ]
    assert [
        (
            item.first_drought_answer,
            item.last_drought_answer,
            item.numerator,
            item.denominator,
            item.minimum_tier,
        )
        for item in catalog.STANDARD_FIND_SCHEDULE
    ] == [
        (1, 40, 1, 100, None),
        (41, 60, 1, 40, None),
        (61, 74, 1, 20, None),
        (75, None, 1, 1, catalog.FindTier.UNCOMMON),
    ]
    assert catalog.standard_find_schedule_band(74).denominator == 20
    assert catalog.standard_find_schedule_band(75).minimum_tier is catalog.FindTier.UNCOMMON
    assert catalog.standard_find_schedule_band(1_000).minimum_tier is catalog.FindTier.UNCOMMON
    rich_compost = catalog.STANDARD_FIND_BY_ID["find_fertilizer"]
    assert grant_signature(rich_compost.grant) == (
        "consumable",
        1,
        "fertilizer_basic",
    )


def test_environment_discovery_has_dual_guarantees_per_next_unowned_item() -> None:
    assert {
        item.tier_id.value: (
            item.base_denominator,
            item.card_guarantee,
            item.completion_guarantee,
            item.guarantee_scope,
            item.reset_counters_after_discovery,
        )
        for item in catalog.ENVIRONMENT_TIERS
    } == {
        "rare_environment": (
            2_500,
            10_000,
            60,
            catalog.DiscoveryGuaranteeScope.NEXT_UNOWNED_ITEM,
            True,
        ),
        "very_rare_environment": (
            10_000,
            40_000,
            180,
            catalog.DiscoveryGuaranteeScope.NEXT_UNOWNED_ITEM,
            True,
        ),
        "ultra_environment": (
            25_000,
            50_000,
            365,
            catalog.DiscoveryGuaranteeScope.NEXT_UNOWNED_ITEM,
            True,
        ),
    }
    assert [
        (item.tier_id.value, item.item_id)
        for item in catalog.ENVIRONMENT_DISCOVERIES
    ] == [
        ("rare_environment", "firefly_lantern"),
        ("rare_environment", "rainbow_horizon"),
        ("very_rare_environment", "prism_trellis"),
        ("very_rare_environment", "halloween"),
        ("ultra_environment", "full_moon"),
        ("ultra_environment", "eclipse"),
    ]


def test_all_twenty_achievements_and_multi_grants_are_canonical() -> None:
    assert len(catalog.ACHIEVEMENTS) == 20
    assert set(catalog.ACHIEVEMENTS_BY_ID) == {item.value for item in catalog.AchievementId}
    assert [grant_signature(item) for item in catalog.ACHIEVEMENTS_BY_ID["flourishing_garden"].rewards] == [
        ("bed_unlock", 1, "bed_6"),
        ("consumable", 1, "growth_charge_standard"),
    ]
    assert [grant_signature(item) for item in catalog.ACHIEVEMENTS_BY_ID["botanical_collection"].rewards] == [
        ("consumable", 1, "growth_charge_grand"),
        ("cosmetic", 1, "botanists_plaque"),
    ]
    assert [grant_signature(item) for item in catalog.ACHIEVEMENTS_BY_ID["year_of_harvests"].rewards] == [
        ("coins", 300, None),
        ("cosmetic", 1, "garden_journal"),
    ]
    assert [grant_signature(item) for item in catalog.ACHIEVEMENTS_BY_ID["old_growth"].rewards] == [
        ("coins", 200, None),
        ("consumable", 1, "growth_charge_grand"),
    ]
    assert [grant_signature(item) for item in catalog.ACHIEVEMENTS_BY_ID["ancient_garden"].rewards] == [
        ("cosmetic", 1, "golden_trowel"),
    ]
    all_due = catalog.ACHIEVEMENTS_BY_ID["all_due_done"]
    assert all_due.evaluation_mode is catalog.AchievementEvaluationMode.LIVE_ONLY
    assert all_due.historical_backfill is False


def test_cosmetic_bed_landmark_and_mastery_spend_catalogs_are_exact() -> None:
    assert {
        item.cosmetic_id.value: (item.price_coins, item.source_achievement_id)
        for item in catalog.COSMETICS
    } == {
        "botanists_plaque": (None, catalog.AchievementId.BOTANICAL_COLLECTION),
        "garden_journal": (None, catalog.AchievementId.YEAR_OF_HARVESTS),
        "golden_trowel": (None, catalog.AchievementId.ANCIENT_GARDEN),
    }
    assert [
        (item.bed_number, item.included, item.source_achievement_id)
        for item in catalog.BED_UNLOCKS
    ] == [
        (1, True, None),
        (2, True, None),
        (3, False, catalog.AchievementId.FIRST_CANOPY),
        (4, False, catalog.AchievementId.FIRST_FULL_BLOOM),
        (5, False, catalog.AchievementId.GROWING_GARDEN),
        (6, False, catalog.AchievementId.FLOURISHING_GARDEN),
    ]
    assert [
        (
            item.landmark_id.value,
            item.growth_cost,
            item.cumulative_growth_threshold,
            item.coin_cost,
        )
        for item in catalog.LANDMARKS
    ] == [
        ("mossy_stone_path", 25_000, 25_000, 250),
        ("birdbath_terrace", 75_000, 100_000, 350),
        ("lily_pond", 175_000, 275_000, 550),
        ("wooden_footbridge", 350_000, 625_000, 800),
        ("garden_pergola", 650_000, 1_275_000, 1_200),
        ("glasshouse_conservatory", 1_200_000, 2_475_000, 2_000),
    ]
    assert [
        (
            item.rank_id.value,
            item.growth_cost,
            item.cumulative_growth_threshold,
            item.coin_cost,
        )
        for item in catalog.MASTERY_RANKS
    ] == [
        ("bronze", 25_000, 25_000, 50),
        ("silver", 50_000, 75_000, 100),
        ("gold", 100_000, 175_000, 200),
        ("iridescent", 200_000, 375_000, 400),
    ]


def test_user_facing_economy_metadata_is_catalog_owned_and_valid() -> None:
    from ankigarden.ui.economy_presenters import (
        catalog_item_projections,
        coin_reward_receipt,
    )
    from scripts.validate_economy_catalog import validate_catalog_integrity

    assert (
        catalog.DAILY_ACTIVITY_COINS,
        catalog.ALL_DUE_BASE_COINS,
    ) == (4, 16)
    first_card = coin_reward_receipt(catalog.CoinSourceId.FIRST_ELIGIBLE_ANSWER)
    assert (first_card.display_name, first_card.title, first_card.detail) == (
        "First card",
        "First card",
        "First card today",
    )
    assert not any(
        "eligible" in f"{item.effect_description} {item.acquisition_route}".casefold()
        for item in catalog_item_projections()
        if item.category != "cosmetic"
    )
    assert (
        catalog.GARDEN_LEGACY.legacy_id,
        catalog.GARDEN_LEGACY.growth_cost_per_level,
        catalog.GARDEN_LEGACY.coin_cost,
        catalog.GARDEN_LEGACY.asset_id,
    ) == ("garden_legacy", 500_000, 0, "cosmetic_botanists_plaque")
    assert catalog.CONSUMABLE_BY_ID["fertilizer_premium"].display_name == (
        "Magical Fertilizer"
    )
    assert validate_catalog_integrity()["status"] == "pass"


def test_compatibility_aliases_and_environment_lookup_are_stable() -> None:
    assert catalog.canonical_stage_id("rare") == "full_bloom"
    assert catalog.canonical_stage_id("Full Bloom") == "full_bloom"
    assert catalog.canonical_garden_feature_id("gentle_rain") == "watering_station"
    assert catalog.canonical_environment_kind("weather") == "garden_feature"
    assert catalog.environment_item("weather", "breeze") is catalog.GARDEN_BONUS_BY_ID["wind_chime"]
    assert catalog.WEATHER_CATALOG is catalog.GARDEN_FEATURE_CATALOG
    assert catalog.STAGE_CURRENCY["rare"] == 50
    assert catalog.STAGE_REWARD_SPLITS["rare"] == (10, 10, 10, 20)


def test_catalog_registries_are_immutable_and_validation_rejects_drift() -> None:
    with pytest.raises(TypeError):
        catalog.SPECIES_BY_ID["new_plant"] = catalog.SPECIES[0]
    with pytest.raises(FrozenInstanceError):
        catalog.STAGES[0].threshold_growth = 1

    catalog.validate_balance_catalog()
    with pytest.raises(ValueError, match="stage thresholds or rewards drifted"):
        catalog.validate_balance_catalog(
            replace(
                catalog.CATALOG,
                stages=(replace(catalog.STAGES[0], threshold_growth=1), *catalog.STAGES[1:]),
            )
        )
    with pytest.raises(ValueError, match="Standard Finds must be uncapped"):
        catalog.validate_balance_catalog(
            replace(
                catalog.CATALOG,
                standard_find_daily_cap_bands=(
                    replace(catalog.STANDARD_FIND_DAILY_CAP_BANDS[0], cap=4),
                    *catalog.STANDARD_FIND_DAILY_CAP_BANDS[1:],
                ),
            )
        )
    with pytest.raises(ValueError, match="Landmark spend costs drifted"):
        catalog.validate_balance_catalog(
            replace(
                catalog.CATALOG,
                landmarks=(replace(catalog.LANDMARKS[0], growth_cost=24_999), *catalog.LANDMARKS[1:]),
            )
        )


def test_catalog_snapshot_is_deterministic_json_safe_and_detached() -> None:
    first = catalog.catalog_snapshot()
    second = catalog.catalog_snapshot()
    assert first == second
    encoded = json.dumps(first, sort_keys=True, separators=(",", ":"))
    assert '"catalog_version":"2.2.0"' in encoded
    assert first["standard_find_daily_cap_bands"] == [
        {"minimum_answers_today": 0, "maximum_answers_today": None, "cap": None},
    ]
    first["catalog_version"] = "changed"
    assert catalog.CATALOG.catalog_version == "2.2.0"
    assert catalog.catalog_snapshot()["catalog_version"] == "2.2.0"


def test_catalog_module_has_no_project_layer_imports() -> None:
    source_path = Path(catalog.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "balance_catalog must not use project-relative imports"
            if node.module:
                imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots <= {
        "__future__",
        "collections",
        "dataclasses",
        "enum",
        "re",
        "types",
        "typing",
    }


def test_dynamic_helpers_reject_invalid_counts() -> None:
    with pytest.raises(ValueError):
        catalog.standard_find_daily_cap(-1)
    with pytest.raises(TypeError):
        catalog.standard_find_daily_cap(True)
    with pytest.raises(ValueError):
        catalog.standard_find_schedule_band(0)
