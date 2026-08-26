from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_full_catalog_layout import validate


pytestmark = pytest.mark.release_evidence


def test_full_catalog_layout_matrix_is_warning_free() -> None:
    report = validate()
    rows = json.loads(
        (Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json").read_text("utf-8")
    )["assets"]
    assert report["asset_count"] == sum(row.get("category") == "plants" for row in rows)
    assert report["theme_count"] == 1
    assert report["scenario_count"] == (
        report["asset_count"]
        * report["theme_count"]
        * report["size_count"]
        * report["count_profiles"]
        * report["mode_count"]
    )
    assert report["failure_count"] == 0, report["warning_counts"]
    assert report["failures"] == []
