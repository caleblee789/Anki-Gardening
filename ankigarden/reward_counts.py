"""One read-only definition of awarded Items & finds across reward surfaces."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .garden_finds import STANDARD_FIND_RECEIPT_SOURCES

ITEMS_AND_FINDS_LABEL = "Items & finds"


def _read(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _quantity(row: Any) -> int:
    return max(0, int(_read(row, "quantity", 1) or 0))


def _event(row: Any) -> str:
    return str(_read(row, "event_key", "") or _read(row, "event_id", "") or
               _read(row, "correlation_id", "") or "")


def _excluded(source: str) -> bool:
    return source in {"purchase", "refund", "migration", "adjustment"} or source.endswith("_use")


def reward_drop_count(source: Any) -> int:
    """Count each Find once and independent item quantities once.

    Engine Find totals remain authoritative. Receipts attached to those Finds
    describe their payout, not another drop. Appearance unlocks and their typed
    receipts likewise represent one award. Purchasing or using an item is not
    an earned drop.
    """
    mixed = _read(source, "finds")
    finds = tuple(_read(source, "standard_finds", ()) or ())
    seen = set()
    if mixed is not None:
        total = 0
        for index, row in enumerate(mixed):
            if _excluded(str(_read(row, "source", ""))):
                continue
            identity = (_event(row) or f"row:{index}",
                        str(_read(row, "reward_id", "") or _read(row, "item_id", "")))
            if identity not in seen:
                total += _quantity(row)
                seen.add(identity)
        find_count = total
    else:
        declared = next((_read(source, key) for key in
                         ("footer_find_count", "total_finds", "find_count")
                         if _read(source, key) is not None), None)
        find_count = max(0, int(declared)) if declared is not None else sum(_quantity(row) for row in finds)
        total = find_count
    find_events = {_event(row) for row in finds if _event(row)}
    environments = tuple(_read(source, "environment_discoveries", ()) or ())
    environment_ids = set()
    environment_events = set()
    for index, row in enumerate(environments):
        identity = str(_read(row, "environment_id", "") or _read(row, "item_id", "") or
                       _event(row) or f"environment:{index}")
        if identity in environment_ids:
            continue
        environment_ids.add(identity)
        if _event(row):
            environment_events.add(_event(row))
        if not _event(row) or _event(row) not in find_events:
            total += _quantity(row)
    seen_receipts = set()
    for index, row in enumerate(_read(source, "reward_receipts", ()) or ()):
        kind = str(_read(row, "reward_type", ""))
        if kind not in {"inventory_item", "environment_item"}:
            continue
        award_source = str(_read(row, "source", ""))
        if _excluded(award_source):
            continue
        item_id = str(_read(row, "item_id", ""))
        event = _event(row)
        identity = (event or f"receipt:{index}", kind, item_id)
        if identity in seen_receipts:
            continue
        seen_receipts.add(identity)
        if event and event in find_events:
            continue
        if (award_source in STANDARD_FIND_RECEIPT_SOURCES or award_source == "standard_find") and find_count:
            continue
        if kind == "environment_item" and (item_id in environment_ids or event in environment_events):
            continue
        total += max(0, int(_read(row, "amount", 0) or 0))
    return total


def activity_drop_count(find_count: int, source: str, items: Any) -> int:
    """Adapt the saved Activity projection without re-evaluating rewards."""
    if _excluded(source):
        return 0
    return reward_drop_count({
        "total_finds": find_count,
        "reward_receipts": tuple({
            **item, "reward_type": item.get("kind", ""),
            "source": item.get("source", source),
        } for item in items),
    })
