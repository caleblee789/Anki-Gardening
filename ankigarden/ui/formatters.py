from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from ..display_telemetry import DISPLAY_TELEMETRY


@dataclass(frozen=True)
class GardenDateService:
    """Format Garden dates against Anki's active scheduler day.

    Event timestamps remain persisted as timezone-aware UTC values.  Their
    stored ``scheduler_day`` is the grouping authority; local time is only a
    presentation concern.
    """

    storage: Any | None = None

    def scheduler_day(self) -> date:
        resolver = getattr(self.storage, "current_scheduler_day", None)
        try:
            if callable(resolver):
                return date.fromisoformat(str(resolver())[:10])
        except (TypeError, ValueError):
            pass
        return datetime.now().astimezone().date()

    @staticmethod
    def _local_datetime(value: date | datetime | str | None) -> datetime:
        if value is None:
            return datetime.now().astimezone()
        parsed = _coerce_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone()

    @staticmethod
    def _display_date(value: date) -> str:
        return f"{value.strftime('%b')} {value.day}, {value.year}"

    def format_date(
        self,
        value: date | datetime | str,
        *,
        scheduler_day: str = "",
        include_year: bool = True,
    ) -> str:
        try:
            displayed = (
                date.fromisoformat(str(scheduler_day)[:10])
                if scheduler_day
                else self._local_datetime(value).date()
            )
        except (TypeError, ValueError):
            return str(value or "—")
        if include_year:
            return self._display_date(displayed)
        return f"{displayed.strftime('%b')} {displayed.day}"

    def format_timestamp(
        self,
        value: date | datetime | str | None = None,
        *,
        scheduler_day: str = "",
    ) -> str:
        try:
            local = self._local_datetime(value)
            event_day = (
                date.fromisoformat(str(scheduler_day)[:10])
                if scheduler_day
                else local.date()
            )
        except (TypeError, ValueError):
            return str(value or "—")
        time_text = local.strftime("%I:%M %p").lstrip("0")
        if event_day == self.scheduler_day():
            return f"Today, {time_text}"
        return f"{self._display_date(event_day)}, {time_text}"


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


def format_growth_fifths(value: Any) -> str:
    """Format exact fifths of one Growth point without using floating point."""
    try:
        numerator = max(0, int(_to_decimal(value)))
        whole, remainder = divmod(numerator, 5)
        if remainder == 0:
            return f"{whole:,}"
        return f"{whole:,}.{remainder * 2}"
    except Exception as exc:
        DISPLAY_TELEMETRY.track_parsing_exception(
            route="shared.formatters",
            field="growth_fifths",
            exc=exc,
        )
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


def format_points(value: Any, label: str = "Growth") -> str:
    return f"{format_integer(value)} {label}"


def _signed_integer(value: Any) -> str:
    number = int(_to_decimal(value))
    return f"{number:+,}"


def format_garden_coins(
    value: Any,
    *,
    include_unit: bool = True,
    signed: bool = False,
) -> str:
    """Format a Garden Coin value once for every renderer."""

    number = int(_to_decimal(value))
    amount = _signed_integer(number) if signed else f"{number:,}"
    if not include_unit:
        return amount
    unit = "Garden Coin" if abs(number) == 1 else "Garden Coins"
    return f"{amount} {unit}"


def format_growth(
    value: Any,
    maximum: Any | None = None,
    *,
    signed: bool = False,
    include_unit: bool = True,
) -> str:
    """Format one Growth value or one current/goal pair."""

    number = int(_to_decimal(value))
    amount = _signed_integer(number) if signed else f"{number:,}"
    if maximum is not None:
        amount = f"{amount} / {format_integer(maximum)}"
    return f"{amount} Growth" if include_unit else amount


def format_stage_progress(value: Any, maximum: Any, destination: str) -> str:
    """Format the one visible progress expression used by Garden surfaces."""

    return (
        f"{format_growth(value, maximum, include_unit=False)} Growth to "
        f"{format_status_label(destination)}"
    )


def format_growth_destination(destination: str) -> str:
    """Format the shared heading that names the next plant stage."""

    return f"Growth to {format_status_label(destination)}"


def format_growth_remaining(value: Any) -> str:
    """Format Growth still required inside the current stage."""

    return f"{format_integer(value)} Growth remaining"


def format_growth_unlock(value: Any) -> str:
    """Format a total-Growth unlock threshold."""

    return f"Unlocks at {format_integer(value)} total Growth"


def format_balance_after(value: Any) -> str:
    """Format the standard decision-relevant post-purchase balance."""

    return f"Balance after: {format_integer(value)}"


def format_available(value: Any) -> str:
    """Format a compact owned consumable count without inventory terminology."""

    return f"{format_integer(value)} available"


def format_shortfall(value: Any) -> str:
    """Format the compact Garden Coin shortfall used by commerce surfaces."""

    return f"{format_garden_coins(max(0, int(_to_decimal(value))))} needed"


def format_inventory_delta(value: Any) -> str:
    """Format an inventory change without inventing an item label."""

    return _signed_integer(value)


def format_balance_delta(current: Any, resulting: Any) -> str:
    """Pair current and resulting balances in one canonical value."""

    return (
        f"{format_garden_coins(current, include_unit=False)} → "
        f"{format_garden_coins(resulting)}"
    )


def format_duration(value: Any) -> str:
    """Format seconds as a compact, stable duration for UI status copy."""

    seconds = max(0, int(_to_decimal(value)))
    if seconds < 60:
        return "Under 1 minute" if seconds else "0 minutes"
    duration = timedelta(seconds=seconds)
    days = duration.days
    hours, remainder = divmod(duration.seconds, 3600)
    minutes = remainder // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and len(parts) < 2:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "Under 1 minute"


def format_stage(value: Any) -> str:
    return format_status_label(str(value or ""))


def format_streak(value: Any, *, signed: bool = False) -> str:
    days = int(_to_decimal(value))
    amount = _signed_integer(days) if signed else f"{days:,}"
    return f"{amount} {pluralize(days, 'day')}"


# The Home renderer's contract uses the names from the release brief. These
# aliases point at the same Python implementations and are not independent
# formatting paths.
formatGardenCoins = format_garden_coins
formatGrowth = format_growth
formatInventoryDelta = format_inventory_delta
formatBalanceDelta = format_balance_delta
formatDuration = format_duration
formatStage = format_stage
formatStreak = format_streak


def pluralize(count: Any, singular: str, plural: str | None = None) -> str:
    normalized = abs(int(_to_decimal(count)))
    if normalized == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


def format_quantity(
    count: Any,
    singular: str,
    plural: str | None = None,
) -> str:
    """Format one exact integer quantity with shared singular/plural copy."""

    normalized = int(_to_decimal(count))
    return f"{normalized:,} {pluralize(normalized, singular, plural)}"


def format_approximate_cards(count: Any) -> str:
    """Format an estimated card count without reintroducing answer copy."""

    normalized = max(0, int(_to_decimal(count)))
    return f"~{format_quantity(normalized, 'card')}"


def format_status_label(value: str) -> str:
    normalized = str(value).replace("_", " ").strip()
    if normalized.casefold() == "rare":
        return "Full Bloom"
    return normalized.title()


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
    rendered = format_local_datetime(value, timezone_name=timezone_name, output_format="%b %d, %Y")
    return rendered.replace(" 0", " ")
