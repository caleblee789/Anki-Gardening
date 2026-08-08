import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.models.state import GardenState, PlantMemory


def test_numeric_state_is_clamped_to_safe_ranges() -> None:
    state = GardenState.from_dict(
        {
            "streak_days": -5,
            "daily_stats": {
                "day": "2026-07-10", "reviewed": 2, "correct": 9, "wrong": 8,
                "new_count": -1, "learning_count": 0, "review_count": 2,
                "difficult_count": 0, "recovered_lapses": 0, "growth_earned": -20,
                "completed_due_cards": False, "focus_sessions_completed": 0,
            },
            "plants": [{
                "plant_id": "p", "species": "rose", "name": "Rose", "slot_index": -1,
                "growth_points": -50, "vitality": 4.2,
            }],
        }
    )

    assert state.streak_days == 0
    assert state.daily_stats.correct == 2
    assert state.daily_stats.wrong == 0
    assert state.daily_stats.growth_earned == 0
    assert state.plants[0].growth_points == 0
    assert state.plants[0].vitality == 1.0


def _base_payload() -> dict:
    return GardenState().to_dict()


def test_missing_required_keys_in_nested_plant_are_filtered() -> None:
    payload = _base_payload()
    payload["plants"] = [{"species": "bonsai", "name": "Bonsai", "slot_index": 0}]

    state = GardenState.from_dict(payload)

    assert len(state.plants) == 1
    assert state.plants[0].plant_id == "plant_1"


def test_null_values_for_nullable_fields_are_supported() -> None:
    payload = _base_payload()
    payload["focus_plant_id"] = None
    payload["exam_mode"] = {"enabled": True, "exam_date": None}

    state = GardenState.from_dict(payload)

    assert state.focus_plant_id is None
    assert "exam_mode" not in state.to_dict()


def test_unexpected_status_enum_falls_back_to_default() -> None:
    payload = _base_payload()
    payload["selected_weather"] = "acid_rain"
    payload["garden_mode"] = "per-deck"

    state = GardenState.from_dict(payload)

    assert state.selected_weather == "sunny"
    assert "garden_mode" not in state.to_dict()


def test_type_mismatches_and_malformed_dates_fall_back_to_defaults() -> None:
    payload = _base_payload()
    payload["streak_days"] = "12"
    payload["daily_stats"] = {
        "day": "2026/04/24",
        "reviewed": "10",
        "correct": 8,
        "wrong": 2,
        "new_count": 1,
        "learning_count": 1,
        "review_count": 8,
        "difficult_count": 0,
        "recovered_lapses": 0,
        "growth_earned": 4,
        "completed_due_cards": False,
        "focus_sessions_completed": 0,
    }

    state = GardenState.from_dict(payload)

    assert state.streak_days == 0
    assert state.daily_stats.reviewed == 0
    assert state.daily_stats.day == GardenState().daily_stats.day


def test_hidden_v6_fields_are_dropped_without_affecting_core(caplog) -> None:
    payload = _base_payload()
    payload["exam_mode"] = {
        "enabled": True,
        "exam_date": "04-24-2026",
        "target_deck_ids": ["1"],
        "focus_species": "bonsai",
    }

    GardenState.from_dict(payload)

    state = GardenState.from_dict(payload)
    assert "exam_mode" not in state.to_dict()
    assert state.version == 10


def test_old_payload_deserializes_only_when_explicitly_inspected() -> None:
    payload = _base_payload()
    payload["version"] = 6
    payload["pending_milestone_reward"] = {
        "review_count": 250,
        "offered_species": ["fern", "cactus", "ivy"],
    }

    state = GardenState.from_dict(payload)

    assert state.version == 10
    assert state.pending_milestone_reward is not None
    assert state.pending_milestone_reward.offered_species == ["fern", "cactus", "ivy"]


def test_duplicate_ids_slots_and_out_of_range_slot_count_are_repaired() -> None:
    payload = _base_payload()
    payload["unlocked_slots"] = 99
    payload["plants"] = [
        {"plant_id": "same", "species": "rose", "name": "Rose", "slot_index": 9},
        {"plant_id": "same", "species": "fern", "name": "Fern", "slot_index": 9},
    ]

    state = GardenState.from_dict(payload)

    assert state.unlocked_slots == 2
    assert len({plant.plant_id for plant in state.plants}) == 2
    assert {plant.slot_index for plant in state.plants} == {0, 1}


def test_v8_serializer_omits_all_dormant_system_state() -> None:
    payload = GardenState().to_dict()
    for key in (
        "currency", "focus_session", "exam_mode", "deck_plant_map", "deck_difficulty_map",
        "weekly_event_id", "mastery_tree", "rare_event_log", "passive_reward_days",
    ):
        assert key not in payload


def test_unsupported_species_and_focus_quest_are_removed() -> None:
    payload = _base_payload()
    payload["plants"] = [{"plant_id": "x", "species": "money_tree", "name": "Money", "slot_index": 0}]
    payload["daily_quests"] = [{
        "quest_id": "focus", "description": "Use focus mode", "target": 1,
        "metric": "focus", "progress": 0, "reward_growth": 50, "completed": False,
    }]

    state = GardenState.from_dict(payload)

    assert state.plants == []
    assert state.daily_quests == []


def test_malformed_pending_milestone_is_discarded() -> None:
    payload = _base_payload()
    payload["pending_milestone_reward"] = {"review_count": "250", "offered_species": "fern"}

    state = GardenState.from_dict(payload)

    assert state.pending_milestone_reward is None


def test_plant_memories_round_trip_and_invalid_entries_are_filtered() -> None:
    payload = _base_payload()
    payload["plants"] = [{
        "plant_id": "p1", "species": "rose", "name": "Briar", "slot_index": 0,
        "planted_on": "2026-07-12", "memories": [
            PlantMemory("planted", "planted", "2026-07-12").__dict__,
            {"memory_id": "bad", "kind": "currency", "occurred_on": "2026-07-12"},
            {"memory_id": "stage:sprout", "kind": "stage", "occurred_on": "2026-07-13", "new_stage": "sprout"},
        ],
    }]

    state = GardenState.from_dict(payload)

    assert state.plants[0].planted_on == "2026-07-12"
    assert [memory.memory_id for memory in state.plants[0].memories] == ["planted", "stage:sprout"]
    assert state.to_dict()["plants"][0]["memories"][1]["new_stage"] == "sprout"


def test_plant_names_are_normalized_and_bounded_on_load() -> None:
    payload = _base_payload()
    payload["plants"] = [{
        "plant_id": "p1", "species": "rose", "name": f"  {'Petal ' * 20}  ", "slot_index": 0,
    }]

    plant = GardenState.from_dict(payload).plants[0]

    assert plant.name == plant.name.strip()
    assert "  " not in plant.name
    assert len(plant.name) == 40


def test_imported_history_days_are_normalized_deduplicated_and_round_trip() -> None:
    payload = _base_payload()
    payload["imported_history_days"] = [
        "2026-07-01", "not-a-date", "2026-07-01", "2026-06-30",
    ]

    state = GardenState.from_dict(payload)

    assert state.imported_history_days == ["2026-06-30", "2026-07-01"]
    assert state.to_dict()["imported_history_days"] == ["2026-06-30", "2026-07-01"]
