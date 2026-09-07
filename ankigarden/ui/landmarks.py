from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .plant_display import scene_surface_variant


GARDEN_BACKGROUND_FOCAL = (0.5, 0.48)


def background_cover_rect(
    width: float, height: float, source_width: float, source_height: float,
    focal: tuple[float, float],
) -> tuple[float, float, float, float]:
    """The raster draw rectangle, relative to the Garden canvas origin."""

    scale = max(width / source_width, height / source_height)
    draw_width, draw_height = source_width * scale, source_height * scale
    return (
        -(draw_width - width) * focal[0],
        -(draw_height - height) * focal[1],
        draw_width, draw_height,
    )


def project_landmark_point(
    point: tuple[float, float], *, width: float, height: float,
    source_aspect: float, focal: tuple[float, float],
) -> tuple[float, float]:
    """Project authored image coordinates through the painted cover crop."""

    x, y, draw_width, draw_height = background_cover_rect(
        width, height, source_aspect, 1.0, focal,
    )
    return x + point[0] * draw_width, y + point[1] * draw_height


@dataclass(frozen=True)
class LandmarkAction:
    """Learner-facing behavior registered for a manifest landmark action."""

    accessible_name: str
    tooltip: str


@dataclass(frozen=True)
class SceneLandmark:
    """Validated, variant-specific landmark ready for scene interaction."""

    landmark_id: str
    action_id: str
    accessible_name: str
    tooltip: str
    bounds: tuple[float, float, float, float]
    polygon: tuple[tuple[float, float], ...] = ()
    outline_paths: tuple[tuple[tuple[float, float], ...], ...] = ()
    label_anchor: tuple[float, float] | None = None


DEFAULT_LANDMARK_ACTIONS: Mapping[str, LandmarkAction] = {
    "garden.nursery.open": LandmarkAction(
        accessible_name="Shop",
        tooltip="Open shop",
    ),
    "garden.progress.open": LandmarkAction(
        accessible_name="Progress",
        tooltip="Open progress",
    ),
    "garden.trophies.open": LandmarkAction(
        accessible_name="Trophy Room",
        tooltip="Open Trophy Room",
    ),
    "garden.collection.open": LandmarkAction(
        accessible_name="Collection",
        tooltip="Open collection",
    ),
}


def normalized_landmark_action(accessible_name: Any, tooltip: Any) -> LandmarkAction | None:
    """Return a usable one-line action contract, or fail closed."""

    name = " ".join(str(accessible_name or "").split()).strip()
    help_text = " ".join(str(tooltip or "").split()).strip()
    if not name or not help_text:
        return None
    return LandmarkAction(accessible_name=name, tooltip=help_text)


def resolve_scene_landmarks(
    placement: dict[str, Any] | None,
    *,
    width: float,
    height: float,
    interactive: bool,
    actions: Mapping[str, LandmarkAction] = DEFAULT_LANDMARK_ACTIONS,
) -> tuple[SceneLandmark, ...]:
    """Resolve manifest geometry only for explicitly registered actions.

    The native Garden uses its active surface variant at every window size;
    the actual home-screen preview remains inert.
    """

    if not interactive or not isinstance(placement, dict):
        return ()
    surface_profile = placement.get("surface_profile")
    if not isinstance(surface_profile, dict):
        return ()
    raw_landmarks = surface_profile.get("landmarks", [])
    if not isinstance(raw_landmarks, list):
        return ()

    variant_name, _variant = scene_surface_variant(placement, width, height, "dashboard")
    resolved: list[SceneLandmark] = []
    seen_ids: set[str] = set()
    for raw in raw_landmarks:
        if not isinstance(raw, dict):
            continue
        landmark_id = str(raw.get("landmark_id", "")).strip()
        action_id = str(raw.get("action_id", "")).strip()
        action = actions.get(action_id)
        if not landmark_id or landmark_id in seen_ids or action is None:
            continue
        role = str(raw.get("role", "button")).strip().lower()
        if role != "button":
            continue
        supported = raw.get("supported_variants", [])
        variants = raw.get("variants", {})
        geometry = variants.get(variant_name) if isinstance(variants, dict) else None
        if not isinstance(supported, list) or variant_name not in supported or not isinstance(geometry, dict):
            continue
        bounds = _normalized_bounds(geometry.get("bounds"))
        if bounds is None:
            continue
        polygon = _normalized_polygon(geometry.get("polygon"))
        outline_paths = _normalized_paths(geometry.get("outline_paths"))
        if not polygon or ("outline_paths" in geometry and not outline_paths):
            continue
        label_anchor = _normalized_point(geometry.get("label_anchor"))
        resolved.append(SceneLandmark(
            landmark_id=landmark_id,
            action_id=action_id,
            accessible_name=action.accessible_name,
            tooltip=action.tooltip,
            bounds=bounds,
            polygon=polygon,
            outline_paths=outline_paths,
            label_anchor=label_anchor,
        ))
        seen_ids.add(landmark_id)
    return tuple(resolved)


def project_landmark_bounds(
    landmark: SceneLandmark,
    *,
    width: float,
    height: float,
    source_aspect: float,
    focal: tuple[float, float],
    minimum_size: int = 44,
) -> tuple[int, int, int, int] | None:
    """Project normalized manifest bounds through the scene's cover crop."""

    scene_width = max(0, int(round(width)))
    scene_height = max(0, int(round(height)))
    if scene_width <= 0 or scene_height <= 0:
        return None
    left, top, span_width, span_height = landmark.bounds
    first = project_landmark_point(
        (left, top),
        width=width,
        height=height,
        source_aspect=source_aspect,
        focal=focal,
    )
    second = project_landmark_point(
        (left + span_width, top + span_height),
        width=width,
        height=height,
        source_aspect=source_aspect,
        focal=focal,
    )
    x1 = max(0, min(scene_width, math.floor(min(first[0], second[0]))))
    y1 = max(0, min(scene_height, math.floor(min(first[1], second[1]))))
    x2 = max(0, min(scene_width, math.ceil(max(first[0], second[0]))))
    y2 = max(0, min(scene_height, math.ceil(max(first[1], second[1]))))
    if x2 <= x1 or y2 <= y1:
        return None

    target_width = min(scene_width, max(max(1, int(minimum_size)), x2 - x1))
    target_height = min(scene_height, max(max(1, int(minimum_size)), y2 - y1))
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    x = max(0, min(scene_width - target_width, int(round(center_x - target_width / 2))))
    y = max(0, min(scene_height - target_height, int(round(center_y - target_height / 2))))
    return x, y, target_width, target_height


def project_landmark_polygon(
    landmark: SceneLandmark,
    *,
    width: float,
    height: float,
    source_aspect: float,
    focal: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    return tuple(
        project_landmark_point(
            point,
            width=width,
            height=height,
            source_aspect=source_aspect,
            focal=focal,
        )
        for point in landmark.polygon
    )


def project_landmark_outline_paths(
    landmark: SceneLandmark,
    *,
    width: float,
    height: float,
    source_aspect: float,
    focal: tuple[float, float],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Project visible-edge strokes without joining across painted occluders."""

    projected_paths: list[tuple[tuple[float, float], ...]] = []
    for path in landmark.outline_paths:
        projected: list[tuple[float, float]] = []
        for point in path:
            projected.append(project_landmark_point(
                point,
                width=width,
                height=height,
                source_aspect=source_aspect,
                focal=focal,
            ))
        projected_paths.append(tuple(projected))
    return tuple(projected_paths)


def _normalized_bounds(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        left, top, width, height = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(0.0 <= item <= 1.0 for item in (left, top, width, height)):
        return None
    if width <= 0.0 or height <= 0.0 or left + width > 1.0 or top + height > 1.0:
        return None
    return left, top, width, height


def _normalized_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return (x, y) if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 else None


def _normalized_polygon(value: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        return ()
    points = tuple(_normalized_point(item) for item in value)
    if len(points) < 3 or any(point is None for point in points):
        return ()
    area = sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])
    )
    return points if abs(area) > 1e-8 else ()


def _normalized_paths(value: Any) -> tuple[tuple[tuple[float, float], ...], ...]:
    if not isinstance(value, list):
        return ()
    paths: list[tuple[tuple[float, float], ...]] = []
    for raw_path in value:
        if not isinstance(raw_path, list):
            return ()
        points = tuple(_normalized_point(item) for item in raw_path)
        if len(points) < 2 or any(point is None for point in points):
            return ()
        paths.append(points)
    return tuple(paths)
