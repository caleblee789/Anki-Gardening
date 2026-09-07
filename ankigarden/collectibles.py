from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .balance_catalog import COSMETICS, LANDMARKS, MASTERY_RANKS
from .feature_availability import landmarks_enabled, mastery_enabled
from .environment import GARDEN_FEATURE_CATALOG, GROWTH_CHARGES, SCENERY_CATALOG
from .garden_finds import (
    ENVIRONMENT_TIER_COMPLETION_PITY,
    ENVIRONMENT_TIER_RULES,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_FIND_REGISTRY,
)
from .models.state import CURRENT_CATALOG_SPECIES_ORDER, GROWTH_THRESHOLDS
from .purchases import EffectDescriptor


CollectibleCategory = Literal[
    "plants",
    "scenery",
    "garden_features",
    "garden_beds",
    "growth_items",
    "cosmetics",
    "landmarks",
    "mastery",
]

CATEGORY_LABELS: dict[CollectibleCategory, str] = {
    "plants": "Plants",
    "scenery": "Scenery",
    "garden_features": "Garden decorations",
    "garden_beds": "Garden beds",
    "growth_items": "Growth items",
    "cosmetics": "Gardening Trophies",
    "landmarks": "Garden Landmark",
    "mastery": "Cultivation Mastery",
}

# The Collection grid and compact Entries metric retain the established 39
# discoverable/usable entries. Display Decorations are managed separately, and
# long-term Landmark/Mastery/Legacy progress is projected as project status —
# neither silently inflates the Collection denominator.
COLLECTION_ENTRY_CATEGORIES = frozenset({
    "plants",
    "scenery",
    "garden_features",
    "garden_beds",
    "growth_items",
})


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
    hard_guarantee_completions: int = 0
    progress_completions: int = 0
    completions_until_guaranteed: int = 0

    @property
    def base_chance_text(self) -> str:
        return f"Tier chance: 1 in {self.base_denominator:,} per eligible card"

    @property
    def progress_label(self) -> str:
        return f"Progress to the next guaranteed {self.label} discovery"

    @property
    def unowned_items(self) -> int:
        return max(0, int(self.total_items) - int(self.collected_items))

    @property
    def progress_value_text(self) -> str:
        return (
            f"{self.progress_cards:,} of "
            f"{self.hard_guarantee_cards:,} cards"
        )

    @property
    def guarantee_text(self) -> str:
        card_text = (
            f"{self.cards_until_guaranteed:,} "
            f"{'card' if self.cards_until_guaranteed == 1 else 'cards'}"
        )
        if self.completions_until_guaranteed <= 0:
            return f"Next {self.label} discovery guaranteed within {card_text}"
        completion_text = (
            f"{self.completions_until_guaranteed:,} Today’s Cards "
            f"{'completion' if self.completions_until_guaranteed == 1 else 'completions'}"
        )
        return (
            f"Next {self.label} discovery guaranteed within {card_text} "
            f"or {completion_text}, whichever comes first"
        )

    @property
    def completion_progress_value_text(self) -> str:
        return (
            f"{self.progress_completions:,} of "
            f"{self.hard_guarantee_completions:,} Today’s Cards completions"
        )

    @property
    def completion_text(self) -> str:
        return f"All {self.label} discoveries collected"


_ENVIRONMENT_DISCOVERY_TIERS: tuple[tuple[str, str, str], ...] = (
    ("rare", "rare_environment", "Rare"),
    ("very_rare", "very_rare_environment", "Very Rare"),
    ("ultra", "ultra_environment", "Ultra Rare"),
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
    completion_misses = (
        state.environment_completion_pity_misses
        if isinstance(
            getattr(state, "environment_completion_pity_misses", None), dict
        )
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
        completion_guarantee = max(
            1, int(ENVIRONMENT_TIER_COMPLETION_PITY[drop_tier])
        )
        progress_completions = min(
            max(0, int(completion_misses.get(state_key, 0) or 0)),
            completion_guarantee - 1,
        )
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
            hard_guarantee_completions=completion_guarantee,
            progress_completions=progress_completions,
            completions_until_guaranteed=max(
                1, completion_guarantee - progress_completions
            ),
        ))
    return tuple(result)


def collection_summary(state: Any) -> CollectionSummary:
    views = collection_entry_views(state)
    plant_views = tuple(
        view for view in views if view.definition.category == "plants"
    )
    return CollectionSummary(
        plant_species_owned=sum(1 for view in plant_views if view.owned),
        plant_species_total=len(plant_views),
        collectibles_owned=sum(1 for view in views if view.owned),
        collectibles_total=len(views),
    )


def collection_entry_registry() -> tuple[CollectibleDefinition, ...]:
    """Return the canonical 39 records allowed in the Collection grid."""

    return tuple(
        definition
        for definition in collectible_registry()
        if definition.category in COLLECTION_ENTRY_CATEGORIES
    )


def collection_entry_views(state: Any) -> tuple[CollectibleView, ...]:
    """Project only actual Collection entries, excluding project/status rows."""

    return tuple(
        view
        for view in collectible_views(state)
        if view.definition.category in COLLECTION_ENTRY_CATEGORIES
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


def _cosmetic_definitions() -> Iterable[CollectibleDefinition]:
    for item in COSMETICS:
        source_id = str(item.cosmetic_id)
        yield CollectibleDefinition(
            item_id=f"cosmetics:{source_id}",
            name=item.display_name,
            category="cosmetics",
            rarity="Gardening Trophy",
            descriptor=EffectDescriptor(
                function="Celebrates your achievement in the Trophy Room.",
                buff=item.buff_description,
                activation_condition="Activates automatically after unlocking.",
                duration="Permanent.",
                stacking="All three trophies can be active together, alongside your equipped items.",
                replacement="No equipment slot required.",
                unlock_requirement=(
                    f"Buy in the Nursery for {int(item.price_coins):,} Garden Coins."
                    if item.purchasable and item.price_coins is not None
                    else "Earn from its cumulative achievement."
                ),
            ),
            source_kind="cosmetic",
            source_id=source_id,
        )


def _landmark_definitions() -> Iterable[CollectibleDefinition]:
    for item in LANDMARKS:
        source_id = str(item.landmark_id)
        yield CollectibleDefinition(
            item_id=f"landmarks:{source_id}",
            name=item.display_name,
            category="landmarks",
            rarity="Landmark",
            descriptor=EffectDescriptor(
                function="Permanently transforms the shared Garden Landmark anchor.",
                buff="Cosmetic only. Landmark completion creates no economic multiplier.",
                activation_condition="Complete each Landmark project in sequence after the first Full Bloom.",
                duration="Completed appearances remain selectable permanently.",
                stacking="One completed Landmark appearance is displayed at a time.",
                replacement="Completing a later tier never removes earlier appearances.",
                unlock_requirement=(
                    f"Contribute {item.growth_cost:,} Stored Growth, then "
                    f"complete it for {item.coin_cost:,} Garden Coins."
                ),
            ),
            source_kind="landmark",
            source_id=source_id,
        )


def _mastery_definitions() -> Iterable[CollectibleDefinition]:
    for species in CURRENT_CATALOG_SPECIES_ORDER:
        species_name = species.replace("_", " ").title()
        for rank in MASTERY_RANKS:
            rank_id = str(rank.rank_id)
            source_id = f"{species}:{rank_id}"
            yield CollectibleDefinition(
                item_id=f"mastery:{source_id}",
                name=f"{species_name} — {rank.display_name} Cultivation",
                category="mastery",
                rarity="Mastery",
                descriptor=EffectDescriptor(
                    function=f"Unlocks the {rank.display_name} cosmetic mastery treatment for {species_name}.",
                    buff="Cosmetic only. Mastery never changes Growth, Garden Coins, or Find odds.",
                    activation_condition="The species must have reached Full Bloom.",
                    duration="The mastery treatment remains unlocked permanently.",
                    stacking="Ranks unlock sequentially for each species.",
                    replacement="A higher rank never repeats normal plant progression rewards.",
                    unlock_requirement=(
                        f"Spend {rank.growth_cost:,} Stored Growth and "
                        f"{rank.coin_cost:,} Garden Coins."
                    ),
                ),
                source_kind="mastery",
                source_id=source_id,
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
    basic_duration = f"{basic_fertilizer.card_count:,} eligible cards"
    plants = tuple(_species_definition(species) for species in CURRENT_CATALOG_SPECIES_ORDER)
    environments = tuple(_environment_definitions())
    cosmetics = tuple(_cosmetic_definitions())
    landmarks = tuple(_landmark_definitions()) if landmarks_enabled() else ()
    mastery = tuple(_mastery_definitions()) if mastery_enabled() else ()
    beds = tuple(
        CollectibleDefinition(
            item_id=f"garden_beds:{index}",
            name=f"Garden bed {index + 1}",
            category="garden_beds",
            rarity="",
            descriptor=EffectDescriptor(
                function="Provides one garden location for a collected plant.",
                buff=(
                    "Each other planted bed adds a Shared Growth lane: 10%, "
                    "or 15% with the Golden Trowel. Full Bloom lanes redirect "
                    "to unfinished plants, then Stored Growth."
                ),
                activation_condition="Active after the bed is unlocked.",
                duration="Stays unlocked.",
                stacking="Each unlocked bed adds one location, up to six.",
                replacement="Replaces nothing.",
                unlock_requirement=(
                    "Included." if index < 2 else "Earn from plant progression."
                ),
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
                stacking="Same tier adds cards; a different tier waits its turn.",
                replacement="Remaining paid cards are never replaced.",
                unlock_requirement="Found while reviewing.",
            ),
            source_kind="growth_item",
            source_id=rich_compost.inventory_item_id,
        ),
        *(
            CollectibleDefinition(
                item_id=f"growth_items:fertilizer_{tier}",
                name=spec.name,
                category="growth_items",
                rarity="",
                descriptor=EffectDescriptor(
                    function=f"Adds one {spec.name} to Growth Items inventory.",
                    buff=(
                        f"+{spec.growth_per_answer:,} Growth per eligible card answer while active."
                    ),
                    activation_condition=(
                        "Use on a nurtured plant that is still growing."
                    ),
                    duration=f"{spec.card_count:,} eligible cards",
                    stacking=(
                        "Same tier adds cards; a different tier waits its turn."
                    ),
                    replacement="Remaining paid cards are never replaced.",
                    unlock_requirement="Buy in the Nursery.",
                ),
                source_kind="growth_item",
                source_id=f"fertilizer_{tier}",
            )
            for tier, spec in GardenGameEngine.FERTILIZERS.items()
            if tier != "basic"
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
    return (
        *plants,
        *environments,
        *beds,
        *growth_items,
        *cosmetics,
        *landmarks,
        *mastery,
    )


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
    loadout = getattr(state, "loadout", None)
    project = getattr(state, "garden_project", None)
    completed_landmarks = set(
        getattr(project, "completed_project_ids", ()) or ()
    )
    mastery_state = getattr(state, "cultivation_mastery", None)
    highest_mastery = dict(
        getattr(mastery_state, "highest_rank_by_species", {}) or {}
    )
    mastery_order = tuple(str(rank.rank_id) for rank in MASTERY_RANKS)
    landmark_by_id = {str(item.landmark_id): item for item in LANDMARKS}
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
            displayed_id = (
                str(getattr(loadout, "display_decoration_id", "") or "")
                if definition.category == "garden_features"
                else str(getattr(loadout, "display_scenery_id", "") or "")
            )
            views.append(CollectibleView(
                definition,
                owned,
                equipped=displayed_id == source_id,
                selected=displayed_id == source_id,
            ))
        elif definition.category == "cosmetics":
            owned = source_id in (inventory.get("cosmetics", []) or [])
            equipped = False
            views.append(CollectibleView(
                definition,
                owned,
                equipped=equipped,
                selected=equipped,
                quantity=1 if owned else 0,
            ))
        elif definition.category == "landmarks":
            selected_id = str(
                getattr(project, "selected_project_id", "") or ""
            )
            displayed_id = str(
                getattr(project, "displayed_project_id", "") or ""
            )
            item = landmark_by_id[source_id]
            current_growth = (
                max(
                    0,
                    int(getattr(project, "contributed_growth_units", 0) or 0),
                ) // 100
                if selected_id == source_id else 0
            )
            views.append(CollectibleView(
                definition,
                source_id in completed_landmarks,
                equipped=displayed_id == source_id,
                selected=selected_id == source_id,
                quantity=1 if source_id in completed_landmarks else 0,
                progress_current=(
                    item.growth_cost
                    if source_id in completed_landmarks else current_growth
                ),
                progress_target=item.growth_cost,
            ))
        elif definition.category == "mastery":
            species, _separator, rank_id = source_id.partition(":")
            target_rank_index = mastery_order.index(rank_id)
            current_rank = highest_mastery.get(species, "")
            current_rank_index = (
                mastery_order.index(current_rank)
                if current_rank in mastery_order else -1
            )
            owned = current_rank_index >= target_rank_index
            views.append(CollectibleView(
                definition,
                owned,
                quantity=1 if owned else 0,
                progress_current=max(0, current_rank_index + 1),
                progress_target=target_rank_index + 1,
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
