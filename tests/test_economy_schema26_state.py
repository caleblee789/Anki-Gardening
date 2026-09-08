from __future__ import annotations

from ankigarden.models.state import (
    CardEffectBatch,
    CardEffectQueue,
    CultivationMasteryState,
    DailyEconomySnapshot,
    GardenLoadoutState,
    GardenProjectState,
    GardenState,
    LifetimeEconomyAggregates,
    Plant,
    STATE_VERSION,
)


def test_round_trip_preserves_unified_equipment_and_economy_models() -> None:
    batch = CardEffectBatch(
        "fertilizer_quality",
        200,
        150,
        73,
        "2026-08-30T12:00:00+00:00",
        "purchase:fertilizer:one",
    )
    state = GardenState(
        unlocked_slots=5,
        earned_bed_unlocks=[3, 4, 5],
        loadout=GardenLoadoutState(
            display_decoration_id="garden_bench",
            active_garden_bonus_id="wind_chime",
            display_scenery_id="full_moon",
            active_scenery_effect_id="default",
        ),
        plants=[Plant(
            "plant-1",
            "bonsai",
            "Moss",
            0,
            card_effect_queue=CardEffectQueue([batch], 211),
        )],
        daily_economy_snapshot=DailyEconomySnapshot(
            "2026-08-30",
            "wind_chime",
            "default",
            "local_first_answer",
            "snapshot:2026-08-30:first",
        ),
        firefly_lantern_progress=4,
        hourglass_completion_progress=2,
        full_moon_completion_progress=1,
        prism_pending_growth_units=155,
        garden_project=GardenProjectState(
            selected_project_id="birdbath_terrace",
            contributed_growth_units=3_000_000,
            completed_project_ids=["mossy_stone_path"],
            displayed_project_id="mossy_stone_path",
            auto_contribute=True,
        ),
        cultivation_mastery=CultivationMasteryState({"bonsai": "gold"}),
        lifetime_economy_aggregates=LifetimeEconomyAggregates(
            coins_earned_by_source={"answers": 14},
            coins_spent_by_sink={"nursery": 7},
            growth_earned_by_source={"base": 1_000},
            growth_spent_on_landmarks=250,
            growth_spent_on_mastery=500,
            finds_by_outcome={"hit": 2, "miss": 4},
            environment_discoveries={"wind_chime": 1},
            consumables_earned={"fertilizer_basic": 2},
            consumables_used={"fertilizer_basic": 1},
            plants_completed=3,
            today_cards_completions=6,
        ),
        environment_completion_pity_misses={
            "rare": 2,
            "very_rare": 3,
            "ultra": 4,
        },
    )
    state.inventory["cosmetics"] = ["garden_bench"]
    state.inventory["scenery"].append("full_moon")
    state.inventory["garden_features"].append("wind_chime")

    payload = state.to_dict()
    assert payload["version"] == STATE_VERSION
    assert payload["loadout"] == {
        "display_decoration_id": "garden_bench",
        "display_scenery_id": "full_moon",
        "visibility": {"garden_feature": True, "scenery": True},
    }

    restored = GardenState.from_dict(payload)
    assert restored.loadout.display_decoration_id == "seedling_sign"
    assert restored.loadout.active_garden_bonus_id == "seedling_sign"
    assert restored.loadout.display_scenery_id == "full_moon"
    assert restored.loadout.active_scenery_effect_id == "full_moon"
    assert restored.inventory["cosmetics"] == ["garden_bench"]
    assert restored.plants[0].card_effect_queue.fertilizer_batches == [batch]
    assert restored.plants[0].card_effect_queue.booster_remaining_cards == 211
    assert restored.daily_economy_snapshot == state.daily_economy_snapshot
    assert restored.garden_project.to_dict() == payload["garden_project"]
    assert not restored.garden_project.auto_contribute
    assert restored.cultivation_mastery == state.cultivation_mastery
    assert restored.lifetime_economy_aggregates == state.lifetime_economy_aggregates
    assert restored.environment_completion_pity_misses == {
        "rare": 2,
        "very_rare": 3,
        "ultra": 4,
    }


def test_schema26_round_trip_preserves_booster_activation_boundary() -> None:
    booster = CardEffectBatch(
        "booster_potion",
        500,
        100,
        73,
        "2026-08-30T12:00:00+00:00",
        "booster:activation-boundary",
    )
    state = GardenState(plants=[Plant(
        "plant-1",
        "bonsai",
        "Moss",
        0,
        booster_card_batches=[booster],
    )])

    restored = GardenState.from_dict(state.to_dict())

    assert restored.plants[0].booster_card_batches == [booster]
    assert restored.plants[0].booster_card_queue == []
    assert restored.plants[0].card_effect_queue.booster_remaining_cards == 73


def test_schema26_repairs_effect_counter_and_project_boundaries() -> None:
    payload = GardenState().to_dict()
    payload["firefly_lantern_progress"] = 99
    payload["hourglass_completion_progress"] = 99
    payload["full_moon_completion_progress"] = 99
    payload["prism_pending_growth_units"] = 99_999
    payload["environment_completion_pity_misses"] = {
        "rare": -1,
        "very_rare": 2,
        "ultra": "bad",
    }
    payload["garden_project"] = {
        "selected_project_id": "glasshouse_conservatory",
        "contributed_growth_units": 999_999_999,
        "ready_to_complete": True,
        "completed_project_ids": ["mossy_stone_path", "lily_pond"],
        "displayed_project_id": "missing",
        "auto_contribute": True,
    }

    restored = GardenState.from_dict(payload)
    assert restored.firefly_lantern_progress == 4
    assert restored.hourglass_completion_progress == 14
    assert restored.full_moon_completion_progress == 3
    assert restored.prism_pending_growth_units == 30_000
    assert restored.environment_completion_pity_misses == {
        "rare": 0,
        "very_rare": 2,
        "ultra": 0,
    }
    assert restored.garden_project.completed_project_ids == ["mossy_stone_path"]
    assert restored.garden_project.selected_project_id == "birdbath_terrace"
    assert restored.garden_project.contributed_growth_units == 7_500_000
    assert restored.garden_project.ready_to_complete
    assert restored.garden_project.displayed_project_id == ""


def test_schema27_round_trips_unambiguous_growth_and_endgame_authorities() -> None:
    state = GardenState(
        stored_growth_units=1_234,
        stored_growth_opening_balance_units=1_234,
        stored_growth_opening_balance_source=(
            "schema_27_migration_preserved_balance"
        ),
        stored_growth_opening_balance_identity=(
            "migration:schema27:stored-growth-opening"
        ),
        active_growth_target_type="mastery",
        active_growth_target_id="bonsai",
        active_growth_target_activation_identity="activate:one",
        garden_project=GardenProjectState(
            landmark_growth_units_funded=10_000_000,
            landmark_highest_claimed_tier=1,
            displayed_landmark_tier_id="mossy_stone_path",
        ),
        cultivation_mastery=CultivationMasteryState(
            growth_units_funded_by_species={"bonsai": 7_500_000},
            highest_claimed_rank_by_species={"bonsai": "bronze"},
        ),
        garden_legacy_level=2,
        garden_legacy_progress_units=123,
    )

    payload = state.to_dict()

    assert "stored_growth_units" not in payload
    assert payload["stored_growth_balance_units"] == 1_234
    assert payload["stored_growth_opening_balance_units"] == 1_234
    restored = GardenState.from_dict(payload)
    assert restored.stored_growth_units == restored.stored_growth_balance_units == 1_234
    assert restored.stored_growth_opening_balance_units == 1_234
    assert restored.stored_growth_opening_balance_source == (
        "schema_27_migration_preserved_balance"
    )
    assert restored.active_growth_target_id == "bonsai"
    assert restored.garden_project.landmark_growth_units_funded == 10_000_000
    assert restored.garden_project.landmark_highest_claimed_tier == 1
    assert restored.cultivation_mastery.growth_units_funded_by_species == {
        "bonsai": 7_500_000
    }
    assert restored.cultivation_mastery.highest_rank_by_species == {
        "bonsai": "bronze"
    }
    assert (restored.garden_legacy_level, restored.garden_legacy_progress_units) == (
        2, 123
    )
