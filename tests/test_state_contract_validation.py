import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.models.state import GardenState


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

    assert state.plants == []


def test_null_values_for_nullable_fields_are_supported() -> None:
    payload = _base_payload()
    payload["focus_plant_id"] = None
    payload["exam_mode"] = {
        "enabled": True,
        "exam_date": None,
        "target_deck_ids": [1, 2],
        "focus_species": "bonsai",
    }

    state = GardenState.from_dict(payload)

    assert state.focus_plant_id is None
    assert state.exam_mode.exam_date is None


def test_unexpected_status_enum_falls_back_to_default() -> None:
    payload = _base_payload()
    payload["selected_weather"] = "acid_rain"
    payload["garden_mode"] = "per-deck"

    state = GardenState.from_dict(payload)

    assert state.selected_weather == "sunny"
    assert state.garden_mode == "unified"


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


def test_field_level_contract_mismatches_are_logged(caplog) -> None:
    payload = _base_payload()
    payload["exam_mode"] = {
        "enabled": True,
        "exam_date": "04-24-2026",
        "target_deck_ids": ["1"],
        "focus_species": "bonsai",
    }

    GardenState.from_dict(payload)

    assert "exam_mode.exam_date" in caplog.text
    assert "exam_mode.target_deck_ids" in caplog.text
