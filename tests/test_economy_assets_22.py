from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import ankigarden
from ankigarden.asset_manager import AssetManager
from ankigarden.balance_catalog import COSMETICS, LANDMARKS, MASTERY_RANKS
from ankigarden.collectibles import (
    collection_entry_registry,
    collectible_registry,
    collectible_views,
)
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import GardenState


ADDON_ROOT = Path(ankigarden.__file__).resolve().parent
MANIFEST_PATH = ADDON_ROOT / "assets" / "manifest.json"
ECONOMY_ASSET_COUNTS = {
    "cosmetics": 3,
    "landmarks": 6,
    "mastery": 4,
}


class _Config:
    @staticmethod
    def value(_key: str, default=None):
        return default

    @staticmethod
    def nested(*_keys: str, default=None):
        return default


class _Storage:
    addon_dir = ADDON_ROOT
    assets_root = ADDON_ROOT / "assets"

    @staticmethod
    def load_asset_metadata() -> dict:
        return {}

    @staticmethod
    def save_asset_metadata(_value: dict) -> None:
        return None


def _economy_rows() -> list[dict]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [
        row
        for row in payload["assets"]
        if row.get("category") in ECONOMY_ASSET_COUNTS
    ]


def test_economy_art_manifest_has_one_exact_asset_for_every_catalog_entry() -> None:
    rows = _economy_rows()
    by_category = Counter(str(row["category"]) for row in rows)

    assert by_category == ECONOMY_ASSET_COUNTS
    assert {str(row["asset_id"]) for row in rows} == {
        *(item.asset_id for item in COSMETICS),
        *(item.asset_id for item in LANDMARKS),
        *(f"mastery_{rank.rank_id.value}" for rank in MASTERY_RANKS),
    }
    assert len({str(row["file"]) for row in rows}) == len(rows)


def test_economy_art_is_loadable_lossless_webp_with_real_transparency() -> None:
    for row in _economy_rows():
        path = ADDON_ROOT / str(row["file"])
        assert path.is_file(), path
        assert row["format"] == "webp"
        assert row["alpha"] is True
        assert min(row["width"], row["height"]) >= 1024
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            assert rgba.size == (row["width"], row["height"])
            alpha_min, alpha_max = rgba.getchannel("A").getextrema()
            assert alpha_min == 0
            assert alpha_max == 255


def test_manifest_resolves_every_new_economy_art_identity() -> None:
    manager = AssetManager(_Config(), _Storage())
    expected = {
        "cosmetics": tuple((item.asset_id, item.asset_id) for item in COSMETICS),
        "landmarks": tuple(
            (item.landmark_id.value, item.asset_id) for item in LANDMARKS
        ),
        "mastery": tuple(
            (rank.rank_id.value, f"mastery_{rank.rank_id.value}")
            for rank in MASTERY_RANKS
        ),
    }
    for category, identities in expected.items():
        for key, asset_id in identities:
            resolved = manager.resolve(category, key, f"slot:{category}:{key}")
            assert resolved is not None
            assert resolved.category == category
            assert resolved.asset_id == asset_id
            assert resolved.path.is_file()


def test_shared_item_resolver_routes_every_new_economy_art_identity() -> None:
    """Shared cards must not send 2.2 catalog art through UI fallbacks."""

    manager = AssetManager(_Config(), _Storage())
    engine = SimpleNamespace(assets=manager, config=_Config())
    expected = {
        "cosmetics": tuple(
            (
                (item.cosmetic_id.value, item.asset_id),
                item.asset_id,
            )
            for item in COSMETICS
        ),
        "landmarks": tuple(
            (
                (item.landmark_id.value, item.asset_id),
                item.asset_id,
            )
            for item in LANDMARKS
        ),
        "mastery": tuple(
            (
                (rank.rank_id.value, f"mastery_{rank.rank_id.value}"),
                f"mastery_{rank.rank_id.value}",
            )
            for rank in MASTERY_RANKS
        ),
    }

    for category, identities in expected.items():
        for accepted_keys, asset_id in identities:
            for key in accepted_keys:
                resolved = GardenGameEngine.resolve_item_asset(engine, key)
                assert resolved is not None, (category, key)
                assert resolved.category == category
                assert resolved.asset_id == asset_id
                assert resolved.path.is_file()

    # The new category routing must preserve the existing UI-item contract.
    resolved = GardenGameEngine.resolve_item_asset(engine, "booster_potion")
    assert resolved is not None
    assert resolved.category == "ui"
    assert resolved.asset_id == "ui_booster_potion"
    assert GardenGameEngine.resolve_item_asset(engine, "") is None


def test_collection_registry_is_complete_and_fertilizer_copy_is_card_counted() -> None:
    rows = collectible_registry()
    assert len(rows) == 88
    assert Counter(row.category for row in rows) == {
        "plants": 10,
        "scenery": 9,
        "garden_features": 7,
        "garden_beds": 6,
        "growth_items": 7,
        "cosmetics": 3,
        "landmarks": 6,
        "mastery": 40,
    }
    collection_rows = collection_entry_registry()
    assert len(collection_rows) == 39
    assert not {
        row.category for row in collection_rows
    }.intersection({"cosmetics", "landmarks", "mastery"})
    fertilizers = tuple(
        row for row in rows if "fertilizer" in row.item_id
    )
    assert len(fertilizers) == 3
    assert [row.descriptor.duration for row in fertilizers] == [
        "100 eligible cards",
        "200 eligible cards",
        "400 eligible cards",
    ]
    joined = " ".join(
        str(value)
        for row in fertilizers
        for value in row.descriptor.__dict__.values()
    ).casefold()
    assert "hour" not in joined
    assert "second" not in joined


def test_collection_projects_equipped_artwork_and_its_effect() -> None:
    state = GardenState()
    state.inventory["cosmetics"] = ["garden_bench"]
    state.inventory["garden_features"] = ["watering_station"]
    state.loadout.active_garden_bonus_id = "watering_station"
    state.loadout.display_decoration_id = "watering_station"

    views = collectible_views(state)
    assert all(row.definition.item_id != "cosmetics:garden_bench" for row in views)
    assert all(not row.equipped for row in views if row.definition.category == "cosmetics")
    watering = next(
        row
        for row in views
        if row.definition.item_id == "garden_features:watering_station"
    )

    assert watering.equipped is True
    assert watering.selected is True
    assert [view.definition.item_id for view in views if view.equipped] == [
        "scenery:default", "garden_features:watering_station",
    ]


def test_landmark_resolver_rejects_unfinished_display_and_accepts_completed_art() -> None:
    manager = AssetManager(_Config(), _Storage())
    project = SimpleNamespace(
        selected_project_id="mossy_stone_path",
        displayed_project_id="mossy_stone_path",
        completed_project_ids=[],
    )
    engine = SimpleNamespace(
        assets=manager,
        config=_Config(),
        state=SimpleNamespace(garden_project=project),
    )

    assert GardenGameEngine.resolve_landmark_asset(engine) is None
    project.completed_project_ids = ["mossy_stone_path"]
    resolved = GardenGameEngine.resolve_landmark_asset(engine)
    assert resolved is not None
    assert resolved.asset_id == "landmark_mossy_stone_path"


def test_mastery_resolver_uses_highest_species_rank_and_rejects_unknown_rank() -> None:
    manager = AssetManager(_Config(), _Storage())
    engine = SimpleNamespace(
        assets=manager,
        config=_Config(),
        state=SimpleNamespace(
            cultivation_mastery=SimpleNamespace(
                highest_rank_by_species={"bonsai": "gold"}
            )
        ),
    )

    resolved = GardenGameEngine.resolve_mastery_asset(engine, "bonsai")
    assert resolved is not None
    assert resolved.asset_id == "mastery_gold"
    assert GardenGameEngine.resolve_mastery_asset(engine, "rose") is None
    assert GardenGameEngine.resolve_mastery_rank_asset(engine, "unknown") is None
