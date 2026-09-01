from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .balance_catalog import (
    ACHIEVEMENTS as CATALOG_ACHIEVEMENTS,
    AchievementDefinition as CatalogAchievementDefinition,
    RewardGrant as CatalogRewardGrant,
)


HISTORY_FINGERPRINT_VERSION = 1


class AchievementCategory(str, Enum):
    CONSISTENCY = "consistency"
    STUDY_VOLUME = "study_volume"
    RECALL = "recall"
    COMPLETION = "completion"
    PROGRESSION = "progression"
    COLLECTION = "collection"


class AchievementEvaluationMode(str, Enum):
    IMMEDIATE = "immediate"
    FINALIZED_DAY = "finalized_day"
    LIVE_ONLY = "live_only"


class AchievementProgressMetric(str, Enum):
    STREAK_DAYS = "streak_days"
    DAILY_ANSWERS = "daily_answers"
    LIFETIME_ANSWERS = "lifetime_answers"
    CONSECUTIVE_NON_AGAIN = "consecutive_non_again"
    VALID_ALL_DUE_DAYS = "valid_all_due_days"
    # The canonical persisted values stay compatible with the balance catalog.
    MATURE_SPECIES = "mature_plants"
    MATURE_PLANTS = "mature_plants"
    FULL_BLOOM_SPECIES = "unique_full_blooms"
    UNIQUE_FULL_BLOOMS = "unique_full_blooms"
    VALID_COMPLETIONS = "valid_completions"


@dataclass(frozen=True)
class RewardBundle:
    """The complete one-time payout attached to an achievement unlock."""

    coins: int = 0
    small_growth_charges: int = 0
    standard_growth_charges: int = 0
    grand_growth_charges: int = 0
    bed_unlocks: tuple[int, ...] = ()
    cosmetic_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.coins,
            self.small_growth_charges,
            self.standard_growth_charges,
            self.grand_growth_charges,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise TypeError("achievement reward amounts must be integers")
        if any(value < 0 for value in values):
            raise ValueError("achievement reward amounts cannot be negative")
        if not isinstance(self.bed_unlocks, tuple):
            raise TypeError("achievement bed unlocks must be an immutable tuple")
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value not in {3, 4, 5, 6}
            for value in self.bed_unlocks
        ):
            raise ValueError("achievement bed unlocks must be bed numbers 3 through 6")
        if len(self.bed_unlocks) != len(set(self.bed_unlocks)):
            raise ValueError("achievement bed unlocks cannot contain duplicates")
        if not isinstance(self.cosmetic_ids, tuple):
            raise TypeError("achievement cosmetic grants must be an immutable tuple")
        if any(
            not isinstance(value, str)
            or not value
            or value.strip() != value
            for value in self.cosmetic_ids
        ):
            raise ValueError("achievement cosmetic IDs must be nonempty strings")
        if len(self.cosmetic_ids) != len(set(self.cosmetic_ids)):
            raise ValueError("achievement cosmetic grants cannot contain duplicates")

    @property
    def inventory_items(self) -> Mapping[str, int]:
        """Return the inventory portion used by the reward ledger boundary."""

        return MappingProxyType({
            key: value
            for key, value in (
                ("growth_charge_small", self.small_growth_charges),
                ("growth_charge_standard", self.standard_growth_charges),
                ("growth_charge_grand", self.grand_growth_charges),
            )
            if value
        })


@dataclass(frozen=True)
class AchievementDefinition:
    achievement_id: str
    name: str
    description: str
    category: AchievementCategory
    evaluation_mode: AchievementEvaluationMode
    progress_metric: AchievementProgressMetric
    progress_target: int
    reward: RewardBundle
    historical_backfill: bool = True
    minimum_answers: int = 0
    minimum_non_again_percent: int = 0


def _bundle_from_catalog_grants(
    grants: tuple[CatalogRewardGrant, ...],
) -> RewardBundle:
    coins = 0
    small = 0
    standard = 0
    grand = 0
    beds: list[int] = []
    cosmetics: list[str] = []
    for grant in grants:
        kind = grant.kind.value
        if kind == "coins":
            coins += grant.amount
        elif kind == "consumable":
            if grant.item_id == "growth_charge_small":
                small += grant.amount
            elif grant.item_id == "growth_charge_standard":
                standard += grant.amount
            elif grant.item_id == "growth_charge_grand":
                grand += grant.amount
            else:
                raise ValueError(
                    f"unsupported achievement consumable grant: {grant.item_id}"
                )
        elif kind == "bed_unlock":
            prefix = "bed_"
            if not str(grant.item_id or "").startswith(prefix):
                raise ValueError("achievement bed grant requires a bed_N item ID")
            beds.extend([int(str(grant.item_id)[len(prefix):])] * grant.amount)
        elif kind == "cosmetic":
            cosmetics.extend([str(grant.item_id or "")] * grant.amount)
        else:
            raise ValueError(f"unsupported achievement reward kind: {kind}")
    return RewardBundle(
        coins=coins,
        small_growth_charges=small,
        standard_growth_charges=standard,
        grand_growth_charges=grand,
        bed_unlocks=tuple(beds),
        cosmetic_ids=tuple(cosmetics),
    )


def _definition_from_catalog(
    definition: CatalogAchievementDefinition,
) -> AchievementDefinition:
    return AchievementDefinition(
        achievement_id=definition.achievement_id.value,
        name=definition.display_name,
        description=definition.description,
        category=AchievementCategory(definition.category.value),
        evaluation_mode=AchievementEvaluationMode(definition.evaluation_mode.value),
        progress_metric=AchievementProgressMetric(definition.progress_metric.value),
        progress_target=definition.progress_target,
        reward=_bundle_from_catalog_grants(definition.rewards),
        historical_backfill=definition.historical_backfill,
        minimum_answers=definition.minimum_answers,
        minimum_non_again_percent=definition.minimum_non_again_percent,
    )


ACHIEVEMENT_DEFINITIONS: Tuple[AchievementDefinition, ...] = tuple(
    _definition_from_catalog(definition)
    for definition in CATALOG_ACHIEVEMENTS
)

ACHIEVEMENTS_BY_ID: Mapping[str, AchievementDefinition] = MappingProxyType({
    definition.achievement_id: definition
    for definition in ACHIEVEMENT_DEFINITIONS
})
STREAK_ACHIEVEMENTS: Tuple[AchievementDefinition, ...] = tuple(
    definition
    for definition in ACHIEVEMENT_DEFINITIONS
    if definition.progress_metric is AchievementProgressMetric.STREAK_DAYS
)
LIFETIME_ANSWER_ACHIEVEMENTS: Tuple[AchievementDefinition, ...] = tuple(
    definition
    for definition in ACHIEVEMENT_DEFINITIONS
    if definition.progress_metric is AchievementProgressMetric.LIFETIME_ANSWERS
)
VALID_COMPLETION_ACHIEVEMENTS: Tuple[AchievementDefinition, ...] = tuple(
    definition
    for definition in ACHIEVEMENT_DEFINITIONS
    if definition.progress_metric is AchievementProgressMetric.VALID_COMPLETIONS
)
FULL_BLOOM_ACHIEVEMENTS: Tuple[AchievementDefinition, ...] = tuple(
    definition
    for definition in ACHIEVEMENT_DEFINITIONS
    if definition.progress_metric is AchievementProgressMetric.FULL_BLOOM_SPECIES
)


@dataclass(frozen=True)
class AchievementProgressValues:
    """Runtime-owned counters projected onto the canonical metrics."""

    streak_days: int = 0
    daily_answers: int = 0
    lifetime_answers: int = 0
    consecutive_non_again: int = 0
    valid_all_due_days: int = 0
    mature_species: int = 0
    full_bloom_species: int = 0
    valid_completions: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field_name) for field_name in (
            "streak_days",
            "daily_answers",
            "lifetime_answers",
            "consecutive_non_again",
            "valid_all_due_days",
            "mature_species",
            "full_bloom_species",
            "valid_completions",
        ))
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise TypeError("achievement progress counters must be integers")
        if any(value < 0 for value in values):
            raise ValueError("achievement progress counters cannot be negative")


def achievement_progress_value(
    definition: AchievementDefinition,
    values: AchievementProgressValues,
) -> int:
    """Resolve one definition without duplicating metric dispatch in the engine."""

    if not isinstance(definition, AchievementDefinition):
        raise TypeError("definition must be an AchievementDefinition")
    if not isinstance(values, AchievementProgressValues):
        raise TypeError("values must be AchievementProgressValues")
    by_metric = {
        AchievementProgressMetric.STREAK_DAYS: values.streak_days,
        AchievementProgressMetric.DAILY_ANSWERS: values.daily_answers,
        AchievementProgressMetric.LIFETIME_ANSWERS: values.lifetime_answers,
        AchievementProgressMetric.CONSECUTIVE_NON_AGAIN: values.consecutive_non_again,
        AchievementProgressMetric.VALID_ALL_DUE_DAYS: values.valid_all_due_days,
        AchievementProgressMetric.MATURE_SPECIES: values.mature_species,
        AchievementProgressMetric.FULL_BLOOM_SPECIES: values.full_bloom_species,
        AchievementProgressMetric.VALID_COMPLETIONS: values.valid_completions,
    }
    return by_metric[definition.progress_metric]


@dataclass(frozen=True)
class HistoricalReview:
    """One stable Anki answer event prepared by the storage boundary."""

    event_id: int
    answered_at_ms: int
    scheduler_day: str
    rating: int
    eligible: bool = True


@dataclass(frozen=True)
class HistoricalDaySummary:
    scheduler_day: str
    total_answers: int
    non_again_answers: int
    again_answers: int
    closed: bool

    @property
    def accuracy(self) -> float:
        if self.total_answers <= 0:
            return 0.0
        return self.non_again_answers / self.total_answers

    @property
    def clear_recall_qualified(self) -> bool:
        return (
            self.closed
            and self.total_answers >= 20
            and self.non_again_answers * 10 >= self.total_answers * 9
        )

    @property
    def no_again_day_qualified(self) -> bool:
        return (
            self.closed
            and self.total_answers >= 40
            and self.again_answers == 0
        )


# Keep the concise domain name available to storage and engine integration.
HistoricalDay = HistoricalDaySummary


@dataclass(frozen=True)
class AchievementHistory:
    current_open_day: str
    lifetime_answers: int
    daily_summaries: Tuple[HistoricalDaySummary, ...]
    unlock_days: Dict[str, str]
    maximum_streak_days: int
    current_streak_days: int
    latest_active_day: str
    studied_current_day: bool
    current_non_again_tail: int
    maximum_non_again_run: int
    fingerprint: str

    def unlock_day(self, achievement_id: str) -> Optional[str]:
        return self.unlock_days.get(achievement_id)

    def day_summary(self, scheduler_day: str) -> Optional[HistoricalDaySummary]:
        return next(
            (
                summary
                for summary in self.daily_summaries
                if summary.scheduler_day == scheduler_day
            ),
            None,
        )


def _parse_day(value: str, *, label: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be an ISO calendar date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must use YYYY-MM-DD format")
    return parsed


def _ordered_eligible_reviews(
    reviews: Iterable[HistoricalReview],
    *,
    current_open_date: date,
) -> Tuple[HistoricalReview, ...]:
    by_event_id: Dict[int, HistoricalReview] = {}
    for review in reviews:
        if not isinstance(review, HistoricalReview):
            raise TypeError("achievement history requires HistoricalReview events")
        if not review.eligible:
            continue
        if isinstance(review.event_id, bool) or int(review.event_id) <= 0:
            raise ValueError("eligible history events require a positive event_id")
        if isinstance(review.answered_at_ms, bool) or int(review.answered_at_ms) < 0:
            raise ValueError("eligible history events require a nonnegative timestamp")
        if isinstance(review.rating, bool) or int(review.rating) not in {1, 2, 3, 4}:
            raise ValueError("eligible history event ratings must be 1 through 4")
        review_day = _parse_day(review.scheduler_day, label="scheduler_day")
        if review_day > current_open_date:
            raise ValueError("history events cannot belong to a future Anki day")
        normalized = HistoricalReview(
            event_id=int(review.event_id),
            answered_at_ms=int(review.answered_at_ms),
            scheduler_day=review.scheduler_day,
            rating=int(review.rating),
            eligible=True,
        )
        previous = by_event_id.get(normalized.event_id)
        if previous is not None and previous != normalized:
            raise ValueError(
                f"conflicting history rows share event_id {normalized.event_id}"
            )
        by_event_id[normalized.event_id] = normalized
    return tuple(sorted(
        by_event_id.values(),
        key=lambda review: (
            review.answered_at_ms,
            review.event_id,
            review.scheduler_day,
            review.rating,
        ),
    ))


def _history_fingerprint(
    reviews: Tuple[HistoricalReview, ...],
    *,
    current_open_day: str,
) -> str:
    payload = {
        "version": HISTORY_FINGERPRINT_VERSION,
        "current_open_day": current_open_day,
        "eligible_reviews": [
            [
                review.event_id,
                review.answered_at_ms,
                review.scheduler_day,
                review.rating,
            ]
            for review in reviews
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analyze_history(
    reviews: Iterable[HistoricalReview],
    *,
    current_open_day: str,
) -> AchievementHistory:
    """Derive reconstructable one-time achievements from eligible answers.

    ``current_open_day`` remains open. Ineligible events are ignored entirely.
    Rating history is retained for schema compatibility but never unlocks or
    advances an achievement; ordinary progression is rating-neutral.
    """

    current_open_date = _parse_day(current_open_day, label="current_open_day")
    ordered = _ordered_eligible_reviews(
        reviews,
        current_open_date=current_open_date,
    )

    day_counts: Dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    unlock_candidates: Dict[str, str] = {}
    daily_answer_thresholds: Dict[int, tuple[str, ...]] = {
        threshold: tuple(
            definition.achievement_id
            for definition in ACHIEVEMENT_DEFINITIONS
            if (
                definition.progress_metric is AchievementProgressMetric.DAILY_ANSWERS
                and definition.progress_target == threshold
                and definition.historical_backfill
            )
        )
        for threshold in {
            definition.progress_target
            for definition in ACHIEVEMENT_DEFINITIONS
            if definition.progress_metric is AchievementProgressMetric.DAILY_ANSWERS
        }
    }
    lifetime_answer_thresholds: Dict[int, tuple[str, ...]] = {
        threshold: tuple(
            definition.achievement_id
            for definition in LIFETIME_ANSWER_ACHIEVEMENTS
            if definition.progress_target == threshold
            and definition.historical_backfill
        )
        for threshold in {
            definition.progress_target
            for definition in LIFETIME_ANSWER_ACHIEVEMENTS
        }
    }
    non_again_run = 0
    maximum_non_again_run = 0
    for lifetime_index, review in enumerate(ordered, start=1):
        counts = day_counts[review.scheduler_day]
        counts[0] += 1
        if review.rating == 1:
            counts[2] += 1
            non_again_run = 0
        else:
            counts[1] += 1
            non_again_run += 1
            maximum_non_again_run = max(maximum_non_again_run, non_again_run)
        for achievement_id in daily_answer_thresholds.get(counts[0], ()):
            unlock_candidates.setdefault(achievement_id, review.scheduler_day)
        for achievement_id in lifetime_answer_thresholds.get(lifetime_index, ()):
            unlock_candidates.setdefault(achievement_id, review.scheduler_day)

    daily_summaries = tuple(
        HistoricalDaySummary(
            scheduler_day=day_value,
            total_answers=counts[0],
            non_again_answers=counts[1],
            again_answers=counts[2],
            closed=_parse_day(day_value, label="scheduler_day") < current_open_date,
        )
        for day_value, counts in sorted(day_counts.items())
    )
    active_dates = sorted(
        _parse_day(day_value, label="scheduler_day")
        for day_value in day_counts
    )
    maximum_streak_days = 0
    run_length = 0
    previous_day: Optional[date] = None
    streak_thresholds: Dict[int, tuple[str, ...]] = {
        threshold: tuple(
            definition.achievement_id
            for definition in STREAK_ACHIEVEMENTS
            if definition.progress_target == threshold
            and definition.historical_backfill
        )
        for threshold in {
            definition.progress_target
            for definition in STREAK_ACHIEVEMENTS
        }
    }
    for active_day in active_dates:
        if previous_day is not None and active_day == previous_day + timedelta(days=1):
            run_length += 1
        else:
            run_length = 1
        maximum_streak_days = max(maximum_streak_days, run_length)
        for achievement_id in streak_thresholds.get(run_length, ()):
            unlock_candidates.setdefault(achievement_id, active_day.isoformat())
        previous_day = active_day

    active_date_set = set(active_dates)
    studied_current_day = current_open_date in active_date_set
    cursor = (
        current_open_date
        if studied_current_day
        else current_open_date - timedelta(days=1)
    )
    current_streak_days = 0
    while cursor in active_date_set:
        current_streak_days += 1
        cursor -= timedelta(days=1)

    unlock_days = {
        definition.achievement_id: unlock_candidates[definition.achievement_id]
        for definition in ACHIEVEMENT_DEFINITIONS
        if (
            definition.historical_backfill
            and definition.achievement_id in unlock_candidates
        )
    }
    return AchievementHistory(
        current_open_day=current_open_day,
        lifetime_answers=len(ordered),
        daily_summaries=daily_summaries,
        unlock_days=unlock_days,
        maximum_streak_days=maximum_streak_days,
        current_streak_days=current_streak_days,
        latest_active_day=(active_dates[-1].isoformat() if active_dates else ""),
        studied_current_day=studied_current_day,
        current_non_again_tail=non_again_run,
        maximum_non_again_run=maximum_non_again_run,
        fingerprint=_history_fingerprint(
            ordered,
            current_open_day=current_open_day,
        ),
    )
