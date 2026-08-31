from __future__ import annotations

from pathlib import Path

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
from ankigarden.storage import DueObligationStatus
from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.kernel import DayEvents, generate_event_stream, simulate_scenario
from scripts.balance_analysis.model import (
    APPROVED_STRATEGIES,
    CohortSpec,
    ScenarioSpec,
    SimulationConfig,
    approved_scenarios,
)
from scripts.balance_analysis.trace import (
    GardenGameEngineReplayAdapter,
    ProductionReplayEvent,
    TRACE_FIELDS,
    TraceMismatch,
    assert_engine_trace_parity,
    canonical_trace_rows,
    project_production_engine_trace_row,
    trace_sha256,
)
from scripts.run_balance_engine_parity import run_release_parity


def _trace():
    facts = load_catalog_facts()
    scenario = next(
        row for row in approved_scenarios()
        if row.scenario_id == "headline:no_spend:baseline"
    )
    config = SimulationConfig(seeds=1, days=7, checkpoint_days=(7,))
    events = generate_event_stream(facts, scenario, config, 0)
    return simulate_scenario(
        facts,
        scenario,
        config,
        0,
        events=events,
        capture_trace=True,
    ).trace_rows


def test_engine_trace_contract_is_exact_and_self_consistent():
    rows = _trace()
    assert len(rows) == 7
    assert tuple(rows[0]) == TRACE_FIELDS
    assert_engine_trace_parity(rows, canonical_trace_rows(rows))
    assert trace_sha256(rows) == trace_sha256(canonical_trace_rows(rows))


def test_engine_trace_comparison_reports_first_field_mismatch():
    rows = _trace()
    changed = [dict(row) for row in rows]
    changed[3]["coins_wallet"] += 1
    with pytest.raises(TraceMismatch, match="coins_wallet"):
        assert_engine_trace_parity(rows, changed)


class _ParityConfig:
    def value(self, key, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys, default=None):
        node = DEFAULT_CONFIG
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _ParityStorage:
    def __init__(self):
        self.day = "2026-08-30"
        self.now_ms = 1_788_100_000_000
        self.day_start_ms = self.now_ms - 10_000
        plant = Plant("p1", "bonsai", "Moss", 0)
        self.state = GardenState(
            plants=[plant],
            active_plant_id="p1",
            starter_selection_complete=True,
            garden_setup_version=1,
            unlocked_species=["bonsai"],
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.now_ms - 1_000)
            ],
            reward_seed="parity-seed",
            reward_state_initialized=True,
            reward_activation_ms=self.day_start_ms,
            progression_activation_ms=self.day_start_ms,
            garden_find_activation_ms=9_000_000_000_000,
        )
        self.addon_dir = Path("ankigarden")
        self.assets_root = self.addon_dir / "assets"
        self.eligible_days = []
        self.completion_days = set()

    def save(self):
        return None

    def current_scheduler_day(self):
        return self.day

    def current_day_start_ms(self):
        return self.day_start_ms

    def current_time_ms(self):
        return self.now_ms

    def due_obligations(self):
        return DueObligationStatus()

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _value):
        return None

    def eligible_study_days_before(self, day, *, limit=7):
        return tuple(
            value for value in self.eligible_days
            if value < str(day)
        )[-max(0, int(limit)):]

    def verified_today_cards_completion_days_before(self, day):
        return {
            value for value in self.completion_days
            if value < str(day)
        }

    def record_replay_day(self, day, *, complete, studied):
        if studied and day not in self.eligible_days:
            self.eligible_days.append(day)
            self.eligible_days.sort()
        if complete:
            self.completion_days.add(day)


def _production_engine():
    return GardenGameEngine(_ParityConfig(), _ParityStorage())


@pytest.mark.parametrize("ease", [1, 2, 3, 4])
def test_real_garden_game_engine_matches_one_answer_kernel_trace(ease):
    facts = load_catalog_facts()
    scenario = ScenarioSpec(
        "parity:no_spend:baseline",
        CohortSpec("parity", 1, 7, 0),
        APPROVED_STRATEGIES[0],
    )
    config = SimulationConfig(seeds=1, days=1, checkpoint_days=(1,))
    kernel_rows = simulate_scenario(
        facts,
        scenario,
        config,
        0,
        events=(DayEvents(day=1, study=True, answers=1),),
        capture_trace=True,
    ).trace_rows
    event = ProductionReplayEvent(
        event_identity="day:1",
        event_type="answer",
        payload={
            "queue": 2,
            "ease": ease,
            "lapse_count": int(ease == 1),
            "revlog_id": 1_788_100_000_001,
            "answered_at_ms": 1_788_100_000_001,
            "card_id": 1,
            "answer_identity": "parity-answer-1",
            "scheduler_day": "2026-08-30",
            "first_answer_of_day": True,
            "day_answer_number": 1,
            "history_counted": True,
            "trace_day": 1,
            "trace_study_run": 1,
        },
    )
    production = GardenGameEngineReplayAdapter(
        _production_engine,
        project_production_engine_trace_row,
    ).replay((event,))
    assert production.committed_event_identities == ("day:1",)
    assert_engine_trace_parity(kernel_rows, production.rows)


def test_complete_release_manifest_matches_the_real_engine():
    evidence = run_release_parity()
    assert evidence["status"] == "pass"
    assert evidence["production_engine_trace_equivalent"] is True
    assert evidence["release_qualified"] is True
    assert evidence["scenario_trace_count"] == 66
    assert evidence["scenario_smoke_trace_count"] == 66
    assert evidence["annual_scenario_trace_count"] == 66
    assert evidence["randomized_trace_count"] == 32
    assert evidence["expected_scenario_smoke_trace_count"] == 66
    assert evidence["expected_annual_scenario_trace_count"] == 66
    assert evidence["expected_randomized_trace_count"] == 32
    assert evidence["bounded_trace_count"] == 98
    assert evidence["annual_checkpoint_count"] == 66 * 365
    assert evidence["focused_checkpoint_count"] == 27
    assert evidence["checkpoint_count"] >= 66 * 365 + 27 + 98
    assert evidence["annual_identity_set_exact"] is True
    assert evidence["bounded_identity_set_exact"] is True
    assert len(evidence["scenario_ids"]) == 66
    assert evidence["scenario_ids"] == evidence["expected_scenario_ids"]
    assert len(evidence["randomized_case_ids"]) == 32
    assert len(set(evidence["randomized_case_ids"])) == 32
    assert len(evidence["manifest_sha256"]) == 64
    assert len(evidence["trace_pairs_sha256"]) == 64
    assert len(evidence["state_pairs_sha256"]) == 64
    assert evidence["covered_behaviors"] == evidence["required_behaviors"]
    assert evidence["missing_behaviors"] == []
    assert evidence["covered_state_fields"] == evidence[
        "required_state_fields"
    ]
    assert evidence["missing_state_fields"] == []
    assert evidence["missing_trace_sets"] == []

    annual = evidence["annual_parity"]
    assert annual["status"] == "pass"
    assert annual["annual_scenario_trace_count"] == 66
    assert annual["checkpoint_count"] == 66 * 365
    assert annual["scenario_ids"] == evidence["scenario_ids"]
    assert "environment_ownership" in annual["covered_state_fields"]

    focused = evidence["focused_kernel_equivalence"]
    assert focused["status"] == "pass"
    assert focused["storage_adapter"] == "GardenStorage+RewardLedger(SQLite)"
    assert focused["case_count"] == 9
    assert focused["checkpoint_count"] == 27
    assert focused["state_schema_version"] == 27
    assert focused["ledger_schema_version"] == 3
    assert "booster_activation" in focused["covered_behaviors"]
    assert "garden_legacy_level" in focused["covered_behaviors"]
    assert "undo_and_reanswer_lineage" in focused["covered_behaviors"]
    assert "coin_ledger_entries" in focused["covered_state_fields"]
    assert "undo_lineage" in focused["covered_state_fields"]
    assert len(focused["state_pairs_sha256"]) == 64
    assert len(focused["trace_manifest_sha256"]) == 64

    durable = evidence["durable_persistence"]
    assert durable["status"] == "pass"
    assert durable["storage_adapter"] == "GardenStorage+RewardLedger(SQLite)"
    assert durable["state_schema_version"] == 27
    assert durable["ledger_schema_version"] == 3
    assert durable["kernel_equivalence_claimed"] is False
    assert durable["pre_bloom_completion_counters_preserved"] is True
    assert len(durable["checkpoint_sha256"]) == 64
    assert len(durable["trace_manifest_sha256"]) == 64
    assert "duplicate_sync_delivery" in durable["behaviors"]
    assert "failed_persistence_rollback" in durable["behaviors"]
    assert "undo_and_reanswer_lineage" in durable["behaviors"]
    assert "plant_exact_growth_units" in durable["nontrivial_state_fields"]
    assert "state_revision" in durable["nontrivial_state_fields"]
