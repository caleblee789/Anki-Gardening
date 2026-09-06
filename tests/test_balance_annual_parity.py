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


def test_collection_rotation_matches_public_placement_without_losing_full_blooms():
    from ankigarden.game import GardenGameEngine
    from ankigarden.models.state import Plant
    from scripts.balance_analysis.annual_parity import FastAnnualStorage, _AnnualConfig, _rotate_completed_species
    from scripts.balance_analysis.kernel import _initial_state, _rotate_completed_plants
    from scripts.balance_analysis.quick import quick_cases

    facts = load_catalog_facts()
    scenario = quick_cases()[0].scenario
    storage = FastAnnualStorage(facts, scenario, reward_seed="rotation")
    engine = GardenGameEngine(_AnnualConfig(), storage)
    full = facts.full_bloom_growth
    engine.state.plants = [Plant(f"p{i}", species, species, i if i < 5 else None,
                                growth_points=full if i < 5 else 0)
                           for i, species in enumerate(facts.species_ids[:7])]
    engine.state.unlocked_species = list(facts.species_ids[:7])
    engine.state.unlocked_slots = 5
    engine.state.active_plant_id = None
    state = _initial_state(facts, scenario)
    state.species_owned, state.beds_owned = 7, 5
    state.plant_species_ids = list(facts.species_ids[:7])
    state.plant_growth_units = [full * 100] * 5 + [0, 0]
    state.planted_order = list(range(5))
    state.active_plant_index = None
    _rotate_completed_plants(state, facts)
    _rotate_completed_species(engine)
    actual = {plant.species: plant.slot_index for plant in engine.state.plants if plant.planted}
    expected = {state.plant_species_ids[index]: slot for slot, index in enumerate(state.planted_order)}
    assert actual == expected
    assert len(engine.state.plants) == 7
    assert sum(plant.fully_grown for plant in engine.state.plants) == 5
    assert engine.active_plant().species == state.plant_species_ids[state.active_plant_index]
    assert sum(plant.growth_units for plant in engine.state.plants) == sum(state.plant_growth_units)


@pytest.mark.parametrize("profile,completed", [("fresh", False), ("established", False), ("fresh", True)])
def test_current_onboarding_and_garden_supplies_match_production(profile, completed):
    from dataclasses import replace
    from scripts.balance_analysis.opening import production_opening
    from scripts.balance_analysis.quick import quick_cases

    opening = production_opening(profile)
    assert opening.coins == (1836 if profile == "established" else 51)
    assert opening.starter_growth_units == 10_000
    if completed:
        opening = replace(opening, consumables=(("fertilizer_quality", 2), ("booster_potion", 2), ("growth_charge_grand", 1)))
    scenario = replace(quick_cases()[3].scenario, opening=opening,
                       all_plants_complete=completed, all_environments_owned=completed)
    evidence = run_annual_parity(scenarios=(scenario,), days=7)
    assert evidence["status"] == "pass"
