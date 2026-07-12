from __future__ import annotations

from datetime import date

from ankigarden.ui.formatters import (
    format_decimal,
    format_integer,
    format_local_date,
    format_local_datetime,
    format_percent,
    format_points,
    format_status_label,
    pluralize,
)


def test_percent_and_decimal_rounding_boundaries() -> None:
    assert format_percent(0) == "0%"
    assert format_percent(-0.125, places=1) == "-12.5%"
    assert format_percent(0.99995, places=2) == "100.00%"
    assert format_percent(12345.6789, places=2) == "1,234,567.89%"
    assert format_decimal(999_999_999.995, places=2) == "1,000,000,000.00"


def test_points_and_integer_boundaries() -> None:
    assert format_integer(0) == "0"
    assert format_integer(1234567890) == "1,234,567,890"
    assert format_points(-42) == "-42 growth points"


def test_pluralization_and_status_labels() -> None:
    assert pluralize(1, "day") == "day"
    assert pluralize(0, "day") == "days"
    assert pluralize(-1, "achievement") == "achievement"
    assert pluralize(2, "cactus", "cacti") == "cacti"
    assert format_status_label("gentle_rain") == "Gentle Rain"
    assert format_status_label("  in_progress  ") == "In Progress"


def test_datetime_timezone_conversion_is_stable() -> None:
    iso_value = "2026-01-01T00:30:00+00:00"
    assert format_local_datetime(iso_value, timezone_name="America/Los_Angeles") == "2025-12-31 16:30 PST"
    assert format_local_datetime(iso_value, timezone_name="Asia/Tokyo") == "2026-01-01 09:30 JST"


def test_date_inputs_support_timezone_sensitive_rendering() -> None:
    assert format_local_date(date(2026, 4, 24), timezone_name="UTC") == "2026-04-24"
    assert format_local_date("2026-04-24T23:30:00+00:00", timezone_name="America/New_York") == "2026-04-24"
    assert format_local_date("2026-04-24T23:30:00+00:00", timezone_name="Asia/Tokyo") == "2026-04-25"
