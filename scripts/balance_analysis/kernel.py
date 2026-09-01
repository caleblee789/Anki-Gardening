from __future__ import annotations

from bisect import bisect_left, bisect_right
from array import array
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from hashlib import blake2b, sha256
from fractions import Fraction
import math
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .catalog import CatalogFacts, PurchaseOption, RewardFact, load_catalog_facts
from .model import (
    APPROVED_COHORTS,
    APPROVED_CONSUMABLE_POLICY_BY_STRATEGY,
    APPROVED_SCENARIO_IDS,
    DEFAULT_DAYS,
    DEFAULT_SEED_COUNT,
    ScenarioSpec,
    SimulationConfig,
    approved_scenarios,
    completes_study_day,
    is_study_day,
)


GROWTH_UNITS_PER_POINT = 100
MASK_64 = (1 << 64) - 1
METRIC_UNITS = {
    "answers.total": "cards",
    "days.studied": "days",
    "days.completed": "days",
    "growth.total_units": "growth_units",
    "growth.generated_units": "growth_units",
    "growth.opening_plant_units": "growth_units",
    "growth.applied_units": "growth_units",
    "growth.applied_to_plants_units": "growth_units",
    "growth.stored_balance_units": "growth_units",
    "growth.routed_to_storage_units_lifetime": "growth_units",
    "growth.contributed_to_landmarks_units": "growth_units",
    "growth.contributed_to_mastery_units": "growth_units",
    "growth.contributed_to_legacy_units": "growth_units",
    "growth.unallocated_overflow_units": "growth_units",
    "growth.shared_units": "growth_units",
    "growth.spent_units": "growth_units",
    "plants.full_bloom": "plants",
    "plants.first_full_bloom_day": "day",
    "plants.all_catalog_full_bloom_day": "day",
    "beds.owned": "beds",
    "achievements.claimed": "achievements",
    "coins.gross": "coins",
    "coins.gross_without_completion_rewards": "coins",
    "coins.spent": "coins",
    "coins.ending": "coins",
    "coins.top_source_share": "ratio",
    "coins.source_hhi": "ratio",
    "growth.total_units_per_answer": "growth_units_per_card",
    "coins.gross_per_100_answers": "coins_per_100_cards",
    "finds.per_1000_answers": "finds_per_1000_cards",
    "finds.total": "finds",
    "finds.coins": "coins",
    "finds.growth_units": "growth_units",
    "finds.inventory_units": "items",
    "finds.capped_days": "days",
    "finds.maximum_attempted_gap": "cards",
    "catalog.permanent_owned": "items",
    "catalog.completion_day": "day",
    "catalog.functional_completion_day": "day",
    "catalog.pre_endgame_completion_day": "day",
    "catalog.all_permanent_completion_day": "day",
    "catalog.all_permanent_remaining_coins": "coins",
    "environments.discovered": "items",
    "environments.effect_growth_units": "growth_units",
    "environments.effect_coins": "coins",
    "environments.effect_consumables": "items",
    "inventory.units": "items",
    "inventory.effect_cards_remaining": "cards",
    "consumables.growth_units": "growth_units",
    "landmarks.owned": "items",
    "landmarks.growth_funded_units": "growth_units",
    "landmarks.tiers_funded": "items",
    "landmarks.tiers_claimed": "items",
    "landmarks.tiers_claimable": "items",
    "mastery.owned": "ranks",
    "mastery.growth_funded_units": "growth_units",
    "mastery.ranks_funded": "ranks",
    "mastery.ranks_claimed": "ranks",
    "mastery.ranks_claimable": "ranks",
    "legacy.level": "levels",
    "legacy.progress_units": "growth_units",
    "coins.required_for_claimable_content": "coins",
    "catalog.finite_permanent_remaining_coins": "coins",
    "endgame.finite_coin_claim_demand_remaining": "coins",
    "endgame.finite_growth_capacity_units": "growth_units",
    "endgame.finite_growth_remaining_units": "growth_units",
    "endgame.finite_targets_remaining": "items",
    "endgame.finite_growth_fully_funded": "boolean",
    "endgame.active_project_selected": "boolean",
    "endgame.active_project_unallocated_stored_units": "growth_units",
    "endgame.active_project_no_unallocated_storage": "boolean",
    "endgame.no_project_reserve_units": "growth_units",
    "endgame.no_project_preservation_delta_units": "growth_units",
    "endgame.no_project_preserves_entire_reserve": "boolean",
    "environments.any_tier_simultaneous_forced_user": "boolean",
}


CONSUMABLE_REPORT_FIELDS = (
    "units_earned",
    "units_purchased",
    "units_activated",
    "units_consumed",
    "units_remaining",
    "cards_of_effect_remaining",
    "growth_generated",
    "coins_spent",
)


CONSUMABLE_METRIC_UNITS = {
    "units_earned": "items",
    "units_purchased": "items",
    "units_activated": "items",
    "units_consumed": "items",
    "units_remaining": "items",
    "cards_of_effect_remaining": "cards",
    "growth_generated": "growth_units",
    "coins_spent": "coins",
    # Compatibility aliases retained for frozen pre-release analysis readers.
    "effect_cards_remaining": "cards",
    "growth_generated_units": "growth_units",
}


ENVIRONMENT_METRIC_UNITS = {
    "first_discovery_day": "day",
    "both_items_completion_day": "day",
    "first_discovery_eligible_card": "cards",
    "both_items_completion_eligible_card": "cards",
    "natural_acquisitions": "items",
    "card_pity_acquisitions": "items",
    "completion_pity_acquisitions": "items",
    "simultaneous_forced_acquisitions": "items",
    "simultaneous_forced_user_rate": "ratio",
    "ownership_blocked_card_checks": "cards",
    "ownership_blocked_completion_checks": "days",
    "ownership_blocked_checks": "checks",
    "ownership_check_opportunities": "checks",
    "ownership_suppression_rate": "ratio",
}


COIN_SOURCE_IDS = (
    "first_eligible_answer",
    "todays_cards",
    "completion_cycle_5",
    "seven_day_streak_cycle",
    "achievement",
    "plant_milestone",
    "standard_find",
    "harvest_bell",
    "autumn_hearth",
    "other",
)

COIN_SOURCE_BEHAVIORAL_FAMILY = {
    "first_eligible_answer": "study_attendance",
    "todays_cards": "todays_cards_completion",
    "completion_cycle_5": "todays_cards_completion",
    "seven_day_streak_cycle": "streak",
    "achievement": "achievements",
    "plant_milestone": "plant_progression",
    "standard_find": "finds",
    "harvest_bell": "equipped_effects",
    "autumn_hearth": "equipped_effects",
    "other": "other",
}


RIGHT_CENSORED_TIMING_METRICS = frozenset({
    "catalog.completion_day",
    "catalog.functional_completion_day",
    "catalog.pre_endgame_completion_day",
    "catalog.all_permanent_completion_day",
    "plants.first_full_bloom_day",
    "plants.all_catalog_full_bloom_day",
})


def _is_right_censored_timing_metric(metric_id: str) -> bool:
    return (
        metric_id in RIGHT_CENSORED_TIMING_METRICS
        or (
            metric_id.startswith("environments.")
            and metric_id.endswith(("_day", "_eligible_card"))
        )
    )


def _metric_unit(metric_id: str) -> str:
    if metric_id in METRIC_UNITS:
        return METRIC_UNITS[metric_id]
    if metric_id.startswith("coins.source."):
        return "coins"
    if metric_id.startswith("mastery."):
        suffix = metric_id.rsplit(".", 1)[-1]
        if suffix == "growth_funded_units":
            return "growth_units"
        if suffix in {"ranks_claimed", "ranks_claimable"}:
            return "ranks"
    if metric_id.startswith("consumables."):
        suffix = metric_id.rsplit(".", 1)[-1]
        if suffix in CONSUMABLE_METRIC_UNITS:
            return CONSUMABLE_METRIC_UNITS[suffix]
    if metric_id.startswith("environments."):
        suffix = metric_id.rsplit(".", 1)[-1]
        if suffix in ENVIRONMENT_METRIC_UNITS:
            return ENVIRONMENT_METRIC_UNITS[suffix]
    raise KeyError(f"unknown balance metric unit: {metric_id}")


class StableRng:
    """Small version-stable SplitMix64 stream seeded with SHA-256."""

    def __init__(self, *parts: object) -> None:
        payload = "\0".join(str(part) for part in parts).encode("utf-8")
        self._state = int.from_bytes(sha256(payload).digest()[:8], "big")

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & MASK_64
        value = self._state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK_64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK_64
        return (value ^ (value >> 31)) & MASK_64

    def random(self) -> float:
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def below(self, total: int) -> int:
        if total <= 0:
            raise ValueError("total must be positive")
        return self.next_u64() % int(total)


class StandardGapSampler:
    def __init__(self, facts: CatalogFacts) -> None:
        cdf = []
        survival = 1.0
        last = facts.standard_guarantee_answer
        bands_by_answer = {}
        for band in facts.standard_find_schedule:
            for answer in range(band.first_answer, band.last_answer + 1):
                bands_by_answer[answer] = band
        for answer in range(1, last + 1):
            band = bands_by_answer[answer]
            probability = band.numerator / band.denominator
            hit = survival * probability
            survival *= 1.0 - probability
            cdf.append((answer, 1.0 - survival))
        # The published guarantee remains authoritative even if a malformed
        # schedule rounds below one in floating point.
        cdf[-1] = (last, 1.0)
        self._answers = tuple(row[0] for row in cdf)
        self._cdf = tuple(row[1] for row in cdf)

    def sample(self, rng: StableRng) -> int:
        index = bisect_left(self._cdf, rng.random())
        return self._answers[min(index, len(self._answers) - 1)]


@dataclass(frozen=True)
class EnvironmentDiscoveryEvent:
    item_id: str
    tier_id: str
    route: str
    eligible_card_index: int
    simultaneous_forced: bool = False


@dataclass(frozen=True)
class DayEvents:
    day: int
    study: bool
    answers: int
    standard_finds: int = 0
    find_coins: int = 0
    find_growth_units: int = 0
    inventory_items: Tuple[str, ...] = ()
    capped: bool = False
    maximum_gap: int = 0
    environment_discoveries: Tuple[EnvironmentDiscoveryEvent, ...] = ()
    environment_blocked_card_checks: Tuple[Tuple[str, int], ...] = ()
    environment_blocked_completion_checks: Tuple[Tuple[str, int], ...] = ()
    find_drought_counter_after: int = 0
    daily_find_cap_after: int = 3
    environment_card_pity_after: Tuple[Tuple[str, int], ...] = ()
    environment_completion_pity_after: Tuple[Tuple[str, int], ...] = ()
    environment_owned_item_ids_after: Tuple[str, ...] = ()
    scheduler_day_id: str = ""
    production_reward_seed: str = ""
    find_growth_units_by_answer: Tuple[Tuple[int, int], ...] = ()

    @property
    def environment_item_ids(self) -> Tuple[str, ...]:
        return tuple(item.item_id for item in self.environment_discoveries)

    @property
    def environments_discovered(self) -> int:
        return len(self.environment_item_ids)


def _weighted_reward(
    rewards: Sequence[RewardFact],
    rng: StableRng,
    *,
    minimum_tier: str = "",
) -> RewardFact:
    candidates = tuple(rewards)
    if minimum_tier:
        tier_rank = {
            "common": 0,
            "uncommon": 1,
            "rare": 2,
            "very rare": 3,
            "exceptional": 4,
            "ultra rare": 5,
        }
        filtered = tuple(
            reward for reward in candidates
            if tier_rank.get(reward.tier.lower(), 0)
            >= tier_rank.get(minimum_tier.lower(), 0)
        )
        if filtered:
            candidates = filtered
    total = sum(max(0, reward.weight) for reward in candidates)
    if total <= 0:
        raise ValueError("Standard Find reward pool has no positive weight")
    cursor = rng.below(total)
    for reward in candidates:
        cursor -= max(0, reward.weight)
        if cursor < 0:
            return reward
    return candidates[-1]


def _truncated_geometric(
    rng: StableRng,
    denominator: int,
    hard_limit: int,
) -> int:
    if denominator <= 1:
        return 1
    probability = 1.0 / denominator
    # Inverse geometric CDF, capped by the true hard guarantee.
    draw = max(rng.random(), 2.0 ** -53)
    gap = int(math.floor(math.log1p(-draw) / math.log1p(-probability))) + 1
    return max(1, min(hard_limit, gap))


def _environment_target(
    rng: StableRng,
    denominator: int,
    hard_limit: int,
) -> Tuple[int, bool]:
    """Return a natural target or an explicitly identified card-pity target."""

    if denominator <= 1:
        return 1, False
    probability = 1.0 / denominator
    draw = max(rng.random(), 2.0 ** -53)
    natural_gap = (
        int(math.floor(math.log1p(-draw) / math.log1p(-probability))) + 1
    )
    if natural_gap > hard_limit:
        return max(1, int(hard_limit)), True
    return max(1, int(natural_gap)), False


def _environment_daily_discoveries(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    rng: StableRng,
) -> Tuple[
    Tuple[Tuple[EnvironmentDiscoveryEvent, ...], ...],
    Tuple[Tuple[Tuple[str, int], ...], ...],
    Tuple[Tuple[Tuple[str, int], ...], ...],
]:
    if not facts.environment_tiers or not facts.environment_discovery_ids:
        empty = ((),) * config.days
        return empty, empty, empty
    items_by_tier: MutableMapping[str, List[str]] = defaultdict(list)
    for item in facts.environment_discoveries:
        items_by_tier[item.tier_id].append(item.item_id)
    states = []
    for position, tier in enumerate(facts.environment_tiers):
        tier_rng = StableRng(rng.next_u64(), "environment", position, tier.tier_id)
        target, card_pity = _environment_target(
            tier_rng,
            tier.base_denominator,
            tier.card_guarantee,
        )
        states.append({
            "tier": tier,
            "rng": tier_rng,
            "items": tuple(items_by_tier[tier.tier_id]),
            "index": 0,
            "cards": 0,
            "completions": 0,
            "eligible_cards_lifetime": 0,
            "card_target": target,
            "card_target_is_pity": card_pity,
        })

    daily = []
    daily_blocked_cards = []
    daily_blocked_completions = []
    active_index = 0
    for day in range(1, config.days + 1):
        study = is_study_day(day, scenario)
        answers = scenario.cohort.cards_per_study_day if study else 0
        complete = False
        if study:
            active_index += 1
            complete = completes_study_day(active_index, scenario.completion_percent)
        discovered = []
        blocked_cards = []
        blocked_completions = []
        owned_at_day_start = {
            id(state)
            for state in states
            if state["index"] >= len(state["items"])
        }
        for state in states:
            if id(state) not in owned_at_day_start:
                continue
            tier = state["tier"]
            if answers:
                blocked_cards.append((tier.tier_id, answers))
            if complete:
                blocked_completions.append((tier.tier_id, 1))
        card_cursor = 0
        while card_cursor < answers:
            active_states = [
                state for state in states
                if state["index"] < len(state["items"])
            ]
            if not active_states:
                break
            remaining_answers = answers - card_cursor
            step = min(
                state["card_target"] - state["cards"]
                for state in active_states
            )
            advance = min(remaining_answers, step)
            for state in active_states:
                state["cards"] += advance
                state["eligible_cards_lifetime"] += advance
            card_cursor += advance
            if advance < step:
                break

            candidates = [
                state for state in active_states
                if state["cards"] >= state["card_target"]
            ]
            forced = [
                state for state in candidates
                if state["card_target_is_pity"]
            ]
            natural = [
                state for state in candidates
                if not state["card_target_is_pity"]
            ]
            # A single eligible card may naturally hit several tiers. Only the
            # rarest natural result is granted; every forced tier is granted.
            natural_winner = natural[-1] if natural else None
            granted = [*forced]
            if natural_winner is not None and natural_winner not in granted:
                granted.append(natural_winner)
            granted_ids = {id(state) for state in granted}

            simultaneous_forced = len(forced) > 1
            for state in granted:
                tier = state["tier"]
                discovered.append(EnvironmentDiscoveryEvent(
                    item_id=state["items"][state["index"]],
                    tier_id=tier.tier_id,
                    route=(
                        "card_pity" if state["card_target_is_pity"] else "natural"
                    ),
                    eligible_card_index=state["eligible_cards_lifetime"],
                    simultaneous_forced=(
                        simultaneous_forced and state["card_target_is_pity"]
                    ),
                ))
                state["index"] += 1
                state["cards"] = 0
                state["completions"] = 0
                if state["index"] >= len(state["items"]):
                    remaining_checks = max(0, answers - card_cursor)
                    if remaining_checks:
                        blocked_cards.append((tier.tier_id, remaining_checks))
                if state["index"] < len(state["items"]):
                    target, card_pity = _environment_target(
                        state["rng"],
                        tier.base_denominator,
                        tier.card_guarantee,
                    )
                    state["card_target"] = target
                    state["card_target_is_pity"] = card_pity

            for state in candidates:
                if id(state) in granted_ids:
                    continue
                tier = state["tier"]
                remaining_to_pity = max(
                    1,
                    tier.card_guarantee - state["cards"],
                )
                target_delta, card_pity = _environment_target(
                    state["rng"],
                    tier.base_denominator,
                    remaining_to_pity,
                )
                state["card_target"] = state["cards"] + target_delta
                state["card_target_is_pity"] = card_pity

        for state in states:
            tier = state["tier"]
            if state["index"] >= len(state["items"]):
                if complete and id(state) not in owned_at_day_start:
                    blocked_completions.append((tier.tier_id, 1))
                continue
            if complete:
                state["completions"] += 1

        completion_forced = [
            state for state in states
            if state["index"] < len(state["items"])
            and complete
            and state["completions"] >= state["tier"].completion_guarantee
        ]
        for state in completion_forced:
            tier = state["tier"]
            discovered.append(EnvironmentDiscoveryEvent(
                item_id=state["items"][state["index"]],
                tier_id=tier.tier_id,
                route="completion_pity",
                eligible_card_index=state["eligible_cards_lifetime"],
                simultaneous_forced=len(completion_forced) > 1,
            ))
            state["index"] += 1
            state["cards"] = 0
            state["completions"] = 0
            if state["index"] < len(state["items"]):
                target, card_pity = _environment_target(
                    state["rng"],
                    tier.base_denominator,
                    tier.card_guarantee,
                )
                state["card_target"] = target
                state["card_target_is_pity"] = card_pity

        daily.append(tuple(discovered))
        daily_blocked_cards.append(tuple(blocked_cards))
        daily_blocked_completions.append(tuple(blocked_completions))
    return (
        tuple(daily),
        tuple(daily_blocked_cards),
        tuple(daily_blocked_completions),
    )


def generate_event_stream(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    seed_index: int,
) -> Tuple[DayEvents, ...]:
    """Generate sparse catalog-driven random events, paired across strategies."""

    rng = StableRng(
        config.seed_root,
        seed_index,
        scenario.cohort.cohort_id,
        "missed_week" if scenario.missed_week_start_day else "base_calendar",
    )
    gap_sampler = StandardGapSampler(facts)
    remaining_gap = gap_sampler.sample(rng)
    maximum_gap = remaining_gap
    (
        environment_by_day,
        environment_blocked_cards_by_day,
        environment_blocked_completions_by_day,
    ) = _environment_daily_discoveries(
        facts,
        scenario,
        config,
        rng,
    )
    rows = []
    for day in range(1, config.days + 1):
        study = is_study_day(day, scenario)
        answers = scenario.cohort.cards_per_study_day if study else 0
        finds = 0
        find_coins = 0
        find_growth_units = 0
        inventory = []
        capped = False
        attempted = answers
        daily_cap = facts.standard_daily_cap(answers)
        while attempted > 0 and finds < daily_cap:
            if remaining_gap > attempted:
                remaining_gap -= attempted
                attempted = 0
                break
            attempted -= remaining_gap
            hit_gap = remaining_gap
            finds += 1
            reward = _weighted_reward(
                facts.standard_rewards,
                rng,
                minimum_tier=facts.standard_minimum_tier(hit_gap),
            )
            reward_kind = reward.reward_kind.lower()
            if "coin" in reward_kind:
                find_coins += reward.amount
            elif "growth" in reward_kind:
                find_growth_units += reward.amount * GROWTH_UNITS_PER_POINT
            elif reward.inventory_item_id:
                inventory.extend([reward.inventory_item_id] * reward.amount)
            remaining_gap = gap_sampler.sample(rng)
            maximum_gap = max(maximum_gap, remaining_gap)
        if finds >= daily_cap and attempted > 0:
            capped = True
        rows.append(DayEvents(
            day=day,
            study=study,
            answers=answers,
            standard_finds=finds,
            find_coins=find_coins,
            find_growth_units=find_growth_units,
            inventory_items=tuple(inventory),
            capped=capped,
            maximum_gap=maximum_gap,
            environment_discoveries=environment_by_day[day - 1],
            environment_blocked_card_checks=(
                environment_blocked_cards_by_day[day - 1]
            ),
            environment_blocked_completion_checks=(
                environment_blocked_completions_by_day[day - 1]
            ),
        ))
    return tuple(rows)


@dataclass(frozen=True)
class MilestoneSchedule:
    positions: Tuple[int, ...]
    rewards: Tuple[int, ...]


def _milestone_schedule(facts: CatalogFacts, plant_count: int) -> MilestoneSchedule:
    rows = []
    full = facts.full_bloom_growth
    for plant_index in range(max(0, int(plant_count))):
        offset = plant_index * full
        previous = 0
        for stage in facts.stages[1:]:
            span = stage.threshold_growth - previous
            rewards = stage.checkpoint_coin_rewards
            if rewards:
                for reward_index, reward in enumerate(rewards, start=1):
                    threshold = previous + math.ceil(span * reward_index / len(rewards))
                    rows.append(((offset + threshold) * GROWTH_UNITS_PER_POINT, reward))
            previous = stage.threshold_growth
    rows.sort()
    return MilestoneSchedule(
        positions=tuple(row[0] for row in rows),
        rewards=tuple(row[1] for row in rows),
    )


def _coins_for_crossings(
    schedule: MilestoneSchedule,
    before_units: int,
    after_units: int,
) -> int:
    start = bisect_right(schedule.positions, before_units)
    end = bisect_right(schedule.positions, after_units)
    return sum(schedule.rewards[start:end])


def _option_value(option: PurchaseOption, objective: str) -> Tuple[float, int, str]:
    if objective == "coin":
        primary = option.coin_return_per_coin
    else:
        primary = option.growth_per_coin
    return (-primary, option.price_coins, option.item_id)


def _grant_growth_value(facts: CatalogFacts, grant) -> int:
    kind = grant.kind.lower()
    if kind in {"growth", "instant_growth", "banked_growth"}:
        return grant.amount
    if kind == "consumable":
        consumable = next(
            (
                row for row in facts.consumables
                if row.consumable_id == grant.item_id
            ),
            None,
        )
        if consumable is not None:
            return grant.amount * consumable.maximum_growth
    return 0


def _environment_daily_value(
    facts: CatalogFacts,
    item_id: str,
    scenario: ScenarioSpec,
) -> Tuple[Fraction, Fraction]:
    growth = Fraction(0, 1)
    coins = Fraction(0, 1)
    completion_rate = Fraction(scenario.completion_percent, 100)
    for effect in facts.effects_by_item_id.get(item_id, ()):
        triggers = Fraction(1, 1)
        if effect.trigger == "eligible_card":
            eligible = min(
                scenario.cohort.cards_per_study_day,
                effect.first_n_per_day or scenario.cohort.cards_per_study_day,
            )
            triggers = (
                Fraction(eligible, max(1, effect.every_n))
                if effect.counter_scope == "lifetime_active"
                else Fraction(eligible // max(1, effect.every_n), 1)
            )
        elif effect.trigger == "valid_completion":
            triggers = completion_rate / max(1, effect.every_n)
        elif effect.trigger in {"booster_activation", "plant_milestone"}:
            # These are interaction modifiers, not independent daily grants.
            triggers = Fraction(0, 1)
        if effect.grant is not None:
            growth += triggers * _grant_growth_value(facts, effect.grant)
            if effect.grant.kind.lower() == "coins":
                coins += triggers * effect.grant.amount
        for grant, weight in effect.weighted_grants:
            weighted_triggers = triggers * Fraction(weight, 100)
            growth += weighted_triggers * _grant_growth_value(facts, grant)
            if grant.kind.lower() == "coins":
                coins += weighted_triggers * grant.amount
    return growth, coins


def _permanent_priority(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
) -> Tuple[PurchaseOption, ...]:
    options = facts.purchase_options
    strategy = scenario.strategy
    allowed_endgame = scenario.landmark_mastery_spending
    rows = [
        option for option in options
        if option.permanent
        and option.available
        and option.price_coins > 0
        and (
            allowed_endgame
            or option.category not in {"landmark", "mastery"}
        )
    ]
    if strategy.optimize_for:
        def optimized_key(item: PurchaseOption):
            if item.category in {"garden_bonus", "scenery"}:
                growth, coins = _environment_daily_value(facts, item.item_id, scenario)
                value = coins if strategy.optimize_for == "coin" else growth
                ratio = value / item.price_coins if item.price_coins else Fraction(0, 1)
                return (-ratio, item.price_coins, item.item_id)
            return _option_value(item, strategy.optimize_for)

        return tuple(sorted(rows, key=optimized_key))
    ranks = {category: index for index, category in enumerate(strategy.permanent_priority)}
    return tuple(sorted(
        rows,
        key=lambda item: (
            ranks.get(item.category, len(ranks)),
            item.price_coins,
            item.item_id,
        ),
    ))


def _best_consumable(
    options: Sequence[PurchaseOption],
    objective: str,
) -> Optional[PurchaseOption]:
    rows = [
        option for option in options
        if option.repeatable and option.available and option.price_coins > 0
    ]
    if not rows:
        return None
    return min(rows, key=lambda item: _option_value(item, objective or "growth"))


@dataclass
class RunState:
    wallet: int
    gross_coins: int
    spent_coins: int
    coin_sources: Counter
    answers: int
    studied_days: int
    completed_days: int
    study_run: int
    recent_completion_flags: List[bool]
    total_growth_units: int
    opening_plant_growth_units: int
    applied_growth_units: int
    stored_growth_units: int
    routed_to_storage_units_lifetime: int
    shared_growth_units: int
    growth_spent_units: int
    growth_contributed_to_landmarks_units: int
    growth_contributed_to_mastery_units: int
    growth_contributed_to_legacy_units: int
    manual_project_contributions_units: int
    unallocated_overflow_units: int
    endgame_funded_units: Counter
    endgame_plan_ids: Tuple[str, ...]
    auto_fund_endgame: bool
    endgame_active_target_index: int
    garden_legacy_level: int
    garden_legacy_progress_units: int
    species_owned: int
    beds_owned: int
    plant_growth_units: List[int]
    plant_species_ids: List[str]
    active_plant_index: Optional[int]
    permanent_owned: set
    inventory: Counter
    consumable_effect_cards: Counter
    consumable_active_batches: Dict[str, List[List[int]]]
    fertilizer_activation_order_by_plant: Dict[int, List[str]]
    environment_extension_cards: Counter
    consumable_growth_units: int
    consumable_units_earned: Counter
    consumable_units_purchased: Counter
    consumable_units_activated: Counter
    consumable_units_consumed: Counter
    consumable_growth_by_item_units: Counter
    consumable_coins_spent: Counter
    purchases: List[Tuple[int, str, int]]
    environment_owned: int
    finds: int
    find_coins: int
    find_growth_units: int
    find_inventory_units: int
    capped_days: int
    maximum_gap: int
    catalog_completion_day: Optional[int]
    functional_catalog_completion_day: Optional[int]
    pre_endgame_catalog_completion_day: Optional[int]
    all_permanent_catalog_completion_day: Optional[int]
    first_full_bloom_day: Optional[int]
    all_catalog_full_bloom_day: Optional[int]
    shared_remainder: int
    purchase_cursor: int
    claimed_achievements: set
    achievement_cursors: Dict[str, int]
    active_garden_bonus_id: str
    active_scenery_id: str
    effect_counters: Counter
    effect_banks: Counter
    milestone_coin_carry_units: int
    milestone_bonus_percent: int
    environment_effect_growth_units: int
    environment_effect_coins: int
    environment_effect_consumables: int
    garden_cycle_remainder: int
    environment_first_day_by_tier: Dict[str, int]
    environment_both_day_by_tier: Dict[str, int]
    environment_first_card_by_tier: Dict[str, int]
    environment_both_card_by_tier: Dict[str, int]
    environment_acquisitions_by_tier_route: Counter
    environment_simultaneous_forced_by_tier: Counter
    environment_blocked_cards_by_tier: Counter
    environment_blocked_completions_by_tier: Counter
    environment_owned_count_by_tier: Counter
    find_drought_counter: int
    daily_find_cap: int
    daily_find_count: int
    environment_card_pity: Dict[str, int]
    environment_completion_pity: Dict[str, int]


def _initial_state(facts: CatalogFacts, scenario: ScenarioSpec) -> RunState:
    included = {
        option.item_id
        for option in facts.purchase_options
        if option.included and option.permanent
    }
    if facts.species_ids:
        included.add(facts.species_ids[0])
    if scenario.all_plants_complete:
        included.update(facts.species_ids)
    if scenario.all_environments_owned:
        included.update(facts.environment_discovery_ids)
    included_beds = sum(
        1 for option in facts.purchase_options
        if option.category == "bed" and option.included
    )
    environment_owned = (
        len(facts.environment_discovery_ids)
        if scenario.all_environments_owned else 0
    )
    environment_owned_count_by_tier = Counter()
    if scenario.all_environments_owned:
        environment_owned_count_by_tier.update(
            item.tier_id for item in facts.environment_discoveries
        )
    active_garden_bonus_id = next((
        option.item_id for option in facts.purchase_options
        if option.category == "garden_bonus" and option.included
    ), "")
    active_scenery_id = next((
        option.item_id for option in facts.purchase_options
        if option.category == "scenery" and option.included
    ), "")
    species_owned = (
        len(facts.species_ids) if scenario.all_plants_complete
        else max(1, sum(
            1 for option in facts.purchase_options
            if option.category == "species" and option.included
        ))
    )
    seeded_plant_units = (
        [facts.full_bloom_growth * GROWTH_UNITS_PER_POINT] * species_owned
        if scenario.all_plants_complete else [0] * species_owned
    )
    return RunState(
        wallet=0,
        gross_coins=0,
        spent_coins=0,
        coin_sources=Counter(),
        answers=0,
        studied_days=0,
        completed_days=0,
        study_run=0,
        recent_completion_flags=[],
        total_growth_units=0,
        opening_plant_growth_units=(
            len(facts.species_ids)
            * facts.full_bloom_growth
            * GROWTH_UNITS_PER_POINT
            if scenario.all_plants_complete else 0
        ),
        applied_growth_units=0,
        stored_growth_units=0,
        routed_to_storage_units_lifetime=0,
        shared_growth_units=0,
        growth_spent_units=0,
        growth_contributed_to_landmarks_units=0,
        growth_contributed_to_mastery_units=0,
        growth_contributed_to_legacy_units=0,
        manual_project_contributions_units=0,
        unallocated_overflow_units=0,
        endgame_funded_units=Counter(),
        endgame_plan_ids=tuple(
            option.item_id
            for option in sorted(
                (
                    option for option in facts.purchase_options
                    if option.category in {"landmark", "mastery"}
                ),
                key=lambda option: (
                    0 if option.category == "landmark" else 1,
                    option.growth_cost,
                    option.item_id,
                ),
            )
        ),
        auto_fund_endgame=scenario.landmark_mastery_spending,
        endgame_active_target_index=(
            0 if scenario.landmark_mastery_spending else -1
        ),
        garden_legacy_level=0,
        garden_legacy_progress_units=0,
        species_owned=species_owned,
        beds_owned=(
            max(6, included_beds) if scenario.all_plants_complete
            else max(2, included_beds)
        ),
        plant_growth_units=seeded_plant_units,
        plant_species_ids=(
            list(facts.species_ids)
            if scenario.all_plants_complete
            else [facts.species_ids[0]] if facts.species_ids else []
        ),
        active_plant_index=None if scenario.all_plants_complete else 0,
        permanent_owned=included,
        inventory=Counter(),
        consumable_effect_cards=Counter(),
        consumable_active_batches={},
        fertilizer_activation_order_by_plant={},
        environment_extension_cards=Counter(),
        consumable_growth_units=0,
        consumable_units_earned=Counter(),
        consumable_units_purchased=Counter(),
        consumable_units_activated=Counter(),
        consumable_units_consumed=Counter(),
        consumable_growth_by_item_units=Counter(),
        consumable_coins_spent=Counter(),
        purchases=[],
        environment_owned=environment_owned,
        finds=0,
        find_coins=0,
        find_growth_units=0,
        find_inventory_units=0,
        capped_days=0,
        maximum_gap=0,
        catalog_completion_day=None,
        functional_catalog_completion_day=None,
        pre_endgame_catalog_completion_day=None,
        all_permanent_catalog_completion_day=None,
        first_full_bloom_day=0 if scenario.all_plants_complete else None,
        all_catalog_full_bloom_day=0 if scenario.all_plants_complete else None,
        shared_remainder=0,
        purchase_cursor=0,
        claimed_achievements=set(),
        achievement_cursors={},
        active_garden_bonus_id=active_garden_bonus_id,
        active_scenery_id=active_scenery_id,
        effect_counters=Counter(),
        effect_banks=Counter(),
        milestone_coin_carry_units=0,
        milestone_bonus_percent=0,
        environment_effect_growth_units=0,
        environment_effect_coins=0,
        environment_effect_consumables=0,
        garden_cycle_remainder=0,
        environment_first_day_by_tier={},
        environment_both_day_by_tier={},
        environment_first_card_by_tier={},
        environment_both_card_by_tier={},
        environment_acquisitions_by_tier_route=Counter(),
        environment_simultaneous_forced_by_tier=Counter(),
        environment_blocked_cards_by_tier=Counter(),
        environment_blocked_completions_by_tier=Counter(),
        environment_owned_count_by_tier=environment_owned_count_by_tier,
        find_drought_counter=0,
        daily_find_cap=3,
        daily_find_count=0,
        environment_card_pity={},
        environment_completion_pity={},
    )


def _credit(state: RunState, source: str, amount: int) -> None:
    value = max(0, int(amount))
    state.wallet += value
    state.gross_coins += value
    state.coin_sources[source] += value


def _endgame_option_by_id(
    facts: CatalogFacts,
) -> Mapping[str, PurchaseOption]:
    return {
        option.item_id: option
        for option in facts.purchase_options
        if option.category in {"landmark", "mastery"}
    }


def _finite_endgame_fully_funded(
    state: RunState,
    options_by_id: Mapping[str, PurchaseOption],
) -> bool:
    return bool(state.endgame_plan_ids) and all(
        state.endgame_funded_units[item_id]
        >= options_by_id[item_id].growth_cost * GROWTH_UNITS_PER_POINT
        for item_id in state.endgame_plan_ids
    )


def _endgame_target_plan(
    state: RunState,
    facts: CatalogFacts,
) -> Tuple[Tuple[str, str, Tuple[str, ...]], ...]:
    """Return the player-selectable finite tracks in deterministic order."""

    options_by_id = _endgame_option_by_id(facts)
    landmark_ids = tuple(
        sorted(
            (
                item_id for item_id in state.endgame_plan_ids
                if options_by_id[item_id].category == "landmark"
            ),
            key=lambda item_id: (
                options_by_id[item_id].growth_cost,
                item_id,
            ),
        )
    )
    mastery_by_species: MutableMapping[str, List[str]] = defaultdict(list)
    for item_id in state.endgame_plan_ids:
        option = options_by_id[item_id]
        if option.category != "mastery":
            continue
        mastery_by_species[item_id.split(":", 2)[1]].append(item_id)
    targets: List[Tuple[str, str, Tuple[str, ...]]] = []
    if landmark_ids:
        targets.append(("landmark", "garden_landmark", landmark_ids))
    for species_id in facts.species_ids:
        item_ids = mastery_by_species.get(species_id, ())
        if not item_ids:
            continue
        targets.append((
            "mastery",
            species_id,
            tuple(sorted(
                item_ids,
                key=lambda item_id: (
                    options_by_id[item_id].growth_cost,
                    item_id,
                ),
            )),
        ))
    return tuple(targets)


def _endgame_target_is_funded(
    state: RunState,
    options_by_id: Mapping[str, PurchaseOption],
    option_ids: Sequence[str],
) -> bool:
    return all(
        state.endgame_funded_units[item_id]
        >= options_by_id[item_id].growth_cost * GROWTH_UNITS_PER_POINT
        for item_id in option_ids
    )


def _advance_endgame_active_target(
    state: RunState,
    facts: CatalogFacts,
) -> None:
    """Select the next unfinished finite track, then evergreen Legacy."""

    if not state.auto_fund_endgame:
        return
    targets = _endgame_target_plan(state, facts)
    options_by_id = _endgame_option_by_id(facts)
    index = max(0, int(state.endgame_active_target_index))
    while index < len(targets) and _endgame_target_is_funded(
        state,
        options_by_id,
        targets[index][2],
    ):
        index += 1
    state.endgame_active_target_index = index


def _fund_endgame_projects(
    state: RunState,
    facts: CatalogFacts,
    growth_units: int,
    *,
    allow_target_switches: bool = False,
) -> int:
    """Credit the acknowledged active track, returning any remainder.

    Generated overflow cannot jump from one selectable project to another.
    Manual Stored Growth contributions may explicitly switch projects between
    credits, which is modeled with ``allow_target_switches``.
    """

    remaining = max(0, int(growth_units))
    if not state.auto_fund_endgame or remaining <= 0:
        return remaining
    options_by_id = _endgame_option_by_id(facts)
    targets = _endgame_target_plan(state, facts)
    _advance_endgame_active_target(state, facts)

    while remaining > 0:
        target_index = max(0, int(state.endgame_active_target_index))
        if target_index >= len(targets):
            if not _finite_endgame_fully_funded(state, options_by_id):
                break
            state.growth_contributed_to_legacy_units += remaining
            state.growth_spent_units += remaining
            legacy_total = state.garden_legacy_progress_units + remaining
            levels, state.garden_legacy_progress_units = divmod(
                legacy_total,
                500_000 * GROWTH_UNITS_PER_POINT,
            )
            state.garden_legacy_level += levels
            remaining = 0
            break

        _target_type, _target_id, option_ids = targets[target_index]
        before = remaining
        for item_id in option_ids:
            option = options_by_id[item_id]
            capacity = option.growth_cost * GROWTH_UNITS_PER_POINT
            accepted = min(
                remaining,
                max(0, capacity - state.endgame_funded_units[item_id]),
            )
            if not accepted:
                continue
            state.endgame_funded_units[item_id] += accepted
            state.growth_spent_units += accepted
            if option.category == "landmark":
                state.growth_contributed_to_landmarks_units += accepted
            else:
                state.growth_contributed_to_mastery_units += accepted
            remaining -= accepted
            if remaining <= 0:
                return 0

        target_complete = _endgame_target_is_funded(
            state,
            options_by_id,
            option_ids,
        )
        if not target_complete or remaining == before:
            break
        if not allow_target_switches:
            break
        state.endgame_active_target_index += 1
    return remaining


def _planted_indices(state: RunState) -> Tuple[int, ...]:
    planted = min(
        max(0, int(state.beds_owned)),
        max(0, int(state.species_owned)),
        len(state.plant_growth_units),
    )
    return tuple(range(planted))


def _has_unfinished_planted_plant(
    state: RunState,
    facts: CatalogFacts,
) -> bool:
    full_units = facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    return any(
        state.plant_growth_units[index] < full_units
        for index in _planted_indices(state)
    )


def _next_unfinished_plant_index(
    state: RunState,
    facts: CatalogFacts,
    *,
    after: Optional[int] = None,
) -> Optional[int]:
    planted = _planted_indices(state)
    if not planted:
        return None
    if after in planted:
        position = planted.index(after)
        ordered = planted[position + 1:] + planted[:position + 1]
    else:
        ordered = planted
    full_units = facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    return next((
        index for index in ordered
        if state.plant_growth_units[index] < full_units
    ), None)


def _credit_plant_milestones(
    state: RunState,
    schedule: MilestoneSchedule,
    before_units: int,
    after_units: int,
) -> None:
    milestone_coins = _coins_for_crossings(schedule, before_units, after_units)
    if not milestone_coins:
        return
    _credit(state, "plant_milestone", milestone_coins)
    bonus_percent = state.milestone_bonus_percent
    if not bonus_percent:
        return
    bonus_coins, state.milestone_coin_carry_units = divmod(
        milestone_coins * bonus_percent + state.milestone_coin_carry_units,
        100,
    )
    if bonus_coins:
        _credit(
            state,
            "autumn_hearth"
            if state.active_scenery_id == "autumn" else "other",
            bonus_coins,
        )
        state.environment_effect_coins += bonus_coins


def _enqueue_fertilizer_batch(
    state: RunState,
    plant_index: int,
    item_id: str,
) -> None:
    """Mirror production's active same-tier group plus queued other tiers."""

    order = state.fertilizer_activation_order_by_plant.setdefault(
        plant_index,
        [],
    )
    if order and order[0] == item_id:
        insertion = 0
        while insertion < len(order) and order[insertion] == item_id:
            insertion += 1
        order.insert(insertion, item_id)
        return
    order.append(item_id)


def _transfer_consumable_effects(
    state: RunState,
    source_plant_index: int,
    target_plant_index: Optional[int],
) -> None:
    """Preserve remaining card-counted value when the active plant blooms."""

    if (
        target_plant_index is None
        or source_plant_index == target_plant_index
    ):
        return

    source_order = state.fertilizer_activation_order_by_plant.setdefault(
        source_plant_index,
        [],
    )
    target_order = state.fertilizer_activation_order_by_plant.setdefault(
        target_plant_index,
        [],
    )
    transferable = max(0, 5 - len(target_order))
    moved_order = source_order[:transferable]
    retained_order = source_order[transferable:]
    moved_batch_indices: Dict[str, set[int]] = defaultdict(set)
    for item_id in moved_order:
        batches = state.consumable_active_batches.get(item_id, [])
        batch_index = next((
            index
            for index, batch in enumerate(batches)
            if index not in moved_batch_indices[item_id]
            and len(batch) >= 3
            and int(batch[2]) == source_plant_index
            and max(0, int(batch[0])) > 0
        ), None)
        if batch_index is None:
            continue
        moved_batch_indices[item_id].add(batch_index)
        batch = batches[batch_index]
        batches[batch_index] = [
            max(0, int(batch[0])),
            max(0, int(batch[1])),
            target_plant_index,
        ]
    for item_id in moved_order:
        _enqueue_fertilizer_batch(state, target_plant_index, item_id)
    source_order[:] = retained_order

    booster_batches = state.consumable_active_batches.get(
        "booster_potion",
        [],
    )
    target_booster_count = sum(
        len(batch) >= 3
        and int(batch[2]) == target_plant_index
        and max(0, int(batch[0])) > 0
        for batch in booster_batches
    )
    transferable_boosters = max(0, 5 - target_booster_count)
    for batch in booster_batches:
        if transferable_boosters <= 0:
            break
        if (
            len(batch) >= 3
            and int(batch[2]) == source_plant_index
            and max(0, int(batch[0])) > 0
        ):
            batch[2] = target_plant_index
            transferable_boosters -= 1


def _apply_growth(
    state: RunState,
    facts: CatalogFacts,
    growth_units: int,
    milestone_schedule: MilestoneSchedule,
    *,
    intended_plant_index: Optional[int] = None,
) -> None:
    requested = max(0, int(growth_units))
    state.total_growth_units += requested
    if requested <= 0:
        return

    planted = _planted_indices(state)
    if intended_plant_index is None:
        intended_plant_index = state.active_plant_index
    if intended_plant_index not in planted:
        intended_plant_index = None
    if (
        intended_plant_index is None
        and _has_unfinished_planted_plant(state, facts)
    ):
        intended_plant_index = _next_unfinished_plant_index(state, facts)

    if intended_plant_index in planted:
        start = planted.index(intended_plant_index)
        ordered = planted[start:] + planted[:start]
    else:
        ordered = ()

    full_units = facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    remaining = requested
    applied = 0
    for index in ordered:
        if remaining <= 0:
            break
        before = state.plant_growth_units[index]
        credited = min(remaining, max(0, full_units - before))
        if credited <= 0:
            continue
        after = before + credited
        state.plant_growth_units[index] = after
        state.applied_growth_units += credited
        applied += credited
        remaining -= credited
        _credit_plant_milestones(
            state,
            milestone_schedule,
            before,
            after,
        )
        if before < full_units <= after:
            # Production grants one Small Growth Charge at the first Full
            # Bloom of each plant.  It enters inventory and is never folded
            # into the crossing award itself, so strategy-controlled use can
            # occur no earlier than the next modeled review session.
            state.inventory["growth_charge_small"] += 1
            state.consumable_units_earned["growth_charge_small"] += 1

    overflow = requested - applied
    overflow = _fund_endgame_projects(state, facts, overflow)
    state.stored_growth_units += overflow
    state.routed_to_storage_units_lifetime += overflow

    active = state.active_plant_index
    if active is not None and (
        active not in planted
        or state.plant_growth_units[active] >= full_units
    ):
        replacement = _next_unfinished_plant_index(
            state,
            facts,
            after=active,
        )
        _transfer_consumable_effects(state, active, replacement)
        state.active_plant_index = replacement
    elif active is None and _has_unfinished_planted_plant(state, facts):
        state.active_plant_index = _next_unfinished_plant_index(state, facts)


def _apply_review_growth(
    state: RunState,
    facts: CatalogFacts,
    primary_units: int,
    milestone_schedule: MilestoneSchedule,
) -> None:
    """Route one aggregated day's answer Growth through production lanes."""

    requested_primary = max(0, int(primary_units))
    planted = _planted_indices(state)
    active = state.active_plant_index
    if active not in planted or (
        active is not None
        and state.plant_growth_units[active]
        >= facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    ):
        active = _next_unfinished_plant_index(state, facts, after=active)
        state.active_plant_index = active
    anchor = active
    if anchor is None and planted and all(
        state.plant_growth_units[index]
        >= facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
        for index in planted
    ):
        # Once every planted bed is Full Bloom, production retains the first
        # occupied bed as the deterministic Shared-lane anchor.
        anchor = planted[0]

    other_plants = tuple(
        index for index in planted if anchor is not None and index != anchor
    )
    shared_per_lane = (
        requested_primary * facts.shared_growth_numerator
        // facts.shared_growth_denominator
        if other_plants else 0
    )
    state.shared_remainder = 0
    state.shared_growth_units += shared_per_lane * len(other_plants)

    _apply_growth(
        state,
        facts,
        requested_primary,
        milestone_schedule,
        intended_plant_index=active,
    )
    for intended in other_plants:
        _apply_growth(
            state,
            facts,
            shared_per_lane,
            milestone_schedule,
            intended_plant_index=intended,
        )


def _purchase_day(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    day: int,
    permanent_plan: Sequence[PurchaseOption],
    consumable: Optional[PurchaseOption],
) -> None:
    non_endgame_plan = tuple(
        option for option in permanent_plan
        if option.category not in {"landmark", "mastery"}
    )
    # Buy every affordable unique permanent in deterministic order.  This is
    # end-of-day, so newly acquired mechanics cannot alter the day just closed.
    while (
        scenario.strategy.strategy_id != "no_spend"
        and state.purchase_cursor < len(non_endgame_plan)
    ):
        option = non_endgame_plan[state.purchase_cursor]
        if option.item_id in state.permanent_owned:
            state.purchase_cursor += 1
            continue
        if option.price_coins > state.wallet:
            break
        state.wallet -= option.price_coins
        state.spent_coins += option.price_coins
        state.permanent_owned.add(option.item_id)
        state.purchases.append((day, option.item_id, option.price_coins))
        state.purchase_cursor += 1
        if option.category == "species":
            state.species_owned = min(len(facts.species_ids), state.species_owned + 1)
            while len(state.plant_growth_units) < state.species_owned:
                state.plant_growth_units.append(0)
                state.plant_species_ids.append(option.item_id)
            if (
                state.active_plant_index is None
                and _has_unfinished_planted_plant(state, facts)
            ):
                replacement = _next_unfinished_plant_index(
                    state,
                    facts,
                )
                if replacement is not None:
                    full_units = (
                        facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
                    )
                    for completed_index in _planted_indices(state):
                        if (
                            completed_index != replacement
                            and state.plant_growth_units[completed_index]
                            >= full_units
                        ):
                            _transfer_consumable_effects(
                                state,
                                completed_index,
                                replacement,
                            )
                state.active_plant_index = replacement
        elif option.category == "bed":
            state.beds_owned += 1

    # The endgame strategy acknowledges an active project and contributes the
    # entire existing reserve. Funding is independent from later Coin claims.
    if state.auto_fund_endgame and state.stored_growth_units:
        contribution = state.stored_growth_units
        state.stored_growth_units = 0
        remainder = _fund_endgame_projects(
            state,
            facts,
            contribution,
            allow_target_switches=True,
        )
        state.manual_project_contributions_units += contribution - remainder
        state.stored_growth_units += remainder

    if state.auto_fund_endgame:
        # The player explicitly moves on after finishing a track, even when
        # the final generated unit landed exactly on its cap and no Stored
        # Growth remained to contribute that day.
        _advance_endgame_active_target(state, facts)
        options_by_id = _endgame_option_by_id(facts)
        landmark_ids = tuple(
            item_id for item_id in state.endgame_plan_ids
            if options_by_id[item_id].category == "landmark"
        )
        mastery_by_species: MutableMapping[str, List[str]] = defaultdict(list)
        for item_id in state.endgame_plan_ids:
            option = options_by_id[item_id]
            if option.category == "mastery":
                mastery_by_species[item_id.split(":", 2)[1]].append(item_id)

        claim_sequences = [landmark_ids, *(
            tuple(sorted(
                mastery_by_species.get(species_id, ()),
                key=lambda item_id: (
                    options_by_id[item_id].growth_cost,
                    item_id,
                ),
            ))
            for species_id in facts.species_ids
            if mastery_by_species.get(species_id)
        )]
        for sequence in claim_sequences:
            for item_id in sequence:
                if item_id in state.permanent_owned:
                    continue
                option = options_by_id[item_id]
                required = option.growth_cost * GROWTH_UNITS_PER_POINT
                if state.endgame_funded_units[item_id] < required:
                    break
                if state.wallet < option.price_coins:
                    break
                state.wallet -= option.price_coins
                state.spent_coins += option.price_coins
                state.permanent_owned.add(item_id)
                state.purchases.append((day, item_id, option.price_coins))

    if scenario.strategy.buys_consumables and consumable is not None:
        # One-session cover prevents an unbounded repeatable sink and makes the
        # spend policy comparable across cohorts.
        if (
            _has_unfinished_planted_plant(state, facts)
            and
            state.wallet >= consumable.price_coins
            and state.inventory[consumable.item_id] < 1
            and state.consumable_effect_cards[consumable.item_id] < 1
            and (
                not consumable.item_id.startswith("fertilizer_")
                or len(state.fertilizer_activation_order_by_plant.get(
                    state.active_plant_index,
                    (),
                )) < 5
            )
        ):
            state.wallet -= consumable.price_coins
            state.spent_coins += consumable.price_coins
            state.consumable_units_purchased[consumable.item_id] += 1
            state.consumable_coins_spent[consumable.item_id] += consumable.price_coins
            consumable_fact = next((
                row for row in facts.consumables
                if row.consumable_id == consumable.item_id
            ), None)
            target_index = state.active_plant_index
            if (
                consumable_fact is not None
                and target_index is not None
                and consumable_fact.growth_per_card > 0
            ):
                # The public purchase action is explicitly “Buy and queue”;
                # it activates this purchased dose independently from the
                # user's stored-item auto-use policy.
                state.consumable_units_activated[consumable.item_id] += 1
                state.consumable_effect_cards[
                    consumable.item_id
                ] += consumable_fact.card_count
                state.consumable_active_batches.setdefault(
                    consumable.item_id,
                    [],
                ).append([
                    consumable_fact.card_count,
                    0,
                    target_index,
                ])
                if consumable_fact.consumable_kind.lower() == "fertilizer":
                    _enqueue_fertilizer_batch(
                        state,
                        target_index,
                        consumable.item_id,
                    )
            else:
                state.inventory[consumable.item_id] += 1
            state.purchases.append((day, consumable.item_id, consumable.price_coins))

    _record_catalog_completion_days(state, facts, day)


def _record_catalog_completion_days(
    state: RunState,
    facts: CatalogFacts,
    day: int,
) -> None:
    required = {
        option.item_id: option
        for option in facts.purchase_options
        if option.permanent and option.available and option.price_coins > 0
    }
    groups = {
        "functional": {
            item_id for item_id, option in required.items()
            if option.category in {"species", "garden_bonus", "scenery"}
        },
        "pre_endgame": {
            item_id for item_id, option in required.items()
            if option.category not in {"landmark", "mastery"}
        },
        "all_permanent": set(required),
    }
    for name, item_ids in groups.items():
        attribute = f"{name}_catalog_completion_day"
        if (
            getattr(state, attribute) is None
            and item_ids.issubset(state.permanent_owned)
        ):
            setattr(state, attribute, day)
    state.catalog_completion_day = state.functional_catalog_completion_day


def _equip_best_environment(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
) -> None:
    if scenario.strategy.optimize_for == "manual":
        # Production never auto-equips a discovery. Focused parity traces use
        # this explicit manual-loadout strategy so an ownership event can be
        # compared without inventing a user action.
        return
    objective = scenario.strategy.optimize_for or "growth"
    for category, attribute in (
        ("garden_bonus", "active_garden_bonus_id"),
        ("scenery", "active_scenery_id"),
    ):
        current = getattr(state, attribute)
        candidates = [
            option for option in facts.purchase_options
            if option.category == category
            and option.item_id in state.permanent_owned
        ]
        if not candidates:
            continue

        def score(option: PurchaseOption):
            growth, coins = _environment_daily_value(facts, option.item_id, scenario)
            value = coins if objective == "coin" else growth
            return (value, option.item_id == current, option.item_id)

        setattr(state, attribute, max(candidates, key=score).item_id)
    state.milestone_bonus_percent = sum(
        effect.grant.amount
        for effect in facts.effects_by_item_id.get(state.active_scenery_id, ())
        if effect.trigger == "plant_milestone"
        and effect.grant is not None
        and effect.grant.kind.lower() == "milestone_coin_percent"
    )


def _effect_trigger_count(
    state: RunState,
    effect,
    *,
    eligible_cards: int,
    complete: bool,
) -> int:
    if effect.trigger == "eligible_card":
        eligible = min(
            eligible_cards,
            effect.first_n_per_day or eligible_cards,
        )
        if effect.counter_scope in {"lifetime_active", "persistent_bank"}:
            before = state.effect_counters[effect.effect_id]
            after = before + eligible
            state.effect_counters[effect.effect_id] = after
            return after // effect.every_n - before // effect.every_n
        return eligible // effect.every_n
    if effect.trigger == "valid_completion" and complete:
        if effect.counter_scope == "lifetime_active":
            before = state.effect_counters[effect.effect_id]
            after = before + 1
            state.effect_counters[effect.effect_id] = after
            return after // effect.every_n - before // effect.every_n
        return 1 if effect.every_n == 1 else 0
    return 0


def _closest_checkpoint_plant_index(
    state: RunState,
    milestone_schedule: MilestoneSchedule,
) -> Optional[int]:
    """Match Firefly Lantern's remaining-Growth, then bed-order target."""

    candidates: List[Tuple[int, int]] = []
    for index in _planted_indices(state):
        current = state.plant_growth_units[index]
        next_boundary = next((
            boundary for boundary in milestone_schedule.positions
            if boundary > current
        ), None)
        if next_boundary is None:
            continue
        candidates.append((next_boundary - current, index))
    return min(candidates, default=(0, -1))[1] if candidates else None


def _apply_effect_grant(
    state: RunState,
    facts: CatalogFacts,
    grant,
    amount_multiplier: int,
    milestone_schedule: MilestoneSchedule,
    *,
    coin_source: str = "other",
    intended_plant_index: Optional[int] = None,
) -> None:
    amount = grant.amount * max(0, int(amount_multiplier))
    if amount <= 0:
        return
    kind = grant.kind.lower()
    if kind in {"growth", "instant_growth"}:
        units = amount * GROWTH_UNITS_PER_POINT
        state.environment_effect_growth_units += units
        _apply_growth(
            state,
            facts,
            units,
            milestone_schedule,
            intended_plant_index=intended_plant_index,
        )
    elif kind == "coins":
        _credit(state, coin_source, amount)
        state.environment_effect_coins += amount
    elif kind == "consumable" and grant.item_id:
        state.inventory[grant.item_id] += amount
        state.consumable_units_earned[grant.item_id] += amount
        state.environment_effect_consumables += amount


def _apply_environment_effects(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    seed_index: int,
    event: DayEvents,
    *,
    complete: bool,
    milestone_schedule: MilestoneSchedule,
    pre_shared_effect_ids: frozenset[str] = frozenset(),
) -> None:
    active_ids = (state.active_garden_bonus_id, state.active_scenery_id)
    for item_id in active_ids:
        coin_source = (
            "harvest_bell" if item_id == "harvest_bell"
            else "autumn_hearth" if item_id == "autumn"
            else "other"
        )
        for effect in facts.effects_by_item_id.get(item_id, ()):
            if effect.effect_id in pre_shared_effect_ids:
                continue
            triggers = _effect_trigger_count(
                state,
                effect,
                eligible_cards=event.answers,
                complete=complete,
            )
            if triggers and effect.grant is not None:
                if effect.grant.kind.lower() == "banked_growth":
                    banked = state.effect_banks[effect.effect_id]
                    banked += effect.grant.amount * triggers
                    if effect.bank_cap_growth is not None:
                        banked = min(banked, effect.bank_cap_growth)
                    state.effect_banks[effect.effect_id] = banked
                else:
                    closest_checkpoint = (
                        effect.effect_id
                        == "instant_growth_every_5_plus_3_closest_checkpoint"
                    )
                    for _grant_index in range(
                        triggers if closest_checkpoint else 1
                    ):
                        _apply_effect_grant(
                            state,
                            facts,
                            effect.grant,
                            1 if closest_checkpoint else triggers,
                            milestone_schedule,
                            coin_source=coin_source,
                            intended_plant_index=(
                                _closest_checkpoint_plant_index(
                                    state,
                                    milestone_schedule,
                                )
                                if closest_checkpoint else None
                            ),
                        )
            if triggers and effect.weighted_grants:
                total_weight = sum(weight for _grant, weight in effect.weighted_grants)
                for trigger_index in range(triggers):
                    sequence_key = f"{effect.effect_id}:weighted"
                    sequence = state.effect_counters[sequence_key]
                    state.effect_counters[sequence_key] += 1
                    if (
                        effect.effect_id == "halloween_completion_gift"
                        and event.production_reward_seed
                        and event.scheduler_day_id
                    ):
                        digest = blake2b(
                            (
                                f"{event.production_reward_seed}:"
                                f"{event.scheduler_day_id}"
                            ).encode("utf-8"),
                            digest_size=32,
                            person=b"halloween-gift",
                        ).digest()
                        draw = int.from_bytes(digest[:8], "big") % total_weight
                    else:
                        draw = StableRng(
                            config.seed_root,
                            seed_index,
                            scenario.cohort.cohort_id,
                            "environment_effect",
                            effect.effect_id,
                            sequence,
                            trigger_index,
                        ).below(total_weight)
                    selected = effect.weighted_grants[-1][0]
                    for grant, weight in effect.weighted_grants:
                        draw -= weight
                        if draw < 0:
                            selected = grant
                            break
                    _apply_effect_grant(
                        state,
                        facts,
                        selected,
                        1,
                        milestone_schedule,
                        coin_source=coin_source,
                    )
            if complete and effect.release_trigger == "valid_completion":
                banked = state.effect_banks[effect.effect_id]
                if banked:
                    state.effect_banks[effect.effect_id] = 0
                    units = banked * GROWTH_UNITS_PER_POINT
                    state.environment_effect_growth_units += units
                    _apply_growth(state, facts, units, milestone_schedule)


def _collect_pre_shared_environment_growth(
    state: RunState,
    facts: CatalogFacts,
    event: DayEvents,
    *,
    complete: bool,
) -> Tuple[int, frozenset[str]]:
    """Return ordinary equipped Growth included in the answer award.

    Production adds Garden Bonus and Scenery ``growth`` grants to the primary
    answer award before creating one independent Shared lane per other planted
    bed. Instant and banked Growth remain separate direct grants.
    """

    total_units = 0
    effect_ids = set()
    for item_id in (state.active_garden_bonus_id, state.active_scenery_id):
        for effect in facts.effects_by_item_id.get(item_id, ()):
            grant = effect.grant
            if (
                effect.trigger != "eligible_card"
                or grant is None
                or grant.kind.lower() != "growth"
            ):
                continue
            triggers = _effect_trigger_count(
                state,
                effect,
                eligible_cards=event.answers,
                complete=complete,
            )
            effect_ids.add(effect.effect_id)
            if triggers <= 0:
                continue
            units = grant.amount * triggers * GROWTH_UNITS_PER_POINT
            total_units += units
            state.environment_effect_growth_units += units
    return total_units, frozenset(effect_ids)


def _apply_firefly_review_day(
    state: RunState,
    facts: CatalogFacts,
    event: DayEvents,
    consumables_by_id: Mapping[str, object],
    milestone_schedule: MilestoneSchedule,
    *,
    rhythm_percent: int,
) -> frozenset[str]:
    """Interleave order-sensitive effects with ordinary review Growth.

    The ordinary accelerated path aggregates a day because every lane is
    linear. Firefly's closest target and a card-counted consumable's attached
    plant can change within a batch. Processing only those days card-by-card
    preserves production ordering without slowing the ordinary simulation.
    """

    firefly = next(
        (
            effect
            for effect in facts.effects_by_item_id.get(
                state.active_garden_bonus_id, ()
            )
            if effect.effect_id
            == "instant_growth_every_5_plus_3_closest_checkpoint"
        ),
        None,
    )
    handled = set()
    if firefly is not None:
        if firefly.grant is None:
            raise AssertionError(
                "Firefly Lantern is missing its catalog grant"
            )
        handled.add(firefly.effect_id)
    ordinary_growth_effects = tuple(
        effect
        for item_id in (
            state.active_garden_bonus_id,
            state.active_scenery_id,
        )
        for effect in facts.effects_by_item_id.get(item_id, ())
        if effect.trigger == "eligible_card"
        and effect.grant is not None
        and effect.grant.kind.lower() == "growth"
    )
    handled.update(effect.effect_id for effect in ordinary_growth_effects)

    base_per_answer = (
        facts.base_growth_per_review * GROWTH_UNITS_PER_POINT
        + facts.base_growth_per_review * max(0, int(rhythm_percent))
    )
    find_growth_by_answer = dict(event.find_growth_units_by_answer)
    for answer_number in range(1, max(0, int(event.answers)) + 1):
        consumable_units = _apply_active_consumable_growth(
            state,
            facts,
            consumables_by_id,
            1,
            milestone_schedule,
        )
        environment_units = 0
        for effect in ordinary_growth_effects:
            within_cap = (
                effect.first_n_per_day is None
                or answer_number <= effect.first_n_per_day
            )
            if effect.counter_scope in {
                "lifetime_active",
                "persistent_bank",
            }:
                before = state.effect_counters[effect.effect_id]
                after = before + int(within_cap)
                state.effect_counters[effect.effect_id] = after
                triggered = (
                    after // max(1, effect.every_n)
                    > before // max(1, effect.every_n)
                )
            else:
                triggered = bool(
                    within_cap
                    and answer_number % max(1, effect.every_n) == 0
                )
            if triggered:
                units = effect.grant.amount * GROWTH_UNITS_PER_POINT
                environment_units += units
                state.environment_effect_growth_units += units
        _apply_review_growth(
            state,
            facts,
            base_per_answer + consumable_units + environment_units,
            milestone_schedule,
        )

        if firefly is not None:
            before = state.effect_counters[firefly.effect_id]
            after = before + 1
            state.effect_counters[firefly.effect_id] = after
            if after // max(1, firefly.every_n) > before // max(
                1, firefly.every_n
            ):
                _apply_effect_grant(
                    state,
                    facts,
                    firefly.grant,
                    1,
                    milestone_schedule,
                    intended_plant_index=_closest_checkpoint_plant_index(
                        state,
                        milestone_schedule,
                    ),
                )
        find_units = max(
            0,
            int(find_growth_by_answer.get(answer_number, 0)),
        )
        if find_units:
            _apply_growth(
                state,
                facts,
                find_units,
                milestone_schedule,
            )
    return frozenset(handled)


def _consume_inventory_growth(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    options_by_id: Mapping[str, PurchaseOption],
    consumables_by_id: Mapping[str, object],
    milestone_schedule: MilestoneSchedule,
    *,
    answers: int,
    complete: bool,
) -> None:
    # At most one of each stored item per study day. Card-count effects are
    # activated, not front-loaded; instant Growth is applied immediately.
    policy = scenario.strategy.consumable_policy
    activate = (
        policy in {"use_immediately", "purchase_none_use_earned", "consumable_heavy"}
        or (policy == "save_for_100_card_session" and answers >= 100)
        or (policy == "save_until_today_cards_completion" and complete)
    )
    if not activate:
        return
    if not _has_unfinished_planted_plant(state, facts):
        # Production requires an unfinished planted target. Earned inventory
        # remains untouched while every legal plant is Full Bloom.
        return
    target_plant_index = state.active_plant_index
    if target_plant_index is None:
        return
    for item_id in tuple(sorted(state.inventory)):
        if state.inventory[item_id] <= 0:
            continue
        option = options_by_id.get(item_id)
        consumable = consumables_by_id.get(item_id)
        if option is None or consumable is None or option.growth_value <= 0:
            continue
        if (
            consumable.consumable_kind.lower() == "fertilizer"
            and len(state.fertilizer_activation_order_by_plant.get(
                target_plant_index,
                (),
            )) >= 5
        ):
            # Production keeps the stored dose when the target's active plus
            # queued Fertilizer schedule has reached its five-dose cap.
            continue
        state.inventory[item_id] -= 1
        state.consumable_units_activated[item_id] += 1
        card_count = consumable.card_count
        if consumable.growth_per_card:
            is_booster = consumable.consumable_kind.lower() == "booster"
            extension_cards = sum(
                effect.grant.amount
                for effect in facts.effects_by_item_id.get(
                    state.active_garden_bonus_id, ()
                )
                if effect.trigger == "booster_activation"
                and effect.grant is not None
                and effect.grant.kind.lower() == "booster_card_limit"
            ) if is_booster else 0
            card_count += extension_cards
            state.consumable_effect_cards[item_id] += card_count
            state.environment_extension_cards[item_id] += extension_cards
            state.consumable_active_batches.setdefault(item_id, []).append([
                card_count,
                extension_cards,
                target_plant_index,
            ])
            if consumable.consumable_kind.lower() == "fertilizer":
                _enqueue_fertilizer_batch(
                    state,
                    target_plant_index,
                    item_id,
                )
        if consumable.instant_growth:
            units = consumable.instant_growth * GROWTH_UNITS_PER_POINT
            state.consumable_growth_units += units
            state.consumable_growth_by_item_units[item_id] += units
            state.consumable_units_consumed[item_id] += 1
            _apply_growth(state, facts, units, milestone_schedule)


def _apply_active_consumable_growth(
    state: RunState,
    facts: CatalogFacts,
    consumables_by_id: Mapping[str, object],
    answers: int,
    milestone_schedule: MilestoneSchedule,
) -> int:
    del milestone_schedule
    if not _has_unfinished_planted_plant(state, facts):
        return 0
    active_plant_index = state.active_plant_index
    if active_plant_index is None:
        return 0
    total_units = 0

    def batch_plant_index(batch: Sequence[int]) -> int:
        return (
            int(batch[2])
            if len(batch) >= 3
            else int(active_plant_index)
        )

    def consume_batch(
        item_id: str,
        batch_index: int,
        maximum_cards: int,
    ) -> int:
        nonlocal total_units
        batches = state.consumable_active_batches[item_id]
        consumable = consumables_by_id.get(item_id)
        if consumable is None or consumable.growth_per_card <= 0:
            return 0
        batch = batches[batch_index]
        batch_remaining = max(0, int(batch[0]))
        batch_extension = max(0, int(batch[1]))
        affected = min(max(0, int(maximum_cards)), batch_remaining)
        if affected <= 0:
            return 0
        base_remaining = max(0, batch_remaining - batch_extension)
        extension_affected = max(0, affected - base_remaining)
        batch_remaining -= affected
        batch_extension -= extension_affected
        plant_index = batch_plant_index(batch)
        if batch_remaining == 0:
            batches.pop(batch_index)
            state.consumable_units_consumed[item_id] += 1
        else:
            batches[batch_index] = [
                batch_remaining,
                batch_extension,
                plant_index,
            ]
        state.consumable_effect_cards[item_id] = sum(
            batch[0] for batch in batches
        )
        state.environment_extension_cards[item_id] = sum(
            batch[1] for batch in batches
        )
        units = affected * consumable.growth_per_card * GROWTH_UNITS_PER_POINT
        state.consumable_growth_units += units
        state.consumable_growth_by_item_units[item_id] += units
        state.environment_effect_growth_units += (
            extension_affected
            * consumable.growth_per_card
            * GROWTH_UNITS_PER_POINT
        )
        total_units += units
        return affected

    # Fertilizer doses form one ordered queue per plant. Different tiers do
    # not stack; the next dose begins only after the current one is exhausted.
    # Booster remains a separate family and may stack with Fertilizer.
    fertilizer_order = state.fertilizer_activation_order_by_plant.setdefault(
        active_plant_index,
        [],
    )
    fertilizer_cards_left = max(0, int(answers))
    while fertilizer_order and fertilizer_cards_left > 0:
        item_id = fertilizer_order[0]
        batches = state.consumable_active_batches.get(item_id, [])
        batch_index = next((
            index
            for index, batch in enumerate(batches)
            if batch_plant_index(batch) == active_plant_index
            and max(0, int(batch[0])) > 0
        ), None)
        if batch_index is None:
            fertilizer_order.pop(0)
            continue
        batch_remaining_before = max(
            0,
            int(batches[batch_index][0]),
        )
        affected = consume_batch(
            item_id,
            batch_index,
            fertilizer_cards_left,
        )
        fertilizer_cards_left -= affected
        if affected <= 0:
            break
        if affected >= batch_remaining_before:
            fertilizer_order.pop(0)

    for item_id in tuple(sorted(state.consumable_active_batches)):
        consumable = consumables_by_id.get(item_id)
        if (
            consumable is None
            or consumable.consumable_kind.lower() == "fertilizer"
        ):
            continue
        cards_left = max(0, int(answers))
        while cards_left > 0:
            batches = state.consumable_active_batches[item_id]
            batch_index = next((
                index
                for index, batch in enumerate(batches)
                if batch_plant_index(batch) == active_plant_index
                and max(0, int(batch[0])) > 0
            ), None)
            if batch_index is None:
                break
            affected = consume_batch(item_id, batch_index, cards_left)
            if affected <= 0:
                break
            cards_left -= affected
    return total_units


def _progression_counts(
    state: RunState,
    facts: CatalogFacts,
) -> Tuple[int, int]:
    """Return exact per-plant Mature and Full Bloom counts."""

    full_units = facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    mature_threshold = next(
        (
            stage.threshold_growth
            for stage in facts.stages
            if "mature" in stage.stage_id.lower()
        ),
        facts.stages[-2].threshold_growth,
    ) * GROWTH_UNITS_PER_POINT
    plant_units = tuple(state.plant_growth_units[:state.species_owned])
    return (
        sum(units >= mature_threshold for units in plant_units),
        sum(units >= full_units for units in plant_units),
    )


def _record_progression_days(state: RunState, facts: CatalogFacts, day: int) -> None:
    _mature, full_blooms = _progression_counts(state, facts)
    if full_blooms >= 1 and state.first_full_bloom_day is None:
        state.first_full_bloom_day = day
    if (
        full_blooms >= len(facts.species_ids)
        and state.all_catalog_full_bloom_day is None
    ):
        state.all_catalog_full_bloom_day = day


def _claim_achievements(
    state: RunState,
    facts: CatalogFacts,
    *,
    event_answers: int,
    achievements_by_metric: Mapping[str, Sequence[object]],
    beds_by_item_id: Mapping[str, int],
    milestone_schedule: MilestoneSchedule,
) -> None:
    """Apply one-time catalog achievement grants to the simulation ledger."""

    mature_plants, full_blooms = _progression_counts(state, facts)
    progress = {
        "streak_days": state.study_run,
        "daily_answers": event_answers,
        "lifetime_answers": state.answers,
        "valid_all_due_days": state.completed_days,
        "mature_plants": mature_plants,
        "unique_full_blooms": full_blooms,
        "valid_completions": state.completed_days,
        # Recall-quality distributions are outside the approved cohort inputs;
        # leaving this at zero prevents inventing a completion rate.
        "consecutive_non_again": 0,
    }
    for metric, value in progress.items():
        achievements = achievements_by_metric.get(metric, ())
        cursor = state.achievement_cursors.get(metric, 0)
        while cursor < len(achievements):
            achievement = achievements[cursor]
            if value < achievement.progress_target:
                break
            if event_answers >= achievement.minimum_answers:
                state.claimed_achievements.add(achievement.achievement_id)
                for grant in achievement.rewards:
                    kind = grant.kind.lower()
                    if kind == "coins":
                        _credit(state, "achievement", grant.amount)
                    elif kind in {"growth", "instant_growth", "banked_growth"}:
                        # No current achievement uses direct Growth, but keeping
                        # the catalog grant general avoids a future omission.
                        units = grant.amount * GROWTH_UNITS_PER_POINT
                        _apply_growth(
                            state,
                            facts,
                            units,
                            milestone_schedule,
                        )
                    elif kind == "consumable" and grant.item_id:
                        state.inventory[grant.item_id] += grant.amount
                        state.consumable_units_earned[grant.item_id] += grant.amount
                    elif kind == "cosmetic" and grant.item_id:
                        state.permanent_owned.add(grant.item_id)
                    elif kind == "bed_unlock" and grant.item_id:
                        state.permanent_owned.add(grant.item_id)
                        state.beds_owned = max(
                            state.beds_owned,
                            beds_by_item_id.get(grant.item_id, state.beds_owned),
                        )
            cursor += 1
        state.achievement_cursors[metric] = cursor


def _checkpoint_metrics(state: RunState, facts: CatalogFacts) -> Mapping[str, Optional[float]]:
    shares = [value / state.gross_coins for value in state.coin_sources.values()] if state.gross_coins else []
    permanent_count = sum(
        1 for option in facts.purchase_options
        if option.permanent and option.item_id in state.permanent_owned
    )
    endgame_options = tuple(
        option for option in facts.purchase_options
        if option.category in {"landmark", "mastery"}
    )
    funded = {
        option.item_id
        for option in endgame_options
        if state.endgame_funded_units[option.item_id]
        >= option.growth_cost * GROWTH_UNITS_PER_POINT
    }
    landmark_options = tuple(
        sorted(
            (option for option in endgame_options if option.category == "landmark"),
            key=lambda option: (option.growth_cost, option.item_id),
        )
    )
    mastery_by_species: MutableMapping[str, List[PurchaseOption]] = defaultdict(list)
    for option in endgame_options:
        if option.category == "mastery":
            mastery_by_species[option.item_id.split(":", 2)[1]].append(option)
    claimable_ids = []
    for sequence in (
        landmark_options,
        *(
            tuple(sorted(rows, key=lambda option: (option.growth_cost, option.item_id)))
            for _species, rows in sorted(mastery_by_species.items())
        ),
    ):
        for option in sequence:
            if option.item_id in state.permanent_owned:
                continue
            if option.item_id in funded:
                claimable_ids.append(option.item_id)
            break
    all_permanent_remaining = sum(
        option.price_coins
        for option in facts.purchase_options
        if option.permanent
        and option.available
        and option.price_coins > 0
        and option.item_id not in state.permanent_owned
    )
    finite_growth_capacity_units = sum(
        option.growth_cost * GROWTH_UNITS_PER_POINT
        for option in endgame_options
    )
    finite_growth_remaining_units = sum(
        max(
            0,
            option.growth_cost * GROWTH_UNITS_PER_POINT
            - state.endgame_funded_units[option.item_id],
        )
        for option in endgame_options
    )
    finite_targets_remaining = sum(
        state.endgame_funded_units[option.item_id]
        < option.growth_cost * GROWTH_UNITS_PER_POINT
        for option in endgame_options
    )
    finite_coin_claim_demand_remaining = sum(
        option.price_coins
        for option in endgame_options
        if option.item_id not in state.permanent_owned
    )
    active_project_selected = state.auto_fund_endgame
    no_project_preservation_delta_units = (
        state.routed_to_storage_units_lifetime - state.stored_growth_units
    )
    metrics: Dict[str, Optional[float]] = {
        "answers.total": state.answers,
        "days.studied": state.studied_days,
        "days.completed": state.completed_days,
        "growth.total_units": state.total_growth_units,
        "growth.generated_units": state.total_growth_units,
        "growth.opening_plant_units": state.opening_plant_growth_units,
        "growth.applied_units": state.applied_growth_units,
        "growth.applied_to_plants_units": state.applied_growth_units,
        "growth.stored_balance_units": state.stored_growth_units,
        "growth.routed_to_storage_units_lifetime": (
            state.routed_to_storage_units_lifetime
        ),
        "growth.contributed_to_landmarks_units": (
            state.growth_contributed_to_landmarks_units
        ),
        "growth.contributed_to_mastery_units": (
            state.growth_contributed_to_mastery_units
        ),
        "growth.contributed_to_legacy_units": (
            state.growth_contributed_to_legacy_units
        ),
        "growth.unallocated_overflow_units": state.unallocated_overflow_units,
        "growth.shared_units": state.shared_growth_units,
        "growth.spent_units": state.growth_spent_units,
        "plants.full_bloom": sum(
            units >= facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
            for units in state.plant_growth_units[:state.species_owned]
        ),
        "plants.first_full_bloom_day": state.first_full_bloom_day,
        "plants.all_catalog_full_bloom_day": state.all_catalog_full_bloom_day,
        "beds.owned": state.beds_owned,
        "achievements.claimed": len(state.claimed_achievements),
        "coins.gross": state.gross_coins,
        "coins.gross_without_completion_rewards": (
            state.gross_coins
            - state.coin_sources["todays_cards"]
            - state.coin_sources["all_due"]
            - state.coin_sources["completion_cycle_5"]
        ),
        "coins.spent": state.spent_coins,
        "coins.ending": state.wallet,
        "coins.top_source_share": max(shares, default=0.0),
        "coins.source_hhi": sum(value * value for value in shares),
        "growth.total_units_per_answer": (
            state.total_growth_units / state.answers if state.answers else 0.0
        ),
        "coins.gross_per_100_answers": (
            state.gross_coins * 100 / state.answers if state.answers else 0.0
        ),
        "finds.per_1000_answers": (
            state.finds * 1000 / state.answers if state.answers else 0.0
        ),
        "finds.total": state.finds,
        "finds.coins": state.find_coins,
        "finds.growth_units": state.find_growth_units,
        "finds.inventory_units": state.find_inventory_units,
        "finds.capped_days": state.capped_days,
        "finds.maximum_attempted_gap": state.maximum_gap,
        "catalog.permanent_owned": permanent_count,
        "catalog.completion_day": state.catalog_completion_day,
        "catalog.functional_completion_day": state.functional_catalog_completion_day,
        "catalog.pre_endgame_completion_day": state.pre_endgame_catalog_completion_day,
        "catalog.all_permanent_completion_day": state.all_permanent_catalog_completion_day,
        "catalog.all_permanent_remaining_coins": all_permanent_remaining,
        "catalog.finite_permanent_remaining_coins": all_permanent_remaining,
        "environments.discovered": state.environment_owned,
        "environments.effect_growth_units": state.environment_effect_growth_units,
        "environments.effect_coins": state.environment_effect_coins,
        "environments.effect_consumables": state.environment_effect_consumables,
        "inventory.units": sum(state.inventory.values()),
        "inventory.effect_cards_remaining": sum(state.consumable_effect_cards.values()),
        "consumables.growth_units": state.consumable_growth_units,
        "landmarks.owned": sum(
            1 for option in facts.purchase_options
            if option.category == "landmark" and option.item_id in state.permanent_owned
        ),
        "landmarks.growth_funded_units": sum(
            state.endgame_funded_units[option.item_id]
            for option in landmark_options
        ),
        "landmarks.tiers_funded": sum(
            option.item_id in funded for option in landmark_options
        ),
        "landmarks.tiers_claimed": sum(
            option.item_id in state.permanent_owned for option in landmark_options
        ),
        "landmarks.tiers_claimable": sum(
            item_id in claimable_ids
            for item_id in (option.item_id for option in landmark_options)
        ),
        "mastery.owned": sum(
            1 for option in facts.purchase_options
            if option.category == "mastery" and option.item_id in state.permanent_owned
        ),
        "mastery.growth_funded_units": sum(
            state.endgame_funded_units[option.item_id]
            for option in endgame_options
            if option.category == "mastery"
        ),
        "mastery.ranks_funded": sum(
            option.item_id in funded
            for option in endgame_options
            if option.category == "mastery"
        ),
        "mastery.ranks_claimed": sum(
            option.item_id in state.permanent_owned
            for option in endgame_options
            if option.category == "mastery"
        ),
        "mastery.ranks_claimable": sum(
            item_id in claimable_ids
            for item_id in (
                option.item_id for option in endgame_options
                if option.category == "mastery"
            )
        ),
        "legacy.level": state.garden_legacy_level,
        "legacy.progress_units": state.garden_legacy_progress_units,
        "coins.required_for_claimable_content": sum(
            next(
                option.price_coins for option in endgame_options
                if option.item_id == item_id
            )
            for item_id in claimable_ids
        ),
        "endgame.finite_coin_claim_demand_remaining": (
            finite_coin_claim_demand_remaining
        ),
        "endgame.finite_growth_capacity_units": finite_growth_capacity_units,
        "endgame.finite_growth_remaining_units": finite_growth_remaining_units,
        "endgame.finite_targets_remaining": finite_targets_remaining,
        "endgame.finite_growth_fully_funded": int(
            finite_growth_remaining_units == 0
        ),
        "endgame.active_project_selected": int(active_project_selected),
        "endgame.active_project_unallocated_stored_units": (
            state.stored_growth_units if active_project_selected else None
        ),
        "endgame.active_project_no_unallocated_storage": (
            int(state.stored_growth_units == 0)
            if active_project_selected else None
        ),
        "endgame.no_project_reserve_units": (
            state.stored_growth_units if not active_project_selected else None
        ),
        "endgame.no_project_preservation_delta_units": (
            no_project_preservation_delta_units
            if not active_project_selected else None
        ),
        "endgame.no_project_preserves_entire_reserve": (
            int(
                no_project_preservation_delta_units == 0
                and state.manual_project_contributions_units == 0
            )
            if not active_project_selected else None
        ),
    }
    for source_id in sorted(set(COIN_SOURCE_IDS) | set(state.coin_sources)):
        metrics[f"coins.source.{source_id}"] = state.coin_sources[source_id]
    for species_id in facts.species_ids:
        rows = tuple(sorted(
            mastery_by_species.get(species_id, ()),
            key=lambda option: (option.growth_cost, option.item_id),
        ))
        prefix = f"mastery.{species_id}."
        metrics[prefix + "growth_funded_units"] = sum(
            state.endgame_funded_units[option.item_id]
            for option in rows
        )
        metrics[prefix + "ranks_claimed"] = sum(
            option.item_id in state.permanent_owned for option in rows
        )
        metrics[prefix + "ranks_claimable"] = sum(
            option.item_id in claimable_ids for option in rows
        )
    for consumable in facts.consumables:
        item_id = consumable.consumable_id
        prefix = f"consumables.{item_id}."
        cards_of_effect_remaining = state.consumable_effect_cards[item_id]
        growth_generated = state.consumable_growth_by_item_units[item_id]
        metrics.update({
            prefix + "units_earned": state.consumable_units_earned[item_id],
            prefix + "units_purchased": state.consumable_units_purchased[item_id],
            prefix + "units_activated": state.consumable_units_activated[item_id],
            prefix + "units_consumed": state.consumable_units_consumed[item_id],
            prefix + "units_remaining": state.inventory[item_id],
            prefix + "cards_of_effect_remaining": cards_of_effect_remaining,
            prefix + "growth_generated": growth_generated,
            prefix + "coins_spent": state.consumable_coins_spent[item_id],
            # Frozen source-analysis aliases. New consumers use the canonical
            # fields above so report copy does not leak unit conventions.
            prefix + "effect_cards_remaining": cards_of_effect_remaining,
            prefix + "growth_generated_units": growth_generated,
        })
    any_tier_simultaneous_forced = int(any(
        value > 0
        for value in state.environment_simultaneous_forced_by_tier.values()
    ))
    metrics["environments.any_tier_simultaneous_forced_user"] = (
        any_tier_simultaneous_forced
    )
    # Compatibility aggregate. Its statistic mean is the percentage of users;
    # the new singular field makes clear that each seed contributes 0 or 1.
    metrics["environments.simultaneous_forced_user_rate"] = (
        any_tier_simultaneous_forced
    )
    for tier in facts.environment_tiers:
        tier_id = tier.tier_id
        prefix = f"environments.{tier_id}."
        simultaneous_forced = state.environment_simultaneous_forced_by_tier[
            tier_id
        ]
        blocked_card_checks = state.environment_blocked_cards_by_tier[tier_id]
        blocked_completion_checks = (
            state.environment_blocked_completions_by_tier[tier_id]
        )
        blocked_checks = blocked_card_checks + blocked_completion_checks
        check_opportunities = state.answers + state.completed_days
        metrics.update({
            prefix + "first_discovery_day": state.environment_first_day_by_tier.get(tier_id),
            prefix + "both_items_completion_day": state.environment_both_day_by_tier.get(tier_id),
            prefix + "first_discovery_eligible_card": state.environment_first_card_by_tier.get(tier_id),
            prefix + "both_items_completion_eligible_card": state.environment_both_card_by_tier.get(tier_id),
            prefix + "natural_acquisitions": state.environment_acquisitions_by_tier_route[(tier_id, "natural")],
            prefix + "card_pity_acquisitions": state.environment_acquisitions_by_tier_route[(tier_id, "card_pity")],
            prefix + "completion_pity_acquisitions": state.environment_acquisitions_by_tier_route[(tier_id, "completion_pity")],
            prefix + "simultaneous_forced_acquisitions": simultaneous_forced,
            # Per-seed indicators/rates make the requested percentages
            # directly aggregatable as the statistic mean.
            prefix + "simultaneous_forced_user_rate": int(
                simultaneous_forced > 0
            ),
            prefix + "ownership_blocked_card_checks": blocked_card_checks,
            prefix + "ownership_blocked_completion_checks": (
                blocked_completion_checks
            ),
            prefix + "ownership_blocked_checks": blocked_checks,
            prefix + "ownership_check_opportunities": check_opportunities,
            prefix + "ownership_suppression_rate": (
                blocked_checks / check_opportunities
                if check_opportunities else 0.0
            ),
        })
    return metrics


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    seed_index: int
    checkpoints: Mapping[int, Mapping[str, Optional[float]]]
    assertion_failures: Tuple[str, ...]
    trace_rows: Tuple[Mapping[str, object], ...] = ()
    release_state_rows: Tuple[Mapping[str, object], ...] = ()


def _annual_release_state_row(
    state: RunState,
    facts: CatalogFacts,
) -> Mapping[str, object]:
    categories = {
        option.item_id: option.category
        for option in facts.purchase_options
    }
    options_by_id = _endgame_option_by_id(facts)
    targets = _endgame_target_plan(state, facts)
    active_index = max(0, int(state.endgame_active_target_index))
    active_target = None
    if state.auto_fund_endgame:
        if active_index < len(targets):
            target_type, target_id, _option_ids = targets[active_index]
            active_target = {
                "target_type": target_type,
                "target_id": target_id,
            }
        elif _finite_endgame_fully_funded(state, options_by_id):
            active_target = {
                "target_type": "legacy",
                "target_id": "garden_legacy",
            }

    landmark_ids = next((
        option_ids for target_type, _target_id, option_ids in targets
        if target_type == "landmark"
    ), ())
    landmark_funded = sum(
        max(0, int(state.endgame_funded_units[item_id]))
        for item_id in landmark_ids
    )
    landmark_claimed = 0
    for item_id in landmark_ids:
        if item_id not in state.permanent_owned:
            break
        landmark_claimed += 1

    mastery_funding: Dict[str, int] = {}
    mastery_claims: Dict[str, str] = {}
    for target_type, species_id, option_ids in targets:
        if target_type != "mastery":
            continue
        mastery_funding[species_id] = sum(
            max(0, int(state.endgame_funded_units[item_id]))
            for item_id in option_ids
        )
        highest_rank = ""
        for item_id in option_ids:
            if item_id not in state.permanent_owned:
                break
            highest_rank = item_id.rsplit(":", 1)[-1]
        if highest_rank:
            mastery_claims[species_id] = highest_rank

    return {
        "find_drought_counter": max(0, int(state.find_drought_counter)),
        "daily_find_cap_and_count": {
            "cap": max(0, int(state.daily_find_cap)),
            "count": max(0, int(state.daily_find_count)),
        },
        "environment_pity_counters": {
            "card": dict(sorted(state.environment_card_pity.items())),
            "completion": dict(sorted(
                state.environment_completion_pity.items()
            )),
        },
        "environment_ownership": {
            "garden_features": tuple(sorted(
                item_id for item_id in state.permanent_owned
                if categories.get(item_id) == "garden_bonus"
            )),
            "scenery": tuple(sorted(
                item_id for item_id in state.permanent_owned
                if categories.get(item_id) == "scenery"
            )),
        },
        # Extra exact authority used to drive public endgame actions in the
        # annual replay. The four release-gate fields above remain compared
        # directly rather than inferred from these project aggregates.
        "active_growth_target": active_target,
        "landmark_funding": landmark_funded,
        "landmark_claims": landmark_claimed,
        "mastery_funding_by_species": dict(sorted(
            mastery_funding.items()
        )),
        "mastery_claims": dict(sorted(
            mastery_claims.items()
        )),
        "garden_legacy_progress": {
            "level": max(0, int(state.garden_legacy_level)),
            "progress_units": max(
                0, int(state.garden_legacy_progress_units)
            ),
        },
        "plant_exact_growth_units": dict(sorted(
            (
                species_id,
                max(0, int(state.plant_growth_units[index])),
            )
            for index, species_id in enumerate(state.plant_species_ids)
            if index < len(state.plant_growth_units)
        )),
        "active_plant_species_id": (
            state.plant_species_ids[state.active_plant_index]
            if state.active_plant_index is not None
            and state.active_plant_index < len(state.plant_species_ids)
            else ""
        ),
        "opening_plant_growth_units": max(
            0, int(state.opening_plant_growth_units)
        ),
    }


def simulate_scenario(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    seed_index: int,
    events: Optional[Sequence[DayEvents]] = None,
    capture_trace: bool = False,
) -> ScenarioOutcome:
    stream = tuple(events or generate_event_stream(facts, scenario, config, seed_index))
    state = _initial_state(facts, scenario)
    _equip_best_environment(state, facts, scenario)
    permanent_plan = _permanent_priority(facts, scenario)
    consumable = _best_consumable(
        facts.purchase_options,
        scenario.strategy.optimize_for or "growth",
    )
    options_by_id = {option.item_id: option for option in facts.purchase_options}
    consumables_by_id = {
        row.consumable_id: row for row in facts.consumables
    }
    achievement_rows: MutableMapping[str, List[object]] = defaultdict(list)
    for achievement in facts.achievements:
        achievement_rows[achievement.progress_metric].append(achievement)
    achievements_by_metric = {
        metric: tuple(sorted(rows, key=lambda row: (row.progress_target, row.achievement_id)))
        for metric, rows in achievement_rows.items()
    }
    beds_by_item_id = {
        f"bed_{row.bed_number}": row.bed_number
        for row in facts.bed_unlocks
    }
    # Crossings are tracked independently for each plant. A one-plant schedule
    # is therefore reused for every routed Growth lane.
    milestone_schedule = _milestone_schedule(facts, 1)
    checkpoints = {}
    trace_rows = []
    release_state_rows = []
    active_index = 0
    previous_study_calendar_day = 0

    for event in stream:
        complete = False
        rhythm_percent = 0
        if event.study:
            active_index += 1
            state.studied_days += 1
            state.answers += event.answers
            state.study_run = (
                state.study_run + 1
                if previous_study_calendar_day == event.day - 1 else 1
            )
            complete = completes_study_day(active_index, scenario.completion_percent)
            if complete:
                state.completed_days += 1

            _credit(state, "first_eligible_answer", facts.daily_activity_coins)
            if complete:
                _credit(state, "todays_cards", facts.completion_coins)
                state.garden_cycle_remainder += 1
                if (
                    state.garden_cycle_remainder
                    >= facts.garden_cycle_completions
                ):
                    state.garden_cycle_remainder = 0
                    _credit(
                        state,
                        "completion_cycle_5",
                        facts.garden_cycle_coins,
                    )
            # Production folds only the first seven-day cycle into the
            # streak_7 achievement's identical 10-Coin payout.  After a gap,
            # a later streak may reach seven again; because the achievement
            # is already owned, that cycle uses the recurring source.
            if (
                state.study_run % 7 == 0
                and (
                    state.study_run != 7
                    or "streak_7" in state.claimed_achievements
                )
            ):
                _credit(
                    state,
                    "seven_day_streak_cycle",
                    facts.weekly_streak_coins,
                )

            rhythm_percent = facts.rhythm_percent(
                sum(state.recent_completion_flags[-7:])
            )
            _consume_inventory_growth(
                state,
                facts,
                scenario,
                options_by_id,
                consumables_by_id,
                milestone_schedule,
                answers=event.answers,
                complete=complete,
            )
            active_consumable_is_order_sensitive = any(
                max(0, int(batch[0])) > 0
                and (
                    len(batch) < 3
                    or int(batch[2]) == state.active_plant_index
                )
                for batches in state.consumable_active_batches.values()
                for batch in batches
            )
            if (
                state.active_garden_bonus_id == "firefly_lantern"
                or active_consumable_is_order_sensitive
                or bool(event.find_growth_units_by_answer)
            ):
                pre_shared_effect_ids = _apply_firefly_review_day(
                    state,
                    facts,
                    event,
                    consumables_by_id,
                    milestone_schedule,
                    rhythm_percent=rhythm_percent,
                )
            else:
                consumable_primary_units = _apply_active_consumable_growth(
                    state,
                    facts,
                    consumables_by_id,
                    event.answers,
                    milestone_schedule,
                )
                environment_primary_units, pre_shared_effect_ids = (
                    _collect_pre_shared_environment_growth(
                        state,
                        facts,
                        event,
                        complete=complete,
                    )
                )
                primary_units = (
                    event.answers
                    * (
                        facts.base_growth_per_review
                        * GROWTH_UNITS_PER_POINT
                        + facts.base_growth_per_review * rhythm_percent
                    )
                    + consumable_primary_units
                    + environment_primary_units
                )
                _apply_review_growth(
                    state,
                    facts,
                    primary_units,
                    milestone_schedule,
                )
            if not event.find_growth_units_by_answer:
                _apply_growth(
                    state,
                    facts,
                    event.find_growth_units,
                    milestone_schedule,
                )
            _apply_environment_effects(
                state,
                facts,
                scenario,
                config,
                seed_index,
                event,
                complete=complete,
                milestone_schedule=milestone_schedule,
                pre_shared_effect_ids=pre_shared_effect_ids,
            )
            _record_progression_days(state, facts, event.day)
            state.recent_completion_flags.append(complete)
            previous_study_calendar_day = event.day
        state.finds += event.standard_finds
        state.find_coins += event.find_coins
        state.find_growth_units += event.find_growth_units
        state.find_inventory_units += len(event.inventory_items)
        state.capped_days += int(event.capped)
        state.maximum_gap = max(state.maximum_gap, event.maximum_gap)
        state.find_drought_counter = max(
            0, int(event.find_drought_counter_after)
        )
        state.daily_find_cap = max(0, int(event.daily_find_cap_after))
        state.daily_find_count = max(0, int(event.standard_finds))
        state.environment_card_pity = {
            str(tier): max(0, int(value))
            for tier, value in event.environment_card_pity_after
        }
        state.environment_completion_pity = {
            str(tier): max(0, int(value))
            for tier, value in event.environment_completion_pity_after
        }
        if event.find_coins:
            _credit(state, "standard_find", event.find_coins)
        for item_id in event.inventory_items:
            state.inventory[item_id] += 1
            state.consumable_units_earned[item_id] += 1
        ownership_changed = False
        for discovery in event.environment_discoveries:
            item_id = discovery.item_id
            ownership_changed = ownership_changed or item_id not in state.permanent_owned
            if item_id not in state.permanent_owned:
                tier_id = discovery.tier_id
                owned_before = state.environment_owned_count_by_tier[tier_id]
                state.environment_owned_count_by_tier[tier_id] += 1
                state.environment_acquisitions_by_tier_route[
                    (tier_id, discovery.route)
                ] += 1
                if discovery.simultaneous_forced:
                    state.environment_simultaneous_forced_by_tier[tier_id] += 1
                if owned_before == 0:
                    state.environment_first_day_by_tier[tier_id] = event.day
                    state.environment_first_card_by_tier[tier_id] = (
                        discovery.eligible_card_index
                    )
                if state.environment_owned_count_by_tier[tier_id] == 2:
                    state.environment_both_day_by_tier[tier_id] = event.day
                    state.environment_both_card_by_tier[tier_id] = (
                        discovery.eligible_card_index
                    )
            state.permanent_owned.add(item_id)
        if scenario.all_environments_owned:
            # The generated event stream is paired across strategies and starts
            # from an unowned discovery state.  This edge case deliberately
            # starts production fully owned, so every otherwise-eligible card
            # and completion check is ownership-suppressed from the outset.
            for tier in facts.environment_tiers:
                state.environment_blocked_cards_by_tier[
                    tier.tier_id
                ] += max(0, int(event.answers))
                state.environment_blocked_completions_by_tier[
                    tier.tier_id
                ] += int(complete)
        else:
            for tier_id, count in event.environment_blocked_card_checks:
                state.environment_blocked_cards_by_tier[tier_id] += count
            for tier_id, count in event.environment_blocked_completion_checks:
                state.environment_blocked_completions_by_tier[tier_id] += count
        if scenario.all_environments_owned:
            ownership_changed = ownership_changed or not set(
                facts.environment_discovery_ids
            ).issubset(state.permanent_owned)
            state.permanent_owned.update(facts.environment_discovery_ids)
        state.environment_owned = sum(
            item_id in state.permanent_owned
            for item_id in facts.environment_discovery_ids
        )

        if event.study:
            _claim_achievements(
                state,
                facts,
                event_answers=event.answers,
                achievements_by_metric=achievements_by_metric,
                beds_by_item_id=beds_by_item_id,
                milestone_schedule=milestone_schedule,
            )

        permanent_count_before_purchase = len(state.permanent_owned)
        _purchase_day(
            state,
            facts,
            scenario,
            event.day,
            permanent_plan,
            consumable,
        )
        ownership_changed = (
            ownership_changed
            or len(state.permanent_owned) != permanent_count_before_purchase
        )
        if ownership_changed:
            _equip_best_environment(state, facts, scenario)
        if capture_trace:
            release_state_rows.append(_annual_release_state_row(state, facts))
            trace_rows.append({
                "event_identity": f"day:{event.day}",
                "day": event.day,
                "study": event.study,
                "answers": event.answers,
                "completed_today": complete,
                "study_run": state.study_run,
                "garden_rhythm_percent": rhythm_percent,
                "growth_total_units": state.total_growth_units,
                "growth_applied_units": state.applied_growth_units,
                "growth_stored_balance_units": state.stored_growth_units,
                "growth_spent_units": state.growth_spent_units,
                "growth_routed_to_storage_units_lifetime": state.routed_to_storage_units_lifetime,
                "growth_contributed_to_landmarks_units": state.growth_contributed_to_landmarks_units,
                "growth_contributed_to_mastery_units": state.growth_contributed_to_mastery_units,
                "growth_contributed_to_legacy_units": state.growth_contributed_to_legacy_units,
                "growth_unallocated_overflow_units": state.unallocated_overflow_units,
                "coins_gross": state.gross_coins,
                "coins_spent": state.spent_coins,
                "coins_wallet": state.wallet,
                "finds_total": state.finds,
                "environments_owned": state.environment_owned,
                "beds_owned": state.beds_owned,
                "species_owned": state.species_owned,
                "achievements_claimed": len(state.claimed_achievements),
                "active_garden_bonus_id": state.active_garden_bonus_id,
                "active_scenery_id": state.active_scenery_id,
                "environment_effect_growth_units": state.environment_effect_growth_units,
                "environment_effect_coins": state.environment_effect_coins,
                "garden_cycle_remainder": state.garden_cycle_remainder,
                "coin_sources": dict(sorted(state.coin_sources.items())),
            })
        if event.day in config.checkpoint_days:
            checkpoints[event.day] = _checkpoint_metrics(state, facts)

    failures = []
    if state.gross_coins - state.spent_coins != state.wallet:
        failures.append("LEDGER-COIN-RECONCILIATION")
    if state.wallet < 0:
        failures.append("LEDGER-NONNEGATIVE-WALLET")
    if state.maximum_gap > facts.standard_guarantee_answer:
        failures.append("FIND-GUARANTEE-MAX")
    if state.completed_days > state.studied_days:
        failures.append("CALENDAR-COMPLETION-BOUND")
    if state.stored_growth_units < 0:
        failures.append("GROWTH-NONNEGATIVE-STORED")
    if state.total_growth_units != (
        state.applied_growth_units
        + state.stored_growth_units
        + state.growth_spent_units
    ):
        failures.append("GROWTH-RECONCILIATION")
    if (
        state.opening_plant_growth_units + state.applied_growth_units
        != sum(state.plant_growth_units)
    ):
        failures.append("GROWTH-PLANT-ALLOCATION-RECONCILIATION")
    if state.growth_spent_units != sum((
        state.growth_contributed_to_landmarks_units,
        state.growth_contributed_to_mastery_units,
        state.growth_contributed_to_legacy_units,
    )):
        failures.append("GROWTH-PROJECT-CATEGORY-RECONCILIATION")
    if state.stored_growth_units != (
        state.routed_to_storage_units_lifetime
        - state.manual_project_contributions_units
    ):
        failures.append("GROWTH-STORED-BALANCE-RECONCILIATION")
    if state.unallocated_overflow_units != 0:
        failures.append("GROWTH-UNALLOCATED-OVERFLOW")
    if state.auto_fund_endgame and state.stored_growth_units != 0:
        failures.append("ENDGAME-ACTIVE-PROJECT-NO-UNALLOCATED-STORAGE")
    if (
        not state.auto_fund_endgame
        and (
            state.manual_project_contributions_units != 0
            or state.stored_growth_units
            != state.routed_to_storage_units_lifetime
        )
    ):
        failures.append("ENDGAME-NO-PROJECT-PRESERVES-RESERVE")
    if state.environment_owned > len(facts.environment_discovery_ids):
        failures.append("ENVIRONMENT-OWNERSHIP-BOUND")
    if state.environment_owned != sum(
        item_id in state.permanent_owned
        for item_id in facts.environment_discovery_ids
    ):
        failures.append("ENVIRONMENT-OWNERSHIP-RECONCILIATION")
    if state.environment_effect_coins != (
        state.coin_sources["harvest_bell"]
        + state.coin_sources["autumn_hearth"]
        + state.coin_sources["other"]
    ):
        failures.append("ENVIRONMENT-COIN-RECONCILIATION")
    if state.environment_effect_growth_units > state.total_growth_units:
        failures.append("ENVIRONMENT-GROWTH-BOUND")
    if any(value < 0 for value in state.consumable_effect_cards.values()):
        failures.append("CONSUMABLE-EFFECT-NONNEGATIVE")
    if any(
        state.environment_extension_cards[item_id]
        > state.consumable_effect_cards[item_id]
        for item_id in state.environment_extension_cards
    ):
        failures.append("CONSUMABLE-EXTENSION-BOUND")
    for consumable in facts.consumables:
        item_id = consumable.consumable_id
        if (
            state.consumable_units_earned[item_id]
            + state.consumable_units_purchased[item_id]
            != state.consumable_units_activated[item_id]
            + state.inventory[item_id]
        ):
            failures.append("CONSUMABLE-INVENTORY-RECONCILIATION")
            break
        active_units = len(state.consumable_active_batches.get(item_id, ()))
        if (
            state.consumable_units_activated[item_id]
            != state.consumable_units_consumed[item_id] + active_units
        ):
            failures.append("CONSUMABLE-ACTIVATION-RECONCILIATION")
            break
    return ScenarioOutcome(
        scenario_id=scenario.scenario_id,
        seed_index=seed_index,
        checkpoints=checkpoints,
        assertion_failures=tuple(failures),
        trace_rows=tuple(trace_rows),
        release_state_rows=tuple(release_state_rows),
    )


def _nearest_rank(values: Sequence[float], quantile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int(math.ceil(quantile * len(ordered))))
    return ordered[min(rank - 1, len(ordered) - 1)]


def _summarize_metric(
    values: Sequence[Optional[float]],
    *,
    total_n: int,
    right_censored: bool = False,
) -> Mapping[str, object]:
    reached = [
        float(value) for value in values
        if value is not None and not math.isnan(float(value))
    ]
    n = len(reached)
    if len(values) != total_n:
        raise ValueError(
            f"metric population length {len(values)} does not match n={total_n}"
        )
    if not reached:
        result = {
            "n": total_n,
            "reached_n": 0,
            "reach_rate": 0.0,
            "mean": None,
            "sd": None,
            "se": None,
            "ci95_low": None,
            "ci95_high": None,
            "min": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "p99": None,
            "max": None,
        }
        if right_censored:
            result.update({
                "censored_n": total_n,
                "censoring_rate": 1.0,
                "population_percentile_method": (
                    "nearest_rank_with_common_right_censoring"
                ),
                "conditional_reacher_mean": None,
                "conditional_reacher_sd": None,
                "conditional_reacher_se": None,
                "conditional_reacher_ci95_low": None,
                "conditional_reacher_ci95_high": None,
                "conditional_reacher_min": None,
                "conditional_reacher_p10": None,
                "conditional_reacher_p50": None,
                "conditional_reacher_p90": None,
                "conditional_reacher_p99": None,
                "conditional_reacher_max": None,
            })
        return result
    mean = sum(reached) / n
    variance = (
        sum((value - mean) ** 2 for value in reached) / (n - 1)
        if n > 1 else 0.0
    )
    sd = math.sqrt(variance)
    se = sd / math.sqrt(n)
    conditional = {
        "n": total_n,
        "reached_n": n,
        "reach_rate": n / total_n,
        "mean": mean,
        "sd": sd,
        "se": se,
        "ci95_low": mean - 1.96 * se,
        "ci95_high": mean + 1.96 * se,
        "min": min(reached),
        "p10": _nearest_rank(reached, 0.10),
        "p50": _nearest_rank(reached, 0.50),
        "p90": _nearest_rank(reached, 0.90),
        "p99": _nearest_rank(reached, 0.99),
        "max": max(reached),
    }
    if not right_censored:
        return conditional

    ordered = sorted(reached)

    def population_percentile(quantile: float) -> Optional[float]:
        # Every unreached observation is known only to be later than the common
        # checkpoint. A percentile is identifiable exactly when its absolute
        # population rank lies among the reached observations.
        rank = max(1, int(math.ceil(quantile * total_n)))
        if rank > n:
            return None
        return ordered[rank - 1]

    censored_n = total_n - n
    result = {
        **conditional,
        "censored_n": censored_n,
        "censoring_rate": censored_n / total_n,
        "population_percentile_method": (
            "nearest_rank_with_common_right_censoring"
        ),
        "conditional_reacher_mean": conditional["mean"],
        "conditional_reacher_sd": conditional["sd"],
        "conditional_reacher_se": conditional["se"],
        "conditional_reacher_ci95_low": conditional["ci95_low"],
        "conditional_reacher_ci95_high": conditional["ci95_high"],
        "conditional_reacher_min": conditional["min"],
        "conditional_reacher_p10": conditional["p10"],
        "conditional_reacher_p50": conditional["p50"],
        "conditional_reacher_p90": conditional["p90"],
        "conditional_reacher_p99": conditional["p99"],
        "conditional_reacher_max": conditional["max"],
        "p10": population_percentile(0.10),
        "p50": population_percentile(0.50),
        "p90": population_percentile(0.90),
        "p99": population_percentile(0.99),
    }
    if censored_n:
        # Population moments and the maximum are not identified by a common
        # right-censoring boundary. They remain available above for reachers.
        result.update({
            "mean": None,
            "sd": None,
            "se": None,
            "ci95_low": None,
            "ci95_high": None,
            "max": None,
        })
    return result


def _finding_rows(
    statistics: Sequence[Mapping[str, object]],
    *,
    full_bloom_units: int,
    parity_passed: bool = False,
) -> List[Mapping[str, object]]:
    rows = []
    for statistic in statistics:
        metric = statistic["metric_id"]
        mean = statistic.get("mean")
        if mean is None or statistic.get("checkpoint_day") != 365:
            continue
        if (
            metric == "growth.stored_balance_units"
            and statistic.get("p50") is not None
            and float(statistic["p50"]) > full_bloom_units
        ):
            rows.append({
                "finding_id": f"STORED-GROWTH:{statistic['scenario_id']}",
                "severity": "high",
                "status": "triggered",
                "domain": "endgame",
                "title": (
                    "Median Stored Growth balance exceeds one Full Bloom plant"
                ),
                "metric_refs": [f"{statistic['scenario_id']}|365|{metric}"],
                "threshold": f"> {full_bloom_units:,} Growth units",
                "observed": statistic["p50"],
                "interpretation": "The modeled player has exhausted current plant capacity.",
                "caveat": "The threshold assumes 100 units per displayed Growth.",
            })
    if not parity_passed:
        rows.append({
            "finding_id": "UNKNOWN-PRODUCTION-TRACE-PARITY",
            "severity": "unknown",
            "status": "not_evaluated",
            "domain": "method",
            "title": "Production engine trace parity remains a separate gate",
            "metric_refs": [],
            "threshold": "Exact event-ledger agreement",
            "observed": "Not run by the accelerated kernel",
            "interpretation": "Compare frozen seed traces with the production engine before relying on implementation parity.",
            "caveat": "Catalog parity is verified; event-engine parity is not claimed.",
        })
    rows.append({
            "finding_id": "UNKNOWN-PLAYER-BEHAVIOR",
            "severity": "unknown",
            "status": "not_evaluated",
            "domain": "fairness",
            "title": "Retention and player choice are outside the source model",
            "metric_refs": [],
            "threshold": "Observed player telemetry",
            "observed": "Unavailable",
            "interpretation": "Modeled affordability does not establish perceived value or retention impact.",
            "caveat": "Requires player research or telemetry, not more simulation seeds.",
        })
    return rows


def _concentration_findings(
    rows: Sequence[Mapping[str, object]],
) -> List[Mapping[str, object]]:
    findings = []
    for row in rows:
        if int(row.get("checkpoint_day", 0) or 0) != 365:
            continue
        scenario_id = str(row.get("scenario_id", ""))
        checks = (
            (
                "COIN-HHI",
                "ledger_source_hhi",
                0.35,
                "Ledger-source HHI exceeds the release target",
            ),
            (
                "COIN-TOP-SOURCE",
                "top_source_share",
                0.45,
                "One exact ledger source exceeds 45 percent of gross Coins",
            ),
            (
                "COIN-COMPLETION-FAMILY",
                "completion_family_share",
                0.70,
                "Today’s Cards completion exceeds 70 percent of gross Coins",
            ),
        )
        for prefix, field, threshold, title in checks:
            observed = float(row.get(field, 0.0) or 0.0)
            if observed <= threshold:
                continue
            findings.append({
                "finding_id": f"{prefix}:{scenario_id}",
                "severity": "high" if field != "completion_family_share" else "watch",
                "status": "triggered",
                "domain": "coins",
                "title": title,
                "metric_refs": [],
                "threshold": f"<= {threshold:.2f}",
                "observed": observed,
                "interpretation": "Calculated from pooled exact ledger-source totals.",
                "caveat": (
                    "Today’s Cards and Garden Cycle remain one behavioral family."
                    if field == "completion_family_share" else ""
                ),
            })
    return findings


def _catalog_analysis(facts: CatalogFacts) -> Mapping[str, object]:
    """Return exact, JSON-safe derived values used by tables and prose."""

    stage_rows = []
    previous = 0
    cumulative_coins = 0
    for stage in facts.stages:
        reward = stage.total_coin_reward
        cumulative_coins += reward
        stage_rows.append({
            "stage_id": stage.stage_id,
            "threshold_growth": stage.threshold_growth,
            "incremental_growth": stage.threshold_growth - previous,
            "checkpoint_coin_rewards": list(stage.checkpoint_coin_rewards),
            "stage_coin_reward": reward,
            "cumulative_coin_reward": cumulative_coins,
        })
        previous = stage.threshold_growth

    permanent_costs: Counter = Counter()
    repeatable_rows = []
    first_species = facts.species_ids[0] if facts.species_ids else ""
    for option in facts.purchase_options:
        if option.repeatable:
            repeatable_rows.append({
                "item_id": option.item_id,
                "price_coins": option.price_coins,
                "growth_value": option.growth_value,
                "coin_value": option.coin_value,
            })
        if not (option.permanent and option.available and option.price_coins > 0):
            continue
        # One starter species is selected without a Coin payment.
        if option.category == "species" and option.item_id == first_species:
            continue
        permanent_costs[option.category] += option.price_coins

    consumables = {row.consumable_id: row for row in facts.consumables}
    total_find_weight = sum(row.weight for row in facts.standard_rewards)
    expected_coin_numerator = 0
    expected_growth_numerator = 0
    expected_inventory_numerator = 0
    find_rows = []
    for reward in facts.standard_rewards:
        kind = reward.reward_kind.lower()
        coin_value = reward.amount if kind == "coins" else 0
        direct_growth = reward.amount if kind in {"growth", "instant_growth"} else 0
        growth_equivalent = direct_growth
        inventory_units = reward.amount if reward.inventory_item_id else 0
        if reward.inventory_item_id in consumables:
            growth_equivalent += (
                reward.amount * consumables[reward.inventory_item_id].maximum_growth
            )
        expected_coin_numerator += reward.weight * coin_value
        expected_growth_numerator += reward.weight * growth_equivalent
        expected_inventory_numerator += reward.weight * inventory_units
        find_rows.append({
            "reward_id": reward.reward_id,
            "tier": reward.tier,
            "weight_numerator": reward.weight,
            "weight_denominator": total_find_weight,
            "reward_kind": reward.reward_kind,
            "amount": reward.amount,
            "inventory_item_id": reward.inventory_item_id,
            "coin_value": coin_value,
            "growth_equivalent": growth_equivalent,
        })

    tier_rank = {
        "common": 0,
        "uncommon": 1,
        "rare": 2,
        "very rare": 3,
        "exceptional": 4,
        "ultra rare": 5,
    }

    def pool_expected(minimum_tier: str) -> Tuple[Fraction, Fraction, Fraction]:
        minimum_rank = tier_rank.get(minimum_tier.lower(), 0)
        candidates = [
            row for row in find_rows
            if tier_rank.get(str(row["tier"]).lower(), 0) >= minimum_rank
        ]
        pool_weight = sum(int(row["weight_numerator"]) for row in candidates)
        return tuple(
            Fraction(
                sum(
                    int(row["weight_numerator"]) * int(row[value_key])
                    for row in candidates
                ),
                pool_weight,
            )
            for value_key in ("coin_value", "growth_equivalent", "inventory_units")
        )

    # Keep an explicit inventory field on each reward projection for the exact
    # schedule-adjusted expectation calculation.
    for row, reward in zip(find_rows, facts.standard_rewards):
        row["inventory_units"] = reward.amount if reward.inventory_item_id else 0

    survival = Fraction(1, 1)
    expected_gap = Fraction(0, 1)
    schedule_expected = [Fraction(0, 1), Fraction(0, 1), Fraction(0, 1)]
    guarantee_probability = Fraction(0, 1)
    bands_by_answer = {
        answer: band
        for band in facts.standard_find_schedule
        for answer in range(band.first_answer, band.last_answer + 1)
    }
    for answer in range(1, facts.standard_guarantee_answer + 1):
        band = bands_by_answer[answer]
        hit_probability = survival * Fraction(band.numerator, band.denominator)
        survival -= hit_probability
        expected_gap += answer * hit_probability
        values = pool_expected(band.minimum_tier)
        for index, value in enumerate(values):
            schedule_expected[index] += hit_probability * value
        if answer == facts.standard_guarantee_answer:
            guarantee_probability = hit_probability

    def fixed_six(value: Fraction) -> Mapping[str, int]:
        scale = 1_000_000
        return {
            "scaled_integer": (
                value.numerator * scale + value.denominator // 2
            ) // value.denominator,
            "scale": scale,
        }

    def grant_growth(grant) -> int:
        if grant.kind in {"growth", "instant_growth", "banked_growth"}:
            return grant.amount
        if grant.kind == "consumable" and grant.item_id in consumables:
            return grant.amount * consumables[grant.item_id].maximum_growth
        return 0

    effect_rows = []
    options_by_id = {row.item_id: row for row in facts.purchase_options}
    for item_id, effects in sorted(facts.effects_by_item_id.items()):
        if not effects:
            continue
        option = options_by_id.get(item_id)
        price_coins = option.price_coins if option else 0
        exact_growth = Fraction(0, 1)
        exact_coins = Fraction(0, 1)
        for effect in effects:
            trigger_count = Fraction(1, 1)
            if effect.trigger == "eligible_card":
                eligible = min(100, effect.first_n_per_day or 100)
                trigger_count = Fraction(eligible // max(1, effect.every_n), 1)
            elif effect.trigger == "valid_completion":
                trigger_count = Fraction(1, max(1, effect.every_n))
            if effect.grant is not None:
                exact_growth += trigger_count * grant_growth(effect.grant)
                if effect.grant.kind == "coins":
                    exact_coins += trigger_count * effect.grant.amount
            for grant, weight in effect.weighted_grants:
                exact_growth += trigger_count * Fraction(weight, 100) * grant_growth(grant)
                if grant.kind == "coins":
                    exact_coins += trigger_count * Fraction(weight, 100) * grant.amount
        effect_rows.append({
            "item_id": item_id,
            "price_coins": price_coins,
            "growth_equivalent_numerator": exact_growth.numerator,
            "growth_equivalent_denominator": exact_growth.denominator,
            "coin_value_numerator": exact_coins.numerator,
            "coin_value_denominator": exact_coins.denominator,
            "coin_payback_completion_numerator": (
                price_coins * exact_coins.denominator if exact_coins else None
            ),
            "coin_payback_completion_denominator": (
                exact_coins.numerator if exact_coins else None
            ),
            "effect_ids": [effect.effect_id for effect in effects],
            "reference": "100 eligible cards plus one valid completion",
            "caveat": "Activation-only and milestone-percent interactions are listed but not independently monetized.",
        })

    speed_rows = []
    for consumable in facts.consumables:
        if not consumable.purchasable or not consumable.price_coins:
            continue
        speed_rows.append({
            "item_id": consumable.consumable_id,
            "maximum_growth": consumable.maximum_growth,
            "price_coins": consumable.price_coins,
            "growth_per_coin_numerator": consumable.maximum_growth,
            "growth_per_coin_denominator": consumable.price_coins,
            "cards_per_hour": [30, 100, 300],
            "growth_per_coin_is_speed_invariant": True,
        })

    return {
        "growth": {
            "units_per_displayed_growth": GROWTH_UNITS_PER_POINT,
            "base_growth_per_review": facts.base_growth_per_review,
            "shared_growth_numerator": facts.shared_growth_numerator,
            "shared_growth_denominator": facts.shared_growth_denominator,
            "full_bloom_growth": facts.full_bloom_growth,
            "stage_rows": stage_rows,
            "full_lifecycle_coin_reward": cumulative_coins,
            "full_bloom_stage_coin_reward": facts.stages[-1].total_coin_reward,
        },
        "coins": {
            "daily_activity": facts.daily_activity_coins,
            "valid_completion": facts.completion_coins,
            "weekly_streak": facts.weekly_streak_coins,
            "garden_cycle_every_completions": facts.garden_cycle_completions,
            "garden_cycle_coins": facts.garden_cycle_coins,
            "permanent_cost_by_category": dict(sorted(permanent_costs.items())),
            "permanent_cost_total": sum(permanent_costs.values()),
            "functional_catalog_cost_total": sum(
                value for category, value in permanent_costs.items()
                if category in {"species", "garden_bonus", "scenery"}
            ),
            "pre_endgame_permanent_cost_total": sum(
                value for category, value in permanent_costs.items()
                if category not in {"landmark", "mastery"}
            ),
            "cost_definitions": {
                "functional": "paid species plus Garden Bonuses plus paid Scenery",
                "pre_endgame": "functional catalog plus optional paid cosmetics",
                "all_permanent": "pre-endgame plus Landmark and per-species Mastery claims",
            },
        },
        "repeatable_items": sorted(repeatable_rows, key=lambda row: row["item_id"]),
        "consumable_reporting": {
            "item_ids": [row.consumable_id for row in facts.consumables],
            "canonical_fields": list(CONSUMABLE_REPORT_FIELDS),
            "metric_id_template": "consumables.{item_id}.{field}",
            "compatibility_aliases": {
                "effect_cards_remaining": "cards_of_effect_remaining",
                "growth_generated_units": "growth_generated",
            },
        },
        "standard_finds": {
            "guarantee_answer": facts.standard_guarantee_answer,
            "daily_caps_at_10_200_400_answers": [
                facts.standard_daily_cap(value) for value in (10, 200, 400)
            ],
            "total_weight": total_find_weight,
            "expected_coins": {
                "numerator": expected_coin_numerator,
                "denominator": total_find_weight,
            },
            "expected_growth_equivalent": {
                "numerator": expected_growth_numerator,
                "denominator": total_find_weight,
            },
            "expected_inventory_units": {
                "numerator": expected_inventory_numerator,
                "denominator": total_find_weight,
            },
            "schedule_adjusted_expected_gap_cards_fixed_6": fixed_six(expected_gap),
            "guarantee_hit_probability_fixed_6": fixed_six(guarantee_probability),
            "schedule_adjusted_expected_coins_fixed_6": fixed_six(schedule_expected[0]),
            "schedule_adjusted_expected_growth_equivalent_fixed_6": fixed_six(schedule_expected[1]),
            "schedule_adjusted_expected_inventory_units_fixed_6": fixed_six(schedule_expected[2]),
            "fixed_point_note": "scaled_integer / scale; rounded half-up with integer arithmetic",
            "daily_cap_caveat": "Per-opportunity values exclude reviews suppressed by the daily Find cap.",
            "rewards": find_rows,
        },
        "environment_tiers": [
            {
                "tier_id": tier.tier_id,
                "base_denominator": tier.base_denominator,
                "card_guarantee": tier.card_guarantee,
                "completion_guarantee": tier.completion_guarantee,
                "item_count": sum(
                    item.tier_id == tier.tier_id
                    for item in facts.environment_discoveries
                ),
            }
            for tier in facts.environment_tiers
        ],
        "environment_acquisition_reporting": {
            "timing_percentiles": ["p10", "p50", "p90"],
            "timing_population": "all paired users in the scenario",
            "timing_censoring": "right_censored_at_checkpoint",
            "timing_population_percentile_method": (
                "nearest rank over the full population; null when the rank "
                "falls among users censored after the checkpoint"
            ),
            "conditional_reacher_statistic_prefix": "conditional_reacher_",
            "calendar_day_fields": [
                "first_discovery_day",
                "both_items_completion_day",
            ],
            "eligible_card_fields": [
                "first_discovery_eligible_card",
                "both_items_completion_eligible_card",
            ],
            "route_fields": [
                "natural_acquisitions",
                "card_pity_acquisitions",
                "completion_pity_acquisitions",
            ],
            "simultaneous_forced_user_rate_field": (
                "simultaneous_forced_user_rate"
            ),
            "any_tier_simultaneous_forced_user_field": (
                "environments.any_tier_simultaneous_forced_user"
            ),
            "ownership_suppression_rate_field": "ownership_suppression_rate",
            "ownership_suppression_denominator": (
                "eligible-card checks plus valid-completion checks"
            ),
        },
        "environment_effects": effect_rows,
        "optional_speed_sensitivity": {
            "separate_from_primary_cohorts": True,
            "rows": speed_rows,
        },
    }


def _collect_cohort(
    facts: CatalogFacts,
    config: SimulationConfig,
    cohort_scenarios: Sequence[ScenarioSpec],
    seed_indices: Iterable[int],
) -> Tuple[
    Mapping[Tuple[str, int, str], Sequence[float]],
    Counter,
    Counter,
]:
    """Collect one cohort's paired outcomes for an arbitrary seed slice.

    Event streams are shared by strategies with an identical calendar. This is
    both the common-random-numbers design used by the analysis and the main
    performance shortcut: purchase policy never changes the Find or discovery
    draws assigned to that calendar.
    """

    collectors: MutableMapping[
        Tuple[str, int, str], array
    ] = defaultdict(lambda: array("d"))
    assertion_counts: Counter = Counter()
    exact_integer_totals: Counter = Counter()
    for seed_index in seed_indices:
        stream_cache: Dict[
            Tuple[Optional[int], int, int, int], Tuple[DayEvents, ...]
        ] = {}
        for scenario in cohort_scenarios:
            calendar_key = (
                scenario.missed_week_start_day,
                scenario.cohort.cards_per_study_day,
                scenario.cohort.study_days_per_week,
                scenario.completion_percent,
            )
            events = stream_cache.get(calendar_key)
            if events is None:
                events = generate_event_stream(facts, scenario, config, seed_index)
                stream_cache[calendar_key] = events
            outcome = simulate_scenario(
                facts,
                scenario,
                config,
                seed_index,
                events=events,
            )
            assertion_counts.update(outcome.assertion_failures)
            for checkpoint_day, checkpoint in outcome.checkpoints.items():
                for metric_id, value in checkpoint.items():
                    if (
                        value is not None
                        and (
                            metric_id == "coins.gross"
                            or metric_id.startswith("coins.source.")
                        )
                    ):
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise AssertionError(
                                "Coin totals must reach aggregation as exact "
                                f"integers: {metric_id}={value!r}"
                            )
                        exact_integer_totals[
                            (scenario.scenario_id, checkpoint_day, metric_id)
                        ] += value
                    collectors[(scenario.scenario_id, checkpoint_day, metric_id)].append(
                        float("nan") if value is None else float(value)
                    )
    return dict(collectors), assertion_counts, exact_integer_totals


def _collect_cohort_worker(
    args: Tuple[SimulationConfig, str, int, int],
) -> Tuple[
    Mapping[Tuple[str, int, str], Sequence[float]],
    Counter,
    Counter,
]:
    """Process-pool entrypoint using only picklable canonical inputs."""

    config, cohort_id, start, stop = args
    facts = load_catalog_facts()
    cohort_scenarios = tuple(
        scenario for scenario in approved_scenarios()
        if scenario.cohort.cohort_id == cohort_id
    )
    return _collect_cohort(facts, config, cohort_scenarios, range(start, stop))


CollectedCohort = Tuple[
    Mapping[Tuple[str, int, str], Sequence[float]],
    Counter,
    Counter,
]


def collect_balance_seed_range(
    config: SimulationConfig,
    *,
    seed_start: int,
    seed_stop: int,
    facts: Optional[CatalogFacts] = None,
    workers: int = 1,
) -> Mapping[str, CollectedCohort]:
    """Collect the canonical matrix for one half-open paired-seed range.

    The returned values are deliberately unsummarized. A distributed runner
    can persist the exact per-seed observations, concatenate contiguous ranges
    in seed order, and then use :func:`simulate_balance` for the same summary
    and report path as a monolithic run.
    """

    start = int(seed_start)
    stop = int(seed_stop)
    if start < 0 or stop <= start or stop > config.seeds:
        raise ValueError(
            "seed range must be nonempty and contained in "
            f"[0, {config.seeds}): [{start}, {stop})"
        )
    worker_count = max(1, int(workers))
    if worker_count > 1 and facts is not None:
        raise ValueError(
            "parallel shard collection requires the canonical catalog"
        )

    if worker_count > 1:
        batches = [
            (config, cohort.cohort_id, start, stop)
            for cohort in APPROVED_COHORTS
        ]
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            rows = tuple(executor.map(_collect_cohort_worker, batches))
        return {
            cohort.cohort_id: row
            for cohort, row in zip(APPROVED_COHORTS, rows)
        }

    catalog = facts or load_catalog_facts()
    scenarios = approved_scenarios()
    return {
        cohort.cohort_id: _collect_cohort(
            catalog,
            config,
            tuple(
                scenario for scenario in scenarios
                if scenario.cohort.cohort_id == cohort.cohort_id
            ),
            range(start, stop),
        )
        for cohort in APPROVED_COHORTS
    }


def _coin_concentration_rows(
    statistics: Sequence[Mapping[str, object]],
) -> List[Mapping[str, object]]:
    grouped: MutableMapping[Tuple[str, int], Dict[str, int]] = defaultdict(dict)
    gross_totals: Dict[Tuple[str, int], int] = {}
    metadata: Dict[Tuple[str, int], Tuple[str, str]] = {}
    for row in statistics:
        metric_id = str(row.get("metric_id", ""))
        if metric_id != "coins.gross" and not metric_id.startswith("coins.source."):
            continue
        key = (str(row["scenario_id"]), int(row["checkpoint_day"]))
        if metric_id == "coins.gross":
            if "pooled_total" not in row:
                raise ValueError("Pooled gross Coins have no exact total")
            gross_totals[key] = max(0, int(row.get("pooled_total", 0) or 0))
            metadata[key] = (str(row["strategy_id"]), str(row["case_id"]))
            continue
        source_id = metric_id.removeprefix("coins.source.")
        if "pooled_total" not in row:
            raise ValueError(
                f"Coin concentration source {metric_id} has no exact pooled total"
            )
        grouped[key][source_id] = max(
            0, int(row.get("pooled_total", 0) or 0)
        )
        metadata[key] = (str(row["strategy_id"]), str(row["case_id"]))
    rows = []
    for (scenario_id, checkpoint_day), source_totals in sorted(grouped.items()):
        gross = sum(source_totals.values())
        authoritative_gross = gross_totals.get((scenario_id, checkpoint_day))
        if authoritative_gross is None:
            raise ValueError(
                f"Coin concentration has no pooled gross total for {scenario_id} "
                f"at day {checkpoint_day}"
            )
        if authoritative_gross != gross:
            raise ValueError(
                f"Coin source totals do not reconcile for {scenario_id} at day "
                f"{checkpoint_day}: {gross} != {authoritative_gross}"
            )
        hhi_numerator = sum(amount * amount for amount in source_totals.values())
        hhi_denominator = gross * gross
        source_shares = {
            source_id: (
                float(Fraction(amount, gross)) if gross else 0.0
            )
            for source_id, amount in sorted(source_totals.items())
        }
        family_totals: Counter = Counter()
        for source_id, amount in source_totals.items():
            family_totals[
                COIN_SOURCE_BEHAVIORAL_FAMILY.get(source_id, "other")
            ] += amount
        family_shares = {
            family_id: (
                float(Fraction(amount, gross)) if gross else 0.0
            )
            for family_id, amount in sorted(family_totals.items())
        }
        family_hhi_numerator = sum(
            amount * amount for amount in family_totals.values()
        )
        strategy_id, case_id = metadata[(scenario_id, checkpoint_day)]
        completion_total = family_totals["todays_cards_completion"]
        rows.append({
            "scenario_id": scenario_id,
            "strategy_id": strategy_id,
            "case_id": case_id,
            "checkpoint_day": checkpoint_day,
            "gross_coins_pooled": gross,
            "source_totals": dict(sorted(source_totals.items())),
            "source_shares": source_shares,
            "ledger_source_hhi_numerator": hhi_numerator,
            "ledger_source_hhi_denominator": hhi_denominator,
            "ledger_source_hhi": (
                float(Fraction(hhi_numerator, hhi_denominator))
                if hhi_denominator else 0.0
            ),
            "top_source_id": max(source_shares, key=source_shares.get, default=""),
            "top_source_share": max(source_shares.values(), default=0.0),
            "top_source_share_numerator": max(source_totals.values(), default=0),
            "top_source_share_denominator": gross,
            "behavioral_family_totals": dict(sorted(family_totals.items())),
            "behavioral_family_shares": family_shares,
            "behavioral_family_hhi_numerator": family_hhi_numerator,
            "behavioral_family_hhi_denominator": hhi_denominator,
            "behavioral_family_hhi": (
                float(Fraction(family_hhi_numerator, hhi_denominator))
                if hhi_denominator else 0.0
            ),
            "completion_family_share": family_shares.get(
                "todays_cards_completion", 0.0
            ),
            "completion_family_share_numerator": completion_total,
            "completion_family_share_denominator": gross,
            "gross_without_completion_rewards": gross - completion_total,
            "gross_without_completion_share": (
                float(Fraction(gross - completion_total, gross))
                if gross else 0.0
            ),
        })
    return rows


def simulate_balance(
    config: SimulationConfig,
    *,
    facts: Optional[CatalogFacts] = None,
    scenarios: Optional[Sequence[ScenarioSpec]] = None,
    workers: int = 1,
    precollected_by_cohort: Optional[Mapping[str, CollectedCohort]] = None,
    parity_evidence: Optional[Mapping[str, object]] = None,
    release_validation_evidence: Optional[Mapping[str, object]] = None,
) -> Mapping[str, object]:
    catalog = facts or load_catalog_facts()
    scenario_rows = tuple(scenarios or approved_scenarios())
    release_matrix_requested = (
        scenarios is None
        or len(scenario_rows) == len(APPROVED_SCENARIO_IDS)
        or (
            config.seeds == DEFAULT_SEED_COUNT
            and config.days == DEFAULT_DAYS
        )
    )
    if release_matrix_requested and scenario_rows != approved_scenarios():
        raise ValueError(
            "release-sized balance runs require the exact ordered canonical "
            "66 scenarios, cohorts, and consumable policies"
        )
    statistics = []
    assertion_counts: Counter = Counter()

    scenarios_by_cohort: MutableMapping[str, List[ScenarioSpec]] = defaultdict(list)
    for scenario in scenario_rows:
        scenarios_by_cohort[scenario.cohort.cohort_id].append(scenario)

    for cohort in APPROVED_COHORTS:
        cohort_scenarios = scenarios_by_cohort.get(cohort.cohort_id, [])
        if not cohort_scenarios:
            continue
        collectors: MutableMapping[Tuple[str, int, str], array] = defaultdict(
            lambda: array("d")
        )
        exact_integer_totals: Counter = Counter()
        worker_count = max(1, int(workers))
        if precollected_by_cohort is not None:
            precollected = precollected_by_cohort.get(cohort.cohort_id)
            if precollected is None:
                raise ValueError(
                    "precollected balance data is missing cohort "
                    f"{cohort.cohort_id}"
                )
            (
                batch_collectors,
                batch_assertions,
                batch_exact_integer_totals,
            ) = precollected
            # The shard provider already concatenated this cohort in canonical
            # seed order. Reuse its arrays rather than briefly doubling the
            # merge job's largest in-memory object.
            collectors = batch_collectors
            assertion_counts.update(batch_assertions)
            exact_integer_totals.update(batch_exact_integer_totals)
        elif worker_count > 1:
            if facts is not None or scenarios is not None:
                raise ValueError("parallel simulation requires the canonical catalog and scenarios")
            chunk_size = max(1, math.ceil(config.seeds / worker_count))
            batches = [
                (config, cohort.cohort_id, start, min(config.seeds, start + chunk_size))
                for start in range(0, config.seeds, chunk_size)
            ]
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                for (
                    batch_collectors,
                    batch_assertions,
                    batch_exact_integer_totals,
                ) in executor.map(
                    _collect_cohort_worker, batches
                ):
                    for key, values in batch_collectors.items():
                        collectors[key].extend(values)
                    assertion_counts.update(batch_assertions)
                    exact_integer_totals.update(batch_exact_integer_totals)
        else:
            (
                batch_collectors,
                batch_assertions,
                batch_exact_integer_totals,
            ) = _collect_cohort(
                catalog,
                config,
                tuple(cohort_scenarios),
                range(config.seeds),
            )
            for key, values in batch_collectors.items():
                collectors[key].extend(values)
            assertion_counts.update(batch_assertions)
            exact_integer_totals.update(batch_exact_integer_totals)

        for (scenario_id, checkpoint_day, metric_id), values in sorted(collectors.items()):
            right_censored = _is_right_censored_timing_metric(metric_id)
            summary = _summarize_metric(
                values,
                total_n=config.seeds,
                right_censored=right_censored,
            )
            statistic = {
                "scenario_id": scenario_id,
                "strategy_id": next(
                    row.strategy.strategy_id for row in cohort_scenarios
                    if row.scenario_id == scenario_id
                ),
                "case_id": next(
                    row.case_id for row in cohort_scenarios
                    if row.scenario_id == scenario_id
                ),
                "checkpoint_day": checkpoint_day,
                "metric_id": metric_id,
                "unit": _metric_unit(metric_id),
                "estimator": "paired_monte_carlo",
                "population_scope": (
                    f"{scenario_id}|day_{checkpoint_day}|all_paired_seeds"
                ),
                "censoring": (
                    "right_censored_at_checkpoint"
                    if right_censored
                    else "none"
                ),
                **summary,
            }
            if right_censored:
                statistic["conditional_reacher_population_scope"] = (
                    f"{scenario_id}|day_{checkpoint_day}|reached_by_checkpoint"
                )
            if metric_id == "coins.gross" or metric_id.startswith("coins.source."):
                statistic["pooled_total"] = exact_integer_totals[
                    (scenario_id, checkpoint_day, metric_id)
                ]
            statistics.append(statistic)
        if precollected_by_cohort is not None:
            # Release the completed cohort before the lazy provider inflates
            # the next one from its compressed shard payloads.
            collectors = {}
            batch_collectors = {}
            precollected = None

    assertions = [
        {
            "assertion_id": assertion_id,
            "class": "correctness",
            "status": "pass" if failures == 0 else "fail",
            "observed": failures,
            "expected": 0,
            "evidence_refs": ["simulation_outcomes"],
        }
        for assertion_id, failures in sorted({
            "LEDGER-COIN-RECONCILIATION": assertion_counts["LEDGER-COIN-RECONCILIATION"],
            "LEDGER-NONNEGATIVE-WALLET": assertion_counts["LEDGER-NONNEGATIVE-WALLET"],
            "FIND-GUARANTEE-MAX": assertion_counts["FIND-GUARANTEE-MAX"],
            "CALENDAR-COMPLETION-BOUND": assertion_counts["CALENDAR-COMPLETION-BOUND"],
            "GROWTH-NONNEGATIVE-STORED": assertion_counts["GROWTH-NONNEGATIVE-STORED"],
            "GROWTH-RECONCILIATION": assertion_counts["GROWTH-RECONCILIATION"],
            "GROWTH-PLANT-ALLOCATION-RECONCILIATION": assertion_counts["GROWTH-PLANT-ALLOCATION-RECONCILIATION"],
            "GROWTH-PROJECT-CATEGORY-RECONCILIATION": assertion_counts["GROWTH-PROJECT-CATEGORY-RECONCILIATION"],
            "GROWTH-STORED-BALANCE-RECONCILIATION": assertion_counts["GROWTH-STORED-BALANCE-RECONCILIATION"],
            "GROWTH-UNALLOCATED-OVERFLOW": assertion_counts["GROWTH-UNALLOCATED-OVERFLOW"],
            "ENDGAME-ACTIVE-PROJECT-NO-UNALLOCATED-STORAGE": assertion_counts["ENDGAME-ACTIVE-PROJECT-NO-UNALLOCATED-STORAGE"],
            "ENDGAME-NO-PROJECT-PRESERVES-RESERVE": assertion_counts["ENDGAME-NO-PROJECT-PRESERVES-RESERVE"],
            "ENVIRONMENT-OWNERSHIP-BOUND": assertion_counts["ENVIRONMENT-OWNERSHIP-BOUND"],
            "ENVIRONMENT-OWNERSHIP-RECONCILIATION": assertion_counts["ENVIRONMENT-OWNERSHIP-RECONCILIATION"],
            "ENVIRONMENT-COIN-RECONCILIATION": assertion_counts["ENVIRONMENT-COIN-RECONCILIATION"],
            "ENVIRONMENT-GROWTH-BOUND": assertion_counts["ENVIRONMENT-GROWTH-BOUND"],
            "CONSUMABLE-EFFECT-NONNEGATIVE": assertion_counts["CONSUMABLE-EFFECT-NONNEGATIVE"],
            "CONSUMABLE-EXTENSION-BOUND": assertion_counts["CONSUMABLE-EXTENSION-BOUND"],
            "CONSUMABLE-INVENTORY-RECONCILIATION": assertion_counts["CONSUMABLE-INVENTORY-RECONCILIATION"],
            "CONSUMABLE-ACTIVATION-RECONCILIATION": assertion_counts["CONSUMABLE-ACTIVATION-RECONCILIATION"],
        }.items())
    ]
    failed = [row for row in assertions if row["status"] != "pass"]
    if failed:
        raise AssertionError(f"balance correctness assertions failed: {failed}")

    scenario_projection = [
        {
            "scenario_id": row.scenario_id,
            "cohort_id": row.cohort.cohort_id,
            "cards_per_study_day": row.cohort.cards_per_study_day,
            "study_days_per_week": row.cohort.study_days_per_week,
            "cohort_completion_percent": row.cohort.completion_percent,
            "completion_percent": row.completion_percent,
            "strategy_id": row.strategy.strategy_id,
            "consumable_policy": row.strategy.consumable_policy,
            "case_id": row.case_id,
            "case_label": row.case_label,
        }
        for row in scenario_rows
    ]
    configuration_checks = (
        (
            "CONFIG-COHORT-PAIRS",
            not release_matrix_requested or tuple(sorted({
                (
                    row["cohort_id"],
                    row["cards_per_study_day"],
                    row["study_days_per_week"],
                    row["cohort_completion_percent"],
                )
                for row in scenario_projection
            })) == tuple(sorted({
                (
                    row.cohort_id,
                    row.cards_per_study_day,
                    row.study_days_per_week,
                    row.completion_percent,
                )
                for row in APPROVED_COHORTS
            })),
            len(APPROVED_COHORTS),
        ),
        (
            "CONFIG-SCENARIO-COUNT",
            (
                len(scenario_projection) == len(scenario_rows)
                and len({row["scenario_id"] for row in scenario_projection})
                == len(scenario_projection)
                and (
                    not release_matrix_requested
                    or len(scenario_projection) == 66
                )
            ),
            66 if release_matrix_requested else len(scenario_rows),
        ),
        (
            "CONFIG-SCENARIO-IDENTITIES",
            not release_matrix_requested or tuple(
                row["scenario_id"] for row in scenario_projection
            ) == APPROVED_SCENARIO_IDS,
            "frozen ordered 66-scenario identity set",
        ),
        (
            "CONFIG-CONSUMABLE-POLICY-MAPPING",
            not release_matrix_requested or tuple(sorted({
                (str(row["strategy_id"]), str(row["consumable_policy"]))
                for row in scenario_projection
            })) == tuple(sorted(APPROVED_CONSUMABLE_POLICY_BY_STRATEGY)),
            dict(APPROVED_CONSUMABLE_POLICY_BY_STRATEGY),
        ),
        (
            "CATALOG-FIND-CAPS",
            [catalog.standard_daily_cap(value) for value in (10, 200, 400)]
            == [3, 4, 5],
            [3, 4, 5],
        ),
        (
            "CATALOG-FULL-BLOOM-POSITIVE",
            catalog.full_bloom_growth > 0,
            "> 0",
        ),
        (
            "CATALOG-RELEASE-VERSION",
            catalog.snapshot.get("catalog_version") == "2.2.0",
            "2.2.0",
        ),
    )
    assertions.extend({
        "assertion_id": assertion_id,
        "class": "configuration",
        "status": "pass" if passed else "fail",
        "observed": expected if passed else "mismatch",
        "expected": expected,
        "evidence_refs": ["catalog_snapshot", "scenario_matrix"],
    } for assertion_id, passed, expected in configuration_checks)
    failed = [row for row in assertions if row["status"] != "pass"]
    if failed:
        raise AssertionError(f"balance acceptance assertions failed: {failed}")
    coin_concentration = _coin_concentration_rows(statistics)
    validated_parity = _validated_parity_evidence(parity_evidence)
    validated_release = _validated_release_validation_evidence(
        release_validation_evidence
    )
    parity_passed = bool(
        validated_parity.get("status") == "pass"
        and validated_parity.get("production_engine_trace_equivalent") is True
    )
    release_gate_status = {
        "automated": {
            "status": "pass",
            "detail": "All accelerated-model correctness assertions passed.",
        },
        "modeled_acceptance": {
            "status": "not_evaluated",
            "detail": (
                "Requires the complete 10,000-seed, 365-day release matrix."
            ),
        },
        "production_parity": {
            "status": str(validated_parity.get("status", "not_run")),
            "production_engine_trace_equivalent": parity_passed,
        },
        **validated_release,
        # This report is machine-generated.  It must never silently promote
        # unrun native, human, or platform gates to release approval.
        "release_ready": False,
        "blocking_gates": [
            gate for gate, passed in (
                ("production_parity", parity_passed),
                ("modeled_acceptance", False),
                ("migration_tests", False),
                ("native_macos_smoke", False),
                ("human_review", False),
                ("platform_macos_100_percent_text", False),
            )
            if not passed
        ],
    }
    report = {
        "$schema": "https://anki-garden.local/schemas/economy-analysis-v2.json",
        "run": {
            "release_target": "2.2.0",
            "report_schema_version": 2,
            "model": "catalog-ledger-v2",
            "days": config.days,
            "seed_count": config.seeds,
            "seed_root_sha256": config.seed_root_sha256,
            "rng": "sha256-seeded-splitmix64-v1",
            "quantiles": "nearest-rank",
            "catalog_sha256": catalog.snapshot_sha256,
            "source_date_epoch": config.source_date_epoch,
            "seed_manifest": {
                "seed_root_sha256": config.seed_root_sha256,
                "first_seed_index": 0,
                "last_seed_index": config.seeds - 1,
                "seed_count": config.seeds,
            },
        },
        "catalog": {
            "sha256": catalog.snapshot_sha256,
            "snapshot": catalog.snapshot,
            "records": list(catalog.catalog_records),
        },
        "analysis": _catalog_analysis(catalog),
        "scenario_matrix": {
            "canonical_scenario_count": 66,
            "canonical_scenario_ids": list(APPROVED_SCENARIO_IDS),
            "consumable_policy_by_strategy": dict(
                APPROVED_CONSUMABLE_POLICY_BY_STRATEGY
            ),
            "cohorts": [
                {
                    "cohort_id": row.cohort_id,
                    "cards_per_study_day": row.cards_per_study_day,
                    "study_days_per_week": row.study_days_per_week,
                    "completion_percent": row.completion_percent,
                }
                for row in APPROVED_COHORTS
            ],
            "scenarios": scenario_projection,
        },
        "statistics": statistics,
        "growth_accounting_statistics": [
            row for row in statistics
            if str(row["metric_id"]).startswith("growth.")
            and row["metric_id"] in {
                "growth.generated_units",
                "growth.applied_to_plants_units",
                "growth.routed_to_storage_units_lifetime",
                "growth.stored_balance_units",
                "growth.contributed_to_landmarks_units",
                "growth.contributed_to_mastery_units",
                "growth.contributed_to_legacy_units",
                "growth.unallocated_overflow_units",
            }
        ],
        "consumable_statistics": [
            row for row in statistics
            if str(row["metric_id"]).startswith("consumables.")
            and row["metric_id"] != "consumables.growth_units"
        ],
        "environment_acquisition_statistics": [
            row for row in statistics
            if str(row["metric_id"]).startswith("environments.")
            and row["metric_id"] not in {
                "environments.discovered",
                "environments.effect_growth_units",
                "environments.effect_coins",
                "environments.effect_consumables",
            }
        ],
        "coin_concentration": coin_concentration,
        "milestones": [
            row for row in statistics
            if row["metric_id"] in {
                "catalog.completion_day",
                "plants.first_full_bloom_day",
                "plants.all_catalog_full_bloom_day",
            }
        ],
        "assertions": assertions,
        "parity": validated_parity,
        "release_status": release_gate_status,
        "findings": [
            *_finding_rows(
                statistics,
                full_bloom_units=(
                    catalog.full_bloom_growth * GROWTH_UNITS_PER_POINT
                ),
                parity_passed=parity_passed,
            ),
            *_concentration_findings(coin_concentration),
        ],
    }
    # The report builder owns the release target predicates. Reusing that
    # single scorecard here avoids a second, drifting acceptance definition.
    if config.seeds == 10_000 and config.days == 365:
        from .report import balance_scorecard_rows

        modeled_rows = tuple(
            row for row in balance_scorecard_rows(report)
            if row.get("criterion_id") != "INTEGRITY-PRODUCTION-PARITY"
        )
        statuses = {
            str(row.get("status", "not modeled")) for row in modeled_rows
        }
        # The report scorecard now evaluates every modeled release criterion,
        # including finite Coin/Growth demand and active/no-project invariants.
        uncovered_criteria: list[str] = []
        modeled_status = (
            "attention"
            if "attention" in statuses
            else "not_evaluated"
            if "not modeled" in statuses or uncovered_criteria
            else "pass"
        )
        report["release_status"]["modeled_acceptance"] = {
            "status": modeled_status,
            "criteria_total": len(modeled_rows),
            "attention_criteria": [
                str(row.get("criterion_id", ""))
                for row in modeled_rows
                if row.get("status") == "attention"
            ],
            "not_evaluated_criteria": [
                str(row.get("criterion_id", ""))
                for row in modeled_rows
                if row.get("status") == "not modeled"
            ],
            "uncovered_criteria": uncovered_criteria,
        }
    release_status = report["release_status"]
    required_release_gates = (
        "automated",
        "modeled_acceptance",
        "production_parity",
        "migration_tests",
        "native_macos_smoke",
        "human_review",
        "platform_macos_100_percent_text",
    )
    blocking_gates = [
        gate for gate in required_release_gates
        if str(release_status.get(gate, {}).get("status", "not_run"))
        != "pass"
    ]
    release_status["blocking_gates"] = blocking_gates
    release_status["release_ready"] = not blocking_gates
    return report


def _validated_release_validation_evidence(
    evidence: Optional[Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    """Normalize externally-run release gates without promoting absent work."""

    defaults: Mapping[str, str] = {
        "migration_tests": "not_run",
        "native_macos_smoke": "not_run",
        "platform_macos_100_percent_text": "not_run",
        "human_review": "pending",
    }
    allowed = {"pass", "fail", "not_run", "pending"}
    supplied = dict(evidence or {})
    unknown = sorted(set(supplied) - set(defaults))
    if unknown:
        raise ValueError(
            f"unknown release validation evidence gates: {unknown}"
        )
    normalized: dict[str, Mapping[str, object]] = {}
    for gate, default_status in defaults.items():
        raw = supplied.get(gate, {"status": default_status})
        if isinstance(raw, str):
            row: dict[str, object] = {"status": raw}
        elif isinstance(raw, Mapping):
            row = dict(raw)
        else:
            raise ValueError(
                f"release validation gate {gate} must be a status or object"
            )
        status = str(row.get("status", default_status) or default_status)
        if status not in allowed:
            raise ValueError(
                f"release validation gate {gate} has invalid status {status!r}"
            )
        if status == "pass":
            refs = row.get("evidence_refs", ())
            refs = (
                tuple(str(value) for value in refs)
                if isinstance(refs, Sequence)
                and not isinstance(refs, (str, bytes))
                else ()
            )
            digest = str(row.get("evidence_sha256", "") or "")
            if not refs or any(not value.strip() for value in refs):
                raise ValueError(
                    f"release validation gate {gate} pass requires evidence_refs"
                )
            if (
                len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError(
                    f"release validation gate {gate} pass requires a lowercase "
                    "evidence_sha256"
                )
            row["evidence_refs"] = list(refs)
        row["status"] = status
        normalized[gate] = row
    return normalized


def _validated_parity_evidence(
    evidence: Optional[Mapping[str, object]],
) -> Mapping[str, object]:
    """Fail closed unless the complete production parity manifest passed."""

    if evidence is None:
        return {
            "status": "not_run",
            "production_engine_trace_equivalent": False,
            "note": (
                "Random streams are paired across strategies. Release remains "
                "blocked until the production replay harness passes."
            ),
        }
    row = dict(evidence)
    if row.get("status") != "pass":
        row["production_engine_trace_equivalent"] = False
        return row
    from .trace import (
        REQUIRED_PARITY_BEHAVIORS,
        REQUIRED_PARITY_STATE_FIELDS,
        TRACE_FIELDS,
    )

    required = {
        "production_engine_trace_equivalent": True,
        "scenario_trace_count": 66,
        "scenario_smoke_trace_count": 66,
        "annual_scenario_trace_count": 66,
        "randomized_trace_count": 32,
        "bounded_trace_count": 98,
        "trace_count": 173,
    }
    mismatches = {
        key: (row.get(key), expected)
        for key, expected in required.items()
        if row.get(key) != expected
    }
    compared_fields = tuple(row.get("compared_fields", ()))
    if compared_fields != TRACE_FIELDS:
        mismatches["compared_fields"] = (compared_fields, TRACE_FIELDS)
    if max(0, int(row.get("checkpoint_count", 0) or 0)) < 98:
        mismatches["checkpoint_count"] = (row.get("checkpoint_count"), ">= 98")
    for digest_key in (
        "manifest_sha256",
        "trace_pairs_sha256",
        "state_pairs_sha256",
    ):
        digest = str(row.get(digest_key, "") or "")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            mismatches[digest_key] = (digest, "lowercase SHA-256")
    coverage_contracts = (
        (
            "required_behaviors",
            "covered_behaviors",
            "missing_behaviors",
            REQUIRED_PARITY_BEHAVIORS,
        ),
        (
            "required_state_fields",
            "covered_state_fields",
            "missing_state_fields",
            REQUIRED_PARITY_STATE_FIELDS,
        ),
    )
    for required_key, covered_key, missing_key, required_values in coverage_contracts:
        required_seen = tuple(row.get(required_key, ()))
        covered_seen = tuple(row.get(covered_key, ()))
        missing_seen = tuple(row.get(missing_key, ()))
        if required_seen != required_values:
            mismatches[required_key] = (required_seen, required_values)
        if covered_seen != required_values:
            mismatches[covered_key] = (covered_seen, required_values)
        if missing_seen:
            mismatches[missing_key] = (missing_seen, ())
    missing_trace_sets = tuple(row.get("missing_trace_sets", ()))
    if missing_trace_sets:
        mismatches["missing_trace_sets"] = (missing_trace_sets, ())
    if mismatches:
        raise ValueError(f"invalid production parity evidence: {mismatches}")
    return row
