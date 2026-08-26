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


class DialogWindowMode(str, Enum):
    """Top-level native geometry behavior shared by every dialog family."""

    CANVAS = "canvas"
    WORKSPACE = "workspace"
    CONTENT = "content"


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
class DialogSizeProfile:
    """Content-driven bounds plus the top-level native window behavior."""

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
    window_mode: DialogWindowMode = DialogWindowMode.CONTENT

    def __post_init__(self) -> None:
        if not (
            0 < self.min_width <= self.preferred_width <= self.max_width
            and 0 < self.min_height <= self.preferred_height <= self.max_height
        ):
            raise ValueError("dialog size profiles must use ordered positive bounds")
        if not (0 < self.width_ratio <= 1 and 0 < self.height_ratio <= 1):
            raise ValueError("dialog size profile screen ratios must be in (0, 1]")
        if self.screen_margin < 0:
            raise ValueError("dialog size profile screen margin may not be negative")
        if self.window_mode is DialogWindowMode.CANVAS and self.content_fit:
            raise ValueError("canvas windows cannot use content-fit sizing")


# Source-compatible name retained for integrations that imported the v23 type.
DialogSizePolicy = DialogSizeProfile


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
class DialogGeometryTelemetryRecord:
    """One widget rectangle expressed in top-level client coordinates."""

    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
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
    window_mode: str = DialogWindowMode.CONTENT.value
    client_bounds: DialogGeometryTelemetryRecord | None = None
    body_bounds: DialogGeometryTelemetryRecord | None = None
    footer_bounds: DialogGeometryTelemetryRecord | None = None
    settled_size: tuple[int, int] | None = None
    content_fit_pending: bool = False
    safety_scroll_active: bool = False

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
            "windowMode": self.window_mode,
            "clientBounds": (
                self.client_bounds.as_dict()
                if self.client_bounds is not None
                else None
            ),
            "bodyBounds": (
                self.body_bounds.as_dict()
                if self.body_bounds is not None
                else None
            ),
            "footerBounds": (
                self.footer_bounds.as_dict()
                if self.footer_bounds is not None
                else None
            ),
            "settledSize": (
                {
                    "width": int(self.settled_size[0]),
                    "height": int(self.settled_size[1]),
                }
                if self.settled_size is not None
                else None
            ),
            "contentFitPending": self.content_fit_pending,
            "safetyScrollActive": self.safety_scroll_active,
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


DIALOG_SIZE_POLICIES: dict[DialogSizeClass, DialogSizeProfile] = {
    DialogSizeClass.COMPACT_STATUS: DialogSizePolicy(
        460,
        150,
        500,
        190,
        520,
        260,
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
        640,
        240,
        660,
        360,
        680,
        520,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.SETTINGS: DialogSizePolicy(
        800,
        480,
        820,
        510,
        840,
        520,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.NURSERY: DialogSizePolicy(
        925,
        300,
        940,
        420,
        950,
        560,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.PROGRESS: DialogSizePolicy(
        940,
        560,
        950,
        570,
        960,
        580,
        1.0,
        1.0,
        False,
        False,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.LOADOUT: DialogSizePolicy(
        980,
        520,
        1000,
        540,
        1020,
        560,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.PLANT_STORY: DialogSizePolicy(
        740,
        480,
        760,
        500,
        780,
        520,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.SPECIES_DETAIL: DialogSizePolicy(
        800,
        520,
        820,
        550,
        840,
        570,
        1.0,
        1.0,
        False,
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.GROWTH_CHARGE: DialogSizePolicy(
        480,
        220,
        500,
        270,
        510,
        290,
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
        window_mode=DialogWindowMode.CANVAS,
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
        window_mode=DialogWindowMode.WORKSPACE,
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
        window_mode=DialogWindowMode.WORKSPACE,
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
        window_mode=DialogWindowMode.WORKSPACE,
    ),
}


DIALOG_VIEW_HEIGHT_PROFILES: dict[
    DialogSizeClass,
    dict[str, DialogHeightProfile],
] = {
    DialogSizeClass.COMPACT_STATUS: {
        "default": DialogHeightProfile(180, 200, 210, 480, 500, 520),
    },
    DialogSizeClass.TRANSACTION: {
        "default": DialogHeightProfile(210, 230, 250, 480, 500, 520),
        "simple": DialogHeightProfile(210, 230, 250, 480, 500, 520),
        # The Growth Charge quote is the smallest complete purchase: one
        # artwork row, one cost row, and its actions.  Keep that proposal a
        # true content-fit window instead of inheriting taller catalog states.
        "growth-charge": DialogHeightProfile(220, 230, 240, 500, 500, 500),
        "replacement": DialogHeightProfile(230, 260, 290, 500, 520, 540),
        "complex": DialogHeightProfile(250, 295, 340, 540, 570, 600),
        "loading": DialogHeightProfile(210, 230, 250, 480, 500, 520),
        "warning": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "error": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "success": DialogHeightProfile(180, 210, 240, 480, 510, 540),
    },
    DialogSizeClass.FERTILIZER: {
        "default": DialogHeightProfile(420, 440, 480, 640, 660, 680),
        "selection": DialogHeightProfile(420, 440, 480, 640, 660, 680),
        "replacement": DialogHeightProfile(230, 260, 290, 500, 520, 540),
    },
    DialogSizeClass.SETTINGS: {
        "display": DialogHeightProfile(480, 500, 520, 800, 820, 840),
        "advanced": DialogHeightProfile(500, 510, 520, 800, 820, 840),
        "diagnostics-clean": DialogHeightProfile(280, 300, 320, 760, 780, 800),
        "diagnostics-warning": DialogHeightProfile(280, 300, 320, 760, 780, 800),
        "diagnostics-expanded": DialogHeightProfile(430, 470, 520, 760, 780, 800),
    },
    DialogSizeClass.NURSERY: {
        "starter": DialogHeightProfile(400, 420, 440, 925, 940, 950),
        "plants": DialogHeightProfile(300, 360, 520, 925, 940, 950),
        "owned": DialogHeightProfile(470, 500, 530),
        "fertilizer": DialogHeightProfile(540, 550, 560, 925, 940, 950),
        "spaces": DialogHeightProfile(300, 325, 330, 925, 940, 950),
        "weather": DialogHeightProfile(360, 460, 560, 925, 940, 950),
        "collection-complete": DialogHeightProfile(300, 315, 330, 925, 940, 950),
        "collection-complete-receipt": DialogHeightProfile(370, 385, 410, 925, 940, 950),
        "empty": DialogHeightProfile(300, 335, 370),
    },
    DialogSizeClass.PROGRESS: {
        "growth": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "streak": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "currency": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "achievements": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "collection": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "collection-empty": DialogHeightProfile(570, 570, 570, 950, 950, 950),
    },
    DialogSizeClass.LOADOUT: {
        "default": DialogHeightProfile(520, 540, 560, 980, 1000, 1020),
    },
    DialogSizeClass.PLANT_STORY: {
        "default": DialogHeightProfile(480, 500, 520, 740, 760, 780),
    },
    DialogSizeClass.SPECIES_DETAIL: {
        "default": DialogHeightProfile(520, 550, 570, 800, 820, 840),
        "collected": DialogHeightProfile(520, 550, 570, 800, 820, 840),
        "uncollected": DialogHeightProfile(520, 550, 570, 800, 820, 840),
    },
    DialogSizeClass.GROWTH_CHARGE: {
        "ready": DialogHeightProfile(250, 270, 280, 480, 500, 510),
        "loading": DialogHeightProfile(250, 270, 280, 480, 500, 510),
        # An availability refresh adds one compact status banner.  Let that
        # real content fit up to the approved 310 px family ceiling instead
        # of manufacturing an 8 px safety scrollbar at 510 x 300.
        "stale": DialogHeightProfile(270, 300, 310, 500, 510, 540),
        "empty": DialogHeightProfile(190, 210, 230, 520, 540, 560),
        "warning": DialogHeightProfile(180, 210, 240, 520, 540, 560),
        "error": DialogHeightProfile(180, 210, 240, 520, 540, 560),
        "success": DialogHeightProfile(260, 280, 290, 480, 500, 510),
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


def dialog_window_mode(size_class: DialogSizeClass) -> DialogWindowMode:
    """Resolve the first-class native window mode for one semantic family."""

    return DIALOG_SIZE_POLICIES[size_class].window_mode


def resolved_dialog_view_width(
    size_class: DialogSizeClass,
    view_key: str | None,
    screen_width_cap: int,
) -> int:
    """Resolve a view's preferred width inside its declared and screen bounds."""

    policy = DIALOG_SIZE_POLICIES[size_class]
    profile = dialog_height_profile(size_class, view_key)
    cap = max(1, int(screen_width_cap))
    minimum = min(int(profile.min_width or policy.min_width), cap)
    maximum = max(
        minimum,
        min(int(profile.max_width or policy.max_width), cap),
    )
    preferred = int(profile.preferred_width or policy.preferred_width)
    return min(max(minimum, preferred), maximum)


def content_fit_geometry_limited(
    *,
    window_mode: DialogWindowMode | str,
    screen_width_cap: int,
    screen_height_cap: int,
    preferred_width: int,
    preferred_height: int,
    fitted_width: int,
    fitted_height: int,
    natural_width: int | None = None,
    natural_height: int | None = None,
) -> bool:
    """Report whether a Content window is constrained in either dimension.

    Width matters because a screen clamp can wrap otherwise valid copy and turn
    it into vertical overflow.  Natural dimensions are optional so callers can
    establish a conservative pre-layout state, then refine it after Qt settles.
    """

    if DialogWindowMode(window_mode) is not DialogWindowMode.CONTENT:
        return False
    width_cap = max(1, int(screen_width_cap))
    height_cap = max(1, int(screen_height_cap))
    fitted_width_value = max(1, int(fitted_width))
    fitted_height_value = max(1, int(fitted_height))
    width_limited = width_cap < max(1, int(preferred_width))
    # A content-fit window may intentionally settle below its preferred
    # height.  Height is constrained only when the screen cannot offer the
    # preferred geometry or measured content exceeds the fitted result.
    height_limited = height_cap < max(1, int(preferred_height))
    if natural_width is not None:
        # A family profile may intentionally cap a compact dialog below its
        # natural size.  That is a product-layout defect, not permission for a
        # screen-limited safety scrollbar.  Attribute the constraint to the
        # physical display only when the fitted window has reached its screen
        # cap and content still exceeds it.
        width_limited = width_limited or bool(
            int(natural_width) > fitted_width_value
            and fitted_width_value >= width_cap
        )
    if natural_height is not None:
        height_limited = height_limited or bool(
            int(natural_height) > fitted_height_value
            and fitted_height_value >= height_cap
        )
    return bool(width_limited or height_limited)


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
