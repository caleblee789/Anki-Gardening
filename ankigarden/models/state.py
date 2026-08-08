from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


GROWTH_STAGES = ["seed", "sprout", "young", "mature", "flowering", "rare"]
GROWTH_THRESHOLDS = [0, 80, 220, 480, 900, 1400]
WEATHER_TYPES = {"sunny", "cloudy", "breeze", "gentle_rain", "fireflies"}
PLANT_SPECIES = {"bonsai", "rose", "cactus", "orchid", "moonflower", "sunbloom", "fern", "ivy"}
MAX_GARDEN_SLOTS = 6
PLANT_MEMORY_KINDS = {"planted", "first_focus", "stage", "streak", "reviews"}
MAX_PLANT_NAME_LENGTH = 40

logger = logging.getLogger(__name__)


@dataclass
class PlantMemory:
    memory_id: str
    kind: str
    occurred_on: str
    value: int = 0
    previous_stage: Optional[str] = None
    new_stage: Optional[str] = None


@dataclass
class Plant:
    plant_id: str
    species: str
    name: str
    slot_index: int
    growth_points: int = 0
    vitality: float = 1.0
    rare_variant: bool = False
    personality: str = "balanced"
    planted_on: str = field(default_factory=lambda: date.today().isoformat())
    memories: List[PlantMemory] = field(default_factory=list)

    @property
    def growth_stage(self) -> str:
        for idx, threshold in enumerate(reversed(GROWTH_THRESHOLDS)):
            if self.growth_points >= threshold:
                return GROWTH_STAGES[len(GROWTH_THRESHOLDS) - 1 - idx]
        return "seed"


@dataclass
class DailyStats:
    day: str = field(default_factory=lambda: date.today().isoformat())
    reviewed: int = 0
    correct: int = 0
    wrong: int = 0
    new_count: int = 0
    learning_count: int = 0
    review_count: int = 0
    difficult_count: int = 0
    recovered_lapses: int = 0
    growth_earned: int = 0
    completed_due_cards: bool = False

    @property
    def accuracy(self) -> float:
        total = self.correct + self.wrong
        return 0 if total == 0 else self.correct / total


@dataclass
class Quest:
    quest_id: str
    description: str
    target: int
    metric: str
    progress: int = 0
    reward_growth: int = 0
    completed: bool = False


@dataclass
class Achievement:
    achievement_id: str
    name: str
    description: str
    unlocked: bool = False
    progress: float = 0.0
    unlocked_at: Optional[str] = None


@dataclass
class MilestoneReward:
    review_count: int
    offered_species: List[str] = field(default_factory=list)


@dataclass
class GardenState:
    version: int = 10
    streak_days: int = 0
    total_reviews: int = 0
    total_correct: int = 0
    total_wrong: int = 0
    unlocked_slots: int = 2
    selected_background: str = "default"
    selected_weather: str = "sunny"
    plants: List[Plant] = field(default_factory=list)
    achievements: Dict[str, Achievement] = field(default_factory=dict)
    daily_quests: List[Quest] = field(default_factory=list)
    quest_history: List[str] = field(default_factory=list)
    daily_stats: DailyStats = field(default_factory=DailyStats)
    inventory: Dict[str, List[str]] = field(default_factory=lambda: {
        "plants": ["bonsai", "rose", "ivy", "fern"],
        "pots": ["ceramic_minimal"],
        "backgrounds": ["default"],
        "decorations": ["lantern"],
        "weather": ["sunny"],
    })
    equipped: Dict[str, str] = field(default_factory=lambda: {
        "pot": "ceramic_minimal",
        "background": "default",
        "decoration": "none",
        "weather": "sunny",
    })
    last_active_day: str = field(default_factory=lambda: date.today().isoformat())
    focus_plant_id: Optional[str] = None
    pending_milestone_reward: Optional[MilestoneReward] = None
    retrospective_last_revlog_id: int = 0
    imported_history_days: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({
            "version": self.version,
            "streak_days": self.streak_days,
            "total_reviews": self.total_reviews,
            "total_correct": self.total_correct,
            "total_wrong": self.total_wrong,
            "unlocked_slots": self.unlocked_slots,
            "selected_background": self.selected_background,
            "selected_weather": self.selected_weather,
            "plants": [
                {
                    **{key: value for key, value in p.__dict__.items() if key != "memories"},
                    "memories": [memory.__dict__ for memory in p.memories],
                }
                for p in self.plants
            ],
            "achievements": {key: value.__dict__ for key, value in self.achievements.items()},
            "daily_quests": [q.__dict__ for q in self.daily_quests],
            "quest_history": list(self.quest_history),
            "daily_stats": self.daily_stats.__dict__,
            "inventory": self.inventory,
            "equipped": self.equipped,
            "last_active_day": self.last_active_day,
            "focus_plant_id": self.focus_plant_id,
            "pending_milestone_reward": (
                self.pending_milestone_reward.__dict__ if self.pending_milestone_reward else None
            ),
            "retrospective_last_revlog_id": self.retrospective_last_revlog_id,
            "imported_history_days": list(self.imported_history_days),
        })

    @staticmethod
    def from_dict(data: Any) -> "GardenState":
        if not isinstance(data, dict):
            logger.error("Garden state contract mismatch at root: expected object, got %s", type(data).__name__)
            return GardenState()
        issues: list[str] = []
        state = GardenState()
        state.streak_days = _nonnegative_int(data.get("streak_days"), 0, "streak_days", issues)
        state.total_reviews = _nonnegative_int(data.get("total_reviews"), 0, "total_reviews", issues)
        state.total_correct = min(
            state.total_reviews,
            _nonnegative_int(data.get("total_correct"), 0, "total_correct", issues),
        )
        state.total_wrong = min(
            max(0, state.total_reviews - state.total_correct),
            _nonnegative_int(data.get("total_wrong"), 0, "total_wrong", issues),
        )
        state.selected_background = _string(data.get("selected_background"), "default", "selected_background", issues)
        weather = _string(data.get("selected_weather"), "sunny", "selected_weather", issues)
        if weather not in WEATHER_TYPES:
            issues.append(f"selected_weather: unexpected value {weather!r}")
            weather = "sunny"
        state.selected_weather = weather
        state.daily_stats = _daily_stats(data.get("daily_stats"), issues)
        state.plants = _plants(data.get("plants"), issues)
        requested_slots = _nonnegative_int(data.get("unlocked_slots"), 2, "unlocked_slots", issues)
        occupied_slots = max((plant.slot_index + 1 for plant in state.plants), default=0)
        coherent_slots = min(MAX_GARDEN_SLOTS, max(2, occupied_slots, len(state.plants)))
        state.unlocked_slots = coherent_slots
        if requested_slots != coherent_slots:
            issues.append(f"unlocked_slots: repaired {requested_slots} to {coherent_slots}")
        state.achievements = _achievements(data.get("achievements"), issues)
        state.daily_quests = _quests(data.get("daily_quests"), issues)
        state.quest_history = _string_list(data.get("quest_history"), "quest_history", issues)
        state.inventory = _inventory(data.get("inventory"), state.inventory, issues)
        state.equipped = _equipped(data.get("equipped"), state.equipped, issues)
        state.last_active_day = _iso_date(data.get("last_active_day"), date.today().isoformat(), "last_active_day", issues)
        state.retrospective_last_revlog_id = _nonnegative_int(
            data.get("retrospective_last_revlog_id"), 0, "retrospective_last_revlog_id", issues
        )
        state.imported_history_days = sorted({
            value for value in _string_list(data.get("imported_history_days"), "imported_history_days", issues)
            if _valid_iso_date(value)
        })
        plant_ids = {plant.plant_id for plant in state.plants}
        focus = data.get("focus_plant_id")
        state.focus_plant_id = focus if isinstance(focus, str) and focus in plant_ids else None
        if state.focus_plant_id is None and state.plants:
            state.focus_plant_id = min(state.plants, key=lambda plant: (plant.slot_index, plant.plant_id)).plant_id
            if focus not in (None, state.focus_plant_id):
                issues.append("focus_plant_id: repaired to the first valid plant")
        state.pending_milestone_reward = _milestone(data.get("pending_milestone_reward"), issues)
        if issues:
            logger.error("Garden state contract mismatches (%s): %s", len(issues), "; ".join(issues))
        return state


def _nonnegative_int(value: Any, default: int, label: str, issues: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if value is not None:
            issues.append(f"{label}: expected int, got {type(value).__name__}")
        return default
    return max(0, value)


def _number(value: Any, default: float, low: float, high: float, label: str, issues: list[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if value is not None:
            issues.append(f"{label}: expected number, got {type(value).__name__}")
        return default
    return max(low, min(high, float(value)))


def _string(value: Any, default: str, label: str, issues: list[str]) -> str:
    if not isinstance(value, str) or not value:
        if value is not None:
            issues.append(f"{label}: expected non-empty string")
        return default
    return value


def _iso_date(value: Any, default: str, label: str, issues: list[str]) -> str:
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
            return value
        except ValueError:
            pass
    if value is not None:
        issues.append(f"{label}: expected ISO date string YYYY-MM-DD")
    return default


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _daily_stats(value: Any, issues: list[str]) -> DailyStats:
    result = DailyStats()
    if not isinstance(value, dict):
        if value is not None:
            issues.append("daily_stats: expected object")
        return result
    result.day = _iso_date(value.get("day"), result.day, "daily_stats.day", issues)
    for key in (
        "reviewed", "correct", "wrong", "new_count", "learning_count", "review_count",
        "difficult_count", "recovered_lapses", "growth_earned",
    ):
        setattr(result, key, _nonnegative_int(value.get(key), 0, f"daily_stats.{key}", issues))
    result.correct = min(result.correct, result.reviewed)
    result.wrong = min(result.wrong, max(0, result.reviewed - result.correct))
    completed = value.get("completed_due_cards", False)
    result.completed_due_cards = completed if isinstance(completed, bool) else False
    return result


def _plants(value: Any, issues: list[str]) -> list[Plant]:
    if not isinstance(value, list):
        if value is not None:
            issues.append("plants: expected list")
        return []
    result: list[Plant] = []
    used_ids: set[str] = set()
    used_slots: set[int] = set()
    for index, raw in enumerate(value[:MAX_GARDEN_SLOTS]):
        if not isinstance(raw, dict):
            issues.append(f"plants[{index}]: expected object")
            continue
        species = raw.get("species")
        name = raw.get("name")
        if not isinstance(species, str) or not species or not isinstance(name, str) or not name:
            issues.append(f"plants[{index}]: missing valid species or name")
            continue
        if species not in PLANT_SPECIES:
            issues.append(f"plants[{index}].species: unsupported value {species!r}")
            continue
        clean_name = " ".join(name.split())[:MAX_PLANT_NAME_LENGTH]
        if clean_name != name:
            issues.append(f"plants[{index}].name: normalized to a safe display name")
        if not clean_name:
            clean_name = species.title()
        raw_id = raw.get("plant_id")
        plant_id = raw_id if isinstance(raw_id, str) and raw_id and raw_id not in used_ids else ""
        if not plant_id:
            seed = index + 1
            plant_id = f"plant_{seed}"
            while plant_id in used_ids:
                seed += 1
                plant_id = f"plant_{seed}"
            issues.append(f"plants[{index}].plant_id: repaired duplicate or invalid value")
        raw_slot = raw.get("slot_index")
        slot = raw_slot if isinstance(raw_slot, int) and not isinstance(raw_slot, bool) else -1
        if slot < 0 or slot >= MAX_GARDEN_SLOTS or slot in used_slots:
            slot = next((candidate for candidate in range(MAX_GARDEN_SLOTS) if candidate not in used_slots), -1)
            issues.append(f"plants[{index}].slot_index: repaired duplicate or invalid value")
        if slot < 0:
            break
        used_ids.add(plant_id)
        used_slots.add(slot)
        result.append(Plant(
            plant_id=plant_id,
            species=species,
            name=clean_name,
            slot_index=slot,
            growth_points=_nonnegative_int(raw.get("growth_points"), 0, f"plants[{index}].growth_points", issues),
            vitality=_number(raw.get("vitality"), 1.0, 0.0, 1.0, f"plants[{index}].vitality", issues),
            rare_variant=raw.get("rare_variant", False) if isinstance(raw.get("rare_variant", False), bool) else False,
            personality=raw.get("personality", "balanced") if isinstance(raw.get("personality", "balanced"), str) else "balanced",
            planted_on=_iso_date(
                raw.get("planted_on"), date.today().isoformat(), f"plants[{index}].planted_on", issues
            ),
            memories=_plant_memories(raw.get("memories"), index, issues),
        ))
    return sorted(result, key=lambda plant: (plant.slot_index, plant.plant_id))


def _plant_memories(value: Any, plant_index: int, issues: list[str]) -> list[PlantMemory]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"plants[{plant_index}].memories: expected list")
        return []
    result: list[PlantMemory] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(value[:32]):
        label = f"plants[{plant_index}].memories[{index}]"
        if not isinstance(raw, dict):
            issues.append(f"{label}: expected object")
            continue
        memory_id, kind = raw.get("memory_id"), raw.get("kind")
        if not isinstance(memory_id, str) or not memory_id or memory_id in used_ids:
            issues.append(f"{label}.memory_id: invalid or duplicate")
            continue
        if kind not in PLANT_MEMORY_KINDS:
            issues.append(f"{label}.kind: unsupported value {kind!r}")
            continue
        occurred_on = _iso_date(raw.get("occurred_on"), "", f"{label}.occurred_on", issues)
        if not occurred_on:
            continue
        previous_stage = raw.get("previous_stage") if raw.get("previous_stage") in GROWTH_STAGES else None
        new_stage = raw.get("new_stage") if raw.get("new_stage") in GROWTH_STAGES else None
        if kind == "stage" and new_stage is None:
            issues.append(f"{label}.new_stage: required for stage memory")
            continue
        used_ids.add(memory_id)
        result.append(PlantMemory(
            memory_id=memory_id,
            kind=kind,
            occurred_on=occurred_on,
            value=_nonnegative_int(raw.get("value"), 0, f"{label}.value", issues),
            previous_stage=previous_stage,
            new_stage=new_stage,
        ))
    return sorted(result, key=lambda memory: (memory.occurred_on, memory.memory_id))


def _quests(value: Any, issues: list[str]) -> list[Quest]:
    if not isinstance(value, list):
        return []
    result = []
    for index, raw in enumerate(value[:3]):
        if not isinstance(raw, dict):
            issues.append(f"daily_quests[{index}]: expected object")
            continue
        required = (raw.get("quest_id"), raw.get("description"), raw.get("metric"))
        if not all(isinstance(item, str) and item for item in required):
            issues.append(f"daily_quests[{index}]: missing required strings")
            continue
        if required[2] not in {"reviewed", "accuracy", "lr_total", "difficult", "recoveries", "growth"}:
            issues.append(f"daily_quests[{index}].metric: unsupported value {required[2]!r}")
            continue
        result.append(Quest(
            quest_id=required[0],
            description=required[1],
            target=max(1, _nonnegative_int(raw.get("target"), 1, f"daily_quests[{index}].target", issues)),
            metric=required[2],
            progress=_nonnegative_int(raw.get("progress"), 0, f"daily_quests[{index}].progress", issues),
            reward_growth=_nonnegative_int(raw.get("reward_growth"), 0, f"daily_quests[{index}].reward_growth", issues),
            completed=raw.get("completed", False) if isinstance(raw.get("completed", False), bool) else False,
        ))
    return result


def _achievements(value: Any, issues: list[str]) -> dict[str, Achievement]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            continue
        name, description = raw.get("name"), raw.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            issues.append(f"achievements.{key}: invalid record")
            continue
        result[key] = Achievement(
            achievement_id=key,
            name=name,
            description=description,
            unlocked=raw.get("unlocked", False) if isinstance(raw.get("unlocked", False), bool) else False,
            progress=_number(raw.get("progress"), 0.0, 0.0, 1.0, f"achievements.{key}.progress", issues),
            unlocked_at=raw.get("unlocked_at") if isinstance(raw.get("unlocked_at"), str) else None,
        )
    return result


def _milestone(value: Any, issues: list[str]) -> Optional[MilestoneReward]:
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append("pending_milestone_reward: expected object or null")
        return None
    review_count = value.get("review_count")
    offered = value.get("offered_species")
    if isinstance(review_count, bool) or not isinstance(review_count, int) or review_count < 0:
        issues.append("pending_milestone_reward.review_count: expected non-negative int")
        return None
    if not isinstance(offered, list) or not all(isinstance(item, str) and item for item in offered):
        issues.append("pending_milestone_reward.offered_species: expected list[str]")
        return None
    return MilestoneReward(review_count=review_count, offered_species=list(dict.fromkeys(offered))[:3])


def _string_list(value: Any, label: str, issues: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    return [item for item in value if isinstance(item, str)]


def _inventory(value: Any, default: dict[str, list[str]], issues: list[str]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return default
    result = {key: list(items) for key, items in default.items()}
    for key in result:
        if key in value:
            if isinstance(value[key], list):
                result[key] = list(dict.fromkeys(item for item in value[key] if isinstance(item, str) and item))
            else:
                issues.append(f"inventory.{key}: expected list")
    return result


def _equipped(value: Any, default: dict[str, str], issues: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return default
    result = dict(default)
    for key in result:
        if key in value and isinstance(value[key], str) and value[key]:
            result[key] = value[key]
        elif key in value:
            issues.append(f"equipped.{key}: expected non-empty string")
    return result


def iso_now() -> str:
    return datetime.now().isoformat()
