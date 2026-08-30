from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.kernel import generate_event_stream, simulate_scenario
from scripts.balance_analysis.model import SimulationConfig, approved_scenarios
from scripts.balance_analysis.trace import (
    TRACE_FIELDS,
    TraceMismatch,
    assert_engine_trace_parity,
    canonical_trace_rows,
    trace_sha256,
)


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
    assert_engine_trace_parity(rows, deepcopy(rows))
    assert trace_sha256(rows) == trace_sha256(canonical_trace_rows(rows))


def test_engine_trace_comparison_reports_first_field_mismatch():
    rows = _trace()
    changed = [dict(row) for row in rows]
    changed[3]["coins_wallet"] += 1
    with pytest.raises(TraceMismatch, match="coins_wallet"):
        assert_engine_trace_parity(rows, changed)
