from __future__ import annotations

from dataclasses import dataclass


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
        """Project the shared anchor into any rendering canvas."""

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


# Home and the main 3:2 Garden project this exact normalized rectangle.  It is
# centred on the open rear lawn so every completed tier replaces the previous
# appearance without moving the scene's six plant beds or interactive landmarks.
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
