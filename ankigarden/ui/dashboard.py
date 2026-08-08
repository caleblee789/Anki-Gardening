from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from aqt.qt import (
    QDialog,
    QBoxLayout,
    QDate,
    QDateEdit,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPixmap,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTimer,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    QColor,
    QSizePolicy,
    QGuiApplication,
    QEvent,
    QObject,
    QToolTip,
)
from .formatters import format_status_label
from .garden_studio import GardenStudioWidget
from .plant_display import (
    CURRENT_ONBOARDING_VERSION,
    achievement_progress_display,
    growth_display,
    onboarding_display,
    plant_health_display,
)
from .scene import GardenSceneWidget
from ..display_telemetry import DISPLAY_TELEMETRY
from ..config import ConfigError
from ..models.state import MAX_PLANT_NAME_LENGTH
from ..notices import USER_NOTICES

logger = logging.getLogger(__name__)

UI_TEXT = {
    "settings_window_title": "Anki Garden Settings",
    "advanced_hint": "Start with the plain-language status below. Copy the report if you need help troubleshooting.",
    "tab_advanced": "Troubleshooting",
    "app_title": "Anki Garden",
    "title_banner": "Anki Garden",
    "open_settings": "Settings",
    "quest_progress_title": "Quests",
    "no_quests": "No quest progress yet today. Review a card to start progress.",
    "no_achievements": "Achievement progress will appear as you keep studying.",
    "no_collection": "No collected garden items yet.",
}

BUTTON_VARIANT_PRIMARY = "primary"
BUTTON_VARIANT_SECONDARY = "secondary"


def _set_button_variant(button: QPushButton, variant: str) -> None:
    button.setProperty("variant", variant)
    style = button.style()
    if style is not None:
        style.unpolish(button)
        style.polish(button)


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


def _button_stylesheet() -> str:
    return """
            QPushButton { border-radius: 10px; padding: 7px 12px; font-weight: 600; }
            QPushButton[variant='primary'] { background: #2d7653; border: 1px solid #5b9a70; color: #f2fbf2; }
            QPushButton[variant='primary']:hover { background: #378b62; }
            QPushButton[variant='primary']:pressed { background: #225e42; border-color: #86bc91; }
            QPushButton[variant='secondary'] { background: #1d3935; border: 1px solid #42675a; color: #e6f0ea; }
            QPushButton[variant='secondary']:hover { background: #284b43; }
            QPushButton[variant='secondary']:pressed { background: #142d29; border-color: #6d9581; }
            QPushButton[variant='destructive'] { background: #6d2d2d; border: 1px solid #a44a4a; color: #ffecec; }
            QPushButton[variant='destructive']:hover { background: #823636; }
            QPushButton:disabled { background: #1c2a32; border: 1px solid #2c3b44; color: #7a8a92; }
            QPushButton:focus { border: 2px solid #e5f2a6; padding: 6px 11px; }
    """


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


class ProgressRow(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("progressRow", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        self.marker = QLabel("◔")
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setProperty("rowTitle", True)
        heading.addWidget(self.marker)
        heading.addWidget(self.title, 1)
        self.status = QLabel()
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
    ) -> None:
        self.marker.setText("✓" if completed else "◔")
        self.marker.setAccessibleName("Completed" if completed else "In progress")
        self.title.setText(title)
        self.criteria.setText(criteria)
        self.progress.set_progress(title, current, target, value_text=value_text)
        self.progress.label.hide()
        self.progress.value_label.hide()
        self.progress.setVisible(not completed)
        self.status.setText(completion_text if completed else value_text or f"{current:,} of {target:,}")
        self.status.setVisible(True)
        self.setProperty("completed", completed)
        apply_explanatory_tooltip(
            self.marker,
            "Completed and reward earned." if completed else "Progress toward this requirement.",
        )
        apply_explanatory_tooltip(self.progress, f"{criteria}. {current:,} of {target:,} complete.")

    def set_achievement_state(self, state: str) -> None:
        icons = {"locked": "🔒", "in_progress": "◔", "unlocked": "✓"}
        tooltips = {
            "locked": "Locked. Make progress toward this milestone to begin.",
            "in_progress": "In progress. Keep studying to unlock this achievement.",
            "unlocked": "Unlocked achievement.",
        }
        self.marker.setText(icons[state])
        self.marker.setAccessibleName(state.replace("_", " ").title())
        apply_explanatory_tooltip(self.marker, tooltips[state])


class ProgressList(QWidget):
    """Content-sized rows owned by the dashboard's single page scroll area."""

    def __init__(self, accessible_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self.container = QWidget()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(5)
        outer.addWidget(self.container)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def add_row(self, row: QWidget) -> None:
        self.rows.addWidget(row)

    def add_empty(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("rowCriteria", True)
        self.rows.addWidget(label)

    def finish(self) -> None:
        self.rows.addStretch(1)
        self.container.adjustSize()


class GardenSettingsDialog(QDialog):
    def __init__(self, parent: QWidget, engine: Any, config: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.config = config
        self.setWindowTitle(UI_TEXT["settings_window_title"])
        self.setMinimumSize(640, 460)
        self.resize(*self._recommended_window_size(920, 640, width_ratio=0.72, height_ratio=0.72))
        self.setStyleSheet(_button_stylesheet() + "QLabel[saveStatus='true'] { padding:5px 8px; border-radius:8px; }")

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setAccessibleName("Anki Garden settings sections")
        root.addWidget(tabs)

        self.behavior = GardenStudioWidget(self.config, asset_resolver=self.engine.resolve_preview_assets)
        self._persisted_payload = deepcopy(self.behavior.build_theme_payload())
        self.save_settings = QPushButton("Save settings")
        self.save_settings.setAccessibleName("Save Anki Garden settings")
        _set_button_variant(self.save_settings, BUTTON_VARIANT_PRIMARY)
        self.save_settings.clicked.connect(self._save_visual_settings)
        self.save_settings.setEnabled(False)
        self.restore_defaults = QPushButton("Restore defaults")
        self.restore_defaults.setAccessibleName("Stage the default Anki Garden settings")
        _set_button_variant(self.restore_defaults, BUTTON_VARIANT_SECONDARY)
        self.restore_defaults.clicked.connect(self._restore_defaults)
        self.cancel_settings = QPushButton("Cancel")
        _set_button_variant(self.cancel_settings, BUTTON_VARIANT_SECONDARY)
        self.cancel_settings.clicked.connect(self.reject)
        self.save_status = QLabel("")
        self.save_status.setProperty("saveStatus", True)
        self.save_status.setAccessibleName("Settings save status")
        self.save_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.save_status.setWordWrap(True)
        self.save_status.hide()
        self.behavior.persistentChanged.connect(self._update_dirty_state)
        behavior = QWidget()
        behavior_layout = QVBoxLayout(behavior)
        behavior_scroll = QScrollArea()
        behavior_scroll.setWidgetResizable(True)
        behavior_scroll.setFrameShape(QFrame.Shape.NoFrame)
        behavior_scroll.setWidget(self.behavior)
        behavior_layout.addWidget(behavior_scroll, 1)

        history = QFrame()
        history.setProperty("card", True)
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_title = QLabel("Review history")
        history_title.setStyleSheet("font-size:15px; font-weight:700;")
        history_help = QLabel(
            "Apply completed reviews from past Anki days to plant growth and milestone progress. "
            "Today, streaks, quests, achievements, and weather will not be changed."
        )
        history_help.setWordWrap(True)
        history_layout.addWidget(history_title)
        history_layout.addWidget(history_help)
        history_dates = QHBoxLayout()
        self.history_start = QDateEdit()
        self.history_start.setCalendarPopup(True)
        self.history_start.setDisplayFormat("yyyy-MM-dd")
        self.history_start.setAccessibleName("Review history start date")
        self.history_end = QDateEdit()
        self.history_end.setCalendarPopup(True)
        self.history_end.setDisplayFormat("yyyy-MM-dd")
        self.history_end.setAccessibleName("Review history end date")
        yesterday = QDate.currentDate().addDays(-1)
        self.history_start.setMaximumDate(yesterday)
        self.history_end.setMaximumDate(yesterday)
        self.history_start.setDate(yesterday.addDays(-29))
        self.history_end.setDate(yesterday)
        history_dates.addWidget(QLabel("From"))
        history_dates.addWidget(self.history_start)
        history_dates.addWidget(QLabel("Through"))
        history_dates.addWidget(self.history_end)
        history_dates.addStretch(1)
        history_layout.addLayout(history_dates)
        history_actions = QHBoxLayout()
        self.preview_history = QPushButton("Preview")
        self.apply_history = QPushButton("Apply to garden")
        _set_button_variant(self.preview_history, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.apply_history, BUTTON_VARIANT_PRIMARY)
        self.apply_history.setEnabled(False)
        self.history_status = QLabel("")
        self.history_status.setWordWrap(True)
        self.history_status.setAccessibleName("Review history import status")
        history_actions.addWidget(self.preview_history)
        history_actions.addWidget(self.apply_history)
        history_actions.addWidget(self.history_status, 1)
        history_layout.addLayout(history_actions)
        behavior_layout.addWidget(history)
        self._history_preview = None
        self.preview_history.clicked.connect(self._preview_history)
        self.apply_history.clicked.connect(self._apply_history)
        self.history_start.dateChanged.connect(self._invalidate_history_preview)
        self.history_end.dateChanged.connect(self._invalidate_history_preview)
        settings_actions = QHBoxLayout()
        settings_actions.addWidget(self.save_status, 1)
        settings_actions.addWidget(self.restore_defaults)
        settings_actions.addStretch(1)
        settings_actions.addWidget(self.cancel_settings)
        settings_actions.addWidget(self.save_settings)
        behavior_layout.addLayout(settings_actions)

        advanced = QWidget()
        a_layout = QVBoxLayout(advanced)
        a_layout.addWidget(QLabel(UI_TEXT["advanced_hint"]))
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        self.troubleshooting_status = QLabel("Anki Garden is ready. The technical report below contains display diagnostics only.")
        self.troubleshooting_status.setWordWrap(True)
        a_layout.addWidget(self.troubleshooting_status)
        refresh_debug = QPushButton("Refresh report")
        copy_debug = QPushButton("Copy report")
        _set_button_variant(refresh_debug, BUTTON_VARIANT_SECONDARY)
        refresh_debug.clicked.connect(self._refresh_debug_report)
        copy_debug.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.debug_report.toPlainText()))
        report_actions = QHBoxLayout()
        report_actions.addWidget(refresh_debug)
        report_actions.addWidget(copy_debug)
        report_actions.addStretch(1)
        a_layout.addLayout(report_actions)
        a_layout.addWidget(self.debug_report)
        self._refresh_debug_report()
        a_layout.addStretch(1)

        tabs.addTab(behavior, "Garden settings")
        tabs.addTab(advanced, UI_TEXT["tab_advanced"])

    def prepare_to_show(self) -> None:
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.behavior.reset_preview_defaults()
        self.save_status.setText("")
        self.save_status.setStyleSheet("")
        self.save_status.hide()
        self.save_settings.setEnabled(False)
        self._set_history_bounds()
        self._invalidate_history_preview()

    def _set_history_bounds(self) -> None:
        storage = getattr(self.engine, "storage", None)
        bounds = storage.historical_review_bounds() if storage is not None else None
        yesterday = QDate.currentDate().addDays(-1)
        self.history_start.setMaximumDate(yesterday)
        self.history_end.setMaximumDate(yesterday)
        if not bounds:
            return
        earliest = QDate.fromString(bounds[0], "yyyy-MM-dd")
        latest = QDate.fromString(bounds[1], "yyyy-MM-dd")
        if earliest.isValid():
            self.history_start.setMinimumDate(earliest)
            self.history_end.setMinimumDate(earliest)
            if self.history_start.date() < earliest:
                self.history_start.setDate(earliest)
        if latest.isValid() and self.history_end.date() > latest:
            self.history_end.setDate(latest)

    def _invalidate_history_preview(self, *_args: Any) -> None:
        self._history_preview = None
        self.apply_history.setEnabled(False)
        self.history_status.setText("Preview the selected dates before applying them.")

    def _preview_history(self) -> None:
        storage = getattr(self.engine, "storage", None)
        if storage is None:
            self.history_status.setText("Review history is unavailable until a collection is open.")
            return
        preview = storage.preview_historical_reviews(
            self.history_start.date().toString("yyyy-MM-dd"),
            self.history_end.date().toString("yyyy-MM-dd"),
        )
        self._history_preview = preview
        if preview.error:
            self.history_status.setText(preview.error)
            self.apply_history.setEnabled(False)
            return
        skipped = f" {len(preview.skipped_days)} previously applied day(s) will be skipped." if preview.skipped_days else ""
        self.history_status.setText(
            f"{preview.eligible_reviews:,} eligible review(s) across "
            f"{len(preview.importable_days)} new day(s).{skipped}"
        )
        self.apply_history.setEnabled(bool(preview.importable_days))

    def _apply_history(self) -> None:
        preview = self._history_preview
        if preview is None or preview.error or not preview.importable_days:
            self._preview_history()
            return
        response = QMessageBox.question(
            self,
            UI_TEXT["app_title"],
            f"Apply {preview.eligible_reviews:,} historical reviews from "
            f"{len(preview.importable_days)} completed day(s)?\n\n"
            "This can grow plants and unlock milestone rewards. Imported days cannot be applied again.",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            gained = self.engine.apply_historical_reviews(
                list(preview.reviews), imported_days=list(preview.importable_days)
            )
        except Exception:
            logger.exception("Anki Garden: historical review import failed")
            self.history_status.setText("The import could not be saved. Your garden was not changed.")
            self.apply_history.setEnabled(True)
            return
        self.history_status.setText(
            f"Applied {preview.eligible_reviews:,} reviews and awarded {gained:,} growth."
        )
        self.apply_history.setEnabled(False)
        self._history_preview = None
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_all"):
            parent.refresh_all()
            refresh_external = getattr(parent, "refresh_external_surfaces", None)
            if callable(refresh_external):
                refresh_external()

    def _update_dirty_state(self) -> None:
        dirty = self.behavior.build_theme_payload() != self._persisted_payload
        self.save_settings.setEnabled(dirty)
        if dirty:
            self.save_status.show()
            self.save_status.setText("Unsaved changes")
            self.save_status.setStyleSheet("color:#d8e3e5; background:#24343d;")
            self.save_status.setAccessibleDescription("Persistent settings have unsaved changes.")
        elif self.save_status.text() != "Saved":
            self.save_status.setText("")
            self.save_status.setStyleSheet("")
            self.save_status.setAccessibleDescription("")
            self.save_status.hide()

    def _restore_defaults(self) -> None:
        self.behavior.restore_persistent_defaults()
        self._update_dirty_state()
        if self.save_settings.isEnabled():
            self.save_status.setText("Unsaved changes — defaults are staged")
            self.save_status.setAccessibleDescription("Default settings are staged but not saved.")
        else:
            self.save_status.show()
            self.save_status.setText("Defaults are already active")
            self.save_status.setStyleSheet("color:#d8e3e5; background:#24343d;")
            self.save_status.setAccessibleDescription("The persisted settings already match the defaults.")

    def _save_visual_settings(self) -> None:
        old_payload = deepcopy(self._persisted_payload)
        payload = self.behavior.build_theme_payload()
        try:
            self.config.update(payload)
            self.engine.reconcile_daily_goal(int(payload["daily_goal"]))
        except ConfigError as exc:
            self._show_save_error(str(exc))
            return
        except Exception as exc:
            try:
                self.config.update(old_payload)
            except ConfigError:
                logger.exception("Anki Garden: unable to roll back settings after daily-goal reconciliation")
            self.behavior.apply_persistent_payload(old_payload)
            self._show_save_error("Garden progress could not be updated. Your previous settings are still active.")
            logger.exception("Anki Garden: daily goal reconciliation failed", exc_info=exc)
            return
        self._persisted_payload = deepcopy(payload)
        self.engine.assets.metadata.clear()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_all"):
            parent.refresh_all()
            refresh_external = getattr(parent, "refresh_external_surfaces", None)
            if callable(refresh_external):
                refresh_external()
        self.save_settings.setEnabled(False)
        self.save_status.show()
        self.save_status.setText("Saved")
        self.save_status.setStyleSheet("color:#baf3c6; background:#1d4931;")
        self.save_status.setAccessibleDescription("Anki Garden settings saved successfully.")

    def _show_save_error(self, message: str) -> None:
        self.save_status.show()
        self.save_status.setText(message)
        self.save_status.setStyleSheet("color:#ffd0d0; background:#582f34;")
        self.save_status.setAccessibleDescription(f"Settings error: {message}")
        self.save_status.setFocus()

    def reject(self) -> None:
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.behavior.reset_preview_defaults()
        self.save_settings.setEnabled(False)
        self.save_status.setText("")
        self.save_status.hide()
        super().reject()

    def _refresh_debug_report(self) -> None:
        self.debug_report.setPlainText("\n".join(DISPLAY_TELEMETRY.report_lines()))

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


class MemoryTimeline(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Plant memory timeline")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(8, 2, 8, 2)
        self.layout.setSpacing(0)
        self.setWidget(self.container)

    def set_memories(self, memories: list[tuple[str, str]]) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not memories:
            empty = QLabel("Its first memory will appear here as it grows.")
            empty.setWordWrap(True)
            self.layout.addWidget(empty)
        for display_date, text in memories:
            row = QFrame()
            row.setProperty("memoryRow", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            row_layout.setSpacing(10)
            marker = QLabel("●")
            marker.setProperty("memoryMarker", True)
            marker.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            marker.setAccessibleName(f"Memory on {display_date}")
            copy = QVBoxLayout()
            date_label = QLabel(display_date)
            date_label.setProperty("memoryDate", True)
            body = QLabel(text)
            body.setWordWrap(True)
            copy.addWidget(date_label)
            copy.addWidget(body)
            row_layout.addWidget(marker)
            row_layout.addLayout(copy, 1)
            self.layout.addWidget(row)
        future = QLabel("More memories will appear as this plant grows.")
        future.setWordWrap(True)
        future.setProperty("memoryFuture", True)
        self.layout.addWidget(future)
        self.layout.addStretch(1)
        hint = self.container.sizeHint().height() + 8
        self.setMaximumHeight(max(120, min(360, hint)))


class PlantStoryDialog(QDialog):
    def __init__(self, parent: QWidget, engine: Any, plant_id: str) -> None:
        super().__init__(parent)
        self.engine = engine
        self.plant_id = plant_id
        self.setWindowTitle("Plant story")
        self.setMinimumSize(480, 420)
        self.resize(640, 480)
        self.setStyleSheet(_button_stylesheet() + """
            QFrame[memoryRow='true'] { border-left:2px solid #4c8f67; }
            QLabel[memoryMarker='true'] { color:#72ce8c; padding-left:2px; }
            QLabel[memoryDate='true'] { color:#9db0b5; font-size:12px; font-weight:600; }
            QLabel[memoryFuture='true'] { color:#9db0b5; font-style:italic; padding:10px 0; }
        """)
        root = QVBoxLayout(self)
        self.name_heading = QLabel()
        self.name_heading.setWordWrap(True)
        self.name_heading.setStyleSheet("font-size:22px; font-weight:800;")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color:#b2c4c8;")
        identity_row = QHBoxLayout()
        self.artwork = QLabel()
        self.artwork.setFixedSize(120, 120)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setAccessibleName("Plant artwork")
        identity_text = QVBoxLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_heading, 1)
        self.edit_name_btn = QPushButton("✎")
        self.edit_name_btn.setAccessibleName("Rename plant")
        self.edit_name_btn.setToolTip("Rename plant")
        self.edit_name_btn.setFixedWidth(38)
        _set_button_variant(self.edit_name_btn, BUTTON_VARIANT_SECONDARY)
        name_row.addWidget(self.edit_name_btn, 0, Qt.AlignmentFlag.AlignTop)
        identity_text.addLayout(name_row)
        identity_text.addWidget(self.summary)
        identity_row.addWidget(self.artwork)
        identity_row.addLayout(identity_text, 1)
        root.addLayout(identity_row)

        self.rename_row = QHBoxLayout()
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
        root.addLayout(self.rename_row)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        root.addWidget(self.feedback)

        timeline_label = QLabel("Milestone memories")
        timeline_label.setStyleSheet("font-size:16px; font-weight:700;")
        root.addWidget(timeline_label)
        self.timeline = MemoryTimeline()
        root.addWidget(self.timeline, 1)
        close_btn = QPushButton("Close")
        _set_button_variant(close_btn, BUTTON_VARIANT_SECONDARY)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

        self.edit_name_btn.clicked.connect(self._begin_rename)
        self.cancel_name_btn.clicked.connect(self._cancel_rename)
        self.save_name_btn.clicked.connect(self._save_name)
        self.name_edit.returnPressed.connect(self._save_name)
        self._set_editing(False)
        self.refresh()

    def _plant(self) -> Any:
        return self.engine.plant_story(self.plant_id)

    def _set_editing(self, editing: bool) -> None:
        self.name_heading.setVisible(not editing)
        self.name_edit.setVisible(editing)
        self.save_name_btn.setVisible(editing)
        self.cancel_name_btn.setVisible(editing)
        self.edit_name_btn.setVisible(not editing)
        if editing:
            self.name_edit.setFocus()
            self.name_edit.selectAll()

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
        self.feedback.hide()
        self._set_editing(False)

    def keyPressEvent(self, event: Any) -> None:
        if self.name_edit.isVisible() and event.key() == Qt.Key.Key_Escape:
            self._cancel_rename()
            event.accept()
            return
        super().keyPressEvent(event)

    def _save_name(self) -> None:
        ok, message = self.engine.rename_plant(self.plant_id, self.name_edit.text())
        self.feedback.setText(message)
        self.feedback.setVisible(not ok)
        if ok:
            self._set_editing(False)
            self.refresh()
            parent = self.parent()
            if parent is not None and hasattr(parent, "refresh_all"):
                parent.refresh_all()
                refresh_external = getattr(parent, "refresh_external_surfaces", None)
                if callable(refresh_external):
                    refresh_external()

    @staticmethod
    def _memory_text(memory: Any, name: str) -> str:
        if memory.kind == "planted":
            return f"{name} joined your garden."
        if memory.kind == "first_focus":
            return f"You chose to nurture {name} for the first time."
        if memory.kind == "stage":
            return f"{name} reached {format_status_label(memory.new_stage or 'new growth')}."
        if memory.kind == "streak":
            return f"{name} witnessed your {memory.value}-day study streak."
        if memory.kind == "reviews":
            return f"{name} witnessed your {memory.value:,}th review."
        return "A garden milestone was reached."

    def refresh(self) -> None:
        plant = self._plant()
        if plant is None:
            self.name_heading.setText("Plant unavailable")
            self.summary.setText("This plant is no longer in your garden.")
            self.edit_name_btn.setEnabled(False)
            self.artwork.clear()
            self.timeline.set_memories([])
            return
        self.name_heading.setText(plant.name)
        stage = "Rare bloom" if plant.rare_variant else format_status_label(plant.growth_stage)
        focus = " • Currently nurturing" if self.engine.state.focus_plant_id == plant.plant_id else ""
        self.summary.setText(
            f"{format_status_label(plant.species)} • {stage} • {plant.growth_points:,} growth points{focus}\n"
            f"Planted {self._local_date(plant.planted_on)}"
        )
        try:
            image_path = self.engine.resolve_plant_image(plant.species, plant.growth_stage, plant.rare_variant)
        except Exception:
            logger.exception("Anki Garden: unable to resolve Plant Story artwork")
            image_path = None
        pixmap = QPixmap(str(image_path)) if image_path else QPixmap()
        if pixmap.isNull():
            self.artwork.setText(format_status_label(plant.species))
        else:
            self.artwork.setPixmap(pixmap.scaled(
                self.artwork.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        memories = sorted(plant.memories, key=lambda item: (item.occurred_on, item.memory_id), reverse=True)
        self.timeline.set_memories([
            (self._local_date(memory.occurred_on), self._memory_text(memory, plant.name))
            for memory in memories
        ])

    @staticmethod
    def _local_date(value: str) -> str:
        try:
            from datetime import date
            return date.fromisoformat(str(value)[:10]).strftime("%b %-d, %Y")
        except Exception:
            return str(value)


class PlantActionPanel(QFrame):
    """Native, keyboard-accessible controls for the selected painted plant."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("actionBar", True)
        self.plant_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        self.normal_panel = QWidget()
        self.normal_row = QHBoxLayout(self.normal_panel)
        self.normal_row.setContentsMargins(0, 0, 0, 0)
        self.normal_row.setSpacing(10)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self.heading = QLabel("Select a plant")
        self.heading.setWordWrap(True)
        self.heading.setMaximumHeight(44)
        self.heading.setAccessibleName("Selected plant")
        self.identity = QLabel("Choose a plant in the garden to see its actions.")
        self.identity.setWordWrap(True)
        self.identity.setProperty("actionMeta", True)
        identity.addWidget(self.heading)
        identity.addWidget(self.identity)
        self.normal_row.addLayout(identity, 2)
        self.stage_progress = LabeledProgress("Selected plant growth")
        self.stage_progress.setMinimumWidth(210)
        self.normal_row.addWidget(self.stage_progress, 2)
        self.nurturing_pill = QLabel("Nurtured plant")
        self.nurturing_pill.setProperty("nurturingPill", True)
        apply_explanatory_tooltip(
            self.nurturing_pill,
            "Most growth earned from reviews is currently being applied to this plant.",
        )
        self.nurture = QPushButton("Nurture")
        self.move = QPushButton("Rearrange")
        self.story = QPushButton("View Story")
        self.cancel_move = QPushButton("Cancel")
        self.done_move = QPushButton("Done")
        _set_button_variant(self.nurture, BUTTON_VARIANT_PRIMARY)
        for button in (self.move, self.story, self.cancel_move):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
        _set_button_variant(self.done_move, BUTTON_VARIANT_PRIMARY)
        for button in (
            self.nurture, self.move, self.story, self.cancel_move, self.done_move
        ):
            button.setMinimumHeight(44)
        apply_explanatory_tooltip(self.cancel_move, "Exit move mode without changing the plant arrangement.")
        apply_explanatory_tooltip(self.done_move, "Save the current plant arrangement.")
        apply_explanatory_tooltip(
            self.nurture,
            "Make this your nurtured plant. Most growth earned from reviews will be applied to this plant.",
        )
        apply_explanatory_tooltip(self.move, "Move this plant to another unlocked garden space.")
        apply_explanatory_tooltip(self.story, "View this plant’s growth history and milestones.")
        self.actions = QWidget()
        actions_layout = QHBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.nurturing_pill)
        actions_layout.addWidget(self.nurture)
        actions_layout.addWidget(self.move)
        actions_layout.addWidget(self.story)
        self.normal_row.addWidget(self.actions)
        layout.addWidget(self.normal_panel)

        self.move_panel = QFrame()
        self.move_panel.setProperty("movePanel", True)
        move_layout = QHBoxLayout(self.move_panel)
        move_layout.setContentsMargins(10, 8, 10, 8)
        move_copy = QVBoxLayout()
        move_title = QLabel("Move a plant")
        move_title.setProperty("moveTitle", True)
        self.move_instructions = QLabel("")
        self.move_instructions.setWordWrap(True)
        move_copy.addWidget(move_title)
        move_copy.addWidget(self.move_instructions)
        move_layout.addLayout(move_copy, 1)
        self.destination_selector = QComboBox()
        self.destination_selector.setMinimumHeight(44)
        self.destination_selector.setAccessibleName("Garden destination")
        self.destination_selector.setAccessibleDescription("Choose an unlocked garden space for this plant.")
        self.apply_destination = QPushButton("Move here")
        self.apply_destination.setMinimumHeight(44)
        _set_button_variant(self.apply_destination, BUTTON_VARIANT_PRIMARY)
        self.destination_selector.hide()
        self.apply_destination.hide()
        move_layout.addWidget(self.destination_selector)
        move_layout.addWidget(self.apply_destination)
        move_layout.addWidget(self.cancel_move)
        move_layout.addWidget(self.done_move)
        layout.addWidget(self.move_panel)
        self.move_panel.hide()
        self._native_destination_visible = False
        self.set_selected(None)

    def set_compact(self, compact: bool) -> None:
        self.normal_row.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )

    def set_selected(self, plant: Any | None) -> None:
        self.plant_id = str(plant.get("plant_id", "")) if isinstance(plant, dict) else ""
        available = bool(self.plant_id)
        for button in (self.nurture, self.move, self.story):
            button.setEnabled(available)
        self.stage_progress.setVisible(available)
        if not available:
            self.heading.setText("Select a plant")
            self.identity.setText("Choose a plant in the garden to see its actions.")
            self.nurture.setText("Nurture")
            self.nurturing_pill.hide()
            return
        name = str(plant.get("name") or plant.get("species") or "Plant")
        focused = bool(plant.get("is_focus"))
        self.heading.setText(name)
        species = format_status_label(plant.get("species") or "plant")
        stage = format_status_label(plant.get("stage") or "seed")
        growth_points = max(0, int(plant.get("growth_points", 0) or 0))
        self.identity.setText(f"{species} · {stage} stage · {growth_points:,} growth")
        self.nurturing_pill.setVisible(focused)
        self.nurture.setVisible(not focused)
        self.nurture.setEnabled(not focused)
        self.nurture.setAccessibleDescription(
            "Selected status. This plant currently receives most review growth."
            if focused else "Give this plant most of the growth earned from reviews."
        )
        if bool(plant.get("fully_grown")):
            self.stage_progress.set_progress("Growth stage", 1, 1, value_text="Fully grown")
        else:
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            next_stage = format_status_label(plant.get("next_stage") or "next stage")
            self.stage_progress.set_progress(f"Progress to {next_stage}", stage_points, stage_goal)
            apply_explanatory_tooltip(
                self.stage_progress,
                f"Growth required for this plant to reach the {next_stage} stage.",
            )

    def set_move_active(self, active: bool) -> None:
        self.normal_panel.setVisible(not active)
        self.move_panel.setVisible(active)
        self.move.setEnabled(bool(self.plant_id) and not active)
        self.destination_selector.setVisible(active and self._native_destination_visible)
        self.apply_destination.setVisible(active and self._native_destination_visible)

    def set_native_destination_visible(self, visible: bool) -> None:
        self._native_destination_visible = bool(visible)
        active = self.move_panel.isVisible()
        self.destination_selector.setVisible(active and self._native_destination_visible)
        self.apply_destination.setVisible(active and self._native_destination_visible)

    def set_destinations(self, rows: list[tuple[str, int]]) -> None:
        self.destination_selector.clear()
        for label, slot in rows:
            self.destination_selector.addItem(label, slot)
        self.apply_destination.setEnabled(bool(rows))

    def selected_destination(self) -> int | None:
        value = self.destination_selector.currentData()
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def set_move_message(self, message: str) -> None:
        self.move_instructions.setText(message)

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
    CARD_BG = "#102622"
    CARD_BORDER = "#345348"
    APP_BG = "#0a1715"
    TEXT_PRIMARY = "#edf5ea"
    TEXT_MUTED = "#aac0b1"
    CHIP_BG = "#19372f"
    LIST_ELIDE_WIDTH = 340
    LIST_MAX_LENGTH = 170
    MIN_WINDOW_WIDTH = 780
    MIN_WINDOW_HEIGHT = 560
    DEFAULT_WINDOW_WIDTH = 1240
    DEFAULT_WINDOW_HEIGHT = 840

    def __init__(self, mw_window: Any, engine: Any, storage: Any, config: Any) -> None:
        super().__init__(mw_window)
        self.engine = engine
        self.storage = storage
        self.config = config
        self.mw_window = mw_window
        self.settings_dialog: GardenSettingsDialog | None = None
        self._undo_placement: Any = None
        self._placement_draft: Any = None
        self._move_feedback_generation = 0
        self._onboarding_just_completed = False
        self._onboarding_confirmation_generation = 0
        self._onboarding_save_error = ""
        self.setWindowTitle(UI_TEXT["app_title"])
        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(*self._recommended_window_size())
        self._build_ui()
        QTimer.singleShot(0, self._update_scene_height)

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
            QFrame[card='true'] {{ background: {self.CARD_BG}; border: 1px solid {self.CARD_BORDER}; border-radius: {self.CARD_BORDER_RADIUS}px; }}
            QFrame[topBar='true'] {{ background:transparent; border:0; }}
            QFrame[actionBar='true'] {{ background:#0d211e; border-top:1px solid #345348; border-radius:10px; }}
            QFrame[movePanel='true'] {{ background:#17342e; border-left:3px solid #d1ad69; border-radius:9px; }}
            QFrame[gardenStats='true'] {{ background:#0d211e; border:1px solid #29483c; border-radius:10px; }}
            QLabel[gardenStatsTitle='true'] {{ color:#edf5ea; font-weight:750; }}
            QLabel[gardenStatsSummary='true'] {{ color:#aac0b1; }}
            QFrame[onboarding='true'] {{ background:#17342e; border:1px solid #4e7867; border-radius:12px; }}
            QFrame[progressRow='true'] {{ background:#0d211e; border:1px solid #27443a; border-radius:9px; }}
            QFrame[progressRow='true'][completed='true'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QLabel[typography='title'] {{ font-size: 20px; font-weight: 800; letter-spacing: 0.3px; }}
            QLabel[typography='section-title'] {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
            QLabel[typography='muted-body'] {{ font-size: 13px; color: {self.TEXT_MUTED}; }}
            QLabel[typography='status-chip'] {{ font-size: 12px; font-weight: 600; letter-spacing: 0.1px; }}
            QLabel[chip='true'] {{ padding: {self.CHIP_PADDING[0]}px {self.CHIP_PADDING[1]}px; background:{self.CHIP_BG}; border-radius:{self.CHIP_BORDER_RADIUS}px; }}
            QLabel[nurturingPill='true'] {{ padding:5px 10px; color:#f5e5ba; background:#5a4824; border:1px solid #8a6b34; border-radius:10px; font-weight:700; }}
            QLabel[actionMeta='true'], QLabel[rowCriteria='true'] {{ color:{self.TEXT_MUTED}; font-size:12px; }}
            QLabel[rowTitle='true'], QLabel[moveTitle='true'] {{ font-weight:700; }}
            QLabel[completion='true'] {{ color:#9ef3b0; font-weight:700; }}
            QLabel[rowStatus='true'] {{ color:#bcd0d3; font-size:13px; font-weight:600; }}
            QLabel[progressValue='true'] {{ color:#bcd0d3; font-size:13px; }}
            QTabWidget::pane {{ border:1px solid #345348; border-radius:12px; background:#102622; top:-1px; }}
            QTabBar::tab {{ min-height:34px; min-width:112px; padding:4px 12px; color:#aac0b1; background:#0d211e; border:1px solid #2c493e; }}
            QTabBar::tab:selected {{ background:#244c3d; color:#f4f3df; border-color:#6d8e70; }}
            QScrollArea {{ background:transparent; border:0; }}
            {_button_stylesheet()}
            QProgressBar {{ border-radius: 7px; border: 1px solid {self.CARD_BORDER}; background: #132029; }}
            QProgressBar::chunk {{ background: #58b77b; border-radius: 6px; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(*self.ROOT_MARGINS)
        root.setSpacing(self.ROOT_SPACING)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setWidget(page)
        outer.addWidget(page_scroll)

        top = QFrame()
        top.setProperty("topBar", True)
        t_layout = QHBoxLayout(top)
        t_layout.setContentsMargins(4, 4, 4, 4)
        t_layout.setSpacing(self.CHIP_SPACING)
        self.title_label = QLabel(UI_TEXT["title_banner"])
        self._apply_typography(self.title_label, "title")
        self.title_subtitle = QLabel("A living record of your study rhythm")
        self._apply_typography(self.title_subtitle, "muted-body")
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        title_stack.addWidget(self.title_label)
        title_stack.addWidget(self.title_subtitle)
        self.settings_btn = QPushButton(UI_TEXT["open_settings"])
        _set_button_variant(self.settings_btn, BUTTON_VARIANT_SECONDARY)
        self.settings_btn.clicked.connect(self._open_settings)
        apply_explanatory_tooltip(
            self.settings_btn,
            "Customize your garden, plants, goals, and display preferences.",
        )
        t_layout.addLayout(title_stack)
        t_layout.addStretch(1)
        t_layout.addWidget(self.settings_btn)
        root.addWidget(top)

        self.onboarding_panel = QFrame()
        self.onboarding_panel.setProperty("onboarding", True)
        self.onboarding_panel.setAccessibleName("Getting started with Anki Garden")
        onboarding_layout = QHBoxLayout(self.onboarding_panel)
        onboarding_layout.setContentsMargins(*self.CARD_PADDING)
        onboarding_copy = QVBoxLayout()
        self.onboarding_title = QLabel("")
        self.onboarding_title.setProperty("rowTitle", True)
        self.onboarding_message = QLabel("")
        self.onboarding_message.setWordWrap(True)
        self._apply_typography(self.onboarding_message, "muted-body")
        onboarding_copy.addWidget(self.onboarding_title)
        onboarding_copy.addWidget(self.onboarding_message)
        onboarding_layout.addLayout(onboarding_copy, 1)
        self.onboarding_action = QPushButton("Return to studying")
        _set_button_variant(self.onboarding_action, BUTTON_VARIANT_PRIMARY)
        self.onboarding_action.clicked.connect(self.accept)
        onboarding_layout.addWidget(self.onboarding_action)
        self.dismiss_onboarding = QPushButton("Dismiss tips")
        _set_button_variant(self.dismiss_onboarding, BUTTON_VARIANT_SECONDARY)
        self.dismiss_onboarding.setAccessibleDescription("Hide first-use garden guidance")
        self.dismiss_onboarding.clicked.connect(self._dismiss_onboarding)
        onboarding_layout.addWidget(self.dismiss_onboarding)
        root.addWidget(self.onboarding_panel)

        hero_card = self._card_frame()
        hero_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        h_layout = QVBoxLayout(hero_card)
        h_layout.setContentsMargins(*self.CARD_PADDING)
        h_layout.setSpacing(self.CARD_SPACING)
        self.scene = GardenSceneWidget()
        self.scene.nurtureRequested.connect(self._nurture_plant)
        self.scene.placementRequested.connect(self._place_plant)
        self.scene.storyRequested.connect(self._open_plant_story)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self.scene.placementStateChanged.connect(self._on_placement_state)
        self.scene.cancelPlacementRequested.connect(self._cancel_move)
        self.scene.moveSessionRequested.connect(self._begin_move)
        self.scene.setMinimumHeight(260)
        self.garden_stats_bar = QFrame()
        self.garden_stats_bar.setProperty("gardenStats", True)
        garden_stats_layout = QHBoxLayout(self.garden_stats_bar)
        garden_stats_layout.setContentsMargins(12, 8, 12, 8)
        garden_stats_layout.setSpacing(10)
        self.garden_stats_title = QLabel("Your garden")
        self.garden_stats_title.setProperty("gardenStatsTitle", True)
        self.garden_stats_summary = QLabel("")
        self.garden_stats_summary.setProperty("gardenStatsSummary", True)
        self.garden_stats_summary.setWordWrap(True)
        self.garden_stats_summary.setAccessibleName("Garden study statistics")
        apply_explanatory_tooltip(
            self.garden_stats_summary,
            "Streak counts consecutive study days. Daily goal compares today’s growth with your goal. Garden vitality reflects recent study consistency.",
        )
        garden_stats_layout.addWidget(self.garden_stats_title)
        garden_stats_layout.addWidget(self.garden_stats_summary, 1)
        self.action_panel = PlantActionPanel()
        self.action_panel.nurture.clicked.connect(lambda: self._nurture_plant(self.action_panel.plant_id))
        self.action_panel.move.clicked.connect(lambda: self._begin_move(self.action_panel.plant_id))
        self.action_panel.story.clicked.connect(lambda: self._open_plant_story(self.action_panel.plant_id))
        self.action_panel.cancel_move.clicked.connect(self._cancel_move)
        self.action_panel.done_move.clicked.connect(self._done_move)
        self.action_panel.apply_destination.clicked.connect(self._apply_native_destination)
        self.daily_progress = LabeledProgress("Today's growth")
        apply_explanatory_tooltip(
            self.daily_progress,
            "Today's growth is earned from completed reviews and compared with your configured daily goal.",
        )
        apply_explanatory_tooltip(
            self.daily_progress.bar,
            "Today's growth progress compares growth earned with your configured daily goal.",
        )
        self.above_goal_note = QLabel("")
        self._apply_typography(self.above_goal_note, "muted-body")
        self.placement_note = QLabel("")
        self._apply_typography(self.placement_note, "muted-body")
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
        placement_row.addWidget(self.placement_note)
        placement_row.addWidget(self.undo_move_btn)
        placement_row.addStretch(1)
        self.stage_transition_note = QLabel("")
        self.stage_transition_note.setWordWrap(True)
        self._apply_typography(self.stage_transition_note, "muted-body")
        self.stage_transition_note.setStyleSheet("color:#f4d58a; font-size:14px; font-weight:700;")
        self.stage_transition_note.hide()
        self.retrospective_note = QLabel("")
        self.retrospective_note.setWordWrap(True)
        self.retrospective_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._apply_typography(self.retrospective_note, "muted-body")
        self.retrospective_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.retrospective_note.hide()
        self.status_notice = QLabel("")
        self.status_notice.setWordWrap(True)
        self.status_notice.setAccessibleName("Garden save status")
        self.status_notice.hide()
        h_layout.addWidget(self.garden_stats_bar)
        h_layout.addWidget(self.scene)
        h_layout.addWidget(self.action_panel)
        h_layout.addWidget(self.daily_progress)
        h_layout.addWidget(self.above_goal_note)
        h_layout.addLayout(placement_row)
        h_layout.addWidget(self.stage_transition_note)
        h_layout.addWidget(self.retrospective_note)
        h_layout.addWidget(self.status_notice)
        root.addWidget(hero_card)

        self.milestone_card = self._card_frame()
        self.milestone_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        milestone_layout = QHBoxLayout(self.milestone_card)
        milestone_layout.setContentsMargins(*self.CARD_PADDING)
        milestone_layout.setSpacing(self.CARD_SPACING)
        self.milestone_title = QLabel("Next garden addition")
        self._apply_typography(self.milestone_title, "section-title")
        self.milestone_note = QLabel("")
        self.milestone_note.setWordWrap(True)
        self._apply_typography(self.milestone_note, "muted-body")
        milestone_copy = QVBoxLayout()
        milestone_copy.setSpacing(2)
        milestone_copy.addWidget(self.milestone_title)
        milestone_copy.addWidget(self.milestone_note)
        milestone_layout.addLayout(milestone_copy, 1)
        self.milestone_choices = QHBoxLayout()
        self.milestone_choices.setSpacing(6)
        self.milestone_progress = LabeledProgress("Next plant choice")
        self.milestone_progress.setMinimumWidth(250)
        milestone_layout.addWidget(self.milestone_progress)
        milestone_layout.addLayout(self.milestone_choices)
        root.addWidget(self.milestone_card)

        self.quest_list = ProgressList("Quest progress")
        self.achievement_list = ProgressList("Achievement progress")
        self.details_tabs = QTabWidget()
        self.details_tabs.setDocumentMode(True)
        self.details_tabs.setAccessibleName("Garden progress details")
        self.details_tabs.addTab(self.quest_list, UI_TEXT["quest_progress_title"])
        self.details_tabs.addTab(self.achievement_list, "Achievements")
        self.details_tabs.setTabToolTip(0, "View today’s review goals and growth rewards.")
        self.details_tabs.setTabToolTip(1, "View long-term milestones and unlocked achievements.")
        self.quest_heading = QLabel("Today’s quests")
        self._apply_typography(self.quest_heading, "section-title")
        self.quest_summary = QLabel("")
        self._apply_typography(self.quest_summary, "muted-body")
        self.quest_list.rows.insertWidget(0, self.quest_summary)
        self.quest_list.rows.insertWidget(0, self.quest_heading)
        root.addWidget(self.details_tabs)

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)

    def refresh_all(self) -> None:
        DISPLAY_TELEMETRY.track_render("dashboard")
        state = self.storage.state
        notice = USER_NOTICES.current.message
        self.status_notice.setText(notice)
        self.status_notice.setVisible(bool(notice))
        stats = state.daily_stats
        health = self.engine.garden_health_index()
        daily_goal = max(1, int(self.config.value("daily_goal", 140)))
        focus = self.engine.focus_plant()
        above_goal = max(0, stats.growth_earned - daily_goal)
        growth_value = f"{stats.growth_earned:,} earned · {daily_goal:,} goal"
        goal_label = (
            "Daily goal complete"
            if stats.growth_earned >= daily_goal
            else f"{format_percent(stats.growth_earned / daily_goal)} daily goal"
        )
        self.garden_stats_summary.setText(
            f"{max(0, int(state.streak_days))} day streak  ·  {goal_label}  ·  {format_percent(health)} vitality"
        )
        self.daily_progress.set_progress("Today's growth", stats.growth_earned, daily_goal, value_text=growth_value)
        self.above_goal_note.setText(f"{above_goal:,} above goal" if above_goal else "")
        self.above_goal_note.setVisible(bool(above_goal))
        self._refresh_onboarding()
        self._refresh_milestone_card()

        transitions = self.engine.consume_stage_transitions()
        transition_message = self.engine.stage_transition_message(transitions)
        self.stage_transition_note.setText(transition_message)
        self.stage_transition_note.setVisible(bool(transition_message))
        if transition_message:
            QTimer.singleShot(4200, lambda: (self.stage_transition_note.setText(""), self.stage_transition_note.hide()))

        self.scene.set_scene(
            {
                "weather": state.selected_weather,
                "theme": str(self.config.value("visual_theme", "verdant_dusk")),
                "health": health,
                "growth": min(1.0, stats.growth_earned / daily_goal),
                "unlocked_slots": state.unlocked_slots,
                "streak_days": state.streak_days,
                "cards_today": stats.reviewed,
                "show_status_overlay": False,
                "motion_enabled": bool(
                    self.config.value("enable_animations", True)
                    and not self.config.value("reduced_motion", False)
                ),
                "animation_intensity": self.config.nested("theme_overrides", "animation_intensity", default=0.7),
                "weather_particle_density": self.config.nested("theme_overrides", "weather_particle_density", default=1.0),
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
                "plants": [self._plant_scene_payload(plant) for plant in state.plants],
            }
        )
        active = self.scene.active_plant_id()
        if not active and focus is not None:
            active = focus.plant_id
            self.scene.keep_card_open(active)
        self._on_scene_selection(active or "")

        self.quest_list.clear()
        completed_quests = sum(1 for quest in state.daily_quests if quest.completed)
        self.quest_heading = QLabel("Today’s quests")
        self._apply_typography(self.quest_heading, "section-title")
        self.quest_summary = QLabel(f"{completed_quests} of {len(state.daily_quests)} completed")
        self._apply_typography(self.quest_summary, "muted-body")
        self.quest_list.add_row(self.quest_heading)
        self.quest_list.add_row(self.quest_summary)
        for quest in state.daily_quests:
            quest_description = str(quest.description)
            if str(getattr(quest, "quest_id", "")) == "learning":
                quest_description = quest_description.replace("Finish ", "Complete ").replace(
                    " learning/review cards", " learning or review cards"
                )
            elif str(getattr(quest, "quest_id", "")) == "growth":
                quest_description = quest_description.replace(" garden growth", " growth")
            row = ProgressRow()
            row.set_item(
                quest_description,
                f"Reward: +{quest.reward_growth:,} growth",
                quest.progress,
                quest.target,
                completed=quest.completed,
                value_text=f"{quest.progress:,} of {quest.target:,}",
                completion_text="Completed",
            )
            apply_explanatory_tooltip(row.status, "Completed" if quest.completed else "Current quest progress.")
            self.quest_list.add_row(row)
        if not state.daily_quests:
            DISPLAY_TELEMETRY.track_empty_state(route="dashboard", view="quest_list", expected_non_empty=bool(state.daily_quests))
            self.quest_list.add_empty(UI_TEXT["no_quests"])
        self.quest_list.finish()

        self.achievement_list.clear()
        for ach in state.achievements.values():
            display = achievement_progress_display(ach, state)
            unlocked_at = getattr(ach, "unlocked_at", None)
            completion = f"Unlocked {self._local_date(unlocked_at)}" if unlocked_at else "Achievement completed"
            row = ProgressRow()
            row.set_item(
                ach.name,
                display.criteria_text,
                display.current,
                display.target,
                completed=ach.unlocked,
                value_text=display.value_text,
                completion_text=completion,
            )
            achievement_state = "unlocked" if ach.unlocked else "in_progress" if display.current > 0 else "locked"
            row.set_achievement_state(achievement_state)
            self.achievement_list.add_row(row)
        if not state.achievements:
            DISPLAY_TELEMETRY.track_empty_state(route="dashboard", view="achievement_list", expected_non_empty=bool(state.achievements))
            self.achievement_list.add_empty(UI_TEXT["no_achievements"])
        self.achievement_list.finish()


    @staticmethod
    def _local_date(value: str) -> str:
        try:
            from datetime import date
            return date.fromisoformat(str(value)[:10]).strftime("%B %-d, %Y")
        except Exception:
            return str(value)

    def _on_scene_selection(self, plant_id: str) -> None:
        plant = next((row for row in self.scene.scene.get("plants", []) if str(row.get("plant_id")) == plant_id), None)
        self.action_panel.set_selected(plant)

    def _on_placement_state(self, active: bool) -> None:
        self.action_panel.set_move_active(active)
        self.action_panel.set_native_destination_visible(
            self.scene.uses_native_destination_selector()
        )

    def resizeEvent(self, event: Any) -> None:
        self._update_scene_height(event.size().height())
        self.action_panel.set_compact(event.size().width() < 900)
        self.action_panel.set_native_destination_visible(
            self.scene.uses_native_destination_selector()
        )
        super().resizeEvent(event)

    def done(self, result: int) -> None:
        """Refresh the underlying Anki home surface after the modal dashboard closes."""
        super().done(result)
        QTimer.singleShot(0, self.refresh_external_surfaces)

    def _update_scene_height(self, viewport_height: int | None = None) -> None:
        if not hasattr(self, "scene"):
            return
        available_width = max(1, int(self.width()) - self.ROOT_MARGINS[0] - self.ROOT_MARGINS[2] - 24)
        scene_aspect = 4 / 3 if available_width < 620 else 16 / 9 if available_width < 1400 else 12 / 5
        target = max(280, min(800, int(available_width / scene_aspect)))
        self.scene.setMinimumHeight(target)
        self.scene.setMaximumHeight(target)

    def refresh_external_surfaces(self) -> None:
        """Refresh Anki webviews after a dashboard mutation changes home-card data."""
        reset = getattr(self.mw_window, "reset", None)
        try:
            if callable(reset):
                reset()
            state = str(getattr(self.mw_window, "state", ""))
            surface_name = {"deckBrowser": "deckBrowser", "overview": "overview"}.get(state)
            surface = getattr(self.mw_window, surface_name, None) if surface_name else None
            refresh = getattr(surface, "refresh", None)
            if callable(refresh):
                refresh()
        except Exception:
            logger.exception("Anki Garden: unable to refresh Anki home surfaces")

    def show_retrospective_feedback(self, review_count: int, growth_gain: int) -> None:
        if review_count <= 0:
            self.retrospective_note.setText("")
            self.retrospective_note.hide()
            return
        self.retrospective_note.show()
        self.retrospective_note.setText(
            f"✨ Applied catch-up from synced reviews: +{growth_gain} growth from {review_count} reviews."
        )

    def _plant_scene_payload(self, plant: Any) -> dict[str, Any]:
        display = growth_display(plant.growth_points, plant.rare_variant)
        staged_slots = self._placement_draft.scene_slots() if self._placement_draft is not None else {}
        return {
            "plant_id": plant.plant_id,
            "slot_index": staged_slots.get(plant.plant_id, plant.slot_index),
            "name": plant.name,
            "species": plant.species,
            "stage": display.stage,
            "vitality": plant.vitality,
            "growth_points": plant.growth_points,
            "rare_variant": plant.rare_variant,
            "next_stage": display.next_stage,
            "next_threshold": display.next_threshold,
            "points_remaining": display.points_remaining,
            "stage_progress": display.progress,
            "stage_points": display.stage_points,
            "stage_goal": display.stage_goal,
            "fully_grown": display.fully_grown,
            "health_label": plant_health_display(plant.vitality).label,
            "is_focus": plant.plant_id == self.storage.state.focus_plant_id,
            "asset": self._resolved_asset_payload(
                "resolve_plant_asset",
                "resolve_plant_image",
                plant.species,
                plant.growth_stage,
                plant.rare_variant,
            ),
        }

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
        if self.storage.state.focus_plant_id == plant_id:
            self.scene.keep_card_open(
                plant_id,
                "Currently nurturing this plant — it receives 80% of review growth.",
            )
            self._complete_first_nurture_guidance()
            return
        ok, message = self.engine.set_focus_plant(plant_id)
        if not ok:
            self.scene.keep_card_open(plant_id, message)
            return
        self.refresh_all()
        self.scene.keep_card_open(plant_id, message)
        self.refresh_external_surfaces()
        self._complete_first_nurture_guidance()

    def _open_plant_story(self, plant_id: str) -> None:
        dialog = PlantStoryDialog(self, self.engine, plant_id)
        dialog.exec()
        self.refresh_all()
        self.refresh_external_surfaces()

    def _begin_move(self, plant_id: str) -> None:
        ok, message, draft = self.engine.begin_placement_draft(plant_id)
        if not ok or draft is None:
            self.scene.keep_card_open(plant_id, message)
            return
        self._placement_draft = draft
        plant = next((row for row in self.storage.state.plants if row.plant_id == plant_id), None)
        name = str(getattr(plant, "name", "Plant"))
        move_message = f"Moving {name}. Choose a new location."
        self.action_panel.set_move_message(move_message)
        occupied = {row.slot_index: row.name for row in self.storage.state.plants}
        self.action_panel.set_destinations([
            (
                f"Space {slot + 1} — swap with {occupied[slot]}" if slot in occupied else f"Space {slot + 1} — empty",
                slot,
            )
            for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
            if slot != plant.slot_index
        ] if plant is not None else [])
        if self.scene.begin_move(plant_id):
            self.scene.keep_card_open(plant_id, move_message)
        else:
            self._placement_draft = None

    def _cancel_move(self) -> None:
        if self._placement_draft is None:
            return
        plant_id = self._placement_draft.selected_plant_id
        self._placement_draft = None
        if self.scene._interaction.placing:
            self.scene._interaction.cancel_placement()
            self.scene.placementStateChanged.emit(False)
        self.scene._clear_hit_targets()
        self.scene.update()
        self.action_panel.set_move_active(False)
        self.refresh_all()
        self.scene.keep_card_open(plant_id, "Move cancelled.")
        self._clear_move_feedback()

    def _done_move(self) -> None:
        draft = self._placement_draft
        if draft is None:
            return
        plant_id = draft.selected_plant_id
        ok, message, change = self.engine.commit_placement_draft(draft)
        if not ok or change is None:
            self.scene.keep_card_open(plant_id, message)
            self.placement_note.setText(message)
            self.placement_note.show()
            return
        self._placement_draft = None
        self._undo_placement = change if change.before != change.after else None
        self.scene._interaction.cancel_placement()
        self.action_panel.set_move_active(False)
        self.refresh_all()
        self.refresh_external_surfaces()
        self.scene.keep_card_open(plant_id, "Plant arrangement saved.")
        self.placement_note.setText("Plant arrangement saved.")
        self.placement_note.show()
        self.undo_move_btn.setVisible(self._undo_placement is not None)

    def _apply_native_destination(self) -> None:
        destination = self.action_panel.selected_destination()
        if destination is None or not self.action_panel.plant_id:
            return
        self._place_plant(self.action_panel.plant_id, destination)

    def _place_plant(self, plant_id: str, destination_slot: int) -> None:
        draft = self._placement_draft
        if draft is None or draft.selected_plant_id != plant_id:
            self.scene.keep_card_open(plant_id, "That move session is no longer available.")
            return
        before_slots = draft.scene_slots()
        moving = next((p for p in self.storage.state.plants if p.plant_id == plant_id), None)
        occupant_id = next((pid for pid, slot in before_slots.items() if slot == destination_slot), None)
        occupant = next((p for p in self.storage.state.plants if p.plant_id == occupant_id), None)
        ok, message, change = self.engine.stage_placement(draft, destination_slot)
        if not ok or change is None:
            self.scene.keep_card_open(plant_id, message)
            return
        self.refresh_all()
        if moving is not None and occupant is not None:
            result = f"{moving.name} and {occupant.name} swapped."
        elif moving is not None:
            result = f"{moving.name} moved."
        else:
            result = message
        self.scene.keep_card_open(plant_id, result)
        self.action_panel.set_move_active(True)
        self.action_panel.set_move_message(
            f"Moving {getattr(moving, 'name', 'Plant')}. Choose a new location."
        )
        self.scene.begin_move(plant_id)
        self.placement_note.setText(result)
        self.placement_note.show()
        self.undo_move_btn.show()
        self._move_feedback_generation += 1
        generation = self._move_feedback_generation
        QTimer.singleShot(6000, lambda: self._clear_move_feedback(generation))

    def _undo_move(self) -> None:
        if self._placement_draft is not None:
            ok, message = self.engine.undo_staged_placement(self._placement_draft)
            if ok:
                plant_id = self._placement_draft.selected_plant_id
                self.refresh_all()
                self.scene.begin_move(plant_id)
                self.placement_note.setText(message)
                self.placement_note.show()
                self.undo_move_btn.setVisible(bool(self._placement_draft.history))
            return
        if self._undo_placement is None:
            return
        ok, message, _inverse = self.engine.restore_placement(self._undo_placement)
        if ok:
            self._undo_placement = None
            self.refresh_all()
            self.refresh_external_surfaces()
            self.placement_note.setText("Move undone.")
            self.placement_note.show()
            self.undo_move_btn.hide()
            self._move_feedback_generation += 1
            generation = self._move_feedback_generation
            QTimer.singleShot(3000, lambda: self._clear_move_feedback(generation))
        else:
            self.placement_note.setText(message)
            self.placement_note.show()
            self._undo_placement = None
            self.undo_move_btn.hide()

    def _clear_move_feedback(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._move_feedback_generation:
            return
        self.placement_note.setText("")
        self.placement_note.hide()
        self.undo_move_btn.hide()

    def _refresh_onboarding(self) -> None:
        display = onboarding_display(
            self.storage.state.total_reviews,
            self.config.value("onboarding_version", 0),
            just_completed=self._onboarding_just_completed,
        )
        self.onboarding_panel.setVisible(display.visible)
        if not display.visible:
            return
        self.onboarding_title.setText(display.title)
        self.onboarding_message.setText(self._onboarding_save_error or display.message)
        self.onboarding_action.setVisible(bool(display.action_label))
        self.onboarding_action.setText(display.action_label or "Return to studying")
        self.dismiss_onboarding.setVisible(not self._onboarding_just_completed)
        self.onboarding_panel.setAccessibleDescription(f"{display.title}. {display.message}")

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
        if self._complete_onboarding():
            self._onboarding_confirmation_generation += 1
            self._onboarding_just_completed = False
            self._refresh_onboarding()

    def _complete_first_nurture_guidance(self) -> None:
        if int(self.storage.state.total_reviews or 0) <= 0:
            return
        if self._complete_onboarding():
            self._onboarding_confirmation_generation += 1
            generation = self._onboarding_confirmation_generation
            self._onboarding_just_completed = True
            self._refresh_onboarding()
            QTimer.singleShot(5000, lambda: self._clear_onboarding_confirmation(generation))

    def _clear_onboarding_confirmation(self, generation: int) -> None:
        if generation != self._onboarding_confirmation_generation:
            return
        self._onboarding_just_completed = False
        self._refresh_onboarding()

    def _clear_layout(self, layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_milestone_card(self) -> None:
        self._clear_layout(self.milestone_choices)
        pending = self.engine.pending_milestone()
        next_milestone = self.engine.next_milestone()
        if pending is not None:
            self.milestone_title.setText(f"{pending.review_count:,}-review garden reward")
            self.milestone_note.setText("Choose one new plant for the next garden space.")
            self.milestone_progress.show()
            self.milestone_progress.set_progress(
                "Next plant choice", self.storage.state.total_reviews, pending.review_count,
                value_text=f"{self.storage.state.total_reviews:,} / {pending.review_count:,} reviews",
            )
            for species in pending.offered_species:
                button = QPushButton(f"Choose {format_status_label(species)}")
                _set_button_variant(button, BUTTON_VARIANT_PRIMARY)
                button.clicked.connect(lambda _checked=False, choice=species: self._claim_milestone(choice))
                self.milestone_choices.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            return
        if next_milestone is None:
            self.milestone_title.setText("All 6 garden spaces unlocked")
            self.milestone_note.setText("Every planting surface is available for rearranging.")
            apply_explanatory_tooltip(
                self.milestone_title,
                "You have unlocked every available planting space in the garden.",
            )
            self.milestone_progress.hide()
        else:
            current = max(0, int(self.storage.state.total_reviews))
            self.milestone_title.setText("Next plant choice")
            self.milestone_note.setText("Review cards to unlock another plant for your garden.")
            self.milestone_progress.show()
            self.milestone_progress.set_progress(
                "Next plant choice", current, next_milestone,
                value_text=f"{current:,} / {next_milestone:,} reviews",
            )

    def _claim_milestone(self, species: str) -> None:
        ok, message = self.engine.claim_milestone_reward(species)
        if ok:
            self.refresh_all()
            self.refresh_external_surfaces()
        QMessageBox.information(self, UI_TEXT["app_title"], message)

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = GardenSettingsDialog(self, self.engine, self.config)
        self.settings_dialog.prepare_to_show()
        self.settings_dialog.show()
        self.settings_dialog.raise_()
