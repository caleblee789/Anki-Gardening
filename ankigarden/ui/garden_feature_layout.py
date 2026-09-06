from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FEATURE_ANCHOR_X = 0.215
FEATURE_GROUND_Y = 0.830
FEATURE_CANVAS_SCENE_HEIGHT = 0.250
ASSET_CONTACT_X = 0.500
ASSET_CONTACT_Y = 0.880
# The fourth V6 bed is the only interactive bed that can enter the complete
# feature-canvas reserve. Its canonical 3:2 anchor begins beyond this boundary.
FEATURE_BAY_NEAR_LEFT_BED_X = 0.390
NATIVE_SCENE_ASPECT = 3.0 / 2.0
BACKGROUND_SOURCE_ASPECT = 4.0 / 3.0
BACKGROUND_FOCAL_X = 0.500
BACKGROUND_FOCAL_Y = 0.480

LIGHT_SCENERIES = frozenset({
    "spring",
    "summer",
    "autumn",
    "snowy",
    "rainbow_horizon",
})
DARK_SCENERIES = frozenset({
    "default",
    "halloween",
    "full_moon",
    "eclipse",
})


@dataclass(frozen=True)
class FeatureRect:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class GardenFeatureLayout:
    feature: FeatureRect
    shadow: FeatureRect
    presentation_class: str
    shadow_opacity: float


def garden_feature_layout(
    scene_width: float,
    scene_height: float,
    scenery_id: str,
    placement: Mapping[str, Any] | None = None,
) -> GardenFeatureLayout:
    """Project the authored physical support, never the sprite's alpha bottom."""
    width = max(1.0, float(scene_width))
    height = max(1.0, float(scene_height))
    metadata = placement or {}
    contact_x, contact_y = metadata.get("ground_anchor", (ASSET_CONTACT_X, ASSET_CONTACT_Y))
    scale = float(metadata.get("display_scale", 1.0))
    size = height * FEATURE_CANVAS_SCENE_HEIGHT * scale
    feature = FeatureRect(
        width * FEATURE_ANCHOR_X - size * contact_x,
        height * FEATURE_GROUND_Y - size * contact_y,
        size, size,
    )
    shadow_width, shadow_height = metadata.get("contact_shadow", (.34, .05))
    offset_x, offset_y = metadata.get("shadow_offset", (0.0, 0.0))
    shadow = FeatureRect(
        width * FEATURE_ANCHOR_X + size * (offset_x - shadow_width / 2),
        height * FEATURE_GROUND_Y + size * (offset_y - shadow_height / 2),
        size * shadow_width, size * shadow_height,
    )
    light = str(scenery_id) in LIGHT_SCENERIES
    return GardenFeatureLayout(feature, shadow, "light" if light else "dark", .28 if light else .38)


def background_cover_crop(
    scene_width: float,
    scene_height: float,
    *,
    source_aspect: float = BACKGROUND_SOURCE_ASPECT,
) -> FeatureRect:
    """Return the shared 4:3 cover target for a visible scene container."""

    width = max(1.0, float(scene_width))
    height = max(1.0, float(scene_height))
    scene_aspect = width / height
    if scene_aspect >= source_aspect:
        draw_width = width
        draw_height = width / source_aspect
    else:
        draw_height = height
        draw_width = height * source_aspect
    return FeatureRect(
        -(draw_width - width) * BACKGROUND_FOCAL_X,
        -(draw_height - height) * BACKGROUND_FOCAL_Y,
        draw_width,
        draw_height,
    )



__all__ = [name for name in globals() if name.isupper()] + [
    "FeatureRect",
    "GardenFeatureLayout",
    "background_cover_crop",
    "garden_feature_layout",
]
