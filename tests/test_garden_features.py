from __future__ import annotations

import json
import math
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
        "wind_chime": "growth_first_10_plus_1",
        "harvest_bell": "completion_coins_plus_5",
        "watering_station": "growth_first_20_plus_1",
        "herbalist_hourglass": "booster_duration_multiplier_1_10",
        "firefly_lantern": "growth_first_15_plus_5",
        "prism_trellis": "completion_direct_growth_plus_100",
    }
    assert [GARDEN_FEATURE_CATALOG[key].price for key in GARDEN_FEATURE_CATALOG] == [
        None, 100, 175, 250, 350, None, None,
    ]


def test_schema22_weather_migration_is_lossless_and_idempotent() -> None:
    first = migrate_modern_state(_legacy_schema22())
    assert first.version == STATE_VERSION == 23
    assert first.inventory["garden_features"] == [
        "seedling_sign", "wind_chime", "firefly_lantern",
    ]
    assert "weather" not in first.inventory.keys()
    assert first.selected_garden_feature == "firefly_lantern"
    assert first.loadout.visibility["garden_feature"] is False
    assert first.daily_loadout.pending_garden_feature_id == "wind_chime"

    canonical = first.to_dict()
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


def test_manifest_has_feature_assets_and_no_position_overrides() -> None:
    manifest = json.loads((ROOT / "ankigarden/assets/manifest.json").read_text())
    rows = [row for row in manifest["assets"] if row["category"] == "garden_features"]
    assert len(rows) == 8
    forbidden = {
        "offsetX", "offsetY", "featurePosition", "preferredSide",
        "themePosition", "homeOffset", "gardenOffset", "rarityScale",
    }
    assert all(not (forbidden & set(row)) for row in rows)


def test_config_has_no_weather_visual_controls() -> None:
    assert DEFAULT_CONFIG["theme_overrides"] == {"animation_intensity": 0.7}
    serialized = json.dumps(DEFAULT_CONFIG).casefold()
    assert "weather_particle" not in serialized
    assert "weather_opacity" not in serialized


def test_home_uses_static_pointer_transparent_feature_and_pad() -> None:
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
    assert 'data-testid="home-garden-feature"' in html
    assert 'data-testid="home-garden-feature-pad"' in html
    assert "pointer-events:none" in html
    assert "requestAnimationFrame" not in html
    assert "home-weather-layer" not in html


def test_daily_growth_limits_use_engine_results() -> None:
    for feature_id, limit, amount in (
        ("wind_chime", 10, 1),
        ("watering_station", 20, 1),
        ("firefly_lantern", 15, 5),
    ):
        engine, storage = _engine(feature_id)
        engine.begin_review_session()
        awards = [_answer(engine, storage, index) for index in range(limit + 1)]
        assert all(award.weather_growth == amount for award in awards[:limit])
        assert awards[limit].weather_growth == 0


def test_hidden_artwork_keeps_bonus_and_mid_session_change_does_not_stack() -> None:
    engine, storage = _engine("wind_chime")
    storage.state.inventory["garden_features"].append("watering_station")
    storage.state.loadout.visibility["garden_feature"] = False
    engine.begin_review_session()
    assert _answer(engine, storage, 1).weather_growth == 1

    ok, message = engine.equip_environment("garden_feature", "watering_station")
    assert ok and "next review session" in message
    assert _answer(engine, storage, 2).weather_growth == 1
    assert storage.state.daily_loadout.pending_garden_feature_id == "watering_station"

    engine.end_review_session()
    engine.begin_review_session()
    assert engine.active_garden_feature_id() == "watering_station"
    assert storage.state.loadout.visibility["garden_feature"] is False


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
    assert (prism_coins - base_coins, prism_growth - base_growth) == (0, 100)

    hourglass, storage = _engine("herbalist_hourglass")
    hourglass.begin_review_session()
    storage.state.consumables["booster_potion"] = 1
    ok, _message = hourglass.use_booster_potion("p1")
    assert ok
    assert storage.state.plants[0].booster_card_batches[-1].total_cards == 110
