from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.ui.plant_display import (
    Rect,
    bed_badge_rect,
    move_badge_label,
    plant_layout,
    requires_native_destination_selector,
)


MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
OUTPUT = ROOT / "build" / "full-catalog-layout-report.json"
SIZES = (
    # These are the two smallest scene canvases reachable around the dashboard's
    # 620 px minimum window width and its 4:3 -> 16:9 responsive breakpoint.
    ("minimum-dashboard", 572, 429, "dashboard"),
    ("compact-wide", 620, 349, "dashboard"),
    ("4:3", 640, 480, "dashboard"),
    ("3:2", 720, 480, "dashboard"),
    ("16:9", 800, 450, "dashboard"),
    ("home", 1000, 420, "home"),
    ("wide", 1600, 900, "dashboard"),
    ("exact-scene", 1922, 800, "dashboard"),
)


def _backgrounds(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    release_rows = [
        row for row in rows
        if row.get("category") == "backgrounds"
        and row.get("release_preferred") is True
    ]
    for row in sorted(
        release_rows,
        key=lambda candidate: (
            -float(candidate.get("quality_score", 0.0)),
            str(candidate.get("asset_id", "")),
        ),
    ):
        theme = str((row.get("slot") or {}).get("theme", ""))
        if theme:
            result.setdefault(theme, row)
    if not result:
        raise ValueError("The manifest must declare at least one release-preferred background.")
    return result


def _overlap_ratio(first: Rect, second: Rect) -> float:
    return first.intersection_area(second) / max(1.0, min(first.area, second.area))


def _scenario_warnings(
    layouts: list[Any],
    *,
    width: int,
    height: int,
    count: int,
    move_mode: bool,
    surface_context: str,
) -> list[str]:
    active = [row for row in layouts if row.slot_index < count]
    warnings: set[str] = set()
    if len({row.slot_index for row in layouts}) != len(layouts):
        warnings.add("duplicate slots")
    if any(
        row.visible.x < -.5 or row.visible.y < -.5
        or row.visible.right > width + .5 or row.visible.bottom > height + .5
        for row in active
    ):
        warnings.add("clipping")
    if any(
        first.support_rect.intersects(second.support_rect)
        for index, first in enumerate(active) for second in active[index + 1:]
    ):
        warnings.add("support overlap")
    if any(
        _overlap_ratio(first.foliage_rect, second.foliage_rect)
        > (.78 if abs(first.z_depth - second.z_depth) >= height * .04 else .60)
        for index, first in enumerate(active) for second in active[index + 1:]
    ):
        warnings.add("foliage overlap above policy")
    if any(row.hit.width < 44 or row.hit.height < 44 for row in active):
        warnings.add("small interaction target")
    if any(abs(row.base_rect.bottom - row.depth) > .5 for row in active):
        warnings.add("ground-anchor drift")
    if [row.z_depth for row in active] != sorted(row.z_depth for row in active):
        warnings.add("unstable z-order")
    if any(
        row.surface_id and (
            row.support_rect.x < row.contact_plane.x - .5
            or row.support_rect.right > row.contact_plane.right + .5
            or not row.contact_plane.y <= row.depth <= row.contact_plane.bottom
        )
        for row in active
    ):
        warnings.add("support outside painted plane")
    dense = count >= 4
    dense_narrow = dense and width <= 720
    maximum_fit_error = .261 if dense_narrow else .161 if dense else .081
    minimum_fit_scale = .739 if dense_narrow else .839 if dense else .919
    if any(
        row.target_error > maximum_fit_error
        or not minimum_fit_scale <= row.fit_scale <= 1.001
        for row in active
    ):
        warnings.add("fit exceeds responsive policy")
    use_native_selector = surface_context == "home" or requires_native_destination_selector(
        layouts, width, height, range(count)
    )
    if move_mode and not use_native_selector:
        occupied = set(range(count))
        names = {slot: f"Plant {slot + 1}" for slot in occupied}
        obstacles = [row.visible.expanded(4, 3) for row in active]
        badges: list[Rect] = []
        for row in layouts:
            label, state = move_badge_label(
                row.slot_index,
                origin_slot=0,
                destination_slot=1,
                unlocked_slots=6,
                occupied_slots=occupied,
                occupant_names=names,
            )
            # This mirrors GardenScene._draw_slot_placeholders: compact scenes
            # keep every expanded bed footprint clickable but paint a numbered
            # badge only for the current and keyboard-selected beds. Treating
            # all six compact badges as visible manufactured collisions that
            # cannot occur in the runtime UI.
            if width < 900 and state not in {"active", "selected", "current"}:
                target_width = row.bed_footprint.width + 28.0
                target_height = row.bed_footprint.height + 22.0
                if target_width < 44 or target_height < 44:
                    warnings.add("small move target")
                continue
            visual_label = str(row.slot_index + 1)
            badge = bed_badge_rect(row, visual_label, width, height, obstacles + badges)
            badges.append(badge)
            if badge.width < 44 or badge.height < 44:
                warnings.add("small move target")
            if badge.x < 0 or badge.y < 0 or badge.right > width or badge.bottom > height:
                warnings.add("hidden move control")
            if any(_overlap_ratio(badge, obstacle) > .25 for obstacle in obstacles):
                warnings.add("move control overlap")
        if any(
            _overlap_ratio(first, second) > .25
            for index, first in enumerate(badges) for second in badges[index + 1:]
        ):
            warnings.add("move target overlap")
    for row in active:
        warnings.update(row.validation_warnings)
    return sorted(warnings)


def validate() -> dict[str, Any]:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]
    plants = [row for row in rows if row.get("category") == "plants"]
    backgrounds = _backgrounds(rows)
    failures: list[dict[str, Any]] = []
    warning_counts: Counter[str] = Counter()
    scenario_count = 0
    for asset in plants:
        placement = asset.get("placement", {})
        canvas_aspect = float(asset["width"]) / max(1.0, float(asset["height"]))
        for theme, background in backgrounds.items():
            background_placement = background.get("placement", {})
            for size_name, width, height, context in SIZES:
                for count in range(1, 7):
                    items = [
                        {
                            "plant_id": f"{asset['asset_id']}-{slot}",
                            "slot_index": slot,
                            "species": (asset.get("slot") or {}).get("species", "plant"),
                            "stage": (asset.get("slot") or {}).get("stage", "seed"),
                            "quality_tier": asset.get("quality_tier", "balanced"),
                            "placement": placement,
                            "canvas_aspect": canvas_aspect,
                            "occupied": slot < count,
                        }
                        for slot in range(6)
                    ]
                    for move_mode in (False, True):
                        layouts = plant_layout(
                            width,
                            height,
                            items,
                            background_placement,
                            surface_context=context,
                            composition_count=count,
                            protected_status=False,
                            reserve_move_controls=move_mode and width >= 900 and context != "home",
                        )
                        scenario_count += 1
                        warnings = _scenario_warnings(
                            layouts,
                            width=width,
                            height=height,
                            count=count,
                            move_mode=move_mode,
                            surface_context=context,
                        )
                        if warnings:
                            warning_counts.update(warnings)
                            if len(failures) < 50000:
                                failures.append(
                                    {
                                        "asset_id": asset["asset_id"],
                                        "theme": theme,
                                        "size": size_name,
                                        "count": count,
                                        "mode": "move" if move_mode else "normal",
                                        "warnings": warnings,
                                    }
                                )
    report = {
        "asset_count": len(plants),
        "theme_count": len(backgrounds),
        "size_count": len(SIZES),
        "count_profiles": 6,
        "mode_count": 2,
        "scenario_count": scenario_count,
        "failure_count": sum(warning_counts.values()),
        "warning_counts": dict(sorted(warning_counts.items())),
        "failures": failures,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    report = validate()
    print(json.dumps({key: report[key] for key in report if key != "failures"}, indent=2))
    if report["failure_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
