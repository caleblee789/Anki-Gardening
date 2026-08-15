from __future__ import annotations

from pathlib import Path

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.environment import (
    DROP_BANDS,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    ultra_denominator,
)
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    ActivePlantPeriod,
    DailyStats,
    GardenState,
    Plant,
    STATE_VERSION,
)
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
    return engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": revlog_id,
        "answered_at_ms": revlog_id or storage.now_ms,
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
        engine.state.equipped["weather"] = weather
    if scenery is not None:
        for key in ("backgrounds", "scenery"):
            if scenery not in engine.state.inventory[key]:
                engine.state.inventory[key].append(scenery)
        engine.state.selected_background = scenery
        engine.state.equipped["background"] = scenery


def test_catalog_prices_tiers_charges_and_ultra_pity_match_the_product_contract():
    assert STATE_VERSION == 16
    assert {item_id: item.price for item_id, item in WEATHER_CATALOG.items()} == {
        "sunny": None,
        "breeze": 100,
        "cloudy": 175,
        "gentle_rain": 250,
        "snow_flurry": 350,
        "fireflies": None,
        "rainbow_sunshower": None,
    }
    assert {item_id: item.price for item_id, item in SCENERY_CATALOG.items()} == {
        "default": None,
        "spring": 400,
        "summer": 600,
        "autumn": 800,
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
    assert [(band.tier, band.denominator) for band in DROP_BANDS] == [
        ("ultra_environment", 100_000),
        ("grand_charge", 30_000),
        ("very_rare_environment", 20_000),
        ("standard_charge", 8_000),
        ("rare_environment", 5_000),
        ("booster_potion", 5_000),
        ("small_charge", 2_000),
        ("coin_cache", 800),
    ]
    assert [
        ultra_denominator(value)
        for value in (0, 74_999, 75_000, 84_999, 85_000, 94_999,
                      95_000, 104_999, 105_000, 114_999, 115_000)
    ] == [100_000, 100_000, 90_000, 90_000, 80_000, 80_000,
          70_000, 70_000, 60_000, 60_000, 50_000]


def test_environment_state_round_trip_preserves_entitlements_loadout_visibility_and_pity():
    state = GardenState(
        selected_background="full_moon",
        selected_weather="fireflies",
        inventory={
            "pots": ["ceramic_minimal"],
            "backgrounds": ["default", "full_moon"],
            "scenery": ["default", "full_moon"],
            "decorations": ["lantern"],
            "weather": ["sunny", "fireflies"],
        },
        eligible_reward_count=123,
        ultra_pity_misses=45_678,
        daily_environment_claims={"full_moon": "2026-08-08"},
        environment_visibility={"weather": False, "scenery": True},
        consumables={
            "booster_potion": 2,
            "growth_charge_small": 3,
            "growth_charge_standard": 4,
            "growth_charge_grand": 5,
        },
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.selected_background == "full_moon"
    assert restored.selected_weather == "fireflies"
    assert restored.inventory["scenery"] == ["default", "full_moon"]
    assert restored.eligible_reward_count == 123
    assert restored.ultra_pity_misses == 45_678
    assert restored.daily_environment_claims == {"full_moon": "2026-08-08"}
    assert restored.environment_visibility == {"weather": False, "scenery": True}
    assert restored.consumables["growth_charge_grand"] == 5


def test_schema15_migration_adds_environment_fields_without_losing_existing_state():
    payload = GardenState(
        currency_balance=777,
        selected_weather="breeze",
        inventory={
            "pots": ["ceramic_minimal"],
            "backgrounds": ["default"],
            "decorations": ["lantern"],
            "weather": ["sunny", "breeze"],
        },
    ).to_dict()
    payload["version"] = 15
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
    assert restored.selected_weather == "breeze"
    assert restored.inventory["scenery"] == ["default"]
    assert restored.eligible_reward_count == 0
    assert restored.ultra_pity_misses == 0
    assert restored.environment_visibility == {"weather": True, "scenery": True}
    assert restored.consumables == {
        "booster_potion": 2,
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
    assert storage.state.selected_weather == "sunny"
    assert storage.state.currency_balance == 400
    assert not engine.purchase_environment("weather", "breeze")[0]
    assert engine.equip_environment("weather", "breeze")[0]
    assert engine.set_environment_visibility("weather", False)[0]
    award = answer(engine, storage)
    assert award.weather_growth == 1
    assert award.total_growth == 11
    assert engine.resolve_weather_asset() is None


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

    first = answer(engine, storage)
    for _ in range(4):
        answer(engine, storage)
    sixth = answer(engine, storage)

    assert first.base_growth == 10
    assert first.weather_growth == 5
    assert first.scenery_growth == 10
    assert first.total_growth == 25
    assert sixth.weather_growth == 0
    assert sixth.scenery_growth == 10
    assert sixth.total_growth == 20


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


def test_all_due_weather_rewards_are_small_and_use_normal_growth_accounting():
    cloudy, cloudy_storage = make_engine()
    own_and_equip(cloudy, weather="cloudy")
    answer(cloudy, cloudy_storage)
    ok, message = cloudy.evaluate_all_due(DueObligationStatus())
    assert ok
    assert cloudy_storage.state.currency_balance == 12
    assert "12 Garden Coins" in message

    rainbow, rainbow_storage = make_engine()
    own_and_equip(rainbow, weather="rainbow_sunshower")
    answer(rainbow, rainbow_storage)
    before = rainbow_storage.state.plants[0].growth_points
    ok, message = rainbow.evaluate_all_due(DueObligationStatus())
    assert ok
    assert rainbow_storage.state.plants[0].growth_points == before + 5
    assert rainbow_storage.state.daily_stats.weather_growth == 5
    assert rainbow_storage.state.currency_balance == 10
    assert "5 Growth" in message


def test_autumn_rounds_stage_coin_bonus_half_up():
    engine, storage = make_engine()
    own_and_equip(engine, scenery="autumn")
    storage.state.plants[0].growth_points = 490

    award = answer(engine, storage)

    assert award.total_growth == 10
    assert storage.state.plants[0].growth_stage == "sprout"
    assert storage.state.currency_balance == 6


def test_growth_charges_purchase_apply_normal_transitions_cap_at_rare_and_fail_safely():
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
    assert storage.state.currency_balance == 76

    plant.growth_points = 49_950
    storage.state.consumables["growth_charge_small"] = 1
    assert engine.use_growth_charge("growth_charge_small")[0]
    assert plant.growth_points == 50_000
    assert storage.state.consumables["growth_charge_small"] == 0
    storage.state.consumables["growth_charge_small"] = 1
    assert not engine.use_growth_charge("growth_charge_small")[0]
    assert storage.state.consumables["growth_charge_small"] == 1
    assert not engine.purchase_growth_charge("growth_charge_grand")[0]


def test_equipped_weather_and_scenery_extend_booster_duration_additively(monkeypatch):
    engine, storage = make_engine()
    own_and_equip(engine, weather="snow_flurry", scenery="full_moon")
    storage.state.consumables["booster_potion"] = 1
    monkeypatch.setattr(engine, "_now_seconds", lambda: 1_000.0)

    assert engine.use_booster_potion()[0]

    assert storage.state.plants[0].booster is not None
    assert storage.state.plants[0].booster.expires_at == 10_720.0


def test_daily_scenery_gift_uses_the_reward_slot_and_does_not_backfill_without_an_answer(monkeypatch):
    engine, storage = make_engine()
    own_and_equip(engine, scenery="snowy")
    monkeypatch.setattr(engine, "_drop_hit", lambda *_args: True)
    first_id = storage.now_ms + 1_000

    assert storage.state.daily_environment_claims == {}
    answer(engine, storage, revlog_id=first_id)

    assert storage.state.daily_environment_claims == {"snowy": storage.day}
    assert storage.state.consumables["growth_charge_small"] == 1
    assert [drop.kind for drop in storage.state.reward_drop_history] == [
        "growth_charge_small"
    ]
    assert storage.state.ultra_pity_misses == 1

    answer(engine, storage, revlog_id=first_id + 1_000)
    assert len(storage.state.reward_drop_history) == 2
    assert storage.state.reward_drop_history[-1].kind in {"full_moon", "eclipse"}
    assert storage.state.ultra_pity_misses == 0


@pytest.mark.parametrize(
    ("roll", "expected"),
    ((0, "growth_charge_small"), (70, "growth_charge_standard"), (95, "booster_potion")),
)
def test_halloween_daily_gift_uses_the_exact_70_25_5_split(
    monkeypatch, roll: int, expected: str
):
    engine, storage = make_engine()
    own_and_equip(engine, scenery="halloween")
    monkeypatch.setattr(
        engine,
        "_reward_digest",
        lambda *_args, **_kwargs: int(roll).to_bytes(8, "big") + bytes(24),
    )

    assert engine._claim_daily_environment_gift(123, plant=storage.state.plants[0])
    assert storage.state.consumables[expected] == 1


def test_drop_engine_checks_ultra_first_grants_one_band_and_uses_completion_fallbacks(monkeypatch):
    engine, storage = make_engine()
    monkeypatch.setattr(engine, "_drop_hit", lambda *_args: True)

    answer(engine, storage, revlog_id=storage.now_ms + 1_000)
    first_kind = storage.state.reward_drop_history[-1].kind
    assert first_kind in {"full_moon", "eclipse"}
    assert storage.state.ultra_pity_misses == 0
    assert sum(
        engine.owns_environment("scenery", item_id)
        for item_id in ("full_moon", "eclipse")
    ) == 1

    answer(engine, storage, revlog_id=storage.now_ms + 2_000)
    assert sum(
        engine.owns_environment("scenery", item_id)
        for item_id in ("full_moon", "eclipse")
    ) == 2
    answer(engine, storage, revlog_id=storage.now_ms + 3_000)
    assert storage.state.reward_drop_history[-1].kind == "growth_charge_grand"
    assert storage.state.consumables["growth_charge_grand"] == 1
    assert len(storage.state.reward_drop_history) == 3


def test_rare_completion_falls_back_to_standard_charge(monkeypatch):
    engine, storage = make_engine()
    own_and_equip(engine, weather="fireflies", scenery="rainbow_horizon")
    monkeypatch.setattr(
        engine,
        "_drop_hit",
        lambda _rid, tier, _denominator: tier == "rare_environment",
    )

    answer(engine, storage, revlog_id=storage.now_ms + 1_000)

    assert storage.state.reward_drop_history[-1].kind == "growth_charge_standard"
    assert storage.state.consumables["growth_charge_standard"] == 1


def test_pity_counts_only_unique_eligible_answers_and_resets_only_on_ultra(monkeypatch):
    engine, storage = make_engine()
    monkeypatch.setattr(engine, "_drop_hit", lambda *_args: False)
    revlog_id = storage.now_ms + 1_000

    answer(engine, storage, revlog_id=revlog_id)
    assert storage.state.eligible_reward_count == 1
    assert storage.state.ultra_pity_misses == 1
    duplicate = answer(engine, storage, revlog_id=revlog_id)
    assert duplicate.total_growth == 0
    assert storage.state.eligible_reward_count == 1
    assert storage.state.ultra_pity_misses == 1

    monkeypatch.setattr(
        engine,
        "_drop_hit",
        lambda _rid, tier, _denominator: tier == "small_charge",
    )
    answer(engine, storage, revlog_id=revlog_id + 1_000)
    assert storage.state.ultra_pity_misses == 2
    monkeypatch.setattr(
        engine,
        "_drop_hit",
        lambda _rid, tier, _denominator: tier == "ultra_environment",
    )
    answer(engine, storage, revlog_id=revlog_id + 2_000)
    assert storage.state.ultra_pity_misses == 0


@pytest.mark.parametrize(
    ("winning_tier", "expected_kind"),
    (("booster_potion", "booster_potion"), ("coin_cache", "garden_coins")),
)
def test_random_booster_and_coin_bands_are_not_artificially_capped_per_day(
    monkeypatch, winning_tier: str, expected_kind: str
):
    engine, storage = make_engine()
    monkeypatch.setattr(
        engine,
        "_drop_hit",
        lambda _rid, tier, _denominator: tier == winning_tier,
    )
    first_id = storage.now_ms + 1_000

    answer(engine, storage, revlog_id=first_id)
    answer(engine, storage, revlog_id=first_id + 1_000)

    assert [drop.kind for drop in storage.state.reward_drop_history] == [
        expected_kind,
        expected_kind,
    ]


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


def test_environment_ui_owns_loadout_and_settings_do_not_mount_legacy_weather_controls():
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "ankigarden/ui/dashboard.py").read_text("utf-8")
    studio = (root / "ankigarden/ui/garden_studio.py").read_text("utf-8")

    assert dashboard.index('addTab(self.upgrades_scroll, "Garden Spaces")') < dashboard.index(
        'addTab(self.environment_scroll, "Weather and Scenery")'
    )
    assert 'addTab(self.supplements_scroll, "Fertilizer and Boosters")' in dashboard
    assert "self.customize_dialog = CustomizeGardenDialog(" in dashboard
    assert "self._settings_scene_snapshot," in dashboard
    assert 'self.catalog_tabs.addTab(self.environment_scroll, "Weather and Scenery")' in dashboard
    assert 'self.option_tabs.addTab(self.scenery_page, "Scenery")' in dashboard
    assert 'self.option_tabs.addTab(self.weather_page, "Weather")' in dashboard
    assert 'self.option_tabs.addTab(self.effects_page, "Effects")' in dashboard
    assert "Show Weather" in dashboard
    assert "Show Scenery" in dashboard
    assert "controls_layout.addWidget(self.motion_row)" in studio
    assert "controls_layout.addWidget(self.fine_tune_toggle)" not in studio
    assert "controls_layout.addWidget(self.fine_tune_section)" not in studio


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
