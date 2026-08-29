from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from ankigarden.capture.fixtures import (
    CAPTURE_DATE,
    STREAK_MILESTONE_DATES,
    achievement_completion_schedule,
    validate_achievement_completion_schedule,
)


@pytest.mark.parametrize(
    ("achievement_id", "streak_days"),
    (
        ("streak_7", 7),
        ("streak_30", 30),
        ("streak_100", 100),
        ("streak_365", 365),
    ),
)
def test_streak_fixture_uses_one_plausible_365_day_run(
    achievement_id: str,
    streak_days: int,
) -> None:
    streak_start = date(2025, 8, 29)
    assert STREAK_MILESTONE_DATES[achievement_id] == (
        streak_start + timedelta(days=streak_days - 1)
    )
    assert STREAK_MILESTONE_DATES[achievement_id] <= CAPTURE_DATE


def test_capture_achievement_schedule_is_distinct_and_never_future_dated() -> None:
    ids = (
        "first_growth",
        "streak_7",
        "collector",
        "streak_30",
        "streak_100",
        "streak_365",
    )
    schedule = achievement_completion_schedule(ids)

    assert CAPTURE_DATE == date(2026, 8, 28)
    assert set(schedule) == set(ids)
    assert len(set(schedule.values())) == len(schedule)
    assert max(schedule.values()) == CAPTURE_DATE
    assert validate_achievement_completion_schedule(schedule)


def test_runtime_capture_fixture_uses_the_shared_frozen_schedule() -> None:
    runtime = (
        Path(__file__).resolve().parents[1]
        / "ankigarden"
        / "capture"
        / "runtime.py"
    ).read_text("utf-8")

    assert "achievement_completion_schedule(" in runtime
    assert "validate_achievement_completion_schedule(" in runtime
    assert "date(2026, 8, 28)" not in runtime
