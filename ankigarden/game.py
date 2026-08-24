from __future__ import annotations

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
from typing import Any, Dict, Mapping, Optional

from . import build_capabilities
from .asset_manager import AssetManager, ResolvedAsset
from .environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    ENVIRONMENT_CATALOG,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    catalog_items,
    environment_item,
)
from .achievements import (
    ACHIEVEMENT_DEFINITIONS,
    ACHIEVEMENTS_BY_ID,
    HistoricalReview,
    RewardBundle,
    STREAK_ACHIEVEMENTS,
    analyze_history,
)
from .garden_finds import (
    ENVIRONMENT_POOL_ID,
    ENVIRONMENT_POOL_VERSION,
    ENVIRONMENT_TIER_DENOMINATORS,
    KNOWN_ARTWORK_REFS,
    STANDARD_POOL_ID,
    STANDARD_POOL_VERSION,
    STANDARD_DAILY_CAP,
    STANDARD_DROUGHT_SCHEDULE,
    GardenFindReward,
    consumption_id,
    prepare_reward_registry,
    resolve_environment_find,
    resolve_standard_find,
    stable_answer_event_identity,
    ultra_denominator,
)
from .growth import (
    CompletedGrowthChargeRequest,
    GrowthAllocation,
    GrowthChargeOutcome,
    GrowthChargeQuote,
    GrowthChargeRequest,
    GrowthChargeStatus,
    GrowthChargeTargetState,
    StageRewardProjection,
)
from .models.state import (
    Achievement,
    ActivePlantPeriod,
    CurrencyTransaction,
    DailyStats,
    FeedbackEvent,
    GardenFindOutcome,
    Fertilizer,
    Booster,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    CURRENT_CATALOG_SPECIES_ORDER,
    MAX_COMPLETED_PURCHASE_REQUESTS,
    MAX_COMPLETED_GROWTH_CHARGE_REQUESTS,
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
    STREAK_BONUS_TIERS,
    bounded_reward_receipts,
    utc_now_iso,
)
from .purchases import (
    CompletedPurchaseRequest,
    EffectDescriptor,
    PurchaseDisposition,
    PurchaseKind,
    PurchaseOutcome,
    PurchaseQuote,
    PurchaseRequest,
    PurchaseStatus,
    purchase_presentation,
)
from .storage import DueObligationStatus, RevlogReadError, SchedulerBoundaryError


logger = logging.getLogger(__name__)


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
        }


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
    allocations: tuple[GrowthAllocation, ...] = ()
    correlation_id: str = field(default="", compare=False)
    reward_event_keys: tuple[str, ...] = field(default=(), compare=False)
    garden_find_ids: tuple[str, ...] = field(default=(), compare=False)
    achievement_ids: tuple[str, ...] = field(default=(), compare=False)

    @property
    def bonus_growth(self) -> int:
        return (
            self.streak_bonus_growth
            + self.fertilizer_growth
            + self.booster_growth
            + self.weather_growth
            + self.scenery_growth
        )

    @property
    def total_growth(self) -> int:
        return self.base_growth + self.bonus_growth

    @property
    def total_garden_growth(self) -> int:
        return sum(allocation.credited_growth for allocation in self.allocations)


@dataclass(frozen=True)
class PlacementChange:
    before: dict[str, int]
    after: dict[str, int]

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"before": dict(self.before), "after": dict(self.after)}


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
    duration_seconds: int
    price: int


class GardenGameEngine:
    BASE_GROWTH_PER_REVIEW = 10
    PASSIVE_GROWTH_DENOMINATOR = 5
    STREAK_MEMORY_MILESTONES = (3, 7, 14, 30, 60, 100, 365)
    STAGE_CURRENCY = {"sprout": 5, "young": 10, "mature": 20, "flowering": 35, "rare": 50}
    BOOSTER_GROWTH_PER_ANSWER = 5
    BOOSTER_DURATION_SECONDS = 2 * 60 * 60
    ALL_DUE_BASE_COINS = 10
    DAILY_ACTIVITY_COINS = 2
    WEEKLY_STREAK_COINS = 10
    CLOUDY_ALL_DUE_BONUS_COINS = 2
    RAINBOW_ALL_DUE_GROWTH = 5
    BED_PRICES = {2: 150, 3: 300, 4: 500, 5: 800}
    DIRECT_SOIL_SLOTS = frozenset(range(MAX_GARDEN_SLOTS))
    V6_SLOT_CENTERS = (
        (0.393, 0.45172), (0.611, 0.45172), (0.320, 0.60868),
        (0.538, 0.60868), (0.464, 0.78884), (0.682, 0.78884),
    )
    V4_SLOT_CENTERS = (
        (0.190, 0.526), (0.498, 0.526), (0.769, 0.526),
        (0.185, 0.765), (0.502, 0.835), (0.835, 0.765),
    )
    SOIL_PLANT_MESSAGE = "Choose an empty garden bed."
    SOIL_CAPACITY_MESSAGE = "Unlock or empty a garden bed before placing this plant."
    SPECIES_PRICES = {
        "bonsai": 100,
        "rose": 100,
        "sunflower": 150,
        "lavender": 200,
        "hydrangea": 250,
        "peony": 300,
        "foxglove": 350,
        "japanese_maple": 400,
        "wisteria": 500,
        "dahlia": 600,
    }
    FERTILIZERS = {
        "basic": FertilizerSpec("basic", "Basic Fertilizer", 1, 60 * 60, 25),
        "quality": FertilizerSpec("quality", "Quality Fertilizer", 2, 2 * 60 * 60, 65),
        # Keep the persisted ``premium`` key for compatibility; only its
        # learner-facing name changes.
        "premium": FertilizerSpec("premium", "Magical Fertilizer", 3, 4 * 60 * 60, 150),
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
        snapshot = self._state_snapshot()
        self.assets = AssetManager(config, storage)
        self._repair_environment_state()
        geometry_version, allowed_types = self._scene_surface_contract()
        self._scene_geometry_version = geometry_version
        self._surface_allowed_base_types = allowed_types
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
        self._repair_active_plant()
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
        return _StateSnapshot(deepcopy(self.state.to_dict()), checkpoint)

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
        weather_owned = list(dict.fromkeys([
            DEFAULT_WEATHER_ID,
            *(
                inventory.get("weather", [])
                if isinstance(inventory.get("weather"), list)
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
        inventory["weather"] = [
            item_id for item_id in weather_owned if item_id in WEATHER_CATALOG
        ]
        valid_scenery = [
            item_id for item_id in scenery_owned if item_id in SCENERY_CATALOG
        ]
        inventory.pop("backgrounds", None)
        inventory["scenery"] = list(valid_scenery)
        self.state.inventory = inventory
        if (
            self.state.selected_weather not in WEATHER_CATALOG
            or self.state.selected_weather not in inventory["weather"]
        ):
            self.state.selected_weather = DEFAULT_WEATHER_ID
        if (
            self.state.selected_background not in SCENERY_CATALOG
            or self.state.selected_background not in inventory["scenery"]
        ):
            self.state.selected_background = DEFAULT_SCENERY_ID
        decorations = inventory.get("decorations", [])
        if not isinstance(decorations, list):
            decorations = []
            inventory["decorations"] = decorations
        if self.state.loadout.decoration_id not in decorations:
            self.state.loadout.decoration_id = None
        visibility = (
            self.state.environment_visibility
            if isinstance(self.state.environment_visibility, dict)
            else {}
        )
        self.state.environment_visibility = {
            "weather": visibility.get("weather", True)
            if isinstance(visibility.get("weather", True), bool)
            else True,
            "scenery": visibility.get("scenery", True)
            if isinstance(visibility.get("scenery", True), bool)
            else True,
        }
        if not isinstance(self.state.daily_environment_claims, dict):
            self.state.daily_environment_claims = {}
        for item_id in ("booster_potion", "fertilizer_basic", *GROWTH_CHARGES):
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
        variant = profile.variants.get("16:9", {})
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
                message = f"{plant.name} was moved to an open garden bed."
            else:
                message = (
                    f"{plant.name} was returned to the Collection because no garden bed was open."
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

    def _append_reward_event_key(self, event_key: str) -> None:
        key = str(event_key)
        stager = getattr(self.storage, "stage_reward_event", None)
        if callable(stager):
            stager(key)
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
        return receipt

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
            actual_growth = self._apply_direct_growth(
                plant,
                max(0, int(growth)),
                stats_field="direct_reward_growth",
                transition_source=str(source),
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

        self._append_reward_event_key(key)
        return tuple(receipts)

    def rollover_if_needed(self, *, persist: bool = True) -> None:
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
        self.state.daily_stats = DailyStats(day=today)
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

    def fertilizer_growth(self, plant: Plant | None, *, now: float | None = None) -> int:
        if plant is None:
            return 0
        current = self._now_seconds() if now is None else float(now)
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
        if plant is None:
            return 0
        current = self._now_seconds() if now is None else float(now)
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
    ) -> str:
        """Apply the one canonical Fertilizer effect used by buys and Finds."""

        existing = plant.fertilizer
        current = existing if existing and existing.active(now) else None
        extending = current is not None and current.tier == spec.tier
        replacing = current is not None and current.tier != spec.tier
        archived = (
            None
            if extending
            else self._historical_fertilizer_period(existing, ended_at=now)
        )
        history_identities = {
            self._fertilizer_period_identity(period)
            for period in plant.fertilizer_history
        }
        if (
            archived is not None
            and self._fertilizer_period_identity(archived) not in history_identities
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
        expiration_base = current.expires_at if extending else now
        activation_start = (
            current.started_at
            if extending and current.started_at is not None
            else now
        )
        plant.fertilizer = Fertilizer(
            spec.tier,
            spec.growth_per_answer,
            expiration_base + spec.duration_seconds,
            activation_start,
        )
        return "extended" if extending else "replaced" if replacing else "applied"

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

    @staticmethod
    def streak_bonus_percent(streak_days: int) -> int:
        days = max(0, int(streak_days))
        bonus = 0
        for threshold, percent in STREAK_BONUS_TIERS:
            if days >= threshold:
                bonus = percent
            else:
                break
        return bonus

    def current_streak_bonus_percent(self) -> int:
        return self.streak_bonus_percent(self.state.streak_days)

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

    def reconcile_reward_history(
        self,
        *,
        persist: bool = True,
        include_open_day: bool = True,
    ) -> tuple[bool, str]:
        """Rebuild achievements and process only post-activation synced answers.

        Rollover uses ``include_open_day=False`` because Anki has already added
        the answer that triggered the reviewer hook to revlog. Normal startup
        and sync maintenance include the open day so unseen mobile reviews are
        caught up.
        """

        resolver = getattr(self.storage, "load_eligible_review_history", None)
        if not callable(resolver):
            return False, "Anki review history is not available yet."
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
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
                if include_open_day or str(entry.scheduler_day) < current_day
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
            history = analyze_history(reviews, current_open_day=current_day)
            self.state.lifetime_eligible_answers = int(history.lifetime_answers)
            self.state.current_non_again_run = int(history.current_non_again_tail)
            self.state.streak_days = int(history.current_streak_days)
            if history.latest_active_day:
                self.state.last_active_day = history.latest_active_day
            self._ensure_achievements()

            reconciled_high_water = max(
                (int(entry.revlog_id) for entry in entries),
                default=0,
            )
            sync_correlation = (
                f"sync:{reconciled_high_water}:{history.fingerprint[:12]}"
            )
            existing_receipts = tuple(self.state.recent_reward_receipts)
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
            for summary in history.daily_summaries:
                if summary.closed:
                    self._record_finalized_day(
                        summary.scheduler_day,
                        f"history:{summary.total_answers}:"
                        f"{summary.non_again_answers}:{summary.again_answers}"
                    )

            streak_by_day = self._streak_by_scheduler_day(
                entries
            )
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
                    if not any(
                        int(entry.answer_ms) >= recurring_boundary
                        for entry in entries_by_day.get(day_value, ())
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
            current_stats = self.state.daily_stats
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
            for entry in entries:
                day_value = str(entry.scheduler_day)
                day_answer_numbers[day_value] = day_answer_numbers.get(day_value, 0) + 1
                answer_number = day_answer_numbers[day_value]
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
                else:
                    self.state.daily_stats = temporary_stats.setdefault(
                        day_value, DailyStats(day=day_value)
                    )
                semantics = queue_and_lapse_from_revlog_type(
                    entry.review_type, entry.ease
                )
                if semantics is None:
                    continue
                queue, lapse_count = semantics
                award = self._register_review_in_memory({
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
                    "emit_feedback": False,
                    "correlation_id": sync_correlation,
                })
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
            self.state.achievement_history_fingerprint = history.fingerprint
            self.state.achievement_history_high_water_revlog_id = (
                reconciled_high_water
            )
            self._refresh_achievement_progress(history)

            sync_receipts = tuple(
                receipt
                for receipt in self.state.recent_reward_receipts
                if receipt not in existing_receipts
                if receipt.correlation_id == sync_correlation
            )
            if sync_receipts:
                self._queue_reward_feedback(
                    sync_correlation,
                    sync_receipts,
                    achievement_ids=unlocked_during_sync,
                    title=f"{len(sync_receipts):,} Garden rewards added",
                )
            elif synced_answers and synced_growth:
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
            return True, "Garden is up to date."
        except (RevlogReadError, SchedulerBoundaryError, ValueError, TypeError):
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "Anki review history is not available yet."
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise

    def reconcile_retrospective_streak(self, *, persist: bool = True) -> tuple[bool, str]:
        """Compatibility alias for the unified reward-history reconciliation."""

        return self.reconcile_reward_history(persist=persist)

    def register_review(self, review_payload: Dict[str, Any]) -> ReviewAward:
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.rollover_if_needed(persist=False)
        try:
            award = self._register_review_in_memory(review_payload)
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
                "This card answer has no stable review identity and was not counted.",
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
                None, 0, 0, 0, 0, "This card answer was already counted."
            )
        if not historical_sync:
            processed = self.state.processed_revlog_ids
            index = bisect_left(processed, revlog_id)
            if (
                revlog_id <= self.state.processed_revlog_floor
                or (index < len(processed) and processed[index] == revlog_id)
            ):
                return ReviewAward(None, 0, 0, 0, 0, "This card answer was already counted.")
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
        existing_receipts = tuple(self.state.recent_reward_receipts)
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
            self._grant_reward_bundle(
                daily_activity_event_key,
                source="daily_activity",
                source_id=scheduler_day,
                reason="First eligible answer of the Anki day",
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
            )
        else:
            paused_reason = (
                "Choose an unfinished plant to nurture to resume Growth."
                if self.state.starter_selection_complete
                and int(self.state.garden_setup_version) >= 1
                else "Complete Garden setup before answer rewards begin."
            )
            award = ReviewAward(
                plant.plant_id if plant is not None else None,
                0,
                0,
                0,
                self.streak_bonus_percent(
                    self.state.streak_days
                    if explicit_streak is None
                    else explicit_streak
                ),
                paused_reason,
            )
        # Attribute milestones crossed by this answer to the plant that
        # received it. Reaching Rare clears the nurtured-plant pointer, so
        # looking it up again here would otherwise lose same-answer memories.
        self._record_shared_memories(previous_reviews, previous_streak, plant=plant)
        if progression_eligible:
            self._grant_daily_environment_gift(
                answer_identity,
                scheduler_day=scheduler_day,
                plant=plant,
                correlation_id=correlation_id,
            )
        finds_eligible = bool(
            progression_eligible
            and event_ms >= max(1, int(self.state.garden_find_activation_ms))
        )
        if finds_eligible:
            self._resolve_garden_finds(
                answer_identity,
                answer_key=answer_key,
                scheduler_day=scheduler_day,
                plant=plant,
                correlation_id=correlation_id,
            )
        self._update_achievements(correlation_id=correlation_id)
        if not historical_sync:
            self._acknowledge_current_revlog(revlog_id)
        new_receipts = tuple(
            receipt
            for receipt in self.state.recent_reward_receipts
            if receipt not in existing_receipts
        )
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
            if receipt.source in {"garden_find", "garden_find_environment"}
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
        if bundle.coins:
            parts.append(f"+{bundle.coins:,} Garden Coins")
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
            source="achievement_backfill" if historical else "achievement",
            source_id=definition.achievement_id,
            reason=f"Achievement: {definition.name}",
            scheduler_day=completion_day,
            correlation_id=correlation_id,
            coins=definition.reward.coins,
            inventory_items={
                "growth_charge_small": definition.reward.small_growth_charges,
                "growth_charge_standard": definition.reward.standard_growth_charges,
            },
            title=definition.name,
            description=definition.description,
        )
        now = utc_now_iso()
        achievement.unlocked = True
        achievement.progress = 1.0
        achievement.unlocked_at = (
            f"{completion_day}T00:00:00+00:00" if historical else now
        )
        achievement.rewarded_at = now
        achievement.reward_event_key = event_key
        achievement.historical_backfill = bool(historical)
        if definition.achievement_id == "streak_7":
            # Integrate the first badge payout with the first weekly cycle.
            self._append_reward_event_key(f"weekly_streak:{completion_day}")
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
        definition = next(
            (
                candidate
                for candidate in STREAK_ACHIEVEMENTS
                if candidate.progress_target == days
            ),
            None,
        )
        if definition is not None:
            self._unlock_achievement(
                definition.achievement_id,
                completion_day=scheduler_day,
                correlation_id=correlation_id,
            )
        if allow_recurring_reward and days > 0 and days % 7 == 0:
            self._grant_reward_bundle(
                f"weekly_streak:{scheduler_day}",
                source="weekly_streak",
                source_id=f"day_{days}",
                reason=f"Day {days} seven-day streak cycle",
                scheduler_day=scheduler_day,
                correlation_id=correlation_id,
                coins=self.WEEKLY_STREAK_COINS,
                title="Seven-day streak reward",
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
        if str(kind) == "weather":
            return WEATHER_CATALOG.get(
                self.state.selected_weather, WEATHER_CATALOG[DEFAULT_WEATHER_ID]
            )
        return SCENERY_CATALOG.get(
            self.state.selected_background, SCENERY_CATALOG[DEFAULT_SCENERY_ID]
        )

    def owns_environment(self, kind: str, item_id: str) -> bool:
        if str(kind) == "weather":
            return str(item_id) in self.state.inventory.get("weather", [])
        return str(item_id) in {
            *self.state.inventory.get("backgrounds", []),
            *self.state.inventory.get("scenery", []),
        }

    def _weather_review_growth(self, answer_number: int) -> int:
        weather = self.state.selected_weather
        if weather == "breeze" and answer_number <= 10:
            return 1
        if weather == "gentle_rain" and answer_number <= 20:
            return 1
        if weather == "fireflies" and answer_number <= 5:
            return 5
        return 0

    def _scenery_review_growth(self, answer_number: int) -> int:
        scenery = self.state.selected_background
        if scenery == "spring" and answer_number <= 25:
            return 1
        if scenery == "summer" and answer_number % 2 == 0:
            return 1
        if scenery == "rainbow_horizon":
            return 1
        if scenery == "eclipse":
            # This is a flat secondary award, not a multiplier over streak,
            # Fertilizer, Booster, or weather bonuses.
            return self.BASE_GROWTH_PER_REVIEW
        return 0

    def _review_growth_projection(
        self,
        plant: Plant | None,
        event_ms: int,
        *,
        answer_number: int,
        streak_days: int | None = None,
    ) -> tuple[ReviewAward, int]:
        """Project one review award without mutating plant or daily state."""

        if plant is None:
            return (
                ReviewAward(
                    None,
                    0,
                    0,
                    0,
                    0,
                    "Choose an unfinished plant to nurture to resume Growth.",
                ),
                0,
            )
        bonus_percent = self.streak_bonus_percent(
            self.state.streak_days if streak_days is None else streak_days
        )
        bonus_numerator = plant.bonus_remainder + (self.BASE_GROWTH_PER_REVIEW * bonus_percent)
        proposed_streak_bonus, next_remainder = divmod(bonus_numerator, 100)
        proposed_fertilizer_bonus = self.fertilizer_growth(plant, now=event_ms / 1000)
        proposed_booster_bonus = self.booster_growth(plant, now=event_ms / 1000)
        answer_number = max(1, int(answer_number))
        proposed_weather_bonus = self._weather_review_growth(answer_number)
        proposed_scenery_bonus = self._scenery_review_growth(answer_number)
        remaining = max(0, GROWTH_THRESHOLDS[-1] - plant.growth_points)
        base = min(self.BASE_GROWTH_PER_REVIEW, remaining)
        bonus_remaining = max(0, remaining - base)
        streak_bonus = min(proposed_streak_bonus, bonus_remaining)
        fertilizer_bonus = min(proposed_fertilizer_bonus, max(0, bonus_remaining - streak_bonus))
        booster_bonus = min(
            proposed_booster_bonus,
            max(0, bonus_remaining - streak_bonus - fertilizer_bonus),
        )
        weather_bonus = min(
            proposed_weather_bonus,
            max(0, bonus_remaining - streak_bonus - fertilizer_bonus - booster_bonus),
        )
        scenery_bonus = min(
            proposed_scenery_bonus,
            max(
                0,
                bonus_remaining
                - streak_bonus
                - fertilizer_bonus
                - booster_bonus
                - weather_bonus,
            ),
        )
        total = (
            base
            + streak_bonus
            + fertilizer_bonus
            + booster_bonus
            + weather_bonus
            + scenery_bonus
        )
        if total <= 0:
            return (
                ReviewAward(
                    plant.plant_id,
                    0,
                    0,
                    0,
                    bonus_percent,
                    "This plant is fully grown.",
                ),
                0,
            )
        return (
            ReviewAward(
                plant.plant_id,
                base,
                streak_bonus,
                fertilizer_bonus,
                bonus_percent,
                booster_growth=booster_bonus,
                weather_growth=weather_bonus,
                scenery_growth=scenery_bonus,
            ),
            next_remainder,
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
        return replace(
            award,
            allocations=self._project_review_allocations(target, award),
        )

    def _project_review_allocations(
        self,
        plant: Plant | None,
        award: ReviewAward,
    ) -> tuple[GrowthAllocation, ...]:
        if plant is None or award.total_growth <= 0:
            return ()
        allocations: list[GrowthAllocation] = [GrowthAllocation(
            plant_id=plant.plant_id,
            role="nurtured",
            exact_fifths=(
                award.total_growth * self.PASSIVE_GROWTH_DENOMINATOR
            ),
            credited_growth=award.total_growth,
        )]
        for passive in sorted(
            (
                candidate
                for candidate in self.state.plants
                if (
                    candidate.plant_id != plant.plant_id
                    and candidate.planted
                    and not candidate.fully_grown
                )
            ),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        ):
            residual_before = max(
                0,
                min(
                    self.PASSIVE_GROWTH_DENOMINATOR - 1,
                    int(passive.passive_growth_remainder_fifths),
                ),
            )
            whole_growth, residual_after = divmod(
                residual_before + award.total_growth,
                self.PASSIVE_GROWTH_DENOMINATOR,
            )
            credited = min(
                whole_growth,
                max(0, GROWTH_THRESHOLDS[-1] - int(passive.growth_points)),
            )
            allocations.append(GrowthAllocation(
                plant_id=passive.plant_id,
                role="passive",
                exact_fifths=award.total_growth,
                credited_growth=credited,
                residual_before_fifths=residual_before,
                residual_after_fifths=(
                    0
                    if int(passive.growth_points) + credited >= GROWTH_THRESHOLDS[-1]
                    else residual_after
                ),
            ))
        return tuple(allocations)

    def _award_review_growth(
        self,
        plant: Plant | None,
        event_ms: int,
        *,
        streak_days: int | None = None,
        answer_number: int | None = None,
    ) -> ReviewAward:
        award, next_remainder = self._review_growth_projection(
            plant,
            event_ms,
            answer_number=(
                max(1, int(self.state.daily_stats.reviewed))
                if answer_number is None
                else max(1, int(answer_number))
            ),
            streak_days=streak_days,
        )
        if plant is None or award.total_growth <= 0:
            return award
        passive_plants = sorted(
            (
                candidate
                for candidate in self.state.plants
                if (
                    candidate.plant_id != plant.plant_id
                    and candidate.planted
                    and not candidate.fully_grown
                )
            ),
            key=lambda candidate: (
                int(candidate.slot_index or 0),
                candidate.plant_id,
            ),
        )
        allocations: list[GrowthAllocation] = []
        before = plant.growth_points
        plant.growth_points += award.total_growth
        plant.bonus_remainder = next_remainder if plant.growth_points < GROWTH_THRESHOLDS[-1] else 0
        stats = self.state.daily_stats
        stats.base_growth += award.base_growth
        stats.streak_bonus_growth += award.streak_bonus_growth
        stats.fertilizer_growth += award.fertilizer_growth
        stats.booster_growth += award.booster_growth
        stats.weather_growth += award.weather_growth
        stats.scenery_growth += award.scenery_growth
        stats.plant_nurtured_growth[plant.plant_id] = (
            stats.plant_nurtured_growth.get(plant.plant_id, 0)
            + award.total_growth
        )
        allocations.append(GrowthAllocation(
            plant_id=plant.plant_id,
            role="nurtured",
            exact_fifths=(
                award.total_growth * self.PASSIVE_GROWTH_DENOMINATOR
            ),
            credited_growth=award.total_growth,
        ))
        self._record_growth_crossings(
            plant,
            before,
            plant.growth_points,
            source="nurtured",
        )

        for passive in passive_plants:
            passive_before = int(passive.growth_points)
            residual_before = max(
                0,
                min(
                    self.PASSIVE_GROWTH_DENOMINATOR - 1,
                    int(passive.passive_growth_remainder_fifths),
                ),
            )
            whole_growth, residual_after = divmod(
                residual_before + award.total_growth,
                self.PASSIVE_GROWTH_DENOMINATOR,
            )
            credited = min(
                whole_growth,
                max(0, GROWTH_THRESHOLDS[-1] - passive_before),
            )
            passive.growth_points += credited
            passive.passive_growth_remainder_fifths = (
                0 if passive.fully_grown else residual_after
            )
            stats.plant_passive_growth_fifths[passive.plant_id] = (
                stats.plant_passive_growth_fifths.get(passive.plant_id, 0)
                + award.total_growth
            )
            if credited:
                stats.plant_passive_growth_credited[passive.plant_id] = (
                    stats.plant_passive_growth_credited.get(passive.plant_id, 0)
                    + credited
                )
                self._record_growth_crossings(
                    passive,
                    passive_before,
                    passive.growth_points,
                    source="passive",
                )
            allocations.append(GrowthAllocation(
                plant_id=passive.plant_id,
                role="passive",
                exact_fifths=award.total_growth,
                credited_growth=credited,
                residual_before_fifths=residual_before,
                residual_after_fifths=passive.passive_growth_remainder_fifths,
            ))
        stats.reconcile_growth_totals()
        return replace(award, allocations=tuple(allocations))

    def _grant_daily_environment_gift(
        self,
        answer_identity: str,
        *,
        scheduler_day: str,
        plant: Plant | None,
        correlation_id: str,
    ) -> bool:
        """Grant the existing scenery gift without suppressing either Find pool."""

        scenery = self.state.selected_background
        if scenery not in {"snowy", "halloween", "full_moon"}:
            return False
        event_key = f"environment_daily:{scenery}:{scheduler_day}"
        if self._reward_applied(event_key):
            return False
        if scenery == "snowy":
            consumable_id = "growth_charge_small"
        elif scenery == "full_moon":
            consumable_id = "booster_potion"
        else:
            digest = hashlib.blake2b(
                f"{self.state.reward_seed}:{answer_identity}".encode("utf-8"),
                digest_size=32,
                person=b"halloween-gift",
            ).digest()
            roll = int.from_bytes(digest[:8], "big") % 100
            consumable_id = (
                "growth_charge_small"
                if roll < 70
                else "growth_charge_standard"
                if roll < 95
                else "booster_potion"
            )
        name = (
            "Booster Potion"
            if consumable_id == "booster_potion"
            else GROWTH_CHARGES[consumable_id].name
        )
        scenery_name = SCENERY_CATALOG[scenery].name
        receipts = self._grant_reward_bundle(
            event_key,
            source="environment_daily_gift",
            source_id=scenery,
            reason=f"{scenery_name} daily gift",
            scheduler_day=scheduler_day,
            correlation_id=correlation_id,
            inventory_item_id=consumable_id,
            inventory_quantity=1,
            title=f"{scenery_name} daily gift",
            description=f"+1 {name}",
        )
        if receipts:
            self.state.daily_environment_claims[scenery] = scheduler_day
            return True
        return False

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
            source="garden_find",
            source_id=reward.reward_id,
            reason=f"Garden Find: {reward.display_name}",
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
        inventory_key = "weather" if environment_kind == "weather" else "scenery"
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
            description=f"{tier.replace('_', ' ').title()} Garden Find",
        )
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
            self.state.garden_find_daily_counts[outcome.scheduler_day] = min(
                STANDARD_DAILY_CAP, finds_today + 1
            )
            reward_counts = self.state.garden_find_reward_daily_counts.setdefault(
                outcome.scheduler_day, {}
            )
            reward_counts[outcome.reward_id] = min(
                STANDARD_DAILY_CAP,
                max(0, int(reward_counts.get(outcome.reward_id, 0))) + 1,
            )

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
                growth_available=bool(plant is not None and not plant.fully_grown),
                available_inventory_item_ids=self.state.consumables.keys(),
                reward_daily_counts=reward_daily_counts,
                scheduler_day=scheduler_day,
                addon_version=self._addon_version,
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
                *self.state.inventory.get("weather", []),
                *self.state.inventory.get("scenery", []),
            }
            environment = resolve_environment_find(
                secret=self.state.reward_seed,
                answer_identity=answer_identity,
                owned_environment_ids=owned_environment_ids,
                ultra_pity_misses=self.state.garden_find_ultra_misses,
            )
            self.state.garden_find_ultra_misses = (
                environment.next_ultra_pity_misses
            )
            environment_reward_id = ""
            environment_reward_type = ""
            environment_item_id = ""
            environment_amount = 0
            if environment.hit and environment.item is not None:
                item = environment.item
                event_key = f"garden_find:{answer_key}:{ENVIRONMENT_POOL_ID}"
                receipts = self._grant_environment_find(
                    event_key=event_key,
                    item_id=item.item_id,
                    environment_kind=item.environment_kind,
                    display_name=item.display_name,
                    tier=item.tier,
                    scheduler_day=scheduler_day,
                    correlation_id=correlation_id,
                )
                environment_reward_id = item.item_id
                environment_reward_type = "environment_item"
                environment_item_id = item.item_id
                environment_amount = 1 if receipts else 1
                found_ids.append(item.item_id)
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
                    "Added to the Weather and Scenery collection"
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
            if receipt.source in {"garden_find", "garden_find_environment"}
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
                ACHIEVEMENTS_BY_ID[item].name
                for item in visible_achievement_ids
                if item in ACHIEVEMENTS_BY_ID
            ]
            if names:
                parts.append("Unlocked " + ", ".join(names))
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
        for stage_index in range(previous_index + 1, new_index + 1):
            previous_stage = GROWTH_STAGES[stage_index - 1]
            new_stage = GROWTH_STAGES[stage_index]
            base_reward = self.STAGE_CURRENCY[new_stage]
            reward = (
                (base_reward * 5 + 2) // 4
                if self.state.selected_background == "autumn"
                else base_reward
            )
            projected.append((
                previous_stage,
                new_stage,
                StageRewardProjection(new_stage, reward),
            ))
        return tuple(projected)

    def _record_growth_crossings(
        self,
        plant: Plant,
        before: int,
        after: int,
        *,
        source: str = "nurtured",
    ) -> None:
        for index in range(len(GROWTH_STAGES) - 1):
            stage = GROWTH_STAGES[index]
            start, end = GROWTH_THRESHOLDS[index], GROWTH_THRESHOLDS[index + 1]
            for percent in (25, 50, 75):
                point = start + math.ceil((end - start) * percent / 100)
                if before < point <= after:
                    self._queue_feedback(
                        f"growth:{plant.plant_id}:{stage}:{percent}",
                        "growth_milestone",
                        f"{plant.name} is {percent}% of the way to {GROWTH_STAGES[index + 1].title()}.",
                        plant.plant_id,
                    )
        for previous_stage, new_stage, reward_projection in self._project_stage_rewards(
            before,
            after,
        ):
            self._add_memory(
                plant,
                f"stage:{new_stage}",
                "stage",
                previous_stage=previous_stage,
                new_stage=new_stage,
            )
            transition = StageTransition(
                plant.plant_id,
                plant.species,
                previous_stage,
                new_stage,
                plant.name,
                source,
            )
            self._pending_stage_transitions.append(transition)
            reward = reward_projection.garden_coins
            self._credit_currency(
                f"stage:{plant.plant_id}:{new_stage}",
                f"{plant.name} reached {new_stage.title()}",
                reward,
                feedback=(
                    f"{plant.name} reached {new_stage.title()} and earned "
                    f"{reward} Garden Coins."
                ),
                plant_id=plant.plant_id,
            )
        if after >= GROWTH_THRESHOLDS[-1] and self.state.active_plant_id == plant.plant_id:
            self.state.active_plant_id = None
            self._record_active_period(None)
            self._queue_feedback(
                f"nurture-needed:{plant.plant_id}:rare",
                "nurture_needed",
                f"{plant.name} is fully grown. Choose another unfinished plant to nurture to keep earning Growth.",
                plant.plant_id,
            )

    def _apply_direct_growth(
        self,
        plant: Plant | None,
        requested: int,
        *,
        stats_field: str,
        transition_source: str = "direct_reward",
    ) -> int:
        if plant is None or plant.fully_grown or requested <= 0:
            return 0
        before = int(plant.growth_points)
        awarded = min(
            max(0, int(requested)),
            max(0, GROWTH_THRESHOLDS[-1] - before),
        )
        if awarded <= 0:
            return 0
        plant.growth_points += awarded
        if plant.fully_grown:
            plant.bonus_remainder = 0
            plant.passive_growth_remainder_fifths = 0
        stats = self.state.daily_stats
        if stats_field == "charge_growth":
            target_map = stats.plant_charge_growth
        elif stats_field == "direct_reward_growth":
            target_map = stats.plant_direct_reward_growth
        else:
            raise ValueError(f"unsupported direct Growth source: {stats_field}")
        target_map[plant.plant_id] = target_map.get(plant.plant_id, 0) + awarded
        stats.reconcile_growth_totals()
        self._record_growth_crossings(
            plant,
            before,
            plant.growth_points,
            source=transition_source,
        )
        return awarded

    def all_due_rewards(self) -> tuple[int, int]:
        """Return today's shared mechanics values for the all-due reward."""

        coins = self.ALL_DUE_BASE_COINS + (
            self.CLOUDY_ALL_DUE_BONUS_COINS
            if self.state.selected_weather == "cloudy" else 0
        )
        growth = (
            self.RAINBOW_ALL_DUE_GROWTH
            if self.state.selected_weather == "rainbow_sunshower" else 0
        )
        return coins, growth

    def observe_due_start(self, status: DueObligationStatus | None) -> bool:
        """Persist the collection-wide due baseline before the first answer."""

        self.rollover_if_needed()
        stats = self.state.daily_stats
        if stats.reviewed > 0 or stats.due_started_with_cards is not None:
            return stats.due_started_with_cards is True
        if status is None or not status.available or status.error:
            return False
        snapshot = self._state_snapshot()
        stats.due_started_with_cards = status.remaining > 0
        self._persist_or_restore(snapshot)
        return stats.due_started_with_cards is True

    def evaluate_all_due(self, status: DueObligationStatus | None = None) -> tuple[bool, str]:
        # Rollover is itself durable state. Persist it before taking the reward
        # snapshot so every early-return branch leaves memory and disk aligned.
        self.rollover_if_needed()
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        stats = self.state.daily_stats
        if stats.completed_due_cards:
            return False, "You already earned today’s reward for finishing all due cards."
        if not self._reward_applied(f"daily_activity:{stats.day}"):
            return False, "Answer at least one card before you can earn the reward for finishing all due cards."
        if stats.due_started_with_cards is not True:
            return False, (
                "Today did not begin with a verified due review or learning step."
            )
        if not self.state.starter_selection_complete:
            return False, "Complete Garden setup before all-due rewards begin."
        if status is None:
            resolver = getattr(self.storage, "due_obligations", None)
            status = resolver() if callable(resolver) else DueObligationStatus(available=False, error="Unavailable")
        if not status.complete:
            if status.error:
                return False, status.error
            unit = "due review or learning step remains" if status.remaining == 1 else "due reviews or learning steps remain"
            return False, f"{status.remaining:,} {unit}."
        try:
            if not self.state.reward_state_initialized:
                self.initialize_reward_state(persist=False)
            stats.completed_due_cards = True
            coin_reward, configured_growth = self.all_due_rewards()
            correlation_id = f"all-due:{stats.day}"
            existing_receipts = tuple(self.state.recent_reward_receipts)
            self._grant_reward_bundle(
                f"all_due:{stats.day}",
                source="all_due",
                source_id=stats.day,
                reason="All due cards finished",
                scheduler_day=stats.day,
                correlation_id=correlation_id,
                coins=coin_reward,
                growth=configured_growth,
                plant=self.active_plant(),
                title="All due cards finished",
            )
            all_clear_unlocked = self._unlock_achievement(
                "all_due_done",
                completion_day=stats.day,
                correlation_id=correlation_id,
            )
            receipts = tuple(
                receipt
                for receipt in self.state.recent_reward_receipts
                if receipt not in existing_receipts
            )
            total_coins = sum(
                receipt.amount for receipt in receipts if receipt.reward_type == "coins"
            )
            weather_growth = sum(
                receipt.amount for receipt in receipts if receipt.reward_type == "growth"
            )
            feedback = (
                f"You finished all due cards and earned {total_coins} Garden Coins"
                + (f" and {weather_growth} Growth." if weather_growth else ".")
            )
            self._queue_reward_feedback(
                correlation_id,
                receipts,
                achievement_ids=("all_due_done",) if all_clear_unlocked else (),
                plant_id=self.state.active_plant_id,
                title="Anki day complete",
            )
            self._refresh_achievement_progress()
            self._persist_or_restore(snapshot)
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "The reward for finishing all due cards could not be saved."
        return True, feedback

    def apply_same_day_reviews(self, reviews: list[Dict[str, Any]], *, latest_revlog_id: int = 0) -> int:
        if not reviews:
            if latest_revlog_id > self.state.last_processed_revlog_id:
                snapshot = self._state_snapshot()
                self.state.last_processed_revlog_id = int(latest_revlog_id)
                self._persist_or_restore(snapshot)
            return 0
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.rollover_if_needed(persist=False)
        total = 0
        try:
            ordered = sorted(reviews, key=lambda row: int(row.get("revlog_id", 0) or 0))
            for payload in ordered:
                award = self._register_review_in_memory(payload)
                total += award.total_growth
            self.state.last_processed_revlog_id = max(
                self.state.last_processed_revlog_id, max(0, int(latest_revlog_id))
            )
            self._persist_or_restore(snapshot)
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise
        return total

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
    ) -> bool:
        receipts = self._grant_reward_bundle(
            event_key,
            source=source,
            source_id=source_id or event_key,
            reason=reason,
            scheduler_day=scheduler_day,
            correlation_id=correlation_id or event_key,
            coins=amount,
            title=reason,
        )
        if feedback and receipts:
            self._queue_feedback(
                event_key,
                "currency",
                feedback,
                plant_id,
                correlation_id=correlation_id or event_key,
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
        return list(self.state.pending_feedback)

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
                        self.state.selected_weather == item.item_id
                        if kind == "weather"
                        else self.state.selected_background == item.item_id
                    ),
                    "visible": bool(
                        self.state.environment_visibility.get(kind, True)
                    ),
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
            "daily_cap": STANDARD_DAILY_CAP,
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

        duration = cls._duration_label(cls.BOOSTER_DURATION_SECONDS)
        return EffectDescriptor(
            function="Applies a timed Growth boost to the nurtured plant.",
            buff=(
                f"+{cls.BOOSTER_GROWTH_PER_ANSWER:,} Growth per Anki card "
                "answer while active."
            ),
            activation_condition=(
                "Use on a nurtured, unfinished planted plant."
            ),
            duration=(
                f"Lasts {duration}; another Potion adds more time."
            ),
            stacking="Inventory quantities stack; active duration extends.",
            replacement="Replaces nothing.",
            unlock_requirement=(
                "Earn from a Garden Find or daily Scenery reward."
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
        inventory_before: int = 0,
        inventory_after: int = 0,
        current_equipped_name: str = "",
        state_signature: Any = None,
    ) -> PurchaseQuote:
        price = max(0, int(unit_price))
        balance = max(0, int(self.state.currency_balance))
        effective_status = status
        effective_message = str(message)
        if effective_status is PurchaseStatus.READY and balance < price:
            effective_status = PurchaseStatus.INSUFFICIENT_COINS
            shortfall = price - balance
            effective_message = (
                f"You need {shortfall:,} more Garden Coins to purchase {item_name}."
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
            name = f"{species.replace('_', ' ').title()} Seed" if species else "Plant Seed"
            price = self.SPECIES_PRICES.get(species)
            descriptor = EffectDescriptor(
                function=f"Adds {species.replace('_', ' ').title()} to your collection.",
                buff="Grows from card answers while nurtured.",
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

        if purchase_kind is PurchaseKind.FERTILIZER:
            tier = normalized_item.lower()
            spec = self.FERTILIZERS.get(tier)
            plant = self.plant_story(str(target_id or ""))
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
            duration = self._duration_label(spec.duration_seconds)
            descriptor = EffectDescriptor(
                function="Adds Growth to each card answer.",
                buff=f"+{spec.growth_per_answer:,} Growth per card.",
                activation_condition="Use on a nurtured plant that is still growing.",
                duration=duration,
                stacking="Same tier extends remaining time.",
                replacement="Different tier replaces it and discards remaining time.",
                unlock_requirement=f"Nursery: {spec.price:,} Garden Coins.",
            )
            if (
                plant is None
                or self.state.active_plant_id != plant.plant_id
                or not plant.planted
                or plant.fully_grown
            ):
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
                    target_name=getattr(plant, "name", ""),
                    status=PurchaseStatus.TARGET_INVALID,
                    message=f"This plant can’t use {spec.name}.",
                    state_signature={
                        "target_exists": plant is not None,
                        "active_plant_id": self.state.active_plant_id,
                    },
                )
            now = self._now_seconds()
            existing = plant.fertilizer
            current = existing if existing and existing.active(now) else None
            extending = bool(current is not None and current.tier == tier)
            replacing = bool(current is not None and current.tier != tier)
            status = PurchaseStatus.READY
            message = ""
            seconds_remaining = (
                max(0, int(math.ceil(float(current.expires_at) - now)))
                if current is not None
                else 0
            )
            current_spec = (
                self.FERTILIZERS.get(str(current.tier).lower())
                if current is not None
                else None
            )
            disposition = (
                PurchaseDisposition.EXTENDED
                if extending
                else PurchaseDisposition.REPLACED
                if replacing
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
                target_id=plant.plant_id,
                target_name=plant.name,
                status=status,
                message=message,
                replacement_required=replacing,
                current_item_name=(
                    str(getattr(current_spec, "name", current.tier))
                    if current is not None
                    else ""
                ),
                current_effect=(
                    f"+{int(current.growth_per_answer):,} Growth per card"
                    if current is not None
                    else ""
                ),
                current_duration=(
                    f"{self._duration_label(seconds_remaining)} remaining"
                    if current is not None
                    else ""
                ),
                current_seconds_remaining=seconds_remaining,
                duration_seconds=spec.duration_seconds,
                resulting_seconds_remaining=(
                    seconds_remaining + spec.duration_seconds
                    if extending
                    else spec.duration_seconds
                ),
                state_signature={
                    "plant_id": plant.plant_id,
                    "planted": plant.planted,
                    "fully_grown": plant.fully_grown,
                    "active_plant_id": self.state.active_plant_id,
                    "fertilizer": (
                        {
                            "tier": current.tier,
                            "growth": current.growth_per_answer,
                            "started_at": current.started_at,
                            "expires_at": current.expires_at,
                            "active": True,
                        }
                        if current is not None
                        else {
                            "tier": getattr(existing, "tier", None),
                            "started_at": getattr(existing, "started_at", None),
                            "expires_at": getattr(existing, "expires_at", None),
                            "active": False,
                        }
                    ),
                    "history_count": len(plant.fertilizer_history),
                },
            )

        if purchase_kind in {PurchaseKind.WEATHER, PurchaseKind.SCENERY}:
            environment_kind = purchase_kind.value
            item = environment_item(environment_kind, normalized_item)
            if item is None:
                return self._make_purchase_quote(
                    kind=purchase_kind,
                    item_id=normalized_item,
                    item_name="Weather or Scenery",
                    category="Weather" if purchase_kind is PurchaseKind.WEATHER else "Scenery",
                    artwork_category=(
                        "weather" if purchase_kind is PurchaseKind.WEATHER else "backgrounds"
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
                WEATHER_CATALOG.get(str(self.state.selected_weather))
                if item.kind == "weather"
                else SCENERY_CATALOG.get(str(self.state.selected_background))
            )
            return self._make_purchase_quote(
                kind=purchase_kind,
                item_id=item.item_id,
                item_name=item.name,
                category="Weather" if item.kind == "weather" else "Scenery",
                artwork_category="weather" if item.kind == "weather" else "backgrounds",
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
                        self.state.selected_weather == item.item_id
                        if item.kind == "weather"
                        else self.state.selected_background == item.item_id
                    ),
                },
            )

        current_index = int(self.state.unlocked_slots)
        current_item_id = f"bed_{current_index + 1}"
        price = self.BED_PRICES.get(current_index)
        descriptor = EffectDescriptor(
            function=f"Unlocks bed {current_index + 1} for one plant.",
            buff="Adds 1 planting space; no Growth effect.",
            activation_condition="Available after saving.",
            duration="Stays unlocked.",
            stacking="Beds unlock sequentially.",
            replacement="Replaces nothing and moves no plants.",
            unlock_requirement="Choose a starter; unlock earlier beds first.",
        )
        status = PurchaseStatus.READY
        message = ""
        if normalized_item not in {"", "next", current_item_id}:
            status = PurchaseStatus.STALE_TARGET
            message = "The next garden bed changed. Review the current bed before buying."
        elif not self.state.starter_selection_complete:
            status = PurchaseStatus.TARGET_INVALID
            message = "Choose a starter before unlocking another garden bed."
        elif price is None or current_index >= MAX_GARDEN_SLOTS:
            status = PurchaseStatus.ALREADY_OWNED
            message = "All six garden beds are already unlocked."
        return self._make_purchase_quote(
            kind=purchase_kind,
            item_id=current_item_id,
            item_name=f"Garden Bed {current_index + 1}",
            category="Garden bed",
            artwork_category="ui",
            artwork_key="garden_bed",
            unit_price=int(price or 0),
            disposition=PurchaseDisposition.UNLOCKED,
            descriptor=descriptor,
            status=status,
            message=message,
            state_signature={
                "unlocked_slots": current_index,
                "starter_complete": bool(self.state.starter_selection_complete),
            },
        )

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
                "This purchase request conflicts with an earlier completed purchase. Start again.",
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
                "This purchase request is invalid. Start again.",
                balance=self.state.currency_balance,
            )
        if not isinstance(request.request_id, str) or request.request_id != canonical_request_id:
            return self._purchase_failure(
                current,
                PurchaseStatus.REQUEST_ID_CONFLICT,
                "This purchase request is invalid. Start again.",
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
        if current.replacement_required and not request.authorize_replacement:
            return self._purchase_failure(
                current,
                PurchaseStatus.REPLACEMENT_REQUIRED,
                "Confirm that the active Fertilizer and its remaining time may be replaced.",
                balance=self.state.currency_balance,
            )

        snapshot = self._state_snapshot()
        event_key = f"purchase-request:{request.request_id}"
        try:
            outcome = self._apply_confirmed_purchase(current, event_key)
            if not outcome.success:
                self._restore_state(snapshot)
                return outcome
            self.state.completed_purchase_requests.append(CompletedPurchaseRequest(
                request_id=request.request_id,
                request_fingerprint=request_fingerprint,
                outcome=outcome,
                occurred_at=utc_now_iso(),
            ))
            self.state.completed_purchase_requests = (
                self.state.completed_purchase_requests[-MAX_COMPLETED_PURCHASE_REQUESTS:]
            )
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
                "The purchase could not be saved; no Garden Coins were spent. Try again.",
                balance=self.state.currency_balance,
            )

    def _apply_confirmed_purchase(
        self,
        quote: PurchaseQuote,
        event_key: str,
    ) -> PurchaseOutcome:
        presentation = purchase_presentation(quote, ignore_status=True)
        if not self._debit_currency(
            event_key,
            presentation.activity_label,
            quote.total_price,
        ):
            return self._purchase_failure(
                quote,
                PurchaseStatus.INSUFFICIENT_COINS,
                f"{quote.item_name} costs {quote.total_price:,} Garden Coins.",
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
                f"{plant.name} joined your plant collection.",
                plant.plant_id,
                title=f"{quote.item_name} purchased",
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
                title=f"{quote.item_name} purchased",
                asset_category="ui",
                asset_key=quote.item_id,
                amount=quote.quantity,
            )

        elif quote.kind in {PurchaseKind.WEATHER, PurchaseKind.SCENERY}:
            if quote.kind is PurchaseKind.WEATHER:
                self.state.inventory.setdefault("weather", []).append(quote.item_id)
            else:
                self.state.inventory.setdefault("scenery", []).append(quote.item_id)
            self._queue_feedback(
                event_key,
                "environment_purchase",
                f"{message} Open Collection when you want to preview or equip it.",
                title=f"{quote.item_name} unlocked",
                asset_category=quote.artwork_category,
                asset_key=quote.artwork_key,
                amount=1,
            )

        elif quote.kind is PurchaseKind.FERTILIZER:
            plant = self.plant_story(str(quote.target_id or ""))
            spec = self.FERTILIZERS[quote.item_id]
            if plant is None:
                return self._purchase_failure(
                    quote,
                    PurchaseStatus.TARGET_INVALID,
                    f"This plant can’t use {spec.name}.",
                    balance=self.state.currency_balance,
                )
            now = self._now_seconds()
            action = self._activate_fertilizer_effect(plant, spec, now=now)
            applied = True
            result_id = plant.plant_id
            self._queue_feedback(
                event_key,
                "fertilizer",
                message,
                plant.plant_id,
                title=f"{spec.name} {action}",
                asset_category="ui",
                asset_key=f"fertilizer_{spec.tier}",
                amount=1,
            )

        else:
            self.state.unlocked_slots += 1
            result_id = str(self.state.unlocked_slots - 1)
            self._queue_feedback(
                event_key,
                "unlock",
                message,
                title="Garden bed unlocked",
                asset_category="ui",
                asset_key="garden_bed",
                amount=1,
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
            applied=applied,
            equipped=equipped,
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
        try:
            purchase_kind = PurchaseKind(str(kind))
        except ValueError:
            return False, "Choose Weather or Scenery."
        if purchase_kind not in {PurchaseKind.WEATHER, PurchaseKind.SCENERY}:
            return False, "Choose Weather or Scenery."
        outcome = self._compat_purchase(purchase_kind, str(item_id))
        return outcome.success, outcome.message

    def equip_environment(self, kind: str, item_id: str) -> tuple[bool, str]:
        normalized_kind = str(kind)
        item = environment_item(normalized_kind, str(item_id))
        if item is None:
            return False, "That Weather or Scenery item is unavailable."
        if not self.owns_environment(normalized_kind, item.item_id):
            return False, f"Unlock {item.name} before equipping it."
        current = (
            self.state.selected_weather
            if normalized_kind == "weather"
            else self.state.selected_background
        )
        if current == item.item_id:
            return True, f"{item.name} is already equipped."
        snapshot = self._state_snapshot()
        if normalized_kind == "weather":
            self.state.selected_weather = item.item_id
        else:
            self.state.selected_background = item.item_id
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save changes. Your garden is unchanged."
        return True, f"{item.name} equipped."

    def set_environment_visibility(self, kind: str, enabled: bool) -> tuple[bool, str]:
        normalized_kind = str(kind)
        if normalized_kind not in {"weather", "scenery"}:
            return False, "Choose Weather or Scenery."
        snapshot = self._state_snapshot()
        self.state.environment_visibility[normalized_kind] = bool(enabled)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save changes. Your garden is unchanged."
        return True, "Garden appearance saved."

    def apply_environment_loadout(
        self,
        weather_id: str,
        scenery_id: str,
        visibility: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Compatibility wrapper for the Collection loadout transaction."""

        return self.apply_garden_loadout(
            weather_id,
            scenery_id,
            self.state.loadout.decoration_id,
            visibility,
        )

    def apply_garden_loadout(
        self,
        weather_id: str,
        scenery_id: str,
        decoration_id: str | None = None,
        visibility: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Validate and atomically persist the Collection loadout draft."""

        weather = environment_item("weather", str(weather_id))
        scenery = environment_item("scenery", str(scenery_id))
        if weather is None or scenery is None:
            return False, "That Weather or Scenery choice is unavailable."
        if not self.owns_environment("weather", weather.item_id):
            return False, f"Unlock {weather.name} before equipping it."
        if not self.owns_environment("scenery", scenery.item_id):
            return False, f"Unlock {scenery.name} before equipping it."
        normalized_decoration = None if decoration_id in (None, "", "none") else str(decoration_id)
        decorations = self.state.inventory.get("decorations", [])
        if normalized_decoration is not None and normalized_decoration not in decorations:
            return False, "Unlock that Decoration before equipping it."
        visual_layers = visibility if isinstance(visibility, dict) else {}
        snapshot = self._state_snapshot()
        self.state.selected_weather = weather.item_id
        self.state.selected_background = scenery.item_id
        self.state.loadout.decoration_id = normalized_decoration
        self.state.environment_visibility["weather"] = bool(
            visual_layers.get("weather", True)
        )
        self.state.environment_visibility["scenery"] = bool(
            visual_layers.get("scenery", True)
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save changes. Your garden is unchanged."
        return True, "Garden appearance saved."

    def purchase_growth_charge(self, charge_id: str) -> tuple[bool, str]:
        outcome = self._compat_purchase(
            PurchaseKind.GROWTH_CHARGE,
            str(charge_id),
        )
        return outcome.success, outcome.message

    @staticmethod
    def _growth_stage_for_points(points: int) -> str:
        stage = GROWTH_STAGES[0]
        for index, threshold in enumerate(GROWTH_THRESHOLDS):
            if int(points) >= threshold:
                stage = GROWTH_STAGES[index]
        return stage

    def quote_growth_charge(
        self,
        charge_id: str,
        plant_id: str,
    ) -> GrowthChargeQuote:
        """Return an immutable, non-mutating Growth Charge projection."""

        normalized_charge = str(charge_id)
        normalized_target = str(plant_id)
        spec = GROWTH_CHARGES.get(normalized_charge)
        plant = self.plant_story(normalized_target)
        inventory = max(
            0,
            int(self.state.consumables.get(normalized_charge, 0) or 0),
        )
        if plant is None or plant not in self.state.plants:
            target_state = GrowthChargeTargetState.UNAVAILABLE
        elif not plant.planted:
            target_state = GrowthChargeTargetState.STORED
        elif plant.fully_grown:
            target_state = GrowthChargeTargetState.FULLY_GROWN
        else:
            target_state = GrowthChargeTargetState.ELIGIBLE
        valid_target = target_state is GrowthChargeTargetState.ELIGIBLE
        current_growth = max(0, int(getattr(plant, "growth_points", 0) or 0))
        requested = max(0, int(getattr(spec, "growth", 0) or 0))
        granted = (
            min(requested, max(0, GROWTH_THRESHOLDS[-1] - current_growth))
            if valid_target and spec is not None
            else 0
        )
        projected = current_growth + granted
        stage_rewards = (
            self._project_stage_rewards(current_growth, projected)
            if valid_target
            else ()
        )
        rewards = tuple(item[2] for item in stage_rewards)
        completed_stages = tuple(item[1] for item in stage_rewards)
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
            "scenery": self.state.selected_background,
            "granted": granted,
            "rewards": [reward.to_dict() for reward in rewards],
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
            target_name=str(getattr(plant, "name", "Plant") or "Plant"),
            target_species=str(getattr(plant, "species", "") or ""),
            target_stage=self._growth_stage_for_points(current_growth),
            target_state=target_state,
            current_growth=current_growth,
            requested_growth=requested,
            granted_growth=granted,
            projected_growth=projected,
            projected_stage=self._growth_stage_for_points(projected),
            completed_stages=completed_stages,
            rewards=rewards,
            inventory_before=inventory,
            inventory_after=max(0, inventory - (1 if inventory else 0)),
            quote_token=quote_token,
            message=message,
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
            self.state.consumables[quote.charge_id] -= 1
            awarded = self._apply_direct_growth(
                plant,
                quote.granted_growth,
                stats_field="charge_growth",
                transition_source="charge",
            )
            if awarded != quote.granted_growth or plant is None:
                raise RuntimeError("Growth Charge projection changed during commit")
            outcome = GrowthChargeOutcome(
                status=GrowthChargeStatus.SUCCESS,
                charge_id=quote.charge_id,
                charge_name=quote.charge_name,
                target_id=quote.target_id,
                target_name=quote.target_name,
                previous_growth=quote.current_growth,
                resulting_growth=int(plant.growth_points),
                growth_granted=awarded,
                previous_stage=quote.target_stage,
                resulting_stage=plant.growth_stage,
                completed_stages=quote.completed_stages,
                rewards=quote.rewards,
                inventory_remaining=max(
                    0,
                    int(self.state.consumables.get(quote.charge_id, 0) or 0),
                ),
                message=(
                    f"{quote.charge_name} gave {quote.target_name} "
                    f"{awarded:,} Growth."
                ),
            )
            self._queue_feedback(
                f"growth-charge-use:{request.request_id}",
                "growth_charge",
                outcome.message,
                plant.plant_id,
                title=f"{quote.charge_name} used",
                asset_category="ui",
                asset_key=quote.charge_id,
                amount=awarded,
            )
            self.state.completed_growth_charge_requests.append(
                CompletedGrowthChargeRequest(
                    request_id=request.request_id,
                    request_fingerprint=request_fingerprint,
                    outcome=outcome,
                    occurred_at=utc_now_iso(),
                )
            )
            self.state.completed_growth_charge_requests = (
                self.state.completed_growth_charge_requests[
                    -MAX_COMPLETED_GROWTH_CHARGE_REQUESTS:
                ]
            )
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
                "The Growth Charge could not be saved, so it was not used.",
            )

    def use_growth_charge(
        self,
        charge_id: str,
        plant_id: str | None = None,
    ) -> tuple[bool, str]:
        target_id = str(plant_id or self.state.active_plant_id or "")
        quote = self.quote_growth_charge(str(charge_id), target_id)
        if not quote.ready:
            return False, quote.message
        outcome = self.confirm_growth_charge(GrowthChargeRequest.from_quote(quote))
        return outcome.success, outcome.message

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
        """Persist a Nursery choice without creating or placing a plant."""

        species = str(species).lower()
        progress = self.state.onboarding
        if self.state.plants or self.state.starter_selection_complete:
            return False, "Your starter plant has already been chosen."
        if progress.step not in {OnboardingStep.NURSERY, OnboardingStep.CONFIRMATION}:
            return False, "Open the Starter Nursery before choosing a plant."
        if species not in self.release_ready_species():
            return False, "That starter is not currently stocked in the Nursery."
        if (
            progress.step == OnboardingStep.CONFIRMATION
            and progress.pending_species == species
        ):
            return True, "Starter selected."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=OnboardingStep.CONFIRMATION,
            pending_species=species,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Starter selected."

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
            OnboardingStep.PLACEMENT: OnboardingStep.CONFIRMATION,
        }.get(progress.step)
        if previous is None:
            return False, "Back is not available on this setup step."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=previous,
            pending_species=(
                progress.pending_species
                if previous in {OnboardingStep.NURSERY, OnboardingStep.CONFIRMATION}
                else None
            ),
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed."
        return True, "Back."

    def _create_starter_at(self, species: str, slot: int) -> tuple[bool, str, Plant | None]:
        """Create, place, and advance a starter in one durable transaction."""

        species = str(species).lower()
        try:
            destination = int(slot)
        except (TypeError, ValueError):
            destination = -1
        if self.state.starter_selection_complete or self.state.plants:
            return False, "Your starter plant has already been chosen.", None
        if species not in self.release_ready_species():
            return False, "That starter is not currently stocked in the Nursery.", None
        if not 0 <= destination < min(MAX_GARDEN_SLOTS, int(self.state.unlocked_slots)):
            return False, "Choose an unlocked garden bed for your starter.", None

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
            f"{plant.name} is growing in Bed {destination + 1}.",
            plant.plant_id,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t save your garden. Nothing was changed.", None
        return True, f"{plant.name} is growing in Bed {destination + 1}.", plant

    def place_starter(self, slot: int) -> tuple[bool, str, Plant | None]:
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
                return True, "Your starter is already planted in that garden bed.", existing
        if progress.step != OnboardingStep.PLACEMENT or not progress.pending_species:
            return False, "Confirm a starter before choosing its garden bed.", None
        return self._create_starter_at(progress.pending_species, requested_slot)

    def choose_starter(self, species: str) -> tuple[bool, str, Plant | None]:
        """Compatibility path for callers predating explicit starter placement.

        New UI code uses select, confirm, and place. This wrapper remains atomic
        and selects the first unlocked bed so older integrations do not create
        a half-finished starter.
        """

        return self._create_starter_at(species, 0)

    def finish_onboarding(self) -> tuple[bool, str]:
        progress = self.state.onboarding
        if progress.step == OnboardingStep.DONE:
            return True, "Garden setup is complete."
        if progress.step != OnboardingStep.COMPLETION:
            return False, "Finish nurturing your starter before completing setup."
        snapshot = self._state_snapshot()
        self.state.onboarding = OnboardingProgress(
            step=OnboardingStep.DONE,
            starter_plant_id=progress.starter_plant_id,
        )
        self.state.garden_setup_version = 1
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Garden setup could not be completed because it was not saved."
        return True, "Garden setup is complete."

    def purchase_fertilizer(self, plant_id: str, tier: str, *, replace_active: bool = False) -> tuple[bool, str]:
        outcome = self._compat_purchase(
            PurchaseKind.FERTILIZER,
            str(tier).lower(),
            target_id=str(plant_id),
            authorize_replacement=bool(replace_active),
        )
        return outcome.success, outcome.message

    def use_fertilizer_item(
        self,
        plant_id: str | None = None,
        *,
        replace_active: bool = False,
    ) -> tuple[bool, str]:
        """Use one stored Rich Compost as the existing Basic Fertilizer effect."""

        plant = self.plant_story(str(plant_id or self.state.active_plant_id or ""))
        if (
            plant is None
            or self.state.active_plant_id != plant.plant_id
            or not plant.planted
            or plant.fully_grown
        ):
            return False, "Nurture an unfinished planted plant before using Basic Fertilizer."
        if self.state.consumables.get("fertilizer_basic", 0) <= 0:
            return False, "You do not have any Rich Compost yet."
        spec = self.FERTILIZERS["basic"]
        now = self._now_seconds()
        current = plant.fertilizer if plant.fertilizer and plant.fertilizer.active(now) else None
        if current is not None and current.tier != spec.tier and not replace_active:
            current_spec = self.FERTILIZERS.get(current.tier)
            current_name = current_spec.name if current_spec is not None else "active Fertilizer"
            return False, (
                f"Using Rich Compost will replace {current_name}. Confirm replacement first."
            )
        snapshot = self._state_snapshot()
        try:
            self.state.consumables["fertilizer_basic"] -= 1
            action = self._activate_fertilizer_effect(plant, spec, now=now)
            event_id = f"fertilizer-item:{uuid.uuid4().hex}"
            self._queue_feedback(
                event_id,
                "fertilizer",
                (
                    f"Basic Fertilizer {action} on {plant.name} for "
                    f"{self._duration_label(spec.duration_seconds)}."
                ),
                plant.plant_id,
                title=f"Basic Fertilizer {action}",
                asset_category="ui",
                asset_key="fertilizer_basic",
                amount=1,
                correlation_id=event_id,
            )
            self._persist_or_restore(snapshot)
        except Exception:
            self._restore_state(snapshot)
            return False, "Basic Fertilizer could not be used because it was not saved."
        return True, f"Basic Fertilizer {action} on {plant.name} for 1 hour."

    def use_basic_fertilizer(
        self,
        plant_id: str | None = None,
        *,
        replace_active: bool = False,
    ) -> tuple[bool, str]:
        return self.use_fertilizer_item(
            plant_id,
            replace_active=replace_active,
        )

    def use_booster_potion(self, plant_id: str | None = None) -> tuple[bool, str]:
        plant = self.plant_story(str(plant_id or self.state.active_plant_id or ""))
        if plant is None:
            return False, "Choose an unfinished plant to nurture before using a Booster Potion."
        if self.state.active_plant_id != plant.plant_id or not plant.planted or plant.fully_grown:
            return False, "Nurture this unfinished planted plant before using a Booster Potion."
        if self.state.consumables.get("booster_potion", 0) <= 0:
            return False, "You do not have a Booster Potion yet. Rare study gifts can contain one."
        now = self._now_seconds()
        current = plant.booster if plant.booster and plant.booster.active(now) else None
        archived = None if current is not None else self._historical_booster_period(
            plant.booster,
            ended_at=now,
        )
        history_identities = {
            self._booster_period_identity(period) for period in plant.booster_history
        }
        needs_archive = (
            archived is not None
            and self._booster_period_identity(archived) not in history_identities
        )
        snapshot = self._state_snapshot()
        self.state.consumables["booster_potion"] -= 1
        if needs_archive and archived is not None:
            plant.booster_history.append(archived)
            plant.booster_history.sort(key=lambda period: (
                float(period.started_at if period.started_at is not None else period.expires_at),
                float(period.expires_at),
            ))
        expiration_base = current.expires_at if current is not None else now
        activation_start = (
            current.started_at
            if current is not None and current.started_at is not None
            else now
        )
        duration_bonus_percent = 0
        if self.state.selected_weather == "snow_flurry":
            duration_bonus_percent += 10
        if self.state.selected_background == "full_moon":
            duration_bonus_percent += 25
        duration_seconds = (
            self.BOOSTER_DURATION_SECONDS * (100 + duration_bonus_percent) // 100
        )
        plant.booster = Booster(
            self.BOOSTER_GROWTH_PER_ANSWER,
            expiration_base + duration_seconds,
            activation_start,
        )
        duration_minutes = duration_seconds // 60
        hours, minutes = divmod(duration_minutes, 60)
        duration_text = (
            f"{hours} {'hour' if hours == 1 else 'hours'}"
            + (f" {minutes} minutes" if minutes else "")
        )
        event_key = f"booster:{plant.plant_id}:{uuid.uuid4().hex}"
        action = "extended" if current is not None else "active"
        self._queue_feedback(
            event_key,
            "booster",
            (
                f"Booster Potion {action} on {plant.name}: "
                f"+{self.BOOSTER_GROWTH_PER_ANSWER} Growth per Anki card answer for {duration_text}."
            ),
            plant.plant_id,
            title="Booster Potion active",
            asset_category="ui",
            asset_key="booster_potion",
            amount=1,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The Booster Potion could not be applied; it remains in your collection."
        return True, (
            f"Booster Potion {action}: +{self.BOOSTER_GROWTH_PER_ANSWER} Growth "
            f"per answer for {duration_text}."
        )

    def purchase_species(self, species: str) -> tuple[bool, str, Plant | None]:
        outcome = self._compat_purchase(
            PurchaseKind.SPECIES,
            str(species).lower(),
        )
        plant = self.plant_story(outcome.result_id) if outcome.success else None
        return outcome.success, outcome.message, plant

    def next_bed_price(self) -> int | None:
        return self.BED_PRICES.get(int(self.state.unlocked_slots))

    def purchase_next_bed(self) -> tuple[bool, str]:
        outcome = self._compat_purchase(PurchaseKind.BED, "next")
        return outcome.success, outcome.message

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
            return False, "Choose an empty garden bed."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if destination not in available:
            return False, "Choose an empty garden bed."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Couldn’t place the plant. Your garden is unchanged."
        return True, f"{plant.name} was placed in Bed {destination + 1}."

    def move_plant(self, plant_id: str, slot_index: int) -> tuple[bool, str]:
        """Atomically move a planted Collection item to an empty garden bed."""

        plant = self.plant_story(plant_id)
        if plant is None or not plant.planted:
            return False, "That plant is not currently planted."
        try:
            destination = int(slot_index)
        except (TypeError, ValueError):
            return False, "Choose an empty garden bed."
        occupied = {
            item.slot_index for item in self.state.plants
            if item.plant_id != plant.plant_id and item.slot_index is not None
        }
        if (
            destination < 0
            or destination >= self.state.unlocked_slots
            or destination in occupied
        ):
            return False, "Choose an empty garden bed."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if plant.slot_index == destination:
            return True, f"{plant.name} is already in Bed {destination + 1}."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The move could not be saved; the previous bed was restored."
        return True, f"{plant.name} moved to Bed {destination + 1}."

    def move_to_collection(self, plant_id: str) -> tuple[bool, str]:
        plant = self.plant_story(plant_id)
        if plant is None or not plant.planted:
            return False, "That plant is not currently planted."
        if self.state.active_plant_id == plant.plant_id:
            return False, "Nurture another unfinished planted plant before moving this one to the collection."
        snapshot = self._state_snapshot()
        plant.slot_index = None
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The collection change could not be saved."
        return True, f"{plant.name} moved to the collection without losing progress."

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

    def _record_active_period(self, plant_id: str | None) -> None:
        day = self.state.daily_stats.day
        latest = max(
            self.state.active_plant_periods,
            key=lambda period: (period.started_at_ms, period.day),
            default=None,
        )
        if latest is None or latest.plant_id != plant_id:
            activated_at = self._now_ms()
            self.state.active_plant_periods.append(ActivePlantPeriod(
                day, plant_id, activated_at
            ))
            self._activate_progression_if_ready(activated_at)

    def active_plant(self) -> Plant | None:
        return self._repair_active_plant()

    def set_active_plant(self, plant_id: Optional[str]) -> tuple[bool, str]:
        plant = self.plant_story(str(plant_id or ""))
        if plant is None:
            return False, "That plant is no longer in your collection."
        if not plant.planted:
            return False, "Place this plant in a garden bed before nurturing it."
        if plant.fully_grown:
            return False, "This plant is fully grown. Choose an unfinished plant to nurture instead."
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
                    return False, "The plant you chose to nurture could not be saved."
            return True, f"{plant.name} is already being nurtured and receives Growth from future card answers."
        snapshot = self._state_snapshot()
        self.state.active_plant_id = plant.plant_id
        self._record_active_period(plant.plant_id)
        self._add_memory(plant, "nurture:first", "first_nurture")
        if (
            progress.step == OnboardingStep.NURTURE
            and progress.starter_plant_id == plant.plant_id
        ):
            self.state.onboarding = OnboardingProgress(
                step=OnboardingStep.COMPLETION,
                starter_plant_id=plant.plant_id,
            )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The plant you chose to nurture could not be saved."
        return True, f"You are now nurturing {plant.name}. It receives Growth from future card answers."

    def rename_plant(self, plant_id: str, name: str) -> tuple[bool, str]:
        plant = self.plant_story(plant_id)
        if plant is None:
            return False, "That plant is no longer in your collection."
        clean = " ".join(str(name).split())
        if not clean:
            return False, "Enter a name for this plant."
        if len(clean) > MAX_PLANT_NAME_LENGTH:
            return False, f"Plant names can be at most {MAX_PLANT_NAME_LENGTH} characters."
        snapshot = self._state_snapshot()
        plant.name = clean
        plant.name_customized = True
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The new name could not be saved."
        return True, f"This plant is now named {clean}."

    def rename_garden(self, name: str, *, complete_setup: bool = True) -> tuple[bool, str]:
        clean = " ".join(str(name).split())
        if not clean:
            return False, "Enter a name for your garden."
        if len(clean) > MAX_GARDEN_NAME_LENGTH:
            return False, f"Garden names can be at most {MAX_GARDEN_NAME_LENGTH} characters."
        snapshot = self._state_snapshot()
        self.state.garden_name = clean
        if complete_setup:
            self.state.garden_setup_version = 1
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The garden name could not be saved."
        return True, f"Your garden is now named {clean}."

    def development_populate(self) -> tuple[bool, str]:
        """Populate a broad UI test state without touching the revlog ledger."""

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
        self.state.inventory["weather"] = list(WEATHER_CATALOG)
        self.state.inventory["scenery"] = list(SCENERY_CATALOG)
        self.state.environment_visibility = {"weather": True, "scenery": True}
        now = utc_now_iso()
        for achievement in self.state.achievements.values():
            achievement.unlocked = True
            achievement.unlocked_at = achievement.unlocked_at or now
            achievement.progress = 1.0
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
        return True, "Development garden populated with 100,000 Coins, all plants, spaces, and items."

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
            return False, "That planted plant is no longer in your garden.", None
        try:
            destination = int(destination_slot)
        except (TypeError, ValueError):
            return False, "Choose a garden bed.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That garden bed is still locked.", None
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
            return False, "The new arrangement could not be saved.", None
        return True, "Plants moved.", PlacementChange(before, after)

    def begin_placement_draft(self, plant_id: str) -> tuple[bool, str, PlacementDraft | None]:
        plants = self._planted()
        slots = {plant.plant_id: int(plant.slot_index or 0) for plant in plants}
        if str(plant_id) not in slots:
            return False, "That planted plant is no longer in your garden.", None
        return True, "Arrangement ready.", PlacementDraft(str(plant_id), slots, dict(slots), [])

    def stage_placement(self, draft: PlacementDraft, destination_slot: int) -> tuple[bool, str, PlacementChange | None]:
        if not isinstance(draft, PlacementDraft) or draft.selected_plant_id not in draft.current:
            return False, "That move session is no longer available.", None
        try:
            destination = int(destination_slot)
        except (TypeError, ValueError):
            return False, "Choose a garden bed.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That garden bed is still locked.", None
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

    def commit_placement_draft(self, draft: PlacementDraft) -> tuple[bool, str, PlacementChange | None]:
        if not isinstance(draft, PlacementDraft) or not draft.original:
            return False, "That move session is no longer available.", None
        plants = {plant.plant_id: plant for plant in self._planted()}
        live = {pid: int(plant.slot_index or 0) for pid, plant in plants.items()}
        if live != draft.original:
            return False, "The garden changed while you were moving plants. No arrangement was saved.", None
        if set(draft.current) != set(draft.original) or len(set(draft.current.values())) != len(draft.current):
            return False, "The pending arrangement is not valid.", None
        if any(slot < 0 or slot >= self.state.unlocked_slots for slot in draft.current.values()):
            return False, "The pending arrangement includes a locked garden bed.", None
        surface_error = self._arrangement_error(draft.current)
        if surface_error:
            return False, surface_error, None
        if draft.current == draft.original:
            return True, "The arrangement is unchanged.", PlacementChange(dict(draft.original), dict(draft.current))
        snapshot = self._state_snapshot()
        for plant_id, slot in draft.current.items():
            plants[plant_id].slot_index = slot
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The new arrangement could not be saved.", None
        return True, "Plant arrangement saved.", PlacementChange(dict(draft.original), dict(draft.current))

    def restore_placement(self, change: PlacementChange) -> tuple[bool, str, PlacementChange | None]:
        plants = {plant.plant_id: plant for plant in self._planted()}
        if not change.before or any(pid not in plants for pid in change.before):
            return False, "That move can no longer be undone.", None
        current = {pid: int(plants[pid].slot_index or 0) for pid in change.before}
        if current != change.after:
            return False, "The garden changed after that move, so it cannot be undone.", None
        surface_error = self._arrangement_error(change.before)
        if surface_error:
            return False, "That previous arrangement is no longer valid for these planting surfaces.", None
        snapshot = self._state_snapshot()
        for pid, slot in change.before.items():
            plants[pid].slot_index = slot
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The previous arrangement could not be restored.", None
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
            plant_name = item.plant_name or item.species.replace("_", " ").title()
            return f"{plant_name} reached {item.new_stage.title()}!"
        names = ", ".join(
            item.plant_name or item.species.replace("_", " ").title()
            for item in transitions[:3]
        )
        if len(transitions) > 3:
            names += f" and {len(transitions) - 3} more"
        return f"Garden milestone! {names} reached new growth stages."

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
        for definition in ACHIEVEMENT_DEFINITIONS:
            achievement = self.state.achievements[definition.achievement_id]
            if achievement.unlocked:
                achievement.progress = 1.0
                continue
            metric = definition.progress_metric.value
            current = (
                streak_days
                if metric == "streak_days"
                else current_day_answers
                if metric == "daily_answers"
                else lifetime_answers
                if metric == "lifetime_answers"
                else non_again_run
                if metric == "consecutive_non_again"
                else 0
            )
            achievement.progress = min(
                1.0,
                max(0.0, current / max(1, definition.progress_target)),
            )

    def _update_achievements(self, *, correlation_id: str = "") -> None:
        """Unlock only criteria that cannot be invalidated later in the day."""

        checks = {
            "streak_7": self.state.streak_days >= 7,
            "streak_30": self.state.streak_days >= 30,
            "streak_100": self.state.streak_days >= 100,
            "streak_365": self.state.streak_days >= 365,
            "reviews_100_day": self.state.daily_stats.reviewed >= 100,
            "reviews_1000_total": self.state.lifetime_eligible_answers >= 1_000,
            "retention_100": self.state.current_non_again_run >= 30,
        }
        day_value = self.state.daily_stats.day
        for achievement_id, achieved in checks.items():
            if achieved:
                self._unlock_achievement(
                    achievement_id,
                    completion_day=day_value,
                    correlation_id=correlation_id or f"achievement:{achievement_id}",
                )
        self._refresh_achievement_progress()

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
        """Finalize the two closed-day recall achievements idempotently."""

        try:
            date.fromisoformat(str(scheduler_day))
        except (TypeError, ValueError):
            return ()
        total = max(0, int(answered))
        non_again = max(0, min(total, int(successful)))
        again_count = max(0, min(total, int(again)))
        unlocked: list[str] = []
        if total >= 20 and non_again * 10 >= total * 9:
            if self._unlock_achievement(
                "retention_90",
                completion_day=scheduler_day,
                correlation_id=correlation_id,
            ):
                unlocked.append("retention_90")
        if total >= 40 and again_count == 0:
            if self._unlock_achievement(
                "no_lapse",
                completion_day=scheduler_day,
                correlation_id=correlation_id,
            ):
                unlocked.append("no_lapse")
        self._record_finalized_day(scheduler_day, fingerprint)
        self._refresh_achievement_progress()
        return tuple(unlocked)

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
                    "name": plant.name,
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
        """Resolve Nursery item artwork from the bundled asset manifest."""

        return self.assets.resolve_ui_asset(item_key, quality_preference="balanced")

    def resolve_nurtured_marker_asset(self) -> Optional[ResolvedAsset]:
        """Resolve the watering-can marker shared by Garden scene previews."""

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
        """Return both inward-facing marker orientations for scene renderers."""

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
        visibility = getattr(state, "environment_visibility", {})
        selected_scenery = getattr(state, "selected_background", DEFAULT_SCENERY_ID)
        scenery = (
            selected_scenery
            if not isinstance(visibility, dict) or visibility.get("scenery", True)
            else DEFAULT_SCENERY_ID
        )
        normalized_theme = self.assets.normalize_theme(theme)
        background = self.assets.resolve(
            "backgrounds",
            f"bg_{scenery}_any",
            f"slot:backgrounds:{scenery}:any",
            theme=normalized_theme,
            time_of_day="any",
            quality_preference="balanced",
        )
        weather_overlay = (
            self.assets.resolve(
                "weather",
                f"weather_{weather}",
                f"slot:weather:{weather}",
                theme=normalized_theme,
                quality_preference="balanced",
            )
            if not isinstance(visibility, dict) or visibility.get("weather", True)
            else None
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
            "weather": weather_overlay.to_payload() if weather_overlay else None,
            "plant": plants.get("rose"),
            "plants": plants,
        }

    def resolve_background_image(self) -> Optional[str]:
        asset = self.resolve_background_asset()
        return str(asset.path) if asset else None

    def resolve_background_asset(self) -> Optional[ResolvedAsset]:
        scenery = (
            self.state.selected_background
            if self.state.environment_visibility.get("scenery", True)
            else DEFAULT_SCENERY_ID
        )
        return self.assets.resolve(
            "backgrounds",
            f"bg_{scenery}_any",
            f"slot:backgrounds:{scenery}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            time_of_day="any",
        )

    def resolve_weather_overlay(self) -> Optional[str]:
        asset = self.resolve_weather_asset()
        return str(asset.path) if asset else None

    def resolve_weather_asset(self) -> Optional[ResolvedAsset]:
        if not self.state.environment_visibility.get("weather", True):
            return None
        return self.assets.resolve(
            "weather",
            f"weather_{self.state.selected_weather}",
            f"slot:weather:{self.state.selected_weather}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            quality_preference="balanced",
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

    def resolve_weather_preview_asset(self, item_id: str) -> Optional[ResolvedAsset]:
        weather = str(item_id)
        if weather not in WEATHER_CATALOG:
            return None
        return self.assets.resolve(
            "weather",
            f"weather_{weather}",
            f"slot:weather:{weather}:preview",
            theme=self.config.value("visual_theme", "verdant_twilight"),
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

    def resolve_decoration_image(self, decoration: str) -> Optional[str]:
        asset = self.resolve_decoration_asset(decoration)
        return str(asset.path) if asset else None

    def resolve_decoration_asset(self, decoration: str) -> Optional[ResolvedAsset]:
        if not decoration or decoration == "none":
            return None
        return self.assets.resolve(
            "decorations",
            f"decor_{decoration}",
            f"slot:decorations:{decoration}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
        )

    def reroll_asset_slot(self, slot: str) -> Optional[str]:
        if slot == "background":
            scenery = self.state.selected_background
            path = self.assets.get_or_fetch(
                "backgrounds", f"bg_{scenery}_any", f"slot:backgrounds:{scenery}",
                theme=self.config.value("visual_theme", "verdant_twilight"), reroll=True,
            )
            return str(path) if path else None
        if slot == "weather":
            path = self.assets.get_or_fetch(
                "weather", f"weather_{self.state.selected_weather}",
                f"slot:weather:{self.state.selected_weather}",
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
