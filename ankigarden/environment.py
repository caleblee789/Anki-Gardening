from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .purchases import EffectDescriptor


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
    "booster_activation",
    "plant_milestone",
]
EffectValueKind = Literal[
    "growth",
    "coins",
    "instant_growth",
    "inventory_item",
    "booster_cards",
    "milestone_coin_percent",
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
            activation_condition="Use on any owned, planted, unfinished garden plant.",
            duration="Instant; consumed on use.",
            stacking="Inventory quantities stack; each Charge is used separately.",
            replacement="Replaces nothing.",
            unlock_requirement=self.how_to_earn,
        )


GARDEN_FEATURE_CATALOG: dict[str, CatalogItem] = {
    "seedling_sign": CatalogItem(
        "seedling_sign",
        "Seedling Sign",
        "garden_feature",
        "Common",
        "free",
        "",
        "Included.",
    ),
    "wind_chime": CatalogItem(
        "wind_chime",
        "Wind Chime",
        "garden_feature",
        "Common",
        "purchase",
        "Every 10 eligible card answers: +1 Growth.",
        "Nursery: 100 Garden Coins.",
        100,
        effects=(EnvironmentEffect(
            "growth_every_10_plus_1",
            "eligible_card",
            "growth",
            amount=1,
            every_nth_card=10,
        ),),
    ),
    "harvest_bell": CatalogItem(
        "harvest_bell",
        "Harvest Bell",
        "garden_feature",
        "Common",
        "purchase",
        "+5 Coins when today’s cards are complete.",
        "Nursery: 175 Garden Coins.",
        175,
        effects=(EnvironmentEffect(
            "completion_coins_plus_5",
            "today_cards_complete",
            "coins",
            amount=5,
        ),),
    ),
    "watering_station": CatalogItem(
        "watering_station",
        "Watering Station",
        "garden_feature",
        "Uncommon",
        "purchase",
        "Every 5 eligible card answers: +1 Growth.",
        "Nursery: 250 Garden Coins.",
        250,
        effects=(EnvironmentEffect(
            "growth_every_5_plus_1",
            "eligible_card",
            "growth",
            amount=1,
            every_nth_card=5,
        ),),
    ),
    "herbalist_hourglass": CatalogItem(
        "herbalist_hourglass",
        "Herbalist’s Hourglass",
        "garden_feature",
        "Uncommon",
        "purchase",
        "Booster Potions provide 25 percent more Booster cards.",
        "Nursery: 350 Garden Coins.",
        350,
        effects=(EnvironmentEffect(
            "booster_cards_multiplier_1_25",
            "booster_activation",
            "booster_cards",
            amount=25,
        ),),
    ),
    "firefly_lantern": CatalogItem(
        "firefly_lantern",
        "Firefly Lantern",
        "garden_feature",
        "Rare",
        "drop",
        "Every 4 eligible card answers: +3 Growth.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="rare_environment",
        effects=(EnvironmentEffect(
            "growth_every_4_plus_3",
            "eligible_card",
            "growth",
            amount=3,
            every_nth_card=4,
        ),),
    ),
    "prism_trellis": CatalogItem(
        "prism_trellis",
        "Prism Trellis",
        "garden_feature",
        "Very Rare",
        "drop",
        "Bank 1.5 Growth per eligible card; release it when Today’s Cards are complete.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="very_rare_environment",
        effects=(EnvironmentEffect(
            "prism_bank_per_answer_1_5",
            "eligible_card",
            "instant_growth",
            amount_units=150,
        ),),
    ),
}


SCENERY_CATALOG: dict[str, CatalogItem] = {
    "default": CatalogItem(
        "default",
        "Verdant Twilight",
        "scenery",
        "Common",
        "free",
        "",
        "Included.",
    ),
    "spring": CatalogItem(
        "spring",
        "Spring Bloom",
        "scenery",
        "Common",
        "purchase",
        "+1 Growth on your first 25 cards each Anki day.",
        "Nursery: 400 Garden Coins.",
        400,
        effects=(EnvironmentEffect(
            "spring_bloom_growth",
            "eligible_card",
            "growth",
            amount=1,
            first_cards=25,
        ),),
    ),
    "summer": CatalogItem(
        "summer",
        "Golden Summer",
        "scenery",
        "Uncommon",
        "purchase",
        "+1 Growth on every second card among your first 100 each Anki day.",
        "Nursery: 600 Garden Coins.",
        600,
        effects=(EnvironmentEffect(
            "golden_summer_growth",
            "eligible_card",
            "growth",
            amount=1,
            first_cards=100,
            every_nth_card=2,
        ),),
    ),
    "autumn": CatalogItem(
        "autumn",
        "Autumn Hearth",
        "scenery",
        "Uncommon",
        "purchase",
        "+50% Coins from plant checkpoints and stage completion.",
        "Nursery: 500 Garden Coins.",
        500,
        effects=(EnvironmentEffect(
            "autumn_hearth_milestone_coins",
            "plant_milestone",
            "milestone_coin_percent",
            amount=50,
        ),),
    ),
    "snowy": CatalogItem(
        "snowy",
        "Snow-Covered Garden",
        "scenery",
        "Rare",
        "purchase",
        "Gain 1 Small Growth Charge when today’s cards are complete.",
        "Nursery: 1,200 Garden Coins.",
        1_200,
        effects=(EnvironmentEffect(
            "snowy_completion_charge",
            "today_cards_complete",
            "inventory_item",
            amount=1,
            inventory_item_id="growth_charge_small",
        ),),
    ),
    "rainbow_horizon": CatalogItem(
        "rainbow_horizon",
        "Rainbow Horizon",
        "scenery",
        "Rare",
        "drop",
        "+1 Growth on your first 100 cards each Anki day.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="rare_environment",
        effects=(EnvironmentEffect(
            "rainbow_horizon_growth",
            "eligible_card",
            "growth",
            amount=1,
            first_cards=100,
        ),),
    ),
    "halloween": CatalogItem(
        "halloween",
        "Halloween Garden",
        "scenery",
        "Very Rare",
        "drop",
        "When today’s cards are complete: Small Charge 85%, Standard Charge 10%, or Booster Potion 5%.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="very_rare_environment",
        effects=(EnvironmentEffect(
            "halloween_completion_gift",
            "today_cards_complete",
            "inventory_item",
            amount=1,
            weighted_rewards=(
                WeightedEnvironmentReward("growth_charge_small", 85),
                WeightedEnvironmentReward("growth_charge_standard", 10),
                WeightedEnvironmentReward("booster_potion", 5),
            ),
        ),),
    ),
    "full_moon": CatalogItem(
        "full_moon",
        "Full Moon Garden",
        "scenery",
        "Ultra Rare",
        "drop",
        "Every fourth day you complete today’s cards, gain 1 Booster Potion; Potions apply to 25 additional cards.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="ultra_environment",
        effects=(
            EnvironmentEffect(
                "full_moon_completion_booster",
                "today_cards_complete",
                "inventory_item",
                amount=1,
                every_nth_completion=4,
                inventory_item_id="booster_potion",
            ),
            EnvironmentEffect(
                "full_moon_booster_cards",
                "booster_activation",
                "booster_cards",
                amount=25,
            ),
        ),
    ),
    "eclipse": CatalogItem(
        "eclipse",
        "Celestial Eclipse",
        "scenery",
        "Ultra Rare",
        "drop",
        "+2 Growth on your first 100 cards each Anki day.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="ultra_environment",
        effects=(EnvironmentEffect(
            "celestial_eclipse_growth",
            "eligible_card",
            "growth",
            amount=2,
            first_cards=100,
        ),),
    ),
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
        "Temporarily unavailable",
    ),
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
