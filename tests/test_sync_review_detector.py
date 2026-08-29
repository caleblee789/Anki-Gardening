from __future__ import annotations

from types import SimpleNamespace

from ankigarden.sync_review_detector import SyncReviewDetector


class BoundaryEngine:
    def __init__(self, *, prepared: bool = True) -> None:
        self.prepared = prepared
        self.prepare_calls = 0
        self.baseline_calls = 0
        self.storage = SimpleNamespace(_ledger_revision=7)

    def prepare_sync_reward_boundary(self):
        self.prepare_calls += 1
        return self.prepared, "Garden is up to date." if self.prepared else "busy"

    def _scheduler_day(self) -> str:
        return "2026-08-29"

    def sync_reward_baseline(self) -> dict[str, object]:
        self.baseline_calls += 1
        return {
            "ledger_revision": 7,
            "active_plant_id": "bluebell",
            "garden_coin_balance": 40,
        }


def test_begin_requires_a_clean_local_boundary_and_captures_reward_baseline() -> None:
    engine = BoundaryEngine()
    detector = SyncReviewDetector(
        engine,
        collection_token_resolver=lambda: "profile-a:collection-a",
    )

    snapshot = detector.begin()

    assert engine.prepare_calls == 1
    assert engine.baseline_calls == 1
    assert snapshot.valid
    assert snapshot.scheduler_day == "2026-08-29"
    assert snapshot.collection_token == "profile-a:collection-a"
    assert snapshot.ledger_revision == 7
    assert snapshot.reward_baseline["active_plant_id"] == "bluebell"
    assert snapshot.batch_id
    assert detector.finish() == snapshot
    assert detector.finish() is None


def test_failed_boundary_proof_invalidates_the_attempt_before_sync() -> None:
    engine = BoundaryEngine(prepared=False)
    detector = SyncReviewDetector(
        engine,
        collection_token_resolver=lambda: "profile-a:collection-a",
    )

    snapshot = detector.begin()

    assert not snapshot.valid
    assert snapshot.invalidation_reason
    assert engine.baseline_calls == 0


def test_collection_generation_change_invalidates_without_using_a_time_watermark() -> None:
    engine = BoundaryEngine()
    token = ["profile-a:collection-a"]
    detector = SyncReviewDetector(
        engine,
        collection_token_resolver=lambda: token[0],
    )
    snapshot = detector.begin()

    token[0] = "profile-a:replacement"
    generation = detector.note_collection_generation()
    finished = detector.finish()

    assert finished is not None
    assert not finished.valid
    assert generation == snapshot.collection_generation + 1
    assert finished.collection_generation == snapshot.collection_generation
    assert finished.invalidation_reason == "collection generation changed"


def test_one_way_replacement_is_explicit_and_cleared_between_attempts() -> None:
    engine = BoundaryEngine()
    detector = SyncReviewDetector(
        engine,
        collection_token_resolver=lambda: "profile-a:collection-a",
    )
    detector.begin()

    detector.invalidate_one_way()
    replaced = detector.finish()

    assert replaced is not None
    assert not replaced.valid
    assert replaced.one_way_replacement
    assert replaced.invalidation_reason == "collection_replaced"

    detector.begin()
    detector.clear()
    assert detector.finish() is None
