from __future__ import annotations

import logging
import json
import os
import platform
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from math import cos, isfinite, pi, sin
from pathlib import Path
from typing import Any, Callable

from aqt.qt import (
    QApplication,
    QDialog,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPixmap,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QStackedWidget,
    QTimer,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    QSize,
    QSizePolicy,
    QGuiApplication,
    QEvent,
    QEventLoop,
    QObject,
    QToolTip,
    pyqtSignal,
)

try:
    from aqt.qt import QSvgRenderer
except Exception:  # pragma: no cover - depends on the host Qt export surface
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore[no-redef]
    except Exception:  # pragma: no cover - PyQt5 compatibility fallback
        try:
            from PyQt5.QtSvg import QSvgRenderer  # type: ignore[no-redef]
        except Exception:  # pragma: no cover - graphical fallback remains available
            QSvgRenderer = None  # type: ignore[assignment]

from .dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DialogCloseBlocker,
    DialogCloseDecision,
    DialogClosePolicy,
    DialogCloseReason,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
    dialog_height_profile,
    dialog_view_policy,
    resolve_dialog_close,
    resolved_dialog_size,
    text_column_width,
)
from .accessibility import (
    AccessibilityAnnouncer,
    AnnouncementPriority,
    effective_motion_enabled,
    read_system_reduced_motion,
)
from .responsive import (
    AdaptiveRegion,
    AdaptiveRow,
    AdaptiveSplit,
    COMPACT_MODE,
    WIDE_MODE,
    responsive_column_count,
    responsive_interpolate,
)
from .formatters import (
    format_available,
    format_balance_after,
    format_growth_fifths,
    format_stage_progress,
    format_status_label,
)
from .icons import garden_icon
from .garden_studio import GardenStudioWidget
from .plant_display import (
    chronological_memories,
    growth_display,
    story_is_just_beginning,
)
from .plant_presenters import FertilizerStatus, fertilizer_status
from .scene import GardenSceneWidget
from .state import GardenUiCoordinator, select_garden_ui
from .state_contracts import OnboardingState, onboarding_state_display, streak_presentation
from .theme import (
    BUTTON_MIN_HEIGHT,
    BUTTON_VARIANT_DESTRUCTIVE,
    BUTTON_VARIANT_PRIMARY,
    BUTTON_VARIANT_SECONDARY,
    BUTTON_VARIANT_TERTIARY,
    COMPACT_BUTTON_HEIGHT,
    GARDEN_THEME,
    ICON_BUTTON_SIZE,
    INPUT_VISUAL_HEIGHT,
    PLANT_ACTION_MIN_HEIGHT,
    FeedbackTone,
    SemanticRole,
    TextRole,
    apply_tabular_numerals,
    apply_text_role,
    button_stylesheet,
    foundation_stylesheet,
    nursery_catalog_stylesheet,
    set_control_enabled,
    set_icon_accessible_name,
    set_keyboard_focus_surface,
    set_semantic_role,
)
from ..display_telemetry import DISPLAY_TELEMETRY
from ..collectibles import (
    CATEGORY_LABELS,
    collectible_registry,
    collectible_views,
    collection_categories,
)
from ..environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    GrowthChargeSpec,
)
from ..growth import (
    GrowthChargeRequest,
    GrowthChargeStatus,
    GrowthChargeTargetState,
)
from ..config import ConfigError, DEFAULT_CONFIG
from ..models.state import OnboardingStep
from ..models.state import (
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    MAX_GARDEN_NAME_LENGTH,
    MAX_PLANT_NAME_LENGTH,
    STATE_VERSION,
    STREAK_BONUS_TIERS,
)
from ..notices import USER_NOTICES
from ..reward_presentation import (
    achievement_presentations,
    recent_garden_finds,
    recent_reward_summaries,
    recurring_reward_presentations,
)
from ..purchases import (
    PurchaseFact,
    PurchaseDisposition,
    PurchaseKind,
    PurchaseOutcome,
    PurchasePresentation,
    PurchasePreviewStyle,
    PurchaseQuote,
    PurchaseRequest,
    PurchaseStatus,
    compact_duration,
    purchase_presentation,
)
from ..terminology import (
    ACTIVE_PLANT_EXPLANATION,
    ALL_DUE_EXPLANATION,
    ANKI_STREAK_EXPLANATION,
    FERTILIZER_EXPLANATION,
    GARDEN_CURRENCY_EXPLANATION,
    GROWTH_EXPLANATION,
)
from .copy import (
    CHOOSE_STARTER_ACTION,
    COST_FREE,
    DISABLED_STARTER_TABS,
    FULLY_GROWN_ACTION,
    FULLY_GROWN_MESSAGE,
    GARDEN_SETUP_BODY,
    GARDEN_SETUP_SECONDARY_ACTION,
    GARDEN_SETUP_TITLE,
    GARDEN_NURTURE_ACTION,
    GARDEN_NURTURE_BODY,
    GARDEN_NURTURE_TITLE,
    METRIC_AFFORDANCE,
    NURSERY_STARTER_COUNT,
    NURSERY_STARTER_RATIONALE,
    NURSERY_STARTER_TITLE,
    REWARD_DISCLOSURE,
    cost_label,
    seed_title,
    starter_confirmation,
)

logger = logging.getLogger(__name__)

UI_TEXT = {
    "settings_window_title": "Garden settings",
    "advanced_hint": "Check again. Copy a report if the issue continues.",
    "tab_advanced": "Troubleshooting",
    "app_title": "Anki Garden",
    "title_banner": "Anki Garden",
    "open_settings": "Settings",
    "today_progress_title": "Today",
    "no_achievements": "Achievement progress will appear as you keep studying.",
    "no_collection": "No collected garden items yet.",
}


def _addon_human_version() -> str:
    """Read the packaged version without duplicating release metadata in UI copy."""

    try:
        payload = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text("utf-8"))
        return str(payload.get("human_version") or "current")
    except (OSError, TypeError, ValueError):
        return "current"


def _addon_build_identifier() -> str:
    """Stable packaged identity without exposing filesystem or debug details."""

    return f"{_addon_human_version()}-state{STATE_VERSION}"

UX_NO_STARTER = "NO_STARTER"
UX_STARTER_READY = "STARTER_READY"
UX_ACTIVE_GROWTH = "ACTIVE_GROWTH"
UX_NURTURED_PLANT_COMPLETE = "NURTURED_PLANT_COMPLETE"


class ElidingLabel(QLabel):
    """Single-line label that retains its full accessible name and tooltip."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._full_text = ""
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = str(text)
        self.setAccessibleName(self._full_text)
        self._refresh_elision()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        available = max(1, int(self.contentsRect().width()))
        visible = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            available,
        )
        if super().text() != visible:
            super().setText(visible)
        self.setToolTip(self._full_text if visible != self._full_text else "")


def _set_button_variant(button: QPushButton, variant: str) -> None:
    button.setProperty("variant", variant)
    style = button.style()
    if style is not None:
        style.unpolish(button)
        style.polish(button)


def _set_compact_row_action(button: QPushButton) -> None:
    """Apply the shared text-fit 30 px treatment for card-row actions."""

    button.setProperty("compactRowAction", True)
    style = button.style()
    if style is not None:
        style.unpolish(button)
        style.polish(button)


def _qt_button_text(value: str) -> str:
    """Escape Qt mnemonic markers while preserving the visible action copy."""

    return str(value).replace("&", "&&")


def _settings_gear_icon(size: int = 22) -> QIcon:
    """Return a centered vector-painted gear that stays crisp at high DPI."""

    edge = max(16, int(size))
    pixmap = QPixmap(edge, edge)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = edge / 2
    outer = edge * 0.46
    inner = edge * 0.34
    path = QPainterPath()
    for index in range(32):
        angle = -pi / 2 + index * pi / 16
        radius = outer if index % 4 in (0, 1) else inner
        point = QPointF(
            center + cos(angle) * radius,
            center + sin(angle) * radius,
        )
        path.moveTo(point) if index == 0 else path.lineTo(point)
    path.closeSubpath()
    path.addEllipse(QPointF(center, center), edge * 0.115, edge * 0.115)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    painter.fillPath(path, QColor("#D8E3DE"))
    painter.end()
    return QIcon(pixmap)


def _toggle_state_icon(checked: bool) -> QIcon:
    """Paint one left-side checked or blank state indicator."""

    pixmap = QPixmap(38, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    outline = QRectF(1.0, 1.0, 36.0, 22.0)
    painter.setPen(
        QPen(
            QColor(GARDEN_THEME["growth_accent"] if checked else GARDEN_THEME["strong_border"]),
            1.0,
        )
    )
    painter.setBrush(
        QColor(GARDEN_THEME["action_accent"] if checked else "#20312c")
    )
    painter.drawRoundedRect(outline, 11.0, 11.0)
    if checked:
        check = QPainterPath()
        check.moveTo(10.0, 12.0)
        check.lineTo(16.0, 17.0)
        check.lineTo(28.0, 7.0)
        painter.setPen(
            QPen(
                QColor(GARDEN_THEME["action_text"]),
                2.4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(check)
    painter.end()
    return QIcon(pixmap)


def _pin_empty_state_action_style(button: QPushButton, variant: str) -> None:
    """Keep an empty-state primary action above nested Qt style cascades."""

    _set_button_variant(button, variant)
    if variant != BUTTON_VARIANT_PRIMARY:
        return
    marker = "/* anki-garden-empty-state-primary */"
    if marker in button.styleSheet():
        return
    t = GARDEN_THEME
    local_style = f"""
        {marker}
        QPushButton {{
            min-height:{BUTTON_MIN_HEIGHT}px;
            padding:0 14px;
            background-color:{t['action_accent']};
            border:1px solid {t['action_border']};
            border-radius:8px;
            color:{t['action_text']};
            font-size:14px;
            font-weight:600;
        }}
        QPushButton:hover {{ background-color:{t['action_hover']}; }}
        QPushButton:pressed {{ background-color:{t['action_pressed']}; }}
        QPushButton:focus {{ border:2px solid {t['focus_ring']}; padding:0 13px; }}
        QPushButton:disabled {{
            background-color:{t['disabled_surface']};
            border-color:{t['disabled_border']};
            color:{t['disabled_text']};
        }}
    """
    existing = button.styleSheet()
    button.setStyleSheet(f"{existing}\n{local_style}" if existing else local_style)


def _set_scroll_surface(
    scroll: QScrollArea,
    content: QWidget,
    color: str,
) -> None:
    """Pin every scroll layer to its owning Garden surface.

    Qt scroll areas have three independently painted layers: the frame, its
    viewport, and the content widget.  Styling only one of them lets Anki's
    platform palette show through as a gray gutter when content is short or a
    dialog is resized.  A widget-local property rule wins over that inherited
    palette without replacing any component-specific stylesheet.
    """

    marker = "/* anki-garden-scroll-surface */"
    rule = (
        f"{marker}\n"
        f"QWidget[gardenScrollSurface='true'] {{ background-color:{color}; }}"
    )
    for widget in (scroll, scroll.viewport(), content):
        widget.setProperty("gardenScrollSurface", True)
        widget.setAutoFillBackground(True)
        existing = widget.styleSheet()
        if marker not in existing:
            widget.setStyleSheet(f"{existing}\n{rule}" if existing else rule)


class DialogShell(QWidget):
    """Movable dialog shell attached to its owning Anki window."""

    finished = pyqtSignal(int)
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        native_auxiliary_on_macos = (
            platform.system() == "Darwin" and parent is not None
        )
        if native_auxiliary_on_macos:
            # A parented Qt Tool is a real NSPanel on macOS: it has native
            # window chrome, remains movable/resizable, and stays above its
            # owner. The AppKit Space behavior is configured before show().
            flags = (
                Qt.WindowType.Tool
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowMinimizeButtonHint
                | Qt.WindowType.WindowMaximizeButtonHint
                | Qt.WindowType.WindowCloseButtonHint
            )
            super().__init__(parent, flags)
        else:
            super().__init__(parent, Qt.WindowType.Dialog)
        self._native_auxiliary_on_macos = native_auxiliary_on_macos
        self._dialog_owner = parent
        self._return_focus: QWidget | None = None
        self._initial_focus_policy = InitialFocusPolicy.AUTOMATIC
        self._initial_focus_target: QWidget | None = None
        self._state_focus_target: QWidget | None = None
        self._close_policy = DialogClosePolicy()
        self._close_policy_disabled_top_close = False
        self._dialog_dirty = False
        self._dialog_in_flight = False
        self._dirty_close_confirmation: (
            Callable[[DialogCloseReason], bool] | None
        ) = None
        self._close_blocked_callback: (
            Callable[[DialogCloseDecision], None] | None
        ) = None
        self._pending_close_reason: DialogCloseReason | None = None
        self._last_close_decision: DialogCloseDecision | None = None
        self._registered_scroll_regions: list[QScrollArea] = []
        self._scroll_base_margins: dict[int, tuple[int, int, int, int]] = {}
        self._pinned_footer: QWidget | None = None
        self._dialog_result = int(QDialog.DialogCode.Rejected)
        self._dialog_event_loop: QEventLoop | None = None
        self._dialog_exec_active = False
        self._modal_requested = False
        self._native_position_initialized = False
        self._dialog_size_class: DialogSizeClass | None = None
        self._dialog_view_key = "default"
        self._family_width = 0
        self._preserved_transition_height = 0
        self._preserve_transition_height = False
        # DialogShell deliberately remains a QWidget subclass so its custom
        # dialog contract works consistently in Anki's supported Qt versions.
        # The Tool/Dialog window flag supplies the native top-level window.
        self.setProperty("gardenDialogShell", True)
        self.setProperty("movableNativeWindow", True)
        self.setProperty("embeddedFullscreen", False)
        self.setProperty("nativeParentAttached", False)
        self.setProperty("windowFamily", type(self).__name__)
        self.setProperty("layoutMode", "default")
        self.setProperty("initialFocusPolicy", self._initial_focus_policy.value)
        self.setProperty("closeProtectsDirty", False)
        self.setProperty("closeProtectsInFlight", False)
        self.setProperty("dialogDirty", False)
        self.setProperty("dialogInFlight", False)
        self.setProperty("lastCloseReason", "")
        self.setProperty("closeBlockedBy", "")
        self.accessibility_announcer = AccessibilityAnnouncer(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Secondary Garden shells are built eagerly. Keep every native window
        # hidden until its transient parent and Space behavior are configured.
        self.hide()
        if self._native_auxiliary_on_macos:
            # With two isolated Anki processes macOS treats both as the same
            # application identity. The owner is already active, so the new
            # panel should appear without making another activation request.
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowModality(
            Qt.WindowModality.NonModal
            if self._native_auxiliary_on_macos
            else Qt.WindowModality.WindowModal
        )

    def setWindowTitle(self, title: str) -> None:
        """Keep the native title and accessibility title synchronized."""

        super().setWindowTitle(str(title))
        self.setAccessibleName(str(title))
        top_close = getattr(self, "top_close", None)
        if top_close is not None:
            top_close.setAccessibleName(f"Close {title}")
            if not bool(top_close.property("closeBlockedInFlight")):
                top_close.setToolTip(f"Close {title}")
                top_close.setAccessibleDescription(f"Close {title}")

    def create_inline_close_button(
        self,
        parent: QWidget,
        *,
        title: str | None = None,
    ) -> "GardenIconButton":
        """Create the canonical visible close control for a dialog header."""

        close_title = str(title or self.windowTitle() or "dialog")
        button = GardenIconButton("close", f"Close {close_title}", parent)
        button.clicked.connect(
            lambda _checked=False: self.request_close(
                DialogCloseReason.CLOSE_BUTTON
            )
        )
        self.top_close = button
        self.close_policy_changed()
        return button

    def set_initial_focus(
        self,
        widget: QWidget | None,
        policy: InitialFocusPolicy = InitialFocusPolicy.EXPLICIT,
    ) -> None:
        self._initial_focus_target = widget
        self._initial_focus_policy = InitialFocusPolicy(policy)
        self.setProperty("initialFocusPolicy", self._initial_focus_policy.value)

    def configure_close_policy(
        self,
        *,
        protect_dirty: bool = False,
        protect_in_flight: bool = False,
        confirm_dirty: Callable[[DialogCloseReason], bool] | None = None,
        on_blocked: Callable[[DialogCloseDecision], None] | None = None,
    ) -> None:
        """Opt into shared close safeguards and optional policy hooks.

        The default policy remains permissive. A dirty dialog is only allowed
        to close when its confirmation hook returns true; an in-flight dialog
        remains protected even after a dirty-state confirmation.
        """

        self._close_policy = DialogClosePolicy(
            protect_dirty=bool(protect_dirty),
            protect_in_flight=bool(protect_in_flight),
        )
        self._dirty_close_confirmation = confirm_dirty
        self._close_blocked_callback = on_blocked
        self.setProperty(
            "closeProtectsDirty",
            self._close_policy.protect_dirty,
        )
        self.setProperty(
            "closeProtectsInFlight",
            self._close_policy.protect_in_flight,
        )
        self.close_policy_changed()

    @property
    def close_policy(self) -> DialogClosePolicy:
        return self._close_policy

    @property
    def dialog_dirty(self) -> bool:
        return self._dialog_dirty

    def set_dialog_dirty(self, dirty: bool) -> None:
        self._dialog_dirty = bool(dirty)
        self.setProperty("dialogDirty", self._dialog_dirty)
        self.close_policy_changed()

    @property
    def dialog_in_flight(self) -> bool:
        return self._dialog_in_flight

    def set_dialog_in_flight(self, in_flight: bool) -> None:
        self._dialog_in_flight = bool(in_flight)
        self.setProperty("dialogInFlight", self._dialog_in_flight)
        self.close_policy_changed()

    @property
    def last_close_decision(self) -> DialogCloseDecision | None:
        return self._last_close_decision

    def close_policy_changed(self) -> None:
        """Reflect shared close safety in the canonical inline control."""

        top_close = getattr(self, "top_close", None)
        if top_close is None:
            return
        protected = bool(
            self.close_policy.protect_in_flight and self.dialog_in_flight
        )
        top_close.setProperty("closeBlockedInFlight", protected)
        if protected:
            if top_close.isEnabled():
                self._close_policy_disabled_top_close = True
                top_close.setEnabled(False)
            top_close.setToolTip("Close is unavailable while this action finishes")
            top_close.setAccessibleDescription(
                "Close is unavailable while this action finishes."
            )
            return
        if self._close_policy_disabled_top_close:
            top_close.setEnabled(True)
            self._close_policy_disabled_top_close = False
        title = self.windowTitle() or "dialog"
        top_close.setToolTip(f"Close {title}")
        top_close.setAccessibleDescription(f"Close {title}")

    def confirm_dirty_close(self, reason: DialogCloseReason) -> bool:
        """Hook for a discard confirmation; absence means keep the dialog open."""

        callback = self._dirty_close_confirmation
        return bool(callback(reason)) if callback is not None else False

    def evaluate_close_request(
        self,
        reason: DialogCloseReason | str,
    ) -> DialogCloseDecision:
        """Resolve a close request, including an optional dirty confirmation."""

        reason = DialogCloseReason(reason)
        decision = resolve_dialog_close(
            self._close_policy,
            reason,
            dirty=self._dialog_dirty,
            in_flight=self._dialog_in_flight,
        )
        if (
            decision.blocked_by is DialogCloseBlocker.DIRTY
            and self.confirm_dirty_close(reason)
        ):
            decision = resolve_dialog_close(
                self._close_policy,
                reason,
                dirty=self._dialog_dirty,
                in_flight=self._dialog_in_flight,
                dirty_confirmed=True,
            )
        return decision

    def close_request_blocked(self, decision: DialogCloseDecision) -> None:
        """Hook for visible or announced feedback when dismissal is unsafe."""

        callback = self._close_blocked_callback
        if callback is not None:
            callback(decision)
            return
        message = (
            "Please wait for the current action to finish."
            if decision.blocked_by is DialogCloseBlocker.IN_FLIGHT
            else "This dialog has unsaved changes."
        )
        self.accessibility_announcer.announce(
            message,
            priority=AnnouncementPriority.POLITE,
            target=self,
        )

    def request_close(
        self,
        reason: DialogCloseReason | str = DialogCloseReason.PROGRAMMATIC,
    ) -> bool:
        """Request rejection with a stable reason while preserving overrides."""

        reason = DialogCloseReason(reason)
        previous_reason = self._pending_close_reason
        self._pending_close_reason = reason
        self._last_close_decision = None
        try:
            # Dynamic dispatch intentionally preserves existing reject()
            # overrides that validate, confirm, or roll back local drafts.
            self.reject()
        finally:
            self._pending_close_reason = previous_reason
        return bool(
            self._last_close_decision is not None
            and self._last_close_decision.allowed
        )

    def register_scroll_region(self, scroll: QScrollArea) -> None:
        """Register a deliberate vertical scroll owner for footer clearance."""

        # Child dialogs are parented to their invoking shell but are separate
        # native windows. A recursive QObject search must never let the owner
        # adopt or mutate a nested dialog's scroll contract.
        if scroll.window() is not self:
            return
        if scroll not in self._registered_scroll_regions:
            self._registered_scroll_regions.append(scroll)
        scroll.setProperty("dialogScrollRegion", True)
        self._sync_footer_clearance()

    def register_pinned_footer(self, footer: QWidget) -> None:
        self._pinned_footer = footer
        footer.setProperty("dialogPinnedFooter", True)
        self._sync_footer_clearance()

    def _discover_scroll_regions(self) -> None:
        for scroll in self.findChildren(QScrollArea):
            if (
                scroll.window() is self
                and
                scroll.verticalScrollBarPolicy()
                != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            ):
                self.register_scroll_region(scroll)

    def _sync_footer_clearance(self) -> None:
        footer = self._pinned_footer
        # The footer is a normal sibling in the shell layout, not an overlay.
        # Adding its height to every scroll content margin manufactures a large
        # blank strip and can make a sparse view scroll unnecessarily.
        clearance = 0
        for scroll in tuple(self._registered_scroll_regions):
            try:
                if scroll.window() is not self:
                    self._registered_scroll_regions.remove(scroll)
                    self._scroll_base_margins.pop(id(scroll), None)
                    continue
                content = scroll.widget()
                content_layout = content.layout() if content is not None else None
                if content_layout is None:
                    continue
                key = id(scroll)
                base = self._scroll_base_margins.get(key)
                if base is None:
                    margins = content_layout.contentsMargins()
                    base = (
                        margins.left(),
                        margins.top(),
                        margins.right(),
                        margins.bottom(),
                    )
                    self._scroll_base_margins[key] = base
                content_layout.setContentsMargins(
                    base[0],
                    base[1],
                    base[2],
                    base[3] + clearance,
                )
                scroll.setProperty("footerClearance", clearance)
            except RuntimeError:
                self._registered_scroll_regions.remove(scroll)

    def active_vertical_scroll_regions(self) -> tuple[QScrollArea, ...]:
        """Return visible vertical owners for diagnostics and capture audits."""

        self._discover_scroll_regions()
        return tuple(
            scroll
            for scroll in self._registered_scroll_regions
            if scroll.window() is self
            and scroll.isVisibleTo(self)
            and scroll.verticalScrollBarPolicy()
            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def apply_size_policy(
        self,
        size_class: DialogSizeClass,
        *,
        preferred_width: int | None = None,
        preferred_height: int | None = None,
    ) -> tuple[int, int]:
        policy = DIALOG_SIZE_POLICIES[size_class]
        parent = self.parentWidget()
        screen = (
            parent.window().screen()
            if parent is not None and parent.window() is not None
            else self.screen()
        )
        if screen is None:
            available_width = policy.preferred_width
            available_height = policy.preferred_height
        else:
            available = screen.availableGeometry()
            available_width = int(available.width())
            available_height = int(available.height())
        width, height = resolved_dialog_size(
            size_class,
            available_width,
            available_height,
            preferred_width=preferred_width,
            preferred_height=preferred_height,
        )
        screen_max_width = max(1, available_width - (policy.screen_margin * 2))
        screen_max_height = max(1, available_height - (policy.screen_margin * 2))
        self.setMinimumSize(
            min(policy.min_width, width, screen_max_width),
            min(policy.min_height, height, screen_max_height),
        )
        self.setMaximumSize(
            min(policy.max_width, screen_max_width),
            min(policy.max_height, screen_max_height),
        )
        self.resize(width, height)
        self._dialog_size_class = size_class
        self._dialog_view_key = "default"
        self._family_width = width
        self._preserve_transition_height = bool(
            policy.preserve_transition_height
        )
        self._preserved_transition_height = height
        self.setProperty("dialogSizeClass", size_class.value)
        self.setProperty("dialogFamilyWidth", width)
        self.setProperty("dialogContentFit", policy.content_fit)
        self.setProperty("dialogScreenMargin", policy.screen_margin)
        if policy.content_fit:
            body = getattr(self, "body_region", None)
            if body is not None:
                body.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
            QTimer.singleShot(0, self.fit_content_to_family)
        return width, height

    def apply_view_size_profile(self, view_key: str) -> int:
        """Fit one family view, clamp it to the screen, and re-center it."""

        size_class = self._dialog_size_class
        if size_class is None:
            return int(self.height())
        policy = DIALOG_SIZE_POLICIES[size_class]
        profile = dialog_height_profile(size_class, view_key)
        self._dialog_view_key = str(view_key or "default").strip().lower()
        parent = self.parentWidget()
        screen = (
            parent.window().screen()
            if parent is not None and parent.window() is not None
            else self.screen()
        )
        available_height = (
            int(screen.availableGeometry().height())
            if screen is not None
            else profile.max_height + policy.screen_margin * 2
        )
        available_width = (
            int(screen.availableGeometry().width())
            if screen is not None
            else int(profile.max_width or policy.max_width) + policy.screen_margin * 2
        )
        screen_cap = max(1, available_height - policy.screen_margin * 2)
        screen_width_cap = max(1, available_width - policy.screen_margin * 2)
        minimum = min(profile.min_height, screen_cap)
        maximum = min(profile.max_height, screen_cap)
        minimum_width = min(
            int(profile.min_width or policy.min_width),
            screen_width_cap,
        )
        maximum_width = min(
            int(profile.max_width or policy.max_width),
            screen_width_cap,
        )
        maximum_width = max(minimum_width, maximum_width)
        preferred_width = min(
            max(
                minimum_width,
                int(profile.preferred_width or self._family_width or policy.preferred_width),
            ),
            maximum_width,
        )
        self.setMinimumSize(minimum_width, minimum)
        self.setMaximumSize(maximum_width, max(minimum, maximum))
        self._family_width = preferred_width
        self.resize(
            preferred_width,
            min(max(minimum, profile.preferred_height), maximum),
        )
        self.setProperty("dialogViewProfile", self._dialog_view_key)
        fitted = self.fit_content_to_family(preserve_transition=False)
        QTimer.singleShot(0, self._recenter_over_parent)
        return fitted

    def fit_content_to_family(
        self,
        *,
        breathing_room: int = 16,
        preserve_transition: bool | None = None,
    ) -> int:
        """Fit the active family to native content without changing width.

        Loading/ready transitions in transaction families may deliberately
        retain their first measured height, while terminal compact states can
        call this method with ``preserve_transition=False``.
        """

        size_class = self._dialog_size_class
        if size_class is None:
            return int(self.height())
        policy = DIALOG_SIZE_POLICIES[size_class]
        height_profile = dialog_height_profile(
            size_class,
            self._dialog_view_key,
        )
        if not policy.content_fit:
            return int(self.height())
        keep_height = (
            self._preserve_transition_height
            if preserve_transition is None
            else bool(preserve_transition)
        )
        if keep_height and self.dialog_in_flight and self._preserved_transition_height:
            target = min(self.maximumHeight(), self._preserved_transition_height)
            self.resize(self._family_width or self.width(), target)
            return target
        root_layout = self.layout()
        natural_height = int(self.height())
        if root_layout is not None:
            root_layout.invalidate()
            root_layout.activate()
            natural_height = max(1, int(root_layout.sizeHint().height()))
        target = max(
            min(height_profile.min_height, self.maximumHeight()),
            min(
                self.maximumHeight(),
                height_profile.max_height,
                natural_height + max(0, int(breathing_room)),
            ),
        )
        self.resize(self._family_width or self.width(), target)
        if not self.dialog_in_flight:
            self._preserved_transition_height = target
        self.setProperty("contentNaturalHeight", natural_height)
        self.setProperty("contentFittedHeight", target)
        return target

    def set_content_bounded_maximum_height(
        self,
        maximum_height: int,
        *,
        minimum_height: int | None = None,
        breathing_room: int = 0,
    ) -> int:
        """Cap short semantic dialogs at their natural layout height.

        Width can still grow for comparisons and readable rows. The explicit
        vertical cap prevents a short body from inheriting a catalogue-sized
        empty viewport on a large display, while the size-class minimum still
        protects small windows and the deliberate scroll region.
        """

        requested_cap = max(1, int(maximum_height))
        requested_minimum = max(
            1,
            int(self.minimumHeight() if minimum_height is None else minimum_height),
        )
        requested_minimum = min(requested_minimum, requested_cap)
        # A previous content-aware pass may have installed a shorter maximum.
        # Restore this caller's explicit ceiling before measuring another
        # responsive mode so compact content can grow again when needed.
        self.setMaximumHeight(requested_cap)
        self.setMinimumHeight(requested_minimum)
        for scroll in tuple(self._registered_scroll_regions):
            content = scroll.widget()
            content_layout = content.layout() if content is not None else None
            if content_layout is not None:
                content_layout.invalidate()
                content_layout.activate()
        root_layout = self.layout()
        natural_height = requested_cap
        if root_layout is not None:
            root_layout.invalidate()
            root_layout.activate()
            natural_height = max(1, int(root_layout.sizeHint().height()))
        bounded = max(
            requested_minimum,
            min(requested_cap, natural_height + max(0, int(breathing_room))),
        )
        self.setMaximumHeight(bounded)
        if self.height() > bounded:
            self.resize(self.width(), bounded)
        self.setProperty("contentNaturalHeight", natural_height)
        self.setProperty("contentBoundedMaximumHeight", bounded)
        return bounded

    def _focusable_descendants(self) -> list[QWidget]:
        def enum_value(value: Any) -> int:
            return int(getattr(value, "value", value))

        widgets: list[QWidget] = []
        current = self.nextInFocusChain()
        seen: set[int] = {id(self)}
        # PyQt may create a temporary wrapper for an internal Qt child each
        # time nextInFocusChain() advances. Retain every wrapper until the walk
        # completes so Python cannot recycle an id and terminate the trap
        # before later controls in the native focus chain are reached.
        retained: list[QWidget] = [self]
        while current is not self and id(current) not in seen:
            seen.add(id(current))
            retained.append(current)
            if (
                isinstance(current, QWidget)
                and self.isAncestorOf(current)
                and current.isVisibleTo(self)
                and current.isEnabled()
                and (
                    enum_value(current.focusPolicy())
                    & enum_value(Qt.FocusPolicy.TabFocus)
                )
            ):
                widgets.append(current)
            current = current.nextInFocusChain()
        return widgets

    def _valid_focus_target(self, widget: QWidget | None) -> bool:
        return bool(
            widget is not None
            and self.isAncestorOf(widget)
            and widget.isVisibleTo(self)
            and widget.isEnabled()
        )

    def _policy_focus_target(
        self,
        focusable: list[QWidget],
    ) -> QWidget | None:
        """Resolve the declared policy without replacing the READY target."""

        if self._valid_focus_target(self._state_focus_target):
            return self._state_focus_target

        policy = self._initial_focus_policy
        configured = (
            self._initial_focus_target
            if self._valid_focus_target(self._initial_focus_target)
            else None
        )
        if policy is InitialFocusPolicy.AUTOMATIC:
            return configured
        if policy is InitialFocusPolicy.EXPLICIT:
            return configured
        if policy is InitialFocusPolicy.FIRST_EDITABLE:
            editable_types = (QLineEdit, QTextEdit)
            if isinstance(configured, editable_types):
                return configured
            return next(
                (widget for widget in focusable if isinstance(widget, editable_types)),
                configured,
            )
        if policy is InitialFocusPolicy.SELECTED_ROUTE:
            route_types = (QTabWidget, QStackedWidget)
            if isinstance(configured, route_types):
                return configured
            return next(
                (widget for widget in focusable if isinstance(widget, route_types)),
                configured,
            )
        if policy is InitialFocusPolicy.SAFE_ACTION:
            if isinstance(configured, QPushButton) and (
                configured.property("variant") != BUTTON_VARIANT_DESTRUCTIVE
            ):
                return configured
            return next(
                (
                    widget
                    for widget in focusable
                    if isinstance(widget, QPushButton)
                    and widget.property("variant") != BUTTON_VARIANT_DESTRUCTIVE
                ),
                configured,
            )
        return configured

    def _apply_initial_focus(self) -> None:
        focusable = self._focusable_descendants()
        target = self._policy_focus_target(focusable)
        if target is not None:
            target.setFocus(Qt.FocusReason.TabFocusReason)
            return
        existing = self.focusWidget()
        if (
            existing is not None
            and self.isAncestorOf(existing)
            and existing.isVisibleTo(self)
            and existing.isEnabled()
        ):
            return
        if focusable:
            focusable[0].setFocus(Qt.FocusReason.TabFocusReason)

    def focusNextPrevChild(self, forward: bool) -> bool:
        """Cycle focus inside the active shell instead of escaping to Anki."""

        focusable = self._focusable_descendants()
        if not focusable:
            return False
        current = self.focusWidget()
        try:
            index = focusable.index(current) if current is not None else -1
        except ValueError:
            index = -1
        if forward:
            target = focusable[(index + 1) % len(focusable)]
            reason = Qt.FocusReason.TabFocusReason
        else:
            target = focusable[(index - 1) % len(focusable)]
            reason = Qt.FocusReason.BacktabFocusReason
        target.setFocus(reason)
        return True

    def remember_invoker(self, widget: QWidget | None) -> None:
        self._return_focus = widget

    def setModal(self, modal: bool) -> None:
        self._modal_requested = bool(modal)
        self.setWindowModality(
            (
                Qt.WindowModality.WindowModal
                if modal
                else Qt.WindowModality.NonModal
            )
            if self._native_auxiliary_on_macos
            else (
                Qt.WindowModality.ApplicationModal
                if modal
                else Qt.WindowModality.NonModal
            )
        )

    def isModal(self) -> bool:
        return bool(self._modal_requested)

    def _configure_macos_auxiliary_window(self) -> bool:
        """Keep this native panel in the owner's active full-screen Space."""

        if not self._native_auxiliary_on_macos:
            return True
        try:
            import ctypes

            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            sel_register_name = objc.sel_registerName
            sel_register_name.argtypes = [ctypes.c_char_p]
            sel_register_name.restype = ctypes.c_void_p
            send_pointer = ctypes.CFUNCTYPE(
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(("objc_msgSend", objc))
            send_unsigned = ctypes.CFUNCTYPE(
                ctypes.c_ulong,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(("objc_msgSend", objc))
            send_void_unsigned = ctypes.CFUNCTYPE(
                None,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
            )(("objc_msgSend", objc))

            native_view = ctypes.c_void_p(int(self.winId()))
            ns_window = send_pointer(
                native_view,
                sel_register_name(b"window"),
            )
            if not ns_window:
                raise RuntimeError("Qt native view has no NSWindow")

            collection_selector = sel_register_name(b"collectionBehavior")
            current = int(send_unsigned(ns_window, collection_selector))
            can_join_all_spaces = 1 << 0
            move_to_active_space = 1 << 1
            full_screen_primary = 1 << 7
            full_screen_auxiliary = 1 << 8
            full_screen_none = 1 << 9
            primary = 1 << 16
            auxiliary = 1 << 17
            can_join_all_applications = 1 << 18
            desired = current & ~(
                can_join_all_spaces
                | full_screen_primary
                | full_screen_none
                | primary
                | auxiliary
                | can_join_all_applications
            )
            desired |= (
                move_to_active_space
                | full_screen_auxiliary
                | auxiliary
            )
            send_void_unsigned(
                ns_window,
                sel_register_name(b"setCollectionBehavior:"),
                desired,
            )
            confirmed = int(send_unsigned(ns_window, collection_selector))
            moves_to_active_space = bool(confirmed & move_to_active_space)
            is_full_screen_auxiliary = bool(
                confirmed & full_screen_auxiliary
            )
            self.setProperty(
                "macosMoveToActiveSpace",
                moves_to_active_space,
            )
            self.setProperty(
                "macosFullScreenAuxiliary",
                is_full_screen_auxiliary,
            )
            return moves_to_active_space and is_full_screen_auxiliary
        except Exception:
            logger.warning(
                "Anki Garden: macOS auxiliary window behavior could not be configured",
                exc_info=True,
            )
            self.setProperty("macosMoveToActiveSpace", False)
            self.setProperty("macosFullScreenAuxiliary", False)
            return False

    def _attach_native_parent_before_show(self) -> bool:
        """Bind the native child window before macOS can choose another Space."""

        parent = self.parentWidget()
        if parent is None:
            self.setProperty("nativeParentAttached", False)
            return False
        parent_window = parent.window()

        try:
            parent_window.winId()
            self.winId()
            parent_handle = parent_window.windowHandle()
            child_handle = self.windowHandle()
            if parent_handle is None or child_handle is None:
                self.setProperty("nativeParentAttached", False)
                return False
            child_handle.setTransientParent(parent_handle)
            if parent_handle.screen() is not None:
                child_handle.setScreen(parent_handle.screen())
            attached = child_handle.transientParent() == parent_handle
            space_ready = self._configure_macos_auxiliary_window()
            ready = bool(attached and space_ready)
            self.setProperty("nativeParentAttached", ready)
            return ready
        except (AttributeError, RuntimeError):
            logger.warning(
                "Anki Garden: native dialog parent could not be attached before show",
                exc_info=True,
            )
            self.setProperty("nativeParentAttached", False)
            return False

    def _recenter_over_parent(self) -> None:
        """Center the current content-fit geometry inside its owner screen."""

        parent = self.parentWidget()
        if parent is None:
            return
        parent_frame = parent.window().frameGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(parent_frame.center())
        screen = parent.window().screen()
        available = screen.availableGeometry() if screen is not None else parent_frame
        if frame.left() < available.left():
            frame.moveLeft(available.left())
        if frame.top() < available.top():
            frame.moveTop(available.top())
        if frame.right() > available.right():
            frame.moveRight(available.right())
        if frame.bottom() > available.bottom():
            frame.moveBottom(available.bottom())
        self.move(frame.topLeft())

    def _position_over_parent_once(self) -> None:
        """Center the first show, then preserve ordinary user movement."""

        if self._native_position_initialized:
            return
        self._recenter_over_parent()
        self._native_position_initialized = True

    def present_over_parent(self) -> bool:
        """Present a movable native window in the owner's current Space."""

        try:
            if self.isVisible():
                self.raise_()
                return bool(self.isVisible())
            attached = self._attach_native_parent_before_show()
            if self._native_auxiliary_on_macos and not attached:
                logger.error(
                    "Anki Garden: refusing to expose a movable window before its macOS Space is attached"
                )
                return False
            if getattr(self, "_return_focus", None) is None:
                try:
                    focused = QApplication.focusWidget()
                    if focused is not None and not self.isAncestorOf(focused):
                        self._return_focus = focused
                except (AttributeError, NameError):
                    # Dependency-light method tests and headless probes do not
                    # necessarily provide a QApplication instance.
                    pass
            self._position_over_parent_once()
            self.show()
            if not self.isVisible():
                logger.error("Anki Garden: dialog presentation completed without a visible window")
                return False
            self.raise_()
            QTimer.singleShot(0, self._apply_initial_focus)
            return bool(self.isVisible())
        except Exception:
            logger.exception("Anki Garden: dialog presentation failed")
            return False

    def open(self) -> None:
        self.present_over_parent()

    def exec(self) -> int:
        """Run a dialog-compatible nested loop around the native shell."""

        if self._dialog_exec_active:
            logger.warning("Anki Garden: refusing a reentrant dialog exec loop")
            return int(QDialog.DialogCode.Rejected)
        self._dialog_exec_active = True
        previous_modal_requested = self._modal_requested
        previous_modality: Any | None = None
        try:
            previous_modality = self.windowModality()
            self._modal_requested = True
            self.setWindowModality(Qt.WindowModality.WindowModal)
            self._dialog_result = int(QDialog.DialogCode.Rejected)
            if not self.present_over_parent():
                return self._dialog_result
            event_loop = QEventLoop(self)
            self._dialog_event_loop = event_loop
            event_loop.exec()
            return int(self._dialog_result)
        finally:
            self._dialog_event_loop = None
            self._dialog_exec_active = False
            self._modal_requested = previous_modal_requested
            if previous_modality is not None:
                try:
                    self.setWindowModality(previous_modality)
                except RuntimeError:
                    logger.debug(
                        "Anki Garden: closed dialog modality could not be restored",
                        exc_info=True,
                    )

    def result(self) -> int:
        return int(self._dialog_result)

    def setResult(self, result: int) -> None:
        self._dialog_result = int(result)

    def accept(self) -> None:
        self.done(int(QDialog.DialogCode.Accepted))

    def reject(self) -> None:
        reason = self._pending_close_reason or DialogCloseReason.PROGRAMMATIC
        decision = self.evaluate_close_request(reason)
        self._last_close_decision = decision
        self.setProperty("lastCloseReason", decision.reason.value)
        self.setProperty(
            "closeBlockedBy",
            decision.blocked_by.value if decision.blocked_by is not None else "",
        )
        if not decision.allowed:
            self.close_request_blocked(decision)
            return
        self.done(int(QDialog.DialogCode.Rejected))

    def done(self, result: int) -> None:
        target = self._return_focus
        self._return_focus = None
        result_code = int(result)
        self._dialog_result = result_code
        self.hide()
        if result_code == int(QDialog.DialogCode.Accepted):
            self.accepted.emit()
        elif result_code == int(QDialog.DialogCode.Rejected):
            self.rejected.emit()
        self.finished.emit(result_code)
        event_loop = self._dialog_event_loop
        if event_loop is not None and event_loop.isRunning():
            event_loop.quit()
        if target is None:
            target = self._dialog_owner
        if target is not None:
            def restore() -> None:
                try:
                    if target.isVisible() and target.isEnabled():
                        target.setFocus(Qt.FocusReason.OtherFocusReason)
                except RuntimeError:
                    pass
            QTimer.singleShot(0, restore)

    def showEvent(self, event: Any) -> None:
        self._discover_scroll_regions()
        self._sync_footer_clearance()
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_initial_focus)

    def resizeEvent(self, event: Any) -> None:
        self._sync_footer_clearance()
        super().resizeEvent(event)

    def closeEvent(self, event: Any) -> None:
        self.request_close(DialogCloseReason.WINDOW_CLOSE)
        if self.isVisible():
            event.ignore()
        else:
            event.accept()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.request_close(DialogCloseReason.ESCAPE)
            event.accept()
            return
        super().keyPressEvent(event)


class GardenDialogHeader(QFrame):
    """Shared, non-scrolling dialog header surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dialogHeader", True)
        self.setProperty("gardenComponent", "dialog-header")


class GardenDialogFooter(QFrame):
    """Shared sticky action/footer surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("actionFooter", True)
        self.setProperty("gardenComponent", "dialog-footer")


class GardenButton(QPushButton):
    """Button with one canonical priority and effective hit target."""

    def __init__(
        self,
        label: str,
        parent: QWidget | None = None,
        *,
        variant: str = BUTTON_VARIANT_SECONDARY,
    ) -> None:
        super().__init__(str(label), parent)
        self.setProperty("gardenComponent", "button")
        _set_button_variant(self, variant)
        self.setAccessibleName(str(label))


class GardenIconButton(GardenButton):
    """Compact desktop icon control with a visible shared SVG glyph."""

    def __init__(
        self,
        icon_name: str,
        accessible_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("", parent, variant=BUTTON_VARIANT_TERTIARY)
        self.setProperty("gardenComponent", "icon-button")
        self.setProperty("visualControlSize", ICON_BUTTON_SIZE)
        self.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        self.setIcon(garden_icon(icon_name))
        self.setIconSize(QSize(16, 16))
        set_icon_accessible_name(
            self,
            accessible_name,
            tooltip=accessible_name,
            ensure_hit_target=False,
        )


class GardenDialog(DialogShell):
    """Shared four-region dialog shell: header, tabs, body, and optional footer."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        *,
        subtitle: str = "",
        show_close: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("gardenDialog")
        self.setStyleSheet(_garden_dialog_stylesheet())
        self._shell_layout = QVBoxLayout(self)
        self._shell_layout.setContentsMargins(24, 18, 24, 18)
        self._shell_layout.setSpacing(16)

        self.header = GardenDialogHeader(self)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(12)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(2)
        self.dialog_title = QLabel(title)
        self.dialog_title.setProperty("dialogTitle", True)
        self.dialog_title.setTextFormat(Qt.TextFormat.PlainText)
        self.dialog_title.setWordWrap(True)
        readable_header_width = text_column_width(
            max(1, int(self.dialog_title.fontMetrics().averageCharWidth()))
        )
        self.dialog_title.setMaximumWidth(readable_header_width)
        title_copy.addWidget(self.dialog_title)
        # Parent conditional children before changing visibility. Calling
        # setVisible(True) on a parentless widget creates a temporary top-level
        # NSWindow on macOS, which can animate Anki out of its full-screen
        # Space even though the eventual Garden shell is embedded.
        self.dialog_subtitle = QLabel(subtitle, self.header)
        self.dialog_subtitle.setProperty("dialogSubtitle", True)
        self.dialog_subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.dialog_subtitle.setWordWrap(True)
        self.dialog_subtitle.setMaximumWidth(readable_header_width)
        self.dialog_subtitle.setVisible(bool(subtitle))
        title_copy.addWidget(self.dialog_subtitle)
        self.header_layout.addLayout(title_copy, 1)
        self.top_close = self.create_inline_close_button(
            self.header,
            title=title,
        )
        self.top_close.setVisible(show_close)
        self.header_layout.addWidget(self.top_close, 0, Qt.AlignmentFlag.AlignTop)
        self._shell_layout.addWidget(self.header)

        self.tabs_region = QWidget()
        self.tabs_layout = QVBoxLayout(self.tabs_region)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(0)
        self.tabs_region.hide()
        self._shell_layout.addWidget(self.tabs_region)

        self.body_region = QWidget()
        self.body_layout = QVBoxLayout(self.body_region)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.body_region.setMinimumHeight(0)
        self.body_region.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._shell_layout.addWidget(self.body_region, 1)
        self._body_widgets: list[QWidget] = []
        self._dialog_state = DialogViewState.READY
        self._state_retry_callback: Callable[[], None] | None = None
        self.state_panel = QFrame(self.body_region)
        self.state_panel.setProperty("dialogStatePanel", True)
        state_layout = QVBoxLayout(self.state_panel)
        state_layout.setContentsMargins(20, 24, 20, 24)
        state_layout.setSpacing(12)
        state_layout.addStretch(1)
        self.state_message = QLabel("")
        self.state_message.setWordWrap(True)
        self.state_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_message.setAccessibleName("Dialog status")
        self.state_message.setMaximumWidth(readable_header_width)
        self.state_message.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.state_message)
        self.state_retry = QPushButton("Try again")
        _set_button_variant(self.state_retry, BUTTON_VARIANT_PRIMARY)
        self.state_retry.clicked.connect(self._run_state_retry)
        state_layout.addWidget(self.state_message)
        state_layout.addWidget(
            self.state_retry,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        state_layout.addStretch(1)
        self.state_panel.hide()
        self.body_layout.addWidget(self.state_panel, 1)

        self.footer = GardenDialogFooter(self)
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(0, 10, 0, 0)
        self.footer_layout.setSpacing(8)
        self.footer.hide()
        self._shell_layout.addWidget(self.footer)
        self.register_pinned_footer(self.footer)

    def set_dialog_title(self, title: str) -> None:
        self.setWindowTitle(title)
        self.dialog_title.setText(title)
        self.top_close.setAccessibleName(f"Close {title}")
        self.top_close.setToolTip(f"Close {title}")
        self.close_policy_changed()

    def set_tabs_widget(self, tabs: QWidget) -> None:
        self.tabs_layout.addWidget(tabs)
        self.tabs_region.show()

    def set_body_widget(self, body: QWidget) -> None:
        self.body_layout.insertWidget(
            max(0, self.body_layout.count() - 1),
            body,
            1,
        )
        self._body_widgets.append(body)
        if isinstance(body, QScrollArea):
            self.register_scroll_region(body)
        for scroll in body.findChildren(QScrollArea):
            if (
                scroll.verticalScrollBarPolicy()
                != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            ):
                self.register_scroll_region(scroll)

    def remove_body_widget(self, body: QWidget) -> None:
        """Stop managing a body that a specialized dialog replaces."""

        self.body_layout.removeWidget(body)
        self._body_widgets = [widget for widget in self._body_widgets if widget is not body]

    def _run_state_retry(self) -> None:
        callback = self._state_retry_callback
        if callback is not None:
            callback()

    def set_dialog_state(
        self,
        state: DialogViewState | str,
        message: str = "",
        *,
        retry: Callable[[], None] | None = None,
        retry_label: str = "Try again",
    ) -> None:
        state = DialogViewState(state)
        policy = dialog_view_policy(state)
        self._dialog_state = state
        self._state_retry_callback = retry
        ready = state is DialogViewState.READY
        self.setProperty("dialogState", state.value)
        self.setProperty("dialogBusy", policy.busy)
        self.setProperty("dialogFeedbackTone", policy.feedback_tone)
        self.setProperty("dialogRetryable", policy.retryable)
        self.state_panel.setProperty("dialogState", state.value)
        self.state_panel.setProperty("dialogBusy", policy.busy)
        self.state_panel.setProperty("feedbackTone", policy.feedback_tone)
        for widget in self._body_widgets:
            widget.setVisible(ready)
        self.state_panel.setVisible(not ready)
        if ready:
            self._state_focus_target = None
            self.state_message.setText("")
            self.state_message.setAccessibleDescription("")
            self.state_retry.hide()
            self._apply_initial_focus()
            return
        text = str(message or policy.fallback_message)
        self.state_message.setText(text)
        self.state_message.setAccessibleDescription(text)
        self.state_retry.setText(str(retry_label or "Try again"))
        self.state_retry.setVisible(
            policy.retryable and retry is not None
        )
        self.accessibility_announcer.announce(
            text,
            priority=(
                AnnouncementPriority.ASSERTIVE
                if policy.assertive
                else AnnouncementPriority.POLITE
            ),
            target=self.state_panel,
        )
        if self.state_retry.isVisible():
            self._state_focus_target = self.state_retry
        elif self.top_close.isVisible() and self.top_close.isEnabled():
            self._state_focus_target = self.top_close
        else:
            self._state_focus_target = self.state_message
        self._apply_initial_focus()

    def add_footer_widget(self, widget: QWidget, *, stretch_before: bool = False) -> None:
        if stretch_before and self.footer_layout.count() == 0:
            self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(widget)
        self.footer.show()
        QTimer.singleShot(0, self._sync_footer_clearance)


# Canonical release name; ``GardenDialog`` remains a source-compatible alias
# for existing feature dialogs while all call sites share this implementation.
GardenDialogShell = GardenDialog


def _garden_dialog_stylesheet() -> str:
    t = GARDEN_THEME
    return foundation_stylesheet() + f"""
        QWidget[gardenDialogShell='true'] {{ background:{t['dialog_surface']}; color:{t['text_primary']}; }}
        QFrame[dialogHeader='true'] {{ background:transparent; border:0; }}
        QLabel {{ color:{t['text_primary']}; font-size:14px; }}
        QLabel[dialogTitle='true'] {{ color:{t['text_primary']}; font-size:22px; font-weight:700; }}
        QLabel[dialogSubtitle='true'] {{ color:{t['text_secondary']}; font-size:13px; }}
        QPushButton[iconButton='true'] {{ min-width:{ICON_BUTTON_SIZE}px; max-width:{ICON_BUTTON_SIZE}px; min-height:{ICON_BUTTON_SIZE}px; max-height:{ICON_BUTTON_SIZE}px; padding:0; border-radius:8px; background:transparent; border:1px solid transparent; }}
        QPushButton[iconButton='true']:hover {{ background:{t['raised_surface']}; border-color:{t['subtle_border']}; }}
        QPushButton[iconButton='true']:focus {{ border:2px solid {t['focus_ring']}; }}
        QFrame[actionFooter='true'] {{ background:{t['dialog_surface']}; border-top:1px solid {t['subtle_border']}; }}
        QFrame[sectionCard='true'], QFrame[statSummary='true'] {{ background:{t['raised_surface']}; border:0; border-radius:12px; }}
        QFrame[progressRow='true'] {{ background:#102a22; border:1px solid {t['subtle_border']}; border-radius:9px; }}
        QFrame[appearanceCard='true'] {{ background:#102a22; border:1px solid {t['subtle_border']}; border-radius:9px; }}
        QLabel[collectibleIcon='true'] {{ color:{t['growth_accent']}; background:{t['selected_surface']}; border:1px solid {t['strong_border']}; border-radius:9px; font-size:20px; font-weight:800; }}
        QFrame[storyStage='true'] {{ background:#0c261f; border:1px solid #20483c; border-radius:9px; }}
        QFrame[storyStage='true'][storyStageState='complete'] {{ background:#123228; border-color:#4f806e; }}
        QFrame[storyStage='true'][storyStageState='current'] {{ background:#173b30; border:2px solid #e7c96a; }}
        QLabel[storyStageName='true'] {{ color:#cfe0d6; font-size:13px; font-weight:700; }}
        QLabel[detailStatus='true'] {{ color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 8px; font-size:13px; font-weight:700; }}
        QLabel[detailBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:800; }}
        QLabel[summaryLabel='true'] {{ color:{t['text_muted']}; font-size:13px; }}
        QLabel[summaryValue='true'] {{ color:{t['text_primary']}; font-size:30px; font-weight:700; }}
        QFrame[emptyState='true'] {{ background:{t['raised_surface']}; border:0; border-radius:10px; }}
        QLabel[emptyTitle='true'] {{ color:{t['text_primary']}; font-size:15px; font-weight:700; }}
        QLabel[emptyBody='true'] {{ color:{t['text_secondary']}; font-size:13px; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary'] {{ background:{t['action_accent']}; border:1px solid {t['action_border']}; color:{t['action_text']}; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary']:hover {{ background:{t['action_hover']}; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary']:pressed {{ background:{t['action_pressed']}; }}
        QLabel[fertilizedBadge='true'] {{ color:#d8ecff; background:#18384a; border:1px solid #5686a0; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; }}
        QLabel[fullyGrownBadge='true'] {{ color:#f3dda0; background:#3a3220; border:1px solid #817044; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; }}
        QPushButton[disclosureRow='true'] {{ min-height:{BUTTON_MIN_HEIGHT}px; text-align:left; padding:0 8px; color:{t['text_secondary']}; background:transparent; border:0; border-bottom:1px solid {t['subtle_border']}; border-radius:0; }}
        QPushButton[disclosureRow='true']:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QPushButton[disclosureRow='true']:focus {{ border:2px solid {t['focus_ring']}; }}
        QFrame[dataTable='true'] {{ background:transparent; border:0; }}
        QFrame[sideNavigation='true'] {{ background:transparent; border:0; }}
        QPushButton[sideNavItem='true'] {{ min-height:38px; max-height:38px; padding:0 14px; text-align:left; color:{t['text_secondary']}; background:transparent; border:0; border-left:3px solid transparent; border-radius:8px; font-size:14px; font-weight:600; }}
        QPushButton[sideNavItem='true']:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QPushButton[sideNavItem='true'][selected='true'] {{ color:{t['text_primary']}; background:{t['selected_surface']}; border-left:3px solid {t['growth_accent']}; }}
        QPushButton[sideNavItem='true']:focus {{ border:2px solid {t['focus_ring']}; border-left:3px solid {t['growth_accent']}; }}
        QCheckBox[toggleSwitch='true'] {{ min-height:34px; spacing:10px; color:{t['text_primary']}; border:2px solid transparent; border-radius:8px; }}
        QCheckBox[toggleSwitch='true']:focus {{ border-color:{t['focus_ring']}; }}
        QCheckBox[toggleSwitch='true']::indicator {{ width:0; height:0; border:0; }}
        QTabWidget::pane {{ border:0; background:{t['dialog_surface']}; top:-1px; }}
        QTabBar {{ background:{t['dialog_surface']}; border-bottom:1px solid {t['subtle_border']}; }}
        QTabBar::tab {{ min-height:38px; max-height:38px; padding:0 16px; margin-right:2px; color:{t['text_secondary']}; background:{t['dialog_surface']}; border:0; border-bottom:2px solid transparent; }}
        QTabBar::tab:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QTabBar::tab:selected {{ color:{t['text_primary']}; background:{t['raised_surface']}; border-bottom:2px solid {t['growth_accent']}; }}
        QTabBar::tab:focus {{ border:2px solid {t['focus_ring']}; border-bottom:2px solid {t['growth_accent']}; }}
        QScrollArea {{ background:transparent; border:0; }}
        QLineEdit, QTextEdit {{ color:{t['text_primary']}; background:#10241f; border:1px solid {t['subtle_border']}; border-radius:8px; padding:7px 9px; selection-background-color:{t['action_accent']}; }}
        QLineEdit {{ min-height:40px; max-height:40px; padding:0 10px; }}
        QLineEdit:hover, QTextEdit:hover {{ border-color:{t['strong_border']}; }}
        QLineEdit:focus, QTextEdit:focus {{ border:2px solid {t['focus_ring']}; padding:6px 8px; }}
        QScrollBar:vertical {{ width:10px; margin:2px; background:transparent; }}
        QScrollBar::handle:vertical {{ min-height:30px; border-radius:4px; background:#587066; }}
        QScrollBar::handle:vertical:hover {{ background:#789185; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
    """


def _busy_spinner_icon(frame: int, *, size: int = 16) -> QIcon:
    """Return one code-native spinner frame for an in-button busy state."""

    safe_size = max(12, int(size))
    pixmap = QPixmap(safe_size, safe_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    radius = max(3.0, safe_size / 2 - 2.0)
    center = safe_size / 2
    for index in range(8):
        alpha = 55 + ((index - int(frame)) % 8) * 24
        angle = (index / 8.0) * 2 * pi
        start = QPointF(
            center + cos(angle) * radius * 0.52,
            center + sin(angle) * radius * 0.52,
        )
        end = QPointF(
            center + cos(angle) * radius,
            center + sin(angle) * radius,
        )
        painter.setPen(QPen(QColor(18, 48, 36, min(255, alpha)), 1.8))
        painter.drawLine(start, end)
    painter.end()
    return QIcon(pixmap)


class ConfirmationDialog:
    """One confirmation contract for destructive or replacement actions."""

    @staticmethod
    def confirm(
        parent: QWidget,
        title: str,
        message: str,
        *,
        confirm_label: str,
        cancel_label: str = "Cancel",
    ) -> bool:
        box = QMessageBox(parent)
        box.setWindowTitle(UI_TEXT["app_title"])
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(title)
        box.setInformativeText(message)
        confirm = box.addButton(confirm_label, QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(cancel_label, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is confirm


class PurchaseConfirmationDialog(DialogShell):
    """One contextual confirmation, retry, and terminal-state purchase shell."""

    _COMMIT_TIMEOUT_MS = 10_000

    _REFRESHABLE_FAILURES = {
        PurchaseStatus.STALE_PRICE,
        PurchaseStatus.STALE_BALANCE,
        PurchaseStatus.STALE_TARGET,
    }

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        quote: PurchaseQuote,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.quote = quote
        self.request = PurchaseRequest.from_quote(
            quote,
            authorize_replacement=quote.replacement_required,
        )
        self.outcome: PurchaseOutcome | None = None
        self._submitting = False
        self.requested_route = ""
        self._primary_route_override = ""
        self._display_status = quote.status
        self.presentation = purchase_presentation(quote)
        self.fact_value_labels: dict[str, QLabel] = {}
        self._comparison_policy_minimum_height = 400
        self.setModal(True)
        self.configure_close_policy(protect_in_flight=True)
        self.apply_size_policy(DialogSizeClass.TRANSACTION)
        self._comparison_policy_minimum_height = self.minimumHeight()
        self.setStyleSheet(_garden_dialog_stylesheet())

        root = QVBoxLayout(self)
        self.purchase_root_layout = root
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(10)
        self.header = GardenDialogHeader(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        self.title_label = QLabel("")
        self.title_label.setProperty("dialogTitle", True)
        self.title_label.setProperty("dialogHeader", True)
        self.title_label.setWordWrap(True)
        header_layout.addWidget(self.title_label, 1)
        self.top_close = self.create_inline_close_button(
            self.header,
            title="purchase",
        )
        header_layout.addWidget(
            self.top_close,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        root.addWidget(self.header)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Purchase status")
        self.status.setProperty("liveRegion", "assertive")
        self.status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.status)
        root.addWidget(self.status)

        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_scroll.setAccessibleName("Purchase details")
        self.content_scroll.setProperty("dialogBody", True)
        self.content_host = QWidget()
        content = QVBoxLayout(self.content_host)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)

        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(14)
        self.artwork = ArtworkThumbnail()
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setProperty("itemPreview", True)
        self.summary_copy = QWidget()
        summary_copy_layout = QVBoxLayout(self.summary_copy)
        summary_copy_layout.setContentsMargins(0, 0, 0, 0)
        summary_copy_layout.setSpacing(5)
        self.item_name = QLabel("")
        self.item_name.setStyleSheet("font-size:20px; font-weight:800;")
        self.item_name.setWordWrap(True)
        self.category = QLabel("")
        self.category.setProperty("dialogSubtitle", True)
        self.outcome_label = QLabel("")
        self.outcome_label.setWordWrap(True)
        self.outcome_label.setStyleSheet("font-size:15px; font-weight:650;")
        summary_copy_layout.addWidget(self.item_name)
        summary_copy_layout.addWidget(self.category)
        self.badges_host = QWidget()
        self.badges_layout = QHBoxLayout(self.badges_host)
        self.badges_layout.setContentsMargins(0, 0, 0, 0)
        self.badges_layout.setSpacing(6)
        self.badges: list[QLabel] = []
        for _index in range(3):
            badge = QLabel("")
            badge.setProperty("detailBadge", True)
            badge.hide()
            self.badges_layout.addWidget(badge)
            self.badges.append(badge)
        self.badges_layout.addStretch(1)
        summary_copy_layout.addWidget(self.badges_host)
        summary_copy_layout.addWidget(self.outcome_label)
        self.summary_row.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        self.summary_row.addWidget(self.summary_copy, 1)
        content.addLayout(self.summary_row)

        self.proposal_notice = QLabel("")
        self.proposal_notice.setWordWrap(True)
        self.proposal_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.proposal_notice.setAccessibleName("Purchase proposal status")
        self.proposal_notice.setProperty("summarySupport", True)
        self.proposal_notice.hide()
        content.addWidget(self.proposal_notice)

        self.target_chip = QFrame()
        self.target_chip.setProperty("sectionCard", True)
        self.target_chip.setAccessibleName("Plant")
        target_layout = QHBoxLayout(self.target_chip)
        target_layout.setContentsMargins(10, 7, 12, 7)
        target_layout.setSpacing(9)
        self.target_artwork = ArtworkThumbnail()
        self.target_artwork.setFixedSize(42, 42)
        self.target_artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_artwork.setProperty("itemPreview", True)
        target_copy = QVBoxLayout()
        target_copy.setSpacing(0)
        target_label = QLabel("")
        target_label.setProperty("summaryLabel", True)
        target_label.hide()
        self.target_name = QLabel("")
        self.target_name.setStyleSheet("font-weight:750;")
        self.target_name.setWordWrap(True)
        target_copy.addWidget(target_label)
        target_copy.addWidget(self.target_name)
        target_layout.addWidget(self.target_artwork)
        target_layout.addLayout(target_copy, 1)
        content.addWidget(self.target_chip)

        self.outcome_heading = QLabel("")
        self.outcome_heading.setProperty("summaryLabel", True)
        content.addWidget(self.outcome_heading)
        self.facts_card = GardenOutcomePreview()
        facts_layout = self.facts_card.grid
        facts_layout.setContentsMargins(12, 8, 12, 8)
        facts_layout.setVerticalSpacing(0)
        self.fact_rows: list[tuple[QFrame, QLabel, QLabel]] = []
        for _index in range(4):
            row = QFrame()
            row.setProperty("purchaseFact", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 5, 0, 5)
            row_layout.setSpacing(10)
            label = QLabel("")
            label.setProperty("summaryLabel", True)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            value = QLabel("")
            value.setWordWrap(True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            row_layout.addWidget(label, 0)
            row_layout.addWidget(value, 1)
            facts_layout.addWidget(row, _index, 0, 1, 2)
            self.fact_rows.append((row, label, value))
        content.addWidget(self.facts_card)

        self.more_details_action = QPushButton("Details")
        self.more_details_action.setProperty("disclosureRow", True)
        self.more_details_action.setCheckable(True)
        self.more_details_action.setAccessibleName("Show more purchase details")
        self.more_details_action.toggled.connect(self._toggle_more_details)
        content.addWidget(self.more_details_action)
        self.more_details_copy = QLabel("")
        self.more_details_copy.setWordWrap(True)
        self.more_details_copy.setProperty("dialogSubtitle", True)
        self.more_details_copy.hide()
        content.addWidget(self.more_details_copy)

        self.comparison_host = QWidget()
        self.comparison = QHBoxLayout(self.comparison_host)
        self.comparison.setContentsMargins(0, 0, 0, 0)
        self.comparison.setSpacing(10)
        self.current_summary = self._comparison_card("Current")
        self.new_summary = self._comparison_card("New")
        self.comparison.addWidget(self.current_summary, 1)
        self.comparison.addWidget(self.new_summary, 1)
        content.addWidget(self.comparison_host)
        self.discard_warning = QLabel("")
        self.discard_warning.setWordWrap(True)
        self.discard_warning.setProperty("transactionWarning", True)
        self.discard_warning.setStyleSheet(
            "color:#f4e5aa; background:#3b3420; border:1px solid #7d6f3d; "
            "border-radius:8px; padding:8px 10px;"
        )
        set_semantic_role(
            self.discard_warning,
            SemanticRole.BANNER,
            tone=FeedbackTone.WARNING,
        )
        apply_tabular_numerals(self.discard_warning)

        self.content_scroll.setWidget(self.content_host)
        _set_scroll_surface(
            self.content_scroll,
            self.content_host,
            GARDEN_THEME["dialog_surface"],
        )
        root.addWidget(self.content_scroll, 1)
        self.register_scroll_region(self.content_scroll)
        root.addWidget(self.discard_warning)

        self.cost_summary = QFrame()
        self.cost_summary.setProperty("sectionCard", True)
        self.cost_summary.setAccessibleName("Purchase cost summary")
        cost_layout = QHBoxLayout(self.cost_summary)
        cost_layout.setContentsMargins(14, 9, 14, 9)
        cost_layout.setSpacing(14)
        self.price_label = QLabel("")
        self.price_label.setStyleSheet("font-size:18px; font-weight:800;")
        self.balance_label = QLabel("")
        self.balance_label.setWordWrap(True)
        self.balance_label.setStyleSheet("font-weight:650;")
        apply_tabular_numerals(self.price_label)
        apply_tabular_numerals(self.balance_label)
        cost_layout.addWidget(self.price_label)
        cost_layout.addStretch(1)
        cost_layout.addWidget(self.balance_label)
        root.addWidget(self.cost_summary)

        self.action_footer = QFrame()
        self.action_footer.setProperty("actionFooter", True)
        self.action_footer.setProperty("dialogFooter", True)
        self.actions = QHBoxLayout(self.action_footer)
        self.actions.setContentsMargins(0, 10, 0, 0)
        self.progress_reserve = QWidget()
        self.progress_reserve.setFixedWidth(32)
        progress_layout = QHBoxLayout(self.progress_reserve)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_indicator = QLabel("")
        self.progress_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_indicator.setAccessibleName("Purchase in progress")
        self.progress_indicator.setStyleSheet("font-size:18px; font-weight:800;")
        self.progress_indicator.hide()
        progress_layout.addWidget(self.progress_indicator)
        self.actions.addWidget(self.progress_reserve)
        self.progress_reserve.hide()
        self.actions.addStretch(1)
        self.cancel_action = QPushButton("")
        self.purchase_action = QPushButton("")
        self.replace_action = self.purchase_action
        _set_button_variant(self.cancel_action, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.purchase_action, BUTTON_VARIANT_PRIMARY)
        self.cancel_action.clicked.connect(self.reject)
        self.purchase_action.clicked.connect(self._activate_primary)
        self.actions.addWidget(self.cancel_action)
        self.actions.addWidget(self.purchase_action)
        root.addWidget(self.action_footer)
        self.register_pinned_footer(self.action_footer)
        self.setTabOrder(self.cancel_action, self.purchase_action)
        self.set_initial_focus(self.cancel_action, InitialFocusPolicy.SAFE_ACTION)

        self.summary_responsive = AdaptiveSplit.for_box_layout(
            "purchase-confirmation.summary",
            AdaptiveRegion.measured("artwork", self.artwork, floor=180),
            AdaptiveRegion.measured("summary-copy", self.summary_copy, floor=324),
            layout=self.summary_row,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=14,
            telemetry_target=self,
        )
        self.comparison_responsive = AdaptiveSplit.for_box_layout(
            "fertilizer-replacement.comparison",
            AdaptiveRegion.measured(
                "current-fertilizer", self.current_summary, floor=220
            ),
            AdaptiveRegion.measured("new-fertilizer", self.new_summary, floor=220),
            layout=self.comparison,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=10,
            telemetry_target=self.comparison_host,
        )
        self.actions_responsive = AdaptiveRow.for_box_layout(
            "purchase-confirmation.actions",
            (
                AdaptiveRegion.measured("cancel", self.cancel_action, floor=128),
                AdaptiveRegion.measured("purchase", self.purchase_action, floor=180),
            ),
            layout=self.actions,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.action_footer,
        )

        self._remaining_timer = QTimer(self)
        self._remaining_timer.setInterval(1_000)
        self._remaining_timer.timeout.connect(self._update_remaining_time)
        self._progress_frame_index = 0
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(140)
        self._progress_timer.timeout.connect(self._advance_progress_indicator)
        self._commit_watchdog = QTimer(self)
        self._commit_watchdog.setSingleShot(True)
        self._commit_watchdog.setInterval(self._COMMIT_TIMEOUT_MS)
        self._commit_watchdog.timeout.connect(self._transaction_timed_out)
        config = getattr(self.engine, "config", None)
        value = getattr(config, "value", None)
        self._progress_motion_enabled = effective_motion_enabled(
            bool(value("enable_animations", True)) if callable(value) else True,
            bool(value("reduced_motion", False)) if callable(value) else False,
            os_reader=read_system_reduced_motion,
        )
        self.finished.connect(lambda _result: self._remaining_timer.stop())
        self.finished.connect(lambda _result: self._progress_timer.stop())
        self.finished.connect(lambda _result: self._commit_watchdog.stop())
        self._apply_quote(quote)
        if quote.replacement_required or quote.disposition is PurchaseDisposition.EXTENDED:
            self._remaining_timer.start()
        self._update_responsive_layout(self.width())

    def _populate_artwork(
        self,
        quote: PurchaseQuote,
        presentation: PurchasePresentation,
    ) -> None:
        self.artwork.setText("")
        self.artwork.setAccessibleName(f"{quote.item_name} artwork")
        self.artwork.setAccessibleDescription("")
        self.artwork.setProperty("gardenRole", "")
        if quote.kind is PurchaseKind.SPECIES:
            source = _asset_preview_label(
                self.engine,
                quote.item_id,
                GROWTH_STAGES[0],
                size=72,
                property_name="nurseryArtwork",
            )
            self.artwork.setFixedSize(72, 72)
            pixmap = source.pixmap()
            self.artwork.setPixmap(
                pixmap if pixmap is not None else _purchase_placeholder_pixmap(quote.kind, 72, 72)
            )
            self.artwork.setAccessibleDescription(source.accessibleDescription())
            if source.property("gardenRole") == SemanticRole.MISSING_ART.value:
                set_semantic_role(self.artwork, SemanticRole.MISSING_ART)
            return
        if presentation.preview_style is PurchasePreviewStyle.LANDSCAPE:
            self.artwork.setFixedSize(132, 76)
            item = (
                WEATHER_CATALOG.get(quote.item_id)
                if quote.kind is PurchaseKind.WEATHER
                else SCENERY_CATALOG.get(quote.item_id)
            )
            artwork_available = False
            if item is not None:
                try:
                    resolver = (
                        self.engine.resolve_weather_preview_asset
                        if quote.kind is PurchaseKind.WEATHER
                        else self.engine.resolve_scenery_preview_asset
                    )
                    resolved = resolver(item.item_id)
                    path = getattr(resolved, "path", None)
                    artwork_available = bool(
                        path and not _preview_source_pixmap(path).isNull()
                    )
                except Exception:
                    logger.exception(
                        "Anki Garden: purchase artwork resolution failed for %s",
                        quote.item_id,
                    )
            pixmap = (
                _environment_preview_pixmap(
                    self.engine,
                    item,
                    128,
                    72,
                    scenery_id=str(self.engine.state.selected_background),
                )
                if item is not None
                else _environment_placeholder_pixmap(
                    128,
                    72,
                    category=quote.kind.value,
                    item_key=quote.item_id,
                    source_path=None,
                )
            )
            self.artwork.setPixmap(pixmap)
            if not artwork_available:
                set_semantic_role(self.artwork, SemanticRole.MISSING_ART)
                self.artwork.setAccessibleDescription(
                    f"Artwork unavailable for {quote.item_name}; a "
                    f"{quote.kind.value} category placeholder is shown."
                )
            return
        if presentation.preview_style is PurchasePreviewStyle.GARDEN_BED:
            self.artwork.setFixedSize(180, 94)
            self.artwork.setPixmap(_garden_bed_purchase_preview(
                self.engine,
                quote.item_id,
                176,
                90,
            ))
            self.artwork.setAccessibleDescription(
                f"Garden preview with {quote.item_name} highlighted."
            )
            return
        source = _item_preview_label(
            self.engine,
            quote.artwork_key,
            f"{quote.item_name} artwork",
            size=72,
            placeholder_kind=quote.kind,
        )
        self.artwork.setFixedSize(72, 72)
        pixmap = source.pixmap()
        missing_art = (
            source.property("gardenRole") == SemanticRole.MISSING_ART.value
        )
        self.artwork.setPixmap(
            _purchase_placeholder_pixmap(quote.kind, 72, 72)
            if pixmap is None
            else pixmap
        )
        if missing_art:
            set_semantic_role(self.artwork, SemanticRole.MISSING_ART)
            self.artwork.setAccessibleDescription(
                source.accessibleDescription()
                or f"{quote.category} artwork is unavailable; a category placeholder is shown."
            )

    def _populate_target(self, quote: PurchaseQuote, presentation: PurchasePresentation) -> None:
        self.target_name.setText(presentation.target_name)
        self.target_chip.setVisible(bool(presentation.target_name))
        if not presentation.target_name:
            return
        plant = self.engine.plant_story(str(quote.target_id or ""))
        if plant is None:
            self.target_artwork.setPixmap(
                _purchase_placeholder_pixmap(PurchaseKind.SPECIES, 42, 42)
            )
            self.target_artwork.setAccessibleName("Plant artwork unavailable")
            self.target_artwork.setAccessibleDescription(
                "Plant artwork is unavailable; a botanical placeholder is shown."
            )
            set_semantic_role(
                self.target_artwork,
                SemanticRole.MISSING_ART,
            )
            return
        _populate_asset_preview(
            self.target_artwork,
            self.engine,
            plant.species,
            plant.growth_stage,
            size=42,
            fallback_text=plant.name,
        )
        self.target_artwork.setAccessibleName(f"{plant.name} artwork")

    def _comparison_card(self, heading_text: str) -> QFrame:
        card = QFrame()
        card.setProperty("sectionCard", True)
        card.setMinimumWidth(0)
        box = QVBoxLayout(card)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(5)
        heading = QLabel(heading_text)
        heading.setProperty("dialogSubtitle", True)
        name = QLabel("")
        name.setProperty("purchaseComparisonName", True)
        name.setStyleSheet("font-weight:700;")
        name.setWordWrap(True)
        effect = QLabel("")
        effect.setProperty("purchaseComparisonEffect", True)
        effect.setWordWrap(True)
        duration = QLabel("")
        duration.setProperty("purchaseComparisonDuration", True)
        duration.setWordWrap(True)
        apply_tabular_numerals(duration)
        box.addWidget(heading)
        box.addWidget(name)
        box.addWidget(effect)
        box.addWidget(duration)
        card.name_label = name
        card.effect_label = effect
        card.duration_label = duration
        return card

    def _apply_quote(self, quote: PurchaseQuote) -> None:
        self.quote = quote
        presentation = purchase_presentation(quote)
        self._render_presentation(presentation, status=quote.status)
        if quote.ready:
            self._clear_status()
        else:
            self._show_failure(quote.status, quote.message)

    @staticmethod
    def _transaction_state(status: PurchaseStatus) -> str:
        if status is PurchaseStatus.READY:
            return "ready"
        if status is PurchaseStatus.SUCCESS:
            return "success"
        if status in {
            PurchaseStatus.STALE_PRICE,
            PurchaseStatus.STALE_BALANCE,
            PurchaseStatus.STALE_TARGET,
        }:
            return "stale-proposal"
        if status is PurchaseStatus.PERSISTENCE_FAILURE:
            return "persistence-failure"
        if status is PurchaseStatus.REQUEST_ID_CONFLICT:
            return "recoverable-failure"
        return "business-rule-blocked"

    @staticmethod
    def _failure_tone(status: PurchaseStatus) -> FeedbackTone:
        if status in {
            PurchaseStatus.ALREADY_OWNED,
            PurchaseStatus.STALE_BALANCE,
        }:
            return FeedbackTone.INFO
        if status in {
            PurchaseStatus.INSUFFICIENT_COINS,
            PurchaseStatus.ITEM_UNAVAILABLE,
            PurchaseStatus.TARGET_INVALID,
            PurchaseStatus.STALE_PRICE,
            PurchaseStatus.STALE_TARGET,
            PurchaseStatus.REPLACEMENT_REQUIRED,
        }:
            return FeedbackTone.WARNING
        return FeedbackTone.ERROR

    def _render_presentation(
        self,
        presentation: PurchasePresentation,
        *,
        status: PurchaseStatus | None = None,
    ) -> None:
        self.presentation = presentation
        display_status = PurchaseStatus(status or self.quote.status)
        self._display_status = display_status
        self._primary_route_override = ""
        self.setProperty("purchaseState", display_status.value)
        self.setProperty(
            "transactionState",
            self._transaction_state(display_status),
        )
        self.setProperty(
            "transactionPresentation",
            "retry-preview"
            if display_status is PurchaseStatus.PERSISTENCE_FAILURE
            else "updated-proposal"
            if display_status in {
                PurchaseStatus.STALE_PRICE,
                PurchaseStatus.STALE_BALANCE,
                PurchaseStatus.STALE_TARGET,
            }
            else "committed-state"
            if presentation.terminal
            else "proposal",
        )
        self.setWindowTitle(presentation.title)
        self.title_label.setText(presentation.title)
        self.item_name.setText(presentation.item_name)
        self.item_name.setVisible(bool(presentation.show_item_name))
        self.category.setText(presentation.category)
        self.category.setVisible(bool(presentation.show_category))
        self.outcome_label.setText(
            presentation.outcome
            if display_status in {PurchaseStatus.READY, PurchaseStatus.SUCCESS}
            else ""
        )
        self.outcome_label.setVisible(bool(self.outcome_label.text()))
        self._populate_artwork(self.quote, presentation)
        self.artwork.setVisible(presentation.show_preview)
        for index, badge in enumerate(self.badges):
            text = presentation.badges[index] if index < len(presentation.badges) else ""
            badge.setText(text)
            badge.setVisible(bool(text))
        self.badges_host.setVisible(bool(presentation.badges))
        self._populate_target(self.quote, presentation)

        # Stale and failed attempts use the single status banner. The outcome
        # rows remain authoritative without per-cell Preview/Proposed labels.
        self.proposal_notice.setText("")
        self.proposal_notice.setAccessibleDescription("")
        self.proposal_notice.hide()

        self.fact_value_labels = {}
        for index, (row, label, value) in enumerate(self.fact_rows):
            fact = presentation.facts[index] if index < len(presentation.facts) else None
            row.setVisible(fact is not None)
            if fact is None:
                label.setText("")
                value.setText("")
                continue
            label.setText(str(fact.label))
            label.setVisible(bool(fact.label))
            value.setText(str(fact.value))
            value.setStyleSheet("font-weight:750;" if fact.emphasized else "")
            if fact.key in {"inventory", "remaining"}:
                apply_tabular_numerals(value)
            self.fact_value_labels[fact.key] = value
        self.facts_card.setVisible(
            bool(presentation.facts) and not self.quote.replacement_required
        )
        self.outcome_heading.setVisible(self.facts_card.isVisible())

        details_text = "\n".join(
            f"{fact.label}: {fact.value}" if fact.label else fact.value
            for fact in presentation.more_details
        )
        self.more_details_copy.setText(details_text)
        self.more_details_action.setVisible(bool(details_text))
        if not details_text:
            self.more_details_action.setChecked(False)
            self.more_details_copy.hide()

        replacement = False
        self.comparison_host.setVisible(replacement)
        self.discard_warning.setVisible(replacement)
        if replacement:
            self.current_summary.name_label.setText(self.quote.current_item_name)
            self.current_summary.effect_label.setText(self.quote.current_effect)
            self.current_summary.duration_label.setText(self.quote.current_duration)
            self.new_summary.name_label.setText(self.quote.item_name)
            self.new_summary.effect_label.setText(
                _purchase_fact(
                    presentation,
                    "effect",
                    self.quote.descriptor.buff,
                )
            )
            self.new_summary.duration_label.setText(self.quote.descriptor.duration)
            self._update_remaining_time()

        self.cost_summary.setVisible(presentation.show_cost)
        if presentation.show_cost:
            self.price_label.setText(f"{presentation.price:,} Garden Coins")
            self.balance_label.setText(
                ""
                if presentation.balance_after is None
                else format_balance_after(presentation.balance_after)
            )

        self.cancel_action.setText(presentation.secondary_label)
        self.cancel_action.setAccessibleName(presentation.secondary_label)
        self.cancel_action.setVisible(bool(presentation.secondary_label))
        primary_label = presentation.primary_label
        primary_accessible_name = presentation.primary_accessible_name
        if display_status is PurchaseStatus.TARGET_INVALID:
            self._primary_route_override = "garden"
            primary_label = "Choose plant"
            primary_accessible_name = "Choose another plant in the Garden"
        self.purchase_action.setText(_qt_button_text(primary_label))
        self.purchase_action.setMinimumWidth(max(
            96,
            self.purchase_action.fontMetrics().horizontalAdvance(
                max(
                    primary_label,
                    presentation.processing_label,
                    key=len,
                )
            ) + 34,
        ))
        self.purchase_action.setAccessibleName(primary_accessible_name)
        self.purchase_action.setAccessibleDescription(
            presentation.outcome
            if not (self._primary_route_override or presentation.primary_route)
            else primary_accessible_name
        )
        enabled = bool(
            self._primary_route_override
            or presentation.primary_route
            or presentation.retry
            or self.quote.ready
        ) and not self._submitting
        set_control_enabled(
            self.purchase_action,
            enabled,
            disabled_reason="Purchase is being saved." if self._submitting else self.quote.message,
            enabled_description=self.purchase_action.accessibleDescription(),
        )
        view_profile = (
            "error"
            if display_status is not PurchaseStatus.READY
            else "complex"
            if (
                self.quote.replacement_required
                or bool(presentation.target_name)
                or len(presentation.facts) >= 3
            )
            else "simple"
        )
        self.apply_view_size_profile(view_profile)
        self._update_responsive_layout(self.width())

    def _toggle_more_details(self, checked: bool) -> None:
        self.more_details_copy.setVisible(bool(checked))
        self.more_details_action.setText(
            "Hide details" if checked else "Details"
        )
        self.more_details_action.setAccessibleName(
            "Hide additional purchase details" if checked else "Show more purchase details"
        )

    def _activate_primary(self) -> None:
        route = self._primary_route_override or self.presentation.primary_route
        if route:
            self.requested_route = route
            self.reject()
            return
        self._submit()

    def _current_fertilizer_status(self) -> FertilizerStatus | None:
        if self.quote.kind is not PurchaseKind.FERTILIZER or not self.quote.target_id:
            return None
        plant = self.engine.plant_story(self.quote.target_id)
        if plant is None:
            return None
        now = (
            self.engine._now_seconds()
            if callable(getattr(self.engine, "_now_seconds", None))
            else time.time()
        )
        return fertilizer_status(self.engine, plant, now=now)

    def _update_remaining_time(self) -> None:
        if self.quote.kind is not PurchaseKind.FERTILIZER:
            return
        current = self._current_fertilizer_status()
        if self.quote.replacement_required and current is not None:
            self.current_summary.name_label.setText(current.name)
            self.current_summary.effect_label.setText(current.effect)
        if (
            self.quote.disposition is PurchaseDisposition.EXTENDED
            and current is not None
            and current.active
            and "remaining" in self.fact_value_labels
        ):
            self.fact_value_labels["remaining"].setText(
                f"{compact_duration(current.seconds_remaining)} → "
                f"{compact_duration(current.seconds_remaining + self.quote.duration_seconds)}"
            )
        if not self.quote.replacement_required:
            return
        duration = (
            current.duration
            if current is not None and current.active
            else "No active time remaining"
        )
        seconds = current.seconds_remaining if current is not None else 0
        self.current_summary.duration_label.setText(duration)
        remaining_copy = (
            str(duration)
            .removesuffix(" remaining")
            .removesuffix(" left")
            .lower()
        )
        self.discard_warning.setText("")
        self.discard_warning.hide()

    def _set_submitting(self, submitting: bool) -> None:
        self._submitting = bool(submitting)
        self.set_dialog_in_flight(self._submitting)
        self.setProperty(
            "purchaseState",
            "loading" if self._submitting else self.quote.status.value,
        )
        self.setProperty(
            "transactionState",
            "committing"
            if self._submitting
            else self._transaction_state(self._display_status),
        )
        self.progress_indicator.hide()
        if self._submitting:
            self._progress_frame_index = 0
            self._advance_progress_indicator()
            if self._progress_motion_enabled:
                self._progress_timer.start()
        else:
            self._progress_timer.stop()
            self.purchase_action.setIcon(QIcon())
        self.purchase_action.setProperty("busy", self._submitting)
        action_style = self.purchase_action.style()
        if action_style is not None:
            action_style.unpolish(self.purchase_action)
            action_style.polish(self.purchase_action)
        self.purchase_action.setText(
            self.presentation.processing_label
            if self._submitting
            else _qt_button_text(
                "Choose plant"
                if self._primary_route_override == "garden"
                else self.presentation.primary_label
            )
        )
        self.purchase_action.setAccessibleName(
            self.presentation.processing_label.replace("…", "")
            if self._submitting
            else (
                "Choose another plant in the Garden"
                if self._primary_route_override == "garden"
                else self.presentation.primary_accessible_name
            )
        )
        set_control_enabled(
            self.purchase_action,
            not self._submitting and (
                self.quote.ready or self.presentation.retry
            ),
            disabled_reason=(
                "Purchase is being saved."
                if self._submitting
                else self.quote.message or "Purchase is not currently available."
            ),
            enabled_description=self.purchase_action.accessibleDescription(),
        )
        set_control_enabled(
            self.cancel_action,
            not self._submitting,
            disabled_reason="Purchase is being saved.",
            enabled_description="Cancel without spending Garden Coins.",
        )
        if self._submitting:
            self.accessibility_announcer.announce(
                self.presentation.processing_label,
                priority=AnnouncementPriority.POLITE,
                target=self.purchase_action,
            )

    def _advance_progress_indicator(self) -> None:
        """Animate the sole busy indicator inside the primary action."""

        if not self._submitting:
            self.purchase_action.setIcon(QIcon())
            return
        if self._progress_motion_enabled:
            self._progress_frame_index = (self._progress_frame_index + 1) % 8
        self.purchase_action.setIcon(
            _busy_spinner_icon(self._progress_frame_index)
        )
        self.purchase_action.setIconSize(QSize(16, 16))

    def _submit(self) -> None:
        if self._submitting or not (self.quote.ready or self.presentation.retry):
            return
        self._clear_status()
        self.setProperty("transactionTimedOut", False)
        self._set_submitting(True)
        self._commit_watchdog.start()
        QTimer.singleShot(0, self._commit)

    def _commit(self) -> None:
        if not self._submitting:
            return
        try:
            outcome = self.engine.confirm_purchase(self.request)
        except Exception:
            logger.exception("Anki Garden: purchase confirmation failed unexpectedly")
            self._commit_watchdog.stop()
            self._set_submitting(False)
            self._show_failure(
                PurchaseStatus.PERSISTENCE_FAILURE,
                "No Garden Coins were spent.",
            )
            return
        self._commit_watchdog.stop()
        self.outcome = outcome
        if outcome.success:
            self.presentation = purchase_presentation(
                self.quote,
                ignore_status=True,
            )
            self._set_submitting(False)
            self.setProperty("purchaseState", PurchaseStatus.SUCCESS.value)
            self.setProperty("transactionState", "success")
            self.setProperty("transactionPresentation", "committed-result")
            announcement = (
                f"{outcome.message} Spent {outcome.amount_spent:,} Garden Coins. "
                f"Balance: {outcome.new_balance:,} Garden Coins."
            )
            self.accessibility_announcer.announce(
                announcement,
                priority=AnnouncementPriority.POLITE,
                target=self,
            )
            self.accept()
            return
        if outcome.status in self._REFRESHABLE_FAILURES:
            refreshed = self.engine.quote_purchase(
                self.request.kind,
                self.request.item_id,
                quantity=self.request.quantity,
                target_id=self.request.target_id,
            )
            self.request = PurchaseRequest.from_quote(
                refreshed,
                authorize_replacement=refreshed.replacement_required,
            )
            self._set_submitting(False)
            self.quote = refreshed
            if outcome.status is PurchaseStatus.STALE_BALANCE and refreshed.ready:
                self._render_presentation(
                    purchase_presentation(refreshed, ignore_status=True),
                    status=PurchaseStatus.READY,
                )
                self._clear_status()
                return
            self._render_presentation(
                purchase_presentation(
                    refreshed,
                    status=outcome.status,
                    message=outcome.message,
                ),
                status=outcome.status,
            )
            if refreshed.ready:
                self._show_status_banner(
                    outcome.status,
                    outcome.message,
                )
            return
        self._set_submitting(False)
        self._show_failure(outcome.status, outcome.message)

    def _transaction_timed_out(self) -> None:
        """Return an uncommitted attempt to the same replay-safe request."""

        if not self._submitting:
            return
        self.setProperty("transactionTimedOut", True)
        self._set_submitting(False)
        self._show_failure(
            PurchaseStatus.PERSISTENCE_FAILURE,
            "No Garden Coins were spent.",
        )

    def _clear_status(self) -> None:
        self.status.setText("")
        self.status.setAccessibleDescription("")
        self.status.setStyleSheet("background:transparent; border:0;")
        self.status.hide()

    def _show_failure(self, status: PurchaseStatus, message: str) -> None:
        copy = str(message or "The purchase could not be completed. Try again.")
        self._render_presentation(
            purchase_presentation(self.quote, status=status, message=copy),
            status=status,
        )
        self._show_status_banner(status, self.presentation.outcome, compact=True)

    def _show_status_banner(
        self,
        status: PurchaseStatus,
        message: str,
        *,
        compact: bool = False,
    ) -> None:
        copy = str(message or "The purchase could not be completed.")
        tone = self._failure_tone(status)
        visible_copy = {
            PurchaseStatus.PERSISTENCE_FAILURE: (
                "No Garden Coins were spent."
            ),
            PurchaseStatus.INSUFFICIENT_COINS: (
                self.presentation.outcome
            ),
            PurchaseStatus.ALREADY_OWNED: (
                self.presentation.outcome
            ),
            PurchaseStatus.STALE_PRICE: (
                self.presentation.outcome
            ),
            PurchaseStatus.STALE_BALANCE: (
                self.presentation.outcome
            ),
            PurchaseStatus.STALE_TARGET: (
                self.presentation.outcome
            ),
            PurchaseStatus.TARGET_INVALID: (
                self.presentation.outcome
            ),
            PurchaseStatus.ITEM_UNAVAILABLE: (
                self.presentation.outcome
            ),
        }.get(status, copy)
        self.setProperty("purchaseState", status.value)
        self.setProperty("transactionState", self._transaction_state(status))
        if status in {
            PurchaseStatus.STALE_PRICE,
            PurchaseStatus.STALE_BALANCE,
            PurchaseStatus.STALE_TARGET,
        }:
            self.setProperty("transactionPresentation", "updated-proposal")
        elif status is PurchaseStatus.PERSISTENCE_FAILURE:
            self.setProperty("transactionPresentation", "retry-preview")
        self.status.setText(visible_copy)
        self.status.setAccessibleDescription(
            ". ".join(part for part in (self.presentation.title, visible_copy) if part)
        )
        style = {
            FeedbackTone.INFO: (
                "color:#d8eee5; background:#17352c; border:1px solid #416b5d; "
            ),
            FeedbackTone.WARNING: (
                "color:#f4e5aa; background:#3b3420; border:1px solid #7d6f3d; "
            ),
            FeedbackTone.ERROR: (
                "color:#ffd7d1; background:#4a2424; border:1px solid #8d4a47; "
            ),
        }[tone]
        self.status.setStyleSheet(
            style + "border-radius:8px; padding:8px 10px;"
        )
        set_semantic_role(self.status, SemanticRole.BANNER, tone=tone)
        self.status.setVisible(bool(visible_copy))
        if visible_copy:
            self.status.setFocus()
        self._update_responsive_layout(self.width())
        if visible_copy:
            self.accessibility_announcer.announce(
                self.status.accessibleDescription(),
                priority=(
                    AnnouncementPriority.ASSERTIVE
                    if tone is FeedbackTone.ERROR
                    else AnnouncementPriority.POLITE
                ),
                target=self.status,
            )

    def _update_responsive_layout(self, width: int) -> None:
        # These dialogs are intentionally content-fit and therefore shorter
        # than 480 px in ordinary desktop use. Height alone must not collapse
        # the readable transaction hierarchy into a dense sentence.
        short_viewport = int(width) < 560
        self.purchase_root_layout.setContentsMargins(
            14 if short_viewport else 22,
            10 if short_viewport else 20,
            14 if short_viewport else 22,
            10 if short_viewport else 18,
        )
        self.purchase_root_layout.setSpacing(6 if short_viewport else 10)
        margins = self.layout().contentsMargins()
        available = max(0, int(width) - margins.left() - margins.right())
        summary = self.summary_responsive.evaluate(available)
        comparison = (
            self.comparison_responsive.evaluate(available)
            if self.quote.replacement_required
            else summary
        )
        actions = self.actions_responsive.evaluate(available)
        self.setProperty("comparisonMode", comparison.mode)
        self.setProperty("actionMode", actions.mode)
        self.setProperty("layoutMode", comparison.mode)
        # The replacement consequence belongs in the single summary sentence;
        # duplicate before/after cards and warning rows stay out of the dialog.
        replacement_visible = False
        self.artwork.setVisible(bool(self.presentation.show_preview))
        self.summary_copy.show()
        self.target_chip.setVisible(
            bool(self.presentation.target_name)
        )
        self.facts_card.setVisible(
            bool(self.presentation.facts)
            and not self.quote.replacement_required
        )
        proposal_copy = self.proposal_notice.text().strip()
        self.proposal_notice.setVisible(bool(proposal_copy))
        details_text = self.more_details_copy.text().strip()
        self.more_details_action.setVisible(bool(details_text))
        self.more_details_copy.setVisible(
            bool(details_text)
            and self.more_details_action.isChecked()
        )
        self.comparison_host.setVisible(replacement_visible)
        self.content_scroll.show()
        self.discard_warning.setVisible(replacement_visible)
        self.setProperty("decisionSummaryCondensed", False)
        self.setProperty("replacementSummaryCondensed", False)
        QTimer.singleShot(
            0,
            lambda: self.fit_content_to_family(
                breathing_room=8,
                preserve_transition=not self.presentation.terminal,
            ),
        )

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "summary_responsive"):
            self._update_responsive_layout(event.size().width())
        super().resizeEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.request_close(DialogCloseReason.ESCAPE)
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self) -> None:
        super().reject()

    def closeEvent(self, event: Any) -> None:
        super().closeEvent(event)


# Canonical release name. The established class remains the implementation so
# package fixtures and third-party imports keep working while purchases and
# Growth Charge use share the transaction anatomy and primitives.
GardenTransactionDialog = PurchaseConfirmationDialog


class FertilizerReplacementDialog(PurchaseConfirmationDialog):
    """Named compatibility surface for a replacement-mode purchase quote."""

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        quote: PurchaseQuote,
    ) -> None:
        super().__init__(parent, engine, quote)
        self.setProperty("windowFamily", type(self).__name__)


class GrowthChargeConfirmationDialog(GardenDialog):
    """Target-specific, replay-safe Growth Charge confirmation and receipt."""

    _COMMIT_TIMEOUT_MS = 10_000

    _REFRESHABLE_FAILURES = {
        GrowthChargeStatus.STALE_INVENTORY,
        GrowthChargeStatus.STALE_TARGET,
        GrowthChargeStatus.TARGET_INVALID,
        GrowthChargeStatus.PERSISTENCE_FAILURE,
    }

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        target_id: str,
        *,
        open_nursery: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            "Growth Charges",
            subtitle="",
        )
        self.engine = engine
        self.target_id = str(target_id)
        self.open_nursery_callback = open_nursery
        self.quote: Any | None = None
        self.request: GrowthChargeRequest | None = None
        self.outcome: Any | None = None
        self._submitting = False
        self._completed = False
        self._primary_route = ""
        self.setModal(True)
        self.configure_close_policy(protect_in_flight=True)
        self.apply_size_policy(
            DialogSizeClass.GROWTH_CHARGE,
        )
        self.apply_view_size_profile("ready")

        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_scroll.setAccessibleName("Growth Charge confirmation details")
        self.content_host = QWidget()
        content = QVBoxLayout(self.content_host)
        self.content_layout = content
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(12)

        self.alert = QLabel("")
        self.alert.setWordWrap(True)
        self.alert.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.alert)
        self.alert.setAccessibleName("Growth Charge status")
        self.alert.setProperty("liveRegion", "assertive")
        self.alert.hide()
        content.addWidget(self.alert)

        self.hero = QFrame()
        self.hero.setProperty("detailHero", True)
        hero_layout = QHBoxLayout(self.hero)
        self.hero_layout = hero_layout
        hero_layout.setContentsMargins(14, 12, 14, 12)
        hero_layout.setSpacing(14)
        self.target_artwork = ArtworkThumbnail()
        self.target_artwork.setFixedSize(68, 68)
        self.target_artwork.setScaledContents(True)
        self.target_artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_artwork.setAccessibleName("Plant image")
        hero_layout.addWidget(self.target_artwork, 0, Qt.AlignmentFlag.AlignTop)
        identity = QVBoxLayout()
        identity.setSpacing(4)
        target_kicker = QLabel("")
        self.target_kicker = target_kicker
        target_kicker.setProperty("summaryLabel", True)
        target_kicker.hide()
        self.target_name = QLabel("")
        self.target_name.setWordWrap(True)
        self.target_name.setStyleSheet("font-size:20px; font-weight:800;")
        self.target_stage = QLabel("")
        self.target_stage.setProperty("detailBadge", True)
        self.target_stage.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        identity.addWidget(target_kicker)
        identity.addWidget(self.target_name)
        identity.addWidget(self.target_stage, 0, Qt.AlignmentFlag.AlignLeft)
        hero_layout.addLayout(identity, 1)
        content.addWidget(self.hero)

        selector_card = QFrame()
        selector_card.setProperty("sectionCard", True)
        selector_layout = QVBoxLayout(selector_card)
        self.selector_layout = selector_layout
        selector_layout.setContentsMargins(12, 10, 12, 10)
        selector_layout.setSpacing(6)
        selector_label = QLabel("")
        self.selector_label = selector_label
        selector_label.setProperty("summaryLabel", True)
        selector_label.hide()
        self.charge_selector = QComboBox()
        self.charge_selector.setAccessibleName("Choose a Growth Charge")
        self.charge_selector.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.charge_selector.currentIndexChanged.connect(self._selection_changed)
        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.charge_selector)
        self.static_charge_row = GardenItemRow()
        static_charge_layout = QHBoxLayout(self.static_charge_row)
        static_charge_layout.setContentsMargins(10, 7, 10, 7)
        static_charge_layout.setSpacing(10)
        self.static_charge_art = ArtworkThumbnail()
        self.static_charge_art.setFixedSize(44, 44)
        self.static_charge_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.static_charge_name = QLabel("")
        self.static_charge_name.setProperty("rowTitle", True)
        self.static_charge_quantity = QLabel("")
        self.static_charge_quantity.setProperty("summaryLabel", True)
        apply_tabular_numerals(self.static_charge_quantity)
        static_charge_layout.addWidget(self.static_charge_art)
        static_charge_layout.addWidget(self.static_charge_name, 1)
        static_charge_layout.addWidget(self.static_charge_quantity)
        self.static_charge_row.hide()
        selector_layout.addWidget(self.static_charge_row)
        content.addWidget(selector_card)
        self.selector_card = selector_card

        self.nursery_action = QPushButton("Open Nursery")
        self.nursery_action.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _set_button_variant(self.nursery_action, BUTTON_VARIANT_PRIMARY)
        self.nursery_action.clicked.connect(self._open_nursery)
        self._ready_title = self.windowTitle()
        self._empty_inventory_title = "No Growth Charges"
        self.empty_inventory = EmptyState(
            self._empty_inventory_title,
            "Earn one from rewards or buy one in the Nursery.",
        )
        self.empty_inventory.hide()
        content.addWidget(self.empty_inventory)

        self.compact_summary_card = QFrame()
        self.compact_summary_card.setProperty("transactionPresentation", "preview")
        self.compact_summary_card.setAccessibleName("Growth Charge result")
        set_semantic_role(
            self.compact_summary_card,
            SemanticRole.BANNER,
            tone=FeedbackTone.INFO,
        )
        compact_summary_layout = QVBoxLayout(self.compact_summary_card)
        compact_summary_layout.setContentsMargins(8, 6, 8, 6)
        compact_summary_layout.setSpacing(0)
        self.compact_summary = QLabel("")
        self.compact_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.compact_summary.setWordWrap(True)
        self.compact_summary.setProperty("summarySupport", True)
        self.compact_summary.setAccessibleName("Growth Charge result")
        compact_summary_layout.addWidget(self.compact_summary)
        self.compact_summary_card.hide()
        content.addWidget(self.compact_summary_card)

        self.preview_banner = QFrame()
        self.preview_banner.setProperty("transactionPresentation", "preview")
        self.preview_banner.setProperty("previewMode", "initial")
        self.preview_banner.setAccessibleName(
            "Growth Charge outcome status"
        )
        set_semantic_role(
            self.preview_banner,
            SemanticRole.BANNER,
            tone=FeedbackTone.INFO,
        )
        preview_layout = QVBoxLayout(self.preview_banner)
        preview_layout.setContentsMargins(12, 9, 12, 9)
        preview_layout.setSpacing(0)
        self.preview_notice = QLabel("")
        self.preview_notice.setWordWrap(True)
        self.preview_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_notice.setProperty("summarySupport", True)
        preview_layout.addWidget(self.preview_notice)
        content.addWidget(self.preview_banner)

        self.outcome_heading = QLabel("")
        self.outcome_heading.setProperty("summaryLabel", True)
        self.outcome_heading.hide()
        content.addWidget(self.outcome_heading)
        self.facts_card = GardenOutcomePreview()
        self.fact_values: dict[str, QLabel] = {}
        content.addWidget(self.facts_card)

        self.receipt = QFrame()
        self.receipt.setProperty("sectionCard", True)
        receipt_layout = QVBoxLayout(self.receipt)
        receipt_layout.setContentsMargins(14, 12, 14, 12)
        self.receipt_title = QLabel("")
        self.receipt_title.setStyleSheet("font-size:18px; font-weight:800;")
        self.receipt_title.hide()
        self.charge_heading = QLabel("")
        self.charge_heading.setProperty("summaryLabel", True)
        self.charge_heading.hide()
        self.receipt_copy = QLabel("")
        self.receipt_copy.setWordWrap(True)
        self.receipt_copy.setTextFormat(Qt.TextFormat.PlainText)
        self.stage_rewards_heading = QLabel("")
        self.stage_rewards_heading.setProperty("summaryLabel", True)
        self.stage_rewards_heading.hide()
        self.reward_chips = QWidget()
        self.reward_chips_layout = QHBoxLayout(self.reward_chips)
        self.reward_chips_layout.setContentsMargins(0, 4, 0, 0)
        self.reward_chips_layout.setSpacing(6)
        receipt_layout.addWidget(self.receipt_title)
        receipt_layout.addWidget(self.charge_heading)
        receipt_layout.addWidget(self.receipt_copy)
        receipt_layout.addWidget(self.stage_rewards_heading)
        receipt_layout.addWidget(self.reward_chips)
        self.receipt.hide()
        content.addWidget(self.receipt)

        self.content_scroll.setWidget(self.content_host)
        _set_scroll_surface(
            self.content_scroll,
            self.content_host,
            GARDEN_THEME["dialog_surface"],
        )
        self.set_body_widget(self.content_scroll)

        self.cancel_action = QPushButton("Cancel")
        self.use_action = QPushButton("Use charge")
        for button in (self.cancel_action, self.nursery_action, self.use_action):
            button.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _set_button_variant(self.cancel_action, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.use_action, BUTTON_VARIANT_PRIMARY)
        self.cancel_action.clicked.connect(self.reject)
        self.use_action.clicked.connect(self._activate_primary)
        self.progress_indicator = QLabel("")
        self.progress_indicator.setAccessibleName("Growth Charge in progress")
        self.progress_indicator.setStyleSheet("font-size:18px; font-weight:800;")
        self.progress_indicator.hide()
        self._progress_frame_index = 0
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(140)
        self._progress_timer.timeout.connect(self._advance_progress_indicator)
        self._commit_watchdog = QTimer(self)
        self._commit_watchdog.setSingleShot(True)
        self._commit_watchdog.setInterval(self._COMMIT_TIMEOUT_MS)
        self._commit_watchdog.timeout.connect(self._transaction_timed_out)
        config = getattr(self.engine, "config", None)
        value = getattr(config, "value", None)
        self._progress_motion_enabled = effective_motion_enabled(
            bool(value("enable_animations", True)) if callable(value) else True,
            bool(value("reduced_motion", False)) if callable(value) else False,
            os_reader=read_system_reduced_motion,
        )
        self.finished.connect(lambda _result: self._progress_timer.stop())
        self.finished.connect(lambda _result: self._commit_watchdog.stop())
        self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(self.cancel_action)
        self.footer_layout.addWidget(self.nursery_action)
        self.footer_layout.addWidget(self.use_action)
        self.footer.show()
        self.set_initial_focus(self.cancel_action, InitialFocusPolicy.SAFE_ACTION)
        self.setTabOrder(self.charge_selector, self.cancel_action)
        self.setTabOrder(self.cancel_action, self.nursery_action)
        self.setTabOrder(self.nursery_action, self.use_action)
        self._populate_inventory()
        self._update_responsive_layout(self.width(), self.height())

    @staticmethod
    def _compact_preview_copy(quote: Any) -> str:
        """Show only the Growth result and optional numeric progress."""

        if quote is None or not bool(getattr(quote, "ready", False)):
            return ""
        lines = [f"+{max(0, int(quote.granted_growth)):,} Growth"]
        current_growth = max(0, int(quote.current_growth))
        projected_growth = max(0, int(quote.projected_growth))
        if current_growth != projected_growth:
            lines.append(f"{current_growth:,} → {projected_growth:,}")
        return "\n".join(lines)

    def _refresh_compact_summary(self) -> None:
        copy = self._compact_preview_copy(self.quote)
        self.compact_summary.setText(copy)
        self.compact_summary.setAccessibleDescription(copy)
        self.compact_summary_card.setVisible(bool(copy) and not self._completed)

    def _update_responsive_layout(self, width: int, height: int) -> None:
        """Keep the exact consequence above the action at the minimum size."""

        compact = int(width) <= 480 or int(height) <= 480
        self.setProperty("layoutMode", "compact" if compact else "default")
        self._shell_layout.setContentsMargins(
            16 if compact else 24,
            10 if compact else 18,
            16 if compact else 24,
            10 if compact else 18,
        )
        self._shell_layout.setSpacing(8 if compact else 16)
        self.content_layout.setSpacing(6 if compact else 12)
        self.hero_layout.setContentsMargins(
            8 if compact else 14,
            5 if compact else 12,
            8 if compact else 14,
            5 if compact else 12,
        )
        self.hero_layout.setSpacing(9 if compact else 14)
        artwork_size = 52 if compact else 68
        self.target_artwork.setFixedSize(artwork_size, artwork_size)
        self.target_kicker.hide()
        self.target_name.setStyleSheet(
            f"font-size:{17 if compact else 20}px; font-weight:800;"
        )
        self.selector_layout.setContentsMargins(
            8 if compact else 12,
            4 if compact else 10,
            8 if compact else 12,
            4 if compact else 10,
        )
        self.selector_layout.setSpacing(3 if compact else 6)
        self.selector_label.hide()
        self.charge_selector.setMinimumHeight(36 if compact else BUTTON_MIN_HEIGHT)
        self.dialog_subtitle.setVisible(
            not compact and bool(self.dialog_subtitle.text())
        )

        self.preview_banner.hide()
        self.content_host.updateGeometry()
        QTimer.singleShot(
            0,
            lambda: self.fit_content_to_family(
                breathing_room=8,
                preserve_transition=not self._completed,
            ),
        )

    def _eligible_charge_ids(self) -> list[str]:
        inventory = getattr(self.engine.state, "consumables", {})
        return [
            charge_id
            for charge_id in GROWTH_CHARGES
            if max(0, int(inventory.get(charge_id, 0) or 0)) > 0
        ]

    def _populate_inventory(
        self,
        *,
        preferred: str = "",
        show_status: bool = True,
    ) -> None:
        available = self._eligible_charge_ids()
        self.charge_selector.blockSignals(True)
        self.charge_selector.clear()
        for charge_id in available:
            spec = GROWTH_CHARGES[charge_id]
            quantity = max(
                0,
                int(self.engine.state.consumables.get(charge_id, 0) or 0),
            )
            self.charge_selector.addItem(
                f"{spec.name} · {quantity:,} available",
                charge_id,
            )
        if preferred in available:
            self.charge_selector.setCurrentIndex(available.index(preferred))
        self.charge_selector.blockSignals(False)
        has_inventory = bool(available)
        self.selector_card.setVisible(has_inventory)
        self.empty_inventory.setVisible(not has_inventory)
        self.hero.setVisible(has_inventory)
        self.facts_card.hide()
        self.outcome_heading.hide()
        self.cancel_action.setVisible(True)
        self.cancel_action.setText("Cancel" if has_inventory else "Close")
        self.nursery_action.setVisible(not has_inventory)
        self.use_action.setVisible(has_inventory)
        self.set_dialog_title(
            self._ready_title if has_inventory else self._empty_inventory_title
        )
        if has_inventory:
            one_charge = len(available) == 1
            selected_id = available[self.charge_selector.currentIndex()]
            selected_spec = GROWTH_CHARGES[selected_id]
            selected_quantity = max(
                0,
                int(self.engine.state.consumables.get(selected_id, 0) or 0),
            )
            self.charge_selector.setVisible(not one_charge)
            self.selector_label.hide()
            self.static_charge_name.setText(selected_spec.name)
            charge_art = _item_preview_label(
                self.engine,
                selected_id,
                f"{selected_spec.name} artwork",
                size=44,
                placeholder_kind=PurchaseKind.GROWTH_CHARGE,
            )
            charge_pixmap = charge_art.pixmap()
            self.static_charge_art.setPixmap(
                charge_pixmap if charge_pixmap is not None else QPixmap()
            )
            self.static_charge_art.setAccessibleName(charge_art.accessibleName())
            self.static_charge_quantity.setText(
                f"{selected_quantity:,} available"
            )
            self.static_charge_art.hide()
            self.static_charge_name.hide()
            self.static_charge_row.setVisible(one_charge)
            self._refresh_quote(
                selected_id,
                show_status=show_status,
            )
        else:
            self.quote = None
            self.request = None
            self._render_target_without_charge()
            self.setProperty("growthChargeState", GrowthChargeStatus.EMPTY_INVENTORY.value)
            self.preview_banner.hide()
            self.static_charge_row.hide()
            self.compact_summary_card.hide()
        self.apply_view_size_profile("ready" if has_inventory else "empty")
        self._refresh_compact_summary()
        self._update_responsive_layout(self.width(), self.height())

    def _render_target_without_charge(self) -> None:
        plant = self.engine.plant_story(self.target_id)
        if plant is None:
            self.target_name.setText("Plant unavailable")
            self.target_stage.setText("Unavailable")
            self.target_artwork.setPixmap(_botanical_placeholder_pixmap(68, 68))
            return
        self.target_name.setText(str(plant.name))
        self.target_stage.setText(format_status_label(plant.growth_stage))
        _populate_asset_preview(
            self.target_artwork,
            self.engine,
            plant.species,
            plant.growth_stage,
            size=68,
            fallback_text=plant.name,
        )

    def _selection_changed(self, _index: int) -> None:
        charge_id = str(self.charge_selector.currentData() or "")
        if charge_id:
            self._clear_alert()
            self._refresh_quote(charge_id)

    @staticmethod
    def _stage_reward_copy(rewards: Any, *, empty: str) -> str:
        entries: list[str] = []
        for reward in tuple(rewards or ()):
            amount = max(0, int(getattr(reward, "garden_coins", 0) or 0))
            coin_label = "Garden Coin" if amount == 1 else "Garden Coins"
            entries.append(
                f"{format_status_label(str(getattr(reward, 'stage', '') or 'Stage'))} "
                f"earned {amount:,} {coin_label}"
            )
        return "; ".join(entries) if entries else str(empty)

    @staticmethod
    def _preview_fact_values(quote: Any, reward_copy: str) -> dict[str, str]:
        del reward_copy
        return {
            "growth": f"+{max(0, int(quote.granted_growth)):,} Growth",
            "progress": (
                f"{max(0, int(quote.current_growth)):,} → "
                f"{max(0, int(quote.projected_growth)):,}"
            ),
        }

    @staticmethod
    def _uncommitted_quote_copy(quote: Any) -> str:
        if quote.status is GrowthChargeStatus.TARGET_INVALID:
            return "This plant can’t use a Growth Charge.\nYour charge was not used."
        if quote.status is GrowthChargeStatus.STALE_INVENTORY:
            return ""
        if quote.status is GrowthChargeStatus.STALE_TARGET:
            return ""
        if quote.status is GrowthChargeStatus.PERSISTENCE_FAILURE:
            return "Your charge was not used."
        else:
            return str(
                getattr(quote, "message", "")
                or "This Growth Charge can’t be used."
            )

    @staticmethod
    def _failed_outcome_copy(
        outcome: Any,
        *,
        retry_available: bool,
        previous_inventory: int | None = None,
    ) -> str:
        del retry_available, previous_inventory
        if outcome.status is GrowthChargeStatus.PERSISTENCE_FAILURE:
            return "Your charge was not used."
        elif outcome.status is GrowthChargeStatus.TARGET_INVALID:
            return "This plant can’t use a Growth Charge.\nYour charge was not used."
        elif outcome.status in {
            GrowthChargeStatus.STALE_INVENTORY,
            GrowthChargeStatus.STALE_TARGET,
        }:
            return ""
        return "Your charge was not used."

    @staticmethod
    def _committed_receipt_copy(outcome: Any, reward_copy: str) -> str:
        del reward_copy
        remaining = max(0, int(outcome.inventory_remaining))
        charge_label = "charge" if remaining == 1 else "charges"
        return (
            f"+{max(0, int(outcome.growth_granted)):,} Growth · "
            f"{remaining:,} {charge_label} left"
        )

    def _set_preview_mode(self, mode: str, copy: str) -> None:
        self.preview_banner.setProperty("previewMode", str(mode))
        self.preview_notice.setText(str(copy))
        self.preview_banner.setAccessibleName(
            f"Growth Charge {str(mode).replace('_', ' ')} outcome"
        )
        # The section heading already establishes that the rows are an outcome
        # preview. State-specific guidance belongs in the single alert banner.
        self.preview_banner.hide()

    def _render_committed_target(self, outcome: Any) -> None:
        stage = format_status_label(str(outcome.resulting_stage))
        self.target_name.setText(str(outcome.target_name))
        self.target_stage.setText(stage)
        plant = self.engine.plant_story(str(outcome.target_id))
        species = str(getattr(plant, "species", "") or "")
        if species:
            _populate_asset_preview(
                self.target_artwork,
                self.engine,
                species,
                str(outcome.resulting_stage),
                size=68,
                fallback_text=str(outcome.target_name),
            )
        else:
            _record_missing_artwork(
                category="plant",
                item_key=str(outcome.target_id),
                source_path=None,
            )
            self.target_artwork.setPixmap(
                _missing_artwork_pixmap("plant", 68, 68)
            )
        self.target_artwork.setAccessibleName(
            f"{outcome.target_name}, {stage} stage, committed result"
        )

    def _refresh_quote(self, charge_id: str, *, show_status: bool = True) -> None:
        quote = self.engine.quote_growth_charge(charge_id, self.target_id)
        self.quote = quote
        request = GrowthChargeRequest.from_quote(quote)
        if (
            self.request is None
            or self.request.fingerprint() != request.fingerprint()
        ):
            self.request = request
        self._primary_route = ""
        self.setProperty("growthChargeState", quote.status.value)
        target_state = GrowthChargeTargetState(quote.target_state)
        stage_name = format_status_label(quote.target_stage)
        target_state_label = format_status_label(target_state.value)
        self.target_name.setText(
            " · ".join(part for part in (quote.target_name, stage_name) if part)
        )
        self.target_stage.setText(
            "" if target_state is GrowthChargeTargetState.ELIGIBLE
            else target_state_label
        )
        self.target_stage.setVisible(
            target_state is not GrowthChargeTargetState.ELIGIBLE
        )
        self.target_stage.setAccessibleName("Plant status")
        self.target_stage.setAccessibleDescription(
            ". ".join(filter(None, (
                f"{quote.target_name}, {stage_name}",
                target_state_label
                if target_state is not GrowthChargeTargetState.ELIGIBLE
                else "",
            )))
        )
        _populate_asset_preview(
            self.target_artwork,
            self.engine,
            quote.target_species,
            quote.target_stage,
            size=68,
            fallback_text=quote.target_name,
        )
        self.facts_card.set_rows([])
        self.fact_values = {}
        self.facts_card.hide()
        self.outcome_heading.hide()
        self._set_preview_mode(
            "ready" if quote.ready else "unavailable",
            "",
        )
        set_control_enabled(
            self.use_action,
            (quote.ready or quote.status is GrowthChargeStatus.TARGET_INVALID)
            and not self._submitting,
            disabled_reason="This charge can’t be used right now.",
            enabled_description=(
                "Close this dialog and choose another plant."
                if quote.status is GrowthChargeStatus.TARGET_INVALID
                else f"Use one {quote.charge_name} on {quote.target_name}."
            ),
        )
        if quote.status is GrowthChargeStatus.TARGET_INVALID:
            self._primary_route = "choose_plant"
            self.set_dialog_title("Choose another plant")
            self.use_action.setText("Choose plant")
            self.use_action.setAccessibleName("Choose plant")
            self.hero.setProperty("invalidTarget", True)
            self.hero.show()
            self.selector_card.show()
            self.compact_summary_card.hide()
            self.cancel_action.hide()
        else:
            self.hero.setProperty("invalidTarget", False)
            self.set_dialog_title(f"Use {quote.charge_name}?")
            self.use_action.setText("Use charge")
            self.use_action.setAccessibleName(f"Use {quote.charge_name}")
            self.hero.show()
            self.selector_card.show()
            self.cancel_action.show()
        if (
            show_status
            and not quote.ready
            and quote.status is not GrowthChargeStatus.EMPTY_INVENTORY
        ):
            alert_copy = self._uncommitted_quote_copy(quote)
            if alert_copy:
                self._show_alert(alert_copy, quote.status)
        self.apply_view_size_profile("ready" if quote.ready else "error")
        self._refresh_compact_summary()
        self._update_responsive_layout(self.width(), self.height())

    def _activate_primary(self) -> None:
        if self._completed:
            self.accept()
            return
        if self._primary_route == "choose_plant":
            self.accept()
            return
        if self._submitting or self.quote is None or not self.quote.ready:
            return
        self._submitting = True
        self.set_dialog_in_flight(True)
        self.setProperty("transactionTimedOut", False)
        self.setProperty("growthChargeState", "loading")
        self.apply_view_size_profile("loading")
        self.progress_indicator.hide()
        self.use_action.setText("Using charge…")
        self.use_action.setProperty("busy", True)
        self._progress_frame_index = 0
        self._advance_progress_indicator()
        if self._progress_motion_enabled:
            self._progress_timer.start()
        set_control_enabled(
            self.use_action,
            False,
            disabled_reason="Please wait.",
        )
        set_control_enabled(
            self.cancel_action,
            False,
            disabled_reason="Please wait.",
        )
        self.charge_selector.setEnabled(False)
        self.accessibility_announcer.announce(
            "Using charge…",
            priority=AnnouncementPriority.POLITE,
            target=self.use_action,
        )
        self._commit_watchdog.start()
        QTimer.singleShot(0, self._commit)

    def _commit(self) -> None:
        quote = self.quote
        request = self.request
        if not self._submitting or quote is None or request is None:
            return
        try:
            outcome = self.engine.confirm_growth_charge(request)
        except Exception:
            logger.exception("Anki Garden: Growth Charge confirmation failed unexpectedly")
            outcome = None
        self._commit_watchdog.stop()
        self._submitting = False
        self.set_dialog_in_flight(False)
        self._progress_timer.stop()
        self.use_action.setIcon(QIcon())
        self.progress_indicator.hide()
        self.charge_selector.setEnabled(True)
        self.use_action.setProperty("busy", False)
        set_control_enabled(
            self.cancel_action,
            True,
            enabled_description="Cancel without using a Growth Charge.",
        )
        self.use_action.setText("Use charge")
        if outcome is not None and outcome.success:
            self._show_receipt(outcome)
            return
        status = (
            outcome.status
            if outcome is not None
            else GrowthChargeStatus.PERSISTENCE_FAILURE
        )
        selected = quote.charge_id
        if outcome is None:
            self._populate_inventory(preferred=selected, show_status=False)
            retry_available = bool(self.quote is not None and self.quote.ready)
            if retry_available:
                self.use_action.setText("Try again")
                self.use_action.setAccessibleName("Try Growth Charge again")
            self.apply_view_size_profile("error")
            self.set_dialog_title("Couldn’t use the Growth Charge")
            self.cancel_action.setText("Close")
            self.hero.hide()
            self.selector_card.show()
            self.compact_summary_card.hide()
            self._show_alert(
                "Your charge was not used.",
                status,
            )
            return
        self._show_failed_outcome(outcome, selected)

    def _transaction_timed_out(self) -> None:
        """Restore a retryable view without minting a second request id."""

        quote = self.quote
        if not self._submitting or quote is None:
            return
        self.setProperty("transactionTimedOut", True)
        self._submitting = False
        self.set_dialog_in_flight(False)
        self._progress_timer.stop()
        self.use_action.setIcon(QIcon())
        self.progress_indicator.hide()
        self.charge_selector.setEnabled(True)
        self.use_action.setProperty("busy", False)
        set_control_enabled(
            self.cancel_action,
            True,
            enabled_description="Cancel without using a Growth Charge.",
        )
        self._populate_inventory(preferred=quote.charge_id, show_status=False)
        if self.quote is not None and self.quote.ready:
            self.use_action.setText("Try again")
            self.use_action.setAccessibleName("Try Growth Charge again")
        self.apply_view_size_profile("error")
        self.set_dialog_title("Couldn’t use the Growth Charge")
        self.cancel_action.setText("Close")
        self.hero.hide()
        self.selector_card.show()
        self.compact_summary_card.hide()
        self._show_alert(
            "Your charge was not used.",
            GrowthChargeStatus.PERSISTENCE_FAILURE,
        )

    def _advance_progress_indicator(self) -> None:
        if not self._submitting:
            self.use_action.setIcon(QIcon())
            return
        if self._progress_motion_enabled:
            self._progress_frame_index = (self._progress_frame_index + 1) % 8
        self.use_action.setIcon(
            _busy_spinner_icon(self._progress_frame_index)
        )
        self.use_action.setIconSize(QSize(16, 16))

    def _show_failed_outcome(self, outcome: Any, selected: str) -> None:
        self.outcome = outcome
        self._populate_inventory(preferred=selected, show_status=False)
        retry_available = bool(self.quote is not None and self.quote.ready)
        if outcome.status in {
            GrowthChargeStatus.STALE_INVENTORY,
            GrowthChargeStatus.STALE_TARGET,
        } and (
            self.quote is None
            or self.quote.status is not GrowthChargeStatus.TARGET_INVALID
        ):
            # Quantity and Growth refreshes do not change the requested effect.
            # Keep the newly quoted count/result visible without interrupting.
            self._clear_alert()
            self.setProperty("growthChargeState", outcome.status.value)
            self.cancel_action.setText(
                "Cancel" if self.quote is not None else "Close"
            )
            self.cancel_action.show()
            self.apply_view_size_profile(
                "ready" if self.quote is not None else "empty"
            )
            self._refresh_compact_summary()
            return

        display_status = (
            GrowthChargeStatus.TARGET_INVALID
            if self.quote is not None
            and self.quote.status is GrowthChargeStatus.TARGET_INVALID
            else outcome.status
        )
        self.hero.setProperty(
            "invalidTarget",
            display_status is GrowthChargeStatus.TARGET_INVALID,
        )
        self.compact_summary_card.hide()
        self.facts_card.hide()
        self.outcome_heading.hide()
        self.apply_view_size_profile("error")
        if display_status is GrowthChargeStatus.TARGET_INVALID:
            self.hero.show()
            self.selector_card.show()
            self._primary_route = "choose_plant"
            self.set_dialog_title("Choose another plant")
            self.cancel_action.setText("Cancel")
            self.cancel_action.hide()
            self.use_action.setText("Choose plant")
            self.use_action.setAccessibleName("Choose plant")
            self.use_action.show()
            set_control_enabled(
                self.use_action,
                True,
                enabled_description="Close this dialog and choose another plant.",
            )
        else:
            self.hero.hide()
            self.selector_card.show()
            self.set_dialog_title("Couldn’t use the Growth Charge")
            self.cancel_action.setText("Close")
            self.cancel_action.show()
            self.use_action.setText("Try again")
            self.use_action.setAccessibleName("Try Growth Charge again")
            self.use_action.setVisible(retry_available)
            set_control_enabled(
                self.use_action,
                retry_available,
                disabled_reason="This charge can’t be used right now.",
                enabled_description="Try using the Growth Charge again.",
            )
        self._show_alert(
            self._failed_outcome_copy(
                outcome,
                retry_available=retry_available,
            ),
            display_status,
        )

    def _show_receipt(self, outcome: Any) -> None:
        self.outcome = outcome
        if not outcome.completed_stages:
            self.accessibility_announcer.announce(
                str(outcome.message),
                priority=AnnouncementPriority.POLITE,
                target=self,
            )
            self.accept()
            return
        self._completed = True
        self.setProperty("growthChargeState", GrowthChargeStatus.SUCCESS.value)
        self.apply_view_size_profile("success")
        self._clear_alert()
        reward_copy = self._stage_reward_copy(
            outcome.rewards,
            empty="",
        )
        self._render_committed_target(outcome)
        self.hero.hide()
        self.target_stage.hide()
        self.charge_heading.hide()
        previous_stage = format_status_label(str(outcome.previous_stage))
        resulting_stage = format_status_label(str(outcome.resulting_stage))
        stage_transition = f"{previous_stage} → {resulting_stage}"
        self.receipt_title.setText(stage_transition)
        self.receipt_title.setAccessibleName("Plant stage transition")
        self.receipt_title.show()
        self.receipt_copy.setText(
            self._committed_receipt_copy(outcome, reward_copy)
        )
        while self.reward_chips_layout.count():
            item = self.reward_chips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        reward_total = sum(
            max(0, int(getattr(reward, "garden_coins", 0) or 0))
            for reward in tuple(outcome.rewards or ())
        )
        if reward_total:
            self.reward_chips_layout.addWidget(
                GardenBadge(
                    f"+{reward_total:,} Garden Coins",
                    tone=FeedbackTone.SUCCESS,
                )
            )
        self.reward_chips_layout.addStretch(1)
        self.stage_rewards_heading.hide()
        self.reward_chips.setVisible(bool(reward_total))
        self.receipt.setAccessibleName("Growth Charge result")
        self.receipt.setAccessibleDescription(
            " ".join(part for part in (
                stage_transition,
                self.receipt_copy.text(),
                f"+{reward_total:,} Garden Coins" if reward_total else "",
            ) if part)
        )
        set_semantic_role(
            self.receipt,
            SemanticRole.BANNER,
            tone=FeedbackTone.SUCCESS,
        )
        self.receipt.show()
        self.selector_card.hide()
        self.empty_inventory.hide()
        self.preview_banner.hide()
        self.facts_card.hide()
        self.outcome_heading.hide()
        self.cancel_action.setText("Close")
        self.cancel_action.hide()
        self.nursery_action.hide()
        self.use_action.setText("View plant")
        self.use_action.setAccessibleName(f"View {outcome.target_name}")
        set_control_enabled(
            self.use_action,
            True,
            enabled_description=f"Return to {outcome.target_name}.",
        )
        set_control_enabled(
            self.cancel_action,
            True,
            enabled_description="Close this committed receipt.",
        )
        self.charge_selector.setEnabled(False)
        self.set_dialog_title(f"{outcome.target_name} reached {resulting_stage}")
        self.dialog_subtitle.setText("")
        self.receipt.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.receipt)
        self.receipt.setFocus()
        self.accessibility_announcer.announce(
            self.receipt_copy.text(),
            priority=AnnouncementPriority.POLITE,
            target=self.receipt,
        )
        self._update_responsive_layout(self.width(), self.height())
        QTimer.singleShot(
            0,
            lambda: self.fit_content_to_family(
                breathing_room=8,
                preserve_transition=False,
            ),
        )

    def _show_alert(self, message: str, status: GrowthChargeStatus) -> None:
        copy = str(message or "This charge can’t be used right now.")
        is_error = status is GrowthChargeStatus.PERSISTENCE_FAILURE
        tone = FeedbackTone.ERROR if is_error else FeedbackTone.WARNING
        alert_palette = (
            "color:#ffd7d1; background:#4a2424; border:1px solid #8d4a47; "
            if is_error
            else "color:#ffe0a3; background:#4a3820; border:1px solid #8b6b2e; "
        )
        self.setProperty("growthChargeState", status.value)
        self.alert.setText(copy)
        self.alert.setAccessibleName(
            "Growth Charge error" if is_error else "Growth Charge warning"
        )
        self.alert.setAccessibleDescription(copy)
        self.alert.setStyleSheet(
            alert_palette + "border-radius:8px; padding:8px 10px;"
        )
        self.alert.setProperty("liveRegion", "assertive" if is_error else "polite")
        set_semantic_role(self.alert, SemanticRole.BANNER, tone=tone)
        self.alert.show()
        self.alert.setFocus()
        self.accessibility_announcer.announce(
            self.alert.accessibleDescription(),
            priority=(
                AnnouncementPriority.ASSERTIVE
                if is_error
                else AnnouncementPriority.POLITE
            ),
            target=self.alert,
        )

    def _clear_alert(self) -> None:
        self.alert.clear()
        self.alert.setAccessibleDescription("")
        self.alert.hide()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, "compact_summary_card"):
            self._update_responsive_layout(
                event.size().width(),
                event.size().height(),
            )

    def _open_nursery(self) -> None:
        self.reject()
        if callable(self.open_nursery_callback):
            QTimer.singleShot(0, self.open_nursery_callback)


class ToastRegion(QFrame):
    """Accessible, replace-in-place feedback with an optional undo action."""

    shown = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("toastRegion", True)
        set_semantic_role(self, SemanticRole.TOAST, tone=FeedbackTone.NEUTRAL)
        self.setProperty("liveRegion", "polite")
        self.setAccessibleName("Garden update")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self)
        self.accessibility_announcer = AccessibilityAnnouncer(self)
        self._generation = 0
        self._scheduled_generation = 0
        self._callback: Callable[[], None] | None = None
        self._dismiss_callback: Callable[[], None] | None = None
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._clear_scheduled_message)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        self.icon = QLabel("✓")
        self.icon.setProperty("toastIcon", True)
        self.icon.setFixedSize(20, 20)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setAccessibleName("Success")
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.action = QPushButton("")
        _set_button_variant(self.action, BUTTON_VARIANT_SECONDARY)
        _set_compact_row_action(self.action)
        self.action.clicked.connect(self._run_action)
        self.dismiss = QPushButton("Dismiss")
        self.dismiss.setAccessibleName("Dismiss Garden update")
        _set_button_variant(self.dismiss, BUTTON_VARIANT_SECONDARY)
        _set_compact_row_action(self.dismiss)
        self.dismiss.clicked.connect(self._run_dismiss)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.action)
        layout.addWidget(self.dismiss)
        self.dismiss.hide()
        # A compact 32 px action plus 12 px vertical margins fits a 44 px toast.
        # Wrapped or actionable errors may grow, but routine notices stay on
        # the desktop-density baseline and never resize their parent layout.
        self.setMinimumHeight(44)
        self.setMaximumHeight(84)
        self.hide()

    def show_message(
        self,
        message: str,
        *,
        action_text: str = "",
        callback: Callable[[], None] | None = None,
        duration_ms: int | None = None,
        error: bool = False,
        dismissible: bool | None = None,
        dismiss_text: str = "",
        dismiss_callback: Callable[[], None] | None = None,
    ) -> None:
        self._clear_timer.stop()
        self._generation += 1
        generation = self._generation
        text = _learner_text(message)
        self._callback = callback
        self._dismiss_callback = dismiss_callback
        self.message.setText(text)
        self.setAccessibleDescription(text)
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text and callback is not None))
        if dismissible is None:
            dismissible = bool(error and duration_ms is not None and duration_ms <= 0)
        self.dismiss.setText(str(dismiss_text or "Dismiss"))
        self.dismiss.setAccessibleName(
            str(dismiss_text or "Dismiss Garden update")
        )
        self.dismiss.setVisible(bool(dismissible))
        self.setProperty("error", bool(error))
        self.icon.setText("!" if error else "✓")
        self.icon.setAccessibleName("Error" if error else "Success")
        self.icon.setProperty("error", bool(error))
        self.setProperty("liveRegion", "assertive" if error else "polite")
        set_semantic_role(
            self,
            SemanticRole.TOAST,
            tone=FeedbackTone.ERROR if error else FeedbackTone.SUCCESS,
        )
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        icon_style = self.icon.style()
        if icon_style is not None:
            icon_style.unpolish(self.icon)
            icon_style.polish(self.icon)
        self.show()
        self.raise_()
        self.accessibility_announcer.announce(
            text,
            priority=(
                AnnouncementPriority.ASSERTIVE
                if error
                else AnnouncementPriority.POLITE
            ),
        )
        self.shown.emit()
        if duration_ms is None:
            duration_ms = 6000 if callback is not None else 3000
        if duration_ms > 0:
            self._scheduled_generation = generation
            self._clear_timer.start(duration_ms)

    def _run_action(self) -> None:
        callback = self._callback
        self.clear()
        if callback is not None:
            callback()

    def _run_dismiss(self) -> None:
        callback = self._dismiss_callback
        self.clear()
        if callback is not None:
            callback()

    def _clear_generation(self, generation: int) -> None:
        if generation == self._generation:
            self.clear()

    def _clear_scheduled_message(self) -> None:
        self._clear_generation(self._scheduled_generation)

    def clear(self) -> None:
        self._clear_timer.stop()
        self._generation += 1
        self._callback = None
        self._dismiss_callback = None
        self.message.setText("")
        self.setAccessibleDescription("")
        self.dismiss.hide()
        self.hide()


GardenToast = ToastRegion


class _TooltipFocusFilter(QObject):
    def eventFilter(self, watched: Any, event: Any) -> bool:
        if event.type() == QEvent.Type.FocusIn and watched.toolTip():
            QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()), watched.toolTip(), watched)
        elif event.type() == QEvent.Type.FocusOut:
            QToolTip.hideText()
        return False


def apply_explanatory_tooltip(widget: QWidget, text: str) -> None:
    widget.setToolTip(text)
    widget.setAccessibleDescription(text)
    focus_filter = _TooltipFocusFilter(widget)
    widget.installEventFilter(focus_filter)
    widget._anki_garden_tooltip_filter = focus_filter  # type: ignore[attr-defined]


def _learner_text(value: Any) -> str:
    """Render legacy separator-based messages as readable stacked statements."""
    separator = chr(0xB7)
    return "\n".join(
        segment.strip()
        for line in str(value or "").splitlines()
        for segment in line.split(separator)
        if segment.strip()
    )


def _plant_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'plant' if count == 1 else 'plants'}"


def _card_answer_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'Anki card answer' if count == 1 else 'Anki card answers'}"


def _day_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'day' if count == 1 else 'days'}"


def _minute_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'minute' if count == 1 else 'minutes'}"


def _garden_coin_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'Garden Coin' if count == 1 else 'Garden Coins'}"


def _purchase_fact(
    presentation: PurchasePresentation,
    key: str,
    fallback: str = "",
) -> str:
    """Read one shared purchase fact without duplicating product copy."""

    for fact in presentation.facts:
        if fact.key == key:
            return fact.value
    return fallback


def _transaction_date(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return f"{parsed.strftime('%b')} {parsed.day}"
    except (TypeError, ValueError):
        return "—"


def _calendar_date(value: Any) -> str:
    try:
        parsed = date.fromisoformat(str(value or "")[:10])
        return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
    except (TypeError, ValueError):
        return str(value or "—")


def _currency_transaction_type(transaction: Any) -> str:
    """Return the learner-facing direction stored by the currency ledger."""

    transaction_type = str(
        getattr(transaction, "transaction_type", "") or ""
    ).lower()
    if transaction_type == "credit":
        return "Earned"
    if transaction_type == "debit":
        return "Spent"
    try:
        return "Earned" if int(getattr(transaction, "delta", 0) or 0) >= 0 else "Spent"
    except (TypeError, ValueError):
        return "Activity"


def _currency_transaction_source(
    transaction: Any,
    achievement_names: dict[str, str] | None = None,
) -> str:
    """Translate a typed ledger source without exposing persistence IDs."""

    source = str(getattr(transaction, "source", "") or "legacy")
    source_id = str(getattr(transaction, "source_id", "") or "")
    event_key = str(getattr(transaction, "event_key", "") or "")
    if source in {"achievement", "achievement_backfill"}:
        achievement_name = (achievement_names or {}).get(source_id, "")
        return (
            f"Achievement · {achievement_name}"
            if achievement_name else
            "Achievement"
        )
    if source == "garden_reward" and event_key.startswith("stage:"):
        return "Plant stage"
    labels = {
        "daily_activity": "Daily activity",
        "weekly_streak": "Seven-day streak",
        "all_due": "All due cards",
        "garden_find": "Garden Find",
        "garden_find_environment": "Garden Find",
        "environment_daily_gift": "Scenery gift",
        "garden_reward": "Garden reward",
        "purchase": "Nursery purchase",
        "legacy": "Imported history",
    }
    return labels.get(source, format_status_label(source))


def _affordability_status(price: int, balance: int) -> tuple[bool, str]:
    shortfall = max(0, int(price) - max(0, int(balance)))
    if shortfall == 0:
        return True, "Affordable now."
    unit = "Garden Coin" if shortfall == 1 else "Garden Coins"
    return False, f"Need {shortfall:,} more {unit}."


def _compact_affordability_status(
    price: int,
    balance: int,
    *,
    ready_text: str,
) -> str:
    """Keep visible price rows concise while full descriptions retain the unit."""

    shortfall = max(0, int(price) - max(0, int(balance)))
    return ready_text if shortfall == 0 else f"{shortfall:,} more needed"


def _padded_preview_bounds(
    value: Any,
    *,
    padding: float = 0.10,
) -> tuple[float, float, float, float]:
    """Expand trusted normalized art bounds without restoring empty canvas."""

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return (0.0, 0.0, 1.0, 1.0)
    try:
        x, y, width, height = (float(part) for part in value)
    except (TypeError, ValueError):
        return (0.0, 0.0, 1.0, 1.0)
    if (
        not all(isfinite(part) for part in (x, y, width, height))
        or width <= 0
        or height <= 0
    ):
        return (0.0, 0.0, 1.0, 1.0)
    safe_padding = max(0.0, min(0.5, float(padding)))
    left = max(0.0, x - width * safe_padding)
    top = max(0.0, y - height * safe_padding)
    right = min(1.0, x + width * (1.0 + safe_padding))
    bottom = min(1.0, y + height * (1.0 + safe_padding))
    if right <= left or bottom <= top:
        return (0.0, 0.0, 1.0, 1.0)
    return (left, top, right - left, bottom - top)


def _rare_stage_unlocked(engine: Any, species: str) -> bool:
    """Return whether this species' Rare artwork has been discovered."""

    target_species = str(species or "").strip().lower()
    if not target_species:
        return False
    state = getattr(engine, "state", None)
    if state is None:
        state = getattr(getattr(engine, "storage", None), "state", None)
    plants = (
        state.get("plants", ())
        if isinstance(state, dict)
        else getattr(state, "plants", ())
    ) or ()
    for plant in plants:
        if isinstance(plant, dict):
            plant_species = plant.get("species", "")
            stage = plant.get("growth_stage") or plant.get("stage", "")
            growth_points = plant.get("growth_points", 0)
        else:
            plant_species = getattr(plant, "species", "")
            stage = getattr(plant, "growth_stage", "")
            growth_points = getattr(plant, "growth_points", 0)
        if str(plant_species or "").strip().lower() != target_species:
            continue
        try:
            reached_threshold = int(growth_points or 0) >= GROWTH_THRESHOLDS[-1]
        except (TypeError, ValueError):
            reached_threshold = False
        if str(stage or "").strip().lower() == "rare" or reached_threshold:
            return True
    return False


_LOGGED_MISSING_ARTWORK: set[tuple[str, str, str]] = set()


def _record_missing_artwork(
    *,
    category: str,
    item_key: str,
    source_path: Any = None,
) -> None:
    """Record an unresolved source internally without exposing its path in UI."""

    normalized_category = str(category or "artwork").strip().lower()
    normalized_key = str(item_key or "unknown").strip()
    normalized_path = str(source_path or "<unresolved>")
    fingerprint = (normalized_category, normalized_key, normalized_path)
    if fingerprint in _LOGGED_MISSING_ARTWORK:
        return
    _LOGGED_MISSING_ARTWORK.add(fingerprint)
    DISPLAY_TELEMETRY.track_fallback(
        route="artwork",
        field=f"{normalized_category}:{normalized_key}",
        fallback=normalized_path,
    )
    logger.warning(
        "Anki Garden: artwork unavailable category=%s item=%s source=%s",
        normalized_category,
        normalized_key,
        normalized_path,
    )


def _missing_artwork_pixmap(
    category: str,
    width: int,
    height: int,
) -> QPixmap:
    """Paint one intentional, category-aware fallback at the caller's ratio."""

    safe_width = max(1, int(width))
    safe_height = max(1, int(height))
    category_key = str(category or "artwork").strip().lower().replace("_", "-")
    preview = QPixmap(safe_width, safe_height)
    preview.fill(QColor("#14251f"))
    painter = QPainter(preview)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # A quiet woven-garden texture makes the fallback read as designed rather
    # than as an empty or failed rectangular asset.
    painter.setPen(QPen(QColor(71, 105, 88, 58), 1))
    spacing = max(9, min(safe_width, safe_height) // 5)
    for offset in range(-safe_height, safe_width + safe_height, spacing):
        painter.drawLine(offset, 0, offset - safe_height, safe_height)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(32, 67, 54, 220))
    painter.drawRoundedRect(QRectF(4, 4, safe_width - 8, safe_height - 8), 9, 9)

    icon_bottom = max(14, safe_height - 4)
    icon_size = max(12, min(30, min(safe_width - 12, icon_bottom - 8)))
    center_x = safe_width / 2
    center_y = safe_height / 2
    icon_rect = QRectF(
        center_x - icon_size / 2,
        center_y - icon_size / 2,
        icon_size,
        icon_size,
    )
    painter.setPen(QPen(QColor("#d9c978"), max(1.5, icon_size / 12)))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if category_key in {"plant", "species", "botanical"}:
        painter.drawLine(
            QPointF(center_x, icon_rect.bottom()),
            QPointF(center_x, icon_rect.top() + icon_size * 0.24),
        )
        painter.drawEllipse(
            QRectF(
                icon_rect.left() + icon_size * 0.08,
                icon_rect.top() + icon_size * 0.34,
                icon_size * 0.42,
                icon_size * 0.28,
            )
        )
        painter.drawEllipse(
            QRectF(
                center_x,
                icon_rect.top() + icon_size * 0.15,
                icon_size * 0.42,
                icon_size * 0.28,
            )
        )
    elif category_key in {"weather"}:
        painter.drawEllipse(
            QRectF(
                icon_rect.left() + icon_size * 0.08,
                icon_rect.top() + icon_size * 0.35,
                icon_size * 0.68,
                icon_size * 0.38,
            )
        )
        painter.drawEllipse(
            QRectF(
                icon_rect.left() + icon_size * 0.36,
                icon_rect.top() + icon_size * 0.20,
                icon_size * 0.50,
                icon_size * 0.48,
            )
        )
        painter.drawLine(
            QPointF(icon_rect.left() + icon_size * 0.35, icon_rect.bottom()),
            QPointF(icon_rect.left() + icon_size * 0.25, icon_rect.bottom() + 3),
        )
        painter.drawLine(
            QPointF(icon_rect.left() + icon_size * 0.70, icon_rect.bottom()),
            QPointF(icon_rect.left() + icon_size * 0.60, icon_rect.bottom() + 3),
        )
    elif category_key in {"scenery", "bed", "environment"}:
        painter.drawRoundedRect(icon_rect, 4, 4)
        painter.drawLine(
            QPointF(icon_rect.left(), icon_rect.bottom() - icon_size * 0.25),
            QPointF(icon_rect.left() + icon_size * 0.35, icon_rect.top() + icon_size * 0.48),
        )
        painter.drawLine(
            QPointF(icon_rect.left() + icon_size * 0.35, icon_rect.top() + icon_size * 0.48),
            QPointF(icon_rect.right(), icon_rect.bottom() - icon_size * 0.18),
        )
    elif category_key in {"fertilizer"}:
        bottle = QRectF(
            icon_rect.left() + icon_size * 0.24,
            icon_rect.top() + icon_size * 0.25,
            icon_size * 0.52,
            icon_size * 0.66,
        )
        painter.drawRoundedRect(bottle, 3, 3)
        painter.drawLine(
            QPointF(center_x - icon_size * 0.12, icon_rect.top() + icon_size * 0.18),
            QPointF(center_x + icon_size * 0.12, icon_rect.top() + icon_size * 0.18),
        )
        painter.drawLine(
            QPointF(center_x, bottle.top() + icon_size * 0.12),
            QPointF(center_x, bottle.bottom() - icon_size * 0.12),
        )
    else:
        # Growth Charge and other consumables share a compact energy mark.
        bolt = QPainterPath()
        bolt.moveTo(center_x + icon_size * 0.08, icon_rect.top())
        bolt.lineTo(center_x - icon_size * 0.28, center_y + icon_size * 0.05)
        bolt.lineTo(center_x - icon_size * 0.02, center_y + icon_size * 0.05)
        bolt.lineTo(center_x - icon_size * 0.10, icon_rect.bottom())
        bolt.lineTo(center_x + icon_size * 0.30, center_y - icon_size * 0.04)
        bolt.lineTo(center_x + icon_size * 0.04, center_y - icon_size * 0.04)
        bolt.closeSubpath()
        painter.drawPath(bolt)

    painter.end()
    return preview


def _botanical_placeholder_pixmap(
    width: int,
    height: int,
    *,
    stage: str = "",
    undiscovered: bool = False,
) -> QPixmap:
    """Draw a quiet code-native illustration for unresolved artwork.

    A missing bitmap must not collapse the card or turn its visual region into
    a word placeholder. This deliberately uses no packaged asset, so it still
    works when the missing file is the package resource being recovered from.
    """

    safe_width = max(1, int(width))
    safe_height = max(1, int(height))
    preview = QPixmap(safe_width, safe_height)
    preview.fill(QColor(0, 0, 0, 0))
    painter = QPainter(preview)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)

    center_x = safe_width // 2
    ground_y = max(2, round(safe_height * 0.78))
    halo_size = max(10, round(min(safe_width, safe_height) * 0.82))
    painter.setBrush(QColor(31, 57, 48, 225))
    painter.drawEllipse(
        center_x - halo_size // 2,
        max(0, (safe_height - halo_size) // 2),
        halo_size,
        halo_size,
    )
    painter.setBrush(QColor("#795D3F"))
    painter.drawEllipse(
        max(1, round(safe_width * 0.20)),
        ground_y - max(2, round(safe_height * 0.06)),
        max(4, round(safe_width * 0.60)),
        max(3, round(safe_height * 0.13)),
    )

    stage_key = str(stage or "").strip().lower()
    if stage_key == "seed":
        seed_width = max(5, round(safe_width * 0.18))
        seed_height = max(4, round(safe_height * 0.11))
        painter.setBrush(QColor("#D7B764"))
        painter.drawEllipse(
            center_x - seed_width // 2,
            ground_y - seed_height,
            seed_width,
            seed_height,
        )
    else:
        stem_height_ratio = {
            "sprout": 0.28,
            "young": 0.40,
            "mature": 0.50,
            "flowering": 0.54,
            "rare": 0.58,
        }.get(stage_key, 0.44)
        stem_height = max(8, round(safe_height * stem_height_ratio))
        stem_width = max(2, round(safe_width * 0.045))
        stem_top = ground_y - stem_height
        painter.setBrush(QColor("#78986F"))
        painter.drawRect(
            center_x - stem_width // 2,
            stem_top,
            stem_width,
            stem_height,
        )
        leaf_width = max(7, round(safe_width * 0.26))
        leaf_height = max(5, round(safe_height * 0.13))
        painter.setBrush(QColor("#5F8B69"))
        painter.drawEllipse(
            center_x - leaf_width,
            stem_top + max(2, stem_height // 3),
            leaf_width,
            leaf_height,
        )
        painter.drawEllipse(
            center_x,
            stem_top + max(4, stem_height // 2),
            leaf_width,
            leaf_height,
        )
        if stage_key in {"mature", "flowering", "rare", ""}:
            painter.setBrush(QColor("#76A277"))
            painter.drawEllipse(
                center_x - leaf_width // 2,
                stem_top + max(1, stem_height // 6),
                leaf_width,
                leaf_height,
            )
        if stage_key in {"flowering", "rare"}:
            bloom = max(6, round(min(safe_width, safe_height) * 0.17))
            painter.setBrush(QColor("#D7B764") if stage_key == "rare" else QColor("#D797A5"))
            painter.drawEllipse(
                center_x - bloom // 2,
                max(1, stem_top - bloom // 3),
                bloom,
                bloom,
            )

    if undiscovered:
        veil = max(16, round(min(safe_width, safe_height) * 0.64))
        painter.setBrush(QColor(9, 27, 22, 242))
        painter.drawEllipse(
            center_x - veil // 2,
            max(0, (safe_height - veil) // 2),
            veil,
            veil,
        )
        painter.setPen(QColor("#D7B764"))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(13, round(min(safe_width, safe_height) * 0.38)))
        painter.setFont(font)
        painter.drawText(preview.rect(), Qt.AlignmentFlag.AlignCenter, "?")
    painter.end()
    return preview


def _asset_preview_label(
    engine: Any,
    species: str,
    stage: str,
    *,
    size: int = 84,
    property_name: str = "stagePreview",
    rare_unlocked: bool | None = None,
) -> QLabel:
    """Create a metadata-cropped plant preview without altering source art."""

    label = ArtworkThumbnail()
    label.setFixedSize(size, size)
    label.setProperty(property_name, True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    species_name = format_status_label(species)
    stage_name = format_status_label(stage)
    label.setAccessibleName(f"{species_name}, {stage_name} stage preview")
    stage_key = str(stage or "").strip().lower()
    if stage_key == "rare":
        discovered = (
            _rare_stage_unlocked(engine, species)
            if rare_unlocked is None else
            bool(rare_unlocked)
        )
        if not discovered:
            label.setText("")
            label.setPixmap(
                _botanical_placeholder_pixmap(
                    size,
                    size,
                    stage="rare",
                    undiscovered=True,
                )
            )
            label.setAccessibleName(f"{species_name}, Rare stage undiscovered")
            label.setAccessibleDescription(
                "Rare-stage artwork remains hidden until this species reaches Rare."
            )
            label.setToolTip("Reach Rare with this species to reveal its artwork.")
            return label
    asset = None
    try:
        resolver = getattr(engine, "resolve_plant_asset", None)
        asset = resolver(species, stage) if callable(resolver) else None
    except Exception:
        asset = None
    path = getattr(asset, "path", None) if asset is not None else None
    placement = getattr(asset, "placement", None) if asset is not None else None
    if not path:
        try:
            path = engine.resolve_plant_image(species, stage)
        except Exception:
            path = None
    pixmap = _normalized_plant_thumbnail(
        path,
        placement,
        stage=str(stage),
        size=size,
    )
    if pixmap.isNull():
        _record_missing_artwork(
            category="plant",
            item_key=f"{species}:{stage}",
            source_path=path,
        )
        set_semantic_role(label, SemanticRole.MISSING_ART)
        label.setText("")
        label.setPixmap(
            _missing_artwork_pixmap("plant", size, size)
        )
        label.setAccessibleDescription(
            f"Artwork unavailable for {species_name} at the {stage_name} stage; "
            "a botanical fallback illustration is shown."
        )
        return label
    label.setPixmap(pixmap)
    return label


def _placement_value(placement: Any, key: str, default: Any) -> Any:
    if isinstance(placement, dict):
        return placement.get(key, default)
    return getattr(placement, key, default) if placement is not None else default


def _normalized_plant_thumbnail(
    path: Any,
    placement: Any,
    *,
    stage: str,
    size: int,
) -> QPixmap:
    """Render one alpha-bounded, optically centered plant thumbnail."""

    source = QPixmap(str(path)) if path else QPixmap()
    if source.isNull():
        return QPixmap()
    bounds = _placement_value(
        placement,
        "thumbnail_bounds",
        _placement_value(
            placement,
            "art_bounds",
            _placement_value(placement, "visible_bounds", None),
        ),
    )
    try:
        safe_padding = float(
            _placement_value(placement, "thumbnail_safe_padding", 0.10)
        )
    except (TypeError, ValueError):
        safe_padding = 0.10
    left, top, width, height = _padded_preview_bounds(
        bounds,
        padding=safe_padding,
    )
    source_width, source_height = source.width(), source.height()
    crop_x = max(0, min(source_width - 1, round(left * source_width)))
    crop_y = max(0, min(source_height - 1, round(top * source_height)))
    crop_width = max(1, min(source_width - crop_x, round(width * source_width)))
    crop_height = max(1, min(source_height - crop_y, round(height * source_height)))
    cropped = source.copy(crop_x, crop_y, crop_width, crop_height)
    if cropped.isNull():
        cropped = source
        left, top, width, height = (0.0, 0.0, 1.0, 1.0)

    stage_fill = {
        "seed": 0.92,
        "sprout": 0.90,
        "young": 0.86,
        "mature": 0.84,
        "flowering": 0.88,
        "rare": 0.88,
    }.get(str(stage).lower(), 0.86)
    try:
        content_scale = float(
            _placement_value(placement, "thumbnail_scale", 1.0)
        )
    except (TypeError, ValueError):
        content_scale = 1.0
    target = max(16, min(size, round(size * stage_fill * max(0.5, min(1.5, content_scale)))))
    scaled = cropped.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    optical = _placement_value(
        placement,
        "thumbnail_optical_center",
        _placement_value(placement, "focal_point", (0.5, 0.5)),
    )
    try:
        optical_x, optical_y = float(optical[0]), float(optical[1])
    except (TypeError, ValueError, IndexError):
        optical_x, optical_y = (0.5, 0.5)
    relative_x = max(0.0, min(1.0, (optical_x - left) / max(width, 0.0001)))
    relative_y = max(0.0, min(1.0, (optical_y - top) / max(height, 0.0001)))
    draw_x = round(size / 2 - relative_x * scaled.width())
    draw_y = round(size / 2 - relative_y * scaled.height())
    draw_x = max(0, min(size - scaled.width(), draw_x))
    draw_y = max(0, min(size - scaled.height(), draw_y))
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(draw_x, draw_y, scaled)
    painter.end()
    return result


def _populate_asset_preview(
    target: QLabel,
    engine: Any,
    species: str,
    stage: str,
    *,
    size: int,
    fallback_text: str,
    rare_unlocked: bool | None = None,
) -> None:
    """Copy one resolved stage preview into an existing layout-owned label."""

    preview = _asset_preview_label(
        engine,
        species,
        stage,
        size=size,
        rare_unlocked=rare_unlocked,
    )
    target.setAccessibleName(preview.accessibleName())
    target.setAccessibleDescription(preview.accessibleDescription())
    target.setToolTip(preview.toolTip())
    if preview.property("gardenRole") == SemanticRole.MISSING_ART.value:
        set_semantic_role(target, SemanticRole.MISSING_ART)
    else:
        target.setProperty("gardenRole", "")
    pixmap = preview.pixmap()
    if pixmap is None or pixmap.isNull():
        _record_missing_artwork(
            category="plant",
            item_key=f"{species}:{stage}",
            source_path=None,
        )
        target.setText("")
        target.setPixmap(
            _missing_artwork_pixmap("plant", size, size)
        )
        target.setAccessibleDescription(
            f"Artwork unavailable for {fallback_text}; a botanical fallback illustration is shown."
        )
        return
    target.setText("")
    target.setPixmap(pixmap)


def _item_preview_label(
    engine: Any,
    item_key: str,
    accessible_name: str,
    *,
    size: int = 76,
    placeholder_kind: PurchaseKind | None = None,
) -> QLabel:
    """Resolve bundled UI artwork while preserving a readable fallback."""

    label = ArtworkThumbnail()
    label.setFixedSize(size, size)
    label.setProperty("itemPreview", True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setAccessibleName(accessible_name)
    asset = None
    try:
        resolver = getattr(engine, "resolve_item_asset", None)
        asset = resolver(str(item_key)) if callable(resolver) else None
    except Exception:
        logger.exception("Anki Garden: item preview resolution failed for %s", item_key)
    path = getattr(asset, "path", None) if asset is not None else None
    pixmap = QPixmap(str(path)) if path else QPixmap()
    if pixmap.isNull():
        category = (
            placeholder_kind.value
            if placeholder_kind is not None
            else "artwork"
        )
        _record_missing_artwork(
            category=category,
            item_key=str(item_key),
            source_path=path,
        )
        set_semantic_role(label, SemanticRole.MISSING_ART)
        label.setText("")
        label.setPixmap(
            _purchase_placeholder_pixmap(
                placeholder_kind,
                size,
                size,
            )
            if placeholder_kind is not None
            else _missing_artwork_pixmap("artwork", size, size)
        )
        label.setToolTip(accessible_name)
        label.setAccessibleDescription(
            f"Artwork unavailable for {accessible_name}; a "
            f"{placeholder_kind.value.replace('_', ' ') if placeholder_kind is not None else 'botanical'} "
            "category placeholder is shown."
        )
    else:
        label.setPixmap(pixmap.scaled(
            size - 8,
            size - 8,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
    return label


def _cover_pixmap(source: QPixmap, width: int, height: int) -> QPixmap:
    """Return a center-cropped preview without distorting its source art."""

    if source.isNull() or width <= 0 or height <= 0:
        return QPixmap()
    scaled = source.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    left = max(0, (scaled.width() - width) // 2)
    top = max(0, (scaled.height() - height) // 2)
    return scaled.copy(left, top, min(width, scaled.width()), min(height, scaled.height()))


def _preview_source_pixmap(path: Any) -> QPixmap:
    """Load raster or SVG preview art through the host's supported renderer."""

    if not path:
        return QPixmap()
    source_path = Path(str(path))
    if source_path.suffix.lower() != ".svg":
        return QPixmap(str(source_path))
    if QSvgRenderer is None:
        return QPixmap()
    renderer = QSvgRenderer(str(source_path))
    if not renderer.isValid():
        return QPixmap()
    default_size = renderer.defaultSize()
    width = max(1, int(default_size.width()))
    height = max(1, int(default_size.height()))
    preview = QPixmap(width, height)
    preview.fill(Qt.GlobalColor.transparent)
    painter = QPainter(preview)
    try:
        renderer.render(painter, QRectF(0, 0, width, height))
    finally:
        painter.end()
    return preview


def _environment_placeholder_pixmap(
    width: int,
    height: int,
    *,
    category: str = "environment",
    item_key: str = "unknown",
    source_path: Any = None,
) -> QPixmap:
    """Provide the shared intentional fallback at the requested aspect ratio."""

    if item_key == "unknown" and not source_path and category == "environment":
        # Neutral pre-selection canvas; this is not a missing source state.
        preview = QPixmap(max(1, int(width)), max(1, int(height)))
        preview.fill(QColor("#14251f"))
        painter = QPainter(preview)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(71, 105, 88, 55), 1))
        for offset in range(-int(height), int(width) + int(height), 16):
            painter.drawLine(offset, 0, offset - int(height), int(height))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#355b48"))
        painter.drawRoundedRect(
            QRectF(6, max(6, int(height) * 0.58), max(1, int(width) - 12), max(1, int(height) * 0.34)),
            8,
            8,
        )
        painter.end()
        return preview
    if item_key != "unknown" or source_path:
        _record_missing_artwork(
            category=category,
            item_key=item_key,
            source_path=source_path,
        )
    return _missing_artwork_pixmap(category, width, height)


def _purchase_placeholder_pixmap(
    kind: PurchaseKind,
    width: int,
    height: int,
) -> QPixmap:
    """Draw a category-specific unavailable preview without fake product art."""

    return _missing_artwork_pixmap(kind.value, width, height)


def _garden_bed_purchase_preview(
    engine: Any,
    item_id: str,
    width: int,
    height: int,
) -> QPixmap:
    """Render the current garden with the quoted sequential bed highlighted."""

    scenery = SCENERY_CATALOG.get(str(engine.state.selected_background))
    background = (
        _environment_preview_pixmap(engine, scenery, width, height)
        if scenery is not None
        else _environment_placeholder_pixmap(width, height)
    )
    preview = background.copy()
    try:
        target_index = max(0, int(str(item_id).rsplit("_", 1)[-1]) - 1)
    except (TypeError, ValueError):
        target_index = max(0, int(engine.state.unlocked_slots))
    columns = 3
    rows = 2
    gap = max(5, width // 40)
    grid_width = min(width - 24, max(180, width * 3 // 4))
    grid_height = min(height - 22, max(72, height * 2 // 3))
    bed_width = max(34, (grid_width - gap * (columns - 1)) // columns)
    bed_height = max(24, (grid_height - gap * (rows - 1)) // rows)
    origin_x = (width - (bed_width * columns + gap * (columns - 1))) // 2
    origin_y = (height - (bed_height * rows + gap * (rows - 1))) // 2
    painter = QPainter(preview)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for index in range(columns * rows):
        column = index % columns
        row = index // columns
        rect = QRectF(
            origin_x + column * (bed_width + gap),
            origin_y + row * (bed_height + gap),
            bed_width,
            bed_height,
        )
        owned = index < int(engine.state.unlocked_slots)
        target = index == target_index
        painter.setBrush(QColor("#315a3f" if owned else "#1d3329"))
        painter.setPen(
            QPen(
                QColor("#f0cf6a" if target else "#6f8d78"),
                4 if target else 1,
            )
        )
        painter.drawRoundedRect(rect, 8, 8)
        if target:
            painter.setPen(QColor("#fff2b1"))
            painter.drawText(
                rect,
                int(Qt.AlignmentFlag.AlignCenter),
                f"Bed {index + 1}",
            )
    painter.end()
    return preview


def _weather_placeholder_overlay(width: int, height: int) -> QPixmap:
    """Return a recognizable graphical overlay when packaged Weather art fails."""

    overlay = QPixmap(max(1, width), max(1, height))
    overlay.fill(Qt.GlobalColor.transparent)
    painter = QPainter(overlay)
    painter.setOpacity(0.72)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#dbe8e5"))
    cloud_width = max(28, width // 3)
    cloud_height = max(12, height // 8)
    cloud_left = max(8, width // 2 - cloud_width // 2)
    cloud_top = max(8, height // 5)
    painter.drawEllipse(cloud_left, cloud_top, cloud_width, cloud_height)
    painter.drawEllipse(
        cloud_left + cloud_width // 5,
        max(4, cloud_top - cloud_height // 2),
        cloud_width // 2,
        cloud_height,
    )
    painter.setPen(QColor("#9bc4ce"))
    for offset in (1, 2, 3):
        x = cloud_left + cloud_width * offset // 4
        painter.drawLine(
            x,
            cloud_top + cloud_height + 5,
            x - max(3, width // 60),
            cloud_top + cloud_height + max(11, height // 10),
        )
    painter.end()
    return overlay


def _environment_preview_pixmap(
    engine: Any,
    item: CatalogItem,
    width: int,
    height: int,
    *,
    scenery_id: str = DEFAULT_SCENERY_ID,
) -> QPixmap:
    """Render Scenery directly and Weather over a real garden background."""

    try:
        if item.kind == "scenery":
            base_asset = engine.resolve_scenery_preview_asset(item.item_id)
        else:
            base_asset = engine.resolve_scenery_preview_asset(scenery_id)
        base_path = getattr(base_asset, "path", None)
        result = _cover_pixmap(
            _preview_source_pixmap(base_path),
            width,
            height,
        )
        if result.isNull():
            return _environment_placeholder_pixmap(
                width,
                height,
                category=item.kind,
                item_key=item.item_id,
                source_path=base_path,
            )
        if item.kind == "weather":
            weather_asset = engine.resolve_weather_preview_asset(item.item_id)
            weather_path = getattr(weather_asset, "path", None)
            overlay = _cover_pixmap(
                _preview_source_pixmap(weather_path),
                width,
                height,
            )
            if overlay.isNull():
                return _environment_placeholder_pixmap(
                    width,
                    height,
                    category="weather",
                    item_key=item.item_id,
                    source_path=weather_path,
                )
            painter = QPainter(result)
            painter.drawPixmap(0, 0, overlay)
            painter.end()
        return result
    except Exception:
        logger.exception(
            "Anki Garden: environment preview composition failed for %s",
            item.item_id,
        )
        return _environment_placeholder_pixmap(
            width,
            height,
            category=item.kind,
            item_key=item.item_id,
            source_path=None,
        )


class ArtworkThumbnail(QLabel):
    """Metadata-cropped artwork preview; source sprite geometry remains untouched."""

    pass


def _nurtured_badge_pixmap(asset: Any, *, size: int = 15) -> QPixmap:
    """Crop the shared painterly watering can into a legible text-height icon."""

    payload = asset.to_payload() if hasattr(asset, "to_payload") else asset
    if isinstance(payload, dict):
        path = payload.get("path")
        metadata = payload.get("metadata", {})
    else:
        path = payload
        metadata = {}
    source = QPixmap(str(path)) if path else QPixmap()
    if source.isNull():
        return QPixmap()
    placement = metadata.get("placement", {}) if isinstance(metadata, dict) else {}
    bounds = placement.get("alpha_bounds") if isinstance(placement, dict) else None
    left, top, width, height = _padded_preview_bounds(bounds, padding=0.04)
    crop = source.copy(
        max(0, round(left * source.width())),
        max(0, round(top * source.height())),
        max(1, round(width * source.width())),
        max(1, round(height * source.height())),
    )
    return crop.scaled(
        max(1, int(size)),
        max(1, int(size)),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class NurturedPlantBadge(QFrame):
    """Shared icon-and-text designation used by every plant summary."""

    def __init__(self, asset: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("nurturedBadgeFrame", True)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Nurtured")
        self.setAccessibleDescription("Nurtured plant.")
        self.setToolTip("")
        row = QHBoxLayout(self)
        row.setContentsMargins(7, 3, 8, 3)
        row.setSpacing(4)
        self.icon = QLabel("")
        self.icon.setFixedSize(15, 15)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setAccessibleName("Watering can")
        self.text_label = QLabel("Nurtured")
        self.text_label.setProperty("nurturedBadgeText", True)
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignBaseline)
        row.addWidget(self.text_label, 0, Qt.AlignmentFlag.AlignBaseline)
        self.setStyleSheet(
            "QFrame[nurturedBadgeFrame='true'] {"
            "color:#352514; background:#e1b85e; border:0; border-radius:8px;"
            "}"
            "QFrame[nurturedBadgeFrame='true'] QLabel {"
            "color:#352514; background:transparent; border:0; padding:0;"
            "font-size:12px; font-weight:800;"
            "}"
        )
        self.set_asset(asset)

    def set_asset(self, asset: Any) -> None:
        icon = _nurtured_badge_pixmap(asset)
        self.icon.setVisible(not icon.isNull())
        if not icon.isNull():
            self.icon.setPixmap(icon)


class FertilizerStatusBlock(QFrame):
    """Shared compact, structured fertilizer status with optional disclosure."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        allow_description: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setProperty("fertilizerStatusBlock", True)
        self.setAccessibleName("Fertilizer status")
        column = QVBoxLayout(self)
        vertical_padding = 8 if allow_description else 4
        column.setContentsMargins(10, vertical_padding, 10, vertical_padding)
        column.setSpacing(2 if allow_description else 1)
        self.name_label = QLabel("")
        self.name_label.setProperty("fertilizerStatusName", True)
        self.effect_label = QLabel("")
        self.effect_label.setProperty("fertilizerStatusEffect", True)
        self.duration_label = QLabel("")
        self.duration_label.setProperty("fertilizerStatusDuration", True)
        apply_tabular_numerals(self.duration_label)
        for label in (
            self.name_label,
            self.effect_label,
            self.duration_label,
        ):
            label.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
        column.addWidget(self.name_label)
        column.addWidget(self.effect_label)
        column.addWidget(self.duration_label)
        self.description_toggle = QPushButton("What fertilizer does")
        self.description_toggle.setCheckable(True)
        self.description_toggle.setProperty("fertilizerDisclosure", True)
        self.description_toggle.setAccessibleName("Show full Fertilizer description")
        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setProperty("fertilizerDescription", True)
        self.description.hide()
        self.description_toggle.toggled.connect(self._toggle_description)
        if allow_description:
            column.addWidget(self.description_toggle)
            column.addWidget(self.description)
        else:
            self.description_toggle.hide()
        self.setStyleSheet(
            "QFrame[fertilizerStatusBlock='true'] {"
            "background:#102a22; border:1px solid #3f6753; border-radius:9px;"
            "}"
            "QLabel[fertilizerStatusName='true'] {color:#f4f7f5; font-size:13px; font-weight:800;}"
            "QLabel[fertilizerStatusEffect='true'] {color:#b8d8c2; font-size:13px;}"
            "QLabel[fertilizerStatusDuration='true'] {color:#e8cf87; font-size:13px; font-weight:700;}"
            "QLabel[fertilizerStatusDuration='true'][fertilizerUrgent='true'] {"
            "color:#f3d17d; background:#3b3420; border:1px solid #7d6f3d; "
            "border-radius:7px; padding:3px 7px;}"
            "QLabel[fertilizerDescription='true'] {color:#a9bdb0; font-size:12px; padding-top:3px;}"
            "QPushButton[fertilizerDisclosure='true'] {"
            "min-height:28px; text-align:left; padding:0; color:#b8d8c2;"
            "background:transparent; border:0; font-size:12px;"
            "}"
            "QPushButton[fertilizerDisclosure='true']:focus {border:1px solid #82e2ac;}"
        )
        self.hide()

    def _toggle_description(self, expanded: bool) -> None:
        self.description.setVisible(bool(expanded))
        self.description_toggle.setText(
            "Hide fertilizer description" if expanded else "What fertilizer does"
        )
        self.description_toggle.setAccessibleName(
            "Hide full Fertilizer description"
            if expanded else
            "Show full Fertilizer description"
        )

    def set_status(self, status: FertilizerStatus | dict[str, Any]) -> None:
        if isinstance(status, dict):
            try:
                status = FertilizerStatus(**status)
            except (TypeError, ValueError):
                self.hide()
                return
        self.name_label.setText(status.name)
        self.effect_label.setText(status.effect)
        self.duration_label.setText(status.duration)
        self.duration_label.setProperty(
            "fertilizerUrgent",
            bool(status.active and 0 < int(status.seconds_remaining) < 60),
        )
        duration_style = self.duration_label.style()
        if duration_style is not None:
            duration_style.unpolish(self.duration_label)
            duration_style.polish(self.duration_label)
        widest = max(
            self.duration_label.fontMetrics().horizontalAdvance("59 seconds left"),
            self.duration_label.fontMetrics().horizontalAdvance("99h 59m remaining"),
        )
        self.duration_label.setMinimumWidth(widest)
        self.description.setText(status.description)
        self.setToolTip(status.description)
        self.setAccessibleDescription(status.accessible_text)
        self.setProperty("fertilizerPhase", status.phase)
        self.description_toggle.setChecked(False)
        self.description.hide()
        self.setVisible(status.phase != "inactive")


def _button_stylesheet() -> str:
    return button_stylesheet()


def _fit_dialog_to_screen(
    dialog: QDialog,
    default_width: int,
    default_height: int,
    *,
    width_ratio: float = 0.82,
    height_ratio: float = 0.82,
) -> tuple[int, int]:
    """Keep secondary windows useful on compact displays without oversizing large ones."""
    parent = dialog.parent()
    screen = (
        parent.screen()
        if parent is not None and hasattr(parent, "screen")
        else None
    ) or dialog.screen()
    if screen is None:
        return default_width, default_height
    available = screen.availableGeometry()
    return (
        min(default_width, max(dialog.minimumWidth(), int(available.width() * width_ratio))),
        min(default_height, max(dialog.minimumHeight(), int(available.height() * height_ratio))),
    )


class LabeledProgress(QWidget):
    """A numeric label paired with a thin, semantically complete progress bar."""

    def __init__(self, accessible_name: str = "Progress", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        labels = QHBoxLayout()
        labels.setSpacing(8)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.value_label = QLabel()
        self.value_label.setProperty("progressValue", True)
        labels.addWidget(self.label, 1)
        labels.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignRight)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setAccessibleName(accessible_name)
        set_semantic_role(self.bar, SemanticRole.PROGRESS)
        apply_tabular_numerals(self.value_label)
        layout.addLayout(labels)
        layout.addWidget(self.bar)

    def set_progress(self, label: str, current: int, maximum: int, *, value_text: str | None = None) -> None:
        current = max(0, int(current))
        maximum = max(1, int(maximum))
        self.label.setText(label)
        self.value_label.setText(value_text or f"{current:,} / {maximum:,}")
        self.bar.setRange(0, maximum)
        self.bar.setValue(min(current, maximum))
        description = f"{label}: {self.value_label.text()}"
        self.bar.setAccessibleName(label)
        self.bar.setAccessibleDescription(description)
        self.setAccessibleName(description)


class ProgressBar(LabeledProgress):
    """Shared stage-relative Growth progress presentation."""


GardenProgressBar = ProgressBar


class GardenTabs(QTabWidget):
    """Shared accessible tab container with unclipped, scrollable labels."""

    def __init__(self, accessible_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setAccessibleName(accessible_name)
        set_semantic_role(self.tabBar(), SemanticRole.TABS)
        self.tabBar().setUsesScrollButtons(True)
        self.tabBar().setExpanding(True)
        self.tabBar().setElideMode(Qt.TextElideMode.ElideNone)


class SectionCard(QFrame):
    """Raised surface for one meaningfully grouped section."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("sectionCard", True)


GardenCard = SectionCard


class GardenItemRow(QFrame):
    """One compact catalogue or inventory row without nested card chrome."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenItemRow", True)
        self.setProperty("gardenComponent", "item-row")


class StatSummary(QFrame):
    """Compact equal-width summary values used by Today and metric views."""

    def __init__(self, rows: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("statSummary", True)
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(16)
        for column, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setProperty("summaryLabel", True)
            value = QLabel(value_text)
            value.setProperty("summaryValue", True)
            apply_text_role(value, TextRole.NUMERIC_DISPLAY)
            value.setAlignment(Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(label, 0, column)
            grid.addWidget(value, 1, column)
            grid.setColumnStretch(column, 1)


GardenStat = StatSummary


class GardenBadge(QLabel):
    """Shared semantic badge; color is supplied by role and tone."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        tone: FeedbackTone = FeedbackTone.NEUTRAL,
    ) -> None:
        super().__init__(str(text), parent)
        self.setProperty("gardenComponent", "badge")
        set_semantic_role(self, SemanticRole.BADGE, tone=tone)
        self.setTextFormat(Qt.TextFormat.PlainText)


class GardenStatusBanner(QFrame):
    """Single-source feedback block for one state or transaction."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "status-banner")
        set_semantic_role(self, SemanticRole.BANNER)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message, 1)
        self.hide()

    def set_status(
        self,
        message: str,
        *,
        tone: FeedbackTone = FeedbackTone.NEUTRAL,
    ) -> None:
        copy = str(message).strip()
        self.message.setText(copy)
        self.setAccessibleName("Garden status")
        self.setAccessibleDescription(copy)
        set_semantic_role(self, SemanticRole.BANNER, tone=tone)
        self.setVisible(bool(copy))


class EmptyState(QFrame):
    """A heading, at most one supporting line, and one primary action."""

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        action: QPushButton | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("emptyState", True)
        set_semantic_role(self, SemanticRole.EMPTY_STATE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setProperty("emptyTitle", True)
        body = QLabel(str(description).strip())
        body.setProperty("emptyBody", True)
        body.setWordWrap(True)
        layout.addWidget(heading)
        if body.text():
            layout.addWidget(body)
        if action is not None:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignLeft)
            action.setProperty("emptyStateAction", True)
            _pin_empty_state_action_style(
                action,
                str(action.property("variant") or BUTTON_VARIANT_PRIMARY),
            )


GardenEmptyState = EmptyState


class GardenTooltip:
    """Shared truncation tooltip helper."""

    @staticmethod
    def attach(widget: QWidget, full_text: str) -> None:
        copy = str(full_text)
        widget.setToolTip(copy)
        if not widget.accessibleName():
            widget.setAccessibleName(copy)


class GardenOutcomePreview(QFrame):
    """Structured outcome rows with one section-level preview label."""

    def __init__(
        self,
        rows: list[tuple[str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "outcome-preview")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(12, 10, 12, 10)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(6)
        self.value_labels: dict[str, QLabel] = {}
        self.set_rows(rows or [])

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        self.value_labels = {}
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, (label_text, value_text) in enumerate(rows):
            label = QLabel(str(label_text))
            value = QLabel(str(value_text))
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            apply_tabular_numerals(value)
            self.grid.addWidget(label, index, 0)
            self.grid.addWidget(value, index, 1)
            self.value_labels[str(label_text).strip().lower()] = value


class GardenPlantSummary(SectionCard):
    """Single structured plant summary used before contextual actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "plant-summary")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self.name_label = QLabel("")
        self.name_label.setProperty("rowTitle", True)
        self.stage_label = QLabel("")
        self.stage_label.setProperty("summaryLabel", True)
        self.progress = GardenProgressBar("Plant Growth")
        layout.addWidget(self.name_label)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress)

    def set_summary(
        self,
        name: str,
        stage: str,
        current: int,
        maximum: int,
    ) -> None:
        self.name_label.setText(str(name))
        self.stage_label.setText(str(stage))
        self.progress.set_progress("Growth", current, maximum)


class GardenSceneOverlay(QFrame):
    """Shared transparent scene-overlay marker for geometry ownership."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "scene-overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


class GardenPopover(GardenSceneOverlay):
    """Shared bounded scene popover surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "popover")


class DisclosureRow(QWidget):
    """Keyboard-native disclosure with visible state and no independent scrolling."""

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        *,
        expanded: bool = False,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.button = QPushButton()
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setProperty("disclosureRow", True)
        self.button.setProperty("compactDisclosure", bool(compact))
        if compact:
            self.button.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Fixed,
            )
        set_semantic_role(self.button, SemanticRole.DISCLOSURE)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panel = QWidget()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(12, 4, 4, 8)
        panel_layout.setSpacing(4)
        for label_text, value_text in rows:
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setWordWrap(True)
            value = QLabel(value_text)
            value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            apply_tabular_numerals(value)
            row.addWidget(label, 1)
            row.addWidget(value, 0)
            panel_layout.addLayout(row)
        layout.addWidget(self.button)
        layout.addWidget(self.panel)

        def sync(checked: bool) -> None:
            self.button.setText(f"{'⌄' if checked else '›'}  {title}")
            self.button.setAccessibleName(title)
            self.button.setAccessibleDescription(
                f"{title}. {'Expanded' if checked else 'Collapsed'}."
            )
            self.panel.setVisible(checked)

        self.button.toggled.connect(sync)
        sync(expanded)


class DataTable(QFrame):
    """Lightweight table surface using row dividers rather than nested cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dataTable", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(0)


class ActionFooter(GardenDialogFooter):
    """Static action row for dialogs that genuinely have a primary action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenComponent", "action-footer")


class ToggleSwitch(QCheckBox):
    """Accessible switch with one left-side visual state indicator."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setProperty("toggleSwitch", True)
        self.setAccessibleName(label)
        self.setIconSize(QSize(38, 24))
        self.toggled.connect(self._sync_accessible_state)
        self._sync_accessible_state(self.isChecked())

    def _sync_accessible_state(self, checked: bool) -> None:
        self.setText(self.accessibleName())
        self.setIcon(_toggle_state_icon(bool(checked)))
        self.setAccessibleDescription("On" if checked else "Off")

    def setChecked(self, checked: bool) -> None:
        """Keep visible state text correct even while callers block signals."""
        super().setChecked(bool(checked))
        self._sync_accessible_state(bool(checked))


class ProgressRow(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("progressRow", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.title.setProperty("rowTitle", True)
        heading.addWidget(self.title, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status.setProperty("rowStatus", True)
        apply_tabular_numerals(self.status)
        heading.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(heading)
        self.criteria = QLabel()
        self.criteria.setWordWrap(True)
        self.criteria.setProperty("rowCriteria", True)
        layout.addWidget(self.criteria)
        self.progress = LabeledProgress()
        layout.addWidget(self.progress)
        self.completion = self.status

    def set_item(
        self, title: str, criteria: str, current: int, target: int, *, completed: bool = False,
        value_text: str | None = None, completion_text: str = "Completed",
        explanation: str | None = None,
    ) -> None:
        self.title.setText(title)
        self.criteria.setText(criteria)
        self.progress.set_progress(title, current, target, value_text=value_text)
        self.progress.label.hide()
        self.progress.value_label.hide()
        self.progress.setVisible(not completed)
        self.status.setText(completion_text if completed else value_text or f"{current:,} of {target:,}")
        self.status.setVisible(True)
        self.setProperty("completed", completed)
        state_text = "Completed and reward earned" if completed else "In progress"
        details = explanation or criteria
        self.setAccessibleName(f"{title}. {state_text}.")
        apply_explanatory_tooltip(self, details)
        apply_explanatory_tooltip(self.progress, f"{details} {current:,} of {target:,} complete.")
        self.setAccessibleDescription(
            f"{details} {current:,} of {target:,} complete."
        )

    def set_information(
        self,
        title: str,
        criteria: str,
        value_text: str,
        *,
        explanation: str | None = None,
    ) -> None:
        """Render a measured result without implying a requirement or reward."""
        self.title.setText(title)
        self.criteria.setText(criteria)
        self.progress.hide()
        self.status.setText(value_text)
        self.status.setVisible(True)
        self.setProperty("completed", False)
        self.setAccessibleName(f"{title}. Today’s recorded Garden result.")
        details = explanation or criteria
        apply_explanatory_tooltip(self, f"{details} {value_text}")
        self.setAccessibleDescription(f"{details} {value_text}")

    def set_achievement_state(self, state: str) -> None:
        tooltips = {
            "locked": "Locked. Make progress toward this milestone to begin.",
            "in_progress": "In progress. Keep studying to unlock this achievement.",
            "unlocked": "Unlocked achievement.",
        }
        self.setProperty("achievementState", state)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.setAccessibleDescription(tooltips[state])
        apply_explanatory_tooltip(self, tooltips[state])


class ProgressCardGrid(QWidget):
    """Responsive catalogue grid for achievements and collected plants."""

    def __init__(
        self,
        accessible_name: str,
        parent: QWidget | None = None,
        *,
        wide_columns: int = 2,
        minimum_item_width: int = 180,
        minimum_card_height: int = 136,
        span_singleton_rows: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self._entries: list[tuple[QWidget, bool]] = []
        self._wide_columns = max(1, int(wide_columns))
        self._minimum_item_width = max(120, int(minimum_item_width))
        self._minimum_card_height = max(96, int(minimum_card_height))
        self._span_singleton_rows = bool(span_singleton_rows)
        self._columns = self._wide_columns
        self._layout_row_count = 0
        self.container = QWidget()
        self.container.setObjectName("progressCardGridContainer")
        self.container.setStyleSheet(
            "QWidget#progressCardGridContainer { background:#071a15; }"
        )
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(6, 6, 22, 6)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setObjectName("progressCardGridViewport")
        self.scroll.viewport().setStyleSheet(
            "QWidget#progressCardGridViewport { background:#071a15; }"
        )
        self.scroll.setAccessibleName(f"{accessible_name} scroll area")
        self.scroll.setWidget(self.container)
        _set_scroll_surface(self.scroll, self.container, "#071a15")
        outer.addWidget(self.scroll)

    def clear(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        self._reset_row_metrics()
        for widget, _full_width in self._entries:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        self._entries.clear()
        self.container.setMinimumHeight(0)

    def add_card(self, card: QWidget) -> None:
        card.setMinimumHeight(
            max(self._minimum_card_height, int(card.minimumHeight()))
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._entries.append((card, False))
        self._reflow()

    def add_full_width(self, widget: QWidget) -> None:
        self._entries.append((widget, True))
        self._reflow()

    def add_empty(self, title: str, body: str = "") -> None:
        self.add_full_width(EmptyState(title, body))

    def _reset_row_metrics(self) -> None:
        for row_index in range(max(self._layout_row_count, len(self._entries) + 2)):
            self.grid.setRowMinimumHeight(row_index, 0)
            self.grid.setRowStretch(row_index, 0)

    def _reflow(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        self._reset_row_metrics()
        row = 0
        column = 0
        row_minimums: dict[int, int] = {}
        # New Qt widgets are hidden until a layout adopts them, so isHidden()
        # cannot distinguish fresh cards from an intentionally suppressed row.
        # Callers mark only the latter explicitly. Keeping the filtered
        # sequence also lets category-bound singleton cards span the row
        # without changing the default grid behavior.
        visible_entries = [
            (widget, full_width)
            for widget, full_width in self._entries
            if not bool(widget.property("excludedFromProgressGrid"))
        ]
        for entry_index, (widget, full_width) in enumerate(visible_entries):
            if full_width:
                if column:
                    row += 1
                    column = 0
                self.grid.addWidget(widget, row, 0, 1, self._columns)
                row_minimums[row] = max(
                    row_minimums.get(row, 0),
                    int(widget.minimumHeight()),
                    int(widget.minimumSizeHint().height()),
                )
                row += 1
                continue
            next_is_boundary = (
                entry_index + 1 >= len(visible_entries)
                or visible_entries[entry_index + 1][1]
            )
            spans_singleton_row = (
                self._span_singleton_rows
                and self._columns == 2
                and column == 0
                and next_is_boundary
            )
            widget.setProperty("spansSingletonRow", spans_singleton_row)
            if spans_singleton_row:
                self.grid.addWidget(widget, row, 0, 1, self._columns)
                row_minimums[row] = max(
                    row_minimums.get(row, 0),
                    self._minimum_card_height,
                    int(widget.minimumHeight()),
                )
                row += 1
                column = 0
                continue
            self.grid.addWidget(widget, row, column)
            row_minimums[row] = max(
                row_minimums.get(row, 0),
                self._minimum_card_height,
                int(widget.minimumHeight()),
            )
            column += 1
            if column >= self._columns:
                row += 1
                column = 0
        for index in range(self._wide_columns):
            self.grid.setColumnStretch(index, 1 if index < self._columns else 0)
        for row_index, minimum in row_minimums.items():
            self.grid.setRowMinimumHeight(row_index, max(0, int(minimum)))
        trailing_row = row + (1 if column else 0)
        self.grid.setRowStretch(trailing_row, 1)
        self._layout_row_count = trailing_row + 1
        self.grid.invalidate()
        self.grid.activate()
        required_height = max(
            0,
            int(self.grid.minimumSize().height()),
            int(self.grid.sizeHint().height()),
        )
        self.container.setMinimumHeight(required_height)
        self.container.setProperty("contentRowCount", len(row_minimums))
        self.container.setProperty("contentMinimumHeight", required_height)
        self.container.updateGeometry()
        self.updateGeometry()

    def finish(self) -> None:
        self._reflow()
        # Callers update the no-results visibility immediately after finish().
        # Re-measure once that state is applied so 0, 1, and full-result views
        # all retain their natural content height.
        QTimer.singleShot(0, self._reflow)

    def resizeEvent(self, event: Any) -> None:
        width = event.size().width()
        columns = responsive_column_count(
            width,
            minimum_item_width=self._minimum_item_width,
            maximum_columns=self._wide_columns,
            spacing=self.grid.horizontalSpacing(),
        )
        if columns != self._columns:
            self._columns = columns
            self._reflow()
        super().resizeEvent(event)


class ResponsiveTileGrid(QWidget):
    """Content-sized two-to-one column grid for catalog tiles."""

    def __init__(
        self,
        *,
        breakpoint: int = 560,
        minimum_tile_width: int | None = None,
        maximum_columns: int = 2,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.breakpoint = int(breakpoint)
        self.maximum_columns = max(1, int(maximum_columns))
        self.minimum_tile_width = (
            max(44, int(minimum_tile_width))
            if minimum_tile_width is not None else
            max(180, (self.breakpoint - 10 - 24) // 2)
        )
        self._columns = self.maximum_columns
        self._items: list[QWidget] = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)

    def add_tile(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._reflow()

    def _reflow(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for index, widget in enumerate(self._items):
            self.grid.addWidget(widget, index // self._columns, index % self._columns)
        for column in range(self._columns):
            self.grid.setColumnStretch(column, 1)
        self.updateGeometry()

    def resizeEvent(self, event: Any) -> None:
        columns = responsive_column_count(
            event.size().width(),
            minimum_item_width=self.minimum_tile_width,
            maximum_columns=self.maximum_columns,
            spacing=self.grid.horizontalSpacing(),
        )
        if columns != self._columns:
            self._columns = columns
            self._reflow()
        super().resizeEvent(event)


class ResponsiveActionCard(QFrame):
    """A summary/action card that stacks only when both regions cannot fit."""

    def __init__(
        self,
        summary: QWidget,
        action: QWidget,
        *,
        semantic_id: str,
        summary_floor: int,
        action_floor: int,
        spacing: int = 10,
        margins: tuple[int, int, int, int] = (0, 0, 0, 0),
        wide_maximum_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("decisionGroup", True)
        self.summary = summary
        self.action = action
        self._compact_layout: bool | None = None
        self._wide_maximum_height = wide_maximum_height
        self.flow_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.flow_layout.setContentsMargins(*margins)
        self.flow_layout.setSpacing(spacing)
        self.flow_layout.addWidget(summary)
        self.flow_layout.addWidget(action)
        self.flow_layout.setStretch(0, 1)
        if wide_maximum_height is not None:
            self.setMaximumHeight(max(0, int(wide_maximum_height)))
        self.responsive = AdaptiveSplit(
            semantic_id,
            AdaptiveRegion.measured(
                f"{semantic_id}.summary",
                summary,
                floor=summary_floor,
            ),
            AdaptiveRegion.measured(
                f"{semantic_id}.action",
                action,
                floor=action_floor,
            ),
            spacing=spacing,
            apply_mode=self._apply_responsive_mode,
            telemetry_target=self,
        )

    def _apply_responsive_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self.flow_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact else QBoxLayout.Direction.LeftToRight
        )
        self.flow_layout.setStretch(0, 0 if compact else 1)
        self.action.setSizePolicy(
            QSizePolicy.Policy.Expanding
            if compact else QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.setMaximumHeight(
            16777215
            if compact or self._wide_maximum_height is None
            else max(0, int(self._wide_maximum_height))
        )
        self.flow_layout.invalidate()
        self.flow_layout.activate()
        self.updateGeometry()

    def resizeEvent(self, event: Any) -> None:
        margins = self.flow_layout.contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        self.responsive.evaluate(available)
        super().resizeEvent(event)


class CollectionFilterControls(QWidget):
    """Content-measured Collection filters with one accessible control set."""

    def __init__(
        self,
        *,
        count: QLabel,
        query: str,
        status: str,
        category: str,
        sort_order: str,
        set_query: Callable[[str], None],
        set_status: Callable[[str], None],
        set_category: Callable[[str], None],
        set_sort_order: Callable[[str], None],
        clear_filters: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("collectionFilters", True)
        self.setAccessibleName("Collection filters")
        self.count = count
        self.count.setProperty("collectionCount", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(14, 11, 14, 11)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)

        self.search = QLineEdit(query)
        self.search.setPlaceholderText("Search Collection")
        self.search.setAccessibleName("Search collectibles")
        self.search.setAccessibleDescription(
            "Search collectible names. Press Tab to continue through the filters."
        )
        self.search.setClearButtonEnabled(True)
        self.search.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.search.editingFinished.connect(
            lambda field=self.search: set_query(field.text())
        )

        self.status, self.status_combo = self._combo_field(
            "Status",
            "Collection status",
            (
                ("Any status", "all"),
                ("Owned", "collected"),
                ("Locked", "not_collected"),
            ),
            status,
        )
        self.category, self.category_combo = self._combo_field(
            "Category",
            "Collection category",
            (
                ("Any category", "all"),
                *((label, key) for key, label in collection_categories()),
            ),
            category,
        )
        self.sort_order, self.sort_combo = self._combo_field(
            "Sort",
            "Collection sort order",
            (
                ("Catalog order", "catalog"),
                ("Name", "name"),
            ),
            "catalog" if sort_order == "registry" else sort_order,
        )
        self.status_combo.currentIndexChanged.connect(
            lambda _index: set_status(str(self.status_combo.currentData() or "all"))
        )
        self.category_combo.currentIndexChanged.connect(
            lambda _index: set_category(str(self.category_combo.currentData() or "all"))
        )
        self.sort_combo.currentIndexChanged.connect(
            lambda _index: set_sort_order(
                str(self.sort_combo.currentData() or "catalog")
            )
        )

        self.clear = QPushButton("Clear filters")
        _set_button_variant(self.clear, BUTTON_VARIANT_TERTIARY)
        self.clear.setAccessibleDescription(
            "Clear the search and restore every Collection filter to its default."
        )
        self.clear.clicked.connect(clear_filters)
        filters_active = bool(
            query
            or status != "all"
            or category != "all"
            or sort_order not in {"catalog", "registry"}
        )
        set_control_enabled(
            self.clear,
            filters_active,
            disabled_reason="The complete Collection is already shown in catalog order.",
            enabled_description=self.clear.accessibleDescription(),
        )

        self.setStyleSheet(f"""
            QComboBox {{
                min-height:{BUTTON_MIN_HEIGHT}px;
                padding:0 30px 0 10px;
                color:{GARDEN_THEME['text_primary']};
                background:#10241f;
                border:1px solid {GARDEN_THEME['subtle_border']};
                border-radius:8px;
            }}
            QComboBox:hover {{ border-color:{GARDEN_THEME['strong_border']}; }}
            QComboBox:focus {{ border:2px solid {GARDEN_THEME['focus_ring']}; padding:0 29px 0 9px; }}
            QComboBox::drop-down {{ border:0; width:24px; }}
            QComboBox QAbstractItemView {{
                color:{GARDEN_THEME['text_primary']};
                background:#10241f;
                selection-background-color:{GARDEN_THEME['action_accent']};
                border:1px solid {GARDEN_THEME['subtle_border']};
            }}
        """)

        self.responsive = AdaptiveRow(
            "progress.collection-filter-controls",
            (
                AdaptiveRegion(
                    "collection-filter-grid",
                    self._wide_content_width,
                    self,
                ),
            ),
            apply_mode=self._apply_responsive_mode,
            telemetry_target=self,
        )
        # Start from the smallest safe arrangement; resizeEvent promotes it
        # only after both wide rows fit their measured content.
        self._compact_layout: bool | None = None
        self._apply_responsive_mode(COMPACT_MODE)
        self.setFocusProxy(self.search)

    @staticmethod
    def _combo_field(
        label_text: str,
        accessible_name: str,
        options: tuple[tuple[str, str], ...],
        selected: str,
    ) -> tuple[QWidget, QComboBox]:
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(label_text)
        label.setProperty("dialogSubtitle", True)
        combo = QComboBox()
        combo.setAccessibleName(accessible_name)
        combo.setAccessibleDescription(f"Choose the {label_text.lower()} filter.")
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        for option_label, option_value in options:
            combo.addItem(option_label, option_value)
        selected_index = combo.findData(selected)
        combo.setCurrentIndex(max(0, selected_index))
        label.setBuddy(combo)
        layout.addWidget(label)
        layout.addWidget(combo)
        return field, combo

    @staticmethod
    def _minimum_width(widget: QWidget, floor: int) -> int:
        return max(
            int(floor),
            int(widget.minimumSizeHint().width()),
        )

    def _wide_content_width(self) -> int:
        spacing = self.grid.horizontalSpacing()
        return (
            self._minimum_width(self.count, 180)
            + self._minimum_width(self.search, 220)
            + self._minimum_width(self.status, 130)
            + self._minimum_width(self.category, 150)
            + self._minimum_width(self.sort_order, 140)
            + self._minimum_width(self.clear, 100)
            + (spacing * 5)
        )

    def _apply_responsive_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        controls = (
            self.count,
            self.search,
            self.status,
            self.category,
            self.sort_order,
            self.clear,
        )
        for control in controls:
            self.grid.removeWidget(control)
        for column in range(6):
            self.grid.setColumnStretch(column, 0)
        if compact:
            # At the canonical progress width the toolbar uses two concise
            # rows, never a tall right-hand filter stack. The first row keeps
            # identity and search together; the second holds all filters.
            self.grid.addWidget(self.count, 0, 0, 1, 2)
            self.grid.addWidget(self.search, 0, 2, 1, 4)
            self.grid.addWidget(self.status, 1, 0, 1, 2)
            self.grid.addWidget(self.category, 1, 2, 1, 2)
            self.grid.addWidget(self.sort_order, 1, 4)
            self.grid.addWidget(
                self.clear,
                1,
                5,
                alignment=Qt.AlignmentFlag.AlignBottom,
            )
            self.grid.setColumnStretch(2, 1)
            QWidget.setTabOrder(self.search, self.status_combo)
            QWidget.setTabOrder(self.status_combo, self.category_combo)
            QWidget.setTabOrder(self.category_combo, self.sort_combo)
            QWidget.setTabOrder(self.sort_combo, self.clear)
        else:
            # Desktop keeps every Collection filter in one predictable toolbar.
            self.grid.addWidget(self.count, 0, 0)
            self.grid.addWidget(self.search, 0, 1)
            self.grid.addWidget(self.status, 0, 2)
            self.grid.addWidget(self.category, 0, 3)
            self.grid.addWidget(self.sort_order, 0, 4)
            self.grid.addWidget(
                self.clear,
                0,
                5,
                alignment=Qt.AlignmentFlag.AlignBottom,
            )
            self.grid.setColumnStretch(1, 1)
            QWidget.setTabOrder(self.search, self.status_combo)
            QWidget.setTabOrder(self.status_combo, self.category_combo)
            QWidget.setTabOrder(self.category_combo, self.sort_combo)
            QWidget.setTabOrder(self.sort_combo, self.clear)
        self.setProperty("layoutMode", mode)
        self.grid.invalidate()
        self.grid.activate()
        self.updateGeometry()

    def resizeEvent(self, event: Any) -> None:
        margins = self.grid.contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        self.responsive.evaluate(available)
        super().resizeEvent(event)


class ResponsiveSplit(QWidget):
    """Two-column 60/40 surface that stacks without adding another scrollbar."""

    def __init__(
        self,
        left: QWidget,
        right: QWidget,
        *,
        breakpoint: int = 620,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.left = left
        self.right = right
        self.breakpoint = int(breakpoint)
        region_floor = max(220, (self.breakpoint - 16 - 24) // 2)
        self._stacked: bool | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self._reflow(False)
        self.responsive = AdaptiveSplit(
            "shared.two-panel-split",
            AdaptiveRegion.measured(
                "primary-panel",
                self.left,
                floor=region_floor,
            ),
            AdaptiveRegion.measured(
                "secondary-panel",
                self.right,
                floor=region_floor,
            ),
            spacing=16,
            apply_mode=lambda mode: self._reflow(mode == COMPACT_MODE),
            telemetry_target=self,
        )

    def _reflow(self, stacked: bool) -> None:
        if stacked == self._stacked:
            return
        self._stacked = stacked
        self.grid.removeWidget(self.left)
        self.grid.removeWidget(self.right)
        if stacked:
            self.grid.addWidget(self.left, 0, 0)
            self.grid.addWidget(self.right, 1, 0)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 0)
        else:
            self.grid.addWidget(self.left, 0, 0)
            self.grid.addWidget(self.right, 0, 1)
            self.grid.setColumnStretch(0, 3)
            self.grid.setColumnStretch(1, 2)

    def resizeEvent(self, event: Any) -> None:
        self.responsive.evaluate(event.size().width())
        super().resizeEvent(event)


class GardenSettingsDialog(GardenDialog):
    def __init__(self, parent: QWidget, engine: Any, config: Any) -> None:
        super().__init__(parent, UI_TEXT["settings_window_title"])
        self.engine = engine
        self.config = config
        self._save_status_generation = 0
        self.apply_size_policy(
            DialogSizeClass.SETTINGS,
        )
        self.setStyleSheet(_garden_dialog_stylesheet() + f"""
            QLabel[saveStatus='true'] {{ padding:5px 8px; border-radius:8px; }}
            QFrame[diagnosticsCard='true'] {{ background:{GARDEN_THEME['raised_surface']}; border:0; border-left:4px solid {GARDEN_THEME['success']}; border-radius:12px; }}
            QFrame[diagnosticsCard='true'][diagnosticState='warning'] {{ background:#332D1D; border-left:4px solid {GARDEN_THEME['warning']}; }}
            QLineEdit[validationState='error'] {{ border:2px solid {GARDEN_THEME['error']}; padding:6px 9px; }}
            QLabel[fieldError='true'] {{ color:#ffb4ab; font-size:12px; font-weight:600; }}
            QLabel[diagnosticsIcon='true'] {{ color:{GARDEN_THEME['action_text']}; background:{GARDEN_THEME['success']}; border-radius:20px; font-size:20px; font-weight:800; }}
            QLabel[diagnosticsTitle='true'] {{ color:{GARDEN_THEME['text_primary']}; font-size:16px; font-weight:700; }}
            QLabel[diagnosticsMeta='true'] {{ color:{GARDEN_THEME['text_muted']}; font-size:13px; }}
        """)

        self.tabs = GardenTabs("Anki Garden settings sections")
        self.set_body_widget(self.tabs)

        snapshot_provider = getattr(parent, "_settings_scene_snapshot", None)
        self.behavior = GardenStudioWidget(
            self.config,
            asset_resolver=self.engine.resolve_preview_assets,
            garden_snapshot_provider=snapshot_provider if callable(snapshot_provider) else None,
        )
        self.behavior.manageEnvironmentRequested.connect(
            self._open_environment_management
        )
        self.behavior.fine_tune_toggle.toggled.connect(
            lambda _expanded: self._sync_settings_tab(self.tabs.currentIndex())
        )
        self.behavior.advanced_toggle.toggled.connect(
            lambda _expanded: self._sync_settings_tab(self.tabs.currentIndex())
        )
        self._persisted_payload = deepcopy(self.behavior.build_theme_payload())
        self._persisted_name = str(
            getattr(self.engine.state, "garden_name", "My Garden") or "My Garden"
        )
        self.save_settings = QPushButton("Save")
        self.save_settings.setAccessibleName("Save Anki Garden settings")
        _set_button_variant(self.save_settings, BUTTON_VARIANT_PRIMARY)
        self.save_settings.clicked.connect(self._save_visual_settings)
        set_control_enabled(
            self.save_settings,
            False,
            disabled_reason="No unsaved settings changes.",
        )
        self.restore_defaults = QPushButton("Reset display settings")
        self.restore_defaults.setAccessibleName("Reset display settings")
        _set_button_variant(self.restore_defaults, BUTTON_VARIANT_SECONDARY)
        self.restore_defaults.clicked.connect(self._restore_defaults)
        self.behavior.advanced_actions_layout.addWidget(self.restore_defaults)
        self.cancel_settings = QPushButton("Cancel")
        _set_button_variant(self.cancel_settings, BUTTON_VARIANT_SECONDARY)
        self.cancel_settings.clicked.connect(self.reject)
        self.save_status = QLabel("")
        self.save_status.setTextFormat(Qt.TextFormat.PlainText)
        self.save_status.setProperty("saveStatus", True)
        self.save_status.setAccessibleName("Settings save status")
        self.save_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.save_status)
        self.save_status.setWordWrap(True)
        self.save_status.hide()
        self.behavior.persistentChanged.connect(self._update_dirty_state)
        behavior = QWidget()
        # Let the Display page shrink to the live scroll viewport after its
        # vertical scrollbar appears. Without the ignored horizontal hint,
        # the expanded Advanced panel can retain its pre-scrollbar width and
        # overflow the viewport by exactly the scrollbar extent.
        behavior.setMinimumWidth(0)
        behavior.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.setContentsMargins(0, 0, 0, 0)
        behavior_layout.setSpacing(10)
        garden_name_panel = QFrame()
        garden_name_panel.setProperty("settingsSection", True)
        # Keep the label, input, and help line at their natural heights when
        # the compact two-row footer is visible at the dialog minimum.
        garden_name_panel.setMinimumHeight(96)
        garden_name_layout = QHBoxLayout(garden_name_panel)
        garden_name_copy = QVBoxLayout()
        garden_name_label = QLabel("Garden name")
        garden_name_label.setStyleSheet("font-weight:700;")
        self.garden_name_edit = QLineEdit()
        # Permit an invalid draft to remain visible so the user can understand
        # and fix it; truncating at 40 silently hides the validation state.
        self.garden_name_edit.setMaxLength(MAX_GARDEN_NAME_LENGTH + 80)
        self.garden_name_edit.setFixedHeight(INPUT_VISUAL_HEIGHT)
        self.garden_name_edit.setAccessibleName("Garden name")
        self.garden_name_edit.setAccessibleDescription(
            f"The name shown on your Garden and Anki home preview. Up to {MAX_GARDEN_NAME_LENGTH} characters."
        )
        self.set_initial_focus(
            self.garden_name_edit,
            InitialFocusPolicy.FIRST_EDITABLE,
        )
        garden_name_header = QHBoxLayout()
        garden_name_header.setContentsMargins(0, 0, 0, 0)
        garden_name_header.setSpacing(8)
        garden_name_header.addWidget(garden_name_label)
        garden_name_header.addStretch(1)
        self.garden_name_counter = QLabel("")
        self.garden_name_counter.setProperty("dialogSubtitle", True)
        self.garden_name_counter.setAccessibleName("Garden name character count")
        garden_name_header.addWidget(self.garden_name_counter)
        garden_name_copy.addLayout(garden_name_header)
        garden_name_copy.addWidget(self.garden_name_edit)
        self.garden_name_error = QLabel("")
        self.garden_name_error.setProperty("fieldError", True)
        self.garden_name_error.setWordWrap(True)
        self.garden_name_error.setAccessibleName("Garden name error")
        self.garden_name_error.hide()
        garden_name_copy.addWidget(self.garden_name_error)
        self.garden_name_edit.textChanged.connect(self._update_dirty_state)
        self.garden_name_edit.textChanged.connect(self._preview_garden_name)
        self.garden_name_edit.returnPressed.connect(self._save_visual_settings)
        garden_name_layout.addLayout(garden_name_copy, 1)
        behavior_layout.addWidget(garden_name_panel)
        # GardenStudioWidget owns the controls-column scroll surface. The
        # parent Display page scrolls the combined name/studio stack only when
        # the native dialog reaches its minimum height, so the preview remains
        # reachable without changing the window size.
        behavior_layout.addWidget(self.behavior, 1)
        self.behavior_page = behavior
        self.behavior_scroll = QScrollArea()
        self.behavior_scroll.setObjectName("gardenSettingsDisplayScroll")
        self.behavior_scroll.setWidgetResizable(True)
        self.behavior_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.behavior_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.behavior_scroll.setAccessibleName("Display settings")
        self.behavior_scroll.setWidget(behavior)
        _set_scroll_surface(
            self.behavior_scroll,
            behavior,
            GARDEN_THEME["dialog_surface"],
        )
        self.behavior_scroll.verticalScrollBar().rangeChanged.connect(
            lambda _minimum, _maximum: QTimer.singleShot(
                0,
                self._sync_display_scroll_width,
            )
        )

        # Save feedback gets the full content width so long validation errors do
        # not compress or misalign the persistent action row.
        self.settings_footer_actions = QWidget()
        self.settings_footer_grid = QGridLayout(self.settings_footer_actions)
        self.settings_footer_grid.setContentsMargins(0, 0, 0, 0)
        self.settings_footer_grid.setHorizontalSpacing(8)
        self.settings_footer_grid.setVerticalSpacing(8)
        self.footer_layout.addWidget(self.save_status, 1)
        self.footer_layout.addWidget(self.settings_footer_actions, 0)
        self.footer.show()
        self._settings_footer_compact: bool | None = None
        self.settings_footer_responsive = AdaptiveRow(
            "settings.footer-actions",
            (
                AdaptiveRegion.measured(
                    "cancel-settings",
                    self.cancel_settings,
                    floor=96,
                ),
                AdaptiveRegion.measured(
                    "save-settings",
                    self.save_settings,
                    floor=112,
                ),
            ),
            spacing=8,
            apply_mode=self._set_settings_footer_mode,
            telemetry_target=self.settings_footer_actions,
        )
        self._apply_settings_footer_layout(
            max(
                0,
                self.width()
                - self._shell_layout.contentsMargins().left()
                - self._shell_layout.contentsMargins().right(),
            )
        )

        advanced = QScrollArea()
        self.troubleshooting_scroll = advanced
        advanced.setWidgetResizable(True)
        advanced.setFrameShape(QFrame.Shape.NoFrame)
        advanced.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        advanced.setAccessibleName("Troubleshooting")
        advanced_body = QWidget()
        a_layout = QVBoxLayout(advanced_body)
        a_layout.setContentsMargins(0, 8, 0, 0)
        a_layout.setSpacing(12)
        advanced.setWidget(advanced_body)
        _set_scroll_surface(
            advanced,
            advanced_body,
            GARDEN_THEME["dialog_surface"],
        )
        self.diagnostics_card = QFrame()
        self.diagnostics_card.setProperty("diagnosticsCard", True)
        self.diagnostics_card.setProperty("diagnosticState", "clean")
        diagnostics_layout = QHBoxLayout(self.diagnostics_card)
        diagnostics_layout.setContentsMargins(16, 14, 16, 14)
        diagnostics_layout.setSpacing(12)
        self.diagnostics_icon = QLabel("✓")
        self.diagnostics_icon.setProperty("diagnosticsIcon", True)
        self.diagnostics_icon.setFixedSize(40, 40)
        self.diagnostics_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.diagnostics_icon.setAccessibleName("Diagnostics passed")
        diagnostics_copy = QVBoxLayout()
        diagnostics_copy.setSpacing(3)
        self.troubleshooting_status = QLabel("No display issues found")
        self.troubleshooting_status.setProperty("diagnosticsTitle", True)
        self.troubleshooting_status.setWordWrap(True)
        self.troubleshooting_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.troubleshooting_status)
        self.troubleshooting_status.setAccessibleName("Diagnostics report status")
        self.diagnostics_summary = QLabel("")
        self.diagnostics_summary.setWordWrap(True)
        self.diagnostics_summary.setProperty("dialogSubtitle", True)
        self.diagnostics_checked = QLabel("Checked just now")
        self.diagnostics_checked.setProperty("diagnosticsMeta", True)
        self.diagnostics_version = QLabel(
            f"Anki Garden {_addon_human_version()} · Build {_addon_build_identifier()} · "
            f"{platform.system() or 'Unknown OS'} · {QGuiApplication.platformName() or 'Qt renderer'}"
        )
        self.diagnostics_version.setProperty("diagnosticsMeta", True)
        self.diagnostics_version.hide()
        self.diagnostics_build = QLabel(
            f"Packaged build {_addon_build_identifier()}"
        )
        self.diagnostics_build.setProperty("diagnosticsMeta", True)
        self.diagnostics_environment = QLabel(
            f"{platform.system() or 'Unknown OS'} · {QGuiApplication.platformName() or 'Qt renderer'}"
        )
        self.diagnostics_environment.setProperty("diagnosticsMeta", True)
        diagnostics_copy.addWidget(self.troubleshooting_status)
        diagnostics_copy.addWidget(self.diagnostics_summary)
        diagnostics_copy.addWidget(self.diagnostics_checked)
        diagnostics_copy.addWidget(self.diagnostics_version)
        diagnostics_layout.addWidget(self.diagnostics_icon, 0, Qt.AlignmentFlag.AlignTop)
        diagnostics_layout.addLayout(diagnostics_copy, 1)
        a_layout.addWidget(self.diagnostics_card)
        self.debug_report_heading = QLabel("Technical details")
        self.debug_report_heading.setProperty("settingsHeading", True)
        self.debug_report_heading.hide()
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        # Technical details stay bounded and selectable. Long reports scroll
        # inside this deliberately self-contained diagnostic control.
        self.debug_report.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.debug_report.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.debug_report.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size:13px;")
        self.debug_report.setMinimumHeight(96)
        self.debug_report.setMaximumHeight(240)
        self.debug_report.hide()
        self.refresh_debug = QPushButton("Check again")
        self.copy_debug = QPushButton("Copy report")
        _set_button_variant(self.refresh_debug, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.copy_debug, BUTTON_VARIANT_SECONDARY)
        self.refresh_debug.clicked.connect(self._refresh_debug_report)
        self.copy_debug.clicked.connect(self._copy_debug_report)
        self.report_actions_panel = QWidget()
        self.report_actions = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            self.report_actions_panel,
        )
        self.report_actions.setContentsMargins(0, 0, 0, 0)
        self.report_actions.setSpacing(12)
        self.report_actions.addWidget(self.refresh_debug)
        self.report_actions.addWidget(self.copy_debug)
        self.report_details_toggle = QPushButton("Technical details")
        self.report_details_toggle.setCheckable(True)
        _set_button_variant(self.report_details_toggle, BUTTON_VARIANT_TERTIARY)
        self.report_details_toggle.toggled.connect(self._toggle_debug_report)
        self.report_actions.addWidget(self.report_details_toggle)
        self.report_actions.addStretch(1)
        a_layout.addWidget(self.report_actions_panel)
        self._report_actions_compact: bool | None = None
        self.report_actions_responsive = AdaptiveRow(
            "settings.troubleshooting-actions",
            (
                AdaptiveRegion.measured(
                    "refresh-diagnostics",
                    self.refresh_debug,
                    floor=144,
                ),
                AdaptiveRegion.measured(
                    "copy-report",
                    self.copy_debug,
                    floor=96,
                ),
                AdaptiveRegion.measured(
                    "technical-details",
                    self.report_details_toggle,
                    floor=168,
                ),
            ),
            spacing=12,
            apply_mode=self._set_report_actions_mode,
            telemetry_target=self.report_actions_panel,
        )
        self._sync_report_actions_layout()
        a_layout.addWidget(self.debug_report_heading)
        a_layout.addWidget(self.debug_report)
        self._refresh_debug_report()

        self.tabs.addTab(self.behavior_scroll, "Display")
        self.tabs.addTab(advanced, UI_TEXT["tab_advanced"])
        self.tabs.currentChanged.connect(self._sync_settings_tab)
        self._sync_settings_tab(0)
        self._refresh_garden_name()

    def _apply_settings_footer_layout(self, width: int) -> None:
        telemetry = self.settings_footer_responsive.evaluate(width)
        self.setProperty("footerMode", telemetry.mode)

    def _sync_report_actions_layout(self) -> None:
        if not hasattr(self, "report_actions_responsive"):
            return
        viewport = self.troubleshooting_scroll.viewport()
        telemetry = self.report_actions_responsive.evaluate(
            max(0, int(viewport.width()))
        )
        self.report_actions_panel.setProperty(
            "troubleshootingActionsMode",
            telemetry.mode,
        )

    def _set_report_actions_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._report_actions_compact:
            return
        self._report_actions_compact = compact
        self.report_actions.setDirection(QBoxLayout.Direction.LeftToRight)
        for button in (
            self.refresh_debug,
            self.copy_debug,
            self.report_details_toggle,
        ):
            button.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
        self.report_actions.invalidate()
        self.report_actions.activate()
        self.report_actions_panel.updateGeometry()
        content = self.troubleshooting_scroll.widget()
        content_layout = content.layout() if content is not None else None
        if content_layout is not None:
            content_layout.invalidate()
        if content is not None:
            content.updateGeometry()
        self.troubleshooting_scroll.updateGeometry()

    def _set_settings_footer_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._settings_footer_compact:
            return
        self._settings_footer_compact = compact
        buttons = (self.cancel_settings, self.save_settings)
        for button in buttons:
            self.settings_footer_grid.removeWidget(button)
            button.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
        for column in range(5):
            self.settings_footer_grid.setColumnStretch(column, 0)
        self.settings_footer_grid.addWidget(self.cancel_settings, 0, 0)
        self.settings_footer_grid.addWidget(self.save_settings, 0, 1)

    def _sync_settings_tab(self, index: int) -> None:
        diagnostics = int(index) == 1
        display_expanded = bool(
            self.behavior.fine_tune_toggle.isChecked()
            or self.behavior.advanced_toggle.isChecked()
        )
        # Troubleshooting is read-only. Keep draft actions reachable only when
        # the user arrived with unsaved Display changes.
        show_settings_actions = not diagnostics or self._draft_is_dirty()
        self.settings_footer_actions.setVisible(show_settings_actions)
        self.save_status.setVisible(bool(self.save_status.text()))
        self.footer.setVisible(show_settings_actions or bool(self.save_status.text()))
        self.setProperty(
            "layoutMode",
            "diagnostics" if diagnostics else "display",
        )
        self.apply_view_size_profile(
            "diagnostics-expanded"
            if diagnostics and self.debug_report.isVisible()
            else "diagnostics-clean" if diagnostics
            else "advanced" if display_expanded
            else "display"
        )
        QTimer.singleShot(0, self._sync_footer_clearance)
        QTimer.singleShot(0, self._sync_display_scroll_width)
        if diagnostics:
            QTimer.singleShot(0, self._sync_report_actions_layout)

    def _sync_display_scroll_width(self) -> None:
        """Keep the Display page inside the live vertical-scroll viewport."""

        if not hasattr(self, "behavior_scroll"):
            return
        viewport_width = max(0, int(self.behavior_scroll.viewport().width()))
        if viewport_width <= 0:
            return
        page = self.behavior_page
        page.setMinimumWidth(0)
        page.setMaximumWidth(viewport_width)
        if int(page.width()) != viewport_width:
            page.resize(viewport_width, page.height())
        page.updateGeometry()

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "settings_footer_grid"):
            margins = self._shell_layout.contentsMargins()
            self._apply_settings_footer_layout(
                max(
                    0,
                    int(event.size().width()) - margins.left() - margins.right(),
                )
            )
        super().resizeEvent(event)
        if hasattr(self, "behavior_scroll"):
            self._sync_display_scroll_width()
            QTimer.singleShot(0, self._sync_display_scroll_width)
        if hasattr(self, "report_actions_responsive"):
            self._sync_report_actions_layout()
            QTimer.singleShot(0, self._sync_report_actions_layout)
        if hasattr(self, "debug_report") and self.debug_report.isVisible():
            # The document retains the old wrap width until Qt settles the
            # resized viewport.
            QTimer.singleShot(0, self._sync_debug_report_height)

    def prepare_to_show(self) -> None:
        self._save_status_generation += 1
        self._persisted_name = str(
            getattr(self.engine.state, "garden_name", "My Garden") or "My Garden"
        )
        self._refresh_garden_name()
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.behavior.reset_preview_defaults()
        self.behavior.collapse_preview_examples()
        self.save_status.setText("")
        self.save_status.setStyleSheet("")
        self.save_status.hide()
        set_control_enabled(
            self.save_settings,
            False,
            disabled_reason="No unsaved settings changes.",
        )
        self.set_dialog_dirty(False)
        self.cancel_settings.setText("Cancel")
        self.cancel_settings.setAccessibleName("Cancel")

    def _refresh_garden_name(self) -> None:
        name = str(getattr(self.engine.state, "garden_name", "My Garden") or "My Garden")
        self.garden_name_edit.blockSignals(True)
        self.garden_name_edit.setText(name)
        self.garden_name_edit.blockSignals(False)
        self.garden_name_edit.setToolTip(name)
        self._update_garden_name_counter(name)
        self._set_garden_name_validation(True)

    def _update_garden_name_counter(self, text: str) -> None:
        count = len(str(text))
        self.garden_name_counter.setText(f"{count} / {MAX_GARDEN_NAME_LENGTH}")
        self.garden_name_counter.setVisible(count >= MAX_GARDEN_NAME_LENGTH - 5)
        self.garden_name_counter.setAccessibleDescription(
            f"{count} of {MAX_GARDEN_NAME_LENGTH} characters used."
        )

    def _modified_setting_count(self) -> int:
        def changed_leaves(current: Any, persisted: Any) -> int:
            if isinstance(current, dict) and isinstance(persisted, dict):
                return sum(
                    changed_leaves(current.get(key), persisted.get(key))
                    for key in set(current) | set(persisted)
                )
            return int(current != persisted)

        current = self.behavior.build_theme_payload()
        changed = changed_leaves(current, self._persisted_payload)
        draft_name = " ".join(self.garden_name_edit.text().split())
        return changed + int(draft_name != self._persisted_name)

    def _set_garden_name_validation(self, valid: bool) -> None:
        draft_name = " ".join(self.garden_name_edit.text().split())
        if not valid:
            self.garden_name_error.setText(
                "Enter a garden name."
                if not draft_name
                else f"Use {MAX_GARDEN_NAME_LENGTH} characters or fewer."
            )
        self.garden_name_edit.setProperty(
            "validationState", "valid" if valid else "error"
        )
        self.garden_name_error.setVisible(not valid)
        self.garden_name_edit.setAccessibleDescription(
            f"The name shown on your Garden and Anki home preview. Up to {MAX_GARDEN_NAME_LENGTH} characters."
            if valid else
            self.garden_name_error.text()
        )
        style = self.garden_name_edit.style()
        if style is not None:
            style.unpolish(self.garden_name_edit)
            style.polish(self.garden_name_edit)

    def _rename_garden(self) -> None:
        """Compatibility entrypoint: rename is now part of the dirty draft."""
        self.garden_name_edit.setFocus()
        self.garden_name_edit.selectAll()

    def _update_dirty_state(self) -> None:
        draft_name = " ".join(self.garden_name_edit.text().split())
        valid = bool(draft_name) and len(draft_name) <= MAX_GARDEN_NAME_LENGTH
        self._update_garden_name_counter(self.garden_name_edit.text())
        modified_count = self._modified_setting_count()
        dirty = modified_count > 0
        self._set_garden_name_validation(valid)
        self.set_dialog_dirty(dirty)
        self.cancel_settings.setText("Discard" if dirty else "Cancel")
        self.cancel_settings.setAccessibleName(self.cancel_settings.text())
        set_control_enabled(
            self.save_settings,
            dirty and valid,
            disabled_reason=(
                "Fix the Garden name error before saving."
                if dirty and not valid
                else "No unsaved settings changes."
            ),
            enabled_description="Save the current Anki Garden settings.",
        )
        if self.save_status.text() != "Saved":
            self.save_status.setText("")
            self.save_status.setStyleSheet("")
            self.save_status.setAccessibleDescription("")
            self.save_status.hide()
        self._sync_settings_tab(self.tabs.currentIndex())

    def _draft_is_dirty(self) -> bool:
        draft_name = " ".join(self.garden_name_edit.text().split())
        return (
            self.behavior.build_theme_payload() != self._persisted_payload
            or draft_name != self._persisted_name
        )

    def _restore_defaults(self) -> None:
        if not ConfirmationDialog.confirm(
            self,
            "Reset display settings?",
            "Garden name, preview, review rewards, motion, and Weather effects return to defaults.",
            confirm_label="Reset",
        ):
            return
        self.garden_name_edit.setText("My Garden")
        self.behavior.restore_persistent_defaults()
        self._update_dirty_state()
        if self.save_settings.isEnabled():
            self.save_status.setText("Defaults selected — save to apply")
            self.save_status.setAccessibleDescription(
                "Default settings are selected but have not been saved."
            )
        else:
            self.save_status.show()
            self.save_status.setText("Defaults are already active")
            self.save_status.setStyleSheet("color:#d8e3e5; background:#24343d;")
            self.save_status.setAccessibleDescription("The persisted settings already match the defaults.")

    def _preview_garden_name(self, text: str) -> None:
        preview = getattr(self.behavior, "set_preview_garden_name", None)
        if callable(preview):
            preview(" ".join(str(text).split()) or "My Garden")

    def _open_environment_management(self) -> None:
        self.reject()
        if self.isVisible():
            return
        parent = self.parentWidget()
        opener = getattr(parent, "_open_collection", None)
        if callable(opener):
            QTimer.singleShot(0, opener)

    def _save_visual_settings(self) -> None:
        old_payload = deepcopy(self._persisted_payload)
        old_name = self._persisted_name
        payload = self.behavior.build_theme_payload()
        draft_name = " ".join(self.garden_name_edit.text().split())
        if not draft_name or len(draft_name) > MAX_GARDEN_NAME_LENGTH:
            self._set_garden_name_validation(False)
            self._update_dirty_state()
            self.garden_name_edit.setFocus()
            self.garden_name_edit.selectAll()
            self.accessibility_announcer.announce(
                self.garden_name_error.text(),
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.garden_name_edit,
            )
            return
        try:
            self.config.update(payload)
        except ConfigError:
            self._show_save_error(
                "Couldn’t save settings. Your changes are still here."
            )
            return
        except Exception as exc:
            try:
                self.config.update(old_payload)
            except ConfigError:
                logger.exception("Anki Garden: unable to roll back settings")
            self._show_save_error(
                "Couldn’t save settings. Your changes are still here."
            )
            logger.exception("Anki Garden: settings save failed", exc_info=exc)
            return
        if draft_name != old_name:
            ok, message = self.engine.rename_garden(draft_name)
            if not ok:
                rollback_applied = False
                try:
                    self.config.update(old_payload)
                    rollback_applied = True
                except Exception:
                    logger.exception(
                        "Anki Garden: unable to roll back settings after name save failure"
                    )
                if rollback_applied:
                    failure_detail = "Nothing was changed."
                else:
                    # The visual configuration committed before the Garden name
                    # transaction failed. Keep the dialog's committed baseline in
                    # sync with that split outcome so retry and Cancel cannot imply
                    # that the visual settings were rolled back.
                    self._persisted_payload = deepcopy(payload)
                    self._persisted_name = old_name
                    self._update_dirty_state()
                    failure_detail = (
                        "Display settings were saved, but the garden name wasn’t. "
                        "Try saving the name again."
                    )
                self._show_save_error(
                    f"Couldn’t save the garden name. {failure_detail}"
                )
                return
        self._persisted_payload = deepcopy(payload)
        self._persisted_name = draft_name
        self.garden_name_edit.setText(draft_name)
        self.set_dialog_dirty(False)
        self.cancel_settings.setText("Cancel")
        self.cancel_settings.setAccessibleName("Cancel")
        clear_asset_cache = getattr(self.engine.assets, "clear_runtime_cache", None)
        if callable(clear_asset_cache):
            clear_asset_cache()
        parent = self.parent()
        if parent is not None:
            refresh_committed = getattr(parent, "_refresh_after_commit", None)
            if callable(refresh_committed):
                refresh_committed("settings update")
            elif hasattr(parent, "refresh_all"):
                try:
                    parent.refresh_all()
                except Exception:
                    logger.exception("Anki Garden: settings saved but parent refresh failed")
        set_control_enabled(
            self.save_settings,
            False,
            disabled_reason="Settings are already saved.",
        )
        self.save_status.show()
        self.save_status.setText("Saved")
        self.save_status.setStyleSheet("color:#baf3c6; background:#1d4931;")
        self.save_status.setAccessibleDescription("Settings saved.")
        self.accessibility_announcer.announce(
            "Settings saved.",
            target=self.save_status,
        )
        self._save_status_generation += 1
        generation = self._save_status_generation
        QTimer.singleShot(2400, lambda: self._hide_saved_status(generation))

    def _hide_saved_status(self, generation: int) -> None:
        if generation != self._save_status_generation:
            return
        if self.save_status.text() == "Saved" and not self.save_settings.isEnabled():
            self.save_status.setText("")
            self.save_status.setStyleSheet("")
            self.save_status.setAccessibleDescription("")
            self.save_status.hide()

    def _show_save_error(self, message: str) -> None:
        message = _learner_text(message)
        self._save_status_generation += 1
        self.save_status.show()
        self.save_status.setText(message)
        self.save_status.setStyleSheet("color:#ffd0d0; background:#582f34;")
        self.save_status.setAccessibleDescription(f"Settings error: {message}")
        self.save_status.setFocus()
        self.accessibility_announcer.announce(
            f"Settings error: {message}",
            priority=AnnouncementPriority.ASSERTIVE,
            target=self.save_status,
        )

    def reject(self) -> None:
        if self._draft_is_dirty() and not ConfirmationDialog.confirm(
            self,
            "Discard changes?",
            "Your changes won’t be saved.",
            confirm_label="Discard",
        ):
            return
        self._save_status_generation += 1
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.garden_name_edit.setText(self._persisted_name)
        self._update_garden_name_counter(self._persisted_name)
        self.set_dialog_dirty(False)
        self.cancel_settings.setText("Cancel")
        self.cancel_settings.setAccessibleName("Cancel")
        self.behavior.reset_preview_defaults()
        self.behavior.collapse_preview_examples()
        set_control_enabled(
            self.save_settings,
            False,
            disabled_reason="No unsaved settings changes.",
        )
        self.save_status.setText("")
        self.save_status.hide()
        super().reject()

    def _refresh_debug_report(self) -> None:
        report_lines = list(DISPLAY_TELEMETRY.report_lines())
        state = self.engine.state
        stats = state.daily_stats
        source_total = sum(max(0, int(value)) for value in (
            getattr(stats, "base_growth", 0),
            getattr(stats, "streak_bonus_growth", 0),
            getattr(stats, "fertilizer_growth", 0),
            getattr(stats, "booster_growth", 0),
            getattr(stats, "weather_growth", 0),
            getattr(stats, "scenery_growth", 0),
        ))
        nurtured_total = sum(
            max(0, int(value))
            for value in getattr(stats, "plant_nurtured_growth", {}).values()
        )
        passive_fifths = sum(
            max(0, int(value))
            for value in getattr(stats, "plant_passive_growth_fifths", {}).values()
        )
        passive_credited = sum(
            max(0, int(value))
            for value in getattr(stats, "plant_passive_growth_credited", {}).values()
        )
        residuals = sorted(
            (
                str(plant.plant_id),
                max(0, min(4, int(
                    getattr(plant, "passive_growth_remainder_fifths", 0) or 0
                ))),
            )
            for plant in getattr(state, "plants", [])
        )
        ledger = list(getattr(state, "completed_growth_charge_requests", []) or [])
        ledger_ids = [str(getattr(record, "request_id", "")) for record in ledger]
        report_lines.extend((
            f"Growth state schema: {int(getattr(state, 'version', STATE_VERSION))}",
            f"Growth source reconciliation: recorded={source_total:,}; "
            f"authoritative={int(getattr(stats, 'study_growth_generated', 0) or 0):,}",
            f"Growth target allocations: nurtured={nurtured_total:,}; "
            f"passive_exact={format_growth_fifths(passive_fifths)}; "
            f"passive_credited={passive_credited:,}; "
            f"charge={int(getattr(stats, 'charge_growth', 0) or 0):,}; "
            f"direct={int(getattr(stats, 'direct_reward_growth', 0) or 0):,}",
            "Passive residuals: " + (
                ", ".join(
                    f"{plant_id}={format_growth_fifths(remainder)}"
                    for plant_id, remainder in residuals
                ) or "none"
            ),
            f"Growth accounting stale: "
            f"{'yes' if getattr(stats, 'growth_accounting_stale', False) else 'no'}",
            f"Growth Charge replay ledger: entries={len(ledger):,}; "
            f"health={'healthy' if len(ledger_ids) == len(set(ledger_ids)) else 'duplicate request IDs'}",
        ))
        self.debug_report.setPlainText("\n".join(report_lines))
        self._sync_debug_report_height()

        def issue_count(attribute: str, prefix: str) -> int:
            value = getattr(DISPLAY_TELEMETRY, attribute, None)
            if value is not None:
                try:
                    return max(0, int(value))
                except (TypeError, ValueError):
                    pass
            for line in report_lines:
                if str(line).startswith(prefix):
                    try:
                        return max(0, int(str(line).split(":", 1)[1].strip().replace(",", "")))
                    except (IndexError, TypeError, ValueError):
                        return 0
            return 0

        contract_failures = issue_count("total_api_contract_failures", "API contract failures:")
        parsing_exceptions = issue_count("total_parsing_exceptions", "Parsing/formatting exceptions:")
        if contract_failures or parsing_exceptions:
            status = "Some artwork is missing"
            self.diagnostics_summary.setText(
                "Check again. Copy a report if the issue continues."
            )
            self.diagnostics_summary.show()
            self.diagnostics_icon.setText("!")
            self.diagnostics_icon.setAccessibleName("Diagnostics warning")
            self.diagnostics_icon.setStyleSheet(
                f"color:#2b120f; background:{GARDEN_THEME['warning']}; border-radius:20px;"
            )
            self.diagnostics_card.setProperty("diagnosticState", "warning")
        else:
            status = "No display issues found"
            self.diagnostics_summary.setText("")
            self.diagnostics_summary.hide()
            self.diagnostics_icon.setText("✓")
            self.diagnostics_icon.setAccessibleName("Diagnostics passed")
            self.diagnostics_icon.setStyleSheet("")
            self.diagnostics_card.setProperty("diagnosticState", "clean")
        card_style = self.diagnostics_card.style()
        if card_style is not None:
            card_style.unpolish(self.diagnostics_card)
            card_style.polish(self.diagnostics_card)
        self.troubleshooting_status.setText(status)
        self.troubleshooting_status.setAccessibleDescription(status)
        self.diagnostics_checked.setText(
            f"Checked {datetime.now().strftime('%-I:%M %p')}"
        )
        self.diagnostics_version.setText(
            f"Anki Garden {_addon_human_version()} · Build {_addon_build_identifier()} · "
            f"{platform.system() or 'Unknown OS'} · {QGuiApplication.platformName() or 'Qt renderer'}"
        )

    def _sync_debug_report_height(self) -> None:
        document = self.debug_report.document()
        document.setTextWidth(max(1, int(self.debug_report.viewport().width())))
        report_height = min(
            240,
            max(
                96,
                int(document.size().height())
                + 2 * int(self.debug_report.frameWidth())
                + 16,
            ),
        )
        self.debug_report.setFixedHeight(report_height)

    def _toggle_debug_report(self, expanded: bool) -> None:
        if expanded:
            self._refresh_debug_report()
        self.debug_report.setVisible(bool(expanded))
        self.debug_report_heading.setVisible(bool(expanded))
        self.diagnostics_version.setVisible(bool(expanded))
        if expanded:
            QTimer.singleShot(0, self._sync_debug_report_height)
        self.report_details_toggle.setText(
            "Hide technical details" if expanded else "Technical details"
        )
        self.copy_debug.setText("Copy report")
        self.report_details_toggle.setAccessibleName(self.report_details_toggle.text())
        self.setProperty(
            "layoutMode",
            "diagnostics-expanded" if expanded else "diagnostics",
        )
        self.apply_view_size_profile(
            "diagnostics-expanded" if expanded else "diagnostics-clean"
        )

    def _copy_debug_report(self) -> None:
        QGuiApplication.clipboard().setText(self.debug_report.toPlainText())
        self.diagnostics_checked.setText("Report copied to clipboard")
        self.diagnostics_card.setAccessibleDescription("Diagnostics report copied to the clipboard.")
        self.diagnostics_card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.diagnostics_card)
        self.diagnostics_card.setFocus()
        self.accessibility_announcer.announce(
            "Diagnostics report copied to the clipboard.",
            target=self.diagnostics_card,
        )

    def _recommended_window_size(
        self, default_width: int, default_height: int, *, width_ratio: float, height_ratio: float
    ) -> tuple[int, int]:
        screen = (self.parent().screen() if self.parent() is not None and hasattr(self.parent(), "screen") else None) or self.screen()
        if screen is None:
            return default_width, default_height
        available = screen.availableGeometry()
        width = min(default_width, max(self.minimumWidth(), int(available.width() * width_ratio)))
        height = min(default_height, max(self.minimumHeight(), int(available.height() * height_ratio)))
        return width, height


class MemoryTimeline(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Plant memory timeline")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 0, 6, 0)
        self.layout.setSpacing(0)

    def set_memories(self, memories: list[tuple[str, str]], *, just_beginning: bool = False) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not memories:
            empty = QLabel("New history will appear as this plant grows.")
            empty.setWordWrap(True)
            empty.setProperty("memoryFuture", True)
            self.layout.addWidget(empty)
        for display_date, text in memories:
            row = QFrame()
            row.setProperty("memoryRow", True)
            row.setMinimumWidth(0)
            row.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 4, 4)
            row_layout.setSpacing(8)
            marker = QLabel("●")
            marker.setProperty("memoryMarker", True)
            marker.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            marker.setAccessibleName(f"Memory on {display_date}")
            copy = QVBoxLayout()
            date_label = QLabel(display_date)
            date_label.setProperty("memoryDate", True)
            body = QLabel(text)
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setWordWrap(True)
            body.setMinimumWidth(0)
            body.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            copy.addWidget(date_label)
            copy.addWidget(body)
            row_layout.addWidget(marker)
            row_layout.addLayout(copy, 1)
            self.layout.addWidget(row)
        if just_beginning and memories:
            future = QLabel("New history will appear as this plant grows.")
            future.setWordWrap(True)
            future.setProperty("memoryFuture", True)
            self.layout.addWidget(future)
        self.updateGeometry()


class PlantStoryDialog(GardenDialog):
    chooseAnother = pyqtSignal()

    def __init__(self, parent: QWidget, engine: Any, plant_id: str) -> None:
        super().__init__(parent, "Plant Story")
        self.engine = engine
        self.plant_id = plant_id
        self.configure_close_policy(
            protect_dirty=True,
            confirm_dirty=self._confirm_discard_rename,
        )
        self.apply_size_policy(
            DialogSizeClass.PLANT_STORY,
        )
        self.apply_view_size_profile("default")
        self.setStyleSheet(_garden_dialog_stylesheet() + """
            QWidget[storyViewport='true'], QWidget[storyBody='true'] { background:#071a15; }
            QFrame[storyHero='true'] { background:transparent; border:0; }
            QFrame[storyTimeline='true'], QFrame[upNext='true'] { background:#0c261f; border:0; border-radius:12px; }
            QFrame[storyStages='true'] { background:transparent; border:0; }
            QFrame[storyStage='true'] { background:#0c261f; border:1px solid #20483c; border-radius:9px; }
            QFrame[storyStage='true'][storyStageState='reached'], QFrame[storyStage='true'][storyStageState='complete'] { background:#123228; border-color:#4f806e; }
            QFrame[storyStage='true'][storyStageState='current'] { background:#173b30; border:2px solid #e7c96a; }
            QFrame[storyStage='true'][storyStageState='preview'] { background:#0c261f; border-color:#31594a; }
            QFrame[storyStage='true'][storyStageState='undiscovered'] { background:#091d18; border-color:#5b5438; }
            QLabel[storyStageName='true'] { color:#cfe0d6; font-size:13px; font-weight:700; }
            QFrame[storyStageState='preview'] QLabel[storyStageName='true'], QFrame[storyStageState='undiscovered'] QLabel[storyStageName='true'] { color:#789083; }
            QLabel[storyStagePreview='true'] { background:transparent; border:0; color:#a9beb1; font-size:13px; }
            QFrame[memoryRow='true'] { border-left:2px solid #5cc58b; }
            QLabel[memoryMarker='true'] { color:#82e2ac; padding-left:2px; }
            QLabel[memoryDate='true'] { color:#9eb4a8; font-size:13px; font-weight:600; }
            QLabel[memoryFuture='true'] { color:#9eb4a8; font-style:italic; padding:10px 0; }
        """)
        self.story_scroll = QScrollArea()
        self.story_scroll.setWidgetResizable(True)
        self.story_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.story_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.story_scroll.setAccessibleName("Plant Story details")
        story_body = QWidget()
        story_body.setProperty("storyBody", True)
        content = QVBoxLayout(story_body)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)
        self.story_scroll.setWidget(story_body)
        self.story_scroll.viewport().setProperty("storyViewport", True)
        _set_scroll_surface(
            self.story_scroll,
            story_body,
            GARDEN_THEME["dialog_surface"],
        )
        self.set_body_widget(self.story_scroll)
        story_workspace = QWidget()
        story_workspace.setProperty("storyWorkspace", True)
        self.story_columns = QBoxLayout(
            QBoxLayout.Direction.LeftToRight, story_workspace
        )
        self.story_columns.setContentsMargins(0, 0, 0, 0)
        self.story_columns.setSpacing(16)
        self.story_left = QWidget()
        story_left_layout = QVBoxLayout(self.story_left)
        story_left_layout.setContentsMargins(0, 0, 0, 0)
        story_left_layout.setSpacing(10)
        self.story_right = QWidget()
        story_right_layout = QVBoxLayout(self.story_right)
        story_right_layout.setContentsMargins(0, 0, 0, 0)
        story_right_layout.setSpacing(10)
        self.story_columns.addWidget(self.story_left, 3)
        self.story_columns.addWidget(self.story_right, 5)
        self.story_workspace_responsive = AdaptiveSplit.for_box_layout(
            "plant-story.columns",
            AdaptiveRegion.measured("plant-facts", self.story_left, floor=300),
            AdaptiveRegion.measured("plant-history", self.story_right, floor=420),
            layout=self.story_columns,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=16,
            telemetry_target=story_workspace,
        )
        content.addWidget(story_workspace)
        hero = QFrame()
        hero.setProperty("storyHero", True)
        self.hero_layout = QVBoxLayout(hero)
        self.hero_layout.setContentsMargins(10, 8, 10, 8)
        self.name_heading = QLabel()
        self.name_heading.setTextFormat(Qt.TextFormat.PlainText)
        self.name_heading.setWordWrap(True)
        self.name_heading.setStyleSheet("font-size:22px; font-weight:800;")
        self.artwork = QLabel()
        self._story_artwork_size = 132
        self.artwork.setFixedSize(
            self._story_artwork_size,
            self._story_artwork_size,
        )
        self.artwork.setProperty("stagePreview", True)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setAccessibleName("Plant artwork")
        identity_text = QVBoxLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_heading, 1)
        self.edit_name_btn = QPushButton("Rename")
        self.edit_name_btn.setAccessibleName("Rename plant")
        self.edit_name_btn.setToolTip("Rename plant")
        self.edit_name_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _set_button_variant(self.edit_name_btn, BUTTON_VARIANT_TERTIARY)
        name_row.addWidget(self.edit_name_btn, 0, Qt.AlignmentFlag.AlignTop)
        identity_text.addLayout(name_row)

        self.rename_row = QHBoxLayout()
        self.rename_row.setSpacing(6)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_PLANT_NAME_LENGTH)
        self.name_edit.setAccessibleName("Plant name")
        self.save_name_btn = QPushButton("Save")
        self.cancel_name_btn = QPushButton("Cancel")
        _set_button_variant(self.save_name_btn, BUTTON_VARIANT_PRIMARY)
        _set_button_variant(self.cancel_name_btn, BUTTON_VARIANT_SECONDARY)
        self.rename_row.addWidget(self.name_edit, 1)
        self.rename_row.addWidget(self.save_name_btn)
        self.rename_row.addWidget(self.cancel_name_btn)
        identity_text.addLayout(self.rename_row)
        self.meta_grid = QGridLayout()
        self.meta_grid.setHorizontalSpacing(12)
        self.meta_grid.setVerticalSpacing(3)
        self.meta_values: dict[str, QLabel] = {}
        for row, key in enumerate(("summary", "planted")):
            label_text = ""
            label = QLabel(label_text)
            label.hide()
            label.setStyleSheet("color:#a9beb1; font-size:13px;")
            value = QLabel("")
            value.setWordWrap(True)
            self.meta_grid.addWidget(label, row, 0)
            self.meta_grid.addWidget(value, row, 1)
            self.meta_values[key] = value
        self.meta_grid.setColumnStretch(1, 1)
        identity_text.addLayout(self.meta_grid)
        try:
            nurtured_asset = self.engine.resolve_nurtured_marker_asset()
        except Exception:
            nurtured_asset = None
        self.nurturing_status = NurturedPlantBadge(nurtured_asset)
        self.stage_status_badge = QLabel("")
        self.stage_status_badge.setProperty("plantStageBadge", True)
        self.stage_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage_status_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.fertilized_status_badge = QLabel("Fertilized")
        self.fertilized_status_badge.setProperty("fertilizedBadge", True)
        self.fertilized_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fertilized_status_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.fertilized_status_badge.hide()
        self.fully_grown_status_badge = QLabel("Fully grown")
        self.fully_grown_status_badge.setProperty("fullyGrownBadge", True)
        self.fully_grown_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fully_grown_status_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.fully_grown_status_badge.hide()
        status_badges = QHBoxLayout()
        status_badges.setSpacing(6)
        status_badges.addWidget(self.stage_status_badge)
        status_badges.addWidget(self.nurturing_status)
        status_badges.addWidget(self.fertilized_status_badge)
        status_badges.addWidget(self.fully_grown_status_badge)
        status_badges.addStretch(1)
        identity_text.addLayout(status_badges)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.feedback)
        self.feedback.setAccessibleName("Plant name status")
        self.feedback.hide()
        identity_text.addWidget(self.feedback)
        identity_text.addStretch(1)
        self.hero_layout.addWidget(
            self.artwork, 0, Qt.AlignmentFlag.AlignHCenter
        )
        self.hero_layout.addLayout(identity_text, 1)
        story_left_layout.addWidget(hero)

        self.stage_path = QFrame()
        self.stage_path.setProperty("storyStages", True)
        self.stage_path.setAccessibleName("Six plant growth stages")
        self.stage_path_layout = QGridLayout(self.stage_path)
        self.stage_path_layout.setContentsMargins(0, 0, 0, 0)
        self.stage_path_layout.setHorizontalSpacing(4)
        self.stage_path_layout.setVerticalSpacing(4)
        self.stage_nodes: dict[str, tuple[QFrame, QLabel]] = {}
        for stage_key in GROWTH_STAGES:
            node = QFrame()
            node.setProperty("storyStage", True)
            node.setMinimumHeight(78)
            node_layout = QVBoxLayout(node)
            node_layout.setContentsMargins(5, 5, 5, 5)
            node_layout.setSpacing(1)
            stage_preview = ArtworkThumbnail()
            stage_preview.setFixedSize(42, 42)
            stage_preview.setProperty("storyStagePreview", True)
            stage_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_preview.setAccessibleName(
                f"{format_status_label(stage_key)} stage preview"
            )
            stage_name = QLabel(format_status_label(stage_key))
            stage_name.setProperty("storyStageName", True)
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_name.setWordWrap(True)
            node_layout.addWidget(stage_preview, 0, Qt.AlignmentFlag.AlignHCenter)
            node_layout.addWidget(stage_name)
            self.stage_nodes[stage_key] = (node, stage_preview)
        self._reflow_story_stages(540)
        story_right_layout.addWidget(self.stage_path)

        story_panel = QFrame()
        story_panel.setProperty("storyTimeline", True)
        story_layout = QVBoxLayout(story_panel)
        story_layout.setContentsMargins(10, 8, 10, 8)
        story_layout.setSpacing(4)
        timeline_label = QLabel("History")
        timeline_label.setStyleSheet("font-size:16px; font-weight:700;")
        story_layout.addWidget(timeline_label)
        self.timeline = MemoryTimeline()
        story_layout.addWidget(self.timeline)
        self.up_next = QFrame()
        self.up_next.setProperty("upNext", True)
        up_next_layout = QVBoxLayout(self.up_next)
        up_next_layout.setContentsMargins(10, 7, 10, 7)
        self.up_next_title = QLabel("Up next")
        self.up_next_title.setStyleSheet("font-weight:700; color:#d8b875;")
        self.up_next_text = QLabel("")
        self.up_next_text.setWordWrap(True)
        self.up_next_text.setAccessibleName("Next plant milestone")
        up_next_layout.addWidget(self.up_next_title)
        up_next_layout.addWidget(self.up_next_text)
        self.choose_another = QPushButton(FULLY_GROWN_ACTION)
        _set_button_variant(self.choose_another, BUTTON_VARIANT_PRIMARY)
        self.choose_another.setAccessibleDescription(FULLY_GROWN_MESSAGE)
        self.choose_another.clicked.connect(self.chooseAnother.emit)
        self.choose_another.hide()
        up_next_layout.addWidget(self.choose_another)
        self.stage_progress = LabeledProgress("Plant progress to the next stage")
        up_next_layout.addWidget(self.stage_progress)
        story_right_layout.addWidget(story_panel)
        story_right_layout.addWidget(self.up_next)
        story_right_layout.addStretch(1)
        story_left_layout.addStretch(1)
        self.edit_name_btn.clicked.connect(self._begin_rename)
        self.cancel_name_btn.clicked.connect(self._cancel_rename)
        self.save_name_btn.clicked.connect(self._save_name)
        self.name_edit.returnPressed.connect(self._save_name)
        self.name_edit.textChanged.connect(self._sync_rename_dirty_state)
        self._set_editing(False)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1_000)
        self.status_timer.timeout.connect(self.refresh)
        self.status_timer.start()
        self.refresh()

    def _set_story_hero_mode(self, mode: str) -> None:
        size = 112 if mode == COMPACT_MODE else 132
        if size == self._story_artwork_size:
            return
        self._story_artwork_size = size
        self.artwork.setFixedSize(size, size)
        plant = self._plant()
        if plant is not None:
            _populate_asset_preview(
                self.artwork,
                self.engine,
                plant.species,
                plant.growth_stage,
                size=size,
                fallback_text=format_status_label(plant.species),
            )

    def resizeEvent(self, event: Any) -> None:
        margins = self._shell_layout.contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "story_workspace_responsive"):
            telemetry = self.story_workspace_responsive.evaluate(available)
            self.setProperty("workspaceMode", telemetry.mode)
            self._set_story_hero_mode(telemetry.mode)
        self._reflow_story_stages(
            available if self.property("workspaceMode") == COMPACT_MODE else max(0, available - 316)
        )
        super().resizeEvent(event)

    def _reflow_story_stages(self, available: int) -> None:
        if not hasattr(self, "stage_path_layout"):
            return
        width = max(0, int(available))
        columns = 6 if width >= 780 else 3 if width >= 430 else 2
        if int(self.stage_path.property("stageColumns") or 0) == columns:
            return
        for node, _preview in self.stage_nodes.values():
            self.stage_path_layout.removeWidget(node)
        for index, stage_key in enumerate(GROWTH_STAGES):
            node, _preview = self.stage_nodes[stage_key]
            self.stage_path_layout.addWidget(node, index // columns, index % columns)
        for column in range(6):
            self.stage_path_layout.setColumnStretch(column, 1 if column < columns else 0)
        self.stage_path.setProperty("stageColumns", columns)

    def _plant(self) -> Any:
        return self.engine.plant_story(self.plant_id)

    def _set_editing(self, editing: bool, *, restore_focus: bool = False) -> None:
        self.name_heading.setVisible(not editing)
        self.name_edit.setVisible(editing)
        self.save_name_btn.setVisible(editing)
        self.cancel_name_btn.setVisible(editing)
        self.edit_name_btn.setVisible(not editing)
        if editing:
            self.name_edit.setFocus()
            self.name_edit.selectAll()
        elif restore_focus:
            QTimer.singleShot(0, self.edit_name_btn.setFocus)

    def _begin_rename(self) -> None:
        plant = self._plant()
        if plant is None:
            return
        self.name_edit.setText(plant.name)
        self.feedback.setText("")
        self.feedback.hide()
        self._set_editing(True)
        self._sync_rename_dirty_state()

    def _cancel_rename(self) -> None:
        self.feedback.setText("")
        self.feedback.setAccessibleDescription("")
        self.feedback.hide()
        self.set_dialog_dirty(False)
        self._set_editing(False, restore_focus=True)

    def _rename_is_dirty(self) -> bool:
        plant = self._plant()
        if plant is None or not self.name_edit.isVisible():
            return False
        return " ".join(self.name_edit.text().split()) != str(plant.name)

    def _sync_rename_dirty_state(self, *_args: Any) -> None:
        self.set_dialog_dirty(self._rename_is_dirty())

    def _confirm_discard_rename(self, _reason: DialogCloseReason) -> bool:
        return ConfirmationDialog.confirm(
            self,
            "Discard name change?",
            "The edited name won’t be saved.",
            confirm_label="Discard",
        )

    def keyPressEvent(self, event: Any) -> None:
        if self.name_edit.isVisible() and event.key() == Qt.Key.Key_Escape:
            self._cancel_rename()
            event.accept()
            return
        super().keyPressEvent(event)

    def _save_name(self) -> None:
        ok, message = self.engine.rename_plant(self.plant_id, self.name_edit.text())
        message = _learner_text(message)
        self.feedback.setText(message)
        self.feedback.setAccessibleDescription(message)
        self.feedback.setVisible(not ok)
        self.accessibility_announcer.announce(
            message,
            priority=(
                AnnouncementPriority.POLITE
                if ok
                else AnnouncementPriority.ASSERTIVE
            ),
            target=self if ok else self.feedback,
        )
        if ok:
            self.set_dialog_dirty(False)
            self._set_editing(False, restore_focus=True)
            self.refresh()
            parent = self.parent()
            if parent is not None:
                refresh_committed = getattr(parent, "_refresh_after_commit", None)
                if callable(refresh_committed):
                    refresh_committed("plant rename")
                elif hasattr(parent, "refresh_all"):
                    try:
                        parent.refresh_all()
                    except Exception:
                        logger.exception("Anki Garden: plant rename saved but parent refresh failed")
        else:
            self.feedback.setFocus()

    @staticmethod
    def _memory_text(memory: Any, name: str) -> str:
        del name
        if memory.kind == "planted":
            return "Joined your garden"
        if memory.kind == "first_nurture":
            return "Nurtured"
        if memory.kind == "stage":
            return f"Reached {format_status_label(memory.new_stage or 'new growth')}"
        if memory.kind == "streak":
            return f"{memory.value}-day Anki streak"
        if memory.kind == "reviews":
            return f"{memory.value:,}th card answer"
        return "Garden milestone"

    def refresh(self) -> None:
        plant = self._plant()
        if plant is None:
            self.name_heading.setText("Plant unavailable")
            for value in self.meta_values.values():
                value.setText("Unavailable")
            self.nurturing_status.hide()
            self.fertilized_status_badge.hide()
            self.fully_grown_status_badge.hide()
            self.set_dialog_dirty(False)
            self._set_editing(False)
            set_control_enabled(
                self.edit_name_btn,
                False,
                disabled_reason="This plant is no longer available to rename.",
            )
            self.artwork.setText("")
            _record_missing_artwork(
                category="plant",
                item_key=self.plant_id,
                source_path=None,
            )
            self.artwork.setPixmap(
                _missing_artwork_pixmap(
                    "plant",
                    self.artwork.width(), self.artwork.height()
                )
            )
            set_semantic_role(self.artwork, SemanticRole.MISSING_ART)
            self.artwork.setAccessibleDescription(
                "Plant artwork is unavailable; a botanical fallback illustration is shown."
            )
            self.timeline.set_memories([])
            return
        self.name_heading.setText(plant.name)
        stage = format_status_label(plant.growth_stage)
        active = self.engine.state.active_plant_id == plant.plant_id
        slot = getattr(plant, "slot_index", None)
        bed = f"Bed {int(slot) + 1}" if isinstance(slot, int) and slot >= 0 else "Collection"
        summary_parts = [stage, bed]
        if active:
            summary_parts.append("Nurtured")
        self.meta_values["summary"].setText(" · ".join(summary_parts))
        self.meta_values["planted"].setText(
            f"Planted {self._local_date(plant.planted_on)}"
        )
        progress = growth_display(plant.growth_points)
        self.stage_status_badge.hide()
        self.nurturing_status.hide()
        self.fully_grown_status_badge.hide()
        now = time.time()
        fertilizer_projection = fertilizer_status(
            self.engine,
            plant,
            now=now,
            description=FERTILIZER_EXPLANATION,
        )
        self.fertilized_status_badge.hide()
        if fertilizer_projection.active:
            self.fertilized_status_badge.setAccessibleName(
                fertilizer_projection.accessible_text
            )
            self.fertilized_status_badge.setToolTip(
                fertilizer_projection.accessible_text
            )
        _populate_asset_preview(
            self.artwork,
            self.engine,
            plant.species,
            plant.growth_stage,
            size=self._story_artwork_size,
            fallback_text=format_status_label(plant.species),
        )
        memories = chronological_memories(plant.memories)
        self.timeline.set_memories([
            (self._local_date(memory.occurred_on), self._memory_text(memory, plant.name))
            for memory in memories
        ], just_beginning=story_is_just_beginning(memories))
        for index, stage_key in enumerate(GROWTH_STAGES):
            node, stage_preview = self.stage_nodes[stage_key]
            stage_state = (
                "reached" if index < progress.stage_index else
                "current" if index == progress.stage_index else
                "undiscovered" if stage_key == GROWTH_STAGES[-1] else
                "preview"
            )
            _populate_asset_preview(
                stage_preview,
                self.engine,
                plant.species,
                stage_key,
                size=42,
                fallback_text=format_status_label(stage_key),
                rare_unlocked=stage_state != "undiscovered",
            )
            node.setProperty("storyStageState", stage_state)
            stage_name_label = next(
                (
                    child for child in node.findChildren(QLabel)
                    if bool(child.property("storyStageName"))
                ),
                None,
            )
            if stage_name_label is not None:
                stage_name_label.setText(format_status_label(stage_key))
            stage_state_label = {
                "reached": "Reached",
                "current": "Current",
                "preview": "Preview",
                "undiscovered": "Undiscovered",
            }[stage_state]
            stage_description = (
                f"{format_status_label(stage_key)} stage — {stage_state_label}"
            )
            node.setAccessibleName(stage_description)
            node.setToolTip("")
            style = node.style()
            if style is not None:
                style.unpolish(node)
                style.polish(node)
        if progress.fully_grown:
            self.up_next_title.setText("Fully grown")
            self.up_next_text.setText("")
            self.up_next_text.hide()
            self.up_next_text.setAccessibleDescription(
                f"Fully grown with {plant.growth_points:,} total Growth."
            )
            self.choose_another.show()
            self.stage_progress.hide()
        else:
            next_stage = format_status_label(progress.next_stage or "next stage")
            self.up_next_title.setText(
                f"Next: {next_stage} at {max(0, int(progress.next_threshold)):,} Growth"
            )
            self.choose_another.hide()
            self.up_next_text.setText("")
            self.up_next_text.hide()
            self.stage_progress.show()
            self.stage_progress.set_progress(
                "",
                progress.stage_points,
                max(1, progress.stage_goal),
                value_text=f"{progress.stage_points:,} / {progress.stage_goal:,}",
            )
            self.stage_progress.label.hide()

    @staticmethod
    def _local_date(value: str) -> str:
        try:
            from datetime import date
            parsed = date.fromisoformat(str(value)[:10])
            return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"
        except Exception:
            return str(value)


class StarterConfirmationDialog(DialogShell):
    """Small, decision-only confirmation used by first-run Nursery mode."""

    def __init__(self, parent: QWidget, engine: Any, species: str) -> None:
        super().__init__(parent)
        self.back_requested = False
        species_name = format_status_label(species)
        item_name = seed_title(species_name)
        self.setWindowTitle(f"Choose {species_name}?")
        self.apply_size_policy(DialogSizeClass.COMPACT_STATUS)
        self.setStyleSheet(_garden_dialog_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        content_host = QWidget()
        content_host.setAccessibleName("Starter choice details")
        content = QVBoxLayout(content_host)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        self.starter_artwork = _asset_preview_label(
            engine,
            species,
            GROWTH_STAGES[0],
            size=64,
            property_name="nurseryArtwork",
        )
        heading.addWidget(self.starter_artwork)
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(6)
        step = QLabel("")
        step.setProperty("plantGuidanceStep", True)
        title = QLabel(f"Choose {species_name}?")
        title.setProperty("dialogTitle", True)
        title.setWordWrap(True)
        body = QLabel("You can move it later.")
        body.setProperty("dialogSubtitle", True)
        body.setWordWrap(True)
        step.hide()
        copy.addWidget(title)
        copy.addWidget(body)
        heading.addWidget(copy_widget, 1)
        self.top_close = self.create_inline_close_button(content_host)
        heading.addWidget(
            self.top_close,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        content.addLayout(heading)
        layout.addWidget(content_host, 1)
        self.action_footer = QFrame()
        self.action_footer.setProperty("actionFooter", True)
        self.actions = QHBoxLayout()
        self.action_footer.setLayout(self.actions)
        self.actions.setContentsMargins(0, 8, 0, 0)
        self.actions.addStretch(1)
        self.back_action = QPushButton("Back")
        _set_button_variant(self.back_action, BUTTON_VARIANT_TERTIARY)
        self.back_action.clicked.connect(self._go_back)
        self.choose_action = QPushButton(f"Choose {species_name}")
        self.choose_action.setAccessibleName(f"Confirm {item_name}")
        self.choose_action.setAccessibleDescription(
            f"Confirm {item_name}, then choose its garden bed. {COST_FREE}."
        )
        _set_button_variant(self.choose_action, BUTTON_VARIANT_PRIMARY)
        self.choose_action.clicked.connect(self.accept)
        self.actions.addWidget(self.back_action)
        self.actions.addWidget(self.choose_action)
        layout.addWidget(self.action_footer)
        self.register_pinned_footer(self.action_footer)
        self.setTabOrder(self.back_action, self.choose_action)
        self.set_initial_focus(
            self.back_action,
            InitialFocusPolicy.SAFE_ACTION,
        )
        self.actions_responsive = AdaptiveRow.for_box_layout(
            "starter-confirmation.actions",
            (
                AdaptiveRegion.measured(
                    "go-back",
                    self.back_action,
                    floor=120,
                ),
                AdaptiveRegion.measured(
                    "choose-starter",
                    self.choose_action,
                    floor=120,
                ),
            ),
            layout=self.actions,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.action_footer,
        )
        self.heading_responsive = AdaptiveSplit.for_box_layout(
            "starter-confirmation.summary",
            AdaptiveRegion.measured(
                "starter-artwork",
                self.starter_artwork,
                floor=64,
            ),
            AdaptiveRegion.measured(
                "starter-copy",
                copy_widget,
                floor=240,
            ),
            layout=heading,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.LeftToRight,
            spacing=12,
            telemetry_target=content_host,
        )
        self.apply_view_size_profile("default")

    def _go_back(self) -> None:
        self.back_requested = True
        self.reject()

    def resizeEvent(self, event: Any) -> None:
        margins = self.layout().contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "actions_responsive"):
            actions = self.actions_responsive.evaluate(available)
            summary = self.heading_responsive.evaluate(available)
            mode = (
                COMPACT_MODE
                if COMPACT_MODE in {actions.mode, summary.mode}
                else WIDE_MODE
            )
            self.setProperty("actionMode", actions.mode)
            self.setProperty("summaryMode", summary.mode)
            self.setProperty("layoutMode", mode)
        super().resizeEvent(event)


class NurseryDialog(DialogShell):
    """Artwork-led catalog for starters, collected plants, and garden spaces."""

    def __init__(self, parent: QWidget, engine: Any, storage: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.storage = storage
        self.setWindowTitle("Nursery")
        self.apply_size_policy(
            DialogSizeClass.NURSERY,
        )
        self.setStyleSheet(foundation_stylesheet() + nursery_catalog_stylesheet() + """
            QWidget[gardenDialogShell='true'] { background:#071a15; color:#f3f7f2; }
            QFrame[nurseryHero='true'] { background:#0c261f; border:0; border-bottom:1px solid #31594b; border-radius:0; }
            QFrame[nurseryFooter='true'] { background:#071a15; border:0; border-top:1px solid #31594b; }
            QFrame[toastRegion='true'] { background:#17342e; border:1px solid #557665; border-radius:12px; }
            QFrame[toastRegion='true'][error='true'] { background:#582f34; border-color:#a85b64; }
            QLabel[toastIcon='true'] { color:#0b211a; background:#82e2ac; border:0; border-radius:12px; font-size:15px; font-weight:900; }
            QLabel[toastIcon='true'][error='true'] { color:#3b1116; background:#ffd0d0; }
            QFrame[nurseryResource='true'] { background:#123228; border:1px solid #416b5d; border-radius:10px; }
            QFrame[nurseryPlant='true'] { background:#46332a; border:1px solid #71513c; border-radius:12px; }
            QFrame[nurseryPlant='true']:hover { background:#513a2e; border-color:#b88a52; }
            QFrame[nurseryPlant='true'][unaffordable='true'] { background:#2b201c; border-color:#574337; }
            QFrame[nurseryGrowing='true'] { background:#35271f; border:1px solid #7d5d43; border-left:3px solid #b88a52; border-radius:10px; }
            QFrame[spaceBed='true'] { background:#30231d; border:1px solid #654b39; border-radius:12px; }
            QFrame[spaceBed='true'][spaceState='unlocked'] { background:#39442d; border-color:#78815a; }
            QFrame[spaceBed='true'][spaceState='new'] { background:#35563c; border:2px solid #9fd48c; }
            QFrame[spaceBed='true'][spaceState='next'] { background:#4a3625; border:2px solid #d5ad70; }
            QLabel[spaceBedIcon='true'] { color:#d5ad70; font-size:26px; font-weight:800; }
            QLabel[nurseryEyebrow='true'] { color:#d5ad70; font-size:12px; font-weight:800; letter-spacing:1.2px; }
            QLabel[nurseryTitle='true'] { font-size:24px; font-weight:800; }
            QLabel[nurserySection='true'] { color:#f8e8cf; font-size:16px; font-weight:800; padding:7px 2px 1px 2px; }
            QLabel[nurserySectionNote='true'] { color:#bca991; font-size:13px; padding:0 2px 4px 2px; }
            QLabel[nurseryPlantName='true'] { color:#fff3da; font-size:16px; font-weight:800; }
            QLabel[nurseryMeta='true'] { color:#d6c4ac; font-size:13px; }
            QLabel[nurseryOwnership='true'] { color:#d5ad70; font-size:12px; font-weight:800; letter-spacing:.8px; }
            QLabel[nurseryStageName='true'] { color:#fff3da; font-size:14px; font-weight:800; }
            QLabel[nurseryStageCount='true'] { color:#cdbba5; font-size:13px; }
            QLabel[nurseryShortfall='true'] { color:#f0cf8d; font-size:13px; }
            QLabel[nurseryCoinLabel='true'] { color:#bca991; font-size:12px; font-weight:800; letter-spacing:.7px; }
            QLabel[nurseryCoins='true'] { color:#f1c979; font-size:18px; font-weight:800; }
            QLabel[nurseryArtwork='true'] {
                background:qradialgradient(cx:0.5,cy:0.58,radius:0.78,fx:0.5,fy:0.58,stop:0 #55402e,stop:0.62 #32231d,stop:1 #211713);
                border:1px solid #795b42;
                border-radius:12px;
                color:#d6c4ac;
                font-size:12px;
                padding:0;
            }
            QTabWidget::pane { border:1px solid #654936; border-radius:12px; background:#2f211b; top:-1px; }
            QTabBar::tab { min-height:36px; max-height:36px; padding:0 12px; color:#b8d8c2; background:#0c261f; border:0; border-bottom:3px solid transparent; font-size:13px; font-weight:700; }
            QTabBar::tab:hover { color:#f3f7f2; background:#123228; border-color:#846044; }
            QTabBar::tab:selected { color:#fff3da; background:#17352c; border-color:#d5ad70; }
            QPushButton[nurseryCarouselNav='true'] { padding:2px 4px; font-size:13px; font-weight:700; }
            QScrollBar:vertical { width:10px; margin:2px; background:#2f211b; }
            QScrollBar::handle:vertical { min-height:30px; border-radius:4px; background:#795b42; }
            QScrollBar::handle:vertical:hover { background:#9b7650; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        hero = QFrame()
        hero.setProperty("nurseryHero", True)
        hero.setProperty("dialogHeader", True)
        self.hero_layout = QHBoxLayout(hero)
        self.hero_layout.setContentsMargins(16, 8, 16, 10)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        eyebrow = QLabel("NURSERY")
        eyebrow.setProperty("nurseryEyebrow", True)
        self.heading = QLabel(NURSERY_STARTER_TITLE)
        self.heading.setProperty("nurseryTitle", True)
        self.heading.setWordWrap(True)
        self.intro = QLabel(NURSERY_STARTER_RATIONALE)
        self.intro.setWordWrap(True)
        self.intro.setProperty("nurseryMeta", True)
        self.starter_count = QLabel(NURSERY_STARTER_COUNT)
        self.starter_count.setWordWrap(True)
        self.starter_count.setProperty("nurseryMeta", True)
        self.starter_count.hide()
        copy.addWidget(eyebrow)
        copy.addWidget(self.heading)
        copy.addWidget(self.intro)
        copy.addWidget(self.starter_count)
        self.hero_layout.addLayout(copy, 1)
        self.coin_resource = QFrame()
        self.coin_resource.setProperty("nurseryResource", True)
        resource_layout = QHBoxLayout(self.coin_resource)
        resource_layout.setContentsMargins(10, 6, 10, 6)
        resource_layout.setSpacing(7)
        coin_label = QLabel("GARDEN COINS")
        coin_label.setProperty("nurseryCoinLabel", True)
        coin_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.coins = QLabel("")
        self.coins.setAccessibleName("Garden Coins balance")
        self.coins.setProperty("nurseryCoins", True)
        apply_tabular_numerals(self.coins)
        self.coins.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.coins.setMinimumWidth(0)
        resource_layout.addWidget(coin_label)
        resource_layout.addWidget(self.coins)
        self.hero_layout.addWidget(self.coin_resource, 0, Qt.AlignmentFlag.AlignVCenter)
        self.top_close = self.create_inline_close_button(hero)
        self.hero_layout.addWidget(
            self.top_close,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        root.addWidget(hero)

        self.nursery_toast = GardenToast(self)
        self.nursery_toast.setAccessibleName("Nursery purchase update")
        _set_button_variant(
            self.nursery_toast.action,
            BUTTON_VARIANT_PRIMARY,
        )
        self.nursery_toast.dismiss.setText("Keep browsing")
        self.nursery_toast.dismiss.setAccessibleName("Keep browsing")
        self.nursery_toast.shown.connect(self._position_nursery_overlays)

        self.catalog_tabs = QTabWidget()
        self.catalog_tabs.setProperty("dialogBody", True)
        self.catalog_tabs.setProperty("nurseryCatalog", True)
        self.catalog_tabs.setDocumentMode(True)
        self.catalog_tabs.setAccessibleName("Nursery catalog sections")
        set_semantic_role(self.catalog_tabs.tabBar(), SemanticRole.TABS)
        # Keep category labels readable. At the minimum width Qt exposes
        # horizontal scroll controls instead of shrinking every tab.
        self.catalog_tabs.tabBar().setExpanding(False)
        self.catalog_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName("Plants catalog")
        self.catalog = QWidget()
        self.catalog.setProperty("nurseryCatalog", True)
        self.catalog_layout = QVBoxLayout(self.catalog)
        self.catalog_layout.setContentsMargins(2, 2, 2, 2)
        self.catalog_layout.setSpacing(9)
        self.scroll.setWidget(self.catalog)
        _set_scroll_surface(self.scroll, self.catalog, "#2f211b")
        self.catalog_tabs.addTab(self.scroll, "Plants")

        self.supplements_scroll = QScrollArea()
        self.supplements_scroll.setWidgetResizable(True)
        self.supplements_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.supplements_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.supplements_scroll.setAccessibleName(
            "Fertilizer and Boosters catalog"
        )
        self.supplements_catalog = QWidget()
        self.supplements_catalog.setProperty("nurseryCatalog", True)
        self.supplements_layout = QVBoxLayout(self.supplements_catalog)
        self.supplements_layout.setContentsMargins(6, 6, 6, 6)
        self.supplements_layout.setSpacing(9)
        self.supplements_scroll.setWidget(self.supplements_catalog)
        _set_scroll_surface(
            self.supplements_scroll,
            self.supplements_catalog,
            "#2f211b",
        )
        self.catalog_tabs.addTab(self.supplements_scroll, "Fertilizer and Boosters")

        self.upgrades_scroll = QScrollArea()
        self.upgrades_scroll.setWidgetResizable(True)
        self.upgrades_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.upgrades_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.upgrades_scroll.setAccessibleName("Garden beds catalog")
        self.upgrades_catalog = QWidget()
        self.upgrades_catalog.setProperty("nurseryCatalog", True)
        self.upgrades_layout = QVBoxLayout(self.upgrades_catalog)
        self.upgrades_layout.setContentsMargins(6, 6, 6, 6)
        self.upgrades_layout.setSpacing(9)
        self.upgrades_scroll.setWidget(self.upgrades_catalog)
        _set_scroll_surface(
            self.upgrades_scroll,
            self.upgrades_catalog,
            "#2f211b",
        )
        self.catalog_tabs.addTab(self.upgrades_scroll, "Garden beds")

        self.environment_scroll = QScrollArea()
        self.environment_scroll.setWidgetResizable(True)
        self.environment_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.environment_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.environment_scroll.setAccessibleName(
            "Weather and Scenery catalog"
        )
        self.environment_catalog = QWidget()
        self.environment_catalog.setProperty("nurseryCatalog", True)
        self.environment_layout = QVBoxLayout(self.environment_catalog)
        self.environment_layout.setContentsMargins(6, 6, 6, 6)
        self.environment_layout.setSpacing(9)
        self.environment_scroll.setWidget(self.environment_catalog)
        _set_scroll_surface(
            self.environment_scroll,
            self.environment_catalog,
            "#2f211b",
        )
        self.catalog_tabs.addTab(self.environment_scroll, "Weather and Scenery")
        self.starter_tab_note = QLabel(DISABLED_STARTER_TABS)
        self.starter_tab_note.setWordWrap(True)
        self.starter_tab_note.setProperty("nurseryMeta", True)
        self.starter_tab_note.setAccessibleName("Starter mode tab availability")
        self.starter_tab_note.hide()
        self.catalog_tabs.setTabToolTip(1, DISABLED_STARTER_TABS)
        self.catalog_tabs.setTabToolTip(2, DISABLED_STARTER_TABS)
        self.catalog_tabs.setTabToolTip(3, DISABLED_STARTER_TABS)
        self.catalog_tabs.tabBar().setUsesScrollButtons(True)
        self.catalog_tabs.currentChanged.connect(self._sync_catalog_intro)
        root.addWidget(self.starter_tab_note)
        root.addWidget(self.catalog_tabs, 1)

        self.status = QLabel("", self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Nursery status")
        self.status.setProperty("liveRegion", "polite")
        self.status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.status)
        apply_tabular_numerals(self.status)
        self._status_generation = 0
        self.status.hide()
        self.nursery_footer = QFrame()
        self.nursery_footer.setProperty("nurseryFooter", True)
        self.nursery_footer.setProperty("dialogFooter", True)
        footer = QHBoxLayout(self.nursery_footer)
        footer.setContentsMargins(0, 6, 0, 0)
        self.nursery_footer.setMaximumHeight(48)
        self.bed_button = QPushButton("")
        self._bed_purchase_pending = False
        self._bed_button_restore_enabled = False
        self._catalog_transaction_pending = False
        self._starter_choice_pending = False
        self._placement_transaction_pending = False
        self._receipt_outcome: PurchaseOutcome | None = None
        self.purchase_dialog: PurchaseConfirmationDialog | None = None
        self._recently_unlocked_bed: int | None = None
        _set_button_variant(self.bed_button, BUTTON_VARIANT_SECONDARY)
        self.bed_button.clicked.connect(self._unlock_bed)
        self.bed_affordability = QLabel("")
        self.bed_affordability.setWordWrap(True)
        self.bed_affordability.setProperty("nurseryShortfall", True)
        self.bed_affordability.setAccessibleName("Garden bed affordability")
        self.bed_affordability.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.bed_affordability)
        apply_tabular_numerals(self.bed_affordability)
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        _set_button_variant(self.close_button, BUTTON_VARIANT_SECONDARY)
        self.close_button.clicked.connect(self._close_nursery)
        footer.addWidget(self.close_button)
        root.addWidget(self.nursery_footer)
        self.register_pinned_footer(self.nursery_footer)
        for scroll_region in (
            self.scroll,
            self.supplements_scroll,
            self.upgrades_scroll,
            self.environment_scroll,
        ):
            self.register_scroll_region(scroll_region)

        self.hero_responsive = AdaptiveSplit.for_box_layout(
            "nursery.hero",
            AdaptiveRegion.measured(
                "nursery-introduction",
                copy,
                floor=360,
            ),
            AdaptiveRegion.measured(
                "garden-coins",
                self.coin_resource,
                floor=160,
            ),
            layout=self.hero_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=14,
            telemetry_target=self,
        )
        self.refresh()

    def _position_nursery_overlays(self) -> None:
        """Clamp Nursery feedback inside its active catalog, below the tabs."""

        if not hasattr(self, "catalog_tabs"):
            return
        tab_rect = self.catalog_tabs.geometry()
        inset = 12
        available_width = max(1, tab_rect.width() - (inset * 2))
        overlay_width = min(520, available_width)
        x = tab_rect.left() + max(inset, (tab_rect.width() - overlay_width) // 2)
        y = tab_rect.top() + self.catalog_tabs.tabBar().height() + inset
        for overlay in (self.nursery_toast, self.status):
            if not overlay.isVisible():
                continue
            overlay_height = min(84, max(44, overlay.sizeHint().height()))
            overlay.setGeometry(x, y, overlay_width, overlay_height)
            overlay.raise_()

    def resizeEvent(self, event: Any) -> None:
        margins = self.layout().contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "hero_responsive"):
            hero = self.hero_responsive.evaluate(available)
            hero_compact = hero.mode == COMPACT_MODE
            self.coin_resource.setMaximumWidth(190)
            self.coin_resource.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
            self.hero_layout.setAlignment(
                self.coin_resource,
                Qt.AlignmentFlag.AlignLeft
                if hero_compact
                else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.hero_layout.setContentsMargins(
                12 if hero_compact else 16,
                6 if hero_compact else 8,
                12 if hero_compact else 16,
                8 if hero_compact else 10,
            )
            self.setProperty("heroMode", hero.mode)
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_nursery_overlays)

    def _clear_catalog(self) -> None:
        while self.catalog_layout.count():
            item = self.catalog_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    @staticmethod
    def _clear_section(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _plant_artwork(self, species: str, stage: str, size: int = 96) -> QLabel:
        artwork = _asset_preview_label(
            self.engine,
            species,
            stage,
            size=size,
            property_name="nurseryArtwork",
        )
        if not artwork.toolTip():
            artwork.setToolTip(
                f"{format_status_label(species)} at the {format_status_label(stage)} stage"
            )
        return artwork

    def _plant_stage_strip(self, species: str) -> QWidget:
        strip = QWidget()
        strip.setAccessibleName(
            f"All six {format_status_label(species)} growth stages"
        )
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        for stage in GROWTH_STAGES:
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(
                self._plant_artwork(species, stage, 48),
                0,
                Qt.AlignmentFlag.AlignHCenter,
            )
            label = QLabel(format_status_label(stage))
            label.setProperty("nurseryStageCount", True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.addWidget(label)
            layout.addLayout(cell, 1)
        return strip

    def _plant_stage_carousel(self, species: str) -> QWidget:
        widget = QWidget()
        widget.setAccessibleName(
            f"{format_status_label(species)} growth stage previews"
        )
        widget.setMinimumWidth(286)
        widget.setMaximumWidth(330)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        preview = self._plant_artwork(species, "seed", 132)
        layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignVCenter)

        stage_details = QVBoxLayout()
        stage_details.setContentsMargins(0, 2, 0, 2)
        stage_details.setSpacing(6)
        stage_name = QLabel(format_status_label(GROWTH_STAGES[0]))
        stage_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        stage_name.setProperty("nurseryStageName", True)
        stage_name.setAccessibleName("Growth stage")
        stage_count = QLabel(f"Stage 1 of {len(GROWTH_STAGES)}")
        stage_count.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        stage_count.setProperty("nurseryStageCount", True)
        stage_count.setAccessibleName("Growth stage preview position")
        stage_details.addWidget(stage_name)
        stage_details.addWidget(stage_count)
        stage_details.addStretch(1)

        previous = QPushButton("← Previous")
        next_button = QPushButton("Next →")
        previous.setAccessibleName("Previous growth stage preview")
        next_button.setAccessibleName("Next growth stage preview")
        for button in (previous, next_button):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
            _set_compact_row_action(button)
            button.setProperty("nurseryCarouselNav", True)
            button.setFixedSize(84, COMPACT_BUTTON_HEIGHT)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        navigation = QHBoxLayout()
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(8)
        navigation.addWidget(previous)
        navigation.addWidget(next_button)
        stage_details.addLayout(navigation)
        state = {"index": 0}

        def sync_navigation() -> None:
            index = state["index"]
            stage = GROWTH_STAGES[index]
            stage_name.setText(format_status_label(stage))
            stage_count.setText(f"Stage {index + 1} of {len(GROWTH_STAGES)}")
            set_control_enabled(
                previous,
                index > 0,
                disabled_reason="This is the first growth stage.",
                enabled_description="Show the previous growth stage preview.",
            )
            set_control_enabled(
                next_button,
                index < len(GROWTH_STAGES) - 1,
                disabled_reason="This is the final growth stage.",
                enabled_description="Show the next growth stage preview.",
            )

        def update(delta: int) -> None:
            state["index"] = max(
                0,
                min(len(GROWTH_STAGES) - 1, state["index"] + delta),
            )
            stage = GROWTH_STAGES[state["index"]]
            replacement = self._plant_artwork(species, stage, 132)
            pixmap = replacement.pixmap()
            preview.setText(replacement.text())
            preview.setPixmap(pixmap if pixmap is not None else QPixmap())
            preview.setAccessibleName(replacement.accessibleName())
            preview.setToolTip(replacement.toolTip())
            preview.setAccessibleDescription(replacement.accessibleDescription())
            sync_navigation()

        previous.clicked.connect(lambda _checked=False: update(-1))
        next_button.clicked.connect(lambda _checked=False: update(1))
        layout.addLayout(stage_details, 1)
        sync_navigation()
        return widget

    def _section_label(self, text: str, note: str = "") -> None:
        label = QLabel(text)
        label.setProperty("nurserySection", True)
        self.catalog_layout.addWidget(label)
        if note:
            support = QLabel(note)
            support.setProperty("nurserySectionNote", True)
            support.setWordWrap(True)
            self.catalog_layout.addWidget(support)

    def _currently_growing_strip(self, plant: Any) -> QFrame:
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(11)
        summary_layout.addWidget(
            self._plant_artwork(plant.species, plant.growth_stage, 48)
        )
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(1)
        try:
            nurtured_asset = self.engine.resolve_nurtured_marker_asset()
        except Exception:
            nurtured_asset = None
        kicker = NurturedPlantBadge(nurtured_asset)
        active_fertilizer = fertilizer_status(
            self.engine,
            plant,
            now=time.time(),
            description=FERTILIZER_EXPLANATION,
        )
        badges = QHBoxLayout()
        badges.setSpacing(6)
        badges.addWidget(kicker)
        if active_fertilizer.active:
            fertilized = QLabel("Fertilized")
            fertilized.setProperty("fertilizedBadge", True)
            fertilized.setAccessibleName(active_fertilizer.accessible_text)
            fertilized.setToolTip(active_fertilizer.accessible_text)
            badges.addWidget(fertilized)
        badges.addStretch(1)
        title = QLabel(plant.name)
        title.setProperty("nurseryPlantName", True)
        progress = growth_display(plant.growth_points)
        stage = format_status_label(progress.stage)
        progress_text = (
            "Fully grown"
            if progress.fully_grown else
            f"{progress.stage_points:,} / {progress.stage_goal:,}"
        )
        meta = QLabel(f"{stage} · {progress_text}")
        meta.setProperty("nurseryMeta", True)
        meta.setTextFormat(Qt.TextFormat.PlainText)
        meta.setWordWrap(True)
        apply_tabular_numerals(meta)
        copy.addLayout(badges)
        copy.addWidget(title)
        copy.addWidget(meta)
        summary_layout.addWidget(copy_widget, 1)
        action = QPushButton("View in garden")
        _set_button_variant(action, BUTTON_VARIANT_TERTIARY)
        _set_compact_row_action(action)
        action.setAccessibleName(f"View {plant.name} in the garden")
        action.setAccessibleDescription(
            f"Close the Nursery and open {plant.name}'s plant card."
        )
        action.clicked.connect(
            lambda _checked=False, plant_id=plant.plant_id:
            self._view_in_garden(plant_id)
        )
        card = ResponsiveActionCard(
            summary,
            action,
            semantic_id="nursery.current-plant",
            summary_floor=205,
            action_floor=131,
            spacing=11,
            margins=(12, 6, 12, 6),
            wide_maximum_height=96,
        )
        card.setProperty("nurseryGrowing", True)
        card.setAccessibleDescription(
            f"Nurtured plant {plant.name}. {stage}. {progress_text}."
        )
        return card

    def _view_in_garden(self, plant_id: str) -> None:
        parent = self.parentWidget()
        self.accept()
        if parent is None:
            return

        def reveal() -> None:
            scene = getattr(parent, "scene", None)
            if scene is None:
                return
            scene.keep_card_open(str(plant_id))
            refresh = getattr(parent, "_refresh_selected_plant_card", None)
            if callable(refresh):
                refresh()

        QTimer.singleShot(0, reveal)

    def _return_to_garden(self) -> None:
        parent = self.parentWidget()
        self.accept()
        scene = getattr(parent, "scene", None)
        if scene is not None:
            QTimer.singleShot(0, scene.setFocus)

    def _owned_card(self, plant: Any) -> QFrame:
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        card.setProperty("nurseryCatalogCard", True)
        card.setProperty("catalogItemId", str(plant.plant_id))
        card.setProperty("catalogSpeciesId", str(plant.species))
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 8, 11, 8)
        row.setSpacing(10)
        row.addWidget(self._plant_artwork(plant.species, plant.growth_stage, 56))
        copy = QVBoxLayout()
        place = (
            f"Bed {plant.slot_index + 1}"
            if plant.planted else
            "Collection"
        )
        stage = format_status_label(plant.growth_stage)
        title = QLabel(f"{plant.name} · {stage} · {place}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title.setProperty("nurseryPlantName", True)
        copy.addWidget(title)
        row.addLayout(copy, 1)
        action = QPushButton(
            "Store" if plant.planted else "Place"
        )
        _set_button_variant(action, BUTTON_VARIANT_SECONDARY)
        action.setAccessibleName(
            f"Store {plant.name} in Collection"
            if plant.planted else
            f"Place {plant.name} in an available garden bed"
        )
        action.setAccessibleDescription(
            self._return_to_collection_copy(plant)
            if plant.planted else
            f"{plant.name}, {stage}, {place}."
        )
        blocked = bool(
            plant.planted
            and plant.plant_id == self.storage.state.active_plant_id
        )
        reason = "Finish or switch your nurtured plant first."
        set_control_enabled(
            action,
            not blocked,
            disabled_reason=reason,
            enabled_description=action.accessibleDescription(),
        )
        if blocked:
            card.setAccessibleDescription(reason)
            action.setToolTip(reason)
        action.clicked.connect(
            lambda _checked=False, selected=plant:
            self._confirm_return_to_collection(selected)
            if selected.planted else
            self._set_placement(selected.plant_id, False)
        )
        row.addWidget(action)
        _set_compact_row_action(action)
        return card

    @staticmethod
    def _return_to_collection_copy(plant: Any) -> str:
        bed_number = max(1, int(getattr(plant, "slot_index", 0) or 0) + 1)
        return (
            f"You will still own {plant.name}. It will be stored in Collection "
            f"with its Growth, memories, and active Fertilizer unchanged. "
            f"Garden Bed {bed_number} will become empty. Your nurtured plant "
            "will not change."
        )

    def _confirm_return_to_collection(self, plant: Any) -> None:
        if not bool(getattr(plant, "planted", False)):
            self._set_placement(str(plant.plant_id), False)
            return
        box = QMessageBox(self)
        box.setWindowTitle(UI_TEXT["app_title"])
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Store {plant.name}?")
        bed_number = max(1, int(getattr(plant, "slot_index", 0) or 0) + 1)
        box.setInformativeText(f"Bed {bed_number} will become empty.")
        confirm = box.addButton(
            "Store",
            QMessageBox.ButtonRole.AcceptRole,
        )
        keep = box.addButton(
            "Cancel",
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(keep)
        box.setEscapeButton(keep)
        box.exec()
        if box.clickedButton() is confirm:
            self._set_placement(str(plant.plant_id), True)

    def _available_card(self, species: str, starter_mode: bool) -> QFrame:
        if starter_mode:
            return self._starter_card(species)
        quote = self.engine.quote_purchase(PurchaseKind.SPECIES, species)
        presentation = purchase_presentation(quote, ignore_status=True)
        item_name = presentation.item_name
        price = presentation.price
        balance = int(self.storage.state.currency_balance)
        affordable, affordability = _affordability_status(price, balance)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        card.setProperty("nurseryCatalogCard", True)
        card.setProperty("catalogItemId", str(species))
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(9)
        card_layout.addWidget(
            self._plant_artwork(species, GROWTH_STAGES[0], 84),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(item_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setProperty("nurseryPlantName", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        stages = self._plant_stage_strip(species)
        stages.hide()
        card_layout.addWidget(stages)
        meta = QLabel(cost_label(price))
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        apply_tabular_numerals(meta)
        affordability_label = QLabel(
            _compact_affordability_status(
                price,
                balance,
                ready_text="Ready to purchase",
            )
            if not affordable
            else ""
        )
        affordability_label.setProperty("nurseryShortfall", True)
        affordability_label.setWordWrap(True)
        affordability_label.setVisible(not affordable)
        apply_tabular_numerals(affordability_label)
        details = QPushButton("Details")
        details.setCheckable(True)
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)
        _set_compact_row_action(details)

        def toggle_stages(checked: bool) -> None:
            stages.setVisible(checked)
            details.setText("Hide details" if checked else "Details")

        details.toggled.connect(toggle_stages)
        action = QPushButton("Buy")
        _set_button_variant(action, BUTTON_VARIANT_PRIMARY)
        _set_compact_row_action(action)
        action.setAccessibleName(
            presentation.primary_accessible_name
        )
        action.setAccessibleDescription(
            f"{presentation.outcome} {cost_label(price)}. {affordability}"
        )
        set_control_enabled(
            action,
            affordable,
            disabled_reason=f"{item_name} is not affordable yet. {affordability}",
            enabled_description=action.accessibleDescription(),
        )
        if not affordable:
            card.setProperty("unaffordable", True)
            card.setAccessibleName(f"{item_name} is not affordable yet")
            card.setAccessibleDescription(
                f"{item_name} costs {price:,} Garden Coins. {affordability}"
            )
            card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            set_keyboard_focus_surface(card)
        action.clicked.connect(
            lambda _checked=False, selected=species: self._purchase_species(selected)
        )
        footer = QHBoxLayout()
        footer.setSpacing(8)
        price_stack = QVBoxLayout()
        price_stack.setSpacing(0)
        price_stack.addWidget(meta)
        price_stack.addWidget(affordability_label)
        footer.addLayout(price_stack, 1)
        footer.addWidget(details, 0, Qt.AlignmentFlag.AlignBottom)
        footer.addWidget(action, 0, Qt.AlignmentFlag.AlignBottom)
        card_layout.addLayout(footer)
        return card

    def _starter_card(self, species: str) -> QFrame:
        """Reduced-choice first-run card: one decision and one disclosure."""

        species_name = format_status_label(species)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        card.setProperty("nurseryCatalogCard", True)
        card.setProperty("catalogItemId", str(species))
        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(card)
        item_name = seed_title(species_name)
        card.setAccessibleName(f"{item_name} starter plant")
        card.setAccessibleDescription(f"{item_name}. Free starter.")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(
            self._plant_artwork(species, GROWTH_STAGES[0], 84),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(item_name)
        title.setProperty("nurseryPlantName", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)
        stages = self._plant_stage_strip(species)
        stages.hide()
        details = QPushButton("Preview")
        details.setCheckable(True)
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)
        _set_compact_row_action(details)

        def toggle_stages(checked: bool) -> None:
            stages.setVisible(checked)
            details.setText("Hide preview" if checked else "Preview")
            details.setAccessibleDescription(
                f"{'Hide' if checked else 'Show'} all six {species_name} growth stages."
            )

        details.toggled.connect(toggle_stages)
        layout.addWidget(stages, 0, Qt.AlignmentFlag.AlignHCenter)
        actions = QHBoxLayout()
        choose = QPushButton("Choose")
        choose.setAccessibleName(f"Choose {item_name} as your first plant")
        choose.setAccessibleDescription(
            f"Choose {item_name}. {COST_FREE}."
        )
        _set_button_variant(choose, BUTTON_VARIANT_PRIMARY)
        _set_compact_row_action(choose)
        choose.clicked.connect(
            lambda _checked=False, selected=species: self._choose_starter(selected)
        )
        actions.addWidget(details)
        actions.addStretch(1)
        actions.addWidget(choose)
        layout.addLayout(actions)
        return card

    def _item_artwork(self, key: str, accessible_name: str, size: int = 96) -> QLabel:
        placeholder_kind = (
            PurchaseKind.FERTILIZER
            if str(key).startswith("fertilizer_")
            else PurchaseKind.GROWTH_CHARGE
            if str(key) in GROWTH_CHARGES
            else None
        )
        label = _item_preview_label(
            self.engine,
            key,
            accessible_name,
            size=size,
            placeholder_kind=placeholder_kind,
        )
        label.setProperty("nurseryArtwork", True)
        return label

    def _catalog_action_card(
        self,
        summary: QWidget,
        action: QWidget,
        *,
        semantic_id: str,
        summary_floor: int,
        action_floor: int,
        spacing: int = 10,
        margins: tuple[int, int, int, int] = (11, 9, 11, 9),
    ) -> ResponsiveActionCard:
        if isinstance(action, QPushButton):
            _set_compact_row_action(action)
        card = ResponsiveActionCard(
            summary,
            action,
            semantic_id=semantic_id,
            summary_floor=summary_floor,
            action_floor=action_floor,
            spacing=spacing,
            margins=margins,
        )
        card.setProperty("nurseryPlant", True)
        card.setProperty("nurseryCatalogCard", True)
        controllers = getattr(self, "_catalog_responsive_controllers", None)
        if isinstance(controllers, list):
            controllers.append(card.responsive)
        return card

    def _supplement_card(self, tier: str) -> QFrame:
        spec = self.engine.FERTILIZERS[tier]
        active = self.engine.active_plant()
        quote = self.engine.quote_purchase(
            PurchaseKind.FERTILIZER,
            tier,
            target_id=getattr(active, "plant_id", None),
        )
        presentation = purchase_presentation(quote, ignore_status=True)
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(self._item_artwork(
            f"fertilizer_{tier}", f"{spec.name} bag preview", 56
        ))
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        title = QLabel(spec.name)
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        duration = str(quote.descriptor.duration or "").strip().rstrip(".")
        meta = QLabel(
            f"+{spec.growth_per_answer:,} Growth per card · "
            f"{duration} · {cost_label(spec.price)}"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        summary_layout.addWidget(copy_widget, 1)
        affordable = self.storage.state.currency_balance >= spec.price
        active_fertilizer = getattr(active, "fertilizer", None) if active is not None else None
        selected_tier = (
            str(getattr(active_fertilizer, "tier", "") or "").lower()
            if active_fertilizer is not None
            and float(getattr(active_fertilizer, "expires_at", 0) or 0) > time.time()
            else ""
        )
        recommended = (
            str(tier).lower() == selected_tier
            or (not selected_tier and str(tier).lower() == "basic")
        )
        action_text = (
            "Buy and replace"
            if quote.replacement_required
            else "Extend"
            if quote.disposition is PurchaseDisposition.EXTENDED
            else "Buy and apply"
        )
        action = QPushButton(_qt_button_text(action_text))
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY
            if affordable and active is not None and recommended
            else BUTTON_VARIANT_SECONDARY,
        )
        shortfall = max(0, int(spec.price) - int(self.storage.state.currency_balance))
        reason = (
            presentation.outcome
            if active is not None and affordable else
            f"Need {shortfall:,} more Garden Coins."
            if active is not None else
            "Choose an unfinished planted plant to nurture first."
        )
        action.setAccessibleName(
            presentation.primary_accessible_name
        )
        action.setAccessibleDescription(
            f"{cost_label(spec.price)}. {reason}"
        )
        set_control_enabled(
            action,
            affordable and active is not None,
            disabled_reason=reason,
            enabled_description=action.accessibleDescription(),
        )
        action.clicked.connect(
            lambda _checked=False, selected=tier: self._purchase_fertilizer(selected)
        )
        if active is not None and not affordable:
            helper = QLabel(f"{shortfall:,} more Garden Coins needed")
            helper.setProperty("nurseryShortfall", True)
            helper.setWordWrap(True)
            apply_tabular_numerals(helper)
            copy.addWidget(helper)
        card = self._catalog_action_card(
            summary,
            action,
            semantic_id=f"nursery.fertilizer-{tier}",
            summary_floor=205,
            action_floor=96,
        )
        card.setProperty("catalogItemId", str(tier))
        return card

    def _booster_card(self) -> QFrame:
        count = max(0, int(self.storage.state.consumables.get("booster_potion", 0)))
        booster_definition = next(
            item
            for item in collectible_registry()
            if item.item_id == "growth_items:booster_potion"
        )
        booster_descriptor = booster_definition.descriptor
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(self._item_artwork(
            "booster_potion", "Booster Potion preview", 56
        ))
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        title = QLabel(f"Booster Potion — {count} owned")
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        apply_tabular_numerals(title)
        meta = QLabel(" ".join((
            booster_descriptor.buff,
            booster_descriptor.duration,
            booster_descriptor.unlock_requirement,
        )))
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        summary_layout.addWidget(copy_widget, 1)
        active = self.engine.active_plant()
        action = QPushButton("Use potion")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if count > 0 and active is not None else BUTTON_VARIANT_SECONDARY,
        )
        action.setAccessibleDescription(
            f"Use one Booster Potion on {active.name}."
            if active is not None and count > 0 else
            "A Booster Potion and a nurtured unfinished plant are required."
        )
        set_control_enabled(
            action,
            count > 0 and active is not None,
            disabled_reason=(
                "A Booster Potion and a nurtured unfinished plant are required."
            ),
            enabled_description=action.accessibleDescription(),
        )
        action.clicked.connect(self._use_booster)
        return self._catalog_action_card(
            summary,
            action,
            semantic_id="nursery.booster-potion",
            summary_floor=205,
            action_floor=112,
        )

    def _basic_fertilizer_inventory_card(self) -> QFrame:
        count = max(0, int(
            self.storage.state.consumables.get("fertilizer_basic", 0)
        ))
        definition = next(
            item
            for item in collectible_registry()
            if item.item_id == "growth_items:fertilizer_basic"
        )
        descriptor = definition.descriptor
        basic = self.engine.FERTILIZERS["basic"]
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(self._item_artwork(
            "fertilizer_basic", f"{definition.name} preview", 56
        ))
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        title = QLabel(f"{definition.name} · {count} owned")
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        apply_tabular_numerals(title)
        meta = QLabel(
            f"+{basic.growth_per_answer:,} Growth per card for "
            f"{str(descriptor.duration or '').strip().rstrip('.')}"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        summary_layout.addWidget(copy_widget, 1)
        active = self.engine.active_plant()
        usable = count > 0 and active is not None
        action = QPushButton("Use")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if usable else BUTTON_VARIANT_SECONDARY,
        )
        action.setAccessibleName(
            f"Use {definition.name} on {active.name}"
            if active is not None else
            f"Use {definition.name}"
        )
        action.setAccessibleDescription(
            f"Use one {definition.name} to apply {basic.name} to {active.name}."
            if usable else
            f"{definition.name} and a nurtured unfinished planted plant are required."
        )
        set_control_enabled(
            action,
            usable,
            disabled_reason=(
                f"{definition.name} and a nurtured unfinished planted plant are required."
            ),
            enabled_description=action.accessibleDescription(),
        )
        action.clicked.connect(self._use_basic_fertilizer)
        return self._catalog_action_card(
            summary,
            action,
            semantic_id="nursery.fertilizer-basic-inventory",
            summary_floor=205,
            action_floor=150,
        )

    def _growth_charge_card(self, spec: GrowthChargeSpec) -> QFrame:
        count = max(0, int(self.storage.state.consumables.get(spec.charge_id, 0)))
        quote = self.engine.quote_purchase(PurchaseKind.GROWTH_CHARGE, spec.charge_id)
        presentation = purchase_presentation(quote, ignore_status=True)
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(self._item_artwork(
            spec.charge_id, f"{spec.name} preview", 56
        ))
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        title = QLabel(spec.name)
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        apply_tabular_numerals(title)
        effect = f"+{spec.growth:,} Growth"
        meta = QLabel(" · ".join((
            effect,
            cost_label(spec.price) if spec.price is not None else "Unavailable",
        )))
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        summary_layout.addWidget(copy_widget, 1)
        active = self.engine.active_plant()
        helper_text = ""
        show_helper = False
        if count > 0:
            action = QPushButton("Use")
            enabled = active is not None
            available = QLabel(f"{count:,} available")
            available.setProperty("nurseryMeta", True)
            apply_tabular_numerals(available)
            copy.addWidget(available)
            if not enabled:
                helper_text = (
                    "Nurture an unfinished planted plant before using this item."
                )
            action.setAccessibleDescription(
                f"Use one {spec.name} on {active.name}."
                if enabled else
                helper_text
            )
            action.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id:
                self._use_growth_charge(charge_id)
            )
        elif spec.price is not None:
            affordable = self.storage.state.currency_balance >= spec.price
            action = QPushButton("Buy")
            enabled = affordable
            if not affordable:
                helper_text = f"{spec.price - self.storage.state.currency_balance:,} more needed"
                show_helper = True
            action.setAccessibleName(
                presentation.primary_accessible_name
            )
            action.setAccessibleDescription(
                f"{cost_label(spec.price)}. {effect}. "
                + (
                    "Affordable with your Garden Coins balance."
                    if affordable else
                    f"{spec.price - self.storage.state.currency_balance:,} "
                    "more Garden Coins needed."
                )
            )
            action.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id:
                self._purchase_growth_charge(charge_id)
            )
        else:
            action = QWidget()
            action.hide()
            enabled = False
        if isinstance(action, QPushButton):
            _set_button_variant(
                action,
                BUTTON_VARIANT_PRIMARY if enabled else BUTTON_VARIANT_SECONDARY,
            )
            set_control_enabled(
                action,
                enabled,
                disabled_reason=action.accessibleDescription(),
                enabled_description=action.accessibleDescription(),
            )
        if show_helper and helper_text:
            helper = QLabel(helper_text)
            helper.setProperty("nurseryShortfall", True)
            helper.setWordWrap(True)
            apply_tabular_numerals(helper)
            copy.addWidget(helper)
        card = self._catalog_action_card(
            summary,
            action,
            semantic_id=f"nursery.{spec.charge_id}",
            summary_floor=205,
            action_floor=160,
        )
        card.setProperty("catalogItemId", str(spec.charge_id))
        return card

    def _environment_artwork(
        self,
        item: CatalogItem,
        *,
        silhouette: bool = False,
        width: int = 176,
        height: int = 104,
    ) -> QLabel:
        label = QLabel()
        label.setFixedSize(width, height)
        label.setProperty("nurseryArtwork", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(
            f"Locked {item.kind} silhouette" if silhouette else f"{item.name} preview"
        )
        if silhouette:
            label.setText("?")
            label.setStyleSheet(
                "background:#171513; border:1px solid #6b5847; border-radius:12px; "
                "color:#827566; font-size:38px; font-weight:800;"
            )
            return label
        available = False
        try:
            resolver = (
                self.engine.resolve_weather_preview_asset
                if item.kind == "weather"
                else self.engine.resolve_scenery_preview_asset
            )
            resolved = resolver(item.item_id)
            path = getattr(resolved, "path", None)
            available = bool(path and not _preview_source_pixmap(path).isNull())
        except Exception:
            logger.exception(
                "Anki Garden: Nursery artwork resolution failed for %s",
                item.item_id,
            )
        label.setPixmap(_environment_preview_pixmap(
            self.engine,
            item,
            width - 10,
            height - 10,
        ))
        if not available:
            set_semantic_role(label, SemanticRole.MISSING_ART)
            label.setAccessibleDescription(
                f"Artwork unavailable for {item.name}; a {item.kind} placeholder is shown."
            )
            label.setToolTip(f"{item.name} artwork unavailable")
        return label

    def _environment_shop_card(self, item: CatalogItem) -> QFrame:
        owned = self.engine.owns_environment(item.kind, item.item_id)
        quote = self.engine.quote_purchase(PurchaseKind(item.kind), item.item_id)
        presentation = purchase_presentation(quote, ignore_status=True)
        equipped = (
            self.storage.state.selected_weather == item.item_id
            if item.kind == "weather" else
            self.storage.state.selected_background == item.item_id
        )
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        card.setProperty("nurseryCatalogCard", True)
        card.setProperty("catalogItemId", str(item.item_id))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._environment_artwork(item, width=180, height=101),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        item_status = "Equipped" if equipped else "Owned" if owned else ""
        title = QLabel(
            " · ".join(part for part in (item.name, item_status) if part)
        )
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        meta = QLabel(" · ".join(filter(None, (
            item.rarity,
            "" if owned else
            cost_label(item.price) if item.purchasable else item.how_to_earn,
        ))))
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        layout.addWidget(title)
        layout.addWidget(meta)
        actions = QHBoxLayout()
        details = QPushButton("Preview")
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)
        _set_compact_row_action(details)
        details.clicked.connect(
            lambda _checked=False, selected=item: self._preview_environment_item(selected)
        )
        actions.addWidget(details)
        actions.addStretch(1)
        affordable = bool(
            item.purchasable
            and self.storage.state.currency_balance >= item.price
        )
        affordability = (
            "Affordable with the current Garden Coin balance."
            if affordable else
            item.how_to_earn
            if not item.purchasable else
            f"Need {int(item.price or 0) - self.storage.state.currency_balance:,} more Garden Coins."
        )
        if item.purchasable and not owned and not affordable:
            shortfall = QLabel(affordability)
            shortfall.setProperty("nurseryShortfall", True)
            shortfall.setWordWrap(True)
            apply_tabular_numerals(shortfall)
            layout.addWidget(shortfall)
        action = QPushButton(
            "View in Collection" if owned else
            "Buy" if item.purchasable else
            "Garden Find only" if item.drop_only else
            "Included"
        )
        action.setAccessibleName(
            f"Open Collection for {item.name}"
            if owned else
            presentation.primary_accessible_name
            if item.purchasable else
            f"How to earn {item.name}"
        )
        _set_button_variant(
            action, BUTTON_VARIANT_PRIMARY if owned or affordable else BUTTON_VARIANT_SECONDARY
        )
        _set_compact_row_action(action)
        action.setAccessibleDescription(
            f"Open Collection to preview or equip {item.name}."
            if owned else
            f"{cost_label(int(item.price or 0))}. {affordability} {presentation.outcome}"
            if item.purchasable else
            item.how_to_earn
        )
        set_control_enabled(
            action,
            owned or affordable,
            disabled_reason=(
                f"{item.name} is not affordable yet. {affordability}"
                if item.purchasable else
                item.how_to_earn
            ),
            enabled_description=action.accessibleDescription(),
        )
        if owned:
            action.clicked.connect(self._open_customize_from_nursery)
        elif item.purchasable:
            action.clicked.connect(
                lambda _checked=False, kind=item.kind, item_id=item.item_id:
                self._purchase_environment(kind, item_id)
            )
        actions.addWidget(action)
        layout.addLayout(actions)
        return card

    def _preview_environment_item(self, item: CatalogItem) -> None:
        if not hasattr(self, "environment_feature_art"):
            return
        replacement = self._environment_artwork(item, width=360, height=202)
        pixmap = replacement.pixmap()
        self.environment_feature_art.setText("")
        self.environment_feature_art.setPixmap(
            pixmap
            if pixmap is not None and not pixmap.isNull()
            else _environment_placeholder_pixmap(350, 192)
        )
        self.environment_feature_art.setAccessibleName(replacement.accessibleName())
        self.environment_feature_art.setAccessibleDescription(
            replacement.accessibleDescription()
        )
        self.environment_feature_art.setProperty(
            "gardenRole",
            replacement.property("gardenRole") or "",
        )
        self.environment_feature_title.setText(item.name)
        presentation = purchase_presentation(
            self.engine.quote_purchase(PurchaseKind(item.kind), item.item_id),
            ignore_status=True,
        )
        equipped = (
            self.storage.state.selected_weather == item.item_id
            if item.kind == "weather" else
            self.storage.state.selected_background == item.item_id
        )
        self.environment_feature_meta.setText(
            " · ".join(filter(None, (
                item.rarity,
                "Equipped" if equipped else "",
                _purchase_fact(presentation, "effect"),
            )))
        )

    def _open_customize_from_nursery(self) -> None:
        """Compatibility route: all retired Customize actions open Collection."""

        parent = self.parentWidget()
        self.accept()
        opener = getattr(parent, "_open_collection", None)
        if callable(opener):
            QTimer.singleShot(0, opener)

    def _space_card(self, index: int) -> QFrame:
        state = self.storage.state
        unlocked = index < int(state.unlocked_slots)
        next_space = index == int(state.unlocked_slots)
        price = self.engine.BED_PRICES.get(index)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        title = QLabel(f"Bed {index + 1}")
        title.setStyleSheet("font-weight:700;")
        apply_tabular_numerals(title)
        status = QLabel(
            "Unlocked"
            if unlocked else
            cost_label(price)
            if next_space and price is not None else
            "Unlock the previous bed first"
        )
        status.setProperty("nurseryMeta", True)
        apply_tabular_numerals(status)
        copy = QVBoxLayout()
        copy.addWidget(title)
        copy.addWidget(status)
        row.addLayout(copy, 1)
        if next_space and price is not None:
            affordable = state.currency_balance >= price
            self.bed_button = QPushButton("Unlock")
            _set_button_variant(self.bed_button, BUTTON_VARIANT_PRIMARY)
            _set_compact_row_action(self.bed_button)
            self.bed_button.clicked.connect(self._unlock_bed)
            self.bed_button.setText("Unlock")
            self.bed_button.setAccessibleName(
                f"Unlock Garden Bed {index + 1} for {price:,} Garden Coins"
            )
            set_control_enabled(
                self.bed_button,
                affordable and not self._bed_purchase_pending,
                disabled_reason=(
                    "Please wait while the garden bed is unlocked."
                    if self._bed_purchase_pending
                    else f"Need {price - state.currency_balance:,} more Garden Coins."
                ),
                enabled_description=(
                    f"Unlock Garden Bed {index + 1} for {price:,} Garden Coins."
                ),
            )
            row.addWidget(self.bed_button)
            self.bed_affordability = QLabel("")
            self.bed_affordability.setProperty("nurseryShortfall", True)
            self.bed_affordability.setText(
                "Ready to unlock" if affordable else f"{price - state.currency_balance:,} more needed"
            )
            row.addWidget(self.bed_affordability)
        else:
            marker = QLabel("Unlocked" if unlocked else "Locked")
            marker.setProperty("nurseryMeta", True)
            row.addWidget(marker)
        return card

    def _space_progression(self) -> QWidget:
        state = self.storage.state
        unlocked_count = max(0, min(6, int(state.unlocked_slots)))
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        summary = QLabel(f"{unlocked_count} of 6 beds unlocked")
        summary.setProperty("nurserySection", True)
        summary.setAccessibleName(summary.text())
        layout.addWidget(summary)
        beds = ResponsiveTileGrid(
            breakpoint=568,
            minimum_tile_width=84,
            maximum_columns=6,
        )
        beds.grid.setHorizontalSpacing(8)
        beds.grid.setVerticalSpacing(8)
        for index in range(6):
            unlocked = index < unlocked_count
            next_bed = index == unlocked_count and index < 6
            newly_unlocked = unlocked and index == self._recently_unlocked_bed
            cell = QFrame()
            cell.setProperty("spaceBed", True)
            cell.setProperty(
                "spaceState",
                "new" if newly_unlocked else
                "unlocked" if unlocked else
                "next" if next_bed else
                "future",
            )
            cell.setProperty("catalogItemId", str(index))
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(7, 8, 7, 8)
            cell_layout.setSpacing(3)
            icon = QLabel("")
            icon.setProperty("spaceBedIcon", True)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_name = "collection" if unlocked else "plant" if next_bed else "lock"
            icon_color = "#d5ad70" if next_bed else "#b8d8c2" if unlocked else "#827566"
            icon.setPixmap(garden_icon(icon_name, color=icon_color).pixmap(26, 26))
            icon.setAccessibleName(
                "New garden bed" if next_bed else
                "Unlocked garden bed" if unlocked else
                "Locked garden bed"
            )
            number = QLabel(f"Bed {index + 1}")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status = QLabel("Newly unlocked" if newly_unlocked else "")
            status.setProperty("nurseryMeta", True)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setVisible(newly_unlocked)
            cell_layout.addWidget(icon)
            cell_layout.addWidget(number)
            cell_layout.addWidget(status)
            cell.setAccessibleName(
                f"Garden bed {index + 1}, "
                f"{'newly unlocked' if newly_unlocked else 'unlocked' if unlocked else 'next expansion' if next_bed else 'locked'}"
            )
            beds.add_tile(cell)
        layout.addWidget(beds)
        next_index = unlocked_count
        price = self.engine.BED_PRICES.get(next_index)
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        title = QLabel(
            "Maximum garden capacity reached"
            if price is None else
            f"Unlock Bed {next_index + 1}"
        )
        title.setProperty("nurseryPlantName", True)
        title.setWordWrap(True)
        details = QLabel("All six beds are available." if price is None else "")
        details.setProperty("nurseryMeta", True)
        details.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(details)
        details.setVisible(bool(details.text()))
        if price is not None:
            price_label = QLabel(cost_label(price))
            price_label.setProperty("nurseryMeta", True)
            copy.addWidget(price_label)
        if price is not None:
            affordable = int(state.currency_balance) >= int(price)
            self.bed_button = QPushButton("Unlock")
            _set_button_variant(
                self.bed_button,
                BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
            )
            self.bed_button.setAccessibleDescription(
                f"{cost_label(price)}. Unlocks bed {next_index + 1}. "
                + (
                    "Affordable with the current Garden Coin balance."
                    if affordable else
                    f"Need {price - int(state.currency_balance):,} more Garden Coins."
                )
            )
            self.bed_button.setAccessibleName(
                f"Unlock Garden Bed {next_index + 1} for {price:,} Garden Coins"
            )
            set_control_enabled(
                self.bed_button,
                affordable and not self._bed_purchase_pending,
                disabled_reason=(
                    "Please wait while the garden bed is unlocked."
                    if self._bed_purchase_pending
                    else f"Need {price - int(state.currency_balance):,} more Garden Coins."
                ),
                enabled_description=self.bed_button.accessibleDescription(),
            )
            self.bed_button.clicked.connect(self._unlock_bed)
            if not affordable:
                shortfall = QLabel(
                    f"{int(price) - int(state.currency_balance):,} more needed"
                )
                shortfall.setProperty("nurseryShortfall", True)
                shortfall.setWordWrap(True)
                copy.addWidget(shortfall)
            expansion = ResponsiveActionCard(
                copy_widget,
                self.bed_button,
                semantic_id="nursery.garden-space-expansion",
                summary_floor=205,
                action_floor=96,
                spacing=12,
                margins=(14, 12, 14, 12),
            )
            expansion.setProperty("sectionCard", True)
            self._catalog_responsive_controllers.append(expansion.responsive)
        else:
            expansion = SectionCard()
            expansion_layout = QVBoxLayout(expansion)
            expansion_layout.setContentsMargins(14, 12, 14, 12)
            expansion_layout.addWidget(copy_widget)
        layout.addWidget(expansion)
        layout.addStretch(1)
        return host

    def _purchase_fertilizer(self, tier: str) -> None:
        if not self._begin_catalog_transaction():
            return
        try:
            plant = self.engine.active_plant()
            if plant is None:
                self._show_result(False, "Choose an unfinished planted plant to nurture first.")
                return
            self._execute_purchase(
                PurchaseKind.FERTILIZER,
                tier,
                target_id=plant.plant_id,
            )
        except Exception:
            self._show_catalog_transaction_exception(
                "Fertilizer purchase", committed=False
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _use_booster(self) -> None:
        if not self._begin_catalog_transaction():
            return
        committed = False
        try:
            ok, message = self.engine.use_booster_potion()
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "Booster use", committed=committed
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _use_basic_fertilizer(self) -> None:
        if not self._begin_catalog_transaction():
            return
        compost_name = next(
            item.name
            for item in collectible_registry()
            if item.item_id == "growth_items:fertilizer_basic"
        )
        committed = False
        try:
            plant = self.engine.active_plant()
            if plant is None:
                self._show_result(
                    False,
                    "Choose an unfinished planted plant to nurture first.",
                )
                return
            now = (
                self.engine._now_seconds()
                if callable(getattr(self.engine, "_now_seconds", None))
                else time.time()
            )
            current = fertilizer_status(self.engine, plant, now=now)
            basic = self.engine.FERTILIZERS["basic"]
            replacing = bool(
                current.active
                and str(getattr(plant.fertilizer, "tier", "")) != basic.tier
            )
            if replacing and not ConfirmationDialog.confirm(
                self,
                f"Replace {current.name}?",
                (
                    f"{basic.name} starts now. You will lose "
                    f"{self.engine._duration_label(current.seconds_remaining).lower()} "
                    f"of {current.name}."
                ),
                confirm_label=f"Use {basic.name.removesuffix(' Fertilizer')}",
            ):
                return
            ok, message = self.engine.use_fertilizer_item(
                plant.plant_id,
                replace_active=replacing,
            )
            committed = bool(ok)
            if not ok:
                message = f"{_learner_text(message)} {compost_name} was not used."
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                f"{compost_name} use", committed=committed
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _purchase_growth_charge(self, charge_id: str) -> None:
        if not self._begin_catalog_transaction():
            return
        try:
            self._execute_purchase(PurchaseKind.GROWTH_CHARGE, charge_id)
        except Exception:
            self._show_catalog_transaction_exception(
                "Growth Charge purchase", committed=False
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _use_growth_charge(self, charge_id: str) -> None:
        if not self._begin_catalog_transaction():
            return
        committed = False
        try:
            ok, message = self.engine.use_growth_charge(charge_id)
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "Growth Charge use", committed=committed
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _purchase_environment(self, kind: str, item_id: str) -> None:
        if not self._begin_catalog_transaction():
            return
        outcome: PurchaseOutcome | None = None
        try:
            catalog = WEATHER_CATALOG if str(kind) == "weather" else SCENERY_CATALOG
            product = catalog.get(str(item_id))
            if product is None:
                self._show_result(False, "That Nursery product is no longer available.")
                return
            outcome = self._execute_purchase(PurchaseKind(str(kind)), item_id)
            if outcome is not None:
                # Refresh rebuilds the catalog, so explicitly restore the receipt's
                # product instead of reverting the feature panel to its first item.
                self._preview_environment_item(product)
        except Exception:
            self._show_catalog_transaction_exception(
                "Weather or Scenery purchase", committed=outcome is not None
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _execute_purchase(
        self,
        kind: PurchaseKind,
        item_id: str,
        *,
        target_id: str | None = None,
    ) -> PurchaseOutcome | None:
        """Quote, confirm, commit, and publish one canonical purchase result."""

        quote = self.engine.quote_purchase(kind, item_id, target_id=target_id)
        dialog_type = (
            FertilizerReplacementDialog
            if quote.replacement_required else
            PurchaseConfirmationDialog
        )
        dialog = dialog_type(self, self.engine, quote)
        self.purchase_dialog = dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._handle_purchase_dialog_route(dialog.requested_route)
            return None
        outcome = dialog.outcome
        if outcome is None or not outcome.success:
            return None
        if outcome.disposition is PurchaseDisposition.UNLOCKED:
            try:
                self._recently_unlocked_bed = int(outcome.result_id)
            except (TypeError, ValueError):
                self._recently_unlocked_bed = None
        try:
            self._refresh_parent()
            self.refresh()
            self._show_purchase_receipt(outcome, dialog.presentation)
        except Exception:
            self._show_catalog_transaction_exception(
                f"{outcome.category} purchase",
                committed=True,
            )
        return outcome

    def _handle_purchase_dialog_route(self, route: str) -> None:
        """Honor one explicit terminal-state route after the modal closes."""

        selected = str(route or "")
        if not selected or selected == "nursery":
            if selected == "nursery":
                QTimer.singleShot(0, self.catalog_tabs.setFocus)
            return
        if selected == "customize":
            self._open_customize_from_nursery()
            return
        parent = self.parentWidget()
        if selected == "garden":
            self.accept()
            scene = getattr(parent, "scene", None)
            if scene is not None:
                QTimer.singleShot(0, scene.setFocus)
            return
        progress = getattr(parent, "progress_dialog", None)
        opener = getattr(progress, "open_page", None)
        page = "currency" if selected == "ways_to_earn" else "collection"
        if callable(opener):
            self.accept()
            QTimer.singleShot(0, lambda: opener(page))

    def _begin_catalog_transaction(self) -> bool:
        if self._catalog_transaction_pending:
            return False
        self._catalog_transaction_pending = True
        return True

    def _schedule_catalog_transaction_release(self) -> None:
        try:
            QTimer.singleShot(350, self._release_catalog_transaction)
        except Exception:
            logger.exception("Anki Garden: Nursery transaction release could not be scheduled")
            self._release_catalog_transaction()

    def _release_catalog_transaction(self) -> None:
        self._catalog_transaction_pending = False

    def _show_catalog_transaction_exception(
        self,
        context: str,
        *,
        committed: bool,
    ) -> None:
        logger.exception(
            "Anki Garden: Nursery %s failed unexpectedly%s",
            context,
            " after the change was saved" if committed else "",
        )
        message = (
            "Your change was saved, but the Nursery display could not refresh. "
            "Close and reopen the Nursery to continue."
            if committed else
            "The Nursery could not confirm that change. Close and reopen the Nursery "
            "before trying again."
        )
        try:
            self._show_result(False, message)
            if committed:
                self.status.setProperty(
                    "transactionPresentation",
                    "committed-result-with-refresh-failure",
                )
        except Exception:
            logger.exception("Anki Garden: Nursery transaction failure could not be displayed")

    def _dismiss_product_receipt(self) -> None:
        self._status_generation += 1
        self._receipt_outcome = None
        self.nursery_toast.clear()
        self.status.hide()
        self.catalog_tabs.setFocus()

    def _show_purchase_receipt(
        self,
        outcome: PurchaseOutcome,
        presentation: PurchasePresentation | None = None,
    ) -> None:
        del presentation
        self._status_generation += 1
        self._receipt_outcome = outcome
        item_name = str(outcome.item_name or "Garden item")
        if outcome.disposition is PurchaseDisposition.COLLECTION:
            species_name = (
                item_name[:-5]
                if item_name.casefold().endswith(" seed") else
                item_name
            )
            message = f"{species_name} added."
            primary = "Plant now"
            secondary = "View collection"
            secondary_callback = self._open_customize_from_nursery
        elif outcome.disposition is PurchaseDisposition.INVENTORY:
            message = f"{item_name} added."
            primary = "Use charge"
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        elif outcome.disposition is PurchaseDisposition.OWNED_NOT_EQUIPPED:
            message = (
                f"{item_name} equipped."
                if bool(outcome.equipped) else
                f"{item_name} added to your collection."
            )
            primary = "View in Collection"
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        elif outcome.disposition in {
            PurchaseDisposition.APPLIED,
            PurchaseDisposition.REPLACED,
        }:
            message = f"{item_name} applied."
            primary = "View plant"
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        elif outcome.disposition is PurchaseDisposition.EXTENDED:
            message = f"{item_name} extended."
            primary = "View plant"
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        elif outcome.disposition is PurchaseDisposition.UNLOCKED:
            bed_name = item_name.replace("Garden bed", "Bed").replace(
                "Garden Bed", "Bed"
            )
            message = f"{bed_name} unlocked."
            primary = "View garden"
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        else:
            message = _learner_text(outcome.message)
            primary = outcome.next_actions[0] if outcome.next_actions else ""
            secondary = "Keep browsing"
            secondary_callback = self._dismiss_product_receipt
        if message and message[-1] not in ".?!":
            message += "."
        callback = (
            self._follow_receipt_action
            if primary
            else None
        )
        self.status.hide()
        _set_button_variant(self.nursery_toast.action, BUTTON_VARIANT_PRIMARY)
        self.nursery_toast.show_message(
            message,
            action_text=primary if callback is not None else "",
            callback=callback,
            duration_ms=6000,
            dismissible=True,
            dismiss_text=secondary,
            dismiss_callback=secondary_callback,
        )
        QTimer.singleShot(0, lambda: self._focus_purchase_result(outcome))

    def _focus_purchase_result(self, outcome: PurchaseOutcome) -> None:
        identifiers = {
            str(outcome.item_id or ""),
            str(outcome.result_id or ""),
        }
        identifiers.discard("")
        for widget in self.catalog_tabs.findChildren(QWidget):
            widget_ids = {
                str(widget.property("catalogItemId") or ""),
                str(widget.property("catalogSpeciesId") or ""),
            }
            if not identifiers.intersection(widget_ids):
                continue
            if isinstance(widget, QPushButton) and widget.isEnabled():
                widget.setFocus()
                return
            for action in widget.findChildren(QPushButton):
                if action.isEnabled():
                    action.setFocus()
                    return
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            set_keyboard_focus_surface(widget)
            widget.setFocus()
            return
        item_name = str(outcome.item_name or "").casefold()
        for action in self.catalog_tabs.findChildren(QPushButton):
            if item_name and item_name in action.accessibleName().casefold():
                action.setFocus()
                return
        self.catalog_tabs.setFocus()

    def _show_product_receipt(self, product: CatalogItem, message: str) -> None:
        """Compatibility adapter for older fixture callers."""

        self._show_purchase_receipt(PurchaseOutcome(
            status=PurchaseStatus.SUCCESS,
            item_id=product.item_id,
            item_name=product.name,
            category=format_status_label(product.kind),
            quantity=1,
            amount_spent=max(0, int(product.price or 0)),
            new_balance=max(0, int(self.storage.state.currency_balance)),
            disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
            message=_learner_text(message),
            next_actions=("View in Collection", "Keep browsing"),
        ))

    def _follow_receipt_action(self) -> None:
        outcome = self._receipt_outcome
        if outcome is None:
            return
        parent = self.parentWidget()
        if outcome.disposition is PurchaseDisposition.COLLECTION and outcome.result_id:
            self._set_placement(outcome.result_id, False)
            return
        if outcome.disposition is PurchaseDisposition.INVENTORY:
            self.accept()
            progress = getattr(parent, "progress_dialog", None)
            opener = getattr(progress, "open_growth_charges", None)
            if callable(opener):
                QTimer.singleShot(0, opener)
            return
        if outcome.disposition is PurchaseDisposition.OWNED_NOT_EQUIPPED:
            self._open_customize_from_nursery()
            return
        if outcome.disposition in {
            PurchaseDisposition.APPLIED,
            PurchaseDisposition.EXTENDED,
            PurchaseDisposition.REPLACED,
        } and outcome.result_id:
            self._view_in_garden(outcome.result_id)
            return
        self.accept()

    def _sync_catalog_intro(self, index: int) -> None:
        if bool(getattr(self, "_starter_mode", False)):
            self.heading.setText(NURSERY_STARTER_TITLE)
            text = NURSERY_STARTER_RATIONALE
        else:
            self.heading.setText({
                0: "Build your collection",
                1: "Boost plant growth",
                2: "Expand your garden",
                3: "Weather and Scenery",
            }.get(int(index), "Nursery"))
            text = {
                0: (
                    ""
                    if bool(getattr(self, "_no_new_plants", False))
                    else getattr(self, "_catalog_summary", "")
                ),
                1: "",
                2: "",
                3: "",
            }.get(int(index), getattr(self, "_catalog_summary", ""))
        self.intro.setText(text)
        self.intro.setAccessibleDescription(text)
        view_key = "starter" if bool(getattr(self, "_starter_mode", False)) else {
            0: "empty" if bool(getattr(self, "_no_new_plants", False)) else "plants",
            1: "fertilizer",
            2: "spaces",
            3: "weather",
        }.get(int(index), "plants")
        self.apply_view_size_profile(view_key)

    def refresh(self) -> None:
        self._clear_catalog()
        self._clear_section(self.supplements_layout)
        self._clear_section(self.upgrades_layout)
        self._clear_section(self.environment_layout)
        self._catalog_responsive_controllers: list[AdaptiveSplit] = []
        self.catalog_content_responsive: tuple[AdaptiveSplit, ...] = ()
        state = self.storage.state
        starter_mode = not bool(getattr(state, "starter_selection_complete", True))
        for index in (1, 2, 3):
            self.catalog_tabs.setTabEnabled(index, not starter_mode)
            self.catalog_tabs.tabBar().setTabVisible(index, not starter_mode)
        self.catalog_tabs.tabBar().setVisible(not starter_mode)
        self.starter_tab_note.hide()
        self.coin_resource.setVisible(not starter_mode)
        self.nursery_footer.setVisible(starter_mode)
        self.close_button.setText("Later" if starter_mode else "Close")
        _set_button_variant(
            self.close_button,
            BUTTON_VARIANT_TERTIARY if starter_mode else BUTTON_VARIANT_SECONDARY,
        )
        self.close_button.setAccessibleDescription(
            "Close the Nursery and resume starter setup later."
            if starter_mode else
            "Close the Nursery."
        )
        self.catalog_tabs.setAccessibleDescription(
            DISABLED_STARTER_TABS if starter_mode else "All Nursery sections are available."
        )
        if starter_mode:
            self.catalog_tabs.setCurrentIndex(0)
        summary = self.engine.catalog_summary()
        available = list(summary.get("available_species", []))
        if starter_mode:
            available = available[:4]
        owned_count = int(summary.get("owned_count", len(state.plants)))
        available_count = int(summary.get("available_count", len(available)))
        release_ready_count = len(summary.get("release_ready_species", []))
        self._collection_complete = bool(
            not starter_mode
            and release_ready_count > 0
            and available_count == 0
            and owned_count >= release_ready_count
        )
        self._no_new_plants = bool(not starter_mode and available_count == 0)
        catalog_summary = (
            f"{owned_count:,} of "
            f"{max(owned_count, owned_count + available_count):,} collected"
        )
        self.coins.setText(f"{state.currency_balance:,}")
        self.coins.setAccessibleDescription(
            f"{state.currency_balance:,} Garden Coins available"
        )
        self.heading.setText(
            NURSERY_STARTER_TITLE
            if starter_mode
            else "Build your collection"
        )
        intro_text = (
            NURSERY_STARTER_RATIONALE
            if starter_mode else
            "" if self._no_new_plants else
            catalog_summary
        )
        self.intro.setText(intro_text)
        self.intro.setAccessibleDescription(intro_text)
        self.starter_count.setVisible(
            starter_mode and bool(NURSERY_STARTER_COUNT)
        )
        self.starter_count.setText(NURSERY_STARTER_COUNT)
        self.starter_count.setAccessibleDescription(NURSERY_STARTER_COUNT)
        self._starter_mode = starter_mode
        self._catalog_summary = catalog_summary
        self._sync_catalog_intro(self.catalog_tabs.currentIndex())
        active = self.engine.active_plant()
        self.currently_growing_strip: ResponsiveActionCard | None = None
        if active is not None and not starter_mode and not self._no_new_plants:
            self.currently_growing_strip = self._currently_growing_strip(active)
            self.catalog_layout.addWidget(self.currently_growing_strip)
        collection_plants = [
            plant for plant in state.plants
            if active is None or plant.plant_id != active.plant_id
        ]
        if collection_plants and not starter_mode and not self._no_new_plants:
            self._section_label("Your plants")
            for plant in sorted(collection_plants, key=lambda item: (item.slot_index is None, item.name.lower())):
                self.catalog_layout.addWidget(self._owned_card(plant))
        if available:
            available_grid_host = ResponsiveTileGrid(
                breakpoint=600,
                minimum_tile_width=270,
                maximum_columns=(
                    2
                    if starter_mode
                    else min(3, max(1, len(available)))
                ),
            )
            for species in available:
                available_grid_host.add_tile(
                    self._available_card(species, starter_mode)
                )
            self.catalog_layout.addWidget(available_grid_host)
        else:
            view_collection = QPushButton("View collection")
            _set_button_variant(view_collection, BUTTON_VARIANT_PRIMARY)
            view_collection.clicked.connect(self._open_customize_from_nursery)
            empty = EmptyState(
                "New plants are being prepared"
                if starter_mode else "All plants collected",
                "The Nursery is stocking new plants. More will appear when their complete artwork is ready."
                if starter_mode else
                f"{owned_count:,} of {max(owned_count, release_ready_count):,}",
                action=None if starter_mode else view_collection,
            )
            self.catalog_layout.addWidget(empty)
        self.catalog_layout.addStretch(1)
        if not starter_mode:
            active_plant = self.engine.active_plant()
            active_status = (
                fertilizer_status(
                    self.engine,
                    active_plant,
                    now=time.time(),
                    description=FERTILIZER_EXPLANATION,
                )
                if active_plant is not None else None
            )
            if active_status is not None and active_status.active:
                active_heading = QLabel("Active fertilizer")
                active_heading.setProperty("nurserySection", True)
                self.supplements_layout.addWidget(active_heading)
                active_block = FertilizerStatusBlock(allow_description=False)
                active_block.set_status(active_status)
                self.supplements_layout.addWidget(active_block)
            stored_fertilizer_count = max(0, int(
                state.consumables.get("fertilizer_basic", 0) or 0
            ))
            if stored_fertilizer_count:
                stored_heading = QLabel("Stored")
                stored_heading.setProperty("nurserySection", True)
                self.supplements_layout.addWidget(stored_heading)
                self.supplements_layout.addWidget(
                    self._basic_fertilizer_inventory_card()
                )
            fertilizer_heading = QLabel("Available")
            fertilizer_heading.setProperty("nurserySection", True)
            self.supplements_layout.addWidget(fertilizer_heading)
            for tier in ("basic", "quality", "premium"):
                self.supplements_layout.addWidget(self._supplement_card(tier))
            booster_heading = QLabel("Boosters")
            booster_heading.setProperty("nurserySection", True)
            self.supplements_layout.addWidget(booster_heading)
            self.supplements_layout.addWidget(self._booster_card())
            charge_heading = QLabel("Growth Charges")
            charge_heading.setProperty("nurserySection", True)
            self.supplements_layout.addWidget(charge_heading)
            for spec in GROWTH_CHARGES.values():
                self.supplements_layout.addWidget(self._growth_charge_card(spec))
            self.supplements_layout.addStretch(1)

            self.upgrades_layout.addWidget(self._space_progression())

            self.environment_feature_art = QLabel()
            self.environment_feature_art.setMinimumSize(180, 101)
            self.environment_feature_art.setMaximumSize(220, 124)
            self.environment_feature_art.resize(220, 124)
            self.environment_feature_art.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
            self.environment_feature_art.setScaledContents(True)
            self.environment_feature_art.setProperty("nurseryArtwork", True)
            self.environment_feature_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.environment_feature_art.setPixmap(
                _environment_placeholder_pixmap(220, 124)
            )
            self.environment_feature_art.setAccessibleName(
                "Weather or Scenery preview"
            )
            feature_copy_widget = QWidget()
            feature_copy = QVBoxLayout(feature_copy_widget)
            feature_copy.setContentsMargins(0, 0, 0, 0)
            self.environment_feature_title = QLabel("Preview")
            self.environment_feature_title.setProperty("nurseryPlantName", True)
            self.environment_feature_title.setWordWrap(True)
            self.environment_feature_meta = QLabel("")
            self.environment_feature_meta.setProperty("nurseryMeta", True)
            self.environment_feature_meta.setWordWrap(True)
            feature_copy.addWidget(self.environment_feature_title)
            feature_copy.addWidget(self.environment_feature_meta)
            feature_copy.addStretch(1)
            feature = ResponsiveActionCard(
                self.environment_feature_art,
                feature_copy_widget,
                semantic_id="nursery.environment-feature",
                summary_floor=220,
                action_floor=180,
                spacing=12,
                margins=(12, 11, 12, 11),
            )
            feature.setProperty("nurseryPlant", True)
            feature.setProperty("nurseryCatalogCard", True)
            self._catalog_responsive_controllers.append(feature.responsive)
            self.environment_layout.addWidget(feature)
            equipped_item = (
                WEATHER_CATALOG.get(str(state.selected_weather))
                or SCENERY_CATALOG.get(str(state.selected_background))
            )
            if equipped_item is not None:
                self._preview_environment_item(equipped_item)
            for heading, catalog in (
                ("Weather", WEATHER_CATALOG),
                ("Scenery", SCENERY_CATALOG),
            ):
                label = QLabel(heading)
                label.setProperty("nurserySection", True)
                self.environment_layout.addWidget(label)
                grid = ResponsiveTileGrid(
                    breakpoint=520,
                    minimum_tile_width=240,
                    maximum_columns=3,
                )
                first_item: CatalogItem | None = None
                for item in catalog.values():
                    if item.acquisition in {"free", "purchase"}:
                        first_item = first_item or item
                        grid.add_tile(self._environment_shop_card(item))
                self.environment_layout.addWidget(grid)
                if self.environment_feature_title.text() == "Preview" and first_item is not None:
                    self._preview_environment_item(first_item)
            self.environment_layout.addStretch(1)
        self.catalog_content_responsive = tuple(
            self._catalog_responsive_controllers
        )

    def _show_result(self, ok: bool, message: str) -> None:
        # Nursery feedback is one overlay lane. Replace any purchase receipt
        # before showing a direct-action result so the two surfaces can never
        # cover one another at the shared catalog anchor.
        self.nursery_toast.clear()
        self._status_generation += 1
        generation = self._status_generation
        message = _learner_text(message)
        self.status.setText(message)
        lower_message = message.casefold()
        persistence_failure = bool(
            not ok
            and (
                "could not be saved" in lower_message
                or "was not saved" in lower_message
            )
        )
        tone = (
            FeedbackTone.SUCCESS
            if ok
            else FeedbackTone.INFO
            if "already" in lower_message
            else FeedbackTone.ERROR
            if any(
                marker in lower_message
                for marker in ("could not", "failed", "reopen the nursery")
            )
            else FeedbackTone.WARNING
        )
        style = {
            FeedbackTone.SUCCESS: "color:#baf3c6; background:#1d4931; border:1px solid #3c7653;",
            FeedbackTone.INFO: "color:#d8eee5; background:#17352c; border:1px solid #416b5d;",
            FeedbackTone.WARNING: "color:#f4e5aa; background:#3b3420; border:1px solid #7d6f3d;",
            FeedbackTone.ERROR: "color:#ffd0d0; background:#582f34; border:1px solid #92515a;",
        }[tone]
        self.status.setStyleSheet(
            style + " padding:7px 9px; border-radius:7px;"
        )
        set_semantic_role(self.status, SemanticRole.BANNER, tone=tone)
        self.status.setProperty(
            "transactionState",
            "success"
            if ok
            else "persistence-failure"
            if persistence_failure
            else "recoverable-failure"
            if tone is FeedbackTone.ERROR
            else "business-rule-blocked",
        )
        self.status.setProperty(
            "transactionPresentation",
            "committed-result"
            if ok
            else "committed-state-unchanged"
            if persistence_failure
            else "attempt-result",
        )
        self.status.setAccessibleDescription(message)
        self.status.show()
        position_overlays = getattr(self, "_position_nursery_overlays", None)
        if callable(position_overlays):
            position_overlays()
        announcer = getattr(self, "accessibility_announcer", None)
        if announcer is not None:
            announcer.announce(
                message,
                priority=(
                    AnnouncementPriority.ASSERTIVE
                    if tone is FeedbackTone.ERROR
                    else AnnouncementPriority.POLITE
                ),
                target=self.status,
            )
        if ok:
            QTimer.singleShot(
                3500,
                lambda: self._hide_status_if_current(generation),
            )
        else:
            self.status.setFocus()

    def _hide_status_if_current(self, generation: int) -> None:
        if int(generation) == self._status_generation:
            self.status.hide()

    def _refresh_parent(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        refresh_committed = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh_committed):
            refresh_committed("Nursery change")
            return
        try:
            if hasattr(parent, "refresh_all"):
                parent.refresh_all()
            refresh_external = getattr(parent, "refresh_external_surfaces", None)
            if callable(refresh_external):
                refresh_external()
        except Exception:
            logger.exception("Anki Garden: Nursery change was saved but its parent did not refresh")

    def _choose_starter(self, species: str) -> None:
        if self._starter_choice_pending:
            return
        self._starter_choice_pending = True
        try:
            ok, message = self.engine.select_starter_species(species)
            if not ok:
                if "could not be saved" in str(message).casefold():
                    message = "Couldn’t save your garden. Nothing was changed."
                self._show_result(False, message)
                return
            self._show_result(True, message)
            self._refresh_parent()
            self.accept()
        except Exception:
            logger.exception("Anki Garden: starter choice save failed unexpectedly")
            self._show_result(
                False,
                "Couldn’t save your garden. Nothing was changed.",
            )
        finally:
            QTimer.singleShot(
                350,
                lambda: setattr(self, "_starter_choice_pending", False),
            )

    def _close_nursery(self) -> None:
        if bool(getattr(self, "_starter_mode", False)):
            self.reject()
        else:
            self.accept()

    def _purchase_species(self, species: str) -> None:
        if not self._begin_catalog_transaction():
            return
        try:
            self._execute_purchase(PurchaseKind.SPECIES, species)
        except Exception:
            self._show_catalog_transaction_exception(
                "plant purchase", committed=False
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _unlock_bed(self) -> None:
        if self._bed_purchase_pending or not self._begin_catalog_transaction():
            return
        self._bed_purchase_pending = True
        try:
            is_enabled = getattr(self.bed_button, "isEnabled", None)
            self._bed_button_restore_enabled = (
                bool(is_enabled()) if callable(is_enabled) else True
            )
            set_control_enabled(
                self.bed_button,
                False,
                disabled_reason="Please wait while the garden bed is unlocked.",
            )
            self._execute_purchase(PurchaseKind.BED, "next")
        except Exception:
            self._show_catalog_transaction_exception(
                "garden-space purchase", committed=False
            )
        finally:
            # Retain the guard through the platform's complete double-click event
            # sequence. A later deliberate activation may buy the next space.
            try:
                QTimer.singleShot(350, self._release_bed_purchase)
            except Exception:
                logger.exception("Anki Garden: garden-space release could not be scheduled")
                self._release_bed_purchase()

    def _release_bed_purchase(self) -> None:
        self._bed_purchase_pending = False
        self._release_catalog_transaction()
        try:
            starter_mode = not bool(
                getattr(self.storage.state, "starter_selection_complete", True)
            )
            bed_price = self.engine.next_bed_price()
            bed_affordable = (
                bed_price is not None
                and int(self.storage.state.currency_balance) >= int(bed_price)
            )
        except Exception:
            logger.exception("Anki Garden: garden-space button state could not be recalculated")
            try:
                restore_enabled = bool(
                    getattr(self, "_bed_button_restore_enabled", False)
                )
                set_control_enabled(
                    self.bed_button,
                    restore_enabled,
                    disabled_reason=(
                        "This garden bed is unavailable until the Nursery updates."
                    ),
                )
            except RuntimeError:
                pass
            return
        try:
            enabled = bool(
                not starter_mode
                and bed_price is not None
                and self.bed_button.isVisible()
                and bed_affordable
            )
            set_control_enabled(
                self.bed_button,
                enabled,
                disabled_reason=(
                    "Complete starter selection before expanding the Garden."
                    if starter_mode
                    else "No additional garden bed is currently affordable."
                ),
                enabled_description="Unlock the next garden bed.",
            )
        except RuntimeError:
            return

    def _set_placement(self, plant_id: str, planted: bool) -> None:
        if self._placement_transaction_pending:
            return
        self._placement_transaction_pending = True
        QTimer.singleShot(
            350,
            lambda: setattr(self, "_placement_transaction_pending", False),
        )
        try:
            plant = self.engine.plant_story(str(plant_id))
        except Exception:
            logger.exception("Anki Garden: Nursery plant lookup failed")
            plant = None
        plant_name = str(getattr(plant, "name", "This plant"))
        bed_number = max(
            1,
            int(getattr(plant, "slot_index", 0) or 0) + 1,
        )
        try:
            if planted:
                ok, message = self.engine.move_to_collection(plant_id)
            else:
                ok, message = self.engine.plant_from_collection(plant_id)
        except Exception:
            logger.exception("Anki Garden: Nursery plant storage change failed")
            ok = False
            message = "The plant storage change could not be saved."
        if ok and planted:
            message = (
                f"{plant_name} stored in Collection and remains owned with its "
                f"Growth, memories, and Fertilizer. Garden Bed {bed_number} is now empty."
            )
        elif not ok and "could not be saved" in str(message).casefold():
            message = (
                f"Storing the plant could not be saved. {plant_name} remains "
                f"in Garden Bed {bed_number}; ownership, Growth, memories, "
                "Fertilizer, and the occupied bed are unchanged."
                if planted else
                f"Planting could not be saved. {plant_name} remains stored in "
                "Collection; ownership, Growth, memories, Fertilizer, and every "
                "garden bed remain unchanged."
            )
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()


class PlantInfoCard(QFrame):
    """Native, keyboard-accessible plant details anchored over the scene."""

    dismissRequested = pyqtSignal()
    chooseAnother = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("plantCard", True)
        self.setAccessibleName("Selected plant details")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self)
        self.setMinimumWidth(280)
        self.setMaximumWidth(300)
        self.plant_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        self.artwork = QLabel("")
        self.artwork.setFixedSize(52, 52)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setProperty("plantPopoverArtwork", True)
        self.artwork.setAccessibleName("Selected plant artwork")
        self.heading = QLabel("")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setProperty("plantCardHeading", True)
        self.heading.setWordWrap(True)
        self.identity = QLabel("")
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.identity.setProperty("plantStageBadge", True)
        self.identity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.identity.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.nurtured_badge = NurturedPlantBadge()
        self.nurtured_badge.hide()
        self.fertilized_badge = QLabel("Fertilized")
        self.fertilized_badge.setProperty("fertilizedBadge", True)
        self.fertilized_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fertilized_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.fertilized_badge.hide()
        self.fully_grown_badge = QLabel("Fully grown")
        self.fully_grown_badge.setProperty("fullyGrownBadge", True)
        self.fully_grown_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fully_grown_badge.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.fully_grown_badge.hide()
        self.growth_section = QLabel("")
        self.growth_section.setProperty("plantCardSection", True)
        self.stage_progress = LabeledProgress("Selected plant growth")
        self.stage_progress.label.setProperty("plantProgressLabel", True)
        self.stage_progress.value_label.setProperty("plantGrowthValue", True)
        self.growth_summary = QLabel("")
        self.growth_remaining = QLabel("")
        # The selected-plant card owns a compact action panel. Keep the full
        # explanation in the block tooltip while reserving disclosure rows for
        # the roomier Story, Progress, and Fertilizer dialogs.
        self.fertilizer_summary = FertilizerStatusBlock(allow_description=False)
        self.booster_summary = QLabel("")
        for label in (
            self.growth_summary,
            self.growth_remaining,
            self.booster_summary,
        ):
            label.setWordWrap(True)
            label.setProperty("actionMeta", True)
            apply_tabular_numerals(label)
        self.status_row = QFrame()
        self.status_row.setProperty("plantStatus", True)
        status_layout = QHBoxLayout(self.status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        status_label = QLabel("")
        status_label.hide()
        status_label.setProperty("plantStatusLabel", True)
        self.status_value = QLabel("")
        self.status_value.setProperty("plantStatusValue", True)
        self.status_value.setWordWrap(True)
        apply_tabular_numerals(self.status_value)
        status_layout.addWidget(status_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.status_value)
        self.action_hint = QLabel("")
        self.action_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.action_hint.setWordWrap(True)
        self.action_hint.setProperty("actionHint", True)
        self.guidance = QFrame()
        self.guidance.setProperty("plantGuidance", True)
        guidance_layout = QVBoxLayout(self.guidance)
        guidance_layout.setContentsMargins(10, 8, 10, 8)
        guidance_layout.setSpacing(3)
        self.guidance_step = QLabel("")
        self.guidance_step.setProperty("plantGuidanceStep", True)
        self.guidance_text = QLabel(GARDEN_NURTURE_BODY)
        self.guidance_text.setWordWrap(True)
        self.guidance_text.setProperty("plantGuidanceText", True)
        guidance_layout.addWidget(self.guidance_step)
        guidance_layout.addWidget(self.guidance_text)
        self.guidance.hide()
        self.guidance_step.hide()
        heading_row = QHBoxLayout()
        heading_row.setSpacing(8)
        heading_row.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(4)
        heading_copy.addWidget(self.heading)
        heading_row.addLayout(heading_copy, 1)
        self.close_btn = GardenIconButton(
            "close", "Close selected plant details"
        )
        self.close_btn.clicked.connect(self.dismissRequested.emit)
        heading_row.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading_row)
        self.badge_container = QWidget()
        self.badge_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.badge_layout.setContentsMargins(0, 0, 0, 0)
        self.badge_layout.setSpacing(6)
        self.badge_container.setLayout(self.badge_layout)
        self.badge_layout.addWidget(self.identity)
        self.badge_layout.addWidget(self.nurtured_badge)
        self.badge_layout.addWidget(self.fertilized_badge)
        self.badge_layout.addWidget(self.fully_grown_badge)
        self.badge_layout.addStretch(1)
        self.badge_responsive = AdaptiveRow.for_box_layout(
            "plant-card.badges",
            (
                AdaptiveRegion.measured("stage", self.identity, floor=48),
                AdaptiveRegion.measured("nurtured", self.nurtured_badge, floor=116),
                AdaptiveRegion.measured("fertilized", self.fertilized_badge, floor=70),
            ),
            layout=self.badge_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=6,
            telemetry_target=self.badge_container,
        )
        layout.addWidget(self.badge_container)
        layout.addWidget(self.stage_progress)
        layout.addWidget(self.growth_summary)
        layout.addWidget(self.growth_remaining)
        layout.addWidget(self.fertilizer_summary)
        layout.addWidget(self.booster_summary)
        layout.addWidget(self.status_row)
        layout.addWidget(self.guidance)
        layout.addWidget(self.action_hint)
        self.action_hint.hide()

        self.nurture_section = QLabel("")
        self.nurture_section.setProperty("plantCardSection", True)
        layout.addWidget(self.nurture_section)
        self.nurture_section.hide()

        self.nurture = QPushButton("Nurture")
        self.nurture.setCheckable(True)
        self.fertilize = QPushButton("Fertilize")
        self.growth_charge = QPushButton("Use charge")
        self.move = QPushButton("Move")
        self.story = QPushButton("Plant Story")
        self.choose_another = QPushButton(FULLY_GROWN_ACTION)
        self.nurture.setProperty("plantActionRole", "primary")
        self.fertilize.setProperty("plantActionRole", "boost")
        self.growth_charge.setProperty("plantActionRole", "boost")
        self.move.setProperty("plantActionRole", "tertiary")
        self.story.setProperty("plantActionRole", "tertiary")
        self.choose_another.setProperty("plantActionRole", "primary")
        _set_button_variant(self.choose_another, BUTTON_VARIANT_PRIMARY)
        self.choose_another.setAccessibleDescription(FULLY_GROWN_MESSAGE)
        self.choose_another.clicked.connect(self.chooseAnother.emit)
        self.choose_another.hide()
        for button in (self.nurture, self.fertilize, self.growth_charge):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
        for button in (self.move, self.story):
            _set_button_variant(button, BUTTON_VARIANT_TERTIARY)
        for action in (
            self.nurture,
            self.fertilize,
            self.growth_charge,
            self.move,
            self.story,
        ):
            action.setToolTip("")
        self.actions = QGridLayout()
        self.actions.setHorizontalSpacing(8)
        self.actions.setVerticalSpacing(8)
        layout.addLayout(self.actions)
        self._active_state = False
        self._fully_grown_state = False
        self._docked_actions = False
        self._base_accessible_description = ""
        self._layout_actions(active=False)
        self.hide()

    def _layout_actions(
        self,
        *,
        active: bool,
        fully_grown: bool = False,
    ) -> None:
        self._active_state = bool(active)
        self._fully_grown_state = bool(fully_grown)
        for button in (
            self.nurture,
            self.fertilize,
            self.growth_charge,
            self.move,
            self.story,
            self.choose_another,
        ):
            self.actions.removeWidget(button)
        self.actions.setColumnStretch(0, 1)
        self.actions.setColumnStretch(1, 1)
        if fully_grown:
            self.actions.addWidget(self.choose_another, 0, 0, 1, 2)
            self.actions.addWidget(self.move, 1, 0)
            self.actions.addWidget(self.story, 1, 1)
            return
        if active:
            self.actions.addWidget(self.fertilize, 0, 0)
            self.actions.addWidget(self.growth_charge, 0, 1)
            secondary_row = 1
        else:
            self.actions.addWidget(self.nurture, 0, 0, 1, 2)
            secondary_row = 1
        self.actions.addWidget(self.move, secondary_row, 0)
        self.actions.addWidget(self.story, secondary_row, 1)
        self.actions.addWidget(self.choose_another, secondary_row + 1, 0, 1, 2)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "badge_responsive"):
            available = max(0, int(event.size().width()) - 32)
            self.badge_responsive.evaluate(available)
        super().resizeEvent(event)

    def set_docked_mode(self, docked: bool) -> None:
        docked = bool(docked)
        base_description = str(self._base_accessible_description or "")
        self.setAccessibleDescription(
            base_description
            + (
                " Displayed in a bottom sheet; Close returns focus to the selected plant."
                if docked else
                ""
            )
        )
        if docked == self._docked_actions:
            return
        self._docked_actions = docked
        self._layout_actions(
            active=self._active_state,
            fully_grown=self._fully_grown_state,
        )
        self.updateGeometry()

    def set_onboarding_guidance(self, visible: bool) -> None:
        self.guidance.setVisible(bool(visible))
        self.guidance.setAccessibleName("Step 2 of 2: Nurture your first plant")
        self.guidance.setAccessibleDescription(GARDEN_NURTURE_BODY)

    def set_selected(self, plant: dict[str, Any] | None) -> None:
        fully_grown_message = globals().get(
            "FULLY_GROWN_MESSAGE",
            "This plant is fully grown. Choose another unfinished plant to nurture.",
        )
        self.plant_id = str(plant.get("plant_id", "")) if isinstance(plant, dict) else ""
        if not self.plant_id or plant is None:
            self.hide()
            return
        name = str(plant.get("name") or plant.get("species") or "Plant")
        stage = format_status_label(plant.get("stage") or "seed")
        self.setAccessibleName(f"Selected plant details: {name}")
        self._base_accessible_description = (
            f"{name}, {stage}. Plant actions and Growth status."
        )
        self.setAccessibleDescription(self._base_accessible_description)
        self.heading.setText(name)
        self.heading.setToolTip(name)
        self.identity.setText(stage)
        asset = plant.get("asset")
        path = asset.get("path") if isinstance(asset, dict) else asset
        placement = asset.get("placement") if isinstance(asset, dict) else None
        pixmap = _normalized_plant_thumbnail(
            path,
            placement,
            stage=str(plant.get("stage") or "seed"),
            size=self.artwork.width(),
        )
        if pixmap.isNull():
            self.artwork.setText("")
            _record_missing_artwork(
                category="plant",
                item_key=str(plant.get("species") or self.plant_id or name),
                source_path=path,
            )
            self.artwork.setPixmap(
                _missing_artwork_pixmap(
                    "plant",
                    self.artwork.width(),
                    self.artwork.height(),
                )
            )
            set_semantic_role(self.artwork, SemanticRole.MISSING_ART)
            self.artwork.setAccessibleDescription(
                f"Artwork unavailable for {name}; a botanical fallback is shown."
            )
        else:
            self.artwork.setText("")
            self.artwork.setPixmap(pixmap)
            self.artwork.setAccessibleDescription(f"Artwork for {name}.")
        growth_points = max(0, int(plant.get("growth_points", 0) or 0))
        if bool(plant.get("fully_grown")):
            self.stage_progress.hide()
            self.identity.setText(f"{stage} · Fully grown")
            self.growth_summary.setText("")
            self.growth_summary.setAccessibleDescription(
                f"Fully grown with {growth_points:,} total Growth."
            )
            self.growth_summary.hide()
            self.growth_remaining.hide()
        else:
            self.stage_progress.show()
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            next_stage = format_status_label(plant.get("next_stage") or "the next stage")
            self.stage_progress.set_progress(
                "",
                stage_points,
                stage_goal,
                value_text=format_stage_progress(stage_points, stage_goal, next_stage),
            )
            self.stage_progress.label.hide()
            self.stage_progress.value_label.show()
            self.growth_summary.setText("")
            self.growth_summary.setToolTip("")
            self.growth_summary.setAccessibleDescription("")
            self.growth_summary.hide()
            self.growth_remaining.hide()
        fertilizer_projection = plant.get("fertilizer_status", {})
        self.fertilizer_summary.set_status(fertilizer_projection)
        fertilizer_active = bool(
            isinstance(fertilizer_projection, dict)
            and fertilizer_projection.get("phase") == "active"
        )
        booster_growth = max(0, int(plant.get("booster_growth", 0) or 0))
        booster_text = str(plant.get("booster_text") or "None active")
        self.booster_summary.setText(
            f"Booster Potion — {booster_text}" if booster_growth else "Booster Potion — None active"
        )
        self.booster_summary.setVisible(booster_growth > 0)
        active = bool(plant.get("is_active"))
        fully_grown = bool(plant.get("fully_grown"))
        self.nurture.setText("Nurture")
        self.nurture.setChecked(False)
        self.nurture.setProperty("selected", False)
        set_control_enabled(
            self.nurture,
            not fully_grown,
            disabled_reason="This plant is fully grown and cannot be nurtured again.",
            enabled_description="Choose this plant as the nurtured plant.",
        )
        self.nurture.setVisible(not active and not fully_grown)
        self.nurtured_badge.set_asset(plant.get("nurtured_badge_asset"))
        self.nurtured_badge.setVisible(active and not fully_grown)
        self.fully_grown_badge.hide()
        self.fertilized_badge.setVisible(fertilizer_active)
        if fertilizer_active and isinstance(fertilizer_projection, dict):
            self.fertilized_badge.setAccessibleName(
                str(fertilizer_projection.get("accessible_text") or "Fertilized")
            )
            self.fertilized_badge.setToolTip(
                str(fertilizer_projection.get("accessible_text") or "Fertilized")
            )
        set_control_enabled(
            self.fertilize,
            active and not fully_grown,
            disabled_reason=(
                "This plant is fully grown and cannot use Fertilizer."
                if fully_grown else "Nurture this plant before using Fertilizer."
            ),
            enabled_description="Choose Fertilizer for this plant.",
        )
        self.fertilize.setVisible(active and not fully_grown)
        self.fertilize.setText("Fertilize")
        set_control_enabled(
            self.growth_charge,
            active and not fully_grown,
            disabled_reason=(
                "This plant is fully grown and cannot use a Growth Charge."
                if fully_grown else "This plant cannot use a Growth Charge."
            ),
            enabled_description="Choose a stored Growth Charge for this planted plant.",
        )
        self.growth_charge.setVisible(active and not fully_grown)
        _set_button_variant(
            self.fertilize,
            BUTTON_VARIANT_SECONDARY,
        )
        _set_button_variant(
            self.nurture,
            BUTTON_VARIANT_PRIMARY if not active and not fully_grown else BUTTON_VARIANT_SECONDARY,
        )
        _set_button_variant(
            self.growth_charge,
            BUTTON_VARIANT_SECONDARY,
        )
        _set_button_variant(
            self.move,
            BUTTON_VARIANT_TERTIARY,
        )
        _set_button_variant(
            self.story,
            BUTTON_VARIANT_TERTIARY,
        )
        self._layout_actions(active=active, fully_grown=fully_grown)
        if fully_grown:
            action_hint = fully_grown_message
            nurture_reason = "Nurture is unavailable because this plant is fully grown."
            fertilizer_reason = "Fertilizer is unavailable because this plant is fully grown."
        elif active:
            action_hint = "This plant is already being nurtured."
            nurture_reason = "This plant is already being nurtured."
            fertilizer_reason = (
                "Choose a tier to replace or extend the active Fertilizer."
                if fertilizer_active else
                "Fertilizer is available for this nurtured plant."
            )
        else:
            action_hint = "Nurture this plant before using Fertilizer."
            nurture_reason = "Nurture is available for this unfinished plant."
            fertilizer_reason = "Nurture this plant before using Fertilizer."
        growth_today = max(0, int(plant.get("growth_today", 0) or 0))
        if fully_grown:
            status_text = ""
        elif fertilizer_active and isinstance(fertilizer_projection, dict):
            status_text = " · ".join(
                part for part in (
                    str(fertilizer_projection.get("name") or "Fertilizer active"),
                    str(fertilizer_projection.get("duration") or ""),
                ) if part
            )
        else:
            status_text = f"{growth_today:,} Growth today" if growth_today else ""
        self.status_value.setText(status_text)
        self.status_value.setAccessibleDescription(
            f"{growth_today:,} Growth today." if growth_today else ""
        )
        self.status_row.setVisible(bool(status_text))
        # The popover owns one concise status sentence. Full fertilizer and
        # booster mechanics remain in their dedicated dialogs.
        self.fertilizer_summary.hide()
        self.booster_summary.hide()
        self.action_hint.setText(action_hint if fully_grown else "")
        self.action_hint.setAccessibleDescription(action_hint if fully_grown else "")
        set_hint_visible = getattr(self.action_hint, "setVisible", None)
        if callable(set_hint_visible):
            set_hint_visible(False)
        self.nurture_section.hide()
        choose_another = getattr(self, "choose_another", None)
        set_choose_visible = getattr(choose_another, "setVisible", None)
        if callable(set_choose_visible):
            set_choose_visible(fully_grown)
        self.nurture.setAccessibleDescription(f"{ACTIVE_PLANT_EXPLANATION} {nurture_reason}")
        self.fertilize.setAccessibleDescription(f"{FERTILIZER_EXPLANATION} {fertilizer_reason}")
        self.show()


AnchoredPlantPopover = PlantInfoCard


class GardenOverlayManager(QObject):
    """Coordinates scene overlays so only one high-attention panel is expanded."""

    def __init__(
        self,
        onboarding: QWidget,
        plant_popover: QWidget,
        restore_onboarding: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.onboarding = onboarding
        self.plant_popover = plant_popover
        self.restore_onboarding = restore_onboarding

    def plant_selection_changed(self, selected: bool) -> None:
        if selected:
            self.onboarding.hide()
        else:
            self.plant_popover.hide()
            self.restore_onboarding()

    def move_mode_changed(self, active: bool) -> None:
        if active:
            self.plant_popover.hide()
            self.onboarding.hide()
        else:
            self.restore_onboarding()


class GardenStatsStrip(QFrame):
    """Plant-first progression surface with supporting study resources."""

    metricActivated = pyqtSignal(str)

    METRICS = (
        ("growth", "Plant Growth", GROWTH_EXPLANATION),
        ("streak", "Anki Streak", ANKI_STREAK_EXPLANATION),
        ("currency", "Garden Coins", GARDEN_CURRENCY_EXPLANATION),
    )
    CELL_HORIZONTAL_INSET = 32
    STREAK_HEADING_SPACING = 6
    BONUS_BADGE_HORIZONTAL_CHROME = 16

    def __init__(self, engine: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenStats", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Nurtured plant progression and garden resources")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.cells: dict[str, QPushButton] = {}
        self.values: dict[str, QLabel] = {}
        self.progress: dict[str, QProgressBar] = {}
        self.metric_copy: dict[str, tuple[str, str]] = {}
        for key, title, description in self.METRICS:
            cell = QPushButton()
            cell.setProperty("gardenStatCell", True)
            cell.setProperty("metric", key)
            cell.setProperty("separator", key != "currency")
            cell.setAccessibleName(f"{title} — {METRIC_AFFORDANCE}")
            cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setMinimumHeight(54)
            cell.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            cell.clicked.connect(
                lambda _checked=False, metric=key: self.metricActivated.emit(metric)
            )
            apply_explanatory_tooltip(cell, description)
            self.cells[key] = cell
            self.metric_copy[key] = (title, description)

        growth_layout = QVBoxLayout(self.cells["growth"])
        growth_layout.setContentsMargins(16, 5, 16, 5)
        growth_layout.setSpacing(2)
        self.growth_kicker = GardenBadge("")
        self.growth_kicker.hide()
        growth_heading = QHBoxLayout()
        growth_heading.setSpacing(8)
        growth_heading.addWidget(self.growth_kicker)
        growth_heading.addStretch(1)
        self.growth_stage = QLabel("")
        self.growth_stage.setProperty("gardenStageBadge", True)
        self.growth_stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.growth_stage.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        growth_heading.addWidget(self.growth_stage)
        growth_identity = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.growth_identity = growth_identity
        growth_identity.setSpacing(8)
        self.growth_name = ElidingLabel("Choose a plant")
        self.growth_name.setProperty("gardenPlantName", True)
        self.growth_name.setWordWrap(False)
        self.growth_name.setMinimumWidth(0)
        growth_identity.addWidget(self.growth_name, 1)
        self.growth_value = QLabel("0 / 0")
        self.growth_value.setProperty("gardenGrowthValue", True)
        self.growth_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        growth_identity.addWidget(self.growth_value, 0)
        growth_bar = QProgressBar()
        growth_bar.setRange(0, 1000)
        growth_bar.setValue(0)
        growth_bar.setTextVisible(False)
        growth_bar.setFixedHeight(4)
        growth_bar.setAccessibleName("Nurtured plant Growth")
        growth_bar.setProperty("metricProgress", True)
        self.growth_support = QLabel("")
        self.growth_support.setProperty("gardenStatSupport", True)
        self.growth_support.setWordWrap(True)
        self.growth_support.setMinimumWidth(0)
        self.growth_support.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        growth_layout.addLayout(growth_heading)
        growth_layout.addLayout(growth_identity)
        growth_bar.hide()
        # The bar must belong to the metric card before set_progress() shows it.
        # An unparented QProgressBar becomes a separate macOS window.
        growth_layout.addWidget(growth_bar)
        growth_layout.addWidget(self.growth_support)

        streak_layout = QVBoxLayout(self.cells["streak"])
        streak_layout.setContentsMargins(16, 5, 16, 5)
        streak_layout.setSpacing(2)
        self.streak_heading = QHBoxLayout()
        self.streak_heading.setSpacing(6)
        self.streak_label = QLabel("")
        self.streak_label.hide()
        self.streak_label.setProperty("gardenStatLabel", True)
        self.streak_label.setMinimumWidth(0)
        self.streak_label.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Preferred,
        )
        self.streak_bonus = QLabel("")
        self.streak_bonus.setProperty("gardenBonusBadge", True)
        self.streak_bonus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.streak_bonus.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        # Qt's styled size hint can undercount the leading plus glyph at high
        # scaling. Reserve the tier badge's full maximum-width compact form.
        self.streak_bonus.setMinimumWidth(48)
        self.streak_heading.addWidget(self.streak_label)
        self.streak_heading.addStretch(1)
        self.streak_heading.addWidget(self.streak_bonus)
        self.streak_value_row = QHBoxLayout()
        self.streak_value_row.setSpacing(5)
        self.streak_number = QLabel("0")
        self.streak_number.setProperty("gardenLargeValue", True)
        self.streak_unit = QLabel("")
        self.streak_unit.hide()
        self.streak_unit.setProperty("gardenValueUnit", True)
        self.streak_value_row.addWidget(
            self.streak_number,
            0,
            Qt.AlignmentFlag.AlignBottom,
        )
        self.streak_value_row.addWidget(
            self.streak_unit,
            0,
            Qt.AlignmentFlag.AlignBottom,
        )
        self.streak_value_row.addStretch(1)
        self.streak_support = QLabel("")
        self.streak_support.setProperty("gardenStatSupport", True)
        self.streak_support.setWordWrap(True)
        self.streak_support.setMinimumWidth(0)
        self.streak_support.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        streak_layout.addLayout(self.streak_heading)
        streak_layout.addLayout(self.streak_value_row)
        streak_layout.addWidget(self.streak_support)

        currency_layout = QVBoxLayout(self.cells["currency"])
        currency_layout.setContentsMargins(16, 5, 16, 5)
        currency_layout.setSpacing(2)
        self.currency_label = QLabel("")
        self.currency_label.setProperty("gardenStatLabel", True)
        self.currency_label.hide()
        self.currency_value = QLabel("0")
        self.currency_value.setProperty("gardenLargeValue", True)
        self.currency_support = QLabel("")
        self.currency_support.setProperty("gardenStatSupport", True)
        self.currency_support.setWordWrap(True)
        self.currency_support.setMinimumWidth(0)
        self.currency_support.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        currency_value_row = QHBoxLayout()
        currency_value_row.setSpacing(8)
        currency_value_row.addWidget(self.currency_value)
        currency_value_row.addStretch(1)
        currency_layout.addWidget(self.currency_label)
        currency_layout.addLayout(currency_value_row)
        currency_layout.addWidget(self.currency_support)

        self.values = {
            "growth": self.growth_value,
            "streak": self.streak_number,
            "currency": self.currency_value,
        }
        for value_label in self.values.values():
            apply_tabular_numerals(value_label)
        self.progress = {"growth": growth_bar}
        self._compact = False
        self._onboarding_mode = False
        self._streak_bonus_percent = 0
        self._growth_value_full_text = "0 / 0"
        self.growth_identity_responsive = AdaptiveRow.for_box_layout(
            "dashboard.growth-identity",
            (
                AdaptiveRegion(
                    "active-plant-name",
                    self._growth_name_content_width,
                    self.growth_name,
                ),
                AdaptiveRegion(
                    "stage-growth-value",
                    self._growth_value_content_width,
                    self.growth_value,
                ),
            ),
            layout=self.growth_identity,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.cells["growth"],
        )
        # Every visible child belongs to one semantic, clickable metric card.
        for cell in self.cells.values():
            for child in cell.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_compact(False)

    def _growth_name_content_width(self) -> int:
        return max(
            1,
            self.growth_name.fontMetrics().horizontalAdvance(
                str(self.growth_name._full_text)
            ),
        )

    def _growth_value_content_width(self) -> int:
        visible_text = (
            self._growth_value_full_text.removesuffix(" Growth")
            if self._compact else
            self._growth_value_full_text
        )
        return max(
            1,
            self.growth_value.fontMetrics().horizontalAdvance(visible_text),
        )

    def _sync_growth_identity_layout(self) -> None:
        margins = self.cells["growth"].layout().contentsMargins()
        available = (
            0
            if self._compact
            else max(
                0,
                int(self.cells["growth"].contentsRect().width())
                - margins.left()
                - margins.right(),
            )
        )
        telemetry = self.growth_identity_responsive.evaluate(available)
        self.growth_name.setMinimumWidth(
            self._growth_name_content_width()
            if telemetry.mode == WIDE_MODE else
            0
        )
        self.cells["growth"].setProperty("growthIdentityMode", telemetry.mode)
        QTimer.singleShot(0, self.growth_name._refresh_elision)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "growth_identity_responsive"):
            self._sync_growth_identity_layout()
            QTimer.singleShot(0, self._sync_growth_identity_layout)
        super().resizeEvent(event)

    def wide_content_minimum_width(self) -> int:
        """Return the stable width needed by the four-column full-copy mode.

        Growth spans two grid columns while Streak and Garden Coins each own
        one.  The Streak heading is the widest single-column requirement: its
        label and the largest source-defined bonus badge must coexist without
        either QLabel being compressed.  Measuring that content directly
        keeps the decision tied to the active Qt font and display scale.
        """

        maximum_bonus = max(percent for _days, percent in STREAK_BONUS_TIERS)
        bonus_text = f"Streak bonus +{maximum_bonus}%"
        label_width = max(
            int(self.streak_label.sizeHint().width()),
            int(self.streak_label.fontMetrics().horizontalAdvance("ANKI STREAK")),
        )
        bonus_width = (
            int(self.streak_bonus.fontMetrics().horizontalAdvance(bonus_text))
            + self.BONUS_BADGE_HORIZONTAL_CHROME
        )
        streak_column_width = (
            self.CELL_HORIZONTAL_INSET
            + label_width
            + self.STREAK_HEADING_SPACING
            + bonus_width
        )
        return streak_column_width * 4

    def _streak_bonus_minimum_width(self, *, compact: bool) -> int:
        maximum_bonus = max(percent for _days, percent in STREAK_BONUS_TIERS)
        text = f"Streak bonus +{maximum_bonus}%"
        return (
            int(self.streak_bonus.fontMetrics().horizontalAdvance(text))
            + self.BONUS_BADGE_HORIZONTAL_CHROME
        )

    def set_compact(self, compact: bool) -> None:
        self._compact = bool(compact)
        onboarding_mode = bool(getattr(self, "_onboarding_mode", False))
        for key, _title, _description in self.METRICS:
            self.grid.removeWidget(self.cells[key])
        if onboarding_mode:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 4)
        elif compact:
            # Long plant, streak, and coin values retain their natural font
            # size. Move complete metric groups onto two rows instead of
            # compressing labels or clipping tabular values into one line.
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 4)
            self.grid.addWidget(self.cells["streak"], 1, 0, 1, 2)
            self.grid.addWidget(self.cells["currency"], 1, 2, 1, 2)
        else:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 2)
            self.grid.addWidget(self.cells["streak"], 0, 2)
            self.grid.addWidget(self.cells["currency"], 0, 3)
        stretches = (1, 1, 1, 1)
        self.growth_support.setVisible(
            not compact and bool(self.growth_support.text()) and not onboarding_mode
        )
        self.streak_support.setVisible(
            not compact and bool(self.streak_support.text()) and not onboarding_mode
        )
        self.currency_support.hide()
        self.streak_label.setText("")
        self.streak_label.setAccessibleName("Anki streak")
        self.streak_label.setMinimumWidth(self.streak_label.sizeHint().width())
        self.streak_bonus.setMinimumWidth(
            max(48, self._streak_bonus_minimum_width(compact=compact))
        )
        self.streak_heading.removeWidget(self.streak_bonus)
        self.streak_value_row.removeWidget(self.streak_bonus)
        if compact:
            self.streak_value_row.insertWidget(
                2,
                self.streak_bonus,
                0,
                Qt.AlignmentFlag.AlignBottom,
            )
        else:
            self.streak_heading.addWidget(self.streak_bonus)
        self.streak_bonus.setText(
            f"+{self._streak_bonus_percent}% Growth"
            if self._streak_bonus_percent else ""
        )
        self.streak_bonus.setVisible(self._streak_bonus_percent > 0)
        refresh_growth_value = getattr(self, "_refresh_growth_value_copy", None)
        if callable(refresh_growth_value):
            refresh_growth_value()
        sync_growth_identity = getattr(self, "_sync_growth_identity_layout", None)
        if callable(sync_growth_identity):
            sync_growth_identity()
        if hasattr(self.cells["streak"], "setVisible"):
            self.cells["streak"].setVisible(not onboarding_mode)
            self.cells["currency"].setVisible(not onboarding_mode)
        for column, stretch in enumerate(stretches):
            self.grid.setColumnStretch(column, stretch)

    def set_onboarding_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._onboarding_mode:
            return
        self._onboarding_mode = enabled
        for cell in self.cells.values():
            # The guided header still contains the complete Growth identity
            # at nurture/completion. Keep the same content-safe vertical floor
            # while hiding the unrelated Streak and Coin cells.
            cell.setMinimumHeight(54)
        set_control_enabled(
            self.cells["growth"],
            not enabled,
            disabled_reason="Choose and nurture a starter plant to open Growth details.",
            enabled_description="Open Plant Growth details.",
        )
        self.cells["growth"].setCursor(
            Qt.CursorShape.ArrowCursor if enabled else Qt.CursorShape.PointingHandCursor
        )
        self.set_compact(self._compact)

    def set_values(self, **values: str) -> None:
        for key, value in values.items():
            label = self.values.get(key)
            if label is not None:
                label.setText(value)
                label.setAccessibleDescription(f"{label.text()}")
                cell = self.cells.get(key)
                title, explanation = self.metric_copy.get(key, (key, ""))
                if cell is not None:
                    cell.setAccessibleDescription(
                        f"{METRIC_AFFORDANCE}. Open {title} details. {value}. {explanation}"
                    )

    def _refresh_growth_value_copy(self) -> None:
        full_text = str(self._growth_value_full_text)
        visible_text = (
            full_text.removesuffix(" Growth")
            if self._compact else
            full_text
        )
        self.growth_value.setText(visible_text)
        self.growth_value.setMinimumWidth(self.growth_value.sizeHint().width())
        self.growth_value.setAccessibleName(full_text)
        self.growth_value.setToolTip(full_text if visible_text != full_text else "")

    def set_growth_details(
        self,
        *,
        plant_name: str,
        stage: str,
        next_stage: str,
        total_growth: int,
        current: int,
        maximum: int,
        remaining: int,
        fully_grown: bool,
        accessible_text: str,
        status_label: str = "Nurtured",
        forecast_text: str = "",
        forecast_tooltip: str = "",
    ) -> None:
        safe_maximum = max(1, int(maximum))
        safe_current = min(safe_maximum, max(0, int(current)))
        normalized_status = str(status_label or "FIRST PLANT").upper()
        onboarding_state_only = not str(plant_name).strip() or normalized_status in {
            "NO PLANT SELECTED",
            "READY TO NURTURE",
            "READY TO PLACE",
        }
        if onboarding_state_only:
            self.growth_kicker.hide()
            self.growth_name.setText(str(status_label))
            self.growth_name.show()
            self.growth_stage.hide()
            self.growth_value.hide()
            self.progress["growth"].hide()
            self.growth_support.hide()
            self.cells["growth"].setAccessibleDescription(
                f"{status_label}. {accessible_text}"
            )
            return
        self.growth_kicker.hide()
        self.growth_name.setText(
            " · ".join(part for part in (str(plant_name), str(stage)) if part)
        )
        self.growth_name.setVisible(bool(str(plant_name).strip()))
        self.growth_value.show()
        self.growth_stage.setText("")
        self.growth_stage.hide()
        if not stage:
            self._growth_value_full_text = "—"
            self.growth_support.setText("")
        else:
            self._growth_value_full_text = (
                "Fully grown"
                if fully_grown else
                f"{safe_current:,} / {safe_maximum:,}"
            )
            if normalized_status == "READY TO NURTURE":
                self.growth_support.setText("")
            else:
                self.growth_support.setText("")
                self.growth_support.setToolTip(str(forecast_tooltip))
        self.growth_support.hide()
        self._refresh_growth_value_copy()
        self._sync_growth_identity_layout()
        if fully_grown:
            self.progress["growth"].hide()
        else:
            self.set_progress(
                "growth", safe_current, safe_maximum, accessible_text=accessible_text
            )
        self.cells["growth"].setAccessibleDescription(
            f"{METRIC_AFFORDANCE}. Open Plant Growth details. {accessible_text} {GROWTH_EXPLANATION}"
        )

    def set_streak_details(
        self,
        *,
        days: int,
        bonus_percent: int,
        support: str,
    ) -> None:
        safe_days = max(0, int(days))
        self._streak_bonus_percent = max(0, int(bonus_percent))
        self.streak_number.setText(
            "No streak" if safe_days == 0 else f"{safe_days:,}-day streak"
        )
        self.streak_unit.setText("")
        self.streak_unit.hide()
        self.streak_bonus.setText(
            f"+{self._streak_bonus_percent}% Growth"
            if self._streak_bonus_percent else ""
        )
        self.streak_bonus.setVisible(self._streak_bonus_percent > 0)
        self.streak_support.setText(str(support))
        self.streak_support.hide()
        title, explanation = self.metric_copy["streak"]
        self.cells["streak"].setAccessibleDescription(
            f"{METRIC_AFFORDANCE}. Open {title} details. {safe_days:,} days; +{max(0, int(bonus_percent))}% Growth. "
            f"{support}. {explanation}"
        )

    def set_currency_details(self, balance: int) -> None:
        safe_balance = max(0, int(balance))
        self.currency_value.setText(f"{safe_balance:,} Garden Coins")
        title, explanation = self.metric_copy["currency"]
        self.cells["currency"].setAccessibleDescription(
            f"{METRIC_AFFORDANCE}. Open {title} details. {safe_balance:,} Garden Coins. {explanation}"
        )

    def set_progress(
        self,
        key: str,
        current: int,
        maximum: int,
        *,
        accessible_text: str,
    ) -> None:
        bar = self.progress.get(key)
        if bar is None:
            return
        safe_maximum = max(1, int(maximum))
        safe_current = min(safe_maximum, max(0, int(current)))
        bar.setValue(round(safe_current / safe_maximum * 1000))
        bar.setAccessibleDescription(accessible_text)
        bar.show()


class RearrangeBar(QFrame):
    """Mode-only controls kept separate from plant inspection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("movePanel", True)
        self.setProperty("error", False)
        self.setAccessibleName("Move")
        self.plant_id = ""
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)
        self.bar_layout = QHBoxLayout(self)
        self.bar_layout.setContentsMargins(12, 4, 12, 4)
        copy = QHBoxLayout()
        copy.setSpacing(8)
        self.title = QLabel("")
        self.title.setProperty("moveTitle", True)
        self.instructions = QLabel("Choose a bed.")
        self.instructions.setTextFormat(Qt.TextFormat.PlainText)
        self.instructions.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.instructions)
        self.bar_layout.addLayout(copy, 1)
        self.retry = QPushButton("Try again")
        _set_button_variant(self.retry, BUTTON_VARIANT_PRIMARY)
        self.retry.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.retry.hide()
        self.bar_layout.addWidget(self.retry)
        self.cancel = QPushButton("Cancel")
        _set_button_variant(self.cancel, BUTTON_VARIANT_SECONDARY)
        self.cancel.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.bar_layout.addWidget(self.cancel)
        self.hide()

    def set_failure(self, message: str) -> None:
        self.title.setText("Couldn’t move the plant")
        self.instructions.setText(str(message))
        self.setAccessibleName("Couldn’t move the plant")
        self.setAccessibleDescription(
            f"{message} Try again, or cancel move."
        )
        self.setProperty("error", True)
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(56)
        self.retry.show()
        self.cancel.setText("Stop moving")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.show()

    def clear_failure(self) -> None:
        self.setProperty("error", False)
        self.setAccessibleName("Move")
        self.setAccessibleDescription("")
        self.title.setText("")
        self.instructions.setText("Choose a bed.")
        self.cancel.setText("Cancel")
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)
        self.retry.hide()
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def set_compact(self, compact: bool) -> None:
        self.bar_layout.setDirection(
            QBoxLayout.Direction.LeftToRight
        )
        self.title.setVisible(not compact)
        if not bool(self.property("error")):
            self.setMinimumHeight(42 if compact else 40)
            self.setMaximumHeight(42 if compact else 40)

    def set_destinations(self, rows: list[tuple[str, int]]) -> None:
        """Compatibility no-op; destinations are selected directly in the scene."""

    def selected_destination(self) -> int | None:
        return None


class GardenSideNavigation(QWidget):
    """Responsive left rail that becomes a content-measured grid when narrow."""

    currentChanged = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Garden Progress sections")
        self.root_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(22)
        self.rail = QFrame()
        self.rail.setProperty("sideNavigation", True)
        self.rail_layout = QGridLayout(self.rail)
        self.rail_layout.setContentsMargins(0, 0, 0, 0)
        self.rail_layout.setHorizontalSpacing(4)
        self.rail_layout.setVerticalSpacing(4)
        self.stack = QStackedWidget()
        self.stack.setAccessibleName("Garden Progress content")
        self.buttons: dict[str, QPushButton] = {}
        self.keys: list[str] = []
        self._compact = False
        self._rail_columns = 1
        self.root_layout.addWidget(self.rail, 0)
        self.root_layout.addWidget(self.stack, 1)
        self.set_compact(False)

    def add_page(self, key: str, label: str, widget: QWidget) -> None:
        normalized = str(key)
        button = QPushButton(label)
        button.setCheckable(True)
        button.setProperty("sideNavItem", True)
        button.setAccessibleName(f"Open {label}")
        button.clicked.connect(
            lambda _checked=False, page_key=normalized: self.set_current(page_key)
        )
        self.buttons[normalized] = button
        self.keys.append(normalized)
        self.stack.addWidget(widget)
        self._reflow_rail()
        if len(self.keys) == 1:
            self.set_current(normalized, emit=False)

    def set_current(self, key: str, *, emit: bool = True) -> None:
        normalized = str(key)
        if normalized not in self.keys:
            normalized = self.keys[0] if self.keys else ""
        if not normalized:
            return
        index = self.keys.index(normalized)
        self.stack.setCurrentIndex(index)
        for page_key, button in self.buttons.items():
            selected = page_key == normalized
            button.setChecked(selected)
            button.setProperty("selected", selected)
            style = button.style()
            if style is not None:
                style.unpolish(button)
                style.polish(button)
        if emit:
            self.currentChanged.emit(normalized)

    def set_compact(self, compact: bool) -> None:
        self._compact = bool(compact)
        self.root_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact else
            QBoxLayout.Direction.LeftToRight
        )
        self.rail.setMaximumWidth(16777215 if compact else 160)
        self.rail.setMinimumWidth(0 if compact else 148)
        for button in self.buttons.values():
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        self._reflow_rail()
        if compact:
            QTimer.singleShot(0, self._reflow_rail)

    def _compact_column_count(self) -> int:
        available = max(1, int(self.rail.width() or self.width()))
        item_width = 112
        if self.buttons:
            item_width = max(
                112,
                *(
                    button.fontMetrics().horizontalAdvance(button.text()) + 36
                    for button in self.buttons.values()
                ),
            )
        return responsive_column_count(
            available,
            minimum_item_width=item_width,
            maximum_columns=3,
            spacing=self.rail_layout.horizontalSpacing(),
        )

    def _reflow_rail(self) -> None:
        while self.rail_layout.count():
            self.rail_layout.takeAt(0)
        columns = self._compact_column_count() if self._compact else 1
        self._rail_columns = max(1, int(columns))
        for index, button in enumerate(self.buttons.values()):
            self.rail_layout.addWidget(
                button,
                index // self._rail_columns,
                index % self._rail_columns,
            )
        rows = max(
            1,
            (len(self.buttons) + self._rail_columns - 1) // self._rail_columns,
        )
        for column in range(3):
            self.rail_layout.setColumnStretch(
                column,
                1 if column < self._rail_columns else 0,
            )
        for row in range(len(self.buttons) + 1):
            self.rail_layout.setRowStretch(row, 0)
        if self._compact:
            height = (
                rows * BUTTON_MIN_HEIGHT
                + max(0, rows - 1) * self.rail_layout.verticalSpacing()
            )
            self.rail.setMinimumHeight(height)
            self.rail.setMaximumHeight(height)
        else:
            self.rail.setMinimumHeight(0)
            self.rail.setMaximumHeight(16777215)
            self.rail_layout.setRowStretch(rows, 1)
        self.rail.setProperty("navigationColumns", self._rail_columns)
        self.rail.setProperty("navigationRows", rows)
        self.rail.updateGeometry()

    def resizeEvent(self, event: Any) -> None:
        if self._compact:
            columns = self._compact_column_count()
            if columns != self._rail_columns:
                self._reflow_rail()
        super().resizeEvent(event)


def _streak_milestone_fraction(streak_days: int) -> float:
    points = (0, *(threshold for threshold, _percent in STREAK_BONUS_TIERS))
    days = max(0, int(streak_days))
    if days >= points[-1]:
        return 1.0
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if start <= days < end:
            within = (days - start) / max(1, end - start)
            return (index + within) / (len(points) - 1)
    return 0.0


def _streak_support_text(streak_days: int, bonus_percent: int) -> str:
    days = max(0, int(streak_days))
    if days <= 0:
        return "Study today to start your streak"
    maximum_day, maximum_bonus = STREAK_BONUS_TIERS[-1]
    if days >= maximum_day and int(bonus_percent) >= maximum_bonus:
        return "Maximum Growth bonus reached"
    for threshold, percent in STREAK_BONUS_TIERS:
        if threshold > days:
            return f"Next bonus: +{percent}% at {threshold} days"
    return "Keep studying to maintain your Growth bonus"


class _TabbedProgressShell(GardenDialog):
    """Compatibility shell retained for older integrations; no longer instantiated."""

    def __init__(self, parent: QWidget, tabs: QTabWidget) -> None:
        super().__init__(
            parent,
            "Garden Progress",
            subtitle=(
                "See what your studying has earned, what advances each system, "
                "and what comes next."
            ),
        )
        self.apply_size_policy(
            DialogSizeClass.STANDARD_TEXT,
            preferred_width=820,
            preferred_height=620,
        )
        tabs.tabBar().setUsesScrollButtons(True)
        tabs.tabBar().setExpanding(True)
        tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.set_body_widget(tabs)


class GardenDetailsDialog(GardenDialog):
    """One reusable, tabbed home for the three Garden summary metrics."""

    METRIC_TABS = (
        ("growth", "Plant Growth"),
        ("streak", "Anki Streak"),
        ("currency", "Garden Coins"),
    )

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        storage: Any,
        open_nursery: Any,
    ) -> None:
        super().__init__(parent, "Plant Growth")
        self.engine = engine
        self.storage = storage
        self.open_nursery = open_nursery
        self._show_all_transactions = False
        self._transaction_filter = "all"
        self.apply_size_policy(
            DialogSizeClass.STANDARD_TEXT,
            preferred_width=740,
            preferred_height=570,
        )
        self.setStyleSheet(_garden_dialog_stylesheet() + """
            QWidget[detailBodyPanel='true'] { background:#0b1f1b; }
            QLabel[detailTitle='true'] { color:#f5f7e8; font-size:20px; font-weight:800; }
            QLabel[detailSection='true'] { color:#f3f6e9; font-size:14px; font-weight:750; }
            QLabel[detailBody='true'] { color:#c5d3c9; font-size:14px; }
            QLabel[detailSupport='true'] { color:#a9bdb0; font-size:13px; }
            QLabel[detailMetric='true'] { color:#f5f7e8; font-size:31px; font-weight:800; }
            QLabel[detailGoldMetric='true'] { color:#f0ca78; font-size:32px; font-weight:800; }
            QLabel[detailBadge='true'] { color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:800; }
            QLabel[detailStatus='true'] { color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 8px; font-size:13px; font-weight:700; }
            QLabel[detailStatus='true'][streakSemantic='warning'] { color:#ffe0a3; background:#4a3820; border-color:#8b6b2e; }
            QLabel[detailStatus='true'][streakSemantic='missed'] { color:#ffc5c0; background:#48272a; border-color:#8d5057; }
            QLabel[detailStatus='true'][streakSemantic='start'] { color:#d7e8de; background:#24372f; border-color:#50665b; }
            QLabel[detailTableHeader='true'] { color:#91aa9b; font-size:12px; font-weight:800; }
            QLabel[detailPositive='true'] { color:#8ee0a8; font-size:13px; font-weight:700; }
            QLabel[detailNegative='true'] { color:#f0b4a9; font-size:13px; font-weight:700; }
            QLabel[detailCoinIcon='true'] { color:#352514; background:#e1b85e; border:2px solid #f3d58f; border-radius:25px; font-size:20px; font-weight:900; }
            QFrame[detailHero='true'] { background:#17342e; border:1px solid #557665; border-radius:12px; }
            QFrame[detailCard='true'] { background:#112b25; border:0; border-radius:11px; }
            QFrame[detailRow='true'] { border:0; border-bottom:1px solid #29463c; }
            QFrame[detailStage='true'] { background:#102622; border:1px solid #345348; border-radius:10px; }
            QFrame[detailStage='true'][detailStageState='completed'] { background:#132820; border-color:#456b57; }
            QFrame[detailStage='true'][detailStageState='current'] { background:#1a382f; border:2px solid #d1ad69; }
            QFrame[detailStage='true'][detailStageState='upcoming'] { background:#0d1e1b; border-color:#2b4239; }
            QFrame[streakDay='true'] { background:#102622; border:1px solid #345348; border-radius:9px; }
            QFrame[streakDay='true'][streakDayState='complete'] { background:#173b30; border-color:#4f806e; }
            QFrame[streakDay='true'][streakDayState='today'] { background:#1a382f; border:2px solid #82e2ac; }
            QFrame[streakDay='true'][streakDayState='missed'] { background:#321f22; border-color:#8d5057; }
            QFrame[streakDay='true'][streakDayState='neutral'] { background:#0d1e1b; border-color:#293d35; }
            QLabel[streakDayLabel='true'] { color:#b9ccc0; font-size:13px; font-weight:700; }
            QLabel[streakDayValue='true'] { color:#f3f6e9; font-size:14px; font-weight:800; }
            QProgressBar { border:0; border-radius:4px; background:#203d35; min-height:8px; max-height:8px; }
            QProgressBar::chunk { border-radius:4px; background:#65c487; }
            QScrollArea { background:transparent; border:0; }
            QPushButton[detailDisclosure='true'] { text-align:left; min-height:44px; background:transparent; border:0; border-bottom:1px solid #345348; color:#c8d8cd; }
            QPushButton[detailDisclosure='true']:hover { background:#17342e; }
            QPushButton[detailDisclosure='true'][achievementFilter='true'] { min-height:38px; max-height:38px; }
        """)

        self.tabs = GardenTabs("Garden detail sections")
        self.tabs.tabBar().setExpanding(True)
        self.body_layouts: dict[str, QVBoxLayout] = {}
        for key, label in self.METRIC_TABS:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setAccessibleName(f"{label} details")
            body = QWidget()
            body.setProperty("detailBodyPanel", True)
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(18, 18, 26, 18)
            body_layout.setSpacing(18)
            scroll.setWidget(body)
            _set_scroll_surface(scroll, body, "#0b1f1b")
            self.tabs.addTab(scroll, label)
            self.body_layouts[key] = body_layout
        self.tabs.currentChanged.connect(self._sync_context_action)
        self.set_body_widget(self.tabs)

        self.nursery = QPushButton("Open Nursery")
        self.nursery.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _set_button_variant(self.nursery, BUTTON_VARIANT_PRIMARY)
        self.nursery.clicked.connect(self._open_nursery)
        self.close_details = QPushButton("Close")
        self.close_details.setMinimumHeight(BUTTON_MIN_HEIGHT)
        _set_button_variant(self.close_details, BUTTON_VARIANT_SECONDARY)
        self.close_details.clicked.connect(self.close)
        self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(self.nursery)
        self.footer_layout.addWidget(self.close_details)
        self.refresh()
        self._fertilizer_refresh_token = self._current_fertilizer_token()
        self._fertilizer_refresh_timer = QTimer(self)
        self._fertilizer_refresh_timer.setInterval(1_000)
        self._fertilizer_refresh_timer.timeout.connect(self._refresh_timed_fertilizer)
        self._fertilizer_refresh_timer.start()
        self._sync_context_action()

    def open_metric(self, metric: str) -> None:
        keys = [key for key, _label in self.METRIC_TABS]
        key = str(metric)
        index = keys.index(key) if key in keys else 0
        self.refresh()
        self.tabs.setCurrentIndex(index)
        self.present_over_parent()
        self.tabs.tabBar().setFocus()

    def _sync_context_action(self, _index: int | None = None) -> None:
        index = self.tabs.currentIndex()
        self.set_dialog_title(self.METRIC_TABS[index][1])
        self.footer.setVisible(index == 2)

    def _current_fertilizer_token(self) -> tuple[str, str, str]:
        plant = self.engine.active_plant()
        if plant is None:
            return ("", "inactive", "")
        status = fertilizer_status(
            self.engine,
            plant,
            now=time.time(),
            description=FERTILIZER_EXPLANATION,
        )
        return (str(plant.plant_id), status.phase, status.duration)

    def _refresh_timed_fertilizer(self) -> None:
        if not self.isVisible():
            return
        token = self._current_fertilizer_token()
        if token == getattr(self, "_fertilizer_refresh_token", None):
            return
        self._fertilizer_refresh_token = token
        self.refresh()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().hide()
                        child.widget().deleteLater()

    @staticmethod
    def _label(text: str, property_name: str = "detailBody") -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setProperty(property_name, True)
        return label

    def _section_label(self, layout: QVBoxLayout, text: str) -> QLabel:
        label = self._label(text, "detailSection")
        layout.addWidget(label)
        return label

    def _value_row(
        self,
        layout: QVBoxLayout,
        label_text: str,
        value_text: str,
        *,
        total: bool = False,
    ) -> None:
        row = QFrame()
        row.setProperty("detailRow", True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 6, 0, 7)
        row_layout.setSpacing(12)
        label = self._label(label_text, "detailBody")
        value = self._label(value_text, "detailBody")
        apply_tabular_numerals(value)
        if total:
            label.setStyleSheet("font-weight:800; color:#f3f6e9;")
            value.setStyleSheet("font-weight:800; color:#f3f6e9;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(label, 1)
        row_layout.addWidget(value, 0)
        layout.addWidget(row)

    def _disclosure(
        self,
        layout: QVBoxLayout,
        title: str,
        rows: list[tuple[str, str]],
        *,
        expanded: bool = False,
        compact: bool = False,
    ) -> None:
        layout.addWidget(DisclosureRow(
            title,
            rows,
            expanded=expanded,
            compact=compact,
        ))

    @staticmethod
    def _reward_result_text(summary: Any) -> str:
        """Read the committed summary's canonical learner-facing result."""

        return str(getattr(summary, "learner_text", "") or "")

    @staticmethod
    def _reward_source_text(summary: Any) -> str:
        labels = {
            "daily_activity": "Daily activity",
            "weekly_streak": "Seven-day streak",
            "all_due": "All due",
            "achievement": "Achievement",
            "achievement_backfill": "Achievement",
            "stage": "Plant stage",
            "garden_find": "Garden Find",
            "garden_find_environment": "Garden Find",
            "environment_daily_gift": "Scenery gift",
        }
        sources = tuple(getattr(summary, "sources", ()) or ())
        visible = tuple(dict.fromkeys(
            labels.get(str(source), format_status_label(str(source)))
            for source in sources
            if str(source)
        ))
        return " + ".join(visible) if visible else "Garden reward"

    @staticmethod
    def _garden_find_result_text(finding: Any) -> str:
        """Read one committed Find's canonical persisted result copy."""

        return str(getattr(finding, "description", "") or "Reward recorded")

    def _add_recent_reward_history(self, layout: QVBoxLayout) -> None:
        self._section_label(layout, "Recent rewards")
        summaries = tuple(reversed(recent_reward_summaries(
            self.storage.state,
            limit=8,
        )))
        if not summaries:
            layout.addWidget(EmptyState(
                "No rewards recorded yet",
                "Committed study rewards will appear here.",
            ))
            return
        table = DataTable()
        grid = table.grid
        for column, heading in enumerate(("Date", "Source", "Reward")):
            header = self._label(heading, "detailTableHeader")
            if column == 2:
                header.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(header, 0, column)
        for row, summary in enumerate(summaries, start=1):
            occurred_at = str(
                getattr(summary, "occurred_at", "")
                or getattr(summary, "scheduler_day", "")
            )
            date_label = self._label(_transaction_date(occurred_at), "detailSupport")
            source_text = self._reward_source_text(summary)
            title = str(getattr(summary, "title", "") or "")
            visible_source = (
                f"{title}\n{source_text}"
                if title and title.casefold() != source_text.casefold() else
                source_text
            )
            source = self._label(visible_source, "detailBody")
            source.setAccessibleName(
                f"Reward source: {source_text}. {title}" if title else
                f"Reward source: {source_text}."
            )
            result_text = self._reward_result_text(summary)
            result = self._label(
                result_text
                or str(getattr(summary, "description", "") or "Reward recorded"),
                "detailPositive",
            )
            result.setAlignment(Qt.AlignmentFlag.AlignRight)
            apply_tabular_numerals(result)
            source.setToolTip(title or source_text)
            for cell in (date_label, source, result):
                cell.setContentsMargins(4, 7, 4, 7)
            grid.addWidget(date_label, row, 0)
            grid.addWidget(source, row, 1)
            grid.addWidget(result, row, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(table)

    def _add_recent_garden_finds(self, layout: QVBoxLayout) -> None:
        self._section_label(layout, "Recent Finds")
        findings = tuple(reversed(recent_garden_finds(
            self.storage.state,
            limit=8,
        )))
        if not findings:
            layout.addWidget(EmptyState(
                "No Garden Finds yet",
                "Garden Finds are occasional surprises from Anki card answers Garden can count.",
            ))
            return
        table = DataTable()
        grid = table.grid
        for column, heading in enumerate(("Date", "Find", "Result")):
            header = self._label(heading, "detailTableHeader")
            if column == 2:
                header.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(header, 0, column)
        for row, finding in enumerate(findings, start=1):
            date_label = self._label(
                _transaction_date(getattr(finding, "occurred_at", "")),
                "detailSupport",
            )
            name = str(getattr(finding, "display_name", "") or "Garden Find")
            tier = str(getattr(finding, "tier", "") or "")
            find_label = self._label(
                f"{name} · {tier}" if tier else name,
                "detailBody",
            )
            result = self._label(
                self._garden_find_result_text(finding),
                "detailPositive",
            )
            result.setAlignment(Qt.AlignmentFlag.AlignRight)
            apply_tabular_numerals(result)
            for cell in (date_label, find_label, result):
                cell.setContentsMargins(4, 7, 4, 7)
            grid.addWidget(date_label, row, 0)
            grid.addWidget(find_label, row, 1)
            grid.addWidget(result, row, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(table)

    def refresh(self) -> None:
        for key, _label in self.METRIC_TABS:
            layout = self.body_layouts[key]
            self._clear_layout(layout)
            try:
                if key == "growth":
                    self._refresh_growth(layout)
                elif key == "streak":
                    self._refresh_streak(layout)
                else:
                    self._refresh_currency(layout)
            except Exception:
                logger.exception("Anki Garden: unable to refresh %s details", key)
                error = QFrame()
                error.setProperty("detailCard", True)
                error_layout = QVBoxLayout(error)
                error_layout.addWidget(self._label(
                    "These Garden details could not refresh. Close and reopen the Garden to try again."
                ))
                layout.addWidget(error)
            layout.addStretch(1)

    def _refresh_growth(self, layout: QVBoxLayout) -> None:
        self.growth_charge_focus_target = None
        snapshot = select_garden_ui(self.engine, self.storage)
        planted = sorted(
            (plant for plant in snapshot.plants if plant.planted),
            key=lambda plant: (
                plant.slot_index is None,
                int(plant.slot_index) if plant.slot_index is not None else 99,
                plant.plant_id,
            ),
        )

        active = next((plant for plant in planted if plant.is_active), None)
        if active is None:
            layout.addWidget(EmptyState(
                "No nurtured plant",
                "Choose a plant to nurture.",
            ))
        else:
            active_plant = self.engine.plant_story(active.plant_id)
            active_display = growth_display(active.growth_points)
            hero = QFrame()
            hero.setProperty("detailCard", True)
            hero_layout = QHBoxLayout(hero)
            hero_layout.setContentsMargins(14, 12, 14, 12)
            hero_layout.setSpacing(12)
            if active_plant is not None:
                hero_layout.addWidget(
                    _asset_preview_label(
                        self.engine,
                        active.species,
                        active.stage,
                        size=72,
                    ),
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
            identity = QVBoxLayout()
            identity.setSpacing(4)
            name = self._label(active.name, "detailSection")
            name.setStyleSheet("font-size:19px; font-weight:800;")
            identity.addWidget(name)
            support = self._label(
                (
                    f"{format_status_label(active.stage)} · Fully grown"
                    if active.fully_grown else
                    f"{format_status_label(active.stage)} · "
                    f"{format_stage_progress(active_display.stage_points, active_display.stage_goal, format_status_label(active_display.next_stage or 'next stage'))}"
                ),
                "detailSupport",
            )
            apply_tabular_numerals(support)
            identity.addWidget(support)
            hero_layout.addLayout(identity, 1)
            layout.addWidget(hero)

        today = QFrame()
        today.setProperty("detailCard", True)
        today_layout = QVBoxLayout(today)
        today_layout.setContentsMargins(14, 12, 14, 12)
        today_layout.setSpacing(7)
        total_today = max(0, int(snapshot.growth_today))
        total_value = self._label(
            "No Growth today" if total_today <= 0 else f"{total_today:,} Growth today",
            "detailMetric",
        )
        apply_tabular_numerals(total_value)
        today_layout.addWidget(total_value)
        direct_total = snapshot.charge_growth_today + snapshot.direct_reward_growth_today
        if total_today <= 0:
            today_layout.addWidget(self._label(
                "Answer a card to start.",
                "detailSupport",
            ))
        if total_today > 0:
            self._disclosure(
                today_layout,
                "Growth breakdown",
                [
                    ("From cards", f"{snapshot.study_growth_generated:,}"),
                    ("Bonuses", f"{snapshot.passive_growth_credited_today:,}"),
                    ("Rewards and charges", f"{direct_total:,}"),
                ],
                expanded=False,
                compact=True,
            )
        today.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(today)
        layout.addWidget(today)

        if snapshot.growth_accounting_stale:
            stale = QLabel("Some Growth details are unavailable.")
            stale.setWordWrap(True)
            stale.setProperty("fieldError", True)
            stale.setAccessibleName("Some Growth details are unavailable")
            set_semantic_role(stale, SemanticRole.BANNER, tone=FeedbackTone.WARNING)
            layout.addWidget(stale)

        stage_plant = (
            self.engine.plant_story(active.plant_id)
            if active is not None
            else (
                self.engine.plant_story(planted[0].plant_id)
                if planted else None
            )
        )
        if stage_plant is not None:
            self._add_growth_stage_path(
                layout,
                stage_plant,
                growth_display(stage_plant.growth_points),
            )

        if not planted:
            self._section_label(layout, "Planted plants")
            layout.addWidget(EmptyState(
                "No plants are planted",
                "Place a plant from your Collection in a garden bed.",
            ))
            return

        listed_plants = [plant for plant in planted if active is None or not plant.is_active]
        if not listed_plants:
            return

        self._section_label(
            layout,
            "Other planted plants" if active is not None else "Planted plants",
        )
        plant_grid = ResponsiveTileGrid(
            breakpoint=650,
            minimum_tile_width=300,
            maximum_columns=2,
        )
        plant_grid.setAccessibleName("Other planted plants")
        for plant in listed_plants:
            card = QFrame()
            card.setProperty("detailCard", True)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(7)

            heading = QHBoxLayout()
            heading.setSpacing(10)
            heading.addWidget(
                _asset_preview_label(
                    self.engine,
                    plant.species,
                    plant.stage,
                    size=58,
                ),
                0,
                Qt.AlignmentFlag.AlignTop,
            )
            identity = QVBoxLayout()
            identity.setSpacing(2)
            name = self._label(plant.name, "detailSection")
            stage = self._label(format_status_label(plant.stage), "detailSupport")
            identity.addWidget(name)
            identity.addWidget(stage)
            heading.addLayout(identity, 1)
            card_layout.addLayout(heading)

            if plant.growth_today > 0:
                today_value = self._label(
                    f"{plant.growth_today:,} Growth today",
                    "detailSupport",
                )
                apply_tabular_numerals(today_value)
                card_layout.addWidget(today_value)

            display = growth_display(plant.growth_points)
            if not plant.fully_grown:
                progress = ProgressBar(f"{plant.name} progress to next stage")
                progress.set_progress(
                    "",
                    display.stage_points,
                    max(1, display.stage_goal),
                    value_text=format_stage_progress(
                        display.stage_points,
                        display.stage_goal,
                        format_status_label(display.next_stage or "next stage"),
                    ),
                )
                progress.label.hide()
                card_layout.addWidget(progress)
                charge = QPushButton("Use charge")
                charge.setMinimumHeight(BUTTON_MIN_HEIGHT)
                charge.setAccessibleName(f"Use Growth Charge on {plant.name}")
                charge.setAccessibleDescription(
                    "Use a Growth Charge on this plant."
                )
                _set_button_variant(charge, BUTTON_VARIANT_SECONDARY)
                charge.clicked.connect(
                    lambda _checked=False, plant_id=plant.plant_id, source=charge:
                    self._open_growth_charge_dialog(plant_id, source)
                )
                if self.growth_charge_focus_target is None:
                    self.growth_charge_focus_target = charge
                card_layout.addWidget(charge)
            else:
                finished = self._label("Fully grown", "detailSupport")
                card_layout.addWidget(finished)
            accessible_parts = [plant.name, format_status_label(plant.stage)]
            if plant.growth_today > 0:
                accessible_parts.append(f"{plant.growth_today:,} Growth today")
            card.setAccessibleName(". ".join(accessible_parts) + ".")
            plant_grid.add_tile(card)
        layout.addWidget(plant_grid)

    def _add_growth_stage_path(self, layout: QVBoxLayout, plant: Any, display: Any) -> None:
        self._section_label(layout, "Growth stages")
        stages = ResponsiveTileGrid(
            breakpoint=650,
            minimum_tile_width=92,
            maximum_columns=6,
        )
        stages.setAccessibleName("Six-stage plant growth track")
        for index, stage_key in enumerate(GROWTH_STAGES):
            state = (
                "completed" if index < display.stage_index else
                "current" if index == display.stage_index else
                "upcoming"
            )
            stage_card = QFrame()
            stage_card.setProperty("detailStage", True)
            stage_card.setProperty("detailStageState", state)
            stage_layout = QVBoxLayout(stage_card)
            stage_layout.setContentsMargins(7, 7, 7, 7)
            stage_layout.setSpacing(3)
            stage_layout.addWidget(
                _asset_preview_label(
                    self.engine,
                    plant.species,
                    stage_key,
                    size=52,
                    rare_unlocked=state != "upcoming",
                ),
                0,
                Qt.AlignmentFlag.AlignHCenter,
            )
            stage_name = self._label(format_status_label(stage_key), "detailSection")
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(stage_name)
            stage_card.setAccessibleName(
                f"{format_status_label(stage_key)} stage. "
                f"{state}."
            )
            stages.add_tile(stage_card)
        layout.addWidget(stages)

    def _open_growth_charge_dialog(
        self,
        plant_id: str,
        invoker: QWidget | None = None,
    ) -> None:
        dialog = GrowthChargeConfirmationDialog(
            self,
            self.engine,
            plant_id,
            open_nursery=self._open_nursery,
        )
        dialog.remember_invoker(invoker)
        self.growth_charge_dialog = dialog
        dialog.exec()
        if dialog.outcome is None or not dialog.outcome.success:
            return
        parent = self.parentWidget()
        refresh = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh):
            refresh("Growth Charge")
        else:
            self.refresh()

    def _refresh_streak(self, layout: QVBoxLayout) -> None:
        state = self.storage.state
        try:
            current_day = date.fromisoformat(str(state.daily_stats.day)[:10])
        except (TypeError, ValueError):
            current_day = date.today()
        presentation = streak_presentation(
            getattr(state, "streak_days", 0),
            getattr(state, "last_active_day", ""),
            getattr(state.daily_stats, "reviewed", 0),
            today=current_day,
        )
        days = presentation.current_days
        reward_rules = {
            rule.rule_id: rule
            for rule in recurring_reward_presentations(
                state,
                self.engine,
                current_streak_days=days,
            )
        }
        bonus = self.engine.current_streak_bonus_percent() if days > 0 else 0
        maintained_today = presentation.status_label == "Active"
        cutoff_text = "Unavailable"
        try:
            cutoff_ms = int(self.storage.current_day_end_ms())
            if cutoff_ms > 0:
                cutoff = datetime.fromtimestamp(cutoff_ms / 1000)
                cutoff_text = cutoff.strftime("%I:%M %p").lstrip("0")
        except (AttributeError, OSError, TypeError, ValueError):
            pass

        positive_bonus_tiers = tuple(
            (day, percent)
            for day, percent in STREAK_BONUS_TIERS
            if percent > 0
        )
        next_tier = next(
            ((day, percent) for day, percent in positive_bonus_tiers if days < day),
            None,
        )
        next_day = (
            next_tier[0]
            if next_tier is not None else
            positive_bonus_tiers[-1][0]
        )

        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 15, 18, 15)
        hero_layout.setSpacing(8)
        status_row = QHBoxLayout()
        metric_text = (
            "No streak"
            if presentation.semantic == "start" else
            f"Streak ended at {_day_count(presentation.previous_days)}"
            if presentation.semantic == "missed" else
            f"{days:,}-day streak"
        )
        metric = self._label(metric_text, "detailMetric")
        apply_tabular_numerals(metric)
        status = self._label("At risk", "detailStatus")
        status.setProperty("streakSemantic", presentation.semantic)
        status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(metric, 1)
        if presentation.semantic == "warning":
            status_row.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(status_row)
        days_to_next = max(0, next_day - days)
        if days > 0 and bonus > 0:
            bonus_label = self._label(f"+{bonus}% Growth", "detailSection")
            hero_layout.addWidget(bonus_label)
        if days_to_next > 0:
            hero_layout.addWidget(self._label(
                f"Next bonus at {next_day:,} days · {_day_count(days_to_next)} left",
                "detailSupport",
            ))
        week = QHBoxLayout()
        week.setSpacing(7)
        try:
            last_active = date.fromisoformat(str(state.last_active_day)[:10])
        except (TypeError, ValueError):
            last_active = current_day if maintained_today else current_day - timedelta(days=1)
        streak_start = last_active - timedelta(days=max(0, days - 1))
        week_start = current_day - timedelta(days=current_day.weekday())
        for offset in range(7):
            calendar_day = week_start + timedelta(days=offset)
            complete = bool(days > 0 and streak_start <= calendar_day <= last_active)
            missed = presentation.missed_day == calendar_day
            day_state = (
                "today" if calendar_day == current_day else
                "complete" if complete else
                "missed" if missed else
                "upcoming" if calendar_day > current_day else
                "neutral"
            )
            day = QFrame()
            day.setProperty("streakDay", True)
            day.setProperty("streakDayState", day_state)
            day.setMinimumHeight(64)
            day_layout = QVBoxLayout(day)
            day_layout.setContentsMargins(6, 5, 6, 5)
            day_layout.setSpacing(1)
            day_name = self._label(calendar_day.strftime("%a")[:1], "streakDayLabel")
            day_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            date_value = self._label(str(calendar_day.day), "detailSupport")
            apply_tabular_numerals(date_value)
            date_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state_icon = self._label(
                "✓" if complete else "●" if calendar_day == current_day else "!" if missed else "○" if calendar_day > current_day else "·",
                "streakDayValue",
            )
            state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_value = self._label(
                "Today" if calendar_day == current_day else
                "Complete" if complete else
                "Missed" if missed else
                "Upcoming" if calendar_day > current_day else
                "—",
                "streakDayLabel",
            )
            day_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_layout.addWidget(day_name)
            day_layout.addWidget(date_value)
            day_layout.addWidget(state_icon)
            day.setAccessibleName(
                f"{calendar_day.strftime('%A')}, "
                f"{'today' if calendar_day == current_day else 'streak complete' if complete else 'missed' if missed else 'upcoming' if calendar_day > current_day else 'before this streak'}"
            )
            week.addWidget(day, 1)
        hero_layout.addLayout(week)
        if presentation.semantic == "warning" and cutoff_text != "Unavailable":
            cutoff_value = self._label(f"Day ends at {cutoff_text}", "detailSupport")
            apply_tabular_numerals(cutoff_value)
            hero_layout.addWidget(cutoff_value)
        layout.addWidget(hero)

        if presentation.message:
            layout.addWidget(self._label(presentation.message, "detailBody"))

        self._section_label(layout, "Rewards")
        reward_grid = ResponsiveTileGrid(
            breakpoint=720,
            minimum_tile_width=210,
            maximum_columns=3,
        )
        reward_grid.setAccessibleName("Daily and streak reward status")
        for rule_id, heading in (
            ("daily_activity", "First card today"),
            ("all_due", "Finish today’s due cards"),
            ("weekly_streak", "Day 7"),
        ):
            rule = reward_rules[rule_id]
            card = QFrame()
            card.setProperty("detailCard", True)
            card.setProperty(
                "rewardState",
                "earned" if rule.awarded_today else "available",
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(13, 11, 13, 11)
            card_layout.setSpacing(5)
            card_layout.addWidget(self._label(heading, "detailSupport"))
            reward = self._label(rule.reward_summary, "detailSection")
            apply_tabular_numerals(reward)
            card_layout.addWidget(reward)
            trigger = self._label(rule.trigger, "detailSupport")
            trigger.setWordWrap(True)
            trigger.hide()
            card.setAccessibleName(
                f"{heading}. {rule.reward_summary}."
            )
            card.setAccessibleDescription(rule.trigger)
            reward_grid.add_tile(card)
        layout.addWidget(reward_grid)

        self._section_label(layout, "Growth bonuses")
        milestone_table = DataTable()
        milestone_grid = milestone_table.grid
        milestone_grid.setHorizontalSpacing(14)
        for column, heading in enumerate(("Streak", "Growth bonus")):
            header = self._label(heading, "detailTableHeader")
            milestone_grid.addWidget(header, 0, column)
        display_bonus_tiers = tuple(STREAK_BONUS_TIERS)
        reached_indexes = [
            index for index, (threshold, _percent) in enumerate(display_bonus_tiers)
            if days >= threshold
        ]
        current_index = reached_indexes[-1] if reached_indexes else None
        next_index = next(
            (
                index for index, (threshold, _percent) in enumerate(display_bonus_tiers)
                if days < threshold
            ),
            None,
        )
        milestone_indexes: list[int] = []
        if current_index is not None:
            milestone_indexes.append(current_index)
        if next_index is not None:
            milestone_indexes.append(next_index)
            if next_index + 1 < len(display_bonus_tiers):
                milestone_indexes.append(next_index + 1)
        for row, tier_index in enumerate(dict.fromkeys(milestone_indexes), start=1):
            day, percent = display_bonus_tiers[tier_index]
            next_threshold = (
                display_bonus_tiers[tier_index + 1][0]
                if tier_index + 1 < len(display_bonus_tiers) else
                None
            )
            tier_end = next_threshold - 1 if next_threshold is not None else None
            tier_label = (
                f"Days {day:,}–{tier_end:,}"
                if tier_end is not None and tier_end != day else
                f"Day {day:,}"
                if tier_end == day else
                f"Day {day:,}+"
            )
            milestone = self._label(tier_label, "detailBody")
            reward = self._label(
                f"{'+' if percent > 0 else ''}{percent}% Growth",
                "detailBody",
            )
            apply_tabular_numerals(milestone)
            apply_tabular_numerals(reward)
            for cell in (milestone, reward):
                cell.setContentsMargins(4, 7, 4, 7)
            milestone_grid.addWidget(milestone, row, 0)
            milestone_grid.addWidget(reward, row, 1)
        milestone_grid.setColumnStretch(1, 1)
        layout.addWidget(milestone_table)

        streak_achievements = tuple(
            projection
            for projection in achievement_presentations(state)
            if projection.progress_metric == "streak_days"
        )
        if streak_achievements:
            self._section_label(layout, "One-time streak achievements")
            achievement_table = DataTable()
            achievement_grid = achievement_table.grid
            achievement_grid.setHorizontalSpacing(14)
            for column, heading in enumerate(("Achievement", "Reward", "Status")):
                header = self._label(heading, "detailTableHeader")
                if column == 2:
                    header.setAlignment(Qt.AlignmentFlag.AlignRight)
                achievement_grid.addWidget(header, 0, column)
            for row, projection in enumerate(streak_achievements, start=1):
                achievement = self._label(projection.name, "detailBody")
                reward = self._label(projection.reward_summary, "detailBody")
                status_text = (
                    (
                        f"Unlocked {_calendar_date(projection.unlocked_at)}"
                        if projection.unlocked_at else
                        "Unlocked · date unavailable"
                    )
                    if projection.unlocked else
                    f"{projection.value_text} · In progress"
                    if projection.current > 0 else
                    f"{projection.value_text} · Locked"
                )
                status = self._label(
                    status_text,
                    "detailStatus" if not projection.unlocked and projection.current > 0 else "detailSupport",
                )
                status.setAlignment(Qt.AlignmentFlag.AlignRight)
                apply_tabular_numerals(reward)
                for cell in (achievement, reward, status):
                    cell.setContentsMargins(4, 7, 4, 7)
                achievement_grid.addWidget(achievement, row, 0)
                achievement_grid.addWidget(reward, row, 1)
                achievement_grid.addWidget(status, row, 2)
            achievement_grid.setColumnStretch(1, 1)
            layout.addWidget(achievement_table)

    def _refresh_currency(self, layout: QVBoxLayout) -> None:
        state = self.storage.state
        balance = max(0, int(state.currency_balance))
        achievement_views = achievement_presentations(state)
        achievement_names = {
            projection.achievement_id: projection.name
            for projection in achievement_views
        }
        all_transactions = sorted(
            state.currency_transactions,
            key=lambda transaction: str(getattr(transaction, "occurred_at", "")),
            reverse=True,
        )
        lifetime_earned = sum(
            max(0, int(transaction.delta)) for transaction in all_transactions
        )
        lifetime_spent = sum(
            abs(min(0, int(transaction.delta))) for transaction in all_transactions
        )
        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(14)
        icon = self._label("G", "detailCoinIcon")
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setAccessibleName("Garden Coin")
        balance_copy = QVBoxLayout()
        balance_copy.setSpacing(1)
        balance_value = self._label(
            f"{balance:,} Garden {'Coin' if balance == 1 else 'Coins'}",
            "detailGoldMetric",
        )
        apply_tabular_numerals(balance_value)
        balance_copy.addWidget(balance_value)
        hero_layout.addWidget(icon)
        hero_layout.addLayout(balance_copy, 1)
        open_nursery = QPushButton("Nursery")
        _set_button_variant(open_nursery, BUTTON_VARIANT_PRIMARY)
        open_nursery.clicked.connect(self._open_nursery)
        hero_layout.addWidget(open_nursery, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(hero)
        layout.addWidget(StatSummary([
            ("Earned", f"{lifetime_earned:,}"),
            ("Spent", f"{lifetime_spent:,}"),
        ]))

        if not all_transactions:
            layout.addWidget(self._label(
                "Earn Garden Coins from cards, streaks, achievements, and Garden Finds.",
                "detailBody",
            ))
            self._disclosure(
                layout,
                "How to earn Garden Coins",
                [
                    ("Study", "Daily, all-due, and streak rewards can award Garden Coins."),
                    ("Progress", "Plant stages, achievements, and some Garden Finds can award coins."),
                ],
                compact=True,
            )
            return

        self._section_label(layout, "Recent activity")
        if len(all_transactions) > 8:
            filters = QHBoxLayout()
            filters.setSpacing(6)
            for key, label in (("all", "All"), ("earned", "Earned"), ("spent", "Spent")):
                button = QPushButton(label)
                button.setCheckable(True)
                button.setChecked(self._transaction_filter == key)
                button.setProperty("detailDisclosure", True)
                button.clicked.connect(
                    lambda _checked=False, selected=key, target=layout:
                    self._set_transaction_filter(selected, target)
                )
                filters.addWidget(button)
            filters.addStretch(1)
            layout.addLayout(filters)
        transactions = [
            transaction for transaction in all_transactions
            if self._transaction_filter == "all"
            or (self._transaction_filter == "earned" and int(transaction.delta) > 0)
            or (self._transaction_filter == "spent" and int(transaction.delta) < 0)
        ]
        visible = transactions if self._show_all_transactions else transactions[:8]
        if not visible:
            layout.addWidget(EmptyState(
                "No coin activity yet",
                "Earnings and purchases will appear here.",
            ))
        else:
            ledger = DataTable()
            ledger_grid = ledger.grid
            for column, heading in enumerate(("Source", "Change", "Balance")):
                header = self._label(heading, "detailTableHeader")
                if column >= 1:
                    header.setAlignment(Qt.AlignmentFlag.AlignRight)
                ledger_grid.addWidget(header, 0, column)
            for row, transaction in enumerate(visible, start=1):
                delta = int(transaction.delta)
                transaction_source = _currency_transaction_source(
                    transaction,
                    achievement_names,
                )
                source = self._label(
                    transaction_source or str(transaction.reason),
                    "detailBody",
                )
                amount = self._label(
                    f"{'+' if delta >= 0 else '−'}{abs(delta):,}",
                    "detailPositive" if delta >= 0 else "detailNegative",
                )
                apply_tabular_numerals(amount)
                amount.setAlignment(Qt.AlignmentFlag.AlignRight)
                resulting = self._label(f"{int(transaction.balance):,}", "detailBody")
                apply_tabular_numerals(resulting)
                resulting.setAlignment(Qt.AlignmentFlag.AlignRight)
                source.setAccessibleDescription(
                    f"{_transaction_date(transaction.occurred_at)}. {source.text()}"
                )
                for cell in (source, amount, resulting):
                    cell.setContentsMargins(4, 7, 4, 7)
                ledger_grid.addWidget(source, row, 0)
                ledger_grid.addWidget(amount, row, 1)
                ledger_grid.addWidget(resulting, row, 2)
            ledger_grid.setColumnStretch(0, 1)
            layout.addWidget(ledger)
        if len(transactions) > 8 and not self._show_all_transactions:
            view_all = QPushButton("View all activity")
            view_all.setProperty("detailDisclosure", True)
            view_all.setMinimumHeight(BUTTON_MIN_HEIGHT)

            def show_all() -> None:
                self._show_all_transactions = True
                self._clear_layout(layout)
                self._refresh_currency(layout)
                layout.addStretch(1)

            view_all.clicked.connect(show_all)
            layout.addWidget(view_all)

        self._disclosure(
            layout,
            "How to earn Garden Coins",
            [
                ("Earn", "Study rewards, plant stages, achievements, and some Garden Finds can award coins."),
                ("Spend", "Use Garden Coins for plants, Fertilizer, garden beds, and environments in the Nursery."),
            ],
            compact=True,
        )

    def _set_transaction_filter(self, selected: str, layout: QVBoxLayout) -> None:
        self._transaction_filter = selected if selected in {"all", "earned", "spent"} else "all"
        self._show_all_transactions = False
        self._clear_layout(layout)
        self._refresh_currency(layout)
        layout.addStretch(1)

    def _open_nursery(self) -> None:
        self.close()
        if callable(self.open_nursery):
            QTimer.singleShot(0, self.open_nursery)


class GardenProgressDialog(GardenDetailsDialog):
    """One responsive home for Growth, progress, rewards, and collection."""

    PAGE_LABELS = (
        ("growth", "Plant Growth"),
        ("streak", "Anki Streak"),
        ("currency", "Garden Coins"),
        ("achievements", "Achievements"),
        ("collection", "Collection"),
    )

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        storage: Any,
        open_nursery: Any,
        achievements: QWidget,
        collection: QWidget,
    ) -> None:
        super().__init__(parent, engine, storage, open_nursery)
        self.set_dialog_title("Garden Progress")
        self.dialog_subtitle.setText("")
        self.dialog_subtitle.hide()
        self.apply_size_policy(
            DialogSizeClass.PROGRESS,
        )

        metric_pages: dict[str, QWidget] = {}
        for key, _label in self.METRIC_TABS:
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if page is not None:
                metric_pages[key] = page
        self.remove_body_widget(self.tabs)
        self.tabs.hide()

        self.navigation = GardenSideNavigation()
        pages = {
            **metric_pages,
            "achievements": achievements,
            "collection": collection,
        }
        for key, label in self.PAGE_LABELS:
            page = pages.get(key)
            if page is not None:
                self.navigation.add_page(key, label, page)
        self.navigation.currentChanged.connect(self._page_changed)
        self.set_body_widget(self.navigation)
        self.navigation_responsive = AdaptiveSplit(
            "garden-progress.navigation",
            AdaptiveRegion.fixed(
                "section-navigation",
                160,
                target=self.navigation.rail,
            ),
            AdaptiveRegion.fixed(
                "progress-page",
                560,
                target=self.navigation.stack,
            ),
            spacing=16,
            apply_mode=lambda mode: self.navigation.set_compact(
                mode == COMPACT_MODE
            ),
            telemetry_target=self,
        )

        self.help_button = GardenIconButton("help", "How Growth works")
        self.help_button.clicked.connect(self._show_growth_help)
        self.header_layout.insertWidget(
            max(0, self.header_layout.count() - 1),
            self.help_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.nursery.hide()
        self.close_details.hide()
        self.footer.hide()
        self._last_valid_page = "growth"
        self.navigation.set_current("growth", emit=False)
        self._page_changed("growth")

    def _show_growth_help(self) -> None:
        QMessageBox.information(
            self,
            "How Growth Works",
            GROWTH_EXPLANATION,
        )
        QTimer.singleShot(0, self.help_button.setFocus)

    def _page_changed(self, key: str) -> None:
        if str(key) in self.navigation.keys:
            self._last_valid_page = str(key)
        self.set_dialog_title("Garden Progress")
        self.footer.hide()
        QTimer.singleShot(0, self._sync_footer_clearance)
        button = self.navigation.buttons.get(str(key))
        if button is not None:
            self.dialog_subtitle.setAccessibleDescription(
                f"Showing {button.text()} in Garden Progress."
            )
        self.apply_view_size_profile(self._view_profile_for_page(str(key)))

    def _view_profile_for_page(self, key: str) -> str:
        """Use the sparse Collection family only for a true empty result."""

        normalized = str(key)
        if normalized != "collection" or normalized not in self.navigation.keys:
            return normalized
        page = self.navigation.stack.widget(
            self.navigation.keys.index(normalized)
        )
        return (
            "collection-empty"
            if page is not None and bool(page.property("emptyResult"))
            else normalized
        )

    @staticmethod
    def _normalized_page(key: str | None, last_valid: str) -> str:
        requested = str(key or last_valid or "growth")
        if requested == "overview":
            return "growth"
        valid = {page for page, _label in GardenProgressDialog.PAGE_LABELS}
        return requested if requested in valid else "growth"

    def open_page(self, key: str | None = None) -> None:
        target = self._normalized_page(key, self._last_valid_page)
        self.refresh()
        self.navigation.set_current(target)
        self.present_over_parent()
        button = self.navigation.buttons.get(target) or self.navigation.buttons.get("growth")
        if button is not None:
            QTimer.singleShot(0, button.setFocus)

    def open_metric(self, metric: str) -> None:
        self.open_page(metric)

    def open_growth_charges(
        self,
        plant_id: str,
        invoker: QWidget | None = None,
    ) -> None:
        """Open Plant Growth and then its target-specific confirmation."""
        self.open_page("growth")
        QTimer.singleShot(
            0,
            lambda: self._open_growth_charge_dialog(plant_id, invoker),
        )

    def _sync_navigation_layout(self) -> None:
        if not hasattr(self, "navigation_responsive"):
            return
        content_width = max(
            0,
            int(self.body_region.width() or self.width())
            - self.body_layout.contentsMargins().left()
            - self.body_layout.contentsMargins().right(),
        )
        telemetry = self.navigation_responsive.evaluate(content_width)
        self.setProperty("navigationMode", telemetry.mode)

    def resizeEvent(self, event: Any) -> None:
        self._sync_navigation_layout()
        QTimer.singleShot(0, self._sync_navigation_layout)
        super().resizeEvent(event)


class CollectibleDetailDialog(GardenDialog):
    """Collection-owned loadout inspector with a reversible visual preview."""

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        storage: Any,
        snapshot_provider: Callable[[], dict[str, Any]],
    ) -> None:
        super().__init__(
            parent,
            "Garden appearance",
            subtitle="",
        )
        self.engine = engine
        self.storage = storage
        self.snapshot_provider = snapshot_provider
        self._draft_weather = DEFAULT_WEATHER_ID
        self._draft_scenery = DEFAULT_SCENERY_ID
        self._draft_decoration: str | None = None
        self._draft_visibility = {"weather": True, "scenery": True}
        self._persisted_draft: tuple[str, str, str | None, bool, bool] = (
            DEFAULT_WEATHER_ID,
            DEFAULT_SCENERY_ID,
            None,
            True,
            True,
        )
        self._tiles: dict[tuple[str, str], QPushButton] = {}
        self._persisted_weather = DEFAULT_WEATHER_ID
        self._persisted_scenery = DEFAULT_SCENERY_ID
        self._compact = False
        self._loadout_save_pending = False
        self._loadout_failure = False
        self.configure_close_policy(
            protect_dirty=True,
            protect_in_flight=True,
            confirm_dirty=self._confirm_discard_preview,
        )
        self.apply_size_policy(
            DialogSizeClass.LOADOUT,
        )
        self.setStyleSheet(_garden_dialog_stylesheet() + f"""
            QFrame[collectionLibrary='true'] {{ background:{GARDEN_THEME['raised_surface']}; border:0; border-radius:12px; }}
            QFrame[collectionPreview='true'] {{ background:#0a211b; border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:12px; }}
            QPushButton[environmentTile='true'] {{ min-height:132px; text-align:left; padding:8px; color:{GARDEN_THEME['text_primary']}; background:#102a22; border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:11px; }}
            QPushButton[environmentTile='true']:hover {{ background:#173b30; border-color:{GARDEN_THEME['strong_border']}; }}
            QPushButton[environmentTile='true']:checked {{ background:#173b30; border:2px solid {GARDEN_THEME['focus_ring']}; padding:9px; }}
            QPushButton[environmentTile='true']:disabled {{ color:{GARDEN_THEME['text_secondary']}; background:#10231f; border-color:#344b43; }}
            QLabel[environmentThumb='true'] {{ background:#071a15; border:0; border-radius:8px; color:{GARDEN_THEME['text_muted']}; }}
            QLabel[environmentName='true'] {{ color:{GARDEN_THEME['text_primary']}; font-size:14px; font-weight:650; }}
            QLabel[environmentState='true'] {{ color:{GARDEN_THEME['text_secondary']}; font-size:12.5px; }}
            QLabel[unsavedState='true'] {{ color:{GARDEN_THEME['coin_accent']}; font-size:13px; font-weight:650; }}
            QFrame[toastRegion='true'] {{ background:#17342e; border:1px solid #557665; border-radius:12px; }}
            QFrame[toastRegion='true'][error='true'] {{ background:#582f34; border-color:#a85b64; }}
            QLabel[toastIcon='true'] {{ color:#0b211a; background:#82e2ac; border:0; border-radius:10px; font-size:14px; font-weight:900; }}
            QLabel[toastIcon='true'][error='true'] {{ color:#3b1116; background:#ffd0d0; }}
        """)

        body = QWidget()
        self.main_grid = QGridLayout(body)
        self.main_grid.setContentsMargins(0, 0, 0, 0)
        self.main_grid.setHorizontalSpacing(16)
        self.main_grid.setVerticalSpacing(16)

        self.library = QFrame()
        self.library.setProperty("collectionLibrary", True)
        self.library.setMinimumWidth(0)
        self.library.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        library_layout = QVBoxLayout(self.library)
        library_layout.setContentsMargins(12, 10, 12, 12)
        library_layout.setSpacing(10)
        self.option_tabs = GardenTabs("Garden appearance categories")
        self.option_tabs.tabBar().setUsesScrollButtons(False)
        self.option_tabs.setStyleSheet("QTabBar::tab { padding-left:8px; padding-right:8px; }")
        self.scenery_page, self.scenery_grid = self._option_page("Scenery")
        self.weather_page, self.weather_grid = self._option_page("Weather")
        self.decoration_page, self.decoration_grid = self._option_page("Decorations")
        effects_host = QWidget()
        effects_layout = QVBoxLayout(effects_host)
        effects_layout.setContentsMargins(6, 10, 18, 10)
        effects_layout.setSpacing(14)
        effects_heading = QLabel("")
        effects_heading.hide()
        effects_heading.setProperty("dialogTitle", True)
        effects_intro = QLabel(
            "These settings only hide artwork."
        )
        effects_intro.setProperty("dialogSubtitle", True)
        effects_intro.setWordWrap(True)
        self.show_weather = ToggleSwitch("Weather effects")
        self.show_weather.setAccessibleName("Weather effects")
        self.show_scenery = ToggleSwitch("Scenery effects")
        self.show_scenery.setAccessibleName("Scenery effects")
        self.show_weather.toggled.connect(
            lambda enabled: self._set_draft_visibility("weather", enabled)
        )
        self.show_scenery.toggled.connect(
            lambda enabled: self._set_draft_visibility("scenery", enabled)
        )
        self.effects_advanced = SectionCard()
        self.effects_advanced_layout = QVBoxLayout(self.effects_advanced)
        self.effects_advanced_layout.setContentsMargins(12, 10, 12, 10)
        self.effects_advanced_layout.setSpacing(6)
        advanced_title = QLabel("")
        advanced_title.hide()
        advanced_title.setProperty("rowTitle", True)
        advanced_copy = QLabel("")
        advanced_copy.hide()
        advanced_copy.setProperty("dialogSubtitle", True)
        advanced_copy.setWordWrap(True)
        restore = QPushButton("Reset preview")
        restore.setAccessibleDescription(
            "Reset the preview to your saved garden appearance."
        )
        _set_button_variant(restore, BUTTON_VARIANT_SECONDARY)
        restore.clicked.connect(self._reset_preview)
        self.effects_advanced_layout.addWidget(advanced_title)
        self.effects_advanced_layout.addWidget(advanced_copy)
        self.effects_advanced_layout.addWidget(
            restore,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        effects_layout.addWidget(effects_heading)
        effects_layout.addWidget(effects_intro)
        effects_layout.addWidget(self.show_weather)
        effects_layout.addWidget(self.show_scenery)
        effects_layout.addWidget(self.effects_advanced)
        effects_layout.addStretch(1)
        self.effects_page = effects_host
        self.effects_page.setAccessibleName("Garden visual effects")
        self.option_tabs.addTab(self.scenery_page, "Scenery")
        self.option_tabs.addTab(self.weather_page, "Weather")
        self.option_tabs.addTab(self.decoration_page, "Decorations")
        self.option_tabs.addTab(self.effects_page, "Effects")
        self.set_initial_focus(
            self.option_tabs,
            InitialFocusPolicy.SELECTED_ROUTE,
        )
        self.option_tabs.currentChanged.connect(
            lambda _index: self.library.updateGeometry()
        )
        library_layout.addWidget(self.option_tabs, 1)

        self.preview_panel = QFrame()
        self.preview_panel.setProperty("collectionPreview", True)
        self.preview_panel.setMinimumWidth(0)
        self.preview_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_heading = QLabel("Preview")
        preview_heading.setProperty("dialogTitle", True)
        self.preview_selection = QLabel("")
        self.preview_selection.setProperty("dialogSubtitle", True)
        self.preview_selection.setWordWrap(True)
        self.preview_scene = GardenSceneWidget()
        self.preview_scene.set_interactive(False)
        self.preview_scene.setMinimumSize(0, 260)
        self.preview_scene.installEventFilter(self)
        self.preview_feedback = ToastRegion(self.preview_scene)
        self.preview_feedback.setAccessibleName("Garden appearance result")
        self.preview_feedback.shown.connect(self._position_preview_feedback)
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview_selection)
        preview_layout.addWidget(self.preview_scene, 1)

        self.main_grid.addWidget(self.library, 0, 0)
        self.main_grid.addWidget(self.preview_panel, 0, 1)
        self.main_grid.setColumnStretch(0, 3)
        self.main_grid.setColumnStretch(1, 5)
        self.body_scroll = QScrollArea()
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body_scroll.setAccessibleName("Garden appearance")
        self.body_scroll.setWidget(body)
        _set_scroll_surface(
            self.body_scroll,
            body,
            GARDEN_THEME["dialog_surface"],
        )
        self.set_body_widget(self.body_scroll)
        self.collection_detail_responsive = AdaptiveSplit(
            "collection-loadout.workspace",
            AdaptiveRegion.measured(
                "appearance-library",
                self.library,
                floor=320,
            ),
            AdaptiveRegion.measured(
                "garden-preview",
                self.preview_panel,
                floor=480,
            ),
            spacing=16,
            apply_mode=self._apply_detail_layout_mode,
            telemetry_target=self,
        )

        self.unsaved = QLabel("")
        self.unsaved.setProperty("unsavedState", True)
        self.unsaved.setAccessibleName("Garden appearance save status")
        self.unsaved.setWordWrap(True)
        self.unsaved.setMargin(8)
        self.unsaved.hide()
        self.footer_layout.addWidget(self.unsaved, 1)
        self.cancel_preview = QPushButton("Cancel")
        _set_button_variant(self.cancel_preview, BUTTON_VARIANT_SECONDARY)
        self.cancel_preview.clicked.connect(self._cancel_preview)
        self.apply_changes = QPushButton("Save")
        _set_button_variant(self.apply_changes, BUTTON_VARIANT_PRIMARY)
        self.apply_changes.clicked.connect(self._apply_draft)
        self.footer_layout.addWidget(self.cancel_preview)
        self.footer_layout.addWidget(self.apply_changes)
        self._loadout_footer_compact: bool | None = None
        self.loadout_footer_responsive = AdaptiveRow(
            "collection-loadout.actions",
            (
                AdaptiveRegion.measured("status", self.unsaved, floor=220),
                AdaptiveRegion.measured(
                    "discard-or-cancel",
                    self.cancel_preview,
                    floor=150,
                ),
                AdaptiveRegion.measured(
                    "apply-or-retry",
                    self.apply_changes,
                    floor=140,
                ),
            ),
            spacing=8,
            apply_mode=self._set_loadout_footer_mode,
            telemetry_target=self.footer,
        )
        self.footer.show()
        self.prepare_to_show()
        self.apply_view_size_profile("default")
        QTimer.singleShot(0, self._sync_preview_scene_geometry)

    def _position_preview_feedback(self) -> None:
        """Keep appearance feedback inside the scene without consuming layout."""

        if not self.preview_feedback.isVisible():
            return
        inset = 12
        available_width = max(1, self.preview_scene.width() - (inset * 2))
        toast_width = min(420, available_width)
        toast_height = min(
            84,
            max(44, self.preview_feedback.sizeHint().height()),
        )
        x = max(inset, (self.preview_scene.width() - toast_width) // 2)
        self.preview_feedback.setGeometry(
            x,
            inset,
            toast_width,
            toast_height,
        )
        self.preview_feedback.raise_()

    def _sync_preview_scene_geometry(self) -> None:
        """Choose the complete 16:9 garden variant instead of cropping its beds."""

        available_width = max(
            0,
            self.preview_panel.contentsRect().width() - 24,
        )
        if available_width < 80:
            return
        target_height = max(260, min(420, round(available_width * 9 / 16)))
        if (
            self.preview_scene.minimumHeight() != target_height
            or self.preview_scene.maximumHeight() != target_height
        ):
            self.preview_scene.setMinimumHeight(target_height)
            self.preview_scene.setMaximumHeight(target_height)
        self._position_preview_feedback()

    def _show_preview_feedback(
        self,
        message: str,
        *,
        tone: FeedbackTone,
        duration_ms: int = 2400,
    ) -> None:
        error = tone is FeedbackTone.ERROR
        self.preview_feedback.show_message(
            message,
            duration_ms=0 if error else duration_ms,
            error=error,
            dismissible=error,
        )
        self._position_preview_feedback()

    def _set_loadout_footer_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact != self._loadout_footer_compact:
            self._loadout_footer_compact = compact
            self.footer_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact else
                QBoxLayout.Direction.LeftToRight
            )
            self.footer_layout.setAlignment(
                Qt.AlignmentFlag.AlignTop
                if compact else
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self._sync_loadout_footer_button_geometry()
        self.unsaved.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.footer_layout.invalidate()
        self.footer_layout.activate()
        self.footer.updateGeometry()

    def _sync_loadout_footer_button_geometry(self) -> None:
        """Re-measure state-dependent action copy without stretching it."""

        for button in (self.cancel_preview, self.apply_changes):
            copy_width = int(
                button.fontMetrics().horizontalAdvance(
                    str(button.text()).replace("&&", "&")
                )
            )
            target_width = max(96, min(220, copy_width + 40))
            button.setMinimumWidth(target_width)
            button.setMaximumWidth(target_width)
            button.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )

    def _option_page(self, accessible_name: str) -> tuple[QWidget, QGridLayout]:
        host = QWidget()
        host.setAccessibleName(f"{accessible_name} options")
        grid = QGridLayout(host)
        grid.setContentsMargins(4, 6, 4, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        return host, grid

    def _apply_detail_layout_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._compact:
            return
        self._compact = compact
        self.main_grid.removeWidget(self.library)
        self.main_grid.removeWidget(self.preview_panel)
        for column in range(2):
            self.main_grid.setColumnStretch(column, 0)
        for row in range(2):
            self.main_grid.setRowStretch(row, 0)
        if compact:
            # Keep source, focus, and visual reading order aligned: choose an
            # appearance first, then review its garden preview.
            self.main_grid.addWidget(self.library, 0, 0)
            self.main_grid.addWidget(self.preview_panel, 1, 0)
            self.main_grid.setColumnStretch(0, 1)
            self.main_grid.setRowStretch(0, 0)
            self.main_grid.setRowStretch(1, 1)
            self.library.setMinimumWidth(0)
            self.library.setMaximumWidth(16777215)
        else:
            self.main_grid.addWidget(self.library, 0, 0)
            self.main_grid.addWidget(self.preview_panel, 0, 1)
            self.main_grid.setColumnStretch(0, 3)
            self.main_grid.setColumnStretch(1, 5)
            self.main_grid.setRowStretch(0, 1)
            self.library.setMinimumWidth(300)
            self.library.setMaximumWidth(330)
        self.library.setMinimumHeight(0)
        self.preview_panel.setMinimumHeight(0)
        body = self.body_scroll.widget()
        if body is not None:
            body.setMinimumHeight(0)
            body.updateGeometry()
        QTimer.singleShot(0, self._sync_preview_scene_geometry)

    @staticmethod
    def _clear_grid(grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _asset_payload(asset: Any) -> Any:
        if asset is None:
            return None
        converter = getattr(asset, "to_payload", None)
        return converter() if callable(converter) else {"path": str(getattr(asset, "path", ""))}

    def _thumbnail(self, item: CatalogItem) -> QLabel:
        label = QLabel()
        label.setFixedSize(112, 68)
        label.setProperty("environmentThumb", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(f"{item.name} preview")
        available = False
        try:
            resolver = (
                self.engine.resolve_weather_preview_asset
                if item.kind == "weather"
                else self.engine.resolve_scenery_preview_asset
            )
            resolved = resolver(item.item_id)
            path = getattr(resolved, "path", None)
            available = bool(path and not _preview_source_pixmap(path).isNull())
        except Exception:
            logger.exception(
                "Anki Garden: Collection artwork resolution failed for %s",
                item.item_id,
            )
        label.setPixmap(_environment_preview_pixmap(
            self.engine,
            item,
            112,
            68,
            scenery_id=self._draft_scenery,
        ))
        if not available:
            set_semantic_role(label, SemanticRole.MISSING_ART)
            label.setAccessibleDescription(
                f"Artwork unavailable for {item.name}; a {item.kind} placeholder is shown."
            )
            label.setToolTip(f"{item.name} artwork unavailable")
        return label

    def _option_tile(self, item: CatalogItem) -> QPushButton:
        owned = self.engine.owns_environment(item.kind, item.item_id)
        equipped = (
            self._persisted_weather == item.item_id
            if item.kind == "weather" else
            self._persisted_scenery == item.item_id
        )
        selected = (
            self._draft_weather == item.item_id
            if item.kind == "weather" else
            self._draft_scenery == item.item_id
        )
        tile = QPushButton()
        tile.setProperty("environmentTile", True)
        tile.setCheckable(owned)
        tile.setChecked(selected)
        tile.setCursor(
            Qt.CursorShape.PointingHandCursor if owned else Qt.CursorShape.ArrowCursor
        )
        tile.setAccessibleName(f"{item.name}, {item.kind}")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        layout.addWidget(self._thumbnail(item), 0, Qt.AlignmentFlag.AlignHCenter)
        name = QLabel(item.name)
        name.setProperty("environmentName", True)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setMinimumWidth(0)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        state_text = (
            "Equipped" if equipped and selected else
            "Equipped" if equipped else
            "Previewing" if selected else
            ""
        )
        state = QLabel(state_text)
        state.setProperty("environmentState", True)
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state.setWordWrap(True)
        state.setVisible(bool(state_text))
        state.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(name)
        layout.addWidget(state)
        effect_copy = str(item.effect or "").strip()
        if effect_copy.casefold() == "no gameplay bonus.":
            effect_copy = ""
        tile.setAccessibleDescription(" ".join(
            part for part in (
                f"{item.name}.",
                f"{state_text}." if state_text else "",
                effect_copy if owned else item.how_to_earn,
            )
            if part
        ))
        set_control_enabled(
            tile,
            owned,
            disabled_reason=f"{item.name} is locked. {item.how_to_earn}",
            enabled_description=tile.accessibleDescription(),
        )
        if owned:
            tile.clicked.connect(
                lambda _checked=False, kind=item.kind, item_id=item.item_id:
                self._select_option(kind, item_id)
            )
        self._tiles[(item.kind, item.item_id)] = tile
        return tile

    def _browse_nursery_empty_state(self, category: str) -> EmptyState:
        browse = QPushButton("Open Nursery")
        _set_button_variant(browse, BUTTON_VARIANT_SECONDARY)
        browse.clicked.connect(self._browse_nursery)
        return EmptyState(
            f"No other {str(category).strip().lower()}.",
            "",
            action=browse,
        )

    def _browse_nursery(self) -> None:
        self.close()
        parent = self.parentWidget()
        opener = getattr(parent, "_open_nursery", None)
        if callable(opener):
            QTimer.singleShot(0, opener)

    def _rebuild_options(self) -> None:
        self._clear_grid(self.scenery_grid)
        self._clear_grid(self.weather_grid)
        self._clear_grid(self.decoration_grid)
        self._tiles.clear()
        for kind, grid, catalog in (
            (
                "scenery",
                self.scenery_grid,
                SCENERY_CATALOG,
            ),
            (
                "weather",
                self.weather_grid,
                WEATHER_CATALOG,
            ),
        ):
            owned_items = [
                item for item in catalog.values()
                if self.engine.owns_environment(item.kind, item.item_id)
            ]
            for index, item in enumerate(owned_items):
                grid.addWidget(self._option_tile(item), index // 2, index % 2)
            if len(owned_items) <= 1:
                grid.addWidget(
                    self._browse_nursery_empty_state(kind),
                    (len(owned_items) + 1) // 2,
                    0,
                    1,
                    2,
                )
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setRowStretch((len(owned_items) + 2) // 2, 1)
        decoration_options = [
            (item_id, name)
            for item_id, name in ((None, "No decoration"), ("lantern", "Garden Lantern"))
            if item_id is None or item_id in self.storage.state.inventory.get("decorations", [])
        ]
        for index, (item_id, name) in enumerate(decoration_options):
            owned = item_id is None or item_id in self.storage.state.inventory.get("decorations", [])
            persisted_decoration = self._persisted_draft[2]
            selected = self._draft_decoration == item_id
            equipped = persisted_decoration == item_id
            state_text = (
                "Equipped"
                if equipped and selected
                else "Equipped"
                if equipped
                else "Previewing"
                if selected
                else ""
            )
            button = QPushButton(
                f"{name} · {state_text}" if state_text else name
            )
            button.setCheckable(True)
            button.setChecked(selected)
            button.setAccessibleDescription(
                f"{name}. {state_text}." if state_text else f"{name}."
            )
            set_control_enabled(
                button,
                owned,
                disabled_reason=f"{name} is locked.",
                enabled_description=button.accessibleDescription(),
            )
            if owned:
                button.clicked.connect(
                    lambda _checked=False, selected=item_id: self._select_decoration(selected)
                )
            self.decoration_grid.addWidget(button, index, 0, 1, 2)
        if len(decoration_options) <= 1:
            self.decoration_grid.addWidget(
                self._browse_nursery_empty_state("decorations"),
                len(decoration_options),
                0,
                1,
                2,
            )
        self.decoration_grid.setColumnStretch(0, 1)

    def prepare_to_show(self) -> None:
        state = self.storage.state
        self._loadout_save_pending = False
        self._loadout_failure = False
        self.set_dialog_in_flight(False)
        self.setProperty("transactionState", "ready")
        self.preview_feedback.clear()
        self._draft_weather = str(state.selected_weather)
        self._draft_scenery = str(state.selected_background)
        self._draft_decoration = state.loadout.decoration_id
        self._persisted_weather = self._draft_weather
        self._persisted_scenery = self._draft_scenery
        self._draft_visibility = {
            "weather": bool(state.environment_visibility.get("weather", True)),
            "scenery": bool(state.environment_visibility.get("scenery", True)),
        }
        self._persisted_draft = self._draft_key()
        self.show_weather.blockSignals(True)
        self.show_scenery.blockSignals(True)
        self.show_weather.setChecked(self._draft_visibility["weather"])
        self.show_scenery.setChecked(self._draft_visibility["scenery"])
        self.show_weather.blockSignals(False)
        self.show_scenery.blockSignals(False)
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()

    def _draft_key(self) -> tuple[str, str, str | None, bool, bool]:
        return (
            self._draft_weather,
            self._draft_scenery,
            self._draft_decoration,
            self._draft_visibility["weather"],
            self._draft_visibility["scenery"],
        )

    def _select_option(self, kind: str, item_id: str) -> None:
        self.preview_feedback.clear()
        if kind == "weather":
            self._draft_weather = str(item_id)
        else:
            self._draft_scenery = str(item_id)
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()

    def _set_draft_visibility(self, kind: str, enabled: bool) -> None:
        self.preview_feedback.clear()
        self._draft_visibility[str(kind)] = bool(enabled)
        self._refresh_preview()
        self._sync_dirty_state()

    def _select_decoration(self, item_id: str | None) -> None:
        self.preview_feedback.clear()
        self._draft_decoration = item_id
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()

    def _reset_preview(self) -> None:
        (
            self._draft_weather,
            self._draft_scenery,
            self._draft_decoration,
            weather_visible,
            scenery_visible,
        ) = self._persisted_draft
        self._draft_visibility = {
            "weather": bool(weather_visible),
            "scenery": bool(scenery_visible),
        }
        self.show_weather.blockSignals(True)
        self.show_scenery.blockSignals(True)
        self.show_weather.setChecked(self._draft_visibility["weather"])
        self.show_scenery.setChecked(self._draft_visibility["scenery"])
        self.show_weather.blockSignals(False)
        self.show_scenery.blockSignals(False)
        self._loadout_failure = False
        self.preview_feedback.clear()
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()
        self._show_preview_feedback(
            "Preview reset.",
            tone=FeedbackTone.INFO,
        )

    def _restore_default_draft(self) -> None:
        """Compatibility alias for older callers; reset means saved appearance."""

        self._reset_preview()

    def _sync_dirty_state(self) -> None:
        dirty = self._draft_key() != self._persisted_draft
        self.set_dialog_dirty(dirty)
        if not self._loadout_save_pending and not self._loadout_failure:
            self.setProperty("transactionState", "ready")
            self.setProperty(
                "transactionPresentation",
                "preview" if dirty else "committed-state",
            )
        set_control_enabled(
            self.apply_changes,
            dirty and not self._loadout_save_pending,
            disabled_reason=(
                "Appearance changes are being saved."
                if self._loadout_save_pending
                else "Garden appearance is already saved."
            ),
            enabled_description=(
                "Try saving the garden appearance again."
                if self._loadout_failure
                else "Save the garden appearance."
            ),
        )
        set_control_enabled(
            self.cancel_preview,
            not self._loadout_save_pending,
            disabled_reason="Appearance changes are being saved.",
            enabled_description=(
                "Discard these changes and keep the current garden appearance."
                if self._loadout_failure
                else "Close without saving changes."
            ),
        )
        self.apply_changes.setText(
            "Saving…"
            if self._loadout_save_pending
            else "Try again"
            if self._loadout_failure
            else "Save"
        )
        self.cancel_preview.setText(
            "Discard changes" if self._loadout_failure else "Cancel"
        )
        self._sync_loadout_footer_button_geometry()
        status_text = (
            "Saving appearance changes…"
            if self._loadout_save_pending
            else ""
        )
        self.unsaved.setText(status_text)
        self.unsaved.setAccessibleDescription(
            status_text
            if self._loadout_failure or self._loadout_save_pending
            else "Garden appearance has unsaved changes."
            if dirty
            else ""
        )
        self.unsaved.setVisible(bool(status_text))
        if status_text:
            tone = (
                FeedbackTone.INFO
                if self._loadout_save_pending
                else FeedbackTone.WARNING
            )
            set_semantic_role(self.unsaved, SemanticRole.BANNER, tone=tone)

    def _refresh_preview(self) -> None:
        snapshot = dict(self.snapshot_provider() or {})
        scenery_id = (
            self._draft_scenery
            if self._draft_visibility["scenery"] else
            DEFAULT_SCENERY_ID
        )

        def resolve_preview_asset(
            label: str,
            resolver_name: str,
            *args: Any,
        ) -> Any:
            try:
                resolver = getattr(self.engine, resolver_name)
                return resolver(*args)
            except Exception:
                logger.exception(
                    "Anki Garden: Collection preview artwork resolution failed for %s",
                    label,
                )
                return None

        background = resolve_preview_asset(
            f"scenery {scenery_id}",
            "resolve_scenery_preview_asset",
            scenery_id,
        )
        weather = (
            resolve_preview_asset(
                f"weather {self._draft_weather}",
                "resolve_weather_preview_asset",
                self._draft_weather,
            )
            if self._draft_visibility["weather"] else None
        )
        overlay = resolve_preview_asset(
            "garden overlay",
            "resolve_garden_overlay_asset",
        )
        nurtured_marker = resolve_preview_asset(
            "nurtured marker",
            "resolve_nurtured_marker_asset",
        )
        nurtured_marker_spout_right = resolve_preview_asset(
            "right-facing nurtured marker",
            "resolve_nurtured_marker_spout_right_asset",
        )
        decoration = (
            resolve_preview_asset(
                f"decoration {self._draft_decoration}",
                "resolve_decoration_asset",
                self._draft_decoration,
            )
            if self._draft_decoration else None
        )
        plants = []
        for row in snapshot.get("plants", []):
            plant = dict(row)
            try:
                plant["asset"] = self._asset_payload(
                    self.engine.resolve_plant_asset(
                        str(plant.get("species") or "bonsai"),
                        str(plant.get("stage") or "seed"),
                    )
                )
            except Exception:
                plant["asset"] = None
            plants.append(plant)
        self.preview_scene.set_scene({
            **snapshot,
            "weather": self._draft_weather,
            "theme": str(self.engine.config.value("visual_theme", "verdant_twilight")),
            "show_status_overlay": False,
            "motion_enabled": False,
            "asset_paths": {
                "background": self._asset_payload(background),
                "garden_overlay": self._asset_payload(overlay),
                "nurtured_marker": self._asset_payload(nurtured_marker),
                "nurtured_marker_spout_right": self._asset_payload(
                    nurtured_marker_spout_right
                ),
                "weather": self._asset_payload(weather),
                "decoration": self._asset_payload(decoration),
            },
            "plants": plants,
        })
        weather_item = WEATHER_CATALOG.get(self._draft_weather)
        scenery_item = SCENERY_CATALOG.get(self._draft_scenery)
        weather_name = (
            weather_item.name
            if weather_item is not None
            else f"{format_status_label(self._draft_weather)} (Unavailable)"
        )
        scenery_name = (
            scenery_item.name
            if scenery_item is not None
            else f"{format_status_label(self._draft_scenery)} (Unavailable)"
        )
        decoration_name = (
            "Garden Lantern"
            if self._draft_decoration == "lantern"
            else "No decoration"
            if self._draft_decoration is None
            else f"{format_status_label(self._draft_decoration)} (Unavailable)"
        )
        previewing = self._draft_key() != self._persisted_draft
        self.preview_selection.setText(
            f"{scenery_name} · {weather_name} · {decoration_name}"
        )
        self.preview_selection.setAccessibleDescription(
            f"{'Previewing' if previewing else 'Equipped'}. {scenery_name} scenery with {weather_name} weather and {decoration_name}."
        )

    def _apply_draft(self) -> None:
        if self._loadout_save_pending:
            return
        self._loadout_save_pending = True
        self.set_dialog_in_flight(True)
        self.setProperty("transactionState", "committing")
        self.setProperty("transactionPresentation", "preview-being-committed")
        self._sync_dirty_state()
        try:
            ok, _message = self.engine.apply_garden_loadout(
                self._draft_weather,
                self._draft_scenery,
                self._draft_decoration,
                self._draft_visibility,
            )
        except Exception:
            logger.exception("Anki Garden: Collection loadout save failed unexpectedly")
            ok = False
        finally:
            self._loadout_save_pending = False
            self.set_dialog_in_flight(False)
        if not ok:
            self._loadout_failure = True
            self.setProperty("transactionState", "persistence-failure")
            self.setProperty("transactionPresentation", "committed-state-unchanged")
            self._sync_dirty_state()
            failure_copy = "Couldn’t save changes. Your garden is unchanged."
            self._show_preview_feedback(
                failure_copy,
                tone=FeedbackTone.ERROR,
            )
            self.preview_feedback.setFocus()
            self.accessibility_announcer.announce(
                self.preview_feedback.accessibleDescription(),
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.preview_feedback,
            )
            return
        self._loadout_failure = False
        self._persisted_draft = self._draft_key()
        self._persisted_weather = self._draft_weather
        self._persisted_scenery = self._draft_scenery
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()
        self.setProperty("transactionState", "success")
        self.setProperty("transactionPresentation", "committed-result")
        self.unsaved.clear()
        self.unsaved.hide()
        self._show_preview_feedback(
            "Garden appearance saved.",
            tone=FeedbackTone.SUCCESS,
        )
        self.accessibility_announcer.announce(
            self.preview_feedback.accessibleDescription(),
            target=self.preview_feedback,
        )
        parent = self.parentWidget()
        refresh = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh):
            refresh("environment loadout")
        QTimer.singleShot(
            2400,
            self._clear_loadout_save_status,
        )

    def _clear_loadout_save_status(self) -> None:
        if self._draft_key() != self._persisted_draft:
            return
        self.unsaved.clear()
        self.unsaved.setAccessibleDescription("")
        self.unsaved.hide()
        self.preview_feedback.clear()

    def open_item(self, category: str, item_id: str) -> None:
        """Open from a Collection card with that owned item selected for preview."""

        self.prepare_to_show()
        if category == "weather" and self.engine.owns_environment(category, item_id):
            self._draft_weather = item_id
            self.option_tabs.setCurrentWidget(self.weather_page)
        elif category == "scenery" and self.engine.owns_environment(category, item_id):
            self._draft_scenery = item_id
            self.option_tabs.setCurrentWidget(self.scenery_page)
        elif category == "decorations" and item_id in self.storage.state.inventory.get("decorations", []):
            self._draft_decoration = item_id
            self.option_tabs.setCurrentWidget(self.decoration_page)
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()
        self.present_over_parent()

    def _confirm_discard_preview(self, _reason: DialogCloseReason) -> bool:
        if self._draft_key() == self._persisted_draft:
            return True
        answer = QMessageBox.question(
            self,
            "Discard changes?",
            "Your garden appearance was not saved.",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _cancel_preview(self) -> None:
        if self._loadout_failure:
            self._reset_preview()
            self.request_close(DialogCloseReason.CANCEL_ACTION)
            return
        if self.request_close(DialogCloseReason.CANCEL_ACTION):
            self.prepare_to_show()

    def resizeEvent(self, event: Any) -> None:
        margins = self._shell_layout.contentsMargins()
        content_width = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "collection_detail_responsive"):
            telemetry = self.collection_detail_responsive.evaluate(content_width)
            self.setProperty("workspaceMode", telemetry.mode)
        if hasattr(self, "loadout_footer_responsive"):
            footer = self.loadout_footer_responsive.evaluate(content_width)
            self.setProperty("footerMode", footer.mode)
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_preview_scene_geometry)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if (
            watched is getattr(self, "preview_scene", None)
            and event.type() in (QEvent.Type.Resize, QEvent.Type.Show)
        ):
            QTimer.singleShot(0, self._sync_preview_scene_geometry)
        return super().eventFilter(watched, event)

class GardenDashboard(DialogShell):
    ROOT_MARGINS = (12, 12, 12, 12)
    ROOT_SPACING = 12
    CARD_SPACING = 8
    CARD_PADDING = (10, 10, 10, 10)
    CARD_BORDER_RADIUS = 14
    CHIP_BORDER_RADIUS = 12
    CHIP_PADDING = (5, 10)
    CHIP_SPACING = 8
    MID_ROW_SPACING = 12
    CARD_BG = GARDEN_THEME["raised_surface"]
    CARD_BORDER = GARDEN_THEME["subtle_border"]
    APP_BG = GARDEN_THEME["garden_background"]
    TEXT_PRIMARY = GARDEN_THEME["text_primary"]
    TEXT_MUTED = GARDEN_THEME["text_muted"]
    CHIP_BG = GARDEN_THEME["selected_surface"]
    LIST_ELIDE_WIDTH = 340
    LIST_MAX_LENGTH = 170
    MIN_WINDOW_WIDTH = 620
    MIN_WINDOW_HEIGHT = 520
    DEFAULT_WINDOW_WIDTH = 1240
    DEFAULT_WINDOW_HEIGHT = 840
    ONBOARDING_COACHMARK_MIN_WIDTH = 320
    ONBOARDING_COACHMARK_MAX_WIDTH = 360

    def __init__(
        self,
        mw_window: Any,
        engine: Any,
        storage: Any,
        config: Any,
        coordinator: GardenUiCoordinator | None = None,
        starter_selected_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(mw_window)
        self.engine = engine
        self.storage = storage
        self.config = config
        self.mw_window = mw_window
        self._system_reduced_motion = read_system_reduced_motion()
        self.state_events = coordinator or GardenUiCoordinator(self)
        self.state_events.stateChanged.connect(self._on_state_changed)
        self._starter_selected_callback = starter_selected_callback
        self._collection_activation_pending = False
        self.settings_dialog: GardenSettingsDialog | None = None
        self.nursery_dialog: NurseryDialog | None = None
        self.story_dialog: PlantStoryDialog | None = None
        self.fertilizer_dialog: DialogShell | None = None
        self._fertilizer_purchase_pending = False
        self._undo_nurture_plant_id = ""
        self._starter_prompt_scheduled = False
        self._starter_setup_dismissed = False
        self._starter_confirmation_pending = False
        self._undo_placement: Any = None
        self._placement_draft: Any = None
        self._active_placement_token: int | None = None
        self._failed_move_destination: int | None = None
        self._move_focus_return: QWidget | None = None
        self._move_focus_plant_id = ""
        self._starter_placement_active = False
        self._collection_placement_plant_id = ""
        self._stage_message_generation = 0
        self._pending_feedback_ack_ids: tuple[str, ...] = ()
        self._pending_transition_ack: tuple[Any, ...] = ()
        self._onboarding_just_completed = False
        self._onboarding_confirmation_generation = 0
        self._onboarding_save_error = ""
        self._last_onboarding_error_announcement = ""
        self._starter_confirmation_message = ""
        self._onboarding_plant_id = ""
        self._onboarding_focus_return: QWidget | None = None
        self._compact_layout: bool | None = None
        self._header_compact_layout: bool | None = None
        self._header_narrow_layout: bool | None = None
        self._header_metrics_compact: bool | None = None
        self._rearrange_compact_layout: bool | None = None
        self._application_filter_installed = False
        self._skip_next_show_refresh = False
        self._home_surface_dirty = False
        self.setWindowTitle(UI_TEXT["app_title"])
        self.accessibility_announcer = AccessibilityAnnouncer(self)
        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(*self._recommended_window_size())
        self._build_ui()
        self._apply_responsive_layout(self._dashboard_content_width())
        self._fertilizer_timer = QTimer(self)
        self._fertilizer_timer.setInterval(1_000)
        self._fertilizer_timer.timeout.connect(self._refresh_timed_plant_statuses)
        self._fertilizer_timer.start()
        self._install_application_filter()
        QTimer.singleShot(0, self._update_scene_height)

    def _install_application_filter(self) -> None:
        application = QGuiApplication.instance()
        if application is not None and not self._application_filter_installed:
            application.installEventFilter(self)
            self._application_filter_installed = True

    def showEvent(self, event: Any) -> None:
        self._install_application_filter()
        if not self._fertilizer_timer.isActive():
            self._fertilizer_timer.start()
        super().showEvent(event)
        if self._skip_next_show_refresh:
            self._skip_next_show_refresh = False
        else:
            self.refresh_all()

    def prepare_to_show(self) -> None:
        """Refresh exactly once before either showing or raising the Garden."""
        # The opener acknowledges one-shot messages only after show/raise
        # succeeds. A failed window open must not discard unseen feedback.
        USER_NOTICES.clear(key="display_refresh")
        try:
            self.refresh_all(acknowledge=False)
        except Exception:
            USER_NOTICES.publish(
                "Your garden progress is safe, but the display could not refresh. "
                "Reopen Anki Garden to try again.",
                key="display_refresh",
            )
            raise
        self._skip_next_show_refresh = not self.isVisible()

    def _present_starter_setup_if_needed(self) -> None:
        """Refresh first-run guidance without opening a modal or naming gate."""

        if self.storage.state.onboarding.step != OnboardingStep.DONE:
            self._refresh_onboarding()

    def _derived_ux_state(self) -> str:
        """Derive newcomer presentation from saved gameplay state only."""

        state = self.storage.state
        plants = list(getattr(state, "plants", []) or [])
        if plants and all(bool(getattr(plant, "fully_grown", False)) for plant in plants):
            return UX_NURTURED_PLANT_COMPLETE
        display = onboarding_state_display(
            state,
            self.config.value("onboarding_version", 0),
        )
        if display.state == OnboardingState.NO_STARTER:
            return UX_NO_STARTER
        if display.state in {
            OnboardingState.STARTER_SELECTED,
            OnboardingState.STARTER_PLANTED_NOT_NURTURED,
        }:
            return UX_STARTER_READY
        return UX_ACTIVE_GROWTH

    def _recommended_window_size(self) -> tuple[int, int]:
        screen = (self.parent().screen() if self.parent() is not None and hasattr(self.parent(), "screen") else None) or self.screen()
        if screen is None:
            return self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT
        available = screen.availableGeometry()
        width = min(self.DEFAULT_WINDOW_WIDTH, max(self.MIN_WINDOW_WIDTH, int(available.width() * 0.92)))
        height = min(self.DEFAULT_WINDOW_HEIGHT, max(self.MIN_WINDOW_HEIGHT, int(available.height() * 0.9)))
        return width, height

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget[gardenDialogShell='true'] {{ background: {self.APP_BG}; color: {self.TEXT_PRIMARY}; }}
            QWidget#gardenDashboardPage {{ background:{self.APP_BG}; }}
            QFrame[card='true'] {{ background:transparent; border:0; }}
            QFrame[topBar='true'] {{ background:transparent; border:0; }}
            QFrame[actionBar='true'] {{ background:#0d211e; border-top:1px solid #345348; border-radius:10px; }}
            QFrame[plantCard='true'] {{ background:#0C261F; border:1px solid #4F806E; border-radius:12px; }}
            QFrame[plantCardDock='true'] {{ background:transparent; border:0; }}
            QFrame[transientFeedback='true'] {{ background:transparent; border:0; }}
            QFrame[toastRegion='true'] {{ background:#17342e; border:1px solid #557665; border-radius:12px; }}
            QFrame[toastRegion='true'][error='true'] {{ background:#582f34; border-color:#a85b64; }}
            QLabel[toastIcon='true'] {{ color:#0b211a; background:#82e2ac; border:0; border-radius:12px; font-size:15px; font-weight:900; }}
            QLabel[toastIcon='true'][error='true'] {{ color:#3b1116; background:#ffd0d0; }}
            QLabel[plantPopoverArtwork='true'] {{ background:#123228; border:0; border-radius:10px; color:#B8C5BF; font-size:24px; }}
            QLabel[plantCardHeading='true'] {{ color:#F4F7F5; font-size:18px; font-weight:700; }}
            QLabel[plantStageBadge='true'] {{ color:#B8C5BF; background:#123228; border:0; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; letter-spacing:.5px; }}
            QLabel[fertilizedBadge='true'] {{ color:#d8ecff; background:#18384a; border:1px solid #5686a0; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; }}
            QLabel[fullyGrownBadge='true'] {{ color:#f3dda0; background:#3a3220; border:1px solid #817044; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; }}
            QLabel[plantCardSection='true'] {{ color:#d8b875; font-size:12px; font-weight:800; letter-spacing:1px; padding-top:3px; }}
            QLabel[plantProgressLabel='true'] {{ color:#aac0b1; font-size:13px; }}
            QLabel[plantGrowthValue='true'] {{ color:#f5f7e8; font-size:26px; font-weight:800; }}
            QFrame[plantStatus='true'] {{ background:#17312b; border:0; border-radius:8px; padding:7px 9px; }}
            QFrame[plantCard='true'] QPushButton {{ min-height:{PLANT_ACTION_MIN_HEIGHT}px; }}
            QLabel[plantStatusLabel='true'] {{ color:#91aa9b; font-size:12px; font-weight:800; letter-spacing:.8px; }}
            QLabel[plantStatusValue='true'] {{ color:#e9d9ac; font-size:13px; font-weight:700; }}
            QFrame[plantGuidance='true'] {{ background:#123228; border:0; border-left:3px solid #5CC58B; border-radius:8px; }}
            QLabel[plantGuidanceStep='true'] {{ color:#82E2AC; font-size:12px; font-weight:700; letter-spacing:.8px; }}
            QLabel[plantGuidanceText='true'] {{ color:#CBD6D0; font-size:13px; }}
            QFrame[plantCard='true'] QPushButton[plantActionRole='primary'] {{ min-height:34px; max-height:34px; }}
            QFrame[plantCard='true'] QPushButton[plantActionRole='boost'] {{ min-height:32px; max-height:32px; }}
            QFrame[plantCard='true'] QPushButton[plantActionRole='tertiary'] {{ min-height:30px; max-height:30px; }}
            QFrame[movePanel='true'] {{ background:rgba(12,38,31,235); border:1px solid #4F806E; border-radius:10px; }}
            QFrame[movePanel='true'][error='true'] {{ background:rgba(66,34,36,242); border:2px solid #c8787f; }}
            QFrame[gardenStats='true'] {{ background:#0C261F; border:1px solid {self.CARD_BORDER}; border-radius:10px; }}
            QPushButton[gardenStatCell='true'] {{ min-height:54px; max-height:54px; text-align:left; background:transparent; border:0; border-radius:0; padding:0; }}
            QPushButton[gardenStatCell='true'][separator='true'] {{ border-right:1px solid {self.CARD_BORDER}; }}
            QPushButton[gardenStatCell='true']:hover {{ background:#173B30; }}
            QPushButton[gardenStatCell='true']:pressed {{ background:#123228; }}
            QPushButton[gardenStatCell='true']:focus {{ border:2px solid #82E2AC; }}
            QLabel[gardenStatLabel='true'] {{ color:#91aa9b; font-size:12px; font-weight:800; letter-spacing:.8px; }}
            QLabel[gardenPlantName='true'] {{ color:#F4F7F5; font-size:14px; font-weight:700; }}
            QLabel[gardenStageBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:800; letter-spacing:.7px; }}
            QLabel[gardenGrowthValue='true'] {{ color:#F4F7F5; font-size:14px; font-weight:700; }}
            QLabel[gardenLargeValue='true'] {{ color:#F4F7F5; font-size:20px; font-weight:700; }}
            QLabel[gardenValueUnit='true'] {{ color:#c8d5cb; font-size:15px; padding-bottom:2px; }}
            QLabel[gardenBonusBadge='true'] {{ color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 7px; font-size:12px; font-weight:700; }}
            QLabel[gardenStatSupport='true'] {{ color:#B8C5BF; font-size:13px; }}
            QLabel[gardenDetailsAffordance='true'] {{ color:#B8C5BF; font-size:13px; font-weight:600; }}
            QFrame[onboarding='true'] {{ background:rgba(12,38,31,238); border:1px solid #4F806E; border-radius:10px; }}
            QFrame[onboarding='true'][statusTone='error'] {{ background:rgba(66,34,36,242); border:2px solid #c8787f; }}
            QLabel[statusTone='error'] {{ color:#ffd8dc; }}
            QFrame[progressRow='true'] {{ background:#0d211e; border:1px solid #27443a; border-radius:9px; }}
            QFrame[progressRow='true'][completed='true'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QFrame[progressRow='true'][achievementState='locked'] {{ border-left:3px solid #52645d; }}
            QFrame[progressRow='true'][achievementState='in_progress'] {{ border-left:3px solid #d1ad69; }}
            QFrame[progressRow='true'][achievementState='unlocked'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QFrame[catalogCard='true'] {{ background:#0C261F; border:1px solid #20483C; border-radius:12px; }}
            QFrame[catalogCard='true'][catalogState='available'] {{ border-color:#52645D; }}
            QFrame[catalogCard='true'][catalogState='locked'] {{ border-color:#52645D; }}
            QFrame[catalogCard='true'][catalogState='in_progress'] {{ border-color:#D1AD69; }}
            QFrame[catalogCard='true'][catalogState='completed'] {{ border-color:#4F806E; }}
            QFrame[catalogCard='true'][catalogState='unlocked'] {{ border-color:#4F806E; }}
            QLabel[catalogIcon='true'] {{ color:#82E2AC; background:#123228; border-radius:18px; font-size:17px; font-weight:800; }}
            QLabel[catalogStatus='true'] {{ color:#CFE0D6; background:#123228; border-radius:8px; padding:4px 7px; font-size:12px; font-weight:700; }}
            QLabel[categoryTitle='true'] {{ color:#F4F7F5; font-size:15px; font-weight:800; padding:8px 2px 1px 2px; }}
            QLabel[typography='title'] {{ font-size:16px; font-weight:800; letter-spacing:0.3px; }}
            QLabel[typography='section-title'] {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
            QLabel[typography='muted-body'] {{ font-size: 13px; color: {self.TEXT_MUTED}; }}
            QLabel[typography='status-chip'] {{ font-size: 13px; font-weight: 600; letter-spacing: 0.1px; }}
            QLabel[chip='true'] {{ padding: {self.CHIP_PADDING[0]}px {self.CHIP_PADDING[1]}px; background:{self.CHIP_BG}; border-radius:{self.CHIP_BORDER_RADIUS}px; }}
            QLabel[nurturingPill='true'] {{ padding:5px 10px; color:#f5e5ba; background:#5a4824; border:1px solid #8a6b34; border-radius:10px; font-weight:700; }}
            QLabel[actionMeta='true'], QLabel[rowCriteria='true'] {{ color:{self.TEXT_MUTED}; font-size:13px; }}
            QLabel[actionHint='true'] {{ color:#d8cba2; font-size:13px; padding-top:2px; }}
            QLabel[rowTitle='true'], QLabel[moveTitle='true'] {{ font-weight:700; }}
            QLabel[completion='true'] {{ color:#9ef3b0; font-weight:700; }}
            QLabel[rowStatus='true'] {{ color:#bcd0d3; font-size:13px; font-weight:600; }}
            QLabel[progressValue='true'] {{ color:#bcd0d3; font-size:13px; }}
            QTabWidget::pane {{ border:0; background:#0C261F; top:-1px; }}
            QTabBar {{ background:#0b1f1b; }}
            QTabBar::tab {{ min-height:38px; max-height:38px; min-width:104px; padding:0 14px; color:#B8C5BF; background:transparent; border:0; border-bottom:2px solid transparent; font-weight:600; }}
            QTabBar::tab:hover {{ background:#173B30; color:#F4F7F5; }}
            QTabBar::tab:selected {{ color:#F4F7F5; border-bottom:2px solid #5CC58B; }}
            QScrollArea {{ background:transparent; border:0; }}
            {foundation_stylesheet()}
            QPushButton[catalogCard='true'] {{ min-height:214px; padding:10px; text-align:left; background:#0C261F; border:1px solid #20483C; border-radius:12px; }}
            QPushButton[catalogCard='true']:hover {{ background:#173B30; border-color:#4F806E; }}
            QPushButton[catalogCard='true']:focus {{ border:2px solid #82E2AC; padding:9px; }}
            QPushButton[headerAction='true'] {{ min-height:36px; max-height:36px; min-width:36px; font-size:13px; }}
            QProgressBar {{ border-radius: 7px; border: 1px solid {self.CARD_BORDER}; background: #132029; }}
            QProgressBar::chunk {{ background: {GARDEN_THEME['growth_accent']}; border-radius: 6px; }}
            QProgressBar[metricProgress='true'] {{ border:0; border-radius:4px; background:#203d35; }}
            QProgressBar[metricProgress='true']::chunk {{ border-radius:4px; background:{GARDEN_THEME['growth_accent']}; }}
            QLabel[stagePreview='true'] {{ background:#0c211d; border:1px solid #315045; border-radius:9px; color:#aac0b1; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        page.setObjectName("gardenDashboardPage")
        root = QVBoxLayout(page)
        self.dashboard_root_layout = root
        root.setContentsMargins(*self.ROOT_MARGINS)
        root.setSpacing(self.ROOT_SPACING)
        # The complete dashboard becomes vertically reachable when the compact
        # header and six-bed scene cannot coexist at minimum height.
        self.dashboard_page = page
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.dashboard_scroll.setAccessibleName("Garden dashboard content")
        self.dashboard_scroll.setWidget(page)
        _set_scroll_surface(self.dashboard_scroll, page, self.APP_BG)
        outer.addWidget(self.dashboard_scroll)

        self.top_bar = QFrame()
        top = self.top_bar
        top.setProperty("topBar", True)
        top.setMinimumHeight(102)
        # The header may grow to its responsive size hint, but it must not
        # absorb spare dashboard height. A vertical Minimum policy lets Qt
        # stretch the frame and leaves a large empty band between the metric
        # strip and garden artwork on shorter/high-DPI displays.
        top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.header_grid = QGridLayout(top)
        self.header_grid.setContentsMargins(14, 4, 14, 4)
        self.header_grid.setHorizontalSpacing(12)
        self.header_grid.setVerticalSpacing(4)
        self.title_stack_widget = QWidget()
        self.title_stack_widget.setMinimumWidth(230)
        self.title_stack_widget.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Maximum,
        )
        title_stack = QVBoxLayout()
        self.title_stack_widget.setLayout(title_stack)
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(1)
        self.product_label = QLabel("ANKI GARDEN")
        self.product_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        self.product_label.setStyleSheet(
            "color:#d8b875; font-size:12px; font-weight:800; letter-spacing:1.2px;"
        )
        self.title_label = ElidingLabel("")
        self._apply_typography(self.title_label, "title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(False)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Maximum,
        )
        title_stack.addWidget(self.product_label)
        title_stack.addWidget(self.title_label)
        self.progress_btn = QPushButton("Garden Progress")
        self.progress_btn.setProperty("headerAction", True)
        _set_button_variant(self.progress_btn, BUTTON_VARIANT_SECONDARY)
        self.progress_btn.setAccessibleDescription(
            "Open today, achievement, collection, and progression details."
        )
        self.progress_btn.clicked.connect(self._open_progress)
        self.collection_btn = QPushButton("Collection")
        self.collection_btn.setProperty("headerAction", True)
        _set_button_variant(self.collection_btn, BUTTON_VARIANT_SECONDARY)
        self.collection_btn.setAccessibleDescription(
            "Open the plant Collection in Garden Progress."
        )
        self.collection_btn.clicked.connect(self._open_collection)
        # Compatibility alias for fixture and extension code that queried the
        # old header control. It now routes to Collection, never Customize.
        self.customize_btn = self.collection_btn
        self.settings_btn = GardenIconButton("settings", UI_TEXT["open_settings"])
        self.settings_btn.setProperty("headerAction", True)
        self.settings_btn.clicked.connect(self._open_settings)
        apply_explanatory_tooltip(
            self.settings_btn,
            "Change garden display preferences.",
        )
        self.nursery_recovery_btn = QPushButton("Open Nursery")
        self.nursery_recovery_btn.setProperty("headerAction", True)
        _set_button_variant(self.nursery_recovery_btn, BUTTON_VARIANT_SECONDARY)
        self.nursery_recovery_btn.setAccessibleDescription(
            "Open the Nursery. This recovery action appears because its garden building is unavailable."
        )
        self.nursery_recovery_btn.clicked.connect(self._open_nursery)
        self.nursery_recovery_btn.hide()
        self.starter_header_btn = QPushButton(CHOOSE_STARTER_ACTION)
        self.starter_header_btn.setProperty("headerAction", True)
        _set_button_variant(self.starter_header_btn, BUTTON_VARIANT_PRIMARY)
        self.starter_header_btn.setAccessibleName(CHOOSE_STARTER_ACTION)
        self.starter_header_btn.setAccessibleDescription(
            "Open the Nursery to choose your starter."
        )
        self.starter_header_btn.clicked.connect(self._open_starter_nursery)
        self.starter_header_btn.hide()
        self.header_actions_widget = QWidget()
        self.header_actions_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        action_row = QHBoxLayout(self.header_actions_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self.starter_header_btn)
        action_row.addWidget(self.nursery_recovery_btn)
        action_row.addWidget(self.progress_btn)
        action_row.addWidget(self.collection_btn)
        action_row.addWidget(self.settings_btn)
        self.garden_stats_bar = GardenStatsStrip(self.engine)
        self.garden_stats_bar.setMinimumHeight(54)
        self.garden_stats_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.garden_stats_bar.setMinimumWidth(0)
        self.garden_stats_bar.metricActivated.connect(self._open_metric_details)
        self.header_grid.addWidget(self.title_stack_widget, 0, 0)
        self.header_grid.addWidget(self.header_actions_widget, 0, 1)
        self.header_grid.addWidget(self.garden_stats_bar, 1, 0, 1, 2)
        self.header_grid.setColumnStretch(0, 1)

        self.onboarding_panel = QFrame()
        self.onboarding_panel.setProperty("onboarding", True)
        self.onboarding_panel.setAccessibleName("Getting started with Anki Garden")
        self.onboarding_layout = QVBoxLayout(self.onboarding_panel)
        self.onboarding_layout.setContentsMargins(*self.CARD_PADDING)
        self.onboarding_layout.setSpacing(8)
        onboarding_copy = QVBoxLayout()
        onboarding_copy.setSpacing(3)
        self.onboarding_step = QLabel("")
        self.onboarding_step.hide()
        self.onboarding_step.setStyleSheet(
            "color:#82E2AC; font-size:12px; font-weight:700; letter-spacing:.8px;"
        )
        self.onboarding_title = QLabel("")
        self.onboarding_title.setProperty("rowTitle", True)
        self.onboarding_message = QLabel("")
        self.onboarding_message.setWordWrap(True)
        self._apply_typography(self.onboarding_message, "muted-body")
        onboarding_copy.addWidget(self.onboarding_step)
        onboarding_copy.addWidget(self.onboarding_title)
        onboarding_copy.addWidget(self.onboarding_message)
        self.onboarding_layout.addLayout(onboarding_copy, 1)
        self.onboarding_error_banner = GardenStatusBanner()
        self.onboarding_layout.addWidget(self.onboarding_error_banner)
        onboarding_actions = QHBoxLayout()
        onboarding_actions.setSpacing(8)
        self.onboarding_action = QPushButton(CHOOSE_STARTER_ACTION)
        _set_button_variant(self.onboarding_action, BUTTON_VARIANT_PRIMARY)
        self.onboarding_action.clicked.connect(self._activate_onboarding_action)
        onboarding_actions.addWidget(self.onboarding_action, 1)
        self.dismiss_onboarding = QPushButton(GARDEN_SETUP_SECONDARY_ACTION)
        _set_button_variant(self.dismiss_onboarding, BUTTON_VARIANT_SECONDARY)
        self.dismiss_onboarding.setAccessibleDescription("Hide first-use garden guidance")
        self.dismiss_onboarding.clicked.connect(self._dismiss_onboarding)
        onboarding_actions.addWidget(self.dismiss_onboarding, 1)
        self.onboarding_layout.addLayout(onboarding_actions)
        self.onboarding_actions_responsive = AdaptiveRow.for_box_layout(
            "dashboard.onboarding-actions",
            (
                AdaptiveRegion.measured("primary", self.onboarding_action, floor=104),
                AdaptiveRegion.measured("secondary", self.dismiss_onboarding, floor=104),
            ),
            layout=onboarding_actions,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.onboarding_panel,
        )
        self.onboarding_panel.setMaximumWidth(
            self.ONBOARDING_COACHMARK_MAX_WIDTH
        )

        hero_card = self._card_frame()
        hero_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        h_layout = QVBoxLayout(hero_card)
        self.dashboard_hero_layout = h_layout
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(self.CARD_SPACING)
        self.scene = GardenSceneWidget()
        self.onboarding_shield = QFrame(self.scene)
        self.onboarding_shield.setProperty("onboardingShield", True)
        self.onboarding_shield.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.onboarding_shield.setStyleSheet(
            "QFrame[onboardingShield='true'] { background:rgba(5,22,18,96); border:0; }"
        )
        self.onboarding_shield.setAccessibleName("Garden interaction paused")
        self.onboarding_shield.setAccessibleDescription(
            "Complete or postpone the current setup instruction before using the garden scene."
        )
        self.onboarding_shield.hide()
        self.onboarding_panel.setParent(self.scene)
        self.scene.placementRequested.connect(self._place_plant)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self.scene.landmarkActivated.connect(self._on_landmark_activated)
        self.scene.landmarksChanged.connect(self._sync_nursery_recovery)
        self.scene.placementStateChanged.connect(self._on_placement_state)
        self.scene.cancelPlacementRequested.connect(self._cancel_move)
        self.scene.cardGeometryChanged.connect(self._position_plant_card)
        self.scene.setMinimumHeight(260)
        self.plant_card = AnchoredPlantPopover(self.scene)
        self.plant_card_dock = QFrame()
        self.plant_card_dock.setProperty("plantCardDock", True)
        self.plant_card_dock.setProperty("bottomSheet", True)
        self.plant_card_dock.setAccessibleName("Selected plant bottom sheet")
        self.plant_card_dock_layout = QVBoxLayout(self.plant_card_dock)
        self.plant_card_dock_layout.setContentsMargins(0, 0, 0, 0)
        self.plant_card_dock_layout.setSpacing(0)
        self.plant_card_dock.hide()
        self.overlay_manager = GardenOverlayManager(
            self.onboarding_panel,
            self.plant_card,
            self._refresh_onboarding,
            self,
        )
        self.plant_card.dismissRequested.connect(self.scene.dismiss_selection)
        self.plant_card.nurture.clicked.connect(lambda: self._nurture_plant(self.plant_card.plant_id))
        self.plant_card.fertilize.clicked.connect(lambda: self._open_fertilizer_menu(self.plant_card.plant_id))
        self.plant_card.growth_charge.clicked.connect(
            lambda: self._open_growth_charges_for_plant(self.plant_card.plant_id)
        )
        self.plant_card.move.clicked.connect(lambda: self._begin_move(self.plant_card.plant_id))
        self.plant_card.story.clicked.connect(lambda: self._open_plant_story(self.plant_card.plant_id))
        self.plant_card.chooseAnother.connect(self._choose_another_plant)
        self.rearrange_bar = RearrangeBar(self.scene)
        self.rearrange_bar.retry.clicked.connect(self._retry_failed_move)
        self.rearrange_bar.cancel.clicked.connect(self._cancel_move)
        self.stage_transition_note = QLabel("")
        self.stage_transition_note.setTextFormat(Qt.TextFormat.PlainText)
        self.stage_transition_note.setWordWrap(True)
        self.stage_transition_note.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.stage_transition_note)
        self.stage_transition_note.setAccessibleName("Garden progress update")
        self._apply_typography(self.stage_transition_note, "muted-body")
        self.stage_transition_note.setStyleSheet("color:#f4d58a; font-size:14px; font-weight:700;")
        self.stage_transition_note.hide()
        self.same_day_catchup_note = QLabel("")
        self.same_day_catchup_note.setTextFormat(Qt.TextFormat.PlainText)
        self.same_day_catchup_note.setWordWrap(True)
        self.same_day_catchup_note.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.same_day_catchup_note)
        self.same_day_catchup_note.setAccessibleName("Garden rewards update")
        self.same_day_catchup_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._apply_typography(self.same_day_catchup_note, "muted-body")
        self.same_day_catchup_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.same_day_catchup_note.hide()
        self.status_notice = QLabel("")
        self.status_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.status_notice.setWordWrap(True)
        self.status_notice.setAccessibleName("Garden save status")
        self.status_notice.hide()
        self.feedback_panel = QFrame()
        self.feedback_panel.setProperty("transientFeedback", True)
        self.feedback_panel.setAccessibleName("Garden updates")
        self.feedback_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.toast_region = ToastRegion(self.scene)
        self.toast_region.shown.connect(self._position_scene_overlays)
        feedback_layout = QVBoxLayout(self.feedback_panel)
        feedback_layout.setContentsMargins(0, 0, 0, 0)
        feedback_layout.setSpacing(5)
        feedback_layout.addWidget(self.stage_transition_note)
        feedback_layout.addWidget(self.same_day_catchup_note)
        feedback_layout.addWidget(self.status_notice)
        self.feedback_panel.hide()
        h_layout.addWidget(top)
        # All temporary guidance and results belong before the artwork they
        # describe. Below a full-height scene they can be valid but invisible.
        h_layout.addWidget(self.feedback_panel)
        h_layout.addWidget(self.scene, 1)
        h_layout.addWidget(self.plant_card_dock)
        root.addWidget(hero_card, 1)

        self.milestone_card = self._card_frame()
        self.milestone_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.milestone_layout = QHBoxLayout(self.milestone_card)
        self.milestone_layout.setContentsMargins(*self.CARD_PADDING)
        self.milestone_layout.setSpacing(self.CARD_SPACING)
        self.milestone_title = QLabel("Garden unlocks")
        self._apply_typography(self.milestone_title, "section-title")
        self.milestone_note = QLabel("")
        self.milestone_note.setWordWrap(True)
        self._apply_typography(self.milestone_note, "muted-body")
        self.milestone_copy_layout = QVBoxLayout()
        self.milestone_copy_layout.setSpacing(2)
        self.milestone_copy_layout.addWidget(self.milestone_title)
        self.milestone_copy_layout.addWidget(self.milestone_note)
        self.milestone_layout.addLayout(self.milestone_copy_layout, 1)
        self.milestone_choices = QHBoxLayout()
        self.milestone_choices.setSpacing(6)
        self.milestone_progress = LabeledProgress("Collection progress")
        self.milestone_progress.setMinimumWidth(250)
        self.milestone_layout.addWidget(self.milestone_progress)
        self.milestone_layout.addLayout(self.milestone_choices)
        self.milestone_card.hide()

        self._achievement_filter = "all"
        self._achievement_filter_buttons: dict[str, QPushButton] = {}
        self.achievement_list = ProgressCardGrid(
            "Achievement progress", span_singleton_rows=True
        )
        self._collection_filter = "all"
        self._collection_category = "all"
        self._collection_query = ""
        self._collection_sort = "catalog"
        self.collection_list = ProgressCardGrid(
            "Collectible collection", wide_columns=4, minimum_item_width=160
        )
        self.collectible_detail_dialog = CollectibleDetailDialog(
            self,
            self.engine,
            self.storage,
            self._settings_scene_snapshot,
        )
        self.progress_dialog = GardenProgressDialog(
            self,
            self.engine,
            self.storage,
            self._open_nursery,
            self.achievement_list,
            self.collection_list,
        )
        self._progress_return_focus: QWidget | None = None
        self.progress_dialog.finished.connect(self._restore_progress_focus)
        # Compatibility alias: both entry points now share one dialog instance.
        self.details_dialog = self.progress_dialog
        self._metric_return_focus: QWidget | None = None
        self.details_dialog.finished.connect(self._restore_metric_focus)

        # Each dashboard region owns its content requirement independently.
        # This prevents one arbitrary pixel edge from changing the header,
        # metric density, card composition, and action copy together.
        self.dashboard_header_full = AdaptiveRow(
            "dashboard.header-full",
            (
                AdaptiveRegion.measured(
                    "garden-title",
                    self.title_stack_widget,
                    floor=230,
                ),
                AdaptiveRegion(
                    "garden-metrics",
                    self.garden_stats_bar.wide_content_minimum_width,
                    self.garden_stats_bar,
                ),
                AdaptiveRegion(
                    "garden-actions",
                    self._header_actions_content_width,
                    self.header_actions_widget,
                ),
            ),
            spacing=12,
            telemetry_target=self.top_bar,
        )
        self.dashboard_header_title_actions = AdaptiveRow(
            "dashboard.header-title-actions",
            (
                AdaptiveRegion.measured(
                    "garden-title",
                    self.title_stack_widget,
                    floor=230,
                ),
                AdaptiveRegion(
                    "garden-actions",
                    self._header_actions_content_width,
                    self.header_actions_widget,
                ),
            ),
            spacing=12,
            telemetry_target=self.header_actions_widget,
        )
        self.dashboard_metrics_responsive = AdaptiveRow(
            "dashboard.metrics-density",
            (
                AdaptiveRegion(
                    "full-metric-copy",
                    self.garden_stats_bar.wide_content_minimum_width,
                    self.garden_stats_bar,
                ),
            ),
            telemetry_target=self.garden_stats_bar,
        )
        self.dashboard_milestone_responsive = AdaptiveRow.for_box_layout(
            "dashboard.milestone",
            (
                AdaptiveRegion.measured(
                    "milestone-copy",
                    self.milestone_copy_layout,
                    floor=300,
                ),
                AdaptiveRegion.measured(
                    "milestone-progress",
                    self.milestone_progress,
                    floor=250,
                ),
                AdaptiveRegion.measured(
                    "milestone-actions",
                    self.milestone_choices,
                    floor=160,
                ),
            ),
            layout=self.milestone_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=self.CARD_SPACING,
            telemetry_target=self.milestone_card,
        )
        self.dashboard_rearrange_responsive = AdaptiveRow(
            "dashboard.rearrange-actions",
            (AdaptiveRegion.fixed("rearrange-bar", 560, target=self.rearrange_bar),),
            apply_mode=lambda mode: self.rearrange_bar.set_compact(
                mode == COMPACT_MODE
            ),
            telemetry_target=self.rearrange_bar,
        )

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)
        role = {
            "title": TextRole.SCREEN_TITLE,
            "section-title": TextRole.SECTION_HEADING,
            "card-title": TextRole.CARD_TITLE,
            "body": TextRole.BODY,
            "muted-body": TextRole.SECONDARY,
            "metadata": TextRole.METADATA,
            "badge": TextRole.BADGE,
            "numeric": TextRole.NUMERIC_DISPLAY,
        }.get(str(level), TextRole.BODY)
        apply_text_role(label, role)

    def _open_progress(self) -> None:
        self._progress_return_focus = self.focusWidget()
        self.progress_dialog.open_page()

    def _open_collection(self) -> None:
        """Reuse the single Garden Progress shell and select Collection."""

        if self._collection_activation_pending:
            return
        self._collection_activation_pending = True
        self._progress_return_focus = self.focusWidget()
        try:
            self.progress_dialog.open_page("collection")
        finally:
            QTimer.singleShot(0, self._release_collection_activation)

    def _release_collection_activation(self) -> None:
        self._collection_activation_pending = False

    def _open_customize(self) -> None:
        """One-release compatibility route for retired Customize entry points."""

        self._open_collection()

    def _open_loadout_detail(
        self,
        category: str = "",
        item_id: str = "",
    ) -> None:
        if self.scene._interaction.placing:
            return
        self.scene.dismiss_selection()
        self.collectible_detail_dialog.remember_invoker(self.progress_dialog)
        if category and item_id:
            self.collectible_detail_dialog.open_item(category, item_id)
        else:
            self.collectible_detail_dialog.prepare_to_show()
            self.collectible_detail_dialog.present_over_parent()

    def _restore_progress_focus(self, _result: int) -> None:
        target = self._progress_return_focus
        self._progress_return_focus = None
        if target is not None:
            try:
                target.setFocus()
            except RuntimeError:
                pass

    def _open_metric_details(self, metric: str) -> None:
        key = str(metric)
        self._metric_return_focus = self.garden_stats_bar.cells.get(key)
        self.progress_dialog.open_page(key)

    def _restore_metric_focus(self, _result: int) -> None:
        target = self._metric_return_focus
        self._metric_return_focus = None
        if target is not None:
            try:
                target.setFocus()
            except RuntimeError:
                pass

    def refresh_all(self, *, acknowledge: bool | None = None) -> None:
        if acknowledge is None:
            try:
                acknowledge = bool(self.isVisible())
            except RuntimeError:
                acknowledge = False
        DISPLAY_TELEMETRY.track_render("dashboard")
        state = self.storage.state
        snapshot = select_garden_ui(self.engine, self.storage)
        garden_name = snapshot.garden_name
        self.title_label.setText(garden_name)
        self.title_label.setToolTip(garden_name)
        self.title_label.setAccessibleName(f"Garden name: {garden_name}")
        self.setWindowTitle(f"{garden_name} — Anki Garden")
        notice = _learner_text(USER_NOTICES.current.message)
        self.status_notice.setText(notice)
        self.status_notice.setVisible(bool(notice))
        self.status_notice.setStyleSheet("color:#ffd0d0;" if notice else "")
        self.status_notice.setAccessibleDescription(notice)
        stats = state.daily_stats
        try:
            presentation_day = date.fromisoformat(str(stats.day)[:10])
        except (TypeError, ValueError):
            presentation_day = date.today()
        streak_view = streak_presentation(
            snapshot.streak_days,
            getattr(state, "last_active_day", ""),
            getattr(stats, "reviewed", 0),
            today=presentation_day,
        )
        streak_days = streak_view.current_days
        streak_bonus = snapshot.streak_bonus_percent if streak_days > 0 else 0
        streak_value = (
            f"0 days\n{streak_view.status_label}"
            if streak_days == 0
            else (
                f"{streak_days} {'day' if streak_days == 1 else 'days'}\n"
                f"+{streak_bonus}% Growth"
            )
        )
        onboarding_display = onboarding_state_display(
            state,
            self.config.value("onboarding_version", 0),
        )
        active = self.engine.active_plant()
        planted_starter = None
        if (
            active is None
            and onboarding_display.state == OnboardingState.STARTER_PLANTED_NOT_NURTURED
        ):
            planted_starter = next(
                (plant for plant in getattr(state, "plants", []) if bool(getattr(plant, "planted", True))),
                None,
            )
        displayed_plant = active or planted_starter
        if displayed_plant is None:
            active_growth = "No plant selected"
            growth_now, growth_max = 0, 1
            growth_name, growth_stage, growth_next_stage, growth_total, growth_remaining, growth_complete = (
                "", "", "", 0, 0, False
            )
            growth_progress_text = "No plant selected."
        else:
            progress = growth_display(displayed_plant.growth_points)
            active_growth = (
                "Fully grown"
                if progress.fully_grown else
                f"{progress.stage_points:,} / {progress.stage_goal:,}"
            )
            growth_now = 1 if progress.fully_grown else progress.stage_points
            growth_max = 1 if progress.fully_grown else max(1, progress.stage_goal)
            growth_name = displayed_plant.name
            growth_stage = format_status_label(progress.stage)
            growth_next_stage = format_status_label(progress.next_stage or "")
            growth_total = displayed_plant.growth_points
            growth_remaining = progress.points_remaining
            growth_complete = progress.fully_grown
            growth_progress_text = (
                f"{displayed_plant.name} is fully grown."
                if progress.fully_grown else
                f"{progress.stage_points:,} / {progress.stage_goal:,} Growth to "
                f"{format_status_label(progress.next_stage or 'the next stage')}."
            )
        self.garden_stats_bar.set_values(
            growth=active_growth,
            streak=streak_value,
            currency=f"{snapshot.currency_balance:,}",
        )
        self.garden_stats_bar.set_growth_details(
            plant_name=growth_name,
            stage=growth_stage,
            next_stage=growth_next_stage,
            total_growth=growth_total,
            current=growth_now,
            maximum=growth_max,
            remaining=growth_remaining,
            fully_grown=growth_complete,
            accessible_text=growth_progress_text,
            status_label=onboarding_display.header_label,
            forecast_text="",
            forecast_tooltip="",
        )
        self.garden_stats_bar.set_streak_details(
            days=streak_days,
            bonus_percent=streak_bonus,
            support=streak_view.message,
        )
        self.garden_stats_bar.set_currency_details(snapshot.currency_balance)
        self._refresh_onboarding()

        transitions = self.engine.peek_stage_transitions()
        transition_message = self.engine.stage_transition_message(transitions)
        feedback = self.engine.peek_feedback()[:3]
        feedback_message = "\n".join(_learner_text(event.message) for event in feedback)
        progress_message = "\n".join(
            filter(None, (_learner_text(transition_message), feedback_message))
        )
        self._stage_message_generation += 1
        stage_generation = self._stage_message_generation
        self.stage_transition_note.setText(progress_message)
        self.stage_transition_note.hide()
        self.stage_transition_note.setAccessibleDescription(progress_message)
        self._sync_feedback_panel_visibility()
        if progress_message:
            self.toast_region.show_message(progress_message, duration_ms=0)
            QTimer.singleShot(4200, lambda: self._clear_stage_message(stage_generation))

        selected_id = self.scene.selected_plant_id()
        self.scene.set_scene(
            {
                "weather": snapshot.selected_weather,
                "theme": str(self.config.value("visual_theme", "verdant_twilight")),
                "health": min(1.0, 0.5 + (streak_bonus / 50.0)),
                "growth": min(1.0, stats.growth_earned / max(10, stats.reviewed * 10)),
                "unlocked_slots": snapshot.unlocked_slots,
                "streak_days": snapshot.streak_days,
                "streak_bonus_percent": streak_bonus,
                "cards_today": stats.reviewed,
                "show_status_overlay": False,
                "motion_enabled": bool(
                    effective_motion_enabled(
                        bool(self.config.value("enable_animations", True)),
                        bool(self.config.value("reduced_motion", False)),
                        os_reader=lambda: self._system_reduced_motion,
                    )
                ),
                "animation_intensity": 0.7,
                "weather_particle_density": 1.0,
                "asset_paths": {
                    "background": self._resolved_asset_payload("resolve_background_asset", "resolve_background_image"),
                    "garden_overlay": self._resolved_asset_payload(
                        "resolve_garden_overlay_asset",
                        "resolve_garden_overlay_image",
                    ),
                    "nurtured_marker": self._resolved_asset_payload(
                        "resolve_nurtured_marker_asset",
                        "resolve_nurtured_marker_image",
                    ),
                    "nurtured_marker_spout_right": self._resolved_asset_payload(
                        "resolve_nurtured_marker_spout_right_asset",
                        "resolve_nurtured_marker_spout_right_image",
                    ),
                    "weather": self._resolved_asset_payload("resolve_weather_asset", "resolve_weather_overlay"),
                    "decoration": self._resolved_asset_payload(
                        "resolve_decoration_asset",
                        "resolve_decoration_image",
                        state.equipped.get("decoration", "none"),
                    ),
                },
                "stage_transitions": [transition.to_dict() for transition in transitions],
                "plants": [
                    self._plant_scene_payload(plant)
                    for plant in state.plants
                    if plant.slot_index is not None
                ],
            }
        )
        self._on_scene_selection(selected_id or "")

        self._refresh_achievement_list()
        self._refresh_collection_list()
        environment_new = bool(
            not self.config.value(
                "show_progress_notifications",
                DEFAULT_CONFIG["show_progress_notifications"],
            )
            and any(
                event.kind in {
                    "environment_drop",
                    "charge_drop",
                    "booster_drop",
                }
                for event in self.engine.peek_feedback()
            )
        )
        self.collection_btn.setAccessibleDescription(
            "New Garden rewards are available. Open the Collection in Garden Progress."
            if environment_new else
            "Open the plant Collection in Garden Progress."
        )
        if self.details_dialog.isVisible():
            self.details_dialog.refresh()
        self._pending_feedback_ack_ids = tuple(event.event_id for event in feedback)
        self._pending_transition_ack = tuple(transitions)
        self._update_scene_height()
        if acknowledge:
            self.acknowledge_rendered_feedback()

    @staticmethod
    def _achievement_view_state(projection: Any) -> str:
        if bool(getattr(projection, "unlocked", False)):
            return "completed"
        return "in_progress" if int(getattr(projection, "current", 0)) > 0 else "locked"

    def _set_achievement_filter(self, selected: str) -> None:
        normalized = selected if selected in {
            "all", "in_progress", "completed", "locked",
        } else "all"
        self._achievement_filter = normalized
        self._refresh_achievement_list()
        target = self._achievement_filter_buttons.get(normalized)
        if target is not None:
            QTimer.singleShot(0, target.setFocus)

    def _refresh_achievement_list(self) -> None:
        state = self.storage.state
        achievement_views = achievement_presentations(state)
        self.achievement_list.clear()

        filter_panel = QFrame()
        filter_panel.setProperty("dataTable", True)
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(6)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._achievement_filter_buttons = {}
        for key, label in (
            ("all", "All"),
            ("in_progress", "In progress"),
            ("completed", "Completed"),
            ("locked", "Locked"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(self._achievement_filter == key)
            button.setProperty("detailDisclosure", True)
            button.setProperty("achievementFilter", True)
            button.setFixedHeight(38)
            button.setAccessibleDescription(
                f"Show {label.lower()} achievements."
            )
            button.clicked.connect(
                lambda _checked=False, selected=key: self._set_achievement_filter(selected)
            )
            self._achievement_filter_buttons[key] = button
            filter_row.addWidget(button)
        filter_row.addStretch(1)
        filter_layout.addLayout(filter_row)
        self.achievement_list.add_full_width(filter_panel)

        visible = tuple(
            projection
            for projection in achievement_views
            if self._achievement_filter == "all"
            or self._achievement_view_state(projection) == self._achievement_filter
        )
        category_groups = (
            ("consistency", "Consistency"),
            ("study_volume", "Study volume"),
            ("recall", "Recall"),
            ("completion", "Completion"),
        )
        for category, group_label in category_groups:
            group = tuple(sorted(
                (
                    projection
                    for projection in visible
                    if projection.category == category
                ),
                key=lambda projection: (
                    0 if projection.unlocked else 1,
                    -float(projection.progress),
                    projection.name.casefold(),
                ),
            ))
            if not group:
                continue
            group_heading = QLabel(group_label)
            group_heading.setProperty("categoryTitle", True)
            self.achievement_list.add_full_width(group_heading)
            for projection in group:
                view_state = self._achievement_view_state(projection)
                status_text = {
                    "completed": "Completed",
                    "in_progress": "In progress",
                    "locked": "Locked",
                }[view_state]
                catalog_state = "unlocked" if view_state == "completed" else view_state
                card = QFrame()
                card.setProperty("catalogCard", True)
                card.setProperty("catalogState", catalog_state)
                card.setProperty("achievementState", view_state)
                card.setProperty("achievementId", projection.achievement_id)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(13, 12, 13, 12)
                card_layout.setSpacing(7)

                heading = QHBoxLayout()
                icon = QLabel(
                    "✓" if projection.unlocked else
                    "◐" if view_state == "in_progress" else
                    "○"
                )
                icon.setProperty("catalogIcon", True)
                icon.setFixedSize(44, 44)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setAccessibleName(f"Achievement {status_text.lower()}")
                title = QLabel(projection.name)
                title.setWordWrap(True)
                title.setProperty("rowTitle", True)
                status = QLabel(status_text)
                status.setProperty("catalogStatus", True)
                heading.addWidget(icon)
                heading.addWidget(title, 1)
                if self._achievement_filter == "all":
                    heading.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
                card_layout.addLayout(heading)

                condition_lines = tuple(projection.condition_lines) or (
                    projection.criteria_text,
                )
                compound_conditions = bool(
                    not projection.unlocked
                    and len(condition_lines) > 1
                )
                card.setProperty(
                    "compoundConditionsVisible",
                    compound_conditions,
                )
                if not str(projection.achievement_id).startswith("streak_"):
                    requirement = QLabel(projection.criteria_text or condition_lines[0])
                    requirement.setWordWrap(True)
                    requirement.setProperty("rowCriteria", True)
                    card_layout.addWidget(requirement)
                if compound_conditions:
                    conditions = QWidget()
                    conditions.setProperty("achievementConditions", True)
                    conditions_layout = QVBoxLayout(conditions)
                    conditions_layout.setContentsMargins(0, 0, 0, 0)
                    conditions_layout.setSpacing(3)
                    for condition_line in condition_lines:
                        condition = QLabel(condition_line)
                        condition.setWordWrap(True)
                        condition.setProperty("rowStatus", True)
                        apply_tabular_numerals(condition)
                        conditions_layout.addWidget(condition)
                    card_layout.addWidget(conditions)

                unlock_text = ""
                if projection.unlocked:
                    unlock_text = (
                        _calendar_date(projection.unlocked_at)
                        if projection.unlocked_at else
                        "Date unavailable"
                    )
                    completed_date = QLabel(unlock_text)
                    completed_date.setProperty("rowCriteria", True)
                    card_layout.addWidget(completed_date)
                elif not compound_conditions:
                    progress = LabeledProgress(f"{projection.name} progress")
                    progress.set_progress(
                        "",
                        projection.current,
                        projection.progress_target,
                        value_text=projection.value_text,
                    )
                    progress.label.hide()
                    card_layout.addWidget(progress)

                finalization_note = ""
                if projection.evaluation_mode == "finalized_day":
                    finalization_note = (
                        "Finalized only after the Anki day closes; today's values are provisional."
                        if not projection.unlocked else
                        "Finalized after the qualifying Anki day closed."
                    )
                    finalized = QLabel(finalization_note)
                    finalized.setWordWrap(True)
                    finalized.setProperty("rowCriteria", True)
                    finalized.hide()

                reward = QLabel(projection.reward_summary)
                reward.setWordWrap(True)
                reward.setProperty("rowStatus", True)
                apply_tabular_numerals(reward)
                card_layout.addWidget(reward)
                card.setAccessibleName(
                    f"{projection.name}. {status_text}."
                )
                card.setAccessibleDescription(" ".join(filter(None, (
                    ". ".join(condition_lines),
                    projection.value_text,
                    finalization_note,
                    f"Reward: {projection.reward_summary}.",
                    unlock_text,
                ))))
                self.achievement_list.add_card(card)

        if not achievement_views:
            DISPLAY_TELEMETRY.track_empty_state(
                route="dashboard",
                view="achievement_list",
                expected_non_empty=True,
            )
            self.achievement_list.add_empty(
                "Achievements unavailable",
                UI_TEXT["no_achievements"],
            )
        elif not visible:
            label = self._achievement_filter.replace("_", " ")
            self.achievement_list.add_empty(
                f"No {label} achievements",
                "Choose another filter to view the achievement collection.",
            )
        self.achievement_list.finish()

    def acknowledge_rendered_feedback(self) -> None:
        """Persist acknowledgement only after the rendered surface is usable."""
        feedback_ids = self._pending_feedback_ack_ids
        rendered_transitions = self._pending_transition_ack
        if feedback_ids:
            try:
                self.engine.consume_feedback(event_ids=feedback_ids)
            except Exception:
                # Repeating a notice is safer than losing it or blocking the UI.
                logger.exception("Anki Garden: rendered feedback could not be acknowledged")
            else:
                self._pending_feedback_ack_ids = ()
        if rendered_transitions:
            try:
                self.engine.consume_stage_transitions(transitions=rendered_transitions)
            except Exception:
                logger.exception("Anki Garden: rendered stage transitions could not be acknowledged")
            else:
                self._pending_transition_ack = ()

    def _clear_stage_message(self, generation: int) -> None:
        if generation != self._stage_message_generation:
            return
        try:
            self.stage_transition_note.setText("")
            self.stage_transition_note.setAccessibleDescription("")
            self.stage_transition_note.hide()
            self._sync_feedback_panel_visibility()
        except RuntimeError:
            # A delayed capture/restart timer may outlive a replaced Qt tree.
            return

    @staticmethod
    def _local_date(value: str) -> str:
        try:
            from datetime import date
            parsed = date.fromisoformat(str(value)[:10])
            return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
        except Exception:
            return str(value)

    def _on_scene_selection(self, plant_id: str) -> None:
        plant = next((row for row in self.scene.scene.get("plants", []) if str(row.get("plant_id")) == plant_id), None)
        self.scene.set_keyboard_hint_suppressed(plant is not None)
        self.overlay_manager.plant_selection_changed(plant is not None)
        self.plant_card.set_selected(plant)
        onboarding_display = onboarding_state_display(
            self.storage.state,
            self.config.value("onboarding_version", 0),
        )
        guide_nurture = bool(
            plant is not None
            and onboarding_display.state == OnboardingState.STARTER_PLANTED_NOT_NURTURED
        )
        self.plant_card.set_onboarding_guidance(guide_nurture)
        if guide_nurture:
            self.onboarding_panel.hide()
            self._set_onboarding_shield(False)
        elif onboarding_display.step == OnboardingStep.NURTURE:
            self._refresh_onboarding()
        if plant is None:
            self._update_scene_height()
        self._position_plant_card()

    def _on_landmark_activated(self, action_id: str) -> None:
        action = str(action_id)
        handlers = {
            "garden.nursery.open": (
                self._open_starter_nursery
                if self.storage.state.onboarding.step in {
                    OnboardingStep.INTRODUCTION,
                    OnboardingStep.NURSERY,
                }
                else self._open_nursery
            ),
            "garden.progress.open": self._open_progress,
            "garden.collection.open": self._open_collection,
        }
        handler = handlers.get(action)
        if handler is not None:
            handler()

    def _open_nursery(self, tab_index: int = 0, *, status_message: str = "") -> None:
        if self.scene._interaction.placing:
            return
        if self.details_dialog.isVisible():
            self.details_dialog.close()
        self.scene.dismiss_selection()
        dialog = NurseryDialog(self, self.engine, self.storage)
        self.nursery_dialog = dialog
        dialog.catalog_tabs.setCurrentIndex(
            max(0, min(3, int(tab_index)))
        )
        if status_message:
            dialog._show_result(True, status_message)
        result = int(QDialog.DialogCode.Rejected)
        try:
            result = dialog.exec()
        finally:
            # Nursery is rebuilt from current persisted state on every open.
            # Detach and defer-delete the closed instance so the long-lived
            # Dashboard does not retain one complete catalogue tree per visit.
            if self.nursery_dialog is dialog:
                self.nursery_dialog = None
            dialog.hide()
            dialog.setParent(None)
            dialog.deleteLater()
        if not bool(getattr(self.storage.state, "starter_selection_complete", True)):
            self._starter_prompt_scheduled = False
        if (
            result == int(QDialog.DialogCode.Rejected)
            and self.storage.state.onboarding.step == OnboardingStep.NURSERY
        ):
            self._starter_setup_dismissed = True
        self._refresh_after_commit("Nursery dialog")
        if self.storage.state.onboarding.step == OnboardingStep.CONFIRMATION:
            QTimer.singleShot(0, self._show_starter_confirmation)

    def _open_starter_nursery(self) -> None:
        """Shared direct route for every pre-starter call to action."""

        self._starter_setup_dismissed = False
        step = self.storage.state.onboarding.step
        if step == OnboardingStep.INTRODUCTION:
            ok, message = self.engine.enter_starter_nursery()
            if not ok:
                self._onboarding_save_error = message
                self._refresh_onboarding()
                return
            self._onboarding_save_error = ""
            self._refresh_after_commit("onboarding Nursery entry")
            step = self.storage.state.onboarding.step
        if step == OnboardingStep.NURSERY:
            self._open_nursery(0)
        elif step == OnboardingStep.CONFIRMATION:
            self._show_starter_confirmation()
        elif step == OnboardingStep.PLACEMENT:
            self._begin_starter_placement()

    def _show_starter_confirmation(self) -> None:
        progress = self.storage.state.onboarding
        if (
            self._starter_confirmation_pending
            or progress.step != OnboardingStep.CONFIRMATION
            or not progress.pending_species
        ):
            return
        self._starter_confirmation_pending = True
        self._set_onboarding_shield(False)
        self.onboarding_panel.hide()
        dialog = StarterConfirmationDialog(
            self,
            self.engine,
            progress.pending_species,
        )
        result = int(QDialog.DialogCode.Rejected)
        try:
            result = dialog.exec()
        finally:
            self._starter_confirmation_pending = False
            dialog.hide()
            dialog.setParent(None)
            dialog.deleteLater()
        if result == int(QDialog.DialogCode.Accepted):
            ok, message = self.engine.confirm_starter_species()
            if not ok:
                self._onboarding_save_error = message
                self._refresh_onboarding()
                return
            self._onboarding_save_error = ""
            self._refresh_after_commit("starter confirmation")
            QTimer.singleShot(0, self._begin_starter_placement)
            return
        if dialog.back_requested:
            ok, message = self.engine.back_onboarding()
            if not ok:
                self._onboarding_save_error = message
                self._refresh_onboarding()
                return
            self._refresh_after_commit("starter confirmation back")
            QTimer.singleShot(0, self._open_starter_nursery)
            return
        self._refresh_onboarding()

    def _begin_starter_placement(self) -> None:
        if self.storage.state.onboarding.step != OnboardingStep.PLACEMENT:
            self._refresh_onboarding()
            return
        self._starter_setup_dismissed = False
        self._starter_placement_active = True
        self._set_onboarding_shield(False)
        self.onboarding_panel.hide()
        self.rearrange_bar.plant_id = "__starter__"
        self.rearrange_bar.clear_failure()
        self.rearrange_bar.title.setText("Place your starter")
        self.rearrange_bar.instructions.setText("Choose a bed.")
        self.rearrange_bar.cancel.setText("Back")
        allowed = list(range(max(0, min(6, int(self.storage.state.unlocked_slots)))))
        if self.scene.begin_starter_placement(allowed):
            self._record_active_placement_token()
            self.rearrange_bar.show()
            QTimer.singleShot(0, self._position_scene_overlays)
            return
        self._starter_placement_active = False
        self._active_placement_token = None
        self.rearrange_bar.cancel.setText("Cancel")
        self._onboarding_save_error = "No unlocked garden bed is available for placement."
        self._refresh_onboarding()

    def _show_nursery_landmark(self) -> None:
        # Landmark emphasis is supplementary; the actionable route is always
        # the same direct Nursery opener used by the Home and header CTAs.
        self.scene.focus_landmark("garden.nursery.open")
        self._open_starter_nursery()

    def _activate_onboarding_action(self) -> None:
        step = self.storage.state.onboarding.step
        if step in {OnboardingStep.INTRODUCTION, OnboardingStep.NURSERY}:
            self._open_starter_nursery()
            return
        if step == OnboardingStep.CONFIRMATION:
            self._show_starter_confirmation()
            return
        if step == OnboardingStep.PLACEMENT:
            self._begin_starter_placement()
            return
        if step == OnboardingStep.COMPLETION:
            if self._complete_onboarding():
                self._refresh_after_commit("onboarding Return to Anki")
                self._refresh_onboarding()
                self.accept()
            return
        if step != OnboardingStep.NURTURE:
            return
        plant = next(
            (
                row for row in self.storage.state.plants
                if row.planted and not row.fully_grown
            ),
            None,
        )
        if plant is None:
            return
        self._onboarding_plant_id = str(plant.plant_id)
        self.scene.keep_card_open(self._onboarding_plant_id)
        self._refresh_selected_plant_card()
        self.plant_card.set_onboarding_guidance(True)
        self.onboarding_panel.hide()
        QTimer.singleShot(0, self.plant_card.nurture.setFocus)

    def _sync_nursery_recovery(self) -> None:
        """Expose a button only when artwork-first Nursery navigation failed."""
        available = self.scene.landmark_geometry("garden.nursery.open") is not None
        derive = getattr(self, "_derived_ux_state", None)
        ux_state = derive() if callable(derive) else UX_ACTIVE_GROWTH
        storage = getattr(self, "storage", None)
        state = getattr(storage, "state", None)
        progress = getattr(state, "onboarding", None)
        raw_step = getattr(progress, "step", "done")
        guided = str(getattr(raw_step, "value", raw_step)) != "done"
        self.nursery_recovery_btn.setVisible(
            not guided and not available and not self.scene._interaction.placing
        )

    def _on_placement_state(self, active: bool) -> None:
        self.overlay_manager.move_mode_changed(active)
        self.rearrange_bar.setVisible(active)
        self._position_scene_overlays()
        self._sync_nursery_recovery()

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "onboarding_layout"):
            self._apply_responsive_layout(self._dashboard_content_width())
        self._update_scene_height(event.size().height())
        if hasattr(self, "onboarding_shield"):
            self.onboarding_shield.setGeometry(self.scene.rect())
        QTimer.singleShot(0, self._position_plant_card)
        QTimer.singleShot(0, self._position_onboarding_coachmark)
        QTimer.singleShot(0, self._position_scene_overlays)
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_dashboard_responsive_geometry)

    def _dashboard_content_width(self) -> int:
        margins = self.dashboard_page.layout().contentsMargins()
        scroll = getattr(self, "dashboard_scroll", None)
        viewport = scroll.viewport() if scroll is not None else None
        available = (
            int(viewport.width())
            if viewport is not None and int(viewport.width()) > 0 else
            int(self.width())
        )
        return max(0, available - margins.left() - margins.right())

    def _sync_dashboard_responsive_geometry(self) -> None:
        if not hasattr(self, "dashboard_root_layout"):
            return
        self._apply_responsive_layout(self._dashboard_content_width())
        self._sync_dashboard_content_minimum_height()

    def _sync_dashboard_content_minimum_height(self) -> None:
        """Let one vertical owner resolve compact header/scene pressure."""

        root = getattr(self, "dashboard_root_layout", None)
        page = getattr(self, "dashboard_page", None)
        if root is None or page is None:
            return
        # Do not feed live descendant geometry back into the page minimum.
        # The scene expands to the available viewport, so using its current
        # bottom edge here made each relayout preserve an obsolete oversized
        # page and forced the full Garden out of view. The root layout already
        # owns every reachable content region; its minimum is the canonical
        # scroll requirement.
        page.setMinimumHeight(0)
        root.invalidate()
        root.activate()
        required = max(1, int(root.minimumSize().height()))
        page.setMinimumHeight(required)
        page.setProperty("minimumReachableContentHeight", required)

    def _position_scene_overlays(self) -> None:
        if not hasattr(self, "scene"):
            return
        inset = 20
        available_width = max(1, self.scene.width() - (inset * 2))
        available_height = max(1, self.scene.height() - (inset * 2))
        top = inset
        if self.rearrange_bar.isVisible():
            bar_width = min(620, max(1, available_width))
            self.rearrange_bar.setFixedWidth(bar_width)
            self.rearrange_bar.adjustSize()
            bar_height = min(96, max(40, self.rearrange_bar.sizeHint().height()))
            self.rearrange_bar.setGeometry(
                max(inset, (self.scene.width() - bar_width) // 2),
                inset,
                bar_width,
                bar_height,
            )
            self.rearrange_bar.raise_()
            top = inset + bar_height + 8
        if self.toast_region.isVisible():
            toast_width = min(
                360,
                max(240, available_width) if available_width >= 240 else available_width,
            )
            self.toast_region.setFixedWidth(toast_width)
            self.toast_region.adjustSize()
            toast_height = min(
                available_height,
                min(84, max(44, self.toast_region.sizeHint().height())),
            )
            toast_x = self.scene.width() - toast_width - inset
            card_in_scene = (
                self.plant_card.isVisible()
                and self.plant_card.parentWidget() is self.scene
            )
            if card_in_scene:
                card_geometry = self.plant_card.geometry()
                # Feedback belongs opposite the selected plant. This keeps a
                # successful action visible without covering the open card.
                toast_x = (
                    self.scene.width() - toast_width - inset
                    if card_geometry.center().x() < self.scene.width() / 2
                    else inset
                )
                overlaps_horizontally = not (
                    toast_x + toast_width + 8 <= card_geometry.left()
                    or toast_x >= card_geometry.right() + 8
                )
                overlaps_vertically = not (
                    top + toast_height + 8 <= card_geometry.top()
                    or top >= card_geometry.bottom() + 8
                )
                if overlaps_horizontally and overlaps_vertically:
                    toast_x = max(inset, (self.scene.width() - toast_width) // 2)
            toast_y = max(
                inset,
                min(top, self.scene.height() - toast_height - inset),
            )
            self.toast_region.setGeometry(
                max(inset, min(toast_x, self.scene.width() - toast_width - inset)),
                toast_y,
                toast_width,
                toast_height,
            )
            self.toast_region.raise_()

    def _position_onboarding_coachmark(self) -> None:
        if not hasattr(self, "onboarding_panel") or not self.onboarding_panel.isVisible():
            return
        width = min(
            self.ONBOARDING_COACHMARK_MAX_WIDTH,
            max(self.ONBOARDING_COACHMARK_MIN_WIDTH, self.scene.width() - 24),
        )
        self.onboarding_panel.setFixedWidth(width)
        if hasattr(self, "onboarding_actions_responsive"):
            margins = self.onboarding_layout.contentsMargins()
            self.onboarding_actions_responsive.evaluate(
                max(0, width - margins.left() - margins.right())
            )
        margins = self.onboarding_layout.contentsMargins()
        active_message = self.onboarding_message
        message_width = max(1, width - margins.left() - margins.right())
        if self.onboarding_error_banner.isVisible():
            active_message = self.onboarding_error_banner.message
            banner_layout = self.onboarding_error_banner.layout()
            if banner_layout is not None:
                banner_margins = banner_layout.contentsMargins()
                message_width = max(
                    1,
                    message_width
                    - banner_margins.left()
                    - banner_margins.right(),
                )
        self.onboarding_message.setMinimumHeight(0)
        self.onboarding_error_banner.message.setMinimumHeight(0)
        wrapped_message_height = active_message.heightForWidth(message_width)
        if wrapped_message_height > 0:
            # QLabel.heightForWidth() can report the exact text block height
            # without the small amount of vertical breathing room needed by
            # the styled font. At that exact height the first and final lines
            # can be visibly shaved even though the label remains clear of the
            # action row. Keep one bounded line-metric allowance so dense
            # receipts (notably setup completion) render in full.
            message_vertical_allowance = max(
                8,
                int(active_message.fontMetrics().height()),
            )
            active_message.setMinimumHeight(
                wrapped_message_height + message_vertical_allowance
            )
        self.onboarding_layout.invalidate()
        self.onboarding_layout.activate()
        self.onboarding_panel.adjustSize()
        content_height = max(
            self.onboarding_panel.sizeHint().height(),
            self.onboarding_layout.sizeHint().height(),
        )
        height = max(
            104,
            min(content_height, max(112, self.scene.height() - 24)),
        )
        step = self.storage.state.onboarding.step
        if step == OnboardingStep.NURTURE and self._onboarding_plant_id:
            anchor_geometry = self.scene.plant_geometry(self._onboarding_plant_id)
        elif step in {OnboardingStep.INTRODUCTION, OnboardingStep.NURSERY}:
            anchor_geometry = self.scene.landmark_geometry("garden.nursery.open")
        else:
            anchor_geometry = None
        if anchor_geometry is None:
            x, y = 12, 12
        else:
            x = round(anchor_geometry.center().x() - width / 2)
            y = round(anchor_geometry.top() - height - 10)
            if y < 12:
                y = round(anchor_geometry.bottom() + 10)
        x = max(12, min(x, self.scene.width() - width - 12))
        y = max(12, min(y, self.scene.height() - height - 12))
        self.onboarding_panel.setGeometry(x, y, width, height)
        self.onboarding_panel.raise_()

    def _header_actions_content_width(self) -> int:
        """Measure complete visible action copy instead of shrinkable minima."""

        return max(300, int(self.header_actions_widget.sizeHint().width()))

    def _apply_responsive_layout(self, width: int) -> None:
        available = max(0, int(width))
        if not hasattr(self, "dashboard_header_full"):
            return
        header_margins = self.header_grid.contentsMargins()
        header_available = max(
            0,
            available - int(header_margins.left()) - int(header_margins.right()),
        )
        full_header = self.dashboard_header_full.evaluate(header_available)
        title_actions = self.dashboard_header_title_actions.evaluate(header_available)
        metrics = self.dashboard_metrics_responsive.evaluate(header_available)
        milestone = self.dashboard_milestone_responsive.evaluate(available)
        rearrange = self.dashboard_rearrange_responsive.evaluate(available)

        header_compact = full_header.mode == COMPACT_MODE
        header_narrow = header_compact and title_actions.mode == COMPACT_MODE
        metrics_compact = metrics.mode == COMPACT_MODE
        compact = milestone.mode == COMPACT_MODE
        rearrange_compact = rearrange.mode == COMPACT_MODE
        header_mode = (
            "narrow" if header_narrow else
            "compact" if header_compact else
            "wide"
        )
        self.setProperty(
            "layoutMode",
            header_mode,
        )
        self.setProperty("headerMode", header_mode)
        self.setProperty("metricsMode", metrics.mode)
        self.setProperty("milestoneMode", milestone.mode)
        self.setProperty("rearrangeMode", rearrange.mode)
        compact_changed = compact != self._compact_layout
        header_changed = header_compact != self._header_compact_layout
        narrow_changed = header_narrow != self._header_narrow_layout
        metrics_changed = metrics_compact != self._header_metrics_compact
        rearrange_changed = rearrange_compact != self._rearrange_compact_layout
        if (
            not compact_changed
            and not header_changed
            and not narrow_changed
            and not metrics_changed
            and not rearrange_changed
        ):
            return
        if compact_changed:
            self._compact_layout = compact
        self._rearrange_compact_layout = rearrange_compact
        self._header_compact_layout = header_compact
        self._header_narrow_layout = header_narrow
        self._header_metrics_compact = metrics_compact
        # Preserve action copy across responsive modes. The narrow header gives
        # actions their own row, so truncating this label at 700 px is neither
        # necessary nor helpful to keyboard and screen-reader users.
        self.progress_btn.setText("Garden Progress")
        self.progress_btn.setAccessibleName("Garden Progress")
        self.progress_btn.setToolTip("")
        self.progress_btn.setMinimumWidth(0)
        self.garden_stats_bar.set_compact(metrics_compact)
        # The large tabular values need a little more vertical breathing room
        # at high display scaling. Keep this adaptive instead of forcing the
        # metric strip below its child cards' minimum height.
        for widget in (
            self.title_stack_widget,
            self.garden_stats_bar,
            self.header_actions_widget,
        ):
            self.header_grid.removeWidget(widget)
        if header_narrow:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0, 1, 2)
            self.header_grid.addWidget(self.header_actions_widget, 1, 0, 1, 2)
            self.header_grid.addWidget(self.garden_stats_bar, 2, 0, 1, 2)
            self.header_grid.setColumnStretch(0, 1)
            self.header_grid.setColumnStretch(1, 0)
            self.header_grid.setColumnStretch(2, 0)
        else:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0)
            self.header_grid.addWidget(self.header_actions_widget, 0, 1)
            self.header_grid.addWidget(self.garden_stats_bar, 1, 0, 1, 2)
            self.header_grid.setColumnStretch(0, 1)
            self.header_grid.setColumnStretch(1, 0)
            self.header_grid.setColumnStretch(2, 0)
        self._sync_header_minimum_heights()
        self.top_bar.updateGeometry()
        self.header_grid.activate()
        self.top_bar.adjustSize()

    def _sync_header_minimum_heights(self) -> None:
        """Keep first-run status compact without weakening active metrics."""

        guided = bool(getattr(self.garden_stats_bar, "_onboarding_mode", False))
        metrics_compact = bool(self._header_metrics_compact)
        self.garden_stats_bar.setVisible(not guided)
        self.garden_stats_bar.setMinimumHeight(
            0 if guided else (108 if metrics_compact else 54)
        )
        if guided:
            minimum = 56
        else:
            minimum = (
                164 if self._header_narrow_layout and metrics_compact else
                156 if self._header_compact_layout and metrics_compact else
                142 if self._header_narrow_layout else
                102
            )
        self.top_bar.setMinimumHeight(minimum)
        self._sync_dashboard_content_minimum_height()

    def _set_plant_card_mode(self, compact: bool) -> None:
        del compact
        # Actual side-card vs bottom-sheet placement depends on scene width,
        # not the broader dashboard chrome breakpoint.
        QTimer.singleShot(0, self._position_plant_card)

    def _show_docked_plant_card(self, *, full_width: bool) -> None:
        """Use a native bottom sheet only after anchored geometry fails."""

        if self.plant_card.parentWidget() is not self.plant_card_dock:
            self.plant_card.setParent(self.plant_card_dock)
            self.plant_card_dock_layout.addWidget(
                self.plant_card,
                0,
                Qt.AlignmentFlag.AlignHCenter,
            )
        connector = getattr(self.scene, "set_card_connector_geometry", None)
        if callable(connector):
            connector(None)
        available_width = max(
            280,
            self.plant_card_dock.width() or self.scene.width(),
        )
        card_width = available_width if full_width else min(360, available_width)
        self.plant_card.setMaximumWidth(card_width)
        self.plant_card.setFixedWidth(card_width)
        self.plant_card.set_docked_mode(True)
        card_layout = self.plant_card.layout()
        if card_layout is not None:
            card_layout.activate()
        self.plant_card.adjustSize()
        self.plant_card.setMinimumHeight(int(self.plant_card.sizeHint().height()) + 4)
        self.plant_card.show()
        self.plant_card_dock.show()

    def _position_plant_card(self) -> None:
        if not hasattr(self, "plant_card") or not self.plant_card.plant_id or self.scene._interaction.placing:
            if hasattr(self, "plant_card"):
                self.plant_card.hide()
            if hasattr(self, "plant_card_dock"):
                self.plant_card_dock.hide()
            if hasattr(self, "scene"):
                connector = getattr(self.scene, "set_card_connector_geometry", None)
                if callable(connector):
                    connector(None)
            return
        if hasattr(self, "plant_card_dock"):
            self.plant_card_dock.hide()
        if self.plant_card.parentWidget() is not self.scene:
            self.plant_card.setParent(self.scene)
        self.plant_card.set_docked_mode(False)
        self.plant_card.setMinimumHeight(0)
        if hasattr(self.plant_card, "setMaximumWidth"):
            self.plant_card.setMaximumWidth(340)
        available_width = max(300, self.scene.width() - 24)
        desired_width = min(320, available_width)
        def measured_height(width: int) -> int:
            self.plant_card.setFixedWidth(int(width))
            card_layout = self.plant_card.layout()
            if card_layout is not None:
                card_layout.activate()
            self.plant_card.adjustSize()
            # Qt's wrapped-label size hint can settle before the two-row action
            # grid has received its final width. Reserve the grid's vertical gap
            # so 125–150% font scaling never compresses the 40 px action targets.
            action_height_reserve = (
                72 if self.plant_card.choose_another.isVisible() else 24
            )
            return min(
                420,
                max(220, self.plant_card.sizeHint().height() + action_height_reserve),
            )

        desired_height = measured_height(desired_width)
        card_height = min(desired_height, max(220, self.scene.height() - 24))
        geometry = self.scene.card_geometry(desired_width, card_height)
        if geometry is None:
            # A dense mature scene can leave no overlay lane that protects the
            # selected plant. Preserve the user's selection in a docked card
            # instead of silently making every action disappear.
            self._show_docked_plant_card(full_width=self.scene.width() < 600)
            return
        placement_reader = getattr(self.scene, "card_popover_placement", None)
        placement = placement_reader() if callable(placement_reader) else None
        docked = bool(getattr(placement, "docked", False))
        resolved_width = max(1, round(geometry.width()))
        if resolved_width != desired_width:
            # The scene resolver may offer either a narrower side lane or its
            # full-width, in-scene bottom dock. Reflow the real Qt content at
            # that exact width, then resolve again with its measured size as a
            # hard floor. Only a missing rectangle needs the external dock.
            resolved_height = min(
                measured_height(resolved_width),
                max(220, self.scene.height() - 24),
            )
            geometry = self.scene.card_geometry(
                resolved_width,
                resolved_height,
                minimum_width=resolved_width,
                minimum_height=resolved_height,
            )
            if geometry is None:
                self._show_docked_plant_card(full_width=self.scene.width() < 600)
                return
            placement = placement_reader() if callable(placement_reader) else None
            docked = bool(getattr(placement, "docked", False))
            card_height = resolved_height
        actual_width = self.plant_card.width()
        actual_height = card_height
        if (
            geometry.width() + 0.5 < actual_width
            or geometry.height() + 0.5 < actual_height
        ):
            self._show_docked_plant_card(full_width=self.scene.width() < 600)
            return
        self.plant_card.set_docked_mode(docked)
        self.plant_card.setMaximumWidth(
            max(340, round(geometry.width())) if docked else 340
        )
        connector = getattr(self.scene, "set_card_connector_geometry", None)
        if callable(connector):
            connector(geometry, self.plant_card.plant_id)
        self.plant_card.setGeometry(
            round(geometry.x()), round(geometry.y()), round(geometry.width()), round(geometry.height())
        )
        self.plant_card.show()
        self.plant_card.raise_()
        self._position_scene_overlays()

    def _refresh_selected_plant_card(self) -> None:
        selected = self.scene.selected_plant_id()
        if not selected:
            return
        plant = self.engine.plant_story(selected)
        if plant is None or not plant.planted:
            self.scene.dismiss_selection()
            return
        self.plant_card.set_selected(self._plant_scene_payload(plant))
        self._position_plant_card()

    def _refresh_timed_plant_statuses(self) -> None:
        """Refresh countdown copy and invalidate forecasts exactly at expiry."""

        now = time.time()
        active = self.engine.active_plant()
        active_status = (
            fertilizer_status(
                self.engine,
                active,
                now=now,
                description=FERTILIZER_EXPLANATION,
            )
            if active is not None else
            None
        )
        active_phase = (
            str(getattr(active, "plant_id", "") or ""),
            active_status.phase if active_status is not None else "inactive",
        )
        previous_phase = getattr(self, "_active_fertilizer_phase", None)
        self._active_fertilizer_phase = active_phase

        selected_id = self.scene.selected_plant_id()
        selected = self.engine.plant_story(selected_id) if selected_id else None
        selected_status = (
            fertilizer_status(
                self.engine,
                selected,
                now=now,
                description=FERTILIZER_EXPLANATION,
            )
            if selected is not None else
            None
        )
        selected_token = (
            str(selected_id or ""),
            selected_status.phase if selected_status is not None else "inactive",
            selected_status.duration if selected_status is not None else "",
        )
        if selected_token != getattr(self, "_selected_fertilizer_token", None):
            self._selected_fertilizer_token = selected_token
            self._refresh_selected_plant_card()

        if previous_phase is not None and active_phase != previous_phase:
            self.refresh_all()

    @staticmethod
    def _is_widget_descendant(widget: Any, ancestor: QWidget) -> bool:
        current = widget if isinstance(widget, QWidget) else None
        while current is not None:
            if current is ancestor:
                return True
            current = current.parentWidget()
        return False

    def eventFilter(self, watched: Any, event: Any) -> bool:
        belongs_to_dashboard = (
            isinstance(watched, QWidget)
            and (watched is self or self.isAncestorOf(watched))
        )
        if (
            hasattr(self, "scene")
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
            and belongs_to_dashboard
        ):
            if bool(self.rearrange_bar.property("error")):
                self._cancel_move()
                return True
            if self.scene._interaction.placing:
                self._cancel_move()
                return True
            if self.scene.selected_plant_id():
                self.scene.dismiss_selection()
                return True
        if (
            hasattr(self, "scene")
            and self.scene.selected_plant_id()
            and not self.scene._interaction.placing
            and event.type() == QEvent.Type.MouseButtonPress
            and belongs_to_dashboard
            and not self._is_widget_descendant(watched, self.plant_card)
            and watched is not self.scene
        ):
            self.scene.dismiss_selection()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if bool(self.rearrange_bar.property("error")):
                self._cancel_move()
                event.accept()
                return
            if self.scene._interaction.placing:
                self._cancel_move()
                event.accept()
                return
            if self.scene.selected_plant_id():
                self.scene.dismiss_selection()
                event.accept()
                return
        super().keyPressEvent(event)

    def done(self, result: int) -> None:
        """Refresh the underlying Anki home surface after the modal dashboard closes."""
        self._fertilizer_timer.stop()
        if self._starter_placement_active:
            self._starter_placement_active = False
            self._active_placement_token = None
            self.scene.finish_move("Starter placement paused. Resume it when you return.")
            self.rearrange_bar.hide()
            self.rearrange_bar.cancel.setText("Cancel")
        elif self.scene._interaction.placing:
            self._cancel_move()
        if self.scene.selected_plant_id():
            self.scene.dismiss_selection()
        application = QGuiApplication.instance()
        if application is not None and self._application_filter_installed:
            application.removeEventFilter(self)
            self._application_filter_installed = False
        super().done(result)
        QTimer.singleShot(0, self.refresh_external_surfaces)

    def _update_scene_height(self, viewport_height: int | None = None) -> None:
        if not hasattr(self, "scene"):
            return
        self._sync_feedback_panel_visibility()
        window_height = int(viewport_height or self.height())
        minimum_height = round(
            responsive_interpolate(
                window_height,
                560,
                680,
                220,
                260,
            )
        )
        self.scene.setMinimumHeight(minimum_height)
        self.scene.setMaximumHeight(16777215)
        self.scene.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._sync_dashboard_content_minimum_height()

    def _sync_feedback_panel_visibility(self) -> bool:
        """Collapse the transient row unless it contains real visible copy."""

        if not hasattr(self, "feedback_panel"):
            return False
        rows = (
            self.stage_transition_note,
            self.same_day_catchup_note,
            self.status_notice,
        )
        visible = any(
            not row.isHidden() and bool(str(row.text() or "").strip())
            for row in rows
        )
        self.feedback_panel.setVisible(visible)
        return visible

    def refresh_external_surfaces(self) -> None:
        """Refresh Anki webviews after a dashboard mutation changes home-card data."""
        try:
            if not bool(getattr(self, "_home_surface_dirty", True)):
                return
            state = str(getattr(self.mw_window, "state", ""))
            surface_name = {"deckBrowser": "deckBrowser", "overview": "overview"}.get(state)
            if surface_name is None:
                return
            reset = getattr(self.mw_window, "reset", None)
            if callable(reset):
                reset()
            surface = getattr(self.mw_window, surface_name, None) if surface_name else None
            refresh = getattr(surface, "refresh", None)
            if callable(refresh):
                refresh()
            self._home_surface_dirty = False
        except Exception:
            logger.exception("Anki Garden: unable to refresh Anki home surfaces")

    def _refresh_after_commit(self, context: str) -> None:
        """Publish one post-commit event shared by every visible Garden surface."""
        USER_NOTICES.clear(key="display_refresh")
        self.state_events.notify(context)

    def _on_state_changed(self, context: str) -> None:
        """Refresh views without turning a saved mutation into an ambiguous failure."""
        self._home_surface_dirty = True
        try:
            if not self.isVisible():
                return
        except RuntimeError:
            return
        if context in {"plant arrangement", "plant move", "move undo"}:
            try:
                self._refresh_move_scene()
            except Exception:
                logger.exception("Anki Garden: %s was saved but the move scene could not refresh", context)
            return
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: %s was saved but the Garden refresh failed", context)
            USER_NOTICES.publish(
                "Your change was saved, but the display could not refresh. "
                "Reopen Anki Garden to try again.",
                key="display_refresh",
            )

    def _refresh_move_scene(self) -> None:
        """Refresh only slot geometry after a move; artwork and catalogs are unchanged."""
        slots = {
            str(plant.plant_id): int(plant.slot_index)
            for plant in self.storage.state.plants
            if plant.slot_index is not None
        }
        updater = getattr(self.scene, "update_plant_slots", None)
        if callable(updater):
            updater(slots)
            return
        # Compatibility fallback for older scene wrappers and focused tests.
        self.refresh_all()

    def show_same_day_catchup_feedback(self, review_count: int, growth_gain: int) -> None:
        if review_count <= 0:
            self.same_day_catchup_note.setText("")
            self.same_day_catchup_note.setAccessibleDescription("")
            self.same_day_catchup_note.hide()
            self._sync_feedback_panel_visibility()
            return
        self.same_day_catchup_note.show()
        self.same_day_catchup_note.setText(
            f"Counted {_card_answer_count(review_count)} from same-day sync: "
            f"+{growth_gain:,} Growth."
        )
        self.same_day_catchup_note.setAccessibleDescription(self.same_day_catchup_note.text())
        self._sync_feedback_panel_visibility()

    def _plant_scene_payload(self, plant: Any) -> dict[str, Any]:
        display = growth_display(plant.growth_points)
        snapshot = select_garden_ui(self.engine, self.storage)
        plant_snapshot = next(
            (
                item for item in snapshot.plants
                if item.plant_id == str(plant.plant_id)
            ),
            None,
        )
        staged_slots = self._placement_draft.scene_slots() if self._placement_draft is not None else {}
        current_time = time.time()
        fertilizer_projection = fertilizer_status(
            self.engine,
            plant,
            now=current_time,
            description=FERTILIZER_EXPLANATION,
        )
        fertilizer_growth = self.engine.fertilizer_growth(plant, now=current_time)
        booster_growth = self.engine.booster_growth(plant)
        return {
            "plant_id": plant.plant_id,
            "slot_index": staged_slots.get(plant.plant_id, plant.slot_index),
            "name": plant.name,
            "species": plant.species,
            "stage": display.stage,
            "growth_points": plant.growth_points,
            "next_stage": display.next_stage,
            "next_threshold": display.next_threshold,
            "points_remaining": display.points_remaining,
            "stage_progress": display.progress,
            "stage_points": display.stage_points,
            "stage_goal": display.stage_goal,
            "fully_grown": display.fully_grown,
            "streak_bonus_percent": self.engine.current_streak_bonus_percent(),
            "fertilizer_growth": fertilizer_growth,
            "booster_growth": booster_growth,
            "growth_today": (
                plant_snapshot.growth_today if plant_snapshot is not None else 0
            ),
            "nurtured_growth_today": (
                plant_snapshot.nurtured_growth_today
                if plant_snapshot is not None else 0
            ),
            "passive_growth_fifths_today": (
                plant_snapshot.passive_growth_fifths_today
                if plant_snapshot is not None else 0
            ),
            "passive_growth_credited_today": (
                plant_snapshot.passive_growth_credited_today
                if plant_snapshot is not None else 0
            ),
            "passive_remainder_fifths": (
                plant_snapshot.passive_remainder_fifths
                if plant_snapshot is not None else 0
            ),
            "charge_growth_today": (
                plant_snapshot.charge_growth_today
                if plant_snapshot is not None else 0
            ),
            "direct_reward_growth_today": (
                plant_snapshot.direct_reward_growth_today
                if plant_snapshot is not None else 0
            ),
            "allocation_type": (
                plant_snapshot.allocation_type
                if plant_snapshot is not None else "No Growth today"
            ),
            "fertilizer_status": dict(fertilizer_projection.__dict__),
            "fertilizer_text": self._fertilizer_text(plant),
            "booster_text": self._booster_text(plant),
            "is_active": plant.plant_id == self.storage.state.active_plant_id,
            "asset": self._resolved_asset_payload(
                "resolve_plant_asset",
                "resolve_plant_image",
                plant.species,
                plant.growth_stage,
            ),
            "nurtured_badge_asset": self._resolved_asset_payload(
                "resolve_nurtured_marker_asset",
                "resolve_nurtured_marker_image",
            ),
        }

    def _settings_scene_snapshot(self) -> dict[str, Any]:
        state = self.storage.state
        active = self.engine.active_plant()
        active_progress = growth_display(active.growth_points).progress if active is not None else 0.0
        return {
            "garden_name": str(getattr(state, "garden_name", "My Garden") or "My Garden"),
            "starter_selected": bool(
                getattr(state, "starter_selection_complete", bool(state.plants))
            ),
            "weather": state.selected_weather,
            "background": str(getattr(state, "selected_background", "verdant_twilight") or "verdant_twilight"),
            "unlocked_slots": state.unlocked_slots,
            "growth": active_progress,
            "streak_days": state.streak_days,
            "streak_bonus_percent": self.engine.current_streak_bonus_percent(),
            "currency_balance": max(0, int(getattr(state, "currency_balance", 0) or 0)),
            "plants": [
                {
                    "plant_id": plant.plant_id,
                    "slot_index": plant.slot_index,
                    "name": plant.name,
                    "species": plant.species,
                    "stage": plant.growth_stage,
                    "growth_points": plant.growth_points,
                    "is_active": plant.plant_id == state.active_plant_id,
                }
                for plant in state.plants
                if plant.slot_index is not None
            ],
        }

    def _fertilizer_text(self, plant: Any) -> str:
        if plant is None:
            return "No active Fertilizer"
        status = fertilizer_status(
            self.engine,
            plant,
            now=time.time(),
            description=FERTILIZER_EXPLANATION,
        )
        if not status.active:
            return "No active Fertilizer"
        return f"{status.name}: {status.effect}\n{status.duration}"

    def _booster_text(self, plant: Any) -> str:
        booster = getattr(plant, "booster", None)
        if booster is None:
            return "None active"
        remaining = max(0, int(float(getattr(booster, "expires_at", 0) or 0) - time.time()))
        if remaining <= 0:
            return "None active"
        minutes = max(1, (remaining + 59) // 60)
        hours, minutes = divmod(minutes, 60)
        duration = (
            f"{hours}h {minutes}m" if hours and minutes
            else f"{hours}h" if hours
            else f"{minutes}m"
        )
        return (
            f"+{int(getattr(booster, 'growth_per_answer', 0))} Growth per Anki card answer, "
            f"{duration} remaining"
        )

    def _resolved_asset_payload(self, structured_name: str, legacy_name: str, *args: Any) -> Any:
        resolver = getattr(self.engine, structured_name, None)
        try:
            if callable(resolver):
                asset = resolver(*args)
                if asset is not None and hasattr(asset, "to_payload"):
                    return asset.to_payload()
        except Exception:
            logger.exception("Anki Garden: structured artwork resolution failed for %s", structured_name)
        legacy = getattr(self.engine, legacy_name, None)
        try:
            return legacy(*args) if callable(legacy) else None
        except Exception:
            logger.exception("Anki Garden: fallback artwork resolution failed for %s", legacy_name)
            return None

    def _nurture_plant(self, plant_id: str) -> None:
        if self.storage.state.active_plant_id == plant_id:
            if self.storage.state.onboarding.step == OnboardingStep.NURTURE:
                ok, message = self.engine.set_active_plant(plant_id)
                if not ok:
                    self.toast_region.show_message(message, error=True, duration_ms=0)
                    return
                self._refresh_after_commit("nurtured-plant onboarding resume")
            self.scene.keep_card_open(plant_id)
            self._refresh_selected_plant_card()
            self._complete_first_nurture_guidance()
            return
        previous_id = str(self.storage.state.active_plant_id or "")
        ok, message = self.engine.set_active_plant(plant_id)
        if not ok:
            self.toast_region.show_message(message, error=True, duration_ms=0)
            return
        self._undo_nurture_plant_id = previous_id
        self._refresh_after_commit("nurtured-plant choice")
        self.scene.keep_card_open(plant_id)
        self._refresh_selected_plant_card()
        previous = self.engine.plant_story(previous_id) if previous_id else None
        selected = self.engine.plant_story(plant_id)
        selected_name = str(getattr(selected, "name", "This plant"))
        toast_copy = f"{selected_name} is now nurtured."
        self.scene.show_nurture_feedback(plant_id)
        can_undo = previous is not None and bool(getattr(previous, "planted", False))
        self.toast_region.show_message(
            toast_copy,
            action_text="Undo Nurture" if can_undo else "",
            callback=self._undo_nurture if can_undo else None,
            duration_ms=6000 if can_undo else 3500,
        )
        self._complete_first_nurture_guidance()

    def _undo_nurture(self) -> None:
        previous_id = self._undo_nurture_plant_id
        self._undo_nurture_plant_id = ""
        if not previous_id:
            return
        ok, message = self.engine.set_active_plant(previous_id)
        if not ok:
            self.toast_region.show_message(message, error=True, duration_ms=0)
            return
        self._refresh_after_commit("nurtured-plant undo")
        self.scene.keep_card_open(previous_id)
        self._refresh_selected_plant_card()
        self.toast_region.show_message("Nurture choice restored.")

    def _open_plant_story(self, plant_id: str) -> None:
        self.story_dialog = PlantStoryDialog(self, self.engine, plant_id)
        self.story_dialog.remember_invoker(self.plant_card.story)
        self.story_dialog.chooseAnother.connect(self._choose_another_plant)
        self.story_dialog.exec()
        self._refresh_after_commit("Plant Story")

    def _open_growth_charges_for_plant(self, plant_id: str) -> None:
        plant = self.engine.plant_story(plant_id)
        if (
            plant is None
            or plant not in self.storage.state.plants
            or not bool(getattr(plant, "planted", False))
            or bool(getattr(plant, "fully_grown", False))
        ):
            self.toast_region.show_message(
                "This plant can’t use a Growth Charge.",
                error=True,
            )
            return
        dialog = GrowthChargeConfirmationDialog(
            self,
            self.engine,
            plant_id,
            open_nursery=self._open_nursery,
        )
        dialog.remember_invoker(self.plant_card.growth_charge)
        self.growth_charge_dialog = dialog
        dialog.exec()
        if dialog.outcome is not None and dialog.outcome.success:
            self._refresh_after_commit("Growth Charge")
            self.toast_region.show_message(dialog.outcome.message)

    def _choose_another_plant(self) -> None:
        """Route a completed plant to an unfinished owned plant or Nursery."""

        plants = list(getattr(self.storage.state, "plants", []) or [])
        unfinished = next((plant for plant in plants if not bool(getattr(plant, "fully_grown", False))), None)
        if unfinished is not None and bool(getattr(unfinished, "planted", False)):
            self.scene.keep_card_open(str(unfinished.plant_id), FULLY_GROWN_MESSAGE)
            return
        if unfinished is not None:
            self._open_nursery(status_message=f"Choose {unfinished.name} to nurture next.")
            return
        self._open_nursery()

    def _remember_move_focus(self, plant_id: str) -> None:
        if self._move_focus_return is None:
            focused = QApplication.focusWidget()
            self._move_focus_return = (
                focused
                if isinstance(focused, QWidget) and self.isAncestorOf(focused)
                else self.plant_card.move
            )
        self._move_focus_plant_id = str(plant_id)

    def _restore_move_focus(self, plant_id: str) -> None:
        """Return keyboard focus to the original plant after move teardown."""

        plant_id = str(plant_id or self._move_focus_plant_id or "")
        target = self._move_focus_return
        self._move_focus_return = None
        self._move_focus_plant_id = ""
        if plant_id:
            self.scene.keep_card_open(plant_id)
            self._refresh_selected_plant_card()
        if target is None:
            target = self.plant_card.move if plant_id else self.scene

        def restore() -> None:
            try:
                if target.isVisibleTo(self) and target.isEnabled():
                    target.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except (AttributeError, RuntimeError):
                pass
            self.scene.setFocus(Qt.FocusReason.OtherFocusReason)

        QTimer.singleShot(0, restore)

    def _record_active_placement_token(self) -> None:
        token_reader = getattr(self.scene, "active_placement_token", None)
        self._active_placement_token = (
            token_reader() if callable(token_reader) else None
        )

    def _placement_callback_is_current(self, request_token: int | None) -> bool:
        current_reader = getattr(self.scene, "active_placement_token", None)
        scene_token = current_reader() if callable(current_reader) else None
        candidate = int(request_token) if request_token is not None else None
        return bool(
            candidate is not None
            and scene_token == candidate
            and self._active_placement_token == candidate
        )

    def _begin_move(self, plant_id: str) -> None:
        ok, message, draft = self.engine.begin_placement_draft(plant_id)
        if not ok or draft is None:
            self.scene.keep_card_open(plant_id, _learner_text(message))
            return
        # Starting a new move retires the previous popup's Undo contract.
        self._undo_placement = None
        self.toast_region.clear()
        self._placement_draft = draft
        plant = next((row for row in self.storage.state.plants if row.plant_id == plant_id), None)
        name = str(getattr(plant, "name", "Plant"))
        move_message = "Choose a bed."
        self.rearrange_bar.plant_id = plant_id
        self.rearrange_bar.clear_failure()
        self.rearrange_bar.title.setText(f"Move {name}")
        self.rearrange_bar.instructions.setText(move_message)
        scene_slots_method = getattr(draft, "scene_slots", None)
        scene_slots = (
            scene_slots_method()
            if callable(scene_slots_method) else
            {
                row.plant_id: int(row.slot_index)
                for row in self.storage.state.plants
                if getattr(row, "slot_index", None) is not None
            }
        )
        origin_slot = scene_slots.get(plant_id)
        valid_destinations = [
            int(slot) for slot in self.engine.valid_destination_slots(draft)
            if int(slot) != origin_slot
        ]
        if not valid_destinations:
            self._placement_draft = None
            self._active_placement_token = None
            self._failed_move_destination = None
            self.rearrange_bar.clear_failure()
            self.toast_region.show_message(
                "No valid destination is available for this plant.",
                error=True,
                duration_ms=4500,
            )
            if self._move_focus_return is not None:
                self._restore_move_focus(plant_id)
            return
        self._remember_move_focus(plant_id)
        self._failed_move_destination = None
        allowed_slots = ([int(origin_slot)] if origin_slot is not None else []) + valid_destinations
        if self.scene.begin_move(plant_id, allowed_slots):
            self._record_active_placement_token()
            self.rearrange_bar.show()
            self.scene.setFocus()
            QTimer.singleShot(0, self._position_scene_overlays)
        else:
            self._placement_draft = None
            self._active_placement_token = None
            self._restore_move_focus(plant_id)

    def _refresh_rearrange_destinations(self, plant_id: str) -> None:
        draft = self._placement_draft
        slots = draft.scene_slots() if draft is not None else {
            plant.plant_id: int(plant.slot_index)
            for plant in self.storage.state.plants
            if plant.slot_index is not None
        }
        current_slot = slots.get(plant_id)
        names = {plant.plant_id: plant.name for plant in self.storage.state.plants}
        occupied = {slot: names.get(occupant_id, "plant") for occupant_id, slot in slots.items()}
        valid_slots = set(self.engine.valid_destination_slots(draft)) if draft is not None else set()
        self.rearrange_bar.set_destinations([
            (
                f"Space {slot + 1} — " + (
                    "Current"
                    if slot == current_slot else
                    f"Swap with {occupied[slot]}"
                    if slot in occupied else
                    "Move here"
                ),
                slot,
            )
            for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
            if slot in valid_slots
        ])

    def _cancel_move(self) -> None:
        if self._starter_placement_active:
            self._starter_placement_active = False
            self._active_placement_token = None
            self.rearrange_bar.clear_failure()
            self.scene.finish_move("Starter placement cancelled. Returning to confirmation.")
            self.rearrange_bar.hide()
            self.rearrange_bar.cancel.setText("Cancel")
            ok, message = self.engine.back_onboarding()
            if not ok:
                self._onboarding_save_error = message
                self._refresh_onboarding()
                return
            self._onboarding_save_error = ""
            self._refresh_after_commit("onboarding placement back")
            QTimer.singleShot(0, self._show_starter_confirmation)
            return
        if self._collection_placement_plant_id:
            self._collection_placement_plant_id = ""
            self._active_placement_token = None
            self.rearrange_bar.clear_failure()
            self.scene.finish_move("Planting cancelled. Returning to Collection.")
            self.rearrange_bar.hide()
            self.rearrange_bar.cancel.setText("Cancel")
            QTimer.singleShot(0, self._open_collection)
            return
        selected_id = str(
            getattr(self._placement_draft, "selected_plant_id", "")
            or self._move_focus_plant_id
            or ""
        )
        self._placement_draft = None
        self._active_placement_token = None
        self._failed_move_destination = None
        self.rearrange_bar.clear_failure()
        self.scene.finish_move("Move cancelled. Plant selection remains available.")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: move cancelled but persisted scene did not refresh")
        self.toast_region.clear()
        if selected_id:
            self._restore_move_focus(selected_id)
        else:
            self.scene.setFocus(Qt.FocusReason.OtherFocusReason)

    def _finish_failed_move(self, message: str) -> None:
        """Restore persisted slots and expose explicit retry/cancel actions."""

        del message
        failure_copy = "Your garden is unchanged."
        selected_id = str(
            getattr(self._placement_draft, "selected_plant_id", "") or ""
        )
        self._placement_draft = None
        self._active_placement_token = None
        self.scene.finish_move(failure_copy)
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: rejected move could not refresh persisted scene")
        retry_started = False
        engine = getattr(self, "engine", None)
        begin_retry = getattr(engine, "begin_placement_draft", None)
        if selected_id and callable(begin_retry):
            ok, _retry_message, retry_draft = begin_retry(selected_id)
            if ok and retry_draft is not None:
                self._placement_draft = retry_draft
                retry_slots = retry_draft.scene_slots()
                origin_slot = retry_slots.get(selected_id)
                valid_destinations = [
                    int(slot)
                    for slot in engine.valid_destination_slots(retry_draft)
                    if int(slot) != origin_slot
                ]
                allowed_slots = (
                    ([int(origin_slot)] if origin_slot is not None else [])
                    + valid_destinations
                )
                retry_started = self.scene.begin_move(
                    selected_id,
                    allowed_slots,
                )
                if retry_started:
                    self._record_active_placement_token()
        if not retry_started and selected_id:
            self.scene.keep_card_open(selected_id, failure_copy)
            self._refresh_selected_plant_card()
        self.rearrange_bar.plant_id = selected_id
        self.rearrange_bar.set_failure(failure_copy)
        self.overlay_manager.move_mode_changed(True)
        self._position_scene_overlays()
        self.rearrange_bar.retry.setFocus(Qt.FocusReason.OtherFocusReason)

    def _retry_failed_move(self) -> None:
        plant_id = str(
            getattr(self._placement_draft, "selected_plant_id", "")
            or self._move_focus_plant_id
            or self.rearrange_bar.plant_id
            or ""
        )
        destination = self._failed_move_destination
        if (
            plant_id
            and destination is not None
            and self._placement_draft is not None
            and self.scene._interaction.placing
        ):
            self._place_plant(
                plant_id,
                int(destination),
                self._active_placement_token,
            )
            return
        self._placement_draft = None
        self._active_placement_token = None
        self.scene.finish_move("Preparing to retry the move.")
        self.rearrange_bar.hide()
        self.toast_region.clear()
        if plant_id:
            self._begin_move(plant_id)

    def _done_move(self) -> None:
        draft = self._placement_draft
        if draft is None:
            return
        plant_id = draft.selected_plant_id
        ok, message, change = self.engine.commit_placement_draft(draft)
        if not ok or change is None:
            self._finish_failed_move(message)
            return
        self._placement_draft = None
        self._active_placement_token = None
        self._failed_move_destination = None
        self.rearrange_bar.clear_failure()
        self._undo_placement = change if change.before != change.after else None
        self.scene.finish_move("Plant arrangement saved. Undo is available.")
        self.rearrange_bar.hide()
        self._refresh_after_commit("plant arrangement")
        self.scene.keep_card_open(plant_id)
        self._refresh_selected_plant_card()
        if self._undo_placement is not None:
            self.toast_region.show_message(
                "Plant arrangement saved.",
                action_text="Undo Move",
                callback=self._undo_move,
            )
        self._restore_move_focus(plant_id)

    def _apply_native_destination(self) -> None:
        destination = self.rearrange_bar.selected_destination()
        if destination is None or not self.rearrange_bar.plant_id:
            return
        self._place_plant(
            self.rearrange_bar.plant_id,
            destination,
            self._active_placement_token,
        )

    def _confirm_occupied_bed_swap(self, moving: Any, occupant: Any) -> bool:
        """Ask only after an occupied destination has been selected."""

        box = QMessageBox(self)
        box.setWindowTitle(UI_TEXT["app_title"])
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Swap {moving.name} with {occupant.name}?")
        swap = box.addButton("Swap", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is swap

    def _resume_move_after_swap_cancel(self, plant_id: str, draft: Any) -> None:
        origin_slot = draft.scene_slots().get(plant_id)
        valid_destinations = [
            int(slot)
            for slot in self.engine.valid_destination_slots(draft)
            if int(slot) != origin_slot
        ]
        allowed_slots = (
            ([int(origin_slot)] if origin_slot is not None else [])
            + valid_destinations
        )
        self._failed_move_destination = None
        if self.scene.begin_move(plant_id, allowed_slots):
            self._record_active_placement_token()
            self.rearrange_bar.clear_failure()
            self.rearrange_bar.instructions.setText("Choose a bed.")
            self.rearrange_bar.show()
            self.scene.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        self._placement_draft = None
        self._active_placement_token = None
        self.scene.finish_move("Move cancelled.")
        self.rearrange_bar.hide()
        self._restore_move_focus(plant_id)

    def _place_plant(
        self,
        plant_id: str,
        destination_slot: int,
        request_token: int | None = None,
    ) -> None:
        if not self._placement_callback_is_current(request_token):
            return
        if self._starter_placement_active and plant_id == "__starter__":
            ok, message, plant = self.engine.place_starter(destination_slot)
            if not ok or plant is None:
                self._starter_placement_active = False
                self._active_placement_token = None
                self.scene.finish_move(
                    "Couldn’t save your garden. Nothing was changed."
                )
                self.rearrange_bar.hide()
                self.rearrange_bar.cancel.setText("Cancel")
                self.toast_region.clear()
                self._onboarding_save_error = message
                self._refresh_onboarding()
                return
            self._starter_placement_active = False
            self._active_placement_token = None
            self._onboarding_save_error = ""
            self.scene.finish_move("Starter planted. Continue to nurture selection.")
            self.rearrange_bar.hide()
            self.rearrange_bar.cancel.setText("Cancel")
            self._on_starter_selected(plant, message)
            self._refresh_after_commit("starter placement")
            return
        if self._collection_placement_plant_id == plant_id:
            ok, message = self.engine.plant_from_collection(plant_id, destination_slot)
            if not ok:
                occupied = {
                    item.slot_index for item in self.storage.state.plants
                    if item.slot_index is not None
                }
                plant = self.engine.plant_story(plant_id)
                allowed = [
                    slot
                    for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
                    if slot not in occupied
                    and plant is not None
                    and self.engine.slot_accepts_plant(plant, slot)
                ]
                failure_copy = "The plant was not placed. Your garden is unchanged."
                if self.scene.begin_collection_placement(plant_id, allowed):
                    self._record_active_placement_token()
                    self.rearrange_bar.set_failure(failure_copy)
                    self.rearrange_bar.show()
                    self.rearrange_bar.retry.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
                self._collection_placement_plant_id = ""
                self._active_placement_token = None
                self.scene.finish_move(failure_copy)
                self.rearrange_bar.clear_failure()
                self.rearrange_bar.hide()
                self.rearrange_bar.cancel.setText("Cancel")
                self.toast_region.show_message(
                    f"{failure_copy} {_learner_text(message)}",
                    action_text="Return to Collection",
                    callback=self._open_collection,
                    error=True,
                    duration_ms=0,
                    dismissible=False,
                )
                return
            self._collection_placement_plant_id = ""
            self._active_placement_token = None
            self.scene.finish_move(_learner_text(message))
            self.rearrange_bar.hide()
            self._refresh_after_commit("collection plant placement")
            self.scene.keep_card_open(plant_id)
            self.toast_region.show_message(_learner_text(message))
            return
        draft = self._placement_draft
        if draft is None or draft.selected_plant_id != plant_id:
            self._finish_failed_move("That move session is no longer available.")
            return
        self._failed_move_destination = int(destination_slot)
        if bool(self.rearrange_bar.property("error")):
            moving_plant = next(
                (row for row in self.storage.state.plants if row.plant_id == plant_id),
                None,
            )
            self.rearrange_bar.clear_failure()
            self.rearrange_bar.title.setText(
                f"Move {getattr(moving_plant, 'name', 'Plant')}"
            )
            self.rearrange_bar.instructions.setText("Choose a bed.")
            self.rearrange_bar.cancel.setText("Cancel")
            self.toast_region.clear()
        before_slots = draft.scene_slots()
        origin_slot = before_slots.get(plant_id)
        moving = next((p for p in self.storage.state.plants if p.plant_id == plant_id), None)
        occupant_id = next((pid for pid, slot in before_slots.items() if slot == destination_slot), None)
        occupant = next((p for p in self.storage.state.plants if p.plant_id == occupant_id), None)
        if (
            moving is not None
            and occupant is not None
            and not self._confirm_occupied_bed_swap(moving, occupant)
        ):
            self._resume_move_after_swap_cancel(plant_id, draft)
            return
        ok, message, change = self.engine.stage_placement(draft, destination_slot)
        if not ok or change is None:
            self._finish_failed_move(message)
            return
        ok, message, committed = self.engine.commit_placement_draft(draft)
        if not ok or committed is None:
            self._finish_failed_move(message)
            return
        if moving is not None and occupant is not None:
            result = f"{moving.name} and {occupant.name} swapped."
        elif moving is not None:
            result = f"{moving.name} moved."
        else:
            result = message
        result = _learner_text(result)
        self._placement_draft = None
        self._active_placement_token = None
        self._failed_move_destination = None
        self._undo_placement = committed if committed.before != committed.after else None
        self.scene.finish_move(f"{result} Undo is available.")
        self.rearrange_bar.hide()
        self._refresh_after_commit("plant move")
        self.scene.keep_card_open(plant_id)
        self._refresh_selected_plant_card()
        if origin_slot is not None:
            self.scene.animate_plant_move(plant_id, int(origin_slot), int(destination_slot))
        if self._undo_placement is not None:
            self.toast_region.show_message(
                result,
                action_text="Undo Move",
                callback=self._undo_move,
            )
        self._restore_move_focus(plant_id)

    def _undo_move(self) -> None:
        if self._placement_draft is not None:
            ok, message = self.engine.undo_staged_placement(self._placement_draft)
            if ok:
                plant_id = self._placement_draft.selected_plant_id
                slots = self._placement_draft.scene_slots()
                updater = getattr(self.scene, "update_plant_slots", None)
                if callable(updater):
                    updater(slots)
                else:
                    self.refresh_all()
                self._refresh_rearrange_destinations(plant_id)
                restarted = self.scene.begin_move(
                    plant_id,
                    self.engine.valid_destination_slots(self._placement_draft),
                )
                if restarted:
                    self._record_active_placement_token()
                message = _learner_text(message)
                can_undo = bool(self._placement_draft.history)
                self.toast_region.show_message(
                    message,
                    action_text="Undo Move" if can_undo else "",
                    callback=self._undo_move if can_undo else None,
                )
            return
        if self._undo_placement is None:
            return
        ok, message, _inverse = self.engine.restore_placement(self._undo_placement)
        if ok:
            self._undo_placement = None
            self._refresh_after_commit("move undo")
            self.toast_region.show_message("Move undone.")
            self.scene.setFocus()
        else:
            message = _learner_text(message)
            retryable = message == "The previous arrangement could not be restored."
            if not retryable:
                self._undo_placement = None
            self.toast_region.show_message(
                message,
                action_text="Retry Undo" if retryable else "",
                callback=self._undo_move if retryable else None,
                error=True,
                duration_ms=0,
            )
            self.toast_region.setFocus()

    def _refresh_onboarding(self) -> None:
        display = onboarding_state_display(
            self.storage.state,
            self.config.value("onboarding_version", 0),
        )
        step = display.step or self.storage.state.onboarding.step
        guided = step != OnboardingStep.DONE
        self.starter_header_btn.setVisible(
            step in {OnboardingStep.INTRODUCTION, OnboardingStep.NURSERY}
            and self._starter_setup_dismissed
        )
        self.progress_btn.setVisible(not guided)
        self.collection_btn.setVisible(not guided)
        self.settings_btn.setVisible(not guided)
        self.garden_stats_bar.set_onboarding_mode(guided)
        # First-run guidance owns the scene; do not duplicate it with a
        # full-width neutral metric/status strip in the header.
        self.garden_stats_bar.setVisible(not guided)
        self._sync_header_minimum_heights()
        self.top_bar.updateGeometry()
        if step == OnboardingStep.DONE:
            self.onboarding_panel.hide()
            self._set_onboarding_shield(False)
            self.plant_card.set_onboarding_guidance(False)
            return

        if step == OnboardingStep.NURTURE:
            plant = next(
                (
                    row for row in self.storage.state.plants
                    if row.planted and not row.fully_grown
                ),
                None,
            )
            self._onboarding_plant_id = str(getattr(plant, "plant_id", "") or "")
            selected = self.scene.selected_plant_id() == self._onboarding_plant_id
            self.plant_card.set_onboarding_guidance(selected)
            visible = not selected and not self._starter_setup_dismissed
        else:
            self.plant_card.set_onboarding_guidance(False)
            visible = not (
                self._starter_setup_dismissed
                and step in {
                    OnboardingStep.INTRODUCTION,
                    OnboardingStep.NURSERY,
                }
            )
        if self._starter_placement_active:
            visible = False
        elif self._onboarding_save_error:
            visible = True

        species = format_status_label(
            self.storage.state.onboarding.pending_species or "starter"
        )
        content = {
            OnboardingStep.INTRODUCTION: (
                GARDEN_SETUP_TITLE,
                GARDEN_SETUP_BODY,
                CHOOSE_STARTER_ACTION,
                "Later",
            ),
            OnboardingStep.NURSERY: (
                "Choose a starter",
                "Your first plant is free.",
                "Choose starter",
                "Later",
            ),
            OnboardingStep.CONFIRMATION: (
                f"Choose {species}?",
                "You can move it later.",
                f"Choose {species}",
                "Back",
            ),
            OnboardingStep.PLACEMENT: (
                "Place your starter",
                "Choose a bed.",
                "Place here",
                "Back",
            ),
            OnboardingStep.NURTURE: (
                GARDEN_NURTURE_TITLE,
                GARDEN_NURTURE_BODY,
                GARDEN_NURTURE_ACTION,
                "Later",
            ),
            OnboardingStep.COMPLETION: (
                "Your garden is ready",
                self._onboarding_completion_receipt(),
                "Back to Anki",
                "Explore garden",
            ),
        }
        title, body, action_text, secondary_text = content[step]
        has_save_error = bool(self._onboarding_save_error)
        message = (
            self._onboarding_failure_receipt(step)
            if has_save_error
            else body
        )
        if has_save_error:
            title = "Couldn’t save your garden"
            message = "Nothing was changed."
            action_text = "Try again"
            secondary_text = "Back to setup"
        self.onboarding_step.setText("")
        self.onboarding_step.hide()
        self.onboarding_title.setText(title)
        self.onboarding_message.setText(message)
        self.onboarding_panel.setProperty("statusTone", "neutral")
        self.onboarding_message.setProperty(
            "statusTone",
            "error" if has_save_error else "neutral",
        )
        for target in (self.onboarding_panel, self.onboarding_message):
            style = target.style()
            if style is not None:
                style.unpolish(target)
                style.polish(target)
        self.onboarding_error_banner.set_status(
            message if has_save_error else "",
            tone=FeedbackTone.ERROR,
        )
        self.onboarding_message.setVisible(not has_save_error)
        self.onboarding_action.setText(action_text)
        self.onboarding_action.show()
        self.dismiss_onboarding.setText(secondary_text)
        self.dismiss_onboarding.show()
        self.onboarding_panel.setAccessibleDescription(
            f"{title}. {message}"
        )
        if has_save_error and message != self._last_onboarding_error_announcement:
            self._last_onboarding_error_announcement = message
            self.accessibility_announcer.announce(
                message,
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.onboarding_message,
            )
        elif not has_save_error:
            self._last_onboarding_error_announcement = ""
        self.onboarding_panel.setVisible(visible)
        self._set_onboarding_shield(visible)
        if visible:
            QTimer.singleShot(0, self._position_onboarding_coachmark)

    def _onboarding_completion_receipt(self) -> str:
        progress = self.storage.state.onboarding
        plant = self.engine.plant_story(str(progress.starter_plant_id or ""))
        plant_name = str(getattr(plant, "name", "Your plant") or "Your plant")
        slot = getattr(plant, "slot_index", None)
        bed = f"Bed {int(slot) + 1}" if isinstance(slot, int) and slot >= 0 else "Saved bed"
        return f"{plant_name} is growing in {bed}."

    def _onboarding_failure_receipt(self, step: OnboardingStep) -> str:
        del step
        return "Nothing was changed."

    def _set_onboarding_shield(self, active: bool) -> None:
        if not hasattr(self, "onboarding_shield"):
            return
        was_active = self.onboarding_shield.isVisible()
        self.onboarding_shield.setGeometry(self.scene.rect())
        self.onboarding_shield.setVisible(bool(active))
        if active:
            if not was_active:
                focused = QApplication.focusWidget()
                self._onboarding_focus_return = (
                    focused
                    if isinstance(focused, QWidget) and self.isAncestorOf(focused)
                    else None
                )
            self.onboarding_shield.raise_()
            self.onboarding_panel.raise_()
            QTimer.singleShot(
                0,
                lambda: (
                    self.onboarding_action.setFocus(Qt.FocusReason.OtherFocusReason)
                    if self.onboarding_panel.isVisible()
                    else None
                ),
            )
        elif was_active:
            target = self._onboarding_focus_return
            self._onboarding_focus_return = None
            if target is not None:
                QTimer.singleShot(
                    0,
                    lambda candidate=target: (
                        candidate.setFocus(Qt.FocusReason.OtherFocusReason)
                        if candidate.isVisibleTo(self) and candidate.isEnabled()
                        else None
                    ),
                )

    def focusNextPrevChild(self, forward: bool) -> bool:
        """Trap Tab inside a visible modal onboarding instruction."""

        if (
            hasattr(self, "onboarding_shield")
            and self.onboarding_shield.isVisible()
            and self.onboarding_panel.isVisible()
        ):
            targets = [
                button
                for button in (self.onboarding_action, self.dismiss_onboarding)
                if button.isVisibleTo(self) and button.isEnabled()
            ]
            if targets:
                current = QApplication.focusWidget()
                try:
                    index = targets.index(current)
                except ValueError:
                    index = -1 if forward else 0
                target = targets[(index + (1 if forward else -1)) % len(targets)]
                target.setFocus(
                    Qt.FocusReason.TabFocusReason
                    if forward else
                    Qt.FocusReason.BacktabFocusReason
                )
                return True
        return super().focusNextPrevChild(forward)

    def _on_starter_selected(self, plant: Any, confirmation: str = "") -> None:
        """Publish starter success only after the engine transaction returned OK."""

        if callable(self._starter_selected_callback):
            self._starter_selected_callback()
        self._starter_confirmation_message = confirmation or starter_confirmation(
            getattr(plant, "name", "Your plant")
        )
        self._onboarding_just_completed = True
        self._starter_setup_dismissed = False
        self._onboarding_plant_id = str(getattr(plant, "plant_id", "") or "")
        self._onboarding_confirmation_generation += 1
        self._refresh_onboarding()
        if self._onboarding_plant_id:
            def open_nurture_step() -> None:
                self.scene.keep_card_open(self._onboarding_plant_id)
                self._refresh_selected_plant_card()
                self.plant_card.set_onboarding_guidance(True)
                self._refresh_onboarding()
                QTimer.singleShot(0, self.plant_card.nurture.setFocus)
            QTimer.singleShot(0, open_nurture_step)

    def _complete_onboarding(self) -> bool:
        ok, message = self.engine.finish_onboarding()
        if not ok:
            self._onboarding_save_error = message
            self._refresh_onboarding()
            return False
        self._onboarding_save_error = ""
        return True

    def _dismiss_onboarding(self) -> None:
        step = self.storage.state.onboarding.step
        if self._onboarding_save_error:
            self._onboarding_save_error = ""
            self._refresh_onboarding()
            return
        if step in {
            OnboardingStep.INTRODUCTION,
            OnboardingStep.NURSERY,
            OnboardingStep.NURTURE,
        }:
            self._starter_setup_dismissed = True
            self._refresh_onboarding()
            return
        if step in {OnboardingStep.CONFIRMATION, OnboardingStep.PLACEMENT}:
            ok, message = self.engine.back_onboarding()
            if not ok:
                self._onboarding_save_error = message
            else:
                self._refresh_after_commit("onboarding back")
            self._refresh_onboarding()
            return
        if step == OnboardingStep.COMPLETION and self._complete_onboarding():
            self._refresh_after_commit("onboarding Explore garden")
            self._refresh_onboarding()

    def _complete_first_nurture_guidance(self) -> None:
        self._onboarding_just_completed = False
        self._starter_setup_dismissed = False
        self.plant_card.set_onboarding_guidance(False)
        self._refresh_onboarding()

    def _clear_onboarding_confirmation(self, generation: int) -> None:
        if generation != self._onboarding_confirmation_generation:
            return
        self._onboarding_just_completed = False
        self._starter_confirmation_message = ""
        self._refresh_onboarding()

    def _clear_layout(self, layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_unlock_card(self) -> None:
        self.milestone_card.hide()

    def _purchase_species(self, species: str) -> None:
        self._confirm_dashboard_purchase(PurchaseKind.SPECIES, species)

    def _purchase_bed(self) -> None:
        self._confirm_dashboard_purchase(PurchaseKind.BED, "next")

    def _confirm_dashboard_purchase(
        self,
        kind: PurchaseKind,
        item_id: str,
        *,
        target_id: str | None = None,
    ) -> PurchaseOutcome | None:
        quote = self.engine.quote_purchase(
            kind,
            item_id,
            target_id=target_id,
        )
        dialog_type = (
            FertilizerReplacementDialog
            if quote.replacement_required else
            PurchaseConfirmationDialog
        )
        dialog = dialog_type(self, self.engine, quote)
        self.purchase_dialog = dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            route = dialog.requested_route
            if route == "ways_to_earn":
                QTimer.singleShot(0, lambda: self.progress_dialog.open_page("currency"))
            elif route == "collection":
                QTimer.singleShot(0, lambda: self.progress_dialog.open_page("collection"))
            elif route == "customize":
                QTimer.singleShot(0, self._open_collection)
            return None
        outcome = dialog.outcome
        if outcome is None or not outcome.success:
            return None
        self._refresh_after_commit(f"{kind.value} purchase")
        self.toast_region.show_message(outcome.message)
        return outcome

    def _refresh_collection_list(self) -> None:
        self.collection_list.clear()
        state = self.storage.state
        registry_views = list(collectible_views(state))
        summary = self.engine.catalog_summary()
        species_catalog = list(summary.get("release_ready_species", []))
        owned_species = {
            str(species)
            for species in summary.get("owned_species", [])
        }
        collected = sum(1 for view in registry_views if view.owned)
        count = QLabel(f"{collected} of {len(registry_views)} collected")
        count.setProperty("rowTitle", True)
        count.setWordWrap(True)
        filters = CollectionFilterControls(
            count=count,
            query=self._collection_query,
            status=self._collection_filter,
            category=self._collection_category,
            sort_order=self._collection_sort,
            set_query=self._set_collection_query,
            set_status=self._set_collection_filter,
            set_category=self._set_collection_category,
            set_sort_order=self._set_collection_sort,
            clear_filters=self._clear_collection_filters,
        )
        filters.setProperty("sectionCard", True)
        self.collection_filter_header_responsive = filters.responsive
        self.collection_filter_responsive = filters.responsive
        self.collection_filter_controls = filters
        self.collection_list.add_full_width(filters)

        no_results = EmptyState(
            "No matches",
            "",
        )
        no_results.setAccessibleName("Collection filters returned no results")
        no_results.setProperty("excludedFromProgressGrid", True)
        no_results.hide()
        self.collection_list.add_full_width(no_results)
        self.collection_no_results = no_results

        stage_rank = {stage: index for index, stage in enumerate(GROWTH_STAGES)}
        rendered = 0
        result_count = 0
        ordered_species = list(species_catalog)
        if self._collection_sort == "name":
            ordered_species.sort(key=lambda value: format_status_label(value).casefold())
        for species in ordered_species:
            if self._collection_category not in {"all", "plants"}:
                continue
            if self._collection_query and self._collection_query.casefold() not in format_status_label(species).casefold():
                continue
            instances = [plant for plant in state.plants if plant.species == species]
            collected_species = species in owned_species or bool(instances)
            if self._collection_filter == "collected" and not collected_species:
                continue
            if self._collection_filter == "not_collected" and collected_species:
                continue
            highest = max(
                instances,
                key=lambda plant: stage_rank.get(str(plant.growth_stage), 0),
                default=None,
            )
            highest_stage = str(highest.growth_stage) if highest is not None else "seed"
            button = QPushButton()
            button.setProperty("catalogCard", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, selected=species:
                self._open_species_overview(selected)
            )
            card: QWidget = button
            card.setMinimumHeight(224)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            layout = QVBoxLayout(card)
            layout.setContentsMargins(10, 9, 10, 10)
            layout.setSpacing(6)
            artwork = _asset_preview_label(
                self.engine,
                species,
                highest_stage if collected_species else "seed",
                size=104,
            )
            layout.addWidget(artwork, 0, Qt.AlignmentFlag.AlignHCenter)
            title = QLabel(format_status_label(species))
            title.setProperty("rowTitle", True)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setWordWrap(True)
            status = QLabel("")
            status.hide()
            status.setProperty("catalogStatus", True)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            stage_copy = QLabel(
                f"{format_status_label(highest_stage)} · {_plant_count(len(instances))}"
                if collected_species else
                "Available in Nursery"
            )
            stage_copy.setProperty("rowCriteria", True)
            stage_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
            instances_copy = QLabel("")
            instances_copy.hide()
            instances_copy.setProperty("rowCriteria", True)
            instances_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setProperty("rowCriteria", True)
            status.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(stage_copy)
            for child in card.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            card.setAccessibleName(
                f"{format_status_label(species)}, "
                + (
                    f"collected, highest stage {format_status_label(highest_stage)}"
                    if collected_species else
                    "not collected"
                )
            )
            card.setAccessibleDescription(
                "Open the species overview. Plant Story remains specific to one collected instance."
            )
            self.collection_list.add_card(card)
            rendered += 1
        result_count += rendered
        if self._collection_category in {"all", "weather", "scenery"}:
            environment_copy = self._collection_appearance_summary()
            customize = QPushButton("Edit appearance")
            _set_button_variant(customize, BUTTON_VARIANT_PRIMARY)
            customize.setFixedHeight(36)
            customize.setAccessibleDescription(
                "Edit your garden’s Scenery, Weather, and Decorations."
            )
            customize.clicked.connect(self._open_loadout_detail)
            environment_header = ResponsiveActionCard(
                environment_copy,
                customize,
                semantic_id="progress.collection-environment",
                summary_floor=360,
                action_floor=150,
                spacing=10,
                margins=(14, 11, 14, 11),
            )
            environment_header.setProperty("sectionCard", True)
            self.collection_environment_responsive = environment_header.responsive
            self.collection_list.add_full_width(environment_header)
            catalogs = (
                (WEATHER_CATALOG,) if self._collection_category == "weather" else
                (SCENERY_CATALOG,) if self._collection_category == "scenery" else
                (WEATHER_CATALOG, SCENERY_CATALOG)
            )
            environment_rendered = 0
            for catalog in catalogs:
                for item in catalog.values():
                    owned = self.engine.owns_environment(item.kind, item.item_id)
                    searchable_name = (
                        item.name
                        if owned or not item.drop_only else
                        f"Mystery {format_status_label(item.kind)}"
                    )
                    if self._collection_query and self._collection_query.casefold() not in searchable_name.casefold():
                        continue
                    if self._collection_filter != "all" and owned != (self._collection_filter == "collected"):
                        continue
                    self.collection_list.add_full_width(
                        self._environment_collection_card(item)
                    )
                    environment_rendered += 1
            result_count += environment_rendered
        if self._collection_category in {"all", "decorations", "garden_beds", "growth_items"}:
            extra = [
                view for view in registry_views
                if view.definition.category in {"decorations", "garden_beds", "growth_items"}
                and (
                    self._collection_category == "all"
                    or view.definition.category == self._collection_category
                )
                and (self._collection_filter == "all" or view.owned == (self._collection_filter == "collected"))
                and (
                    not self._collection_query
                    or self._collection_query.casefold() in view.definition.name.casefold()
                )
            ]
            if self._collection_sort == "name":
                extra.sort(key=lambda view: view.definition.name.casefold())
            for category_key in ("decorations", "garden_beds", "growth_items"):
                group = [
                    view for view in extra
                    if view.definition.category == category_key
                ]
                if not group:
                    continue
                group_heading = QLabel(CATEGORY_LABELS[category_key])
                group_heading.setProperty("categoryTitle", True)
                group_heading.setAccessibleName(
                    f"{CATEGORY_LABELS[category_key]} collection group"
                )
                self.collection_list.add_full_width(group_heading)
                for view in group:
                    self.collection_list.add_card(
                        self._collectible_registry_card(view)
                    )
            result_count += len(extra)
        is_empty = result_count == 0
        no_results.setProperty("excludedFromProgressGrid", not is_empty)
        self.collection_list.finish()
        no_results.setVisible(is_empty)
        self.collection_list.setProperty("emptyResult", is_empty)
        progress_dialog = getattr(self, "progress_dialog", None)
        if (
            progress_dialog is not None
            and progress_dialog.navigation.stack.currentWidget()
            is self.collection_list
        ):
            progress_dialog.apply_view_size_profile(
                progress_dialog._view_profile_for_page("collection")
            )

    def _set_collection_filter(self, selected: str) -> None:
        self._collection_filter = (
            selected
            if selected in {"all", "collected", "not_collected"}
            else "all"
        )
        self._refresh_collection_list()

    def _set_collection_category(self, selected: str) -> None:
        valid = {"all", *(key for key, _label in collection_categories())}
        self._collection_category = selected if selected in valid else "all"
        self._refresh_collection_list()

    def _set_collection_query(self, query: str) -> None:
        normalized = " ".join(str(query).split())
        if normalized == self._collection_query:
            return
        self._collection_query = normalized
        self._refresh_collection_list()

    def _set_collection_sort(self, selected: str) -> None:
        normalized = "catalog" if str(selected) == "registry" else str(selected)
        self._collection_sort = normalized if normalized in {"catalog", "name"} else "catalog"
        self._refresh_collection_list()

    def _toggle_collection_sort(self) -> None:
        self._set_collection_sort(
            "name" if self._collection_sort in {"catalog", "registry"} else "catalog"
        )

    def _clear_collection_filters(self) -> None:
        self._collection_filter = "all"
        self._collection_category = "all"
        self._collection_query = ""
        self._collection_sort = "catalog"
        self._refresh_collection_list()

    def _collection_appearance_summary(self) -> QWidget:
        """Show one compact persisted appearance summary."""

        state = self.storage.state
        scenery = SCENERY_CATALOG.get(str(state.selected_background)) or SCENERY_CATALOG[
            DEFAULT_SCENERY_ID
        ]
        weather = WEATHER_CATALOG.get(str(state.selected_weather)) or WEATHER_CATALOG[
            DEFAULT_WEATHER_ID
        ]
        decoration_id = str(state.loadout.decoration_id or "")
        decoration_name = "Garden Lantern" if decoration_id == "lantern" else "No decoration"

        summary = QFrame()
        summary.setProperty("appearanceCard", True)
        summary.setProperty("collectionAppearanceSummary", True)
        summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(5)
        title = QLabel("Garden appearance")
        title.setProperty("rowTitle", True)
        title.setProperty("appearanceSummaryTitle", True)
        summary_layout.addWidget(title)
        selection = QLabel(
            f"{scenery.name} · {weather.name} · {decoration_name}"
        )
        selection.setProperty("rowCriteria", True)
        selection.setWordWrap(True)
        summary_layout.addWidget(selection)
        summary.setAccessibleName(
            f"Garden appearance. Scenery {scenery.name}. Weather {weather.name}. "
            f"Decoration {decoration_name}."
        )
        return summary

    def _collection_mechanics_help(
        self,
        descriptor: Any,
        item_name: str,
    ) -> QWidget:
        """Keep long-duration mechanics available without dominating cards."""

        help_region = QWidget()
        layout = QVBoxLayout(help_region)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        toggle = QPushButton("Details")
        toggle.setCheckable(True)
        toggle.setProperty("disclosureRow", True)
        toggle.setProperty("environmentMechanicsDisclosure", True)
        toggle.setAccessibleName(f"Details for {item_name}")
        toggle.setAccessibleDescription(
            "Show duration, stacking, and replacement details for this item."
        )
        details = QLabel("\n".join((
            f"Duration: {descriptor.duration}",
            f"Stacking: {descriptor.stacking}",
            f"Replacement: {descriptor.replacement}",
        )))
        details.setTextFormat(Qt.TextFormat.PlainText)
        details.setProperty("rowCriteria", True)
        details.setProperty("environmentMechanicsDetails", True)
        details.setWordWrap(True)
        details.hide()

        def set_expanded(expanded: bool) -> None:
            details.setVisible(bool(expanded))
            toggle.setText("Hide details" if expanded else "Details")
            toggle.setAccessibleName(
                f"{'Hide details' if expanded else 'Details'} for {item_name}"
            )
            toggle.setAccessibleDescription(
                "Hide duration, stacking, and replacement details."
                if expanded else
                "Show duration, stacking, and replacement details for this item."
            )
            help_region.updateGeometry()

        toggle.toggled.connect(set_expanded)
        layout.addWidget(toggle)
        layout.addWidget(details)
        return help_region

    def _collectible_registry_card(self, view: Any) -> QWidget:
        definition = view.definition
        card = QFrame()
        card.setProperty("catalogCard", True)
        card.setProperty("catalogState", view.state_label.casefold().replace(" ", "_"))
        card.setMinimumHeight(224)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(7)
        identity = QHBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(9)
        icon = QLabel({
            "decorations": "◆",
            "garden_beds": "▦",
            "growth_items": "✦",
        }.get(definition.category, "•"))
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setProperty("collectibleIcon", True)
        icon.setAccessibleName(f"{CATEGORY_LABELS[definition.category]} icon")
        title = QLabel(definition.name)
        title.setProperty("rowTitle", True)
        title.setWordWrap(True)
        identity.addWidget(icon)
        identity.addWidget(title, 1)
        owned_quantity = (
            int(view.quantity)
            if definition.category == "growth_items" else
            1 if view.owned else 0
        )
        status_text = (
            format_available(owned_quantity)
            if definition.category == "growth_items" and owned_quantity > 0 else
            "Equipped"
            if bool(getattr(view, "equipped", False)) else
            "Unlocked"
            if definition.category == "garden_beds" and view.owned else
            ""
            if view.owned else
            "Available in Nursery"
        )
        status = QLabel(status_text)
        status.setProperty("catalogStatus", True)
        status.setWordWrap(True)
        status.setVisible(bool(status_text))
        detail_lines = []
        if definition.category == "growth_items" and definition.descriptor.buff:
            detail_lines.append(definition.descriptor.buff.rstrip("."))
        facts = QLabel("\n".join(detail_lines))
        facts.setTextFormat(Qt.TextFormat.PlainText)
        facts.setProperty("rowCriteria", True)
        facts.setWordWrap(True)
        layout.addLayout(identity)
        if status_text:
            layout.addWidget(status)
        facts.setVisible(bool(detail_lines))
        if detail_lines:
            layout.addWidget(facts)

        action: QPushButton | None = None
        if definition.category == "decorations" and view.owned:
            action = QPushButton("Preview")
            _set_button_variant(action, BUTTON_VARIANT_PRIMARY)
            action.setAccessibleDescription(
                "Open a reversible preview. Applying is required to change the garden."
            )
            action.clicked.connect(
                lambda _checked=False, item_id=definition.source_id:
                self._open_loadout_detail("decorations", item_id)
            )
        elif definition.category == "garden_beds":
            action = QPushButton("View garden" if view.owned else "Open Nursery")
            _set_button_variant(
                action,
                BUTTON_VARIANT_SECONDARY if view.owned else BUTTON_VARIANT_PRIMARY,
            )
            action.setAccessibleDescription(
                "Return to the garden and inspect its available beds."
                if view.owned else
                "Open the Nursery to review the next available garden bed."
            )
            action.clicked.connect(
                self._return_to_garden_from_collection
                if view.owned else
                self._open_nursery_from_collection
            )
        elif definition.category == "growth_items":
            action = QPushButton("Use" if view.owned else "Open Nursery")
            _set_button_variant(
                action,
                BUTTON_VARIANT_PRIMARY if view.owned else BUTTON_VARIANT_SECONDARY,
            )
            action.setAccessibleDescription(
                "Return to the garden and choose a plant."
                if view.owned else
                "Open the Nursery to review available Growth items."
            )
            action.clicked.connect(
                self._return_to_garden_from_collection
                if view.owned else
                self._open_nursery_from_collection
            )
        if action is not None:
            layout.addWidget(action)
        card.setAccessibleName(
            f"{definition.name}. {status_text or 'In your collection'}."
        )
        card.setAccessibleDescription(facts.text())
        return card

    def _open_species_overview(self, species: str) -> None:
        dialog = self._build_species_overview_dialog(species)
        if dialog is not None:
            dialog.exec()

    def _build_species_overview_dialog(
        self,
        species: str,
        *,
        parent: QWidget | None = None,
    ) -> GardenDialog | None:
        summary = self.engine.catalog_summary()
        catalog = [str(value) for value in summary.get("release_ready_species", [])]
        if str(species) not in catalog:
            return None
        instances = [
            plant for plant in self.storage.state.plants
            if str(plant.species) == str(species)
        ]
        owned_species = {str(value) for value in summary.get("owned_species", [])}
        collected = bool(instances) or str(species) in owned_species
        stage_rank = {stage: index for index, stage in enumerate(GROWTH_STAGES)}
        highest = max(
            instances,
            key=lambda plant: stage_rank.get(str(plant.growth_stage), 0),
            default=None,
        )
        highest_stage = str(highest.growth_stage) if highest is not None else "seed"
        dialog = GardenDialog(
            parent or self.progress_dialog,
            format_status_label(species),
            subtitle="",
        )
        dialog.apply_size_policy(
            DialogSizeClass.SPECIES_DETAIL,
        )
        dialog.apply_view_size_profile("default")
        dialog.setProperty("windowFamily", "SpeciesOverviewDialog")
        dialog.setProperty("layoutMode", "default")
        dialog.setProperty("collectionState", "collected" if collected else "not-collected")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Species overview details")
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)
        hero_art = _asset_preview_label(
            self.engine,
            species,
            highest_stage if collected else "seed",
            size=128,
        )
        facts = QWidget()
        facts_layout = QVBoxLayout(facts)
        facts_layout.setContentsMargins(0, 0, 0, 0)
        facts_layout.setSpacing(5)
        discovered_date = (
            self._local_date(min(plant.planted_on for plant in instances))
            if instances else
            ""
        )
        summary_text = (
            f"Discovered {discovered_date} · "
            f"Highest stage {format_status_label(highest_stage)} · "
            f"{_plant_count(len(instances))}"
            if collected and instances else
            "Available in the Nursery"
        )
        summary_label = QLabel(summary_text)
        summary_label.setProperty("dialogSubtitle", True)
        summary_label.setWordWrap(True)
        apply_tabular_numerals(summary_label)
        facts_layout.addWidget(summary_label)
        hero = ResponsiveActionCard(
            hero_art,
            facts,
            semantic_id="species-overview.hero",
            summary_floor=128,
            action_floor=280,
            spacing=18,
            margins=(14, 12, 14, 12),
        )
        hero.setProperty("sectionCard", True)
        dialog.hero_responsive = hero.responsive
        layout.addWidget(hero)

        stage_panel = SectionCard()
        stage_panel_layout = QVBoxLayout(stage_panel)
        stage_panel_layout.setContentsMargins(14, 12, 14, 12)
        stage_panel_layout.setSpacing(9)
        stages_title = QLabel("Species stages")
        stages_title.setProperty("dialogTitle", True)
        stage_panel_layout.addWidget(stages_title)
        stages = ResponsiveTileGrid(
            breakpoint=760,
            minimum_tile_width=112,
            maximum_columns=6,
        )
        stages.grid.setHorizontalSpacing(8)
        stages.grid.setVerticalSpacing(8)
        highest_index = stage_rank.get(highest_stage, 0) if collected else -1
        for index, stage in enumerate(GROWTH_STAGES):
            stage_card = QFrame()
            stage_card.setProperty("storyStage", True)
            stage_card.setProperty(
                "storyStageState",
                "complete" if index < highest_index else
                "current" if index == highest_index and collected else
                "upcoming",
            )
            stage_layout = QVBoxLayout(stage_card)
            stage_layout.setContentsMargins(6, 6, 6, 6)
            stage_layout.setSpacing(3)
            mystery_stage = stage == "rare" and not _rare_stage_unlocked(self.engine, species)
            if mystery_stage:
                preview = QLabel("?")
                preview.setFixedSize(68, 68)
                preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                preview.setProperty("stagePreview", True)
                preview.setAccessibleName("Undiscovered Rare stage silhouette")
            else:
                preview = _asset_preview_label(
                    self.engine,
                    species,
                    stage,
                    size=68,
                )
            stage_name = QLabel(format_status_label(stage))
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_name.setProperty("storyStageName", True)
            stage_state = QLabel(
                f"Unlocks at {GROWTH_THRESHOLDS[-1]:,} Growth"
                if mystery_stage else
                ""
            )
            stage_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_state.setProperty("dialogSubtitle", True)
            stage_state.setWordWrap(True)
            stage_state.setVisible(bool(stage_state.text()))
            stage_layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
            stage_layout.addWidget(stage_name)
            if stage_state.text():
                stage_layout.addWidget(stage_state)
            accessible_state = (
                "Reached"
                if index <= highest_index and collected else
                stage_state.text() or "Available to preview"
            )
            stage_card.setAccessibleName(
                f"{format_status_label(stage)} stage. {accessible_state}."
            )
            stages.add_tile(stage_card)
        stage_panel_layout.addWidget(stages)

        instances_panel = SectionCard()
        instances_layout = QVBoxLayout(instances_panel)
        instances_layout.setContentsMargins(14, 12, 14, 12)
        instances_layout.setSpacing(8)
        instances_title = QLabel("Your plants")
        instances_title.setProperty("dialogTitle", True)
        instances_layout.addWidget(instances_title)
        empty_instances: QWidget | None = None
        if not instances:
            nursery = QPushButton("Open Nursery")
            _set_button_variant(nursery, BUTTON_VARIANT_PRIMARY)
            nursery.clicked.connect(
                lambda: (
                    dialog.accept(),
                    QTimer.singleShot(0, self._open_nursery),
                )
            )
            empty_instances = nursery
        else:
            for plant in sorted(instances, key=lambda item: (not item.planted, item.planted_on, item.name)):
                location = (
                    f"Bed {plant.slot_index + 1}"
                    if plant.planted and plant.slot_index is not None else
                    "In Collection"
                )
                row = QFrame()
                row.setProperty("progressRow", True)
                row_layout = QVBoxLayout(row)
                row_layout.setContentsMargins(10, 8, 10, 8)
                row_layout.setSpacing(2)
                row_name = QLabel(plant.name)
                row_name.setProperty("rowTitle", True)
                row_meta_parts = [format_status_label(plant.growth_stage), location]
                if plant.plant_id == self.storage.state.active_plant_id:
                    row_meta_parts.append("Nurtured")
                row_meta = QLabel(" · ".join(row_meta_parts))
                row_meta.setProperty("dialogSubtitle", True)
                row_meta.setWordWrap(True)
                row_layout.addWidget(row_name)
                row_layout.addWidget(row_meta)
                progress = growth_display(plant.growth_points)
                if not progress.fully_grown:
                    growth = LabeledProgress(f"{plant.name} Growth progress")
                    growth.set_progress(
                        "",
                        progress.stage_points,
                        max(1, progress.stage_goal),
                        value_text=format_stage_progress(
                            progress.stage_points,
                            progress.stage_goal,
                            format_status_label(progress.next_stage or "next stage"),
                        ),
                    )
                    growth.label.hide()
                    row_layout.addWidget(growth)
                actions = ResponsiveTileGrid(
                    breakpoint=420,
                    minimum_tile_width=170,
                    maximum_columns=2,
                )
                action_specs = (
                    (("View in garden", "view") if plant.planted else ("Place in garden", "plant")),
                    *(((("Move", "move"), ("Store", "remove"))) if plant.planted else ()),
                    *(((("Nurture", "nurture"),)) if plant.planted and not plant.fully_grown else ()),
                )
                for label_text, action_name in action_specs:
                    action = QPushButton(label_text)
                    _set_button_variant(
                        action,
                        BUTTON_VARIANT_PRIMARY if action_name in {"view", "plant", "nurture"} else BUTTON_VARIANT_SECONDARY,
                    )
                    action.setAccessibleDescription(f"{label_text} for {plant.name}.")
                    set_control_enabled(
                        action,
                        not (action_name == "remove" and plant.plant_id == self.storage.state.active_plant_id),
                        disabled_reason="Select another nurtured plant before removing this one.",
                        enabled_description=action.accessibleDescription(),
                    )
                    action.clicked.connect(
                        lambda _checked=False, selected=plant.plant_id, requested=action_name, owner=dialog:
                        self._collection_plant_action(requested, selected, owner)
                    )
                    actions.add_tile(action)
                row_layout.addWidget(actions)
                instances_layout.addWidget(row)
        layout.addWidget(stage_panel)
        if instances:
            layout.addWidget(instances_panel)
        elif empty_instances is not None:
            layout.addWidget(empty_instances)
        scroll.setWidget(body)
        _set_scroll_surface(scroll, body, GARDEN_THEME["dialog_surface"])
        dialog.set_body_widget(scroll)
        return dialog

    def _collection_plant_action(
        self,
        action: str,
        plant_id: str,
        dialog: QDialog,
    ) -> None:
        plant = self.engine.plant_story(plant_id)
        if plant is None:
            QMessageBox.warning(dialog, UI_TEXT["app_title"], "That plant is no longer available.")
            return
        if action == "view":
            dialog.accept()
            self.progress_dialog.close()
            self.scene.keep_card_open(plant_id)
            self.scene.setFocus()
            return
        if action == "plant":
            dialog.accept()
            self._begin_collection_placement(plant_id)
            return
        if action == "move":
            dialog.accept()
            self.progress_dialog.close()
            self._begin_move(plant_id)
            return
        if action == "nurture":
            ok, message = self.engine.set_active_plant(plant_id)
        elif action == "remove":
            ok, message = self.engine.move_to_collection(plant_id)
        else:
            return
        message = _learner_text(message)
        if not ok:
            message = f"{message} Your garden is unchanged."
        if ok:
            self._refresh_after_commit(f"collection plant {action}")
            dialog.accept()
            QTimer.singleShot(0, self._open_collection)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, UI_TEXT["app_title"], message
        )

    def _environment_collection_artwork(
        self,
        item: CatalogItem,
        *,
        silhouette: bool,
    ) -> QLabel:
        label = QLabel()
        label.setFixedSize(184, 108)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(
            f"Undiscovered {item.kind} silhouette"
            if silhouette else
            f"{item.name} collection preview"
        )
        label.setStyleSheet(
            "background:#10231f; border:1px solid #416054; border-radius:10px;"
        )
        if silhouette:
            label.setText("?")
            label.setStyleSheet(
                "background:#111513; border:1px solid #4b554e; border-radius:10px; "
                "color:#65716a; font-size:38px; font-weight:800;"
            )
            return label
        label.setPixmap(_environment_preview_pixmap(
            self.engine,
            item,
            176,
            100,
            scenery_id=str(self.storage.state.selected_background),
        ))
        return label

    def _environment_collection_card(self, item: CatalogItem) -> QFrame:
        owned = self.engine.owns_environment(item.kind, item.item_id)
        equipped = (
            self.storage.state.selected_weather == item.item_id
            if item.kind == "weather"
            else self.storage.state.selected_background == item.item_id
        )
        card = QFrame()
        card.setProperty("progressRow", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        artwork = self._environment_collection_artwork(
            item,
            silhouette=bool(item.drop_only and not owned),
        )
        mystery = bool(item.drop_only and not owned)
        display_name = f"Mystery {format_status_label(item.kind)}" if mystery else item.name
        copy_widget = QWidget()
        copy = QVBoxLayout(copy_widget)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(4)
        title = QLabel(display_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setProperty("rowTitle", True)
        descriptor = item.descriptor
        state_text = (
            "Equipped" if equipped else
            "" if owned else
            "Available in Nursery" if item.purchasable else
            "Garden Find"
        )
        status_text = " · ".join(
            part for part in (format_status_label(item.kind), state_text) if part
        )
        status = QLabel(status_text)
        status.setProperty("catalogStatus", True)
        status.setWordWrap(True)
        effect_copy = "" if mystery else str(item.effect or "").strip()
        if effect_copy.casefold() == "no gameplay bonus.":
            effect_copy = ""
        effect = QLabel(effect_copy)
        effect.setTextFormat(Qt.TextFormat.PlainText)
        effect.setWordWrap(True)
        effect.setProperty("rowCriteria", True)
        copy.addWidget(title)
        copy.addWidget(status)
        if effect_copy:
            copy.addWidget(effect)
        if effect_copy and owned:
            copy.addWidget(self._collection_mechanics_help(descriptor, item.name))
        summary = ResponsiveActionCard(
            artwork,
            copy_widget,
            semantic_id=f"collection.environment-card.{item.kind}.{item.item_id}",
            summary_floor=184,
            action_floor=260,
            spacing=12,
        )
        layout.addWidget(summary)

        actions = ResponsiveTileGrid(
            breakpoint=420,
            minimum_tile_width=150,
            maximum_columns=2,
        )
        action = QPushButton(
            "Preview" if owned else
            "Open Nursery" if item.purchasable else
            "Garden Find only"
        )
        _set_button_variant(
            action, BUTTON_VARIANT_PRIMARY if owned else BUTTON_VARIANT_SECONDARY,
        )
        if owned:
            action_description = f"Open Garden appearance with {item.name} selected."
        elif item.purchasable:
            action_description = f"Open the Nursery to purchase {item.name}."
        else:
            action_description = item.how_to_earn
        action.setAccessibleDescription(action_description)
        set_control_enabled(
            action,
            owned or item.purchasable,
            disabled_reason=action.accessibleDescription(),
            enabled_description=action.accessibleDescription(),
        )
        if owned:
            action.clicked.connect(
                lambda _checked=False, kind=item.kind, item_id=item.item_id:
                self._open_loadout_detail(kind, item_id)
            )
        elif item.purchasable:
            action.clicked.connect(self._open_nursery_from_collection)
        actions.add_tile(action)
        if equipped and item.item_id not in {DEFAULT_WEATHER_ID, DEFAULT_SCENERY_ID}:
            unequip = QPushButton("Unequip")
            _set_button_variant(unequip, BUTTON_VARIANT_SECONDARY)
            unequip.setAccessibleDescription(
                f"Reset {format_status_label(item.kind)} to the included neutral default."
            )
            unequip.clicked.connect(
                lambda _checked=False, kind=item.kind: self._unequip_environment(kind)
            )
            actions.add_tile(unequip)
        layout.addWidget(actions)
        card.setAccessibleName(
            f"{display_name}. {status_text}."
        )
        card.setAccessibleDescription(effect_copy)
        return card

    def _open_customize_from_collection(self) -> None:
        """Compatibility helper retained for one release of fixture callers."""

        self._open_loadout_detail()

    def _unequip_environment(self, kind: str) -> None:
        state = self.storage.state
        weather_id = DEFAULT_WEATHER_ID if kind == "weather" else state.selected_weather
        scenery_id = DEFAULT_SCENERY_ID if kind == "scenery" else state.selected_background
        ok, message = self.engine.apply_garden_loadout(
            weather_id,
            scenery_id,
            state.loadout.decoration_id,
            state.environment_visibility,
        )
        if ok:
            self._refresh_after_commit("collection unequip")
            self._refresh_collection_list()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, UI_TEXT["app_title"], _learner_text(message)
        )

    def _open_nursery_from_collection(self) -> None:
        self.progress_dialog.close()
        QTimer.singleShot(0, self._open_nursery)

    def _return_to_garden_from_collection(self) -> None:
        self.progress_dialog.close()
        QTimer.singleShot(0, self.scene.setFocus)

    def _begin_collection_placement(self, plant_id: str) -> None:
        plant = self.engine.plant_story(str(plant_id))
        if plant is None or plant.planted:
            return
        occupied = {
            item.slot_index for item in self.storage.state.plants
            if item.slot_index is not None
        }
        allowed = [
            slot for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
            if slot not in occupied and self.engine.slot_accepts_plant(plant, slot)
        ]
        if not allowed:
            QMessageBox.warning(self, UI_TEXT["app_title"], self.engine.SOIL_CAPACITY_MESSAGE)
            return
        self.progress_dialog.close()
        self._collection_placement_plant_id = plant.plant_id
        self.rearrange_bar.plant_id = plant.plant_id
        self.rearrange_bar.clear_failure()
        self.rearrange_bar.title.setText(f"Place {plant.name}")
        self.rearrange_bar.instructions.setText("Choose a bed.")
        self.rearrange_bar.cancel.setText("Back")
        if self.scene.begin_collection_placement(plant.plant_id, allowed):
            self._record_active_placement_token()
            self.rearrange_bar.show()
            self.scene.setFocus()
            QTimer.singleShot(0, self._position_scene_overlays)
            return
        self._collection_placement_plant_id = ""
        self._active_placement_token = None
        QTimer.singleShot(0, self._open_collection)

    def _set_collection_placement(self, plant_id: str, currently_planted: bool) -> None:
        if currently_planted:
            ok, message = self.engine.move_to_collection(plant_id)
        else:
            ok, message = self.engine.plant_from_collection(plant_id)
        if ok:
            self.scene.dismiss_selection()
            self._refresh_after_commit("collection placement")
        self.accessibility_announcer.announce(
            _learner_text(message),
            priority=(
                AnnouncementPriority.POLITE
                if ok
                else AnnouncementPriority.ASSERTIVE
            ),
            target=self.status_notice,
        )
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, UI_TEXT["app_title"], _learner_text(message)
        )

    def _open_fertilizer_menu(self, plant_id: str) -> None:
        if not plant_id:
            return
        plant = self.engine.plant_story(plant_id)
        if plant is None:
            self.status_notice.setText("That plant is no longer in your garden.")
            self.status_notice.setAccessibleDescription(self.status_notice.text())
            self.status_notice.setStyleSheet("color:#ffd0d0;")
            self.status_notice.show()
            self.accessibility_announcer.announce(
                self.status_notice.text(),
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.status_notice,
            )
            self._sync_feedback_panel_visibility()
            self._update_scene_height()
            return
        dialog = DialogShell(self)
        self.fertilizer_dialog = dialog
        dialog.setProperty("windowFamily", "FertilizerDialog")
        dialog.setProperty("layoutMode", "default")
        dialog.remember_invoker(self.plant_card.fertilize)
        dialog.setWindowTitle(f"Fertilize {plant.name}")
        dialog.apply_size_policy(
            DialogSizeClass.FERTILIZER,
        )
        dialog.setStyleSheet(foundation_stylesheet() + """
            QWidget[gardenDialogShell='true'] { background:#071a15; color:#f3f7f2; }
            QWidget#fertilizerOptions { background:#071a15; }
            QScrollArea { background:transparent; border:0; }
            QScrollBar:vertical { width:10px; margin:2px; background:transparent; }
            QScrollBar::handle:vertical { min-height:30px; border-radius:4px; background:#4f806e; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
            QFrame[fertilizerHero='true'] { background:transparent; border:0; }
            QFrame[fertilizerCard='true'] { background:#0c261f; border:1px solid #20483c; border-radius:12px; }
            QLabel[fertilizerMeta='true'] { color:#a9bdb0; font-size:13px; }
            QLabel[fertilizerTitle='true'] { color:#f3f7f2; font-size:16px; font-weight:800; }
            QLabel[fertilizerBalance='true'] { color:#e7c96a; background:#123228; border-radius:9px; padding:6px 9px; font-weight:800; }
            QLabel[fertilizerShortfall='true'] { color:#e7c96a; font-size:13px; font-weight:700; }
            QLabel[currentFertilizer='true'] { background:#123228; border:0; border-radius:9px; padding:8px 10px; }
            QLabel[activeFertilizerBadge='true'] { color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:6px 10px; font-size:13px; font-weight:700; }
            QLabel[fertilizerUrgent='true'] { color:#f3d17d; background:#3b3420; border:1px solid #7d6f3d; border-radius:7px; padding:3px 7px; }
            QPushButton[fertilizerRowAction='true'] { min-height:32px; max-height:32px; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title_header = GardenDialogHeader(dialog)
        title_layout = QHBoxLayout(title_header)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(12)
        title = QLabel(f"Fertilize {plant.name}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:22px; font-weight:800;")
        title_layout.addWidget(title, 1)
        dialog.top_close = dialog.create_inline_close_button(title_header)
        title_layout.addWidget(
            dialog.top_close,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        hero = QFrame()
        hero.setProperty("fertilizerHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(_asset_preview_label(
            self.engine, plant.species, plant.growth_stage, size=48
        ))
        hero_layout.addStretch(1)
        current_time = time.time()
        existing_fertilizer = getattr(plant, "fertilizer", None)
        current_fertilizer = (
            existing_fertilizer
            if existing_fertilizer is not None
            and float(getattr(existing_fertilizer, "expires_at", 0) or 0) > current_time
            else None
        )
        current_tier = (
            str(getattr(current_fertilizer, "tier", "") or "").lower()
            if current_fertilizer is not None else ""
        )
        current_status = FertilizerStatusBlock(allow_description=False)
        current_status.set_status(
            fertilizer_status(
                self.engine,
                plant,
                now=current_time,
                description=FERTILIZER_EXPLANATION,
            )
        )
        countdown_timer = QTimer(dialog)
        countdown_timer.setInterval(1_000)
        extend_current: QPushButton | None = None

        def refresh_fertilizer_countdown() -> None:
            live_plant = self.engine.plant_story(plant_id)
            status = fertilizer_status(
                self.engine,
                live_plant,
                now=time.time(),
                description=FERTILIZER_EXPLANATION,
            ) if live_plant is not None else FertilizerStatus(
                "inactive",
                "No active Fertilizer",
                "",
                "",
                FERTILIZER_EXPLANATION,
                "No active Fertilizer.",
                0,
            )
            current_status.set_status(status)
            if extend_current is not None:
                extend_current.setText("Extend" if status.active else "Apply")
                extend_current.setAccessibleName(
                    f"{'Extend' if status.active else 'Apply'} "
                    f"{current_tier.title()} Fertilizer on {plant.name}"
                )

        countdown_timer.timeout.connect(refresh_fertilizer_countdown)
        countdown_timer.start()
        balance_value = int(self.storage.state.currency_balance)
        balance = QLabel(f"{balance_value:,} Garden Coins")
        balance.setProperty("fertilizerBalance", True)
        apply_tabular_numerals(balance)
        layout.addWidget(title_header)
        hero_layout.addWidget(balance, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(hero)
        current_status_row = QHBoxLayout()
        current_status_row.setSpacing(10)
        current_status_row.addWidget(current_status, 1)
        if current_fertilizer is not None:
            extend_current = QPushButton("Extend")
            extend_current.setProperty("fertilizerRowAction", True)
            _set_compact_row_action(extend_current)
            _set_button_variant(extend_current, BUTTON_VARIANT_PRIMARY)
            extend_current.setAccessibleName(
                f"Extend {current_status.name_label.text()} on {plant.name}"
            )
            extend_current.clicked.connect(
                lambda _checked=False, selected_tier=current_tier, target=dialog:
                self._purchase_fertilizer_from_dialog(
                    plant_id, selected_tier, target, purchase_status
                )
            )
            current_status_row.addWidget(extend_current)
        layout.addLayout(current_status_row)
        options_heading = QLabel("Replace with")
        options_heading.setProperty("fertilizerTitle", True)
        options_heading.setVisible(current_fertilizer is not None)
        layout.addWidget(options_heading)
        active = str(self.storage.state.active_plant_id or "") == plant_id
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setFrameShape(QFrame.Shape.NoFrame)
        options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        options_scroll.setAccessibleName("Fertilizer options")
        options = QWidget()
        options.setObjectName("fertilizerOptions")
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(0, 0, 2, 0)
        options_layout.setSpacing(9)
        options_scroll.setWidget(options)
        _set_scroll_surface(
            options_scroll,
            options,
            GARDEN_THEME["garden_background"],
        )
        if not active:
            nurture_note = QLabel(
                "Nurture this plant first."
            )
            nurture_note.setWordWrap(True)
            nurture_note.setProperty("fertilizerMeta", True)
            options_layout.addWidget(nurture_note)
            nurture_now = QPushButton("Nurture")
            _set_button_variant(nurture_now, BUTTON_VARIANT_PRIMARY)
            nurture_now.clicked.connect(
                lambda: (dialog.accept(), QTimer.singleShot(0, lambda: self._nurture_plant(plant_id)))
            )
            options_layout.addWidget(nurture_now, 0, Qt.AlignmentFlag.AlignLeft)
        purchase_status = QLabel("")
        purchase_status.setTextFormat(Qt.TextFormat.PlainText)
        purchase_status.setWordWrap(True)
        purchase_status.setAccessibleName("Fertilizer purchase status")
        purchase_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(purchase_status)
        purchase_status.hide()
        options_layout.addWidget(purchase_status)
        option_responsive: list[AdaptiveSplit] = []
        for tier, spec in self.engine.FERTILIZERS.items():
            if current_tier and str(tier).lower() == current_tier:
                continue
            quote = self.engine.quote_purchase(
                PurchaseKind.FERTILIZER,
                tier,
                target_id=plant_id,
            )
            presentation = purchase_presentation(quote, ignore_status=True)
            summary = QWidget()
            summary_layout = QHBoxLayout(summary)
            summary_layout.setContentsMargins(0, 0, 0, 0)
            summary_layout.setSpacing(12)
            summary_layout.addWidget(
                _item_preview_label(
                    self.engine,
                    f"fertilizer_{tier}",
                    f"{spec.name} bag preview",
                    size=46,
                )
            )
            copy_widget = QWidget()
            copy = QVBoxLayout(copy_widget)
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(3)
            name = QLabel(spec.name)
            name.setProperty("fertilizerTitle", True)
            affordable, affordability = _affordability_status(spec.price, balance_value)
            effect = _purchase_fact(
                presentation,
                "effect",
                f"+{spec.growth_per_answer:,} Growth per card",
            )
            consequence = str(quote.descriptor.duration or "").strip().rstrip(".")
            detail = QLabel(
                " · ".join(filter(None, (effect, consequence, cost_label(spec.price))))
            )
            detail.setProperty("fertilizerMeta", True)
            detail.setWordWrap(True)
            apply_tabular_numerals(detail)
            copy.addWidget(name)
            copy.addWidget(detail)
            if not affordable:
                shortfall = max(0, int(spec.price) - balance_value)
                shortfall_label = QLabel(
                    f"{shortfall:,} more "
                    f"{'Garden Coin' if shortfall == 1 else 'Garden Coins'} needed"
                )
                shortfall_label.setProperty("fertilizerShortfall", True)
                apply_tabular_numerals(shortfall_label)
                copy.addWidget(shortfall_label)
            summary_layout.addWidget(copy_widget, 1)
            action_label = (
                "Buy and replace"
                if quote.replacement_required
                else presentation.primary_label.split(" ·", 1)[0]
            )
            choose = QPushButton(_qt_button_text(action_label))
            choose.setProperty("fertilizerRowAction", True)
            _set_compact_row_action(choose)
            recommended = not current_tier and str(tier).lower() == "basic"
            _set_button_variant(
                choose,
                BUTTON_VARIANT_PRIMARY
                if affordable and active and recommended
                else BUTTON_VARIANT_SECONDARY,
            )
            choose.setAccessibleName(
                presentation.primary_accessible_name
            )
            choose.setAccessibleDescription(
                f"{presentation.outcome} {effect}. "
                f"{cost_label(spec.price)}. {affordability}"
            )
            set_control_enabled(
                choose,
                affordable and active,
                disabled_reason=(
                    "Nurture this plant before buying Fertilizer."
                    if not active
                    else f"{spec.name} is not affordable yet. {affordability}"
                ),
                enabled_description=choose.accessibleDescription(),
            )
            card = ResponsiveActionCard(
                summary,
                choose,
                semantic_id=f"fertilizer.{tier}-option",
                summary_floor=220,
                action_floor=96,
                spacing=12,
                margins=(12, 6, 12, 6),
            )
            card.setProperty("fertilizerCard", True)
            card.setMinimumHeight(68)
            card.setMaximumHeight(72)
            option_responsive.append(card.responsive)
            if not affordable or not active:
                card.setAccessibleName(
                    f"{spec.name} requires nurturing this plant first"
                    if not active else f"{spec.name} is not affordable yet"
                )
                card.setAccessibleDescription(
                    "Nurture this plant first."
                    if not active else affordability
                )
                card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                set_keyboard_focus_surface(card)
            choose.clicked.connect(
                lambda _checked=False, selected_tier=tier, target=dialog, status=purchase_status:
                self._purchase_fertilizer_from_dialog(plant_id, selected_tier, target, status)
            )
            options_layout.addWidget(card)
        dialog.fertilizer_option_responsive = tuple(option_responsive)
        options_scroll.setMinimumHeight(220)
        options_scroll.setMaximumHeight(340)
        layout.addWidget(options_scroll, 0)
        dialog.register_scroll_region(options_scroll)
        footer_frame = QFrame()
        footer_frame.setProperty("actionFooter", True)
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(0, 10, 0, 0)
        browse = QPushButton("Open Nursery")
        _set_button_variant(browse, BUTTON_VARIANT_TERTIARY)
        browse.clicked.connect(
            lambda: (dialog.accept(), QTimer.singleShot(0, lambda: self._open_nursery(tab_index=1)))
        )
        cancel = QPushButton("Cancel")
        _set_button_variant(cancel, BUTTON_VARIANT_TERTIARY)
        cancel.clicked.connect(dialog.reject)
        footer.addWidget(browse)
        footer.addStretch(1)
        footer.addWidget(cancel)
        layout.addWidget(footer_frame)
        dialog.register_pinned_footer(footer_frame)
        dialog.set_initial_focus(cancel, InitialFocusPolicy.SAFE_ACTION)
        QTimer.singleShot(0, dialog.fit_content_to_family)
        dialog.exec()

    def _purchase_fertilizer_from_dialog(
        self,
        plant_id: str,
        tier: str,
        dialog: QDialog,
        status: QLabel,
    ) -> None:
        ok, message = self._purchase_fertilizer(plant_id, tier, confirmation_parent=dialog)
        message = _learner_text(message)
        if ok:
            self.toast_region.show_message(message)
            dialog.accept()
            return
        if not message:
            return
        status.setText(message)
        status.setAccessibleDescription(message)
        status.setStyleSheet("color:#ffd0d0; background:#582f34; padding:7px; border-radius:7px;")
        status.show()
        status.setFocus()
        announcer = getattr(dialog, "accessibility_announcer", None)
        if announcer is not None:
            announcer.announce(
                message,
                priority=AnnouncementPriority.ASSERTIVE,
                target=status,
            )

    def _purchase_fertilizer(
        self,
        plant_id: str,
        tier: str,
        *,
        confirmation_parent: QWidget | None = None,
    ) -> tuple[bool, str]:
        if self._fertilizer_purchase_pending:
            return False, "A Fertilizer purchase is already being saved."
        self._fertilizer_purchase_pending = True
        try:
            quote = self.engine.quote_purchase(
                PurchaseKind.FERTILIZER,
                tier,
                target_id=plant_id,
            )
            dialog_type = (
                FertilizerReplacementDialog
                if quote.replacement_required else
                PurchaseConfirmationDialog
            )
            confirmation = dialog_type(
                confirmation_parent or self,
                self.engine,
                quote,
            )
            self.purchase_dialog = confirmation
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                route = confirmation.requested_route
                if route in {"nursery", "ways_to_earn", "collection", "customize"}:
                    if confirmation_parent is not None:
                        confirmation_parent.accept()
                    if route == "nursery":
                        QTimer.singleShot(0, lambda: self._open_nursery(tab_index=1))
                    elif route == "ways_to_earn":
                        QTimer.singleShot(0, lambda: self.progress_dialog.open_page("currency"))
                    elif route == "collection":
                        QTimer.singleShot(0, lambda: self.progress_dialog.open_page("collection"))
                    else:
                        QTimer.singleShot(0, self._open_customize)
                return False, ""
            outcome = confirmation.outcome
            if outcome is None or not outcome.success:
                return False, (
                    outcome.message
                    if outcome is not None else
                    "The Fertilizer purchase was not completed."
                )
        finally:
            self._fertilizer_purchase_pending = False
        self._refresh_after_commit("Fertilizer purchase")
        return True, outcome.message

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = GardenSettingsDialog(self, self.engine, self.config)
        elif self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            return
        self.settings_dialog.prepare_to_show()
        self.settings_dialog.present_over_parent()
