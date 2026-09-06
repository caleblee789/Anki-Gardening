from __future__ import annotations

import importlib
import os
import re
import sys
import types
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.economy_progression import (
    GrowthTargetType,
    ProjectGrowthAllocation,
)
from ankigarden.game import CommittedAnswerResult, GardenGameEngine, ReviewAward
from ankigarden.growth import GrowthAllocation
from ankigarden.models.state import (
    ActivePlantPeriod,
    CurrencyTransaction,
    DailyStats,
    GardenFindOutcome,
    GardenState,
    Plant,
)
from ankigarden.storage import DueObligationStatus
from ankigarden.ui.session_summary import (
    CommittedSessionEvent,
    PlantGrowthDelta,
    ReviewContinuationTarget,
    SessionEndSnapshot,
    SessionStartSnapshot,
    SessionSummaryAccumulator,
    TodayCardsSnapshot,
    project_session_day,
)
from ankigarden.ui.transient_summary_coordinator import (
    TransientSummaryCoordinator,
)


DAY = "2026-08-28"


class _Config:
    def __init__(self) -> None:
        self.data = dict(DEFAULT_CONFIG)

    def value(self, key, default=None):
        return self.data.get(key, default)

    def nested(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


class _EngineStorage:
    def __init__(self) -> None:
        self.day = DAY
        self.day_start_ms = 1_788_000_000_000
        self.now_ms = self.day_start_ms + 10_000
        self.state = GardenState(
            plants=[
                Plant("p1", "bonsai", "Moss", 0),
                Plant("p2", "rose", "Briar", 1),
            ],
            active_plant_id="p1",
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.day_start_ms)
            ],
            reward_seed="session-summary-integration",
        )
        self.addon_dir = Path("ankigarden")
        self.assets_root = self.addon_dir / "assets"
        self.due_status = DueObligationStatus()

    def save(self) -> None:
        return None

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return self.due_status

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _data) -> None:
        return None


def _engine() -> tuple[GardenGameEngine, _EngineStorage]:
    storage = _EngineStorage()
    return GardenGameEngine(_Config(), storage), storage


def _review_payload(revlog_id: int, card_id: int) -> dict[str, object]:
    return {
        "queue": 2,
        "ease": 3,
        "revlog_id": revlog_id,
        "card_id": card_id,
        "answered_at_ms": revlog_id,
        "answer_identity": f"v1|{DAY}|{card_id}|1",
        "scheduler_day": DAY,
    }


def test_detailed_engine_commit_returns_exact_awards_and_keeps_compatibility_total():
    detailed_engine, detailed_storage = _engine()
    first_id = detailed_storage.now_ms + 1
    second_id = first_id + 1
    payloads = [
        _review_payload(first_id, 101),
        _review_payload(second_id, 102),
    ]

    awards = detailed_engine.apply_same_day_reviews_with_awards(
        payloads,
        latest_revlog_id=second_id,
    )

    assert len(awards) == 2
    # Other startup tests intentionally reload ``ankigarden.game``. Verify the
    # immutable award contract structurally instead of depending on Python
    # class identity across that reload boundary.
    assert all(
        type(award).__name__ == "ReviewAward"
        and hasattr(award, "allocations")
        for award in awards
    )
    assert all(award.correlation_id.startswith("answer:") for award in awards)
    assert len({award.correlation_id for award in awards}) == 2
    assert [award.total_growth for award in awards] == [10, 10]
    assert [
        (allocation.plant_id, allocation.role, allocation.applied_units)
        for allocation in awards[0].allocations
    ] == [
        ("p1", "nurtured", 1_000),
        ("p2", "passive", 100),
    ]

    compatibility_engine, compatibility_storage = _engine()
    compatibility_total = compatibility_engine.apply_same_day_reviews(
        payloads,
        latest_revlog_id=second_id,
    )
    assert compatibility_total == sum(award.total_growth for award in awards) == 20
    assert compatibility_storage.state.last_processed_revlog_id == second_id


def test_engine_committed_result_contains_causal_receipts_and_due_rewards(monkeypatch):
    engine, storage = _engine()
    storage.state.starter_selection_complete = True
    storage.state.progression_activation_ms = storage.day_start_ms - 1
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    revlog_id = storage.now_ms + 1

    result = engine.commit_reviewer_answer(
        _review_payload(revlog_id, 101),
        latest_revlog_id=revlog_id,
        due_status=DueObligationStatus(),
    )

    assert result is not None
    assert result.origin == "local"
    assert result.daily_completion_rewarded is True
    assert {receipt.source for receipt in result.reward_receipts} >= {
        "first_eligible_answer", "todays_cards"
    }
    assert all(
        receipt.correlation_id == result.correlation_id
        for receipt in result.reward_receipts
    )
    assert all(
        transaction.correlation_id == result.correlation_id
        for transaction in result.currency_transactions
    )
    committed_receipt = result.reward_receipts[0]
    state_receipt = next(
        receipt
        for receipt in storage.state.recent_reward_receipts
        if receipt.event_key == committed_receipt.event_key
    )
    assert committed_receipt is not state_receipt
    committed_title = committed_receipt.title
    state_receipt.title = "mutated after commit"
    assert committed_receipt.title == committed_title

    result = replace(
        result,
        landmark_growth_before_units=125,
        landmark_growth_after_units=425,
        project_allocations=(
            ProjectGrowthAllocation(GrowthTargetType.MASTERY, "rose", 100),
            ProjectGrowthAllocation(GrowthTargetType.MASTERY, "rose", 0),
        ),
    )

    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    event = handler._session_event_from_result(result)
    assert event is not None
    assert event.reward_receipts == result.reward_receipts
    assert event.landmark_growth_delta_units == 300
    assert tuple(
        (row.target_type, row.target_id, row.units)
        for row in event.project_allocations
    ) == (("mastery", "rose", 100),)
    assert sum(item.amount for item in event.coin_awards) == sum(
        transaction.delta
        for transaction in result.currency_transactions
        if transaction.delta > 0
    )


def test_typed_committed_result_carries_exact_landmark_progress(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    result = CommittedAnswerResult(
        event_id="answer:landmark",
        correlation_id="answer:landmark",
        scheduler_day=DAY,
        occurred_at_ms=1_788_000_010_000,
        origin="local",
        award=ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id="answer:landmark",
        ),
        landmark_growth_before_units=125,
        landmark_growth_after_units=425,
    )

    event = handler._session_event_from_result(result)

    assert event is not None
    assert event.landmark_growth_delta_units == 300


def test_typed_committed_result_carries_generic_project_allocations(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    result = CommittedAnswerResult(
        event_id="answer:projects",
        correlation_id="answer:projects",
        scheduler_day=DAY,
        occurred_at_ms=1_788_000_010_000,
        origin="local",
        award=ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id="answer:projects",
        ),
        project_allocations=(
            ProjectGrowthAllocation(
                GrowthTargetType.LANDMARK,
                "garden_landmark",
                250,
            ),
            ProjectGrowthAllocation(
                GrowthTargetType.MASTERY,
                "bonsai",
                100,
            ),
            ProjectGrowthAllocation(
                GrowthTargetType.LEGACY,
                "garden_legacy",
                25,
            ),
            ProjectGrowthAllocation(
                GrowthTargetType.MASTERY,
                "bonsai",
                0,
            ),
        ),
    )

    event = handler._session_event_from_result(result)

    assert event is not None
    assert [(row.target_type, row.target_id, row.units) for row in event.project_allocations] == [
        ("landmark", "garden_landmark", 250),
        ("mastery", "bonsai", 100),
        ("legacy", "garden_legacy", 25),
    ]


def test_engine_committed_result_owns_standard_find_count():
    from ankigarden.garden_finds import STANDARD_FIND_REGISTRY, PreparedRewardRegistry

    engine, storage = _engine()
    # Durable storage owns outcomes outside the renderer's bounded state cache.
    outcomes = {}
    storage.stage_garden_find_outcome = lambda outcome: outcomes.setdefault(outcome.outcome_key, outcome)
    storage.garden_find_outcome = lambda key, pool: outcomes.get(f"{pool}:{key}")
    state = storage.state
    state.starter_selection_complete = True
    state.progression_activation_ms = storage.day_start_ms - 1
    for plant in state.plants:
        plant.growth_points = 35_000
    state.active_plant_id = None
    state.active_growth_target_type = "mastery"
    state.active_growth_target_id = "bonsai"
    state.active_growth_target_activation_identity = "selected-bonsai"
    state.inventory["garden_features"].append("prism_trellis")
    assert engine.equip_environment("garden_feature", "prism_trellis")[0]
    engine.initialize_reward_state()
    state.garden_find_drought_count = 74
    engine.garden_find_registry = PreparedRewardRegistry(tuple(
        item for item in STANDARD_FIND_REGISTRY if item.reward_id == "find_growth_burst"
    ))
    assert engine.observe_due_start(DueObligationStatus(review_count=1))
    result = engine.commit_reviewer_answer(
        _review_payload(storage.now_ms + 1, 101), due_status=DueObligationStatus(),
    )

    assert result is not None and result.daily_completion_rewarded
    assert result.standard_find_count == 1
    assert [item.reward_id for item in result.garden_find_outcomes if item.status == "hit"] == ["find_growth_burst"]
    assert not state.garden_find_outcomes
    # The receipt includes ordinary Growth, its 100-Growth Find, and Prism's 100 Growth.
    assert sum(row.units for row in result.project_allocations) == result.mastery_growth_delta_units
    assert result.mastery_growth_delta_units == result.award.mastery_growth_units + 20_000


def test_reviewer_find_details_fail_closed_against_engine_count(
    monkeypatch,
    caplog,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    detailed_outcome = GardenFindOutcome(
        answer_key="one",
        scheduler_day=DAY,
        status="hit",
        pool_id="standard",
        pool_version="v1",
        occurred_at="2026-08-28T10:00:01Z",
        reward_id="morning_dew",
        display_name="Morning Dew",
    )
    result = CommittedAnswerResult(
        event_id="answer:find-mismatch",
        correlation_id="answer:find-mismatch",
        scheduler_day=DAY,
        occurred_at_ms=1_788_000_010_000,
        origin="local",
        award=ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id="answer:find-mismatch",
        ),
        garden_find_outcomes=(detailed_outcome,),
        standard_find_count=2,
    )

    event = handler._session_event_from_result(result)

    assert event is not None
    assert event.total_finds == 2
    assert len(event.standard_finds) == 1

    accumulator = _empty_accumulator()
    accumulator.accept_committed(event)
    payload = accumulator.finalize(
        ended_at="2026-08-28T10:01:00Z",
        end_snapshot=SessionEndSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=1)
        ),
    )

    assert payload is not None
    summary = payload.segments[0]
    assert summary.total_finds == 2
    assert summary.find_items == ()
    assert summary.find_items_reconciled is False
    live = accumulator.live_snapshot(
        ended_at="2026-08-28T10:01:00Z",
        end_snapshot=SessionEndSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=1)
        ),
    )
    assert live.footer_find_count == 2
    assert "Session Summary Find details omitted" in caplog.text


def test_reviewer_promotes_only_canonically_rare_standard_finds(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    outcomes = tuple(
        GardenFindOutcome(
            answer_key=tier.casefold(),
            scheduler_day=DAY,
            status="hit",
            pool_id="standard",
            pool_version="v1",
            occurred_at=f"2026-08-28T10:00:0{index}Z",
            reward_id=f"find_{tier.casefold()}",
            display_name=f"{tier} Find",
            tier=tier,
        )
        for index, tier in enumerate(("Rare", "Exceptional", "Uncommon"), start=1)
    )
    result = CommittedAnswerResult(
        event_id="answer:rarity",
        correlation_id="answer:rarity",
        scheduler_day=DAY,
        occurred_at_ms=1_788_000_010_000,
        origin="local",
        award=ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id="answer:rarity",
        ),
        garden_find_outcomes=outcomes,
        standard_find_count=3,
    )

    event = handler._session_event_from_result(result)

    assert event is not None
    assert [find.notable for find in event.standard_finds] == [True, True, False]
    assert reviewer_module._standard_find_is_notable(
        SimpleNamespace(tier="common", notable=True)
    ) is True


def _load_reviewer_module(monkeypatch):
    aqt_module = types.ModuleType("aqt")
    aqt_module.mw = SimpleNamespace(
        state="review",
        reviewer=None,
        col=SimpleNamespace(),
    )
    utils_module = types.ModuleType("aqt.utils")
    utils_module.tooltip = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "aqt", aqt_module)
    monkeypatch.setitem(sys.modules, "aqt.utils", utils_module)
    module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    module.mw = aqt_module.mw
    return module


class _AccumulatorSpy:
    current_anki_day_id = DAY

    def __init__(self) -> None:
        self.events: list[object] = []

    def accept_committed(self, event: object) -> bool:
        self.events.append(event)
        return True


class _ReviewerStorage:
    def __init__(self, *, proven: bool) -> None:
        self.proven = proven
        self.row = (2_000, 7, 3, 10, 5, 2_500, 100, 1)
        self.state = SimpleNamespace(
            last_processed_revlog_id=1_000,
            processed_revlog_floor=999,
            processed_revlog_ids=[],
            pending_reanswer_lineages={},
            answer_lineage_bindings={},
            starter_selection_complete=False,
            daily_stats=SimpleNamespace(reviewed=0, day=DAY),
        )
        self.mw = SimpleNamespace(col=SimpleNamespace())
        self.full_day_reads = 0

    def current_scheduler_day(self) -> str:
        return DAY

    def ensure_revlog_ledger_ready(self) -> None:
        return None

    def pending_reanswer_lineages(self):
        return {}

    def load_proven_local_answer(self, **_kwargs):
        if not self.proven:
            return None
        return SimpleNamespace(row=self.row, card_day_rows=(self.row,))

    def max_revlog_id(self) -> int:
        return int(self.row[0])

    def load_new_revlog_entries(self, _after_id):
        self.full_day_reads += 1
        return [self.row]

    def answer_lineage_bindings_for_cards(self, _card_ids):
        return {}

    def deck_ids_for_cards(self, _card_ids):
        return {7: 55}

    def due_obligations(self):
        return SimpleNamespace(complete=False)


class _ReviewerEngine:
    def __init__(self, storage: _ReviewerStorage) -> None:
        self.storage = storage
        self.committed_payloads: list[dict[str, object]] = []
        self.evaluate_calls: list[bool] = []

    def apply_same_day_reviews_with_results(
        self,
        payloads,
        *,
        latest_revlog_id,
        due_status=None,
    ):
        self.committed_payloads.extend(payloads)
        self.storage.state.last_processed_revlog_id = latest_revlog_id
        award = ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id=f"answer:{latest_revlog_id}",
        )
        payload = payloads[-1]
        return (CommittedAnswerResult(
            event_id=award.correlation_id,
            correlation_id=award.correlation_id,
            scheduler_day=DAY,
            occurred_at_ms=latest_revlog_id,
            origin=str(payload.get("origin") or "local"),
            award=award,
        ),)

    def evaluate_all_due(self, _status, *, record_completed_delta=False):
        self.evaluate_calls.append(bool(record_completed_delta))
        return False, ""


class _LegacyReviewerEngine:
    """Compatibility engine exposing awards but not committed results."""

    def __init__(self, storage: _ReviewerStorage) -> None:
        self.storage = storage
        self.committed_payloads: list[dict[str, object]] = []
        self.evaluate_calls: list[bool] = []

    def apply_same_day_reviews_with_awards(
        self,
        payloads,
        *,
        latest_revlog_id,
    ):
        self.committed_payloads.extend(payloads)
        self.storage.state.last_processed_revlog_id = latest_revlog_id
        return (ReviewAward(
            None,
            10,
            0,
            0,
            0,
            correlation_id=f"answer:{latest_revlog_id}",
        ),)

    def evaluate_all_due(self, _status, *, record_completed_delta=False):
        self.evaluate_calls.append(bool(record_completed_delta))
        return False, ""


def _exercise_reviewer_commit(monkeypatch, *, proven: bool):
    reviewer_module = _load_reviewer_module(monkeypatch)
    storage = _ReviewerStorage(proven=proven)
    engine = _ReviewerEngine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    accumulator = _AccumulatorSpy()
    handler._session_summary_accumulator = accumulator
    handler.mark_history_reconciled()

    committed_event = object()
    monkeypatch.setattr(handler, "_session_event_baseline", lambda: {"exact": True})
    monkeypatch.setattr(
        handler,
        "_committed_session_event",
        lambda **_kwargs: committed_event,
    )
    monkeypatch.setattr(
        handler,
        "_session_event_from_result",
        lambda _result: committed_event,
    )
    monkeypatch.setattr(handler, "_committed_growth_snapshot", lambda _state: {})
    monkeypatch.setattr(handler, "_show_committed_growth_feedback", lambda *_a, **_k: None)
    monkeypatch.setattr(handler, "_show_optional_progress_feedback", lambda: None)
    monkeypatch.setattr(handler, "_ensure_reviewer_hud", lambda **_kwargs: None)

    handler._process_answer(None, SimpleNamespace(id=7), 3)
    return handler, storage, engine, accumulator, committed_event


def test_legacy_commit_that_enters_footer_also_enters_reward_history(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    storage = _ReviewerStorage(proven=True)
    engine = _LegacyReviewerEngine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    accumulator = _AccumulatorSpy()
    handler._session_summary_accumulator = accumulator
    handler.mark_history_reconciled()
    event = CommittedSessionEvent(
        event_id="answer:2000",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:00:00Z",
        plant_growth=(PlantGrowthDelta("p1", "Moss", 1_000),),
    )

    monkeypatch.setattr(handler, "_session_event_baseline", lambda: {"exact": True})
    monkeypatch.setattr(
        handler,
        "_committed_session_event",
        lambda **_kwargs: event,
    )
    monkeypatch.setattr(handler, "_committed_growth_snapshot", lambda _state: {})
    monkeypatch.setattr(handler, "_show_committed_growth_feedback", lambda *_a, **_k: None)
    monkeypatch.setattr(handler, "_show_optional_progress_feedback", lambda: None)
    monkeypatch.setattr(handler, "_ensure_reviewer_hud", lambda **_kwargs: None)

    handler._process_answer(None, SimpleNamespace(id=7), 3)

    assert accumulator.events == [event]
    assert handler._pending_reviewer_results == [(None, event)]
    assert engine.evaluate_calls == [True]


def test_only_a_proven_local_commit_enters_the_session_accumulator(monkeypatch):
    _handler, storage, engine, accumulator, committed_event = _exercise_reviewer_commit(
        monkeypatch,
        proven=True,
    )

    assert storage.full_day_reads == 0
    assert [payload["revlog_id"] for payload in engine.committed_payloads] == [2_000]
    assert accumulator.events == [committed_event]


def test_fallback_local_recovery_enters_the_same_session_accumulator(
    monkeypatch,
):
    _handler, storage, engine, accumulator, _event = _exercise_reviewer_commit(
        monkeypatch,
        proven=False,
    )

    assert storage.full_day_reads == 1
    assert [payload["revlog_id"] for payload in engine.committed_payloads] == [2_000]
    assert engine.committed_payloads[0]["origin"] == "local_recovery"
    assert accumulator.events == [_event]


def test_reviewer_hud_is_mounted_once_and_updated_in_place(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    storage = SimpleNamespace(state=SimpleNamespace())
    routes: list[str] = []

    class _App:
        def open_dashboard(self):
            routes.append("garden")

        def open_collection(self):
            routes.append("collection")

    app = _App()
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        storage,
        open_garden=app.open_dashboard,
    )
    parent = object()
    created = []

    class _Panel:
        def __init__(self):
            self.updates = []
            self.callback_updates = []
            self.positions = []
            self.disposed = False

        def parentWidget(self):
            return parent

        def update_projection(self, projection, *, animate=False):
            self.updates.append((projection, animate))

        def set_callbacks(self, **callbacks):
            self.callback_updates.append(callbacks)

        def reposition(self, width, height):
            self.positions.append((width, height))

        def dispose(self):
            self.disposed = True

    panel = _Panel()

    def create(_parent, **callbacks):
        assert _parent is parent
        created.append(callbacks)
        return panel

    monkeypatch.setattr(reviewer_module, "create_reviewer_hud", create)
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_flush_pending_reviewer_results", lambda: None)

    first = SimpleNamespace(collapsed=False)
    second = SimpleNamespace(collapsed=False)
    handler._render_reviewer_hud(
        parent,
        first,
        viewport_width=1_600,
        viewport_height=1_000,
    )
    handler._render_reviewer_hud(
        parent,
        second,
        viewport_width=1_280,
        viewport_height=800,
    )

    assert len(created) == 1
    assert callable(created[0]["resolve_reward_art"])
    assert created[0]["animations_enabled"] is True
    assert "on_effects_overflow" not in created[0]
    assert "on_open_reward" not in created[0]
    created[0]["on_open_collection"]()
    assert routes == ["collection"]
    assert handler._reviewer_hud is panel
    assert panel.updates == [(first, False), (second, False)]
    assert panel.positions == [(1_600, 1_000), (1_280, 800)]
    assert len(panel.callback_updates) == 1
    assert panel.callback_updates[0]["animations_enabled"] is True

    handler._hide_reviewer_hud()
    assert panel.disposed is True


def test_reviewer_hud_accepts_committed_result_before_session_snapshot(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    parent = object()
    calls = []

    class _Panel:
        def parentWidget(self):
            return parent

        def update_projection(self, _projection, *, animate=False):
            calls.append(("projection", animate))

        def set_callbacks(self, **_callbacks):
            return None

        def reposition(self, _width, _height):
            return None

    handler._reviewer_hud = _Panel()
    monkeypatch.setattr(
        handler,
        "_flush_pending_reviewer_results",
        lambda: calls.append(("committed", True)),
    )
    monkeypatch.setattr(
        handler,
        "_update_reviewer_hud_session_totals",
        lambda: calls.append(("session", True)),
    )
    handler._pending_reviewer_results = [(object(), object())]

    handler._render_reviewer_hud(
        parent,
        SimpleNamespace(collapsed=False),
        viewport_width=1_600,
        viewport_height=1_000,
    )

    assert calls == [("projection", True), ("committed", True)]

    calls.clear()
    handler._pending_reviewer_results = []
    handler._render_reviewer_hud(
        parent,
        SimpleNamespace(collapsed=False),
        viewport_width=1_600,
        viewport_height=1_000,
    )

    assert calls == [("projection", False), ("session", True)]


def test_reviewer_hud_preserves_accepted_reward_state_across_remount(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    parent = object()
    preserved = {
        "seen_bundle_ids": ("answer:1",),
        "history": (SimpleNamespace(bundle_id="answer:1"),),
        "pending": (SimpleNamespace(bundle_id="answer:2"),),
        "unseen_major": 1,
    }

    class _Panel:
        def __init__(self, *, reward_state=None):
            self.reward_state = reward_state
            self.restored = []
            self.updates = []

        def parentWidget(self):
            return parent

        def update_projection(self, projection, *, animate=False):
            self.updates.append((projection, animate))

        def reposition(self, _width, _height):
            return None

        def export_reward_state(self):
            return self.reward_state

        def restore_reward_state(self, snapshot):
            self.restored.append(snapshot)

        def dispose(self):
            return None

    panels = [_Panel(reward_state=preserved), _Panel()]
    monkeypatch.setattr(
        reviewer_module,
        "create_reviewer_hud",
        lambda _parent, **_callbacks: panels.pop(0),
    )
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_flush_pending_reviewer_results", lambda: None)

    projection = SimpleNamespace(collapsed=False)
    handler._render_reviewer_hud(
        parent,
        projection,
        viewport_width=1_600,
        viewport_height=1_000,
    )
    first = handler._reviewer_hud
    handler._hide_reviewer_hud()
    handler._render_reviewer_hud(
        parent,
        projection,
        viewport_width=1_600,
        viewport_height=1_000,
    )
    second = handler._reviewer_hud

    assert first is not second
    assert second.restored == [preserved]
    assert handler._reviewer_hud_reward_state is None

    handler._reviewer_hud_reward_state = preserved
    handler._start_reviewer_session_totals()
    assert handler._reviewer_hud_reward_state is None


def test_reviewer_hud_honors_reduced_motion_configuration(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    values = {"enable_animations": True, "reduced_motion": True}
    engine = SimpleNamespace(
        config=SimpleNamespace(
            value=lambda key, default=None: values.get(key, default)
        )
    )
    handler = reviewer_module.ReviewerHookHandler(
        engine,
        SimpleNamespace(state=SimpleNamespace()),
    )

    assert handler._session_summary_animations_enabled() is False


def test_committed_result_enters_reward_dock_once(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    presented = []
    acknowledged = []

    class _Panel:
        def present_reward(self, bundle, *, reveal=True):
            presented.append((bundle, reveal))
            return True

    event = CommittedSessionEvent(
        event_id="answer:1",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:00:00Z",
        plant_growth=(PlantGrowthDelta("p1", "Moss", 1_000),),
        shared_growth=(PlantGrowthDelta("p2", "Briar", 200),),
        stored_growth_delta_units=50,
    )
    award = ReviewAward(
        "p1",
        10,
        0,
        0,
        0,
        correlation_id="answer:1",
    )
    result = CommittedAnswerResult(
        event_id="answer:1",
        correlation_id="answer:1",
        scheduler_day=DAY,
        occurred_at_ms=2_000,
        origin="local",
        award=award,
    )
    handler._reviewer_hud = _Panel()
    handler._pending_reviewer_results = [(result, event)]
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_retry_reviewer_feedback_acknowledgements", lambda: None)
    monkeypatch.setattr(
        handler,
        "_acknowledge_reviewer_result_feedback",
        lambda accepted: acknowledged.append(accepted.event_id),
    )

    handler._flush_pending_reviewer_results()
    handler._flush_pending_reviewer_results()

    assert len(presented) == 1
    assert presented[0][0].bundle_id == "answer:1"
    assert presented[0][1] is True
    assert acknowledged == ["answer:1"]
    assert handler._pending_reviewer_results == []
    assert handler._presented_reviewer_result_ids == {"answer:1"}


def test_committed_result_prefers_integrated_hud_entrypoint(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    presented = []
    acknowledged = []

    class _Panel:
        def present_committed_result(
            self,
            bundle,
            *,
            applied_growth_units=0,
            reveal=True,
        ):
            presented.append((bundle, applied_growth_units, reveal))
            return True

        def present_reward(self, bundle, *, reveal=True):
            raise AssertionError("legacy reward entrypoint must not be preferred")

    event = CommittedSessionEvent(
        event_id="answer:integrated",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:00:00Z",
        plant_growth=(PlantGrowthDelta("p1", "Moss", 1_000),),
        shared_growth=(PlantGrowthDelta("p2", "Briar", 200),),
        stored_growth_delta_units=50,
    )
    award = ReviewAward(
        "p1",
        10,
        0,
        0,
        0,
        correlation_id="answer:integrated",
    )
    result = CommittedAnswerResult(
        event_id="answer:integrated",
        correlation_id="answer:integrated",
        scheduler_day=DAY,
        occurred_at_ms=2_000,
        origin="local",
        award=award,
    )
    handler._reviewer_hud = _Panel()
    handler._pending_reviewer_results = [(result, event)]
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_retry_reviewer_feedback_acknowledgements", lambda: None)
    monkeypatch.setattr(
        handler,
        "_acknowledge_reviewer_result_feedback",
        lambda accepted: acknowledged.append(accepted.event_id),
    )

    handler._flush_pending_reviewer_results()
    handler._flush_pending_reviewer_results()

    assert len(presented) == 1
    assert presented[0][0].bundle_id == "answer:integrated"
    assert presented[0][1] == award.total_growth_units
    assert presented[0][2] is True
    assert acknowledged == ["answer:integrated"]
    assert handler._pending_reviewer_results == []
    assert handler._presented_reviewer_result_ids == {"answer:integrated"}


def test_legacy_session_event_uses_same_integrated_history_entrypoint(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    presented = []

    class _Panel:
        def present_committed_result(
            self,
            bundle,
            *,
            applied_growth_units=0,
            reveal=True,
        ):
            presented.append((bundle, applied_growth_units, reveal))
            return True

    event = CommittedSessionEvent(
        event_id="answer:legacy",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:00:00Z",
        plant_growth=(PlantGrowthDelta("p1", "Moss", 1_000),),
        shared_growth=(PlantGrowthDelta("p2", "Briar", 200),),
        stored_growth_delta_units=50,
    )
    handler._reviewer_hud = _Panel()
    handler._pending_reviewer_results = [(None, event)]
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_retry_reviewer_feedback_acknowledgements", lambda: None)

    handler._flush_pending_reviewer_results()
    handler._flush_pending_reviewer_results()

    assert len(presented) == 1
    assert presented[0][0].bundle_id == "answer:legacy"
    # Shared Growth is an independently tracked fan-out lane; the routine
    # answer feedback owns direct plus newly stored Growth only.
    assert presented[0][1] == 1_050
    assert presented[0][2] is True
    assert handler._pending_reviewer_results == []
    assert handler._presented_reviewer_result_ids == {"answer:legacy"}


def test_zero_reward_commit_notifies_hud_once_without_a_bundle(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
    )
    notified: list[str] = []

    class _Panel:
        def notify_committed_card(self, event_id):
            notified.append(event_id)
            return True

    event = CommittedSessionEvent(
        event_id="answer:no-reward",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:00:00Z",
    )
    handler._reviewer_hud = _Panel()
    handler._pending_reviewer_results = [(None, event)]
    monkeypatch.setattr(handler, "_update_reviewer_hud_session_totals", lambda: None)
    monkeypatch.setattr(handler, "_retry_reviewer_feedback_acknowledgements", lambda: None)

    handler._flush_pending_reviewer_results()
    handler._flush_pending_reviewer_results()

    assert notified == ["answer:no-reward"]
    assert handler._pending_reviewer_results == []
    assert handler._presented_reviewer_result_ids == {"answer:no-reward"}


def test_reviewer_event_builder_preserves_exact_reward_categories(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    p1 = Plant("p1", "bonsai", "Moss", 0)
    p2 = Plant("p2", "rose", "Briar", 1)
    p1.growth_units = 1_000
    p2.growth_units = 200
    positive_coin = CurrencyTransaction(
        "coin:daily",
        f"daily_activity:{DAY}",
        "First card of the Anki day",
        2,
        2,
        "2026-08-28T10:00:00Z",
        source="daily_activity",
        correlation_id="answer:local",
    )
    checkpoint_coin = CurrencyTransaction(
        "coin:checkpoint",
        "stage_checkpoint:p1:sprout:25",
        "Sprout checkpoint",
        1,
        3,
        "2026-08-28T10:00:01Z",
        source="plant_checkpoint",
        correlation_id="answer:local",
        included_in_total=False,
    )
    excluded_spend = CurrencyTransaction(
        "coin:purchase",
        "purchase:test",
        "Nursery purchase",
        -50,
        0,
        "2026-08-28T10:00:02Z",
        source="purchase",
        correlation_id="purchase:test",
    )
    find = GardenFindOutcome(
        answer_key="local",
        scheduler_day=DAY,
        status="hit",
        pool_id="standard",
        pool_version="v1",
        occurred_at="2026-08-28T10:00:03Z",
        reward_id="morning_dew",
        reward_type="growth",
        amount=40,
        display_name="Morning Dew",
        description="+40 Plant Growth",
        tier="common",
    )
    state = SimpleNamespace(
        plants=[p1, p2],
        stored_growth_units=75,
        garden_project=SimpleNamespace(contributed_growth_units=425),
        currency_transactions=[positive_coin, checkpoint_coin, excluded_spend],
        garden_find_outcomes={"standard:local": find},
        inventory={
            "weather": ["default", "fireflies"],
            "scenery": ["default"],
        },
    )
    storage = SimpleNamespace(state=state, current_scheduler_day=lambda: DAY)
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)
    monkeypatch.setattr(handler, "_plant_art_asset", lambda _plant: "")
    award = ReviewAward(
        "p1",
        10,
        0,
        0,
        0,
        allocations=(
            GrowthAllocation("p1", "active", 0, 10, applied_units=1_000),
            GrowthAllocation("p2", "passive", 0, 2, applied_units=200),
        ),
        correlation_id="answer:local",
        garden_find_ids=("fireflies",),
    )

    event = handler._committed_session_event(
        payload={"answered_at_ms": 1_788_000_010_000, "scheduler_day": DAY},
        award=award,
        baseline={
            "plant_units": {"p1": 0, "p2": 0},
            "stored_units": 0,
            "landmark_units": 125,
            "transaction_ids": set(),
            "find_outcome_ids": set(),
            "owned_environment_ids": {"default"},
        },
    )

    assert event is not None
    assert [(item.plant_id, item.growth_units) for item in event.plant_growth] == [
        ("p1", 1_000)
    ]
    assert [(item.plant_id, item.growth_units) for item in event.shared_growth] == [
        ("p2", 200)
    ]
    assert event.landmark_growth_delta_units == 300
    assert event.project_allocations == ()
    assert event.stored_growth_delta_units == 75
    assert event.landmark_growth_delta_units == 300
    assert [(item.event_id, item.amount) for item in event.coin_awards] == [
        ("coin:daily", 2),
        ("coin:checkpoint", 1),
    ]
    assert [item.included_in_total for item in event.coin_awards] == [True, False]
    assert [item.find_id for item in event.standard_finds] == ["morning_dew"]
    assert [item.event_id for item in event.milestones] == [
        "stage_checkpoint:p1:sprout:25"
    ]
    assert event.milestones[0].plant_class == "Bonsai"
    assert event.milestones[0].coin_included_in_total is False
    assert [item.environment_id for item in event.environment_discoveries] == [
        "firefly_lantern"
    ]


def test_reviewer_environment_baseline_tracks_canonical_and_legacy_inventory(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    state = SimpleNamespace(
        plants=(),
        stored_growth_units=0,
        currency_transactions=(),
        garden_find_outcomes={},
        recent_reward_receipts=(),
        inventory={
            "garden_features": ["seedling_sign", "firefly_lantern"],
            "weather": ["fireflies"],
            "scenery": ["full_moon"],
        },
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=state),
    )

    assert handler._session_event_baseline()["owned_environment_ids"] == {
        "seedling_sign",
        "firefly_lantern",
        "fireflies",
        "full_moon",
    }


def test_reviewer_event_builder_preserves_atomic_multi_stage_crossings(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    plant = Plant("p1", "rose", "Rose", 0)
    young_coin = CurrencyTransaction(
        "coin:young",
        "stage:p1:young",
        "Young stage",
        10,
        10,
        "2026-08-28T10:00:00Z",
        source="plant_stage",
        correlation_id="answer:local",
    )
    mature_coin = CurrencyTransaction(
        "coin:mature",
        "stage:p1:mature",
        "Mature stage",
        20,
        30,
        "2026-08-28T10:00:01Z",
        source="plant_stage",
        correlation_id="answer:local",
    )
    state = SimpleNamespace(
        plants=[plant],
        stored_growth_units=0,
        currency_transactions=[young_coin, mature_coin],
        garden_find_outcomes={},
        inventory={"weather": ["default"], "scenery": ["default"]},
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=state, current_scheduler_day=lambda: DAY),
    )
    monkeypatch.setattr(handler, "_plant_art_asset", lambda _plant: "")

    event = handler._committed_session_event(
        payload={"answered_at_ms": 1_788_000_010_000, "scheduler_day": DAY},
        award=SimpleNamespace(
            correlation_id="answer:local",
            allocations=(),
            garden_find_ids=(),
        ),
        baseline={
            "plant_units": {"p1": 0},
            "stored_units": 0,
            "transaction_ids": set(),
            "find_outcome_ids": set(),
            "owned_environment_ids": {"default"},
        },
    )

    assert event is not None
    assert [item.event_id for item in event.milestones] == [
        "stage:p1:young",
        "stage:p1:mature",
    ]
    assert [item.milestone_type for item in event.milestones] == [
        "stage_change",
        "stage_change",
    ]
    assert [item.plant_class for item in event.milestones] == ["Rose", "Rose"]
    assert [item.stage_path for item in event.milestones] == [
        ("sprout", "young"),
        ("young", "mature"),
    ]
    assert [item.coin_reward for item in event.milestones] == [10, 20]


def _empty_accumulator() -> SessionSummaryAccumulator:
    return SessionSummaryAccumulator(
        session_id="local-session",
        started_at="2026-08-28T10:00:00Z",
        anki_day_id=DAY,
        start_snapshot=SessionStartSnapshot(
            TodayCardsSnapshot(
                "in_progress",
                cards_remaining=20,
                cards_completed=0,
                cards_total=20,
            )
        ),
    )


def test_summary_lifecycle_calls_the_injected_engine_session_hooks(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    calls: list[str] = []
    plant = SimpleNamespace(
        plant_id="plant-1",
        name="Moss",
        fertilizer_card_batches=(SimpleNamespace(
            effect_id="fertilizer_quality",
            remaining_cards=42,
            source_event_key="card:fertilizer",
        ),),
        booster_card_batches=(),
    )
    engine = SimpleNamespace(
        begin_review_session=lambda: calls.append("begin"),
        end_review_session=lambda: calls.append("end"),
        FERTILIZERS={"quality": SimpleNamespace(name="Quality Fertilizer")},
    )
    handler = reviewer_module.ReviewerHookHandler(
        engine,
        SimpleNamespace(
            current_scheduler_day=lambda: DAY,
            state=SimpleNamespace(plants=(plant,)),
        ),
    )
    fertilizer = handler._effects_snapshot().fertilizers[0]
    assert (
        fertilizer.effect_id,
        fertilizer.remaining_cards,
        fertilizer.remaining_seconds,
        fertilizer.source_event_id,
    ) == ("fertilizer:plant-1:quality", 42, 0, "card:fertilizer")
    monkeypatch.setattr(
        handler,
        "_session_start_snapshot",
        lambda: SessionStartSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=20)
        ),
    )
    monkeypatch.setattr(handler, "_schedule_session_cutoff_split", lambda: None)
    monkeypatch.setattr(
        handler,
        "_session_end_snapshot",
        lambda **_kwargs: SessionEndSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=20)
        ),
    )

    handler._begin_session_summary()
    handler._show_reviewer_session_summary()

    assert calls == ["begin", "end"]


def test_zero_card_exit_schedules_no_summary_and_duplicate_exit_schedules_once(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    storage = SimpleNamespace(state=SimpleNamespace())
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)
    monkeypatch.setattr(
        handler,
        "_session_end_snapshot",
        lambda **_kwargs: SessionEndSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=20)
        ),
    )
    renders: list[object] = []
    monkeypatch.setattr(
        handler,
        "_schedule_session_summary_render",
        lambda: renders.append(handler._pending_session_summary),
    )

    handler._session_summary_accumulator = _empty_accumulator()
    handler._show_reviewer_session_summary()
    assert renders == []
    assert handler._pending_session_summary is None

    accumulator = _empty_accumulator()
    accumulator.accept_committed(CommittedSessionEvent(
        event_id="answer:local",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:01:00Z",
    ))
    handler._session_summary_accumulator = accumulator
    handler._show_reviewer_session_summary()
    handler._show_reviewer_session_summary()
    assert len(renders) == 1
    assert renders[0].cards_completed == 1


def test_finalized_summary_refreshes_committed_home_surface_before_render(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    calls: list[str] = []
    reviewer_module.mw.state = "deckBrowser"
    reviewer_module.mw.deckBrowser = SimpleNamespace(
        refresh=lambda: calls.append("refresh")
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(end_review_session=lambda: calls.append("end")),
        SimpleNamespace(state=SimpleNamespace()),
        state_changed=lambda reason: calls.append(f"state:{reason}"),
    )
    monkeypatch.setattr(
        handler,
        "_session_end_snapshot",
        lambda **_kwargs: SessionEndSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=1)
        ),
    )
    accumulator = _empty_accumulator()
    accumulator.accept_committed(CommittedSessionEvent(
        event_id="answer:committed",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:01:00Z",
    ))
    handler._session_summary_accumulator = accumulator
    monkeypatch.setattr(
        handler,
        "_schedule_session_summary_render",
        lambda: calls.append("render"),
    )

    handler._show_reviewer_session_summary()

    assert calls == [
        "end",
        "state:Session summary committed",
        "refresh",
        "render",
    ]


def test_today_snapshot_unifies_new_learn_review_without_using_answer_count(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    due_tree = SimpleNamespace(
        deck_id=55,
        name="Default",
        new_count=1,
        learn_count=0,
        review_count=18,
        children=[],
    )
    completion = SimpleNamespace(
        status="in_progress",
        starting_required_cards=144,
        starting_required_cards_completed=125,
        remaining_new_cards=1,
        remaining_required_reviews=18,
        remaining_learning_steps=0,
        future_learning_steps_before_cutoff=0,
        next_learning_due_at_ms=0,
        # A repeated/relearning answer can make raw activity larger than the
        # number of scheduler obligations that have actually completed.
        cards_completed_today=126,
    )
    storage = SimpleNamespace(
        state=SimpleNamespace(
            daily_completion=completion,
            daily_stats=SimpleNamespace(reviewed=126),
        ),
        mw=SimpleNamespace(
            col=SimpleNamespace(
                sched=SimpleNamespace(deck_due_tree=lambda: due_tree),
                decks=SimpleNamespace(get_current_id=lambda: 55),
            ),
        ),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)

    snapshot = handler._today_cards_snapshot(refresh=False)

    assert snapshot.cards_completed == 125
    assert snapshot.cards_remaining == 19
    assert snapshot.currently_due_cards == 19
    assert snapshot.cards_total == 144
    assert snapshot.continuation_target == ReviewContinuationTarget(
        "deck",
        55,
        "Default",
    )
    assert snapshot.can_continue_reviews


def test_today_snapshot_does_not_continue_into_another_deck(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    tree = SimpleNamespace(
        deck_id=0,
        new_count=0,
        learn_count=0,
        review_count=0,
        children=[
            SimpleNamespace(deck_id=33, name="Finished", new_count=0, learn_count=0, review_count=0, children=[]),
            SimpleNamespace(
                deck_id=11,
                name="New",
                new_count=1,
                learn_count=0,
                review_count=0,
                children=[],
            ),
            SimpleNamespace(
                deck_id=22,
                name="Due",
                new_count=0,
                learn_count=0,
                review_count=18,
                children=[],
            ),
        ],
    )
    completion = SimpleNamespace(
        status="in_progress",
        starting_required_cards=19,
        starting_required_cards_completed=0,
        remaining_new_cards=1,
        remaining_required_reviews=18,
        remaining_learning_steps=0,
        future_learning_steps_before_cutoff=0,
        next_learning_due_at_ms=0,
    )
    storage = SimpleNamespace(
        state=SimpleNamespace(daily_completion=completion),
        mw=SimpleNamespace(
            col=SimpleNamespace(
                sched=SimpleNamespace(deck_due_tree=lambda: tree),
                decks=SimpleNamespace(get_current_id=lambda: 33),
            ),
        ),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)

    snapshot = handler._today_cards_snapshot(refresh=False)

    assert snapshot.cards_remaining == snapshot.currently_due_cards == 19
    assert snapshot.contributing_deck_count == 2
    assert snapshot.continuation_target is None
    assert not snapshot.can_continue_reviews


def test_today_snapshot_hides_continue_when_future_learning_is_outside_target(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    due_tree = SimpleNamespace(
        deck_id=55,
        name="Default",
        new_count=0,
        learn_count=0,
        review_count=18,
        children=[],
    )
    completion = SimpleNamespace(
        status="in_progress",
        starting_required_cards=19,
        starting_required_cards_completed=0,
        remaining_new_cards=0,
        remaining_required_reviews=18,
        remaining_learning_steps=0,
        future_learning_steps_before_cutoff=1,
        next_learning_due_at_ms=2_000_000_000_000,
    )
    storage = SimpleNamespace(
        state=SimpleNamespace(daily_completion=completion),
        mw=SimpleNamespace(
            col=SimpleNamespace(
                sched=SimpleNamespace(deck_due_tree=lambda: due_tree),
                decks=SimpleNamespace(get_current_id=lambda: 55),
            ),
        ),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)

    snapshot = handler._today_cards_snapshot(refresh=False)

    assert snapshot.cards_remaining == 19
    assert snapshot.currently_due_cards == 18
    assert snapshot.continuation_target is None
    assert not snapshot.can_continue_reviews


def test_today_snapshot_keeps_current_learning_cards_reviewable(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    due_tree = SimpleNamespace(
        deck_id=55,
        name="Default",
        new_count=0,
        learn_count=2,
        review_count=0,
        children=[],
    )
    completion = SimpleNamespace(
        status="in_progress",
        starting_required_cards=2,
        starting_required_cards_completed=0,
        remaining_new_cards=0,
        remaining_required_reviews=0,
        remaining_learning_steps=2,
        future_learning_steps_before_cutoff=0,
        next_learning_due_at_ms=0,
    )
    storage = SimpleNamespace(
        state=SimpleNamespace(daily_completion=completion),
        mw=SimpleNamespace(
            col=SimpleNamespace(
                sched=SimpleNamespace(deck_due_tree=lambda: due_tree),
                decks=SimpleNamespace(get_current_id=lambda: 55),
            ),
        ),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)

    snapshot = handler._today_cards_snapshot(refresh=False)

    assert snapshot.cards_remaining == 2
    assert snapshot.currently_due_cards == 2
    assert snapshot.waiting_cards == 0
    assert snapshot.can_continue_reviews
    assert snapshot.continuation_target == ReviewContinuationTarget(
        "deck", 55, "Default"
    )


def test_continue_reviews_uses_native_overview_timebox_review_path(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    calls: list[str] = []

    def move_to_state(state):
        calls.append(state)
        reviewer_module.mw.state = state

    reviewer_module.mw.state = "deckBrowser"
    reviewer_module.mw.moveToState = move_to_state
    selected = {"id": 1}

    def select_deck(deck_id):
        selected["id"] = int(deck_id)
        calls.append(f"select:{deck_id}")

    reviewer_module.mw.col.startTimebox = lambda: calls.append("timebox")
    reviewer_module.mw.col.decks = SimpleNamespace(
        select=select_deck,
        get_current_id=lambda: selected["id"],
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    target = ReviewContinuationTarget("deck", 55, "Default")
    today = TodayCardsSnapshot(
        "in_progress",
        cards_remaining=18,
        cards_completed=126,
        cards_total=144,
        currently_due_cards=18,
        can_continue_reviews=True,
        continuation_target=target,
    )
    handler._presented_session_summary_payload = SimpleNamespace(
        terminal_today_cards=today,
    )
    monkeypatch.setattr(handler, "_today_cards_snapshot", lambda **_kwargs: today)

    assert handler._continue_reviews_from_session_summary() is True
    assert calls == ["select:55", "overview", "timebox", "review"]


def test_continue_reviews_revalidates_current_today_scope(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    calls: list[str] = []
    reviewer_module.mw.state = "deckBrowser"
    reviewer_module.mw.moveToState = lambda state: calls.append(state)
    reviewer_module.mw.col.startTimebox = lambda: calls.append("timebox")
    reviewer_module.mw.col.decks = SimpleNamespace(
        select=lambda deck_id: calls.append(f"select:{deck_id}"),
        get_current_id=lambda: 1,
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    target = ReviewContinuationTarget("deck", 55, "Default")
    terminal = TodayCardsSnapshot(
        "in_progress",
        cards_remaining=19,
        cards_completed=125,
        cards_total=144,
        currently_due_cards=19,
        scope="all_decks",
        can_continue_reviews=True,
        continuation_target=target,
    )
    refreshed = TodayCardsSnapshot(
        "in_progress",
        cards_remaining=19,
        cards_completed=125,
        cards_total=144,
        currently_due_cards=19,
        scope="deck",
        scope_label="Default",
        can_continue_reviews=True,
        continuation_target=target,
    )
    handler._presented_session_summary_payload = SimpleNamespace(
        terminal_today_cards=terminal,
    )
    monkeypatch.setattr(
        handler,
        "_today_cards_snapshot",
        lambda **_kwargs: refreshed,
    )

    assert handler._continue_reviews_from_session_summary() is False
    assert calls == []


def test_continue_reviews_failure_returns_false_without_dismissing_card(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    reviewer_module.mw.state = "deckBrowser"
    reviewer_module.mw.moveToState = lambda _state: None
    selected = {"id": 1}
    reviewer_module.mw.col.startTimebox = lambda: None
    reviewer_module.mw.col.decks = SimpleNamespace(
        select=lambda deck_id: selected.__setitem__("id", int(deck_id)),
        get_current_id=lambda: selected["id"],
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    sentinel = object()
    handler._session_summary_card = sentinel
    target = ReviewContinuationTarget("deck", 55, "Default")
    today = TodayCardsSnapshot(
        "in_progress",
        cards_remaining=18,
        cards_completed=126,
        cards_total=144,
        currently_due_cards=18,
        can_continue_reviews=True,
        continuation_target=target,
    )
    handler._presented_session_summary_payload = SimpleNamespace(
        terminal_today_cards=today,
    )
    monkeypatch.setattr(handler, "_today_cards_snapshot", lambda **_kwargs: today)
    dismissed: list[bool] = []
    monkeypatch.setattr(
        handler,
        "_hide_session_summary",
        lambda **_kwargs: dismissed.append(True),
    )

    assert handler._continue_reviews_from_session_summary() is False
    assert handler._session_summary_card is sentinel
    assert dismissed == []
    assert selected["id"] == 1


def test_summary_finalizes_only_when_leaving_review_then_dismisses_on_navigation(
    monkeypatch,
):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    events: list[str] = []
    monkeypatch.setattr(
        handler,
        "_show_reviewer_session_summary",
        lambda: events.append("finalize"),
    )
    monkeypatch.setattr(
        handler,
        "dismiss_session_summary_for_navigation",
        lambda *_args: events.append("dismiss"),
    )
    monkeypatch.setattr(handler, "_hide_reward_toast", lambda: None)
    monkeypatch.setattr(handler, "_hide_reviewer_hud", lambda: None)
    monkeypatch.setattr(handler, "_hide_no_starter_notice", lambda: None)

    handler.on_state_change("deckBrowser", "review")
    handler.on_state_change("overview", "deckBrowser")

    assert events == ["finalize", "dismiss"]


def test_dismissed_summary_generation_cannot_replay_a_newer_payload(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    newer_payload = object()
    handler._pending_session_summary = newer_payload
    handler._session_summary_render_scheduled = True
    handler._session_summary_presentation_generation = 4

    handler._present_pending_session_summary(expected_generation=3)

    assert handler._pending_session_summary is newer_payload
    assert handler._session_summary_render_scheduled is True


def test_session_summary_escape_is_modal_guarded_and_coordinator_owned(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)

    class _Coordinator:
        def __init__(self) -> None:
            self.active_kind = "session"
            self.dismissed: list[str] = []

        def owns(self, kind: str) -> bool:
            return self.active_kind == kind

        def dismiss(self, reason: str) -> bool:
            self.dismissed.append(reason)
            return True

    coordinator = _Coordinator()
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=SimpleNamespace()),
        summary_coordinator=coordinator,
    )

    monkeypatch.setattr(reviewer_module, "reviewer_modal_active", lambda _mw: True)
    handler._dismiss_session_summary_on_escape()
    assert coordinator.dismissed == []

    monkeypatch.setattr(reviewer_module, "reviewer_modal_active", lambda _mw: False)
    coordinator.active_kind = "sync"
    handler._dismiss_session_summary_on_escape()
    assert coordinator.dismissed == []

    coordinator.active_kind = "session"
    handler._dismiss_session_summary_on_escape()
    assert coordinator.dismissed == ["escape"]


def test_recovery_rows_admit_only_one_unambiguous_current_window_answer(monkeypatch):
    reviewer_module = _load_reviewer_module(monkeypatch)
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(), SimpleNamespace(state=SimpleNamespace())
    )
    handler._review_window_started_after_revlog_id = 1_000
    card = SimpleNamespace(id=7)
    current = (2_000, 7, 3, 10, 5, 2_500, 100, 1)
    stale = (1_500, 8, 3, 10, 5, 2_500, 100, 1)

    assert handler._current_review_revlog_id(
        [stale, current], card, 3, proven_local_commit=False
    ) == 2_000
    assert handler._current_review_revlog_id(
        [current, (2_100, 9, 3, 10, 5, 2_500, 100, 1)],
        card,
        3,
        proven_local_commit=False,
    ) == 0


def test_session_summary_projection_contains_no_prohibited_progress_copy():
    accumulator = _empty_accumulator()
    accumulator.accept_committed(CommittedSessionEvent(
        event_id="answer:local",
        anki_day_id=DAY,
        occurred_at="2026-08-28T10:01:00Z",
    ))
    payload = accumulator.finalize(
        ended_at="2026-08-28T10:02:00Z",
        end_snapshot=SessionEndSnapshot(
            TodayCardsSnapshot(
                "waiting_for_learning",
                cards_remaining=2,
                cards_completed=18,
                cards_total=20,
                waiting_cards=2,
                next_due_in_seconds=360,
            )
        ),
    )
    assert payload is not None
    projection_text = " ".join(
        str(value)
        for value in _walk_text(asdict(project_session_day(payload.segments[0])))
    ).casefold()

    assert "required card" not in projection_text
    assert "all clear" not in projection_text
    assert "daily care" not in projection_text
    assert "find drought" not in projection_text
    assert "find cap" not in projection_text
    assert re.search(r"\b\d[\d,]*\s+answers?\b", projection_text) is None
    assert "2 cards left" in projection_text
    assert "18 / 20 completed" in projection_text
    assert "next card in 6 minutes" in projection_text


def _walk_text(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_text(item)
    elif isinstance(value, str):
        yield value
