from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from ..display_telemetry import DISPLAY_TELEMETRY


def _to_decimal(value: Any, *, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def format_integer(value: Any) -> str:
    try:
        return f"{int(_to_decimal(value)):,}"
    except Exception as exc:
        DISPLAY_TELEMETRY.track_parsing_exception(route="shared.formatters", field="integer", exc=exc)
        return "N/A"


def format_decimal(value: Any, places: int = 2) -> str:
    try:
        quantizer = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
        rounded = _to_decimal(value).quantize(quantizer, rounding=ROUND_HALF_UP)
        return f"{rounded:,.{max(0, places)}f}"
    except Exception as exc:
        DISPLAY_TELEMETRY.track_parsing_exception(route="shared.formatters", field="decimal", exc=exc)
        return "N/A"


def format_percent(value: Any, places: int = 0) -> str:
    try:
        percent_value = _to_decimal(value) * Decimal("100")
        quantizer = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
        rounded = percent_value.quantize(quantizer, rounding=ROUND_HALF_UP)
        return f"{rounded:,.{max(0, places)}f}%"
    except Exception as exc:
        DISPLAY_TELEMETRY.track_parsing_exception(route="shared.formatters", field="percent", exc=exc)
        return "N/A"


def format_points(value: Any, label: str = "growth points") -> str:
    return f"{format_integer(value)} {label}"


def pluralize(count: Any, singular: str, plural: str | None = None) -> str:
    normalized = abs(int(_to_decimal(count)))
    if normalized == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


def format_status_label(value: str) -> str:
    return str(value).replace("_", " ").strip().title()


def _coerce_datetime(value: date | datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    parsed = datetime.fromisoformat(value)
    return parsed


def format_local_datetime(
    value: date | datetime | str,
    *,
    timezone_name: str,
    output_format: str = "%Y-%m-%d %H:%M %Z",
) -> str:
    dt = _coerce_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    target = dt.astimezone(ZoneInfo(timezone_name))
    return target.strftime(output_format)


def format_local_date(value: date | datetime | str, *, timezone_name: str) -> str:
    return format_local_datetime(value, timezone_name=timezone_name, output_format="%Y-%m-%d")
