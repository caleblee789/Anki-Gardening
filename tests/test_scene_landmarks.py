from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ankigarden.asset_manager import AssetManager
from ankigarden.ui.landmarks import (
    DEFAULT_LANDMARK_ACTIONS,
    LandmarkAction,
    normalized_landmark_action,
    project_landmark_bounds,
    project_landmark_outline_paths,
    project_landmark_polygon,
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
    assert nursery.tooltip == "Open nursery"
    assert nursery.bounds == (0.076, 0.142, 0.146, 0.178)
    assert len(nursery.polygon) == 13
    house = landmarks[1]
    assert house.landmark_id == "garden_house"
    assert house.action_id == "garden.collection.open"
    assert house.accessible_name == "Collection"
    assert house.tooltip == "Open collection"
    assert len(house.polygon) == 17
    assert tuple(len(path) for path in house.outline_paths) == (7, 2, 2)


def test_every_responsive_landmark_uses_a_detailed_building_contour() -> None:
    placement = _placement()

    for width, height in ((800, 600), (1280, 720), (1920, 700)):
        landmarks = resolve_scene_landmarks(
            placement, width=width, height=height, interactive=True
        )
        assert {item.landmark_id for item in landmarks} == {
            "nursery_entrance",
            "garden_house",
        }
        assert all(len(item.polygon) >= 13 for item in landmarks)

        house = next(item for item in landmarks if item.landmark_id == "garden_house")
        # The first six points step around the roof and chimney instead of
        # replacing the cottage with one broad convex hull.
        roof_steps = house.polygon[:6]
        assert len({point[0] for point in roof_steps}) >= 4
        assert len({point[1] for point in roof_steps}) >= 4
        assert len(house.polygon) >= 15
        assert len(house.outline_paths) == 3


def test_house_outline_is_open_and_occlusion_aware() -> None:
    placement = _placement()
    profile = placement["surface_profile"]

    for width, height in ((800, 600), (1280, 720), (1920, 700)):
        house = next(
            item
            for item in resolve_scene_landmarks(
                placement, width=width, height=height, interactive=True
            )
            if item.landmark_id == "garden_house"
        )
        variant_name = (
            "home" if width / height >= 2.05
            else "4:3" if width / height <= 1.42
            else "16:9"
        )
        variant = profile["variants"][variant_name]
        projected = project_landmark_outline_paths(
            house,
            width=width,
            height=height,
            source_aspect=variant["width"] / variant["height"],
            focal=tuple(variant["focal_point"]),
        )

        assert tuple(len(path) for path in projected) == (7, 2, 2)
        assert all(path[0] != path[-1] for path in projected)


def test_autumn_house_override_projects_the_measured_16x9_edges() -> None:
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "ankigarden/assets/manifest.json"
        ).read_text(encoding="utf-8")
    )
    rows = {
        row["asset_id"]: row
        for row in manifest["assets"]
        if row.get("category") == "backgrounds"
    }
    manager = object.__new__(AssetManager)
    manager._catalog_by_asset_id = {
        ("backgrounds", asset_id): row for asset_id, row in rows.items()
    }
    placement = manager._placement_for_entry(
        rows["bg_autumn_any_soil_master_v6"], "backgrounds"
    )
    house = next(
        landmark
        for landmark in resolve_scene_landmarks(
            placement,
            width=1672,
            height=941,
            interactive=True,
        )
        if landmark.landmark_id == "garden_house"
    )

    assert house.bounds == (0.711, 0.131, 0.132, 0.249)
    assert tuple(len(path) for path in house.outline_paths) == (11, 2, 2)
    assert house.outline_paths[0][0] == (0.711, 0.245)
    assert house.outline_paths[0][6] == (0.751, 0.134)
    assert house.outline_paths[1][-1] == (0.807, 0.245)


def test_landmark_highlight_draws_only_the_building_outline() -> None:
    scene_source = (
        Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py"
    ).read_text(encoding="utf-8")
    affordance_source = scene_source.split(
        "def _draw_landmark_affordances", 1
    )[1].split("def _draw_card_connector", 1)[0]

    assert "painter.setBrush(Qt.BrushStyle.NoBrush)" in affordance_source
    assert "QColor(244, 198, 103, 34)" not in affordance_source
    assert "if outline_paths:" in affordance_source
    assert "for outline in outline_paths:" in affordance_source
    assert "Qt.PenCapStyle.RoundCap" in affordance_source
    assert "Qt.PenJoinStyle.RoundJoin" in affordance_source


def test_preview_is_inert_even_when_manifest_supports_home_variant() -> None:
    placement = _placement()

    assert resolve_scene_landmarks(
        placement, width=1200, height=400, interactive=False
    ) == ()
    full_garden = resolve_scene_landmarks(
        placement, width=1200, height=400, interactive=True
    )
    assert full_garden[0].bounds == (0.222, 0.169, 0.082, 0.173)


def test_unknown_or_malformed_actions_fail_closed() -> None:
    placement = deepcopy(_placement())
    landmark = placement["surface_profile"]["landmarks"][0]
    landmark["action_id"] = "garden.unknown.open"
    assert [item.action_id for item in resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True
    )] == ["garden.collection.open"]

    landmark["action_id"] = "garden.nursery.open"
    landmark["variants"]["4:3"]["bounds"] = [0.9, 0.9, 0.2, 0.2]
    assert [item.action_id for item in resolve_scene_landmarks(
        placement, width=800, height=600, interactive=True
    )] == ["garden.collection.open"]


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
        ("garden_house", "garden.collection.open", "Open collection"),
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


def test_projected_building_contours_stay_inside_their_forgiving_hit_targets() -> None:
    placement = _placement()
    profile = placement["surface_profile"]

    for width, height in ((800, 600), (1280, 720), (1920, 700)):
        landmarks = resolve_scene_landmarks(
            placement, width=width, height=height, interactive=True
        )
        variant_name = (
            "home" if width / height >= 2.05
            else "4:3" if width / height <= 1.42
            else "16:9"
        )
        variant = profile["variants"][variant_name]
        source_aspect = variant["width"] / variant["height"]
        focal = tuple(variant["focal_point"])

        for landmark in landmarks:
            hit = project_landmark_bounds(
                landmark,
                width=width,
                height=height,
                source_aspect=source_aspect,
                focal=focal,
            )
            points = project_landmark_polygon(
                landmark,
                width=width,
                height=height,
                source_aspect=source_aspect,
                focal=focal,
            )
            assert hit is not None
            left, top, hit_width, hit_height = hit
            tolerance = 3.0
            assert all(
                left - tolerance <= x <= left + hit_width + tolerance
                and top - tolerance <= y <= top + hit_height + tolerance
                for x, y in points
            )
