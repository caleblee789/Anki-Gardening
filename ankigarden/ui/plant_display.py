from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..models.state import GROWTH_STAGES, GROWTH_THRESHOLDS


SETTINGS_STACK_BREAKPOINT = 720


def settings_layout_is_compact(width: int) -> bool:
    """Return whether settings controls should stack above the preview."""
    return max(0, int(width)) < SETTINGS_STACK_BREAKPOINT


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (self.right <= other.x or other.right <= self.x or self.bottom <= other.y or other.bottom <= self.y)

    def expanded(self, x_pad: float, y_pad: float | None = None) -> "Rect":
        y_pad = x_pad if y_pad is None else y_pad
        return Rect(self.x - x_pad, self.y - y_pad, self.width + 2 * x_pad, self.height + 2 * y_pad)


@dataclass(frozen=True)
class PlantPlacement:
    slot_index: int
    draw: Rect
    visible: Rect
    hit: Rect
    footprint: Rect
    depth: float
    smart_card_anchor: Rect
    scale: float


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
    stage_points: int
    stage_goal: int


@dataclass(frozen=True)
class PlantHealthDisplay:
    label: str
    percent: int


@dataclass(frozen=True)
class AchievementProgressDisplay:
    current: int
    target: int
    value_text: str
    criteria_text: str


def achievement_progress_display(achievement: Any, state: Any) -> AchievementProgressDisplay:
    """Map persisted achievement state to useful, numeric presentation data."""
    stats = getattr(state, "daily_stats", None)
    reviewed = max(0, int(getattr(stats, "reviewed", 0) or 0))
    wrong = max(0, int(getattr(stats, "wrong", 0) or 0))
    accuracy = int(round(float(getattr(stats, "accuracy", 0.0) or 0.0) * 100))
    achievement_id = str(getattr(achievement, "achievement_id", ""))
    definitions = {
        "streak_7": (max(0, int(getattr(state, "streak_days", 0) or 0)), 7, "days", "Study 7 days in a row."),
        "streak_30": (max(0, int(getattr(state, "streak_days", 0) or 0)), 30, "days", "Study 30 days in a row."),
        "reviews_100_day": (reviewed, 100, "reviews", "Complete 100 reviews in one day."),
        "reviews_1000_total": (
            max(0, int(getattr(state, "total_reviews", 0) or 0)), 1000, "reviews", "Complete 1,000 total reviews."
        ),
        "retention_90": (accuracy, 90, "% accuracy", "Reach 90% accuracy after at least 20 reviews today."),
        "retention_100": (
            reviewed if wrong == 0 else 0, 30, "perfect reviews", "Complete 30 reviews today with 100% accuracy."
        ),
        "all_due_done": (
            1 if bool(getattr(stats, "completed_due_cards", False)) else 0, 1, "complete", "Finish all due cards today."
        ),
        "no_lapse": (
            reviewed if wrong == 0 else 0, 40, "reviews", "Complete 40 reviews today with no incorrect answers."
        ),
    }
    current, target, unit, criteria = definitions.get(
        achievement_id,
        (int(round(float(getattr(achievement, "progress", 0.0) or 0.0) * 100)), 100, "%", str(getattr(achievement, "description", ""))),
    )
    current = max(0, int(current))
    target = max(1, int(target))
    if achievement_id == "retention_90":
        value_text = f"{current} / {target}% accuracy; {reviewed} / 20 reviews"
    elif achievement_id == "all_due_done":
        value_text = "1 / 1 complete" if current else "0 / 1 complete"
    else:
        value_text = f"{current:,} / {target:,} {unit}"
    return AchievementProgressDisplay(current, target, value_text, criteria)


def plant_health_display(vitality: Any) -> PlantHealthDisplay:
    try:
        ratio = max(0.0, min(1.0, float(vitality)))
    except (TypeError, ValueError):
        ratio = 0.0
    percent = int(round(ratio * 100))
    label = "Thriving" if percent >= 85 else "Healthy" if percent >= 65 else "Needs care"
    return PlantHealthDisplay(label, percent)


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
        return PlantGrowthDisplay(
            stage, stage_index, None, GROWTH_THRESHOLDS[stage_index], None, 0, 1.0, True, 0, 0
        )
    next_threshold = GROWTH_THRESHOLDS[stage_index + 1]
    stage_start = GROWTH_THRESHOLDS[stage_index]
    stage_points = max(0, points - stage_start)
    stage_goal = max(1, next_threshold - stage_start)
    progress = max(0.0, min(1.0, stage_points / stage_goal))
    return PlantGrowthDisplay(stage, stage_index, GROWTH_STAGES[stage_index + 1], stage_start, next_threshold,
                              max(0, next_threshold - points), progress, False, stage_points, stage_goal)


def _number(value: Any, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _rect(value: Any, default: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return default
    x, y, w, h = (_number(v, d, 0.0, 1.0) for v, d in zip(value, default))
    return x, y, max(0.01, min(w, 1.0 - x)), max(0.01, min(h, 1.0 - y))


def plant_layout_item(item: Any, slot_index: int) -> dict[str, Any]:
    """Normalize resolved scene payloads for the shared layout engine."""
    result = dict(item) if isinstance(item, dict) else {}
    asset = result.get("asset")
    if not isinstance(result.get("placement"), dict) and isinstance(asset, dict):
        placement = asset.get("placement")
        if isinstance(placement, dict):
            result["placement"] = dict(placement)
    result["slot_index"] = int(slot_index)
    return result


def plant_layout(width: float, height: float, plants: int | Iterable[dict[str, Any]],
                 planting_zone: dict[str, Any] | None = None) -> list[PlantPlacement]:
    """Compose up to six plants in a deterministic, collision-free 4:3 garden bed."""
    items = ([{} for _ in range(max(0, plants))] if isinstance(plants, int) else list(plants))[:6]
    if not items:
        return []
    width, height = max(1.0, float(width)), max(1.0, float(height))
    zone = planting_zone if isinstance(planting_zone, dict) else {}
    left = _number(zone.get("left"), 0.08, 0.0, 0.45) * width
    right = _number(zone.get("right"), 0.92, 0.55, 1.0) * width
    far_y = _number(zone.get("far_y"), 0.62, 0.25, 0.88) * height
    near_y = _number(zone.get("near_y"), 0.91, 0.5, 0.99) * height
    clearance = max(4.0, (right - left) * 0.02)
    left, right = left + clearance, right - clearance
    count = len(items)
    if count <= 2:
        xs = [0.5] if count == 1 else [0.39, 0.61]
        depths = [0.76] * count
    elif count <= 4:
        xs = {3: [0.28, 0.5, 0.72], 4: [0.2, 0.4, 0.6, 0.8]}[count]
        depths = {3: [0.72, 0.9, 0.72], 4: [0.72, 0.9, 0.9, 0.72]}[count]
    else:
        xs = {5: [0.25, 0.5, 0.75, 0.37, 0.63], 6: [0.2, 0.5, 0.8, 0.31, 0.5, 0.69]}[count]
        depths = [0.35] * 3 + [0.9] * (count - 3)

    available_w = right - left
    nominal_h = min(height * 0.34, available_w / max(2.4, count * 0.82))
    specs: list[tuple[int, dict[str, Any], float, float, tuple[float, float, float, float], tuple[float, float]]] = []
    for order, (item, x_ratio, depth) in enumerate(zip(items, xs, depths)):
        placement = item.get("placement", {}) if isinstance(item, dict) else {}
        visible_bounds = _rect(placement.get("visible_bounds"), (0.08, 0.04, 0.84, 0.92))
        ground_anchor = placement.get("ground_anchor", [0.5, visible_bounds[1] + visible_bounds[3]])
        if not isinstance(ground_anchor, (list, tuple)) or len(ground_anchor) != 2:
            ground_anchor = [0.5, visible_bounds[1] + visible_bounds[3]]
        asset_scale = _number(placement.get("display_scale", placement.get("scale", 1.0)), 1.0, 0.25, 2.5)
        row_scale = 0.88 if depth < 0.5 else 1.0
        specs.append((order, item, x_ratio, depth, visible_bounds,
                      (_number(ground_anchor[0], 0.5, 0, 1), _number(ground_anchor[1], 0.96, 0, 1))))

    def build(group_scale: float) -> list[PlantPlacement]:
        result: list[PlantPlacement] = []
        for (order, item, x_ratio, depth, vb, anchor), row_depth in zip(specs, depths):
            placement = item.get("placement", {}) if isinstance(item, dict) else {}
            asset_scale = _number(placement.get("display_scale", placement.get("scale", 1.0)), 1.0, 0.25, 2.5)
            row_scale = 0.88 if row_depth < 0.5 else 1.0
            visible_h = nominal_h * asset_scale * row_scale * group_scale
            visible_w = visible_h * (vb[2] / vb[3])
            base_x = left + available_w * x_ratio
            base_y = far_y + (near_y - far_y) * depth
            draw_w, draw_h = visible_w / vb[2], visible_h / vb[3]
            # Anchor the artwork's declared point of ground contact to the scene
            # baseline. This works for both potted plants and dirt mounds and avoids
            # treating transparent image padding as part of the plant's height.
            draw = Rect(base_x - anchor[0] * draw_w, base_y - anchor[1] * draw_h, draw_w, draw_h)
            visible = Rect(draw.x + vb[0] * draw_w, draw.y + vb[1] * draw_h,
                           vb[2] * draw_w, vb[3] * draw_h)
            motion = max(4.0, visible_w * 0.045)
            hit = visible.expanded(motion + max(5.0, visible_w * 0.05), max(5.0, visible_h * 0.025))
            base_type = str(placement.get("base_type", "legacy"))
            default_contact = {
                "pot": (0.52, 0.045),
                "dirt_mound": (0.68, 0.04),
                "legacy": (0.56, 0.055),
            }.get(base_type, (0.56, 0.055))
            contact = placement.get("contact_shadow", default_contact)
            if not isinstance(contact, (list, tuple)) or len(contact) != 2:
                contact = default_contact
            contact_w = visible_w * _number(contact[0], default_contact[0], 0.2, 1.0)
            contact_h = max(3.0, visible_h * _number(contact[1], default_contact[1], 0.015, 0.12))
            footprint = Rect(base_x - contact_w / 2, base_y - contact_h / 2, contact_w, contact_h)
            slot = int(item.get("slot_index", order)) if isinstance(item, dict) else order
            result.append(PlantPlacement(slot, draw, visible, hit, footprint, base_y,
                                         Rect(visible.x, visible.y, visible.width, min(24.0, visible.height)),
                                         asset_scale * row_scale * group_scale))
        return result

    scale = 1.0
    while scale > 0.35:
        result = build(scale)
        extrema = [p.visible.expanded(max(6.0, p.visible.width * 0.08), max(3.0, p.visible.height * 0.04)) for p in result]
        safe = all(r.x >= left and r.right <= right and r.y >= 0 and r.bottom <= height for r in extrema)
        collision_free = all(not a.intersects(b) for i, a in enumerate(extrema) for b in extrema[i + 1:])
        if safe and collision_free:
            return sorted(result, key=lambda p: (p.depth, p.slot_index))
        scale *= 0.94
    return sorted(build(scale), key=lambda p: (p.depth, p.slot_index))


def compact_plant_layout(width: float, height: float, plants: Iterable[dict[str, Any]],
                         planting_zone: dict[str, Any] | None = None) -> list[PlantPlacement]:
    """Lay out a garden snapshot with larger, tightly grouped plant artwork."""
    items = [dict(item) for item in list(plants)[:6]]
    if not items:
        return []
    compact_zone = dict(planting_zone or {})
    compact_zone.update({
        "left": max(0.04, float(compact_zone.get("left", 0.08))),
        "right": min(0.96, float(compact_zone.get("right", 0.92))),
        "far_y": 0.67,
        "near_y": 0.92,
    })
    # Compact cards need stronger artwork than the full 4:3 scene. Preserve the
    # asset-specific proportions while applying a bounded context multiplier.
    multiplier = 1.75 if len(items) <= 2 else 1.45 if len(items) <= 4 else 1.2
    for item in items:
        placement = dict(item.get("placement", {})) if isinstance(item.get("placement"), dict) else {}
        base_scale = _number(placement.get("display_scale", placement.get("scale", 1.0)), 1.0, 0.1, 2.5)
        minimum = 0.65 if len(items) <= 2 else 0.5 if len(items) <= 4 else 0.4
        placement["display_scale"] = min(2.5, max(minimum, base_scale * multiplier))
        item["placement"] = placement
    return plant_layout(width, height, items, compact_zone)


def slot_layout(width: float, height: float, slot_count: int,
                planting_zone: dict[str, Any] | None = None) -> list[PlantPlacement]:
    """Return the stable composition-safe positions for unlocked garden slots."""
    count = max(0, min(6, int(slot_count)))
    return plant_layout(
        width,
        height,
        [{"slot_index": index} for index in range(count)],
        planting_zone,
    )


def smart_card_rect(width: float, height: float, anchor_x: float, anchor_y: float,
                    card_width: float = 252.0, card_height: float = 184.0,
                    obstacles: Iterable[Rect] = (), planting_top: float | None = None) -> tuple[float, float, float, float]:
    margin = 12.0
    safe_width, safe_height = max(1.0, width), max(1.0, height)
    card_width = max(136.0, min(card_width, safe_width - 2 * margin))
    card_height = max(132.0, min(card_height, safe_height - 2 * margin))
    candidates = [
        Rect(anchor_x + 24, anchor_y - card_height, card_width, card_height),
        Rect(anchor_x - card_width - 24, anchor_y - card_height, card_width, card_height),
        Rect(anchor_x - card_width / 2, anchor_y + 18, card_width, card_height),
    ]
    def clamp(r: Rect) -> Rect:
        max_x = max(0.0, safe_width - card_width)
        max_y = max(0.0, safe_height - card_height)
        return Rect(max(0.0, min(r.x, max_x)), max(0.0, min(r.y, max_y)), card_width, card_height)
    obstacles = list(obstacles)
    for candidate in map(clamp, candidates):
        if not any(candidate.intersects(obstacle) for obstacle in obstacles):
            return candidate.x, candidate.y, candidate.width, candidate.height
    dock_y = max(margin, min((planting_top or anchor_y) - card_height - 10, safe_height - card_height - margin))
    dock = clamp(Rect(anchor_x - card_width / 2, dock_y, card_width, card_height))
    return dock.x, dock.y, dock.width, dock.height


def hit_test(layouts: list[PlantPlacement], point_x: float, point_y: float) -> int | None:
    for index in range(len(layouts) - 1, -1, -1):
        if layouts[index].hit.contains(point_x, point_y):
            return index
    return None


class PlantInteractionState:
    def __init__(self) -> None:
        self.hovered_id: str | None = None
        self.pinned_id: str | None = None
        self.focused_index = -1
        self.dragged_id: str | None = None
        self.drag_origin_slot: int | None = None
        self.destination_slot: int | None = None
        self.move_mode = False
    @property
    def active_id(self) -> str | None: return self.pinned_id or self.hovered_id
    def reconcile(self, plant_ids: list[str]) -> None:
        valid = set(plant_ids)
        if self.hovered_id not in valid: self.hovered_id = None
        if self.pinned_id not in valid: self.pinned_id = None
        if self.dragged_id not in valid: self.cancel_placement()
        self.focused_index = -1 if not plant_ids else min(self.focused_index, len(plant_ids) - 1)
    def hover(self, plant_id: str | None) -> None: self.hovered_id = plant_id
    def toggle_pin(self, plant_id: str | None) -> None:
        self.pinned_id = None if plant_id is None or self.pinned_id == plant_id else plant_id
        if plant_id is not None: self.hovered_id = plant_id
    def dismiss(self) -> None: self.pinned_id = self.hovered_id = None
    @property
    def placing(self) -> bool:
        return self.dragged_id is not None or self.move_mode
    def begin_placement(self, plant_id: str, origin_slot: int, valid_slots: list[int], *, keyboard: bool) -> bool:
        if not plant_id or origin_slot not in valid_slots:
            return False
        self.dragged_id = plant_id
        self.drag_origin_slot = origin_slot
        self.destination_slot = origin_slot
        self.move_mode = keyboard
        self.pinned_id = plant_id
        return True
    def cycle_destination(self, valid_slots: list[int], direction: int) -> int | None:
        if not valid_slots or not self.placing:
            return None
        current = self.destination_slot
        index = valid_slots.index(current) if current in valid_slots else 0
        self.destination_slot = valid_slots[(index + direction) % len(valid_slots)]
        return self.destination_slot
    def choose_destination(self, slot_index: int, valid_slots: list[int]) -> bool:
        if not self.placing or slot_index not in valid_slots:
            return False
        self.destination_slot = slot_index
        return True
    def cancel_placement(self) -> None:
        self.dragged_id = None
        self.drag_origin_slot = None
        self.destination_slot = None
        self.move_mode = False
    def complete_placement(self) -> tuple[str, int] | None:
        if self.dragged_id is None or self.destination_slot is None:
            return None
        result = (self.dragged_id, self.destination_slot)
        self.cancel_placement()
        return result
    def cycle_focus(self, plant_ids: list[str], direction: int) -> str | None:
        if not plant_ids: self.focused_index = -1; return None
        self.focused_index = (0 if direction >= 0 else len(plant_ids)-1) if self.focused_index < 0 else (self.focused_index + direction) % len(plant_ids)
        self.hovered_id = plant_ids[self.focused_index]; return self.hovered_id
    def focused_id(self, plant_ids: list[str]) -> str | None:
        return plant_ids[self.focused_index] if 0 <= self.focused_index < len(plant_ids) else None
