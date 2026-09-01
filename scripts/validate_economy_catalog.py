#!/usr/bin/env python3
"""Validate economy catalog copy, routes, artwork, and UI coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.balance_catalog import (
    BED_UNLOCKS,
    COIN_SOURCES,
    STANDARD_FINDS,
    catalog_snapshot,
    validate_balance_catalog,
)
from ankigarden.environment import GARDEN_FEATURE_CATALOG, SCENERY_CATALOG
from ankigarden.collectibles import collectible_registry
from ankigarden.ui.economy_presenters import (
    CATALOG_UI_ENTRY_IDS,
    CatalogItemProjection,
    catalog_item_projections,
)


MANIFEST_PATH = ROOT / "ankigarden" / "assets" / "manifest.json"
_BARE_COIN_COPY = re.compile(r"(?<!Garden )\bCoins?\b")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_records(path: Path) -> tuple[dict[str, Any], ...]:
    payload = _read_json(path)
    records = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("asset manifest must contain an assets list")
    return tuple(record for record in records if isinstance(record, dict))


def _asset_record(
    item: CatalogItemProjection,
    records: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    direct = next(
        (row for row in records if str(row.get("asset_id", "")) == item.asset_id),
        None,
    )
    if direct is not None or item.category != "scenery":
        return direct
    expected_season = "any" if item.item_id == "default" else item.item_id
    return next(
        (
            row
            for row in records
            if str(row.get("category", "")) == "backgrounds"
            and str((row.get("slot") or {}).get("season", "")) == expected_season
        ),
        None,
    )


def _ui_registry_ids(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return tuple(CATALOG_UI_ENTRY_IDS)
    payload = _read_json(path)
    values = payload.get("entry_ids") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("UI registry must be a string list or {entry_ids: [...]} object")
    return tuple(values)


def validate_catalog_integrity(
    *,
    manifest_path: Path = MANIFEST_PATH,
    ui_entry_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Raise on the first release-blocking catalog/UI integrity defect."""

    validate_balance_catalog()
    items = catalog_item_projections()
    authority = catalog_snapshot()
    artwork_ids = authority.get("artwork_ids", {})
    if not isinstance(artwork_ids, dict):
        raise ValueError("catalog artwork IDs must be a mapping")
    entry_ids = tuple(item.entry_id for item in items)
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError("duplicate ID")
    canonical_names = tuple(item.canonical_display_name.strip().casefold() for item in items)
    if len(canonical_names) != len(set(canonical_names)):
        raise ValueError("duplicate canonical display name")
    for item in items:
        if not item.effect_description.strip():
            raise ValueError(f"missing effect copy: {item.entry_id}")
        if not item.acquisition_route.strip():
            raise ValueError(f"missing acquisition route: {item.entry_id}")
        if artwork_ids.get(item.entry_id) != item.asset_id:
            raise ValueError(
                f"catalog artwork authority mismatch: {item.entry_id}"
            )
        if item.purchasable and (item.price_coins is None or item.price_coins <= 0):
            raise ValueError(f"purchasable item without price: {item.entry_id}")
        if not item.purchasable and item.price_coins is not None:
            raise ValueError(
                f"nonpurchasable item with active purchase route: {item.entry_id}"
            )
        for field_name, copy in (
            ("effect copy", item.effect_description),
            ("acquisition route", item.acquisition_route),
        ):
            if _BARE_COIN_COPY.search(copy):
                raise ValueError(
                    f"bare Coin wording in {field_name}: {item.entry_id}"
                )

    for item in (
        *GARDEN_FEATURE_CATALOG.values(),
        *SCENERY_CATALOG.values(),
    ):
        for field_name, copy in (
            ("effect copy", item.effect),
            ("acquisition route", item.how_to_earn),
        ):
            if _BARE_COIN_COPY.search(str(copy)):
                raise ValueError(
                    f"bare Coin wording in environment {field_name}: {item.item_id}"
                )

    for source in COIN_SOURCES:
        for field_name, copy in (
            ("eligibility rule", source.eligibility_rule),
            ("receipt title", source.receipt_title),
            ("receipt detail", source.receipt_detail),
        ):
            if _BARE_COIN_COPY.search(str(copy)):
                raise ValueError(
                    f"bare Coin wording in Coin source {field_name}: {source.source_id}"
                )
    for reward in STANDARD_FINDS:
        if _BARE_COIN_COPY.search(str(reward.description)):
            raise ValueError(
                f"bare Coin wording in Standard Find copy: {reward.reward_id}"
            )
    for item in collectible_registry():
        for field_name, copy in item.descriptor.to_dict().items():
            if _BARE_COIN_COPY.search(str(copy)):
                raise ValueError(
                    f"bare Coin wording in Collection {field_name}: {item.item_id}"
                )
    for bed in BED_UNLOCKS:
        if not str(bed.requirement_copy).strip():
            raise ValueError(f"missing acquisition route: bed_{bed.bed_number}")
        if not str(bed.purchase_action_text).strip():
            raise ValueError(f"missing action copy: bed_{bed.bed_number}")
        for field_name, copy in (
            ("requirement copy", bed.requirement_copy),
            ("action copy", bed.purchase_action_text),
        ):
            if _BARE_COIN_COPY.search(str(copy)):
                raise ValueError(
                    f"bare Coin wording in Bed {field_name}: bed_{bed.bed_number}"
                )
        if bed.price_coins is not None:
            raise ValueError(
                f"nonpurchasable item with active purchase route: bed_{bed.bed_number}"
            )

    records = _manifest_records(Path(manifest_path))
    for item in items:
        record = _asset_record(item, records)
        if record is None:
            raise ValueError(f"missing asset: {item.entry_id} -> {item.asset_id}")
        relative_file = str(record.get("file", ""))
        if not relative_file or not (ROOT / "ankigarden" / relative_file).is_file():
            raise ValueError(f"missing asset: {item.entry_id} -> {relative_file or item.asset_id}")

    ui_ids = tuple(CATALOG_UI_ENTRY_IDS if ui_entry_ids is None else ui_entry_ids)
    if len(ui_ids) != len(set(ui_ids)):
        raise ValueError("duplicate UI entry")
    catalog_set = set(entry_ids)
    ui_set = set(ui_ids)
    orphaned_ui = sorted(ui_set - catalog_set)
    if orphaned_ui:
        raise ValueError(f"orphaned UI entry: {orphaned_ui[0]}")
    orphaned_catalog = sorted(catalog_set - ui_set)
    if orphaned_catalog:
        raise ValueError(f"orphaned catalog entry: {orphaned_catalog[0]}")

    encoded = json.dumps(
        catalog_snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return {
        "catalog_version": "2.2.0",
        "catalog_sha256": hashlib.sha256(encoded).hexdigest(),
        "catalog_entries": len(items),
        "ui_entries": len(ui_ids),
        "asset_manifest": str(Path(manifest_path).relative_to(ROOT)),
        "status": "pass",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument(
        "--ui-registry",
        type=Path,
        help="Optional JSON UI entry registry used by the combined integration gate.",
    )
    args = parser.parse_args(argv)
    ui_ids = _ui_registry_ids(args.ui_registry)
    result = validate_catalog_integrity(
        manifest_path=args.manifest,
        ui_entry_ids=ui_ids,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
