import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.asset_manager import AssetManager
from ankigarden.config import DEFAULT_CONFIG, ConfigManager


class DummyConfig:
    def __init__(self, overrides=None):
        self.cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if overrides:
            self.cfg = ConfigManager._merge(self.cfg, overrides)

    def value(self, key, default=None):
        return self.cfg.get(key, default)

    def nested(self, *keys, default=None):
        node = self.cfg
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                return default
        return node


class DummyStorage:
    def __init__(self, root: Path):
        self.addon_dir = root
        self.assets_root = root / "assets"
        self.cache_dir = self.assets_root / "cache"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._meta = {}

    def load_asset_metadata(self):
        return self._meta

    def save_asset_metadata(self, data):
        self._meta = data


def _build_manifest(storage: DummyStorage, assets: list[dict]):
    manifest = storage.assets_root / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "assets": assets}, indent=2), encoding="utf-8")


def _touch_asset(storage: DummyStorage, rel_path: str):
    p = storage.addon_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<svg></svg>", encoding="utf-8")


def test_local_selection_is_deterministic(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "bg_a",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze_a.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.82,
        },
        {
            "asset_id": "bg_b",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze_b.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.81,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig(), storage)
    first = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")
    second = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")

    assert first is not None and second is not None
    assert first == second
    assert storage._meta["backgrounds:bg_spring_breeze"]["source_kind"] == "local_catalog"


def test_missing_file_uses_placeholder_when_enabled(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "decor_missing",
            "category": "decorations",
            "slot": {"decoration_id": "bench_corner"},
            "file": "assets/decorations/bench_corner/missing.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.8,
        }
    ]
    _build_manifest(storage, assets)

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("decorations", "decor_bench_corner", "ignored")

    assert picked is not None
    assert picked.name == "fallback_placeholder.svg"


def test_quality_preference_prefers_higher_tier(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "weather_perf",
            "category": "weather",
            "slot": {"weather": "breeze"},
            "file": "assets/weather/breeze/perf.svg",
            "width": 1280,
            "height": 720,
            "quality_tier": "performance",
            "quality_score": 0.7,
        },
        {
            "asset_id": "weather_ultra",
            "category": "weather",
            "slot": {"weather": "breeze"},
            "file": "assets/weather/breeze/ultra.svg",
            "width": 1280,
            "height": 720,
            "quality_tier": "ultra",
            "quality_score": 0.95,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig({"assets": {"quality_preference": "ultra"}}), storage)
    picked = manager.get_or_fetch("weather", "weather_breeze", "ignored")

    assert picked is not None
    assert picked.name == "ultra.svg"


def test_catalog_svg_manifest_dimensions_are_accepted(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "plant_svg",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v2_cozy_handpainted/plants/rose/young/rose_young.svg",
            "width": 256,
            "height": 256,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("plants", "rose_young", "ignored")

    assert picked is not None
    assert picked.name == "rose_young.svg"


def test_storybook_png_is_preferred_over_matching_v2_svg(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "rose_v2",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v2/rose.svg",
            "format": "svg",
            "width": 256,
            "height": 256,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
        {
            "asset_id": "rose_v3",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v3/rose.png",
            "format": "png",
            "style_family": "storybook_gouache",
            "width": 1024,
            "height": 1024,
            "quality_tier": "ultra",
            "quality_score": 0.98,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    picked = AssetManager(DummyConfig(), storage).get_or_fetch("plants", "rose_young", "ignored")

    assert picked is not None and picked.name == "rose.png"


def test_storybook_season_master_serves_every_weather(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "summer_master",
            "category": "backgrounds",
            "slot": {"season": "summer", "weather": "any", "theme": "verdant_dusk"},
            "file": "assets/v3/summer.webp",
            "format": "webp",
            "style_family": "storybook_gouache",
            "width": 1448,
            "height": 1086,
            "quality_tier": "ultra",
            "quality_score": 0.98,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    picked = AssetManager(DummyConfig(), storage).get_or_fetch(
        "backgrounds", "bg_summer_gentle_rain", "ignored", theme="verdant_dusk"
    )

    assert picked is not None and picked.name == "summer.webp"


def test_morning_bloom_theme_alias_selects_verdant_dawn_assets(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "bg_dawn",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dawn"},
            "file": "assets/v2_cozy_handpainted/backgrounds/verdant_dawn/spring_breeze.svg",
            "width": 512,
            "height": 384,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="morning_bloom")

    assert picked is not None
    assert "verdant_dawn" in picked.as_posix()


def test_explicit_preview_quality_overrides_config_preference(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "weather_perf",
            "category": "weather",
            "slot": {"weather": "sunny"},
            "file": "assets/v2_cozy_handpainted/weather/sunny/sunny_performance.svg",
            "width": 256,
            "height": 192,
            "quality_tier": "performance",
            "quality_score": 0.7,
        },
        {
            "asset_id": "weather_balanced",
            "category": "weather",
            "slot": {"weather": "sunny"},
            "file": "assets/v2_cozy_handpainted/weather/sunny/sunny_balanced.svg",
            "width": 256,
            "height": 192,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig({"assets": {"quality_preference": "performance"}}), storage)
    picked = manager.get_or_fetch("weather", "weather_sunny", "ignored", quality_preference="balanced")

    assert picked is not None
    assert picked.name == "sunny_balanced.svg"


def test_reroll_cycles_through_local_alternatives(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "plant1",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/a.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.85,
        },
        {
            "asset_id": "plant2",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/b.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.84,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig(), storage)
    first = manager.get_or_fetch("plants", "bonsai_mature", "ignored", reroll=True)
    second = manager.get_or_fetch("plants", "bonsai_mature", "ignored", reroll=True)

    assert first is not None and second is not None
    assert first != second


def test_legacy_remote_metadata_is_migrated_and_not_selected(tmp_path):
    storage = DummyStorage(tmp_path)
    old = storage.addon_dir / "assets/backgrounds/legacy_remote.jpg"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"legacy")
    storage._meta = {
        "backgrounds:bg_spring_breeze": {
            "source_kind": "remote",
            "local_path": "assets/backgrounds/legacy_remote.jpg",
            "provider": "wikimedia",
        }
    }
    assets = [
        {
            "asset_id": "bg_local",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.85,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")

    assert picked is not None
    assert picked.name == "spring_breeze.svg"
    assert storage._meta["backgrounds:bg_spring_breeze"]["legacy_remote_preserved"] is True
    assert storage._meta["backgrounds:bg_spring_breeze"]["source_kind"] == "local_catalog"


def test_config_merge_keeps_new_visual_defaults():
    merged = ConfigManager._merge(DEFAULT_CONFIG.copy(), {"enable_sounds": True})
    assert merged["enable_sounds"] is True
    assert merged["assets"]["mode"] == "local_only"
    assert "weather_particle_density" in merged["theme_overrides"]
