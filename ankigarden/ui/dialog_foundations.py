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

    COMPACT_STATUS = "compact-status"
    TRANSACTION = "transaction"
    FERTILIZER = "fertilizer"
    SETTINGS = "settings"
    NURSERY = "nursery"
    PROGRESS = "progress"
    LOADOUT = "loadout"
    PLANT_STORY = "plant-story"
    SPECIES_DETAIL = "species-detail"
    GROWTH_CHARGE = "growth-charge"
    GARDEN_WORKSPACE = "garden-workspace"

    # Compatibility families remain available while feature call sites move
    # to the release-specific policies above.  Aliases intentionally share a
    # single policy rather than retaining duplicate geometry authorities.
    COMPACT_CONFIRMATION = "compact-status"
    COMPARISON = "transaction"
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
    """Shared dialog presentation states.

    ``LOADING`` and ``ERROR`` remain as compatibility states for existing
    non-transaction dialogs. New transaction surfaces should use the more
    precise validating, committing, stale, blocked, and failure states.
    """

    READY = "ready"
    VALIDATING = "validating"
    COMMITTING = "committing"
    LOADING = "loading"
    STALE_PROPOSAL = "stale-proposal"
    BUSINESS_RULE_BLOCKED = "business-rule-blocked"
    RECOVERABLE_FAILURE = "recoverable-failure"
    PERSISTENCE_FAILURE = "persistence-failure"
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True)
class DialogViewPolicy:
    """Presentation metadata shared by generic and specialized dialogs."""

    fallback_message: str
    feedback_tone: str
    busy: bool = False
    retryable: bool = False
    assertive: bool = False


DIALOG_VIEW_POLICIES: dict[DialogViewState, DialogViewPolicy] = {
    DialogViewState.READY: DialogViewPolicy("", "neutral"),
    DialogViewState.VALIDATING: DialogViewPolicy(
        "Checking the latest details…",
        "loading",
        busy=True,
    ),
    DialogViewState.COMMITTING: DialogViewPolicy(
        "Saving changes…",
        "loading",
        busy=True,
    ),
    DialogViewState.LOADING: DialogViewPolicy(
        "Loading…",
        "loading",
        busy=True,
    ),
    DialogViewState.STALE_PROPOSAL: DialogViewPolicy(
        "The proposal changed. Review the latest details before continuing.",
        "warning",
        retryable=True,
    ),
    DialogViewState.BUSINESS_RULE_BLOCKED: DialogViewPolicy(
        "This action is not available.",
        "warning",
    ),
    DialogViewState.RECOVERABLE_FAILURE: DialogViewPolicy(
        "This action could not be completed. Try again.",
        "error",
        retryable=True,
        assertive=True,
    ),
    DialogViewState.PERSISTENCE_FAILURE: DialogViewPolicy(
        "Changes could not be saved. The committed state is unchanged.",
        "error",
        retryable=True,
        assertive=True,
    ),
    DialogViewState.SUCCESS: DialogViewPolicy(
        "Saved successfully.",
        "success",
    ),
    DialogViewState.ERROR: DialogViewPolicy(
        "This view could not be loaded.",
        "error",
        retryable=True,
        assertive=True,
    ),
}


def dialog_view_policy(state: DialogViewState | str) -> DialogViewPolicy:
    """Return semantic presentation metadata for a dialog state."""

    return DIALOG_VIEW_POLICIES[DialogViewState(state)]


class DialogCloseReason(str, Enum):
    """Stable origins for a dismiss request."""

    PROGRAMMATIC = "programmatic"
    CLOSE_BUTTON = "close-button"
    ESCAPE = "escape"
    WINDOW_CLOSE = "window-close"
    CANCEL_ACTION = "cancel-action"


class DialogCloseBlocker(str, Enum):
    """Conditions that can prevent a dialog from being dismissed."""

    DIRTY = "dirty"
    IN_FLIGHT = "in-flight"


@dataclass(frozen=True)
class DialogClosePolicy:
    """Opt-in safeguards for dismissing a dialog."""

    protect_dirty: bool = False
    protect_in_flight: bool = False


@dataclass(frozen=True)
class DialogCloseDecision:
    """Resolved outcome of one close request."""

    reason: DialogCloseReason
    allowed: bool
    blocked_by: DialogCloseBlocker | None = None


def resolve_dialog_close(
    policy: DialogClosePolicy,
    reason: DialogCloseReason | str,
    *,
    dirty: bool = False,
    in_flight: bool = False,
    dirty_confirmed: bool = False,
) -> DialogCloseDecision:
    """Resolve close safety without importing Qt or performing UI work.

    In-flight work takes precedence over dirty-state confirmation because a
    confirmed discard must not make an unsafe commit cancellable.
    """

    reason = DialogCloseReason(reason)
    if policy.protect_in_flight and in_flight:
        return DialogCloseDecision(
            reason,
            allowed=False,
            blocked_by=DialogCloseBlocker.IN_FLIGHT,
        )
    if policy.protect_dirty and dirty and not dirty_confirmed:
        return DialogCloseDecision(
            reason,
            allowed=False,
            blocked_by=DialogCloseBlocker.DIRTY,
        )
    return DialogCloseDecision(reason, allowed=True)


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
    content_fit: bool = False
    screen_margin: int = 24
    preserve_transition_height: bool = False


@dataclass(frozen=True)
class DialogHeightProfile:
    """Content-fit geometry range for one view within a dialog family."""

    min_height: int
    preferred_height: int
    max_height: int
    min_width: int | None = None
    preferred_width: int | None = None
    max_width: int | None = None

    def __post_init__(self) -> None:
        if not (
            0 < self.min_height <= self.preferred_height <= self.max_height
        ):
            raise ValueError("dialog height profiles must be ordered and positive")
        widths = (self.min_width, self.preferred_width, self.max_width)
        if any(value is not None for value in widths):
            if not all(value is not None for value in widths):
                raise ValueError("dialog view width profiles must be complete")
            if not (
                0
                < int(self.min_width or 0)
                <= int(self.preferred_width or 0)
                <= int(self.max_width or 0)
            ):
                raise ValueError("dialog view width profiles must be ordered and positive")


DIALOG_SIZE_POLICIES: dict[DialogSizeClass, DialogSizePolicy] = {
    DialogSizeClass.COMPACT_STATUS: DialogSizePolicy(
        500,
        220,
        540,
        250,
        580,
        280,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.TRANSACTION: DialogSizePolicy(
        520,
        210,
        560,
        290,
        600,
        340,
        1.0,
        1.0,
        False,
        True,
        24,
        True,
    ),
    DialogSizeClass.FERTILIZER: DialogSizePolicy(
        700,
        420,
        720,
        480,
        740,
        520,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.SETTINGS: DialogSizePolicy(
        880,
        400,
        900,
        540,
        920,
        580,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.NURSERY: DialogSizePolicy(
        920,
        330,
        950,
        560,
        980,
        680,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.PROGRESS: DialogSizePolicy(
        960,
        430,
        980,
        620,
        1000,
        720,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.LOADOUT: DialogSizePolicy(
        1000,
        560,
        1020,
        610,
        1040,
        650,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.PLANT_STORY: DialogSizePolicy(
        800,
        540,
        840,
        570,
        860,
        600,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.SPECIES_DETAIL: DialogSizePolicy(
        880,
        580,
        920,
        620,
        940,
        650,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.GROWTH_CHARGE: DialogSizePolicy(
        540,
        220,
        560,
        340,
        580,
        380,
        1.0,
        1.0,
        False,
        True,
        24,
        True,
    ),
    DialogSizeClass.GARDEN_WORKSPACE: DialogSizePolicy(
        900,
        640,
        1240,
        840,
        1600,
        1100,
        1.0,
        1.0,
        False,
    ),
    # Legacy generic policies remain for secondary dialogs that are outside
    # the named release families. They are deliberately not used by Settings,
    # Nursery, Progress, loadout, fertilizer, or transaction surfaces.
    DialogSizeClass.STANDARD_TEXT: DialogSizePolicy(
        480,
        320,
        760,
        560,
        960,
        760,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.CATALOG: DialogSizePolicy(
        640,
        460,
        960,
        700,
        1200,
        900,
        1.0,
        1.0,
        False,
    ),
    DialogSizeClass.PREVIEW: DialogSizePolicy(
        680,
        480,
        1120,
        760,
        1280,
        960,
        1.0,
        1.0,
        False,
    ),
}


DIALOG_VIEW_HEIGHT_PROFILES: dict[
    DialogSizeClass,
    dict[str, DialogHeightProfile],
] = {
    DialogSizeClass.COMPACT_STATUS: {
        "default": DialogHeightProfile(220, 250, 260, 500, 520, 540),
    },
    DialogSizeClass.TRANSACTION: {
        "simple": DialogHeightProfile(250, 280, 320, 520, 540, 560),
        "complex": DialogHeightProfile(280, 320, 340, 560, 580, 600),
        "error": DialogHeightProfile(210, 245, 280, 520, 540, 560),
    },
    DialogSizeClass.FERTILIZER: {
        "default": DialogHeightProfile(420, 480, 520, 700, 720, 740),
    },
    DialogSizeClass.SETTINGS: {
        "display": DialogHeightProfile(460, 520, 560, 880, 900, 920),
        "advanced": DialogHeightProfile(520, 550, 580, 880, 900, 920),
        "diagnostics-clean": DialogHeightProfile(400, 440, 500, 880, 900, 920),
        "diagnostics-expanded": DialogHeightProfile(500, 540, 580, 880, 900, 920),
    },
    DialogSizeClass.NURSERY: {
        "starter": DialogHeightProfile(500, 540, 580, 920, 950, 980),
        "plants": DialogHeightProfile(540, 610, 680),
        "fertilizer": DialogHeightProfile(500, 570, 640),
        "spaces": DialogHeightProfile(420, 470, 520),
        "weather": DialogHeightProfile(500, 570, 640),
        "empty": DialogHeightProfile(330, 365, 400),
    },
    DialogSizeClass.PROGRESS: {
        "growth": DialogHeightProfile(560, 620, 680),
        "streak": DialogHeightProfile(580, 640, 700),
        "currency": DialogHeightProfile(480, 540, 600),
        "achievements": DialogHeightProfile(600, 670, 720),
        "collection": DialogHeightProfile(540, 620, 700),
        "collection-empty": DialogHeightProfile(330, 380, 430),
    },
    DialogSizeClass.LOADOUT: {
        "default": DialogHeightProfile(560, 610, 650, 1000, 1020, 1040),
    },
    DialogSizeClass.PLANT_STORY: {
        "default": DialogHeightProfile(540, 570, 600, 800, 840, 860),
    },
    DialogSizeClass.SPECIES_DETAIL: {
        "default": DialogHeightProfile(580, 620, 650, 880, 920, 940),
    },
    DialogSizeClass.GROWTH_CHARGE: {
        "ready": DialogHeightProfile(300, 340, 380, 540, 560, 580),
        "empty": DialogHeightProfile(230, 250, 270, 540, 560, 580),
        "loading": DialogHeightProfile(300, 340, 380, 540, 560, 580),
        "error": DialogHeightProfile(220, 250, 280, 540, 560, 580),
        "success": DialogHeightProfile(300, 340, 380, 540, 560, 580),
    },
}


def dialog_height_profile(
    size_class: DialogSizeClass,
    view_key: str | None = None,
) -> DialogHeightProfile:
    """Resolve a view-specific content-fit range with a family fallback."""

    policy = DIALOG_SIZE_POLICIES[size_class]
    fallback = DialogHeightProfile(
        policy.min_height,
        policy.preferred_height,
        policy.max_height,
    )
    profiles = DIALOG_VIEW_HEIGHT_PROFILES.get(size_class, {})
    if not profiles:
        return fallback
    key = str(view_key or "default").strip().lower()
    return profiles.get(key) or profiles.get("default") or fallback


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
    usable_width = max(1, available_width - (policy.screen_margin * 2))
    usable_height = max(1, available_height - (policy.screen_margin * 2))
    screen_width = max(1, int(usable_width * policy.width_ratio))
    screen_height = max(1, int(usable_height * policy.height_ratio))
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
        min(usable_width, screen_width, policy.max_width, wanted_width),
        min(usable_height, screen_height, policy.max_height, wanted_height),
    )


def text_column_width(average_character_width: int, characters: int = 68) -> int:
    """Return the shared readable line-length cap in logical pixels."""

    return max(1, int(average_character_width)) * max(1, int(characters))
