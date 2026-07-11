from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

GROWTH_STAGES = ["seed", "sprout", "young", "mature", "flowering", "rare"]
GARDEN_MODES = {"unified", "deck-by-deck"}
WEATHER_TYPES = {"sunny", "cloudy", "breeze", "gentle_rain", "fireflies"}

logger = logging.getLogger(__name__)


@dataclass
class Plant:
    plant_id: str
    species: str
    name: str
    slot_index: int
    growth_points: int = 0
    vitality: float = 1.0
    rare_variant: bool = False
    assigned_deck_id: Optional[int] = None
    personality: str = "balanced"

    @property
    def growth_stage(self) -> str:
        thresholds = [0, 80, 220, 480, 900, 1400]
        for idx, threshold in enumerate(reversed(thresholds)):
            if self.growth_points >= threshold:
                return GROWTH_STAGES[len(thresholds) - 1 - idx]
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
    focus_sessions_completed: int = 0

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
    reward_currency: int = 0
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
class FocusSession:
    active: bool = False
    started_at: Optional[str] = None
    duration_minutes: int = 25
    deep_work_streak: int = 0


@dataclass
class ExamMode:
    enabled: bool = False
    exam_date: Optional[str] = None
    target_deck_ids: List[int] = field(default_factory=list)
    focus_species: str = "bonsai"


@dataclass
class SessionSummary:
    day: str
    summary: str
    quality_score: float
    growth: int


@dataclass
class Snapshot:
    day: str
    streak_days: int
    health_index: float
    total_reviews: int
    plant_stages: Dict[str, str]


@dataclass
class GardenState:
    version: int = 5
    streak_days: int = 0
    total_reviews: int = 0
    total_correct: int = 0
    total_wrong: int = 0
    total_focus_sessions: int = 0
    currency: int = 0
    unlocked_slots: int = 2
    selected_background: str = "default"
    selected_weather: str = "sunny"
    plants: List[Plant] = field(default_factory=list)
    achievements: Dict[str, Achievement] = field(default_factory=dict)
    daily_quests: List[Quest] = field(default_factory=list)
    quest_history: List[str] = field(default_factory=list)
    daily_stats: DailyStats = field(default_factory=DailyStats)
    journal: Dict[str, str] = field(default_factory=dict)
    inventory: Dict[str, List[str]] = field(default_factory=lambda: {
        "plants": ["bonsai", "rose", "ivy", "fern"],
        "pots": ["ceramic_minimal"],
        "backgrounds": ["default"],
        "decorations": ["lantern"],
        "weather": ["sunny"],
        "sounds": [],
        "skins": [],
    })
    equipped: Dict[str, str] = field(default_factory=lambda: {
        "pot": "ceramic_minimal",
        "background": "default",
        "decoration": "lantern",
        "weather": "sunny",
    })
    purchased_items: List[str] = field(default_factory=list)
    streak_freeze_tokens: int = 1
    recovery_mode: bool = False
    last_active_day: str = field(default_factory=lambda: date.today().isoformat())
    focus_plant_id: Optional[str] = None
    deck_plant_map: Dict[str, str] = field(default_factory=dict)
    deck_difficulty_map: Dict[str, float] = field(default_factory=dict)
    gardener_name: str = "Gardener"
    garden_mode: str = "unified"
    retrospective_last_revlog_id: int = 0
    weekly_event_id: str = ""
    weekly_event_applied_for_day: str = ""
    mastery_tree: Dict[str, int] = field(default_factory=lambda: {
        "consistency": 0,
        "accuracy": 0,
        "volume": 0,
        "recovery": 0,
    })
    rare_event_log: List[str] = field(default_factory=list)
    focus_session: FocusSession = field(default_factory=FocusSession)
    exam_mode: ExamMode = field(default_factory=ExamMode)
    snapshots: List[Snapshot] = field(default_factory=list)
    recent_summaries: List[SessionSummary] = field(default_factory=list)
    passive_reward_days: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "streak_days": self.streak_days,
            "total_reviews": self.total_reviews,
            "total_correct": self.total_correct,
            "total_wrong": self.total_wrong,
            "total_focus_sessions": self.total_focus_sessions,
            "currency": self.currency,
            "unlocked_slots": self.unlocked_slots,
            "selected_background": self.selected_background,
            "selected_weather": self.selected_weather,
            "plants": [p.__dict__ for p in self.plants],
            "achievements": {k: v.__dict__ for k, v in self.achievements.items()},
            "daily_quests": [q.__dict__ for q in self.daily_quests],
            "quest_history": self.quest_history,
            "daily_stats": self.daily_stats.__dict__,
            "journal": self.journal,
            "inventory": self.inventory,
            "equipped": self.equipped,
            "purchased_items": self.purchased_items,
            "streak_freeze_tokens": self.streak_freeze_tokens,
            "recovery_mode": self.recovery_mode,
            "last_active_day": self.last_active_day,
            "focus_plant_id": self.focus_plant_id,
            "deck_plant_map": self.deck_plant_map,
            "deck_difficulty_map": self.deck_difficulty_map,
            "gardener_name": self.gardener_name,
            "garden_mode": self.garden_mode,
            "retrospective_last_revlog_id": self.retrospective_last_revlog_id,
            "weekly_event_id": self.weekly_event_id,
            "weekly_event_applied_for_day": self.weekly_event_applied_for_day,
            "mastery_tree": self.mastery_tree,
            "rare_event_log": self.rare_event_log,
            "focus_session": self.focus_session.__dict__,
            "exam_mode": {
                "enabled": self.exam_mode.enabled,
                "exam_date": self.exam_mode.exam_date,
                "target_deck_ids": self.exam_mode.target_deck_ids,
                "focus_species": self.exam_mode.focus_species,
            },
            "snapshots": [s.__dict__ for s in self.snapshots],
            "recent_summaries": [s.__dict__ for s in self.recent_summaries],
            "passive_reward_days": self.passive_reward_days,
        }

    @staticmethod
    def from_dict(data: dict) -> "GardenState":
        if not isinstance(data, dict):
            logger.error("Garden state contract mismatch at root: expected object, got %s", type(data).__name__)
            return GardenState()

        issues: list[str] = []
        payload = _sanitize_garden_state_payload(data, issues)
        if issues:
            logger.error(
                "Garden state contract mismatches (%s): %s",
                len(issues),
                "; ".join(issues),
            )

        state = GardenState()
        for key in [
            "version", "streak_days", "total_reviews", "total_correct", "total_wrong", "total_focus_sessions",
            "currency", "unlocked_slots", "selected_background", "selected_weather", "journal", "inventory",
            "equipped", "purchased_items", "streak_freeze_tokens", "recovery_mode", "last_active_day",
            "focus_plant_id", "deck_plant_map", "deck_difficulty_map", "gardener_name", "garden_mode",
            "retrospective_last_revlog_id", "weekly_event_id",
            "weekly_event_applied_for_day", "mastery_tree", "rare_event_log", "quest_history", "passive_reward_days",
        ]:
            if key in payload:
                setattr(state, key, payload[key])
        state.plants = [Plant(**p) for p in payload.get("plants", [])]
        state.achievements = {k: Achievement(**v) for k, v in payload.get("achievements", {}).items()}
        state.daily_quests = [Quest(**q) for q in payload.get("daily_quests", []) if isinstance(q, dict)]
        if "daily_stats" in payload and isinstance(payload["daily_stats"], dict):
            state.daily_stats = DailyStats(**payload["daily_stats"])
        if isinstance(payload.get("focus_session"), dict):
            state.focus_session = FocusSession(**payload["focus_session"])
        if isinstance(payload.get("exam_mode"), dict):
            state.exam_mode = ExamMode(**payload["exam_mode"])
        state.snapshots = [Snapshot(**s) for s in payload.get("snapshots", []) if isinstance(s, dict)]
        state.recent_summaries = [SessionSummary(**s) for s in payload.get("recent_summaries", []) if isinstance(s, dict)]
        return state


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _expect_type(payload: dict, key: str, expected_type: Any, issues: list[str], *, allow_none: bool = False) -> Any:
    value = payload.get(key)
    if value is None and allow_none:
        return value
    if not isinstance(value, expected_type):
        issues.append(f"{key}: expected {getattr(expected_type, '__name__', expected_type)}, got {type(value).__name__}")
        return None
    return value


def _sanitize_garden_state_payload(data: dict, issues: list[str]) -> dict:
    defaults = GardenState().to_dict()
    sanitized: dict[str, Any] = dict(defaults)

    scalar_types = {
        "version": int,
        "streak_days": int,
        "total_reviews": int,
        "total_correct": int,
        "total_wrong": int,
        "total_focus_sessions": int,
        "currency": int,
        "unlocked_slots": int,
        "selected_background": str,
        "selected_weather": str,
        "streak_freeze_tokens": int,
        "recovery_mode": bool,
        "last_active_day": str,
        "focus_plant_id": str,
        "gardener_name": str,
        "garden_mode": str,
        "retrospective_last_revlog_id": int,
        "weekly_event_id": str,
        "weekly_event_applied_for_day": str,
    }

    for key, expected in scalar_types.items():
        if key not in data:
            continue
        if data[key] is None and key == "focus_plant_id":
            sanitized[key] = None
            continue
        if isinstance(data[key], expected):
            sanitized[key] = data[key]
        else:
            issues.append(f"{key}: expected {expected.__name__}, got {type(data[key]).__name__}")

    if sanitized["garden_mode"] not in GARDEN_MODES:
        issues.append(f"garden_mode: unexpected value '{sanitized['garden_mode']}'")
        sanitized["garden_mode"] = defaults["garden_mode"]

    if sanitized["selected_weather"] not in WEATHER_TYPES:
        issues.append(f"selected_weather: unexpected value '{sanitized['selected_weather']}'")
        sanitized["selected_weather"] = defaults["selected_weather"]

    for date_field in ("last_active_day", "weekly_event_applied_for_day"):
        value = sanitized.get(date_field)
        if value and not _is_iso_date(value):
            issues.append(f"{date_field}: expected ISO date string YYYY-MM-DD, got {value!r}")
            sanitized[date_field] = defaults[date_field]

    # object/list sections used by UI
    for dict_key in ("journal", "inventory", "equipped", "deck_plant_map", "deck_difficulty_map", "mastery_tree", "achievements"):
        if dict_key in data and isinstance(data[dict_key], dict):
            sanitized[dict_key] = data[dict_key]
        elif dict_key in data:
            issues.append(f"{dict_key}: expected object, got {type(data[dict_key]).__name__}")

    for list_key in ("purchased_items", "quest_history", "rare_event_log", "passive_reward_days", "plants", "daily_quests", "snapshots", "recent_summaries"):
        if list_key in data and isinstance(data[list_key], list):
            sanitized[list_key] = data[list_key]
        elif list_key in data:
            issues.append(f"{list_key}: expected list, got {type(data[list_key]).__name__}")

    if "daily_stats" in data:
        if not isinstance(data["daily_stats"], dict):
            issues.append(f"daily_stats: expected object, got {type(data['daily_stats']).__name__}")
        else:
            ds = dict(defaults["daily_stats"])
            raw_ds = data["daily_stats"]
            for key, expected in {
                "day": str,
                "reviewed": int,
                "correct": int,
                "wrong": int,
                "new_count": int,
                "learning_count": int,
                "review_count": int,
                "difficult_count": int,
                "recovered_lapses": int,
                "growth_earned": int,
                "completed_due_cards": bool,
                "focus_sessions_completed": int,
            }.items():
                if key not in raw_ds:
                    issues.append(f"daily_stats.{key}: required field missing")
                    continue
                if isinstance(raw_ds[key], expected):
                    ds[key] = raw_ds[key]
                else:
                    issues.append(f"daily_stats.{key}: expected {expected.__name__}, got {type(raw_ds[key]).__name__}")
            if ds["day"] and not _is_iso_date(ds["day"]):
                issues.append(f"daily_stats.day: expected ISO date string YYYY-MM-DD, got {ds['day']!r}")
                ds["day"] = defaults["daily_stats"]["day"]
            sanitized["daily_stats"] = ds

    if "focus_session" in data:
        if not isinstance(data["focus_session"], dict):
            issues.append(f"focus_session: expected object, got {type(data['focus_session']).__name__}")
        else:
            raw = data["focus_session"]
            clean = dict(defaults["focus_session"])
            active = _expect_type(raw, "active", bool, issues)
            duration = _expect_type(raw, "duration_minutes", int, issues)
            streak = _expect_type(raw, "deep_work_streak", int, issues)
            started_at = raw.get("started_at")
            if started_at is not None and not isinstance(started_at, str):
                issues.append(f"focus_session.started_at: expected str|null, got {type(started_at).__name__}")
                started_at = None
            if active is not None:
                clean["active"] = active
            if duration is not None:
                clean["duration_minutes"] = duration
            if streak is not None:
                clean["deep_work_streak"] = streak
            clean["started_at"] = started_at
            sanitized["focus_session"] = clean

    if "exam_mode" in data:
        if not isinstance(data["exam_mode"], dict):
            issues.append(f"exam_mode: expected object, got {type(data['exam_mode']).__name__}")
        else:
            raw = data["exam_mode"]
            clean = dict(defaults["exam_mode"])
            enabled = _expect_type(raw, "enabled", bool, issues)
            if enabled is not None:
                clean["enabled"] = enabled
            exam_date = raw.get("exam_date")
            if exam_date is not None:
                if not isinstance(exam_date, str):
                    issues.append(f"exam_mode.exam_date: expected str|null, got {type(exam_date).__name__}")
                    exam_date = None
                elif not _is_iso_date(exam_date):
                    issues.append(f"exam_mode.exam_date: malformed date {exam_date!r}")
                    exam_date = None
            clean["exam_date"] = exam_date

            target_ids = raw.get("target_deck_ids", [])
            if not isinstance(target_ids, list) or not all(isinstance(i, int) for i in target_ids):
                issues.append("exam_mode.target_deck_ids: expected list[int]")
                target_ids = []
            clean["target_deck_ids"] = target_ids

            focus_species = raw.get("focus_species", clean["focus_species"])
            if isinstance(focus_species, str):
                clean["focus_species"] = focus_species
            else:
                issues.append(f"exam_mode.focus_species: expected str, got {type(focus_species).__name__}")
            sanitized["exam_mode"] = clean

    cleaned_plants = []
    for idx, plant in enumerate(sanitized.get("plants", [])):
        if not isinstance(plant, dict):
            issues.append(f"plants[{idx}]: expected object, got {type(plant).__name__}")
            continue
        required = {
            "plant_id": str,
            "species": str,
            "name": str,
            "slot_index": int,
        }
        optional = {
            "growth_points": int,
            "vitality": (int, float),
            "rare_variant": bool,
            "assigned_deck_id": (int, type(None)),
            "personality": str,
        }
        valid = True
        for key, kind in required.items():
            if key not in plant:
                issues.append(f"plants[{idx}].{key}: required field missing")
                valid = False
            elif not isinstance(plant[key], kind):
                issues.append(f"plants[{idx}].{key}: expected {kind.__name__}, got {type(plant[key]).__name__}")
                valid = False
        if not valid:
            continue
        normalized = {
            "plant_id": plant["plant_id"],
            "species": plant["species"],
            "name": plant["name"],
            "slot_index": plant["slot_index"],
            "growth_points": 0,
            "vitality": 1.0,
            "rare_variant": False,
            "assigned_deck_id": None,
            "personality": "balanced",
        }
        for key, kind in optional.items():
            if key in plant:
                if isinstance(plant[key], kind):
                    normalized[key] = plant[key]
                else:
                    issues.append(f"plants[{idx}].{key}: expected {kind}, got {type(plant[key]).__name__}")
        normalized["growth_points"] = max(0, int(normalized["growth_points"]))
        normalized["slot_index"] = max(0, int(normalized["slot_index"]))
        normalized["vitality"] = max(0.0, min(1.0, float(normalized["vitality"])))
        cleaned_plants.append(normalized)
    sanitized["plants"] = cleaned_plants

    for key in (
        "streak_days", "total_reviews", "total_correct", "total_wrong",
        "total_focus_sessions", "currency", "unlocked_slots",
        "streak_freeze_tokens", "retrospective_last_revlog_id",
    ):
        sanitized[key] = max(0, int(sanitized[key]))

    stats = sanitized["daily_stats"]
    for key in (
        "reviewed", "correct", "wrong", "new_count", "learning_count",
        "review_count", "difficult_count", "recovered_lapses",
        "growth_earned", "focus_sessions_completed",
    ):
        stats[key] = max(0, int(stats[key]))
    stats["correct"] = min(stats["correct"], stats["reviewed"])
    stats["wrong"] = min(stats["wrong"], max(0, stats["reviewed"] - stats["correct"]))

    return sanitized


def iso_now() -> str:
    return datetime.now().isoformat()
