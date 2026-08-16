"""Content-measured responsive layout policy for native Garden surfaces.

The helpers in this module deliberately do not import Qt.  Native callers can
provide widgets, layouts, and Qt direction values through the small duck-typed
adapters below, while contract tests can exercise every threshold without a
live Anki runtime.

Changing a layout direction preserves the existing widgets, QObject parentage,
reading order, and tab chain.  This module never removes or reinserts children.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any, Callable, Iterable, Literal, Sequence, Union


RESPONSIVE_WIDTH_RESERVE = 24
COMPACT_MODE = "compact"
WIDE_MODE = "wide"

ResponsiveMode = Literal["compact", "wide"]
WidthValue = Union[int, float]
WidthProvider = Callable[[], WidthValue]
ModeApplier = Callable[[ResponsiveMode], None]
TelemetryObserver = Callable[["AdaptiveLayoutTelemetry"], None]


def _pixel_width(value: WidthValue, *, label: str) -> int:
    """Return a deterministic integral logical-pixel width.

    Fractional high-DPI measurements round up so a row never switches to its
    wide mode one logical pixel before all measured content fits.
    """

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not isfinite(numeric):
        raise ValueError(f"{label} must be a finite number")
    return max(0, int(ceil(numeric)))


def stable_threshold(
    minimum_widths: Iterable[WidthValue],
    *,
    spacing: WidthValue = 0,
) -> int:
    """Return the first width where all regions fit in one row.

    The shared 24 px reserve absorbs borders, rounding, and the small amount of
    breathing room needed to avoid a fragile edge-to-edge breakpoint.
    """

    widths = tuple(
        _pixel_width(value, label="region minimum width")
        for value in minimum_widths
    )
    gap = _pixel_width(spacing, label="spacing")
    return (
        sum(widths)
        + gap * max(0, len(widths) - 1)
        + RESPONSIVE_WIDTH_RESERVE
    )


def adaptive_layout_mode(
    available_width: WidthValue,
    minimum_widths: Iterable[WidthValue],
    *,
    spacing: WidthValue = 0,
) -> ResponsiveMode:
    """Choose one deterministic mode from measured content requirements."""

    available = _pixel_width(available_width, label="available width")
    threshold = stable_threshold(minimum_widths, spacing=spacing)
    return WIDE_MODE if available >= threshold else COMPACT_MODE


def responsive_progress(
    value: WidthValue,
    start: WidthValue,
    end: WidthValue,
) -> float:
    """Return a smooth 0..1 transition across a stable logical-pixel range."""

    numeric = float(_pixel_width(value, label="responsive value"))
    lower = float(_pixel_width(start, label="responsive range start"))
    upper = float(_pixel_width(end, label="responsive range end"))
    if upper <= lower:
        raise ValueError("responsive range end must be greater than its start")
    progress = max(0.0, min(1.0, (numeric - lower) / (upper - lower)))
    return progress * progress * (3.0 - 2.0 * progress)


def responsive_interpolate(
    value: WidthValue,
    start: WidthValue,
    end: WidthValue,
    start_value: WidthValue,
    end_value: WidthValue,
) -> float:
    """Blend a numeric layout value without introducing a pixel cliff."""

    initial = float(start_value)
    final = float(end_value)
    if not isfinite(initial) or not isfinite(final):
        raise ValueError("responsive interpolation values must be finite")
    progress = responsive_progress(value, start, end)
    return initial + (final - initial) * progress


def responsive_column_count(
    available_width: WidthValue,
    *,
    minimum_item_width: WidthValue,
    maximum_columns: int,
    spacing: WidthValue = 0,
) -> int:
    """Return the largest legible grid column count that actually fits."""

    available = _pixel_width(available_width, label="available width")
    item = _pixel_width(minimum_item_width, label="minimum item width")
    gap = _pixel_width(spacing, label="spacing")
    maximum = max(1, int(maximum_columns))
    for columns in range(maximum, 0, -1):
        if available >= stable_threshold((item,) * columns, spacing=gap):
            return columns
    return 1


def _size_width(value: Any) -> WidthValue | None:
    if value is None:
        return None
    width = getattr(value, "width", None)
    if callable(width):
        try:
            return width()
        except (RuntimeError, TypeError, ValueError):
            return None
    if isinstance(width, (int, float)):
        return width
    return None


def _method_value(target: Any, name: str) -> Any | None:
    method = getattr(target, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except (RuntimeError, TypeError, ValueError):
        return None


def measured_minimum_width(target: Any) -> int:
    """Measure a widget or layout's current minimum content width.

    Qt widgets expose slightly different useful hints.  Explicit minimums,
    minimum-size hints, and layout minimums are authoritative.  ``sizeHint`` is
    only a fallback when none of those provides a positive width, avoiding an
    unnecessarily early stack for intentionally shrinkable previews.
    """

    candidates: list[WidthValue] = []

    direct = _method_value(target, "minimumWidth")
    if direct is not None:
        candidates.append(direct)

    minimum_hint = _size_width(_method_value(target, "minimumSizeHint"))
    if minimum_hint is not None:
        candidates.append(minimum_hint)

    layout = _method_value(target, "layout")
    layout_minimum = _size_width(_method_value(layout, "minimumSize"))
    if layout_minimum is not None:
        candidates.append(layout_minimum)

    measured = max(
        (_pixel_width(value, label="minimum width hint") for value in candidates),
        default=0,
    )
    if measured > 0:
        return measured

    fallback = _size_width(_method_value(target, "sizeHint"))
    if fallback is not None:
        return _pixel_width(fallback, label="size hint")
    return 0


def _set_semantic_property(target: Any | None, name: str, value: Any) -> None:
    if target is None:
        return
    setter = getattr(target, "setProperty", None)
    if callable(setter):
        setter(name, value)


@dataclass(frozen=True)
class AdaptiveRegion:
    """One semantic region and its live minimum-width measurement."""

    region_id: str
    width_provider: WidthProvider
    target: Any | None = None

    def __post_init__(self) -> None:
        normalized = str(self.region_id).strip()
        if not normalized:
            raise ValueError("responsive region_id must not be empty")
        object.__setattr__(self, "region_id", normalized)
        if not callable(self.width_provider):
            raise TypeError("responsive width_provider must be callable")

    @classmethod
    def fixed(
        cls,
        region_id: str,
        minimum_width: WidthValue,
        *,
        target: Any | None = None,
    ) -> "AdaptiveRegion":
        normalized = _pixel_width(minimum_width, label="minimum width")
        return cls(region_id, lambda: normalized, target)

    @classmethod
    def measured(
        cls,
        region_id: str,
        target: Any,
        *,
        floor: WidthValue = 0,
    ) -> "AdaptiveRegion":
        minimum_floor = _pixel_width(floor, label="minimum width floor")
        return cls(
            region_id,
            lambda: max(minimum_floor, measured_minimum_width(target)),
            target,
        )

    def minimum_width(self) -> int:
        return _pixel_width(
            self.width_provider(),
            label=f"minimum width for {self.region_id}",
        )


@dataclass(frozen=True)
class RegionMeasurement:
    region_id: str
    minimum_width: int


@dataclass(frozen=True)
class AdaptiveLayoutTelemetry:
    """Semantic, capture-friendly record of one responsive decision."""

    semantic_id: str
    mode: ResponsiveMode
    available_width: int
    threshold_width: int
    content_width: int
    spacing: int
    reserve: int
    regions: tuple[RegionMeasurement, ...]

    @property
    def region_order(self) -> tuple[str, ...]:
        return tuple(region.region_id for region in self.regions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantic_id": self.semantic_id,
            "mode": self.mode,
            "available_width": self.available_width,
            "threshold_width": self.threshold_width,
            "content_width": self.content_width,
            "spacing": self.spacing,
            "reserve": self.reserve,
            "regions": [
                {
                    "region_id": region.region_id,
                    "minimum_width": region.minimum_width,
                }
                for region in self.regions
            ],
        }


class AdaptiveRow:
    """Apply row/stack mode without rebuilding or reordering child widgets."""

    def __init__(
        self,
        semantic_id: str,
        regions: Sequence[AdaptiveRegion],
        *,
        spacing: WidthValue = 0,
        apply_mode: ModeApplier | None = None,
        telemetry_target: Any | None = None,
        observe_telemetry: TelemetryObserver | None = None,
    ) -> None:
        normalized_id = str(semantic_id).strip()
        if not normalized_id:
            raise ValueError("responsive semantic_id must not be empty")
        ordered_regions = tuple(regions)
        if not ordered_regions:
            raise ValueError("an adaptive row requires at least one region")
        region_ids = tuple(region.region_id for region in ordered_regions)
        if len(set(region_ids)) != len(region_ids):
            raise ValueError("responsive region_id values must be unique")

        self.semantic_id = normalized_id
        self._regions = ordered_regions
        self._spacing = _pixel_width(spacing, label="spacing")
        self._apply_mode = apply_mode
        self._telemetry_target = telemetry_target
        self._observe_telemetry = observe_telemetry
        self._mode: ResponsiveMode | None = None
        self._telemetry: AdaptiveLayoutTelemetry | None = None
        self._published_properties: dict[str, Any] = {}

        for region in self._regions:
            _set_semantic_property(region.target, "responsiveRegion", region.region_id)

    @classmethod
    def for_box_layout(
        cls,
        semantic_id: str,
        regions: Sequence[AdaptiveRegion],
        *,
        layout: Any,
        wide_direction: Any,
        compact_direction: Any,
        spacing: WidthValue = 0,
        telemetry_target: Any | None = None,
        observe_telemetry: TelemetryObserver | None = None,
    ) -> "AdaptiveRow":
        """Adapt a QBoxLayout-like object without importing a Qt binding."""

        def set_direction(mode: ResponsiveMode) -> None:
            direction = wide_direction if mode == WIDE_MODE else compact_direction
            layout.setDirection(direction)

        return cls(
            semantic_id,
            regions,
            spacing=spacing,
            apply_mode=set_direction,
            telemetry_target=telemetry_target,
            observe_telemetry=observe_telemetry,
        )

    @property
    def regions(self) -> tuple[AdaptiveRegion, ...]:
        return self._regions

    @property
    def region_order(self) -> tuple[str, ...]:
        return tuple(region.region_id for region in self._regions)

    @property
    def mode(self) -> ResponsiveMode | None:
        return self._mode

    @property
    def telemetry(self) -> AdaptiveLayoutTelemetry | None:
        return self._telemetry

    def evaluate(self, available_width: WidthValue) -> AdaptiveLayoutTelemetry:
        available = _pixel_width(available_width, label="available width")
        regions = tuple(
            RegionMeasurement(region.region_id, region.minimum_width())
            for region in self._regions
        )
        threshold = stable_threshold(
            (region.minimum_width for region in regions),
            spacing=self._spacing,
        )
        content_width = threshold - RESPONSIVE_WIDTH_RESERVE
        mode: ResponsiveMode = WIDE_MODE if available >= threshold else COMPACT_MODE
        telemetry = AdaptiveLayoutTelemetry(
            semantic_id=self.semantic_id,
            mode=mode,
            available_width=available,
            threshold_width=threshold,
            content_width=content_width,
            spacing=self._spacing,
            reserve=RESPONSIVE_WIDTH_RESERVE,
            regions=regions,
        )

        if mode != self._mode:
            if self._apply_mode is not None:
                self._apply_mode(mode)
            self._mode = mode

        previous = self._telemetry
        self._telemetry = telemetry
        self._publish(telemetry)
        if telemetry != previous and self._observe_telemetry is not None:
            self._observe_telemetry(telemetry)
        return telemetry

    def _publish(self, telemetry: AdaptiveLayoutTelemetry) -> None:
        properties = {
            "responsiveRegion": telemetry.semantic_id,
            "responsiveMode": telemetry.mode,
            "layoutMode": telemetry.mode,
            "responsiveAvailableWidth": telemetry.available_width,
            "responsiveThreshold": telemetry.threshold_width,
            "responsiveContentWidth": telemetry.content_width,
            "responsiveReserve": telemetry.reserve,
            "responsiveRegionOrder": "|".join(telemetry.region_order),
        }
        for name, value in properties.items():
            if self._published_properties.get(name) == value:
                continue
            _set_semantic_property(self._telemetry_target, name, value)
            self._published_properties[name] = value


class AdaptiveSplit(AdaptiveRow):
    """Two-region specialization for preview/detail and comparison layouts."""

    def __init__(
        self,
        semantic_id: str,
        primary: AdaptiveRegion,
        secondary: AdaptiveRegion,
        **kwargs: Any,
    ) -> None:
        super().__init__(semantic_id, (primary, secondary), **kwargs)

    @classmethod
    def for_box_layout(
        cls,
        semantic_id: str,
        primary: AdaptiveRegion,
        secondary: AdaptiveRegion,
        *,
        layout: Any,
        wide_direction: Any,
        compact_direction: Any,
        spacing: WidthValue = 0,
        telemetry_target: Any | None = None,
        observe_telemetry: TelemetryObserver | None = None,
    ) -> "AdaptiveSplit":
        """Adapt a two-region QBoxLayout-like object without importing Qt."""

        def set_direction(mode: ResponsiveMode) -> None:
            direction = wide_direction if mode == WIDE_MODE else compact_direction
            layout.setDirection(direction)

        return cls(
            semantic_id,
            primary,
            secondary,
            spacing=spacing,
            apply_mode=set_direction,
            telemetry_target=telemetry_target,
            observe_telemetry=observe_telemetry,
        )
