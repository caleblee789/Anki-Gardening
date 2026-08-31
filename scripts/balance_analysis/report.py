from __future__ import annotations

"""Frozen-data ReportLab builder for the economy analysis PDF.

This module never imports runtime Garden catalogs.  A catalog hash mismatch or
failed correctness or configuration assertion prevents authoring, so the PDF
cannot silently mix two source snapshots. Balance-target misses remain visible:
they block release readiness through modeled acceptance without being proof that
the simulator itself is invalid.
"""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ReportSection:
    section_id: str
    title: str
    subtitle: str


REPORT_SECTIONS: Tuple[ReportSection, ...] = (
    ReportSection("cover", "Economy, Progression, and Rewards", "Scope and source snapshot"),
    ReportSection("scorecard", "Executive scorecard", "Release targets and top modeled risks"),
    ReportSection("catalog", "Complete catalog map", "Every purchasable and earnable record"),
    ReportSection("permanent", "Permanent purchases", "Finite costs and acquisition routes"),
    ReportSection("earnable", "Earnable and repeatable", "Finds, consumables, and unavailable entries"),
    ReportSection("progression", "Progression pacing", "Stage and Full Bloom timing"),
    ReportSection("growth", "Growth capacity", "Shared Growth, application, and storage"),
    ReportSection("coins", "Garden Coin economy", "Sources, sinks, and concentration"),
    ReportSection("strategy", "Affordability and strategy", "Collection-first pacing across cohorts"),
    ReportSection("consumables", "Consumables", "Value, use, and speed sensitivity"),
    ReportSection("environments", "Garden bonuses and scenery", "Effects, conditions, and payback"),
    ReportSection("finds", "Standard Finds", "Expected value, cap, and guarantee"),
    ReportSection("discoveries", "Environment discoveries", "Tier distributions and hard guarantees"),
    ReportSection("fairness", "Fairness and endgame", "Cohort normalization and post-catalog risk"),
    ReportSection("method", "Method and limitations", "Seeds, assertions, and reproducibility"),
)


REPRESENTATIVE_STRATEGY_ID = "collection_first"
REPRESENTATIVE_CASE_ID = "baseline"
REPRESENTATIVE_CHECKPOINT_DAY = 365
ENDGAME_STRATEGY_ID = "optimal_coin"
ENDGAME_CASE_ID = "landmark_mastery"
ENDGAME_SCENARIO_LABEL = "Landmark and Mastery spending"
EXPECTED_FUNCTIONAL_COIN_DEMAND = 5_825
EXPECTED_PRE_ENDGAME_COIN_DEMAND = 7_125
EXPECTED_PERMANENT_COIN_DEMAND = 19_775


def validate_frozen_report(report: Mapping[str, Any]) -> None:
    required = {
        "$schema",
        "run",
        "catalog",
        "analysis",
        "scenario_matrix",
        "statistics",
        "growth_accounting_statistics",
        "consumable_statistics",
        "environment_acquisition_statistics",
        "coin_concentration",
        "milestones",
        "assertions",
        "parity",
        "release_status",
        "findings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"frozen report is missing keys: {missing}")
    run = report.get("run")
    catalog = report.get("catalog")
    analysis = report.get("analysis")
    if not all(isinstance(value, Mapping) for value in (run, catalog, analysis)):
        raise ValueError("run, catalog, and analysis must be objects")
    if not run.get("run_id"):
        raise ValueError("frozen report has no run_id")
    if run.get("catalog_sha256") != catalog.get("sha256"):
        raise ValueError("run/catalog hash mismatch")
    if int(run.get("seed_count", 0) or 0) <= 0:
        raise ValueError("frozen report has no seeds")
    if report.get("$schema") != (
        "https://anki-garden.local/schemas/economy-analysis-v2.json"
    ):
        raise ValueError("frozen report is not economy analysis schema v2")
    if int(run.get("report_schema_version", 0) or 0) != 2:
        raise ValueError("frozen report has the wrong report schema version")
    parity = report.get("parity")
    release_status = report.get("release_status")
    if not isinstance(parity, Mapping) or not isinstance(release_status, Mapping):
        raise ValueError("parity and release_status must be objects")
    parity_gate = release_status.get("production_parity")
    if not isinstance(parity_gate, Mapping):
        raise ValueError("release_status has no production_parity gate")
    if (
        parity_gate.get("status") != parity.get("status")
        or parity_gate.get("production_engine_trace_equivalent")
        is not parity.get("production_engine_trace_equivalent")
    ):
        raise ValueError("release_status production parity does not match parity evidence")
    release_ready = release_status.get("release_ready")
    if not isinstance(release_ready, bool):
        raise ValueError("release_status.release_ready must be a boolean")
    if release_ready and (
        parity.get("status") != "pass"
        or parity.get("production_engine_trace_equivalent") is not True
        or release_status.get("blocking_gates")
    ):
        raise ValueError("release_ready cannot bypass an incomplete release gate")
    required_release_gates = (
        "automated",
        "modeled_acceptance",
        "production_parity",
        "migration_tests",
        "native_macos_smoke",
        "human_review",
        "platform_macos_100_percent_text",
    )
    allowed_gate_statuses = {
        "pass", "fail", "attention", "not_run", "not_evaluated", "pending",
    }
    for gate_id in required_release_gates:
        gate = release_status.get(gate_id)
        if not isinstance(gate, Mapping):
            raise ValueError(f"release_status has no {gate_id} gate")
        status = str(gate.get("status", ""))
        if status not in allowed_gate_statuses:
            raise ValueError(f"release_status {gate_id} has invalid status")
        if gate_id in {
            "migration_tests",
            "native_macos_smoke",
            "human_review",
            "platform_macos_100_percent_text",
        } and status == "pass":
            refs = gate.get("evidence_refs", ())
            digest = str(gate.get("evidence_sha256", "") or "")
            if (
                not isinstance(refs, Sequence)
                or isinstance(refs, (str, bytes))
                or not refs
                or any(not str(value).strip() for value in refs)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError(
                    f"release_status {gate_id} has an unsupported pass claim"
                )
    expected_blocking_gates = [
        gate_id for gate_id in required_release_gates
        if release_status[gate_id].get("status") != "pass"
    ]
    if list(release_status.get("blocking_gates", ())) != expected_blocking_gates:
        raise ValueError("release_status blocking_gates do not match gate statuses")
    if release_ready != (not expected_blocking_gates):
        raise ValueError("release_status.release_ready does not match gate statuses")
    failures = [
        row for row in report.get("assertions", ())
        if (
            isinstance(row, Mapping)
            and row.get("status") != "pass"
            and str(row.get("class", "correctness"))
            in {"correctness", "configuration"}
        )
    ]
    if failures:
        raise ValueError(f"frozen report contains failed assertions: {failures}")
    metric_refs = {
        f"{row.get('scenario_id')}|{row.get('checkpoint_day')}|{row.get('metric_id')}"
        for row in report.get("statistics", ())
        if isinstance(row, Mapping)
    }
    for finding in report.get("findings", ()):
        if not isinstance(finding, Mapping):
            continue
        unknown = sorted(set(finding.get("metric_refs", ())) - metric_refs)
        if unknown:
            raise ValueError(
                f"finding {finding.get('finding_id')} has unknown metric refs: {unknown}"
            )


def report_outline(report: Mapping[str, Any]) -> Sequence[Mapping[str, str]]:
    validate_frozen_report(report)
    return tuple({
        "section_id": section.section_id,
        "title": section.title,
        "subtitle": section.subtitle,
    } for section in REPORT_SECTIONS)


def _cohort_ids(report: Mapping[str, Any]) -> Tuple[str, ...]:
    matrix = report.get("scenario_matrix", {})
    if not isinstance(matrix, Mapping):
        return ()
    cohorts = matrix.get("cohorts", ())
    if not isinstance(cohorts, Sequence) or isinstance(cohorts, (str, bytes)):
        return ()
    return tuple(
        str(row.get("cohort_id", ""))
        for row in cohorts
        if isinstance(row, Mapping) and str(row.get("cohort_id", ""))
    )


def _scenario_id(
    report: Mapping[str, Any],
    cohort_id: str,
    strategy_id: str,
    case_id: str,
) -> str:
    matrix = report.get("scenario_matrix", {})
    scenarios = matrix.get("scenarios", ()) if isinstance(matrix, Mapping) else ()
    for row in scenarios if isinstance(scenarios, Sequence) else ():
        if not isinstance(row, Mapping):
            continue
        if (
            row.get("cohort_id") == cohort_id
            and row.get("strategy_id") == strategy_id
            and row.get("case_id") == case_id
        ):
            return str(row.get("scenario_id", ""))
    return ""


def representative_statistic_rows(
    report: Mapping[str, Any],
    metric_id: str,
    *,
    checkpoint_day: int = REPRESENTATIVE_CHECKPOINT_DAY,
    strategy_id: str = REPRESENTATIVE_STRATEGY_ID,
    case_id: str = REPRESENTATIVE_CASE_ID,
) -> Sequence[Mapping[str, Any]]:
    """Return one declared-policy row for every cohort, in matrix order.

    Alphabetical truncation made the old report look comprehensive while it
    happened to show only the first few scenarios.  The explicit policy here
    keeps every metric page comparable and ensures all six approved cohorts are
    represented.
    """

    rows = {
        str(row.get("scenario_id", "")): row
        for row in report.get("statistics", ())
        if (
            isinstance(row, Mapping)
            and row.get("metric_id") == metric_id
            and int(row.get("checkpoint_day", 0) or 0) == checkpoint_day
            and row.get("strategy_id") == strategy_id
            and row.get("case_id") == case_id
        )
    }
    selected = []
    for cohort_id in _cohort_ids(report):
        scenario_id = _scenario_id(report, cohort_id, strategy_id, case_id)
        if scenario_id in rows:
            selected.append(rows[scenario_id])
    return tuple(selected)


def _statistic(
    report: Mapping[str, Any],
    *,
    cohort_id: str,
    metric_id: str,
    strategy_id: str = REPRESENTATIVE_STRATEGY_ID,
    case_id: str = REPRESENTATIVE_CASE_ID,
    checkpoint_day: int = REPRESENTATIVE_CHECKPOINT_DAY,
) -> Optional[Mapping[str, Any]]:
    scenario_id = _scenario_id(report, cohort_id, strategy_id, case_id)
    return next((
        row for row in report.get("statistics", ())
        if (
            isinstance(row, Mapping)
            and row.get("scenario_id") == scenario_id
            and row.get("metric_id") == metric_id
            and int(row.get("checkpoint_day", 0) or 0) == checkpoint_day
        )
    ), None)


def _criterion(
    criterion_id: str,
    status: str,
    criterion: str,
    evidence: str,
    target: str,
) -> Mapping[str, str]:
    return {
        "criterion_id": criterion_id,
        "status": status,
        "criterion": criterion,
        "evidence": evidence,
        "target": target,
    }


def _numeric_status(value: Any, predicate) -> str:
    if not isinstance(value, (int, float)):
        return "not modeled"
    return "pass" if predicate(float(value)) else "attention"


def balance_scorecard_rows(report: Mapping[str, Any]) -> Sequence[Mapping[str, str]]:
    """Evaluate the release targets consumed by the modeled-acceptance gate."""

    analysis = report.get("analysis", {})
    analysis = analysis if isinstance(analysis, Mapping) else {}
    growth = analysis.get("growth", {})
    growth = growth if isinstance(growth, Mapping) else {}
    coins = analysis.get("coins", {})
    coins = coins if isinstance(coins, Mapping) else {}

    scenario_matrix = report.get("scenario_matrix", {})
    scenario_rows = (
        scenario_matrix.get("scenarios", ())
        if isinstance(scenario_matrix, Mapping) else ()
    )
    scenario_rows = tuple(
        row for row in scenario_rows
        if isinstance(row, Mapping) and row.get("scenario_id")
    )

    def selected_metric_rows(
        metric_id: str,
        selector,
    ) -> Tuple[Sequence[Mapping[str, Any]], Sequence[str]]:
        expected_ids = {
            str(row["scenario_id"])
            for row in scenario_rows
            if selector(row)
        }
        found = {
            str(row.get("scenario_id")): row
            for row in report.get("statistics", ())
            if (
                isinstance(row, Mapping)
                and row.get("scenario_id") in expected_ids
                and row.get("metric_id") == metric_id
                and int(row.get("checkpoint_day", 0) or 0)
                == REPRESENTATIVE_CHECKPOINT_DAY
            )
        }
        missing = tuple(sorted(expected_ids - set(found)))
        return tuple(found[scenario_id] for scenario_id in sorted(found)), missing

    def strict_extreme(
        metric_id: str,
        selector,
        *,
        statistic_field: str,
        use_minimum: bool,
        predicate,
        unit: str,
    ) -> Tuple[str, str]:
        metric_rows, missing = selected_metric_rows(metric_id, selector)
        values = [row.get(statistic_field) for row in metric_rows]
        if missing or not values or not all(
            isinstance(value, (int, float)) for value in values
        ):
            return (
                "not modeled",
                f"Missing day-365 evidence for {len(missing)} scenario(s)",
            )
        extreme = min(values) if use_minimum else max(values)
        label = "Minimum" if use_minimum else "Maximum"
        return (
            "pass" if predicate(float(extreme)) else "attention",
            f"{label} {_fmt(extreme, 0)} {unit} across {len(values)} scenarios",
        )

    rows = []
    full_bloom = growth.get("full_bloom_growth")
    base_growth = growth.get("base_growth_per_review")
    if (
        isinstance(full_bloom, (int, float))
        and isinstance(base_growth, (int, float))
        and base_growth > 0
    ):
        base_cards = math.ceil(float(full_bloom) / float(base_growth))
        active_days = math.ceil(base_cards / 10)
        status = "pass" if active_days <= 365 else "attention"
        evidence = f"{active_days:,} active days ({base_cards:,} base cards)"
    else:
        status = "not modeled"
        evidence = "Threshold or base Growth is unavailable"
    rows.append(_criterion(
        "PACE-10-FIRST-FULL-BLOOM",
        status,
        "10 cards/day reaches a first Full Bloom",
        evidence,
        "Within 365 active days",
    ))

    for criterion_id, cohort_id, label, low, high in (
        ("PACE-25-FULL-BLOOMS", "light", "25-card cohort Full Blooms", 2, None),
        ("PACE-100-FULL-BLOOMS", "headline", "100-card cohort Full Blooms", 8, 10),
    ):
        statistic = _statistic(report, cohort_id=cohort_id, metric_id="plants.full_bloom")
        median = statistic.get("p50") if statistic else None
        predicate = (
            (lambda value, minimum=low: value >= minimum)
            if high is None
            else (lambda value, minimum=low, maximum=high: minimum <= value <= maximum)
        )
        rows.append(_criterion(
            criterion_id,
            _numeric_status(median, predicate),
            label,
            f"Median {_fmt(median, 0)} plants at day 365",
            f"At least {low}" if high is None else f"{low} to {high}",
        ))

    cost_gates = (
        (
            "COINS-FUNCTIONAL-DEMAND",
            "functional_catalog_cost_total",
            EXPECTED_FUNCTIONAL_COIN_DEMAND,
            "Functional catalog cost matches the release specification",
        ),
        (
            "COINS-PRE-ENDGAME-DEMAND",
            "pre_endgame_permanent_cost_total",
            EXPECTED_PRE_ENDGAME_COIN_DEMAND,
            "Full pre-endgame catalog cost matches the release specification",
        ),
        (
            "COINS-PERMANENT-DEMAND",
            "permanent_cost_total",
            EXPECTED_PERMANENT_COIN_DEMAND,
            "All finite permanent Garden Coin demand matches the release specification",
        ),
    )
    for criterion_id, field_name, expected, label in cost_gates:
        observed = coins.get(field_name)
        rows.append(_criterion(
            criterion_id,
            _numeric_status(observed, lambda value, target=expected: value == target),
            label,
            f"{_fmt(observed, 0)} Garden Coins",
            f"{expected:,} Garden Coins",
        ))

    light_coins = _statistic(report, cohort_id="light", metric_id="coins.gross")
    light_gross = light_coins.get("p10") if light_coins else None
    rows.append(_criterion(
        "COINS-25-CORE-AFFORDABILITY",
        (
            _numeric_status(
                light_gross,
                lambda value: value >= EXPECTED_FUNCTIONAL_COIN_DEMAND,
            )
        ),
        "25-card cohort gross Garden Coin sufficiency for the core catalog",
        (
            f"P10 gross {_fmt(light_gross, 0)} Garden Coins vs "
            f"{EXPECTED_FUNCTIONAL_COIN_DEMAND:,} required"
        ),
        "P10 gross Garden Coins at least 5,825",
    ))

    for criterion_id, cohort_id, predicate, target in (
        (
            "COINS-25-FUNCTIONAL-DAY",
            "light",
            lambda value: value <= 365,
            "Median no later than day 365",
        ),
        (
            "COINS-100-PRE-ENDGAME-DAY",
            "headline",
            lambda value: 180 <= value <= 270,
            "Median day 180 to 270",
        ),
        (
            "COINS-400-PRE-ENDGAME-DAY",
            "power",
            lambda value: value >= 150,
            "Median no earlier than day 150",
        ),
    ):
        # Light accessibility is deliberately measured against the functional
        # 5,825-Garden-Coin subset.  The Headline and Power pacing bounds were
        # historically content-exhaustion guards, so bind them to the entire
        # 7,125-Garden-Coin non-endgame plan (including optional cosmetics).
        # Keeping the metrics distinct prevents an optional-cosmetics subset
        # from being silently substituted for either player-facing concept.
        metric_id = (
            "catalog.functional_completion_day"
            if cohort_id == "light"
            else "catalog.pre_endgame_completion_day"
        )
        completion = _statistic(
            report,
            cohort_id=cohort_id,
            metric_id=metric_id,
        )
        value = completion.get("p50") if completion else None
        rows.append(_criterion(
            criterion_id,
            _numeric_status(value, predicate),
            (
                f"{cohort_id.replace('_', ' ').title()} functional-catalog completion"
                if metric_id == "catalog.functional_completion_day"
                else f"{cohort_id.replace('_', ' ').title()} pre-endgame completion"
            ),
            f"Median {_fmt(value, 0)}",
            target,
        ))

    speed_rows = analysis.get("optional_speed_sensitivity", {})
    speed_rows = speed_rows.get("rows", ()) if isinstance(speed_rows, Mapping) else ()
    fertilizers = [
        row for row in speed_rows
        if isinstance(row, Mapping) and str(row.get("item_id", "")).startswith("fertilizer_")
    ] if isinstance(speed_rows, Sequence) else []
    if not fertilizers:
        fertilizer_status = "not modeled"
        fertilizer_evidence = "No purchasable Fertilizer rows"
    else:
        invariant = all(
            row.get("growth_per_coin_is_speed_invariant") is True
            for row in fertilizers
        )
        fertilizer_status = "pass" if invariant else "attention"
        fertilizer_evidence = f"{len(fertilizers)} tiers; " + (
            "all invariant" if invariant else "speed variance detected"
        )
    rows.append(_criterion(
        "FAIRNESS-FERTILIZER-SPEED",
        fertilizer_status,
        "Purchased Fertilizer value is independent of review speed",
        fertilizer_evidence,
        "Every purchasable tier is speed-invariant",
    ))

    all_scenarios = lambda _row: True
    high_volume_scenarios = lambda row: row.get("cohort_id") in {
        "headline", "heavy", "power",
    }
    active_project_scenarios = lambda row: (
        row.get("strategy_id") == ENDGAME_STRATEGY_ID
        and row.get("case_id") == ENDGAME_CASE_ID
    )
    active_high_volume_scenarios = lambda row: (
        high_volume_scenarios(row) and active_project_scenarios(row)
    )
    no_project_reserve_scenarios = lambda row: (
        row.get("strategy_id") == "no_spend"
        and row.get("case_id") == "all_plants_complete"
    )

    status, evidence = strict_extreme(
        "catalog.finite_permanent_remaining_coins",
        all_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value > 0,
        unit="Garden Coins remaining",
    )
    rows.append(_criterion(
        "COINS-ALL-COHORTS-PERMANENT-REMAINS",
        status,
        "Every modeled cohort retains finite permanent Garden Coin demand",
        evidence,
        "Day-365 minimum greater than zero in every scenario",
    ))

    status, evidence = strict_extreme(
        "catalog.finite_permanent_remaining_coins",
        high_volume_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value > 0,
        unit="Garden Coins remaining",
    )
    rows.append(_criterion(
        "COINS-100-200-400-PERMANENT-REMAINS",
        status,
        "100-, 200-, and 400-card cohorts retain a finite Garden Coin target",
        evidence,
        "Day-365 minimum greater than zero",
    ))

    status, evidence = strict_extreme(
        "endgame.finite_growth_remaining_units",
        active_project_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value > 0,
        unit="exact Growth units remaining",
    )
    rows.append(_criterion(
        "ENDGAME-FINITE-GROWTH-REMAINS",
        status,
        "No cohort funds all finite endgame Growth within one year",
        evidence,
        "Day-365 minimum greater than zero in active-project scenarios",
    ))

    status, evidence = strict_extreme(
        "endgame.finite_targets_remaining",
        active_high_volume_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value >= 1,
        unit="finite targets remaining",
    )
    rows.append(_criterion(
        "ENDGAME-100-200-400-TARGETS-REMAIN",
        status,
        "Headline, Heavy, and Power retain an endgame Growth target",
        evidence,
        "At least one finite target remains in every seed",
    ))

    status, evidence = strict_extreme(
        "endgame.active_project_no_unallocated_storage",
        active_project_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value == 1,
        unit="invariant flag",
    )
    rows.append(_criterion(
        "ENDGAME-ACTIVE-PROJECT-NO-STORAGE",
        status,
        "An active project leaves no Stored Growth while it has capacity",
        evidence,
        "Day-365 minimum invariant flag equals one",
    ))

    preserve_status, preserve_evidence = strict_extreme(
        "endgame.no_project_preserves_entire_reserve",
        no_project_reserve_scenarios,
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value == 1,
        unit="invariant flag",
    )
    delta_status, delta_evidence = strict_extreme(
        "endgame.no_project_preservation_delta_units",
        no_project_reserve_scenarios,
        statistic_field="max",
        use_minimum=False,
        predicate=lambda value: value == 0,
        unit="exact Growth units",
    )
    if "attention" in {preserve_status, delta_status}:
        no_project_status = "attention"
    elif "not modeled" in {preserve_status, delta_status}:
        no_project_status = "not modeled"
    else:
        no_project_status = "pass"
    rows.append(_criterion(
        "ENDGAME-NO-PROJECT-PRESERVES-RESERVE",
        no_project_status,
        "No-project scenarios preserve the entire Stored Growth reserve",
        f"{preserve_evidence}; {delta_evidence}",
        "Invariant minimum one and preservation-delta maximum zero",
    ))

    concentration_cohorts = ("very_light", "light", "moderate", "headline")
    expected_concentration_ids = tuple(
        _scenario_id(
            report,
            cohort_id,
            REPRESENTATIVE_STRATEGY_ID,
            REPRESENTATIVE_CASE_ID,
        )
        for cohort_id in concentration_cohorts
    )
    concentration_rows_by_id = {}
    duplicate_concentration_ids = set()
    for concentration_row in report.get("coin_concentration", ()):
        if not isinstance(concentration_row, Mapping):
            continue
        scenario_id = str(concentration_row.get("scenario_id", ""))
        if (
            scenario_id not in expected_concentration_ids
            or int(concentration_row.get("checkpoint_day", 0) or 0) != 365
        ):
            continue
        if scenario_id in concentration_rows_by_id:
            duplicate_concentration_ids.add(scenario_id)
        concentration_rows_by_id[scenario_id] = concentration_row

    def concentration_extreme(
        field_name: str,
        *,
        predicate,
        label: str,
    ) -> Tuple[str, str, Optional[float]]:
        valid_ids = tuple(value for value in expected_concentration_ids if value)
        metric_values = [
            concentration_rows_by_id.get(scenario_id, {}).get(field_name)
            for scenario_id in valid_ids
        ]
        complete = (
            len(valid_ids) == len(concentration_cohorts)
            and not duplicate_concentration_ids
            and all(
                isinstance(value, (int, float)) for value in metric_values
            )
        )
        if not complete:
            evidenced = sum(
                isinstance(value, (int, float)) for value in metric_values
            )
            return (
                "not modeled",
                f"Complete day-365 evidence {evidenced}/{len(concentration_cohorts)} cohorts",
                None,
            )
        maximum = max(float(value) for value in metric_values)
        return (
            "pass" if predicate(maximum) else "attention",
            f"{label} {_fmt(maximum, 3)} across {len(metric_values)} cohorts",
            maximum,
        )

    hhi_status, hhi_evidence, _maximum_hhi = concentration_extreme(
        "ledger_source_hhi",
        predicate=lambda value: value <= 0.35,
        label="Maximum HHI",
    )
    source_status, source_evidence, _maximum_source = concentration_extreme(
        "top_source_share",
        predicate=lambda value: value <= 0.45,
        label="Maximum share",
    )
    completion_status, completion_evidence, _maximum_completion = (
        concentration_extreme(
            "completion_family_share",
            predicate=lambda value: value <= 0.70,
            label="Maximum share",
        )
    )
    rows.extend((
        _criterion(
            "COINS-LEDGER-HHI",
            hhi_status,
            "Pooled ledger-source Garden Coin concentration",
            hhi_evidence,
            "At most 0.35",
        ),
        _criterion(
            "COINS-TOP-SOURCE-SHARE",
            source_status,
            "Largest individual Garden Coin ledger source",
            source_evidence,
            "At most 45 percent",
        ),
        _criterion(
            "COINS-COMPLETION-FAMILY-WATCH",
            completion_status,
            "Today’s Cards behavioral-family concentration",
            completion_evidence,
            "Watch unless above 70 percent",
        ),
    ))

    non_completion_status, non_completion_evidence = strict_extreme(
        "coins.gross_without_completion_rewards",
        lambda row: (
            row.get("cohort_id") in concentration_cohorts
            and row.get("strategy_id") == REPRESENTATIVE_STRATEGY_ID
            and row.get("case_id") == REPRESENTATIVE_CASE_ID
        ),
        statistic_field="min",
        use_minimum=True,
        predicate=lambda value: value > 0,
        unit="gross Garden Coins excluding completion rewards",
    )
    share_values = [
        concentration_rows_by_id.get(scenario_id, {}).get(
            "gross_without_completion_share"
        )
        for scenario_id in expected_concentration_ids
        if scenario_id
    ]
    if len(share_values) == len(concentration_cohorts) and all(
        isinstance(value, (int, float)) for value in share_values
    ):
        non_completion_evidence += (
            "; pooled non-completion share "
            f"{100 * min(float(value) for value in share_values):.1f}% to "
            f"{100 * max(float(value) for value in share_values):.1f}%"
        )
    rows.append(_criterion(
        "COINS-NON-COMPLETION-PROGRESSION",
        non_completion_status,
        "Non-completion sources retain positive Garden Coin progression",
        non_completion_evidence,
        "Day-365 per-seed minimum greater than zero in all four cohorts",
    ))

    parity = report.get("parity", {})
    parity = parity if isinstance(parity, Mapping) else {}
    parity_passed = (
        parity.get("status") == "pass"
        and parity.get("production_engine_trace_equivalent") is True
    )
    rows.append(_criterion(
        "INTEGRITY-PRODUCTION-PARITY",
        "pass" if parity_passed else "not modeled",
        "Accelerated and production traces match exactly",
        str(parity.get("status", "not run")).replace("_", " ").title(),
        "Required release gate",
    ))
    return tuple(rows)


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None or value == "":
        return "Not reached"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def catalog_record_price_status(
    category: str,
    definition: Mapping[str, Any],
) -> str:
    """Return the compact acquisition/cost label used by catalog pages."""

    price = next((
        definition.get(key) for key in (
            "purchase_price_coins",
            "price_coins",
            "cost_coins",
            "price",
            "unlock_cost",
            "coin_cost",
        ) if definition.get(key) is not None
    ), None)
    growth_cost = definition.get("growth_cost")
    if category == "species" and isinstance(price, (int, float)):
        return f"{int(price):,} C; one starter free"
    if category in {"landmark", "mastery"} and all(
        isinstance(value, (int, float)) for value in (growth_cost, price)
    ):
        suffix = " / species" if category == "mastery" else ""
        return f"{int(growth_cost):,} G + {int(price):,} C{suffix}"
    if category == "bed":
        if definition.get("included") is True:
            return "Included"
        achievement = str(definition.get("source_achievement_id", "")).strip()
        if achievement:
            return "Achievement: " + achievement.replace("_", " ").title()
    if isinstance(price, (int, float)):
        return f"{int(price):,} Garden Coins"
    achievement = str(definition.get("source_achievement_id", "")).strip()
    if achievement:
        return "Achievement: " + achievement.replace("_", " ").title()
    raw_status = (
        definition.get("status")
        or definition.get("acquisition")
        or "Earned/included"
    )
    status_labels = {
        "purchase": "Purchase",
        "find": "Garden Find",
        "achievement": "Achievement",
        "environment_reward": "Garden reward",
        "discovery": "Discovery",
        "included": "Included",
        "unavailable": "Unavailable",
    }

    def status_label(value: Any) -> str:
        text = str(value or "").strip()
        return status_labels.get(text, text.replace("_", " ").capitalize())

    if isinstance(raw_status, Sequence) and not isinstance(raw_status, (str, bytes)):
        return " / ".join(status_label(value) for value in raw_status)
    return status_label(raw_status)


def _fmt_fixed(value: Any, digits: int = 3) -> str:
    if not isinstance(value, Mapping):
        return "-"
    scale = int(value.get("scale", 0) or 0)
    if scale <= 0:
        return "-"
    return f"{int(value.get('scaled_integer', 0)) / scale:.{digits}f}"


def build_pdf(report: Mapping[str, Any], output_path: Path) -> Path:
    """Create the deterministic 15-page PDF from one validated frozen report."""

    validate_frozen_report(report)
    try:
        from reportlab import rl_config
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as error:
        raise RuntimeError(
            "ReportLab is required. Use the bundled Codex workspace Python runtime."
        ) from error

    rl_config.invariant = 1
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = letter
    palette = {
        "ink": colors.HexColor("#20362E"),
        "muted": colors.HexColor("#61746B"),
        "leaf": colors.HexColor("#4F8063"),
        "mist": colors.HexColor("#EAF1EC"),
        "cream": colors.HexColor("#FAF7EF"),
        "gold": colors.HexColor("#C79A45"),
        "high": colors.HexColor("#A8483D"),
        "watch": colors.HexColor("#B7792B"),
    }

    class InvariantCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("invariant", 1)
            kwargs.setdefault("pageCompression", 1)
            super().__init__(*args, **kwargs)
            self._page_number = 0
            self.setTitle("Anki Garden Economy, Progression, and Rewards Analysis")
            self.setAuthor("Anki Garden source analysis")
            self.setSubject(str(report["run"]["run_id"]))

        def showPage(self):
            self._page_number += 1
            self.saveState()
            self.setStrokeColor(palette["mist"])
            self.line(0.65 * inch, 0.52 * inch, page_width - 0.65 * inch, 0.52 * inch)
            self.setFillColor(palette["muted"])
            self.setFont("Helvetica", 7)
            self.drawString(0.65 * inch, 0.30 * inch, "Anki Garden 2.2.0 balance analysis")
            self.drawRightString(
                page_width - 0.65 * inch,
                0.30 * inch,
                f"{self._page_number} / {len(REPORT_SECTIONS)}",
            )
            self.restoreState()
            super().showPage()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "PageTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=22,
        textColor=palette["ink"],
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        "PageSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=palette["muted"],
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=palette["ink"],
    ))
    styles.add(ParagraphStyle(
        "Tiny",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.7,
        leading=8.4,
        textColor=palette["ink"],
    ))
    styles.add(ParagraphStyle(
        "MicroHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=5.2,
        leading=6.1,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        "MicroCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=5.2,
        leading=6.1,
        textColor=palette["ink"],
    ))
    styles.add(ParagraphStyle(
        "Cover",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=27,
        leading=31,
        alignment=TA_LEFT,
        textColor=palette["ink"],
        spaceAfter=18,
    ))
    styles.add(ParagraphStyle(
        "CoverMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=palette["muted"],
    ))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.68 * inch,
        title="Anki Garden Economy, Progression, and Rewards Analysis",
        author="Anki Garden source analysis",
    )

    def table(data, widths=None, tiny=False, micro=False):
        value = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        body_size = 5.2 if micro else (6.3 if tiny else 7.2)
        body_leading = 6.1 if micro else (7.6 if tiny else 9)
        vertical_padding = 1.25 if micro else 3
        value.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), palette["ink"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), body_size),
            ("LEADING", (0, 0), (-1, -1), body_leading),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, palette["cream"]]),
            ("GRID", (0, 0), (-1, -1), 0.25, palette["mist"]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
        ]))
        return value

    def heading(section: ReportSection):
        return [
            Paragraph(section.title, styles["PageTitle"]),
            Paragraph(section.subtitle, styles["PageSubtitle"]),
        ]

    story = []
    run = report["run"]
    catalog = report["catalog"]
    analysis = report["analysis"]
    findings = list(report.get("findings", ()))
    public_names = {}
    for record in catalog.get("records", ()):
        if not isinstance(record, Mapping):
            continue
        definition = record.get("definition", {})
        definition = definition if isinstance(definition, Mapping) else {}
        item_id = str(record.get("item_id", ""))
        display_name = next((
            str(definition.get(key, "")).strip()
            for key in ("display_name", "name", "title", "label")
            if str(definition.get(key, "")).strip()
        ), "")
        if item_id and display_name:
            public_names[item_id] = display_name

    tier_names = {
        "rare_environment": "Rare",
        "very_rare_environment": "Very Rare",
        "ultra_environment": "Ultra Rare",
    }

    def public_label(item_id: Any) -> str:
        value = str(item_id or "")
        return (
            public_names.get(value)
            or tier_names.get(value)
            or value.replace("_", " ").title()
        )

    metric_labels = {
        "plants.full_bloom": "Full Bloom plants",
        "growth.stored_balance_units": "Stored Growth balance",
        "coins.gross": "Gross Garden Coins",
        "catalog.functional_completion_day": "Functional catalog completion day",
        "consumables.fertilizer_basic.units_remaining": (
            "Basic Fertilizer units remaining"
        ),
        "growth.total_units": "Total generated Growth",
        "finds.total": "Standard Finds",
        "environments.discovered": "Environment discoveries",
        "growth.total_units_per_answer": "Growth units per eligible answer",
    }

    # Page 1: cover.
    story.extend([
        Spacer(1, 1.05 * inch),
        Paragraph("Anki Garden", styles["CoverMeta"]),
        Paragraph("Economy, Progression,<br/>and Rewards Analysis", styles["Cover"]),
        Paragraph(
            "A source-frozen review of the implemented 2.2.0 balance. It reports "
            "catalog definitions and modeled outcomes; it does not constitute "
            "release approval.",
            styles["CoverMeta"],
        ),
        Spacer(1, 0.48 * inch),
        table([
            ["Release target", "Seeds", "Catalog snapshot", "Run ID"],
            [
                str(run.get("release_target", "")),
                _fmt(run.get("seed_count"), 0),
                str(catalog.get("sha256", ""))[:14],
                str(run.get("run_id", ""))[:14],
            ],
        ], widths=[1.2 * inch, 1.0 * inch, 2.1 * inch, 2.1 * inch]),
    ])

    # Page 2: scorecard.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[1]))
    criteria_data = [["Status", "Release criterion", "Evidence", "Target"]]
    for row in balance_scorecard_rows(report):
        criteria_data.append([
            str(row.get("status", "not modeled")).upper(),
            Paragraph(str(row.get("criterion", "")), styles["Tiny"]),
            Paragraph(str(row.get("evidence", "")), styles["Tiny"]),
            Paragraph(str(row.get("target", "")), styles["Tiny"]),
        ])
    story.append(table(
        criteria_data,
        widths=[0.72 * inch, 2.15 * inch, 2.25 * inch, 1.63 * inch],
        micro=True,
    ))
    story.append(Spacer(1, 7))
    scorecard_findings = []
    for severity in ("high", "watch", "unknown"):
        scorecard_findings.extend([
            row for row in findings
            if row.get("severity") == severity
        ][:1])
    finding_data = [["Level", "Domain", "Finding", "Observed"]]
    for row in scorecard_findings:
        finding_data.append([
            str(row.get("severity", "unknown")).upper(),
            str(row.get("domain", "")),
            Paragraph(str(row.get("title", "")), styles["Tiny"]),
            _fmt(row.get("observed")),
        ])
    if len(finding_data) == 1:
        finding_data.append(["INFO", "analysis", "No heuristic threshold triggered.", "-"])
    story.append(table(
        finding_data,
        widths=[0.7 * inch, 0.9 * inch, 4.25 * inch, 0.9 * inch],
        micro=True,
    ))
    story.append(Spacer(1, 7))
    story.append(Paragraph(
        "ATTENTION means the supplied release target is missed in the named model; "
        "NOT MODELED means evidence is unavailable. These balance findings do not "
        "block report authoring, but they do block release readiness through modeled "
        "acceptance. Correctness and configuration assertions must pass, and "
        "neither a PASS nor this PDF constitutes release approval.",
        styles["Small"],
    ))

    # Page 3: complete catalog.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[2]))
    category_counts = {}
    for record in catalog.get("records", ()):
        category = str(record.get("category", "unknown"))
        category_counts[category] = category_counts.get(category, 0) + 1
    story.append(table(
        [["Category", "Records"]]
        + [[key.replace("_", " ").title(), value] for key, value in sorted(category_counts.items())],
        widths=[4.9 * inch, 1.1 * inch],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "The machine-readable catalog, not copied report prose, is the authority. "
        "The companion catalog CSV retains each complete definition.",
        styles["Small"],
    ))

    # Pages 4 and 5: every catalog record, split by permanent/value scope.
    records = list(catalog.get("records", ()))
    permanent_categories = {
        "species", "garden_bonus", "scenery", "cosmetic", "landmark", "mastery", "bed"
    }
    record_groups = (
        [row for row in records if row.get("category") in permanent_categories],
        [row for row in records if row.get("category") not in permanent_categories],
    )
    for selected, section_index in zip(record_groups, (3, 4)):
        story.append(PageBreak())
        story.extend(heading(REPORT_SECTIONS[section_index]))
        if section_index == 3:
            costs = analysis.get("coins", {}).get("permanent_cost_by_category", {})
            story.append(table([
                ["Functional cost", "Pre-endgame cost", "All permanent cost", "Category costs"],
                [
                    _fmt(analysis.get("coins", {}).get("functional_catalog_cost_total"), 0),
                    _fmt(analysis.get("coins", {}).get("pre_endgame_permanent_cost_total"), 0),
                    _fmt(analysis.get("coins", {}).get("permanent_cost_total"), 0),
                    ", ".join(
                        f"{public_label(key)}: {_fmt(value, 0)}"
                        for key, value in sorted(costs.items())
                    ),
                ],
            ], widths=[1.0 * inch, 1.0 * inch, 1.0 * inch, 3.3 * inch], micro=True))
            story.append(Spacer(1, 5))
        data = [["Category", "Name", "Price/status"]]
        for record in selected:
            definition = record.get("definition", {})
            if not isinstance(definition, Mapping):
                definition = {}
            category = str(record.get("category", ""))
            status = catalog_record_price_status(category, definition)
            data.append([
                category.replace("_", " ").title(),
                public_label(record.get("item_id", "")),
                status,
            ])
        story.append(table(
            data,
            widths=[1.25 * inch, 3.15 * inch, 1.9 * inch],
            micro=True,
        ))
        if section_index == 3:
            story.append(Spacer(1, 5))
            story.append(Paragraph(
                "G = Stored Growth; C = Garden Coins. Mastery costs apply to each "
                "species independently, and one starter species is free.",
                styles["Tiny"],
            ))

    metric_pages = (
        (5, "plants.full_bloom", ["Cohort", "P10", "Median", "P90"]),
        (6, "growth.stored_balance_units", ["Cohort", "P10", "Median", "P90"]),
        (7, "coins.gross", ["Cohort", "P10", "Median", "P90"]),
        (8, "catalog.functional_completion_day", ["Cohort", "Reach", "Median", "P90"]),
        (9, "consumables.fertilizer_basic.units_remaining", ["Cohort", "P10", "Median", "P90"]),
        (10, "growth.total_units", ["Cohort", "P10", "Median", "P90"]),
        (11, "finds.total", ["Cohort", "P10", "Median", "P90"]),
        (12, "environments.discovered", ["Cohort", "P10", "Median", "P90"]),
        (13, "growth.total_units_per_answer", ["Cohort", "P10", "Median", "P90"]),
    )
    for section_index, metric_id, headers in metric_pages:
        story.append(PageBreak())
        story.extend(heading(REPORT_SECTIONS[section_index]))
        if section_index == 5:
            stage_data = [[
                "Stage", "Growth", "Increment", "Stage Garden Coins", "Cumulative",
            ]]
            for row in analysis.get("growth", {}).get("stage_rows", ()):  # type: ignore[union-attr]
                stage_data.append([
                    public_label(row.get("stage_id", "")),
                    _fmt(row.get("threshold_growth"), 0),
                    _fmt(row.get("incremental_growth"), 0),
                    _fmt(row.get("stage_coin_reward"), 0),
                    _fmt(row.get("cumulative_coin_reward"), 0),
                ])
            story.append(table(stage_data, widths=[1.35 * inch] * 5, tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 6:
            growth_analysis = analysis.get("growth", {})
            story.append(table([
                ["Base Growth/card", "Shared per other plant", "Exact units/Growth", "Full Bloom"],
                [
                    _fmt(growth_analysis.get("base_growth_per_review"), 0),
                    f"{growth_analysis.get('shared_growth_numerator', 0)}/{growth_analysis.get('shared_growth_denominator', 1)}",
                    _fmt(growth_analysis.get("units_per_displayed_growth"), 0),
                    _fmt(growth_analysis.get("full_bloom_growth"), 0),
                ],
            ], widths=[1.45 * inch, 1.75 * inch, 1.45 * inch, 1.45 * inch], tiny=True))
            story.append(Spacer(1, 7))
            story.append(Paragraph(
                f"Declared endgame scenario: {ENDGAME_SCENARIO_LABEL}; "
                "Headline cohort, day-365 medians.",
                styles["Tiny"],
            ))
            story.append(Spacer(1, 3))
            accounting_data = [[
                "Scenario",
                "Generated",
                "Plants",
                "Storage lifetime",
                "Storage current",
                "Landmark",
                "Mastery",
                "Legacy",
            ]]
            accounting_metrics = (
                "growth.generated_units",
                "growth.applied_to_plants_units",
                "growth.routed_to_storage_units_lifetime",
                "growth.stored_balance_units",
                "growth.contributed_to_landmarks_units",
                "growth.contributed_to_mastery_units",
                "growth.contributed_to_legacy_units",
            )
            values = []
            for accounting_metric in accounting_metrics:
                row = _statistic(
                    report,
                    cohort_id="headline",
                    strategy_id=ENDGAME_STRATEGY_ID,
                    case_id=ENDGAME_CASE_ID,
                    metric_id=accounting_metric,
                )
                values.append(_fmt(row.get("p50") if row else None, 0))
            accounting_data.append([
                ENDGAME_SCENARIO_LABEL,
                *values,
            ])
            story.append(table(
                accounting_data,
                widths=[1.25 * inch] + [0.75 * inch] * 7,
                micro=True,
            ))
            story.append(Spacer(1, 7))
        elif section_index == 7:
            coin_analysis = analysis.get("coins", {})
            story.append(table([
                ["First answer", "Today’s Cards", "Garden Cycle / 5", "Functional cost"],
                [
                    _fmt(coin_analysis.get("daily_activity"), 0),
                    _fmt(coin_analysis.get("valid_completion"), 0),
                    _fmt(coin_analysis.get("garden_cycle_coins"), 0),
                    _fmt(coin_analysis.get("functional_catalog_cost_total"), 0),
                ],
            ], widths=[1.4 * inch, 1.5 * inch, 1.45 * inch, 1.95 * inch], tiny=True))
            story.append(Spacer(1, 7))
            concentration_data = [[
                "Cohort",
                "Ledger HHI",
                "Top source",
                "Top share",
                "Completion share",
                "Other-source gross",
                "Other-source share",
            ]]
            for cohort_id in ("very_light", "light", "moderate", "headline"):
                scenario_id = _scenario_id(
                    report,
                    cohort_id,
                    REPRESENTATIVE_STRATEGY_ID,
                    REPRESENTATIVE_CASE_ID,
                )
                concentration = next((
                    row for row in report.get("coin_concentration", ())
                    if row.get("scenario_id") == scenario_id
                    and row.get("checkpoint_day") == 365
                ), None)
                concentration = concentration or {}
                concentration_data.append([
                    cohort_id.replace("_", " ").title(),
                    _fmt(concentration.get("ledger_source_hhi"), 3),
                    public_label(concentration.get("top_source_id", "")),
                    _fmt(concentration.get("top_source_share"), 3),
                    _fmt(concentration.get("completion_family_share"), 3),
                    _fmt(
                        concentration.get("gross_without_completion_rewards"),
                        0,
                    ),
                    _fmt(
                        concentration.get("gross_without_completion_share"),
                        3,
                    ),
                ])
            story.append(table(
                concentration_data,
                widths=[0.7 * inch, 0.7 * inch, 1.15 * inch, 0.7 * inch,
                        0.9 * inch, 1.0 * inch, 0.95 * inch],
                micro=True,
            ))
            story.append(Paragraph(
                "Collection-first baseline, day 365. Concentration uses exact "
                "pooled integer ledger totals; other-source values exclude the "
                "Today’s Cards completion family. The companion CSV retains each "
                "exact numerator and denominator.",
                styles["Tiny"],
            ))
            story.append(Spacer(1, 7))
        elif section_index == 9:
            repeatable_data = [["Item", "Garden Coins", "Growth value"]]
            for row in analysis.get("repeatable_items", ()):
                repeatable_data.append([
                    public_label(row.get("item_id", "")),
                    _fmt(row.get("price_coins"), 0),
                    _fmt(row.get("growth_value"), 0),
                ])
            story.append(table(
                repeatable_data,
                widths=[4.0 * inch, 1.0 * inch, 1.3 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 7))
            per_item = [[
                "Headline median",
                "Earned",
                "Purchased",
                "Activated",
                "Consumed",
                "Remaining",
                "Effect cards",
                "Growth units",
                "Garden Coins spent",
            ]]
            for item in analysis.get("repeatable_items", ()):
                item_id = str(item.get("item_id", ""))
                values = []
                for suffix in (
                    "units_earned", "units_purchased", "units_activated",
                    "units_consumed", "units_remaining",
                    "cards_of_effect_remaining", "growth_generated",
                    "coins_spent",
                ):
                    row = _statistic(
                        report,
                        cohort_id="headline",
                        metric_id=f"consumables.{item_id}.{suffix}",
                    )
                    values.append(_fmt(row.get("p50") if row else None, 0))
                per_item.append([public_label(item_id), *values])
            story.append(table(per_item, widths=[1.45 * inch] + [0.61 * inch] * 8, micro=True))
            story.append(Spacer(1, 7))
        elif section_index == 10:
            effect_data = [[
                "Bonus / scenery", "Garden Coins", "Growth@100", "Garden Coin payback",
            ]]
            for row in analysis.get("environment_effects", ()):
                numerator = row.get("coin_payback_completion_numerator")
                denominator = row.get("coin_payback_completion_denominator")
                payback = (
                    f"{numerator}/{denominator} completions"
                    if numerator is not None and denominator else "No Garden Coin return"
                )
                growth_numerator = row.get("growth_equivalent_numerator", 0)
                growth_denominator = row.get("growth_equivalent_denominator", 1)
                effect_data.append([
                    public_label(row.get("item_id", "")),
                    _fmt(row.get("price_coins"), 0),
                    f"{growth_numerator}/{growth_denominator}",
                    payback,
                ])
            story.append(table(
                effect_data,
                widths=[2.2 * inch, 0.75 * inch, 1.05 * inch, 2.3 * inch],
                micro=True,
            ))
            story.append(Spacer(1, 6))
        elif section_index == 11:
            find_analysis = analysis.get("standard_finds", {})
            expected_coins = find_analysis.get("expected_coins", {})
            expected_growth = find_analysis.get("expected_growth_equivalent", {})
            story.append(table([
                [
                    "Mean gap / guarantee", "Daily caps 10/200/400",
                    "Expected Garden Coins/find", "Growth equivalent/find",
                ],
                [
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_gap_cards_fixed_6"))
                        + " / "
                        + _fmt(find_analysis.get("guarantee_answer"), 0)
                    ),
                    "/".join(map(str, find_analysis.get("daily_caps_at_10_200_400_answers", ()))),
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_coins_fixed_6"))
                        + f" (base {expected_coins.get('numerator', 0)}/{expected_coins.get('denominator', 1)})"
                    ),
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_growth_equivalent_fixed_6"))
                        + f" (base {expected_growth.get('numerator', 0)}/{expected_growth.get('denominator', 1)})"
                    ),
                ],
            ], widths=[1.2 * inch, 1.65 * inch, 1.55 * inch, 1.9 * inch], tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 12:
            tier_data = [["Tier", "Natural chance", "Card guarantee", "Completion guarantee", "Items"]]
            for row in analysis.get("environment_tiers", ()):
                tier_data.append([
                    public_label(row.get("tier_id", "")),
                    f"1/{_fmt(row.get('base_denominator'), 0)}",
                    _fmt(row.get("card_guarantee"), 0),
                    _fmt(row.get("completion_guarantee"), 0),
                    _fmt(row.get("item_count"), 0),
                ])
            story.append(table(
                tier_data,
                widths=[1.55 * inch, 1.15 * inch, 1.2 * inch, 1.45 * inch, 0.65 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 7))
            timing_data = [[
                "Headline tier / milestone",
                "Calendar day P10 / P50 / P90",
                "Eligible cards P10 / P50 / P90",
                "Reached",
            ]]
            for tier_row in analysis.get("environment_tiers", ()):
                tier_id = str(tier_row.get("tier_id", ""))
                for milestone, day_suffix, card_suffix in (
                    (
                        "First",
                        "first_discovery_day",
                        "first_discovery_eligible_card",
                    ),
                    (
                        "Both",
                        "both_items_completion_day",
                        "both_items_completion_eligible_card",
                    ),
                ):
                    day_row = _statistic(
                        report,
                        cohort_id="headline",
                        metric_id=f"environments.{tier_id}.{day_suffix}",
                    )
                    card_row = _statistic(
                        report,
                        cohort_id="headline",
                        metric_id=f"environments.{tier_id}.{card_suffix}",
                    )
                    timing_data.append([
                        f"{public_label(tier_id)} / {milestone}",
                        " / ".join(
                            _fmt(day_row.get(key) if day_row else None, 0)
                            for key in ("p10", "p50", "p90")
                        ),
                        " / ".join(
                            _fmt(card_row.get(key) if card_row else None, 0)
                            for key in ("p10", "p50", "p90")
                        ),
                        (
                            f"{100 * float(day_row.get('reach_rate', 0.0) or 0.0):.0f}%"
                            if day_row else "0%"
                        ),
                    ])
            story.append(table(
                timing_data,
                widths=[1.35 * inch, 2.0 * inch, 2.0 * inch, 0.7 * inch],
                micro=True,
            ))
            story.append(Paragraph(
                "Timing uses full-population nearest-rank percentiles. "
                "Not reached marks a percentile censored at day 365; Reached "
                "is the checkpoint reach rate.",
                styles["Tiny"],
            ))
            story.append(Spacer(1, 5))
            route_data = [[
                "Headline tier",
                "Natural median",
                "Card-pity median",
                "Completion-pity median",
                "Users with simultaneous pity",
                "Ownership-suppressed checks",
            ]]
            for tier_row in analysis.get("environment_tiers", ()):
                tier_id = str(tier_row.get("tier_id", ""))
                route_rows = {
                    suffix: _statistic(
                        report,
                        cohort_id="headline",
                        metric_id=f"environments.{tier_id}.{suffix}",
                    )
                    for suffix in (
                        "natural_acquisitions",
                        "card_pity_acquisitions",
                        "completion_pity_acquisitions",
                        "simultaneous_forced_user_rate",
                        "ownership_suppression_rate",
                    )
                }
                route_data.append([
                    public_label(tier_id),
                    _fmt(
                        route_rows["natural_acquisitions"].get("p50")
                        if route_rows["natural_acquisitions"] else None,
                        0,
                    ),
                    _fmt(
                        route_rows["card_pity_acquisitions"].get("p50")
                        if route_rows["card_pity_acquisitions"] else None,
                        0,
                    ),
                    _fmt(
                        route_rows["completion_pity_acquisitions"].get("p50")
                        if route_rows["completion_pity_acquisitions"] else None,
                        0,
                    ),
                    (
                        f"{100 * float(route_rows['simultaneous_forced_user_rate'].get('mean', 0.0) or 0.0):.1f}%"
                        if route_rows["simultaneous_forced_user_rate"] else "0.0%"
                    ),
                    (
                        f"{100 * float(route_rows['ownership_suppression_rate'].get('mean', 0.0) or 0.0):.1f}%"
                        if route_rows["ownership_suppression_rate"] else "0.0%"
                    ),
                ])
            story.append(table(
                route_data,
                widths=[1.0 * inch, 0.85 * inch, 0.85 * inch, 1.0 * inch, 1.25 * inch, 1.25 * inch],
                micro=True,
            ))
            story.append(Spacer(1, 7))
        elif section_index == 13:
            speed_rows = analysis.get("optional_speed_sensitivity", {}).get("rows", ())
            speed_data = [[
                "Consumable", "Growth", "Garden Coins", "Growth/Garden Coin",
                "30/100/300 cph",
            ]]
            for row in speed_rows:
                speed_data.append([
                    public_label(row.get("item_id", "")),
                    _fmt(row.get("maximum_growth"), 0),
                    _fmt(row.get("price_coins"), 0),
                    f"{row.get('growth_per_coin_numerator', 0)}/{row.get('growth_per_coin_denominator', 1)}",
                    "Invariant" if row.get("growth_per_coin_is_speed_invariant") else "Varies",
                ])
            story.append(table(
                speed_data,
                widths=[2.2 * inch, 0.8 * inch, 0.7 * inch, 1.15 * inch, 1.45 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 5))
            story.append(Paragraph(
                f"Declared endgame scenario: {ENDGAME_SCENARIO_LABEL}; day-365 medians.",
                styles["Tiny"],
            ))
            story.append(Spacer(1, 3))
            endgame_growth_data = [[
                Paragraph("Cohort", styles["MicroHeader"]),
                Paragraph("Storage<br/>current", styles["MicroHeader"]),
                Paragraph("Storage<br/>lifetime", styles["MicroHeader"]),
                Paragraph(
                    "Landmark Growth<br/>tiers F / A / C",
                    styles["MicroHeader"],
                ),
                Paragraph(
                    "Mastery Growth<br/>ranks F / A / C",
                    styles["MicroHeader"],
                ),
                Paragraph("Legacy<br/>level / progress", styles["MicroHeader"]),
                Paragraph(
                    "Claimable<br/>Garden Coin need",
                    styles["MicroHeader"],
                ),
            ]]
            endgame_coin_data = [[
                Paragraph("Cohort", styles["MicroHeader"]),
                Paragraph("Gross<br/>Garden Coins", styles["MicroHeader"]),
                Paragraph("Spent<br/>Garden Coins", styles["MicroHeader"]),
                Paragraph("Remaining<br/>Garden Coins", styles["MicroHeader"]),
                Paragraph(
                    "Finite permanent Garden Coin demand remaining",
                    styles["MicroHeader"],
                ),
            ]]
            for cohort_id in ("headline", "heavy", "power"):
                endgame_rows = {
                    metric: _statistic(
                        report,
                        cohort_id=cohort_id,
                        strategy_id=ENDGAME_STRATEGY_ID,
                        case_id=ENDGAME_CASE_ID,
                        metric_id=metric,
                    )
                    for metric in (
                        "growth.stored_balance_units",
                        "growth.routed_to_storage_units_lifetime",
                        "catalog.finite_permanent_remaining_coins",
                        "landmarks.growth_funded_units",
                        "landmarks.tiers_funded",
                        "landmarks.tiers_claimable",
                        "landmarks.tiers_claimed",
                        "mastery.growth_funded_units",
                        "mastery.ranks_funded",
                        "mastery.ranks_claimable",
                        "mastery.ranks_claimed",
                        "legacy.level",
                        "legacy.progress_units",
                        "coins.required_for_claimable_content",
                        "coins.gross",
                        "coins.spent",
                        "coins.ending",
                    )
                }

                def endgame_value(metric: str, statistic: str = "p50") -> str:
                    row = endgame_rows[metric]
                    return _fmt(row.get(statistic) if row else None, 0)

                endgame_growth_data.append([
                    cohort_id.title(),
                    endgame_value("growth.stored_balance_units"),
                    endgame_value("growth.routed_to_storage_units_lifetime"),
                    Paragraph(
                        endgame_value("landmarks.growth_funded_units")
                        + "<br/>"
                        + " / ".join((
                            endgame_value("landmarks.tiers_funded"),
                            endgame_value("landmarks.tiers_claimable"),
                            endgame_value("landmarks.tiers_claimed"),
                        )),
                        styles["MicroCell"],
                    ),
                    Paragraph(
                        endgame_value("mastery.growth_funded_units")
                        + "<br/>"
                        + " / ".join((
                            endgame_value("mastery.ranks_funded"),
                            endgame_value("mastery.ranks_claimable"),
                            endgame_value("mastery.ranks_claimed"),
                        )),
                        styles["MicroCell"],
                    ),
                    Paragraph(
                        " / ".join((
                            endgame_value("legacy.level"),
                            endgame_value("legacy.progress_units"),
                        )),
                        styles["MicroCell"],
                    ),
                    endgame_value("coins.required_for_claimable_content"),
                ])
                endgame_coin_data.append([
                    cohort_id.title(),
                    endgame_value("coins.gross"),
                    endgame_value("coins.spent"),
                    endgame_value("coins.ending"),
                    endgame_value("catalog.finite_permanent_remaining_coins"),
                ])
            story.append(table(
                endgame_growth_data,
                widths=[0.65 * inch, 0.8 * inch, 0.85 * inch, 1.15 * inch,
                        1.15 * inch, 0.85 * inch, 0.85 * inch],
                micro=True,
            ))
            story.append(Paragraph(
                "F / A / C = funded, claimable, and claimed tier or rank counts. "
                "Landmark and Mastery Growth values are exact funded units.",
                styles["Tiny"],
            ))
            story.append(Spacer(1, 4))
            story.append(table(
                endgame_coin_data,
                widths=[0.9 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch,
                        2.1 * inch],
                micro=True,
            ))
            story.append(Spacer(1, 7))
        data = [headers]
        for row in representative_statistic_rows(report, metric_id):
            first = _fmt(row.get("reach_rate"), 2) if metric_id.endswith("completion_day") else _fmt(row.get("p10"))
            cohort_id = str(row.get("scenario_id", "")).partition(":")[0]
            data.append([
                cohort_id.replace("_", " ").title(),
                first,
                _fmt(row.get("p50")),
                _fmt(row.get("p90")),
            ])
        if len(data) == 1:
            data.append(["No modeled row", "-", "-", "-"])
        story.append(table(data, widths=[3.7 * inch, 0.85 * inch, 0.85 * inch, 0.85 * inch], tiny=True))
        story.append(Spacer(1, 9))
        units_note = (
            " Growth quantities use exact hundredth units; 100 units equal "
            "1 displayed Growth."
            if metric_id in {
                "growth.stored_balance_units",
                "growth.total_units",
                "growth.total_units_per_answer",
            }
            else ""
        )
        story.append(Paragraph(
            f"Metric: {metric_labels.get(metric_id, public_label(metric_id))}. "
            "Rows use the collection-first baseline for all "
            "six cohorts in scenario-matrix order. Values are paired across the "
            f"fixed seed manifest;{units_note} quantiles use the nearest-rank method.",
            styles["Small"],
        ))

    # Page 15: methodology and source manifest.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[14]))
    release_status = report.get("release_status", {})
    release_status = release_status if isinstance(release_status, Mapping) else {}
    story.append(table([
        ["Method field", "Frozen value"],
        ["Model", str(run.get("model", ""))],
        ["RNG", str(run.get("rng", ""))],
        ["Seed count", _fmt(run.get("seed_count"), 0)],
        ["Quantiles", str(run.get("quantiles", ""))],
        ["Catalog SHA-256", str(run.get("catalog_sha256", ""))],
        ["Run ID", str(run.get("run_id", ""))],
        ["Git commit", str(run.get("git_commit", ""))],
        [
            "Automated assertions",
            str(release_status.get("automated", {}).get("status", "not_run")),
        ],
        [
            "Modeled acceptance",
            str(release_status.get("modeled_acceptance", {}).get("status", "not_evaluated")),
        ],
        [
            "Production parity",
            str(release_status.get("production_parity", {}).get("status", "not_run")),
        ],
        [
            "Migration tests",
            str(release_status.get("migration_tests", {}).get("status", "not_run")),
        ],
        [
            "Native macOS smoke",
            str(release_status.get("native_macos_smoke", {}).get("status", "not_run")),
        ],
        [
            "Human review",
            str(release_status.get("human_review", {}).get("status", "pending")),
        ],
        [
            "macOS 100% text",
            str(release_status.get("platform_macos_100_percent_text", {}).get("status", "not_run")),
        ],
        [
            "Release ready",
            "YES" if release_status.get("release_ready") is True else "NO",
        ],
    ], widths=[1.45 * inch, 5.1 * inch], micro=True))
    story.append(Spacer(1, 6))

    def compact_assertion_value(value: Any) -> str:
        if isinstance(value, Mapping) or (
            isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        ):
            return "See JSON"
        text = _fmt(value, 0)
        return text if len(text) <= 10 else "See JSON"

    assertion_data = [["Assertion", "Status", "Observed", "Expected"]]
    for row in report.get("assertions", ()):
        assertion_data.append([
            str(row.get("assertion_id", "")),
            str(row.get("status", "")).upper(),
            compact_assertion_value(row.get("observed")),
            compact_assertion_value(row.get("expected")),
        ])
    story.append(table(
        assertion_data,
        widths=[3.8 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch],
        micro=True,
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Limitations: cohort schedules, completion patterns, purchase strategies, and "
        "session timing are modeled assumptions. Production trace parity status: "
        f"{str(report.get('parity', {}).get('status', 'not run')).replace('_', ' ')}. "
        "A report with parity not passed is explicitly blocked from release approval. "
        "Balance-target misses block release readiness through modeled acceptance "
        "without being simulator correctness failures. This analysis does not "
        "constitute release approval.",
        styles["Tiny"],
    ))

    doc.build(story, canvasmaker=InvariantCanvas)
    return output_path
