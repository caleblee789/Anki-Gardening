from __future__ import annotations

import logging
import json
import os
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any, Callable

from aqt.qt import (
    QDialog,
    QBoxLayout,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
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
    QSizePolicy,
    QGuiApplication,
    QEvent,
    QObject,
    QToolTip,
    pyqtSignal,
)
from .formatters import format_status_label
from .garden_studio import GardenStudioWidget
from .plant_display import (
    CURRENT_ONBOARDING_VERSION,
    achievement_progress_display,
    chronological_memories,
    dashboard_layout_is_compact,
    growth_display,
    story_is_just_beginning,
)
from .scene import GardenSceneWidget
from .state import GardenUiCoordinator, select_garden_ui
from .theme import (
    BUTTON_MIN_HEIGHT,
    BUTTON_VARIANT_PRIMARY,
    BUTTON_VARIANT_SECONDARY,
    BUTTON_VARIANT_TERTIARY,
    GARDEN_THEME,
    ICON_BUTTON_SIZE,
    PLANT_ACTION_MIN_HEIGHT,
    button_stylesheet,
)
from ..display_telemetry import DISPLAY_TELEMETRY
from ..environment import (
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    CatalogItem,
    GrowthChargeSpec,
)
from ..config import ConfigError
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
    PAID_COST_TEMPLATE,
    REWARD_DISCLOSURE,
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


class DialogShell(QDialog):
    """Shared native dialog lifecycle with deterministic focus restoration."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._return_focus: QWidget | None = None
        self.setWindowModality(Qt.WindowModality.WindowModal)

    def remember_invoker(self, widget: QWidget | None) -> None:
        self._return_focus = widget

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.raise_)
        QTimer.singleShot(0, self.activateWindow)

    def done(self, result: int) -> None:
        target = self._return_focus
        self._return_focus = None
        super().done(result)
        if target is not None:
            def restore() -> None:
                try:
                    target.setFocus()
                except RuntimeError:
                    pass
            QTimer.singleShot(0, restore)


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
        title_copy.addWidget(self.dialog_title)
        self.dialog_subtitle = QLabel(subtitle)
        self.dialog_subtitle.setProperty("dialogSubtitle", True)
        self.dialog_subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.dialog_subtitle.setWordWrap(True)
        self.dialog_subtitle.setVisible(bool(subtitle))
        title_copy.addWidget(self.dialog_subtitle)
        self.header_layout.addLayout(title_copy, 1)
        self.top_close = QPushButton("×")
        self.top_close.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        self.top_close.setAccessibleName(f"Close {title}")
        self.top_close.setToolTip(f"Close {title}")
        self.top_close.setProperty("iconButton", True)
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

        self.footer = QFrame()
        self.footer.setProperty("actionFooter", True)
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(0, 10, 0, 0)
        self.footer_layout.setSpacing(8)
        self.footer.hide()
        self._shell_layout.addWidget(self.footer)

    def set_dialog_title(self, title: str) -> None:
        self.setWindowTitle(title)
        self.dialog_title.setText(title)
        self.top_close.setAccessibleName(f"Close {title}")
        self.top_close.setToolTip(f"Close {title}")

    def set_tabs_widget(self, tabs: QWidget) -> None:
        self.tabs_layout.addWidget(tabs)
        self.tabs_region.show()

    def set_body_widget(self, body: QWidget) -> None:
        self.body_layout.addWidget(body, 1)

    def add_footer_widget(self, widget: QWidget, *, stretch_before: bool = False) -> None:
        if stretch_before and self.footer_layout.count() == 0:
            self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(widget)
        self.footer.show()


def _nurtured_badge_declarations() -> str:
    """Keep the nurtured status visually identical across Garden surfaces."""

    t = GARDEN_THEME
    return (
        f"color:{t['action_text']}; background:{t['coin_accent']}; border:0; "
        "border-radius:8px; padding:4px 8px; font-size:11px; font-weight:700;"
    )


def _garden_dialog_stylesheet() -> str:
    t = GARDEN_THEME
    return _button_stylesheet() + f"""
        QDialog#gardenDialog {{ background:{t['dialog_surface']}; color:{t['text_primary']}; }}
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
        QCheckBox[toggleSwitch='true'] {{ min-height:40px; spacing:10px; color:{t['text_primary']}; }}
        QCheckBox[toggleSwitch='true']::indicator {{ width:38px; height:22px; border-radius:11px; border:1px solid {t['subtle_border']}; background:#20312c; }}
        QCheckBox[toggleSwitch='true']::indicator:checked {{ border:1px solid {t['growth_accent']}; background:{t['action_accent']}; }}
        QTabWidget::pane {{ border:0; background:transparent; top:-1px; }}
        QTabBar {{ background:{t['dialog_surface']}; border-bottom:1px solid {t['subtle_border']}; }}
        QTabBar::tab {{ min-height:42px; padding:0 16px; margin-right:2px; color:{t['text_secondary']}; background:transparent; border:0; border-bottom:2px solid transparent; }}
        QTabBar::tab:hover {{ color:{t['text_primary']}; background:{t['raised_surface']}; }}
        QTabBar::tab:selected {{ color:{t['text_primary']}; background:transparent; border-bottom:2px solid {t['growth_accent']}; }}
        QTabBar::tab:focus {{ border:2px solid {t['focus_ring']}; border-bottom:2px solid {t['growth_accent']}; }}
        QScrollArea {{ background:transparent; border:0; }}
        QLineEdit, QTextEdit {{ color:{t['text_primary']}; background:#10241f; border:1px solid {t['subtle_border']}; border-radius:8px; padding:7px 9px; selection-background-color:{t['action_accent']}; }}
        QLineEdit {{ min-height:24px; padding:7px 10px; }}
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


class ToastRegion(QFrame):
    """Accessible, replace-in-place feedback with an optional undo action."""

    shown = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("toastRegion", True)
        self.setProperty("liveRegion", "polite")
        self.setAccessibleName("Garden update")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.show()
        self.raise_()
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
    return f"{count:,} {'card answer' if count == 1 else 'card answers'}"


def _day_count(value: int) -> str:
    count = max(0, int(value))
    return f"{count:,} {'day' if count == 1 else 'days'}"


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


def _asset_preview_label(
    engine: Any,
    species: str,
    stage: str,
    *,
    size: int = 84,
    property_name: str = "stagePreview",
) -> QLabel:
    """Create a metadata-cropped plant preview without altering source art."""

    label = ArtworkThumbnail()
    label.setFixedSize(size, size)
    label.setProperty(property_name, True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    species_name = format_status_label(species)
    stage_name = format_status_label(stage)
    label.setAccessibleName(f"{species_name}, {stage_name} stage preview")
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
        label.setWordWrap(True)
        label.setText(stage_name)
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
) -> None:
    """Copy one resolved stage preview into an existing layout-owned label."""

    preview = _asset_preview_label(engine, species, stage, size=size)
    target.setAccessibleName(preview.accessibleName())
    pixmap = preview.pixmap()
    if pixmap is None or pixmap.isNull():
        target.setPixmap(QPixmap())
        target.setText(fallback_text)
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
        label.setText("◇")
        label.setToolTip(accessible_name)
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
            if not overlay.isNull():
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
    """Accessible switch whose checked state is conveyed by position and text."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setProperty("toggleSwitch", True)
        self.setAccessibleName(label)
        self.toggled.connect(self._sync_accessible_state)
        self._sync_accessible_state(self.isChecked())

    def _sync_accessible_state(self, checked: bool) -> None:
        self.setText(f"{self.accessibleName()}   {'✓  On' if checked else '○  Off'}")
        self.setAccessibleDescription("On" if checked else "Off")


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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.viewport().setStyleSheet("background:#0b1f1b;")
        self.scroll.setAccessibleName(f"{accessible_name} scroll area")
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(4, 4, 22, 4)
        self.rows.setSpacing(5)
        self.scroll.setWidget(self.container)
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
        columns = (
            1 if width < 410 else
            2 if self._wide_columns >= 3 and width < 620 else
            self._wide_columns
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
        columns = 1 if event.size().width() < self.breakpoint else 2
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
        self._stacked: bool | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self._reflow(False)

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
        self._reflow(event.size().width() < self.breakpoint)
        super().resizeEvent(event)


class GardenSettingsDialog(GardenDialog):
    def __init__(self, parent: QWidget, engine: Any, config: Any) -> None:
        super().__init__(parent, UI_TEXT["settings_window_title"])
        self.engine = engine
        self.config = config
        self._save_status_generation = 0
        self._troubleshooting_compact = False
        self._display_dialog_size: Any | None = None
        self.setMinimumSize(560, 420)
        self.setMaximumWidth(1000)
        self.resize(*self._recommended_window_size(980, 680, width_ratio=0.88, height_ratio=0.88))
        self.setStyleSheet(_garden_dialog_stylesheet() + f"""
            QLabel[saveStatus='true'] {{ padding:5px 8px; border-radius:8px; }}
            QFrame[diagnosticsCard='true'] {{ background:{GARDEN_THEME['raised_surface']}; border:0; border-left:4px solid {GARDEN_THEME['success']}; border-radius:12px; }}
            QFrame[diagnosticsCard='true'][diagnosticState='warning'] {{ background:#322221; border-left:4px solid #E77D6D; }}
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
        self.save_settings.setEnabled(False)
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
        self.save_status.setWordWrap(True)
        self.save_status.hide()
        self.behavior.persistentChanged.connect(self._update_dirty_state)
        behavior = QWidget()
        behavior_layout = QVBoxLayout(behavior)
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
        self.garden_name_edit.setMaxLength(MAX_GARDEN_NAME_LENGTH)
        self.garden_name_edit.setFixedHeight(40)
        self.garden_name_edit.setAccessibleName("Garden name")
        self.garden_name_edit.setAccessibleDescription(
            f"The name shown on your Garden and Anki home preview. Up to {MAX_GARDEN_NAME_LENGTH} characters."
        )
        garden_name_copy.addWidget(garden_name_label)
        garden_name_copy.addWidget(self.garden_name_edit)
        garden_name_help = QLabel("Shown in the Garden header and home-screen preview.")
        garden_name_help.setWordWrap(True)
        garden_name_help.setProperty("dialogSubtitle", True)
        garden_name_copy.addWidget(garden_name_help)
        self.garden_name_edit.textChanged.connect(self._update_dirty_state)
        self.garden_name_edit.textChanged.connect(self._preview_garden_name)
        self.garden_name_edit.returnPressed.connect(self._save_visual_settings)
        garden_name_layout.addLayout(garden_name_copy, 1)
        behavior_layout.addWidget(garden_name_panel)
        behavior_scroll = QScrollArea()
        behavior_scroll.setWidgetResizable(True)
        behavior_scroll.setFrameShape(QFrame.Shape.NoFrame)
        behavior_scroll.setWidget(self.behavior)
        behavior_layout.addWidget(behavior_scroll, 1)

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
        self._apply_settings_footer_layout(self.width())

        advanced = QWidget()
        a_layout = QVBoxLayout(advanced)
        a_layout.setContentsMargins(0, 8, 0, 0)
        a_layout.setSpacing(12)
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
        self.troubleshooting_status.setAccessibleName("Troubleshooting report status")
        self.diagnostics_summary = QLabel("The Garden display contract is healthy.")
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
        diagnostics_copy.addWidget(self.troubleshooting_status)
        diagnostics_copy.addWidget(self.diagnostics_summary)
        diagnostics_copy.addWidget(self.diagnostics_checked)
        diagnostics_copy.addWidget(self.diagnostics_version)
        diagnostics_copy.addWidget(self.diagnostics_build)
        diagnostics_layout.addWidget(self.diagnostics_icon, 0, Qt.AlignmentFlag.AlignTop)
        diagnostics_layout.addLayout(diagnostics_copy, 1)
        a_layout.addWidget(self.diagnostics_card)
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        self.debug_report.setMaximumHeight(220)
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
        self.copy_details = QPushButton("Copy details")
        _set_button_variant(self.copy_details, BUTTON_VARIANT_TERTIARY)
        self.copy_details.clicked.connect(self._copy_debug_report)
        self.copy_details.hide()
        report_actions.addWidget(self.copy_details)
        self.report_details_toggle = QPushButton("View technical details")
        self.report_details_toggle.setCheckable(True)
        _set_button_variant(self.report_details_toggle, BUTTON_VARIANT_TERTIARY)
        self.report_details_toggle.toggled.connect(self._toggle_debug_report)
        report_actions.addWidget(self.report_details_toggle)
        report_actions.addStretch(1)
        a_layout.addLayout(report_actions)
        a_layout.addWidget(self.debug_report)
        self._development_backup_path: Path | None = None
        self.unlock_development = QPushButton("Unlock development tools")
        _set_button_variant(self.unlock_development, BUTTON_VARIANT_SECONDARY)
        self.unlock_development.setAccessibleDescription(
            "Reveal temporary state-population tools for this Settings session."
        )
        self.unlock_development.clicked.connect(self._unlock_development_tools)
        self.unlock_development.setVisible(
            os.environ.get("ANKI_GARDEN_DEV_TOOLS") == "1"
        )
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
        self.restore_development.setEnabled(False)
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

        self.tabs.addTab(behavior, "Display")
        self.tabs.addTab(advanced, UI_TEXT["tab_advanced"])
        self.tabs.currentChanged.connect(self._sync_settings_tab)
        self._sync_settings_tab(0)
        self._refresh_garden_name()

    def _apply_settings_footer_layout(self, width: int) -> None:
        compact = int(width) < 700
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
        if troubleshooting and not self._troubleshooting_compact:
            self._display_dialog_size = self.size()
            compact_width, compact_height = _fit_dialog_to_screen(
                self,
                min(980, self.width()),
                430,
                width_ratio=0.88,
                height_ratio=0.72,
            )
            self.resize(compact_width, compact_height)
        elif not troubleshooting and self._troubleshooting_compact:
            if self._display_dialog_size is not None:
                self.resize(self._display_dialog_size)
        self._troubleshooting_compact = troubleshooting

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "settings_footer_grid"):
            self._apply_settings_footer_layout(event.size().width())
        super().resizeEvent(event)

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
        self.save_settings.setEnabled(False)

    def _refresh_garden_name(self) -> None:
        name = str(getattr(self.engine.state, "garden_name", "My Garden") or "My Garden")
        self.garden_name_edit.blockSignals(True)
        self.garden_name_edit.setText(name)
        self.garden_name_edit.blockSignals(False)
        self.garden_name_edit.setToolTip(name)

    def _rename_garden(self) -> None:
        """Compatibility entrypoint: rename is now part of the dirty draft."""
        self.garden_name_edit.setFocus()
        self.garden_name_edit.selectAll()

    def _update_dirty_state(self) -> None:
        draft_name = " ".join(self.garden_name_edit.text().split())
        valid = bool(draft_name) and len(draft_name) <= MAX_GARDEN_NAME_LENGTH
        dirty = self._draft_is_dirty()
        self.save_settings.setEnabled(dirty and valid)
        if dirty:
            self.save_status.setVisible(self.tabs.currentIndex() != 1)
            self.save_status.setText("Unsaved changes" if valid else "Enter a valid garden name")
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
            "Stage these defaults: garden name “My Garden”, Home preview on, and progress notifications off. Scenery and gameplay progress will not change.",
        ):
            return
        self.garden_name_edit.setText("My Garden")
        self.behavior.show_home_widget.setChecked(True)
        self.behavior.show_progress_notifications.setChecked(False)
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
        if not draft_name:
            self._show_save_error("Enter a name for your garden.")
            return
        if len(draft_name) > MAX_GARDEN_NAME_LENGTH:
            self._show_save_error(
                f"Garden names can be at most {MAX_GARDEN_NAME_LENGTH} characters."
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
        self.save_settings.setEnabled(False)
        self.save_status.show()
        self.save_status.setText("Saved")
        self.save_status.setStyleSheet("color:#baf3c6; background:#1d4931;")
        self.save_status.setAccessibleDescription("Anki Garden settings saved successfully.")
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
        self.save_settings.setEnabled(False)
        self.save_status.setText("")
        self.save_status.hide()
        super().reject()

    def _refresh_debug_report(self) -> None:
        report_lines = list(DISPLAY_TELEMETRY.report_lines())
        self.debug_report.setPlainText("\n".join(report_lines))

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
            self.diagnostics_icon.setText("!")
            self.diagnostics_icon.setAccessibleName("Diagnostics warning")
            self.diagnostics_icon.setStyleSheet(
                f"color:#2b120f; background:{GARDEN_THEME['error']}; border-radius:20px;"
            )
            self.diagnostics_card.setProperty("diagnosticState", "warning")
        else:
            status = "No display issues detected"
            self.diagnostics_summary.setText("The Garden display contract is healthy.")
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

    def _toggle_debug_report(self, expanded: bool) -> None:
        self.debug_report.setVisible(bool(expanded))
        self.copy_details.setVisible(bool(expanded))
        self.report_details_toggle.setText(
            "Hide technical details" if expanded else "View technical details"
        )
        self.report_details_toggle.setAccessibleName(self.report_details_toggle.text())
        if self.tabs.currentIndex() == 1:
            _width, height = _fit_dialog_to_screen(
                self,
                self.width(),
                680 if expanded else 480,
                width_ratio=0.88,
                height_ratio=0.88 if expanded else 0.72,
            )
            self.resize(self.width(), height)

    def _copy_debug_report(self) -> None:
        QGuiApplication.clipboard().setText(self.debug_report.toPlainText())
        self.diagnostics_checked.setText("Report copied to clipboard")
        self.diagnostics_card.setAccessibleDescription("Troubleshooting report copied to the clipboard.")
        self.diagnostics_card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.diagnostics_card.setFocus()

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
            self.restore_development.setEnabled(True)
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
            self.restore_development.setEnabled(False)
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
        self.setMinimumSize(480, 400)
        self.setMaximumWidth(640)
        self.resize(*_fit_dialog_to_screen(self, 640, 520, width_ratio=0.78, height_ratio=0.78))
        self.setStyleSheet(_garden_dialog_stylesheet() + """
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
        self.story_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.story_scroll.setAccessibleName("Plant Story details")
        story_body = QWidget()
        story_body.setStyleSheet("background:#071a15;")
        content = QVBoxLayout(story_body)
        content.setContentsMargins(0, 0, 12, 0)
        content.setSpacing(12)
        self.story_scroll.setWidget(story_body)
        self.story_scroll.viewport().setStyleSheet("background:#071a15;")
        self.set_body_widget(self.story_scroll)
        hero = QFrame()
        hero.setProperty("storyHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
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
            "Eligible card answers add Growth to this plant."
        )
        identity_text.addWidget(self.nurturing_status, 0, Qt.AlignmentFlag.AlignLeft)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.feedback.setAccessibleName("Plant name status")
        self.feedback.hide()
        identity_text.addWidget(self.feedback)
        identity_text.addStretch(1)
        hero_layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(identity_text, 1)
        content.addWidget(hero)

        self.stage_path = QFrame()
        self.stage_path.setProperty("storyStages", True)
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
        content.addWidget(self.stage_path)

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
            self.edit_name_btn.setEnabled(False)
            self.artwork.clear()
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
            if stage_key == "rare" and stage_state == "upcoming":
                stage_preview.setPixmap(QPixmap())
                stage_preview.setText("?")
                stage_preview.setAccessibleDescription(
                    "Rare-stage artwork remains undiscovered."
                )
            else:
                _populate_asset_preview(
                    stage_preview,
                    self.engine,
                    plant.species,
                    stage_key,
                    size=56,
                    fallback_text=format_status_label(stage_key),
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
                f"{next_stage}\n"
                f"{progress.points_remaining:,} Growth remaining · "
                f"About {answers:,} eligible {'answer' if answers == 1 else 'answers'}"
            )
            self.stage_progress.set_progress(
                f"Progress to {next_stage}",
                progress.stage_points,
                max(1, progress.stage_goal),
                value_text=f"{progress.stage_points:,} of {progress.stage_goal:,} Growth",
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
        self.setWindowTitle(f"Choose {species_name}")
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
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
        title = QLabel(f"Choose {species_name} as your first plant?")
        title.setProperty("dialogTitle", True)
        title.setWordWrap(True)
        body = QLabel(
            "You can collect additional species later through the Nursery."
        )
        body.setProperty("dialogSubtitle", True)
        body.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(body)
        heading.addLayout(copy, 1)
        layout.addLayout(heading)
        actions = QHBoxLayout()
        actions.addStretch(1)
        back = QPushButton("Go back")
        _set_button_variant(back, BUTTON_VARIANT_TERTIARY)
        back.clicked.connect(self.reject)
        choose = QPushButton(f"Choose {species_name}")
        choose.setAccessibleDescription(
            f"Plant {species_name} as your free first plant."
        )
        _set_button_variant(choose, BUTTON_VARIANT_PRIMARY)
        choose.clicked.connect(self.accept)
        actions.addWidget(back)
        actions.addWidget(choose)
        layout.addLayout(actions)
        self.setTabOrder(back, choose)
        choose.setFocus()


class NurseryDialog(QDialog):
    """Artwork-led catalog for starters, collected plants, and garden spaces."""

    def __init__(self, parent: QWidget, engine: Any, storage: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.storage = storage
        self.setWindowTitle("Nursery")
        self.setMinimumSize(720, 480)
        self.resize(*_fit_dialog_to_screen(self, 840, 640, width_ratio=0.88, height_ratio=0.84))
        self.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#241813; color:#f5ead7; }
            QFrame[nurseryHero='true'] { background:transparent; border:0; border-bottom:1px solid #604333; border-radius:0; }
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
            QLabel[nurseryOwnership='true'] { color:#d5ad70; font-size:11px; font-weight:800; letter-spacing:.8px; }
            QLabel[nurseryStageName='true'] { color:#fff3da; font-size:16px; font-weight:800; }
            QLabel[nurseryStageCount='true'] { color:#cdbba5; font-size:13px; }
            QLabel[nurseryShortfall='true'] { color:#f0cf8d; font-size:13px; }
            QLabel[nurseryCoinLabel='true'] { color:#bca991; font-size:11px; font-weight:800; letter-spacing:.9px; }
            QLabel[nurseryCoins='true'] { color:#f1c979; font-size:29px; font-weight:800; }
            QLabel[nurseryArtwork='true'] {
                background:qradialgradient(cx:0.5,cy:0.58,radius:0.78,fx:0.5,fy:0.58,stop:0 #55402e,stop:0.62 #32231d,stop:1 #211713);
                border:1px solid #795b42;
                border-radius:12px;
                color:#d6c4ac;
                font-size:11px;
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
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 10, 24, 14)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        eyebrow = QLabel("NURSERY")
        eyebrow.setProperty("nurseryEyebrow", True)
        self.heading = QLabel(NURSERY_STARTER_TITLE)
        self.heading.setProperty("nurseryTitle", True)
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
        hero_layout.addLayout(copy, 1)
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
        self.coins.setAlignment(Qt.AlignmentFlag.AlignRight)
        resource_layout.addWidget(coin_label)
        resource_layout.addWidget(self.coins)
        hero_layout.addWidget(self.coin_resource, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hero)

        self.catalog_tabs = QTabWidget()
        self.catalog_tabs.setDocumentMode(True)
        self.catalog_tabs.setAccessibleName("Nursery catalog sections")
        self.catalog_tabs.tabBar().setExpanding(True)
        self.catalog_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog = QWidget()
        self.catalog_layout = QVBoxLayout(self.catalog)
        self.catalog_layout.setContentsMargins(2, 2, 2, 2)
        self.catalog_layout.setSpacing(9)
        self.scroll.setWidget(self.catalog)
        self.catalog_tabs.addTab(self.scroll, "Plants")

        self.supplements_scroll = QScrollArea()
        self.supplements_scroll.setWidgetResizable(True)
        self.supplements_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.supplements_catalog = QWidget()
        self.supplements_layout = QVBoxLayout(self.supplements_catalog)
        self.supplements_layout.setContentsMargins(6, 6, 6, 6)
        self.supplements_layout.setSpacing(9)
        self.supplements_scroll.setWidget(self.supplements_catalog)
        self.catalog_tabs.addTab(self.supplements_scroll, "Fertilizer and Boosters")

        self.upgrades_scroll = QScrollArea()
        self.upgrades_scroll.setWidgetResizable(True)
        self.upgrades_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.upgrades_catalog = QWidget()
        self.upgrades_layout = QVBoxLayout(self.upgrades_catalog)
        self.upgrades_layout.setContentsMargins(6, 6, 6, 6)
        self.upgrades_layout.setSpacing(9)
        self.upgrades_scroll.setWidget(self.upgrades_catalog)
        self.catalog_tabs.addTab(self.upgrades_scroll, "Garden Spaces")

        self.environment_scroll = QScrollArea()
        self.environment_scroll.setWidgetResizable(True)
        self.environment_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.environment_catalog = QWidget()
        self.environment_layout = QVBoxLayout(self.environment_catalog)
        self.environment_layout.setContentsMargins(6, 6, 6, 6)
        self.environment_layout.setSpacing(9)
        self.environment_scroll.setWidget(self.environment_catalog)
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
        self.status.hide()
        root.addWidget(self.status)
        footer = QHBoxLayout()
        self.bed_button = QPushButton("")
        self._bed_purchase_pending = False
        _set_button_variant(self.bed_button, BUTTON_VARIANT_SECONDARY)
        self.bed_button.clicked.connect(self._unlock_bed)
        self.bed_affordability = QLabel("")
        self.bed_affordability.setWordWrap(True)
        self.bed_affordability.setProperty("nurseryShortfall", True)
        self.bed_affordability.setAccessibleName("Garden space affordability")
        self.bed_affordability.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        _set_button_variant(self.close_button, BUTTON_VARIANT_SECONDARY)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        root.addLayout(footer)
        self.refresh()

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
            previous.setEnabled(index > 0)
            next_button.setEnabled(index < len(GROWTH_STAGES) - 1)

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
        if plant.planted and plant.plant_id == self.storage.state.active_plant_id:
            action.setEnabled(False)
            reason = "Finish or switch your nurtured plant first."
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
        title = QLabel(species_name)
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
        meta = QLabel(PAID_COST_TEMPLATE.format(amount=f"{price:,}"))
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        affordability_label = QLabel(
            _compact_affordability_status(price, balance, ready_text="Ready to unlock")
        )
        affordability_label.setProperty("nurseryShortfall", True)
        affordability_label.setWordWrap(True)
        details = QPushButton("Details")
        details.setCheckable(True)
        _set_button_variant(details, BUTTON_VARIANT_TERTIARY)

        def toggle_stages(checked: bool) -> None:
            stages.setVisible(checked)
            details.setText("Hide details" if checked else "Details")

        details.toggled.connect(toggle_stages)
        action = QPushButton(f"Buy for {price:,}")
        _set_button_variant(action, BUTTON_VARIANT_PRIMARY)
        action.setAccessibleName(f"Buy {species_name} for {price:,} Garden Coins")
        action.setAccessibleDescription(
            f"Add {species_name} to your plant collection. {affordability}"
        )
        action.setEnabled(affordable)
        if not affordable:
            card.setProperty("unaffordable", True)
            card.setAccessibleName(f"{species_name} is not affordable yet")
            apply_explanatory_tooltip(
                card,
                f"{species_name} costs {price:,} Garden Coins. {affordability}",
            )
            card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        card.setAccessibleName(f"{species_name} starter plant")
        card.setAccessibleDescription(self._plant_description(species))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        layout.addWidget(
            self._plant_artwork(species, GROWTH_STAGES[0], 112),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        title = QLabel(species_name)
        title.setProperty("nurseryPlantName", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        description = QLabel(self._plant_description(species))
        description.setProperty("nurseryMeta", True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        stage = QLabel(f"Starting stage: {format_status_label(GROWTH_STAGES[0])}")
        stage.setProperty("nurseryOwnership", True)
        stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(stage)
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
        choose = QPushButton(f"Choose {species_name}")
        choose.setAccessibleName(f"Choose {species_name} as your first plant")
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
            label.setWordWrap(True)
            label.setText(accessible_name)
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
            f"Effect: +{spec.growth_per_answer} Growth per eligible answer\n"
            f"Duration: {duration_hours} {'hour' if duration_hours == 1 else 'hours'}  ·  "
            f"Price: {spec.price:,} Garden Coins"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        active = self.engine.active_plant()
        affordable = self.storage.state.currency_balance >= spec.price
        action = QPushButton(f"Apply for {spec.price:,}")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if affordable and active is not None else BUTTON_VARIANT_SECONDARY,
        )
        action.setEnabled(affordable and active is not None)
        reason = (
            f"Use {spec.name} on {active.name}."
            if active is not None and affordable else
            f"Need {spec.price - self.storage.state.currency_balance:,} more Garden Coins."
            if active is not None else
            "Choose an unfinished planted plant to nurture first."
        )
        action.setAccessibleDescription(reason)
        action.clicked.connect(
            lambda _checked=False, selected=tier: self._purchase_fertilizer(selected)
        )
        row.addWidget(action)
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
        meta = QLabel(
            "+5 Growth per answer for 2 hours. A rare study gift; not sold in the Nursery."
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        active = self.engine.active_plant()
        action = QPushButton("Use potion")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if count > 0 and active is not None else BUTTON_VARIANT_SECONDARY,
        )
        action.setEnabled(count > 0 and active is not None)
        action.setAccessibleDescription(
            f"Use one Booster Potion on {active.name}."
            if active is not None and count > 0 else
            "A Booster Potion and a nurtured unfinished plant are required."
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
        meta = QLabel(
            f"Adds up to {spec.growth:,} Growth to the nurtured plant, capped at Rare.\n"
            + (
                f"Cost: {spec.price:,} Garden Coins"
                if spec.price is not None
                else "Earn-only; never sold."
            )
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
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
            action = QPushButton(f"Buy for {spec.price:,}")
            enabled = affordable
            action.setAccessibleDescription(
                f"Buy one {spec.name} for {spec.price:,} Garden Coins."
                if affordable else
                f"Need {spec.price - self.storage.state.currency_balance:,} more Garden Coins."
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
        action.setEnabled(enabled)
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
            f"{item.price:,} Garden Coins"
            if item.price is not None else
            "Included with every garden"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
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
        action = QPushButton(
            "Customize" if owned else f"Buy for {int(item.price or 0):,}"
        )
        action.setEnabled(owned or affordable)
        _set_button_variant(
            action, BUTTON_VARIANT_PRIMARY if owned or affordable else BUTTON_VARIANT_SECONDARY
        )
        action.setAccessibleDescription(
            f"Open Customize Garden to preview or equip {item.name}."
            if owned else
            f"Buy {item.name} once for {item.price:,} Garden Coins."
            if affordable else
            f"Need {int(item.price or 0) - self.storage.state.currency_balance:,} more Garden Coins."
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
        status = QLabel(
            "Unlocked permanently"
            if unlocked else
            f"Next upgrade — {price:,} Garden Coins"
            if next_space and price is not None else
            "Unlock the previous garden space first"
        )
        status.setProperty("nurseryMeta", True)
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
            self.bed_button.setEnabled(affordable and not self._bed_purchase_pending)
            self.bed_button.setAccessibleName(
                f"Unlock garden space {index + 1} for {price:,} Garden Coins"
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
        summary = QLabel(f"{unlocked_count} of 6 garden beds unlocked")
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
            f"New capacity: {min(6, unlocked_count + 1)} plants · Price: {price:,} Garden Coins"
        )
        details.setProperty("nurseryMeta", True)
        details.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(details)
        expansion_layout.addLayout(copy, 1)
        if price is not None:
            affordable = int(state.currency_balance) >= int(price)
            self.bed_button = QPushButton(f"Buy for {price:,}")
            self.bed_button.setEnabled(affordable and not self._bed_purchase_pending)
            _set_button_variant(
                self.bed_button,
                BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
            )
            self.bed_button.setAccessibleDescription(
                f"Unlock garden bed {next_index + 1} for {price:,} Garden Coins."
                if affordable else
                f"Need {price - int(state.currency_balance):,} more Garden Coins."
            )
            self.bed_button.clicked.connect(self._unlock_bed)
            expansion_layout.addWidget(self.bed_button)
        layout.addWidget(expansion)
        layout.addStretch(1)
        return host

    def _purchase_fertilizer(self, tier: str) -> None:
        plant = self.engine.active_plant()
        if plant is None:
            self._show_result(False, "Choose an unfinished planted plant to nurture first.")
            return
        current = getattr(plant, "fertilizer", None)
        replace = bool(current and current.active(time.time()) and current.tier != tier)
        if replace:
            answer = QMessageBox.question(
                self,
                "Replace active Fertilizer?",
                "Replacing it discards the remaining time. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        ok, message = self.engine.purchase_fertilizer(
            plant.plant_id, tier, replace_active=replace
        )
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _use_booster(self) -> None:
        ok, message = self.engine.use_booster_potion()
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _purchase_growth_charge(self, charge_id: str) -> None:
        ok, message = self.engine.purchase_growth_charge(charge_id)
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _use_growth_charge(self, charge_id: str) -> None:
        ok, message = self.engine.use_growth_charge(charge_id)
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _purchase_environment(self, kind: str, item_id: str) -> None:
        ok, message = self.engine.purchase_environment(kind, item_id)
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _sync_catalog_intro(self, index: int) -> None:
        if bool(getattr(self, "_starter_mode", False)):
            text = NURSERY_STARTER_RATIONALE
        else:
            text = {
                0: f"{getattr(self, '_catalog_summary', '')}. Choose plants to add or return to the Garden.",
                1: "Apply timed Fertilizer or use collected Booster Potions on a nurtured plant.",
                2: "Unlock permanent Garden spaces and manage planting capacity.",
                3: "Unlock collectible Weather and Scenery. Equipped passives remain active when artwork is hidden.",
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
            "Free starter plants" if starter_mode else "Botanical catalog",
            "Your first plant is free. Choose the one whose look you like best."
            if starter_mode else
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
            fertilizer_heading = QLabel("Fertilizers")
            fertilizer_heading.setProperty("nurserySection", True)
            self.supplements_layout.addWidget(fertilizer_heading)
            supplement_intro = QLabel(
                "Timed boosts applied directly to the nurtured plant."
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

            upgrade_intro = QLabel(
                "Garden spaces are permanent upgrades. Unlock them in order to plant more of your collection."
            )
            upgrade_intro.setWordWrap(True)
            upgrade_intro.setProperty("nurseryMeta", True)
            self.upgrades_layout.addWidget(upgrade_intro)
            self.upgrades_layout.addWidget(self._space_progression())

            environment_intro = QLabel(
                "Preview appearance products before buying. Purchases unlock the artwork "
                "and passive; equip owned items in Customize Garden."
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
        message = _learner_text(message)
        self.status.setText(message)
        self.status.setStyleSheet(
            "color:#baf3c6; background:#1d4931; padding:7px 9px; border-radius:7px;"
            if ok else
            "color:#ffd0d0; background:#582f34; padding:7px 9px; border-radius:7px;"
        )
        self.status.setAccessibleDescription(message)
        self.status.show()
        if ok:
            QTimer.singleShot(3500, self.status.hide)
        else:
            self.status.setFocus()

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
        ok, message, _plant = self.engine.purchase_species(species)
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()

    def _unlock_bed(self) -> None:
        if self._bed_purchase_pending:
            return
        self._bed_purchase_pending = True
        self.bed_button.setEnabled(False)
        ok, message = self.engine.purchase_next_bed()
        self._show_result(ok, message)
        if ok:
            self._refresh_parent()
            self.refresh()
        # Retain the guard through the platform's complete double-click event
        # sequence. A later deliberate activation may buy the next space.
        QTimer.singleShot(350, self._release_bed_purchase)

    def _release_bed_purchase(self) -> None:
        self._bed_purchase_pending = False
        starter_mode = not bool(getattr(self.storage.state, "starter_selection_complete", True))
        bed_price = self.engine.next_bed_price()
        if starter_mode or bed_price is None:
            try:
                self.bed_button.setEnabled(False)
            except RuntimeError:
                pass
            return
        bed_affordable = (
            bed_price is not None
            and int(self.storage.state.currency_balance) >= int(bed_price)
        )
        try:
            self.bed_button.setEnabled(self.bed_button.isVisible() and bed_affordable)
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
            "Eligible card answers add Growth to this plant."
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
        self._layout_actions(active=False)
        for button in (self.nurture, self.fertilize, self.move, self.story):
            button.setMinimumHeight(PLANT_ACTION_MIN_HEIGHT)
        self.choose_another.setMinimumHeight(PLANT_ACTION_MIN_HEIGHT)
        self.hide()

    def _layout_actions(self, *, active: bool) -> None:
        for button in (
            self.nurture,
            self.fertilize,
            self.move,
            self.story,
            self.choose_another,
        ):
            self.actions.removeWidget(button)
        if active:
            self.actions.addWidget(self.fertilize, 0, 0, 1, 2)
        else:
            self.actions.addWidget(self.nurture, 0, 0)
            self.actions.addWidget(self.fertilize, 0, 1)
        self.actions.addWidget(self.move, 1, 0)
        self.actions.addWidget(self.story, 1, 1)
        self.actions.addWidget(self.choose_another, 2, 0, 1, 2)

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
            self.artwork.setPixmap(QPixmap())
            self.artwork.setText("◇")
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
            self.stage_progress.set_progress("Final stage", 1, 1, value_text="Rare stage, fully grown")
            self.growth_summary.setText(f"{growth_points:,} total Growth")
            self.growth_remaining.hide()
        else:
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            next_stage = format_status_label(plant.get("next_stage") or "the next stage")
            self.stage_progress.set_progress(
                f"Progress to {next_stage}",
                stage_points,
                stage_goal,
                value_text=f"{stage_points:,} of {stage_goal:,} Growth",
            )
            self.stage_progress.value_label.show()
            remaining = max(0, int(plant.get("points_remaining", 0) or 0))
            reviews_remaining = max(0, int(plant.get("reviews_remaining", 0) or 0))
            self.growth_summary.setText(
                f"About {_card_answer_count(reviews_remaining).replace('card answer', 'eligible answer')} "
                f"to {next_stage}"
            )
            self.growth_remaining.setText(f"{remaining:,} Growth remaining")
            self.growth_remaining.show()
            self.growth_summary.setAccessibleDescription(
                f"{remaining:,} Growth remaining. "
                f"About {_card_answer_count(reviews_remaining).replace('card answer', 'eligible answer')} before bonuses."
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
        self.nurture.setEnabled(not fully_grown)
        self.nurture.setVisible(not active and not fully_grown)
        self.nurtured_badge.setText("Fully grown" if fully_grown else "Nurtured")
        self.nurtured_badge.setVisible(active or fully_grown)
        self.fertilize.setEnabled(not fully_grown)
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
        self._layout_actions(active=active or fully_grown)
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
            cell.setMinimumHeight(68)
            cell.clicked.connect(
                lambda _checked=False, metric=key: self.metricActivated.emit(metric)
            )
            apply_explanatory_tooltip(cell, description)
            self.cells[key] = cell
            self.metric_copy[key] = (title, description)

        growth_layout = QVBoxLayout(self.cells["growth"])
        growth_layout.setContentsMargins(14, 6, 14, 6)
        growth_layout.setSpacing(2)
        growth_kicker = QLabel("NURTURED PLANT")
        growth_kicker.setProperty("gardenStatLabel", True)
        growth_heading = QHBoxLayout()
        growth_heading.setSpacing(8)
        growth_heading.addWidget(growth_kicker)
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
        growth_bar.setFixedHeight(8)
        growth_bar.setAccessibleName("Nurtured plant Growth")
        growth_bar.setProperty("metricProgress", True)
        self.growth_support = QLabel("Choose an unfinished plant to begin earning Growth")
        self.growth_support.setProperty("gardenStatSupport", True)
        self.growth_support.setWordWrap(False)
        growth_layout.addLayout(growth_heading)
        growth_layout.addLayout(growth_identity)
        growth_bar.hide()
        growth_layout.addWidget(self.growth_support)

        streak_layout = QVBoxLayout(self.cells["streak"])
        streak_layout.setContentsMargins(14, 6, 14, 6)
        streak_layout.setSpacing(2)
        streak_heading = QHBoxLayout()
        streak_heading.setSpacing(6)
        self.streak_label = QLabel("ANKI STREAK")
        self.streak_label.setProperty("gardenStatLabel", True)
        self.streak_bonus = QLabel("")
        self.streak_bonus.setProperty("gardenBonusBadge", True)
        self.streak_bonus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.streak_bonus.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        streak_heading.addWidget(self.streak_label)
        streak_heading.addStretch(1)
        streak_heading.addWidget(self.streak_bonus)
        streak_value_row = QHBoxLayout()
        streak_value_row.setSpacing(5)
        self.streak_number = QLabel("0")
        self.streak_number.setProperty("gardenLargeValue", True)
        self.streak_unit = QLabel("days")
        self.streak_unit.setProperty("gardenValueUnit", True)
        streak_value_row.addWidget(self.streak_number, 0, Qt.AlignmentFlag.AlignBottom)
        streak_value_row.addWidget(self.streak_unit, 0, Qt.AlignmentFlag.AlignBottom)
        streak_value_row.addStretch(1)
        self.streak_support = QLabel("Study today to start your streak")
        self.streak_support.setProperty("gardenStatSupport", True)
        self.streak_support.setWordWrap(False)
        streak_layout.addLayout(streak_heading)
        streak_layout.addLayout(streak_value_row)
        streak_layout.addWidget(self.streak_support)

        currency_layout = QVBoxLayout(self.cells["currency"])
        currency_layout.setContentsMargins(14, 6, 14, 6)
        currency_layout.setSpacing(2)
        currency_label = QLabel("GARDEN COINS")
        currency_label.setProperty("gardenStatLabel", True)
        self.currency_value = QLabel("0")
        self.currency_value.setProperty("gardenLargeValue", True)
        self.currency_support = QLabel("Spend in the Nursery")
        self.currency_support.setProperty("gardenStatSupport", True)
        self.currency_support.setWordWrap(False)
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
        self.growth_support.setVisible(not compact)
        self.streak_support.setVisible(not compact and not onboarding_mode)
        self.currency_support.setVisible(not compact and not onboarding_mode)
        self.streak_label.setText("STREAK" if compact else "ANKI STREAK")
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
        self.cells["growth"].setEnabled(not enabled)
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
    ) -> None:
        safe_maximum = max(1, int(maximum))
        safe_current = min(safe_maximum, max(0, int(current)))
        self.growth_name.setText(str(plant_name))
        self.growth_stage.setText(str(stage).upper())
        self.growth_stage.setVisible(bool(stage))
        if not stage:
            self._growth_value_full_text = "—"
            self.growth_support.setText("Choose an unfinished plant to begin earning Growth")
        else:
            self._growth_value_full_text = (
                "Complete" if fully_grown else f"{safe_current:,} / {safe_maximum:,} Growth"
            )
            self.growth_support.setText(
                "Rare · Fully grown"
                if fully_grown else
                f"{stage} · About {max(1, (max(0, int(remaining)) + 9) // 10):,} eligible answers to {next_stage or 'the next stage'}"
            )
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
        self.setMinimumSize(640, 420)
        self.resize(*_fit_dialog_to_screen(self, 820, 620, width_ratio=0.88, height_ratio=0.88))
        self.setMaximumWidth(820)
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
        self.setMinimumSize(620, 460)
        self.setMaximumWidth(740)
        screen = parent.screen() if hasattr(parent, "screen") else None
        maximum_height = max(
            500,
            int(screen.availableGeometry().height()) - 96 if screen is not None else 620,
        )
        self.setMaximumHeight(maximum_height)
        self.resize(740, min(570, maximum_height))
        self.setStyleSheet(_garden_dialog_stylesheet() + """
            QWidget[detailBodyPanel='true'] { background:#0b1f1b; }
            QLabel[detailTitle='true'] { color:#f5f7e8; font-size:20px; font-weight:800; }
            QLabel[detailSection='true'] { color:#f3f6e9; font-size:14px; font-weight:750; }
            QLabel[detailBody='true'] { color:#c5d3c9; font-size:14px; }
            QLabel[detailSupport='true'] { color:#a9bdb0; font-size:13px; }
            QLabel[detailMetric='true'] { color:#f5f7e8; font-size:31px; font-weight:800; }
            QLabel[detailGoldMetric='true'] { color:#f0ca78; font-size:32px; font-weight:800; }
            QLabel[detailBadge='true'] { color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:800; }
            QLabel[detailStatus='true'] { color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 8px; font-size:13px; font-weight:700; }
            QLabel[detailTableHeader='true'] { color:#91aa9b; font-size:11px; font-weight:800; }
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
            QLabel[streakDayLabel='true'] { color:#b9ccc0; font-size:13px; font-weight:700; }
            QLabel[streakDayValue='true'] { color:#f3f6e9; font-size:14px; font-weight:800; }
            QProgressBar { border:0; border-radius:4px; background:#203d35; min-height:8px; max-height:8px; }
            QProgressBar::chunk { border-radius:4px; background:#65c487; }
            QScrollArea { background:transparent; border:0; }
            QPushButton[detailDisclosure='true'] { text-align:left; min-height:36px; background:transparent; border:0; border-bottom:1px solid #345348; color:#c8d8cd; }
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

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        center = parent.mapToGlobal(parent.rect().center())
        frame = self.frameGeometry()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    def open_metric(self, metric: str) -> None:
        keys = [key for key, _label in self.METRIC_TABS]
        key = str(metric)
        index = keys.index(key) if key in keys else 0
        self.refresh()
        self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()
        self.activateWindow()
        self.tabs.tabBar().setFocus()
        QTimer.singleShot(0, self._center_on_parent)

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
                f"{display.stage_points:,} / {display.stage_goal:,} Growth",
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
                f"{display.points_remaining:,} Growth remaining — "
                f"about {answers:,} eligible {'answer' if answers == 1 else 'answers'}"
            )
        identity.addWidget(self._label(support_text, "detailSupport"))
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
        today_layout.addWidget(StatSummary([
            ("Growth today", f"{int(stats.growth_earned):,}"),
            ("Card-answer Growth", f"{answer_growth:,}"),
            ("Growth Charges", f"{charge_growth:,}"),
        ]))
        if int(stats.growth_earned) == 0:
            today_layout.addWidget(EmptyState(
                "No Growth earned today",
                f"Answer an eligible card to begin growing {plant.name}.",
            ))
        self._disclosure(
            today_layout,
            "Growth breakdown",
            [(label, f"{value:,}") for label, value in contributions],
            expanded=bool(active_rows),
        )
        today.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        apply_explanatory_tooltip(today, GROWTH_EXPLANATION)
        layout.addWidget(today)

        charges = QFrame()
        charges.setProperty("detailCard", True)
        charges_layout = QVBoxLayout(charges)
        charges_layout.setContentsMargins(14, 12, 14, 12)
        charges_layout.setSpacing(4)
        charges_layout.addWidget(self._label("Growth Charges", "detailSection"))
        charges_layout.addWidget(self._label(
            f"Growth Charges applied today: {charge_growth:,}\nInstant Growth from stored charges.",
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
            row.addWidget(self._label(
                f"{spec.name}: {quantity:,} available — +{spec.growth:,} Growth",
                "detailBody",
            ), 1)
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
            if stage_key == "rare" and state == "upcoming":
                preview = QLabel("?")
                preview.setFixedSize(58, 58)
                preview.setProperty("stagePreview", True)
                preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                preview.setAccessibleName("Undiscovered Rare-stage silhouette")
            else:
                preview = _asset_preview_label(
                    self.engine, plant.species, stage_key, size=58
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
        days = max(0, int(state.streak_days))
        bonus = self.engine.current_streak_bonus_percent()
        maintained_today = bool(
            int(getattr(state.daily_stats, "reviewed", 0) or 0) > 0
            or (
                days > 0
                and int(getattr(state, "total_reviews", 0) or 0) > 0
                and str(getattr(state, "last_active_day", "")) == str(state.daily_stats.day)
            )
        )
        status_text = (
            "Start today" if days == 0 else
            "Active" if maintained_today else
            "At risk"
        )
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
        status = self._label(status_text, "detailStatus")
        status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(metric, 1)
        status_row.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(status_row)
        hero_layout.addWidget(self._label(
            f"Next milestone: Day {next_day:,}", "detailSection"
        ))
        next_progress = ProgressBar("Progress to the next Anki streak milestone")
        next_progress.set_progress(
            f"{days:,} / {next_day:,} {'day' if next_day == 1 else 'days'}",
            min(days, next_day),
            max(1, next_day),
            value_text=f"{days:,} / {next_day:,}",
        )
        hero_layout.addWidget(next_progress)
        week = QHBoxLayout()
        week.setSpacing(7)
        try:
            current_day = date.fromisoformat(str(state.daily_stats.day)[:10])
        except (TypeError, ValueError):
            current_day = date.today()
        try:
            last_active = date.fromisoformat(str(state.last_active_day)[:10])
        except (TypeError, ValueError):
            last_active = current_day if maintained_today else current_day - timedelta(days=1)
        streak_start = last_active - timedelta(days=max(0, days - 1))
        week_start = current_day - timedelta(days=current_day.weekday())
        for offset in range(7):
            calendar_day = week_start + timedelta(days=offset)
            complete = bool(days > 0 and streak_start <= calendar_day <= last_active)
            day_state = (
                "today" if calendar_day == current_day else
                "complete" if complete else
                "upcoming" if calendar_day > current_day else
                "missed"
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
            date_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state_icon = self._label(
                "✓" if complete else "●" if calendar_day == current_day else "—" if calendar_day < current_day else "○",
                "streakDayValue",
            )
            state_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_value = self._label(
                "Today" if calendar_day == current_day else
                "Complete" if complete else
                "Upcoming" if calendar_day > current_day else
                "Missed",
                "streakDayLabel",
            )
            day_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_layout.addWidget(day_name)
            day_layout.addWidget(date_value)
            day_layout.addWidget(state_icon)
            day_layout.addWidget(day_value)
            day.setAccessibleName(
                f"{calendar_day.strftime('%A')}, "
                f"{'today' if calendar_day == current_day else 'streak complete' if complete else 'upcoming' if calendar_day > current_day else 'missed'}"
            )
            week.addWidget(day, 1)
        hero_layout.addLayout(week)
        metadata = QHBoxLayout()
        metadata.addWidget(self._label("Current Growth bonus", "detailSupport"))
        metadata.addWidget(self._label(f"+{bonus}%", "detailSection"))
        metadata.addStretch(1)
        cutoff_sentence = (
            f"Your Anki day ends at {cutoff_text}."
            if cutoff_text != "Unavailable" else
            "Your Anki day cutoff is currently unavailable."
        )
        metadata.addWidget(self._label(cutoff_sentence, "detailBody"))
        hero_layout.addLayout(metadata)
        layout.addWidget(hero)

        instruction = (
            "Answer one eligible card today to start your streak."
            if days == 0 else
            "Today counted toward your streak."
            if maintained_today else
            "Study today to continue your streak."
        )
        layout.addWidget(self._label(instruction, "detailBody"))

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
            reached = days >= day
            reward_milestone = day in STREAK_REWARD_MILESTONES
            claimed = day in set(getattr(state, "claimed_streak_rewards", []) or [])
            status_text = (
                "Claimed" if reached and reward_milestone and claimed else
                "Reward pending" if reached and reward_milestone else
                "Reached" if reached else
                "Next" if day == next_day else
                "Upcoming"
            )
            milestone = self._label(_day_count(day), "detailBody")
            reward = self._label(self._streak_reward_text(day, percent), "detailBody")
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
        balance_copy.addWidget(self._label(
            f"{balance:,} Garden {'Coin' if balance == 1 else 'Coins'}",
            "detailGoldMetric",
        ))
        balance_copy.addWidget(self._label("Available balance", "detailBody"))
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
                "Garden Coins earned from goals, milestones, plant stages, and study gifts will appear here.",
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
                amount.setAlignment(Qt.AlignmentFlag.AlignRight)
                resulting = self._label(f"{int(transaction.balance):,}", "detailBody")
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
            ("Complete daily study goals", "Finish eligible daily goals to earn rewards."),
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
        self.dialog_subtitle.setText(
            "Study progress, plant Growth, rewards, achievements, and collection."
        )
        self.dialog_subtitle.show()
        self.setMinimumSize(720, 500)
        self.setMaximumWidth(1000)
        self.resize(*_fit_dialog_to_screen(self, 940, 680, width_ratio=0.92, height_ratio=0.90))

        metric_pages: dict[str, QWidget] = {}
        for key, _label in self.METRIC_TABS:
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if page is not None:
                metric_pages[key] = page
        self.body_layout.removeWidget(self.tabs)
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
            "Eligible card answers give the nurtured plant base Growth. "
            "Your Anki streak, active Fertilizer, Booster Potions, equipped Weather and Scenery, "
            "and Growth Charges can add more. Existing Growth never moves between plants.",
        )
        QTimer.singleShot(0, self.help_button.setFocus)

    def _page_changed(self, key: str) -> None:
        self.set_dialog_title("Garden Progress")
        self.footer.hide()
        button = self.navigation.buttons.get(str(key))
        if button is not None:
            self.dialog_subtitle.setAccessibleDescription(
                f"Showing {button.text()} in Garden Progress."
            )

    def open_page(self, key: str = "overview") -> None:
        self.refresh()
        self.navigation.set_current(str(key))
        self.show()
        self.raise_()
        self.activateWindow()
        button = self.navigation.buttons.get(str(key)) or self.navigation.buttons.get("overview")
        if button is not None:
            QTimer.singleShot(0, button.setFocus)
        QTimer.singleShot(0, self._center_on_parent)

    def open_metric(self, metric: str) -> None:
        self.open_page(metric)

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "navigation"):
            self.navigation.set_compact(event.size().width() < 820)
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
        self._compact = False
        self.setMinimumSize(680, 480)
        self.setMaximumWidth(1120)
        self.resize(*_fit_dialog_to_screen(self, 1040, 700, width_ratio=0.92, height_ratio=0.90))
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
        library_layout = QVBoxLayout(self.library)
        library_layout.setContentsMargins(12, 10, 12, 12)
        library_layout.setSpacing(10)
        self.option_tabs = GardenTabs("Garden appearance categories")
        self.option_tabs.tabBar().setUsesScrollButtons(False)
        self.option_tabs.setStyleSheet("QTabBar::tab { padding-left:8px; padding-right:8px; }")
        self.scenery_page, self.scenery_grid = self._option_page("Scenery")
        self.weather_page, self.weather_grid = self._option_page("Weather")
        self.effects_page = QWidget()
        effects_layout = QVBoxLayout(self.effects_page)
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
        advanced = SectionCard()
        advanced_layout = QHBoxLayout(advanced)
        advanced_layout.setContentsMargins(12, 10, 12, 10)
        advanced_copy = QLabel(
            "Advanced\nRestore the included Clear Skies and Verdant Twilight appearance."
        )
        advanced_copy.setProperty("dialogSubtitle", True)
        advanced_copy.setWordWrap(True)
        restore = QPushButton("Restore default appearance")
        _set_button_variant(restore, BUTTON_VARIANT_TERTIARY)
        restore.clicked.connect(self._restore_default_draft)
        advanced_layout.addWidget(advanced_copy, 1)
        advanced_layout.addWidget(restore)
        effects_layout.addWidget(effects_heading)
        effects_layout.addWidget(effects_intro)
        effects_layout.addWidget(self.show_weather)
        effects_layout.addWidget(self.show_scenery)
        effects_layout.addWidget(advanced)
        effects_layout.addStretch(1)
        self.option_tabs.addTab(self.scenery_page, "Scenery")
        self.option_tabs.addTab(self.weather_page, "Weather")
        self.option_tabs.addTab(self.effects_page, "Effects")
        library_layout.addWidget(self.option_tabs, 1)

        self.preview_panel = QFrame()
        self.preview_panel.setProperty("customizePreview", True)
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
        self.preview_scene.setMinimumSize(360, 300)
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview_selection)
        preview_layout.addWidget(self.preview_scene, 1)

        self.main_grid.addWidget(self.library, 0, 0)
        self.main_grid.addWidget(self.preview_panel, 0, 1)
        self.main_grid.setColumnStretch(0, 5)
        self.main_grid.setColumnStretch(1, 6)
        self.set_body_widget(body)

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

    def _option_page(self, accessible_name: str) -> tuple[QScrollArea, QGridLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName(f"{accessible_name} options")
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(4, 6, 18, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        scroll.setWidget(host)
        return scroll, grid

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
        selected = (
            self._draft_weather == item.item_id
            if item.kind == "weather" else
            self._draft_scenery == item.item_id
        )
        tile = QPushButton()
        tile.setProperty("environmentTile", True)
        tile.setCheckable(owned)
        tile.setChecked(selected)
        tile.setEnabled(owned)
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
            "Selected" if selected else
            "Owned" if owned else
            f"Locked · {item.price:,} coins" if item.price is not None else
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
        self.apply_changes.setEnabled(dirty)
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
        except Exception:
            background = weather = overlay = None
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
            self.unsaved.setText(_learner_text(message))
            self.unsaved.setAccessibleDescription(f"Customize Garden error: {message}")
            self.unsaved.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.unsaved.setFocus()
            return
        self._persisted_draft = self._draft_key()
        self._sync_dirty_state()
        self.unsaved.setText("Changes applied")
        self.unsaved.setAccessibleDescription("Garden appearance changes saved.")
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
        compact = event.size().width() < 820
        if compact != self._compact:
            self._compact = compact
            self.main_grid.removeWidget(self.library)
            self.main_grid.removeWidget(self.preview_panel)
            if compact:
                self.main_grid.addWidget(self.library, 0, 0)
                self.main_grid.addWidget(self.preview_panel, 1, 0)
                self.preview_scene.setMinimumHeight(280)
            else:
                self.main_grid.addWidget(self.library, 0, 0)
                self.main_grid.addWidget(self.preview_panel, 0, 1)
                self.preview_scene.setMinimumHeight(300)
        super().resizeEvent(event)

class GardenDashboard(QDialog):
    ROOT_MARGINS = (14, 12, 14, 16)
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
    COMPACT_LAYOUT_WIDTH = 900

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
        self.state_events = coordinator or GardenUiCoordinator(self)
        self.state_events.stateChanged.connect(self._on_state_changed)
        self._starter_selected_callback = starter_selected_callback
        self.settings_dialog: GardenSettingsDialog | None = None
        self.nursery_dialog: NurseryDialog | None = None
        self.story_dialog: PlantStoryDialog | None = None
        self.fertilizer_dialog: DialogShell | None = None
        self._undo_nurture_plant_id = ""
        self._starter_prompt_scheduled = False
        self._starter_setup_dismissed = False
        self._undo_placement: Any = None
        self._placement_draft: Any = None
        self._move_feedback_generation = 0
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
        self._header_metrics_compact: bool | None = None
        self._application_filter_installed = False
        self._skip_next_show_refresh = False
        self._home_surface_dirty = False
        self.setWindowTitle(UI_TEXT["app_title"])
        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(*self._recommended_window_size())
        self._build_ui()
        self._apply_responsive_layout(self.width())
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
        if not bool(getattr(state, "starter_selection_complete", False)):
            return UX_NO_STARTER
        active = self.engine.active_plant()
        if active is not None:
            return UX_ACTIVE_GROWTH if int(getattr(active, "growth_points", 0) or 0) > 0 else UX_STARTER_READY
        active_id = str(getattr(state, "active_plant_id", "") or "")
        pointed = next(
            (plant for plant in getattr(state, "plants", []) if str(getattr(plant, "plant_id", "")) == active_id),
            None,
        )
        if pointed is not None and bool(getattr(pointed, "fully_grown", False)):
            return UX_NURTURED_PLANT_COMPLETE
        # Growth routing records a null period when the nurtured plant reaches
        # Rare, so the saved active_plant_id is intentionally cleared. The
        # most recent named period still identifies the plant that just
        # completed without adding a new onboarding field.
        periods = sorted(
            list(getattr(state, "active_plant_periods", []) or []),
            key=lambda period: (str(getattr(period, "day", "")), int(getattr(period, "started_at_ms", 0) or 0)),
        )
        latest_period = periods[-1] if periods else None
        if latest_period is not None and getattr(latest_period, "plant_id", None) is None:
            completed_id = next(
                (
                    str(getattr(period, "plant_id", ""))
                    for period in reversed(periods[:-1])
                    if getattr(period, "plant_id", None)
                ),
                "",
            )
            completed = next(
                (
                    plant for plant in getattr(state, "plants", [])
                    if str(getattr(plant, "plant_id", "")) == completed_id
                ),
                None,
            )
            if completed is not None and bool(getattr(completed, "fully_grown", False)):
                return UX_NURTURED_PLANT_COMPLETE
        if getattr(state, "plants", None) and all(bool(getattr(plant, "fully_grown", False)) for plant in state.plants):
            return UX_NURTURED_PLANT_COMPLETE
        return UX_STARTER_READY

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
            QDialog {{ background: {self.APP_BG}; color: {self.TEXT_PRIMARY}; }}
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
            QLabel[plantStageBadge='true'] {{ color:#B8C5BF; background:#123228; border:0; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:700; letter-spacing:.5px; }}
            QLabel[nurturedBadge='true'] {{ {_nurtured_badge_declarations()} }}
            QLabel[plantCardSection='true'] {{ color:#d8b875; font-size:11px; font-weight:800; letter-spacing:1px; padding-top:3px; }}
            QLabel[plantProgressLabel='true'] {{ color:#aac0b1; font-size:13px; }}
            QLabel[plantGrowthValue='true'] {{ color:#f5f7e8; font-size:26px; font-weight:800; }}
            QFrame[plantStatus='true'] {{ background:#17312b; border:0; border-radius:8px; padding:7px 9px; }}
            QFrame[plantCard='true'] QPushButton {{ min-height:{PLANT_ACTION_MIN_HEIGHT}px; }}
            QLabel[plantStatusLabel='true'] {{ color:#91aa9b; font-size:11px; font-weight:800; letter-spacing:.8px; }}
            QLabel[plantStatusValue='true'] {{ color:#e9d9ac; font-size:13px; font-weight:700; }}
            QFrame[plantGuidance='true'] {{ background:#123228; border:0; border-left:3px solid #5CC58B; border-radius:8px; }}
            QLabel[plantGuidanceStep='true'] {{ color:#82E2AC; font-size:11px; font-weight:700; letter-spacing:.8px; }}
            QLabel[plantGuidanceText='true'] {{ color:#CBD6D0; font-size:13px; }}
            QFrame[movePanel='true'] {{ background:rgba(12,38,31,235); border:1px solid #4F806E; border-radius:10px; }}
            QFrame[gardenStats='true'] {{ background:#0C261F; border:1px solid {self.CARD_BORDER}; border-radius:10px; }}
            QPushButton[gardenStatCell='true'] {{ min-height:68px; text-align:left; background:transparent; border:0; border-radius:0; padding:0; }}
            QPushButton[gardenStatCell='true'][separator='true'] {{ border-right:1px solid {self.CARD_BORDER}; }}
            QPushButton[gardenStatCell='true']:hover {{ background:#173B30; }}
            QPushButton[gardenStatCell='true']:pressed {{ background:#123228; }}
            QPushButton[gardenStatCell='true']:focus {{ border:2px solid #82E2AC; }}
            QLabel[gardenStatLabel='true'] {{ color:#91aa9b; font-size:11px; font-weight:800; letter-spacing:.8px; }}
            QLabel[gardenPlantName='true'] {{ color:#F4F7F5; font-size:16px; font-weight:700; }}
            QLabel[gardenStageBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:800; letter-spacing:.7px; }}
            QLabel[gardenGrowthValue='true'] {{ color:#F4F7F5; font-size:16px; font-weight:700; }}
            QLabel[gardenLargeValue='true'] {{ color:#F4F7F5; font-size:22px; font-weight:700; }}
            QLabel[gardenValueUnit='true'] {{ color:#c8d5cb; font-size:15px; padding-bottom:2px; }}
            QLabel[gardenBonusBadge='true'] {{ color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 7px; font-size:11px; font-weight:700; }}
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
            QLabel[catalogStatus='true'] {{ color:#CFE0D6; background:#123228; border-radius:8px; padding:4px 7px; font-size:11px; font-weight:700; }}
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
            {_button_stylesheet()}
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
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setWidget(page)
        outer.addWidget(self.page_scroll)

        self.top_bar = QFrame()
        top = self.top_bar
        top.setProperty("topBar", True)
        top.setMinimumHeight(92)
        top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.header_grid = QGridLayout(top)
        self.header_grid.setContentsMargins(14, 8, 14, 8)
        self.header_grid.setHorizontalSpacing(12)
        self.header_grid.setVerticalSpacing(8)
        self.title_stack_widget = QWidget()
        self.title_stack_widget.setMinimumWidth(0)
        self.title_stack_widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        title_stack = QVBoxLayout()
        self.title_stack_widget.setLayout(title_stack)
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(1)
        self.product_label = QLabel("ANKI GARDEN")
        self.product_label.setStyleSheet(
            "color:#d8b875; font-size:11px; font-weight:800; letter-spacing:1.2px;"
        )
        self.title_label = QLabel("")
        self._apply_typography(self.title_label, "title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
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
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setProperty("headerAction", True)
        self.settings_btn.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
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
        action_row = QHBoxLayout(self.header_actions_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        action_row.addWidget(self.starter_header_btn)
        action_row.addWidget(self.nursery_recovery_btn)
        action_row.addWidget(self.progress_btn)
        action_row.addWidget(self.customize_btn)
        action_row.addWidget(self.settings_btn)
        self.garden_stats_bar = GardenStatsStrip()
        self.garden_stats_bar.setMinimumHeight(80)
        self.garden_stats_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.garden_stats_bar.setMinimumWidth(390)
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
            "color:#82E2AC; font-size:11px; font-weight:700; letter-spacing:.8px;"
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
        self.placement_note = QLabel("")
        self.placement_note.setTextFormat(Qt.TextFormat.PlainText)
        self.placement_note.setWordWrap(True)
        self.placement_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._apply_typography(self.placement_note, "muted-body")
        self.placement_note.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.placement_note.setAccessibleName("Plant move status")
        self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.placement_note.hide()
        self.undo_move_btn = QPushButton("Undo")
        _set_button_variant(self.undo_move_btn, BUTTON_VARIANT_SECONDARY)
        self.undo_move_btn.setAccessibleName("Undo the most recent plant move")
        apply_explanatory_tooltip(self.undo_move_btn, "Restore the previous plant arrangement.")
        self.undo_move_btn.clicked.connect(self._undo_move)
        self.undo_move_btn.hide()
        placement_row = QHBoxLayout()
        placement_row.setSpacing(8)
        placement_row.addWidget(self.placement_note, 1)
        placement_row.addWidget(self.undo_move_btn)
        self.stage_transition_note = QLabel("")
        self.stage_transition_note.setTextFormat(Qt.TextFormat.PlainText)
        self.stage_transition_note.setWordWrap(True)
        self.stage_transition_note.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.stage_transition_note.setAccessibleName("Garden progress update")
        self._apply_typography(self.stage_transition_note, "muted-body")
        self.stage_transition_note.setStyleSheet("color:#f4d58a; font-size:14px; font-weight:700;")
        self.stage_transition_note.hide()
        self.same_day_catchup_note = QLabel("")
        self.same_day_catchup_note.setTextFormat(Qt.TextFormat.PlainText)
        self.same_day_catchup_note.setWordWrap(True)
        self.same_day_catchup_note.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.toast_region = ToastRegion(self.scene)
        self.toast_region.shown.connect(self._position_scene_overlays)
        feedback_layout = QVBoxLayout(self.feedback_panel)
        feedback_layout.setContentsMargins(0, 0, 0, 0)
        feedback_layout.setSpacing(5)
        feedback_layout.addLayout(placement_row)
        feedback_layout.addWidget(self.stage_transition_note)
        feedback_layout.addWidget(self.same_day_catchup_note)
        feedback_layout.addWidget(self.status_notice)
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
        milestone_copy = QVBoxLayout()
        milestone_copy.setSpacing(2)
        milestone_copy.addWidget(self.milestone_title)
        milestone_copy.addWidget(self.milestone_note)
        self.milestone_layout.addLayout(milestone_copy, 1)
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

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)

    def _open_progress(self) -> None:
        self._progress_return_focus = self.focusWidget()
        self.progress_dialog.open_page("overview")

    def _open_customize(self) -> None:
        if self.scene._interaction.placing:
            return
        self.scene.dismiss_selection()
        self.customize_dialog.prepare_to_show()
        self.customize_dialog.remember_invoker(self.customize_btn)
        self.customize_dialog.show()
        self.customize_dialog.raise_()
        self.customize_dialog.activateWindow()

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
        streak_days = snapshot.streak_days
        streak_bonus = snapshot.streak_bonus_percent
        streak_value = (
            "No streak yet\nStudy today to start"
            if streak_days == 0
            else (
                f"{streak_days} {'day' if streak_days == 1 else 'days'}\n"
                f"+{streak_bonus}% Growth"
            )
        )
        active = self.engine.active_plant()
        if active is None:
            active_growth = "Choose a plant"
            growth_now, growth_max = 0, 1
            growth_name, growth_stage, growth_next_stage, growth_total, growth_remaining, growth_complete = (
                "Choose a plant", "", "", 0, 0, False
            )
            growth_progress_text = "Choose an unfinished plant to begin earning Growth."
        else:
            progress = growth_display(active.growth_points)
            active_growth = (
                f"{active.growth_points:,} Growth\nFully grown"
                if progress.fully_grown else
                f"{active.growth_points:,} Growth\n"
                f"Needs {progress.points_remaining:,} more to reach "
                f"{format_status_label(progress.next_stage or 'next stage')}"
            )
            growth_now = 1 if progress.fully_grown else progress.stage_points
            growth_max = 1 if progress.fully_grown else max(1, progress.stage_goal)
            growth_name = active.name
            growth_stage = format_status_label(progress.stage)
            growth_next_stage = format_status_label(progress.next_stage or "")
            growth_total = active.growth_points
            growth_remaining = progress.points_remaining
            growth_complete = progress.fully_grown
            growth_progress_text = (
                f"{active.name} is fully grown."
                if progress.fully_grown else
                f"{progress.stage_points:,} of {progress.stage_goal:,} Growth to "
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
        )
        self.garden_stats_bar.set_streak_details(
            days=streak_days,
            bonus_percent=streak_bonus,
            support=_streak_support_text(streak_days, streak_bonus),
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
                    self.config.value("enable_animations", True)
                    and not self.config.value("reduced_motion", False)
                ),
                "animation_intensity": 0.7,
                "weather_particle_density": 1.0,
                "asset_paths": {
                    "background": self._resolved_asset_payload("resolve_background_asset", "resolve_background_image"),
                    "garden_overlay": self._resolved_asset_payload(
                        "resolve_garden_overlay_asset",
                        "resolve_garden_overlay_image",
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
                progress = LabeledProgress(f"{ach.name} progress")
                progress.set_progress(
                    "Progress",
                    display.current,
                    display.target,
                    value_text=display.value_text,
                )
                card_layout.addWidget(progress)
                if ach.unlocked and getattr(ach, "unlocked_at", None):
                    unlocked = QLabel(f"Unlocked {self._local_date(ach.unlocked_at)}")
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
            not self.config.value("show_progress_notifications", False)
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
        due_complete = bool(getattr(due_status, "complete", False))
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
        elif stats.completed_due_cards:
            daily_status = "Daily study goal complete"
            daily_explanation = "Today’s all-due reward has been earned."
            progress_current = 1
        elif due_complete and int(stats.reviewed) == 0:
            daily_status = "Answer one eligible card"
            daily_explanation = "No cards are due; one eligible answer activates today’s reward."
            progress_current = 0
        else:
            daily_status = f"{remaining:,} cards remaining"
            daily_explanation = "Finish today’s due review and learning cards."
            progress_current = 0
        status = QLabel(daily_status)
        status.setProperty("rowTitle", True)
        status.setWordWrap(True)
        daily_layout.addWidget(status)
        goal_progress = ProgressBar("Daily study goal")
        goal_progress.set_progress(
            "Finish today’s due cards",
            progress_current,
            1,
            value_text="Complete" if progress_current else "In progress",
        )
        daily_layout.addWidget(goal_progress)
        explanation = QLabel(daily_explanation)
        explanation.setProperty("dialogSubtitle", True)
        explanation.setWordWrap(True)
        daily_layout.addWidget(explanation)
        reward = QLabel(
            f"Reward: +{reward_coins:,} Garden Coins"
            + (f" and +{reward_growth:,} Growth" if reward_growth else "")
        )
        reward.setProperty("dialogSubtitle", True)
        reward.setWordWrap(True)
        daily_layout.addWidget(reward)
        continue_studying = QPushButton("Continue studying")
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
                "Choose an unfinished plant so eligible answers have somewhere to add Growth.",
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
            row_layout.addWidget(reason, 1)
            row_layout.addWidget(amount)
            recent_layout.addWidget(row)
        recent_layout.addStretch(1)

        milestone = SectionCard()
        milestone_layout = QVBoxLayout(milestone)
        milestone_layout.setContentsMargins(14, 12, 14, 12)
        milestone_layout.setSpacing(7)
        milestone_title = QLabel("Next milestone")
        milestone_title.setProperty("rowTitle", True)
        milestone_layout.addWidget(milestone_title)
        if active_plant is not None:
            display = growth_display(active_plant.growth_points)
            if display.fully_grown:
                milestone_text = "Choose another plant to continue progressing."
                requirement = "Rare stage reached"
            else:
                milestone_text = f"{format_status_label(display.next_stage or 'Next stage')} for {active_plant.name}"
                requirement = f"{display.points_remaining:,} Growth remaining"
            milestone_layout.addWidget(QLabel(milestone_text))
            requirement_label = QLabel(requirement)
            requirement_label.setProperty("dialogSubtitle", True)
            requirement_label.setWordWrap(True)
            milestone_layout.addWidget(requirement_label)
        else:
            milestone_layout.addWidget(QLabel("Nurture a plant to reveal its next stage milestone."))
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
            milestone_layout.addWidget(streak_reward)
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
        guide_nurture = bool(
            plant is not None
            and self._derived_ux_state() == UX_STARTER_READY
            and int(self.config.value("onboarding_version", 0) or 0) < CURRENT_ONBOARDING_VERSION
        )
        self.plant_card.set_onboarding_guidance(guide_nurture)
        if plant is None:
            self._update_scene_height()
        self._position_plant_card()
        if plant is not None:
            QTimer.singleShot(0, self._ensure_selected_card_visible)
            # Scene and wrapped-text geometry can settle over more than one
            # layout pass after a DPI change. Recheck without stealing focus.
            QTimer.singleShot(120, self._ensure_selected_card_visible)
            QTimer.singleShot(260, self._ensure_selected_card_visible)

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
            self._apply_responsive_layout(event.size().width())
        self._update_scene_height(event.size().height())
        QTimer.singleShot(0, self._position_plant_card)
        QTimer.singleShot(0, self._position_onboarding_coachmark)
        QTimer.singleShot(0, self._position_scene_overlays)
        super().resizeEvent(event)

    def _position_scene_overlays(self) -> None:
        if not hasattr(self, "scene"):
            return
        top = 12
        if self.rearrange_bar.isVisible():
            bar_width = min(620, max(280, self.scene.width() - 24))
            self.rearrange_bar.setFixedWidth(bar_width)
            self.rearrange_bar.adjustSize()
            bar_height = min(96, max(56, self.rearrange_bar.sizeHint().height()))
            self.rearrange_bar.setGeometry(
                max(12, (self.scene.width() - bar_width) // 2),
                12,
                bar_width,
                bar_height,
            )
            self.rearrange_bar.raise_()
            top = 12 + bar_height + 8
        if self.toast_region.isVisible():
            toast_width = min(360, max(300, self.scene.width() - 24))
            self.toast_region.setFixedWidth(toast_width)
            self.toast_region.adjustSize()
            toast_height = min(124, max(56, self.toast_region.sizeHint().height()))
            toast_x = self.scene.width() - toast_width - 12
            self.toast_region.setGeometry(
                max(12, toast_x),
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
        compact = dashboard_layout_is_compact(width)
        # Keep the product header in three stable zones. At ordinary desktop
        # widths the actions and title get their own row so the metric strip
        # can use the full width; only the metric copy itself compacts below
        # 1,000 px.
        header_compact = int(width) < 1360
        metrics_compact = int(width) < 1000
        compact_changed = compact != self._compact_layout
        header_changed = header_compact != self._header_compact_layout
        metrics_changed = metrics_compact != self._header_metrics_compact
        if not compact_changed and not header_changed and not metrics_changed:
            return
        if compact_changed:
            self._compact_layout = compact
            direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            self.milestone_layout.setDirection(direction)
            self.rearrange_bar.set_compact(compact)
            self._set_plant_card_mode(compact)
        self._header_compact_layout = header_compact
        self._header_metrics_compact = metrics_compact
        self.garden_stats_bar.set_compact(metrics_compact)
        # The large tabular values need a little more vertical breathing room
        # at high display scaling. Keep this adaptive instead of forcing the
        # metric strip below its child cards' minimum height.
        self.garden_stats_bar.setMinimumHeight(72 if metrics_compact else 80)
        for widget in (
            self.title_stack_widget,
            self.garden_stats_bar,
            self.header_actions_widget,
        ):
            self.header_grid.removeWidget(widget)
        if header_compact:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0)
            self.header_grid.addWidget(self.header_actions_widget, 0, 1)
            self.header_grid.addWidget(self.garden_stats_bar, 1, 0, 1, 2)
            self.header_grid.setColumnStretch(0, 1)
            self.header_grid.setColumnStretch(1, 0)
            self.header_grid.setColumnStretch(2, 0)
            self.top_bar.setMinimumHeight(140 if metrics_compact else 148)
        else:
            self.header_grid.addWidget(self.title_stack_widget, 0, 0)
            self.header_grid.addWidget(self.garden_stats_bar, 0, 1)
            self.header_grid.addWidget(self.header_actions_widget, 0, 2)
            self.header_grid.setColumnStretch(0, 0)
            self.header_grid.setColumnStretch(1, 1)
            self.header_grid.setColumnStretch(2, 0)
            self.top_bar.setMinimumHeight(96)
        self.top_bar.updateGeometry()
        self.header_grid.activate()
        self.top_bar.adjustSize()

    def _set_plant_card_mode(self, compact: bool) -> None:
        del compact
        # Actual side-card vs bottom-sheet placement depends on scene width,
        # not the broader dashboard chrome breakpoint.
        QTimer.singleShot(0, self._position_plant_card)

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
        narrow_sheet = self.scene.width() < 540
        if narrow_sheet:
            if self.plant_card.parentWidget() is not self.plant_card_dock:
                self.plant_card.setParent(self.plant_card_dock)
                self.plant_card_dock_layout.addWidget(self.plant_card)
            connector = getattr(self.scene, "set_card_connector_geometry", None)
            if callable(connector):
                connector(None)
            if hasattr(self.plant_card, "setMaximumWidth"):
                self.plant_card.setMaximumWidth(16777215)
            self.plant_card.setFixedWidth(max(280, self.plant_card_dock.width() or self.scene.width()))
            self.plant_card.adjustSize()
            self.plant_card.show()
            self.plant_card_dock.show()
            return
        if hasattr(self, "plant_card_dock"):
            self.plant_card_dock.hide()
        if self.plant_card.parentWidget() is not self.scene:
            self.plant_card.setParent(self.scene)
        if hasattr(self.plant_card, "setMaximumWidth"):
            self.plant_card.setMaximumWidth(330)
        available_width = max(280, self.scene.width() - 24)
        desired_width = available_width if narrow_sheet else min(320, available_width)
        self.plant_card.setFixedWidth(desired_width)
        self.plant_card.adjustSize()
        # Qt's wrapped-label size hint can settle before the two-row action
        # grid has received its final width. Reserve the grid's vertical gap
        # so 125–150% font scaling never compresses the 40 px plant action targets.
        action_grid_reserve = 24
        desired_height = min(
            360,
            max(220, self.plant_card.sizeHint().height() + action_grid_reserve),
        )
        card_height = min(
            desired_height,
            max(220, self.scene.height() - 24),
        )
        geometry = self.scene.card_geometry(self.plant_card.width(), card_height)
        if geometry is None:
            self.plant_card.hide()
            connector = getattr(self.scene, "set_card_connector_geometry", None)
            if callable(connector):
                connector(None)
            return
        connector = getattr(self.scene, "set_card_connector_geometry", None)
        if callable(connector):
            connector(geometry, self.plant_card.plant_id)
        self.plant_card.setGeometry(
            round(geometry.x()), round(geometry.y()), round(geometry.width()), round(geometry.height())
        )
        self.plant_card.show()
        self.plant_card.raise_()

    def _ensure_selected_card_visible(self) -> None:
        if self.plant_card.plant_id and self.plant_card.isVisible():
            self.page_scroll.ensureWidgetVisible(self.plant_card, 12, 12)
            content = self.page_scroll.widget()
            viewport = self.page_scroll.viewport()
            if content is not None and viewport is not None:
                bottom = self.plant_card.mapTo(
                    content,
                    self.plant_card.rect().bottomLeft(),
                ).y()
                scroll_bar = self.page_scroll.verticalScrollBar()
                target = bottom + 12 - viewport.height()
                if target > scroll_bar.value():
                    scroll_bar.setValue(min(scroll_bar.maximum(), target))

    def _ensure_move_controls_visible(self) -> None:
        target = self.rearrange_bar if self.rearrange_bar.isVisible() else self.placement_note
        if target.isVisible():
            self.page_scroll.ensureWidgetVisible(target, 12, 12)

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
            and watched.window() is self
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
        available_height = max(300, int(viewport_height or self.height()) - 160)
        target = max(300, min(680, available_height))
        self.scene.setMinimumHeight(target)
        self.scene.setMaximumHeight(target)

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
            return
        self.same_day_catchup_note.show()
        self.same_day_catchup_note.setText(
            f"Counted {_card_answer_count(review_count)} from same-day sync: "
            f"+{growth_gain:,} Growth."
        )
        self.same_day_catchup_note.setAccessibleDescription(self.same_day_catchup_note.text())

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
                f"{name}: +{int(fertilizer.growth_per_answer)} Growth per answer\n"
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
            f"{name}: +{int(fertilizer.growth_per_answer)} Growth per answer\n"
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
        return f"+{int(getattr(booster, 'growth_per_answer', 0))} Growth per answer, {duration} remaining"

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
            "Future eligible answers will add Growth here."
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
        # Starting a new move retires the previous move's Undo contract; one
        # visible Undo must always refer to the interaction currently shown.
        self._undo_placement = None
        self._move_feedback_generation += 1
        self._clear_move_feedback()
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
        self._move_feedback_generation += 1
        self._placement_draft = None
        self.scene.finish_move("Move cancelled. Plant selection remains available.")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: move cancelled but persisted scene did not refresh")
        self._clear_move_feedback()
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
        self._move_feedback_generation += 1
        self._placement_draft = None
        self.scene.finish_move(f"Move not saved. {message}")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: rejected move could not refresh persisted scene")
        self.placement_note.setText(message)
        self.placement_note.setAccessibleDescription(message)
        self.placement_note.setStyleSheet("color:#ffd0d0; font-size:13px;")
        self.placement_note.show()
        self.scene.setFocus()
        self.undo_move_btn.setVisible(self._undo_placement is not None)
        if selected_id:
            self.scene.keep_card_open(selected_id, message)
            self._refresh_selected_plant_card()
        self.toast_region.show_message(message, error=True, duration_ms=0)

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
        self.placement_note.setText("Plant arrangement saved.")
        self.placement_note.setAccessibleDescription("Plant arrangement saved.")
        self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.placement_note.show()
        self.undo_move_btn.setVisible(self._undo_placement is not None)
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
        self.placement_note.setText(result)
        self.placement_note.setAccessibleDescription(result)
        self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.placement_note.show()
        self.undo_move_btn.setVisible(self._undo_placement is not None)
        if self._undo_placement is not None:
            self.toast_region.show_message(
                result,
                action_text="Undo Move",
                callback=self._undo_move,
            )
        self.scene.setFocus()
        self._move_feedback_generation += 1
        generation = self._move_feedback_generation
        QTimer.singleShot(6000, lambda: self._clear_move_feedback(generation))

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
                self.placement_note.setText(message)
                self.placement_note.show()
                self.undo_move_btn.setVisible(bool(self._placement_draft.history))
            return
        if self._undo_placement is None:
            return
        ok, message, _inverse = self.engine.restore_placement(self._undo_placement)
        if ok:
            self._undo_placement = None
            self._refresh_after_commit("move undo")
            self.placement_note.setText("Move undone.")
            self.placement_note.setAccessibleDescription("Move undone.")
            self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
            self.placement_note.show()
            self.undo_move_btn.hide()
            self._move_feedback_generation += 1
            generation = self._move_feedback_generation
            QTimer.singleShot(3000, lambda: self._clear_move_feedback(generation))
            self.placement_note.setFocus()
            QTimer.singleShot(0, self._ensure_move_controls_visible)
        else:
            message = _learner_text(message)
            self.placement_note.setText(message)
            self.placement_note.setAccessibleDescription(message)
            self.placement_note.setStyleSheet("color:#ffd0d0; font-size:13px;")
            self.placement_note.show()
            retryable = message == "The previous arrangement could not be restored."
            if not retryable:
                self._undo_placement = None
            self.undo_move_btn.setVisible(retryable)
            self._move_feedback_generation += 1
            self.placement_note.setFocus()
            QTimer.singleShot(0, self._ensure_move_controls_visible)

    def _clear_move_feedback(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._move_feedback_generation:
            return
        self.placement_note.setText("")
        self.placement_note.hide()
        self.undo_move_btn.hide()

    def _refresh_onboarding(self) -> None:
        ux_state = self._derived_ux_state()
        starter_incomplete = ux_state == UX_NO_STARTER
        nurture_step = bool(
            ux_state == UX_STARTER_READY
            and getattr(self.storage.state, "plants", None)
            and int(self.config.value("onboarding_version", 0) or 0) < CURRENT_ONBOARDING_VERSION
        )
        guided = starter_incomplete or nurture_step
        self.starter_header_btn.setVisible(starter_incomplete)
        self.progress_btn.setVisible(not guided)
        self.customize_btn.setVisible(not guided)
        self.settings_btn.setVisible(not guided)
        self.garden_stats_bar.set_onboarding_mode(guided)
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
            kind = QLabel("Garden species")
            kind.setProperty("catalogStatus", True)
            kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kind.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            layout.addWidget(title)
            layout.addWidget(status)
            layout.addWidget(kind, 0, Qt.AlignmentFlag.AlignHCenter)
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
            self.collection_list.add_empty(
                "No plants match this filter",
                "Choose another collection filter to see available species.",
            )
        self.collection_list.finish()

    def _set_collection_filter(self, selected: str) -> None:
        self._collection_filter = selected if selected in {"all", "discovered", "locked"} else "all"
        self._refresh_collection_list()

    def _open_species_overview(self, species: str) -> None:
        instances = [
            plant for plant in self.storage.state.plants
            if str(plant.species) == str(species)
        ]
        if not instances:
            return
        stage_rank = {stage: index for index, stage in enumerate(GROWTH_STAGES)}
        highest = max(
            instances,
            key=lambda plant: stage_rank.get(str(plant.growth_stage), 0),
        )
        dialog = GardenDialog(
            self.progress_dialog,
            format_status_label(species),
            subtitle="Species overview",
        )
        dialog.setMinimumSize(500, 420)
        dialog.resize(560, 500)
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
        dialog.set_body_widget(body)
        dialog.exec()

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
        action.setEnabled(owned and not equipped)
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
                "Each eligible post-starter card answer checks these bands in order; at most one reward can win. A daily scenery gift uses that answer's reward slot.",
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

    def _set_environment_visibility(self, kind: str, enabled: bool) -> None:
        ok, message = self.engine.set_environment_visibility(kind, enabled)
        if ok:
            self._refresh_after_commit("environment visibility")
        self.status_notice.setText(_learner_text(message))
        self.status_notice.setAccessibleDescription(_learner_text(message))
        self.status_notice.setStyleSheet("color:#baf3c6;" if ok else "color:#ffd0d0;")
        self.status_notice.show()

    def _set_collection_placement(self, plant_id: str, currently_planted: bool) -> None:
        if currently_planted:
            ok, message = self.engine.move_to_collection(plant_id)
        else:
            ok, message = self.engine.plant_from_collection(plant_id)
        if ok:
            self.scene.dismiss_selection()
            self._refresh_after_commit("collection placement")
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
            return
        dialog = DialogShell(self)
        self.fertilizer_dialog = dialog
        dialog.remember_invoker(self.plant_card.fertilize)
        dialog.setWindowTitle(f"Fertilize {plant.name}")
        dialog.setMinimumSize(520, 460)
        dialog.resize(*_fit_dialog_to_screen(dialog, 600, 580, width_ratio=0.78, height_ratio=0.86))
        dialog.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#071a15; color:#f3f7f2; }
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
        identity.addWidget(QLabel("Choose a timed Growth boost for eligible answers."))
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
        options = QWidget()
        options.setObjectName("fertilizerOptions")
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(0, 0, 2, 0)
        options_layout.setSpacing(9)
        options_scroll.setWidget(options)
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
        purchase_status.hide()
        options_layout.addWidget(purchase_status)
        for tier, spec in self.engine.FERTILIZERS.items():
            hours = spec.duration_seconds // 3600
            duration = f"{hours} hour" if hours == 1 else f"{hours} hours"
            card = QFrame()
            card.setProperty("fertilizerCard", True)
            card.setFixedHeight(112)
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
                f"+{spec.growth_per_answer} Growth per eligible answer\n"
                f"Duration: {duration} · Cost: {spec.price:,} Garden Coins"
            )
            detail.setProperty("fertilizerMeta", True)
            detail.setWordWrap(True)
            copy.addWidget(name)
            copy.addWidget(detail)
            if not affordable:
                shortfall = max(0, int(spec.price) - balance_value)
                shortfall_label = QLabel(
                    f"Need {shortfall:,} more {'coin' if shortfall == 1 else 'coins'}"
                )
                shortfall_label.setProperty("fertilizerShortfall", True)
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
            if not active:
                action_label = "Nurture first"
            elif not affordable:
                shortfall = max(0, int(spec.price) - balance_value)
                action_label = f"Need {shortfall:,} more {'coin' if shortfall == 1 else 'coins'}"
            elif current_tier:
                action_label = f"Replace for {spec.price:,}"
            else:
                action_label = f"Apply for {spec.price:,}"
            choose = QPushButton(action_label)
            _set_button_variant(
                choose,
                BUTTON_VARIANT_PRIMARY if affordable and active else BUTTON_VARIANT_SECONDARY,
            )
            choose.setAccessibleName(
                f"{semantic_action} for {spec.price:,} Garden Coins"
            )
            choose.setAccessibleDescription(
                f"{semantic_action}. {spec.name} adds {spec.growth_per_answer} Growth per eligible answer for {duration}. "
                f"Costs {spec.price:,} Garden Coins. {affordability}"
            )
            choose.setEnabled(affordable and active)
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
            choose.setMinimumHeight(BUTTON_MIN_HEIGHT)
            choose.clicked.connect(
                lambda _checked=False, selected_tier=tier, target=dialog, status=purchase_status:
                self._purchase_fertilizer_from_dialog(plant_id, selected_tier, target, status)
            )
            row.addWidget(choose)
            options_layout.addWidget(card)
        options_layout.addStretch(1)
        layout.addWidget(options_scroll, 1)
        footer = QHBoxLayout()
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
        layout.addLayout(footer)
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

    def _purchase_fertilizer(
        self,
        plant_id: str,
        tier: str,
        *,
        confirmation_parent: QWidget | None = None,
    ) -> tuple[bool, str]:
        plant = self.engine.plant_story(plant_id)
        if plant is None:
            return False, "That plant is no longer in your collection."
        replace = False
        current = plant.fertilizer
        if current is not None and current.active(time.time()) and current.tier != tier:
            answer = QMessageBox.question(
                confirmation_parent or self,
                "Replace active Fertilizer?",
                "Replacing the active Fertilizer discards its remaining time. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False, "Fertilizer was not changed."
            replace = True
        ok, message = self.engine.purchase_fertilizer(plant_id, tier, replace_active=replace)
        if ok:
            self._refresh_after_commit("Fertilizer purchase")
        return ok, message

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = GardenSettingsDialog(self, self.engine, self.config)
        elif self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.settings_dialog.prepare_to_show()
        self.settings_dialog.show()
        self.settings_dialog.raise_()
