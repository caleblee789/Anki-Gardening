from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

from .asset_manager import AssetManager, ResolvedAsset
from .models.state import Achievement, GardenState, Plant, Quest, SessionSummary, Snapshot, iso_now


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


class GardenGameEngine:
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
    SHOP_ITEMS = {
        "plants:cactus": 140,
        "plants:orchid": 220,
        "plants:moonflower": 280,
        "plants:sunbloom": 280,
        "plants:ivy": 200,
        "plants:fern": 180,
        "pots:charcoal_modern": 80,
        "backgrounds:zen_path": 120,
        "decorations:butterflies": 130,
        "weather:fireflies": 160,
        "sounds:rain_ambient": 140,
        "skins:winter_glass": 200,
    }
    WEEKLY_EVENTS = [
        {"event_id": "growth_festival", "name": "Growth Festival", "description": "Review growth +25%.", "growth_multiplier": 1.25, "quest_currency_bonus": 0, "shop_discount": 0.0, "weather_override": None},
        {"event_id": "dew_market", "name": "Dew Market", "description": "Shop 15% off.", "growth_multiplier": 1.0, "quest_currency_bonus": 0, "shop_discount": 0.15, "weather_override": None},
        {"event_id": "community_bloom", "name": "Community Bloom", "description": "Quests grant bonus currency.", "growth_multiplier": 1.0, "quest_currency_bonus": 4, "shop_discount": 0.0, "weather_override": "fireflies"},
        {"event_id": "storm_recovery", "name": "Storm Recovery", "description": "Recovery sessions get boosted.", "growth_multiplier": 1.1, "quest_currency_bonus": 2, "shop_discount": 0.0, "weather_override": "breeze"},
    ]

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
    RARE_EVENTS = [
        ("golden_bloom", "Golden Bloom: one random plant glows with extra growth."),
        ("rainfall_blessing", "Rainfall Blessing: vitality restoration is amplified today."),
        ("meteor_shower", "Meteor Shower: rare variant chance is elevated."),
        ("firefly_night", "Firefly Night: calm focus bonus tonight."),
        ("rainbow_morning", "Rainbow Morning: morning bonuses strengthened."),
        ("moonlit_garden", "Moonlit Garden: night species gain extra affinity."),
    ]

    def __init__(self, config: Any, storage: Any) -> None:
        self.config = config
        self.storage = storage
        self.state: GardenState = storage.state
        self._pending_stage_transitions: list[StageTransition] = []
        self.assets = AssetManager(config, storage)
        self._apply_weekly_event(force=True)
        self._ensure_achievements()
        self._ensure_daily_quests(force_refresh=False)

    def rollover_if_needed(self) -> None:
        today = date.today().isoformat()
        if self.state.daily_stats.day == today:
            return
        prev = self.state.daily_stats
        if prev.reviewed > 0:
            self._append_summary(prev)
            self._snapshot_if_needed(prev.day)
        self._apply_weekly_event(force=True)
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
        self.state.daily_stats.focus_sessions_completed = 0
        self._ensure_daily_quests(force_refresh=True)
        self._update_weather()
        self.storage.save()

    def register_review(self, review_payload: Dict[str, Any]) -> None:
        self.rollover_if_needed()
        today = self.state.daily_stats
        first_review_today = today.reviewed == 0
        if first_review_today:
            self.state.streak_days += 1
            self.state.last_active_day = date.today().isoformat()

        today.reviewed += 1
        self.state.total_reviews += 1

        queue = review_payload.get("queue", 2)
        ease = int(review_payload.get("ease", 1))
        deck_id = review_payload.get("deck_id")
        difficulty = float(review_payload.get("difficulty", 0.4))
        lapse_count = int(review_payload.get("lapse_count", 0))

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
        self._update_achievements()
        self._update_mastery()
        self._maybe_unlock_slot()
        self._update_weather()
        self.storage.save()

    def _calculate_growth(self, card_type: str, is_correct: bool, difficulty: float, lapse_count: int, deck_id: Optional[int]) -> int:
        mapping = self.config.value("points_per_card", {})
        base = float(mapping.get(card_type, 2))
        base *= float(self.current_weekly_event().get("growth_multiplier", 1.0))
        base *= float(self.config.value("correct_answer_bonus", 1.08) if is_correct else self.config.value("incorrect_answer_penalty", 0.6))

        accuracy_weight = 0.9 + (self.state.daily_stats.accuracy * 0.3)
        difficulty_weight = 1.0 + (difficulty * float(self.config.value("difficulty_weight", 0.12)))
        recovery_weight = 1.0 + (min(3, lapse_count) * float(self.config.value("recovery_weight", 0.2)))
        streak_weight = 1.0 + min(0.2, self.state.streak_days / 100)
        session_quality = self._session_quality_score()
        quality_weight = 0.9 + (session_quality * float(self.config.value("session_quality_weight", 0.25)))
        focus_mult = 1.0
        if self.state.focus_session.active:
            focus_mult = float(self.config.nested("focus_mode", "growth_multiplier", default=1.15))

        if self.config.value("time_of_day_bonus", True):
            hour = datetime.now().hour
            if hour <= 7:
                streak_weight += 0.05
            elif hour >= 22:
                streak_weight += 0.05

        if self.state.recovery_mode:
            recovery_weight += 0.15

        if self.state.exam_mode.enabled and deck_id is not None and deck_id in self.state.exam_mode.target_deck_ids:
            focus_mult *= float(self.config.nested("exam_mode", "deck_weight_boost", default=1.25))

        points = int(max(0, round(base * accuracy_weight * difficulty_weight * recovery_weight * streak_weight * quality_weight * focus_mult)))
        return points

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

    def _eligible_plants(self, deck_id: Optional[int]) -> list[Plant]:
        plants = self.state.plants
        if self.state.garden_mode == "deck-by-deck" and deck_id is not None:
            mapped = self.state.deck_plant_map.get(str(deck_id))
            if mapped:
                selected = [p for p in plants if p.plant_id == mapped]
                if selected:
                    return selected
        return plants

    def _apply_growth(self, growth: int, deck_id: Optional[int]) -> None:
        plants = self._eligible_plants(deck_id)
        if not plants:
            return
        base, remainder = divmod(max(0, int(growth)), len(plants))
        for index, plant in enumerate(plants):
            previous_stage = self._effective_stage(plant)
            plant.growth_points += base + (1 if index < remainder else 0)
            vitality_gain = 0.03 + (0.005 * self.state.mastery_tree.get("recovery", 0))
            plant.vitality = min(1.0, plant.vitality + vitality_gain)
            if plant.growth_stage == "flowering" and self.state.streak_days >= 10 and random.random() < 0.006:
                plant.rare_variant = True
            new_stage = self._effective_stage(plant)
            if new_stage != previous_stage:
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
        if metric == "focus":
            return stats.focus_sessions_completed
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

    def set_due_completion(self, completed: bool) -> None:
        self.state.daily_stats.completed_due_cards = completed
        self._update_achievements()
        self.storage.save()

    def set_journal_note(self, day: str, note: str) -> None:
        self.state.journal[day] = note.strip()
        self.storage.save()

    def assign_focus_plant(self, plant_id: Optional[str]) -> None:
        self.state.focus_plant_id = plant_id
        self.storage.save()

    def assign_deck_to_plant(self, deck_id: int, plant_id: str) -> None:
        self.state.deck_plant_map[str(deck_id)] = plant_id
        self.storage.save()

    def set_garden_mode(self, mode: str) -> None:
        self.state.garden_mode = "deck-by-deck" if mode == "deck-by-deck" else "unified"
        self.storage.save()

    def apply_retrospective_reviews(self, reviews: list[Dict[str, Any]]) -> int:
        if not reviews:
            return 0
        self.rollover_if_needed()
        total_growth = 0
        for review in reviews:
            ease = int(review.get("ease", 1))
            deck_id = review.get("deck_id")
            difficulty = float(review.get("difficulty", 0.45))
            lapse_count = int(review.get("lapse_count", 0))
            queue = int(review.get("queue", 2))
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
        self._update_achievements()
        self._update_mastery()
        self._maybe_unlock_slot()
        self._update_weather()
        self.storage.save()
        return total_growth

    def set_deck_difficulty(self, deck_id: int, weight: float) -> None:
        self.state.deck_difficulty_map[str(deck_id)] = max(0.6, min(weight, 2.0))
        self.storage.save()

    def start_focus_session(self, duration_minutes: int) -> tuple[bool, str]:
        if self.state.focus_session.active:
            return False, "Focus session already active."
        self.state.focus_session.active = True
        self.state.focus_session.duration_minutes = duration_minutes
        self.state.focus_session.started_at = iso_now()
        self.storage.save()
        return True, f"Focus session started for {duration_minutes} minutes."

    def complete_focus_session(self) -> tuple[bool, str]:
        fs = self.state.focus_session
        if not fs.active or not fs.started_at:
            return False, "No active focus session."
        started = datetime.fromisoformat(fs.started_at)
        elapsed = (datetime.now() - started).total_seconds() / 60
        fs.active = False
        fs.started_at = None
        if elapsed < fs.duration_minutes * 0.8:
            self.storage.save()
            return False, "Session ended early (no bonus)."
        self.state.daily_stats.focus_sessions_completed += 1
        self.state.total_focus_sessions += 1
        fs.deep_work_streak += 1
        bonus = 16 + (2 * fs.deep_work_streak)
        self.state.currency += 8
        self._award_growth(bonus, None)
        self._update_quests()
        self._update_achievements()
        self.storage.save()
        return True, "Deep work session complete. Bonus growth applied."

    def cancel_focus_session(self) -> None:
        self.state.focus_session.active = False
        self.state.focus_session.started_at = None
        self.storage.save()

    def configure_exam_mode(self, enabled: bool, exam_date: Optional[str], deck_ids: list[int]) -> None:
        self.state.exam_mode.enabled = enabled
        self.state.exam_mode.exam_date = exam_date
        self.state.exam_mode.target_deck_ids = deck_ids
        self.storage.save()

    def exam_countdown_days(self) -> Optional[int]:
        if not self.state.exam_mode.enabled or not self.state.exam_mode.exam_date:
            return None
        try:
            target = date.fromisoformat(self.state.exam_mode.exam_date)
            return (target - date.today()).days
        except Exception:
            return None

    def purchase_item(self, item_key: str) -> tuple[bool, str]:
        cost = self.SHOP_ITEMS.get(item_key)
        if cost is None:
            return False, "Item not found"
        if item_key in self.state.purchased_items:
            return False, "Already purchased"
        effective_cost = self.get_shop_price(item_key)
        if self.state.currency < effective_cost:
            return False, "Not enough currency"
        self.state.currency -= effective_cost
        self.state.purchased_items.append(item_key)
        category, item = item_key.split(":", 1)
        self.state.inventory.setdefault(category, [])
        if item not in self.state.inventory[category]:
            self.state.inventory[category].append(item)
        self.storage.save()
        return True, "Purchased"

    def current_weekly_event(self) -> Dict[str, Any]:
        if not self.config.nested("future_features", "enable_weekly_events", default=False):
            return {"event_id": "none", "name": "No Active Event", "description": "Weekly events disabled.", "growth_multiplier": 1.0, "quest_currency_bonus": 0, "shop_discount": 0.0, "weather_override": None}
        idx = date.today().isocalendar().week % len(self.WEEKLY_EVENTS)
        return self.WEEKLY_EVENTS[idx]

    def _apply_weekly_event(self, force: bool = False) -> None:
        event = self.current_weekly_event()
        today = date.today().isoformat()
        if force or self.state.weekly_event_applied_for_day != today:
            self.state.weekly_event_applied_for_day = today
            self.state.weekly_event_id = event["event_id"]

    def get_weekly_event_summary(self) -> str:
        event = self.current_weekly_event()
        return f"{event['name']}: {event['description']}"

    def get_shop_price(self, item_key: str) -> int:
        base = self.SHOP_ITEMS[item_key]
        discount = float(self.current_weekly_event().get("shop_discount", 0.0))
        return max(1, int(round(base * (1.0 - discount))))

    def set_gardener_name(self, name: str) -> None:
        cleaned = name.strip()
        if cleaned:
            self.state.gardener_name = cleaned[:40]
            self.storage.save()

    def add_plant_to_slot(self, species: str, slot_index: int) -> bool:
        if slot_index >= self.state.unlocked_slots:
            return False
        if any(p.slot_index == slot_index for p in self.state.plants):
            return False
        personality = self.SPECIES_PERSONALITY.get(species, "balanced")
        plant = Plant(plant_id=f"plant_{len(self.state.plants)+1}", species=species, name=species.capitalize(), slot_index=slot_index, personality=personality)
        self.state.plants.append(plant)
        self.storage.save()
        return True

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
        unlocked = self.state.unlocked_slots
        max_slots = self.config.value("max_slots", 6)
        if unlocked >= max_slots:
            return
        milestones = [250, 700, 1500, 2600, 4200]
        idx = unlocked - self.config.value("initial_slots", 2)
        if 0 <= idx < len(milestones) and self.state.total_reviews >= milestones[idx]:
            self.state.unlocked_slots += 1

    def _update_weather(self) -> None:
        s = self.state.daily_stats
        override = self.current_weekly_event().get("weather_override")
        if override:
            self.state.selected_weather = str(override)
        elif self.state.recovery_mode:
            self.state.selected_weather = "gentle_rain"
        elif s.reviewed > 350 and s.accuracy < 0.72:
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
            "currency": self.state.currency,
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

    def burnout_risk(self) -> bool:
        if not self.config.value("burnout_detection", True):
            return False
        s = self.state.daily_stats
        high_volume = s.reviewed >= self.config.value("burnout_volume_threshold", 500)
        low_quality = s.reviewed > 100 and s.accuracy < 0.72
        return bool(high_volume and low_quality)

    def _apply_streak_rollover(self, today: str) -> None:
        last = date.fromisoformat(self.state.last_active_day)
        now = date.fromisoformat(today)
        missed = max(0, (now - last).days - 1)
        grace = self.config.value("streak_grace_period_days", 1)
        if missed <= grace:
            self.state.recovery_mode = False
        elif missed > 0:
            if self.state.streak_freeze_tokens > 0:
                self.state.streak_freeze_tokens -= 1
            else:
                self.state.streak_days = max(0, self.state.streak_days - min(missed, 4))
                decay = float(self.config.value("vitality_decay_sensitivity", 0.08))
                if self.current_weekly_event()["event_id"] == "storm_recovery":
                    decay *= 0.6
                decay *= max(0.75, 1 - (0.05 * self.state.mastery_tree.get("recovery", 0)))
                for plant in self.state.plants:
                    plant.vitality = max(0.42, plant.vitality - decay * missed)
                self.state.recovery_mode = True
        self.state.last_active_day = today

    def _update_mastery(self) -> None:
        s = self.state.daily_stats
        if s.reviewed in {120, 360, 720, 1200}:
            self.state.mastery_tree["volume"] = min(10, self.state.mastery_tree["volume"] + 1)
        if s.accuracy >= 0.9 and s.reviewed in {30, 100, 250, 500}:
            self.state.mastery_tree["accuracy"] = min(10, self.state.mastery_tree["accuracy"] + 1)
        if s.reviewed == 1 and self.state.streak_days in {7, 14, 30, 60, 100}:
            self.state.mastery_tree["consistency"] = min(10, self.state.mastery_tree["consistency"] + 1)
        if self.state.recovery_mode and s.reviewed in {40, 100, 250}:
            self.state.mastery_tree["recovery"] = min(10, self.state.mastery_tree["recovery"] + 1)

    def _maybe_trigger_rare_event(self) -> None:
        if self.state.daily_stats.reviewed < 25:
            return
        chance = 0.005 * float(self.config.value("rare_event_frequency", 1.0))
        chance += 0.0005 * self.state.mastery_tree.get("consistency", 0)
        if random.random() > chance:
            return
        event_id, desc = random.choice(self.RARE_EVENTS)
        today = date.today().isoformat()
        if any(entry.startswith(f"{today}:") for entry in self.state.rare_event_log):
            return
        self.state.rare_event_log.append(f"{today}:{event_id}")
        self.state.currency += 10
        if event_id == "golden_bloom" and self.state.plants:
            random.choice(self.state.plants).growth_points += 24
        elif event_id == "rainfall_blessing":
            for p in self.state.plants:
                p.vitality = min(1.0, p.vitality + 0.08)
        elif event_id == "meteor_shower" and self.state.plants:
            if random.random() < 0.2:
                random.choice(self.state.plants).rare_variant = True
        self.state.recent_summaries.append(SessionSummary(day=today, summary=desc, quality_score=self._session_quality_score(), growth=self.state.daily_stats.growth_earned))

    def _append_summary(self, stats: Any) -> None:
        quality = self._session_quality_score()
        if self.state.recovery_mode and stats.reviewed >= 30:
            text = "Recovery day: steady effort revived your garden."
        elif quality >= 0.8:
            text = "Strong accuracy day: your garden responded with vibrant growth."
        elif self.burnout_risk():
            text = "Heavy workload detected: consider a lighter focus block tomorrow."
        else:
            text = "Consistent study keeps the garden healthy and resilient."
        self.state.recent_summaries.append(SessionSummary(day=stats.day, summary=text, quality_score=quality, growth=stats.growth_earned))
        self.state.recent_summaries = self.state.recent_summaries[-30:]

    def _snapshot_if_needed(self, snapshot_day: str) -> None:
        if not self.config.value("daily_snapshot", True):
            return
        every = int(self.config.value("snapshot_frequency_days", 1))
        if len(self.state.snapshots) > 0 and every > 1:
            if len(self.state.snapshots) % every != 0:
                return
        snap = Snapshot(
            day=snapshot_day,
            streak_days=self.state.streak_days,
            health_index=self.garden_health_index(),
            total_reviews=self.state.total_reviews,
            plant_stages={p.name: p.growth_stage for p in self.state.plants},
        )
        self.state.snapshots.append(snap)
        self.state.snapshots = self.state.snapshots[-180:]

    def _passive_daily_reward(self) -> None:
        today = date.today().isoformat()
        if today in self.state.passive_reward_days:
            return
        self.state.passive_reward_days.append(today)
        self.state.currency += 2
