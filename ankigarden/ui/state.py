from __future__ import annotations

from dataclasses import dataclass, replace
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
    selected_background: str
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
        selected_background=str(
            getattr(state, "selected_background", "verdant_twilight")
            or "verdant_twilight"
        ),
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
        plants=plants,
    )


PREVIEW_PHASES = frozenset({
    "loading",
    "empty",
    "error",
    "disabled",
    "success",
    "stale",
})


@dataclass(frozen=True)
class GardenPreviewSnapshot:
    """Renderer-neutral scene and copy shared by every compact preview."""

    consumer: str
    phase: str
    garden_name: str
    title: str
    summary: str
    stage_text: str
    active_plant_name: str
    active_stage: str
    selected_weather: str
    selected_scenery: str
    scene_items: tuple[dict[str, Any], ...]
    unlocked_slots: int
    scene_opacity: float = 1.0
    motion_enabled: bool = True
    status_text: str = ""

    @property
    def stale(self) -> bool:
        return self.phase == "stale"


def garden_preview_snapshot(
    snapshot: GardenUiSnapshot | None,
    *,
    consumer: str,
    phase: str = "success",
    scene_items: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    enabled: bool = True,
    motion_enabled: bool = True,
    status_text: str = "",
) -> GardenPreviewSnapshot:
    return garden_preview_from_values(
        consumer=consumer,
        phase=phase,
        garden_name=(snapshot.garden_name if snapshot is not None else "My Garden"),
        active_plant_name=(snapshot.active_plant_name if snapshot is not None else ""),
        active_stage=(snapshot.active_stage if snapshot is not None else ""),
        active_growth_points=(
            snapshot.active_growth_points if snapshot is not None else 0
        ),
        active_stage_points=(
            snapshot.active_stage_points if snapshot is not None else 0
        ),
        active_stage_goal=(
            snapshot.active_stage_goal if snapshot is not None else 0
        ),
        active_fully_grown=(
            snapshot.active_fully_grown if snapshot is not None else False
        ),
        selected_weather=(snapshot.selected_weather if snapshot is not None else "sunny"),
        selected_scenery=(
            snapshot.selected_background if snapshot is not None else "verdant_twilight"
        ),
        scene_items=scene_items,
        unlocked_slots=(snapshot.unlocked_slots if snapshot is not None else 0),
        enabled=enabled,
        motion_enabled=motion_enabled,
        status_text=status_text,
    )


def garden_preview_from_values(
    *,
    consumer: str,
    phase: str = "success",
    garden_name: str = "My Garden",
    active_plant_name: str = "",
    active_stage: str = "",
    active_growth_points: int = 0,
    active_stage_points: int = 0,
    active_stage_goal: int = 0,
    active_fully_grown: bool = False,
    starter_selected: bool = True,
    planted_starter_name: str = "",
    planted_starter_stage: str = "",
    selected_weather: str = "sunny",
    selected_scenery: str = "verdant_twilight",
    scene_items: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    unlocked_slots: int = 0,
    enabled: bool = True,
    motion_enabled: bool = True,
    status_text: str = "",
) -> GardenPreviewSnapshot:
    normalized_phase = str(phase)
    if normalized_phase not in PREVIEW_PHASES:
        normalized_phase = "error"
    if not enabled:
        normalized_phase = "disabled"
    garden_name = str(garden_name or "My Garden")
    active_name = str(active_plant_name or "")
    stage = str(active_stage or "") if active_name else ""
    stage_label = stage.replace("_", " ").title() if stage else ""
    title = garden_name
    if not starter_selected and normalized_phase == "success":
        normalized_phase = "empty"
    if normalized_phase == "empty":
        title = "Choose your first plant"
        summary = "Pick a starter in the Garden to begin growing."
    elif active_name and stage_label:
        if active_fully_grown:
            summary = (
                f"{active_name}, {stage_label} — "
                f"{max(0, int(active_growth_points or 0)):,} Growth"
            )
        elif int(active_stage_goal or 0) > 0:
            summary = (
                f"{active_name}, {stage_label} — "
                f"{max(0, int(active_stage_points or 0)):,} / "
                f"{max(0, int(active_stage_goal or 0)):,} Growth"
            )
        else:
            summary = f"{active_name}, {stage_label}"
    elif planted_starter_name:
        planted_stage = str(planted_starter_stage or "seed").replace("_", " ").title()
        summary = f"{planted_starter_name}, {planted_stage}. Planted starter."
    else:
        summary = "No nurtured plant. Open the garden to choose one."
    if normalized_phase == "loading":
        summary = "Loading garden preview…"
    elif normalized_phase == "error":
        summary = status_text or "Garden preview is unavailable."
    elif normalized_phase == "stale":
        status_text = status_text or "Updating garden preview…"
    elif normalized_phase == "disabled":
        status_text = status_text or "Home previews are off."
    return GardenPreviewSnapshot(
        consumer=str(consumer),
        phase=normalized_phase,
        garden_name=garden_name,
        title=title,
        summary=summary,
        # Stage is retained separately for consumers that do not already show
        # it in their summary. Renderers must never display both.
        stage_text=stage_label,
        active_plant_name=active_name,
        active_stage=stage,
        selected_weather=str(selected_weather or "sunny"),
        selected_scenery=str(selected_scenery or "verdant_twilight"),
        scene_items=tuple(scene_items),
        unlocked_slots=max(0, min(6, int(unlocked_slots or 0))),
        scene_opacity=(
            0.46 if normalized_phase == "disabled" else
            0.72 if normalized_phase == "stale" else
            1.0
        ),
        motion_enabled=bool(motion_enabled),
        status_text=str(status_text),
    )


def preview_with_phase(
    snapshot: GardenPreviewSnapshot,
    phase: str,
    *,
    motion_enabled: bool | None = None,
    status_text: str | None = None,
) -> GardenPreviewSnapshot:
    """Project request state without replacing the last valid scene or copy."""

    normalized_phase = str(phase)
    if normalized_phase not in PREVIEW_PHASES:
        normalized_phase = "error"
    status = snapshot.status_text if status_text is None else str(status_text)
    if normalized_phase == "stale" and not status:
        status = "Updating garden preview…"
    elif normalized_phase == "disabled" and not status:
        status = "Home previews are off."
    return replace(
        snapshot,
        phase=normalized_phase,
        scene_opacity=(
            0.46 if normalized_phase == "disabled" else
            0.72 if normalized_phase == "stale" else
            1.0
        ),
        motion_enabled=(
            snapshot.motion_enabled
            if motion_enabled is None else bool(motion_enabled)
        ),
        status_text=status,
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
