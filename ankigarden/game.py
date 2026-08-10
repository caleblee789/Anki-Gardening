from __future__ import annotations

import json
import math
import time
import uuid
from bisect import bisect_left, insort
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .asset_manager import AssetManager, ResolvedAsset
from .models.state import (
    Achievement,
    ActivePlantPeriod,
    CurrencyTransaction,
    DailyStats,
    FeedbackEvent,
    Fertilizer,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    MAX_FERTILIZER_HISTORY,
    MAX_GARDEN_SLOTS,
    MAX_PLANT_NAME_LENGTH,
    MAX_PROCESSED_REVLOG_IDS,
    PLANT_SPECIES,
    PLANT_SPECIES_ORDER,
    Plant,
    PlantMemory,
    STREAK_BONUS_TIERS,
    utc_now_iso,
)
from .storage import DueObligationStatus, SchedulerBoundaryError


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

    @property
    def bonus_growth(self) -> int:
        return self.streak_bonus_growth + self.fertilizer_growth

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
    SOIL_PLANT_MESSAGE = "Choose an empty unlocked garden bed."
    SOIL_CAPACITY_MESSAGE = "Unlock or empty a garden bed before planting this plant."
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
        "premium": FertilizerSpec("premium", "Premium Fertilizer", 3, 4 * 60 * 60, 150),
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
        self.assets = AssetManager(config, storage)
        geometry_version, allowed_types = self._scene_surface_contract()
        self._scene_geometry_version = geometry_version
        self._surface_allowed_base_types = allowed_types
        snapshot = self._state_snapshot()
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
                    f"{plant.name} was returned to the collection because no garden bed was open."
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
        self.state.active_plant_periods = [
            period for period in self.state.active_plant_periods if period.day >= (current_day - timedelta(days=7)).isoformat()
        ]
        self.state.active_plant_periods.append(ActivePlantPeriod(today, self.state.active_plant_id, self._now_ms()))
        self._update_weather()
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

    def register_review(self, review_payload: Dict[str, Any]) -> ReviewAward:
        snapshot = self._state_snapshot()
        transition_snapshot = list(self._pending_stage_transitions)
        self.rollover_if_needed(persist=False)
        try:
            award = self._register_review_in_memory(review_payload)
            self._update_achievements()
            self._update_weather()
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
        self.state.streak_days = self.state.streak_days + 1 if (today - last).days == 1 else 1
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

    def _award_review_growth(self, plant: Plant | None, event_ms: int) -> ReviewAward:
        if plant is None:
            return ReviewAward(None, 0, 0, 0, 0, "Choose an unfinished plant to nurture to resume Growth.")
        bonus_percent = self.current_streak_bonus_percent()
        bonus_numerator = plant.bonus_remainder + (self.BASE_GROWTH_PER_REVIEW * bonus_percent)
        proposed_streak_bonus, next_remainder = divmod(bonus_numerator, 100)
        proposed_fertilizer_bonus = self.fertilizer_growth(plant, now=event_ms / 1000)
        remaining = max(0, GROWTH_THRESHOLDS[-1] - plant.growth_points)
        base = min(self.BASE_GROWTH_PER_REVIEW, remaining)
        bonus_remaining = max(0, remaining - base)
        streak_bonus = min(proposed_streak_bonus, bonus_remaining)
        fertilizer_bonus = min(proposed_fertilizer_bonus, max(0, bonus_remaining - streak_bonus))
        if base + streak_bonus + fertilizer_bonus <= 0:
            return ReviewAward(plant.plant_id, 0, 0, 0, bonus_percent, "This plant is fully grown.")
        before = plant.growth_points
        plant.growth_points += base + streak_bonus + fertilizer_bonus
        plant.bonus_remainder = next_remainder if plant.growth_points < GROWTH_THRESHOLDS[-1] else 0
        stats = self.state.daily_stats
        stats.base_growth += base
        stats.streak_bonus_growth += streak_bonus
        stats.fertilizer_growth += fertilizer_bonus
        stats.bonus_growth = stats.streak_bonus_growth + stats.fertilizer_growth
        stats.growth_earned = stats.base_growth + stats.bonus_growth
        stats.plant_growth[plant.plant_id] = stats.plant_growth.get(plant.plant_id, 0) + base + streak_bonus + fertilizer_bonus
        self._record_growth_crossings(plant, before, plant.growth_points)
        return ReviewAward(plant.plant_id, base, streak_bonus, fertilizer_bonus, bonus_percent)

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
            reward = self.STAGE_CURRENCY[new_stage]
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
        self._credit_currency(
            f"all-due:{stats.day}",
            "All due cards finished",
            10,
            feedback="You finished all due cards and earned 10 Garden Coins.",
        )
        try:
            self._update_achievements()
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The reward for finishing all due cards could not be saved."
        return True, "You finished all due cards and earned 10 Garden Coins."

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
            self._update_weather()
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

    def _queue_feedback(self, event_id: str, kind: str, message: str, plant_id: str | None = None) -> bool:
        if any(event.event_id == event_id for event in self.state.pending_feedback):
            return False
        self.state.pending_feedback.append(FeedbackEvent(event_id, kind, message, utc_now_iso(), plant_id))
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

    def choose_starter(self, species: str) -> tuple[bool, str, Plant | None]:
        """Create the first plant for free without backfilling earlier reviews."""
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
        self.state.active_plant_id = plant.plant_id
        if not any(
            period.day == today
            and period.plant_id is None
            and period.started_at_ms <= 0
            for period in self.state.active_plant_periods
        ):
            # A day-start sentinel ensures a later same-day revlog sync routes
            # reviews answered before this choice to no plant.
            self.state.active_plant_periods.append(ActivePlantPeriod(today, None, 0))
        self.state.active_plant_periods.append(ActivePlantPeriod(
            today, plant.plant_id, self._now_ms()
        ))
        self._queue_feedback(
            f"starter:{species}",
            "unlock",
            f"{plant.name} joined your garden as your free starter.",
            plant.plant_id,
        )
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The starter choice could not be saved; you can choose again.", None
        return True, f"{plant.name} joined your garden as your free starter.", plant

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
                f"{spec.name} is active on {plant.name}. Each card answer adds "
                f"{spec.growth_per_answer} extra Growth for {hours} {hour_unit}."
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
            f"+{spec.growth_per_answer} Growth per answer while active."
        )

    def purchase_species(self, species: str) -> tuple[bool, str, Plant | None]:
        species = str(species).lower()
        if not self.state.starter_selection_complete:
            return False, "Choose your free starter before purchasing another plant.", None
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
            return False, "Choose your free starter before unlocking another garden space."
        index = int(self.state.unlocked_slots)
        price = self.BED_PRICES.get(index)
        if price is None or index >= MAX_GARDEN_SLOTS:
            return False, "All six garden spaces are already unlocked."
        snapshot = self._state_snapshot()
        event_key = f"purchase:bed:{index + 1}"
        if not self._debit_currency(event_key, f"Unlocked garden bed {index + 1}", price):
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
            return False, "Choose an empty unlocked garden bed."
        if not self.slot_accepts_plant(plant, destination):
            return False, self.SOIL_PLANT_MESSAGE
        if destination not in available:
            return False, "Choose an empty unlocked garden bed."
        snapshot = self._state_snapshot()
        plant.slot_index = destination
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The planting change could not be saved."
        return True, f"{plant.name} was planted in bed {destination + 1}."

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
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The new name could not be saved."
        return True, f"This plant is now named {clean}."

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
        used = {plant.name.casefold() for plant in self.state.plants}
        choices = self.SPECIES_NAMES.get(species, (species.replace("_", " ").title(),))
        for choice in choices:
            if choice.casefold() not in used:
                return choice
        base = choices[0]
        suffix = 2
        while f"{base} {suffix}".casefold() in used:
            suffix += 1
        return f"{base} {suffix}"

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
            return False, "Choose an unlocked garden bed.", None
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
            return False, "Choose an unlocked garden bed.", None
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
            return False, "There is no staged move to undo."
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
            return False, "The staged arrangement is not valid.", None
        if any(slot < 0 or slot >= self.state.unlocked_slots for slot in draft.current.values()):
            return False, "The staged arrangement includes a locked garden bed.", None
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

    def _update_weather(self) -> None:
        stats = self.state.daily_stats
        if stats.reviewed > 350 and stats.accuracy < 0.72:
            self.state.selected_weather = "cloudy"
        elif stats.wrong > stats.correct and stats.reviewed > 25:
            self.state.selected_weather = "cloudy"
        elif stats.accuracy >= 0.9 and stats.reviewed >= 50:
            self.state.selected_weather = "fireflies"
        elif stats.reviewed >= 120:
            self.state.selected_weather = "sunny"
        else:
            self.state.selected_weather = "breeze"

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

    def seasonal_theme(self) -> str:
        if not self.config.value("seasonal_visuals", True):
            return "default"
        month = date.today().month
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "autumn"

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

    def resolve_preview_assets(
        self,
        theme: str,
        weather: str,
        stage: str,
        quality_preference: str,
        plant_requests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        seasonal = self.seasonal_theme()
        time_of_day = self.local_time_band()
        normalized_theme = self.assets.normalize_theme(theme)
        background = self.assets.resolve(
            "backgrounds",
            f"bg_{seasonal}_{weather}",
            f"slot:backgrounds:{seasonal}:{weather}",
            theme=normalized_theme,
            time_of_day=time_of_day,
            quality_preference=quality_preference,
        )
        weather_overlay = self.assets.resolve(
            "weather",
            f"weather_{weather}",
            f"slot:weather:{weather}",
            theme=normalized_theme,
            quality_preference=quality_preference,
        )
        garden_overlay = self.resolve_garden_overlay_asset(theme=normalized_theme, quality_preference=quality_preference)
        plants: dict[str, Any] = {}
        requests = [
            (str(item.get("species") or ""), str(item.get("stage") or stage))
            for item in (plant_requests or [])
            if isinstance(item, dict) and item.get("species")
        ] or [(species, stage) for species in ("bonsai", "rose", "sunflower")]
        for species, requested_stage in requests:
            asset = self.assets.resolve(
                "plants", f"{species}_{requested_stage}", f"slot:plants:{species}:{requested_stage}",
                theme=normalized_theme, quality_preference=quality_preference,
            )
            plants[species] = asset.to_payload() if asset else None
        return {
            "background": background.to_payload() if background else None,
            "garden_overlay": garden_overlay.to_payload() if garden_overlay else None,
            "weather": weather_overlay.to_payload() if weather_overlay else None,
            "plant": plants.get("rose"),
            "plants": plants,
        }

    def resolve_background_image(self) -> Optional[str]:
        asset = self.resolve_background_asset()
        return str(asset.path) if asset else None

    def resolve_background_asset(self) -> Optional[ResolvedAsset]:
        seasonal = self.seasonal_theme()
        weather = self.state.selected_weather
        return self.assets.resolve(
            "backgrounds",
            f"bg_{seasonal}_{weather}",
            f"slot:backgrounds:{seasonal}:{weather}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
            time_of_day=self.local_time_band(),
        )

    def resolve_weather_overlay(self) -> Optional[str]:
        asset = self.resolve_weather_asset()
        return str(asset.path) if asset else None

    def resolve_weather_asset(self) -> Optional[ResolvedAsset]:
        return self.assets.resolve(
            "weather",
            f"weather_{self.state.selected_weather}",
            f"slot:weather:{self.state.selected_weather}",
            theme=self.config.value("visual_theme", "verdant_twilight"),
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
            seasonal = self.seasonal_theme()
            weather = self.state.selected_weather
            path = self.assets.get_or_fetch(
                "backgrounds", f"bg_{seasonal}_{weather}", f"slot:backgrounds:{seasonal}:{weather}",
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
