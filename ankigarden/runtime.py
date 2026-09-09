from __future__ import annotations

"""One cancellable reconciliation pipeline, independent of view rendering."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime
import logging
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from typing import Any, Callable
import uuid

from .history_index import HISTORY_PAGE_SIZE, HistoryIndex, SchedulerDayMapper
from .performance import RUNTIME_PERFORMANCE


logger = logging.getLogger(__name__)


def audit_ledger(database: Path) -> tuple[int, dict[str, Any]]:
    """Verify a consistent private copy without owning the live writer."""
    from .models.state import GardenState
    from .reward_ledger import RewardLedger
    from .storage import GardenStorage

    with TemporaryDirectory(prefix="anki-garden-ledger-audit-") as temporary:
        destination = Path(temporary) / "ledger.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(str(destination))) as target:
                source.backup(target, pages=256)
        with RewardLedger(destination) as ledger:
            snapshot = ledger.load_state_snapshot()
            if snapshot is None:
                raise ValueError("Garden state is unavailable")
            ledger.reset_economy_projections()
            probe = object.__new__(GardenStorage)
            probe._reward_ledger = ledger
            probe._ledger_revision = snapshot.revision
            probe.state = GardenState.from_dict(dict(snapshot.payload))
            probe.refresh_lifetime_economy_aggregates()
            return snapshot.revision, deepcopy(ledger._economy_projections)


class ReconciliationCoordinator:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.storage = app.storage
        self.generation = 0
        self.busy = False
        self.dirty = True
        self.suspended = False
        self.closed = False
        self._job_active = False
        self._scheduled = False
        self._replacement = False
        self._batch_size = 8
        self._alias_batch_size = 256
        self._alias_after_id = 0
        self._source = "startup"
        self._sync_rewards_pending = False
        self._batch_id = ""
        self._batch_number = 0
        self._after_id = 0
        self._upper_id = 0
        self._append_scan = False
        self.storage._history_after_id = 0
        self._collection = None
        self._audit_complete = False
        self._cutoff = None
        self._last_answer_handler = None
        self._verified_day = ""
        self._verified_boundary = None
        self._scan_boundary = None
        self._started_at = None
        self.index = HistoryIndex(self.storage.cache_dir / "review-history.sqlite3")

    @staticmethod
    def _schedule(callback: Callable[[], None], delay: int = 0) -> None:
        from aqt.qt import QTimer
        QTimer.singleShot(delay, callback)

    def request(self, source: str, *, replacement: bool = False) -> bool:
        if self.closed:
            return False
        self._source = str(source)
        self._replacement = self._replacement or replacement
        if not self.dirty and not self.busy:
            try:
                if self._verified_boundary != self._scheduler_boundary():
                    self.invalidate("scheduler day changed")
                    return False
            except Exception:
                self.invalidate("scheduler unavailable")
                return False
        if not self.dirty and not self.busy:
            return True
        if self.busy:
            return False
        self.busy = True
        if self._started_at is None:
            self._started_at = RUNTIME_PERFORMANCE.begin()
        self.storage.runtime_pending = True
        from .notices import HISTORY_UPDATE_MESSAGE, USER_NOTICES
        USER_NOTICES.publish(HISTORY_UPDATE_MESSAGE, key="review_history")
        if not self.suspended and not self._job_active and not self._scheduled:
            self._scheduled = True
            self._schedule(self._start)
        return False

    def _scheduler_boundary(self) -> tuple[Any, ...]:
        return (
            self.storage.current_scheduler_day(),
            self.storage.current_scheduler_day_bounds_ms(),
            time.tzname, time.timezone, time.altzone,
        )

    def invalidate(self, reason: str, *, suspended: bool | None = None, replacement: bool = False,
                   from_sync: bool = False) -> None:
        self.generation += 1
        self.dirty = True
        self.busy = False
        self.storage.history_index = None
        self.storage._verified_history_high_water = 0
        self.storage.invalidate_due_snapshot()
        # Ordinary invalidations cannot release a sync/collection-close hold.
        if suspended is not None:
            self.suspended = suspended
        self._replacement = self._replacement or replacement
        # Helper operations and view refreshes can supersede the scan's source.
        # Retain an actual sync completion until its reconciliation settles.
        self._sync_rewards_pending = self._sync_rewards_pending or from_sync
        self.request(reason, replacement=replacement)

    def close(self) -> None:
        self.closed = True
        self._sync_rewards_pending = False
        self.generation += 1
        self.storage.history_index = None
        self.storage.runtime_pending = True

    def note_local_answer(self, handler: Any) -> None:
        self._last_answer_handler = handler

    def operation_finished(self, changes: Any, handler: Any) -> bool:
        known_answer = handler is not None and handler is self._last_answer_handler
        self._last_answer_handler = None
        if known_answer:
            return True
        self.storage.invalidate_due_snapshot()
        # Note text, deck selection and scheduler settings do not alter revlog.
        # Unknown card operations (including imports) need content verification.
        if bool(getattr(changes, "card", False)):
            self.invalidate("collection operation")
        elif bool(getattr(changes, "config", False)):
            self.request("scheduler settings changed")
        return False

    def defer_answer(self, card: Any, ease: int, review_window_token: str) -> int:
        RUNTIME_PERFORMANCE.count("review.deferred")
        col = getattr(self.storage.mw, "col", None)
        if col is None:
            return 0
        row = col.db.first(
            "SELECT id, ease FROM revlog WHERE cid=? AND type IN (0,1,2,3) ORDER BY id DESC LIMIT 1",
            int(card.id),
        )
        if row is None or int(row[1]) != int(ease):
            return 0
        revlog_id = int(row[0])
        self.storage._reward_ledger.remember_deferred_review(
            revlog_id, review_window_token=review_window_token,
        )
        if revlog_id <= self._upper_id:
            self.invalidate("non-appended local review")
        self.request("local review during verification")
        return revlog_id

    def answer_committed(self, row: tuple[Any, ...], day: str) -> None:
        if self.busy or self.storage.history_index is None:
            return
        try:
            self.index.append_committed(row, day)
            self.storage._verified_history_high_water = max(
                getattr(self.storage, "_verified_history_high_water", 0), int(row[0]),
            )
        except Exception:
            self.invalidate("review index update failed")

    def review_undone(self, occurred_at_ms: int) -> None:
        self.storage._reward_ledger.remember_review_undo(occurred_at_ms)
        self.invalidate("review undo")

    def _run(self, operation: Callable[..., Any], success: Callable[[Any], None], *, collection: bool) -> None:
        from aqt.operations import QueryOp

        token = self.generation
        self._job_active = True
        def execute(col: Any) -> Any:
            started = RUNTIME_PERFORMANCE.begin()
            try:
                if collection and col is not self._collection:
                    raise ValueError("The collection changed during Garden verification")
                return operation(col) if collection else operation()
            finally:
                RUNTIME_PERFORMANCE.finish("history.query" if collection else "history.compute", started)
        def done(result: Any) -> None:
            self._job_active = False
            if self.closed:
                return
            if token != self.generation:
                self.busy = False
                self.request(self._source)
                return
            try:
                success(result)
            except Exception as error:
                self._failed(error)
        def failed(error: Exception) -> None:
            self._job_active = False
            if not self.closed and token == self.generation:
                self._failed(error)
            elif not self.closed:
                self.busy = False
                self.request(self._source)
        operation_handle = QueryOp(parent=self.storage.mw, op=execute, success=done).failure(failed)
        if not collection:
            operation_handle = operation_handle.without_collection()
        operation_handle.run_in_background()

    def _start(self) -> None:
        self._scheduled = False
        if self.closed or self.suspended or self._job_active:
            return
        self._collection = getattr(self.storage.mw, "col", None)
        if self._collection is None or getattr(self._collection, "db", None) is None:
            self._scheduled = True
            self._schedule(self._start, 100)
            return
        try:
            _, cutoff_ms = self.storage.current_scheduler_day_bounds_ms()
            self._cutoff = datetime.fromtimestamp(cutoff_ms / 1000)
            self._day_mapper = SchedulerDayMapper(self._cutoff)
            self._scan_boundary = self._scheduler_boundary()
        except Exception:
            self._scheduled = True
            self._schedule(self._start, 100)
            return
        self._batch_id = "reconcile:" + uuid.uuid4().hex
        self._batch_number = 0
        self._after_id = 0
        self._upper_id = 0
        self._append_scan = False
        self._alias_after_id = 0
        self.storage._history_after_id = 0
        if self._audit_complete:
            self._begin_scan()
        else:
            self._run(lambda: audit_ledger(self.storage.database_path), self._audited, collection=False)

    def _audited(self, result: tuple[int, dict[str, Any]]) -> None:
        revision, projections = result
        if revision != self.storage._ledger_revision:
            self.invalidate("Garden changed during verification")
            return
        ledger = self.storage._reward_ledger
        ledger._economy_projections = projections
        ledger._projection_data_version = ledger._data_version()
        self._audit_complete = True
        self._begin_scan()

    def _begin_scan(self) -> None:
        boundary = f"{self._cutoff.time().isoformat()}:{time.tzname!r}"
        self._run(lambda: self.index.begin_scan(boundary), lambda _result: self._snapshot_upper(), collection=False)

    def _snapshot_upper(self) -> None:
        self._run(lambda col: int(col.db.scalar("select max(id) from revlog where type in (0, 1, 2, 3)") or 0),
                  self._got_upper, collection=True)

    def _got_upper(self, value: int) -> None:
        self._upper_id = max(self._upper_id, int(value))
        self._fetch_page()

    def _fetch_page(self) -> None:
        if self._after_id >= self._upper_id:
            self._finish_scan()
            return
        after, upper = self._after_id, self._upper_id
        self._run(lambda col: col.db.all(
            "select id, cid, ease, ivl, lastIvl, factor, time, type from revlog "
            "where id > ? and id <= ? and type in (0, 1, 2, 3) order by id limit ?",
            after, upper, HISTORY_PAGE_SIZE,
        ), self._got_page, collection=True)

    def _got_page(self, rows: list[tuple[Any, ...]]) -> None:
        RUNTIME_PERFORMANCE.count("history.rows-read", len(rows))
        if not rows:
            self._after_id = self._upper_id
            self._finish_scan()
            return
        self._after_id = int(rows[-1][0])
        day_for_id = self._day_mapper
        self._run(lambda: self.index.ingest(rows, day_for_id), lambda _result: self._fetch_page(), collection=False)

    def _finish_scan(self) -> None:
        self._run(lambda: self.index.finish_scan(prune=not self._append_scan),
                  lambda _result: self._check_tail(), collection=False)

    def _check_tail(self) -> None:
        self._run(lambda col: int(col.db.scalar("select max(id) from revlog where type in (0, 1, 2, 3)") or 0),
                  self._tail_checked, collection=True)

    def _tail_checked(self, high_water: int) -> None:
        if high_water > self._upper_id:
            self._append_scan = True
            self._upper_id = high_water
            self._fetch_page()
            return
        self._run(lambda: self.index.pending_undo_hint(self.storage.database_path), self._undo_checked, collection=False)

    def _undo_checked(self, hint: tuple[int, str, int] | None) -> None:
        if hint is not None:
            self.storage._reward_ledger.resolve_review_undo(*hint)
            self.storage._refresh_reanswer_hint_cache(self.storage.state)
            self._run(lambda: self.index.pending_undo_hint(self.storage.database_path), self._undo_checked, collection=False)
            return
        self._prepare_aliases()

    def _prepare_aliases(self) -> None:
        self._run(lambda: self.index.prepare_alias_page(self.storage.database_path, limit=self._alias_batch_size, after_id=self._alias_after_id),
                  self._aliases_ready, collection=False)

    def _aliases_ready(self, aliases: list[tuple[int, str]]) -> None:
        if aliases:
            started = time.perf_counter()
            checkpoint = self.storage.reward_ledger_checkpoint()
            self.storage._allow_runtime_commit = True
            try:
                for revlog_id, lineage in aliases:
                    self.storage.stage_answer_lineage_alias(revlog_id, lineage)
                self.storage.save()
                self._alias_after_id = aliases[-1][0]
            except Exception:
                self.storage.rollback_reward_ledger(checkpoint)
                raise
            finally:
                self.storage._allow_runtime_commit = False
            elapsed = (time.perf_counter() - started) * 1000
            RUNTIME_PERFORMANCE.record("history.alias-commit", elapsed)
            if elapsed > 20:
                self._alias_batch_size = max(16, self._alias_batch_size // 2)
            self._prepare_aliases()
            return
        self.storage.history_index = self.index
        self.storage._history_batch_limit = self._batch_size
        self._schedule_batch()

    def _schedule_batch(self, delay: int = 0) -> None:
        generation = self.generation
        self._schedule(
            lambda: self._apply_batch() if not self.closed and generation == self.generation else None,
            delay,
        )

    def _apply_batch(self) -> None:
        if self.closed or self.suspended or self.storage.history_index is None:
            self.request(self._source)
            return
        started = time.perf_counter()
        self.storage._allow_runtime_commit = True
        try:
            if not self.storage._runtime_initialized:
                self.storage._ensure_defaults()
                self.app.engine.initialize_runtime_state()
                self.storage._runtime_initialized = True
            if self._replacement:
                ok, message = self.app.engine.baseline_reward_history("collection_replaced")
                if not ok:
                    raise ValueError(message)
            else:
                from .sync_review_detector import SyncAttemptSnapshot
                snapshot = SyncAttemptSnapshot(
                    batch_id=f"{self._batch_id}:{self._batch_number}",
                    scheduler_day=self.storage.current_scheduler_day(),
                    reward_baseline=self.app.engine.sync_reward_baseline(),
                )
                self.app.sync_reward_processor.process(
                    snapshot, presentation_enabled=(
                        self._sync_rewards_pending and self.app._sync_reward_summary_enabled()
                    ),
                    raise_on_failure=True,
                )
            self.storage._history_after_id = max(
                self.storage._history_after_id, getattr(self.storage, "_history_loaded_through", 0),
            )
            self._batch_number += 1
            elapsed = (time.perf_counter() - started) * 1000
            RUNTIME_PERFORMANCE.record("history.commit-batch", elapsed)
            if elapsed > 20 and self._batch_size > 1:
                self._batch_size = max(1, self._batch_size // 2)
            self.storage._history_batch_limit = self._batch_size
            remaining = next(self.index.reward_pages(
                activation_ms=self.storage.state.reward_activation_ms,
                through_day=self.storage.current_scheduler_day(), ledger_path=self.storage.database_path, limit=1,
                after_id=self.storage._history_after_id,
            ), [])
            if remaining:
                self._schedule_batch(1)
            elif self._replacement:
                # The baseline deliberately leaves deferred local answers
                # unconsumed. Replay them normally after replacement history
                # has been drained, including answers below the batch cursor.
                self._replacement = False
                self.storage._history_after_id = 0
                self._schedule_batch(1)
            else:
                self._run(lambda col: int(col.db.scalar("select max(id) from revlog where type in (0, 1, 2, 3)") or 0),
                          self._complete_or_extend, collection=True)
        except Exception as error:
            self._failed(error)
        finally:
            self.storage._allow_runtime_commit = False

    def _complete_or_extend(self, high_water: int) -> None:
        if self._scan_boundary != self._scheduler_boundary():
            self.invalidate("scheduler boundary changed during verification")
            return
        if high_water > self._upper_id:
            self._append_scan = True
            self._upper_id = high_water
            self._fetch_page()
            return
        self.busy = self.dirty = False
        self._verified_day = self.storage.current_scheduler_day()
        self._verified_boundary = self._scan_boundary
        self.storage._verified_history_high_water = max(
            (int(row["last"]) for row in self.index.summaries() if row["day"] <= self._verified_day), default=0,
        )
        self._replacement = False
        self._sync_rewards_pending = False
        self.storage.runtime_pending = False
        self.storage._history_batch_limit = None
        self.storage._history_after_id = 0
        self.storage._reward_ledger.prune_deferred_reviews()
        RUNTIME_PERFORMANCE.finish("history.total", self._started_at)
        self._started_at = None
        self.app._runtime_reconciled()

    def _failed(self, error: Exception) -> None:
        from .notices import USER_NOTICES
        logger.error("Anki Garden: background reconciliation deferred", exc_info=(type(error), error, error.__traceback__))
        self.dirty = True
        self.busy = False
        self.storage.runtime_pending = True
        self.storage.history_index = None
        USER_NOTICES.publish(
            "Garden progress is temporarily paused while review history is unavailable. "
            "Your Anki reviews are safe, and Garden will retry automatically.", key="review_history",
        )
        self._schedule(lambda: self.request(self._source), 5_000)
