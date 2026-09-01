"""Dependency-light contracts for native Garden dialogs.

The Qt implementation stays in :mod:`ankigarden.ui.dashboard` for backwards
compatibility with the add-on's existing surface classes.  These value objects
are intentionally independent from Qt so sizing and focus policy can be tested
without importing Anki.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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


def resolve_widget_layout(widget: Any) -> Any | None:
    """Return a Qt layout whether a widget exposes ``layout()`` or ``layout``.

    A few established Garden content widgets keep their ``QVBoxLayout`` in a
    public ``layout`` attribute, which shadows ``QWidget.layout()``. Shared
    shell code must accept both shapes when it adjusts scroll-content margins.
    """

    if widget is None:
        return None
    candidate = getattr(widget, "layout", None)
    return candidate() if callable(candidate) else candidate


@dataclass(frozen=True)
class DialogLayoutMetrics:
    """Shared non-scrolling shell and central-body spacing contract."""

    horizontal_padding: int = 24
    compact_body_padding: int = 20
    header_top_padding: int = 24
    body_top_padding: int = 16
    body_bottom_padding: int = 24
    footer_top_padding: int = 12
    footer_bottom_padding: int = 16
    card_padding: int = 16
    section_gap: int = 16
    row_gap: int = 12
    action_gap: int = 8

    @property
    def body_margins(self) -> tuple[int, int, int, int]:
        return (
            self.horizontal_padding,
            self.body_top_padding,
            self.horizontal_padding,
            self.body_bottom_padding,
        )

    @property
    def footer_margins(self) -> tuple[int, int, int, int]:
        return (
            self.horizontal_padding,
            self.footer_top_padding,
            self.horizontal_padding,
            self.footer_bottom_padding,
        )


@dataclass(frozen=True)
class DialogScrollContract:
    """Structural overflow rules for a four-region Garden dialog."""

    header_pinned: bool = True
    tabs_pinned: bool = True
    footer_pinned: bool = True
    central_body_scrolls: bool = True
    horizontal_scrolls: bool = False
    body_minimum_height: int = 0
    bottom_padding: int = 24
    scrollbar_clearance: int = 8
    overflow_owner_count: int = 1


GARDEN_DIALOG_LAYOUT = DialogLayoutMetrics()
DIALOG_LAYOUT_METRICS = GARDEN_DIALOG_LAYOUT
GardenDialogLayout = DialogLayoutMetrics
GARDEN_DIALOG_SCROLL = DialogScrollContract()
DIALOG_SCROLL_CONTRACT = GARDEN_DIALOG_SCROLL


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
class ResolvedDialogGeometry:
    """Screen-clamped minimum, initial, and maximum native client sizes."""

    minimum_width: int
    minimum_height: int
    initial_width: int
    initial_height: int
    maximum_width: int
    maximum_height: int

    def __post_init__(self) -> None:
        if not (
            0 < self.minimum_width <= self.initial_width <= self.maximum_width
            and 0 < self.minimum_height <= self.initial_height <= self.maximum_height
        ):
            raise ValueError("resolved dialog geometry must use ordered positive bounds")

    @property
    def minimum_size(self) -> tuple[int, int]:
        return self.minimum_width, self.minimum_height

    @property
    def initial_size(self) -> tuple[int, int]:
        return self.initial_width, self.initial_height

    @property
    def maximum_size(self) -> tuple[int, int]:
        return self.maximum_width, self.maximum_height


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


def workspace_content_fit_natural_height(
    natural_height: int,
    *,
    window_mode: DialogWindowMode | str,
    window_height: int,
    viewport_height: int | None,
    scroll_content_height: int | None,
) -> int:
    """Replace a workspace viewport with its natural scroll-content height.

    A ``QScrollArea`` reports the allocated viewport in its parent layout's
    size hint. For content-fit workspaces that makes the current window height
    self-reinforcing: content can overflow while the root still claims it
    fits. Derive the fixed header/tab/footer chrome from the live geometry and
    replace only the central viewport with its layout hint. The result is
    stable before and after a resize and still leaves the family and screen
    caps authoritative.
    """

    base = max(1, int(natural_height))
    if DialogWindowMode(window_mode) is not DialogWindowMode.WORKSPACE:
        return base
    if viewport_height is None or scroll_content_height is None:
        return base
    viewport = max(0, int(viewport_height))
    content = max(0, int(scroll_content_height))
    if viewport <= 0 or content <= 0:
        return base
    fixed_chrome = max(0, int(window_height) - viewport)
    return max(base, fixed_chrome + content)


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
        720,
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
        580,
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
        True,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.LOADOUT: DialogSizePolicy(
        980,
        520,
        1000,
        540,
        1020,
        680,
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
        480,
        260,
        820,
        440,
        820,
        900,
        1.0,
        1.0,
        False,
        True,
        screen_margin=16,
        window_mode=DialogWindowMode.WORKSPACE,
    ),
    DialogSizeClass.GROWTH_CHARGE: DialogSizePolicy(
        480,
        400,
        500,
        460,
        500,
        500,
        1.0,
        1.0,
        False,
        True,
        16,
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
        True,
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
        True,
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
        "growth-charge": DialogHeightProfile(270, 280, 300, 500, 500, 500),
        "replacement": DialogHeightProfile(230, 300, 340, 500, 520, 540),
        "complex": DialogHeightProfile(250, 295, 340, 540, 570, 600),
        "loading": DialogHeightProfile(210, 230, 250, 480, 500, 520),
        "warning": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "error": DialogHeightProfile(180, 210, 240, 480, 510, 540),
        "success": DialogHeightProfile(180, 210, 240, 480, 510, 540),
    },
    DialogSizeClass.FERTILIZER: {
        "default": DialogHeightProfile(470, 490, 520, 640, 660, 680),
        "selection": DialogHeightProfile(470, 490, 520, 640, 660, 680),
        "replacement": DialogHeightProfile(230, 260, 290, 500, 520, 540),
    },
    DialogSizeClass.SETTINGS: {
        # The Display page no longer carries a 100 px live preview. Keep the
        # shell content-fit around the remaining identity and appearance rows.
        "display": DialogHeightProfile(390, 400, 420, 800, 820, 840),
        # Advanced adds four compact setting rows beneath the same preview-free
        # Display content. The pinned shell consumes about 217 logical px, so
        # reserve the measured content height plus breathing room rather than
        # opening with the final row behind the emergency scroll viewport.
        # Shorter screens still retain the outer scroll owner.
        "advanced": DialogHeightProfile(700, 700, 720, 800, 820, 840),
        "diagnostics-clean": DialogHeightProfile(280, 300, 320, 760, 780, 800),
        "diagnostics-warning": DialogHeightProfile(280, 300, 320, 760, 780, 800),
        "diagnostics-expanded": DialogHeightProfile(430, 470, 520, 760, 780, 800),
    },
    DialogSizeClass.NURSERY: {
        # Four starter cards form two complete 90 px rows. The workspace's
        # content-derived fit lands near 377 px at canonical scale; keep the
        # semantic bounds wide enough for that natural height instead of
        # forcing the second row through the central scroll viewport.
        "starter": DialogHeightProfile(370, 380, 410, 925, 940, 950),
        "plants": DialogHeightProfile(300, 360, 520, 925, 940, 950),
        "owned": DialogHeightProfile(470, 500, 530),
        # The Fertilizer catalogue deliberately opens on three complete 88 px
        # cards: both stored items and Basic Fertilizer's full price/action
        # row. 557 px keeps that third 88 px card complete after the artwork-led
        # active strip, while leaving the following Quality card below the
        # initial fold. Content-fit still owns heights below this semantic
        # ceiling, and the same central scroll owner keeps every later product
        # reachable.
        "fertilizer": DialogHeightProfile(500, 506, 557, 925, 940, 950),
        "spaces": DialogHeightProfile(300, 325, 330, 925, 940, 950),
        # Garden Decoration cards keep one complete product row in view. The
        # active-bonus summary consumes 147 px above the 276 px product row,
        # so the content-fit ceiling must leave the catalogue a complete fold
        # instead of clipping all three first-row cards.
        "garden_features": DialogHeightProfile(488, 575, 580, 925, 940, 950),
        # The compact completion body has a 156 px native minimum on macOS.
        # Eight more client pixels remove the otherwise spurious scrollbar.
        "collection-complete": DialogHeightProfile(308, 323, 338, 925, 940, 950),
        "collection-complete-receipt": DialogHeightProfile(390, 400, 410, 925, 940, 950),
        "empty": DialogHeightProfile(300, 335, 370),
    },
    DialogSizeClass.PROGRESS: {
        # The native six-stage strip is three logical pixels taller than the
        # root layout hint on macOS. Keep the complete strip in the viewport
        # instead of exposing a three-pixel emergency scrollbar.
        "growth": DialogHeightProfile(501, 501, 510, 940, 940, 960),
        # The final Today setup card extends four logical pixels beyond the
        # generic Progress minimum. Give this real content state its own
        # profile so the card is painted as a complete surface.
        "today": DialogHeightProfile(564, 570, 580),
        "streak": DialogHeightProfile(440, 460, 480, 940, 940, 960),
        "currency": DialogHeightProfile(340, 380, 440, 940, 950, 960),
        "achievements": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "collection": DialogHeightProfile(570, 570, 570, 950, 950, 950),
        "collection-empty": DialogHeightProfile(360, 400, 460, 940, 950, 960),
    },
    DialogSizeClass.LOADOUT: {
        # The wide preview is a complete 16:9 garden scene beside two native
        # catalogue rows. Its natural height must include both the structured
        # appearance summary and the uncropped artwork.
        "default": DialogHeightProfile(680, 680, 680, 980, 1000, 1020),
    },
    DialogSizeClass.PLANT_STORY: {
        "default": DialogHeightProfile(480, 500, 520, 740, 760, 780),
    },
    DialogSizeClass.SPECIES_DETAIL: {
        "default": DialogHeightProfile(260, 440, 900, 480, 820, 820),
        "collected": DialogHeightProfile(260, 440, 900, 480, 820, 820),
        "uncollected": DialogHeightProfile(260, 360, 900, 480, 820, 820),
    },
    DialogSizeClass.GROWTH_CHARGE: {
        # Preview, commit, and result all use one markup tree and one geometry
        # envelope. Content-fit may settle anywhere inside these bounds, but
        # changing tense or footer callbacks must not resize the window.
        "ready": DialogHeightProfile(400, 460, 500, 480, 500, 500),
        "loading": DialogHeightProfile(400, 460, 500, 480, 500, 500),
        # An availability refresh adds one compact status banner. Let the
        # settled content determine the height instead of manufacturing a
        # transaction-body scrollbar.
        "stale": DialogHeightProfile(400, 460, 500, 480, 500, 500),
        "empty": DialogHeightProfile(190, 210, 230, 480, 500, 500),
        "warning": DialogHeightProfile(180, 210, 240, 480, 500, 500),
        "error": DialogHeightProfile(180, 210, 240, 480, 500, 500),
        "success": DialogHeightProfile(400, 460, 500, 480, 500, 500),
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

    # Workspace dialogs may still opt into content-fit sizing. ``workspace``
    # describes the pinned-header/body/footer composition; it is not a reason
    # to manufacture empty body height. Only the scene canvas intentionally
    # owns a stable viewport independent of its child size hints.
    if DialogWindowMode(window_mode) is DialogWindowMode.CANVAS:
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


def should_schedule_content_fit(
    window_mode: DialogWindowMode | str,
    *,
    policy_content_fit: bool,
) -> bool:
    """Return whether descendant layout changes should trigger a native fit.

    ``workspace`` describes a pinned header/body/footer composition, not a
    fixed-height window.  Any family that explicitly opts into ``content_fit``
    therefore follows the same settled-layout scheduler as compact Content
    dialogs.  Canvas windows remain the sole exception because their viewport
    is intentionally independent of descendant size hints.
    """

    return bool(
        policy_content_fit
        and DialogWindowMode(window_mode) is not DialogWindowMode.CANVAS
    )


def resolved_dialog_geometry(
    size_class: DialogSizeClass,
    available_width: int,
    available_height: int,
    *,
    preferred_width: int | None = None,
    preferred_height: int | None = None,
) -> ResolvedDialogGeometry:
    """Resolve ordered native bounds inside the available screen.

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
    maximum_width = max(
        1,
        min(usable_width, screen_width, policy.max_width),
    )
    maximum_height = max(
        1,
        min(usable_height, screen_height, policy.max_height),
    )
    minimum_width = min(policy.min_width, maximum_width)
    minimum_height = min(policy.min_height, maximum_height)
    initial_width = min(maximum_width, max(minimum_width, wanted_width))
    initial_height = min(maximum_height, max(minimum_height, wanted_height))
    return ResolvedDialogGeometry(
        minimum_width,
        minimum_height,
        initial_width,
        initial_height,
        maximum_width,
        maximum_height,
    )


def resolved_dialog_size(
    size_class: DialogSizeClass,
    available_width: int,
    available_height: int,
    *,
    preferred_width: int | None = None,
    preferred_height: int | None = None,
) -> tuple[int, int]:
    """Return the reasonable initial size from screen-clamped dialog bounds."""

    return resolved_dialog_geometry(
        size_class,
        available_width,
        available_height,
        preferred_width=preferred_width,
        preferred_height=preferred_height,
    ).initial_size


def text_column_width(average_character_width: int, characters: int = 68) -> int:
    """Return the shared readable line-length cap in logical pixels."""

    return max(1, int(average_character_width)) * max(1, int(characters))
