#!/usr/bin/env python3
from __future__ import annotations

"""Summarize or compare opt-in Anki Garden runtime timing exports."""

import argparse
import json
from pathlib import Path
from typing import Any


def _operations(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported performance schema")
    rows = payload.get("operations")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: operations must be a list")
    return {
        str(row["name"]): dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("name")
    }


def _percent_change(before: float, after: float) -> str:
    if before <= 0:
        return "n/a"
    return f"{((after - before) / before) * 100:+.1f}%"


def _comparison_row(
    name: str,
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> tuple[str, ...]:
    if current is None:
        return name, "0", "missing", "missing", "n/a", "n/a"
    median = float(current.get("median_ms", 0.0))
    p95 = float(current.get("p95_ms", 0.0))
    previous_median = (
        float(previous.get("median_ms", 0.0)) if previous is not None else 0.0
    )
    previous_p95 = (
        float(previous.get("p95_ms", 0.0)) if previous is not None else 0.0
    )
    return (
        name,
        str(int(current.get("count", 0))),
        f"{median:.3f}",
        f"{p95:.3f}",
        _percent_change(previous_median, median),
        _percent_change(previous_p95, p95),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    candidate = _operations(args.candidate)
    baseline = _operations(args.baseline) if args.baseline else {}
    names = sorted(set(candidate) | set(baseline))
    print("operation\tcount\tmedian_ms\tp95_ms\tmedian_delta\tp95_delta")
    for name in names:
        current = candidate.get(name)
        previous = baseline.get(name)
        print("\t".join(_comparison_row(name, current, previous)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
