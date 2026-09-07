"""Small, explicitly scoped progression audit, independent of release gates.

The same single-scenario kernel supplies all arithmetic. This module selects
fewer users and days, summarizes coarse results, and writes review artifacts.
Opening states use production onboarding once; runs stay in the fast kernel.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import csv
import json
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Callable, Mapping, Sequence

from ankigarden.feature_availability import garden_legacy_enabled, growth_target_enabled, landmarks_enabled, mastery_enabled
from .catalog import CatalogFacts, canonical_json_bytes, load_catalog_facts, to_primitive
from .kernel import (
    _catalog_analysis, _environment_daily_value, _is_right_censored_timing_metric,
    _summarize_metric, simulate_scenario,
)
from .model import (
    APPROVED_COHORTS, APPROVED_STRATEGIES, DEFAULT_SEED_ROOT, CohortSpec,
    ScenarioSpec, SimulationConfig,
)


CHECKPOINTS = (7, 14, 30, 60, 90, 180)
METRICS = (
    "answers.total", "days.studied", "days.completed", "plants.full_bloom",
    "plants.first_full_bloom_day", "plants.all_catalog_full_bloom_day",
    "beds.owned", "catalog.functional_completion_day", "catalog.permanent_owned",
    "coins.gross", "coins.spent", "coins.ending", "finds.total",
    "environments.discovered", "growth.generated_units", "growth.shared_units",
    "growth.stored_balance_units", "consumables.growth_units",
    "environments.effect_growth_units", "environments.effect_coins",
)


@dataclass(frozen=True)
class QuickCase:
    scenario: ScenarioSpec
    seeds: int
    days: int
    group: str = "main"


def quick_cases(*, seeds: int | None = None, days: int | None = None) -> tuple[QuickCase, ...]:
    """An explicit override also shrinks the three spot checks for development."""
    if seeds is not None and seeds < 1:
        raise ValueError("seeds must be positive")
    if days is not None and days < 1:
        raise ValueError("days must be positive")
    strategies = {row.strategy_id: row for row in APPROVED_STRATEGIES}
    rows = []
    for cohort in APPROVED_COHORTS:
        if cohort.cards_per_study_day not in (100, 200, 400):
            continue
        for strategy in ("collection_first", "optimal_growth", "optimal_coin"):
            rows.append(QuickCase(ScenarioSpec(
                f"quick:{cohort.cohort_id}:{strategy}", cohort, strategies[strategy],
                rotate_completed_plants=True, starting_profile="fresh",
            ), seeds or 50, days or 180))
    for cohort, strategy, horizon, group, missed in (
        (CohortSpec("quick_light", 25, 6, 90), "collection_first", 90, "light", None),
        (CohortSpec("quick_inconsistent", 200, 7, 80), "collection_first", 180, "inconsistent", 15),
        (CohortSpec("quick_stress", 1000, 7, 100), "optimal_growth", 30, "stress", None),
    ):
        rows.append(QuickCase(ScenarioSpec(
            f"quick:{cohort.cohort_id}:{strategy}", cohort, strategies[strategy],
            missed_week_start_day=missed, rotate_completed_plants=True, starting_profile="fresh",
        ), min(seeds, 25) if seeds is not None else 25,
            min(days, horizon) if days is not None else horizon, group))
    for answers in (200, 400):
        cohort = CohortSpec(f"established_{answers}", answers, 7, 100)
        rows.append(QuickCase(ScenarioSpec(
            f"quick:{cohort.cohort_id}:collection_first", cohort, strategies["collection_first"],
            rotate_completed_plants=True, starting_profile="established",
        ), min(seeds, 25) if seeds is not None else 25,
            min(days, 30) if days is not None else 30, "established"))
    return tuple(rows)


def source_manifest(root: Path) -> dict:
    files = set((root / "ankigarden").rglob("*.py"))
    files.update((root / "scripts/balance_analysis").glob("*.py"))
    files.update(root / path for path in (
        "scripts/simulate_balance_profiles.py", "scripts/run_balance_engine_parity.py",
        "ankigarden/config.json", "ankigarden/manifest.json",
    ))
    hashes = {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
              for path in sorted(files) if path.is_file() and "user_files" not in path.parts}
    result = {"source_hashes": hashes, "source_sha256": sha256(canonical_json_bytes(hashes)).hexdigest()}
    try:
        result["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        result["git_commit"] = None
    return result


def _run_case(case: QuickCase, facts: CatalogFacts) -> dict:
    started = perf_counter()
    checkpoints = tuple(sorted({day for day in CHECKPOINTS if day <= case.days} | {case.days}))
    config = SimulationConfig(seeds=case.seeds, days=case.days,
                              seed_root=DEFAULT_SEED_ROOT, checkpoint_days=checkpoints)
    samples = {day: [] for day in checkpoints}
    choices = {day: [] for day in checkpoints}
    for seed in range(case.seeds):
        outcome = simulate_scenario(facts, case.scenario, config, seed, capture_choices=True)
        if outcome.assertion_failures:
            raise AssertionError(f"{case.scenario.scenario_id}, seed {seed}: {outcome.assertion_failures}")
        for day in checkpoints:
            samples[day].append({metric: outcome.checkpoints[day][metric] for metric in METRICS})
            choices[day].append(outcome.checkpoint_choices[day])
    statistics = []
    for day, population in samples.items():
        for metric in METRICS:
            summary = _summarize_metric(
                [row[metric] for row in population], total_n=case.seeds,
                right_censored=_is_right_censored_timing_metric(metric),
            )
            statistics.append({
                "checkpoint_day": day, "metric_id": metric,
                **{key: summary[key] for key in ("n", "reached_n", "min", "p10", "p50", "p90", "max")},
            })
    completion = "plants.all_catalog_full_bloom_day"
    final = samples[case.days]
    day30 = samples.get(30)
    return {
        "scenario_id": case.scenario.scenario_id, "group": case.group,
        "scenario": asdict(case.scenario), "seeds": case.seeds, "days": case.days,
        "runtime_seconds": round(perf_counter() - started, 4),
        "completed_by_day30": None if day30 is None else sum(
            row[completion] is not None and row[completion] <= 30 for row in day30),
        "borderline_seed_indices": [seed for seed, row in enumerate(final)
                                    if row[completion] is not None and 25 <= row[completion] <= 35],
        "statistics": statistics, "samples": samples, "choices": choices,
        "accounting_assertions": "pass",
    }


_WORKER_FACTS: CatalogFacts | None = None


def _initialize_worker() -> None:
    global _WORKER_FACTS
    _WORKER_FACTS = load_catalog_facts()


def _run_worker(case: QuickCase) -> dict:
    assert _WORKER_FACTS is not None
    return _run_case(case, _WORKER_FACTS)


def run_quick_audit(
    *, cases: Sequence[QuickCase] | None = None, seeds: int | None = None,
    days: int | None = None, workers: int = 1, facts: CatalogFacts | None = None,
    progress: Callable[[str], None] | None = None,
    repository_root: Path | None = None,
) -> dict:
    """Run exactly the selected cases, including cohorts absent from release mode.

    Passing alternate immutable CatalogFacts supports small paired candidate
    comparisons without changing the runtime catalog. These run in one process.
    """
    started = perf_counter()
    selected = tuple(quick_cases(seeds=seeds, days=days) if cases is None else cases)
    if not selected or len({c.scenario.scenario_id for c in selected}) != len(selected):
        raise ValueError("quick audit requires nonempty, unique scenario IDs")
    if workers < 1 or any(c.seeds < 1 or c.days < 1 for c in selected):
        raise ValueError("workers, seeds, and days must be positive")
    root = repository_root or Path(__file__).resolve().parents[2]
    before = source_manifest(root)
    supplied_facts = facts is not None
    catalog = facts or load_catalog_facts()
    from .opening import production_opening
    selected = tuple(replace(case, scenario=replace(
        case.scenario, opening=production_opening(case.scenario.starting_profile),
    )) if case.scenario.opening is None and case.scenario.starting_profile != "legacy"
        else case for case in selected)
    results = []
    if workers > 1 and not supplied_facts:
        with ProcessPoolExecutor(max_workers=min(workers, len(selected)), initializer=_initialize_worker) as pool:
            for result in pool.map(_run_worker, selected):
                results.append(result)
                if progress:
                    progress(f"{result['scenario_id']}: {result['seeds']} seeds, {result['runtime_seconds']:.1f}s")
    else:
        for case in selected:
            result = _run_case(case, catalog)
            results.append(result)
            if progress:
                progress(f"{result['scenario_id']}: {result['seeds']} seeds, {result['runtime_seconds']:.1f}s")
    if source_manifest(root)["source_sha256"] != before["source_sha256"]:
        raise RuntimeError("Audit sources changed during simulation; rerun from a frozen source copy.")
    report = {
        "schema": "anki-garden-quick-audit-v1", "mode": "quick_audit",
        "source": before, "catalog_sha256": catalog.snapshot_sha256,
        "effective_facts_sha256": sha256(canonical_json_bytes({
            key: to_primitive(value) for key, value in vars(catalog).items()
            if key != "daily_cap_resolver"
        })).hexdigest(),
        "catalog": catalog.snapshot,
        "assumptions": [
            "Eligible answers, not distinct cards; Anki completion follows the configured schedule.",
            "Fresh starts include production welcome rewards. Established starts include the 100,000-review/365-day historical fixture; answer totals include those opening reviews.",
            "Purchases and equipment selections occur at day end. Owned seedlings replace Full Blooms once per day.",
            "Growth/Coin strategies are heuristics, not mathematically optimal policies; no within-session switching is simulated.",
            "Random Finds are paired by cohort and seed and batched daily; event-level parity is checked separately.",
            "Small samples support broad pacing judgments, not rare-tail guarantees or proof that no user can finish early.",
            "Unreached milestones remain beyond the observed horizon; medians include all seeds, not only finishers.",
        ],
        "availability": {"landmarks_enabled": landmarks_enabled(),
                         "mastery_enabled": mastery_enabled(),
                         "garden_legacy_enabled": garden_legacy_enabled(),
                         "legacy_reachable_for_fresh_save": landmarks_enabled() and mastery_enabled() and garden_legacy_enabled()},
        "scenarios": results,
        "direct_analysis": _catalog_analysis(replace(catalog, purchase_options=tuple(
            replace(option, available=False)
            if not growth_target_enabled(option.category) else option
            for option in catalog.purchase_options))),
        "item_value_rows": item_value_rows(catalog),
        "runtime_seconds": round(perf_counter() - started, 4),
        "scenario_days": sum(c.seeds * c.days for c in selected),
        "validation": {"accounting": "pass", "production_engine_checks": "not_run",
                       "full_release_matrix": "not_run", "native_ui": "not_run"},
    }
    return report


def item_value_rows(facts: CatalogFacts) -> list[dict]:
    rows = []
    for item in facts.consumables:
        rows.append({"item_id": item.consumable_id, "kind": "consumable",
                     "price_coins": item.price_coins,
                     "growth_per_dose": item.maximum_growth,
                     "growth_per_coin": item.maximum_growth / item.price_coins if item.price_coins else None,
                     "note": "Primary Growth only; Fertilizer/Booster also receive occupied-bed Shared Growth."})
    options = {item.item_id: item for item in facts.purchase_options}
    for item_id in facts.effects_by_item_id:
        option = options.get(item_id)
        for answers in (25, 100, 200, 400):
            scenario = ScenarioSpec("value", CohortSpec("value", answers, 7, 100), APPROVED_STRATEGIES[0])
            growth, coins = _environment_daily_value(facts, item_id, scenario)
            rows.append({"item_id": item_id, "kind": "equipment", "answers": answers,
                         "price_coins": option.price_coins if option else None,
                         "daily_growth_equivalent": float(growth), "daily_coins": float(coins),
                         "note": "Steady active use with daily completion; excludes Shared Growth, milestone percentages and activation-only interactions."})
    return rows


def _stat(case: Mapping, metric: str, day: int | None = None) -> Mapping:
    return next(row for row in case["statistics"]
                if row["metric_id"] == metric and row["checkpoint_day"] == (day or case["days"]))


def _number(value: object, *, horizon: int | None = None) -> str:
    if value is None:
        return f">{horizon}" if horizon is not None else "—"
    return f"{float(value):,.0f}"


def markdown_report(report: Mapping) -> str:
    lines = ["# Anki Garden quick progression audit", "",
             "Targets: enjoyable, useful rewards; meaningful progression beyond the first month; "
             "preserve current pacing, including about 55 days at 400 answers/day. Slightly strong choices are acceptable.", "",
             f"Computed {report['scenario_days']:,} scenario-days in {report['runtime_seconds']:.1f} seconds. "
             "This is a small-sample audit, not release acceptance.", "",
             "## Progression results", "",
             "Full Bloom timing is calendar days from a fresh start. `>N` means the population median "
             "was not reached within N days; it is not an estimate of eventual completion.", "",
             "| Answers/day | Strategy | Seeds / days | Full Blooms at day 30 | First Full Bloom median | All ten median | Paid catalog median | Day-30 finishers |",
             "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for case in report["scenarios"]:
        horizon = case["days"]
        strategy = {"optimal_growth": "Growth spending", "optimal_coin": "Coin focused"}.get(
            case["scenario"]["strategy"]["strategy_id"], case["scenario"]["strategy"]["label"])
        cohort = case["scenario"]["cohort"]
        label = strategy if case["group"] == "main" else f"{strategy} ({case['group']})"
        day30 = next((row for row in case["statistics"] if row["checkpoint_day"] == 30
                      and row["metric_id"] == "plants.full_bloom"), {})
        lines.append(f"| {cohort['cards_per_study_day']} | {label} | {case['seeds']} / {horizon} | "
                     f"{_number(day30.get('p50'))} | "
                     f"{_number(_stat(case, 'plants.first_full_bloom_day')['p50'], horizon=horizon)} | "
                     f"{_number(_stat(case, 'plants.all_catalog_full_bloom_day')['p50'], horizon=horizon)} | "
                     f"{_number(_stat(case, 'catalog.functional_completion_day')['p50'], horizon=horizon)} | "
                     f"{_number(case['completed_by_day30'])}/{case['seeds']} |")
    lines.extend(["", "Paid catalog timing covers available paid plants, scenery, and Garden Bonuses. "
                  "Beds are earned. Mastery and rare discoveries do not delay the all-ten metric.", "",
                  "## Observations", ""])
    protected = [case for case in report["scenarios"] if case["group"] == "main"]
    observed = sum(case["completed_by_day30"] or 0 for case in protected)
    covered = sum(case["seeds"] for case in protected if case["completed_by_day30"] is not None)
    lines.append(f"- First-month core completion: {observed}/{covered} modeled main-audience users. "
                 "These are paired scenario outcomes, not independent sampled people.")
    for case in protected:
        timing = _stat(case, "plants.all_catalog_full_bloom_day")
        if timing["p50"] is None:
            lines.append(f"- {case['scenario_id']}: the all-ten median remains beyond day {case['days']}; "
                         f"median {_number(_stat(case, 'plants.full_bloom')['p50'])} Full Blooms at the horizon.")
    borderline = [case["scenario_id"] for case in report["scenarios"] if case["borderline_seed_indices"]]
    if borderline:
        lines.append("- Completion results between days 25 and 35 merit a targeted 200-seed rerun: " + ", ".join(borderline) + ".")
    lines.extend(["", "## Equipment and supplies", "",
                  "Values below compare a completed 100-answer day. Growth equivalents include the base value "
                  "of consumable gifts, amortized across their cadence. They exclude milestone multipliers, "
                  "Booster activation extensions, and Shared Growth; those interactions need separate judgment.", "",
                  "| Item | Price | Growth per dose / completed 100-answer day | Coins/day |",
                  "|---|---:|---:|---:|"])
    for row in report["item_value_rows"]:
        if row["kind"] == "equipment" and row["answers"] != 100:
            continue
        growth = row.get("growth_per_dose", row.get("daily_growth_equivalent"))
        lines.append(f"| {row['item_id']} | {_number(row['price_coins'])} | "
                     f"{float(growth):g} | {_number(row.get('daily_coins'))} |")
    lines.extend(["", "## Equipped items and scaling achievements", "",
                  "Items below are equipped at the final checkpoint, not merely owned. Counts show "
                  "how many simulated users selected each item. Achievement Coins and bed unlocks are "
                  "included in progression; permanent trophy effects activate only after earning them.", "",
                  "| Scenario | Decorations | Scenery | Active trophies |", "|---|---|---|---|"])
    for case in report["scenarios"]:
        choices = case["choices"].get(case["days"], case["choices"].get(str(case["days"]), []))
        counts = [Counter(row[slot] for row in choices) for slot in ("decoration", "scenery")]
        counts.append(Counter(trophy for row in choices for trophy in row["active_trophies"]))
        cells = [", ".join(f"{item}: {count}" for item, count in sorted(counter.items())) or "None"
                 for counter in counts]
        lines.append(f"| {case['scenario_id']} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Method and limits", ""])
    lines.extend("- " + assumption for assumption in report["assumptions"])
    lines.extend(["- Disabled Landmarks are excluded from longevity. Garden Legacy remains unavailable "
                  "to a fresh save while its Landmark prerequisite cannot be funded.",
                  "- Trophy effects are included when earned. Long-term Mastery and discovery guarantees "
                  "are available in the direct-analysis JSON; they are not treated as first-month content.",
                  f"- Validation: {json.dumps(report['validation'], sort_keys=True)}.",
                  f"- Catalog SHA-256: `{report['catalog_sha256']}`.",
                  f"- Source SHA-256: `{report['source']['source_sha256']}`.", ""])
    return "\n".join(lines)


def write_quick_artifacts(report: Mapping, output_dir: Path) -> Mapping[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"report": output_dir / "quick-audit.md", "json": output_dir / "quick-audit.json",
             "statistics": output_dir / "quick-statistics.csv", "items": output_dir / "quick-items.csv"}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("Audit output already exists; choose a fresh output directory.")
    paths["json"].write_text(json.dumps(to_primitive(report), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    paths["report"].write_text(markdown_report(report), encoding="utf-8")
    rows = [{"scenario_id": case["scenario_id"], **row}
            for case in report["scenarios"] for row in case["statistics"]]
    for key, values in (("statistics", rows), ("items", report["item_value_rows"])):
        fields = list(dict.fromkeys(field for row in values for field in row))
        with paths[key].open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    return paths
