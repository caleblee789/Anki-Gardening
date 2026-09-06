from __future__ import annotations

import json
import os
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from ankigarden.models.state import (
    ActivePlantPeriod,
    Fertilizer,
    GardenState,
    HISTORICAL_PLANT_SPECIES_ORDER,
    MAX_COMPLETED_PURCHASE_REQUESTS,
    OnboardingStep,
    Plant,
    PlantMemory,
    STATE_VERSION,
)
from ankigarden.purchases import (
    CompletedPurchaseRequest,
    PurchaseDisposition,
    PurchaseOutcome,
    PurchaseStatus,
)
from ankigarden.storage import (
    DueObligationStatus,
    GardenStorage,
    RevlogReadError,
    SchedulerBoundaryError,
    StatePreservationError,
    migrate_modern_state,
    migrate_previous_state,
    unprocessed_revlog_entries,
)


def storage_at(path):
    storage = object.__new__(GardenStorage)
    storage.data_path = path
    return storage


def _completed_request(index: int) -> CompletedPurchaseRequest:
    return CompletedPurchaseRequest(
        request_id=f"00000000-0000-4000-8000-{index:012d}",
        request_fingerprint=f"{index:064x}"[-64:],
        outcome=PurchaseOutcome(
            status=PurchaseStatus.SUCCESS,
            item_id="growth_charge_small",
            item_name="Small Growth Charge",
            category="Growth Charge",
            quantity=1,
            amount_spent=30,
            new_balance=max(0, 1_000 - index),
            disposition=PurchaseDisposition.INVENTORY,
            message="Small Growth Charge added to Supplements & Boosters.",
            next_actions=("Use growth charge",),
        ),
        occurred_at="2026-08-16T12:00:00+00:00",
    )


def test_schema18_purchase_request_history_round_trips_and_is_bounded() -> None:
    records = [
        _completed_request(index)
        for index in range(MAX_COMPLETED_PURCHASE_REQUESTS + 5)
    ]
    state = GardenState(completed_purchase_requests=records)

    payload = state.to_dict()
    restored = GardenState.from_dict(payload)

    assert len(payload["completed_purchase_requests"]) == MAX_COMPLETED_PURCHASE_REQUESTS
    assert len(restored.completed_purchase_requests) == MAX_COMPLETED_PURCHASE_REQUESTS
    assert restored.completed_purchase_requests[0].request_id == records[5].request_id
    assert restored.completed_purchase_requests[-1] == records[-1]


def test_daily_obligation_projection_defaults_and_repairs_in_place() -> None:
    payload = GardenState().to_dict()
    schema_version = payload["version"]
    completion = payload["daily_completion"]
    completion.pop("obligation_projection_initialized", None)
    completion.pop("remaining_new_cards", None)
    completion.pop("unresolved_obligation_disappearances", None)

    restored = GardenState.from_dict(payload)

    assert restored.version == schema_version
    assert restored.daily_completion.obligation_projection_initialized is False
    assert restored.daily_completion.remaining_new_cards == 0
    assert restored.daily_completion.unresolved_obligation_disappearances == 0

    completion["obligation_projection_initialized"] = "yes"
    completion["remaining_new_cards"] = -4
    completion["unresolved_obligation_disappearances"] = -2
    repaired = GardenState.from_dict(payload)

    assert repaired.version == schema_version
    assert repaired.daily_completion.obligation_projection_initialized is False
    assert repaired.daily_completion.remaining_new_cards == 0
    assert repaired.daily_completion.unresolved_obligation_disappearances == 0


def test_schema18_purchase_history_discards_malformed_and_duplicate_records() -> None:
    valid = _completed_request(1).to_dict()
    duplicate = _completed_request(1).to_dict()
    invalid_fingerprint = {
        **_completed_request(2).to_dict(),
        "request_fingerprint": "not-a-fingerprint",
    }
    invalid_request_id = {
        **_completed_request(3).to_dict(),
        "request_id": "not-a-uuid",
    }
    noncanonical_request_id = {
        **_completed_request(4).to_dict(),
        "request_id": "{aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}",
    }
    noncanonical_fingerprint = {
        **_completed_request(5).to_dict(),
        "request_fingerprint": "A" * 64,
    }
    invalid_outcome = _completed_request(6).to_dict()
    invalid_outcome["outcome"]["amount_spent"] = -1
    invalid_timestamp = {
        **_completed_request(7).to_dict(),
        "occurred_at": "2026-08-16T12:00:00",
    }
    payload = GardenState().to_dict()
    payload["completed_purchase_requests"] = [
        valid,
        duplicate,
        invalid_fingerprint,
        invalid_request_id,
        noncanonical_request_id,
        noncanonical_fingerprint,
        invalid_outcome,
        invalid_timestamp,
    ]

    restored = GardenState.from_dict(payload)

    assert restored.completed_purchase_requests == [_completed_request(1)]


def test_schema17_migration_adds_empty_purchase_history_and_preserves_state(tmp_path) -> None:
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        currency_balance=777,
        plants=[Plant("starter", "bonsai", "Moss", 0)],
        active_plant_id="starter",
    ).to_dict()
    payload["version"] = 17
    payload.pop("completed_purchase_requests", None)
    payload["onboarding"] = {
        "version": 1,
        "step": "nurture",
        "pending_species": None,
        "starter_plant_id": "starter",
    }
    payload["processed_revlog_floor"] = 100
    payload["processed_revlog_ids"] = [101, 105]
    payload["revlog_ledger_migration_pending"] = False
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    migrated = storage_at(state_path)._load()

    assert migrated.version == STATE_VERSION
    assert migrated.currency_balance == 777
    assert migrated.completed_purchase_requests == []
    assert migrated.onboarding.step is OnboardingStep.NURTURE
    assert migrated.onboarding.starter_plant_id == "starter"
    assert migrated.processed_revlog_floor == 100
    assert migrated.processed_revlog_ids == [101, 105]
    assert migrated.revlog_ledger_migration_pending is False
    assert state_path.with_suffix(".schema-17.legacy.json").exists()


def test_schema18_migration_preserves_purchase_replay_history_and_collapses_loadout() -> None:
    completed = _completed_request(7)
    payload = GardenState(completed_purchase_requests=[completed]).to_dict()
    payload["version"] = 18
    payload["selected_weather"] = "breeze"
    payload["selected_background"] = "spring"
    payload["environment_visibility"] = {"weather": False, "scenery": True}
    payload["equipped"] = {"weather": "breeze", "background": "spring", "decoration": "lantern"}
    payload["inventory"]["weather"].append("breeze")
    payload["inventory"]["scenery"].append("spring")
    payload["inventory"]["backgrounds"] = ["default", "spring"]

    migrated = migrate_modern_state(payload)

    assert migrated.completed_purchase_requests == [completed]
    assert migrated.selected_garden_feature == "wind_chime"
    assert migrated.selected_background == "spring"
    assert not hasattr(migrated.loadout, "decoration_id")
    assert "decoration_id" not in migrated.to_dict()["loadout"]
    assert migrated.environment_visibility == {
        "garden_feature": False, "weather": False, "scenery": True
    }
    assert "backgrounds" not in migrated.inventory
    assert not {"selected_weather", "selected_background", "equipped", "environment_visibility"} & migrated.to_dict().keys()


def test_schema19_growth_migration_preserves_unattributed_day_and_backup(tmp_path) -> None:
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        plants=[Plant("p", "bonsai", "Moss", 0, growth_points=777)],
        active_plant_id="p",
    ).to_dict()
    payload["version"] = 19
    payload["daily_stats"].update({
        "day": "2026-08-17",
        "base_growth": 30,
        "streak_bonus_growth": 2,
        "fertilizer_growth": 5,
        "growth_earned": 37,
        "plant_growth": {"p": 37},
    })
    for key in (
        "plant_nurtured_growth",
        "plant_passive_growth_fifths",
        "plant_passive_growth_credited",
        "plant_charge_growth",
        "plant_direct_reward_growth",
        "legacy_unattributed_growth",
        "legacy_plant_growth",
        "growth_accounting_stale",
    ):
        payload["daily_stats"].pop(key, None)
    payload["plants"][0].pop("passive_growth_remainder_fifths", None)
    payload.pop("completed_growth_charge_requests", None)
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    migrated = storage_at(state_path)._load()

    assert migrated.version == STATE_VERSION
    assert migrated.plants[0].growth_points == 777
    assert migrated.plants[0].passive_growth_remainder_fifths == 0
    assert migrated.daily_stats.legacy_unattributed_growth == 37
    assert migrated.daily_stats.legacy_plant_growth == {"p": 37}
    assert migrated.daily_stats.growth_accounting_stale
    assert migrated.daily_stats.study_growth_generated == 0
    assert migrated.daily_stats.growth_earned == 37
    assert migrated.completed_growth_charge_requests == []
    assert state_path.with_suffix(".schema-19.legacy.json").exists()


def legacy_state_payload() -> dict:
    return {
        "version": 10,
        "streak_days": 9,
        "total_reviews": 321,
        "total_correct": 280,
        "total_wrong": 41,
        "unlocked_slots": 4,
        "selected_background": "default",
        "selected_weather": "cloudy",
        "plants": [{
            "plant_id": "legacy_lavender",
            "species": "lavender",
            "name": " Violet  Friend ",
            "slot_index": 3,
            "growth_points": 350,
            "vitality": 0.42,
            "rare_variant": True,
            "personality": "recovery",
            "planted_on": "2026-07-01",
            "memories": [
                {"memory_id": "planted", "kind": "planted", "occurred_on": "2026-07-01"},
                {"memory_id": "focus:first", "kind": "first_focus", "occurred_on": "2026-07-02"},
            ],
        }],
        "achievements": {},
        "daily_quests": [{"quest_id": "obsolete", "completed": True}],
        "quest_history": ["obsolete"],
        "daily_stats": {
            "day": "2026-08-08",
            "reviewed": 70,
            "correct": 65,
            "wrong": 5,
            "new_count": 10,
            "learning_count": 20,
            "review_count": 40,
            "difficult_count": 5,
            "recovered_lapses": 2,
            "growth_earned": 999,
            "completed_due_cards": True,
        },
        "inventory": {
            "plants": ["bonsai", "rose", "wisteria", "lavender"],
            "pots": ["ceramic_minimal"],
            "backgrounds": ["default"],
            "decorations": ["lantern"],
            "weather": ["sunny", "cloudy"],
        },
        "equipped": {
            "pot": "ceramic_minimal",
            "background": "default",
            "decoration": "none",
            "weather": "cloudy",
        },
        "last_active_day": "2026-08-08",
        "focus_plant_id": "legacy_lavender",
        "retrospective_last_revlog_id": 1_786_100_000_123,
        "imported_history_days": ["2026-07-01"],
    }


def test_previous_release_schema_is_backed_up_and_progress_is_migrated(tmp_path):
    state_path = tmp_path / "garden_state.json"
    payload = legacy_state_payload()
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = storage_at(state_path)._load()

    assert state.version == STATE_VERSION
    assert state.total_reviews == 321
    assert state.streak_days == 9
    assert state.unlocked_slots == 4
    assert state.unlocked_species == ["bonsai", "rose", "wisteria", "lavender"]
    assert state.active_plant_id == "legacy_lavender"
    assert state.last_processed_revlog_id == 1_786_100_000_123
    assert state.plants[0].name == "Violet Friend"
    assert state.plants[0].growth_points == 4_000
    assert [memory.kind for memory in state.plants[0].memories] == ["planted", "first_nurture"]
    assert state.daily_stats.reviewed == 70
    assert state.daily_stats.growth_earned == 0
    assert state.daily_stats.completed_due_cards
    assert state.currency_balance == 0
    assert state.starter_selection_complete
    serialized = state.to_dict()
    for removed in ("daily_quests", "quest_history", "vitality", "rare_variant", "imported_history_days"):
        assert removed not in serialized
    backup = state_path.with_suffix(".schema-10.legacy.json")
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["total_reviews"] == 321


@pytest.mark.parametrize(
    ("legacy_growth", "expected_growth"),
    [
        (0, 0),
        (40, 200),
        (80, 400),
        (150, 1_200),
        (220, 2_000),
        (350, 4_000),
        (480, 6_000),
        (690, 10_500),
        (900, 15_000),
        (1_150, 25_000),
        (1_400, 35_000),
        (99_999, 35_000),
    ],
)
def test_previous_release_growth_keeps_stage_and_within_stage_percentage(legacy_growth, expected_growth):
    payload = legacy_state_payload()
    payload["plants"][0]["growth_points"] = legacy_growth
    assert migrate_previous_state(payload).plants[0].growth_points == expected_growth


def test_previous_release_does_not_restore_removed_goal_or_vitality_systems():
    payload = legacy_state_payload()
    payload["daily_stats"]["reviewed"] = 70

    state = migrate_previous_state(payload)

    serialized = state.to_dict()
    assert "active_review_goal" not in serialized
    assert "activity_history" not in serialized
    assert "vitality" not in serialized
    assert state.currency_transactions == []


def test_unsupported_schema_is_backed_up_and_reset(tmp_path):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(total_reviews=321).to_dict()
    payload["version"] = 9
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = storage_at(state_path)._load()

    assert state.version == STATE_VERSION
    assert state.total_reviews == 0
    assert state_path.with_suffix(".schema-9.legacy.json").exists()


def test_migration_backup_failure_stops_before_returning_or_overwriting_state(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(total_reviews=321).to_dict()
    payload["version"] = 12
    original = json.dumps(payload)
    state_path.write_text(original, encoding="utf-8")
    storage = storage_at(state_path)

    def fail_copy(*_args, **_kwargs):
        raise OSError("backup volume unavailable")

    monkeypatch.setattr("ankigarden.storage.shutil.copy2", fail_copy)

    with pytest.raises(StatePreservationError, match="stopped before any overwrite"):
        storage._load()

    assert state_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [state_path]


def test_current_schema_loads_without_backup(tmp_path):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(total_reviews=88).to_dict()
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = storage_at(state_path)._load()

    assert state.total_reviews == 88
    assert list(tmp_path.glob("*.legacy.json")) == []


@pytest.mark.parametrize("previous_version", [11, 12, 13, 14, 15])
def test_modern_pre_starter_schema_preserves_the_garden_and_marks_it_complete(
    tmp_path, previous_version
):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        total_reviews=88,
        currency_balance=240,
        unlocked_slots=4,
        unlocked_species=["lavender"],
        plants=[Plant("legacy_lavender", "lavender", "Violet", 3, growth_points=7_777)],
        active_plant_id="legacy_lavender",
    ).to_dict()
    payload["version"] = previous_version
    payload.pop("starter_selection_complete")
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    state = storage_at(state_path)._load()

    assert state.total_reviews == 88
    assert state.currency_balance == 240
    assert state.unlocked_slots == 4
    assert state.unlocked_species == ["lavender"]
    assert state.plants[0].growth_points == 7_777
    assert state.active_plant_id == "legacy_lavender"
    assert state.starter_selection_complete
    assert state_path.with_suffix(f".schema-{previous_version}.legacy.json").exists()


@pytest.mark.parametrize("previous_version", [11, 12, 13, 14, 15])
def test_modern_migration_preserves_every_historical_species_story_and_progress(
    previous_version,
):
    names = {
        species: f"Legacy {species.replace('_', ' ').title()}"
        for species in HISTORICAL_PLANT_SPECIES_ORDER
    }
    plants = [
        Plant(
            plant_id=f"historical-{index}",
            species=species,
            name=names[species],
            slot_index=index if index < 6 else None,
            growth_points=1_000 + index * 137,
            bonus_remainder=index,
            personality=f"legacy-{index}",
            planted_on=f"2026-07-{index + 1:02d}",
            memories=[PlantMemory(
                memory_id=f"stage:{species}",
                kind="stage",
                occurred_on=f"2026-08-{index + 1:02d}",
                value=index,
                previous_stage="sprout",
                new_stage="young",
            )],
            fertilizer=Fertilizer(
                tier="quality",
                growth_per_answer=2,
                expires_at=1_900_000_000.0 + index,
            ),
        )
        for index, species in enumerate(HISTORICAL_PLANT_SPECIES_ORDER)
    ]
    payload = GardenState(
        unlocked_slots=6,
        unlocked_species=list(HISTORICAL_PLANT_SPECIES_ORDER),
        plants=plants,
        active_plant_id=plants[0].plant_id,
    ).to_dict()
    payload["version"] = previous_version
    payload.pop("starter_selection_complete")

    restored = migrate_modern_state(payload, migrated_at=1_800_000_000.0)
    by_species = {plant.species: plant for plant in restored.plants}

    assert set(by_species) == set(HISTORICAL_PLANT_SPECIES_ORDER)
    assert restored.unlocked_species == list(HISTORICAL_PLANT_SPECIES_ORDER)
    assert restored.active_plant_id == plants[0].plant_id
    assert restored.starter_selection_complete
    for index, species in enumerate(HISTORICAL_PLANT_SPECIES_ORDER):
        plant = by_species[species]
        assert plant.name == names[species]
        assert plant.growth_points == 1_000 + index * 137
        assert plant.bonus_remainder == index
        assert plant.personality == f"legacy-{index}"
        assert plant.planted_on == f"2026-07-{index + 1:02d}"
        assert [memory.memory_id for memory in plant.memories] == [f"stage:{species}"]
        assert plant.memories[0].new_stage == "young"
        assert plant.fertilizer is None
        assert plant.fertilizer_history == []
        assert len(plant.fertilizer_card_batches) == 1
        assert plant.fertilizer_card_queue == []
        batches = plant.card_effect_queue.fertilizer_batches
        assert len(batches) == 1
        assert plant.fertilizer_card_batches[0] == batches[0]
        assert (
            batches[0].effect_id,
            batches[0].growth_per_card_units,
            batches[0].total_cards,
            batches[0].remaining_cards,
        ) == ("fertilizer_quality", 200, 200, 200)


def test_modern_migration_resumes_an_empty_preexisting_garden_at_introduction():
    payload = GardenState().to_dict()
    payload["version"] = 12
    payload.pop("starter_selection_complete")

    state = migrate_modern_state(payload)

    assert state.plants == []
    assert state.unlocked_species == []
    assert state.starter_selection_complete is False
    assert state.onboarding.step is OnboardingStep.INTRODUCTION


def test_schema13_fertilizer_migration_converts_remaining_time_to_cards():
    payload = GardenState(
        plants=[Plant(
            "p1",
            "bonsai",
            "Moss",
            0,
            fertilizer=Fertilizer("quality", 2, 2_000.0),
        )],
        active_plant_id="p1",
    ).to_dict()
    payload["version"] = 13
    payload.pop("starter_selection_complete")

    state = migrate_modern_state(payload, migrated_at=1_000.0)
    plant = state.plants[0]

    assert plant.fertilizer is None
    assert plant.fertilizer_history == []
    assert len(plant.fertilizer_card_batches) == 1
    assert plant.fertilizer_card_queue == []
    batch = plant.card_effect_queue.fertilizer_batches[0]
    assert plant.fertilizer_card_batches[0] == batch
    # 1,000 seconds of a 7,200-second dose: ceil(200 * 1000 / 7200) = 28.
    assert (
        batch.effect_id,
        batch.growth_per_card_units,
        batch.total_cards,
        batch.remaining_cards,
    ) == ("fertilizer_quality", 200, 200, 28)
    assert state.revlog_ledger_migration_pending


def test_schema25_json_preserves_experimental_fertilizer_batches_as_cards(
    tmp_path,
    monkeypatch,
):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        plants=[Plant("p1", "bonsai", "Moss", 0)],
        active_plant_id="p1",
    ).to_dict()
    payload["version"] = 25
    payload["plants"][0]["fertilizer_card_batches"] = [{
        "effect_id": "fertilizer_quality",
        "growth_per_card_units": 200,
        "total_cards": 150,
        "remaining_cards": 75,
        "activated_at": "2026-08-28T12:00:00+00:00",
        "source_event_key": "purchase:quality:1",
    }]
    payload["plants"][0]["fertilizer_card_queue"] = [{
        "effect_id": "fertilizer_premium",
        "growth_per_card_units": 300,
        "total_cards": 250,
        "remaining_cards": 125,
        "activated_at": "2026-08-28T12:01:00+00:00",
        "source_event_key": "purchase:premium:1",
    }]
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("ankigarden.storage.time.time", lambda: 1_500.0)

    restored = storage_at(state_path)._load()

    plant = restored.plants[0]
    assert plant.fertilizer is None
    assert plant.fertilizer_history == []
    assert len(plant.fertilizer_card_batches) == 1
    assert len(plant.fertilizer_card_queue) == 1
    assert [
        (
            batch.effect_id,
            batch.growth_per_card_units,
            batch.total_cards,
            batch.remaining_cards,
        )
        for batch in plant.card_effect_queue.fertilizer_batches
    ] == [
        ("fertilizer_quality", 200, 150, 75),
        ("fertilizer_premium", 300, 250, 125),
    ]


@pytest.mark.parametrize(
    ("fixture", "legacy_preference", "expected_step"),
    [
        ("empty", 0, OnboardingStep.INTRODUCTION),
        ("planted-incomplete", 0, OnboardingStep.NURTURE),
        ("planted-legacy-complete", 3, OnboardingStep.DONE),
        ("active", 0, OnboardingStep.DONE),
        ("setup-complete", 0, OnboardingStep.DONE),
        ("shelved-collection", 0, OnboardingStep.DONE),
    ],
)
def test_schema16_onboarding_migration_matrix(
    fixture,
    legacy_preference,
    expected_step,
):
    state = GardenState()
    if fixture != "empty":
        plant = Plant(
            "legacy-starter",
            "bonsai",
            "Moss",
            None if fixture == "shelved-collection" else 0,
            memories=[PlantMemory("planted", "planted", "2026-08-08")],
        )
        state.plants = [plant]
        state.unlocked_species = [plant.species]
        state.starter_selection_complete = True
        if fixture == "active":
            state.active_plant_id = plant.plant_id
        if fixture == "setup-complete":
            state.garden_setup_version = 1
    payload = state.to_dict()
    payload["version"] = 16
    payload.pop("onboarding", None)
    if fixture in {"planted-incomplete", "planted-legacy-complete", "active", "shelved-collection"}:
        payload["garden_setup_version"] = 0

    migrated = migrate_modern_state(
        payload,
        onboarding_version=legacy_preference,
    )

    assert migrated.onboarding.step is expected_step
    assert migrated.version == STATE_VERSION


@pytest.mark.parametrize("saved_version", [11, 12, 13, 14, 15, STATE_VERSION])
def test_entitlement_only_species_materializes_as_zero_growth_shelved_plant(
    tmp_path,
    saved_version,
):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        unlocked_species=["sunflower"],
        starter_selection_complete=True,
        currency_balance=500,
    ).to_dict()
    payload["version"] = saved_version
    if saved_version in (11, 12, 13):
        payload.pop("starter_selection_complete")
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    restored = storage_at(state_path)._load()

    matches = [plant for plant in restored.plants if plant.species == "sunflower"]
    assert len(matches) == 1
    assert matches[0].slot_index is None
    assert matches[0].growth_points == 0
    assert [memory.kind for memory in matches[0].memories] == ["planted"]
    assert restored.starter_selection_complete
    assert restored.currency_balance == 500


def test_schema13_ledger_seed_survives_two_restarts_and_finds_late_lower_id(tmp_path):
    state_path = tmp_path / "garden_state.json"
    payload = GardenState(
        last_processed_revlog_id=200,
        daily_stats=GardenState().daily_stats,
    ).to_dict()
    payload["version"] = 13
    for key in (
        "processed_revlog_floor",
        "processed_revlog_ids",
        "revlog_ledger_migration_pending",
    ):
        payload.pop(key)
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    first = storage_at(state_path)
    first.state = first._load()
    first.mw = SimpleNamespace(col=SimpleNamespace(db=FakeDb(rows=[
        (150, 1, 3, 1, 0, 2500, 100, 1),
        (200, 2, 3, 1, 0, 2500, 100, 1),
    ])))
    first.current_scheduler_day_bounds_ms = lambda: (100, 300)
    first.ensure_revlog_ledger_ready()

    assert first.state.processed_revlog_floor == 99
    assert first.state.processed_revlog_ids == [150, 200]
    assert not first.state.revlog_ledger_migration_pending

    second_loader = storage_at(state_path)
    second = second_loader._load()
    second_loader.state = second
    second_loader.user_files_dir = tmp_path / "user_files"
    second_loader.cache_dir = second_loader.user_files_dir / "cache"
    second_loader.current_scheduler_day = lambda: second.daily_stats.day
    second_loader.current_day_start_ms = lambda: 100
    second_loader.current_time_ms = lambda: 250
    second_loader._ensure_defaults()
    late_row = (125, 3, 3, 1, 0, 2500, 100, 1)
    day_rows = [late_row,
        (150, 1, 3, 1, 0, 2500, 100, 1),
        (200, 2, 3, 1, 0, 2500, 100, 1),
    ]
    assert [row[0] for row in unprocessed_revlog_entries(second, day_rows)] == [125]
    second.processed_revlog_ids.append(125)
    second_loader.save()

    third_loader = storage_at(state_path)
    third = third_loader._load()
    third_loader.state = third
    third_loader.user_files_dir = tmp_path / "user_files"
    third_loader.cache_dir = third_loader.user_files_dir / "cache"
    third_loader.current_scheduler_day = lambda: third.daily_stats.day
    third_loader.current_day_start_ms = lambda: 100
    third_loader.current_time_ms = lambda: 275
    third_loader._ensure_defaults()
    assert third.processed_revlog_floor == 99
    assert third.processed_revlog_ids == [125, 150, 200]
    assert unprocessed_revlog_entries(third, day_rows) == []
    assert state_path.with_suffix(".schema-13.legacy.json").exists()


def test_legacy_ledger_seed_save_failure_restores_pending_cursor_and_ledger():
    storage = object.__new__(GardenStorage)
    storage.state = GardenState(
        last_processed_revlog_id=200,
        processed_revlog_floor=200,
        processed_revlog_ids=[],
        revlog_ledger_migration_pending=True,
    )
    storage.current_scheduler_day_bounds_ms = lambda: (100, 300)
    storage._load_revlog_entries_between = lambda *_args: [
        (150, 1, 3, 1, 0, 2500, 100, 1),
        (200, 2, 3, 1, 0, 2500, 100, 1),
    ]
    storage.save = lambda: (_ for _ in ()).throw(OSError("disk full"))

    with pytest.raises(OSError, match="disk full"):
        storage.ensure_revlog_ledger_ready()

    assert storage.state.last_processed_revlog_id == 200
    assert storage.state.processed_revlog_floor == 200
    assert storage.state.processed_revlog_ids == []
    assert storage.state.revlog_ledger_migration_pending


def test_truly_new_state_keeps_two_empty_slots_until_starter_selection(tmp_path):
    storage = object.__new__(GardenStorage)
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"
    storage.state = GardenState()
    storage.current_scheduler_day = lambda: "2026-08-08"
    storage.current_day_start_ms = lambda: 1_786_100_000_000
    storage.current_time_ms = lambda: 1_786_150_000_000
    storage.save = lambda: None

    storage._ensure_defaults()

    assert storage.state.unlocked_slots == 2
    assert storage.state.plants == []
    assert storage.state.unlocked_species == []
    assert not storage.state.starter_selection_complete
    assert storage.state.active_plant_id is None
    assert len(storage.state.active_plant_periods) == 1
    assert storage.state.active_plant_periods[0].plant_id is None
    assert storage.state.active_plant_periods[0].started_at_ms == 0


def test_established_state_keeps_saved_scheduler_day_when_cutoff_is_unavailable(tmp_path):
    storage = object.__new__(GardenStorage)
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"
    storage.state = GardenState(
        plants=[Plant("p1", "bonsai", "Moss", 0)],
        active_plant_id="p1",
        daily_stats=GardenState().daily_stats,
    )
    storage.state.daily_stats.day = "2026-03-07"
    storage.state.active_plant_periods = [
        ActivePlantPeriod("2026-03-07", "p1", 123)
    ]
    storage.current_scheduler_day = lambda: (_ for _ in ()).throw(
        SchedulerBoundaryError("cutoff unavailable")
    )
    storage.current_time_ms = lambda: 999
    saved_days = []
    storage.save = lambda: saved_days.append(storage.state.daily_stats.day)

    storage._ensure_defaults()

    assert storage.state.daily_stats.day == "2026-03-07"
    assert {period.day for period in storage.state.active_plant_periods} == {"2026-03-07"}
    assert saved_days == ["2026-03-07"]


def test_startup_day_repair_uses_authoritative_start_not_future_scalar_cursor(tmp_path):
    storage = object.__new__(GardenStorage)
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"
    storage.state = GardenState(
        last_processed_revlog_id=9_999_999_999_999,
        processed_revlog_floor=9_999_999_999_999,
        processed_revlog_ids=[],
    )
    storage.state.daily_stats.day = "2026-08-08"
    storage.current_scheduler_day = lambda: "2026-08-09"
    storage.current_day_start_ms = lambda: 1_786_262_400_000
    storage.current_time_ms = lambda: 1_786_270_000_000
    storage.save = lambda: None

    storage._ensure_defaults()

    assert storage.state.daily_stats.day == "2026-08-09"
    assert storage.state.processed_revlog_floor == 1_786_262_399_999
    assert storage.state.processed_revlog_ids == []
    assert storage.state.last_processed_revlog_id == 9_999_999_999_999


def test_atomic_write_failure_preserves_original_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"old": true}', encoding="utf-8")
    storage = storage_at(target)
    original_replace = type(target).replace
    monkeypatch.setattr(type(target), "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    try:
        try:
            storage._atomic_write_json(target, {"new": True})
        except OSError:
            pass
    finally:
        monkeypatch.setattr(type(target), "replace", original_replace)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_corrupt_state_is_backed_up_before_fresh_recovery(tmp_path):
    state_path = tmp_path / "garden_state.json"
    state_path.write_text("{not valid json", encoding="utf-8")

    state = storage_at(state_path)._load()

    assert state.version == STATE_VERSION
    assert state.total_reviews == 0
    backup = state_path.with_suffix(".invalid.json")
    assert backup.read_text(encoding="utf-8") == "{not valid json"


class Tree:
    def __init__(self, deck_id=0, review=0, learn=0, new=0, children=()):
        self.deck_id = deck_id
        self.new_count = new
        self.review_count = review
        self.learn_count = learn
        self.children = list(children)


def test_due_tree_synthetic_root_sums_children_without_double_counting_descendants():
    child = Tree(
        1,
        new=1,
        review=4,
        learn=2,
        children=[Tree(2, new=99, review=99, learn=99)],
    )
    root = Tree(0, children=[child, Tree(3, new=2, review=3, learn=1)])
    assert GardenStorage._due_tree_totals(root) == (3, 3, 7)


class FakeDb:
    def __init__(self, intraday=0, rows=()):
        self.intraday = intraday
        self.rows = list(rows)
        self.calls = []

    def scalar(self, query, *args):
        self.calls.append((query, args))
        if "count() from cards" in query:
            return self.intraday
        if "max(id)" in query:
            return max((row[0] for row in self.rows), default=0)
        return 0

    def all(self, query, *args):
        self.calls.append((query, args))
        return list(self.rows)


def test_retrospective_streak_counts_consecutive_scheduler_days_from_revlog():
    cutoff_ms = int(datetime(2026, 8, 11, 4, 0).timestamp() * 1000)
    db = FakeDb(rows=[
        ("2026-08-10",),
        ("2026-08-09",),
        ("2026-08-08",),
        ("2026-08-06",),
    ])
    storage = object.__new__(GardenStorage)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db))
    storage.current_scheduler_day_bounds_ms = lambda: (cutoff_ms - 86_400_000, cutoff_ms)
    storage.current_scheduler_day = lambda: "2026-08-10"

    snapshot = storage.retrospective_streak()

    assert snapshot.days == 3
    assert snapshot.latest_day == "2026-08-10"
    assert snapshot.studied_today
    query, args = db.calls[-1]
    assert "type in (0, 1, 2, 3)" in query
    assert args[1:] == (cutoff_ms, 10_000)


def test_retrospective_streak_can_end_yesterday_without_resetting_early():
    cutoff_ms = int(datetime(2026, 8, 11, 4, 0).timestamp() * 1000)
    db = FakeDb(rows=[("2026-08-09",), ("2026-08-08",)])
    storage = object.__new__(GardenStorage)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db))
    storage.current_scheduler_day_bounds_ms = lambda: (cutoff_ms - 86_400_000, cutoff_ms)
    storage.current_scheduler_day = lambda: "2026-08-10"

    snapshot = storage.retrospective_streak()

    assert snapshot.days == 2
    assert snapshot.latest_day == "2026-08-09"
    assert not snapshot.studied_today


class FakeScheduler:
    today = 123
    day_cutoff = 1_786_176_000

    def __init__(self, tree):
        self.tree = tree

    def deck_due_tree(self):
        return self.tree


def due_storage(*, tree, intraday=0):
    storage = object.__new__(GardenStorage)
    db = FakeDb(intraday=intraday)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=FakeScheduler(tree)))
    return storage, db


def test_all_due_status_uses_live_review_limits_and_full_day_learning_obligations():
    storage, db = due_storage(
        tree=Tree(1, new=1, review=3, learn=1),
        intraday=4,
    )

    status = storage.due_obligations()

    assert status.new_count == 1
    assert status.review_count == 3
    assert status.learning_count == 4
    assert status.future_learning_count == 3
    assert status.remaining == 8
    assert status.currently_due == 5
    assert status.cutoff_at_ms == FakeScheduler.day_cutoff * 1_000
    query, args = next(call for call in db.calls if "count() from cards" in call[0])
    assert "queue = 1" in query and "queue = 3" in query
    assert "queue = 0" not in query and "queue < 0" not in query
    assert args == (FakeScheduler.day_cutoff, FakeScheduler.today)


def test_all_due_is_recomputed_live_and_includes_filtered_deck_tree_counts():
    filtered = Tree(99, new=1, review=2, learn=1)
    regular = Tree(1, new=0, review=3, learn=0)
    storage, _db = due_storage(tree=Tree(0, children=[regular, filtered]), intraday=1)

    status = storage.due_obligations()
    assert status.new_count == 1
    assert status.review_count == 5
    assert status.learning_count == 1
    assert status.future_learning_count == 0
    assert status.cutoff_at_ms == FakeScheduler.day_cutoff * 1_000

    regular.review_count = 0
    filtered.new_count = 0
    filtered.review_count = 0
    filtered.learn_count = 0
    storage.mw.col.db.intraday = 0
    assert storage.due_obligations().complete


def test_all_due_scheduler_query_failure_fails_closed():
    storage, _db = due_storage(tree=Tree(1))
    storage.mw.col.sched.deck_due_tree = lambda: (_ for _ in ()).throw(RuntimeError("scheduler failed"))

    status = storage.due_obligations()

    assert not status.complete
    assert not status.available
    assert "could not verify" in status.error.lower()


def test_all_due_status_is_complete_only_when_available_and_zero():
    assert DueObligationStatus().complete
    assert not DueObligationStatus(new_count=1).complete
    assert not DueObligationStatus(review_count=1).complete
    assert not DueObligationStatus(available=False).complete
    assert not DueObligationStatus(error="failed").complete


def test_all_due_fails_closed_without_collection():
    storage = object.__new__(GardenStorage)
    storage.mw = SimpleNamespace(col=None)
    status = storage.due_obligations()
    assert not status.available
    assert status.error


def test_today_cards_scope_counts_scheduler_available_new_learn_and_review():
    storage, _db = due_storage(
        tree=Tree(1, new=1, review=18, learn=0),
    )

    status = storage.due_obligations()

    assert (status.new_count, status.learning_count, status.review_count) == (
        1,
        0,
        18,
    )
    assert status.remaining == 19
    assert status.currently_due == 19


def test_due_obligations_classifies_committed_card_and_auto_buried_sibling():
    class TransitionDb(FakeDb):
        def all(self, query, *args):
            self.calls.append((query, args))
            if "select id, nid, queue, due" in query:
                return [(101, 9001, 2, FakeScheduler.today + 1)]
            if "queue in (-3, -2)" in query:
                return [(202,)]
            return []

    storage = object.__new__(GardenStorage)
    db = TransitionDb()
    storage.mw = SimpleNamespace(
        col=SimpleNamespace(db=db, sched=FakeScheduler(Tree(1)))
    )

    status = storage.due_obligations(committed_card_ids=(101,))

    assert status.committed_card_ids == (101,)
    assert status.card_transitions == ((101, "completed"),)
    assert status.committed_card_classification_complete
    assert status.buried_sibling_card_ids == (202,)


def test_same_day_revlog_query_excludes_prior_days_and_manual_types(monkeypatch):
    storage = object.__new__(GardenStorage)
    rows = [(1_786_100_000_001, 1, 3, 1, 0, 2500, 100, 1)]
    db = FakeDb(rows=rows)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=FakeScheduler(Tree())))
    monkeypatch.setattr(
        storage,
        "current_scheduler_day_bounds_ms",
        lambda: (1_786_100_000_000, 1_786_176_000_000),
    )

    assert storage.load_new_revlog_entries(0) == rows
    query, args = db.calls[-1]
    assert "type in (0, 1, 2, 3)" in query
    assert args == (1_786_099_999_999, 1_786_176_000_000, 100_001)


def test_same_day_query_is_full_day_and_excludes_prior_and_future_skew_rows(
    monkeypatch,
):
    day_start = 1_786_100_000_000
    day_end = day_start + 86_400_000
    rows = [
        (day_start - 1, 1, 3, 1, 0, 2500, 100, 1),
        (day_start, 2, 3, 1, 0, 2500, 100, 1),
        (day_start + 82_000_000, 3, 3, 1, 0, 2500, 100, 1),
        (day_end, 4, 3, 1, 0, 2500, 100, 1),
        (day_end + 5_000, 5, 3, 1, 0, 2500, 100, 1),
    ]

    class FilteringDb(FakeDb):
        def all(self, query, *args):
            self.calls.append((query, args))
            lower_bound, upper_bound, limit = args
            return [
                row for row in self.rows
                if lower_bound < row[0] < upper_bound
            ][:limit]

    storage = object.__new__(GardenStorage)
    db = FilteringDb(rows=rows)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=FakeScheduler(Tree())))
    monkeypatch.setattr(
        storage,
        "current_scheduler_day_bounds_ms",
        lambda: (day_start, day_end),
    )

    loaded = storage.load_new_revlog_entries(day_end + 99_999)

    assert [row[0] for row in loaded] == [day_start, day_start + 82_000_000]


def test_same_day_revlog_query_failure_is_not_indistinguishable_from_no_rows(monkeypatch):
    storage = object.__new__(GardenStorage)
    db = FakeDb()
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=FakeScheduler(Tree())))
    monkeypatch.setattr(
        storage,
        "current_scheduler_day_bounds_ms",
        lambda: (1_786_100_000_000, 1_786_176_000_000),
    )

    def fail_all(*_args, **_kwargs):
        raise OSError("collection read unavailable")

    monkeypatch.setattr(db, "all", fail_all)

    with pytest.raises(RevlogReadError, match="could not read same-day review history"):
        storage.load_new_revlog_entries(0)


def test_scheduler_day_query_fails_closed_instead_of_truncating_ledger_input(monkeypatch):
    storage = object.__new__(GardenStorage)
    rows = [
        (100 + index, index, 3, 1, 0, 2500, 100, 1)
        for index in range(3)
    ]
    db = FakeDb(rows=rows)
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=FakeScheduler(Tree())))
    monkeypatch.setattr(
        storage,
        "current_scheduler_day_bounds_ms",
        lambda: (100, 300),
    )

    with pytest.raises(RevlogReadError, match="safety bound"):
        storage.load_new_revlog_entries(0, limit=2)


def test_latest_revlog_query_failure_is_explicit_instead_of_returning_zero(monkeypatch):
    storage = object.__new__(GardenStorage)
    db = FakeDb()
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db))

    def fail_scalar(*_args, **_kwargs):
        raise OSError("collection read unavailable")

    monkeypatch.setattr(db, "scalar", fail_scalar)

    with pytest.raises(RevlogReadError, match="latest review-history id"):
        storage.max_revlog_id()


def test_missing_scheduler_cutoff_stops_catchup_before_any_history_query(monkeypatch):
    storage = object.__new__(GardenStorage)
    db = FakeDb(rows=[(1, 1, 3, 1, 0, 2500, 100, 1)])
    storage.mw = SimpleNamespace(col=SimpleNamespace(db=db, sched=SimpleNamespace()))

    with pytest.raises(SchedulerBoundaryError, match="cutoff is unavailable"):
        storage.load_new_revlog_entries(0)

    assert db.calls == []


@pytest.mark.parametrize(
    ("cutoff", "expected_start", "elapsed_hours"),
    [
        ((2026, 3, 8, 4), (2026, 3, 7, 4), 23),
        ((2026, 11, 1, 4), (2026, 10, 31, 4), 25),
    ],
)
def test_scheduler_day_start_preserves_local_rollover_time_across_dst(
    cutoff,
    expected_start,
    elapsed_hours,
):
    old_timezone = os.environ.get("TZ")
    os.environ["TZ"] = "America/Chicago"
    time.tzset()
    try:
        zone = ZoneInfo("America/Chicago")
        cutoff_at = datetime(*cutoff, tzinfo=zone)
        expected = datetime(*expected_start, tzinfo=zone)
        storage = object.__new__(GardenStorage)
        storage.current_day_end_ms = lambda: int(cutoff_at.timestamp() * 1000)

        start_ms = storage.current_day_start_ms()

        assert start_ms == int(expected.timestamp() * 1000)
        assert (int(cutoff_at.timestamp() * 1000) - start_ms) / 3_600_000 == elapsed_hours
    finally:
        if old_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_timezone
        time.tzset()


def test_scheduler_day_is_derived_from_anki_cutoff_not_wall_clock(monkeypatch):
    storage = object.__new__(GardenStorage)
    monkeypatch.setattr(storage, "current_day_start_ms", lambda: 1_786_100_000_000)
    assert storage.current_scheduler_day() == "2026-08-07"
