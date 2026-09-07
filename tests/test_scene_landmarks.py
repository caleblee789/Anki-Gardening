from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ankigarden.asset_manager import AssetManager
from ankigarden.ui.landmarks import (
    DEFAULT_LANDMARK_ACTIONS,
    GARDEN_BACKGROUND_FOCAL,
    LandmarkAction,
    background_cover_rect,
    normalized_landmark_action,
    project_landmark_bounds,
    project_landmark_outline_paths,
    project_landmark_point,
    project_landmark_polygon,
    resolve_scene_landmarks,
)
from ankigarden.ui.plant_display import contained_canvas_rect

ROOT = Path(__file__).resolve().parents[1]


def _placement() -> dict[str, object]:
    return {"surface_profile": json.loads(
        (ROOT / "tests/fixtures/verdant_twilight_surface_v6.json").read_text()
    )}


def _sceneries():
    rows = {
        row["asset_id"]: row
        for row in json.loads((ROOT / "ankigarden/assets/manifest.json").read_text())["assets"]
        if row.get("category") == "backgrounds"
    }
    manager = object.__new__(AssetManager)
    manager._catalog_by_asset_id = {("backgrounds", key): row for key, row in rows.items()}
    return [
        (key, manager._placement_for_entry(row, "backgrounds"))
        for key, row in rows.items() if "soil_master" in key
    ]


def test_nursery_uses_registered_copy_and_manifest_geometry() -> None:
    landmarks = resolve_scene_landmarks(_placement(), width=800, height=600, interactive=True)
    assert [(item.landmark_id, item.action_id, item.accessible_name, item.tooltip) for item in landmarks] == [
        ("nursery_entrance", "garden.nursery.open", "Shop", "Open shop"),
        ("garden_house", "garden.trophies.open", "Trophy Room", "Open Trophy Room"),
    ]
    for item in landmarks:
        left, top, width, height = item.bounds
        assert all(left <= x <= left + width and top <= y <= top + height for x, y in item.polygon)
        assert item.label_anchor[1] > max(y for _, y in item.polygon)


@pytest.mark.parametrize("width,height", [(540, 360), (828, 552), (1200, 800)])
def test_building_projection_matches_the_painted_background_crop(width, height) -> None:
    # The 4:3 painting fills a 3:2 canvas: 12.5% extra height, cropped at 48%.
    # These expected positions are independent of the landmark implementation.
    expected = [(0, -.06 * height), (.25 * width, .22125 * height),
                (width, 1.065 * height)]
    points = [(0, 0), (.25, .25), (1, 1)]
    for point, target in zip(points, expected):
        assert project_landmark_point(
            point, width=width, height=height, source_aspect=4 / 3,
            focal=GARDEN_BACKGROUND_FOCAL,
        ) == pytest.approx(target)
    assert background_cover_rect(width, height, 1448, 1086, GARDEN_BACKGROUND_FOCAL) == pytest.approx(
        (0, -.06 * height, width, 1.125 * height)
    )


def test_every_scenery_has_separate_building_shapes_and_visible_edge_strokes() -> None:
    sceneries = _sceneries()
    assert len(sceneries) == 9
    contours = {key: set() for key in ("nursery_entrance", "garden_house")}
    for _, placement in sceneries:
        for width, height in ((540, 360), (1040, 720), (1920, 900)):
            canvas = contained_canvas_rect(width, height)
            args = dict(width=canvas.width, height=canvas.height,
                        source_aspect=4 / 3, focal=GARDEN_BACKGROUND_FOCAL)
            landmarks = resolve_scene_landmarks(
                placement, width=canvas.width, height=canvas.height, interactive=True,
            )
            assert {item.landmark_id for item in landmarks} == set(contours)
            for item in landmarks:
                contours[item.landmark_id].add(item.polygon)
                hit = project_landmark_bounds(item, **args)
                assert hit is not None
                left, top, hit_width, hit_height = hit
                assert hit_width >= 44 and hit_height >= 44
                assert left >= 0 and top >= 0
                assert left + hit_width <= round(canvas.width)
                assert top + hit_height <= round(canvas.height)
                points = project_landmark_polygon(item, **args)
                assert all(left - 1 <= x <= left + hit_width + 1
                           and top - 1 <= y <= top + hit_height + 1 for x, y in points)
                strokes = project_landmark_outline_paths(item, **args)
                assert strokes and all(path[0] != path[-1] for path in strokes)
        assert resolve_scene_landmarks(placement, width=1200, height=400, interactive=False) == ()
    assert all(len(shapes) == 9 for shapes in contours.values())


@pytest.mark.parametrize("defect", ["unknown_action", "bounds", "missing_polygon", "bad_point", "flat_polygon", "bad_stroke"])
def test_unknown_or_malformed_landmarks_fail_closed(defect) -> None:
    placement = deepcopy(_placement())
    landmark = placement["surface_profile"]["landmarks"][0]
    geometry = landmark["variants"]["4:3"]
    if defect == "unknown_action":
        landmark["action_id"] = "garden.unknown.open"
    elif defect == "bounds":
        geometry["bounds"] = [0.9, 0.9, 0.2, 0.2]
    elif defect == "missing_polygon":
        geometry.pop("polygon")
    elif defect == "bad_point":
        geometry["polygon"][1] = [2, 3]
    elif defect == "flat_polygon":
        geometry["polygon"] = [[.1, .1], [.2, .2], [.3, .3]]
    else:
        geometry["outline_paths"][0][1] = [None, .2]
    assert [item.action_id for item in resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True,
    )] == ["garden.trophies.open"]


def test_registered_future_action_is_generic_and_tooltip_is_one_line() -> None:
    placement = deepcopy(_placement())
    landmark = placement["surface_profile"]["landmarks"][0]
    landmark["landmark_id"] = "tool_shed"
    landmark["action_id"] = "garden.tools.open"
    action = normalized_landmark_action("Tool shed", "Open\n tool shed")
    assert action == LandmarkAction("Tool shed", "Open tool shed")
    actions = {**DEFAULT_LANDMARK_ACTIONS, "garden.tools.open": action}
    resolved = resolve_scene_landmarks(placement, width=800, height=600, interactive=True, actions=actions)
    assert [(item.landmark_id, item.action_id, item.tooltip) for item in resolved] == [
        ("tool_shed", "garden.tools.open", "Open tool shed"),
        ("garden_house", "garden.trophies.open", "Open Trophy Room"),
    ]
