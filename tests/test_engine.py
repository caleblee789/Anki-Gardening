from __future__ import annotations

import math
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import (
    GardenGameEngine,
    StageTransition,
    difficulty_from_factor,
    queue_and_lapse_from_revlog_type,
)
from ankigarden.garden_finds import (
    GardenFindReward,
    PreparedRewardRegistry,
    consumption_id,
    stable_answer_event_identity,
)
from ankigarden.growth import (
    GrowthChargeRequest,
    GrowthChargeStatus,
    GrowthChargeTargetState,
)
from ankigarden.models.state import (
    ActivePlantPeriod,
    CardEffectBatch,
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
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
    RewardReceipt,
    STATE_VERSION,
)
from ankigarden.storage import (
    DueObligationStatus,
    GardenStorage,
    HistoricalReviewEntry,
    HistoricalReviewSnapshot,
    RevlogReadError,
    SchedulerBoundaryError,
)


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
            reward_seed="test-engine-reward-seed",
        )
        self.addon_dir = Path("ankigarden")
        self.assets_root = self.addon_dir / "assets"
        self.save_count = 0
        self.fail_save = False
        self.due_status = DueObligationStatus()
        self.eligible_study_days = ()
        self.today_cards_completion_days = set()

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

    def eligible_study_days_before(self, _scheduler_day, *, limit=7):
        return tuple(self.eligible_study_days)[-max(0, int(limit)):]

    def verified_today_cards_completion_days_before(self, _scheduler_day):
        return set(self.today_cards_completion_days)


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


@pytest.mark.parametrize("unlocks", range(8))
@pytest.mark.parametrize("feature", ("seedling_sign", "wind_chime"))
def test_permanent_trophies_stack_and_survive_duplicate_events_and_restart(unlocks, feature):
    from ankigarden.balance_catalog import ACHIEVEMENT_TROPHIES, GARDEN_BONUS_BY_ID

    engine, storage = make_engine()
    state = storage.state
    for bit, trophy in enumerate(ACHIEVEMENT_TROPHIES):
        if unlocks & (1 << bit):
            state.achievements[str(trophy.source_achievement_id)].unlocked = True
            state.trophy_activation_ms[str(trophy.cosmetic_id)] = storage.now_ms - 1
    state.inventory["garden_features"].append(feature)
    state.loadout.display_decoration_id = feature
    state.wind_chime_progress = GARDEN_BONUS_BY_ID["wind_chime"].effects[0].cadence.every_n - 1
    engine.observe_due_start(DueObligationStatus(review_count=1))
    award = answer(engine, storage)
    primary = (10 + bool(unlocks & 1) + (feature == "wind_chime")) * 100
    share = primary * (3 if unlocks & 4 else 1) // (20 if unlocks & 4 else 10)
    assert award.total_growth_units == primary
    assert award.shared_growth_units == share
    assert award.trophy_growth_units == (100 if unlocks & 1 else 0)
    assert state.daily_stats.trophy_growth == bool(unlocks & 1)
    assert engine.evaluate_today_cards(DueObligationStatus(), record_completed_delta=True)[0]
    journal = [r for r in state.recent_reward_receipts if r.source == "achievement_trophy"]
    assert sum(r.amount for r in journal) == (5 if unlocks & 2 else 0)
    assert engine.last_completion_result.trophy_coins == (5 if unlocks & 2 else 0)
    balance, growth = state.currency_balance, [p.growth_units for p in state.plants]
    answer(engine, storage, revlog_id=storage.now_ms)
    assert not engine.evaluate_today_cards(DueObligationStatus())[0]
    assert (state.currency_balance, [p.growth_units for p in state.plants]) == (balance, growth)
    boundary = dict(state.trophy_activation_ms)
    storage.state = GardenState.from_dict(state.to_dict())
    restarted = GardenGameEngine(FakeConfig(), storage)
    assert restarted.state.trophy_activation_ms == boundary
    before = restarted.project_review_growth(now=storage.now_ms / 1000)
    restarted.state.loadout.visibility = {"garden_feature": False, "scenery": False}
    after = restarted.project_review_growth(now=storage.now_ms / 1000)
    assert (after.trophy_growth_units, after.shared_growth_units) == (before.trophy_growth_units, before.shared_growth_units)


@pytest.mark.parametrize("trophy_id,achievement_id", (
    ("botanists_plaque", "botanical_collection"),
    ("garden_journal", "year_of_harvests"),
    ("golden_trowel", "ancient_garden"),
))
def test_trophy_unlock_boundary_blocks_backpay_and_rolls_back_with_failed_save(trophy_id, achievement_id):
    from ankigarden.trophies import trophy_effects

    engine, storage = make_engine()
    before = storage.state.to_dict()
    engine._unlock_achievement(achievement_id, completion_day=storage.day, correlation_id="trophy-test")
    boundary = storage.state.trophy_activation_ms[trophy_id]
    from ankigarden.trophies import trophy_presentations
    presentation = next(t for t in trophy_presentations(storage.state) if t.trophy_id == trophy_id)
    assert presentation.obtained_at == storage.state.achievements[achievement_id].unlocked_at
    before_effects = trophy_effects(storage.state, event_ms=boundary)
    after_effects = trophy_effects(storage.state, event_ms=boundary + 1)
    assert before_effects.review_growth == before_effects.completion_coins == 0
    assert before_effects.shared_growth_percent == 10
    assert after_effects.review_growth == (1 if trophy_id == "botanists_plaque" else 0)
    assert after_effects.completion_coins == (5 if trophy_id == "garden_journal" else 0)
    assert after_effects.shared_growth_percent == (15 if trophy_id == "golden_trowel" else 10)
    storage.fail_save = True
    with pytest.raises(OSError):
        engine._persist_or_restore(before)
    assert not storage.state.achievements[achievement_id].unlocked
    assert storage.state.trophy_activation_ms == {}


@pytest.mark.parametrize("beds", (0, 1, 6))
@pytest.mark.parametrize("full_bloom", (False, True))
def test_trophy_shared_growth_conserves_every_planted_lane_and_overflow(beds, full_bloom):
    engine, storage = make_engine()
    state = storage.state
    state.plants = [Plant(f"p{i}", CURRENT_CATALOG_SPECIES_ORDER[i], f"Plant {i}", i,
                          growth_points=GROWTH_THRESHOLDS[-1] if full_bloom else 0)
                    for i in range(beds)]
    state.active_plant_id = state.plants[0].plant_id if beds and not full_bloom else None
    for trophy, achievement in (("botanists_plaque", "botanical_collection"), ("golden_trowel", "ancient_garden")):
        state.achievements[achievement].unlocked = True
        state.trophy_activation_ms[trophy] = storage.now_ms - 1
    award = engine._award_review_growth(engine.active_plant(), storage.now_ms)
    expected = 1100 + max(0, beds - 1) * 165
    assert award.total_growth_units == 1100
    assert award.applied_growth_units + award.stored_growth_units == expected
    assert award.stored_growth_units == (expected if full_bloom or not beds else 0)


def test_golden_trowel_unlocks_after_the_100000th_answer_without_retroactive_growth():
    engine, storage = make_engine()
    storage.state.lifetime_eligible_answers = 99_999
    unlocking = answer(engine, storage)
    assert storage.state.achievements["ancient_garden"].unlocked
    assert unlocking.shared_growth_units == 100
    assert answer(engine, storage).shared_growth_units == 150


def test_botanists_plaque_starts_after_the_tenth_species_reaches_full_bloom():
    engine, storage = make_engine()
    storage.state.plants = [
        Plant("p1", CURRENT_CATALOG_SPECIES_ORDER[0], "Last bloom", 0,
              growth_points=GROWTH_THRESHOLDS[-1] - 5),
        *(Plant(f"p{i}", species, species, None, growth_points=GROWTH_THRESHOLDS[-1])
          for i, species in enumerate(CURRENT_CATALOG_SPECIES_ORDER[1:], start=2)),
    ]
    unlocking = answer(engine, storage)
    assert storage.state.achievements["botanical_collection"].unlocked
    assert unlocking.trophy_growth_units == 0
    assert answer(engine, storage).trophy_growth_units == 100


def test_garden_journal_starts_after_365_verified_completions_and_pays_once_next_day():
    engine, storage = make_engine()
    storage.state.lifetime_economy_aggregates.today_cards_completions = 364
    engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage)
    assert engine.evaluate_today_cards(DueObligationStatus(), record_completed_delta=True)[0]
    assert storage.state.achievements["year_of_harvests"].unlocked
    assert engine.last_completion_result.trophy_coins == 0
    storage.day = "2026-08-09"
    storage.day_start_ms += 86_400_000
    storage.now_ms += 86_400_000
    engine.rollover_if_needed()
    engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage)
    assert engine.evaluate_today_cards(DueObligationStatus(), record_completed_delta=True)[0]
    assert engine.last_completion_result.trophy_coins == 5
    assert not engine.evaluate_today_cards(DueObligationStatus())[0]
    assert sum(r.amount for r in storage.state.recent_reward_receipts
               if r.source == "achievement_trophy") == 5


def test_existing_trophies_activate_once_on_upgrade_without_reissuing_rewards():
    from ankigarden.balance_catalog import ACHIEVEMENT_TROPHIES
    engine, storage = make_engine()
    for trophy in ACHIEVEMENT_TROPHIES:
        storage.state.achievements[str(trophy.source_achievement_id)].unlocked = True
    before = (storage.state.currency_balance, dict(storage.state.consumables))
    GardenGameEngine(FakeConfig(), storage)
    activations = dict(storage.state.trophy_activation_ms)
    assert len(activations) == 3 and set(activations.values()) == {storage.now_ms}
    storage.now_ms += 1000
    storage.state = GardenState.from_dict(storage.state.to_dict())
    GardenGameEngine(FakeConfig(), storage)
    assert storage.state.trophy_activation_ms == activations
    assert (storage.state.currency_balance, storage.state.consumables) == before


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


def test_public_batch_selects_only_new_receipts_without_pruning_history():
    engine, storage = make_engine()
    state = storage.state
    state.starter_selection_complete = True
    state.garden_setup_version = 1
    state.reward_state_initialized = True
    state.reward_activation_ms = storage.day_start_ms
    state.progression_activation_ms = storage.day_start_ms
    state.garden_find_activation_ms = storage.now_ms + 1_000_000
    existing = RewardReceipt(
        event_key="existing",
        reward_type="coins",
        source="achievement",
        source_id="existing",
        scheduler_day=storage.day,
        correlation_id="existing",
        occurred_at="2026-08-08T00:00:00Z",
        amount=1,
    )
    state.recent_reward_receipts.append(existing)
    first_id = storage.now_ms + 1_000
    second_id = first_id + 1_000

    results = engine.apply_same_day_reviews_with_results(
        [
            {
                "queue": 2,
                "ease": 3,
                "revlog_id": first_id,
                "answered_at_ms": first_id,
                "correlation_id": "answer:first",
            },
            {
                "queue": 2,
                "ease": 3,
                "revlog_id": second_id,
                "answered_at_ms": second_id,
                "correlation_id": "answer:second",
            },
        ],
        latest_revlog_id=second_id,
    )

    assert [receipt.event_key for receipt in results[0].reward_receipts] == [
        f"daily_activity:{storage.day}",
    ]
    assert results[1].reward_receipts == ()
    assert [receipt.event_key for receipt in state.recent_reward_receipts] == [
        "existing",
        f"daily_activity:{storage.day}",
    ]


def test_public_batch_can_skip_result_snapshots_without_changing_commit_state():
    payloads = [
        {
            "queue": 2,
            "ease": ease,
            "revlog_id": 1_786_150_001_000 + index,
            "answered_at_ms": 1_786_150_001_000 + index,
            "card_id": index,
            "answer_identity": f"batch-result-mode:{index}",
            "emit_feedback": False,
        }
        for index, ease in enumerate((1, 2, 3, 4), start=1)
    ]

    engines = []
    for collect_results in (True, False):
        engine, storage = make_engine()
        state = storage.state
        state.starter_selection_complete = True
        state.garden_setup_version = 1
        state.reward_state_initialized = True
        state.reward_activation_ms = storage.day_start_ms
        state.progression_activation_ms = storage.day_start_ms
        state.garden_find_activation_ms = storage.now_ms + 1_000_000
        results = engine.apply_same_day_reviews_with_results(
            payloads,
            latest_revlog_id=int(payloads[-1]["revlog_id"]),
            due_status=DueObligationStatus(review_count=0),
            collect_results=collect_results,
        )
        assert len(results) == (4 if collect_results else 0)
        engines.append((engine, storage))

    def committed_projection(engine, storage):
        state = engine.state
        return {
            "wallet": state.currency_balance,
            "plants": tuple(
                (plant.plant_id, plant.growth_units, plant.growth_stage)
                for plant in state.plants
            ),
            "daily": dict(vars(state.daily_stats)),
            "reward_keys": tuple(state.applied_reward_event_keys),
            "receipts": tuple(
                (
                    receipt.event_key,
                    receipt.reward_type,
                    receipt.source,
                    receipt.source_id,
                    receipt.amount,
                    receipt.item_id,
                )
                for receipt in state.recent_reward_receipts
            ),
            "transactions": tuple(
                (
                    row.event_key,
                    row.transaction_type,
                    row.source,
                    row.source_id,
                    row.delta,
                    row.balance,
                )
                for row in state.currency_transactions
            ),
            "aggregates": state.lifetime_economy_aggregates.to_dict(),
            "save_count": storage.save_count,
        }

    assert committed_projection(*engines[0]) == committed_projection(*engines[1])


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


def test_rollover_does_not_consume_the_new_open_day_answer_from_history():
    engine, storage = make_engine()
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = storage.now_ms - 1
    storage.state.garden_find_activation_ms = storage.now_ms - 1
    storage.day = "2026-08-09"
    storage.day_start_ms += 86_400_000
    storage.now_ms = storage.day_start_ms + 1_000
    entry = HistoricalReviewEntry(
        revlog_id=storage.now_ms,
        card_id=42,
        ease=3,
        interval=1,
        last_interval=0,
        factor=2_500,
        response_time_ms=500,
        review_type=1,
        answer_ms=storage.now_ms,
        scheduler_day=storage.day,
        card_day_ordinal=1,
    )
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=(entry,),
        high_water_revlog_id=entry.revlog_id,
        fingerprint="open-day",
    )

    award = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": entry.revlog_id,
        "card_id": entry.card_id,
        "answered_at_ms": entry.answer_ms,
        "answer_identity": entry.stable_answer_key,
        "scheduler_day": entry.scheduler_day,
    })

    assert award.total_growth == 10
    assert storage.state.daily_stats.day == storage.day
    assert storage.state.daily_stats.reviewed == 1
    assert sum(
        tx.delta
        for tx in storage.state.currency_transactions
        if tx.event_key == f"daily_activity:{storage.day}"
    ) == 4


def test_first_history_failure_retains_activation_for_later_synced_answer():
    engine, storage = make_engine()
    storage.now_ms = 100
    storage.load_eligible_review_history = lambda: (_ for _ in ()).throw(
        RevlogReadError("collection busy")
    )

    reconciled, _message = engine.reconcile_reward_history()

    assert not reconciled
    assert not storage.state.reward_state_initialized

    entry = HistoricalReviewEntry(
        revlog_id=150,
        card_id=42,
        ease=3,
        interval=1,
        last_interval=0,
        factor=2_500,
        response_time_ms=500,
        review_type=1,
        answer_ms=150,
        scheduler_day=storage.day,
        card_day_ordinal=1,
    )
    storage.now_ms = 200
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=(entry,),
        high_water_revlog_id=entry.revlog_id,
        fingerprint="retry-history",
    )

    reconciled, _message = engine.reconcile_reward_history()

    assert reconciled
    assert storage.state.reward_activation_ms == 100
    assert storage.state.plants[0].growth_points == 10
    assert storage.state.currency_balance == 4


def test_first_garden_receipt_preserves_all_paid_history_without_replaying_study():
    from ankigarden.welcome_presentation import present_welcome

    storage = FakeStorage()
    storage.state = GardenState(daily_stats=DailyStats(day=storage.day))
    # Repeat reviews of one card count as study events, over a past 365-day
    # streak that has since ended. All ten historical milestones qualify.
    start = datetime(2025, 1, 1)
    entries = tuple(
        HistoricalReviewEntry(
            revlog_id=number, card_id=42, ease=3, interval=1, last_interval=0,
            factor=2500, response_time_ms=500, review_type=1, answer_ms=number,
            scheduler_day=(start + timedelta(days=min(364, number // 274))).date().isoformat(),
            card_day_ordinal=number % 274 + 1,
        )
        for number in range(1, 100_001)
    )
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=entries, high_water_revlog_id=100_000, fingerprint="welcome-history",
    )
    engine = GardenGameEngine(FakeConfig(), storage)
    assert engine.reconcile_reward_history()[0]
    receipt = storage.state.welcome_receipt
    view = present_welcome(receipt)
    assert receipt.history_review_count == 100_000
    assert view.achievement_count == 10
    assert view.history_intro == (
        "You’ve completed 100,000 card reviews in Anki. "
        "Your past study has earned you these rewards:"
    )
    assert {row.item_id or row.label: row.amount for row in view.history} == {
        "Coins": 1785, "growth_charge_small": 1, "growth_charge_standard": 2,
        "growth_charge_grand": 1, "golden_trowel": 1,
    }
    assert storage.state.currency_balance == 1785
    assert storage.state.streak_days == 0
    assert storage.state.daily_stats.reviewed == 0
    assert storage.state.stored_growth_units == 0
    assert not storage.state.plants
    assert not engine.peek_feedback()
    assert engine.reconcile_reward_history()[0]
    assert storage.state.welcome_receipt == receipt
    assert storage.state.currency_balance == 1785

    # A paused setup retains its receipt even after the general cache expires.
    storage.state.recent_reward_receipts.clear()
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), storage)
    assert engine.reconcile_reward_history()[0]
    assert storage.state.welcome_receipt == receipt
    ok, _, plant = engine.choose_starter("rose")
    assert ok and engine.set_active_plant(plant.plant_id)[0]
    assert engine.finish_onboarding()[0]
    ready = storage.state.welcome_receipt
    assert ready.history_rewards == receipt.history_rewards
    assert storage.state.currency_balance == 1836
    assert plant.growth_points == 100
    assert engine.reconcile_reward_history()[0]
    assert storage.state.welcome_receipt == ready


def test_closed_day_delayed_ingestion_uses_durable_cutoffs_target_and_effects():
    storage = FakeStorage()
    storage.now_ms = 500
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = 100
    storage.state.progression_activation_ms = 200
    storage.state.garden_find_activation_ms = 1_000
    storage.state.active_plant_id = "p2"
    storage.state.active_plant_periods = [
        ActivePlantPeriod("2026-08-07", "p1", 200),
        ActivePlantPeriod(storage.day, "p2", 400),
    ]
    storage.state.plants[0].fertilizer_history = [
        Fertilizer("basic", 1, 0.35, 0.20)
    ]
    storage.state.plants[0].booster_history = [Booster(5, 0.35, 0.20)]
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), storage)
    entries = (
        HistoricalReviewEntry(
            150, 41, 3, 1, 0, 2_500, 500, 1, 150,
            "2026-08-07", 1, "v1|2026-08-07|41|1",
        ),
        HistoricalReviewEntry(
            250, 42, 3, 1, 0, 2_500, 500, 1, 250,
            "2026-08-07", 1, "v1|2026-08-07|42|1",
        ),
    )
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=entries,
        high_water_revlog_id=250,
        fingerprint="delayed-effects",
    )

    reconciled, _message = engine.reconcile_reward_history()
    after_first = storage.state.to_dict()
    repeated, _message = engine.reconcile_reward_history()

    assert reconciled and repeated
    assert storage.state.plants[0].growth_points == 16
    assert storage.state.plants[1].growth_points == 1
    assert storage.state.plants[1].growth_remainder_units == 60
    assert storage.state.currency_balance == 4
    assert set(storage.state.processed_answer_keys) == {
        consumption_id(stable_answer_event_identity(
            entry.revlog_id,
            card_id=entry.card_id,
            answered_at_ms=entry.answer_ms,
            lineage_id=entry.stable_answer_key,
        ))
        for entry in entries
    }
    assert storage.state.to_dict() == after_first


def test_full_history_sync_reconciliation_rewards_past_and_current_but_not_future():
    engine, storage = make_engine()
    past_day = "2026-08-07"
    current_day = storage.day
    storage.state.inventory["garden_features"].append("watering_station")
    assert engine.equip_environment("garden_feature", "watering_station")[0]
    storage.state.watering_station_progress = 2
    storage.state.watering_station_progress_by_day = {past_day: 4, current_day: 2}
    storage.state.inventory["scenery"].append("spring")
    assert engine.equip_environment("scenery", "spring")[0]
    future_day = "2026-08-09"
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = 100
    storage.state.progression_activation_ms = 100
    storage.state.garden_find_activation_ms = 10_000
    storage.state.active_plant_periods = [
        ActivePlantPeriod(past_day, "p1", 100),
        ActivePlantPeriod(current_day, "p1", 100),
    ]
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    storage.state.daily_loadout.scheduler_day = current_day
    storage.state.daily_loadout.locked_at_ms = 150
    storage.state.daily_loadout.garden_feature_id = "seedling_sign"
    storage.state.daily_loadout.garden_bonus_anki_day_id = current_day
    storage.state.daily_loadout.garden_bonus_locked_at_ms = 150
    storage.state.daily_loadout.scenery_id = "default"
    current_loadout_before = dict(vars(storage.state.daily_loadout))

    def history_entry(
        revlog_id: int,
        *,
        card_id: int,
        answer_ms: int,
        scheduler_day: str,
        ordinal: int,
    ) -> HistoricalReviewEntry:
        return HistoricalReviewEntry(
            revlog_id=revlog_id,
            card_id=card_id,
            ease=3,
            interval=1,
            last_interval=0,
            factor=2_500,
            response_time_ms=500,
            review_type=1,
            answer_ms=answer_ms,
            scheduler_day=scheduler_day,
            card_day_ordinal=ordinal,
            answer_identity=(
                f"v1|{scheduler_day}|{card_id}|{ordinal}"
            ),
        )

    past = history_entry(
        400,
        card_id=42,
        answer_ms=1_000,
        scheduler_day=past_day,
        ordinal=1,
    )
    current = history_entry(
        500,
        card_id=43,
        answer_ms=2_000,
        scheduler_day=current_day,
        ordinal=1,
    )
    future = history_entry(
        600,
        card_id=44,
        answer_ms=3_000,
        scheduler_day=future_day,
        ordinal=1,
    )
    rows = [past, current, future]
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=tuple(rows),
        high_water_revlog_id=max(row.revlog_id for row in rows),
        fingerprint=f"full-history-{len(rows)}",
    )

    def answer_key(entry: HistoricalReviewEntry) -> str:
        return consumption_id(stable_answer_event_identity(
            entry.revlog_id,
            card_id=entry.card_id,
            answered_at_ms=entry.answer_ms,
            lineage_id=entry.stable_answer_key,
        ))

    first_results = []
    reconciled, _message = engine.reconcile_reward_history(
        result_collector=first_results,
        due_status=DueObligationStatus(),
        emit_feedback=False,
    )

    assert reconciled
    assert [result.scheduler_day for result in first_results] == [
        past_day,
        current_day,
    ]
    assert all(result.award.total_growth_units > 0 for result in first_results)
    assert [result.award.scenery_growth_units for result in first_results] == [200, 200]
    assert [result.award.weather_growth_units for result in first_results] == [200, 100]
    assert storage.state.watering_station_progress == 1
    assert GardenState.from_dict(storage.state.to_dict()).watering_station_progress_by_day == {
        past_day: 1, current_day: 1,
    }
    assert not first_results[0].daily_completion_rewarded
    assert first_results[1].daily_completion_rewarded
    assert storage.state.daily_completion.scheduler_day == current_day
    assert storage.state.daily_completion.reward_claimed
    assert dict(vars(storage.state.daily_loadout)) == current_loadout_before
    assert answer_key(past) in storage.state.processed_answer_keys
    assert answer_key(current) in storage.state.processed_answer_keys
    assert answer_key(future) not in storage.state.processed_answer_keys
    assert storage.state.achievement_history_high_water_revlog_id == 500
    assert 600 not in storage.state.processed_revlog_ids

    # A later sync can insert a distinct answer for the same card with a lower
    # revlog ID. It is still new by stable answer identity and is credited once.
    late_lower_id = history_entry(
        100,
        card_id=past.card_id,
        answer_ms=1_500,
        scheduler_day=past_day,
        ordinal=2,
    )
    assert engine.equip_environment("scenery", "default")[0]
    rows.insert(1, late_lower_id)
    late_results = []
    repeated, _message = engine.reconcile_reward_history(
        result_collector=late_results,
        due_status=DueObligationStatus(),
        emit_feedback=False,
    )

    assert repeated
    assert len(late_results) == 1
    assert late_results[0].scheduler_day == past_day
    assert late_results[0].award.total_growth_units > 0
    assert late_results[0].award.scenery_growth_units == 0
    assert late_results[0].award.weather_growth_units == 100
    assert storage.state.watering_station_progress_by_day == {past_day: 0, current_day: 1}
    assert storage.state.watering_station_progress == 1
    assert not late_results[0].daily_completion_rewarded
    assert answer_key(late_lower_id) in storage.state.processed_answer_keys
    assert answer_key(past) != answer_key(late_lower_id)
    assert answer_key(future) not in storage.state.processed_answer_keys
    after_late_arrival = storage.state.to_dict()

    duplicate_results = []
    final, _message = engine.reconcile_reward_history(
        result_collector=duplicate_results,
        due_status=DueObligationStatus(),
        emit_feedback=False,
    )

    assert final
    assert duplicate_results == []
    assert storage.state.to_dict() == after_late_arrival


def test_suppressed_sync_restores_the_preexisting_stage_transition_queue() -> None:
    engine, storage = make_engine()
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = 100
    storage.state.progression_activation_ms = 100
    storage.state.garden_find_activation_ms = storage.now_ms + 100_000
    storage.state.plants[0].growth_points = 390
    storage.state.active_plant_periods = [
        ActivePlantPeriod(storage.day, "p1", 100)
    ]
    existing = StageTransition(
        "p2",
        "rose",
        "seed",
        "sprout",
        "Briar",
        "charge",
    )
    engine._pending_stage_transitions.append(existing)
    entry = HistoricalReviewEntry(
        revlog_id=storage.now_ms + 1_000,
        card_id=42,
        ease=3,
        interval=1,
        last_interval=0,
        factor=2_500,
        response_time_ms=500,
        review_type=1,
        answer_ms=storage.now_ms + 1_000,
        scheduler_day=storage.day,
        card_day_ordinal=1,
        answer_identity=f"v1|{storage.day}|42|1",
    )
    storage.load_eligible_review_history = lambda: HistoricalReviewSnapshot(
        entries=(entry,),
        high_water_revlog_id=entry.revlog_id,
        fingerprint="suppressed-stage-transition",
    )

    reconciled, _message = engine.reconcile_reward_history(emit_feedback=False)

    assert reconciled
    assert storage.state.plants[0].growth_points >= 400
    assert engine.peek_stage_transitions() == [existing]


def test_first_post_activation_answer_can_start_the_current_weekly_cycle():
    engine, storage = make_engine()
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = storage.now_ms
    storage.state.garden_find_activation_ms = storage.now_ms
    storage.state.daily_stats.reviewed = 1
    storage.state.streak_days = 7
    storage.state.last_active_day = storage.day
    storage.state.garden_find_daily_counts[storage.day] = 3
    storage.state.inventory["weather"].extend(["fireflies", "rainbow_sunshower"])
    storage.state.inventory["scenery"].extend([
        "rainbow_horizon", "halloween", "full_moon", "eclipse",
    ])
    storage.now_ms += 1_000

    answer(engine, storage)

    assert storage.state.currency_balance == 14
    assert storage.state.achievements["streak_7"].unlocked
    assert {
        tx.event_key for tx in storage.state.currency_transactions
    } == {
        f"daily_activity:{storage.day}",
        "achievement:streak_7",
    }


def test_progress_export_reports_growth_reconciliation_without_mutation():
    engine, storage = make_engine()
    storage.state.daily_stats.reviewed = 1
    storage.state.selected_weather = "breeze"
    answer(engine, storage)
    before = storage.state.to_dict()

    report = json.loads(engine.export_progress_summary())

    assert report["schema_version"] == STATE_VERSION
    assert report["growth_reconciliation"]["study_source_total"] == 10
    assert report["growth_reconciliation"]["study_growth_generated"] == 10
    assert report["growth_reconciliation"]["nurtured_by_plant"] == {"p1": 10}
    assert report["growth_reconciliation"]["passive_exact_fifths_by_plant"] == {
        "p2": 5,
    }
    assert report["plants"][1]["passive_growth_remainder_fifths"] == 0
    assert report["growth_charge_replay_ledger"]["healthy"] is True
    assert storage.state.to_dict() == before


def test_catalog_price_name_and_personality_tables_match_exact_species_contract():
    expected_prices = {
        species: 250 for species in CURRENT_CATALOG_SPECIES_ORDER
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
        "You need 250 more Garden Coins to buy Japanese Maple Seed."
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


def test_day_14_streak_grants_the_weekly_reward_once():
    engine, storage = make_engine()
    storage.state.streak_days = 13
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()
    engine._apply_streak_rewards(
        scheduler_day=storage.day,
        correlation_id="duplicate-day-14",
    )

    assert storage.state.streak_days == 14
    assert storage.state.currency_balance == 10
    assert [tx.event_key for tx in storage.state.currency_transactions] == [
        f"weekly_streak:{storage.day}",
    ]


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


def test_garden_rhythm_bonus_is_fractional_and_never_reduces_base():
    engine, storage = make_engine()
    storage.eligible_study_days = tuple(
        f"2026-08-{day:02d}" for day in range(1, 8)
    )
    storage.today_cards_completion_days = set(storage.eligible_study_days[:3])

    first = answer(engine, storage)
    second = answer(engine, storage)

    assert first.bonus_percent == second.bonus_percent == 4
    assert first.base_growth == second.base_growth == 10
    assert first.streak_growth_units == second.streak_growth_units == 40
    assert first.total_growth_units == second.total_growth_units == 1_040
    assert storage.state.plants[0].growth_units == 2_080


def test_growth_routes_full_to_active_and_passive_to_other_planted_plants():
    engine, storage = make_engine()
    answer(engine, storage)
    before = storage.state.plants[0].growth_points

    ok, _message = engine.set_active_plant("p2")
    assert ok
    answer(engine, storage)

    assert storage.state.plants[0].growth_points == before + 1
    assert storage.state.plants[1].growth_points > 0
    assert storage.state.daily_stats.plant_growth.keys() == {"p1", "p2"}


@pytest.mark.parametrize("planted_beds", range(1, 7))
def test_one_through_six_planted_beds_create_exact_ten_percent_lanes(
    planted_beds,
):
    engine, storage = make_engine()
    storage.state.plants = [
        Plant(
            f"p{index + 1}",
            CURRENT_CATALOG_SPECIES_ORDER[index],
            f"Plant {index + 1}",
            index,
        )
        for index in range(planted_beds)
    ]
    storage.state.active_plant_id = "p1"
    storage.state.active_plant_periods = [
        ActivePlantPeriod(storage.day, "p1", storage.day_start_ms)
    ]

    award = answer(engine, storage)

    assert award.total_growth_units == 1_000
    assert award.shared_growth_units == (planted_beds - 1) * 100
    assert award.applied_growth_units == 1_000 + award.shared_growth_units
    assert storage.state.plants[0].growth_units == 1_000
    assert all(
        plant.growth_units == 100 for plant in storage.state.plants[1:]
    )


def test_shared_growth_preserves_exact_hundredth_units_from_garden_rhythm() -> None:
    engine, storage = make_engine()
    storage.state.plants.extend(
        Plant(
            f"p{index + 1}",
            CURRENT_CATALOG_SPECIES_ORDER[index],
            f"Plant {index + 1}",
            index,
        )
        for index in range(2, 6)
    )
    storage.eligible_study_days = tuple(
        f"2026-08-{day:02d}" for day in range(1, 8)
    )
    storage.today_cards_completion_days = set(storage.eligible_study_days[:3])

    award = answer(engine, storage)

    assert award.bonus_percent == 4
    assert award.total_growth_units == 1_040
    assert award.shared_growth_units == 5 * 104
    assert all(
        (plant.growth_points, plant.growth_remainder_units) == (1, 4)
        for plant in storage.state.plants[1:]
    )


def test_full_bloom_shared_lane_routes_whole_lane_in_bed_order() -> None:
    engine, storage = make_engine()
    active, completed = storage.state.plants
    completed.growth_points = GROWTH_THRESHOLDS[-1]
    continuation = Plant("p3", "sunflower", "Sunny", 2)
    storage.state.plants.append(continuation)

    award = answer(engine, storage)

    assert award.total_growth_units == 1_000
    assert award.shared_growth_units == 200
    assert active.growth_units == 1_000
    assert completed.growth_units == GROWTH_THRESHOLDS[-1] * 100
    assert continuation.growth_units == 200


def test_garden_rhythm_uses_prior_seven_eligible_days_without_a_reset_cliff() -> None:
    engine, storage = make_engine()
    storage.eligible_study_days = (
        "2026-08-01",
        "2026-08-03",
        "2026-08-04",
        "2026-08-08",
        "2026-08-11",
        "2026-08-12",
        "2026-08-20",
    )
    storage.today_cards_completion_days = set(storage.eligible_study_days[:6])
    assert engine._garden_rhythm_percent_for_day("2026-08-21") == 10

    storage.today_cards_completion_days.remove("2026-08-01")
    assert engine._garden_rhythm_percent_for_day("2026-08-21") == 8

    first = answer(engine, storage)
    assert first.bonus_percent == 8
    assert storage.state.daily_economy_snapshot is not None
    assert storage.state.daily_economy_snapshot.garden_rhythm_percent == 8


@pytest.mark.parametrize("answer_number", [1, 101])
def test_historical_reviews_use_current_equipment_and_preserve_unknown_rhythm(answer_number) -> None:
    engine, storage = make_engine()
    storage.state.reward_state_initialized = True
    storage.state.reward_activation_ms = 1
    storage.state.progression_activation_ms = 1
    storage.state.garden_find_activation_ms = storage.now_ms + 100_000
    storage.state.inventory["garden_features"].append("wind_chime")
    storage.state.inventory["scenery"].append("spring")
    storage.state.loadout.active_garden_bonus_id = "wind_chime"
    storage.state.loadout.active_scenery_effect_id = "spring"
    storage.state.wind_chime_progress = 4
    plant = storage.state.plants[0]
    plant.fertilizer_card_batches = [CardEffectBatch(
        "fertilizer_quality", 200, 200, 200
    )]
    plant.booster_card_batches = [CardEffectBatch(
        "booster_potion", 500, 100, 100
    )]

    storage.now_ms += 1_000
    award = engine.register_review({
        "queue": 2,
        "ease": 3,
        "revlog_id": storage.now_ms,
        "answered_at_ms": storage.now_ms,
        "scheduler_day": "2026-08-07",
        "historical_sync": True,
        "day_answer_number": answer_number,
    })

    assert award.base_growth_units == 1_000
    assert award.fertilizer_growth_units == 200
    assert award.booster_growth_units == 500
    assert award.streak_growth_units == 0
    assert award.weather_growth_units == 100
    assert award.scenery_growth_units == (200 if answer_number == 1 else 0)
    assert award.total_growth_units == (2_000 if answer_number == 1 else 1_800)
    snapshot = storage.state.daily_economy_snapshot
    assert snapshot is not None
    assert snapshot.anki_day == "2026-08-07"
    assert snapshot.snapshot_source == "sync_fail_closed"
    assert snapshot.active_garden_bonus_id == "seedling_sign"
    assert snapshot.active_scenery_effect_id == "default"


def test_every_study_modifier_subset_is_applied_once_before_passive_fanout():
    modifier_bits = ("streak", "fertilizer", "booster", "weather", "scenery")
    expected_units = {
        "streak": 40,
        "fertilizer": 200,
        "booster": 500,
        "weather": 100,
        "scenery": 100,
    }
    for mask in range(1 << len(modifier_bits)):
        enabled = {
            name for index, name in enumerate(modifier_bits)
            if mask & (1 << index)
        }
        engine, storage = make_engine()
        nurtured, passive_one = storage.state.plants
        passive_two = Plant("p3", "lavender", "Violet", 2)
        storage.state.plants.append(passive_two)
        storage.state.daily_stats.reviewed = 1
        storage.eligible_study_days = tuple(
            f"2026-08-{day:02d}" for day in range(1, 8)
        )
        storage.today_cards_completion_days = (
            set(storage.eligible_study_days[:3])
            if "streak" in enabled else set()
        )
        if "fertilizer" in enabled:
            nurtured.fertilizer_card_batches = [CardEffectBatch(
                "fertilizer_quality", 200, 200, 200
            )]
        if "booster" in enabled:
            nurtured.booster_card_batches = [CardEffectBatch(
                "booster_potion", 500, 100, 100
            )]
        storage.state.selected_weather = "breeze" if "weather" in enabled else "sunny"
        storage.state.wind_chime_progress = 4 if "weather" in enabled else 0
        storage.state.loadout.active_scenery_effect_id = (
            "summer" if "scenery" in enabled else "default"
        )

        award = answer(engine, storage)
        final_units = 1_000 + sum(expected_units[name] for name in enabled)
        shared_units = final_units // 10

        assert award.total_growth_units == final_units
        assert award.applied_growth_units == final_units + shared_units * 2
        assert nurtured.growth_units == final_units
        assert passive_one.growth_units == passive_two.growth_units == shared_units
        assert [allocation.role for allocation in award.allocations] == [
            "nurtured", "passive", "passive",
        ]
        assert [allocation.requested_units for allocation in award.allocations] == [
            final_units, shared_units, shared_units,
        ]
        stats = storage.state.daily_stats
        assert stats.answer_growth_units == final_units
        assert stats.plant_applied_growth_units == {
            "p1": final_units,
            "p2": shared_units,
            "p3": shared_units,
        }
        assert stats.plant_shared_growth_units == {
            "p2": shared_units,
            "p3": shared_units,
        }


def test_shared_growth_units_survive_batch_restart_switch_and_duplicate_replay():
    engine, storage = make_engine()
    storage.state.daily_stats.reviewed = 1
    storage.state.selected_weather = "breeze"
    storage.state.inventory["weather"].append("breeze")
    first_id = storage.now_ms + 1_000

    first = answer(engine, storage, revlog_id=first_id)
    assert first.total_growth == 10
    assert storage.state.plants[1].growth_points == 1
    assert storage.state.plants[1].growth_remainder_units == 0

    restarted_storage = FakeStorage()
    restarted_storage.now_ms = storage.now_ms
    restarted_storage.state = GardenState.from_dict(storage.state.to_dict())
    restarted = GardenGameEngine(FakeConfig(), restarted_storage)
    second_id = first_id + 1_000
    third_id = first_id + 2_000
    gained = restarted.apply_same_day_reviews(
        [
            {"queue": 2, "ease": 3, "revlog_id": second_id, "answered_at_ms": second_id},
            {"queue": 2, "ease": 3, "revlog_id": third_id, "answered_at_ms": third_id},
        ],
        latest_revlog_id=third_id,
    )
    assert gained == 20
    assert restarted_storage.state.plants[1].growth_points == 3
    assert restarted_storage.state.plants[1].growth_remainder_units == 0

    restarted_storage.now_ms = third_id + 1_000
    assert restarted.set_active_plant("p2")[0]
    switched_id = restarted_storage.now_ms + 1_000
    answer(restarted, restarted_storage, revlog_id=switched_id)
    p1, p2 = restarted_storage.state.plants
    assert p1.growth_remainder_units == 0
    assert p2.growth_remainder_units == 0
    snapshot = restarted_storage.state.to_dict()
    duplicate = answer(restarted, restarted_storage, revlog_id=switched_id)
    assert duplicate.total_growth == 0
    assert restarted_storage.state.to_dict() == snapshot


def test_multiple_full_bloom_shares_route_as_whole_lanes_in_bed_order():
    engine, storage = make_engine()
    active, unfinished_one = storage.state.plants
    unfinished_two = Plant("p3", "lavender", "Violet", 2)
    full_one = Plant(
        "p4", "sunflower", "Sol", 3,
        growth_points=GROWTH_THRESHOLDS[-1],
    )
    full_two = Plant(
        "p5", "rose", "Briar", 4,
        growth_points=GROWTH_THRESHOLDS[-1],
    )
    storage.state.plants.extend((unfinished_two, full_one, full_two))

    award = answer(engine, storage)

    # Four other planted beds create four exact 10% lanes (400 units total).
    # Each Full Bloom lane skips completed beds and carries forward as one
    # whole lane. In this slot order both completed lanes reach the active bed.
    assert award.total_growth_units == 1_000
    assert award.shared_growth_units == 400
    assert active.growth_units == 1_200
    assert unfinished_one.growth_units == 100
    assert unfinished_two.growth_units == 100
    assert full_one.growth_units == full_two.growth_units == 3_500_000


def test_full_bloom_shares_return_to_active_when_it_is_the_only_unfinished_plant():
    engine, storage = make_engine()
    active, full_one = storage.state.plants
    full_one.growth_points = GROWTH_THRESHOLDS[-1]
    full_two = Plant(
        "p3", "lavender", "Violet", 2,
        growth_points=GROWTH_THRESHOLDS[-1],
    )
    storage.state.plants.append(full_two)

    award = answer(engine, storage)

    assert award.total_growth_units == 1_000
    assert award.shared_growth_units == 200
    assert active.growth_units == 1_200
    assert full_one.growth_units == full_two.growth_units == 3_500_000


def test_shared_growth_excludes_ineligible_plants_and_redirects_overflow_exactly():
    engine, storage = make_engine()
    nurtured, passive = storage.state.plants
    passive.growth_points = GROWTH_THRESHOLDS[-1] - 1
    unplanted = Plant("collection", "sunflower", "Sol", None)
    finished = Plant(
        "finished", "lavender", "Violet", 2,
        growth_points=GROWTH_THRESHOLDS[-1],
    )
    storage.state.plants.extend((unplanted, finished))
    storage.state.daily_stats.reviewed = 1
    storage.state.selected_weather = "breeze"
    storage.state.wind_chime_progress = 4

    award = answer(engine, storage)

    assert award.total_growth == 11
    assert passive.growth_points == GROWTH_THRESHOLDS[-1]
    assert passive.growth_remainder_units == 0
    assert unplanted.growth_points == 0
    assert finished.growth_points == GROWTH_THRESHOLDS[-1]
    assert {allocation.plant_id for allocation in award.allocations} == {"p1", "p2"}
    # The Full Bloom bed contributes a second exact 10% lane. That whole lane,
    # plus the other passive lane's over-cap remainder, routes forward in bed
    # order without losing any value.
    assert nurtured.growth_units == 1_220
    assert award.shared_growth_units == 220
    assert award.redirected_growth_units == 120

    capped_engine, capped_storage = make_engine()
    capped_storage.state.plants[0].growth_points = GROWTH_THRESHOLDS[-1] - 5
    capped = answer(capped_engine, capped_storage)
    assert capped.total_growth_units == 1_000
    assert capped_storage.state.plants[1].growth_points == 6
    assert capped_storage.state.plants[1].growth_remainder_units == 0


def test_simultaneous_nurtured_and_passive_stage_rewards_are_once_per_plant():
    engine, storage = make_engine()
    nurtured, passive = storage.state.plants
    nurtured.growth_points = 390
    passive.growth_points = 399
    revlog_id = storage.now_ms + 1_000

    answer(engine, storage, revlog_id=revlog_id)

    transitions = engine.peek_stage_transitions()
    assert [(item.plant_id, item.source, item.new_stage) for item in transitions] == [
        ("p1", "nurtured", "sprout"),
        ("p2", "shared_growth", "sprout"),
    ]
    assert [transaction.event_key for transaction in storage.state.currency_transactions] == [
        f"daily_activity:{storage.day}",
        "stage:p1:sprout",
        "stage:p2:sprout",
    ]
    assert [
        memory.memory_id
        for plant in storage.state.plants
        for memory in plant.memories
        if memory.kind == "stage"
    ] == ["stage:sprout", "stage:sprout"]
    state_after = storage.state.to_dict()
    answer(engine, storage, revlog_id=revlog_id)
    assert storage.state.to_dict() == state_after


@pytest.mark.parametrize("target_id", ["p1", "p2"], ids=["active", "non-active"])
@pytest.mark.parametrize(
    "charge_id",
    ["growth_charge_small", "growth_charge_standard", "growth_charge_grand"],
)
def test_growth_charge_quote_confirm_targets_one_plant_without_fanout_or_buffs(
    target_id,
    charge_id,
):
    engine, storage = make_engine()
    from ankigarden.balance_catalog import ACHIEVEMENT_TROPHIES
    for trophy in ACHIEVEMENT_TROPHIES:
        storage.state.achievements[str(trophy.source_achievement_id)].unlocked = True
        storage.state.trophy_activation_ms[str(trophy.cosmetic_id)] = storage.now_ms - 1
    target = engine.plant_story(target_id)
    other = next(plant for plant in storage.state.plants if plant.plant_id != target_id)
    target.growth_points = 390
    target.growth_remainder_units = 50
    target.fertilizer_card_batches = [
        CardEffectBatch("fertilizer_premium", 300, 400, 400)
    ]
    # Garden Rhythm is history-based in 2.2. Keep legacy streak achievements
    # out of this transaction-only assertion so their one-time inventory
    # grants cannot be mistaken for charge rollback.
    storage.state.streak_days = 0
    storage.state.selected_weather = "fireflies"
    storage.state.selected_background = "eclipse"
    storage.state.consumables[charge_id] = 1
    other_before = other.growth_points

    quote = engine.quote_growth_charge(charge_id, target_id)
    request = GrowthChargeRequest.from_quote(quote)
    outcome = engine.confirm_growth_charge(request)
    replay = engine.confirm_growth_charge(request)
    conflicting_reuse = engine.confirm_growth_charge(
        GrowthChargeRequest.from_quote(
            engine.quote_growth_charge(charge_id, other.plant_id),
            request_id=request.request_id,
        )
    )

    assert quote.status is GrowthChargeStatus.READY
    assert outcome.success and replay == outcome
    assert conflicting_reuse.status is GrowthChargeStatus.REQUEST_ID_CONFLICT
    assert outcome.growth_granted == quote.granted_growth
    assert target.growth_points == quote.projected_growth
    assert quote.current_growth_units == 39_050
    assert quote.projected_growth_units == 39_050 + quote.granted_growth * 100
    assert outcome.previous_growth_units == quote.current_growth_units
    assert outcome.resulting_growth_units == quote.projected_growth_units
    assert other.growth_points == other_before
    assert [transition.source for transition in engine.peek_stage_transitions()] == [
        "charge" for _stage in quote.completed_stages
    ]
    assert storage.state.consumables[charge_id] == 0
    assert storage.state.daily_stats.plant_charge_growth == {
        target_id: quote.granted_growth,
    }
    assert storage.state.daily_stats.study_growth_generated == 0
    assert len(storage.state.completed_growth_charge_requests) == 1


def test_growth_charge_rejects_stale_invalid_and_rolls_back_failed_save():
    engine, storage = make_engine()
    storage.state.consumables["growth_charge_small"] = 2
    quote = engine.quote_growth_charge("growth_charge_small", "p2")
    invalid_request = GrowthChargeRequest.from_quote(
        quote,
        request_id="not-a-valid-request-id",
    )
    assert (
        engine.confirm_growth_charge(invalid_request).status
        is GrowthChargeStatus.REQUEST_ID_CONFLICT
    )
    assert storage.state.plants[1].growth_points == 0
    assert storage.state.consumables["growth_charge_small"] == 2
    stale_inventory_request = GrowthChargeRequest.from_quote(quote)
    storage.state.consumables["growth_charge_small"] = 1
    stale_inventory = engine.confirm_growth_charge(stale_inventory_request)
    assert stale_inventory.status is GrowthChargeStatus.STALE_INVENTORY
    assert storage.state.plants[1].growth_points == 0

    target_quote = engine.quote_growth_charge("growth_charge_small", "p2")
    target_request = GrowthChargeRequest.from_quote(target_quote)
    storage.state.plants[1].slot_index = None
    invalid_target = engine.confirm_growth_charge(target_request)
    assert invalid_target.status is GrowthChargeStatus.TARGET_INVALID
    storage.state.plants[1].slot_index = 1

    growth_quote = engine.quote_growth_charge("growth_charge_small", "p2")
    growth_request = GrowthChargeRequest.from_quote(growth_quote)
    storage.state.plants[1].growth_points += 1
    stale_target = engine.confirm_growth_charge(growth_request)
    assert stale_target.status is GrowthChargeStatus.STALE_TARGET

    assert engine.quote_growth_charge(
        "growth_charge_small", "not-owned"
    ).status is GrowthChargeStatus.TARGET_INVALID

    rollback_quote = engine.quote_growth_charge("growth_charge_small", "p2")
    rollback_request = GrowthChargeRequest.from_quote(rollback_quote)
    state_before = storage.state.to_dict()
    transitions_before = engine.peek_stage_transitions()
    storage.fail_save = True
    failed = engine.confirm_growth_charge(rollback_request)
    assert failed.status is GrowthChargeStatus.PERSISTENCE_FAILURE
    assert storage.state.to_dict() == state_before
    assert engine.peek_stage_transitions() == transitions_before


def test_growth_charge_quote_exposes_authoritative_target_state() -> None:
    engine, storage = make_engine()
    storage.state.consumables["growth_charge_small"] = 2

    ready = engine.quote_growth_charge("growth_charge_small", "p2")
    assert ready.target_state is GrowthChargeTargetState.ELIGIBLE

    storage.state.plants[1].slot_index = None
    stored = engine.quote_growth_charge("growth_charge_small", "p2")
    assert stored.status is GrowthChargeStatus.TARGET_INVALID
    assert stored.target_state is GrowthChargeTargetState.STORED
    assert stored.quote_token != ready.quote_token

    storage.state.plants[1].slot_index = 1
    storage.state.plants[1].growth_points = GROWTH_THRESHOLDS[-1]
    fully_grown = engine.quote_growth_charge("growth_charge_small", "p2")
    assert fully_grown.status is GrowthChargeStatus.TARGET_INVALID
    assert fully_grown.target_state is GrowthChargeTargetState.FULLY_GROWN
    assert fully_grown.quote_token != stored.quote_token

    unavailable = engine.quote_growth_charge(
        "growth_charge_small",
        "not-owned",
    )
    assert unavailable.status is GrowthChargeStatus.TARGET_INVALID
    assert unavailable.target_state is GrowthChargeTargetState.UNAVAILABLE


def test_growth_charge_routes_its_full_value_before_consuming_the_item():
    engine, storage = make_engine()
    target, continuation = storage.state.plants
    target.growth_points = 34_997
    storage.state.consumables["growth_charge_standard"] = 1

    quote = engine.quote_growth_charge("growth_charge_standard", target.plant_id)
    outcome = engine.confirm_growth_charge(GrowthChargeRequest.from_quote(quote))

    assert quote.requested_growth == quote.granted_growth == 500
    assert outcome.success and outcome.growth_granted == 500
    assert target.fully_grown
    assert continuation.growth_points == 497
    assert storage.state.stored_growth_units == 0
    assert storage.state.active_plant_id == continuation.plant_id
    assert storage.state.daily_stats.plant_charge_growth == {
        target.plant_id: 3,
        continuation.plant_id: 497,
    }
    assert storage.state.consumables["growth_charge_standard"] == 0
    assert storage.state.consumables["growth_charge_small"] == 1


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
    assert GROWTH_THRESHOLDS == [0, 400, 2_000, 6_000, 15_000, 35_000]
    plant = Plant("p", "lavender", "Violet", 0, growth_points=5_999)
    assert plant.growth_stage == "young"
    plant.growth_points = 6_000
    assert plant.growth_stage == "mature"


def test_stage_completion_uses_the_final_checkpoint_split_and_is_durable():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 390

    answer(engine, storage)

    assert plant.growth_stage == "sprout"
    assert engine.peek_stage_transitions()[0].new_stage == "sprout"
    assert engine.peek_stage_transitions()[0].source == "nurtured"
    assert storage.state.currency_balance == 6
    assert any(
        tx.event_key == "stage:p1:sprout" and tx.delta == 2
        for tx in storage.state.currency_transactions
    )
    assert any(memory.memory_id == "stage:sprout" for memory in plant.memories)
    assert any(
        event.message == "Bonsai reached sprout. +2 Garden Coins"
        for event in engine.peek_feedback()
    )


def test_day_7_achievement_and_weekly_reward_are_one_integrated_payout() -> None:
    engine, storage = make_engine()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.streak_days == 7
    assert storage.state.currency_balance == 10
    assert storage.state.achievements["streak_7"].unlocked
    assert "achievement:streak_7" in storage.state.applied_reward_event_keys
    assert f"weekly_streak:{storage.day}" in storage.state.applied_reward_event_keys
    assert [tx.delta for tx in storage.state.currency_transactions] == [10]


def test_twenty_five_fifty_and_seventy_five_percent_feedback_uses_stage_interval():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 99
    answer(engine, storage)
    assert any("25%" in event.message for event in engine.peek_feedback())
    plant.growth_points = 199
    answer(engine, storage)
    assert any("50%" in event.message for event in engine.peek_feedback())
    plant.growth_points = 299
    answer(engine, storage)
    assert any("75%" in event.message for event in engine.peek_feedback())


@pytest.mark.parametrize(
    ("before", "event_key", "reward"),
    [
        (99, "stage_checkpoint:p1:sprout:25", 1),
        (199, "stage_checkpoint:p1:sprout:50", 1),
        (299, "stage_checkpoint:p1:sprout:75", 1),
        (399, "stage:p1:sprout", 2),
    ],
)
def test_seed_stage_coin_pool_is_split_across_checkpoints_and_completion(
    before,
    event_key,
    reward,
):
    engine, storage = make_engine()
    storage.state.plants[0].growth_points = before

    answer(engine, storage)

    transaction = next(
        item for item in storage.state.currency_transactions
        if item.event_key == event_key
    )
    assert transaction.delta == reward


def test_one_large_charge_grants_every_crossed_checkpoint_once_in_order():
    engine, storage = make_engine()
    storage.state.consumables["growth_charge_grand"] = 1

    assert engine.use_growth_charge("growth_charge_grand")[0]

    milestone_keys = [
        item.event_key for item in storage.state.currency_transactions
        if item.event_key.startswith("stage")
    ]
    assert milestone_keys == [
        "stage_checkpoint:p1:sprout:25",
        "stage_checkpoint:p1:sprout:50",
        "stage_checkpoint:p1:sprout:75",
        "stage:p1:sprout",
        "stage_checkpoint:p1:young:25",
        "stage_checkpoint:p1:young:50",
        "stage_checkpoint:p1:young:75",
        "stage:p1:young",
    ]
    assert sum(
        item.delta for item in storage.state.currency_transactions
        if item.event_key in milestone_keys
    ) == 15


def test_full_bloom_grants_the_completion_package_once():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.growth_points = 34_990
    event_id = storage.now_ms + 1_000

    answer(engine, storage, revlog_id=event_id)
    inventory_after = storage.state.consumables["growth_charge_small"]
    duplicate = answer(engine, storage, revlog_id=event_id)

    assert plant.fully_grown
    assert plant.completed_on == storage.day
    assert plant.completed_at_ms == event_id
    assert plant.completion_cards >= 1
    assert plant.completion_active_days >= 1
    assert plant.full_bloom_reward_claimed
    assert inventory_after == 1
    assert storage.state.consumables["growth_charge_small"] == inventory_after
    assert duplicate.total_growth_units == 0
    assert "full_bloom:p1" in storage.state.applied_reward_event_keys
    full_bloom_coin_awards = [
        transaction
        for transaction in storage.state.currency_transactions
        if transaction.event_key == "stage:p1:rare"
    ]
    assert len(full_bloom_coin_awards) == 1
    assert full_bloom_coin_awards[0].source == "plant_milestone"
    assert full_bloom_coin_awards[0].source_id == plant.plant_id
    assert full_bloom_coin_awards[0].included_in_total is True


def test_exact_fractional_growth_is_conserved_when_every_plant_fills():
    engine, storage = make_engine()
    active, shared = storage.state.plants
    active.growth_points = 34_995
    shared.growth_points = 34_998
    storage.state.daily_stats.reviewed = 1

    award = answer(engine, storage)

    assert award.total_growth_units == 1_000
    assert award.applied_growth_units == 700
    assert award.shared_growth_units == 0
    assert award.stored_growth_units == 400
    assert storage.state.stored_growth_units == 400
    assert active.fully_grown and shared.fully_grown
    assert award.applied_growth_units + award.stored_growth_units == (
        award.total_growth_units + award.total_growth_units // 10
    )


def test_all_full_bloom_beds_keep_shared_lanes_for_endgame_storage():
    engine, storage = make_engine()
    storage.state.plants = [
        Plant(
            f"p{index + 1}",
            CURRENT_CATALOG_SPECIES_ORDER[index],
            f"Plant {index + 1}",
            index,
            growth_points=GROWTH_THRESHOLDS[-1],
        )
        for index in range(6)
    ]
    storage.state.active_plant_id = None
    storage.state.active_plant_periods = [
        ActivePlantPeriod(storage.day, None, storage.day_start_ms)
    ]

    award = answer(engine, storage)

    assert award.total_growth_units == 1_000
    assert award.applied_growth_units == 0
    assert award.stored_growth_units == 1_500
    assert storage.state.stored_growth_balance_units == 1_500


def test_full_bloom_conserves_growth_and_auto_continues_to_the_next_plant():
    engine, storage = make_engine()
    completed, next_plant = storage.state.plants
    completed.growth_points = 34_995

    award = answer(engine, storage)
    first_event_ms = storage.now_ms
    continued = answer(engine, storage)

    assert completed.growth_points == 35_000
    assert award.total_growth_units == 1_000
    assert award.applied_growth_units == 1_100
    assert award.redirected_growth_units == 500
    assert award.shared_growth_units == 100
    assert award.stored_growth_units == 0
    # Once the first plant reaches Full Bloom, its 10% share continues and is
    # redistributed to the only plant still growing on the second card.
    assert next_plant.growth_points == 17
    assert storage.state.active_plant_id == next_plant.plant_id
    assert storage.state.active_plant_periods[-1] == ActivePlantPeriod(
        storage.day, next_plant.plant_id, first_event_ms
    )
    assert continued.plant_id == next_plant.plant_id
    assert continued.total_growth_units == 1_000


def test_no_target_reserve_survives_restart_and_target_selection_without_spending(
    tmp_path,
):
    storage = FakeStorage()
    storage.state.plants[0].growth_points = 35_000
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
    assert award.total_growth_units == 1_000
    assert award.applied_growth_units == 0
    assert award.stored_growth_units == 1_000
    assert unfinished.growth_points == before
    assert storage.state.stored_growth_units == 1_000
    assert award.paused_reason == (
        "No plant is selected. This card’s Growth is being stored."
    )

    assert engine.plant_from_collection(unfinished.plant_id, 0)[0]
    assert engine.set_active_plant(unfinished.plant_id)[0]
    assert unfinished.growth_points == before
    assert storage.state.stored_growth_units == 1_000

    next_award = answer(engine, storage)
    assert next_award.applied_growth_units == 1_000
    assert unfinished.growth_points == before + 10
    assert storage.state.stored_growth_units == 1_000


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


def test_todays_cards_completion_is_verified_live_and_claimed_once():
    engine, storage = make_engine()
    assert not engine.evaluate_today_cards(DueObligationStatus())[0]
    assert engine.observe_due_start(DueObligationStatus(review_count=2))
    assert storage.state.daily_completion.status == "in_progress"
    assert storage.state.daily_completion.starting_required_cards == 2
    answer(engine, storage)
    assert not engine.evaluate_today_cards(
        DueObligationStatus(review_count=1),
        record_completed_delta=True,
    )[0]

    answer(engine, storage)
    ok, message = engine.evaluate_today_cards(
        DueObligationStatus(),
        record_completed_delta=True,
    )
    assert ok
    assert "today’s cards" in message.lower()
    assert "all clear" not in message.lower()
    assert "required card" not in message.lower()
    assert storage.state.daily_stats.completed_due_cards
    assert storage.state.daily_completion.status == "complete"
    assert storage.state.daily_completion.reward_claimed
    balance = storage.state.currency_balance
    growth = storage.state.plants[0].growth_units
    storage.state.inventory["garden_features"].append("harvest_bell")
    assert engine.equip_environment("garden_feature", "harvest_bell")[0]
    assert not engine.evaluate_today_cards(DueObligationStatus())[0]
    assert storage.state.currency_balance == balance
    assert storage.state.plants[0].growth_units == growth
    assert not engine.evaluate_all_due(
        DueObligationStatus(review_count=9, learning_count=4)
    )[0]
    assert storage.state.daily_stats.completed_due_cards
    assert storage.state.daily_completion.reward_claimed
    assert storage.state.daily_completion.status == "in_progress"
    assert storage.state.daily_completion.remaining_required_reviews == 9
    assert storage.state.daily_completion.remaining_learning_steps == 4
    assert storage.state.currency_balance == balance


def test_garden_cycle_cadence_is_visible_nonconsecutive_and_idempotent():
    engine, storage = make_engine()
    initial_day = datetime.fromisoformat(storage.day)
    for offset in (0, 1, 3, 4, 7):
        if offset:
            next_day = initial_day + timedelta(days=offset)
            storage.day = next_day.date().isoformat()
            storage.day_start_ms += 86_400_000
            storage.now_ms = storage.day_start_ms + 1_000
            engine.rollover_if_needed()
        assert engine.observe_due_start(DueObligationStatus(review_count=1))
        answer(engine, storage)
        ok, _message = engine.evaluate_today_cards(
            DueObligationStatus(),
            record_completed_delta=True,
        )
        assert ok
        balance = storage.state.currency_balance
        assert not engine.evaluate_today_cards(DueObligationStatus())[0]
        assert storage.state.currency_balance == balance

    by_source: dict[str, int] = {}
    for transaction in storage.state.currency_transactions:
        by_source[transaction.source] = (
            by_source.get(transaction.source, 0) + transaction.delta
        )
    assert by_source["first_eligible_answer"] == 5 * 4
    assert by_source["todays_cards"] == 5 * 8
    assert by_source["completion_cycle_5"] == 30
    assert storage.state.garden_cycle_remainder == 0
    cycle = next(
        receipt for receipt in storage.state.recent_reward_receipts
        if receipt.source == "completion_cycle_5"
    )
    assert (cycle.title, cycle.description, cycle.amount) == (
        "Garden Cycle complete",
        "5 completed review days",
        30,
    )

    next_day = initial_day + timedelta(days=9)
    storage.day = next_day.date().isoformat()
    storage.day_start_ms += 86_400_000
    storage.now_ms = storage.day_start_ms + 1_000
    engine.rollover_if_needed()
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage)
    assert engine.evaluate_today_cards(
        DueObligationStatus(), record_completed_delta=True
    )[0]
    assert storage.state.garden_cycle_remainder == 1
    assert sum(
        transaction.delta
        for transaction in storage.state.currency_transactions
        if transaction.source == "completion_cycle_5"
    ) == 30


def test_no_due_baseline_remains_not_eligible_on_later_live_refresh():
    engine, storage = make_engine()

    assert not engine.observe_due_start(DueObligationStatus())
    completion = engine.today_cards_status(DueObligationStatus())

    assert storage.state.daily_stats.due_started_with_cards is False
    assert completion.status == "not_eligible"
    assert completion.reward_claimed is False


def test_today_cards_projection_keeps_answer_activity_out_of_obligation_progress():
    engine, storage = make_engine()
    storage.reviews_today = lambda: 176
    status = DueObligationStatus(new_count=1, review_count=18)

    assert engine.observe_due_start(status)
    completion = engine.today_cards_status(status)

    # Revlog activity remains available for other surfaces, but it is not the
    # Today’s Cards completion numerator or denominator.
    assert completion.cards_completed_today == 176
    assert completion.starting_required_cards_completed == 0
    assert completion.starting_required_cards == 19
    assert completion.remaining_new_cards == 1
    assert completion.remaining_required_reviews == 18


def test_today_cards_obligation_stays_open_through_new_and_relearning_steps():
    engine, storage = make_engine()
    initial = DueObligationStatus(new_count=1, review_count=18)
    storage.reviews_today = lambda: 0
    assert engine.observe_due_start(initial)

    # Answering the New card can move it into Learn without completing the
    # scheduler obligation. Repeated answers remain raw activity only.
    storage.reviews_today = lambda: 1
    learning = engine.today_cards_status(DueObligationStatus(
        review_count=18,
        learning_count=1,
        future_learning_count=1,
    ))
    assert learning.starting_required_cards == 19
    assert learning.starting_required_cards_completed == 0
    assert learning.cards_completed_today == 1

    storage.reviews_today = lambda: 2
    repeated = engine.today_cards_status(DueObligationStatus(
        review_count=18,
        learning_count=1,
        future_learning_count=1,
    ))
    assert repeated.starting_required_cards == 19
    assert repeated.starting_required_cards_completed == 0
    assert repeated.cards_completed_today == 2

    # A read-only queue shrink may be bury/suspend or a limit change. It
    # rebases the denominator instead of claiming completed work.
    reconciled = engine.today_cards_status(DueObligationStatus(review_count=18))
    assert reconciled.starting_required_cards == 18
    assert reconciled.starting_required_cards_completed == 0
    assert reconciled.cards_completed_today == 2


def test_committed_today_cards_delta_advances_obligation_completion():
    engine, storage = make_engine()
    assert engine.observe_due_start(
        DueObligationStatus(new_count=1, review_count=18)
    )
    storage.reviews_today = lambda: 1

    ok, _message = engine.evaluate_today_cards(
        DueObligationStatus(review_count=18),
        record_completed_delta=True,
    )

    assert not ok
    completion = storage.state.daily_completion
    assert completion.starting_required_cards == 19
    assert completion.starting_required_cards_completed == 1
    assert completion.cards_completed_today == 1


def test_committed_answer_caps_completion_when_siblings_are_auto_buried():
    engine, storage = make_engine()
    assert engine.observe_due_start(DueObligationStatus(review_count=5))
    storage.reviews_today = lambda: 1

    ok, _message = engine.evaluate_today_cards(
        DueObligationStatus(review_count=2),
        record_completed_delta=True,
    )

    assert not ok
    completion = storage.state.daily_completion
    assert completion.starting_required_cards_completed == 1
    assert completion.remaining_required_reviews == 2
    assert completion.unresolved_obligation_disappearances == 2
    assert completion.status == "unavailable"
    # One committed answer completed one obligation; the two unavailable
    # siblings rebase out of the denominator instead of inflating progress.
    assert completion.starting_required_cards == 3


def test_committed_answer_cannot_complete_when_a_sibling_is_auto_buried():
    engine, storage = make_engine()
    assert engine.observe_due_start(DueObligationStatus(review_count=2))
    answer(engine, storage)
    balance = storage.state.currency_balance

    ok, message = engine.evaluate_today_cards(
        DueObligationStatus(
            committed_card_ids=(101,),
            card_transitions=((101, "completed"),),
            buried_sibling_card_ids=(202,),
        ),
        record_completed_delta=True,
    )

    assert not ok
    assert "unavailable" in message.lower()
    completion = storage.state.daily_completion
    assert completion.status == "unavailable"
    assert completion.unavailable_reason == "auto_buried_sibling_obligation"
    assert completion.starting_required_cards_completed == 1
    assert completion.starting_required_cards == 1
    assert completion.unresolved_obligation_disappearances == 1
    assert completion.starting_required_cards == (
        completion.starting_required_cards_completed
        + completion.remaining_new_cards
        + completion.remaining_required_reviews
        + completion.remaining_learning_steps
        + completion.future_learning_steps_before_cutoff
    )
    assert completion.reward_claimed is False
    assert storage.state.daily_stats.completed_due_cards is False
    assert storage.state.currency_balance == balance

    # A later read-only empty snapshot cannot turn the ambiguous transition
    # into a completed day.
    refreshed = engine.today_cards_status(DueObligationStatus())
    assert refreshed.status == "unavailable"
    assert refreshed.unresolved_obligation_disappearances == 1


def test_terminal_completion_fails_closed_when_committed_identity_is_unavailable():
    engine, storage = make_engine()
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage)

    ok, _message = engine.evaluate_today_cards(
        DueObligationStatus(committed_card_ids=(101,)),
        record_completed_delta=True,
    )

    assert not ok
    completion = storage.state.daily_completion
    assert completion.status == "unavailable"
    assert completion.starting_required_cards_completed == 0
    assert completion.unresolved_obligation_disappearances == 1
    assert completion.reward_claimed is False


def test_read_only_empty_queue_cannot_award_today_cards_completion():
    engine, storage = make_engine()
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    answer(engine, storage)
    balance = storage.state.currency_balance

    ok, message = engine.evaluate_today_cards(DueObligationStatus())

    assert not ok
    assert "unavailable" in message.lower()
    completion = storage.state.daily_completion
    assert completion.status == "unavailable"
    assert completion.starting_required_cards == 0
    assert completion.starting_required_cards_completed == 0
    assert completion.reward_claimed is False
    assert storage.state.daily_stats.completed_due_cards is False
    assert storage.state.currency_balance == balance


def test_committed_answer_result_groups_final_due_rewards_under_answer_identity():
    engine, storage = make_engine()
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    revlog_id = storage.now_ms + 1_000
    result = engine.commit_reviewer_answer(
        {
            "queue": 2,
            "ease": 3,
            "revlog_id": revlog_id,
            "answered_at_ms": revlog_id,
            "scheduler_day": storage.day,
            "origin": "local",
        },
        latest_revlog_id=revlog_id,
        due_status=DueObligationStatus(),
    )

    assert result is not None
    assert result.event_id == result.correlation_id
    assert result.event_id.startswith("answer:")
    assert result.origin == "local"
    assert result.daily_completion_rewarded
    assert result.plants_before != result.plants_after
    assert result.stored_growth_delta_units == 0
    assert result.reward_receipts
    assert {
        receipt.correlation_id for receipt in result.reward_receipts
    } == {result.correlation_id}
    assert any(
        transaction.source == "todays_cards"
        for transaction in result.currency_transactions
    )


def test_committed_answer_result_propagates_answer_correlation_to_checkpoint():
    engine, storage = make_engine()
    plant = engine.active_plant()
    assert plant is not None
    first_stage_end = GROWTH_THRESHOLDS[1]
    plant.growth_points = math.ceil(first_stage_end * 0.25) - 5
    revlog_id = storage.now_ms + 1_000

    result = engine.commit_reviewer_answer(
        {
            "queue": 2,
            "ease": 3,
            "revlog_id": revlog_id,
            "answered_at_ms": revlog_id,
            "scheduler_day": storage.day,
        },
        latest_revlog_id=revlog_id,
        due_status=DueObligationStatus(review_count=1),
    )

    assert result is not None
    checkpoint_transactions = tuple(
        transaction
        for transaction in result.currency_transactions
        if transaction.event_key.startswith("stage_checkpoint:")
    )
    assert checkpoint_transactions
    assert {
        transaction.correlation_id for transaction in checkpoint_transactions
    } == {result.correlation_id}
    assert {
        receipt.correlation_id
        for receipt in result.reward_receipts
        if receipt.event_key.startswith("stage_checkpoint:")
    } == {result.correlation_id}
    assert {
        event.correlation_id
        for event in engine.peek_feedback()
        if event.event_id.startswith("stage_checkpoint:")
    } == {result.correlation_id}


def test_todays_cards_check_persists_scheduler_rollover_even_when_not_earned():
    engine, storage = make_engine()
    storage.state.daily_stats.reviewed = 1
    storage.day = "2026-08-09"
    storage.now_ms += 86_400_000
    saves_before = storage.save_count

    ok, _message = engine.evaluate_today_cards(DueObligationStatus(review_count=2))

    assert not ok
    assert storage.state.daily_stats.day == "2026-08-09"
    assert storage.state.daily_completion.scheduler_day == "2026-08-09"
    assert storage.save_count > saves_before


def test_progress_estimates_recalculate_from_the_effective_growth_rate():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    plant = storage.state.plants[0]
    plant.growth_points = 500
    assert engine.progress_estimates(plant) == math.ceil((2_000 - 500) / 10)
    plant.fertilizer_card_batches = [CardEffectBatch(
        "fertilizer_quality", 200, 200, 200
    )]
    assert engine.progress_estimates(plant) == math.ceil((2_000 - 500) / 12)


def test_sync_reward_baseline_identifies_active_boost_items():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    plant = storage.state.plants[0]
    plant.fertilizer_card_batches = [
        CardEffectBatch("fertilizer_quality", 200, 200, 90)
    ]
    plant.booster_card_batches = [
        CardEffectBatch("booster_potion", 500, 100, 12)
    ]
    storage.state.garden_project.contributed_growth_units = 250

    baseline = engine.sync_reward_baseline()

    assert baseline["fertilizer_item_id"] == "fertilizer_quality"
    assert baseline["fertilizer_cards_remaining"] == 90
    assert baseline["fertilizer_remaining_seconds"] == 0
    assert baseline["booster_item_id"] == "booster_potion"
    assert baseline["booster_cards_remaining"] == 12
    assert baseline["landmark_growth_units"] == 250
    assert baseline["total_growth_units"] == (
        sum(item.growth_units for item in storage.state.plants)
        + storage.state.stored_growth_units
        + 250
    )


def test_next_review_growth_projection_is_nonmutating_and_matches_the_award():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    plant = storage.state.plants[0]
    storage.state.daily_stats.reviewed = 1
    storage.state.streak_days = 7
    storage.state.selected_weather = "breeze"
    storage.state.selected_background = "spring"
    plant.fertilizer_card_batches = [
        CardEffectBatch("fertilizer_quality", 200, 200, 200)
    ]
    before_state = storage.state.to_dict()
    before_saves = storage.save_count
    next_event_seconds = (storage.now_ms + 1_000) / 1_000

    projected = engine.project_review_growth(plant, now=next_event_seconds)

    assert storage.state.to_dict() == before_state
    assert storage.save_count == before_saves
    awarded = answer(engine, storage)
    assert awarded == projected


def test_fertilizer_dose_is_card_counted_and_projection_does_not_consume_it():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    storage.state.consumables["fertilizer_quality"] = 1
    ok, message = engine.use_fertilizer_item("p1", tier="quality")
    plant = storage.state.plants[0]

    assert ok
    assert "card" in message.lower()
    assert "200 eligible cards" in message.lower()
    assert [
        (batch.effect_id, batch.total_cards, batch.remaining_cards)
        for batch in plant.fertilizer_card_batches
    ] == [("fertilizer_quality", 200, 200)]
    assert plant.fertilizer_card_queue == []
    before = storage.state.to_dict()
    projected = engine.project_review_growth(plant)
    assert projected.fertilizer_growth_units == 200
    assert storage.state.to_dict() == before

    award = answer(engine, storage)

    assert award.fertilizer_growth_units == 200
    assert plant.fertilizer_card_batches[0].remaining_cards == 199
    assert storage.state.plants[1].fertilizer is None

    after_elapsed_time = engine.project_review_growth(
        plant,
        now=storage.now_ms / 1_000 + 86_400,
    )
    assert after_elapsed_time.fertilizer_growth_units == 200


def test_same_fertilizer_extends_while_a_different_tier_queues_without_loss():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    storage.state.consumables.update({
        "fertilizer_basic": 2,
        "fertilizer_quality": 1,
    })

    assert engine.use_fertilizer_item("p1", tier="basic")[0]
    assert engine.use_fertilizer_item("p1", tier="basic")[0]
    ok, message = engine.use_fertilizer_item("p1", tier="quality")
    plant = storage.state.plants[0]

    assert ok
    assert "replace" not in message.lower()
    assert "discard" not in message.lower()
    assert "queued" in message.lower()
    assert [
        (batch.effect_id, batch.total_cards, batch.remaining_cards)
        for batch in plant.fertilizer_card_batches
    ] == [
        ("fertilizer_basic", 100, 100),
        ("fertilizer_basic", 100, 100),
    ]
    assert [
        (batch.effect_id, batch.total_cards, batch.remaining_cards)
        for batch in plant.fertilizer_card_queue
    ] == [("fertilizer_quality", 200, 200)]


def test_fertilizer_fifo_survives_restart_and_is_independent_of_elapsed_time() -> None:
    engine, storage = make_engine()
    storage.state.consumables.update({
        "fertilizer_basic": 2,
        "fertilizer_quality": 1,
    })
    assert engine.use_fertilizer_item("p1", tier="basic")[0]
    assert engine.use_fertilizer_item("p1", tier="basic")[0]
    assert engine.use_fertilizer_item("p1", tier="quality")[0]

    restarted_storage = FakeStorage()
    restarted_storage.state = GardenState.from_dict(storage.state.to_dict())
    restarted_storage.now_ms = storage.now_ms + 30 * 86_400_000
    restarted = GardenGameEngine(FakeConfig(), restarted_storage)
    plant = restarted_storage.state.plants[0]

    first = answer(restarted, restarted_storage)
    assert first.fertilizer_growth_units == 100
    assert plant.fertilizer_card_batches[0].remaining_cards == 99
    for _ in range(199):
        award = answer(restarted, restarted_storage)
        assert award.fertilizer_growth_units == 100
    assert [batch.effect_id for batch in plant.fertilizer_card_batches] == [
        "fertilizer_quality"
    ]
    assert plant.fertilizer_card_queue == []
    quality = answer(restarted, restarted_storage)
    assert quality.fertilizer_growth_units == 200
    assert plant.fertilizer_card_batches[0].remaining_cards == 199


def test_booster_and_fertilizer_concurrently_consume_one_committed_card() -> None:
    engine, storage = make_engine()
    storage.state.consumables["fertilizer_quality"] = 1
    storage.state.consumables["booster_potion"] = 1
    assert engine.use_fertilizer_item("p1", tier="quality")[0]
    assert engine.use_booster_potion("p1")[0]

    award = answer(engine, storage)
    plant = storage.state.plants[0]

    assert award.base_growth_units == 1_000
    assert award.fertilizer_growth_units == 200
    assert award.booster_growth_units == 500
    assert award.total_growth_units == 1_700
    assert plant.fertilizer_card_batches[0].remaining_cards == 199
    assert plant.booster_card_batches[0].remaining_cards == 99


def test_fertilizer_queue_changes_tier_only_when_the_previous_cards_are_used():
    engine, storage = make_engine()
    plant = storage.state.plants[0]
    plant.fertilizer_card_batches = [
        CardEffectBatch("fertilizer_basic", 100, 1, 1)
    ]
    plant.fertilizer_card_queue = [
        CardEffectBatch("fertilizer_quality", 200, 200, 200)
    ]

    final_basic = answer(engine, storage)
    first_quality = answer(engine, storage)

    assert final_basic.fertilizer_growth_units == 100
    assert first_quality.fertilizer_growth_units == 200
    assert [batch.effect_id for batch in plant.fertilizer_card_batches] == [
        "fertilizer_quality"
    ]
    assert plant.fertilizer_card_batches[0].remaining_cards == 199
    assert plant.fertilizer_card_queue == []


def test_booster_count_pauses_without_a_target_and_resumes_when_growth_applies():
    engine, storage = make_engine()
    storage.state.consumables["booster_potion"] = 1
    assert engine.use_booster_potion()[0]
    plant = storage.state.plants[0]
    assert plant.booster_card_batches[0].remaining_cards == 100

    assert engine.set_active_plant(None)[0]
    stored_award = answer(engine, storage)
    assert stored_award.booster_growth_units == 0
    assert plant.booster_card_batches[0].remaining_cards == 100
    assert storage.state.stored_growth_units == 1_000

    assert engine.set_active_plant("p1")[0]
    resumed = answer(engine, storage)
    assert resumed.booster_growth_units == 500
    assert plant.booster_card_batches[0].remaining_cards == 99


@pytest.mark.parametrize("hourglass,moon", [(False, False), (True, False), (False, True), (True, True)])
def test_booster_combines_owned_extensions_for_new_doses(hourglass, moon):
    engine, storage = make_engine()
    state = storage.state
    state.inventory["garden_features"] = ["seedling_sign"] + (["herbalist_hourglass"] if hourglass else [])
    state.inventory["scenery"] = ["default"] + (["full_moon"] if moon else [])
    state.loadout.display_decoration_id = "seedling_sign"
    state.loadout.display_scenery_id = "default"
    state.consumables["booster_potion"] = 2
    expected = 100 + 25 * (hourglass + moon)
    assert engine.consumable_use_projection("booster_potion").cards_added == expected
    assert engine.use_booster_potion()[0]
    batch = state.plants[0].booster_card_batches[0]
    assert batch.total_cards == batch.remaining_cards == expected
    # Buying or equipping later cannot rewrite an existing dose.
    if "herbalist_hourglass" not in state.inventory["garden_features"]:
        state.inventory["garden_features"].append("herbalist_hourglass")
    if "full_moon" not in state.inventory["scenery"]:
        state.inventory["scenery"].append("full_moon")
    assert engine.equip_environment("garden_feature", "herbalist_hourglass")[0]
    assert engine.equip_environment("scenery", "full_moon")[0]
    assert engine.use_booster_potion()[0]
    restored = GardenState.from_dict(state.to_dict())
    assert [batch.total_cards for batch in restored.plants[0].booster_card_batches] == [expected, 150]


def test_equipment_controls_artwork_and_next_reward_without_rewriting_daily_rhythm() -> None:
    engine, storage = make_engine()
    storage.state.inventory["scenery"].extend(["spring", "summer"])
    assert engine.equip_environment("scenery", "spring")[0]
    first = answer(engine, storage)
    snapshot = storage.state.daily_economy_snapshot
    assert first.scenery_growth == 2
    assert engine.display_scenery("summer")[0]
    assert storage.state.selected_background == "summer"
    assert answer(engine, storage).scenery_growth == 1
    assert storage.state.daily_economy_snapshot == snapshot
    before = storage.state.to_dict()
    storage.fail_save = True
    assert not engine.equip_environment("scenery", "spring")[0]
    assert storage.state.to_dict() == before
    storage.fail_save = False
    assert engine.equip_environment("scenery", "default")[0]
    assert answer(engine, storage).scenery_growth == 0
    assert engine.equip_environment("scenery", "default")[0]
    assert storage.state.daily_economy_snapshot == snapshot


def test_full_bloom_transfers_remaining_card_fertilizer_and_booster():
    engine, storage = make_engine()
    completed, continuation = storage.state.plants
    completed.growth_points = 34_990
    completed.fertilizer_card_batches = [CardEffectBatch(
        "fertilizer_basic", 100, 30, 30, source_event_key="fertilizer-transfer"
    )]
    completed.booster_card_batches = [CardEffectBatch(
        "booster_potion", 500, 30, 30, source_event_key="booster-transfer"
    )]

    award = answer(engine, storage)

    assert award.fertilizer_growth_units == 100
    assert award.booster_growth_units == 500
    assert completed.fertilizer_card_batches == []
    assert completed.fertilizer_card_queue == []
    assert completed.booster_card_batches == []
    assert storage.state.active_plant_id == continuation.plant_id
    assert continuation.fertilizer_card_batches[0].effect_id == "fertilizer_basic"
    assert continuation.fertilizer_card_batches[0].remaining_cards == 29
    assert continuation.fertilizer_card_queue == []
    assert continuation.booster_card_batches[0].remaining_cards == 29


def test_effect_dose_cap_keeps_unaccepted_items_in_inventory():
    engine, storage = make_engine()
    engine._now_seconds = lambda: storage.now_ms / 1_000
    storage.state.consumables["fertilizer_basic"] = 6

    results = [engine.use_fertilizer_item("p1", tier="basic") for _ in range(6)]

    assert [ok for ok, _message in results] == [True, True, True, True, True, False]
    plant = storage.state.plants[0]
    assert len(plant.fertilizer_card_batches) == 5
    assert plant.fertilizer_card_queue == []
    assert storage.state.consumables["fertilizer_basic"] == 1


def test_guaranteed_garden_find_growth_is_direct_and_duplicate_safe():
    engine, storage = make_engine()
    engine.initialize_reward_state()
    engine.garden_find_registry = PreparedRewardRegistry((GardenFindReward(
        "find_morning_dew",
        "Morning Dew",
        "+40 Growth",
        "growth",
        40,
        1_000,
        "Uncommon",
        eligibility_rule="unfinished_nurtured_plant",
    ),))
    storage.state.garden_find_drought_count = 74
    first_id = storage.now_ms + 1_000
    first = answer(engine, storage, revlog_id=first_id)
    duplicate = answer(engine, storage, revlog_id=first_id)

    assert duplicate.total_growth == 0
    assert first.garden_find_ids == ("find_morning_dew",)
    assert storage.state.plants[0].growth_points == 50
    assert storage.state.plants[1].growth_points == 1
    assert storage.state.garden_find_drought_count == 0
    outcomes = list(storage.state.garden_find_outcomes.values())
    assert {outcome.pool_id for outcome in outcomes} == {"standard", "environment"}
    assert sum(outcome.status == "hit" for outcome in outcomes) == 1
    feedback = next(
        event
        for event in engine.peek_feedback()
        if event.event_id == f"reward-summary:{first.correlation_id}"
    )
    assert feedback.message == (
        "+4 Coins and +40 Growth"
    )
    assert feedback.correlation_id == first.correlation_id
    assert feedback.amount == 0


def test_guaranteed_growth_find_keeps_v2_weights_and_stores_without_a_target():
    engine, storage = make_engine()
    engine.initialize_reward_state()
    engine.garden_find_registry = PreparedRewardRegistry((GardenFindReward(
        "find_stored_growth",
        "Stored Growth",
        "+40 Growth",
        "growth",
        40,
        1_000,
        "Uncommon",
        eligibility_rule="unfinished_nurtured_plant",
    ),))
    storage.state.garden_find_drought_count = 74
    assert engine.set_active_plant(None)[0]

    award = answer(engine, storage)

    assert award.garden_find_ids == ("find_stored_growth",)
    assert storage.state.stored_growth_units == 5_000
    assert storage.state.daily_stats.instant_growth_units == 4_000
    standard = next(
        outcome for outcome in storage.state.garden_find_outcomes.values()
        if outcome.pool_id == "standard"
    )
    assert standard.pool_version == "standard-v2"
    assert standard.status == "hit"


def test_garden_finds_wait_for_their_own_activation_boundary():
    engine, storage = make_engine()
    engine.initialize_reward_state()
    storage.state.garden_find_activation_ms = storage.now_ms + 2_000
    storage.state.garden_find_drought_count = 74

    before_cutoff = answer(engine, storage)
    assert before_cutoff.total_growth == 10
    assert storage.state.garden_find_drought_count == 74
    assert storage.state.garden_find_outcomes == {}

    at_cutoff = answer(engine, storage)
    assert at_cutoff.garden_find_ids
    assert any(
        outcome.pool_id == "standard"
        for outcome in storage.state.garden_find_outcomes.values()
    )


def test_engine_persists_and_resets_only_the_winning_environment_pity_tier():
    engine, storage = make_engine()
    engine.initialize_reward_state()
    storage.state.inventory["scenery"].append("rainbow_horizon")
    storage.state.inventory["scenery"].extend([
        "halloween", "full_moon", "eclipse",
    ])
    storage.state.environment_pity_misses = {
        "rare": 9_999,
        "very_rare": 123,
        "ultra": 456,
    }

    award = answer(engine, storage)

    discovered = set(award.garden_find_ids) & {
        "firefly_lantern", "rainbow_horizon"
    }
    assert len(discovered) == 1
    assert storage.state.environment_pity_misses == {
        "rare": 0,
        "very_rare": 124,
        "ultra": 456,
    }
    environment = next(
        outcome for outcome in storage.state.garden_find_outcomes.values()
        if outcome.pool_id == "environment"
    )
    assert environment.pool_version == "environment-v2"
    assert environment.status == "hit"
    assert environment.tier == "rare_environment"


def test_synced_answers_only_consume_card_fertilizer_at_or_after_activation(monkeypatch):
    engine, storage = make_engine()
    activation_ms = storage.now_ms
    monkeypatch.setattr(engine, "_now_seconds", lambda: activation_ms / 1_000)
    storage.state.consumables["fertilizer_quality"] = 1
    assert engine.use_fertilizer_item("p1", tier="quality")[0]

    gained = engine.apply_same_day_reviews(
        [
            {
                "queue": 2,
                "ease": 3,
                "revlog_id": activation_ms - 1_000,
                "answered_at_ms": activation_ms - 1_000,
            },
            {
                "queue": 2,
                "ease": 3,
                "revlog_id": activation_ms,
                "answered_at_ms": activation_ms,
            },
            {
                "queue": 2,
                "ease": 3,
                "revlog_id": activation_ms + 1_000,
                "answered_at_ms": activation_ms + 1_000,
            },
        ],
        latest_revlog_id=activation_ms + 1_000,
    )

    assert gained == 34
    assert storage.state.daily_stats.base_growth == 30
    assert storage.state.daily_stats.fertilizer_growth == 4
    batches = storage.state.plants[0].fertilizer_card_batches
    assert len(batches) == 1
    assert batches[0].effect_id == "fertilizer_quality"
    assert batches[0].remaining_cards == 198
    assert storage.state.plants[0].fertilizer_card_queue == []


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


def test_reanswer_alias_is_acknowledged_without_regranting_consumed_lineage():
    engine, storage = make_engine()
    lineage = f"v1|{storage.day}|42|1"
    first_id = storage.now_ms + 1_000
    older_synced_id = storage.now_ms + 2_000
    replacement_id = storage.now_ms + 3_000

    first = engine.register_review({
        "queue": 2,
        "ease": 3,
        "card_id": 42,
        "revlog_id": first_id,
        "answered_at_ms": first_id,
        "answer_identity": lineage,
    })
    storage.state.pending_reanswer_lineages[lineage] = replacement_id
    storage.reanswer_floor_for_lineage = (
        lambda key: storage.state.pending_reanswer_lineages.get(key)
    )
    storage.clear_reanswer_hint = (
        lambda key: storage.state.pending_reanswer_lineages.pop(key, None)
    )
    older_synced = engine.register_review({
        "queue": 2,
        "ease": 3,
        "card_id": 42,
        "revlog_id": older_synced_id,
        "answered_at_ms": older_synced_id,
        "answer_identity": lineage,
    })
    assert storage.state.pending_reanswer_lineages == {
        lineage: replacement_id
    }
    replacement = engine.register_review({
        "queue": 2,
        "ease": 3,
        "card_id": 42,
        "revlog_id": replacement_id,
        "answered_at_ms": replacement_id,
        "answer_identity": lineage,
    })

    assert first.total_growth == 10
    assert older_synced.total_growth == 0
    assert replacement.total_growth == 0
    assert storage.state.daily_stats.reviewed == 1
    assert storage.state.processed_revlog_ids == [
        first_id,
        older_synced_id,
        replacement_id,
    ]
    assert storage.state.answer_lineage_bindings[str(replacement_id)] == lineage
    assert lineage not in storage.state.pending_reanswer_lineages


def test_species_bed_and_collection_economy_preserves_plant_progress():
    engine, storage = make_engine()
    storage.state.currency_balance = 1_000

    ok, _message, sunflower = engine.purchase_species("sunflower")
    assert ok and sunflower is not None and not sunflower.planted
    assert not engine.purchase_next_bed()[0]
    storage.state.unlocked_slots = 3
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
    assert message == "Choose an empty bed."
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

    storage.state.unlocked_slots = 6
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
    event_id = storage.now_ms + 1_000

    with pytest.raises(OSError):
        answer(engine, storage, revlog_id=event_id)

    assert storage.state.to_dict() == before
    storage.fail_save = False

    retry = answer(engine, storage, revlog_id=event_id)

    assert retry.total_growth == 10
    assert storage.state.reward_activation_ms == event_id
    assert storage.state.currency_balance == 4


def test_failed_same_day_batch_rolls_back_growth_cursor_and_transitions():
    engine, storage = make_engine()
    storage.state.plants[0].growth_points = 390
    before = storage.state.to_dict()
    storage.fail_save = True

    with pytest.raises(OSError):
        engine.apply_same_day_reviews(
            [{
                "queue": 2,
                "ease": 3,
                "revlog_id": storage.now_ms + 1,
                "answer_identity": f"v1|{storage.day}|42|1",
            }],
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
    assert "100,000 Garden Coins" in message
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
        "collection", "active", "garden_name", "place", "commit", "restore",
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
        (50, [1, 4, 12, 30, 70]),
        (150, [1, 2, 4, 10, 24]),
        (300, [1, 1, 2, 5, 12]),
        (500, [1, 1, 2, 3, 7]),
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


@pytest.mark.parametrize(
    ("tier", "growth_per_card", "cards", "price"),
    [
        ("basic", 1, 100, 30),
        ("quality", 2, 200, 100),
        ("premium", 3, 400, 300),
    ],
)
def test_card_counted_fertilizer_balance_and_equal_value_per_card(
    tier,
    growth_per_card,
    cards,
    price,
):
    spec = GardenGameEngine.FERTILIZERS[tier]
    assert spec.growth_per_answer == growth_per_card
    assert spec.card_count == cards
    assert spec.price == price
    assert spec.growth_per_answer * spec.card_count / spec.price == pytest.approx(
        10 / 3 if tier == "basic" else 4
    )


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


def test_day_7_integrated_reward_remains_once_ever_when_visible_history_is_cleared():
    engine, storage = make_engine()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.currency_balance == 10
    assert storage.state.achievements["streak_7"].unlocked
    storage.state.currency_transactions.clear()
    storage.state.streak_days = 6
    storage.state.last_active_day = "2026-08-07"

    engine._start_study_day()

    assert storage.state.currency_balance == 10
    assert storage.state.currency_transactions == []


def completed_collection_engine(*, displayed=True):
    engine, storage = make_engine()
    state = storage.state
    state.plants = [Plant(f"catalog-{index}", species, species.title(),
                          index if displayed and index < 6 else None,
                          growth_points=GROWTH_THRESHOLDS[-1])
                    for index, species in enumerate(CURRENT_CATALOG_SPECIES_ORDER)]
    state.unlocked_species = list(CURRENT_CATALOG_SPECIES_ORDER)
    state.unlocked_slots = 6
    state.active_plant_id = None
    state.active_plant_periods = []
    from dataclasses import replace
    state.onboarding = replace(state.onboarding, starter_plant_id=state.plants[0].plant_id)
    engine = GardenGameEngine(FakeConfig(), storage)
    engine._update_achievements()
    return engine, storage


@pytest.mark.parametrize("displayed", [False, True])
@pytest.mark.parametrize("charge_id,amount", [("growth_charge_small", 100), ("growth_charge_standard", 500), ("growth_charge_grand", 2000)])
def test_completed_collection_charge_receipt_conserves_mastery_and_storage(displayed, charge_id, amount):
    from ankigarden.economy_progression import MASTERY_MAX_GROWTH_UNITS

    engine, storage = completed_collection_engine(displayed=displayed)
    state = storage.state
    species = CURRENT_CATALOG_SPECIES_ORDER[0]
    state.active_growth_target_type = "mastery"
    state.active_growth_target_id = species
    state.active_growth_target_activation_identity = "test-mastery-selection"
    state.cultivation_mastery.growth_units_funded_by_species[species] = MASTERY_MAX_GROWTH_UNITS - 5_000
    state.consumables[charge_id] = 1
    quote = engine.quote_growth_charge(charge_id)
    assert quote.ready and quote.destination_kind == "garden"
    assert quote.target_state is GrowthChargeTargetState.GARDEN
    assert sum(row.units for row in quote.project_allocations) == 5_000
    assert quote.stored_growth_units == amount * 100 - 5_000
    for invalid in ("", "missing", state.plants[0].plant_id):
        assert not engine.quote_growth_charge(charge_id, invalid).ready
    request = GrowthChargeRequest.from_quote(quote)
    before = state.to_dict()
    storage.fail_save = True
    assert engine.confirm_growth_charge(request).status is GrowthChargeStatus.PERSISTENCE_FAILURE
    assert storage.state.to_dict() == before
    storage.fail_save = False
    outcome = engine.confirm_growth_charge(request)
    assert outcome.success and outcome.destination_kind == "garden"
    assert outcome.stored_growth_units + sum(row.units for row in outcome.project_allocations) == amount * 100
    assert storage.state.stored_growth_units == amount * 100 - 5_000
    assert storage.state.consumables[charge_id] == 0
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), storage)
    assert engine.confirm_growth_charge(request) == outcome
    assert "Mastery" in outcome.message and "Stored Growth" in outcome.message


@pytest.mark.parametrize("displayed", [False, True])
@pytest.mark.parametrize("tier", ["basic", "quality", "premium"])
def test_completed_garden_supplies_contribute_once_and_preserve_paid_cards(displayed, tier):
    from ankigarden.balance_catalog import ACHIEVEMENT_TROPHIES
    from ankigarden.purchases import PurchaseKind, PurchaseRequest

    engine, storage = completed_collection_engine(displayed=displayed)
    state = storage.state
    for trophy in ACHIEVEMENT_TROPHIES:
        state.achievements[str(trophy.source_achievement_id)].unlocked = True
        state.trophy_activation_ms[str(trophy.cosmetic_id)] = storage.now_ms - 1
    state.inventory["garden_features"].extend(["watering_station", "herbalist_hourglass"])
    state.inventory["scenery"].extend(["spring", "full_moon"])
    assert engine.equip_environment("garden_feature", "watering_station")[0]
    assert engine.equip_environment("scenery", "spring")[0]
    state.consumables[f"fertilizer_{tier}"] = 1
    state.consumables["booster_potion"] = 1
    assert not engine.use_fertilizer_item("missing", tier=tier)[0]
    assert not engine.use_booster_potion(state.plants[0].plant_id)[0]
    before = state.to_dict()
    storage.fail_save = True
    assert not engine.use_fertilizer_item(tier=tier)[0]
    assert storage.state.to_dict() == before
    assert not engine.use_booster_potion()[0]
    assert storage.state.to_dict() == before
    storage.fail_save = False
    assert engine.use_fertilizer_item(tier=tier)[0]
    assert engine.use_booster_potion()[0]
    first = answer(engine, storage)
    assert first.fertilizer_growth_units == engine.FERTILIZERS[tier].growth_per_answer * 100
    assert first.booster_growth_units == 500
    assert first.trophy_growth_units == 100 and first.scenery_growth_units == 200
    assert first.stored_growth_units == first.total_growth_units + ((first.total_growth_units * 15 // 100) * 5 if displayed else 0)
    baseline = engine.sync_reward_baseline()
    assert baseline["fertilizer_cards_remaining"] == engine.FERTILIZERS[tier].card_count - 1
    assert baseline["booster_cards_remaining"] == 149
    before = storage.state.to_dict()
    assert answer(engine, storage, revlog_id=storage.now_ms).total_growth_units == 0
    assert storage.state.garden_card_effects.to_dict() == before["garden_card_effects"]
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), storage)
    assert engine.sync_reward_baseline()["booster_cards_remaining"] == 149
    # Buying and applying uses the same explicit garden destination.
    storage.state.currency_balance = 1000
    quote = engine.quote_purchase(PurchaseKind.FERTILIZER, tier, target_id=engine.GARDEN_SUPPLY_TARGET)
    assert quote.ready and quote.target_name == "Garden"
    result = engine.confirm_purchase(PurchaseRequest.from_quote(quote))
    assert result.success
    assert engine.sync_reward_baseline()["fertilizer_cards_remaining"] == 2 * engine.FERTILIZERS[tier].card_count - 1


def test_schema29_final_bloom_transfers_inherited_queues_once_without_truncation():
    from ankigarden.storage import migrate_modern_state

    engine, storage = completed_collection_engine()
    state = storage.state
    last = state.plants[0]
    last.growth_points = GROWTH_THRESHOLDS[-1] - 1
    state.active_plant_id = last.plant_id
    state.active_plant_periods = [ActivePlantPeriod(storage.day, last.plant_id, storage.now_ms - 1000)]
    for index, plant in enumerate(state.plants):
        plant.fertilizer_card_batches = [CardEffectBatch("fertilizer_basic", 100, 100, 1,
            activated_at="2026-08-01T00:00:00+00:00", source_event_key=f"paid-{index}")]
    payload = state.to_dict()
    payload["version"] = 29
    payload["wind_chime_progress"] = 9
    payload["watering_station_progress"] = 4
    payload["watering_station_progress_by_day"] = {storage.day: 4}
    storage.state = migrate_modern_state(payload)
    engine = GardenGameEngine(FakeConfig(), storage)
    assert not storage.state.collection_complete
    assert answer(engine, storage).fertilizer_growth_units == 100
    assert storage.state.collection_complete
    assert all(not p.fertilizer_card_batches and not p.fertilizer_card_queue for p in storage.state.plants)
    garden = storage.state.garden_card_effects
    batches = [*garden.fertilizer_card_batches, *garden.fertilizer_card_queue]
    assert [batch.source_event_key for batch in batches] == [f"paid-{index}" for index in range(1, 10)]
    assert all(batch.activated_at == "2026-08-01T00:00:00+00:00" and batch.remaining_cards == 1 for batch in batches)
    storage.state.consumables["fertilizer_basic"] = 1
    assert not engine.use_fertilizer_item()[0]
    storage.state = GardenState.from_dict(storage.state.to_dict())
    engine = GardenGameEngine(FakeConfig(), storage)
    assert engine.sync_reward_baseline()["fertilizer_cards_remaining"] == 9
    for _ in range(5):
        assert answer(engine, storage).fertilizer_growth_units == 100
    assert engine.use_fertilizer_item()[0]
    assert engine.sync_reward_baseline()["fertilizer_cards_remaining"] == 104
    assert storage.state.wind_chime_progress == 9
    assert storage.state.watering_station_progress_by_day[storage.day] == 4
