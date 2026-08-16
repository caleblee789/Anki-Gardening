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
from .dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
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
from .formatters import format_status_label
from .garden_studio import GardenStudioWidget
from .plant_display import (
    CURRENT_ONBOARDING_VERSION,
    achievement_progress_display,
    chronological_memories,
    growth_display,
    story_is_just_beginning,
)
from .scene import GardenSceneWidget
from .state import GardenUiCoordinator, select_garden_ui
from .state_contracts import (
    DailyProgressState,
    OnboardingState,
    daily_progress_display,
    onboarding_state_display,
    streak_presentation,
)
from .theme import (
    BUTTON_MIN_HEIGHT,
    BUTTON_VARIANT_DESTRUCTIVE,
    BUTTON_VARIANT_PRIMARY,
    BUTTON_VARIANT_SECONDARY,
    BUTTON_VARIANT_TERTIARY,
    GARDEN_THEME,
    ICON_BUTTON_SIZE,
    PLANT_ACTION_MIN_HEIGHT,
    FeedbackTone,
    SemanticRole,
    TextRole,
    apply_tabular_numerals,
    apply_text_role,
    button_stylesheet,
    foundation_stylesheet,
    set_control_enabled,
    set_icon_accessible_name,
    set_keyboard_focus_surface,
    set_semantic_role,
)
from ..display_telemetry import DISPLAY_TELEMETRY
from ..build_capabilities import DEVELOPMENT_MUTATION_ENABLED
from ..environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    GrowthChargeSpec,
)
from ..config import ConfigError, DEFAULT_CONFIG
from ..models.state import (
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    MAX_GARDEN_NAME_LENGTH,
    MAX_PLANT_NAME_LENGTH,
    STATE_VERSION,
    STREAK_BONUS_TIERS,
    STREAK_REWARD_MILESTONES,
)
from ..notices import USER_NOTICES
from ..terminology import (
    ACTIVE_PLANT_EXPLANATION,
    ALL_DUE_EXPLANATION,
    ANKI_STREAK_EXPLANATION,
    FERTILIZER_EXPLANATION,
    GARDEN_CURRENCY_EXPLANATION,
    GROWTH_EXPLANATION,
)
from .copy import (
    ALL_PLANTS_COMPLETE,
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
    "settings_window_title": "Anki Garden Settings",
    "advanced_hint": "Start with the plain-language status below. Copy the report if you need help troubleshooting.",
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
        self._registered_scroll_regions: list[QScrollArea] = []
        self._scroll_base_margins: dict[int, tuple[int, int, int, int]] = {}
        self._pinned_footer: QWidget | None = None
        self._dialog_result = int(QDialog.DialogCode.Rejected)
        self._dialog_event_loop: QEventLoop | None = None
        self._dialog_exec_active = False
        self._modal_requested = False
        self._native_position_initialized = False
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

    def set_initial_focus(
        self,
        widget: QWidget | None,
        policy: InitialFocusPolicy = InitialFocusPolicy.EXPLICIT,
    ) -> None:
        self._initial_focus_target = widget
        self._initial_focus_policy = InitialFocusPolicy(policy)
        self.setProperty("initialFocusPolicy", self._initial_focus_policy.value)

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
        clearance = (
            max(0, int(footer.height()))
            if footer is not None and footer.isVisible()
            else 0
        )
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
        self.setMinimumSize(
            min(policy.min_width, width),
            min(policy.min_height, height),
        )
        self.setMaximumSize(policy.max_width, policy.max_height)
        self.resize(width, height)
        self.setProperty("dialogSizeClass", size_class.value)
        return width, height

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

    def _position_over_parent_once(self) -> None:
        """Center the first show, then preserve every user move and resize."""

        if self._native_position_initialized:
            return
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
        self.reject()
        if self.isVisible():
            event.ignore()
        else:
            event.accept()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)


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

        self.header = QFrame()
        self.header.setProperty("dialogHeader", True)
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
        self.top_close = QPushButton("×", self.header)
        self.top_close.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        set_icon_accessible_name(
            self.top_close,
            f"Close {title}",
            tooltip=f"Close {title}",
        )
        _set_button_variant(self.top_close, BUTTON_VARIANT_TERTIARY)
        self.top_close.setVisible(show_close)
        self.top_close.clicked.connect(self.reject)
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

        self.footer = QFrame()
        self.footer.setProperty("actionFooter", True)
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
    ) -> None:
        state = DialogViewState(state)
        self._dialog_state = state
        self._state_retry_callback = retry
        ready = state is DialogViewState.READY
        for widget in self._body_widgets:
            widget.setVisible(ready)
        self.state_panel.setVisible(not ready)
        if ready:
            self._state_focus_target = None
            self.state_message.setText("")
            self.state_retry.hide()
            self._apply_initial_focus()
            return
        fallback = (
            "Loading…"
            if state is DialogViewState.LOADING
            else "This view could not be loaded."
        )
        text = str(message or fallback)
        self.state_message.setText(text)
        self.state_message.setAccessibleDescription(text)
        self.state_panel.setProperty(
            "dialogState",
            state.value,
        )
        self.state_retry.setVisible(
            state is DialogViewState.ERROR and retry is not None
        )
        self.accessibility_announcer.announce(
            text,
            priority=(
                AnnouncementPriority.ASSERTIVE
                if state is DialogViewState.ERROR
                else AnnouncementPriority.POLITE
            ),
            target=self.state_panel,
        )
        if self.state_retry.isVisible():
            self._state_focus_target = self.state_retry
        elif self.top_close.isVisible():
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


def _nurtured_badge_declarations() -> str:
    """Keep the nurtured status visually identical across Garden surfaces."""

    t = GARDEN_THEME
    return (
        f"color:{t['action_text']}; background:{t['coin_accent']}; border:0; "
        "border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700;"
    )


def _garden_dialog_stylesheet() -> str:
    t = GARDEN_THEME
    return foundation_stylesheet() + f"""
        QWidget[gardenDialogShell='true'] {{ background:{t['dialog_surface']}; color:{t['text_primary']}; }}
        QFrame[dialogHeader='true'] {{ background:transparent; border:0; }}
        QLabel {{ color:{t['text_primary']}; font-size:14px; }}
        QLabel[dialogTitle='true'] {{ color:{t['text_primary']}; font-size:22px; font-weight:700; }}
        QLabel[dialogSubtitle='true'] {{ color:{t['text_secondary']}; font-size:13px; }}
        QPushButton[iconButton='true'] {{ min-width:{ICON_BUTTON_SIZE}px; min-height:{ICON_BUTTON_SIZE}px; padding:0; border-radius:8px; background:transparent; border:1px solid transparent; font-size:22px; }}
        QPushButton[iconButton='true']:hover {{ background:{t['raised_surface']}; border-color:{t['subtle_border']}; }}
        QPushButton[iconButton='true']:focus {{ border:2px solid {t['focus_ring']}; }}
        QFrame[actionFooter='true'] {{ background:{t['dialog_surface']}; border-top:1px solid {t['subtle_border']}; }}
        QFrame[sectionCard='true'], QFrame[statSummary='true'] {{ background:{t['raised_surface']}; border:0; border-radius:12px; }}
        QLabel[summaryLabel='true'] {{ color:{t['text_muted']}; font-size:13px; }}
        QLabel[summaryValue='true'] {{ color:{t['text_primary']}; font-size:30px; font-weight:700; }}
        QFrame[emptyState='true'] {{ background:{t['raised_surface']}; border:0; border-radius:10px; }}
        QLabel[emptyTitle='true'] {{ color:{t['text_primary']}; font-size:15px; font-weight:700; }}
        QLabel[emptyBody='true'] {{ color:{t['text_secondary']}; font-size:13px; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary'] {{ background:{t['action_accent']}; border:1px solid {t['action_border']}; color:{t['action_text']}; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary']:hover {{ background:{t['action_hover']}; }}
        QFrame[emptyState='true'] QPushButton[emptyStateAction='true'][variant='primary']:pressed {{ background:{t['action_pressed']}; }}
        QLabel[nurturedBadge='true'] {{ {_nurtured_badge_declarations()} }}
        QPushButton[disclosureRow='true'] {{ min-height:{BUTTON_MIN_HEIGHT}px; text-align:left; padding:0 8px; color:{t['text_secondary']}; background:transparent; border:0; border-bottom:1px solid {t['subtle_border']}; border-radius:0; }}
        QPushButton[disclosureRow='true']:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QPushButton[disclosureRow='true']:focus {{ border:2px solid {t['focus_ring']}; }}
        QFrame[dataTable='true'] {{ background:transparent; border:0; }}
        QFrame[sideNavigation='true'] {{ background:transparent; border:0; }}
        QPushButton[sideNavItem='true'] {{ min-height:44px; padding:0 14px; text-align:left; color:{t['text_secondary']}; background:transparent; border:0; border-left:3px solid transparent; border-radius:8px; font-size:14px; font-weight:600; }}
        QPushButton[sideNavItem='true']:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QPushButton[sideNavItem='true'][selected='true'] {{ color:{t['text_primary']}; background:{t['selected_surface']}; border-left:3px solid {t['growth_accent']}; }}
        QPushButton[sideNavItem='true']:focus {{ border:2px solid {t['focus_ring']}; border-left:3px solid {t['growth_accent']}; }}
        QCheckBox[toggleSwitch='true'] {{ min-height:44px; spacing:10px; color:{t['text_primary']}; border:2px solid transparent; border-radius:8px; }}
        QCheckBox[toggleSwitch='true']:focus {{ border-color:{t['focus_ring']}; }}
        QCheckBox[toggleSwitch='true']::indicator {{ width:0; height:0; border:0; }}
        QTabWidget::pane {{ border:0; background:{t['dialog_surface']}; top:-1px; }}
        QTabBar {{ background:{t['dialog_surface']}; border-bottom:1px solid {t['subtle_border']}; }}
        QTabBar::tab {{ min-height:44px; padding:0 16px; margin-right:2px; color:{t['text_secondary']}; background:{t['dialog_surface']}; border:0; border-bottom:2px solid transparent; }}
        QTabBar::tab:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QTabBar::tab:selected {{ color:{t['text_primary']}; background:{t['raised_surface']}; border-bottom:2px solid {t['growth_accent']}; }}
        QTabBar::tab:focus {{ border:2px solid {t['focus_ring']}; border-bottom:2px solid {t['growth_accent']}; }}
        QScrollArea {{ background:transparent; border:0; }}
        QLineEdit, QTextEdit {{ color:{t['text_primary']}; background:#10241f; border:1px solid {t['subtle_border']}; border-radius:8px; padding:7px 9px; selection-background-color:{t['action_accent']}; }}
        QLineEdit {{ min-height:44px; padding:0 10px; }}
        QLineEdit:hover, QTextEdit:hover {{ border-color:{t['strong_border']}; }}
        QLineEdit:focus, QTextEdit:focus {{ border:2px solid {t['focus_ring']}; padding:6px 8px; }}
        QScrollBar:vertical {{ width:10px; margin:2px; background:transparent; }}
        QScrollBar::handle:vertical {{ min-height:30px; border-radius:4px; background:#587066; }}
        QScrollBar::handle:vertical:hover {{ background:#789185; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
    """


class ConfirmationDialog:
    """One confirmation contract for destructive or replacement actions."""

    @staticmethod
    def confirm(parent: QWidget, title: str, message: str) -> bool:
        return QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Yes


class FertilizerReplacementDialog(DialogShell):
    """Product-aware confirmation for replacing a timed Fertilizer."""

    def __init__(
        self,
        parent: QWidget,
        *,
        current_name: str,
        current_effect: str,
        remaining_time: str,
        new_name: str,
        new_effect: str,
        cost: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Replace active Fertilizer?")
        self.setModal(True)
        self.apply_size_policy(DialogSizeClass.COMPARISON)
        self.setStyleSheet(_garden_dialog_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Replace active Fertilizer?")
        title.setProperty("dialogTitle", True)
        layout.addWidget(title)

        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_scroll.setAccessibleName("Fertilizer replacement details")
        content_host = QWidget()
        content_layout = QVBoxLayout(content_host)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        self.comparison = QHBoxLayout()
        self.comparison.setSpacing(10)

        def summary(title_text: str, name_text: str, *details: str) -> QFrame:
            card = QFrame()
            card.setProperty("sectionCard", True)
            card.setMinimumWidth(0)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(5)
            heading = QLabel(title_text)
            heading.setProperty("dialogSubtitle", True)
            name = QLabel(name_text)
            name.setStyleSheet("font-weight:700;")
            name.setWordWrap(True)
            card_layout.addWidget(heading)
            card_layout.addWidget(name)
            for detail_text in details:
                detail = QLabel(detail_text)
                detail.setWordWrap(True)
                apply_tabular_numerals(detail)
                card_layout.addWidget(detail)
            card_layout.addStretch(1)
            return card

        self.current_summary = summary(
            "Current",
            current_name,
            current_effect,
            f"{remaining_time} remaining",
        )
        self.new_summary = summary("New", new_name, new_effect, cost_label(cost))
        self.comparison.addWidget(self.current_summary, 1)
        self.comparison.addWidget(self.new_summary, 1)
        content_layout.addLayout(self.comparison)
        warning = QLabel(
            f"Replacing now discards {remaining_time} of active Fertilizer time."
        )
        warning.setWordWrap(True)
        warning.setProperty("fieldError", True)
        apply_tabular_numerals(warning)
        content_layout.addWidget(warning)
        content_layout.addStretch(1)
        self.content_scroll.setWidget(content_host)
        _set_scroll_surface(
            self.content_scroll,
            content_host,
            GARDEN_THEME["dialog_surface"],
        )
        layout.addWidget(self.content_scroll, 1)
        self.register_scroll_region(self.content_scroll)

        self.action_footer = QFrame()
        self.action_footer.setProperty("actionFooter", True)
        self.actions = QHBoxLayout()
        self.action_footer.setLayout(self.actions)
        self.actions.setContentsMargins(0, 10, 0, 0)
        self.actions.addStretch(1)
        self.cancel_action = QPushButton("Keep current")
        self.replace_action = QPushButton("Replace")
        self.replace_action.setAccessibleName(
            f"Replace {current_name} with {new_name} for {max(0, int(cost)):,} Garden Coins"
        )
        self.replace_action.setAccessibleDescription(
            f"{cost_label(cost)}. Replacing discards {remaining_time} of active Fertilizer time."
        )
        _set_button_variant(self.cancel_action, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.replace_action, BUTTON_VARIANT_PRIMARY)
        self.cancel_action.clicked.connect(self.reject)
        self.replace_action.clicked.connect(self.accept)
        self.actions.addWidget(self.cancel_action)
        self.actions.addWidget(self.replace_action)
        layout.addWidget(self.action_footer)
        self.register_pinned_footer(self.action_footer)
        self.setTabOrder(self.cancel_action, self.replace_action)
        self.set_initial_focus(
            self.cancel_action,
            InitialFocusPolicy.SAFE_ACTION,
        )

        self.comparison_responsive = AdaptiveSplit.for_box_layout(
            "fertilizer-replacement.comparison",
            AdaptiveRegion.measured(
                "current-fertilizer",
                self.current_summary,
                floor=220,
            ),
            AdaptiveRegion.measured(
                "new-fertilizer",
                self.new_summary,
                floor=220,
            ),
            layout=self.comparison,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=10,
            telemetry_target=self,
        )
        self.actions_responsive = AdaptiveRow.for_box_layout(
            "fertilizer-replacement.actions",
            (
                AdaptiveRegion.measured(
                    "keep-current",
                    self.cancel_action,
                    floor=112,
                ),
                AdaptiveRegion.measured(
                    "replace",
                    self.replace_action,
                    floor=112,
                ),
            ),
            layout=self.actions,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.action_footer,
        )

    def resizeEvent(self, event: Any) -> None:
        margins = self.layout().contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "comparison_responsive"):
            comparison = self.comparison_responsive.evaluate(available)
            actions = self.actions_responsive.evaluate(available)
            self.setProperty("comparisonMode", comparison.mode)
            self.setProperty("actionMode", actions.mode)
            self.setProperty("layoutMode", comparison.mode)
        super().resizeEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)


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
        self._callback: Callable[[], None] | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.action = QPushButton("")
        _set_button_variant(self.action, BUTTON_VARIANT_SECONDARY)
        self.action.clicked.connect(self._run_action)
        self.dismiss = QPushButton("Dismiss")
        self.dismiss.setAccessibleName("Dismiss Garden update")
        _set_button_variant(self.dismiss, BUTTON_VARIANT_SECONDARY)
        self.dismiss.clicked.connect(self.clear)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.action)
        layout.addWidget(self.dismiss)
        self.dismiss.hide()
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
    ) -> None:
        self._generation += 1
        generation = self._generation
        text = _learner_text(message)
        self._callback = callback
        self.message.setText(text)
        self.setAccessibleDescription(text)
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text and callback is not None))
        if dismissible is None:
            dismissible = bool(error and duration_ms is not None and duration_ms <= 0)
        self.dismiss.setVisible(bool(dismissible))
        self.setProperty("error", bool(error))
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
            QTimer.singleShot(duration_ms, lambda: self._clear_generation(generation))

    def _run_action(self) -> None:
        callback = self._callback
        self.clear()
        if callback is not None:
            callback()

    def _clear_generation(self, generation: int) -> None:
        if generation == self._generation:
            self.clear()

    def clear(self) -> None:
        self._generation += 1
        self._callback = None
        self.message.setText("")
        self.setAccessibleDescription("")
        self.dismiss.hide()
        self.hide()


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


def _transaction_date(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return f"{parsed.strftime('%b')} {parsed.day}"
    except (TypeError, ValueError):
        return "—"


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
    pixmap = QPixmap(str(path)) if path else QPixmap()
    if pixmap.isNull():
        set_semantic_role(label, SemanticRole.MISSING_ART)
        label.setText("")
        label.setPixmap(
            _botanical_placeholder_pixmap(size, size, stage=str(stage))
        )
        label.setAccessibleDescription(
            f"Artwork unavailable for {species_name} at the {stage_name} stage; "
            "a botanical fallback illustration is shown."
        )
        return label
    bounds = (
        placement.get("visible_bounds", placement.get("art_bounds"))
        if isinstance(placement, dict)
        else getattr(placement, "visible_bounds", getattr(placement, "art_bounds", None))
    )
    left, top, width, height = _padded_preview_bounds(bounds)
    source_width, source_height = pixmap.width(), pixmap.height()
    crop_x = max(0, min(source_width - 1, round(left * source_width)))
    crop_y = max(0, min(source_height - 1, round(top * source_height)))
    crop_width = max(1, min(source_width - crop_x, round(width * source_width)))
    crop_height = max(1, min(source_height - crop_y, round(height * source_height)))
    cropped = pixmap.copy(crop_x, crop_y, crop_width, crop_height)
    if not cropped.isNull():
        pixmap = cropped
    stage_fill = {
        "seed": 0.92,
        "sprout": 0.88,
        "young": 0.84,
        "mature": 0.82,
        "flowering": 0.86,
        "rare": 0.86,
    }.get(str(stage).lower(), 0.84)
    target = max(24, round(size * stage_fill))
    label.setPixmap(pixmap.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ))
    return label


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
        target.setText("")
        target.setPixmap(
            _botanical_placeholder_pixmap(size, size, stage=str(stage))
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
        set_semantic_role(label, SemanticRole.MISSING_ART)
        label.setText("")
        label.setPixmap(_botanical_placeholder_pixmap(size, size))
        label.setToolTip(accessible_name)
        label.setAccessibleDescription(
            f"Artwork unavailable for {accessible_name}; a botanical fallback illustration is shown."
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


def _environment_placeholder_pixmap(width: int, height: int) -> QPixmap:
    """Provide a graphical fail-closed preview instead of substituting copy."""

    preview = QPixmap(max(1, width), max(1, height))
    preview.fill(QColor("#14251f"))
    painter = QPainter(preview)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#d7b764"))
    diameter = max(12, min(width, height) // 5)
    painter.drawEllipse(max(6, width - diameter - 14), 12, diameter, diameter)
    painter.setBrush(QColor("#355b48"))
    painter.drawRect(0, max(1, height * 2 // 3), width, max(1, height // 3))
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
            QPixmap(str(base_path)) if base_path else QPixmap(),
            width,
            height,
        )
        if result.isNull():
            return _environment_placeholder_pixmap(width, height)
        if item.kind == "weather":
            weather_asset = engine.resolve_weather_preview_asset(item.item_id)
            weather_path = getattr(weather_asset, "path", None)
            overlay = _cover_pixmap(
                QPixmap(str(weather_path)) if weather_path else QPixmap(),
                width,
                height,
            )
            if overlay.isNull():
                overlay = _weather_placeholder_overlay(width, height)
            painter = QPainter(result)
            painter.drawPixmap(0, 0, overlay)
            painter.end()
        return result
    except Exception:
        logger.exception(
            "Anki Garden: environment preview composition failed for %s",
            item.item_id,
        )
        return _environment_placeholder_pixmap(width, height)


class ArtworkThumbnail(QLabel):
    """Metadata-cropped artwork preview; source sprite geometry remains untouched."""

    pass


def _fertilizer_action_label(
    current_tier: str,
    selected_tier: str,
    fertilizer_name: str,
) -> str:
    current = str(current_tier or "").lower()
    selected = str(selected_tier or "").lower()
    if not current:
        return f"Use {fertilizer_name}"
    if current == selected:
        return f"Extend {fertilizer_name}"
    return f"Replace with {fertilizer_name}"


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


class EmptyState(QFrame):
    """Compact explanation-first empty state with an optional next action."""

    def __init__(
        self,
        title: str,
        description: str,
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
        body = QLabel(description)
        body.setProperty("emptyBody", True)
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        if action is not None:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignLeft)
            action.setProperty("emptyStateAction", True)
            _pin_empty_state_action_style(
                action,
                str(action.property("variant") or BUTTON_VARIANT_PRIMARY),
            )


class DisclosureRow(QWidget):
    """Keyboard-native disclosure with visible state and no independent scrolling."""

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        *,
        expanded: bool = False,
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


class ActionFooter(QFrame):
    """Static action row for dialogs that genuinely have a primary action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("actionFooter", True)


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


class ProgressList(QWidget):
    """A scrollable, content-sized list used by one Garden Progress tab."""

    def __init__(self, accessible_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self.container = QWidget()
        self.container.setStyleSheet("background:#0b1f1b;")
        self.container.setMinimumWidth(0)
        self.container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.viewport().setStyleSheet("background:#0b1f1b;")
        self.scroll.setAccessibleName(f"{accessible_name} scroll area")
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(4, 4, 22, 4)
        self.rows.setSpacing(5)
        self.scroll.setWidget(self.container)
        _set_scroll_surface(self.scroll, self.container, "#0b1f1b")
        outer.addWidget(self.scroll)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # A nested dialog event loop can defer deleteLater long enough
                # for two generations to paint at once. Detach immediately.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.container.updateGeometry()

    def add_row(self, row: QWidget) -> None:
        self.rows.addWidget(row)

    def add_empty(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("rowCriteria", True)
        self.rows.addWidget(label)

    def finish(self) -> None:
        self.container.adjustSize()


class ProgressCardGrid(QWidget):
    """Responsive catalogue grid for achievements and collected plants."""

    def __init__(
        self,
        accessible_name: str,
        parent: QWidget | None = None,
        *,
        wide_columns: int = 2,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self._entries: list[tuple[QWidget, bool]] = []
        self._wide_columns = max(1, int(wide_columns))
        self._columns = self._wide_columns
        self.container = QWidget()
        self.container.setStyleSheet("background:#071a15;")
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
        self.scroll.viewport().setStyleSheet("background:#071a15;")
        self.scroll.setAccessibleName(f"{accessible_name} scroll area")
        self.scroll.setWidget(self.container)
        _set_scroll_surface(self.scroll, self.container, "#071a15")
        outer.addWidget(self.scroll)

    def clear(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for widget, _full_width in self._entries:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        self._entries.clear()

    def add_card(self, card: QWidget) -> None:
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._entries.append((card, False))
        self._reflow()

    def add_full_width(self, widget: QWidget) -> None:
        self._entries.append((widget, True))
        self._reflow()

    def add_empty(self, title: str, body: str = "") -> None:
        self.add_full_width(EmptyState(title, body))

    def _reflow(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        row = 0
        column = 0
        for widget, full_width in self._entries:
            if full_width:
                if column:
                    row += 1
                    column = 0
                self.grid.addWidget(widget, row, 0, 1, self._columns)
                row += 1
                continue
            self.grid.addWidget(widget, row, column)
            column += 1
            if column >= self._columns:
                row += 1
                column = 0
        for index in range(self._columns):
            self.grid.setColumnStretch(index, 1)
        self.grid.setRowStretch(row + (1 if column else 0), 1)
        self.container.updateGeometry()

    def finish(self) -> None:
        self._reflow()

    def resizeEvent(self, event: Any) -> None:
        width = event.size().width()
        columns = responsive_column_count(
            width,
            minimum_item_width=180,
            maximum_columns=self._wide_columns,
            spacing=self.grid.horizontalSpacing(),
        )
        if columns != self._columns:
            self._columns = columns
            self._reflow()
        super().resizeEvent(event)


class ResponsiveTileGrid(QWidget):
    """Content-sized two-to-one column grid for catalog tiles."""

    def __init__(self, *, breakpoint: int = 560, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.breakpoint = int(breakpoint)
        self.minimum_tile_width = max(
            180,
            (self.breakpoint - 10 - 24) // 2,
        )
        self._columns = 2
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
            maximum_columns=2,
            spacing=self.grid.horizontalSpacing(),
        )
        if columns != self._columns:
            self._columns = columns
            self._reflow()
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
            DialogSizeClass.CATALOG,
            preferred_width=980,
            preferred_height=680,
        )
        self.setStyleSheet(_garden_dialog_stylesheet() + f"""
            QLabel[saveStatus='true'] {{ padding:5px 8px; border-radius:8px; }}
            QFrame[diagnosticsCard='true'] {{ background:{GARDEN_THEME['raised_surface']}; border:0; border-left:4px solid {GARDEN_THEME['success']}; border-radius:12px; }}
            QFrame[diagnosticsCard='true'][diagnosticState='warning'] {{ background:#322221; border-left:4px solid #E77D6D; }}
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
        self._persisted_payload = deepcopy(self.behavior.build_theme_payload())
        self._persisted_name = str(
            getattr(self.engine.state, "garden_name", "My Garden") or "My Garden"
        )
        self.save_settings = QPushButton("Save changes")
        self.save_settings.setAccessibleName("Save Anki Garden settings")
        _set_button_variant(self.save_settings, BUTTON_VARIANT_PRIMARY)
        self.save_settings.clicked.connect(self._save_visual_settings)
        set_control_enabled(
            self.save_settings,
            False,
            disabled_reason="No unsaved settings changes.",
        )
        self.restore_defaults = QPushButton("Restore display defaults")
        self.restore_defaults.setAccessibleName("Restore display defaults")
        _set_button_variant(self.restore_defaults, BUTTON_VARIANT_TERTIARY)
        self.restore_defaults.clicked.connect(self._restore_defaults)
        self.reset_tips = QPushButton("Restart onboarding tips")
        self.reset_tips.setAccessibleDescription("Show Garden guidance again the next time the Garden opens.")
        _set_button_variant(self.reset_tips, BUTTON_VARIANT_TERTIARY)
        self.reset_tips.clicked.connect(self._reset_tips)
        self.behavior.advanced_actions_layout.addWidget(self.restore_defaults)
        self.behavior.advanced_actions_layout.addWidget(self.reset_tips)
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
        self.garden_name_edit.setFixedHeight(BUTTON_MIN_HEIGHT)
        self.garden_name_edit.setAccessibleName("Garden name")
        self.garden_name_edit.setAccessibleDescription(
            f"The name shown on your Garden and Anki home preview. Up to {MAX_GARDEN_NAME_LENGTH} characters."
        )
        self.set_initial_focus(
            self.garden_name_edit,
            InitialFocusPolicy.FIRST_EDITABLE,
        )
        garden_name_copy.addWidget(garden_name_label)
        garden_name_copy.addWidget(self.garden_name_edit)
        self.garden_name_error = QLabel(
            f"Garden name must be 1 to {MAX_GARDEN_NAME_LENGTH} characters."
        )
        self.garden_name_error.setProperty("fieldError", True)
        self.garden_name_error.setWordWrap(True)
        self.garden_name_error.setAccessibleName("Garden name error")
        self.garden_name_error.hide()
        garden_name_copy.addWidget(self.garden_name_error)
        garden_name_help = QLabel("Shown in the Garden header and home-screen preview.")
        garden_name_help.setWordWrap(True)
        garden_name_help.setProperty("dialogSubtitle", True)
        garden_name_copy.addWidget(garden_name_help)
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
        behavior_scroll = QScrollArea()
        behavior_scroll.setWidgetResizable(True)
        behavior_scroll.setFrameShape(QFrame.Shape.NoFrame)
        behavior_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        behavior_scroll.setAccessibleName("Display settings")
        behavior_scroll.setWidget(behavior)
        _set_scroll_surface(
            behavior_scroll,
            behavior,
            GARDEN_THEME["dialog_surface"],
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
        advanced.setWidgetResizable(True)
        advanced.setFrameShape(QFrame.Shape.NoFrame)
        advanced.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        advanced.setAccessibleName("Troubleshooting settings")
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
        self.troubleshooting_status = QLabel("No display issues detected")
        self.troubleshooting_status.setProperty("diagnosticsTitle", True)
        self.troubleshooting_status.setWordWrap(True)
        self.troubleshooting_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.troubleshooting_status)
        self.troubleshooting_status.setAccessibleName("Troubleshooting report status")
        self.diagnostics_summary = QLabel("")
        self.diagnostics_summary.setWordWrap(True)
        self.diagnostics_summary.setProperty("dialogSubtitle", True)
        self.diagnostics_checked = QLabel("Last checked just now")
        self.diagnostics_checked.setProperty("diagnosticsMeta", True)
        self.diagnostics_version = QLabel(f"Anki Garden {_addon_human_version()}")
        self.diagnostics_version.setProperty("diagnosticsMeta", True)
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
        diagnostics_copy.addWidget(self.diagnostics_build)
        diagnostics_copy.addWidget(self.diagnostics_environment)
        diagnostics_layout.addWidget(self.diagnostics_icon, 0, Qt.AlignmentFlag.AlignTop)
        diagnostics_layout.addLayout(diagnostics_copy, 1)
        a_layout.addWidget(self.diagnostics_card)
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        # Technical details expand to their full document height so the outer
        # Settings page remains the only vertical scroll owner.
        self.debug_report.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.debug_report.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.debug_report.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size:13px;")
        self.debug_report.hide()
        refresh_debug = QPushButton("Refresh diagnostics")
        copy_debug = QPushButton("Copy report")
        _set_button_variant(refresh_debug, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(copy_debug, BUTTON_VARIANT_SECONDARY)
        refresh_debug.clicked.connect(self._refresh_debug_report)
        copy_debug.clicked.connect(self._copy_debug_report)
        report_actions = QHBoxLayout()
        report_actions.addWidget(refresh_debug)
        report_actions.addWidget(copy_debug)
        self.report_details_toggle = QPushButton("View technical details")
        self.report_details_toggle.setCheckable(True)
        _set_button_variant(self.report_details_toggle, BUTTON_VARIANT_TERTIARY)
        self.report_details_toggle.toggled.connect(self._toggle_debug_report)
        report_actions.addWidget(self.report_details_toggle)
        report_actions.addStretch(1)
        a_layout.addLayout(report_actions)
        a_layout.addWidget(self.debug_report)
        self._development_backup_path: Path | None = None
        if DEVELOPMENT_MUTATION_ENABLED:
            self.unlock_development = QPushButton("Unlock development tools")
            _set_button_variant(self.unlock_development, BUTTON_VARIANT_SECONDARY)
            self.unlock_development.setAccessibleDescription(
                "Reveal temporary state-population tools for this Settings session."
            )
            self.unlock_development.clicked.connect(self._unlock_development_tools)
            a_layout.addWidget(self.unlock_development)
            self.development_panel = QFrame()
            self.development_panel.setStyleSheet(
                "QFrame { background:#4a2b22; border:1px solid #b67656; border-radius:9px; }"
            )
            development_layout = QVBoxLayout(self.development_panel)
            development_warning = QLabel(
                "Development only: this replaces the current Garden with a populated test catalog. "
                "A recovery backup is created first."
            )
            development_warning.setWordWrap(True)
            development_layout.addWidget(development_warning)
            development_actions = QHBoxLayout()
            self.populate_development = QPushButton("Populate test garden")
            self.restore_development = QPushButton("Restore backup")
            _set_button_variant(self.populate_development, BUTTON_VARIANT_PRIMARY)
            _set_button_variant(self.restore_development, BUTTON_VARIANT_SECONDARY)
            set_control_enabled(
                self.restore_development,
                False,
                disabled_reason="Create a development backup before restoring it.",
            )
            self.populate_development.clicked.connect(self._populate_development_garden)
            self.restore_development.clicked.connect(self._restore_development_garden)
            development_actions.addWidget(self.populate_development)
            development_actions.addWidget(self.restore_development)
            development_actions.addStretch(1)
            development_layout.addLayout(development_actions)
            self.development_panel.hide()
            a_layout.addWidget(self.development_panel)
        self._refresh_debug_report()
        a_layout.addStretch(1)

        self.tabs.addTab(behavior_scroll, "Display")
        self.tabs.addTab(advanced, UI_TEXT["tab_advanced"])
        self.tabs.currentChanged.connect(self._sync_settings_tab)
        self._sync_settings_tab(0)
        self._refresh_garden_name()

    def _apply_settings_footer_layout(self, width: int) -> None:
        telemetry = self.settings_footer_responsive.evaluate(width)
        self.setProperty("footerMode", telemetry.mode)

    def _set_settings_footer_mode(self, mode: str) -> None:
        compact = mode == COMPACT_MODE
        if compact == self._settings_footer_compact:
            return
        self._settings_footer_compact = compact
        buttons = (self.cancel_settings, self.save_settings)
        for button in buttons:
            self.settings_footer_grid.removeWidget(button)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding if compact else QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
        for column in range(5):
            self.settings_footer_grid.setColumnStretch(column, 0)
        if compact:
            self.settings_footer_grid.addWidget(self.cancel_settings, 0, 0)
            self.settings_footer_grid.addWidget(self.save_settings, 0, 1)
            self.settings_footer_grid.setColumnStretch(0, 1)
            self.settings_footer_grid.setColumnStretch(1, 1)
        else:
            self.settings_footer_grid.addWidget(self.cancel_settings, 0, 0)
            self.settings_footer_grid.addWidget(self.save_settings, 0, 1)

    def _sync_settings_tab(self, index: int) -> None:
        troubleshooting = int(index) == 1
        self.settings_footer_actions.setVisible(not troubleshooting)
        self.save_status.setVisible(not troubleshooting and bool(self.save_status.text()))
        self.footer.setVisible(not troubleshooting)
        self.setProperty(
            "layoutMode",
            "troubleshooting" if troubleshooting else "display",
        )
        QTimer.singleShot(0, self._sync_footer_clearance)

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
        if hasattr(self, "debug_report") and self.debug_report.isVisible():
            # With both QTextEdit scrollbars disabled, its document retains
            # the old wrap width until Qt settles the resized viewport.
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

    def _refresh_garden_name(self) -> None:
        name = str(getattr(self.engine.state, "garden_name", "My Garden") or "My Garden")
        self.garden_name_edit.blockSignals(True)
        self.garden_name_edit.setText(name)
        self.garden_name_edit.blockSignals(False)
        self.garden_name_edit.setToolTip(name)
        self._set_garden_name_validation(True)

    def _set_garden_name_validation(self, valid: bool) -> None:
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
        dirty = self._draft_is_dirty()
        self._set_garden_name_validation(valid)
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
        if dirty:
            self.save_status.setVisible(self.tabs.currentIndex() != 1)
            self.save_status.setText("Unsaved changes" if valid else "Fix 1 error before saving.")
            self.save_status.setStyleSheet(
                "color:#d8e3e5; background:#24343d;" if valid else
                "color:#ffd0d0; background:#582f34;"
            )
            self.save_status.setAccessibleDescription(self.save_status.text())
        elif self.save_status.text() != "Saved":
            self.save_status.setText("")
            self.save_status.setStyleSheet("")
            self.save_status.setAccessibleDescription("")
            self.save_status.hide()

    def _draft_is_dirty(self) -> bool:
        draft_name = " ".join(self.garden_name_edit.text().split())
        return (
            self.behavior.build_theme_payload() != self._persisted_payload
            or draft_name != self._persisted_name
        )

    def _restore_defaults(self) -> None:
        if not ConfirmationDialog.confirm(
            self,
            "Restore default settings?",
            "Stage these defaults: garden name “My Garden”, Home preview on, and progress notifications on. Scenery and gameplay progress will not change.",
        ):
            return
        self.garden_name_edit.setText("My Garden")
        self.behavior.show_home_widget.setChecked(True)
        self.behavior.show_progress_notifications.setChecked(
            DEFAULT_CONFIG["show_progress_notifications"]
        )
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
        opener = getattr(parent, "_open_customize", None)
        if callable(opener):
            QTimer.singleShot(0, opener)

    def _reset_tips(self) -> None:
        try:
            self.config.update({"onboarding_version": 0})
        except ConfigError as exc:
            self._show_save_error(str(exc))
            return
        parent = self.parent()
        refresh_committed = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh_committed):
            refresh_committed("tips reset")
        self.save_status.show()
        self.save_status.setText("Garden tips will be shown again.")
        self.save_status.setStyleSheet("color:#baf3c6; background:#1d4931;")

    def _save_visual_settings(self) -> None:
        old_payload = deepcopy(self._persisted_payload)
        old_name = self._persisted_name
        payload = self.behavior.build_theme_payload()
        draft_name = " ".join(self.garden_name_edit.text().split())
        if not draft_name or len(draft_name) > MAX_GARDEN_NAME_LENGTH:
            self._set_garden_name_validation(False)
            self.save_status.show()
            self.save_status.setText("Fix 1 error before saving.")
            self.save_status.setStyleSheet("color:#ffd0d0; background:#582f34;")
            self.save_status.setAccessibleDescription("Settings error: Fix 1 error before saving.")
            self.garden_name_edit.setFocus()
            self.garden_name_edit.selectAll()
            self.accessibility_announcer.announce(
                "Settings error: Fix 1 error before saving.",
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.save_status,
            )
            return
        try:
            self.config.update(payload)
        except ConfigError as exc:
            self._show_save_error(str(exc))
            return
        except Exception as exc:
            try:
                self.config.update(old_payload)
            except ConfigError:
                logger.exception("Anki Garden: unable to roll back settings")
            self._show_save_error(
                "Settings could not be saved. Your draft is still here and your previous choices remain active."
            )
            logger.exception("Anki Garden: settings save failed", exc_info=exc)
            return
        if draft_name != old_name:
            ok, message = self.engine.rename_garden(draft_name)
            if not ok:
                try:
                    self.config.update(old_payload)
                except ConfigError:
                    logger.exception(
                        "Anki Garden: unable to roll back settings after name save failure"
                    )
                self._show_save_error(
                    f"{_learner_text(message)} Your draft is still here and no Settings changes were applied."
                )
                return
        self._persisted_payload = deepcopy(payload)
        self._persisted_name = draft_name
        self.garden_name_edit.setText(draft_name)
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
        self.save_status.setAccessibleDescription("Anki Garden settings saved successfully.")
        self.accessibility_announcer.announce(
            "Anki Garden settings saved successfully.",
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
            "Discard settings changes?",
            "Your display changes have not been saved. Discard them and close Settings?",
        ):
            return
        self._save_status_generation += 1
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.garden_name_edit.setText(self._persisted_name)
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
            status = "Garden display may be incomplete"
            self.diagnostics_summary.setText(
                "Some artwork or Garden details may not appear correctly. Refresh diagnostics; "
                "if the warning remains, copy the report when requesting help."
            )
            self.diagnostics_summary.show()
            self.diagnostics_icon.setText("!")
            self.diagnostics_icon.setAccessibleName("Diagnostics warning")
            self.diagnostics_icon.setStyleSheet(
                f"color:#2b120f; background:{GARDEN_THEME['error']}; border-radius:20px;"
            )
            self.diagnostics_card.setProperty("diagnosticState", "warning")
        else:
            status = "No display issues detected"
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
            f"Last checked {datetime.now().strftime('%-I:%M %p')}"
        )
        self.diagnostics_build.setText(
            f"Packaged build {_addon_build_identifier()}"
        )

    def _sync_debug_report_height(self) -> None:
        document = self.debug_report.document()
        document.setTextWidth(max(1, int(self.debug_report.viewport().width())))
        report_height = max(
            76,
            int(document.size().height())
            + 2 * int(self.debug_report.frameWidth())
            + 16,
        )
        self.debug_report.setFixedHeight(report_height)

    def _toggle_debug_report(self, expanded: bool) -> None:
        if expanded:
            self._refresh_debug_report()
        self.debug_report.setVisible(bool(expanded))
        if expanded:
            QTimer.singleShot(0, self._sync_debug_report_height)
        self.report_details_toggle.setText(
            "Hide technical details" if expanded else "View technical details"
        )
        self.report_details_toggle.setAccessibleName(self.report_details_toggle.text())
        self.setProperty(
            "layoutMode",
            "troubleshooting-expanded" if expanded else "troubleshooting",
        )

    def _copy_debug_report(self) -> None:
        QGuiApplication.clipboard().setText(self.debug_report.toPlainText())
        self.diagnostics_checked.setText("Report copied to clipboard")
        self.diagnostics_card.setAccessibleDescription("Troubleshooting report copied to the clipboard.")
        self.diagnostics_card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.diagnostics_card)
        self.diagnostics_card.setFocus()
        self.accessibility_announcer.announce(
            "Troubleshooting report copied to the clipboard.",
            target=self.diagnostics_card,
        )

    def _unlock_development_tools(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Development tools",
            "These controls replace Garden state for testing. Unlock them for this Settings session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.development_panel.show()
        self.unlock_development.hide()

    def _populate_development_garden(self) -> None:
        answer = QMessageBox.question(
            self,
            "Populate test garden?",
            "Create a backup, then replace the Garden with a fully populated development state?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = self.engine.storage.create_development_backup()
        except Exception:
            QMessageBox.warning(
                self,
                "Development tools",
                "The recovery backup could not be created, so no Garden data was changed.",
            )
            return
        ok, message = self.engine.development_populate()
        if ok:
            self._development_backup_path = backup
            set_control_enabled(
                self.restore_development,
                True,
                enabled_description="Restore the development backup.",
            )
            parent = self.parent()
            if parent is not None and hasattr(parent, "_refresh_after_commit"):
                parent._refresh_after_commit("development test state")
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Development tools", message
        )

    def _restore_development_garden(self) -> None:
        if self._development_backup_path is None:
            return
        ok, message = self.engine.restore_development_backup(
            self._development_backup_path
        )
        if ok:
            set_control_enabled(
                self.restore_development,
                False,
                disabled_reason="The development backup has already been restored.",
            )
            parent = self.parent()
            if parent is not None and hasattr(parent, "_refresh_after_commit"):
                parent._refresh_after_commit("development backup restore")
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Development tools", message
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
        self.layout.setContentsMargins(8, 2, 8, 2)
        self.layout.setSpacing(0)

    def set_memories(self, memories: list[tuple[str, str]], *, just_beginning: bool = False) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not memories:
            empty = QLabel("New memories will appear as this plant grows.")
            empty.setWordWrap(True)
            empty.setProperty("memoryFuture", True)
            self.layout.addWidget(empty)
        for display_date, text in memories:
            row = QFrame()
            row.setProperty("memoryRow", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 4, 6)
            row_layout.setSpacing(10)
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
            copy.addWidget(date_label)
            copy.addWidget(body)
            row_layout.addWidget(marker)
            row_layout.addLayout(copy, 1)
            self.layout.addWidget(row)
        if just_beginning and memories:
            future = QLabel("New memories will appear as this plant grows.")
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
        self.apply_size_policy(DialogSizeClass.STANDARD_TEXT)
        self.setStyleSheet(_garden_dialog_stylesheet() + """
            QWidget[storyViewport='true'], QWidget[storyBody='true'] { background:#071a15; }
            QFrame[storyHero='true'] { background:transparent; border:0; }
            QFrame[storyTimeline='true'], QFrame[upNext='true'] { background:#0c261f; border:0; border-radius:12px; }
            QFrame[storyStages='true'] { background:transparent; border:0; }
            QFrame[storyStage='true'] { background:#0c261f; border:1px solid #20483c; border-radius:9px; }
            QFrame[storyStage='true'][storyStageState='complete'] { background:#123228; border-color:#4f806e; }
            QFrame[storyStage='true'][storyStageState='current'] { background:#173b30; border:2px solid #e7c96a; }
            QLabel[storyStageName='true'] { color:#cfe0d6; font-size:13px; font-weight:700; }
            QLabel[storyStagePreview='true'] { background:transparent; border:0; color:#a9beb1; font-size:13px; }
            QFrame[memoryRow='true'] { border-left:2px solid #5cc58b; }
            QLabel[memoryMarker='true'] { color:#82e2ac; padding-left:2px; }
            QLabel[memoryDate='true'] { color:#9eb4a8; font-size:13px; font-weight:600; }
            QLabel[memoryFuture='true'] { color:#9eb4a8; font-style:italic; padding:10px 0; }
        """)
        self.story_scroll = QScrollArea()
        self.story_scroll.setWidgetResizable(True)
        self.story_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.story_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        hero = QFrame()
        hero.setProperty("storyHero", True)
        self.hero_layout = QHBoxLayout(hero)
        self.hero_layout.setContentsMargins(14, 12, 14, 12)
        self.name_heading = QLabel()
        self.name_heading.setTextFormat(Qt.TextFormat.PlainText)
        self.name_heading.setWordWrap(True)
        self.name_heading.setStyleSheet("font-size:22px; font-weight:800;")
        self.artwork = QLabel()
        self.artwork.setFixedSize(104, 104)
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
        for row, (key, label_text) in enumerate((
            ("species", "Species"),
            ("stage", "Stage"),
            ("planted", "Planted"),
        )):
            label = QLabel(label_text)
            label.setStyleSheet("color:#a9beb1; font-size:13px;")
            value = QLabel("")
            value.setWordWrap(True)
            self.meta_grid.addWidget(label, row, 0)
            self.meta_grid.addWidget(value, row, 1)
            self.meta_values[key] = value
        self.meta_grid.setColumnStretch(1, 1)
        identity_text.addLayout(self.meta_grid)
        self.nurturing_status = QLabel("Nurtured")
        self.nurturing_status.setProperty("nurturedBadge", True)
        self.nurturing_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nurturing_status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.nurturing_status.setAccessibleDescription(
            "Anki card answers add Growth to this plant."
        )
        identity_text.addWidget(self.nurturing_status, 0, Qt.AlignmentFlag.AlignLeft)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.feedback)
        self.feedback.setAccessibleName("Plant name status")
        self.feedback.hide()
        identity_text.addWidget(self.feedback)
        identity_text.addStretch(1)
        self.hero_layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        self.hero_layout.addLayout(identity_text, 1)
        self.hero_responsive = AdaptiveSplit.for_box_layout(
            "plant-story.hero",
            AdaptiveRegion.fixed(
                "plant-artwork",
                104,
                target=self.artwork,
            ),
            AdaptiveRegion.measured(
                "plant-identity",
                identity_text,
                floor=340,
            ),
            layout=self.hero_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=12,
            telemetry_target=self,
        )
        content.addWidget(hero)

        self.stage_path_scroll = QScrollArea()
        self.stage_path_scroll.setWidgetResizable(True)
        self.stage_path_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.stage_path_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.stage_path_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.stage_path_scroll.setAccessibleName("Six plant growth stages")
        self.stage_path = QFrame()
        self.stage_path.setProperty("storyStages", True)
        self.stage_path.setMinimumWidth(456)
        stage_path_layout = QHBoxLayout(self.stage_path)
        stage_path_layout.setContentsMargins(0, 0, 0, 0)
        stage_path_layout.setSpacing(6)
        self.stage_nodes: dict[str, tuple[QFrame, QLabel]] = {}
        for stage_key in GROWTH_STAGES:
            node = QFrame()
            node.setProperty("storyStage", True)
            node.setMinimumHeight(96)
            node_layout = QVBoxLayout(node)
            node_layout.setContentsMargins(5, 5, 5, 5)
            node_layout.setSpacing(1)
            stage_preview = ArtworkThumbnail()
            stage_preview.setFixedSize(56, 56)
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
            stage_path_layout.addWidget(node, 1)
            self.stage_nodes[stage_key] = (node, stage_preview)
        self.stage_path.setAccessibleName("Six plant growth stages")
        self.stage_path_scroll.setWidget(self.stage_path)
        _set_scroll_surface(
            self.stage_path_scroll,
            self.stage_path,
            GARDEN_THEME["dialog_surface"],
        )
        content.addWidget(self.stage_path_scroll)

        story_panel = QFrame()
        story_panel.setProperty("storyTimeline", True)
        story_layout = QVBoxLayout(story_panel)
        story_layout.setContentsMargins(12, 10, 12, 10)
        story_layout.setSpacing(5)
        timeline_label = QLabel("Memories")
        timeline_label.setStyleSheet("font-size:16px; font-weight:700;")
        story_layout.addWidget(timeline_label)
        self.timeline = MemoryTimeline()
        story_layout.addWidget(self.timeline)
        self.up_next = QFrame()
        self.up_next.setProperty("upNext", True)
        up_next_layout = QVBoxLayout(self.up_next)
        up_next_layout.setContentsMargins(12, 9, 12, 9)
        up_next_title = QLabel("Up next")
        up_next_title.setStyleSheet("font-weight:700; color:#d8b875;")
        self.up_next_text = QLabel("")
        self.up_next_text.setWordWrap(True)
        self.up_next_text.setAccessibleName("Next plant milestone")
        up_next_layout.addWidget(up_next_title)
        up_next_layout.addWidget(self.up_next_text)
        self.choose_another = QPushButton(FULLY_GROWN_ACTION)
        _set_button_variant(self.choose_another, BUTTON_VARIANT_PRIMARY)
        self.choose_another.setAccessibleDescription(FULLY_GROWN_MESSAGE)
        self.choose_another.clicked.connect(self.chooseAnother.emit)
        self.choose_another.hide()
        up_next_layout.addWidget(self.choose_another)
        self.stage_progress = LabeledProgress("Plant progress to the next stage")
        up_next_layout.addWidget(self.stage_progress)
        content.addWidget(story_panel)
        content.addWidget(self.up_next)
        content.addStretch(1)
        self.edit_name_btn.clicked.connect(self._begin_rename)
        self.cancel_name_btn.clicked.connect(self._cancel_rename)
        self.save_name_btn.clicked.connect(self._save_name)
        self.name_edit.returnPressed.connect(self._save_name)
        self._set_editing(False)
        self.refresh()

    def resizeEvent(self, event: Any) -> None:
        margins = self._shell_layout.contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "hero_responsive"):
            telemetry = self.hero_responsive.evaluate(available)
            self.setProperty("heroMode", telemetry.mode)
        super().resizeEvent(event)

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

    def _cancel_rename(self) -> None:
        self.feedback.setText("")
        self.feedback.setAccessibleDescription("")
        self.feedback.hide()
        self._set_editing(False, restore_focus=True)

    def _rename_is_dirty(self) -> bool:
        plant = self._plant()
        if plant is None or not self.name_edit.isVisible():
            return False
        return " ".join(self.name_edit.text().split()) != str(plant.name)

    def _request_close(self) -> None:
        if self._rename_is_dirty() and not ConfirmationDialog.confirm(
            self,
            "Discard plant name change?",
            "The edited plant name has not been saved. Discard it and close Plant Story?",
        ):
            return
        super().accept()

    def reject(self) -> None:
        if self._rename_is_dirty() and not ConfirmationDialog.confirm(
            self,
            "Discard plant name change?",
            "The edited plant name has not been saved. Discard it and close Plant Story?",
        ):
            return
        super().reject()

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
        if memory.kind == "planted":
            return f"{name} joined your garden."
        if memory.kind == "first_nurture":
            return f"You began nurturing {name}."
        if memory.kind == "stage":
            return f"{name} reached {format_status_label(memory.new_stage or 'new growth')}."
        if memory.kind == "streak":
            return f"{name} witnessed your {memory.value}-day Anki streak."
        if memory.kind == "reviews":
            return f"{name} witnessed your {memory.value:,}th card answer."
        return "A garden milestone was reached."

    def refresh(self) -> None:
        plant = self._plant()
        if plant is None:
            self.name_heading.setText("Plant unavailable")
            for value in self.meta_values.values():
                value.setText("Unavailable")
            self.nurturing_status.hide()
            set_control_enabled(
                self.edit_name_btn,
                False,
                disabled_reason="This plant is no longer available to rename.",
            )
            self.artwork.setText("")
            self.artwork.setPixmap(
                _botanical_placeholder_pixmap(
                    self.artwork.width(), self.artwork.height()
                )
            )
            self.artwork.setAccessibleDescription(
                "Plant artwork is unavailable; a botanical fallback illustration is shown."
            )
            self.timeline.set_memories([])
            return
        self.name_heading.setText(plant.name)
        stage = format_status_label(plant.growth_stage)
        active = self.engine.state.active_plant_id == plant.plant_id
        self.meta_values["species"].setText(format_status_label(plant.species))
        self.meta_values["stage"].setText(stage)
        self.meta_values["planted"].setText(self._local_date(plant.planted_on))
        self.nurturing_status.setVisible(active)
        _populate_asset_preview(
            self.artwork,
            self.engine,
            plant.species,
            plant.growth_stage,
            size=104,
            fallback_text=format_status_label(plant.species),
        )
        memories = chronological_memories(plant.memories)
        self.timeline.set_memories([
            (self._local_date(memory.occurred_on), self._memory_text(memory, plant.name))
            for memory in memories
        ], just_beginning=story_is_just_beginning(memories))
        progress = growth_display(plant.growth_points)
        for index, stage_key in enumerate(GROWTH_STAGES):
            node, stage_preview = self.stage_nodes[stage_key]
            stage_state = (
                "complete" if index < progress.stage_index else
                "current" if index == progress.stage_index else
                "upcoming"
            )
            _populate_asset_preview(
                stage_preview,
                self.engine,
                plant.species,
                stage_key,
                size=56,
                fallback_text=format_status_label(stage_key),
                rare_unlocked=stage_state != "upcoming",
            )
            node.setProperty("storyStageState", stage_state)
            stage_description = (
                f"{format_status_label(stage_key)} stage, "
                f"{'completed' if stage_state == 'complete' else 'current' if stage_state == 'current' else 'upcoming'}"
            )
            node.setAccessibleName(stage_description)
            node.setToolTip(stage_description)
            style = node.style()
            if style is not None:
                style.unpolish(node)
                style.polish(node)
        if progress.fully_grown:
            self.up_next_text.setText(FULLY_GROWN_MESSAGE)
            self.choose_another.show()
            self.stage_progress.set_progress(
                "Rare stage", 1, 1, value_text="Fully grown"
            )
        else:
            self.choose_another.hide()
            next_stage = format_status_label(progress.next_stage or "next stage")
            answers = max(1, (progress.points_remaining + 9) // 10)
            self.up_next_text.setText(
                f"About {answers:,} Anki card {'answer' if answers == 1 else 'answers'} to {next_stage}"
            )
            self.stage_progress.set_progress(
                "Growth",
                progress.stage_points,
                max(1, progress.stage_goal),
                value_text=f"{progress.stage_points:,} / {progress.stage_goal:,} Growth",
            )

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
        species_name = format_status_label(species)
        item_name = seed_title(species_name)
        self.setWindowTitle(f"Choose {item_name}")
        self.apply_size_policy(DialogSizeClass.COMPACT_CONFIRMATION)
        self.setStyleSheet(_garden_dialog_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        heading.setSpacing(14)
        heading.addWidget(
            _asset_preview_label(
                engine,
                species,
                GROWTH_STAGES[0],
                size=96,
                property_name="nurseryArtwork",
            )
        )
        copy = QVBoxLayout()
        copy.setSpacing(6)
        title = QLabel(f"Choose {item_name}?")
        title.setProperty("dialogTitle", True)
        title.setWordWrap(True)
        body = QLabel(
            f"{COST_FREE}\nYou can collect additional species later through the Nursery."
        )
        body.setProperty("dialogSubtitle", True)
        body.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(body)
        heading.addLayout(copy, 1)
        layout.addLayout(heading)
        self.actions = QHBoxLayout()
        self.actions.addStretch(1)
        self.back_action = QPushButton("Go back")
        _set_button_variant(self.back_action, BUTTON_VARIANT_TERTIARY)
        self.back_action.clicked.connect(self.reject)
        self.choose_action = QPushButton("Choose")
        self.choose_action.setAccessibleName(f"Choose {item_name}")
        self.choose_action.setAccessibleDescription(
            f"Plant {item_name} as your first plant. {COST_FREE}."
        )
        _set_button_variant(self.choose_action, BUTTON_VARIANT_PRIMARY)
        self.choose_action.clicked.connect(self.accept)
        self.actions.addWidget(self.back_action)
        self.actions.addWidget(self.choose_action)
        layout.addLayout(self.actions)
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
            telemetry_target=self,
        )

    def resizeEvent(self, event: Any) -> None:
        margins = self.layout().contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "actions_responsive"):
            self.actions_responsive.evaluate(available)
        super().resizeEvent(event)


class NurseryDialog(DialogShell):
    """Artwork-led catalog for starters, collected plants, and garden spaces."""

    def __init__(self, parent: QWidget, engine: Any, storage: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.storage = storage
        self.setWindowTitle("Nursery")
        self.apply_size_policy(
            DialogSizeClass.CATALOG,
            preferred_width=840,
            preferred_height=640,
        )
        self.setStyleSheet(foundation_stylesheet("nursery") + """
            QWidget[gardenDialogShell='true'] { background:#241813; color:#f5ead7; }
            QFrame[nurseryHero='true'] { background:transparent; border:0; border-bottom:1px solid #604333; border-radius:0; }
            QFrame[nurseryFooter='true'] { background:#241813; border:0; border-top:1px solid #604333; }
            QFrame[nurseryResource='true'] { background:#34231c; border:1px solid #6f503b; border-radius:10px; }
            QFrame[nurseryPlant='true'] { background:#46332a; border:1px solid #71513c; border-radius:12px; }
            QFrame[nurseryPlant='true']:hover { background:#513a2e; border-color:#b88a52; }
            QFrame[nurseryPlant='true'][unaffordable='true'] { background:#2b201c; border-color:#574337; }
            QFrame[nurseryGrowing='true'] { background:#35271f; border:1px solid #7d5d43; border-left:3px solid #b88a52; border-radius:10px; }
            QFrame[spaceBed='true'] { background:#30231d; border:1px solid #654b39; border-radius:12px; }
            QFrame[spaceBed='true'][spaceState='unlocked'] { background:#39442d; border-color:#78815a; }
            QFrame[spaceBed='true'][spaceState='next'] { background:#4a3625; border:2px solid #d5ad70; }
            QLabel[spaceBedIcon='true'] { color:#d5ad70; font-size:26px; font-weight:800; }
            QLabel[nurseryEyebrow='true'] { color:#d5ad70; font-size:12px; font-weight:800; letter-spacing:1.2px; }
            QLabel[nurseryTitle='true'] { font-size:30px; font-weight:800; }
            QLabel[nurserySection='true'] { color:#f8e8cf; font-size:19px; font-weight:800; padding:11px 2px 1px 2px; }
            QLabel[nurserySectionNote='true'] { color:#bca991; font-size:13px; padding:0 2px 4px 2px; }
            QLabel[nurseryPlantName='true'] { color:#fff3da; font-size:19px; font-weight:800; }
            QLabel[nurseryMeta='true'] { color:#d6c4ac; font-size:14px; }
            QLabel[nurseryOwnership='true'] { color:#d5ad70; font-size:12px; font-weight:800; letter-spacing:.8px; }
            QLabel[nurseryStageName='true'] { color:#fff3da; font-size:16px; font-weight:800; }
            QLabel[nurseryStageCount='true'] { color:#cdbba5; font-size:13px; }
            QLabel[nurseryShortfall='true'] { color:#f0cf8d; font-size:13px; }
            QLabel[nurseryCoinLabel='true'] { color:#bca991; font-size:12px; font-weight:800; letter-spacing:.9px; }
            QLabel[nurseryCoins='true'] { color:#f1c979; font-size:29px; font-weight:800; }
            QLabel[nurseryArtwork='true'] {
                background:qradialgradient(cx:0.5,cy:0.58,radius:0.78,fx:0.5,fy:0.58,stop:0 #55402e,stop:0.62 #32231d,stop:1 #211713);
                border:1px solid #795b42;
                border-radius:12px;
                color:#d6c4ac;
                font-size:12px;
                padding:0;
            }
            QTabWidget::pane { border:1px solid #654936; border-radius:12px; background:#2f211b; top:-1px; }
            QTabBar::tab { min-height:44px; padding:0 12px; color:#d8c7b1; background:#2d201a; border:0; border-bottom:2px solid transparent; font-size:13px; font-weight:700; }
            QTabBar::tab:hover { color:#fff3da; background:#3d2a21; border-color:#846044; }
            QTabBar::tab:selected { color:#fff3da; background:#4d3528; border-color:#b88a52; }
            QPushButton[nurseryCarouselNav='true'] { padding:2px 4px; font-size:13px; font-weight:700; }
            QScrollBar:vertical { width:10px; margin:2px; background:#2f211b; }
            QScrollBar::handle:vertical { min-height:30px; border-radius:4px; background:#795b42; }
            QScrollBar::handle:vertical:hover { background:#9b7650; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(14)

        hero = QFrame()
        hero.setProperty("nurseryHero", True)
        self.hero_layout = QHBoxLayout(hero)
        self.hero_layout.setContentsMargins(24, 10, 24, 14)
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
        resource_layout = QVBoxLayout(self.coin_resource)
        resource_layout.setContentsMargins(14, 8, 14, 8)
        resource_layout.setSpacing(0)
        coin_label = QLabel("GARDEN COINS")
        coin_label.setProperty("nurseryCoinLabel", True)
        coin_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.coins = QLabel("")
        self.coins.setAccessibleName("Garden Coins balance")
        self.coins.setProperty("nurseryCoins", True)
        apply_tabular_numerals(self.coins)
        self.coins.setAlignment(Qt.AlignmentFlag.AlignRight)
        resource_layout.addWidget(coin_label)
        resource_layout.addWidget(self.coins)
        self.hero_layout.addWidget(self.coin_resource, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hero)

        self.catalog_tabs = QTabWidget()
        self.catalog_tabs.setDocumentMode(True)
        self.catalog_tabs.setAccessibleName("Nursery catalog sections")
        set_semantic_role(self.catalog_tabs.tabBar(), SemanticRole.TABS)
        self.catalog_tabs.tabBar().setExpanding(True)
        self.catalog_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName("Plants catalog")
        self.catalog = QWidget()
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
        self.upgrades_scroll.setAccessibleName("Garden Spaces catalog")
        self.upgrades_catalog = QWidget()
        self.upgrades_layout = QVBoxLayout(self.upgrades_catalog)
        self.upgrades_layout.setContentsMargins(6, 6, 6, 6)
        self.upgrades_layout.setSpacing(9)
        self.upgrades_scroll.setWidget(self.upgrades_catalog)
        _set_scroll_surface(
            self.upgrades_scroll,
            self.upgrades_catalog,
            "#2f211b",
        )
        self.catalog_tabs.addTab(self.upgrades_scroll, "Garden Spaces")

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

        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Nursery status")
        self.status.setProperty("liveRegion", "polite")
        self.status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.status)
        apply_tabular_numerals(self.status)
        self._status_generation = 0
        self.status.hide()
        root.addWidget(self.status)
        self.receipt_actions = QWidget()
        self.receipt_layout = QHBoxLayout(self.receipt_actions)
        self.receipt_layout.setContentsMargins(0, 0, 0, 0)
        self.receipt_layout.setSpacing(8)
        self.receipt_layout.addStretch(1)
        self.receipt_customize = QPushButton("Customize Garden")
        self.receipt_continue = QPushButton("Continue shopping")
        _set_button_variant(self.receipt_customize, BUTTON_VARIANT_PRIMARY)
        _set_button_variant(self.receipt_continue, BUTTON_VARIANT_SECONDARY)
        self.receipt_customize.clicked.connect(self._open_customize_from_nursery)
        self.receipt_continue.clicked.connect(self._dismiss_product_receipt)
        self.receipt_layout.addWidget(self.receipt_continue)
        self.receipt_layout.addWidget(self.receipt_customize)
        self.receipt_actions.hide()
        root.addWidget(self.receipt_actions)
        self.nursery_footer = QFrame()
        self.nursery_footer.setProperty("nurseryFooter", True)
        footer = QHBoxLayout(self.nursery_footer)
        footer.setContentsMargins(0, 10, 0, 0)
        self.bed_button = QPushButton("")
        self._bed_purchase_pending = False
        self._bed_button_restore_enabled = False
        self._catalog_transaction_pending = False
        _set_button_variant(self.bed_button, BUTTON_VARIANT_SECONDARY)
        self.bed_button.clicked.connect(self._unlock_bed)
        self.bed_affordability = QLabel("")
        self.bed_affordability.setWordWrap(True)
        self.bed_affordability.setProperty("nurseryShortfall", True)
        self.bed_affordability.setAccessibleName("Garden space affordability")
        self.bed_affordability.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(self.bed_affordability)
        apply_tabular_numerals(self.bed_affordability)
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        _set_button_variant(self.close_button, BUTTON_VARIANT_SECONDARY)
        self.close_button.clicked.connect(self.accept)
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
                floor=400,
            ),
            AdaptiveRegion.measured(
                "garden-coins",
                self.coin_resource,
                floor=200,
            ),
            layout=self.hero_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=14,
            telemetry_target=self,
        )
        self.receipt_responsive = AdaptiveRow.for_box_layout(
            "nursery.receipt-actions",
            (
                AdaptiveRegion.measured(
                    "continue-shopping",
                    self.receipt_continue,
                    floor=140,
                ),
                AdaptiveRegion.measured(
                    "customize-garden",
                    self.receipt_customize,
                    floor=140,
                ),
            ),
            layout=self.receipt_layout,
            wide_direction=QBoxLayout.Direction.LeftToRight,
            compact_direction=QBoxLayout.Direction.TopToBottom,
            spacing=8,
            telemetry_target=self.receipt_actions,
        )
        self.refresh()

    def resizeEvent(self, event: Any) -> None:
        margins = self.layout().contentsMargins()
        available = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "hero_responsive"):
            hero = self.hero_responsive.evaluate(available)
            receipt = self.receipt_responsive.evaluate(available)
            hero_compact = hero.mode == COMPACT_MODE
            self.coin_resource.setMaximumWidth(16777215 if hero_compact else 240)
            self.coin_resource.setSizePolicy(
                QSizePolicy.Policy.Expanding
                if hero_compact
                else QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
            self.setProperty("heroMode", hero.mode)
            self.setProperty("receiptMode", receipt.mode)
        super().resizeEvent(event)

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

    @staticmethod
    def _plant_description(species: str) -> str:
        return {
            "bonsai": "A quiet, sculptural evergreen with a calm silhouette.",
            "rose": "A classic flowering plant with warm layered petals.",
            "sunflower": "A bright, cheerful plant that turns toward the light.",
            "lavender": "A soft purple plant with a relaxed cottage-garden look.",
            "hydrangea": "A rounded flowering shrub with cloudlike blooms.",
            "peony": "A lush garden flower with full, delicate petals.",
            "foxglove": "A tall woodland flower with bell-shaped blooms.",
            "japanese_maple": "A graceful small tree with finely shaped leaves.",
            "wisteria": "A trailing flowering vine with cascading blossoms.",
            "dahlia": "A bold garden flower with precise geometric petals.",
        }.get(str(species), "A distinctive plant for your garden collection.")

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
            button.setProperty("nurseryCarouselNav", True)
            button.setFixedSize(84, BUTTON_MIN_HEIGHT)
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
        card = QFrame()
        card.setProperty("nurseryGrowing", True)
        card.setMaximumHeight(96)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(11)
        row.addWidget(self._plant_artwork(plant.species, plant.growth_stage, 64))
        copy = QVBoxLayout()
        copy.setSpacing(1)
        kicker = QLabel("NURTURED PLANT")
        kicker.setProperty("nurseryOwnership", True)
        title = QLabel(plant.name)
        title.setProperty("nurseryPlantName", True)
        progress = growth_display(plant.growth_points)
        stage = format_status_label(progress.stage)
        progress_text = (
            "Fully grown"
            if progress.fully_grown else
            f"{progress.stage_points:,} / {progress.stage_goal:,} Growth"
        )
        meta = QLabel(f"{stage} Stage\n{progress_text}")
        meta.setProperty("nurseryMeta", True)
        meta.setTextFormat(Qt.TextFormat.PlainText)
        apply_tabular_numerals(meta)
        copy.addWidget(kicker)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        action = QPushButton("View in garden")
        _set_button_variant(action, BUTTON_VARIANT_TERTIARY)
        action.setMinimumHeight(BUTTON_MIN_HEIGHT)
        action.setAccessibleName(f"View {plant.name} in the garden")
        action.setAccessibleDescription(
            f"Close the Nursery and open {plant.name}'s plant card."
        )
        action.clicked.connect(
            lambda _checked=False, plant_id=plant.plant_id:
            self._view_in_garden(plant_id)
        )
        row.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        card.setAccessibleDescription(
            f"Nurtured plant {plant.name}. {stage} Stage. {progress_text}."
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

    def _owned_card(self, plant: Any) -> QFrame:
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 8, 11, 8)
        row.setSpacing(10)
        row.addWidget(self._plant_artwork(plant.species, plant.growth_stage, 76))
        copy = QVBoxLayout()
        ownership = QLabel("IN YOUR COLLECTION")
        ownership.setProperty("nurseryOwnership", True)
        title = QLabel(plant.name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title.setProperty("nurseryPlantName", True)
        place = f"Space {plant.slot_index + 1}" if plant.planted else "Shelved"
        meta = QLabel(
            f"{format_status_label(plant.species)} — "
            f"{format_status_label(plant.growth_stage)} Stage\n{place}"
        )
        meta.setTextFormat(Qt.TextFormat.PlainText)
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        copy.addWidget(ownership)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        action = QPushButton("Shelve" if plant.planted else "Plant")
        _set_button_variant(action, BUTTON_VARIANT_SECONDARY)
        action.setAccessibleName(
            f"Shelve {plant.name}"
            if plant.planted else
            f"Plant {plant.name} in an available garden space"
        )
        action.setAccessibleDescription(
            f"{plant.name}, {format_status_label(plant.species)}, "
            f"{format_status_label(plant.growth_stage)} stage."
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
            lambda _checked=False, plant_id=plant.plant_id, planted=plant.planted:
            self._set_placement(plant_id, planted)
        )
        row.addWidget(action)
        action.setMinimumHeight(BUTTON_MIN_HEIGHT)
        return card

    def _available_card(self, species: str, starter_mode: bool) -> QFrame:
        if starter_mode:
            return self._starter_card(species)
        species_name = format_status_label(species)
        item_name = seed_title(species_name)
        price = int(self.engine.SPECIES_PRICES.get(species, 0))
        balance = int(self.storage.state.currency_balance)
        affordable, affordability = _affordability_status(price, balance)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(9)
        card_layout.addWidget(
            self._plant_artwork(species, GROWTH_STAGES[0], 112),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(item_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setProperty("nurseryPlantName", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(self._plant_description(species))
        description.setProperty("nurseryMeta", True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        ownership = QLabel("Not collected")
        ownership.setProperty("nurseryOwnership", True)
        ownership.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        card_layout.addWidget(description)
        card_layout.addWidget(ownership)
        stages = self._plant_stage_strip(species)
        stages.hide()
        card_layout.addWidget(stages)
        meta = QLabel(cost_label(price))
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        apply_tabular_numerals(meta)
        affordability_label = QLabel(
            _compact_affordability_status(price, balance, ready_text="Ready to unlock")
        )
        affordability_label.setProperty("nurseryShortfall", True)
        affordability_label.setWordWrap(True)
        apply_tabular_numerals(affordability_label)
        details = QPushButton("Details")
        details.setCheckable(True)
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)

        def toggle_stages(checked: bool) -> None:
            stages.setVisible(checked)
            details.setText("Hide details" if checked else "Details")

        details.toggled.connect(toggle_stages)
        action = QPushButton("Buy")
        _set_button_variant(action, BUTTON_VARIANT_PRIMARY)
        action.setAccessibleName(f"Buy {item_name} for {price:,} Garden Coins")
        action.setAccessibleDescription(
            f"{cost_label(price)}. {affordability} Add {item_name} to your plant collection."
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
            apply_explanatory_tooltip(
                card,
                f"{item_name} costs {price:,} Garden Coins. {affordability}",
            )
            card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            set_keyboard_focus_surface(card)
        action.clicked.connect(
            lambda _checked=False, selected=species: self._purchase_species(selected)
        )
        action.setMinimumHeight(BUTTON_MIN_HEIGHT)
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
        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(card)
        item_name = seed_title(species_name)
        card.setAccessibleName(f"{item_name} starter plant")
        card.setAccessibleDescription(
            f"{item_name}. {COST_FREE}. {self._plant_description(species)}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        layout.addWidget(
            self._plant_artwork(species, GROWTH_STAGES[0], 112),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(item_name)
        title.setProperty("nurseryPlantName", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        description = QLabel(self._plant_description(species))
        description.setProperty("nurseryMeta", True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        cost = QLabel(COST_FREE)
        cost.setProperty("nurseryOwnership", True)
        cost.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(cost)
        stages = self._plant_stage_strip(species)
        stages.hide()
        details = QPushButton("View stages")
        details.setCheckable(True)
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)

        def toggle_stages(checked: bool) -> None:
            stages.setVisible(checked)
            details.setText("Hide stages" if checked else "View stages")
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
        choose.clicked.connect(
            lambda _checked=False, selected=species: self._choose_starter(selected)
        )
        actions.addWidget(details)
        actions.addStretch(1)
        actions.addWidget(choose)
        layout.addLayout(actions)
        return card

    def _item_artwork(self, key: str, accessible_name: str, size: int = 96) -> QLabel:
        label = QLabel()
        label.setFixedSize(size, size)
        label.setProperty("nurseryArtwork", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(accessible_name)
        normalized_key = str(key or "").strip()
        logical_asset_id = (
            normalized_key if normalized_key.startswith("ui_")
            else f"ui_{normalized_key}"
        )
        asset = None
        resolver = getattr(self.engine, "resolve_item_asset", None)
        try:
            asset = resolver(normalized_key) if callable(resolver) else None
        except Exception:
            logger.exception(
                "Anki Garden: item artwork resolution failed for %s (%s)",
                normalized_key,
                logical_asset_id,
            )
        path = getattr(asset, "path", None) if asset is not None else None
        if path is not None:
            try:
                path = Path(path)
            except TypeError:
                path = None
        pixmap = QPixmap(str(path)) if path is not None and path.is_file() else QPixmap()
        if pixmap.isNull():
            label.setText("")
            label.setPixmap(_botanical_placeholder_pixmap(size, size))
            label.setAccessibleDescription(
                f"Artwork unavailable for {accessible_name}; a botanical fallback illustration is shown."
            )
        else:
            label.setPixmap(pixmap.scaled(
                size - 12,
                size - 12,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        return label

    def _supplement_card(self, tier: str) -> QFrame:
        spec = self.engine.FERTILIZERS[tier]
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._item_artwork(
            f"fertilizer_{tier}", f"{spec.name} bag preview", 56
        ))
        copy = QVBoxLayout()
        title = QLabel(spec.name)
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        duration_hours = max(1, spec.duration_seconds // 3600)
        meta = QLabel(
            f"Effect: +{spec.growth_per_answer} Growth per Anki card answer\n"
            f"Duration: {duration_hours} {'hour' if duration_hours == 1 else 'hours'}  ·  "
            f"{cost_label(spec.price)}"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        active = self.engine.active_plant()
        affordable = self.storage.state.currency_balance >= spec.price
        action = QPushButton("Apply")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if affordable and active is not None else BUTTON_VARIANT_SECONDARY,
        )
        shortfall = max(0, int(spec.price) - int(self.storage.state.currency_balance))
        reason = (
            f"Use {spec.name} on {active.name}."
            if active is not None and affordable else
            f"Need {shortfall:,} more Garden Coins."
            if active is not None else
            "Choose an unfinished planted plant to nurture first."
        )
        action.setAccessibleName(
            f"Apply {spec.name} for {spec.price:,} Garden Coins"
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
        row.addWidget(action)
        if active is not None and not affordable:
            helper = QLabel(f"Need {shortfall:,} more coins")
            helper.setProperty("nurseryShortfall", True)
            helper.setWordWrap(True)
            apply_tabular_numerals(helper)
            copy.addWidget(helper)
        return card

    def _booster_card(self) -> QFrame:
        count = max(0, int(self.storage.state.consumables.get("booster_potion", 0)))
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._item_artwork(
            "booster_potion", "Booster Potion preview", 56
        ))
        copy = QVBoxLayout()
        title = QLabel(f"Booster Potion — {count} owned")
        title.setStyleSheet("font-weight:700;")
        apply_tabular_numerals(title)
        meta = QLabel(
            "+5 Growth per Anki card answer for 2 hours. A rare study gift; not sold in the Nursery."
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
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
        row.addWidget(action)
        return card

    def _growth_charge_card(self, spec: GrowthChargeSpec) -> QFrame:
        count = max(0, int(self.storage.state.consumables.get(spec.charge_id, 0)))
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._item_artwork(
            spec.charge_id, f"{spec.name} preview", 56
        ))
        copy = QVBoxLayout()
        title = QLabel(f"{spec.name} — {count} owned")
        title.setStyleSheet("font-weight:700;")
        apply_tabular_numerals(title)
        meta = QLabel(
            f"Adds up to {spec.growth:,} Growth to the nurtured plant, capped at Rare.\n"
            + (
                cost_label(spec.price)
                if spec.price is not None
                else "Earn-only; never sold."
            )
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        active = self.engine.active_plant()
        if count > 0:
            action = QPushButton("Use on nurtured plant")
            enabled = active is not None
            action.setAccessibleDescription(
                f"Use one {spec.name} on {active.name}."
                if enabled else
                "Nurture an unfinished planted plant before using this item."
            )
            action.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id:
                self._use_growth_charge(charge_id)
            )
        elif spec.price is not None:
            affordable = self.storage.state.currency_balance >= spec.price
            action = QPushButton("Buy")
            enabled = affordable
            action.setAccessibleName(
                f"Buy {spec.name} for {spec.price:,} Garden Coins"
            )
            action.setAccessibleDescription(
                f"{cost_label(spec.price)}. Adds up to {spec.growth:,} Growth to the nurtured plant. "
                + (
                    "Affordable with the current Garden Coin balance."
                    if affordable else
                    f"Need {spec.price - self.storage.state.currency_balance:,} more Garden Coins."
                )
            )
            action.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id:
                self._purchase_growth_charge(charge_id)
            )
        else:
            action = QPushButton("Not collected")
            enabled = False
            action.setAccessibleDescription(spec.how_to_earn)
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
        row.addWidget(action)
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
        label.setPixmap(_environment_preview_pixmap(
            self.engine,
            item,
            width - 10,
            height - 10,
        ))
        return label

    def _environment_shop_card(self, item: CatalogItem) -> QFrame:
        owned = self.engine.owns_environment(item.kind, item.item_id)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._environment_artwork(item, width=240, height=135),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(f"{item.name} — {item.rarity}")
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        category = QLabel(format_status_label(item.kind))
        category.setProperty("nurseryOwnership", True)
        meta = QLabel(
            cost_label(item.price)
            if item.price is not None else
            "Included with every garden"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        apply_tabular_numerals(meta)
        layout.addWidget(title)
        layout.addWidget(category)
        layout.addWidget(meta)
        actions = QHBoxLayout()
        details = QPushButton("Preview")
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)
        details.clicked.connect(
            lambda _checked=False, selected=item: self._preview_environment_item(selected)
        )
        actions.addWidget(details)
        actions.addStretch(1)
        affordable = bool(
            item.price is not None
            and self.storage.state.currency_balance >= item.price
        )
        affordability = (
            "Affordable with the current Garden Coin balance."
            if affordable else
            f"Need {int(item.price or 0) - self.storage.state.currency_balance:,} more Garden Coins."
        )
        action = QPushButton(
            "Customize" if owned else "Buy"
        )
        action.setAccessibleName(
            f"Open Customize Garden for {item.name}"
            if owned else
            f"Buy {item.name} for {int(item.price or 0):,} Garden Coins"
        )
        _set_button_variant(
            action, BUTTON_VARIANT_PRIMARY if owned or affordable else BUTTON_VARIANT_SECONDARY
        )
        action.setAccessibleDescription(
            f"Open Customize Garden to preview or equip {item.name}."
            if owned else
            f"{cost_label(int(item.price or 0))}. {affordability} "
            f"Unlocks {item.name} for Customize Garden."
        )
        set_control_enabled(
            action,
            owned or affordable,
            disabled_reason=(
                f"{item.name} is not affordable yet. {affordability}"
            ),
            enabled_description=action.accessibleDescription(),
        )
        if owned:
            action.clicked.connect(self._open_customize_from_nursery)
        else:
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
        self.environment_feature_title.setText(item.name)
        self.environment_feature_meta.setText(
            f"{format_status_label(item.kind)} · {item.rarity}\n{item.effect}"
        )

    def _open_customize_from_nursery(self) -> None:
        parent = self.parentWidget()
        self.accept()
        opener = getattr(parent, "_open_customize", None)
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
        title = QLabel(f"Garden space {index + 1}")
        title.setStyleSheet("font-weight:700;")
        apply_tabular_numerals(title)
        status = QLabel(
            "Unlocked permanently"
            if unlocked else
            cost_label(price)
            if next_space and price is not None else
            "Unlock the previous garden space first"
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
            self.bed_button.clicked.connect(self._unlock_bed)
            self.bed_button.setText("Unlock")
            self.bed_button.setAccessibleName(
                f"Unlock garden space {index + 1} for {price:,} Garden Coins"
            )
            set_control_enabled(
                self.bed_button,
                affordable and not self._bed_purchase_pending,
                disabled_reason=(
                    "The Garden space purchase is still being saved."
                    if self._bed_purchase_pending
                    else f"Need {price - state.currency_balance:,} more Garden Coins."
                ),
                enabled_description=(
                    f"Unlock garden space {index + 1} for {price:,} Garden Coins."
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
        summary = QLabel(f"{unlocked_count} of 6 garden spaces unlocked")
        summary.setProperty("nurserySection", True)
        summary.setAccessibleName(summary.text())
        layout.addWidget(summary)
        beds = QHBoxLayout()
        beds.setSpacing(8)
        for index in range(6):
            unlocked = index < unlocked_count
            next_bed = index == unlocked_count and index < 6
            cell = QFrame()
            cell.setProperty("spaceBed", True)
            cell.setProperty(
                "spaceState", "unlocked" if unlocked else "next" if next_bed else "future"
            )
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(7, 8, 7, 8)
            cell_layout.setSpacing(3)
            icon = QLabel("▰" if unlocked else "+" if next_bed else "▱")
            icon.setProperty("spaceBedIcon", True)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number = QLabel(f"Bed {index + 1}")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status = QLabel("Owned" if unlocked else "Next" if next_bed else "Locked")
            status.setProperty("nurseryMeta", True)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(icon)
            cell_layout.addWidget(number)
            cell_layout.addWidget(status)
            cell.setAccessibleName(
                f"Garden bed {index + 1}, {'unlocked' if unlocked else 'next expansion' if next_bed else 'locked'}"
            )
            beds.addWidget(cell, 1)
        layout.addLayout(beds)
        next_index = unlocked_count
        price = self.engine.BED_PRICES.get(next_index)
        expansion = SectionCard()
        expansion_layout = QHBoxLayout(expansion)
        expansion_layout.setContentsMargins(14, 12, 14, 12)
        expansion_layout.setSpacing(12)
        copy = QVBoxLayout()
        title = QLabel(
            "Maximum garden capacity reached"
            if price is None else
            "Unlock one additional garden bed"
        )
        title.setProperty("nurseryPlantName", True)
        details = QLabel(
            "All six garden beds are available."
            if price is None else
            "Adds one planting space."
        )
        details.setProperty("nurseryMeta", True)
        details.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(details)
        if price is not None:
            price_label = QLabel(cost_label(price))
            price_label.setProperty("nurseryMeta", True)
            copy.addWidget(price_label)
        expansion_layout.addLayout(copy, 1)
        if price is not None:
            affordable = int(state.currency_balance) >= int(price)
            self.bed_button = QPushButton("Unlock")
            _set_button_variant(
                self.bed_button,
                BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
            )
            self.bed_button.setAccessibleDescription(
                f"{cost_label(price)}. Unlocks garden space {next_index + 1} permanently. "
                + (
                    "Affordable with the current Garden Coin balance."
                    if affordable else
                    f"Need {price - int(state.currency_balance):,} more Garden Coins."
                )
            )
            self.bed_button.setAccessibleName(
                f"Unlock garden space {next_index + 1} for {price:,} Garden Coins"
            )
            set_control_enabled(
                self.bed_button,
                affordable and not self._bed_purchase_pending,
                disabled_reason=(
                    "The Garden space purchase is still being saved."
                    if self._bed_purchase_pending
                    else f"Need {price - int(state.currency_balance):,} more Garden Coins."
                ),
                enabled_description=self.bed_button.accessibleDescription(),
            )
            self.bed_button.clicked.connect(self._unlock_bed)
            expansion_layout.addWidget(self.bed_button)
            if not affordable:
                shortfall = QLabel(
                    f"Need {int(price) - int(state.currency_balance):,} more coins"
                )
                shortfall.setProperty("nurseryShortfall", True)
                shortfall.setWordWrap(True)
                copy.addWidget(shortfall)
        layout.addWidget(expansion)
        layout.addStretch(1)
        return host

    def _purchase_fertilizer(self, tier: str) -> None:
        if not self._begin_catalog_transaction():
            return
        committed = False
        try:
            plant = self.engine.active_plant()
            if plant is None:
                self._show_result(False, "Choose an unfinished planted plant to nurture first.")
                return
            current = getattr(plant, "fertilizer", None)
            replace = bool(current and current.active(time.time()) and current.tier != tier)
            if replace:
                current_spec = self.engine.FERTILIZERS.get(str(current.tier).lower())
                new_spec = self.engine.FERTILIZERS.get(str(tier).lower())
                if new_spec is None:
                    self._show_result(False, "Choose a valid Fertilizer tier.")
                    return
                remaining_seconds = max(0, int(float(current.expires_at) - time.time()))
                hours, remainder = divmod(remaining_seconds, 3600)
                minutes = max(1, remainder // 60) if hours == 0 else remainder // 60
                remaining_time = f"{hours}h {minutes}m" if hours else _minute_count(minutes)
                confirmation = FertilizerReplacementDialog(
                    self,
                    current_name=str(getattr(current_spec, "name", current.tier)),
                    current_effect=f"+{int(current.growth_per_answer)} Growth per Anki card answer",
                    remaining_time=remaining_time,
                    new_name=new_spec.name,
                    new_effect=(
                        f"+{new_spec.growth_per_answer} Growth per Anki card answer for "
                        f"{max(1, new_spec.duration_seconds // 3600)} hours"
                    ),
                    cost=new_spec.price,
                )
                if confirmation.exec() != QDialog.DialogCode.Accepted:
                    return
            ok, message = self.engine.purchase_fertilizer(
                plant.plant_id, tier, replace_active=replace
            )
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "Fertilizer purchase", committed=committed
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

    def _purchase_growth_charge(self, charge_id: str) -> None:
        if not self._begin_catalog_transaction():
            return
        committed = False
        try:
            ok, message = self.engine.purchase_growth_charge(charge_id)
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "Growth Charge purchase", committed=committed
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
        committed = False
        try:
            catalog = WEATHER_CATALOG if str(kind) == "weather" else SCENERY_CATALOG
            product = catalog.get(str(item_id))
            if product is None:
                self._show_result(False, "That Nursery product is no longer available.")
                return
            ok, message = self.engine.purchase_environment(kind, item_id)
            committed = bool(ok)
            if ok:
                self._refresh_parent()
                self.refresh()
                # Refresh rebuilds the catalog, so explicitly restore the receipt's
                # product instead of reverting the feature panel to its first item.
                self._preview_environment_item(product)
                self._show_product_receipt(product, message)
            else:
                self._show_result(False, message)
        except Exception:
            self._show_catalog_transaction_exception(
                "Weather or Scenery purchase", committed=committed
            )
        finally:
            self._schedule_catalog_transaction_release()

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
        except Exception:
            logger.exception("Anki Garden: Nursery transaction failure could not be displayed")

    def _dismiss_product_receipt(self) -> None:
        self._status_generation += 1
        self.receipt_actions.hide()
        self.status.hide()
        self.catalog_tabs.setFocus()

    def _show_product_receipt(self, product: CatalogItem, message: str) -> None:
        self._status_generation += 1
        cost = max(0, int(product.price or 0))
        receipt = (
            f"{product.name} unlocked\n"
            f"{cost_label(cost)}\n"
            "Owned · Ready in Customize Garden"
        )
        self.status.setText(receipt)
        self.status.setAccessibleDescription(
            f"Purchase complete. {receipt.replace(chr(10), '. ')}"
        )
        self.status.setStyleSheet(
            "color:#baf3c6; background:#1d4931; padding:9px 11px; border-radius:7px;"
        )
        self.status.show()
        self.status.setFocus()
        self.status.setToolTip(_learner_text(message))
        self.receipt_actions.show()
        self.accessibility_announcer.announce(
            self.status.accessibleDescription(),
            target=self.status,
        )

    def _sync_catalog_intro(self, index: int) -> None:
        if bool(getattr(self, "_starter_mode", False)):
            self.heading.setText(NURSERY_STARTER_TITLE)
            text = NURSERY_STARTER_RATIONALE
        else:
            self.heading.setText({
                0: "Build your collection",
                1: "Boost plant growth",
                2: "Expand your garden",
                3: "Change the atmosphere",
            }.get(int(index), "Nursery"))
            text = {
                0: f"{getattr(self, '_catalog_summary', '')}.",
                1: "Choose a timed or single-use boost for your nurtured plant.",
                2: "Make room for a larger plant collection.",
                3: "Collect a new look for the garden.",
            }.get(int(index), getattr(self, "_catalog_summary", ""))
        self.intro.setText(text)
        self.intro.setAccessibleDescription(text)

    def refresh(self) -> None:
        self._clear_catalog()
        self._clear_section(self.supplements_layout)
        self._clear_section(self.upgrades_layout)
        self._clear_section(self.environment_layout)
        state = self.storage.state
        starter_mode = not bool(getattr(state, "starter_selection_complete", True))
        for index in (1, 2, 3):
            self.catalog_tabs.setTabEnabled(index, not starter_mode)
            self.catalog_tabs.tabBar().setTabVisible(index, not starter_mode)
        self.starter_tab_note.hide()
        self.coin_resource.setVisible(not starter_mode)
        self.close_button.setText("Back to garden" if starter_mode else "Close")
        self.catalog_tabs.setAccessibleDescription(
            DISABLED_STARTER_TABS if starter_mode else "All Nursery sections are available."
        )
        if starter_mode:
            self.catalog_tabs.setCurrentIndex(0)
        summary = self.engine.catalog_summary()
        available = list(summary.get("available_species", []))
        owned_count = int(summary.get("owned_count", len(state.plants)))
        available_count = int(summary.get("available_count", len(available)))
        catalog_summary = (
            f"{owned_count:,} of {max(owned_count, owned_count + available_count):,} "
            f"{'plant' if max(owned_count, owned_count + available_count) == 1 else 'plants'} collected"
        )
        self.coins.setText(f"{state.currency_balance:,}")
        self.coins.setAccessibleDescription(
            f"{state.currency_balance:,} Garden Coins available"
        )
        self.heading.setText(NURSERY_STARTER_TITLE if starter_mode else "Build your collection")
        intro_text = (
            NURSERY_STARTER_RATIONALE
            if starter_mode else
            catalog_summary
        )
        self.intro.setText(intro_text)
        self.intro.setAccessibleDescription(intro_text)
        self.starter_count.setVisible(starter_mode)
        self.starter_count.setText(NURSERY_STARTER_COUNT)
        self.starter_count.setAccessibleDescription(NURSERY_STARTER_COUNT)
        self._starter_mode = starter_mode
        self._catalog_summary = catalog_summary
        self._sync_catalog_intro(self.catalog_tabs.currentIndex())
        active = self.engine.active_plant()
        if active is not None and not starter_mode:
            self.catalog_layout.addWidget(self._currently_growing_strip(active))
        collection_plants = [
            plant for plant in state.plants
            if active is None or plant.plant_id != active.plant_id
        ]
        if collection_plants and not starter_mode:
            self._section_label(
                "Your collection",
                "Collected plants stay with you and can be returned to the garden whenever space is available.",
            )
            for plant in sorted(collection_plants, key=lambda item: (item.slot_index is None, item.name.lower())):
                self.catalog_layout.addWidget(self._owned_card(plant))
        self._section_label(
            "Starter plants" if starter_mode else "Botanical catalog",
            "" if starter_mode else
            "Preview every growth stage before adding a new species to your collection.",
        )
        if available:
            available_grid_host = ResponsiveTileGrid(breakpoint=600)
            for species in available:
                available_grid_host.add_tile(
                    self._available_card(species, starter_mode)
                )
            self.catalog_layout.addWidget(available_grid_host)
        else:
            empty = QLabel(
                "The Nursery is stocking new plants. More will appear when their complete artwork is ready."
                if starter_mode else "You have collected every plant currently available."
            )
            empty.setWordWrap(True)
            empty.setProperty("nurseryMeta", True)
            self.catalog_layout.addWidget(empty)
        self.catalog_layout.addStretch(1)
        if not starter_mode:
            fertilizer_heading = QLabel("Fertilizer")
            fertilizer_heading.setProperty("nurserySection", True)
            self.supplements_layout.addWidget(fertilizer_heading)
            supplement_intro = QLabel(
                "Timed Fertilizer replaces any active Fertilizer. Boosters and Growth Charges are used once."
            )
            supplement_intro.setWordWrap(True)
            supplement_intro.setProperty("nurseryMeta", True)
            self.supplements_layout.addWidget(supplement_intro)
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

            spaces_heading = QLabel("Garden spaces")
            spaces_heading.setProperty("nurserySection", True)
            self.upgrades_layout.addWidget(spaces_heading)
            upgrade_intro = QLabel(
                "Unlocks follow the order shown below."
            )
            upgrade_intro.setWordWrap(True)
            upgrade_intro.setProperty("nurseryMeta", True)
            self.upgrades_layout.addWidget(upgrade_intro)
            self.upgrades_layout.addWidget(self._space_progression())

            atmosphere_heading = QLabel("Weather and Scenery")
            atmosphere_heading.setProperty("nurserySection", True)
            self.environment_layout.addWidget(atmosphere_heading)
            environment_intro = QLabel(
                "Preview before buying; equip owned items in Customize Garden."
            )
            environment_intro.setWordWrap(True)
            environment_intro.setProperty("nurseryMeta", True)
            self.environment_layout.addWidget(environment_intro)
            feature = QFrame()
            feature.setProperty("nurseryPlant", True)
            feature_layout = QHBoxLayout(feature)
            feature_layout.setContentsMargins(12, 11, 12, 11)
            self.environment_feature_art = QLabel("◇")
            self.environment_feature_art.setFixedSize(360, 202)
            self.environment_feature_art.setProperty("nurseryArtwork", True)
            self.environment_feature_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            feature_copy = QVBoxLayout()
            self.environment_feature_title = QLabel("Select an item to preview")
            self.environment_feature_title.setProperty("nurseryPlantName", True)
            self.environment_feature_meta = QLabel(
                "Compare Weather and Scenery artwork before purchasing."
            )
            self.environment_feature_meta.setProperty("nurseryMeta", True)
            self.environment_feature_meta.setWordWrap(True)
            feature_copy.addWidget(self.environment_feature_title)
            feature_copy.addWidget(self.environment_feature_meta)
            feature_copy.addStretch(1)
            feature_layout.addWidget(self.environment_feature_art)
            feature_layout.addLayout(feature_copy, 1)
            self.environment_layout.addWidget(feature)
            for heading, catalog in (
                ("Weather", WEATHER_CATALOG),
                ("Scenery", SCENERY_CATALOG),
            ):
                label = QLabel(heading)
                label.setProperty("nurserySection", True)
                self.environment_layout.addWidget(label)
                grid = ResponsiveTileGrid(breakpoint=620)
                first_item: CatalogItem | None = None
                for item in catalog.values():
                    if item.acquisition in {"free", "purchase"}:
                        first_item = first_item or item
                        grid.add_tile(self._environment_shop_card(item))
                self.environment_layout.addWidget(grid)
                if self.environment_feature_title.text() == "Select an item to preview" and first_item is not None:
                    self._preview_environment_item(first_item)
            self.environment_layout.addStretch(1)

    def _show_result(self, ok: bool, message: str) -> None:
        self._status_generation += 1
        generation = self._status_generation
        message = _learner_text(message)
        self.status.setText(message)
        self.status.setStyleSheet(
            "color:#baf3c6; background:#1d4931; padding:7px 9px; border-radius:7px;"
            if ok else
            "color:#ffd0d0; background:#582f34; padding:7px 9px; border-radius:7px;"
        )
        self.status.setAccessibleDescription(message)
        self.status.show()
        announcer = getattr(self, "accessibility_announcer", None)
        if announcer is not None:
            announcer.announce(
                message,
                priority=(
                    AnnouncementPriority.POLITE
                    if ok
                    else AnnouncementPriority.ASSERTIVE
                ),
                target=self.status,
            )
        if not ok:
            self.receipt_actions.hide()
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
        confirmation = StarterConfirmationDialog(self, self.engine, species)
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        ok, message, plant = self.engine.choose_starter(species)
        self._show_result(ok, message)
        if ok:
            # The persisted state now authorizes every normal Nursery tab.
            # Refresh before closing so the dialog never retains stale
            # starter-mode controls for callers that keep the instance alive.
            self.refresh()
            parent = self.parent()
            self._refresh_parent()
            if parent is not None and hasattr(parent, "_on_starter_selected"):
                parent._on_starter_selected(plant, message)
            self.accept()

    def _purchase_species(self, species: str) -> None:
        if not self._begin_catalog_transaction():
            return
        committed = False
        try:
            ok, message, _plant = self.engine.purchase_species(species)
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "plant purchase", committed=committed
            )
        finally:
            self._schedule_catalog_transaction_release()

    def _unlock_bed(self) -> None:
        if self._bed_purchase_pending or not self._begin_catalog_transaction():
            return
        self._bed_purchase_pending = True
        committed = False
        try:
            is_enabled = getattr(self.bed_button, "isEnabled", None)
            self._bed_button_restore_enabled = (
                bool(is_enabled()) if callable(is_enabled) else True
            )
            set_control_enabled(
                self.bed_button,
                False,
                disabled_reason="The Garden space purchase is being saved.",
            )
            ok, message = self.engine.purchase_next_bed()
            committed = bool(ok)
            self._show_result(ok, message)
            if ok:
                self._refresh_parent()
                self.refresh()
        except Exception:
            self._show_catalog_transaction_exception(
                "garden-space purchase", committed=committed
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
                        "The Garden space action is unavailable until the Nursery refreshes."
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
                    else "No additional Garden space is currently affordable."
                ),
                enabled_description="Unlock the next Garden space.",
            )
        except RuntimeError:
            return

    def _set_placement(self, plant_id: str, planted: bool) -> None:
        if planted:
            ok, message = self.engine.move_to_collection(plant_id)
        else:
            ok, message = self.engine.plant_from_collection(plant_id)
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
        self.setMaximumWidth(330)
        self.plant_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
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
        self.nurtured_badge = QLabel("Nurtured")
        self.nurtured_badge.setProperty("nurturedBadge", True)
        self.nurtured_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nurtured_badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.nurtured_badge.setAccessibleDescription(
            "Anki card answers add Growth to this plant."
        )
        self.nurtured_badge.hide()
        self.growth_section = QLabel("")
        self.growth_section.setProperty("plantCardSection", True)
        self.stage_progress = LabeledProgress("Selected plant growth")
        self.stage_progress.label.setProperty("plantProgressLabel", True)
        self.stage_progress.value_label.setProperty("plantGrowthValue", True)
        self.growth_summary = QLabel("")
        self.growth_remaining = QLabel("")
        self.fertilizer_summary = QLabel("")
        self.booster_summary = QLabel("")
        for label in (
            self.growth_summary,
            self.growth_remaining,
            self.fertilizer_summary,
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
        self.guidance_step = QLabel("STEP 2 OF 2")
        self.guidance_step.setProperty("plantGuidanceStep", True)
        self.guidance_text = QLabel(GARDEN_NURTURE_BODY)
        self.guidance_text.setWordWrap(True)
        self.guidance_text.setProperty("plantGuidanceText", True)
        guidance_layout.addWidget(self.guidance_step)
        guidance_layout.addWidget(self.guidance_text)
        self.guidance.hide()
        heading_row = QHBoxLayout()
        heading_row.setSpacing(8)
        heading_row.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(4)
        heading_copy.addWidget(self.heading)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        badge_row.addWidget(self.identity)
        badge_row.addWidget(self.nurtured_badge)
        badge_row.addStretch(1)
        heading_copy.addLayout(badge_row)
        heading_row.addLayout(heading_copy, 1)
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        self.close_btn.setAccessibleName("Close selected plant details")
        self.close_btn.setToolTip("Close selected plant details")
        _set_button_variant(self.close_btn, BUTTON_VARIANT_TERTIARY)
        self.close_btn.clicked.connect(self.dismissRequested.emit)
        heading_row.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading_row)
        layout.addWidget(self.stage_progress)
        layout.addWidget(self.growth_summary)
        layout.addWidget(self.growth_remaining)
        layout.addWidget(self.fertilizer_summary)
        layout.addWidget(self.booster_summary)
        layout.addWidget(self.status_row)
        layout.addWidget(self.guidance)
        layout.addWidget(self.action_hint)
        self.action_hint.hide()

        self.nurture = QPushButton("Nurture")
        self.nurture.setCheckable(True)
        self.fertilize = QPushButton("Fertilize")
        self.move = QPushButton("Move")
        self.story = QPushButton("Story")
        self.choose_another = QPushButton(FULLY_GROWN_ACTION)
        _set_button_variant(self.choose_another, BUTTON_VARIANT_PRIMARY)
        self.choose_another.setAccessibleDescription(FULLY_GROWN_MESSAGE)
        self.choose_another.clicked.connect(self.chooseAnother.emit)
        self.choose_another.hide()
        for button in (self.nurture, self.fertilize):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
        for button in (self.move, self.story):
            _set_button_variant(button, BUTTON_VARIANT_TERTIARY)
        apply_explanatory_tooltip(self.nurture, ACTIVE_PLANT_EXPLANATION)
        apply_explanatory_tooltip(self.fertilize, FERTILIZER_EXPLANATION)
        apply_explanatory_tooltip(self.move, "Move this plant to another highlighted garden space.")
        apply_explanatory_tooltip(self.story, "View this plant’s name, age, and growth history.")
        self.actions = QGridLayout()
        self.actions.setHorizontalSpacing(8)
        self.actions.setVerticalSpacing(8)
        layout.addLayout(self.actions)
        self._active_state = False
        self._fully_grown_state = False
        self._docked_actions = False
        self._layout_actions(active=False)
        for button in (self.nurture, self.fertilize, self.move, self.story):
            button.setMinimumHeight(PLANT_ACTION_MIN_HEIGHT)
        self.choose_another.setMinimumHeight(PLANT_ACTION_MIN_HEIGHT)
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
            self.move,
            self.story,
            self.choose_another,
        ):
            self.actions.removeWidget(button)
        if self._docked_actions:
            visible_actions = (
                (self.choose_another, self.move, self.story)
                if fully_grown else
                (self.fertilize, self.move, self.story)
                if active else
                (self.nurture, self.fertilize, self.move, self.story)
            )
            for column, button in enumerate(visible_actions):
                self.actions.addWidget(button, 0, column)
                self.actions.setColumnStretch(column, 1)
            return
        if fully_grown:
            self.actions.addWidget(self.choose_another, 0, 0, 1, 2)
            self.actions.addWidget(self.move, 1, 0)
            self.actions.addWidget(self.story, 1, 1)
            return
        if active:
            self.actions.addWidget(self.fertilize, 0, 0, 1, 2)
        else:
            self.actions.addWidget(self.nurture, 0, 0)
            self.actions.addWidget(self.fertilize, 0, 1)
        self.actions.addWidget(self.move, 1, 0)
        self.actions.addWidget(self.story, 1, 1)
        self.actions.addWidget(self.choose_another, 2, 0, 1, 2)

    def set_docked_mode(self, docked: bool) -> None:
        docked = bool(docked)
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
        self.heading.setText(name)
        self.heading.setToolTip(name)
        self.identity.setText(stage)
        asset = plant.get("asset")
        path = asset.get("path") if isinstance(asset, dict) else asset
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            self.artwork.setText("")
            self.artwork.setPixmap(
                _botanical_placeholder_pixmap(
                    self.artwork.width(),
                    self.artwork.height(),
                    stage=str(plant.get("stage") or ""),
                )
            )
            self.artwork.setAccessibleDescription(
                f"Artwork unavailable for {name}; a botanical fallback is shown."
            )
        else:
            self.artwork.setText("")
            self.artwork.setPixmap(
                pixmap.scaled(
                    self.artwork.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.artwork.setAccessibleDescription(f"Artwork for {name}.")
        growth_points = max(0, int(plant.get("growth_points", 0) or 0))
        if bool(plant.get("fully_grown")):
            self.stage_progress.set_progress(
                "Plant Growth",
                1,
                1,
                value_text=f"{growth_points:,} Growth",
            )
            self.growth_summary.hide()
            self.growth_remaining.hide()
        else:
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            next_stage = format_status_label(plant.get("next_stage") or "the next stage")
            self.stage_progress.set_progress(
                f"Progress to {next_stage}",
                stage_points,
                stage_goal,
                value_text=f"{stage_points:,} / {stage_goal:,} Growth",
            )
            self.stage_progress.value_label.show()
            self.growth_summary.show()
            remaining = max(0, int(plant.get("points_remaining", 0) or 0))
            reviews_remaining = max(0, int(plant.get("reviews_remaining", 0) or 0))
            self.growth_summary.setText(
                f"About {_card_answer_count(reviews_remaining)} "
                f"to {next_stage}"
            )
            # The progress value already communicates the remaining Growth.
            # Keep one short forecast below it instead of repeating the same
            # number in three different phrasings.
            self.growth_remaining.hide()
            self.growth_summary.setAccessibleDescription(
                f"{remaining:,} Growth remaining. "
                f"About {_card_answer_count(reviews_remaining)} before bonuses."
            )
        fertilizer_growth = max(0, int(plant.get("fertilizer_growth", 0) or 0))
        fertilizer_text = str(plant.get("fertilizer_text") or "No active Fertilizer")
        self.fertilizer_summary.setText(
            f"Fertilizer — {fertilizer_text}" if fertilizer_growth else "Fertilizer — None active"
        )
        self.fertilizer_summary.setVisible(fertilizer_growth > 0)
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
        self.nurtured_badge.setText("Fully grown" if fully_grown else "Nurtured")
        self.nurtured_badge.setVisible(active or fully_grown)
        set_control_enabled(
            self.fertilize,
            not fully_grown,
            disabled_reason="This plant is fully grown and cannot use Fertilizer.",
            enabled_description="Choose Fertilizer for this plant.",
        )
        self.fertilize.setVisible(not fully_grown)
        self.fertilize.setText("Fertilize")
        _set_button_variant(
            self.fertilize,
            BUTTON_VARIANT_PRIMARY if active and not fully_grown else BUTTON_VARIANT_SECONDARY,
        )
        _set_button_variant(
            self.nurture,
            BUTTON_VARIANT_PRIMARY if not active and not fully_grown else BUTTON_VARIANT_SECONDARY,
        )
        _set_button_variant(
            self.move,
            BUTTON_VARIANT_SECONDARY if active and not fully_grown else BUTTON_VARIANT_TERTIARY,
        )
        _set_button_variant(
            self.story,
            BUTTON_VARIANT_SECONDARY if active and not fully_grown else BUTTON_VARIANT_TERTIARY,
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
                if fertilizer_growth else
                "Fertilizer is available for this nurtured plant."
            )
        else:
            action_hint = "Nurture this plant before using Fertilizer."
            nurture_reason = "Nurture is available for this unfinished plant."
            fertilizer_reason = "Nurture this plant before using Fertilizer."
        self.status_value.setText(
            "Fully grown" if fully_grown else "Nurtured" if active else ""
        )
        self.status_row.hide()
        self.action_hint.setText(action_hint if fully_grown else "")
        self.action_hint.setAccessibleDescription(action_hint if fully_grown else "")
        set_hint_visible = getattr(self.action_hint, "setVisible", None)
        if callable(set_hint_visible):
            set_hint_visible(fully_grown)
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

    def __init__(self, parent: QWidget | None = None) -> None:
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
            cell.setMinimumHeight(96)
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
        growth_layout.setContentsMargins(16, 10, 16, 11)
        growth_layout.setSpacing(5)
        self.growth_kicker = QLabel("NURTURED PLANT")
        self.growth_kicker.setProperty("gardenStatLabel", True)
        growth_heading = QHBoxLayout()
        growth_heading.setSpacing(8)
        growth_heading.addWidget(self.growth_kicker)
        growth_heading.addStretch(1)
        self.growth_stage = QLabel("")
        self.growth_stage.setProperty("gardenStageBadge", True)
        self.growth_stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.growth_stage.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        growth_heading.addWidget(self.growth_stage)
        growth_identity = QHBoxLayout()
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
        growth_bar.setFixedHeight(10)
        growth_bar.setAccessibleName("Nurtured plant Growth")
        growth_bar.setProperty("metricProgress", True)
        self.growth_support = QLabel("Choose an unfinished plant to begin earning Growth")
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
        streak_layout.setContentsMargins(16, 10, 16, 11)
        streak_layout.setSpacing(5)
        self.streak_heading = QHBoxLayout()
        self.streak_heading.setSpacing(6)
        self.streak_label = QLabel("ANKI STREAK")
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
        self.streak_unit = QLabel("days")
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
        self.streak_support = QLabel("Study today to start your streak")
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
        currency_layout.setContentsMargins(16, 10, 16, 11)
        currency_layout.setSpacing(5)
        currency_label = QLabel("GARDEN COINS")
        currency_label.setProperty("gardenStatLabel", True)
        self.currency_value = QLabel("0")
        self.currency_value.setProperty("gardenLargeValue", True)
        self.currency_support = QLabel("Spend in the Nursery")
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
        currency_layout.addWidget(currency_label)
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
        self._growth_value_full_text = "0 / 0 Growth"
        # Every visible child belongs to one semantic, clickable metric card.
        for cell in self.cells.values():
            for child in cell.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self._compact = bool(compact)
        onboarding_mode = bool(getattr(self, "_onboarding_mode", False))
        for key, _title, _description in self.METRICS:
            self.grid.removeWidget(self.cells[key])
        if onboarding_mode:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 4)
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
        self.currency_support.setVisible(not compact and not onboarding_mode)
        self.streak_label.setText("ANKI STREAK")
        self.streak_label.setAccessibleName("ANKI STREAK")
        self.streak_label.setMinimumWidth(
            self.streak_label.sizeHint().width()
            if compact else 0
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
            f"+{self._streak_bonus_percent}%"
            if compact else
            f"+{self._streak_bonus_percent}% Growth"
        )
        refresh_growth_value = getattr(self, "_refresh_growth_value_copy", None)
        if callable(refresh_growth_value):
            refresh_growth_value()
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
            cell.setMinimumHeight(64 if enabled else 96)
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
        status_label: str = "NURTURED PLANT",
    ) -> None:
        safe_maximum = max(1, int(maximum))
        safe_current = min(safe_maximum, max(0, int(current)))
        normalized_status = str(status_label or "FIRST PLANT").upper()
        onboarding_state_only = normalized_status in {
            "NO PLANT SELECTED",
            "READY TO NURTURE",
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
        self.growth_kicker.show()
        self.growth_name.setText(str(plant_name))
        self.growth_name.setVisible(bool(str(plant_name).strip()))
        self.growth_value.show()
        self.growth_kicker.setText(normalized_status)
        self.growth_stage.setText(str(stage).upper())
        self.growth_stage.setVisible(bool(stage))
        if not stage:
            self._growth_value_full_text = "—"
            self.growth_support.setText("")
        else:
            self._growth_value_full_text = (
                "Complete" if fully_grown else f"{safe_current:,} / {safe_maximum:,} Growth"
            )
            if normalized_status == "READY TO NURTURE":
                self.growth_support.setText("")
            else:
                self.growth_support.setText(
                    "Rare · Fully grown"
                    if fully_grown else
                    f"{stage} · About {max(1, (max(0, int(remaining)) + 9) // 10):,} Anki card answers to {next_stage or 'the next stage'}"
                )
        self.growth_support.setVisible(bool(self.growth_support.text()) and not self._compact)
        self._refresh_growth_value_copy()
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
        self.streak_number.setText(f"{safe_days:,}")
        self.streak_unit.setText("day" if safe_days == 1 else "days")
        self.streak_bonus.setText(
            f"+{self._streak_bonus_percent}%"
            if self._compact else
            f"+{self._streak_bonus_percent}% Growth"
        )
        self.streak_support.setText(str(support))
        self.streak_support.setVisible(
            bool(str(support).strip()) and not self._compact and not self._onboarding_mode
        )
        title, explanation = self.metric_copy["streak"]
        self.cells["streak"].setAccessibleDescription(
            f"{METRIC_AFFORDANCE}. Open {title} details. {safe_days:,} days; +{max(0, int(bonus_percent))}% Growth. "
            f"{support}. {explanation}"
        )

    def set_currency_details(self, balance: int) -> None:
        safe_balance = max(0, int(balance))
        self.currency_value.setText(f"{safe_balance:,}")
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
        self.plant_id = ""
        self.bar_layout = QHBoxLayout(self)
        self.bar_layout.setContentsMargins(10, 8, 10, 8)
        copy = QVBoxLayout()
        self.title = QLabel("Moving plant")
        self.title.setProperty("moveTitle", True)
        self.instructions = QLabel("")
        self.instructions.setTextFormat(Qt.TextFormat.PlainText)
        self.instructions.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.instructions)
        self.bar_layout.addLayout(copy, 1)
        self.cancel = QPushButton("Cancel")
        _set_button_variant(self.cancel, BUTTON_VARIANT_SECONDARY)
        self.cancel.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.bar_layout.addWidget(self.cancel)
        self.hide()

    def set_compact(self, compact: bool) -> None:
        self.bar_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )

    def set_destinations(self, rows: list[tuple[str, int]]) -> None:
        """Compatibility no-op; destinations are selected directly in the scene."""

    def selected_destination(self) -> int | None:
        return None


class GardenSideNavigation(QWidget):
    """Responsive left rail that becomes a single-line tab row when narrow."""

    currentChanged = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Garden Progress sections")
        self.root_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(22)
        self.rail = QFrame()
        self.rail.setProperty("sideNavigation", True)
        self.rail_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.rail)
        self.rail_layout.setContentsMargins(0, 0, 0, 0)
        self.rail_layout.setSpacing(4)
        self.stack = QStackedWidget()
        self.stack.setAccessibleName("Garden Progress content")
        self.buttons: dict[str, QPushButton] = {}
        self.keys: list[str] = []
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
        self.rail_layout.addWidget(button)
        self.stack.addWidget(widget)
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
        self.root_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact else
            QBoxLayout.Direction.LeftToRight
        )
        self.rail_layout.setDirection(
            QBoxLayout.Direction.LeftToRight
            if compact else
            QBoxLayout.Direction.TopToBottom
        )
        self.rail.setMaximumWidth(16777215 if compact else 168)
        self.rail.setMinimumWidth(0 if compact else 156)
        self.rail.setMaximumHeight(52 if compact else 16777215)
        for button in self.buttons.values():
            button.setSizePolicy(
                QSizePolicy.Policy.Preferred if compact else QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )


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
    ) -> None:
        layout.addWidget(DisclosureRow(title, rows, expanded=expanded))

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
        plant = self.engine.active_plant()
        if plant is None:
            empty = QFrame()
            empty.setProperty("detailHero", True)
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(18, 16, 18, 16)
            empty_layout.addWidget(self._label("No nurtured plant", "detailSection"))
            empty_layout.addWidget(self._label(
                "Choose an unfinished planted plant to nurture. Future card answers will send Growth to that plant."
            ))
            layout.addWidget(empty)
            return

        display = growth_display(plant.growth_points)
        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(14)
        hero_layout.addWidget(_asset_preview_label(
            self.engine, plant.species, plant.growth_stage, size=80
        ), 0, Qt.AlignmentFlag.AlignTop)
        identity = QVBoxLayout()
        identity.setSpacing(5)
        kicker = self._label("NURTURED PLANT", "detailSupport")
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = self._label(plant.name, "detailSection")
        name.setStyleSheet("font-size:20px; font-weight:800;")
        stage = self._label(format_status_label(display.stage), "detailBadge")
        stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stage.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        name_row.addWidget(name, 1)
        name_row.addWidget(stage)
        identity.addWidget(kicker)
        identity.addLayout(name_row)
        progress = ProgressBar("Nurtured plant Growth to the next stage")
        if display.fully_grown:
            progress.set_progress("Rare Stage", 1, 1, value_text="Fully grown")
        else:
            next_stage = format_status_label(display.next_stage or "next stage")
            progress.set_progress(
                "Growth",
                display.stage_points,
                max(1, display.stage_goal),
                value_text=f"{display.stage_points:,} / {display.stage_goal:,} Growth",
            )
        identity.addWidget(progress)
        if display.fully_grown:
            support_text = f"Lifetime Growth: {plant.growth_points:,}"
        else:
            answers = max(1, (display.points_remaining + 9) // 10)
            support_text = (
                f"About {answers:,} Anki card {'answer' if answers == 1 else 'answers'} "
                f"to {next_stage}"
            )
        growth_support = self._label(support_text, "detailSupport")
        apply_tabular_numerals(growth_support)
        identity.addWidget(growth_support)
        hero_layout.addLayout(identity, 1)
        layout.addWidget(hero)
        self._add_growth_stage_path(layout, plant, display)

        stats = self.storage.state.daily_stats
        today = QFrame()
        today.setProperty("detailCard", True)
        today_layout = QVBoxLayout(today)
        today_layout.setContentsMargins(14, 12, 14, 12)
        today_layout.setSpacing(8)
        today_layout.addWidget(self._label("Growth today", "detailSection"))
        contributions = [
            ("Base", int(stats.base_growth)),
            ("Anki Streak", int(stats.streak_bonus_growth)),
            ("Fertilizer", int(stats.fertilizer_growth)),
            ("Booster Potion", int(getattr(stats, "booster_growth", 0))),
            ("Weather", int(getattr(stats, "weather_growth", 0))),
            ("Scenery", int(getattr(stats, "scenery_growth", 0))),
        ]
        charge_growth = max(0, int(getattr(stats, "charge_growth", 0) or 0))
        answer_growth = max(0, int(stats.growth_earned) - charge_growth)
        recorded = sum(value for _label, value in contributions)
        if recorded != answer_growth:
            contributions.append(("Other recorded Growth", answer_growth - recorded))
        active_rows = [(label, value) for label, value in contributions if value != 0]
        if charge_growth:
            active_rows.append(("Growth Charges", charge_growth))
        if int(stats.growth_earned) == 0:
            today_layout.addWidget(EmptyState(
                "No Growth earned today",
                f"Answer an Anki card to begin growing {plant.name}.",
            ))
        else:
            today_layout.addWidget(StatSummary([
                ("Total Growth", f"{int(stats.growth_earned):,}"),
            ]))
            self._disclosure(
                today_layout,
                "Growth breakdown",
                [(label, f"{value:,}") for label, value in active_rows],
                expanded=True,
            )
        today.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_keyboard_focus_surface(today)
        apply_explanatory_tooltip(today, GROWTH_EXPLANATION)
        layout.addWidget(today)

        charges = QFrame()
        charges.setProperty("detailCard", True)
        charges_layout = QVBoxLayout(charges)
        charges_layout.setContentsMargins(14, 12, 14, 12)
        charges_layout.setSpacing(4)
        charges_layout.addWidget(self._label("Growth Charges", "detailSection"))
        charges_layout.addWidget(self._label(
            "Stored charges provide instant Growth to the nurtured plant.",
            "detailBody",
        ))
        owned_charge = False
        inventory = getattr(self.storage.state, "consumables", {})
        for spec in GROWTH_CHARGES.values():
            quantity = max(0, int(inventory.get(spec.charge_id, 0) or 0))
            if quantity <= 0:
                continue
            owned_charge = True
            row = QHBoxLayout()
            row.addWidget(_item_preview_label(
                self.engine,
                spec.charge_id,
                f"{spec.name} preview",
                size=48,
            ))
            charge_quantity = self._label(
                f"{spec.name}: {quantity:,} available — +{spec.growth:,} Growth",
                "detailBody",
            )
            apply_tabular_numerals(charge_quantity)
            row.addWidget(charge_quantity, 1)
            use = QPushButton("Use Growth Charge")
            use.setMinimumHeight(BUTTON_MIN_HEIGHT)
            _set_button_variant(use, BUTTON_VARIANT_PRIMARY)
            use.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id: self._apply_growth_charge(charge_id)
            )
            row.addWidget(use)
            charges_layout.addLayout(row)
        if not owned_charge:
            nursery_route = QPushButton("Open Nursery")
            nursery_route.setMinimumHeight(BUTTON_MIN_HEIGHT)
            _set_button_variant(nursery_route, BUTTON_VARIANT_SECONDARY)
            nursery_route.clicked.connect(self._open_nursery)
            charges_layout.addWidget(EmptyState(
                "No Growth Charges available",
                "Growth Charges provide instant Growth and can be obtained in the Nursery.",
                action=nursery_route,
            ))
        layout.addWidget(charges)

    def _add_growth_stage_path(self, layout: QVBoxLayout, plant: Any, display: Any) -> None:
        self._section_label(layout, "Growth stages")
        stage_scroll = QScrollArea()
        stage_scroll.setWidgetResizable(True)
        stage_scroll.setFrameShape(QFrame.Shape.NoFrame)
        stage_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stage_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        stage_scroll.setAccessibleName("Six-stage plant growth track")
        stage_host = QWidget()
        stage_host.setMinimumWidth(648)
        stages = QHBoxLayout(stage_host)
        stages.setContentsMargins(0, 0, 0, 0)
        stages.setSpacing(8)
        for index, stage_key in enumerate(GROWTH_STAGES):
            state = (
                "completed" if index < display.stage_index else
                "current" if index == display.stage_index else
                "upcoming"
            )
            stage_card = QFrame()
            stage_card.setProperty("detailStage", True)
            stage_card.setProperty("detailStageState", state)
            stage_card.setMinimumWidth(98)
            stage_layout = QVBoxLayout(stage_card)
            stage_layout.setContentsMargins(7, 7, 7, 7)
            stage_layout.setSpacing(3)
            preview = _asset_preview_label(
                self.engine,
                plant.species,
                stage_key,
                size=58,
                rare_unlocked=state != "upcoming",
            )
            stage_layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
            stage_name = self._label(format_status_label(stage_key), "detailSection")
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status = self._label(
                "✓ Completed" if state == "completed" else
                "Current" if state == "current" else
                "Locked",
                "detailSupport",
            )
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(stage_name)
            stage_layout.addWidget(status)
            stage_card.setAccessibleName(
                f"{format_status_label(stage_key)} stage. {status.text()}."
            )
            stages.addWidget(stage_card)
        stage_scroll.setWidget(stage_host)
        _set_scroll_surface(stage_scroll, stage_host, "#0b1f1b")
        layout.addWidget(stage_scroll)

    def _apply_growth_charge(self, charge_id: str) -> None:
        plant = self.engine.active_plant()
        spec = GROWTH_CHARGES.get(str(charge_id))
        if plant is not None and spec is not None:
            before = max(0, int(plant.growth_points))
            after = before + int(spec.growth)
            crossed = sum(1 for threshold in GROWTH_THRESHOLDS if before < threshold <= after)
            if crossed > 1 and not ConfirmationDialog.confirm(
                self,
                "Use large Growth Charge?",
                f"{spec.name} may cross {crossed} plant stages. Use it now?",
            ):
                return
        ok, message = self.engine.use_growth_charge(charge_id)
        parent = self.parentWidget()
        toast = getattr(parent, "toast_region", None)
        if ok:
            refresh = getattr(parent, "_refresh_after_commit", None)
            if callable(refresh):
                refresh("Growth Charge")
            self.refresh()
        if toast is not None:
            toast.show_message(_learner_text(message), error=not ok)

    def _streak_reward_text(self, day: int, percent: int) -> str:
        if day == 1 and percent == 0:
            return "Streak activated"
        parts = [f"+{percent}% Growth"]
        coins = int(self.engine.STREAK_CURRENCY.get(day, 0) or 0)
        if coins:
            parts.append(_garden_coin_count(coins))
        return " · ".join(parts)

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
        bonus = self.engine.current_streak_bonus_percent() if days > 0 else 0
        maintained_today = presentation.status_label == "Active"
        status_text = presentation.status_label
        cutoff_text = "Unavailable"
        try:
            cutoff_ms = int(self.storage.current_day_end_ms())
            if cutoff_ms > 0:
                cutoff = datetime.fromtimestamp(cutoff_ms / 1000)
                cutoff_text = cutoff.strftime("%I:%M %p").lstrip("0")
        except (AttributeError, OSError, TypeError, ValueError):
            pass

        next_tier = next(
            ((day, percent) for day, percent in STREAK_BONUS_TIERS if days < day),
            None,
        )
        next_day = next_tier[0] if next_tier is not None else STREAK_BONUS_TIERS[-1][0]

        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 15, 18, 15)
        hero_layout.setSpacing(8)
        status_row = QHBoxLayout()
        metric = self._label(_day_count(days), "detailMetric")
        apply_tabular_numerals(metric)
        status = self._label(status_text, "detailStatus")
        status.setProperty("streakSemantic", presentation.semantic)
        status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(metric, 1)
        status_row.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(status_row)
        if presentation.previous_days > 0:
            previous_streak = self._label(
                f"Previous streak: {_day_count(presentation.previous_days)}",
                "detailSupport",
            )
            apply_tabular_numerals(previous_streak)
            hero_layout.addWidget(previous_streak)
        next_progress = ProgressBar("Progress to the next Anki streak milestone")
        days_to_next = max(0, next_day - days)
        next_progress.set_progress(
            f"Next milestone: Day {next_day:,}",
            min(days, next_day),
            max(1, next_day),
            value_text=(
                "Reached" if days_to_next == 0 else
                f"{_day_count(days_to_next)} to go"
            ),
        )
        hero_layout.addWidget(next_progress)
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
            day.setMinimumHeight(82)
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
            day_layout.addWidget(day_value)
            day.setAccessibleName(
                f"{calendar_day.strftime('%A')}, "
                f"{'today' if calendar_day == current_day else 'streak complete' if complete else 'missed' if missed else 'upcoming' if calendar_day > current_day else 'before this streak'}"
            )
            week.addWidget(day, 1)
        hero_layout.addLayout(week)
        metadata = QHBoxLayout()
        metadata.addWidget(self._label("Current Growth bonus", "detailSupport"))
        bonus_value = self._label(f"+{bonus}%", "detailSection")
        apply_tabular_numerals(bonus_value)
        metadata.addWidget(bonus_value)
        metadata.addStretch(1)
        cutoff_sentence = (
            f"Your Anki day ends at {cutoff_text}."
            if cutoff_text != "Unavailable" else
            "Your Anki day cutoff is currently unavailable."
        )
        cutoff_value = self._label(cutoff_sentence, "detailBody")
        apply_tabular_numerals(cutoff_value)
        metadata.addWidget(cutoff_value)
        hero_layout.addLayout(metadata)
        layout.addWidget(hero)

        if presentation.message:
            layout.addWidget(self._label(presentation.message, "detailBody"))

        self._section_label(layout, "Milestones")
        milestone_table = DataTable()
        milestone_grid = milestone_table.grid
        milestone_grid.setHorizontalSpacing(14)
        for column, heading in enumerate(("Milestone", "Reward", "Status")):
            header = self._label(heading, "detailTableHeader")
            if column == 2:
                header.setAlignment(Qt.AlignmentFlag.AlignRight)
            milestone_grid.addWidget(header, 0, column)
        for row, (day, percent) in enumerate(STREAK_BONUS_TIERS, start=1):
            reward_milestone = day in STREAK_REWARD_MILESTONES
            claimed = day in set(getattr(state, "claimed_streak_rewards", []) or [])
            reached = days >= day or (reward_milestone and claimed)
            status_text = (
                "Earned automatically" if reached and reward_milestone else
                "Reached" if reached else
                "Next" if day == next_day else
                "Upcoming"
            )
            milestone = self._label(_day_count(day), "detailBody")
            reward = self._label(self._streak_reward_text(day, percent), "detailBody")
            apply_tabular_numerals(milestone)
            apply_tabular_numerals(reward)
            status = self._label(
                status_text,
                "detailStatus" if day == next_day and not reached else "detailSupport",
            )
            status.setAlignment(Qt.AlignmentFlag.AlignRight)
            for cell in (milestone, reward, status):
                cell.setContentsMargins(4, 7, 4, 7)
            milestone_grid.addWidget(milestone, row, 0)
            milestone_grid.addWidget(reward, row, 1)
            milestone_grid.addWidget(status, row, 2)
        milestone_grid.setColumnStretch(1, 1)
        layout.addWidget(milestone_table)
        self._disclosure(
            layout,
            "How the streak works",
            [(
                "Rule",
                "Answer at least one card during each consecutive Anki scheduler day to maintain the streak.",
            )],
        )

    def _refresh_currency(self, layout: QVBoxLayout) -> None:
        balance = max(0, int(self.storage.state.currency_balance))
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
        open_nursery = QPushButton("Open Nursery")
        _set_button_variant(open_nursery, BUTTON_VARIANT_PRIMARY)
        open_nursery.clicked.connect(self._open_nursery)
        hero_layout.addWidget(open_nursery, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(hero)

        ledger_panel = QWidget()
        ledger_layout = QVBoxLayout(ledger_panel)
        ledger_layout.setContentsMargins(0, 0, 0, 0)
        ledger_layout.setSpacing(10)
        earning_panel = QWidget()
        earning_layout = QVBoxLayout(earning_panel)
        earning_layout.setContentsMargins(0, 0, 0, 0)
        earning_layout.setSpacing(10)
        split = ResponsiveSplit(ledger_panel, earning_panel, breakpoint=620)
        layout.addWidget(split)

        self._section_label(ledger_layout, "Recent activity")
        all_transactions = sorted(
            self.storage.state.currency_transactions,
            key=lambda transaction: str(getattr(transaction, "occurred_at", "")),
            reverse=True,
        )
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
            ledger_layout.addLayout(filters)
        transactions = [
            transaction for transaction in all_transactions
            if self._transaction_filter == "all"
            or (self._transaction_filter == "earned" and int(transaction.delta) > 0)
            or (self._transaction_filter == "spent" and int(transaction.delta) < 0)
        ]
        visible = transactions if self._show_all_transactions else transactions[:8]
        if not visible:
            ledger_layout.addWidget(EmptyState(
                "No coin activity yet",
                "Earnings and purchases will appear here.",
            ))
        else:
            ledger = DataTable()
            ledger_grid = ledger.grid
            for column, heading in enumerate(("Date", "Activity", "Coins", "Balance")):
                header = self._label(heading, "detailTableHeader")
                if column >= 2:
                    header.setAlignment(Qt.AlignmentFlag.AlignRight)
                ledger_grid.addWidget(header, 0, column)
            for row, transaction in enumerate(visible, start=1):
                delta = int(transaction.delta)
                date_label = self._label(_transaction_date(transaction.occurred_at), "detailSupport")
                reason = self._label(str(transaction.reason), "detailBody")
                amount = self._label(
                    f"{'+' if delta >= 0 else '−'}{abs(delta):,}",
                    "detailPositive" if delta >= 0 else "detailNegative",
                )
                apply_tabular_numerals(amount)
                amount.setAlignment(Qt.AlignmentFlag.AlignRight)
                resulting = self._label(f"{int(transaction.balance):,}", "detailBody")
                apply_tabular_numerals(resulting)
                resulting.setAlignment(Qt.AlignmentFlag.AlignRight)
                for cell in (date_label, reason, amount, resulting):
                    cell.setContentsMargins(4, 7, 4, 7)
                ledger_grid.addWidget(date_label, row, 0)
                ledger_grid.addWidget(reason, row, 1)
                ledger_grid.addWidget(amount, row, 2)
                ledger_grid.addWidget(resulting, row, 3)
            ledger_grid.setColumnStretch(1, 1)
            ledger_layout.addWidget(ledger)
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
            ledger_layout.addWidget(view_all)

        ledger_layout.addStretch(1)

        self._section_label(earning_layout, "Ways to earn")
        for title, body in (
            ("Reach new plant stages", "Stage rewards are added when a plant advances."),
            ("Build an Anki streak", "Milestone rewards grow with your Anki streak."),
            ("Complete daily study goals", "Finish daily Anki study goals to earn rewards."),
        ):
            method = QFrame()
            method.setProperty("detailRow", True)
            method_layout = QVBoxLayout(method)
            method_layout.setContentsMargins(6, 8, 6, 8)
            method_layout.setSpacing(2)
            method_layout.addWidget(self._label(title, "detailSection"))
            method_layout.addWidget(self._label(body, "detailSupport"))
            earning_layout.addWidget(method)

        earning_rows = [
            (f"Reach {format_status_label(stage)}", f"+{amount:,} Garden Coins")
            for stage, amount in self.engine.STAGE_CURRENCY.items()
        ]
        earning_rows.extend(
            (f"Reach an Anki streak of {_day_count(day)}", f"+{amount:,} Garden Coins")
            for day, amount in self.engine.STREAK_CURRENCY.items()
        )
        earning_rows.extend((
            ("Finish all due cards", "Daily Garden Coin reward"),
            ("Receive a rare study gift", f"+{int(self.engine.COIN_DROP_AMOUNT):,} Garden Coins"),
        ))
        self._disclosure(
            earning_layout,
            "View all earning rules",
            earning_rows,
            expanded=False,
        )
        self._disclosure(
            earning_layout,
            "What Garden Coins can purchase",
            [
                ("Plants", "Unlock new species in the Nursery"),
                ("Fertilizer", "Apply timed Growth bonuses"),
                ("Garden spaces", "Permanently expand planting capacity"),
                ("Environment", "Unlock purchasable Weather and Scenery"),
            ],
        )
        earning_layout.addStretch(1)

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
    """One responsive home for Overview, progress, rewards, and collection."""

    PAGE_LABELS = (
        ("overview", "Overview"),
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
        overview: QWidget,
        achievements: QWidget,
        collection: QWidget,
    ) -> None:
        super().__init__(parent, engine, storage, open_nursery)
        self.set_dialog_title("Garden Progress")
        self.dialog_subtitle.setText("")
        self.dialog_subtitle.hide()
        self.apply_size_policy(
            DialogSizeClass.CATALOG,
            preferred_width=940,
            preferred_height=680,
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
            "overview": overview,
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
                168,
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

        self.help_button = QPushButton("?")
        self.help_button.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        self.help_button.setAccessibleName("How Growth works")
        self.help_button.setToolTip("How Growth works")
        _set_button_variant(self.help_button, BUTTON_VARIANT_TERTIARY)
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
        self.navigation.set_current("overview", emit=False)
        self._page_changed("overview")

    def _show_growth_help(self) -> None:
        QMessageBox.information(
            self,
            "How Growth Works",
            "Anki card answers give the nurtured plant base Growth. "
            "Your Anki streak, active Fertilizer, Booster Potions, equipped Weather and Scenery, "
            "and Growth Charges can add more. Existing Growth never moves between plants.",
        )
        QTimer.singleShot(0, self.help_button.setFocus)

    def _page_changed(self, key: str) -> None:
        self.set_dialog_title("Garden Progress")
        self.footer.hide()
        QTimer.singleShot(0, self._sync_footer_clearance)
        button = self.navigation.buttons.get(str(key))
        if button is not None:
            self.dialog_subtitle.setAccessibleDescription(
                f"Showing {button.text()} in Garden Progress."
            )

    def open_page(self, key: str = "overview") -> None:
        self.refresh()
        self.navigation.set_current(str(key))
        self.present_over_parent()
        button = self.navigation.buttons.get(str(key)) or self.navigation.buttons.get("overview")
        if button is not None:
            QTimer.singleShot(0, button.setFocus)

    def open_metric(self, metric: str) -> None:
        self.open_page(metric)

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


class CustomizeGardenDialog(GardenDialog):
    """Image-led Weather and Scenery configurator with an unsaved draft."""

    def __init__(
        self,
        parent: QWidget,
        engine: Any,
        storage: Any,
        snapshot_provider: Callable[[], dict[str, Any]],
    ) -> None:
        super().__init__(
            parent,
            "Customize Garden",
            subtitle="Preview Weather and Scenery together before applying changes.",
        )
        self.engine = engine
        self.storage = storage
        self.snapshot_provider = snapshot_provider
        self._draft_weather = DEFAULT_WEATHER_ID
        self._draft_scenery = DEFAULT_SCENERY_ID
        self._draft_visibility = {"weather": True, "scenery": True}
        self._persisted_draft: tuple[str, str, bool, bool] = (
            DEFAULT_WEATHER_ID,
            DEFAULT_SCENERY_ID,
            True,
            True,
        )
        self._tiles: dict[tuple[str, str], QPushButton] = {}
        self._persisted_weather = DEFAULT_WEATHER_ID
        self._persisted_scenery = DEFAULT_SCENERY_ID
        self._compact = False
        self.apply_size_policy(
            DialogSizeClass.PREVIEW,
            preferred_width=1040,
            preferred_height=700,
        )
        self.setStyleSheet(_garden_dialog_stylesheet() + f"""
            QFrame[customizeLibrary='true'] {{ background:{GARDEN_THEME['raised_surface']}; border:0; border-radius:12px; }}
            QFrame[customizePreview='true'] {{ background:#0a211b; border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:12px; }}
            QPushButton[environmentTile='true'] {{ min-height:176px; text-align:left; padding:10px; color:{GARDEN_THEME['text_primary']}; background:#102a22; border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:11px; }}
            QPushButton[environmentTile='true']:hover {{ background:#173b30; border-color:{GARDEN_THEME['strong_border']}; }}
            QPushButton[environmentTile='true']:checked {{ background:#173b30; border:2px solid {GARDEN_THEME['focus_ring']}; padding:9px; }}
            QPushButton[environmentTile='true']:disabled {{ color:{GARDEN_THEME['text_secondary']}; background:#10231f; border-color:#344b43; }}
            QLabel[environmentThumb='true'] {{ background:#071a15; border:0; border-radius:8px; color:{GARDEN_THEME['text_muted']}; }}
            QLabel[environmentName='true'] {{ color:{GARDEN_THEME['text_primary']}; font-size:14px; font-weight:650; }}
            QLabel[environmentState='true'] {{ color:{GARDEN_THEME['text_secondary']}; font-size:12.5px; }}
            QLabel[unsavedState='true'] {{ color:{GARDEN_THEME['coin_accent']}; font-size:13px; font-weight:650; }}
        """)

        body = QWidget()
        self.main_grid = QGridLayout(body)
        self.main_grid.setContentsMargins(0, 0, 0, 0)
        self.main_grid.setHorizontalSpacing(16)
        self.main_grid.setVerticalSpacing(16)

        self.library = QFrame()
        self.library.setProperty("customizeLibrary", True)
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
        effects_host = QWidget()
        effects_layout = QVBoxLayout(effects_host)
        effects_layout.setContentsMargins(6, 10, 18, 10)
        effects_layout.setSpacing(14)
        effects_heading = QLabel("Visual effects")
        effects_heading.setProperty("dialogTitle", True)
        effects_intro = QLabel(
            "These switches control artwork only. Equipped passive effects remain active."
        )
        effects_intro.setProperty("dialogSubtitle", True)
        effects_intro.setWordWrap(True)
        self.show_weather = ToggleSwitch("Show Weather artwork")
        self.show_scenery = ToggleSwitch("Show Scenery artwork")
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
        advanced_title = QLabel("Included appearance")
        advanced_title.setProperty("rowTitle", True)
        advanced_copy = QLabel(
            "Preview Clear Skies with Verdant Twilight. Apply changes to save."
        )
        advanced_copy.setProperty("dialogSubtitle", True)
        advanced_copy.setWordWrap(True)
        restore = QPushButton("Preview included appearance")
        restore.setAccessibleDescription(
            "Update the preview to Clear Skies and Verdant Twilight. "
            "The appearance is not saved until Apply changes is selected."
        )
        _set_button_variant(restore, BUTTON_VARIANT_SECONDARY)
        restore.clicked.connect(self._restore_default_draft)
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
        self.preview_panel.setProperty("customizePreview", True)
        self.preview_panel.setMinimumWidth(0)
        self.preview_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_heading = QLabel("Live garden preview")
        preview_heading.setProperty("dialogTitle", True)
        self.preview_selection = QLabel("")
        self.preview_selection.setProperty("dialogSubtitle", True)
        self.preview_selection.setWordWrap(True)
        self.preview_scene = GardenSceneWidget()
        self.preview_scene.set_interactive(False)
        self.preview_scene.setMinimumSize(0, 300)
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview_selection)
        preview_layout.addWidget(self.preview_scene, 1)

        self.main_grid.addWidget(self.library, 0, 0)
        self.main_grid.addWidget(self.preview_panel, 0, 1)
        self.main_grid.setColumnStretch(0, 5)
        self.main_grid.setColumnStretch(1, 6)
        self.body_scroll = QScrollArea()
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body_scroll.setAccessibleName("Customize Garden content")
        self.body_scroll.setWidget(body)
        _set_scroll_surface(
            self.body_scroll,
            body,
            GARDEN_THEME["dialog_surface"],
        )
        self.set_body_widget(self.body_scroll)
        self.customize_responsive = AdaptiveSplit(
            "customize-garden.workspace",
            AdaptiveRegion.measured(
                "appearance-library",
                self.library,
                floor=420,
            ),
            AdaptiveRegion.measured(
                "garden-preview",
                self.preview_panel,
                floor=460,
            ),
            spacing=16,
            apply_mode=self._apply_customize_layout_mode,
            telemetry_target=self,
        )

        self.unsaved = QLabel("")
        self.unsaved.setProperty("unsavedState", True)
        self.unsaved.setAccessibleName("Customize Garden save status")
        self.footer_layout.addWidget(self.unsaved, 1)
        cancel = QPushButton("Cancel")
        _set_button_variant(cancel, BUTTON_VARIANT_SECONDARY)
        cancel.clicked.connect(self.reject)
        self.apply_changes = QPushButton("Apply changes")
        _set_button_variant(self.apply_changes, BUTTON_VARIANT_PRIMARY)
        self.apply_changes.clicked.connect(self._apply_draft)
        self.footer_layout.addWidget(cancel)
        self.footer_layout.addWidget(self.apply_changes)
        self.footer.show()
        self.prepare_to_show()

    def _option_page(self, accessible_name: str) -> tuple[QWidget, QGridLayout]:
        host = QWidget()
        host.setAccessibleName(f"{accessible_name} options")
        grid = QGridLayout(host)
        grid.setContentsMargins(4, 6, 4, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        return host, grid

    def _apply_customize_layout_mode(self, mode: str) -> None:
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
            self.preview_scene.setMinimumHeight(240)
        else:
            self.main_grid.addWidget(self.library, 0, 0)
            self.main_grid.addWidget(self.preview_panel, 0, 1)
            self.main_grid.setColumnStretch(0, 5)
            self.main_grid.setColumnStretch(1, 6)
            self.main_grid.setRowStretch(0, 1)
            self.preview_scene.setMinimumHeight(300)
        self.library.setMinimumHeight(0)
        self.preview_panel.setMinimumHeight(0)
        body = self.body_scroll.widget()
        if body is not None:
            body.setMinimumHeight(0)
            body.updateGeometry()

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
        label.setFixedSize(164, 92)
        label.setProperty("environmentThumb", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(f"{item.name} preview")
        label.setPixmap(_environment_preview_pixmap(
            self.engine,
            item,
            164,
            92,
            scenery_id=self._draft_scenery,
        ))
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
            "Selected · Unsaved" if selected else
            "Owned" if owned else
            f"Locked · {cost_label(item.price)}" if item.price is not None else
            "Locked · discovery reward"
        )
        state = QLabel(state_text)
        state.setProperty("environmentState", True)
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state.setWordWrap(True)
        state.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(name)
        layout.addWidget(state)
        tile.setAccessibleDescription(
            f"{item.name}. {state_text}. {item.effect if owned else item.how_to_earn}"
        )
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

    def _rebuild_options(self) -> None:
        self._clear_grid(self.scenery_grid)
        self._clear_grid(self.weather_grid)
        self._tiles.clear()
        for grid, catalog in (
            (self.scenery_grid, SCENERY_CATALOG),
            (self.weather_grid, WEATHER_CATALOG),
        ):
            for index, item in enumerate(catalog.values()):
                grid.addWidget(self._option_tile(item), index // 2, index % 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setRowStretch((len(catalog) + 1) // 2, 1)

    def prepare_to_show(self) -> None:
        state = self.storage.state
        self._draft_weather = str(state.selected_weather)
        self._draft_scenery = str(state.selected_background)
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

    def _draft_key(self) -> tuple[str, str, bool, bool]:
        return (
            self._draft_weather,
            self._draft_scenery,
            self._draft_visibility["weather"],
            self._draft_visibility["scenery"],
        )

    def _select_option(self, kind: str, item_id: str) -> None:
        if kind == "weather":
            self._draft_weather = str(item_id)
        else:
            self._draft_scenery = str(item_id)
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()

    def _set_draft_visibility(self, kind: str, enabled: bool) -> None:
        self._draft_visibility[str(kind)] = bool(enabled)
        self._refresh_preview()
        self._sync_dirty_state()

    def _restore_default_draft(self) -> None:
        self._draft_weather = DEFAULT_WEATHER_ID
        self._draft_scenery = DEFAULT_SCENERY_ID
        self._draft_visibility = {"weather": True, "scenery": True}
        self.show_weather.setChecked(True)
        self.show_scenery.setChecked(True)
        self._rebuild_options()
        self._refresh_preview()
        self._sync_dirty_state()

    def _sync_dirty_state(self) -> None:
        dirty = self._draft_key() != self._persisted_draft
        set_control_enabled(
            self.apply_changes,
            dirty,
            disabled_reason="The Garden appearance already matches the saved choices.",
            enabled_description="Save the previewed Weather and Scenery choices.",
        )
        self.unsaved.setText("Unsaved changes" if dirty else "")
        self.unsaved.setAccessibleDescription(
            "The preview contains unapplied appearance changes." if dirty else ""
        )

    def _refresh_preview(self) -> None:
        snapshot = dict(self.snapshot_provider() or {})
        scenery_id = (
            self._draft_scenery
            if self._draft_visibility["scenery"] else
            DEFAULT_SCENERY_ID
        )
        try:
            background = self.engine.resolve_scenery_preview_asset(scenery_id)
            weather = (
                self.engine.resolve_weather_preview_asset(self._draft_weather)
                if self._draft_visibility["weather"] else None
            )
            overlay = self.engine.resolve_garden_overlay_asset()
            nurtured_marker = self.engine.resolve_nurtured_marker_asset()
            nurtured_marker_spout_right = (
                self.engine.resolve_nurtured_marker_spout_right_asset()
            )
        except Exception:
            background = weather = overlay = nurtured_marker = None
            nurtured_marker_spout_right = None
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
            },
            "plants": plants,
        })
        weather_name = WEATHER_CATALOG[self._draft_weather].name
        scenery_name = SCENERY_CATALOG[self._draft_scenery].name
        self.preview_selection.setText(f"{scenery_name} · {weather_name}")
        self.preview_selection.setAccessibleDescription(
            f"Previewing {scenery_name} scenery with {weather_name} weather."
        )

    def _apply_draft(self) -> None:
        ok, message = self.engine.apply_environment_loadout(
            self._draft_weather,
            self._draft_scenery,
            self._draft_visibility,
        )
        if not ok:
            learner_message = _learner_text(message)
            self.unsaved.setText(learner_message)
            self.unsaved.setAccessibleDescription(f"Customize Garden error: {message}")
            self.unsaved.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            set_keyboard_focus_surface(self.unsaved)
            self.unsaved.setFocus()
            self.accessibility_announcer.announce(
                learner_message,
                priority=AnnouncementPriority.ASSERTIVE,
                target=self.unsaved,
            )
            return
        self._persisted_draft = self._draft_key()
        self._persisted_weather = self._draft_weather
        self._persisted_scenery = self._draft_scenery
        self._rebuild_options()
        self._sync_dirty_state()
        self.unsaved.setText("Changes applied")
        self.unsaved.setAccessibleDescription("Garden appearance changes saved.")
        self.accessibility_announcer.announce(
            "Garden appearance changes saved.",
            target=self.unsaved,
        )
        parent = self.parentWidget()
        refresh = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh):
            refresh("environment loadout")
        QTimer.singleShot(
            2400,
            lambda: self.unsaved.setText("")
            if self._draft_key() == self._persisted_draft else None,
        )

    def resizeEvent(self, event: Any) -> None:
        margins = self._shell_layout.contentsMargins()
        content_width = max(
            0,
            int(event.size().width()) - margins.left() - margins.right(),
        )
        if hasattr(self, "customize_responsive"):
            telemetry = self.customize_responsive.evaluate(content_width)
            self.setProperty("workspaceMode", telemetry.mode)
        super().resizeEvent(event)

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
        self.settings_dialog: GardenSettingsDialog | None = None
        self.nursery_dialog: NurseryDialog | None = None
        self.story_dialog: PlantStoryDialog | None = None
        self.fertilizer_dialog: DialogShell | None = None
        self._fertilizer_purchase_pending = False
        self._undo_nurture_plant_id = ""
        self._starter_prompt_scheduled = False
        self._starter_setup_dismissed = False
        self._undo_placement: Any = None
        self._placement_draft: Any = None
        self._stage_message_generation = 0
        self._pending_feedback_ack_ids: tuple[str, ...] = ()
        self._pending_transition_ack: tuple[Any, ...] = ()
        self._onboarding_just_completed = False
        self._onboarding_confirmation_generation = 0
        self._onboarding_save_error = ""
        self._starter_confirmation_message = ""
        self._onboarding_plant_id = ""
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
        self._apply_responsive_layout(
            max(0, self.width() - self.ROOT_MARGINS[0] - self.ROOT_MARGINS[2])
        )
        self._fertilizer_timer = QTimer(self)
        self._fertilizer_timer.setInterval(30_000)
        self._fertilizer_timer.timeout.connect(self._refresh_selected_plant_card)
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

        if not bool(getattr(self.storage.state, "starter_selection_complete", True)):
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
            QLabel[plantPopoverArtwork='true'] {{ background:#123228; border:0; border-radius:10px; color:#B8C5BF; font-size:24px; }}
            QLabel[plantCardHeading='true'] {{ color:#F4F7F5; font-size:18px; font-weight:700; }}
            QLabel[plantStageBadge='true'] {{ color:#B8C5BF; background:#123228; border:0; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; letter-spacing:.5px; }}
            QLabel[nurturedBadge='true'] {{ {_nurtured_badge_declarations()} }}
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
            QFrame[movePanel='true'] {{ background:rgba(12,38,31,235); border:1px solid #4F806E; border-radius:10px; }}
            QFrame[gardenStats='true'] {{ background:#0C261F; border:1px solid {self.CARD_BORDER}; border-radius:10px; }}
            QPushButton[gardenStatCell='true'] {{ min-height:96px; text-align:left; background:transparent; border:0; border-radius:0; padding:0; }}
            QPushButton[gardenStatCell='true'][separator='true'] {{ border-right:1px solid {self.CARD_BORDER}; }}
            QPushButton[gardenStatCell='true']:hover {{ background:#173B30; }}
            QPushButton[gardenStatCell='true']:pressed {{ background:#123228; }}
            QPushButton[gardenStatCell='true']:focus {{ border:2px solid #82E2AC; }}
            QLabel[gardenStatLabel='true'] {{ color:#91aa9b; font-size:12px; font-weight:800; letter-spacing:.8px; }}
            QLabel[gardenPlantName='true'] {{ color:#F4F7F5; font-size:16px; font-weight:700; }}
            QLabel[gardenStageBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:800; letter-spacing:.7px; }}
            QLabel[gardenGrowthValue='true'] {{ color:#F4F7F5; font-size:16px; font-weight:700; }}
            QLabel[gardenLargeValue='true'] {{ color:#F4F7F5; font-size:22px; font-weight:700; }}
            QLabel[gardenValueUnit='true'] {{ color:#c8d5cb; font-size:15px; padding-bottom:2px; }}
            QLabel[gardenBonusBadge='true'] {{ color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 7px; font-size:12px; font-weight:700; }}
            QLabel[gardenStatSupport='true'] {{ color:#B8C5BF; font-size:13px; }}
            QLabel[gardenDetailsAffordance='true'] {{ color:#B8C5BF; font-size:13px; font-weight:600; }}
            QFrame[onboarding='true'] {{ background:rgba(12,38,31,238); border:1px solid #4F806E; border-radius:10px; }}
            QFrame[progressRow='true'] {{ background:#0d211e; border:1px solid #27443a; border-radius:9px; }}
            QFrame[progressRow='true'][completed='true'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QFrame[progressRow='true'][achievementState='locked'] {{ border-left:3px solid #52645d; }}
            QFrame[progressRow='true'][achievementState='in_progress'] {{ border-left:3px solid #d1ad69; }}
            QFrame[progressRow='true'][achievementState='unlocked'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QFrame[catalogCard='true'] {{ background:#0C261F; border:1px solid #20483C; border-radius:12px; }}
            QFrame[catalogCard='true'][catalogState='unlocked'] {{ border-color:#4F806E; }}
            QLabel[catalogIcon='true'] {{ color:#82E2AC; background:#123228; border-radius:18px; font-size:17px; font-weight:800; }}
            QLabel[catalogStatus='true'] {{ color:#CFE0D6; background:#123228; border-radius:8px; padding:4px 7px; font-size:12px; font-weight:700; }}
            QLabel[categoryTitle='true'] {{ color:#F4F7F5; font-size:15px; font-weight:800; padding:8px 2px 1px 2px; }}
            QLabel[typography='title'] {{ font-size: 20px; font-weight: 800; letter-spacing: 0.3px; }}
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
            QTabBar::tab {{ min-height:42px; min-width:104px; padding:0 14px; color:#B8C5BF; background:transparent; border:0; border-bottom:2px solid transparent; font-weight:600; }}
            QTabBar::tab:hover {{ background:#173B30; color:#F4F7F5; }}
            QTabBar::tab:selected {{ color:#F4F7F5; border-bottom:2px solid #5CC58B; }}
            QScrollArea {{ background:transparent; border:0; }}
            {foundation_stylesheet()}
            QPushButton[catalogCard='true'] {{ min-height:214px; padding:10px; text-align:left; background:#0C261F; border:1px solid #20483C; border-radius:12px; }}
            QPushButton[catalogCard='true']:hover {{ background:#173B30; border-color:#4F806E; }}
            QPushButton[catalogCard='true']:focus {{ border:2px solid #82E2AC; padding:9px; }}
            QPushButton[headerAction='true'] {{ min-height:44px; max-height:44px; min-width:44px; font-size:13px; }}
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
        root.setContentsMargins(*self.ROOT_MARGINS)
        root.setSpacing(self.ROOT_SPACING)
        # The dashboard is a fixed shell. A focus change inside the scene must
        # never scroll the product title or primary actions out of view.
        self.dashboard_page = page
        outer.addWidget(page)

        self.top_bar = QFrame()
        top = self.top_bar
        top.setProperty("topBar", True)
        top.setMinimumHeight(92)
        # The header may grow to its responsive size hint, but it must not
        # absorb spare dashboard height. A vertical Minimum policy lets Qt
        # stretch the frame and leaves a large empty band between the metric
        # strip and garden artwork on shorter/high-DPI displays.
        top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.header_grid = QGridLayout(top)
        self.header_grid.setContentsMargins(14, 8, 14, 8)
        self.header_grid.setHorizontalSpacing(12)
        self.header_grid.setVerticalSpacing(8)
        self.title_stack_widget = QWidget()
        self.title_stack_widget.setMinimumWidth(0)
        self.title_stack_widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
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
        self.title_label = QLabel("")
        self._apply_typography(self.title_label, "title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(True)
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
        self.customize_btn = QPushButton("Customize Garden")
        self.customize_btn.setProperty("headerAction", True)
        _set_button_variant(self.customize_btn, BUTTON_VARIANT_TERTIARY)
        self.customize_btn.setAccessibleDescription(
            "Choose Weather and Scenery without changing plant placement."
        )
        self.customize_btn.clicked.connect(self._open_customize)
        self.settings_btn = QPushButton()
        self.settings_btn.setProperty("headerAction", True)
        self.settings_btn.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        self.settings_btn.setIcon(_settings_gear_icon(22))
        self.settings_btn.setIconSize(QSize(22, 22))
        self.settings_btn.setAccessibleName(UI_TEXT["open_settings"])
        _set_button_variant(self.settings_btn, BUTTON_VARIANT_TERTIARY)
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
        action_row.setSpacing(6)
        action_row.addWidget(self.starter_header_btn)
        action_row.addWidget(self.nursery_recovery_btn)
        action_row.addWidget(self.progress_btn)
        action_row.addWidget(self.customize_btn)
        action_row.addWidget(self.settings_btn)
        self.garden_stats_bar = GardenStatsStrip()
        self.garden_stats_bar.setMinimumHeight(104)
        self.garden_stats_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.garden_stats_bar.setMinimumWidth(0)
        self.garden_stats_bar.metricActivated.connect(self._open_metric_details)
        self.header_grid.addWidget(self.title_stack_widget, 0, 0)
        self.header_grid.addWidget(self.garden_stats_bar, 0, 1)
        self.header_grid.addWidget(self.header_actions_widget, 0, 2)
        self.header_grid.setColumnStretch(1, 1)

        self.onboarding_panel = QFrame()
        self.onboarding_panel.setProperty("onboarding", True)
        self.onboarding_panel.setAccessibleName("Getting started with Anki Garden")
        self.onboarding_layout = QVBoxLayout(self.onboarding_panel)
        self.onboarding_layout.setContentsMargins(*self.CARD_PADDING)
        self.onboarding_layout.setSpacing(8)
        onboarding_copy = QVBoxLayout()
        onboarding_copy.setSpacing(3)
        self.onboarding_step = QLabel("STEP 1 OF 2")
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
        self.onboarding_panel.setMaximumWidth(280)

        hero_card = self._card_frame()
        hero_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        h_layout = QVBoxLayout(hero_card)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(self.CARD_SPACING)
        self.scene = GardenSceneWidget()
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
        self.plant_card.move.clicked.connect(lambda: self._begin_move(self.plant_card.plant_id))
        self.plant_card.story.clicked.connect(lambda: self._open_plant_story(self.plant_card.plant_id))
        self.plant_card.chooseAnother.connect(self._choose_another_plant)
        self.rearrange_bar = RearrangeBar(self.scene)
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
        self.same_day_catchup_note.setAccessibleName("Synced review update")
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

        self.today_list = ProgressList("Today progress")
        self.achievement_list = ProgressCardGrid("Achievement progress")
        self._collection_filter = "all"
        self.collection_list = ProgressCardGrid(
            "Plant collection", wide_columns=3
        )
        self.customize_dialog = CustomizeGardenDialog(
            self,
            self.engine,
            self.storage,
            self._settings_scene_snapshot,
        )
        self.today_summary = QLabel("")
        self.today_summary.setWordWrap(True)
        self._apply_typography(self.today_summary, "muted-body")
        self.today_list.rows.insertWidget(0, self.today_summary)
        self.progress_dialog = GardenProgressDialog(
            self,
            self.engine,
            self.storage,
            self._open_nursery,
            self.today_list,
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
                AdaptiveRegion.measured(
                    "garden-metrics",
                    self.garden_stats_bar,
                    floor=420,
                ),
                AdaptiveRegion.measured(
                    "garden-actions",
                    self.header_actions_widget,
                    floor=300,
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
                AdaptiveRegion.measured(
                    "garden-actions",
                    self.header_actions_widget,
                    floor=300,
                ),
            ),
            spacing=12,
            telemetry_target=self.header_actions_widget,
        )
        self.dashboard_metrics_responsive = AdaptiveRow(
            "dashboard.metrics-density",
            (
                AdaptiveRegion.fixed(
                    "full-metric-copy",
                    760,
                    target=self.garden_stats_bar,
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
        self.progress_dialog.open_page("overview")

    def _open_customize(self) -> None:
        if self.scene._interaction.placing:
            return
        self.scene.dismiss_selection()
        self.customize_dialog.prepare_to_show()
        self.customize_dialog.remember_invoker(self.customize_btn)
        self.customize_dialog.present_over_parent()

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
                f"{displayed_plant.growth_points:,} Growth\nFully grown"
                if progress.fully_grown else
                f"{displayed_plant.growth_points:,} Growth\n"
                f"Needs {progress.points_remaining:,} more to reach "
                f"{format_status_label(progress.next_stage or 'next stage')}"
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

        self._refresh_progress_overview(snapshot, stats, state)

        self.achievement_list.clear()
        achievement_groups = (
            ("Anki streak", lambda key: key.startswith("streak_") or key.startswith("retention_") or key == "no_lapse"),
            ("Garden milestones", lambda key: key.startswith("reviews_") or key == "all_due_done"),
        )
        rendered_achievements: set[str] = set()
        for group_name, belongs in achievement_groups:
            group = [
                (key, achievement) for key, achievement in state.achievements.items()
                if belongs(str(key))
            ]
            if not group:
                continue
            group_heading = QLabel(group_name)
            group_heading.setProperty("categoryTitle", True)
            self.achievement_list.add_full_width(group_heading)
            for achievement_key, ach in group:
                rendered_achievements.add(str(achievement_key))
                display = achievement_progress_display(ach, state)
                achievement_state = (
                    "unlocked" if ach.unlocked else
                    "in_progress" if display.current > 0 else
                    "locked"
                )
                card = QFrame()
                card.setProperty("catalogCard", True)
                card.setProperty("catalogState", achievement_state)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(13, 12, 13, 12)
                card_layout.setSpacing(7)
                heading = QHBoxLayout()
                icon = QLabel("✓" if ach.unlocked else "◌")
                icon.setProperty("catalogIcon", True)
                icon.setFixedSize(44, 44)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setAccessibleName("Achievement unlocked" if ach.unlocked else "Achievement locked")
                title = QLabel(ach.name)
                title.setWordWrap(True)
                title.setProperty("rowTitle", True)
                status = QLabel(
                    "Completed" if ach.unlocked else
                    "In progress" if display.current > 0 else
                    "Locked"
                )
                status.setProperty("catalogStatus", True)
                heading.addWidget(icon)
                heading.addWidget(title, 1)
                heading.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
                card_layout.addLayout(heading)
                criteria = QLabel(display.criteria_text)
                criteria.setWordWrap(True)
                criteria.setProperty("rowCriteria", True)
                card_layout.addWidget(criteria)
                if display.conditions:
                    conditions = QFrame()
                    conditions.setProperty("dataTable", True)
                    condition_layout = QVBoxLayout(conditions)
                    condition_layout.setContentsMargins(0, 0, 0, 0)
                    condition_layout.setSpacing(5)
                    for condition in display.conditions:
                        condition_row = QHBoxLayout()
                        condition_label = QLabel(condition.label)
                        condition_label.setProperty("rowCriteria", True)
                        condition_value = QLabel(
                            f"{'✓ ' if condition.satisfied else ''}{condition.value_text}"
                        )
                        condition_value.setProperty("rowStatus", True)
                        condition_value.setAccessibleName(
                            f"{condition.label}: {condition.value_text}; "
                            f"{'satisfied' if condition.satisfied else 'not yet satisfied'}"
                        )
                        condition_row.addWidget(condition_label, 1)
                        condition_row.addWidget(condition_value)
                        condition_layout.addLayout(condition_row)
                    card_layout.addWidget(conditions)
                else:
                    progress = LabeledProgress(f"{ach.name} progress")
                    progress.set_progress(
                        "Requirement satisfied" if display.completed else "Progress",
                        display.current,
                        display.target,
                        value_text=display.value_text,
                    )
                    card_layout.addWidget(progress)
                if ach.unlocked and getattr(ach, "unlocked_at", None):
                    unlocked = QLabel(f"Completed {self._local_date(ach.unlocked_at)}")
                    unlocked.setProperty("rowCriteria", True)
                    card_layout.addWidget(unlocked)
                card.setAccessibleName(f"{ach.name}. {status.text()}.")
                card.setAccessibleDescription(
                    f"{display.criteria_text} {display.value_text}."
                )
                self.achievement_list.add_card(card)
        for key, ach in state.achievements.items():
            if str(key) in rendered_achievements:
                continue
            display = achievement_progress_display(ach, state)
            fallback = ProgressRow()
            fallback.set_item(
                ach.name,
                display.criteria_text,
                display.current,
                display.target,
                completed=ach.unlocked,
                value_text=display.value_text,
            )
            self.achievement_list.add_card(fallback)
        if not state.achievements:
            DISPLAY_TELEMETRY.track_empty_state(route="dashboard", view="achievement_list", expected_non_empty=bool(state.achievements))
            self.achievement_list.add_empty("No achievements yet", UI_TEXT["no_achievements"])
        self.achievement_list.finish()
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
        self.customize_btn.setAccessibleDescription(
            "New Weather or Scenery is available. Open Customize Garden."
            if environment_new else
            "Choose Weather and Scenery without changing plant placement."
        )
        if self.details_dialog.isVisible():
            self.details_dialog.refresh()
        self._pending_feedback_ack_ids = tuple(event.event_id for event in feedback)
        self._pending_transition_ack = tuple(transitions)
        self._update_scene_height()
        if acknowledge:
            self.acknowledge_rendered_feedback()

    def _refresh_progress_overview(self, snapshot: Any, stats: Any, state: Any) -> None:
        """Compose the Overview as a stable 7/5 dashboard grid."""

        self.today_list.clear()
        coin_delta_today = sum(
            int(transaction.delta)
            for transaction in state.currency_transactions
            if str(getattr(transaction, "occurred_at", ""))[:10] == str(stats.day)[:10]
        )
        self.today_summary = StatSummary([
            ("Card answers", f"{int(stats.reviewed):,}"),
            ("Growth", f"{int(stats.growth_earned):,}"),
            ("Coins earned", f"{coin_delta_today:,}"),
        ])
        self.today_list.add_row(self.today_summary)

        due_status = None
        try:
            resolver = getattr(self.storage, "due_obligations", None)
            due_status = resolver() if callable(resolver) else None
        except Exception:
            logger.debug("Anki Garden: due-card status is unavailable", exc_info=True)
        due_available = bool(getattr(due_status, "available", False))
        due_error = str(getattr(due_status, "error", "") or "")
        remaining = max(0, int(getattr(due_status, "remaining", 0) or 0))
        reward_coins, reward_growth = self.engine.all_due_rewards()

        daily = SectionCard()
        daily_layout = QVBoxLayout(daily)
        daily_layout.setContentsMargins(14, 12, 14, 12)
        daily_layout.setSpacing(8)
        daily_layout.addWidget(QLabel("Daily progress"))
        if not due_available or due_error:
            daily_status = "Due-card status unavailable"
            daily_explanation = due_error or "Refresh after Anki finishes loading the scheduler."
            progress_current = 0
            progress_state = None
        else:
            reward_outcome = (
                f"+{reward_coins:,} Garden Coins"
                + (f" and +{reward_growth:,} Growth" if reward_growth else "")
                + " added automatically."
            )
            progress_state = daily_progress_display(
                remaining,
                reward_complete=bool(stats.completed_due_cards),
                reviewed_today=int(stats.reviewed),
                custom_study_supported=False,
                reward_outcome=reward_outcome,
            )
            daily_status = progress_state.summary
            daily_explanation = progress_state.detail
            progress_current = 1 if progress_state.state == DailyProgressState.COMPLETE else 0
        status = QLabel(daily_status)
        status.setProperty("rowTitle", True)
        status.setWordWrap(True)
        daily_layout.addWidget(status)
        if progress_state is not None and progress_state.state in {
            DailyProgressState.IN_PROGRESS,
            DailyProgressState.COMPLETE,
        }:
            goal_progress = ProgressBar("Daily study goal")
            goal_progress.set_progress(
                "Finish today’s due cards",
                progress_current,
                1,
                value_text=progress_state.status_label,
            )
            daily_layout.addWidget(goal_progress)
        if not (
            progress_state is not None
            and progress_state.state == DailyProgressState.NO_DUE
        ):
            explanation = QLabel(daily_explanation)
            explanation.setProperty("dialogSubtitle", True)
            explanation.setWordWrap(True)
            daily_layout.addWidget(explanation)
        if progress_state is not None and progress_state.state in {
            DailyProgressState.IN_PROGRESS,
            DailyProgressState.COMPLETE,
        }:
            if progress_state.state == DailyProgressState.COMPLETE:
                reward_text = f"Earned automatically: {progress_state.reward_outcome}"
            else:
                reward_text = (
                    f"Automatic reward on completion: +{reward_coins:,} Garden Coins"
                    + (f" and +{reward_growth:,} Growth" if reward_growth else "")
                )
            reward = QLabel(reward_text)
            reward.setProperty("dialogSubtitle", True)
            reward.setWordWrap(True)
            daily_layout.addWidget(reward)
        if progress_state is not None:
            if progress_state.action_enabled and progress_state.action_kind == "review":
                continue_studying = QPushButton(progress_state.action_label or "Continue studying")
                _set_button_variant(continue_studying, BUTTON_VARIANT_PRIMARY)
                continue_studying.setAccessibleDescription(
                    "Close Garden Progress and the Garden to return to Anki."
                )
                continue_studying.clicked.connect(
                    lambda: (self.progress_dialog.close(), self.close())
                )
                daily_layout.addWidget(continue_studying, 0, Qt.AlignmentFlag.AlignLeft)

        active_plant = self.engine.active_plant()
        if active_plant is None:
            choose = QPushButton("Choose plant")
            _set_button_variant(choose, BUTTON_VARIANT_PRIMARY)
            choose.clicked.connect(self._choose_another_plant)
            plant_card: QWidget = EmptyState(
                "No nurtured plant",
                "Choose an unfinished plant so Anki card answers have somewhere to add Growth.",
                action=choose,
            )
        else:
            display = growth_display(active_plant.growth_points)
            plant_card = SectionCard()
            plant_layout = QVBoxLayout(plant_card)
            plant_layout.setContentsMargins(14, 12, 14, 12)
            plant_layout.setSpacing(7)
            identity = QHBoxLayout()
            identity.addWidget(_asset_preview_label(
                self.engine,
                active_plant.species,
                active_plant.growth_stage,
                size=72,
            ))
            copy = QVBoxLayout()
            title = QLabel(active_plant.name)
            title.setProperty("rowTitle", True)
            stage = QLabel(format_status_label(display.stage))
            stage.setProperty("dialogSubtitle", True)
            copy.addWidget(title)
            copy.addWidget(stage)
            identity.addLayout(copy, 1)
            plant_layout.addLayout(identity)
            plant_progress = ProgressBar("Nurtured plant progress")
            plant_progress.set_progress(
                "Rare stage" if display.fully_grown else "Growth progress",
                1 if display.fully_grown else display.stage_points,
                1 if display.fully_grown else max(1, display.stage_goal),
                value_text="Fully grown" if display.fully_grown else f"{display.stage_points:,} / {display.stage_goal:,}",
            )
            plant_layout.addWidget(plant_progress)
            open_growth = QPushButton("Open Plant Growth")
            _set_button_variant(open_growth, BUTTON_VARIANT_TERTIARY)
            open_growth.clicked.connect(lambda: self._open_metric_details("growth"))
            plant_layout.addWidget(open_growth, 0, Qt.AlignmentFlag.AlignLeft)
        self.today_list.add_row(
            ResponsiveSplit(daily, plant_card, breakpoint=620)
        )

        recent = SectionCard()
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(14, 12, 14, 12)
        recent_layout.setSpacing(6)
        recent_title = QLabel("Recent rewards")
        recent_title.setProperty("rowTitle", True)
        recent_layout.addWidget(recent_title)
        recent_transactions = list(reversed(state.currency_transactions[-3:]))
        if not recent_transactions:
            recent_layout.addWidget(EmptyState(
                "No rewards yet",
                "Rewards from milestones, plant stages, and study goals will appear here.",
            ))
        for transaction in recent_transactions:
            row = QFrame()
            row.setProperty("detailRow", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(3, 7, 3, 7)
            reason = QLabel(str(transaction.reason))
            reason.setWordWrap(True)
            amount = QLabel(f"{'+' if transaction.delta >= 0 else '−'}{abs(int(transaction.delta)):,}")
            amount.setProperty(
                "detailPositive" if int(transaction.delta) >= 0 else "detailNegative",
                True,
            )
            apply_tabular_numerals(amount)
            row_layout.addWidget(reason, 1)
            row_layout.addWidget(amount)
            recent_layout.addWidget(row)
        recent_layout.addStretch(1)

        milestone = SectionCard()
        milestone_layout = QVBoxLayout(milestone)
        milestone_layout.setContentsMargins(14, 12, 14, 12)
        milestone_layout.setSpacing(7)
        milestone_title = QLabel("Next rewards")
        milestone_title.setProperty("rowTitle", True)
        milestone_layout.addWidget(milestone_title)
        has_next_reward = False
        if active_plant is not None:
            display = growth_display(active_plant.growth_points)
            if not display.fully_grown:
                next_stage = str(display.next_stage or "")
                stage_reward = max(0, int(self.engine.STAGE_CURRENCY.get(next_stage, 0) or 0))
                stage_reward_label = QLabel(
                    f"{format_status_label(next_stage)} stage reward: "
                    f"+{stage_reward:,} Garden Coins"
                )
                stage_reward_label.setProperty("dialogSubtitle", True)
                stage_reward_label.setWordWrap(True)
                apply_tabular_numerals(stage_reward_label)
                milestone_layout.addWidget(stage_reward_label)
                has_next_reward = True
        else:
            milestone_layout.addWidget(QLabel("Nurture a plant to reveal its next stage reward."))
            has_next_reward = True
        next_streak = next(
            ((day, percent) for day, percent in STREAK_BONUS_TIERS if state.streak_days < day),
            None,
        )
        if next_streak is not None:
            day, percent = next_streak
            streak_reward = QLabel(
                f"Streak reward: +{percent}% Growth at {_day_count(day)}"
            )
            streak_reward.setProperty("dialogSubtitle", True)
            streak_reward.setWordWrap(True)
            apply_tabular_numerals(streak_reward)
            milestone_layout.addWidget(streak_reward)
            has_next_reward = True
        if not has_next_reward:
            milestone_layout.addWidget(QLabel("All current stage and Anki streak rewards reached."))
        milestone_layout.addStretch(1)
        self.today_list.add_row(
            ResponsiveSplit(recent, milestone, breakpoint=620)
        )
        self.today_list.finish()

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
        if plant is None:
            self._update_scene_height()
        self._position_plant_card()

    def _on_landmark_activated(self, action_id: str) -> None:
        action = str(action_id)
        handlers = {
            "garden.nursery.open": self._open_nursery,
            "garden.progress.open": self._open_progress,
        }
        handler = handlers.get(action)
        if handler is not None:
            if action == "garden.nursery.open" and self._derived_ux_state() != UX_NO_STARTER:
                self._complete_onboarding()
            handler()

    def _open_nursery(self, tab_index: int = 0, *, status_message: str = "") -> None:
        if self.scene._interaction.placing:
            return
        if self.details_dialog.isVisible():
            self.details_dialog.close()
        self.scene.dismiss_selection()
        self.nursery_dialog = NurseryDialog(self, self.engine, self.storage)
        self.nursery_dialog.catalog_tabs.setCurrentIndex(
            max(0, min(3, int(tab_index)))
        )
        if status_message:
            self.nursery_dialog._show_result(True, status_message)
        self.nursery_dialog.exec()
        if not bool(getattr(self.storage.state, "starter_selection_complete", True)):
            self._starter_prompt_scheduled = False
        self._refresh_after_commit("Nursery dialog")

    def _open_starter_nursery(self) -> None:
        """Shared direct route for every pre-starter call to action."""

        self._starter_setup_dismissed = False
        self._open_nursery(0)

    def _show_nursery_landmark(self) -> None:
        # Landmark emphasis is supplementary; the actionable route is always
        # the same direct Nursery opener used by the Home and header CTAs.
        self.scene.focus_landmark("garden.nursery.open")
        self._open_starter_nursery()

    def _activate_onboarding_action(self) -> None:
        if self._derived_ux_state() == UX_NO_STARTER:
            self._show_nursery_landmark()
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
        config = getattr(self, "config", None)
        onboarding_version = (
            int(config.value("onboarding_version", 0) or 0)
            if config is not None and hasattr(config, "value") else CURRENT_ONBOARDING_VERSION
        )
        guided = ux_state in {UX_NO_STARTER, UX_STARTER_READY} and (
            ux_state == UX_NO_STARTER or onboarding_version < CURRENT_ONBOARDING_VERSION
        )
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
            margins = self.dashboard_page.layout().contentsMargins()
            content_width = max(
                0,
                int(event.size().width()) - margins.left() - margins.right(),
            )
            self._apply_responsive_layout(content_width)
        self._update_scene_height(event.size().height())
        QTimer.singleShot(0, self._position_plant_card)
        QTimer.singleShot(0, self._position_onboarding_coachmark)
        QTimer.singleShot(0, self._position_scene_overlays)
        super().resizeEvent(event)

    def _position_scene_overlays(self) -> None:
        if not hasattr(self, "scene"):
            return
        inset = 20
        top = inset
        if self.rearrange_bar.isVisible():
            bar_width = min(620, max(240, self.scene.width() - (inset * 2)))
            self.rearrange_bar.setFixedWidth(bar_width)
            self.rearrange_bar.adjustSize()
            bar_height = min(96, max(56, self.rearrange_bar.sizeHint().height()))
            self.rearrange_bar.setGeometry(
                max(inset, (self.scene.width() - bar_width) // 2),
                inset,
                bar_width,
                bar_height,
            )
            self.rearrange_bar.raise_()
            top = inset + bar_height + 8
        if self.toast_region.isVisible():
            toast_width = min(360, max(240, self.scene.width() - (inset * 2)))
            self.toast_region.setFixedWidth(toast_width)
            self.toast_region.adjustSize()
            toast_height = min(124, max(56, self.toast_region.sizeHint().height()))
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
            self.toast_region.setGeometry(
                max(inset, min(toast_x, self.scene.width() - toast_width - inset)),
                top,
                toast_width,
                toast_height,
            )
            self.toast_region.raise_()

    def _position_onboarding_coachmark(self) -> None:
        if not hasattr(self, "onboarding_panel") or not self.onboarding_panel.isVisible():
            return
        width = min(280, max(240, self.scene.width() - 24))
        self.onboarding_panel.setFixedWidth(width)
        self.onboarding_panel.adjustSize()
        height = max(
            104,
            min(self.onboarding_panel.sizeHint().height(), max(112, self.scene.height() - 24)),
        )
        step_two = self.onboarding_step.text() == "STEP 2 OF 2"
        anchor_geometry = (
            self.scene.plant_geometry(self._onboarding_plant_id)
            if step_two and self._onboarding_plant_id else
            self.scene.landmark_geometry("garden.nursery.open")
        )
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

    def _apply_responsive_layout(self, width: int) -> None:
        available = max(0, int(width))
        if not hasattr(self, "dashboard_header_full"):
            return
        full_header = self.dashboard_header_full.evaluate(available)
        title_actions = self.dashboard_header_title_actions.evaluate(available)
        metrics = self.dashboard_metrics_responsive.evaluate(available)
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
        elif header_compact:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0)
            self.header_grid.addWidget(self.header_actions_widget, 0, 1)
            self.header_grid.addWidget(self.garden_stats_bar, 1, 0, 1, 2)
            self.header_grid.setColumnStretch(0, 1)
            self.header_grid.setColumnStretch(1, 0)
            self.header_grid.setColumnStretch(2, 0)
        else:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0)
            self.header_grid.addWidget(self.garden_stats_bar, 0, 1)
            self.header_grid.addWidget(self.header_actions_widget, 0, 2)
            self.header_grid.setColumnStretch(0, 0)
            self.header_grid.setColumnStretch(1, 1)
            self.header_grid.setColumnStretch(2, 0)
        self._sync_header_minimum_heights()
        self.top_bar.updateGeometry()
        self.header_grid.activate()
        self.top_bar.adjustSize()

    def _sync_header_minimum_heights(self) -> None:
        """Keep first-run status compact without weakening active metrics."""

        guided = bool(getattr(self.garden_stats_bar, "_onboarding_mode", False))
        metrics_compact = bool(self._header_metrics_compact)
        self.garden_stats_bar.setMinimumHeight(
            64 if guided else (96 if metrics_compact else 104)
        )
        if guided:
            minimum = (
                154 if self._header_narrow_layout else
                128 if self._header_compact_layout else
                88
            )
        else:
            minimum = (
                224 if self._header_narrow_layout else
                168 if self._header_compact_layout and metrics_compact else
                176 if self._header_compact_layout else
                112
            )
        self.top_bar.setMinimumHeight(minimum)

    def _set_plant_card_mode(self, compact: bool) -> None:
        del compact
        # Actual side-card vs bottom-sheet placement depends on scene width,
        # not the broader dashboard chrome breakpoint.
        QTimer.singleShot(0, self._position_plant_card)

    def _show_docked_plant_card(self, *, full_width: bool) -> None:
        """Keep selection details reachable when no safe in-scene lane exists."""

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
        card_width = available_width if full_width else min(640, available_width)
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
            self.plant_card.setMaximumWidth(330)
        available_width = max(280, self.scene.width() - 24)
        desired_width = min(320, available_width)
        self.plant_card.setFixedWidth(desired_width)
        self.plant_card.adjustSize()
        # Qt's wrapped-label size hint can settle before the two-row action
        # grid has received its final width. Reserve the grid's vertical gap
        # so 125–150% font scaling never compresses the 40 px plant action targets.
        action_grid_reserve = 24
        action_height_reserve = (
            72 if self.plant_card.choose_another.isVisible() else action_grid_reserve
        )
        desired_height = min(
            420,
            max(220, self.plant_card.sizeHint().height() + action_height_reserve),
        )
        card_height = min(
            desired_height,
            max(220, self.scene.height() - 24),
        )
        geometry = self.scene.card_geometry(self.plant_card.width(), card_height)
        if geometry is None:
            # A dense mature scene can leave no overlay lane that protects the
            # selected plant. Preserve the user's selection in a docked card
            # instead of silently making every action disappear.
            self._show_docked_plant_card(full_width=False)
            return
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
        for payload in self.scene.scene.get("plants", []):
            if str(payload.get("plant_id", "")) == str(selected):
                self.plant_card.set_selected(dict(payload))
                self._position_plant_card()
                return
        plant = self.engine.plant_story(selected)
        if plant is None or not plant.planted:
            self.scene.dismiss_selection()
            return
        self.plant_card.set_selected(self._plant_scene_payload(plant))
        self._position_plant_card()

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
        if self.scene._interaction.placing:
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
        staged_slots = self._placement_draft.scene_slots() if self._placement_draft is not None else {}
        fertilizer_growth = self.engine.fertilizer_growth(plant)
        booster_growth = self.engine.booster_growth(plant)
        reviews_remaining = self.engine.progress_estimates(plant)
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
            "growth_today": self.storage.state.daily_stats.plant_growth.get(plant.plant_id, 0),
            "reviews_remaining": reviews_remaining,
            "fertilizer_text": self._fertilizer_text(plant),
            "booster_text": self._booster_text(plant),
            "is_active": plant.plant_id == self.storage.state.active_plant_id,
            "asset": self._resolved_asset_payload(
                "resolve_plant_asset",
                "resolve_plant_image",
                plant.species,
                plant.growth_stage,
            ),
        }

    def _settings_scene_snapshot(self) -> dict[str, Any]:
        state = self.storage.state
        active = self.engine.active_plant()
        active_progress = growth_display(active.growth_points).progress if active is not None else 0.0
        return {
            "garden_name": str(getattr(state, "garden_name", "My Garden") or "My Garden"),
            "weather": state.selected_weather,
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
        fertilizer = getattr(plant, "fertilizer", None)
        if fertilizer is None:
            return "No active Fertilizer"
        remaining = max(0, int(float(fertilizer.expires_at) - time.time()))
        if remaining <= 0:
            return "No active Fertilizer"
        spec = self.engine.FERTILIZERS.get(str(fertilizer.tier))
        name = spec.name if spec is not None else format_status_label(fertilizer.tier)
        if remaining < 60:
            return (
                f"{name}: +{int(fertilizer.growth_per_answer)} Growth per Anki card answer\n"
                "Less than 1 minute remaining"
            )
        total_minutes = (remaining + 59) // 60
        hours, minutes = divmod(total_minutes, 60)
        duration = (
            f"{hours}h {minutes}m" if hours and minutes
            else f"{hours}h" if hours
            else f"{minutes}m"
        )
        return (
            f"{name}: +{int(fertilizer.growth_per_answer)} Growth per Anki card answer\n"
            f"{duration} remaining"
        )

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
        toast_copy = (
            f"{selected_name} is now nurtured\n"
            "Future Anki card answers will add Growth here."
        )
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
        self._open_nursery(status_message=ALL_PLANTS_COMPLETE)

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
        move_message = "Choose a highlighted garden bed. Press Esc to cancel."
        self.rearrange_bar.plant_id = plant_id
        self.rearrange_bar.title.setText(f"Moving {name}")
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
        occupied_slots = {
            int(slot) for occupant_id, slot in scene_slots.items()
            if occupant_id != plant_id
        }
        empty_destinations = [
            int(slot) for slot in self.engine.valid_destination_slots(draft)
            if int(slot) not in occupied_slots and int(slot) != origin_slot
        ]
        if not empty_destinations:
            self._placement_draft = None
            self.toast_region.show_message(
                "No empty garden space is available. Shelve a plant before moving this one.",
                error=True,
                duration_ms=4500,
            )
            return
        allowed_slots = ([int(origin_slot)] if origin_slot is not None else []) + empty_destinations
        if self.scene.begin_move(plant_id, allowed_slots):
            self.rearrange_bar.show()
            self.scene.setFocus()
            QTimer.singleShot(0, self._position_scene_overlays)
        else:
            self._placement_draft = None

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
                f"Space {slot + 1} — empty",
                slot,
            )
            for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
            if slot != current_slot and slot in valid_slots and slot not in occupied
        ])

    def _cancel_move(self) -> None:
        selected_id = str(
            getattr(self._placement_draft, "selected_plant_id", "") or ""
        )
        self._placement_draft = None
        self.scene.finish_move("Move cancelled. Plant selection remains available.")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: move cancelled but persisted scene did not refresh")
        self.toast_region.clear()
        if selected_id:
            self.scene.keep_card_open(selected_id)
            self._refresh_selected_plant_card()
            QTimer.singleShot(0, self.plant_card.move.setFocus)

    def _finish_failed_move(self, message: str) -> None:
        """Return the scene to persisted state after any terminal move error."""
        message = _learner_text(message)
        selected_id = str(
            getattr(self._placement_draft, "selected_plant_id", "") or ""
        )
        self._placement_draft = None
        self.scene.finish_move(f"Move not saved. {message}")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: rejected move could not refresh persisted scene")
        self.scene.setFocus()
        if selected_id:
            self.scene.keep_card_open(selected_id, message)
            self._refresh_selected_plant_card()
        self.toast_region.show_message(message, error=True, duration_ms=0)
        self.toast_region.setFocus()

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
        self.scene.setFocus()

    def _apply_native_destination(self) -> None:
        destination = self.rearrange_bar.selected_destination()
        if destination is None or not self.rearrange_bar.plant_id:
            return
        self._place_plant(self.rearrange_bar.plant_id, destination)

    def _place_plant(self, plant_id: str, destination_slot: int) -> None:
        draft = self._placement_draft
        if draft is None or draft.selected_plant_id != plant_id:
            self._finish_failed_move("That move session is no longer available.")
            return
        before_slots = draft.scene_slots()
        origin_slot = before_slots.get(plant_id)
        moving = next((p for p in self.storage.state.plants if p.plant_id == plant_id), None)
        occupant_id = next((pid for pid, slot in before_slots.items() if slot == destination_slot), None)
        occupant = next((p for p in self.storage.state.plants if p.plant_id == occupant_id), None)
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
        self.scene.setFocus()

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
                self.scene.begin_move(
                    plant_id,
                    self.engine.valid_destination_slots(self._placement_draft),
                )
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
        starter_incomplete = display.state in {
            OnboardingState.NO_STARTER,
            OnboardingState.STARTER_SELECTED,
        }
        nurture_step = display.state == OnboardingState.STARTER_PLANTED_NOT_NURTURED
        guided = starter_incomplete or nurture_step
        self.starter_header_btn.setVisible(
            starter_incomplete and self._starter_setup_dismissed
        )
        self.progress_btn.setVisible(not guided)
        self.customize_btn.setVisible(not guided)
        self.settings_btn.setVisible(not guided)
        self.garden_stats_bar.set_onboarding_mode(guided)
        self._sync_header_minimum_heights()
        self.top_bar.updateGeometry()
        if starter_incomplete:
            visible = not self._starter_setup_dismissed
            self.onboarding_panel.setVisible(visible)
            self.plant_card.set_onboarding_guidance(False)
            if not visible:
                return
            self.onboarding_step.setText("STEP 1 OF 2")
            title = GARDEN_SETUP_TITLE
            message = self._onboarding_save_error or GARDEN_SETUP_BODY
            action_text = CHOOSE_STARTER_ACTION
            dismiss_text = GARDEN_SETUP_SECONDARY_ACTION
            self.onboarding_title.setText(title)
            self.onboarding_message.setText(message)
            self.onboarding_action.setText(action_text)
            self.onboarding_action.setVisible(True)
            self.dismiss_onboarding.setText(dismiss_text)
            self.dismiss_onboarding.setVisible(True)
            self.onboarding_panel.setAccessibleDescription(f"{title}. {message}")
            QTimer.singleShot(0, self._position_onboarding_coachmark)
            return

        if nurture_step:
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
            self.onboarding_panel.setVisible(visible)
            if visible:
                self.onboarding_step.setText("STEP 2 OF 2")
                self.onboarding_title.setText(GARDEN_NURTURE_TITLE)
                self.onboarding_message.setText(GARDEN_NURTURE_BODY)
                self.onboarding_action.setText(GARDEN_NURTURE_ACTION)
                self.onboarding_action.show()
                self.dismiss_onboarding.setText(GARDEN_SETUP_SECONDARY_ACTION)
                self.dismiss_onboarding.show()
                self.onboarding_panel.setAccessibleDescription(
                    f"Step 2 of 2. {GARDEN_NURTURE_TITLE}. {GARDEN_NURTURE_BODY}"
                )
                QTimer.singleShot(0, self._position_onboarding_coachmark)
            return

        # Once a starter exists, feedback belongs to transient toasts and the
        # metric strip. A permanent coachmark would compete with the garden.
        self.onboarding_panel.hide()
        self.plant_card.set_onboarding_guidance(False)

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
                QTimer.singleShot(0, self.plant_card.nurture.setFocus)
            QTimer.singleShot(0, open_nurture_step)

    def _complete_onboarding(self) -> bool:
        if int(self.config.value("onboarding_version", 0) or 0) >= CURRENT_ONBOARDING_VERSION:
            return True
        try:
            self.config.update({"onboarding_version": CURRENT_ONBOARDING_VERSION})
        except ConfigError:
            logger.warning("Anki Garden: could not persist the onboarding preference", exc_info=True)
            self._onboarding_save_error = (
                "The tip could not be saved yet. It will remain available until Anki can save it."
            )
            self._refresh_onboarding()
            return False
        self._onboarding_save_error = ""
        return True

    def _dismiss_onboarding(self) -> None:
        if self._derived_ux_state() in {UX_NO_STARTER, UX_STARTER_READY}:
            self._starter_setup_dismissed = True
            self._refresh_onboarding()
            return
        if self._complete_onboarding():
            self._onboarding_confirmation_generation += 1
            self._onboarding_just_completed = False
            self._refresh_onboarding()

    def _complete_first_nurture_guidance(self) -> None:
        self._onboarding_just_completed = False
        self._starter_setup_dismissed = False
        self.plant_card.set_onboarding_guidance(False)
        if self._complete_onboarding():
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
        ok, message, _plant = self.engine.purchase_species(species)
        if ok:
            self._refresh_after_commit("plant purchase")
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, UI_TEXT["app_title"], _learner_text(message)
        )

    def _purchase_bed(self) -> None:
        ok, message = self.engine.purchase_next_bed()
        if ok:
            self._refresh_after_commit("garden-space purchase")
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, UI_TEXT["app_title"], _learner_text(message)
        )

    def _refresh_collection_list(self) -> None:
        self.collection_list.clear()
        state = self.storage.state
        summary = self.engine.catalog_summary()
        species_catalog = list(summary.get("release_ready_species", []))
        owned_species = {
            str(species)
            for species in summary.get("owned_species", [])
        }
        discovered = len([species for species in species_catalog if species in owned_species])
        header = SectionCard()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 11, 14, 11)
        count = QLabel(f"{discovered} of {len(species_catalog)} species discovered")
        count.setProperty("rowTitle", True)
        count.setWordWrap(True)
        header_layout.addWidget(count, 1)
        for key, label in (("all", "All"), ("discovered", "Discovered"), ("locked", "Locked")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(self._collection_filter == key)
            _set_button_variant(button, BUTTON_VARIANT_TERTIARY)
            button.setAccessibleDescription(f"Show {label.lower()} collection entries.")
            button.clicked.connect(
                lambda _checked=False, selected=key: self._set_collection_filter(selected)
            )
            header_layout.addWidget(button)
        self.collection_list.add_full_width(header)

        stage_rank = {stage: index for index, stage in enumerate(GROWTH_STAGES)}
        rendered = 0
        for species in species_catalog:
            discovered_species = species in owned_species
            if self._collection_filter == "discovered" and not discovered_species:
                continue
            if self._collection_filter == "locked" and discovered_species:
                continue
            instances = [plant for plant in state.plants if plant.species == species]
            highest = max(
                instances,
                key=lambda plant: stage_rank.get(str(plant.growth_stage), 0),
                default=None,
            )
            highest_stage = str(highest.growth_stage) if highest is not None else "seed"
            card: QWidget
            if discovered_species:
                button = QPushButton()
                button.setProperty("catalogCard", True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda _checked=False, selected=species:
                    self._open_species_overview(selected)
                )
                card = button
            else:
                frame = QFrame()
                frame.setProperty("catalogCard", True)
                frame.setAccessibleName("Undiscovered plant species")
                card = frame
            card.setMinimumHeight(224)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            layout = QVBoxLayout(card)
            layout.setContentsMargins(10, 9, 10, 10)
            layout.setSpacing(6)
            if discovered_species:
                artwork = _asset_preview_label(
                    self.engine, species, highest_stage, size=104
                )
            else:
                artwork = QLabel("?")
                artwork.setFixedSize(104, 104)
                artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
                artwork.setProperty("stagePreview", True)
                artwork.setStyleSheet(
                    "background:#101915; color:#58675f; border:0; border-radius:12px; "
                    "font-size:42px; font-weight:800;"
                )
                artwork.setAccessibleName("Undiscovered species silhouette")
            layout.addWidget(artwork, 0, Qt.AlignmentFlag.AlignHCenter)
            title = QLabel(
                format_status_label(species)
                if discovered_species else
                "Undiscovered species"
            )
            title.setProperty("rowTitle", True)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setWordWrap(True)
            status = QLabel(
                f"Highest stage: {format_status_label(highest_stage)}"
                if discovered_species else
                "Locked · Discover through the Nursery"
            )
            status.setProperty("rowCriteria", True)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(status)
            for child in card.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if discovered_species:
                card.setAccessibleName(
                    f"{format_status_label(species)}, discovered, highest stage {format_status_label(highest_stage)}"
                )
                card.setAccessibleDescription(
                    "Open the species overview. Plant Story remains specific to one planted instance."
                )
            self.collection_list.add_card(card)
            rendered += 1
        if rendered == 0:
            clear_filters = QPushButton("Clear filters")
            _set_button_variant(clear_filters, BUTTON_VARIANT_PRIMARY)
            clear_filters.setAccessibleDescription(
                "Show the complete plant collection."
            )
            clear_filters.clicked.connect(lambda: self._set_collection_filter("all"))
            self.collection_list.add_full_width(EmptyState(
                "No plants match these filters",
                "Choose another filter or show the complete collection.",
                action=clear_filters,
            ))
        self.collection_list.finish()

    def _set_collection_filter(self, selected: str) -> None:
        self._collection_filter = selected if selected in {"all", "discovered", "locked"} else "all"
        self._refresh_collection_list()

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
        instances = [
            plant for plant in self.storage.state.plants
            if str(plant.species) == str(species)
        ]
        if not instances:
            return None
        stage_rank = {stage: index for index, stage in enumerate(GROWTH_STAGES)}
        highest = max(
            instances,
            key=lambda plant: stage_rank.get(str(plant.growth_stage), 0),
        )
        dialog = GardenDialog(
            parent or self.progress_dialog,
            format_status_label(species),
            subtitle="Species overview",
        )
        dialog.apply_size_policy(
            DialogSizeClass.STANDARD_TEXT,
            preferred_width=760,
            preferred_height=620,
        )
        dialog.setProperty("windowFamily", "SpeciesOverviewDialog")
        dialog.setProperty("layoutMode", "default")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Species overview details")
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)
        hero = SectionCard()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        hero_layout.addWidget(
            _asset_preview_label(
                self.engine, species, highest.growth_stage, size=104
            )
        )
        facts = QLabel(
            f"Highest stage: {format_status_label(highest.growth_stage)}\n"
            f"Discovered: {self._local_date(min(plant.planted_on for plant in instances))}\n"
            f"Current planted instances: {sum(1 for plant in instances if plant.planted):,}"
        )
        facts.setWordWrap(True)
        facts.setProperty("dialogSubtitle", True)
        hero_layout.addWidget(facts, 1)
        layout.addWidget(hero)
        stages = QHBoxLayout()
        highest_index = stage_rank.get(str(highest.growth_stage), 0)
        for index, stage in enumerate(GROWTH_STAGES):
            if index > highest_index:
                break
            stages.addWidget(
                _asset_preview_label(self.engine, species, stage, size=64)
            )
        layout.addLayout(stages)
        instances_title = QLabel("Collected plants")
        instances_title.setProperty("dialogTitle", True)
        layout.addWidget(instances_title)
        for plant in instances:
            location = f"Garden bed {plant.slot_index + 1}" if plant.planted else "Shelved"
            row = QLabel(
                f"{plant.name} · {format_status_label(plant.growth_stage)} · {location}"
            )
            row.setProperty("dialogSubtitle", True)
            row.setWordWrap(True)
            layout.addWidget(row)
        layout.addStretch(1)
        scroll.setWidget(body)
        _set_scroll_surface(scroll, body, GARDEN_THEME["dialog_surface"])
        dialog.set_body_widget(scroll)
        return dialog

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
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(11)
        row.addWidget(self._environment_collection_artwork(
            item,
            silhouette=bool(item.drop_only and not owned),
        ))
        copy = QVBoxLayout()
        title = QLabel(
            f"{item.name} — {item.rarity}"
            + (" — Equipped" if equipped else "")
        )
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setProperty("rowTitle", True)
        effect = QLabel(
            f"Passive: {item.effect}\nHow to earn: {item.how_to_earn}"
        )
        effect.setTextFormat(Qt.TextFormat.PlainText)
        effect.setWordWrap(True)
        effect.setProperty("rowCriteria", True)
        copy.addWidget(title)
        copy.addWidget(effect)
        row.addLayout(copy, 1)
        action = QPushButton(
            "Equipped" if equipped else
            "Equip" if owned else
            "Available in Nursery" if item.purchasable else
            "Not discovered"
        )
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if owned and not equipped else BUTTON_VARIANT_SECONDARY,
        )
        action.setAccessibleDescription(
            f"Equip {item.name}. Its passive applies even if the visual layer is hidden."
            if owned and not equipped else
            f"{item.name} is currently equipped."
            if equipped else
            item.how_to_earn
        )
        set_control_enabled(
            action,
            owned and not equipped,
            disabled_reason=action.accessibleDescription(),
            enabled_description=action.accessibleDescription(),
        )
        action.clicked.connect(
            lambda _checked=False, kind=item.kind, item_id=item.item_id:
            self._equip_environment(kind, item_id)
        )
        row.addWidget(action)
        return card

    def _refresh_environment_collection(self) -> None:
        self._clear_layout(self.environment_collection_layout)
        state = self.storage.state
        weather = WEATHER_CATALOG.get(
            state.selected_weather, WEATHER_CATALOG["sunny"]
        )
        scenery = SCENERY_CATALOG.get(
            state.selected_background, SCENERY_CATALOG["default"]
        )
        heading = QLabel("Your environment loadout")
        self._apply_typography(heading, "section-title")
        self.environment_collection_layout.addWidget(heading)
        loadout = QLabel(
            f"Weather: {weather.name} — {weather.effect}\n"
            f"Scenery: {scenery.name} — {scenery.effect}\n"
            "Only equipped passives apply. Weather and Scenery passives stack."
        )
        loadout.setTextFormat(Qt.TextFormat.PlainText)
        loadout.setWordWrap(True)
        self._apply_typography(loadout, "muted-body")
        self.environment_collection_layout.addWidget(loadout)
        visibility = QFrame()
        visibility.setProperty("progressRow", True)
        visibility_layout = QHBoxLayout(visibility)
        visibility_layout.setContentsMargins(10, 8, 10, 8)
        visibility_copy = QLabel(
            "Visual layers\nHiding artwork never disables its equipped passive."
        )
        visibility_copy.setTextFormat(Qt.TextFormat.PlainText)
        visibility_copy.setWordWrap(True)
        visibility_copy.setProperty("rowCriteria", True)
        visibility_layout.addWidget(visibility_copy, 1)
        show_weather = QCheckBox("Show Weather")
        show_weather.setChecked(bool(
            state.environment_visibility.get("weather", True)
        ))
        show_weather.setAccessibleDescription(
            "Show or hide only the equipped Weather artwork."
        )
        show_weather.toggled.connect(
            lambda enabled: self._set_environment_visibility("weather", enabled)
        )
        show_scenery = QCheckBox("Show Scenery")
        show_scenery.setChecked(bool(
            state.environment_visibility.get("scenery", True)
        ))
        show_scenery.setAccessibleDescription(
            "Show the equipped Scenery, or display Verdant Twilight while keeping its passive."
        )
        show_scenery.toggled.connect(
            lambda enabled: self._set_environment_visibility("scenery", enabled)
        )
        visibility_layout.addWidget(show_weather)
        visibility_layout.addWidget(show_scenery)
        self.environment_collection_layout.addWidget(visibility)

        for section_name, catalog in (
            ("Weather collection", WEATHER_CATALOG),
            ("Scenery collection", SCENERY_CATALOG),
        ):
            section = QLabel(section_name)
            self._apply_typography(section, "section-title")
            self.environment_collection_layout.addWidget(section)
            for item in catalog.values():
                self.environment_collection_layout.addWidget(
                    self._environment_collection_card(item)
                )

        odds = self.engine.environment_drop_odds()
        odds_rows = [
            (
                "Eligibility",
                "Each Anki card answer after choosing a starter checks these bands in order; at most one reward can win. A daily scenery gift uses that answer's reward slot.",
            ),
            (
                "Reward bands",
                "; ".join(
                    f"{row['name']}: 1 in {row['denominator']:,}"
                    for row in odds.get("bands", [])
                ),
            ),
            (
                "Ultra pity",
                (
                    f"{int(odds.get('ultra_pity_misses', 0)):,} misses; current Ultra chance "
                    f"1 in {int(odds.get('ultra_denominator', 100000)):,}. The denominator improves "
                    "to 90,000 at 75,000 misses, then 80,000 at 85,000, 70,000 at 95,000, "
                    "60,000 at 105,000, and 50,000 at 115,000. There is no guaranteed drop; "
                    "only an Ultra-band hit resets pity."
                ),
            ),
            (
                "Completed tiers",
                "Tier choice is uniform among unowned items. Once a tier is complete, Rare becomes a Standard Charge; Very Rare and Ultra Rare become a Grand Charge.",
            ),
        ]
        self.environment_collection_layout.addWidget(
            DisclosureRow(REWARD_DISCLOSURE, odds_rows, expanded=False)
        )
        self.environment_collection_layout.addStretch(1)

    def _equip_environment(self, kind: str, item_id: str) -> None:
        ok, message = self.engine.equip_environment(kind, item_id)
        if ok:
            self._refresh_after_commit("environment loadout")
        self.status_notice.setText(_learner_text(message))
        self.status_notice.setAccessibleDescription(_learner_text(message))
        self.status_notice.setStyleSheet("color:#baf3c6;" if ok else "color:#ffd0d0;")
        self.status_notice.show()
        self.accessibility_announcer.announce(
            _learner_text(message),
            priority=(
                AnnouncementPriority.POLITE
                if ok
                else AnnouncementPriority.ASSERTIVE
            ),
            target=self,
        )
        self._sync_feedback_panel_visibility()
        self._update_scene_height()

    def _set_environment_visibility(self, kind: str, enabled: bool) -> None:
        ok, message = self.engine.set_environment_visibility(kind, enabled)
        if ok:
            self._refresh_after_commit("environment visibility")
        self.status_notice.setText(_learner_text(message))
        self.status_notice.setAccessibleDescription(_learner_text(message))
        self.status_notice.setStyleSheet("color:#baf3c6;" if ok else "color:#ffd0d0;")
        self.status_notice.show()
        self.accessibility_announcer.announce(
            _learner_text(message),
            priority=(
                AnnouncementPriority.POLITE
                if ok
                else AnnouncementPriority.ASSERTIVE
            ),
            target=self.status_notice,
        )
        self._sync_feedback_panel_visibility()
        self._update_scene_height()

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
            DialogSizeClass.STANDARD_TEXT,
            preferred_width=760,
            preferred_height=620,
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
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel(f"Fertilize {plant.name}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:22px; font-weight:800;")
        hero = QFrame()
        hero.setProperty("fertilizerHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(_asset_preview_label(
            self.engine, plant.species, plant.growth_stage, size=68
        ))
        identity = QVBoxLayout()
        identity.setSpacing(3)
        identity_name = QLabel(plant.name)
        identity_name.setProperty("fertilizerTitle", True)
        identity.addWidget(identity_name)
        subtitle = QLabel(
            f"{format_status_label(plant.species)} · "
            f"{format_status_label(plant.growth_stage)} Stage"
        )
        subtitle.setProperty("fertilizerMeta", True)
        identity.addWidget(subtitle)
        fertilizer_intro = QLabel(
            "Choose a timed Growth boost for Anki card answers."
        )
        fertilizer_intro.setWordWrap(True)
        identity.addWidget(fertilizer_intro)
        hero_layout.addLayout(identity, 1)
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
        current_status = QLabel(
            f"Active fertilizer · {self._fertilizer_text(plant)}"
            if current_fertilizer is not None else
            "Active fertilizer · None"
        )
        current_status.setTextFormat(Qt.TextFormat.PlainText)
        current_status.setWordWrap(True)
        current_status.setProperty("currentFertilizer", True)
        current_status.setAccessibleName("Current Fertilizer status")
        current_status.setAccessibleDescription(current_status.text().replace("\n", ". "))
        apply_tabular_numerals(current_status)
        countdown_timer = QTimer(dialog)
        countdown_timer.setInterval(1_000)

        def refresh_fertilizer_countdown() -> None:
            live_plant = self.engine.plant_story(plant_id)
            text = (
                f"Active fertilizer · {self._fertilizer_text(live_plant)}"
                if live_plant is not None
                and getattr(live_plant, "fertilizer", None) is not None
                and live_plant.fertilizer.active(time.time()) else
                "Active fertilizer · None"
            )
            current_status.setText(text)
            current_status.setAccessibleDescription(text.replace("\n", ". "))

        countdown_timer.timeout.connect(refresh_fertilizer_countdown)
        countdown_timer.start()
        balance_value = int(self.storage.state.currency_balance)
        balance = QLabel(f"{balance_value:,} Garden Coins")
        balance.setProperty("fertilizerBalance", True)
        apply_tabular_numerals(balance)
        layout.addWidget(title)
        hero_layout.addWidget(balance, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(hero)
        layout.addWidget(current_status)
        options_heading = QLabel("Choose a fertilizer")
        options_heading.setProperty("fertilizerTitle", True)
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
                "This plant is not currently nurtured. Nurture it before purchasing Fertilizer."
            )
            nurture_note.setWordWrap(True)
            nurture_note.setProperty("fertilizerMeta", True)
            options_layout.addWidget(nurture_note)
            nurture_now = QPushButton("Nurture this plant")
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
        for tier, spec in self.engine.FERTILIZERS.items():
            hours = spec.duration_seconds // 3600
            duration = f"{hours} hour" if hours == 1 else f"{hours} hours"
            card = QFrame()
            card.setProperty("fertilizerCard", True)
            card.setMinimumHeight(112)
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(12)
            row.addWidget(_item_preview_label(
                self.engine,
                f"fertilizer_{tier}",
                f"{spec.name} bag preview",
                size=72,
            ))
            copy = QVBoxLayout()
            copy.setSpacing(3)
            name = QLabel(spec.name)
            name.setProperty("fertilizerTitle", True)
            affordable, affordability = _affordability_status(spec.price, balance_value)
            detail = QLabel(
                f"+{spec.growth_per_answer} Growth per Anki card answer\n"
                f"Duration: {duration} · {cost_label(spec.price)}"
            )
            detail.setProperty("fertilizerMeta", True)
            detail.setWordWrap(True)
            apply_tabular_numerals(detail)
            copy.addWidget(name)
            copy.addWidget(detail)
            if not affordable:
                shortfall = max(0, int(spec.price) - balance_value)
                shortfall_label = QLabel(
                    f"Need {shortfall:,} more {'coin' if shortfall == 1 else 'coins'}"
                )
                shortfall_label.setProperty("fertilizerShortfall", True)
                apply_tabular_numerals(shortfall_label)
                copy.addWidget(shortfall_label)
            row.addLayout(copy, 1)
            semantic_action = _fertilizer_action_label(
                current_tier,
                str(tier),
                spec.name,
            )
            tier_is_active = bool(current_tier and current_tier == str(tier).lower())
            if tier_is_active:
                active_badge = QLabel("Active")
                active_badge.setProperty("activeFertilizerBadge", True)
                active_badge.setAccessibleDescription(
                    f"{spec.name} is active. {self._fertilizer_text(plant)}"
                )
                row.addWidget(active_badge, 0, Qt.AlignmentFlag.AlignVCenter)
                options_layout.addWidget(card)
                continue
            if current_tier:
                action_label = "Replace"
            else:
                action_label = "Apply"
            choose = QPushButton(action_label)
            _set_button_variant(
                choose,
                BUTTON_VARIANT_PRIMARY if affordable and active else BUTTON_VARIANT_SECONDARY,
            )
            choose.setAccessibleName(
                f"{semantic_action} for {spec.price:,} Garden Coins"
            )
            choose.setAccessibleDescription(
                f"{semantic_action}. {spec.name} adds {spec.growth_per_answer} Growth per Anki card answer for {duration}. "
                f"Costs {spec.price:,} Garden Coins. {affordability}"
            )
            set_control_enabled(
                choose,
                affordable and active,
                disabled_reason=(
                    "Nurture this plant before purchasing Fertilizer."
                    if not active
                    else f"{spec.name} is not affordable yet. {affordability}"
                ),
                enabled_description=choose.accessibleDescription(),
            )
            if not affordable or not active:
                card.setAccessibleName(
                    f"{spec.name} requires nurturing this plant first"
                    if not active else f"{spec.name} is not affordable yet"
                )
                apply_explanatory_tooltip(
                    card,
                    "Nurture this plant before purchasing Fertilizer."
                    if not active else
                    f"{spec.name} costs {spec.price:,} Garden Coins. {affordability}",
                )
                card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                set_keyboard_focus_surface(card)
            choose.setMinimumHeight(BUTTON_MIN_HEIGHT)
            choose.clicked.connect(
                lambda _checked=False, selected_tier=tier, target=dialog, status=purchase_status:
                self._purchase_fertilizer_from_dialog(plant_id, selected_tier, target, status)
            )
            row.addWidget(choose)
            options_layout.addWidget(card)
        options_layout.addStretch(1)
        layout.addWidget(options_scroll, 1)
        dialog.register_scroll_region(options_scroll)
        footer_frame = QFrame()
        footer_frame.setProperty("actionFooter", True)
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(0, 10, 0, 0)
        browse = QPushButton("View fertilizer in Nursery")
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
        plant = self.engine.plant_story(plant_id)
        if plant is None:
            return False, "That plant is no longer in your collection."
        replace = False
        current = plant.fertilizer
        if current is not None and current.active(time.time()) and current.tier != tier:
            current_spec = self.engine.FERTILIZERS.get(str(current.tier).lower())
            new_spec = self.engine.FERTILIZERS.get(str(tier).lower())
            if new_spec is None:
                return False, "Choose a valid Fertilizer tier."
            remaining_seconds = max(0, int(float(current.expires_at) - time.time()))
            hours, remainder = divmod(remaining_seconds, 3600)
            minutes = max(1, remainder // 60) if hours == 0 else remainder // 60
            remaining_time = (
                f"{hours}h {minutes}m" if hours else _minute_count(minutes)
            )
            replacement = FertilizerReplacementDialog(
                confirmation_parent or self,
                current_name=str(getattr(current_spec, "name", current.tier)),
                current_effect=f"+{int(current.growth_per_answer)} Growth per Anki card answer",
                remaining_time=remaining_time,
                new_name=new_spec.name,
                new_effect=(
                    f"+{new_spec.growth_per_answer} Growth per Anki card answer for "
                    f"{max(1, new_spec.duration_seconds // 3600)} hours"
                ),
                cost=new_spec.price,
            )
            if replacement.exec() != QDialog.DialogCode.Accepted:
                return False, "Fertilizer was not changed."
            replace = True
        self._fertilizer_purchase_pending = True
        try:
            ok, message = self.engine.purchase_fertilizer(
                plant_id, tier, replace_active=replace
            )
        finally:
            self._fertilizer_purchase_pending = False
        if ok:
            self._refresh_after_commit("Fertilizer purchase")
        return ok, message

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = GardenSettingsDialog(self, self.engine, self.config)
        elif self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            return
        self.settings_dialog.prepare_to_show()
        self.settings_dialog.present_over_parent()
