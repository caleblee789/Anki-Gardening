from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..balance_catalog import LANDMARK_BY_ID, MASTERY_RANK_BY_ID


def _asset_field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _catalog_asset_identity_matches(
    value: Any,
    *,
    category: str,
    logical_id: str,
    asset_id: str,
) -> bool:
    """Require one structured asset to match its frozen catalog identity."""

    if not value or not logical_id or not asset_id:
        return False
    metadata = _asset_field(value, "metadata")
    slot = metadata.get("slot") if isinstance(metadata, dict) else None
    return bool(
        str(_asset_field(value, "category") or "") == category
        and str(_asset_field(value, "asset_id") or "") == asset_id
        and isinstance(slot, dict)
        and str(slot.get("key") or "") == logical_id
    )


def landmark_asset_identity_matches(value: Any, landmark_id: str) -> bool:
    """Return whether artwork is the exact completed Landmark requested."""

    normalized = str(landmark_id or "")
    definition = LANDMARK_BY_ID.get(normalized)
    return bool(
        definition is not None
        and _catalog_asset_identity_matches(
            value,
            category="landmarks",
            logical_id=normalized,
            asset_id=str(definition.asset_id),
        )
    )


def mastery_asset_identity_matches(value: Any, rank_id: str) -> bool:
    """Return whether artwork is the exact claimed Mastery rank requested."""

    normalized = str(rank_id or "")
    definition = MASTERY_RANK_BY_ID.get(normalized)
    return bool(
        definition is not None
        and _catalog_asset_identity_matches(
            value,
            category="mastery",
            logical_id=normalized,
            asset_id=str(definition.asset_id),
        )
    )


@dataclass(frozen=True)
class LandmarkSceneAnchor:
    """One normalized, presentation-only Garden Landmark scene anchor."""

    left: float
    top: float
    width: float
    height: float

    def project(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> tuple[float, float, float, float]:
        return (
            x + width * self.left,
            y + height * self.top,
            width * self.width,
            height * self.height,
        )

    @property
    def identity(self) -> str:
        return (
            f"{self.left:.3f},{self.top:.3f},"
            f"{self.width:.3f},{self.height:.3f}"
        )


# The live Garden and Collection preview share the rear lawn, above the first
# bed row. Low garden features should read as ground details; structures need
# more height. The path sits slightly forward in the gap between beds so its
# far end stays on the ground plane. Low ground surfaces receive perspective
# compression; upright structures preserve their source proportions. These
# are display coordinates,
# independent of construction progress and the existing plant/bed geometry.
GARDEN_LANDMARK_ANCHOR = LandmarkSceneAnchor(
    left=0.38,
    top=0.055,
    width=0.24,
    height=0.32,
)

GARDEN_LANDMARK_ANCHORS = MappingProxyType({
    landmark_id: LandmarkSceneAnchor(
        left=0.38,
        top=(0.40 if landmark_id == "mossy_stone_path" else 0.375) - height,
        width=0.24,
        height=height,
    )
    for landmark_id, height in (
        ("mossy_stone_path", 0.23),
        ("birdbath_terrace", 0.23),
        ("lily_pond", 0.20),
        ("wooden_footbridge", 0.22),
        ("garden_pergola", 0.30),
        ("glasshouse_conservatory", 0.32),
    )
})


def landmark_scene_lighting(scenery_id: str) -> tuple[float, float]:
    """Return brightness and saturation for artwork on the distant lawn.

    This is presentation lighting, never transparency: opaque stone, water,
    and building pixels continue to occlude the scenery behind them. Native
    paint and Home's CSS use the same values; catalog thumbnails stay neutral.
    """
    return {
        "default": (0.78, 0.80),
        "spring": (0.96, 0.95),
        "summer": (0.98, 0.98),
        "autumn": (0.90, 0.86),
        "snowy": (0.95, 0.64),
        "rainbow_horizon": (0.97, 0.90),
        "halloween": (0.66, 0.74),
        "full_moon": (0.60, 0.60),
        "eclipse": (0.55, 0.70),
    }.get(str(scenery_id), (0.78, 0.80))


def project_garden_landmark_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    landmark_id: str = "",
) -> tuple[float, float, float, float]:
    anchor = GARDEN_LANDMARK_ANCHORS.get(str(landmark_id), GARDEN_LANDMARK_ANCHOR)
    return anchor.project(x, y, width, height)


def landmark_ground_compression(landmark_id: str) -> float:
    """Match low ground features to the scene's shallow viewing angle."""
    return {
        "mossy_stone_path": 0.48,
        "lily_pond": 0.58,
    }.get(str(landmark_id), 1.0)


def project_landmark_artwork_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    landmark_id: str,
) -> tuple[float, float, float, float]:
    """Fit each square source, then project ground art about its contact line.

    The Path and Pond keep a readable horizontal footprint instead of being
    reduced until their camera-angle mismatch is difficult to see. Upright
    landmarks retain the ordinary contain fit. Callers paint directly into
    this rectangle; a second contain fit would undo the ground projection.
    """
    left, top, box_width, box_height = project_garden_landmark_rect(
        x, y, width, height, landmark_id,
    )
    side = min(box_width, box_height)
    compression = landmark_ground_compression(landmark_id)
    return (
        left + (box_width - side) / 2,
        top + (box_height - side) / 2 + side * (1.0 - compression),
        side,
        side * compression,
    )


def project_landmark_contact_shadow_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    landmark_id: str,
) -> tuple[float, float, float, float]:
    """Place a restrained contact shadow beneath the existing cutout's base.

    All six frozen Landmark files have square canvases. Their base offsets
    account for transparent bottom padding and the diagonal stone path, and
    follow the same ground projection as the artwork.
    """
    draw_left, draw_top, draw_width, draw_height = project_landmark_artwork_rect(
        x, y, width, height, landmark_id,
    )
    offset_x, offset_y, shadow_width, shadow_height = {
        "mossy_stone_path": (0.06, 0.84, 0.64, 0.13),
        "birdbath_terrace": (0.13, 0.80, 0.76, 0.12),
        "lily_pond": (0.12, 0.85, 0.78, 0.12),
        "wooden_footbridge": (0.15, 0.84, 0.74, 0.14),
        "garden_pergola": (0.20, 0.87, 0.68, 0.12),
        "glasshouse_conservatory": (0.25, 0.87, 0.72, 0.12),
    }.get(str(landmark_id), (0.15, 0.86, 0.70, 0.12))
    return (
        draw_left + draw_width * offset_x,
        draw_top + draw_height * offset_y,
        draw_width * shadow_width,
        draw_height * shadow_height,
    )


__all__ = [
    "GARDEN_LANDMARK_ANCHOR",
    "GARDEN_LANDMARK_ANCHORS",
    "LandmarkSceneAnchor",
    "landmark_asset_identity_matches",
    "landmark_ground_compression",
    "landmark_scene_lighting",
    "mastery_asset_identity_matches",
    "project_garden_landmark_rect",
    "project_landmark_artwork_rect",
    "project_landmark_contact_shadow_rect",
]
