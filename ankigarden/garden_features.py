from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    GARDEN_FEATURE_CATALOG,
    LEGACY_WEATHER_TO_GARDEN_FEATURE,
    CatalogItem,
    canonical_garden_feature_id,
)

GardenFeatureEffectKey = Literal[
    "none",
    "growth_every_10_plus_1",
    "completion_coins_plus_5",
    "growth_every_5_plus_1",
    "booster_cards_multiplier_1_25",
    "growth_every_4_plus_3",
    "prism_bank_per_answer_1_5",
]


@dataclass(frozen=True)
class GardenFeatureDefinition:
    item: CatalogItem
    effect_key: GardenFeatureEffectKey
    asset_id: str


FEATURE_EFFECT_KEYS: dict[str, GardenFeatureEffectKey] = {
    "seedling_sign": "none",
    "wind_chime": "growth_every_10_plus_1",
    "harvest_bell": "completion_coins_plus_5",
    "watering_station": "growth_every_5_plus_1",
    "herbalist_hourglass": "booster_cards_multiplier_1_25",
    "firefly_lantern": "growth_every_4_plus_3",
    "prism_trellis": "prism_bank_per_answer_1_5",
}

GARDEN_FEATURES: dict[str, GardenFeatureDefinition] = {
    item_id: GardenFeatureDefinition(
        item=item,
        effect_key=FEATURE_EFFECT_KEYS[item_id],
        asset_id=f"garden_feature_{item_id}",
    )
    for item_id, item in GARDEN_FEATURE_CATALOG.items()
}


def garden_feature(item_id: object) -> GardenFeatureDefinition | None:
    return GARDEN_FEATURES.get(canonical_garden_feature_id(item_id))


__all__ = [
    "DEFAULT_GARDEN_FEATURE_ID",
    "FEATURE_EFFECT_KEYS",
    "GARDEN_FEATURES",
    "LEGACY_WEATHER_TO_GARDEN_FEATURE",
    "GardenFeatureDefinition",
    "GardenFeatureEffectKey",
    "canonical_garden_feature_id",
    "garden_feature",
]
