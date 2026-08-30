from __future__ import annotations

from scripts.balance_analysis.model import (
    APPROVED_COHORTS,
    APPROVED_EDGE_CASES,
    APPROVED_STRATEGIES,
    DEFAULT_SEED_COUNT,
    approved_scenarios,
    completes_study_day,
    is_study_day,
)
from scripts.simulate_balance_profiles import build_parser


def test_approved_cohort_pairs_are_exact_and_not_a_cross_product():
    assert tuple(
        (
            row.cohort_id,
            row.cards_per_study_day,
            row.study_days_per_week,
            row.completion_percent,
        )
        for row in APPROVED_COHORTS
    ) == (
        ("very_light", 10, 5, 80),
        ("light", 25, 6, 90),
        ("moderate", 50, 7, 90),
        ("headline", 100, 7, 100),
        ("heavy", 200, 7, 100),
        ("power", 400, 7, 100),
    )
    assert all(row.completion_percent != 50 for row in APPROVED_COHORTS)


def test_scenario_matrix_has_six_strategies_and_five_separate_edge_cases():
    rows = approved_scenarios()
    assert len(APPROVED_STRATEGIES) == 6
    assert len(APPROVED_EDGE_CASES) == 5
    assert len(rows) == 66
    assert all(
        sum(row.cohort == cohort for row in rows) == 11
        for cohort in APPROVED_COHORTS
    )
    assert len({row.scenario_id for row in rows}) == len(rows)


def test_completion_and_missed_week_calendars_are_deterministic():
    assert [completes_study_day(index, 80) for index in range(1, 6)] == [
        True, True, True, True, False
    ]
    assert [completes_study_day(index, 90) for index in range(1, 11)] == [
        True, True, True, True, True, True, True, True, True, False
    ]
    missed = next(
        row for row in approved_scenarios()
        if row.cohort.cohort_id == "headline" and row.case_id == "missed_week"
    )
    assert all(not is_study_day(day, missed) for day in range(183, 190))


def test_release_cli_defaults_to_ten_thousand_paired_seeds():
    args = build_parser().parse_args([])
    assert DEFAULT_SEED_COUNT == 10_000
    assert args.seeds == 10_000
    assert args.workers == 0
