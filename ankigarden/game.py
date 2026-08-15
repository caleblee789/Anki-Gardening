from __future__ import annotations

import json
import hashlib
import math
import random
import time
import uuid
from bisect import bisect_left, insort
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from . import build_capabilities
from .asset_manager import AssetManager, ResolvedAsset
from .environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    DROP_BANDS,
    DROP_TIER_ITEMS,
    ENVIRONMENT_CATALOG,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    catalog_items,
    environment_item,
    ultra_denominator,
)
from .models.state import (
    Achievement,
    ActivePlantPeriod,
    CurrencyTransaction,
    DailyStats,
    FeedbackEvent,
    Fertilizer,
    Booster,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    CURRENT_CATALOG_SPECIES_ORDER,
    MAX_FERTILIZER_HISTORY,
    MAX_BOOSTER_HISTORY,
    MAX_GARDEN_SLOTS,
    MAX_GARDEN_NAME_LENGTH,
    MAX_PLANT_NAME_LENGTH,
    MAX_PROCESSED_REVLOG_IDS,
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
    PlantMemory,
    RewardDrop,
    STREAK_BONUS_TIERS,
    utc_now_iso,
)
from .storage import DueObligationStatus, RevlogReadError, SchedulerBoundaryError


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

    def to_dict(self) -> dict[str, str]:
        return {
            "plant_id": self.plant_id,
            "species": self.species,
            "previous_stage": self.previous_stage,
            "new_stage": self.new_stage,
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
    STREAK_MEMORY_MILESTONES = (3, 7, 14, 30, 60, 100, 365)
    STREAK_CURRENCY = {7: 25, 14: 50, 30: 100, 100: 300}
    STAGE_CURRENCY = {"sprout": 5, "young": 10, "mature": 20, "flowering": 35, "rare": 50}
    COIN_DROP_CHANCE = 800
    COIN_DROP_AMOUNT = 50
    BOOSTER_DROP_CHANCE = 5_000
    BOOSTER_GROWTH_PER_ANSWER = 5
    BOOSTER_DURATION_SECONDS = 2 * 60 * 60
    ALL_DUE_BASE_COINS = 10
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
    SOIL_PLANT_MESSAGE = "Choose an empty unlocked garden space."
    SOIL_CAPACITY_MESSAGE = "Unlock or empty a garden space before planting this plant."
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
        self._pending_stage_transitions: list[StageTransition] = []
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
        try:
            self.rollover_if_needed(persist=False)
        except SchedulerBoundaryError:
            # Add-ons can be imported before Anki has finished attaching the
            # collection scheduler. Preserve the saved scheduler day and let
            # the app's maintenance boundary retry after collection startup.
            pass
        if self.state.to_dict() != snapshot:
            self._persist_or_restore(snapshot)

    def _state_snapshot(self) -> dict[str, Any]:
        return deepcopy(self.state.to_dict())

    def _restore_state(self, snapshot: dict[str, Any]) -> None:
        restored = GardenState.from_dict(snapshot)
        self.state.__dict__.clear()
        self.state.__dict__.update(restored.__dict__)
        self.storage.state = self.state

    def _persist_or_restore(self, snapshot: dict[str, Any]) -> None:
        try:
            self.storage.save()
        except Exception:
            self._restore_state(snapshot)
            raise

    def _repair_environment_state(self) -> None:
        """Normalize compatibility fields without revoking valid entitlements."""

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
                inventory.get("backgrounds", [])
                if isinstance(inventory.get("backgrounds"), list)
                else []
            ),
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
        inventory["backgrounds"] = list(valid_scenery)
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
        equipped = self.state.equipped if isinstance(self.state.equipped, dict) else {}
        equipped["weather"] = self.state.selected_weather
        equipped["background"] = self.state.selected_background
        self.state.equipped = equipped
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
        for item_id in ("booster_potion", *GROWTH_CHARGES):
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
                message = f"{plant.name} was moved to an open garden space."
            else:
                message = (
                    f"{plant.name} was returned to the collection because no garden space was open."
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

    def rollover_if_needed(self, *, persist: bool = True) -> None:
        today = self._scheduler_day()
        if self.state.daily_stats.day == today:
            return
        scheduler_day_floor = self._scheduler_day_floor()
        snapshot = self._state_snapshot()
        previous = self.state.daily_stats
        try:
            previous_day = date.fromisoformat(previous.day)
            current_day = date.fromisoformat(today)
        except ValueError:
            previous_day = current_day = date.today()
        self.state.daily_stats = DailyStats(day=today)
        self.state.processed_revlog_floor = scheduler_day_floor
        self.state.processed_revlog_ids = []
        # Reviews outside the current scheduler day are no longer eligible for
        # catch-up, so their completed Fertilizer windows can be pruned without
        # losing answer-time attribution. Keep any interval that overlaps the
        # new day because a late synced answer may still fall inside it.
        scheduler_day_start = (scheduler_day_floor + 1) / 1000.0
        for plant in self.state.plants:
            plant.fertilizer_history = [
                period for period in plant.fertilizer_history
                if float(period.expires_at) > scheduler_day_start
            ][-MAX_FERTILIZER_HISTORY:]
            if (
                plant.fertilizer is not None
                and float(plant.fertilizer.expires_at) <= scheduler_day_start
            ):
                plant.fertilizer = None
            plant.booster_history = [
                period for period in plant.booster_history
                if float(period.expires_at) > scheduler_day_start
            ][-MAX_BOOSTER_HISTORY:]
            if (
                plant.booster is not None
                and float(plant.booster.expires_at) <= scheduler_day_start
            ):
                plant.booster = None
        self.state.active_plant_periods = [
            period for period in self.state.active_plant_periods if period.day >= (current_day - timedelta(days=7)).isoformat()
        ]
        self.state.active_plant_periods.append(ActivePlantPeriod(today, self.state.active_plant_id, self._now_ms()))
        if persist:
            self._persist_or_restore(snapshot)

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

    def reconcile_retrospective_streak(self, *, persist: bool = True) -> tuple[bool, str]:
        """Reconcile streak display/rewards without replaying historic Growth.

        A collection or scheduler read failure is deliberately non-destructive:
        the saved streak remains active and the next maintenance boundary can
        retry. Existing milestone transaction keys make backfilled Coins
        idempotent across restarts and sync reconciliation.
        """

        resolver = getattr(self.storage, "retrospective_streak", None)
        if not callable(resolver):
            return False, "Anki review history is not available yet."
        try:
            streak = resolver()
        except (RevlogReadError, SchedulerBoundaryError):
            return False, "Anki review history is not available yet."
        snapshot = self._state_snapshot()
        previous_days = int(self.state.streak_days)
        self.state.streak_days = max(0, int(getattr(streak, "days", 0)))
        latest_day = str(getattr(streak, "latest_day", "") or "")
        if latest_day:
            self.state.last_active_day = latest_day
        credited_total = 0
        newly_claimed: list[int] = []
        for threshold, reward in sorted(self.STREAK_CURRENCY.items()):
            if (
                self.state.streak_days >= threshold
                and threshold not in self.state.claimed_streak_rewards
            ):
                if self._credit_currency(
                    f"streak:{threshold}",
                    f"{threshold}-day Anki streak",
                    reward,
                ):
                    credited_total += reward
                # A legacy transaction may already hold this event key; the
                # claim still needs to be repaired to prevent repeated checks.
                self.state.claimed_streak_rewards.append(threshold)
                newly_claimed.append(threshold)
        self.state.claimed_streak_rewards = sorted(set(self.state.claimed_streak_rewards))
        if credited_total:
            milestone_copy = ", ".join(f"{value}-day" for value in newly_claimed)
            self._queue_feedback(
                f"streak-backfill:{':'.join(str(value) for value in newly_claimed)}",
                "streak",
                (
                    f"Your review history restored a {self.state.streak_days}-day Anki streak "
                    f"and {credited_total} Garden Coins from the {milestone_copy} milestones."
                ),
                title="Streak rewards restored",
                asset_category="ui",
                asset_key="streak_reward",
                amount=credited_total,
            )
        self._update_achievements()
        if self.state.to_dict() == snapshot:
            return True, "Your Anki streak is up to date."
        if persist:
            try:
                self._persist_or_restore(snapshot)
            except Exception:
                return False, "The updated Anki streak could not be saved."
        direction = "restored" if self.state.streak_days >= previous_days else "updated"
        return True, f"Your {self.state.streak_days}-day Anki streak was {direction}."

    def register_review(self, review_payload: Dict[str, Any]) -> ReviewAward:
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.rollover_if_needed(persist=False)
        try:
            award = self._register_review_in_memory(review_payload)
            self._update_achievements()
            self._persist_or_restore(snapshot)
            return award
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            raise

    def _register_review_in_memory(self, payload: Any) -> ReviewAward:
        source = payload if isinstance(payload, dict) else {}
        try:
            revlog_id = max(0, int(source.get("revlog_id", 0)))
        except (TypeError, ValueError):
            revlog_id = 0
        if revlog_id:
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
        try:
            event_ms = max(0, int(source.get("answered_at_ms", revlog_id or self._now_ms())))
        except (TypeError, ValueError):
            event_ms = self._now_ms()
        queue, ease, _deck_id, _difficulty, lapse_count = self._normalized_review(source)
        stats = self.state.daily_stats
        first_review_today = stats.reviewed == 0
        previous_streak = self.state.streak_days
        previous_reviews = self.state.total_reviews
        if first_review_today:
            self._start_study_day()
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
        plant = self._active_plant_at(event_ms)
        award = self._award_review_growth(plant, event_ms)
        # Attribute milestones crossed by this answer to the plant that
        # received it. Reaching Rare clears the nurtured-plant pointer, so
        # looking it up again here would otherwise lose same-answer memories.
        self._record_shared_memories(previous_reviews, previous_streak, plant=plant)
        if revlog_id and self.state.starter_selection_complete:
            self._maybe_award_random_drop(revlog_id, plant)
        if revlog_id:
            insort(self.state.processed_revlog_ids, revlog_id)
            self.state.last_processed_revlog_id = max(self.state.last_processed_revlog_id, revlog_id)
        return award

    def _start_study_day(self) -> None:
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
        for threshold, reward in self.STREAK_CURRENCY.items():
            if self.state.streak_days >= threshold and threshold not in self.state.claimed_streak_rewards:
                credited = self._credit_currency(
                    f"streak:{threshold}",
                    f"{threshold}-day Anki streak",
                    reward,
                    feedback=(
                        f"Your {threshold}-day Anki streak earned "
                        f"{reward} Garden Coins."
                    ),
                )
                if credited:
                    self.state.claimed_streak_rewards.append(threshold)

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
        day = self.state.daily_stats.day
        periods = [period for period in self.state.active_plant_periods if period.day == day and period.started_at_ms <= event_ms]
        plant_id = periods[-1].plant_id if periods else self.state.active_plant_id
        plant = next((item for item in self.state.plants if item.plant_id == plant_id), None)
        return plant if plant is not None and not plant.fully_grown else None

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

    def _award_review_growth(self, plant: Plant | None, event_ms: int) -> ReviewAward:
        if plant is None:
            return ReviewAward(None, 0, 0, 0, 0, "Choose an unfinished plant to nurture to resume Growth.")
        bonus_percent = self.current_streak_bonus_percent()
        bonus_numerator = plant.bonus_remainder + (self.BASE_GROWTH_PER_REVIEW * bonus_percent)
        proposed_streak_bonus, next_remainder = divmod(bonus_numerator, 100)
        proposed_fertilizer_bonus = self.fertilizer_growth(plant, now=event_ms / 1000)
        proposed_booster_bonus = self.booster_growth(plant, now=event_ms / 1000)
        answer_number = max(1, int(self.state.daily_stats.reviewed))
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
            return ReviewAward(plant.plant_id, 0, 0, 0, bonus_percent, "This plant is fully grown.")
        before = plant.growth_points
        plant.growth_points += total
        plant.bonus_remainder = next_remainder if plant.growth_points < GROWTH_THRESHOLDS[-1] else 0
        stats = self.state.daily_stats
        stats.base_growth += base
        stats.streak_bonus_growth += streak_bonus
        stats.fertilizer_growth += fertilizer_bonus
        stats.booster_growth += booster_bonus
        stats.weather_growth += weather_bonus
        stats.scenery_growth += scenery_bonus
        stats.bonus_growth = (
            stats.streak_bonus_growth
            + stats.fertilizer_growth
            + stats.booster_growth
            + stats.weather_growth
            + stats.scenery_growth
            + stats.charge_growth
        )
        stats.growth_earned = stats.base_growth + stats.bonus_growth
        stats.plant_growth[plant.plant_id] = (
            stats.plant_growth.get(plant.plant_id, 0)
            + total
        )
        self._record_growth_crossings(plant, before, plant.growth_points)
        return ReviewAward(
            plant.plant_id,
            base,
            streak_bonus,
            fertilizer_bonus,
            bonus_percent,
            booster_growth=booster_bonus,
            weather_growth=weather_bonus,
            scenery_growth=scenery_bonus,
        )

    def _reward_digest(self, revlog_id: int, *, namespace: bytes) -> bytes:
        return hashlib.blake2b(
            f"{self.state.reward_seed}:{int(revlog_id)}".encode("utf-8"),
            digest_size=32,
            person=namespace[:16],
        ).digest()

    def _record_reward_drop(self, revlog_id: int, kind: str, amount: int) -> None:
        self.state.reward_drop_history.append(RewardDrop(
            int(revlog_id), self.state.daily_stats.day, str(kind), int(amount), utc_now_iso()
        ))
        self.state.reward_drop_history = self.state.reward_drop_history[-500:]

    def _drop_hit(self, revlog_id: int, tier: str, denominator: int) -> bool:
        digest = self._reward_digest(
            revlog_id,
            namespace=f"drop-v2:{tier}".encode("utf-8"),
        )
        return int.from_bytes(digest[:8], "big") % max(1, int(denominator)) == 0

    def _drop_choice_index(self, revlog_id: int, tier: str, size: int) -> int:
        if size <= 1:
            return 0
        digest = self._reward_digest(
            revlog_id,
            namespace=f"choice:{tier}".encode("utf-8"),
        )
        return int.from_bytes(digest[8:16], "big") % int(size)

    def _grant_consumable_drop(
        self,
        revlog_id: int,
        consumable_id: str,
        *,
        plant: Plant | None,
        title: str,
        message: str,
        event_prefix: str = "drop",
    ) -> None:
        self.state.consumables[consumable_id] = (
            self.state.consumables.get(consumable_id, 0) + 1
        )
        self._queue_feedback(
            f"{event_prefix}:{consumable_id}:{revlog_id}",
            "charge_drop" if consumable_id in GROWTH_CHARGES else "booster_drop",
            message,
            plant.plant_id if plant is not None else None,
            title=title,
            asset_category="ui",
            asset_key=consumable_id,
            amount=1,
        )
        self._record_reward_drop(revlog_id, consumable_id, 1)

    def _grant_environment_drop(
        self,
        revlog_id: int,
        item: CatalogItem,
        *,
        plant: Plant | None,
    ) -> None:
        if item.kind == "weather":
            owned = self.state.inventory.setdefault("weather", [])
        else:
            owned = self.state.inventory.setdefault("scenery", [])
        if item.item_id not in owned:
            owned.append(item.item_id)
        if item.kind == "scenery":
            backgrounds = self.state.inventory.setdefault("backgrounds", [])
            if item.item_id not in backgrounds:
                backgrounds.append(item.item_id)
        self._queue_feedback(
            f"drop:environment:{item.item_id}:{revlog_id}",
            "environment_drop",
            (
                f"You found {item.name}. It is now in Garden Progress → Weather and Scenery, "
                f"ready to equip. {item.effect}"
            ),
            plant.plant_id if plant is not None else None,
            title=f"{item.rarity} garden discovery",
            asset_category="weather" if item.kind == "weather" else "backgrounds",
            asset_key=item.item_id,
            amount=1,
        )
        self._record_reward_drop(revlog_id, item.item_id, 1)

    def _grant_environment_tier(
        self,
        revlog_id: int,
        tier: str,
        *,
        plant: Plant | None,
    ) -> None:
        candidates = [
            item for item in DROP_TIER_ITEMS.get(tier, ())
            if not self.owns_environment(item.kind, item.item_id)
        ]
        if candidates:
            item = candidates[self._drop_choice_index(revlog_id, tier, len(candidates))]
            self._grant_environment_drop(revlog_id, item, plant=plant)
            return
        fallback = (
            "growth_charge_standard"
            if tier == "rare_environment"
            else "growth_charge_grand"
        )
        spec = GROWTH_CHARGES[fallback]
        self._grant_consumable_drop(
            revlog_id,
            fallback,
            plant=plant,
            title=f"{spec.name} found",
            message=(
                f"You already own every environment in this tier, so the garden "
                f"left you a {spec.name} instead."
            ),
        )

    def _claim_daily_environment_gift(
        self,
        revlog_id: int,
        *,
        plant: Plant | None,
    ) -> bool:
        scenery = self.state.selected_background
        if scenery not in {"snowy", "halloween", "full_moon"}:
            return False
        day = self.state.daily_stats.day
        if self.state.daily_environment_claims.get(scenery) == day:
            return False
        self.state.daily_environment_claims[scenery] = day
        if scenery == "snowy":
            consumable_id = "growth_charge_small"
        elif scenery == "full_moon":
            consumable_id = "booster_potion"
        else:
            digest = self._reward_digest(revlog_id, namespace=b"halloween-gift")
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
        self._grant_consumable_drop(
            revlog_id,
            consumable_id,
            plant=plant,
            title=f"{scenery_name} daily gift",
            message=(
                f"Your first card answer today awakened {scenery_name}. "
                f"It left one {name} in your Supplements collection."
            ),
            event_prefix="daily",
        )
        return True

    def _maybe_award_random_drop(self, revlog_id: int, plant: Plant | None) -> None:
        """Resolve one deterministic reward slot after a qualifying card answer."""

        if revlog_id <= 0 or any(
            event.revlog_id == revlog_id for event in self.state.reward_drop_history
        ):
            return
        self.state.eligible_reward_count += 1
        if self._claim_daily_environment_gift(revlog_id, plant=plant):
            self.state.ultra_pity_misses += 1
            return
        ultra_hit = False
        for band in DROP_BANDS:
            denominator = (
                ultra_denominator(self.state.ultra_pity_misses)
                if band.tier == "ultra_environment"
                else self.BOOSTER_DROP_CHANCE
                if band.tier == "booster_potion"
                else self.COIN_DROP_CHANCE
                if band.tier == "coin_cache"
                else band.denominator
            )
            if not self._drop_hit(revlog_id, band.tier, denominator):
                continue
            if band.tier in {
                "ultra_environment",
                "very_rare_environment",
                "rare_environment",
            }:
                self._grant_environment_tier(
                    revlog_id, band.tier, plant=plant
                )
                ultra_hit = band.tier == "ultra_environment"
            elif band.tier == "grand_charge":
                self._grant_consumable_drop(
                    revlog_id,
                    "growth_charge_grand",
                    plant=plant,
                    title="A Grand Growth Charge!",
                    message=(
                        "Your garden uncovered a Grand Growth Charge. "
                        "Its 2,000 Growth is waiting in Supplements & Boosters."
                    ),
                )
            elif band.tier == "standard_charge":
                self._grant_consumable_drop(
                    revlog_id,
                    "growth_charge_standard",
                    plant=plant,
                    title="A Standard Growth Charge!",
                    message="A Standard Growth Charge joined your Supplements collection.",
                )
            elif band.tier == "booster_potion":
                self._grant_consumable_drop(
                    revlog_id,
                    "booster_potion",
                    plant=plant,
                    title="A rare garden gift",
                    message=(
                        "Your nurtured plant found a Booster Potion. "
                        "Your steady work is helping the whole garden grow."
                    ),
                )
            elif band.tier == "small_charge":
                self._grant_consumable_drop(
                    revlog_id,
                    "growth_charge_small",
                    plant=plant,
                    title="A Small Growth Charge!",
                    message="A Small Growth Charge joined your Supplements collection.",
                )
            else:
                event_key = f"drop:coins:{revlog_id}"
                if self._credit_currency(
                    event_key, "Rare study gift", self.COIN_DROP_AMOUNT
                ):
                    plant_name = plant.name if plant is not None else "Your garden"
                    self._queue_feedback(
                        event_key,
                        "coin_drop",
                        (
                            f"{plant_name} seems to say: “I can see how much care you’re "
                            f"putting in. Please take these {self.COIN_DROP_AMOUNT} "
                            "Garden Coins.”"
                        ),
                        plant.plant_id if plant is not None else None,
                        title="A little garden gift",
                        asset_category="ui",
                        asset_key="garden_coins",
                        amount=self.COIN_DROP_AMOUNT,
                    )
                    self._record_reward_drop(
                        revlog_id, "garden_coins", self.COIN_DROP_AMOUNT
                    )
            break
        if ultra_hit:
            self.state.ultra_pity_misses = 0
        else:
            self.state.ultra_pity_misses += 1

    def _record_growth_crossings(self, plant: Plant, before: int, after: int) -> None:
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
        previous_index = max(index for index, threshold in enumerate(GROWTH_THRESHOLDS) if before >= threshold)
        new_index = max(index for index, threshold in enumerate(GROWTH_THRESHOLDS) if after >= threshold)
        for stage_index in range(previous_index + 1, new_index + 1):
            previous_stage = GROWTH_STAGES[stage_index - 1]
            new_stage = GROWTH_STAGES[stage_index]
            self._add_memory(
                plant,
                f"stage:{new_stage}",
                "stage",
                previous_stage=previous_stage,
                new_stage=new_stage,
            )
            transition = StageTransition(plant.plant_id, plant.species, previous_stage, new_stage)
            self._pending_stage_transitions.append(transition)
            base_reward = self.STAGE_CURRENCY[new_stage]
            reward = (
                (base_reward * 5 + 2) // 4
                if self.state.selected_background == "autumn"
                else base_reward
            )
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
            self.state.active_plant_periods.append(ActivePlantPeriod(
                self.state.daily_stats.day, None, self._now_ms()
            ))
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
        stats = self.state.daily_stats
        setattr(stats, stats_field, int(getattr(stats, stats_field, 0)) + awarded)
        stats.bonus_growth = (
            stats.streak_bonus_growth
            + stats.fertilizer_growth
            + stats.booster_growth
            + stats.weather_growth
            + stats.scenery_growth
            + stats.charge_growth
        )
        stats.growth_earned = stats.base_growth + stats.bonus_growth
        stats.plant_growth[plant.plant_id] = (
            stats.plant_growth.get(plant.plant_id, 0) + awarded
        )
        self._record_growth_crossings(plant, before, plant.growth_points)
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

    def evaluate_all_due(self, status: DueObligationStatus | None = None) -> tuple[bool, str]:
        # Rollover is itself durable state. Persist it before taking the reward
        # snapshot so every early-return branch leaves memory and disk aligned.
        self.rollover_if_needed()
        snapshot = self._state_snapshot()
        stats = self.state.daily_stats
        if stats.completed_due_cards:
            return False, "You already earned today’s reward for finishing all due cards."
        if stats.reviewed <= 0:
            return False, "Answer at least one card before you can earn the reward for finishing all due cards."
        if status is None:
            resolver = getattr(self.storage, "due_obligations", None)
            status = resolver() if callable(resolver) else DueObligationStatus(available=False, error="Unavailable")
        if not status.complete:
            if status.error:
                return False, status.error
            unit = "due review or learning step remains" if status.remaining == 1 else "due reviews or learning steps remain"
            return False, f"{status.remaining:,} {unit}."
        stats.completed_due_cards = True
        coin_reward, configured_growth = self.all_due_rewards()
        weather_growth = 0
        if configured_growth:
            weather_growth = self._apply_direct_growth(
                self.active_plant(), configured_growth, stats_field="weather_growth"
            )
        feedback = (
            f"You finished all due cards and earned {coin_reward} Garden Coins"
            + (f" and {weather_growth} Growth." if weather_growth else ".")
        )
        self._credit_currency(
            f"all-due:{stats.day}",
            "All due cards finished",
            coin_reward,
            feedback=feedback,
        )
        try:
            self._update_achievements()
            self._persist_or_restore(snapshot)
        except Exception:
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
            self._update_achievements()
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
    ) -> bool:
        if amount <= 0 or any(tx.event_key == event_key for tx in self.state.currency_transactions):
            return False
        self.state.currency_balance += int(amount)
        self.state.currency_transactions.append(CurrencyTransaction(
            transaction_id=f"tx_{uuid.uuid4().hex}",
            event_key=event_key,
            reason=reason,
            delta=int(amount),
            balance=self.state.currency_balance,
            occurred_at=utc_now_iso(),
        ))
        self.state.currency_transactions = self.state.currency_transactions[-500:]
        if feedback:
            self._queue_feedback(event_key, "currency", feedback, plant_id)
        return True

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
    ) -> bool:
        if any(event.event_id == event_id for event in self.state.pending_feedback):
            return False
        self.state.pending_feedback.append(FeedbackEvent(
            event_id,
            kind,
            message,
            utc_now_iso(),
            plant_id,
            title,
            asset_category,
            asset_key,
            max(0, int(amount)),
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
        rows: list[dict[str, Any]] = []
        for band in DROP_BANDS:
            denominator = (
                ultra_denominator(self.state.ultra_pity_misses)
                if band.tier == "ultra_environment"
                else int(band.denominator)
            )
            rows.append({
                "tier": band.tier,
                "name": band.display_name,
                "numerator": int(band.numerator),
                "denominator": denominator,
                "base_denominator": int(band.denominator),
            })
        return {
            "eligible_answers": int(self.state.eligible_reward_count),
            "ultra_pity_misses": int(self.state.ultra_pity_misses),
            "ultra_denominator": ultra_denominator(self.state.ultra_pity_misses),
            "bands": rows,
        }

    def purchase_environment(self, kind: str, item_id: str) -> tuple[bool, str]:
        normalized_kind = str(kind)
        item = environment_item(normalized_kind, str(item_id))
        if item is None:
            return False, "That Weather or Scenery item is not in the current collection."
        if self.owns_environment(normalized_kind, item.item_id):
            return False, f"You already own {item.name}."
        if not item.purchasable or item.price is None:
            return False, f"{item.name} can only be earned while reviewing cards."
        snapshot = self._state_snapshot()
        event_key = f"purchase:environment:{normalized_kind}:{item.item_id}"
        if not self._debit_currency(
            event_key,
            f"Purchased {item.name}",
            item.price,
        ):
            return False, f"{item.name} costs {item.price:,} Garden Coins."
        if normalized_kind == "weather":
            self.state.inventory.setdefault("weather", []).append(item.item_id)
        else:
            self.state.inventory.setdefault("scenery", []).append(item.item_id)
            self.state.inventory.setdefault("backgrounds", []).append(item.item_id)
        self._queue_feedback(
            event_key,
            "environment_purchase",
            (
                f"{item.name} joined your collection. Visit Customize Garden "
                "when you want to equip it."
            ),
            title=f"{item.name} unlocked",
            asset_category="weather" if item.kind == "weather" else "backgrounds",
            asset_key=item.item_id,
            amount=1,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The purchase could not be saved; no Garden Coins were spent."
        return True, (
            f"{item.name} unlocked. It was not equipped automatically; "
            "choose it in Customize Garden."
        )

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
            self.state.equipped["weather"] = item.item_id
        else:
            self.state.selected_background = item.item_id
            self.state.equipped["background"] = item.item_id
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "That environment choice could not be saved."
        return True, f"{item.name} equipped. {item.effect}"

    def set_environment_visibility(self, kind: str, enabled: bool) -> tuple[bool, str]:
        normalized_kind = str(kind)
        if normalized_kind not in {"weather", "scenery"}:
            return False, "Choose Weather or Scenery."
        snapshot = self._state_snapshot()
        self.state.environment_visibility[normalized_kind] = bool(enabled)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "That visual preference could not be saved."
        name = "Weather effects" if normalized_kind == "weather" else "Scenery artwork"
        state = "shown" if enabled else "hidden"
        return True, f"{name} are {state}. The equipped passive remains active."

    def apply_environment_loadout(
        self,
        weather_id: str,
        scenery_id: str,
        visibility: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """Atomically persist the visual configurator draft.

        Customize Garden previews freely, then commits one validated loadout so
        Cancel can never leave a partially applied Weather/Scenery combination.
        """

        weather = environment_item("weather", str(weather_id))
        scenery = environment_item("scenery", str(scenery_id))
        if weather is None or scenery is None:
            return False, "That Weather or Scenery choice is unavailable."
        if not self.owns_environment("weather", weather.item_id):
            return False, f"Unlock {weather.name} before equipping it."
        if not self.owns_environment("scenery", scenery.item_id):
            return False, f"Unlock {scenery.name} before equipping it."
        visual_layers = visibility if isinstance(visibility, dict) else {}
        snapshot = self._state_snapshot()
        self.state.selected_weather = weather.item_id
        self.state.selected_background = scenery.item_id
        self.state.equipped["weather"] = weather.item_id
        self.state.equipped["background"] = scenery.item_id
        self.state.environment_visibility["weather"] = bool(
            visual_layers.get("weather", True)
        )
        self.state.environment_visibility["scenery"] = bool(
            visual_layers.get("scenery", True)
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Those appearance changes could not be saved."
        return True, "Garden appearance saved."

    def purchase_growth_charge(self, charge_id: str) -> tuple[bool, str]:
        spec = GROWTH_CHARGES.get(str(charge_id))
        if spec is None:
            return False, "Choose a valid Growth Charge."
        if not spec.purchasable or spec.price is None:
            return False, f"{spec.name} can only be earned while reviewing cards."
        snapshot = self._state_snapshot()
        event_key = f"purchase:charge:{spec.charge_id}:{uuid.uuid4().hex}"
        if not self._debit_currency(
            event_key, f"Purchased {spec.name}", spec.price
        ):
            return False, f"{spec.name} costs {spec.price:,} Garden Coins."
        self.state.consumables[spec.charge_id] = (
            self.state.consumables.get(spec.charge_id, 0) + 1
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The Growth Charge purchase could not be saved; no Garden Coins were spent."
        return True, f"{spec.name} added to Supplements & Boosters."

    def use_growth_charge(
        self,
        charge_id: str,
        plant_id: str | None = None,
    ) -> tuple[bool, str]:
        spec = GROWTH_CHARGES.get(str(charge_id))
        if spec is None:
            return False, "Choose a valid Growth Charge."
        plant = self.plant_story(str(plant_id or self.state.active_plant_id or ""))
        if (
            plant is None
            or self.state.active_plant_id != plant.plant_id
            or not plant.planted
            or plant.fully_grown
        ):
            return False, "Nurture an unfinished planted plant before using a Growth Charge."
        if self.state.consumables.get(spec.charge_id, 0) <= 0:
            return False, f"You do not have a {spec.name}."
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.state.consumables[spec.charge_id] -= 1
        awarded = self._apply_direct_growth(
            plant, spec.growth, stats_field="charge_growth"
        )
        if awarded <= 0:
            self._pending_stage_transitions = transition_snapshot
            self._restore_state(snapshot)
            return False, "That plant cannot receive more Growth. The charge was not used."
        event_key = f"charge:{spec.charge_id}:{plant.plant_id}:{uuid.uuid4().hex}"
        self._queue_feedback(
            event_key,
            "growth_charge",
            f"{spec.name} gave {plant.name} {awarded:,} Growth.",
            plant.plant_id,
            title=f"{spec.name} used",
            asset_category="ui",
            asset_key=spec.charge_id,
            amount=awarded,
        )
        try:
            self._update_achievements()
            self._persist_or_restore(snapshot)
        except Exception:
            self._pending_stage_transitions = transition_snapshot
            return False, "The Growth Charge could not be saved, so it was not used."
        return True, f"{spec.name} gave {plant.name} {awarded:,} Growth."

    def choose_starter(self, species: str) -> tuple[bool, str, Plant | None]:
        """Plant the free starter; Nurture remains a separate explicit step.

        The day-start null sentinel keeps every review answered before Nurture
        ineligible for retroactive Growth, including reviews answered after the
        species was chosen but before the learner completed setup.
        """
        species = str(species).lower()
        if self.state.starter_selection_complete or self.state.plants:
            return False, "Your starter plant has already been chosen.", None
        if species not in self.release_ready_species():
            return False, "That starter is not currently stocked in the Nursery.", None

        snapshot = self._state_snapshot()
        today = self._scheduler_day()
        plant = Plant(
            plant_id=f"plant_{uuid.uuid4().hex[:12]}",
            species=species,
            name=self._generated_name(species),
            slot_index=0,
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
            f"{plant.name} is planted. Nurture it before studying so Anki card answers can add Growth.",
            plant.plant_id,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "Your starter could not be saved. No changes were made. Try again.", None
        return True, (
            f"{plant.name} is planted and ready to nurture. "
            "Nurture it before studying so Anki card answers can add Growth."
        ), plant

    def purchase_fertilizer(self, plant_id: str, tier: str, *, replace_active: bool = False) -> tuple[bool, str]:
        spec = self.FERTILIZERS.get(str(tier).lower())
        plant = self.plant_story(plant_id)
        if spec is None:
            return False, "Choose a valid Fertilizer tier."
        if plant is None:
            return False, "That plant is no longer in your collection."
        if self.state.active_plant_id != plant.plant_id or not plant.planted or plant.fully_grown:
            return False, "Nurture this unfinished planted plant before applying Fertilizer."
        now = self._now_seconds()
        existing = plant.fertilizer
        current = existing if existing and existing.active(now) else None
        if current is not None and current.tier != spec.tier and not replace_active:
            return False, "Replacing the active Fertilizer will discard its remaining time. Confirm replacement first."
        extending = current is not None and current.tier == spec.tier
        archived = None if extending else self._historical_fertilizer_period(existing, ended_at=now)
        history_identities = {
            self._fertilizer_period_identity(period)
            for period in plant.fertilizer_history
        }
        needs_archive = (
            archived is not None
            and self._fertilizer_period_identity(archived) not in history_identities
        )
        if needs_archive and len(plant.fertilizer_history) >= MAX_FERTILIZER_HISTORY:
            return False, (
                "This plant's current-day Fertilizer history is full. "
                "Try again after Anki's next-day cutoff."
            )
        snapshot = self._state_snapshot()
        event_key = f"purchase:fertilizer:{plant.plant_id}:{spec.tier}:{uuid.uuid4().hex}"
        if not self._debit_currency(event_key, f"Purchased {spec.name} for {plant.name}", spec.price):
            return False, f"{spec.name} costs {spec.price} Garden Coins."
        if needs_archive and archived is not None:
            plant.fertilizer_history.append(archived)
            plant.fertilizer_history.sort(key=lambda period: (
                float(period.started_at if period.started_at is not None else period.expires_at),
                float(period.expires_at),
                str(period.tier),
            ))
        expiration_base = current.expires_at if extending else now
        activation_start = (
            current.started_at
            if extending
            and current.started_at is not None
            else now
        )
        plant.fertilizer = Fertilizer(
            spec.tier,
            spec.growth_per_answer,
            expiration_base + spec.duration_seconds,
            activation_start,
        )
        hours = spec.duration_seconds // 3600
        hour_unit = "hour" if hours == 1 else "hours"
        self._queue_feedback(
            event_key,
            "fertilizer",
            (
                f"{spec.name} is active on {plant.name}: "
                f"+{spec.growth_per_answer} Growth per Anki card answer "
                f"for {hours} {hour_unit}."
            ),
            plant.plant_id,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The Fertilizer purchase could not be saved; no Garden Coins were spent."
        action = "extended" if extending else "applied"
        return True, (
            f"{spec.name} {action} for {hours} {hour_unit}: "
            f"+{spec.growth_per_answer} Growth per Anki card answer while active."
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
        if needs_archive and len(plant.booster_history) >= MAX_BOOSTER_HISTORY:
            return False, (
                "This plant's current-day Booster history is full. "
                "Try again after Anki's next-day cutoff."
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
        species = str(species).lower()
        if not self.state.starter_selection_complete:
            return False, "Choose a starter before purchasing another plant.", None
        if species not in self.release_ready_species():
            return False, "That species is not currently stocked in the Nursery.", None
        price = self.SPECIES_PRICES.get(species)
        if price is None:
            return False, "That species is not available for purchase.", None
        if species in self.state.unlocked_species or any(plant.species == species for plant in self.state.plants):
            return False, "That species is already in your collection.", None
        snapshot = self._state_snapshot()
        event_key = f"purchase:species:{species}"
        species_label = species.replace("_", " ").title()
        if not self._debit_currency(event_key, f"Unlocked {species_label}", price):
            return False, f"{species_label} costs {price} Garden Coins.", None
        plant = Plant(
            plant_id=f"plant_{uuid.uuid4().hex[:12]}",
            species=species,
            name=self._generated_name(species),
            slot_index=None,
            personality=self.SPECIES_PERSONALITY.get(species, "balanced"),
            planted_on=self.state.daily_stats.day,
            memories=[PlantMemory("planted", "planted", self.state.daily_stats.day)],
        )
        self.state.unlocked_species.append(species)
        self.state.plants.append(plant)
        self._queue_feedback(event_key, "unlock", f"{plant.name} joined your plant collection.", plant.plant_id)
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The species purchase could not be saved; no Garden Coins were spent.", None
        return True, f"{plant.name} joined your collection.", plant

    def next_bed_price(self) -> int | None:
        return self.BED_PRICES.get(int(self.state.unlocked_slots))

    def purchase_next_bed(self) -> tuple[bool, str]:
        if not self.state.starter_selection_complete:
            return False, "Choose a starter before unlocking another garden space."
        index = int(self.state.unlocked_slots)
        price = self.BED_PRICES.get(index)
        if price is None or index >= MAX_GARDEN_SLOTS:
            return False, "All six garden spaces are already unlocked."
        snapshot = self._state_snapshot()
        event_key = f"purchase:bed:{index + 1}"
        if not self._debit_currency(event_key, f"Unlocked garden space {index + 1}", price):
            return False, f"Garden space {index + 1} costs {price} Garden Coins."
        self.state.unlocked_slots += 1
        self._queue_feedback(event_key, "unlock", f"Garden space {index + 1} unlocked.")
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The garden-space purchase could not be saved; no Garden Coins were spent."
        return True, f"Garden space {index + 1} unlocked."

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
            return False, "Choose an empty unlocked garden space."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if destination not in available:
            return False, "Choose an empty unlocked garden space."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The planting change could not be saved."
        return True, f"{plant.name} was planted in space {destination + 1}."

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
            if replacement is not None:
                self._record_active_period(replacement.plant_id)
            return replacement
        if plant is None or not plant.planted or plant.fully_grown:
            self.state.active_plant_id = None
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

    def _record_active_period(self, plant_id: str) -> None:
        day = self.state.daily_stats.day
        latest = max(
            (period for period in self.state.active_plant_periods if period.day == day),
            key=lambda period: period.started_at_ms,
            default=None,
        )
        if latest is None or latest.plant_id != plant_id:
            self.state.active_plant_periods.append(ActivePlantPeriod(
                day, plant_id, self._now_ms()
            ))

    def active_plant(self) -> Plant | None:
        return self._repair_active_plant()

    def set_active_plant(self, plant_id: Optional[str]) -> tuple[bool, str]:
        plant = self.plant_story(str(plant_id or ""))
        if plant is None:
            return False, "That plant is no longer in your collection."
        if not plant.planted:
            return False, "Plant this species in an unlocked garden space before nurturing it."
        if plant.fully_grown:
            return False, "This plant is fully grown. Choose an unfinished plant to nurture instead."
        if self.state.active_plant_id == plant.plant_id:
            return True, f"{plant.name} is already being nurtured and receives Growth from future card answers."
        snapshot = self._state_snapshot()
        self.state.active_plant_id = plant.plant_id
        self.state.active_plant_periods.append(ActivePlantPeriod(
            self.state.daily_stats.day, plant.plant_id, self._now_ms()
        ))
        self._add_memory(plant, "nurture:first", "first_nurture")
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
        self.state.inventory["backgrounds"] = list(SCENERY_CATALOG)
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
            return False, "Choose an unlocked garden space.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That garden space is still locked.", None
        origin = int(plant.slot_index or 0)
        if origin == destination:
            return False, "That plant is already in this space.", None
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
            return False, "Choose an unlocked garden space.", None
        if destination < 0 or destination >= self.state.unlocked_slots:
            return False, "That garden space is still locked.", None
        origin = draft.current[draft.selected_plant_id]
        if destination == origin:
            return False, "That plant is already in this space.", None
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
            return False, "The pending arrangement includes a locked garden space.", None
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
            species = item.species.replace("_", " ").title()
            return f"Your {species} reached {item.new_stage.title()}!"
        names = ", ".join(item.species.replace("_", " ").title() for item in transitions[:3])
        if len(transitions) > 3:
            names += f" and {len(transitions) - 3} more"
        return f"Garden milestone! {names} reached new growth stages."

    def _ensure_achievements(self) -> None:
        definitions = {
            "streak_7": ("7-Day Anki Streak", "Answer at least one card on 7 Anki days in a row."),
            "streak_30": ("30-Day Anki Streak", "Answer at least one card on 30 Anki days in a row."),
            "reviews_100_day": ("Century Day", "Record 100 card answers in one Anki day."),
            "reviews_1000_total": ("Deep Roots", "Record 1,000 total card answers."),
            "retention_90": ("Clear Recall", "Reach at least 90% accuracy after 20 card answers."),
            "retention_100": ("Perfect Canopy", "Complete 30 card answers without choosing Again."),
            "all_due_done": ("All Clear", "Finish all due cards in the collection."),
            "no_lapse": ("No-Again Session", "Complete 40 card answers without choosing Again."),
        }
        self.state.achievements = {key: value for key, value in self.state.achievements.items() if key in definitions}
        for key, (name, description) in definitions.items():
            self.state.achievements.setdefault(key, Achievement(key, name, description))

    def _update_achievements(self) -> None:
        stats = self.state.daily_stats
        checks = {
            "streak_7": self.state.streak_days >= 7,
            "streak_30": self.state.streak_days >= 30,
            "reviews_100_day": stats.reviewed >= 100,
            "reviews_1000_total": self.state.total_reviews >= 1_000,
            "retention_90": stats.reviewed >= 20 and stats.accuracy >= 0.9,
            "retention_100": stats.reviewed >= 30 and stats.accuracy == 1.0,
            "all_due_done": stats.completed_due_cards,
            "no_lapse": stats.reviewed >= 40 and stats.wrong == 0,
        }
        for key, achieved in checks.items():
            achievement = self.state.achievements[key]
            if achieved and not achievement.unlocked:
                achievement.unlocked = True
                achievement.unlocked_at = utc_now_iso()
            achievement.progress = 1.0 if achievement.unlocked else 0.0

    def progress_estimates(self, plant: Plant) -> int:
        stage_index = GROWTH_STAGES.index(plant.growth_stage)
        if stage_index >= len(GROWTH_STAGES) - 1:
            return 0
        remaining = GROWTH_THRESHOLDS[stage_index + 1] - plant.growth_points
        return int(math.ceil(remaining / self.BASE_GROWTH_PER_REVIEW))

    def export_progress_summary(self) -> str:
        payload = {
            "date": self.state.daily_stats.day,
            "streak": self.state.streak_days,
            "total_reviews": self.state.total_reviews,
            "garden_currency": self.state.currency_balance,
            "streak_bonus_percent": self.current_streak_bonus_percent(),
            "plants": [
                {
                    "name": plant.name,
                    "species": plant.species,
                    "stage": plant.growth_stage,
                    "growth": plant.growth_points,
                    "planted": plant.planted,
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
