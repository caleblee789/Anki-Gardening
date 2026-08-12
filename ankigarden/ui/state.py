from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from weakref import WeakMethod

from .plant_display import growth_display


@dataclass(frozen=True)
class PlantUiSnapshot:
    plant_id: str
    name: str
    species: str
    stage: str
    growth_points: int
    slot_index: int | None
    is_active: bool


@dataclass(frozen=True)
class GardenUiSnapshot:
    """Immutable, calculation-free projection shared by visible Garden surfaces."""

    garden_name: str
    active_plant_id: str
    active_plant_name: str
    active_stage: str
    active_growth_points: int
    active_stage_points: int
    active_stage_goal: int
    active_points_remaining: int
    active_next_stage: str
    active_fully_grown: bool
    streak_days: int
    streak_bonus_percent: int
    currency_balance: int
    reviewed_today: int
    growth_today: int
    selected_weather: str
    unlocked_slots: int
    plants: tuple[PlantUiSnapshot, ...]


def select_garden_ui(engine: Any, storage: Any) -> GardenUiSnapshot:
    state = storage.state
    active_id = str(getattr(state, "active_plant_id", "") or "")
    plants = tuple(
        PlantUiSnapshot(
            plant_id=str(getattr(plant, "plant_id", "") or ""),
            name=str(getattr(plant, "name", "Plant") or "Plant"),
            species=str(getattr(plant, "species", "plant") or "plant"),
            stage=str(getattr(plant, "growth_stage", "seed") or "seed"),
            growth_points=max(0, int(getattr(plant, "growth_points", 0) or 0)),
            slot_index=getattr(plant, "slot_index", None),
            is_active=str(getattr(plant, "plant_id", "") or "") == active_id,
        )
        for plant in list(getattr(state, "plants", []) or [])
    )
    active = next((plant for plant in plants if plant.is_active), None)
    active_growth = growth_display(active.growth_points if active is not None else 0)
    stats = state.daily_stats
    return GardenUiSnapshot(
        garden_name=str(getattr(state, "garden_name", "My Garden") or "My Garden"),
        active_plant_id=active_id,
        active_plant_name=active.name if active is not None else "",
        active_stage=active_growth.stage if active is not None else "",
        active_growth_points=active.growth_points if active is not None else 0,
        active_stage_points=active_growth.stage_points if active is not None else 0,
        active_stage_goal=active_growth.stage_goal if active is not None else 0,
        active_points_remaining=active_growth.points_remaining if active is not None else 0,
        active_next_stage=str(active_growth.next_stage or "") if active is not None else "",
        active_fully_grown=active_growth.fully_grown if active is not None else False,
        streak_days=max(0, int(getattr(state, "streak_days", 0) or 0)),
        streak_bonus_percent=max(0, int(engine.current_streak_bonus_percent() or 0)),
        currency_balance=max(0, int(getattr(state, "currency_balance", 0) or 0)),
        reviewed_today=max(0, int(getattr(stats, "reviewed", 0) or 0)),
        growth_today=max(0, int(getattr(stats, "growth_earned", 0) or 0)),
        selected_weather=str(getattr(state, "selected_weather", "sunny") or "sunny"),
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
        plants=plants,
    )


class _StateSignal:
    """Small Qt-independent signal so state projection can load before the UI."""

    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback: Any) -> None:
        try:
            self._callbacks.append(WeakMethod(callback))
        except TypeError:
            self._callbacks.append(callback)

    def emit(self, reason: str) -> None:
        retained: list[Any] = []
        for entry in self._callbacks:
            callback = entry() if isinstance(entry, WeakMethod) else entry
            if callback is None:
                continue
            callback(reason)
            retained.append(entry)
        self._callbacks = retained


class GardenUiCoordinator:
    """Single post-commit event boundary for every Garden surface."""

    def __init__(self, _parent: Any | None = None) -> None:
        self.stateChanged = _StateSignal()
        self.revision = 0

    def notify(self, reason: str) -> None:
        self.revision += 1
        self.stateChanged.emit(str(reason or "Garden state changed"))
