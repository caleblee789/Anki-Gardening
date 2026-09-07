from __future__ import annotations

"""Disposable, paged review index. Anki and the reward ledger remain authorities.

The object carries only a path; every operation owns its SQLite connection,
so collection-query and computation jobs never share a connection across
threads. An unfinished scan is never exposed as a verified history.
"""

from contextlib import closing
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterable, Iterator, Mapping

from .achievements import (
    ACHIEVEMENT_DEFINITIONS, AchievementHistory, AchievementProgressMetric,
    HistoricalDaySummary,
)


INDEX_VERSION = 2
HISTORY_PAGE_SIZE = 2_000
_FIELDS = "id, cid, ease, ivl, last_ivl, factor, elapsed, type, day"


class SchedulerDayMapper:
    """Resolve local/DST cutoffs once per day instead of once per answer."""

    def __init__(self, cutoff: datetime) -> None:
        self.cutoff = cutoff.time()
        self.lower_ms = self.upper_ms = 0
        self.day = ""

    def __call__(self, answered_at_ms: int) -> str:
        if self.lower_ms <= answered_at_ms < self.upper_ms:
            return self.day
        local = datetime.fromtimestamp(answered_at_ms / 1000)
        boundary = datetime.combine(local.date(), self.cutoff)
        day = local.date() if local >= boundary else local.date() - timedelta(days=1)
        lower = datetime.combine(day, self.cutoff)
        upper = datetime.combine(day + timedelta(days=1), self.cutoff)
        self.lower_ms = int(lower.timestamp() * 1000)
        self.upper_ms = int(upper.timestamp() * 1000)
        # Ambiguous or nonexistent cutoff clocks must retain the reference's
        # wall-clock comparison on every row through a DST transition.
        if (
            self.upper_ms - self.lower_ms != 86_400_000
            or datetime.fromtimestamp(self.lower_ms / 1000) != lower
            or datetime.fromtimestamp(self.upper_ms / 1000) != upper
        ):
            self.lower_ms = self.upper_ms = 0
        self.day = day.isoformat()
        return self.day


class HistoryIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=1)
        connection.row_factory = sqlite3.Row
        return connection

    def begin_scan(self, boundary: str) -> None:
        try:
            self._begin_scan(boundary)
        except sqlite3.DatabaseError:
            # Only this disposable index is replaced. Keep the failed file
            # for diagnostics; Anki and Garden's authority are untouched.
            if self.path.exists():
                self.path.replace(self.path.with_name(self.path.name + f".invalid-{time.time_ns()}"))
            self._begin_scan(boundary)

    def _begin_scan(self, boundary: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS review (
                    id INTEGER PRIMARY KEY, cid INTEGER NOT NULL, ease INTEGER NOT NULL,
                    ivl INTEGER NOT NULL, last_ivl INTEGER NOT NULL, factor INTEGER NOT NULL,
                    elapsed INTEGER NOT NULL, type INTEGER NOT NULL, day TEXT NOT NULL,
                    ordinal INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS review_card ON review(cid, id);
                CREATE INDEX IF NOT EXISTS review_day ON review(day, id);
                CREATE TABLE IF NOT EXISTS day_summary (day TEXT PRIMARY KEY, payload TEXT NOT NULL, payload_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scan_seen (id INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS dirty_day (day TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS planned_lineage (id INTEGER PRIMARY KEY, lineage TEXT NOT NULL);
            """)
            previous = dict(db.execute("SELECT key, value FROM metadata"))
            if "payload_hash" not in {row[1] for row in db.execute("PRAGMA table_info(day_summary)")}:
                db.execute("ALTER TABLE day_summary ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
            if previous.get("version") not in (None, str(INDEX_VERSION)):
                # This database contains no authoritative state.
                db.execute("DELETE FROM review")
                db.execute("DELETE FROM day_summary")
            db.execute("DELETE FROM scan_seen")
            db.execute("DELETE FROM planned_lineage")
            if previous.get("ready") != "1" or previous.get("boundary") != boundary:
                db.execute("INSERT OR IGNORE INTO dirty_day SELECT DISTINCT day FROM review")
            for day, payload, checksum in db.execute("SELECT day, payload, payload_hash FROM day_summary"):
                if hashlib.sha256(payload.encode()).hexdigest() != checksum:
                    db.execute("INSERT OR IGNORE INTO dirty_day VALUES (?)", (day,))
            db.executemany(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
                (("version", str(INDEX_VERSION)), ("boundary", boundary), ("ready", "0")),
            )

    def ingest(self, rows: Iterable[tuple[Any, ...]], day_for_id: Callable[[int], str]) -> int:
        values = [tuple(int(value) for value in row[:8]) for row in rows]
        if not values:
            return 0
        if any(len(row) != 8 or row[0] <= 0 or row[1] <= 0 or row[2] not in (1, 2, 3, 4)
               or row[7] not in (0, 1, 2, 3) for row in values):
            raise ValueError("Invalid eligible review history")
        with closing(self._connect()) as db, db:
            existing = {
                int(row[0]): tuple(row)
                for row in db.execute(
                    f"SELECT {_FIELDS} FROM review WHERE id >= ? AND id <= ?",
                    (values[0][0], values[-1][0]),
                )
            }
            changed = []
            dirty = set()
            for raw in values:
                entry = (*raw, day_for_id(raw[0]))
                old = existing.get(raw[0])
                if old != entry:
                    changed.append(entry)
                    dirty.add(entry[-1])
                    if old is not None:
                        dirty.add(old[-1])
            db.executemany("INSERT OR IGNORE INTO scan_seen VALUES (?)", ((row[0],) for row in values))
            db.executemany(
                f"INSERT OR REPLACE INTO review ({_FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", changed,
            )
            db.executemany("INSERT OR IGNORE INTO dirty_day VALUES (?)", ((day,) for day in dirty))
        return len(changed)

    @staticmethod
    def _rebuild_day(db: sqlite3.Connection, day: str) -> None:
        count = again = prefix = tail = longest = 0
        first = last = 0
        digest = hashlib.sha256()
        ordinals = []
        for row in db.execute(f"SELECT {_FIELDS} FROM review WHERE day = ? ORDER BY id", (day,)):
            count += 1
            first = first or int(row[0])
            last = int(row[0])
            if row[2] == 1:
                again += 1
                tail = 0
            else:
                tail += 1
                if again == 0:
                    prefix += 1
                longest = max(longest, tail)
            digest.update(json.dumps(tuple(row), separators=(",", ":")).encode())
            ordinals.append((count, int(row[0])))
            if len(ordinals) == HISTORY_PAGE_SIZE:
                db.executemany("UPDATE review SET ordinal = ? WHERE id = ?", ordinals)
                ordinals.clear()
        db.executemany("UPDATE review SET ordinal = ? WHERE id = ?", ordinals)
        if not count:
            db.execute("DELETE FROM day_summary WHERE day = ?", (day,))
            return
        payload = dict(day=day, total=count, again=again, prefix=prefix, tail=tail,
                       longest=longest, first=first, last=last, digest=digest.hexdigest())
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        db.execute("INSERT OR REPLACE INTO day_summary VALUES (?, ?, ?)",
                   (day, encoded, hashlib.sha256(encoded.encode()).hexdigest()))

    def finish_scan(self, *, prune: bool = True) -> dict[str, int]:
        with closing(self._connect()) as db, db:
            deleted = 0
            if prune:
                db.execute("INSERT OR IGNORE INTO dirty_day SELECT DISTINCT day FROM review "
                           "WHERE NOT EXISTS (SELECT 1 FROM scan_seen WHERE scan_seen.id = review.id)")
                deleted = db.execute("DELETE FROM review WHERE NOT EXISTS "
                                     "(SELECT 1 FROM scan_seen WHERE scan_seen.id = review.id)").rowcount
            dirty = [row[0] for row in db.execute("SELECT day FROM dirty_day ORDER BY day")]
            for day in dirty:
                self._rebuild_day(db, day)
            db.execute("DELETE FROM dirty_day")
            db.execute("DELETE FROM scan_seen")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('ready', '1')")
            return {"deleted": deleted, "rebuilt_days": len(dirty)}

    def summaries(self) -> tuple[dict[str, Any], ...]:
        with closing(self._connect()) as db:
            ready = db.execute("SELECT value FROM metadata WHERE key = 'ready'").fetchone()
            if ready is None or ready[0] != "1":
                raise ValueError("Review history verification is incomplete")
            return tuple(json.loads(row[0]) for row in db.execute("SELECT payload FROM day_summary ORDER BY day"))

    def card_rows(self, card_id: int) -> list[tuple[int, int, str]]:
        with closing(self._connect()) as db:
            return [tuple(row) for row in db.execute("SELECT id, cid, day FROM review WHERE cid = ? ORDER BY id", (int(card_id),))]

    def pending_undo_hint(self, ledger_path: str | Path) -> tuple[int, str, int] | None:
        """Resolve the existing orphan-lineage rule against verified history."""
        with closing(self._connect()) as db:
            db.execute("ATTACH DATABASE ? AS rewards", (str(ledger_path),))
            pending = db.execute("SELECT undo_id, occurred_at_ms FROM rewards.deferred_review_undo ORDER BY undo_id LIMIT 1").fetchone()
            if pending is None:
                return None
            orphan = db.execute(
                "SELECT a.revlog_id, a.lineage_key FROM rewards.revlog_alias a "
                "JOIN rewards.answer_lineage l ON l.lineage_key=a.lineage_key "
                "LEFT JOIN review r ON r.id=a.revlog_id "
                "WHERE r.id IS NULL AND l.reanswer_floor=0 AND NOT EXISTS ("
                "SELECT 1 FROM rewards.revlog_alias b JOIN review current ON current.id=b.revlog_id "
                "WHERE b.lineage_key=a.lineage_key) ORDER BY a.revlog_id DESC LIMIT 1"
            ).fetchone()
            return (int(pending[0]), str(orphan[1]) if orphan else "",
                    max(int(pending[1]), int(orphan[0]) + 1 if orphan else 0))

    def prepare_alias_page(self, ledger_path: str | Path, *, limit: int = 256, after_id: int = 0) -> list[tuple[int, str]]:
        """Plan complete card lineages off-thread, commit their aliases in pages.

        Pre-activation aliases are retained as in the full-history reader.
        Planning the entire card before committing a page prevents a later
        page from assigning a different serial to an earlier unbound answer.
        """
        from .storage import assign_stable_answer_identities
        with closing(self._connect()) as db, db:
            db.execute("ATTACH DATABASE ? AS rewards", (str(ledger_path),))
            rows = list(db.execute(
                "SELECT r.id, r.cid, p.lineage FROM review r "
                "LEFT JOIN rewards.revlog_alias a ON a.revlog_id=r.id "
                "LEFT JOIN planned_lineage p ON p.id=r.id "
                "WHERE r.id > ? AND a.revlog_id IS NULL ORDER BY r.id LIMIT ?", (int(after_id), int(limit)),
            ))
            cards = {int(row[1]) for row in rows if row[2] is None}
            planned = {int(row[0]): str(row[2]) for row in rows if row[2] is not None}
            for card_id in cards:
                bindings = {str(row[0]): str(row[1]) for row in db.execute(
                    "SELECT a.revlog_id, a.lineage_key FROM rewards.revlog_alias a "
                    "JOIN rewards.answer_lineage l ON l.lineage_key=a.lineage_key WHERE l.card_id=?", (card_id,),
                )}
                hints = {str(row[0]): int(row[1]) for row in db.execute(
                    "SELECT lineage_key, reanswer_floor FROM rewards.answer_lineage WHERE card_id=? AND reanswer_floor>0",
                    (card_id,),
                )}
                identities, _bindings = assign_stable_answer_identities(
                    (tuple(row) for row in db.execute("SELECT id, cid, day FROM review WHERE cid=? ORDER BY id", (card_id,))),
                    bindings, hints,
                )
                db.executemany("INSERT OR REPLACE INTO planned_lineage VALUES (?,?)", identities.items())
                planned.update(identities)
            return [(int(row[0]), planned[int(row[0])]) for row in rows]

    def reward_pages(self, *, activation_ms: int, through_day: str, ledger_path: str | Path,
                     limit: int | None = None, after_id: int = 0) -> Iterator[list[tuple[Any, ...]]]:
        """Read only unconsumed post-activation answers, with exact day ordinals."""
        with closing(self._connect()) as db:
            db.execute("ATTACH DATABASE ? AS rewards", (str(ledger_path),))
            cursor = db.execute(
                "SELECT r.id, r.cid, r.ease, r.ivl, r.last_ivl, r.factor, r.elapsed, r.type, r.day, r.ordinal "
                "FROM review r LEFT JOIN rewards.revlog_alias a ON a.revlog_id = r.id "
                "LEFT JOIN rewards.answer_consumption c ON c.lineage_key = a.lineage_key "
                "WHERE r.id >= ? AND r.day <= ? AND c.answer_key IS NULL ORDER BY r.id LIMIT ?",
                (max(1, int(activation_ms), int(after_id) + 1), str(through_day), -1 if limit is None else max(1, int(limit))),
            )
            while rows := cursor.fetchmany(HISTORY_PAGE_SIZE):
                yield [tuple(row) for row in rows]

    def append_committed(self, row: tuple[Any, ...], day: str) -> None:
        """Advance the disposable open-day summary after a proven local commit."""
        values = tuple(int(value) for value in row[:8])
        with closing(self._connect()) as db, db:
            if db.execute("SELECT 1 FROM review WHERE id = ?", (values[0],)).fetchone():
                return
            last = db.execute("SELECT max(id) FROM review WHERE day=?", (day,)).fetchone()[0] or 0
            if values[0] <= last:
                raise ValueError("A non-appended answer requires history verification")
            stored = db.execute("SELECT payload FROM day_summary WHERE day = ?", (day,)).fetchone()
            summary = json.loads(stored[0]) if stored else dict(day=day, total=0, again=0, prefix=0,
                                                               tail=0, longest=0, first=values[0], last=0, digest="")
            summary["total"] += 1
            summary["last"] = values[0]
            if values[2] == 1:
                summary["again"] += 1
                summary["tail"] = 0
            else:
                summary["tail"] += 1
                if not summary["again"]:
                    summary["prefix"] += 1
                summary["longest"] = max(summary["longest"], summary["tail"])
            # Full source fingerprints are reconstructed at the next scan.
            summary["digest"] = hashlib.sha256((summary["digest"] + repr(values)).encode()).hexdigest()
            db.execute(f"INSERT INTO review ({_FIELDS}, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (*values, day, summary["total"]))
            encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"))
            db.execute("INSERT OR REPLACE INTO day_summary VALUES (?, ?, ?)",
                       (day, encoded, hashlib.sha256(encoded.encode()).hexdigest()))


def analyze_indexed_days(
    days: Iterable[Mapping[str, Any]], *, current_open_day: str, include_open_day: bool = True,
) -> AchievementHistory:
    """Compose daily sufficient statistics without revisiting individual answers."""
    today = date.fromisoformat(current_open_day)
    eligible = [dict(day) for day in days if str(day["day"]) < current_open_day
                or (include_open_day and str(day["day"]) == current_open_day)]
    eligible.sort(key=lambda day: day["day"])
    lifetime = streak = maximum_streak = tail = longest = 0
    previous = None
    unlocks: dict[str, str] = {}
    summaries = []
    for day in eligible:
        day_value = str(day["day"])
        moment = date.fromisoformat(day_value)
        lifetime += int(day["total"])
        streak = streak + 1 if previous is not None and moment == previous + timedelta(days=1) else 1
        maximum_streak = max(maximum_streak, streak)
        longest = max(longest, int(day["longest"]), tail + int(day["prefix"]))
        tail = tail + int(day["total"]) if not day["again"] else int(day["tail"])
        values = {
            AchievementProgressMetric.LIFETIME_ANSWERS: lifetime,
            AchievementProgressMetric.DAILY_ANSWERS: int(day["total"]),
            AchievementProgressMetric.STREAK_DAYS: streak,
        }
        for definition in ACHIEVEMENT_DEFINITIONS:
            if definition.historical_backfill and values.get(definition.progress_metric, -1) >= definition.progress_target:
                unlocks.setdefault(definition.achievement_id, day_value)
        summaries.append(HistoricalDaySummary(day_value, int(day["total"]),
                                              int(day["total"]) - int(day["again"]), int(day["again"]), moment < today))
        previous = moment
    active_days = {date.fromisoformat(day["day"]) for day in eligible}
    studied_today = today in active_days
    cursor = today if studied_today else today - timedelta(days=1)
    current_streak = 0
    while cursor in active_days:
        current_streak += 1
        cursor -= timedelta(days=1)
    digest = hashlib.sha256(json.dumps([INDEX_VERSION, current_open_day, include_open_day, eligible],
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return AchievementHistory(
        current_open_day, lifetime, tuple(summaries), unlocks, maximum_streak, current_streak,
        eligible[-1]["day"] if eligible else "", studied_today, tail, longest, digest,
    )
