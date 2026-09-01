from __future__ import annotations

from dataclasses import dataclass
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


# Home, the live Garden, and the Garden Appearance preview use this same rear
# lawn rectangle. A newly completed tier replaces the prior appearance without
# moving any plant bed or interactive navigation landmark.
GARDEN_LANDMARK_ANCHOR = LandmarkSceneAnchor(
    left=0.36,
    top=0.18,
    width=0.28,
    height=0.52,
)


def project_garden_landmark_rect(
    x: float,
    y: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    return GARDEN_LANDMARK_ANCHOR.project(x, y, width, height)


__all__ = [
    "GARDEN_LANDMARK_ANCHOR",
    "LandmarkSceneAnchor",
    "landmark_asset_identity_matches",
    "mastery_asset_identity_matches",
    "project_garden_landmark_rect",
]
