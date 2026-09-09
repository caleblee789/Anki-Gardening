from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from ankigarden.achievements import HistoricalReview, analyze_history
from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine
from ankigarden.history_index import HistoryIndex, analyze_indexed_days
from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
from ankigarden.storage import GardenStorage


def _day(value: int) -> str:
    return datetime.fromtimestamp(value / 1000).date().isoformat()


def _verify_index(index, rows):
    index.begin_scan("midnight")
    for offset in range(0, len(rows), 13):
        index.ingest(rows[offset:offset + 13], _day)
    return index.finish_scan()


def test_daily_index_matches_full_history_through_edits_restarts_and_day_changes(tmp_path):
    start = datetime(2025, 1, 1, 12)
    rows = [
        (int((start + timedelta(days=offset)).timestamp() * 1000) + answer, answer % 7 + 1,
         answer % 4 + 1, 10, 5, 2500, 500, answer % 4)
        for offset in range(366) if offset != 150
        for answer in range(104 if offset == 100 else 5)
    ]
    index = HistoryIndex(tmp_path / "history.sqlite3")

    def parity(current_rows):
        for include_open_day in (False, True):
            reference = analyze_history(
                tuple(HistoricalReview(row[0], row[0], _day(row[0]), row[2])
                      for row in current_rows
                      if _day(row[0]) < "2026-01-01" or include_open_day),
                current_open_day="2026-01-01",
            )
            actual = analyze_indexed_days(index.summaries(), current_open_day="2026-01-01", include_open_day=include_open_day)
            assert {k: v for k, v in asdict(actual).items() if k != "fingerprint"} == {
                k: v for k, v in asdict(reference).items() if k != "fingerprint"
            }

    _verify_index(index, rows)
    parity(rows)

    assert _verify_index(index, rows) == {"deleted": 0, "rebuilt_days": 0}
    # A changed rating, an older insertion, and a deletion preserve max(id).
    rows[5] = (*rows[5][:2], 4, *rows[5][3:])
    del rows[20]
    rows.insert(15, (rows[14][0] + 1, 20, 3, 10, 5, 2500, 500, 1))
    _verify_index(index, rows)
    parity(rows)
    index.begin_scan("midnight")
    index.ingest(rows[:13], _day)
    with pytest.raises(ValueError, match="incomplete"):
        index.summaries()
    index = HistoryIndex(index.path)
    _verify_index(index, rows)
    parity(rows)
    appended = (rows[-1][0] + 1, 42, 3, 10, 5, 2500, 500, 1)
    index.append_committed(appended, _day(appended[0]))
    rows.append(appended)
    parity(rows)
    # Disposable cache damage must rebuild from the source, never invent
    # achievement counts or prevent the collection from opening.
    with sqlite3.connect(index.path) as db:
        db.execute("UPDATE day_summary SET payload='{}'")
    _verify_index(index, rows)
    parity(rows)
    index.path.write_bytes(b"invalid disposable index")
    _verify_index(index, rows)
    parity(rows)


def test_day_mapper_preserves_wall_clock_days_across_dst(monkeypatch):
    import time
    from ankigarden.history_index import SchedulerDayMapper
    if not hasattr(time, "tzset"):
        pytest.skip("Changing the process timezone requires time.tzset")
    try:
        with monkeypatch.context() as context:
            context.setenv("TZ", "America/Chicago")
            time.tzset()
            for date_text in ("2026-03-07", "2026-10-31"):
                start = int(datetime.fromisoformat(date_text).timestamp() * 1000)
                for hour in (1, 2, 4):
                    cutoff = datetime(2026, 1, 1, hour, 30)
                    mapper = SchedulerDayMapper(cutoff)
                    for delta in range(0, 3 * 86_400_000, 15 * 60_000):
                        value = start + delta
                        assert mapper(value) == GardenStorage._scheduler_day_from_wall_cutoff(value, cutoff)
    finally:
        time.tzset()


class _Db:
    def __init__(self, rows):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("CREATE TABLE revlog(id INTEGER PRIMARY KEY,cid,ease,ivl,lastIvl,factor,time,type)")
        self.connection.executemany("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", rows)

    def all(self, sql, *args):
        return self.connection.execute(sql, args).fetchall()

    def scalar(self, sql, *args):
        row = self.connection.execute(sql, args).fetchone()
        return row[0] if row else None

    def first(self, sql, *args):
        return self.connection.execute(sql, args).fetchone()


class _Config:
    def value(self, key, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys, default=None):
        value = DEFAULT_CONFIG
        for key in keys:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        return value or default


def _engine_at(root, rows, *, indexed, current_day=None):
    storage = object.__new__(GardenStorage)
    storage.user_files_dir = root
    storage.cache_dir = root / "cache"
    storage.data_path = root / "garden_state.json"
    storage.asset_metadata = root / "asset_metadata.json"
    storage.database_path = root / "garden_state.sqlite3"
    storage.addon_dir = Path(__file__).resolve().parents[1] / "ankigarden"
    storage.assets_root = storage.addon_dir / "assets"
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=_Db(rows)))
    storage.config = _Config()
    storage.runtime_pending = False
    storage._runtime_initialized = True
    day = current_day or _day(rows[-1][0])
    cutoff = int((datetime.fromisoformat(day) + timedelta(days=1)).timestamp() * 1000)
    storage.current_scheduler_day = lambda: day
    storage.current_scheduler_day_bounds_ms = lambda: (cutoff - 86_400_000, cutoff)
    storage.current_time_ms = lambda: rows[-1][0] + 1000
    activation = rows[0][0] + 2
    storage.state = GardenState(
        plants=[Plant("p1", "bonsai", "Moss", 0)], active_plant_id="p1",
        starter_selection_complete=True, garden_setup_version=1,
        daily_stats=DailyStats(day=day), reward_seed="performance-parity",
        reward_state_initialized=True, reward_activation_ms=activation,
        progression_activation_ms=activation, garden_find_activation_ms=activation,
        active_plant_periods=[ActivePlantPeriod(_day(activation), "p1", activation)],
    )
    storage._install_reward_database(storage.state)
    if indexed:
        storage.history_index = HistoryIndex(root / "history.sqlite3")
        _verify_index(storage.history_index, rows)
        while aliases := storage.history_index.prepare_alias_page(storage.database_path, limit=7):
            for revlog_id, lineage in aliases:
                storage.stage_answer_lineage_alias(revlog_id, lineage)
            storage.save()
    return GardenGameEngine(storage.config, storage), storage


def test_batched_replay_preserves_exact_rewards_lineages_and_durable_restart(tmp_path):
    start = datetime(2026, 8, 1, 12)
    rows = [(int((start + timedelta(days=day)).timestamp() * 1000) + answer,
             answer % 3 + 1, answer % 4 + 1, 10, 5, 2500, 500, 1)
            for day in range(9) for answer in range(15)]
    current_day = _day(rows[-1][0])
    # Imported future timestamps must not advance today's counted-history
    # cursor and suppress the next real local answer.
    rows.append((rows[-1][0] + 2 * 86_400_000, 42, 3, 10, 5, 2500, 500, 1))
    reference, reference_storage = _engine_at(tmp_path / "reference", rows, indexed=False, current_day=current_day)
    indexed, storage = _engine_at(tmp_path / "indexed", rows, indexed=True, current_day=current_day)
    storage._history_batch_limit = 7
    assert reference.reconcile_reward_history()[0]
    for _ in range(len(rows)):
        assert indexed.reconcile_reward_history()[0]
        if not next(storage.history_index.reward_pages(
            activation_ms=storage.state.reward_activation_ms, through_day=storage.current_scheduler_day(),
            ledger_path=storage.database_path, limit=1,
        ), []):
            break
    else:
        pytest.fail("Replay did not finish")
    assert storage.lifetime_economy_aggregates() == reference_storage.lifetime_economy_aggregates()
    for field in ("currency_balance", "stored_growth_units", "lifetime_eligible_answers", "streak_days",
                  "garden_find_drought_count", "consumables", "processed_revlog_ids",
                  "achievement_history_high_water_revlog_id"):
        assert getattr(indexed.state, field) == getattr(reference.state, field), field
    assert indexed.state.plants[0].growth_units == reference.state.plants[0].growth_units
    assert storage._reward_ledger.all_revlog_bindings() == reference_storage._reward_ledger.all_revlog_bindings()
    before = storage._ledger_revision
    assert indexed.reconcile_reward_history()[0]
    assert storage._ledger_revision == before
    storage._reward_ledger.close()
    storage.state = storage._load_authoritative_state()
    assert storage.lifetime_economy_aggregates() == reference_storage.lifetime_economy_aggregates()
    storage._reward_ledger.close()
    reference_storage._reward_ledger.close()


def test_background_reconciliation_cancels_stale_reads_and_protects_undo_reanswer(tmp_path, monkeypatch):
    import sys
    from ankigarden.runtime import ReconciliationCoordinator
    from ankigarden.sync_reward_processor import SyncRewardProcessor
    queued = []

    class QueryOp:
        def __init__(self, *, parent, op, success):
            self.parent, self.op, self.success = parent, op, success

        def failure(self, callback):
            self.failed = callback
            return self

        def without_collection(self):
            return self

        def run_in_background(self):
            def complete():
                try:
                    self.success(self.op(self.parent.col))
                except Exception as error:
                    self.failed(error)
            queued.append(complete)

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=QueryOp))
    monkeypatch.setattr(ReconciliationCoordinator, "_schedule", staticmethod(lambda callback, delay=0: queued.append(callback)))
    now = int(datetime(2026, 8, 1, 12).timestamp() * 1000)
    rows = [(now + i, 1, 3, 10, 5, 2500, 500, 1) for i in range(20)]
    engine, storage = _engine_at(tmp_path / "runtime", rows, indexed=False)
    completions = []
    presented = []
    app = SimpleNamespace(engine=engine, storage=storage, _sync_reward_summary_enabled=lambda: True,
                          _runtime_reconciled=lambda: completions.append(True))
    app.sync_reward_processor = SyncRewardProcessor(engine, storage, SimpleNamespace(enqueue=presented.append))
    runtime = ReconciliationCoordinator(app)

    def drain():
        for _ in range(1000):
            if not queued:
                return
            queued.pop(0)()
        pytest.fail("Background work did not settle")

    runtime.request("startup")
    queued.pop(0)()  # Queue the initial audit, then invalidate its generation.
    runtime.invalidate("collection edited")
    drain()
    assert completions == [True]
    assert not storage.runtime_pending
    # A collection callback during sync must not release the suspension or
    # let an already queued query commit against the in-flight collection.
    runtime.invalidate("sync start", suspended=True)
    runtime.invalidate("collection reload")
    runtime.operation_finished(SimpleNamespace(card=True), None)
    drain()
    assert runtime.suspended and storage.runtime_pending
    assert completions == [True]
    runtime.invalidate("sync completion", suspended=False)
    drain()
    assert not runtime.suspended and not storage.runtime_pending
    completions.pop()
    before = storage.lifetime_economy_aggregates()
    storage.mw.col.db.connection.execute("DELETE FROM revlog WHERE id=?", (rows[-1][0],))
    runtime.review_undone(now + 30)
    replacement = (now + 40, *rows[-1][1:])
    storage.mw.col.db.connection.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", replacement)
    runtime.defer_answer(SimpleNamespace(id=1), 3, "same-window")
    drain()
    assert completions == [True, True]
    assert storage.lifetime_economy_aggregates() == before
    ledger = storage._reward_ledger
    assert ledger.binding_for_revlog(replacement[0]) == ledger.binding_for_revlog(rows[-1][0])
    assert ledger.deferred_review_context(replacement[0]) == {}
    # Old, nonpayable answers today must not make the first live answer
    # ambiguous after a complete verification.
    appended = (now + 50, *rows[-1][1:])
    storage.mw.col.db.connection.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", appended)
    proof = storage.load_proven_local_answer(
        after_id=storage.state.last_processed_revlog_id, card_id=1, ease=3,
    )
    assert proof is not None
    assert proof.row[0] == appended[0]
    # A cutoff-hour change needs a fresh verification even on the same day.
    old_bounds = storage.current_scheduler_day_bounds_ms()
    storage.current_scheduler_day_bounds_ms = lambda: tuple(value + 3_600_000 for value in old_bounds)
    assert not runtime.request("scheduler settings changed")
    assert storage.runtime_pending
    drain()
    assert completions == [True, True, True]
    # Reviews made while replacement history is being verified must earn
    # rewards, while imported replacement history remains a nonpaying baseline.
    reviewed_before = storage.state.total_reviews
    runtime.invalidate("collection replacement", suspended=True, replacement=True)
    remote_rows = [(now + 60 + i, 2, 3, 10, 5, 2500, 500, 1) for i in range(12)]
    storage.mw.col.db.connection.executemany("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", remote_rows)
    runtime.invalidate("collection reopened", suspended=False, replacement=True)
    local = (now + 100, 3, 3, 10, 5, 2500, 500, 1)
    storage.mw.col.db.connection.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", local)
    runtime.defer_answer(SimpleNamespace(id=3), 3, "replacement-window")
    drain()
    assert storage.state.total_reviews == reviewed_before + 1
    assert ledger.deferred_review_context(local[0]) == {}
    runtime.invalidate("repeat sync", suspended=False)
    drain()
    assert storage.state.total_reviews == reviewed_before + 1
    # Startup, ordinary operations and deferred local answers must not masquerade
    # as sync rewards, even when the learner enables sync summaries.
    assert presented == []
    incoming = (now + 200, 4, 3, 10, 5, 2500, 500, 1)
    storage.mw.col.db.connection.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", incoming)
    runtime.invalidate("sync completion", suspended=False, from_sync=True)
    runtime.operation_finished(SimpleNamespace(card=True), None)
    runtime.request("home rendering")
    drain()
    assert sum(summary.eligible_answer_count for summary in presented) == 1
    assert storage.state.total_reviews == reviewed_before + 2
    presented.clear()
    browser_answer = (now + 201, 5, 3, 10, 5, 2500, 500, 1)
    storage.mw.col.db.connection.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", browser_answer)
    runtime.operation_finished(SimpleNamespace(card=True), None)
    drain()
    assert storage.state.total_reviews == reviewed_before + 3
    assert presented == []
    runtime.close()
    drain()
    ledger.close()


@pytest.mark.parametrize("missing_obligations", [0, 1])
def test_batched_sync_completion_matches_unbatched_after_restart(tmp_path, missing_obligations):
    from ankigarden.storage import DueObligationStatus
    from ankigarden.sync_reward_processor import SyncRewardProcessor
    from ankigarden.sync_review_detector import SyncAttemptSnapshot

    now = int(datetime(2026, 8, 1, 12).timestamp() * 1000)
    rows = [(now + i, i + 1, 3, 10, 5, 2500, 500, 1) for i in range(20)]
    engines = [_engine_at(tmp_path / name, rows, indexed=indexed)
               for name, indexed in (("reference", False), ("batched", True))]
    # The first two rows precede activation; 18 new answers complete the queue.
    for engine, storage in engines:
        engine.observe_due_start(DueObligationStatus(review_count=18 + missing_obligations))
        storage.due_obligations = lambda: DueObligationStatus()
    reference, reference_storage = engines[0]
    engine, storage = engines[1]
    storage._history_batch_limit = 7

    def process(engine, storage, batch):
        processor = SyncRewardProcessor(engine, storage, SimpleNamespace())
        return processor.process(SyncAttemptSnapshot(
            batch_id=batch, scheduler_day=storage.current_scheduler_day(),
            reward_baseline=engine.sync_reward_baseline(),
        ), raise_on_failure=True)

    process(reference, reference_storage, "reference")
    process(engine, storage, "batch-0")
    assert not storage.state.daily_completion.reward_claimed
    storage._reward_ledger.close()
    storage.state = storage._load_authoritative_state()
    engine = GardenGameEngine(storage.config, storage)
    for batch in range(1, 4):
        process(engine, storage, f"batch-{batch}")
    actual = storage.state.daily_completion
    expected = reference_storage.state.daily_completion
    assert actual.reward_claimed == expected.reward_claimed == (missing_obligations == 0)
    assert actual.starting_required_cards_completed == expected.starting_required_cards_completed == 18
    assert actual.unresolved_obligation_disappearances == expected.unresolved_obligation_disappearances == missing_obligations
    assert storage.lifetime_economy_aggregates() == reference_storage.lifetime_economy_aggregates()
    if not missing_obligations:
        summary = storage.state.pending_sync_reward_summary
        assert summary["all_clear_earned"]
    before = storage._ledger_revision
    process(engine, storage, "repeat")
    assert storage._ledger_revision == before
    for _, owner in engines:
        owner._reward_ledger.close()
