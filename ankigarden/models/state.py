from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


STATE_VERSION = 14
GROWTH_STAGES = ["seed", "sprout", "young", "mature", "flowering", "rare"]
GROWTH_THRESHOLDS = [0, 500, 2_500, 8_000, 20_000, 50_000]
WEATHER_TYPES = {"sunny", "cloudy", "breeze", "gentle_rain", "fireflies"}
CURRENT_CATALOG_SPECIES_ORDER = (
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
)
HISTORICAL_PLANT_SPECIES_ORDER = (
    "fern",
    "ivy",
    "cactus",
    "orchid",
    "sunbloom",
    "moonflower",
    "marigold",
    "strawberry",
    "pumpkin",
)
PLANT_SPECIES_ORDER = tuple(dict.fromkeys((
    *CURRENT_CATALOG_SPECIES_ORDER,
    *HISTORICAL_PLANT_SPECIES_ORDER,
)))
PLANT_SPECIES = frozenset(PLANT_SPECIES_ORDER)
MAX_GARDEN_SLOTS = 6
MAX_COLLECTION_PLANTS = len(PLANT_SPECIES)
PLANT_MEMORY_KINDS = {"planted", "first_nurture", "stage", "streak", "reviews"}
MAX_PLANT_NAME_LENGTH = 40
MAX_TRANSACTION_HISTORY = 500
MAX_FEEDBACK_EVENTS = 100
MAX_ACTIVE_PERIODS = 64
MAX_FERTILIZER_HISTORY = 64
MAX_PROCESSED_REVLOG_IDS = 100_000
STREAK_REWARD_MILESTONES = {7, 14, 30, 100}
STREAK_BONUS_TIERS = ((1, 0), (7, 5), (14, 10), (30, 15), (100, 20), (365, 25))

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@dataclass
class PlantMemory:
    memory_id: str
    kind: str
    occurred_on: str
    value: int = 0
    previous_stage: Optional[str] = None
    new_stage: Optional[str] = None


@dataclass
class Fertilizer:
    tier: str
    growth_per_answer: int
    expires_at: float
    started_at: Optional[float] = None

    def active(self, now: float) -> bool:
        current = float(now)
        return (
            self.started_at is not None
            and float(self.started_at) <= current < self.expires_at
        )


@dataclass
class Plant:
    plant_id: str
    species: str
    name: str
    slot_index: Optional[int]
    growth_points: int = 0
    bonus_remainder: int = 0
    personality: str = "balanced"
    planted_on: str = field(default_factory=lambda: date.today().isoformat())
    memories: List[PlantMemory] = field(default_factory=list)
    fertilizer: Optional[Fertilizer] = None
    # Completed/replaced activation windows remain available for late synced
    # reviews. The current window stays in ``fertilizer`` for UI compatibility.
    fertilizer_history: List[Fertilizer] = field(default_factory=list)

    @property
    def growth_stage(self) -> str:
        stage = GROWTH_STAGES[0]
        for index, threshold in enumerate(GROWTH_THRESHOLDS):
            if self.growth_points >= threshold:
                stage = GROWTH_STAGES[index]
        return stage

    @property
    def fully_grown(self) -> bool:
        return self.growth_points >= GROWTH_THRESHOLDS[-1]

    @property
    def planted(self) -> bool:
        return self.slot_index is not None


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
    base_growth: int = 0
    streak_bonus_growth: int = 0
    fertilizer_growth: int = 0
    bonus_growth: int = 0
    growth_earned: int = 0
    plant_growth: Dict[str, int] = field(default_factory=dict)
    completed_due_cards: bool = False

    @property
    def accuracy(self) -> float:
        total = self.correct + self.wrong
        return 0 if total == 0 else self.correct / total


@dataclass
class CurrencyTransaction:
    transaction_id: str
    event_key: str
    reason: str
    delta: int
    balance: int
    occurred_at: str


@dataclass
class FeedbackEvent:
    event_id: str
    kind: str
    message: str
    occurred_at: str
    plant_id: Optional[str] = None


@dataclass
class ActivePlantPeriod:
    day: str
    plant_id: Optional[str]
    started_at_ms: int


@dataclass
class Achievement:
    achievement_id: str
    name: str
    description: str
    unlocked: bool = False
    progress: float = 0.0
    unlocked_at: Optional[str] = None


@dataclass
class GardenState:
    version: int = STATE_VERSION
    streak_days: int = 0
    total_reviews: int = 0
    total_correct: int = 0
    total_wrong: int = 0
    unlocked_slots: int = 2
    unlocked_species: List[str] = field(default_factory=list)
    starter_selection_complete: bool = False
    selected_background: str = "default"
    selected_weather: str = "sunny"
    plants: List[Plant] = field(default_factory=list)
    achievements: Dict[str, Achievement] = field(default_factory=dict)
    daily_stats: DailyStats = field(default_factory=DailyStats)
    currency_balance: int = 0
    currency_transactions: List[CurrencyTransaction] = field(default_factory=list)
    claimed_streak_rewards: List[int] = field(default_factory=list)
    pending_feedback: List[FeedbackEvent] = field(default_factory=list)
    inventory: Dict[str, List[str]] = field(default_factory=lambda: {
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
    active_plant_id: Optional[str] = None
    active_plant_periods: List[ActivePlantPeriod] = field(default_factory=list)
    last_processed_revlog_id: int = 0
    processed_revlog_floor: int = 0
    processed_revlog_ids: List[int] = field(default_factory=list)
    revlog_ledger_migration_pending: bool = False
    scene_geometry_version: int = 6
    # Runtime-only repair marker. A non-null saved reference that cannot route
    # Growth is recoverable, while an explicit null means the user intentionally
    # has no plant selected after Rare. This distinction is never serialized.
    _active_plant_reference_invalid: bool = field(
        default=False, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # A state constructed around an existing collection represents an
        # established garden, even when the caller predates the starter flag.
        if self.plants:
            self.starter_selection_complete = True
            self.unlocked_species = list(dict.fromkeys([
                *self.unlocked_species,
                *(plant.species for plant in self.plants if plant.species in PLANT_SPECIES),
            ]))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({
            "version": STATE_VERSION,
            "streak_days": self.streak_days,
            "total_reviews": self.total_reviews,
            "total_correct": self.total_correct,
            "total_wrong": self.total_wrong,
            "unlocked_slots": self.unlocked_slots,
            "unlocked_species": list(self.unlocked_species),
            "starter_selection_complete": self.starter_selection_complete,
            "selected_background": self.selected_background,
            "selected_weather": self.selected_weather,
            "plants": [
                _plant_to_dict(plant)
                for plant in sorted(
                    self.plants,
                    key=lambda item: (
                        item.slot_index is None,
                        item.slot_index if item.slot_index is not None else MAX_GARDEN_SLOTS,
                        item.plant_id,
                    ),
                )
            ],
            "achievements": {key: value.__dict__ for key, value in self.achievements.items()},
            "daily_stats": {
                **{key: value for key, value in self.daily_stats.__dict__.items() if key != "plant_growth"},
                "plant_growth": dict(self.daily_stats.plant_growth),
            },
            "currency_balance": self.currency_balance,
            "currency_transactions": [tx.__dict__ for tx in self.currency_transactions[-MAX_TRANSACTION_HISTORY:]],
            "claimed_streak_rewards": sorted(set(self.claimed_streak_rewards)),
            "pending_feedback": [event.__dict__ for event in self.pending_feedback[-MAX_FEEDBACK_EVENTS:]],
            "inventory": self.inventory,
            "equipped": self.equipped,
            "last_active_day": self.last_active_day,
            "active_plant_id": self.active_plant_id,
            "active_plant_periods": [period.__dict__ for period in self.active_plant_periods[-MAX_ACTIVE_PERIODS:]],
            "last_processed_revlog_id": self.last_processed_revlog_id,
            "processed_revlog_floor": self.processed_revlog_floor,
            "processed_revlog_ids": sorted({
                value for value in self.processed_revlog_ids
                if isinstance(value, int)
                and not isinstance(value, bool)
                and value > self.processed_revlog_floor
            })[-MAX_PROCESSED_REVLOG_IDS:],
            "revlog_ledger_migration_pending": self.revlog_ledger_migration_pending,
            "scene_geometry_version": self.scene_geometry_version,
        })

    @staticmethod
    def from_dict(data: Any) -> "GardenState":
        if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
            logger.error("Garden state contract mismatch: expected schema %s", STATE_VERSION)
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
        state.selected_weather = weather if weather in WEATHER_TYPES else "sunny"
        if weather not in WEATHER_TYPES:
            issues.append(f"selected_weather: unexpected value {weather!r}")
        state.daily_stats = _daily_stats(data.get("daily_stats"), issues)
        state.plants = _plants(data.get("plants"), issues)
        state.unlocked_slots = _bounded_int(
            data.get("unlocked_slots"), 2, 2, MAX_GARDEN_SLOTS, "unlocked_slots", issues
        )
        occupied = [plant.slot_index for plant in state.plants if plant.slot_index is not None]
        required_slots = max(occupied, default=1) + 1
        if required_slots > state.unlocked_slots:
            issues.append(f"unlocked_slots: repaired {state.unlocked_slots} to {required_slots}")
            state.unlocked_slots = min(MAX_GARDEN_SLOTS, required_slots)
        unlocked = _string_list(data.get("unlocked_species"), "unlocked_species", issues)
        unlocked = [value for value in unlocked if value in PLANT_SPECIES]
        unlocked.extend(plant.species for plant in state.plants)
        state.unlocked_species = list(dict.fromkeys(unlocked))
        starter_selection_complete = data.get("starter_selection_complete", False)
        if not isinstance(starter_selection_complete, bool):
            issues.append("starter_selection_complete: expected bool")
            starter_selection_complete = False
        if state.plants and not starter_selection_complete:
            issues.append("starter_selection_complete: repaired to true for an existing collection")
            starter_selection_complete = True
        state.starter_selection_complete = starter_selection_complete
        state.achievements = _achievements(data.get("achievements"), issues)
        state.currency_balance = _nonnegative_int(data.get("currency_balance"), 0, "currency_balance", issues)
        state.currency_transactions = _transactions(data.get("currency_transactions"), state.currency_balance, issues)
        claimed_streaks = data.get("claimed_streak_rewards", [])
        if isinstance(claimed_streaks, list):
            claimed_values = {
                value
                for value in claimed_streaks
                if isinstance(value, int) and not isinstance(value, bool) and value in STREAK_REWARD_MILESTONES
            }
            for transaction in state.currency_transactions:
                if transaction.event_key.startswith("streak:"):
                    try:
                        milestone = int(transaction.event_key.partition(":")[2])
                    except ValueError:
                        continue
                    if milestone in STREAK_REWARD_MILESTONES:
                        claimed_values.add(milestone)
            state.claimed_streak_rewards = sorted(claimed_values)
        else:
            issues.append("claimed_streak_rewards: expected list")
        state.pending_feedback = _feedback_events(data.get("pending_feedback"), issues)
        state.inventory = _inventory(data.get("inventory"), state.inventory, issues)
        state.equipped = _equipped(data.get("equipped"), state.equipped, issues)
        state.last_active_day = _iso_date(
            data.get("last_active_day"), state.daily_stats.day, "last_active_day", issues
        )
        plant_ids = {plant.plant_id for plant in state.plants}
        active = data.get("active_plant_id")
        active_plant = next((plant for plant in state.plants if plant.plant_id == active), None)
        state._active_plant_reference_invalid = active is not None and not (
            active_plant is not None
            and active_plant.planted
            and not active_plant.fully_grown
        )
        state.active_plant_id = (
            active if active_plant is not None and active_plant.planted and not active_plant.fully_grown else None
        )
        state.active_plant_periods = _active_periods(data.get("active_plant_periods"), plant_ids, issues)
        state.last_processed_revlog_id = _nonnegative_int(
            data.get("last_processed_revlog_id"), 0, "last_processed_revlog_id", issues
        )
        state.processed_revlog_floor = _nonnegative_int(
            data.get("processed_revlog_floor"),
            state.last_processed_revlog_id,
            "processed_revlog_floor",
            issues,
        )
        raw_processed = data.get("processed_revlog_ids", [])
        if isinstance(raw_processed, list):
            processed = sorted({
                value
                for value in raw_processed
                if isinstance(value, int)
                and not isinstance(value, bool)
                and value > state.processed_revlog_floor
            })
            if len(processed) > MAX_PROCESSED_REVLOG_IDS:
                issues.append("processed_revlog_ids: exceeded current-day safety bound")
                processed = processed[-MAX_PROCESSED_REVLOG_IDS:]
            state.processed_revlog_ids = processed
        else:
            issues.append("processed_revlog_ids: expected list")
        pending = data.get("revlog_ledger_migration_pending", False)
        if not isinstance(pending, bool):
            issues.append("revlog_ledger_migration_pending: expected bool")
            pending = False
        state.revlog_ledger_migration_pending = pending
        state.scene_geometry_version = _bounded_int(
            data.get("scene_geometry_version"), 0, 0, 99, "scene_geometry_version", issues
        )
        if issues:
            logger.error("Garden state contract mismatches (%s): %s", len(issues), "; ".join(issues))
        return state


def _plant_to_dict(plant: Plant) -> dict[str, Any]:
    return {
        "plant_id": plant.plant_id,
        "species": plant.species,
        "name": plant.name,
        "slot_index": plant.slot_index,
        "growth_points": plant.growth_points,
        "bonus_remainder": plant.bonus_remainder,
        "personality": plant.personality,
        "planted_on": plant.planted_on,
        "memories": [memory.__dict__ for memory in plant.memories],
        "fertilizer": plant.fertilizer.__dict__ if plant.fertilizer else None,
        "fertilizer_history": [
            period.__dict__
            for period in sorted(
                plant.fertilizer_history,
                key=lambda item: (
                    float(item.started_at if item.started_at is not None else item.expires_at),
                    float(item.expires_at),
                    str(item.tier),
                ),
            )[-MAX_FERTILIZER_HISTORY:]
        ],
    }


def _nonnegative_int(value: Any, default: int, label: str, issues: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if value is not None:
            issues.append(f"{label}: expected int, got {type(value).__name__}")
        return default
    return max(0, value)


def _bounded_int(value: Any, default: int, low: int, high: int, label: str, issues: list[str]) -> int:
    parsed = _nonnegative_int(value, default, label, issues)
    bounded = max(low, min(high, parsed))
    if parsed != bounded:
        issues.append(f"{label}: repaired {parsed} to {bounded}")
    return bounded


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


def _valid_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
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
        "difficult_count", "recovered_lapses", "base_growth", "streak_bonus_growth",
        "fertilizer_growth", "bonus_growth", "growth_earned",
    ):
        setattr(result, key, _nonnegative_int(value.get(key), 0, f"daily_stats.{key}", issues))
    result.correct = min(result.correct, result.reviewed)
    result.wrong = min(result.wrong, max(0, result.reviewed - result.correct))
    result.bonus_growth = result.streak_bonus_growth + result.fertilizer_growth
    result.growth_earned = result.base_growth + result.bonus_growth
    plant_growth = value.get("plant_growth", {})
    if isinstance(plant_growth, dict):
        result.plant_growth = {
            str(key): max(0, int(points))
            for key, points in plant_growth.items()
            if isinstance(key, str) and isinstance(points, int) and not isinstance(points, bool)
        }
    else:
        issues.append("daily_stats.plant_growth: expected object")
    raw = value.get("completed_due_cards", False)
    result.completed_due_cards = raw if isinstance(raw, bool) else False
    return result


def _plants(value: Any, issues: list[str]) -> list[Plant]:
    if not isinstance(value, list):
        if value is not None:
            issues.append("plants: expected list")
        return []
    result: list[Plant] = []
    used_ids: set[str] = set()
    used_species: set[str] = set()
    used_slots: set[int] = set()
    # Count accepted plants rather than raw rows. This lets validation skip a
    # retired or malformed entry without accidentally discarding a valid plant
    # that appears later in the saved collection.
    for index, raw in enumerate(value):
        if len(result) >= MAX_COLLECTION_PLANTS:
            break
        if not isinstance(raw, dict):
            issues.append(f"plants[{index}]: expected object")
            continue
        species, name = raw.get("species"), raw.get("name")
        if species not in PLANT_SPECIES or not isinstance(name, str) or not name.strip():
            issues.append(f"plants[{index}]: missing supported species or name")
            continue
        if species in used_species:
            issues.append(f"plants[{index}].species: duplicate collection species")
            continue
        clean_name = " ".join(name.split())[:MAX_PLANT_NAME_LENGTH] or str(species).title()
        raw_id = raw.get("plant_id")
        plant_id = raw_id if isinstance(raw_id, str) and raw_id and raw_id not in used_ids else f"plant_{index + 1}"
        while plant_id in used_ids:
            plant_id += "_2"
        raw_slot = raw.get("slot_index")
        slot: Optional[int]
        if raw_slot is None:
            slot = None
        elif isinstance(raw_slot, int) and not isinstance(raw_slot, bool) and 0 <= raw_slot < MAX_GARDEN_SLOTS and raw_slot not in used_slots:
            slot = raw_slot
            used_slots.add(slot)
        else:
            slot = None
            issues.append(f"plants[{index}].slot_index: moved invalid or duplicate slot to collection")
        fertilizer = _fertilizer(raw.get("fertilizer"), f"plants[{index}].fertilizer", issues)
        fertilizer_history = _fertilizer_history(
            raw.get("fertilizer_history"),
            f"plants[{index}].fertilizer_history",
            issues,
        )
        used_ids.add(plant_id)
        used_species.add(species)
        result.append(Plant(
            plant_id=plant_id,
            species=species,
            name=clean_name,
            slot_index=slot,
            growth_points=min(GROWTH_THRESHOLDS[-1], _nonnegative_int(
                raw.get("growth_points"), 0, f"plants[{index}].growth_points", issues
            )),
            bonus_remainder=_bounded_int(
                raw.get("bonus_remainder"), 0, 0, 99, f"plants[{index}].bonus_remainder", issues
            ),
            personality=raw.get("personality", "balanced") if isinstance(raw.get("personality"), str) else "balanced",
            planted_on=_iso_date(
                raw.get("planted_on"), date.today().isoformat(), f"plants[{index}].planted_on", issues
            ),
            memories=_plant_memories(raw.get("memories"), index, issues),
            fertilizer=fertilizer,
            fertilizer_history=fertilizer_history,
        ))
    return sorted(result, key=lambda plant: (plant.slot_index is None, plant.slot_index or 0, plant.plant_id))


def _fertilizer(value: Any, label: str, issues: list[str]) -> Optional[Fertilizer]:
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append(f"{label}: expected object or null")
        return None
    tier = value.get("tier")
    specs = {"basic": 1, "quality": 2, "premium": 3}
    if tier not in specs:
        issues.append(f"{label}.tier: unsupported value")
        return None
    expires_at = _number(value.get("expires_at"), 0.0, 0.0, 99_999_999_999.0, f"{label}.expires_at", issues)
    started_value = value.get("started_at")
    if started_value is None:
        # A current-schema record missing its activation boundary cannot safely
        # reward historical synced rows. Previous schemas receive an explicit
        # migration-time boundary before reaching this validator.
        started_at = expires_at
        issues.append(f"{label}.started_at: missing; disabled conservatively")
    else:
        started_at = _number(
            started_value,
            expires_at,
            0.0,
            99_999_999_999.0,
            f"{label}.started_at",
            issues,
        )
    started_at = min(started_at, expires_at)
    return Fertilizer(str(tier), specs[str(tier)], expires_at, started_at)


def _fertilizer_history(
    value: Any,
    label: str,
    issues: list[str],
) -> list[Fertilizer]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    parsed: list[Fertilizer] = []
    seen: set[tuple[str, float, float]] = set()
    for index, raw in enumerate(value):
        period = _fertilizer(raw, f"{label}[{index}]", issues)
        if (
            period is None
            or period.started_at is None
            or float(period.started_at) >= float(period.expires_at)
        ):
            if period is not None:
                issues.append(f"{label}[{index}]: empty activation interval")
            continue
        identity = (
            str(period.tier),
            float(period.started_at),
            float(period.expires_at),
        )
        if identity in seen:
            issues.append(f"{label}[{index}]: duplicate activation interval")
            continue
        seen.add(identity)
        parsed.append(period)
    parsed.sort(key=lambda item: (
        float(item.started_at if item.started_at is not None else item.expires_at),
        float(item.expires_at),
        str(item.tier),
    ))
    if len(parsed) > MAX_FERTILIZER_HISTORY:
        issues.append(f"{label}: exceeded activation history safety bound")
        parsed = parsed[-MAX_FERTILIZER_HISTORY:]
    return parsed


def _plant_memories(value: Any, plant_index: int, issues: list[str]) -> list[PlantMemory]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"plants[{plant_index}].memories: expected list")
        return []
    result: list[PlantMemory] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(value[:64]):
        label = f"plants[{plant_index}].memories[{index}]"
        if not isinstance(raw, dict):
            continue
        memory_id, kind = raw.get("memory_id"), raw.get("kind")
        if not isinstance(memory_id, str) or not memory_id or memory_id in used_ids or kind not in PLANT_MEMORY_KINDS:
            issues.append(f"{label}: invalid or duplicate memory")
            continue
        occurred_on = _iso_date(raw.get("occurred_on"), "", f"{label}.occurred_on", issues)
        if not occurred_on:
            continue
        previous = raw.get("previous_stage") if raw.get("previous_stage") in GROWTH_STAGES else None
        new = raw.get("new_stage") if raw.get("new_stage") in GROWTH_STAGES else None
        if kind == "stage" and new is None:
            continue
        used_ids.add(memory_id)
        result.append(PlantMemory(
            memory_id, str(kind), occurred_on,
            _nonnegative_int(raw.get("value"), 0, f"{label}.value", issues), previous, new,
        ))
    # Preserve the saved sequence as the stable tie-breaker for memories that
    # happened on the same scheduler day.  Memory IDs describe the event; they
    # are not chronological (for example ``nurture:first`` sorts before
    # ``planted`` even though planting happened first).
    return result


def _transactions(value: Any, balance: int, issues: list[str]) -> list[CurrencyTransaction]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("currency_transactions: expected list")
        return []
    result: list[CurrencyTransaction] = []
    ids: set[str] = set()
    events: set[str] = set()
    for index, raw in enumerate(value[-MAX_TRANSACTION_HISTORY:]):
        if not isinstance(raw, dict):
            continue
        tx_id, event_key, reason = raw.get("transaction_id"), raw.get("event_key"), raw.get("reason")
        if not all(isinstance(item, str) and item for item in (tx_id, event_key, reason)):
            continue
        if tx_id in ids or event_key in events:
            issues.append(f"currency_transactions[{index}]: duplicate identity")
            continue
        delta, resulting = raw.get("delta"), raw.get("balance")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in (delta, resulting)) or resulting < 0:
            continue
        occurred = raw.get("occurred_at")
        if not _valid_iso_datetime(occurred):
            continue
        ids.add(tx_id)
        events.add(event_key)
        result.append(CurrencyTransaction(tx_id, event_key, reason, delta, resulting, occurred))
    if result:
        opening_balance = balance - sum(item.delta for item in result)
        if opening_balance < 0:
            issues.append("currency_transactions: discarded ledger with impossible opening balance")
            return []
        running = opening_balance
        repaired: list[CurrencyTransaction] = []
        for item in result:
            running += item.delta
            if running < 0:
                issues.append("currency_transactions: discarded ledger with a negative intermediate balance")
                return []
            if item.balance != running:
                issues.append(
                    f"currency_transactions: repaired balance for event {item.event_key!r} "
                    f"from {item.balance} to {running}"
                )
            repaired.append(CurrencyTransaction(
                item.transaction_id,
                item.event_key,
                item.reason,
                item.delta,
                running,
                item.occurred_at,
            ))
        result = repaired
    return result


def _feedback_events(value: Any, issues: list[str]) -> list[FeedbackEvent]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("pending_feedback: expected list")
        return []
    result: list[FeedbackEvent] = []
    ids: set[str] = set()
    for raw in value[-MAX_FEEDBACK_EVENTS:]:
        if not isinstance(raw, dict):
            continue
        event_id, kind, message = raw.get("event_id"), raw.get("kind"), raw.get("message")
        if not all(isinstance(item, str) and item for item in (event_id, kind, message)) or event_id in ids:
            continue
        occurred = raw.get("occurred_at")
        if not _valid_iso_datetime(occurred):
            continue
        plant_id = raw.get("plant_id") if isinstance(raw.get("plant_id"), str) else None
        ids.add(event_id)
        result.append(FeedbackEvent(event_id, kind, message, occurred, plant_id))
    return result


def _active_periods(value: Any, plant_ids: set[str], issues: list[str]) -> list[ActivePlantPeriod]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("active_plant_periods: expected list")
        return []
    result: list[ActivePlantPeriod] = []
    for index, raw in enumerate(value[-MAX_ACTIVE_PERIODS:]):
        if not isinstance(raw, dict):
            continue
        day_value = _iso_date(raw.get("day"), "", f"active_plant_periods[{index}].day", issues)
        plant_id = raw.get("plant_id")
        if plant_id is not None and plant_id not in plant_ids:
            plant_id = None
        started = _nonnegative_int(raw.get("started_at_ms"), 0, f"active_plant_periods[{index}].started_at_ms", issues)
        if day_value:
            result.append(ActivePlantPeriod(day_value, plant_id, started))
    return sorted(result, key=lambda period: (period.day, period.started_at_ms))


def _achievements(value: Any, issues: list[str]) -> dict[str, Achievement]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Achievement] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            continue
        name, description = raw.get("name"), raw.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            continue
        result[key] = Achievement(
            key, name, description,
            bool(raw.get("unlocked", False)),
            _number(raw.get("progress"), 0.0, 0.0, 1.0, f"achievements.{key}.progress", issues),
            raw.get("unlocked_at") if isinstance(raw.get("unlocked_at"), str) else None,
        )
    return result


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
        if key in value and isinstance(value[key], list):
            result[key] = list(dict.fromkeys(item for item in value[key] if isinstance(item, str) and item))
        elif key in value:
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
            issues.append(f"equipped.{key}: expected string")
    return result
