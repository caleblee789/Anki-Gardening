from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ..environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
)
from ..growth import CompletedGrowthChargeRequest
from ..purchases import CompletedPurchaseRequest

STATE_VERSION = 20
ONBOARDING_PROGRESS_VERSION = 1
GROWTH_STAGES = ["seed", "sprout", "young", "mature", "flowering", "rare"]
GROWTH_THRESHOLDS = [0, 500, 2_500, 8_000, 20_000, 50_000]
WEATHER_TYPES = set(WEATHER_CATALOG)
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
MAX_GARDEN_NAME_LENGTH = 40
MAX_TRANSACTION_HISTORY = 500
MAX_COMPLETED_PURCHASE_REQUESTS = 500
MAX_COMPLETED_GROWTH_CHARGE_REQUESTS = 500
MAX_FEEDBACK_EVENTS = 100
MAX_REWARD_DROP_HISTORY = 500
MAX_ACTIVE_PERIODS = 64
MAX_FERTILIZER_HISTORY = 64
MAX_BOOSTER_HISTORY = 64
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
class Booster:
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
    booster: Optional[Booster] = None
    booster_history: List[Booster] = field(default_factory=list)
    name_customized: bool = False
    passive_growth_remainder_fifths: int = 0

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
    booster_growth: int = 0
    weather_growth: int = 0
    scenery_growth: int = 0
    plant_nurtured_growth: Dict[str, int] = field(default_factory=dict)
    plant_passive_growth_fifths: Dict[str, int] = field(default_factory=dict)
    plant_passive_growth_credited: Dict[str, int] = field(default_factory=dict)
    plant_charge_growth: Dict[str, int] = field(default_factory=dict)
    plant_direct_reward_growth: Dict[str, int] = field(default_factory=dict)
    legacy_unattributed_growth: int = 0
    legacy_plant_growth: Dict[str, int] = field(default_factory=dict)
    growth_accounting_stale: bool = False
    completed_due_cards: bool = False

    @property
    def accuracy(self) -> float:
        total = self.correct + self.wrong
        return 0 if total == 0 else self.correct / total

    @property
    def study_growth_generated(self) -> int:
        return max(0, int(
            self.base_growth
            + self.streak_bonus_growth
            + self.fertilizer_growth
            + self.booster_growth
            + self.weather_growth
            + self.scenery_growth
        ))

    @property
    def plant_growth(self) -> Dict[str, int]:
        plant_ids = {
            *self.plant_nurtured_growth,
            *self.plant_passive_growth_credited,
            *self.plant_charge_growth,
            *self.plant_direct_reward_growth,
        }
        return {
            plant_id: sum((
                max(0, int(self.plant_nurtured_growth.get(plant_id, 0))),
                max(0, int(self.plant_passive_growth_credited.get(plant_id, 0))),
                max(0, int(self.plant_charge_growth.get(plant_id, 0))),
                max(0, int(self.plant_direct_reward_growth.get(plant_id, 0))),
            ))
            for plant_id in sorted(plant_ids)
        }

    @property
    def charge_growth(self) -> int:
        return sum(max(0, int(value)) for value in self.plant_charge_growth.values())

    @property
    def direct_reward_growth(self) -> int:
        return sum(
            max(0, int(value))
            for value in self.plant_direct_reward_growth.values()
        )

    @property
    def bonus_growth(self) -> int:
        return max(
            0,
            self.study_growth_generated
            - max(0, int(self.base_growth))
            + self.charge_growth
            + self.direct_reward_growth,
        )

    @property
    def growth_earned(self) -> int:
        return (
            max(0, int(self.legacy_unattributed_growth))
            + sum(self.plant_growth.values())
        )

    def reconcile_growth_totals(self) -> None:
        """Normalize canonical maps; compatibility totals are computed properties."""

        for field_name in (
            "plant_nurtured_growth",
            "plant_passive_growth_fifths",
            "plant_passive_growth_credited",
            "plant_charge_growth",
            "plant_direct_reward_growth",
            "legacy_plant_growth",
        ):
            mapping = getattr(self, field_name)
            setattr(self, field_name, {
                str(plant_id): max(0, int(value))
                for plant_id, value in mapping.items()
                if str(plant_id)
            })


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
    title: str = ""
    asset_category: str = ""
    asset_key: str = ""
    amount: int = 0


@dataclass
class RewardDrop:
    revlog_id: int
    scheduler_day: str
    kind: str
    amount: int
    occurred_at: str


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


class OnboardingStep(str, Enum):
    """The persisted six-step Garden setup state machine.

    Anki Home is deliberately not represented here: it is an entry/resume
    surface rather than a counted Garden step.
    """

    INTRODUCTION = "introduction"
    NURSERY = "nursery"
    CONFIRMATION = "confirmation"
    PLACEMENT = "placement"
    NURTURE = "nurture"
    COMPLETION = "completion"
    DONE = "done"


@dataclass
class OnboardingProgress:
    version: int = ONBOARDING_PROGRESS_VERSION
    step: OnboardingStep = OnboardingStep.INTRODUCTION
    pending_species: Optional[str] = None
    starter_plant_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": ONBOARDING_PROGRESS_VERSION,
            "step": self.step.value,
            "pending_species": self.pending_species,
            "starter_plant_id": self.starter_plant_id,
        }


@dataclass
class GardenLoadoutState:
    """The single persisted authority for garden appearance and passives."""

    weather_id: str = DEFAULT_WEATHER_ID
    scenery_id: str = DEFAULT_SCENERY_ID
    decoration_id: Optional[str] = None
    visibility: Dict[str, bool] = field(default_factory=lambda: {
        "weather": True,
        "scenery": True,
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "weather_id": self.weather_id,
            "scenery_id": self.scenery_id,
            "decoration_id": self.decoration_id,
            "visibility": {
                "weather": bool(self.visibility.get("weather", True)),
                "scenery": bool(self.visibility.get("scenery", True)),
            },
        }


@dataclass
class GardenState:
    version: int = STATE_VERSION
    garden_name: str = "My Garden"
    garden_setup_version: int = 0
    streak_days: int = 0
    total_reviews: int = 0
    total_correct: int = 0
    total_wrong: int = 0
    unlocked_slots: int = 2
    unlocked_species: List[str] = field(default_factory=list)
    starter_selection_complete: bool = False
    onboarding: OnboardingProgress = field(default_factory=OnboardingProgress)
    loadout: GardenLoadoutState = field(default_factory=GardenLoadoutState)
    plants: List[Plant] = field(default_factory=list)
    achievements: Dict[str, Achievement] = field(default_factory=dict)
    daily_stats: DailyStats = field(default_factory=DailyStats)
    currency_balance: int = 0
    currency_transactions: List[CurrencyTransaction] = field(default_factory=list)
    completed_purchase_requests: List[CompletedPurchaseRequest] = field(default_factory=list)
    completed_growth_charge_requests: List[CompletedGrowthChargeRequest] = field(default_factory=list)
    claimed_streak_rewards: List[int] = field(default_factory=list)
    pending_feedback: List[FeedbackEvent] = field(default_factory=list)
    reward_seed: str = field(default_factory=lambda: uuid.uuid4().hex)
    reward_drop_history: List[RewardDrop] = field(default_factory=list)
    eligible_reward_count: int = 0
    ultra_pity_misses: int = 0
    daily_environment_claims: Dict[str, str] = field(default_factory=dict)
    consumables: Dict[str, int] = field(default_factory=lambda: {
        "booster_potion": 0,
        **{charge_id: 0 for charge_id in GROWTH_CHARGES},
    })
    inventory: Dict[str, List[str]] = field(default_factory=lambda: {
        "pots": ["ceramic_minimal"],
        "scenery": [DEFAULT_SCENERY_ID],
        "decorations": ["lantern"],
        "weather": [DEFAULT_WEATHER_ID],
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
            self.garden_setup_version = max(1, int(self.garden_setup_version))
            self.starter_selection_complete = True
            self.unlocked_species = list(dict.fromkeys([
                *self.unlocked_species,
                *(plant.species for plant in self.plants if plant.species in PLANT_SPECIES),
            ]))
            if self.onboarding.step == OnboardingStep.INTRODUCTION:
                self.onboarding = OnboardingProgress(
                    step=OnboardingStep.DONE,
                    starter_plant_id=self.plants[0].plant_id,
                )

    @property
    def selected_weather(self) -> str:
        """Compatibility alias backed by the canonical loadout."""

        return self.loadout.weather_id

    @selected_weather.setter
    def selected_weather(self, value: str) -> None:
        self.loadout.weather_id = str(value)

    @property
    def selected_background(self) -> str:
        """Compatibility alias for the canonical Scenery selection."""

        return self.loadout.scenery_id

    @selected_background.setter
    def selected_background(self, value: str) -> None:
        self.loadout.scenery_id = str(value)

    @property
    def environment_visibility(self) -> Dict[str, bool]:
        """Compatibility alias backed by the canonical loadout visibility."""

        return self.loadout.visibility

    @environment_visibility.setter
    def environment_visibility(self, value: Dict[str, bool]) -> None:
        self.loadout.visibility = dict(value)

    @property
    def equipped(self) -> Dict[str, str]:
        """Read-only compatibility projection; never persisted as a mirror."""

        return {
            "weather": self.loadout.weather_id,
            "background": self.loadout.scenery_id,
            "decoration": self.loadout.decoration_id or "none",
        }

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({
            "version": STATE_VERSION,
            "garden_name": self.garden_name,
            "garden_setup_version": self.garden_setup_version,
            "streak_days": self.streak_days,
            "total_reviews": self.total_reviews,
            "total_correct": self.total_correct,
            "total_wrong": self.total_wrong,
            "unlocked_slots": self.unlocked_slots,
            "unlocked_species": list(self.unlocked_species),
            "starter_selection_complete": self.starter_selection_complete,
            "onboarding": self.onboarding.to_dict(),
            "loadout": self.loadout.to_dict(),
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
                **{
                    key: value
                    for key, value in self.daily_stats.__dict__.items()
                    if key not in {
                        "plant_growth",
                        "plant_nurtured_growth",
                        "plant_passive_growth_fifths",
                        "plant_passive_growth_credited",
                        "plant_charge_growth",
                        "plant_direct_reward_growth",
                        "legacy_plant_growth",
                    }
                },
                "growth_earned": self.daily_stats.growth_earned,
                "charge_growth": self.daily_stats.charge_growth,
                "direct_reward_growth": self.daily_stats.direct_reward_growth,
                "bonus_growth": self.daily_stats.bonus_growth,
                "plant_growth": dict(self.daily_stats.plant_growth),
                "plant_nurtured_growth": dict(self.daily_stats.plant_nurtured_growth),
                "plant_passive_growth_fifths": dict(
                    self.daily_stats.plant_passive_growth_fifths
                ),
                "plant_passive_growth_credited": dict(
                    self.daily_stats.plant_passive_growth_credited
                ),
                "plant_charge_growth": dict(self.daily_stats.plant_charge_growth),
                "plant_direct_reward_growth": dict(
                    self.daily_stats.plant_direct_reward_growth
                ),
                "legacy_plant_growth": dict(self.daily_stats.legacy_plant_growth),
            },
            "currency_balance": self.currency_balance,
            "currency_transactions": [tx.__dict__ for tx in self.currency_transactions[-MAX_TRANSACTION_HISTORY:]],
            "completed_purchase_requests": [
                request.to_dict()
                for request in self.completed_purchase_requests[-MAX_COMPLETED_PURCHASE_REQUESTS:]
            ],
            "completed_growth_charge_requests": [
                request.to_dict()
                for request in self.completed_growth_charge_requests[
                    -MAX_COMPLETED_GROWTH_CHARGE_REQUESTS:
                ]
            ],
            "claimed_streak_rewards": sorted(set(self.claimed_streak_rewards)),
            "pending_feedback": [event.__dict__ for event in self.pending_feedback[-MAX_FEEDBACK_EVENTS:]],
            "reward_seed": self.reward_seed,
            "reward_drop_history": [
                event.__dict__ for event in self.reward_drop_history[-MAX_REWARD_DROP_HISTORY:]
            ],
            "eligible_reward_count": self.eligible_reward_count,
            "ultra_pity_misses": self.ultra_pity_misses,
            "daily_environment_claims": dict(self.daily_environment_claims),
            "consumables": dict(self.consumables),
            "inventory": self.inventory,
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
        state.garden_name = _garden_name(data.get("garden_name"), issues)
        state.garden_setup_version = _bounded_int(
            data.get("garden_setup_version"), 0, 0, 1, "garden_setup_version", issues
        )
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
        state.loadout = _garden_loadout(data.get("loadout"), issues)
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
        state.onboarding = _onboarding_progress(
            data.get("onboarding"),
            state.plants,
            issues,
        )
        state.achievements = _achievements(data.get("achievements"), issues)
        state.currency_balance = _nonnegative_int(data.get("currency_balance"), 0, "currency_balance", issues)
        state.currency_transactions = _transactions(data.get("currency_transactions"), state.currency_balance, issues)
        state.completed_purchase_requests = _completed_purchase_requests(
            data.get("completed_purchase_requests"), issues
        )
        state.completed_growth_charge_requests = _completed_growth_charge_requests(
            data.get("completed_growth_charge_requests"), issues
        )
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
        state.reward_seed = _reward_seed(data.get("reward_seed"), state.reward_seed, issues)
        state.reward_drop_history = _reward_drop_history(data.get("reward_drop_history"), issues)
        state.eligible_reward_count = _nonnegative_int(
            data.get("eligible_reward_count"),
            0,
            "eligible_reward_count",
            issues,
        )
        state.ultra_pity_misses = _nonnegative_int(
            data.get("ultra_pity_misses"),
            0,
            "ultra_pity_misses",
            issues,
        )
        state.daily_environment_claims = _daily_environment_claims(
            data.get("daily_environment_claims"), issues
        )
        state.consumables = _consumables(data.get("consumables"), issues)
        state.inventory = _inventory(data.get("inventory"), state.inventory, issues)
        scenery_owned = list(dict.fromkeys([
            DEFAULT_SCENERY_ID,
            *state.inventory.get("scenery", []),
        ]))
        scenery_owned = [item_id for item_id in scenery_owned if item_id in SCENERY_CATALOG]
        state.inventory["scenery"] = list(scenery_owned)
        weather_owned = list(dict.fromkeys([
            DEFAULT_WEATHER_ID,
            *state.inventory.get("weather", []),
        ]))
        state.inventory["weather"] = [
            item_id for item_id in weather_owned if item_id in WEATHER_CATALOG
        ]
        if state.selected_background not in state.inventory["scenery"]:
            issues.append("selected_background: repaired to an owned scenery")
            state.selected_background = DEFAULT_SCENERY_ID
        if state.selected_weather not in state.inventory["weather"]:
            issues.append("selected_weather: repaired to an owned weather")
            state.selected_weather = DEFAULT_WEATHER_ID
        decorations = state.inventory.get("decorations", [])
        if state.loadout.decoration_id not in decorations:
            if state.loadout.decoration_id is not None:
                issues.append("loadout.decoration_id: repaired to none")
            state.loadout.decoration_id = None
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
        "passive_growth_remainder_fifths": plant.passive_growth_remainder_fifths,
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
        "booster": plant.booster.__dict__ if plant.booster else None,
        "booster_history": [
            period.__dict__
            for period in sorted(
                plant.booster_history,
                key=lambda item: (
                    float(item.started_at if item.started_at is not None else item.expires_at),
                    float(item.expires_at),
                ),
            )[-MAX_BOOSTER_HISTORY:]
        ],
        "name_customized": bool(plant.name_customized),
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


def _garden_name(value: Any, issues: list[str]) -> str:
    if not isinstance(value, str):
        if value is not None:
            issues.append("garden_name: expected string")
        return "My Garden"
    clean = " ".join(value.split())
    if not clean:
        issues.append("garden_name: repaired blank name")
        return "My Garden"
    if len(clean) > MAX_GARDEN_NAME_LENGTH:
        issues.append("garden_name: truncated to the current length limit")
    return clean[:MAX_GARDEN_NAME_LENGTH]


def _onboarding_progress(
    value: Any,
    plants: list[Plant],
    issues: list[str],
) -> OnboardingProgress:
    """Validate setup progress without deriving it from display copy or config."""

    if not isinstance(value, dict):
        if value is not None:
            issues.append("onboarding: expected object")
        return OnboardingProgress()
    version = value.get("version")
    if version != ONBOARDING_PROGRESS_VERSION:
        issues.append("onboarding.version: unsupported version")
        return OnboardingProgress()
    try:
        step = OnboardingStep(str(value.get("step", "")))
    except ValueError:
        issues.append("onboarding.step: unexpected value")
        step = OnboardingStep.INTRODUCTION

    pending = value.get("pending_species")
    if pending is not None and pending not in PLANT_SPECIES:
        issues.append("onboarding.pending_species: unsupported species")
        pending = None
    starter_id = value.get("starter_plant_id")
    if starter_id is not None and not isinstance(starter_id, str):
        issues.append("onboarding.starter_plant_id: expected string or null")
        starter_id = None

    plant_ids = {plant.plant_id for plant in plants}
    if starter_id not in plant_ids:
        if starter_id is not None:
            issues.append("onboarding.starter_plant_id: missing plant")
        starter_id = plants[0].plant_id if plants else None

    if step in {OnboardingStep.CONFIRMATION, OnboardingStep.PLACEMENT} and pending is None:
        issues.append("onboarding.pending_species: required for current step")
        step = OnboardingStep.NURSERY
    if not plants and step in {
        OnboardingStep.NURTURE,
        OnboardingStep.COMPLETION,
        OnboardingStep.DONE,
    }:
        issues.append("onboarding.step: requires a starter plant")
        step = OnboardingStep.INTRODUCTION
        starter_id = None
    elif plants and step in {
        OnboardingStep.INTRODUCTION,
        OnboardingStep.NURSERY,
        OnboardingStep.CONFIRMATION,
        OnboardingStep.PLACEMENT,
    }:
        issues.append("onboarding.step: repaired past atomic placement")
        step = OnboardingStep.NURTURE
        pending = None
    if step in {OnboardingStep.INTRODUCTION, OnboardingStep.NURTURE, OnboardingStep.COMPLETION, OnboardingStep.DONE}:
        pending = None
    if step == OnboardingStep.DONE:
        starter_id = starter_id or (plants[0].plant_id if plants else None)
    return OnboardingProgress(
        version=ONBOARDING_PROGRESS_VERSION,
        step=step,
        pending_species=pending,
        starter_plant_id=starter_id,
    )


def _reward_seed(value: Any, default: str, issues: list[str]) -> str:
    clean = str(value or "").strip()
    if not (8 <= len(clean) <= 128) or any(character.isspace() for character in clean):
        if value is not None:
            issues.append("reward_seed: replaced invalid seed")
        return default
    return clean


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
        "fertilizer_growth", "booster_growth", "weather_growth", "scenery_growth",
        "legacy_unattributed_growth",
    ):
        setattr(result, key, _nonnegative_int(value.get(key), 0, f"daily_stats.{key}", issues))
    result.correct = min(result.correct, result.reviewed)
    result.wrong = min(result.wrong, max(0, result.reviewed - result.correct))
    def growth_map(key: str) -> dict[str, int]:
        raw_map = value.get(key, {})
        if not isinstance(raw_map, dict):
            issues.append(f"daily_stats.{key}: expected object")
            return {}
        return {
            str(plant_id): max(0, int(points))
            for plant_id, points in raw_map.items()
            if (
                isinstance(plant_id, str)
                and plant_id
                and isinstance(points, int)
                and not isinstance(points, bool)
            )
        }

    result.plant_nurtured_growth = growth_map("plant_nurtured_growth")
    result.plant_passive_growth_fifths = growth_map("plant_passive_growth_fifths")
    result.plant_passive_growth_credited = growth_map("plant_passive_growth_credited")
    result.plant_charge_growth = growth_map("plant_charge_growth")
    result.plant_direct_reward_growth = growth_map("plant_direct_reward_growth")
    result.legacy_plant_growth = growth_map("legacy_plant_growth")
    stale = value.get("growth_accounting_stale", False)
    if not isinstance(stale, bool):
        issues.append("daily_stats.growth_accounting_stale: expected bool")
        stale = False
    result.growth_accounting_stale = stale
    persisted_plant_growth = growth_map("plant_growth")
    result.reconcile_growth_totals()
    if persisted_plant_growth and persisted_plant_growth != result.plant_growth:
        issues.append("daily_stats.plant_growth: repaired from typed allocation totals")
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
        if species not in PLANT_SPECIES:
            issues.append(f"plants[{index}]: missing supported species")
            continue
        if species in used_species:
            issues.append(f"plants[{index}].species: duplicate collection species")
            continue
        species_name = str(species).replace("_", " ").title()
        clean_name = (
            " ".join(name.split())[:MAX_PLANT_NAME_LENGTH]
            if isinstance(name, str)
            else ""
        )
        if not clean_name:
            clean_name = f"{species_name} Plant"[:MAX_PLANT_NAME_LENGTH]
            issues.append(f"plants[{index}].name: repaired blank name")
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
        booster = _booster(raw.get("booster"), f"plants[{index}].booster", issues)
        booster_history = _booster_history(
            raw.get("booster_history"),
            f"plants[{index}].booster_history",
            issues,
        )
        name_customized = raw.get("name_customized", False)
        if not isinstance(name_customized, bool):
            issues.append(f"plants[{index}].name_customized: expected bool")
            name_customized = False
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
            passive_growth_remainder_fifths=_bounded_int(
                raw.get("passive_growth_remainder_fifths"),
                0,
                0,
                4,
                f"plants[{index}].passive_growth_remainder_fifths",
                issues,
            ),
            personality=raw.get("personality", "balanced") if isinstance(raw.get("personality"), str) else "balanced",
            planted_on=_iso_date(
                raw.get("planted_on"), date.today().isoformat(), f"plants[{index}].planted_on", issues
            ),
            memories=_plant_memories(raw.get("memories"), index, issues),
            fertilizer=fertilizer,
            fertilizer_history=fertilizer_history,
            booster=booster,
            booster_history=booster_history,
            name_customized=name_customized,
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


def _booster(value: Any, label: str, issues: list[str]) -> Optional[Booster]:
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append(f"{label}: expected object or null")
        return None
    growth = _bounded_int(
        value.get("growth_per_answer"), 5, 1, 100, f"{label}.growth_per_answer", issues
    )
    expires_at = _number(
        value.get("expires_at"), 0.0, 0.0, 99_999_999_999.0, f"{label}.expires_at", issues
    )
    started_value = value.get("started_at")
    if started_value is None:
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
    return Booster(growth, expires_at, min(started_at, expires_at))


def _booster_history(value: Any, label: str, issues: list[str]) -> list[Booster]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    parsed: list[Booster] = []
    seen: set[tuple[int, float, float]] = set()
    for index, raw in enumerate(value):
        period = _booster(raw, f"{label}[{index}]", issues)
        if (
            period is None
            or period.started_at is None
            or float(period.started_at) >= float(period.expires_at)
        ):
            continue
        identity = (
            int(period.growth_per_answer),
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
    ))
    if len(parsed) > MAX_BOOSTER_HISTORY:
        issues.append(f"{label}: exceeded activation history safety bound")
        parsed = parsed[-MAX_BOOSTER_HISTORY:]
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


def _completed_purchase_requests(
    value: Any,
    issues: list[str],
) -> list[CompletedPurchaseRequest]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("completed_purchase_requests: expected list")
        return []
    result: list[CompletedPurchaseRequest] = []
    request_ids: set[str] = set()
    for index, raw in enumerate(value[-MAX_COMPLETED_PURCHASE_REQUESTS:]):
        record = CompletedPurchaseRequest.from_dict(raw)
        if record is None:
            issues.append(f"completed_purchase_requests[{index}]: invalid record")
            continue
        if record.request_id in request_ids:
            issues.append(
                f"completed_purchase_requests[{index}]: duplicate request identity"
            )
            continue
        request_ids.add(record.request_id)
        result.append(record)
    return result


def _completed_growth_charge_requests(
    value: Any,
    issues: list[str],
) -> list[CompletedGrowthChargeRequest]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("completed_growth_charge_requests: expected list")
        return []
    result: list[CompletedGrowthChargeRequest] = []
    request_ids: set[str] = set()
    for index, raw in enumerate(value[-MAX_COMPLETED_GROWTH_CHARGE_REQUESTS:]):
        record = CompletedGrowthChargeRequest.from_dict(raw)
        if record is None:
            issues.append(f"completed_growth_charge_requests[{index}]: invalid record")
            continue
        if record.request_id in request_ids:
            issues.append(
                f"completed_growth_charge_requests[{index}]: duplicate request identity"
            )
            continue
        request_ids.add(record.request_id)
        result.append(record)
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
        title = raw.get("title") if isinstance(raw.get("title"), str) else ""
        asset_category = (
            raw.get("asset_category") if isinstance(raw.get("asset_category"), str) else ""
        )
        asset_key = raw.get("asset_key") if isinstance(raw.get("asset_key"), str) else ""
        amount = _nonnegative_int(raw.get("amount"), 0, "pending_feedback.amount", issues)
        ids.add(event_id)
        result.append(FeedbackEvent(
            event_id, kind, message, occurred, plant_id,
            title, asset_category, asset_key, amount,
        ))
    return result


def _reward_drop_history(value: Any, issues: list[str]) -> list[RewardDrop]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("reward_drop_history: expected list")
        return []
    result: list[RewardDrop] = []
    seen: set[int] = set()
    for index, raw in enumerate(value[-MAX_REWARD_DROP_HISTORY:]):
        if not isinstance(raw, dict):
            continue
        revlog_id = _nonnegative_int(
            raw.get("revlog_id"), 0, f"reward_drop_history[{index}].revlog_id", issues
        )
        scheduler_day = _iso_date(
            raw.get("scheduler_day"), "", f"reward_drop_history[{index}].scheduler_day", issues
        )
        kind = raw.get("kind")
        amount = _nonnegative_int(
            raw.get("amount"), 0, f"reward_drop_history[{index}].amount", issues
        )
        occurred_at = raw.get("occurred_at")
        valid_kinds = {
            "garden_coins",
            "booster_potion",
            *GROWTH_CHARGES,
            *WEATHER_CATALOG,
            *SCENERY_CATALOG,
        }
        if (
            revlog_id <= 0
            or revlog_id in seen
            or not scheduler_day
            or kind not in valid_kinds
            or not _valid_iso_datetime(occurred_at)
        ):
            continue
        seen.add(revlog_id)
        result.append(RewardDrop(
            revlog_id,
            scheduler_day,
            str(kind),
            amount,
            str(occurred_at),
        ))
    return result


def _consumables(value: Any, issues: list[str]) -> dict[str, int]:
    result = {
        "booster_potion": 0,
        **{charge_id: 0 for charge_id in GROWTH_CHARGES},
    }
    if value is None:
        return result
    if not isinstance(value, dict):
        issues.append("consumables: expected object")
        return result
    for key in result:
        result[key] = _bounded_int(
            value.get(key), 0, 0, 1_000_000, f"consumables.{key}", issues
        )
    return result


def _daily_environment_claims(value: Any, issues: list[str]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("daily_environment_claims: expected object")
        return {}
    result: dict[str, str] = {}
    valid_items = set(SCENERY_CATALOG) | set(WEATHER_CATALOG)
    for item_id, day_value in value.items():
        if not isinstance(item_id, str) or item_id not in valid_items:
            continue
        parsed = _iso_date(
            day_value,
            "",
            f"daily_environment_claims.{item_id}",
            issues,
        )
        if parsed:
            result[item_id] = parsed
    return result


def _environment_visibility(value: Any, issues: list[str]) -> dict[str, bool]:
    result = {"weather": True, "scenery": True}
    if value is None:
        return result
    if not isinstance(value, dict):
        issues.append("environment_visibility: expected object")
        return result
    for key in result:
        raw = value.get(key, True)
        if isinstance(raw, bool):
            result[key] = raw
        else:
            issues.append(f"environment_visibility.{key}: expected bool")
    return result


def _garden_loadout(value: Any, issues: list[str]) -> GardenLoadoutState:
    if value is None:
        return GardenLoadoutState()
    if not isinstance(value, dict):
        issues.append("loadout: expected object")
        return GardenLoadoutState()
    weather = _string(
        value.get("weather_id"), DEFAULT_WEATHER_ID, "loadout.weather_id", issues
    )
    scenery = _string(
        value.get("scenery_id"), DEFAULT_SCENERY_ID, "loadout.scenery_id", issues
    )
    if weather not in WEATHER_CATALOG:
        issues.append(f"loadout.weather_id: unexpected value {weather!r}")
        weather = DEFAULT_WEATHER_ID
    if scenery not in SCENERY_CATALOG:
        issues.append(f"loadout.scenery_id: unexpected value {scenery!r}")
        scenery = DEFAULT_SCENERY_ID
    decoration = value.get("decoration_id")
    if decoration in ("", "none"):
        decoration = None
    if decoration is not None and not isinstance(decoration, str):
        issues.append("loadout.decoration_id: expected string or null")
        decoration = None
    return GardenLoadoutState(
        weather_id=weather,
        scenery_id=scenery,
        decoration_id=decoration,
        visibility=_environment_visibility(value.get("visibility"), issues),
    )


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
    for key, raw in value.items():
        normalized_key = "scenery" if key == "backgrounds" else str(key)
        if isinstance(raw, list):
            parsed = list(dict.fromkeys(
                item for item in raw if isinstance(item, str) and item
            ))
            if normalized_key == "scenery":
                result["scenery"] = list(dict.fromkeys([
                    *result.get("scenery", []),
                    *parsed,
                ]))
            else:
                # Preserve extension-owned and historical inventory lists even
                # when the current Collection has no renderer for them.
                result[normalized_key] = parsed
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
            issues.append(f"equipped.{key}: expected string")
    return result
