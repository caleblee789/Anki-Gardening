from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.balance_analysis.artifacts import (
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
    }
    for key, expected in expected_headers.items():
        with second[key].open(newline="", encoding="utf-8") as stream:
            assert tuple(next(csv.reader(stream))) == expected


def test_run_id_ignores_unrelated_dirty_paths():
    report = simulate_profiles(seeds=1, days=7)
    first = finalize_report(report, repository_root=REPOSITORY_ROOT)
    second = finalize_report(report, repository_root=REPOSITORY_ROOT)
    assert first["run"]["run_id"] == second["run"]["run_id"]
    assert set(first["run"]["dirty_paths"]) <= set(first["run"]["source_files"])
