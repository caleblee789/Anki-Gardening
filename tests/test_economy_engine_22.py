from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.economy_progression import (
    LandmarkAction,
    LandmarkRequest,
    MasteryRequest,
    ProgressionDisposition,
)
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
from ankigarden.reward_ledger import EconomyEventRecord, IdempotencyRecord
from ankigarden.storage import DueObligationStatus


class _Config:
    def value(self, key, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys, default=None):
        node = DEFAULT_CONFIG
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _Storage:
    def __init__(self) -> None:
        self.day = "2026-08-30"
        self.now_ms = 1_788_100_000_000
        full = Plant("p1", "bonsai", "Moss", 0, growth_points=35_000)
        self.state = GardenState(
            plants=[full],
            active_plant_id=None,
            starter_selection_complete=True,
            garden_setup_version=1,
            unlocked_species=["bonsai"],
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[ActivePlantPeriod(self.day, None, self.now_ms)],
            currency_balance=10_000,
            stored_growth_units=100_000_000,
        )
        self.addon_dir = Path("ankigarden")
        self.assets_root = self.addon_dir / "assets"
        self.fail_save = False
        self._pending_idempotency: dict[tuple[str, str], IdempotencyRecord] = {}
        self._idempotency: dict[tuple[str, str], IdempotencyRecord] = {}
        self._pending_events: dict[str, EconomyEventRecord] = {}
        self._events: dict[str, EconomyEventRecord] = {}

    def save(self):
        if self.fail_save:
            raise OSError("disk full")
        self._idempotency.update(self._pending_idempotency)
        self._events.update(self._pending_events)
        self._pending_idempotency.clear()
        self._pending_events.clear()

    def reward_ledger_checkpoint(self):
        return (deepcopy(self._pending_idempotency), deepcopy(self._pending_events))

    def rollback_reward_ledger(self, checkpoint):
        self._pending_idempotency, self._pending_events = deepcopy(checkpoint)

    def idempotency_record(self, kind, operation_id):
        key = (str(kind), str(operation_id))
        return self._pending_idempotency.get(key) or self._idempotency.get(key)

    def stage_idempotency_record(self, record):
        self._pending_idempotency[(record.operation_kind, record.operation_id)] = record

    def stage_economy_event(self, record):
        self._pending_events[record.event_key] = record

    def refresh_lifetime_economy_aggregates(self):
        return self.state.lifetime_economy_aggregates

    def current_scheduler_day(self):
        return self.day

    def current_day_start_ms(self):
        return self.now_ms - 1_000

    def current_time_ms(self):
        return self.now_ms

    def due_obligations(self):
        return DueObligationStatus()

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _data):
        return None


def _request_id(number: int) -> str:
    return str(UUID(int=number))


def _engine() -> tuple[GardenGameEngine, _Storage]:
    storage = _Storage()
    return GardenGameEngine(_Config(), storage), storage


def test_landmark_commits_growth_then_requires_explicit_coin_completion() -> None:
    engine, storage = _engine()
    selected = engine.confirm_landmark(LandmarkRequest(
        _request_id(1), LandmarkAction.SELECT, "mossy_stone_path"
    ))
    assert selected.applied
    assert storage.state.currency_balance == 10_000

    contributed = engine.confirm_landmark(LandmarkRequest(
        _request_id(2), LandmarkAction.CONTRIBUTE, "mossy_stone_path", 2_500_000
    ))
    assert contributed.applied and contributed.snapshot.ready_to_complete
    assert storage.state.stored_growth_units == 97_500_000
    assert storage.state.currency_balance == 10_000

    completed = engine.confirm_landmark(LandmarkRequest(
        _request_id(3), LandmarkAction.COMPLETE, "mossy_stone_path"
    ))
    assert completed.applied and completed.coins_spent == 250
    assert storage.state.currency_balance == 9_750
    assert storage.state.garden_project.completed_project_ids == [
        "mossy_stone_path"
    ]
    assert storage.state.garden_project.displayed_project_id == "mossy_stone_path"


def test_landmark_replay_survives_bounded_state_history_and_conflict_rejects() -> None:
    engine, storage = _engine()
    request = LandmarkRequest(
        _request_id(10), LandmarkAction.SELECT, "mossy_stone_path"
    )
    first = engine.confirm_landmark(request)
    before = storage.state.to_dict()
    replay = engine.confirm_landmark(request)
    assert replay == first
    assert storage.state.to_dict() == before

    with pytest.raises(ValueError, match="already used"):
        engine.confirm_landmark(LandmarkRequest(
            _request_id(10), LandmarkAction.CONTRIBUTE, "mossy_stone_path", 100
        ))


def test_auto_landmark_contribution_never_spends_coins_and_conserves_growth() -> None:
    engine, storage = _engine()
    engine.select_landmark("mossy_stone_path")
    ok, _message = engine.set_landmark_auto_contribute(True)
    assert ok
    before_coins = storage.state.currency_balance
    result = engine._apply_direct_growth_units(
        None,
        3_000_000,
        stats_field="direct_reward_growth",
        transition_source="test_overflow",
    )
    assert result.conserved
    assert result.landmark_units == 2_500_000
    assert result.stored_units == 500_000
    assert storage.state.garden_project.ready_to_complete
    assert storage.state.currency_balance == before_coins


def test_mastery_requires_full_bloom_and_commits_both_resources_atomically() -> None:
    engine, storage = _engine()
    request = MasteryRequest(_request_id(20), "bonsai", "bronze")
    outcome = engine.confirm_mastery(request)
    assert outcome.applied
    assert outcome.growth_spent_units == 2_500_000
    assert outcome.coins_spent == 50
    assert storage.state.stored_growth_units == 97_500_000
    assert storage.state.currency_balance == 9_950
    assert storage.state.cultivation_mastery.highest_rank_by_species == {
        "bonsai": "bronze"
    }
    assert engine.confirm_mastery(request) == outcome

    rose = MasteryRequest(_request_id(21), "rose", "bronze")
    locked = engine.confirm_mastery(rose)
    assert not locked.applied
    assert locked.disposition is ProgressionDisposition.NOT_READY


def test_mastery_catalog_contains_only_the_ten_active_release_species() -> None:
    engine, _storage = _engine()

    summary = engine.mastery_catalog_summary()

    assert [row["species_id"] for row in summary["species"]] == [
        "bonsai",
        "rose",
        "sunflower",
        "lavender",
        "hydrangea",
        "peony",
        "foxglove",
        "japanese_maple",
        "wisteria",
        "dahlia",
    ]


def test_landmark_contribution_rolls_back_all_resources_on_save_failure() -> None:
    engine, storage = _engine()
    engine.select_landmark("mossy_stone_path")
    before = storage.state.to_dict()
    storage.fail_save = True
    with pytest.raises(OSError, match="disk full"):
        engine.confirm_landmark(LandmarkRequest(
            _request_id(30),
            LandmarkAction.CONTRIBUTE,
            "mossy_stone_path",
            1_000_000,
        ))
    assert storage.state.to_dict() == before
    assert storage.idempotency_record("landmark", _request_id(30)) is None


def test_landmark_completion_rolls_back_coin_display_and_feedback_on_save_failure() -> None:
    engine, storage = _engine()
    engine.confirm_landmark(LandmarkRequest(
        _request_id(31), LandmarkAction.SELECT, "mossy_stone_path"
    ))
    engine.confirm_landmark(LandmarkRequest(
        _request_id(32),
        LandmarkAction.CONTRIBUTE,
        "mossy_stone_path",
        2_500_000,
    ))
    before = storage.state.to_dict()
    events_before = deepcopy(storage._events)
    storage.fail_save = True

    with pytest.raises(OSError, match="disk full"):
        engine.confirm_landmark(LandmarkRequest(
            _request_id(33), LandmarkAction.COMPLETE, "mossy_stone_path"
        ))

    assert storage.state.to_dict() == before
    assert storage._events == events_before
    assert storage._pending_events == {}
    assert storage.idempotency_record("landmark", _request_id(33)) is None
    assert storage.state.garden_project.displayed_project_id == ""
    assert storage.state.garden_project.completed_project_ids == []


def test_mastery_rolls_back_both_resources_rank_and_feedback_on_save_failure() -> None:
    engine, storage = _engine()
    before = storage.state.to_dict()
    storage.fail_save = True

    with pytest.raises(OSError, match="disk full"):
        engine.confirm_mastery(
            MasteryRequest(_request_id(34), "bonsai", "bronze")
        )

    assert storage.state.to_dict() == before
    assert storage._events == {}
    assert storage._pending_events == {}
    assert storage.idempotency_record("mastery", _request_id(34)) is None
    assert storage.state.cultivation_mastery.highest_rank_by_species == {}
