from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ankigarden.ui.responsive import (
    COMPACT_MODE,
    RESPONSIVE_WIDTH_RESERVE,
    WIDE_MODE,
    AdaptiveRegion,
    AdaptiveRow,
    AdaptiveSplit,
    adaptive_layout_mode,
    measured_minimum_width,
    responsive_column_count,
    responsive_interpolate,
    responsive_progress,
    stable_threshold,
)


@dataclass
class _Size:
    value: float

    def width(self) -> float:
        return self.value


class _Target:
    def __init__(
        self,
        *,
        minimum: float = 0,
        minimum_hint: float = 0,
        layout_minimum: float = 0,
        size_hint: float = 0,
    ) -> None:
        self.minimum = minimum
        self.minimum_hint = minimum_hint
        self.layout_minimum = layout_minimum
        self.size_hint = size_hint
        self.properties: dict[str, Any] = {}

    def minimumWidth(self) -> float:
        return self.minimum

    def minimumSizeHint(self) -> _Size:
        return _Size(self.minimum_hint)

    def layout(self) -> "_Target":
        return self

    def minimumSize(self) -> _Size:
        return _Size(self.layout_minimum)

    def sizeHint(self) -> _Size:
        return _Size(self.size_hint)

    def setProperty(self, name: str, value: Any) -> None:
        self.properties[name] = value


class _BoxLayout:
    def __init__(self, children: list[str], tab_order: list[str]) -> None:
        self.children = children
        self.tab_order = tab_order
        self.direction_changes: list[str] = []

    def setDirection(self, direction: str) -> None:
        self.direction_changes.append(direction)


def test_threshold_uses_shared_reserve_and_rounds_fractional_measurements_up() -> None:
    assert RESPONSIVE_WIDTH_RESERVE == 24
    assert stable_threshold((199.1, 300), spacing=11.2) == 536
    assert adaptive_layout_mode(535, (199.1, 300), spacing=11.2) == COMPACT_MODE
    assert adaptive_layout_mode(536, (199.1, 300), spacing=11.2) == WIDE_MODE

    with pytest.raises(ValueError, match="finite number"):
        stable_threshold((float("nan"),))


def test_threshold_minus_two_through_plus_two_has_one_stable_boundary() -> None:
    widths = (240, 320)
    threshold = stable_threshold(widths, spacing=16)

    observed = {
        offset: adaptive_layout_mode(threshold + offset, widths, spacing=16)
        for offset in (-2, -1, 0, 1, 2)
    }

    assert observed == {
        -2: COMPACT_MODE,
        -1: COMPACT_MODE,
        0: WIDE_MODE,
        1: WIDE_MODE,
        2: WIDE_MODE,
    }


@pytest.mark.parametrize(
    ("semantic_id", "minimum_widths", "spacing"),
    (
        ("starter.actions", (120, 120), 8),
        ("fertilizer-replacement.comparison", (220, 220), 10),
        ("fertilizer-replacement.actions", (112, 112), 8),
        ("plant-story.hero", (104, 340), 12),
        ("nursery.hero", (400, 200), 14),
        ("nursery.receipt-actions", (140, 140), 8),
        ("garden-progress.navigation", (168, 560), 16),
        ("collection-loadout.workspace", (420, 460), 16),
        ("settings.display-studio", (280, 360), 20),
        ("settings.footer-actions", (96, 112), 8),
        ("dashboard.header-full", (230, 944, 373), 12),
        ("dashboard.header-title-actions", (230, 373), 12),
        ("dashboard.metrics-density", (944,), 0),
        ("dashboard.milestone", (300, 250, 160), 8),
        ("dashboard.rearrange-actions", (560,), 0),
    ),
)
def test_every_shared_semantic_breakpoint_is_stable_at_plus_or_minus_two(
    semantic_id: str,
    minimum_widths: tuple[int, ...],
    spacing: int,
) -> None:
    del semantic_id
    threshold = stable_threshold(minimum_widths, spacing=spacing)
    assert {
        offset: adaptive_layout_mode(
            threshold + offset,
            minimum_widths,
            spacing=spacing,
        )
        for offset in (-2, -1, 0, 1, 2)
    } == {
        -2: COMPACT_MODE,
        -1: COMPACT_MODE,
        0: WIDE_MODE,
        1: WIDE_MODE,
        2: WIDE_MODE,
    }


@pytest.mark.parametrize(
    ("target_columns", "expected_threshold"),
    ((2, 394), (3, 584)),
)
def test_grid_column_count_changes_once_at_each_content_threshold(
    target_columns: int,
    expected_threshold: int,
) -> None:
    threshold = stable_threshold((180,) * target_columns, spacing=10)
    assert threshold == expected_threshold
    observed = {
        offset: responsive_column_count(
            threshold + offset,
            minimum_item_width=180,
            maximum_columns=3,
            spacing=10,
        )
        for offset in (-2, -1, 0, 1, 2)
    }
    assert observed == {
        -2: target_columns - 1,
        -1: target_columns - 1,
        0: target_columns,
        1: target_columns,
        2: target_columns,
    }


@pytest.mark.parametrize("breakpoint", (600, 620))
def test_tile_grid_breakpoints_are_stable_at_plus_or_minus_two(
    breakpoint: int,
) -> None:
    minimum_tile_width = max(180, (breakpoint - 10 - 24) // 2)
    threshold = stable_threshold(
        (minimum_tile_width, minimum_tile_width),
        spacing=10,
    )
    assert threshold == breakpoint
    assert {
        offset: responsive_column_count(
            threshold + offset,
            minimum_item_width=minimum_tile_width,
            maximum_columns=2,
            spacing=10,
        )
        for offset in (-2, -1, 0, 1, 2)
    } == {-2: 1, -1: 1, 0: 2, 1: 2, 2: 2}


def test_shared_split_breakpoint_is_stable_at_plus_or_minus_two() -> None:
    breakpoint = 620
    region_floor = max(220, (breakpoint - 16 - 24) // 2)
    assert stable_threshold((region_floor, region_floor), spacing=16) == breakpoint
    assert {
        offset: adaptive_layout_mode(
            breakpoint + offset,
            (region_floor, region_floor),
            spacing=16,
        )
        for offset in (-2, -1, 0, 1, 2)
    } == {
        -2: COMPACT_MODE,
        -1: COMPACT_MODE,
        0: WIDE_MODE,
        1: WIDE_MODE,
        2: WIDE_MODE,
    }


def test_continuous_responsive_values_have_no_hidden_pixel_cliffs() -> None:
    assert responsive_progress(100, 100, 200) == 0.0
    assert responsive_progress(200, 100, 200) == 1.0
    assert responsive_interpolate(150, 100, 200, 20, 40) == pytest.approx(30)

    for boundary in (360, 440, 480, 520, 560, 600, 620, 660, 680, 720, 760, 780, 840):
        values = [
            responsive_interpolate(width, 360, 840, 1.18, 1.0)
            for width in range(boundary - 2, boundary + 3)
        ]
        assert max(
            abs(later - earlier)
            for earlier, later in zip(values, values[1:])
        ) < 0.01

    with pytest.raises(ValueError, match="greater than"):
        responsive_progress(100, 200, 200)


def test_historical_capture_pairs_no_longer_straddle_shared_layout_cliffs() -> None:
    cases = {
        "starter-399-401": (
            (399, 401),
            (120, 120),
            8,
            (WIDE_MODE, WIDE_MODE),
        ),
        "fertilizer-replacement-399-401": (
            (399, 401),
            (220, 220),
            10,
            (COMPACT_MODE, COMPACT_MODE),
        ),
        "plant-story-539-541": (
            (539, 541),
            (104, 340),
            12,
            (WIDE_MODE, WIDE_MODE),
        ),
        "nursery-759-761": (
            (759, 761),
            (400, 200),
            14,
            (WIDE_MODE, WIDE_MODE),
        ),
        "progress-819-821": (
            (819, 821),
            (168, 560),
            16,
            (WIDE_MODE, WIDE_MODE),
        ),
        "customize-819-821": (
            (819, 821),
            (420, 460),
            16,
            (COMPACT_MODE, COMPACT_MODE),
        ),
        "dashboard-699-701": (
            (699, 701),
            (300, 250, 160),
            8,
            (COMPACT_MODE, COMPACT_MODE),
        ),
    }
    for _label, (widths, regions, spacing, expected) in cases.items():
        assert tuple(
            adaptive_layout_mode(width, regions, spacing=spacing)
            for width in widths
        ) == expected


def test_dynamic_child_minima_recompute_the_threshold_from_current_content() -> None:
    primary = _Target(minimum=180, minimum_hint=220, layout_minimum=200)
    secondary = _Target(minimum=260, minimum_hint=280, layout_minimum=270)
    split = AdaptiveSplit(
        "settings-preview",
        AdaptiveRegion.measured("settings", primary),
        AdaptiveRegion.measured("preview", secondary),
        spacing=16,
    )

    initial = split.evaluate(540)
    assert initial.threshold_width == 220 + 280 + 16 + 24
    assert initial.mode == WIDE_MODE

    secondary.layout_minimum = 340
    updated = split.evaluate(540)
    assert updated.threshold_width == 220 + 340 + 16 + 24
    assert updated.mode == COMPACT_MODE
    assert updated.region_order == ("settings", "preview")


def test_size_hint_is_only_a_fallback_for_a_shrinkable_region() -> None:
    shrinkable = _Target(minimum=120, minimum_hint=160, size_hint=600)
    fallback_only = _Target(size_hint=245.2)

    assert measured_minimum_width(shrinkable) == 160
    assert measured_minimum_width(fallback_only) == 246


def test_mode_application_is_idempotent_and_preserves_child_and_tab_order() -> None:
    layout = _BoxLayout(
        children=["filters", "results", "actions"],
        tab_order=["filters", "results", "actions"],
    )
    original_children = list(layout.children)
    original_tab_order = list(layout.tab_order)
    row = AdaptiveRow.for_box_layout(
        "nursery-catalog",
        (
            AdaptiveRegion.fixed("filters", 180),
            AdaptiveRegion.fixed("results", 360),
            AdaptiveRegion.fixed("actions", 160),
        ),
        layout=layout,
        wide_direction="left-to-right",
        compact_direction="top-to-bottom",
        spacing=12,
    )
    threshold = stable_threshold((180, 360, 160), spacing=12)

    row.evaluate(threshold - 2)
    row.evaluate(threshold - 1)
    row.evaluate(threshold - 1)
    row.evaluate(threshold)
    row.evaluate(threshold + 1)
    row.evaluate(threshold + 2)

    assert layout.direction_changes == ["top-to-bottom", "left-to-right"]
    assert layout.children == original_children
    assert layout.tab_order == original_tab_order
    assert row.region_order == ("filters", "results", "actions")


def test_adaptive_split_box_layout_adapter_changes_direction_in_place() -> None:
    layout = _BoxLayout(
        children=["preview", "details"],
        tab_order=["preview", "details"],
    )
    split = AdaptiveSplit.for_box_layout(
        "comparison",
        AdaptiveRegion.fixed("preview", 320),
        AdaptiveRegion.fixed("details", 280),
        layout=layout,
        wide_direction="left-to-right",
        compact_direction="top-to-bottom",
        spacing=16,
    )
    threshold = stable_threshold((320, 280), spacing=16)

    split.evaluate(threshold - 1)
    split.evaluate(threshold)

    assert layout.direction_changes == ["top-to-bottom", "left-to-right"]
    assert layout.children == ["preview", "details"]
    assert layout.tab_order == ["preview", "details"]


def test_semantic_region_telemetry_is_complete_and_published_without_churn() -> None:
    owner = _Target()
    primary = _Target(minimum_hint=240)
    secondary = _Target(minimum_hint=320)
    observations = []
    split = AdaptiveSplit(
        "plant-story-comparison",
        AdaptiveRegion.measured("story", primary),
        AdaptiveRegion.measured("artwork", secondary),
        spacing=16,
        telemetry_target=owner,
        observe_telemetry=observations.append,
    )
    threshold = stable_threshold((240, 320), spacing=16)

    telemetry = split.evaluate(threshold)
    same = split.evaluate(threshold)

    assert telemetry == same
    assert len(observations) == 1
    assert telemetry.as_dict() == {
        "semantic_id": "plant-story-comparison",
        "mode": WIDE_MODE,
        "available_width": threshold,
        "threshold_width": threshold,
        "content_width": threshold - RESPONSIVE_WIDTH_RESERVE,
        "spacing": 16,
        "reserve": RESPONSIVE_WIDTH_RESERVE,
        "regions": [
            {"region_id": "story", "minimum_width": 240},
            {"region_id": "artwork", "minimum_width": 320},
        ],
    }
    assert owner.properties["responsiveRegion"] == "plant-story-comparison"
    assert owner.properties["responsiveMode"] == WIDE_MODE
    assert owner.properties["layoutMode"] == WIDE_MODE
    assert owner.properties["responsiveThreshold"] == threshold
    assert owner.properties["responsiveRegionOrder"] == "story|artwork"
    assert primary.properties["responsiveRegion"] == "story"
    assert secondary.properties["responsiveRegion"] == "artwork"


def test_responsive_foundation_imports_without_aqt() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ankigarden"
        / "ui"
        / "responsive.py"
    ).read_text("utf-8")
    assert "from aqt" not in source
    assert "import aqt" not in source
