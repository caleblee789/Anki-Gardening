"""One complete effect line derived from each appearance item's mechanics."""

from dataclasses import dataclass

from .balance_catalog import COMPLETION_TRIGGER_COPY, format_appearance_effect


def appearance_effect_copy(item_id: str, fallback: str = "") -> str:
    from .balance_catalog import GARDEN_BONUS_BY_ID, SCENERY_BY_ID
    key = str(item_id or "").strip().casefold()
    item = GARDEN_BONUS_BY_ID.get(key) or SCENERY_BY_ID.get(key)
    return format_appearance_effect(item) if item is not None else fallback


def gift_contents_copy(item_id: str) -> tuple[str, ...]:
    from .balance_catalog import CONSUMABLE_BY_ID, SCENERY_BY_ID
    item = SCENERY_BY_ID[item_id]
    return tuple(
        f"{CONSUMABLE_BY_ID[entry.grant.item_id].display_name}: {entry.weight_percent}%"
        for effect in item.effects for entry in effect.weighted_grants
    )


@dataclass(frozen=True)
class AppearanceEffectGroup:
    effect: str
    conditions: tuple[str, ...] = ()


def appearance_effect_groups(item_id: str, state=None) -> tuple[AppearanceEffectGroup, ...]:
    text = appearance_effect_copy(item_id)
    return (AppearanceEffectGroup(text),) if text else ()
