from __future__ import annotations

import re
from pathlib import Path

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.collectibles import (
    collectible_registry,
    collectible_views,
    collection_categories,
    environment_discovery_progress,
)
from ankigarden.environment import (
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
)
from ankigarden.garden_finds import ultra_denominator
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    ActivePlantPeriod,
    DailyStats,
    GardenLoadoutState,
    GardenState,
    Plant,
    STATE_VERSION,
)
from ankigarden.purchases import compact_duration
from ankigarden.storage import DueObligationStatus, migrate_modern_state


class FakeConfig:
    def __init__(self) -> None:
        self.data = dict(DEFAULT_CONFIG)

    def value(self, key: str, default=None):
        return self.data.get(key, default)

    def nested(self, *keys: str, default=None):
        node = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class FakeStorage:
    def __init__(self) -> None:
        self.day = "2026-08-08"
        self.day_start_ms = 1_786_100_000_000
        self.now_ms = 1_786_150_000_000
        self.state = GardenState(
            plants=[
                Plant("p1", "bonsai", "Bonsai Plant", 0),
                Plant("p2", "rose", "Rose Plant", 1),
            ],
            active_plant_id="p1",
            daily_stats=DailyStats(day=self.day),
            last_active_day="2026-08-06",
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.now_ms - 10_000)
            ],
            reward_seed="test-environment-reward-seed",
        )
        self.addon_dir = Path(__file__).resolve().parents[1] / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.save_count = 0
        self.fail_save = False

    def save(self) -> None:
        self.save_count += 1
        if self.fail_save:
            raise OSError("disk full")

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return DueObligationStatus()

    def load_asset_metadata(self) -> dict:
        return {}

    def save_asset_metadata(self, _data) -> None:
        return None


def make_engine() -> tuple[GardenGameEngine, FakeStorage]:
    storage = FakeStorage()
    return GardenGameEngine(FakeConfig(), storage), storage


def answer(
    engine: GardenGameEngine,
    storage: FakeStorage,
    *,
    revlog_id: int = 0,
):
    storage.now_ms += 1_000
    stable_id = revlog_id or storage.now_ms
    return engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": stable_id,
        "answered_at_ms": stable_id,
    })


def own_and_equip(
    engine: GardenGameEngine,
    *,
    weather: str | None = None,
    scenery: str | None = None,
) -> None:
    if weather is not None:
        if weather not in engine.state.inventory["weather"]:
            engine.state.inventory["weather"].append(weather)
        engine.state.selected_weather = weather
    if scenery is not None:
        if scenery not in engine.state.inventory["scenery"]:
            engine.state.inventory["scenery"].append(scenery)
        engine.state.selected_background = scenery


def assert_concise_player_copy(message: str) -> None:
    normalized = str(message).lower()
    assert "all clear" not in normalized
    assert "required card" not in normalized
    assert re.search(r"\b\d[\d,]*\s+answers?\b", normalized) is None


def test_catalog_prices_tiers_charges_and_ultra_pity_match_the_product_contract():
    assert STATE_VERSION == 23
    assert {item_id: item.price for item_id, item in WEATHER_CATALOG.items()} == {
        "seedling_sign": None,
        "wind_chime": 100,
        "harvest_bell": 175,
        "watering_station": 250,
        "herbalist_hourglass": 350,
        "firefly_lantern": None,
        "prism_trellis": None,
    }
    assert {item_id: item.price for item_id, item in SCENERY_CATALOG.items()} == {
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
    assert {
        charge_id: (spec.growth, spec.price)
        for charge_id, spec in GROWTH_CHARGES.items()
    } == {
        "growth_charge_small": (100, 30),
        "growth_charge_standard": (500, 125),
        "growth_charge_grand": (2_000, None),
    }
    assert [
        ultra_denominator(value)
        for value in (0, 24_999, 49_999, 50_000)
    ] == [25_000, 25_000, 25_000, 25_000]
    assert [key for key, _label in collection_categories()] == [
        "plants", "scenery", "garden_features", "decorations", "garden_beds", "growth_items"
    ]
    registry = collectible_registry()
    bed = next(
        item for item in registry if item.item_id == "garden_beds:0"
    )
    assert "Each planted plant adds a 20% Shared Growth share" in bed.descriptor.buff
    assert "reaches Full Bloom" in bed.descriptor.buff
    booster = next(
        item for item in registry
        if item.item_id == "growth_items:booster_potion"
    )
    compost = next(
        item for item in registry
        if item.item_id == "growth_items:fertilizer_basic"
    )
    basic_fertilizer = GardenGameEngine.FERTILIZERS["basic"]
    assert compost.name == "Rich Compost"
    assert compost.source_id == "fertilizer_basic"
    assert compost.rarity == "Rare"
    assert (
        f"+{basic_fertilizer.growth_per_answer:,} Growth"
        in compost.descriptor.buff
    )
    assert compost.descriptor.duration == compact_duration(
        basic_fertilizer.duration_seconds
    )
    assert compost.descriptor.unlock_requirement == "Found while reviewing."
    compost_view = next(
        view
        for view in collectible_views(GardenState(
            consumables={"fertilizer_basic": 2},
        ))
        if view.definition.item_id == "growth_items:fertilizer_basic"
    )
    assert compost_view.owned
    assert compost_view.quantity == 2
    assert booster.descriptor.unlock_requirement == (
        "Earn from a Garden Find or Scenery reward."
    )
    assert booster.descriptor.buff == (
        f"+{GardenGameEngine.BOOSTER_GROWTH_PER_ANSWER:,} Growth per card."
    )
    assert (
        f"{GardenGameEngine.BOOSTER_CARD_COUNT:,} cards"
        in booster.descriptor.duration
    )
    assert "Purchase" not in booster.descriptor.unlock_requirement
    assert all(
        item.mystery == (
                item.category in {"garden_features", "scenery"}
            and item.source_id in {
                key for catalog in (WEATHER_CATALOG, SCENERY_CATALOG)
                for key, catalog_item in catalog.items() if catalog_item.drop_only
            }
        )
        for item in registry
    )


def test_collection_projects_finite_environment_guarantees_and_completed_tiers():
    state = GardenState(
        environment_pity_misses={
            "rare": 1_234,
            "very_rare": 19_999,
            "ultra": 999_999,
        },
        inventory={
            "pots": ["ceramic_minimal"],
            "weather": ["sunny", "fireflies", "rainbow_sunshower"],
            "scenery": ["default", "halloween"],
            "decorations": ["lantern"],
        },
    )

    rare, very_rare, ultra = environment_discovery_progress(state)

    assert (rare.label, rare.base_denominator, rare.hard_guarantee_cards) == (
        "Rare",
        2_500,
        5_000,
    )
    assert rare.progress_cards == 1_234
    assert rare.cards_until_guaranteed == 3_766
    assert rare.progress_value_text == "1,234 of 5,000 cards"
    assert rare.base_chance_text == "Base chance: 1 in 2,500 per card"
    assert rare.guarantee_text == (
        "Next Rare discovery guaranteed within 3,766 cards"
    )
    assert not rare.completed
    assert (rare.collected_items, rare.total_items) == (1, 2)

    assert very_rare.completed
    assert very_rare.completion_text == "All Very Rare discoveries collected"
    assert (very_rare.collected_items, very_rare.total_items) == (2, 2)

    assert ultra.progress_cards == 49_999
    assert ultra.cards_until_guaranteed == 1
    assert ultra.guarantee_text == (
        "Next Ultra discovery guaranteed within 1 card"
    )
    assert not ultra.completed


def test_collection_marks_each_environment_tier_complete_without_a_pending_roll():
    state = GardenState(
        environment_pity_misses={
            "rare": 4_999,
            "very_rare": 19_999,
            "ultra": 49_999,
        },
        inventory={
            "pots": ["ceramic_minimal"],
            "weather": ["sunny", "fireflies", "rainbow_sunshower"],
            "scenery": [
                "default",
                "rainbow_horizon",
                "halloween",
                "full_moon",
                "eclipse",
            ],
            "decorations": ["lantern"],
        },
    )

    tiers = environment_discovery_progress(state)

    assert [tier.label for tier in tiers] == ["Rare", "Very Rare", "Ultra"]
    assert all(tier.completed for tier in tiers)
    assert [tier.completion_text for tier in tiers] == [
        "All Rare discoveries collected",
        "All Very Rare discoveries collected",
        "All Ultra discoveries collected",
    ]


def test_environment_state_round_trip_preserves_entitlements_loadout_visibility_and_pity():
    state = GardenState(
        loadout=GardenLoadoutState(
            scenery_id="full_moon",
            weather_id="fireflies",
            decoration_id="lantern",
            visibility={"weather": False, "scenery": True},
        ),
        inventory={
            "pots": ["ceramic_minimal"],
            "scenery": ["default", "full_moon"],
            "decorations": ["lantern"],
            "weather": ["sunny", "fireflies"],
        },
        eligible_reward_count=123,
        ultra_pity_misses=45_678,
        daily_environment_claims={"full_moon": "2026-08-08"},
        consumables={
            "booster_potion": 2,
            "growth_charge_small": 3,
            "growth_charge_standard": 4,
            "growth_charge_grand": 5,
        },
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.selected_background == "full_moon"
    assert restored.selected_garden_feature == "firefly_lantern"
    assert restored.inventory["scenery"] == ["default", "full_moon"]
    assert restored.eligible_reward_count == 123
    assert restored.ultra_pity_misses == 45_678
    assert restored.daily_environment_claims == {"full_moon": "2026-08-08"}
    assert restored.environment_visibility == {
        "garden_feature": False, "weather": False, "scenery": True
    }
    assert restored.loadout.decoration_id == "lantern"
    assert "equipped" not in restored.to_dict()
    assert "backgrounds" not in restored.inventory
    assert restored.consumables["growth_charge_grand"] == 5


def test_schema15_migration_adds_environment_fields_without_losing_existing_state():
    payload = GardenState(
        currency_balance=777,
        loadout=GardenLoadoutState(weather_id="breeze"),
        inventory={
            "pots": ["ceramic_minimal"],
            "scenery": ["default"],
            "decorations": ["lantern"],
            "weather": ["sunny", "breeze"],
        },
    ).to_dict()
    payload["version"] = 15
    payload.pop("loadout", None)
    payload["selected_weather"] = "breeze"
    for key in (
        "eligible_reward_count",
        "ultra_pity_misses",
        "daily_environment_claims",
        "environment_visibility",
    ):
        payload.pop(key, None)
    payload["consumables"] = {"booster_potion": 2}

    restored = migrate_modern_state(payload)

    assert restored.currency_balance == 777
    assert restored.selected_garden_feature == "wind_chime"
    assert restored.inventory["scenery"] == ["default"]
    assert restored.eligible_reward_count == 0
    assert restored.ultra_pity_misses == 0
    assert restored.environment_visibility == {
        "garden_feature": True, "weather": True, "scenery": True
    }
    assert restored.consumables == {
        "booster_potion": 2,
        "fertilizer_basic": 0,
        "fertilizer_quality": 0,
        "fertilizer_premium": 0,
        "growth_charge_small": 0,
        "growth_charge_standard": 0,
        "growth_charge_grand": 0,
    }


def test_one_time_purchase_does_not_auto_equip_and_hidden_visual_keeps_passive():
    engine, storage = make_engine()
    storage.state.currency_balance = 500

    ok, _message = engine.purchase_environment("weather", "breeze")

    assert ok
    assert "breeze" in storage.state.inventory["weather"]
    assert storage.state.selected_garden_feature == "seedling_sign"
    assert storage.state.currency_balance == 400
    assert not engine.purchase_environment("weather", "breeze")[0]
    assert engine.equip_environment("weather", "breeze")[0]
    assert engine.set_environment_visibility("weather", False)[0]
    award = answer(engine, storage)
    assert award.weather_growth == 1
    assert award.total_growth == 11
    assert engine.resolve_garden_feature_asset() is None


def test_first_progress_event_locks_mechanics_and_later_equips_queue_for_tomorrow():
    engine, storage = make_engine()
    storage.state.inventory["weather"].extend(["breeze", "gentle_rain"])
    storage.state.inventory["scenery"].extend(["spring", "summer"])
    assert engine.apply_environment_loadout("breeze", "spring")[0]

    first = answer(engine, storage)
    locked_at = storage.state.daily_loadout.locked_at_ms
    ok, message = engine.apply_environment_loadout("gentle_rain", "summer")
    second = answer(engine, storage)

    assert first.weather_growth == second.weather_growth == 1
    assert first.scenery_growth == second.scenery_growth == 1
    assert locked_at > 0
    assert engine.locked_environment_id("garden_feature") == "wind_chime"
    assert engine.locked_environment_id("scenery") == "spring"
    assert ok
    assert "next anki day" in message.lower() or "tomorrow" in message.lower()
    assert_concise_player_copy(message)
    assert storage.state.daily_loadout.pending_garden_feature_id == "watering_station"
    assert storage.state.daily_loadout.queued_scenery_id == "summer"

    engine.end_review_session()
    engine.begin_review_session()
    assert storage.state.selected_garden_feature == "watering_station"

    storage.day = "2026-08-09"
    storage.day_start_ms += 86_400_000
    storage.now_ms += 86_400_000
    engine.rollover_if_needed()

    assert storage.state.selected_background == "summer"
    assert storage.state.daily_loadout.locked_at_ms == 0


def test_growth_charge_does_not_create_a_review_session_feature_snapshot():
    engine, storage = make_engine()
    storage.state.inventory["weather"].extend(["breeze", "gentle_rain"])
    assert engine.equip_environment("weather", "breeze")[0]
    storage.state.consumables["growth_charge_small"] = 1

    assert engine.use_growth_charge("growth_charge_small")[0]
    ok, message = engine.equip_environment("weather", "gentle_rain")

    assert storage.state.daily_loadout.locked_at_ms > 0
    assert engine.locked_environment_id("garden_feature") == "watering_station"
    assert ok
    assert storage.state.daily_loadout.pending_garden_feature_id == ""
    assert_concise_player_copy(message)


def test_weather_and_scenery_review_passives_stack_and_stop_at_their_exact_limits():
    engine, storage = make_engine()
    own_and_equip(engine, weather="breeze", scenery="spring")

    awards = [answer(engine, storage) for _ in range(26)]

    assert awards[0].total_growth == 12
    assert awards[9].total_growth == 12
    assert awards[10].total_growth == 11
    assert awards[24].total_growth == 11
    assert awards[25].total_growth == 10
    assert storage.state.daily_stats.weather_growth == 10
    assert storage.state.daily_stats.scenery_growth == 25


def test_secondary_growth_is_flat_and_never_multiplies_other_bonuses():
    engine, storage = make_engine()
    own_and_equip(engine, weather="fireflies", scenery="eclipse")

    awards = [answer(engine, storage) for _ in range(101)]

    assert awards[0].base_growth == 10
    assert awards[0].weather_growth == 5
    assert awards[0].scenery_growth == 2
    assert awards[0].total_growth == 17
    assert awards[14].weather_growth == 5
    assert awards[15].weather_growth == 0
    assert awards[15].scenery_growth == 2
    assert awards[15].total_growth == 12
    assert awards[99].scenery_growth == 2
    assert awards[100].scenery_growth == 0
    assert awards[100].total_growth == 10


@pytest.mark.parametrize(
    ("scenery", "expected"),
    (("rainbow_horizon", (11, 11)), ("summer", (10, 11))),
)
def test_every_answer_and_every_second_answer_scenery_passives(
    scenery: str, expected: tuple[int, int]
):
    engine, storage = make_engine()
    own_and_equip(engine, scenery=scenery)
    assert (answer(engine, storage).total_growth, answer(engine, storage).total_growth) == expected


def test_todays_cards_environment_rewards_use_locked_mechanics_and_normal_accounting():
    cloudy, cloudy_storage = make_engine()
    own_and_equip(cloudy, weather="cloudy")
    assert cloudy.observe_due_start(DueObligationStatus(review_count=1))
    answer(cloudy, cloudy_storage)
    ok, message = cloudy.evaluate_today_cards(DueObligationStatus())
    assert ok
    assert cloudy_storage.state.currency_balance == 22
    assert "today’s cards" in message.lower()
    assert_concise_player_copy(message)

    rainbow, rainbow_storage = make_engine()
    own_and_equip(rainbow, weather="rainbow_sunshower")
    assert rainbow.observe_due_start(DueObligationStatus(review_count=1))
    answer(rainbow, rainbow_storage)
    rainbow_storage.state.plants[0].growth_points = 499
    before = rainbow_storage.state.plants[0].growth_points
    ok, message = rainbow.evaluate_today_cards(DueObligationStatus())
    assert ok
    assert rainbow_storage.state.plants[0].growth_points == before + 100
    assert rainbow_storage.state.daily_stats.direct_reward_growth == 100
    assert rainbow_storage.state.currency_balance == 19
    assert rainbow.peek_stage_transitions()[0].source == "all_due"
    assert_concise_player_copy(message)


def test_autumn_carries_fractional_bonus_across_checkpoint_payouts():
    engine, storage = make_engine()
    own_and_equip(engine, scenery="autumn")
    plant = storage.state.plants[0]
    for before in (124, 249, 374, 499):
        plant.growth_points = before
        answer(engine, storage)

    milestone_payouts = [
        tx.delta for tx in storage.state.currency_transactions
        if tx.event_key.startswith("stage")
    ]
    assert milestone_payouts == [1, 2, 1, 3]
    assert sum(milestone_payouts) == 7
    assert storage.state.checkpoint_coin_carry_units == 50


def test_growth_charges_purchase_apply_transitions_without_losing_overflow():
    engine, storage = make_engine()
    storage.state.currency_balance = 100
    own_and_equip(engine, scenery="autumn")
    plant = storage.state.plants[0]
    plant.growth_points = 490

    assert engine.purchase_growth_charge("growth_charge_small")[0]
    assert storage.state.currency_balance == 70
    ok, message = engine.use_growth_charge("growth_charge_small")
    assert ok
    assert "100 Growth" in message
    assert plant.growth_points == 590
    assert storage.state.daily_stats.charge_growth == 100
    assert storage.state.currency_balance == 73

    plant.growth_points = 49_950
    continuation = storage.state.plants[1]
    storage.state.consumables["growth_charge_small"] = 1
    assert engine.use_growth_charge("growth_charge_small")[0]
    assert plant.growth_points == 50_000
    assert continuation.growth_points == 50
    assert storage.state.active_plant_id == continuation.plant_id
    assert storage.state.consumables["growth_charge_small"] == 1
    grand_purchase = engine.purchase_growth_charge("growth_charge_grand")
    assert not grand_purchase[0]
    assert grand_purchase[1] == "This item is unavailable right now."


def test_equipped_weather_and_scenery_extend_booster_card_count_additively():
    engine, storage = make_engine()
    own_and_equip(engine, weather="snow_flurry", scenery="full_moon")
    storage.state.consumables["booster_potion"] = 1
    assert engine.use_booster_potion()[0]

    batch = storage.state.plants[0].booster_card_batches[0]
    assert batch.total_cards == batch.remaining_cards == 135


def test_todays_cards_scenery_gift_is_independent_of_capped_find_pools():
    engine, storage = make_engine()
    engine.initialize_reward_state()
    own_and_equip(engine, scenery="snowy")
    storage.state.garden_find_daily_counts[storage.day] = 3
    storage.state.garden_find_drought_count = 40
    first_id = storage.now_ms + 1_000

    assert storage.state.daily_environment_claims == {}
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage, revlog_id=first_id)

    assert storage.state.daily_environment_claims == {}
    assert storage.state.consumables["growth_charge_small"] == 0
    assert storage.state.garden_find_drought_count == 40
    first_outcomes = list(storage.state.garden_find_outcomes.values())
    assert len(first_outcomes) == 2
    assert next(
        outcome for outcome in first_outcomes if outcome.pool_id == "standard"
    ).status == "paused"
    assert any(outcome.pool_id == "environment" for outcome in first_outcomes)

    ok, message = engine.evaluate_today_cards(DueObligationStatus())
    assert ok
    assert "today’s cards" in message.lower()
    assert_concise_player_copy(message)
    assert storage.state.daily_environment_claims == {"snowy": storage.day}
    assert storage.state.consumables["growth_charge_small"] == 1
    assert storage.state.garden_find_drought_count == 40
    assert len(storage.state.garden_find_outcomes) == 2


def test_environment_purchase_and_growth_charge_use_restore_state_on_save_failure():
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    storage.fail_save = True

    assert not engine.purchase_environment("weather", "breeze")[0]
    assert storage.state.currency_balance == 500
    assert "breeze" not in storage.state.inventory["weather"]

    storage.state.consumables["growth_charge_small"] = 1
    before = storage.state.plants[0].growth_points
    assert not engine.use_growth_charge("growth_charge_small")[0]
    assert storage.state.plants[0].growth_points == before
    assert storage.state.consumables["growth_charge_small"] == 1




def test_every_scenery_resolves_its_own_art_with_shared_surface_geometry():
    engine, _storage = make_engine()
    base = engine.resolve_scenery_preview_asset("default")
    assert base is not None
    base_placement = base.placement.to_dict()
    base_profile = base_placement["surface_profile"]

    for item_id in SCENERY_CATALOG:
        asset = engine.resolve_scenery_preview_asset(item_id)
        assert asset is not None
        placement = asset.placement.to_dict()
        profile = placement["surface_profile"]
        assert profile["geometry_version"] == 6
        if item_id == "autumn":
            base_house = next(
                landmark
                for landmark in base_profile["landmarks"]
                if landmark["landmark_id"] == "garden_house"
            )
            house = next(
                landmark
                for landmark in profile["landmarks"]
                if landmark["landmark_id"] == "garden_house"
            )
            nursery = next(
                landmark
                for landmark in profile["landmarks"]
                if landmark["landmark_id"] == "nursery_entrance"
            )
            base_nursery = next(
                landmark
                for landmark in base_profile["landmarks"]
                if landmark["landmark_id"] == "nursery_entrance"
            )
            assert nursery == base_nursery
            assert house["action_id"] == base_house["action_id"]
            assert set(house["variants"]) == {"4:3", "16:9", "home"}
            assert all(
                len(geometry["outline_paths"][0]) == 11
                for geometry in house["variants"].values()
            )
        else:
            assert profile["landmarks"] == base_profile["landmarks"]
        for variant_name, variant in profile["variants"].items():
            base_variant = base_profile["variants"][variant_name]
            assert variant["surfaces"] == base_variant["surfaces"]
            assert (variant["width"], variant["height"]) == (
                base_variant["width"], base_variant["height"]
            )
            if item_id == "default":
                assert "verdant_twilight" in variant["file"]
            else:
                assert f"backgrounds/{item_id}/" in variant["file"]
                assert f"backgrounds/{item_id}/" in variant["occlusion_file"]
