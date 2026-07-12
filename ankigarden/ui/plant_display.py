from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models.state import GROWTH_STAGES, GROWTH_THRESHOLDS


@dataclass(frozen=True)
class PlantGrowthDisplay:
    stage: str
    stage_index: int
    next_stage: str | None
    stage_start: int
    next_threshold: int | None
    points_remaining: int
    progress: float
    fully_grown: bool


def growth_display(growth_points: Any, rare_variant: bool = False) -> PlantGrowthDisplay:
    try:
        points = max(0, int(growth_points))
    except (TypeError, ValueError):
        points = 0
    stage_index = 0
    for index, threshold in enumerate(GROWTH_THRESHOLDS):
        if points >= threshold:
            stage_index = index
    if rare_variant:
        stage_index = len(GROWTH_STAGES) - 1
    stage = GROWTH_STAGES[stage_index]
    fully_grown = stage_index >= len(GROWTH_STAGES) - 1
    if fully_grown:
        return PlantGrowthDisplay(stage, stage_index, None, GROWTH_THRESHOLDS[stage_index], None, 0, 1.0, True)
    next_threshold = GROWTH_THRESHOLDS[stage_index + 1]
    stage_start = GROWTH_THRESHOLDS[stage_index]
    progress = max(0.0, min(1.0, (points - stage_start) / max(1, next_threshold - stage_start)))
    return PlantGrowthDisplay(
        stage,
        stage_index,
        GROWTH_STAGES[stage_index + 1],
        stage_start,
        next_threshold,
        max(0, next_threshold - points),
        progress,
        False,
    )


def plant_layout(width: float, height: float, count: int) -> list[tuple[float, float, float, float, float, float]]:
    """Return x, baseline, and generous x/y/w/h hit bounds for each plant."""
    if count <= 0:
        return []
    safe_width = max(240.0, float(width))
    safe_height = max(240.0, float(height))
    rows: list[tuple[float, float, float, float, float, float]] = []
    for index in range(count):
        x = safe_width * ((index + 1) / (count + 1))
        baseline = safe_height * (0.755 + (0.018 if index % 2 else 0.0))
        hit_width = max(96.0, min(166.0, safe_width / max(2.4, count + 0.35)))
        hit_height = min(218.0, safe_height * 0.63)
        rows.append((x, baseline, x - hit_width / 2, baseline - hit_height, hit_width, hit_height + 22.0))
    return rows


def smart_card_rect(
    width: float, height: float, anchor_x: float, anchor_y: float, card_width: float = 252.0, card_height: float = 184.0
) -> tuple[float, float, float, float]:
    safe_width = max(card_width + 16.0, float(width))
    safe_height = max(card_height + 16.0, float(height))
    margin = 12.0
    x = anchor_x + 30.0
    if x + card_width > safe_width - margin:
        x = anchor_x - card_width - 30.0
    x = max(margin, min(x, safe_width - card_width - margin))
    y = max(margin + 48.0, anchor_y - card_height - 22.0)
    y = min(y, safe_height - card_height - margin)
    return (x, y, card_width, card_height)


def hit_test(
    layouts: list[tuple[float, float, float, float, float, float]], point_x: float, point_y: float
) -> int | None:
    for index in range(len(layouts) - 1, -1, -1):
        _x, _baseline, left, top, width, height = layouts[index]
        if left <= point_x <= left + width and top <= point_y <= top + height:
            return index
    return None


class PlantInteractionState:
    def __init__(self) -> None:
        self.hovered_id: str | None = None
        self.pinned_id: str | None = None
        self.focused_index = -1

    @property
    def active_id(self) -> str | None:
        return self.pinned_id or self.hovered_id

    def reconcile(self, plant_ids: list[str]) -> None:
        valid = set(plant_ids)
        if self.hovered_id not in valid:
            self.hovered_id = None
        if self.pinned_id not in valid:
            self.pinned_id = None
        if not plant_ids:
            self.focused_index = -1
        elif self.focused_index >= len(plant_ids):
            self.focused_index = len(plant_ids) - 1

    def hover(self, plant_id: str | None) -> None:
        self.hovered_id = plant_id

    def toggle_pin(self, plant_id: str | None) -> None:
        self.pinned_id = None if plant_id is None or self.pinned_id == plant_id else plant_id
        if plant_id is not None:
            self.hovered_id = plant_id

    def dismiss(self) -> None:
        self.pinned_id = None
        self.hovered_id = None

    def cycle_focus(self, plant_ids: list[str], direction: int) -> str | None:
        if not plant_ids:
            self.focused_index = -1
            return None
        if self.focused_index < 0:
            self.focused_index = 0 if direction >= 0 else len(plant_ids) - 1
        else:
            self.focused_index = (self.focused_index + direction) % len(plant_ids)
        self.hovered_id = plant_ids[self.focused_index]
        return self.hovered_id

    def focused_id(self, plant_ids: list[str]) -> str | None:
        if 0 <= self.focused_index < len(plant_ids):
            return plant_ids[self.focused_index]
        return None
