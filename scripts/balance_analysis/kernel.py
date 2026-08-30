from __future__ import annotations

from bisect import bisect_left, bisect_right
from array import array
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from fractions import Fraction
import math
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .catalog import CatalogFacts, PurchaseOption, RewardFact, load_catalog_facts
from .model import (
    APPROVED_COHORTS,
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
    "growth.applied_units": "growth_units",
    "growth.stored_units": "growth_units",
    "growth.shared_units": "growth_units",
    "growth.spent_units": "growth_units",
    "plants.full_bloom": "plants",
    "plants.first_full_bloom_day": "day",
    "plants.all_catalog_full_bloom_day": "day",
    "beds.owned": "beds",
    "achievements.claimed": "achievements",
    "coins.gross": "coins",
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
    "environments.discovered": "items",
    "environments.effect_growth_units": "growth_units",
    "environments.effect_coins": "coins",
    "environments.effect_consumables": "items",
    "inventory.units": "items",
    "inventory.effect_cards_remaining": "cards",
    "consumables.growth_units": "growth_units",
    "landmarks.owned": "items",
    "mastery.owned": "ranks",
}


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
    environment_item_ids: Tuple[str, ...] = ()

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


def _environment_daily_discoveries(
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    config: SimulationConfig,
    rng: StableRng,
) -> Tuple[Tuple[str, ...], ...]:
    if not facts.environment_tiers or not facts.environment_discovery_ids:
        return ((),) * config.days
    items_by_tier: MutableMapping[str, List[str]] = defaultdict(list)
    for item in facts.environment_discoveries:
        items_by_tier[item.tier_id].append(item.item_id)
    states = []
    for position, tier in enumerate(facts.environment_tiers):
        tier_rng = StableRng(rng.next_u64(), "environment", position, tier.tier_id)
        states.append({
            "tier": tier,
            "rng": tier_rng,
            "items": tuple(items_by_tier[tier.tier_id]),
            "index": 0,
            "cards": 0,
            "completions": 0,
            "card_target": _truncated_geometric(
                tier_rng,
                tier.base_denominator,
                tier.card_guarantee,
            ),
        })

    daily = []
    active_index = 0
    for day in range(1, config.days + 1):
        study = is_study_day(day, scenario)
        answers = scenario.cohort.cards_per_study_day if study else 0
        complete = False
        if study:
            active_index += 1
            complete = completes_study_day(active_index, scenario.completion_percent)
        discovered = []
        for state in states:
            tier = state["tier"]
            cards_remaining = answers
            while state["index"] < len(state["items"]) and cards_remaining:
                needed = state["card_target"] - state["cards"]
                if cards_remaining < needed:
                    state["cards"] += cards_remaining
                    cards_remaining = 0
                    break
                cards_remaining -= needed
                discovered.append(state["items"][state["index"]])
                state["index"] += 1
                state["cards"] = 0
                state["completions"] = 0
                if state["index"] < len(state["items"]):
                    state["card_target"] = _truncated_geometric(
                        state["rng"],
                        tier.base_denominator,
                        tier.card_guarantee,
                    )
            if state["index"] < len(state["items"]) and complete:
                state["completions"] += 1
                if state["completions"] >= tier.completion_guarantee:
                    discovered.append(state["items"][state["index"]])
                    state["index"] += 1
                    state["cards"] = 0
                    state["completions"] = 0
                    if state["index"] < len(state["items"]):
                        state["card_target"] = _truncated_geometric(
                            state["rng"],
                            tier.base_denominator,
                            tier.card_guarantee,
                        )
        daily.append(tuple(discovered))
    return tuple(daily)


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
    environment_by_day = _environment_daily_discoveries(
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
            environment_item_ids=environment_by_day[day - 1],
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
    applied_growth_units: int
    stored_growth_units: int
    shared_growth_units: int
    growth_spent_units: int
    species_owned: int
    beds_owned: int
    permanent_owned: set
    inventory: Counter
    consumable_effect_cards: Counter
    environment_extension_cards: Counter
    consumable_growth_units: int
    purchases: List[Tuple[int, str, int]]
    environment_owned: int
    finds: int
    find_coins: int
    find_growth_units: int
    find_inventory_units: int
    capped_days: int
    maximum_gap: int
    catalog_completion_day: Optional[int]
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
    active_garden_bonus_id = next((
        option.item_id for option in facts.purchase_options
        if option.category == "garden_bonus" and option.included
    ), "")
    active_scenery_id = next((
        option.item_id for option in facts.purchase_options
        if option.category == "scenery" and option.included
    ), "")
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
        total_growth_units=(
            len(facts.species_ids)
            * facts.full_bloom_growth
            * GROWTH_UNITS_PER_POINT
            if scenario.all_plants_complete else 0
        ),
        applied_growth_units=(
            len(facts.species_ids)
            * facts.full_bloom_growth
            * GROWTH_UNITS_PER_POINT
            if scenario.all_plants_complete else 0
        ),
        stored_growth_units=0,
        shared_growth_units=0,
        growth_spent_units=0,
        species_owned=(
            len(facts.species_ids) if scenario.all_plants_complete
            else max(1, sum(
                1 for option in facts.purchase_options
                if option.category == "species" and option.included
            ))
        ),
        beds_owned=(
            max(6, included_beds) if scenario.all_plants_complete
            else max(2, included_beds)
        ),
        permanent_owned=included,
        inventory=Counter(),
        consumable_effect_cards=Counter(),
        environment_extension_cards=Counter(),
        consumable_growth_units=0,
        purchases=[],
        environment_owned=environment_owned,
        finds=0,
        find_coins=0,
        find_growth_units=0,
        find_inventory_units=0,
        capped_days=0,
        maximum_gap=0,
        catalog_completion_day=None,
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
    )


def _credit(state: RunState, source: str, amount: int) -> None:
    value = max(0, int(amount))
    state.wallet += value
    state.gross_coins += value
    state.coin_sources[source] += value


def _apply_growth(
    state: RunState,
    facts: CatalogFacts,
    growth_units: int,
    milestone_schedule: MilestoneSchedule,
) -> None:
    requested = max(0, int(growth_units))
    state.total_growth_units += requested
    capacity = (
        state.species_owned
        * facts.full_bloom_growth
        * GROWTH_UNITS_PER_POINT
    )
    before = state.applied_growth_units
    applied = min(requested, max(0, capacity - before))
    after = before + applied
    state.applied_growth_units = after
    state.stored_growth_units += requested - applied
    milestone_coins = _coins_for_crossings(milestone_schedule, before, after)
    if milestone_coins:
        _credit(state, "plant_milestones", milestone_coins)
        bonus_percent = state.milestone_bonus_percent
        if bonus_percent:
            bonus_coins, state.milestone_coin_carry_units = divmod(
                milestone_coins * bonus_percent
                + state.milestone_coin_carry_units,
                100,
            )
            if bonus_coins:
                _credit(state, "environment_effects", bonus_coins)
                state.environment_effect_coins += bonus_coins


def _purchase_day(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
    day: int,
    permanent_plan: Sequence[PurchaseOption],
    consumable: Optional[PurchaseOption],
) -> None:
    if scenario.strategy.strategy_id == "no_spend":
        return
    # Buy every affordable unique permanent in deterministic order.  This is
    # end-of-day, so newly acquired mechanics cannot alter the day just closed.
    while state.purchase_cursor < len(permanent_plan):
        option = permanent_plan[state.purchase_cursor]
        if option.item_id in state.permanent_owned:
            state.purchase_cursor += 1
            continue
        growth_cost_units = option.growth_cost * GROWTH_UNITS_PER_POINT
        if option.price_coins > state.wallet or growth_cost_units > state.stored_growth_units:
            break
        state.wallet -= option.price_coins
        state.spent_coins += option.price_coins
        state.stored_growth_units -= growth_cost_units
        state.growth_spent_units += growth_cost_units
        state.permanent_owned.add(option.item_id)
        state.purchases.append((day, option.item_id, option.price_coins))
        state.purchase_cursor += 1
        if option.category == "species":
            state.species_owned = min(len(facts.species_ids), state.species_owned + 1)
        elif option.category == "bed":
            state.beds_owned += 1

    if scenario.strategy.buys_consumables and consumable is not None:
        # One-session cover prevents an unbounded repeatable sink and makes the
        # spend policy comparable across cohorts.
        if (
            state.wallet >= consumable.price_coins
            and state.inventory[consumable.item_id] < 1
            and state.consumable_effect_cards[consumable.item_id] < 1
        ):
            state.wallet -= consumable.price_coins
            state.spent_coins += consumable.price_coins
            state.inventory[consumable.item_id] += 1
            state.purchases.append((day, consumable.item_id, consumable.price_coins))

    if permanent_plan and state.purchase_cursor >= len(permanent_plan) and state.catalog_completion_day is None:
        state.catalog_completion_day = day


def _equip_best_environment(
    state: RunState,
    facts: CatalogFacts,
    scenario: ScenarioSpec,
) -> None:
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


def _apply_effect_grant(
    state: RunState,
    facts: CatalogFacts,
    grant,
    amount_multiplier: int,
    milestone_schedule: MilestoneSchedule,
) -> None:
    amount = grant.amount * max(0, int(amount_multiplier))
    if amount <= 0:
        return
    kind = grant.kind.lower()
    if kind in {"growth", "instant_growth"}:
        units = amount * GROWTH_UNITS_PER_POINT
        state.environment_effect_growth_units += units
        _apply_growth(state, facts, units, milestone_schedule)
    elif kind == "coins":
        _credit(state, "environment_effects", amount)
        state.environment_effect_coins += amount
    elif kind == "consumable" and grant.item_id:
        state.inventory[grant.item_id] += amount
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
) -> None:
    active_ids = (state.active_garden_bonus_id, state.active_scenery_id)
    for item_id in active_ids:
        for effect in facts.effects_by_item_id.get(item_id, ()):
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
                    _apply_effect_grant(
                        state,
                        facts,
                        effect.grant,
                        triggers,
                        milestone_schedule,
                    )
            if triggers and effect.weighted_grants:
                total_weight = sum(weight for _grant, weight in effect.weighted_grants)
                for trigger_index in range(triggers):
                    sequence_key = f"{effect.effect_id}:weighted"
                    sequence = state.effect_counters[sequence_key]
                    state.effect_counters[sequence_key] += 1
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
                    )
            if complete and effect.release_trigger == "valid_completion":
                banked = state.effect_banks[effect.effect_id]
                if banked:
                    state.effect_banks[effect.effect_id] = 0
                    units = banked * GROWTH_UNITS_PER_POINT
                    state.environment_effect_growth_units += units
                    _apply_growth(state, facts, units, milestone_schedule)


def _consume_inventory_growth(
    state: RunState,
    facts: CatalogFacts,
    options_by_id: Mapping[str, PurchaseOption],
    consumables_by_id: Mapping[str, object],
    milestone_schedule: MilestoneSchedule,
) -> None:
    # At most one of each stored item per study day. Card-count effects are
    # activated, not front-loaded; instant Growth is applied immediately.
    for item_id in tuple(sorted(state.inventory)):
        if state.inventory[item_id] <= 0:
            continue
        option = options_by_id.get(item_id)
        consumable = consumables_by_id.get(item_id)
        if option is None or consumable is None or option.growth_value <= 0:
            continue
        state.inventory[item_id] -= 1
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
        if consumable.instant_growth:
            units = consumable.instant_growth * GROWTH_UNITS_PER_POINT
            state.consumable_growth_units += units
            _apply_growth(state, facts, units, milestone_schedule)


def _apply_active_consumable_growth(
    state: RunState,
    facts: CatalogFacts,
    consumables_by_id: Mapping[str, object],
    answers: int,
    milestone_schedule: MilestoneSchedule,
) -> None:
    for item_id in tuple(sorted(state.consumable_effect_cards)):
        remaining = state.consumable_effect_cards[item_id]
        consumable = consumables_by_id.get(item_id)
        if remaining <= 0 or consumable is None or consumable.growth_per_card <= 0:
            continue
        affected = min(answers, remaining)
        extension_remaining = state.environment_extension_cards[item_id]
        base_remaining = max(0, remaining - extension_remaining)
        extension_affected = max(0, affected - base_remaining)
        state.consumable_effect_cards[item_id] -= affected
        state.environment_extension_cards[item_id] -= extension_affected
        units = affected * consumable.growth_per_card * GROWTH_UNITS_PER_POINT
        state.consumable_growth_units += units
        state.environment_effect_growth_units += (
            extension_affected
            * consumable.growth_per_card
            * GROWTH_UNITS_PER_POINT
        )
        _apply_growth(state, facts, units, milestone_schedule)


def _progression_counts(
    state: RunState,
    facts: CatalogFacts,
) -> Tuple[int, int]:
    """Return sequentially allocated Mature and Full Bloom plant counts."""

    full_units = facts.full_bloom_growth * GROWTH_UNITS_PER_POINT
    full_blooms = min(state.species_owned, state.applied_growth_units // full_units)
    remainder = state.applied_growth_units - full_blooms * full_units
    mature_threshold = next(
        (
            stage.threshold_growth
            for stage in facts.stages
            if "mature" in stage.stage_id.lower()
        ),
        facts.stages[-2].threshold_growth,
    ) * GROWTH_UNITS_PER_POINT
    mature = min(
        state.species_owned,
        full_blooms + int(full_blooms < state.species_owned and remainder >= mature_threshold),
    )
    return mature, full_blooms


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
                        _credit(state, "achievements", grant.amount)
                    elif kind in {"growth", "instant_growth", "banked_growth"}:
                        # No current achievement uses direct Growth, but keeping
                        # the catalog grant general avoids a future omission.
                        units = grant.amount * GROWTH_UNITS_PER_POINT
                        state.total_growth_units += units
                        state.stored_growth_units += units
                    elif kind == "consumable" and grant.item_id:
                        state.inventory[grant.item_id] += grant.amount
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
    return {
        "answers.total": state.answers,
        "days.studied": state.studied_days,
        "days.completed": state.completed_days,
        "growth.total_units": state.total_growth_units,
        "growth.applied_units": state.applied_growth_units,
        "growth.stored_units": state.stored_growth_units,
        "growth.shared_units": state.shared_growth_units,
        "growth.spent_units": state.growth_spent_units,
        "plants.full_bloom": min(
            state.species_owned,
            state.applied_growth_units
            // (facts.full_bloom_growth * GROWTH_UNITS_PER_POINT),
        ),
        "plants.first_full_bloom_day": state.first_full_bloom_day,
        "plants.all_catalog_full_bloom_day": state.all_catalog_full_bloom_day,
        "beds.owned": state.beds_owned,
        "achievements.claimed": len(state.claimed_achievements),
        "coins.gross": state.gross_coins,
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
        "mastery.owned": sum(
            1 for option in facts.purchase_options
            if option.category == "mastery" and option.item_id in state.permanent_owned
        ),
    }


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    seed_index: int
    checkpoints: Mapping[int, Mapping[str, Optional[float]]]
    assertion_failures: Tuple[str, ...]
    trace_rows: Tuple[Mapping[str, object], ...] = ()


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
    milestone_schedule = _milestone_schedule(facts, len(facts.species_ids))
    checkpoints = {}
    trace_rows = []
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

            _credit(state, "daily_activity", facts.daily_activity_coins)
            if complete:
                _credit(state, "today_complete", facts.completion_coins)
            if state.study_run % 7 == 0:
                _credit(state, "weekly_streak", facts.weekly_streak_coins)

            rhythm_percent = facts.rhythm_percent(
                sum(state.recent_completion_flags[-7:])
            )
            _consume_inventory_growth(
                state,
                facts,
                options_by_id,
                consumables_by_id,
                milestone_schedule,
            )
            _apply_active_consumable_growth(
                state,
                facts,
                consumables_by_id,
                event.answers,
                milestone_schedule,
            )
            primary_units = (
                event.answers
                * (
                    facts.base_growth_per_review * GROWTH_UNITS_PER_POINT
                    + facts.base_growth_per_review * rhythm_percent
                )
            )
            planted = max(1, min(state.species_owned, state.beds_owned))
            shared_numerator = (
                primary_units
                * max(0, planted - 1)
                * facts.shared_growth_numerator
                + state.shared_remainder
            )
            shared_units, state.shared_remainder = divmod(
                shared_numerator,
                facts.shared_growth_denominator,
            )
            state.shared_growth_units += shared_units
            _apply_growth(
                state,
                facts,
                primary_units + shared_units,
                milestone_schedule,
            )
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
        if event.find_coins:
            _credit(state, "standard_finds", event.find_coins)
        for item_id in event.inventory_items:
            state.inventory[item_id] += 1
        ownership_changed = False
        for item_id in event.environment_item_ids:
            ownership_changed = ownership_changed or item_id not in state.permanent_owned
            state.permanent_owned.add(item_id)
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
            trace_rows.append({
                "day": event.day,
                "study": event.study,
                "answers": event.answers,
                "completed_today": complete,
                "study_run": state.study_run,
                "garden_rhythm_percent": rhythm_percent,
                "growth_total_units": state.total_growth_units,
                "growth_applied_units": state.applied_growth_units,
                "growth_stored_units": state.stored_growth_units,
                "growth_spent_units": state.growth_spent_units,
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
    if state.environment_owned > len(facts.environment_discovery_ids):
        failures.append("ENVIRONMENT-OWNERSHIP-BOUND")
    if state.environment_owned != sum(
        item_id in state.permanent_owned
        for item_id in facts.environment_discovery_ids
    ):
        failures.append("ENVIRONMENT-OWNERSHIP-RECONCILIATION")
    if state.environment_effect_coins != state.coin_sources["environment_effects"]:
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
    return ScenarioOutcome(
        scenario_id=scenario.scenario_id,
        seed_index=seed_index,
        checkpoints=checkpoints,
        assertion_failures=tuple(failures),
        trace_rows=tuple(trace_rows),
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
) -> Mapping[str, Optional[float]]:
    reached = [
        float(value) for value in values
        if value is not None and not math.isnan(float(value))
    ]
    n = len(reached)
    if not reached:
        return {
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
    mean = sum(reached) / n
    variance = (
        sum((value - mean) ** 2 for value in reached) / (n - 1)
        if n > 1 else 0.0
    )
    sd = math.sqrt(variance)
    se = sd / math.sqrt(n)
    return {
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


def _finding_rows(
    statistics: Sequence[Mapping[str, object]],
    *,
    full_bloom_units: int,
) -> List[Mapping[str, object]]:
    rows = []
    for statistic in statistics:
        metric = statistic["metric_id"]
        mean = statistic.get("mean")
        if mean is None or statistic.get("checkpoint_day") != 365:
            continue
        if metric == "coins.top_source_share" and float(mean) > 0.50:
            rows.append({
                "finding_id": f"COIN-CONCENTRATION:{statistic['scenario_id']}",
                "severity": "watch",
                "status": "triggered",
                "domain": "coins",
                "title": "One Coin source supplies more than half of income",
                "metric_refs": [f"{statistic['scenario_id']}|365|{metric}"],
                "threshold": "> 0.50",
                "observed": mean,
                "interpretation": "Review source concentration before changing rewards.",
                "caveat": "This is an analysis heuristic, not a release gate.",
            })
        elif metric == "coins.source_hhi" and float(mean) > 0.25:
            rows.append({
                "finding_id": f"COIN-HHI:{statistic['scenario_id']}",
                "severity": "watch",
                "status": "triggered",
                "domain": "coins",
                "title": "Coin source concentration HHI exceeds 0.25",
                "metric_refs": [f"{statistic['scenario_id']}|365|{metric}"],
                "threshold": "> 0.25",
                "observed": mean,
                "interpretation": "A small number of sources dominate modeled income.",
                "caveat": "This is an analysis heuristic, not a release gate.",
            })
        elif (
            metric == "growth.stored_units"
            and statistic.get("p50") is not None
            and float(statistic["p50"]) > full_bloom_units
        ):
            rows.append({
                "finding_id": f"STORED-GROWTH:{statistic['scenario_id']}",
                "severity": "high",
                "status": "triggered",
                "domain": "endgame",
                "title": "Median Stored Growth exceeds one Full Bloom plant",
                "metric_refs": [f"{statistic['scenario_id']}|365|{metric}"],
                "threshold": f"> {full_bloom_units:,} Growth units",
                "observed": statistic["p50"],
                "interpretation": "The modeled player has exhausted current plant capacity.",
                "caveat": "The threshold assumes 100 units per displayed Growth.",
            })
    rows.extend((
        {
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
        },
        {
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
        },
    ))
    return rows


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
            "permanent_cost_by_category": dict(sorted(permanent_costs.items())),
            "permanent_cost_total": sum(permanent_costs.values()),
            "pre_endgame_permanent_cost_total": sum(
                value for category, value in permanent_costs.items()
                if category not in {"landmark", "mastery"}
            ),
        },
        "repeatable_items": sorted(repeatable_rows, key=lambda row: row["item_id"]),
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
                    collectors[(scenario.scenario_id, checkpoint_day, metric_id)].append(
                        float("nan") if value is None else float(value)
                    )
    return dict(collectors), assertion_counts


def _collect_cohort_worker(
    args: Tuple[SimulationConfig, str, int, int],
) -> Tuple[
    Mapping[Tuple[str, int, str], Sequence[float]],
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


def simulate_balance(
    config: SimulationConfig,
    *,
    facts: Optional[CatalogFacts] = None,
    scenarios: Optional[Sequence[ScenarioSpec]] = None,
    workers: int = 1,
) -> Mapping[str, object]:
    catalog = facts or load_catalog_facts()
    scenario_rows = tuple(scenarios or approved_scenarios())
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
        worker_count = max(1, int(workers))
        if worker_count > 1:
            if facts is not None or scenarios is not None:
                raise ValueError("parallel simulation requires the canonical catalog and scenarios")
            chunk_size = max(1, math.ceil(config.seeds / worker_count))
            batches = [
                (config, cohort.cohort_id, start, min(config.seeds, start + chunk_size))
                for start in range(0, config.seeds, chunk_size)
            ]
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                for batch_collectors, batch_assertions in executor.map(
                    _collect_cohort_worker, batches
                ):
                    for key, values in batch_collectors.items():
                        collectors[key].extend(values)
                    assertion_counts.update(batch_assertions)
        else:
            batch_collectors, batch_assertions = _collect_cohort(
                catalog,
                config,
                tuple(cohort_scenarios),
                range(config.seeds),
            )
            for key, values in batch_collectors.items():
                collectors[key].extend(values)
            assertion_counts.update(batch_assertions)

        for (scenario_id, checkpoint_day, metric_id), values in sorted(collectors.items()):
            summary = _summarize_metric(values, total_n=config.seeds)
            statistics.append({
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
                "unit": METRIC_UNITS[metric_id],
                "estimator": "paired_monte_carlo",
                **summary,
            })

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
            "ENVIRONMENT-OWNERSHIP-BOUND": assertion_counts["ENVIRONMENT-OWNERSHIP-BOUND"],
            "ENVIRONMENT-OWNERSHIP-RECONCILIATION": assertion_counts["ENVIRONMENT-OWNERSHIP-RECONCILIATION"],
            "ENVIRONMENT-COIN-RECONCILIATION": assertion_counts["ENVIRONMENT-COIN-RECONCILIATION"],
            "ENVIRONMENT-GROWTH-BOUND": assertion_counts["ENVIRONMENT-GROWTH-BOUND"],
            "CONSUMABLE-EFFECT-NONNEGATIVE": assertion_counts["CONSUMABLE-EFFECT-NONNEGATIVE"],
            "CONSUMABLE-EXTENSION-BOUND": assertion_counts["CONSUMABLE-EXTENSION-BOUND"],
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
            "case_id": row.case_id,
            "case_label": row.case_label,
        }
        for row in scenario_rows
    ]
    configuration_checks = (
        (
            "CONFIG-COHORT-PAIRS",
            scenarios is not None or tuple(sorted({
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
            len(scenario_projection) == len(scenario_rows),
            len(scenario_rows),
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
    return {
        "$schema": "https://anki-garden.local/schemas/economy-analysis-v1.json",
        "run": {
            "release_target": "2.2.0",
            "model": "catalog-ledger-v1",
            "days": config.days,
            "seed_count": config.seeds,
            "seed_root_sha256": config.seed_root_sha256,
            "rng": "sha256-seeded-splitmix64-v1",
            "quantiles": "nearest-rank",
            "catalog_sha256": catalog.snapshot_sha256,
            "source_date_epoch": config.source_date_epoch,
        },
        "catalog": {
            "sha256": catalog.snapshot_sha256,
            "snapshot": catalog.snapshot,
            "records": list(catalog.catalog_records),
        },
        "analysis": _catalog_analysis(catalog),
        "scenario_matrix": {
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
        "milestones": [
            row for row in statistics
            if row["metric_id"] in {
                "catalog.completion_day",
                "plants.first_full_bloom_day",
                "plants.all_catalog_full_bloom_day",
            }
        ],
        "assertions": assertions,
        "parity": {
            "status": "catalog_oracle_compatible",
            "note": (
                "Random streams are paired across strategies. Production engine "
                "trace comparison remains a separate release test lane."
            ),
        },
        "findings": _finding_rows(
            statistics,
            full_bloom_units=(
                catalog.full_bloom_growth * GROWTH_UNITS_PER_POINT
            ),
        ),
    }
