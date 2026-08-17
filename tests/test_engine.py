from __future__ import annotations

import math
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine, difficulty_from_factor, queue_and_lapse_from_revlog_type
from ankigarden.models.state import (
    ActivePlantPeriod,
    CURRENT_CATALOG_SPECIES_ORDER,
    DailyStats,
    Booster,
    Fertilizer,
    FeedbackEvent,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    HISTORICAL_PLANT_SPECIES_ORDER,
    CURRENT_CATALOG_SPECIES_ORDER,
    MAX_FERTILIZER_HISTORY,
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
)
from ankigarden.storage import DueObligationStatus, GardenStorage, SchedulerBoundaryError


class FakeConfig:
    def __init__(self, **overrides):
        self.data = {**DEFAULT_CONFIG, **overrides}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def nested(self, *keys, default=None):
        node = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class FakeStorage:
    def __init__(self, *, goal: int = 50):
        self.day = "2026-08-08"
        self.day_start_ms = 1_786_100_000_000
        self.now_ms = 1_786_150_000_000
        p1 = Plant("p1", "bonsai", "Moss", 0)
        p2 = Plant("p2", "rose", "Briar", 1)
        self.state = GardenState(
            plants=[p1, p2],
            active_plant_id="p1",
            daily_stats=DailyStats(day=self.day),
            last_active_day="2026-08-06",
            active_plant_periods=[ActivePlantPeriod(self.day, "p1", self.now_ms - 10_000)],
        )
        self.addon_dir = Path("ankigarden")
        self.assets_root = self.addon_dir / "assets"
        self.save_count = 0
        self.fail_save = False
        self.due_status = DueObligationStatus()

    def save(self):
        self.save_count += 1
        if self.fail_save:
            raise OSError("disk full")

    def current_scheduler_day(self):
        return self.day

    def current_day_start_ms(self):
        return self.day_start_ms

    def current_time_ms(self):
        return self.now_ms

    def due_obligations(self):
        return self.due_status

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _data):
        return None


def make_engine(*, goal: int = 50):
    storage = FakeStorage(goal=goal)
    engine = GardenGameEngine(FakeConfig(), storage)
    # Economy tests exercise purchase mechanics independently from the bundled
    # manifest's intentionally incremental V6 catalog rollout.
    engine.assets.release_ready_plant_species = lambda **_kwargs: tuple(engine.SPECIES_PRICES)
    return engine, storage


def answer(engine: GardenGameEngine, storage: FakeStorage, *, ease: int = 3, revlog_id: int = 0):
    storage.now_ms += 1_000
    stable_id = revlog_id or storage.now_ms
    return engine.register_review({
        "queue": 2,
        "ease": ease,
        "lapse_count": int(ease == 1),
        "revlog_id": stable_id,
        "answered_at_ms": stable_id,
    })


def test_review_semantics_helpers_remain_stable():
    assert difficulty_from_factor(0) == difficulty_from_factor(None) == 0.25
    assert difficulty_from_factor(1000) == 1.0
    assert queue_and_lapse_from_revlog_type(0, 3) == (1, 0)
    assert queue_and_lapse_from_revlog_type(2, 1) == (1, 1)
    assert queue_and_lapse_from_revlog_type(4, 3) is None


def test_engine_startup_preserves_saved_day_until_scheduler_boundary_is_available():
    storage = FakeStorage()
    storage.state.daily_stats.day = "2026-03-07"
    storage.current_scheduler_day = lambda: (_ for _ in ()).throw(
        SchedulerBoundaryError("collection scheduler is not ready")
    )

    engine = GardenGameEngine(FakeConfig(), storage)

    assert engine.state.daily_stats.day == "2026-03-07"


def test_new_scheduler_day_floor_ignores_future_scalar_cursor_and_counts_answer():
    engine, storage = make_engine()
    future_cursor = 9_999_999_999_999
    storage.state.last_processed_revlog_id = future_cursor
    storage.state.processed_revlog_floor = storage.day_start_ms - 1
    storage.state.processed_revlog_ids = [storage.day_start_ms + 10]
    storage.day = "2026-08-09"
    storage.day_start_ms += 86_400_000
    answer_id = storage.day_start_ms + 1

    engine.rollover_if_needed()
    gained = engine.apply_same_day_reviews(
        [{"queue": 2, "ease": 3, "revlog_id": answer_id, "answered_at_ms": answer_id}],
        latest_revlog_id=answer_id,
    )

    assert storage.state.processed_revlog_floor == storage.day_start_ms - 1
    assert storage.state.processed_revlog_ids == [answer_id]
    assert storage.state.last_processed_revlog_id == future_cursor
    assert gained == 10


def test_scheduler_rollover_clears_migration_stale_growth_accounting():
    engine, storage = make_engine()
    storage.state.daily_stats.growth_accounting_stale = True
    storage.state.daily_stats.legacy_unattributed_growth = 37
    storage.state.daily_stats.legacy_plant_growth = {"p1": 37}
    storage.state.daily_stats.reconcile_growth_totals()
    storage.day = "2026-08-09"
    storage.day_start_ms += 86_400_000

    engine.rollover_if_needed()

    assert storage.state.daily_stats.day == "2026-08-09"
    assert not storage.state.daily_stats.growth_accounting_stale
    assert storage.state.daily_stats.legacy_unattributed_growth == 0
    assert storage.state.daily_stats.legacy_plant_growth == {}


def test_progress_export_reports_growth_reconciliation_without_mutation():
    engine, storage = make_engine()
    storage.state.daily_stats.reviewed = 1
    storage.state.selected_weather = "breeze"
    answer(engine, storage)
    before = storage.state.to_dict()

    report = json.loads(engine.export_progress_summary())

    assert report["schema_version"] == 20
    assert report["growth_reconciliation"]["study_source_total"] == 11
    assert report["growth_reconciliation"]["study_growth_generated"] == 11
    assert report["growth_reconciliation"]["nurtured_by_plant"] == {"p1": 11}
    assert report["growth_reconciliation"]["passive_exact_fifths_by_plant"] == {
        "p2": 11,
    }
    assert report["plants"][1]["passive_growth_remainder_fifths"] == 1
    assert report["growth_charge_replay_ledger"]["healthy"] is True
    assert storage.state.to_dict() == before


def test_catalog_price_name_and_personality_tables_match_exact_species_contract():
    expected_prices = {
        "bonsai": 100,
        "rose": 100,
        "sunflower": 150,
        "lavender": 200,
        "hydrangea": 250,
        "peony": 300,
        "foxglove": 350,
        "japanese_maple": 400,
        "wisteria": 500,
        "dahlia": 600,
    }

    assert tuple(expected_prices) == CURRENT_CATALOG_SPECIES_ORDER
    assert GardenGameEngine.SPECIES_PRICES == expected_prices
    assert set(GardenGameEngine.SPECIES_NAMES) == set(CURRENT_CATALOG_SPECIES_ORDER)
    assert set(GardenGameEngine.SPECIES_PERSONALITY) == set(CURRENT_CATALOG_SPECIES_ORDER)
    assert PLANT_SPECIES == frozenset(PLANT_SPECIES_ORDER)
    assert set(CURRENT_CATALOG_SPECIES_ORDER).issubset(PLANT_SPECIES)
    assert set(HISTORICAL_PLANT_SPECIES_ORDER).issubset(PLANT_SPECIES)


def test_multiword_species_uses_learner_facing_label_in_messages():
    engine, _storage = make_engine()

    ok, message, _plant = engine.purchase_species("japanese_maple")

    assert not ok
    assert message == (
        "You need 400 more Garden Coins to purchase Japanese Maple Seed."
    )


@pytest.mark.parametrize("queue", [0, 1, 3, 2], ids=["new", "learning", "relearning", "review"])
@pytest.mark.parametrize("ease", [1, 2, 3, 4], ids=["again", "hard", "good", "easy"])
def test_all_answer_ratings_and_scheduler_queues_count_once(queue, ease):
    engine, storage = make_engine(goal=5_000)
    storage.now_ms += 1_000

    award = engine.register_review({
        "queue": queue,
        "ease": ease,
        "lapse_count": int(queue == 3 or ease == 1),
        "revlog_id": storage.now_ms,
        "answered_at_ms": storage.now_ms,
    })

    stats = storage.state.daily_stats
    assert stats.reviewed == storage.state.total_reviews == 1
    assert award.base_growth == 10
    assert (stats.wrong, stats.correct) == ((1, 0) if ease == 1 else (0, 1))
    assert stats.new_count == int(queue == 0)
    assert stats.learning_count == int(queue in (1, 3))
    assert stats.review_count == int(queue == 2)
    assert stats.recovered_lapses == int(queue == 3 and ease > 1)


def test_duplicate_live_revlog_row_is_ignored_completely():
    engine, storage = make_engine(goal=5_000)
    revlog_id = storage.now_ms + 1_000

    first = engine.register_review({"queue": 2, "ease": 3, "revlog_id": revlog_id})
    snapshot = storage.state.to_dict()
    duplicate = engine.register_review({"queue": 2, "ease": 1, "revlog_id": revlog_id})

    assert first.total_growth >= 10
    assert duplicate.total_growth == 0
    assert "already counted" in duplicate.paused_reason
    assert storage.state.to_dict() == snapshot


def test_day_one_answers_award_base_growth_without_a_streak_bonus():
    engine, storage = make_engine()

    first = answer(engine, storage)
    second = answer(engine, storage)

    assert first.base_growth == second.base_growth == 10
    assert first.bonus_percent == second.bonus_percent == 0
    assert first.bonus_growth == 0
    assert second.bonus_growth == 0
    assert storage.state.plants[0].growth_points == 20
    assert storage.state.daily_stats.base_growth == 20
    assert storage.state.daily_stats.bonus_growth == 0


@pytest.mark.parametrize(
    ("streak_days", "expected_bonus"),
    [
        (0, 0), (1, 0), (6, 0), (7, 5), (13, 5),
        (14, 10), (29, 10), (30, 15), (99, 15),
        (100, 20), (364, 20), (365, 25),
    ],
)
def test_streak_bonus_tiers_are_exact(streak_days, expected_bonus):
    assert GardenGameEngine.streak_bonus_percent(streak_days) == expected_bonus


def test_retrospective_streak_grants_each_historical_coin_milestone_once():
    engine, storage = make_engine()
    storage.state.streak_days = 0
    storage.state.currency_balance = 0
    storage.state.claimed_streak_rewards = []
    storage.retrospective_streak = lambda: SimpleNamespace(
        days=100,
        latest_day=storage.day,
        studied_today=True,
    )

    first = engine.reconcile_retrospective_streak()
    balance_after_first = storage.state.currency_balance
    second = engine.reconcile_retrospective_streak()

    assert first[0] and second[0]
    assert storage.state.streak_days == 100
    assert balance_after_first == storage.state.currency_balance == 475
    assert storage.state.claimed_streak_rewards == [7, 14, 30, 100]
    assert [tx.event_key for tx in storage.state.currency_transactions] == [
        "streak:7", "streak:14", "streak:30", "streak:100",
    ]
    restored = [
        event for event in storage.state.pending_feedback
        if event.event_id.startswith("streak-backfill:")
    ]
    assert len(restored) == 1
    assert restored[0].amount == 475


def test_retrospective_streak_read_failure_preserves_saved_state():
    engine, storage = make_engine()
    storage.state.streak_days = 30
    storage.state.currency_balance = 125
    before = storage.state.to_dict()

    def unavailable():
        raise SchedulerBoundaryError("scheduler not ready")

    storage.retrospective_streak = unavailable
    ok, message = engine.reconcile_retrospective_streak()

    assert not ok
    assert "not available" in message
    assert storage.state.to_dict() == before


def test_missed_day_resets_streak_before_awarding_growth():
    engine, storage = make_engine()
    storage.state.streak_days = 10
    award = answer(engine, storage)

    assert storage.state.streak_days == 1
    assert engine.current_streak_bonus_percent() == 0
    assert award.base_growth == 10
    assert award.bonus_growth == 0


def test_streak_growth_bonus_is_fractional_and_never_reduces_base():
    engine, storage = make_engine()
    storage.state.streak_days = 7
    storage.state.last_active_day = "2026-08-07"

    first = answer(engine, storage)
    second = answer(engine, storage)

    assert first.bonus_percent == second.bonus_percent == 5
    assert first.base_growth == second.base_growth == 10
    assert first.streak_bonus_growth == 0
    assert second.streak_bonus_growth == 1
    assert storage.state.plants[0].growth_points == 21


def test_growth_routes_full_to_active_and_passive_to_other_planted_plants():
    engine, storage = make_engine()
    answer(engine, storage)
    before = storage.state.plants[0].growth_points

    ok, _message = engine.set_active_plant("p2")
    assert ok
    answer(engine, storage)

    assert storage.state.plants[0].growth_points == before + 2
    assert storage.state.plants[1].growth_points > 0
    assert storage.state.daily_stats.plant_growth.keys() == {"p1", "p2"}


def test_same_day_events_route_by_active_period_timestamp():
    engine, storage = make_engine()
    switch_at = storage.now_ms + 5_000
    storage.now_ms = switch_at
    assert engine.set_active_plant("p2")[0]
    rows = [
        {"queue": 2, "ease": 3, "revlog_id": switch_at - 1, "answered_at_ms": switch_at - 1},
        {"queue": 2, "ease": 3, "revlog_id": switch_at + 1, "answered_at_ms": switch_at + 1},
    ]

    gained = engine.apply_same_day_reviews(rows, latest_revlog_id=switch_at + 1)

    assert gained >= 20
    assert storage.state.daily_stats.plant_growth.keys() == {"p1", "p2"}
    assert engine.apply_same_day_reviews(rows, latest_revlog_id=switch_at + 1) == 0


def test_stage_thresholds_and_stage_local_progress_are_exact():
    assert GROWTH_STAGES == ["seed", "sprout", "young", "mature", "flowering", "rare"]
    assert GROWTH_THRESHOLDS == [0, 500, 2_500, 8_000, 20_000, 50_000]
    plant = Plant("p", "lavender", "Violet", 0, growth_points=7_999)
    assert plant.growth_stage == "young"
    plant.growth_points = 8_000
    assert plant.growth_stage == "mature"


def test_growth_milestones_stage_reward_and_transition_are_durable():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 490

    answer(engine, storage)

    assert plant.growth_stage == "sprout"
    assert engine.peek_stage_transitions()[0].new_stage == "sprout"
    assert engine.peek_stage_transitions()[0].source == "nurtured"
    assert storage.state.currency_balance == 5
    assert any(tx.reason == "Moss reached Sprout" for tx in storage.state.currency_transactions)
    assert any(memory.memory_id == "stage:sprout" for memory in plant.memories)
    assert any(
        event.message == "Moss reached Sprout and earned 5 Garden Coins."
        for event in engine.peek_feedback()
    )


def test_streak_reward_feedback_reads_as_a_sentence() -> None:
    engine, storage = make_engine()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.streak_days == 7
    assert any(
        event.message == "Your 7-day Anki streak earned 25 Garden Coins."
        for event in engine.peek_feedback()
    )


def test_twenty_five_fifty_and_seventy_five_percent_feedback_uses_stage_interval():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 119
    answer(engine, storage)
    assert any("25%" in event.message for event in engine.peek_feedback())
    plant.growth_points = 249
    answer(engine, storage)
    assert any("50%" in event.message for event in engine.peek_feedback())
    plant.growth_points = 369
    answer(engine, storage)
    assert any("75%" in event.message for event in engine.peek_feedback())


def test_rare_stage_caps_growth_pauses_and_does_not_overflow():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 49_995

    award = answer(engine, storage)
    paused = answer(engine, storage)

    assert plant.growth_points == 50_000
    assert award.total_growth == 5
    assert storage.state.active_plant_id is None
    assert paused.total_growth == 0
    assert paused.paused_reason == "Choose an unfinished plant to nurture to resume Growth."


def test_rare_restart_and_geometry_migration_preserve_the_intentional_growth_pause(
    tmp_path,
):
    storage = FakeStorage()
    storage.state.plants[0].growth_points = 50_000
    storage.state.active_plant_id = None
    paused_at_ms = storage.now_ms - 1_000
    storage.state.active_plant_periods = [
        ActivePlantPeriod(storage.day, None, paused_at_ms)
    ]
    storage.state.scene_geometry_version = 5
    # Exercise the saved schema-14 contract, not merely an in-memory null.
    storage.state = GardenState.from_dict(storage.state.to_dict())
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"

    GardenStorage._ensure_defaults(storage)
    engine = GardenGameEngine(FakeConfig(), storage)
    unfinished = storage.state.plants[1]
    before = unfinished.growth_points
    award = answer(engine, storage)

    assert storage.state.scene_geometry_version == 6
    assert storage.state.active_plant_id is None
    assert [(period.plant_id, period.started_at_ms) for period in storage.state.active_plant_periods] == [
        (None, paused_at_ms)
    ]
    assert award.total_growth == 0
    assert unfinished.growth_points == before
    assert award.paused_reason == "Choose an unfinished plant to nurture to resume Growth."


def test_dangling_non_null_saved_active_reference_repairs_deterministically_with_period(
    tmp_path,
):
    storage = FakeStorage()
    payload = storage.state.to_dict()
    payload["active_plant_id"] = "missing-plant"
    payload["active_plant_periods"] = [{
        "day": storage.day,
        "plant_id": "missing-plant",
        "started_at_ms": storage.now_ms - 1_000,
    }]
    payload["scene_geometry_version"] = 5
    storage.state = GardenState.from_dict(payload)
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"

    GardenStorage._ensure_defaults(storage)
    engine = GardenGameEngine(FakeConfig(), storage)

    assert storage.state.active_plant_id == "p1"
    assert [period.plant_id for period in storage.state.active_plant_periods] == [None, "p1"]
    assert storage.state.active_plant_periods[-1] == ActivePlantPeriod(
        storage.day, "p1", storage.now_ms
    )
    assert answer(engine, storage).plant_id == "p1"


@pytest.mark.parametrize(
    ("slot_index", "growth_points"),
    [(None, 0), (1, GROWTH_THRESHOLDS[-1])],
)
def test_saved_non_null_unusable_active_target_repairs_to_a_routable_plant(
    tmp_path,
    slot_index,
    growth_points,
):
    storage = FakeStorage()
    payload = storage.state.to_dict()
    payload["plants"][1]["slot_index"] = slot_index
    payload["plants"][1]["growth_points"] = growth_points
    payload["active_plant_id"] = "p2"
    payload["active_plant_periods"] = [{
        "day": storage.day,
        "plant_id": "p2",
        "started_at_ms": storage.now_ms - 1_000,
    }]
    storage.state = GardenState.from_dict(payload)
    storage.user_files_dir = tmp_path / "user_files"
    storage.cache_dir = storage.user_files_dir / "cache"

    GardenStorage._ensure_defaults(storage)

    assert storage.state.active_plant_id == "p1"
    assert [period.plant_id for period in storage.state.active_plant_periods] == ["p2", "p1"]
    assert storage.state.active_plant_periods[-1].started_at_ms == storage.now_ms


def test_all_due_requires_an_answer_live_zero_obligations_and_is_once_per_day():
    engine, storage = make_engine()
    assert engine.evaluate_all_due(DueObligationStatus()) == (
        False,
        "Answer at least one card before you can earn the reward for finishing all due cards.",
    )
    answer(engine, storage)
    assert not engine.evaluate_all_due(DueObligationStatus(review_count=1))[0]

    ok, message = engine.evaluate_all_due(DueObligationStatus())
    assert ok and message == "You finished all due cards and earned 10 Garden Coins."
    assert storage.state.daily_stats.completed_due_cards
    balance = storage.state.currency_balance
    assert not engine.evaluate_all_due(DueObligationStatus(review_count=9, learning_count=4))[0]
    assert storage.state.daily_stats.completed_due_cards
    assert storage.state.currency_balance == balance


def test_all_due_check_persists_scheduler_rollover_even_when_not_earned():
    engine, storage = make_engine()
    storage.state.daily_stats.reviewed = 1
    storage.day = "2026-08-09"
    storage.now_ms += 86_400_000
    saves_before = storage.save_count

    ok, message = engine.evaluate_all_due(DueObligationStatus(review_count=2))

    assert not ok and "at least one card" in message
    assert storage.state.daily_stats.day == "2026-08-09"
    assert storage.save_count == saves_before + 1


def test_progress_estimates_recalculate_from_the_effective_growth_rate(monkeypatch):
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 500
    assert engine.progress_estimates(plant) == math.ceil((2_500 - 500) / 10)
    monkeypatch.setattr(engine, "_now_seconds", lambda: 1_000.0)
    plant.fertilizer = Fertilizer("quality", 2, 2_000.0, 500.0)
    assert engine.progress_estimates(plant) == math.ceil((2_500 - 500) / 12)


def test_next_review_growth_projection_is_nonmutating_and_matches_the_award():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    storage.state.daily_stats.reviewed = 1
    storage.state.streak_days = 7
    storage.state.selected_weather = "breeze"
    storage.state.selected_background = "spring"
    plant.bonus_remainder = 50
    plant.fertilizer = Fertilizer(
        "quality",
        2,
        storage.now_ms / 1_000 + 3_600,
        storage.now_ms / 1_000 - 60,
    )
    before_state = storage.state.to_dict()
    before_saves = storage.save_count
    next_event_seconds = (storage.now_ms + 1_000) / 1_000

    projected = engine.project_review_growth(plant, now=next_event_seconds)

    assert storage.state.to_dict() == before_state
    assert storage.save_count == before_saves
    awarded = answer(engine, storage)
    assert awarded == projected


def test_fertilizer_is_currency_purchased_time_based_and_plant_specific(monkeypatch):
    engine, storage = make_engine()
    answer(engine, storage)
    storage.state.currency_balance = 200
    monkeypatch.setattr(engine, "_now_seconds", lambda: 1_000.0)

    ok, message = engine.purchase_fertilizer("p1", "quality")
    assert ok
    assert message == "Quality Fertilizer applied to Moss for 2 hours."
    plant = storage.state.plants[0]
    assert plant.fertilizer.tier == "quality"
    assert plant.fertilizer.started_at == 1_000
    assert plant.fertilizer.expires_at == 1_000 + 7_200
    assert storage.state.currency_balance == 135
    assert engine.fertilizer_growth(plant, now=999.999) == 0
    assert engine.fertilizer_growth(plant, now=1_000) == 2
    assert engine.fertilizer_growth(plant, now=1_001) == 2
    assert engine.fertilizer_growth(storage.state.plants[1], now=1_001) == 0
    assert engine.fertilizer_growth(plant, now=9_000) == 0
    assert any(
        event.message
        == "Quality Fertilizer applied to Moss for 2 hours."
        for event in engine.peek_feedback()
    )


def test_same_fertilizer_extends_and_different_tier_requires_confirmation(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    now = [1_000.0]
    monkeypatch.setattr(engine, "_now_seconds", lambda: now[0])
    assert engine.purchase_fertilizer("p1", "basic")[0]
    first_start = storage.state.plants[0].fertilizer.started_at
    first_expiration = storage.state.plants[0].fertilizer.expires_at
    now[0] = 1_100.0
    assert engine.purchase_fertilizer("p1", "basic")[0]
    assert storage.state.plants[0].fertilizer.started_at == first_start
    assert storage.state.plants[0].fertilizer.expires_at == first_expiration + 3_600
    assert not engine.purchase_fertilizer("p1", "premium")[0]
    assert storage.state.plants[0].fertilizer_history == []
    now[0] = 1_200.0
    assert engine.purchase_fertilizer("p1", "premium", replace_active=True)[0]
    assert storage.state.plants[0].fertilizer.started_at == 1_200
    assert storage.state.plants[0].fertilizer_history == [
        Fertilizer("basic", 1, 1_200.0, 1_000.0)
    ]


def test_replaced_fertilizer_keeps_the_prior_tier_for_late_synced_answers(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    now = [1_000.0]
    monkeypatch.setattr(engine, "_now_seconds", lambda: now[0])
    assert engine.purchase_fertilizer("p1", "basic")[0]
    now[0] = 1_200.0
    assert engine.purchase_fertilizer("p1", "premium", replace_active=True)[0]

    plant = storage.state.plants[0]
    assert plant.fertilizer_history == [Fertilizer("basic", 1, 1_200.0, 1_000.0)]
    assert engine.fertilizer_growth(plant, now=999.999) == 0
    assert engine.fertilizer_growth(plant, now=1_100.0) == 1
    assert engine.fertilizer_growth(plant, now=1_200.0) == 3
    assert engine.fertilizer_growth(plant, now=15_600.0) == 0

    gained = engine.apply_same_day_reviews(
        [
            {"queue": 2, "ease": 3, "revlog_id": 999_000, "answered_at_ms": 999_000},
            {"queue": 2, "ease": 3, "revlog_id": 1_100_000, "answered_at_ms": 1_100_000},
            {"queue": 2, "ease": 3, "revlog_id": 1_200_000, "answered_at_ms": 1_200_000},
            {"queue": 2, "ease": 3, "revlog_id": 15_600_000, "answered_at_ms": 15_600_000},
        ],
        latest_revlog_id=15_600_000,
    )

    assert gained == 44
    assert storage.state.daily_stats.base_growth == 40
    assert storage.state.daily_stats.fertilizer_growth == 4


def test_expired_fertilizer_is_retained_when_the_tier_is_purchased_again(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    now = [1_000.0]
    monkeypatch.setattr(engine, "_now_seconds", lambda: now[0])
    assert engine.purchase_fertilizer("p1", "basic")[0]
    now[0] = 5_000.0
    assert engine.purchase_fertilizer("p1", "basic")[0]

    plant = storage.state.plants[0]
    assert plant.fertilizer_history == [Fertilizer("basic", 1, 4_600.0, 1_000.0)]
    assert plant.fertilizer == Fertilizer("basic", 1, 8_600.0, 5_000.0)
    assert engine.fertilizer_growth(plant, now=4_500.0) == 1
    assert engine.fertilizer_growth(plant, now=4_700.0) == 0
    assert engine.fertilizer_growth(plant, now=5_000.0) == 1
    assert engine.fertilizer_growth(plant, now=8_600.0) == 0

    gained = engine.apply_same_day_reviews(
        [
            {"queue": 2, "ease": 3, "revlog_id": 4_500_000, "answered_at_ms": 4_500_000},
            {"queue": 2, "ease": 3, "revlog_id": 4_700_000, "answered_at_ms": 4_700_000},
            {"queue": 2, "ease": 3, "revlog_id": 5_000_000, "answered_at_ms": 5_000_000},
            {"queue": 2, "ease": 3, "revlog_id": 8_600_000, "answered_at_ms": 8_600_000},
        ],
        latest_revlog_id=8_600_000,
    )

    assert gained == 42
    assert storage.state.daily_stats.fertilizer_growth == 2


def test_fertilizer_history_survives_restart_and_routes_late_answer_once(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    now = [1_000.0]
    monkeypatch.setattr(engine, "_now_seconds", lambda: now[0])
    assert engine.purchase_fertilizer("p1", "basic")[0]
    now[0] = 1_200.0
    assert engine.purchase_fertilizer("p1", "premium", replace_active=True)[0]

    storage.state = GardenState.from_dict(storage.state.to_dict())
    restarted = GardenGameEngine(FakeConfig(), storage)
    restarted.assets.release_ready_plant_species = lambda **_kwargs: tuple(restarted.SPECIES_PRICES)
    plant = storage.state.plants[0]

    assert plant.fertilizer_history == [Fertilizer("basic", 1, 1_200.0, 1_000.0)]
    first = restarted.apply_same_day_reviews(
        [{"queue": 2, "ease": 3, "revlog_id": 1_100_000, "answered_at_ms": 1_100_000}],
        latest_revlog_id=1_100_000,
    )
    second = restarted.apply_same_day_reviews(
        [{"queue": 2, "ease": 3, "revlog_id": 1_100_000, "answered_at_ms": 1_100_000}],
        latest_revlog_id=1_100_000,
    )

    assert first == 11
    assert second == 0
    assert storage.state.daily_stats.fertilizer_growth == 1


def test_fertilizer_history_cap_fails_closed_before_spending(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    plant = storage.state.plants[0]
    plant.fertilizer_history = [
        Fertilizer("basic", 1, float(index * 2 + 2), float(index * 2 + 1))
        for index in range(MAX_FERTILIZER_HISTORY)
    ]
    plant.fertilizer = Fertilizer("quality", 2, 1_000.0, 500.0)
    monkeypatch.setattr(engine, "_now_seconds", lambda: 2_000.0)
    before = storage.state.to_dict()

    ok, message = engine.purchase_fertilizer("p1", "basic")

    assert not ok
    assert "history is full" in message
    assert storage.state.to_dict() == before


def test_scheduler_day_rollover_prunes_only_unreachable_fertilizer_intervals():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.fertilizer_history = [
        Fertilizer("basic", 1, 90.0, 10.0),
        Fertilizer("quality", 2, 110.0, 80.0),
    ]
    plant.fertilizer = Fertilizer("premium", 3, 120.0, 95.0)
    storage.state.daily_stats.day = "2026-08-08"
    storage.day = "2026-08-09"
    storage.day_start_ms = 100_000

    engine.rollover_if_needed()

    assert plant.fertilizer_history == [Fertilizer("quality", 2, 110.0, 80.0)]
    assert plant.fertilizer == Fertilizer("premium", 3, 120.0, 95.0)


@pytest.mark.parametrize(
    ("tier", "growth_per_answer", "duration", "price"),
    [("basic", 1, 3_600, 25), ("quality", 2, 7_200, 65), ("premium", 3, 14_400, 150)],
)
def test_fertilizer_tiers_and_expiry_boundary_are_exact(monkeypatch, tier, growth_per_answer, duration, price):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    monkeypatch.setattr(engine, "_now_seconds", lambda: 1_000.0)

    ok, _message = engine.purchase_fertilizer("p1", tier)
    plant = storage.state.plants[0]

    assert ok
    assert plant.fertilizer.growth_per_answer == growth_per_answer
    assert plant.fertilizer.started_at == 1_000
    assert plant.fertilizer.expires_at == 1_000 + duration
    assert storage.state.currency_balance == 500 - price
    assert engine.fertilizer_growth(plant, now=plant.fertilizer.expires_at - 0.001) == growth_per_answer
    assert engine.fertilizer_growth(plant, now=plant.fertilizer.expires_at) == 0


def test_booster_potion_stacks_with_base_growth_and_expires_at_exact_boundary(monkeypatch):
    engine, storage = make_engine()
    now = storage.now_ms / 1000.0
    monkeypatch.setattr(engine, "_now_seconds", lambda: now)
    storage.state.consumables["booster_potion"] = 1

    ok, message = engine.use_booster_potion()
    plant = storage.state.plants[0]

    assert ok
    assert "+5 Growth" in message
    assert storage.state.consumables["booster_potion"] == 0
    assert plant.booster is not None
    assert plant.booster.started_at == now
    assert plant.booster.expires_at == now + 7_200

    active_award = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": int((now + 1) * 1000),
        "answered_at_ms": int((now + 1) * 1000),
    })
    expired_award = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": int((now + 7_200) * 1000),
        "answered_at_ms": int((now + 7_200) * 1000),
    })

    assert active_award.base_growth == 10
    assert active_award.booster_growth == 5
    assert active_award.total_growth == 15
    assert expired_award.booster_growth == 0
    assert expired_award.total_growth == 10
    assert storage.state.daily_stats.booster_growth == 5


def test_using_another_booster_extends_the_same_activation_window(monkeypatch):
    engine, storage = make_engine()
    now = [1_000.0]
    monkeypatch.setattr(engine, "_now_seconds", lambda: now[0])
    storage.state.consumables["booster_potion"] = 2

    assert engine.use_booster_potion()[0]
    plant = storage.state.plants[0]
    original_start = plant.booster.started_at
    original_expiry = plant.booster.expires_at
    now[0] = 1_100.0
    assert engine.use_booster_potion()[0]

    assert plant.booster.started_at == original_start
    assert plant.booster.expires_at == original_expiry + 7_200
    assert storage.state.consumables["booster_potion"] == 0


def test_random_drop_bands_are_prioritized_deterministic_and_limited_to_one_per_answer(monkeypatch):
    engine, storage = make_engine()
    monkeypatch.setattr(engine, "_drop_hit", lambda *_args: True)
    first_id = storage.now_ms + 1_000
    second_id = first_id + 1_000
    third_id = second_id + 1_000

    answer(engine, storage, revlog_id=first_id)
    answer(engine, storage, revlog_id=second_id)
    answer(engine, storage, revlog_id=third_id)
    duplicate = answer(engine, storage, revlog_id=second_id)

    assert duplicate.total_growth == 0
    kinds = [drop.kind for drop in storage.state.reward_drop_history]
    assert set(kinds[:2]) == {"full_moon", "eclipse"}
    assert kinds[2] == "growth_charge_grand"
    assert storage.state.consumables["growth_charge_grand"] == 1
    assert len({drop.revlog_id for drop in storage.state.reward_drop_history}) == 3
    assert storage.state.ultra_pity_misses == 0
    feedback = {event.kind for event in storage.state.pending_feedback}
    assert {"environment_drop", "charge_drop"}.issubset(feedback)


def test_synced_answers_only_receive_fertilizer_during_the_activation_interval(monkeypatch):
    engine, storage = make_engine()
    storage.state.currency_balance = 500
    monkeypatch.setattr(engine, "_now_seconds", lambda: 1_000.0)
    assert engine.purchase_fertilizer("p1", "quality")[0]

    gained = engine.apply_same_day_reviews(
        [
            {"queue": 2, "ease": 3, "revlog_id": 999_000, "answered_at_ms": 999_000},
            {"queue": 2, "ease": 3, "revlog_id": 1_000_000, "answered_at_ms": 1_000_000},
            {"queue": 2, "ease": 3, "revlog_id": 8_200_000, "answered_at_ms": 8_200_000},
        ],
        latest_revlog_id=8_200_000,
    )

    assert gained == 32
    assert storage.state.daily_stats.base_growth == 30
    assert storage.state.daily_stats.fertilizer_growth == 2


def test_out_of_order_same_day_revlog_id_uses_ledger_not_scalar_cursor():
    engine, storage = make_engine()
    storage.state.processed_revlog_floor = 100
    storage.state.processed_revlog_ids = [200]
    storage.state.last_processed_revlog_id = 200

    rows = [
        {"queue": 2, "ease": 3, "revlog_id": 150, "answered_at_ms": storage.now_ms},
        {"queue": 2, "ease": 3, "revlog_id": 200, "answered_at_ms": storage.now_ms},
    ]
    first = engine.apply_same_day_reviews(rows, latest_revlog_id=200)
    second = engine.apply_same_day_reviews(rows, latest_revlog_id=200)

    assert first == 10
    assert second == 0
    assert storage.state.daily_stats.reviewed == 1
    assert storage.state.processed_revlog_ids == [150, 200]
    assert storage.state.last_processed_revlog_id == 200


def test_species_bed_and_collection_economy_preserves_plant_progress():
    engine, storage = make_engine()
    storage.state.currency_balance = 1_000

    ok, _message, sunflower = engine.purchase_species("sunflower")
    assert ok and sunflower is not None and not sunflower.planted
    assert engine.purchase_next_bed()[0]
    assert engine.plant_from_collection(sunflower.plant_id)[0]
    sunflower.growth_points = 777
    assert engine.move_to_collection("p2")[0]
    assert storage.state.plants[1].growth_points == 0
    assert engine.move_to_collection("p1")[0] is False
    assert sunflower.growth_points == 777


@pytest.mark.parametrize("invalid_destination", ["not-a-bed", object()])
def test_collection_planting_rejects_invalid_external_destination_without_mutation(
    invalid_destination,
):
    engine, storage = make_engine()
    storage.state.unlocked_slots = 3
    shelved = Plant("p3", "sunflower", "Sunny", None)
    storage.state.plants.append(shelved)
    before = storage.state.to_dict()
    saves_before = storage.save_count

    ok, message = engine.plant_from_collection("p3", invalid_destination)

    assert not ok
    assert message == "Choose an empty unlocked garden space."
    assert storage.state.to_dict() == before
    assert storage.save_count == saves_before


def test_invalid_and_insufficient_economy_actions_do_not_mutate_state():
    engine, storage = make_engine()
    before = storage.state.to_dict()

    assert not engine.purchase_fertilizer("missing", "quality")[0]
    assert not engine.purchase_fertilizer("p1", "invalid")[0]
    assert not engine.purchase_fertilizer("p1", "quality")[0]
    assert not engine.purchase_species("bonsai")[0]
    assert not engine.purchase_species("invalid")[0]
    assert not engine.purchase_species("sunflower")[0]
    assert not engine.purchase_next_bed()[0]
    assert storage.state.to_dict() == before


def test_species_beds_capacity_and_duplicate_purchases_are_enforced():
    engine, storage = make_engine()
    storage.state.currency_balance = 10_000

    purchased = []
    for species in (
        "sunflower", "lavender", "hydrangea", "peony",
        "foxglove", "japanese_maple", "wisteria", "dahlia",
    ):
        ok, _message, plant = engine.purchase_species(species)
        assert ok and plant is not None
        purchased.append(plant)
        assert not engine.purchase_species(species)[0]
    assert len(storage.state.plants) == 10
    assert not engine.purchase_species("sunflower")[0]

    while storage.state.unlocked_slots < 6:
        assert engine.purchase_next_bed()[0]
    assert engine.next_bed_price() is None
    assert not engine.purchase_next_bed()[0]


def test_feedback_queue_is_ordered_deduplicated_bounded_and_persisted():
    engine, storage = make_engine()
    for index in range(110):
        assert engine._queue_feedback(f"event:{index}", "test", f"Message {index}")
    assert not engine._queue_feedback("event:109", "test", "Duplicate")
    assert len(engine.peek_feedback()) == 100
    assert engine.peek_feedback()[0].event_id == "event:10"

    consumed = engine.consume_feedback(limit=3)

    assert [event.event_id for event in consumed] == ["event:10", "event:11", "event:12"]
    assert engine.peek_feedback()[0].event_id == "event:13"
    assert storage.save_count > 0


def test_feedback_acknowledgement_by_rendered_ids_survives_queue_cap_churn():
    engine, _storage = make_engine()
    assert engine._queue_feedback("rendered:A", "test", "Rendered A")
    assert engine._queue_feedback("rendered:B", "test", "Rendered B")
    rendered_ids = ("rendered:A", "rendered:B")

    # The 100-item cap drops A while B remains and all later events are new.
    for index in range(99):
        assert engine._queue_feedback(f"new:{index}", "test", f"New {index}")
    before = [event.event_id for event in engine.peek_feedback()]
    assert "rendered:A" not in before
    assert "rendered:B" in before

    consumed = engine.consume_feedback(event_ids=rendered_ids)
    remaining = [event.event_id for event in engine.peek_feedback()]

    assert [event.event_id for event in consumed] == ["rendered:B"]
    assert remaining == [event_id for event_id in before if event_id != "rendered:B"]
    assert remaining == [f"new:{index}" for index in range(99)]


def test_placement_draft_swap_undo_and_commit_are_deterministic():
    engine, storage = make_engine()
    before_growth = {
        plant.plant_id: plant.growth_points for plant in storage.state.plants
    }
    active_id = storage.state.active_plant_id
    ok, _message, draft = engine.begin_placement_draft("p1")
    assert ok and draft is not None
    assert engine.stage_placement(draft, 1)[0]
    assert draft.scene_slots() == {"p1": 1, "p2": 0}
    assert engine.undo_staged_placement(draft)[0]
    assert draft.scene_slots() == {"p1": 0, "p2": 1}
    assert engine.stage_placement(draft, 1)[0]
    ok, _message, committed = engine.commit_placement_draft(draft)
    assert ok and committed is not None
    assert {plant.plant_id: plant.slot_index for plant in storage.state.plants} == {"p1": 1, "p2": 0}
    assert storage.state.active_plant_id == active_id
    assert {
        plant.plant_id: plant.growth_points for plant in storage.state.plants
    } == before_growth

    ok, _message, _inverse = engine.restore_placement(committed)
    assert ok
    assert {plant.plant_id: plant.slot_index for plant in storage.state.plants} == {
        "p1": 0,
        "p2": 1,
    }
    assert storage.state.active_plant_id == active_id
    assert {
        plant.plant_id: plant.growth_points for plant in storage.state.plants
    } == before_growth


def test_all_plants_can_use_any_unlocked_v6_direct_soil_bed():
    engine, storage = make_engine()
    storage.state.unlocked_slots = 6
    storage.state.plants[0].slot_index = 2
    storage.state.plants[1].slot_index = 3
    sunflower = Plant("sun", "sunflower", "Sunny", None)
    storage.state.plants.append(sunflower)

    ok, _message = engine.plant_from_collection("sun", 4)
    assert ok
    assert sunflower.slot_index == 4


def test_v6_surface_validation_allows_direct_moves_and_swaps_across_all_beds():
    engine, storage = make_engine()
    storage.state.unlocked_slots = 6
    storage.state.plants[0].slot_index = 2
    storage.state.plants[1].slot_index = 3
    sunflower = Plant("sun", "sunflower", "Sunny", 0)
    storage.state.plants.append(sunflower)

    draft = engine.begin_placement_draft("sun")[2]
    assert draft is not None
    assert set(engine.valid_destination_slots(draft)) == set(range(6))
    assert engine.stage_placement(draft, 4)[0]
    assert draft.scene_slots()["sun"] == 4

    bonsai = engine.begin_placement_draft("p1")[2]
    assert bonsai is not None
    assert set(engine.valid_destination_slots(bonsai)) == set(range(6))
    assert engine.stage_placement(bonsai, 0)[0]


def test_existing_v6_direct_soil_placement_is_preserved_without_unlocking_beds():
    storage = FakeStorage()
    storage.state.plants.append(Plant("sun", "sunflower", "Sunny", 4))
    storage.state.active_plant_id = "sun"

    engine = GardenGameEngine(FakeConfig(), storage)

    assert engine.plant_story("sun").slot_index == 4
    assert storage.state.unlocked_slots == 2
    assert storage.state.active_plant_id == "sun"
    assert not any(event.event_id == "surface-repair:sun" for event in storage.state.pending_feedback)


def test_v6_geometry_refresh_preserves_progress_and_seats_only_active_plant():
    storage = FakeStorage()
    storage.state.scene_geometry_version = 4
    storage.state.plants[0].slot_index = 1
    storage.state.plants[0].growth_points = 2_345
    storage.state.plants[0].bonus_remainder = 17
    storage.state.plants[1].slot_index = 5

    GardenGameEngine(FakeConfig(), storage)

    moss, briar = storage.state.plants
    assert storage.state.scene_geometry_version == 6
    assert moss.slot_index == 3
    assert briar.slot_index is None
    assert (moss.plant_id, moss.name, moss.growth_points, moss.bonus_remainder) == (
        "p1", "Moss", 2_345, 17,
    )
    notices = [event for event in storage.state.pending_feedback if event.event_id == "scene-geometry:6"]
    assert len(notices) == 1
    assert "Placements were refreshed" in notices[0].message


def test_v6_geometry_refresh_uses_nearest_direct_soil_bed_for_active_plant():
    storage = FakeStorage()
    storage.state.scene_geometry_version = 4
    storage.state.unlocked_slots = 4
    storage.state.plants.append(Plant("sun", "sunflower", "Sunny", 3, growth_points=800))
    storage.state.active_plant_id = "sun"

    GardenGameEngine(FakeConfig(), storage)

    sun = next(plant for plant in storage.state.plants if plant.plant_id == "sun")
    assert sun.slot_index == 2
    assert storage.state.unlocked_slots == 4
    assert all(plant.slot_index is None for plant in storage.state.plants if plant.plant_id != "sun")


def test_failed_save_rolls_back_review_and_currency_state():
    engine, storage = make_engine()
    before = storage.state.to_dict()
    storage.fail_save = True

    with pytest.raises(OSError):
        answer(engine, storage)

    assert storage.state.to_dict() == before


def test_failed_same_day_batch_rolls_back_growth_cursor_and_transitions():
    engine, storage = make_engine()
    storage.state.plants[0].growth_points = 490
    before = storage.state.to_dict()
    storage.fail_save = True

    with pytest.raises(OSError):
        engine.apply_same_day_reviews(
            [{"queue": 2, "ease": 3, "revlog_id": storage.now_ms + 1}],
            latest_revlog_id=storage.now_ms + 1,
        )

    assert storage.state.to_dict() == before
    assert engine.peek_stage_transitions() == []


def test_garden_and_generated_plant_names_are_plain_unambiguous_and_editable():
    engine, storage = make_engine()

    ok, message = engine.rename_garden("  Moss   & Moon  ")

    assert ok
    assert "Moss & Moon" in message
    assert storage.state.garden_name == "Moss & Moon"
    assert storage.state.garden_setup_version == 1
    assert engine._generated_name("bonsai") == "Bonsai Plant"
    assert engine._generated_name("japanese_maple") == "Japanese Maple Plant"
    assert not engine.rename_garden("   ")[0]


def test_development_population_fails_closed_without_capture_build_capability(
    monkeypatch,
):
    monkeypatch.setenv("ANKI_GARDEN_DEV_TOOLS", "1")
    monkeypatch.setenv("ANKI_GARDEN_CAPTURE_UI_FACES", "1")
    engine, storage = make_engine()
    before = storage.state.to_dict()
    save_count = storage.save_count

    ok, message = engine.development_populate()

    assert not ok
    assert "unavailable in this production build" in message
    assert storage.state.to_dict() == before
    assert storage.save_count == save_count


def test_development_population_builds_complete_state_without_touching_revlog_ledger(
    monkeypatch,
):
    monkeypatch.setattr(
        "ankigarden.game.build_capabilities.DEVELOPMENT_MUTATION_ENABLED",
        True,
    )
    engine, storage = make_engine()
    storage.state.last_processed_revlog_id = 123_456
    storage.state.processed_revlog_floor = 100_000
    storage.state.processed_revlog_ids = [123_000, 123_456]

    ok, message = engine.development_populate()

    assert ok
    assert "100,000 Coins" in message
    assert len(storage.state.plants) == len(CURRENT_CATALOG_SPECIES_ORDER) == 10
    assert {plant.species for plant in storage.state.plants} == set(CURRENT_CATALOG_SPECIES_ORDER)
    assert {plant.slot_index for plant in storage.state.plants if plant.planted} == set(range(6))
    assert storage.state.unlocked_slots == 6
    assert storage.state.currency_balance >= 100_000
    assert storage.state.consumables["booster_potion"] >= 12
    active = engine.active_plant()
    assert active is not None and active.planted and not active.fully_grown
    assert storage.state.last_processed_revlog_id == 123_456
    assert storage.state.processed_revlog_floor == 100_000
    assert storage.state.processed_revlog_ids == [123_000, 123_456]


@pytest.mark.parametrize(
    "mutation",
    [
        "all_due", "feedback", "fertilizer", "booster", "species", "bed", "plant",
        "collection", "active", "rename", "garden_name", "place", "commit", "restore",
    ],
)
def test_every_persistent_mutation_rolls_back_after_save_failure(mutation):
    engine, storage = make_engine(goal=150)
    storage.state.currency_balance = 2_000
    if mutation == "feedback":
        storage.state.pending_feedback = [FeedbackEvent("one", "test", "One", "2026-08-08T12:00:00+00:00")]
    if mutation == "plant":
        storage.state.plants.append(Plant("p3", "hydrangea", "Misty", None))
    if mutation == "booster":
        storage.state.consumables["booster_potion"] = 1
    if mutation == "all_due":
        storage.state.daily_stats.reviewed = 1
    draft = None
    change = None
    if mutation == "commit":
        draft = engine.begin_placement_draft("p1")[2]
        assert draft is not None and engine.stage_placement(draft, 1)[0]
    if mutation == "restore":
        ok, _message, change = engine.place_plant("p1", 1)
        assert ok and change is not None
    before = storage.state.to_dict()
    storage.fail_save = True

    if mutation == "all_due":
        result = engine.evaluate_all_due(DueObligationStatus())
    elif mutation == "feedback":
        with pytest.raises(OSError):
            engine.consume_feedback(limit=1)
        result = None
    elif mutation == "fertilizer":
        result = engine.purchase_fertilizer("p1", "basic")
    elif mutation == "booster":
        result = engine.use_booster_potion("p1")
    elif mutation == "species":
        result = engine.purchase_species("sunflower")
    elif mutation == "bed":
        result = engine.purchase_next_bed()
    elif mutation == "plant":
        result = engine.plant_from_collection("p3")
    elif mutation == "collection":
        result = engine.move_to_collection("p2")
    elif mutation == "active":
        result = engine.set_active_plant("p2")
    elif mutation == "rename":
        result = engine.rename_plant("p1", "Juniper")
    elif mutation == "garden_name":
        result = engine.rename_garden("Moss & Moon")
    elif mutation == "place":
        result = engine.place_plant("p1", 1)
    elif mutation == "commit":
        result = engine.commit_placement_draft(draft)
    else:
        result = engine.restore_placement(change)

    if result is not None:
        assert result[0] is False
    assert storage.state.to_dict() == before


@pytest.mark.parametrize(
    ("reviews_per_day", "stage_days"),
    [
        (50, [1, 5, 16, 40, 100]),
        (150, [1, 2, 6, 14, 34]),
        (300, [1, 1, 3, 7, 17]),
        (500, [1, 1, 2, 4, 10]),
    ],
)
def test_progression_balance_profiles(reviews_per_day, stage_days):
    base_growth_per_day = reviews_per_day * 10
    calculated = [math.ceil(threshold / base_growth_per_day) for threshold in GROWTH_THRESHOLDS[1:]]
    assert calculated == stage_days


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(4, "night"), (5, "dawn"), (7, "dawn"), (8, "day"), (16, "day"),
     (17, "dusk"), (19, "dusk"), (20, "night"), (23, "night")],
)
def test_background_time_band_uses_local_clock_boundaries(hour, expected):
    moment = datetime(2026, 8, 8, hour, 0).astimezone()
    assert GardenGameEngine.local_time_band(moment) == expected


@pytest.mark.parametrize("tier", ["basic", "quality", "premium"])
def test_daily_currency_cannot_keep_fertilizer_active_constantly(tier):
    spec = GardenGameEngine.FERTILIZERS[tier]
    sustainable_hours_per_day = (15 / spec.price) * (spec.duration_seconds / 3600)
    assert sustainable_hours_per_day < 1


def test_currency_is_never_awarded_per_review():
    engine, storage = make_engine(goal=5_000)
    for _ in range(100):
        answer(engine, storage)
    assert all(not tx.event_key.startswith("review:") for tx in storage.state.currency_transactions)
    assert {
        tx.event_key
        for tx in storage.state.currency_transactions
        if tx.event_key.startswith("stage:")
    } == {"stage:p1:sprout"}


def test_streak_currency_milestones_are_once_ever_even_after_ledger_pruning():
    engine, storage = make_engine()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.currency_balance == 25
    assert storage.state.claimed_streak_rewards == [7]
    storage.state.currency_transactions.clear()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.currency_balance == 25
    assert storage.state.currency_transactions == []
