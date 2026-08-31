from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.balance_analysis.artifacts import (
    ANALYSIS_FIELDS,
    CATALOG_FIELDS,
    FINDING_FIELDS,
    MILESTONE_FIELDS,
    STATISTIC_FIELDS,
    canonical_json_text,
    finalize_report,
    write_artifacts,
)
from scripts.simulate_balance_profiles import REPOSITORY_ROOT, simulate_profiles


def test_frozen_json_and_csv_artifacts_are_canonical_and_reproducible(tmp_path: Path):
    report = simulate_profiles(seeds=1, days=7)
    frozen = finalize_report(report, repository_root=REPOSITORY_ROOT)
    first = write_artifacts(frozen, tmp_path)
    first_json = first["json"].read_bytes()
    second = write_artifacts(frozen, tmp_path)

    assert first_json == second["json"].read_bytes()
    assert first_json.decode("utf-8") == canonical_json_text(frozen)
    assert json.loads(first_json)["run"]["run_id"] == frozen["run"]["run_id"]
    assert frozen["run"]["generated_at_utc"] == "1970-01-01T00:00:00Z"

    expected_headers = {
        "catalog_csv": CATALOG_FIELDS,
        "statistics_csv": STATISTIC_FIELDS,
        "milestones_csv": MILESTONE_FIELDS,
        "findings_csv": FINDING_FIELDS,
        "analysis_csv": ANALYSIS_FIELDS,
    }
    for key, expected in expected_headers.items():
        with second[key].open(newline="", encoding="utf-8") as stream:
            assert tuple(next(csv.reader(stream))) == expected
    with second["analysis_csv"].open(newline="", encoding="utf-8") as stream:
        analysis_rows = list(csv.DictReader(stream))
    assert any(
        row["item_id"] == "rare_environment"
        and row["metric_id"].endswith("ownership_suppression_rate")
        for row in analysis_rows
    )
    release_rows = {
        row["metric_id"]: row for row in analysis_rows
        if row["record_type"] in {"release_gate", "release_readiness"}
    }
    assert release_rows["release_status.migration_tests"]["status"] == "not_run"
    assert release_rows["release_status.release_ready"]["status"] == "blocked"
    hhi_row = next(
        row for row in analysis_rows
        if row["metric_id"] == "coins.ledger_source_hhi"
    )
    hhi_exact = json.loads(hhi_row["details_json"])
    assert int(hhi_exact["denominator"]) > 0
    assert int(hhi_exact["numerator"]) >= 0
    concentration_metric_ids = {
        row["metric_id"] for row in analysis_rows
        if row["record_type"] == "coin_concentration"
    }
    assert {
        "coins.gross_without_completion_rewards",
        "coins.gross_without_completion_share",
    } <= concentration_metric_ids
    timing_row = next(
        row for row in analysis_rows
        if row["metric_id"].endswith("first_discovery_day")
        and row["statistic"] == "p10"
    )
    timing_details = json.loads(timing_row["details_json"])
    assert timing_details["population_percentile_method"] == (
        "nearest_rank_with_common_right_censoring"
    )


def test_run_id_ignores_unrelated_dirty_paths():
    report = simulate_profiles(seeds=1, days=7)
    first = finalize_report(report, repository_root=REPOSITORY_ROOT)
    second = finalize_report(report, repository_root=REPOSITORY_ROOT)
    assert first["run"]["run_id"] == second["run"]["run_id"]
    assert set(first["run"]["dirty_paths"]) <= set(first["run"]["source_files"])
    assert {
        "ankigarden/game.py",
        "scripts/run_balance_engine_parity.py",
        "scripts/balance_analysis/annual_parity.py",
        "scripts/balance_analysis/model.py",
    } <= set(first["run"]["source_files"])
