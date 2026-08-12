from __future__ import annotations

import json
import logging
from pathlib import Path

from ankigarden.asset_manager import AssetManager
from ankigarden.config import DEFAULT_CONFIG, ConfigManager


class DummyConfig:
    def __init__(self) -> None:
        self.cfg = json.loads(json.dumps(DEFAULT_CONFIG))

    def value(self, key: str, default=None):
        return self.cfg.get(key, default)

    def nested(self, *keys: str, default=None):
        node = self.cfg
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                return default
        return node


class DummyStorage:
    def __init__(self, root: Path) -> None:
        self.addon_dir = root
        self.assets_root = root / "assets"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, dict] = {}

    def load_asset_metadata(self):
        return self._metadata

    def save_asset_metadata(self, value):
        self._metadata = value


def _manager(tmp_path: Path, rows: list[dict]) -> AssetManager:
    storage = DummyStorage(tmp_path)
    (storage.assets_root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "assets": rows}), encoding="utf-8"
    )
    for row in rows:
        path = storage.addon_dir / row["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime asset")
    return AssetManager(DummyConfig(), storage)


def test_every_bundled_ui_catalog_item_resolves_through_production_resolver() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "ankigarden/assets/manifest.json").read_text())[
        "assets"
    ]
    manager = AssetManager(
        DummyConfig(),
        type(
            "Storage",
            (),
            {
                "addon_dir": root / "ankigarden",
                "assets_root": root / "ankigarden/assets",
                "load_asset_metadata": lambda _self: {},
                "save_asset_metadata": lambda _self, _value: None,
            },
        )(),
    )
    ui_rows = [row for row in rows if row.get("category") == "ui"]
    assert len(ui_rows) == 7
    for row in ui_rows:
        key = row["slot"]["ui_id"]
        resolved = manager.resolve_ui_asset(key)
        assert resolved is not None
        assert resolved.path.is_file()


def test_all_shipped_supplement_keys_resolve() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "ankigarden/assets/manifest.json").read_text())["assets"]
    manager = AssetManager(
        DummyConfig(),
        type(
            "Storage",
            (),
            {
                "addon_dir": root / "ankigarden",
                "assets_root": root / "ankigarden/assets",
                "load_asset_metadata": lambda _self: {},
                "save_asset_metadata": lambda _self, _value: None,
            },
        )(),
    )
    keys = (
        "booster_potion",
        "fertilizer_basic",
        "fertilizer_quality",
        "fertilizer_premium",
        "growth_charge_small",
        "growth_charge_standard",
        "growth_charge_grand",
    )
    assert all(manager.resolve_ui_asset(key) is not None for key in keys)


def test_ui_resolver_uses_manifest_selected_webp_extension(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        [
            {
                "asset_id": "ui_test_item",
                "category": "ui",
                "slot": {"ui_id": "test_item"},
                "file": "assets/ui/test_item.webp",
                "format": "webp",
                "width": 512,
                "height": 512,
                "quality_tier": "balanced",
            }
        ],
    )
    resolved = manager.resolve_ui_asset("test_item")
    assert resolved is not None
    assert resolved.path.name == "test_item.webp"


def test_unknown_item_key_fails_closed() -> None:
    root = Path(__file__).resolve().parents[1]
    manager = AssetManager(
        DummyConfig(),
        type(
            "Storage",
            (),
            {
                "addon_dir": root / "ankigarden",
                "assets_root": root / "ankigarden/assets",
                "load_asset_metadata": lambda _self: {},
                "save_asset_metadata": lambda _self, _value: None,
            },
        )(),
    )
    assert manager.resolve_ui_asset("does_not_exist") is None


def test_missing_expected_item_artwork_warning_is_deduplicated(caplog, tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        [
            {
                "asset_id": "ui_missing_item",
                "category": "ui",
                "slot": {"ui_id": "missing_item"},
                "file": "assets/ui/missing_item.webp",
                "format": "webp",
                "width": 512,
                "height": 512,
                "quality_tier": "balanced",
            }
        ],
    )
    (tmp_path / "assets/ui/missing_item.webp").unlink()
    with caplog.at_level(logging.WARNING):
        assert manager.resolve_ui_asset("missing_item") is None
        assert manager.resolve_ui_asset("missing_item") is None
    warnings = [
        record
        for record in caplog.records
        if "expected item artwork could not be resolved" in record.message
    ]
    assert len(warnings) == 1
    assert "missing_item" in warnings[0].message
    assert "ui_missing_item" in warnings[0].message
