"""Uninstall-independent storage and one-time, all-or-nothing migration."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Iterator


@dataclass(frozen=True)
class StoragePaths:
    data_dir: Path
    addon_dir: Path

    @classmethod
    def resolve(cls, mw: Any, *, base_dir: Path | None = None,
                addon_dir: Path | None = None) -> StoragePaths:
        base = base_dir if base_dir is not None else getattr(getattr(mw, "pm", None), "base", None)
        if not base or not Path(base).is_absolute():
            raise RuntimeError("Garden could not locate Anki's data directory; no progress was changed.")
        return cls(Path(base) / "anki-garden-data", addon_dir or Path(__file__).parent)

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _migration_lock(data_dir: Path) -> Iterator[None]:
    """OS-held lock releases on crashes; the stable lock file is never removed."""
    from .storage import StatePreservationError
    with (data_dir.parent / ".anki-garden-migration.lock").open("a+b") as handle:
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            yield
        except BlockingIOError as exc:
            raise StatePreservationError("Another Garden instance is preparing saved progress. Close it and restart Anki.") from exc
        finally:
            if locked:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _copy_legacy_database(source: Path, destination: Path) -> None:
    # Open the original read-only: RewardLedger's constructor may migrate a
    # schema. SQLite's online backup includes committed WAL data without
    # copying a potentially inconsistent family of live database files.
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader:
        with closing(sqlite3.connect(destination)) as writer:
            reader.backup(writer)


def open_persistent_garden(mw: Any, *, paths: StoragePaths | None = None):
    """Return configuration and storage only after complete migration publication."""
    from .config import ConfigManager
    from .storage import GardenStorage, REWARD_DATABASE_FILENAME, StatePreservationError

    paths = paths or StoragePaths.resolve(mw)
    try:
        if not paths.data_dir.exists():
            with _migration_lock(paths.data_dir):
                if not paths.data_dir.exists():
                    legacy_config = ConfigManager(mw)
                    with TemporaryDirectory(prefix=".anki-garden-migration-", dir=paths.data_dir.parent) as temporary:
                        stage = Path(temporary) / "data"
                        stage.mkdir()
                        legacy = paths.addon_dir / "user_files"
                        database = legacy / REWARD_DATABASE_FILENAME
                        if database.exists():
                            _copy_legacy_database(database, stage / REWARD_DATABASE_FILENAME)
                        elif (legacy / "garden_state.json").exists():
                            shutil.copyfile(legacy / "garden_state.json", stage / "garden_state.json")
                        atomic_write_json(stage / "settings.json", legacy_config._config)
                        staged = GardenStorage(mw, legacy_config, deferred=True,
                                               data_dir=stage, addon_dir=paths.addon_dir)
                        try:
                            staged._reward_ledger.integrity_check()
                            staged._reward_ledger.reset_economy_projections()
                            staged.refresh_lifetime_economy_aggregates()
                        finally:
                            staged.close()
                        # Under the OS lock no second initializer can publish.
                        # Never replace a directory that already contains data.
                        if paths.data_dir.exists():
                            raise StatePreservationError("Garden's destination appeared during migration. Restart Anki to use it.")
                        stage.rename(paths.data_dir)
        # A published directory is authoritative even if damaged/incomplete.
        # Never fall back to stale installed files or create a new database here.
        if not (paths.data_dir / REWARD_DATABASE_FILENAME).is_file():
            raise StatePreservationError("Garden's saved database is missing from its existing data directory.")
        config = ConfigManager(mw, settings_path=paths.settings_path)
        storage = GardenStorage(mw, config, deferred=True,
                                data_dir=paths.data_dir, addon_dir=paths.addon_dir)
        return config, storage
    except Exception as exc:
        raise StatePreservationError(
            f"Garden could not open saved progress at {paths.data_dir}. "
            "Existing progress was preserved. Check disk space and folder permissions; "
            f"if data is damaged, restore a valid copy before restarting Garden. Details: {exc}"
        ) from exc
