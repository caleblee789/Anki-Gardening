from __future__ import annotations

from types import SimpleNamespace

from ankigarden.environment import (
    GARDEN_FEATURE_CATALOG,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
)
from ankigarden.garden_finds import SPECIAL_ENVIRONMENT_POOL
from ankigarden.growth import canonical_stage_projection, stage_presentation
from ankigarden.models.state import (
    CURRENT_CATALOG_SPECIES_ORDER,
    GardenState,
    MAX_GARDEN_SLOTS,
)
from ankigarden.presentation import (
    GARDEN_DISCOVERY_INTERNAL_ID,
    STANDARD_FIND_INTERNAL_ID,
    PlantIdentity,
    project_collection,
    project_garden_appearance,
    visible_reward_term,
)


def test_canonical_stage_projection_retains_rare_as_only_the_internal_id() -> None:
    stages = canonical_stage_projection()

    assert [stage.stage_id for stage in stages] == [
        "seed",
        "sprout",
        "young",
        "mature",
        "flowering",
        "rare",
    ]
    assert [stage.display_name for stage in stages] == [
        "Seed",
        "Sprout",
        "Young",
        "Mature",
        "Flowering",
        "Full Bloom",
    ]
    assert [stage.display_ordinal for stage in stages] == [1, 2, 3, 4, 5, 6]
    assert {stage.display_total for stage in stages} == {6}
    assert stage_presentation("Full Bloom") == stages[-1]
    assert stage_presentation("rare") == stages[-1]


def test_plant_identity_preserves_the_instance_name_and_species_name() -> None:
    identity = PlantIdentity.from_plant(SimpleNamespace(
        plant_id="bonsai-1",
        species="bonsai",
        name="Bonsai Plant",
    ))

    assert identity == PlantIdentity(
        plant_id="bonsai-1",
        display_name="Bonsai Plant",
        species_name="Bonsai",
    )


def test_collection_projection_names_exact_species_and_registry_denominators() -> None:
    state = GardenState()
    state.unlocked_species = list(CURRENT_CATALOG_SPECIES_ORDER)
    state.unlocked_slots = MAX_GARDEN_SLOTS
    state.inventory["garden_features"] = [
        item_id
        for item_id, item in GARDEN_FEATURE_CATALOG.items()
        if not item.drop_only
    ]
    state.inventory["scenery"] = [
        item_id
        for item_id, item in SCENERY_CATALOG.items()
        if not item.drop_only
    ]
    state.consumables["booster_potion"] = 1
    for charge_id in GROWTH_CHARGES:
        state.consumables[charge_id] = 1

    projection = project_collection(state)

    assert (projection.species_discovered, projection.species_total) == (10, 10)
    assert (
        projection.collection_entries_discovered,
        projection.collection_entries_total,
    ) == (30, 39)
    assert projection.collection_complete
    assert projection.species_text == "10 of 10 species discovered"
    assert projection.collection_entries_text == (
        "30 of 39 collection entries discovered"
    )


def test_garden_appearance_keeps_display_bonus_scenery_and_effects_distinct() -> None:
    state = GardenState()
    day = state.daily_stats.day
    state.loadout.scenery_id = "default"
    state.loadout.displayed_garden_feature_id = "seedling_sign"
    state.loadout.active_bonus_garden_feature_id = "wind_chime"
    state.loadout.visibility["garden_feature"] = True
    state.daily_loadout.garden_bonus_anki_day_id = day
    state.daily_loadout.garden_bonus_locked_at_ms = 100
    state.daily_loadout.garden_feature_id = "watering_station"

    projection = project_garden_appearance(state)

    assert projection.to_dict() == {
        "scenery_id": "default",
        "displayed_decoration_id": "seedling_sign",
        "active_bonus_decoration_id": "watering_station",
        "visual_effects_enabled": True,
    }
    assert projection.summary_rows == (
        ("Scenery", "Verdant Twilight"),
        ("Displayed decoration", "Seedling Sign"),
        ("Active garden bonus", "Watering Station"),
        ("Visual effects", "On"),
    )


def test_find_vocabulary_changes_visible_copy_without_changing_internal_ids() -> None:
    standard = visible_reward_term(STANDARD_FIND_INTERNAL_ID)
    discovery = visible_reward_term(GARDEN_DISCOVERY_INTERNAL_ID)

    assert standard.internal_id == STANDARD_FIND_INTERNAL_ID
    assert standard.label(2, include_quantity=True) == "2 Standard Finds"
    assert discovery.internal_id == GARDEN_DISCOVERY_INTERNAL_ID
    assert discovery.label(1, include_quantity=True) == "1 Garden discovery"
    assert discovery.label(2) == "Garden discoveries"


def test_environment_pool_unlock_copy_never_calls_a_discovery_a_standard_find() -> None:
    catalog_by_identity = {
        (item.kind, item.item_id): item
        for catalog in (GARDEN_FEATURE_CATALOG, SCENERY_CATALOG)
        for item in catalog.values()
        if item.drop_only
    }
    pool_identities = {
        (item.environment_kind, item.item_id)
        for item in SPECIAL_ENVIRONMENT_POOL
    }

    assert set(catalog_by_identity) == pool_identities
    for identity in sorted(pool_identities):
        item = catalog_by_identity[identity]
        # Nursery and Collection both expose this catalog copy; the descriptor
        # is the renderer-neutral projection used by shared item details.
        visible_copy = item.how_to_earn
        projected_copy = item.descriptor.unlock_requirement
        assert visible_copy == (
            "Discover through an occasional Garden discovery while reviewing."
        )
        assert projected_copy == visible_copy
        assert "Standard Find" not in visible_copy
