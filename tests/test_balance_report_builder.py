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
    assert len(frozen_report["catalog"]["records"]) == 121
    assert frozen_report["analysis"]["standard_finds"]["guarantee_answer"] == 75
    release_status = frozen_report["release_status"]
    assert release_status["automated"]["status"] == "pass"
    assert release_status["modeled_acceptance"]["status"] == "not_evaluated"
    assert release_status["production_parity"]["status"] == "not_run"
    assert release_status["migration_tests"]["status"] == "not_run"
    assert release_status["native_macos_smoke"]["status"] == "not_run"
    assert release_status["human_review"]["status"] == "pending"
    assert release_status["platform_macos_100_percent_text"]["status"] == "not_run"
    assert release_status["release_ready"] is False
    assert set(release_status["blocking_gates"]) == {
        "production_parity",
        "modeled_acceptance",
        "migration_tests",
        "native_macos_smoke",
        "human_review",
        "platform_macos_100_percent_text",
    }


def test_report_validation_rejects_hash_mismatch(frozen_report):
    changed = deepcopy(frozen_report)
    changed["catalog"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_frozen_report(changed)


def test_report_validation_rejects_false_release_promotion(frozen_report):
    changed = deepcopy(frozen_report)
    changed["release_status"]["release_ready"] = True
    changed["release_status"]["blocking_gates"] = []
    with pytest.raises(ValueError, match="cannot bypass"):
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
        ("light:collection_first:baseline", "coins.gross"): {"p10": 4_446},
        ("light:collection_first:baseline", "catalog.functional_completion_day"): {"p50": 365},
        ("headline:collection_first:baseline", "catalog.pre_endgame_completion_day"): {"p50": 220},
        ("power:collection_first:baseline", "catalog.pre_endgame_completion_day"): {"p50": 160},
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
    for scenario in scenario_index.values():
        common = {
            "scenario_id": scenario["scenario_id"],
            "strategy_id": scenario["strategy_id"],
            "case_id": scenario["case_id"],
            "checkpoint_day": 365,
        }
        changed["statistics"].append({
            **common,
            "metric_id": "catalog.finite_permanent_remaining_coins",
            "min": 1,
        })
        if (
            scenario["cohort_id"]
            in {"very_light", "light", "moderate", "headline"}
            and scenario["strategy_id"] == "collection_first"
            and scenario["case_id"] == "baseline"
        ):
            changed["statistics"].append({
                **common,
                "metric_id": "coins.gross_without_completion_rewards",
                "min": 1,
            })
            changed["coin_concentration"].append({
                **common,
                "ledger_source_hhi": 0.30,
                "top_source_share": 0.40,
                "completion_family_share": 0.60,
                "gross_without_completion_rewards": 4_000,
                "gross_without_completion_share": 0.40,
            })
        if (
            scenario["strategy_id"] == "optimal_coin"
            and scenario["case_id"] == "landmark_mastery"
        ):
            changed["statistics"].extend((
                {
                    **common,
                    "metric_id": "endgame.finite_growth_remaining_units",
                    "min": 1,
                },
                {
                    **common,
                    "metric_id": "endgame.finite_targets_remaining",
                    "min": 1,
                },
                {
                    **common,
                    "metric_id": "endgame.active_project_no_unallocated_storage",
                    "min": 1,
                },
            ))
        if (
            scenario["strategy_id"] == "no_spend"
            and scenario["case_id"] == "all_plants_complete"
        ):
            changed["statistics"].extend((
                {
                    **common,
                    "metric_id": "endgame.no_project_preserves_entire_reserve",
                    "min": 1,
                },
                {
                    **common,
                    "metric_id": "endgame.no_project_preservation_delta_units",
                    "max": 0,
                },
            ))
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
        "COINS-FUNCTIONAL-DEMAND",
        "COINS-PRE-ENDGAME-DEMAND",
        "COINS-PERMANENT-DEMAND",
        "COINS-25-CORE-AFFORDABILITY",
        "COINS-25-FUNCTIONAL-DAY",
        "COINS-100-PRE-ENDGAME-DAY",
        "COINS-400-PRE-ENDGAME-DAY",
        "FAIRNESS-FERTILIZER-SPEED",
        "COINS-ALL-COHORTS-PERMANENT-REMAINS",
        "COINS-100-200-400-PERMANENT-REMAINS",
        "ENDGAME-FINITE-GROWTH-REMAINS",
        "ENDGAME-100-200-400-TARGETS-REMAIN",
        "ENDGAME-ACTIVE-PROJECT-NO-STORAGE",
        "ENDGAME-NO-PROJECT-PRESERVES-RESERVE",
        "COINS-LEDGER-HHI",
        "COINS-TOP-SOURCE-SHARE",
        "COINS-COMPLETION-FAMILY-WATCH",
        "COINS-NON-COMPLETION-PROGRESSION",
        "INTEGRITY-PRODUCTION-PARITY",
    ]
    assert rows["PACE-10-FIRST-FULL-BLOOM"]["status"] == "pass"
    assert rows["PACE-10-FIRST-FULL-BLOOM"]["evidence"].startswith("350 active days")
    assert rows["PACE-25-FULL-BLOOMS"]["status"] == "pass"
    assert rows["PACE-100-FULL-BLOOMS"]["status"] == "pass"
    assert rows["COINS-25-CORE-AFFORDABILITY"]["status"] == "attention"
    assert "4,446" in rows["COINS-25-CORE-AFFORDABILITY"]["evidence"]
    assert "5,825" in rows["COINS-25-CORE-AFFORDABILITY"]["evidence"]
    assert rows["COINS-FUNCTIONAL-DEMAND"]["status"] == "pass"
    assert rows["COINS-PRE-ENDGAME-DEMAND"]["status"] == "pass"
    assert rows["COINS-PERMANENT-DEMAND"] == {
        "criterion_id": "COINS-PERMANENT-DEMAND",
        "status": "pass",
        "criterion": "All finite permanent Garden Coin demand matches the release specification",
        "evidence": "19,775 Garden Coins",
        "target": "19,775 Garden Coins",
    }
    assert rows["FAIRNESS-FERTILIZER-SPEED"]["status"] == "pass"
    assert rows["COINS-25-FUNCTIONAL-DAY"]["status"] == "pass"
    assert rows["COINS-100-PRE-ENDGAME-DAY"]["status"] == "pass"
    assert rows["COINS-400-PRE-ENDGAME-DAY"]["status"] == "pass"
    assert rows["COINS-ALL-COHORTS-PERMANENT-REMAINS"]["status"] == "pass"
    assert rows["COINS-100-200-400-PERMANENT-REMAINS"]["status"] == "pass"
    assert rows["ENDGAME-FINITE-GROWTH-REMAINS"]["status"] == "pass"
    assert rows["ENDGAME-100-200-400-TARGETS-REMAIN"]["status"] == "pass"
    assert rows["ENDGAME-ACTIVE-PROJECT-NO-STORAGE"]["status"] == "pass"
    assert rows["ENDGAME-NO-PROJECT-PRESERVES-RESERVE"]["status"] == "pass"
    assert rows["COINS-LEDGER-HHI"]["status"] == "pass"
    assert rows["COINS-TOP-SOURCE-SHARE"]["status"] == "pass"
    assert rows["COINS-COMPLETION-FAMILY-WATCH"]["status"] == "pass"
    assert rows["COINS-NON-COMPLETION-PROGRESSION"]["status"] == "pass"
    assert "40.0% to 40.0%" in rows[
        "COINS-NON-COMPLETION-PROGRESSION"
    ]["evidence"]
    assert rows["INTEGRITY-PRODUCTION-PARITY"]["status"] == "not modeled"


@pytest.mark.parametrize(("field_name", "criterion_id", "wrong_value"), (
    ("functional_catalog_cost_total", "COINS-FUNCTIONAL-DEMAND", 5_824),
    ("pre_endgame_permanent_cost_total", "COINS-PRE-ENDGAME-DEMAND", 7_124),
    ("permanent_cost_total", "COINS-PERMANENT-DEMAND", 13_025),
))
def test_scorecard_marks_wrong_catalog_demand_for_attention(
    frozen_report,
    field_name,
    criterion_id,
    wrong_value,
):
    report = _release_scorecard_fixture(frozen_report)
    report["analysis"]["coins"][field_name] = wrong_value
    rows = {
        row["criterion_id"]: row
        for row in balance_scorecard_rows(report)
    }
    assert rows[criterion_id]["status"] == "attention"
    assert rows[criterion_id]["evidence"] == f"{wrong_value:,} Garden Coins"


def test_scorecard_requires_all_four_coin_concentration_cohorts(frozen_report):
    report = _release_scorecard_fixture(frozen_report)
    report["coin_concentration"] = [
        row for row in report["coin_concentration"]
        if not (
            row.get("scenario_id") == "very_light:collection_first:baseline"
            and row.get("checkpoint_day") == 365
        )
    ]
    rows = {
        row["criterion_id"]: row
        for row in balance_scorecard_rows(report)
    }
    for criterion_id in (
        "COINS-LEDGER-HHI",
        "COINS-TOP-SOURCE-SHARE",
        "COINS-COMPLETION-FAMILY-WATCH",
    ):
        assert rows[criterion_id]["status"] == "not modeled"
        assert "3/4 cohorts" in rows[criterion_id]["evidence"]


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
    assert catalog_record_price_status(
        "consumable", records[("consumable", "booster_potion")]
    ) == "Garden Find / Garden reward"
