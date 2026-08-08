from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict

from .models.state import GardenState, Plant, PlantMemory


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalReviewPreview:
    start_date: str
    end_date: str
    eligible_reviews: int
    importable_days: tuple[str, ...]
    skipped_days: tuple[str, ...]
    reviews: tuple[dict[str, Any], ...]
    error: str = ""


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
                version = int(raw.get("version", GardenState().version)) if isinstance(raw, dict) else -1
                if version not in (8, 9, GardenState().version):
                    backup = self.data_path.with_suffix(".legacy.json")
                    shutil.copy2(self.data_path, backup)
                    logger.warning("Anki Garden: unsupported state preserved at %s; starting the focused garden format", backup)
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
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tf:
                json.dump(payload, tf, indent=2, ensure_ascii=False)
                tf.flush()
                temp_path = Path(tf.name)
            temp_path.replace(path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def save(self) -> None:
        self._atomic_write_json(self.data_path, self.state.to_dict())

    def _ensure_defaults(self) -> None:
        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.state.plants:
            starters = [("bonsai", "streak", "Moss"), ("rose", "accuracy", "Briar")]
            for idx, species in enumerate(starters[: self.config.value("initial_slots", 2)]):
                name, personality, generated_name = species
                today = GardenState().daily_stats.day
                self.state.plants.append(
                    Plant(
                        plant_id=f"plant_{idx+1}",
                        species=name,
                        name=generated_name,
                        slot_index=idx,
                        personality=personality,
                        planted_on=today,
                        memories=[PlantMemory("planted", "planted", today)],
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

    def review_type_for_revlog_id(self, revlog_id: int) -> int | None:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None or int(revlog_id) <= 0:
            return None
        try:
            value = collection.db.scalar("select type from revlog where id = ?", int(revlog_id))
            return int(value) if value is not None else None
        except Exception:
            return None

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
            cutoff = getattr(sched, "day_cutoff", None)
            if cutoff is None:
                cutoff = getattr(sched, "dayCutoff", None)
            if cutoff is None:
                return 0
            return max(0, (int(cutoff) - 86_400) * 1000)
        except Exception:
            return 0

    def historical_review_bounds(self) -> tuple[str, str] | None:
        collection = getattr(self.mw, "col", None)
        today_start = self.current_day_cutoff_ms()
        if collection is None or getattr(collection, "db", None) is None or today_start <= 0:
            return None
        try:
            row = collection.db.first(
                "select min(id), max(id) from revlog where id < ? and type in (0, 1, 2, 3)",
                today_start,
            )
            if not row or not row[0] or not row[1]:
                return None
            return self._anki_day_for_ms(int(row[0])), self._anki_day_for_ms(int(row[1]))
        except Exception:
            logger.exception("Anki Garden: unable to inspect historical review bounds")
            return None

    def preview_historical_reviews(self, start_date: str, end_date: str) -> HistoricalReviewPreview:
        try:
            start = date.fromisoformat(str(start_date))
            end = date.fromisoformat(str(end_date))
        except ValueError:
            return HistoricalReviewPreview(str(start_date), str(end_date), 0, (), (), (), "Choose valid dates.")
        if start > end:
            return HistoricalReviewPreview(start.isoformat(), end.isoformat(), 0, (), (), (), "Start date must be on or before end date.")
        if end >= date.today():
            return HistoricalReviewPreview(start.isoformat(), end.isoformat(), 0, (), (), (), "Review history can only be applied through yesterday.")
        requested = tuple(
            (start + timedelta(days=offset)).isoformat()
            for offset in range((end - start).days + 1)
        )
        already_imported = set(self.state.imported_history_days)
        skipped = tuple(day for day in requested if day in already_imported)
        importable = tuple(day for day in requested if day not in already_imported)
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            return HistoricalReviewPreview(
                start.isoformat(), end.isoformat(), 0, importable, skipped, (),
                "Open an Anki collection before importing history.",
            )
        reviews: list[dict[str, Any]] = []
        try:
            for day in importable:
                lower, upper = self._anki_day_bounds_ms(day)
                rows = collection.db.all(
                    "select id, cid, ease, ivl, lastIvl, factor, time, type from revlog "
                    "where id >= ? and id < ? and type in (0, 1, 2, 3) order by id asc",
                    lower,
                    upper,
                )
                for rid, cid, ease, ivl, last_ivl, factor, elapsed, qtype in rows:
                    deck_id = None
                    try:
                        deck_id = int(collection.get_card(int(cid)).did)
                    except Exception:
                        pass
                    reviews.append({
                        "revlog_id": int(rid),
                        "day": day,
                        "ease": int(ease),
                        "interval": int(ivl),
                        "last_interval": int(last_ivl),
                        "factor": int(factor),
                        "elapsed_ms": int(elapsed),
                        "review_type": int(qtype),
                        "deck_id": deck_id,
                    })
        except Exception:
            logger.exception("Anki Garden: unable to preview historical reviews")
            return HistoricalReviewPreview(
                start.isoformat(), end.isoformat(), 0, importable, skipped, (),
                "Anki could not read that review-history range.",
            )
        return HistoricalReviewPreview(
            start.isoformat(), end.isoformat(), len(reviews), importable, skipped, tuple(reviews)
        )

    def _anki_day_for_ms(self, timestamp_ms: int) -> str:
        today_start = self.current_day_cutoff_ms()
        if today_start <= 0:
            return datetime.fromtimestamp(timestamp_ms / 1000).date().isoformat()
        anchor = datetime.fromtimestamp(today_start / 1000).astimezone()
        candidate = datetime.fromtimestamp(timestamp_ms / 1000).astimezone()
        cutoff = (anchor.hour, anchor.minute, anchor.second)
        if (candidate.hour, candidate.minute, candidate.second) < cutoff:
            candidate -= timedelta(days=1)
        return candidate.date().isoformat()

    def _anki_day_bounds_ms(self, day_value: str) -> tuple[int, int]:
        requested = date.fromisoformat(day_value)
        today_start = self.current_day_cutoff_ms()
        if today_start <= 0:
            start = datetime.combine(requested, datetime.min.time()).astimezone()
        else:
            anchor = datetime.fromtimestamp(today_start / 1000).astimezone()
            start = anchor.replace(year=requested.year, month=requested.month, day=requested.day)
        next_day = requested + timedelta(days=1)
        end = start.replace(year=next_day.year, month=next_day.month, day=next_day.day)
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)
