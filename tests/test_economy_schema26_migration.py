from __future__ import annotations

import json
import uuid

import pytest

from ankigarden.growth import (
    CompletedGrowthChargeRequest,
    GrowthChargeOutcome,
    GrowthChargeStatus,
)
from ankigarden.models.state import (
    CURRENT_CATALOG_SPECIES_ORDER,
    GARDEN_LEGACY_LEVEL_COST_UNITS,
    LANDMARK_MAX_GROWTH_UNITS,
    MASTERY_MAX_GROWTH_UNITS_PER_SPECIES,
    GardenState,
    Plant,
    STATE_VERSION,
)
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
    RewardLedgerCorruptionError,
    UNBOUNDED_STATE_AUTHORITY_KEYS,
)
from ankigarden.storage import (
    GardenStorage,
    StatePreservationError,
    migrate_modern_state,
)


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


def test_plant_beds_restore_legacy_completion_without_inventing_bonus_receipt():
    from ankigarden.models.state import Achievement
    from ankigarden.plant_beds import plant_bed_progress

    state = GardenState(plants=[Plant("retained", "bonsai", "Retained", 0)],
                        active_plant_id="retained")
    state.achievements["flourishing_garden"] = Achievement(
        "flourishing_garden", "Flourishing Garden", "", unlocked=True,
        unlocked_at="2026-09-07T12:00:00+00:00")
    loaded = GardenState.from_dict(state.to_dict())
    bed = plant_bed_progress(loaded)[5]
    assert loaded.unlocked_slots == 6 and bed.unlocked
    assert bed.unlocked_at == "2026-09-07T12:00:00+00:00"
    assert not bed.bonus_received and bed.current == 0
    assert loaded.plants[0].slot_index == 0 and loaded.active_plant_id == "retained"
    again = GardenState.from_dict(loaded.to_dict())
    assert plant_bed_progress(again) == plant_bed_progress(loaded)
    assert again.consumables == loaded.consumables


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

    migrated = migrate_modern_state(payload, migrated_at=1_000.0)

    assert migrated.version == STATE_VERSION
    assert migrated.stored_growth_units == 12_345
    assert migrated.earned_bed_unlocks == [3, 4, 5, 6]
    from ankigarden.plant_beds import plant_bed_progress
    beds = plant_bed_progress(migrated)
    assert all(bed.unlocked and bed.unlocked_at is None for bed in beds)
    assert not beds[5].bonus_received  # A purchased-bed migration is not an item grant.
    reloaded = GardenState.from_dict(migrated.to_dict())
    assert plant_bed_progress(reloaded) == beds
    assert reloaded.consumables == migrated.consumables
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
    assert migrated.loadout.display_decoration_id == "seedling_sign"
    assert migrated.loadout.active_garden_bonus_id == "seedling_sign"
    assert migrated.loadout.display_scenery_id == "full_moon"
    assert migrated.loadout.active_scenery_effect_id == "full_moon"
    assert migrated.inventory["cosmetics"] == ["garden_bench"]
    assert migrated.consumables["fertilizer_basic"] == 2
    assert migrated.environment_completion_pity_misses == {
        "rare": 0,
        "very_rare": 0,
        "ultra": 0,
    }
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


def test_storage_wrappers_expose_snapshot_and_completion_history(tmp_path) -> None:
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
    storage.state.stored_growth_opening_balance_units = 123
    storage.state.stored_growth_opening_balance_source = (
        "schema_27_migration_preserved_balance"
    )
    storage.state.stored_growth_opening_balance_identity = (
        "migration:schema27:stored-growth-opening"
    )
    storage.state.stored_growth_balance_units = 113
    storage.state.garden_project.landmark_growth_units_funded = 10
    storage.stage_economy_event(EconomyEventRecord(
        event_key="growth-project:opening-reconciliation",
        event_kind="growth_project_contribute",
        sink_id="garden_landmark",
        growth_flow_kind="manual_contribution",
        stored_growth_balance_delta_units=-10,
        growth_contributed_to_landmarks_units=10,
        metric_deltas={
            "project_allocations": {"landmark:garden_landmark": 10}
        },
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


def test_schema26_to_27_preserves_value_and_grandfathers_claimed_funding(
    tmp_path,
) -> None:
    payload = GardenState(currency_balance=777, stored_growth_units=123_456).to_dict()
    payload["version"] = 26
    payload["stored_growth_units"] = payload.pop("stored_growth_balance_units")
    payload["garden_project"] = {
        "selected_project_id": "lily_pond",
        "contributed_growth_units": 1_500_000,
        "ready_to_complete": False,
        "completed_project_ids": ["mossy_stone_path", "birdbath_terrace"],
        "displayed_project_id": "birdbath_terrace",
        "auto_contribute": True,
    }
    payload["cultivation_mastery"] = {
        "highest_rank_by_species": {"bonsai": "gold"},
    }

    migrated = migrate_modern_state(payload, migrated_at=1_000.0)

    assert migrated.currency_balance == 777
    assert migrated.stored_growth_balance_units == 123_456
    assert migrated.stored_growth_opening_balance_units == 123_456
    assert migrated.stored_growth_opening_balance_source == (
        "schema_27_migration_preserved_balance"
    )
    assert migrated.stored_growth_opening_balance_identity == (
        "migration:schema27:stored-growth-opening"
    )
    assert migrated.active_growth_target_type == ""
    assert migrated.garden_project.landmark_highest_claimed_tier == 2
    assert migrated.garden_project.landmark_growth_units_funded == 11_500_000
    assert migrated.garden_project.grandfathered_funding_units == 11_500_000
    assert migrated.cultivation_mastery.highest_rank_by_species == {
        "bonsai": "gold"
    }
    assert migrated.cultivation_mastery.growth_units_funded_by_species == {
        "bonsai": 17_500_000
    }
    assert (
        migrated.cultivation_mastery
        .grandfathered_funding_units_by_species
    ) == {"bonsai": 17_500_000}
    assert migrated.garden_legacy_level == migrated.garden_legacy_progress_units == 0
    ledger = RewardLedger(tmp_path / "preserved-endgame.sqlite3")
    GardenStorage._initialize_schema27_migration_metadata(ledger, migrated)
    migration = ledger.idempotency_record(
        "migration", "migration:schema27:economy-authorities"
    )
    assert migration is not None
    assert migration.outcome["landmark_grandfathered_funding_units"] == (
        11_500_000
    )
    assert migration.outcome["landmark_highest_claimed_tier_baseline"] == 2
    assert migration.outcome[
        "mastery_grandfathered_funding_units_by_species"
    ] == {"bonsai": 17_500_000}
    assert migration.outcome[
        "mastery_highest_claimed_rank_baseline_by_species"
    ] == {"bonsai": "gold"}
    ledger.rollback_all()
    ledger.close()


def test_schema26_empty_history_stays_explicitly_incomplete(tmp_path) -> None:
    payload = GardenState().to_dict()
    payload["version"] = 26
    state = migrate_modern_state(payload, migrated_at=1_000.0)
    ledger = RewardLedger(tmp_path / "empty-history.sqlite3")

    GardenStorage._initialize_schema27_migration_metadata(ledger, state)

    storage = GardenStorage.__new__(GardenStorage)
    storage.state = state
    storage._reward_ledger = ledger
    storage._ledger_revision = 0
    assert not storage.refresh_lifetime_economy_aggregates().history_complete
    ledger.rollback_all()
    ledger.close()


@pytest.mark.parametrize(
    ("case", "error_pattern"),
    (
        ("exact", None),
        ("unbacked_funding", "do not reconcile"),
        ("unpaid_claim", "unfunded, or unpaid"),
    ),
)
def test_schema27_endgame_state_reconciles_exact_funding_and_claims(
    tmp_path,
    case: str,
    error_pattern: str | None,
) -> None:
    state = GardenState(stored_growth_units=5_000_000)
    state.stored_growth_opening_balance_units = 5_000_000
    ledger = RewardLedger(tmp_path / f"endgame-{case}.sqlite3")
    GardenStorage._initialize_schema27_migration_metadata(ledger, state)
    for event in (
        EconomyEventRecord(
            "project:landmark",
            "growth_project_contribute",
            sink_id="garden_landmark",
            growth_flow_kind="manual_contribution",
            stored_growth_balance_delta_units=-2_500_000,
            growth_contributed_to_landmarks_units=2_500_000,
            metric_deltas={
                "project_allocations": {
                    "landmark:garden_landmark": 2_500_000
                }
            },
        ),
        EconomyEventRecord(
            "project:mastery",
            "growth_project_contribute",
            sink_id="bonsai",
            growth_flow_kind="manual_contribution",
            stored_growth_balance_delta_units=-2_500_000,
            growth_contributed_to_mastery_units=2_500_000,
            metric_deltas={
                "project_allocations": {"mastery:bonsai": 2_500_000}
            },
        ),
        EconomyEventRecord(
            "claim:landmark",
            "growth_project_claim",
            sink_id="garden_landmark",
            coins_spent=0 if case == "unpaid_claim" else 250,
            growth_flow_kind="claim",
            item_id="mossy_stone_path",
            quantity=1,
        ),
        EconomyEventRecord(
            "claim:mastery",
            "growth_project_claim",
            sink_id="bonsai",
            coins_spent=50,
            growth_flow_kind="claim",
            item_id="bronze",
            quantity=1,
        ),
    ):
        ledger.stage_economy_event(event)
    state.stored_growth_balance_units = 0
    state.garden_project.landmark_growth_units_funded = (
        2_500_001 if case == "unbacked_funding" else 2_500_000
    )
    state.garden_project.landmark_highest_claimed_tier = 1
    state.cultivation_mastery.growth_units_funded_by_species = {
        "bonsai": 2_500_000
    }
    state.cultivation_mastery.highest_claimed_rank_by_species = {
        "bonsai": "bronze"
    }
    storage = GardenStorage.__new__(GardenStorage)
    storage.state = state
    storage._reward_ledger = ledger
    storage._ledger_revision = 0

    if error_pattern is None:
        storage.refresh_lifetime_economy_aggregates()
    else:
        with pytest.raises(RewardLedgerCorruptionError, match=error_pattern):
            storage.refresh_lifetime_economy_aggregates()
    ledger.rollback_all()
    ledger.close()


def test_schema27_legacy_progress_reconciles_after_finite_funding(tmp_path) -> None:
    state = GardenState(stored_growth_units=GARDEN_LEGACY_LEVEL_COST_UNITS)
    state.stored_growth_opening_balance_units = GARDEN_LEGACY_LEVEL_COST_UNITS
    state.garden_project.landmark_growth_units_funded = LANDMARK_MAX_GROWTH_UNITS
    state.cultivation_mastery.growth_units_funded_by_species = {
        species_id: MASTERY_MAX_GROWTH_UNITS_PER_SPECIES
        for species_id in CURRENT_CATALOG_SPECIES_ORDER
    }
    ledger = RewardLedger(tmp_path / "legacy.sqlite3")
    GardenStorage._initialize_schema27_migration_metadata(ledger, state)
    ledger.stage_economy_event(EconomyEventRecord(
        "project:legacy",
        "growth_project_contribute",
        sink_id="garden_legacy",
        growth_flow_kind="manual_contribution",
        stored_growth_balance_delta_units=-GARDEN_LEGACY_LEVEL_COST_UNITS,
        growth_contributed_to_legacy_units=GARDEN_LEGACY_LEVEL_COST_UNITS,
        metric_deltas={
            "project_allocations": {
                "legacy:garden_legacy": GARDEN_LEGACY_LEVEL_COST_UNITS
            }
        },
    ))
    state.stored_growth_balance_units = 0
    state.garden_legacy_level = 1
    storage = GardenStorage.__new__(GardenStorage)
    storage.state = state
    storage._reward_ledger = ledger
    storage._ledger_revision = 0

    storage.refresh_lifetime_economy_aggregates()

    ledger.rollback_all()
    ledger.close()


def test_schema27_legacy_claim_paths_reconcile_combined_mastery_spend(
    tmp_path,
) -> None:
    state = GardenState(stored_growth_units=5_000_000)
    state.stored_growth_opening_balance_units = 5_000_000
    ledger = RewardLedger(tmp_path / "legacy-claims.sqlite3")
    GardenStorage._initialize_schema27_migration_metadata(ledger, state)
    for event in (
        EconomyEventRecord(
            "legacy:landmark-funding",
            "landmark_contribute",
            sink_id="mossy_stone_path",
            growth_flow_kind="manual_contribution",
            stored_growth_balance_delta_units=-2_500_000,
            growth_contributed_to_landmarks_units=2_500_000,
            metric_deltas={
                "project_allocations": {
                    "landmark:garden_landmark": 2_500_000
                }
            },
        ),
        EconomyEventRecord(
            "legacy:landmark-claim",
            "landmark_complete",
            sink_id="mossy_stone_path",
            coins_spent=250,
            growth_flow_kind="claim",
            item_id="mossy_stone_path",
            quantity=1,
        ),
        EconomyEventRecord(
            "legacy:mastery-purchase",
            "mastery_purchase",
            sink_id="bonsai:bronze",
            coins_spent=50,
            growth_flow_kind="manual_contribution",
            stored_growth_balance_delta_units=-2_500_000,
            growth_contributed_to_mastery_units=2_500_000,
            item_id="bronze",
            quantity=1,
            metric_deltas={
                "project_allocations": {"mastery:bonsai": 2_500_000}
            },
        ),
    ):
        ledger.stage_economy_event(event)
    state.stored_growth_balance_units = 0
    state.garden_project.landmark_growth_units_funded = 2_500_000
    state.garden_project.landmark_highest_claimed_tier = 1
    state.cultivation_mastery.growth_units_funded_by_species = {
        "bonsai": 2_500_000
    }
    state.cultivation_mastery.highest_claimed_rank_by_species = {
        "bonsai": "bronze"
    }
    storage = GardenStorage.__new__(GardenStorage)
    storage.state = state
    storage._reward_ledger = ledger
    storage._ledger_revision = 0

    storage.refresh_lifetime_economy_aggregates()

    ledger.rollback_all()
    ledger.close()


@pytest.mark.parametrize("source", ["sqlite", "json"])
def test_equipment_upgrade_preserves_display_progress_and_earned_state(tmp_path, source) -> None:
    state = GardenState()
    state.inventory["garden_features"].extend(["wind_chime", "watering_station"])
    state.inventory["scenery"].extend(["spring", "summer"])
    state.loadout.display_decoration_id = "wind_chime"
    state.loadout.display_scenery_id = "spring"
    state.loadout.visibility["garden_feature"] = False
    state.wind_chime_progress = 9
    state.prism_pending_growth_units = 3_700
    database = tmp_path / ("garden_state.sqlite3" if source == "sqlite" else "original.sqlite3")
    ledger = RewardLedger(database)
    GardenStorage._initialize_schema27_migration_metadata(ledger, state)
    # These values have advanced since the earlier migration's opening record.
    state.currency_balance = 543
    payload = state.to_dict()
    payload["version"] = 27
    payload["loadout"]["active_garden_bonus_id"] = "watering_station"
    payload["loadout"]["active_scenery_effect_id"] = "summer"
    payload["daily_loadout"] = {
        "pending_garden_feature_id": "watering_station",
        "queued_scenery_id": "summer", "queued_for_day": "2099-01-01",
    }
    if source == "sqlite":
        for key in UNBOUNDED_STATE_AUTHORITY_KEYS:
            payload.pop(key, None)
        ledger.commit_state(payload, schema_version=27, expected_revision=0)
    else:
        (tmp_path / "garden_state.json").write_text(json.dumps(payload), "utf-8")
    ledger.close()
    storage = GardenStorage.__new__(GardenStorage)
    storage.user_files_dir = tmp_path
    storage.database_path = tmp_path / "garden_state.sqlite3"
    storage.data_path = tmp_path / "garden_state.json"
    storage._reward_ledger = None
    storage._ledger_revision = 0

    restored = storage._load_authoritative_state()

    assert restored.to_dict() == state.to_dict()
    assert restored.loadout.active_garden_bonus_id == "wind_chime"
    assert restored.loadout.active_scenery_effect_id == "spring"
    assert "daily_loadout" not in restored.to_dict()
    assert tuple(tmp_path.glob("garden_state.schema-27.legacy*"))
    storage._reward_ledger.close()


def test_schema27_reload_fails_closed_on_unbacked_endgame_state(tmp_path) -> None:
    database = tmp_path / "garden_state.sqlite3"
    state = GardenState()
    ledger = RewardLedger(database)
    GardenStorage._initialize_schema27_migration_metadata(ledger, state)
    state.garden_project.landmark_growth_units_funded = 1
    ledger.commit_state(
        GardenStorage._bounded_state_payload(state),
        schema_version=STATE_VERSION,
        expected_revision=0,
    )
    ledger.close()
    storage = GardenStorage.__new__(GardenStorage)
    storage.user_files_dir = tmp_path
    storage.database_path = database
    storage.data_path = tmp_path / "garden_state.json"
    storage._reward_ledger = None
    storage._ledger_revision = 0

    with pytest.raises(StatePreservationError, match="preserved an unreadable"):
        storage._load_authoritative_state()

    assert tuple(tmp_path.glob("garden_state.invalid-*.sqlite3"))
