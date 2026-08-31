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
)
from ankigarden.models.state import GardenFindOutcome, RewardReceipt
from ankigarden.models.sync_reward import SyncRewardSummary
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
    landmark_before_units: int = 0,
    landmark_after_units: int = 0,
    mastery_before_units: int = 0,
    mastery_after_units: int = 0,
    legacy_before_units: int = 0,
    legacy_after_units: int = 0,
    project_allocations: tuple[ProjectGrowthAllocation, ...] = (),
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
            base_growth_units=max(
                0,
                (after_units - before_units)
                + (landmark_after_units - landmark_before_units)
                + (mastery_after_units - mastery_before_units)
                + (legacy_after_units - legacy_before_units),
            ),
            landmark_growth_units=max(
                0, landmark_after_units - landmark_before_units
            ),
        ),
        reward_receipts=receipts,
        plants_before=(before,),
        plants_after=(after,),
        landmark_growth_before_units=landmark_before_units,
        landmark_growth_after_units=landmark_after_units,
        mastery_growth_before_units=mastery_before_units,
        mastery_growth_after_units=mastery_after_units,
        legacy_growth_before_units=legacy_before_units,
        legacy_growth_after_units=legacy_after_units,
        project_allocations=project_allocations,
        active_plant_before_id="bluebell",
        active_plant_after_id="bluebell",
    )


def _all_clear_receipt(event_id: str, scheduler_day: str, amount: int) -> RewardReceipt:
    return RewardReceipt(
        event_key=f"all_due:{scheduler_day}",
        reward_type="coins",
        source="all_due",
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
    results = (
        _result(
            event_id="answer:200",
            scheduler_day="2026-08-27",
            before_units=0,
            after_units=1_000,
        ),
        _result(
            event_id="answer:100",
            scheduler_day=CURRENT_DAY,
            before_units=1_000,
            after_units=2_000,
        ),
    )

    summary = build_sync_reward_summary(
        "sync-batch",
        results,
        baseline={},
        engine=SimpleNamespace(_scheduler_day=lambda: CURRENT_DAY),
    )

    assert summary is not None
    assert summary.eligible_answer_count == 2
    assert summary.anki_days == ("2026-08-27", CURRENT_DAY)
    assert summary.growth_total_units == 2_000
    assert summary.plant_growth[0]["growth_delta_units"] == 2_000
    assert summary.plant_results[0].plant_id == "bluebell"
    assert summary.plant_results[0].growth_delta_units == 2_000
    assert summary.to_dict()["model_version"] == 4


def test_landmark_only_import_preserves_total_growth_and_allocation() -> None:
    result = _result(
        event_id="answer:300",
        scheduler_day=CURRENT_DAY,
        before_units=3_500_000,
        after_units=3_500_000,
        landmark_before_units=25_000,
        landmark_after_units=26_000,
    )

    summary = build_sync_reward_summary(
        "sync-landmark-only",
        (result,),
        baseline={},
        engine=SimpleNamespace(_scheduler_day=lambda: CURRENT_DAY),
    )

    assert summary is not None
    assert summary.eligible_answer_count == 1
    assert summary.plant_results == ()
    assert summary.plant_growth == ()
    assert summary.stored_growth_delta_units == 0
    assert summary.landmark_growth_delta_units == 1_000
    assert summary.growth_total_units == 1_000
    assert summary.meaningful is True


def test_sync_exposes_exact_committed_allocations_for_every_project_type() -> None:
    results = (
        _result(
            event_id="answer:301",
            scheduler_day=CURRENT_DAY,
            before_units=3_500_000,
            after_units=3_500_000,
            landmark_before_units=25_000,
            landmark_after_units=25_100,
            project_allocations=(ProjectGrowthAllocation(
                GrowthTargetType.LANDMARK,
                "garden_landmark",
                100,
            ),),
        ),
        _result(
            event_id="answer:302",
            scheduler_day=CURRENT_DAY,
            before_units=3_500_000,
            after_units=3_500_000,
            mastery_before_units=75_000,
            mastery_after_units=75_200,
            project_allocations=(ProjectGrowthAllocation(
                GrowthTargetType.MASTERY,
                "bonsai",
                200,
            ),),
        ),
        _result(
            event_id="answer:303",
            scheduler_day=CURRENT_DAY,
            before_units=3_500_000,
            after_units=3_500_000,
            legacy_before_units=500_000,
            legacy_after_units=500_300,
            project_allocations=(ProjectGrowthAllocation(
                GrowthTargetType.LEGACY,
                "garden_legacy",
                300,
            ),),
        ),
    )

    summary = build_sync_reward_summary(
        "sync-all-projects",
        results,
        baseline={"landmark_growth_units": 999_999_999},
        engine=SimpleNamespace(_scheduler_day=lambda: CURRENT_DAY),
    )

    assert summary is not None
    assert summary.growth_total_units == 600
    assert summary.landmark_growth_delta_units == 100
    assert summary.mastery_growth_delta_units == 200
    assert summary.legacy_growth_delta_units == 300
    assert tuple(row.to_dict() for row in summary.project_allocations) == (
        {
            "target_type": "landmark",
            "target_id": "garden_landmark",
            "units": 100,
        },
        {"target_type": "mastery", "target_id": "bonsai", "units": 200},
        {
            "target_type": "legacy",
            "target_id": "garden_legacy",
            "units": 300,
        },
    )
    assert SyncRewardSummary.from_dict(summary.to_dict()) == summary


def test_sync_named_find_replaces_legacy_category_icon_with_canonical_art() -> None:
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
    result = replace(
        _result(
            event_id="answer:100",
            scheduler_day=CURRENT_DAY,
            before_units=0,
            after_units=1_000,
        ),
        garden_find_outcomes=(legacy_outcome,),
        standard_find_count=1,
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


def test_sync_active_boosts_keep_canonical_item_art_in_pending_summary() -> None:
    engine = SimpleNamespace(
        _scheduler_day=lambda: CURRENT_DAY,
        sync_reward_baseline=lambda: {
            "fertilizer_signature": ("quality-after",),
            "fertilizer_cards_remaining": 90,
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
    assert summary.fertilizer_cards_remaining == 90
    assert summary.fertilizer_remaining_seconds == 0
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
