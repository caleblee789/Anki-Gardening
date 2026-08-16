"""Dependency-light contracts for native Garden dialogs.

The Qt implementation stays in :mod:`ankigarden.ui.dashboard` for backwards
compatibility with the add-on's existing surface classes.  These value objects
are intentionally independent from Qt so sizing and focus policy can be tested
without importing Anki.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DialogSizeClass(str, Enum):
    """Semantic size policies rather than screenshot-specific dimensions."""

    COMPACT_CONFIRMATION = "compact-confirmation"
    COMPARISON = "comparison"
    STANDARD_TEXT = "standard-text"
    CATALOG = "catalog"
    PREVIEW = "preview"


class InitialFocusPolicy(str, Enum):
    """The kind of control that should receive focus when a dialog opens."""

    AUTOMATIC = "automatic"
    SAFE_ACTION = "safe-action"
    FIRST_EDITABLE = "first-editable"
    SELECTED_ROUTE = "selected-route"
    EXPLICIT = "explicit"


class DialogViewState(str, Enum):
    """Shared asynchronous body states."""

    READY = "ready"
    LOADING = "loading"
    ERROR = "error"


@dataclass(frozen=True)
class DialogSizePolicy:
    min_width: int
    min_height: int
    preferred_width: int
    preferred_height: int
    max_width: int
    max_height: int
    width_ratio: float
    height_ratio: float
    grows_with_screen: bool = True


DIALOG_SIZE_POLICIES: dict[DialogSizeClass, DialogSizePolicy] = {
    DialogSizeClass.COMPACT_CONFIRMATION: DialogSizePolicy(
        360,
        280,
        480,
        300,
        520,
        520,
        0.82,
        0.78,
        False,
    ),
    DialogSizeClass.COMPARISON: DialogSizePolicy(
        420,
        400,
        720,
        560,
        820,
        660,
        0.88,
        0.86,
    ),
    DialogSizeClass.STANDARD_TEXT: DialogSizePolicy(
        480,
        400,
        760,
        620,
        960,
        820,
        0.86,
        0.88,
    ),
    DialogSizeClass.CATALOG: DialogSizePolicy(
        640,
        460,
        960,
        700,
        1200,
        900,
        0.92,
        0.90,
    ),
    DialogSizeClass.PREVIEW: DialogSizePolicy(
        680,
        480,
        1120,
        760,
        1280,
        960,
        0.94,
        0.92,
    ),
}


def resolved_dialog_size(
    size_class: DialogSizeClass,
    available_width: int,
    available_height: int,
    *,
    preferred_width: int | None = None,
    preferred_height: int | None = None,
) -> tuple[int, int]:
    """Resolve a logical client size inside the current screen.

    Large semantic dialogs may use otherwise idle screen area, while compact
    confirmations keep their deliberate maximum.  A screen smaller than the
    nominal minimum wins so the top-level window never becomes unreachable.
    """

    policy = DIALOG_SIZE_POLICIES[size_class]
    available_width = max(1, int(available_width))
    available_height = max(1, int(available_height))
    screen_width = max(1, int(available_width * policy.width_ratio))
    screen_height = max(1, int(available_height * policy.height_ratio))
    wanted_width = max(
        policy.min_width,
        int(preferred_width or policy.preferred_width),
    )
    wanted_height = max(
        policy.min_height,
        int(preferred_height or policy.preferred_height),
    )
    if policy.grows_with_screen:
        wanted_width = max(wanted_width, screen_width)
        wanted_height = max(wanted_height, screen_height)
    return (
        min(available_width, screen_width, policy.max_width, wanted_width),
        min(available_height, screen_height, policy.max_height, wanted_height),
    )


def text_column_width(average_character_width: int, characters: int = 68) -> int:
    """Return the shared readable line-length cap in logical pixels."""

    return max(1, int(average_character_width)) * max(1, int(characters))
