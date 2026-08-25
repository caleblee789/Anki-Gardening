"""Pure projections for the Garden reward surfaces.

The reward engine and :mod:`ankigarden.models.state` own the facts in these
projections.  This module only joins and groups those facts for a UI; it does
not mutate state, grant rewards, or make eligibility decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from .achievements import ACHIEVEMENT_DEFINITIONS, ACHIEVEMENTS_BY_ID, AchievementDefinition
from .environment import ENVIRONMENT_CATALOG, GROWTH_CHARGES
from .garden_finds import (
    ENVIRONMENT_POOL_ID,
    ENVIRONMENT_POOL_VERSION,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_POOL_ID,
    STANDARD_POOL_VERSION,
    STANDARD_FIND_REGISTRY,
    GardenFindReward,
    PreparedRewardRegistry,
)
from .models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt


@dataclass(frozen=True)
class RewardLine:
    """One resource line within an atomic reward event."""

    reward_type: str
    amount: int
    item_id: str = ""
    plant_id: str = ""

    @property
    def learner_text(self) -> str:
        """Return exact learner-facing copy without parsing receipt prose."""

        amount = max(0, int(self.amount))
        if self.reward_type == "coins":
            unit = "Garden Coin" if amount == 1 else "Garden Coins"
            return f"+{amount:,} {unit}"
        if self.reward_type == "growth":
            return f"+{amount:,} Growth"
        if self.reward_type == "inventory_item":
            item_name = _inventory_item_name(self.item_id)
            if amount != 1 and not item_name.endswith("s"):
                item_name = f"{item_name}s"
            return f"+{amount:,} {item_name}"
        if self.reward_type == "environment_item":
            return f"{_environment_item_name(self.item_id)} added to Weather and Scenery"
        return f"+{amount:,} {_identifier_name(self.reward_type or 'reward')}"


@dataclass(frozen=True)
class RewardSummary:
    """One consolidated user-visible result made of atomic ledger events."""

    scheduler_day: str
    correlation_id: str
    occurred_at: str
    receipts: tuple[RewardReceipt, ...]

    @property
    def event_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(receipt.event_key for receipt in self.receipts))

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(receipt.source for receipt in self.receipts))

    @property
    def title(self) -> str:
        return next((receipt.title for receipt in self.receipts if receipt.title), "")

    @property
    def description(self) -> str:
        return next(
            (receipt.description for receipt in self.receipts if receipt.description),
            "",
        )

    @property
    def event_key(self) -> str:
        """Compatibility value for a summary containing one ledger event."""

        return self.event_keys[0] if len(self.event_keys) == 1 else self.correlation_id

    @property
    def source(self) -> str:
        return self.sources[0] if len(self.sources) == 1 else "stacked_rewards"

    @property
    def source_id(self) -> str:
        values = tuple(dict.fromkeys(
            receipt.source_id for receipt in self.receipts if receipt.source_id
        ))
        return values[0] if len(values) == 1 else ""

    @property
    def lines(self) -> tuple[RewardLine, ...]:
        return tuple(
            RewardLine(
                reward_type=receipt.reward_type,
                amount=max(0, int(receipt.amount)),
                item_id=receipt.item_id,
                plant_id=receipt.plant_id,
            )
            for receipt in self.receipts
            if receipt.reward_type != "reference"
        )

    @property
    def total_amount(self) -> int:
        return sum(line.amount for line in self.lines)

    @property
    def growth_total(self) -> int:
        return sum(
            line.amount for line in self.lines if line.reward_type == "growth"
        )

    @property
    def coins_total(self) -> int:
        return sum(
            line.amount for line in self.lines if line.reward_type == "coins"
        )

    @property
    def inventory_totals(self) -> tuple[tuple[str, int], ...]:
        totals: dict[str, int] = {}
        for line in self.lines:
            if line.reward_type == "inventory_item" and line.item_id:
                totals[line.item_id] = totals.get(line.item_id, 0) + line.amount
        return tuple(sorted(totals.items()))

    @property
    def garden_find_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            receipt.source_id
            for receipt in self.receipts
            if receipt.source in {"garden_find", "garden_find_environment"}
            and receipt.source_id
        ))

    @property
    def achievement_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            receipt.source_id
            for receipt in self.receipts
            if receipt.source in {"achievement", "achievement_backfill"}
            and receipt.source_id
        ))
    @property
    def amounts(self) -> Mapping[str, int]:
        totals: dict[str, int] = {}
        for line in self.lines:
            totals[line.reward_type] = totals.get(line.reward_type, 0) + line.amount
        return totals

    @property
    def reward_lines(self) -> tuple[RewardLine, ...]:
        """Compatibility name for consumers that call lines reward entries."""

        return self.lines

    @property
    def items(self) -> tuple[RewardLine, ...]:
        return self.lines

    @property
    def consolidated_lines(self) -> tuple[RewardLine, ...]:
        """Combine like typed resources while retaining first-seen order."""

        totals: dict[tuple[str, str, str], int] = {}
        order: list[tuple[str, str, str]] = []
        for line in self.lines:
            identity = (line.reward_type, line.item_id, line.plant_id)
            if identity not in totals:
                order.append(identity)
                totals[identity] = 0
            totals[identity] += line.amount
        return tuple(
            RewardLine(
                reward_type=reward_type,
                amount=totals[(reward_type, item_id, plant_id)],
                item_id=item_id,
                plant_id=plant_id,
            )
            for reward_type, item_id, plant_id in order
        )

    @property
    def learner_text(self) -> str:
        """Return one consolidated result assembled from typed reward lines."""

        parts = tuple(line.learner_text for line in self.consolidated_lines)
        if len(parts) <= 2:
            return " and ".join(parts)
        return f"{', '.join(parts[:-1])}, and {parts[-1]}"


@dataclass(frozen=True)
class RecurringRewardPresentation:
    """One canonical recurring rule plus its current-day presentation state."""

    rule_id: str
    source: str
    title: str
    trigger: str
    reward_coins: int
    reward_growth: int
    awarded_today: bool
    status: str
    next_streak_day: int = 0
    streak_days_remaining: int = 0

    @property
    def reward_summary(self) -> str:
        parts: list[str] = []
        if self.reward_coins:
            label = "Garden Coin" if self.reward_coins == 1 else "Garden Coins"
            parts.append(f"+{self.reward_coins:,} {label}")
        if self.reward_growth:
            parts.append(f"+{self.reward_growth:,} Growth")
        return " and ".join(parts) if parts else "No reward"


def _receipt_group_key(receipt: RewardReceipt) -> str:
    return str(receipt.correlation_id or receipt.event_key)


def reward_summary(
    receipts: RewardReceipt | Iterable[RewardReceipt],
    *,
    correlation_id: str = "",
) -> RewardSummary:
    """Project one receipt or one already-grouped sequence of receipts.

    ``recent_reward_summaries`` performs grouping.  This function intentionally
    accepts a sequence as well so callers with a single event can use the same
    projection without manufacturing an intermediate state object.
    """

    if isinstance(receipts, RewardReceipt):
        grouped = (receipts,)
    else:
        grouped = tuple(receipts)
    if not grouped:
        raise ValueError("reward_summary requires at least one receipt")
    if not all(isinstance(receipt, RewardReceipt) for receipt in grouped):
        raise TypeError("reward_summary requires RewardReceipt values")
    identity = str(correlation_id or _receipt_group_key(grouped[0]))
    if any(_receipt_group_key(receipt) != identity for receipt in grouped):
        raise ValueError("reward_summary receipts must share one correlation")

    first = grouped[0]
    return RewardSummary(
        scheduler_day=first.scheduler_day,
        correlation_id=identity,
        occurred_at=max(receipt.occurred_at for receipt in grouped),
        receipts=grouped,
    )


def recent_reward_summaries(
    state_or_receipts: GardenState | Iterable[RewardReceipt],
    *,
    limit: int | None = None,
) -> tuple[RewardSummary, ...]:
    """Group bounded receipt history into stable, atomic reward summaries."""

    if isinstance(state_or_receipts, GardenState):
        receipts = tuple(state_or_receipts.recent_reward_receipts)
    else:
        receipts = tuple(state_or_receipts)
    groups: dict[str, list[RewardReceipt]] = {}
    order: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, RewardReceipt):
            raise TypeError("recent reward history requires RewardReceipt values")
        identity = _receipt_group_key(receipt)
        if identity not in groups:
            groups[identity] = []
        elif identity in order:
            order.remove(identity)
        order.append(identity)
        groups[identity].append(receipt)
    if limit is not None:
        if isinstance(limit, bool) or int(limit) < 0:
            raise ValueError("limit must be a nonnegative integer")
        order = order[-int(limit):] if limit else []
    return tuple(reward_summary(groups[identity]) for identity in order)


def recurring_reward_presentations(
    state: GardenState,
    engine: Any,
    *,
    current_streak_days: int | None = None,
) -> tuple[RecurringRewardPresentation, ...]:
    """Project exact recurring rules and today's committed receipt state."""

    scheduler_day = str(getattr(state.daily_stats, "day", "") or "")
    today_receipts = tuple(
        receipt
        for receipt in state.recent_reward_receipts
        if receipt.scheduler_day == scheduler_day
    )
    today_sources = {receipt.source for receipt in today_receipts}
    first_weekly_achievement = any(
        receipt.source in {"achievement", "achievement_backfill"}
        and receipt.source_id == "streak_7"
        and not bool(
            getattr(state.achievements.get("streak_7"), "historical_backfill", False)
        )
        for receipt in today_receipts
    )

    daily_coins = max(0, int(engine.DAILY_ACTIVITY_COINS))
    weekly_coins = max(0, int(engine.WEEKLY_STREAK_COINS))
    today_all_due_receipts = tuple(
        receipt for receipt in today_receipts if receipt.source == "all_due"
    )
    if today_all_due_receipts:
        # Once earned, the committed ledger remains authoritative even if the
        # learner later changes the equipped Weather or Scenery.
        all_due_coins = sum(
            max(0, int(receipt.amount))
            for receipt in today_all_due_receipts
            if receipt.reward_type == "coins"
        )
        all_due_growth = sum(
            max(0, int(receipt.amount))
            for receipt in today_all_due_receipts
            if receipt.reward_type == "growth"
        )
    else:
        all_due_coins = max(0, int(getattr(engine, "ALL_DUE_BASE_COINS", 0)))
        all_due_growth = max(0, int(getattr(engine, "ALL_DUE_BASE_GROWTH", 0)))
        all_due_resolver = getattr(engine, "all_due_rewards", None)
        if callable(all_due_resolver):
            try:
                resolved_coins, resolved_growth = all_due_resolver()
                all_due_coins = max(0, int(resolved_coins))
                all_due_growth = max(0, int(resolved_growth))
            except Exception:
                # Presentation must remain available if an injected or older
                # engine cannot resolve its equipped all-due bonuses.
                pass

    projected_streak_days = (
        getattr(state, "streak_days", 0) or 0
        if current_streak_days is None
        else current_streak_days
    )
    streak_days = max(0, int(projected_streak_days))
    next_streak_day = ((streak_days // 7) + 1) * 7
    streak_days_remaining = max(1, next_streak_day - streak_days)
    weekly_awarded = (
        "weekly_streak" in today_sources or first_weekly_achievement
    )
    day_label = "day" if streak_days_remaining == 1 else "days"

    return (
        RecurringRewardPresentation(
            rule_id="daily_activity",
            source="daily_activity",
            title="Daily activity",
            trigger="Answer your first card today.",
            reward_coins=daily_coins,
            reward_growth=0,
            awarded_today="daily_activity" in today_sources,
            status=(
                "Earned today" if "daily_activity" in today_sources else "Available"
            ),
        ),
        RecurringRewardPresentation(
            rule_id="all_due",
            source="all_due",
            title="All due cards",
            trigger="Finish today’s due cards.",
            reward_coins=all_due_coins,
            reward_growth=all_due_growth,
            awarded_today="all_due" in today_sources,
            status=(
                "Earned today" if "all_due" in today_sources else "Available"
            ),
        ),
        RecurringRewardPresentation(
            rule_id="weekly_streak",
            source="weekly_streak",
            title="Seven-day streak cycle",
            trigger="Reach each 7-day Anki streak milestone.",
            reward_coins=weekly_coins,
            reward_growth=0,
            awarded_today=weekly_awarded,
            status=(
                "Earned today"
                if weekly_awarded else
                f"Next on Day {next_streak_day:,}, "
                f"{streak_days_remaining:,} streak {day_label} to go"
            ),
            next_streak_day=next_streak_day,
            streak_days_remaining=streak_days_remaining,
        ),
    )


@dataclass(frozen=True)
class GardenFindPresentation:
    """Visible Garden Find hit joined to its current registry metadata."""

    answer_key: str
    scheduler_day: str
    occurred_at: str
    pool_id: str
    pool_version: str
    reward_id: str
    reward_type: str
    amount: int
    item_id: str
    display_name: str
    description: str
    tier: str
    artwork_ref: str
    localization_key: str

    @property
    def title(self) -> str:
        return self.display_name


def _identifier_name(value: str) -> str:
    return str(value or "").replace("_", " ").strip().title() or "Reward"


def _inventory_item_name(item_id: str) -> str:
    normalized = str(item_id or "")
    charge = GROWTH_CHARGES.get(normalized)
    if charge is not None:
        return charge.name
    if normalized.startswith("fertilizer_"):
        tier = normalized.removeprefix("fertilizer_")
        return f"{_identifier_name(tier)} Fertilizer"
    return _identifier_name(normalized or "item")


def _environment_item_name(item_id: str) -> str:
    normalized = str(item_id or "")
    for catalog in ENVIRONMENT_CATALOG.values():
        item = catalog.get(normalized)
        if item is not None:
            return item.name
    return _identifier_name(normalized or "environment item")


def _garden_find_description(
    reward_type: str,
    amount: int,
    persisted_or_registry_description: str,
) -> str:
    """Keep old and registry-backed Growth snapshots concise and accurate."""

    if str(reward_type) == "growth":
        return f"+{max(0, int(amount)):,} Growth"
    return str(persisted_or_registry_description)


def _reward_entries(
    registry: Iterable[GardenFindReward] | PreparedRewardRegistry | Mapping[str, GardenFindReward] | None,
) -> tuple[GardenFindReward, ...]:
    if registry is None:
        return STANDARD_FIND_REGISTRY
    if isinstance(registry, PreparedRewardRegistry):
        return tuple(registry.rewards)
    if isinstance(registry, Mapping):
        return tuple(registry.values())
    return tuple(registry)


def lookup(
    outcome: GardenFindOutcome | GardenState,
    answer_key: str | None = None,
    registry: Iterable[GardenFindReward] | PreparedRewardRegistry | Mapping[str, GardenFindReward] | None = None,
) -> GardenFindPresentation | None:
    """Return a presentation only for a persisted hit.

    Misses and cap pauses return ``None``. Earned copy is read from the outcome
    snapshot first so a later registry version cannot rewrite or hide it.
    """

    # For a direct outcome, accepting the registry as the second positional
    # argument keeps the small API convenient while retaining state lookup's
    # ``(state, answer_key, registry)`` form.
    if not isinstance(outcome, GardenState) and answer_key is not None and not isinstance(answer_key, str):
        if registry is not None:
            raise TypeError("registry was supplied twice")
        registry = answer_key  # type: ignore[assignment]
        answer_key = None
    if isinstance(outcome, GardenState):
        if answer_key is None:
            raise ValueError("answer_key is required when looking up GardenState")
        lookup_key = str(answer_key)
        outcomes = outcome.garden_find_outcomes
        resolved = outcomes.get(lookup_key)
        if resolved is None:
            candidates = tuple(
                candidate
                for candidate in outcomes.values()
                if isinstance(candidate, GardenFindOutcome)
                and candidate.answer_key == lookup_key
            )
            if len(candidates) > 1:
                raise ValueError(
                    "answer_key is ambiguous; use the pool-qualified outcome key"
                )
            resolved = candidates[0] if candidates else None
        outcome = resolved
        if outcome is None:
            return None
    if not isinstance(outcome, GardenFindOutcome) or outcome.status != "hit":
        return None
    reward_id = str(outcome.reward_id)
    if outcome.display_name:
        return GardenFindPresentation(
            answer_key=outcome.answer_key,
            scheduler_day=outcome.scheduler_day,
            occurred_at=outcome.occurred_at,
            pool_id=outcome.pool_id,
            pool_version=outcome.pool_version,
            reward_id=reward_id,
            reward_type=outcome.reward_type,
            amount=max(0, int(outcome.amount)),
            item_id=outcome.item_id,
            display_name=outcome.display_name,
            description=_garden_find_description(
                outcome.reward_type,
                outcome.amount,
                outcome.description,
            ),
            tier=outcome.tier,
            artwork_ref=outcome.artwork_ref,
            localization_key=outcome.localization_key,
        )
    if (
        outcome.pool_id == ENVIRONMENT_POOL_ID
        and outcome.pool_version == ENVIRONMENT_POOL_VERSION
    ):
        environment = next(
            (
                candidate
                for candidate in SPECIAL_ENVIRONMENT_POOL
                if candidate.item_id == reward_id
            ),
            None,
        )
        if environment is None:
            return None
        return GardenFindPresentation(
            answer_key=outcome.answer_key,
            scheduler_day=outcome.scheduler_day,
            occurred_at=outcome.occurred_at,
            pool_id=outcome.pool_id,
            pool_version=outcome.pool_version,
            reward_id=reward_id,
            reward_type=outcome.reward_type or "environment_item",
            amount=max(0, int(outcome.amount)),
            item_id=outcome.item_id or environment.item_id,
            display_name=environment.display_name,
            description="Added to Weather and Scenery",
            tier=environment.tier,
            artwork_ref=environment.item_id,
            localization_key=f"garden_find.environment.{environment.item_id}",
        )
    reward = next(
        (
            candidate
            for candidate in _reward_entries(registry)
            if candidate.reward_id == reward_id
            and candidate.enabled
            and outcome.pool_id == STANDARD_POOL_ID
            and outcome.pool_version == STANDARD_POOL_VERSION
            and candidate.pool_version == outcome.pool_version
        ),
        None,
    )
    if reward is None:
        item_label = (outcome.item_id or reward_id).replace("_", " ").title()
        if outcome.reward_type == "coins":
            description = f"+{max(0, int(outcome.amount)):,} Garden Coins"
        elif outcome.reward_type == "growth":
            description = f"+{max(0, int(outcome.amount)):,} Growth"
        else:
            description = f"+{max(0, int(outcome.amount)):,} {item_label}"
        return GardenFindPresentation(
            answer_key=outcome.answer_key,
            scheduler_day=outcome.scheduler_day,
            occurred_at=outcome.occurred_at,
            pool_id=outcome.pool_id,
            pool_version=outcome.pool_version,
            reward_id=reward_id,
            reward_type=outcome.reward_type,
            amount=max(0, int(outcome.amount)),
            item_id=outcome.item_id,
            display_name=reward_id.replace("_", " ").title(),
            description=_garden_find_description(
                outcome.reward_type,
                outcome.amount,
                description,
            ),
            tier="",
            artwork_ref=outcome.item_id or reward_id,
            localization_key="",
        )
    return GardenFindPresentation(
        answer_key=outcome.answer_key,
        scheduler_day=outcome.scheduler_day,
        occurred_at=outcome.occurred_at,
        pool_id=outcome.pool_id,
        pool_version=outcome.pool_version,
        reward_id=reward_id,
        reward_type=outcome.reward_type or reward.reward_kind,
        amount=max(0, int(outcome.amount)),
        item_id=outcome.item_id or reward.inventory_item_id or "",
        display_name=reward.display_name,
        description=_garden_find_description(
            outcome.reward_type or reward.reward_kind,
            outcome.amount,
            reward.description,
        ),
        tier=reward.tier,
        artwork_ref=reward.artwork_ref,
        localization_key=reward.localization_key,
    )


def recent_garden_finds(
    state: GardenState,
    *,
    limit: int = 8,
    registry: Iterable[GardenFindReward] | PreparedRewardRegistry | Mapping[str, GardenFindReward] | None = None,
) -> tuple[GardenFindPresentation, ...]:
    if isinstance(limit, bool) or int(limit) < 0:
        raise ValueError("limit must be a nonnegative integer")
    if not limit:
        return ()
    visible: list[GardenFindPresentation] = []
    seen_events: set[str] = set()
    for receipt in state.recent_reward_receipts:
        if (
            receipt.source not in {"garden_find", "garden_find_environment"}
            or receipt.event_key in seen_events
        ):
            continue
        prefix = "garden_find:"
        if not receipt.event_key.startswith(prefix):
            continue
        payload = receipt.event_key[len(prefix):]
        answer_key, separator, pool_id = payload.rpartition(":")
        if not separator or not answer_key or not pool_id:
            continue
        outcome = state.garden_find_outcomes.get(f"{pool_id}:{answer_key}")
        presentation = lookup(outcome, registry=registry) if outcome else None
        if presentation is None:
            continue
        seen_events.add(receipt.event_key)
        visible.append(presentation)
    return tuple(visible[-int(limit):])


@dataclass(frozen=True)
class AchievementPresentation:
    """Canonical achievement definition joined with persisted user state."""

    achievement_id: str
    name: str
    description: str
    category: str
    evaluation_mode: str
    progress_metric: str
    progress: float
    progress_target: int
    unlocked: bool
    unlocked_at: str | None
    rewarded_at: str | None
    reward_event_key: str
    historical_backfill: bool
    reward_coins: int
    reward_small_growth_charges: int
    reward_standard_growth_charges: int
    persisted_requirement: str = ""
    persisted_reward_summary: str = ""
    condition_lines: tuple[str, ...] = ()

    @property
    def completed(self) -> bool:
        return self.unlocked

    @property
    def progress_percent(self) -> int:
        return round(self.progress * 100)

    @property
    def current(self) -> int:
        if self.unlocked:
            return self.progress_target
        return min(
            self.progress_target,
            max(0, round(self.progress * self.progress_target)),
        )

    @property
    def value_text(self) -> str:
        return f"{self.current:,} of {self.progress_target:,}"

    @property
    def criteria_text(self) -> str:
        return self.persisted_requirement or self.description

    @property
    def reward_summary(self) -> str:
        if self.persisted_reward_summary:
            return self.persisted_reward_summary.replace("+", "")
        parts: list[str] = []
        if self.reward_coins:
            parts.append(f"{self.reward_coins:,} Garden Coins")
        if self.reward_small_growth_charges:
            parts.append(
                f"{self.reward_small_growth_charges} Small Growth Charge"
            )
        if self.reward_standard_growth_charges:
            parts.append(
                f"{self.reward_standard_growth_charges} Standard Growth Charge"
            )
        return " and ".join(parts) if parts else "Badge only"


def _definition_map(
    definitions: Sequence[AchievementDefinition] | Mapping[str, AchievementDefinition] | None,
) -> Mapping[str, AchievementDefinition]:
    if definitions is None:
        return ACHIEVEMENTS_BY_ID
    if isinstance(definitions, Mapping):
        return definitions
    return {definition.achievement_id: definition for definition in definitions}


def _achievement_condition_lines(
    definition: AchievementDefinition,
    persisted_requirement: str,
    *,
    state: GardenState | None,
    unlocked: bool,
) -> tuple[str, ...]:
    """Keep compound achievement requirements structured outside the UI."""

    if definition.minimum_non_again_percent:
        if state is not None and not unlocked:
            daily_stats = getattr(state, "daily_stats", None)
            answers = max(
                0,
                int(getattr(daily_stats, "reviewed", 0) or 0),
            )
            again_answers = min(
                answers,
                max(0, int(getattr(daily_stats, "wrong", 0) or 0)),
            )
            non_again_percent = _compound_accuracy_percent(
                answers - again_answers,
                answers,
                definition.minimum_non_again_percent,
            )
            return (
                f"{answers:,} card answers, {non_again_percent}% accuracy",
            )
        return (persisted_requirement or definition.description,)
    return (persisted_requirement or definition.description,)


def _compound_accuracy_percent(
    non_again_answers: int,
    total_answers: int,
    required_percent: int,
) -> str:
    """Format accuracy without rounding a near miss up to its requirement."""

    if total_answers <= 0:
        return "0"
    exact = (
        Decimal(max(0, non_again_answers))
        * Decimal(100)
        / Decimal(total_answers)
    )
    rounded_whole = exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    requirement = Decimal(max(0, required_percent))
    if exact < requirement <= rounded_whole:
        rounded_tenth = exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if rounded_tenth >= requirement:
            rounded_tenth = exact.quantize(Decimal("0.1"), rounding=ROUND_DOWN)
        return format(rounded_tenth, ".1f")
    return format(rounded_whole, ".0f")


def achievement_presentation(
    achievement: Achievement | str,
    state: GardenState | None = None,
    *,
    definitions: Sequence[AchievementDefinition] | Mapping[str, AchievementDefinition] | None = None,
) -> AchievementPresentation | None:
    """Project one canonical achievement while retaining saved progress metadata."""

    if isinstance(achievement, str):
        if state is None:
            raise ValueError("state is required when achievement is an ID")
        persisted = state.achievements.get(achievement)
        achievement_id = achievement
    else:
        persisted = achievement
        achievement_id = str(getattr(achievement, "achievement_id", ""))
    definition = _definition_map(definitions).get(achievement_id)
    if definition is None:
        return None
    if not isinstance(persisted, Achievement):
        # A definition without a saved record is a locked, zero-progress card.
        progress = 0.0
        unlocked = False
        unlocked_at = rewarded_at = None
        reward_event_key = ""
        # Derivability is a policy on the definition, not provenance for a
        # learner who has no persisted unlock record.
        historical_backfill = False
        persisted_requirement = persisted_reward_summary = ""
    else:
        progress = min(1.0, max(0.0, float(persisted.progress)))
        unlocked = bool(persisted.unlocked)
        unlocked_at = persisted.unlocked_at
        rewarded_at = persisted.rewarded_at
        reward_event_key = persisted.reward_event_key
        historical_backfill = bool(persisted.historical_backfill)
        persisted_requirement = persisted.requirement
        persisted_reward_summary = persisted.reward_summary
    return AchievementPresentation(
        achievement_id=definition.achievement_id,
        name=definition.name,
        description=definition.description,
        category=definition.category.value,
        evaluation_mode=definition.evaluation_mode.value,
        progress_metric=definition.progress_metric.value,
        progress=progress,
        progress_target=definition.progress_target,
        unlocked=unlocked,
        unlocked_at=unlocked_at,
        rewarded_at=rewarded_at,
        reward_event_key=reward_event_key,
        historical_backfill=historical_backfill,
        reward_coins=definition.reward.coins,
        reward_small_growth_charges=definition.reward.small_growth_charges,
        reward_standard_growth_charges=definition.reward.standard_growth_charges,
        persisted_requirement=persisted_requirement,
        persisted_reward_summary=persisted_reward_summary,
        condition_lines=_achievement_condition_lines(
            definition,
            persisted_requirement,
            state=state,
            unlocked=unlocked,
        ),
    )


def achievement_presentations(
    state: GardenState,
    *,
    definitions: Sequence[AchievementDefinition] | Mapping[str, AchievementDefinition] | None = None,
) -> tuple[AchievementPresentation, ...]:
    """Project definitions in registry order, joining any persisted records."""

    if definitions is None:
        ordered = ACHIEVEMENT_DEFINITIONS
    elif isinstance(definitions, Mapping):
        ordered = tuple(definitions.values())
    else:
        ordered = tuple(definitions)
    result = tuple(
        presentation
        for definition in ordered
        for presentation in (achievement_presentation(definition.achievement_id, state, definitions=definitions),)
        if presentation is not None
    )
    return result


# A concise alias for callers that name projections after their output type.
project_achievements = achievement_presentations


__all__ = [
    "AchievementPresentation",
    "GardenFindPresentation",
    "RecurringRewardPresentation",
    "RewardLine",
    "RewardSummary",
    "achievement_presentation",
    "achievement_presentations",
    "lookup",
    "project_achievements",
    "recent_garden_finds",
    "recent_reward_summaries",
    "recurring_reward_presentations",
    "reward_summary",
]
