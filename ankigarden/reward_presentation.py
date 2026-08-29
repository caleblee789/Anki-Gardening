"""Pure projections for the Garden reward surfaces.

The reward engine and :mod:`ankigarden.models.state` own the facts in these
projections.  This module only joins and groups those facts for a UI; it does
not mutate state, grant rewards, or make eligibility decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .achievements import ACHIEVEMENT_DEFINITIONS, ACHIEVEMENTS_BY_ID, AchievementDefinition
from .environment import (
    ENVIRONMENT_CATALOG,
    GROWTH_CHARGES,
    canonical_garden_feature_id,
)
from .garden_finds import (
    ENVIRONMENT_POOL_ID,
    SPECIAL_ENVIRONMENT_POOL,
    STANDARD_POOL_ID,
    STANDARD_POOL_VERSION,
    STANDARD_FIND_REGISTRY,
    GardenFindReward,
    PreparedRewardRegistry,
)
from .models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt
from .ui.formatters import format_quantity
from .ui.session_summary import CommittedSessionEvent, format_growth_units


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
            return (
                f"{_environment_item_name(self.item_id)} added to "
                f"{_environment_item_destination(self.item_id)}"
            )
        return f"+{amount:,} {_identifier_name(self.reward_type or 'reward')}"


class RewardHero(str, Enum):
    """Typed reward-dock hero classes in their exact display priority."""

    FULL_BLOOM = "full_bloom"
    STAGE_CHANGE = "stage_change"
    ENVIRONMENT_DISCOVERY = "environment_discovery"
    GARDEN_FIND = "garden_find"
    CHECKPOINT = "checkpoint"
    COIN_OR_BOOSTER = "coin_or_booster"
    ROUTINE_GROWTH = "routine_growth"

    @property
    def priority(self) -> int:
        return _REWARD_HERO_PRIORITY[self]


_REWARD_HERO_PRIORITY = {
    RewardHero.FULL_BLOOM: 0,
    RewardHero.STAGE_CHANGE: 1,
    RewardHero.ENVIRONMENT_DISCOVERY: 2,
    RewardHero.GARDEN_FIND: 3,
    RewardHero.CHECKPOINT: 4,
    RewardHero.COIN_OR_BOOSTER: 5,
    RewardHero.ROUTINE_GROWTH: 6,
}


@dataclass(frozen=True)
class RewardItemProjection:
    """One stable, typed item inside a committed-answer reward bundle."""

    event_id: str
    kind: RewardHero
    title: str
    category_label: str
    occurred_at: str = ""
    growth_units: int = 0
    garden_coins: int = 0
    inventory_items: tuple[tuple[str, int], ...] = ()
    rarity: str = ""
    artwork_ref: str = ""
    detail: str = ""
    plant_id: str = ""
    plant_name: str = ""
    plant_class: str = ""
    checkpoint_percent: int = 0
    previous_stage: str = ""
    new_stage: str = ""
    stage_path: tuple[str, ...] = ()
    sequence: int = 0

    def __post_init__(self) -> None:
        event_id = str(self.event_id or "").strip()
        if not event_id:
            raise ValueError("reward item event_id must not be empty")
        object.__setattr__(self, "event_id", event_id)
        try:
            kind = self.kind if isinstance(self.kind, RewardHero) else RewardHero(self.kind)
        except ValueError as exc:
            raise ValueError(f"unsupported reward hero kind: {self.kind}") from exc
        object.__setattr__(self, "kind", kind)
        title = str(self.title or "").strip() or "Reward earned"
        category_label = str(self.category_label or "").strip() or "Garden reward"
        object.__setattr__(self, "title", title)
        object.__setattr__(
            self,
            "category_label",
            category_label,
        )
        object.__setattr__(self, "growth_units", max(0, int(self.growth_units)))
        object.__setattr__(self, "garden_coins", max(0, int(self.garden_coins)))
        for field_name in (
            "plant_id",
            "plant_name",
            "plant_class",
            "previous_stage",
            "new_stage",
        ):
            object.__setattr__(
                self,
                field_name,
                str(getattr(self, field_name) or "").strip(),
            )
        object.__setattr__(
            self,
            "checkpoint_percent",
            max(0, int(self.checkpoint_percent)),
        )
        object.__setattr__(
            self,
            "stage_path",
            tuple(
                str(stage).strip()
                for stage in self.stage_path
                if str(stage).strip()
            ),
        )
        object.__setattr__(self, "sequence", max(0, int(self.sequence)))
        inventory: dict[str, int] = {}
        order: list[str] = []
        for raw_item_id, raw_quantity in self.inventory_items:
            item_id = str(raw_item_id or "").strip()
            quantity = max(0, int(raw_quantity))
            if not item_id or not quantity:
                continue
            if item_id not in inventory:
                order.append(item_id)
                inventory[item_id] = 0
            inventory[item_id] += quantity
        object.__setattr__(
            self,
            "inventory_items",
            tuple((item_id, inventory[item_id]) for item_id in order),
        )

    @property
    def routine(self) -> bool:
        return self.kind is RewardHero.ROUTINE_GROWTH

    @property
    def growth_total_units(self) -> int:
        return self.growth_units

    @property
    def coins_total(self) -> int:
        return self.garden_coins

    @property
    def art_asset(self) -> str:
        return self.artwork_ref

    @property
    def tier(self) -> str:
        return self.rarity

    @property
    def learner_inventory_labels(self) -> tuple[str, ...]:
        """Exact quantity copy shared by every reward presentation surface."""

        return tuple(
            RewardLine("inventory_item", quantity, item_id=item_id).learner_text
            for item_id, quantity in self.inventory_items
        )


@dataclass(frozen=True)
class RewardCompactSummary:
    """One categorized chip backed by exact atomic reward-event identities."""

    key: str
    label: str
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        key = str(self.key or "").strip()
        label = str(self.label or "").strip()
        event_ids = tuple(dict.fromkeys(
            str(event_id).strip()
            for event_id in self.event_ids
            if str(event_id).strip()
        ))
        if not key:
            raise ValueError("compact reward summary key must not be empty")
        if not label:
            raise ValueError("compact reward summary label must not be empty")
        if not event_ids:
            raise ValueError("compact reward summary must reference an event")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "event_ids", event_ids)


@dataclass(frozen=True)
class RewardCompactProjection:
    """Bounded reward-dock copy derived from an immutable atomic bundle."""

    eyebrow: str
    hero_title: str
    hero_subtitle: str
    visible_summaries: tuple[RewardCompactSummary, ...] = ()
    hidden_summaries: tuple[RewardCompactSummary, ...] = ()
    more_label: str = ""

    def __post_init__(self) -> None:
        visible = tuple(self.visible_summaries)
        hidden = tuple(self.hidden_summaries)
        if len(visible) > 2:
            raise ValueError("compact reward projection may show at most two summaries")
        object.__setattr__(self, "eyebrow", str(self.eyebrow or "").strip())
        object.__setattr__(self, "hero_title", str(self.hero_title or "").strip())
        object.__setattr__(self, "hero_subtitle", str(self.hero_subtitle or "").strip())
        object.__setattr__(self, "visible_summaries", visible)
        object.__setattr__(self, "hidden_summaries", hidden)
        object.__setattr__(self, "more_label", str(self.more_label or "").strip())

    @property
    def hidden_event_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            event_id
            for summary in self.hidden_summaries
            for event_id in summary.event_ids
        ))

    @property
    def hidden_event_count(self) -> int:
        return len(self.hidden_event_ids)


@dataclass(frozen=True)
class RewardBundleProjection:
    """One answer-correlated dock bundle with a bounded visible projection."""

    bundle_id: str
    occurred_at: str
    all_items: tuple[RewardItemProjection, ...]
    displayed_coin_delta: int | None = None

    def __post_init__(self) -> None:
        bundle_id = str(self.bundle_id or "").strip()
        if not bundle_id:
            raise ValueError("reward bundle_id must not be empty")
        items = tuple(self.all_items)
        if not items:
            raise ValueError("a reward bundle must contain at least one item")
        object.__setattr__(self, "bundle_id", bundle_id)
        object.__setattr__(self, "all_items", items)
        displayed_coin_delta = self.displayed_coin_delta
        if displayed_coin_delta is not None:
            displayed_coin_delta = max(0, int(displayed_coin_delta))
        object.__setattr__(self, "displayed_coin_delta", displayed_coin_delta)

    @property
    def correlation_id(self) -> str:
        return self.bundle_id

    @property
    def event_id(self) -> str:
        return self.bundle_id

    @property
    def hero(self) -> RewardItemProjection:
        return self.all_items[0]

    @property
    def secondary_items(self) -> tuple[RewardItemProjection, ...]:
        return self.all_items[1:4]

    @property
    def visible_items(self) -> tuple[RewardItemProjection, ...]:
        return self.all_items[:4]

    @property
    def compact(self) -> RewardCompactProjection:
        return _project_compact_reward(self)

    @property
    def compact_projection(self) -> RewardCompactProjection:
        """Compatibility-friendly explicit name for compact HUD consumers."""

        return self.compact

    @property
    def visible_summaries(self) -> tuple[RewardCompactSummary, ...]:
        return self.compact.visible_summaries

    @property
    def hidden_summaries(self) -> tuple[RewardCompactSummary, ...]:
        return self.compact.hidden_summaries

    @property
    def items(self) -> tuple[RewardItemProjection, ...]:
        return self.all_items

    @property
    def remaining_count(self) -> int:
        return self.compact.hidden_event_count

    @property
    def more_label(self) -> str:
        return self.compact.more_label

    @property
    def routine_only(self) -> bool:
        return all(item.routine for item in self.all_items)

    @property
    def has_major_reward(self) -> bool:
        return not self.routine_only


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


def _stage_label(stage: str) -> str:
    normalized = str(stage or "").strip()
    if normalized == "rare":
        return "Full Bloom"
    return _identifier_name(normalized or "new stage")


_COMPACT_EYEBROWS = {
    RewardHero.FULL_BLOOM: "MILESTONE REACHED",
    RewardHero.STAGE_CHANGE: "MILESTONE REACHED",
    RewardHero.ENVIRONMENT_DISCOVERY: "DISCOVERY",
    RewardHero.GARDEN_FIND: "GARDEN FIND",
    RewardHero.CHECKPOINT: "CHECKPOINT REACHED",
    RewardHero.COIN_OR_BOOSTER: "REWARD EARNED",
    RewardHero.ROUTINE_GROWTH: "GROWTH APPLIED",
}

_STAGE_SORT_ORDER = {
    "seed": 0,
    "sprout": 1,
    "young": 2,
    "mature": 3,
    "flowering": 4,
    "rare": 5,
}


def _bundle_item_sort_key(
    pair: tuple[int, RewardItemProjection],
) -> tuple[int, int, int, str]:
    index, item = pair
    # One answer may cross multiple stages. The highest ordinary stage becomes
    # the hero while every atomic transition remains available to history.
    stage_rank = (
        -_STAGE_SORT_ORDER.get(item.new_stage, -1)
        if item.kind is RewardHero.STAGE_CHANGE
        else 0
    )
    return item.kind.priority, stage_rank, index, item.event_id


def _same_full_bloom_plant(
    hero: RewardItemProjection,
    candidate: RewardItemProjection,
) -> bool:
    """Return whether a stage row is redundant with this Full Bloom hero."""

    if candidate.kind is not RewardHero.STAGE_CHANGE:
        return False
    if hero.plant_id and candidate.plant_id:
        return hero.plant_id == candidate.plant_id
    hero_name = str(hero.plant_name or hero.title).strip().casefold()
    candidate_name = str(candidate.plant_name or candidate.title).strip().casefold()
    return bool(hero_name and candidate_name and hero_name == candidate_name)


def _inventory_compact_label(item: RewardItemProjection) -> str:
    item_id, quantity = item.inventory_items[0]
    if "booster" in item_id.casefold():
        name = "Booster"
    else:
        # Event titles describe why the item was granted (for example,
        # "Full Bloom"), not the inventory item itself. Compact chips keep the
        # canonical item identity so a Growth Charge cannot look like a second
        # milestone.
        name = _inventory_item_name(item_id)
    detail = str(item.detail or "").strip()
    if detail.startswith("+"):
        return f"{name} {detail}"
    return f"{name} +{quantity:,}"


def _project_compact_reward(
    bundle: RewardBundleProjection,
) -> RewardCompactProjection:
    """Map atomic reward events to a deterministic two-chip dock projection."""

    hero = bundle.hero
    if hero.kind is RewardHero.FULL_BLOOM:
        hero_title = "Full Bloom achieved"
        hero_subtitle = hero.plant_name or hero.title
    elif hero.kind is RewardHero.STAGE_CHANGE:
        hero_title = hero.detail or "Milestone reached"
        hero_subtitle = hero.plant_name or hero.title
    else:
        hero_title = hero.title
        hero_subtitle = hero.detail

    candidates = tuple(
        item
        for item in bundle.all_items[1:]
        if not (
            hero.kind is RewardHero.FULL_BLOOM
            and _same_full_bloom_plant(hero, item)
        )
    )

    growth_units = 0
    growth_event_ids: list[str] = []
    discovery_event_ids: list[str] = []
    find_event_ids: list[str] = []
    inventory_summaries: list[RewardCompactSummary] = []
    checkpoint_summaries: list[RewardCompactSummary] = []
    stage_summaries: list[RewardCompactSummary] = []
    coin_summaries: list[RewardCompactSummary] = []
    other_summaries: list[RewardCompactSummary] = []

    for item in candidates:
        if item.growth_units:
            growth_units += item.growth_units
            growth_event_ids.append(item.event_id)
            continue
        if item.kind is RewardHero.ENVIRONMENT_DISCOVERY:
            discovery_event_ids.append(item.event_id)
            continue
        if item.inventory_items:
            inventory_summaries.append(RewardCompactSummary(
                key=f"inventory:{item.event_id}",
                label=_inventory_compact_label(item),
                event_ids=(item.event_id,),
            ))
            continue
        if item.kind is RewardHero.GARDEN_FIND:
            find_event_ids.append(item.event_id)
            continue
        if item.kind is RewardHero.CHECKPOINT:
            checkpoint_summaries.append(RewardCompactSummary(
                key=f"checkpoint:{item.event_id}",
                label="Checkpoint reached",
                event_ids=(item.event_id,),
            ))
            continue
        if item.kind is RewardHero.STAGE_CHANGE:
            stage_summaries.append(RewardCompactSummary(
                key=f"stage:{item.event_id}",
                label=item.detail or "Stage advanced",
                event_ids=(item.event_id,),
            ))
            continue
        if item.garden_coins:
            coin_summaries.append(RewardCompactSummary(
                key=f"coins:{item.event_id}",
                label=f"+{format_quantity(item.garden_coins, 'coin')}",
                event_ids=(item.event_id,),
            ))
            continue
        other_summaries.append(RewardCompactSummary(
            key=f"reward:{item.event_id}",
            label=item.detail or item.title,
            event_ids=(item.event_id,),
        ))

    summaries: list[RewardCompactSummary] = []
    if growth_event_ids:
        summaries.append(RewardCompactSummary(
            key="growth",
            label=f"+{format_growth_units(growth_units)} growth",
            event_ids=tuple(growth_event_ids),
        ))
    if discovery_event_ids:
        summaries.append(RewardCompactSummary(
            key="discoveries",
            label=format_quantity(
                len(tuple(dict.fromkeys(discovery_event_ids))),
                "discovery",
                "discoveries",
            ),
            event_ids=tuple(discovery_event_ids),
        ))
    if find_event_ids:
        summaries.append(RewardCompactSummary(
            key="garden_finds",
            label=format_quantity(
                len(tuple(dict.fromkeys(find_event_ids))),
                "Garden Find",
            ),
            event_ids=tuple(find_event_ids),
        ))
    summaries.extend(inventory_summaries)
    summaries.extend(checkpoint_summaries)
    summaries.extend(stage_summaries)
    summaries.extend(coin_summaries)
    summaries.extend(other_summaries)

    visible = tuple(summaries[:2])
    hidden = tuple(summaries[2:])
    hidden_event_count = len({
        event_id
        for summary in hidden
        for event_id in summary.event_ids
    })
    more_label = (
        f"{format_quantity(hidden_event_count, 'more reward')} ›"
        if hidden_event_count
        else ""
    )
    return RewardCompactProjection(
        eyebrow=_COMPACT_EYEBROWS[hero.kind],
        hero_title=hero_title,
        hero_subtitle=hero_subtitle,
        visible_summaries=visible,
        hidden_summaries=hidden,
        more_label=more_label,
    )


def _receipt_inventory(
    receipts: Iterable[RewardReceipt],
) -> tuple[tuple[str, int], ...]:
    totals: dict[str, int] = {}
    order: list[str] = []
    for receipt in receipts:
        if receipt.reward_type != "inventory_item" or not receipt.item_id:
            continue
        item_id = str(receipt.item_id)
        if item_id not in totals:
            order.append(item_id)
            totals[item_id] = 0
        totals[item_id] += max(0, int(receipt.amount))
    return tuple(
        (item_id, totals[item_id])
        for item_id in order
        if totals[item_id] > 0
    )


def project_committed_reward_bundle(
    event: CommittedSessionEvent,
    *,
    receipts: Iterable[RewardReceipt] | None = None,
) -> RewardBundleProjection | None:
    """Project one engine-confirmed answer into one stable reward-dock bundle.

    The committed session event owns exact applied Growth, coin, Find,
    milestone, and discovery facts. Optional typed receipts add resources that
    are not represented by that contract yet, chiefly inventory or Booster
    rewards. Every supplied receipt must share the answer correlation; silently
    joining another answer would violate the dock's exact-once boundary.
    """

    if not isinstance(event, CommittedSessionEvent):
        raise TypeError("event must be a CommittedSessionEvent")
    bundle_id = str(event.event_id)
    typed_receipts = tuple(
        event.reward_receipts if receipts is None else receipts
    )
    if not all(isinstance(receipt, RewardReceipt) for receipt in typed_receipts):
        raise TypeError("receipts must contain RewardReceipt values")
    if any(_receipt_group_key(receipt) != bundle_id for receipt in typed_receipts):
        raise ValueError("reward bundle receipts must share the committed event correlation")

    items: list[RewardItemProjection] = []
    embedded_coins = 0
    embedded_direct_growth_units = 0

    milestone_event_ids: set[str] = set()
    for milestone in event.milestones:
        milestone_event_ids.add(milestone.event_id)
        # The milestone item below already renders this value. Count every
        # rendered milestone Coin here, including an additional (not included
        # in the base total) award, so the canonical footer delta is not added
        # a second time by the reconciliation row.
        embedded_coins += max(0, int(milestone.coin_reward))
        if milestone.milestone_type == "full_bloom":
            kind = RewardHero.FULL_BLOOM
            category = "Full Bloom"
            detail = "Reached Full Bloom"
        elif milestone.milestone_type == "stage_change":
            kind = RewardHero.STAGE_CHANGE
            category = "Stage change"
            detail = f"Reached {_stage_label(milestone.new_stage)}"
        else:
            kind = RewardHero.CHECKPOINT
            category = "Checkpoint reached"
            detail = (
                f"{max(0, int(milestone.checkpoint_percent))}% toward "
                f"{_stage_label(milestone.new_stage)}"
            )
        items.append(RewardItemProjection(
            event_id=milestone.event_id,
            kind=kind,
            title=milestone.plant_name or "Plant milestone",
            category_label=category,
            occurred_at=milestone.occurred_at or event.occurred_at,
            garden_coins=max(0, int(milestone.coin_reward)),
            artwork_ref=milestone.plant_art_asset,
            detail=detail,
            plant_id=milestone.plant_id,
            plant_name=milestone.plant_name,
            plant_class=milestone.plant_class,
            checkpoint_percent=milestone.checkpoint_percent,
            previous_stage=milestone.previous_stage,
            new_stage=milestone.new_stage,
            stage_path=milestone.stage_path,
            sequence=len(items),
        ))

    find_ids: set[str] = set()
    projected_find_count = 0
    for find in event.standard_finds:
        find_ids.add(find.find_id)
        find_quantity = max(1, int(find.quantity))
        projected_find_count += find_quantity
        reward_type = str(find.reward_type or "")
        reward_amount = max(0, int(find.reward_amount))
        growth_units = reward_amount * 100 if reward_type == "growth" else 0
        coins = reward_amount if reward_type == "coins" else 0
        inventory = (
            ((find.item_id or find.find_id, reward_amount),)
            if reward_type == "inventory_item" and reward_amount
            else ()
        )
        embedded_direct_growth_units += growth_units
        embedded_coins += coins
        items.append(RewardItemProjection(
            event_id=find.event_id,
            kind=RewardHero.GARDEN_FIND,
            title=find.find_name or "Garden Find",
            category_label="Garden Find",
            occurred_at=find.occurred_at or event.occurred_at,
            growth_units=growth_units,
            garden_coins=coins,
            inventory_items=inventory,
            rarity=find.rarity,
            artwork_ref=find.art_asset,
            detail=find.reward_label,
            sequence=len(items),
        ))
        # A grouped StandardFind keeps one rich payout item, then contributes
        # zero-value occurrence markers. This makes its authoritative quantity
        # countable in expandable history without duplicating Growth, Coins,
        # inventory, or receipts.
        for occurrence in range(2, find_quantity + 1):
            items.append(RewardItemProjection(
                event_id=f"{find.event_id}:occurrence:{occurrence}",
                kind=RewardHero.GARDEN_FIND,
                title=find.find_name or "Garden Find",
                category_label="Garden Find",
                occurred_at=find.occurred_at or event.occurred_at,
                rarity=find.rarity,
                artwork_ref=find.art_asset,
                detail="Additional occurrence",
                sequence=len(items),
            ))

    # Engine totals remain authoritative even when a legacy or partial result
    # lacks item-level Find metadata. Deterministic zero-value markers keep the
    # missing occurrences locatable in reward history without inventing a
    # payout or mutating the session accumulator.
    missing_find_count = max(0, int(event.total_finds) - projected_find_count)
    for occurrence in range(1, missing_find_count + 1):
        items.append(RewardItemProjection(
            event_id=f"{bundle_id}:find:unitemized:{occurrence}",
            kind=RewardHero.GARDEN_FIND,
            title="Garden Find",
            category_label="Garden Find",
            occurred_at=event.occurred_at,
            detail="Details unavailable",
            sequence=len(items),
        ))

    environment_ids: set[str] = set()
    for discovery in event.environment_discoveries:
        environment_ids.add(discovery.environment_id)
        items.append(RewardItemProjection(
            event_id=discovery.event_id,
            kind=RewardHero.ENVIRONMENT_DISCOVERY,
            title=discovery.environment_name or "Environment discovered",
            category_label="Environment discovery",
            occurred_at=discovery.occurred_at or event.occurred_at,
            rarity=discovery.rarity,
            artwork_ref=discovery.art_asset,
            detail=discovery.effect_summary,
            sequence=len(items),
        ))

    receipt_groups: dict[str, list[RewardReceipt]] = {}
    receipt_order: list[str] = []
    for receipt in typed_receipts:
        if receipt.reward_type == "reference":
            continue
        event_key = str(receipt.event_key)
        if event_key not in receipt_groups:
            receipt_groups[event_key] = []
            receipt_order.append(event_key)
        receipt_groups[event_key].append(receipt)

    for event_key in receipt_order:
        group = tuple(receipt_groups[event_key])
        sources = {str(receipt.source) for receipt in group}
        source_ids = {str(receipt.source_id) for receipt in group if receipt.source_id}
        if (
            sources.intersection({"garden_find", "garden_find_environment"})
            and (source_ids.intersection(find_ids) or source_ids.intersection(environment_ids))
        ):
            # The committed Find/discovery carries richer persisted metadata.
            continue
        coins = sum(
            max(0, int(receipt.amount))
            for receipt in group
            if receipt.reward_type == "coins"
        )
        growth_units = 100 * sum(
            max(0, int(receipt.amount))
            for receipt in group
            if receipt.reward_type == "growth"
        )
        inventory = _receipt_inventory(group)
        environment_items = tuple(
            str(receipt.item_id or receipt.source_id)
            for receipt in group
            if receipt.reward_type == "environment_item"
            and str(receipt.item_id or receipt.source_id)
        )
        if not any((coins, growth_units, inventory, environment_items)):
            continue

        if "full_bloom" in sources:
            kind = RewardHero.FULL_BLOOM
            category = "Full Bloom"
        elif sources.intersection({"garden_find_environment", "environment_discovery"}) or environment_items:
            kind = RewardHero.ENVIRONMENT_DISCOVERY
            category = "Environment discovery"
        elif "garden_find" in sources:
            kind = RewardHero.GARDEN_FIND
            category = "Garden Find"
        elif event_key in milestone_event_ids:
            # Numeric milestone values already live on the richer typed item.
            continue
        elif coins or inventory:
            kind = RewardHero.COIN_OR_BOOSTER
            category = "Garden reward"
        else:
            kind = RewardHero.ROUTINE_GROWTH
            category = "Growth earned"

        title = next((str(receipt.title) for receipt in group if receipt.title), "")
        if not title and environment_items:
            title = _environment_item_name(environment_items[0])
        if not title and inventory:
            title = _inventory_item_name(inventory[0][0])
        if not title:
            title = category
        artwork = environment_items[0] if environment_items else (
            inventory[0][0] if inventory else ""
        )
        detail = next(
            (str(receipt.description) for receipt in group if receipt.description),
            "",
        )
        embedded_coins += coins
        embedded_direct_growth_units += growth_units
        items.append(RewardItemProjection(
            event_id=event_key,
            kind=kind,
            title=title,
            category_label=category,
            occurred_at=max((receipt.occurred_at for receipt in group), default=event.occurred_at),
            growth_units=growth_units,
            garden_coins=coins,
            inventory_items=inventory,
            artwork_ref=artwork,
            detail=detail,
            sequence=len(items),
        ))

    # The live footer includes both the engine's base Coin total and positive
    # additional awards. Project the same canonical delta, then subtract only
    # values already rendered by richer milestone/Find/receipt items.
    coin_total = sum(
        max(0, int(award.amount))
        for award in event.coin_awards
    )
    standalone_coins = max(0, coin_total - embedded_coins)
    if standalone_coins:
        coin_title = (
            event.coin_awards[0].source_label
            if len(event.coin_awards) == 1 and event.coin_awards[0].source_label
            else "Garden Coins"
        )
        items.append(RewardItemProjection(
            event_id=f"{bundle_id}:coins",
            kind=RewardHero.COIN_OR_BOOSTER,
            title=coin_title,
            category_label="Garden Coin reward",
            occurred_at=event.occurred_at,
            garden_coins=standalone_coins,
            sequence=len(items),
        ))

    plant_growth_units = sum(
        max(0, int(delta.growth_units)) for delta in event.plant_growth
    )
    stored_added_units = max(0, int(event.stored_growth_delta_units))
    remaining_embedded_growth = embedded_direct_growth_units
    routine_plant_growth = max(0, plant_growth_units - remaining_embedded_growth)
    remaining_embedded_growth = max(0, remaining_embedded_growth - plant_growth_units)
    routine_stored_growth = max(0, stored_added_units - remaining_embedded_growth)
    shared_growth_units = sum(
        max(0, int(delta.growth_units)) for delta in event.shared_growth
    )
    for suffix, title, growth_units in (
        ("plant", "Growth earned", routine_plant_growth),
        ("shared", "Shared Growth", shared_growth_units),
        ("stored", "Stored Growth", routine_stored_growth),
    ):
        if not growth_units:
            continue
        items.append(RewardItemProjection(
            event_id=f"{bundle_id}:growth:{suffix}",
            kind=RewardHero.ROUTINE_GROWTH,
            title=title,
            category_label="Routine Growth",
            occurred_at=event.occurred_at,
            growth_units=growth_units,
            sequence=len(items),
        ))

    if not items:
        return None
    unique: list[RewardItemProjection] = []
    seen_ids: set[str] = set()
    for item in items:
        if item.event_id in seen_ids:
            continue
        seen_ids.add(item.event_id)
        unique.append(item)
    ordered = tuple(
        item
        for _index, item in sorted(
            enumerate(unique),
            key=_bundle_item_sort_key,
        )
    )
    return RewardBundleProjection(
        bundle_id,
        event.occurred_at,
        ordered,
        displayed_coin_delta=(
            coin_total
            if ordered[0].kind is RewardHero.FULL_BLOOM
            else None
        ),
    )


# Compact compatibility name for reviewer adapters.
project_reward_bundle = project_committed_reward_bundle


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
        # learner later changes the equipped Garden Feature or Scenery.
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
            title="First card today",
            trigger="Complete your first card today.",
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
            title="Today’s Cards",
            trigger="Complete today’s cards.",
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
    normalized = canonical_garden_feature_id(item_id)
    for catalog in ENVIRONMENT_CATALOG.values():
        item = catalog.get(normalized)
        if item is not None:
            return item.name
    return _identifier_name(normalized or "environment item")


def _environment_item_destination(item_id: str) -> str:
    """Name the exact collection category for an environment reward."""

    normalized = canonical_garden_feature_id(item_id)
    for kind, catalog in ENVIRONMENT_CATALOG.items():
        if normalized not in catalog:
            continue
        return "Garden Features" if kind == "garden_feature" else "Scenery"
    return "Collection"


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
    if outcome.pool_id == ENVIRONMENT_POOL_ID:
        # Pool versions define future rolls, not whether an already committed
        # discovery may still be shown. Preserve legacy environment outcomes
        # after the finite-pity pool upgrade.
        canonical_reward_id = canonical_garden_feature_id(reward_id)
        environment = next(
            (
                candidate
                for candidate in SPECIAL_ENVIRONMENT_POOL
                if candidate.item_id == canonical_reward_id
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
            description=(
                "Added to Garden Features"
                if environment.environment_kind == "garden_feature"
                else "Added to Scenery"
            ),
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
            description = RewardLine(
                "coins",
                max(0, int(outcome.amount)),
            ).learner_text
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
            unit = "Garden Coin" if self.reward_coins == 1 else "Garden Coins"
            parts.append(f"{self.reward_coins:,} {unit}")
        if self.reward_small_growth_charges:
            count = self.reward_small_growth_charges
            parts.append(
                f"{count} Small Growth {'Charge' if count == 1 else 'Charges'}"
            )
        if self.reward_standard_growth_charges:
            count = self.reward_standard_growth_charges
            parts.append(
                f"{count} Standard Growth {'Charge' if count == 1 else 'Charges'}"
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
                f"{answers:,} cards complete · {non_again_percent}% accuracy",
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
    "RewardBundleProjection",
    "RewardCompactProjection",
    "RewardCompactSummary",
    "RewardHero",
    "RewardItemProjection",
    "RewardLine",
    "RewardSummary",
    "achievement_presentation",
    "achievement_presentations",
    "lookup",
    "project_achievements",
    "project_committed_reward_bundle",
    "project_reward_bundle",
    "recent_garden_finds",
    "recent_reward_summaries",
    "recurring_reward_presentations",
    "reward_summary",
]
