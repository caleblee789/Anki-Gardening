#!/usr/bin/env python3
"""Repeatable history benchmark on a read-only copy or a synthetic collection."""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["ANKI_GARDEN_SKIP_STARTUP"] = "1"

from ankigarden.achievements import HistoricalReview, analyze_history
from ankigarden.history_index import HISTORY_PAGE_SIZE, HistoryIndex, SchedulerDayMapper, analyze_indexed_days
from ankigarden.performance import RuntimePerformanceRecorder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--synthetic-reviews", type=int, default=1_000_001)
    parser.add_argument("--synthetic-cards", type=int, default=300_000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.collection
    if source is None:
        source = args.output / "synthetic.sqlite3"
        with closing(sqlite3.connect(source)) as db, db:
            db.execute("CREATE TABLE revlog(id INTEGER PRIMARY KEY,cid,ease,ivl,lastIvl,factor,time,type)")
            for offset in range(0, args.synthetic_reviews, HISTORY_PAGE_SIZE):
                db.executemany("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?)", (
                    (1_700_000_000_000 + i * 60_000, i % args.synthetic_cards + 1,
                     i % 4 + 1, 30, 20, 2500, 500, i % 4)
                    for i in range(offset, min(args.synthetic_reviews, offset + HISTORY_PAGE_SIZE))
                ))
    source = source.resolve()
    recorder = RuntimePerformanceRecorder(enabled=True, max_samples=2048)
    index = HistoryIndex(args.output / "history.sqlite3")
    day_for_id = SchedulerDayMapper(datetime(2026, 1, 1))
    counts = {}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        upper = int(db.execute("SELECT max(id) FROM revlog WHERE type IN (0,1,2,3)").fetchone()[0] or 0)
        for route in ("cold", "warm-verification"):
            begin = recorder.begin()
            index.begin_scan("benchmark-midnight")
            after = 0
            rows_read = 0
            while after < upper:
                query_start = recorder.begin()
                rows = db.execute(
                    "SELECT id,cid,ease,ivl,lastIvl,factor,time,type FROM revlog "
                    "WHERE id>? AND id<=? AND type IN (0,1,2,3) ORDER BY id LIMIT ?",
                    (after, upper, HISTORY_PAGE_SIZE),
                ).fetchall()
                recorder.finish("source-page", query_start)
                if not rows:
                    break
                index.ingest(rows, day_for_id)
                after = rows[-1][0]
                rows_read += len(rows)
            counts[route] = {"rows_read": rows_read, **index.finish_scan()}
            recorder.finish(route, begin)
        index_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        today = day_for_id(upper)
        for _ in range(20):
            begin = recorder.begin()
            actual = analyze_indexed_days(index.summaries(), current_open_day=today)
            recorder.finish("indexed-summary", begin)
        # The unchanged full reducer remains the correctness reference.
        reviews = tuple(HistoricalReview(row[0], row[0], day_for_id(row[0]), row[1])
                        for row in db.execute("SELECT id,ease FROM revlog WHERE type IN (0,1,2,3) ORDER BY id"))
        for _ in range(3):
            begin = recorder.begin()
            reference = analyze_history(reviews, current_open_day=today)
            recorder.finish("full-summary-reference", begin)
        expected = asdict(reference)
        obtained = asdict(actual)
        expected.pop("fingerprint")
        obtained.pop("fingerprint")
        assert obtained == expected, "Indexed achievements differ from the full reducer"
        assert counts["warm-verification"]["rebuilt_days"] == 0
    payload = {
        "source": str(source), "eligible_reviews": len(reviews),
        "synthetic_cards": args.synthetic_cards if args.collection is None else None,
        "reference_parity": True, "counts": counts,
        "index_peak_rss_bytes": index_peak if sys.platform == "darwin" else index_peak * 1024,
        "peak_including_reference_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "timings": recorder.payload(),
    }
    (args.output / "report.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
