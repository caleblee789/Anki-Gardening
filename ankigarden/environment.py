from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .purchases import EffectDescriptor


EnvironmentKind = Literal["weather", "scenery"]
AcquisitionKind = Literal["free", "purchase", "drop"]
Rarity = Literal["Common", "Uncommon", "Rare", "Very Rare", "Ultra Rare"]
DropTier = Literal[
    "ultra_environment",
    "very_rare_environment",
    "rare_environment",
]


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

    @property
    def purchasable(self) -> bool:
        return self.acquisition == "purchase" and self.price is not None

    @property
    def drop_only(self) -> bool:
        return self.acquisition == "drop"

    @property
    def descriptor(self) -> EffectDescriptor:
        kind_name = "Weather" if self.kind == "weather" else "Scenery"
        other_kind = "Scenery" if self.kind == "weather" else "Weather"
        return EffectDescriptor(
            function=f"Changes {kind_name} and applies its passive.",
            buff=self.effect,
            activation_condition="Active while equipped, even if its artwork is hidden.",
            duration="Owned permanently; active until replaced.",
            stacking=f"One {kind_name} at a time; stacks with {other_kind} passives.",
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


WEATHER_CATALOG: dict[str, CatalogItem] = {
    "sunny": CatalogItem(
        "sunny",
        "Clear Skies",
        "weather",
        "Common",
        "free",
        "No gameplay bonus.",
        "Included.",
    ),
    "breeze": CatalogItem(
        "breeze",
        "Soft Breeze",
        "weather",
        "Common",
        "purchase",
        "+1 Growth on your first 10 card answers each Anki day.",
        "Nursery: 100 Garden Coins.",
        100,
    ),
    "cloudy": CatalogItem(
        "cloudy",
        "Cloudy Drift",
        "weather",
        "Common",
        "purchase",
        "+2 Garden Coins when you finish all due cards that day.",
        "Nursery: 175 Garden Coins.",
        175,
    ),
    "gentle_rain": CatalogItem(
        "gentle_rain",
        "Gentle Rain",
        "weather",
        "Uncommon",
        "purchase",
        "+1 Growth on your first 20 card answers each Anki day.",
        "Nursery: 250 Garden Coins.",
        250,
    ),
    "snow_flurry": CatalogItem(
        "snow_flurry",
        "Snow Flurry",
        "weather",
        "Uncommon",
        "purchase",
        "Booster Potions last 10% longer while this weather is equipped.",
        "Nursery: 350 Garden Coins.",
        350,
    ),
    "fireflies": CatalogItem(
        "fireflies",
        "Firefly Evening",
        "weather",
        "Rare",
        "drop",
        "+5 Growth on your first 5 card answers each Anki day.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="rare_environment",
    ),
    "rainbow_sunshower": CatalogItem(
        "rainbow_sunshower",
        "Rainbow Sunshower",
        "weather",
        "Very Rare",
        "drop",
        "+5 Growth when you finish all due cards that day.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="very_rare_environment",
    ),
}


SCENERY_CATALOG: dict[str, CatalogItem] = {
    "default": CatalogItem(
        "default",
        "Verdant Twilight",
        "scenery",
        "Common",
        "free",
        "No gameplay bonus.",
        "Included.",
    ),
    "spring": CatalogItem(
        "spring",
        "Spring Bloom",
        "scenery",
        "Common",
        "purchase",
        "+1 Growth on your first 25 card answers each Anki day.",
        "Nursery: 400 Garden Coins.",
        400,
    ),
    "summer": CatalogItem(
        "summer",
        "Golden Summer",
        "scenery",
        "Uncommon",
        "purchase",
        "+1 Growth on every second card answer.",
        "Nursery: 600 Garden Coins.",
        600,
    ),
    "autumn": CatalogItem(
        "autumn",
        "Autumn Hearth",
        "scenery",
        "Uncommon",
        "purchase",
        "+25% Garden Coins from plant stage rewards; halves round up.",
        "Nursery: 800 Garden Coins.",
        800,
    ),
    "snowy": CatalogItem(
        "snowy",
        "Snow-Covered Garden",
        "scenery",
        "Rare",
        "purchase",
        "First card answer each Anki day gives 1 Small Growth Charge.",
        "Nursery: 1,200 Garden Coins.",
        1_200,
    ),
    "rainbow_horizon": CatalogItem(
        "rainbow_horizon",
        "Rainbow Horizon",
        "scenery",
        "Rare",
        "drop",
        "+1 Growth on every card answer.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="rare_environment",
    ),
    "halloween": CatalogItem(
        "halloween",
        "Halloween Garden",
        "scenery",
        "Very Rare",
        "drop",
        "First daily answer: Small Charge 70%, Standard Charge 25%, or Booster Potion 5%.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="very_rare_environment",
    ),
    "full_moon": CatalogItem(
        "full_moon",
        "Full Moon Garden",
        "scenery",
        "Ultra Rare",
        "drop",
        "First daily answer gives 1 Booster Potion; Potions last 25% longer.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="ultra_environment",
    ),
    "eclipse": CatalogItem(
        "eclipse",
        "Celestial Eclipse",
        "scenery",
        "Ultra Rare",
        "drop",
        "+10 Scenery Growth per card answer; doubles base Growth only.",
        "Discover through an occasional Garden Find while reviewing.",
        drop_tier="ultra_environment",
    ),
}


ENVIRONMENT_CATALOG: dict[str, dict[str, CatalogItem]] = {
    "weather": WEATHER_CATALOG,
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
        "Not currently obtainable.",
    ),
}


DEFAULT_WEATHER_ID = "sunny"
DEFAULT_SCENERY_ID = "default"


def environment_item(kind: str, item_id: str) -> CatalogItem | None:
    return ENVIRONMENT_CATALOG.get(str(kind), {}).get(str(item_id))


def catalog_items(kind: str | None = None) -> tuple[CatalogItem, ...]:
    if kind is not None:
        return tuple(ENVIRONMENT_CATALOG.get(str(kind), {}).values())
    return tuple(
        item for catalog in ENVIRONMENT_CATALOG.values() for item in catalog.values()
    )
