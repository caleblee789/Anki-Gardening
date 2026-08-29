from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .environment import GARDEN_FEATURE_CATALOG, GROWTH_CHARGES, SCENERY_CATALOG
from .garden_finds import (
    ENVIRONMENT_TIER_RULES,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_FIND_REGISTRY,
)
from .models.state import CURRENT_CATALOG_SPECIES_ORDER, GROWTH_THRESHOLDS
from .purchases import EffectDescriptor, compact_duration


CollectibleCategory = Literal[
    "plants",
    "scenery",
    "garden_features",
    "decorations",
    "garden_beds",
    "growth_items",
]

CATEGORY_LABELS: dict[CollectibleCategory, str] = {
    "plants": "Plants",
    "scenery": "Scenery",
    "garden_features": "Garden Features",
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


@dataclass(frozen=True)
class CollectionSummary:
    """Explicit category and whole-registry counts for collection copy."""

    plant_species_owned: int
    plant_species_total: int
    collectibles_owned: int
    collectibles_total: int


@dataclass(frozen=True)
class EnvironmentDiscoveryProgress:
    """One Collection-only view of a finite environment guarantee."""

    tier: str
    label: str
    base_denominator: int
    hard_guarantee_cards: int
    progress_cards: int
    cards_until_guaranteed: int
    collected_items: int
    total_items: int
    completed: bool

    @property
    def base_chance_text(self) -> str:
        return f"Base chance: 1 in {self.base_denominator:,} per card"

    @property
    def progress_label(self) -> str:
        return f"{self.label} guarantee progress"

    @property
    def progress_value_text(self) -> str:
        return (
            f"{self.progress_cards:,} of "
            f"{self.hard_guarantee_cards:,} cards"
        )

    @property
    def guarantee_text(self) -> str:
        return (
            f"Next {self.label} discovery guaranteed within "
            f"{self.cards_until_guaranteed:,} "
            f"{'card' if self.cards_until_guaranteed == 1 else 'cards'}"
        )

    @property
    def completion_text(self) -> str:
        return f"All {self.label} discoveries collected"


_ENVIRONMENT_DISCOVERY_TIERS: tuple[tuple[str, str, str], ...] = (
    ("rare", "rare_environment", "Rare"),
    ("very_rare", "very_rare_environment", "Very Rare"),
    ("ultra", "ultra_environment", "Ultra"),
)


def environment_discovery_progress(
    state: Any,
) -> tuple[EnvironmentDiscoveryProgress, ...]:
    """Project the three independent environment guarantees for Collection.

    Counters remain implementation state.  This projection gives Collection a
    finite and plainly labelled card count without exposing Standard Find
    drought state to any player-facing surface.
    """

    inventory = (
        state.inventory
        if isinstance(getattr(state, "inventory", None), dict)
        else {}
    )
    owned_features = {
        str(item_id) for item_id in (inventory.get("garden_features", []) or [])
    }
    owned_scenery = {
        str(item_id)
        for item_id in (
            *(inventory.get("scenery", []) or []),
            *(inventory.get("backgrounds", []) or []),
        )
    }
    misses = (
        state.environment_pity_misses
        if isinstance(getattr(state, "environment_pity_misses", None), dict)
        else {}
    )
    result: list[EnvironmentDiscoveryProgress] = []
    for state_key, drop_tier, label in _ENVIRONMENT_DISCOVERY_TIERS:
        items = tuple(
            item for item in SPECIAL_ENVIRONMENT_POOL
            if item.tier == drop_tier
        )
        collected = sum(
            1
            for item in items
            if item.item_id in (
                owned_features
                if item.environment_kind == "garden_feature"
                else owned_scenery
            )
        )
        completed = bool(items) and collected == len(items)
        rule = ENVIRONMENT_TIER_RULES[drop_tier]
        # A healthy pending tier can hold at most threshold - 1 misses: the
        # threshold card awards the discovery and resets the tier.  Clamping a
        # repaired or forward-written value keeps the next guarantee finite.
        progress_cards = min(
            max(0, int(misses.get(state_key, 0) or 0)),
            max(0, int(rule.hard_pity_answers) - 1),
        )
        cards_until = max(1, int(rule.hard_pity_answers) - progress_cards)
        result.append(EnvironmentDiscoveryProgress(
            tier=state_key,
            label=label,
            base_denominator=int(rule.base_denominator),
            hard_guarantee_cards=int(rule.hard_pity_answers),
            progress_cards=progress_cards,
            cards_until_guaranteed=cards_until,
            collected_items=collected,
            total_items=len(items),
            completed=completed,
        ))
    return tuple(result)


def collection_summary(state: Any) -> CollectionSummary:
    views = collectible_views(state)
    plant_views = tuple(
        view for view in views if view.definition.category == "plants"
    )
    return CollectionSummary(
        plant_species_owned=sum(1 for view in plant_views if view.owned),
        plant_species_total=len(plant_views),
        collectibles_owned=sum(1 for view in views if view.owned),
        collectibles_total=len(views),
    )


def _species_definition(species: str) -> CollectibleDefinition:
    name = species.replace("_", " ").title()
    return CollectibleDefinition(
        item_id=f"plant:{species}",
        name=name,
        category="plants",
        rarity="Collectible",
        descriptor=EffectDescriptor(
            function="A plant species with six Growth stages.",
            buff="Species is cosmetic. Every plant uses the same Growth and reward rules.",
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
    for category, catalog in (
        ("scenery", SCENERY_CATALOG),
        ("garden_features", GARDEN_FEATURE_CATALOG),
    ):
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
    basic_duration = compact_duration(basic_fertilizer.duration_seconds)
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
                buff=(
                    "Each planted plant adds a 20% Shared Growth share. When a "
                    "plant reaches Full Bloom, its share is divided among planted "
                    "plants still growing."
                ),
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
                    "card while active."
                ),
                activation_condition=(
                    "Use on a nurtured plant that is still growing."
                ),
                duration=basic_duration,
                stacking="Same tier adds time; a different tier waits its turn.",
                replacement="Remaining paid time is never replaced.",
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
        elif definition.category in {"garden_features", "scenery"}:
            owned = source_id in (inventory.get(definition.category, []) or [])
            equipped_id = (
                state.loadout.garden_feature_id
                if definition.category == "garden_features"
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
