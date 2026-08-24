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
        "Details changed. Review them before continuing.",
        "warning",
        retryable=True,
    ),
    DialogViewState.BUSINESS_RULE_BLOCKED: DialogViewPolicy(
        "This action is not available.",
        "warning",
    ),
    DialogViewState.RECOVERABLE_FAILURE: DialogViewPolicy(
        "Couldn’t finish that action. Try again.",
        "error",
        retryable=True,
        assertive=True,
    ),
    DialogViewState.PERSISTENCE_FAILURE: DialogViewPolicy(
        "Couldn’t save changes. Nothing was changed.",
        "error",
        retryable=True,
        assertive=True,
    ),
    DialogViewState.SUCCESS: DialogViewPolicy(
        "Saved.",
        "success",
    ),
    DialogViewState.ERROR: DialogViewPolicy(
        "Couldn’t load this view.",
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


@dataclass(frozen=True)
class ScrollbarTelemetryRecord:
    """Capture-facing state for one deliberate dialog scroll region."""

    name: str
    minimum: int
    maximum: int
    value: int
    visible: bool
    overflow_owner: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "value": self.value,
            "visible": self.visible,
            "overflowOwner": self.overflow_owner,
        }


@dataclass(frozen=True)
class DialogCaptureTelemetryRecord:
    """Stable native geometry/text evidence consumed by capture QA.

    The Qt shell owns measurement; this dependency-light value object keeps
    capture code from having to rediscover widget conventions or duplicate
    threshold logic.
    """

    client_surface_fill: float
    nursery_root_offset: int | None
    content_to_footer_gap: int | None
    maximum_action_width_ratio: float
    scrollbars: tuple[ScrollbarTelemetryRecord, ...]
    minimum_rendered_text_size: float | None
    tooltip_widget_count: int
    elided_widget_count: int
    elision_without_tooltip_count: int
    overflow_owner_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "clientSurfaceFill": self.client_surface_fill,
            "nurseryRootOffset": self.nursery_root_offset,
            "contentToFooterGap": self.content_to_footer_gap,
            "maximumActionWidthRatio": self.maximum_action_width_ratio,
            "scrollbars": [record.as_dict() for record in self.scrollbars],
            "minimumRenderedTextSize": self.minimum_rendered_text_size,
            "tooltipWidgetCount": self.tooltip_widget_count,
            "elidedWidgetCount": self.elided_widget_count,
            "elisionWithoutTooltipCount": self.elision_without_tooltip_count,
            "overflowOwnerCount": self.overflow_owner_count,
        }


def merge_content_fit_preservation(
    current: bool | None,
    requested: bool | None,
) -> bool | None:
    """Coalesce transition intent with terminal shrink taking precedence."""

    if current is False or requested is False:
        return False
    if current is True or requested is True:
        return True
    return None


def should_preserve_transition_height(
    *,
    policy_enabled: bool,
    in_flight: bool,
    requested: bool | None,
    preserved_height: int,
) -> bool:
    """Limit fixed-height preservation to an intentional in-flight state."""

    return bool(
        policy_enabled
        and in_flight
        and requested is not False
        and int(preserved_height) > 0
    )


DIALOG_SIZE_POLICIES: dict[DialogSizeClass, DialogSizePolicy] = {
    DialogSizeClass.COMPACT_STATUS: DialogSizePolicy(
        500,
        200,
        520,
        220,
        540,
        250,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.TRANSACTION: DialogSizePolicy(
        480,
        180,
        540,
        250,
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
        250,
        720,
        430,
        740,
        470,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.SETTINGS: DialogSizePolicy(
        820,
        330,
        900,
        490,
        920,
        590,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.NURSERY: DialogSizePolicy(
        920,
        300,
        950,
        540,
        980,
        600,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.PROGRESS: DialogSizePolicy(
        960,
        350,
        980,
        540,
        1000,
        650,
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
        560,
        840,
        595,
        860,
        630,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.SPECIES_DETAIL: DialogSizePolicy(
        880,
        430,
        920,
        600,
        940,
        620,
        1.0,
        1.0,
        False,
        True,
    ),
    DialogSizeClass.GROWTH_CHARGE: DialogSizePolicy(
        520,
        180,
        540,
        315,
        560,
        340,
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
        "default": DialogHeightProfile(200, 220, 250, 500, 520, 540),
    },
    DialogSizeClass.TRANSACTION: {
        "default": DialogHeightProfile(220, 245, 270, 500, 520, 540),
        "simple": DialogHeightProfile(220, 245, 270, 500, 520, 540),
        "complex": DialogHeightProfile(250, 295, 340, 540, 570, 600),
        "loading": DialogHeightProfile(220, 245, 270, 500, 520, 540),
        "warning": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "error": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "success": DialogHeightProfile(180, 210, 240, 480, 510, 540),
    },
    DialogSizeClass.FERTILIZER: {
        "default": DialogHeightProfile(390, 430, 470, 700, 720, 740),
        "selection": DialogHeightProfile(390, 430, 470, 700, 720, 740),
        "replacement": DialogHeightProfile(250, 275, 300, 560, 590, 620),
    },
    DialogSizeClass.SETTINGS: {
        "display": DialogHeightProfile(460, 485, 510, 880, 900, 920),
        "advanced": DialogHeightProfile(540, 565, 590, 880, 900, 920),
        "diagnostics-clean": DialogHeightProfile(330, 360, 390, 820, 880, 900),
        "diagnostics-warning": DialogHeightProfile(360, 390, 420, 820, 880, 900),
        "diagnostics-expanded": DialogHeightProfile(500, 545, 590, 820, 880, 900),
    },
    DialogSizeClass.NURSERY: {
        "starter": DialogHeightProfile(500, 550, 600, 920, 950, 980),
        "plants": DialogHeightProfile(540, 570, 600),
        "owned": DialogHeightProfile(470, 500, 530),
        "fertilizer": DialogHeightProfile(470, 500, 530),
        "spaces": DialogHeightProfile(380, 405, 430),
        "weather": DialogHeightProfile(480, 510, 540),
        "empty": DialogHeightProfile(300, 335, 370),
    },
    DialogSizeClass.PROGRESS: {
        "growth": DialogHeightProfile(520, 540, 560),
        "streak": DialogHeightProfile(560, 585, 610),
        "currency": DialogHeightProfile(360, 390, 420),
        "achievements": DialogHeightProfile(600, 625, 650),
        "collection": DialogHeightProfile(540, 570, 600),
        "collection-empty": DialogHeightProfile(350, 380, 410),
    },
    DialogSizeClass.LOADOUT: {
        "default": DialogHeightProfile(560, 610, 650, 1000, 1020, 1040),
    },
    DialogSizeClass.PLANT_STORY: {
        "default": DialogHeightProfile(560, 595, 630, 800, 840, 860),
    },
    DialogSizeClass.SPECIES_DETAIL: {
        "default": DialogHeightProfile(580, 600, 620, 880, 920, 940),
        "collected": DialogHeightProfile(580, 600, 620, 880, 920, 940),
        "uncollected": DialogHeightProfile(430, 455, 480, 880, 920, 940),
    },
    DialogSizeClass.GROWTH_CHARGE: {
        "ready": DialogHeightProfile(290, 315, 340, 520, 540, 560),
        "loading": DialogHeightProfile(290, 315, 340, 520, 540, 560),
        "stale": DialogHeightProfile(290, 315, 340, 520, 540, 560),
        "empty": DialogHeightProfile(190, 210, 230, 520, 540, 560),
        "warning": DialogHeightProfile(180, 210, 240, 520, 540, 560),
        "error": DialogHeightProfile(180, 210, 240, 520, 540, 560),
        "success": DialogHeightProfile(260, 290, 320, 520, 540, 560),
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
