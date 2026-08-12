from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ankigarden.ui.landmarks import (
    DEFAULT_LANDMARK_ACTIONS,
    LandmarkAction,
    normalized_landmark_action,
    project_landmark_bounds,
    resolve_scene_landmarks,
)


def _placement() -> dict[str, object]:
    profile = json.loads(
        (Path(__file__).parent / "fixtures/verdant_twilight_surface_v6.json").read_text()
    )
    return {"surface_profile": profile}


def test_nursery_uses_registered_copy_and_manifest_geometry() -> None:
    landmarks = resolve_scene_landmarks(
        _placement(), width=800, height=600, interactive=True
    )

    assert len(landmarks) == 2
    nursery = landmarks[0]
    assert nursery.landmark_id == "nursery_entrance"
    assert nursery.action_id == "garden.nursery.open"
    assert nursery.accessible_name == "Nursery"
    assert nursery.tooltip == "Open Nursery"
    assert nursery.bounds == (0.077, 0.15, 0.145, 0.17)
    assert len(nursery.polygon) == 7
    house = landmarks[1]
    assert house.landmark_id == "garden_house"
    assert house.action_id == "garden.progress.open"
    assert house.accessible_name == "Garden Progress"
    assert house.tooltip == "Open Garden Progress"


def test_preview_is_inert_even_when_manifest_supports_home_variant() -> None:
    placement = _placement()

    assert resolve_scene_landmarks(
        placement, width=1200, height=400, interactive=False
    ) == ()
    full_garden = resolve_scene_landmarks(
        placement, width=1200, height=400, interactive=True
    )
    assert full_garden[0].bounds == (0.224, 0.169, 0.08, 0.173)


def test_unknown_or_malformed_actions_fail_closed() -> None:
    placement = deepcopy(_placement())
    landmark = placement["surface_profile"]["landmarks"][0]
    landmark["action_id"] = "garden.unknown.open"
    assert [item.action_id for item in resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True
    )] == ["garden.progress.open"]

    landmark["action_id"] = "garden.nursery.open"
    landmark["variants"]["4:3"]["bounds"] = [0.9, 0.9, 0.2, 0.2]
    assert [item.action_id for item in resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True
    )] == ["garden.progress.open"]


def test_registered_future_action_is_generic_and_tooltip_is_one_line() -> None:
    placement = deepcopy(_placement())
    landmark = placement["surface_profile"]["landmarks"][0]
    landmark["landmark_id"] = "tool_shed"
    landmark["action_id"] = "garden.tools.open"
    action = normalized_landmark_action("Tool shed", "Open\n tool shed")
    assert action == LandmarkAction("Tool shed", "Open tool shed")

    actions = {**DEFAULT_LANDMARK_ACTIONS, "garden.tools.open": action}
    resolved = resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True, actions=actions
    )
    assert [(item.landmark_id, item.action_id, item.tooltip) for item in resolved] == [
        ("tool_shed", "garden.tools.open", "Open tool shed"),
        ("garden_house", "garden.progress.open", "Open Garden Progress"),
    ]


def test_projected_hotspot_stays_inside_scene_and_meets_touch_target() -> None:
    landmark = resolve_scene_landmarks(
        _placement(), width=1920, height=700, interactive=True
    )[0]
    geometry = project_landmark_bounds(
        landmark,
        width=1920,
        height=700,
        source_aspect=12 / 5,
        focal=(0.5, 0.5),
    )

    assert geometry is not None
    x, y, width, height = geometry
    assert x >= 0 and y >= 0
    assert width >= 44 and height >= 44
    assert x + width <= 1920
    assert y + height <= 700
