from __future__ import annotations

import json
from pathlib import Path

from ankigarden.models.state import (
    CardEffectBatch,
    DailyCompletionState,
    DailyLoadoutSchedule,
    DailyStats,
    GardenState,
    Fertilizer,
    Plant,
    STATE_VERSION,
)
from ankigarden.reward_ledger import (
    RewardEventRecord,
    RewardLedger,
    UNBOUNDED_STATE_AUTHORITY_KEYS,
)
from ankigarden.storage import GardenStorage, migrate_modern_state


def _schema21_payload(state: GardenState) -> dict:
    payload = state.to_dict()
    payload["version"] = 21
    for key in (
        "daily_completion",
        "daily_loadout",
        "stored_growth_units",
        "streak_growth_remainder_units",
        "checkpoint_coin_carry_units",
        "first_daily_completion_reward_claimed",
        "environment_pity_misses",
    ):
        payload.pop(key, None)
    for key in (
        "answer_growth_units",
        "instant_growth_units",
        "applied_growth_units",
        "redirected_growth_units",
        "shared_growth_units",
        "stored_growth_units",
        "plant_applied_growth_units",
        "plant_shared_growth_units",
        "plant_instant_growth_units",
    ):
        payload["daily_stats"].pop(key, None)
    for plant in payload["plants"]:
        for key in (
            "growth_remainder_units",
            "checkpoint_claims",
            "stage_reward_claims",
            "completed_on",
            "completed_at_ms",
            "completion_cards",
            "completion_active_days",
            "full_bloom_reward_claimed",
            "fertilizer_card_batches",
            "fertilizer_card_queue",
            "booster_card_batches",
            "booster_card_queue",
        ):
            plant.pop(key, None)
    return payload


def _storage_for(tmp_path: Path) -> GardenStorage:
    storage = object.__new__(GardenStorage)
    storage.user_files_dir = tmp_path
    storage.data_path = tmp_path / "garden_state.json"
    storage.database_path = tmp_path / "garden_state.sqlite3"
    storage._reward_ledger = None
    storage._ledger_revision = 0
    return storage


def test_schema22_exact_progression_fields_round_trip() -> None:
    batch = CardEffectBatch(
        effect_id="fertilizer_quality",
        growth_per_card_units=200,
        total_cards=150,
        remaining_cards=83,
        activated_at="2026-08-28T12:00:00+00:00",
        source_event_key="purchase:quality:1",
    )
    plant = Plant(
        "p",
        "bonsai",
        "Moss",
        0,
        growth_points=999,
        growth_remainder_units=75,
        checkpoint_claims=["sprout:25"],
        stage_reward_claims=["sprout"],
        fertilizer_card_batches=[batch],
    )
    state = GardenState(
        plants=[plant],
        active_plant_id="p",
        daily_stats=DailyStats(
            day="2026-08-28",
            answer_growth_units=1_350,
            instant_growth_units=10_000,
            applied_growth_units=500,
            redirected_growth_units=850,
            shared_growth_units=270,
            stored_growth_units=50,
            plant_applied_growth_units={"p": 500},
            plant_shared_growth_units={"p": 270},
            plant_instant_growth_units={"p": 10_000},
        ),
        daily_completion=DailyCompletionState(
            scheduler_day="2026-08-28",
            status="in_progress",
            starting_required_cards=160,
            starting_required_cards_completed=142,
            remaining_required_reviews=16,
            remaining_learning_steps=2,
            cards_completed_today=176,
        ),
        daily_loadout=DailyLoadoutSchedule(
            scheduler_day="2026-08-28",
            locked_at_ms=1_777_000_000_000,
            weather_id="sunny",
            scenery_id="default",
            queued_for_day="2026-08-29",
            queued_weather_id="sunny",
            queued_scenery_id="default",
        ),
        stored_growth_units=1_250,
        streak_growth_remainder_units=50,
        checkpoint_coin_carry_units=50,
        environment_pity_misses={"rare": 12, "very_rare": 34, "ultra": 56},
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.version == STATE_VERSION == 27
    assert restored.plants[0].growth_units == 99_975
    assert restored.plants[0].fertilizer_card_batches == [batch]
    assert restored.stored_growth_units == 1_250
    assert restored.streak_growth_remainder_units == 50
    assert restored.checkpoint_coin_carry_units == 50
    assert restored.daily_stats.plant_applied_growth_units == {"p": 500}
    assert restored.daily_stats.plant_shared_growth_units == {"p": 270}
    assert restored.daily_completion.cards_completed_today == 176
    assert restored.daily_loadout.queued_for_day == "2026-08-29"
    assert restored.environment_pity_misses == {
        "rare": 12,
        "very_rare": 34,
        "ultra": 56,
    }


def test_schema21_migration_preserves_value_and_preclaims_crossed_rewards() -> None:
    state = GardenState(
        plants=[Plant(
            "p",
            "bonsai",
            "Moss",
            0,
            growth_points=1_000,
            bonus_remainder=50,
        )],
        active_plant_id="p",
        garden_find_ultra_misses=77,
    )
    payload = _schema21_payload(state)
    payload["daily_stats"].update({
        "day": "2026-08-28",
        "reviewed": 176,
        "completed_due_cards": True,
    })
    payload["plants"][0]["fertilizer"] = {
        "tier": "quality",
        "growth_per_answer": 2,
        "started_at": 1_000.0,
        "expires_at": 2_000.0,
    }
    payload["plants"][0]["booster"] = {
        "growth_per_answer": 5,
        "started_at": 1_100.0,
        "expires_at": 1_900.0,
    }

    migrated = migrate_modern_state(payload, migrated_at=1_500.0)
    plant = migrated.plants[0]

    assert migrated.version == STATE_VERSION
    assert plant.growth_remainder_units == 0
    assert migrated.streak_growth_remainder_units == 50
    assert plant.stage_reward_claims == ["sprout"]
    assert plant.checkpoint_claims == [
        "sprout:25",
        "sprout:50",
        "sprout:75",
        "young:25",
    ]
    assert plant.fertilizer is None
    assert len(plant.fertilizer_card_batches) == 1
    assert plant.fertilizer_card_queue == []
    fertilizer_batch = plant.card_effect_queue.fertilizer_batches[0]
    assert plant.fertilizer_card_batches[0] == fertilizer_batch
    assert (
        fertilizer_batch.effect_id,
        fertilizer_batch.growth_per_card_units,
        fertilizer_batch.total_cards,
        fertilizer_batch.remaining_cards,
    ) == ("fertilizer_quality", 200, 200, 14)
    assert plant.booster is None
    assert len(plant.booster_card_batches) == 1
    assert plant.booster_card_batches[0].effect_id == "booster_potion"
    assert plant.booster_card_batches[0].remaining_cards == 100
    assert plant.booster_card_queue == []
    assert plant.card_effect_queue.booster_remaining_cards == 100
    assert migrated.daily_completion.status == "complete"
    assert migrated.daily_completion.cards_completed_today == 176
    assert migrated.daily_completion.reward_claimed
    assert migrated.first_daily_completion_reward_claimed
    assert migrated.environment_pity_misses == {
        "rare": 0,
        "very_rare": 0,
        "ultra": 77,
    }


def test_authoritative_schema22_restores_experimental_fertilizer_cards_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = _storage_for(tmp_path)
    batch = CardEffectBatch(
        effect_id="fertilizer_quality",
        growth_per_card_units=200,
        total_cards=150,
        remaining_cards=75,
        activated_at="2026-08-28T12:00:00+00:00",
        source_event_key="purchase:quality:1",
    )
    state = GardenState(plants=[Plant(
        "p",
        "bonsai",
        "Moss",
        0,
        fertilizer=Fertilizer("quality", 2, 2_000.0, 1_000.0),
        fertilizer_card_batches=[batch],
    )])
    payload = state.to_dict()
    for key in UNBOUNDED_STATE_AUTHORITY_KEYS:
        payload.pop(key, None)
    ledger = RewardLedger(storage.database_path)
    payload["version"] = 22
    ledger.commit_state(payload, schema_version=22, expected_revision=0)
    ledger.close()
    monkeypatch.setattr("ankigarden.storage.time.time", lambda: 1_500.0)

    restored = storage._load_authoritative_state()

    plant = restored.plants[0]
    assert plant.fertilizer is None
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
        ("fertilizer_quality", 200, 200, 14),
        ("fertilizer_quality", 200, 150, 75),
    ]
    assert storage._reward_ledger is not None
    snapshot = storage._reward_ledger.load_state_snapshot()
    assert snapshot is not None
    assert snapshot.revision == 2
    assert len(snapshot.payload["plants"][0]["fertilizer_card_batches"]) == 1
    assert len(snapshot.payload["plants"][0]["fertilizer_card_queue"]) == 1
    assert snapshot.payload["plants"][0]["fertilizer_history"] == []
    assert [
        (
            batch["effect_id"],
            batch["total_cards"],
            batch["remaining_cards"],
        )
        for batch in snapshot.payload["plants"][0]["card_effect_queue"]["fertilizer_batches"]
    ] == [
        ("fertilizer_quality", 200, 14),
        ("fertilizer_quality", 150, 75),
    ]
    storage._reward_ledger.close()


def test_schema21_json_load_is_backed_up_and_upgraded(tmp_path: Path) -> None:
    storage = _storage_for(tmp_path)
    storage.data_path.write_text(
        json.dumps(_schema21_payload(GardenState(currency_balance=321))),
        encoding="utf-8",
    )

    restored = storage._load()

    assert restored.version == STATE_VERSION
    assert restored.currency_balance == 321
    backup = storage.data_path.with_suffix(".schema-21.legacy.json")
    assert backup.exists()
    assert json.loads(backup.read_text("utf-8"))["version"] == 21


def test_authoritative_schema21_sqlite_is_backed_up_and_upgraded(
    tmp_path: Path,
) -> None:
    storage = _storage_for(tmp_path)
    ledger = RewardLedger(storage.database_path)
    ledger.stage_reward_event(RewardEventRecord("legacy:reward"))
    payload = _schema21_payload(GardenState(currency_balance=444))
    for key in UNBOUNDED_STATE_AUTHORITY_KEYS:
        payload.pop(key, None)
    ledger.commit_state(payload, schema_version=21, expected_revision=0)
    ledger.close()

    restored = storage._load_authoritative_state()

    assert restored.version == STATE_VERSION
    assert restored.currency_balance == 444
    assert storage._reward_ledger is not None
    snapshot = storage._reward_ledger.load_state_snapshot()
    assert snapshot is not None
    assert snapshot.schema_version == STATE_VERSION
    assert snapshot.revision == 2
    assert storage._reward_ledger.reward_applied("legacy:reward")
    backups = list(tmp_path.glob("garden_state.schema-21.legacy-*.sqlite3"))
    assert len(backups) == 1
    preserved = RewardLedger(backups[0])
    try:
        old_snapshot = preserved.load_state_snapshot()
        assert old_snapshot is not None
        assert old_snapshot.schema_version == 21
        assert preserved.reward_applied("legacy:reward")
    finally:
        preserved.close()
        storage._reward_ledger.close()
