from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Dict, Iterable, Optional, Tuple


HISTORY_FINGERPRINT_VERSION = 1


class AchievementCategory(str, Enum):
    CONSISTENCY = "consistency"
    STUDY_VOLUME = "study_volume"
    RECALL = "recall"
    COMPLETION = "completion"


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


@dataclass(frozen=True)
class RewardBundle:
    """The complete one-time payout attached to an achievement unlock."""

    coins: int = 0
    small_growth_charges: int = 0
    standard_growth_charges: int = 0

    def __post_init__(self) -> None:
        values = (
            self.coins,
            self.small_growth_charges,
            self.standard_growth_charges,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise TypeError("achievement reward amounts must be integers")
        if any(value < 0 for value in values):
            raise ValueError("achievement reward amounts cannot be negative")


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


ACHIEVEMENT_DEFINITIONS: Tuple[AchievementDefinition, ...] = (
    AchievementDefinition(
        "streak_7",
        "7-Day Anki Streak",
        "Reach a 7-day Anki streak.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        7,
        RewardBundle(coins=10),
    ),
    AchievementDefinition(
        "streak_30",
        "30-Day Anki Streak",
        "Reach a 30-day Anki streak.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        30,
        RewardBundle(coins=100, small_growth_charges=1),
    ),
    AchievementDefinition(
        "streak_100",
        "100-Day Anki Streak",
        "Reach a 100-day Anki streak.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        100,
        RewardBundle(coins=300),
    ),
    AchievementDefinition(
        "streak_365",
        "365-Day Anki Streak",
        "Reach a 365-day Anki streak.",
        AchievementCategory.CONSISTENCY,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.STREAK_DAYS,
        365,
        RewardBundle(coins=1_000),
    ),
    AchievementDefinition(
        "reviews_100_day",
        "Century Day",
        "Finish a day with 100 card answers.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.DAILY_ANSWERS,
        100,
        RewardBundle(coins=25),
        minimum_answers=100,
    ),
    AchievementDefinition(
        "reviews_1000_total",
        "Deep Roots",
        "Answer 1,000 cards.",
        AchievementCategory.STUDY_VOLUME,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.LIFETIME_ANSWERS,
        1_000,
        RewardBundle(standard_growth_charges=1),
    ),
    AchievementDefinition(
        "retention_90",
        "Clear Recall",
        "Finish a day with 20 card answers and at least 90% accuracy.",
        AchievementCategory.RECALL,
        AchievementEvaluationMode.FINALIZED_DAY,
        AchievementProgressMetric.DAILY_ANSWERS,
        20,
        RewardBundle(coins=10),
        minimum_answers=20,
        minimum_non_again_percent=90,
    ),
    AchievementDefinition(
        "retention_100",
        "Perfect Canopy",
        "Answer 30 cards in a row without Again.",
        AchievementCategory.RECALL,
        AchievementEvaluationMode.IMMEDIATE,
        AchievementProgressMetric.CONSECUTIVE_NON_AGAIN,
        30,
        RewardBundle(small_growth_charges=1),
    ),
    AchievementDefinition(
        "no_lapse",
        "No-Again Day",
        "Finish a day with 40 card answers and no Again answers.",
        AchievementCategory.RECALL,
        AchievementEvaluationMode.FINALIZED_DAY,
        AchievementProgressMetric.DAILY_ANSWERS,
        40,
        RewardBundle(coins=15),
        minimum_answers=40,
        minimum_non_again_percent=100,
    ),
    AchievementDefinition(
        "all_due_done",
        "All Clear",
        "Finish all due cards.",
        AchievementCategory.COMPLETION,
        AchievementEvaluationMode.LIVE_ONLY,
        AchievementProgressMetric.VALID_ALL_DUE_DAYS,
        1,
        RewardBundle(coins=5),
        historical_backfill=False,
    ),
)

ACHIEVEMENTS_BY_ID: Dict[str, AchievementDefinition] = {
    definition.achievement_id: definition
    for definition in ACHIEVEMENT_DEFINITIONS
}
STREAK_ACHIEVEMENTS: Tuple[AchievementDefinition, ...] = tuple(
    definition
    for definition in ACHIEVEMENT_DEFINITIONS
    if definition.progress_metric is AchievementProgressMetric.STREAK_DAYS
)


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

    ``current_open_day`` is deliberately not finalized for Clear Recall or
    No-Again Day. Immediate criteria may still unlock on events from that day.
    Ineligible events are ignored entirely, including for non-Again runs.
    """

    current_open_date = _parse_day(current_open_day, label="current_open_day")
    ordered = _ordered_eligible_reviews(
        reviews,
        current_open_date=current_open_date,
    )

    day_counts: Dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    unlock_candidates: Dict[str, str] = {}
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
            if non_again_run == 30:
                unlock_candidates.setdefault("retention_100", review.scheduler_day)
        if counts[0] == 100:
            unlock_candidates.setdefault("reviews_100_day", review.scheduler_day)
        if lifetime_index == 1_000:
            unlock_candidates.setdefault("reviews_1000_total", review.scheduler_day)

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
    for summary in daily_summaries:
        if summary.clear_recall_qualified:
            unlock_candidates.setdefault("retention_90", summary.scheduler_day)
        if summary.no_again_day_qualified:
            unlock_candidates.setdefault("no_lapse", summary.scheduler_day)

    active_dates = sorted(
        _parse_day(day_value, label="scheduler_day")
        for day_value in day_counts
    )
    maximum_streak_days = 0
    run_length = 0
    previous_day: Optional[date] = None
    streak_thresholds = {
        7: "streak_7",
        30: "streak_30",
        100: "streak_100",
        365: "streak_365",
    }
    for active_day in active_dates:
        if previous_day is not None and active_day == previous_day + timedelta(days=1):
            run_length += 1
        else:
            run_length = 1
        maximum_streak_days = max(maximum_streak_days, run_length)
        achievement_id = streak_thresholds.get(run_length)
        if achievement_id is not None:
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
