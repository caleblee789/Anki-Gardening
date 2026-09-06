from __future__ import annotations

import json
import math
import pytest
from pathlib import Path

from PIL import Image

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    GARDEN_FEATURE_CATALOG,
    LEGACY_WEATHER_TO_GARDEN_FEATURE,
)
from ankigarden.garden_features import FEATURE_EFFECT_KEYS, GARDEN_FEATURES
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    ActivePlantPeriod,
    DailyStats,
    GardenState,
    Plant,
    STATE_VERSION,
)
from ankigarden.storage import DueObligationStatus, migrate_modern_state
from ankigarden.ui.garden_feature_layout import (
    ASSET_CONTACT_X,
    ASSET_CONTACT_Y,
    BACKGROUND_FOCAL_Y,
    FEATURE_ANCHOR_X,
    FEATURE_CANVAS_SCENE_HEIGHT,
    FEATURE_GROUND_Y,
    NATIVE_SCENE_ASPECT,
    background_cover_crop,
    garden_feature_layout,
)
from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    render_home_widget,
)


ROOT = Path(__file__).resolve().parents[1]


class _Config:
    def value(self, key: str, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys: str, default=None):
        node = DEFAULT_CONFIG
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _Storage:
    def __init__(self) -> None:
        self.day = "2026-08-28"
        self.now_ms = 1_788_000_000_000
        self.day_start_ms = self.now_ms - 10_000
        self.addon_dir = ROOT / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.state = GardenState(
            plants=[Plant("p1", "bonsai", "Moss", 0)],
            active_plant_id="p1",
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.day_start_ms)
            ],
            last_active_day=self.day,
        )
        self.save_count = 0

    def save(self) -> None:
        self.save_count += 1

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

    def save_asset_metadata(self, _payload: dict) -> None:
        return None


def _engine(feature_id: str) -> tuple[GardenGameEngine, _Storage]:
    storage = _Storage()
    storage.state.inventory["garden_features"].append(feature_id)
    storage.state.selected_garden_feature = feature_id
    engine = GardenGameEngine(_Config(), storage)
    return engine, storage


def _answer(engine: GardenGameEngine, storage: _Storage, index: int):
    storage.now_ms += 1_000
    return engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": storage.now_ms + index,
        "answered_at_ms": storage.now_ms,
    })


def _legacy_schema22() -> dict:
    payload = GardenState().to_dict()
    payload["version"] = 22
    payload["inventory"].pop("garden_features", None)
    payload["inventory"]["weather"] = ["sunny", "breeze", "fireflies"]
    payload["loadout"] = {
        "weather_id": "fireflies",
        "scenery_id": "spring",
        "decoration_id": "lantern",
        "visibility": {"weather": False, "scenery": True},
    }
    payload["daily_loadout"] = {
        "scheduler_day": "2026-08-28",
        "weather_id": "fireflies",
        "scenery_id": "spring",
        "queued_weather_id": "breeze",
        "queued_scenery_id": "summer",
    }
    return payload


def test_registry_is_exact_and_uses_shipped_bonus_values() -> None:
    assert tuple(GARDEN_FEATURE_CATALOG) == (
        "seedling_sign",
        "wind_chime",
        "harvest_bell",
        "watering_station",
        "herbalist_hourglass",
        "firefly_lantern",
        "prism_trellis",
    )
    assert set(GARDEN_FEATURES) == set(GARDEN_FEATURE_CATALOG)
    assert FEATURE_EFFECT_KEYS == {
        "seedling_sign": "none",
        "wind_chime": "growth_every_10_plus_1",
        "harvest_bell": "completion_coins_plus_5",
        "watering_station": "growth_every_5_first_100_plus_1",
        "herbalist_hourglass": "hourglass_completion_booster",
        "firefly_lantern": (
            "instant_growth_every_5_plus_3_nurtured"
        ),
        "prism_trellis": "prism_completion_growth_100",
    }
    assert [GARDEN_FEATURE_CATALOG[key].price for key in GARDEN_FEATURE_CATALOG] == [
        None, 100, 175, 250, 350, None, None,
    ]


def test_schema22_weather_migration_is_lossless_and_idempotent() -> None:
    first = migrate_modern_state(_legacy_schema22())
    assert first.version == STATE_VERSION
    assert first.inventory["garden_features"] == [
        "seedling_sign", "wind_chime", "firefly_lantern",
    ]
    assert "weather" not in first.inventory.keys()
    assert first.selected_garden_feature == "firefly_lantern"
    assert first.loadout.visibility["garden_feature"] is False
    assert first.daily_loadout.pending_garden_feature_id == ""

    canonical = first.to_dict()
    assert "decoration_id" not in canonical["loadout"]
    assert GardenState.from_dict(canonical).to_dict() == canonical


def test_schema23_discards_retired_lantern_slot_idempotently() -> None:
    payload = GardenState().to_dict()
    payload["inventory"]["decorations"] = ["lantern"]
    payload["loadout"]["decoration_id"] = "lantern"

    restored = GardenState.from_dict(payload)
    canonical = restored.to_dict()

    assert "decorations" not in restored.inventory
    assert not hasattr(restored.loadout, "decoration_id")
    assert "decorations" not in canonical["inventory"]
    assert "decoration_id" not in canonical["loadout"]
    assert GardenState.from_dict(canonical).to_dict() == canonical


def test_all_legacy_ids_have_one_canonical_target() -> None:
    assert set(LEGACY_WEATHER_TO_GARDEN_FEATURE.values()) == set(
        GARDEN_FEATURE_CATALOG
    )
    assert DEFAULT_GARDEN_FEATURE_ID == "seedling_sign"


def test_fixed_layout_is_shared_and_native_background_crops_vertically() -> None:
    native = garden_feature_layout(1260, 840, "spring")
    home = garden_feature_layout(960, 400, "spring")
    assert (FEATURE_ANCHOR_X, FEATURE_GROUND_Y) == (0.215, 0.830)
    assert (ASSET_CONTACT_X, ASSET_CONTACT_Y) == (0.5, 0.88)
    assert FEATURE_CANVAS_SCENE_HEIGHT == 0.25
    assert native.feature.width == native.feature.height == 210
    assert home.feature.width == home.feature.height == 100
    assert native.feature.x + native.feature.width * 0.5 == 1260 * 0.215
    assert home.feature.x + home.feature.width * 0.5 == 960 * 0.215
    assert math.isclose(
        native.feature.y + native.feature.height * 0.88,
        840 * 0.830,
    )

    crop = background_cover_crop(1260, 840)
    assert NATIVE_SCENE_ASPECT == 1.5
    assert crop.x == 0
    assert crop.width == 1260
    assert crop.height == 945
    assert crop.y == -(945 - 840) * BACKGROUND_FOCAL_Y


def test_feature_assets_share_square_canvas_and_contact_line() -> None:
    root = ROOT / "ankigarden/assets/v6_storybook_gouache/garden_features"
    for item_id in GARDEN_FEATURE_CATALOG:
        with Image.open(root / f"{item_id}.webp") as image:
            assert image.mode == "RGBA"
            assert image.size == (1024, 1024)
            alpha = image.getchannel("A").point(lambda value: 255 if value > 20 else 0)
            bbox = alpha.getbbox()
            assert bbox is not None
            assert bbox[3] == round(1024 * ASSET_CONTACT_Y)


def test_manifest_has_physical_support_metadata_and_no_scene_offsets() -> None:
    manifest = json.loads((ROOT / "ankigarden/assets/manifest.json").read_text())
    rows = [row for row in manifest["assets"] if row["category"] == "garden_features"]
    assert len(rows) == 7
    assert all(row["category"] != "decorations" for row in manifest["assets"])
    assert not (ROOT / "ankigarden/assets/support/decorations/lantern.webp").exists()
    forbidden = {
        "offsetX", "offsetY", "featurePosition", "preferredSide",
        "themePosition", "homeOffset", "gardenOffset", "rarityScale",
    }
    assert all(not (forbidden & set(row)) for row in rows)
    for row in rows:
        metadata = row["placement"]
        x, y = metadata["ground_anchor"]
        sx, sy, sw, sh = metadata["support_bounds"]
        assert sx <= x <= sx + sw and sy <= y <= sy + sh
        for width, height in ((1260, 840), (960, 400)):
            layout = garden_feature_layout(width, height, "spring", metadata)
            assert math.isclose(layout.feature.x + layout.feature.width * x, width * FEATURE_ANCHOR_X)
            assert math.isclose(layout.feature.y + layout.feature.height * y, height * FEATURE_GROUND_Y)
            assert layout.shadow.width < layout.feature.width



def test_config_has_no_weather_visual_controls() -> None:
    assert DEFAULT_CONFIG["theme_overrides"] == {"animation_intensity": 0.7}
    serialized = json.dumps(DEFAULT_CONFIG).casefold()
    assert "weather_particle" not in serialized
    assert "weather_opacity" not in serialized


def test_home_preview_omits_decorations_even_when_equipped() -> None:
    data = HomeWidgetData(
        reviews_today=1,
        growth_earned=10,
        base_growth=10,
        streak_bonus_growth=0,
        fertilizer_growth=0,
        bonus_growth=0,
        all_due_completed=False,
        streak_days=1,
        streak_bonus_percent=0,
        next_streak_day=3,
        next_streak_bonus_percent=5,
        garden_currency=12,
        weather="wind_chime",
        weather_url="/_addons/test/wind_chime.webp",
        garden_feature_pad_url="/_addons/test/feature_pad.webp",
        garden_overlay_url="/_addons/test/home.webp",
        visible_scenery="spring",
    )
    html = render_home_widget(HomeWidgetSnapshot(1, "success", data))
    assert 'data-testid="home-garden-feature"' not in html
    assert 'data-testid="home-garden-feature-pad"' not in html
    assert 'class="ag-home__feature-shadow"' not in html
    assert "pointer-events:none" in html
    assert "requestAnimationFrame" not in html
    assert "home-weather-layer" not in html


def test_recurring_growth_cadence_uses_engine_results() -> None:
    for feature_id, cadence, amount in (
        ("wind_chime", 5, 1),
        ("watering_station", 2, 1),
    ):
        engine, storage = _engine(feature_id)
        engine.begin_review_session()
        awards = [_answer(engine, storage, index) for index in range(cadence * 2)]
        assert [award.weather_growth for award in awards] == [
            *(0 for _ in range(cadence - 1)), amount,
            *(0 for _ in range(cadence - 1)), amount,
        ]

    firefly, storage = _engine("firefly_lantern")
    awards = [_answer(firefly, storage, index) for index in range(10)]
    assert [
        award.decoration_result.direct_growth_awarded_units
        for award in awards
    ] == [0, 0, 0, 0, 300, 0, 0, 0, 0, 300]


def test_recurring_growth_catalog_matches_100_and_200_answer_balance() -> None:
    for feature_id, expected_100, expected_200 in (
        ("wind_chime", 20, 40),
        ("watering_station", 50, 100),
    ):
        engine, storage = _engine(feature_id)
        awards = [_answer(engine, storage, index) for index in range(200)]
        assert sum(item.weather_growth for item in awards[:100]) == expected_100
        assert sum(item.weather_growth for item in awards) == expected_200

    firefly, storage = _engine("firefly_lantern")
    awards = [_answer(firefly, storage, index) for index in range(200)]
    direct = [
        item.decoration_result.direct_growth_awarded_units
        for item in awards
    ]
    assert sum(direct[:100]) == 6_000
    assert sum(direct) == 12_000


def test_equipment_swaps_restore_visibility_and_preserve_session_progress() -> None:
    engine, storage = _engine("wind_chime")
    storage.state.inventory["garden_features"].append("watering_station")
    storage.state.loadout.visibility["garden_feature"] = False
    engine.begin_review_session()
    for index in range(4):
        assert _answer(engine, storage, index).weather_growth == 0
    assert engine.equip_environment("garden_feature", "watering_station")[0]
    assert storage.state.displayed_garden_feature == "watering_station"
    assert _answer(engine, storage, 10).weather_growth == 0
    assert engine.equip_environment("garden_feature", "wind_chime")[0]
    assert _answer(engine, storage, 11).weather_growth == 1
    engine.end_review_session()
    storage.day = "2026-08-29"
    engine.rollover_if_needed()
    assert engine.active_garden_feature_id() == "wind_chime"
    assert storage.state.loadout.visibility["garden_feature"] is True


def test_completion_and_booster_values_match_shipped_engine_balance() -> None:
    base, _storage = _engine("seedling_sign")
    base_coins, base_growth = base.all_due_rewards()

    bell, _storage = _engine("harvest_bell")
    bell.begin_review_session()
    bell_coins, bell_growth = bell.all_due_rewards()
    assert (bell_coins - base_coins, bell_growth - base_growth) == (5, 0)

    prism, _storage = _engine("prism_trellis")
    prism.begin_review_session()
    prism_coins, prism_growth = prism.all_due_rewards()
    assert (prism_coins - base_coins, prism_growth - base_growth) == (0, 0)

    hourglass, storage = _engine("herbalist_hourglass")
    hourglass.begin_review_session()
    storage.state.consumables["booster_potion"] = 1
    ok, _message = hourglass.use_booster_potion("p1")
    assert ok
    assert storage.state.plants[0].booster_card_batches[-1].total_cards == 125
    assert hourglass.last_booster_result.hourglass_bonus_cards == 25


def test_schema24_splits_display_and_bonus_without_losing_hidden_selection() -> None:
    payload = GardenState().to_dict()
    payload["version"] = 24
    payload["inventory"]["garden_features"] = ["seedling_sign", "firefly_lantern"]
    payload["loadout"] = {
        "garden_feature_id": "firefly_lantern",
        "scenery_id": "default",
        "visibility": {"garden_feature": False, "scenery": True},
    }
    migrated = migrate_modern_state(payload)
    assert migrated.displayed_garden_feature == "firefly_lantern"
    assert migrated.selected_garden_feature == "firefly_lantern"
    assert migrated.loadout.visibility["garden_feature"] is False
    assert migrated.daily_loadout.garden_bonus_anki_day_id == ""
    assert migrated.wind_chime_progress == 0
    assert migrated.prism_pending_growth_units == 0


def test_retired_cosmetics_cannot_replace_equipped_decoration_or_its_effect() -> None:
    engine, storage = _engine("wind_chime")
    storage.state.inventory["garden_features"].append("prism_trellis")
    storage.state.inventory["cosmetics"].append("garden_bench")
    _answer(engine, storage, 1)
    assert engine.display_garden_feature("prism_trellis")[0]
    assert engine.active_garden_feature_id() == "prism_trellis"
    assert engine.set_environment_visibility("garden_feature", False)[0]
    assert _answer(engine, storage, 2).decoration_result.prism_growth_banked_units == 0
    assert not engine.display_decoration("garden_bench")[0]
    assert storage.state.displayed_garden_feature == "prism_trellis"
    assert _answer(engine, storage, 3).decoration_result.prism_growth_banked_units == 0
    assert storage.state.prism_pending_growth_units == 0
    restored = GardenState.from_dict(storage.state.to_dict())
    assert restored.displayed_garden_feature == "prism_trellis"
    assert restored.loadout.active_garden_bonus_id == "prism_trellis"


def test_cadence_progress_persists_across_cutoff_and_inactive_days() -> None:
    engine, storage = _engine("wind_chime")
    storage.state.inventory["garden_features"].append("watering_station")
    for index in range(7):
        _answer(engine, storage, index)
    assert storage.state.wind_chime_progress == 2
    assert engine.equip_environment("garden_feature", "watering_station")[0]
    storage.day = "2026-08-29"
    engine.rollover_if_needed()
    for index in range(5):
        _answer(engine, storage, 100 + index)
    assert storage.state.watering_station_progress == 1
    assert storage.state.wind_chime_progress == 2
    assert engine.equip_environment("garden_feature", "wind_chime")[0]
    storage.day = "2026-08-30"
    engine.rollover_if_needed()
    awards = [_answer(engine, storage, 200 + index) for index in range(3)]
    assert [award.weather_growth for award in awards] == [0, 0, 1]


def test_prism_completion_grants_100_growth_once_without_banking() -> None:
    engine, storage = _engine("prism_trellis")
    assert engine.observe_due_start(DueObligationStatus(review_count=2))
    first = _answer(engine, storage, 1)
    assert first.decoration_result.prism_growth_banked_units == 0
    assert storage.state.prism_pending_growth_units == 0
    assert not engine.evaluate_today_cards(
        DueObligationStatus(review_count=1), record_completed_delta=True
    )[0]
    _answer(engine, storage, 2)
    before_units = storage.state.plants[0].growth_units
    ok, _message = engine.evaluate_today_cards(
        DueObligationStatus(), record_completed_delta=True
    )
    assert ok
    assert engine.last_completion_result.prism_growth_released_units == 10_000
    assert storage.state.prism_pending_growth_units == 0
    assert storage.state.plants[0].growth_units == before_units + 10_000
    assert not engine.evaluate_today_cards(DueObligationStatus(), record_completed_delta=True)[0]
    assert storage.state.plants[0].growth_units == before_units + 10_000
    later = _answer(engine, storage, 3)
    assert later.decoration_result.direct_growth_awarded_units == 0
    assert later.decoration_result.prism_growth_banked_units == 0


def test_legacy_prism_bank_is_inert_across_answers_and_cutoff() -> None:
    engine, storage = _engine("prism_trellis")
    storage.state.prism_pending_growth_units = 3_700
    for index in range(37):
        _answer(engine, storage, index)
    assert storage.state.prism_pending_growth_units == 3_700
    storage.day = "2026-08-29"
    engine.rollover_if_needed()
    assert storage.state.prism_pending_growth_units == 3_700


def test_equipment_changes_preserve_owned_potion_bonuses() -> None:
    engine, storage = _engine("wind_chime")
    storage.state.inventory["garden_features"].append("herbalist_hourglass")
    storage.state.consumables["booster_potion"] = 2
    _answer(engine, storage, 1)
    assert engine.use_booster_potion("p1")[0]
    assert engine.last_booster_result.total_cards_added == 125
    assert engine.equip_environment("garden_feature", "herbalist_hourglass")[0]
    assert engine.use_booster_potion("p1")[0]
    assert engine.last_booster_result.total_cards_added == 125
    assert engine.equip_environment("garden_feature", "wind_chime")[0]
    assert sum(batch.remaining_cards for batch in storage.state.plants[0].booster_card_batches) == 250


def test_hourglass_multiple_uses_extend_only_each_new_potion_dose() -> None:
    engine, storage = _engine("herbalist_hourglass")
    storage.state.consumables["booster_potion"] = 2
    assert engine.use_booster_potion("p1")[0]
    assert engine.use_booster_potion("p1")[0]
    plant = storage.state.plants[0]
    assert sum(batch.total_cards for batch in (*plant.booster_card_batches, *plant.booster_card_queue)) == 250
    assert engine.last_booster_result == engine.last_booster_result.__class__(
        base_cards_added=100,
        hourglass_bonus_cards=25,
        total_cards_added=125,
        remaining_booster_cards=250,
        target_id="p1",
    )


@pytest.mark.parametrize("feature,counter,credit,remainder", [
    ("wind_chime", "wind_chime_progress", 9, 0),
    ("watering_station", "watering_station_progress", 4, 1),
])
def test_carried_decoration_credit_settles_once_on_next_equipped_answer(feature, counter, credit, remainder):
    engine, storage = _engine(feature)
    setattr(storage.state, counter, credit)
    if feature == "watering_station":
        storage.state.watering_station_progress_by_day[storage.day] = credit
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(_Config(), storage)
    award = _answer(engine, storage, 1)
    assert award.weather_growth_units == 200
    assert getattr(storage.state, counter) == remainder
    assert _answer(engine, storage, 2).weather_growth_units == (100 if remainder else 0)
