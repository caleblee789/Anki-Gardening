from __future__ import annotations

"""Exact comparison helpers for production-engine balance traces.

The accelerated simulator does not claim engine parity by itself. A production
trace can be exported with these field names and compared row-for-row before a
release report promotes the parity status.
"""

from hashlib import sha256
from typing import Iterable, Mapping, Sequence, Tuple

from .catalog import canonical_json_bytes, to_primitive


TRACE_FIELDS: Tuple[str, ...] = (
    "day",
    "study",
    "answers",
    "completed_today",
    "study_run",
    "garden_rhythm_percent",
    "growth_total_units",
    "growth_applied_units",
    "growth_stored_units",
    "growth_spent_units",
    "coins_gross",
    "coins_spent",
    "coins_wallet",
    "finds_total",
    "environments_owned",
    "beds_owned",
    "species_owned",
    "achievements_claimed",
    "active_garden_bonus_id",
    "active_scenery_id",
    "environment_effect_growth_units",
    "environment_effect_coins",
)


class TraceMismatch(AssertionError):
    pass


def canonical_trace_rows(rows: Iterable[Mapping[str, object]]) -> Tuple[Mapping[str, object], ...]:
    normalized = []
    for index, row in enumerate(rows):
        missing = [field for field in TRACE_FIELDS if field not in row]
        extra = sorted(set(row) - set(TRACE_FIELDS))
        if missing or extra:
            raise ValueError(
                f"trace row {index} schema mismatch; missing={missing}, extra={extra}"
            )
        normalized.append({field: to_primitive(row[field]) for field in TRACE_FIELDS})
    return tuple(normalized)


def trace_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    return sha256(canonical_json_bytes(canonical_trace_rows(rows))).hexdigest()


def assert_engine_trace_parity(
    kernel_rows: Sequence[Mapping[str, object]],
    engine_rows: Sequence[Mapping[str, object]],
) -> None:
    expected = canonical_trace_rows(kernel_rows)
    observed = canonical_trace_rows(engine_rows)
    if len(expected) != len(observed):
        raise TraceMismatch(
            f"trace row count differs: kernel={len(expected)}, engine={len(observed)}"
        )
    for index, (kernel_row, engine_row) in enumerate(zip(expected, observed)):
        if kernel_row == engine_row:
            continue
        differences = [
            field for field in TRACE_FIELDS
            if kernel_row[field] != engine_row[field]
        ]
        field = differences[0]
        raise TraceMismatch(
            f"trace row {index} day {kernel_row['day']} differs at {field}: "
            f"kernel={kernel_row[field]!r}, engine={engine_row[field]!r}"
        )
