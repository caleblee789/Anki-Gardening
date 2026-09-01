"""Pure, authoritative data model for reviewer Session Summaries.

This module deliberately contains no Qt or reviewer-hook code.  The reviewer
integration owns lifecycle detection and supplies engine-confirmed events;
this accumulator only deduplicates, reverses, segments, and projects them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Literal, Sequence, TypeVar

from ..environment import canonical_garden_feature_id
from ..models.state import RewardReceipt
from .formatters import format_garden_coins, format_quantity


TodayCardsStatus = Literal[
    "in_progress",
    "waiting_for_learning",
    "complete",
    "not_eligible",
    "unavailable",
]
TodayCardsKind = Literal["reviewable", "daily_target"]
TodayCardsScope = Literal["deck", "parent_deck", "all_decks", "unavailable"]
ReviewContinuationKind = Literal["deck", "parent_deck"]
MilestoneType = Literal["checkpoint", "stage_change", "full_bloom"]
EnvironmentKind = Literal["garden_feature", "scenery"]
UnlockCategory = Literal[
    "garden_item",
    "environment",
    "plant",
    "planter",
    "background",
]
HighlightKind = Literal[
    "full_bloom",
    "environment",
    "stage_change",
    "major_checkpoint",
    "rare_reward",
    "minor_checkpoint",
]

_TODAY_STATUSES = {
    "in_progress",
    "waiting_for_learning",
    "complete",
    "not_eligible",
    "unavailable",
}
_MILESTONE_TYPES = {"checkpoint", "stage_change", "full_bloom"}
_ENVIRONMENT_KINDS = {"garden_feature", "scenery"}
_UNLOCK_CATEGORIES = {
    "garden_item", "environment", "plant", "planter", "background",
}
_TODAY_KINDS = {"reviewable", "daily_target"}
_TODAY_SCOPES = {"deck", "parent_deck", "all_decks", "unavailable"}
_CONTINUATION_KINDS = {"deck", "parent_deck"}

_UNLOCK_CATEGORY_COPY: dict[str, tuple[str, str]] = {
    "garden_item": (
        "GARDEN DISCOVERY",
        "Added to your Garden collection",
    ),
    "environment": (
        "ENVIRONMENT UNLOCKED",
        "Now available in the Garden",
    ),
    "plant": (
        "PLANT UNLOCKED",
        "Added to your plant collection",
    ),
    "planter": (
        "PLANTER UNLOCKED",
        "Added to your Garden collection",
    ),
    "background": (
        "BACKGROUND UNLOCKED",
        "Now available in the Garden",
    ),
}

logger = logging.getLogger(__name__)


def unlock_category_copy(category: UnlockCategory | str) -> tuple[str, str]:
    """Return the public label and concise destination for one unlock type."""

    return _UNLOCK_CATEGORY_COPY.get(
        str(category or ""),
        _UNLOCK_CATEGORY_COPY["environment"],
    )


def _nonnegative(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must not be negative")
    return normalized


def _positive(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized


def _event_id(value: Any, field_name: str = "event_id") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _plural_cards(count: int, *, completed: bool = False) -> str:
    suffix = " completed" if completed else ""
    return f"{format_quantity(count, 'card')}{suffix}"


def _remaining_cards(count: int) -> str:
    return f"{_plural_cards(count)} remaining"


def _due_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "less than a minute"
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f"{minutes:,} {'minute' if minutes == 1 else 'minutes'}"
    hours = (minutes + 59) // 60
    return f"{hours:,} {'hour' if hours == 1 else 'hours'}"


def format_growth_units(units: int, *, signed: bool = False) -> str:
    """Format exact hundredth units with at most one displayed decimal."""

    normalized = int(units)
    value = (Decimal(abs(normalized)) / Decimal(100)).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )
    if value == value.to_integral():
        text = f"{int(value):,}"
    else:
        whole, fraction = f"{value:.1f}".split(".")
        text = f"{int(whole):,}.{fraction}"
    if normalized < 0:
        return f"-{text}"
    if signed and normalized > 0:
        return f"+{text}"
    return text


@dataclass(frozen=True)
class ReviewContinuationTarget:
    """An explicit Anki review scope that can be resumed safely."""

    kind: ReviewContinuationKind
    deck_id: int | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _CONTINUATION_KINDS:
            raise ValueError(
                "continuation target must identify a routable deck or parent deck"
            )
        if self.deck_id is not None:
            object.__setattr__(self, "deck_id", _positive(self.deck_id, "deck_id"))
        if self.kind in {"deck", "parent_deck"} and self.deck_id is None:
            raise ValueError(f"{self.kind} continuation requires a deck_id")
        object.__setattr__(self, "label", str(self.label or "").strip())


@dataclass(frozen=True)
class TodayCardsSnapshot:
    """One explicit scheduler snapshot; renderers never parse its copy."""

    status: TodayCardsStatus
    cards_remaining: int | None = None
    cards_completed: int = 0
    waiting_cards: int = 0
    currently_due_cards: int | None = None
    next_due_in_seconds: int = 0
    reward_coins: int = 0
    display_lines: tuple[str, ...] = ()
    cards_total: int | None = None
    kind: TodayCardsKind = "reviewable"
    scope: TodayCardsScope = "all_decks"
    scope_label: str = ""
    contributing_deck_count: int = 1
    can_continue_reviews: bool = False
    continuation_target: ReviewContinuationTarget | None = None

    def __post_init__(self) -> None:
        if self.status not in _TODAY_STATUSES:
            raise ValueError(f"unsupported Today’s Cards status: {self.status}")
        if self.cards_remaining is not None:
            object.__setattr__(
                self,
                "cards_remaining",
                _nonnegative(self.cards_remaining, "cards_remaining"),
            )
        if self.currently_due_cards is not None:
            object.__setattr__(
                self,
                "currently_due_cards",
                _nonnegative(self.currently_due_cards, "currently_due_cards"),
            )
        if self.cards_total is not None:
            object.__setattr__(
                self,
                "cards_total",
                _nonnegative(self.cards_total, "cards_total"),
            )
        for name in (
            "cards_completed",
            "waiting_cards",
            "next_due_in_seconds",
            "reward_coins",
        ):
            object.__setattr__(self, name, _nonnegative(getattr(self, name), name))
        object.__setattr__(
            self,
            "contributing_deck_count",
            _nonnegative(self.contributing_deck_count, "contributing_deck_count"),
        )
        if self.kind not in _TODAY_KINDS:
            raise ValueError(f"unsupported Today’s Cards kind: {self.kind}")
        if self.scope not in _TODAY_SCOPES:
            raise ValueError(f"unsupported Today’s Cards scope: {self.scope}")
        object.__setattr__(self, "scope_label", str(self.scope_label or "").strip())
        object.__setattr__(self, "can_continue_reviews", bool(self.can_continue_reviews))
        object.__setattr__(
            self,
            "display_lines",
            tuple(str(line) for line in self.display_lines if str(line).strip()),
        )

        # Preserve a semantic queue size across every verified state.  The
        # renderer must not infer queue facts by parsing status copy.
        if self.status == "complete":
            object.__setattr__(self, "cards_remaining", 0)
            object.__setattr__(self, "currently_due_cards", 0)
        elif self.status == "not_eligible":
            object.__setattr__(self, "cards_remaining", 0)
            object.__setattr__(self, "currently_due_cards", 0)
        elif self.status == "waiting_for_learning":
            if self.cards_remaining is None:
                object.__setattr__(self, "cards_remaining", self.waiting_cards)
            if self.currently_due_cards is None:
                object.__setattr__(self, "currently_due_cards", 0)
        elif self.status == "in_progress" and self.currently_due_cards is None:
            object.__setattr__(
                self,
                "currently_due_cards",
                max(0, int(self.cards_remaining or 0)),
            )

        total = self.cards_total
        if total is not None:
            if self.cards_completed > total:
                raise ValueError("cards_completed must not exceed cards_total")
            if self.cards_remaining is not None and self.cards_remaining > total:
                raise ValueError("cards_remaining must not exceed cards_total")
            if (
                self.status in {"in_progress", "waiting_for_learning", "complete"}
                and self.cards_remaining is not None
                and self.cards_completed + self.cards_remaining != total
            ):
                raise ValueError(
                    "cards_completed plus cards_remaining must equal cards_total"
                )
        if self.can_continue_reviews and not (
            self.kind == "reviewable"
            and self.status == "in_progress"
            and int(self.currently_due_cards or 0) > 0
            and self.continuation_target is not None
        ):
            raise ValueError(
                "can_continue_reviews requires a reviewable, currently due "
                "queue and an explicit continuation_target"
            )

    @property
    def player_lines(self) -> tuple[str, ...]:
        if self.display_lines:
            return self.display_lines
        if self.status == "complete":
            return ("All of today’s cards complete",)
        if self.status == "waiting_for_learning":
            count = self.waiting_cards
            return (
                _remaining_cards(count),
                f"Next card in {_due_time(self.next_due_in_seconds)}",
            )
        if self.status == "not_eligible":
            return ("No cards were due today",)
        if self.status == "unavailable":
            return (
                "Card status unavailable",
                (
                    "Anki Garden could not verify today’s cards. "
                    "Normal Garden Growth is unaffected."
                ),
            )
        remaining = int(self.cards_remaining or 0)
        if self.kind == "daily_target":
            return (f"{remaining:,} to goal",)
        scope_suffix = (
            " across all decks"
            if self.contributing_deck_count > 1 else ""
        )
        return (f"{_remaining_cards(remaining)}{scope_suffix}",)


@dataclass(frozen=True)
class PlantStateSnapshot:
    plant_id: str
    growth_units: int
    stage: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plant_id", _event_id(self.plant_id, "plant_id"))
        object.__setattr__(
            self,
            "growth_units",
            _nonnegative(self.growth_units, "growth_units"),
        )


@dataclass(frozen=True)
class FertilizerSnapshot:
    effect_id: str
    name: str
    remaining_seconds: int
    plant_id: str = ""
    plant_name: str = ""
    source_event_id: str = ""
    active: bool = True
    expires_at_epoch_seconds: int = 0
    remaining_cards: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _event_id(self.effect_id, "effect_id"))
        object.__setattr__(
            self,
            "remaining_seconds",
            _nonnegative(self.remaining_seconds, "remaining_seconds"),
        )
        object.__setattr__(
            self,
            "expires_at_epoch_seconds",
            _nonnegative(
                self.expires_at_epoch_seconds,
                "expires_at_epoch_seconds",
            ),
        )
        object.__setattr__(
            self,
            "remaining_cards",
            _nonnegative(self.remaining_cards, "remaining_cards"),
        )


@dataclass(frozen=True)
class BoosterSnapshot:
    effect_id: str
    remaining_cards: int
    name: str = "Booster Potion"
    plant_id: str = ""
    plant_name: str = ""
    source_event_id: str = ""
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _event_id(self.effect_id, "effect_id"))
        object.__setattr__(
            self,
            "remaining_cards",
            _nonnegative(self.remaining_cards, "remaining_cards"),
        )


@dataclass(frozen=True)
class EffectsSnapshot:
    fertilizers: tuple[FertilizerSnapshot, ...] = ()
    boosters: tuple[BoosterSnapshot, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fertilizers", tuple(self.fertilizers))
        object.__setattr__(self, "boosters", tuple(self.boosters))


@dataclass(frozen=True)
class SessionStartSnapshot:
    """Validation baseline captured when one Anki-day segment begins."""

    today_cards: TodayCardsSnapshot
    effects: EffectsSnapshot = field(default_factory=EffectsSnapshot)
    coin_balance: int = 0
    stored_growth_units: int = 0
    plants: tuple[PlantStateSnapshot, ...] = ()
    existing_event_ids: frozenset[str] = frozenset()
    existing_standard_find_event_ids: frozenset[str] = frozenset()
    existing_milestone_event_ids: frozenset[str] = frozenset()
    owned_environment_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "coin_balance", _nonnegative(self.coin_balance, "coin_balance"))
        object.__setattr__(
            self,
            "stored_growth_units",
            _nonnegative(self.stored_growth_units, "stored_growth_units"),
        )
        object.__setattr__(self, "plants", tuple(self.plants))
        for name in (
            "existing_event_ids",
            "existing_standard_find_event_ids",
            "existing_milestone_event_ids",
            "owned_environment_ids",
        ):
            values = frozenset(
                str(value) for value in getattr(self, name) if str(value)
            )
            if name == "owned_environment_ids":
                values = frozenset((
                    *values,
                    *(canonical_garden_feature_id(value) for value in values),
                ))
            object.__setattr__(
                self,
                name,
                values,
            )

    @property
    def known_event_ids(self) -> frozenset[str]:
        return frozenset((
            *self.existing_event_ids,
            *self.existing_standard_find_event_ids,
            *self.existing_milestone_event_ids,
        ))


@dataclass(frozen=True)
class SessionEndSnapshot:
    today_cards: TodayCardsSnapshot
    effects: EffectsSnapshot = field(default_factory=EffectsSnapshot)


@dataclass(frozen=True)
class PlantGrowthDelta:
    plant_id: str
    plant_name: str
    growth_units: int
    species_name: str = ""
    art_asset: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plant_id", _event_id(self.plant_id, "plant_id"))
        object.__setattr__(
            self,
            "growth_units",
            _positive(self.growth_units, "growth_units"),
        )


@dataclass(frozen=True)
class CoinAward:
    event_id: str
    source_type: str
    source_label: str
    amount: int
    event_key: str = ""
    transaction_id: str = ""
    source_id: str = ""
    correlation_id: str = ""
    included_in_total: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _event_id(self.event_id))
        object.__setattr__(self, "amount", _positive(self.amount, "amount"))
        object.__setattr__(
            self,
            "transaction_id",
            str(self.transaction_id or self.event_id),
        )
        object.__setattr__(self, "event_key", str(self.event_key or ""))
        object.__setattr__(self, "source_id", str(self.source_id or ""))
        object.__setattr__(self, "correlation_id", str(self.correlation_id or ""))
        object.__setattr__(self, "included_in_total", bool(self.included_in_total))


@dataclass(frozen=True)
class StandardFind:
    event_id: str
    find_id: str
    find_name: str
    rarity: str
    reward_type: str
    reward_label: str
    reward_amount: int = 0
    art_asset: str = ""
    occurred_at: str = ""
    item_id: str = ""
    quantity: int = 1
    notable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _event_id(self.event_id))
        object.__setattr__(self, "find_id", _event_id(self.find_id, "find_id"))
        object.__setattr__(
            self,
            "reward_amount",
            _nonnegative(self.reward_amount, "reward_amount"),
        )
        object.__setattr__(self, "item_id", str(self.item_id or ""))
        object.__setattr__(self, "quantity", _positive(self.quantity, "quantity"))
        object.__setattr__(self, "notable", bool(self.notable))


def _standard_find_display_name(find: StandardFind) -> str:
    """Project the concrete inventory grant while retaining its Find ID."""

    fallback = str(find.find_name or "Standard Find")
    if str(find.reward_type or "") != "inventory_item":
        return fallback
    reward_label = str(find.reward_label or "").strip()
    prefix = f"+{max(0, int(find.reward_amount)):,} "
    if reward_label.startswith(prefix):
        granted_name = reward_label[len(prefix):].strip()
        if granted_name:
            return granted_name
    return fallback


@dataclass(frozen=True)
class RewardComponent:
    """One explicitly linked reward component shown in session accounting."""

    amount: int
    reward_type: str
    included_in_session_total: bool
    source_event_ids: tuple[str, ...] = ()
    component_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _positive(self.amount, "amount"))
        reward_type = str(self.reward_type or "").strip()
        if not reward_type:
            raise ValueError("reward_type must not be empty")
        object.__setattr__(self, "reward_type", reward_type)
        object.__setattr__(
            self,
            "component_type",
            str(self.component_type or "").strip(),
        )
        object.__setattr__(
            self,
            "included_in_session_total",
            bool(self.included_in_session_total),
        )
        event_ids = tuple(dict.fromkeys(
            _event_id(value, "source_event_id")
            for value in self.source_event_ids
        ))
        object.__setattr__(self, "source_event_ids", event_ids)
        if self.included_in_session_total and not event_ids:
            raise ValueError(
                "an included reward component must link to a source event"
            )


@dataclass(frozen=True)
class PlantMilestone:
    event_id: str
    plant_id: str
    plant_name: str
    milestone_type: MilestoneType
    occurred_at: str
    plant_art_asset: str = ""
    plant_class: str = ""
    checkpoint_percent: int = 0
    previous_stage: str = ""
    new_stage: str = ""
    stage_path: tuple[str, ...] = ()
    coin_reward: int = 0
    coin_award_event_ids: tuple[str, ...] = ()
    coin_included_in_total: bool = False
    reward: RewardComponent | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _event_id(self.event_id))
        object.__setattr__(self, "plant_id", _event_id(self.plant_id, "plant_id"))
        object.__setattr__(self, "plant_name", str(self.plant_name or "").strip())
        object.__setattr__(self, "plant_class", str(self.plant_class or "").strip())
        if self.milestone_type not in _MILESTONE_TYPES:
            raise ValueError(f"unsupported milestone type: {self.milestone_type}")
        object.__setattr__(
            self,
            "checkpoint_percent",
            _nonnegative(self.checkpoint_percent, "checkpoint_percent"),
        )
        object.__setattr__(
            self,
            "coin_reward",
            _nonnegative(self.coin_reward, "coin_reward"),
        )
        object.__setattr__(self, "stage_path", tuple(self.stage_path))
        object.__setattr__(
            self,
            "coin_award_event_ids",
            tuple(dict.fromkeys(
                _event_id(value, "coin_award_event_id")
                for value in self.coin_award_event_ids
            )),
        )
        object.__setattr__(
            self,
            "coin_included_in_total",
            bool(self.coin_included_in_total),
        )
        reward = self.reward
        if self.coin_reward > 0 and not self.coin_award_event_ids and reward is None:
            raise ValueError(
                "a positive coin milestone reward must link to a source event"
            )
        if reward is None and self.coin_reward > 0:
            reward = RewardComponent(
                amount=self.coin_reward,
                reward_type="coins",
                included_in_session_total=self.coin_included_in_total,
                source_event_ids=self.coin_award_event_ids,
                component_type=(
                    "full_bloom_bonus"
                    if self.milestone_type == "full_bloom"
                    else "milestone_bonus"
                ),
            )
            object.__setattr__(self, "reward", reward)
        elif reward is not None and reward.reward_type == "coins":
            expected_component_type = (
                "full_bloom_bonus"
                if self.milestone_type == "full_bloom"
                else "milestone_bonus"
            )
            if reward.component_type and (
                reward.component_type != expected_component_type
            ):
                raise ValueError(
                    "reward.component_type contradicts the milestone type"
                )
            if not reward.component_type:
                reward = replace(
                    reward,
                    component_type=expected_component_type,
                )
                object.__setattr__(self, "reward", reward)
            if not reward.source_event_ids:
                raise ValueError(
                    "a positive coin milestone reward must link to a source event"
                )
            if self.coin_reward not in {0, reward.amount}:
                raise ValueError("coin_reward contradicts reward.amount")
            if (
                self.coin_award_event_ids
                and self.coin_award_event_ids != reward.source_event_ids
            ):
                raise ValueError(
                    "coin_award_event_ids contradict reward.source_event_ids"
                )
            if (
                self.coin_included_in_total
                and not reward.included_in_session_total
            ):
                raise ValueError(
                    "coin_included_in_total contradicts the reward component"
                )
            object.__setattr__(self, "coin_reward", reward.amount)
            object.__setattr__(
                self,
                "coin_award_event_ids",
                reward.source_event_ids,
            )
            object.__setattr__(
                self,
                "coin_included_in_total",
                reward.included_in_session_total,
            )
        elif reward is not None and self.coin_reward > 0:
            raise ValueError("coin_reward requires a coins reward component")


@dataclass(frozen=True)
class EnvironmentDiscovery:
    event_id: str
    environment_id: str
    environment_name: str
    environment_kind: EnvironmentKind
    rarity: str
    art_asset: str
    effect_summary: str
    occurred_at: str = ""
    unlock_category: UnlockCategory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _event_id(self.event_id))
        kind = str(self.environment_kind or "")
        if kind == "weather":
            kind = "garden_feature"
        object.__setattr__(self, "environment_kind", kind)
        environment_id = _event_id(self.environment_id, "environment_id")
        if kind == "garden_feature":
            environment_id = canonical_garden_feature_id(environment_id)
        object.__setattr__(
            self,
            "environment_id",
            environment_id,
        )
        if kind not in _ENVIRONMENT_KINDS:
            raise ValueError(f"unsupported environment kind: {kind}")
        unlock_category = str(self.unlock_category or "") or (
            "garden_item" if kind == "garden_feature" else "environment"
        )
        if unlock_category not in _UNLOCK_CATEGORIES:
            raise ValueError(
                f"unsupported unlock category: {unlock_category}"
            )
        object.__setattr__(self, "unlock_category", unlock_category)


def _unique_records(records: Iterable[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    seen: set[str] = set()
    for record in records:
        identifier = str(getattr(record, "event_id", "") or "")
        if identifier in seen:
            continue
        seen.add(identifier)
        result.append(record)
    return tuple(result)


def _reward_receipt_identity(receipt: RewardReceipt) -> tuple[Any, ...]:
    return (
        str(receipt.event_key),
        str(receipt.reward_type),
        str(receipt.source),
        str(receipt.source_id),
        str(receipt.scheduler_day),
        str(receipt.correlation_id),
        str(receipt.occurred_at),
        int(receipt.amount),
        str(receipt.item_id),
        str(receipt.plant_id),
        str(receipt.title),
        str(receipt.description),
    )


def _unique_reward_receipts(
    receipts: Iterable[RewardReceipt],
) -> tuple[RewardReceipt, ...]:
    """Keep every typed line while removing exact replay duplicates."""

    result: list[RewardReceipt] = []
    seen: set[tuple[Any, ...]] = set()
    for receipt in receipts:
        if not isinstance(receipt, RewardReceipt):
            raise TypeError("reward_receipts must contain RewardReceipt values")
        identity = _reward_receipt_identity(receipt)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(receipt)
    return tuple(result)


@dataclass(frozen=True)
class SessionProjectGrowthAllocation:
    """Immutable committed Growth credit for one stable project target."""

    target_type: str
    target_id: str
    units: int

    def __post_init__(self) -> None:
        target_type = str(self.target_type or "").strip().casefold()
        target_id = str(self.target_id or "").strip()
        units = _positive(self.units, "project allocation units")
        if target_type not in {"landmark", "mastery", "legacy"}:
            raise ValueError("Unknown Growth project target type")
        if not target_id:
            raise ValueError("Growth project target id is required")
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "units", units)

    def to_dict(self) -> dict[str, int | str]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "units": self.units,
        }


def _merge_project_allocations(
    allocations: Iterable[SessionProjectGrowthAllocation],
) -> tuple[SessionProjectGrowthAllocation, ...]:
    """Coalesce committed credits by stable target without reading state."""

    totals: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for allocation in allocations:
        if not isinstance(allocation, SessionProjectGrowthAllocation):
            raise TypeError(
                "project_allocations must contain "
                "SessionProjectGrowthAllocation values"
            )
        key = (allocation.target_type, allocation.target_id)
        if key not in totals:
            order.append(key)
            totals[key] = 0
        totals[key] += allocation.units
    return tuple(
        SessionProjectGrowthAllocation(target_type, target_id, totals[key])
        for key in order
        for target_type, target_id in (key,)
    )


@dataclass(frozen=True)
class CommittedSessionEvent:
    """Exact deltas from one authoritative local Garden transaction."""

    event_id: str
    anki_day_id: str
    occurred_at: str
    cards_completed: int = 1
    plant_growth: tuple[PlantGrowthDelta, ...] = ()
    shared_growth: tuple[PlantGrowthDelta, ...] = ()
    stored_growth_delta_units: int = 0
    coin_awards: tuple[CoinAward, ...] = ()
    standard_finds: tuple[StandardFind, ...] = ()
    milestones: tuple[PlantMilestone, ...] = ()
    environment_discoveries: tuple[EnvironmentDiscovery, ...] = ()
    reward_receipts: tuple[RewardReceipt, ...] = ()
    total_finds: int = 0
    project_allocations: tuple[SessionProjectGrowthAllocation, ...] = ()
    landmark_growth_delta_units: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _event_id(self.event_id))
        object.__setattr__(self, "anki_day_id", _event_id(self.anki_day_id, "anki_day_id"))
        object.__setattr__(
            self,
            "cards_completed",
            _nonnegative(self.cards_completed, "cards_completed"),
        )
        object.__setattr__(self, "plant_growth", tuple(self.plant_growth))
        object.__setattr__(self, "shared_growth", tuple(self.shared_growth))
        object.__setattr__(self, "coin_awards", _unique_records(self.coin_awards))
        object.__setattr__(self, "standard_finds", _unique_records(self.standard_finds))
        object.__setattr__(self, "milestones", _unique_records(self.milestones))
        object.__setattr__(
            self,
            "environment_discoveries",
            _unique_records(self.environment_discoveries),
        )
        object.__setattr__(
            self,
            "reward_receipts",
            _unique_reward_receipts(self.reward_receipts),
        )
        object.__setattr__(
            self,
            "stored_growth_delta_units",
            int(self.stored_growth_delta_units),
        )
        object.__setattr__(
            self,
            "project_allocations",
            _merge_project_allocations(self.project_allocations),
        )
        object.__setattr__(
            self,
            "landmark_growth_delta_units",
            _nonnegative(
                self.landmark_growth_delta_units,
                "landmark_growth_delta_units",
            ),
        )
        object.__setattr__(
            self,
            "total_finds",
            _nonnegative(self.total_finds, "total_finds"),
        )

    @property
    def related_event_ids(self) -> frozenset[str]:
        return frozenset((
            self.event_id,
            *(item.event_id for item in self.coin_awards),
            *(item.event_id for item in self.standard_finds),
            *(item.event_id for item in self.milestones),
            *(item.event_id for item in self.environment_discoveries),
            *(item.event_key for item in self.reward_receipts),
        ))


@dataclass(frozen=True)
class AuthoritativeEventReversal:
    reversal_id: str
    reversed_event_ids: tuple[str, ...]
    corrected_events: tuple[CommittedSessionEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reversal_id", _event_id(self.reversal_id, "reversal_id"))
        object.__setattr__(
            self,
            "reversed_event_ids",
            tuple(dict.fromkeys(
                _event_id(value, "reversed_event_id")
                for value in self.reversed_event_ids
            )),
        )
        if not self.reversed_event_ids:
            raise ValueError("a reversal must name at least one event")
        object.__setattr__(self, "corrected_events", tuple(self.corrected_events))


@dataclass(frozen=True)
class PlantGrowthTotal:
    plant_id: str
    plant_name: str
    species_name: str
    art_asset: str
    growth_units: int


@dataclass(frozen=True)
class StoredGrowthTotal:
    delta_units: int
    added_units: int
    used_units: int


@dataclass(frozen=True)
class EffectRow:
    kind: Literal["fertilizer", "booster"]
    effect_id: str
    label: str
    value: str
    secondary: str = ""
    ended_during_session: bool = False
    plant_id: str = ""
    remaining_seconds: int = 0
    remaining_cards: int = 0
    expires_at_epoch_seconds: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "remaining_seconds",
            _nonnegative(self.remaining_seconds, "remaining_seconds"),
        )
        object.__setattr__(
            self,
            "remaining_cards",
            _nonnegative(self.remaining_cards, "remaining_cards"),
        )
        object.__setattr__(
            self,
            "expires_at_epoch_seconds",
            _nonnegative(
                self.expires_at_epoch_seconds,
                "expires_at_epoch_seconds",
            ),
        )


@dataclass(frozen=True)
class FindItemQuantity:
    """A display-safe group of identical committed Find outcomes."""

    find_id: str
    find_name: str
    quantity: int
    rarity: str = ""
    reward_type: str = ""
    reward_label: str = ""
    art_asset: str = ""
    item_id: str = ""
    occurred_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "find_id", _event_id(self.find_id, "find_id"))
        object.__setattr__(self, "quantity", _positive(self.quantity, "quantity"))


def _reconcile_find_items(
    finds: Sequence[StandardFind],
    total_finds: int,
) -> tuple[tuple[FindItemQuantity, ...], bool]:
    """Group Finds only when the item-level quantities match the engine total."""

    expected = _nonnegative(total_finds, "total_finds")
    grouped: dict[str, FindItemQuantity] = {}
    order: list[str] = []
    valid = True
    for find in finds:
        key = find.find_id
        current = grouped.get(key)
        if current is None:
            order.append(key)
            grouped[key] = FindItemQuantity(
                find_id=find.find_id,
                find_name=_standard_find_display_name(find),
                quantity=find.quantity,
                rarity=find.rarity,
                reward_type=find.reward_type,
                reward_label=find.reward_label,
                art_asset=find.art_asset,
                item_id=find.item_id,
                occurred_at=find.occurred_at,
            )
            continue
        identity = (
            current.find_name,
            current.rarity,
            current.reward_type,
            current.reward_label,
            current.art_asset,
            current.item_id,
        )
        candidate_identity = (
            _standard_find_display_name(find),
            find.rarity,
            find.reward_type,
            find.reward_label,
            find.art_asset,
            find.item_id,
        )
        if identity != candidate_identity:
            valid = False
            continue
        grouped[key] = replace(current, quantity=current.quantity + find.quantity)

    actual = sum(item.quantity for item in grouped.values())
    if not valid or actual != expected:
        logger.warning(
            "Session Summary Find details omitted: expected total=%s, "
            "grouped quantity=%s, identity_consistent=%s",
            expected,
            actual,
            valid,
        )
        return (), False
    return tuple(grouped[key] for key in order), True


def _validated_milestone_rewards(
    milestones: Sequence[PlantMilestone],
    coin_sources: Sequence[CoinAward],
) -> tuple[PlantMilestone, ...]:
    """Omit contradictory coin components while preserving milestones."""

    coins = {coin.event_id: coin for coin in coin_sources}
    claimed_coin_event_ids: set[str] = set()
    result: list[PlantMilestone] = []
    for milestone in milestones:
        reward = milestone.reward
        if reward is None or reward.reward_type != "coins":
            result.append(milestone)
            continue
        linked = tuple(coins.get(event_id) for event_id in reward.source_event_ids)
        reused = bool(
            claimed_coin_event_ids.intersection(reward.source_event_ids)
        )
        valid = bool(linked) and not reused and all(
            coin is not None
            and coin.included_in_total == reward.included_in_session_total
            and (
                not reward.component_type
                or coin.source_type == reward.component_type
                or reward.component_type == "milestone_bonus"
            )
            for coin in linked
        )
        linked_total = sum(coin.amount for coin in linked if coin is not None)
        if valid and linked_total == reward.amount:
            result.append(milestone)
            claimed_coin_event_ids.update(reward.source_event_ids)
            continue
        logger.warning(
            "Session Summary milestone reward omitted: milestone=%s, "
            "declared=%s, linked=%s, included=%s, reused=%s",
            milestone.event_id,
            reward.amount,
            linked_total,
            reward.included_in_session_total,
            reused,
        )
        result.append(replace(
            milestone,
            coin_reward=0,
            coin_award_event_ids=(),
            coin_included_in_total=False,
            reward=None,
        ))
    return tuple(result)


@dataclass(frozen=True)
class SessionDaySummary:
    anki_day_id: str
    started_at: str
    ended_at: str
    cards_completed: int
    today_cards_start: TodayCardsSnapshot
    today_cards_end: TodayCardsSnapshot
    plant_growth_total_units: int
    plant_growth_by_plant: tuple[PlantGrowthTotal, ...]
    shared_growth_total_units: int
    shared_growth_by_plant: tuple[PlantGrowthTotal, ...]
    stored_growth: StoredGrowthTotal
    garden_coins_earned: int
    coin_sources: tuple[CoinAward, ...]
    standard_finds: tuple[StandardFind, ...]
    milestones: tuple[PlantMilestone, ...]
    environment_discoveries: tuple[EnvironmentDiscovery, ...]
    reward_receipts: tuple[RewardReceipt, ...]
    effects_at_start: EffectsSnapshot
    effects_at_end: EffectsSnapshot
    effects_remaining: tuple[EffectRow, ...]
    total_finds: int = 0
    project_allocations: tuple[SessionProjectGrowthAllocation, ...] = ()
    landmark_growth_delta_units: int = 0
    coin_sources_reconciled: bool = field(default=True, init=False)
    additional_coins_earned: int = field(default=0, init=False)
    garden_coins_total: int = field(default=0, init=False)
    find_items: tuple[FindItemQuantity, ...] = field(default=(), init=False)
    find_items_reconciled: bool = field(default=True, init=False)
    direct_growth_total_units: int | None = None
    growth_applied_total_units: int | None = None

    def __post_init__(self) -> None:
        authoritative_coins = _nonnegative(
            self.garden_coins_earned,
            "garden_coins_earned",
        )
        coin_sources = tuple(self.coin_sources)
        additional_coins = sum(
            award.amount for award in coin_sources
            if not award.included_in_total
        )
        included_coin_total = sum(
            award.amount for award in coin_sources if award.included_in_total
        )
        coin_sources_reconciled = included_coin_total == authoritative_coins
        if not coin_sources_reconciled:
            logger.warning(
                "Session Summary Coin details omitted: authoritative total=%s, "
                "included source total=%s",
                authoritative_coins,
                included_coin_total,
            )
            coin_sources = ()
        object.__setattr__(self, "garden_coins_earned", authoritative_coins)
        object.__setattr__(self, "additional_coins_earned", additional_coins)
        object.__setattr__(
            self,
            "garden_coins_total",
            authoritative_coins + additional_coins,
        )
        object.__setattr__(self, "coin_sources", coin_sources)
        object.__setattr__(
            self,
            "coin_sources_reconciled",
            coin_sources_reconciled,
        )

        total_finds = _nonnegative(self.total_finds, "total_finds")
        object.__setattr__(self, "total_finds", total_finds)
        object.__setattr__(
            self,
            "project_allocations",
            _merge_project_allocations(self.project_allocations),
        )
        object.__setattr__(
            self,
            "landmark_growth_delta_units",
            _nonnegative(
                self.landmark_growth_delta_units,
                "landmark_growth_delta_units",
            ),
        )
        find_items, reconciled = _reconcile_find_items(
            self.standard_finds,
            total_finds,
        )
        object.__setattr__(self, "find_items", find_items)
        object.__setattr__(self, "find_items_reconciled", reconciled)

        direct = (
            max(0, int(self.plant_growth_total_units))
            if self.direct_growth_total_units is None
            else _nonnegative(
                self.direct_growth_total_units,
                "direct_growth_total_units",
            )
        )
        if direct != max(0, int(self.plant_growth_total_units)):
            raise ValueError(
                "direct_growth_total_units must match plant_growth_total_units"
            )
        applied = (
            direct + max(0, int(self.shared_growth_total_units))
            if self.growth_applied_total_units is None
            else _nonnegative(
                self.growth_applied_total_units,
                "growth_applied_total_units",
            )
        )
        if applied != direct + max(0, int(self.shared_growth_total_units)):
            raise ValueError(
                "growth_applied_total_units must equal direct plus shared Growth"
            )
        object.__setattr__(self, "direct_growth_total_units", direct)
        object.__setattr__(self, "growth_applied_total_units", applied)
        object.__setattr__(
            self,
            "milestones",
            _validated_milestone_rewards(self.milestones, self.coin_sources),
        )

    @property
    def has_garden_rewards(self) -> bool:
        return any((
            self.plant_growth_total_units,
            self.shared_growth_total_units,
            self.stored_growth.delta_units,
            self.project_growth_total_units,
            self.garden_coins_earned,
            self.total_finds,
            self.milestones,
            self.environment_discoveries,
        ))

    @property
    def open_garden_available(self) -> bool:
        # Open Garden is the stable contextual action for every non-empty
        # summary, not a reward-dependent affordance.
        return True

    @property
    def continue_reviews_available(self) -> bool:
        return self.today_cards_end.can_continue_reviews

    @property
    def project_growth_total_units(self) -> int:
        """Exact project credit with Landmark-only legacy compatibility."""

        allocated = sum(item.units for item in self.project_allocations)
        landmark_allocated = sum(
            item.units
            for item in self.project_allocations
            if item.target_type == "landmark"
        )
        return allocated + max(
            0,
            self.landmark_growth_delta_units - landmark_allocated,
        )


@dataclass(frozen=True)
class SessionSummaryPayload:
    session_id: str
    started_at: str
    ended_at: str
    segments: tuple[SessionDaySummary, ...]
    cards_completed: int
    terminal_today_cards: TodayCardsSnapshot | None = None
    terminal_effects: EffectsSnapshot | None = None

    def __post_init__(self) -> None:
        if not self.segments:
            return
        terminal = self.segments[-1]
        if self.terminal_today_cards is None:
            object.__setattr__(
                self,
                "terminal_today_cards",
                terminal.today_cards_end,
            )
        if self.terminal_effects is None:
            object.__setattr__(self, "terminal_effects", terminal.effects_at_end)

    @property
    def page_count(self) -> int:
        return len(self.segments)

    @property
    def continue_reviews_available(self) -> bool:
        return bool(
            self.terminal_today_cards
            and self.terminal_today_cards.can_continue_reviews
        )

    @property
    def project_allocations(self) -> tuple[SessionProjectGrowthAllocation, ...]:
        """Session-wide target totals from committed immutable events only."""

        return _merge_project_allocations(
            allocation
            for segment in self.segments
            for allocation in segment.project_allocations
        )


@dataclass(frozen=True)
class LiveSessionSnapshot:
    """Non-finalizing projection of the exact accepted session events.

    ``segments`` are built by the same reducer used by
    :meth:`SessionSummaryAccumulator.finalize`.  The compact reviewer footer
    may combine the three Growth lanes, while callers that need the full
    Session Summary contract retain each component and its detailed records.
    Stored Growth contributes only the amount earned during the session; using
    previously stored Growth must not reduce the celebratory footer total.
    """

    session_id: str
    started_at: str
    as_of: str
    segments: tuple[SessionDaySummary, ...]
    cards_completed: int
    plant_growth_total_units: int
    shared_growth_total_units: int
    stored_growth: StoredGrowthTotal
    garden_coins_earned: int
    coin_sources: tuple[CoinAward, ...]
    standard_finds: tuple[StandardFind, ...]
    milestones: tuple[PlantMilestone, ...]
    environment_discoveries: tuple[EnvironmentDiscovery, ...]
    reward_receipts: tuple[RewardReceipt, ...]
    project_allocations: tuple[SessionProjectGrowthAllocation, ...] = ()
    landmark_growth_delta_units: int = 0

    @property
    def footer_growth_units(self) -> int:
        """Combined HUD Growth without losing its authoritative components."""

        return (
            self.plant_growth_total_units
            + self.shared_growth_total_units
            + self.stored_growth.added_units
            + self.project_growth_total_units
        )

    @property
    def project_growth_total_units(self) -> int:
        allocated = sum(item.units for item in self.project_allocations)
        landmark_allocated = sum(
            item.units
            for item in self.project_allocations
            if item.target_type == "landmark"
        )
        return allocated + max(
            0,
            self.landmark_growth_delta_units - landmark_allocated,
        )

    @property
    def footer_find_count(self) -> int:
        """Expose the engine-owned Find total, independent of detail rows."""

        return sum(segment.total_finds for segment in self.segments)

    @property
    def footer_coin_count(self) -> int:
        """Expose the engine-owned Coin total, independent of detail rows."""

        return sum(segment.garden_coins_total for segment in self.segments)

    @property
    def footer_discovery_count(self) -> int:
        """Expose committed Garden discoveries for the four-metric HUD."""

        return sum(
            len(tuple(segment.environment_discoveries or ()))
            for segment in self.segments
        )

    @property
    def combined_growth_units(self) -> int:
        return self.footer_growth_units

    @property
    def find_count(self) -> int:
        return self.footer_find_count

    @property
    def discovery_count(self) -> int:
        return self.footer_discovery_count

    @property
    def ended_at(self) -> str:
        """Compatibility name shared with the finalized payload."""

        return self.as_of


T = TypeVar("T")


@dataclass(frozen=True)
class LimitedListProjection:
    visible: tuple[Any, ...]
    remaining_count: int = 0
    more_label: str = ""


@dataclass(frozen=True)
class ResultRow:
    key: str
    label: str
    value: str
    expandable: bool = False


@dataclass(frozen=True)
class TodayCardsProjection:
    heading: str
    lines: tuple[str, ...]
    status: TodayCardsStatus = "unavailable"
    status_text: str = ""
    supporting_text: str = ""
    completed_cards: int = 0
    total_cards: int = 0
    progress_value: int = 0
    progress_max: int = 0
    progress_fraction: float = 0.0
    start_completed_cards: int = 0
    start_progress_value: int = 0
    start_progress_fraction: float = 0.0
    remaining_cards: int = 0
    kind: TodayCardsKind = "reviewable"
    scope: TodayCardsScope = "unavailable"
    scope_label: str = ""
    continuation_target: ReviewContinuationTarget | None = None
    animate_progress: bool = False
    is_complete: bool = False
    can_continue_reviews: bool = False


@dataclass(frozen=True)
class SessionHighlight:
    event_id: str
    kind: HighlightKind
    occurred_at: str
    eyebrow: str
    title: str
    supporting_text: str
    art_asset: str = ""
    reward_text: str = ""
    coin_reward: int = 0
    coin_award_event_ids: tuple[str, ...] = ()
    coin_included_in_total: bool = False
    unlock_category: UnlockCategory | None = None


@dataclass(frozen=True)
class HighlightProjection:
    featured: tuple[SessionHighlight, ...] = ()
    overflow: tuple[SessionHighlight, ...] = ()
    more_label: str = ""


@dataclass(frozen=True)
class SessionDayProjection:
    cards_completed_value: str
    cards_completed_label: str
    today_cards: TodayCardsProjection
    result_rows: tuple[ResultRow, ...]
    plant_growth_details: LimitedListProjection
    shared_growth_details: LimitedListProjection
    coin_details: LimitedListProjection
    find_details: LimitedListProjection
    milestones: LimitedListProjection
    environment_discoveries: LimitedListProjection
    effects_remaining: tuple[EffectRow, ...]
    open_garden_available: bool
    reward_metrics: tuple[ResultRow, ...] = ()
    highlights: HighlightProjection = field(default_factory=HighlightProjection)
    growth_applied_total_units: int = 0
    continue_reviews_available: bool = False
    project_allocations: tuple[SessionProjectGrowthAllocation, ...] = ()
    landmark_growth_delta_units: int = 0


def _limited(
    values: Sequence[T],
    limit: int,
    *,
    singular: str,
    plural: str | None = None,
) -> LimitedListProjection:
    visible = tuple(values[:max(0, int(limit))])
    remaining = max(0, len(values) - len(visible))
    noun = singular if remaining == 1 else (plural or f"{singular}s")
    return LimitedListProjection(
        visible,
        remaining,
        f"View {remaining:,} more {noun}" if remaining else "",
    )


def _limited_find_items(
    values: Sequence[FindItemQuantity],
    limit: int = 2,
) -> LimitedListProjection:
    visible = tuple(values[:max(0, int(limit))])
    hidden_quantity = sum(item.quantity for item in values[len(visible):])
    noun = "Standard Find" if hidden_quantity == 1 else "Standard Finds"
    return LimitedListProjection(
        visible=visible,
        remaining_count=hidden_quantity,
        more_label=(
            f"{hidden_quantity:,} more {noun}"
            if hidden_quantity else ""
        ),
    )


def project_today_cards(
    start: TodayCardsSnapshot,
    end: TodayCardsSnapshot,
) -> TodayCardsProjection:
    """Project explicit day totals without deriving them from session work."""

    is_complete = end.status == "complete"
    total = max(0, int(end.cards_total or 0))
    remaining = max(0, int(end.cards_remaining or 0))
    completed = max(0, int(end.cards_completed))

    if is_complete:
        status_text = "All of today’s cards complete"
    elif end.status in {"in_progress", "waiting_for_learning"}:
        if end.kind == "daily_target":
            status_text = f"{remaining:,} to goal"
        else:
            suffix = (
                " across all decks"
                if end.contributing_deck_count > 1 else ""
            )
            status_text = f"{_remaining_cards(remaining)}{suffix}"
    elif end.status == "not_eligible":
        status_text = "No cards were due today"
    else:
        status_text = "Card status unavailable"

    supporting = (
        f"{completed:,} of {format_quantity(total, 'card')} completed"
        if total > 0 else ""
    )
    if end.status == "waiting_for_learning" and end.next_due_in_seconds > 0:
        due_copy = f"Next card in {_due_time(end.next_due_in_seconds)}"
        supporting = f"{supporting} · {due_copy}" if supporting else due_copy
    lines = tuple(line for line in (status_text, supporting) if line)
    if total > 0:
        progress_value = completed
        progress_max = total
        progress_fraction = completed / total
    elif is_complete:
        # A complete state with no recoverable denominator still needs a full
        # accessibility/value state without inventing a card total.
        progress_value = 1
        progress_max = 1
        progress_fraction = 1.0
    else:
        progress_value = 0
        progress_max = 0
        progress_fraction = 0.0

    compatible_start = bool(
        total > 0
        and start.cards_total == end.cards_total
        and start.kind == end.kind
        and start.scope == end.scope
        and start.scope_label == end.scope_label
        and start.cards_completed <= completed
    )
    if total > 0 and start.cards_total is not None and not compatible_start:
        logger.warning(
            "Session Summary Today progress animation omitted: "
            "start_total=%s, end_total=%s, start_kind=%s, end_kind=%s, "
            "start_scope=%s, end_scope=%s",
            start.cards_total,
            end.cards_total,
            start.kind,
            end.kind,
            start.scope,
            end.scope,
        )
    if compatible_start:
        start_completed = max(0, min(total, int(start.cards_completed)))
        start_fraction = start_completed / total
    else:
        # A scope or denominator change must not produce a misleading sweep.
        start_completed = progress_value
        start_fraction = progress_fraction
    return TodayCardsProjection(
        heading="Daily target" if end.kind == "daily_target" else "Today’s cards",
        lines=lines,
        status=end.status,
        status_text=status_text,
        supporting_text=supporting,
        completed_cards=completed,
        total_cards=total,
        progress_value=progress_value,
        progress_max=progress_max,
        progress_fraction=max(0.0, min(1.0, float(progress_fraction))),
        start_completed_cards=start_completed,
        start_progress_value=start_completed,
        start_progress_fraction=max(0.0, min(1.0, float(start_fraction))),
        remaining_cards=remaining,
        kind=end.kind,
        scope=end.scope,
        scope_label=end.scope_label,
        continuation_target=end.continuation_target,
        animate_progress=bool(
            compatible_start and start_completed != progress_value
        ),
        is_complete=is_complete,
        can_continue_reviews=end.can_continue_reviews,
    )


def _merged_growth_rows(summary: SessionDaySummary) -> tuple[PlantGrowthTotal, ...]:
    totals: dict[str, int] = {}
    metadata: dict[str, PlantGrowthTotal] = {}
    for row in (*summary.plant_growth_by_plant, *summary.shared_growth_by_plant):
        totals[row.plant_id] = totals.get(row.plant_id, 0) + max(
            0, int(row.growth_units)
        )
        metadata.setdefault(row.plant_id, row)
    return tuple(sorted(
        (
            PlantGrowthTotal(
                plant_id=plant_id,
                plant_name=metadata[plant_id].plant_name,
                species_name=metadata[plant_id].species_name,
                art_asset=metadata[plant_id].art_asset,
                growth_units=units,
            )
            for plant_id, units in totals.items()
            if units > 0
        ),
        key=lambda row: (-row.growth_units, row.plant_name.casefold(), row.plant_id),
    ))


def _highlight_reward_text(
    milestone: PlantMilestone,
    *,
    displayed_coin_total: int,
) -> str:
    if milestone.coin_reward <= 0:
        return ""
    if milestone.coin_included_in_total:
        return f"{format_garden_coins(milestone.coin_reward, signed=True)} bonus included"
    return (
        f"{format_garden_coins(milestone.coin_reward, signed=True)} bonus"
        f" · included in "
        f"{format_garden_coins(displayed_coin_total, signed=True)} total"
    )


def _session_highlights(summary: SessionDaySummary) -> HighlightProjection:
    candidates: list[tuple[int, str, str, SessionHighlight]] = []
    for milestone in summary.milestones:
        if milestone.milestone_type == "full_bloom":
            priority = 0
            kind: HighlightKind = "full_bloom"
            eyebrow = "FULL BLOOM"
            supporting = "Final growth stage reached"
        elif milestone.milestone_type == "stage_change":
            priority = 2
            kind = "stage_change"
            eyebrow = "STAGE ADVANCED"
            stage_name = milestone.new_stage.replace("_", " ").title()
            supporting = f"Advanced to {stage_name}" if stage_name else "Stage advanced"
        else:
            major = int(milestone.checkpoint_percent) >= 75
            if not major:
                # Minor checkpoints remain available in the accounting
                # breakdown; they do not consume the highlight budget.
                continue
            priority = 3
            kind = "major_checkpoint"
            eyebrow = "GROWTH CHECKPOINT"
            supporting = (
                f"{milestone.checkpoint_percent}% growth checkpoint reached"
                if milestone.checkpoint_percent else "Growth checkpoint reached"
            )
        highlight = SessionHighlight(
            event_id=milestone.event_id,
            kind=kind,
            occurred_at=milestone.occurred_at,
            eyebrow=eyebrow,
            title=milestone.plant_name,
            supporting_text=supporting,
            art_asset=milestone.plant_art_asset,
            reward_text=_highlight_reward_text(
                milestone,
                displayed_coin_total=summary.garden_coins_total,
            ),
            coin_reward=milestone.coin_reward,
            coin_award_event_ids=milestone.coin_award_event_ids,
            coin_included_in_total=milestone.coin_included_in_total,
            unlock_category="plant",
        )
        candidates.append((priority, milestone.occurred_at, milestone.event_id, highlight))

    for discovery in summary.environment_discoveries:
        eyebrow, supporting = unlock_category_copy(
            discovery.unlock_category or "environment"
        )
        highlight = SessionHighlight(
            event_id=discovery.event_id,
            kind="environment",
            occurred_at=discovery.occurred_at,
            eyebrow=eyebrow,
            title=discovery.environment_name,
            supporting_text=supporting,
            art_asset=discovery.art_asset,
            unlock_category=discovery.unlock_category,
        )
        candidates.append((1, discovery.occurred_at, discovery.event_id, highlight))

    for find in summary.standard_finds:
        if not find.notable:
            continue
        highlight = SessionHighlight(
            event_id=find.event_id,
            kind="rare_reward",
            occurred_at=find.occurred_at,
            eyebrow=f"{find.rarity.upper()} FIND",
            title=_standard_find_display_name(find),
            supporting_text=find.reward_label or "Rare Standard Find",
            art_asset=find.art_asset,
            unlock_category="garden_item",
        )
        candidates.append((4, find.occurred_at, find.event_id, highlight))

    ordered = tuple(item[3] for item in sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    ))
    featured = ordered[:2]
    overflow = ordered[2:]
    hidden_count = max(0, len(overflow) - 3)
    noun = "item" if hidden_count == 1 else "items"
    return HighlightProjection(
        featured=featured,
        overflow=overflow,
        more_label=(
            f"View {hidden_count:,} more progress {noun}"
            if hidden_count else ""
        ),
    )


def project_session_day(summary: SessionDaySummary) -> SessionDayProjection:
    rows: list[ResultRow] = []
    growth_rows = _merged_growth_rows(summary)
    # The reviewer footer already presents every positive Growth lane earned
    # during the session.  Keep the final headline on that same committed
    # basis: direct plant Growth + Shared Growth + Growth stored for later +
    # exact long-term project credit.
    # Stored Growth spent during the session is a separate balance movement
    # and is not counted as a second reward after it reaches a plant/project.
    growth_headline_units = (
        int(summary.growth_applied_total_units or 0)
        + max(0, int(summary.stored_growth.added_units))
        + summary.project_growth_total_units
    )
    if growth_headline_units:
        rows.append(ResultRow(
            "growth_applied",
            "Growth applied",
            format_growth_units(growth_headline_units, signed=True),
            bool(
                growth_rows
                or summary.shared_growth_total_units
                or summary.stored_growth.added_units
                or summary.project_growth_total_units
            ),
        ))
    if summary.garden_coins_total:
        rows.append(ResultRow(
            "garden_coins",
            "Garden Coins",
            f"+{summary.garden_coins_total:,}",
            summary.coin_sources_reconciled and bool(summary.coin_sources),
        ))
    if summary.total_finds:
        rows.append(ResultRow(
            "standard_finds",
            "Standard Finds",
            f"+{summary.total_finds:,}",
            summary.find_items_reconciled and bool(summary.find_items),
        ))

    full_bloom = [
        item for item in summary.milestones
        if item.milestone_type == "full_bloom"
    ]
    other_milestones = [
        item for item in summary.milestones
        if item.milestone_type != "full_bloom"
    ]
    shown_other = tuple(other_milestones[:3])
    hidden_milestones = max(0, len(other_milestones) - len(shown_other))
    milestone_projection = LimitedListProjection(
        tuple((*full_bloom, *shown_other)),
        hidden_milestones,
        f"View {hidden_milestones:,} more" if hidden_milestones else "",
    )

    card_label = (
        "card completed this session"
        if summary.cards_completed == 1
        else "cards completed this session"
    )
    metrics = tuple(rows)
    return SessionDayProjection(
        cards_completed_value=f"{summary.cards_completed:,}",
        cards_completed_label=card_label,
        today_cards=project_today_cards(
            summary.today_cards_start,
            summary.today_cards_end,
        ),
        result_rows=metrics,
        plant_growth_details=_limited(
            growth_rows,
            3,
            singular="plant",
        ),
        shared_growth_details=_limited(
            summary.shared_growth_by_plant,
            3,
            singular="plant",
        ),
        coin_details=_limited(summary.coin_sources, 4, singular="reward"),
        find_details=(
            _limited_find_items(summary.find_items)
            if summary.find_items_reconciled else LimitedListProjection(())
        ),
        milestones=milestone_projection,
        environment_discoveries=_limited(
            summary.environment_discoveries,
            2,
            singular="Garden discovery",
            plural="Garden discoveries",
        ),
        effects_remaining=summary.effects_remaining,
        open_garden_available=summary.open_garden_available,
        reward_metrics=metrics,
        highlights=_session_highlights(summary),
        growth_applied_total_units=growth_headline_units,
        continue_reviews_available=summary.continue_reviews_available,
        project_allocations=summary.project_allocations,
        landmark_growth_delta_units=summary.landmark_growth_delta_units,
    )


@dataclass
class _Segment:
    anki_day_id: str
    started_at: str
    start: SessionStartSnapshot
    ended_at: str = ""
    end: SessionEndSnapshot | None = None
    transaction_ids: list[str] = field(default_factory=list)


class SessionSummaryAccumulator:
    """In-memory, event-sourced accumulator for one continuous local session."""

    def __init__(
        self,
        *,
        session_id: str,
        started_at: str,
        anki_day_id: str,
        start_snapshot: SessionStartSnapshot,
    ) -> None:
        self.session_id = _event_id(session_id, "session_id")
        self.started_at = str(started_at)
        self._segments = [_Segment(
            _event_id(anki_day_id, "anki_day_id"),
            str(started_at),
            start_snapshot,
        )]
        self._events: dict[str, CommittedSessionEvent] = {}
        self._seen_event_ids: set[str] = set(start_snapshot.known_event_ids)
        self._reversed_event_ids: set[str] = set()
        self._processed_reversal_ids: set[str] = set()
        self._finalized: SessionSummaryPayload | None = None
        self._finalized_empty = False
        self._taken = False

    @property
    def finalized(self) -> bool:
        return self._finalized is not None or self._finalized_empty

    @property
    def processed_event_ids(self) -> frozenset[str]:
        return frozenset(self._seen_event_ids)

    @property
    def current_anki_day_id(self) -> str:
        return self._segments[-1].anki_day_id

    @property
    def cards_completed(self) -> int:
        return sum(event.cards_completed for event in self._events.values())

    def _segment_for_day(self, anki_day_id: str) -> _Segment:
        for segment in self._segments:
            if segment.anki_day_id == anki_day_id:
                return segment
        raise ValueError(
            "the event belongs to an Anki day without a session segment"
        )

    @staticmethod
    def _filter_nested(
        event: CommittedSessionEvent,
        blocked_ids: set[str],
    ) -> CommittedSessionEvent:
        remaining_finds = tuple(
            item for item in event.standard_finds
            if item.event_id not in blocked_ids
        )
        removed_find_quantity = sum(
            item.quantity for item in event.standard_finds
            if item.event_id in blocked_ids
        )
        return replace(
            event,
            coin_awards=tuple(
                item for item in event.coin_awards
                if item.event_id not in blocked_ids
            ),
            standard_finds=remaining_finds,
            total_finds=max(0, event.total_finds - removed_find_quantity),
            milestones=tuple(
                item for item in event.milestones
                if item.event_id not in blocked_ids
            ),
            environment_discoveries=tuple(
                item for item in event.environment_discoveries
                if item.event_id not in blocked_ids
            ),
            reward_receipts=tuple(
                item for item in event.reward_receipts
                if item.event_key not in blocked_ids
            ),
        )

    def _accept_event(
        self,
        event: CommittedSessionEvent,
        *,
        allowed_replay_ids: frozenset[str] = frozenset(),
    ) -> bool:
        if self.finalized:
            raise RuntimeError("the Session Summary is already finalized")
        segment = self._segment_for_day(event.anki_day_id)
        blocked = {
            event_id
            for event_id in self._seen_event_ids | self._reversed_event_ids
            if event_id not in allowed_replay_ids
        }
        if event.event_id in blocked or event.event_id in self._events:
            return False
        normalized = self._filter_nested(event, blocked)
        self._events[normalized.event_id] = normalized
        if normalized.event_id not in segment.transaction_ids:
            segment.transaction_ids.append(normalized.event_id)
        self._seen_event_ids.update(normalized.related_event_ids)
        return True

    def accept_committed(self, event: CommittedSessionEvent) -> bool:
        """Add one local engine transaction exactly once."""

        return self._accept_event(event)

    def apply_reversal(self, reversal: AuthoritativeEventReversal) -> bool:
        """Mirror only event IDs the engine explicitly reports as reversed."""

        if self.finalized:
            raise RuntimeError("the Session Summary is already finalized")
        if reversal.reversal_id in self._processed_reversal_ids:
            return False
        self._processed_reversal_ids.add(reversal.reversal_id)
        targets = set(reversal.reversed_event_ids)
        changed = False
        for transaction_id, event in tuple(self._events.items()):
            if transaction_id in targets:
                del self._events[transaction_id]
                changed = True
                continue
            filtered = self._filter_nested(event, targets)
            if filtered != event:
                self._events[transaction_id] = filtered
                changed = True
        self._reversed_event_ids.update(targets)
        for corrected in reversal.corrected_events:
            changed = self._accept_event(
                corrected,
                allowed_replay_ids=frozenset(targets),
            ) or changed
        return changed

    def split_anki_day(
        self,
        *,
        ended_at: str,
        end_snapshot: SessionEndSnapshot,
        next_anki_day_id: str,
        next_started_at: str,
        next_start_snapshot: SessionStartSnapshot,
    ) -> None:
        """Close one day segment and begin the next without ending review."""

        if self.finalized:
            raise RuntimeError("the Session Summary is already finalized")
        current = self._segments[-1]
        if current.end is not None:
            raise RuntimeError("the current Anki-day segment is already closed")
        normalized_day = _event_id(next_anki_day_id, "next_anki_day_id")
        if any(segment.anki_day_id == normalized_day for segment in self._segments):
            raise ValueError("an Anki-day segment already exists for this day")
        current.ended_at = str(ended_at)
        current.end = end_snapshot
        self._segments.append(_Segment(
            normalized_day,
            str(next_started_at),
            next_start_snapshot,
        ))
        self._seen_event_ids.update(next_start_snapshot.known_event_ids)

    @staticmethod
    def _growth_totals(
        deltas: Iterable[PlantGrowthDelta],
    ) -> tuple[int, tuple[PlantGrowthTotal, ...]]:
        totals: dict[str, int] = {}
        metadata: dict[str, PlantGrowthDelta] = {}
        for delta in deltas:
            totals[delta.plant_id] = totals.get(delta.plant_id, 0) + delta.growth_units
            metadata[delta.plant_id] = delta
        rows = tuple(sorted(
            (
                PlantGrowthTotal(
                    plant_id,
                    metadata[plant_id].plant_name,
                    metadata[plant_id].species_name,
                    metadata[plant_id].art_asset,
                    units,
                )
                for plant_id, units in totals.items()
                if units > 0
            ),
            key=lambda item: (-item.growth_units, item.plant_name.casefold(), item.plant_id),
        ))
        return sum(item.growth_units for item in rows), rows

    @staticmethod
    def _effect_rows(
        start: EffectsSnapshot,
        end: EffectsSnapshot,
        session_event_ids: frozenset[str],
    ) -> tuple[EffectRow, ...]:
        rows: list[EffectRow] = []
        start_fertilizers = {item.effect_id: item for item in start.fertilizers}
        end_fertilizers = {item.effect_id: item for item in end.fertilizers}
        unmatched_start_fertilizers = dict(start_fertilizers)
        for effect_id, final in end_fertilizers.items():
            initial = unmatched_start_fertilizers.pop(effect_id, None)
            if initial is None:
                # Full Bloom can transfer a paid card-counted effect to the next
                # plant and therefore change its attachment identity. Match
                # the closest same-tier snapshot without treating that
                # transfer as an ended effect plus an unrelated new one.
                candidates = [
                    item
                    for item in unmatched_start_fertilizers.values()
                    if item.name == final.name
                    and item.active
                    and item.remaining_cards >= final.remaining_cards
                ]
                if candidates:
                    initial = min(
                        candidates,
                        key=lambda item: (
                            item.remaining_cards - final.remaining_cards,
                            item.effect_id,
                        ),
                    )
                    unmatched_start_fertilizers.pop(initial.effect_id, None)
            existed = initial is not None
            session_created = bool(
                final.source_event_id
                and final.source_event_id in session_event_ids
            )
            if final.active and final.remaining_cards > 0 and (existed or session_created):
                rows.append(EffectRow(
                    "fertilizer",
                    effect_id,
                    final.name,
                    f"{_plural_cards(final.remaining_cards)} remaining",
                    plant_id=final.plant_id,
                    remaining_cards=final.remaining_cards,
                ))

        start_boosters = {item.effect_id: item for item in start.boosters}
        end_boosters = {item.effect_id: item for item in end.boosters}
        unmatched_start_boosters = dict(start_boosters)
        for effect_id, final in end_boosters.items():
            initial = unmatched_start_boosters.pop(effect_id, None)
            if initial is None:
                candidates = [
                    item
                    for item in unmatched_start_boosters.values()
                    if item.name == final.name
                    and item.active
                    and item.remaining_cards >= final.remaining_cards
                ]
                if candidates:
                    initial = min(
                        candidates,
                        key=lambda item: (
                            item.remaining_cards - final.remaining_cards,
                            item.effect_id,
                        ),
                    )
                    unmatched_start_boosters.pop(initial.effect_id, None)
            existed = initial is not None
            session_created = bool(
                final.source_event_id
                and final.source_event_id in session_event_ids
            )
            if final.active and final.remaining_cards > 0 and (existed or session_created):
                rows.append(EffectRow(
                    "booster",
                    effect_id,
                    final.name,
                    f"{_plural_cards(final.remaining_cards)} remaining",
                    plant_id=final.plant_id,
                    remaining_cards=final.remaining_cards,
                ))
        return tuple(sorted(
            rows,
            key=lambda item: (0 if item.kind == "fertilizer" else 1, item.label, item.effect_id),
        ))

    def _build_segment(self, segment: _Segment) -> SessionDaySummary | None:
        events = [
            self._events[event_id]
            for event_id in segment.transaction_ids
            if event_id in self._events
        ]
        cards = sum(event.cards_completed for event in events)
        if cards <= 0 or segment.end is None:
            return None
        plant_total, plant_rows = self._growth_totals(
            delta for event in events for delta in event.plant_growth
        )
        shared_total, shared_rows = self._growth_totals(
            delta for event in events for delta in event.shared_growth
        )
        stored_deltas = [event.stored_growth_delta_units for event in events]
        project_allocations = _merge_project_allocations(
            allocation
            for event in events
            for allocation in event.project_allocations
        )
        landmark_growth_delta_units = sum(
            event.landmark_growth_delta_units for event in events
        )
        stored_added = sum(value for value in stored_deltas if value > 0)
        stored_used = sum(-value for value in stored_deltas if value < 0)
        coin_sources = tuple(
            award for event in events for award in event.coin_awards
            if award.amount > 0
        )
        standard_finds = tuple(
            find for event in events for find in event.standard_finds
        )
        total_finds = sum(event.total_finds for event in events)
        milestone_records = [
            (milestone, sequence)
            for sequence, milestone in enumerate(
                milestone for event in events for milestone in event.milestones
            )
        ]
        importance = {"full_bloom": 0, "stage_change": 1, "checkpoint": 2}
        milestones = tuple(
            milestone
            for milestone, _sequence in sorted(
                milestone_records,
                key=lambda item: (
                    importance[item[0].milestone_type],
                    item[0].occurred_at,
                    item[1],
                ),
            )
        )
        discoveries_list: list[EnvironmentDiscovery] = []
        seen_environment_ids: set[str] = set()
        for event in events:
            for discovery in event.environment_discoveries:
                environment_id = discovery.environment_id
                if (
                    environment_id in segment.start.owned_environment_ids
                    or environment_id in seen_environment_ids
                ):
                    continue
                seen_environment_ids.add(environment_id)
                discoveries_list.append(discovery)
        discoveries = tuple(discoveries_list)
        reward_receipts = _unique_reward_receipts(
            receipt for event in events for receipt in event.reward_receipts
        )
        session_event_ids = frozenset(
            event_id for event in events for event_id in event.related_event_ids
        )
        return SessionDaySummary(
            anki_day_id=segment.anki_day_id,
            started_at=segment.started_at,
            ended_at=segment.ended_at,
            cards_completed=cards,
            today_cards_start=segment.start.today_cards,
            today_cards_end=segment.end.today_cards,
            plant_growth_total_units=plant_total,
            plant_growth_by_plant=plant_rows,
            shared_growth_total_units=shared_total,
            shared_growth_by_plant=shared_rows,
            stored_growth=StoredGrowthTotal(
                sum(stored_deltas),
                stored_added,
                stored_used,
            ),
            garden_coins_earned=sum(
                item.amount for item in coin_sources if item.included_in_total
            ),
            coin_sources=coin_sources,
            standard_finds=standard_finds,
            milestones=milestones,
            environment_discoveries=discoveries,
            effects_at_start=segment.start.effects,
            effects_at_end=segment.end.effects,
            effects_remaining=self._effect_rows(
                segment.start.effects,
                segment.end.effects,
                session_event_ids,
            ),
            reward_receipts=reward_receipts,
            total_finds=total_finds,
            project_allocations=project_allocations,
            landmark_growth_delta_units=landmark_growth_delta_units,
            direct_growth_total_units=plant_total,
            growth_applied_total_units=plant_total + shared_total,
        )

    def _project_segments(
        self,
        *,
        ended_at: str,
        end_snapshot: SessionEndSnapshot,
    ) -> tuple[SessionDaySummary, ...]:
        """Run the final Session Summary reducer without closing the session."""

        summaries: list[SessionDaySummary] = []
        last_index = len(self._segments) - 1
        for index, segment in enumerate(self._segments):
            candidate = segment
            if index == last_index and segment.end is None:
                candidate = replace(
                    segment,
                    ended_at=str(ended_at),
                    end=end_snapshot,
                )
            summary = self._build_segment(candidate)
            if summary is not None:
                summaries.append(summary)
        return tuple(summaries)

    @staticmethod
    def _live_snapshot_from_segments(
        *,
        session_id: str,
        started_at: str,
        as_of: str,
        segments: tuple[SessionDaySummary, ...],
    ) -> LiveSessionSnapshot:
        stored = StoredGrowthTotal(
            delta_units=sum(segment.stored_growth.delta_units for segment in segments),
            added_units=sum(segment.stored_growth.added_units for segment in segments),
            used_units=sum(segment.stored_growth.used_units for segment in segments),
        )
        return LiveSessionSnapshot(
            session_id=session_id,
            started_at=started_at,
            as_of=str(as_of),
            segments=segments,
            cards_completed=sum(segment.cards_completed for segment in segments),
            plant_growth_total_units=sum(
                segment.plant_growth_total_units for segment in segments
            ),
            shared_growth_total_units=sum(
                segment.shared_growth_total_units for segment in segments
            ),
            stored_growth=stored,
            garden_coins_earned=sum(
                segment.garden_coins_earned for segment in segments
            ),
            coin_sources=tuple(
                item for segment in segments for item in segment.coin_sources
            ),
            standard_finds=tuple(
                item for segment in segments for item in segment.standard_finds
            ),
            milestones=tuple(
                item for segment in segments for item in segment.milestones
            ),
            environment_discoveries=tuple(
                item
                for segment in segments
                for item in segment.environment_discoveries
            ),
            reward_receipts=_unique_reward_receipts(
                receipt
                for segment in segments
                for receipt in segment.reward_receipts
            ),
            project_allocations=_merge_project_allocations(
                allocation
                for segment in segments
                for allocation in segment.project_allocations
            ),
            landmark_growth_delta_units=sum(
                segment.landmark_growth_delta_units for segment in segments
            ),
        )

    def live_snapshot(
        self,
        *,
        ended_at: str,
        end_snapshot: SessionEndSnapshot,
    ) -> LiveSessionSnapshot:
        """Return an exact, repeatable snapshot without finalizing or consuming it."""

        if self._finalized is not None:
            segments = self._finalized.segments
            as_of = self._finalized.ended_at
        elif self._finalized_empty:
            segments = ()
            as_of = str(ended_at)
        else:
            segments = self._project_segments(
                ended_at=ended_at,
                end_snapshot=end_snapshot,
            )
            as_of = str(ended_at)
        return self._live_snapshot_from_segments(
            session_id=self.session_id,
            started_at=self.started_at,
            as_of=as_of,
            segments=segments,
        )

    def finalize(
        self,
        *,
        ended_at: str,
        end_snapshot: SessionEndSnapshot,
    ) -> SessionSummaryPayload | None:
        """Freeze all reportable day segments; repeated calls are idempotent."""

        if self.finalized:
            return self._finalized
        segments = self._project_segments(
            ended_at=ended_at,
            end_snapshot=end_snapshot,
        )
        current = self._segments[-1]
        current.ended_at = str(ended_at)
        current.end = end_snapshot
        if not segments:
            self._finalized_empty = True
            return None
        self._finalized = SessionSummaryPayload(
            session_id=self.session_id,
            started_at=self.started_at,
            ended_at=str(ended_at),
            segments=segments,
            cards_completed=sum(segment.cards_completed for segment in segments),
            terminal_today_cards=end_snapshot.today_cards,
            terminal_effects=end_snapshot.effects,
        )
        return self._finalized

    def take_finalized_payload(self) -> SessionSummaryPayload | None:
        """Return a finalized payload once so duplicate exits cannot reshow it."""

        if not self.finalized:
            raise RuntimeError("the Session Summary has not been finalized")
        if self._taken:
            return None
        self._taken = True
        return self._finalized


__all__ = [
    "AuthoritativeEventReversal",
    "BoosterSnapshot",
    "CoinAward",
    "CommittedSessionEvent",
    "EffectRow",
    "EffectsSnapshot",
    "EnvironmentDiscovery",
    "FertilizerSnapshot",
    "FindItemQuantity",
    "HighlightProjection",
    "LimitedListProjection",
    "LiveSessionSnapshot",
    "PlantGrowthDelta",
    "PlantGrowthTotal",
    "PlantMilestone",
    "PlantStateSnapshot",
    "ResultRow",
    "ReviewContinuationTarget",
    "RewardComponent",
    "SessionDayProjection",
    "SessionDaySummary",
    "SessionEndSnapshot",
    "SessionHighlight",
    "SessionProjectGrowthAllocation",
    "SessionStartSnapshot",
    "SessionSummaryAccumulator",
    "SessionSummaryPayload",
    "StandardFind",
    "StoredGrowthTotal",
    "TodayCardsProjection",
    "TodayCardsKind",
    "TodayCardsScope",
    "TodayCardsSnapshot",
    "UnlockCategory",
    "format_growth_units",
    "project_session_day",
    "project_today_cards",
    "unlock_category_copy",
]
