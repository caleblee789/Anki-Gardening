from __future__ import annotations

from .presentation import PlantIdentity, plant_species_name, plant_stage_event, plant_stage_title

import json
import hashlib
import logging
import math
import random
import time
import uuid
from bisect import bisect_left, insort
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from .performance import timed

from . import build_capabilities
from .feature_availability import growth_target_enabled, landmarks_enabled, mastery_enabled
from .asset_manager import AssetManager, ResolvedAsset
from .balance_catalog import (
    ALL_DUE_BASE_COINS as CATALOG_ALL_DUE_BASE_COINS,
    BASE_GROWTH_PER_REVIEW as CATALOG_BASE_GROWTH_PER_REVIEW,
    BOOSTER_CARD_COUNT as CATALOG_BOOSTER_CARD_COUNT,
    BOOSTER_GROWTH_PER_ANSWER as CATALOG_BOOSTER_GROWTH_PER_ANSWER,
    CONSUMABLES as BALANCE_CONSUMABLES,
    COSMETIC_BY_ID,
    DAILY_ACTIVITY_COINS as CATALOG_DAILY_ACTIVITY_COINS,
    EFFECT_DOSE_CAP as CATALOG_EFFECT_DOSE_CAP,
    SHARED_GROWTH_DENOMINATOR as CATALOG_SHARED_GROWTH_DENOMINATOR,
    SPECIES as BALANCE_SPECIES,
    STAGES as BALANCE_STAGES,
    ConsumableKind as BalanceConsumableKind,
    StageId as BalanceStageId,
)
from .plant_beds import species_progress_counts
from .achievements import milestone_unlocked_text
from .economy_progression import (
    LANDMARK_BY_ID,
    LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS,
    LANDMARK_GROWTH_COST_UNITS,
    LANDMARK_ORDER,
    MASTERY_RANK_BY_ID,
    MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS,
    MASTERY_GROWTH_COST_UNITS,
    ContributionMode,
    GrowthProjectAction,
    GrowthProjectConfirmation,
    GrowthProjectOutcome,
    GrowthProjectQuote,
    GrowthProjectRequest,
    GrowthProjectsSnapshot,
    GrowthTargetRef,
    GrowthTargetType,
    LandmarkAction,
    LandmarkOutcome,
    LandmarkProjectSnapshot,
    LandmarkQuote,
    LandmarkRequest,
    MasteryOutcome,
    MasteryQuote,
    MasteryRequest,
    MasterySnapshot,
    ProgressionDisposition,
    build_growth_projects_snapshot,
    growth_project_outcome_from_dict,
    landmark_snapshot,
    mastery_snapshot,
    next_landmark_id,
    next_mastery_rank_id,
    project_landmark_request,
    project_mastery_request,
    project_growth_project_request,
    quote_landmark_request,
    quote_mastery_request,
    quote_growth_project_request,
)
from .environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    ENVIRONMENT_CATALOG,
    GARDEN_FEATURE_CATALOG,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    catalog_items,
    environment_item,
    canonical_garden_feature_id,
)
from .garden_features import FEATURE_EFFECT_KEYS
from .achievements import (
    ACHIEVEMENT_DEFINITIONS,
    ACHIEVEMENTS_BY_ID,
    AchievementProgressValues,
    HistoricalReview,
    RewardBundle,
    STREAK_ACHIEVEMENTS,
    streak_growth_progress,
    achievement_progress_value,
    analyze_history,
)
from .garden_finds import (
    GARDEN_FIND_RECEIPT_SOURCES,
    STANDARD_FIND_RECEIPT_SOURCES,
    ENVIRONMENT_POOL_ID,
    ENVIRONMENT_POOL_VERSION,
    ENVIRONMENT_TIER_DENOMINATORS,
    KNOWN_ARTWORK_REFS,
    STANDARD_POOL_ID,
    STANDARD_POOL_VERSION,
    STANDARD_DROUGHT_SCHEDULE,
    GardenFindReward,
    consumption_id,
    prepare_reward_registry,
    resolve_environment_find,
    resolve_environment_completion_pity,
    resolve_standard_find,
    stable_answer_event_identity,
    standard_find_status,
    standard_daily_cap,
    ultra_denominator,
)
from .growth import (
    CompletedGrowthChargeRequest,
    GROWTH_UNITS_PER_POINT,
    GrowthAllocation,
    GrowthGrantResult,
    ProjectGrowthAllocation,
    GrowthChargeOutcome,
    GrowthChargeQuote,
    GrowthChargeRequest,
    GrowthChargeStatus,
    GrowthChargeTargetState,
    project_growth_charge_application,
    stage_progress,
    StageRewardProjection,
)
from .models.state import (
    Achievement,
    ActivePlantPeriod,
    CardEffectBatch,
    GardenCardEffects,
    CurrencyTransaction,
    DailyEconomySnapshot,
    DailyCompletionState,
    DailyLoadoutSchedule,
    DailyStats,
    FeedbackEvent,
    GardenFindOutcome,
    Fertilizer,
    Booster,
    GardenState,
    GARDEN_LEGACY_LEVEL_COST_UNITS,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    LANDMARK_MAX_GROWTH_UNITS,
    MASTERY_MAX_GROWTH_UNITS_PER_SPECIES,
    CURRENT_CATALOG_SPECIES_ORDER,
    MAX_COMPLETED_PURCHASE_REQUESTS,
    MAX_COMPLETED_GROWTH_CHARGE_REQUESTS,
    MAX_CARD_EFFECT_BATCHES,
    MAX_GARDEN_SLOTS,
    MAX_GARDEN_NAME_LENGTH,
    MAX_PLANT_NAME_LENGTH,
    MAX_PROCESSED_REVLOG_IDS,
    MAX_REWARD_RECEIPTS,
    OnboardingProgress,
    OnboardingStep,
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
    PlantMemory,
    RewardReceipt,
    STATE_VERSION,
    bounded_reward_receipts,
    utc_now_iso,
)
from .models.welcome import (
    WELCOME_COINS, WELCOME_EVENT_KEY, WELCOME_GROWTH,
    WelcomeReceipt, WelcomeReward,
)
from .reward_ledger import (
    DailyEconomySnapshotRecord,
    EconomyEventRecord,
    IdempotencyRecord,
)
from .models.sync_reward import SyncRewardSummary
from .balance_catalog import KNOWN_COSMETIC_IDS, TROPHY_BY_ACHIEVEMENT
from .trophies import trophy_effects, initialize_trophy_activations
from .purchases import (
    CompletedPurchaseRequest,
    EffectDescriptor,
    FertilizerStoredItemDisposition,
    FertilizerStoredItemProjection,
    PurchaseDisposition,
    PurchaseKind,
    PurchaseOutcome,
    PurchaseProjection,
    PurchaseQuote,
    PurchaseRequest,
    PurchaseStatus,
    purchase_projection as build_purchase_projection,
    purchase_presentation,
    fertilizer_stored_item_projection as build_fertilizer_stored_item_projection,
)
from .storage import DueObligationStatus, RevlogReadError, SchedulerBoundaryError


logger = logging.getLogger(__name__)


def _garden_coin_amount(value: int, *, signed: bool = False) -> str:
    """Format formal reward and balance copy with correct plurality."""

    amount = max(0, int(value))
    prefix = "+" if signed else ""
    unit = "Garden Coin" if amount == 1 else "Garden Coins"
    return f"{prefix}{amount:,} {unit}"


class _StateSnapshot(dict[str, Any]):
    """Bounded state copy paired with its staged-ledger rollback point."""

    def __init__(self, payload: Mapping[str, Any], ledger_checkpoint: Any = None) -> None:
        super().__init__(payload)
        self.ledger_checkpoint = ledger_checkpoint


def difficulty_from_factor(value: Any) -> float:
    """Retained for revlog compatibility; difficulty no longer changes Growth."""
    try:
        factor = int(value)
    except (TypeError, ValueError):
        factor = 2500
    if factor <= 0:
        factor = 2500
    return max(0.1, min(1.0, (3000 - factor) / 2000))


def queue_and_lapse_from_revlog_type(qtype: object, ease: object) -> tuple[int, int] | None:
    """Map answer revlog rows to stable queue semantics."""
    try:
        review_type = int(qtype)
        rating = int(ease)
    except (TypeError, ValueError):
        return None
    if review_type not in (0, 1, 2, 3):
        return None
    queue = 1 if review_type in (0, 2) else 2
    lapse_count = 1 if review_type == 2 or rating == 1 else 0
    return queue, lapse_count


@dataclass(frozen=True)
class StageTransition:
    plant_id: str
    species: str
    previous_stage: str
    new_stage: str
    plant_name: str = ""
    source: str = "nurtured"

    def to_dict(self) -> dict[str, str]:
        return {
            "plant_id": self.plant_id,
            "species": self.species,
            "previous_stage": self.previous_stage,
            "new_stage": self.new_stage,
            "plant_name": self.plant_name,
            "source": self.source,
            # Renderer-neutral compatibility names.  Reviewer surfaces may
            # consume either spelling, but the engine remains the authority.
            "transition_source": self.source,
            "stage_transition_source": self.source,
        }


@dataclass(frozen=True)
class DecorationResult:
    """Committed mechanical facts for one Garden Decoration event."""

    active_bonus_id: str = DEFAULT_GARDEN_FEATURE_ID
    progress_before: int = 0
    progress_after: int = 0
    trigger_reached: bool = False
    decoration_growth_awarded_units: int = 0
    direct_growth_awarded_units: int = 0
    coins_awarded: int = 0
    prism_growth_banked_units: int = 0
    prism_growth_released_units: int = 0
    booster_cards_added: int = 0


@dataclass(frozen=True)
class BoosterResult:
    base_cards_added: int = 0
    total_cards_added: int = 0
    remaining_booster_cards: int = 0
    target_id: str = ""
    destination_kind: str = "plant"


@dataclass(frozen=True)
class ConsumableUseProjection:
    target_id: str
    target_name: str
    destination_kind: str
    can_use: bool
    message: str
    cards_added: int = 0
    remaining_cards: int = 0
    doses: int = 0
    queued_item_doses: int = 0
    active_item_id: str = ""


@dataclass(frozen=True)
class CompletionResult:
    base_coins: int = 0
    harvest_bell_coins: int = 0
    trophy_coins: int = 0
    prism_growth_released_units: int = 0
    prism_growth_destination: str = ""
    prism_growth_destination_kind: str = ""
    prism_growth_destination_id: str = ""
    prism_project_allocations: tuple[ProjectGrowthAllocation, ...] = ()


@dataclass(frozen=True)
class ReviewAward:
    plant_id: Optional[str]
    base_growth: int
    streak_bonus_growth: int
    fertilizer_growth: int
    bonus_percent: int
    paused_reason: str = ""
    booster_growth: int = 0
    weather_growth: int = 0
    scenery_growth: int = 0
    trophy_growth: int = 0
    shared_growth_numerator: int = 1
    shared_growth_denominator: int = 10
    allocations: tuple[GrowthAllocation, ...] = ()
    correlation_id: str = field(default="", compare=False)
    reward_event_keys: tuple[str, ...] = field(default=(), compare=False)
    garden_find_ids: tuple[str, ...] = field(default=(), compare=False)
    achievement_ids: tuple[str, ...] = field(default=(), compare=False)
    base_growth_units: int = field(default=0, compare=False)
    streak_growth_units: int = field(default=0, compare=False)
    fertilizer_growth_units: int = field(default=0, compare=False)
    booster_growth_units: int = field(default=0, compare=False)
    weather_growth_units: int = field(default=0, compare=False)
    scenery_growth_units: int = field(default=0, compare=False)
    trophy_growth_units: int = field(default=0, compare=False)
    applied_growth_units: int = field(default=0, compare=False)
    redirected_growth_units: int = field(default=0, compare=False)
    shared_growth_units: int = field(default=0, compare=False)
    stored_growth_units: int = field(default=0, compare=False)
    landmark_growth_units: int = field(default=0, compare=False)
    mastery_growth_units: int = field(default=0, compare=False)
    legacy_growth_units: int = field(default=0, compare=False)
    project_allocations: tuple[ProjectGrowthAllocation, ...] = field(
        default=(), compare=False
    )
    decoration_result: DecorationResult = field(
        default_factory=DecorationResult,
        compare=False,
    )

    @property
    def bonus_growth(self) -> int:
        return (
            self.streak_bonus_growth
            + self.fertilizer_growth
            + self.booster_growth
            + self.weather_growth
            + self.scenery_growth
            + self.trophy_growth
        )

    @property
    def total_growth(self) -> int:
        return self.base_growth + self.bonus_growth

    @property
    def total_growth_units(self) -> int:
        explicit = sum((
            max(0, int(self.base_growth_units)),
            max(0, int(self.streak_growth_units)),
            max(0, int(self.fertilizer_growth_units)),
            max(0, int(self.booster_growth_units)),
            max(0, int(self.weather_growth_units)),
            max(0, int(self.scenery_growth_units)),
            max(0, int(self.trophy_growth_units)),
        ))
        return explicit or max(0, int(self.total_growth)) * GROWTH_UNITS_PER_POINT

    @property
    def total_growth_value(self) -> float:
        return self.total_growth_units / GROWTH_UNITS_PER_POINT

    @property
    def total_garden_growth(self) -> int:
        return sum(allocation.credited_growth for allocation in self.allocations)


@dataclass(frozen=True)
class CommittedPlantSnapshot:
    """Immutable plant facts bracketing one committed reviewer answer."""

    plant_id: str
    name: str
    species: str
    stage: str
    growth_units: int
    slot_index: int | None
    fully_grown: bool


@dataclass(frozen=True)
class CommittedAnswerResult:
    """Engine-owned facts emitted only after one answer transaction commits.

    Presentation code may reshape these facts, but must never infer rewards by
    diffing the mutable Garden state after this result has been returned.
    """

    event_id: str
    correlation_id: str
    scheduler_day: str
    occurred_at_ms: int
    origin: str
    award: ReviewAward
    cards_completed: int = 1
    reward_receipts: tuple[RewardReceipt, ...] = ()
    currency_transactions: tuple[CurrencyTransaction, ...] = ()
    garden_find_outcomes: tuple[GardenFindOutcome, ...] = ()
    standard_find_count: int = 0
    stage_transitions: tuple[StageTransition, ...] = ()
    plants_before: tuple[CommittedPlantSnapshot, ...] = ()
    plants_after: tuple[CommittedPlantSnapshot, ...] = ()
    stored_growth_before_units: int = 0
    stored_growth_after_units: int = 0
    landmark_growth_before_units: int = 0
    landmark_growth_after_units: int = 0
    mastery_growth_before_units: int = 0
    mastery_growth_after_units: int = 0
    legacy_growth_before_units: int = 0
    legacy_growth_after_units: int = 0
    project_allocations: tuple[ProjectGrowthAllocation, ...] = ()
    active_plant_before_id: str = ""
    active_plant_after_id: str = ""

    @property
    def stored_growth_delta_units(self) -> int:
        return (
            int(self.stored_growth_after_units)
            - int(self.stored_growth_before_units)
        )

    @property
    def landmark_growth_delta_units(self) -> int:
        return (
            int(self.landmark_growth_after_units)
            - int(self.landmark_growth_before_units)
        )

    @property
    def mastery_growth_delta_units(self) -> int:
        return (
            int(self.mastery_growth_after_units)
            - int(self.mastery_growth_before_units)
        )

    @property
    def legacy_growth_delta_units(self) -> int:
        return (
            int(self.legacy_growth_after_units)
            - int(self.legacy_growth_before_units)
        )

    @property
    def daily_completion_rewarded(self) -> bool:
        return any(
            receipt.source in {"all_due", "todays_cards"}
            for receipt in self.reward_receipts
        )


def _project_allocation_metric_deltas(
    allocations: Iterable[ProjectGrowthAllocation],
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize exact per-target project credits into the economy event."""

    result = dict(existing or {})
    project_allocations: dict[str, int] = {}
    for allocation in allocations:
        units = max(0, int(allocation.units))
        if not units:
            continue
        target_key = (
            f"{allocation.target_type.value}:{allocation.target_id}"
        )
        project_allocations[target_key] = (
            project_allocations.get(target_key, 0) + units
        )
    if project_allocations:
        result["project_allocations"] = project_allocations
    return result


@dataclass(frozen=True)
class PlacementChange:
    before: dict[str, int]
    after: dict[str, int]

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"before": dict(self.before), "after": dict(self.after)}


@dataclass(frozen=True)
class StarterPlacementChange:
    """Opaque receipt for one atomic first-run placement transaction."""

    plant_id: str
    _before: _StateSnapshot = field(repr=False, compare=False)
    _after: dict[str, Any] = field(repr=False, compare=False)


@dataclass
class PlacementDraft:
    selected_plant_id: str
    original: dict[str, int]
    current: dict[str, int]
    history: list[dict[str, int]]

    def scene_slots(self) -> dict[str, int]:
        return dict(self.current)


@dataclass(frozen=True)
class FertilizerSpec:
    tier: str
    name: str
    growth_per_answer: int
    card_count: int
    price: int


RUNTIME_WAIT_MESSAGE = "Garden is updating. Try this change again shortly."


def _requires_ready_runtime(*empty_results: Any):
    """Keep mutation results explicit while verified progress catches up."""
    def decorate(method):
        @wraps(method)
        def checked(self, *args, **kwargs):
            runtime = getattr(self.storage, "runtime_coordinator", None)
            if runtime is not None and not getattr(self.storage, "_allow_runtime_commit", False):
                runtime.request("Garden action")
            if getattr(self.storage, "runtime_pending", False) and not getattr(self.storage, "_allow_runtime_commit", False):
                return (False, RUNTIME_WAIT_MESSAGE, *empty_results)
            return method(self, *args, **kwargs)
        return checked
    return decorate


class GardenGameEngine:
    BASE_GROWTH_PER_REVIEW = CATALOG_BASE_GROWTH_PER_REVIEW
    PASSIVE_GROWTH_DENOMINATOR = CATALOG_SHARED_GROWTH_DENOMINATOR
    STREAK_MEMORY_MILESTONES = (3, 7, 14, 30, 60, 100, 365)
    STAGE_REWARD_SPLITS = {
        (
            "rare"
            if stage.stage_id is BalanceStageId.FULL_BLOOM
            else str(stage.stage_id)
        ): tuple(stage.checkpoint_coin_rewards)
        for stage in BALANCE_STAGES
        if stage.checkpoint_coin_rewards
    }
    STAGE_CURRENCY = {
        (
            "rare"
            if stage.stage_id is BalanceStageId.FULL_BLOOM
            else str(stage.stage_id)
        ): sum(stage.checkpoint_coin_rewards)
        for stage in BALANCE_STAGES
        if stage.checkpoint_coin_rewards
    }
    BOOSTER_GROWTH_PER_ANSWER = CATALOG_BOOSTER_GROWTH_PER_ANSWER
    BOOSTER_DURATION_SECONDS = 2 * 60 * 60
    BOOSTER_CARD_COUNT = CATALOG_BOOSTER_CARD_COUNT
    EFFECT_DOSE_CAP = CATALOG_EFFECT_DOSE_CAP
    ALL_DUE_BASE_COINS = CATALOG_ALL_DUE_BASE_COINS
    DAILY_ACTIVITY_COINS = CATALOG_DAILY_ACTIVITY_COINS
    CLOUDY_ALL_DUE_BONUS_COINS = 5
    RAINBOW_ALL_DUE_GROWTH = 100
    DIRECT_SOIL_SLOTS = frozenset(range(MAX_GARDEN_SLOTS))
    V6_SLOT_CENTERS = (
        (0.393, 0.45172), (0.611, 0.45172), (0.320, 0.60868),
        (0.538, 0.60868), (0.464, 0.78884), (0.682, 0.78884),
    )
    V4_SLOT_CENTERS = (
        (0.190, 0.526), (0.498, 0.526), (0.769, 0.526),
        (0.185, 0.765), (0.502, 0.835), (0.835, 0.765),
    )
    SOIL_PLANT_MESSAGE = "Choose an empty bed."
    SOIL_CAPACITY_MESSAGE = "Unlock or empty a bed first."
    SPECIES_PRICES = {
        str(species.species_id): int(species.purchase_price_coins or 0)
        for species in BALANCE_SPECIES
    }
    FERTILIZERS = {
        str(item.consumable_id).removeprefix("fertilizer_"): FertilizerSpec(
            str(item.consumable_id).removeprefix("fertilizer_"),
            item.display_name,
            item.growth_per_card,
            item.card_count,
            int(item.price_coins or 0),
        )
        for item in BALANCE_CONSUMABLES
        if item.kind is BalanceConsumableKind.FERTILIZER
    }
    SPECIES_PERSONALITY = {
        "bonsai": "streak",
        "rose": "accuracy",
        "sunflower": "morning",
        "lavender": "balanced",
        "hydrangea": "cumulative",
        "peony": "accuracy",
        "foxglove": "difficult",
        "japanese_maple": "recovery",
        "wisteria": "streak",
        "dahlia": "volume",
    }
    SPECIES_NAMES = {
        "bonsai": ("Moss", "Juniper", "Sage"),
        "rose": ("Briar", "Rosie", "Petal"),
        "sunflower": ("Sunny", "Sol", "Dawn"),
        "lavender": ("Violet", "Mauve", "Lav"),
        "hydrangea": ("Misty", "Azure", "Dew"),
        "peony": ("Pearl", "Paeonia", "Blush"),
        "foxglove": ("Bell", "Fable", "Thimble"),
        "japanese_maple": ("Momiji", "Acer", "Ember"),
        "wisteria": ("Wisp", "Cascade", "Amethyst"),
        "dahlia": ("Della", "Jewel", "Velvet"),
    }

    def __init__(self, config: Any, storage: Any) -> None:
        self.config = config
        self.storage = storage
        self.state: GardenState = storage.state
        self._pending_reward_activation_ms: int | None = None
        self._pending_stage_transitions: list[StageTransition] = []
        self._current_correlation_id = ""
        self._reward_equipment: tuple[str, str] | None = None
        self.last_booster_result = BoosterResult()
        self.last_completion_result = CompletionResult()
        self.last_fertilizer_stored_item_result: (
            FertilizerStoredItemProjection | None
        ) = None
        try:
            manifest_payload = json.loads(
                (self.storage.addon_dir / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self._addon_version = str(
                manifest_payload.get("human_version") or "0"
            )
        except Exception:
            self._addon_version = "0"
        self.garden_find_registry = prepare_reward_registry(
            known_artwork_refs=KNOWN_ARTWORK_REFS
        )
        self.assets = AssetManager(config, storage)
        geometry_version, allowed_types = self._scene_surface_contract()
        self._scene_geometry_version = geometry_version
        self._surface_allowed_base_types = allowed_types
        if not getattr(storage, "runtime_pending", False):
            self.initialize_runtime_state()
        else:
            self._pending_reward_activation_ms = self._now_ms()

    def initialize_runtime_state(self) -> None:
        """Run bounded repairs after the startup authority audit has finished."""
        snapshot = self._state_snapshot()
        self._repair_environment_state()
        geometry_version = self._scene_geometry_version
        self.state.processed_revlog_ids = sorted({
            value
            for value in self.state.processed_revlog_ids
            if isinstance(value, int)
            and not isinstance(value, bool)
            and value > self.state.processed_revlog_floor
        })[-MAX_PROCESSED_REVLOG_IDS:]
        if geometry_version >= 5 and self.state.scene_geometry_version < geometry_version:
            self._migrate_scene_geometry(geometry_version)
        self._repair_surface_placements()
        self._ensure_achievements()
        initialize_trophy_activations(self.state, self._now_ms())
        self._repair_active_plant()
        self.state.collect_completed_card_effects()
        if (
            self.state.reward_state_initialized
            and self.state.progression_activation_ms <= 0
        ):
            self._activate_progression_if_ready(self._now_ms())
        try:
            self.rollover_if_needed(persist=False)
        except (RevlogReadError, SchedulerBoundaryError):
            # Add-ons can be imported before Anki has finished attaching the
            # collection scheduler. Preserve the saved scheduler day and let
            # the app's maintenance boundary retry after collection startup.
            pass
        if self.state.to_dict() != snapshot:
            self._persist_or_restore(snapshot)

    def _state_snapshot(self) -> _StateSnapshot:
        checkpoint_resolver = getattr(
            self.storage, "reward_ledger_checkpoint", None
        )
        checkpoint = (
            checkpoint_resolver() if callable(checkpoint_resolver) else None
        )
        # to_dict() already detaches every mutable value for rollback.
        return _StateSnapshot(self.state.to_dict(), checkpoint)

    def _restore_state(self, snapshot: dict[str, Any]) -> None:
        rollback = getattr(self.storage, "rollback_reward_ledger", None)
        checkpoint = getattr(snapshot, "ledger_checkpoint", None)
        if callable(rollback) and checkpoint is not None:
            rollback(checkpoint)
        restored = GardenState.from_dict(snapshot)
        self.state.__dict__.clear()
        self.state.__dict__.update(restored.__dict__)
        self.storage.state = self.state

    def _persist_or_restore(self, snapshot: dict[str, Any]) -> None:
        try:
            self.storage.save()
            if self.state.reward_state_initialized:
                self._pending_reward_activation_ms = None
        except Exception:
            self._restore_state(snapshot)
            raise

    def _repair_environment_state(self) -> None:
        """Normalize the canonical loadout without revoking entitlements."""

        inventory = self.state.inventory if isinstance(self.state.inventory, dict) else {}
        feature_owned = list(dict.fromkeys([
            DEFAULT_GARDEN_FEATURE_ID,
            *(
                inventory.get("garden_features", [])
                if isinstance(inventory.get("garden_features"), list)
                else []
            ),
        ]))
        scenery_owned = list(dict.fromkeys([
            DEFAULT_SCENERY_ID,
            *(
                inventory.get("scenery", [])
                if isinstance(inventory.get("scenery"), list)
                else []
            ),
        ]))
        cosmetic_owned = [
            item_id
            for item_id in inventory.get("cosmetics", [])
            if item_id in KNOWN_COSMETIC_IDS
        ] if isinstance(inventory.get("cosmetics", []), list) else []
        inventory.pop("weather", None)
        inventory["garden_features"] = [
            canonical_garden_feature_id(item_id)
            for item_id in feature_owned
            if canonical_garden_feature_id(item_id) in GARDEN_FEATURE_CATALOG
        ]
        valid_scenery = [
            item_id for item_id in scenery_owned if item_id in SCENERY_CATALOG
        ]
        inventory.pop("backgrounds", None)
        inventory["scenery"] = list(valid_scenery)
        inventory["cosmetics"] = list(dict.fromkeys(cosmetic_owned))
        self.state.inventory = inventory
        if (
            self.state.loadout.active_garden_bonus_id
            not in GARDEN_FEATURE_CATALOG
            or self.state.loadout.active_garden_bonus_id
            not in inventory["garden_features"]
        ):
            self.state.loadout.active_garden_bonus_id = (
                DEFAULT_GARDEN_FEATURE_ID
            )
        if (
            (
                self.state.loadout.display_decoration_id
                not in GARDEN_FEATURE_CATALOG
                or self.state.loadout.display_decoration_id
                not in inventory["garden_features"]
            )
        ):
            self.state.loadout.display_decoration_id = (
                DEFAULT_GARDEN_FEATURE_ID
            )
        if (
            self.state.loadout.display_scenery_id not in SCENERY_CATALOG
            or self.state.loadout.display_scenery_id not in inventory["scenery"]
        ):
            self.state.loadout.display_scenery_id = DEFAULT_SCENERY_ID
        if (
            self.state.loadout.active_scenery_effect_id not in SCENERY_CATALOG
            or self.state.loadout.active_scenery_effect_id
            not in inventory["scenery"]
        ):
            self.state.loadout.active_scenery_effect_id = DEFAULT_SCENERY_ID
        visibility = (
            self.state.environment_visibility
            if isinstance(self.state.environment_visibility, dict)
            else {}
        )
        self.state.environment_visibility = {
            "garden_feature": visibility.get(
                "garden_feature", visibility.get("weather", True)
            )
            if isinstance(
                visibility.get("garden_feature", visibility.get("weather", True)),
                bool,
            )
            else True,
            "scenery": visibility.get("scenery", True)
            if isinstance(visibility.get("scenery", True), bool)
            else True,
        }
        if not isinstance(self.state.daily_environment_claims, dict):
            self.state.daily_environment_claims = {}
        for item_id in (
            "booster_potion",
            "fertilizer_basic",
            "fertilizer_quality",
            "fertilizer_premium",
            *GROWTH_CHARGES,
        ):
            value = self.state.consumables.get(item_id, 0)
            self.state.consumables[item_id] = (
                max(0, int(value))
                if isinstance(value, int) and not isinstance(value, bool)
                else 0
            )

    def _scene_surface_contract(self) -> tuple[int, tuple[tuple[str, ...], ...]]:
        """Resolve compatibility from the selected painted background profile."""
        try:
            background = self.resolve_background_asset()
            profile = background.placement.surface_profile if background is not None else None
        except Exception:
            profile = None
        if profile is None:
            fallback = tuple(("direct_soil",) for _slot in range(MAX_GARDEN_SLOTS))
            return 0, fallback
        variant = profile.variants.get("4:3", {})
        raw_surfaces = variant.get("surfaces", []) if isinstance(variant, dict) else []
        allowed: list[tuple[str, ...]] = []
        for surface in raw_surfaces:
            raw_allowed = surface.get("allowed_base_types", []) if isinstance(surface, dict) else []
            values = tuple(
                value for value in raw_allowed
                if value in {"pot", "dirt_mound", "direct_soil"}
            ) if isinstance(raw_allowed, list) else ()
            allowed.append(values or ("direct_soil",))
        if len(allowed) != MAX_GARDEN_SLOTS:
            allowed = [("direct_soil",) for _slot in range(MAX_GARDEN_SLOTS)]
        return profile.geometry_version, tuple(allowed)

    def _migrate_scene_geometry(self, geometry_version: int) -> None:
        """Refresh visual placements once without touching plant progression."""
        old_slots = {plant.plant_id: plant.slot_index for plant in self.state.plants}
        requested_active_id = self.state.active_plant_id
        referenced_plant = next((
            plant for plant in self.state.plants
            if plant.plant_id == requested_active_id
        ), None)
        active = next((
            plant for plant in self.state.plants
            if plant.plant_id == requested_active_id
            and plant.planted
            and not plant.fully_grown
        ), None)
        invalid_reference = bool(
            getattr(self.state, "_active_plant_reference_invalid", False)
        ) or (requested_active_id is not None and referenced_plant is None)
        if active is None and invalid_reference:
            active = self._deterministic_active_candidate()
            self.state.active_plant_id = active.plant_id if active is not None else None
            if active is not None:
                self._record_active_period(active.plant_id)
            self.state._active_plant_reference_invalid = False
        elif active is None:
            # An explicit null (including the normal post-Rare state) is a
            # deliberate pause. Geometry migration must never choose for the
            # learner merely because another unfinished plant exists.
            self.state.active_plant_id = None
        for plant in self.state.plants:
            plant.slot_index = None
        if active is not None:
            old_slot = old_slots.get(active.plant_id)
            origin = (
                self.V4_SLOT_CENTERS[int(old_slot)]
                if isinstance(old_slot, int) and 0 <= old_slot < len(self.V4_SLOT_CENTERS)
                else self.V6_SLOT_CENTERS[0]
            )
            compatible = [
                slot for slot in range(MAX_GARDEN_SLOTS)
                if self.slot_accepts_plant(active, slot)
            ]
            destination = min(
                compatible,
                key=lambda slot: (
                    (self.V6_SLOT_CENTERS[slot][0] - origin[0]) ** 2
                    + (self.V6_SLOT_CENTERS[slot][1] - origin[1]) ** 2,
                    slot,
                ),
                default=None,
            )
            if destination is not None:
                active.slot_index = destination
                self.state.unlocked_slots = max(self.state.unlocked_slots, destination + 1)
        self.state.scene_geometry_version = geometry_version
        self._queue_feedback(
            f"scene-geometry:{geometry_version}",
            "placement",
            (
                "Placements were refreshed for the rebuilt garden. The plant you nurture was seated; the others are in Collection."
                if active is not None and active.slot_index is not None
                else "Placements were refreshed for the rebuilt garden. Plants are in Collection."
            ),
            active.plant_id if active is not None else None,
        )

    def _plant_base_type(self, plant: Plant) -> str:
        return "direct_soil"

    def slot_accepts_plant(self, plant: Plant, slot: int) -> bool:
        try:
            destination = int(slot)
        except (TypeError, ValueError):
            return False
        if destination < 0 or destination >= MAX_GARDEN_SLOTS:
            return False
        allowed = (
            self._surface_allowed_base_types[destination]
            if len(self._surface_allowed_base_types) == MAX_GARDEN_SLOTS
            else ("direct_soil",)
        )
        return self._plant_base_type(plant) in allowed

    def _arrangement_error(self, slots: dict[str, int]) -> str:
        plants = {plant.plant_id: plant for plant in self.state.plants}
        for plant_id, slot in slots.items():
            plant = plants.get(plant_id)
            if plant is None or not self.slot_accepts_plant(plant, slot):
                return self.SOIL_PLANT_MESSAGE
        return ""

    def valid_destination_slots(self, draft: PlacementDraft) -> list[int]:
        if not isinstance(draft, PlacementDraft) or draft.selected_plant_id not in draft.current:
            return []
        origin = draft.current[draft.selected_plant_id]
        valid = [origin]
        for destination in range(max(0, min(MAX_GARDEN_SLOTS, int(self.state.unlocked_slots)))):
            if destination == origin:
                continue
            candidate = dict(draft.current)
            occupant = next((pid for pid, slot in candidate.items() if slot == destination), None)
            candidate[draft.selected_plant_id] = destination
            if occupant is not None:
                candidate[occupant] = origin
            if not self._arrangement_error(candidate):
                valid.append(destination)
        return valid

    def _repair_surface_placements(self) -> None:
        occupied = {
            int(plant.slot_index)
            for plant in self.state.plants
            if plant.slot_index is not None
        }
        for plant in sorted(self.state.plants, key=lambda item: item.plant_id):
            if plant.slot_index is None or self.slot_accepts_plant(plant, plant.slot_index):
                continue
            occupied.discard(int(plant.slot_index))
            replacement = next((
                slot for slot in range(MAX_GARDEN_SLOTS)
                if slot < self.state.unlocked_slots and slot not in occupied
            ), None)
            plant.slot_index = replacement
            if replacement is not None:
                occupied.add(replacement)
                message = f"{PlantIdentity.from_plant(plant).display_name} was moved to an open garden bed."
            else:
                message = (
                    f"{PlantIdentity.from_plant(plant).display_name} was returned to the Collection because no garden bed was open."
                )
            self._queue_feedback(
                f"surface-repair:{plant.plant_id}", "collection", message, plant.plant_id
            )

    def _scheduler_day(self) -> str:
        resolver = getattr(self.storage, "current_scheduler_day", None)
        return str(resolver() if callable(resolver) else date.today().isoformat())

    def _scheduler_day_floor(self) -> int:
        resolver = getattr(self.storage, "current_day_start_ms", None)
        if not callable(resolver):
            # Lightweight test/storage adapters predate the persisted ledger.
            # Production GardenStorage always supplies the authoritative start.
            return 0
        start = int(resolver())
        if start <= 0:
            raise SchedulerBoundaryError("Anki's scheduler-day cutoff is invalid.")
        return start - 1

    @staticmethod
    def _now_seconds() -> float:
        return time.time()

    def _now_ms(self) -> int:
        resolver = getattr(self.storage, "current_time_ms", None)
        return int(resolver() if callable(resolver) else self._now_seconds() * 1000)

    def initialize_reward_state(
        self,
        *,
        activation_ms: int | None = None,
        persist: bool = True,
    ) -> bool:
        """Establish the no-replay boundary for recurring rewards and Finds."""

        if self.state.reward_state_initialized:
            return False
        snapshot = self._state_snapshot()
        boundary = max(1, int(self._now_ms() if activation_ms is None else activation_ms))
        self.state.reward_state_initialized = True
        self.state.reward_activation_ms = boundary
        self.state.garden_find_activation_ms = boundary
        self._activate_progression_if_ready(boundary)
        # The legacy eligible-answer counter is not a compatible drought.
        self.state.garden_find_drought_count = 0
        if persist:
            self._persist_or_restore(snapshot)
        return True

    def _activate_progression_if_ready(self, event_ms: int) -> bool:
        """Persist the first instant answer rewards could reach a nurtured plant."""

        if (
            not self.state.reward_state_initialized
            or self.state.progression_activation_ms > 0
        ):
            return False
        plant = next((
            candidate
            for candidate in self.state.plants
            if candidate.plant_id == self.state.active_plant_id
            and candidate.planted
            and not candidate.fully_grown
        ), None)
        established_setup = bool(
            int(self.state.garden_setup_version) >= 1
            or any(
                period.plant_id is not None
                for period in self.state.active_plant_periods
            )
        )
        if (
            not self.state.starter_selection_complete
            or (plant is None and not established_setup)
        ):
            return False
        boundary = max(1, int(event_ms))
        self.state.progression_activation_ms = boundary
        latest = max(
            (
                period
                for period in self.state.active_plant_periods
                if period.started_at_ms <= boundary
            ),
            key=lambda period: (period.started_at_ms, period.day),
            default=None,
        )
        if latest is None or latest.plant_id != self.state.active_plant_id:
            self.state.active_plant_periods.append(ActivePlantPeriod(
                self.state.daily_stats.day,
                self.state.active_plant_id,
                boundary,
            ))
        return True

    def _reward_applied(self, event_key: str) -> bool:
        resolver = getattr(self.storage, "reward_applied", None)
        if callable(resolver):
            return bool(resolver(str(event_key)))
        return str(event_key) in self.state.applied_reward_event_keys

    def _append_reward_event_key(
        self,
        event_key: str,
        *,
        source: str = "",
        scheduler_day: str = "",
        occurred_at: str = "",
    ) -> None:
        key = str(event_key)
        stager = getattr(self.storage, "stage_reward_event", None)
        if callable(stager):
            stager(
                key,
                source=str(source),
                scheduler_day=str(scheduler_day),
                occurred_at=str(occurred_at),
            )
            return
        if key and key not in self.state.applied_reward_event_keys:
            self.state.applied_reward_event_keys.append(key)

    def _append_reward_receipt(
        self,
        *,
        event_key: str,
        reward_type: str,
        source: str,
        source_id: str,
        scheduler_day: str,
        correlation_id: str,
        amount: int,
        item_id: str = "",
        plant_id: str = "",
        title: str = "",
        description: str = "",
    ) -> RewardReceipt:
        receipt = RewardReceipt(
            event_key=str(event_key),
            reward_type=str(reward_type),
            source=str(source),
            source_id=str(source_id),
            scheduler_day=str(scheduler_day),
            correlation_id=str(correlation_id),
            occurred_at=utc_now_iso(),
            amount=max(0, int(amount)),
            item_id=str(item_id),
            plant_id=str(plant_id),
            title=str(title),
            description=str(description),
        )
        self.state.recent_reward_receipts.append(receipt)
        self.state.recent_reward_receipts = bounded_reward_receipts(
            self.state.recent_reward_receipts,
            limit=MAX_REWARD_RECEIPTS,
        )
        receipt_capture = getattr(
            self,
            "_active_reward_receipt_capture",
            None,
        )
        if isinstance(receipt_capture, list):
            receipt_capture.append(receipt)
        return receipt

    def _stage_economy_event(self, record: EconomyEventRecord) -> None:
        stager = getattr(self.storage, "stage_economy_event", None)
        if callable(stager):
            stager(record)
        activity = getattr(self.storage, "stage_activity_economy_event", None)
        if callable(activity):
            activity(record, correlation_id=str(self._current_correlation_id or ""))

    def _grant_reward_bundle(
        self,
        event_key: str,
        *,
        source: str,
        source_id: str,
        reason: str,
        scheduler_day: str | None = None,
        correlation_id: str = "",
        coins: int = 0,
        coin_included_in_total: bool = True,
        growth: int = 0,
        inventory_item_id: str = "",
        inventory_quantity: int = 0,
        inventory_items: dict[str, int] | None = None,
        plant: Plant | None = None,
        title: str = "",
        description: str = "",
    ) -> tuple[RewardReceipt, ...]:
        """Apply one atomic, typed reward event inside the caller transaction."""

        key = str(event_key)
        if not key or self._reward_applied(key):
            return ()
        day_value = str(scheduler_day or self.state.daily_stats.day)
        correlation = str(correlation_id or key)
        occurred_at = utc_now_iso()
        coin_amount = max(0, int(coins))
        autumn_bonus = 0
        if coin_amount and source != "autumn_hearth":
            from .earned_coins import quote_earned_coins
            quote = quote_earned_coins(
                coin_amount, active_scenery_id=self.locked_environment_id("scenery"),
                carry_units=self.state.autumn_coin_carry_units,
            )
            autumn_bonus = quote.bonus_coins
            self.state.autumn_coin_carry_units = quote.next_carry_units
        item_grants = {
            str(item_id): max(0, int(quantity))
            for item_id, quantity in (inventory_items or {}).items()
            if max(0, int(quantity)) > 0
        }
        inventory_amount = max(0, int(inventory_quantity))
        if inventory_amount:
            item_grants[str(inventory_item_id)] = (
                item_grants.get(str(inventory_item_id), 0) + inventory_amount
            )
        receipts: list[RewardReceipt] = []
        growth_flow_result: GrowthGrantResult | None = None

        if coin_amount:
            self.state.currency_balance += coin_amount
            self.state.currency_transactions.append(CurrencyTransaction(
                transaction_id=f"tx_{uuid.uuid4().hex}",
                event_key=key,
                reason=str(reason),
                delta=coin_amount,
                balance=self.state.currency_balance,
                occurred_at=occurred_at,
                transaction_type="credit",
                source=str(source),
                source_id=str(source_id),
                scheduler_day=day_value,
                correlation_id=correlation,
                included_in_total=bool(coin_included_in_total),
            ))
            self.state.currency_transactions = self.state.currency_transactions[-500:]
            receipts.append(self._append_reward_receipt(
                event_key=key,
                reward_type="coins",
                source=source,
                source_id=source_id,
                scheduler_day=day_value,
                correlation_id=correlation,
                amount=coin_amount,
                title=title or reason,
                description=description,
            ))

        if growth:
            growth_flow_result = self._apply_direct_growth_units(
                plant,
                max(0, int(growth)) * GROWTH_UNITS_PER_POINT,
                stats_field="direct_reward_growth",
                transition_source=str(source),
            )
            actual_growth = (
                growth_flow_result.requested_units // GROWTH_UNITS_PER_POINT
            )
            if actual_growth:
                receipts.append(self._append_reward_receipt(
                    event_key=key,
                    reward_type="growth",
                    source=source,
                    source_id=source_id,
                    scheduler_day=day_value,
                    correlation_id=correlation,
                    amount=actual_growth,
                    plant_id=plant.plant_id if plant is not None else "",
                    title=title or reason,
                    description=description,
                ))

        for item_id, item_amount in item_grants.items():
            if item_id not in self.state.consumables:
                raise ValueError(f"unsupported reward inventory item: {item_id}")
            self.state.consumables[item_id] = (
                self.state.consumables.get(item_id, 0) + item_amount
            )
            receipts.append(self._append_reward_receipt(
                event_key=key,
                reward_type="inventory_item",
                source=source,
                source_id=source_id,
                scheduler_day=day_value,
                correlation_id=correlation,
                amount=item_amount,
                item_id=item_id,
                title=title or reason,
                description=description,
            ))

        metric_deltas: dict[str, Any] = {}
        if source in STANDARD_FIND_RECEIPT_SOURCES:
            metric_deltas["finds_by_outcome"] = {str(source_id): 1}
        if source == "full_bloom":
            metric_deltas["plants_completed"] = 1
        if source in {"all_due", "todays_cards"}:
            metric_deltas["today_cards_completions"] = 1
        if item_grants:
            metric_deltas["consumables_earned"] = dict(item_grants)
        growth_units = max(0, int(growth)) * GROWTH_UNITS_PER_POINT
        if coin_amount or growth_units or item_grants or metric_deltas:
            if growth_flow_result is not None:
                aggregates = self.state.lifetime_economy_aggregates
                aggregates.growth_generated_units += growth_flow_result.requested_units
                aggregates.growth_applied_to_plants_units += (
                    growth_flow_result.applied_units
                )
            self._stage_economy_event(EconomyEventRecord(
                event_key=key,
                event_kind="reward",
                # Economy aggregation groups by the canonical ledger source;
                # the receipt retains the source-specific target/day identity.
                source_id=str(source),
                scheduler_day=day_value,
                occurred_at=occurred_at,
                coins_earned=coin_amount,
                growth_earned_units=growth_units,
                growth_flow_kind=("generated" if growth_flow_result else ""),
                growth_generated_units=(
                    growth_flow_result.requested_units
                    if growth_flow_result else 0
                ),
                growth_applied_to_plants_units=(
                    growth_flow_result.applied_units
                    if growth_flow_result else 0
                ),
                growth_routed_to_storage_units_lifetime=(
                    growth_flow_result.stored_units
                    if growth_flow_result else 0
                ),
                stored_growth_balance_delta_units=(
                    growth_flow_result.stored_units
                    if growth_flow_result else 0
                ),
                growth_contributed_to_landmarks_units=(
                    growth_flow_result.landmark_units
                    if growth_flow_result else 0
                ),
                growth_contributed_to_mastery_units=(
                    growth_flow_result.mastery_units
                    if growth_flow_result else 0
                ),
                growth_contributed_to_legacy_units=(
                    growth_flow_result.legacy_units
                    if growth_flow_result else 0
                ),
                item_id=(next(iter(item_grants)) if len(item_grants) == 1 else ""),
                quantity=sum(item_grants.values()),
                metric_deltas=_project_allocation_metric_deltas(
                    (
                        growth_flow_result.project_allocations
                        if growth_flow_result is not None else ()
                    ),
                    existing=metric_deltas,
                ),
            ))

        self._append_reward_event_key(
            key,
            source=str(source),
            scheduler_day=day_value,
            occurred_at=occurred_at,
        )
        if autumn_bonus:
            receipts.extend(self._grant_reward_bundle(
                f"autumn_hearth:{key}", source="autumn_hearth", source_id="autumn",
                reason=f"Autumn Hearth bonus for {reason}", scheduler_day=day_value,
                correlation_id=correlation, coins=autumn_bonus,
                title="Autumn Hearth", description=f"+{autumn_bonus} Coins",
            ))
        return tuple(receipts)

    def earned_coin_total(self, event_key: str) -> int | None:
        """Read committed base and Autumn Coins without applying the modifier."""
        ledger = getattr(self.storage, "_reward_ledger", None)
        lookup = getattr(ledger, "activity_event", None)
        total = 0
        for key in (event_key, f"autumn_hearth:{event_key}"):
            event = lookup(key) if callable(lookup) else None
            if event is not None:
                total += max(0, int(event.coins))
                continue
            transactions = [tx for tx in self.state.currency_transactions if tx.event_key == key]
            if not transactions and (key == event_key or self._reward_applied(key)):
                return None
            total += sum(max(0, int(tx.delta)) for tx in transactions)
        return total

    def quote_completion_coins(self, core_coins: int | None = None):
        from .earned_coins import quote_completion_coins
        return quote_completion_coins(
            self.ALL_DUE_BASE_COINS if core_coins is None else core_coins,
            harvest_bell_coins=(self.CLOUDY_ALL_DUE_BONUS_COINS
                               if self.active_garden_feature_id() == "harvest_bell" else 0),
            trophy_coins=trophy_effects(self.state, event_ms=self._now_ms()).completion_coins,
            active_scenery_id=self.locked_environment_id("scenery"),
            carry_units=self.state.autumn_coin_carry_units,
        )

    def rollover_if_needed(self, *, persist: bool = True) -> None:
        runtime = getattr(self.storage, "runtime_coordinator", None)
        if runtime is not None and not getattr(self.storage, "_allow_runtime_commit", False):
            runtime.request("Garden day boundary")
        if getattr(self.storage, "runtime_pending", False) and not getattr(self.storage, "_allow_runtime_commit", False):
            return
        today = self._scheduler_day()
        if self.state.daily_stats.day == today:
            return
        scheduler_day_floor = self._scheduler_day_floor()
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        previous = self.state.daily_stats
        try:
            previous_day = date.fromisoformat(previous.day)
            current_day = date.fromisoformat(today)
        except ValueError:
            previous_day = current_day = date.today()
        if (
            previous_day < current_day
            and self.state.reward_state_initialized
            and callable(getattr(self.storage, "load_eligible_review_history", None))
        ):
            # The reviewer hook runs after Anki writes the new answer. During
            # rollover that answer already appears in revlog, but it still
            # belongs to the open day and must be handled by the live path
            # below. Reconcile only closed days here so the answer is not
            # consumed into temporary stats and then reported as a duplicate.
            reconciled, message = self.reconcile_reward_history(
                persist=False,
                include_open_day=False,
            )
            if not reconciled:
                raise RevlogReadError(message)
        self._apply_queued_loadout_for_day(today)
        self.state.daily_stats = DailyStats(day=today)
        self.state.daily_completion = DailyCompletionState(scheduler_day=today)
        self.state.daily_economy_snapshot = None
        self.state.processed_revlog_floor = scheduler_day_floor
        self.state.processed_revlog_ids = []
        # A post-activation mobile answer can arrive after any number of Anki
        # days. Preserve every local target/effect interval so delayed
        # ingestion can reconstruct answer-time Growth without granting an
        # item retroactively.
        scheduler_day_start = (scheduler_day_floor + 1) / 1000.0
        for plant in self.state.plants:
            if (
                plant.fertilizer is not None
                and float(plant.fertilizer.expires_at) <= scheduler_day_start
            ):
                archived = self._historical_fertilizer_period(
                    plant.fertilizer,
                    ended_at=scheduler_day_start,
                )
                identities = {
                    self._fertilizer_period_identity(period)
                    for period in plant.fertilizer_history
                }
                if (
                    archived is not None
                    and self._fertilizer_period_identity(archived) not in identities
                ):
                    plant.fertilizer_history.append(archived)
                    plant.fertilizer_history.sort(key=lambda period: (
                        float(
                            period.started_at
                            if period.started_at is not None
                            else period.expires_at
                        ),
                        float(period.expires_at),
                        str(period.tier),
                    ))
                plant.fertilizer = None
            if (
                plant.booster is not None
                and float(plant.booster.expires_at) <= scheduler_day_start
            ):
                archived = self._historical_booster_period(
                    plant.booster,
                    ended_at=scheduler_day_start,
                )
                identities = {
                    self._booster_period_identity(period)
                    for period in plant.booster_history
                }
                if (
                    archived is not None
                    and self._booster_period_identity(archived) not in identities
                ):
                    plant.booster_history.append(archived)
                    plant.booster_history.sort(key=lambda period: (
                        float(
                            period.started_at
                            if period.started_at is not None
                            else period.expires_at
                        ),
                        float(period.expires_at),
                    ))
                plant.booster = None
        self._record_active_period(self.state.active_plant_id)
        if persist:
            try:
                self._persist_or_restore(snapshot)
            except Exception:
                self._pending_stage_transitions = transition_snapshot
                raise

    @staticmethod
    def _batch_activation_ms(batch: CardEffectBatch) -> int:
        raw = str(getattr(batch, "activated_at", "") or "")
        if not raw:
            return 0
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int(parsed.timestamp() * 1000))
        except (TypeError, ValueError, OverflowError):
            return 0

    GARDEN_SUPPLY_TARGET = "garden:overflow"

    def consumable_target_id(self) -> str:
        return (self.GARDEN_SUPPLY_TARGET if self.state.collection_complete
                else str(self.state.active_plant_id or ""))

    def _consumable_target(self, target_id: str | None) -> Plant | GardenCardEffects | None:
        resolved = self.consumable_target_id() if target_id is None else str(target_id)
        if resolved == self.GARDEN_SUPPLY_TARGET:
            return self.state.garden_card_effects if self.state.collection_complete else None
        plant = self.plant_story(resolved)
        if (plant is not None and plant in self.state.plants and plant.planted
                and not plant.fully_grown and self.state.active_plant_id == plant.plant_id):
            return plant
        return None


    def consumable_use_projection(self, item_id: str, target_id: str | None = None) -> ConsumableUseProjection:
        resolved = self.consumable_target_id() if target_id is None else str(target_id)
        target = self._consumable_target(resolved)
        garden = isinstance(target, GardenCardEffects)
        family = "booster" if item_id == "booster_potion" else "fertilizer"
        spec = self.FERTILIZERS.get(item_id.removeprefix("fertilizer_")) if family == "fertilizer" else None
        cards = (self.BOOSTER_CARD_COUNT if family == "booster"
                 else spec.card_count if spec else 0)
        batches = sum((list(part) for part in self._card_effect_lists(target, family)), []) if target else []
        live = [batch for batch in batches if batch.remaining_cards > 0]
        name = "Garden" if garden else PlantIdentity.from_plant(target).display_name if target else ""
        noun = "Booster Potion" if family == "booster" else "Fertilizer"
        message = ("That supply is unavailable." if not cards else
                   "Choose a nurtured plant that is still growing." if target is None else
                   f"No {noun} available." if self.state.consumables.get(item_id, 0) <= 0 else
                   f"{name} already has five {noun} doses." if len(live) >= self.EFFECT_DOSE_CAP else "")
        return ConsumableUseProjection(resolved, name, "garden" if garden else "plant",
                                       not message, message, cards,
                                       sum(batch.remaining_cards for batch in live), len(live),
                                       sum(batch.effect_id == item_id and batch.remaining_cards > 0
                                           for batch in self._card_effect_lists(target, family)[1]) if target else 0,
                                       live[0].effect_id if live else "")

    def _effect_owner(self, plant: Plant | GardenCardEffects | None, family: str) -> Plant | GardenCardEffects | None:
        garden = self.state.garden_card_effects
        if any(batch.remaining_cards > 0 for group in self._card_effect_lists(garden, family) for batch in group):
            return garden
        return plant

    @staticmethod
    def _card_effect_lists(
        plant: Plant | GardenCardEffects,
        family: str,
    ) -> tuple[list[CardEffectBatch], list[CardEffectBatch]]:
        if str(family) == "fertilizer":
            return plant.fertilizer_card_batches, plant.fertilizer_card_queue
        return plant.booster_card_batches, plant.booster_card_queue

    def _active_card_effect_batch(
        self,
        plant: Plant | None,
        family: str,
        *,
        event_ms: int,
    ) -> CardEffectBatch | None:
        if plant is None:
            return None
        active, queued = self._card_effect_lists(plant, family)
        candidates = [
            batch
            for batch in (*active, *queued)
            if int(batch.remaining_cards) > 0
            and self._batch_activation_ms(batch) <= max(0, int(event_ms))
        ]
        return candidates[0] if candidates else None

    def _card_effect_supersedes_legacy(
        self,
        plant: Plant,
        family: str,
        *,
        event_ms: int,
    ) -> bool:
        active, queued = self._card_effect_lists(plant, family)
        activations = [
            self._batch_activation_ms(batch)
            for batch in (*active, *queued)
        ]
        return bool(activations) and max(0, int(event_ms)) >= min(activations)

    def _promote_card_effect_queue(self, plant: Plant, family: str) -> None:
        active, queued = self._card_effect_lists(plant, family)
        active[:] = [batch for batch in active if int(batch.remaining_cards) > 0]
        queued[:] = [batch for batch in queued if int(batch.remaining_cards) > 0]
        if active or not queued:
            return
        first = queued.pop(0)
        active.append(first)
        if str(family) == "fertilizer":
            while queued and queued[0].effect_id == first.effect_id:
                active.append(queued.pop(0))
        else:
            active.extend(queued)
            queued.clear()

    def _consume_card_effect(
        self,
        plant: Plant | None,
        family: str,
        *,
        event_ms: int,
    ) -> bool:
        plant = self._effect_owner(plant, family)
        if plant is None:
            return False
        self._promote_card_effect_queue(plant, family)
        batch = self._active_card_effect_batch(plant, family, event_ms=event_ms)
        if batch is None:
            return False
        batch.remaining_cards = max(0, int(batch.remaining_cards) - 1)
        self._promote_card_effect_queue(plant, family)
        return True

    def _add_card_effect_batch(
        self,
        plant: Plant,
        *,
        effect_id: str,
        growth_units: int,
        cards: int,
        source_event_key: str,
    ) -> str | None:
        family = "booster" if effect_id == "booster_potion" else "fertilizer"
        active, queued = self._card_effect_lists(plant, family)
        self._promote_card_effect_queue(plant, family)
        if len(active) + len(queued) >= self.EFFECT_DOSE_CAP:
            return None
        batch = CardEffectBatch(
            effect_id=str(effect_id),
            growth_per_card_units=max(0, int(growth_units)),
            total_cards=max(1, int(cards)),
            remaining_cards=max(1, int(cards)),
            activated_at=datetime.fromtimestamp(
                max(1, int(self._now_ms())) / 1000,
                tz=timezone.utc,
            ).isoformat(timespec="seconds"),
            source_event_key=str(source_event_key),
        )
        if family == "booster":
            active.append(batch)
            return "extended" if len(active) > 1 else "applied"
        if not active or active[0].effect_id == batch.effect_id:
            active.append(batch)
            return "extended" if len(active) > 1 else "applied"
        queued.append(batch)
        return "queued"

    @classmethod
    def _fertilizer_periods(cls, plant: Plant) -> tuple[Fertilizer, ...]:
        """Return unique valid timed windows in activation order."""

        periods: list[Fertilizer] = []
        seen: set[tuple[str, float, float]] = set()
        for period in (
            *plant.fertilizer_history,
            *([plant.fertilizer] if plant.fertilizer is not None else []),
        ):
            if period.started_at is None:
                continue
            start = float(period.started_at)
            end = float(period.expires_at)
            if end <= start:
                continue
            identity = cls._fertilizer_period_identity(period)
            if identity in seen:
                continue
            seen.add(identity)
            periods.append(period)
        return tuple(sorted(periods, key=lambda period: (
            float(period.started_at or 0),
            float(period.expires_at),
            str(period.tier),
        )))

    @classmethod
    def _set_fertilizer_periods(
        cls,
        plant: Plant,
        periods: Iterable[Fertilizer],
        *,
        now: float,
    ) -> None:
        ordered = list(sorted(periods, key=lambda period: (
            float(period.started_at or 0),
            float(period.expires_at),
            str(period.tier),
        )))
        active = [period for period in ordered if period.active(float(now))]
        current = active[-1] if active else None
        plant.fertilizer = current
        plant.fertilizer_history = [
            period for period in ordered if period is not current
        ]

    def fertilizer_schedule(
        self,
        plant: Plant | None,
        *,
        now: float | None = None,
    ) -> tuple[Fertilizer | None, tuple[Fertilizer, ...]]:
        """Return the current timed Fertilizer and every future queued window."""

        if plant is None:
            return None, ()
        current = self._now_seconds() if now is None else float(now)
        periods = self._fertilizer_periods(plant)
        active = next(
            (period for period in reversed(periods) if period.active(current)),
            None,
        )
        queued = tuple(
            period
            for period in periods
            if float(period.started_at or 0) >= current
            and period is not active
        )
        return active, queued

    def _transfer_timed_fertilizer(
        self,
        source: Plant,
        target: Plant,
        *,
        now: float,
    ) -> None:
        """Move every unspent second to the next plant at Full Bloom."""

        retained: list[Fertilizer] = []
        remaining: list[tuple[str, int, float]] = []
        for period in self._fertilizer_periods(source):
            start = float(period.started_at or 0)
            end = float(period.expires_at)
            if end <= now:
                retained.append(period)
                continue
            if start < now:
                retained.append(Fertilizer(
                    str(period.tier),
                    int(period.growth_per_answer),
                    float(now),
                    start,
                ))
            remaining.append((
                str(period.tier),
                int(period.growth_per_answer),
                end - max(now, start),
            ))
        if not remaining:
            self._set_fertilizer_periods(source, retained, now=now)
            return

        target_periods = list(self._fertilizer_periods(target))
        tail = max(
            (float(period.expires_at) for period in target_periods if period.expires_at > now),
            default=now,
        )
        for tier, growth, duration in remaining:
            end = tail + max(0.0, float(duration))
            if end > tail:
                target_periods.append(Fertilizer(tier, growth, end, tail))
                tail = end
        self._set_fertilizer_periods(source, retained, now=now)
        self._set_fertilizer_periods(target, target_periods, now=now)

    def _transfer_card_effects(
        self,
        source: Plant,
        target: Plant | None,
        *,
        event_ms: int | None = None,
    ) -> None:
        """Move paid remaining effects without dropping their value."""

        if target is None or source.plant_id == target.plant_id:
            return
        transfer_now = (
            max(0, int(event_ms)) / 1000
            if event_ms is not None else self._now_seconds()
        )
        # Legacy timed windows are retained only as a schema-25 migration
        # bridge. New activations and all durable value use card batches.
        self._transfer_timed_fertilizer(source, target, now=transfer_now)
        for family in ("fertilizer", "booster"):
            source_active, source_queue = self._card_effect_lists(source, family)
            batches = [
                batch
                for batch in (*source_active, *source_queue)
                if int(batch.remaining_cards) > 0
            ]
            source_active.clear()
            source_queue.clear()
            target_active, target_queue = self._card_effect_lists(target, family)
            for batch in batches:
                if len(target_active) + len(target_queue) >= self.EFFECT_DOSE_CAP:
                    source_queue.append(batch)
                    continue
                if family == "fertilizer" and target_active and (
                    target_active[0].effect_id != batch.effect_id
                ):
                    target_queue.append(batch)
                else:
                    target_active.append(batch)
            self._promote_card_effect_queue(target, family)

    def _claim_completed_plant_effects(self, target: Plant) -> None:
        for completed in sorted(
            (item for item in self.state.plants if item.fully_grown),
            key=lambda item: (
                int(item.slot_index if item.slot_index is not None else MAX_GARDEN_SLOTS),
                item.plant_id,
            ),
        ):
            self._transfer_card_effects(completed, target)

    def fertilizer_growth(self, plant: Plant | None, *, now: float | None = None) -> int:
        plant = self._effect_owner(plant, "fertilizer")
        if plant is None:
            return 0
        current = self._now_seconds() if now is None else float(now)
        event_ms = max(0, int(current * 1000))
        card_batch = self._active_card_effect_batch(
            plant, "fertilizer", event_ms=event_ms
        )
        if card_batch is not None:
            return (
                max(0, int(card_batch.growth_per_card_units))
                // GROWTH_UNITS_PER_POINT
            )
        if isinstance(plant, GardenCardEffects) or self._card_effect_supersedes_legacy(
            plant, "fertilizer", event_ms=event_ms
        ):
            return 0
        # The most recently activated matching interval wins. This is
        # deterministic even for a repaired payload containing overlapping
        # periods, while normal replacement paths truncate the old interval.
        matches = [
            (index, period)
            for index, period in enumerate([
                *plant.fertilizer_history,
                *([plant.fertilizer] if plant.fertilizer is not None else []),
            ])
            if period.active(current)
        ]
        if not matches:
            return 0
        _index, active_period = max(matches, key=lambda item: (
            float(item[1].started_at if item[1].started_at is not None else item[1].expires_at),
            item[0],
        ))
        return int(active_period.growth_per_answer)

    def booster_growth(self, plant: Plant | None, *, now: float | None = None) -> int:
        plant = self._effect_owner(plant, "booster")
        if plant is None:
            return 0
        current = self._now_seconds() if now is None else float(now)
        event_ms = max(0, int(current * 1000))
        card_batch = self._active_card_effect_batch(
            plant, "booster", event_ms=event_ms
        )
        if card_batch is not None:
            return max(0, int(card_batch.growth_per_card_units)) // GROWTH_UNITS_PER_POINT
        if isinstance(plant, GardenCardEffects) or self._card_effect_supersedes_legacy(
            plant, "booster", event_ms=event_ms
        ):
            return 0
        matches = [
            (index, period)
            for index, period in enumerate([
                *plant.booster_history,
                *([plant.booster] if plant.booster is not None else []),
            ])
            if period.active(current)
        ]
        if not matches:
            return 0
        _index, active_period = max(matches, key=lambda item: (
            float(item[1].started_at if item[1].started_at is not None else item[1].expires_at),
            item[0],
        ))
        return int(active_period.growth_per_answer)

    @staticmethod
    def _historical_fertilizer_period(
        fertilizer: Fertilizer | None,
        *,
        ended_at: float,
    ) -> Fertilizer | None:
        if fertilizer is None or fertilizer.started_at is None:
            return None
        end = min(float(fertilizer.expires_at), float(ended_at))
        start = float(fertilizer.started_at)
        if start >= end:
            return None
        return Fertilizer(
            str(fertilizer.tier),
            int(fertilizer.growth_per_answer),
            end,
            start,
        )

    @staticmethod
    def _fertilizer_period_identity(period: Fertilizer) -> tuple[str, float, float]:
        return (
            str(period.tier),
            float(period.started_at if period.started_at is not None else period.expires_at),
            float(period.expires_at),
        )

    def _activate_fertilizer_effect(
        self,
        plant: Plant,
        spec: FertilizerSpec,
        *,
        now: float,
        source_event_key: str = "",
    ) -> str:
        """Schedule one card-counted Fertilizer dose without losing value."""

        del now
        action = self._add_card_effect_batch(
            plant,
            effect_id=f"fertilizer_{spec.tier}",
            growth_units=spec.growth_per_answer * GROWTH_UNITS_PER_POINT,
            cards=spec.card_count,
            source_event_key=source_event_key,
        )
        if action is None:
            raise RuntimeError("Fertilizer dose limit reached")
        return action

    @staticmethod
    def _historical_booster_period(
        booster: Booster | None,
        *,
        ended_at: float,
    ) -> Booster | None:
        if booster is None or booster.started_at is None:
            return None
        end = min(float(booster.expires_at), float(ended_at))
        start = float(booster.started_at)
        if start >= end:
            return None
        return Booster(int(booster.growth_per_answer), end, start)

    @staticmethod
    def _booster_period_identity(period: Booster) -> tuple[int, float, float]:
        return (
            int(period.growth_per_answer),
            float(period.started_at if period.started_at is not None else period.expires_at),
            float(period.expires_at),
        )

    def current_streak_bonus_percent(self) -> int:
        """Highest permanent base-card Growth tier unlocked by achievements."""
        return streak_growth_progress(self.state)[0]

    @staticmethod
    def _state_economy_snapshot(
        record: DailyEconomySnapshotRecord,
    ) -> DailyEconomySnapshot:
        return DailyEconomySnapshot(
            anki_day=str(record.anki_day),
            active_garden_bonus_id=str(record.active_garden_bonus_id),
            active_scenery_effect_id=str(record.active_scenery_effect_id),
            snapshot_source=str(record.snapshot_source),
            snapshot_id=str(record.snapshot_id),
        )

    def _ensure_daily_economy_snapshot(
        self,
        scheduler_day: str,
        *,
        historical_sync: bool,
        event_ms: int,
    ) -> DailyEconomySnapshot:
        """Record daily equipment metadata; each transaction resolves its rewards."""

        day_value = str(scheduler_day)
        state_snapshot = getattr(self.state, "daily_economy_snapshot", None)
        if state_snapshot is not None and state_snapshot.anki_day == day_value:
            return state_snapshot

        resolver = getattr(self.storage, "daily_economy_snapshot", None)
        record = resolver(day_value) if callable(resolver) else None
        if record is not None:
            snapshot = self._state_economy_snapshot(record)
            self.state.daily_economy_snapshot = snapshot
            return snapshot

        try:
            current_day = self._scheduler_day()
        except Exception:
            current_day = self.state.daily_stats.day
        fail_closed = bool(historical_sync and day_value < str(current_day))
        if fail_closed:
            garden_bonus = DEFAULT_GARDEN_FEATURE_ID
            scenery_effect = DEFAULT_SCENERY_ID
            source = "sync_fail_closed"
        else:
            garden_bonus = self.active_garden_feature_id()
            scenery_effect = self.locked_environment_id("scenery")
            source = "first_eligible_answer"

        snapshot_id = hashlib.sha256(
            "\0".join((
                str(self.state.reward_seed),
                "daily-economy-snapshot-v1",
                day_value,
            )).encode("utf-8")
        ).hexdigest()
        record = DailyEconomySnapshotRecord(
            anki_day=day_value,
            active_garden_bonus_id=garden_bonus,
            active_scenery_effect_id=scenery_effect,
            snapshot_source=source,
            snapshot_id=snapshot_id,
        )
        stager = getattr(self.storage, "stage_daily_economy_snapshot", None)
        if callable(stager):
            stager(record)
        snapshot = self._state_economy_snapshot(record)
        self.state.daily_economy_snapshot = snapshot

        return snapshot

    @staticmethod
    def _streak_by_scheduler_day(entries: tuple[Any, ...]) -> dict[str, int]:
        days = sorted({str(entry.scheduler_day) for entry in entries})
        result: dict[str, int] = {}
        previous: date | None = None
        run = 0
        for day_value in days:
            current = date.fromisoformat(day_value)
            run = run + 1 if previous is not None and current == previous + timedelta(days=1) else 1
            result[day_value] = run
            previous = current
        return result

    @staticmethod
    def _sync_card_effect_signature(plant: Plant, family: str) -> tuple[Any, ...]:
        active, queued = GardenGameEngine._card_effect_lists(plant, family)
        return tuple(
            (
                str(batch.effect_id),
                max(0, int(batch.growth_per_card_units)),
                max(0, int(batch.total_cards)),
                max(0, int(batch.remaining_cards)),
                str(batch.activated_at or ""),
                str(batch.source_event_key or ""),
                lane,
            )
            for lane, batches in (("active", active), ("queued", queued))
            for batch in batches
        )

    def sync_reward_baseline(self) -> dict[str, Any]:
        """Return compact presentation facts at one clean sync boundary.

        This deliberately excludes revlog identities. The durable answer ledger
        remains the only authority for deciding which post-sync events are new.
        """

        now_seconds = self._now_seconds()
        active = self.active_plant()
        fertilizer, _queued_fertilizer = self.fertilizer_schedule(
            active, now=now_seconds
        )
        fertilizer_owner = self._effect_owner(active, "fertilizer")
        active_fertilizer_batches = tuple(
            batch for group in self._card_effect_lists(fertilizer_owner, "fertilizer")
            for batch in group if batch.remaining_cards > 0
        ) if fertilizer_owner is not None else ()
        fertilizer_cards_remaining = sum(
            max(0, int(batch.remaining_cards))
            for batch in active_fertilizer_batches
        )
        fertilizer_item_id = (
            str(active_fertilizer_batches[0].effect_id)
            if active_fertilizer_batches
            else (
                f"fertilizer_{str(fertilizer.tier)}"
                if fertilizer is not None else ""
            )
        )
        plants: dict[str, dict[str, Any]] = {}
        fertilizer_signature: list[Any] = []
        booster_signature: list[Any] = []
        booster_cards_remaining = 0
        for plant in self.state.plants:
            plants[str(plant.plant_id)] = {
                "plant_id": str(plant.plant_id),
                "plant_name": str(PlantIdentity.from_plant(plant).display_name or "Plant"),
                "species": str(plant.species or ""),
                "growth_units": max(0, int(plant.growth_units)),
                "stage": str(plant.growth_stage or ""),
                "fully_grown": bool(plant.fully_grown),
                "slot_index": (
                    None if plant.slot_index is None else int(plant.slot_index)
                ),
                "checkpoint_claims": tuple(sorted({
                    str(value) for value in plant.checkpoint_claims if str(value)
                })),
                "stage_reward_claims": tuple(sorted({
                    str(value) for value in plant.stage_reward_claims if str(value)
                })),
            }
            timed_fertilizer = tuple(
                self._fertilizer_period_identity(period)
                for period in self._fertilizer_periods(plant)
            )
            fertilizer_signature.append((
                str(plant.plant_id),
                timed_fertilizer,
                self._sync_card_effect_signature(plant, "fertilizer"),
            ))
            timed_booster = tuple(
                self._booster_period_identity(period)
                for period in (
                    *plant.booster_history,
                    *([plant.booster] if plant.booster is not None else []),
                )
                if period.started_at is not None
            )
            card_boosters = self._sync_card_effect_signature(plant, "booster")
            booster_signature.append((
                str(plant.plant_id), timed_booster, card_boosters
            ))
            if active is not None and plant.plant_id == active.plant_id:
                booster_cards_remaining = sum(
                    max(0, int(batch.remaining_cards))
                    for batch in (
                        *plant.booster_card_batches,
                        *plant.booster_card_queue,
                    )
                )
        garden = self.state.garden_card_effects
        fertilizer_signature.append((self.GARDEN_SUPPLY_TARGET, (), self._sync_card_effect_signature(garden, "fertilizer")))
        booster_signature.append((self.GARDEN_SUPPLY_TARGET, (), self._sync_card_effect_signature(garden, "booster")))
        if self._effect_owner(active, "booster") is garden:
            booster_cards_remaining = sum(batch.remaining_cards for group
                                          in self._card_effect_lists(garden, "booster") for batch in group)
        inventory = getattr(self.state, "inventory", {}) or {}
        environments = {
            "garden_feature": tuple(sorted({
                str(value)
                for value in inventory.get("garden_features", ())
                if str(value)
            })),
            "scenery": tuple(sorted({
                str(value)
                for value in inventory.get("scenery", ())
                if str(value)
            })),
        }
        completion = self.state.daily_completion
        completion_remaining = sum((
            max(0, int(completion.remaining_new_cards)),
            max(0, int(completion.remaining_required_reviews)),
            max(0, int(completion.remaining_learning_steps)),
            max(0, int(completion.future_learning_steps_before_cutoff)),
        ))
        return {
            "scheduler_day": self._scheduler_day(),
            "ledger_revision": max(
                0, int(getattr(self.storage, "_ledger_revision", 0) or 0)
            ),
            "active_plant_id": str(self.state.active_plant_id or ""),
            "plants": plants,
            "stored_growth_units": max(
                0, int(getattr(self.state, "stored_growth_units", 0) or 0)
            ),
            "landmark_growth_units": max(
                0,
                int(self.state.garden_project.contributed_growth_units),
            ),
            "total_growth_units": sum(
                max(0, int(plant.growth_units)) for plant in self.state.plants
            ) + max(
                0, int(getattr(self.state, "stored_growth_units", 0) or 0)
            ) + max(
                0, int(self.state.garden_project.contributed_growth_units)
            ),
            "garden_coin_balance": max(0, int(self.state.currency_balance)),
            "consumables": {
                str(key): max(0, int(value))
                for key, value in self.state.consumables.items()
            },
            "environments": environments,
            "reward_receipts": tuple(
                self._reward_receipt_identity(receipt)
                for receipt in self.state.recent_reward_receipts
            ),
            "fertilizer_signature": tuple(fertilizer_signature),
            "fertilizer_cards_remaining": max(
                0, fertilizer_cards_remaining
            ),
            "fertilizer_remaining_seconds": (
                max(0, int(math.ceil(float(fertilizer.expires_at) - now_seconds)))
                if fertilizer is not None else 0
            ),
            "fertilizer_item_id": fertilizer_item_id,
            "booster_signature": tuple(booster_signature),
            "booster_cards_remaining": max(0, booster_cards_remaining),
            "booster_item_id": (
                "booster_potion" if booster_cards_remaining > 0 else ""
            ),
            "daily_completion": {
                "scheduler_day": str(completion.scheduler_day or ""),
                "projection_initialized": bool(
                    completion.obligation_projection_initialized
                ),
                "remaining": completion_remaining,
                "reward_claimed": bool(completion.reward_claimed),
                "due_started_with_cards": (
                    self.state.daily_stats.due_started_with_cards
                ),
            },
        }

    def prepare_sync_reward_boundary(self) -> tuple[bool, str]:
        """Commit a clean local ledger and cautious current-day due projection."""

        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        try:
            reconciled, message = self.reconcile_reward_history(
                persist=False,
                include_open_day=True,
                emit_feedback=False,
            )
            if not reconciled:
                self._pending_stage_transitions = transition_snapshot
                self._restore_state(snapshot)
                return False, message
            due_resolver = getattr(self.storage, "due_obligations", None)
            due_status = due_resolver() if callable(due_resolver) else None
            if (
                due_status is not None
                and due_status.available
                and not due_status.error
            ):
                remaining = max(0, int(due_status.remaining))
                self._update_daily_completion(
                    due_status,
                    preserve_start=False,
                )
                # This is an observation only. It establishes that a positive
                # obligation existed before sync but never grants All Clear.
                if remaining > 0:
                    self.state.daily_stats.due_started_with_cards = True
            has_staged = getattr(
                self.storage, "reward_ledger_has_staged_writes", None
            )
            if (
                self.state.to_dict() != snapshot
                or (callable(has_staged) and bool(has_staged()))
            ):
                self._persist_or_restore(snapshot)
            return True, "Garden is ready for sync."
        except (RevlogReadError, SchedulerBoundaryError, ValueError, TypeError):
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "Anki review history is not available yet."
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise

    def baseline_reward_history(
        self,
        reason: str = "collection_replaced",
        *,
        persist: bool = True,
    ) -> tuple[bool, str]:
        """Consume replacement history without granting retrospective rewards."""

        resolver = getattr(self.storage, "load_reconciliation_history", None)
        if not callable(resolver):
            resolver = getattr(self.storage, "load_eligible_review_history", None)
        if not callable(resolver):
            return False, "Anki review history is not available yet."
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        try:
            if not self.state.reward_state_initialized:
                self.initialize_reward_state(persist=False)
            history_snapshot = resolver()
            current_day = self._scheduler_day()
            entries = tuple(
                entry
                for entry in history_snapshot.entries
                if str(entry.scheduler_day) <= current_day
            )
            reviews = tuple(
                HistoricalReview(
                    event_id=int(entry.revlog_id),
                    answered_at_ms=int(entry.answer_ms),
                    scheduler_day=str(entry.scheduler_day),
                    rating=int(entry.ease),
                )
                for entry in entries
            )
            history = getattr(history_snapshot, "history", None)
            if history is None:
                history = analyze_history(reviews, current_open_day=current_day)
            self.state.lifetime_eligible_answers = int(history.lifetime_answers)
            self.state.current_non_again_run = int(history.current_non_again_tail)
            self.state.streak_days = int(history.current_streak_days)
            if history.latest_active_day:
                self.state.last_active_day = history.latest_active_day
            self._ensure_achievements()
            for definition in ACHIEVEMENT_DEFINITIONS:
                completion_day = history.unlock_day(definition.achievement_id)
                if not completion_day:
                    continue
                achievement = self.state.achievements[definition.achievement_id]
                event_key = f"achievement:{definition.achievement_id}"
                if not achievement.unlocked:
                    achievement.unlocked = True
                    achievement.progress = 1.0
                    achievement.unlocked_at = f"{completion_day}T00:00:00+00:00"
                    achievement.rewarded_at = None
                    achievement.reward_event_key = event_key
                    achievement.historical_backfill = True
                self._append_reward_event_key(event_key)
            streak_by_day = (history_snapshot.streaks() if hasattr(history_snapshot, "streaks")
                             else self._streak_by_scheduler_day(entries))
            activation = max(
                1,
                int(self.state.reward_activation_ms),
                int(self.state.progression_activation_ms),
            )
            post_activation_days: set[str] = set()
            current_revlogs: list[int] = []
            for entry in entries:
                if int(entry.answer_ms) < int(self.state.reward_activation_ms):
                    continue
                if queue_and_lapse_from_revlog_type(
                    entry.review_type, entry.ease
                ) is None:
                    continue
                answer_key = consumption_id(stable_answer_event_identity(
                    int(entry.revlog_id),
                    card_id=int(entry.card_id),
                    answered_at_ms=int(entry.answer_ms),
                    lineage_id=str(entry.stable_answer_key),
                ))
                self._record_answer_consumption(
                    answer_key,
                    scheduler_day=str(entry.scheduler_day),
                    lineage_id=str(entry.stable_answer_key),
                    revlog_id=int(entry.revlog_id),
                )
                post_activation_days.add(str(entry.scheduler_day))
                if str(entry.scheduler_day) == current_day:
                    current_revlogs.append(int(entry.revlog_id))
            for day_value in post_activation_days:
                self._append_reward_event_key(f"daily_activity:{day_value}")
            if hasattr(history_snapshot, "days"):
                current_revlogs.extend(self.state.processed_revlog_ids)
            self.state.processed_revlog_ids = sorted({
                value for value in current_revlogs
                if value > int(self.state.processed_revlog_floor)
            })[-MAX_PROCESSED_REVLOG_IDS:]
            self.state.last_processed_revlog_id = max(
                int(self.state.last_processed_revlog_id),
                max(current_revlogs, default=0),
            )
            for summary in history.daily_summaries:
                if summary.closed:
                    self._record_finalized_day(
                        summary.scheduler_day,
                        f"baseline:{summary.total_answers}:"
                        f"{summary.non_again_answers}:{summary.again_answers}",
                    )
            self.state.achievement_history_fingerprint = history.fingerprint
            self.state.achievement_history_high_water_revlog_id = (
                history_snapshot.high_water_revlog_id if hasattr(history_snapshot, "days") else
                max((int(entry.revlog_id) for entry in entries), default=0)
            )
            self._refresh_achievement_progress(history)
            has_staged = getattr(
                self.storage, "reward_ledger_has_staged_writes", None
            )
            if persist and (
                self.state.to_dict() != snapshot
                or (callable(has_staged) and bool(has_staged()))
            ):
                self._persist_or_restore(snapshot)
            return True, f"Garden baseline updated after {str(reason or 'sync')}."
        except (RevlogReadError, SchedulerBoundaryError, ValueError, TypeError):
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "Anki review history is not available yet."
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise

    def reconcile_reward_history(
        self,
        *,
        persist: bool = True,
        include_open_day: bool = True,
        result_collector: list[CommittedAnswerResult] | None = None,
        due_status: DueObligationStatus | None = None,
        pending_summary_factory: Callable[
            [tuple[CommittedAnswerResult, ...]], SyncRewardSummary | None
        ] | None = None,
        emit_feedback: bool = True,
    ) -> tuple[bool, str]:
        """Rebuild achievements and process only post-activation synced answers.

        Rollover uses ``include_open_day=False`` because Anki has already added
        the answer that triggered the reviewer hook to revlog. Normal startup
        and sync maintenance include the open day so unseen mobile reviews are
        caught up.
        """

        resolver = getattr(self.storage, "load_reconciliation_history", None)
        if not callable(resolver):
            resolver = getattr(self.storage, "load_eligible_review_history", None)
        if not callable(resolver):
            return False, "Anki review history is not available yet."
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        previous_correlation = self._current_correlation_id
        previous_equipment = self._reward_equipment
        self._reward_equipment = (
            self.active_garden_feature_id(), self.locked_environment_id("scenery")
        )
        try:
            if not self.state.reward_state_initialized:
                if self._pending_reward_activation_ms is None:
                    self._pending_reward_activation_ms = self._now_ms()
                self.initialize_reward_state(
                    activation_ms=self._pending_reward_activation_ms,
                    persist=False,
                )
            history_snapshot = resolver()
            current_day = self._scheduler_day()
            entries = tuple(
                entry
                for entry in history_snapshot.entries
                if (
                    str(entry.scheduler_day) <= current_day
                    if include_open_day
                    else str(entry.scheduler_day) < current_day
                )
            )
            reviews = tuple(
                HistoricalReview(
                    event_id=int(entry.revlog_id),
                    answered_at_ms=int(entry.answer_ms),
                    scheduler_day=str(entry.scheduler_day),
                    rating=int(entry.ease),
                )
                for entry in entries
            )
            history = getattr(history_snapshot, "history" if include_open_day else "closed_history", None)
            if history is None:
                history = analyze_history(reviews, current_open_day=current_day)
            self.state.lifetime_eligible_answers = int(history.lifetime_answers)
            self.state.current_non_again_run = int(history.current_non_again_tail)
            self.state.streak_days = int(history.current_streak_days)
            if history.latest_active_day:
                self.state.last_active_day = history.latest_active_day
            self._ensure_achievements()

            reconciled_high_water = (
                max((int(row["last"]) for row in history_snapshot.days
                     if include_open_day or str(row["day"]) < current_day), default=0)
                if hasattr(history_snapshot, "days") else
                max((int(entry.revlog_id) for entry in entries), default=0)
            )
            sync_correlation = (
                f"sync:{reconciled_high_water}:{history.fingerprint[:12]}"
            )
            self._current_correlation_id = sync_correlation
            existing_receipts = tuple(self.state.recent_reward_receipts)
            existing_feedback = deepcopy(self.state.pending_feedback)
            unlocked_before_sync = {
                achievement_id
                for achievement_id, achievement in self.state.achievements.items()
                if achievement.unlocked
            }
            for definition in ACHIEVEMENT_DEFINITIONS:
                completion_day = history.unlock_day(definition.achievement_id)
                if completion_day:
                    self._unlock_achievement(
                        definition.achievement_id,
                        completion_day=completion_day,
                        correlation_id=sync_correlation,
                        historical=True,
                    )
            self._refresh_achievement_progress(history)
            unlocked_during_sync = tuple(
                definition.achievement_id
                for definition in ACHIEVEMENT_DEFINITIONS
                if (
                    self.state.achievements[definition.achievement_id].unlocked
                    and definition.achievement_id not in unlocked_before_sync
                )
            )
            self._capture_welcome_history(history)
            for summary in history.daily_summaries:
                if summary.closed:
                    self._record_finalized_day(
                        summary.scheduler_day,
                        f"history:{summary.total_answers}:"
                        f"{summary.non_again_answers}:{summary.again_answers}"
                    )

            streak_by_day = (history_snapshot.streaks() if hasattr(history_snapshot, "streaks")
                             else self._streak_by_scheduler_day(entries))
            entries_by_day: dict[str, list[Any]] = {}
            for entry in entries:
                entries_by_day.setdefault(str(entry.scheduler_day), []).append(entry)
            recurring_boundary = max(
                1,
                int(self.state.reward_activation_ms),
                int(self.state.progression_activation_ms),
            )
            if self.state.progression_activation_ms > 0:
                # Sync may fill an older gap and move an already-studied day
                # onto an authoritative 7-day boundary. Grants are monotonic:
                # preserve any earlier committed cycle and add each newly
                # proven post-activation cycle once. Previously committed
                # answer Growth is intentionally not rewritten or revoked.
                for day_value, streak_days in streak_by_day.items():
                    if streak_days <= 0 or streak_days % 7:
                        continue
                    if not (
                        history_snapshot.active_after(day_value, recurring_boundary)
                        if hasattr(history_snapshot, "active_after") else any(
                            int(entry.answer_ms) >= recurring_boundary
                            for entry in entries_by_day.get(day_value, ())
                        )
                    ):
                        continue
                    self._apply_streak_rewards(
                        scheduler_day=day_value,
                        correlation_id=sync_correlation,
                        streak_days=streak_days,
                        allow_recurring_reward=True,
                    )
            day_answer_numbers: dict[str, int] = {}
            temporary_stats: dict[str, DailyStats] = {}
            temporary_completion: dict[str, DailyCompletionState] = {}
            temporary_economy_snapshots: dict[
                str, DailyEconomySnapshot | None
            ] = {}
            current_stats = self.state.daily_stats
            current_completion = self.state.daily_completion
            current_economy_snapshot = self.state.daily_economy_snapshot
            candidate_answer_keys = {
                consumption_id(stable_answer_event_identity(
                    int(entry.revlog_id),
                    card_id=int(entry.card_id),
                    answered_at_ms=int(entry.answer_ms),
                    lineage_id=str(entry.stable_answer_key),
                ))
                for entry in entries
                if int(entry.answer_ms) >= int(self.state.reward_activation_ms)
            }
            consumed_resolver = getattr(
                self.storage, "consumed_answer_keys", None
            )
            processed_answer_keys = (
                set(consumed_resolver(candidate_answer_keys))
                if callable(consumed_resolver)
                else candidate_answer_keys.intersection(
                    self.state.processed_answer_keys
                )
            )
            synced_answers = 0
            synced_growth = 0
            committed_results: list[CommittedAnswerResult] = []
            pending_result: tuple[
                Mapping[str, Any], ReviewAward, Mapping[str, Any]
            ] | None = None
            for entry in entries:
                day_value = str(entry.scheduler_day)
                day_answer_numbers[day_value] = day_answer_numbers.get(day_value, 0) + 1
                answer_number = getattr(history_snapshot, "day_answer_numbers", {}).get(
                    int(entry.revlog_id), day_answer_numbers[day_value]
                )
                if int(entry.answer_ms) < int(self.state.reward_activation_ms):
                    continue
                answer_identity = stable_answer_event_identity(
                    int(entry.revlog_id),
                    card_id=int(entry.card_id),
                    answered_at_ms=int(entry.answer_ms),
                    lineage_id=str(entry.stable_answer_key),
                )
                answer_key = consumption_id(answer_identity)
                if entry.stable_answer_key:
                    self._bind_answer_lineage(
                        int(entry.revlog_id),
                        str(entry.stable_answer_key),
                    )
                if answer_key in processed_answer_keys:
                    if day_value == current_day:
                        self._acknowledge_current_revlog(int(entry.revlog_id))
                    continue
                if day_value == current_stats.day:
                    self.state.daily_stats = current_stats
                    self.state.daily_completion = current_completion
                    self.state.daily_economy_snapshot = current_economy_snapshot
                else:
                    self.state.daily_stats = temporary_stats.setdefault(
                        day_value, DailyStats(day=day_value)
                    )
                    self.state.daily_completion = temporary_completion.setdefault(
                        day_value, DailyCompletionState(scheduler_day=day_value)
                    )
                    self.state.daily_economy_snapshot = (
                        temporary_economy_snapshots.setdefault(day_value, None)
                    )
                semantics = queue_and_lapse_from_revlog_type(
                    entry.review_type, entry.ease
                )
                if semantics is None:
                    continue
                queue, lapse_count = semantics
                if pending_result is not None:
                    previous_payload, previous_award, previous_baseline = pending_result
                    committed_results.append(self._committed_answer_result(
                        payload=previous_payload,
                        award=previous_award,
                        baseline=previous_baseline,
                    ))
                    pending_result = None
                payload = {
                    "queue": queue,
                    "ease": int(entry.ease),
                    "factor": int(entry.factor),
                    "lapse_count": lapse_count,
                    "revlog_id": int(entry.revlog_id),
                    "card_id": int(entry.card_id),
                    "answered_at_ms": int(entry.answer_ms),
                    "answer_identity": str(entry.stable_answer_key),
                    "scheduler_day": day_value,
                    "day_answer_number": answer_number,
                    "first_answer_of_day": answer_number == 1,
                    "streak_days": streak_by_day.get(day_value, 0),
                    "history_counted": True,
                    "historical_sync": True,
                    "activity_batch_id": sync_correlation,
                    "environment_growth_known": True,
                    "emit_feedback": False,
                    "correlation_id": sync_correlation,
                }
                ledger = getattr(self.storage, "_reward_ledger", None)
                if ledger is not None:
                    payload.update(ledger.deferred_review_context(int(entry.revlog_id)))
                answer_baseline = self._committed_answer_baseline()
                award = self._register_review_in_memory(payload)
                if day_value == current_day:
                    current_economy_snapshot = self.state.daily_economy_snapshot
                else:
                    temporary_economy_snapshots[day_value] = (
                        self.state.daily_economy_snapshot
                    )
                if award.correlation_id:
                    pending_result = (payload, award, answer_baseline)
                processed_answer_keys.add(answer_key)
                if day_value == current_day:
                    processed = self.state.processed_revlog_ids
                    index = bisect_left(processed, int(entry.revlog_id))
                    if index >= len(processed) or processed[index] != int(entry.revlog_id):
                        if len(processed) >= MAX_PROCESSED_REVLOG_IDS:
                            raise RuntimeError(
                                "The current scheduler day exceeded Garden's "
                                "review-history safety bound."
                            )
                        insort(processed, int(entry.revlog_id))
                    self.state.last_processed_revlog_id = max(
                        self.state.last_processed_revlog_id,
                        int(entry.revlog_id),
                    )
                synced_answers += 1
                synced_growth += award.total_growth
            self.state.daily_stats = current_stats
            self.state.daily_completion = current_completion
            self.state.daily_economy_snapshot = current_economy_snapshot
            if (
                pending_result is not None
                and due_status is not None
                and any(
                    str(result.scheduler_day) == current_day
                    for result in committed_results
                )
                or (
                    pending_result is not None
                    and due_status is not None
                    and str(pending_result[0].get("scheduler_day", "")) == current_day
                )
            ):
                self.evaluate_today_cards(
                    due_status,
                    persist=False,
                    correlation_id=str(pending_result[1].correlation_id),
                    record_completed_delta=True,
                    completed_obligation_limit=max(
                        1,
                        sum(
                            1
                            for result in committed_results
                            if str(result.scheduler_day) == current_day
                        )
                        + int(
                            str(pending_result[0].get("scheduler_day", ""))
                            == current_day
                        ),
                    ),
                    emit_feedback=False,
                )
            if pending_result is not None:
                payload, award, answer_baseline = pending_result
                committed_results.append(self._committed_answer_result(
                    payload=payload,
                    award=award,
                    baseline=answer_baseline,
                ))
            if result_collector is not None:
                result_collector.extend(committed_results)
            if pending_summary_factory is not None and committed_results:
                summary = pending_summary_factory(tuple(committed_results))
                if summary is not None and summary.meaningful:
                    existing = SyncRewardSummary.from_dict(
                        self.state.pending_sync_reward_summary
                    )
                    if existing is not None:
                        summary = existing.merge(summary)
                    self.state.pending_sync_reward_summary = summary.to_dict()
            self.state.achievement_history_fingerprint = history.fingerprint
            self.state.achievement_history_high_water_revlog_id = (
                reconciled_high_water
            )
            self._refresh_achievement_progress(history)

            if not emit_feedback:
                # Stage/checkpoint currency helpers predate the batch feedback
                # switch and can enqueue their own cards. A sync receipt is the
                # only presentation for this transaction, so retain exactly the
                # feedback and ordinary stage-transition queue that existed at
                # the clean boundary.
                self.state.pending_feedback = existing_feedback
                self._pending_stage_transitions = transition_snapshot
            sync_receipts = tuple(
                receipt
                for receipt in self.state.recent_reward_receipts
                if receipt not in existing_receipts
                if receipt.correlation_id == sync_correlation
            )
            welcome = self.state.welcome_receipt
            if welcome is not None and welcome.status == "collecting":
                welcome_keys = {row.event_key for row in welcome.history_rewards}
                sync_receipts = tuple(row for row in sync_receipts if row.event_key not in welcome_keys)
                unlocked_during_sync = tuple(
                    key for key in unlocked_during_sync if key not in welcome.achievement_ids
                )
            if emit_feedback and sync_receipts:
                self._queue_reward_feedback(
                    sync_correlation,
                    sync_receipts,
                    achievement_ids=unlocked_during_sync,
                    title=f"{len(sync_receipts):,} Garden rewards added",
                )
            elif emit_feedback and synced_answers and synced_growth:
                self._queue_feedback(
                    f"reward-summary:{sync_correlation}",
                    "reward_summary",
                    (
                        f"{synced_growth:,} Growth added."
                    ),
                    title="Garden progress updated",
                    asset_category="ui",
                    asset_key="growth",
                    amount=synced_growth,
                    correlation_id=sync_correlation,
                )
            has_staged_writes = getattr(
                self.storage, "reward_ledger_has_staged_writes", None
            )
            if persist and (
                self.state.to_dict() != snapshot
                or (
                    callable(has_staged_writes)
                    and bool(has_staged_writes())
                )
            ):
                self._persist_or_restore(snapshot)
            self._current_correlation_id = previous_correlation
            return True, "Garden is up to date."
        except (RevlogReadError, SchedulerBoundaryError, ValueError, TypeError):
            self._current_correlation_id = previous_correlation
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "Anki review history is not available yet."
        except Exception:
            self._current_correlation_id = previous_correlation
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise
        finally:
            self._reward_equipment = previous_equipment

    def reconcile_retrospective_streak(self, *, persist: bool = True) -> tuple[bool, str]:
        """Compatibility alias for the unified reward-history reconciliation."""

        return self.reconcile_reward_history(persist=persist)

    def register_review(self, review_payload: Dict[str, Any]) -> ReviewAward:
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.rollover_if_needed(persist=False)
        try:
            award = self._register_review_in_memory(review_payload)
            has_staged_writes = getattr(
                self.storage, "reward_ledger_has_staged_writes", None
            )
            if (
                self.state.to_dict() != snapshot
                or (
                    callable(has_staged_writes)
                    and bool(has_staged_writes())
                )
            ):
                self._persist_or_restore(snapshot)
            return award
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise

    def _acknowledge_current_revlog(self, revlog_id: int) -> None:
        """Persist a newly observed revlog alias without double-counting it."""

        normalized = max(0, int(revlog_id))
        processed = self.state.processed_revlog_ids
        index = bisect_left(processed, normalized)
        if (
            normalized > self.state.processed_revlog_floor
            and (index >= len(processed) or processed[index] != normalized)
        ):
            if len(processed) >= MAX_PROCESSED_REVLOG_IDS:
                raise RuntimeError(
                    "The current scheduler day exceeded Garden's review-history safety bound."
                )
            insort(processed, normalized)
        self.state.last_processed_revlog_id = max(
            self.state.last_processed_revlog_id,
            normalized,
        )

    def _bind_answer_lineage(self, revlog_id: int, lineage_id: str) -> None:
        """Persist an alias and retire a satisfied explicit reanswer hint."""

        normalized = max(0, int(revlog_id))
        lineage = str(lineage_id)
        if normalized <= 0 or not lineage:
            return
        stager = getattr(self.storage, "stage_answer_lineage_alias", None)
        if callable(stager):
            stager(normalized, lineage)
        else:
            self.state.answer_lineage_bindings[str(normalized)] = lineage
        floor_resolver = getattr(
            self.storage, "reanswer_floor_for_lineage", None
        )
        hinted_floor = (
            floor_resolver(lineage)
            if callable(floor_resolver)
            else self.state.pending_reanswer_lineages.get(lineage)
        )
        if hinted_floor is not None and normalized >= int(hinted_floor):
            clearer = getattr(self.storage, "clear_reanswer_hint", None)
            if callable(clearer):
                clearer(lineage)
            else:
                self.state.pending_reanswer_lineages.pop(lineage, None)

    def _answer_consumed(self, answer_key: str) -> bool:
        resolver = getattr(self.storage, "answer_consumed", None)
        if callable(resolver):
            return bool(resolver(answer_key))
        return answer_key in self.state.processed_answer_keys

    def _record_answer_consumption(
        self,
        answer_key: str,
        *,
        scheduler_day: str,
        lineage_id: str,
        revlog_id: int,
    ) -> None:
        stager = getattr(self.storage, "stage_answer_consumption", None)
        if callable(stager):
            stager(
                answer_key,
                scheduler_day=scheduler_day,
                lineage_key=lineage_id,
                first_revlog_id=revlog_id,
            )
            return
        if answer_key not in self.state.processed_answer_keys:
            self.state.processed_answer_keys.append(answer_key)

    def record_review_undo(self, *, undo_at_ms: int | None = None) -> bool:
        """Mark the just-removed review lineage for one deterministic reanswer.

        The Anki undo hook runs after the revlog row disappears. Comparing the
        durable alias authority with current eligible history identifies the
        orphan. Its wall-clock floor distinguishes a later reanswer from an
        older row that arrives through sync in the meantime.
        """

        resolver = getattr(self.storage, "load_eligible_review_history", None)
        if not callable(resolver):
            return False
        snapshot = self._state_snapshot()
        try:
            history_snapshot = resolver()
            current_revlog_ids = {
                int(entry.revlog_id) for entry in history_snapshot.entries
            }
            bindings_resolver = getattr(
                self.storage, "all_answer_lineage_bindings", None
            )
            bindings = (
                bindings_resolver()
                if callable(bindings_resolver)
                else dict(self.state.answer_lineage_bindings)
            )
            pending_resolver = getattr(
                self.storage, "pending_reanswer_lineages", None
            )
            pending_reanswers = (
                pending_resolver()
                if callable(pending_resolver)
                else dict(self.state.pending_reanswer_lineages)
            )
            current_lineages = {
                lineage
                for raw_revlog_id, lineage in bindings.items()
                if raw_revlog_id.isdigit()
                and int(raw_revlog_id) in current_revlog_ids
            }
            candidates = [
                (int(raw_revlog_id), lineage)
                for raw_revlog_id, lineage in bindings.items()
                if raw_revlog_id.isdigit()
                and int(raw_revlog_id) not in current_revlog_ids
                and lineage not in current_lineages
                and lineage not in pending_reanswers
            ]
            if candidates:
                removed_revlog_id, lineage = max(
                    candidates, key=lambda item: item[0]
                )
                floor = max(
                    removed_revlog_id + 1,
                    int(self._now_ms() if undo_at_ms is None else undo_at_ms),
                )
                hint_stager = getattr(
                    self.storage, "stage_reanswer_hint", None
                )
                if callable(hint_stager):
                    hint_stager(lineage, floor)
                else:
                    self.state.pending_reanswer_lineages[lineage] = floor
            has_staged_writes = getattr(
                self.storage, "reward_ledger_has_staged_writes", None
            )
            if (
                self.state.to_dict() != snapshot
                or (
                    callable(has_staged_writes)
                    and bool(has_staged_writes())
                )
            ):
                self._persist_or_restore(snapshot)
            return bool(candidates)
        except Exception:
            self._restore_state(snapshot)
            raise

    def _register_review_in_memory(self, payload: Any) -> ReviewAward:
        source = payload if isinstance(payload, dict) else {}
        historical_sync = bool(source.get("historical_sync", False))
        try:
            revlog_id = max(0, int(source.get("revlog_id", 0)))
        except (TypeError, ValueError):
            revlog_id = 0
        if revlog_id <= 0:
            return ReviewAward(
                None,
                0,
                0,
                0,
                0,
                "This card has no stable review record and was not counted.",
            )
        try:
            event_ms = max(0, int(source.get("answered_at_ms", revlog_id)))
        except (TypeError, ValueError):
            event_ms = revlog_id
        lineage_id = str(source.get("answer_identity", "") or "").strip()
        try:
            card_id = (
                int(source.get("card_id"))
                if source.get("card_id") is not None
                else None
            )
        except (TypeError, ValueError):
            card_id = None
        answer_identity = stable_answer_event_identity(
            revlog_id,
            card_id=card_id,
            answered_at_ms=event_ms,
            lineage_id=lineage_id or None,
        )
        answer_key = consumption_id(answer_identity)
        if lineage_id:
            self._bind_answer_lineage(revlog_id, lineage_id)
        if self._answer_consumed(answer_key):
            if not historical_sync:
                # Undo/reanswer can create a new revlog alias for an already
                # consumed lineage. Record that alias so repeated hooks become
                # a cheap ledger hit without granting or rerolling anything.
                self._acknowledge_current_revlog(revlog_id)
            return ReviewAward(
                None, 0, 0, 0, 0, "This card was already counted."
            )
        if not historical_sync:
            processed = self.state.processed_revlog_ids
            index = bisect_left(processed, revlog_id)
            if (
                revlog_id <= self.state.processed_revlog_floor
                or (index < len(processed) and processed[index] == revlog_id)
            ):
                return ReviewAward(None, 0, 0, 0, 0, "This card was already counted.")
            if len(processed) >= MAX_PROCESSED_REVLOG_IDS:
                raise RuntimeError(
                    "The current scheduler day exceeded Garden's review-history safety bound."
                )

        if not self.state.reward_state_initialized:
            # A direct reviewer event can arrive before startup maintenance.
            # Treat that event as the activation boundary; older history still
            # remains ineligible for recurring rewards and Garden Finds.
            if self._pending_reward_activation_ms is None:
                self._pending_reward_activation_ms = event_ms
            else:
                self._pending_reward_activation_ms = min(
                    self._pending_reward_activation_ms,
                    event_ms,
                )
            self.initialize_reward_state(
                activation_ms=self._pending_reward_activation_ms,
                persist=False,
            )
        if not historical_sync and self.state.progression_activation_ms <= 0:
            self._activate_progression_if_ready(event_ms)
        after_activation = event_ms >= max(1, int(self.state.reward_activation_ms))
        scheduler_day = str(
            source.get("scheduler_day") or self.state.daily_stats.day
        )
        try:
            date.fromisoformat(scheduler_day)
        except (TypeError, ValueError):
            scheduler_day = self.state.daily_stats.day
        if after_activation:
            # Consumption is staged before any Find outcome so the database
            # can enforce their foreign-key relationship in the same atomic
            # commit. The surrounding engine checkpoint rolls both back if
            # any later reward mutation fails.
            self._record_answer_consumption(
                answer_key,
                scheduler_day=scheduler_day,
                lineage_id=lineage_id,
                revlog_id=revlog_id,
            )
        correlation_id = str(
            source.get("correlation_id") or f"answer:{answer_key}"
        )
        receipt_capture: list[RewardReceipt] = []
        self._active_reward_receipt_capture = receipt_capture
        unlocked_before = {
            achievement_id
            for achievement_id, achievement in self.state.achievements.items()
            if achievement.unlocked
        }
        queue, ease, _deck_id, _difficulty, lapse_count = self._normalized_review(source)
        stats = self.state.daily_stats
        first_review_today = stats.reviewed == 0
        previous_streak = self.state.streak_days
        previous_reviews = self.state.total_reviews
        progression_eligible = bool(
            after_activation
            and self.state.starter_selection_complete
            and self.state.progression_activation_ms > 0
            and event_ms >= int(self.state.progression_activation_ms)
        )
        daily_activity_event_key = f"daily_activity:{scheduler_day}"
        explicit_streak: int | None = None
        if source.get("streak_days") is not None:
            try:
                explicit_streak = max(0, int(source.get("streak_days")))
            except (TypeError, ValueError):
                explicit_streak = None
        if first_review_today and not historical_sync:
            self._start_study_day(
                correlation_id=correlation_id,
                allow_recurring_rewards=progression_eligible,
            )
        elif (
            historical_sync
            and bool(source.get("first_answer_of_day", False))
            and explicit_streak is not None
        ):
            self._apply_streak_rewards(
                scheduler_day=scheduler_day,
                correlation_id=correlation_id,
                streak_days=explicit_streak,
                allow_recurring_reward=progression_eligible,
            )
        if progression_eligible and not self._reward_applied(
            daily_activity_event_key
        ):
            # Activation or a sync can occur after earlier answers from this
            # Anki day were reconstructed without recurring rewards. The first
            # post-activation eligible answer still starts today's recurring
            # reward cadence, including a seventh-day cycle when applicable.
            self._apply_streak_rewards(
                scheduler_day=scheduler_day,
                correlation_id=correlation_id,
                streak_days=explicit_streak,
                allow_recurring_reward=True,
            )
        stats.reviewed += 1
        if hasattr(self.state, "daily_completion"):
            self.state.daily_completion.scheduler_day = scheduler_day
            self.state.daily_completion.cards_completed_today = stats.reviewed
        self.state.total_reviews += 1
        is_correct = ease > 1
        if is_correct:
            stats.correct += 1
            self.state.total_correct += 1
            if lapse_count > 0:
                stats.recovered_lapses += 1
        else:
            stats.wrong += 1
            stats.difficult_count += 1
            self.state.total_wrong += 1
        if queue == 0:
            stats.new_count += 1
        elif queue in (1, 3):
            stats.learning_count += 1
        else:
            stats.review_count += 1

        history_counted = bool(source.get("history_counted", False)) or (
            revlog_id <= int(self.state.achievement_history_high_water_revlog_id)
        )
        if not history_counted:
            self.state.lifetime_eligible_answers += 1
            self.state.current_non_again_run = (
                self.state.current_non_again_run + 1 if is_correct else 0
            )
        plant = self._active_plant_at(event_ms)
        if progression_eligible:
            self._ensure_daily_economy_snapshot(
                scheduler_day,
                historical_sync=historical_sync,
                event_ms=event_ms,
            )
            self._grant_reward_bundle(
                daily_activity_event_key,
                source="first_eligible_answer",
                source_id=scheduler_day,
                reason="First card of the Anki day",
                scheduler_day=scheduler_day,
                correlation_id=correlation_id,
                coins=self.DAILY_ACTIVITY_COINS,
                title="Daily activity reward",
            )
            award = self._award_review_growth(
                plant,
                event_ms,
                streak_days=explicit_streak,
                answer_number=source.get("day_answer_number"),
                environment_growth_known=True,
            )
            decoration = award.decoration_result
            if decoration.trigger_reached and (
                decoration.decoration_growth_awarded_units
                or decoration.direct_growth_awarded_units
            ):
                item = GARDEN_FEATURE_CATALOG.get(decoration.active_bonus_id)
                awarded_units = (
                    decoration.decoration_growth_awarded_units
                    or decoration.direct_growth_awarded_units
                )
                amount_text = (
                    f"+{awarded_units // GROWTH_UNITS_PER_POINT} Growth"
                    if awarded_units % GROWTH_UNITS_PER_POINT == 0 else
                    f"+{awarded_units / GROWTH_UNITS_PER_POINT:g} Growth"
                )
                self._queue_feedback(
                    f"{correlation_id}:garden-decoration",
                    "garden_feature",
                    amount_text,
                    plant.plant_id if plant is not None else "",
                    title=item.name.upper() if item is not None else "GARDEN BONUS",
                    asset_category="garden_features",
                    asset_key=f"garden_feature_{decoration.active_bonus_id}",
                    amount=max(0, awarded_units // GROWTH_UNITS_PER_POINT),
                    correlation_id=correlation_id,
                )
        else:
            paused_reason = (
                "Choose an unfinished plant to nurture to resume Growth."
                if self.state.starter_selection_complete
                and int(self.state.garden_setup_version) >= 1
                else "Complete Garden setup before card rewards begin."
            )
            award = ReviewAward(
                plant.plant_id if plant is not None else None,
                0,
                0,
                0,
                self.current_streak_bonus_percent(),
                paused_reason,
            )
        # Attribute milestones crossed by this card to its original target.
        self._record_shared_memories(previous_reviews, previous_streak, plant=plant)
        finds_eligible = bool(
            progression_eligible
            and event_ms >= max(1, int(self.state.garden_find_activation_ms))
        )
        if finds_eligible:
            self._resolve_garden_finds(
                answer_identity,
                answer_key=answer_key,
                scheduler_day=scheduler_day,
                plant=self.active_plant(),
                correlation_id=correlation_id,
            )
        self._update_achievements(correlation_id=correlation_id)
        if not historical_sync:
            self._acknowledge_current_revlog(revlog_id)
        new_receipts = tuple(receipt_capture)
        self._active_reward_receipt_capture = None
        new_achievement_ids = tuple(
            achievement_id
            for achievement_id, achievement in self.state.achievements.items()
            if achievement.unlocked and achievement_id not in unlocked_before
        )
        if new_receipts and bool(source.get("emit_feedback", True)):
            self._queue_reward_feedback(
                correlation_id,
                new_receipts,
                achievement_ids=new_achievement_ids,
                plant_id=plant.plant_id if plant is not None else None,
            )
        reward_event_keys = tuple(dict.fromkeys(
            receipt.event_key for receipt in new_receipts
        ))
        garden_find_ids = tuple(dict.fromkeys(
            receipt.source_id
            for receipt in new_receipts
            if receipt.source in {
                "garden_find",
                "standard_find",
                "garden_find_environment",
            }
        ))
        produced_units = sum((
            max(0, int(award.applied_growth_units)),
            max(0, int(award.stored_growth_units)),
            max(0, int(award.landmark_growth_units)),
            max(0, int(award.mastery_growth_units)),
            max(0, int(award.legacy_growth_units)),
        ))
        if produced_units:
            aggregates = self.state.lifetime_economy_aggregates
            aggregates.growth_generated_units += produced_units
            aggregates.growth_applied_to_plants_units += max(
                0, int(award.applied_growth_units)
            )
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"answer-growth:{answer_key}",
                event_kind="answer_growth",
                source_id="answer_growth",
                scheduler_day=scheduler_day,
                occurred_at=utc_now_iso(),
                growth_earned_units=produced_units,
                growth_flow_kind="generated",
                growth_generated_units=produced_units,
                growth_applied_to_plants_units=max(
                    0, int(award.applied_growth_units)
                ),
                growth_routed_to_storage_units_lifetime=max(
                    0, int(award.stored_growth_units)
                ),
                stored_growth_balance_delta_units=max(
                    0, int(award.stored_growth_units)
                ),
                growth_contributed_to_landmarks_units=max(
                    0, int(award.landmark_growth_units)
                ),
                growth_contributed_to_mastery_units=max(
                    0, int(award.mastery_growth_units)
                ),
                growth_contributed_to_legacy_units=max(
                    0, int(award.legacy_growth_units)
                ),
                metric_deltas=_project_allocation_metric_deltas(
                    award.project_allocations
                ),
            ))
        return replace(
            award,
            correlation_id=correlation_id,
            reward_event_keys=reward_event_keys,
            garden_find_ids=garden_find_ids,
            achievement_ids=new_achievement_ids,
        )

    def _start_study_day(
        self,
        *,
        correlation_id: str = "",
        allow_recurring_rewards: bool = True,
    ) -> None:
        today = date.fromisoformat(self.state.daily_stats.day)
        try:
            last = date.fromisoformat(self.state.last_active_day)
        except (TypeError, ValueError):
            last = today - timedelta(days=2)
        day_gap = (today - last).days
        if day_gap == 0:
            # A retrospective startup reconciliation may already include the
            # answer Anki just committed to revlog. Do not collapse that streak
            # when Garden processes the same answer into today's detail stats.
            self.state.streak_days = max(1, self.state.streak_days)
        else:
            self.state.streak_days = self.state.streak_days + 1 if day_gap == 1 else 1
        self.state.last_active_day = today.isoformat()
        self._apply_streak_rewards(
            scheduler_day=today.isoformat(),
            correlation_id=correlation_id,
            allow_recurring_reward=allow_recurring_rewards,
        )

    @staticmethod
    def _reward_bundle_description(bundle: RewardBundle) -> str:
        parts: list[str] = []
        if bundle.permanent_growth_percent:
            parts.append(f"Total permanent Growth bonus: +{bundle.permanent_growth_percent}%")
        if bundle.coins:
            parts.append(_garden_coin_amount(bundle.coins, signed=True))
        if bundle.small_growth_charges:
            parts.append(
                f"+{bundle.small_growth_charges} Small Growth Charge"
                + ("s" if bundle.small_growth_charges != 1 else "")
            )
        if bundle.standard_growth_charges:
            parts.append(
                f"+{bundle.standard_growth_charges} Standard Growth Charge"
                + ("s" if bundle.standard_growth_charges != 1 else "")
            )
        if bundle.grand_growth_charges:
            parts.append(
                f"+{bundle.grand_growth_charges} Grand Growth Charge"
                + ("s" if bundle.grand_growth_charges != 1 else "")
            )
        for bed_number in bundle.bed_unlocks:
            parts.append(f"Bed {bed_number} unlocked")
        for cosmetic_id in bundle.cosmetic_ids:
            parts.append(
                "+" + cosmetic_id.replace("_", " ").title()
            )
        return " and ".join(parts) if parts else "Badge only"

    def _unlock_achievement(
        self,
        achievement_id: str,
        *,
        completion_day: str,
        correlation_id: str,
        historical: bool = False,
    ) -> bool:
        definition = ACHIEVEMENTS_BY_ID.get(str(achievement_id))
        achievement = self.state.achievements.get(str(achievement_id))
        if definition is None or achievement is None or achievement.unlocked:
            return False
        event_key = f"achievement:{definition.achievement_id}"
        self._grant_reward_bundle(
            event_key,
            source="achievement",
            source_id=definition.achievement_id,
            reason=(milestone_unlocked_text(definition.achievement_id)
                    if definition.reward.bed_unlocks else f"Achievement: {definition.name}"),
            scheduler_day=completion_day,
            correlation_id=correlation_id,
            coins=definition.reward.coins,
            inventory_items=dict(definition.reward.inventory_items),
            title=(milestone_unlocked_text(definition.achievement_id)
                   if definition.reward.bed_unlocks else definition.name),
            description=definition.description,
        )
        for bed_number in definition.reward.bed_unlocks:
            if bed_number not in self.state.earned_bed_unlocks:
                self.state.earned_bed_unlocks.append(bed_number)
            self.state.unlocked_slots = max(
                int(self.state.unlocked_slots),
                min(MAX_GARDEN_SLOTS, int(bed_number)),
            )
        if definition.reward.cosmetic_ids:
            owned_cosmetics = self.state.inventory.setdefault("cosmetics", [])
            for cosmetic_id in definition.reward.cosmetic_ids:
                if cosmetic_id not in owned_cosmetics:
                    owned_cosmetics.append(cosmetic_id)
        now = utc_now_iso()
        achievement.unlocked = True
        achievement.progress = 1.0
        achievement.unlocked_at = (
            f"{completion_day}T00:00:00+00:00" if historical else now
        )
        achievement.rewarded_at = now
        achievement.reward_event_key = event_key
        achievement.historical_backfill = bool(historical)
        trophy = TROPHY_BY_ACHIEVEMENT.get(str(achievement_id))
        if trophy is not None:
            self.state.trophy_activation_ms.setdefault(
                str(trophy.cosmetic_id), max(1, self._now_ms())
            )
        return True

    def _apply_streak_rewards(
        self,
        *,
        scheduler_day: str,
        correlation_id: str,
        streak_days: int | None = None,
        allow_recurring_reward: bool = True,
    ) -> None:
        days = max(0, int(self.state.streak_days if streak_days is None else streak_days))
        for definition in STREAK_ACHIEVEMENTS:
            if days >= definition.progress_target:
                self._unlock_achievement(
                    definition.achievement_id,
                    completion_day=scheduler_day,
                    correlation_id=correlation_id,
                )

    @staticmethod
    def _normalized_review(payload: Any) -> tuple[int, int, Optional[int], float, int]:
        source = payload if isinstance(payload, dict) else {}
        try:
            queue = int(source.get("queue", 2))
        except (TypeError, ValueError):
            queue = 2
        try:
            ease = max(1, min(4, int(source.get("ease", 1))))
        except (TypeError, ValueError):
            ease = 1
        raw_deck_id = source.get("deck_id")
        try:
            deck_id = int(raw_deck_id) if raw_deck_id is not None else None
        except (TypeError, ValueError):
            deck_id = None
        try:
            difficulty = max(0.1, min(1.0, float(source.get("difficulty", 0.4))))
        except (TypeError, ValueError):
            difficulty = 0.4
        try:
            lapse_count = max(0, min(100, int(source.get("lapse_count", 0))))
        except (TypeError, ValueError):
            lapse_count = 0
        return queue, ease, deck_id, difficulty, lapse_count

    def _active_plant_at(self, event_ms: int) -> Plant | None:
        periods = sorted(
            (
                period
                for period in self.state.active_plant_periods
                if period.started_at_ms <= event_ms
            ),
            key=lambda period: (period.started_at_ms, period.day),
        )
        if periods:
            plant_id = periods[-1].plant_id
        else:
            # An empty timeline or an event before its first target must fail
            # closed. Valid progression activation always creates an anchor.
            return None
        plant = next((item for item in self.state.plants if item.plant_id == plant_id), None)
        return plant

    def equipped_environment(self, kind: str) -> CatalogItem:
        if str(kind) in {"garden_feature", "weather"}:
            return GARDEN_FEATURE_CATALOG.get(
                self.active_garden_feature_id(),
                GARDEN_FEATURE_CATALOG[DEFAULT_GARDEN_FEATURE_ID],
            )
        return SCENERY_CATALOG.get(
            self.locked_environment_id("scenery"),
            SCENERY_CATALOG[DEFAULT_SCENERY_ID],
        )

    def locked_environment_id(self, kind: str) -> str:
        """Compatibility name for the equipped item's effect; never day-locked."""
        if str(kind) in {"garden_feature", "weather"}:
            return self.active_garden_feature_id()
        item_id = (
            self._reward_equipment[1] if self._reward_equipment is not None
            else self.state.loadout.display_scenery_id
        )
        return item_id if item_id in SCENERY_CATALOG else DEFAULT_SCENERY_ID

    def begin_review_session(self) -> str:
        self.rollover_if_needed()
        return self.active_garden_feature_id()

    def end_review_session(self) -> None:
        """Compatibility hook; equipment is never frozen for a session."""

    def active_garden_feature_id(self) -> str:
        item_id = (
            self._reward_equipment[0] if self._reward_equipment is not None
            else self.state.loadout.active_garden_bonus_id
        )
        return item_id if item_id in GARDEN_FEATURE_CATALOG else DEFAULT_GARDEN_FEATURE_ID

    def _lock_daily_loadout(self, *, event_ms: int | None = None) -> bool:
        """Establish daily equipment metadata."""
        existing = self.state.daily_economy_snapshot
        self._ensure_daily_economy_snapshot(
            self.state.daily_stats.day, historical_sync=False,
            event_ms=max(1, int(event_ms or self._now_ms())),
        )
        return existing is None

    def _lock_scenery_loadout(self, *, event_ms: int | None = None) -> bool:
        """Compatibility hook; progression actions never lock equipment."""
        return False

    def _apply_queued_loadout_for_day(self, scheduler_day: str) -> None:
        """Reset daily progress, without changing equipment."""
        self.state.watering_station_progress = self.state.watering_station_progress_by_day.get(
            scheduler_day, 0
        )
        self.state.daily_loadout = DailyLoadoutSchedule()

    def owns_environment(self, kind: str, item_id: str) -> bool:
        if str(kind) in {"garden_feature", "weather"}:
            return canonical_garden_feature_id(item_id) in self.state.inventory.get(
                "garden_features", []
            )
        return str(item_id) in {
            *self.state.inventory.get("backgrounds", []),
            *self.state.inventory.get("scenery", []),
        }

    def garden_decoration_obtained_at(self, item_id: str) -> str | None:
        """Project an actual acquisition record without inventing migration dates."""
        item_id = canonical_garden_feature_id(item_id)
        if not self.owns_environment("garden_feature", item_id):
            return None
        resolver = getattr(self.storage, "first_item_acquisition_at", None)
        recorded = resolver(item_id) if callable(resolver) else None
        candidates = [recorded] if recorded else []
        candidates.extend(
            request.occurred_at for request in self.state.completed_purchase_requests
            if request.outcome.success and request.outcome.item_id == item_id
        )
        candidates.extend(
            receipt.occurred_at for receipt in self.state.recent_reward_receipts
            if receipt.reward_type == "environment_item" and receipt.item_id == item_id
        )
        candidates.extend(
            outcome.occurred_at for outcome in self.state.garden_find_outcomes.values()
            if outcome.status == "hit" and outcome.item_id == item_id
        )
        if item_id == "seedling_sign":
            starter = self.plant_story(self.state.onboarding.starter_plant_id or "")
            if starter is not None:
                candidates.append(starter.planted_on)
        valid = []
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(str(candidate).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    # Date-only starter records are already local garden dates.
                    parsed = parsed.astimezone()
                valid.append((parsed.timestamp(), str(candidate)))
            except (TypeError, ValueError, OverflowError):
                continue
        return min(valid)[1] if valid else None

    def _decoration_progress_spec(self) -> tuple[str, int, int] | None:
        item_id = self.active_garden_feature_id()
        field_name = {"wind_chime": "wind_chime_progress", "watering_station": "watering_station_progress"}.get(item_id)
        if field_name is None:
            return None
        effect = next(effect for effect in GARDEN_FEATURE_CATALOG[item_id].effects
                      if effect.trigger == "eligible_card" and effect.value_kind == "growth")
        return field_name, int(effect.every_nth_card or 1), effect.amount * GROWTH_UNITS_PER_POINT

    def _project_decoration_answer(self, answer_number: int | None = None) -> DecorationResult:
        active_id = self.active_garden_feature_id()
        effect = FEATURE_EFFECT_KEYS[active_id]
        answer_number = max(1, int(answer_number or self.state.daily_stats.reviewed))
        spec = self._decoration_progress_spec()
        if spec is not None:
            field_name, cadence, reward_units = spec
            definition = next(item for item in GARDEN_FEATURE_CATALOG[active_id].effects if item.trigger == "eligible_card")
            before = (
                self.state.watering_station_progress_by_day.get(self.state.daily_stats.day, 0)
                if field_name == "watering_station_progress"
                else max(0, int(getattr(self.state, field_name, 0) or 0))
            )
            if definition.first_cards is not None and answer_number > definition.first_cards:
                return DecorationResult(active_bonus_id=active_id, progress_before=before, progress_after=before)
            # Old counters retain all qualifying answers through a cadence
            # change. Settle their credit once on the next equipped answer.
            awards, remainder = divmod(before + 1, cadence)
            return DecorationResult(
                active_bonus_id=active_id,
                progress_before=before,
                progress_after=remainder,
                trigger_reached=bool(awards),
                decoration_growth_awarded_units=reward_units * awards,
            )
        if effect == "instant_growth_every_5_plus_3_nurtured":
            before = max(0, int(self.state.firefly_lantern_progress or 0))
            reached = before + 1 >= 5
            return DecorationResult(
                active_bonus_id=active_id,
                progress_before=before,
                progress_after=0 if reached else before + 1,
                trigger_reached=reached,
                direct_growth_awarded_units=300 if reached else 0,
            )
        return DecorationResult(active_bonus_id=active_id)

    def _advance_decoration_answer(self, answer_number: int | None = None) -> DecorationResult:
        result = self._project_decoration_answer(answer_number)
        spec = self._decoration_progress_spec()
        if spec is not None:
            if spec[0] == "watering_station_progress":
                self.state.watering_station_progress_by_day[self.state.daily_stats.day] = result.progress_after
                if self.state.daily_stats.day == self._scheduler_day():
                    self.state.watering_station_progress = result.progress_after
            else:
                setattr(self.state, spec[0], result.progress_after)
        if result.active_bonus_id == "firefly_lantern":
            self.state.firefly_lantern_progress = result.progress_after
        if result.prism_growth_banked_units:
            self.state.prism_pending_growth_units = (
                max(0, int(self.state.prism_pending_growth_units))
                + result.prism_growth_banked_units
            )
        return result

    def _garden_feature_review_growth(self, answer_number: int) -> int:
        """Compatibility projection for callers that still request points."""

        return (
            self._project_decoration_answer(answer_number).decoration_growth_awarded_units
            // GROWTH_UNITS_PER_POINT
        )

    def _weather_review_growth(self, answer_number: int) -> int:
        """Legacy method name; calculations use the Garden Decoration registry."""

        return self._garden_feature_review_growth(answer_number)

    def _scenery_review_growth(self, answer_number: int) -> int:
        scenery = self.locked_environment_id("scenery")
        if scenery == "spring" and answer_number <= 20:
            return 2
        if scenery == "summer" and answer_number <= 120 and answer_number % 2 == 0:
            return 1
        if scenery == "rainbow_horizon" and answer_number <= 75:
            return 1
        if scenery == "eclipse" and answer_number <= 125:
            return 1
        return 0

    @staticmethod
    def _plant_growth_units(plant: Plant) -> int:
        return (
            max(0, int(plant.growth_points)) * GROWTH_UNITS_PER_POINT
            + max(0, min(
                GROWTH_UNITS_PER_POINT - 1,
                int(getattr(plant, "growth_remainder_units", 0) or 0),
            ))
        )

    @staticmethod
    def _set_plant_growth_units(plant: Plant, units: int) -> None:
        maximum = GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT
        whole, remainder = divmod(
            max(0, min(maximum, int(units))),
            GROWTH_UNITS_PER_POINT,
        )
        plant.growth_points = whole
        if hasattr(plant, "growth_remainder_units"):
            plant.growth_remainder_units = (
                0 if whole >= GROWTH_THRESHOLDS[-1] else remainder
            )

    def _growth_route_candidates(self, intended: Plant | None) -> list[Plant]:
        planted = sorted(
            (
                candidate
                for candidate in self.state.plants
                if candidate.planted
            ),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        )
        if intended is None:
            return []
        if intended not in planted:
            return []
        start = planted.index(intended)
        ordered = (
            planted[start + 1:] + planted[:start]
            if intended.fully_grown
            else planted[start:] + planted[:start]
        )
        return [candidate for candidate in ordered if not candidate.fully_grown]

    def _next_planted_unfinished(self, after: Plant | None) -> Plant | None:
        planted = sorted(
            (candidate for candidate in self.state.plants if candidate.planted),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        )
        if not planted:
            return None
        if after not in planted:
            return next((item for item in planted if not item.fully_grown), None)
        start = planted.index(after)
        ordered = planted[start + 1:] + planted[:start]
        return next((item for item in ordered if not item.fully_grown), None)

    def _shared_growth_plan(
        self,
        target: Plant | None,
        award_units: int,
        *,
        numerator: int = 1,
        denominator: int = 10,
    ) -> tuple[tuple[Plant, int], ...]:
        """Create one exact effective-rate lane for every other planted bed.

        A Full Bloom bed still owns its lane. The normal lane router skips the
        full intended recipient and carries that complete lane forward in
        deterministic bed order, rather than pooling and redistributing it.
        """

        if target is None or not target.planted:
            return ()
        planted = sorted(
            (candidate for candidate in self.state.plants if candidate.planted),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        )
        if target not in planted:
            return ()
        other_plants = [candidate for candidate in planted if candidate is not target]
        if not other_plants:
            return ()
        share_units = max(0, int(award_units)) * numerator // denominator
        if share_units <= 0:
            return ()
        return tuple((candidate, share_units) for candidate in other_plants)

    def _shared_growth_anchor(self, target: Plant | None) -> Plant | None:
        """Return the deterministic bed that defines independent Shared lanes.

        Normally the nurtured plant is the anchor. Once every planted bed is
        Full Bloom there is deliberately no unfinished active plant, but the
        occupied beds must keep producing their frozen Shared-lane value for
        long-term projects and Stored Growth. An intentionally deselected
        garden with an unfinished plant does not receive those extra lanes.
        """

        if target is not None and target.planted:
            return target
        planted = sorted(
            (candidate for candidate in self.state.plants if candidate.planted),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        )
        if planted and all(candidate.fully_grown for candidate in planted):
            return planted[0]
        return None

    def _landmark_unlocked(self) -> bool:
        return any(plant.fully_grown for plant in self.state.plants)

    def _landmark_snapshot(self) -> LandmarkProjectSnapshot:
        project = self.state.garden_project
        claimed = max(0, min(
            len(LANDMARK_ORDER), int(project.landmark_highest_claimed_tier)
        ))
        next_id = LANDMARK_ORDER[claimed] if claimed < len(LANDMARK_ORDER) else ""
        previous_floor = (
            LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
                LANDMARK_ORDER[claimed - 1]
            ]
            if claimed else 0
        )
        next_threshold = (
            LANDMARK_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[next_id]
            if next_id else previous_floor
        )
        contribution = min(
            max(0, next_threshold - previous_floor),
            max(0, int(project.landmark_growth_units_funded) - previous_floor),
        )
        selected = str(project.selected_project_id or "")
        if not selected and next_id and contribution:
            # Schema-26 callers can finish an already funded cumulative tier
            # without re-contributing or discarding prefunded later tiers.
            selected = next_id
        return landmark_snapshot(
            selected_landmark_id=selected,
            contributed_growth_units=(contribution if selected else 0),
            ready_to_complete=bool(
                selected and contribution == next_threshold - previous_floor
            ),
            completed_landmark_ids=project.completed_project_ids,
            displayed_landmark_id=project.displayed_project_id,
        )

    def _apply_landmark_snapshot(
        self,
        snapshot: LandmarkProjectSnapshot,
    ) -> None:
        project = self.state.garden_project
        existing_funded = max(
            0, int(project.landmark_growth_units_funded)
        )
        project.selected_project_id = snapshot.selected_landmark_id
        project.contributed_growth_units = snapshot.contributed_growth_units
        project.ready_to_complete = snapshot.ready_to_complete
        project.completed_project_ids = list(snapshot.completed_landmark_ids)
        project.displayed_project_id = snapshot.displayed_landmark_id
        claimed = len(snapshot.completed_landmark_ids)
        claimed_floor = (
            sum(
                LANDMARK_GROWTH_COST_UNITS[item_id]
                for item_id in LANDMARK_ORDER[:claimed]
            )
        )
        project.landmark_highest_claimed_tier = claimed
        project.landmark_growth_units_funded = min(
            LANDMARK_MAX_GROWTH_UNITS,
            max(
                existing_funded,
                claimed_floor + max(0, int(snapshot.contributed_growth_units)),
            ),
        )
        project.displayed_landmark_tier_id = snapshot.displayed_landmark_id

    def _mastery_snapshot(self) -> MasterySnapshot:
        return mastery_snapshot(
            self.state.cultivation_mastery.highest_rank_by_species
        )

    def _apply_mastery_snapshot(self, snapshot: MasterySnapshot) -> None:
        claimed = dict(snapshot.highest_rank_by_species)
        mastery = self.state.cultivation_mastery
        mastery.highest_claimed_rank_by_species = claimed
        mastery.highest_rank_by_species = mastery.highest_claimed_rank_by_species
        for species_id, rank_id in claimed.items():
            rank_index = tuple(MASTERY_RANK_BY_ID).index(rank_id)
            floor = sum(
                MASTERY_GROWTH_COST_UNITS[item_id]
                for item_id in tuple(MASTERY_RANK_BY_ID)[:rank_index + 1]
            )
            mastery.growth_units_funded_by_species[species_id] = max(
                floor,
                max(0, int(
                    mastery.growth_units_funded_by_species.get(species_id, 0)
                )),
            )

    def growth_projects_snapshot(self) -> GrowthProjectsSnapshot:
        """Return the single renderer-neutral long-term-project projection."""

        active_target: GrowthTargetRef | None = None
        target_type = str(self.state.active_growth_target_type or "")
        target_id = str(self.state.active_growth_target_id or "")
        if target_type and target_id:
            try:
                active_target = GrowthTargetRef(
                    GrowthTargetType(target_type), target_id
                )
            except (TypeError, ValueError):
                active_target = None
        full_bloom_species = tuple(dict.fromkeys(
            plant.species
            for plant in self.state.plants
            if plant.fully_grown
            and plant.species in CURRENT_CATALOG_SPECIES_ORDER
        ))
        return build_growth_projects_snapshot(
            state_revision=max(
                0, int(getattr(self.storage, "_ledger_revision", 0) or 0)
            ),
            stored_balance_units=self.state.stored_growth_balance_units,
            wallet_balance_coins=max(0, int(self.state.currency_balance)),
            full_bloom_species=full_bloom_species,
            active_target=active_target,
            active_target_activation_identity=str(
                self.state.active_growth_target_activation_identity or ""
            ),
            landmark_growth_units_funded=max(
                0, int(self.state.garden_project.landmark_growth_units_funded)
            ),
            landmark_highest_claimed_tier=max(
                0, int(self.state.garden_project.landmark_highest_claimed_tier)
            ),
            mastery_growth_units_funded_by_species=dict(
                self.state.cultivation_mastery.growth_units_funded_by_species
            ),
            mastery_highest_claimed_rank_by_species=dict(
                self.state.cultivation_mastery.highest_claimed_rank_by_species
            ),
            garden_legacy_level=max(0, int(self.state.garden_legacy_level)),
            garden_legacy_progress_units=max(
                0, int(self.state.garden_legacy_progress_units)
            ),
        )

    def _apply_growth_projects_snapshot(
        self,
        snapshot: GrowthProjectsSnapshot,
    ) -> None:
        active = snapshot.active_target
        self.state.active_growth_target_type = (
            active.target_type.value if active is not None else ""
        )
        self.state.active_growth_target_id = (
            active.target_id if active is not None else ""
        )
        self.state.active_growth_target_activation_identity = (
            snapshot.active_target_activation_identity if active is not None else ""
        )
        self.state.stored_growth_balance_units = snapshot.stored_balance_units
        self.state.currency_balance = snapshot.wallet_balance_coins
        project = self.state.garden_project
        project.landmark_growth_units_funded = (
            snapshot.landmark_track.growth_units_funded
        )
        project.landmark_highest_claimed_tier = sum(
            1 for row in snapshot.landmark_track.tiers if row.claimed
        )
        project.completed_project_ids = list(
            LANDMARK_ORDER[:project.landmark_highest_claimed_tier]
        )
        if (
            active is not None
            and active.target_type is GrowthTargetType.LANDMARK
            and project.landmark_highest_claimed_tier < len(LANDMARK_ORDER)
        ):
            project.selected_project_id = LANDMARK_ORDER[
                project.landmark_highest_claimed_tier
            ]
        else:
            project.selected_project_id = ""
        if project.landmark_highest_claimed_tier:
            previous_floor = snapshot.landmark_track.tiers[
                project.landmark_highest_claimed_tier - 1
            ].cumulative_growth_threshold_units
        else:
            previous_floor = 0
        if project.landmark_highest_claimed_tier < len(LANDMARK_ORDER):
            next_row = snapshot.landmark_track.tiers[
                project.landmark_highest_claimed_tier
            ]
            project.contributed_growth_units = min(
                max(0, snapshot.landmark_track.growth_units_funded - previous_floor),
                max(0, next_row.cumulative_growth_threshold_units - previous_floor),
            )
            project.ready_to_complete = next_row.funded
        else:
            project.contributed_growth_units = 0
            project.ready_to_complete = False
        project.displayed_project_id = project.displayed_landmark_tier_id
        project.auto_contribute = False

        mastery_funding = {
            species_id: track.growth_units_funded
            for species_id, track in snapshot.mastery_tracks_by_species
        }
        mastery_claims = {
            species_id: track.highest_claimed_id
            for species_id, track in snapshot.mastery_tracks_by_species
            if track.highest_claimed_id
        }
        self.state.cultivation_mastery.growth_units_funded_by_species = (
            mastery_funding
        )
        self.state.cultivation_mastery.highest_claimed_rank_by_species = (
            mastery_claims
        )
        self.state.cultivation_mastery.highest_rank_by_species = (
            self.state.cultivation_mastery.highest_claimed_rank_by_species
        )
        self.state.garden_legacy_level = snapshot.legacy_track.level
        self.state.garden_legacy_progress_units = (
            snapshot.legacy_track.level_progress_units
        )

    def quote_growth_project(
        self,
        request: GrowthProjectRequest,
    ) -> GrowthProjectQuote:
        quote = self._available_growth_project_quote(
            quote_growth_project_request(self.growth_projects_snapshot(), request)
        )
        if getattr(self.storage, "runtime_pending", False):
            return replace(quote, disposition=ProgressionDisposition.NOT_READY, can_apply=False,
                           blocking_reason=RUNTIME_WAIT_MESSAGE)
        return quote

    @staticmethod
    def _available_growth_project_quote(quote: GrowthProjectQuote) -> GrowthProjectQuote:
        if growth_target_enabled(quote.target.target_type):
            return quote
        return replace(
            quote,
            quote_fingerprint=hashlib.sha256(
                f"{quote.quote_fingerprint}:unavailable".encode("utf-8")
            ).hexdigest(),
            disposition=ProgressionDisposition.NOT_READY,
            can_apply=False,
            blocking_reason="This Growth project is unavailable.",
            stored_balance_after_units=quote.stored_balance_before_units,
            project_funded_after_units=quote.project_funded_before_units,
            accepted_growth_units=0,
            crossed_threshold_ids=(),
            coin_cost=0,
            wallet_balance_after_coins=quote.wallet_balance_before_coins,
        )

    def confirm_growth_project(
        self,
        request: GrowthProjectRequest,
        confirmation: GrowthProjectConfirmation,
    ) -> GrowthProjectOutcome:
        """Freshly revalidate and atomically commit one project operation."""

        if not isinstance(request, GrowthProjectRequest):
            raise TypeError("request must be a GrowthProjectRequest")
        if not isinstance(confirmation, GrowthProjectConfirmation):
            raise TypeError("confirmation must be a GrowthProjectConfirmation")
        if (
            confirmation.request_id != request.request_id
            or confirmation.request_fingerprint != request.fingerprint
        ):
            raise ValueError("Growth project confirmation does not match request")
        lookup = getattr(self.storage, "idempotency_record", None)
        existing = (
            lookup("growth_project", request.request_id)
            if callable(lookup) else None
        )
        if existing is not None:
            if existing.request_fingerprint != request.fingerprint:
                raise ValueError("That Growth project request ID was already used.")
            # Replay the exact durable outcome.  Returning a reconstructed
            # no-op would make retry behavior depend on today's mutable state.
            return growth_project_outcome_from_dict(existing.outcome)
        fresh = self.growth_projects_snapshot()
        quote = self._available_growth_project_quote(
            quote_growth_project_request(fresh, request)
        )
        stale = quote.quote_fingerprint != confirmation.quote_fingerprint
        if stale or not quote.can_apply:
            return GrowthProjectOutcome(
                request.request_id,
                request.fingerprint,
                quote.quote_fingerprint,
                ProgressionDisposition.NO_CHANGE if stale else quote.disposition,
                False,
                0,
                0,
                None,
                fresh,
                "The Garden changed. Refresh this quote before continuing."
                if stale else quote.blocking_reason,
                ledger_identity=f"growth-project:{request.request_id}",
                state_revision_before=fresh.state_revision,
                state_revision_after=fresh.state_revision,
                catalog_digest=quote.catalog_digest,
            )
        outcome = project_growth_project_request(fresh, request)
        if not outcome.applied:
            return outcome
        state_before = self._state_snapshot()
        occurred_at = utc_now_iso()
        try:
            if outcome.coins_spent:
                if not self._debit_currency(
                    f"growth-project:{request.request_id}",
                    "Long-term garden project",
                    outcome.coins_spent,
                ):
                    raise RuntimeError("Garden Coin balance changed during claim")
            self._apply_growth_projects_snapshot(outcome.snapshot)
            allocation = outcome.allocation
            if allocation is not None:
                aggregates = self.state.lifetime_economy_aggregates
                if allocation.target_type is GrowthTargetType.LANDMARK:
                    aggregates.growth_contributed_to_landmarks_units += allocation.units
                elif allocation.target_type is GrowthTargetType.MASTERY:
                    aggregates.growth_contributed_to_mastery_units += allocation.units
                else:
                    aggregates.growth_contributed_to_legacy_units += allocation.units
            stager = getattr(self.storage, "stage_idempotency_record", None)
            if callable(stager):
                stager(IdempotencyRecord(
                    operation_kind="growth_project",
                    operation_id=request.request_id,
                    request_fingerprint=request.fingerprint,
                    outcome=outcome.to_dict(),
                    occurred_at=occurred_at,
                    scheduler_day=self.state.daily_stats.day,
                ))
            project_target = request.target.target_type
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"growth-project:{request.request_id}",
                event_kind=f"growth_project_{request.action.value}",
                sink_id=request.target.target_id,
                scheduler_day=self.state.daily_stats.day,
                occurred_at=occurred_at,
                coins_spent=outcome.coins_spent,
                growth_flow_kind=(
                    "manual_contribution"
                    if allocation is not None
                    else "claim"
                    if request.action is GrowthProjectAction.CLAIM
                    else ""
                ),
                stored_growth_balance_delta_units=(
                    outcome.stored_balance_delta_units
                ),
                growth_contributed_to_landmarks_units=(
                    allocation.units
                    if allocation is not None
                    and project_target is GrowthTargetType.LANDMARK else 0
                ),
                growth_contributed_to_mastery_units=(
                    allocation.units
                    if allocation is not None
                    and project_target is GrowthTargetType.MASTERY else 0
                ),
                growth_contributed_to_legacy_units=(
                    allocation.units
                    if allocation is not None
                    and project_target is GrowthTargetType.LEGACY else 0
                ),
                growth_spent_on_landmarks=(
                    allocation.units
                    if allocation is not None
                    and project_target is GrowthTargetType.LANDMARK else 0
                ),
                growth_spent_on_mastery=(
                    allocation.units
                    if allocation is not None
                    and project_target is GrowthTargetType.MASTERY else 0
                ),
                item_id=(
                    request.claim_id
                    if request.action is GrowthProjectAction.CLAIM else ""
                ),
                quantity=(
                    1 if request.action is GrowthProjectAction.CLAIM else 0
                ),
                metric_deltas=_project_allocation_metric_deltas(
                    (allocation,) if allocation is not None else ()
                ),
            ))
            self._persist_or_restore(state_before)
            return outcome
        except Exception:
            self._restore_state(state_before)
            raise

    def _garden_legacy_unlocked(self) -> bool:
        mastery = self.state.cultivation_mastery.growth_units_funded_by_species
        return (
            max(0, int(self.state.garden_project.landmark_growth_units_funded))
            >= LANDMARK_MAX_GROWTH_UNITS
            and all(
                max(0, int(mastery.get(species_id, 0)))
                >= MASTERY_MAX_GROWTH_UNITS_PER_SPECIES
                for species_id in CURRENT_CATALOG_SPECIES_ORDER
            )
        )

    def _credit_active_growth_target(
        self,
        units: int,
    ) -> tuple[int, tuple[ProjectGrowthAllocation, ...]]:
        """Credit only final overflow to the acknowledged active project."""

        available = max(0, int(units))
        target_type = str(
            getattr(self.state, "active_growth_target_type", "") or ""
        )
        target_id = str(
            getattr(self.state, "active_growth_target_id", "") or ""
        )
        if (
            available <= 0 or not target_type or not target_id
            or not growth_target_enabled(target_type)
        ):
            return 0, ()
        aggregates = self.state.lifetime_economy_aggregates
        contribution = 0
        canonical_target_id = target_id
        if target_type == "landmark" and target_id in {
            "garden_landmark", *LANDMARK_ORDER
        } and self._landmark_unlocked():
            project = self.state.garden_project
            before = max(0, int(project.landmark_growth_units_funded))
            contribution = min(
                available, max(0, LANDMARK_MAX_GROWTH_UNITS - before)
            )
            if contribution:
                project.landmark_growth_units_funded = before + contribution
                canonical_target_id = "garden_landmark"
                aggregates.growth_contributed_to_landmarks_units += contribution
                self._sync_landmark_compatibility_projection()
        elif target_type == "mastery" and target_id in CURRENT_CATALOG_SPECIES_ORDER:
            eligible = any(
                plant.species == target_id and plant.fully_grown
                for plant in self.state.plants
            )
            if eligible:
                funding = (
                    self.state.cultivation_mastery.growth_units_funded_by_species
                )
                before = max(0, int(funding.get(target_id, 0)))
                contribution = min(
                    available,
                    max(0, MASTERY_MAX_GROWTH_UNITS_PER_SPECIES - before),
                )
                if contribution:
                    funding[target_id] = before + contribution
                    aggregates.growth_contributed_to_mastery_units += contribution
        elif (
            target_type == "legacy"
            and target_id == "garden_legacy"
            and self._garden_legacy_unlocked()
        ):
            contribution = available
            combined = (
                max(0, int(self.state.garden_legacy_progress_units))
                + contribution
            )
            levels, remainder = divmod(
                combined, GARDEN_LEGACY_LEVEL_COST_UNITS
            )
            self.state.garden_legacy_level = (
                max(0, int(self.state.garden_legacy_level)) + levels
            )
            self.state.garden_legacy_progress_units = remainder
            aggregates.growth_contributed_to_legacy_units += contribution
        if contribution <= 0:
            return 0, ()
        return contribution, (
            ProjectGrowthAllocation(
                target_type=GrowthTargetType(target_type),
                target_id=canonical_target_id,
                units=contribution,
            ),
        )

    def _sync_landmark_compatibility_projection(self) -> None:
        """Refresh schema-26 Landmark fields from cumulative authority."""

        project = self.state.garden_project
        claimed = max(0, min(
            len(LANDMARK_ORDER), int(project.landmark_highest_claimed_tier)
        ))
        claimed_ids = list(LANDMARK_ORDER[:claimed])
        claimed_floor = sum(
            LANDMARK_GROWTH_COST_UNITS[item_id]
            for item_id in claimed_ids
        )
        next_id = (
            LANDMARK_ORDER[claimed] if claimed < len(LANDMARK_ORDER) else ""
        )
        next_increment = LANDMARK_GROWTH_COST_UNITS.get(next_id, 0)
        funded = max(0, min(
            LANDMARK_MAX_GROWTH_UNITS,
            int(project.landmark_growth_units_funded),
        ))
        landmark_active = (
            self.state.active_growth_target_type
            == GrowthTargetType.LANDMARK.value
            and self.state.active_growth_target_id == "garden_landmark"
        )
        project.completed_project_ids = claimed_ids
        project.selected_project_id = next_id if landmark_active else ""
        project.contributed_growth_units = min(
            next_increment,
            max(0, funded - claimed_floor),
        )
        project.ready_to_complete = bool(
            next_id and funded >= claimed_floor + next_increment
        )
        project.displayed_project_id = project.displayed_landmark_tier_id

    def _finalize_growth_overflow(
        self,
        units: int,
    ) -> tuple[int, tuple[ProjectGrowthAllocation, ...]]:
        """Route pooled final overflow to a project, then durable storage."""

        remaining = max(0, int(units))
        project_units, allocations = self._credit_active_growth_target(remaining)
        remaining -= project_units
        if remaining:
            self.state.stored_growth_balance_units = (
                self.state.stored_growth_balance_units + remaining
            )
            aggregates = self.state.lifetime_economy_aggregates
            aggregates.growth_routed_to_storage_units_lifetime += remaining
        return remaining, allocations

    def _route_growth_units(
        self,
        intended: Plant | None,
        requested_units: int,
        *,
        role: str,
        transition_source: str,
        event_ms: int,
        finalize_overflow: bool = True,
    ) -> GrowthGrantResult:
        """Conserve one Growth lane across plants, then durable storage."""

        requested = max(0, int(requested_units))
        original_target_id = intended.plant_id if intended is not None else ""
        if requested <= 0:
            return GrowthGrantResult(
                0,
                0,
                0,
                original_target_id=original_target_id,
            )
        active_before = str(self.state.active_plant_id or "")
        remaining = requested
        allocations: list[GrowthAllocation] = []
        for candidate in self._growth_route_candidates(intended):
            if remaining <= 0:
                break
            before_units = self._plant_growth_units(candidate)
            capacity_units = max(
                0,
                GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT - before_units,
            )
            applied = min(remaining, capacity_units)
            if applied <= 0:
                continue
            before_points = int(candidate.growth_points)
            self._set_plant_growth_units(candidate, before_units + applied)
            remaining -= applied
            redirected = candidate.plant_id != original_target_id
            if candidate.fully_grown:
                if not candidate.completed_on:
                    candidate.completed_on = self.state.daily_stats.day
                if not candidate.completed_at_ms:
                    candidate.completed_at_ms = max(1, int(event_ms))
            allocations.append(GrowthAllocation(
                plant_id=candidate.plant_id,
                role=role,
                exact_fifths=0,
                credited_growth=applied // GROWTH_UNITS_PER_POINT,
                requested_units=applied,
                applied_units=applied,
                redirected=redirected,
            ))
            self._record_growth_crossings(
                candidate,
                before_points,
                int(candidate.growth_points),
                source=(
                    "shared_growth"
                    if transition_source == "shared_growth"
                    else "redirected_growth"
                    if redirected
                    else transition_source
                ),
            )
        if finalize_overflow:
            stored, project_allocations = self._finalize_growth_overflow(remaining)
            project_units = remaining - stored
        else:
            stored = remaining
            project_allocations = ()
            project_units = 0

        auto_selected = ""
        active_plant = next(
            (
                candidate
                for candidate in self.state.plants
                if candidate.plant_id == active_before
            ),
            None,
        )
        if active_plant is not None and active_plant.fully_grown:
            replacement = self._next_planted_unfinished(active_plant)
            self.state.active_plant_id = (
                replacement.plant_id if replacement is not None else None
            )
            auto_selected = replacement.plant_id if replacement is not None else ""
            self._transfer_card_effects(
                active_plant,
                replacement,
                event_ms=event_ms,
            )
            self._record_active_period(
                replacement.plant_id if replacement is not None else None,
                event_ms=event_ms,
            )

        self.state.collect_completed_card_effects()

        landmark_units = sum(
            item.units
            for item in project_allocations
            if item.target_type == "landmark"
        )
        mastery_units = sum(
            item.units
            for item in project_allocations
            if item.target_type == "mastery"
        )
        legacy_units = sum(
            item.units
            for item in project_allocations
            if item.target_type == "legacy"
        )
        applied_total = requested - stored - project_units
        return GrowthGrantResult(
            requested,
            applied_total,
            stored,
            tuple(allocations),
            original_target_id,
            str(self.state.active_plant_id or ""),
            auto_selected,
            landmark_units,
            mastery_units,
            legacy_units,
            project_allocations,
        )

    def _review_growth_projection(
        self,
        plant: Plant | None,
        event_ms: int,
        *,
        answer_number: int,
        streak_days: int | None = None,
        environment_growth_known: bool = True,
        decoration_result: DecorationResult | None = None,
    ) -> tuple[ReviewAward, int]:
        """Project one review award without mutating plant or daily state."""
        del streak_days
        bonus_percent = self.current_streak_bonus_percent()
        base_units = self.BASE_GROWTH_PER_REVIEW * GROWTH_UNITS_PER_POINT
        streak_units = self.BASE_GROWTH_PER_REVIEW * bonus_percent
        proposed_fertilizer_bonus = (
            self.fertilizer_growth(plant, now=event_ms / 1000)
        )
        proposed_booster_bonus = (
            self.booster_growth(plant, now=event_ms / 1000)
        )
        answer_number = max(1, int(answer_number))
        decoration = (
            decoration_result
            if decoration_result is not None
            else self._project_decoration_answer(answer_number)
            if environment_growth_known
            else DecorationResult(active_bonus_id=self.active_garden_feature_id())
        )
        proposed_scenery_bonus = (
            self._scenery_review_growth(answer_number)
            if environment_growth_known else 0
        )
        fertilizer_units = proposed_fertilizer_bonus * GROWTH_UNITS_PER_POINT
        booster_units = proposed_booster_bonus * GROWTH_UNITS_PER_POINT
        weather_units = max(0, int(decoration.decoration_growth_awarded_units))
        scenery_units = proposed_scenery_bonus * GROWTH_UNITS_PER_POINT
        trophies = trophy_effects(self.state, event_ms=event_ms)
        return (
            ReviewAward(
                plant.plant_id if plant is not None else None,
                base_units // GROWTH_UNITS_PER_POINT,
                streak_units // GROWTH_UNITS_PER_POINT,
                proposed_fertilizer_bonus,
                bonus_percent,
                (
                    "No plant is selected. This card’s Growth is being stored."
                    if plant is None else ""
                ),
                booster_growth=proposed_booster_bonus,
                weather_growth=weather_units // GROWTH_UNITS_PER_POINT,
                scenery_growth=proposed_scenery_bonus,
                trophy_growth=trophies.review_growth,
                trophy_growth_units=trophies.review_growth * GROWTH_UNITS_PER_POINT,
                shared_growth_numerator=trophies.shared_growth_numerator,
                shared_growth_denominator=trophies.shared_growth_denominator,
                base_growth_units=base_units,
                streak_growth_units=streak_units,
                fertilizer_growth_units=fertilizer_units,
                booster_growth_units=booster_units,
                weather_growth_units=weather_units,
                scenery_growth_units=scenery_units,
                decoration_result=decoration,
            ),
            0,
        )

    def project_review_growth(
        self,
        plant: Plant | None = None,
        *,
        now: float | None = None,
        answer_number: int | None = None,
    ) -> ReviewAward:
        """Return the next eligible card's effective Growth without mutation."""

        target = plant if plant is not None else self.active_plant()
        projected_answer = (
            max(1, int(answer_number))
            if answer_number is not None
            else max(1, int(self.state.daily_stats.reviewed) + 1)
        )
        event_ms = int(
            round((self._now_seconds() if now is None else float(now)) * 1000)
        )
        award, _next_remainder = self._review_growth_projection(
            target,
            event_ms,
            answer_number=projected_answer,
        )
        allocations = self._project_review_allocations(target, award)
        shared_plan = self._shared_growth_plan(
            self._shared_growth_anchor(target),
            award.total_growth_units,
            numerator=award.shared_growth_numerator,
            denominator=award.shared_growth_denominator,
        )
        requested_with_shared = award.total_growth_units + sum(
            units for _recipient, units in shared_plan
        )
        applied_units = sum(item.applied_units for item in allocations)
        overflow_units = max(0, requested_with_shared - applied_units)
        project_allocations, stored_units = (
            self._project_active_growth_overflow(overflow_units)
        )
        paused_reason = award.paused_reason
        if target is None and project_allocations:
            destination = project_allocations[0]
            paused_reason = (
                "No plant is selected. This card’s Growth will fund "
                f"{destination.target_id.replace('_', ' ').title()}."
            )
        return replace(
            award,
            allocations=allocations,
            applied_growth_units=applied_units,
            redirected_growth_units=sum(
                item.applied_units for item in allocations if item.redirected
            ),
            shared_growth_units=sum(
                item.applied_units for item in allocations if item.role == "passive"
            ),
            stored_growth_units=stored_units,
            landmark_growth_units=sum(
                item.units for item in project_allocations
                if item.target_type is GrowthTargetType.LANDMARK
            ),
            mastery_growth_units=sum(
                item.units for item in project_allocations
                if item.target_type is GrowthTargetType.MASTERY
            ),
            legacy_growth_units=sum(
                item.units for item in project_allocations
                if item.target_type is GrowthTargetType.LEGACY
            ),
            project_allocations=project_allocations,
            paused_reason=paused_reason,
        )

    def _project_active_growth_overflow(
        self,
        units: int,
    ) -> tuple[tuple[ProjectGrowthAllocation, ...], int]:
        """Project final overflow using the same active-target capacity rules."""

        available = max(0, int(units))
        if available <= 0:
            return (), 0
        projects = self.growth_projects_snapshot()
        target = projects.active_target
        if target is None or not growth_target_enabled(target.target_type):
            return (), available
        if target.target_type is GrowthTargetType.LANDMARK:
            track = projects.landmark_track
        elif target.target_type is GrowthTargetType.MASTERY:
            track = projects.mastery_track(target.target_id)
        else:
            track = projects.legacy_track
        choice = next(
            (item for item in projects.target_choices if item.target == target),
            None,
        )
        if choice is None or not choice.available:
            return (), available
        accepted = (
            available
            if track.remaining_capacity_units is None
            else min(available, track.remaining_capacity_units)
        )
        if accepted <= 0:
            return (), available
        return (
            (ProjectGrowthAllocation(
                target.target_type,
                target.target_id,
                accepted,
            ),),
            available - accepted,
        )

    def _project_review_allocations(
        self,
        plant: Plant | None,
        award: ReviewAward,
    ) -> tuple[GrowthAllocation, ...]:
        if plant is None or award.total_growth_units <= 0:
            return ()
        planted = sorted(
            (candidate for candidate in self.state.plants if candidate.planted),
            key=lambda candidate: (int(candidate.slot_index or 0), candidate.plant_id),
        )
        remaining_capacity = {
            candidate.plant_id: max(
                0,
                GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT
                - self._plant_growth_units(candidate),
            )
            for candidate in planted
        }
        allocations: list[GrowthAllocation] = []

        def project_lane(intended: Plant, units: int, role: str) -> None:
            if intended not in planted:
                return
            start = planted.index(intended)
            ordered = planted[start:] + planted[:start]
            remaining = max(0, int(units))
            for candidate in ordered:
                if remaining <= 0:
                    break
                capacity = remaining_capacity.get(candidate.plant_id, 0)
                applied = min(remaining, capacity)
                if applied <= 0:
                    continue
                remaining_capacity[candidate.plant_id] = capacity - applied
                remaining -= applied
                allocations.append(GrowthAllocation(
                    plant_id=candidate.plant_id,
                    role=role,
                    exact_fifths=0,
                    credited_growth=applied // GROWTH_UNITS_PER_POINT,
                    requested_units=applied,
                    applied_units=applied,
                    redirected=candidate.plant_id != intended.plant_id,
                ))

        project_lane(plant, award.total_growth_units, "nurtured")
        for recipient, shared_units in self._shared_growth_plan(
            plant, award.total_growth_units,
            numerator=award.shared_growth_numerator,
            denominator=award.shared_growth_denominator,
        ):
            project_lane(recipient, shared_units, "passive")
        return tuple(allocations)

    def _award_review_growth(
        self,
        plant: Plant | None,
        event_ms: int,
        *,
        streak_days: int | None = None,
        answer_number: int | None = None,
        environment_growth_known: bool = True,
    ) -> ReviewAward:
        decoration = (
            self._advance_decoration_answer(answer_number)
            if environment_growth_known
            else DecorationResult(active_bonus_id=self.active_garden_feature_id())
        )
        award, _next_remainder = self._review_growth_projection(
            plant,
            event_ms,
            answer_number=(
                max(1, int(self.state.daily_stats.reviewed))
                if answer_number is None
                else max(1, int(answer_number))
            ),
            streak_days=streak_days,
            environment_growth_known=environment_growth_known,
            decoration_result=decoration,
        )
        if award.total_growth_units <= 0 and decoration.direct_growth_awarded_units <= 0:
            return award
        # Card-counted effects spend one card only when their Growth is part of
        # this committed award. Save rollback restores both queues exactly.
        if award.fertilizer_growth_units > 0:
            self._consume_card_effect(plant, "fertilizer", event_ms=event_ms)
        if award.booster_growth_units > 0:
            self._consume_card_effect(plant, "booster", event_ms=event_ms)
        stats = self.state.daily_stats
        card_growth_seen_before = {
            *stats.plant_nurtured_growth,
            *stats.plant_passive_growth_credited,
        }
        shared_plan = self._shared_growth_plan(
            self._shared_growth_anchor(plant),
            award.total_growth_units,
            numerator=award.shared_growth_numerator,
            denominator=award.shared_growth_denominator,
        )
        primary = self._route_growth_units(
            plant,
            award.total_growth_units,
            role="nurtured",
            transition_source="nurtured",
            event_ms=event_ms,
            finalize_overflow=False,
        )
        allocations: list[GrowthAllocation] = list(primary.allocations)
        shared_results: list[GrowthGrantResult] = []
        for passive, shared_units in shared_plan:
            result = self._route_growth_units(
                passive,
                shared_units,
                role="passive",
                transition_source="shared_growth",
                event_ms=event_ms,
                finalize_overflow=False,
            )
            shared_results.append(result)
            allocations.extend(result.allocations)
        final_overflow_units = primary.stored_units + sum(
            item.stored_units for item in shared_results
        )
        stored_units, project_allocations = self._finalize_growth_overflow(
            final_overflow_units
        )

        for field_name, units in (
            ("base_growth", award.base_growth_units),
            ("streak_bonus_growth", award.streak_growth_units),
            ("fertilizer_growth", award.fertilizer_growth_units),
            ("booster_growth", award.booster_growth_units),
            ("weather_growth", award.weather_growth_units),
            ("scenery_growth", award.scenery_growth_units),
            ("trophy_growth", award.trophy_growth_units),
        ):
            setattr(
                stats,
                field_name,
                max(0, int(getattr(stats, field_name, 0) or 0))
                + max(0, int(units)) // GROWTH_UNITS_PER_POINT,
            )
        for field_name, units in (
            ("answer_growth_units", award.total_growth_units),
            ("applied_growth_units", primary.applied_units + sum(
                item.applied_units for item in shared_results
            )),
            ("redirected_growth_units", sum(
                allocation.applied_units
                for allocation in allocations
                if allocation.redirected
            )),
            ("shared_growth_units", sum(
                item.applied_units for item in shared_results
            )),
            ("stored_growth_units", stored_units),
        ):
            if hasattr(stats, field_name):
                setattr(
                    stats,
                    field_name,
                    max(0, int(getattr(stats, field_name, 0) or 0))
                    + max(0, int(units)),
                )
        contributed_plant_ids = {
            allocation.plant_id
            for allocation in allocations
            if int(allocation.applied_units) > 0
        }
        for plant_id in contributed_plant_ids:
            contributed = self.plant_story(plant_id)
            if contributed is None:
                continue
            contributed.completion_cards = max(
                0, int(getattr(contributed, "completion_cards", 0) or 0)
            ) + 1
            if plant_id not in card_growth_seen_before:
                contributed.completion_active_days = max(
                    0,
                    int(getattr(contributed, "completion_active_days", 0) or 0),
                ) + 1
        for allocation in allocations:
            legacy_map = (
                stats.plant_passive_growth_credited
                if allocation.role == "passive"
                else stats.plant_nurtured_growth
            )
            legacy_map[allocation.plant_id] = (
                legacy_map.get(allocation.plant_id, 0)
                + max(0, int(allocation.applied_units)) // GROWTH_UNITS_PER_POINT
            )
            if hasattr(stats, "plant_applied_growth_units"):
                stats.plant_applied_growth_units[allocation.plant_id] = (
                    stats.plant_applied_growth_units.get(allocation.plant_id, 0)
                    + max(0, int(allocation.applied_units))
                )
            if (
                allocation.role == "passive"
                and hasattr(stats, "plant_shared_growth_units")
            ):
                stats.plant_shared_growth_units[allocation.plant_id] = (
                    stats.plant_shared_growth_units.get(allocation.plant_id, 0)
                    + max(0, int(allocation.applied_units))
                )
            if allocation.role == "passive":
                stats.plant_passive_growth_fifths[allocation.plant_id] = (
                    stats.plant_passive_growth_fifths.get(allocation.plant_id, 0)
                    + max(0, int(allocation.applied_units)) // 20
                )
        stats.reconcile_growth_totals()
        redirected_units = sum(
            allocation.applied_units
            for allocation in allocations
            if allocation.redirected
        )
        shared_applied = sum(item.applied_units for item in shared_results)
        landmark_units = sum(
            item.units
            for item in project_allocations
            if item.target_type is GrowthTargetType.LANDMARK
        )
        mastery_units = sum(
            item.units
            for item in project_allocations
            if item.target_type is GrowthTargetType.MASTERY
        )
        legacy_units = sum(
            item.units
            for item in project_allocations
            if item.target_type is GrowthTargetType.LEGACY
        )
        direct_result = GrowthGrantResult(0, 0, 0)
        if decoration.direct_growth_awarded_units:
            direct_target = plant
            direct_result = self._apply_direct_growth_units(
                direct_target,
                decoration.direct_growth_awarded_units,
                stats_field="direct_reward_growth",
                transition_source=(
                    "firefly_lantern"
                    if decoration.active_bonus_id == "firefly_lantern"
                    else "direct_reward"
                ),
            )
            allocations.extend(direct_result.allocations)
            project_allocations = (
                *project_allocations,
                *direct_result.project_allocations,
            )
        return replace(
            award,
            allocations=tuple(allocations),
            applied_growth_units=(
                primary.applied_units + shared_applied
                + direct_result.applied_units
            ),
            redirected_growth_units=(
                redirected_units
                + sum(
                    allocation.applied_units
                    for allocation in direct_result.allocations
                    if allocation.redirected
                )
            ),
            shared_growth_units=shared_applied,
            stored_growth_units=stored_units + direct_result.stored_units,
            landmark_growth_units=(landmark_units + direct_result.landmark_units),
            mastery_growth_units=(mastery_units + direct_result.mastery_units),
            legacy_growth_units=(legacy_units + direct_result.legacy_units),
            project_allocations=project_allocations,
        )

    def _grant_completion_environment_gift(
        self,
        *,
        scheduler_day: str,
        correlation_id: str,
    ) -> bool:
        """Grant the locked Scenery gift when today's cards are complete."""

        granted = False
        active_bonus = self.active_garden_feature_id()
        if active_bonus == "herbalist_hourglass":
            hourglass_key = f"hourglass_completion:{scheduler_day}"
            if not self._reward_applied(hourglass_key):
                progress = max(
                    0,
                    int(getattr(self.state, "hourglass_completion_progress", 0)),
                ) + 1
                interval = GARDEN_FEATURE_CATALOG["herbalist_hourglass"].effects[0].every_nth_completion
                reward_due = progress >= interval
                self.state.hourglass_completion_progress = 0 if reward_due else progress
                hourglass_receipts = self._grant_reward_bundle(
                    hourglass_key,
                    source="garden_decoration",
                    source_id="herbalist_hourglass",
                    reason="Herbalist’s Hourglass progress",
                    scheduler_day=scheduler_day,
                    correlation_id=correlation_id,
                    inventory_item_id="booster_potion" if reward_due else "",
                    inventory_quantity=1 if reward_due else 0,
                    title="Herbalist’s Hourglass",
                    description="+1 Booster Potion" if reward_due else "",
                )
                granted = granted or bool(hourglass_receipts)

        scenery = self.locked_environment_id("scenery")
        if scenery not in {"snowy", "halloween", "full_moon"}:
            return granted
        event_key = f"environment_daily:{scenery}:{scheduler_day}"
        if self._reward_applied(event_key):
            return granted
        if scenery == "snowy":
            receipts = self._grant_reward_bundle(
                event_key, source="environment_completion_gift", source_id=scenery,
                reason="Snow-Covered Garden reward", scheduler_day=scheduler_day,
                correlation_id=correlation_id, growth=SCENERY_CATALOG[scenery].effects[0].amount,
                plant=self.active_plant(), title="Snow-Covered Garden",
            )
            self.state.daily_environment_claims[scenery] = scheduler_day
            return granted or bool(receipts)
        elif scenery == "full_moon":
            progress = max(
                0, int(getattr(self.state, "full_moon_completion_progress", 0))
            ) + 1
            reward_due = progress >= SCENERY_CATALOG["full_moon"].effects[0].every_nth_completion
            self.state.full_moon_completion_progress = 0 if reward_due else progress
            consumable_id = "booster_potion" if reward_due else ""
        else:
            digest = hashlib.blake2b(
                f"{self.state.reward_seed}:{scheduler_day}".encode("utf-8"),
                digest_size=32,
                person=b"halloween-gift",
            ).digest()
            roll = int.from_bytes(digest[:8], "big") % 100
            consumable_id = (
                "growth_charge_small"
                if roll < 95
                else "growth_charge_standard"
                if roll < 99
                else "booster_potion"
            )
        scenery_name = SCENERY_CATALOG[scenery].name
        name = (
            "Booster Potion"
            if consumable_id == "booster_potion"
            else GROWTH_CHARGES[consumable_id].name
            if consumable_id
            else ""
        )
        receipts = self._grant_reward_bundle(
            event_key,
            source="environment_completion_gift",
            source_id=scenery,
            reason=f"{scenery_name} reward",
            scheduler_day=scheduler_day,
            correlation_id=correlation_id,
            inventory_item_id=consumable_id,
            inventory_quantity=1 if consumable_id else 0,
            title=f"{scenery_name} reward",
            description=f"+1 {name}" if name else "",
        )
        self.state.daily_environment_claims[scenery] = scheduler_day
        return granted or bool(receipts)

    def _grant_environment_completion_pity(
        self,
        *,
        scheduler_day: str,
        correlation_id: str,
    ) -> tuple[str, ...]:
        """Advance completion-day discovery guarantees exactly once."""

        event_guard = f"environment_completion_pity:{scheduler_day}"
        if self._reward_applied(event_guard):
            return ()
        owned = {
            *self.state.inventory.get("garden_features", []),
            *self.state.inventory.get("scenery", []),
        }
        stored_counts = getattr(
            self.state, "environment_completion_pity_misses", {}
        )
        decision = resolve_environment_completion_pity(
            secret=self.state.reward_seed,
            completion_identity=f"today-cards:{scheduler_day}",
            owned_environment_ids=owned,
            tier_completion_misses={
                "rare_environment": max(0, int(stored_counts.get("rare", 0))),
                "very_rare_environment": max(
                    0, int(stored_counts.get("very_rare", 0))
                ),
                "ultra_environment": max(0, int(stored_counts.get("ultra", 0))),
            },
        )
        self.state.environment_completion_pity_misses = {
            "rare": max(0, int(decision.next_tier_completion_misses.get(
                "rare_environment", 0
            ))),
            "very_rare": max(0, int(decision.next_tier_completion_misses.get(
                "very_rare_environment", 0
            ))),
            "ultra": max(0, int(decision.next_tier_completion_misses.get(
                "ultra_environment", 0
            ))),
        }
        granted: list[str] = []
        for item in decision.items:
            self._grant_environment_find(
                event_key=f"{event_guard}:{item.tier}",
                item_id=item.item_id,
                environment_kind=item.environment_kind,
                display_name=item.display_name,
                tier=item.tier,
                scheduler_day=scheduler_day,
                correlation_id=correlation_id,
            )
            card_key = {
                "rare_environment": "rare",
                "very_rare_environment": "very_rare",
                "ultra_environment": "ultra",
            }[item.tier]
            self.state.environment_pity_misses[card_key] = 0
            granted.append(item.item_id)
        # The guard is authoritative even when no tier is due.
        self._append_reward_event_key(event_guard)
        return tuple(granted)

    def _grant_standard_find_reward(
        self,
        reward: GardenFindReward,
        *,
        event_key: str,
        scheduler_day: str,
        correlation_id: str,
        plant: Plant | None,
    ) -> tuple[RewardReceipt, ...]:
        return self._grant_reward_bundle(
            event_key,
            source="standard_find",
            source_id=reward.reward_id,
            reason=f"Standard Find: {reward.display_name}",
            scheduler_day=scheduler_day,
            correlation_id=correlation_id,
            coins=reward.amount if reward.reward_kind == "coins" else 0,
            growth=reward.amount if reward.reward_kind == "growth" else 0,
            inventory_item_id=reward.inventory_item_id or "",
            inventory_quantity=(
                reward.amount if reward.reward_kind == "inventory_item" else 0
            ),
            plant=plant,
            title=reward.display_name,
            description=reward.description,
        )

    def _grant_environment_find(
        self,
        *,
        event_key: str,
        item_id: str,
        environment_kind: str,
        display_name: str,
        tier: str,
        scheduler_day: str,
        correlation_id: str,
    ) -> tuple[RewardReceipt, ...]:
        if self._reward_applied(event_key):
            return ()
        inventory_key = (
            "garden_features"
            if environment_kind in {"garden_feature", "weather"}
            else "scenery"
        )
        item_id = (
            canonical_garden_feature_id(item_id)
            if inventory_key == "garden_features"
            else item_id
        )
        owned = self.state.inventory.setdefault(inventory_key, [])
        if item_id not in owned:
            owned.append(item_id)
        receipt = self._append_reward_receipt(
            event_key=event_key,
            reward_type="environment_item",
            source="garden_find_environment",
            source_id=item_id,
            scheduler_day=scheduler_day,
            correlation_id=correlation_id,
            amount=1,
            item_id=item_id,
            title=display_name,
            description=f"{tier.replace('_', ' ').title()} Garden discovery",
        )
        self._stage_economy_event(EconomyEventRecord(
            event_key=event_key,
            event_kind="environment_discovery",
            source_id=str(item_id),
            scheduler_day=scheduler_day,
            occurred_at=receipt.occurred_at,
            item_id=str(item_id),
            quantity=1,
            metric_deltas={"environment_discoveries": {str(item_id): 1}},
        ))
        self._append_reward_event_key(event_key)
        return (receipt,)

    def _garden_find_outcome(
        self,
        answer_key: str,
        pool_id: str,
    ) -> GardenFindOutcome | None:
        resolver = getattr(self.storage, "garden_find_outcome", None)
        if callable(resolver):
            return resolver(answer_key, pool_id)
        return self.state.garden_find_outcomes.get(f"{pool_id}:{answer_key}")

    def _garden_find_counts(
        self,
        scheduler_day: str,
    ) -> tuple[int, dict[str, int]]:
        resolver = getattr(self.storage, "garden_find_counts", None)
        if callable(resolver):
            total, reward_counts = resolver(
                scheduler_day, pool_id=STANDARD_POOL_ID
            )
            return max(0, int(total)), dict(reward_counts)
        return (
            max(0, int(self.state.garden_find_daily_counts.get(
                scheduler_day, 0
            ))),
            dict(self.state.garden_find_reward_daily_counts.get(
                scheduler_day, {}
            )),
        )

    def garden_find_status(self):
        """Return the small, counter-free Find status used by the HUD."""

        finds_today, _reward_counts = self._garden_find_counts(
            self.state.daily_stats.day
        )
        return standard_find_status(
            finds_today=finds_today,
            drought_misses=self.state.garden_find_drought_count,
            eligible_answers_today=self.state.daily_stats.reviewed,
        )

    def _record_garden_find_outcome(
        self,
        outcome: GardenFindOutcome,
    ) -> None:
        stager = getattr(self.storage, "stage_garden_find_outcome", None)
        if callable(stager):
            stager(outcome)
            return
        outcome_key = f"{outcome.pool_id}:{outcome.answer_key}"
        if outcome_key in self.state.garden_find_outcomes:
            return
        self.state.garden_find_outcomes[outcome_key] = outcome
        if outcome.pool_id == STANDARD_POOL_ID and outcome.status == "hit":
            finds_today = max(0, int(
                self.state.garden_find_daily_counts.get(
                    outcome.scheduler_day, 0
                )
            ))
            self.state.garden_find_daily_counts[outcome.scheduler_day] = finds_today + 1
            reward_counts = self.state.garden_find_reward_daily_counts.setdefault(
                outcome.scheduler_day, {}
            )
            reward_counts[outcome.reward_id] = max(0, int(reward_counts.get(outcome.reward_id, 0))) + 1

    def _resolve_garden_finds(
        self,
        answer_identity: str,
        *,
        answer_key: str,
        scheduler_day: str,
        plant: Plant | None,
        correlation_id: str,
    ) -> tuple[str, ...]:
        """Resolve and record both independent pools inside the review save."""

        occurred_at = utc_now_iso()
        found_ids: list[str] = []
        if self._garden_find_outcome(answer_key, STANDARD_POOL_ID) is None:
            finds_today, reward_daily_counts = self._garden_find_counts(
                scheduler_day
            )
            decision = resolve_standard_find(
                secret=self.state.reward_seed,
                answer_identity=answer_identity,
                drought_misses=self.state.garden_find_drought_count,
                finds_today=finds_today,
                registry=self.garden_find_registry,
                # v2 keeps this flag for old callers but never removes Growth
                # rewards. With no target, Instant Growth is stored.
                growth_available=True,
                available_inventory_item_ids=self.state.consumables.keys(),
                reward_daily_counts=reward_daily_counts,
                scheduler_day=scheduler_day,
                addon_version=self._addon_version,
                eligible_answers_today=max(1, int(self.state.daily_stats.reviewed)),
            )
            self.state.garden_find_drought_count = decision.next_drought_misses
            status = "paused" if decision.capped else "hit" if decision.hit else "miss"
            reward_id = ""
            reward_type = ""
            reward_amount = 0
            item_id = ""
            if decision.hit and decision.reward is not None:
                reward = decision.reward
                event_key = f"garden_find:{answer_key}:{STANDARD_POOL_ID}"
                receipts = self._grant_standard_find_reward(
                    reward,
                    event_key=event_key,
                    scheduler_day=scheduler_day,
                    correlation_id=correlation_id,
                    plant=plant,
                )
                reward_id = reward.reward_id
                reward_type = reward.reward_kind
                reward_amount = sum(
                    receipt.amount
                    for receipt in receipts
                    if receipt.event_key == event_key
                ) or reward.amount
                item_id = reward.inventory_item_id or ""
                found_ids.append(reward.reward_id)
            self._record_garden_find_outcome(GardenFindOutcome(
                answer_key=answer_key,
                scheduler_day=scheduler_day,
                status=status,
                pool_id=STANDARD_POOL_ID,
                pool_version=STANDARD_POOL_VERSION,
                occurred_at=occurred_at,
                reward_id=reward_id,
                reward_type=reward_type,
                amount=reward_amount,
                item_id=item_id,
                display_name=(decision.reward.display_name if decision.reward else ""),
                description=(decision.reward.description if decision.reward else ""),
                tier=(decision.reward.tier if decision.reward else ""),
                artwork_ref=(decision.reward.artwork_ref if decision.reward else ""),
                localization_key=(
                    decision.reward.localization_key if decision.reward else ""
                ),
            ))
            for issue in decision.registry_issues:
                logger.warning(
                    "Anki Garden disabled Garden Find entry %s: %s",
                    issue.reward_id or issue.code,
                    issue.message,
                )

        if self._garden_find_outcome(answer_key, ENVIRONMENT_POOL_ID) is None:
            owned_environment_ids = {
                *self.state.inventory.get("garden_features", []),
                *self.state.inventory.get("scenery", []),
            }
            environment = resolve_environment_find(
                secret=self.state.reward_seed,
                answer_identity=answer_identity,
                owned_environment_ids=owned_environment_ids,
                tier_pity_misses={
                    "rare_environment": max(0, int(
                        self.state.environment_pity_misses.get("rare", 0)
                    )),
                    "very_rare_environment": max(0, int(
                        self.state.environment_pity_misses.get("very_rare", 0)
                    )),
                    "ultra_environment": max(0, int(
                        self.state.environment_pity_misses.get("ultra", 0)
                    )),
                },
            )
            self.state.environment_pity_misses = {
                "rare": max(0, int(environment.next_tier_pity_misses.get(
                    "rare_environment", 0
                ))),
                "very_rare": max(0, int(environment.next_tier_pity_misses.get(
                    "very_rare_environment", 0
                ))),
                "ultra": max(0, int(environment.next_tier_pity_misses.get(
                    "ultra_environment", 0
                ))),
            }
            self.state.garden_find_ultra_misses = (
                self.state.environment_pity_misses["ultra"]
            )
            environment_reward_id = ""
            environment_reward_type = ""
            environment_item_id = ""
            environment_amount = 0
            environment_items = tuple(
                environment.items
                or ((environment.item,) if environment.item is not None else ())
            )
            if environment.hit and environment_items:
                for item in environment_items:
                    event_key = (
                        f"garden_find:{answer_key}:{ENVIRONMENT_POOL_ID}:"
                        f"{item.tier}"
                    )
                    self._grant_environment_find(
                        event_key=event_key,
                        item_id=item.item_id,
                        environment_kind=item.environment_kind,
                        display_name=item.display_name,
                        tier=item.tier,
                        scheduler_day=scheduler_day,
                        correlation_id=correlation_id,
                    )
                    completion_pity = getattr(
                        self.state, "environment_completion_pity_misses", {}
                    )
                    tier_key = {
                        "rare_environment": "rare",
                        "very_rare_environment": "very_rare",
                        "ultra_environment": "ultra",
                    }[item.tier]
                    completion_pity[tier_key] = 0
                    self.state.environment_completion_pity_misses = completion_pity
                    found_ids.append(item.item_id)
                primary_item = environment_items[0]
                environment_reward_id = primary_item.item_id
                environment_reward_type = "environment_item"
                environment_item_id = primary_item.item_id
                environment_amount = len(environment_items)
            self._record_garden_find_outcome(GardenFindOutcome(
                answer_key=answer_key,
                scheduler_day=scheduler_day,
                status="hit" if environment.hit else "miss",
                pool_id=ENVIRONMENT_POOL_ID,
                pool_version=ENVIRONMENT_POOL_VERSION,
                occurred_at=occurred_at,
                reward_id=environment_reward_id,
                reward_type=environment_reward_type,
                amount=environment_amount,
                item_id=environment_item_id,
                display_name=(
                    environment.item.display_name if environment.item else ""
                ),
                description=(
                    "Added to Garden decorations"
                    if environment.item else ""
                ),
                tier=(environment.item.tier if environment.item else ""),
                artwork_ref=(environment.item.item_id if environment.item else ""),
                localization_key=(
                    f"garden_find.environment.{environment.item.item_id}"
                    if environment.item else ""
                ),
            ))
        return tuple(found_ids)

    def _queue_reward_feedback(
        self,
        correlation_id: str,
        receipts: tuple[RewardReceipt, ...],
        *,
        achievement_ids: tuple[str, ...] = (),
        plant_id: str | None = None,
        title: str = "Review rewards",
    ) -> bool:
        find_receipts = tuple(
            receipt
            for receipt in receipts
            if receipt.source in GARDEN_FIND_RECEIPT_SOURCES
        )
        projected_achievement_ids: tuple[str, ...] = ()
        try:
            from .reward_presentation import reward_summary

            summary = reward_summary(receipts, correlation_id=correlation_id)
            message = summary.learner_text
            projected_achievement_ids = summary.achievement_ids
        except Exception:
            # Reward presentation is deliberately non-transactional. A copy
            # projection failure must not roll back an otherwise valid grant.
            message = ""
        parts = [message] if message else []
        visible_achievement_ids = tuple(dict.fromkeys(
            (*projected_achievement_ids, *achievement_ids)
        ))
        if visible_achievement_ids:
            names = [
                milestone_unlocked_text(item)
                for item in visible_achievement_ids
                if item in ACHIEVEMENTS_BY_ID
            ]
            if names:
                parts.append(", ".join(names))
        if find_receipts:
            find_names = [receipt.title for receipt in find_receipts if receipt.title]
            title = (
                find_names[0]
                if len(find_names) == 1 and len(receipts) == 1
                else f"{len(receipts):,} Garden rewards added"
            )
        message = "; ".join(parts) or "Your Garden rewards were recorded."
        first_find = find_receipts[0] if find_receipts else None
        find_artwork = ""
        if first_find is not None:
            definition = next(
                (
                    reward
                    for reward in self.garden_find_registry.rewards
                    if reward.reward_id == first_find.source_id
                ),
                None,
            )
            find_artwork = (
                definition.artwork_ref
                if definition is not None
                else first_find.item_id or first_find.source_id
            )
        return self._queue_feedback(
            f"reward-summary:{correlation_id}",
            "garden_find" if first_find is not None else "reward_summary",
            message,
            plant_id,
            title=title,
            asset_category=(
                "environment"
                if first_find is not None
                and first_find.source == "garden_find_environment"
                else "ui"
            ),
            asset_key=find_artwork if first_find else "garden_coins",
            correlation_id=correlation_id,
        )

    def _project_stage_rewards(
        self,
        before: int,
        after: int,
    ) -> tuple[tuple[str, str, StageRewardProjection], ...]:
        previous_index = max(
            index
            for index, threshold in enumerate(GROWTH_THRESHOLDS)
            if before >= threshold
        )
        new_index = max(
            index
            for index, threshold in enumerate(GROWTH_THRESHOLDS)
            if after >= threshold
        )
        projected: list[tuple[str, str, StageRewardProjection]] = []
        from .earned_coins import quote_earned_coins
        carry = self.state.autumn_coin_carry_units
        for stage_index in range(previous_index + 1, new_index + 1):
            previous_stage = GROWTH_STAGES[stage_index - 1]
            new_stage = GROWTH_STAGES[stage_index]
            base_reward = self.STAGE_REWARD_SPLITS[new_stage][3]
            quote = quote_earned_coins(
                base_reward, active_scenery_id=self.locked_environment_id("scenery"),
                carry_units=carry,
            )
            reward, carry = quote.total_coins, quote.next_carry_units
            projected.append((
                previous_stage,
                new_stage,
                StageRewardProjection(new_stage, reward),
            ))
        return tuple(projected)

    @staticmethod
    def _stage_display_name(stage: str) -> str:
        return "Full Bloom" if str(stage) == "rare" else str(stage).title()

    def _checkpoint_reward_amount(self, base_reward: int) -> int:
        from .earned_coins import quote_earned_coins
        return quote_earned_coins(
            base_reward, active_scenery_id=self.locked_environment_id("scenery"),
            carry_units=self.state.autumn_coin_carry_units,
        ).total_coins

    def project_checkpoint_reward(self, next_stage: str, percent: int) -> int:
        """Return the next milestone payout without spending Autumn carry."""

        splits = self.STAGE_REWARD_SPLITS.get(str(next_stage), ())
        try:
            index = (25, 50, 75, 100).index(int(percent))
            base = max(0, int(splits[index]))
        except (ValueError, TypeError, IndexError):
            return 0
        return self._checkpoint_reward_amount(base)

    def _record_growth_crossings(
        self,
        plant: Plant,
        before: int,
        after: int,
        *,
        source: str = "nurtured",
    ) -> None:
        crossings: list[tuple[int, int, str, str, int]] = []
        # (growth point, order, next stage, kind, checkpoint percent)
        for index in range(len(GROWTH_STAGES) - 1):
            stage = GROWTH_STAGES[index]
            next_stage = GROWTH_STAGES[index + 1]
            start, end = GROWTH_THRESHOLDS[index], GROWTH_THRESHOLDS[index + 1]
            for checkpoint_index, percent in enumerate((25, 50, 75)):
                point = start + math.ceil((end - start) * percent / 100)
                if before < point <= after:
                    crossings.append((
                        point,
                        checkpoint_index,
                        next_stage,
                        "checkpoint",
                        percent,
                    ))
            if before < end <= after:
                crossings.append((end, 3, next_stage, "stage", 100))

        def credit_crossing(
            event_key: str,
            reason: str,
            *,
            base_reward: int,
            total_reward: int,
            feedback: str,
        ) -> None:
            # Preserve the established milestone identity for the catalog
            # base payout.  Autumn's incremental value is a separate,
            # correlated ledger source so concentration reporting reflects
            # the effect without changing the total or fractional carry.
            self._credit_currency(
                event_key,
                reason,
                base_reward,
                feedback=feedback,
                plant_id=plant.plant_id,
                source="plant_milestone",
                source_id=plant.plant_id,
                included_in_total=True,
            )

        for _point, order, next_stage, kind, percent in sorted(crossings):
            base_reward = self.STAGE_REWARD_SPLITS[next_stage][order]
            reward = self._checkpoint_reward_amount(base_reward)
            if kind == "checkpoint":
                event_key = (
                    f"stage_checkpoint:{plant.plant_id}:{next_stage}:{percent}"
                )
                if hasattr(plant, "checkpoint_claims"):
                    claim = f"{next_stage}:{percent}"
                    if claim not in plant.checkpoint_claims:
                        plant.checkpoint_claims.append(claim)
                credit_crossing(
                    event_key,
                    plant_stage_event(plant, next_stage, checkpoint_percent=percent),
                    base_reward=base_reward,
                    total_reward=reward,
                    feedback=(
                        f"{plant_stage_event(plant, next_stage, checkpoint_percent=percent)}. "
                        f"{_garden_coin_amount(reward, signed=True)}"
                    ),
                )
                continue

            previous_stage = GROWTH_STAGES[GROWTH_STAGES.index(next_stage) - 1]
            if next_stage not in plant.stage_reward_claims:
                plant.stage_reward_claims.append(next_stage)
            self._add_memory(
                plant,
                f"stage:{next_stage}",
                "stage",
                previous_stage=previous_stage,
                new_stage=next_stage,
            )
            self._pending_stage_transitions.append(StageTransition(
                plant.plant_id,
                plant.species,
                previous_stage,
                next_stage,
                plant_species_name(plant),
                source,
            ))
            credit_crossing(
                f"stage:{plant.plant_id}:{next_stage}",
                plant_stage_event(plant, next_stage),
                base_reward=base_reward,
                total_reward=reward,
                feedback=(
                    f"{plant_stage_event(plant, next_stage)}. "
                    f"{_garden_coin_amount(reward, signed=True)}"
                ),
            )
            if next_stage == "rare":
                self._grant_reward_bundle(
                    f"full_bloom:{plant.plant_id}",
                    source="full_bloom",
                    source_id=plant.plant_id,
                    reason=plant_stage_event(plant, "rare"),
                    scheduler_day=self.state.daily_stats.day,
                    correlation_id=self._current_correlation_id or f"full_bloom:{plant.plant_id}",
                    inventory_items={"growth_charge_small": 1},
                    title="Full Bloom",
                )
                if self._reward_applied(f"full_bloom:{plant.plant_id}"):
                    plant.full_bloom_reward_claimed = True

    def _apply_direct_growth(
        self,
        plant: Plant | None,
        requested: int,
        *,
        stats_field: str,
        transition_source: str = "direct_reward",
    ) -> int:
        requested_points = max(0, int(requested))
        self._apply_direct_growth_units(
            plant,
            requested_points * GROWTH_UNITS_PER_POINT,
            stats_field=stats_field,
            transition_source=transition_source,
        )
        return requested_points

    def _apply_direct_growth_units(
        self,
        plant: Plant | None,
        requested_units: int,
        *,
        stats_field: str,
        transition_source: str = "direct_reward",
    ) -> GrowthGrantResult:
        units = max(0, int(requested_units))
        if units <= 0:
            return GrowthGrantResult(0, 0, 0, ())
        result = self._route_growth_units(
            plant,
            units,
            role=("charge" if stats_field == "charge_growth" else "instant"),
            transition_source=transition_source,
            event_ms=self._now_ms(),
        )
        stats = self.state.daily_stats
        if stats_field == "charge_growth":
            target_map = stats.plant_charge_growth
        elif stats_field == "direct_reward_growth":
            target_map = stats.plant_direct_reward_growth
        else:
            raise ValueError(f"unsupported direct Growth source: {stats_field}")
        for allocation in result.allocations:
            applied_points = max(0, int(allocation.applied_units)) // GROWTH_UNITS_PER_POINT
            target_map[allocation.plant_id] = target_map.get(allocation.plant_id, 0) + applied_points
            if hasattr(stats, "plant_applied_growth_units"):
                stats.plant_applied_growth_units[allocation.plant_id] = (
                    stats.plant_applied_growth_units.get(allocation.plant_id, 0)
                    + max(0, int(allocation.applied_units))
                )
            if hasattr(stats, "plant_instant_growth_units"):
                stats.plant_instant_growth_units[allocation.plant_id] = (
                    stats.plant_instant_growth_units.get(allocation.plant_id, 0)
                    + max(0, int(allocation.applied_units))
                )
        for field_name, value in (
            ("instant_growth_units", result.requested_units),
            ("applied_growth_units", result.applied_units),
            ("redirected_growth_units", sum(
                allocation.applied_units for allocation in result.allocations
                if allocation.redirected
            )),
            ("stored_growth_units", result.stored_units),
        ):
            if hasattr(stats, field_name):
                setattr(stats, field_name, max(0, int(getattr(stats, field_name, 0) or 0)) + max(0, int(value)))
        stats.reconcile_growth_totals()
        return result

    def all_due_rewards(self) -> tuple[int, int]:
        """Compatibility name for the Today’s Cards reward values."""

        coins = self.ALL_DUE_BASE_COINS + (
            self.CLOUDY_ALL_DUE_BONUS_COINS
            if FEATURE_EFFECT_KEYS[self.active_garden_feature_id()]
            == "completion_coins_plus_5" else 0
        )
        return coins, 0

    def today_cards_reward_summary(self) -> dict[str, Any]:
        """Quote the daily completion reward, or read its committed Coin amounts."""
        day = self.state.daily_stats.day
        earned = bool(self.state.daily_completion.reward_claimed)
        if earned:
            keys = [f"all_due:{day}"]
            keys.extend(key for key in (f"harvest-bell:{day}",
                        f"achievement-trophy:garden_journal:{day}") if self._reward_applied(key))
            amounts = [self.earned_coin_total(key) for key in keys]
            coins = sum(amounts) if all(value is not None for value in amounts) else None
        else:
            coins = self.quote_completion_coins().total_coins
        prism = (self.state.prism_released_anki_day_id == day if earned
                 else self.active_garden_feature_id() == "prism_trellis")
        growth = next(item.amount for item in GARDEN_FEATURE_CATALOG["prism_trellis"].effects
                      if item.effect_id == "prism_completion_growth_100") if prism else 0
        return {"earned": earned, "coins": coins, "completion_coins": coins, "growth": growth}

    def study_rewards_summary(self) -> dict[str, Any]:
        """Read-only daily reward amounts and achievement-owned Growth progress."""
        from .earned_coins import quote_earned_coins

        day = self.state.daily_stats.day
        first_earned = self._reward_applied(f"daily_activity:{day}")
        first_coins = (self.earned_coin_total(f"daily_activity:{day}") if first_earned
                       else quote_earned_coins(self.DAILY_ACTIVITY_COINS,
                            active_scenery_id=self.locked_environment_id("scenery"),
                            carry_units=self.state.autumn_coin_carry_units).total_coins)
        percent, next_tier = streak_growth_progress(self.state)
        return {"first_earned": first_earned, "first_coins": first_coins,
                "completion": self.today_cards_reward_summary(),
                "growth_percent": percent,
                "next_tier_days": next_tier.progress_target if next_tier else None,
                "next_tier_percent": next_tier.reward.permanent_growth_percent if next_tier else None,
                "achievement_id": next_tier.achievement_id if next_tier else "streak_365"}

    @staticmethod
    def _cards_remaining_copy(count: int) -> str:
        remaining = max(0, int(count))
        return (
            "1 card remaining"
            if remaining == 1
            else f"{remaining:,} cards remaining"
        )

    def _waiting_cards_copy(self, count: int, due_at_ms: int) -> str:
        waiting = max(0, int(count))
        if due_at_ms > 0:
            minutes = max(
                1,
                int(math.ceil((due_at_ms - self._now_ms()) / 60_000)),
            )
            card_word = "card" if waiting == 1 else "cards"
            return (
                f"{waiting:,} more {card_word} will be due in "
                f"{minutes:,} {'minute' if minutes == 1 else 'minutes'}"
            )
        return self._cards_remaining_copy(waiting)

    @classmethod
    def _today_cards_complete_copy(cls, cards_completed: int) -> str:
        return (
            "TODAY’S CARDS COMPLETE\n"
            f"+{cls.ALL_DUE_BASE_COINS} Garden Coins earned\n"
            f"{max(0, int(cards_completed)):,} cards complete"
        )

    @staticmethod
    def _today_cards_ineligible_copy() -> str:
        return "NO COMPLETION REWARD TODAY\nNo cards were due today!"

    @staticmethod
    def _today_cards_unavailable_copy() -> str:
        return (
            "CARD STATUS UNAVAILABLE\n"
            "Anki Garden could not verify today’s cards. "
            "Normal Garden Growth is unaffected."
        )

    def _update_daily_completion(
        self,
        status: DueObligationStatus | None,
        *,
        preserve_start: bool = True,
        record_completed_delta: bool = False,
        completed_obligation_limit: int = 1,
    ) -> DailyCompletionState:
        day = self.state.daily_stats.day
        current = self.state.daily_completion
        if current.scheduler_day != day:
            current = DailyCompletionState(scheduler_day=day)
            self.state.daily_completion = current
        reviewed_today = max(0, int(self.state.daily_stats.reviewed))
        reviews_today = getattr(self.storage, "reviews_today", None)
        if callable(reviews_today):
            try:
                reviewed_today = max(0, int(reviews_today()))
            except Exception:
                logger.debug(
                    "Anki Garden: global scheduler-day review count unavailable",
                    exc_info=True,
                )
        current.cards_completed_today = reviewed_today
        if status is None or not status.available or status.error:
            current.status = "unavailable"
            current.unavailable_reason = "verification_failed"
            return current

        previous_remaining = sum((
            max(0, int(current.remaining_new_cards)),
            max(0, int(current.remaining_required_reviews)),
            max(0, int(current.remaining_learning_steps)),
            max(0, int(current.future_learning_steps_before_cutoff)),
        ))
        remaining = max(0, int(status.remaining))
        future = max(0, min(
            remaining,
            int(getattr(status, "future_learning_count", 0) or 0),
        ))
        current_due = max(
            0,
            int(getattr(status, "currently_due", remaining - future)),
        )
        current.remaining_new_cards = max(
            0, int(getattr(status, "new_count", 0) or 0)
        )
        current.remaining_required_reviews = max(
            0, int(getattr(status, "review_count", 0) or 0)
        )
        current.remaining_learning_steps = max(
            0,
            int(getattr(status, "learning_count", 0) or 0) - future,
        )
        current.future_learning_steps_before_cutoff = future
        current.next_learning_due_at_ms = max(
            0, int(getattr(status, "next_learning_due_at_ms", 0) or 0)
        )
        current.cutoff_at_ms = max(
            0, int(getattr(status, "cutoff_at_ms", 0) or 0)
        )
        if not current.cutoff_at_ms:
            cutoff = getattr(self.storage, "current_day_end_ms", None)
            if callable(cutoff):
                try:
                    current.cutoff_at_ms = max(0, int(cutoff()))
                except Exception:
                    current.cutoff_at_ms = 0
        # This projection counts scheduler obligations, not answer events. A
        # New card that moves into Learn therefore stays outstanding, and a
        # repeated/relearning answer does not advance completed progress until
        # that obligation leaves the unified New/Learn/Review scope.
        projection_was_initialized = bool(
            current.obligation_projection_initialized
        )
        if not preserve_start or not projection_was_initialized:
            obligation_total = remaining
            obligation_completed = 0
            current.unresolved_obligation_disappearances = 0
            current.obligation_projection_initialized = True
        else:
            previous_completed = max(
                0, int(current.starting_required_cards_completed)
            )
            # Only the scheduler state sampled as part of a committed answer
            # can prove that a shrinking queue represents completed work.
            # Read-only refreshes may instead reflect bury/suspend or a limit
            # change, so they rebase the denominator and preserve progress.
            obligation_completed = previous_completed
            if record_completed_delta and remaining < previous_remaining:
                queue_shrink = previous_remaining - remaining
                completion_cap = max(0, int(completed_obligation_limit))
                requested_ids = tuple(
                    int(card_id)
                    for card_id in getattr(status, "committed_card_ids", ())
                    if int(card_id) > 0
                )
                if requested_ids:
                    if status.committed_card_classification_complete:
                        transition_states = {
                            int(card_id): str(state)
                            for card_id, state in status.card_transitions
                        }
                        completion_cap = min(
                            completion_cap,
                            sum(
                                transition_states.get(card_id) == "completed"
                                for card_id in requested_ids
                            ),
                        )
                    else:
                        completion_cap = 0
                proven_completed = min(queue_shrink, completion_cap)
                obligation_completed += proven_completed
                current.unresolved_obligation_disappearances += max(
                    0, queue_shrink - proven_completed
                )
            obligation_total = obligation_completed + remaining
        current.starting_required_cards = obligation_total
        current.starting_required_cards_completed = obligation_completed
        current.unavailable_reason = ""
        unverified_completion = bool(
            projection_was_initialized
            and not record_completed_delta
            and previous_remaining > 0
            and remaining == 0
            and not current.reward_claimed
        )
        if (
            self.state.daily_stats.due_started_with_cards is False
            and not current.reward_claimed
        ):
            current.status = "not_eligible"
        elif unverified_completion:
            current.status = "unavailable"
            current.unavailable_reason = "completion_unverified"
        elif current.unresolved_obligation_disappearances > 0:
            current.status = "unavailable"
            current.unavailable_reason = (
                "auto_buried_sibling_obligation"
                if getattr(status, "buried_sibling_card_ids", ())
                else "obligation_disappearance_unverified"
            )
        elif remaining == 0:
            current.status = "complete"
        elif current_due == 0 and future > 0:
            current.status = "waiting_for_learning"
        else:
            current.status = "in_progress"
        return current

    def observe_due_start(self, status: DueObligationStatus | None) -> bool:
        """Persist today's collection-wide card baseline before the first card."""
        if getattr(self.storage, "runtime_pending", False) and not getattr(self.storage, "_allow_runtime_commit", False):
            return self.state.daily_stats.due_started_with_cards is True
        self.rollover_if_needed()
        stats = self.state.daily_stats
        if stats.reviewed > 0 or stats.due_started_with_cards is not None:
            return stats.due_started_with_cards is True
        snapshot = self._state_snapshot()
        if status is None or not status.available or status.error:
            stats.due_started_with_cards = None
            self._update_daily_completion(status, preserve_start=False)
        else:
            stats.due_started_with_cards = status.remaining > 0
            completion = self._update_daily_completion(
                status, preserve_start=False
            )
            if status.remaining <= 0:
                completion.status = "not_eligible"
        self._persist_or_restore(snapshot)
        return stats.due_started_with_cards is True

    def today_cards_status(
        self,
        status: DueObligationStatus | None = None,
    ) -> DailyCompletionState:
        """Return the current Today’s Cards projection without granting rewards."""
        if getattr(self.storage, "runtime_pending", False) and not getattr(self.storage, "_allow_runtime_commit", False):
            return self.state.daily_completion
        if status is None:
            resolver = getattr(self.storage, "due_obligations", None)
            status = resolver() if callable(resolver) else None
        return self._update_daily_completion(status)

    def evaluate_today_cards(
        self,
        status: DueObligationStatus | None = None,
        *,
        persist: bool = True,
        correlation_id: str = "",
        record_completed_delta: bool = False,
        completed_obligation_limit: int = 1,
        emit_feedback: bool = True,
    ) -> tuple[bool, str]:
        """Grant the once-daily reward when every Today’s Card is complete."""

        self.last_completion_result = CompletionResult()
        self.rollover_if_needed(persist=persist)
        snapshot = self._state_snapshot() if persist else None
        transition_snapshot = list(self._pending_stage_transitions)
        stats = self.state.daily_stats
        if status is None:
            resolver = getattr(self.storage, "due_obligations", None)
            status = resolver() if callable(resolver) else None
        previous_completion = self.state.daily_completion
        projection_was_initialized = bool(
            previous_completion.scheduler_day == stats.day
            and previous_completion.obligation_projection_initialized
        )
        previous_remaining = sum((
            max(0, int(previous_completion.remaining_new_cards)),
            max(0, int(previous_completion.remaining_required_reviews)),
            max(0, int(previous_completion.remaining_learning_steps)),
            max(
                0,
                int(previous_completion.future_learning_steps_before_cutoff),
            ),
        ))
        previous_completed = max(
            0,
            int(previous_completion.starting_required_cards_completed),
        )
        completion = self._update_daily_completion(
            status,
            record_completed_delta=record_completed_delta,
            completed_obligation_limit=completed_obligation_limit,
        )
        committed_completion_delta = bool(
            record_completed_delta
            and max(0, int(completed_obligation_limit)) > 0
            and projection_was_initialized
            and status is not None
            and status.available
            and not status.error
            and max(0, int(status.remaining)) < previous_remaining
            and completion.starting_required_cards_completed > previous_completed
            and completion.unresolved_obligation_disappearances == 0
        )

        def persist_status(message: str) -> tuple[bool, str]:
            if not persist:
                return False, message
            try:
                assert snapshot is not None
                self._persist_or_restore(snapshot)
            except Exception:
                self._pending_stage_transitions = transition_snapshot
                self._restore_state(snapshot)
                return False, self._today_cards_unavailable_copy()
            return False, message

        if stats.completed_due_cards or completion.reward_claimed:
            if completion.status == "complete":
                message = self._today_cards_complete_copy(
                    completion.starting_required_cards_completed
                )
            elif completion.status == "waiting_for_learning":
                message = self._waiting_cards_copy(
                    completion.future_learning_steps_before_cutoff,
                    completion.next_learning_due_at_ms,
                )
            else:
                message = self._cards_remaining_copy(
                    max(0, int(getattr(status, "remaining", 0) or 0))
                )
            return persist_status(message)
        if stats.due_started_with_cards is False:
            completion.status = "not_eligible"
            return persist_status(self._today_cards_ineligible_copy())
        if (
            stats.due_started_with_cards is not True
            or status is None
            or not status.available
            or status.error
        ):
            completion.status = "unavailable"
            completion.unavailable_reason = "verification_failed"
            return persist_status(self._today_cards_unavailable_copy())
        if completion.unresolved_obligation_disappearances > 0:
            completion.status = "unavailable"
            if not completion.unavailable_reason:
                completion.unavailable_reason = (
                    "auto_buried_sibling_obligation"
                    if getattr(status, "buried_sibling_card_ids", ())
                    else "obligation_disappearance_unverified"
                )
            return persist_status(self._today_cards_unavailable_copy())
        if status.complete and not committed_completion_delta:
            completion.status = "unavailable"
            completion.unavailable_reason = "completion_unverified"
            return persist_status(self._today_cards_unavailable_copy())
        if not self._reward_applied(f"daily_activity:{stats.day}"):
            return persist_status(self._cards_remaining_copy(status.remaining))
        if not self.state.starter_selection_complete:
            return persist_status(self._cards_remaining_copy(status.remaining))
        if not status.complete:
            message = (
                self._waiting_cards_copy(
                    completion.future_learning_steps_before_cutoff,
                    completion.next_learning_due_at_ms,
                )
                if completion.status == "waiting_for_learning"
                else self._cards_remaining_copy(status.remaining)
            )
            return persist_status(message)
        try:
            if not self.state.reward_state_initialized:
                self.initialize_reward_state(persist=False)
            self._lock_daily_loadout(event_ms=self._now_ms())
            stats.completed_due_cards = True
            completion.status = "complete"
            completion.reward_claimed = True
            completion.remaining_new_cards = 0
            completion.remaining_required_reviews = 0
            completion.remaining_learning_steps = 0
            completion.future_learning_steps_before_cutoff = 0
            completion.next_learning_due_at_ms = 0
            coin_reward, configured_growth = self.all_due_rewards()
            active_effect = FEATURE_EFFECT_KEYS[self.active_garden_feature_id()]
            harvest_coins = 5 if active_effect == "completion_coins_plus_5" else 0
            reward_correlation_id = (
                str(correlation_id).strip() or f"today-cards:{stats.day}"
            )
            existing_receipts = tuple(self.state.recent_reward_receipts)
            self._grant_reward_bundle(
                f"all_due:{stats.day}",
                source="todays_cards",
                source_id=stats.day,
                reason="Today’s cards complete",
                scheduler_day=stats.day,
                correlation_id=reward_correlation_id,
                coins=max(0, coin_reward - harvest_coins),
                growth=configured_growth,
                plant=self.active_plant(),
                title="Today’s cards complete",
            )
            journal_coins = trophy_effects(
                self.state, event_ms=self._now_ms()
            ).completion_coins
            if journal_coins:
                self._grant_reward_bundle(
                    f"achievement-trophy:garden_journal:{stats.day}",
                    source="achievement_trophy",
                    source_id="garden_journal",
                    reason="Garden Journal",
                    scheduler_day=stats.day,
                    correlation_id=reward_correlation_id,
                    coins=journal_coins,
                    title="Garden Journal",
                    description="Today’s Cards completed",
                )
            if harvest_coins:
                self._grant_reward_bundle(
                    f"harvest-bell:{stats.day}",
                    source="harvest_bell",
                    source_id="harvest_bell",
                    reason="Harvest Bell",
                    scheduler_day=stats.day,
                    correlation_id=reward_correlation_id,
                    coins=harvest_coins,
                    title="Harvest Bell",
                    description="Today’s Cards completed",
                )
            prism_units = 0
            prism_destination = ""
            prism_destination_kind = ""
            prism_destination_id = ""
            prism_grant = GrowthGrantResult(0, 0, 0)
            if active_effect == "prism_completion_growth_100":
                prism_effect = next(
                    item for item in GARDEN_FEATURE_CATALOG["prism_trellis"].effects
                    if item.effect_id == active_effect
                )
                prism_units = prism_effect.amount * GROWTH_UNITS_PER_POINT
                if prism_units:
                    prism_grant = self._apply_direct_growth_units(
                        self.active_plant(),
                        prism_units,
                        stats_field="direct_reward_growth",
                        transition_source="prism_harvest",
                    )
                    prism_destination = (
                        "mixed"
                        if prism_grant.project_units
                        and prism_grant.stored_units
                        else
                        "growth_project"
                        if prism_grant.project_units
                        and not prism_grant.applied_units
                        and not prism_grant.stored_units
                        else
                        "stored_growth"
                        if prism_grant.stored_units and not prism_grant.applied_units
                        else "plant_growth"
                    )
                    if prism_grant.project_allocations:
                        destination = prism_grant.project_allocations[0]
                        prism_destination_kind = destination.target_type.value
                        prism_destination_id = destination.target_id
                    elif prism_grant.stored_units:
                        prism_destination_kind = "stored_growth"
                        prism_destination_id = "stored_growth_balance"
                    elif prism_grant.applied_units:
                        prism_destination_kind = "plant"
                        prism_destination_id = str(
                            prism_grant.active_target_id
                            or prism_grant.original_target_id
                        )
                    aggregates = self.state.lifetime_economy_aggregates
                    aggregates.growth_generated_units += prism_grant.requested_units
                    aggregates.growth_applied_to_plants_units += (
                        prism_grant.applied_units
                    )
                    self._stage_economy_event(EconomyEventRecord(
                        event_key=f"prism-harvest-growth:{stats.day}",
                        event_kind="instant_growth",
                        source_id="prism_trellis",
                        scheduler_day=stats.day,
                        occurred_at=utc_now_iso(),
                        growth_earned_units=prism_grant.requested_units,
                        growth_flow_kind="generated",
                        growth_generated_units=prism_grant.requested_units,
                        growth_applied_to_plants_units=(
                            prism_grant.applied_units
                        ),
                        growth_routed_to_storage_units_lifetime=(
                            prism_grant.stored_units
                        ),
                        stored_growth_balance_delta_units=(
                            prism_grant.stored_units
                        ),
                        growth_contributed_to_landmarks_units=(
                            prism_grant.landmark_units
                        ),
                        growth_contributed_to_mastery_units=(
                            prism_grant.mastery_units
                        ),
                        growth_contributed_to_legacy_units=(
                            prism_grant.legacy_units
                        ),
                        metric_deltas=_project_allocation_metric_deltas(
                            prism_grant.project_allocations
                        ),
                    ))
                self.state.prism_released_anki_day_id = stats.day
            self.last_completion_result = CompletionResult(
                base_coins=self.ALL_DUE_BASE_COINS,
                harvest_bell_coins=harvest_coins,
                trophy_coins=journal_coins,
                prism_growth_released_units=prism_units,
                prism_growth_destination=prism_destination,
                prism_growth_destination_kind=prism_destination_kind,
                prism_growth_destination_id=prism_destination_id,
                prism_project_allocations=tuple(
                    prism_grant.project_allocations
                ),
            )
            if prism_units and emit_feedback:
                prism_value = prism_units / GROWTH_UNITS_PER_POINT
                self._queue_feedback(
                    f"prism-harvest:{stats.day}",
                    "garden_feature",
                    (
                        f"No unfinished plant was available. +{prism_value:g} Stored Growth"
                        if prism_destination == "stored_growth" else
                        f"Today’s Cards completed. +{prism_value:g} Growth toward your active project"
                        if prism_destination == "growth_project" else
                        f"Today’s Cards completed. +{prism_value:g} Growth split between your active project and Stored Growth"
                        if prism_destination == "mixed" else
                        f"Today’s Cards completed. +{prism_value:g} direct Growth"
                    ),
                    self.state.active_plant_id,
                    title="PRISM HARVEST",
                    asset_category="garden_features",
                    asset_key="garden_feature_prism_trellis",
                    amount=max(0, prism_units // GROWTH_UNITS_PER_POINT),
                    correlation_id=reward_correlation_id,
                )
            self._grant_completion_environment_gift(
                scheduler_day=stats.day,
                correlation_id=reward_correlation_id,
            )
            self._grant_environment_completion_pity(
                scheduler_day=stats.day,
                correlation_id=reward_correlation_id,
            )
            completion_achievement_unlocked = self._unlock_achievement(
                "all_due_done",
                completion_day=stats.day,
                correlation_id=reward_correlation_id,
            )
            self.state.first_daily_completion_reward_claimed = True
            aggregates = self.state.lifetime_economy_aggregates
            aggregates.today_cards_completions = max(
                0, int(aggregates.today_cards_completions)
            ) + 1
            self._update_achievements(
                correlation_id=reward_correlation_id
            )
            receipts = tuple(
                receipt
                for receipt in self.state.recent_reward_receipts
                if receipt not in existing_receipts
            )
            if emit_feedback:
                self._queue_reward_feedback(
                    reward_correlation_id,
                    receipts,
                    achievement_ids=("all_due_done",)
                    if completion_achievement_unlocked else (),
                    plant_id=self.state.active_plant_id,
                    title="Today’s cards complete",
                )
            if persist:
                assert snapshot is not None
                self._persist_or_restore(snapshot)
        except Exception:
            if not persist:
                raise
            self._pending_stage_transitions = transition_snapshot
            assert snapshot is not None
            self._restore_state(snapshot)
            return False, self._today_cards_unavailable_copy()
        return True, self._today_cards_complete_copy(
            completion.starting_required_cards_completed
        )

    def evaluate_all_due(
        self,
        status: DueObligationStatus | None = None,
        *,
        record_completed_delta: bool = False,
        completed_obligation_limit: int = 1,
    ) -> tuple[bool, str]:
        """Internal compatibility alias for older reviewer integrations."""

        return self.evaluate_today_cards(
            status,
            record_completed_delta=record_completed_delta,
            completed_obligation_limit=completed_obligation_limit,
        )

    @staticmethod
    def _committed_plant_snapshot(plant: Plant) -> CommittedPlantSnapshot:
        return CommittedPlantSnapshot(
            plant_id=str(plant.plant_id),
            name=str(PlantIdentity.from_plant(plant).display_name or "Plant"),
            species=str(plant.species or ""),
            stage=str(plant.growth_stage or ""),
            growth_units=max(0, int(plant.growth_units)),
            slot_index=(
                None if plant.slot_index is None else int(plant.slot_index)
            ),
            fully_grown=bool(plant.fully_grown),
        )

    @staticmethod
    def _reward_receipt_identity(receipt: RewardReceipt) -> tuple[Any, ...]:
        return (
            str(receipt.event_key),
            str(receipt.reward_type),
            str(receipt.source),
            str(receipt.source_id),
            str(receipt.correlation_id),
            int(receipt.amount),
            str(receipt.item_id),
            str(receipt.plant_id),
        )

    def _committed_answer_baseline(self) -> dict[str, Any]:
        mastery_funded = sum(
            max(0, int(units))
            for units in (
                self.state.cultivation_mastery
                .growth_units_funded_by_species.values()
            )
        )
        legacy_funded = (
            max(0, int(self.state.garden_legacy_level))
            * GARDEN_LEGACY_LEVEL_COST_UNITS
            + max(0, int(self.state.garden_legacy_progress_units))
        )
        return {
            "plants": tuple(
                self._committed_plant_snapshot(plant)
                for plant in self.state.plants
            ),
            "stored_growth_units": max(
                0, int(getattr(self.state, "stored_growth_units", 0) or 0)
            ),
            "landmark_growth_units": max(
                0, int(self.state.garden_project.landmark_growth_units_funded)
            ),
            "mastery_growth_units": mastery_funded,
            "mastery_growth_by_species": dict(
                self.state.cultivation_mastery.growth_units_funded_by_species
            ),
            "legacy_growth_units": legacy_funded,
            "active_plant_id": str(self.state.active_plant_id or ""),
            "transaction_ids": {
                str(transaction.transaction_id)
                for transaction in self.state.currency_transactions
            },
            "reward_receipts": {
                self._reward_receipt_identity(receipt)
                for receipt in self.state.recent_reward_receipts
            },
            "find_outcome_ids": {
                str(answer_key)
                for answer_key in self.state.garden_find_outcomes
            },
            "stage_transition_count": len(self._pending_stage_transitions),
        }

    @staticmethod
    def _answer_consumption_id(payload: Mapping[str, Any]) -> str:
        try:
            revlog_id = max(0, int(payload.get("revlog_id", 0) or 0))
        except (TypeError, ValueError):
            revlog_id = 0
        try:
            event_ms = max(
                0, int(payload.get("answered_at_ms", revlog_id) or revlog_id)
            )
        except (TypeError, ValueError):
            event_ms = revlog_id
        try:
            card_id = (
                int(payload.get("card_id"))
                if payload.get("card_id") is not None
                else None
            )
        except (TypeError, ValueError):
            card_id = None
        identity = stable_answer_event_identity(
            revlog_id,
            card_id=card_id,
            answered_at_ms=event_ms,
            lineage_id=(
                str(payload.get("answer_identity", "") or "").strip()
                or None
            ),
        )
        return consumption_id(identity)

    @classmethod
    def _answer_correlation_id(cls, payload: Mapping[str, Any]) -> str:
        return str(
            payload.get("correlation_id")
            or f"answer:{cls._answer_consumption_id(payload)}"
        )

    def _committed_answer_result(
        self,
        *,
        payload: Mapping[str, Any],
        award: ReviewAward,
        baseline: Mapping[str, Any],
    ) -> CommittedAnswerResult:
        previous_receipts = set(baseline.get("reward_receipts", set()) or set())
        previous_transactions = set(
            baseline.get("transaction_ids", set()) or set()
        )
        previous_find_ids = set(
            baseline.get("find_outcome_ids", set()) or set()
        )
        transition_index = max(
            0, int(baseline.get("stage_transition_count", 0) or 0)
        )
        origin = str(payload.get("origin", "") or "").strip()
        if not origin:
            origin = (
                "historical_sync"
                if bool(payload.get("historical_sync", False))
                else "local"
            )
        outcomes_by_key = {
            outcome.outcome_key: outcome
            for answer_key, outcome in self.state.garden_find_outcomes.items()
            if str(answer_key) not in previous_find_ids
        }
        # SQLite stages outcomes outside the bounded state cache. Read the
        # authoritative outcome for this answer before the transaction saves.
        answer_key = self._answer_consumption_id(payload)
        for pool_id in (STANDARD_POOL_ID, ENVIRONMENT_POOL_ID):
            outcome = self._garden_find_outcome(answer_key, pool_id)
            if outcome is not None and outcome.outcome_key not in previous_find_ids:
                outcomes_by_key[outcome.outcome_key] = outcome
        committed_find_outcomes = tuple(
            deepcopy(outcome) for outcome in outcomes_by_key.values()
        )
        # Completion rewards and direct Finds may fund the same target after
        # the ordinary answer award. Project every committed funding delta.
        project_deltas = [(
            GrowthTargetType.LANDMARK, "garden_landmark",
            self.state.garden_project.landmark_growth_units_funded
            - int(baseline.get("landmark_growth_units", 0)),
        )]
        previous_mastery = baseline.get("mastery_growth_by_species", {})
        project_deltas.extend(
            (GrowthTargetType.MASTERY, species_id,
             int(units) - int(previous_mastery.get(species_id, 0)))
            for species_id, units in sorted(
                self.state.cultivation_mastery.growth_units_funded_by_species.items()
            )
        )
        project_deltas.append((
            GrowthTargetType.LEGACY, "garden_legacy",
            self.state.garden_legacy_level * GARDEN_LEGACY_LEVEL_COST_UNITS
            + self.state.garden_legacy_progress_units
            - int(baseline.get("legacy_growth_units", 0)),
        ))
        project_allocations = tuple(
            ProjectGrowthAllocation(target_type, target_id, units)
            for target_type, target_id, units in project_deltas if units > 0
        )
        result = CommittedAnswerResult(
            event_id=str(award.correlation_id),
            correlation_id=str(award.correlation_id),
            scheduler_day=str(
                payload.get("scheduler_day") or self.state.daily_stats.day
            ),
            occurred_at_ms=max(
                0, int(payload.get("answered_at_ms", 0) or 0)
            ),
            origin=origin,
            award=award,
            reward_receipts=tuple(
                deepcopy(receipt)
                for receipt in self.state.recent_reward_receipts
                if self._reward_receipt_identity(receipt)
                not in previous_receipts
            ),
            currency_transactions=tuple(
                deepcopy(transaction)
                for transaction in self.state.currency_transactions
                if str(transaction.transaction_id) not in previous_transactions
            ),
            garden_find_outcomes=committed_find_outcomes,
            standard_find_count=sum(
                1
                for outcome in committed_find_outcomes
                if str(outcome.pool_id or "") == STANDARD_POOL_ID
                and str(outcome.status or "") == "hit"
            ),
            stage_transitions=tuple(
                self._pending_stage_transitions[transition_index:]
            ),
            plants_before=tuple(baseline.get("plants", ()) or ()),
            plants_after=tuple(
                self._committed_plant_snapshot(plant)
                for plant in self.state.plants
            ),
            stored_growth_before_units=max(
                0, int(baseline.get("stored_growth_units", 0) or 0)
            ),
            stored_growth_after_units=max(
                0, int(getattr(self.state, "stored_growth_units", 0) or 0)
            ),
            landmark_growth_before_units=max(
                0, int(baseline.get("landmark_growth_units", 0) or 0)
            ),
            landmark_growth_after_units=max(
                0,
                int(self.state.garden_project.landmark_growth_units_funded),
            ),
            mastery_growth_before_units=max(
                0, int(baseline.get("mastery_growth_units", 0) or 0)
            ),
            mastery_growth_after_units=sum(
                max(0, int(units))
                for units in (
                    self.state.cultivation_mastery
                    .growth_units_funded_by_species.values()
                )
            ),
            legacy_growth_before_units=max(
                0, int(baseline.get("legacy_growth_units", 0) or 0)
            ),
            legacy_growth_after_units=(
                max(0, int(self.state.garden_legacy_level))
                * GARDEN_LEGACY_LEVEL_COST_UNITS
                + max(0, int(self.state.garden_legacy_progress_units))
            ),
            project_allocations=project_allocations,
            active_plant_before_id=str(
                baseline.get("active_plant_id", "") or ""
            ),
            active_plant_after_id=str(self.state.active_plant_id or ""),
        )
        activity = getattr(self.storage, "stage_activity_answer", None)
        if callable(activity):
            activity(result, answer_key=answer_key,
                window_token=str(payload.get("review_window_token", "") or ""),
                batch_id=str(payload.get("activity_batch_id", "") or ""))
        return result

    @timed("review.engine")
    def apply_same_day_reviews_with_results(
        self,
        reviews: list[Dict[str, Any]],
        *,
        latest_revlog_id: int = 0,
        due_status: DueObligationStatus | None = None,
        collect_results: bool = True,
    ) -> tuple[CommittedAnswerResult, ...]:
        """Commit reviewer rows and return exact typed results.

        When ``due_status`` is supplied, a final-due completion reward is
        evaluated before the shared state/ledger commit and grouped under the
        last committed answer correlation.

        Annual production-parity replays may set ``collect_results=False`` to
        skip renderer-facing before/after snapshots that they do not consume.
        Every answer still traverses the same reward, state, ledger, due-card,
        and atomic persistence paths; the default typed-result contract is
        unchanged.
        """

        if not reviews:
            if latest_revlog_id > self.state.last_processed_revlog_id:
                snapshot = self._state_snapshot()
                self.state.last_processed_revlog_id = int(latest_revlog_id)
                self._persist_or_restore(snapshot)
            return ()
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        previous_correlation = self._current_correlation_id
        self.rollover_if_needed(persist=False)
        results: list[CommittedAnswerResult] = []
        committed_count = 0
        pending: tuple[
            Mapping[str, Any], ReviewAward, Mapping[str, Any]
        ] | None = None
        try:
            ordered = sorted(
                reviews, key=lambda row: int(row.get("revlog_id", 0) or 0)
            )
            for payload in ordered:
                if pending is not None:
                    previous_payload, previous_award, previous_baseline = pending
                    if collect_results:
                        results.append(self._committed_answer_result(
                            payload=previous_payload,
                            award=previous_award,
                            baseline=previous_baseline,
                        ))
                    committed_count += 1
                    pending = None
                baseline = (
                    self._committed_answer_baseline()
                    if collect_results else {}
                )
                self._current_correlation_id = self._answer_correlation_id(payload)
                award = self._register_review_in_memory(payload)
                if award.correlation_id:
                    pending = (payload, award, baseline)
            if pending is not None and due_status is not None:
                self._current_correlation_id = pending[1].correlation_id
                self.evaluate_today_cards(
                    due_status,
                    persist=False,
                    correlation_id=self._current_correlation_id,
                    record_completed_delta=True,
                    completed_obligation_limit=max(
                        1, committed_count + 1
                    ),
                )
            self.state.last_processed_revlog_id = max(
                self.state.last_processed_revlog_id,
                max(0, int(latest_revlog_id)),
            )
            if pending is not None:
                payload, award, baseline = pending
                if collect_results:
                    results.append(self._committed_answer_result(
                        payload=payload,
                        award=award,
                        baseline=baseline,
                    ))
            self._persist_or_restore(snapshot)
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise
        finally:
            self._current_correlation_id = previous_correlation
        return tuple(results)

    def commit_reviewer_answer(
        self,
        payload: Dict[str, Any],
        *,
        latest_revlog_id: int = 0,
        due_status: DueObligationStatus | None = None,
    ) -> CommittedAnswerResult | None:
        """Commit one local reviewer answer and its causal completion reward."""

        results = self.apply_same_day_reviews_with_results(
            [payload],
            latest_revlog_id=latest_revlog_id,
            due_status=due_status,
        )
        return results[0] if results else None

    def apply_same_day_reviews_with_awards(
        self,
        reviews: list[Dict[str, Any]],
        *,
        latest_revlog_id: int = 0,
    ) -> tuple[ReviewAward, ...]:
        """Commit review rows and return their exact engine-owned awards.

        The returned objects are produced by the same transaction that writes
        Growth and rewards.  Presentation surfaces can therefore report the
        committed per-card allocations without reconstructing them from UI
        values or mutable daily totals.
        """

        return tuple(
            result.award
            for result in self.apply_same_day_reviews_with_results(
                reviews,
                latest_revlog_id=latest_revlog_id,
            )
        )

    def apply_same_day_reviews(
        self,
        reviews: list[Dict[str, Any]],
        *,
        latest_revlog_id: int = 0,
    ) -> int:
        """Compatibility total for callers that do not need per-card facts."""

        return sum(
            award.total_growth
            for award in self.apply_same_day_reviews_with_awards(
                reviews,
                latest_revlog_id=latest_revlog_id,
            )
        )

    def _credit_currency(
        self,
        event_key: str,
        reason: str,
        amount: int,
        *,
        feedback: str = "",
        plant_id: str | None = None,
        source: str = "garden_reward",
        source_id: str = "",
        scheduler_day: str | None = None,
        correlation_id: str = "",
        included_in_total: bool = True,
    ) -> bool:
        receipts = self._grant_reward_bundle(
            event_key,
            source=source,
            source_id=source_id or event_key,
            reason=reason,
            scheduler_day=scheduler_day,
            correlation_id=(
                correlation_id
                or self._current_correlation_id
                or event_key
            ),
            coins=amount,
            coin_included_in_total=included_in_total,
            title=reason,
        )
        if feedback and receipts:
            self._queue_feedback(
                event_key,
                "currency",
                feedback,
                plant_id,
                correlation_id=(
                    correlation_id
                    or self._current_correlation_id
                    or event_key
                ),
            )
        return bool(receipts)

    def _debit_currency(self, event_key: str, reason: str, amount: int) -> bool:
        cost = max(0, int(amount))
        if cost <= 0 or self.state.currency_balance < cost:
            return False
        if any(tx.event_key == event_key for tx in self.state.currency_transactions):
            return False
        self.state.currency_balance -= cost
        self.state.currency_transactions.append(CurrencyTransaction(
            transaction_id=f"tx_{uuid.uuid4().hex}",
            event_key=event_key,
            reason=reason,
            delta=-cost,
            balance=self.state.currency_balance,
            occurred_at=utc_now_iso(),
            transaction_type="debit",
            source="purchase",
            source_id=event_key,
            scheduler_day=self.state.daily_stats.day,
            correlation_id=event_key,
        ))
        self.state.currency_transactions = self.state.currency_transactions[-500:]
        return True

    def _queue_feedback(
        self,
        event_id: str,
        kind: str,
        message: str,
        plant_id: str | None = None,
        *,
        title: str = "",
        asset_category: str = "",
        asset_key: str = "",
        amount: int = 0,
        correlation_id: str = "",
    ) -> bool:
        if any(event.event_id == event_id for event in self.state.pending_feedback):
            return False
        self.state.pending_feedback.append(FeedbackEvent(
            event_id=event_id,
            kind=kind,
            message=message,
            occurred_at=utc_now_iso(),
            plant_id=plant_id,
            title=title,
            asset_category=asset_category,
            asset_key=asset_key,
            amount=max(0, int(amount)),
            correlation_id=str(correlation_id),
        ))
        self.state.pending_feedback = self.state.pending_feedback[-100:]
        return True

    def peek_feedback(self) -> list[FeedbackEvent]:
        from .reward_presentation import reward_content_visible
        return [event for event in self.state.pending_feedback if reward_content_visible(event)]

    def consume_feedback(
        self,
        *,
        limit: int | None = None,
        event_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[FeedbackEvent]:
        if not self.state.pending_feedback:
            return []
        snapshot = self._state_snapshot()
        if event_ids is not None:
            expected = {str(event_id) for event_id in event_ids}
            consumed = [
                event for event in self.state.pending_feedback
                if event.event_id in expected
            ]
            if not consumed:
                return []
            self.state.pending_feedback = [
                event for event in self.state.pending_feedback
                if event.event_id not in expected
            ]
        else:
            count = len(self.state.pending_feedback) if limit is None else max(0, int(limit))
            consumed = self.state.pending_feedback[:count]
            self.state.pending_feedback = self.state.pending_feedback[count:]
        self._persist_or_restore(snapshot)
        return consumed

    def release_ready_species(self) -> list[str]:
        """Return species that have a complete current-scene release line."""
        ready = {
            species
            for species in self.assets.release_ready_plant_species(
                theme=self.config.value("visual_theme", "verdant_twilight"),
                geometry_version=6,
            )
            if species in PLANT_SPECIES
        }
        return [species for species in self.SPECIES_PRICES if species in ready]

    def catalog_summary(self) -> dict[str, Any]:
        """Return the data-driven Nursery sections and their dynamic counts."""
        release_ready = self.release_ready_species()
        owned_set = {
            species
            for species in [
                *self.state.unlocked_species,
                *(plant.species for plant in self.state.plants),
            ]
            if species in PLANT_SPECIES
        }
        owned = [species for species in PLANT_SPECIES_ORDER if species in owned_set]
        available = [species for species in release_ready if species not in owned_set]
        return {
            "release_ready_species": list(release_ready),
            "owned_species": owned,
            "available_species": available,
            "owned_count": len(owned),
            "available_count": len(available),
        }

    def environment_catalog_summary(self) -> dict[str, Any]:
        return {
            kind: [
                {
                    "item": item,
                    "owned": self.owns_environment(kind, item.item_id),
                    "equipped": (
                        self.state.loadout.display_decoration_id if kind == "garden_feature"
                        else self.state.loadout.display_scenery_id
                    ) == item.item_id,
                    "displayed_in_garden": (
                        self.state.loadout.display_decoration_id if kind == "garden_feature"
                        else self.state.loadout.display_scenery_id
                    ) == item.item_id,
                    "hidden": False,
                    "visible": True,
                }
                for item in catalog.values()
            ]
            for kind, catalog in ENVIRONMENT_CATALOG.items()
        }

    def environment_drop_odds(self) -> dict[str, Any]:
        finds_today, _reward_counts = self._garden_find_counts(
            self.state.daily_stats.day
        )
        standard_bands = [
            {
                "first_answer": int(band.first_answer),
                "last_answer": int(band.last_answer),
                "numerator": int(band.numerator),
                "denominator": int(band.denominator),
            }
            for band in STANDARD_DROUGHT_SCHEDULE
        ]
        special_bands = [
            {
                "tier": tier,
                "numerator": 1,
                "denominator": (
                    ultra_denominator(self.state.garden_find_ultra_misses)
                    if tier == "ultra_environment"
                    else int(denominator)
                ),
                "base_denominator": int(denominator),
            }
            for tier, denominator in ENVIRONMENT_TIER_DENOMINATORS.items()
        ]
        return {
            "drought_misses": int(self.state.garden_find_drought_count),
            "finds_today": int(finds_today),
            "daily_cap": standard_daily_cap(self.state.daily_stats.reviewed),
            "standard_bands": standard_bands,
            "ultra_pity_misses": int(self.state.garden_find_ultra_misses),
            "ultra_denominator": ultra_denominator(
                self.state.garden_find_ultra_misses
            ),
            "bands": special_bands,
        }

    @staticmethod
    def _purchase_quote_token(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _duration_label(seconds: int) -> str:
        total_minutes = max(1, int(math.ceil(max(0, seconds) / 60)))
        hours, minutes = divmod(total_minutes, 60)
        if not hours:
            return f"{minutes} {'minute' if minutes == 1 else 'minutes'}"
        hour_text = f"{hours} {'hour' if hours == 1 else 'hours'}"
        if not minutes:
            return hour_text
        return f"{hour_text} {minutes} minutes"

    @classmethod
    def booster_descriptor(cls) -> EffectDescriptor:
        """Return the canonical learner-facing Booster Potion contract."""

        return EffectDescriptor(
            function="Adds Growth while you complete cards.",
            buff=(
                f"+{cls.BOOSTER_GROWTH_PER_ANSWER:,} Growth per card."
            ),
            activation_condition="Use on a nurtured plant that is still growing.",
            duration=f"Applies to the next {cls.BOOSTER_CARD_COUNT:,} cards.",
            stacking="Another Potion adds more cards, up to five active doses.",
            replacement="Replaces nothing.",
            unlock_requirement=(
                "Earn from a Standard Find or Scenery reward."
            ),
        )

    @staticmethod
    def _unavailable_descriptor(message: str) -> EffectDescriptor:
        return EffectDescriptor(
            function="Unavailable.",
            buff="None.",
            activation_condition="Not available.",
            duration="None.",
            stacking="None.",
            replacement="None.",
            unlock_requirement=message,
        )

    def _make_purchase_quote(
        self,
        *,
        kind: PurchaseKind,
        item_id: str,
        item_name: str,
        category: str,
        artwork_category: str,
        artwork_key: str,
        unit_price: int,
        disposition: PurchaseDisposition,
        descriptor: EffectDescriptor,
        target_id: str | None = None,
        target_name: str = "",
        status: PurchaseStatus = PurchaseStatus.READY,
        message: str = "",
        replacement_required: bool = False,
        current_item_name: str = "",
        current_effect: str = "",
        current_duration: str = "",
        current_seconds_remaining: int = 0,
        duration_seconds: int = 0,
        resulting_seconds_remaining: int = 0,
        current_cards_remaining: int = 0,
        card_count: int = 0,
        resulting_cards_remaining: int = 0,
        queued_doses: int = 0,
        fertilizer_stored_item_disposition: (
            FertilizerStoredItemDisposition | None
        ) = None,
        duration_delta_seconds: int = 0,
        card_queue_delta: int = 0,
        fertilizer_expires_at_ms: int | None = None,
        inventory_before: int = 0,
        inventory_after: int = 0,
        current_equipped_name: str = "",
        state_signature: Any = None,
    ) -> PurchaseQuote:
        price = max(0, int(unit_price))
        balance = max(0, int(self.state.currency_balance))
        effective_status = status
        effective_message = str(message)
        if getattr(self.storage, "runtime_pending", False):
            effective_status = PurchaseStatus.ITEM_UNAVAILABLE
            effective_message = RUNTIME_WAIT_MESSAGE
        if effective_status is PurchaseStatus.READY and balance < price:
            effective_status = PurchaseStatus.INSUFFICIENT_COINS
            shortfall = price - balance
            effective_message = (
                f"You need {shortfall:,} more "
                f"{'Garden Coin' if shortfall == 1 else 'Garden Coins'} "
                f"to buy {item_name}."
            )
        token = self._purchase_quote_token({
            "schema": 1,
            "kind": kind.value,
            "item_id": item_id,
            "price": price,
            "balance": balance,
            "target_id": target_id,
            "disposition": disposition.value,
            "status": effective_status.value,
            "replacement_required": bool(replacement_required),
            "state": state_signature,
        })
        return PurchaseQuote(
            kind=kind,
            item_id=item_id,
            item_name=item_name,
            category=category,
            artwork_category=artwork_category,
            artwork_key=artwork_key,
            quantity=1,
            unit_price=price,
            balance_before=balance,
            balance_after=balance - price,
            target_id=target_id,
            target_name=target_name,
            disposition=disposition,
            descriptor=descriptor,
            quote_token=token,
            status=effective_status,
            message=effective_message,
            replacement_required=bool(replacement_required),
            current_item_name=current_item_name,
            current_effect=current_effect,
            current_duration=current_duration,
            current_seconds_remaining=max(0, int(current_seconds_remaining)),
            duration_seconds=max(0, int(duration_seconds)),
            resulting_seconds_remaining=max(0, int(resulting_seconds_remaining)),
            inventory_before=max(0, int(inventory_before)),
            inventory_after=max(0, int(inventory_after)),
            current_equipped_name=str(current_equipped_name or ""),
            current_cards_remaining=max(0, int(current_cards_remaining)),
            card_count=max(0, int(card_count)),
            resulting_cards_remaining=max(0, int(resulting_cards_remaining)),
            queued_doses=max(0, int(queued_doses)),
            fertilizer_stored_item_disposition=(
                fertilizer_stored_item_disposition
            ),
            duration_delta_seconds=max(0, int(duration_delta_seconds)),
            card_queue_delta=max(0, int(card_queue_delta)),
            fertilizer_expires_at_ms=fertilizer_expires_at_ms,
            destination_kind=("garden" if target_id == self.GARDEN_SUPPLY_TARGET else "plant" if target_id else "inventory"),
        )

    def quote_purchase(
        self,
        kind: PurchaseKind | str,
        item_id: str,
        *,
        quantity: int = 1,
        target_id: str | None = None,
    ) -> PurchaseQuote:
        """Build one current, renderer-neutral Garden Coin purchase quote."""

        purchase_kind = (
            kind if isinstance(kind, PurchaseKind) else PurchaseKind(str(kind))
        )
        normalized_item = str(item_id or "")
        if int(quantity) != 1:
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=normalized_item,
                item_name="Unavailable item",
                category="Garden item",
                artwork_category="ui",
                artwork_key="missing",
                unit_price=0,
                disposition=PurchaseDisposition.INVENTORY,
                descriptor=self._unavailable_descriptor(
                    "Garden purchases currently use a quantity of one."
                ),
                status=PurchaseStatus.ITEM_UNAVAILABLE,
                message="Garden purchases currently use a quantity of one.",
                state_signature={"quantity": quantity},
            )

        if purchase_kind is PurchaseKind.SPECIES:
            species = normalized_item.lower()
            name = plant_stage_title(species, "seed")
            price = self.SPECIES_PRICES.get(species)
            descriptor = EffectDescriptor(
                function=f"Adds {species.replace('_', ' ').title()} to your collection.",
                buff="Each card adds Growth while this plant is nurtured.",
                activation_condition="Place in a garden bed, then nurture.",
                duration="Stays in your collection.",
                stacking="One purchase per species.",
                replacement="Replaces nothing.",
                unlock_requirement="Choose a free starter first.",
            )
            status = PurchaseStatus.READY
            message = ""
            if price is None or species not in self.release_ready_species():
                status = PurchaseStatus.ITEM_UNAVAILABLE
                message = "That species is no longer available in the Nursery."
            elif not self.state.starter_selection_complete:
                status = PurchaseStatus.TARGET_INVALID
                message = "Choose your starter before buying another plant."
            elif species in self.state.unlocked_species or any(
                plant.species == species for plant in self.state.plants
            ):
                status = PurchaseStatus.ALREADY_OWNED
                message = f"{name} is already in your collection."
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=species,
                item_name=name,
                category="Plant",
                artwork_category="plant",
                artwork_key=species,
                unit_price=int(price or 0),
                disposition=PurchaseDisposition.COLLECTION,
                descriptor=descriptor,
                status=status,
                message=message,
                inventory_before=0,
                inventory_after=1,
                state_signature={
                    "starter_complete": bool(self.state.starter_selection_complete),
                    "owned": species in self.state.unlocked_species or any(
                        plant.species == species for plant in self.state.plants
                    ),
                    "release_ready": species in self.release_ready_species(),
                },
            )

        if purchase_kind is PurchaseKind.GROWTH_CHARGE:
            spec = GROWTH_CHARGES.get(normalized_item)
            if spec is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=normalized_item,
                    item_name="Growth Charge",
                    category="Growth Charge",
                    artwork_category="ui",
                    artwork_key=normalized_item or "growth_charge_small",
                    unit_price=0,
                    disposition=PurchaseDisposition.INVENTORY,
                    descriptor=self._unavailable_descriptor(
                        "This item is unavailable right now."
                    ),
                    status=PurchaseStatus.ITEM_UNAVAILABLE,
                    message="This item is unavailable right now.",
                    state_signature={"available": False},
                )
            status = PurchaseStatus.READY
            message = ""
            inventory_before = max(
                0, int(self.state.consumables.get(spec.charge_id, 0))
            )
            if not spec.purchasable or spec.price is None:
                status = PurchaseStatus.ITEM_UNAVAILABLE
                message = "This item is unavailable right now."
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=spec.charge_id,
                item_name=spec.name,
                category="Growth Charge",
                artwork_category="ui",
                artwork_key=spec.charge_id,
                unit_price=int(spec.price or 0),
                disposition=PurchaseDisposition.INVENTORY,
                descriptor=spec.descriptor,
                status=status,
                message=message,
                inventory_before=inventory_before,
                inventory_after=inventory_before + 1,
                state_signature={
                    "growth": spec.growth,
                    "purchasable": spec.purchasable,
                    "inventory": inventory_before,
                },
            )

        if purchase_kind is PurchaseKind.COSMETIC:
            cosmetic = COSMETIC_BY_ID.get(normalized_item)
            if cosmetic is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=normalized_item,
                    item_name="Display Decoration",
                    category="Display Decoration",
                    artwork_category="cosmetics",
                    artwork_key=normalized_item or "garden_bench",
                    unit_price=0,
                    disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
                    descriptor=self._unavailable_descriptor(
                        "That Display Decoration is unavailable."
                    ),
                    status=PurchaseStatus.ITEM_UNAVAILABLE,
                    message="That Display Decoration is unavailable.",
                    state_signature={"available": False},
                )
            owned = cosmetic.cosmetic_id.value in self.state.inventory.get(
                "cosmetics", []
            )
            status = PurchaseStatus.READY
            message = ""
            if not cosmetic.purchasable or cosmetic.price_coins is None:
                status = PurchaseStatus.ITEM_UNAVAILABLE
                message = f"{cosmetic.display_name} is earned from an achievement."
            elif owned:
                status = PurchaseStatus.ALREADY_OWNED
                message = f"You already own {cosmetic.display_name}."
            descriptor = EffectDescriptor(
                function="Adds cosmetic artwork to your Display Decorations.",
                buff="Appearance only. No gameplay effect.",
                activation_condition="Choose it as the displayed decoration.",
                duration="Stays in your collection.",
                stacking="One Display Decoration is shown at a time.",
                replacement="Changing appearance never changes the active Garden Bonus.",
                unlock_requirement=(
                    f"Nursery: {_garden_coin_amount(int(cosmetic.price_coins or 0))}."
                    if cosmetic.purchasable
                    else "Earn from its achievement."
                ),
            )
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=cosmetic.cosmetic_id.value,
                item_name=cosmetic.display_name,
                category="Display Decoration",
                artwork_category="cosmetics",
                artwork_key=cosmetic.asset_id,
                unit_price=int(cosmetic.price_coins or 0),
                disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
                descriptor=descriptor,
                status=status,
                message=message,
                inventory_before=1 if owned else 0,
                inventory_after=1,
                state_signature={
                    "owned": owned,
                    "purchasable": cosmetic.purchasable,
                },
            )

        if purchase_kind is PurchaseKind.FERTILIZER:
            tier = normalized_item.lower()
            spec = self.FERTILIZERS.get(tier)
            plant = self._consumable_target(target_id) if target_id is not None else None
            garden = isinstance(plant, GardenCardEffects)
            target_name = "Garden" if garden else PlantIdentity.from_plant(plant).display_name
            if spec is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=tier,
                    item_name="Fertilizer",
                    category="Fertilizer",
                    artwork_category="ui",
                    artwork_key=f"fertilizer_{tier or 'basic'}",
                    unit_price=0,
                    disposition=PurchaseDisposition.APPLIED,
                    descriptor=self._unavailable_descriptor(
                        "That Fertilizer is no longer available."
                    ),
                    target_id=target_id,
                    status=PurchaseStatus.ITEM_UNAVAILABLE,
                    message="That Fertilizer is no longer available.",
                    state_signature={"available": False},
                )
            descriptor = EffectDescriptor(
                function="Adds Growth while you complete cards.",
                buff=(
                    f"+{spec.growth_per_answer:,} Growth per eligible "
                    "card answer."
                ),
                activation_condition="Use for garden-wide Growth." if garden else "Use on a nurtured plant that is still growing.",
                duration=f"Lasts {spec.card_count:,} eligible cards.",
                stacking="Same tier adds cards; a different tier waits its turn.",
                replacement="Remaining paid cards are never replaced.",
                unlock_requirement=f"Nursery: {_garden_coin_amount(spec.price)}.",
            )
            inventory_key = f"fertilizer_{tier}"
            inventory_before = max(
                0,
                int(self.state.consumables.get(inventory_key, 0) or 0),
            )
            if target_id is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=tier,
                    item_name=spec.name,
                    category="Fertilizer",
                    artwork_category="ui",
                    artwork_key=inventory_key,
                    unit_price=spec.price,
                    disposition=PurchaseDisposition.INVENTORY,
                    descriptor=descriptor,
                    inventory_before=inventory_before,
                    inventory_after=inventory_before + 1,
                    state_signature={
                        "inventory": inventory_before,
                        "target": None,
                    },
                )
            if plant is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=tier,
                    item_name=spec.name,
                    category="Fertilizer",
                    artwork_category="ui",
                    artwork_key=f"fertilizer_{tier}",
                    unit_price=spec.price,
                    disposition=PurchaseDisposition.APPLIED,
                    descriptor=descriptor,
                    target_id=target_id,
                    target_name=target_name,
                    status=PurchaseStatus.TARGET_INVALID,
                    message=f"This plant can’t use {spec.name}.",
                    state_signature={
                        "target_exists": plant is not None,
                        "active_plant_id": self.state.active_plant_id,
                    },
                )
            self._promote_card_effect_queue(plant, "fertilizer")
            active_batches, queued_batches = self._card_effect_lists(
                plant, "fertilizer"
            )
            live_batches = [
                batch
                for batch in (*active_batches, *queued_batches)
                if int(batch.remaining_cards) > 0
            ]
            tail = live_batches[-1] if live_batches else None
            extending = bool(
                tail is not None
                and str(tail.effect_id) == f"fertilizer_{tier}"
            )
            queuing = bool(tail is not None and not extending)
            dose_count = len(live_batches)
            status = (
                PurchaseStatus.TARGET_INVALID
                if dose_count >= self.EFFECT_DOSE_CAP
                else PurchaseStatus.READY
            )
            message = (
                f"{target_name} already has five Fertilizer doses."
                if status is PurchaseStatus.TARGET_INVALID else ""
            )
            # Bind confirmation copy to the last scheduled card batch.
            predecessor_batch = tail
            predecessor_tier = (
                str(predecessor_batch.effect_id).removeprefix("fertilizer_")
                if predecessor_batch is not None
                else ""
            )
            predecessor_spec = self.FERTILIZERS.get(predecessor_tier)
            predecessor_cards = (
                max(0, int(predecessor_batch.remaining_cards))
                if predecessor_batch is not None else 0
            )
            scheduled_cards = sum(
                max(0, int(batch.remaining_cards)) for batch in live_batches
            )
            disposition = (
                PurchaseDisposition.EXTENDED
                if extending
                else PurchaseDisposition.QUEUED
                if queuing
                else PurchaseDisposition.APPLIED
            )
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=tier,
                item_name=spec.name,
                category="Fertilizer",
                artwork_category="ui",
                artwork_key=f"fertilizer_{tier}",
                unit_price=spec.price,
                disposition=disposition,
                descriptor=descriptor,
                target_id=str(target_id),
                target_name=target_name,
                status=status,
                message=message,
                replacement_required=False,
                current_item_name=(
                    str(getattr(predecessor_spec, "name", "Fertilizer"))
                    if predecessor_batch is not None
                    else ""
                ),
                current_effect=(
                    f"+{int(predecessor_batch.growth_per_card_units) // GROWTH_UNITS_PER_POINT:,} Growth per eligible card"
                    if predecessor_batch is not None
                    else ""
                ),
                current_duration=(
                    f"{predecessor_cards:,} cards remaining"
                    if predecessor_batch is not None
                    else ""
                ),
                current_cards_remaining=predecessor_cards,
                card_count=spec.card_count,
                resulting_cards_remaining=scheduled_cards + spec.card_count,
                queued_doses=len(queued_batches) + (1 if queuing else 0),
                fertilizer_stored_item_disposition=(
                    FertilizerStoredItemDisposition.QUEUE
                    if live_batches
                    else FertilizerStoredItemDisposition.USE
                ),
                card_queue_delta=spec.card_count,
                state_signature={
                    "plant_id": str(target_id),
                    "planted": bool(getattr(plant, "planted", False)),
                    "fully_grown": bool(getattr(plant, "fully_grown", False)),
                    "garden": garden,
                    "active_plant_id": self.state.active_plant_id,
                    "fertilizer_batches": [
                        (
                            batch.effect_id,
                            batch.growth_per_card_units,
                            batch.total_cards,
                            batch.remaining_cards,
                        )
                        for batch in live_batches
                    ],
                },
            )

        if purchase_kind in {PurchaseKind.GARDEN_FEATURE, PurchaseKind.SCENERY}:
            environment_kind = purchase_kind.value
            item = environment_item(environment_kind, normalized_item)
            if item is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=normalized_item,
                    item_name="Garden Decoration or Scenery",
                    category=(
                        "Garden decorations"
                        if purchase_kind is PurchaseKind.GARDEN_FEATURE
                        else "Scenery"
                    ),
                    artwork_category=(
                        "garden_features"
                        if purchase_kind is PurchaseKind.GARDEN_FEATURE
                        else "backgrounds"
                    ),
                    artwork_key=normalized_item or "missing",
                    unit_price=0,
                    disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
                    descriptor=self._unavailable_descriptor(
                        "That Nursery item is no longer available."
                    ),
                    status=PurchaseStatus.ITEM_UNAVAILABLE,
                    message="That Nursery item is no longer available.",
                    state_signature={"available": False},
                )
            owned = self.owns_environment(environment_kind, item.item_id)
            status = PurchaseStatus.READY
            message = ""
            if owned:
                status = PurchaseStatus.ALREADY_OWNED
                message = f"You already own {item.name}."
            elif not item.purchasable or item.price is None:
                status = PurchaseStatus.ITEM_UNAVAILABLE
                message = f"{item.name} can only be earned while reviewing cards."
            current_equipped = (
                GARDEN_FEATURE_CATALOG.get(
                    str(self.state.loadout.active_garden_bonus_id)
                )
                if item.kind == "garden_feature"
                else SCENERY_CATALOG.get(
                    str(self.state.loadout.active_scenery_effect_id)
                )
            )
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=item.item_id,
                item_name=item.name,
                category="Garden decorations" if item.kind == "garden_feature" else "Scenery",
                artwork_category="garden_features" if item.kind == "garden_feature" else "backgrounds",
                artwork_key=item.item_id,
                unit_price=int(item.price or 0),
                disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
                descriptor=item.descriptor,
                status=status,
                message=message,
                current_equipped_name=(
                    current_equipped.name if current_equipped is not None else ""
                ),
                state_signature={
                    "owned": owned,
                    "acquisition": item.acquisition,
                    "selected": (
                        self.state.loadout.active_garden_bonus_id == item.item_id
                        if item.kind == "garden_feature"
                        else self.state.loadout.active_scenery_effect_id
                        == item.item_id
                    ),
                },
            )

        current_index = int(self.state.unlocked_slots)
        current_item_id = f"bed_{min(MAX_GARDEN_SLOTS, current_index + 1)}"
        descriptor = EffectDescriptor(
            function="Adds another permanent planting space as the garden grows.",
            buff=(
                "Beds 3 through 6 are earned at Mature and unique Full Bloom "
                "collection milestones. Each other planted bed adds one "
                f"{trophy_effects(self.state).shared_growth_percent}% Shared Growth lane."
            ),
            activation_condition="Granted automatically when its milestone is committed.",
            duration="Stays unlocked.",
            stacking="Beds unlock sequentially.",
            replacement="Replaces nothing and moves no plants.",
            unlock_requirement="Progress plants and complete the botanical collection.",
        )
        status = PurchaseStatus.ITEM_UNAVAILABLE
        message = (
            "Garden beds are earned from plant progression and are no longer sold."
        )
        if current_index >= MAX_GARDEN_SLOTS:
            status = PurchaseStatus.ALREADY_OWNED
            message = "All six garden beds are already unlocked."
        return self._make_purchase_quote(
            kind=purchase_kind,
            item_id=current_item_id,
            item_name=f"Garden Bed {current_index + 1}",
            category="Garden bed",
            artwork_category="ui",
            artwork_key="garden_bed",
            unit_price=0,
            disposition=PurchaseDisposition.UNLOCKED,
            descriptor=descriptor,
            status=status,
            message=message,
            state_signature={
                "unlocked_slots": current_index,
                "starter_complete": bool(self.state.starter_selection_complete),
            },
        )

    def purchase_projection(
        self,
        kind: PurchaseKind | str,
        item_id: str,
        *,
        quantity: int = 1,
        target_id: str | None = None,
    ) -> PurchaseProjection:
        """Return action, price, balance, and disposition as separate fields."""

        return build_purchase_projection(self.quote_purchase(
            kind,
            item_id,
            quantity=quantity,
            target_id=target_id,
        ))

    @staticmethod
    def _purchase_failure(
        quote: PurchaseQuote,
        status: PurchaseStatus,
        message: str,
        *,
        balance: int | None = None,
    ) -> PurchaseOutcome:
        return PurchaseOutcome(
            status=status,
            item_id=quote.item_id,
            item_name=quote.item_name,
            category=quote.category,
            quantity=quote.quantity,
            amount_spent=0,
            new_balance=(quote.balance_before if balance is None else max(0, int(balance))),
            disposition=quote.disposition,
            message=message,
        )

    def confirm_purchase(self, request: PurchaseRequest) -> PurchaseOutcome:
        """Revalidate and atomically persist one idempotent purchase request."""

        request_fingerprint = request.fingerprint()
        permanent_lookup = getattr(self.storage, "idempotency_record", None)
        permanent = (
            permanent_lookup("purchase", str(request.request_id))
            if callable(permanent_lookup) and str(request.request_id)
            else None
        )
        if permanent is not None:
            restored = PurchaseOutcome.from_dict(dict(permanent.outcome))
            if (
                permanent.request_fingerprint == request_fingerprint
                and restored is not None
            ):
                return restored
            replay_quote = self.quote_purchase(
                request.kind,
                request.item_id,
                quantity=request.quantity,
                target_id=request.target_id,
            )
            return self._purchase_failure(
                replay_quote,
                PurchaseStatus.REQUEST_ID_CONFLICT,
                "Purchase failed. No Garden Coins were spent.",
                balance=self.state.currency_balance,
            )
        completed = next((
            record
            for record in self.state.completed_purchase_requests
            if record.request_id == request.request_id
        ), None)
        if completed is not None:
            if completed.request_fingerprint == request_fingerprint:
                return completed.outcome
            replay_quote = self.quote_purchase(
                request.kind,
                request.item_id,
                quantity=request.quantity,
                target_id=request.target_id,
            )
            return self._purchase_failure(
                replay_quote,
                PurchaseStatus.REQUEST_ID_CONFLICT,
                "Purchase failed. No Garden Coins were spent.",
                balance=self.state.currency_balance,
            )

        current = self.quote_purchase(
            request.kind,
            request.item_id,
            quantity=request.quantity,
            target_id=request.target_id,
        )
        try:
            canonical_request_id = str(uuid.UUID(str(request.request_id)))
        except (ValueError, TypeError, AttributeError):
            return self._purchase_failure(
                current,
                PurchaseStatus.REQUEST_ID_CONFLICT,
                "Purchase failed. No Garden Coins were spent.",
                balance=self.state.currency_balance,
            )
        if not isinstance(request.request_id, str) or request.request_id != canonical_request_id:
            return self._purchase_failure(
                current,
                PurchaseStatus.REQUEST_ID_CONFLICT,
                "Purchase failed. No Garden Coins were spent.",
                balance=self.state.currency_balance,
            )
        if current.item_id != request.item_id:
            return self._purchase_failure(
                current,
                PurchaseStatus.STALE_TARGET,
                "Item updated.",
                balance=self.state.currency_balance,
            )
        if current.status in {
            PurchaseStatus.ITEM_UNAVAILABLE,
            PurchaseStatus.ALREADY_OWNED,
            PurchaseStatus.TARGET_INVALID,
            PurchaseStatus.STALE_TARGET,
        }:
            return self._purchase_failure(
                current,
                current.status,
                current.message,
                balance=self.state.currency_balance,
            )
        if current.total_price != int(request.expected_price):
            return self._purchase_failure(
                current,
                PurchaseStatus.STALE_PRICE,
                (
                    f"The price changed from {int(request.expected_price):,} to "
                    f"{current.total_price:,} Garden Coins. Review the new price."
                ),
                balance=self.state.currency_balance,
            )
        if current.balance_before != int(request.expected_balance):
            return self._purchase_failure(
                current,
                PurchaseStatus.STALE_BALANCE,
                (
                    f"Your Garden Coin balance changed from "
                    f"{int(request.expected_balance):,} to {current.balance_before:,}. "
                    "Review the updated balance."
                ),
                balance=self.state.currency_balance,
            )
        if current.status is PurchaseStatus.INSUFFICIENT_COINS:
            return self._purchase_failure(
                current,
                PurchaseStatus.INSUFFICIENT_COINS,
                current.message,
                balance=self.state.currency_balance,
            )
        if current.quote_token != request.quote_token:
            return self._purchase_failure(
                current,
                PurchaseStatus.STALE_TARGET,
                "The item changed. Review it before buying.",
                balance=self.state.currency_balance,
            )
        snapshot = self._state_snapshot()
        event_key = f"purchase-request:{request.request_id}"
        try:
            outcome = self._apply_confirmed_purchase(current, event_key)
            if not outcome.success:
                self._restore_state(snapshot)
                return outcome
            occurred_at = utc_now_iso()
            self.state.completed_purchase_requests.append(CompletedPurchaseRequest(
                request_id=request.request_id,
                request_fingerprint=request_fingerprint,
                outcome=outcome,
                occurred_at=occurred_at,
            ))
            self.state.completed_purchase_requests = (
                self.state.completed_purchase_requests[-MAX_COMPLETED_PURCHASE_REQUESTS:]
            )
            permanent_stager = getattr(
                self.storage, "stage_idempotency_record", None
            )
            if callable(permanent_stager):
                permanent_stager(IdempotencyRecord(
                    operation_kind="purchase",
                    operation_id=request.request_id,
                    request_fingerprint=request_fingerprint,
                    outcome=outcome.to_dict(),
                    occurred_at=occurred_at,
                    scheduler_day=self.state.daily_stats.day,
                ))
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"purchase:{request.request_id}",
                event_kind="purchase",
                sink_id=f"{request.kind.value}:{request.item_id}",
                scheduler_day=self.state.daily_stats.day,
                occurred_at=occurred_at,
                coins_spent=outcome.amount_spent,
                item_id=request.item_id,
                quantity=1,
            ))
            self._persist_or_restore(snapshot)
            return outcome
        except Exception:
            logger.exception(
                "Anki Garden: Garden Coin purchase could not be persisted",
                extra={
                    "purchase_kind": current.kind.value,
                    "purchase_item_id": current.item_id,
                    "purchase_request_id": request.request_id,
                },
            )
            self._restore_state(snapshot)
            return self._purchase_failure(
                current,
                PurchaseStatus.PERSISTENCE_FAILURE,
                "Purchase failed. No Garden Coins were spent.",
                balance=self.state.currency_balance,
            )

    def _apply_confirmed_purchase(
        self,
        quote: PurchaseQuote,
        event_key: str,
    ) -> PurchaseOutcome:
        fertilizer_target: Plant | GardenCardEffects | None = None
        if (
            quote.kind is PurchaseKind.FERTILIZER
            and quote.disposition is not PurchaseDisposition.INVENTORY
        ):
            spec = self.FERTILIZERS[quote.item_id]
            fertilizer_target = self._consumable_target(str(quote.target_id or ""))
            if fertilizer_target is None:
                return self._purchase_failure(
                    quote,
                    PurchaseStatus.TARGET_INVALID,
                    f"This plant can’t use {spec.name}.",
                    balance=self.state.currency_balance,
                )
        presentation = purchase_presentation(quote, ignore_status=True)
        if not self._debit_currency(
            event_key,
            presentation.activity_label,
            quote.total_price,
        ):
            return self._purchase_failure(
                quote,
                PurchaseStatus.INSUFFICIENT_COINS,
                f"{quote.item_name} costs {_garden_coin_amount(quote.total_price)}.",
                balance=self.state.currency_balance,
            )

        result_id = ""
        message = presentation.success_message
        next_actions = presentation.next_actions
        applied = False
        equipped = False

        if quote.kind is PurchaseKind.SPECIES:
            species = quote.item_id
            plant = Plant(
                plant_id=f"plant_{uuid.uuid4().hex[:12]}",
                species=species,
                name=self._generated_name(species),
                slot_index=None,
                personality=self.SPECIES_PERSONALITY.get(species, "balanced"),
                planted_on=self.state.daily_stats.day,
                memories=[
                    PlantMemory("planted", "planted", self.state.daily_stats.day)
                ],
            )
            self.state.unlocked_species.append(species)
            self.state.plants.append(plant)
            result_id = plant.plant_id
            self._queue_feedback(
                event_key,
                "unlock",
                message,
                plant.plant_id,
                title=message.rstrip("."),
                asset_category="plant",
                asset_key=species,
                amount=1,
            )

        elif quote.kind is PurchaseKind.GROWTH_CHARGE:
            self.state.consumables[quote.item_id] = (
                self.state.consumables.get(quote.item_id, 0) + quote.quantity
            )
            self._queue_feedback(
                event_key,
                "charge_purchase",
                message,
                title=message.rstrip("."),
                asset_category="ui",
                asset_key=quote.item_id,
                amount=quote.quantity,
            )

        elif quote.kind in {PurchaseKind.GARDEN_FEATURE, PurchaseKind.SCENERY}:
            if quote.kind is PurchaseKind.GARDEN_FEATURE:
                self.state.inventory.setdefault("garden_features", []).append(quote.item_id)
            else:
                self.state.inventory.setdefault("scenery", []).append(quote.item_id)
            self._queue_feedback(
                event_key,
                "environment_purchase",
                message,
                title=message.rstrip("."),
                asset_category=quote.artwork_category,
                asset_key=quote.artwork_key,
                amount=1,
            )

        elif quote.kind is PurchaseKind.COSMETIC:
            self.state.inventory.setdefault("cosmetics", []).append(quote.item_id)
            result_id = quote.item_id
            self._queue_feedback(
                event_key,
                "cosmetic_purchase",
                message,
                title=message.rstrip("."),
                asset_category="cosmetics",
                asset_key=quote.artwork_key,
                amount=1,
            )

        elif quote.kind is PurchaseKind.FERTILIZER:
            spec = self.FERTILIZERS[quote.item_id]
            inventory_key = f"fertilizer_{spec.tier}"
            if quote.disposition is PurchaseDisposition.INVENTORY:
                self.state.consumables[inventory_key] = (
                    max(0, int(self.state.consumables.get(inventory_key, 0) or 0))
                    + quote.quantity
                )
                result_id = inventory_key
                self._queue_feedback(
                    event_key,
                    "fertilizer_inventory",
                    message,
                    title=message.rstrip("."),
                    asset_category="ui",
                    asset_key=inventory_key,
                    amount=quote.quantity,
                )
                return PurchaseOutcome(
                    status=PurchaseStatus.SUCCESS,
                    item_id=quote.item_id,
                    item_name=quote.item_name,
                    category=quote.category,
                    quantity=quote.quantity,
                    amount_spent=quote.total_price,
                    new_balance=max(0, int(self.state.currency_balance)),
                    disposition=quote.disposition,
                    message=message,
                    next_actions=next_actions,
                    result_id=result_id,
                    applied=False,
                    equipped=False,
                    fertilizer_stored_item_disposition=(
                        quote.fertilizer_stored_item_disposition
                    ),
                    duration_delta_seconds=quote.duration_delta_seconds,
                    card_queue_delta=quote.card_queue_delta,
                    fertilizer_expires_at_ms=(
                        quote.fertilizer_expires_at_ms
                    ),
                )
            plant = fertilizer_target
            assert plant is not None
            self._lock_scenery_loadout(event_ms=self._now_ms())
            now = self._now_seconds()
            action = self._activate_fertilizer_effect(
                plant,
                spec,
                now=now,
                source_event_key=event_key,
            )
            applied = True
            result_id = str(quote.target_id)
            self._queue_feedback(
                event_key,
                "fertilizer",
                message,
                "" if isinstance(plant, GardenCardEffects) else plant.plant_id,
                title=message.rstrip("."),
                asset_category="ui",
                asset_key=f"fertilizer_{spec.tier}",
                amount=1,
            )

        elif quote.kind is PurchaseKind.BED:
            # Quotes for beds are permanently unavailable in the release
            # economy.  Keeping this explicit branch prevents a future
            # PurchaseKind from accidentally inheriting the legacy bed grant.
            return self._purchase_failure(
                quote,
                PurchaseStatus.ITEM_UNAVAILABLE,
                "Garden beds are earned from plant progression and are no longer sold.",
                balance=self.state.currency_balance,
            )

        else:  # pragma: no cover - defensive guard for a future PurchaseKind
            raise ValueError(f"unsupported purchase kind: {quote.kind!r}")

        return PurchaseOutcome(
            status=PurchaseStatus.SUCCESS,
            item_id=quote.item_id,
            item_name=quote.item_name,
            category=quote.category,
            quantity=quote.quantity,
            amount_spent=quote.total_price,
            new_balance=max(0, int(self.state.currency_balance)),
            disposition=quote.disposition,
            message=message,
            next_actions=next_actions,
            result_id=result_id,
            destination_kind=quote.destination_kind,
            remaining_cards=quote.resulting_cards_remaining,
            applied=applied,
            equipped=equipped,
            fertilizer_stored_item_disposition=(
                quote.fertilizer_stored_item_disposition
                if quote.kind is PurchaseKind.FERTILIZER else None
            ),
            duration_delta_seconds=(
                quote.duration_delta_seconds
                if quote.kind is PurchaseKind.FERTILIZER else 0
            ),
            card_queue_delta=(
                quote.card_queue_delta
                if quote.kind is PurchaseKind.FERTILIZER else 0
            ),
            fertilizer_expires_at_ms=(
                quote.fertilizer_expires_at_ms
                if quote.kind is PurchaseKind.FERTILIZER else None
            ),
        )

    def _compat_purchase(
        self,
        kind: PurchaseKind,
        item_id: str,
        *,
        target_id: str | None = None,
        authorize_replacement: bool = False,
    ) -> PurchaseOutcome:
        """Keep legacy engine callers on the canonical transaction path."""

        quote = self.quote_purchase(kind, item_id, target_id=target_id)
        request = PurchaseRequest.from_quote(
            quote,
            authorize_replacement=authorize_replacement,
        )
        return self.confirm_purchase(request)

    def purchase_environment(self, kind: str, item_id: str) -> tuple[bool, str]:
        normalized_kind = "garden_feature" if str(kind) == "weather" else str(kind)
        try:
            purchase_kind = PurchaseKind(normalized_kind)
        except ValueError:
            return False, "Choose garden decorations or scenery."
        if purchase_kind not in {PurchaseKind.GARDEN_FEATURE, PurchaseKind.SCENERY}:
            return False, "Choose garden decorations or scenery."
        outcome = self._compat_purchase(purchase_kind, str(item_id))
        return outcome.success, outcome.message

    @_requires_ready_runtime()
    def equip_environment(self, kind: str, item_id: str) -> tuple[bool, str]:
        """Equip an owned item, committing its artwork and effect together."""
        normalized_kind = "garden_feature" if str(kind) == "weather" else str(kind)
        item_id = canonical_garden_feature_id(item_id) if normalized_kind == "garden_feature" else str(item_id)
        if normalized_kind not in {"garden_feature", "scenery"}:
            return False, "Choose garden decorations or scenery."
        state = self.state
        return self.apply_garden_appearance(
            item_id if normalized_kind == "garden_feature" else state.loadout.display_decoration_id,
            item_id if normalized_kind == "scenery" else state.loadout.display_scenery_id,
            state.loadout.visibility,
        )

    def display_garden_feature(self, item_id: str) -> tuple[bool, str]:
        """Compatibility alias for changing the Display Decoration."""

        return self.display_decoration(item_id)

    def apply_garden_appearance(
        self,
        display_decoration_id: str,
        display_scenery_id: str,
        visibility: Mapping[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Atomically equip both selections and their catalog effects."""

        self.rollover_if_needed()

        decoration_id = canonical_garden_feature_id(display_decoration_id)
        scenery_id = str(display_scenery_id)
        feature = environment_item("garden_feature", decoration_id)
        owns_decoration = bool(
            (
                feature is not None
                and self.owns_environment("garden_feature", feature.item_id)
            )
        )
        scenery = environment_item("scenery", scenery_id)
        owns_scenery = bool(
            scenery is not None
            and self.owns_environment("scenery", scenery.item_id)
        )
        if not owns_decoration:
            return False, "That Display Decoration is not owned."
        if not owns_scenery:
            return False, "That Scenery appearance is not owned."

        # Keep the legacy argument readable, but equipment always displays.
        desired_visibility = {"garden_feature": True, "scenery": True}
        if (self.state.loadout.display_decoration_id == decoration_id
                and self.state.loadout.display_scenery_id == scenery_id
                and self.state.loadout.visibility == desired_visibility):
            return True, "Already equipped."
        snapshot = self._state_snapshot()
        self.state.loadout.display_decoration_id = decoration_id
        self.state.loadout.display_scenery_id = scenery_id
        self.state.loadout.visibility.update(desired_visibility)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save changes. Your garden is unchanged."
        return True, "Garden updated."

    def display_decoration(self, item_id: str) -> tuple[bool, str]:
        """Compatibility alias for equipping a decoration."""
        return self.equip_environment("garden_feature", item_id)

    def purchase_cosmetic(self, item_id: str) -> tuple[bool, str]:
        outcome = self._compat_purchase(PurchaseKind.COSMETIC, str(item_id))
        return outcome.success, outcome.message

    def display_scenery(self, item_id: str) -> tuple[bool, str]:
        """Compatibility alias for equipping scenery."""
        return self.equip_environment("scenery", item_id)

    def set_environment_visibility(self, kind: str, enabled: bool) -> tuple[bool, str]:
        normalized_kind = str(kind)
        normalized_kind = "garden_feature" if normalized_kind == "weather" else normalized_kind
        if normalized_kind not in {"garden_feature", "scenery"}:
            return False, "Choose garden decorations or scenery."
        # Retired compatibility command: never hide equipment or write a save
        # just to change a display preference that is no longer supported.
        return True, "Equipped items are always displayed."

    def apply_environment_loadout(
        self,
        weather_id: str,
        scenery_id: str,
        visibility: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Compatibility wrapper for the Collection loadout transaction."""

        return self.apply_garden_loadout(
            canonical_garden_feature_id(weather_id),
            scenery_id,
            visibility,
        )

    def apply_garden_loadout(
        self,
        garden_feature_id: str,
        scenery_id: str,
        visibility: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Compatibility wrapper for the unified equipment transaction."""
        return self.apply_garden_appearance(garden_feature_id, scenery_id, visibility)

    def purchase_growth_charge(self, charge_id: str) -> tuple[bool, str]:
        outcome = self._compat_purchase(
            PurchaseKind.GROWTH_CHARGE,
            str(charge_id),
        )
        return outcome.success, outcome.message

    @staticmethod
    def _growth_stage_for_points(points: int) -> str:
        return stage_progress(points).stage

    def quote_growth_charge(
        self,
        charge_id: str,
        plant_id: str | None = None,
    ) -> GrowthChargeQuote:
        """Return an immutable, non-mutating Growth Charge projection."""

        normalized_charge = str(charge_id)
        normalized_target = self.consumable_target_id() if plant_id is None else str(plant_id)
        spec = GROWTH_CHARGES.get(normalized_charge)
        plant = self.plant_story(normalized_target)
        inventory = max(
            0,
            int(self.state.consumables.get(normalized_charge, 0) or 0),
        )
        garden = normalized_target == self.GARDEN_SUPPLY_TARGET and self.state.collection_complete
        if garden:
            target_state = GrowthChargeTargetState.GARDEN
        elif plant is None or plant not in self.state.plants:
            target_state = GrowthChargeTargetState.UNAVAILABLE
        elif not plant.planted:
            target_state = GrowthChargeTargetState.STORED
        elif plant.fully_grown:
            target_state = GrowthChargeTargetState.FULLY_GROWN
        else:
            target_state = GrowthChargeTargetState.ELIGIBLE
        valid_target = target_state in {GrowthChargeTargetState.ELIGIBLE, GrowthChargeTargetState.GARDEN}
        current_growth = max(0, int(getattr(plant, "growth_points", 0) or 0))
        requested = max(0, int(getattr(spec, "growth", 0) or 0))
        charge_projection = project_growth_charge_application(
            current_growth,
            requested,
            inventory,
            target_state=target_state,
        )
        granted = charge_projection.granted_growth if spec is not None else 0
        projected = charge_projection.projected_growth
        stage_rewards = (
            self._project_stage_rewards(current_growth, projected)
            if charge_projection.ready and not garden
            else ()
        )
        rewards = tuple(item[2] for item in stage_rewards)
        completed_stages = tuple(item[1] for item in stage_rewards)
        route_capacity = sum(max(0, GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT
                                 - self._plant_growth_units(candidate))
                             for candidate in self._growth_route_candidates(plant))
        overflow_units = max(0, granted * GROWTH_UNITS_PER_POINT - route_capacity)
        project_allocations, stored_units = self._project_active_growth_overflow(overflow_units)
        if spec is None:
            status = GrowthChargeStatus.TARGET_INVALID
            message = "Growth Charge unavailable."
        elif not valid_target:
            status = GrowthChargeStatus.TARGET_INVALID
            message = "This plant can’t use a Growth Charge."
        elif inventory <= 0:
            status = GrowthChargeStatus.EMPTY_INVENTORY
            message = "No Growth Charges."
        else:
            status = GrowthChargeStatus.READY
            message = ""
        token_payload = {
            "charge_id": normalized_charge,
            "target_id": normalized_target,
            "inventory": inventory,
            "current_growth": current_growth,
            "slot_index": getattr(plant, "slot_index", None),
            "species": str(getattr(plant, "species", "") or ""),
            "owned": bool(plant is not None and plant in self.state.plants),
            "planted": bool(getattr(plant, "planted", False)),
            "fully_grown": bool(getattr(plant, "fully_grown", False)),
            "eligible": valid_target,
            "target_state": target_state.value,
            "scenery": self.locked_environment_id("scenery"),
            "granted": granted,
            "route_capacity": [
                (candidate.plant_id, self._plant_growth_units(candidate))
                for candidate in self._growth_route_candidates(plant)
            ] if plant is not None else [],
            "stored_growth_units": max(
                0, int(getattr(self.state, "stored_growth_units", 0) or 0)
            ),
            "rewards": [reward.to_dict() for reward in rewards],
            "overflow_projects": [item.to_dict() for item in project_allocations],
            "active_growth_target": (self.state.active_growth_target_type, self.state.active_growth_target_id,
                                     self.state.active_growth_target_activation_identity),
        }
        quote_token = hashlib.sha256(json.dumps(
            token_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")).hexdigest()
        return GrowthChargeQuote(
            status=status,
            charge_id=normalized_charge,
            charge_name=str(getattr(spec, "name", "Growth Charge") or "Growth Charge"),
            target_id=normalized_target,
            target_name="Garden" if garden else str(PlantIdentity.from_plant(plant).display_name or "Plant"),
            target_species=str(getattr(plant, "species", "") or ""),
            target_stage="" if garden else self._growth_stage_for_points(current_growth),
            target_state=target_state,
            current_growth=current_growth,
            current_growth_units=self._plant_growth_units(plant) if plant is not None else 0,
            projected_growth_units=0 if garden else min(GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT,
                (self._plant_growth_units(plant) if plant is not None else 0) + granted * GROWTH_UNITS_PER_POINT),
            requested_growth=requested,
            granted_growth=granted,
            projected_growth=projected,
            projected_stage="" if garden else self._growth_stage_for_points(projected),
            completed_stages=completed_stages,
            rewards=rewards,
            inventory_before=inventory,
            inventory_after=charge_projection.inventory_after,
            quote_token=quote_token,
            message=message,
            destination_kind="garden" if garden else "plant",
            stored_growth_units=stored_units,
            project_allocations=project_allocations,
        )

    @staticmethod
    def _growth_charge_failure(
        quote: GrowthChargeQuote,
        status: GrowthChargeStatus,
        message: str,
    ) -> GrowthChargeOutcome:
        return GrowthChargeOutcome(
            status=status,
            charge_id=quote.charge_id,
            charge_name=quote.charge_name,
            target_id=quote.target_id,
            target_name=quote.target_name,
            previous_growth=quote.current_growth,
            resulting_growth=quote.current_growth,
            growth_granted=0,
            previous_stage=quote.target_stage,
            resulting_stage=quote.target_stage,
            completed_stages=(),
            rewards=(),
            inventory_remaining=quote.inventory_before,
            message=message,
            destination_kind=quote.destination_kind,
        )

    def confirm_growth_charge(
        self,
        request: GrowthChargeRequest,
    ) -> GrowthChargeOutcome:
        """Revalidate and atomically persist one idempotent Charge use."""

        if not isinstance(request, GrowthChargeRequest):
            quote = self.quote_growth_charge(
                str(getattr(request, "charge_id", "") or ""),
                str(getattr(request, "target_id", "") or ""),
            )
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.REQUEST_ID_CONFLICT,
                "This Growth Charge request is invalid. Start again.",
            )
        quote = self.quote_growth_charge(request.charge_id, request.target_id)
        try:
            canonical_request_id = str(uuid.UUID(str(request.request_id)))
        except (ValueError, TypeError, AttributeError):
            canonical_request_id = ""
        request_fields_valid = bool(
            isinstance(request.request_id, str)
            and request.request_id == canonical_request_id
            and isinstance(request.charge_id, str)
            and bool(request.charge_id)
            and isinstance(request.target_id, str)
            and bool(request.target_id)
            and isinstance(request.quote_token, str)
            and bool(request.quote_token)
            and isinstance(request.expected_inventory, int)
            and not isinstance(request.expected_inventory, bool)
            and request.expected_inventory >= 0
            and isinstance(request.expected_growth, int)
            and not isinstance(request.expected_growth, bool)
            and request.expected_growth >= 0
        )
        if not request_fields_valid:
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.REQUEST_ID_CONFLICT,
                "This Growth Charge request is invalid. Start again.",
            )
        request_fingerprint = request.fingerprint()
        permanent_lookup = getattr(self.storage, "idempotency_record", None)
        permanent = (
            permanent_lookup("growth_charge", request.request_id)
            if callable(permanent_lookup)
            else None
        )
        if permanent is not None:
            restored = GrowthChargeOutcome.from_dict(dict(permanent.outcome))
            if (
                permanent.request_fingerprint == request_fingerprint
                and restored is not None
            ):
                return restored
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.REQUEST_ID_CONFLICT,
                "This Growth Charge request conflicts with an earlier use. Start again.",
            )
        completed = next((
            record
            for record in self.state.completed_growth_charge_requests
            if record.request_id == request.request_id
        ), None)
        if completed is not None:
            if completed.request_fingerprint == request_fingerprint:
                return completed.outcome
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.REQUEST_ID_CONFLICT,
                "This Growth Charge request conflicts with an earlier use. Start again.",
            )
        if quote.status is GrowthChargeStatus.TARGET_INVALID:
            return self._growth_charge_failure(quote, quote.status, quote.message)
        if quote.inventory_before != int(request.expected_inventory):
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.STALE_INVENTORY,
                "Charge count updated.",
            )
        if quote.current_growth != int(request.expected_growth):
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.STALE_TARGET,
                "Plant Growth updated.",
            )
        if quote.status is GrowthChargeStatus.EMPTY_INVENTORY:
            return self._growth_charge_failure(quote, quote.status, quote.message)
        if quote.quote_token != request.quote_token:
            return self._growth_charge_failure(
                quote,
                GrowthChargeStatus.STALE_TARGET,
                "Plant Growth updated.",
            )

        plant = self.plant_story(request.target_id)
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        try:
            self._lock_scenery_loadout(event_ms=self._now_ms())
            self.state.consumables[quote.charge_id] -= 1
            growth_flow = self._apply_direct_growth_units(
                plant,
                quote.granted_growth * GROWTH_UNITS_PER_POINT,
                stats_field="charge_growth",
                transition_source="charge",
            )
            awarded = growth_flow.requested_units // GROWTH_UNITS_PER_POINT
            if awarded != quote.granted_growth or (plant is None and quote.destination_kind != "garden"):
                raise RuntimeError("Growth Charge projection changed during commit")
            aggregates = self.state.lifetime_economy_aggregates
            aggregates.growth_generated_units += growth_flow.requested_units
            aggregates.growth_applied_to_plants_units += growth_flow.applied_units
            self._update_achievements(
                correlation_id=f"growth-charge:{request.request_id}"
            )
            outcome = GrowthChargeOutcome(
                status=GrowthChargeStatus.SUCCESS,
                charge_id=quote.charge_id,
                charge_name=quote.charge_name,
                target_id=quote.target_id,
                target_name=quote.target_name,
                previous_growth=quote.current_growth,
                previous_growth_units=quote.current_growth_units,
                resulting_growth_units=self._plant_growth_units(plant) if plant else 0,
                resulting_growth=int(plant.growth_points) if plant else 0,
                growth_granted=awarded,
                previous_stage=quote.target_stage,
                resulting_stage=plant.growth_stage if plant else "",
                completed_stages=quote.completed_stages,
                rewards=quote.rewards,
                inventory_remaining=max(
                    0,
                    int(self.state.consumables.get(quote.charge_id, 0) or 0),
                ),
                message=self.growth_destination_text(growth_flow.stored_units, growth_flow.project_allocations)
                        if quote.destination_kind == "garden" else f"{awarded:,} Growth applied.",
                destination_kind=quote.destination_kind,
                stored_growth_units=growth_flow.stored_units,
                project_allocations=growth_flow.project_allocations,
            )
            self._queue_feedback(
                f"growth-charge-use:{request.request_id}",
                "growth_charge",
                outcome.message,
                plant.plant_id if plant else "",
                title=f"{awarded:,} Growth applied",
                asset_category="ui",
                asset_key=quote.charge_id,
                amount=awarded,
            )
            occurred_at = utc_now_iso()
            self.state.completed_growth_charge_requests.append(
                CompletedGrowthChargeRequest(
                    request_id=request.request_id,
                    request_fingerprint=request_fingerprint,
                    outcome=outcome,
                    occurred_at=occurred_at,
                )
            )
            self.state.completed_growth_charge_requests = (
                self.state.completed_growth_charge_requests[
                    -MAX_COMPLETED_GROWTH_CHARGE_REQUESTS:
                ]
            )
            permanent_stager = getattr(
                self.storage, "stage_idempotency_record", None
            )
            if callable(permanent_stager):
                permanent_stager(IdempotencyRecord(
                    operation_kind="growth_charge",
                    operation_id=request.request_id,
                    request_fingerprint=request_fingerprint,
                    outcome=outcome.to_dict(),
                    occurred_at=occurred_at,
                    scheduler_day=self.state.daily_stats.day,
                ))
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"growth-charge:{request.request_id}",
                event_kind="growth_charge_use",
                source_id=request.charge_id,
                scheduler_day=self.state.daily_stats.day,
                occurred_at=occurred_at,
                growth_earned_units=(
                    max(0, int(outcome.growth_granted))
                    * GROWTH_UNITS_PER_POINT
                ),
                growth_flow_kind="generated",
                growth_generated_units=growth_flow.requested_units,
                growth_applied_to_plants_units=growth_flow.applied_units,
                growth_routed_to_storage_units_lifetime=growth_flow.stored_units,
                stored_growth_balance_delta_units=growth_flow.stored_units,
                growth_contributed_to_landmarks_units=(
                    growth_flow.landmark_units
                ),
                growth_contributed_to_mastery_units=growth_flow.mastery_units,
                growth_contributed_to_legacy_units=growth_flow.legacy_units,
                item_id=request.charge_id,
                quantity=1,
                metric_deltas=_project_allocation_metric_deltas(
                    growth_flow.project_allocations,
                    existing={
                        "consumables_used": {request.charge_id: 1}
                    },
                ),
            ))
            self._persist_or_restore(snapshot)
            return outcome
        except Exception:
            logger.exception(
                "Anki Garden: Growth Charge use could not be persisted",
                extra={
                    "growth_charge_id": quote.charge_id,
                    "growth_charge_target_id": quote.target_id,
                    "growth_charge_request_id": request.request_id,
                },
            )
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            refreshed = self.quote_growth_charge(request.charge_id, request.target_id)
            return self._growth_charge_failure(
                refreshed,
                GrowthChargeStatus.PERSISTENCE_FAILURE,
                "Your charge was not used.",
            )

    def use_growth_charge(
        self,
        charge_id: str,
        plant_id: str | None = None,
    ) -> tuple[bool, str]:
        quote = self.quote_growth_charge(str(charge_id), plant_id)
        if not quote.ready:
            return False, quote.message
        outcome = self.confirm_growth_charge(GrowthChargeRequest.from_quote(quote))
        return outcome.success, outcome.message

    def overflow_destination_summary(self) -> str:
        """Describe the committed destination after unfinished plants are filled."""
        projects = self.growth_projects_snapshot()
        target = projects.active_target
        choice = next((item for item in projects.target_choices
                       if item.target == target and item.available
                       and growth_target_enabled(item.target.target_type)), None)
        if choice is None:
            return "Overflow becomes Stored Growth after unfinished plants."
        if target.target_type is GrowthTargetType.MASTERY:
            track = projects.mastery_track(target.target_id)
            destination = f"{target.target_id.replace('_', ' ').title()} Mastery"
        elif target.target_type is GrowthTargetType.LANDMARK:
            track = projects.landmark_track
            destination = "Garden Landmarks"
        else:
            track = projects.legacy_track
            destination = "Garden Legacy"
        if track.remaining_capacity_units == 0:
            return "Overflow becomes Stored Growth after unfinished plants."
        return f"Overflow goes to {destination} after unfinished plants."

    @staticmethod
    def growth_destination_text(stored_units: int, allocations: tuple) -> str:
        parts = [f"{item.units / GROWTH_UNITS_PER_POINT:,.0f} Growth to {item.target_id.replace('_', ' ').title()} Mastery"
                 for item in allocations]
        if stored_units:
            parts.append(f"{stored_units / GROWTH_UNITS_PER_POINT:,.0f} Stored Growth")
        return "; ".join(parts) + "."

    @staticmethod
    def _landmark_outcome_from_dict(value: Mapping[str, Any]) -> LandmarkOutcome | None:
        try:
            raw_snapshot = value["snapshot"]
            if not isinstance(raw_snapshot, Mapping):
                return None
            snapshot = landmark_snapshot(
                selected_landmark_id=raw_snapshot.get("selected_landmark_id", ""),
                contributed_growth_units=raw_snapshot.get(
                    "contributed_growth_units", 0
                ),
                ready_to_complete=raw_snapshot.get("ready_to_complete", False),
                completed_landmark_ids=raw_snapshot.get(
                    "completed_landmark_ids", ()
                ),
                displayed_landmark_id=raw_snapshot.get(
                    "displayed_landmark_id", ""
                ),
            )
            return LandmarkOutcome(
                request_id=str(value["request_id"]),
                request_fingerprint=str(value["request_fingerprint"]),
                action=LandmarkAction(str(value["action"])),
                landmark_id=str(value["landmark_id"]),
                disposition=ProgressionDisposition(str(value["disposition"])),
                applied=bool(value["applied"]),
                growth_spent_units=max(0, int(value["growth_spent_units"])),
                coins_spent=max(0, int(value["coins_spent"])),
                snapshot=snapshot,
                message=str(value["message"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _mastery_outcome_from_dict(value: Mapping[str, Any]) -> MasteryOutcome | None:
        try:
            raw_snapshot = value["snapshot"]
            if not isinstance(raw_snapshot, Mapping):
                return None
            raw_ranks = raw_snapshot.get("highest_rank_by_species", {})
            if not isinstance(raw_ranks, Mapping):
                return None
            snapshot = mastery_snapshot(raw_ranks)
            return MasteryOutcome(
                request_id=str(value["request_id"]),
                request_fingerprint=str(value["request_fingerprint"]),
                species_id=str(value["species_id"]),
                rank_id=str(value["rank_id"]),
                disposition=ProgressionDisposition(str(value["disposition"])),
                applied=bool(value["applied"]),
                growth_spent_units=max(0, int(value["growth_spent_units"])),
                coins_spent=max(0, int(value["coins_spent"])),
                snapshot=snapshot,
                message=str(value["message"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def landmark_catalog_summary(self) -> dict[str, Any]:
        projects = self.growth_projects_snapshot()
        track = projects.landmark_track
        active = projects.active_target
        landmark_active = bool(
            active is not None
            and active.target_type is GrowthTargetType.LANDMARK
        )
        claimed_ids = [row.tier_id for row in track.tiers if row.claimed]
        next_row = next((row for row in track.tiers if not row.claimed), None)
        selected = next_row.tier_id if landmark_active and next_row else ""
        displayed = str(
            self.state.garden_project.displayed_landmark_tier_id or ""
        )
        items: list[dict[str, Any]] = []
        previous_threshold = 0
        for row in track.tiers:
            required = (
                row.cumulative_growth_threshold_units - previous_threshold
            )
            contributed = max(0, min(
                required,
                track.growth_units_funded - previous_threshold,
            ))
            items.append({
                # Schema-26 renderer compatibility.
                "landmark_id": row.tier_id,
                "display_name": row.display_name,
                "contributed_growth_units": contributed,
                "required_growth_units": required,
                "ready_to_complete": row.claimable,
                "auto_contribute": landmark_active,
                "growth_cost_units": required,
                "coin_cost": row.coin_cost,
                "completed": row.claimed,
                "selected": row.tier_id == selected,
                "displayed": row.tier_id == displayed,
                # Schema-27 cumulative authority.
                "cumulative_growth_threshold_units": (
                    row.cumulative_growth_threshold_units
                ),
                "remaining_growth_units": row.remaining_growth_units,
                "funded": row.funded,
                "claimed": row.claimed,
                "claimable": row.claimable,
                "can_claim_now": row.can_claim_now,
                "state": row.state,
                "artwork_id": row.artwork_id,
                "effect_description": row.effect_description,
                "acquisition_route": row.acquisition_route,
                "allowed_actions": list(row.allowed_actions),
            })
            previous_threshold = row.cumulative_growth_threshold_units
        selected_item = next(
            (item for item in items if item["landmark_id"] == selected), None
        )
        return {
            "unlocked": projects.unlocked,
            "stored_growth_units": projects.stored_balance_units,
            "stored_growth_balance_units": projects.stored_balance_units,
            "auto_contribute": landmark_active,
            "selected_landmark_id": selected,
            "next_landmark_id": next_row.tier_id if next_row else None,
            "displayed_landmark_id": displayed,
            "completed_landmark_ids": claimed_ids,
            "contributed_growth_units": (
                int(selected_item["contributed_growth_units"])
                if selected_item else 0
            ),
            "required_growth_units": (
                int(selected_item["required_growth_units"])
                if selected_item else 0
            ),
            "ready_to_complete": bool(
                selected_item and selected_item["ready_to_complete"]
            ),
            "landmark_growth_units_funded": track.growth_units_funded,
            "remaining_capacity_units": track.remaining_capacity_units,
            "landmark_highest_claimed_tier": len(claimed_ids),
            "landmark_claimable_tiers": [
                row.tier_id for row in track.tiers if row.claimable
            ],
            "active_growth_target_type": (
                active.target_type.value if active is not None else ""
            ),
            "active_growth_target_id": (
                active.target_id if active is not None else ""
            ),
            "items": items,
            "growth_projects": projects.to_dict(),
        }

    def quote_landmark(self, request: LandmarkRequest) -> LandmarkQuote:
        quote = quote_landmark_request(
            self._landmark_snapshot(),
            request,
            available_growth_units=max(0, int(self.state.stored_growth_units)),
            available_coins=max(0, int(self.state.currency_balance)),
        )
        if not landmarks_enabled():
            return replace(
                quote,
                disposition=ProgressionDisposition.NOT_READY,
                can_apply=False,
                message="This Growth project is unavailable.",
                growth_spend_units=0,
                coin_spend=0,
            )
        if not self._landmark_unlocked():
            return replace(
                quote,
                disposition=ProgressionDisposition.NOT_READY,
                can_apply=False,
                message="Reach Full Bloom once to unlock Garden Landmarks.",
                growth_spend_units=0,
                coin_spend=0,
            )
        return quote

    def confirm_landmark(self, request: LandmarkRequest) -> LandmarkOutcome:
        if not isinstance(request, LandmarkRequest):
            raise TypeError("request must be a LandmarkRequest")
        lookup = getattr(self.storage, "idempotency_record", None)
        existing = (
            lookup("landmark", request.request_id) if callable(lookup) else None
        )
        if existing is not None:
            restored = self._landmark_outcome_from_dict(existing.outcome)
            if (
                existing.request_fingerprint == request.fingerprint
                and restored is not None
            ):
                return restored
            raise ValueError("That Landmark request ID was already used.")
        before = self._landmark_snapshot()
        quote = self.quote_landmark(request)
        if not quote.can_apply:
            return LandmarkOutcome(
                request.request_id,
                request.fingerprint,
                request.action,
                request.landmark_id,
                quote.disposition,
                False,
                0,
                0,
                before,
                quote.message,
            )
        outcome = project_landmark_request(
            before,
            request,
            available_growth_units=max(0, int(self.state.stored_growth_units)),
            available_coins=max(0, int(self.state.currency_balance)),
        )
        snapshot = self._state_snapshot()
        occurred_at = utc_now_iso()
        try:
            if outcome.growth_spent_units:
                if self.state.stored_growth_units < outcome.growth_spent_units:
                    raise RuntimeError("Stored Growth changed during Landmark commit")
                self.state.stored_growth_units -= outcome.growth_spent_units
            if outcome.coins_spent and not self._debit_currency(
                f"landmark-request:{request.request_id}",
                LANDMARK_BY_ID[request.landmark_id].display_name,
                outcome.coins_spent,
            ):
                raise RuntimeError("Garden Coin balance changed during Landmark commit")
            self._apply_landmark_snapshot(outcome.snapshot)
            if outcome.growth_spent_units:
                self.state.lifetime_economy_aggregates.growth_contributed_to_landmarks_units += (
                    outcome.growth_spent_units
                )
            stager = getattr(self.storage, "stage_idempotency_record", None)
            if callable(stager):
                stager(IdempotencyRecord(
                    operation_kind="landmark",
                    operation_id=request.request_id,
                    request_fingerprint=request.fingerprint,
                    outcome=outcome.to_dict(),
                    occurred_at=occurred_at,
                    scheduler_day=self.state.daily_stats.day,
                ))
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"landmark:{request.request_id}",
                event_kind=f"landmark_{request.action.value}",
                sink_id=request.landmark_id,
                scheduler_day=self.state.daily_stats.day,
                occurred_at=occurred_at,
                coins_spent=outcome.coins_spent,
                growth_spent_on_landmarks=outcome.growth_spent_units,
                growth_flow_kind=(
                    "manual_contribution"
                    if outcome.growth_spent_units else
                    "claim"
                    if request.action is LandmarkAction.COMPLETE else ""
                ),
                stored_growth_balance_delta_units=(
                    -outcome.growth_spent_units
                ),
                growth_contributed_to_landmarks_units=(
                    outcome.growth_spent_units
                ),
                item_id=(
                    request.landmark_id
                    if request.action is LandmarkAction.COMPLETE else ""
                ),
                quantity=(1 if request.action is LandmarkAction.COMPLETE else 0),
                metric_deltas=_project_allocation_metric_deltas((
                    ProjectGrowthAllocation(
                        GrowthTargetType.LANDMARK,
                        "garden_landmark",
                        outcome.growth_spent_units,
                    ),
                ) if outcome.growth_spent_units else ()),
            ))
            if request.action is LandmarkAction.COMPLETE:
                self._queue_feedback(
                    f"landmark:{request.request_id}",
                    "landmark",
                    "Garden Landmark completed.",
                    title=LANDMARK_BY_ID[request.landmark_id].display_name,
                    asset_category="landmarks",
                    asset_key=request.landmark_id,
                )
            self._persist_or_restore(snapshot)
            return outcome
        except Exception:
            self._restore_state(snapshot)
            raise

    def select_landmark(self, landmark_id: str) -> LandmarkOutcome:
        return self.confirm_landmark(LandmarkRequest(
            str(uuid.uuid4()), LandmarkAction.SELECT, str(landmark_id)
        ))

    def contribute_to_landmark(
        self, landmark_id: str, growth_units: int
    ) -> LandmarkOutcome:
        return self.confirm_landmark(LandmarkRequest(
            str(uuid.uuid4()),
            LandmarkAction.CONTRIBUTE,
            str(landmark_id),
            max(0, int(growth_units)),
        ))

    def complete_landmark(self, landmark_id: str) -> LandmarkOutcome:
        return self.confirm_landmark(LandmarkRequest(
            str(uuid.uuid4()), LandmarkAction.COMPLETE, str(landmark_id)
        ))

    def set_landmark_auto_contribute(self, enabled: bool) -> tuple[bool, str]:
        if not landmarks_enabled():
            return False, "This Growth project is unavailable."
        if enabled and not self.state.garden_project.selected_project_id:
            return False, "Select a Garden Landmark first."
        snapshot = self._state_snapshot()
        self.state.garden_project.auto_contribute = bool(enabled)
        if enabled:
            self.state.active_growth_target_type = GrowthTargetType.LANDMARK.value
            self.state.active_growth_target_id = "garden_landmark"
            self.state.active_growth_target_activation_identity = (
                f"legacy-landmark-selection:{self.state.daily_stats.day}"
            )
        elif (
            self.state.active_growth_target_type
            == GrowthTargetType.LANDMARK.value
        ):
            self.state.active_growth_target_type = ""
            self.state.active_growth_target_id = ""
            self.state.active_growth_target_activation_identity = ""
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t update Landmark contributions."
        return True, (
            "New overflow Growth will fund this Landmark."
            if enabled else "New overflow Growth will remain stored."
        )

    @_requires_ready_runtime()
    def display_landmark(self, landmark_id: str) -> tuple[bool, str]:
        if not landmarks_enabled():
            return False, "This appearance is unavailable."
        item_id = str(landmark_id or "")
        if item_id not in self.state.garden_project.completed_project_ids:
            return False, "Complete this Landmark before displaying it."
        snapshot = self._state_snapshot()
        self.state.garden_project.displayed_project_id = item_id
        self.state.garden_project.displayed_landmark_tier_id = item_id
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t change the displayed Landmark."
        return True, f"Displaying {LANDMARK_BY_ID[item_id].display_name}."

    def undo_landmark_appearance(self, previous_id: str, expected_id: str) -> tuple[bool, str]:
        """Restore only the displayed artwork while preserving later project work."""
        if not landmarks_enabled():
            return False, "This appearance is unavailable."
        project = self.state.garden_project
        if project.displayed_project_id != expected_id:
            return False, "Landmark appearance has changed since then."
        if previous_id and previous_id not in project.completed_project_ids:
            return False, "That Landmark is no longer available."
        snapshot = self._state_snapshot()
        project.displayed_project_id = previous_id
        project.displayed_landmark_tier_id = previous_id
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t restore the Landmark appearance. Try again."
        return True, "Landmark appearance restored."

    def mastery_catalog_summary(self) -> dict[str, Any]:
        projects = self.growth_projects_snapshot()
        full_bloom_species = {
            plant.species for plant in self.state.plants if plant.fully_grown
        }
        return {
            "stored_growth_units": projects.stored_balance_units,
            "stored_growth_balance_units": projects.stored_balance_units,
            "highest_rank_by_species": dict(
                self.state.cultivation_mastery
                .highest_claimed_rank_by_species
            ),
            "mastery_growth_units_funded_by_species": {
                species_id: track.growth_units_funded
                for species_id, track in projects.mastery_tracks_by_species
            },
            "mastery_ranks_claimed": {
                species_id: track.highest_claimed_id
                for species_id, track in projects.mastery_tracks_by_species
                if track.highest_claimed_id
            },
            "mastery_ranks_available_to_claim": {
                species_id: [
                    row.tier_id for row in track.tiers if row.claimable
                ]
                for species_id, track in projects.mastery_tracks_by_species
            },
            "species": [
                {
                    "species_id": species_id,
                    "eligible": species_id in full_bloom_species,
                    "current_rank_id": track.highest_claimed_id,
                    "next_rank_id": next((
                        row.tier_id for row in track.tiers if not row.claimed
                    ), None),
                    "growth_units_funded": track.growth_units_funded,
                    "remaining_capacity_units": track.remaining_capacity_units,
                    "display_name": track.display_name,
                    "artwork_id": track.artwork_id,
                    "effect_description": track.effect_description,
                    "acquisition_route": track.acquisition_route,
                    "ranks": [row.to_dict() for row in track.tiers],
                    "allowed_actions": list(track.allowed_actions),
                }
                # Cultivation Mastery is a release-catalog progression system.
                # Historical compatibility species remain loadable, but they
                # are deliberately outside the ten-species Mastery catalog and
                # cannot be passed to ``next_mastery_rank_id()``.
                for species_id, track in projects.mastery_tracks_by_species
            ],
            "garden_legacy": projects.legacy_track.to_dict(),
            "coins_required_for_claimable_content": (
                projects.coins_required_for_claimable_content
            ),
        }

    def quote_mastery(self, request: MasteryRequest) -> MasteryQuote:
        stored_balance = max(0, int(self.state.stored_growth_units))
        funded = max(0, int(
            self.state.cultivation_mastery.growth_units_funded_by_species.get(
                request.species_id, 0
            )
        ))
        cumulative_threshold = (
            MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[request.rank_id]
        )
        funding_deficit = max(0, cumulative_threshold - funded)
        quote = quote_mastery_request(
            self._mastery_snapshot(),
            request,
            # The schema-26 quote validates rank order against incremental
            # costs. Include already funded cumulative Growth for that check;
            # the renderer-neutral quote below exposes only the true deficit.
            available_growth_units=(
                stored_balance
                + max(0, MASTERY_GROWTH_COST_UNITS[request.rank_id] - funding_deficit)
            ),
            available_coins=max(0, int(self.state.currency_balance)),
        )
        if not mastery_enabled():
            return replace(
                quote, disposition=ProgressionDisposition.NOT_READY,
                can_apply=False, message="This Growth project is unavailable.",
                growth_spend_units=0, coin_spend=0,
            )
        if quote.can_apply and stored_balance < funding_deficit:
            return replace(
                quote,
                disposition=ProgressionDisposition.INSUFFICIENT_GROWTH,
                can_apply=False,
                message="Not enough stored Growth for this Mastery rank.",
                growth_spend_units=0,
                coin_spend=0,
            )
        if quote.can_apply:
            quote = replace(quote, growth_spend_units=funding_deficit)
        eligible = any(
            plant.species == request.species_id and plant.fully_grown
            for plant in self.state.plants
        )
        if not eligible:
            return replace(
                quote,
                disposition=ProgressionDisposition.NOT_READY,
                can_apply=False,
                message="Reach Full Bloom with this species first.",
                growth_spend_units=0,
                coin_spend=0,
            )
        return quote

    def confirm_mastery(self, request: MasteryRequest) -> MasteryOutcome:
        if not isinstance(request, MasteryRequest):
            raise TypeError("request must be a MasteryRequest")
        lookup = getattr(self.storage, "idempotency_record", None)
        existing = lookup("mastery", request.request_id) if callable(lookup) else None
        if existing is not None:
            restored = self._mastery_outcome_from_dict(existing.outcome)
            if (
                existing.request_fingerprint == request.fingerprint
                and restored is not None
            ):
                return restored
            raise ValueError("That Mastery request ID was already used.")
        before = self._mastery_snapshot()
        quote = self.quote_mastery(request)
        if not quote.can_apply:
            return MasteryOutcome(
                request.request_id,
                request.fingerprint,
                request.species_id,
                request.rank_id,
                quote.disposition,
                False,
                0,
                0,
                before,
                quote.message,
            )
        outcome = project_mastery_request(
            before,
            request,
            # Rank/order projection still uses the schema-26 incremental
            # contract; the fresh quote above already calculated the exact
            # cumulative funding deficit that may actually be debited.
            available_growth_units=MASTERY_GROWTH_COST_UNITS[request.rank_id],
            available_coins=max(0, int(self.state.currency_balance)),
        )
        outcome = replace(
            outcome,
            growth_spent_units=quote.growth_spend_units,
            coins_spent=quote.coin_spend,
        )
        snapshot = self._state_snapshot()
        occurred_at = utc_now_iso()
        try:
            if self.state.stored_growth_units < outcome.growth_spent_units:
                raise RuntimeError("Stored Growth changed during Mastery commit")
            self.state.stored_growth_units -= outcome.growth_spent_units
            rank = MASTERY_RANK_BY_ID[request.rank_id]
            if outcome.coins_spent and not self._debit_currency(
                f"mastery-request:{request.request_id}",
                f"{request.species_id.replace('_', ' ').title()} {rank.display_name}",
                outcome.coins_spent,
            ):
                raise RuntimeError("Garden Coin balance changed during Mastery commit")
            self._apply_mastery_snapshot(outcome.snapshot)
            if outcome.growth_spent_units:
                self.state.lifetime_economy_aggregates.growth_contributed_to_mastery_units += (
                    outcome.growth_spent_units
                )
            stager = getattr(self.storage, "stage_idempotency_record", None)
            if callable(stager):
                stager(IdempotencyRecord(
                    operation_kind="mastery",
                    operation_id=request.request_id,
                    request_fingerprint=request.fingerprint,
                    outcome=outcome.to_dict(),
                    occurred_at=occurred_at,
                    scheduler_day=self.state.daily_stats.day,
                ))
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"mastery:{request.request_id}",
                event_kind="mastery_purchase",
                sink_id=f"{request.species_id}:{request.rank_id}",
                scheduler_day=self.state.daily_stats.day,
                occurred_at=occurred_at,
                coins_spent=outcome.coins_spent,
                growth_spent_on_mastery=outcome.growth_spent_units,
                growth_flow_kind=(
                    "manual_contribution"
                    if outcome.growth_spent_units else "claim"
                ),
                stored_growth_balance_delta_units=(
                    -outcome.growth_spent_units
                ),
                growth_contributed_to_mastery_units=(
                    outcome.growth_spent_units
                ),
                item_id=request.rank_id,
                quantity=1,
                metric_deltas=_project_allocation_metric_deltas((
                    ProjectGrowthAllocation(
                        GrowthTargetType.MASTERY,
                        request.species_id,
                        outcome.growth_spent_units,
                    ),
                ) if outcome.growth_spent_units else ()),
            ))
            self._queue_feedback(
                f"mastery:{request.request_id}",
                "mastery",
                "Cultivation Mastery unlocked.",
                title=(
                    f"{request.species_id.replace('_', ' ').title()} "
                    f"{rank.display_name}"
                ),
                asset_category="mastery",
                asset_key=request.rank_id,
            )
            self._persist_or_restore(snapshot)
            return outcome
        except Exception:
            self._restore_state(snapshot)
            raise

    def purchase_mastery(self, species_id: str, rank_id: str) -> MasteryOutcome:
        return self.confirm_mastery(MasteryRequest(
            str(uuid.uuid4()), str(species_id), str(rank_id)
        ))

    def enter_starter_nursery(self) -> tuple[bool, str]:
        progress = self.state.onboarding
        if progress.step == OnboardingStep.NURSERY:
            return True, "Choose your starter plant."
        if progress.step != OnboardingStep.INTRODUCTION:
            return False, "Resume the current Garden setup step first."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(step=OnboardingStep.NURSERY)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Choose a starter."

    def select_starter_species(self, species: str) -> tuple[bool, str]:
        """Persist a reversible Nursery choice and advance directly to placement."""

        species = str(species).lower()
        progress = self.state.onboarding
        if self.state.plants or self.state.starter_selection_complete:
            return False, "Your starter plant has already been chosen."
        if progress.step not in {OnboardingStep.NURSERY, OnboardingStep.CONFIRMATION}:
            return False, "Open the Starter Nursery before choosing a plant."
        if species not in self.release_ready_species():
            return False, "That starter is not currently stocked in the Nursery."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=OnboardingStep.PLACEMENT,
            pending_species=species,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Choose a bed."

    def confirm_starter_species(self) -> tuple[bool, str]:
        progress = self.state.onboarding
        if progress.step == OnboardingStep.PLACEMENT and progress.pending_species:
            return True, "Choose a bed."
        if progress.step != OnboardingStep.CONFIRMATION or not progress.pending_species:
            return False, "Choose a starter plant before continuing."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=OnboardingStep.PLACEMENT,
            pending_species=progress.pending_species,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Choose a bed."

    def back_onboarding(self) -> tuple[bool, str]:
        """Move to the one intentional previous setup surface."""

        progress = self.state.onboarding
        previous = {
            OnboardingStep.NURSERY: OnboardingStep.INTRODUCTION,
            OnboardingStep.CONFIRMATION: OnboardingStep.NURSERY,
            OnboardingStep.PLACEMENT: OnboardingStep.NURSERY,
        }.get(progress.step)
        if previous is None:
            return False, "Back is not available on this setup step."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=previous,
            pending_species=(
                progress.pending_species
                if previous == OnboardingStep.NURSERY
                else None
            ),
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Back."

    def _create_starter_at_with_change(
        self,
        species: str,
        slot: int,
    ) -> tuple[bool, str, Plant | None, StarterPlacementChange | None]:
        """Create, place, and advance a starter in one durable transaction."""

        species = str(species).lower()
        try:
            destination = int(slot)
        except (TypeError, ValueError):
            destination = -1
        if self.state.starter_selection_complete or self.state.plants:
            return False, "Your starter plant has already been chosen.", None, None
        if species not in self.release_ready_species():
            return False, "That starter is not currently stocked in the Nursery.", None, None
        if not 0 <= destination < min(MAX_GARDEN_SLOTS, int(self.state.unlocked_slots)):
            return False, "Choose an unlocked garden bed for your starter.", None, None

        snapshot = self._state_snapshot()
        today = self._scheduler_day()
        plant = Plant(
            plant_id=f"plant_{uuid.uuid4().hex[:12]}",
            species=species,
            name=self._generated_name(species),
            slot_index=destination,
            personality=self.SPECIES_PERSONALITY.get(species, "balanced"),
            planted_on=today,
            memories=[PlantMemory("planted", "planted", today)],
        )
        self.state.unlocked_slots = max(2, int(self.state.unlocked_slots))
        self.state.unlocked_species = list(dict.fromkeys([
            *self.state.unlocked_species,
            species,
        ]))
        self.state.plants.append(plant)
        self.state.starter_selection_complete = True
        self.state.active_plant_id = None
        self.state.onboarding = OnboardingProgress(
            step=OnboardingStep.NURTURE,
            starter_plant_id=plant.plant_id,
        )
        if not any(
            period.day == today
            and period.plant_id is None
            and period.started_at_ms <= 0
            for period in self.state.active_plant_periods
        ):
            # A day-start sentinel ensures a later same-day revlog sync routes
            # reviews answered before this choice to no plant.
            self.state.active_plant_periods.append(ActivePlantPeriod(today, None, 0))
        self._queue_feedback(
            f"starter:{species}",
            "unlock",
            f"{PlantIdentity.from_plant(plant).species_name} planted.",
            plant.plant_id,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed.", None, None
        change = StarterPlacementChange(
            plant_id=plant.plant_id,
            # ``storage.save()`` committed the placement and advanced the
            # reward-ledger generation.  The pre-commit checkpoint is now
            # intentionally stale, so the durable Undo is a new bounded-state
            # commit rather than a rollback of already-committed ledger work.
            _before=_StateSnapshot(deepcopy(snapshot), None),
            _after=self.state.to_dict(),
        )
        return (
            True,
            f"{PlantIdentity.from_plant(plant).species_name} planted.",
            plant,
            change,
        )

    def _create_starter_at(self, species: str, slot: int) -> tuple[bool, str, Plant | None]:
        """Compatibility wrapper that discards the internal Undo receipt."""

        ok, message, plant, _change = self._create_starter_at_with_change(
            species,
            slot,
        )
        return ok, message, plant

    def place_starter_with_change(
        self,
        slot: int,
    ) -> tuple[bool, str, Plant | None, StarterPlacementChange | None]:
        """Place the selected starter and return its opaque atomic Undo receipt."""

        try:
            requested_slot = int(slot)
        except (TypeError, ValueError):
            requested_slot = -1
        progress = self.state.onboarding
        if progress.step in {
            OnboardingStep.NURTURE,
            OnboardingStep.COMPLETION,
            OnboardingStep.DONE,
        } and progress.starter_plant_id:
            existing = self.plant_story(progress.starter_plant_id)
            if existing is not None and existing.slot_index == requested_slot:
                return (
                    True,
                    "Your starter is already planted in that garden bed.",
                    existing,
                    None,
                )
        if progress.step != OnboardingStep.PLACEMENT or not progress.pending_species:
            return False, "Choose a starter before selecting its garden bed.", None, None
        return self._create_starter_at_with_change(
            progress.pending_species,
            requested_slot,
        )

    def place_starter(self, slot: int) -> tuple[bool, str, Plant | None]:
        """Compatibility wrapper for callers that do not expose starter Undo."""

        ok, message, plant, _change = self.place_starter_with_change(slot)
        return ok, message, plant

    def undo_starter_placement(
        self,
        change: StarterPlacementChange,
    ) -> tuple[bool, str]:
        """Restore placement only while the durable state matches its receipt."""

        if not isinstance(change, StarterPlacementChange):
            return False, "Starter placement can no longer be undone."
        if self.state.to_dict() != change._after:
            return False, "Starter placement can no longer be undone."
        current = self._state_snapshot()
        self._restore_state(change._before)
        try:
            self.storage.save()
        except Exception:
            self._restore_state(current)
            return False, "Couldn’t undo starter placement. Your garden is unchanged."
        return True, "Starter placement undone."

    def choose_starter(self, species: str) -> tuple[bool, str, Plant | None]:
        """Compatibility path for callers predating explicit starter placement.

        New UI code uses select, confirm, and place. This wrapper remains atomic
        and selects the first unlocked bed so older integrations do not create
        a half-finished starter.
        """

        return self._create_starter_at(species, 0)

    def _welcome_eligible(self) -> bool:
        return (
            self.state.onboarding.step != OnboardingStep.DONE
            and self.state.garden_setup_version == 0
            and not self._reward_applied(WELCOME_EVENT_KEY)
        )

    def _capture_welcome_history(self, history: Any) -> None:
        """Snapshot paid historical rewards while setup is still unfinished.

        Query committed/staged economy rows when available, so pausing setup
        cannot lose historical amounts when the ordinary receipt cache prunes.
        Imported badges without a payout are never advertised as fresh Coins.
        """
        if not self._welcome_eligible():
            return
        welcome = self.state.welcome_receipt or WelcomeReceipt()
        if welcome.status != "collecting":
            return
        rewards: list[WelcomeReward] = []
        achievement_ids: list[str] = []
        event_resolver = getattr(self.storage, "economy_event", None)
        for definition in ACHIEVEMENT_DEFINITIONS:
            key = definition.achievement_id
            achievement = self.state.achievements.get(key)
            if (
                not history.unlock_day(key) or achievement is None
                or not achievement.unlocked or not achievement.rewarded_at
                or not achievement.historical_backfill
            ):
                continue
            event_key = achievement.reward_event_key
            event = event_resolver(event_key) if callable(event_resolver) else None
            if event is not None:
                if event.coins_earned:
                    rewards.append(WelcomeReward(event_key, "coins", int(event.coins_earned)))
                for item_id, quantity in event.metric_deltas.get("consumables_earned", {}).items():
                    if quantity:
                        rewards.append(WelcomeReward(event_key, "inventory_item", int(quantity), str(item_id)))
            else:
                rewards.extend(
                    WelcomeReward(row.event_key, row.reward_type, row.amount, row.item_id)
                    for row in self.state.recent_reward_receipts
                    if row.event_key == event_key and row.amount > 0
                    and row.reward_type in {"coins", "inventory_item"}
                )
            for trophy_id in definition.reward.cosmetic_ids:
                if trophy_id in self.state.inventory.get("cosmetics", []):
                    rewards.append(WelcomeReward(event_key, "trophy", 1, trophy_id))
            achievement_ids.append(key)
        self.state.welcome_receipt = welcome.with_history(
            review_count=int(history.lifetime_answers),
            rewards=rewards, achievement_ids=achievement_ids,
        )

    def mark_welcome_presented(self, receipt_id: str, *, acknowledged: bool = False) -> bool:
        welcome = self.state.welcome_receipt
        if welcome is None or welcome.receipt_id != receipt_id or not welcome.pending:
            return False
        status = "acknowledged" if acknowledged else "started"
        if welcome.status == status:
            return True
        snapshot = self._state_snapshot()
        self.state.welcome_receipt = replace(welcome, status=status)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            logger.exception("Anki Garden: welcome presentation acknowledgement failed")
            return False
        return True

    @_requires_ready_runtime()
    def finish_onboarding(self) -> tuple[bool, str]:
        progress = self.state.onboarding
        if progress.step == OnboardingStep.DONE:
            return True, "Your garden is ready."
        if progress.step != OnboardingStep.COMPLETION:
            return False, "Finish nurturing your starter before completing setup."
        snapshot = self._state_snapshot()
        transitions = list(self._pending_stage_transitions)
        correlation = self._current_correlation_id
        try:
            if self._welcome_eligible():
                plant = self.plant_story(str(progress.starter_plant_id or ""))
                if plant is None or not plant.planted or self.state.active_plant_id != plant.plant_id:
                    return False, "Nurture your starter before completing setup."
                welcome = self.state.welcome_receipt or WelcomeReceipt()
                before = self._plant_growth_units(plant)
                self._current_correlation_id = WELCOME_EVENT_KEY
                self._grant_reward_bundle(
                    WELCOME_EVENT_KEY, source="welcome", source_id="first_garden",
                    reason="Welcome gift", title="Welcome gift", coins=WELCOME_COINS,
                    growth=WELCOME_GROWTH, plant=plant, correlation_id=WELCOME_EVENT_KEY,
                )
                gift = tuple(
                    WelcomeReward(row.event_key, row.reward_type, row.amount, row.item_id)
                    for row in self.state.recent_reward_receipts
                    if row.correlation_id == WELCOME_EVENT_KEY and row.amount > 0
                    and row.reward_type in {"coins", "growth", "inventory_item"}
                )
                self.state.welcome_receipt = replace(
                    welcome, status="ready", gift_rewards=gift,
                    plant_id=plant.plant_id, species=plant.species,
                    growth_before_units=before, growth_after_units=self._plant_growth_units(plant),
                )
                self.state.pending_feedback = [
                    event for event in self.state.pending_feedback
                    if event.correlation_id != WELCOME_EVENT_KEY
                    and event.event_id != f"starter:{plant.species}"
                ]
                self._pending_stage_transitions = transitions
            self.state.onboarding = OnboardingProgress(
                step=OnboardingStep.DONE, starter_plant_id=progress.starter_plant_id,
            )
            self.state.garden_setup_version = 1
            self._persist_or_restore(snapshot)
        except Exception:
            self._pending_stage_transitions = transitions
            self._restore_state(snapshot)
            logger.exception("Anki Garden: first-garden welcome could not be saved")
            return False, "Couldn’t save your garden. Nothing was changed."
        finally:
            self._current_correlation_id = correlation
        return True, "Your garden is ready."

    def purchase_fertilizer(self, plant_id: str, tier: str, *, replace_active: bool = False) -> tuple[bool, str]:
        outcome = self._compat_purchase(
            PurchaseKind.FERTILIZER,
            str(tier).lower(),
            target_id=str(plant_id),
            authorize_replacement=bool(replace_active),
        )
        return outcome.success, outcome.message

    @_requires_ready_runtime()
    def use_fertilizer_item(
        self,
        plant_id: str | None = None,
        *,
        tier: str = "basic",
        replace_active: bool = False,
    ) -> tuple[bool, str]:
        """Use one stored Fertilizer dose on the nurtured plant."""

        self.last_fertilizer_stored_item_result = None
        normalized_tier = str(tier or "basic").lower()
        spec = self.FERTILIZERS.get(normalized_tier)
        if spec is None:
            return False, "That Fertilizer is no longer available."
        inventory_key = f"fertilizer_{normalized_tier}"
        # ``None`` retains the legacy "current nurtured plant" convenience.
        # Any supplied value, including an empty or stale ID, is an immutable
        # explicit target and must never be rebound to whichever plant is now
        # active.
        projection = self.consumable_use_projection(inventory_key, plant_id)
        if not projection.can_use:
            return False, projection.message
        plant = self._consumable_target(projection.target_id)
        assert plant is not None
        dose_count = projection.doses
        stored_item_result = build_fertilizer_stored_item_projection(
            FertilizerStoredItemDisposition.QUEUE
            if dose_count else FertilizerStoredItemDisposition.USE,
            card_queue_delta=spec.card_count,
            # Card-counted Fertilizer has no wall-clock expiration. Legacy
            # timed projections may populate this field explicitly.
            expires_at_ms=None,
        )
        _ = bool(replace_active)  # Different tiers now queue; no confirmation needed.
        snapshot = self._state_snapshot()
        try:
            self._lock_scenery_loadout(event_ms=self._now_ms())
            event_id = f"fertilizer-item:{uuid.uuid4().hex}"
            self.state.consumables[inventory_key] -= 1
            action = self._activate_fertilizer_effect(
                plant,
                spec,
                now=self._now_seconds(),
                source_event_key=event_id,
            )
            remaining_cards = sum(
                max(0, int(batch.remaining_cards))
                for batch in (
                    *plant.fertilizer_card_batches,
                    *plant.fertilizer_card_queue,
                )
            )
            message = (
                f"{spec.name} queued."
                if action == "queued"
                else (
                    f"{spec.name} extended to {remaining_cards:,} cards remaining."
                )
                if action == "extended"
                else (
                    f"{spec.name} active: +{spec.growth_per_answer:,} Growth "
                    f"per card for the next {spec.card_count:,} eligible cards."
                )
            )
            self._queue_feedback(
                event_id,
                "fertilizer",
                message,
                "" if projection.destination_kind == "garden" else projection.target_id,
                title=(f"{spec.name} queued" if action == "queued" else f"{spec.name} active"),
                asset_category="ui",
                asset_key=inventory_key,
                amount=1,
                correlation_id=event_id,
            )
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"consumable-use:{event_id}",
                event_kind="fertilizer_use",
                source_id=inventory_key,
                scheduler_day=self.state.daily_stats.day,
                occurred_at=utc_now_iso(),
                item_id=inventory_key,
                quantity=1,
                metric_deltas={
                    "consumables_used": {inventory_key: 1}
                },
            ))
            self._persist_or_restore(snapshot)
        except Exception:
            self._restore_state(snapshot)
            return False, f"Couldn’t use {spec.name}."
        self.last_fertilizer_stored_item_result = replace(
            stored_item_result, target_id=projection.target_id, target_name=projection.target_name,
            destination_kind=projection.destination_kind, remaining_cards=remaining_cards,
        )
        return True, message

    def fertilizer_stored_item_projection(
        self,
        plant_id: str | None = None,
        *,
        tier: str = "basic",
    ) -> FertilizerStoredItemProjection | None:
        """Project an inventory dose action without inferring it in the UI.

        Production emits only ``USE`` or ``QUEUE`` with a card delta and a
        null ``expires_at_ms``. Schema-25 timed doses are converted to this
        card-counted queue during migration. ``ADD_ONE_HOUR`` and
        ``ADD_TWO_HOURS`` remain compatibility-builder values only; the
        production engine never emits them.
        """

        normalized_tier = str(tier or "basic").lower()
        spec = self.FERTILIZERS.get(normalized_tier)
        plant = self._consumable_target(plant_id)
        if spec is None or plant is None:
            return None
        active, queued = self._card_effect_lists(plant, "fertilizer")
        live_count = sum(
            1 for batch in (*active, *queued)
            if int(batch.remaining_cards) > 0
        )
        return replace(build_fertilizer_stored_item_projection(
            FertilizerStoredItemDisposition.QUEUE
            if live_count else FertilizerStoredItemDisposition.USE,
            card_queue_delta=spec.card_count,
            expires_at_ms=None,
        ), target_id=self.consumable_target_id() if plant_id is None else str(plant_id),
            target_name="Garden" if isinstance(plant, GardenCardEffects) else PlantIdentity.from_plant(plant).display_name,
            destination_kind="garden" if isinstance(plant, GardenCardEffects) else "plant",
            remaining_cards=sum(batch.remaining_cards for batch in (*active, *queued)) + spec.card_count)

    def use_fertilizer_item_with_result(
        self,
        plant_id: str | None = None,
        *,
        tier: str = "basic",
        replace_active: bool = False,
    ) -> tuple[bool, str, FertilizerStoredItemProjection | None]:
        """Use an inventory dose and return its explicit committed disposition."""

        ok, message = self.use_fertilizer_item(
            plant_id,
            tier=tier,
            replace_active=replace_active,
        )
        return ok, message, self.last_fertilizer_stored_item_result

    def use_basic_fertilizer(
        self,
        plant_id: str | None = None,
        *,
        replace_active: bool = False,
    ) -> tuple[bool, str]:
        return self.use_fertilizer_item(
            plant_id,
            tier="basic",
            replace_active=replace_active,
        )

    def use_booster_potion(self, plant_id: str | None = None) -> tuple[bool, str]:
        self.last_booster_result = BoosterResult()
        projection = self.consumable_use_projection("booster_potion", plant_id)
        if not projection.can_use:
            return False, projection.message
        plant = self._consumable_target(projection.target_id)
        assert plant is not None
        snapshot = self._state_snapshot()
        try:
            self._lock_scenery_loadout(event_ms=self._now_ms())
            base_cards = self.BOOSTER_CARD_COUNT
            card_count = base_cards
            event_key = f"booster:{projection.target_id}:{uuid.uuid4().hex}"
            self.state.consumables["booster_potion"] -= 1
            action = self._add_card_effect_batch(
                plant,
                effect_id="booster_potion",
                growth_units=self.BOOSTER_GROWTH_PER_ANSWER * GROWTH_UNITS_PER_POINT,
                cards=card_count,
                source_event_key=event_key,
            )
            if action is None:
                raise RuntimeError("Booster Potion dose limit reached")
            remaining_cards = sum(
                max(0, int(batch.remaining_cards))
                for batch in (
                    *plant.booster_card_batches,
                    *plant.booster_card_queue,
                )
            )
            self.last_booster_result = BoosterResult(
                base_cards_added=base_cards,
                total_cards_added=card_count,
                remaining_booster_cards=remaining_cards,
                target_id=projection.target_id,
                destination_kind=projection.destination_kind,
            )
            message = (
                f"Booster Potion added {card_count:,} cards."
                if action == "extended"
                else (
                    f"Booster Potion active: +{self.BOOSTER_GROWTH_PER_ANSWER} "
                    f"Growth for the next {card_count:,} cards."
                )
            )
            self._queue_feedback(
                event_key,
                "booster",
                message,
                "" if projection.destination_kind == "garden" else projection.target_id,
                title="Booster Potion active",
                asset_category="ui",
                asset_key="booster_potion",
                amount=1,
            )
            self._stage_economy_event(EconomyEventRecord(
                event_key=f"consumable-use:{event_key}",
                event_kind="booster_use",
                source_id="booster_potion",
                scheduler_day=self.state.daily_stats.day,
                occurred_at=utc_now_iso(),
                item_id="booster_potion",
                quantity=1,
                metric_deltas={
                    "consumables_used": {"booster_potion": 1}
                },
            ))
            self._persist_or_restore(snapshot)
        except Exception:
            self._restore_state(snapshot)
            return False, "Couldn’t use the Booster Potion. Your potion was not used."
        return True, message

    def purchase_species(self, species: str) -> tuple[bool, str, Plant | None]:
        outcome = self._compat_purchase(
            PurchaseKind.SPECIES,
            str(species).lower(),
        )
        plant = self.plant_story(outcome.result_id) if outcome.success else None
        return outcome.success, outcome.message, plant

    def next_bed_price(self) -> int | None:
        return None

    def purchase_next_bed(self) -> tuple[bool, str]:
        return (
            False,
            "Garden beds are earned from plant progression and are no longer sold.",
        )

    @_requires_ready_runtime()
    def plant_from_collection(self, plant_id: str, slot_index: int | None = None) -> tuple[bool, str]:
        plant = self.plant_story(plant_id)
        if plant is None:
            return False, "That plant is no longer in your collection."
        if plant.planted:
            return False, "That plant is already in the garden."
        occupied = {item.slot_index for item in self.state.plants if item.slot_index is not None}
        available = [
            slot for slot in range(self.state.unlocked_slots)
            if slot not in occupied and self.slot_accepts_plant(plant, slot)
        ]
        if not available:
            return False, self.SOIL_CAPACITY_MESSAGE
        try:
            destination = available[0] if slot_index is None else int(slot_index)
        except (TypeError, ValueError):
            return False, "Choose an empty bed."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if destination not in available:
            return False, "Choose an empty bed."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t place the plant. Your garden is unchanged."
        return True, f"{PlantIdentity.from_plant(plant).display_name} was placed in Bed {destination + 1}."

    @_requires_ready_runtime()
    def move_plant(self, plant_id: str, slot_index: int) -> tuple[bool, str]:
        """Atomically move a planted Collection item to an empty garden bed."""

        plant = self.plant_story(plant_id)
        if plant is None or not plant.planted:
            return False, "That plant is not currently planted."
        try:
            destination = int(slot_index)
        except (TypeError, ValueError):
            return False, "Choose an empty bed."
        occupied = {
            item.slot_index for item in self.state.plants
            if item.plant_id != plant.plant_id and item.slot_index is not None
        }
        if (
            destination < 0
            or destination >= self.state.unlocked_slots
            or destination in occupied
        ):
            return False, "Choose an empty bed."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if plant.slot_index == destination:
            return True, f"{PlantIdentity.from_plant(plant).display_name} is already in Bed {destination + 1}."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t move the plant. Your garden is unchanged."
        return True, f"{PlantIdentity.from_plant(plant).display_name} moved to Bed {destination + 1}."

    @_requires_ready_runtime()
    def move_to_collection(self, plant_id: str) -> tuple[bool, str]:
        plant = self.plant_story(plant_id)
        if plant is None or not plant.planted:
            return False, "That plant is not currently planted."
        if self.state.active_plant_id == plant.plant_id:
            return False, "Nurture another plant before storing this one."
        snapshot = self._state_snapshot()
        plant.slot_index = None
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t store the plant. Your garden is unchanged."
        return True, f"{PlantIdentity.from_plant(plant).display_name} stored."

    def _repair_active_plant(self) -> Plant | None:
        requested_active_id = self.state.active_plant_id
        if requested_active_id is None and not bool(
            getattr(self.state, "_active_plant_reference_invalid", False)
        ):
            return None
        plant = next((
            item for item in self.state.plants if item.plant_id == requested_active_id
        ), None)
        if plant is not None and plant.planted and not plant.fully_grown:
            self.state._active_plant_reference_invalid = False
            return plant
        invalid_reference = bool(
            getattr(self.state, "_active_plant_reference_invalid", False)
        ) or (requested_active_id is not None and plant is None)
        if invalid_reference:
            replacement = self._deterministic_active_candidate()
            self.state.active_plant_id = replacement.plant_id if replacement is not None else None
            self.state._active_plant_reference_invalid = False
            self._record_active_period(
                replacement.plant_id if replacement is not None else None
            )
            return replacement
        if plant is None or not plant.planted or plant.fully_grown:
            self.state.active_plant_id = None
            self._record_active_period(None)
            return None
        return plant

    def _deterministic_active_candidate(self) -> Plant | None:
        return next((
            plant for plant in sorted(
                self.state.plants,
                key=lambda item: (
                    item.slot_index is None,
                    item.slot_index if item.slot_index is not None else MAX_GARDEN_SLOTS,
                    item.plant_id,
                ),
            )
            if plant.planted and not plant.fully_grown
        ), None)

    def _record_active_period(
        self,
        plant_id: str | None,
        *,
        event_ms: int | None = None,
    ) -> None:
        day = self.state.daily_stats.day
        latest = max(
            self.state.active_plant_periods,
            key=lambda period: (period.started_at_ms, period.day),
            default=None,
        )
        if latest is None or latest.plant_id != plant_id:
            activated_at = (
                self._now_ms()
                if event_ms is None
                else max(1, int(event_ms))
            )
            self.state.active_plant_periods.append(ActivePlantPeriod(
                day, plant_id, activated_at
            ))
            self._activate_progression_if_ready(activated_at)

    def active_plant(self) -> Plant | None:
        return self._repair_active_plant()

    @_requires_ready_runtime()
    def set_active_plant(self, plant_id: Optional[str]) -> tuple[bool, str]:
        if plant_id is None:
            if self.state.active_plant_id is None:
                return True, "No plant is being nurtured."
            snapshot = self._state_snapshot()
            self.state.active_plant_id = None
            self._record_active_period(None)
            try:
                self._persist_or_restore(snapshot)
            except Exception:
                return False, "Couldn’t stop nurturing. Your garden is unchanged."
            return True, "Stopped nurturing."
        plant = self.plant_story(str(plant_id or ""))
        if plant is None:
            return False, "That plant is no longer in your collection."
        if not plant.planted:
            return False, "Place this plant in a bed first."
        if plant.fully_grown:
            return False, "This plant is in Full Bloom. Nurture another plant."
        progress = self.state.onboarding
        if self.state.active_plant_id == plant.plant_id:
            if (
                progress.step == OnboardingStep.NURTURE
                and progress.starter_plant_id == plant.plant_id
            ):
                snapshot = self._state_snapshot()
                self.state.onboarding = OnboardingProgress(
                    step=OnboardingStep.COMPLETION,
                    starter_plant_id=plant.plant_id,
                )
                try:
                    self._persist_or_restore(snapshot)
                except Exception:
                    return False, "Couldn’t nurture the plant. Your garden is unchanged."
            return True, f"{PlantIdentity.from_plant(plant).display_name} is already nurtured."
        snapshot = self._state_snapshot()
        self.state.active_plant_id = plant.plant_id
        activated_at = self._now_ms()
        self._record_active_period(plant.plant_id, event_ms=activated_at)
        self._claim_completed_plant_effects(plant)
        self._add_memory(plant, "nurture:first", "first_nurture")
        if (
            progress.step == OnboardingStep.NURTURE
            and progress.starter_plant_id == plant.plant_id
        ):
            self.state.onboarding = OnboardingProgress(
                step=OnboardingStep.COMPLETION,
                starter_plant_id=plant.plant_id,
            )
        # Stored Growth remains saved while its spending features are deferred.
        # Selecting a nurture target never spends the reserve. Future answer
        # Growth still routes to this plant normally.
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t nurture the plant. Your garden is unchanged."
        return True, f"{PlantIdentity.from_plant(plant).display_name} is now nurtured."

    def rename_garden(self, name: str, *, complete_setup: bool = True) -> tuple[bool, str]:
        clean = " ".join(str(name).split())
        if not clean:
            return False, "Enter a garden name."
        if len(clean) > MAX_GARDEN_NAME_LENGTH:
            return False, f"Use {MAX_GARDEN_NAME_LENGTH} characters or fewer."
        snapshot = self._state_snapshot()
        self.state.garden_name = clean
        if complete_setup:
            self.state.garden_setup_version = 1
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save the garden name. Nothing was changed."
        return True, f"Your garden is now named {clean}."

    def development_populate(
        self,
        *,
        emit_feedback: bool = True,
    ) -> tuple[bool, str]:
        """Populate a broad UI test state without touching the revlog ledger.

        The capture harness seeds this state as fixture setup rather than as a
        learner action.  It can therefore suppress the development receipt at
        the source while the explicit development control retains its normal
        product feedback.
        """

        if not build_capabilities.DEVELOPMENT_MUTATION_ENABLED:
            return False, "Development garden population is unavailable in this production build."

        snapshot = self._state_snapshot()
        today = self._scheduler_day()
        seed_value = int.from_bytes(hashlib.blake2b(
            self.state.reward_seed.encode("utf-8"), digest_size=8
        ).digest(), "big")
        rng = random.Random(seed_value ^ int(self._now_ms()))
        # Seed only the current catalog. Historical species remain valid for
        # imported state, but do not have complete V6 catalog artwork.
        species = list(CURRENT_CATALOG_SPECIES_ORDER)
        rng.shuffle(species)
        stage_indexes = [0, 1, 2, 3, 4, 5, 1, 2, 3, 4]
        rng.shuffle(stage_indexes)
        plants: list[Plant] = []
        for index, plant_species in enumerate(species):
            stage_index = stage_indexes[index % len(stage_indexes)]
            points = GROWTH_THRESHOLDS[stage_index]
            if stage_index < len(GROWTH_STAGES) - 1:
                points += rng.randint(
                    0,
                    max(0, (GROWTH_THRESHOLDS[stage_index + 1] - points) // 2),
                )
            plants.append(Plant(
                plant_id=f"dev_{plant_species}",
                species=plant_species,
                name=self._generated_name(plant_species),
                slot_index=index if index < MAX_GARDEN_SLOTS else None,
                growth_points=min(GROWTH_THRESHOLDS[-1], points),
                personality=self.SPECIES_PERSONALITY.get(plant_species, "balanced"),
                planted_on=today,
                memories=[PlantMemory("planted", "planted", today)],
                name_customized=False,
            ))
        # Guarantee one valid unfinished nurtured plant regardless of shuffle.
        nurtured = plants[0]
        nurtured.growth_points = min(nurtured.growth_points, GROWTH_THRESHOLDS[-2])
        self.state.plants = plants
        self.state.unlocked_species = list(CURRENT_CATALOG_SPECIES_ORDER)
        self.state.unlocked_slots = MAX_GARDEN_SLOTS
        self.state.starter_selection_complete = True
        self.state.garden_setup_version = 1
        self.state.active_plant_id = nurtured.plant_id
        self.state.active_plant_periods = [
            ActivePlantPeriod(today, nurtured.plant_id, self._now_ms())
        ]
        self._activate_progression_if_ready(
            self.state.active_plant_periods[0].started_at_ms
        )
        coin_delta = max(0, 100_000 - int(self.state.currency_balance))
        if coin_delta:
            self._credit_currency(
                f"development:populate:{uuid.uuid4().hex}",
                "Development catalog seed",
                coin_delta,
            )
        self.state.consumables["booster_potion"] = max(
            12, self.state.consumables.get("booster_potion", 0)
        )
        for charge_id in GROWTH_CHARGES:
            self.state.consumables[charge_id] = max(
                12, self.state.consumables.get(charge_id, 0)
            )
        self.state.inventory["garden_features"] = list(GARDEN_FEATURE_CATALOG)
        self.state.inventory["scenery"] = list(SCENERY_CATALOG)
        self.state.environment_visibility = {"garden_feature": True, "scenery": True}
        now = utc_now_iso()
        for achievement in self.state.achievements.values():
            achievement.unlocked = True
            achievement.unlocked_at = achievement.unlocked_at or now
            achievement.progress = 1.0
        if emit_feedback:
            self._queue_feedback(
                f"development:ready:{uuid.uuid4().hex}",
                "development",
                "Development garden populated. Use Restore backup to return to the prior state.",
                title="Development garden ready",
            )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The development garden could not be saved."
        return True, "Development garden populated with 100,000 Garden Coins, all plants, spaces, and items."

    def restore_development_backup(self, path: Any) -> tuple[bool, str]:
        exact_restorer = getattr(
            self.storage, "restore_development_backup", None
        )
        if (
            callable(exact_restorer)
            and getattr(self.storage, "_reward_ledger", None) is not None
        ):
            try:
                restored = exact_restorer(path)
                self.state.__dict__.clear()
                self.state.__dict__.update(restored.__dict__)
                self.storage.state = self.state
            except Exception:
                return False, "The development backup could not be restored."
            return True, "The pre-development garden backup was restored."

        snapshot = self._state_snapshot()
        try:
            restored = self.storage.load_development_backup(path)
            self._restore_state(restored.to_dict())
            self.storage.save()
        except Exception:
            self._restore_state(snapshot)
            return False, "The development backup could not be restored."
        return True, "The pre-development garden backup was restored."

    def plant_story(self, plant_id: str) -> Plant | None:
        return next((item for item in self.state.plants if item.plant_id == plant_id), None)

    def _add_memory(
        self,
        plant: Plant,
        memory_id: str,
        kind: str,
        *,
        value: int = 0,
        previous_stage: Optional[str] = None,
        new_stage: Optional[str] = None,
    ) -> bool:
        if any(memory.memory_id == memory_id for memory in plant.memories):
            return False
        plant.memories.append(PlantMemory(
            memory_id, kind, self.state.daily_stats.day, max(0, int(value)), previous_stage, new_stage
        ))
        return True

    def _record_shared_memories(
        self,
        previous_reviews: int,
        previous_streak: int,
        *,
        plant: Plant | None = None,
    ) -> None:
        plant = plant or self.active_plant()
        if plant is None:
            return
        for threshold in self.STREAK_MEMORY_MILESTONES:
            if previous_streak < threshold <= self.state.streak_days:
                self._add_memory(plant, f"streak:{threshold}", "streak", value=threshold)
        for threshold in (250, 700, 1_500, 2_600, 5_000, 10_000):
            if previous_reviews < threshold <= self.state.total_reviews:
                self._add_memory(plant, f"reviews:{threshold}", "reviews", value=threshold)

    def _generated_name(self, species: str) -> str:
        species_name = species.replace("_", " ").title()
        return f"{species_name} Plant"[:MAX_PLANT_NAME_LENGTH]

    def _planted(self) -> list[Plant]:
        return sorted(
            (plant for plant in self.state.plants if plant.slot_index is not None),
            key=lambda plant: (int(plant.slot_index or 0), plant.plant_id),
        )

    def place_plant(self, plant_id: str, destination_slot: int) -> tuple[bool, str, PlacementChange | None]:
        plants = self._planted()
        plants_by_id = {plant.plant_id: plant for plant in plants}
        plant = plants_by_id.get(str(plant_id))
        if plant is None:
            return False, "That plant is no longer in your garden.", None
        try:
            destination = int(destination_slot)
        except (TypeError, ValueError):
            return False, "Choose a bed.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That bed is locked.", None
        origin = int(plant.slot_index or 0)
        if origin == destination:
            return False, "That plant is already in this bed.", None
        occupant = next((item for item in plants if item.slot_index == destination), None)
        affected = [plant] + ([occupant] if occupant else [])
        before = {item.plant_id: int(item.slot_index or 0) for item in affected}
        candidate = {item.plant_id: int(item.slot_index or 0) for item in plants}
        candidate[plant.plant_id] = destination
        if occupant:
            candidate[occupant.plant_id] = origin
        surface_error = self._arrangement_error(candidate)
        if surface_error:
            return False, surface_error, None
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        if occupant:
            occupant.slot_index = origin
        after = {item.plant_id: int(item.slot_index or 0) for item in affected}
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t move the plant. Your garden is unchanged.", None
        return True, "Plants moved.", PlacementChange(before, after)

    @_requires_ready_runtime(None)
    def begin_placement_draft(self, plant_id: str) -> tuple[bool, str, PlacementDraft | None]:
        plants = self._planted()
        slots = {plant.plant_id: int(plant.slot_index or 0) for plant in plants}
        if str(plant_id) not in slots:
            return False, "That plant is no longer in your garden.", None
        return True, "Arrangement ready.", PlacementDraft(str(plant_id), slots, dict(slots), [])

    def stage_placement(self, draft: PlacementDraft, destination_slot: int) -> tuple[bool, str, PlacementChange | None]:
        if not isinstance(draft, PlacementDraft) or draft.selected_plant_id not in draft.current:
            return False, "That move session is no longer available.", None
        try:
            destination = int(destination_slot)
        except (TypeError, ValueError):
            return False, "Choose a bed.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That bed is locked.", None
        origin = draft.current[draft.selected_plant_id]
        if destination == origin:
            return False, "That plant is already in this bed.", None
        occupant = next((pid for pid, slot in draft.current.items() if slot == destination), None)
        before = dict(draft.current)
        candidate = dict(draft.current)
        candidate[draft.selected_plant_id] = destination
        if occupant:
            candidate[occupant] = origin
        surface_error = self._arrangement_error(candidate)
        if surface_error:
            return False, surface_error, None
        draft.history.append(before)
        draft.current = candidate
        return True, "Arrangement updated.", PlacementChange(before, dict(draft.current))

    def undo_staged_placement(self, draft: PlacementDraft) -> tuple[bool, str]:
        if not isinstance(draft, PlacementDraft) or not draft.history:
            return False, "There is no pending move to undo."
        draft.current = draft.history.pop()
        return True, "Move undone."

    @_requires_ready_runtime(None)
    def commit_placement_draft(self, draft: PlacementDraft) -> tuple[bool, str, PlacementChange | None]:
        if not isinstance(draft, PlacementDraft) or not draft.original:
            return False, "That move session is no longer available.", None
        plants = {plant.plant_id: plant for plant in self._planted()}
        live = {pid: int(plant.slot_index or 0) for pid, plant in plants.items()}
        if live != draft.original:
            return False, "Your garden changed while you were moving the plant. Nothing was saved.", None
        if set(draft.current) != set(draft.original) or len(set(draft.current.values())) != len(draft.current):
            return False, "Choose another bed.", None
        if any(slot < 0 or slot >= self.state.unlocked_slots for slot in draft.current.values()):
            return False, "Choose an unlocked bed.", None
        surface_error = self._arrangement_error(draft.current)
        if surface_error:
            return False, surface_error, None
        if draft.current == draft.original:
            return True, "Nothing changed.", PlacementChange(dict(draft.original), dict(draft.current))
        snapshot = self._state_snapshot()
        for plant_id, slot in draft.current.items():
            plants[plant_id].slot_index = slot
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t move the plant. Your garden is unchanged.", None
        return True, "Plants moved.", PlacementChange(dict(draft.original), dict(draft.current))

    def restore_placement(self, change: PlacementChange) -> tuple[bool, str, PlacementChange | None]:
        plants = {plant.plant_id: plant for plant in self._planted()}
        if not change.before or any(pid not in plants for pid in change.before):
            return False, "That move can’t be undone.", None
        current = {pid: int(plants[pid].slot_index or 0) for pid in change.before}
        if current != change.after:
            return False, "Your garden changed, so that move can’t be undone.", None
        surface_error = self._arrangement_error(change.before)
        if surface_error:
            return False, "That move can’t be restored.", None
        snapshot = self._state_snapshot()
        for pid, slot in change.before.items():
            plants[pid].slot_index = slot
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t undo the move. Your garden is unchanged.", None
        return True, "Move undone.", PlacementChange(current, dict(change.before))

    def peek_stage_transitions(self) -> list[StageTransition]:
        return list(self._pending_stage_transitions)

    def consume_stage_transitions(
        self,
        *,
        limit: int | None = None,
        transitions: list[StageTransition] | tuple[StageTransition, ...] | None = None,
    ) -> list[StageTransition]:
        if transitions is None:
            count = len(self._pending_stage_transitions) if limit is None else max(0, int(limit))
            consumed = list(self._pending_stage_transitions[:count])
            del self._pending_stage_transitions[:count]
            return consumed
        expected = list(transitions)
        consumed: list[StageTransition] = []
        remaining: list[StageTransition] = []
        for current in self._pending_stage_transitions:
            try:
                index = expected.index(current)
            except ValueError:
                remaining.append(current)
            else:
                consumed.append(current)
                expected.pop(index)
        self._pending_stage_transitions = remaining
        return consumed

    @staticmethod
    def stage_transition_message(transitions: list[StageTransition]) -> str:
        if not transitions:
            return ""
        if len(transitions) == 1:
            item = transitions[0]
            return plant_stage_event(item.species, item.new_stage) + "."
        names = ", ".join(
            plant_species_name(item.species)
            for item in transitions[:3]
        )
        if len(transitions) > 3:
            names += f" and {len(transitions) - 3} more"
        return f"{names} reached new growth stages."

    def _ensure_achievements(self) -> None:
        allowed = {definition.achievement_id for definition in ACHIEVEMENT_DEFINITIONS}
        self.state.achievements = {
            key: value
            for key, value in self.state.achievements.items()
            if key in allowed
        }
        for definition in ACHIEVEMENT_DEFINITIONS:
            achievement = self.state.achievements.setdefault(
                definition.achievement_id,
                Achievement(
                    definition.achievement_id,
                    definition.name,
                    definition.description,
                ),
            )
            achievement.name = definition.name
            achievement.description = definition.description
            achievement.category = definition.category.value
            achievement.requirement = definition.description
            achievement.reward_summary = self._reward_bundle_description(
                definition.reward
            )

    def _refresh_achievement_progress(self, history: Any | None = None) -> None:
        current_day_answers = int(self.state.daily_stats.reviewed)
        streak_days = int(self.state.streak_days)
        lifetime_answers = int(self.state.lifetime_eligible_answers)
        non_again_run = int(self.state.current_non_again_run)
        if history is not None:
            current_summary = history.day_summary(history.current_open_day)
            current_day_answers = (
                int(current_summary.total_answers)
                if current_summary is not None
                else 0
            )
            streak_days = int(history.current_streak_days)
            lifetime_answers = int(history.lifetime_answers)
            non_again_run = int(history.current_non_again_tail)
        mature_species, full_bloom_species = species_progress_counts(self.state)
        valid_completions = max(
            0,
            int(
                getattr(
                    self.state.lifetime_economy_aggregates,
                    "today_cards_completions",
                    0,
                )
            ),
        )
        progress_values = AchievementProgressValues(
            streak_days=max(0, streak_days),
            daily_answers=max(0, current_day_answers),
            lifetime_answers=max(0, lifetime_answers),
            consecutive_non_again=max(0, non_again_run),
            valid_all_due_days=(
                1 if self.state.first_daily_completion_reward_claimed else 0
            ),
            mature_species=mature_species,
            full_bloom_species=full_bloom_species,
            valid_completions=valid_completions,
        )
        for definition in ACHIEVEMENT_DEFINITIONS:
            achievement = self.state.achievements[definition.achievement_id]
            if achievement.unlocked:
                achievement.progress = 1.0
                continue
            current = achievement_progress_value(definition, progress_values)
            achievement.progress = min(
                1.0,
                max(0.0, current / max(1, definition.progress_target)),
            )

    def _update_achievements(self, *, correlation_id: str = "") -> None:
        """Unlock only criteria that cannot be invalidated later in the day."""
        self._refresh_achievement_progress()
        day_value = self.state.daily_stats.day
        for definition in ACHIEVEMENT_DEFINITIONS:
            if definition.achievement_id == "all_due_done":
                continue
            achievement = self.state.achievements[definition.achievement_id]
            if achievement.progress >= 1.0:
                self._unlock_achievement(
                    definition.achievement_id,
                    completion_day=day_value,
                    correlation_id=(
                        correlation_id
                        or f"achievement:{definition.achievement_id}"
                    ),
                )
        # `_unlock_achievement` sets the committed row to progress 1.0. Its
        # current rewards (Coins, inventory, beds, and cosmetics) cannot alter
        # any achievement progress input, so a second full scan is identical.

    def _finalize_day_achievements(
        self,
        scheduler_day: str,
        *,
        answered: int,
        successful: int,
        again: int,
        fingerprint: str,
        correlation_id: str,
    ) -> tuple[str, ...]:
        """Finalize a closed-day fingerprint without rating-based rewards."""

        try:
            date.fromisoformat(str(scheduler_day))
        except (TypeError, ValueError):
            return ()
        del answered, successful, again, correlation_id
        self._record_finalized_day(scheduler_day, fingerprint)
        self._refresh_achievement_progress()
        return ()

    def _record_finalized_day(
        self,
        scheduler_day: str,
        fingerprint: str,
    ) -> None:
        stager = getattr(self.storage, "stage_finalized_day", None)
        if callable(stager):
            stager(str(scheduler_day), str(fingerprint))
            return
        self.state.finalized_day_fingerprints[str(scheduler_day)] = str(
            fingerprint
        )

    def progress_estimates(self, plant: Plant) -> int:
        stage_index = GROWTH_STAGES.index(plant.growth_stage)
        if stage_index >= len(GROWTH_STAGES) - 1:
            return 0
        remaining = GROWTH_THRESHOLDS[stage_index + 1] - plant.growth_points
        award = self.project_review_growth(plant)
        if award.total_growth <= 0:
            return 0
        return int(math.ceil(max(0, remaining) / award.total_growth))

    def export_progress_summary(self) -> str:
        stats = self.state.daily_stats
        source_components = {
            "base": max(0, int(stats.base_growth)),
            "streak": max(0, int(stats.streak_bonus_growth)),
            "fertilizer": max(0, int(stats.fertilizer_growth)),
            "weather": max(0, int(stats.weather_growth)),
            "scenery": max(0, int(stats.scenery_growth)),
            "trophies": max(0, int(stats.trophy_growth)),
            "other": max(0, int(stats.booster_growth)),
        }
        ledger = list(self.state.completed_growth_charge_requests)
        ledger_ids = [record.request_id for record in ledger]
        payload = {
            "schema_version": STATE_VERSION,
            "date": self.state.daily_stats.day,
            "streak": self.state.streak_days,
            "total_reviews": self.state.total_reviews,
            "garden_currency": self.state.currency_balance,
            "streak_bonus_percent": self.current_streak_bonus_percent(),
            "growth_reconciliation": {
                "study_sources": source_components,
                "study_source_total": sum(source_components.values()),
                "study_growth_generated": stats.study_growth_generated,
                "nurtured_by_plant": dict(stats.plant_nurtured_growth),
                "passive_exact_fifths_by_plant": dict(
                    stats.plant_passive_growth_fifths
                ),
                "passive_credited_by_plant": dict(
                    stats.plant_passive_growth_credited
                ),
                "charge_by_plant": dict(stats.plant_charge_growth),
                "direct_reward_by_plant": dict(
                    stats.plant_direct_reward_growth
                ),
                "legacy_unattributed": stats.legacy_unattributed_growth,
                "partially_stale": stats.growth_accounting_stale,
            },
            "growth_charge_replay_ledger": {
                "entries": len(ledger),
                "healthy": len(ledger_ids) == len(set(ledger_ids)),
            },
            "plants": [
                {
                    "name": PlantIdentity.from_plant(plant).display_name,
                    "species": plant.species,
                    "stage": plant.growth_stage,
                    "growth": plant.growth_points,
                    "planted": plant.planted,
                    "passive_growth_remainder_fifths": (
                        plant.passive_growth_remainder_fifths
                    ),
                }
                for plant in self.state.plants
            ],
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def local_time_band(moment: datetime | None = None) -> str:
        """Resolve the environment time band from the user's local clock."""
        local = moment.astimezone() if moment is not None else datetime.now().astimezone()
        hour = int(local.hour)
        if 5 <= hour < 8:
            return "dawn"
        if 8 <= hour < 17:
            return "day"
        if 17 <= hour < 20:
            return "dusk"
        return "night"

    def resolve_plant_image(self, species: str, stage: str) -> Optional[str]:
        asset = self.resolve_plant_asset(species, stage)
        return str(asset.path) if asset else None

    def resolve_plant_asset(self, species: str, stage: str) -> Optional[ResolvedAsset]:
        effective = stage if stage in GROWTH_STAGES else "seed"
        return self.assets.resolve(
            "plants",
            f"{species}_{effective}",
            f"slot:plants:{species}:{effective}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
        )

    def resolve_item_asset(self, item_key: str) -> Optional[ResolvedAsset]:
        """Resolve catalog item artwork from the bundled asset manifest.

        Most consumables and legacy Nursery items live in the ``ui`` manifest
        category.  Release 2.2 adds independently rendered cosmetic,
        Landmark, and Mastery artwork, whose catalog identities must be routed
        to their own categories instead of being treated as missing UI art.
        Accept both the logical catalog ID and packaged asset ID because the
        shared preview surfaces use both forms.
        """

        normalized = str(item_key or "").strip()
        if not normalized:
            return None
        theme = self.config.value("visual_theme", "verdant_twilight")

        cosmetic = COSMETIC_BY_ID.get(normalized)
        if cosmetic is None:
            cosmetic = next(
                (
                    definition
                    for definition in COSMETIC_BY_ID.values()
                    if definition.asset_id == normalized
                ),
                None,
            )
        if cosmetic is not None:
            cosmetic_id = str(cosmetic.cosmetic_id)
            return self.assets.resolve(
                "cosmetics",
                cosmetic.asset_id,
                f"slot:cosmetics:{cosmetic_id}:item-preview",
                theme=theme,
                quality_preference="balanced",
            )

        landmark = LANDMARK_BY_ID.get(normalized)
        if landmark is None:
            landmark = next(
                (
                    definition
                    for definition in LANDMARK_BY_ID.values()
                    if definition.asset_id == normalized
                ),
                None,
            )
        if landmark is not None:
            landmark_id = str(landmark.landmark_id)
            return self.assets.resolve(
                "landmarks",
                landmark_id,
                f"slot:landmarks:{landmark_id}:item-preview",
                theme=theme,
                quality_preference="balanced",
            )

        mastery_rank_id = normalized.removeprefix("mastery_")
        if mastery_rank_id in MASTERY_RANK_BY_ID and normalized in {
            mastery_rank_id,
            f"mastery_{mastery_rank_id}",
        }:
            if not mastery_enabled():
                return None
            return self.assets.resolve(
                "mastery",
                mastery_rank_id,
                f"slot:mastery:{mastery_rank_id}:item-preview",
                theme=theme,
                quality_preference="balanced",
            )

        return self.assets.resolve_ui_asset(
            normalized,
            quality_preference="balanced",
        )

    def resolve_nurtured_marker_asset(self) -> Optional[ResolvedAsset]:
        """Resolve retained watering-can artwork for compact Nurtured icons."""

        return self.assets.resolve_ui_asset(
            "nurtured_marker",
            quality_preference="balanced",
        )

    def resolve_nurtured_marker_spout_right_asset(self) -> Optional[ResolvedAsset]:
        """Resolve the upright-label can whose spout points to the right."""

        return self.assets.resolve_ui_asset(
            "nurtured_marker_spout_right",
            quality_preference="balanced",
        )

    def resolve_nurtured_marker_assets(self) -> dict[str, Optional[ResolvedAsset]]:
        """Return both retained orientations for compatibility and icon use."""

        return {
            "spout_left": self.resolve_nurtured_marker_asset(),
            "spout_right": self.resolve_nurtured_marker_spout_right_asset(),
        }

    def resolve_nurtured_marker_image(self) -> Optional[str]:
        asset = self.resolve_nurtured_marker_asset()
        return str(asset.path) if asset else None

    def resolve_nurtured_marker_spout_right_image(self) -> Optional[str]:
        asset = self.resolve_nurtured_marker_spout_right_asset()
        return str(asset.path) if asset else None

    def resolve_preview_assets(
        self,
        theme: str,
        weather: str,
        stage: str,
        quality_preference: str,
        plant_requests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        state = getattr(self, "state", None)
        scenery = getattr(state, "selected_background", DEFAULT_SCENERY_ID)
        normalized_theme = self.assets.normalize_theme(theme)
        background = self.assets.resolve(
            "backgrounds",
            f"bg_{scenery}_any",
            f"slot:backgrounds:{scenery}:any",
            theme=normalized_theme,
            time_of_day="any",
            quality_preference="balanced",
        )
        feature_id = canonical_garden_feature_id(weather)
        feature_asset = self.assets.resolve(
            "garden_features",
            f"garden_feature_{feature_id}",
            f"slot:garden_features:{feature_id}",
            theme=normalized_theme,
            quality_preference="balanced",
        )
        garden_overlay = self.resolve_garden_overlay_asset(
            theme=normalized_theme, quality_preference="balanced"
        )
        nurtured_markers = self.resolve_nurtured_marker_assets()
        plants: dict[str, Any] = {}
        requests = [
            (str(item.get("species") or ""), str(item.get("stage") or stage))
            for item in (plant_requests or [])
            if isinstance(item, dict) and item.get("species")
        ] or [(species, stage) for species in ("bonsai", "rose", "sunflower")]
        for species, requested_stage in requests:
            asset = self.assets.resolve(
                "plants", f"{species}_{requested_stage}", f"slot:plants:{species}:{requested_stage}",
                theme=normalized_theme, quality_preference="balanced",
            )
            plants[species] = asset.to_payload() if asset else None
        return {
            "background": background.to_payload() if background else None,
            "garden_overlay": garden_overlay.to_payload() if garden_overlay else None,
            "nurtured_marker": (
                nurtured_markers["spout_left"].to_payload()
                if nurtured_markers["spout_left"] else None
            ),
            "nurtured_marker_spout_right": (
                nurtured_markers["spout_right"].to_payload()
                if nurtured_markers["spout_right"] else None
            ),
            "garden_feature": feature_asset.to_payload() if feature_asset else None,
            "plant": plants.get("rose"),
            "plants": plants,
        }

    def resolve_background_image(self) -> Optional[str]:
        asset = self.resolve_background_asset()
        return str(asset.path) if asset else None

    def resolve_background_asset(self) -> Optional[ResolvedAsset]:
        scenery = self.state.selected_background
        return self.assets.resolve(
            "backgrounds",
            f"bg_{scenery}_any",
            f"slot:backgrounds:{scenery}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            time_of_day="any",
        )

    def resolve_landmark_asset(self) -> Optional[ResolvedAsset]:
        """Resolve only the completed Landmark appearance selected in state."""

        project = getattr(self.state, "garden_project", None)
        landmark_id = str(
            getattr(project, "displayed_project_id", "") or ""
        )
        completed = {
            str(item_id)
            for item_id in tuple(
                getattr(project, "completed_project_ids", ()) or ()
            )
        }
        if landmark_id not in LANDMARK_BY_ID or landmark_id not in completed:
            return None
        return self.assets.resolve(
            "landmarks",
            landmark_id,
            f"slot:landmarks:{landmark_id}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            quality_preference="balanced",
        )

    def resolve_landmark_image(self) -> Optional[str]:
        asset = self.resolve_landmark_asset()
        return str(asset.path) if asset else None

    def resolve_mastery_rank_asset(
        self,
        rank_id: str | None,
    ) -> Optional[ResolvedAsset]:
        """Resolve one universal Cultivation Mastery overlay by rank."""

        if not mastery_enabled():
            return None
        normalized = str(rank_id or "")
        if normalized not in MASTERY_RANK_BY_ID:
            return None
        return self.assets.resolve(
            "mastery",
            normalized,
            f"slot:mastery:{normalized}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            quality_preference="balanced",
        )

    def resolve_mastery_asset(
        self,
        species_id: str | None,
    ) -> Optional[ResolvedAsset]:
        """Resolve the highest unlocked universal overlay for one species."""

        mastery = getattr(self.state, "cultivation_mastery", None)
        ranks = getattr(mastery, "highest_rank_by_species", {})
        rank_id = (
            str(ranks.get(str(species_id or ""), "") or "")
            if isinstance(ranks, dict)
            else ""
        )
        return GardenGameEngine.resolve_mastery_rank_asset(self, rank_id)

    def resolve_mastery_image(self, species_id: str | None) -> Optional[str]:
        asset = self.resolve_mastery_asset(species_id)
        return str(asset.path) if asset else None

    def resolve_garden_feature_asset(
        self,
        item_id: str | None = None,
        *,
        preview: bool = False,
        respect_visibility: bool = True,
    ) -> Optional[ResolvedAsset]:
        # respect_visibility remains accepted for older callers. Equipped
        # artwork is always shown, including saves with retired false flags.
        feature_id = canonical_garden_feature_id(
            item_id or self.state.loadout.display_decoration_id
        )
        if feature_id not in GARDEN_FEATURE_CATALOG:
            return None
        resolved = self.assets.resolve(
            "garden_features",
            f"garden_feature_{feature_id}",
            (
                f"slot:garden_features:{feature_id}:preview"
                if preview
                else f"slot:garden_features:{feature_id}"
            ),
            theme=self.config.value("visual_theme", "verdant_twilight"),
            quality_preference="balanced",
        )
        return resolved

    def resolve_garden_feature_pad_asset(self) -> Optional[ResolvedAsset]:
        """Compatibility hook: physical support now comes from each decoration."""
        return None

    def resolve_garden_feature_preview_asset(
        self,
        item_id: str,
    ) -> Optional[ResolvedAsset]:
        """Resolve card/loadout artwork independently of scene visibility."""

        return self.resolve_garden_feature_asset(
            item_id,
            preview=True,
            respect_visibility=False,
        )

    def resolve_scenery_preview_asset(self, item_id: str) -> Optional[ResolvedAsset]:
        scenery = str(item_id)
        if scenery not in SCENERY_CATALOG:
            return None
        return self.assets.resolve(
            "backgrounds",
            f"bg_{scenery}_any",
            f"slot:backgrounds:{scenery}:preview",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            time_of_day="any",
            quality_preference="balanced",
        )

    def resolve_garden_overlay_image(self) -> Optional[str]:
        asset = self.resolve_garden_overlay_asset()
        return str(asset.path) if asset else None

    def resolve_garden_overlay_asset(
        self,
        *,
        theme: Optional[str] = None,
        quality_preference: Optional[str] = None,
    ) -> Optional[ResolvedAsset]:
        selected_theme = theme or str(self.config.value("visual_theme", "verdant_twilight"))
        return self.assets.resolve(
            "overlays",
            "overlay_garden_beds",
            "slot:overlays:garden_beds",
            theme=selected_theme,
            quality_preference=quality_preference,
        )

    def reroll_asset_slot(self, slot: str) -> Optional[str]:
        if slot == "background":
            scenery = self.state.selected_background
            path = self.assets.get_or_fetch(
                "backgrounds", f"bg_{scenery}_any", f"slot:backgrounds:{scenery}",
                theme=self.config.value("visual_theme", "verdant_twilight"), reroll=True,
            )
            return str(path) if path else None
        if slot in {"weather", "garden_feature"}:
            feature_id = self.state.displayed_garden_feature
            path = self.assets.get_or_fetch(
                "garden_features", f"garden_feature_{feature_id}",
                f"slot:garden_features:{feature_id}",
                theme=self.config.value("visual_theme", "verdant_twilight"), reroll=True,
            )
            return str(path) if path else None
        first = self._planted()[0] if self._planted() else None
        if first is None:
            return None
        path = self.assets.get_or_fetch(
            "plants", f"{first.species}_{first.growth_stage}",
            f"slot:plants:{first.species}:{first.growth_stage}",
            theme=self.config.value("visual_theme", "verdant_twilight"), reroll=True,
        )
        return str(path) if path else None
