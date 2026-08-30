from __future__ import annotations

import uuid

from ankigarden.growth import (
    CompletedGrowthChargeRequest,
    GrowthChargeOutcome,
    GrowthChargeStatus,
)
from ankigarden.models.state import GardenState, Plant, STATE_VERSION
from ankigarden.purchases import (
    CompletedPurchaseRequest,
    PurchaseDisposition,
    PurchaseOutcome,
    PurchaseStatus,
)
from ankigarden.reward_ledger import (
    AnswerConsumptionRecord,
    DailyEconomySnapshotRecord,
    EconomyEventRecord,
    IdempotencyRecord,
    RewardEventRecord,
    RewardLedger,
    UNBOUNDED_STATE_AUTHORITY_KEYS,
)
from ankigarden.storage import GardenStorage, migrate_modern_state


def _recorded_plant_purchase(amount: int) -> CompletedPurchaseRequest:
    return CompletedPurchaseRequest(
        request_id=str(uuid.UUID("00000000-0000-0000-0000-000000000123")),
        request_fingerprint="a" * 64,
        outcome=PurchaseOutcome(
            status=PurchaseStatus.SUCCESS,
            item_id="dahlia",
            item_name="Dahlia",
            category="Plant",
            quantity=1,
            amount_spent=amount,
            new_balance=100,
            disposition=PurchaseDisposition.COLLECTION,
            message="Added.",
            result_id="plant:dahlia",
            applied=True,
        ),
        occurred_at="2026-08-29T12:00:00+00:00",
    )


def test_v25_migration_preserves_growth_and_converts_paid_effects_by_ceil() -> None:
    state = GardenState(
        plants=[Plant("plant-1", "bonsai", "Moss", 0)],
        unlocked_slots=6,
        stored_growth_units=12_345,
        currency_balance=10,
        completed_purchase_requests=[_recorded_plant_purchase(600)],
    )
    payload = state.to_dict()
    payload["version"] = 25
    payload["loadout"] = {
        "displayed_garden_feature_id": "garden_bench",
        "active_bonus_garden_feature_id": "wind_chime",
        "scenery_id": "full_moon",
        "visibility": {"garden_feature": True, "scenery": True},
    }
    payload["inventory"]["decorations"] = ["garden_bench"]
    payload["inventory"]["garden_features"].append("wind_chime")
    payload["inventory"]["scenery"].append("full_moon")
    payload["plants"][0].pop("card_effect_queue", None)
    payload["plants"][0]["fertilizer"] = {
        "tier": "basic",
        "growth_per_answer": 1,
        "started_at": 0.0,
        "expires_at": 2_801.0,
    }
    payload["plants"][0]["fertilizer_history"] = []
    payload["consumables"]["rich_compost"] = 2
    payload["environment_completion_pity_misses"] = {
        "rare": 99,
        "very_rare": 99,
        "ultra": 99,
    }
    payload.pop("full_moon_completion_progress", None)
    payload["environment_completion_counts"] = {"full_moon": 7}

    migrated = migrate_modern_state(payload, migrated_at=1_000.0)

    assert migrated.version == STATE_VERSION == 26
    assert migrated.stored_growth_units == 12_345
    assert migrated.earned_bed_unlocks == [3, 4, 5, 6]
    assert {
        "first_canopy",
        "first_full_bloom",
        "growing_garden",
        "flourishing_garden",
    }.issubset(migrated.achievements)
    assert all(
        migrated.achievements[item_id].unlocked
        for item_id in (
            "first_canopy",
            "first_full_bloom",
            "growing_garden",
            "flourishing_garden",
        )
    )
    assert migrated.loadout.display_decoration_id == "garden_bench"
    assert migrated.loadout.active_garden_bonus_id == "wind_chime"
    assert migrated.loadout.display_scenery_id == "full_moon"
    assert migrated.loadout.active_scenery_effect_id == "full_moon"
    assert migrated.inventory["cosmetics"] == ["garden_bench"]
    assert migrated.consumables["fertilizer_basic"] == 2
    assert migrated.environment_completion_pity_misses == {
        "rare": 0,
        "very_rare": 0,
        "ultra": 0,
    }
    assert migrated.full_moon_completion_progress == 5
    batch = migrated.plants[0].card_effect_queue.fertilizer_batches[0]
    # 1,801 seconds of a 3,600-second dose: ceil(100 * 1801 / 3600) = 51.
    assert (batch.total_cards, batch.remaining_cards) == (100, 51)
    assert migrated.plants[0].fertilizer is None
    grants = {grant.event_key: grant.coins for grant in migrated.pending_economy_migration_grants}
    assert grants == {
        "migration:v26:bed_refund:3": 150,
        "migration:v26:bed_refund:4": 300,
        "migration:v26:bed_refund:5": 500,
        "migration:v26:bed_refund:6": 800,
        "migration:v26:plant_refund:00000000-0000-0000-0000-000000000123": 350,
    }


def test_full_moon_migration_preserves_each_old_fraction_without_overpaying() -> None:
    expected_by_old_remainder = {0: 0, 1: 2, 2: 3, 3: 5}
    for old_remainder, expected_progress in expected_by_old_remainder.items():
        payload = GardenState().to_dict()
        payload["version"] = 25
        payload.pop("full_moon_completion_progress", None)
        payload["environment_completion_counts"] = {
            "full_moon": 8 + old_remainder
        }

        migrated = migrate_modern_state(payload, migrated_at=1_000.0)

        assert migrated.full_moon_completion_progress == expected_progress


def test_schema25_growth_overflow_is_conserved_in_exact_stored_units() -> None:
    payload = GardenState(
        plants=[
            Plant(
                "full",
                "bonsai",
                "Moss",
                0,
                growth_points=50_000,
                growth_remainder_units=75,
            ),
            Plant(
                "one-over",
                "rose",
                "Rose",
                1,
                growth_points=35_001,
                growth_remainder_units=25,
            ),
        ],
        stored_growth_units=123,
    ).to_dict()
    payload["version"] = 25
    # Keep the v25 fixture explicit at the migration boundary.
    payload["plants"][0]["growth_points"] = 50_000
    payload["plants"][0]["growth_remainder_units"] = 75
    payload["plants"][1]["growth_points"] = 35_001
    payload["plants"][1]["growth_remainder_units"] = 25

    migrated = migrate_modern_state(payload, migrated_at=1_000.0)

    assert [plant.growth_points for plant in migrated.plants] == [35_000, 35_000]
    assert [plant.growth_remainder_units for plant in migrated.plants] == [0, 0]
    assert migrated.stored_growth_units == 1_500_323
    reloaded = GardenState.from_dict(migrated.to_dict())
    assert reloaded.stored_growth_units == 1_500_323

    retry_payload = migrated.to_dict()
    retry_payload["version"] = 25
    retried = migrate_modern_state(retry_payload, migrated_at=1_001.0)
    assert retried.stored_growth_units == 1_500_323


def test_pending_migration_refunds_commit_once_with_permanent_identities(
    tmp_path,
) -> None:
    payload = GardenState(unlocked_slots=4, currency_balance=10).to_dict()
    payload["version"] = 25
    state = migrate_modern_state(payload, migrated_at=1_000.0)
    ledger = RewardLedger(tmp_path / "ledger.sqlite3")

    GardenStorage._apply_pending_economy_migration_grants(ledger, state)
    assert state.currency_balance == 460
    assert state.pending_economy_migration_grants == []
    assert state.lifetime_economy_aggregates.coins_earned_by_source == {
        "bed_refund": 450
    }
    bounded_payload = {
        key: value
        for key, value in state.to_dict().items()
        if key not in UNBOUNDED_STATE_AUTHORITY_KEYS
    }
    ledger.commit_state(
        bounded_payload, schema_version=26, expected_revision=0
    )
    ledger.close()

    reopened = RewardLedger(tmp_path / "ledger.sqlite3")
    assert reopened.idempotency_record(
        "migration", "migration:v26:bed_refund:3"
    ) is not None
    assert reopened.idempotency_record(
        "migration", "migration:v26:bed_refund:4"
    ) is not None
    assert reopened.lifetime_economy_aggregates()["coins_earned_by_source"] == {
        "bed_refund": 450
    }
    restored = GardenState.from_dict(reopened.load_state_snapshot().payload)
    GardenStorage._apply_pending_economy_migration_grants(reopened, restored)
    assert restored.currency_balance == 460
    assert not reopened.has_staged_writes
    reopened.close()


def test_v25_bounded_request_receipts_seed_permanent_idempotency(tmp_path) -> None:
    purchase = _recorded_plant_purchase(250)
    growth_charge = CompletedGrowthChargeRequest(
        request_id="00000000-0000-4000-8000-000000000456",
        request_fingerprint="b" * 64,
        outcome=GrowthChargeOutcome(
            status=GrowthChargeStatus.SUCCESS,
            charge_id="growth_charge_small",
            charge_name="Small Growth Charge",
            target_id="plant-1",
            target_name="Moss",
            previous_growth=100,
            resulting_growth=200,
            growth_granted=100,
            previous_stage="seed",
            resulting_stage="seed",
            completed_stages=(),
            rewards=(),
            inventory_remaining=0,
            message="Applied.",
        ),
        occurred_at="2026-08-29T12:00:01+00:00",
    )
    state = GardenState(
        completed_purchase_requests=[purchase],
        completed_growth_charge_requests=[growth_charge],
    )
    ledger = RewardLedger(tmp_path / "ledger.sqlite3")

    GardenStorage._stage_legacy_economy_idempotency(ledger, state)
    assert ledger.idempotency_record("purchase", purchase.request_id).outcome == (
        purchase.outcome.to_dict()
    )
    assert ledger.idempotency_record(
        "growth_charge", growth_charge.request_id
    ).outcome == growth_charge.outcome.to_dict()
    ledger.rollback_all()
    ledger.close()


def test_storage_wrappers_expose_snapshot_and_rhythm_history(tmp_path) -> None:
    ledger = RewardLedger(tmp_path / "ledger.sqlite3")
    ledger.stage_answer_consumption(AnswerConsumptionRecord(
        "answer-1", "2026-08-28"
    ))
    ledger.stage_reward_event(RewardEventRecord("all_due:2026-08-28"))
    storage = GardenStorage.__new__(GardenStorage)
    storage.state = GardenState()
    storage._reward_ledger = ledger
    storage._ledger_revision = 0

    snapshot = storage.stage_daily_economy_snapshot(
        DailyEconomySnapshotRecord(
            anki_day="2026-08-30",
            garden_rhythm_percent=2,
            active_garden_bonus_id="seedling_sign",
            active_scenery_effect_id="default",
            snapshot_source="local_first_answer",
            snapshot_id="snapshot:2026-08-30",
        )
    )
    storage.stage_idempotency_record(IdempotencyRecord(
        "landmark",
        "landmark:request:1",
        "c" * 64,
        {"status": "completed"},
    ))
    storage.stage_economy_event(EconomyEventRecord(
        event_key="landmark:complete:mossy_stone_path",
        event_kind="landmark_completion",
        sink_id="landmark:mossy_stone_path",
        coins_spent=250,
        growth_spent_on_landmarks=2_500_000,
    ))
    assert storage.daily_economy_snapshot("2026-08-30") == snapshot
    assert storage.idempotency_record(
        "landmark", "landmark:request:1"
    ) is not None
    rebuilt = storage.refresh_lifetime_economy_aggregates()
    assert rebuilt.coins_spent_by_sink == {
        "landmark:mossy_stone_path": 250
    }
    assert rebuilt.growth_spent_on_landmarks == 2_500_000
    assert storage.eligible_study_days_before("2026-08-30") == ("2026-08-28",)
    assert storage.verified_today_cards_completion_days_before("2026-08-30") == {
        "2026-08-28"
    }
    ledger.rollback_all()
    ledger.close()
