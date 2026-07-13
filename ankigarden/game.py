from __future__ import annotations

import json
import random
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

from .asset_manager import AssetManager, ResolvedAsset
from .models.state import (
    Achievement, GardenState, GROWTH_STAGES, MAX_PLANT_NAME_LENGTH, MilestoneReward, Plant, PlantMemory, Quest, iso_now,
)


def difficulty_from_factor(value: Any) -> float:
    """Normalize Anki's ease factor, treating zero on new cards as unknown."""
    try:
        factor = int(value)
    except (TypeError, ValueError):
        factor = 2500
    if factor <= 0:
        factor = 2500
    return max(0.1, min(1.0, (3000 - factor) / 2000))


def queue_and_lapse_from_revlog_type(qtype: object, ease: object) -> tuple[int, int] | None:
    """Map answered revlog rows to stable queue semantics shared by live and catch-up paths."""
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
class PlacementChange:
    before: dict[str, int]
    after: dict[str, int]

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"before": dict(self.before), "after": dict(self.after)}


class GardenGameEngine:
    MILESTONE_REVIEWS = (250, 700, 1500, 2600)
    STREAK_MEMORY_MILESTONES = (3, 7, 14, 30, 60, 100, 365)
    REWARD_SPECIES = ("fern", "cactus", "ivy", "orchid", "sunbloom", "moonflower")
    SPECIES_PERSONALITY = {
        "bonsai": "streak",
        "rose": "accuracy",
        "cactus": "volume",
        "orchid": "difficult",
        "moonflower": "night",
        "sunbloom": "morning",
        "fern": "recovery",
        "ivy": "cumulative",
    }
    SPECIES_NAMES = {
        "bonsai": ("Moss", "Juniper", "Sage"), "rose": ("Briar", "Rosie", "Petal"),
        "cactus": ("Pip", "Prickle", "Sol"), "orchid": ("Opal", "Iris", "Luma"),
        "moonflower": ("Luna", "Nox", "Selene"), "sunbloom": ("Sunny", "Marigold", "Dawn"),
        "fern": ("Fiddle", "Frond", "Clover"), "ivy": ("Vine", "Ever", "Sylvan"),
    }

    def _effective_stage(self, plant: Plant) -> str:
        return "rare" if plant.rare_variant else plant.growth_stage

    def peek_stage_transitions(self) -> list[StageTransition]:
        return list(self._pending_stage_transitions)

    def consume_stage_transitions(self) -> list[StageTransition]:
        transitions = list(self._pending_stage_transitions)
        self._pending_stage_transitions.clear()
        return transitions

    @staticmethod
    def stage_transition_message(transitions: list[StageTransition]) -> str:
        if not transitions:
            return ""
        if len(transitions) == 1:
            item = transitions[0]
            return f"Your {item.species.title()} reached {item.new_stage.title()}!"
        names = ", ".join(item.species.title() for item in transitions[:3])
        if len(transitions) > 3:
            names += f" and {len(transitions) - 3} more"
        return f"Garden milestone! {names} reached new growth stages."
    def __init__(self, config: Any, storage: Any) -> None:
        self.config = config
        self.storage = storage
        self.state: GardenState = storage.state
        self._pending_stage_transitions: list[StageTransition] = []
        self.assets = AssetManager(config, storage)
        snapshot = self._state_snapshot()
        self._ensure_achievements()
        self._ensure_daily_quests(force_refresh=False)
        self._repair_focus_plant()
        self._ensure_pending_milestone()
        if self.state.to_dict() != snapshot:
            self._persist_or_restore(snapshot)

    def _state_snapshot(self) -> dict[str, Any]:
        # State serializers intentionally return plain dictionaries, but nested
        # dataclass dictionaries may still alias live objects. Transactions need
        # an isolated snapshot so rollback remains trustworthy.
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

    def rollover_if_needed(self, *, persist: bool = True) -> None:
        today = date.today().isoformat()
        if self.state.daily_stats.day == today:
            return
        snapshot = self._state_snapshot()
        self._apply_streak_rollover(today)
        self.state.daily_stats.day = today
        self.state.daily_stats.reviewed = 0
        self.state.daily_stats.correct = 0
        self.state.daily_stats.wrong = 0
        self.state.daily_stats.new_count = 0
        self.state.daily_stats.learning_count = 0
        self.state.daily_stats.review_count = 0
        self.state.daily_stats.difficult_count = 0
        self.state.daily_stats.recovered_lapses = 0
        self.state.daily_stats.growth_earned = 0
        self.state.daily_stats.completed_due_cards = False
        self._ensure_daily_quests(force_refresh=True)
        self._update_weather()
        if persist:
            self._persist_or_restore(snapshot)

    def register_review(self, review_payload: Dict[str, Any]) -> None:
        snapshot = self._state_snapshot()
        previous_reviews = self.state.total_reviews
        previous_streak = self.state.streak_days
        self.rollover_if_needed(persist=False)
        today = self.state.daily_stats
        first_review_today = today.reviewed == 0
        if first_review_today:
            self.state.streak_days += 1
            self.state.last_active_day = date.today().isoformat()

        today.reviewed += 1
        self.state.total_reviews += 1

        queue, ease, deck_id, difficulty, lapse_count = self._normalized_review(review_payload)

        is_correct = ease > 1
        if is_correct:
            today.correct += 1
            self.state.total_correct += 1
            if lapse_count > 0:
                today.recovered_lapses += 1
        else:
            today.wrong += 1
            self.state.total_wrong += 1
            today.difficult_count += 1

        card_type = "review"
        if queue == 0:
            card_type = "new"
            today.new_count += 1
        elif queue in (1, 3):
            card_type = "learning"
            today.learning_count += 1
        else:
            today.review_count += 1

        growth = self._calculate_growth(card_type, is_correct, difficulty, lapse_count, deck_id)
        if growth > 0:
            self._award_growth(growth, deck_id)
        self._update_quests()
        self._record_shared_memories(previous_reviews, previous_streak)
        self._update_achievements()
        self._maybe_unlock_slot()
        self._update_weather()
        try:
            revlog_id = max(0, int(review_payload.get("revlog_id", 0)))
        except (AttributeError, TypeError, ValueError):
            revlog_id = 0
        self.state.retrospective_last_revlog_id = max(self.state.retrospective_last_revlog_id, revlog_id)
        self._persist_or_restore(snapshot)

    def _calculate_growth(self, card_type: str, is_correct: bool, difficulty: float, lapse_count: int, deck_id: Optional[int]) -> int:
        mapping = self.config.value("points_per_card", {})
        base = float(mapping.get(card_type, 2))
        base *= float(self.config.value("correct_answer_bonus", 1.08) if is_correct else self.config.value("incorrect_answer_penalty", 0.6))

        accuracy_weight = 0.9 + (self.state.daily_stats.accuracy * 0.3)
        difficulty_weight = 1.0 + (difficulty * float(self.config.value("difficulty_weight", 0.12)))
        recovery_weight = 1.0 + (min(3, lapse_count) * float(self.config.value("recovery_weight", 0.2)))
        streak_weight = 1.0 + min(0.2, self.state.streak_days / 100)
        session_quality = self._session_quality_score()
        quality_weight = 0.9 + (session_quality * float(self.config.value("session_quality_weight", 0.25)))
        if self.config.value("time_of_day_bonus", True):
            hour = datetime.now().hour
            if hour <= 7:
                streak_weight += 0.05
            elif hour >= 22:
                streak_weight += 0.05

        points = int(max(0, round(base * accuracy_weight * difficulty_weight * recovery_weight * streak_weight * quality_weight)))
        return points

    @staticmethod
    def _normalized_review(payload: Any) -> tuple[int, int, Optional[int], float, int]:
        """Return bounded review inputs without allowing malformed hook data to abort saving."""
        source = payload if isinstance(payload, dict) else {}
        try:
            queue = int(source.get("queue", 2))
        except (TypeError, ValueError):
            queue = 2
        try:
            ease = max(1, min(4, int(source.get("ease", 1))))
        except (TypeError, ValueError):
            ease = 1
        try:
            difficulty = max(0.1, min(1.0, float(source.get("difficulty", 0.4))))
        except (TypeError, ValueError):
            difficulty = 0.4
        try:
            lapse_count = max(0, min(100, int(source.get("lapse_count", 0))))
        except (TypeError, ValueError):
            lapse_count = 0
        raw_deck_id = source.get("deck_id")
        try:
            deck_id = int(raw_deck_id) if raw_deck_id is not None else None
        except (TypeError, ValueError):
            deck_id = None
        return queue, ease, deck_id, difficulty, lapse_count

    def _award_growth(self, growth: int, deck_id: Optional[int] = None) -> int:
        """Apply and record all growth through one accounting path."""
        awarded = max(0, int(growth))
        if awarded == 0:
            return 0
        self._apply_growth(awarded, deck_id)
        self.state.daily_stats.growth_earned += awarded
        return awarded

    def _session_quality_score(self) -> float:
        s = self.state.daily_stats
        if s.reviewed == 0:
            return 0.5
        volume_component = min(1.0, s.reviewed / 150)
        accuracy_component = s.accuracy
        error_pressure = min(0.25, s.wrong / max(1, s.reviewed))
        return max(0.2, (0.55 * accuracy_component) + (0.45 * volume_component) - error_pressure)

    def _apply_growth(self, growth: int, deck_id: Optional[int]) -> None:
        plants = sorted(self.state.plants, key=lambda plant: (plant.slot_index, plant.plant_id))
        if not plants:
            return
        focus = self._repair_focus_plant()
        awarded = max(0, int(growth))
        allocations = {plant.plant_id: 0 for plant in plants}
        if len(plants) == 1 or focus is None:
            allocations[plants[0].plant_id] = awarded
        else:
            focus_points = (awarded * 80 + 50) // 100
            focus_points = min(awarded, focus_points)
            allocations[focus.plant_id] = focus_points
            others = [plant for plant in plants if plant.plant_id != focus.plant_id]
            base, remainder = divmod(awarded - focus_points, len(others))
            for index, plant in enumerate(others):
                allocations[plant.plant_id] = base + (1 if index < remainder else 0)
        for plant in plants:
            previous_stage = self._effective_stage(plant)
            plant.growth_points += allocations[plant.plant_id]
            plant.vitality = min(1.0, plant.vitality + 0.03)
            new_stage = self._effective_stage(plant)
            if new_stage != previous_stage:
                previous_index = GROWTH_STAGES.index(previous_stage)
                new_index = GROWTH_STAGES.index(new_stage)
                for stage_index in range(previous_index + 1, new_index + 1):
                    reached_stage = GROWTH_STAGES[stage_index]
                    self._add_memory(
                        plant, f"stage:{reached_stage}", "stage",
                        previous_stage=GROWTH_STAGES[stage_index - 1], new_stage=reached_stage,
                    )
                self._pending_stage_transitions.append(
                    StageTransition(
                        plant_id=plant.plant_id,
                        species=plant.species,
                        previous_stage=previous_stage,
                        new_stage=new_stage,
                    )
                )

    def _ensure_achievements(self) -> None:
        defs = {
            "streak_7": ("7-Day Rhythm", "Study seven days in a row."),
            "streak_30": ("Evergreen Month", "Study 30 days in a row."),
            "reviews_100_day": ("Century Day", "Complete 100 reviews in one day."),
            "reviews_1000_total": ("Deep Roots", "Complete 1000 total reviews."),
            "retention_90": ("Clear Recall", "Reach at least 90% accuracy in a day."),
            "retention_100": ("Perfect Canopy", "Perfect retention on at least 30 cards in a day."),
            "all_due_done": ("Inbox Zero", "Finish all due cards for today."),
            "no_lapse": ("No-Lapse Session", "Review at least 40 cards with no incorrect answers."),
        }
        self.state.achievements = {
            key: value for key, value in self.state.achievements.items() if key in defs
        }
        for aid, (name, desc) in defs.items():
            if aid not in self.state.achievements:
                self.state.achievements[aid] = Achievement(aid, name, desc)

    def _ensure_daily_quests(self, force_refresh: bool = False) -> None:
        if self.state.daily_quests and not force_refresh:
            return
        s = self.state.daily_stats
        difficulty = self.config.value("quest_difficulty", "normal")
        base = {"easy": 35, "normal": 50, "hard": 80}.get(difficulty, 50)
        quest_pool = [
            Quest("reviews", f"Complete {base} reviews", base, "reviewed", reward_growth=20),
            Quest("accuracy", "Maintain at least 85% accuracy", 85, "accuracy", reward_growth=15),
            Quest("learning", f"Finish {int(base * 0.6)} learning/review cards", int(base * 0.6), "lr_total", reward_growth=18),
            Quest("growth", f"Earn {int(self.config.value('daily_goal', 140))} garden growth", int(self.config.value("daily_goal", 140)), "growth", reward_growth=20),
        ]
        if s.accuracy < 0.8 and s.reviewed >= 30:
            picks = [quest_pool[1], quest_pool[0], quest_pool[2]]
        elif s.reviewed < 20:
            picks = [quest_pool[0], quest_pool[2], quest_pool[3]]
        else:
            rng = random.Random(date.today().toordinal())
            picks = rng.sample(quest_pool, k=min(self.config.value("max_daily_quests", 3), len(quest_pool)))
        self.state.daily_quests = picks[:3]

    def _metric_value(self, metric: str) -> int:
        stats = self.state.daily_stats
        if metric == "reviewed":
            return stats.reviewed
        if metric == "accuracy":
            return int(stats.accuracy * 100)
        if metric == "lr_total":
            return stats.learning_count + stats.review_count
        if metric == "difficult":
            return stats.difficult_count
        if metric == "recoveries":
            return stats.recovered_lapses
        if metric == "growth":
            return stats.growth_earned
        return 0

    def _update_quests(self) -> None:
        for quest in self.state.daily_quests:
            if quest.completed:
                continue
            quest.progress = self._metric_value(quest.metric)
            if quest.progress >= quest.target:
                quest.completed = True
                self.state.quest_history.append(f"{date.today().isoformat()}:{quest.quest_id}")
                self._award_growth(quest.reward_growth, None)

    def reconcile_daily_goal(self, new_goal: int) -> None:
        """Reconcile today's active growth quest without revoking earned rewards."""
        goal = max(10, min(2000, int(new_goal)))
        snapshot = self._state_snapshot()
        changed = False
        for quest in self.state.daily_quests:
            if quest.metric != "growth" or quest.completed:
                continue
            quest.target = goal
            quest.description = f"Earn {goal} garden growth"
            quest.progress = self._metric_value("growth")
            changed = True
            if quest.progress >= quest.target:
                quest.completed = True
                history_key = f"{date.today().isoformat()}:{quest.quest_id}"
                if history_key not in self.state.quest_history:
                    self.state.quest_history.append(history_key)
                    self._award_growth(quest.reward_growth, None)
        if changed:
            self._persist_or_restore(snapshot)

    def set_due_completion(self, completed: bool) -> None:
        snapshot = self._state_snapshot()
        self.state.daily_stats.completed_due_cards = completed
        self._update_achievements()
        self._persist_or_restore(snapshot)

    def assign_focus_plant(self, plant_id: Optional[str]) -> None:
        self.set_focus_plant(plant_id)

    def _repair_focus_plant(self) -> Optional[Plant]:
        plants = sorted(self.state.plants, key=lambda plant: (plant.slot_index, plant.plant_id))
        if not plants:
            self.state.focus_plant_id = None
            return None
        focus = next((plant for plant in plants if plant.plant_id == self.state.focus_plant_id), None)
        if focus is None:
            focus = plants[0]
            self.state.focus_plant_id = focus.plant_id
        return focus

    def focus_plant(self) -> Optional[Plant]:
        return self._repair_focus_plant()

    def set_focus_plant(self, plant_id: Optional[str]) -> tuple[bool, str]:
        plant = next((plant for plant in self.state.plants if plant.plant_id == plant_id), None)
        if plant is None:
            return False, "That plant is no longer in your garden."
        snapshot = self._state_snapshot()
        self.state.focus_plant_id = plant.plant_id
        self._add_memory(plant, "focus:first", "first_focus")
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "That nurturing choice could not be saved. Your previous plant is still being nurtured."
        return True, (
            f"Now nurturing {plant.name}. It receives 80% of growth earned from reviews; "
            "the remaining 20% is shared among your other plants."
        )

    def rename_plant(self, plant_id: str, name: str) -> tuple[bool, str]:
        plant = next((item for item in self.state.plants if item.plant_id == plant_id), None)
        if plant is None:
            return False, "That plant is no longer in your garden."
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
            return False, "The new name could not be saved. The previous name is still active."
        return True, f"This plant is now named {clean}."

    def plant_story(self, plant_id: str) -> Optional[Plant]:
        return next((item for item in self.state.plants if item.plant_id == plant_id), None)

    def _add_memory(self, plant: Plant, memory_id: str, kind: str, *, value: int = 0,
                    previous_stage: Optional[str] = None, new_stage: Optional[str] = None) -> bool:
        if any(memory.memory_id == memory_id for memory in plant.memories):
            return False
        plant.memories.append(PlantMemory(
            memory_id=memory_id, kind=kind, occurred_on=self.state.daily_stats.day,
            value=max(0, int(value)), previous_stage=previous_stage, new_stage=new_stage,
        ))
        return True

    def _record_shared_memories(self, previous_reviews: int, previous_streak: int) -> None:
        focus = self.focus_plant()
        if focus is None:
            return
        for threshold in self.STREAK_MEMORY_MILESTONES:
            if previous_streak < threshold <= self.state.streak_days:
                self._add_memory(focus, f"streak:{threshold}", "streak", value=threshold)
        for threshold in self.MILESTONE_REVIEWS:
            if previous_reviews < threshold <= self.state.total_reviews:
                self._add_memory(focus, f"reviews:{threshold}", "reviews", value=threshold)

    def _generated_name(self, species: str) -> str:
        used = {plant.name.casefold() for plant in self.state.plants}
        choices = self.SPECIES_NAMES.get(species, (species.title(),))
        for choice in choices:
            if choice.casefold() not in used:
                return choice
        base = choices[0]
        suffix = 2
        while f"{base} {suffix}".casefold() in used:
            suffix += 1
        return f"{base} {suffix}"

    def place_plant(self, plant_id: str, destination_slot: int) -> tuple[bool, str, Optional[PlacementChange]]:
        """Atomically move a plant to an unlocked slot, swapping when occupied."""
        plants_by_id = {plant.plant_id: plant for plant in self.state.plants}
        if len(plants_by_id) != len(self.state.plants):
            return False, "The garden has duplicate plant IDs and cannot be rearranged safely.", None
        plant = plants_by_id.get(str(plant_id))
        if plant is None:
            return False, "That plant is no longer in your garden.", None
        if isinstance(destination_slot, bool):
            return False, "Choose an unlocked garden space.", None
        try:
            destination = int(destination_slot)
        except (TypeError, ValueError):
            return False, "Choose an unlocked garden space.", None
        unlocked = max(0, min(6, int(self.state.unlocked_slots)))
        if destination < 0 or destination >= unlocked:
            return False, "That garden space is still locked.", None
        if plant.slot_index == destination:
            return False, "That plant is already in this space.", None
        occupants = [item for item in self.state.plants if item.slot_index == destination]
        if len(occupants) > 1:
            return False, "That garden space has conflicting plants and cannot be rearranged safely.", None
        affected = [plant] + occupants
        if len({item.plant_id for item in affected}) != len(affected):
            return False, "The selected plants could not be rearranged safely.", None
        before = {item.plant_id: item.slot_index for item in affected}
        origin = plant.slot_index
        plant.slot_index = destination
        if occupants:
            occupants[0].slot_index = origin
        after = {item.plant_id: item.slot_index for item in affected}
        try:
            self.storage.save()
        except Exception:
            for item in affected:
                item.slot_index = before[item.plant_id]
            return False, "The new arrangement could not be saved. Your plants stayed where they were.", None
        return True, "Plants moved.", PlacementChange(before=before, after=after)

    def restore_placement(self, change: PlacementChange) -> tuple[bool, str, Optional[PlacementChange]]:
        """Persist the inverse of the latest session-local placement change."""
        plants_by_id = {plant.plant_id: plant for plant in self.state.plants}
        if len(plants_by_id) != len(self.state.plants) or not change.before:
            return False, "That move can no longer be undone.", None
        affected = [plants_by_id.get(plant_id) for plant_id in change.before]
        if any(plant is None for plant in affected):
            return False, "That move can no longer be undone.", None
        current = {plant.plant_id: plant.slot_index for plant in affected if plant is not None}
        if current != change.after:
            return False, "The garden changed after that move, so it cannot be undone.", None
        for plant in affected:
            if plant is not None:
                plant.slot_index = change.before[plant.plant_id]
        try:
            self.storage.save()
        except Exception:
            for plant in affected:
                if plant is not None:
                    plant.slot_index = current[plant.plant_id]
            return False, "The previous arrangement could not be restored.", None
        inverse = PlacementChange(before=current, after=dict(change.before))
        return True, "Move undone.", inverse

    def _owned_species(self) -> set[str]:
        return {plant.species for plant in self.state.plants}

    def _next_unclaimed_milestone(self) -> Optional[int]:
        claimed = max(0, self.state.unlocked_slots - int(self.config.value("initial_slots", 2)))
        if claimed >= len(self.MILESTONE_REVIEWS):
            return None
        milestone = self.MILESTONE_REVIEWS[claimed]
        return milestone if self.state.total_reviews >= milestone else None

    def next_milestone(self) -> Optional[int]:
        claimed = max(0, self.state.unlocked_slots - int(self.config.value("initial_slots", 2)))
        if claimed >= len(self.MILESTONE_REVIEWS):
            return None
        return self.MILESTONE_REVIEWS[claimed]

    def _ensure_pending_milestone(self) -> Optional[MilestoneReward]:
        pending = self.state.pending_milestone_reward
        if pending is not None:
            valid_offers = [
                species for species in pending.offered_species
                if species in self.REWARD_SPECIES and species not in self._owned_species()
            ]
            if pending.review_count in self.MILESTONE_REVIEWS and valid_offers:
                pending.offered_species = valid_offers[:3]
                return pending
            self.state.pending_milestone_reward = None
        milestone = self._next_unclaimed_milestone()
        if milestone is None or self.state.unlocked_slots >= int(self.config.value("max_slots", 6)):
            return None
        offers = [species for species in self.REWARD_SPECIES if species not in self._owned_species()][:3]
        if not offers:
            return None
        self.state.pending_milestone_reward = MilestoneReward(milestone, offers)
        return self.state.pending_milestone_reward

    def pending_milestone(self) -> Optional[MilestoneReward]:
        return self._ensure_pending_milestone()

    def claim_milestone_reward(self, species: str) -> tuple[bool, str]:
        pending = self._ensure_pending_milestone()
        if pending is None:
            return False, "There is no garden reward ready to claim."
        if species not in pending.offered_species or species in self._owned_species():
            return False, "That plant is not available for this reward."
        max_slots = int(self.config.value("max_slots", 6))
        if self.state.unlocked_slots >= max_slots:
            return False, "Your garden is already full."
        slot_index = self.state.unlocked_slots
        used_ids = {plant.plant_id for plant in self.state.plants}
        next_id = slot_index + 1
        plant_id = f"plant_{next_id}"
        while plant_id in used_ids:
            next_id += 1
            plant_id = f"plant_{next_id}"
        plant = Plant(
            plant_id=plant_id,
            species=species,
            name=self._generated_name(species),
            slot_index=slot_index,
            personality=self.SPECIES_PERSONALITY.get(species, "balanced"),
            planted_on=self.state.daily_stats.day,
            memories=[PlantMemory("planted", "planted", self.state.daily_stats.day)],
        )
        snapshot = self._state_snapshot()
        self.state.unlocked_slots += 1
        self.state.plants.append(plant)
        self.state.inventory.setdefault("plants", [])
        if species not in self.state.inventory["plants"]:
            self.state.inventory["plants"].append(species)
        self.state.pending_milestone_reward = None
        self._ensure_pending_milestone()
        try:
            self._persist_or_restore(snapshot)
        except Exception:
            return False, "The new plant could not be saved. Your garden was not changed."
        return True, f"{plant.name} joined your garden."

    def apply_retrospective_reviews(self, reviews: list[Dict[str, Any]], *, latest_revlog_id: int = 0) -> int:
        if not reviews:
            return 0
        snapshot = self._state_snapshot()
        previous_reviews = self.state.total_reviews
        previous_streak = self.state.streak_days
        self.rollover_if_needed(persist=False)
        if self.state.daily_stats.reviewed == 0:
            self.state.streak_days += 1
            self.state.last_active_day = date.today().isoformat()
        total_growth = 0
        for review in reviews:
            queue, ease, deck_id, difficulty, lapse_count = self._normalized_review(review)
            is_correct = ease > 1
            stats = self.state.daily_stats
            stats.reviewed += 1
            self.state.total_reviews += 1
            if is_correct:
                stats.correct += 1
                self.state.total_correct += 1
                if lapse_count > 0:
                    stats.recovered_lapses += 1
            else:
                stats.wrong += 1
                self.state.total_wrong += 1
                stats.difficult_count += 1
            if queue == 0:
                card_type = "new"
                stats.new_count += 1
            elif queue in (1, 3):
                card_type = "learning"
                stats.learning_count += 1
            else:
                card_type = "review"
                stats.review_count += 1
            growth = self._calculate_growth(card_type, is_correct, difficulty, lapse_count, deck_id)
            if growth > 0:
                total_growth += self._award_growth(growth, deck_id)
        self._update_quests()
        self._record_shared_memories(previous_reviews, previous_streak)
        self._update_achievements()
        self._maybe_unlock_slot()
        self._update_weather()
        self.state.retrospective_last_revlog_id = max(
            self.state.retrospective_last_revlog_id,
            max(0, int(latest_revlog_id)),
        )
        self._persist_or_restore(snapshot)
        return total_growth

    def _update_achievements(self) -> None:
        stats = self.state.daily_stats
        checks = {
            "streak_7": self.state.streak_days >= 7,
            "streak_30": self.state.streak_days >= 30,
            "reviews_100_day": stats.reviewed >= 100,
            "reviews_1000_total": self.state.total_reviews >= 1000,
            "retention_90": stats.reviewed >= 20 and stats.accuracy >= 0.9,
            "retention_100": stats.reviewed >= 30 and stats.accuracy == 1.0,
            "all_due_done": stats.completed_due_cards,
            "no_lapse": stats.reviewed >= 40 and stats.wrong == 0,
        }
        for aid, achieved in checks.items():
            ach = self.state.achievements[aid]
            was_unlocked = ach.unlocked
            if achieved:
                ach.unlocked = True
                if not was_unlocked:
                    ach.unlocked_at = iso_now()
            ach.progress = 1.0 if ach.unlocked else 0.0

    def _maybe_unlock_slot(self) -> None:
        self._ensure_pending_milestone()

    def _update_weather(self) -> None:
        s = self.state.daily_stats
        if s.reviewed > 350 and s.accuracy < 0.72:
            self.state.selected_weather = "cloudy"
        elif s.wrong > s.correct and s.reviewed > 25:
            self.state.selected_weather = "cloudy"
        elif s.accuracy >= 0.9 and s.reviewed >= 50:
            self.state.selected_weather = "fireflies"
        elif s.reviewed >= 120:
            self.state.selected_weather = "sunny"
        else:
            self.state.selected_weather = "breeze"

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

    def resolve_plant_image(self, species: str, stage: str, rare: bool) -> Optional[str]:
        asset = self.resolve_plant_asset(species, stage, rare)
        return str(asset.path) if asset else None

    def resolve_plant_asset(self, species: str, stage: str, rare: bool) -> Optional[ResolvedAsset]:
        effective = "rare" if rare else stage
        return self.assets.resolve(
            "plants",
            f"{species}_{effective}",
            f"slot:plants:{species}:{effective}",
            theme=self.config.value("visual_theme", "verdant_dusk"),
        )

    def resolve_preview_assets(self, theme: str, weather: str, stage: str, quality_preference: str) -> dict[str, Any]:
        seasonal = self.seasonal_theme()
        normalized_theme = self.assets.normalize_theme(theme)
        background = self.assets.resolve(
            "backgrounds",
            f"bg_{seasonal}_{weather}",
            f"slot:backgrounds:{seasonal}:{weather}",
            theme=normalized_theme,
            quality_preference=quality_preference,
        )
        weather_overlay = self.assets.resolve(
            "weather",
            f"weather_{weather}",
            f"slot:weather:{weather}",
            theme=normalized_theme,
            quality_preference=quality_preference,
        )
        plants = {}
        for species in ("bonsai", "rose", "sunbloom"):
            asset = self.assets.resolve(
                "plants", f"{species}_{stage}", f"slot:plants:{species}:{stage}",
                theme=normalized_theme, quality_preference=quality_preference,
            )
            plants[species] = asset.to_payload() if asset else None
        return {
            "background": background.to_payload() if background else None,
            "weather": weather_overlay.to_payload() if weather_overlay else None,
            "plant": plants["rose"],
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
            theme=self.config.value("visual_theme", "verdant_dusk"),
        )

    def resolve_weather_overlay(self) -> Optional[str]:
        asset = self.resolve_weather_asset()
        return str(asset.path) if asset else None

    def resolve_weather_asset(self) -> Optional[ResolvedAsset]:
        return self.assets.resolve(
            "weather",
            f"weather_{self.state.selected_weather}",
            f"slot:weather:{self.state.selected_weather}",
            theme=self.config.value("visual_theme", "verdant_dusk"),
        )

    def resolve_decoration_image(self, decoration: str) -> Optional[str]:
        asset = self.resolve_decoration_asset(decoration)
        return str(asset.path) if asset else None

    def resolve_decoration_asset(self, decoration: str) -> Optional[ResolvedAsset]:
        return self.assets.resolve(
            "decorations",
            f"decor_{decoration}",
            f"slot:decorations:{decoration}",
            theme=self.config.value("visual_theme", "verdant_dusk"),
        )

    def reroll_asset_slot(self, slot: str) -> Optional[str]:
        if slot == "background":
            seasonal = self.seasonal_theme()
            weather = self.state.selected_weather
            path = self.assets.get_or_fetch(
                "backgrounds",
                f"bg_{seasonal}_{weather}",
                f"slot:backgrounds:{seasonal}:{weather}",
                theme=self.config.value("visual_theme", "verdant_dusk"),
                reroll=True,
            )
            return str(path) if path else None
        if slot == "weather":
            path = self.assets.get_or_fetch(
                "weather",
                f"weather_{self.state.selected_weather}",
                f"slot:weather:{self.state.selected_weather}",
                theme=self.config.value("visual_theme", "verdant_dusk"),
                reroll=True,
            )
            return str(path) if path else None
        first = self.state.plants[0] if self.state.plants else None
        if not first:
            return None
        effective = "rare" if first.rare_variant else first.growth_stage
        path = self.assets.get_or_fetch(
            "plants",
            f"{first.species}_{effective}",
            f"slot:plants:{first.species}:{effective}",
            theme=self.config.value("visual_theme", "verdant_dusk"),
            reroll=True,
        )
        return str(path) if path else None

    def export_progress_summary(self) -> str:
        payload = {
            "date": date.today().isoformat(),
            "streak": self.state.streak_days,
            "total_reviews": self.state.total_reviews,
            "garden_health": round(self.garden_health_index(), 2),
            "plants": [{"name": p.name, "species": p.species, "stage": p.growth_stage, "vitality": p.vitality} for p in self.state.plants],
        }
        return json.dumps(payload, indent=2)

    def garden_health_index(self) -> float:
        s = self.state.daily_stats
        vitality = sum(p.vitality for p in self.state.plants) / max(1, len(self.state.plants))
        recency = 1.0 if self.state.last_active_day == date.today().isoformat() else 0.75
        streak_factor = min(1.0, self.state.streak_days / 30)
        volume_factor = min(1.0, s.reviewed / 150)
        acc = s.accuracy if s.reviewed else 0.7
        return round((0.27 * vitality) + (0.23 * recency) + (0.2 * streak_factor) + (0.15 * volume_factor) + (0.15 * acc), 4)

    def _apply_streak_rollover(self, today: str) -> None:
        try:
            last = date.fromisoformat(self.state.last_active_day)
        except (TypeError, ValueError):
            last = date.fromisoformat(today)
        now = date.fromisoformat(today)
        missed = max(0, (now - last).days - 1)
        if missed > 0:
            self.state.streak_days = 0
            for plant in self.state.plants:
                plant.vitality = max(0.42, plant.vitality - (0.08 * missed))
        self.state.last_active_day = today
