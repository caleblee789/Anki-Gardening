from __future__ import annotations

from hashlib import sha256

from ankigarden import balance_catalog

from scripts.balance_analysis.catalog import canonical_json_bytes, load_catalog_facts
from scripts.balance_analysis.kernel import generate_event_stream, simulate_balance
from scripts.balance_analysis.model import SimulationConfig, approved_scenarios


def _config(seeds: int = 3, days: int = 30) -> SimulationConfig:
    return SimulationConfig(
        seeds=seeds,
        days=days,
        checkpoint_days=(7, days) if days != 7 else (7,),
    )


def test_adapter_is_a_hash_exact_projection_of_the_runtime_catalog():
    facts = load_catalog_facts()
    snapshot = balance_catalog.catalog_snapshot()
    assert facts.snapshot == snapshot
    assert facts.snapshot_sha256 == sha256(canonical_json_bytes(snapshot)).hexdigest()
    assert [row.threshold_growth for row in facts.stages] == [
        0, 400, 2_000, 6_000, 15_000, 35_000
    ]
    assert [facts.standard_daily_cap(value) for value in (10, 199, 200, 399, 400)] == [
        3, 3, 4, 4, 5
    ]
    assert [
        (row.card_guarantee, row.completion_guarantee)
        for row in facts.environment_tiers
    ] == [(10_000, 60), (40_000, 180), (50_000, 365)]


def test_paired_event_streams_do_not_depend_on_purchase_strategy():
    facts = load_catalog_facts()
    rows = [
        row for row in approved_scenarios()
        if row.cohort.cohort_id == "headline"
        and row.case_id == "baseline"
    ]
    config = _config(seeds=1)
    first = generate_event_stream(facts, rows[0], config, 0)
    assert all(generate_event_stream(facts, row, config, 0) == first for row in rows[1:])


def test_same_seed_manifest_is_byte_deterministic_and_other_seed_stream_changes():
    facts = load_catalog_facts()
    scenarios = tuple(
        row for row in approved_scenarios()
        if row.cohort.cohort_id == "headline" and row.case_id == "baseline"
    )
    config = _config()
    first = simulate_balance(config, facts=facts, scenarios=scenarios)
    second = simulate_balance(config, facts=facts, scenarios=scenarios)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)

    stream_zero = generate_event_stream(facts, scenarios[0], config, 0)
    stream_one = generate_event_stream(facts, scenarios[0], config, 1)
    assert stream_zero != stream_one


def test_parallel_and_single_process_runs_are_identical():
    config = _config(seeds=2, days=7)
    serial = simulate_balance(config, workers=1)
    parallel = simulate_balance(config, workers=2)
    assert canonical_json_bytes(serial) == canonical_json_bytes(parallel)


def test_exact_derived_totals_and_expected_find_values_are_frozen():
    report = simulate_balance(_config(seeds=1, days=7))
    growth = report["analysis"]["growth"]
    coins = report["analysis"]["coins"]
    finds = report["analysis"]["standard_finds"]

    assert growth["full_bloom_growth"] == 35_000
    assert growth["full_bloom_stage_coin_reward"] == 50
    assert growth["full_lifecycle_coin_reward"] == 120
    assert coins["pre_endgame_permanent_cost_total"] == 7_125
    assert coins["permanent_cost_by_category"]["mastery"] == 7_500
    assert coins["permanent_cost_total"] == 19_775
    assert finds["expected_coins"] == {"numerator": 2_320, "denominator": 1_000}
    assert finds["expected_growth_equivalent"] == {
        "numerator": 44_000,
        "denominator": 1_000,
    }
    assert finds["schedule_adjusted_expected_gap_cards_fixed_6"] == {
        "scaled_integer": 48_062_269,
        "scale": 1_000_000,
    }
    assert finds["guarantee_hit_probability_fixed_6"] == {
        "scaled_integer": 196_621,
        "scale": 1_000_000,
    }
    assert report["analysis"]["optional_speed_sensitivity"][
        "separate_from_primary_cohorts"
    ] is True


def test_landmark_mastery_case_spends_both_growth_and_coins():
    facts = load_catalog_facts()
    scenario = next(
        row for row in approved_scenarios()
        if row.cohort.cohort_id == "power" and row.case_id == "landmark_mastery"
    )
    config = SimulationConfig(seeds=1, days=365, checkpoint_days=(365,))
    report = simulate_balance(config, facts=facts, scenarios=(scenario,))

    def metric(metric_id):
        return next(row for row in report["statistics"] if row["metric_id"] == metric_id)

    assert metric("growth.spent_units")["max"] > 0
    assert metric("coins.spent")["max"] > 0
    assert metric("landmarks.owned")["max"] + metric("mastery.owned")["max"] > 0


def test_mastery_catalog_expands_every_rank_for_every_species():
    facts = load_catalog_facts()
    mastery = [
        option for option in facts.purchase_options
        if option.category == "mastery"
    ]

    assert len(mastery) == 40
    assert sum(option.price_coins for option in mastery) == 7_500
    assert sum(option.growth_cost for option in mastery) == 3_750_000
    assert len({option.item_id for option in mastery}) == 40
    assert {
        option.item_id.split(":", 2)[2]
        for option in mastery
    } == {"bronze", "silver", "gold", "iridescent"}


def test_optimal_environment_strategies_receive_catalog_effects():
    facts = load_catalog_facts()
    wanted = {
        "headline:optimal_growth:baseline",
        "headline:optimal_coin:baseline",
    }
    scenarios = tuple(
        row for row in approved_scenarios()
        if row.scenario_id in wanted
    )
    report = simulate_balance(
        SimulationConfig(seeds=1, days=365, checkpoint_days=(365,)),
        facts=facts,
        scenarios=scenarios,
    )

    def metric(scenario_id, metric_id):
        return next(
            row for row in report["statistics"]
            if row["scenario_id"] == scenario_id and row["metric_id"] == metric_id
        )["max"]

    assert metric(
        "headline:optimal_growth:baseline",
        "environments.effect_growth_units",
    ) > 0
    assert metric(
        "headline:optimal_coin:baseline",
        "environments.effect_coins",
    ) > 0
