from __future__ import annotations

from datetime import date, datetime

from ankigarden.ui.formatters import (
    GardenDateService,
    format_available,
    format_balance_after,
    format_balance_delta,
    format_decimal,
    format_duration,
    format_approximate_cards,
    format_garden_coins,
    format_growth,
    format_integer,
    format_inventory_delta,
    format_local_date,
    format_local_datetime,
    format_percent,
    format_points,
    format_quantity,
    format_status_label,
    format_streak,
    format_stage_progress,
    format_shortfall,
    pluralize,
)


class _SchedulerDayStorage:
    def __init__(self, scheduler_day: str) -> None:
        self._scheduler_day = scheduler_day

    def current_scheduler_day(self) -> str:
        return self._scheduler_day


def test_percent_and_decimal_rounding_boundaries() -> None:
    assert format_percent(0) == "0%"
    assert format_percent(-0.125, places=1) == "-12.5%"
    assert format_percent(0.99995, places=2) == "100.00%"
    assert format_percent(12345.6789, places=2) == "1,234,567.89%"
    assert format_decimal(999_999_999.995, places=2) == "1,000,000,000.00"


def test_points_and_integer_boundaries() -> None:
    assert format_integer(0) == "0"
    assert format_integer(1234567890) == "1,234,567,890"
    assert format_points(-42) == "-42 Growth"


def test_garden_release_formatters_have_one_stable_representation() -> None:
    assert format_garden_coins(1) == "1 Garden Coin"
    assert format_garden_coins(1_000_000) == "1,000,000 Garden Coins"
    assert format_garden_coins(-2, signed=True) == "-2 Garden Coins"
    assert format_growth(40) == "40 Growth"
    assert format_growth(40, 500) == "40 / 500 Growth"
    assert format_growth(40, signed=True) == "+40 Growth"
    assert format_inventory_delta(-1) == "-1"
    assert format_balance_delta(150, 119) == "150 → 119 Garden Coins"
    assert format_duration(0) == "0 minutes"
    assert format_duration(59) == "Under 1 minute"
    assert format_duration(9_060) == "2h 31m"
    assert format_streak(1) == "1 day"
    assert format_streak(7) == "7 days"
    assert (
        format_stage_progress(1_250, 2_000, "young")
        == "1,250 / 2,000 toward Young"
    )
    assert format_balance_after(4_850) == "Balance after: 4,850"
    assert format_available(2) == "2 available"
    assert format_shortfall(30) == "30 Garden Coins needed"


def test_pluralization_and_status_labels() -> None:
    assert pluralize(1, "day") == "day"
    assert pluralize(0, "day") == "days"
    assert pluralize(-1, "achievement") == "achievement"
    assert pluralize(2, "cactus", "cacti") == "cacti"
    assert format_status_label("gentle_rain") == "Gentle Rain"
    assert format_status_label("  in_progress  ") == "In Progress"
    assert format_status_label("rare") == "Full Bloom"


def test_shared_quantity_formatting_covers_cards_effects_and_finds() -> None:
    assert format_quantity(1, "card") == "1 card"
    assert format_quantity(14, "card") == "14 cards"
    assert format_quantity(1_000, "effect") == "1,000 effects"
    assert format_quantity(1, "Garden Find") == "1 Garden Find"
    assert format_quantity(2, "discovery", "discoveries") == "2 discoveries"
    assert format_approximate_cards(1) == "~1 card"
    assert format_approximate_cards(14) == "~14 cards"
    assert format_approximate_cards(-4) == "~0 cards"


def test_datetime_timezone_conversion_is_stable() -> None:
    iso_value = "2026-01-01T00:30:00+00:00"
    assert format_local_datetime(iso_value, timezone_name="America/Los_Angeles") == "2025-12-31 16:30 PST"
    assert format_local_datetime(iso_value, timezone_name="Asia/Tokyo") == "2026-01-01 09:30 JST"


def test_date_inputs_support_timezone_sensitive_rendering() -> None:
    assert format_local_date(date(2026, 4, 24), timezone_name="UTC") == "Apr 24, 2026"
    assert format_local_date("2026-04-24T23:30:00+00:00", timezone_name="America/New_York") == "Apr 24, 2026"
    assert format_local_date("2026-04-24T23:30:00+00:00", timezone_name="Asia/Tokyo") == "Apr 25, 2026"


def test_garden_date_service_uses_scheduler_day_for_grouping() -> None:
    service = GardenDateService(_SchedulerDayStorage("2026-08-25"))

    assert service.scheduler_day() == date(2026, 8, 25)
    assert service.format_date(
        "2026-08-26T04:30:00+00:00",
        scheduler_day="2026-08-25",
    ) == "Aug 25, 2026"


def test_garden_date_service_uses_compact_today_timestamp() -> None:
    local_now = datetime.now().astimezone().replace(
        hour=23,
        minute=25,
        second=0,
        microsecond=0,
    )
    service = GardenDateService(
        _SchedulerDayStorage(local_now.date().isoformat())
    )

    assert service.format_timestamp(
        local_now,
        scheduler_day=local_now.date().isoformat(),
    ) == "Today, 11:25 PM"
