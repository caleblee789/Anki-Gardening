from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from ankigarden.config import ConfigError, ConfigManager
from ankigarden.models.state import GardenState, STATE_VERSION
from ankigarden.persistence import StoragePaths, _migration_lock, open_persistent_garden
from ankigarden.storage import GardenStorage, StatePreservationError


def environment(base: Path):
    base.mkdir(exist_ok=True)
    addon = base / "addons21" / "garden"
    addon.mkdir(parents=True, exist_ok=True)
    manager = SimpleNamespace(
        addonFromModule=lambda _module: "garden",
        getConfig=lambda _key: {"enable_animations": False, "onboarding_version": 3},
    )
    mw = SimpleNamespace(pm=SimpleNamespace(base=str(base)), addonManager=manager)
    return mw, StoragePaths.resolve(mw, addon_dir=addon)


def test_reinstall_preserves_wal_progress_settings_and_reward_authority(tmp_path):
    mw, paths = environment(tmp_path)
    legacy = paths.addon_dir / "user_files"
    legacy.mkdir()
    state = GardenState(garden_name="My saved garden", total_reviews=42)
    state.processed_answer_keys = ["answer:already-consumed"]
    state.applied_reward_event_keys = ["reward:already-applied"]
    (legacy / "garden_state.json").write_text(json.dumps(state.to_dict()))
    original = GardenStorage(mw, ConfigManager(mw), deferred=True,
                             addon_dir=paths.addon_dir, data_dir=legacy)
    try:
        original.runtime_pending = False
        original.state.garden_name = "Committed in WAL"
        original.save()
        assert Path(str(original.database_path) + "-wal").stat().st_size > 0
        config, storage = open_persistent_garden(mw, paths=paths)
        try:
            assert storage.state.garden_name == "Committed in WAL"
            assert storage.state.total_reviews == 42
            assert storage.answer_consumed("answer:already-consumed")
            assert storage.reward_applied("reward:already-applied")
            config.update({"reviewer_hud_dock": "left"})
            storage.runtime_pending = False
            storage.state.garden_name = "Latest durable save"
            storage.save()
        finally:
            storage.close()
    finally:
        original.close()
    shutil.rmtree(paths.addon_dir)
    paths.addon_dir.mkdir()
    # A stale install must never override the durable store.
    (paths.addon_dir / "user_files").mkdir()
    (paths.addon_dir / "user_files" / "garden_state.json").write_text("corrupt stale data")
    config, storage = open_persistent_garden(mw, paths=paths)
    try:
        assert config.value("reviewer_hud_dock") == "left"
        assert config.value("enable_animations") is False
        assert config.value("onboarding_version") == 3
        assert storage.state.garden_name == "Latest durable save"
        assert storage.answer_consumed("answer:already-consumed")
        assert storage.reward_applied("reward:already-applied")
        state_reference = storage.state
        storage.close()
        mw.pm.name = "Another profile"
        storage.reopen()
        assert storage.state is state_reference
        assert storage.state.garden_name == "Latest durable save"
        other_mw, other_paths = environment(tmp_path / "other-base")
        _, other = open_persistent_garden(other_mw, paths=other_paths)
        try:
            assert not other.answer_consumed("answer:already-consumed")
            assert other.state.total_reviews == 0
        finally:
            other.close()
    finally:
        storage.close()


@pytest.mark.parametrize("kind", ["bad-json", "future-json", "bad-sqlite", "future-sqlite"])
def test_failed_migration_never_publishes_or_changes_original(tmp_path, kind):
    mw, paths = environment(tmp_path)
    legacy = paths.addon_dir / "user_files"
    legacy.mkdir()
    if kind.endswith("json"):
        source = legacy / "garden_state.json"
        source.write_text("broken" if kind == "bad-json" else json.dumps({"version": STATE_VERSION + 1}))
    else:
        source = legacy / "garden_state.sqlite3"
        if kind == "bad-sqlite":
            source.write_bytes(b"broken")
        else:
            with sqlite3.connect(source) as connection:
                connection.execute("PRAGMA user_version = 9999")
    before = source.read_bytes()
    with pytest.raises(StatePreservationError):
        open_persistent_garden(mw, paths=paths)
    assert source.read_bytes() == before
    assert not paths.data_dir.exists()


def test_interrupted_publication_retries_and_settings_failure_keeps_saved_value(tmp_path, monkeypatch):
    mw, paths = environment(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(StatePreservationError):
            open_persistent_garden(mw, paths=paths)
    assert not paths.data_dir.exists()
    config, storage = open_persistent_garden(mw, paths=paths)
    storage.close()
    with monkeypatch.context() as patch:
        patch.setattr("ankigarden.persistence.os.replace", lambda *_args: (_ for _ in ()).throw(OSError("read only")))
        with pytest.raises(ConfigError):
            config.update({"enable_animations": True})
    assert config.value("enable_animations") is False
    config.reload()
    assert config.value("enable_animations") is False


@pytest.mark.parametrize("damage", ["missing-database", "invalid-settings"])
def test_damaged_durable_store_does_not_fall_back_or_reset(tmp_path, damage):
    mw, paths = environment(tmp_path)
    _, storage = open_persistent_garden(mw, paths=paths)
    storage.close()
    if damage == "missing-database":
        (paths.data_dir / "garden_state.sqlite3").unlink()
    else:
        paths.settings_path.write_text("{broken")
    before = {p.name: p.read_bytes() for p in paths.data_dir.iterdir() if p.is_file()}
    with pytest.raises(StatePreservationError):
        open_persistent_garden(mw, paths=paths)
    assert {p.name: p.read_bytes() for p in paths.data_dir.iterdir() if p.is_file()} == before


def test_legacy_json_migration_retries_after_another_initializer_exits(tmp_path):
    mw, paths = environment(tmp_path)
    legacy = paths.addon_dir / "user_files"
    legacy.mkdir()
    source = legacy / "garden_state.json"
    original = json.dumps({"version": 10, "total_reviews": 321, "streak_days": 9})
    source.write_text(original)
    with _migration_lock(paths.data_dir):
        with pytest.raises(StatePreservationError):
            open_persistent_garden(mw, paths=paths)
        assert not paths.data_dir.exists()
    config, storage = open_persistent_garden(mw, paths=paths)
    try:
        assert storage.state.total_reviews == 321
        assert storage.state.streak_days == 9
        assert config.value("onboarding_version") == 3
        assert source.read_text() == original
    finally:
        storage.close()
