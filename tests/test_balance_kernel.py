from __future__ import annotations

from hashlib import sha256

import pytest

from ankigarden import balance_catalog

from scripts.balance_analysis.catalog import canonical_json_bytes, load_catalog_facts
from scripts.balance_analysis.kernel import (
    DayEvents,
    EnvironmentDiscoveryEvent,
    _apply_environment_effects,
    _apply_firefly_review_day,
    _apply_growth,
    _consume_inventory_growth,
    _enqueue_fertilizer_batch,
    _initial_state,
    _milestone_schedule,
    _summarize_metric,
    _transfer_consumable_effects,
    _validated_parity_evidence,
    _validated_release_validation_evidence,
    generate_event_stream,
    simulate_balance,
    simulate_scenario,
)
from scripts.balance_analysis.model import SimulationConfig, approved_scenarios
from scripts.balance_analysis.trace import (
    REQUIRED_PARITY_BEHAVIORS,
    REQUIRED_PARITY_STATE_FIELDS,
    TRACE_FIELDS,
)


def _config(seeds: int = 3, days: int = 30) -> SimulationConfig:
    return SimulationConfig(
        seeds=seeds,
        days=days,
        checkpoint_days=(7, days) if days != 7 else (7,),
    )


def test_report_parity_evidence_fails_closed_until_the_full_manifest_passes():
    assert _validated_parity_evidence(None)["status"] == "not_run"
    evidence = {
        "status": "pass",
        "production_engine_trace_equivalent": True,
        "scenario_trace_count": 66,
        "scenario_smoke_trace_count": 66,
        "annual_scenario_trace_count": 66,
        "randomized_trace_count": 32,
        "bounded_trace_count": 98,
        "trace_count": 173,
        "checkpoint_count": 194,
        "compared_fields": list(TRACE_FIELDS),
        "required_behaviors": list(REQUIRED_PARITY_BEHAVIORS),
        "covered_behaviors": list(REQUIRED_PARITY_BEHAVIORS),
        "missing_behaviors": [],
        "required_state_fields": list(REQUIRED_PARITY_STATE_FIELDS),
        "covered_state_fields": list(REQUIRED_PARITY_STATE_FIELDS),
        "missing_state_fields": [],
        "missing_trace_sets": [],
        "manifest_sha256": "a" * 64,
        "trace_pairs_sha256": "b" * 64,
        "state_pairs_sha256": "c" * 64,
    }
    assert _validated_parity_evidence(evidence) == evidence
    with pytest.raises(ValueError, match="invalid production parity evidence"):
        _validated_parity_evidence({**evidence, "randomized_trace_count": 31})


@pytest.mark.parametrize("release_config,scenarios", (
    (
        SimulationConfig(
            seeds=10_000,
            days=365,
            checkpoint_days=(365,),
        ),
        approved_scenarios()[:1],
    ),
    (
        SimulationConfig(seeds=1, days=1, checkpoint_days=(1,)),
        tuple(reversed(approved_scenarios())),
    ),
))
def test_release_sized_or_66_row_runs_require_the_canonical_matrix(
    release_config,
    scenarios,
):
    with pytest.raises(ValueError, match="exact ordered canonical 66"):
        simulate_balance(release_config, scenarios=scenarios)


def test_passed_external_release_gate_requires_auditable_evidence():
    with pytest.raises(ValueError, match="evidence_refs"):
        _validated_release_validation_evidence({
            "migration_tests": {"status": "pass"},
        })
    accepted = _validated_release_validation_evidence({
        "migration_tests": {
            "status": "pass",
            "evidence_refs": ["migration-test-run.json"],
            "evidence_sha256": "d" * 64,
        },
    })
    assert accepted["migration_tests"]["status"] == "pass"
    assert accepted["native_macos_smoke"]["status"] == "not_run"


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
    for row in serial["coin_concentration"]:
        gross = row["gross_coins_pooled"]
        source_totals = row["source_totals"]
        assert sum(source_totals.values()) == gross
        assert row["ledger_source_hhi_numerator"] == sum(
            amount * amount for amount in source_totals.values()
        )
        assert row["ledger_source_hhi_denominator"] == gross * gross
        assert row["gross_without_completion_share"] == pytest.approx(
            row["gross_without_completion_rewards"] / gross
            if gross else 0.0
        )
    assert any(
        row["metric_id"] == "coins.gross_without_completion_rewards"
        for row in serial["statistics"]
    )


def test_right_censored_timing_keeps_population_and_reacher_estimands_separate():
    summary = _summarize_metric(
        [10, 20, None, None, None],
        total_n=5,
        right_censored=True,
    )

    assert summary["p10"] == 10
    assert summary["p50"] is None
    assert summary["p90"] is None
    assert summary["mean"] is None
    assert summary["conditional_reacher_p50"] == 10
    assert summary["conditional_reacher_mean"] == 15
    assert summary["censored_n"] == 3


def test_exact_derived_totals_and_expected_find_values_are_frozen():
    report = simulate_balance(_config(seeds=1, days=7))
    growth = report["analysis"]["growth"]
    coins = report["analysis"]["coins"]
    finds = report["analysis"]["standard_finds"]

    assert growth["full_bloom_growth"] == 35_000
    assert growth["full_bloom_stage_coin_reward"] == 50
    assert growth["full_lifecycle_coin_reward"] == 120
    assert coins["pre_endgame_permanent_cost_total"] == 5_825
    assert coins["permanent_cost_by_category"]["mastery"] == 7_500
    assert coins["permanent_cost_total"] == 18_475
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
    concentration = report["coin_concentration"][0]
    for source_id, exact_total in concentration["source_totals"].items():
        statistic = next(
            row for row in report["statistics"]
            if row["scenario_id"] == concentration["scenario_id"]
            and row["checkpoint_day"] == concentration["checkpoint_day"]
            and row["metric_id"] == f"coins.source.{source_id}"
        )
        assert statistic["pooled_total"] == exact_total


def test_endgame_spending_preserves_mastery_while_landmarks_are_dormant():
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
    assert metric("growth.contributed_to_landmarks_units")["max"] == 0
    assert metric("legacy.level")["max"] == 0
    assert metric("landmarks.tiers_funded")["max"] >= metric(
        "landmarks.tiers_claimed"
    )["max"]
    assert metric("mastery.ranks_funded")["max"] >= metric(
        "mastery.ranks_claimed"
    )["max"]
    assert metric("mastery.bonsai.growth_funded_units")["max"] >= 0
    assert metric("mastery.bonsai.ranks_claimed")["max"] >= 0
    assert metric("mastery.bonsai.ranks_claimable")["max"] >= 0
    assert metric("coins.spent")["max"] > 0
    assert metric("landmarks.owned")["max"] + metric("mastery.owned")["max"] > 0
    assert metric("endgame.active_project_selected")["min"] == 1
    assert metric("endgame.active_project_unallocated_stored_units")["max"] == 0
    assert metric("endgame.active_project_no_unallocated_storage")["min"] == 1
    assert metric("endgame.finite_growth_remaining_units")["min"] > 0


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


def test_shared_scenery_and_post_collection_consumables_follow_production_routing():
    facts = load_catalog_facts()
    scenarios = {row.scenario_id: row for row in approved_scenarios()}

    full_garden = scenarios["headline:no_spend:all_plants_complete"]
    scenery = simulate_scenario(
        facts,
        full_garden,
        SimulationConfig(seeds=1, days=2, checkpoint_days=(2,)),
        0,
        events=(
            DayEvents(
                day=1,
                study=False,
                answers=0,
                environment_discoveries=(EnvironmentDiscoveryEvent(
                    "rainbow_horizon",
                    "rare",
                    "natural",
                    0,
                ),),
            ),
            DayEvents(day=2, study=True, answers=100),
        ),
    )
    assert scenery.checkpoints[2]["growth.opening_plant_units"] == 35_000_000
    # The seeded Botanical Collection activates its permanent +1 Growth after
    # the first answer; the following 99 answers also share that bonus.
    assert scenery.checkpoints[2]["growth.total_units"] == 176_100
    assert scenery.checkpoints[2][
        "environments.effect_growth_units"
    ] == 7_500

    endgame = scenarios["headline:optimal_coin:landmark_mastery"]
    preserved = simulate_scenario(
        facts,
        endgame,
        SimulationConfig(seeds=1, days=2, checkpoint_days=(2,)),
        0,
        events=(
            DayEvents(
                day=1,
                study=True,
                answers=1,
                inventory_items=("growth_charge_small",),
            ),
            DayEvents(day=2, study=True, answers=1),
        ),
    )
    metrics = preserved.checkpoints[2]
    assert metrics["consumables.growth_charge_small.units_earned"] == 1
    assert metrics["consumables.growth_charge_small.units_activated"] == 1
    assert metrics["consumables.growth_charge_small.units_remaining"] == 0
    assert metrics["consumables.growth_charge_small.growth_generated"] == 10_000

    bloom_state = _initial_state(facts, scenarios[
        "very_light:no_spend:baseline"
    ])
    bloom_state.plant_growth_units[0] = (
        facts.full_bloom_growth * 100 - 10_000
    )
    schedule = _milestone_schedule(facts, 1)
    _apply_growth(bloom_state, facts, 10_000, schedule)
    _apply_growth(bloom_state, facts, 10_000, schedule)
    assert bloom_state.inventory["growth_charge_small"] == 1
    assert bloom_state.consumable_units_earned["growth_charge_small"] == 1

    bloom_state.consumable_active_batches["fertilizer_quality"] = [
        [53, 0, 0]
    ]
    bloom_state.fertilizer_activation_order_by_plant[0] = [
        "fertilizer_quality"
    ]
    _transfer_consumable_effects(bloom_state, 0, 1)
    assert bloom_state.consumable_active_batches[
        "fertilizer_quality"
    ] == [[53, 0, 1]]
    assert bloom_state.fertilizer_activation_order_by_plant[1] == [
        "fertilizer_quality"
    ]
    bloom_state.fertilizer_activation_order_by_plant[1] = [
        "fertilizer_basic",
        "fertilizer_quality",
    ]
    _enqueue_fertilizer_batch(bloom_state, 1, "fertilizer_basic")
    assert bloom_state.fertilizer_activation_order_by_plant[1] == [
        "fertilizer_basic",
        "fertilizer_basic",
        "fertilizer_quality",
    ]

    capped_state = _initial_state(
        facts,
        scenarios["moderate:optimal_growth:baseline"],
    )
    capped_state.inventory["fertilizer_basic"] = 1
    capped_state.fertilizer_activation_order_by_plant[0] = [
        "fertilizer_quality",
    ] * 5
    capped_state.inventory["booster_potion"] = 1
    capped_state.consumable_active_batches["booster_potion"] = [
        [50, 0, 0] for _ in range(5)
    ]
    _consume_inventory_growth(
        capped_state,
        facts,
        scenarios["moderate:optimal_growth:baseline"],
        {row.item_id: row for row in facts.purchase_options},
        {row.consumable_id: row for row in facts.consumables},
        schedule,
        answers=100,
        complete=True,
    )
    assert capped_state.inventory["fertilizer_basic"] == 1
    assert capped_state.consumable_units_activated["fertilizer_basic"] == 0
    assert capped_state.inventory["booster_potion"] == 1
    assert capped_state.consumable_units_activated["booster_potion"] == 0


def test_repeated_seven_day_run_uses_recurring_streak_source_after_gap():
    facts = load_catalog_facts()
    scenario = next(
        row for row in approved_scenarios()
        if row.scenario_id == "very_light:no_spend:baseline"
    )
    events = tuple(
        DayEvents(day=day, study=day != 8, answers=10 if day != 8 else 0)
        for day in range(1, 16)
    )
    result = simulate_scenario(
        facts,
        scenario,
        SimulationConfig(seeds=1, days=15, checkpoint_days=(15,)),
        0,
        events=events,
    )

    assert result.checkpoints[15]["coins.source.achievement"] >= 10
    assert result.checkpoints[15]["coins.source.seven_day_streak_cycle"] == 10


def test_firefly_instant_growth_targets_the_closest_checkpoint_plant():
    facts = load_catalog_facts()
    scenario = next(
        row for row in approved_scenarios()
        if row.scenario_id == "very_light:collection_first:baseline"
    )
    state = _initial_state(facts, scenario)
    state.species_owned = 3
    state.beds_owned = 3
    state.plant_species_ids = list(facts.species_ids[:3])
    state.plant_growth_units = [907_400, 66_620, 25_140]
    state.active_plant_index = 0
    state.active_garden_bonus_id = "firefly_lantern"
    schedule = _milestone_schedule(facts, 1)

    _apply_environment_effects(
        state,
        facts,
        scenario,
        SimulationConfig(seeds=1, days=1, checkpoint_days=(1,)),
        0,
        DayEvents(day=1, study=True, answers=10),
        complete=True,
        milestone_schedule=schedule,
    )

    assert state.plant_growth_units == [907_400, 66_620, 25_740]
    assert state.environment_effect_growth_units == 600

    # Production resolves Firefly after each fifth answer, so a normal Growth
    # crossing midway through the batch may change the closest plant.  The
    # accelerated day path must preserve that ordering rather than applying
    # both grants after aggregating all ten answers.
    state.plant_growth_units = [1_004_600, 75_340, 39_260]
    state.effect_counters[
        "instant_growth_every_5_plus_3_closest_checkpoint"
    ] = 0
    state.environment_effect_growth_units = 0
    _apply_firefly_review_day(
        state,
        facts,
        DayEvents(day=1, study=True, answers=10),
        {row.consumable_id: row for row in facts.consumables},
        schedule,
        rhythm_percent=0,
    )

    assert state.plant_growth_units == [1_014_600, 76_640, 40_560]
    assert state.environment_effect_growth_units == 600

    state.plant_growth_units = [1_988_300, 183_080, 128_100]
    state.active_scenery_id = "rainbow_horizon"
    state.effect_counters[
        "instant_growth_every_5_plus_3_closest_checkpoint"
    ] = 0
    state.environment_effect_growth_units = 0
    _apply_firefly_review_day(
        state,
        facts,
        DayEvents(
            day=1,
            study=True,
            answers=10,
            find_growth_units=10_000,
            find_growth_units_by_answer=((1, 10_000),),
        ),
        {row.consumable_id: row for row in facts.consumables},
        schedule,
        rhythm_percent=10,
    )

    assert state.plant_growth_units == [2_010_300, 184_880, 129_300]
    assert state.environment_effect_growth_units == 1_600


def test_halloween_gift_uses_the_production_reward_seed_and_anki_day():
    facts = load_catalog_facts()
    scenario = next(
        row for row in approved_scenarios()
        if row.scenario_id == "very_light:collection_first:incomplete_days"
    )
    config = SimulationConfig(
        seeds=1,
        days=337,
        checkpoint_days=(337,),
    )
    # Fixed production seed/day keep this outcome independent of catalog copy.
    event = DayEvents(
        day=337,
        study=True,
        answers=10,
        scheduler_day_id="2027-08-01",
        production_reward_seed=(
            "86d82db0f8d0e434f1cb9912e6bfcad71"
            "fd3de654a1361eb4bef3da46b1c7737"
        ),
    )
    state = _initial_state(facts, scenario)
    state.active_scenery_id = "halloween"

    _apply_environment_effects(
        state,
        facts,
        scenario,
        config,
        0,
        event,
        complete=True,
        milestone_schedule=_milestone_schedule(facts, 1),
    )

    assert state.inventory["growth_charge_standard"] == 1
    assert state.inventory["growth_charge_small"] == 0
