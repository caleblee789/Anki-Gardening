from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from ankigarden.economy_progression import (
    GrowthTargetType,
    ProjectGrowthAllocation,
)
from ankigarden.game import (
    CommittedAnswerResult,
    CommittedPlantSnapshot,
    ReviewAward,
    StageTransition,
)
from ankigarden.models.state import GardenFindOutcome, RewardReceipt
from ankigarden.models.sync_reward import (
    SYNC_REWARD_MODEL_VERSION,
    SyncRewardSummary,
)
from ankigarden.sync_review_detector import SyncAttemptSnapshot
from ankigarden.sync_reward_processor import (
    SyncRewardProcessor,
    build_sync_reward_summary,
)


CURRENT_DAY = "2026-08-29"


def _result(
    *,
    event_id: str,
    scheduler_day: str,
    before_units: int,
    after_units: int,
    receipts: tuple[RewardReceipt, ...] = (),
) -> CommittedAnswerResult:
    before = CommittedPlantSnapshot(
        "bluebell",
        "Bluebell",
        "hydrangea",
        "young",
        before_units,
        0,
        False,
    )
    after = CommittedPlantSnapshot(
        "bluebell",
        "Bluebell",
        "hydrangea",
        "young",
        after_units,
        0,
        False,
    )
    return CommittedAnswerResult(
        event_id=event_id,
        correlation_id=event_id,
        scheduler_day=scheduler_day,
        occurred_at_ms=int(event_id.rsplit(":", 1)[-1]),
        origin="sync_import",
        award=ReviewAward(
            "bluebell",
            10,
            0,
            0,
            0,
            correlation_id=event_id,
            base_growth_units=max(0, after_units - before_units),
        ),
        reward_receipts=receipts,
        plants_before=(before,),
        plants_after=(after,),
        active_plant_before_id="bluebell",
        active_plant_after_id="bluebell",
    )


def _all_clear_receipt(event_id: str, scheduler_day: str, amount: int) -> RewardReceipt:
    return RewardReceipt(
        event_key=f"all_due:{scheduler_day}",
        reward_type="coins",
        source="todays_cards",
        source_id=scheduler_day,
        scheduler_day=scheduler_day,
        correlation_id=event_id,
        occurred_at=f"{scheduler_day}T12:00:00+00:00",
        amount=amount,
    )


class Engine:
    def __init__(self, results: tuple[CommittedAnswerResult, ...]) -> None:
        self.results = results
        self.state = SimpleNamespace(pending_sync_reward_summary=None)
        self.reconcile_calls: list[dict[str, object]] = []
        self.baseline_calls: list[tuple[str, bool]] = []

    def _scheduler_day(self) -> str:
        return CURRENT_DAY

    def reconcile_reward_history(self, **kwargs):
        self.reconcile_calls.append(kwargs)
        factory = kwargs.get("pending_summary_factory")
        if callable(factory):
            summary = factory(self.results)
            if summary is not None:
                self.state.pending_sync_reward_summary = summary.to_dict()
        return True, "Garden is up to date."

    def baseline_reward_history(
        self,
        reason: str = "collection_replaced",
        *,
        persist: bool = True,
    ):
        self.baseline_calls.append((reason, persist))
        return True, "Garden baseline updated."


class Presenter:
    def __init__(self) -> None:
        self.enqueued: list[SyncRewardSummary] = []

    def enqueue(self, summary: SyncRewardSummary) -> None:
        self.enqueued.append(summary)


def _snapshot(**changes):
    values = {
        "batch_id": "sync-batch",
        "scheduler_day": CURRENT_DAY,
        "collection_token": "profile-a:collection-a",
        "collection_generation": 0,
        "ledger_revision": 7,
        "valid": True,
        "invalidation_reason": "",
        "one_way_replacement": False,
        "reward_baseline": {"garden_coin_balance": 40},
    }
    values.update(changes)
    return SyncAttemptSnapshot(**values)


def test_summary_counts_multi_day_events_even_when_a_later_arrival_has_lower_id() -> None:
    stage_coin = RewardReceipt("stage:bluebell:mature", "coins", "plant_milestone", "bluebell",
                               "2026-08-27", "answer:200", "2026-08-27T12:00:00Z", amount=2, plant_id="bluebell")
    results = (
        replace(_result(
            event_id="answer:200",
            scheduler_day="2026-08-27",
            before_units=0,
            after_units=1_000,
            receipts=(stage_coin, stage_coin),
        ),
            mastery_growth_before_units=0,
            mastery_growth_after_units=100,
            project_allocations=(
                ProjectGrowthAllocation(GrowthTargetType.MASTERY, "rose", 100),
                ProjectGrowthAllocation(GrowthTargetType.MASTERY, "rose", 0),
            ),
            stage_transitions=(StageTransition(
                "bluebell",
                "hydrangea",
                "young",
                "mature",
                "Bluebell",
                "shared_growth",
            ),),
        ),
        replace(_result(
            event_id="answer:100",
            scheduler_day=CURRENT_DAY,
            before_units=1_000,
            after_units=2_000,
            receipts=(replace(stage_coin, event_key="stage:bluebell:flowering", amount=3, correlation_id="answer:100"),),
        ),
            mastery_growth_before_units=100,
            mastery_growth_after_units=150,
            legacy_growth_before_units=0,
            legacy_growth_after_units=25,
            project_allocations=(
                ProjectGrowthAllocation(GrowthTargetType.MASTERY, "rose", 50),
                ProjectGrowthAllocation(GrowthTargetType.LEGACY, "garden_legacy", 25),
            ),
        ),
    )

    summary = build_sync_reward_summary(
        "sync-batch",
        results,
        baseline={"garden_coin_balance": 0},
        engine=SimpleNamespace(_scheduler_day=lambda: CURRENT_DAY, sync_reward_baseline=lambda: {"garden_coin_balance": 5}),
    )

    assert summary is not None
    assert summary.eligible_answer_count == 2
    assert summary.anki_days == ("2026-08-27", CURRENT_DAY)
    assert summary.growth_total_units == 2_175
    assert summary.plant_growth[0]["growth_delta_units"] == 2_000
    assert summary.plant_results[0].plant_id == "bluebell"
    assert summary.plant_results[0].growth_delta_units == 2_000
    assert summary.garden_coin_delta == summary.plant_results[0].progression_coins == 5
    assert summary.plant_results[0].transition_source == "shared_growth"
    assert tuple(
        (row.target_type, row.target_id, row.units)
        for row in summary.project_allocations
    ) == (("mastery", "rose", 150), ("legacy", "garden_legacy", 25))
    assert summary.to_dict()["model_version"] == SYNC_REWARD_MODEL_VERSION


def test_sync_named_finds_keep_canonical_art_and_single_receipt_payouts() -> None:
    legacy_outcome = GardenFindOutcome(
        "answer:100",
        CURRENT_DAY,
        "hit",
        "standard",
        "standard-v2",
        f"{CURRENT_DAY}T12:00:00+00:00",
        reward_id="find_morning_dew",
        reward_type="growth",
        amount=40,
        display_name="Morning Dew",
        description="+40 Growth",
        tier="Common",
        artwork_ref="growth",
    )
    item_outcome = replace(
        legacy_outcome, answer_key="answer:101", reward_id="find_small_charge",
        reward_type="inventory_item", amount=1, item_id="growth_charge_small",
        display_name="Small Growth Charge", description="+1 Small Growth Charge",
        artwork_ref="ui_growth_charge_small",
    )
    result = replace(
        _result(
            event_id="answer:100",
            scheduler_day=CURRENT_DAY,
            before_units=0,
            after_units=1_000,
        ),
        garden_find_outcomes=(legacy_outcome, item_outcome),
        standard_find_count=2,
        reward_receipts=(RewardReceipt(
            "garden_find:answer:101:standard", "inventory_item", "standard_find", "find_small_charge",
            CURRENT_DAY, "answer:100", f"{CURRENT_DAY}T12:00:00+00:00",
            amount=1, item_id="growth_charge_small",
        ),),
    )
    engine = SimpleNamespace(
        _scheduler_day=lambda: CURRENT_DAY,
        resolve_item_asset=lambda key: SimpleNamespace(
            path=f"/art/{key}.webp"
        ),
    )

    summary = build_sync_reward_summary(
        "sync-batch",
        (result,),
        baseline={},
        engine=engine,
    )

    assert summary is not None
    assert summary.finds[0]["image_asset"] == "/art/morning_dew.webp"
    assert [(row["reward_id"], row["quantity"]) for row in summary.finds] == [
        ("find_morning_dew", 1), ("find_small_charge", 1),
    ]
    # A retained Find identity may also be an inventory item ID. Distinct
    # achievement and Find awards remain counted without inventing one cause.
    mixed = replace(result,
        garden_find_outcomes=(replace(item_outcome, reward_id="growth_charge_small"),),
        reward_receipts=(RewardReceipt(
            "achievement:streak_7", "inventory_item", "achievement", "streak_7",
            CURRENT_DAY, "answer:100", f"{CURRENT_DAY}T12:00:00+00:00",
            amount=1, item_id="growth_charge_small",
        ),))
    mixed_summary = build_sync_reward_summary("mixed", (mixed,), baseline={}, engine=engine)
    assert mixed_summary is not None
    assert mixed_summary.finds[0]["quantity"] == 2
    assert mixed_summary.finds[0]["source"] == "mixed"


def test_sync_active_boosts_keep_canonical_item_art_in_pending_summary() -> None:
    engine = SimpleNamespace(
        _scheduler_day=lambda: CURRENT_DAY,
        sync_reward_baseline=lambda: {
            "fertilizer_signature": ("quality-after",),
            "fertilizer_remaining_seconds": 1_080,
            "fertilizer_item_id": "fertilizer_quality",
            "booster_signature": ("booster-after",),
            "booster_cards_remaining": 12,
            "booster_item_id": "booster_potion",
        },
        resolve_item_asset=lambda key: SimpleNamespace(path=f"/art/{key}.webp"),
    )

    summary = build_sync_reward_summary(
        "sync-batch",
        (_result(
            event_id="answer:100",
            scheduler_day=CURRENT_DAY,
            before_units=0,
            after_units=1_000,
        ),),
        baseline={
            "fertilizer_signature": ("quality-before",),
            "booster_signature": ("booster-before",),
        },
        engine=engine,
    )

    assert summary is not None
    assert summary.fertilizer_item_id == "fertilizer_quality"
    assert summary.fertilizer_art_asset == "/art/fertilizer_quality.webp"
    assert summary.booster_item_id == "booster_potion"
    assert summary.booster_art_asset == "/art/booster_potion.webp"
    assert SyncRewardSummary.from_dict(summary.to_dict()) == summary


def test_historical_all_clear_is_ignored_but_current_day_all_clear_is_kept() -> None:
    past = _result(
        event_id="answer:100",
        scheduler_day="2026-08-27",
        before_units=0,
        after_units=1_000,
        receipts=(_all_clear_receipt("answer:100", "2026-08-27", 99),),
    )
    current = _result(
        event_id="answer:200",
        scheduler_day=CURRENT_DAY,
        before_units=1_000,
        after_units=2_000,
        receipts=(_all_clear_receipt("answer:200", CURRENT_DAY, 10),),
    )

    summary = build_sync_reward_summary(
        "sync-batch",
        (past, current),
        baseline={},
        engine=SimpleNamespace(_scheduler_day=lambda: CURRENT_DAY),
    )

    assert summary is not None
    assert summary.all_clear_earned
    assert summary.all_clear_coin_reward == 10


def test_enabled_processing_persists_one_pending_summary_and_enqueues_it() -> None:
    engine = Engine((_result(
        event_id="answer:100",
        scheduler_day=CURRENT_DAY,
        before_units=0,
        after_units=1_000,
    ),))
    presenter = Presenter()
    storage = SimpleNamespace(due_obligations=lambda: "current-due-status")
    processor = SyncRewardProcessor(engine, storage, presenter)

    summary = processor.process(_snapshot(), presentation_enabled=True)

    assert summary is not None
    assert len(engine.reconcile_calls) == 1
    call = engine.reconcile_calls[0]
    assert call["persist"] is True
    assert call["include_open_day"] is True
    assert call["due_status"] == "current-due-status"
    assert callable(call["pending_summary_factory"])
    assert call["emit_feedback"] is False
    assert engine.state.pending_sync_reward_summary == summary.to_dict()
    assert presenter.enqueued == [summary]


def test_disabled_presentation_still_reconciles_rewards_without_pending_receipt() -> None:
    engine = Engine((_result(
        event_id="answer:100",
        scheduler_day=CURRENT_DAY,
        before_units=0,
        after_units=1_000,
    ),))
    presenter = Presenter()
    processor = SyncRewardProcessor(
        engine,
        SimpleNamespace(due_obligations=lambda: None),
        presenter,
    )

    summary = processor.process(_snapshot(), presentation_enabled=False)

    assert summary is None
    assert len(engine.reconcile_calls) == 1
    assert engine.reconcile_calls[0]["pending_summary_factory"] is None
    assert engine.state.pending_sync_reward_summary is None
    assert presenter.enqueued == []


def test_one_way_replacement_baselines_without_processing_or_presenting() -> None:
    engine = Engine((_result(
        event_id="answer:100",
        scheduler_day=CURRENT_DAY,
        before_units=0,
        after_units=1_000,
    ),))
    presenter = Presenter()
    processor = SyncRewardProcessor(engine, SimpleNamespace(), presenter)

    summary = processor.process(_snapshot(
        valid=False,
        invalidation_reason="collection_replaced",
        one_way_replacement=True,
    ))

    assert summary is None
    assert engine.baseline_calls == [("collection_replaced", True)]
    assert engine.reconcile_calls == []
    assert engine.state.pending_sync_reward_summary is None
    assert presenter.enqueued == []
