from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from ..environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    GARDEN_FEATURE_CATALOG,
    GROWTH_CHARGES,
    canonical_garden_feature_id,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
)
from ..growth import (
    CompletedGrowthChargeRequest,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    stage_progress,
)
from ..purchases import CompletedPurchaseRequest

STATE_VERSION = 23


class GardenFeatureIdList(list[str]):
    """Canonical ID list accepting schema-22 identities at its boundary."""

    def __init__(self, values=()) -> None:
        super().__init__()
        self.extend(values)

    def append(self, value: str) -> None:
        super().append(canonical_garden_feature_id(value))

    def extend(self, values) -> None:
        for value in values:
            self.append(value)

    def insert(self, index: int, value: str) -> None:
        super().insert(index, canonical_garden_feature_id(value))

    def __contains__(self, value: object) -> bool:
        return super().__contains__(canonical_garden_feature_id(value))


class InventoryState(dict[str, List[str]]):
    """Canonical inventory with a non-persisted schema-22 access alias."""

    @staticmethod
    def _key(key: object) -> object:
        return "garden_features" if key == "weather" else key

    def __init__(self, values=()) -> None:
        super().__init__()
        for key, value in dict(values).items():
            self[key] = value

    def __getitem__(self, key: object) -> List[str]:
        return super().__getitem__(self._key(key))

    def __setitem__(self, key: object, value: List[str]) -> None:
        normalized_key = self._key(key)
        if normalized_key == "garden_features":
            value = GardenFeatureIdList(dict.fromkeys(
                canonical_garden_feature_id(item) for item in value
            ))
        super().__setitem__(normalized_key, value)

    def get(self, key: object, default=None):
        return super().get(self._key(key), default)

    def setdefault(self, key: object, default=None):
        normalized_key = self._key(key)
        if normalized_key not in self:
            self[normalized_key] = [] if default is None else default
        return super().__getitem__(normalized_key)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._key(key))
ONBOARDING_PROGRESS_VERSION = 1
GROWTH_UNITS_PER_POINT = 100
GARDEN_FEATURE_TYPES = set(GARDEN_FEATURE_CATALOG)
WEATHER_TYPES = GARDEN_FEATURE_TYPES
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
MAX_REWARD_RECEIPTS = 250
MAX_ACTIVE_PERIODS = 64
MAX_FERTILIZER_HISTORY = 64
MAX_BOOSTER_HISTORY = 64
MAX_PROCESSED_REVLOG_IDS = 100_000
STREAK_REWARD_MILESTONES = {7, 14, 30, 100}
STREAK_BONUS_TIERS = ((1, 0), (7, 5), (14, 10), (30, 15), (100, 20), (365, 25))
GARDEN_FIND_OUTCOME_STATUSES = frozenset({"miss", "hit", "paused"})
DAILY_COMPLETION_STATUSES = frozenset({
    "in_progress",
    "waiting_for_learning",
    "complete",
    "not_eligible",
    "unavailable",
})
ENVIRONMENT_PITY_TIERS = ("rare", "very_rare", "ultra")
STAGE_CHECKPOINT_PERCENTAGES = (25, 50, 75)
MAX_CARD_EFFECT_BATCHES = 5
CARD_EFFECT_SPECS = {
    "fertilizer_basic": (100, 100, 100),
    "fertilizer_quality": (200, 150, 150),
    "fertilizer_premium": (300, 250, 250),
    "booster_potion": (500, 100, 135),
}

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
class CardEffectBatch:
    """One paid, card-counted effect dose.

    Growth is stored in hundredth units. ``total_cards`` records the activated
    dose size (including a loadout extension); ``remaining_cards`` is the only
    value decremented by eligible cards.
    """

    effect_id: str
    growth_per_card_units: int
    total_cards: int
    remaining_cards: int
    activated_at: str = ""
    source_event_key: str = ""


@dataclass
class DailyCompletionState:
    """Durable technical projection for the collection-wide daily objective."""

    scheduler_day: str = field(default_factory=lambda: date.today().isoformat())
    status: str = "unavailable"
    starting_required_cards: int = 0
    starting_required_cards_completed: int = 0
    remaining_required_reviews: int = 0
    remaining_learning_steps: int = 0
    future_learning_steps_before_cutoff: int = 0
    next_learning_due_at_ms: int = 0
    cutoff_at_ms: int = 0
    cards_completed_today: int = 0
    reward_claimed: bool = False
    unavailable_reason: str = ""


@dataclass(init=False)
class DailyLoadoutSchedule:
    """Scenery day lock plus the continuous-session Garden Feature snapshot."""

    scheduler_day: str = ""
    locked_at_ms: int = 0
    garden_feature_id: str = ""
    scenery_id: str = ""
    queued_for_day: str = ""
    pending_garden_feature_id: str = ""
    queued_scenery_id: str = ""

    def __init__(
        self,
        scheduler_day: str = "",
        locked_at_ms: int = 0,
        garden_feature_id: str = "",
        scenery_id: str = "",
        queued_for_day: str = "",
        pending_garden_feature_id: str = "",
        queued_scenery_id: str = "",
        *,
        weather_id: str | None = None,
        queued_weather_id: str | None = None,
    ) -> None:
        self.scheduler_day = str(scheduler_day)
        self.locked_at_ms = int(locked_at_ms)
        self.garden_feature_id = canonical_garden_feature_id(
            weather_id if weather_id is not None else garden_feature_id
        )
        self.scenery_id = str(scenery_id)
        self.queued_for_day = str(queued_for_day)
        self.pending_garden_feature_id = canonical_garden_feature_id(
            queued_weather_id
            if queued_weather_id is not None
            else pending_garden_feature_id
        )
        self.queued_scenery_id = str(queued_scenery_id)

    @property
    def weather_id(self) -> str:
        return self.garden_feature_id

    @weather_id.setter
    def weather_id(self, value: str) -> None:
        self.garden_feature_id = canonical_garden_feature_id(value)

    @property
    def queued_weather_id(self) -> str:
        return self.pending_garden_feature_id

    @queued_weather_id.setter
    def queued_weather_id(self, value: str) -> None:
        self.pending_garden_feature_id = canonical_garden_feature_id(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduler_day": self.scheduler_day,
            "locked_at_ms": self.locked_at_ms,
            "garden_feature_id": self.garden_feature_id,
            "scenery_id": self.scenery_id,
            "queued_for_day": self.queued_for_day,
            "pending_garden_feature_id": self.pending_garden_feature_id,
            "queued_scenery_id": self.queued_scenery_id,
        }


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
    # ``growth_points`` remains the whole-point compatibility field. Exact
    # schema-22 Growth is the pair (growth_points, growth_remainder_units).
    growth_remainder_units: int = 0
    checkpoint_claims: List[str] = field(default_factory=list)
    stage_reward_claims: List[str] = field(default_factory=list)
    completed_on: Optional[str] = None
    completed_at_ms: int = 0
    completion_cards: int = 0
    completion_active_days: int = 0
    full_bloom_reward_claimed: bool = False
    fertilizer_card_batches: List[CardEffectBatch] = field(default_factory=list)
    fertilizer_card_queue: List[CardEffectBatch] = field(default_factory=list)
    booster_card_batches: List[CardEffectBatch] = field(default_factory=list)
    booster_card_queue: List[CardEffectBatch] = field(default_factory=list)

    @property
    def growth_units(self) -> int:
        return min(
            GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT,
            max(0, int(self.growth_points)) * GROWTH_UNITS_PER_POINT + max(
                0, min(GROWTH_UNITS_PER_POINT - 1, int(self.growth_remainder_units))
            ),
        )

    @growth_units.setter
    def growth_units(self, value: int) -> None:
        bounded = max(0, min(GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT, int(value)))
        self.growth_points, self.growth_remainder_units = divmod(
            bounded, GROWTH_UNITS_PER_POINT
        )

    @property
    def growth_stage(self) -> str:
        return stage_progress(self.growth_points).stage

    @property
    def fully_grown(self) -> bool:
        return stage_progress(self.growth_points).fully_grown

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
    # None means the start-of-day due state was not observed, so All Clear
    # must fail closed rather than infer a historical obligation.
    due_started_with_cards: Optional[bool] = None
    # Schema-22 exact accounting. These counters are event-flow totals, not
    # compatibility mirrors of the whole-point maps above.
    answer_growth_units: int = 0
    instant_growth_units: int = 0
    applied_growth_units: int = 0
    redirected_growth_units: int = 0
    shared_growth_units: int = 0
    stored_growth_units: int = 0
    plant_applied_growth_units: Dict[str, int] = field(default_factory=dict)
    plant_shared_growth_units: Dict[str, int] = field(default_factory=dict)
    plant_instant_growth_units: Dict[str, int] = field(default_factory=dict)

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
            "plant_applied_growth_units",
            "plant_shared_growth_units",
            "plant_instant_growth_units",
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
    transaction_type: str = "legacy"
    source: str = "legacy"
    source_id: str = ""
    scheduler_day: str = ""
    correlation_id: str = ""


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
    correlation_id: str = ""


@dataclass
class RewardReceipt:
    """Bounded presentation history for an applied reward event.

    Idempotency never depends on this display history; the unbounded
    ``applied_reward_event_keys`` ledger remains authoritative after receipts
    or currency transactions are pruned.
    """

    event_key: str
    reward_type: str
    source: str
    source_id: str
    scheduler_day: str
    correlation_id: str
    occurred_at: str
    amount: int = 0
    item_id: str = ""
    plant_id: str = ""
    title: str = ""
    description: str = ""


def bounded_reward_receipts(
    receipts: List[RewardReceipt],
    *,
    limit: int = MAX_REWARD_RECEIPTS,
) -> List[RewardReceipt]:
    """Keep the newest complete correlation groups for presentation history.

    A very large sync can produce more rows than the display-history limit in
    one correlation. Such a group is compacted into resource totals plus as
    many zero-value Find references as fit, preserving both the atomic total
    and a bounded Recent Finds projection. Idempotency never depends on these
    receipts.
    """

    bounded_limit = max(1, int(limit))
    groups: Dict[str, List[RewardReceipt]] = {}
    order: List[str] = []
    for receipt in receipts:
        identity = str(receipt.correlation_id or receipt.event_key)
        if identity not in groups:
            groups[identity] = []
        elif identity in order:
            order.remove(identity)
        order.append(identity)
        groups[identity].append(receipt)
    retained: List[str] = []
    retained_rows = 0
    for identity in reversed(order):
        group = groups[identity]
        if len(group) > bounded_limit:
            group = _compact_reward_receipt_group(group, bounded_limit)
            groups[identity] = group
        group_size = len(group)
        if retained and retained_rows + group_size > bounded_limit:
            break
        retained.append(identity)
        retained_rows += group_size
        if retained_rows >= bounded_limit:
            break
    retained.reverse()
    return [receipt for identity in retained for receipt in groups[identity]]


def _compact_reward_receipt_group(
    receipts: List[RewardReceipt],
    limit: int,
) -> List[RewardReceipt]:
    """Compress one oversized correlation without dropping its resource total."""

    if not receipts:
        return []
    bounded_limit = max(1, int(limit))
    value_receipts = [
        receipt for receipt in receipts if receipt.reward_type != "reference"
    ]

    def aggregate(mode: str) -> List[RewardReceipt]:
        buckets: Dict[tuple[str, str], List[RewardReceipt]] = {}
        for receipt in value_receipts:
            if mode == "resource_item":
                key = (receipt.reward_type, receipt.item_id)
            elif mode == "resource":
                key = (receipt.reward_type, "")
            else:
                key = ("mixed", "")
            buckets.setdefault(key, []).append(receipt)
        result: List[RewardReceipt] = []
        correlation = str(receipts[-1].correlation_id or receipts[-1].event_key)
        for index, ((reward_type, item_id), bucket) in enumerate(
            buckets.items(), start=1
        ):
            sources = tuple(dict.fromkeys(item.source for item in bucket))
            source_ids = tuple(dict.fromkeys(
                item.source_id for item in bucket if item.source_id
            ))
            plant_ids = tuple(dict.fromkeys(
                item.plant_id for item in bucket if item.plant_id
            ))
            titles = tuple(dict.fromkeys(
                item.title for item in bucket if item.title
            ))
            descriptions = tuple(dict.fromkeys(
                item.description for item in bucket if item.description
            ))
            latest = max(bucket, key=lambda item: item.occurred_at)
            result.append(RewardReceipt(
                event_key=f"reward-summary:{correlation}:{index}",
                reward_type=reward_type,
                source=sources[0] if len(sources) == 1 else "reward_summary",
                source_id=source_ids[0] if len(source_ids) == 1 else "",
                scheduler_day=latest.scheduler_day,
                correlation_id=correlation,
                occurred_at=latest.occurred_at,
                amount=sum(max(0, int(item.amount)) for item in bucket),
                item_id=item_id,
                plant_id=plant_ids[0] if len(plant_ids) == 1 else "",
                title=titles[0] if len(titles) == 1 else "Consolidated rewards",
                description=(
                    descriptions[0]
                    if len(descriptions) == 1
                    else "Aggregated reward history"
                ),
            ))
        return result

    aggregates = aggregate("resource_item")
    if len(aggregates) > bounded_limit:
        aggregates = aggregate("resource")
    if len(aggregates) > bounded_limit:
        aggregates = aggregate("mixed")

    references: Dict[str, RewardReceipt] = {}
    reference_order: List[str] = []
    for receipt in receipts:
        if (
            receipt.source not in {"garden_find", "garden_find_environment"}
            or not receipt.event_key.startswith("garden_find:")
        ):
            continue
        if receipt.event_key in reference_order:
            reference_order.remove(receipt.event_key)
        reference_order.append(receipt.event_key)
        references[receipt.event_key] = RewardReceipt(
            event_key=receipt.event_key,
            reward_type="reference",
            source=receipt.source,
            source_id=receipt.source_id,
            scheduler_day=receipt.scheduler_day,
            correlation_id=receipt.correlation_id,
            occurred_at=receipt.occurred_at,
            amount=0,
            item_id=receipt.item_id,
            plant_id=receipt.plant_id,
            title=receipt.title,
            description=receipt.description,
        )
    available_reference_slots = max(0, bounded_limit - len(aggregates))
    kept_reference_ids = (
        reference_order[-available_reference_slots:]
        if available_reference_slots
        else []
    )
    return [*aggregates, *(references[event_key] for event_key in kept_reference_ids)]


@dataclass
class GardenFindOutcome:
    """Durable consumed Garden Find roll, including misses and cap pauses."""

    answer_key: str
    scheduler_day: str
    status: str
    pool_id: str
    pool_version: str
    occurred_at: str
    reward_id: str = ""
    reward_type: str = ""
    amount: int = 0
    item_id: str = ""
    display_name: str = ""
    description: str = ""
    tier: str = ""
    artwork_ref: str = ""
    localization_key: str = ""

    @property
    def outcome_key(self) -> str:
        """Pool-qualified identity; independent pools may share one answer."""

        return f"{self.pool_id}:{self.answer_key}"


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
    category: str = ""
    requirement: str = ""
    reward_summary: str = ""
    rewarded_at: Optional[str] = None
    reward_event_key: str = ""
    historical_backfill: bool = False


class OnboardingStep(str, Enum):
    """The persisted five-surface Garden setup state machine.

    Anki Home is deliberately not represented here: it is an entry/resume
    surface rather than a counted Garden step. ``CONFIRMATION`` remains
    permanently reserved for decoding older state, but has no visible UI.
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


@dataclass(init=False)
class GardenLoadoutState:
    """The single persisted authority for garden appearance and passives."""

    garden_feature_id: str = DEFAULT_GARDEN_FEATURE_ID
    scenery_id: str = DEFAULT_SCENERY_ID
    decoration_id: Optional[str] = None
    visibility: Dict[str, bool] = field(default_factory=lambda: {
        "garden_feature": True,
        "scenery": True,
    })

    def __init__(
        self,
        garden_feature_id: str = DEFAULT_GARDEN_FEATURE_ID,
        scenery_id: str = DEFAULT_SCENERY_ID,
        decoration_id: Optional[str] = None,
        visibility: Dict[str, bool] | None = None,
        *,
        weather_id: str | None = None,
    ) -> None:
        self.garden_feature_id = canonical_garden_feature_id(
            weather_id if weather_id is not None else garden_feature_id
        )
        self.scenery_id = str(scenery_id)
        self.decoration_id = decoration_id
        raw_visibility = dict(visibility or {})
        self.visibility = {
            "garden_feature": bool(
                raw_visibility.get(
                    "garden_feature",
                    raw_visibility.get("weather", True),
                )
            ),
            "scenery": bool(raw_visibility.get("scenery", True)),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "garden_feature_id": self.garden_feature_id,
            "scenery_id": self.scenery_id,
            "decoration_id": self.decoration_id,
            "visibility": {
                "garden_feature": bool(self.visibility.get("garden_feature", True)),
                "scenery": bool(self.visibility.get("scenery", True)),
            },
        }

    @property
    def weather_id(self) -> str:
        return self.garden_feature_id

    @weather_id.setter
    def weather_id(self, value: str) -> None:
        self.garden_feature_id = canonical_garden_feature_id(value)


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
    daily_completion: DailyCompletionState = field(default_factory=DailyCompletionState)
    daily_loadout: DailyLoadoutSchedule = field(default_factory=DailyLoadoutSchedule)
    stored_growth_units: int = 0
    streak_growth_remainder_units: int = 0
    checkpoint_coin_carry_units: int = 0
    first_daily_completion_reward_claimed: bool = False
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
    environment_completion_counts: Dict[str, int] = field(default_factory=dict)
    # Schema-21 reward ownership. Visible histories are bounded, while the
    # event and answer ledgers deliberately are not: pruning either authority
    # would make an old reward or answer eligible again.
    reward_state_initialized: bool = False
    reward_activation_ms: int = 0
    progression_activation_ms: int = 0
    applied_reward_event_keys: List[str] = field(default_factory=list)
    recent_reward_receipts: List[RewardReceipt] = field(default_factory=list)
    processed_answer_keys: List[str] = field(default_factory=list)
    answer_lineage_bindings: Dict[str, str] = field(default_factory=dict)
    pending_reanswer_lineages: Dict[str, int] = field(default_factory=dict)
    achievement_history_fingerprint: str = ""
    achievement_history_high_water_revlog_id: int = 0
    finalized_day_fingerprints: Dict[str, str] = field(default_factory=dict)
    current_non_again_run: int = 0
    lifetime_eligible_answers: int = 0
    garden_find_activation_ms: int = 0
    garden_find_drought_count: int = 0
    garden_find_daily_counts: Dict[str, int] = field(default_factory=dict)
    garden_find_reward_daily_counts: Dict[str, Dict[str, int]] = field(
        default_factory=dict
    )
    garden_find_outcomes: Dict[str, GardenFindOutcome] = field(default_factory=dict)
    garden_find_ultra_misses: int = 0
    environment_pity_misses: Dict[str, int] = field(default_factory=lambda: {
        tier: 0 for tier in ENVIRONMENT_PITY_TIERS
    })
    consumables: Dict[str, int] = field(default_factory=lambda: {
        "booster_potion": 0,
        "fertilizer_basic": 0,
        "fertilizer_quality": 0,
        "fertilizer_premium": 0,
        **{charge_id: 0 for charge_id in GROWTH_CHARGES},
    })
    inventory: Dict[str, List[str]] = field(default_factory=lambda: InventoryState({
        "pots": ["ceramic_minimal"],
        "scenery": [DEFAULT_SCENERY_ID],
        "decorations": ["lantern"],
        "garden_features": [DEFAULT_GARDEN_FEATURE_ID],
    }))
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
        if not isinstance(self.inventory, InventoryState):
            source_inventory = dict(self.inventory or {})
            legacy_features = source_inventory.pop("weather", [])
            canonical_features = source_inventory.get("garden_features", [])
            source_inventory["garden_features"] = list(dict.fromkeys((
                DEFAULT_GARDEN_FEATURE_ID,
                *(canonical_garden_feature_id(item) for item in legacy_features),
                *(canonical_garden_feature_id(item) for item in canonical_features),
            )))
            self.inventory = InventoryState(source_inventory)
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
        """Legacy migration-window alias for the active Garden Feature."""

        return self.loadout.garden_feature_id

    @selected_weather.setter
    def selected_weather(self, value: str) -> None:
        self.loadout.garden_feature_id = canonical_garden_feature_id(value)

    @property
    def selected_garden_feature(self) -> str:
        return self.loadout.garden_feature_id

    @selected_garden_feature.setter
    def selected_garden_feature(self, value: str) -> None:
        self.loadout.garden_feature_id = canonical_garden_feature_id(value)

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

        return {
            **self.loadout.visibility,
            "weather": bool(self.loadout.visibility.get("garden_feature", True)),
        }

    @environment_visibility.setter
    def environment_visibility(self, value: Dict[str, bool]) -> None:
        source = dict(value)
        if "garden_feature" not in source and "weather" in source:
            source["garden_feature"] = bool(source["weather"])
        source.pop("weather", None)
        self.loadout.visibility = source

    @property
    def equipped(self) -> Dict[str, str]:
        """Read-only compatibility projection; never persisted as a mirror."""

        return {
            "garden_feature": self.loadout.garden_feature_id,
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
                        "plant_applied_growth_units",
                        "plant_shared_growth_units",
                        "plant_instant_growth_units",
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
                "plant_applied_growth_units": dict(
                    self.daily_stats.plant_applied_growth_units
                ),
                "plant_shared_growth_units": dict(
                    self.daily_stats.plant_shared_growth_units
                ),
                "plant_instant_growth_units": dict(
                    self.daily_stats.plant_instant_growth_units
                ),
            },
            "daily_completion": self.daily_completion.__dict__,
            "daily_loadout": self.daily_loadout.to_dict(),
            "stored_growth_units": self.stored_growth_units,
            "streak_growth_remainder_units": self.streak_growth_remainder_units,
            "checkpoint_coin_carry_units": self.checkpoint_coin_carry_units,
            "first_daily_completion_reward_claimed": bool(
                self.first_daily_completion_reward_claimed
            ),
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
            "environment_completion_counts": {
                str(item_id): max(0, int(count))
                for item_id, count in self.environment_completion_counts.items()
                if str(item_id) in SCENERY_CATALOG
            },
            "reward_state_initialized": bool(self.reward_state_initialized),
            "reward_activation_ms": self.reward_activation_ms,
            "progression_activation_ms": self.progression_activation_ms,
            "applied_reward_event_keys": list(dict.fromkeys(
                key for key in self.applied_reward_event_keys
                if isinstance(key, str) and key
            )),
            "recent_reward_receipts": [
                receipt.__dict__
                for receipt in bounded_reward_receipts(self.recent_reward_receipts)
            ],
            "processed_answer_keys": list(dict.fromkeys(
                key for key in self.processed_answer_keys
                if isinstance(key, str) and key
            )),
            "answer_lineage_bindings": dict(self.answer_lineage_bindings),
            "pending_reanswer_lineages": dict(self.pending_reanswer_lineages),
            "achievement_history_fingerprint": self.achievement_history_fingerprint,
            "achievement_history_high_water_revlog_id": (
                self.achievement_history_high_water_revlog_id
            ),
            "finalized_day_fingerprints": dict(self.finalized_day_fingerprints),
            "current_non_again_run": self.current_non_again_run,
            "lifetime_eligible_answers": self.lifetime_eligible_answers,
            "garden_find_activation_ms": self.garden_find_activation_ms,
            "garden_find_drought_count": self.garden_find_drought_count,
            "garden_find_daily_counts": dict(self.garden_find_daily_counts),
            "garden_find_reward_daily_counts": {
                day_value: dict(counts)
                for day_value, counts in self.garden_find_reward_daily_counts.items()
            },
            "garden_find_outcomes": {
                outcome.outcome_key: outcome.__dict__
                for outcome in self.garden_find_outcomes.values()
            },
            "garden_find_ultra_misses": self.garden_find_ultra_misses,
            "environment_pity_misses": {
                tier: max(0, int(self.environment_pity_misses.get(tier, 0)))
                for tier in ENVIRONMENT_PITY_TIERS
            },
            "consumables": dict(self.consumables),
            "inventory": self.inventory,
            "last_active_day": self.last_active_day,
            "active_plant_id": self.active_plant_id,
            "active_plant_periods": [
                period.__dict__ for period in self.active_plant_periods
            ],
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
        state.daily_completion = _daily_completion_state(
            data.get("daily_completion"), state.daily_stats.day, issues
        )
        state.daily_loadout = _daily_loadout_schedule(
            data.get("daily_loadout"), issues
        )
        state.stored_growth_units = _nonnegative_int(
            data.get("stored_growth_units"), 0, "stored_growth_units", issues
        )
        state.streak_growth_remainder_units = _bounded_int(
            data.get("streak_growth_remainder_units"),
            0,
            0,
            GROWTH_UNITS_PER_POINT - 1,
            "streak_growth_remainder_units",
            issues,
        )
        state.checkpoint_coin_carry_units = _bounded_int(
            data.get("checkpoint_coin_carry_units"),
            0,
            0,
            GROWTH_UNITS_PER_POINT - 1,
            "checkpoint_coin_carry_units",
            issues,
        )
        first_completion_claimed = data.get(
            "first_daily_completion_reward_claimed", False
        )
        if not isinstance(first_completion_claimed, bool):
            issues.append("first_daily_completion_reward_claimed: expected bool")
            first_completion_claimed = False
        state.first_daily_completion_reward_claimed = first_completion_claimed
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
        state.environment_completion_counts = _environment_completion_counts(
            data.get("environment_completion_counts"), issues
        )
        initialized = data.get("reward_state_initialized", False)
        if not isinstance(initialized, bool):
            issues.append("reward_state_initialized: expected bool")
            initialized = False
        state.reward_state_initialized = initialized
        state.reward_activation_ms = _nonnegative_int(
            data.get("reward_activation_ms"), 0, "reward_activation_ms", issues
        )
        state.progression_activation_ms = _nonnegative_int(
            data.get("progression_activation_ms"),
            0,
            "progression_activation_ms",
            issues,
        )
        state.applied_reward_event_keys = _unique_event_keys(
            data.get("applied_reward_event_keys"),
            "applied_reward_event_keys",
            issues,
        )
        state.recent_reward_receipts = _reward_receipts(
            data.get("recent_reward_receipts"), issues
        )
        state.processed_answer_keys = _unique_event_keys(
            data.get("processed_answer_keys"),
            "processed_answer_keys",
            issues,
        )
        state.answer_lineage_bindings = _answer_lineage_bindings(
            data.get("answer_lineage_bindings"), issues
        )
        state.pending_reanswer_lineages = _pending_reanswer_lineages(
            data.get("pending_reanswer_lineages"), issues
        )
        state.achievement_history_fingerprint = _optional_token(
            data.get("achievement_history_fingerprint"),
            "achievement_history_fingerprint",
            issues,
        )
        state.achievement_history_high_water_revlog_id = _nonnegative_int(
            data.get("achievement_history_high_water_revlog_id"),
            0,
            "achievement_history_high_water_revlog_id",
            issues,
        )
        state.finalized_day_fingerprints = _day_fingerprints(
            data.get("finalized_day_fingerprints"), issues
        )
        state.current_non_again_run = _nonnegative_int(
            data.get("current_non_again_run"), 0, "current_non_again_run", issues
        )
        state.lifetime_eligible_answers = _nonnegative_int(
            data.get("lifetime_eligible_answers"),
            0,
            "lifetime_eligible_answers",
            issues,
        )
        state.garden_find_activation_ms = _nonnegative_int(
            data.get("garden_find_activation_ms"), 0, "garden_find_activation_ms", issues
        )
        state.garden_find_drought_count = _nonnegative_int(
            data.get("garden_find_drought_count"), 0, "garden_find_drought_count", issues
        )
        state.garden_find_daily_counts = _garden_find_daily_counts(
            data.get("garden_find_daily_counts"), issues
        )
        state.garden_find_reward_daily_counts = _garden_find_reward_daily_counts(
            data.get("garden_find_reward_daily_counts"), issues
        )
        state.garden_find_outcomes = _garden_find_outcomes(
            data.get("garden_find_outcomes"), issues
        )
        state.garden_find_ultra_misses = _nonnegative_int(
            data.get("garden_find_ultra_misses"), 0, "garden_find_ultra_misses", issues
        )
        state.environment_pity_misses = _environment_pity_misses(
            data.get("environment_pity_misses"), issues
        )
        if data.get("environment_pity_misses") is None:
            state.environment_pity_misses["ultra"] = state.garden_find_ultra_misses
        if state.reward_state_initialized:
            if state.reward_activation_ms <= 0:
                issues.append(
                    "reward_state_initialized: disabled without an activation boundary"
                )
                state.reward_state_initialized = False
                state.reward_activation_ms = 0
                state.progression_activation_ms = 0
                state.garden_find_activation_ms = 0
            elif state.garden_find_activation_ms <= 0:
                issues.append(
                    "garden_find_activation_ms: repaired from reward activation boundary"
                )
                state.garden_find_activation_ms = state.reward_activation_ms
        else:
            state.reward_activation_ms = 0
            state.progression_activation_ms = 0
            state.garden_find_activation_ms = 0
        if not state.starter_selection_complete and state.progression_activation_ms:
            issues.append(
                "progression_activation_ms: disabled until starter selection completes"
            )
            state.progression_activation_ms = 0

        # Exact visible evidence can repair a missing authority entry, but the
        # authority itself remains unbounded and therefore survives pruning.
        state.applied_reward_event_keys = list(dict.fromkeys([
            *state.applied_reward_event_keys,
            *(
                transaction.event_key
                for transaction in state.currency_transactions
                if transaction.delta > 0
                or transaction.transaction_type == "credit"
            ),
            *(receipt.event_key for receipt in state.recent_reward_receipts),
            *(
                achievement.reward_event_key
                for achievement in state.achievements.values()
                if achievement.reward_event_key
            ),
        ]))
        state.processed_answer_keys = list(dict.fromkeys([
            *state.processed_answer_keys,
            *(outcome.answer_key for outcome in state.garden_find_outcomes.values()),
        ]))
        state.consumables = _consumables(data.get("consumables"), issues)
        state.inventory = _inventory(data.get("inventory"), state.inventory, issues)
        scenery_owned = list(dict.fromkeys([
            DEFAULT_SCENERY_ID,
            *state.inventory.get("scenery", []),
        ]))
        scenery_owned = [item_id for item_id in scenery_owned if item_id in SCENERY_CATALOG]
        state.inventory["scenery"] = list(scenery_owned)
        feature_owned = list(dict.fromkeys([
            DEFAULT_GARDEN_FEATURE_ID,
            *(
                canonical_garden_feature_id(item_id)
                for item_id in state.inventory.get("garden_features", [])
            ),
        ]))
        state.inventory["garden_features"] = [
            item_id for item_id in feature_owned if item_id in GARDEN_FEATURE_CATALOG
        ]
        if state.selected_background not in state.inventory["scenery"]:
            issues.append("selected_background: repaired to an owned scenery")
            state.selected_background = DEFAULT_SCENERY_ID
        if state.selected_garden_feature not in state.inventory["garden_features"]:
            issues.append("selected_garden_feature: repaired to an owned Garden Feature")
            state.selected_garden_feature = DEFAULT_GARDEN_FEATURE_ID
        if (
            state.daily_loadout.garden_feature_id
            and state.daily_loadout.garden_feature_id not in state.inventory["garden_features"]
        ):
            issues.append("daily_loadout.garden_feature_id: repaired to the active feature")
            state.daily_loadout.garden_feature_id = state.selected_garden_feature
        if (
            state.daily_loadout.scenery_id
            and state.daily_loadout.scenery_id not in state.inventory["scenery"]
        ):
            issues.append("daily_loadout.scenery_id: repaired to the selected scenery")
            state.daily_loadout.scenery_id = state.selected_background
        if (
            state.daily_loadout.pending_garden_feature_id
            and state.daily_loadout.pending_garden_feature_id not in state.inventory["garden_features"]
        ):
            issues.append("daily_loadout.pending_garden_feature_id: removed unowned feature")
            state.daily_loadout.pending_garden_feature_id = ""
        if (
            state.daily_loadout.queued_scenery_id
            and state.daily_loadout.queued_scenery_id not in state.inventory["scenery"]
        ):
            issues.append("daily_loadout.queued_scenery_id: removed unowned scenery")
            state.daily_loadout.queued_scenery_id = ""
        if (
            state.daily_loadout.queued_for_day
            and not (
                state.daily_loadout.pending_garden_feature_id
                or state.daily_loadout.queued_scenery_id
            )
        ):
            state.daily_loadout.queued_for_day = ""
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
        "growth_remainder_units": plant.growth_remainder_units,
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
            )
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
            )
        ],
        "name_customized": bool(plant.name_customized),
        "checkpoint_claims": list(dict.fromkeys(plant.checkpoint_claims)),
        "stage_reward_claims": list(dict.fromkeys(plant.stage_reward_claims)),
        "completed_on": plant.completed_on,
        "completed_at_ms": plant.completed_at_ms,
        "completion_cards": plant.completion_cards,
        "completion_active_days": plant.completion_active_days,
        "full_bloom_reward_claimed": bool(plant.full_bloom_reward_claimed),
        "fertilizer_card_batches": [
            batch.__dict__ for batch in plant.fertilizer_card_batches
        ],
        "fertilizer_card_queue": [
            batch.__dict__ for batch in plant.fertilizer_card_queue
        ],
        "booster_card_batches": [
            batch.__dict__ for batch in plant.booster_card_batches
        ],
        "booster_card_queue": [
            batch.__dict__ for batch in plant.booster_card_queue
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
    elif step == OnboardingStep.CONFIRMATION:
        issues.append("onboarding.step: retired confirmation advanced to placement")
        step = OnboardingStep.PLACEMENT
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
        "answer_growth_units", "instant_growth_units", "applied_growth_units",
        "redirected_growth_units", "shared_growth_units", "stored_growth_units",
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
    result.plant_applied_growth_units = growth_map("plant_applied_growth_units")
    result.plant_shared_growth_units = growth_map("plant_shared_growth_units")
    result.plant_instant_growth_units = growth_map("plant_instant_growth_units")
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
    raw_due = value.get("due_started_with_cards")
    if raw_due is None or isinstance(raw_due, bool):
        result.due_started_with_cards = raw_due
    else:
        issues.append("daily_stats.due_started_with_cards: expected bool or null")
        result.due_started_with_cards = None
    return result


def _daily_completion_state(
    value: Any,
    fallback_day: str,
    issues: list[str],
) -> DailyCompletionState:
    result = DailyCompletionState(scheduler_day=fallback_day)
    if not isinstance(value, dict):
        if value is not None:
            issues.append("daily_completion: expected object")
        return result
    result.scheduler_day = _iso_date(
        value.get("scheduler_day"),
        fallback_day,
        "daily_completion.scheduler_day",
        issues,
    )
    status = value.get("status", "unavailable")
    if status not in DAILY_COMPLETION_STATUSES:
        issues.append("daily_completion.status: unsupported value")
        status = "unavailable"
    result.status = str(status)
    for key in (
        "starting_required_cards",
        "starting_required_cards_completed",
        "remaining_required_reviews",
        "remaining_learning_steps",
        "future_learning_steps_before_cutoff",
        "next_learning_due_at_ms",
        "cutoff_at_ms",
        "cards_completed_today",
    ):
        setattr(
            result,
            key,
            _nonnegative_int(
                value.get(key), 0, f"daily_completion.{key}", issues
            ),
        )
    result.starting_required_cards_completed = min(
        result.starting_required_cards,
        result.starting_required_cards_completed,
    )
    reward_claimed = value.get("reward_claimed", False)
    if not isinstance(reward_claimed, bool):
        issues.append("daily_completion.reward_claimed: expected bool")
        reward_claimed = False
    result.reward_claimed = reward_claimed
    reason = value.get("unavailable_reason", "")
    if not isinstance(reason, str):
        issues.append("daily_completion.unavailable_reason: expected string")
        reason = ""
    result.unavailable_reason = reason.strip()[:240]
    if result.status == "complete":
        if (
            result.remaining_required_reviews
            or result.remaining_learning_steps
            or result.future_learning_steps_before_cutoff
        ):
            issues.append("daily_completion: complete state cleared remaining obligations")
        result.remaining_required_reviews = 0
        result.remaining_learning_steps = 0
        result.future_learning_steps_before_cutoff = 0
        result.next_learning_due_at_ms = 0
        result.starting_required_cards_completed = result.starting_required_cards
    if result.status != "unavailable":
        result.unavailable_reason = ""
    return result


def _daily_loadout_schedule(value: Any, issues: list[str]) -> DailyLoadoutSchedule:
    if not isinstance(value, dict):
        if value is not None:
            issues.append("daily_loadout: expected object")
        return DailyLoadoutSchedule()
    scheduler_day = _iso_date(
        value.get("scheduler_day"), "", "daily_loadout.scheduler_day", issues
    ) if value.get("scheduler_day") not in (None, "") else ""
    queued_for_day = _iso_date(
        value.get("queued_for_day"), "", "daily_loadout.queued_for_day", issues
    ) if value.get("queued_for_day") not in (None, "") else ""
    feature_id = canonical_garden_feature_id(
        value.get("garden_feature_id", value.get("weather_id", ""))
    )
    scenery_id = value.get("scenery_id", "")
    pending_feature_id = canonical_garden_feature_id(
        value.get("pending_garden_feature_id", value.get("queued_weather_id", ""))
    )
    queued_scenery_id = value.get("queued_scenery_id", "")
    if feature_id not in {"", *GARDEN_FEATURE_CATALOG}:
        issues.append("daily_loadout.garden_feature_id: unsupported value")
        feature_id = ""
    if scenery_id not in {"", *SCENERY_CATALOG}:
        issues.append("daily_loadout.scenery_id: unsupported value")
        scenery_id = ""
    if pending_feature_id not in {"", *GARDEN_FEATURE_CATALOG}:
        issues.append("daily_loadout.pending_garden_feature_id: unsupported value")
        pending_feature_id = ""
    if queued_scenery_id not in {"", *SCENERY_CATALOG}:
        issues.append("daily_loadout.queued_scenery_id: unsupported value")
        queued_scenery_id = ""
    locked_at_ms = _nonnegative_int(
        value.get("locked_at_ms"), 0, "daily_loadout.locked_at_ms", issues
    )
    if not scheduler_day:
        locked_at_ms = 0
        feature_id = ""
        scenery_id = ""
    if not queued_for_day:
        queued_scenery_id = ""
    return DailyLoadoutSchedule(
        scheduler_day=scheduler_day,
        locked_at_ms=locked_at_ms,
        garden_feature_id=str(feature_id),
        scenery_id=str(scenery_id),
        queued_for_day=queued_for_day,
        pending_garden_feature_id=str(pending_feature_id),
        queued_scenery_id=str(queued_scenery_id),
    )


def _environment_pity_misses(value: Any, issues: list[str]) -> dict[str, int]:
    result = {tier: 0 for tier in ENVIRONMENT_PITY_TIERS}
    if value is None:
        return result
    if not isinstance(value, dict):
        issues.append("environment_pity_misses: expected object")
        return result
    for tier in ENVIRONMENT_PITY_TIERS:
        result[tier] = _nonnegative_int(
            value.get(tier), 0, f"environment_pity_misses.{tier}", issues
        )
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
        fertilizer_card_batches = _card_effect_batches(
            raw.get("fertilizer_card_batches"),
            family="fertilizer",
            label=f"plants[{index}].fertilizer_card_batches",
            issues=issues,
        )
        fertilizer_card_queue = _card_effect_batches(
            raw.get("fertilizer_card_queue"),
            family="fertilizer",
            label=f"plants[{index}].fertilizer_card_queue",
            issues=issues,
            limit=max(0, MAX_CARD_EFFECT_BATCHES - len(fertilizer_card_batches)),
        )
        booster_card_batches = _card_effect_batches(
            raw.get("booster_card_batches"),
            family="booster",
            label=f"plants[{index}].booster_card_batches",
            issues=issues,
        )
        booster_card_queue = _card_effect_batches(
            raw.get("booster_card_queue"),
            family="booster",
            label=f"plants[{index}].booster_card_queue",
            issues=issues,
            limit=max(0, MAX_CARD_EFFECT_BATCHES - len(booster_card_batches)),
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
            growth_remainder_units=_bounded_int(
                raw.get("growth_remainder_units"),
                0,
                0,
                GROWTH_UNITS_PER_POINT - 1,
                f"plants[{index}].growth_remainder_units",
                issues,
            ),
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
            checkpoint_claims=_checkpoint_claims(
                raw.get("checkpoint_claims"),
                f"plants[{index}].checkpoint_claims",
                issues,
            ),
            stage_reward_claims=_stage_reward_claims(
                raw.get("stage_reward_claims"),
                f"plants[{index}].stage_reward_claims",
                issues,
            ),
            completed_on=_optional_iso_date(
                raw.get("completed_on"),
                f"plants[{index}].completed_on",
                issues,
            ),
            completed_at_ms=_nonnegative_int(
                raw.get("completed_at_ms"),
                0,
                f"plants[{index}].completed_at_ms",
                issues,
            ),
            completion_cards=_nonnegative_int(
                raw.get("completion_cards"),
                0,
                f"plants[{index}].completion_cards",
                issues,
            ),
            completion_active_days=_nonnegative_int(
                raw.get("completion_active_days"),
                0,
                f"plants[{index}].completion_active_days",
                issues,
            ),
            full_bloom_reward_claimed=(
                raw.get("full_bloom_reward_claimed", False)
                if isinstance(raw.get("full_bloom_reward_claimed", False), bool)
                else False
            ),
            fertilizer_card_batches=fertilizer_card_batches,
            fertilizer_card_queue=fertilizer_card_queue,
            booster_card_batches=booster_card_batches,
            booster_card_queue=booster_card_queue,
        ))
        accepted = result[-1]
        if accepted.growth_points >= GROWTH_THRESHOLDS[-1]:
            accepted.growth_remainder_units = 0
        elif (
            accepted.completed_on
            or accepted.completed_at_ms
            or accepted.full_bloom_reward_claimed
            or accepted.completion_cards
            or accepted.completion_active_days
        ):
            issues.append(f"plants[{index}]: removed Full Bloom metadata before completion")
            accepted.completed_on = None
            accepted.completed_at_ms = 0
            accepted.full_bloom_reward_claimed = False
            accepted.completion_cards = 0
            accepted.completion_active_days = 0
    return sorted(result, key=lambda plant: (plant.slot_index is None, plant.slot_index or 0, plant.plant_id))


def _checkpoint_claims(
    value: Any,
    label: str,
    issues: list[str],
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    allowed = {
        f"{stage}:{percentage}"
        for stage in GROWTH_STAGES[1:]
        for percentage in STAGE_CHECKPOINT_PERCENTAGES
    }
    return list(dict.fromkeys(
        item for item in value if isinstance(item, str) and item in allowed
    ))


def _stage_reward_claims(
    value: Any,
    label: str,
    issues: list[str],
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    allowed = set(GROWTH_STAGES[1:])
    return list(dict.fromkeys(
        item for item in value if isinstance(item, str) and item in allowed
    ))


def _optional_iso_date(value: Any, label: str, issues: list[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    if _valid_iso_date(value):
        return str(value)
    issues.append(f"{label}: expected ISO date string or null")
    return None


def _card_effect_batches(
    value: Any,
    *,
    family: str,
    label: str,
    issues: list[str],
    limit: int = MAX_CARD_EFFECT_BATCHES,
) -> list[CardEffectBatch]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    allowed = {
        effect_id
        for effect_id in CARD_EFFECT_SPECS
        if (
            (family == "fertilizer" and effect_id.startswith("fertilizer_"))
            or (family == "booster" and effect_id == "booster_potion")
        )
    }
    bounded_limit = max(0, min(MAX_CARD_EFFECT_BATCHES, int(limit)))
    result: list[CardEffectBatch] = []
    event_keys: set[str] = set()
    for index, raw in enumerate(value):
        if len(result) >= bounded_limit:
            issues.append(f"{label}: limited to {bounded_limit} paid doses")
            break
        if not isinstance(raw, dict):
            continue
        effect_id = raw.get("effect_id")
        if effect_id not in allowed:
            issues.append(f"{label}[{index}].effect_id: unsupported value")
            continue
        expected_growth, default_cards, maximum_cards = CARD_EFFECT_SPECS[str(effect_id)]
        total_cards = _bounded_int(
            raw.get("total_cards"),
            default_cards,
            1,
            maximum_cards,
            f"{label}[{index}].total_cards",
            issues,
        )
        remaining_cards = _bounded_int(
            raw.get("remaining_cards"),
            total_cards,
            0,
            total_cards,
            f"{label}[{index}].remaining_cards",
            issues,
        )
        if remaining_cards <= 0:
            continue
        activated_at = raw.get("activated_at", "")
        if activated_at and not _valid_iso_datetime(activated_at):
            issues.append(f"{label}[{index}].activated_at: expected ISO datetime")
            activated_at = ""
        source_event_key = raw.get("source_event_key", "")
        if not isinstance(source_event_key, str):
            source_event_key = ""
        if source_event_key and source_event_key in event_keys:
            issues.append(f"{label}[{index}]: duplicate source event")
            continue
        if source_event_key:
            event_keys.add(source_event_key)
        raw_growth = raw.get("growth_per_card_units")
        if raw_growth != expected_growth:
            if raw_growth is not None:
                issues.append(
                    f"{label}[{index}].growth_per_card_units: derived from effect"
                )
        result.append(CardEffectBatch(
            effect_id=str(effect_id),
            growth_per_card_units=expected_growth,
            total_cards=total_cards,
            remaining_cards=remaining_cards,
            activated_at=str(activated_at),
            source_event_key=source_event_key,
        ))
    return result


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


def _optional_token(value: Any, label: str, issues: list[str]) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label}: expected string")
        return ""
    return value.strip()


def _unique_event_keys(value: Any, label: str, issues: list[str]) -> list[str]:
    """Validate an intentionally unbounded replay-prevention ledger."""

    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"{label}: expected list")
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str) or not raw or raw in seen:
            if isinstance(raw, str) and raw in seen:
                issues.append(f"{label}: removed duplicate key")
            continue
        seen.add(raw)
        result.append(raw)
    return result


def _answer_lineage_bindings(value: Any, issues: list[str]) -> dict[str, str]:
    """Validate the unbounded revlog-alias to stable-lineage authority."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("answer_lineage_bindings: expected object")
        return {}
    result: dict[str, str] = {}
    for raw_revlog_id, raw_lineage in value.items():
        if (
            not isinstance(raw_revlog_id, str)
            or not raw_revlog_id.isdigit()
            or int(raw_revlog_id) <= 0
            or not isinstance(raw_lineage, str)
        ):
            continue
        parts = raw_lineage.split("|")
        if len(parts) != 4 or parts[0] != "v1" or not _valid_iso_date(parts[1]):
            continue
        try:
            card_id = int(parts[2])
            serial = int(parts[3])
        except ValueError:
            continue
        if card_id <= 0 or serial <= 0:
            continue
        result[raw_revlog_id] = raw_lineage
    return result


def _pending_reanswer_lineages(value: Any, issues: list[str]) -> dict[str, int]:
    """Validate short-lived undo lineage hints used to prevent rerolling."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("pending_reanswer_lineages: expected object")
        return {}
    result: dict[str, int] = {}
    for raw_lineage, raw_floor in value.items():
        if (
            not isinstance(raw_lineage, str)
            or not isinstance(raw_floor, int)
            or isinstance(raw_floor, bool)
            or raw_floor <= 0
        ):
            continue
        parts = raw_lineage.split("|")
        if len(parts) != 4 or parts[0] != "v1" or not _valid_iso_date(parts[1]):
            continue
        try:
            card_id = int(parts[2])
            serial = int(parts[3])
        except ValueError:
            continue
        if card_id > 0 and serial > 0:
            result[raw_lineage] = raw_floor
    return result


def _reward_receipts(value: Any, issues: list[str]) -> list[RewardReceipt]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append("recent_reward_receipts: expected list")
        return []
    result: list[RewardReceipt] = []
    identities: set[tuple[str, str, str, str, str, str]] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        event_key = raw.get("event_key")
        reward_type = raw.get("reward_type")
        source = raw.get("source")
        source_id = raw.get("source_id", "")
        scheduler_day = raw.get("scheduler_day")
        correlation_id = raw.get("correlation_id", "")
        occurred_at = raw.get("occurred_at")
        item_id = raw.get("item_id", "")
        plant_id = raw.get("plant_id", "")
        title = raw.get("title", "")
        description = raw.get("description", "")
        if not all(isinstance(item, str) and item for item in (
            event_key, reward_type, source, scheduler_day, occurred_at,
        )):
            continue
        if not _valid_iso_date(scheduler_day) or not _valid_iso_datetime(occurred_at):
            continue
        optional_strings = (
            source_id,
            correlation_id,
            item_id,
            plant_id,
            title,
            description,
        )
        if not all(isinstance(item, str) for item in optional_strings):
            continue
        amount = _nonnegative_int(
            raw.get("amount"), 0, f"recent_reward_receipts[{index}].amount", issues
        )
        # One atomic event may contain several resource lines. Only collapse an
        # exact duplicate receipt, never every row sharing its event key.
        identity = (
            event_key,
            reward_type,
            source_id,
            item_id,
            plant_id,
            correlation_id,
        )
        if identity in identities:
            issues.append(f"recent_reward_receipts[{index}]: duplicate resource line")
            continue
        identities.add(identity)
        result.append(RewardReceipt(
            event_key=event_key,
            reward_type=reward_type,
            source=source,
            source_id=source_id,
            scheduler_day=scheduler_day,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            amount=amount,
            item_id=item_id,
            plant_id=plant_id,
            title=title,
            description=description,
        ))
    return bounded_reward_receipts(result)


def _day_fingerprints(value: Any, issues: list[str]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("finalized_day_fingerprints: expected object")
        return {}
    result: dict[str, str] = {}
    for raw_day, raw_fingerprint in value.items():
        if _valid_iso_date(raw_day) and isinstance(raw_fingerprint, str) and raw_fingerprint:
            result[str(raw_day)] = raw_fingerprint
    return result


def _garden_find_daily_counts(value: Any, issues: list[str]) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("garden_find_daily_counts: expected object")
        return {}
    result: dict[str, int] = {}
    for raw_day, raw_count in value.items():
        if not _valid_iso_date(raw_day):
            continue
        result[str(raw_day)] = _bounded_int(
            raw_count,
            0,
            0,
            3,
            f"garden_find_daily_counts.{raw_day}",
            issues,
        )
    return result


def _garden_find_reward_daily_counts(
    value: Any,
    issues: list[str],
) -> dict[str, dict[str, int]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("garden_find_reward_daily_counts: expected object")
        return {}
    result: dict[str, dict[str, int]] = {}
    for raw_day, raw_counts in value.items():
        if not _valid_iso_date(raw_day) or not isinstance(raw_counts, dict):
            continue
        counts: dict[str, int] = {}
        for raw_reward_id, raw_count in raw_counts.items():
            if not isinstance(raw_reward_id, str) or not raw_reward_id:
                continue
            counts[raw_reward_id] = _bounded_int(
                raw_count,
                0,
                0,
                3,
                f"garden_find_reward_daily_counts.{raw_day}.{raw_reward_id}",
                issues,
            )
        if counts:
            result[str(raw_day)] = counts
    return result


def _garden_find_outcomes(
    value: Any,
    issues: list[str],
) -> dict[str, GardenFindOutcome]:
    """Validate consumed outcomes without pruning replay-prevention history."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("garden_find_outcomes: expected object")
        return {}
    result: dict[str, GardenFindOutcome] = {}
    for outcome_key, raw in value.items():
        if not isinstance(outcome_key, str) or not outcome_key or not isinstance(raw, dict):
            continue
        scheduler_day = raw.get("scheduler_day")
        status = raw.get("status")
        pool_id = raw.get("pool_id")
        pool_version = raw.get("pool_version")
        occurred_at = raw.get("occurred_at")
        if (
            not _valid_iso_date(scheduler_day)
            or status not in GARDEN_FIND_OUTCOME_STATUSES
            or not isinstance(pool_id, str)
            or not pool_id
            or not isinstance(pool_version, str)
            or not pool_version
            or not _valid_iso_datetime(occurred_at)
        ):
            continue
        stored_answer_key = raw.get("answer_key")
        if not isinstance(stored_answer_key, str) or not stored_answer_key:
            prefix = f"{pool_id}:"
            stored_answer_key = (
                outcome_key[len(prefix):]
                if outcome_key.startswith(prefix)
                else outcome_key
            )
        expected_outcome_key = f"{pool_id}:{stored_answer_key}"
        if outcome_key != expected_outcome_key:
            issues.append(
                f"garden_find_outcomes.{outcome_key}: repaired pool-qualified identity"
            )
        reward_id = raw.get("reward_id", "")
        reward_type = raw.get("reward_type", "")
        item_id = raw.get("item_id", "")
        display_name = raw.get("display_name", "")
        description = raw.get("description", "")
        tier = raw.get("tier", "")
        artwork_ref = raw.get("artwork_ref", "")
        localization_key = raw.get("localization_key", "")
        if not all(isinstance(item, str) for item in (
            reward_id,
            reward_type,
            item_id,
            display_name,
            description,
            tier,
            artwork_ref,
            localization_key,
        )):
            continue
        amount = _nonnegative_int(
            raw.get("amount"),
            0,
            f"garden_find_outcomes.{outcome_key}.amount",
            issues,
        )
        if status == "hit" and (not reward_id or not reward_type):
            issues.append(f"garden_find_outcomes.{outcome_key}: hit missing reward")
            continue
        if status != "hit":
            reward_id = ""
            reward_type = ""
            item_id = ""
            amount = 0
        result[expected_outcome_key] = GardenFindOutcome(
            answer_key=stored_answer_key,
            scheduler_day=str(scheduler_day),
            status=str(status),
            pool_id=pool_id,
            pool_version=str(pool_version),
            occurred_at=str(occurred_at),
            reward_id=reward_id,
            reward_type=reward_type,
            amount=amount,
            item_id=item_id,
            display_name=display_name,
            description=description,
            tier=tier,
            artwork_ref=artwork_ref,
            localization_key=localization_key,
        )
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
        transaction_type = raw.get("transaction_type", "legacy")
        source = raw.get("source", "legacy")
        source_id = raw.get("source_id", "")
        scheduler_day = raw.get("scheduler_day", "")
        correlation_id = raw.get("correlation_id", "")
        if not isinstance(transaction_type, str) or not transaction_type:
            transaction_type = "legacy"
        if not isinstance(source, str) or not source:
            source = "legacy"
        if not isinstance(source_id, str):
            source_id = ""
        if scheduler_day and not _valid_iso_date(scheduler_day):
            issues.append(f"currency_transactions[{index}].scheduler_day: expected ISO date")
            scheduler_day = ""
        if not isinstance(scheduler_day, str):
            scheduler_day = ""
        if not isinstance(correlation_id, str):
            correlation_id = ""
        result.append(CurrencyTransaction(
            tx_id,
            event_key,
            reason,
            delta,
            resulting,
            occurred,
            transaction_type,
            source,
            source_id,
            scheduler_day,
            correlation_id,
        ))
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
                item.transaction_type,
                item.source,
                item.source_id,
                item.scheduler_day,
                item.correlation_id,
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
        correlation_id = (
            raw.get("correlation_id")
            if isinstance(raw.get("correlation_id"), str)
            else ""
        )
        ids.add(event_id)
        result.append(FeedbackEvent(
            event_id, kind, message, occurred, plant_id,
            title, asset_category, asset_key, amount, correlation_id,
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
        "fertilizer_basic": 0,
        "fertilizer_quality": 0,
        "fertilizer_premium": 0,
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


def _environment_completion_counts(
    value: Any,
    issues: list[str],
) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        issues.append("environment_completion_counts: expected object")
        return {}
    return {
        str(item_id): _nonnegative_int(
            count,
            0,
            f"environment_completion_counts.{item_id}",
            issues,
        )
        for item_id, count in value.items()
        if isinstance(item_id, str) and item_id in SCENERY_CATALOG
    }


def _environment_visibility(value: Any, issues: list[str]) -> dict[str, bool]:
    result = {"garden_feature": True, "scenery": True}
    if value is None:
        return result
    if not isinstance(value, dict):
        issues.append("environment_visibility: expected object")
        return result
    for key in result:
        raw = value.get(
            key,
            value.get("weather", True) if key == "garden_feature" else True,
        )
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
    feature = canonical_garden_feature_id(_string(
        value.get("garden_feature_id", value.get("weather_id")),
        DEFAULT_GARDEN_FEATURE_ID,
        "loadout.garden_feature_id",
        issues,
    ))
    scenery = _string(
        value.get("scenery_id"), DEFAULT_SCENERY_ID, "loadout.scenery_id", issues
    )
    if feature not in GARDEN_FEATURE_CATALOG:
        issues.append(f"loadout.garden_feature_id: unexpected value {feature!r}")
        feature = DEFAULT_GARDEN_FEATURE_ID
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
        garden_feature_id=feature,
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
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        day_value = _iso_date(raw.get("day"), "", f"active_plant_periods[{index}].day", issues)
        plant_id = raw.get("plant_id")
        if plant_id is not None and plant_id not in plant_ids:
            plant_id = None
        started = _nonnegative_int(raw.get("started_at_ms"), 0, f"active_plant_periods[{index}].started_at_ms", issues)
        if day_value:
            result.append(ActivePlantPeriod(day_value, plant_id, started))
    ordered = sorted(result, key=lambda period: (period.started_at_ms, period.day))
    coalesced: list[ActivePlantPeriod] = []
    for period in ordered:
        if coalesced and coalesced[-1].plant_id == period.plant_id:
            continue
        coalesced.append(period)
    return coalesced


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
        unlocked = raw.get("unlocked", False)
        if not isinstance(unlocked, bool):
            issues.append(f"achievements.{key}.unlocked: expected bool")
            unlocked = False
        unlocked_at = raw.get("unlocked_at")
        if unlocked_at is not None and not _valid_iso_datetime(unlocked_at):
            issues.append(f"achievements.{key}.unlocked_at: expected ISO datetime")
            unlocked_at = None
        rewarded_at = raw.get("rewarded_at")
        if rewarded_at is not None and not _valid_iso_datetime(rewarded_at):
            issues.append(f"achievements.{key}.rewarded_at: expected ISO datetime")
            rewarded_at = None
        category = raw.get("category", "")
        requirement = raw.get("requirement", "")
        reward_summary = raw.get("reward_summary", "")
        reward_event_key = raw.get("reward_event_key", "")
        historical_backfill = raw.get("historical_backfill", False)
        result[key] = Achievement(
            key,
            name,
            description,
            unlocked,
            _number(
                raw.get("progress"),
                0.0,
                0.0,
                1.0,
                f"achievements.{key}.progress",
                issues,
            ),
            unlocked_at,
            category if isinstance(category, str) else "",
            requirement if isinstance(requirement, str) else "",
            reward_summary if isinstance(reward_summary, str) else "",
            rewarded_at,
            reward_event_key if isinstance(reward_event_key, str) else "",
            historical_backfill if isinstance(historical_backfill, bool) else False,
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
        normalized_key = (
            "scenery" if key == "backgrounds"
            else "garden_features" if key == "weather"
            else str(key)
        )
        if isinstance(raw, list):
            parsed = list(dict.fromkeys(
                item for item in raw if isinstance(item, str) and item
            ))
            if normalized_key in {"scenery", "garden_features"}:
                if normalized_key == "garden_features":
                    parsed = [canonical_garden_feature_id(item) for item in parsed]
                result[normalized_key] = list(dict.fromkeys([
                    *result.get(normalized_key, []),
                    *parsed,
                ]))
            else:
                # Preserve extension-owned and historical inventory lists even
                # when the current Collection has no renderer for them.
                result[normalized_key] = parsed
        else:
            issues.append(f"inventory.{key}: expected list")
    return InventoryState(result)


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
