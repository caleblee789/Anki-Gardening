#!/usr/bin/env python3
from __future__ import annotations

"""Run the catalog-driven Anki Garden economy simulation.

The release lane uses 10,000 paired seeds. Tests call :func:`simulate_profiles`
with a small explicit seed count; they never silently reduce the CLI default.
"""

import argparse
import os
from pathlib import Path
import sys
from typing import Optional, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from scripts.balance_analysis.artifacts import (
    canonical_json_text,
    finalize_report,
    write_artifacts,
)
from scripts.balance_analysis.catalog import load_catalog_facts, validate_runtime_catalog
from scripts.balance_analysis.kernel import simulate_balance
from scripts.balance_analysis.model import (
    DEFAULT_DAYS,
    DEFAULT_SEED_COUNT,
    DEFAULT_SEED_ROOT,
    SimulationConfig,
    approved_scenarios,
)


def _checkpoints(days: int) -> tuple:
    values = [value for value in (7, 30, 90, 365) if value <= days]
    if days not in values:
        values.append(days)
    return tuple(sorted(set(values)))


def simulation_config(
    *,
    seeds: int,
    days: int = DEFAULT_DAYS,
    seed_root: str = DEFAULT_SEED_ROOT,
    source_date_epoch: int = 0,
) -> SimulationConfig:
    return SimulationConfig(
        seeds=int(seeds),
        days=int(days),
        seed_root=str(seed_root),
        checkpoint_days=_checkpoints(int(days)),
        source_date_epoch=max(0, int(source_date_epoch)),
    )


def simulate_profiles(
    *,
    seeds: int = 4,
    days: int = DEFAULT_DAYS,
    seed_root: str = DEFAULT_SEED_ROOT,
    source_date_epoch: int = 0,
    finalize: bool = False,
    workers: int = 1,
):
    """Run all approved cohorts, strategies, and edge cases.

    The small Python API default is intentional for unit tests. The CLI default
    remains the approved 10,000 seeds and is asserted independently.
    """

    config = simulation_config(
        seeds=seeds,
        days=days,
        seed_root=seed_root,
        source_date_epoch=source_date_epoch,
    )
    worker_count = max(1, int(workers))
    report = (
        simulate_balance(config, facts=load_catalog_facts(), workers=1)
        if worker_count == 1
        else simulate_balance(config, workers=worker_count)
    )
    return (
        finalize_report(report, repository_root=REPOSITORY_ROOT)
        if finalize else report
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=int,
        default=DEFAULT_SEED_COUNT,
        help="Paired seed count (release default: 10000).",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help=(
            "Process count (0 selects 1 for small runs and up to 8 for the "
            "10,000-seed release run)."
        ),
    )
    parser.add_argument("--seed-root", default=DEFAULT_SEED_ROOT)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0") or 0),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write canonical JSON and CSV evidence to this directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print canonical JSON to stdout instead of the compact summary.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the pure runtime catalog and exit without simulating.",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print approved scenario IDs and exit.",
    )
    return parser


def _summary(report) -> str:
    run = report["run"]
    scenario_count = len(report["scenario_matrix"]["scenarios"])
    return "\n".join((
        "Anki Garden economy analysis configured",
        f"  seeds: {int(run['seed_count']):,}",
        f"  days: {int(run['days']):,}",
        f"  scenarios: {scenario_count:,}",
        f"  catalog: {run['catalog_sha256']}",
        f"  run: {run.get('run_id', 'not finalized')}",
        f"  assertions: {len(report['assertions'])} passed",
    )) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_scenarios:
        for scenario in approved_scenarios():
            print(scenario.scenario_id)
        return 0
    validate_runtime_catalog()
    if args.validate_only:
        print("balance catalog valid")
        return 0
    config = simulation_config(
        seeds=args.seeds,
        days=args.days,
        seed_root=args.seed_root,
        source_date_epoch=args.source_date_epoch,
    )
    workers = int(args.workers)
    if workers < 0:
        raise SystemExit("--workers must be zero or positive")
    if workers == 0:
        workers = (
            min(8, os.cpu_count() or 1)
            if args.seeds >= 128 else 1
        )
    report = (
        simulate_balance(config, facts=load_catalog_facts(), workers=1)
        if workers == 1
        else simulate_balance(config, workers=workers)
    )
    frozen = finalize_report(report, repository_root=REPOSITORY_ROOT)
    if args.output_dir is not None:
        paths = write_artifacts(frozen, args.output_dir)
        for kind, path in sorted(paths.items()):
            print(f"{kind}: {path}")
    elif args.json:
        print(canonical_json_text(frozen), end="")
    else:
        print(_summary(frozen), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
