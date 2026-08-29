from __future__ import annotations

from datetime import date, timedelta

from ankigarden.achievements import (
    ACHIEVEMENT_DEFINITIONS,
    ACHIEVEMENTS_BY_ID,
    AchievementCategory,
    AchievementEvaluationMode,
    HistoricalReview,
    analyze_history,
)


def _review(event_id: int, day: date, rating: int = 3) -> HistoricalReview:
    return HistoricalReview(
        event_id=event_id,
        answered_at_ms=event_id,
        scheduler_day=day.isoformat(),
        rating=rating,
    )


def test_achievement_registry_is_the_exact_one_time_reward_contract() -> None:
    assert [item.achievement_id for item in ACHIEVEMENT_DEFINITIONS] == [
        "streak_7",
        "streak_30",
        "streak_100",
        "streak_365",
        "reviews_100_day",
        "reviews_1000_total",
        "all_due_done",
    ]
    rewards = {
        key: (
            definition.reward.coins,
            definition.reward.small_growth_charges,
            definition.reward.standard_growth_charges,
        )
        for key, definition in ACHIEVEMENTS_BY_ID.items()
    }
    assert rewards == {
        "streak_7": (10, 0, 0),
        "streak_30": (100, 1, 0),
        "streak_100": (300, 0, 0),
        "streak_365": (1_000, 0, 0),
        "reviews_100_day": (25, 0, 0),
        "reviews_1000_total": (0, 0, 1),
        "all_due_done": (5, 0, 0),
    }
    assert {"retention_90", "retention_100", "no_lapse"}.isdisjoint(
        ACHIEVEMENTS_BY_ID
    )
    assert (
        ACHIEVEMENTS_BY_ID["all_due_done"].evaluation_mode
        is AchievementEvaluationMode.LIVE_ONLY
    )
    assert not ACHIEVEMENTS_BY_ID["all_due_done"].historical_backfill
    assert ACHIEVEMENTS_BY_ID["all_due_done"].name == "Review Day Complete"
    assert ACHIEVEMENTS_BY_ID["all_due_done"].description == "Complete today's cards."


def test_history_analysis_is_order_independent_and_never_finalizes_the_open_day() -> None:
    start = date(2025, 1, 1)
    open_day = start + timedelta(days=364)
    reviews: list[HistoricalReview] = []
    event_id = 1
    for offset in range(365):
        day = start + timedelta(days=offset)
        answer_count = 100 if offset == 0 else 3
        for _ in range(answer_count):
            reviews.append(_review(event_id, day))
            event_id += 1
    # Neither an ineligible Again event nor an identical replay changes the
    # eligible history or its deterministic identity.
    reviews.append(HistoricalReview(event_id, event_id, open_day.isoformat(), 1, False))
    reviews.append(reviews[0])

    history = analyze_history(reversed(reviews), current_open_day=open_day.isoformat())
    expected_deep_roots_day = sorted(
        {item.event_id: item for item in reviews if item.eligible}.values(),
        key=lambda item: (item.answered_at_ms, item.event_id),
    )[999].scheduler_day

    assert history.lifetime_answers == 100 + 364 * 3
    assert history.maximum_streak_days == 365
    assert history.current_streak_days == 365
    assert history.studied_current_day
    assert history.current_non_again_tail == history.lifetime_answers
    assert history.maximum_non_again_run == history.lifetime_answers
    assert history.unlock_days == {
        "streak_7": (start + timedelta(days=6)).isoformat(),
        "streak_30": (start + timedelta(days=29)).isoformat(),
        "streak_100": (start + timedelta(days=99)).isoformat(),
        "streak_365": open_day.isoformat(),
        "reviews_100_day": start.isoformat(),
        "reviews_1000_total": expected_deep_roots_day,
    }
    assert "all_due_done" not in history.unlock_days
    assert history.day_summary(start.isoformat()).closed
    assert not history.day_summary(open_day.isoformat()).closed
    assert history.fingerprint == analyze_history(
        reviews,
        current_open_day=open_day.isoformat(),
    ).fingerprint

    open_day_only = [_review(index, open_day) for index in range(1, 41)]
    provisional = analyze_history(
        open_day_only,
        current_open_day=open_day.isoformat(),
    )
    assert {"retention_90", "retention_100", "no_lapse"}.isdisjoint(
        provisional.unlock_days
    )
