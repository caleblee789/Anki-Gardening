#!/usr/bin/env python3
from __future__ import annotations

"""Build the Anki Garden economy PDF from frozen simulation JSON."""

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.balance_analysis.artifacts import load_frozen_report
from scripts.balance_analysis.report import build_pdf, validate_frozen_report


DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "output"
    / "pdf"
    / "anki-garden-economy-progression-rewards-analysis-2.2.0.pdf"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate frozen input without authoring a PDF.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = load_frozen_report(args.input_json)
    validate_frozen_report(report)
    if args.validate_only:
        print("frozen balance report valid")
        return 0
    path = build_pdf(report, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
