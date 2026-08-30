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

from dataclasses import dataclass, replace
from datetime import date, datetime
import errno
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
import uuid


LEDGER_SCHEMA_VERSION = 2
FIND_OUTCOME_STATUSES = frozenset({"miss", "hit", "paused"})
MAX_RECENT_HITS_QUERY = 1_000
_SQL_IN_CHUNK = 500
_HARD_LINK_FALLBACK_ERRNOS = frozenset({
    errno.EACCES,
    errno.EINVAL,
    errno.ENOSYS,
    errno.EPERM,
    errno.EXDEV,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
})
UNBOUNDED_STATE_AUTHORITY_KEYS = frozenset({
    "applied_reward_event_keys",
    "processed_answer_keys",
    "answer_lineage_bindings",
    "pending_reanswer_lineages",
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
    reanswer_floor: int = 0


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
class IdempotencyRecord:
    operation_kind: str
    operation_id: str
    request_fingerprint: str
    outcome: Mapping[str, Any]
    occurred_at: str = ""
    scheduler_day: str = ""


@dataclass(frozen=True)
class EconomyEventRecord:
    event_key: str
    event_kind: str
    source_id: str = ""
    sink_id: str = ""
    scheduler_day: str = ""
    occurred_at: str = ""
    coins_earned: int = 0
    coins_spent: int = 0
    growth_earned_units: int = 0
    growth_spent_on_landmarks: int = 0
    growth_spent_on_mastery: int = 0
    item_id: str = ""
    quantity: int = 0
    metric_deltas: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class DailyEconomySnapshotRecord:
    anki_day: str
    garden_rhythm_percent: int
    active_garden_bonus_id: str
    active_scenery_effect_id: str
    snapshot_source: str
    snapshot_id: str


@dataclass(frozen=True)
class _StagedFinalizedDay:
    record: FinalizedDayRecord
    replace: bool


@dataclass(frozen=True)
class _StagedReanswerFloor:
    lineage_key: str
    minimum_revlog_id: int


_IDEMPOTENCY_TABLE_SQL = """
CREATE TABLE idempotency_record (
    operation_kind TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL DEFAULT '',
    scheduler_day TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (operation_kind, operation_id)
)
"""
_ECONOMY_EVENT_TABLE_SQL = """
CREATE TABLE economy_event (
    event_key TEXT PRIMARY KEY,
    event_kind TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    sink_id TEXT NOT NULL DEFAULT '',
    scheduler_day TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT '',
    coins_earned INTEGER NOT NULL DEFAULT 0 CHECK (coins_earned >= 0),
    coins_spent INTEGER NOT NULL DEFAULT 0 CHECK (coins_spent >= 0),
    growth_earned_units INTEGER NOT NULL DEFAULT 0 CHECK (growth_earned_units >= 0),
    growth_spent_on_landmarks INTEGER NOT NULL DEFAULT 0
        CHECK (growth_spent_on_landmarks >= 0),
    growth_spent_on_mastery INTEGER NOT NULL DEFAULT 0
        CHECK (growth_spent_on_mastery >= 0),
    item_id TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    metric_deltas_json TEXT NOT NULL DEFAULT '{}'
)
"""
_DAILY_ECONOMY_SNAPSHOT_TABLE_SQL = """
CREATE TABLE daily_economy_snapshot (
    anki_day TEXT PRIMARY KEY,
    garden_rhythm_percent INTEGER NOT NULL
        CHECK (garden_rhythm_percent IN (0, 2, 4, 6, 8, 10)),
    active_garden_bonus_id TEXT NOT NULL,
    active_scenery_effect_id TEXT NOT NULL,
    snapshot_source TEXT NOT NULL,
    snapshot_id TEXT NOT NULL UNIQUE
)
"""
_V2_SCHEMA_STATEMENTS = (
    _IDEMPOTENCY_TABLE_SQL,
    _ECONOMY_EVENT_TABLE_SQL,
    _DAILY_ECONOMY_SNAPSHOT_TABLE_SQL,
    """
    CREATE INDEX idempotency_record_day_idx
    ON idempotency_record(scheduler_day, operation_kind)
    """,
    """
    CREATE INDEX economy_event_day_idx
    ON economy_event(scheduler_day, event_kind)
    """,
    """
    CREATE INDEX daily_economy_snapshot_id_idx
    ON daily_economy_snapshot(snapshot_id)
    """,
)


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
        reanswer_floor INTEGER NOT NULL DEFAULT 0 CHECK (reanswer_floor >= 0),
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
    *_V2_SCHEMA_STATEMENTS,
    "CREATE INDEX revlog_alias_lineage_idx ON revlog_alias(lineage_key)",
    "CREATE INDEX answer_lineage_card_idx ON answer_lineage(card_id)",
    """
    CREATE INDEX answer_lineage_reanswer_idx
    ON answer_lineage(reanswer_floor) WHERE reanswer_floor > 0
    """,
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
    "idempotency_record",
    "economy_event",
    "daily_economy_snapshot",
})

_V1_REQUIRED_TABLES = frozenset({
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
        "lineage_key", "original_day", "card_id", "serial", "reanswer_floor",
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
    "idempotency_record": (
        "operation_kind", "operation_id", "request_fingerprint",
        "outcome_json", "occurred_at", "scheduler_day",
    ),
    "economy_event": (
        "event_key", "event_kind", "source_id", "sink_id", "scheduler_day",
        "occurred_at", "coins_earned", "coins_spent",
        "growth_earned_units", "growth_spent_on_landmarks",
        "growth_spent_on_mastery", "item_id", "quantity",
        "metric_deltas_json",
    ),
    "daily_economy_snapshot": (
        "anki_day", "garden_rhythm_percent", "active_garden_bonus_id",
        "active_scenery_effect_id", "snapshot_source", "snapshot_id",
    ),
}

_V1_EXPECTED_COLUMNS = {
    key: value for key, value in _EXPECTED_COLUMNS.items()
    if key in _V1_REQUIRED_TABLES
}

_EXPECTED_PRIMARY_KEYS = {
    "state_snapshot": ("singleton",),
    "reward_event": ("event_key",),
    "answer_lineage": ("lineage_key",),
    "revlog_alias": ("revlog_id",),
    "answer_consumption": ("answer_key",),
    "find_outcome": ("recorded_sequence",),
    "finalized_day": ("scheduler_day",),
    "idempotency_record": ("operation_kind", "operation_id"),
    "economy_event": ("event_key",),
    "daily_economy_snapshot": ("anki_day",),
}

_V1_EXPECTED_PRIMARY_KEYS = {
    key: value for key, value in _EXPECTED_PRIMARY_KEYS.items()
    if key in _V1_REQUIRED_TABLES
}

_REQUIRED_UNIQUE_KEYS = {
    "answer_lineage": {("original_day", "card_id", "serial")},
    "answer_consumption": {("lineage_key",)},
    "find_outcome": {("answer_key", "pool_id")},
    "daily_economy_snapshot": {("snapshot_id",)},
}

_V1_REQUIRED_UNIQUE_KEYS = {
    key: value for key, value in _REQUIRED_UNIQUE_KEYS.items()
    if key in _V1_REQUIRED_TABLES
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
    "answer_lineage_reanswer_idx",
    "find_outcome_day_idx",
    "find_outcome_recent_hit_idx",
    "idempotency_record_day_idx",
    "economy_event_day_idx",
    "daily_economy_snapshot_id_idx",
})

_V1_REQUIRED_NAMED_INDEXES = frozenset({
    "revlog_alias_lineage_idx",
    "answer_lineage_card_idx",
    "answer_lineage_reanswer_idx",
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
        self._pending_reanswer_floors: Dict[str, int] = {}
        self._pending_outcomes: Dict[Tuple[str, str], FindOutcomeRecord] = {}
        self._pending_finalized_days: Dict[str, _StagedFinalizedDay] = {}
        self._pending_idempotency_records: Dict[
            Tuple[str, str], IdempotencyRecord
        ] = {}
        self._pending_economy_events: Dict[str, EconomyEventRecord] = {}
        self._pending_daily_economy_snapshots: Dict[
            str, DailyEconomySnapshotRecord
        ] = {}
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
        try:
            destination_connection = sqlite3.connect(str(temporary))
            self._connection.backup(destination_connection)
            destination_connection.close()
            destination_connection = None
            _verify_backup_database(temporary)
            # Both paths share a directory/filesystem. Hard-link installation
            # is atomic and fails with EEXIST rather than replacing a file that
            # appeared after the initial validation. Some valid Anki storage
            # volumes (for example exFAT or a restricted network share) do not
            # support hard links, so retain the no-overwrite contract with an
            # exclusive, flushed, independently verified copy on those volumes.
            try:
                os.link(str(temporary), str(target))
            except OSError as error:
                if error.errno not in _HARD_LINK_FALLBACK_ERRNOS:
                    raise
                _exclusive_verified_copy(temporary, target)
            temporary.unlink()
            return target
        finally:
            if destination_connection is not None:
                destination_connection.close()
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
            if key in self._pending_reanswer_floors:
                return replace(
                    pending,
                    reanswer_floor=self._pending_reanswer_floors[key],
                )
            return pending
        row = self._connection.execute(
            "SELECT lineage_key, original_day, card_id, serial, reanswer_floor "
            "FROM answer_lineage WHERE lineage_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        record = _lineage_from_row(row)
        if key in self._pending_reanswer_floors:
            record = replace(
                record,
                reanswer_floor=self._pending_reanswer_floors[key],
            )
        return record

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

    def reanswer_floor_for_lineage(self, lineage_key: str) -> Optional[int]:
        """Return a committed or staged undo floor for one answer lineage.

        ``None`` means the lineage does not exist; ``0`` means it has no pending
        reanswer.
        """

        self._ensure_open()
        key = _required_text(lineage_key, "lineage_key")
        if key in self._pending_reanswer_floors:
            return self._pending_reanswer_floors[key]
        pending = self._pending_lineages.get(key)
        if pending is not None:
            return pending.reanswer_floor
        row = self._connection.execute(
            "SELECT reanswer_floor FROM answer_lineage WHERE lineage_key = ?",
            (key,),
        ).fetchone()
        return int(row["reanswer_floor"]) if row is not None else None

    def reanswer_hints(self) -> Dict[str, int]:
        """Return every durable pending reanswer lineage and its minimum ID."""

        self._ensure_open()
        rows = self._connection.execute(
            "SELECT lineage_key, reanswer_floor FROM answer_lineage "
            "WHERE reanswer_floor > 0"
        ).fetchall()
        result = {
            str(row["lineage_key"]): int(row["reanswer_floor"])
            for row in rows
        }
        for record in self._pending_lineages.values():
            if record.reanswer_floor > 0:
                result[record.lineage_key] = record.reanswer_floor
        for lineage, floor in self._pending_reanswer_floors.items():
            if floor > 0:
                result[lineage] = floor
            else:
                result.pop(lineage, None)
        return result

    def stage_reanswer_hint(self, lineage_key: str, minimum_revlog_id: int) -> None:
        """Stage one durable undo/reanswer floor for an answer lineage."""

        self._ensure_open()
        lineage = _required_text(lineage_key, "lineage_key")
        floor = _positive_int(minimum_revlog_id, "minimum_revlog_id")
        current = self.reanswer_floor_for_lineage(lineage)
        if current is None:
            raise ValueError(
                "lineage_key must reference a committed or staged lineage"
            )
        if current == floor:
            return
        if current > 0:
            raise RewardLedgerConflictError(
                "That answer lineage already has a different reanswer floor."
            )
        self._append_operation(
            "reanswer_floor", _StagedReanswerFloor(lineage, floor)
        )

    def stage_clear_reanswer_hint(self, lineage_key: str) -> None:
        """Stage removal of a satisfied undo/reanswer floor."""

        self._ensure_open()
        lineage = _required_text(lineage_key, "lineage_key")
        current = self.reanswer_floor_for_lineage(lineage)
        if current is None:
            raise ValueError(
                "lineage_key must reference a committed or staged lineage"
            )
        if current == 0:
            return
        self._append_operation(
            "reanswer_floor", _StagedReanswerFloor(lineage, 0)
        )

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

    def idempotency_record(
        self,
        operation_kind: str,
        operation_id: str,
    ) -> Optional[IdempotencyRecord]:
        self._ensure_open()
        identity = (
            _required_text(operation_kind, "operation_kind"),
            _required_text(operation_id, "operation_id"),
        )
        pending = self._pending_idempotency_records.get(identity)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT operation_kind, operation_id, request_fingerprint, "
            "outcome_json, occurred_at, scheduler_day "
            "FROM idempotency_record "
            "WHERE operation_kind = ? AND operation_id = ?",
            identity,
        ).fetchone()
        return _idempotency_from_row(row) if row is not None else None

    def stage_idempotency_record(self, record: IdempotencyRecord) -> None:
        self._ensure_open()
        normalized = _normalize_idempotency_record(record)
        existing = self.idempotency_record(
            normalized.operation_kind, normalized.operation_id
        )
        if existing is not None:
            if existing == normalized:
                return
            raise RewardLedgerConflictError(
                "That operation identity has a conflicting permanent outcome."
            )
        self._append_operation("idempotency_record", normalized)

    def economy_event(self, event_key: str) -> Optional[EconomyEventRecord]:
        self._ensure_open()
        key = _required_text(event_key, "event_key")
        pending = self._pending_economy_events.get(key)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT event_key, event_kind, source_id, sink_id, scheduler_day, "
            "occurred_at, coins_earned, coins_spent, growth_earned_units, "
            "growth_spent_on_landmarks, growth_spent_on_mastery, item_id, "
            "quantity, metric_deltas_json FROM economy_event WHERE event_key = ?",
            (key,),
        ).fetchone()
        return _economy_event_from_row(row) if row is not None else None

    def stage_economy_event(self, record: EconomyEventRecord) -> None:
        self._ensure_open()
        normalized = _normalize_economy_event(record)
        existing = self.economy_event(normalized.event_key)
        if existing is not None:
            if existing == normalized:
                return
            raise RewardLedgerConflictError(
                "That economy event identity has conflicting deltas."
            )
        self._append_operation("economy_event", normalized)

    def daily_economy_snapshot(
        self,
        anki_day: str,
    ) -> Optional[DailyEconomySnapshotRecord]:
        self._ensure_open()
        day_value = _iso_day(anki_day, "anki_day")
        pending = self._pending_daily_economy_snapshots.get(day_value)
        if pending is not None:
            return pending
        row = self._connection.execute(
            "SELECT anki_day, garden_rhythm_percent, active_garden_bonus_id, "
            "active_scenery_effect_id, snapshot_source, snapshot_id "
            "FROM daily_economy_snapshot WHERE anki_day = ?",
            (day_value,),
        ).fetchone()
        return _daily_economy_snapshot_from_row(row) if row is not None else None

    def stage_daily_economy_snapshot(
        self,
        record: DailyEconomySnapshotRecord,
    ) -> None:
        self._ensure_open()
        normalized = _normalize_daily_economy_snapshot(record)
        existing = self.daily_economy_snapshot(normalized.anki_day)
        if existing is not None:
            if existing == normalized:
                return
            raise RewardLedgerConflictError(
                "That Anki day already has a different economy snapshot."
            )
        pending_id = next((
            snapshot
            for snapshot in self._pending_daily_economy_snapshots.values()
            if snapshot.snapshot_id == normalized.snapshot_id
        ), None)
        if pending_id is not None:
            raise RewardLedgerConflictError(
                "That economy snapshot identity already belongs to another day."
            )
        committed_id = self._connection.execute(
            "SELECT 1 FROM daily_economy_snapshot WHERE snapshot_id = ?",
            (normalized.snapshot_id,),
        ).fetchone()
        if committed_id is not None:
            raise RewardLedgerConflictError(
                "That economy snapshot identity already belongs to another day."
            )
        self._append_operation("daily_economy_snapshot", normalized)

    def eligible_study_days_before(
        self,
        anki_day: str,
        *,
        limit: int = 7,
    ) -> Tuple[str, ...]:
        """Return newest eligible answer days strictly before ``anki_day``."""

        self._ensure_open()
        day_value = _iso_day(anki_day, "anki_day")
        bounded_limit = _history_limit(limit)
        if bounded_limit == 0:
            return ()
        rows = self._connection.execute(
            "SELECT DISTINCT scheduler_day FROM answer_consumption "
            "WHERE scheduler_day <> '' AND scheduler_day < ? "
            "ORDER BY scheduler_day DESC LIMIT ?",
            (day_value, bounded_limit),
        ).fetchall()
        days = {str(row["scheduler_day"]) for row in rows}
        days.update(
            record.scheduler_day
            for record in self._pending_consumptions.values()
            if record.scheduler_day and record.scheduler_day < day_value
        )
        return tuple(sorted(days, reverse=True)[:bounded_limit])

    def verified_today_cards_completion_days_before(
        self,
        anki_day: str,
    ) -> frozenset[str]:
        """Return provable completion days strictly before ``anki_day``."""

        self._ensure_open()
        day_value = _iso_day(anki_day, "anki_day")
        rows = self._connection.execute(
            "SELECT event_key, source, scheduler_day FROM reward_event "
            "WHERE source = 'all_due' OR event_key LIKE 'all_due:%'"
        ).fetchall()
        days = {
            completion_day
            for row in rows
            for completion_day in [_completion_day_from_reward_row(row)]
            if completion_day and completion_day < day_value
        }
        for record in self._pending_reward_events.values():
            completion_day = _completion_day_from_reward_event(record)
            if completion_day and completion_day < day_value:
                days.add(completion_day)
        return frozenset(days)

    def lifetime_economy_aggregates(self) -> Mapping[str, Any]:
        """Rebuild exact lifetime aggregates from permanent event deltas."""

        self._ensure_open()
        rows = self._connection.execute(
            "SELECT event_key, event_kind, source_id, sink_id, scheduler_day, "
            "occurred_at, coins_earned, coins_spent, growth_earned_units, "
            "growth_spent_on_landmarks, growth_spent_on_mastery, item_id, "
            "quantity, metric_deltas_json FROM economy_event ORDER BY rowid"
        ).fetchall()
        committed = [_economy_event_from_row(row) for row in rows]
        pending_keys = set(self._pending_economy_events)
        events = [
            event for event in committed if event.event_key not in pending_keys
        ]
        events.extend(self._pending_economy_events.values())
        result: Dict[str, Any] = {
            "coins_earned_by_source": {},
            "coins_spent_by_sink": {},
            "growth_earned_by_source": {},
            "growth_spent_on_landmarks": 0,
            "growth_spent_on_mastery": 0,
            "finds_by_outcome": {},
            "environment_discoveries": {},
            "consumables_earned": {},
            "consumables_used": {},
            "plants_completed": 0,
            "today_cards_completions": 0,
        }
        for event in events:
            if event.coins_earned:
                _increment_count(
                    result["coins_earned_by_source"],
                    event.source_id,
                    event.coins_earned,
                )
            if event.coins_spent:
                _increment_count(
                    result["coins_spent_by_sink"],
                    event.sink_id,
                    event.coins_spent,
                )
            if event.growth_earned_units:
                _increment_count(
                    result["growth_earned_by_source"],
                    event.source_id,
                    event.growth_earned_units,
                )
            result["growth_spent_on_landmarks"] += (
                event.growth_spent_on_landmarks
            )
            result["growth_spent_on_mastery"] += event.growth_spent_on_mastery
            for key, delta in dict(event.metric_deltas or {}).items():
                if key in {
                    "finds_by_outcome",
                    "environment_discoveries",
                    "consumables_earned",
                    "consumables_used",
                }:
                    for item_id, amount in dict(delta).items():
                        _increment_count(result[key], item_id, amount)
                elif key in {"plants_completed", "today_cards_completions"}:
                    result[key] += int(delta)
        return result

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
        if version == 1:
            missing = _V1_REQUIRED_TABLES - tables
            if missing:
                raise RewardLedgerSchemaError(
                    "The schema-1 reward ledger is incomplete: "
                    + ", ".join(sorted(missing))
                )
            self._validate_schema_shape(
                expected_columns=_V1_EXPECTED_COLUMNS,
                expected_primary_keys=_V1_EXPECTED_PRIMARY_KEYS,
                required_unique_keys=_V1_REQUIRED_UNIQUE_KEYS,
                required_named_indexes=_V1_REQUIRED_NAMED_INDEXES,
            )
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                for statement in _V2_SCHEMA_STATEMENTS:
                    self._connection.execute(statement)
                self._connection.execute(
                    "PRAGMA user_version = " + str(LEDGER_SCHEMA_VERSION)
                )
                self._connection.execute("COMMIT")
            except sqlite3.DatabaseError as error:
                self._rollback_sql_transaction()
                raise RewardLedgerSchemaError(
                    "The reward-ledger schema-2 upgrade could not complete."
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

    def _validate_schema_shape(
        self,
        *,
        expected_columns: Mapping[str, Tuple[str, ...]] = _EXPECTED_COLUMNS,
        expected_primary_keys: Mapping[str, Tuple[str, ...]] = (
            _EXPECTED_PRIMARY_KEYS
        ),
        required_unique_keys: Mapping[str, set[Tuple[str, ...]]] = (
            _REQUIRED_UNIQUE_KEYS
        ),
        required_named_indexes: frozenset[str] = _REQUIRED_NAMED_INDEXES,
    ) -> None:
        """Fail closed if exact identities are not backed by expected SQL keys."""

        for table, table_expected_columns in expected_columns.items():
            rows = self._connection.execute(
                "PRAGMA table_info(" + _quote_identifier(table) + ")"
            ).fetchall()
            columns = tuple(str(row["name"]) for row in rows)
            if columns != table_expected_columns:
                raise RewardLedgerSchemaError(
                    "The reward-ledger table has an unexpected shape: " + table
                )
            primary_key = tuple(
                str(row["name"])
                for row in sorted(rows, key=lambda item: int(item["pk"]))
                if int(row["pk"]) > 0
            )
            if primary_key != expected_primary_keys[table]:
                raise RewardLedgerSchemaError(
                    "The reward-ledger primary key is invalid: " + table
                )

        for table, required_keys in required_unique_keys.items():
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
        if not required_named_indexes.issubset(index_names):
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
        elif kind == "reanswer_floor":
            self._pending_reanswer_floors[record.lineage_key] = (
                record.minimum_revlog_id
            )
        elif kind == "find_outcome":
            self._pending_outcomes[(record.answer_key, record.pool_id)] = record
        elif kind == "finalized_day":
            self._pending_finalized_days[record.record.scheduler_day] = record
        elif kind == "idempotency_record":
            self._pending_idempotency_records[
                (record.operation_kind, record.operation_id)
            ] = record
        elif kind == "economy_event":
            self._pending_economy_events[record.event_key] = record
        elif kind == "daily_economy_snapshot":
            self._pending_daily_economy_snapshots[record.anki_day] = record
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
        self._pending_reanswer_floors.clear()
        self._pending_outcomes.clear()
        self._pending_finalized_days.clear()
        self._pending_idempotency_records.clear()
        self._pending_economy_events.clear()
        self._pending_daily_economy_snapshots.clear()
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
        self._pending_reanswer_floors.clear()
        self._pending_outcomes.clear()
        self._pending_finalized_days.clear()
        self._pending_idempotency_records.clear()
        self._pending_economy_events.clear()
        self._pending_daily_economy_snapshots.clear()
        if increment_generation:
            self._generation += 1

    def _insert_pending_rows(self) -> None:
        for record in self._pending_lineages.values():
            self._connection.execute(
                "INSERT INTO answer_lineage "
                "(lineage_key, original_day, card_id, serial, reanswer_floor) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    record.lineage_key,
                    record.original_day,
                    record.card_id,
                    record.serial,
                    record.reanswer_floor,
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
                "(answer_key, scheduler_day, occurred_at, lineage_key, "
                "first_revlog_id) VALUES (?, ?, ?, ?, ?)",
                (
                    record.answer_key,
                    record.scheduler_day,
                    record.occurred_at,
                    record.lineage_key or None,
                    record.first_revlog_id,
                ),
            )
        for lineage_key, minimum_revlog_id in self._pending_reanswer_floors.items():
            cursor = self._connection.execute(
                "UPDATE answer_lineage SET reanswer_floor = ? "
                "WHERE lineage_key = ?",
                (minimum_revlog_id, lineage_key),
            )
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError(
                    "reanswer floor lost its answer lineage"
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
        for record in self._pending_idempotency_records.values():
            self._connection.execute(
                "INSERT INTO idempotency_record "
                "(operation_kind, operation_id, request_fingerprint, outcome_json, "
                "occurred_at, scheduler_day) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.operation_kind,
                    record.operation_id,
                    record.request_fingerprint,
                    _canonical_json(record.outcome, "outcome"),
                    record.occurred_at,
                    record.scheduler_day,
                ),
            )
        for record in self._pending_economy_events.values():
            self._connection.execute(
                "INSERT INTO economy_event "
                "(event_key, event_kind, source_id, sink_id, scheduler_day, "
                "occurred_at, coins_earned, coins_spent, growth_earned_units, "
                "growth_spent_on_landmarks, growth_spent_on_mastery, item_id, "
                "quantity, metric_deltas_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.event_key,
                    record.event_kind,
                    record.source_id,
                    record.sink_id,
                    record.scheduler_day,
                    record.occurred_at,
                    record.coins_earned,
                    record.coins_spent,
                    record.growth_earned_units,
                    record.growth_spent_on_landmarks,
                    record.growth_spent_on_mastery,
                    record.item_id,
                    record.quantity,
                    _canonical_json(record.metric_deltas or {}, "metric_deltas"),
                ),
            )
        for record in self._pending_daily_economy_snapshots.values():
            self._connection.execute(
                "INSERT INTO daily_economy_snapshot "
                "(anki_day, garden_rhythm_percent, active_garden_bonus_id, "
                "active_scenery_effect_id, snapshot_source, snapshot_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.anki_day,
                    record.garden_rhythm_percent,
                    record.active_garden_bonus_id,
                    record.active_scenery_effect_id,
                    record.snapshot_source,
                    record.snapshot_id,
                ),
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
    return AnswerLineageRecord(
        lineage_key,
        original_day,
        card_id,
        serial,
        _nonnegative_int(record.reanswer_floor, "reanswer_floor"),
    )


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


def _canonical_json(value: Mapping[str, Any], label: str) -> str:
    if not isinstance(value, Mapping):
        raise ValueError(label + " must be a JSON object")
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ValueError(label + " must contain valid JSON data") from error
    if not isinstance(decoded, dict):  # pragma: no cover - dict encoded above
        raise ValueError(label + " must be a JSON object")
    return encoded


def _json_mapping(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    return json.loads(_canonical_json(value, label))


def _normalize_idempotency_record(record: IdempotencyRecord) -> IdempotencyRecord:
    if not isinstance(record, IdempotencyRecord):
        raise TypeError("record must be IdempotencyRecord")
    return IdempotencyRecord(
        operation_kind=_required_text(record.operation_kind, "operation_kind"),
        operation_id=_required_text(record.operation_id, "operation_id"),
        request_fingerprint=_required_text(
            record.request_fingerprint, "request_fingerprint"
        ),
        outcome=_json_mapping(record.outcome, "outcome"),
        occurred_at=_optional_iso_datetime(record.occurred_at, "occurred_at"),
        scheduler_day=_optional_iso_day(record.scheduler_day, "scheduler_day"),
    )


_ECONOMY_MAP_METRICS = frozenset({
    "finds_by_outcome",
    "environment_discoveries",
    "consumables_earned",
    "consumables_used",
})
_ECONOMY_SCALAR_METRICS = frozenset({
    "plants_completed",
    "today_cards_completions",
})


def _normalize_metric_deltas(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("metric_deltas must be a JSON object")
    result: Dict[str, Any] = {}
    for key, raw_delta in value.items():
        if key in _ECONOMY_MAP_METRICS:
            if not isinstance(raw_delta, Mapping):
                raise ValueError(str(key) + " metric delta must be an object")
            normalized_map: Dict[str, int] = {}
            for raw_item_id, raw_amount in raw_delta.items():
                item_id = _required_text(raw_item_id, str(key) + " item_id")
                amount = _nonnegative_int(raw_amount, str(key) + " amount")
                if amount:
                    normalized_map[item_id] = amount
            if normalized_map:
                result[str(key)] = normalized_map
        elif key in _ECONOMY_SCALAR_METRICS:
            amount = _nonnegative_int(raw_delta, str(key))
            if amount:
                result[str(key)] = amount
        else:
            raise ValueError("unsupported lifetime economy metric: " + str(key))
    return _json_mapping(result, "metric_deltas")


def _normalize_economy_event(record: EconomyEventRecord) -> EconomyEventRecord:
    if not isinstance(record, EconomyEventRecord):
        raise TypeError("record must be EconomyEventRecord")
    source_id = _optional_text(record.source_id, "source_id")
    sink_id = _optional_text(record.sink_id, "sink_id")
    coins_earned = _nonnegative_int(record.coins_earned, "coins_earned")
    coins_spent = _nonnegative_int(record.coins_spent, "coins_spent")
    growth_earned = _nonnegative_int(
        record.growth_earned_units, "growth_earned_units"
    )
    if (coins_earned or growth_earned) and not source_id:
        raise ValueError("earned resources require source_id")
    if coins_spent and not sink_id:
        raise ValueError("spent Coins require sink_id")
    return EconomyEventRecord(
        event_key=_required_text(record.event_key, "event_key"),
        event_kind=_required_text(record.event_kind, "event_kind"),
        source_id=source_id,
        sink_id=sink_id,
        scheduler_day=_optional_iso_day(record.scheduler_day, "scheduler_day"),
        occurred_at=_optional_iso_datetime(record.occurred_at, "occurred_at"),
        coins_earned=coins_earned,
        coins_spent=coins_spent,
        growth_earned_units=growth_earned,
        growth_spent_on_landmarks=_nonnegative_int(
            record.growth_spent_on_landmarks,
            "growth_spent_on_landmarks",
        ),
        growth_spent_on_mastery=_nonnegative_int(
            record.growth_spent_on_mastery,
            "growth_spent_on_mastery",
        ),
        item_id=_optional_text(record.item_id, "item_id"),
        quantity=_nonnegative_int(record.quantity, "quantity"),
        metric_deltas=_normalize_metric_deltas(record.metric_deltas),
    )


def _normalize_daily_economy_snapshot(
    record: DailyEconomySnapshotRecord,
) -> DailyEconomySnapshotRecord:
    if not isinstance(record, DailyEconomySnapshotRecord):
        raise TypeError("record must be DailyEconomySnapshotRecord")
    rhythm = _nonnegative_int(
        record.garden_rhythm_percent, "garden_rhythm_percent"
    )
    if rhythm not in {0, 2, 4, 6, 8, 10}:
        raise ValueError("garden_rhythm_percent must be 0, 2, 4, 6, 8, or 10")
    return DailyEconomySnapshotRecord(
        anki_day=_iso_day(record.anki_day, "anki_day"),
        garden_rhythm_percent=rhythm,
        active_garden_bonus_id=_required_text(
            record.active_garden_bonus_id, "active_garden_bonus_id"
        ),
        active_scenery_effect_id=_required_text(
            record.active_scenery_effect_id, "active_scenery_effect_id"
        ),
        snapshot_source=_required_text(record.snapshot_source, "snapshot_source"),
        snapshot_id=_required_text(record.snapshot_id, "snapshot_id"),
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
        int(row["reanswer_floor"]),
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


def _decode_json_object(raw: Any, label: str) -> Mapping[str, Any]:
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError) as error:
        raise RewardLedgerCorruptionError(label + " is not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise RewardLedgerCorruptionError(label + " must be a JSON object.")
    return decoded


def _idempotency_from_row(row: sqlite3.Row) -> IdempotencyRecord:
    return IdempotencyRecord(
        operation_kind=str(row["operation_kind"]),
        operation_id=str(row["operation_id"]),
        request_fingerprint=str(row["request_fingerprint"]),
        outcome=_decode_json_object(
            row["outcome_json"], "An idempotency outcome"
        ),
        occurred_at=str(row["occurred_at"]),
        scheduler_day=str(row["scheduler_day"]),
    )


def _economy_event_from_row(row: sqlite3.Row) -> EconomyEventRecord:
    return EconomyEventRecord(
        event_key=str(row["event_key"]),
        event_kind=str(row["event_kind"]),
        source_id=str(row["source_id"]),
        sink_id=str(row["sink_id"]),
        scheduler_day=str(row["scheduler_day"]),
        occurred_at=str(row["occurred_at"]),
        coins_earned=int(row["coins_earned"]),
        coins_spent=int(row["coins_spent"]),
        growth_earned_units=int(row["growth_earned_units"]),
        growth_spent_on_landmarks=int(row["growth_spent_on_landmarks"]),
        growth_spent_on_mastery=int(row["growth_spent_on_mastery"]),
        item_id=str(row["item_id"]),
        quantity=int(row["quantity"]),
        metric_deltas=_decode_json_object(
            row["metric_deltas_json"], "Economy metric deltas"
        ),
    )


def _daily_economy_snapshot_from_row(
    row: sqlite3.Row,
) -> DailyEconomySnapshotRecord:
    return DailyEconomySnapshotRecord(
        anki_day=str(row["anki_day"]),
        garden_rhythm_percent=int(row["garden_rhythm_percent"]),
        active_garden_bonus_id=str(row["active_garden_bonus_id"]),
        active_scenery_effect_id=str(row["active_scenery_effect_id"]),
        snapshot_source=str(row["snapshot_source"]),
        snapshot_id=str(row["snapshot_id"]),
    )


def _completion_day_from_reward_event(record: RewardEventRecord) -> str:
    if record.source == "all_due" and record.scheduler_day:
        return record.scheduler_day
    if record.event_key.startswith("all_due:"):
        candidate = record.event_key.partition(":")[2]
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            return ""
    return ""


def _completion_day_from_reward_row(row: sqlite3.Row) -> str:
    return _completion_day_from_reward_event(RewardEventRecord(
        event_key=str(row["event_key"]),
        source=str(row["source"]),
        scheduler_day=str(row["scheduler_day"]),
    ))


def _increment_count(target: Dict[str, int], key: Any, amount: Any) -> None:
    normalized_key = str(key)
    normalized_amount = int(amount)
    if not normalized_key or normalized_amount <= 0:
        return
    target[normalized_key] = target.get(normalized_key, 0) + normalized_amount


def _history_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("limit must be a nonnegative integer")
    if value > 366:
        raise ValueError("limit cannot exceed 366")
    return int(value)


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


def _verify_backup_database(path: Path) -> None:
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(str(path))
        integrity_result = tuple(
            str(row[0])
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        )
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    except sqlite3.DatabaseError as error:
        raise RewardLedgerCorruptionError(
            "The reward-ledger backup did not verify."
        ) from error
    finally:
        if connection is not None:
            connection.close()
    if (
        integrity_result != ("ok",)
        or version != LEDGER_SCHEMA_VERSION
        or foreign_key_errors
    ):
        raise RewardLedgerCorruptionError(
            "The reward-ledger backup did not verify."
        )


def _exclusive_verified_copy(source: Path, target: Path) -> None:
    created_target = False
    try:
        with source.open("rb") as reader:
            with target.open("xb") as writer:
                created_target = True
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
        _verify_backup_database(target)
    except BaseException:
        if created_target:
            target.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(str(target) + suffix).unlink(missing_ok=True)
        raise


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'
