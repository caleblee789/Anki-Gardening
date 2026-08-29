#!/usr/bin/env python3
"""Reproducible 365-Anki-day balance report for Anki Garden.

This model is intentionally bounded. It exercises production Garden Find odds,
environment discovery rules, Growth thresholds, reward values, and catalog
prices without opening Anki. It is not a scheduler emulator.

Scenario assumptions
--------------------

* Every simulated day is active and all of that day's cards are completed.
* The player starts with a free Bonsai and the two included beds.
* Purchases happen at the end of each day in this fixed order: remaining plant
  species, beds, purchasable Weather, then purchasable Scenery. Consumables are
  never purchased.
* Purchased plants are immediately available as the next nurture target.
* Find consumables and Full Bloom Charges are used automatically whenever a
  plant can receive them. The 365-day baseline models one continuous daily
  session at 100 cards/hour. Rich Compost uses the proposed one-hour wall-clock
  timer; Booster Potion remains card-counted.
* Discovered environments are recorded but are not equipped in the baseline.
  Their isolated Growth-equivalent value is reported separately.
* The six-bed projection isolates Shared Growth. It excludes Finds,
  consumables, and environments so the bed multiplier remains legible.

Run from the repository root:

    .venv/bin/python scripts/simulate_balance_profiles.py
    .venv/bin/python scripts/simulate_balance_profiles.py --json
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.achievements import ACHIEVEMENTS_BY_ID
from ankigarden.environment import SCENERY_CATALOG, WEATHER_CATALOG
from ankigarden.game import GardenGameEngine
from ankigarden.garden_finds import (
    ENVIRONMENT_TIER_RULES,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_DAILY_CAP,
    resolve_environment_find,
    resolve_standard_find,
    stable_answer_event_identity,
)
from ankigarden.growth import GROWTH_STAGES, GROWTH_THRESHOLDS


SIMULATION_DAYS = 365
PROFILE_CARDS_PER_DAY = (25, 50, 100, 200, 400)
REVIEW_SPEEDS_CARDS_PER_HOUR = (30, 100, 300)
BASELINE_CARDS_PER_HOUR = 100
GROWTH_UNITS_PER_POINT = 100
FULL_BLOOM_UNITS = GROWTH_THRESHOLDS[-1] * GROWTH_UNITS_PER_POINT
MAX_PLANTS = len(GardenGameEngine.SPECIES_PRICES)


@dataclass(frozen=True)
class PurchaseTarget:
    category: str
    item_id: str
    price: int


@dataclass(frozen=True)
class FindReport:
    total: int
    average_per_day: float
    maximum_per_day: int
    maximum_attempted_card_gap: int
    reward_counts: Mapping[str, int]


@dataclass(frozen=True)
class ConsumableReport:
    acquired: Mapping[str, int]
    used: Mapping[str, int]
    inventory_remaining: Mapping[str, int]
    effect_cards_remaining: Mapping[str, int]
    timed_effect_seconds_remaining: Mapping[str, int]
    growth_added: Mapping[str, int]


@dataclass(frozen=True)
class SixBedReport:
    passive_plants_at_start: int
    output_percent_while_growth_available: int
    first_full_bloom_day: int | None
    all_six_full_bloom_day: int | None
    plants_in_full_bloom_after_365_days: int


@dataclass(frozen=True)
class EnvironmentDiscoveryReport:
    observed_unlock_day: Mapping[str, int]
    remaining_unowned: tuple[str, ...]


@dataclass(frozen=True)
class ProfileReport:
    cards_per_day: int
    cards_completed: int
    first_plant_stage_days: Mapping[str, int | None]
    first_plant_stage_cards: Mapping[str, int | None]
    first_plant_full_bloom_day: int | None
    plants_in_full_bloom: int
    stored_growth: float
    finds: FindReport
    coins_by_source: Mapping[str, int]
    gross_coins: int
    ending_coins_after_modeled_purchases: int
    completion_reward_share_percent: float
    purchase_completion_day: Mapping[str, int | None]
    consumables: ConsumableReport
    environment_discoveries: EnvironmentDiscoveryReport
    six_bed_garden: SixBedReport
    maximum_random_environment_advantage_percent: float


@dataclass(frozen=True)
class PityReport:
    tier: str
    median_cards_to_next_item: int
    force_threshold_cards: int
    cards_to_force_two_items_without_cross_tier_preemption: int
    median_days_by_profile: Mapping[int, int]
    force_days_by_profile: Mapping[int, int]


@dataclass(frozen=True)
class TimedFertilizerValueReport:
    tier: str
    growth_per_card: int
    duration_hours: int
    price: int
    growth_by_speed: Mapping[int, int]
    growth_per_coin_by_speed: Mapping[int, float]


@dataclass(frozen=True)
class BalanceReport:
    days: int
    assumptions: tuple[str, ...]
    profiles: tuple[ProfileReport, ...]
    environment_pity: tuple[PityReport, ...]
    environment_growth_equivalent_at_100_cards: Mapping[str, float]
    timed_fertilizer_value: tuple[TimedFertilizerValueReport, ...]


TIMED_FERTILIZER_PROPOSAL = {
    "Basic": (1, 1, 30),
    "Quality": (2, 2, 100),
    "Magical": (3, 4, 300),
}


def _purchase_plan() -> tuple[PurchaseTarget, ...]:
    species = tuple(
        PurchaseTarget("all species", species_id, price)
        for species_id, price in GardenGameEngine.SPECIES_PRICES.items()
        if species_id != "bonsai"
    )
    beds = tuple(
        PurchaseTarget("all beds", f"bed_{current + 1}", price)
        for current, price in sorted(GardenGameEngine.BED_PRICES.items())
    )
    weather = tuple(
        PurchaseTarget("purchasable Weather", item.item_id, int(item.price or 0))
        for item in WEATHER_CATALOG.values()
        if item.price is not None
    )
    scenery = tuple(
        PurchaseTarget("purchasable Scenery", item.item_id, int(item.price or 0))
        for item in SCENERY_CATALOG.values()
        if item.price is not None
    )
    return (*species, *beds, *weather, *scenery)


PURCHASE_PLAN = _purchase_plan()
PURCHASE_CATEGORIES = tuple(dict.fromkeys(item.category for item in PURCHASE_PLAN))


def _streak_bonus_percent(day: int) -> int:
    return GardenGameEngine.streak_bonus_percent(day)


def _card_growth_units(day: int) -> int:
    base = GardenGameEngine.BASE_GROWTH_PER_REVIEW * GROWTH_UNITS_PER_POINT
    return base + (base * _streak_bonus_percent(day)) // 100


def _stage_crossings() -> tuple[tuple[int, str, int], ...]:
    rows: list[tuple[int, str, int]] = []
    for index in range(len(GROWTH_STAGES) - 1):
        start = GROWTH_THRESHOLDS[index]
        end = GROWTH_THRESHOLDS[index + 1]
        next_stage = GROWTH_STAGES[index + 1]
        split = GardenGameEngine.STAGE_REWARD_SPLITS[next_stage]
        for order, percent in enumerate((25, 50, 75)):
            point = start + math.ceil((end - start) * percent / 100)
            rows.append((point * GROWTH_UNITS_PER_POINT, "checkpoint", split[order]))
        rows.append((end * GROWTH_UNITS_PER_POINT, next_stage, split[3]))
    return tuple(sorted(rows))


STAGE_CROSSINGS = _stage_crossings()


class _ProfileModel:
    """Small deterministic state machine for one fixed-volume profile."""

    def __init__(self, cards_per_day: int) -> None:
        self.cards_per_day = int(cards_per_day)
        self.total_cards = 0
        self.coins = 0
        self.coins_by_source: Counter[str] = Counter()
        self.plant_growth_units: list[int] = [0]
        self.active_plant_index = 0
        self.stored_growth_units = 0
        self.first_plant_stage_days: dict[str, int | None] = {
            stage: None for stage in GROWTH_STAGES[1:]
        }
        self.first_plant_stage_cards: dict[str, int | None] = {
            stage: None for stage in GROWTH_STAGES[1:]
        }
        self.full_bloom_count = 0
        self.full_bloom_days: list[int] = []
        self.purchase_index = 0
        self.purchase_days: dict[str, int] = {}
        self.category_purchase_day: dict[str, int | None] = {
            category: None for category in PURCHASE_CATEGORIES
        }
        self.standard_drought = 0
        self.finds_today = 0
        self.finds_per_day: list[int] = []
        self.find_reward_counts: Counter[str] = Counter()
        self.maximum_attempted_card_gap = 0
        self.environment_pity: dict[str, int] = {
            "rare_environment": 0,
            "very_rare_environment": 0,
            "ultra_environment": 0,
        }
        self.owned_environments: set[str] = set()
        self.environment_unlock_day: dict[str, int] = {}
        self.consumable_acquired: Counter[str] = Counter()
        self.consumable_used: Counter[str] = Counter()
        self.consumable_inventory: Counter[str] = Counter()
        self.consumable_growth: Counter[str] = Counter()
        self.fertilizer_seconds_remaining = 0.0
        self.fertilizer_active_doses = 0
        self.booster_batches: list[int] = []

    @property
    def has_target(self) -> bool:
        return self.active_plant_index < len(self.plant_growth_units)

    def _credit(self, source: str, amount: int) -> None:
        value = max(0, int(amount))
        self.coins += value
        self.coins_by_source[str(source)] += value

    def _stage_rewards_between(
        self,
        before_units: int,
        after_units: int,
        *,
        plant_index: int,
        day: int,
    ) -> int:
        coins = 0
        for threshold_units, crossing_kind, reward in STAGE_CROSSINGS:
            if before_units < threshold_units <= after_units:
                coins += reward
                if plant_index == 0 and crossing_kind in GROWTH_STAGES[1:]:
                    self.first_plant_stage_days[crossing_kind] = day
                    self.first_plant_stage_cards[crossing_kind] = self.total_cards
        return coins

    def _route_growth_once(self, growth_units: int, day: int) -> int:
        remaining = max(0, int(growth_units))
        completed = 0
        while remaining > 0 and self.has_target:
            index = self.active_plant_index
            before = self.plant_growth_units[index]
            applied = min(remaining, FULL_BLOOM_UNITS - before)
            after = before + applied
            self.plant_growth_units[index] = after
            remaining -= applied
            stage_coins = self._stage_rewards_between(
                before,
                after,
                plant_index=index,
                day=day,
            )
            if stage_coins:
                self._credit("plant milestones", stage_coins)
            if after >= FULL_BLOOM_UNITS:
                self.active_plant_index += 1
                self.full_bloom_count += 1
                self.full_bloom_days.append(day)
                completed += 1
            else:
                break
        if remaining:
            self.stored_growth_units += remaining
        return completed

    def _route_growth(self, growth_units: int, day: int, source: str) -> None:
        pending = [max(0, int(growth_units))]
        while pending:
            award = pending.pop(0)
            if award <= 0:
                continue
            if source:
                self.consumable_growth[source] += award // GROWTH_UNITS_PER_POINT
            completed = self._route_growth_once(award, day)
            for _ in range(completed):
                # Full Bloom grants one Small Growth Charge. The scenario's
                # auto-use policy consumes it immediately without losing value.
                item_id = "growth_charge_small"
                self.consumable_acquired[item_id] += 1
                self.consumable_used[item_id] += 1
                pending.append(100 * GROWTH_UNITS_PER_POINT)
                self.consumable_growth["Full Bloom Charges"] += 100

    def _drain_stored_growth(self, day: int) -> None:
        if not self.has_target or self.stored_growth_units <= 0:
            return
        stored = self.stored_growth_units
        self.stored_growth_units = 0
        self._route_growth(stored, day, "")

    def _activate_waiting_effects(self) -> None:
        if not self.has_target:
            return
        while (
            self.consumable_inventory["fertilizer_basic"] > 0
            and self.fertilizer_active_doses < GardenGameEngine.EFFECT_DOSE_CAP
        ):
            self.consumable_inventory["fertilizer_basic"] -= 1
            self.consumable_used["fertilizer_basic"] += 1
            self.fertilizer_seconds_remaining += 60 * 60
            self.fertilizer_active_doses += 1
        while (
            self.consumable_inventory["booster_potion"] > 0
            and len(self.booster_batches) < GardenGameEngine.EFFECT_DOSE_CAP
        ):
            self.consumable_inventory["booster_potion"] -= 1
            self.consumable_used["booster_potion"] += 1
            self.booster_batches.append(GardenGameEngine.BOOSTER_CARD_COUNT)

    @staticmethod
    def _consume_effect_batch(batches: list[int]) -> bool:
        if not batches:
            return False
        batches[0] -= 1
        if batches[0] <= 0:
            batches.pop(0)
        return True

    def _grant_consumable(self, item_id: str, day: int) -> None:
        normalized = str(item_id)
        self.consumable_acquired[normalized] += 1
        if normalized == "growth_charge_small":
            self.consumable_used[normalized] += 1
            self._route_growth(100 * GROWTH_UNITS_PER_POINT, day, "Small Charges")
            return
        if normalized == "growth_charge_standard":
            self.consumable_used[normalized] += 1
            self._route_growth(500 * GROWTH_UNITS_PER_POINT, day, "Standard Charges")
            return
        self.consumable_inventory[normalized] += 1
        self._activate_waiting_effects()

    def _process_standard_find(self, day: int) -> None:
        identity = stable_answer_event_identity(self.total_cards)
        decision = resolve_standard_find(
            secret=f"anki-garden-balance-v2:{self.cards_per_day}",
            answer_identity=identity,
            drought_misses=self.standard_drought,
            finds_today=self.finds_today,
            growth_available=self.has_target,
        )
        self.standard_drought = decision.next_drought_misses
        if decision.drought_answer_number is not None:
            self.maximum_attempted_card_gap = max(
                self.maximum_attempted_card_gap,
                decision.drought_answer_number,
            )
        reward = decision.reward
        if not decision.hit or reward is None:
            return
        self.finds_today += 1
        self.find_reward_counts[reward.reward_id] += 1
        if reward.reward_kind == "coins":
            self._credit("Garden Finds", reward.amount)
        elif reward.reward_kind == "growth":
            self._route_growth(
                reward.amount * GROWTH_UNITS_PER_POINT,
                day,
                "Instant Growth Finds",
            )
        elif reward.inventory_item_id:
            for _ in range(reward.amount):
                self._grant_consumable(reward.inventory_item_id, day)

    def _process_environment_find(self, day: int) -> None:
        identity = stable_answer_event_identity(self.total_cards)
        decision = resolve_environment_find(
            secret=f"anki-garden-balance-v2:{self.cards_per_day}",
            answer_identity=identity,
            owned_environment_ids=self.owned_environments,
            tier_pity_misses=self.environment_pity,
        )
        self.environment_pity = dict(decision.next_tier_pity_misses)
        if not decision.hit or decision.item is None:
            return
        item = decision.item
        self.owned_environments.add(item.item_id)
        self.owned_environments.add(item.ownership_key)
        self.environment_unlock_day[item.item_id] = day

    def _achievement_rewards_at_day_start(self, day: int) -> None:
        if day == 7:
            self._credit(
                "one-time achievements",
                ACHIEVEMENTS_BY_ID["streak_7"].reward.coins,
            )
        elif day % 7 == 0:
            self._credit("seven-day streak cycles", GardenGameEngine.WEEKLY_STREAK_COINS)

        achievement_id = {30: "streak_30", 100: "streak_100", 365: "streak_365"}.get(day)
        if achievement_id:
            reward = ACHIEVEMENTS_BY_ID[achievement_id].reward
            self._credit("one-time achievements", reward.coins)
            for _ in range(reward.small_growth_charges):
                self._grant_consumable("growth_charge_small", day)
            for _ in range(reward.standard_growth_charges):
                self._grant_consumable("growth_charge_standard", day)

        if day == 1 and self.cards_per_day >= 100:
            self._credit(
                "one-time achievements",
                ACHIEVEMENTS_BY_ID["reviews_100_day"].reward.coins,
            )

    def _buy_available_items(self, day: int) -> None:
        while self.purchase_index < len(PURCHASE_PLAN):
            item = PURCHASE_PLAN[self.purchase_index]
            if self.coins < item.price:
                break
            self.coins -= item.price
            self.purchase_days[f"{item.category}:{item.item_id}"] = day
            self.purchase_index += 1
            if item.category == "all species":
                self.plant_growth_units.append(0)
                self._drain_stored_growth(day)
                self._activate_waiting_effects()
            category_items = [row for row in PURCHASE_PLAN if row.category == item.category]
            purchased_in_category = sum(
                1 for key in self.purchase_days if key.startswith(f"{item.category}:")
            )
            if purchased_in_category == len(category_items):
                self.category_purchase_day[item.category] = day

    def run(self) -> ProfileReport:
        for day in range(1, SIMULATION_DAYS + 1):
            self.finds_today = 0
            # The proposed Fertilizer uses wall-clock time. A dose left over
            # after one daily session expires before the following day.
            self.fertilizer_seconds_remaining = 0.0
            self.fertilizer_active_doses = 0
            self._activate_waiting_effects()
            self._credit("first card", GardenGameEngine.DAILY_ACTIVITY_COINS)
            self._achievement_rewards_at_day_start(day)
            for _card in range(self.cards_per_day):
                self.total_cards += 1
                self._activate_waiting_effects()
                growth_units = _card_growth_units(day)
                if self.has_target and self.fertilizer_seconds_remaining > 0:
                    growth_units += GROWTH_UNITS_PER_POINT
                    self.consumable_growth["Rich Compost"] += 1
                    self.fertilizer_seconds_remaining = max(
                        0.0,
                        self.fertilizer_seconds_remaining
                        - (60 * 60 / BASELINE_CARDS_PER_HOUR),
                    )
                    if self.fertilizer_seconds_remaining <= 0:
                        self.fertilizer_active_doses = 0
                if self.has_target and self.booster_batches:
                    growth_units += (
                        GardenGameEngine.BOOSTER_GROWTH_PER_ANSWER
                        * GROWTH_UNITS_PER_POINT
                    )
                    self.consumable_growth["Booster Potions"] += (
                        GardenGameEngine.BOOSTER_GROWTH_PER_ANSWER
                    )
                    self._consume_effect_batch(self.booster_batches)
                self._route_growth(growth_units, day, "")
                self._process_standard_find(day)
                self._process_environment_find(day)
                if self.total_cards == 1_000:
                    deep_roots = ACHIEVEMENTS_BY_ID["reviews_1000_total"].reward
                    for _ in range(deep_roots.standard_growth_charges):
                        self._grant_consumable("growth_charge_standard", day)

            self.finds_per_day.append(self.finds_today)
            self._credit("Today’s Cards", GardenGameEngine.ALL_DUE_BASE_COINS)
            if day == 1:
                self._credit(
                    "one-time achievements",
                    ACHIEVEMENTS_BY_ID["all_due_done"].reward.coins,
                )
            self._buy_available_items(day)

        acquired = dict(sorted(self.consumable_acquired.items()))
        used = dict(sorted(self.consumable_used.items()))
        inventory = {
            item_id: max(0, int(self.consumable_inventory[item_id]))
            for item_id in sorted(set(acquired) | set(self.consumable_inventory))
        }
        effect_cards = {
            "booster_potion": sum(self.booster_batches),
        }
        total_finds = sum(self.find_reward_counts.values())
        gross_coins = sum(self.coins_by_source.values())
        completion_coins = self.coins_by_source["Today’s Cards"]
        unowned = tuple(
            item.item_id
            for item in SPECIAL_ENVIRONMENT_POOL
            if item.item_id not in self.owned_environments
        )
        return ProfileReport(
            cards_per_day=self.cards_per_day,
            cards_completed=self.total_cards,
            first_plant_stage_days=dict(self.first_plant_stage_days),
            first_plant_stage_cards=dict(self.first_plant_stage_cards),
            first_plant_full_bloom_day=self.first_plant_stage_days.get("rare"),
            plants_in_full_bloom=self.full_bloom_count,
            stored_growth=round(self.stored_growth_units / GROWTH_UNITS_PER_POINT, 2),
            finds=FindReport(
                total=total_finds,
                average_per_day=round(total_finds / SIMULATION_DAYS, 3),
                maximum_per_day=max(self.finds_per_day, default=0),
                maximum_attempted_card_gap=self.maximum_attempted_card_gap,
                reward_counts=dict(sorted(self.find_reward_counts.items())),
            ),
            coins_by_source=dict(sorted(self.coins_by_source.items())),
            gross_coins=gross_coins,
            ending_coins_after_modeled_purchases=self.coins,
            completion_reward_share_percent=round(
                100.0 * completion_coins / gross_coins, 2
            ),
            purchase_completion_day={
                **self.category_purchase_day,
                "all modeled Coin unlocks": (
                    max(self.purchase_days.values())
                    if len(self.purchase_days) == len(PURCHASE_PLAN)
                    else None
                ),
            },
            consumables=ConsumableReport(
                acquired=acquired,
                used=used,
                inventory_remaining=inventory,
                effect_cards_remaining=effect_cards,
                timed_effect_seconds_remaining={
                    "fertilizer_basic": int(round(self.fertilizer_seconds_remaining)),
                },
                growth_added=dict(sorted(self.consumable_growth.items())),
            ),
            environment_discoveries=EnvironmentDiscoveryReport(
                observed_unlock_day=dict(sorted(self.environment_unlock_day.items())),
                remaining_unowned=unowned,
            ),
            six_bed_garden=_simulate_six_beds(self.cards_per_day),
            maximum_random_environment_advantage_percent=round(
                max(_environment_advantage_percent(self.cards_per_day).values()),
                2,
            ),
        )


def _route_across_plants(
    plants: list[int],
    growth_units: int,
    *,
    start_index: int,
) -> None:
    remaining = max(0, int(growth_units))
    ordered = [
        index
        for offset in range(len(plants))
        if plants[(index := (start_index + offset) % len(plants))] < FULL_BLOOM_UNITS
    ]
    for index in ordered:
        if remaining <= 0:
            break
        applied = min(remaining, FULL_BLOOM_UNITS - plants[index])
        plants[index] += applied
        remaining -= applied


def _simulate_six_beds(cards_per_day: int) -> SixBedReport:
    plants = [0] * 6
    first_day: int | None = None
    all_day: int | None = None
    for day in range(1, SIMULATION_DAYS + 1):
        for _card in range(cards_per_day):
            unfinished = [
                index for index, growth in enumerate(plants)
                if growth < FULL_BLOOM_UNITS
            ]
            if not unfinished:
                break
            active = unfinished[0]
            award = _card_growth_units(day)
            _route_across_plants(plants, award, start_index=active)
            shared_award = award // GardenGameEngine.PASSIVE_GROWTH_DENOMINATOR

            # Every other planted plant creates one 20% share. An unfinished
            # plant receives its own share. Shares belonging to Full Bloom
            # plants are divided exactly among the unfinished snapshot,
            # including the active plant, so all six beds continue producing
            # 200% total garden Growth while any target remains.
            unfinished_others = tuple(
                index for index in unfinished if index != active
            )
            full_bloom_others = tuple(
                index for index in range(len(plants))
                if index != active and index not in unfinished_others
            )
            for recipient in unfinished_others:
                _route_across_plants(plants, shared_award, start_index=recipient)
            redistributed = shared_award * len(full_bloom_others)
            if redistributed:
                per_recipient, remainder = divmod(redistributed, len(unfinished))
                for position, recipient in enumerate(unfinished):
                    exact_share = per_recipient + (1 if position < remainder else 0)
                    _route_across_plants(
                        plants,
                        exact_share,
                        start_index=recipient,
                    )
            completed = sum(growth >= FULL_BLOOM_UNITS for growth in plants)
            if completed and first_day is None:
                first_day = day
            if completed == len(plants):
                all_day = day
                break
        if all_day is not None:
            break
    return SixBedReport(
        passive_plants_at_start=5,
        output_percent_while_growth_available=200,
        first_full_bloom_day=first_day,
        all_six_full_bloom_day=all_day,
        plants_in_full_bloom_after_365_days=sum(
            growth >= FULL_BLOOM_UNITS for growth in plants
        ),
    )


def _environment_growth_equivalent(cards_per_day: int) -> dict[str, float]:
    cards = max(1, int(cards_per_day))
    return {
        "Firefly Evening": float(min(cards, 15) * 5),
        "Rainbow Horizon": float(min(cards, 100)),
        "Rainbow Sunshower": 100.0,
        # 85% Small Charge, 10% Standard Charge, 5% base Booster value.
        "Halloween Garden": 0.85 * 100 + 0.10 * 500 + 0.05 * 500,
        # Every fourth completion grants a 125-card Booster while equipped.
        "Full Moon Garden": (125 * 5) / 4,
        "Celestial Eclipse": float(min(cards, 100) * 2),
    }


def _environment_advantage_percent(cards_per_day: int) -> dict[str, float]:
    baseline = max(1, int(cards_per_day)) * GardenGameEngine.BASE_GROWTH_PER_REVIEW
    return {
        name: value * 100.0 / baseline
        for name, value in _environment_growth_equivalent(cards_per_day).items()
    }


def _environment_pity_report() -> tuple[PityReport, ...]:
    reports: list[PityReport] = []
    for tier, rule in ENVIRONMENT_TIER_RULES.items():
        probability = 1.0 / rule.base_denominator
        median_cards = min(
            rule.hard_pity_answers,
            math.ceil(math.log(0.5) / math.log1p(-probability)),
        )
        reports.append(PityReport(
            tier=tier,
            median_cards_to_next_item=median_cards,
            force_threshold_cards=rule.hard_pity_answers,
            cards_to_force_two_items_without_cross_tier_preemption=(
                2 * rule.hard_pity_answers
            ),
            median_days_by_profile={
                profile: math.ceil(median_cards / profile)
                for profile in PROFILE_CARDS_PER_DAY
            },
            force_days_by_profile={
                profile: math.ceil(rule.hard_pity_answers / profile)
                for profile in PROFILE_CARDS_PER_DAY
            },
        ))
    return tuple(reports)


def _timed_fertilizer_value_report() -> tuple[TimedFertilizerValueReport, ...]:
    reports: list[TimedFertilizerValueReport] = []
    for tier, (growth_per_card, duration_hours, price) in TIMED_FERTILIZER_PROPOSAL.items():
        growth_by_speed = {
            speed: growth_per_card * duration_hours * speed
            for speed in REVIEW_SPEEDS_CARDS_PER_HOUR
        }
        reports.append(TimedFertilizerValueReport(
            tier=tier,
            growth_per_card=growth_per_card,
            duration_hours=duration_hours,
            price=price,
            growth_by_speed=growth_by_speed,
            growth_per_coin_by_speed={
                speed: growth / price
                for speed, growth in growth_by_speed.items()
            },
        ))
    return tuple(reports)


ASSUMPTIONS = (
    "365 consecutive active Anki days; every day’s cards are completed.",
    "Free Bonsai and two included beds at the start.",
    "End-of-day purchase order: species, beds, purchasable Weather, purchasable Scenery.",
    "Find and Full Bloom consumables are automatically used; no consumables are purchased.",
    "The baseline session runs at 100 cards/hour; Rich Compost lasts one wall-clock hour.",
    "Discovered environments are not equipped in baseline progression.",
    "Six-bed results isolate Shared Growth from Finds, consumables, and environments.",
)


def simulate_profiles(
    profiles: Iterable[int] = PROFILE_CARDS_PER_DAY,
) -> BalanceReport:
    normalized = tuple(int(profile) for profile in profiles)
    if not normalized or any(profile <= 0 for profile in normalized):
        raise ValueError("profiles must contain positive cards-per-day values")
    return BalanceReport(
        days=SIMULATION_DAYS,
        assumptions=ASSUMPTIONS,
        profiles=tuple(_ProfileModel(profile).run() for profile in normalized),
        environment_pity=_environment_pity_report(),
        environment_growth_equivalent_at_100_cards=_environment_growth_equivalent(100),
        timed_fertilizer_value=_timed_fertilizer_value_report(),
    )


def _day(value: int | None) -> str:
    return "—" if value is None else str(value)


def _markdown_table(headers: tuple[str, ...], rows: Iterable[Iterable[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(report: BalanceReport) -> str:
    lines = [
        "# Anki Garden 365-day balance simulation",
        "",
        "## Assumptions",
        "",
        *(f"- {assumption}" for assumption in report.assumptions),
        "",
        "## Progression and Finds",
        "",
        _markdown_table(
            (
                "Cards/day", "Sprout", "Young", "Mature", "Flowering",
                "Full Bloom", "Finds/day", "Longest attempted-card Find gap",
            ),
            (
                (
                    profile.cards_per_day,
                    _day(profile.first_plant_stage_days["sprout"]),
                    _day(profile.first_plant_stage_days["young"]),
                    _day(profile.first_plant_stage_days["mature"]),
                    _day(profile.first_plant_stage_days["flowering"]),
                    _day(profile.first_plant_full_bloom_day),
                    f"{profile.finds.average_per_day:.2f}",
                    profile.finds.maximum_attempted_card_gap,
                )
                for profile in report.profiles
            ),
        ),
        "",
        "## Economy",
        "",
        _markdown_table(
            (
                "Cards/day", "Gross Coins", "Today’s Cards share",
                "All species", "All beds", "Weather", "Scenery", "All Coin unlocks",
            ),
            (
                (
                    profile.cards_per_day,
                    profile.gross_coins,
                    f"{profile.completion_reward_share_percent:.1f}%",
                    _day(profile.purchase_completion_day["all species"]),
                    _day(profile.purchase_completion_day["all beds"]),
                    _day(profile.purchase_completion_day["purchasable Weather"]),
                    _day(profile.purchase_completion_day["purchasable Scenery"]),
                    _day(profile.purchase_completion_day["all modeled Coin unlocks"]),
                )
                for profile in report.profiles
            ),
        ),
        "",
        "Purchase days follow the fixed collection-first policy above; drop-only environments use the discovery table below.",
        "",
        "## Six-bed Shared Growth",
        "",
        _markdown_table(
            ("Cards/day", "Passive plants", "Garden output while growing", "First Full Bloom", "All six Full Bloom", "Full Bloom after 365 days"),
            (
                (
                    profile.cards_per_day,
                    profile.six_bed_garden.passive_plants_at_start,
                    f"{profile.six_bed_garden.output_percent_while_growth_available}%",
                    _day(profile.six_bed_garden.first_full_bloom_day),
                    _day(profile.six_bed_garden.all_six_full_bloom_day),
                    profile.six_bed_garden.plants_in_full_bloom_after_365_days,
                )
                for profile in report.profiles
            ),
        ),
        "",
        "## Environment discovery",
        "",
        _markdown_table(
            ("Tier", "Median cards to next item", "Force threshold in cards", "Days at 25/day", "Days at 50/day", "Days at 100/day", "Days at 200/day", "Days at 400/day"),
            (
                (
                    pity.tier.replace("_environment", "").replace("_", " ").title(),
                    pity.median_cards_to_next_item,
                    pity.force_threshold_cards,
                    *(pity.force_days_by_profile[profile] for profile in PROFILE_CARDS_PER_DAY),
                )
                for pity in report.environment_pity
            ),
        ),
        "",
        "The day columns show the nominal force threshold. The current one-item-per-card resolver can pre-empt a forced lower tier when a rarer tier wins on the same card; therefore those lower-tier values are not yet strict calendar-card maxima.",
        "",
        "## Timed Fertilizer value",
        "",
        _markdown_table(
            (
                "Tier", "Effect", "Price", "30 cards/hour", "100 cards/hour",
                "300 cards/hour",
            ),
            (
                (
                    fertilizer.tier,
                    f"+{fertilizer.growth_per_card} for {fertilizer.duration_hours}h",
                    fertilizer.price,
                    f"{fertilizer.growth_by_speed[30]} Growth ({fertilizer.growth_per_coin_by_speed[30]:g}/Coin)",
                    f"{fertilizer.growth_by_speed[100]} Growth ({fertilizer.growth_per_coin_by_speed[100]:g}/Coin)",
                    f"{fertilizer.growth_by_speed[300]} Growth ({fertilizer.growth_per_coin_by_speed[300]:g}/Coin)",
                )
                for fertilizer in report.timed_fertilizer_value
            ),
        ),
        "",
        "These are full-duration ceilings: the cards must continue for the entire timer. A 100-Growth Small Charge at 30 Coins gives 3.33 Growth/Coin; a 500-Growth Standard Charge at 125 Coins gives 4 Growth/Coin. The proposed Fertilizer prices match those references at 100 cards/hour and deliberately scale below or above them with review speed. Changing only prices would move the anchor but would not remove the linear speed difference.",
        "",
        "## Random-environment power at 100 cards/day",
        "",
        _markdown_table(
            ("Environment", "Daily Growth-equivalent", "Advantage over 1,000 base Growth"),
            (
                (name, f"{value:g}", f"{value / 10:.1f}%")
                for name, value in report.environment_growth_equivalent_at_100_cards.items()
            ),
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the compact Markdown report.",
    )
    args = parser.parse_args()
    report = simulate_profiles()
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
