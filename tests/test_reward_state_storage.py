from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from ankigarden.models.state import (
    CurrencyTransaction,
    FeedbackEvent,
    GardenFindOutcome,
    GardenState,
    MAX_REWARD_RECEIPTS,
    RewardDrop,
    RewardReceipt,
    STATE_VERSION,
    bounded_reward_receipts,
)
from ankigarden.storage import (
    GardenStorage,
    RevlogReadError,
    assign_stable_answer_identities,
    migrate_modern_state,
)


def test_schema20_reward_migration_preserves_legacy_and_starts_new_find_drought() -> None:
    payload = GardenState().to_dict()
    payload["version"] = 20
    for key in (
        "reward_state_initialized",
        "reward_activation_ms",
        "progression_activation_ms",
        "applied_reward_event_keys",
        "recent_reward_receipts",
        "processed_answer_keys",
        "pending_reanswer_lineages",
        "achievement_history_fingerprint",
        "achievement_history_high_water_revlog_id",
        "finalized_day_fingerprints",
        "current_non_again_run",
        "lifetime_eligible_answers",
        "garden_find_activation_ms",
        "garden_find_drought_count",
        "garden_find_daily_counts",
        "garden_find_reward_daily_counts",
        "garden_find_outcomes",
        "garden_find_ultra_misses",
    ):
        payload.pop(key, None)
    payload["reward_seed"] = "persisted-secret"
    payload["eligible_reward_count"] = 123
    payload["ultra_pity_misses"] = 45_678
    payload["claimed_streak_rewards"] = [30]
    payload["currency_balance"] = 7
    payload["currency_transactions"] = [{
        "transaction_id": "legacy-tx",
        "event_key": "legacy:event",
        "reason": "Legacy reward",
        "delta": 7,
        "balance": 7,
        "occurred_at": "2026-08-20T12:00:00+00:00",
    }]
    payload["reward_drop_history"] = [{
        "revlog_id": 123,
        "scheduler_day": "2026-08-20",
        "kind": "booster_potion",
        "amount": 1,
        "occurred_at": "2026-08-20T12:00:00+00:00",
    }]
    payload["consumables"].pop("fertilizer_basic", None)

    migrated = migrate_modern_state(payload)

    assert migrated.version == STATE_VERSION == 21
    assert migrated.reward_seed == "persisted-secret"
    assert migrated.currency_transactions[0].event_key == "legacy:event"
    assert migrated.reward_drop_history == [RewardDrop(
        123,
        "2026-08-20",
        "booster_potion",
        1,
        "2026-08-20T12:00:00+00:00",
    )]
    assert migrated.applied_reward_event_keys == ["legacy:event", "streak:30"]
    assert migrated.eligible_reward_count == 123
    assert migrated.garden_find_drought_count == 0
    assert migrated.garden_find_reward_daily_counts == {}
    assert migrated.garden_find_ultra_misses == 45_678
    assert migrated.reward_state_initialized is False
    assert migrated.reward_activation_ms == 0
    assert migrated.progression_activation_ms == 0
    assert migrated.garden_find_activation_ms == 0
    assert migrated.consumables["fertilizer_basic"] == 0


def test_reward_authorities_round_trip_without_using_bounded_history_for_replay(
    tmp_path,
) -> None:
    lineage = "v1|2026-08-20|42|1"
    original_revlog_id = 1_776_700_000_001
    reanswer_floor = original_revlog_id + 50_000
    event_keys = [f"event:{index}" for index in range(MAX_REWARD_RECEIPTS + 25)]
    outcomes = {
        f"standard:answer:{index}": GardenFindOutcome(
            answer_key=f"answer:{index}",
            scheduler_day="2026-08-20",
            status="miss",
            pool_id="standard",
            pool_version="standard-v1",
            occurred_at="2026-08-20T12:00:00+00:00",
        )
        for index in range(MAX_REWARD_RECEIPTS + 25)
    }
    outcomes["environment:answer:0"] = GardenFindOutcome(
        answer_key="answer:0",
        scheduler_day="2026-08-20",
        status="miss",
        pool_id="environment",
        pool_version="environment-v1",
        occurred_at="2026-08-20T12:00:00+00:00",
    )
    state = GardenState(
        currency_balance=10,
        currency_transactions=[CurrencyTransaction(
            "tx",
            "event:bundle",
            "Bundle",
            10,
            10,
            "2026-08-20T12:00:00+00:00",
            "credit",
            "achievement",
            "streak_30",
            "2026-08-20",
            "bundle:30",
        )],
        pending_feedback=[FeedbackEvent(
            "feedback",
            "reward",
            "Bundle awarded",
            "2026-08-20T12:00:00+00:00",
            correlation_id="bundle:30",
        )],
        applied_reward_event_keys=event_keys,
        processed_answer_keys=list(event_keys),
        answer_lineage_bindings={str(original_revlog_id): lineage},
        pending_reanswer_lineages={lineage: reanswer_floor},
        recent_reward_receipts=[
            RewardReceipt(
                "event:bundle",
                "coins",
                "achievement",
                "streak_30",
                "2026-08-20",
                "bundle:30",
                "2026-08-20T12:00:00+00:00",
                amount=100,
            ),
            RewardReceipt(
                "event:bundle",
                "inventory_item",
                "achievement",
                "streak_30",
                "2026-08-20",
                "bundle:30",
                "2026-08-20T12:00:00+00:00",
                amount=1,
                item_id="growth_charge_small",
            ),
        ],
        garden_find_outcomes=outcomes,
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.applied_reward_event_keys[:len(event_keys)] == event_keys
    assert restored.applied_reward_event_keys[-1] == "event:bundle"
    assert restored.processed_answer_keys[:len(event_keys)] == event_keys
    assert {
        outcome.answer_key for outcome in outcomes.values()
    }.issubset(restored.processed_answer_keys)
    assert len(restored.garden_find_outcomes) == len(outcomes)
    assert {
        "standard:answer:0", "environment:answer:0"
    }.issubset(restored.garden_find_outcomes)
    assert [receipt.reward_type for receipt in restored.recent_reward_receipts] == [
        "coins",
        "inventory_item",
    ]
    assert restored.currency_transactions[0].transaction_type == "credit"
    assert restored.currency_transactions[0].source_id == "streak_30"
    assert restored.pending_feedback[0].correlation_id == "bundle:30"

    storage = object.__new__(GardenStorage)
    storage.user_files_dir = tmp_path
    storage.data_path = tmp_path / "garden_state.json"
    storage.database_path = tmp_path / "garden_state.sqlite3"
    storage._reward_ledger = None
    storage._ledger_revision = 0
    storage._install_reward_database(restored)

    assert storage.reward_applied("event:bundle")
    assert storage.answer_consumed("answer:0")
    assert storage.garden_find_outcome("answer:0", "environment") is not None
    assert storage.pending_reanswer_lineages() == {lineage: reanswer_floor}
    assert storage.reanswer_floor_for_lineage(lineage) == reanswer_floor
    snapshot = storage._reward_ledger.load_state_snapshot()
    assert snapshot is not None
    assert not {
        "applied_reward_event_keys",
        "processed_answer_keys",
        "answer_lineage_bindings",
        "pending_reanswer_lineages",
        "garden_find_outcomes",
    }.intersection(snapshot.payload)

    storage._reward_ledger.close()
    reopened = object.__new__(GardenStorage)
    reopened.user_files_dir = tmp_path
    reopened.database_path = storage.database_path
    reopened._reward_ledger = None
    reopened._ledger_revision = 0
    reloaded_state = reopened._load_authoritative_state()
    reopened.state = reloaded_state
    assert reloaded_state.currency_balance == 10
    assert reopened.reward_applied("event:bundle")
    assert reopened.answer_consumed("answer:0")
    assert reloaded_state.pending_reanswer_lineages == {
        lineage: reanswer_floor
    }
    reopened.clear_reanswer_hint(lineage)
    reopened.save()
    reopened._reward_ledger.close()

    cleared = object.__new__(GardenStorage)
    cleared.user_files_dir = tmp_path
    cleared.database_path = storage.database_path
    cleared._reward_ledger = None
    cleared._ledger_revision = 0
    cleared_state = cleared._load_authoritative_state()
    assert cleared_state.pending_reanswer_lineages == {}
    cleared._reward_ledger.close()


def test_oversized_sync_receipts_compact_without_losing_atomic_totals() -> None:
    receipts = [
        RewardReceipt(
            f"garden_find:answer-{index}:standard",
            "coins",
            "garden_find",
            "find_coin_sprout",
            "2026-08-20",
            "sync:large",
            f"2026-08-20T12:{index % 60:02d}:00+00:00",
            amount=2,
            title="Coin Sprout",
        )
        for index in range(MAX_REWARD_RECEIPTS + 10)
    ]

    bounded = bounded_reward_receipts(receipts)

    assert len(bounded) == MAX_REWARD_RECEIPTS
    assert sum(receipt.amount for receipt in bounded) == len(receipts) * 2
    assert bounded[-1].event_key == receipts[-1].event_key
    assert {receipt.correlation_id for receipt in bounded} == {"sync:large"}


class _HistoryDb:
    def __init__(self, rows: list[tuple[int, ...]]) -> None:
        self.rows = rows

    def scalar(self, query: str, *args: int) -> int:
        assert "type in (0, 1, 2, 3)" in query
        return max((row[0] for row in self.rows), default=0)

    def all(self, query: str, *args: int) -> list[tuple[int, ...]]:
        assert "type in (0, 1, 2, 3)" in query
        lower, high_water, limit = args
        return [
            row for row in self.rows
            if lower < row[0] <= high_water and row[7] in {0, 1, 2, 3}
        ][:limit]


def test_full_history_pages_original_anki_days_ordinals_and_fails_closed() -> None:
    before_cutoff = int(datetime(2026, 8, 20, 3, 30).timestamp() * 1000)
    first_after = int(datetime(2026, 8, 20, 5, 0).timestamp() * 1000)
    second_after = int(datetime(2026, 8, 20, 6, 0).timestamp() * 1000)
    next_cutoff = int(datetime(2026, 8, 21, 4, 0).timestamp() * 1000)
    rows = [
        (before_cutoff, 7, 1, 1, 0, 0, 500, 0),
        (first_after, 7, 3, 2, 1, 2500, 600, 1),
        (second_after, 7, 4, 3, 2, 2600, 700, 2),
    ]
    storage = object.__new__(GardenStorage)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=_HistoryDb(rows)))
    storage.current_scheduler_day_bounds_ms = lambda: (
        next_cutoff - 86_400_000,
        next_cutoff,
    )

    snapshot = storage.load_eligible_review_history(page_size=1)

    assert snapshot.high_water_revlog_id == second_after
    assert [entry.scheduler_day for entry in snapshot.entries] == [
        "2026-08-19",
        "2026-08-20",
        "2026-08-20",
    ]
    assert [entry.card_day_ordinal for entry in snapshot.entries] == [1, 1, 2]
    assert snapshot.entries[-1].stable_answer_key == "v1|2026-08-20|7|2"
    assert snapshot.answer_lineage_bindings[str(before_cutoff)] == (
        "v1|2026-08-19|7|1"
    )
    assert snapshot.entries[-1].review_type == 2
    assert snapshot.entries[-1].answer_ms == second_after
    assert snapshot.fingerprint

    with pytest.raises(RevlogReadError, match="safety bound"):
        storage.load_eligible_review_history(max_entries=2, page_size=1)


def test_answer_lineage_survives_sync_insertion_undo_and_day_remapping() -> None:
    original, bindings = assign_stable_answer_identities([
        (200, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ])

    synced, bindings = assign_stable_answer_identities([
        (100, 7, "2026-08-20"),
        (200, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ], bindings)
    undone, bindings = assign_stable_answer_identities([
        (100, 7, "2026-08-20"),
        (250, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ], bindings)
    remapped, _bindings = assign_stable_answer_identities([
        (300, 7, "2026-08-21"),
    ], bindings)
    combined, _bindings = assign_stable_answer_identities([
        (100, 7, "2026-08-20"),
        (250, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ], {
        "200": original[200],
        "300": original[300],
    })
    earlier_undone, _bindings = assign_stable_answer_identities([
        (150, 7, "2026-08-20"),
        (200, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ], {
        "100": "v1|2026-08-20|7|1",
        "200": "v1|2026-08-20|7|2",
    })
    hinted, _bindings = assign_stable_answer_identities([
        (210, 7, "2026-08-20"),
        (250, 7, "2026-08-20"),
        (300, 7, "2026-08-20"),
    ], {
        "200": original[200],
        "300": original[300],
    }, {
        original[200]: 230,
    })

    assert synced[200] == original[200]
    assert synced[300] == original[300]
    assert synced[100] not in set(original.values())
    assert undone[250] == original[200]
    assert remapped[300] == original[300]
    assert combined[250] == original[200]
    assert combined[100] not in set(original.values())
    assert earlier_undone[300] == "v1|2026-08-20|7|1"
    assert earlier_undone[150] not in {
        "v1|2026-08-20|7|1",
        "v1|2026-08-20|7|2",
    }
    assert hinted[250] == original[200]
    assert hinted[210] not in set(original.values())
