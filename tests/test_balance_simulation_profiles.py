"""Compatibility coverage for the public 2.2 economy simulation wrapper.

Detailed cadence, consumable, environment, and progression behavior belongs to
the focused catalog-ledger and kernel tests. This keeps the legacy wrapper
test from reasserting the retired 2.1 profile-report shape while ensuring it
still yields the canonical 2.2 scenario matrix and reconciliation assertions.
"""

from scripts.simulate_balance_profiles import simulate_profiles


def test_simulation_wrapper_emits_the_canonical_2_2_matrix():
    report = simulate_profiles(seeds=1, days=7)
    matrix = report["scenario_matrix"]

    assert report["run"]["report_schema_version"] == 2
    assert report["run"]["days"] == 7
    assert matrix["canonical_scenario_count"] == 66
    assert len(matrix["canonical_scenario_ids"]) == 66
    assert len(matrix["scenarios"]) == 66
    assert len(matrix["cohorts"]) == 6
    assert all(row["status"] == "pass" for row in report["assertions"])
