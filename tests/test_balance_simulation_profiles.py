from __future__ import annotations

from pathlib import Path

import pytest

from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.kernel import simulate_balance
from scripts.balance_analysis.model import SimulationConfig
from scripts.balance_analysis.shards import (
    merge_balance_shards,
    write_balance_shard,
)
from scripts.simulate_balance_profiles import simulate_profiles


@pytest.fixture(scope="module")
def short_report():
    return simulate_profiles(seeds=2, days=30)


def _stat(report, scenario_id: str, metric_id: str, day: int = 30):
    return next(
        row for row in report["statistics"]
        if row["scenario_id"] == scenario_id
        and row["metric_id"] == metric_id
        and row["checkpoint_day"] == day
    )


def test_all_approved_scenarios_run_and_acceptance_assertions_pass(short_report):
    scenarios = short_report["scenario_matrix"]["scenarios"]
    assert len(scenarios) == 6 * 11
    assert {row["case_id"] for row in scenarios} == {
        "baseline",
        "incomplete_days",
        "missed_week",
        "all_environments",
        "all_plants_complete",
        "landmark_mastery",
    }
    assert all(row["status"] == "pass" for row in short_report["assertions"])


def test_no_spend_ledger_reconciles_and_growth_is_exact_integer_units(short_report):
    scenario_id = "headline:no_spend:baseline"
    gross = _stat(short_report, scenario_id, "coins.gross")
    spent = _stat(short_report, scenario_id, "coins.spent")
    ending = _stat(short_report, scenario_id, "coins.ending")
    growth = _stat(short_report, scenario_id, "growth.total_units")

    assert spent["min"] == spent["max"] == 0
    assert gross["mean"] == ending["mean"]
    assert growth["min"].is_integer()
    assert growth["max"].is_integer()


def test_edge_cases_are_modeled_as_separate_rows(short_report):
    baseline = _stat(
        short_report,
        "headline:collection_first:baseline",
        "days.studied",
    )
    incomplete = _stat(
        short_report,
        "headline:collection_first:incomplete_days",
        "days.completed",
    )
    all_environments = _stat(
        short_report,
        "headline:optimal_growth:all_environments",
        "environments.discovered",
    )
    ownership_suppression = _stat(
        short_report,
        "headline:optimal_growth:all_environments",
        "environments.rare_environment.ownership_suppression_rate",
    )
    all_plants = _stat(
        short_report,
        "headline:no_spend:all_plants_complete",
        "growth.stored_balance_units",
    )

    assert baseline["mean"] == 30
    assert incomplete["mean"] == 24
    assert all_environments["min"] == all_environments["max"] == 6
    assert ownership_suppression["min"] == ownership_suppression["max"] == 1
    assert all_plants["min"] > 0
    assert _stat(
        short_report,
        "headline:no_spend:all_plants_complete",
        "endgame.no_project_preserves_entire_reserve",
    )["min"] == 1
    assert _stat(
        short_report,
        "headline:no_spend:all_plants_complete",
        "endgame.no_project_preservation_delta_units",
    )["max"] == 0


def test_find_caps_and_guarantee_hold_for_every_scenario(short_report):
    guarantee_rows = [
        row for row in short_report["statistics"]
        if row["metric_id"] == "finds.maximum_attempted_gap"
    ]
    assert guarantee_rows
    assert all(row["max"] <= 75 for row in guarantee_rows)


def test_release_report_exposes_policy_accounting_and_item_level_evidence(short_report):
    baseline = {
        row["strategy_id"]: row["consumable_policy"]
        for row in short_report["scenario_matrix"]["scenarios"]
        if row["cohort_id"] == "headline" and row["case_id"] == "baseline"
    }
    assert baseline == {
        "no_spend": "never_use_earned",
        "collection_first": "use_immediately",
        "cosmetic_first": "save_for_100_card_session",
        "consumable_heavy": "consumable_heavy",
        "optimal_growth": "save_until_today_cards_completion",
        "optimal_coin": "purchase_none_use_earned",
    }
    metric_ids = {row["metric_id"] for row in short_report["statistics"]}
    assert "growth.stored_units" not in metric_ids
    consumable_fields = (
        "units_earned",
        "units_purchased",
        "units_activated",
        "units_consumed",
        "units_remaining",
        "cards_of_effect_remaining",
        "growth_generated",
        "coins_spent",
    )
    assert tuple(
        short_report["analysis"]["consumable_reporting"]["canonical_fields"]
    ) == consumable_fields
    consumable_ids = short_report["analysis"]["consumable_reporting"][
        "item_ids"
    ]
    assert all(
        f"consumables.{item_id}.{field}" in metric_ids
        for item_id in consumable_ids
        for field in consumable_fields
    )
    assert {
        "growth.generated_units",
        "growth.applied_to_plants_units",
        "growth.routed_to_storage_units_lifetime",
        "growth.stored_balance_units",
        "growth.contributed_to_landmarks_units",
        "growth.contributed_to_mastery_units",
        "growth.contributed_to_legacy_units",
        "landmarks.tiers_funded",
        "landmarks.tiers_claimed",
        "mastery.ranks_funded",
        "mastery.ranks_claimed",
        "catalog.finite_permanent_remaining_coins",
        "endgame.finite_coin_claim_demand_remaining",
        "endgame.finite_growth_remaining_units",
        "endgame.finite_targets_remaining",
        "endgame.active_project_no_unallocated_storage",
        "endgame.no_project_preserves_entire_reserve",
        "environments.any_tier_simultaneous_forced_user",
    } <= metric_ids
    environment_contract = short_report["analysis"][
        "environment_acquisition_reporting"
    ]
    assert environment_contract["timing_percentiles"] == ["p10", "p50", "p90"]
    for tier in short_report["analysis"]["environment_tiers"]:
        prefix = f"environments.{tier['tier_id']}."
        for field in (
            *environment_contract["calendar_day_fields"],
            *environment_contract["eligible_card_fields"],
            *environment_contract["route_fields"],
            "simultaneous_forced_acquisitions",
            environment_contract["simultaneous_forced_user_rate_field"],
            "ownership_blocked_card_checks",
            "ownership_blocked_completion_checks",
            "ownership_blocked_checks",
            "ownership_check_opportunities",
            environment_contract["ownership_suppression_rate_field"],
        ):
            assert prefix + field in metric_ids
        timing = next(
            row for row in short_report["statistics"]
            if row["metric_id"] == prefix + "first_discovery_day"
        )
        assert timing["censoring"] == "right_censored_at_checkpoint"
        assert timing["population_scope"].endswith("|all_paired_seeds")
        assert "conditional_reacher_p50" in timing
    concentration = next(
        row for row in short_report["coin_concentration"]
        if row["scenario_id"] == "headline:collection_first:baseline"
        and row["checkpoint_day"] == 30
    )
    assert sum(concentration["source_totals"].values()) == concentration[
        "gross_coins_pooled"
    ]
    assert concentration["behavioral_family_totals"][
        "todays_cards_completion"
    ] == concentration["source_totals"]["todays_cards"]


def test_seed_shards_merge_to_the_exact_monolithic_report(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    config = SimulationConfig(seeds=2, days=1, checkpoint_days=(1,))
    facts = load_catalog_facts()
    expected = simulate_balance(config, facts=facts)
    shard_paths = []
    for shard_index in range(2):
        shard_path = tmp_path / f"shard-{shard_index}.zip"
        write_balance_shard(
            config,
            shard_index=shard_index,
            shard_count=2,
            output_path=shard_path,
            repository_root=repository_root,
            facts=facts,
        )
        shard_paths.append(shard_path)

    actual = merge_balance_shards(
        config,
        shard_paths=shard_paths,
        shard_count=2,
        repository_root=repository_root,
    )

    assert actual == expected


def test_quick_cli_runs_custom_cohorts_and_writes_censored_results(tmp_path):
    import json
    from scripts.simulate_balance_profiles import main

    assert main(["--quick", "--seeds", "1", "--days", "2", "--workers", "1",
                 "--output-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "quick-audit.json").read_text())
    stress = next(row for row in report["scenarios"] if row["group"] == "stress")
    metrics = stress["samples"]["2"][0]
    assert metrics["answers.total"] == 2000  # Custom cohort must really execute.
    timing = next(row for row in stress["statistics"]
                  if row["metric_id"] == "plants.all_catalog_full_bloom_day")
    assert timing["p50"] is None
    assert stress["completed_by_day30"] is None
    assert stress["choices"]["2"][0]["decoration"]
    assert report["validation"]["full_release_matrix"] == "not_run"
    original = (tmp_path / "quick-audit.json").read_bytes()
    with pytest.raises(FileExistsError):
        from scripts.balance_analysis.quick import write_quick_artifacts
        write_quick_artifacts(report, tmp_path)
    assert (tmp_path / "quick-audit.json").read_bytes() == original


def test_quick_serial_and_parallel_runs_use_the_same_paired_population():
    from scripts.balance_analysis.quick import quick_cases, run_quick_audit

    cases = quick_cases(seeds=2, days=7)[6:8]
    serial = run_quick_audit(cases=cases)
    parallel = run_quick_audit(cases=cases, workers=2)
    for left, right in zip(serial["scenarios"], parallel["scenarios"]):
        assert left["samples"] == right["samples"]
        assert left["choices"] == right["choices"]
        assert left["statistics"] == right["statistics"]
