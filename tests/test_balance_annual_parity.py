from __future__ import annotations

import pytest

from scripts.balance_analysis.annual_parity import (
    generate_primitive_annual_trace,
    run_annual_parity,
)
from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.model import (
    SimulationConfig,
    approved_scenarios,
)


def _scenario(scenario_id: str):
    return next(
        row for row in approved_scenarios()
        if row.scenario_id == scenario_id
    )


def test_annual_trace_uses_production_find_resolvers_for_primitive_answers():
    facts = load_catalog_facts()
    scenario = _scenario("power:no_spend:baseline")
    config = SimulationConfig(seeds=1, days=1, checkpoint_days=(1,))

    trace = generate_primitive_annual_trace(facts, scenario, config, 0)
    event = trace.days[0].kernel_event

    assert len(trace.days[0].answer_payloads) == 400
    assert event.standard_finds > 0
    assert event.find_coins or event.find_growth_units or event.inventory_items
    assert trace.reward_seed == generate_primitive_annual_trace(
        facts, scenario, config, 0
    ).reward_seed

    evidence = run_annual_parity(scenarios=(scenario,), days=1)
    assert evidence["status"] == "pass"
    assert evidence["annual_scenario_trace_count"] == 1
    assert evidence["checkpoint_count"] == 1
    assert evidence["eligible_answer_count"] == 400


def test_very_light_no_spend_matches_production_at_all_365_daily_checkpoints():
    evidence = run_annual_parity(
        scenarios=(_scenario("very_light:no_spend:baseline"),),
        days=365,
    )

    assert evidence["status"] == "pass"
    assert evidence["scope"] == (
        "fast_in_memory_production_engine_daily_checkpoint_parity"
    )
    assert evidence["durable_sqlite_covered_elsewhere"] is True
    assert evidence["checkpoint_count"] == 365
    assert evidence["eligible_answer_count"] == 2_610
    assert len(evidence["manifest_sha256"]) == 64


@pytest.mark.parametrize(("scenario_id", "days"), (
    ("light:collection_first:baseline", 18),
    ("headline:no_spend:all_plants_complete", 19),
))
def test_independent_growth_lanes_match_production_milestones_and_overflow(
    scenario_id,
    days,
):
    evidence = run_annual_parity(
        scenarios=(_scenario(scenario_id),),
        days=days,
    )

    assert evidence["status"] == "pass"
    assert evidence["checkpoint_count"] == days


def test_fertilizer_tiers_queue_in_production_order():
    evidence = run_annual_parity(
        scenarios=(
            _scenario("very_light:consumable_heavy:baseline"),
        ),
        days=40,
    )

    assert evidence["status"] == "pass"
    assert evidence["checkpoint_count"] == 40
