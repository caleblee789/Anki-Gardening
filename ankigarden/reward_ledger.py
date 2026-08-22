from __future__ import annotations

"""Transactional SQLite authority for rewards and per-answer outcomes.

The Garden's ordinary state can remain a bounded JSON-shaped document, but
exact replay prevention cannot be pruned.  This module stores that append-only
authority in indexed SQLite tables and commits it atomically with the supplied
bounded state document.

Writes are staged in memory until :meth:`RewardLedger.commit_state` is called.
Every read merges committed and staged rows, allowing a multi-answer sync batch
to observe the answers staged earlier in the same Garden transaction.
"""

from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
import uuid


LEDGER_SCHEMA_VERSION = 1
FIND_OUTCOME_STATUSES = frozenset({"miss", "hit", "paused"})
MAX_RECENT_HITS_QUERY = 1_000
_SQL_IN_CHUNK = 500
UNBOUNDED_STATE_AUTHORITY_KEYS = frozenset({
    "applied_reward_event_keys",
    "processed_answer_keys",
    "answer_lineage_bindings",
    "garden_find_outcomes",
    "garden_find_daily_counts",
    "garden_find_reward_daily_counts",
    "finalized_day_fingerprints",
})


class RewardLedgerError(RuntimeError):
    """Base error for reward-ledger failures."""


class RewardLedgerSchemaError(RewardLedgerError):
    """The database is not a supported reward-ledger schema."""


class RewardLedgerConflictError(RewardLedgerError):
    """An exact ledger identity already belongs to another committed row."""


class RewardLedgerRevisionConflict(RewardLedgerConflictError):
    """The bounded state changed after the caller took its snapshot."""


class RewardLedgerCheckpointError(RewardLedgerError):
    """A checkpoint does not belong to the current staged-write generation."""


class RewardLedgerCorruptionError(RewardLedgerError):
    """A committed row cannot be decoded without inventing state."""


class RewardLedgerClosedError(RewardLedgerError):
    """The ledger connection has already been closed."""


@dataclass(frozen=True)
class LedgerCheckpoint:
    owner_token: str
    generation: int
    operation_count: int
    prefix_operation_id: int


@dataclass(frozen=True)
class StateSnapshot:
    schema_version: int
    revision: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RewardEventRecord:
    event_key: str
    source: str = ""
    scheduler_day: str = ""
    occurred_at: str = ""


@dataclass(frozen=True)
class AnswerLineageRecord:
    lineage_key: str
    original_day: str
    card_id: int
    serial: int


@dataclass(frozen=True)
class RevlogAliasRecord:
    revlog_id: int
    lineage_key: str


@dataclass(frozen=True)
class AnswerConsumptionRecord:
    answer_key: str
    scheduler_day: str = ""
    occurred_at: str = ""
    lineage_key: str = ""
    first_revlog_id: int = 0


@dataclass(frozen=True)
class FindOutcomeRecord:
    answer_key: str
    scheduler_day: str
    pool_id: str
    pool_version: str
    status: str
    occurred_at: str
    reward_id: str = ""
    hit_payload: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class FindDayCounts:
    scheduler_day: str
    pool_id: str
    total_hits: int
    reward_counts: Mapping[str, int]


@dataclass(frozen=True)
class FinalizedDayRecord:
    scheduler_day: str
    fingerprint: str


@dataclass(frozen=True)
class _StagedFinalizedDay:
    record: FinalizedDayRecord
    replace: bool


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE state_snapshot (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version > 0),
        revision INTEGER NOT NULL CHECK (revision > 0),
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE reward_event (
        event_key TEXT PRIMARY KEY,
        source TEXT NOT NULL DEFAULT '',
        scheduler_day TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE answer_lineage (
        lineage_key TEXT PRIMARY KEY,
        original_day TEXT NOT NULL,
        card_id INTEGER NOT NULL CHECK (card_id > 0),
        serial INTEGER NOT NULL CHECK (serial > 0),
        UNIQUE (original_day, card_id, serial)
    )
    """,
    """
    CREATE TABLE revlog_alias (
        revlog_id INTEGER PRIMARY KEY CHECK (revlog_id > 0),
        lineage_key TEXT NOT NULL REFERENCES answer_lineage(lineage_key)
    )
    """,
    """
    CREATE TABLE answer_consumption (
        answer_key TEXT PRIMARY KEY,
        scheduler_day TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL DEFAULT '',
        lineage_key TEXT UNIQUE REFERENCES answer_lineage(lineage_key),
        first_revlog_id INTEGER NOT NULL DEFAULT 0 CHECK (first_revlog_id >= 0)
    )
    """,
    """
    CREATE TABLE find_outcome (
        recorded_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        answer_key TEXT NOT NULL REFERENCES answer_consumption(answer_key),
        scheduler_day TEXT NOT NULL,
        pool_id TEXT NOT NULL,
        pool_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('miss', 'hit', 'paused')),
        occurred_at TEXT NOT NULL,
        reward_id TEXT NOT NULL DEFAULT '',
        hit_payload_json TEXT,
        UNIQUE (answer_key, pool_id)
    )
    """,
    """
    CREATE TABLE finalized_day (
        scheduler_day TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL
    )
    """,
    "CREATE INDEX revlog_alias_lineage_idx ON revlog_alias(lineage_key)",
    "CREATE INDEX answer_lineage_card_idx ON answer_lineage(card_id)",
    """
    CREATE INDEX find_outcome_day_idx
    ON find_outcome(scheduler_day, pool_id, status, reward_id)
    """,
    """
    CREATE INDEX find_outcome_recent_hit_idx
    ON find_outcome(status, recorded_sequence DESC)
    """,
)

_REQUIRED_TABLES = frozenset({
    "state_snapshot",
    "reward_event",
    "answer_lineage",
    "revlog_alias",
    "answer_consumption",
    "find_outcome",
    "finalized_day",
})

_EXPECTED_COLUMNS = {
    "state_snapshot": (
        "singleton", "schema_version", "revision", "payload_json",
    ),
    "reward_event": (
        "event_key", "source", "scheduler_day", "occurred_at",
    ),
    "answer_lineage": (
        "lineage_key", "original_day", "card_id", "serial",
    ),
    "revlog_alias": ("revlog_id", "lineage_key"),
    "answer_consumption": (
        "answer_key", "scheduler_day", "occurred_at", "lineage_key",
        "first_revlog_id",
    ),
    "find_outcome": (
        "recorded_sequence", "answer_key", "scheduler_day", "pool_id",
        "pool_version", "status", "occurred_at", "reward_id",
        "hit_payload_json",
    ),
    "finalized_day": ("scheduler_day", "fingerprint"),
}

_EXPECTED_PRIMARY_KEYS = {
    "state_snapshot": ("singleton",),
    "reward_event": ("event_key",),
    "answer_lineage": ("lineage_key",),
    "revlog_alias": ("revlog_id",),
    "answer_consumption": ("answer_key",),
    "find_outcome": ("recorded_sequence",),
    "finalized_day": ("scheduler_day",),
}

_REQUIRED_UNIQUE_KEYS = {
    "answer_lineage": {("original_day", "card_id", "serial")},
    "answer_consumption": {("lineage_key",)},
    "find_outcome": {("answer_key", "pool_id")},
}

_REQUIRED_FOREIGN_KEYS = {
    "revlog_alias": {("lineage_key", "answer_lineage", "lineage_key")},
    "answer_consumption": {
        ("lineage_key", "answer_lineage", "lineage_key"),
    },
    "find_outcome": {
        ("answer_key", "answer_consumption", "answer_key"),
    },
}

_REQUIRED_NAMED_INDEXES = frozenset({
    "revlog_alias_lineage_idx",
    "answer_lineage_card_idx",
    "find_outcome_day_idx",
    "find_outcome_recent_hit_idx",
})


class RewardLedger:
    """One SQLite connection owning Garden reward and answer authority.

    The class intentionally does not import Garden model types.  Integration
    code converts the records here to and from its domain dataclasses.
    """

    def __init__(
        self,
        database: Union[str, Path],
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        raw_path = str(database)
        if raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        self.database = raw_path
        self._connection = sqlite3.connect(
            raw_path,
            timeout=max(0.1, float(timeout_seconds)),
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._checkpoint_owner = uuid.uuid4().hex
        self._generation = 0
        self._next_operation_id = 1
        self._operations: List[Tuple[int, str, Any]] = []
        self._pending_reward_events: Dict[str, RewardEventRecord] = {}
        self._pending_lineages: Dict[str, AnswerLineageRecord] = {}
        self._pending_lineage_coordinates: Dict[
            Tuple[str, int, int], AnswerLineageRecord
        ] = {}
        self._pending_aliases: Dict[int, RevlogAliasRecord] = {}
        self._pending_consumptions: Dict[str, AnswerConsumptionRecord] = {}
        self._pending_consumption_lineages: Dict[str, AnswerConsumptionRecord] = {}
        self._pending_outcomes: Dict[Tuple[str, str], FindOutcomeRecord] = {}
        self._pending_finalized_days: Dict[str, _StagedFinalizedDay] = {}
        try:
            self._configure_connection()
            self._initialize_or_validate_schema()
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def __enter__(self) -> "RewardLedger":
        self._ensure_open()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    @property
    def staged_write_count(self) -> int:
        return len(self._operations)

    @property
    def has_staged_writes(self) -> bool:
        return bool(self._operations)

    def close(self) -> None:
        """Close the connection, discarding writes that were never committed."""

        if self._closed:
            return
        self._clear_pending(increment_generation=True)
        self._connection.close()
        self._closed = True

    def integrity_check(self) -> None:
        """Raise if SQLite or its declared foreign-key authority is damaged."""

        self._ensure_open()
        rows = self._connection.execute("PRAGMA integrity_check").fetchall()
        messages = tuple(str(row[0]) for row in rows)
        if messages != ("ok",):
            raise RewardLedgerCorruptionError(
                "The reward-ledger integrity check failed: "
                + "; ".join(messages[:5])
            )
        foreign_key_rows = self._connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if foreign_key_rows:
            raise RewardLedgerCorruptionError(
                "The reward ledger contains broken authority relationships."
            )

    def backup_to(self, destination: Union[str, Path]) -> Path:
        """Create a complete, verified SQLite backup at a new path."""

        self._ensure_open()
        if self.has_staged_writes:
            raise RewardLedgerError(
                "Commit or roll back staged reward writes before creating a backup."
            )
        self.integrity_check()
        target = Path(destination)
        if target.exists():
            raise FileExistsError("The reward-ledger backup path already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(
            target.name + ".tmp-" + uuid.uuid4().hex
        )
        destination_connection: Optional[sqlite3.Connection] = None
        verification_connection: Optional[sqlite3.Connection] = None
        try:
            destination_connection = sqlite3.connect(str(temporary))
            self._connection.backup(destination_connection)
            destination_connection.close()
            destination_connection = None

            verification_connection = sqlite3.connect(str(temporary))
            integrity_result = tuple(
                str(row[0])
                for row in verification_connection.execute(
                    "PRAGMA integrity_check"
                ).fetchall()
            )
            version = int(
                verification_connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            )
            foreign_key_errors = verification_connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            verification_connection.close()
            verification_connection = None
            if (
                integrity_result != ("ok",)
                or version != LEDGER_SCHEMA_VERSION
                or foreign_key_errors
            ):
                raise RewardLedgerCorruptionError(
                    "The reward-ledger backup did not verify."
                )
            # Both paths share a directory/filesystem. Hard-link installation
            # is atomic and fails with EEXIST rather than replacing a file that
            # appeared after the initial validation.
            os.link(str(temporary), str(target))
            temporary.unlink()
            return target
        finally:
            if destination_connection is not None:
                destination_connection.close()
            if verification_connection is not None:
                verification_connection.close()
            if temporary.exists():
                temporary.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(temporary) + suffix)
                if sidecar.exists():
                    sidecar.unlink()

    def checkpoint(self) -> LedgerCheckpoint:
        self._ensure_open()
        return LedgerCheckpoint(
            self._checkpoint_owner,
            self._generation,
            len(self._operations),
            self._operations[-1][0] if self._operations else 0,
        )

    def rollback(self, checkpoint: LedgerCheckpoint) -> None:
        """Discard staged writes added after ``checkpoint``."""

        self._ensure_open()
        if (
            not isinstance(checkpoint, LedgerCheckpoint)
            or checkpoint.owner_token != self._checkpoint_owner
            or checkpoint.generation != self._generation
            or checkpoint.operation_count < 0
            or checkpoint.operation_count > len(self._operations)
            or (
                checkpoint.operation_count == 0
                and checkpoint.prefix_operation_id != 0
            )
            or (
                checkpoint.operation_count > 0
                and self._operations[checkpoint.operation_count - 1][0]
                != checkpoint.prefix_operation_id
            )
        ):
            raise RewardLedgerCheckpointError(
                "The reward-ledger checkpoint is no longer valid."
            )
        del self._operations[checkpoint.operation_count:]
        self._rebuild_pending_indexes()

    def rollback_all(self) -> None:
        self._ensure_open()
        self.rollback(LedgerCheckpoint(
            self._checkpoint_owner,
            self._generation,
            0,
            0,
        ))

    def load_state_snapshot(self) -> Optional[StateSnapshot]:
        self._ensure_open()
        row = self._connection.execute(
            "SELECT schema_version, revision, payload_json "
            "FROM state_snapshot WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError) as error:
            raise RewardLedgerCorruptionError(
                "The bounded Garden state is not valid JSON."
            ) from error
        if not isinstance(payload, dict):
            raise RewardLedgerCorruptionError(
                "The bounded Garden state must be a JSON object."
            )
        return StateSnapshot(
            schema_version=int(row["schema_version"]),
            revision=int(row["revision"]),
            payload=payload,
        )

    def reward_applied(self, event_key: str) -> bool:
        self._ensure_open()
        key = _required_text(event_key, "event_key")
        if key in self._pending_reward_events:
            return True
        return self._connection.execute(
            "SELECT 1 FROM reward_event WHERE event_key = ?", (key,)
        ).fetchone() is not None

    def reward_event(self, event_key: str) -> Optional[RewardEventRecord]:
        self._ensure_open()
        key = _required_text(event_key, "event_key")
        pending = self._pending_reward_events.get(key)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT event_key, source, scheduler_day, occurred_at "
            "FROM reward_event WHERE event_key = ?",
            (key,),
        ).fetchone()
        return _reward_event_from_row(row) if row is not None else None

    def stage_reward_event(self, record: RewardEventRecord) -> None:
        self._ensure_open()
        normalized = _normalize_reward_event(record)
        if self.reward_applied(normalized.event_key):
            raise RewardLedgerConflictError(
                "That reward event identity is already applied."
            )
        self._append_operation("reward_event", normalized)

    def lineage_record(self, lineage_key: str) -> Optional[AnswerLineageRecord]:
        self._ensure_open()
        key = _required_text(lineage_key, "lineage_key")
        pending = self._pending_lineages.get(key)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT lineage_key, original_day, card_id, serial "
            "FROM answer_lineage WHERE lineage_key = ?",
            (key,),
        ).fetchone()
        return _lineage_from_row(row) if row is not None else None

    def stage_answer_lineage(self, record: AnswerLineageRecord) -> None:
        self._ensure_open()
        normalized = _normalize_lineage(record)
        if self.lineage_record(normalized.lineage_key) is not None:
            raise RewardLedgerConflictError(
                "That answer lineage identity is already defined."
            )
        coordinate = (
            normalized.original_day,
            normalized.card_id,
            normalized.serial,
        )
        if coordinate in self._pending_lineage_coordinates:
            raise RewardLedgerConflictError(
                "That answer lineage coordinate is already defined."
            )
        if self._connection.execute(
            "SELECT 1 FROM answer_lineage "
            "WHERE original_day = ? AND card_id = ? AND serial = ?",
            coordinate,
        ).fetchone() is not None:
            raise RewardLedgerConflictError(
                "That answer lineage coordinate is already defined."
            )
        self._append_operation("answer_lineage", normalized)

    def binding_for_revlog(self, revlog_id: int) -> Optional[str]:
        self._ensure_open()
        normalized = _positive_int(revlog_id, "revlog_id")
        pending = self._pending_aliases.get(normalized)
        if pending is not None:
            return pending.lineage_key
        row = self._connection.execute(
            "SELECT lineage_key FROM revlog_alias WHERE revlog_id = ?",
            (normalized,),
        ).fetchone()
        return str(row["lineage_key"]) if row is not None else None

    def stage_revlog_alias(self, record: RevlogAliasRecord) -> None:
        self._ensure_open()
        normalized = _normalize_alias(record)
        if self.binding_for_revlog(normalized.revlog_id) is not None:
            raise RewardLedgerConflictError(
                "That revlog identity already has an answer lineage."
            )
        if self.lineage_record(normalized.lineage_key) is None:
            raise ValueError("lineage_key must reference a committed or staged lineage")
        self._append_operation("revlog_alias", normalized)

    def bindings_for_revlogs(self, revlog_ids: Iterable[int]) -> Dict[int, str]:
        self._ensure_open()
        normalized = _positive_ints(revlog_ids, "revlog_ids")
        result: Dict[int, str] = {}
        for chunk in _chunks(normalized, _SQL_IN_CHUNK):
            placeholders = ",".join("?" for _item in chunk)
            rows = self._connection.execute(
                "SELECT revlog_id, lineage_key FROM revlog_alias "
                "WHERE revlog_id IN (" + placeholders + ")",
                tuple(chunk),
            ).fetchall()
            result.update({int(row["revlog_id"]): str(row["lineage_key"]) for row in rows})
        for revlog_id in normalized:
            pending = self._pending_aliases.get(revlog_id)
            if pending is not None:
                result[revlog_id] = pending.lineage_key
        return result

    def bindings_for_cards(self, card_ids: Iterable[int]) -> Dict[int, str]:
        """Return every committed or staged alias for the requested cards."""

        self._ensure_open()
        normalized = _positive_ints(card_ids, "card_ids")
        requested = set(normalized)
        result: Dict[int, str] = {}
        for chunk in _chunks(normalized, _SQL_IN_CHUNK):
            placeholders = ",".join("?" for _item in chunk)
            rows = self._connection.execute(
                "SELECT a.revlog_id, a.lineage_key "
                "FROM revlog_alias AS a "
                "JOIN answer_lineage AS l ON l.lineage_key = a.lineage_key "
                "WHERE l.card_id IN (" + placeholders + ")",
                tuple(chunk),
            ).fetchall()
            result.update({int(row["revlog_id"]): str(row["lineage_key"]) for row in rows})
        for alias in self._pending_aliases.values():
            lineage = self.lineage_record(alias.lineage_key)
            if lineage is not None and lineage.card_id in requested:
                result[alias.revlog_id] = alias.lineage_key
        return result

    def all_revlog_bindings(self) -> Dict[int, str]:
        """Return the complete alias authority, including orphaned lineages."""

        self._ensure_open()
        rows = self._connection.execute(
            "SELECT revlog_id, lineage_key FROM revlog_alias"
        ).fetchall()
        result = {
            int(row["revlog_id"]): str(row["lineage_key"])
            for row in rows
        }
        result.update({
            alias.revlog_id: alias.lineage_key
            for alias in self._pending_aliases.values()
        })
        return result

    def aliases_for_lineage(self, lineage_key: str) -> Tuple[int, ...]:
        self._ensure_open()
        key = _required_text(lineage_key, "lineage_key")
        rows = self._connection.execute(
            "SELECT revlog_id FROM revlog_alias WHERE lineage_key = ?",
            (key,),
        ).fetchall()
        aliases = {int(row["revlog_id"]) for row in rows}
        aliases.update(
            alias.revlog_id
            for alias in self._pending_aliases.values()
            if alias.lineage_key == key
        )
        return tuple(sorted(aliases))

    def answer_consumed(self, answer_key: str) -> bool:
        self._ensure_open()
        key = _required_text(answer_key, "answer_key")
        if key in self._pending_consumptions:
            return True
        return self._connection.execute(
            "SELECT 1 FROM answer_consumption WHERE answer_key = ?", (key,)
        ).fetchone() is not None

    def consumed_answer_keys(self, answer_keys: Iterable[str]) -> set[str]:
        """Return the requested keys already committed or staged as consumed."""

        self._ensure_open()
        if isinstance(answer_keys, (str, bytes)):
            raise ValueError("answer_keys must be an iterable of identities")
        normalized = sorted({
            _required_text(answer_key, "answer_key")
            for answer_key in answer_keys
        })
        result: set[str] = set()
        for chunk in _chunks_text(normalized, _SQL_IN_CHUNK):
            placeholders = ",".join("?" for _item in chunk)
            rows = self._connection.execute(
                "SELECT answer_key FROM answer_consumption "
                "WHERE answer_key IN (" + placeholders + ")",
                tuple(chunk),
            ).fetchall()
            result.update(str(row["answer_key"]) for row in rows)
        result.update(
            answer_key
            for answer_key in normalized
            if answer_key in self._pending_consumptions
        )
        return result

    def answer_consumption(
        self, answer_key: str
    ) -> Optional[AnswerConsumptionRecord]:
        self._ensure_open()
        key = _required_text(answer_key, "answer_key")
        pending = self._pending_consumptions.get(key)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT answer_key, scheduler_day, occurred_at, "
            "lineage_key, first_revlog_id "
            "FROM answer_consumption WHERE answer_key = ?",
            (key,),
        ).fetchone()
        return _consumption_from_row(row) if row is not None else None

    def stage_answer_consumption(self, record: AnswerConsumptionRecord) -> None:
        self._ensure_open()
        normalized = _normalize_consumption(record)
        if self.answer_consumed(normalized.answer_key):
            raise RewardLedgerConflictError(
                "That answer identity is already consumed."
            )
        if normalized.lineage_key:
            if self.lineage_record(normalized.lineage_key) is None:
                raise ValueError(
                    "lineage_key must reference a committed or staged lineage"
                )
            if normalized.lineage_key in self._pending_consumption_lineages:
                raise RewardLedgerConflictError(
                    "That answer lineage already belongs to another consumption."
                )
            if self._connection.execute(
                "SELECT 1 FROM answer_consumption WHERE lineage_key = ?",
                (normalized.lineage_key,),
            ).fetchone() is not None:
                raise RewardLedgerConflictError(
                    "That answer lineage already belongs to another consumption."
                )
        self._append_operation("answer_consumption", normalized)

    def find_outcome(
        self,
        answer_key: str,
        pool_id: str,
    ) -> Optional[FindOutcomeRecord]:
        self._ensure_open()
        key = _required_text(answer_key, "answer_key")
        pool = _required_text(pool_id, "pool_id")
        pending = self._pending_outcomes.get((key, pool))
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT answer_key, scheduler_day, pool_id, pool_version, status, "
            "occurred_at, reward_id, hit_payload_json "
            "FROM find_outcome WHERE answer_key = ? AND pool_id = ?",
            (key, pool),
        ).fetchone()
        return _outcome_from_row(row) if row is not None else None

    def stage_find_outcome(self, record: FindOutcomeRecord) -> None:
        self._ensure_open()
        normalized = _normalize_outcome(record)
        if self.find_outcome(normalized.answer_key, normalized.pool_id) is not None:
            raise RewardLedgerConflictError(
                "That Garden Find pool has already consumed this answer."
            )
        consumption = self.answer_consumption(normalized.answer_key)
        if consumption is None:
            raise ValueError(
                "answer_key must reference a committed or staged consumption"
            )
        if (
            consumption.scheduler_day
            and consumption.scheduler_day != normalized.scheduler_day
        ):
            raise ValueError("Find outcome scheduler_day differs from its answer")
        if consumption.occurred_at and consumption.occurred_at != normalized.occurred_at:
            raise ValueError("Find outcome occurred_at differs from its answer")
        self._append_operation("find_outcome", normalized)

    def find_counts(
        self,
        scheduler_day: str,
        *,
        pool_id: str = "standard",
    ) -> FindDayCounts:
        """Return hit totals used by the daily cap and per-reward limits."""

        self._ensure_open()
        day_value = _iso_day(scheduler_day, "scheduler_day")
        pool = _required_text(pool_id, "pool_id")
        rows = self._connection.execute(
            "SELECT answer_key, reward_id "
            "FROM find_outcome "
            "WHERE scheduler_day = ? AND pool_id = ? AND status = 'hit' ",
            (day_value, pool),
        ).fetchall()
        pending_keys = set(self._pending_outcomes)
        counts: Dict[str, int] = {}
        total = 0
        for row in rows:
            identity = (str(row["answer_key"]), pool)
            if identity in pending_keys:
                continue
            reward_id = str(row["reward_id"])
            total += 1
            if reward_id:
                counts[reward_id] = counts.get(reward_id, 0) + 1
        for outcome in self._pending_outcomes.values():
            if (
                outcome.scheduler_day == day_value
                and outcome.pool_id == pool
                and outcome.status == "hit"
            ):
                total += 1
                counts[outcome.reward_id] = counts.get(outcome.reward_id, 0) + 1
        return FindDayCounts(day_value, pool, total, counts)

    def recent_hit_outcomes(
        self,
        *,
        limit: int = 8,
        pool_id: Optional[str] = None,
    ) -> Tuple[FindOutcomeRecord, ...]:
        """Return newest hits first, including hits staged after the last commit."""

        self._ensure_open()
        bounded_limit = _query_limit(limit)
        if bounded_limit == 0:
            return ()
        pool = None if pool_id is None else _required_text(pool_id, "pool_id")
        pending = [
            outcome
            for _operation_id, kind, outcome in reversed(self._operations)
            if kind == "find_outcome"
            and outcome.status == "hit"
            and (pool is None or outcome.pool_id == pool)
        ]
        if len(pending) >= bounded_limit:
            return tuple(pending[:bounded_limit])
        remaining = bounded_limit - len(pending)
        pending_keys = set(self._pending_outcomes)
        query_limit = min(
            MAX_RECENT_HITS_QUERY,
            remaining + len(self._pending_outcomes),
        )
        if pool is None:
            rows = self._connection.execute(
                "SELECT answer_key, scheduler_day, pool_id, pool_version, status, "
                "occurred_at, reward_id, hit_payload_json "
                "FROM find_outcome WHERE status = 'hit' "
                "ORDER BY recorded_sequence DESC LIMIT ?",
                (query_limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT answer_key, scheduler_day, pool_id, pool_version, status, "
                "occurred_at, reward_id, hit_payload_json "
                "FROM find_outcome WHERE status = 'hit' AND pool_id = ? "
                "ORDER BY recorded_sequence DESC LIMIT ?",
                (pool, query_limit),
            ).fetchall()
        committed = []
        for row in rows:
            outcome = _outcome_from_row(row)
            if (outcome.answer_key, outcome.pool_id) in pending_keys:
                continue
            committed.append(outcome)
            if len(committed) >= remaining:
                break
        return tuple([*pending, *committed])

    def finalized_day_fingerprint(self, scheduler_day: str) -> Optional[str]:
        self._ensure_open()
        day_value = _iso_day(scheduler_day, "scheduler_day")
        pending = self._pending_finalized_days.get(day_value)
        if pending is not None:
            return pending.record.fingerprint
        row = self._connection.execute(
            "SELECT fingerprint FROM finalized_day WHERE scheduler_day = ?",
            (day_value,),
        ).fetchone()
        return str(row["fingerprint"]) if row is not None else None

    def stage_finalized_day(
        self,
        record: FinalizedDayRecord,
        *,
        replace: bool = False,
    ) -> None:
        """Stage a finalized-day fingerprint.

        ``replace=True`` is an explicit late-sync update.  The default is a
        strict insert, so an accidental uniqueness conflict cannot be hidden.
        """

        self._ensure_open()
        normalized = _normalize_finalized_day(record)
        if normalized.scheduler_day in self._pending_finalized_days:
            raise RewardLedgerConflictError(
                "That scheduler day already has a staged fingerprint."
            )
        existing = self._connection.execute(
            "SELECT 1 FROM finalized_day WHERE scheduler_day = ?",
            (normalized.scheduler_day,),
        ).fetchone()
        if existing is not None and not replace:
            raise RewardLedgerConflictError(
                "That scheduler day is already finalized."
            )
        self._append_operation(
            "finalized_day", _StagedFinalizedDay(normalized, bool(replace))
        )

    def commit_state(
        self,
        state_payload: Mapping[str, Any],
        *,
        schema_version: int,
        expected_revision: int,
    ) -> StateSnapshot:
        """Atomically commit all staged rows and one bounded state document.

        Plain ``INSERT`` statements intentionally enforce exact uniqueness.
        A conflict rolls the whole SQLite transaction back, including the state
        document.  Staged rows remain available for the caller to inspect or
        discard with its engine checkpoint.
        """

        self._ensure_open()
        normalized_schema = _positive_int(schema_version, "schema_version")
        if not isinstance(state_payload, Mapping):
            raise TypeError("state_payload must be a mapping")
        forbidden_keys = UNBOUNDED_STATE_AUTHORITY_KEYS.intersection(
            str(key) for key in state_payload
        )
        if forbidden_keys:
            raise ValueError(
                "state_payload contains unbounded ledger authorities: "
                + ", ".join(sorted(forbidden_keys))
            )
        try:
            encoded_state = json.dumps(
                dict(state_payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise ValueError("state_payload must be valid JSON data") from error
        # Decode before the transaction so no avoidable parsing work can fail
        # after SQLite has durably committed and before staging is cleared.
        payload_copy = json.loads(encoded_state)
        normalized_expected = _nonnegative_int(
            expected_revision, "expected_revision"
        )

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            revision_row = self._connection.execute(
                "SELECT revision FROM state_snapshot WHERE singleton = 1"
            ).fetchone()
            current_revision = (
                int(revision_row["revision"]) if revision_row is not None else 0
            )
            if normalized_expected != current_revision:
                raise RewardLedgerRevisionConflict(
                    "The bounded Garden state revision changed before commit."
                )

            self._insert_pending_rows()
            next_revision = current_revision + 1
            if revision_row is None:
                self._connection.execute(
                    "INSERT INTO state_snapshot "
                    "(singleton, schema_version, revision, payload_json) "
                    "VALUES (1, ?, ?, ?)",
                    (normalized_schema, next_revision, encoded_state),
                )
            else:
                self._connection.execute(
                    "UPDATE state_snapshot SET schema_version = ?, revision = ?, "
                    "payload_json = ? WHERE singleton = 1",
                    (normalized_schema, next_revision, encoded_state),
                )
            self._connection.execute("COMMIT")
        except RewardLedgerRevisionConflict:
            self._rollback_sql_transaction()
            raise
        except sqlite3.IntegrityError as error:
            self._rollback_sql_transaction()
            raise RewardLedgerConflictError(
                "A reward-ledger identity conflicted during atomic commit."
            ) from error
        except sqlite3.DatabaseError as error:
            self._rollback_sql_transaction()
            raise RewardLedgerError(
                "The reward ledger could not commit its atomic transaction."
            ) from error
        except BaseException:
            self._rollback_sql_transaction()
            raise

        result = StateSnapshot(normalized_schema, next_revision, payload_copy)
        self._clear_pending(increment_generation=True)
        return result

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA journal_mode = WAL")

    def _initialize_or_validate_schema(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        tables = {
            str(row["name"])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if version == 0:
            if tables:
                raise RewardLedgerSchemaError(
                    "The reward-ledger database contains an unversioned schema."
                )
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA_STATEMENTS:
                    self._connection.execute(statement)
                self._connection.execute(
                    "PRAGMA user_version = " + str(LEDGER_SCHEMA_VERSION)
                )
                self._connection.execute("COMMIT")
            except sqlite3.DatabaseError as error:
                self._rollback_sql_transaction()
                raise RewardLedgerSchemaError(
                    "The reward-ledger schema could not be initialized."
                ) from error
            self._validate_schema_shape()
            return
        if version != LEDGER_SCHEMA_VERSION:
            raise RewardLedgerSchemaError(
                "Unsupported reward-ledger schema version: " + str(version)
            )
        missing = _REQUIRED_TABLES - tables
        if missing:
            raise RewardLedgerSchemaError(
                "The reward-ledger schema is incomplete: "
                + ", ".join(sorted(missing))
            )
        self._validate_schema_shape()

    def _validate_schema_shape(self) -> None:
        """Fail closed if exact identities are not backed by expected SQL keys."""

        for table, expected_columns in _EXPECTED_COLUMNS.items():
            rows = self._connection.execute(
                "PRAGMA table_info(" + _quote_identifier(table) + ")"
            ).fetchall()
            columns = tuple(str(row["name"]) for row in rows)
            if columns != expected_columns:
                raise RewardLedgerSchemaError(
                    "The reward-ledger table has an unexpected shape: " + table
                )
            primary_key = tuple(
                str(row["name"])
                for row in sorted(rows, key=lambda item: int(item["pk"]))
                if int(row["pk"]) > 0
            )
            if primary_key != _EXPECTED_PRIMARY_KEYS[table]:
                raise RewardLedgerSchemaError(
                    "The reward-ledger primary key is invalid: " + table
                )

        for table, required_keys in _REQUIRED_UNIQUE_KEYS.items():
            actual_keys = set()
            for index_row in self._connection.execute(
                "PRAGMA index_list(" + _quote_identifier(table) + ")"
            ).fetchall():
                if not int(index_row["unique"]):
                    continue
                index_name = str(index_row["name"])
                index_columns = self._connection.execute(
                    "PRAGMA index_info(" + _quote_identifier(index_name) + ")"
                ).fetchall()
                actual_keys.add(tuple(
                    str(item["name"])
                    for item in sorted(
                        index_columns, key=lambda value: int(value["seqno"])
                    )
                ))
            if not required_keys.issubset(actual_keys):
                raise RewardLedgerSchemaError(
                    "The reward-ledger uniqueness contract is invalid: " + table
                )

        for table, required_keys in _REQUIRED_FOREIGN_KEYS.items():
            actual_keys = {
                (
                    str(row["from"]),
                    str(row["table"]),
                    str(row["to"]),
                )
                for row in self._connection.execute(
                    "PRAGMA foreign_key_list(" + _quote_identifier(table) + ")"
                ).fetchall()
            }
            if not required_keys.issubset(actual_keys):
                raise RewardLedgerSchemaError(
                    "The reward-ledger foreign-key contract is invalid: " + table
                )

        index_names = {
            str(row["name"])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        if not _REQUIRED_NAMED_INDEXES.issubset(index_names):
            raise RewardLedgerSchemaError(
                "The reward-ledger query indexes are incomplete."
            )

    def _append_operation(self, kind: str, record: Any) -> None:
        operation_id = self._next_operation_id
        self._next_operation_id += 1
        self._operations.append((operation_id, kind, record))
        self._index_operation(kind, record)

    def _index_operation(self, kind: str, record: Any) -> None:
        if kind == "reward_event":
            self._pending_reward_events[record.event_key] = record
        elif kind == "answer_lineage":
            self._pending_lineages[record.lineage_key] = record
            self._pending_lineage_coordinates[
                (record.original_day, record.card_id, record.serial)
            ] = record
        elif kind == "revlog_alias":
            self._pending_aliases[record.revlog_id] = record
        elif kind == "answer_consumption":
            self._pending_consumptions[record.answer_key] = record
            if record.lineage_key:
                self._pending_consumption_lineages[record.lineage_key] = record
        elif kind == "find_outcome":
            self._pending_outcomes[(record.answer_key, record.pool_id)] = record
        elif kind == "finalized_day":
            self._pending_finalized_days[record.record.scheduler_day] = record
        else:  # pragma: no cover - internal programming error
            raise AssertionError("unsupported staged record: " + str(kind))

    def _rebuild_pending_indexes(self) -> None:
        operations = list(self._operations)
        self._pending_reward_events.clear()
        self._pending_lineages.clear()
        self._pending_lineage_coordinates.clear()
        self._pending_aliases.clear()
        self._pending_consumptions.clear()
        self._pending_consumption_lineages.clear()
        self._pending_outcomes.clear()
        self._pending_finalized_days.clear()
        for _operation_id, kind, record in operations:
            self._index_operation(kind, record)

    def _clear_pending(self, *, increment_generation: bool) -> None:
        self._operations.clear()
        self._pending_reward_events.clear()
        self._pending_lineages.clear()
        self._pending_lineage_coordinates.clear()
        self._pending_aliases.clear()
        self._pending_consumptions.clear()
        self._pending_consumption_lineages.clear()
        self._pending_outcomes.clear()
        self._pending_finalized_days.clear()
        if increment_generation:
            self._generation += 1

    def _insert_pending_rows(self) -> None:
        for record in self._pending_lineages.values():
            self._connection.execute(
                "INSERT INTO answer_lineage "
                "(lineage_key, original_day, card_id, serial) VALUES (?, ?, ?, ?)",
                (
                    record.lineage_key,
                    record.original_day,
                    record.card_id,
                    record.serial,
                ),
            )
        for record in self._pending_aliases.values():
            self._connection.execute(
                "INSERT INTO revlog_alias (revlog_id, lineage_key) VALUES (?, ?)",
                (record.revlog_id, record.lineage_key),
            )
        for record in self._pending_consumptions.values():
            self._connection.execute(
                "INSERT INTO answer_consumption "
                "(answer_key, scheduler_day, occurred_at, lineage_key, first_revlog_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    record.answer_key,
                    record.scheduler_day,
                    record.occurred_at,
                    record.lineage_key or None,
                    record.first_revlog_id,
                ),
            )
        for record in self._pending_reward_events.values():
            self._connection.execute(
                "INSERT INTO reward_event "
                "(event_key, source, scheduler_day, occurred_at) VALUES (?, ?, ?, ?)",
                (
                    record.event_key,
                    record.source,
                    record.scheduler_day,
                    record.occurred_at,
                ),
            )
        for record in self._pending_outcomes.values():
            payload_json = (
                json.dumps(
                    dict(record.hit_payload),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if record.hit_payload is not None
                else None
            )
            self._connection.execute(
                "INSERT INTO find_outcome "
                "(answer_key, scheduler_day, pool_id, pool_version, status, "
                "occurred_at, reward_id, hit_payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.answer_key,
                    record.scheduler_day,
                    record.pool_id,
                    record.pool_version,
                    record.status,
                    record.occurred_at,
                    record.reward_id,
                    payload_json,
                ),
            )
        for staged in self._pending_finalized_days.values():
            record = staged.record
            if staged.replace:
                cursor = self._connection.execute(
                    "UPDATE finalized_day SET fingerprint = ? WHERE scheduler_day = ?",
                    (record.fingerprint, record.scheduler_day),
                )
                if cursor.rowcount == 0:
                    self._connection.execute(
                        "INSERT INTO finalized_day (scheduler_day, fingerprint) "
                        "VALUES (?, ?)",
                        (record.scheduler_day, record.fingerprint),
                    )
            else:
                self._connection.execute(
                    "INSERT INTO finalized_day (scheduler_day, fingerprint) "
                    "VALUES (?, ?)",
                    (record.scheduler_day, record.fingerprint),
                )

    def _rollback_sql_transaction(self) -> None:
        if self._connection.in_transaction:
            self._connection.execute("ROLLBACK")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RewardLedgerClosedError("The reward ledger is closed.")


def _required_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(label + " must be a nonempty string")
    return value


def _optional_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(label + " must be a string")
    return value.strip()


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(label + " must be a positive integer")
    return int(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return int(value)


def _positive_ints(values: Iterable[int], label: str) -> List[int]:
    if isinstance(values, (str, bytes)):
        raise ValueError(label + " must be an iterable of positive integers")
    result = sorted({_positive_int(value, label) for value in values})
    return result


def _iso_day(value: Any, label: str) -> str:
    normalized = _required_text(value, label)
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(label + " must be an ISO calendar date") from error
    if parsed.isoformat() != normalized:
        raise ValueError(label + " must use YYYY-MM-DD form")
    return normalized


def _optional_iso_day(value: Any, label: str) -> str:
    normalized = _optional_text(value, label)
    return _iso_day(normalized, label) if normalized else ""


def _iso_datetime(value: Any, label: str) -> str:
    normalized = _required_text(value, label)
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(label + " must be an ISO date-time") from error
    return normalized


def _optional_iso_datetime(value: Any, label: str) -> str:
    normalized = _optional_text(value, label)
    return _iso_datetime(normalized, label) if normalized else ""


def _normalize_reward_event(record: RewardEventRecord) -> RewardEventRecord:
    if not isinstance(record, RewardEventRecord):
        raise TypeError("record must be RewardEventRecord")
    return RewardEventRecord(
        _required_text(record.event_key, "event_key"),
        _optional_text(record.source, "source"),
        _optional_iso_day(record.scheduler_day, "scheduler_day"),
        _optional_iso_datetime(record.occurred_at, "occurred_at"),
    )


def _normalize_lineage(record: AnswerLineageRecord) -> AnswerLineageRecord:
    if not isinstance(record, AnswerLineageRecord):
        raise TypeError("record must be AnswerLineageRecord")
    lineage_key = _required_text(record.lineage_key, "lineage_key")
    original_day = _iso_day(record.original_day, "original_day")
    card_id = _positive_int(record.card_id, "card_id")
    serial = _positive_int(record.serial, "serial")
    expected_key = "v1|{}|{}|{}".format(original_day, card_id, serial)
    if lineage_key != expected_key:
        raise ValueError(
            "lineage_key must match its v1 day, card, and serial fields"
        )
    return AnswerLineageRecord(lineage_key, original_day, card_id, serial)


def _normalize_alias(record: RevlogAliasRecord) -> RevlogAliasRecord:
    if not isinstance(record, RevlogAliasRecord):
        raise TypeError("record must be RevlogAliasRecord")
    return RevlogAliasRecord(
        _positive_int(record.revlog_id, "revlog_id"),
        _required_text(record.lineage_key, "lineage_key"),
    )


def _normalize_consumption(
    record: AnswerConsumptionRecord,
) -> AnswerConsumptionRecord:
    if not isinstance(record, AnswerConsumptionRecord):
        raise TypeError("record must be AnswerConsumptionRecord")
    return AnswerConsumptionRecord(
        _required_text(record.answer_key, "answer_key"),
        _optional_iso_day(record.scheduler_day, "scheduler_day"),
        _optional_iso_datetime(record.occurred_at, "occurred_at"),
        _optional_text(record.lineage_key, "lineage_key"),
        _nonnegative_int(record.first_revlog_id, "first_revlog_id"),
    )


def _normalize_outcome(record: FindOutcomeRecord) -> FindOutcomeRecord:
    if not isinstance(record, FindOutcomeRecord):
        raise TypeError("record must be FindOutcomeRecord")
    status = _required_text(record.status, "status")
    if status not in FIND_OUTCOME_STATUSES:
        raise ValueError("status must be miss, hit, or paused")
    reward_id = _optional_text(record.reward_id, "reward_id")
    payload: Optional[Mapping[str, Any]] = None
    if status == "hit":
        if not reward_id:
            raise ValueError("a hit must include reward_id")
        if not isinstance(record.hit_payload, Mapping):
            raise ValueError("a hit must include a JSON-object hit_payload")
        try:
            payload_value = json.loads(json.dumps(
                dict(record.hit_payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ))
        except (TypeError, ValueError) as error:
            raise ValueError("hit_payload must contain valid JSON data") from error
        if not isinstance(payload_value, dict):  # pragma: no cover - dict encoded above
            raise ValueError("hit_payload must be a JSON object")
        payload = payload_value
    elif reward_id or record.hit_payload is not None:
        raise ValueError("miss and paused outcomes cannot carry a reward payload")
    return FindOutcomeRecord(
        _required_text(record.answer_key, "answer_key"),
        _iso_day(record.scheduler_day, "scheduler_day"),
        _required_text(record.pool_id, "pool_id"),
        _required_text(record.pool_version, "pool_version"),
        status,
        _iso_datetime(record.occurred_at, "occurred_at"),
        reward_id,
        payload,
    )


def _normalize_finalized_day(record: FinalizedDayRecord) -> FinalizedDayRecord:
    if not isinstance(record, FinalizedDayRecord):
        raise TypeError("record must be FinalizedDayRecord")
    return FinalizedDayRecord(
        _iso_day(record.scheduler_day, "scheduler_day"),
        _required_text(record.fingerprint, "fingerprint"),
    )


def _reward_event_from_row(row: sqlite3.Row) -> RewardEventRecord:
    return RewardEventRecord(
        str(row["event_key"]),
        str(row["source"]),
        str(row["scheduler_day"]),
        str(row["occurred_at"]),
    )


def _lineage_from_row(row: sqlite3.Row) -> AnswerLineageRecord:
    return AnswerLineageRecord(
        str(row["lineage_key"]),
        str(row["original_day"]),
        int(row["card_id"]),
        int(row["serial"]),
    )


def _consumption_from_row(row: sqlite3.Row) -> AnswerConsumptionRecord:
    return AnswerConsumptionRecord(
        str(row["answer_key"]),
        str(row["scheduler_day"]),
        str(row["occurred_at"]),
        str(row["lineage_key"] or ""),
        int(row["first_revlog_id"]),
    )


def _outcome_from_row(row: sqlite3.Row) -> FindOutcomeRecord:
    raw_payload = row["hit_payload_json"]
    payload: Optional[Mapping[str, Any]] = None
    if raw_payload is not None:
        try:
            decoded = json.loads(str(raw_payload))
        except (TypeError, ValueError) as error:
            raise RewardLedgerCorruptionError(
                "A Garden Find hit payload is not valid JSON."
            ) from error
        if not isinstance(decoded, dict):
            raise RewardLedgerCorruptionError(
                "A Garden Find hit payload must be a JSON object."
            )
        payload = decoded
    return FindOutcomeRecord(
        answer_key=str(row["answer_key"]),
        scheduler_day=str(row["scheduler_day"]),
        pool_id=str(row["pool_id"]),
        pool_version=str(row["pool_version"]),
        status=str(row["status"]),
        occurred_at=str(row["occurred_at"]),
        reward_id=str(row["reward_id"]),
        hit_payload=payload,
    )


def _query_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("limit must be a nonnegative integer")
    if value > MAX_RECENT_HITS_QUERY:
        raise ValueError(
            "limit cannot exceed " + str(MAX_RECENT_HITS_QUERY)
        )
    return int(value)


def _chunks(values: List[int], size: int) -> Iterable[List[int]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _chunks_text(values: List[str], size: int) -> Iterable[List[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'
