from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .environment import GROWTH_CHARGES, SCENERY_CATALOG, WEATHER_CATALOG
from .garden_finds import STANDARD_FIND_REGISTRY
from .models.state import CURRENT_CATALOG_SPECIES_ORDER, GROWTH_THRESHOLDS
from .purchases import EffectDescriptor


CollectibleCategory = Literal[
    "plants",
    "scenery",
    "weather",
    "decorations",
    "garden_beds",
    "growth_items",
]

CATEGORY_LABELS: dict[CollectibleCategory, str] = {
    "plants": "Plants",
    "scenery": "Scenery",
    "weather": "Weather",
    "decorations": "Decorations",
    "garden_beds": "Garden beds",
    "growth_items": "Growth items",
}


@dataclass(frozen=True)
class CollectibleDefinition:
    item_id: str
    name: str
    category: CollectibleCategory
    rarity: str
    descriptor: EffectDescriptor
    mystery: bool = False
    source_kind: str = "registry"
    source_id: str = ""


@dataclass(frozen=True)
class CollectibleView:
    definition: CollectibleDefinition
    owned: bool
    equipped: bool = False
    selected: bool = False
    quantity: int = 0
    progress_current: int = 0
    progress_target: int = 1

    @property
    def concealed(self) -> bool:
        return self.definition.mystery and not self.owned

    @property
    def state_label(self) -> str:
        if self.equipped:
            return "Equipped"
        if self.selected:
            return "Selected"
        if self.owned:
            return "Owned"
        if self.concealed:
            return "Mystery, Locked"
        return "Locked"


def _species_definition(species: str) -> CollectibleDefinition:
    name = species.replace("_", " ").title()
    return CollectibleDefinition(
        item_id=f"plant:{species}",
        name=name,
        category="plants",
        rarity="Collectible",
        descriptor=EffectDescriptor(
            function="A plant species with six Growth stages.",
            buff="The nurtured plant receives Growth from card answers.",
            activation_condition="Place the plant in a garden bed and nurture it.",
            duration="Growth stays with the plant.",
            stacking="Each plant keeps its own Growth and care state.",
            replacement="Moving or removing a plant never erases its Growth.",
            unlock_requirement="Choose a starter or obtain another instance from the Nursery.",
        ),
        source_kind="plant",
        source_id=species,
    )


def _environment_definitions() -> Iterable[CollectibleDefinition]:
    for category, catalog in (("scenery", SCENERY_CATALOG), ("weather", WEATHER_CATALOG)):
        for item in catalog.values():
            yield CollectibleDefinition(
                item_id=f"{category}:{item.item_id}",
                name=item.name,
                category=category,
                rarity=item.rarity,
                descriptor=item.descriptor,
                # Mystery is explicit product metadata: only undiscovered,
                # drop-only environment rewards conceal identity and artwork.
                mystery=item.drop_only,
                source_kind=item.kind,
                source_id=item.item_id,
            )


def collectible_registry() -> tuple[CollectibleDefinition, ...]:
    """Return the complete ordered registry used by Collection categories."""

    from .game import GardenGameEngine

    rich_compost = next(
        reward
        for reward in STANDARD_FIND_REGISTRY
        if reward.inventory_item_id == "fertilizer_basic"
    )
    basic_fertilizer = GardenGameEngine.FERTILIZERS["basic"]
    basic_duration = GardenGameEngine._duration_label(
        basic_fertilizer.duration_seconds
    )

    plants = tuple(_species_definition(species) for species in CURRENT_CATALOG_SPECIES_ORDER)
    environments = tuple(_environment_definitions())
    decorations = (
        CollectibleDefinition(
            item_id="decorations:lantern",
            name="Garden Lantern",
            category="decorations",
            rarity="Common",
            descriptor=EffectDescriptor(
                function="Adds a warm lantern to the garden scene.",
                buff="Adds a warm light to your garden.",
                activation_condition="Active while equipped.",
                duration="Shown until unequipped.",
                stacking="One Decoration at a time.",
                replacement="Another Decoration replaces it; ownership stays.",
                unlock_requirement="Included with Anki Garden.",
            ),
            source_kind="decoration",
            source_id="lantern",
        ),
    )
    beds = tuple(
        CollectibleDefinition(
            item_id=f"garden_beds:{index}",
            name=f"Garden bed {index + 1}",
            category="garden_beds",
            rarity="",
            descriptor=EffectDescriptor(
                function="Provides one garden location for a collected plant.",
                buff="Lets one additional plant appear in the garden.",
                activation_condition="Active after the bed is unlocked.",
                duration="Stays unlocked.",
                stacking="Each unlocked bed adds one location, up to six.",
                replacement="Replaces nothing.",
                unlock_requirement="Unlock the next bed in the Nursery.",
            ),
            source_kind="garden_bed",
            source_id=str(index),
        )
        for index in range(6)
    )
    growth_items = [
        CollectibleDefinition(
            item_id="growth_items:fertilizer_basic",
            name=rich_compost.display_name,
            category="growth_items",
            rarity=rich_compost.tier,
            descriptor=EffectDescriptor(
                function=(
                    "Adds "
                    f"{rich_compost.description.removeprefix('+').strip()} "
                    "to Growth Items inventory."
                ),
                buff=(
                    f"+{basic_fertilizer.growth_per_answer:,} Growth per "
                    "card answer while active."
                ),
                activation_condition=(
                    "Use on a nurtured plant that is still growing."
                ),
                duration=(
                    f"Lasts {basic_duration}; another {basic_fertilizer.name} "
                    "adds more time."
                ),
                stacking="Inventory quantities stack; active duration extends.",
                replacement=(
                    "A different active Fertilizer is replaced only after "
                    "confirmation; its remaining time is discarded."
                ),
                unlock_requirement="Found while reviewing.",
            ),
            source_kind="growth_item",
            source_id=rich_compost.inventory_item_id,
        ),
        CollectibleDefinition(
            item_id="growth_items:booster_potion",
            name="Booster Potion",
            category="growth_items",
            rarity="Rare",
            descriptor=GardenGameEngine.booster_descriptor(),
            source_kind="growth_item",
            source_id="booster_potion",
        )
    ]
    growth_items.extend(
        CollectibleDefinition(
            item_id=f"growth_items:{charge.charge_id}",
            name=charge.name,
            category="growth_items",
            rarity=charge.rarity,
            descriptor=charge.descriptor,
            source_kind="growth_item",
            source_id=charge.charge_id,
        )
        for charge in GROWTH_CHARGES.values()
    )
    return (*plants, *environments, *decorations, *beds, *growth_items)


def collection_categories(
    registry: Iterable[CollectibleDefinition] | None = None,
) -> tuple[tuple[CollectibleCategory, str], ...]:
    definitions = tuple(registry or collectible_registry())
    present = {item.category for item in definitions}
    return tuple(
        (category, label)
        for category, label in CATEGORY_LABELS.items()
        if category in present
    )


def collectible_views(state: Any) -> tuple[CollectibleView, ...]:
    """Project one persisted GardenState into typed Collection card states."""

    inventory = state.inventory if isinstance(getattr(state, "inventory", None), dict) else {}
    plants = list(getattr(state, "plants", []) or [])
    owned_species = {
        str(value) for value in getattr(state, "unlocked_species", []) or []
    } | {str(getattr(plant, "species", "")) for plant in plants}
    views: list[CollectibleView] = []
    for definition in collectible_registry():
        source_id = definition.source_id
        if definition.category == "plants":
            instances = [plant for plant in plants if str(getattr(plant, "species", "")) == source_id]
            highest = max((int(getattr(plant, "growth_points", 0)) for plant in instances), default=0)
            views.append(CollectibleView(
                definition,
                source_id in owned_species or bool(instances),
                quantity=len(instances),
                progress_current=highest,
                progress_target=GROWTH_THRESHOLDS[-1],
            ))
        elif definition.category in {"weather", "scenery"}:
            owned = source_id in (inventory.get(definition.category, []) or [])
            equipped_id = (
                state.loadout.weather_id
                if definition.category == "weather"
                else state.loadout.scenery_id
            )
            views.append(CollectibleView(definition, owned, equipped=equipped_id == source_id))
        elif definition.category == "decorations":
            owned = source_id in (inventory.get("decorations", []) or [])
            views.append(CollectibleView(
                definition, owned, equipped=state.loadout.decoration_id == source_id
            ))
        elif definition.category == "garden_beds":
            index = int(source_id)
            views.append(CollectibleView(
                definition,
                index < int(getattr(state, "unlocked_slots", 0)),
                progress_current=min(int(getattr(state, "unlocked_slots", 0)), index + 1),
                progress_target=index + 1,
            ))
        else:
            quantity = max(0, int((getattr(state, "consumables", {}) or {}).get(source_id, 0)))
            views.append(CollectibleView(definition, quantity > 0, quantity=quantity))
    return tuple(views)
