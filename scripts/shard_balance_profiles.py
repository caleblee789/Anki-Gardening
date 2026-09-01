#!/usr/bin/env python3
from __future__ import annotations

"""Collect and merge exact distributed Anki Garden balance seed shards."""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Optional, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from scripts.balance_analysis.artifacts import finalize_report, write_artifacts
from scripts.balance_analysis.catalog import validate_runtime_catalog
from scripts.balance_analysis.model import (
    DEFAULT_DAYS,
    DEFAULT_SEED_COUNT,
    DEFAULT_SEED_ROOT,
)
from scripts.balance_analysis.shards import (
    merge_balance_shards,
    shard_filename,
    shard_seed_range,
    write_balance_shard,
)
from scripts.simulate_balance_profiles import simulation_config


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed-root", default=DEFAULT_SEED_ROOT)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0") or 0),
    )
    parser.add_argument("--shard-count", type=int, default=20)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="collect one seed shard")
    _common_arguments(collect)
    collect.add_argument("--shard-index", type=int, required=True)
    collect.add_argument("--workers", type=int, default=2)
    collect.add_argument("--output-dir", type=Path, required=True)

    merge = commands.add_parser("merge", help="merge a complete shard set")
    _common_arguments(merge)
    merge.add_argument("--shards-dir", type=Path, required=True)
    merge.add_argument("--output-dir", type=Path, required=True)
    merge.add_argument("--parity-evidence", type=Path)
    merge.add_argument("--release-validation-evidence", type=Path)
    return parser


def _load_object(path: Optional[Path], label: str) -> Optional[Mapping[str, object]]:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as source:
        loaded = json.load(source)
    if not isinstance(loaded, dict):
        raise SystemExit(f"{label} must contain one JSON object")
    return loaded


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    validate_runtime_catalog()
    config = simulation_config(
        seeds=args.seeds,
        days=args.days,
        seed_root=args.seed_root,
        source_date_epoch=args.source_date_epoch,
    )
    if args.command == "collect":
        if args.workers <= 0:
            raise SystemExit("--workers must be positive")
        seed_start, seed_stop = shard_seed_range(
            config.seeds, args.shard_index, args.shard_count
        )
        output_path = args.output_dir / shard_filename(
            args.shard_index, args.shard_count
        )
        path = write_balance_shard(
            config,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            output_path=output_path,
            repository_root=REPOSITORY_ROOT,
            workers=args.workers,
        )
        print(
            f"shard {args.shard_index}/{args.shard_count}: "
            f"seeds [{seed_start}, {seed_stop}) -> {path}"
        )
        return 0

    paths = tuple(sorted(args.shards_dir.rglob("balance-shard-*-of-*.zip")))
    if not paths:
        raise SystemExit(f"no balance shards found below {args.shards_dir}")
    report = merge_balance_shards(
        config,
        shard_paths=paths,
        shard_count=args.shard_count,
        repository_root=REPOSITORY_ROOT,
        parity_evidence=_load_object(args.parity_evidence, "--parity-evidence"),
        release_validation_evidence=_load_object(
            args.release_validation_evidence,
            "--release-validation-evidence",
        ),
    )
    frozen = finalize_report(report, repository_root=REPOSITORY_ROOT)
    outputs = write_artifacts(frozen, args.output_dir)
    for kind, path in sorted(outputs.items()):
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
