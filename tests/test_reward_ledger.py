from __future__ import annotations


import errno
import sqlite3

import pytest

from ankigarden.reward_ledger import (
    AnswerConsumptionRecord,
    AnswerLineageRecord,
    EconomyEventRecord,
    FinalizedDayRecord,
    FindOutcomeRecord,
    RevlogAliasRecord,
    RewardEventRecord,
    RewardLedger,
    RewardLedgerCheckpointError,
    RewardLedgerConflictError,
    RewardLedgerRevisionConflict,
    RewardLedgerSchemaError,
)


DAY = "2026-08-21"
OCCURRED_AT = "2026-08-21T15:30:00+00:00"


def _stage_answer(
    ledger: RewardLedger,
    *,
    answer_key: str,
    lineage_key: str,
    revlog_id: int,
    card_id: int,
    serial: int,
) -> None:
    ledger.stage_answer_lineage(AnswerLineageRecord(
        lineage_key,
        DAY,
        card_id,
        serial,
    ))
    ledger.stage_revlog_alias(RevlogAliasRecord(revlog_id, lineage_key))
    ledger.stage_answer_consumption(AnswerConsumptionRecord(
        answer_key,
        DAY,
        OCCURRED_AT,
        lineage_key,
        revlog_id,
    ))


def test_atomic_state_commit_round_trips_staged_authorities_and_reads(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "reward-ledger.sqlite3"
    ledger = RewardLedger(database)
    _stage_answer(
        ledger,
        answer_key="answer-one",
        lineage_key=f"v1|{DAY}|41|1",
        revlog_id=1_787_325_400_001,
        card_id=41,
        serial=1,
    )
    ledger.stage_find_outcome(FindOutcomeRecord(
        "answer-one",
        DAY,
        "standard",
        "standard-v1",
        "miss",
        OCCURRED_AT,
    ))
    ledger.stage_find_outcome(FindOutcomeRecord(
        "answer-one",
        DAY,
        "environment",
        "environment-v1",
        "hit",
        OCCURRED_AT,
        "fireflies",
        {"display_name": "Firefly Evening", "amount": 1},
    ))
    reanswer_lineage = f"v1|{DAY}|41|1"
    reanswer_floor = 1_787_325_400_100
    ledger.stage_reanswer_hint(reanswer_lineage, reanswer_floor)
    _stage_answer(
        ledger,
        answer_key="answer-two",
        lineage_key=f"v1|{DAY}|42|1",
        revlog_id=1_787_325_400_002,
        card_id=42,
        serial=1,
    )
    ledger.stage_find_outcome(FindOutcomeRecord(
        "answer-two",
        DAY,
        "standard",
        "standard-v1",
        "hit",
        OCCURRED_AT,
        "find_coin_sprout",
        {"reward_type": "coins", "amount": 2},
    ))
    ledger.stage_reward_event(RewardEventRecord(
        "garden_find:answer-two:standard",
        "garden_find",
        DAY,
        OCCURRED_AT,
    ))
    ledger.stage_finalized_day(FinalizedDayRecord(DAY, "history:2:2:0"))

    # Every query sees the uncommitted unit of work so later answers in a sync
    # batch cannot reroll or overrun the daily cap.
    assert ledger.reward_applied("garden_find:answer-two:standard")
    assert ledger.answer_consumed("answer-one")
    assert ledger.bindings_for_revlogs([1_787_325_400_001]) == {
        1_787_325_400_001: f"v1|{DAY}|41|1"
    }
    assert ledger.bindings_for_cards([42]) == {
        1_787_325_400_002: f"v1|{DAY}|42|1"
    }
    assert ledger.find_outcome("answer-one", "standard").status == "miss"
    assert ledger.reanswer_hints() == {reanswer_lineage: reanswer_floor}
    assert ledger.reanswer_floor_for_lineage(reanswer_lineage) == reanswer_floor
    assert ledger.find_counts(DAY).reward_counts == {"find_coin_sprout": 1}
    assert [item.reward_id for item in ledger.recent_hit_outcomes()] == [
        "find_coin_sprout",
        "fireflies",
    ]
    assert ledger.finalized_day_fingerprint(DAY) == "history:2:2:0"

    committed = ledger.commit_state(
        {"version": 22, "currency_balance": 2},
        schema_version=22,
        expected_revision=0,
    )
    assert committed.revision == 1
    assert ledger.staged_write_count == 0
    ledger.close()

    reopened = RewardLedger(database)
    snapshot = reopened.load_state_snapshot()
    assert snapshot is not None
    assert snapshot.revision == 1
    assert snapshot.schema_version == 22
    assert snapshot.payload == {"currency_balance": 2, "version": 22}
    assert reopened.aliases_for_lineage(f"v1|{DAY}|41|1") == (
        1_787_325_400_001,
    )
    assert reopened.all_revlog_bindings()[1_787_325_400_002] == (
        f"v1|{DAY}|42|1"
    )
    assert reopened.reanswer_hints() == {reanswer_lineage: reanswer_floor}
    hint_checkpoint = reopened.checkpoint()
    reopened.stage_clear_reanswer_hint(reanswer_lineage)
    assert reopened.reanswer_hints() == {}
    reopened.rollback(hint_checkpoint)
    assert reopened.reanswer_hints() == {reanswer_lineage: reanswer_floor}
    assert reopened.consumed_answer_keys([
        "answer-one", "answer-two", "not-consumed"
    ]) == {"answer-one", "answer-two"}
    assert reopened.find_outcome("answer-one", "environment").hit_payload == {
        "amount": 1,
        "display_name": "Firefly Evening",
    }
    assert reopened.find_counts(DAY).total_hits == 1
    assert reopened.find_counts(DAY, pool_id="environment").total_hits == 1
    assert [item.reward_id for item in reopened.recent_hit_outcomes(limit=2)] == [
        "find_coin_sprout",
        "fireflies",
    ]
    reopened.integrity_check()
    monkeypatch.setattr(
        "ankigarden.reward_ledger.os.link",
        lambda _source, _target: (_ for _ in ()).throw(
            OSError(errno.EOPNOTSUPP, "hard links unavailable")
        ),
    )
    backup = reopened.backup_to(tmp_path / "backup.sqlite3")
    reopened.close()

    backed_up = RewardLedger(backup)
    assert backed_up.load_state_snapshot().payload == {
        "currency_balance": 2,
        "version": 22,
    }
    assert backed_up.answer_consumed("answer-two")
    assert backed_up.reanswer_hints() == {reanswer_lineage: reanswer_floor}
    backed_up.close()


def test_checkpoint_rollback_discards_only_later_staged_rows(tmp_path) -> None:
    ledger = RewardLedger(tmp_path / "reward-ledger.sqlite3")
    root = ledger.checkpoint()
    foreign = RewardLedger(tmp_path / "foreign-ledger.sqlite3")
    with pytest.raises(RewardLedgerCheckpointError):
        ledger.rollback(foreign.checkpoint())
    foreign.close()

    ledger.stage_reward_event(RewardEventRecord("discarded-branch"))
    stale_branch = ledger.checkpoint()
    ledger.rollback(root)
    ledger.stage_reward_event(RewardEventRecord("replacement-branch"))
    with pytest.raises(RewardLedgerCheckpointError):
        ledger.rollback(stale_branch)
    ledger.rollback(root)

    ledger.stage_answer_lineage(AnswerLineageRecord(
        f"v1|{DAY}|50|1", DAY, 50, 1
    ))
    retained = ledger.checkpoint()
    ledger.stage_reanswer_hint(
        f"v1|{DAY}|50|1", 1_787_325_500_100
    )
    ledger.stage_revlog_alias(RevlogAliasRecord(
        1_787_325_500_001, f"v1|{DAY}|50|1"
    ))
    ledger.stage_answer_consumption(AnswerConsumptionRecord(
        "rolled-back-answer",
        DAY,
        OCCURRED_AT,
        f"v1|{DAY}|50|1",
        1_787_325_500_001,
    ))
    ledger.stage_reward_event(RewardEventRecord("rolled-back-reward"))

    ledger.rollback(retained)

    assert ledger.lineage_record(f"v1|{DAY}|50|1") is not None
    assert ledger.reanswer_hints() == {}
    assert ledger.binding_for_revlog(1_787_325_500_001) is None
    assert not ledger.answer_consumed("rolled-back-answer")
    assert not ledger.reward_applied("rolled-back-reward")
    assert ledger.staged_write_count == 1

    with pytest.raises(ValueError, match="unbounded ledger authorities"):
        ledger.commit_state(
            {"version": 22, "pending_reanswer_lineages": {}},
            schema_version=22,
            expected_revision=0,
        )
    assert ledger.staged_write_count == 1
    ledger.commit_state(
        {"version": 22}, schema_version=22, expected_revision=0
    )
    with pytest.raises(RewardLedgerCheckpointError):
        ledger.rollback(root)
    assert ledger.lineage_record(f"v1|{DAY}|50|1") is not None
    ledger.close()


def test_database_uniqueness_conflict_rolls_back_state_and_keeps_staging(tmp_path) -> None:
    database = tmp_path / "reward-ledger.sqlite3"
    first = RewardLedger(database)
    second = RewardLedger(database)
    stale = RewardLedger(database)
    second_checkpoint = second.checkpoint()
    stale_checkpoint = stale.checkpoint()
    event = RewardEventRecord("same-event", "achievement", DAY, OCCURRED_AT)
    for ledger in (first, second):
        _stage_answer(
            ledger,
            answer_key="contended-answer",
            lineage_key=f"v1|{DAY}|60|1",
            revlog_id=1_787_325_600_001,
            card_id=60,
            serial=1,
        )
        ledger.stage_find_outcome(FindOutcomeRecord(
            "contended-answer",
            DAY,
            "standard",
            "standard-v1",
            "hit",
            OCCURRED_AT,
            "find_coin_sprout",
            {"amount": 2},
        ))
        ledger.stage_reward_event(event)
    stale.stage_reward_event(RewardEventRecord("disjoint-stale-event"))

    first.commit_state(
        {"owner": "first"}, schema_version=22, expected_revision=0
    )
    # Pending rows shadow their newly committed primary-key twins instead of
    # being double-counted while the stale unit of work awaits commit.
    assert second.find_counts(DAY).total_hits == 1
    assert len(second.recent_hit_outcomes()) == 1
    with pytest.raises(RewardLedgerConflictError):
        second.commit_state(
            {"owner": "second"}, schema_version=22, expected_revision=1
        )
    with pytest.raises(RewardLedgerRevisionConflict):
        stale.commit_state(
            {"owner": "stale"}, schema_version=22, expected_revision=0
        )

    # The conflicting event and the supplied replacement state were in the
    # same SQLite transaction, so neither part of the second commit landed.
    assert second.load_state_snapshot().payload == {"owner": "first"}
    assert second.has_staged_writes
    second.rollback(second_checkpoint)
    assert not second.has_staged_writes
    stale.rollback(stale_checkpoint)
    assert not stale.reward_applied("disjoint-stale-event")
    with pytest.raises(RewardLedgerConflictError):
        first.stage_reward_event(event)

    stale.close()
    second.close()
    first.close()


def test_failure_after_ledger_inserts_rolls_back_rows_and_state_for_retry(tmp_path) -> None:
    database = tmp_path / "reward-ledger.sqlite3"
    ledger = RewardLedger(database)
    ledger.commit_state(
        {"balance": 0}, schema_version=22, expected_revision=0
    )
    with sqlite3.connect(str(database)) as connection:
        connection.execute(
            "CREATE TRIGGER reject_state_update "
            "BEFORE UPDATE ON state_snapshot "
            "BEGIN SELECT RAISE(ABORT, 'injected state failure'); END"
        )

    _stage_answer(
        ledger,
        answer_key="retry-answer",
        lineage_key=f"v1|{DAY}|70|1",
        revlog_id=1_787_325_700_001,
        card_id=70,
        serial=1,
    )
    ledger.stage_reward_event(RewardEventRecord(
        "retry-reward", "daily_activity", DAY, OCCURRED_AT
    ))
    with pytest.raises(RewardLedgerConflictError):
        ledger.commit_state(
            {"balance": 2}, schema_version=22, expected_revision=1
        )

    # A separate authority reader cannot see any of the rows inserted before
    # the failing state update, while the original unit of work remains staged.
    probe = RewardLedger(database)
    assert probe.load_state_snapshot().payload == {"balance": 0}
    assert not probe.answer_consumed("retry-answer")
    assert not probe.reward_applied("retry-reward")
    probe.close()
    assert ledger.answer_consumed("retry-answer")
    assert ledger.reward_applied("retry-reward")

    with sqlite3.connect(str(database)) as connection:
        connection.execute("DROP TRIGGER reject_state_update")
    retried = ledger.commit_state(
        {"balance": 2}, schema_version=22, expected_revision=1
    )
    assert retried.revision == 2
    assert not ledger.has_staged_writes
    ledger.close()

    reopened = RewardLedger(database)
    assert reopened.load_state_snapshot().payload == {"balance": 2}
    assert reopened.answer_consumed("retry-answer")
    assert reopened.reward_applied("retry-reward")
    reopened.close()


def test_open_fails_closed_when_exact_identity_schema_is_incomplete(tmp_path) -> None:
    database = tmp_path / "reward-ledger.sqlite3"
    ledger = RewardLedger(database)
    ledger.close()
    with sqlite3.connect(str(database)) as connection:
        connection.execute("DROP INDEX find_outcome_day_idx")

    with pytest.raises(RewardLedgerSchemaError, match="indexes are incomplete"):
        RewardLedger(database)


def test_schema3_growth_flows_reconcile_generated_and_manual_units(tmp_path) -> None:
    ledger = RewardLedger(tmp_path / "growth-ledger.sqlite3")
    ledger.stage_economy_event(EconomyEventRecord(
        event_key="answer:one",
        event_kind="answer_growth",
        source_id="base_answer",
        growth_earned_units=1_000,
        growth_flow_kind="generated",
        growth_generated_units=1_000,
        growth_applied_to_plants_units=700,
        growth_routed_to_storage_units_lifetime=200,
        stored_growth_balance_delta_units=200,
        growth_contributed_to_landmarks_units=100,
        metric_deltas={
            "project_allocations": {"landmark:garden_landmark": 100}
        },
    ))
    ledger.stage_economy_event(EconomyEventRecord(
        event_key="project:one",
        event_kind="project_contribution",
        sink_id="landmark:garden_landmark",
        growth_flow_kind="manual_contribution",
        stored_growth_balance_delta_units=-150,
        growth_contributed_to_landmarks_units=150,
        metric_deltas={
            "project_allocations": {"landmark:garden_landmark": 150}
        },
    ))
    aggregates = ledger.lifetime_economy_aggregates()
    assert aggregates["growth_generated_units"] == 1_000
    assert aggregates["growth_applied_to_plants_units"] == 700
    assert aggregates["growth_routed_to_storage_units_lifetime"] == 200
    assert aggregates["growth_contributed_to_landmarks_units"] == 250

    with pytest.raises(ValueError, match="conserve"):
        ledger.stage_economy_event(EconomyEventRecord(
            event_key="broken",
            event_kind="answer_growth",
            source_id="base_answer",
            growth_flow_kind="generated",
            growth_generated_units=10,
            growth_applied_to_plants_units=9,
        ))
    ledger.rollback_all()
    ledger.close()


def test_item_acquisition_date_uses_first_committed_purchase_or_discovery(tmp_path):
    database = tmp_path / "acquisition.sqlite3"
    with RewardLedger(database) as ledger:
        ledger.stage_economy_event(EconomyEventRecord(
            "find:lantern", "environment_discovery", item_id="firefly_lantern",
            occurred_at=OCCURRED_AT, quantity=1,
        ))
        ledger.stage_economy_event(EconomyEventRecord(
            "buy:chime", "purchase", sink_id="garden_feature:wind_chime", item_id="wind_chime",
            occurred_at=OCCURRED_AT, coins_spent=100, quantity=1,
        ))
        ledger.stage_economy_event(EconomyEventRecord(
            "bonus:lantern", "answer_growth", item_id="firefly_lantern",
            occurred_at="2026-08-20T15:30:00+00:00",
        ))
        assert ledger.first_item_acquisition_at("firefly_lantern") == OCCURRED_AT
        assert ledger.first_item_acquisition_at("wind_chime") == OCCURRED_AT
        assert ledger.first_item_acquisition_at("prism_trellis") is None
        ledger.commit_state({}, schema_version=30, expected_revision=0)
        ledger.stage_economy_event(EconomyEventRecord(
            "failed:prism", "environment_discovery", item_id="prism_trellis",
            occurred_at=OCCURRED_AT, quantity=1,
        ))
        ledger.rollback_all()
        assert ledger.first_item_acquisition_at("prism_trellis") is None
    with RewardLedger(database) as reopened:
        assert reopened.first_item_acquisition_at("firefly_lantern") == OCCURRED_AT
        assert reopened.first_item_acquisition_at("wind_chime") == OCCURRED_AT


def test_activity_groups_exact_rewards_and_survives_rollback_and_restart(tmp_path):
    from ankigarden.activity import ActivityEvent, ActivitySession
    from ankigarden.reward_ledger import RewardLedger

    path = tmp_path / "activity.sqlite3"
    with RewardLedger(path) as ledger:
        day, time = "2026-09-06", "2026-09-06T20:24:00+00:00"
        session = "review-session:one"
        ledger.stage_activity_session(ActivitySession(session, started_at=time))
        records = (
            ActivityEvent("answer", session, day, time, "card_answer", card_answers=2),
            ActivityEvent("growth", session, day, time, "answer_growth", growth_units=2200),
            ActivityEvent("daily", session, day, time, "first_eligible_answer", coins=4),
            ActivityEvent("achievement:streak_7", session, day, time, "achievement", coins=10,
                          payload={"source_id": "streak_7"}),
            ActivityEvent("purchase", "purchase", day, time, "purchase", coins=-30),
            ActivityEvent("refund", "refund", day, time, "refund", coins=30, adjustment=True),
        )
        for record in records:
            ledger.stage_activity_event(record)
            ledger.stage_activity_event(record)
        checkpoint = ledger.checkpoint()
        ledger.stage_activity_event(ActivityEvent("failed", session, day, time, "welcome", coins=100))
        ledger.rollback(checkpoint)
        ledger.stage_activity_session(ActivitySession(session, ended_at=time, status="ended"))
        ledger.commit_state({}, schema_version=30, expected_revision=0)
    with RewardLedger(path) as ledger:
        entry, = ledger.activity_entries(filter_key="study")
        assert (entry.card_answers, entry.earned, entry.growth_units, entry.status) == (2, 14, 2200, "ended")
        assert entry.started_at == time
        assert sum(event.coins for event in ledger.activity_details(session)) == entry.earned
        assert ledger.activity_streak_rewards(day) == {"daily": 4, "streak": 10, "achievements": 0}
        assert [row.group_id for row in ledger.activity_entries(filter_key="earned")] == [session]
        assert [row.group_id for row in ledger.activity_entries(filter_key="spent")] == ["purchase"]
        assert ledger.activity_event("failed") is None
        # Replay and regrouping replace an event's contribution atomically;
        # they must not double-count the saved session after a restart.
        from dataclasses import replace
        ledger.stage_activity_event(records[1])
        ledger.stage_activity_event(replace(records[2], group_id="daily"))
        ledger.commit_state({}, schema_version=30, expected_revision=1)
    with RewardLedger(path) as ledger:
        entry, = ledger.activity_entries(filter_key="study")
        assert (entry.earned, entry.growth_units, entry.status) == (10, 2200, "ended")
        assert ledger.activity_day_totals(day)["coins"] == 14


def test_activity_pagination_retains_more_than_500_transactions(tmp_path):
    from ankigarden.activity import ActivityEvent
    from ankigarden.reward_ledger import RewardLedger

    with RewardLedger(tmp_path / "history.sqlite3") as ledger:
        for index in range(525):
            identity = f"reward:{index:04}"
            ledger.stage_activity_event(ActivityEvent(identity, identity, "2026-09-06",
                "2026-09-06T20:00:00+00:00", "standard_find", coins=1))
        ledger.commit_state({}, schema_version=30, expected_revision=0)
        seen, cursor = [], None
        while entries := ledger.activity_entries(limit=20, before=cursor):
            seen.extend(entry.group_id for entry in entries)
            cursor = (entries[-1].sort_ms, entries[-1].group_id)
        assert len(seen) == len(set(seen)) == 525
