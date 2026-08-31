"""Renderer-neutral 2.2 economy projections for Garden surfaces.

These helpers expose committed state and canonical catalog terms only.  They
never quote purchases, roll rewards, or duplicate engine arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..balance_catalog import (
    ACHIEVEMENT_BY_ID,
    BED_ARTWORK_IDS,
    BED_UNLOCKS,
    COIN_SOURCE_BY_ID,
    CONSUMABLES,
    CONSUMABLE_ARTWORK_IDS,
    COSMETICS,
    GARDEN_BONUSES,
    GARDEN_LEGACY,
    LANDMARKS,
    MASTERY_RANKS,
    SCENERIES,
    SPECIES,
    SPECIES_ARTWORK_IDS,
    AcquisitionKind,
    CoinSourceId,
)


def _id(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def growth_points(units: Any) -> str:
    value = max(0, int(units or 0))
    whole, remainder = divmod(value, 100)
    return f"{whole:,}" if not remainder else f"{whole:,}.{remainder:02d}".rstrip("0")


@dataclass(frozen=True)
class CoinRewardReceipt:
    source_id: str
    display_name: str
    behavioral_family: str
    amount_coins: int
    title: str
    detail: str
    artwork_id: str
    summary_policy: str
    affected_by_harvest_bell: bool
    affected_by_autumn_hearth: bool
    affected_by_plant_checkpoint_multiplier: bool


def coin_reward_receipt(
    source_id: CoinSourceId | str,
    amount_coins: int | None = None,
) -> CoinRewardReceipt:
    """Return canonical source and receipt copy without exposing internal IDs."""

    normalized = _id(source_id)
    definition = COIN_SOURCE_BY_ID.get(normalized)
    if definition is None:
        definition = COIN_SOURCE_BY_ID[CoinSourceId.OTHER.value]
    resolved_amount = (
        definition.fixed_amount_coins
        if amount_coins is None
        else max(0, int(amount_coins))
    )
    if resolved_amount is None:
        raise ValueError(f"Coin amount is required for source {normalized or 'other'}")
    return CoinRewardReceipt(
        source_id=_id(definition.source_id),
        display_name=str(definition.display_name),
        behavioral_family=_id(definition.behavioral_family),
        amount_coins=max(0, int(resolved_amount)),
        title=str(definition.receipt_title or definition.display_name),
        detail=str(definition.receipt_detail or definition.eligibility_rule),
        artwork_id=str(definition.artwork_id),
        summary_policy=_id(definition.summary_policy),
        affected_by_harvest_bell=bool(definition.affected_by_harvest_bell),
        affected_by_autumn_hearth=bool(definition.affected_by_autumn_hearth),
        affected_by_plant_checkpoint_multiplier=bool(
            definition.affected_by_plant_checkpoint_multiplier
        ),
    )


@dataclass(frozen=True)
class CatalogItemProjection:
    entry_id: str
    item_id: str
    canonical_display_name: str
    category: str
    effect_description: str
    acquisition_route: str
    asset_id: str
    purchasable: bool
    price_coins: int | None


def catalog_item_projections() -> tuple[CatalogItemProjection, ...]:
    """One ownership entry per user-visible economy item.

    Environment discovery records intentionally do not create duplicate rows;
    they link back to the Garden Decoration or Scenery ownership entry.
    """

    rows: list[CatalogItemProjection] = []
    for item in SPECIES:
        item_id = _id(item.species_id)
        rows.append(CatalogItemProjection(
            f"species:{item_id}",
            item_id,
            str(item.display_name),
            "species",
            "Plant species; economically identical to every other species.",
            "Choose one starter species free; buy each other species for 250 Garden Coins.",
            str(SPECIES_ARTWORK_IDS[item_id]),
            True,
            int(item.purchase_price_coins or 0),
        ))
    for item in CONSUMABLES:
        item_id = _id(item.consumable_id)
        rows.append(CatalogItemProjection(
            f"consumable:{item_id}",
            item_id,
            str(item.display_name),
            "consumable",
            str(item.effect_description),
            str(item.how_to_acquire),
            str(CONSUMABLE_ARTWORK_IDS[item_id]),
            bool(item.purchasable),
            None if item.price_coins is None else int(item.price_coins),
        ))
    for category, definitions, id_field in (
        ("garden_bonus", GARDEN_BONUSES, "bonus_id"),
        ("scenery", SCENERIES, "scenery_id"),
    ):
        for item in definitions:
            item_id = _id(getattr(item, id_field))
            rows.append(CatalogItemProjection(
                f"{category}:{item_id}",
                item_id,
                str(item.display_name),
                category,
                str(item.effect_description),
                str(item.how_to_acquire),
                str(item.asset_id),
                bool(item.purchasable),
                None if item.price_coins is None else int(item.price_coins),
            ))
    for item in COSMETICS:
        item_id = _id(item.cosmetic_id)
        achievement = (
            None
            if item.source_achievement_id is None
            else ACHIEVEMENT_BY_ID[_id(item.source_achievement_id)]
        )
        acquisition = (
            f"Nursery for {int(item.price_coins):,} Garden Coins."
            if item.acquisition is AcquisitionKind.PURCHASE
            else f"Achievement: {achievement.display_name}."
            if achievement is not None
            else "Included."
        )
        rows.append(CatalogItemProjection(
            f"cosmetic:{item_id}",
            item_id,
            str(item.display_name),
            "cosmetic",
            "Display Decoration only; no gameplay effect.",
            acquisition,
            str(item.asset_id),
            bool(item.purchasable),
            None if item.price_coins is None else int(item.price_coins),
        ))
    for item in LANDMARKS:
        item_id = _id(item.landmark_id)
        rows.append(CatalogItemProjection(
            f"landmark:{item_id}", item_id, str(item.display_name), "landmark",
            str(item.effect_description), str(item.how_to_acquire), str(item.asset_id),
            False, None,
        ))
    for item in MASTERY_RANKS:
        item_id = _id(item.rank_id)
        rows.append(CatalogItemProjection(
            f"mastery:{item_id}", item_id, str(item.display_name), "mastery",
            str(item.effect_description), str(item.how_to_acquire), str(item.asset_id),
            False, None,
        ))
    rows.append(CatalogItemProjection(
        "legacy:garden_legacy",
        str(GARDEN_LEGACY.legacy_id),
        str(GARDEN_LEGACY.display_name),
        "legacy",
        str(GARDEN_LEGACY.effect_description),
        str(GARDEN_LEGACY.how_to_acquire),
        str(GARDEN_LEGACY.asset_id),
        False,
        None,
    ))
    for item in BED_UNLOCKS:
        item_id = f"bed_{int(item.bed_number)}"
        achievement = (
            None
            if item.source_achievement_id is None
            else ACHIEVEMENT_BY_ID[_id(item.source_achievement_id)]
        )
        rows.append(CatalogItemProjection(
            f"bed:{item_id}",
            item_id,
            f"Garden Bed {int(item.bed_number)}",
            "bed",
            (
                "Permanent planting space; each other planted bed adds one "
                "10% Shared Growth lane."
            ),
            (
                "Included."
                if bool(item.included)
                else f"Achievement: {achievement.display_name}. {item.requirement_copy}."
            ),
            str(BED_ARTWORK_IDS[item_id]),
            False,
            None,
        ))
    return tuple(rows)


CATALOG_UI_ENTRY_IDS = tuple(row.entry_id for row in catalog_item_projections())


@dataclass(frozen=True)
class BedUnlockRow:
    bed_number: int
    unlocked: bool
    requirement: str
    bed_id: str
    display_name: str
    artwork_id: str
    source_achievement_id: str
    unlock_policy: str
    action_text: str
    price_coins: None
    can_commit: bool
    status: str


def bed_unlock_rows(state: Any) -> tuple[BedUnlockRow, ...]:
    unlocked = max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0)))
    return tuple(
        BedUnlockRow(
            int(item.bed_number),
            int(item.bed_number) <= unlocked,
            str(item.requirement_copy),
            f"bed_{int(item.bed_number)}",
            f"Garden Bed {int(item.bed_number)}",
            str(BED_ARTWORK_IDS[f"bed_{int(item.bed_number)}"]),
            _id(item.source_achievement_id),
            str(item.unlock_policy),
            str(item.purchase_action_text),
            None,
            False,
            (
                "unlocked"
                if int(item.bed_number) <= unlocked
                else "included"
                if bool(item.included)
                else "progression_locked"
            ),
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
    "CATALOG_UI_ENTRY_IDS",
    "CatalogItemProjection",
    "CoinRewardReceipt",
    "CosmeticRow",
    "LandmarkRow",
    "LandmarkSummary",
    "MasterySpeciesRow",
    "MasterySummary",
    "bed_unlock_rows",
    "catalog_item_projections",
    "coin_reward_receipt",
    "cosmetic_rows",
    "growth_points",
    "landmark_summary",
    "mastery_summary",
]
