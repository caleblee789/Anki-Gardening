from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict

from .models.state import GardenState, Plant


logger = logging.getLogger(__name__)


class GardenStorage:
    def __init__(self, mw: Any, config: Any) -> None:
        self.mw = mw
        self.config = config
        self.addon_dir = Path(__file__).parent
        # Anki removes everything outside user_files/ when an add-on is upgraded.
        # Progress and mutable metadata must therefore never live beside source.
        self.user_files_dir = self.addon_dir / "user_files"
        self.data_path = self.user_files_dir / "garden_state.json"
        self.assets_root = self.addon_dir / "assets"
        self.metadata_dir = self.user_files_dir
        self.cache_dir = self.user_files_dir / "cache"
        self.asset_metadata = self.user_files_dir / "asset_metadata.json"
        self.state = self._load()
        self._ensure_defaults()

    def _load(self) -> GardenState:
        try:
            if self.data_path.exists():
                raw = json.loads(self.data_path.read_text("utf-8"))
                if isinstance(raw, dict) and int(raw.get("version", GardenState().version)) != GardenState().version:
                    backup = self.data_path.with_suffix(".legacy.json")
                    shutil.copy2(self.data_path, backup)
                    logger.warning("Anki Garden: legacy state preserved at %s; starting the focused garden format", backup)
                    return GardenState()
                return GardenState.from_dict(raw)
        except Exception:
            logger.exception("Anki Garden: saved state is unreadable; preserving it and starting fresh")
            try:
                backup = self.data_path.with_suffix(".invalid.json")
                shutil.copy2(self.data_path, backup)
            except Exception:
                logger.exception("Anki Garden: could not preserve invalid state")
        return GardenState()

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tf:
            json.dump(payload, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        Path(temp_name).replace(path)

    def save(self) -> None:
        self._atomic_write_json(self.data_path, self.state.to_dict())

    def _ensure_defaults(self) -> None:
        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.state.plants:
            starters = [("bonsai", "streak"), ("rose", "accuracy")]
            for idx, species in enumerate(starters[: self.config.value("initial_slots", 2)]):
                name, personality = species
                self.state.plants.append(
                    Plant(
                        plant_id=f"plant_{idx+1}",
                        species=name,
                        name=name.capitalize(),
                        slot_index=idx,
                        personality=personality,
                    )
                )
        self.save()

    def load_asset_metadata(self) -> dict:
        if not self.asset_metadata.exists():
            return {}
        try:
            return json.loads(self.asset_metadata.read_text("utf-8"))
        except Exception:
            return {}

    def save_asset_metadata(self, data: dict) -> None:
        self._atomic_write_json(self.asset_metadata, data)

    def max_revlog_id(self) -> int:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            return 0
        try:
            rows = collection.db.first("select max(id) from revlog")
            if rows and rows[0]:
                return int(rows[0])
        except Exception:
            pass
        return 0

    def load_new_revlog_entries(self, after_id: int, limit: int = 6000) -> list[tuple[Any, ...]]:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            return []
        try:
            return collection.db.all(
                "select id, cid, ease, ivl, lastIvl, factor, time, type from revlog where id > ? order by id asc limit ?",
                int(after_id),
                int(limit),
            )
        except Exception:
            logger.exception("Anki Garden: unable to read new review history")
            return []

    def current_day_cutoff_ms(self) -> int:
        """Return the start of Anki's current scheduler day in milliseconds."""
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "sched", None) is None:
            return 0
        try:
            sched = collection.sched
            cutoff = getattr(sched, "day_cutoff", getattr(sched, "dayCutoff", None))
            if cutoff is None:
                return 0
            return max(0, (int(cutoff) - 86_400) * 1000)
        except Exception:
            return 0
