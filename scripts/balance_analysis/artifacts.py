from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .catalog import canonical_json_bytes, to_primitive


JSON_FILENAME = "anki-garden-economy-analysis.json"
CATALOG_CSV_FILENAME = "catalog_items.csv"
STATISTICS_CSV_FILENAME = "balance_statistics.csv"
MILESTONES_CSV_FILENAME = "balance_milestones.csv"
FINDINGS_CSV_FILENAME = "balance_findings.csv"
ANALYSIS_CSV_FILENAME = "economy_analysis_companion.csv"


STATISTIC_FIELDS = (
    "run_id",
    "catalog_sha256",
    "scenario_id",
    "strategy_id",
    "case_id",
    "checkpoint_day",
    "metric_id",
    "unit",
    "estimator",
    "population_scope",
    "censoring",
    "n",
    "reached_n",
    "reach_rate",
    "censored_n",
    "censoring_rate",
    "population_percentile_method",
    "mean",
    "sd",
    "se",
    "ci95_low",
    "ci95_high",
    "min",
    "p10",
    "p50",
    "p90",
    "p99",
    "max",
    "conditional_reacher_population_scope",
    "conditional_reacher_mean",
    "conditional_reacher_sd",
    "conditional_reacher_se",
    "conditional_reacher_ci95_low",
    "conditional_reacher_ci95_high",
    "conditional_reacher_min",
    "conditional_reacher_p10",
    "conditional_reacher_p50",
    "conditional_reacher_p90",
    "conditional_reacher_p99",
    "conditional_reacher_max",
    "pooled_total",
)

CATALOG_FIELDS = (
    "catalog_sha256",
    "category",
    "item_id",
    "name",
    "rarity",
    "acquisition",
    "status",
    "price_coins",
    "repeatable",
    "earn_source",
    "effect_id",
    "trigger",
    "value_kind",
    "amount",
    "amount_units",
    "first_cards",
    "every_nth_card",
    "every_nth_completion",
    "inventory_item_id",
    "weight_percent",
    "definition_json",
)

MILESTONE_FIELDS = (
    "run_id",
    "catalog_sha256",
    "scenario_id",
    "strategy_id",
    "case_id",
    "item_id",
    "event_id",
    "unit",
    "n",
    "reach_rate",
    "mean",
    "p10",
    "p50",
    "p90",
    "p99",
    "max",
)

FINDING_FIELDS = (
    "run_id",
    "finding_id",
    "severity",
    "status",
    "domain",
    "title",
    "metric_refs",
    "threshold",
    "observed",
    "interpretation",
    "caveat",
)

ANALYSIS_FIELDS = (
    "run_id",
    "catalog_sha256",
    "record_type",
    "scenario_id",
    "strategy_id",
    "case_id",
    "checkpoint_day",
    "item_id",
    "source_id",
    "family_id",
    "metric_id",
    "unit",
    "statistic",
    "value",
    "status",
    "details_json",
)


ANALYSIS_SOURCE_PATHS = (
    "ankigarden/balance_catalog.py",
    "ankigarden/game.py",
    "ankigarden/feature_availability.py",
    "scripts/simulate_balance_profiles.py",
    "scripts/shard_balance_profiles.py",
    "scripts/build_balance_report.py",
    "scripts/run_balance_engine_parity.py",
    "scripts/balance_analysis/annual_parity.py",
    "scripts/balance_analysis/catalog.py",
    "scripts/balance_analysis/kernel.py",
    "scripts/balance_analysis/model.py",
    "scripts/balance_analysis/artifacts.py",
    "scripts/balance_analysis/report.py",
    "scripts/balance_analysis/shards.py",
    "scripts/balance_analysis/trace.py",
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analysis_source_hashes(repository_root: Path) -> Mapping[str, str]:
    """Hash the frozen source set used by collection, merge, and reporting."""

    return {
        relative_path: _sha256_file(repository_root / relative_path)
        for relative_path in ANALYSIS_SOURCE_PATHS
        if (repository_root / relative_path).is_file()
    }


def _git_commit(repository_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repository_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _git_dirty_paths(repository_root: Path) -> Sequence[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=str(repository_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ()
    return tuple(sorted(
        line[3:] for line in result.stdout.splitlines()
        if len(line) >= 4
    ))


def finalize_report(
    report: Mapping[str, Any],
    *,
    repository_root: Path,
) -> Mapping[str, Any]:
    """Attach reproducible provenance and a content-derived run ID."""

    result: MutableMapping[str, Any] = deepcopy(dict(report))
    sources = analysis_source_hashes(repository_root)
    run = dict(result.get("run", {}))
    epoch = max(0, int(run.get("source_date_epoch", 0) or 0))
    dirty_paths = set(_git_dirty_paths(repository_root))
    run.update({
        "git_commit": _git_commit(repository_root),
        # Limit provenance to the frozen source manifest. Output artifacts or
        # unrelated user changes cannot perturb the content-derived run ID.
        "dirty_paths": sorted(path for path in dirty_paths if path in sources),
        "source_files": sources,
        "generated_at_utc": datetime.fromtimestamp(
            epoch, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
    })
    result["run"] = run
    payload_without_id = deepcopy(result)
    payload_without_id["run"].pop("run_id", None)
    run["run_id"] = sha256(canonical_json_bytes(payload_without_id)).hexdigest()
    return to_primitive(result)


def canonical_json_text(report: Mapping[str, Any]) -> str:
    return json.dumps(
        to_primitive(report),
        ensure_ascii=True,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: row.get(field, "")
                for field in fieldnames
            })


def _common_definition(definition: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in definition:
            return definition[name]
    return ""


def _effect_rows(record: Mapping[str, Any], catalog_sha256: str) -> Sequence[Mapping[str, Any]]:
    definition = record.get("definition", {})
    if not isinstance(definition, Mapping):
        definition = {}
    effects = definition.get("effects") or definition.get("effect_definitions") or ()
    if not isinstance(effects, Sequence) or isinstance(effects, (str, bytes)):
        effects = ()
    if not effects:
        effects = ({},)
    rows = []
    for effect in effects:
        effect = effect if isinstance(effect, Mapping) else {}
        weighted = effect.get("weighted_grants") or effect.get("weighted_rewards") or ()
        if not isinstance(weighted, Sequence) or isinstance(weighted, (str, bytes)):
            weighted = ()
        outcomes = weighted or ({},)
        for outcome in outcomes:
            outcome = outcome if isinstance(outcome, Mapping) else {}
            grant = outcome.get("grant") if outcome else effect.get("grant")
            grant = grant if isinstance(grant, Mapping) else {}
            cadence = effect.get("cadence")
            cadence = cadence if isinstance(cadence, Mapping) else {}
            price = _common_definition(
                definition,
                "price_coins",
                "cost_coins",
                "price",
                "unlock_cost",
                "coin_cost",
            )
            rows.append({
                "catalog_sha256": catalog_sha256,
                "category": record.get("category", ""),
                "item_id": record.get("item_id", ""),
                "name": _common_definition(definition, "name", "display_name", "label"),
                "rarity": _common_definition(definition, "rarity", "tier"),
                "acquisition": _common_definition(definition, "acquisition", "source_kind"),
                "status": _common_definition(definition, "status", "availability"),
                "price_coins": price,
                "repeatable": _common_definition(definition, "repeatable"),
                "earn_source": _common_definition(definition, "earn_source", "how_to_earn"),
                "effect_id": _common_definition(effect, "effect_id", "id"),
                "trigger": _common_definition(effect, "trigger"),
                "value_kind": _common_definition(grant or effect, "value_kind", "kind"),
                "amount": _common_definition(grant or effect, "amount"),
                "amount_units": _common_definition(effect, "amount_units"),
                "first_cards": _common_definition(
                    cadence or effect, "first_n_per_day", "first_cards"
                ),
                "every_nth_card": _common_definition(
                    cadence or effect, "every_n", "every_nth_card"
                ) if str(effect.get("trigger", "")) == "eligible_card" else "",
                "every_nth_completion": _common_definition(
                    cadence or effect, "every_n", "every_nth_completion"
                ) if str(effect.get("trigger", "")) == "valid_completion" else "",
                "inventory_item_id": _common_definition(
                    grant or outcome or effect,
                    "inventory_item_id",
                    "item_id",
                ),
                "weight_percent": _common_definition(
                    outcome,
                    "weight_percent",
                    "weight",
                ),
                "definition_json": json.dumps(
                    definition,
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            })
    return rows


def write_artifacts(
    report: Mapping[str, Any],
    output_directory: Path,
) -> Mapping[str, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    run_id = str(report["run"]["run_id"])
    catalog_sha256 = str(report["catalog"]["sha256"])

    json_path = output_directory / JSON_FILENAME
    json_path.write_text(canonical_json_text(report), encoding="utf-8")

    catalog_path = output_directory / CATALOG_CSV_FILENAME
    catalog_rows = []
    for record in report["catalog"]["records"]:
        catalog_rows.extend(_effect_rows(record, catalog_sha256))
    _write_csv(catalog_path, CATALOG_FIELDS, catalog_rows)

    statistics_path = output_directory / STATISTICS_CSV_FILENAME
    statistic_rows = [
        {"run_id": run_id, "catalog_sha256": catalog_sha256, **row}
        for row in report["statistics"]
    ]
    _write_csv(statistics_path, STATISTIC_FIELDS, statistic_rows)

    milestone_path = output_directory / MILESTONES_CSV_FILENAME
    milestone_rows = []
    for row in report["milestones"]:
        metric_id = row.get("metric_id", "")
        item_id = {
            "catalog.completion_day": "permanent_catalog",
            "plants.first_full_bloom_day": "first_plant",
            "plants.all_catalog_full_bloom_day": "all_catalog_plants",
        }.get(metric_id, "")
        milestone_rows.append({
            "run_id": run_id,
            "catalog_sha256": catalog_sha256,
            "scenario_id": row.get("scenario_id", ""),
            "strategy_id": row.get("strategy_id", ""),
            "case_id": row.get("case_id", ""),
            "item_id": row.get("item_id", item_id),
            "event_id": row.get("event_id", metric_id),
            "unit": row.get("unit", ""),
            "n": row.get("n", ""),
            "reach_rate": row.get("reach_rate", ""),
            "mean": row.get("mean", ""),
            "p10": row.get("p10", ""),
            "p50": row.get("p50", ""),
            "p90": row.get("p90", ""),
            "p99": row.get("p99", ""),
            "max": row.get("max", ""),
        })
    _write_csv(milestone_path, MILESTONE_FIELDS, milestone_rows)

    findings_path = output_directory / FINDINGS_CSV_FILENAME
    finding_rows = [
        {
            "run_id": run_id,
            **row,
            "metric_refs": "|".join(row.get("metric_refs", ())),
        }
        for row in report["findings"]
    ]
    _write_csv(findings_path, FINDING_FIELDS, finding_rows)

    analysis_path = output_directory / ANALYSIS_CSV_FILENAME
    analysis_rows = []
    for row in report["statistics"]:
        metric_id = str(row.get("metric_id", ""))
        item_id = ""
        if metric_id.startswith("consumables."):
            parts = metric_id.split(".")
            item_id = parts[1] if len(parts) > 2 else ""
        elif metric_id.startswith("environments."):
            parts = metric_id.split(".")
            item_id = parts[1] if len(parts) > 2 else ""
        statistic_names = (
            "p10", "p50", "p90", "p99", "mean", "reach_rate",
        )
        if row.get("censoring") != "none":
            statistic_names = (*statistic_names, "censoring_rate")
        timing_details = {
            key: row.get(key, "")
            for key in (
                "censored_n",
                "censoring_rate",
                "population_percentile_method",
                "conditional_reacher_population_scope",
                "conditional_reacher_mean",
                "conditional_reacher_sd",
                "conditional_reacher_se",
                "conditional_reacher_ci95_low",
                "conditional_reacher_ci95_high",
                "conditional_reacher_min",
                "conditional_reacher_p10",
                "conditional_reacher_p50",
                "conditional_reacher_p90",
                "conditional_reacher_p99",
                "conditional_reacher_max",
            )
            if key in row
        }
        for statistic in statistic_names:
            analysis_rows.append({
                "run_id": run_id,
                "catalog_sha256": catalog_sha256,
                "record_type": "statistic",
                "scenario_id": row.get("scenario_id", ""),
                "strategy_id": row.get("strategy_id", ""),
                "case_id": row.get("case_id", ""),
                "checkpoint_day": row.get("checkpoint_day", ""),
                "item_id": item_id,
                "metric_id": metric_id,
                "unit": row.get("unit", ""),
                "statistic": statistic,
                "value": row.get(statistic, ""),
                "details_json": json.dumps({
                    "population_scope": row.get("population_scope", ""),
                    "censoring": row.get("censoring", "none"),
                    **timing_details,
                }, sort_keys=True, separators=(",", ":")),
            })
    for row in report.get("coin_concentration", ()):
        common = {
            "run_id": run_id,
            "catalog_sha256": catalog_sha256,
            "scenario_id": row.get("scenario_id", ""),
            "strategy_id": row.get("strategy_id", ""),
            "case_id": row.get("case_id", ""),
            "checkpoint_day": row.get("checkpoint_day", ""),
            "unit": "ratio",
        }
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.ledger_source_hhi",
            "statistic": "pooled",
            "value": row.get("ledger_source_hhi", ""),
            "details_json": json.dumps({
                "numerator": row.get("ledger_source_hhi_numerator", ""),
                "denominator": row.get("ledger_source_hhi_denominator", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.behavioral_family_hhi",
            "statistic": "pooled",
            "value": row.get("behavioral_family_hhi", ""),
            "details_json": json.dumps({
                "numerator": row.get("behavioral_family_hhi_numerator", ""),
                "denominator": row.get("behavioral_family_hhi_denominator", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.top_source_share",
            "statistic": "pooled",
            "value": row.get("top_source_share", ""),
            "details_json": json.dumps({
                "source_id": row.get("top_source_id", ""),
                "numerator": row.get("top_source_share_numerator", ""),
                "denominator": row.get("top_source_share_denominator", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.completion_family_share",
            "statistic": "pooled",
            "value": row.get("completion_family_share", ""),
            "details_json": json.dumps({
                "numerator": row.get("completion_family_share_numerator", ""),
                "denominator": row.get("completion_family_share_denominator", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.gross_without_completion_rewards",
            "unit": "coins",
            "statistic": "pooled",
            "value": row.get("gross_without_completion_rewards", ""),
            "details_json": json.dumps({
                "numerator": row.get("gross_without_completion_rewards", ""),
                "denominator": row.get("gross_coins_pooled", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        analysis_rows.append({
            **common,
            "record_type": "coin_concentration",
            "metric_id": "coins.gross_without_completion_share",
            "statistic": "pooled",
            "value": row.get("gross_without_completion_share", ""),
            "details_json": json.dumps({
                "numerator": row.get("gross_without_completion_rewards", ""),
                "denominator": row.get("gross_coins_pooled", ""),
            }, sort_keys=True, separators=(",", ":")),
        })
        for source_id, share in row.get("source_shares", {}).items():
            analysis_rows.append({
                **common,
                "record_type": "coin_source_share",
                "source_id": source_id,
                "metric_id": "coins.source_share",
                "statistic": "pooled",
                "value": share,
                "details_json": json.dumps({
                    "numerator": row.get("source_totals", {}).get(source_id, ""),
                    "denominator": row.get("gross_coins_pooled", ""),
                }, sort_keys=True, separators=(",", ":")),
            })
        for family_id, share in row.get("behavioral_family_shares", {}).items():
            analysis_rows.append({
                **common,
                "record_type": "coin_family_share",
                "family_id": family_id,
                "metric_id": "coins.behavioral_family_share",
                "statistic": "pooled",
                "value": share,
                "details_json": json.dumps({
                    "numerator": row.get("behavioral_family_totals", {}).get(
                        family_id, ""
                    ),
                    "denominator": row.get("gross_coins_pooled", ""),
                }, sort_keys=True, separators=(",", ":")),
            })
    for row in report.get("assertions", ()):
        analysis_rows.append({
            "run_id": run_id,
            "catalog_sha256": catalog_sha256,
            "record_type": "assertion",
            "metric_id": row.get("assertion_id", ""),
            "status": row.get("status", ""),
            "value": row.get("observed", ""),
            "details_json": json.dumps(
                {"expected": row.get("expected", "")},
                sort_keys=True,
                separators=(",", ":"),
            ),
        })
    release_status = report.get("release_status", {})
    if isinstance(release_status, Mapping):
        for gate_id, gate in sorted(release_status.items()):
            if not isinstance(gate, Mapping):
                continue
            details = dict(gate)
            if gate_id == "production_parity":
                parity = report.get("parity", {})
                if isinstance(parity, Mapping):
                    details["parity_evidence"] = dict(parity)
            analysis_rows.append({
                "run_id": run_id,
                "catalog_sha256": catalog_sha256,
                "record_type": "release_gate",
                "metric_id": f"release_status.{gate_id}",
                "status": gate.get("status", ""),
                "value": gate.get("status", ""),
                "details_json": json.dumps(
                    details,
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            })
        analysis_rows.append({
            "run_id": run_id,
            "catalog_sha256": catalog_sha256,
            "record_type": "release_readiness",
            "metric_id": "release_status.release_ready",
            "status": (
                "pass" if release_status.get("release_ready") is True
                else "blocked"
            ),
            "value": bool(release_status.get("release_ready") is True),
            "details_json": json.dumps({
                "blocking_gates": list(
                    release_status.get("blocking_gates", ())
                ),
            }, sort_keys=True, separators=(",", ":")),
        })
    _write_csv(analysis_path, ANALYSIS_FIELDS, analysis_rows)
    return {
        "json": json_path,
        "catalog_csv": catalog_path,
        "statistics_csv": statistics_path,
        "milestones_csv": milestone_path,
        "findings_csv": findings_path,
        "analysis_csv": analysis_path,
    }


def load_frozen_report(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError("balance report JSON must be an object")
    return value
