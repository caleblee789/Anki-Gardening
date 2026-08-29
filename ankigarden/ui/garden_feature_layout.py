from __future__ import annotations

from dataclasses import dataclass


FEATURE_ANCHOR_X = 0.215
FEATURE_GROUND_Y = 0.830
FEATURE_CANVAS_SCENE_HEIGHT = 0.250
ASSET_CONTACT_X = 0.500
ASSET_CONTACT_Y = 0.880
PAD_CENTER_X = 0.215
PAD_CENTER_Y = 0.842
PAD_WIDTH_SCENE_HEIGHT = 0.280
PAD_HEIGHT_SCENE_HEIGHT = 0.070
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
    pad: FeatureRect
    presentation_class: str


def garden_feature_layout(
    scene_width: float,
    scene_height: float,
    scenery_id: str,
) -> GardenFeatureLayout:
    width = max(1.0, float(scene_width))
    height = max(1.0, float(scene_height))
    size = height * FEATURE_CANVAS_SCENE_HEIGHT
    feature = FeatureRect(
        width * FEATURE_ANCHOR_X - size * ASSET_CONTACT_X,
        height * FEATURE_GROUND_Y - size * ASSET_CONTACT_Y,
        size,
        size,
    )
    pad_width = height * PAD_WIDTH_SCENE_HEIGHT
    pad_height = height * PAD_HEIGHT_SCENE_HEIGHT
    pad = FeatureRect(
        width * PAD_CENTER_X - pad_width * 0.5,
        height * PAD_CENTER_Y - pad_height * 0.5,
        pad_width,
        pad_height,
    )
    return GardenFeatureLayout(
        feature=feature,
        pad=pad,
        presentation_class=(
            "light" if str(scenery_id) in LIGHT_SCENERIES else "dark"
        ),
    )


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


def feature_css_variables(
    scene_width: float,
    scene_height: float,
    scenery_id: str,
) -> str:
    layout = garden_feature_layout(scene_width, scene_height, scenery_id)
    return ";".join((
        f"--ag-feature-left:{layout.feature.x:.4f}px",
        f"--ag-feature-top:{layout.feature.y:.4f}px",
        f"--ag-feature-size:{layout.feature.width:.4f}px",
        f"--ag-feature-pad-left:{layout.pad.x:.4f}px",
        f"--ag-feature-pad-top:{layout.pad.y:.4f}px",
        f"--ag-feature-pad-width:{layout.pad.width:.4f}px",
        f"--ag-feature-pad-height:{layout.pad.height:.4f}px",
    ))


__all__ = [name for name in globals() if name.isupper()] + [
    "FeatureRect",
    "GardenFeatureLayout",
    "background_cover_crop",
    "feature_css_variables",
    "garden_feature_layout",
]
