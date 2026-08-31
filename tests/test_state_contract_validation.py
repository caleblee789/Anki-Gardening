from __future__ import annotations

from copy import deepcopy

from ankigarden.growth import (
    CompletedGrowthChargeRequest,
    GrowthChargeOutcome,
    GrowthChargeStatus,
    StageRewardProjection,
)
from ankigarden.models.state import (
    ActivePlantPeriod,
    Booster,
    CurrencyTransaction,
    DailyStats,
    Fertilizer,
    FeedbackEvent,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    MAX_COLLECTION_PLANTS,
    MAX_BOOSTER_HISTORY,
    MAX_FERTILIZER_HISTORY,
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
    PlantMemory,
    RewardDrop,
    STATE_VERSION,
)


def base_payload() -> dict:
    return GardenState().to_dict()


def test_schema_mismatch_is_a_deliberate_fresh_reset():
    payload = base_payload()
    payload["version"] = STATE_VERSION - 1
    payload["total_reviews"] = 9_999

    state = GardenState.from_dict(payload)

    assert state.version == STATE_VERSION
    assert state.total_reviews == 0
    assert state.plants == []


def test_numeric_fields_are_clamped_and_growth_total_is_recomputed():
    payload = base_payload()
    payload.update({"streak_days": -1, "currency_balance": -20})
    payload["daily_stats"].update({
        "reviewed": 2,
        "correct": 9,
        "wrong": 8,
        "base_growth": 20,
        "streak_bonus_growth": 1,
        "fertilizer_growth": 2,
        "bonus_growth": 999,
        "growth_earned": 999,
        "plant_nurtured_growth": {"p": 23},
    })

    state = GardenState.from_dict(payload)

    assert state.streak_days == 0
    assert state.currency_balance == 0
    assert state.daily_stats.correct == 2
    assert state.daily_stats.wrong == 0
    assert state.daily_stats.bonus_growth == 3
    assert state.daily_stats.growth_earned == 23


def test_schema21_growth_allocations_residual_and_charge_replay_round_trip():
    outcome = GrowthChargeOutcome(
        status=GrowthChargeStatus.SUCCESS,
        charge_id="growth_charge_small",
        charge_name="Small Growth Charge",
        target_id="p",
        target_name="Moss",
        previous_growth=490,
        resulting_growth=590,
        growth_granted=100,
        previous_stage="seed",
        resulting_stage="sprout",
        completed_stages=("sprout",),
        rewards=(StageRewardProjection("sprout", 5),),
        inventory_remaining=1,
        message="Small Growth Charge gave Moss 100 Growth.",
    )
    record = CompletedGrowthChargeRequest(
        request_id="00000000-0000-4000-8000-000000000001",
        request_fingerprint="1" * 64,
        outcome=outcome,
        occurred_at="2026-08-17T12:00:00+00:00",
    )
    state = GardenState(
        plants=[Plant(
            "p", "bonsai", "Moss", 0,
            growth_points=590,
            passive_growth_remainder_fifths=3,
        )],
        daily_stats=DailyStats(
            base_growth=10,
            streak_bonus_growth=1,
            plant_nurtured_growth={"p": 11},
            plant_passive_growth_fifths={"other": 11},
            plant_passive_growth_credited={"other": 2},
            plant_charge_growth={"p": 100},
        ),
        completed_growth_charge_requests=[record],
    )
    state.daily_stats.reconcile_growth_totals()

    restored = GardenState.from_dict(state.to_dict())

    assert restored.version == STATE_VERSION
    assert restored.plants[0].passive_growth_remainder_fifths == 3
    assert restored.daily_stats.study_growth_generated == 11
    assert restored.daily_stats.plant_growth == {"other": 2, "p": 111}
    assert restored.daily_stats.growth_earned == 113
    assert restored.completed_growth_charge_requests == [record]


def test_schema21_malformed_passive_residual_and_charge_ledger_fail_closed():
    payload = base_payload()
    payload["plants"] = [{
        "plant_id": "p",
        "species": "bonsai",
        "name": "Moss",
        "slot_index": 0,
        "passive_growth_remainder_fifths": 99,
    }]
    payload["completed_growth_charge_requests"] = [{
        "request_id": "not-a-uuid",
        "request_fingerprint": "x",
        "outcome": {},
        "occurred_at": "not-a-time",
    }]
    payload["daily_stats"]["plant_passive_growth_fifths"] = {"p": -5, "bad": "7"}

    restored = GardenState.from_dict(payload)

    assert restored.plants[0].passive_growth_remainder_fifths == 4
    assert restored.completed_growth_charge_requests == []
    assert restored.daily_stats.plant_passive_growth_fifths == {"p": 0}


def test_collection_repair_deduplicates_species_ids_and_slots():
    payload = base_payload()
    payload["unlocked_slots"] = 2
    payload["plants"] = [
        {"plant_id": "same", "species": "rose", "name": " Rose ", "slot_index": 0},
        {"plant_id": "same", "species": "lavender", "name": "Lavender", "slot_index": 0},
        {"plant_id": "third", "species": "rose", "name": "Duplicate", "slot_index": 1},
        {"plant_id": "bad", "species": "money_tree", "name": "Bad", "slot_index": 1},
    ]

    state = GardenState.from_dict(payload)

    assert [plant.species for plant in state.plants] == ["rose", "lavender"]
    assert len({plant.plant_id for plant in state.plants}) == 2
    assert state.plants[0].slot_index == 0
    assert state.plants[1].slot_index is None


def test_growth_is_capped_at_rare_and_stage_names_are_unchanged():
    payload = base_payload()
    payload["plants"] = [{
        "plant_id": "p", "species": "bonsai", "name": "Moss", "slot_index": 0,
        "growth_points": 999_999,
    }]

    plant = GardenState.from_dict(payload).plants[0]

    assert GROWTH_STAGES == ["seed", "sprout", "young", "mature", "flowering", "rare"]
    assert GROWTH_THRESHOLDS == [0, 400, 2_000, 6_000, 15_000, 35_000]
    assert plant.growth_points == 35_000
    assert plant.growth_stage == "rare"


def test_fertilizer_growth_is_derived_from_tier_not_untrusted_payload():
    payload = base_payload()
    payload["plants"] = [{
        "plant_id": "p", "species": "hydrangea", "name": "Misty", "slot_index": 0,
        "fertilizer": {"tier": "quality", "bonus": 99, "expires_at": 2_000_000_000},
    }]

    plant = GardenState.from_dict(payload).plants[0]

    assert plant.fertilizer == Fertilizer(
        "quality", 2, 2_000_000_000, 2_000_000_000
    )
    assert not plant.fertilizer.active(1_999_999_999)


def test_invalid_or_expired_shape_fertilizer_is_safe():
    payload = base_payload()
    payload["plants"] = [{
        "plant_id": "p", "species": "hydrangea", "name": "Misty", "slot_index": 0,
        "fertilizer": {"tier": "miracle", "bonus": 99, "expires_at": "soon"},
    }]
    assert GardenState.from_dict(payload).plants[0].fertilizer is None


def test_fertilizer_history_is_validated_derived_deduplicated_and_durable():
    payload = base_payload()
    payload["plants"] = [{
        "plant_id": "p", "species": "hydrangea", "name": "Misty", "slot_index": 0,
        "fertilizer_history": [
            {
                "tier": "basic",
                "growth_per_answer": 99,
                "started_at": float(index * 2 + 1),
                "expires_at": float(index * 2 + 2),
            }
            for index in range(MAX_FERTILIZER_HISTORY + 2)
        ] + [
            {"tier": "miracle", "started_at": 1.0, "expires_at": 2.0},
            {"tier": "premium", "started_at": 10.0, "expires_at": 10.0},
        ],
    }]

    plant = GardenState.from_dict(payload).plants[0]
    restored = GardenState.from_dict(GardenState.from_dict(payload).to_dict()).plants[0]

    assert len(plant.fertilizer_history) == MAX_FERTILIZER_HISTORY + 2
    assert plant.fertilizer_history[0] == Fertilizer("basic", 1, 2.0, 1.0)
    assert plant.fertilizer_history[-1] == Fertilizer(
        "basic", 1, float((MAX_FERTILIZER_HISTORY + 1) * 2 + 2),
        float((MAX_FERTILIZER_HISTORY + 1) * 2 + 1),
    )
    assert restored.fertilizer_history == plant.fertilizer_history


def test_current_day_revlog_ledger_is_validated_sorted_and_floor_bounded():
    payload = base_payload()
    payload["last_processed_revlog_id"] = 200
    payload["processed_revlog_floor"] = 100
    payload["processed_revlog_ids"] = [200, 150, 200, 99, True, "175"]
    payload["revlog_ledger_migration_pending"] = True

    state = GardenState.from_dict(payload)
    restored = GardenState.from_dict(state.to_dict())

    assert state.processed_revlog_floor == 100
    assert state.processed_revlog_ids == [150, 200]
    assert state.revlog_ledger_migration_pending
    assert restored.processed_revlog_ids == [150, 200]


def test_active_plant_must_be_planted_and_unfinished():
    payload = base_payload()
    payload["plants"] = [
        {"plant_id": "shelved", "species": "peony", "name": "Pearl", "slot_index": None},
        {"plant_id": "rare", "species": "rose", "name": "Briar", "slot_index": 0, "growth_points": 35_000},
    ]
    payload["active_plant_id"] = "shelved"
    assert GardenState.from_dict(payload).active_plant_id is None
    payload["active_plant_id"] = "rare"
    assert GardenState.from_dict(payload).active_plant_id is None


def test_removed_parallel_progression_fields_are_not_serialized():
    payload = base_payload()
    payload.update({
        "activity_history": [{"day": "2026-08-07", "reviewed": 50}],
        "active_review_goal": 150,
        "pending_review_goal": 50,
        "pending_goal_effective_day": "2026-08-09",
    })
    restored = GardenState.from_dict(payload)
    serialized = restored.to_dict()
    assert "activity_history" not in serialized
    assert "active_review_goal" not in serialized
    assert "pending_review_goal" not in serialized
    assert "pending_goal_effective_day" not in serialized


def test_activity_currency_feedback_and_periods_round_trip():
    state = GardenState(
        plants=[Plant("p", "wisteria", "Wisp", 0)],
        active_plant_id="p",
        currency_balance=15,
        currency_transactions=[CurrencyTransaction(
            "tx1", "all-due:2026-08-08", "All due cards finished", 15, 15,
            "2026-08-08T12:00:00+00:00",
        )],
        pending_feedback=[FeedbackEvent(
            "all-due:2026-08-08", "currency", "All due cards finished · +10 Garden Currency",
            "2026-08-08T12:00:00+00:00", "p",
        )],
        active_plant_periods=[ActivePlantPeriod("2026-08-08", "p", 123)],
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.currency_transactions[0].reason == "All due cards finished"
    assert restored.pending_feedback[0].plant_id == "p"
    assert restored.active_plant_periods[0].started_at_ms == 123


def test_transaction_ledger_balances_are_repaired_against_final_balance():
    payload = base_payload()
    payload["currency_balance"] = 20
    payload["currency_transactions"] = [
        {
            "transaction_id": "tx1",
            "event_key": "earned",
            "reason": "Earned reward",
            "delta": 50,
            "balance": 999,
            "occurred_at": "2026-08-08T10:00:00+00:00",
        },
        {
            "transaction_id": "tx2",
            "event_key": "spent",
            "reason": "Bought item",
            "delta": -30,
            "balance": 999,
            "occurred_at": "2026-08-08T11:00:00+00:00",
        },
    ]

    state = GardenState.from_dict(payload)

    assert [tx.balance for tx in state.currency_transactions] == [50, 20]
    assert state.currency_transactions[-1].balance == state.currency_balance


def test_impossible_transaction_ledger_is_discarded_without_changing_balance():
    payload = base_payload()
    payload["currency_balance"] = 0
    payload["currency_transactions"] = [{
        "transaction_id": "tx1",
        "event_key": "impossible",
        "reason": "Impossible reward",
        "delta": 10,
        "balance": 10,
        "occurred_at": "2026-08-08T10:00:00+00:00",
    }]

    state = GardenState.from_dict(payload)

    assert state.currency_balance == 0
    assert state.currency_transactions == []


def test_bounded_feedback_and_coalesced_timelines_survive_round_trips():
    state = GardenState(
        pending_feedback=[
            FeedbackEvent(f"e{index}", "test", f"Message {index}", "2026-08-08T12:00:00+00:00")
            for index in range(130)
        ],
        active_plant_periods=[ActivePlantPeriod("2026-08-08", None, index) for index in range(80)],
    )

    for _ in range(20):
        state = GardenState.from_dict(state.to_dict())

    assert len(state.pending_feedback) == 100
    assert state.active_plant_periods == [
        ActivePlantPeriod("2026-08-08", None, 0)
    ]
    assert state.pending_feedback[0].event_id == "e30"


def test_plant_memories_names_and_shelved_slot_round_trip():
    state = GardenState(plants=[Plant(
        "p", "japanese_maple", "  Ember   Maple  ", None, growth_points=2_500,
        memories=[PlantMemory("stage:young", "stage", "2026-08-08", new_stage="young")],
    )])

    restored = GardenState.from_dict(state.to_dict())

    assert restored.plants[0].name == "Ember Maple"
    assert restored.plants[0].slot_index is None
    assert restored.plants[0].memories[0].new_stage == "young"


def test_blank_generated_names_repair_to_species_plant_and_garden_name_is_normalized():
    payload = base_payload()
    payload["garden_name"] = "  Moss   & Moon  "
    payload["plants"] = [{
        "plant_id": "p",
        "species": "japanese_maple",
        "name": "   ",
        "slot_index": 0,
    }]

    state = GardenState.from_dict(payload)

    assert state.garden_name == "Moss & Moon"
    assert state.plants[0].name == "Japanese Maple Plant"
    assert state.plants[0].name_customized is False


def test_booster_reward_and_rich_feedback_metadata_round_trip_safely():
    state = GardenState(
        plants=[Plant(
            "p", "bonsai", "Bonsai Plant", 0,
            booster=Booster(5, 8_200.0, 1_000.0),
            booster_history=[Booster(5, 900.0, 100.0)],
        )],
        consumables={"booster_potion": 3},
        reward_drop_history=[RewardDrop(
            123, "2026-08-08", "booster_potion", 1,
            "2026-08-08T12:00:00+00:00",
        )],
        pending_feedback=[FeedbackEvent(
            "drop:123", "booster_drop", "A rare gift.",
            "2026-08-08T12:00:00+00:00", "p",
            "A gift from Bonsai Plant", "ui", "booster_potion", 1,
        )],
    )

    restored = GardenState.from_dict(state.to_dict())

    assert restored.plants[0].booster == Booster(5, 8_200.0, 1_000.0)
    assert restored.plants[0].booster_history == [Booster(5, 900.0, 100.0)]
    assert restored.consumables == {
        "booster_potion": 3,
        "fertilizer_basic": 0,
        "fertilizer_quality": 0,
        "fertilizer_premium": 0,
        "growth_charge_small": 0,
        "growth_charge_standard": 0,
        "growth_charge_grand": 0,
    }
    assert restored.reward_drop_history == state.reward_drop_history
    assert restored.pending_feedback[0].asset_key == "booster_potion"
    assert restored.pending_feedback[0].amount == 1


def test_booster_history_is_deduplicated_and_durable():
    payload = base_payload()
    history = [
        {"growth_per_answer": 5, "started_at": index * 2 + 1, "expires_at": index * 2 + 2}
        for index in range(MAX_BOOSTER_HISTORY + 5)
    ]
    history.append(history[-1].copy())
    payload["plants"] = [{
        "plant_id": "p", "species": "bonsai", "name": "Bonsai Plant",
        "slot_index": 0, "booster_history": history,
    }]

    restored = GardenState.from_dict(payload)

    assert len(restored.plants[0].booster_history) == MAX_BOOSTER_HISTORY + 5
    assert len({
        (item.started_at, item.expires_at)
        for item in restored.plants[0].booster_history
    }) == MAX_BOOSTER_HISTORY + 5


def test_current_and_historical_species_are_retained_while_unknown_rows_are_skipped():
    species = list(PLANT_SPECIES_ORDER)
    payload = base_payload()
    payload["unlocked_species"] = [*species, "money_tree"]
    payload["plants"] = [
        {"plant_id": "invalid", "species": "money_tree", "name": "Invalid", "slot_index": 0},
    ] + [
        {"plant_id": f"p{index}", "species": item, "name": item.title(), "slot_index": index if index < 6 else None}
        for index, item in enumerate(species)
    ] + [{"plant_id": "extra", "species": "rose", "name": "Extra", "slot_index": None}]

    state = GardenState.from_dict(payload)

    assert PLANT_SPECIES == frozenset(species)
    assert MAX_COLLECTION_PLANTS == len(species)
    assert len(state.plants) == len(species)
    assert {plant.species for plant in state.plants} == PLANT_SPECIES
    assert state.unlocked_species == species


def test_serializer_omits_removed_parallel_progression_systems():
    payload = GardenState().to_dict()
    for key in (
        "daily_quests", "quest_history", "pending_milestone_reward", "rare_variant",
        "vitality", "focus_plant_id", "retrospective_last_revlog_id", "imported_history_days",
        "currency", "exam_mode", "deck_plant_map",
    ):
        assert key not in payload


def test_claimed_streak_rewards_keep_only_supported_once_ever_milestones():
    payload = base_payload()
    payload["claimed_streak_rewards"] = [7, 7, 14, 15, 30, 100, True, "7"]

    state = GardenState.from_dict(payload)

    assert state.claimed_streak_rewards == [7, 14, 30, 100]


def test_to_dict_returns_a_detached_payload():
    state = GardenState(plants=[Plant("p", "rose", "Briar", 0)])
    payload = state.to_dict()
    changed = deepcopy(payload)
    changed["plants"][0]["name"] = "Changed"
    assert state.plants[0].name == "Briar"
