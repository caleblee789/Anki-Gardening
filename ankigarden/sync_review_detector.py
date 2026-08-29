from __future__ import annotations

"""Lifecycle and attribution boundary for one normal collection sync.

The detector deliberately does not retain a revlog-ID snapshot. A clean
pre-sync reconciliation drains every answer already visible to this Garden,
and the durable answer-consumption ledger remains the exact authority after
sync. This keeps delayed/lower-ID insertions detectable without copying a
potentially large review history into memory.
"""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping
import uuid


@dataclass(frozen=True)
class SyncAttemptSnapshot:
    batch_id: str
    scheduler_day: str
    collection_token: str = ""
    collection_generation: int = 0
    ledger_revision: int = 0
    reward_baseline: Mapping[str, Any] = field(default_factory=dict)
    valid: bool = True
    invalidation_reason: str = ""
    one_way_replacement: bool = False


class SyncReviewDetector:
    """Prove whether a sync may be interpreted as one incremental merge."""

    def __init__(
        self,
        engine: Any,
        *,
        collection_token_resolver: Callable[[], object] | None = None,
    ) -> None:
        self.engine = engine
        self._attempt: SyncAttemptSnapshot | None = None
        self._collection_generation = 0
        self._collection_token_override: str | None = None
        self._collection_token_resolver = collection_token_resolver

    def _scheduler_day(self) -> str:
        resolver = getattr(self.engine, "_scheduler_day", None)
        if callable(resolver):
            return str(resolver())
        storage = getattr(self.engine, "storage", None)
        resolver = getattr(storage, "current_scheduler_day", None)
        return str(resolver()) if callable(resolver) else ""

    def _ledger_revision(self) -> int | None:
        storage = getattr(self.engine, "storage", None)
        if storage is None or not hasattr(storage, "_ledger_revision"):
            return None
        try:
            return max(0, int(getattr(storage, "_ledger_revision") or 0))
        except (TypeError, ValueError):
            return None

    def _collection_token(self) -> str:
        if self._collection_token_override is not None:
            return self._collection_token_override
        resolver = self._collection_token_resolver
        if callable(resolver):
            try:
                return str(resolver() or "")
            except Exception:
                return ""
        storage = getattr(self.engine, "storage", None)
        mw = getattr(storage, "mw", None)
        collection = getattr(mw, "col", None)
        if collection is None:
            return ""
        path_value = ""
        for attribute in ("path", "collection_path"):
            candidate = getattr(collection, attribute, None)
            try:
                value = candidate() if callable(candidate) else candidate
            except Exception:
                value = ""
            if value:
                path_value = str(value)
                break
        # Object identity distinguishes a temporary/replaced collection even
        # when it reuses the same filesystem path.
        return f"{id(collection)}:{path_value}"

    @staticmethod
    def _result_ok(result: object) -> tuple[bool, str]:
        if isinstance(result, tuple) and result:
            return bool(result[0]), str(result[1] if len(result) > 1 else "")
        return bool(result), ""

    def begin(self) -> SyncAttemptSnapshot:
        """Drain local history, then capture a compact attribution baseline."""

        batch_id = uuid.uuid4().hex
        try:
            prepare = getattr(self.engine, "prepare_sync_reward_boundary", None)
            if callable(prepare):
                clean, message = self._result_ok(prepare())
            else:
                reconcile = getattr(self.engine, "reconcile_reward_history", None)
                if not callable(reconcile):
                    clean, message = False, "reward reconciliation unavailable"
                else:
                    clean, message = self._result_ok(reconcile(
                        persist=True,
                        include_open_day=True,
                        emit_feedback=False,
                    ))
            scheduler_day = self._scheduler_day()
            token = self._collection_token()
            baseline_resolver = getattr(self.engine, "sync_reward_baseline", None)
            baseline = (
                deepcopy(dict(baseline_resolver()))
                if clean and callable(baseline_resolver)
                else {}
            )
            valid = bool(clean and scheduler_day and token)
            live_revision = self._ledger_revision()
            try:
                baseline_revision = max(
                    0, int(baseline.get("ledger_revision", 0) or 0)
                )
            except (TypeError, ValueError):
                baseline_revision = 0
            snapshot = SyncAttemptSnapshot(
                batch_id=batch_id,
                scheduler_day=scheduler_day,
                collection_token=token,
                collection_generation=self._collection_generation,
                ledger_revision=(
                    live_revision
                    if live_revision is not None else baseline_revision
                ),
                reward_baseline=baseline,
                valid=valid,
                invalidation_reason=(
                    "" if valid else message or "sync boundary unavailable"
                ),
            )
        except Exception as error:
            snapshot = SyncAttemptSnapshot(
                batch_id=batch_id,
                scheduler_day="",
                collection_token=self._collection_token(),
                collection_generation=self._collection_generation,
                ledger_revision=max(0, int(self._ledger_revision() or 0)),
                valid=False,
                invalidation_reason=str(error) or "sync boundary unavailable",
            )
        self._attempt = snapshot
        return snapshot

    def invalidate(
        self,
        reason: str = "collection_replaced",
        *,
        one_way_replacement: bool = False,
    ) -> None:
        current = self._attempt
        if current is None:
            return
        self._attempt = replace(
            current,
            valid=False,
            invalidation_reason=str(reason or "collection_replaced"),
            one_way_replacement=(
                current.one_way_replacement or bool(one_way_replacement)
            ),
        )

    def invalidate_one_way(self, reason: str = "collection_replaced") -> None:
        self.invalidate(reason, one_way_replacement=True)

    def note_collection_generation(
        self,
        token: object | None = None,
        *,
        one_way_replacement: bool = False,
    ) -> int:
        """Record a collection-object generation change from Anki lifecycle hooks."""

        self._collection_generation += 1
        self._collection_token_override = (
            None if token is None else str(token or "")
        )
        if self._attempt is not None:
            self.invalidate(
                "collection generation changed",
                one_way_replacement=one_way_replacement,
            )
        return self._collection_generation

    def finish(self) -> SyncAttemptSnapshot | None:
        snapshot = self._attempt
        self._attempt = None
        if snapshot is None or not snapshot.valid:
            return snapshot
        if snapshot.collection_generation != self._collection_generation:
            return replace(
                snapshot,
                valid=False,
                invalidation_reason="collection generation changed",
            )
        if snapshot.collection_token != self._collection_token():
            return replace(
                snapshot,
                valid=False,
                invalidation_reason="collection token changed",
            )
        live_revision = self._ledger_revision()
        if (
            live_revision is not None
            and snapshot.ledger_revision != live_revision
        ):
            return replace(
                snapshot,
                valid=False,
                invalidation_reason="Garden changed during sync",
            )
        return snapshot

    def clear(self) -> None:
        self._attempt = None
