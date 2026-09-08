from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .balance_catalog import (
    ENVIRONMENT_DISCOVERIES as BALANCE_ENVIRONMENT_DISCOVERIES,
    GARDEN_BONUSES as BALANCE_GARDEN_BONUSES,
    SCENERIES as BALANCE_SCENERIES,
    CONSUMABLES as BALANCE_CONSUMABLES,
    AcquisitionKind as BalanceAcquisitionKind,
    ConsumableKind as BalanceConsumableKind,
    RewardKind as BalanceRewardKind,
    TriggerKind as BalanceTriggerKind,
)
from .purchases import EffectDescriptor
from .bonus_copy import format_appearance_effect


EnvironmentKind = Literal["garden_feature", "scenery"]
AcquisitionKind = Literal["free", "purchase", "drop"]
Rarity = Literal["Common", "Uncommon", "Rare", "Very Rare", "Ultra Rare"]
DropTier = Literal[
    "ultra_environment",
    "very_rare_environment",
    "rare_environment",
]
EffectTrigger = Literal[
    "eligible_card",
    "today_cards_complete",
    "coin_earned",
]
EffectValueKind = Literal[
    "growth",
    "coins",
    "instant_growth",
    "inventory_item",
    "earned_coin_percent",
]


@dataclass(frozen=True)
class WeightedEnvironmentReward:
    """One outcome in an environment's deterministic weighted gift."""

    item_id: str
    weight_percent: int

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("weighted environment reward item_id is required")
        if (
            isinstance(self.weight_percent, bool)
            or not isinstance(self.weight_percent, int)
            or self.weight_percent <= 0
        ):
            raise ValueError("weighted environment reward must have a positive weight")


@dataclass(frozen=True)
class EnvironmentEffect:
    """Machine-readable definition for one environment effect.

    Copy remains on :class:`CatalogItem` for player-facing surfaces.  The
    structured form is the authority for calculation and validation, so the
    engine and UI do not need to parse prose.
    """

    effect_id: str
    trigger: EffectTrigger
    value_kind: EffectValueKind
    amount: int = 0
    amount_units: int = 0
    first_cards: int | None = None
    every_nth_card: int | None = None
    every_nth_completion: int | None = None
    inventory_item_id: str | None = None
    weighted_rewards: tuple[WeightedEnvironmentReward, ...] = ()
    active_only: bool = True

    def __post_init__(self) -> None:
        if not self.effect_id.strip():
            raise ValueError("environment effect_id is required")
        if (
            isinstance(self.amount, bool)
            or not isinstance(self.amount, int)
            or self.amount < 0
        ):
            raise ValueError("environment effect amount must be a nonnegative integer")
        if (
            isinstance(self.amount_units, bool)
            or not isinstance(self.amount_units, int)
            or self.amount_units < 0
        ):
            raise ValueError("environment effect amount_units must be a nonnegative integer")
        for value, label in (
            (self.first_cards, "first_cards"),
            (self.every_nth_card, "every_nth_card"),
            (self.every_nth_completion, "every_nth_completion"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"environment {label} must be positive")
        if self.weighted_rewards:
            if self.value_kind != "inventory_item":
                raise ValueError("weighted rewards require an inventory effect")
            if sum(item.weight_percent for item in self.weighted_rewards) != 100:
                raise ValueError("weighted environment rewards must total 100 percent")


@dataclass(frozen=True)
class CatalogItem:
    item_id: str
    name: str
    kind: EnvironmentKind
    rarity: Rarity
    acquisition: AcquisitionKind
    effect: str
    how_to_earn: str
    price: int | None = None
    drop_tier: DropTier | None = None
    effects: tuple[EnvironmentEffect, ...] = ()

    @property
    def purchasable(self) -> bool:
        return self.acquisition == "purchase" and self.price is not None

    @property
    def drop_only(self) -> bool:
        return self.acquisition == "drop"

    @property
    def descriptor(self) -> EffectDescriptor:
        kind_name = "Garden Decoration" if self.kind == "garden_feature" else "Scenery"
        other_kind = "Scenery" if self.kind == "garden_feature" else "Garden Decoration"
        return EffectDescriptor(
            function=f"Changes {kind_name}.",
            buff=self.effect,
            activation_condition="Applies while equipped.",
            duration="Stays in your collection.",
            stacking=f"One {kind_name} at a time; {other_kind} remains equipped.",
            replacement=f"Another {kind_name} takes its place; ownership stays.",
            unlock_requirement=self.how_to_earn,
        )


@dataclass(frozen=True)
class GrowthChargeSpec:
    charge_id: str
    name: str
    growth: int
    price: int | None
    rarity: Rarity
    how_to_earn: str

    @property
    def purchasable(self) -> bool:
        return self.price is not None

    @property
    def descriptor(self) -> EffectDescriptor:
        return EffectDescriptor(
            function="Adds 1 Growth Charge to inventory.",
            buff=f"+{self.growth:,} Growth when used.",
            activation_condition="Use on an unfinished planted plant, or across the garden after all species reach Full Bloom.",
            duration="Instant; consumed on use.",
            stacking="Inventory quantities stack; each Charge is used separately.",
            replacement="Replaces nothing.",
            unlock_requirement=self.how_to_earn,
        )


_TRIGGER_PROJECTION = {
    BalanceTriggerKind.ELIGIBLE_CARD: "eligible_card",
    BalanceTriggerKind.VALID_COMPLETION: "today_cards_complete",
    BalanceTriggerKind.COIN_EARNED: "coin_earned",
}
_VALUE_KIND_PROJECTION = {
    BalanceRewardKind.GROWTH: "growth",
    BalanceRewardKind.COINS: "coins",
    BalanceRewardKind.INSTANT_GROWTH: "instant_growth",
    BalanceRewardKind.CONSUMABLE: "inventory_item",
    BalanceRewardKind.EARNED_COIN_PERCENT: "earned_coin_percent",
    BalanceRewardKind.BANKED_GROWTH: "instant_growth",
}


def _runtime_environment_effect(effect: object) -> EnvironmentEffect:
    """Project canonical mechanics into the renderer-facing catalog shape."""

    grant = effect.grant
    weighted = tuple(
        WeightedEnvironmentReward(
            str(weighted_grant.grant.item_id or ""),
            int(weighted_grant.weight_percent),
        )
        for weighted_grant in effect.weighted_grants
    )
    reward_kind = (
        grant.kind
        if grant is not None
        else BalanceRewardKind.CONSUMABLE
    )
    amount = max(0, int(grant.amount)) if grant is not None else 1
    amount_units = (
        amount * 100
        if reward_kind is BalanceRewardKind.BANKED_GROWTH
        else 0
    )
    return EnvironmentEffect(
        effect_id=str(effect.effect_id),
        trigger=_TRIGGER_PROJECTION[effect.trigger],
        value_kind=_VALUE_KIND_PROJECTION[reward_kind],
        amount=0 if amount_units else amount,
        amount_units=amount_units,
        first_cards=effect.cadence.first_n_per_day,
        every_nth_card=(
            effect.cadence.every_n
            if effect.trigger is BalanceTriggerKind.ELIGIBLE_CARD
            and effect.cadence.every_n > 1
            else None
        ),
        every_nth_completion=(
            effect.cadence.every_n
            if effect.trigger is BalanceTriggerKind.VALID_COMPLETION
            and effect.cadence.every_n > 1
            else None
        ),
        inventory_item_id=(
            str(grant.item_id or "") or None
            if grant is not None
            and reward_kind is BalanceRewardKind.CONSUMABLE
            else None
        ),
        weighted_rewards=weighted,
        active_only=effect.cadence.active_only,
    )


def _runtime_acquisition(acquisition: BalanceAcquisitionKind) -> AcquisitionKind:
    if acquisition is BalanceAcquisitionKind.INCLUDED:
        return "free"
    if acquisition is BalanceAcquisitionKind.PURCHASE:
        return "purchase"
    return "drop"


_DISCOVERY_TIER_BY_ITEM = {
    str(item.item_id): str(item.tier_id)
    for item in BALANCE_ENVIRONMENT_DISCOVERIES
}


def _project_catalog_item(
    definition: object,
    *,
    kind: EnvironmentKind,
) -> CatalogItem:
    item_id = str(
        definition.bonus_id if kind == "garden_feature" else definition.scenery_id
    )
    return CatalogItem(
        item_id=item_id,
        name=str(definition.display_name),
        kind=kind,
        rarity=str(definition.rarity),
        acquisition=_runtime_acquisition(definition.acquisition),
        effect=format_appearance_effect(definition),
        how_to_earn=str(definition.how_to_acquire),
        price=definition.price_coins,
        drop_tier=_DISCOVERY_TIER_BY_ITEM.get(item_id),
        effects=tuple(
            _runtime_environment_effect(effect)
            for effect in definition.effects
        ),
    )


# Runtime mechanics, names, prices, and acquisition routes are projections of
# the canonical catalog, including the shared effect formatter.
GARDEN_FEATURE_CATALOG = {
    str(definition.bonus_id): _project_catalog_item(
        definition,
        kind="garden_feature",
    )
    for definition in BALANCE_GARDEN_BONUSES
}
SCENERY_CATALOG = {
    str(definition.scenery_id): _project_catalog_item(
        definition,
        kind="scenery",
    )
    for definition in BALANCE_SCENERIES
}


ENVIRONMENT_CATALOG: dict[str, dict[str, CatalogItem]] = {
    "garden_feature": GARDEN_FEATURE_CATALOG,
    "scenery": SCENERY_CATALOG,
}


GROWTH_CHARGES: dict[str, GrowthChargeSpec] = {
    "growth_charge_small": GrowthChargeSpec(
        "growth_charge_small",
        "Small Growth Charge",
        100,
        30,
        "Common",
        "Nursery: 30 Garden Coins; daily Scenery; achievements; or Garden Finds.",
    ),
    "growth_charge_standard": GrowthChargeSpec(
        "growth_charge_standard",
        "Standard Growth Charge",
        500,
        125,
        "Rare",
        "Nursery: 125 Garden Coins; Halloween Garden; achievements; or Garden Finds.",
    ),
    "growth_charge_grand": GrowthChargeSpec(
        "growth_charge_grand",
        "Grand Growth Charge",
        2_000,
        None,
        "Very Rare",
        "Botanical Collection, Old Growth, and future major event rewards.",
    ),
}

GROWTH_CHARGES = {
    str(item.consumable_id): GrowthChargeSpec(
        charge_id=str(item.consumable_id),
        name=str(item.display_name),
        growth=max(0, int(item.instant_growth)),
        price=item.price_coins,
        rarity=str(item.rarity),
        how_to_earn=str(item.how_to_acquire),
    )
    for item in BALANCE_CONSUMABLES
    if item.kind is BalanceConsumableKind.GROWTH_CHARGE
}


DEFAULT_GARDEN_FEATURE_ID = "seedling_sign"
DEFAULT_SCENERY_ID = "default"

LEGACY_WEATHER_TO_GARDEN_FEATURE: dict[str, str] = {
    "sunny": "seedling_sign",
    "breeze": "wind_chime",
    "cloudy": "harvest_bell",
    "gentle_rain": "watering_station",
    "snow_flurry": "herbalist_hourglass",
    "fireflies": "firefly_lantern",
    "rainbow_sunshower": "prism_trellis",
}
# Supported migration-window aliases. New code and saved state use only the
# Garden Decoration names above. Internal identifiers remain stable for save compatibility.
DEFAULT_WEATHER_ID = DEFAULT_GARDEN_FEATURE_ID
WEATHER_CATALOG = GARDEN_FEATURE_CATALOG


def canonical_garden_feature_id(item_id: object) -> str:
    value = str(item_id or "")
    return LEGACY_WEATHER_TO_GARDEN_FEATURE.get(value, value)


def environment_item(kind: str, item_id: str) -> CatalogItem | None:
    normalized_kind = "garden_feature" if str(kind) == "weather" else str(kind)
    normalized_id = (
        canonical_garden_feature_id(item_id)
        if normalized_kind == "garden_feature"
        else str(item_id)
    )
    return ENVIRONMENT_CATALOG.get(normalized_kind, {}).get(normalized_id)


def catalog_items(kind: str | None = None) -> tuple[CatalogItem, ...]:
    if kind is not None:
        normalized_kind = "garden_feature" if str(kind) == "weather" else str(kind)
        return tuple(ENVIRONMENT_CATALOG.get(normalized_kind, {}).values())
    return tuple(
        item for catalog in ENVIRONMENT_CATALOG.values() for item in catalog.values()
    )
