from __future__ import annotations

from scripts.validate_full_catalog_layout import validate


def test_full_catalog_layout_matrix_is_warning_free() -> None:
    report = validate()
    assert report["asset_count"] == 150
    assert report["scenario_count"] == 150 * 3 * 8 * 6 * 2
    assert report["failure_count"] == 0, report["warning_counts"]
    assert report["failures"] == []
