"""Pure projections for the Garden reward surfaces.

The reward engine and :mod:`ankigarden.models.state` own the facts in these
projections.  This module only joins and groups those facts for a UI; it does
not mutate state, grant rewards, or make eligibility decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    standard_find_artwork_ref,
)
from .models.state import Achievement, GardenFindOutcome, GardenState, RewardReceipt
from .presentation import (
    GARDEN_DISCOVERY_INTERNAL_ID,
    STANDARD_FIND_INTERNAL_ID,
    visible_reward_term,
)
from .ui.economy_presenters import coin_reward_receipt
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


@dataclass(frozen=True)
class ProjectGrowthPresentation:
    """One exact committed project allocation joined to canonical UI facts."""

    target_type: str
    target_id: str
    units: int
    display_name: str
    artwork_id: str = ""
    status: str = ""
    progress: str = ""
    effect_description: str = ""
    acquisition_route: str = ""


def _growth_project_track(snapshot: Any, target_type: str, target_id: str) -> Any:
    """Resolve one public snapshot track without importing engine internals."""

    if snapshot is None:
        return None
    if target_type == "landmark":
        track = getattr(snapshot, "landmark_track", None)
    elif target_type == "mastery":
        resolver = getattr(snapshot, "mastery_track", None)
        if not callable(resolver):
            return None
        try:
            track = resolver(target_id)
        except (TypeError, ValueError):
            return None
    elif target_type == "legacy":
        track = getattr(snapshot, "legacy_track", None)
    else:
        return None
    target = getattr(track, "target", None)
    track_type = getattr(getattr(target, "target_type", ""), "value", None)
    if str(track_type or getattr(target, "target_type", "") or "") != target_type:
        return None
    if str(getattr(target, "target_id", "") or "") != target_id:
        return None
    return track


def _growth_project_status(snapshot: Any, track: Any) -> str:
    target = getattr(track, "target", None)
    active = target == getattr(snapshot, "active_target", None)
    tiers = tuple(getattr(track, "tiers", ()) or ())
    if any(bool(getattr(tier, "can_claim_now", False)) for tier in tiers):
        return (
            "Active project · Ready to claim"
            if active else "Ready to claim"
        )
    if any(bool(getattr(tier, "claimable", False)) for tier in tiers):
        funded = "Funded · Garden Coins needed to claim"
        return f"Active project · {funded}" if active else funded
    if active:
        return "Active project"
    remaining = getattr(track, "remaining_capacity_units", None)
    if remaining is not None and max(0, int(remaining or 0)) == 0:
        return "Fully funded"
    if "activate" in tuple(getattr(track, "allowed_actions", ()) or ()):
        return "Available project"
    return "Project progress"


def _growth_project_progress(track: Any) -> str:
    maximum = getattr(track, "maximum_growth_units", None)
    funded = max(0, int(getattr(track, "growth_units_funded", 0) or 0))
    if maximum is not None:
        return (
            f"{format_growth_units(funded)} / "
            f"{format_growth_units(max(0, int(maximum or 0)))} Growth"
        )
    level = max(0, int(getattr(track, "level", 0) or 0))
    progress = max(0, int(getattr(track, "level_progress_units", 0) or 0))
    return (
        f"Level {level:,} · {format_growth_units(progress)} Growth"
        if level or progress else "Level 0"
    )


def project_growth_allocations(
    allocations: Iterable[Any],
    snapshot: Any = None,
    *,
    landmark_growth_units: int = 0,
) -> tuple[ProjectGrowthPresentation, ...]:
    """Join typed committed credit to canonical project facts, exactly once.

    Input order is retained while duplicate target rows coalesce.  The legacy
    scalar can contribute only a Landmark shortfall; it never creates a
    Mastery species or Legacy identity.
    """

    totals: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for allocation in tuple(allocations or ()):
        raw_type = getattr(allocation, "target_type", "")
        target_type = str(getattr(raw_type, "value", raw_type) or "").casefold()
        target_id = str(getattr(allocation, "target_id", "") or "").strip()
        units = max(0, int(getattr(allocation, "units", 0) or 0))
        if target_type not in {"landmark", "mastery", "legacy"}:
            continue
        if not target_id or units <= 0:
            continue
        key = (target_type, target_id)
        if key not in totals:
            order.append(key)
            totals[key] = 0
        totals[key] += units

    typed_landmark_units = sum(
        units
        for (target_type, _target_id), units in totals.items()
        if target_type == "landmark"
    )
    landmark_residual = max(
        0,
        max(0, int(landmark_growth_units or 0)) - typed_landmark_units,
    )
    if landmark_residual:
        landmark_key = next(
            (key for key in order if key[0] == "landmark"),
            ("landmark", "garden_landmark"),
        )
        if landmark_key not in totals:
            order.append(landmark_key)
            totals[landmark_key] = 0
        totals[landmark_key] += landmark_residual

    result: list[ProjectGrowthPresentation] = []
    for target_type, target_id in order:
        track = _growth_project_track(snapshot, target_type, target_id)
        if track is None:
            display_name = {
                "landmark": "Garden Landmark",
                "mastery": "Cultivation Mastery",
                "legacy": "Garden Legacy",
            }[target_type]
            result.append(ProjectGrowthPresentation(
                target_type,
                target_id,
                totals[(target_type, target_id)],
                display_name,
                status="Committed project Growth",
            ))
            continue
        result.append(ProjectGrowthPresentation(
            target_type,
            target_id,
            totals[(target_type, target_id)],
            str(getattr(track, "display_name", "") or "Growth project"),
            artwork_id=str(getattr(track, "artwork_id", "") or ""),
            status=_growth_project_status(snapshot, track),
            progress=_growth_project_progress(track),
            effect_description=str(
                getattr(track, "effect_description", "") or ""
            ),
            acquisition_route=str(
                getattr(track, "acquisition_route", "") or ""
            ),
        ))
    return tuple(result)


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
    is_routine: bool = False

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
        object.__setattr__(self, "is_routine", bool(self.is_routine))
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
        return self.kind is RewardHero.ROUTINE_GROWTH or self.is_routine

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
    artwork_ref: str = ""
    reward_type: str = ""
    rarity: str = ""
    artwork_refs: tuple[str, ...] = ()

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
        artwork_ref = str(self.artwork_ref or "").strip()
        artwork_refs = tuple(dict.fromkeys(
            str(candidate or "").strip()
            for candidate in self.artwork_refs
            if str(candidate or "").strip()
        ))
        if artwork_ref:
            artwork_refs = tuple(dict.fromkeys((artwork_ref, *artwork_refs)))
        elif artwork_refs:
            artwork_ref = artwork_refs[0]
        object.__setattr__(self, "artwork_ref", artwork_ref)
        object.__setattr__(self, "artwork_refs", artwork_refs)
        object.__setattr__(
            self,
            "reward_type",
            str(self.reward_type or "").strip().casefold(),
        )
        object.__setattr__(self, "rarity", str(self.rarity or "").strip().casefold())

    @property
    def semantic_type(self) -> str:
        """Compatibility-friendly name for icon and color selection."""

        return self.reward_type

    @property
    def art_assets(self) -> tuple[str, ...]:
        """Return every exact artwork source represented by the summary."""

        return self.artwork_refs


@dataclass(frozen=True)
class RewardDetailRow:
    """One render-ready detail row backed by exact atomic reward events."""

    category_label: str
    name: str
    value: str
    event_ids: tuple[str, ...]
    artwork_ref: str = ""

    def __post_init__(self) -> None:
        category_label = str(self.category_label or "").strip()
        name = str(self.name or "").strip()
        value = str(self.value or "").strip()
        event_ids = tuple(dict.fromkeys(
            str(event_id or "").strip()
            for event_id in self.event_ids
            if str(event_id or "").strip()
        ))
        if not category_label:
            raise ValueError("reward detail category_label must not be empty")
        if not name:
            raise ValueError("reward detail name must not be empty")
        if not value:
            raise ValueError("reward detail value must not be empty")
        if not event_ids:
            raise ValueError("reward detail row must reference an event")
        object.__setattr__(self, "category_label", category_label)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "event_ids", event_ids)
        object.__setattr__(
            self,
            "artwork_ref",
            str(self.artwork_ref or "").strip(),
        )

    @property
    def category(self) -> str:
        """Compatibility-friendly short name for category renderers."""

        return self.category_label

    @property
    def art_asset(self) -> str:
        """Compatibility-friendly art name shared by reward renderers."""

        return self.artwork_ref


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
    def detail_rows(self) -> tuple[RewardDetailRow, ...]:
        """Return render-ready rows without asking the widget to parse copy."""

        return project_reward_detail_rows(self.all_items)

    @property
    def detail_expansion_available(self) -> bool:
        """Return whether expanding reveals meaningful structured detail."""

        if len(self.detail_rows) > 1:
            return True
        hero = self.hero
        if str(hero.detail or "").strip():
            return True
        return bool(
            hero.kind is RewardHero.FULL_BLOOM
            and (hero.plant_name or hero.plant_class)
        )

    @property
    def has_detail_expansion(self) -> bool:
        """Concise compatibility name for detail-expansion consumers."""

        return self.detail_expansion_available

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
    RewardHero.STAGE_CHANGE: "NEW GROWTH STAGE",
    RewardHero.ENVIRONMENT_DISCOVERY: "NEW DISCOVERY",
    RewardHero.GARDEN_FIND: "STANDARD FIND",
    RewardHero.CHECKPOINT: "CHECKPOINT REACHED",
    RewardHero.COIN_OR_BOOSTER: "REWARD EARNED",
    RewardHero.ROUTINE_GROWTH: "GROWTH APPLIED",
}

# First-card and similarly small incidental Coin grants update the header and
# session accumulator without opening a major reward reveal. Four Coins is the
# largest routine grant currently used by reviewer reward paths; named
# milestones remain major regardless of amount.
_MAX_ROUTINE_COIN_ONLY_AMOUNT = 4

# A compact reveal has room for only two secondary facts. Collectibles and
# named discoveries therefore outrank resource totals that are already visible
# in the progress animation and Session footer. Values are intentionally spaced
# so future semantic types can be inserted without changing existing ordering.
_SECONDARY_REWARD_PRIORITY = {
    "garden_find": 100,
    "customization_unlock": 95,
    "environment_discovery": 90,
    "checkpoint": 80,
    "booster": 70,
    "fertilizer": 65,
    "coins": 50,
    "growth": 10,
    "other": 0,
}

_MAJOR_COIN_SOURCE_MARKERS = (
    "achievement",
    "all_due",
    "checkpoint",
    "completion",
    "full_bloom",
    "garden_find",
    "milestone",
    "stage",
    "streak",
    "today_cards",
)

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
) -> tuple[int, int, int, int, str]:
    index, item = pair
    # One answer may cross multiple stages. The highest ordinary stage becomes
    # the hero while every atomic transition remains available to history.
    stage_rank = (
        -_STAGE_SORT_ORDER.get(item.new_stage, -1)
        if item.kind is RewardHero.STAGE_CHANGE
        else 0
    )
    return (
        1 if item.routine else 0,
        item.kind.priority,
        stage_rank,
        index,
        item.event_id,
    )


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


def _same_stage_change_plant(
    hero: RewardItemProjection,
    candidate: RewardItemProjection,
) -> bool:
    """Return whether two ordinary stage events belong to one plant."""

    if candidate.kind is not RewardHero.STAGE_CHANGE:
        return False
    if hero.plant_id and candidate.plant_id:
        return hero.plant_id == candidate.plant_id
    hero_name = str(hero.plant_name or hero.title).strip().casefold()
    candidate_name = str(candidate.plant_name or candidate.title).strip().casefold()
    return bool(hero_name and candidate_name and hero_name == candidate_name)


def _stage_advance_count(
    bundle: RewardBundleProjection,
    hero: RewardItemProjection,
) -> int:
    """Count compacted stage crossings without discarding atomic history."""

    atomic_count = sum(
        1
        for item in bundle.all_items
        if item.kind is RewardHero.STAGE_CHANGE
        and _same_stage_change_plant(hero, item)
    )
    path_count = max(0, len(tuple(hero.stage_path)) - 1)
    return max(1, atomic_count, path_count)


def _next_checkpoint_context(percent: int) -> str:
    """Return the next standard checkpoint after a committed milestone."""

    current = max(0, int(percent))
    next_percent = next(
        (candidate for candidate in (25, 50, 75, 100) if candidate > current),
        0,
    )
    return f"Next checkpoint at {next_percent}%" if next_percent else ""


def _coin_source_is_major(*values: object) -> bool:
    """Recognize milestone-backed Coin sources without parsing reward copy."""

    normalized = " ".join(
        str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
        for value in values
        if str(value or "").strip()
    )
    return any(marker in normalized for marker in _MAJOR_COIN_SOURCE_MARKERS)


def _ordinary_coin_total(awards: Iterable[Any]) -> int:
    """Return engine-confirmed Coins not identified as a named milestone."""

    return sum(
        max(0, int(getattr(award, "amount", 0) or 0))
        for award in awards
        if not _coin_source_is_major(
            getattr(award, "source_type", ""),
            getattr(award, "source_label", ""),
            getattr(award, "event_key", ""),
            getattr(award, "source_id", ""),
        )
    )


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


def _inventory_reward_type(item: RewardItemProjection) -> str:
    """Return the semantic priority family for an inventory-backed reward."""

    item_ids = " ".join(
        str(item_id or "").strip().casefold()
        for item_id, _quantity in item.inventory_items
    )
    if "booster" in item_ids:
        return "booster"
    if "fertilizer" in item_ids:
        return "fertilizer"
    return "customization_unlock"


def _compact_artwork_refs(
    items: Iterable[RewardItemProjection],
) -> tuple[str, ...]:
    """Preserve every exact artwork reference in stable event order."""

    return tuple(dict.fromkeys(
        str(item.artwork_ref or "").strip()
        for item in items
        if str(item.artwork_ref or "").strip()
    ))


def _compact_rarity(items: Iterable[RewardItemProjection]) -> str:
    """Choose the first engine-provided rarity using stable event order."""

    return next(
        (
            str(item.rarity or "").strip().casefold()
            for item in items
            if str(item.rarity or "").strip()
        ),
        "",
    )


def _compact_summary(
    *,
    key: str,
    label: str,
    items: Iterable[RewardItemProjection],
    reward_type: str,
    artwork_ref: str = "",
) -> RewardCompactSummary:
    """Build one semantic summary while retaining every atomic event ID."""

    typed_items = tuple(items)
    artwork_refs = _compact_artwork_refs(typed_items)
    primary_artwork = str(artwork_ref or "").strip() or (
        artwork_refs[0] if artwork_refs else ""
    )
    return RewardCompactSummary(
        key=key,
        label=label,
        event_ids=tuple(item.event_id for item in typed_items),
        artwork_ref=primary_artwork,
        reward_type=reward_type,
        rarity=_compact_rarity(typed_items),
        artwork_refs=artwork_refs,
    )


def _compact_summary_sort_key(
    entry: tuple[int, RewardCompactSummary],
) -> tuple[int, int, str, str]:
    """Rank summaries deterministically without depending on rerender order."""

    sequence, summary = entry
    return (
        -_SECONDARY_REWARD_PRIORITY.get(summary.reward_type, 0),
        max(0, int(sequence)),
        summary.event_ids[0],
        summary.key,
    )


def _reward_detail_value(item: RewardItemProjection) -> str:
    """Format exact typed facts for one expandable reward-detail row."""

    values: list[str] = []

    detail = str(item.detail or "").strip()
    if detail:
        values.append(detail)
    elif item.kind is RewardHero.FULL_BLOOM:
        values.append("Reached Full Bloom")
    elif item.kind is RewardHero.STAGE_CHANGE and item.new_stage:
        values.append(f"Reached {_stage_label(item.new_stage)}")
    elif item.kind is RewardHero.CHECKPOINT and item.checkpoint_percent:
        values.append(
            f"{item.checkpoint_percent:,}% toward "
            f"{_stage_label(item.new_stage)}"
        )

    if item.growth_units:
        values.append(
            f"{format_growth_units(item.growth_units, signed=True)} Growth"
        )
    if item.garden_coins:
        values.append(
            f"+{format_quantity(item.garden_coins, 'Garden Coin', 'Garden Coins')}"
        )
    values.extend(item.learner_inventory_labels)

    unique_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.casefold()
        if not value or normalized in seen_values:
            continue
        seen_values.add(normalized)
        unique_values.append(value)
    unique = tuple(unique_values)
    if unique:
        return " · ".join(unique)
    if item.kind is RewardHero.ENVIRONMENT_DISCOVERY:
        return "New discovery"
    return item.category_label


def project_reward_detail_rows(
    items: Iterable[RewardItemProjection],
) -> tuple[RewardDetailRow, ...]:
    """Project atomic bundle items into stable, structured display rows."""

    typed_items = tuple(items)
    if not all(isinstance(item, RewardItemProjection) for item in typed_items):
        raise TypeError("reward detail rows require RewardItemProjection values")
    return tuple(
        RewardDetailRow(
            category_label=item.category_label,
            name=item.title,
            value=_reward_detail_value(item),
            event_ids=(item.event_id,),
            artwork_ref=item.artwork_ref,
        )
        for item in typed_items
    )


def _session_history_row(item: RewardItemProjection) -> RewardDetailRow:
    """Project one meaningful atomic item with concise event-specific copy."""

    category = item.category_label
    name = item.title
    value = _reward_detail_value(item)

    if item.kind is RewardHero.FULL_BLOOM:
        category = "Milestone"
        name = "Full Bloom achieved"
        values = tuple(value for value in (
            str(item.plant_name or item.title).strip(),
            (
                f"+{format_quantity(item.garden_coins, 'Garden Coin', 'Garden Coins')}"
                if item.garden_coins
                else ""
            ),
        ) if value)
        value = " · ".join(values) or "Milestone reached"
    elif item.kind is RewardHero.STAGE_CHANGE:
        category = "Growth stage"
        name = f"{_stage_label(item.new_stage)} reached"
    elif item.kind is RewardHero.CHECKPOINT:
        category = "Checkpoint reward"
        name = (
            f"{item.checkpoint_percent:,}% checkpoint"
            if item.checkpoint_percent
            else "Checkpoint reached"
        )
    elif item.kind is RewardHero.GARDEN_FIND:
        category = "Standard Find"
    elif item.kind is RewardHero.ENVIRONMENT_DISCOVERY:
        category = "Discovery"

    return RewardDetailRow(
        category_label=category,
        name=name,
        value=value,
        event_ids=(item.event_id,),
        artwork_ref=item.artwork_ref,
    )


def project_reward_session_history(
    bundles: Iterable[RewardBundleProjection],
) -> tuple[RewardDetailRow, ...]:
    """Return named history rows with routine Growth aggregated once.

    Bundles and their immutable ledger-backed items remain untouched. Duplicate
    bundle or event identities are ignored at this presentation boundary so a
    remount cannot create duplicate history copy. Meaningful reward rows retain
    their original order; the session-level routine Growth aggregate is last.
    """

    typed_bundles = tuple(bundles)
    if not all(isinstance(bundle, RewardBundleProjection) for bundle in typed_bundles):
        raise TypeError("reward session history requires RewardBundleProjection values")

    rows: list[RewardDetailRow] = []
    routine_growth_units = 0
    routine_growth_event_ids: list[str] = []
    seen_bundle_ids: set[str] = set()
    seen_event_ids: set[str] = set()
    for bundle in typed_bundles:
        if bundle.bundle_id in seen_bundle_ids:
            continue
        seen_bundle_ids.add(bundle.bundle_id)
        for item in bundle.all_items:
            if item.event_id in seen_event_ids:
                continue
            seen_event_ids.add(item.event_id)
            if item.kind is RewardHero.ROUTINE_GROWTH:
                routine_growth_units += item.growth_units
                routine_growth_event_ids.append(item.event_id)
                continue
            rows.append(_session_history_row(item))

    if routine_growth_event_ids:
        rows.append(RewardDetailRow(
            category_label="Routine Growth",
            name="Growth applied",
            value=(
                f"{format_growth_units(routine_growth_units, signed=True)} Growth"
            ),
            event_ids=tuple(routine_growth_event_ids),
        ))
    return tuple(rows)


def _project_compact_reward(
    bundle: RewardBundleProjection,
) -> RewardCompactProjection:
    """Map atomic reward events to a deterministic two-chip dock projection."""

    hero = bundle.hero
    if hero.kind is RewardHero.FULL_BLOOM:
        hero_title = "Full Bloom achieved"
        hero_subtitle = hero.plant_name or hero.title
    elif hero.kind is RewardHero.STAGE_CHANGE:
        hero_title = f"{_stage_label(hero.new_stage)} reached"
        stages_advanced = _stage_advance_count(bundle, hero)
        hero_subtitle = (
            f"Advanced {stages_advanced:,} stages"
            if stages_advanced > 1
            else ""
        )
    elif hero.kind is RewardHero.CHECKPOINT:
        hero_title = (
            f"{hero.checkpoint_percent:,}% checkpoint"
            if hero.checkpoint_percent
            else "Checkpoint reached"
        )
        hero_subtitle = _next_checkpoint_context(hero.checkpoint_percent)
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
        if not (
            hero.kind is RewardHero.STAGE_CHANGE
            and _same_stage_change_plant(hero, item)
        )
    )

    grouped: dict[str, list[RewardItemProjection]] = {
        "garden_find": [],
        "environment_discovery": [],
        "coins": [],
        "growth": [],
    }
    ranked_summaries: list[tuple[int, RewardCompactSummary]] = []

    for item in candidates:
        # Semantic event identity wins over an attached payout. A Garden Find
        # that grants Growth is still a Find in the scarce compact reveal; its
        # Growth remains exact in details and the cumulative Session footer.
        if item.kind is RewardHero.GARDEN_FIND:
            grouped["garden_find"].append(item)
            continue
        if item.kind is RewardHero.ENVIRONMENT_DISCOVERY:
            grouped["environment_discovery"].append(item)
            continue
        if item.kind is RewardHero.CHECKPOINT:
            ranked_summaries.append((item.sequence, _compact_summary(
                key=f"checkpoint:{item.event_id}",
                label="Checkpoint reached",
                items=(item,),
                reward_type="checkpoint",
            )))
            continue
        if item.inventory_items:
            reward_type = _inventory_reward_type(item)
            ranked_summaries.append((item.sequence, _compact_summary(
                key=f"inventory:{item.event_id}",
                label=_inventory_compact_label(item),
                items=(item,),
                reward_type=reward_type,
                artwork_ref=str(item.inventory_items[0][0] or ""),
            )))
            continue
        if item.kind is RewardHero.STAGE_CHANGE:
            ranked_summaries.append((item.sequence, _compact_summary(
                key=f"stage:{item.event_id}",
                label=item.detail or "Stage advanced",
                items=(item,),
                reward_type="other",
            )))
            continue
        if item.garden_coins:
            grouped["coins"].append(item)
            continue
        if item.growth_units:
            grouped["growth"].append(item)
            continue
        ranked_summaries.append((item.sequence, _compact_summary(
            key=f"reward:{item.event_id}",
            label=item.detail or item.title,
            items=(item,),
            reward_type="other",
        )))

    find_items = tuple(grouped["garden_find"])
    if find_items:
        ranked_summaries.append((min(item.sequence for item in find_items), _compact_summary(
            key="garden_finds",
            label=visible_reward_term(STANDARD_FIND_INTERNAL_ID).label(
                len(find_items),
                include_quantity=True,
            ),
            items=find_items,
            reward_type="garden_find",
        )))

    discovery_items = tuple(grouped["environment_discovery"])
    if discovery_items:
        discovery_label = (
            discovery_items[0].title
            if len(discovery_items) == 1
            else visible_reward_term(GARDEN_DISCOVERY_INTERNAL_ID).label(
                len(discovery_items),
                include_quantity=True,
            )
        )
        ranked_summaries.append((
            min(item.sequence for item in discovery_items),
            _compact_summary(
                key="discoveries",
                label=discovery_label,
                items=discovery_items,
                reward_type="environment_discovery",
            ),
        ))

    coin_items = tuple(grouped["coins"])
    if coin_items:
        coin_total = sum(item.garden_coins for item in coin_items)
        ranked_summaries.append((min(item.sequence for item in coin_items), _compact_summary(
            key="coins",
            label=f"+{format_quantity(coin_total, 'Garden Coin', 'Garden Coins')}",
            items=coin_items,
            reward_type="coins",
        )))

    growth_items = tuple(grouped["growth"])
    if growth_items:
        growth_units = sum(item.growth_units for item in growth_items)
        ranked_summaries.append((min(item.sequence for item in growth_items), _compact_summary(
            key="growth",
            label=f"+{format_growth_units(growth_units)} growth",
            items=growth_items,
            reward_type="growth",
        )))

    summaries = tuple(
        summary
        for _sequence, summary in sorted(
            ranked_summaries,
            key=_compact_summary_sort_key,
        )
    )

    visible = tuple(summaries[:2])
    hidden = tuple(summaries[2:])
    hidden_event_count = len({
        event_id
        for summary in hidden
        for event_id in summary.event_ids
    })
    more_label = (
        "Details ›"
        if bundle.detail_expansion_available
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
    feature_if_only_major_ids: set[str] = set()
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
            title=find.find_name or "Standard Find",
            category_label="Standard Find",
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
                title=find.find_name or "Standard Find",
                category_label="Standard Find",
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
            title="Standard Find",
            category_label="Standard Find",
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
            title=discovery.environment_name or "Garden discovery",
            category_label="Garden discovery",
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

        coin_presentation = None
        if coins:
            candidates = tuple(dict.fromkeys((
                *(str(receipt.source or "") for receipt in group),
                *(str(receipt.source_id or "") for receipt in group),
            )))
            for candidate in candidates:
                if not candidate:
                    continue
                projected = coin_reward_receipt(candidate, coins)
                if projected.source_id == candidate:
                    coin_presentation = projected
                    break

        if "full_bloom" in sources:
            kind = RewardHero.FULL_BLOOM
            category = "Full Bloom"
        elif sources.intersection({"garden_find_environment", "environment_discovery"}) or environment_items:
            kind = RewardHero.ENVIRONMENT_DISCOVERY
            category = "Garden discovery"
        elif "garden_find" in sources:
            kind = RewardHero.GARDEN_FIND
            category = "Standard Find"
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
        if not title and coin_presentation is not None:
            title = coin_presentation.title
        if not title and environment_items:
            title = _environment_item_name(environment_items[0])
        if not title and inventory:
            title = _inventory_item_name(inventory[0][0])
        if not title:
            title = category
        artwork = environment_items[0] if environment_items else (
            inventory[0][0] if inventory else
            coin_presentation.artwork_id if coin_presentation is not None else ""
        )
        detail = next(
            (str(receipt.description) for receipt in group if receipt.description),
            "",
        )
        if not detail and coin_presentation is not None:
            detail = coin_presentation.detail
        routine_coin_only = bool(
            coins
            and not growth_units
            and not inventory
            and not environment_items
            and coins <= _MAX_ROUTINE_COIN_ONLY_AMOUNT
            and not _coin_source_is_major(event_key, *sources)
        )
        embedded_coins += coins
        embedded_direct_growth_units += growth_units
        feature_if_only_major = bool(
            coin_presentation is not None
            and coin_presentation.summary_policy
            == "detail_row_feature_if_only_major"
        )
        if feature_if_only_major:
            feature_if_only_major_ids.add(event_key)
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
            is_routine=routine_coin_only or feature_if_only_major,
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
            is_routine=(
                standalone_coins <= _MAX_ROUTINE_COIN_ONLY_AMOUNT
                and _ordinary_coin_total(event.coin_awards) >= standalone_coins
            ),
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

    if feature_if_only_major_ids and not any(
        not item.routine and item.event_id not in feature_if_only_major_ids
        for item in items
    ):
        items = [
            replace(item, is_routine=False)
            if item.event_id in feature_if_only_major_ids else item
            for item in items
        ]

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
        # learner later changes the equipped Garden Decoration or Scenery.
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
    return _identifier_name(normalized or "garden discovery")


def _environment_item_destination(item_id: str) -> str:
    """Name the exact collection category for an environment reward."""

    normalized = canonical_garden_feature_id(item_id)
    for kind, catalog in ENVIRONMENT_CATALOG.items():
        if normalized not in catalog:
            continue
        return "Garden decorations" if kind == "garden_feature" else "Scenery"
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
            artwork_ref=standard_find_artwork_ref(
                reward_id,
                outcome.artwork_ref,
            ),
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
                "Added to Garden decorations"
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
    "ProjectGrowthPresentation",
    "RecurringRewardPresentation",
    "RewardBundleProjection",
    "RewardCompactProjection",
    "RewardCompactSummary",
    "RewardDetailRow",
    "RewardHero",
    "RewardItemProjection",
    "RewardLine",
    "RewardSummary",
    "achievement_presentation",
    "achievement_presentations",
    "lookup",
    "project_achievements",
    "project_committed_reward_bundle",
    "project_growth_allocations",
    "project_reward_detail_rows",
    "project_reward_session_history",
    "project_reward_bundle",
    "recent_garden_finds",
    "recent_reward_summaries",
    "recurring_reward_presentations",
    "reward_summary",
]
