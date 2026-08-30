from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.balance_analysis.artifacts import finalize_report
from scripts.balance_analysis.report import (
    REPORT_SECTIONS,
    balance_scorecard_rows,
    catalog_record_price_status,
    report_outline,
    representative_statistic_rows,
    validate_frozen_report,
)
from scripts.simulate_balance_profiles import REPOSITORY_ROOT, simulate_profiles


@pytest.fixture(scope="module")
def frozen_report():
    return finalize_report(
        simulate_profiles(seeds=1, days=7),
        repository_root=REPOSITORY_ROOT,
    )


def test_frozen_report_has_a_concise_fifteen_page_outline(frozen_report):
    outline = report_outline(frozen_report)
    assert len(REPORT_SECTIONS) == len(outline) == 15
    assert outline[0]["section_id"] == "cover"
    assert outline[-1]["section_id"] == "method"
    assert len(frozen_report["catalog"]["records"]) == 110
    assert frozen_report["analysis"]["standard_finds"]["guarantee_answer"] == 75


def test_report_validation_rejects_hash_mismatch(frozen_report):
    changed = deepcopy(frozen_report)
    changed["catalog"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_frozen_report(changed)


def test_report_validation_rejects_failed_assertion(frozen_report):
    changed = deepcopy(frozen_report)
    changed["assertions"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="failed assertions"):
        validate_frozen_report(changed)


def test_report_validation_keeps_balance_misses_non_blocking(frozen_report):
    changed = deepcopy(frozen_report)
    changed["assertions"].append({
        "assertion_id": "BALANCE-PACING-REVIEW",
        "class": "balance",
        "status": "fail",
        "observed": 1,
        "expected": 2,
    })
    validate_frozen_report(changed)


def test_report_validation_rejects_unresolvable_finding_refs(frozen_report):
    changed = deepcopy(frozen_report)
    changed["findings"].append({
        "finding_id": "BROKEN",
        "metric_refs": ["missing|365|metric"],
    })
    with pytest.raises(ValueError, match="unknown metric refs"):
        validate_frozen_report(changed)


def test_representative_tables_include_all_six_cohorts_in_matrix_order(frozen_report):
    rows = representative_statistic_rows(
        frozen_report,
        "plants.full_bloom",
        checkpoint_day=7,
    )
    assert [row["scenario_id"] for row in rows] == [
        "very_light:collection_first:baseline",
        "light:collection_first:baseline",
        "moderate:collection_first:baseline",
        "headline:collection_first:baseline",
        "heavy:collection_first:baseline",
        "power:collection_first:baseline",
    ]
    assert {row["strategy_id"] for row in rows} == {"collection_first"}
    assert {row["case_id"] for row in rows} == {"baseline"}


def _release_scorecard_fixture(frozen_report):
    changed = deepcopy(frozen_report)
    values = {
        ("light:collection_first:baseline", "plants.full_bloom"): {"p50": 3},
        ("headline:collection_first:baseline", "plants.full_bloom"): {"p50": 10},
        ("light:collection_first:baseline", "coins.gross"): {"p50": 4_446},
        ("headline:optimal_coin:landmark_mastery", "landmarks.owned"): {"max": 0},
        ("headline:optimal_coin:landmark_mastery", "mastery.owned"): {"max": 18},
        ("heavy:optimal_coin:landmark_mastery", "landmarks.owned"): {"max": 0},
        ("heavy:optimal_coin:landmark_mastery", "mastery.owned"): {"max": 25},
        ("power:optimal_coin:landmark_mastery", "landmarks.owned"): {"max": 2},
        ("power:optimal_coin:landmark_mastery", "mastery.owned"): {"max": 31},
    }
    scenario_index = {
        row["scenario_id"]: row
        for row in changed["scenario_matrix"]["scenarios"]
    }
    for (scenario_id, metric_id), summary in values.items():
        scenario = scenario_index[scenario_id]
        changed["statistics"].append({
            "scenario_id": scenario_id,
            "strategy_id": scenario["strategy_id"],
            "case_id": scenario["case_id"],
            "checkpoint_day": 365,
            "metric_id": metric_id,
            **summary,
        })
    return changed


def test_scorecard_exposes_release_pacing_and_coin_miss_without_blocking(frozen_report):
    report = _release_scorecard_fixture(frozen_report)
    rows = {
        row["criterion_id"]: row
        for row in balance_scorecard_rows(report)
    }
    assert list(rows) == [
        "PACE-10-FIRST-FULL-BLOOM",
        "PACE-25-FULL-BLOOMS",
        "PACE-100-FULL-BLOOMS",
        "COINS-25-CORE-AFFORDABILITY",
        "ENDGAME-100-REMAINS-OPEN",
        "ENDGAME-200-400-REMAINS-OPEN",
        "COINS-PERMANENT-DEMAND",
        "FAIRNESS-FERTILIZER-SPEED",
    ]
    assert rows["PACE-10-FIRST-FULL-BLOOM"]["status"] == "pass"
    assert rows["PACE-10-FIRST-FULL-BLOOM"]["evidence"].startswith("350 active days")
    assert rows["PACE-25-FULL-BLOOMS"]["status"] == "pass"
    assert rows["PACE-100-FULL-BLOOMS"]["status"] == "pass"
    assert rows["COINS-25-CORE-AFFORDABILITY"]["status"] == "attention"
    assert "4,446" in rows["COINS-25-CORE-AFFORDABILITY"]["evidence"]
    assert "5,825" in rows["COINS-25-CORE-AFFORDABILITY"]["evidence"]
    assert rows["ENDGAME-100-REMAINS-OPEN"]["status"] == "pass"
    assert rows["ENDGAME-200-400-REMAINS-OPEN"]["status"] == "pass"
    assert rows["COINS-PERMANENT-DEMAND"] == {
        "criterion_id": "COINS-PERMANENT-DEMAND",
        "status": "pass",
        "criterion": "Long-term permanent Coin demand matches the release specification",
        "evidence": "19,775 Coins",
        "target": "19,775 Coins",
    }
    assert rows["FAIRNESS-FERTILIZER-SPEED"]["status"] == "pass"


def test_scorecard_marks_wrong_permanent_demand_for_attention(frozen_report):
    report = _release_scorecard_fixture(frozen_report)
    report["analysis"]["coins"]["permanent_cost_total"] = 13_025
    rows = {
        row["criterion_id"]: row
        for row in balance_scorecard_rows(report)
    }
    assert rows["COINS-PERMANENT-DEMAND"]["status"] == "attention"
    assert rows["COINS-PERMANENT-DEMAND"]["evidence"] == "13,025 Coins"


def test_catalog_cost_labels_preserve_every_release_cost_axis(frozen_report):
    records = {
        (row["category"], row["item_id"]): row["definition"]
        for row in frozen_report["catalog"]["records"]
    }

    assert catalog_record_price_status(
        "species", records[("species", "dahlia")]
    ) == "250 C; one starter free"
    assert catalog_record_price_status(
        "bed", records[("bed", "bed_1")]
    ) == "Included"
    assert catalog_record_price_status(
        "bed", records[("bed", "bed_3")]
    ) == "Achievement: First Canopy"
    assert catalog_record_price_status(
        "landmark", records[("landmark", "mossy_stone_path")]
    ) == "25,000 G + 250 C"
    assert catalog_record_price_status(
        "mastery", records[("mastery", "iridescent")]
    ) == "200,000 G + 400 C / species"
