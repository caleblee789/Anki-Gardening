from __future__ import annotations

import pytest

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
    all_plants = _stat(
        short_report,
        "headline:no_spend:all_plants_complete",
        "growth.stored_units",
    )

    assert baseline["mean"] == 30
    assert incomplete["mean"] == 24
    assert all_environments["min"] == all_environments["max"] == 6
    assert all_plants["min"] > 0


def test_find_caps_and_guarantee_hold_for_every_scenario(short_report):
    guarantee_rows = [
        row for row in short_report["statistics"]
        if row["metric_id"] == "finds.maximum_attempted_gap"
    ]
    assert guarantee_rows
    assert all(row["max"] <= 75 for row in guarantee_rows)
