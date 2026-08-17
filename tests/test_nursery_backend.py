from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ankigarden.asset_manager import AssetManager
from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    DailyStats,
    GardenState,
    Plant,
    STATE_VERSION,
)
from ankigarden.storage import DueObligationStatus, GardenStorage, migrate_previous_state


class FakeConfig:
    def __init__(self, **overrides):
        self.data = {**DEFAULT_CONFIG, **overrides}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def nested(self, *keys, default=None):
        node = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class FakeStorage:
    def __init__(self, state: GardenState | None = None):
        self.day = "2026-08-08"
        self.now_ms = 1_786_150_000_000
        self.state = state or GardenState(
            daily_stats=DailyStats(day=self.day),
            last_active_day="2026-08-07",
        )
        self.addon_dir = Path(__file__).resolve().parents[1] / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.cache_dir = self.addon_dir / "user_files" / "cache"
        self.save_count = 0
        self.fail_save = False

    def save(self):
        self.save_count += 1
        if self.fail_save:
            raise OSError("disk full")

    def current_scheduler_day(self):
        return self.day

    def current_time_ms(self):
        return self.now_ms

    def due_obligations(self):
        return DueObligationStatus()

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _data):
        return None


def release_row(species: str, stage: str, *, base_type: str = "direct_soil") -> dict:
    return {
        "asset_id": f"plant_{species}_{stage}_twilight_v6",
        "category": "plants",
        "slot": {"species": species, "stage": stage},
        "variants": ["storybook_gouache", "direct_soil", "continuity_v6"],
        "file": f"assets/v6_storybook_gouache/plants/{species}/{stage}/{species}_{stage}_twilight_v6.png",
        "width": 1024,
        "height": 1024,
        "format": "png",
        "release_preferred": True,
        "placement": {
            "base_type": base_type,
            "layer": "plants",
            "ground_anchor": [0.5, 0.9],
            "support_bounds": [0.45, 0.88, 0.1, 0.02],
            "scene_scale_correction": 0.8,
            "visual_scale_correction": 0.9,
            "release_layout_candidate": True,
        },
    }


def manifest_manager(tmp_path: Path, rows: list[dict]) -> AssetManager:
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    for row in rows:
        path = tmp_path / row["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGOU8Db5z8DAwMAEIkAYABd8AZq1W63BAAAAAElFTkSuQmCC"
        ))
    (assets_root / "manifest.json").write_text(
        json.dumps({"assets": rows}), encoding="utf-8"
    )

    class Storage:
        addon_dir = tmp_path
        cache_dir = tmp_path / "cache"

        def __init__(self):
            self.assets_root = assets_root

        def load_asset_metadata(self):
            return {}

        def save_asset_metadata(self, _data):
            return None

    return AssetManager(FakeConfig(), Storage())


def test_release_ready_query_requires_every_exact_v6_direct_soil_stage(tmp_path):
    stages = ("seed", "sprout", "young", "mature", "flowering", "rare")
    rows = [release_row("rose", stage) for stage in stages]
    rows.extend(release_row("bonsai", stage) for stage in stages[:-1])
    rows.extend(release_row("hydrangea", stage, base_type="pot") for stage in stages)

    manager = manifest_manager(tmp_path, rows)

    assert manager.release_ready_plant_species() == ("rose",)
    assert manager.release_ready_plant_species(theme="verdant_dusk") == ()


def test_underscore_species_key_keeps_the_full_species_during_resolution(tmp_path):
    stages = ("seed", "sprout", "young", "mature", "flowering", "rare")
    manager = manifest_manager(
        tmp_path,
        [release_row("japanese_maple", stage) for stage in stages],
    )

    assert manager._slot_for(
        "plants", "japanese_maple_flowering", "verdant_twilight"
    ) == {"species": "japanese_maple", "stage": "flowering"}
    assert manager.release_ready_plant_species() == ("japanese_maple",)

    resolved = manager.resolve(
        "plants",
        "japanese_maple_flowering",
        "Japanese Maple flowering plant",
        theme="verdant_twilight",
    )

    assert resolved is not None
    assert resolved.asset_id == "plant_japanese_maple_flowering_twilight_v6"
    assert resolved.metadata["slot"] == {
        "species": "japanese_maple",
        "stage": "flowering",
    }


def test_repeated_asset_resolution_is_read_only(tmp_path):
    row = release_row("rose", "mature")
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    asset_path = tmp_path / row["file"]
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGOU8Db5z8DAwMAEIkAYABd8AZq1W63BAAAAAElFTkSuQmCC"
    ))
    (assets_root / "manifest.json").write_text(
        json.dumps({"assets": [row]}), encoding="utf-8"
    )

    class Storage:
        def __init__(self):
            self.addon_dir = tmp_path
            self.assets_root = assets_root
            self.saved: list[dict] = []

        def load_asset_metadata(self):
            return {}

        def save_asset_metadata(self, data):
            self.saved.append(json.loads(json.dumps(data)))

    storage = Storage()
    manager = AssetManager(FakeConfig(), storage)

    first = manager.resolve("plants", "rose_mature", "Rose mature", theme="verdant_twilight")
    second = manager.resolve("plants", "rose_mature", "Rose mature", theme="verdant_twilight")

    assert first is not None
    assert second is first
    assert storage.saved == []

    manager.clear_runtime_cache()
    third = manager.resolve("plants", "rose_mature", "Rose mature", theme="verdant_twilight")
    assert third is not None
    assert storage.saved == []


def test_bundled_catalog_exposes_only_complete_v6_lines():
    storage = FakeStorage()
    manager = AssetManager(FakeConfig(), storage)

    ready = manager.release_ready_plant_species()
    rows = json.loads(
        (storage.assets_root / "manifest.json").read_text(encoding="utf-8")
    )["assets"]
    required = set(manager.RELEASE_PLANT_STAGES)
    stages_by_species: dict[str, set[str]] = {}
    for row in rows:
        if (
            row.get("category") == "plants"
            and row.get("release_preferred") is True
            and "continuity_v6" in row.get("variants", [])
            and row.get("placement", {}).get("release_layout_candidate") is True
        ):
            slot = row.get("slot", {})
            stages_by_species.setdefault(str(slot.get("species", "")), set()).add(
                str(slot.get("stage", ""))
            )
    expected = tuple(sorted(
        species for species, stages in stages_by_species.items()
        if species and stages == required
    ))

    assert ready == expected
    assert {"bonsai", "rose"}.issubset(ready)


def test_free_starter_is_atomic_requires_nurture_and_does_not_backfill_earlier_reviews():
    storage = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), storage)

    before_choice = engine.register_review({"queue": 2, "ease": 3})
    assert before_choice.total_growth == 0
    assert storage.state.total_reviews == 1

    ok, _message, plant = engine.choose_starter("rose")

    assert ok and plant is not None
    assert plant.slot_index == 0
    assert storage.state.active_plant_id is None
    assert storage.state.unlocked_slots == 2
    assert storage.state.unlocked_species == ["rose"]
    assert storage.state.starter_selection_complete
    assert storage.state.currency_balance == 0

    earlier_revlog = storage.now_ms - 1_000
    synced = engine.apply_same_day_reviews(
        [{
            "queue": 2,
            "ease": 3,
            "revlog_id": earlier_revlog,
            "answered_at_ms": earlier_revlog,
        }],
        latest_revlog_id=earlier_revlog,
    )
    assert synced == 0
    assert plant.growth_points == 0
    assert storage.state.total_reviews == 2

    storage.now_ms += 1_000
    after_choice = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": storage.now_ms,
        "answered_at_ms": storage.now_ms,
    })
    assert after_choice.total_growth == 0
    assert plant.growth_points == 0

    storage.now_ms += 1_000
    nurtured, _message = engine.set_active_plant(plant.plant_id)
    assert nurtured
    assert storage.state.active_plant_id == plant.plant_id
    after_nurture = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": storage.now_ms,
        "answered_at_ms": storage.now_ms,
    })
    assert after_nurture.total_growth == 10
    assert plant.growth_points == 10


def test_starter_species_share_the_same_growth_stages_rate_and_reward_model():
    storage = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), storage)

    assert len(GROWTH_STAGES) == 6
    assert len(GROWTH_THRESHOLDS) == 6
    estimates = {
        species: engine.progress_estimates(
            Plant(f"test-{species}", species, species.title(), 0)
        )
        for species in engine.SPECIES_PRICES
    }
    assert len(set(estimates.values())) == 1
    assert engine.BASE_GROWTH_PER_REVIEW == 10
    assert list(engine.environment_drop_odds())


def test_starter_save_failure_restores_the_empty_garden():
    storage = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), storage)
    storage.fail_save = True

    ok, _message, plant = engine.choose_starter("bonsai")

    assert not ok and plant is None
    assert storage.state.plants == []
    assert storage.state.unlocked_species == []
    assert storage.state.active_plant_id is None
    assert not storage.state.starter_selection_complete


def test_collection_loadout_draft_commits_atomically_and_rolls_back_on_save_failure():
    storage = FakeStorage()
    engine = GardenGameEngine(FakeConfig(), storage)
    storage.state.inventory.setdefault("weather", []).append("breeze")
    storage.state.inventory.setdefault("scenery", []).append("spring")

    ok, message = engine.apply_environment_loadout(
        "breeze", "spring", {"weather": False, "scenery": True}
    )

    assert ok and message == "Garden loadout saved."
    assert storage.state.selected_weather == "breeze"
    assert storage.state.selected_background == "spring"
    assert storage.state.environment_visibility == {
        "weather": False,
        "scenery": True,
    }

    storage.fail_save = True
    ok, message = engine.apply_environment_loadout(
        "sunny", "default", {"weather": True, "scenery": False}
    )

    assert not ok and message == "Those appearance changes could not be saved."
    assert storage.state.selected_weather == "breeze"
    assert storage.state.selected_background == "spring"
    assert storage.state.environment_visibility == {
        "weather": False,
        "scenery": True,
    }


def test_garden_space_cannot_be_purchased_before_free_starter_selection():
    storage = FakeStorage()
    storage.state.currency_balance = 10_000
    engine = GardenGameEngine(FakeConfig(), storage)
    before = storage.state.to_dict()
    save_count = storage.save_count

    ok, message = engine.purchase_next_bed()

    assert not ok
    assert message == "Choose a starter before unlocking another garden bed."
    assert storage.state.to_dict() == before
    assert storage.state.currency_transactions == []
    assert storage.save_count == save_count


def test_catalog_summary_preserves_owned_supported_species_and_counts_dynamically():
    fern = Plant("fern", "fern", "Fiddle", 0, growth_points=2_500)
    state = GardenState(
        plants=[fern],
        unlocked_species=["fern"],
        active_plant_id="fern",
        currency_balance=500,
        daily_stats=DailyStats(day="2026-08-08"),
    )
    storage = FakeStorage(state)
    engine = GardenGameEngine(FakeConfig(), storage)
    engine.assets.release_ready_plant_species = lambda **_kwargs: ("bonsai", "rose")

    summary = engine.catalog_summary()

    assert summary == {
        "release_ready_species": ["bonsai", "rose"],
        "owned_species": ["fern"],
        "available_species": ["bonsai", "rose"],
        "owned_count": 1,
        "available_count": 2,
    }
    assert engine.plant_story("fern") is fern
    assert fern.growth_points == 2_500
    assert not engine.purchase_species("fern")[0]


def test_schema10_inventory_only_species_becomes_a_usable_shelved_plant_without_repurchase():
    state = migrate_previous_state({
        "version": 10,
        "streak_days": 0,
        "total_reviews": 25,
        "total_correct": 20,
        "total_wrong": 5,
        "unlocked_slots": 2,
        "selected_background": "default",
        "selected_weather": "sunny",
        "plants": [],
        "achievements": {},
        "daily_stats": {"day": "2026-08-08", "reviewed": 0},
        "inventory": {
            "plants": ["sunflower"],
            "pots": ["ceramic_minimal"],
            "backgrounds": ["default"],
            "decorations": ["lantern"],
            "weather": ["sunny"],
        },
        "equipped": {
            "pot": "ceramic_minimal",
            "background": "default",
            "decoration": "none",
            "weather": "sunny",
        },
        "last_active_day": "2026-08-08",
        "focus_plant_id": None,
    })
    storage = FakeStorage(state)
    storage.state.currency_balance = 500
    engine = GardenGameEngine(FakeConfig(), storage)
    engine.assets.release_ready_plant_species = lambda **_kwargs: ("sunflower",)
    plant = next(item for item in storage.state.plants if item.species == "sunflower")

    assert plant.slot_index is None
    assert plant.growth_points == 0
    assert engine.catalog_summary()["owned_species"] == ["sunflower"]
    balance = storage.state.currency_balance
    assert not engine.purchase_species("sunflower")[0]
    assert storage.state.currency_balance == balance
    assert engine.plant_from_collection(plant.plant_id, 0)[0]
    assert plant.slot_index == 0


@pytest.mark.parametrize("saved_version", [11, 12, 13, 14, STATE_VERSION])
def test_modern_entitlement_only_species_stays_visible_plantable_and_paid_for(
    tmp_path,
    saved_version,
):
    payload = GardenState(
        unlocked_species=["sunflower"],
        starter_selection_complete=True,
        currency_balance=500,
        daily_stats=DailyStats(day="2026-08-08"),
        last_active_day="2026-08-08",
    ).to_dict()
    payload["version"] = saved_version
    if saved_version in (11, 12, 13):
        payload.pop("starter_selection_complete")
    state_path = tmp_path / "garden_state.json"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    loader = object.__new__(GardenStorage)
    loader.data_path = state_path
    state = loader._load()
    storage = FakeStorage(state)
    engine = GardenGameEngine(FakeConfig(), storage)
    engine.assets.release_ready_plant_species = lambda **_kwargs: ("sunflower",)
    plant = next(item for item in state.plants if item.species == "sunflower")

    assert plant.slot_index is None
    assert plant.growth_points == 0
    assert engine.catalog_summary()["owned_species"] == ["sunflower"]
    balance = state.currency_balance
    assert not engine.purchase_species("sunflower")[0]
    assert state.currency_balance == balance
    assert engine.plant_from_collection(plant.plant_id, 0)[0]
    assert plant.slot_index == 0


def test_ready_species_purchase_is_atomic_and_incomplete_species_are_hidden():
    lavender = Plant("lavender", "lavender", "Violet", 0)
    state = GardenState(
        plants=[lavender],
        unlocked_species=["lavender"],
        currency_balance=500,
        daily_stats=DailyStats(day="2026-08-08"),
    )
    storage = FakeStorage(state)
    engine = GardenGameEngine(FakeConfig(), storage)
    engine.assets.release_ready_plant_species = lambda **_kwargs: ("bonsai", "rose")

    assert not engine.purchase_species("ivy")[0]
    ok, _message, rose = engine.purchase_species("rose")
    assert ok and rose is not None
    assert storage.state.currency_balance == 400
    assert "rose" in storage.state.unlocked_species

    failing_state = GardenState(
        plants=[Plant("lavender", "lavender", "Violet", 0)],
        unlocked_species=["lavender"],
        currency_balance=500,
        daily_stats=DailyStats(day="2026-08-08"),
    )
    failing_storage = FakeStorage(failing_state)
    failing_engine = GardenGameEngine(FakeConfig(), failing_storage)
    failing_engine.assets.release_ready_plant_species = lambda **_kwargs: ("bonsai", "rose")
    before = failing_storage.state.to_dict()
    failing_storage.fail_save = True

    ok, _message, rose = failing_engine.purchase_species("rose")

    assert not ok and rose is None
    assert failing_storage.state.to_dict() == before
