from __future__ import annotations

import sqlite3

import pytest

from ankigarden import reward_ledger as ledger_module
from ankigarden.reward_ledger import (
    AnswerConsumptionRecord,
    DailyEconomySnapshotRecord,
    EconomyEventRecord,
    IdempotencyRecord,
    LEDGER_SCHEMA_VERSION,
    RewardEventRecord,
    RewardLedger,
    RewardLedgerConflictError,
)


def test_schema1_upgrades_transactionally_and_preserves_existing_authority(
    tmp_path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    ledger = RewardLedger(database)
    ledger.stage_reward_event(RewardEventRecord("existing-event"))
    ledger.commit_state({"version": 25}, schema_version=25, expected_revision=0)
    ledger.close()

    with sqlite3.connect(str(database)) as connection:
        connection.execute("DROP TABLE daily_economy_snapshot")
        connection.execute("DROP TABLE economy_event")
        connection.execute("DROP TABLE idempotency_record")
        connection.execute("PRAGMA user_version = 1")

    upgraded = RewardLedger(database)
    assert upgraded.reward_applied("existing-event")
    assert upgraded.load_state_snapshot().payload == {"version": 25}
    with sqlite3.connect(str(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            LEDGER_SCHEMA_VERSION
        ) == 3
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "idempotency_record",
        "economy_event",
        "daily_economy_snapshot",
    }.issubset(tables)
    assert tuple(tmp_path.glob("ledger.ledger-schema-1.legacy-*.sqlite3"))
    upgraded.close()


def test_schema2_records_share_checkpoint_commit_and_replay_boundaries(tmp_path) -> None:
    ledger = RewardLedger(tmp_path / "ledger.sqlite3")
    root = ledger.checkpoint()
    idempotency = IdempotencyRecord(
        "mastery_purchase",
        "request-1",
        "fingerprint-1",
        {"status": "success", "rank": "bronze"},
        "2026-08-30T12:00:00+00:00",
        "2026-08-30",
    )
    event = EconomyEventRecord(
        "mastery:request-1",
        "mastery_purchase",
        sink_id="mastery",
        scheduler_day="2026-08-30",
        occurred_at="2026-08-30T12:00:00+00:00",
        coins_spent=50,
        growth_spent_on_mastery=2_500_000,
        item_id="bonsai:bronze",
        quantity=1,
        metric_deltas={"consumables_used": {"fertilizer_basic": 1}},
    )
    snapshot = DailyEconomySnapshotRecord(
        "2026-08-30",
        6,
        "wind_chime",
        "full_moon",
        "local_first_answer",
        "snapshot-1",
    )
    ledger.stage_idempotency_record(idempotency)
    ledger.stage_economy_event(event)
    ledger.stage_daily_economy_snapshot(snapshot)
    assert ledger.idempotency_record("mastery_purchase", "request-1") == idempotency
    assert ledger.economy_event(event.event_key) == event
    assert ledger.daily_economy_snapshot("2026-08-30") == snapshot

    ledger.rollback(root)
    assert ledger.idempotency_record("mastery_purchase", "request-1") is None
    assert ledger.economy_event(event.event_key) is None
    assert ledger.daily_economy_snapshot("2026-08-30") is None

    ledger.stage_idempotency_record(idempotency)
    ledger.stage_economy_event(event)
    ledger.stage_daily_economy_snapshot(snapshot)
    ledger.commit_state({"version": 27}, schema_version=27, expected_revision=0)
    ledger.close()

    reopened = RewardLedger(tmp_path / "ledger.sqlite3")
    assert reopened.idempotency_record("mastery_purchase", "request-1") == idempotency
    assert reopened.lifetime_economy_aggregates() == {
        "coins_earned_by_source": {},
        "coins_spent_by_sink": {"mastery": 50},
        "growth_earned_by_source": {},
        "growth_spent_on_landmarks": 0,
        "growth_spent_on_mastery": 2_500_000,
        "growth_generated_units": 0,
        "growth_applied_to_plants_units": 0,
        "growth_routed_to_storage_units_lifetime": 0,
        "growth_contributed_to_landmarks_units": 0,
        "growth_contributed_to_mastery_units": 0,
        "growth_contributed_to_legacy_units": 0,
        "growth_unallocated_overflow_units": 0,
        "history_complete": False,
        "authoritative_from_event_identity": "ledger:schema3:first-event",
        "finds_by_outcome": {},
        "environment_discoveries": {},
        "consumables_earned": {},
        "consumables_used": {"fertilizer_basic": 1},
        "plants_completed": 0,
        "today_cards_completions": 0,
    }
    reopened.stage_idempotency_record(idempotency)
    assert not reopened.has_staged_writes
    with pytest.raises(RewardLedgerConflictError):
        reopened.stage_idempotency_record(IdempotencyRecord(
            "mastery_purchase",
            "request-1",
            "different",
            {"status": "success"},
            "2026-08-30T12:00:00+00:00",
            "2026-08-30",
        ))
    reopened.close()


def test_prior_seven_eligible_days_and_verified_completions_are_queryable(
    tmp_path,
) -> None:
    ledger = RewardLedger(tmp_path / "ledger.sqlite3")
    for index, day in enumerate((
        "2026-08-20",
        "2026-08-22",
        "2026-08-23",
        "2026-08-24",
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
        "2026-08-28",
    )):
        ledger.stage_answer_consumption(AnswerConsumptionRecord(
            f"answer-{index}", day
        ))
    ledger.stage_reward_event(RewardEventRecord("all_due:2026-08-22"))
    ledger.stage_reward_event(RewardEventRecord(
        "completion:2026-08-27",
        "all_due",
        "2026-08-27",
    ))

    assert ledger.eligible_study_days_before("2026-08-30") == (
        "2026-08-28",
        "2026-08-27",
        "2026-08-26",
        "2026-08-25",
        "2026-08-24",
        "2026-08-23",
        "2026-08-22",
    )
    assert ledger.verified_today_cards_completion_days_before("2026-08-30") == {
        "2026-08-22",
        "2026-08-27",
    }
    ledger.commit_state({"version": 27}, schema_version=27, expected_revision=0)
    ledger.close()


def test_schema2_upgrade_preserves_rows_and_creates_verified_backup(tmp_path) -> None:
    database = tmp_path / "ledger.sqlite3"
    ledger = RewardLedger(database)
    ledger.stage_economy_event(EconomyEventRecord(
        "legacy-growth", "answer_growth", source_id="base",
        growth_earned_units=1_000,
    ))
    ledger.commit_state({"version": 26}, schema_version=26, expected_revision=0)
    ledger.close()
    with sqlite3.connect(str(database)) as connection:
        connection.execute("ALTER TABLE economy_event RENAME TO economy_event_v3")
        connection.execute(ledger_module._V2_ECONOMY_EVENT_TABLE_SQL)
        columns = (
            "event_key,event_kind,source_id,sink_id,scheduler_day,occurred_at,"
            "coins_earned,coins_spent,growth_earned_units,"
            "growth_spent_on_landmarks,growth_spent_on_mastery,item_id,quantity,"
            "metric_deltas_json"
        )
        connection.execute(
            f"INSERT INTO economy_event ({columns}) SELECT {columns} "
            "FROM economy_event_v3"
        )
        connection.execute("DROP TABLE economy_event_v3")
        connection.execute(
            "CREATE INDEX economy_event_day_idx "
            "ON economy_event(scheduler_day, event_kind)"
        )
        connection.execute("PRAGMA user_version = 2")

    upgraded = RewardLedger(database)
    assert upgraded.economy_event("legacy-growth").growth_flow_kind == (
        "legacy_unreconciled"
    )
    assert not upgraded.lifetime_economy_aggregates()["history_complete"]
    assert tuple(tmp_path.glob("ledger.ledger-schema-2.legacy-*.sqlite3"))
    upgraded.close()
