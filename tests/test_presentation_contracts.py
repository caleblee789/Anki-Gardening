from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def test_plant_identity_without_stage_preserves_id_and_uses_species() -> None:
    identity = PlantIdentity.from_plant(SimpleNamespace(
        plant_id="bonsai-1",
        species="bonsai",
        name="Bonsai Plant",
    ))

    assert identity == PlantIdentity(
        plant_id="bonsai-1",
        display_name="Bonsai",
        species_name="Bonsai",
    )


@pytest.mark.parametrize("stage,label,title", [
    ("seed", "Seed", "{species} Seed"),
    ("sprout", "Sprout", "{species} Sprout"),
    ("young", "Young", "Young {species}"),
    ("mature", "Mature", "Mature {species}"),
    ("flowering", "Flowering", "Flowering {species}"),
    ("rare", "Full Bloom", "Full Bloom {species}"),
])
@pytest.mark.parametrize("species,species_name", [
    ("bonsai", "Bonsai"), ("rose", "Rose"), ("japanese_maple", "Japanese Maple"),
])
@pytest.mark.parametrize("name", ["Bonsai Plant", "Juniper of the Moonlit Library Garden"])
def test_plant_titles_use_stage_and_species_and_ignore_custom_names(
    stage: str, label: str, title: str, species: str, species_name: str, name: str,
) -> None:
    from ankigarden.ui.formatters import format_plant_name
    from ankigarden.presentation import plant_stage_event, plant_stage_title

    plant = dict(plant_id="plant-1", species=species, name=name,
                 display_name=name, name_customized=True, stage=stage)
    expected_title = title.format(species=species_name)
    for source in (plant, SimpleNamespace(**plant)):
        identity = PlantIdentity.from_plant(source)
        assert identity.plant_id == "plant-1"
        assert identity.species_name == species_name
        assert identity.display_name == expected_title
        assert format_plant_name(source) == expected_title
        assert plant_stage_title(source, stage) == expected_title
        assert plant_stage_event(source, stage) == f"{species_name} reached {label.lower()}"
    assert plant["name"] == name


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


def test_garden_appearance_derives_effects_from_equipped_artwork() -> None:
    state = GardenState()
    day = state.daily_stats.day
    state.loadout.scenery_id = "default"
    state.loadout.displayed_garden_feature_id = "seedling_sign"
    state.loadout.active_bonus_garden_feature_id = "wind_chime"
    state.loadout.visibility = {"garden_feature": False, "scenery": False}
    state.daily_loadout.garden_bonus_anki_day_id = day
    state.daily_loadout.garden_bonus_locked_at_ms = 100
    state.daily_loadout.garden_feature_id = "watering_station"

    before = state.to_dict()
    projection = project_garden_appearance(state)
    assert state.to_dict() == before

    assert projection.to_dict() == {
        "scenery_id": "default",
        "displayed_decoration_id": "wind_chime",
        "active_bonus_decoration_id": "wind_chime",
        "active_bonus_effect": (
            "+1 Growth every 5 cards."
        ),
        "visual_effects_enabled": True,
    }
    assert projection.summary_rows == (
        ("Scenery", "Verdant Twilight"),
        ("Displayed decoration", "Wind Chime"),
        (
            "Active garden bonus",
            "Wind Chime · +1 Growth every 5 cards.",
        ),
        ("Visual effects", "Enabled"),
    )


def test_find_vocabulary_changes_visible_copy_without_changing_internal_ids() -> None:
    standard = visible_reward_term(STANDARD_FIND_INTERNAL_ID)
    discovery = visible_reward_term(GARDEN_DISCOVERY_INTERNAL_ID)

    assert standard.internal_id == STANDARD_FIND_INTERNAL_ID
    assert standard.label(2, include_quantity=True) == "2 Garden Finds"
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
        assert visible_copy == projected_copy
        assert visible_copy.endswith("Garden discovery.")
        assert "standard" not in visible_copy.casefold()
        assert "Garden Find" not in visible_copy
