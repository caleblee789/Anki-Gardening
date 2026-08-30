"""Renderer-neutral 2.2 economy projections for Garden surfaces.

These helpers expose committed state and canonical catalog terms only.  They
never quote purchases, roll rewards, or duplicate engine arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..balance_catalog import BED_UNLOCKS, COSMETICS


def _id(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def growth_points(units: Any) -> str:
    value = max(0, int(units or 0))
    whole, remainder = divmod(value, 100)
    return f"{whole:,}" if not remainder else f"{whole:,}.{remainder:02d}".rstrip("0")


@dataclass(frozen=True)
class BedUnlockRow:
    bed_number: int
    unlocked: bool
    requirement: str


_BED_REQUIREMENTS = {
    3: "First plant reaches Mature",
    4: "First unique species reaches Full Bloom",
    5: "3 unique species reach Full Bloom",
    6: "6 unique species reach Full Bloom",
}


def bed_unlock_rows(state: Any) -> tuple[BedUnlockRow, ...]:
    unlocked = max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0)))
    return tuple(
        BedUnlockRow(
            int(item.bed_number),
            int(item.bed_number) <= unlocked,
            "Included" if bool(item.included) else _BED_REQUIREMENTS[int(item.bed_number)],
        )
        for item in BED_UNLOCKS
    )


@dataclass(frozen=True)
class CosmeticRow:
    item_id: str
    name: str
    owned: bool
    displayed: bool
    price: int | None
    acquisition: str
    asset_id: str


def cosmetic_rows(state: Any) -> tuple[CosmeticRow, ...]:
    inventory = getattr(state, "inventory", {}) or {}
    owned_ids = {str(value) for value in (inventory.get("cosmetics", ()) or ())}
    displayed_id = str(
        getattr(getattr(state, "loadout", None), "display_decoration_id", "") or ""
    )
    return tuple(
        CosmeticRow(
            _id(item.cosmetic_id),
            str(item.display_name),
            _id(item.cosmetic_id) in owned_ids,
            _id(item.cosmetic_id) == displayed_id,
            None if item.price_coins is None else int(item.price_coins),
            _id(item.acquisition),
            str(item.asset_id),
        )
        for item in COSMETICS
    )


@dataclass(frozen=True)
class LandmarkRow:
    item_id: str
    name: str
    growth_cost_units: int
    coin_cost: int
    completed: bool
    selected: bool
    displayed: bool


@dataclass(frozen=True)
class LandmarkSummary:
    unlocked: bool
    stored_growth_units: int
    selected_id: str
    next_id: str
    contributed_growth_units: int
    required_growth_units: int
    ready_to_complete: bool
    auto_contribute: bool
    rows: tuple[LandmarkRow, ...]


def landmark_summary(engine: Any) -> LandmarkSummary:
    value = dict(engine.landmark_catalog_summary())
    return LandmarkSummary(
        bool(value.get("unlocked", False)),
        max(0, int(value.get("stored_growth_units", 0) or 0)),
        str(value.get("selected_landmark_id", "") or ""),
        str(value.get("next_landmark_id", "") or ""),
        max(0, int(value.get("contributed_growth_units", 0) or 0)),
        max(0, int(value.get("required_growth_units", 0) or 0)),
        bool(value.get("ready_to_complete", False)),
        bool(value.get("auto_contribute", False)),
        tuple(
            LandmarkRow(
                str(row.get("landmark_id", "") or ""),
                str(row.get("display_name", "") or "Garden Landmark"),
                max(0, int(row.get("growth_cost_units", 0) or 0)),
                max(0, int(row.get("coin_cost", 0) or 0)),
                bool(row.get("completed", False)),
                bool(row.get("selected", False)),
                bool(row.get("displayed", False)),
            )
            for row in (value.get("items", ()) or ())
        ),
    )


@dataclass(frozen=True)
class MasterySpeciesRow:
    species_id: str
    eligible: bool
    current_rank_id: str
    next_rank_id: str


@dataclass(frozen=True)
class MasterySummary:
    stored_growth_units: int
    rows: tuple[MasterySpeciesRow, ...]


def mastery_summary(engine: Any) -> MasterySummary:
    value = dict(engine.mastery_catalog_summary())
    return MasterySummary(
        max(0, int(value.get("stored_growth_units", 0) or 0)),
        tuple(
            MasterySpeciesRow(
                str(row.get("species_id", "") or ""),
                bool(row.get("eligible", False)),
                str(row.get("current_rank_id", "") or ""),
                str(row.get("next_rank_id", "") or ""),
            )
            for row in (value.get("species", ()) or ())
        ),
    )


__all__ = [
    "BedUnlockRow",
    "CosmeticRow",
    "LandmarkRow",
    "LandmarkSummary",
    "MasterySpeciesRow",
    "MasterySummary",
    "bed_unlock_rows",
    "cosmetic_rows",
    "growth_points",
    "landmark_summary",
    "mastery_summary",
]
