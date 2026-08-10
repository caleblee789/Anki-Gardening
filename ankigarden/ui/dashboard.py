from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any

from aqt.qt import (
    QDialog,
    QBoxLayout,
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
    chronological_memories,
    dashboard_layout_is_compact,
    growth_display,
    story_is_just_beginning,
)
from .scene import GardenSceneWidget
from ..display_telemetry import DISPLAY_TELEMETRY
from ..config import ConfigError
from ..models.state import MAX_PLANT_NAME_LENGTH
from ..notices import USER_NOTICES
from ..terminology import (
    ACTIVE_PLANT_EXPLANATION,
    ALL_DUE_EXPLANATION,
    ANKI_STREAK_EXPLANATION,
    FERTILIZER_EXPLANATION,
    GARDEN_CURRENCY_EXPLANATION,
    GROWTH_EXPLANATION,
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


def _affordability_status(price: int, balance: int) -> tuple[bool, str]:
    shortfall = max(0, int(price) - max(0, int(balance)))
    if shortfall == 0:
        return True, "Affordable now."
    unit = "Garden Coin" if shortfall == 1 else "Garden Coins"
    return False, f"Need {shortfall:,} more {unit}."


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
        self._save_status_generation = 0
        self.setWindowTitle(UI_TEXT["settings_window_title"])
        self.setMinimumSize(560, 420)
        self.resize(*self._recommended_window_size(920, 640, width_ratio=0.72, height_ratio=0.72))
        self.setStyleSheet(_button_stylesheet() + "QLabel[saveStatus='true'] { padding:5px 8px; border-radius:8px; }")

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setAccessibleName("Anki Garden settings sections")
        root.addWidget(tabs)

        snapshot_provider = getattr(parent, "_settings_scene_snapshot", None)
        self.behavior = GardenStudioWidget(
            self.config,
            asset_resolver=self.engine.resolve_preview_assets,
            garden_snapshot_provider=snapshot_provider if callable(snapshot_provider) else None,
        )
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
        self.save_status.setTextFormat(Qt.TextFormat.PlainText)
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

        # Save feedback gets the full content width so long validation errors do
        # not compress or misalign the persistent action row.
        behavior_layout.addWidget(self.save_status)
        settings_actions = QHBoxLayout()
        settings_actions.addWidget(self.restore_defaults)
        settings_actions.addStretch(1)
        settings_actions.addWidget(self.cancel_settings)
        settings_actions.addWidget(self.save_settings)
        behavior_layout.addLayout(settings_actions)

        advanced = QWidget()
        a_layout = QVBoxLayout(advanced)
        advanced_hint = QLabel(UI_TEXT["advanced_hint"])
        advanced_hint.setWordWrap(True)
        a_layout.addWidget(advanced_hint)
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        self.troubleshooting_status = QLabel(
            "No display contract or parsing issues are currently recorded."
        )
        self.troubleshooting_status.setWordWrap(True)
        self.troubleshooting_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.troubleshooting_status.setAccessibleName("Troubleshooting report status")
        a_layout.addWidget(self.troubleshooting_status)
        refresh_debug = QPushButton("Refresh report")
        copy_debug = QPushButton("Copy report")
        _set_button_variant(refresh_debug, BUTTON_VARIANT_SECONDARY)
        refresh_debug.clicked.connect(self._refresh_debug_report)
        copy_debug.clicked.connect(self._copy_debug_report)
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
        self._save_status_generation += 1
        self.behavior.apply_persistent_payload(self._persisted_payload)
        self.behavior.reset_preview_defaults()
        self.behavior.collapse_preview_examples()
        self.save_status.setText("")
        self.save_status.setStyleSheet("")
        self.save_status.hide()
        self.save_settings.setEnabled(False)

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
        except ConfigError as exc:
            self._show_save_error(str(exc))
            return
        except Exception as exc:
            try:
                self.config.update(old_payload)
            except ConfigError:
                logger.exception("Anki Garden: unable to roll back settings")
            self.behavior.apply_persistent_payload(old_payload)
            self._show_save_error("Garden progress could not be updated. Your previous settings are still active.")
            logger.exception("Anki Garden: settings save failed", exc_info=exc)
            return
        self._persisted_payload = deepcopy(payload)
        self.engine.assets.metadata.clear()
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
        self._save_status_generation += 1
        self.behavior.apply_persistent_payload(self._persisted_payload)
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
            contract_unit = "failure" if contract_failures == 1 else "failures"
            parsing_unit = "exception" if parsing_exceptions == 1 else "exceptions"
            status = (
                "Display diagnostics need attention: "
                f"{contract_failures:,} contract {contract_unit} and "
                f"{parsing_exceptions:,} parsing {parsing_unit}. "
                "Copy the report when asking for help."
            )
            self.troubleshooting_status.setStyleSheet(
                "color:#ffd0d0; background:#582f34; padding:7px 9px; border-radius:7px;"
            )
        else:
            status = "No display contract or parsing issues are currently recorded."
            self.troubleshooting_status.setStyleSheet(
                "color:#baf3c6; background:#1d4931; padding:7px 9px; border-radius:7px;"
            )
        self.troubleshooting_status.setText(status)
        self.troubleshooting_status.setAccessibleDescription(status)

    def _copy_debug_report(self) -> None:
        QGuiApplication.clipboard().setText(self.debug_report.toPlainText())
        self.troubleshooting_status.setText("Report copied.")
        self.troubleshooting_status.setAccessibleDescription("Troubleshooting report copied.")
        self.troubleshooting_status.setStyleSheet(
            "color:#baf3c6; background:#1d4931; padding:7px 9px; border-radius:7px;"
        )
        self.troubleshooting_status.setFocus()

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
        # This list is content-sized until it reaches its scroll cap. Keeping it
        # vertically Preferred prevents a short story from receiving a tall,
        # empty layout cell above its first memory.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(8, 2, 8, 2)
        self.layout.setSpacing(0)
        self.setWidget(self.container)

    def set_memories(self, memories: list[tuple[str, str]], *, just_beginning: bool = False) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not memories:
            empty = QLabel("This story is just beginning. New memories will appear as this plant grows.")
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
            future = QLabel("This story is just beginning. New memories will appear as this plant grows.")
            future.setWordWrap(True)
            future.setProperty("memoryFuture", True)
            self.layout.addWidget(future)
        hint = self.container.sizeHint().height() + 8
        target_height = max(96, min(200, hint))
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)


class PlantStoryDialog(QDialog):
    def __init__(self, parent: QWidget, engine: Any, plant_id: str) -> None:
        super().__init__(parent)
        self.engine = engine
        self.plant_id = plant_id
        self.setWindowTitle("Plant story")
        self.setMinimumSize(480, 400)
        self.resize(*_fit_dialog_to_screen(self, 640, 520, width_ratio=0.78, height_ratio=0.78))
        self.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#091b18; color:#edf5ea; }
            QFrame[storyHero='true'], QFrame[storyTimeline='true'], QFrame[upNext='true'] { background:#102b25; border:1px solid #385e4f; border-radius:12px; }
            QFrame[memoryRow='true'] { border-left:2px solid #4c8f67; }
            QLabel[memoryMarker='true'] { color:#72ce8c; padding-left:2px; }
            QLabel[memoryDate='true'] { color:#9db0b5; font-size:12px; font-weight:600; }
            QLabel[memoryFuture='true'] { color:#9db0b5; font-style:italic; padding:10px 0; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)
        hero = QFrame()
        hero.setProperty("storyHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        self.name_heading = QLabel()
        self.name_heading.setTextFormat(Qt.TextFormat.PlainText)
        self.name_heading.setWordWrap(True)
        self.name_heading.setStyleSheet("font-size:22px; font-weight:800;")
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color:#b2c4c8;")
        self.artwork = QLabel()
        self.artwork.setFixedSize(96, 96)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setAccessibleName("Plant artwork")
        identity_text = QVBoxLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_heading, 1)
        self.edit_name_btn = QPushButton("✎")
        self.edit_name_btn.setAccessibleName("Rename plant")
        self.edit_name_btn.setToolTip("Rename plant")
        self.edit_name_btn.setFixedSize(36, 36)
        _set_button_variant(self.edit_name_btn, BUTTON_VARIANT_SECONDARY)
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
        identity_text.addWidget(self.summary)
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
        root.addWidget(hero)

        story_panel = QFrame()
        story_panel.setProperty("storyTimeline", True)
        story_layout = QVBoxLayout(story_panel)
        story_layout.setContentsMargins(12, 10, 12, 10)
        story_layout.setSpacing(5)
        timeline_label = QLabel("Your story")
        timeline_label.setStyleSheet("font-size:16px; font-weight:700;")
        story_layout.addWidget(timeline_label)
        self.timeline = MemoryTimeline()
        story_layout.addWidget(self.timeline)
        root.addWidget(story_panel)
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
        root.addWidget(self.up_next)
        root.addStretch(1)
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
            self.summary.setText("This plant is no longer in your garden.")
            self.edit_name_btn.setEnabled(False)
            self.artwork.clear()
            self.timeline.set_memories([])
            return
        self.name_heading.setText(plant.name)
        stage = format_status_label(plant.growth_stage)
        active = "\nBeing nurtured" if self.engine.state.active_plant_id == plant.plant_id else ""
        self.summary.setText(
            f"{format_status_label(plant.species)}, {stage} stage\n"
            f"{plant.growth_points:,} Growth{active}\n"
            f"Planted {self._local_date(plant.planted_on)}"
        )
        try:
            image_path = self.engine.resolve_plant_image(plant.species, plant.growth_stage)
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
        memories = chronological_memories(plant.memories)
        self.timeline.set_memories([
            (self._local_date(memory.occurred_on), self._memory_text(memory, plant.name))
            for memory in memories
        ], just_beginning=story_is_just_beginning(memories))
        progress = growth_display(plant.growth_points)
        if progress.fully_grown:
            self.up_next_text.setText(
                "This plant has reached its rare form. Choose another unfinished plant to nurture; "
                "future card answers will grow that plant."
            )
        else:
            next_stage = format_status_label(progress.next_stage or "next stage")
            answers = max(1, (progress.points_remaining + 9) // 10)
            self.up_next_text.setText(
                f"Reach {next_stage} with {progress.points_remaining:,} more Growth "
                f"(about {_card_answer_count(answers)} before bonuses)."
            )

    @staticmethod
    def _local_date(value: str) -> str:
        try:
            from datetime import date
            parsed = date.fromisoformat(str(value)[:10])
            return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"
        except Exception:
            return str(value)


class NurseryDialog(QDialog):
    """Artwork-led catalog for starters, collected plants, and garden spaces."""

    def __init__(self, parent: QWidget, engine: Any, storage: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.storage = storage
        self.setWindowTitle("Nursery")
        self.setMinimumSize(500, 420)
        self.resize(*_fit_dialog_to_screen(self, 760, 640, width_ratio=0.84, height_ratio=0.84))
        self.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#091b18; color:#edf5ea; }
            QFrame[nurseryHero='true'] { background:#17342e; border:1px solid #527563; border-radius:14px; }
            QFrame[nurseryPlant='true'] { background:#102622; border:1px solid #345348; border-radius:12px; }
            QFrame[nurseryPlant='true'][unaffordable='true'] { background:#0d201c; border-color:#2a4339; }
            QLabel[nurseryTitle='true'] { font-size:22px; font-weight:800; }
            QLabel[nurserySection='true'] { font-size:16px; font-weight:700; padding:8px 2px 2px 2px; }
            QLabel[nurseryMeta='true'] { color:#aac0b1; }
            QLabel[nurseryShortfall='true'] { color:#d8bd81; font-size:12px; }
            QLabel[nurseryCoins='true'] { color:#f1d58a; background:#253d31; border:1px solid #667353; border-radius:10px; padding:6px 9px; font-weight:700; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        hero = QFrame()
        hero.setProperty("nurseryHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        copy = QVBoxLayout()
        self.heading = QLabel("Choose your first plant")
        self.heading.setProperty("nurseryTitle", True)
        self.intro = QLabel("Your first plant is free. Choose the one you would like to nurture.")
        self.intro.setWordWrap(True)
        self.intro.setProperty("nurseryMeta", True)
        copy.addWidget(self.heading)
        copy.addWidget(self.intro)
        hero_layout.addLayout(copy, 1)
        self.coins = QLabel("")
        self.coins.setAccessibleName("Garden Coins balance")
        self.coins.setProperty("nurseryCoins", True)
        self.coins.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.coins, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(hero)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog = QWidget()
        self.catalog_layout = QVBoxLayout(self.catalog)
        self.catalog_layout.setContentsMargins(2, 2, 2, 2)
        self.catalog_layout.setSpacing(9)
        self.scroll.setWidget(self.catalog)
        root.addWidget(self.scroll, 1)

        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Nursery status")
        self.status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.status.hide()
        root.addWidget(self.status)
        footer = QHBoxLayout()
        self.bed_button = QPushButton("")
        self._bed_purchase_pending = False
        _set_button_variant(self.bed_button, BUTTON_VARIANT_SECONDARY)
        self.bed_button.clicked.connect(self._unlock_bed)
        bed_actions = QVBoxLayout()
        bed_actions.setSpacing(3)
        bed_actions.addWidget(self.bed_button)
        self.bed_affordability = QLabel("")
        self.bed_affordability.setWordWrap(True)
        self.bed_affordability.setProperty("nurseryShortfall", True)
        self.bed_affordability.setAccessibleName("Garden space affordability")
        self.bed_affordability.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        bed_actions.addWidget(self.bed_affordability)
        footer.addLayout(bed_actions)
        footer.addStretch(1)
        close_button = QPushButton("Close")
        _set_button_variant(close_button, BUTTON_VARIANT_SECONDARY)
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)
        self.refresh()

    def _clear_catalog(self) -> None:
        while self.catalog_layout.count():
            item = self.catalog_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _plant_artwork(self, species: str, stage: str, size: int = 76) -> QLabel:
        artwork = QLabel()
        artwork.setFixedSize(size, size)
        artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        artwork.setAccessibleName(f"{format_status_label(species)} artwork")
        try:
            path = self.engine.resolve_plant_image(species, stage)
        except Exception:
            path = None
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            artwork.setText(format_status_label(species))
        else:
            artwork.setPixmap(pixmap.scaled(
                artwork.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        return artwork

    def _section_label(self, text: str) -> None:
        label = QLabel(text)
        label.setProperty("nurserySection", True)
        self.catalog_layout.addWidget(label)

    def _owned_card(self, plant: Any) -> QFrame:
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._plant_artwork(plant.species, plant.growth_stage))
        copy = QVBoxLayout()
        title = QLabel(f"{plant.name}\n{format_status_label(plant.species)}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title.setStyleSheet("font-weight:700;")
        place = f"Space {plant.slot_index + 1}" if plant.planted else "In your collection"
        meta = QLabel(
            f"{format_status_label(plant.growth_stage)} stage, "
            f"{plant.growth_points:,} Growth\n{place}"
        )
        meta.setTextFormat(Qt.TextFormat.PlainText)
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
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
            reason = "Nurture another unfinished plant before shelving this one."
            meta.setText(f"{meta.text()}\n{reason}")
            card.setAccessibleDescription(reason)
        action.clicked.connect(
            lambda _checked=False, plant_id=plant.plant_id, planted=plant.planted:
            self._set_placement(plant_id, planted)
        )
        row.addWidget(action)
        action.setMinimumHeight(36)
        return card

    def _available_card(self, species: str, starter_mode: bool) -> QFrame:
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._plant_artwork(species, "seed"))
        copy = QVBoxLayout()
        title = QLabel(format_status_label(species))
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setStyleSheet("font-weight:700;")
        price = int(self.engine.SPECIES_PRICES.get(species, 0))
        balance = int(self.storage.state.currency_balance)
        affordable, affordability = _affordability_status(price, balance)
        if starter_mode:
            affordable = True
            affordability = "Included with your free starter."
        price_text = "Free starter" if starter_mode else f"{price:,} Garden Coins"
        meta = QLabel(f"{price_text}\n{affordability}")
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        action = QPushButton("Choose free starter" if starter_mode else "Unlock")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
        )
        species_name = format_status_label(species)
        action.setAccessibleName(
            f"Choose {species_name} as free starter"
            if starter_mode else
            f"Unlock {species_name} for {price:,} Garden Coins"
        )
        action.setAccessibleDescription(
            f"Add {species_name} to your plant collection. {price_text}. {affordability}"
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
            lambda _checked=False, selected=species:
            self._choose_starter(selected) if starter_mode else self._purchase_species(selected)
        )
        row.addWidget(action)
        action.setMinimumHeight(36)
        return card

    def refresh(self) -> None:
        self._clear_catalog()
        state = self.storage.state
        starter_mode = not bool(getattr(state, "starter_selection_complete", True))
        summary = self.engine.catalog_summary()
        available = list(summary.get("available_species", []))
        owned_count = int(summary.get("owned_count", len(state.plants)))
        available_count = int(summary.get("available_count", len(available)))
        catalog_summary = (
            f"{_plant_count(owned_count)} collected. "
            f"{_plant_count(available_count)} available now."
        )
        self.coins.setText(f"{state.currency_balance:,} Garden Coins")
        self.heading.setText("Choose your first plant" if starter_mode else "Nursery")
        intro_text = (
            "Your first plant is free. Choose the one you would like to nurture."
            if starter_mode else
            catalog_summary
        )
        self.intro.setText(intro_text)
        self.intro.setAccessibleDescription(intro_text)
        if state.plants:
            self._section_label("Your plants")
            for plant in sorted(state.plants, key=lambda item: (item.slot_index is None, item.name.lower())):
                self.catalog_layout.addWidget(self._owned_card(plant))
        self._section_label("Available now")
        if available:
            for species in available:
                self.catalog_layout.addWidget(self._available_card(species, starter_mode))
        else:
            empty = QLabel(
                "The Nursery is stocking new plants. More will appear when their complete artwork is ready."
                if starter_mode else "You have collected every plant currently available."
            )
            empty.setWordWrap(True)
            empty.setProperty("nurseryMeta", True)
            self.catalog_layout.addWidget(empty)
        self.catalog_layout.addStretch(1)
        bed_price = self.engine.next_bed_price()
        self.bed_button.setVisible(not starter_mode and bed_price is not None)
        self.bed_affordability.setVisible(not starter_mode and bed_price is not None)
        if bed_price is not None:
            bed_affordable, bed_status = _affordability_status(
                int(bed_price), int(state.currency_balance)
            )
            self.bed_button.setText(
                f"Unlock space {state.unlocked_slots + 1} for {bed_price:,} Garden Coins"
            )
            self.bed_button.setAccessibleDescription(
                f"Unlock garden space {state.unlocked_slots + 1} for {bed_price:,} Garden Coins. "
                f"{bed_status}"
            )
            self.bed_button.setAccessibleName(
                f"Unlock garden space {state.unlocked_slots + 1} for {bed_price:,} Garden Coins"
            )
            self.bed_affordability.setText(bed_status)
            self.bed_affordability.setAccessibleDescription(
                f"Garden space {state.unlocked_slots + 1}. {bed_status}"
            )
            self.bed_affordability.setStyleSheet(
                "color:#9dd6a8; font-size:12px;"
                if bed_affordable else
                "color:#d8bd81; font-size:12px;"
            )
        else:
            bed_affordable = False
        if not self._bed_purchase_pending:
            self.bed_button.setEnabled(
                not starter_mode and bed_price is not None and bed_affordable
            )

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
        ok, message, _plant = self.engine.choose_starter(species)
        self._show_result(ok, message)
        if ok:
            parent = self.parent()
            if parent is not None and hasattr(parent, "_complete_onboarding"):
                parent._complete_onboarding()
            self._refresh_parent()
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
        bed_affordable = (
            bed_price is not None
            and int(self.storage.state.currency_balance) >= int(bed_price)
        )
        self.bed_button.setEnabled(
            self.bed_button.isVisible()
            and not starter_mode
            and bed_price is not None
            and bed_affordable
        )

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("plantCard", True)
        self.setAccessibleName("Selected plant details")
        self.plant_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        self.heading = QLabel("")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setProperty("plantCardHeading", True)
        self.heading.setWordWrap(True)
        self.identity = QLabel("")
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.identity.setProperty("actionMeta", True)
        self.growth_section = QLabel("Plant Growth")
        self.growth_section.setProperty("plantCardSection", True)
        self.stage_progress = LabeledProgress("Selected plant growth")
        self.growth_summary = QLabel("")
        self.fertilizer_summary = QLabel("")
        for label in (self.growth_summary, self.fertilizer_summary):
            label.setWordWrap(True)
            label.setProperty("actionMeta", True)
        self.action_hint = QLabel("")
        self.action_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.action_hint.setWordWrap(True)
        self.action_hint.setProperty("actionHint", True)
        layout.addWidget(self.heading)
        layout.addWidget(self.identity)
        layout.addWidget(self.growth_section)
        layout.addWidget(self.stage_progress)
        layout.addWidget(self.growth_summary)
        layout.addWidget(self.fertilizer_summary)
        layout.addWidget(self.action_hint)

        self.nurture = QPushButton("Nurture")
        self.fertilize = QPushButton("Fertilize")
        self.move = QPushButton("Move")
        self.story = QPushButton("Story")
        _set_button_variant(self.nurture, BUTTON_VARIANT_PRIMARY)
        for button in (self.fertilize, self.move, self.story):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
        apply_explanatory_tooltip(self.nurture, ACTIVE_PLANT_EXPLANATION)
        apply_explanatory_tooltip(self.fertilize, FERTILIZER_EXPLANATION)
        apply_explanatory_tooltip(self.move, "Move this plant to another highlighted garden space.")
        apply_explanatory_tooltip(self.story, "View this plant’s name, age, and growth history.")
        actions = QGridLayout()
        actions.setSpacing(6)
        actions.addWidget(self.nurture, 0, 0)
        actions.addWidget(self.fertilize, 0, 1)
        actions.addWidget(self.move, 1, 0)
        actions.addWidget(self.story, 1, 1)
        layout.addLayout(actions)
        for button in (self.nurture, self.fertilize, self.move, self.story):
            button.setMinimumHeight(36)
        self.hide()

    def set_selected(self, plant: dict[str, Any] | None) -> None:
        self.plant_id = str(plant.get("plant_id", "")) if isinstance(plant, dict) else ""
        if not self.plant_id or plant is None:
            self.hide()
            return
        name = str(plant.get("name") or plant.get("species") or "Plant")
        species = format_status_label(plant.get("species") or "plant")
        stage = format_status_label(plant.get("stage") or "seed")
        self.heading.setText(name)
        self.identity.setText(f"{species}\n{stage} stage")
        growth_points = max(0, int(plant.get("growth_points", 0) or 0))
        if bool(plant.get("fully_grown")):
            self.stage_progress.set_progress("Final stage", 1, 1, value_text="Rare stage, fully grown")
            self.growth_summary.setText(f"{growth_points:,} total Growth")
        else:
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            next_stage = format_status_label(plant.get("next_stage") or "next stage")
            self.stage_progress.set_progress(f"Progress to {next_stage}", stage_points, stage_goal)
            remaining = max(0, int(plant.get("points_remaining", 0) or 0))
            reviews_remaining = max(0, int(plant.get("reviews_remaining", 0) or 0))
            self.growth_summary.setText(
                f"{remaining:,} Growth to {next_stage}\n"
                f"About {_card_answer_count(reviews_remaining)} before bonuses"
            )
        fertilizer_growth = max(0, int(plant.get("fertilizer_growth", 0) or 0))
        fertilizer_text = str(plant.get("fertilizer_text") or "No active Fertilizer")
        self.fertilizer_summary.setText(
            f"Fertilizer\n{fertilizer_text}" if fertilizer_growth else "Fertilizer\nNone active"
        )
        active = bool(plant.get("is_active"))
        fully_grown = bool(plant.get("fully_grown"))
        self.nurture.setText("Nurturing" if active else "Nurture")
        self.nurture.setEnabled(not active and not fully_grown)
        self.fertilize.setEnabled(active and not fully_grown)
        self.fertilize.setText("Replace Fertilizer" if fertilizer_growth else "Fertilize")
        if fully_grown:
            action_hint = "This plant is fully grown, so Nurture and Fertilizer are no longer needed."
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
        self.action_hint.setText(action_hint)
        self.action_hint.setAccessibleDescription(action_hint)
        self.nurture.setAccessibleDescription(f"{ACTIVE_PLANT_EXPLANATION} {nurture_reason}")
        self.fertilize.setAccessibleDescription(f"{FERTILIZER_EXPLANATION} {fertilizer_reason}")
        self.show()


class GardenStatsStrip(QFrame):
    """Garden-wide facts with a stable wide and compact reading order."""

    METRICS = (
        ("growth", "Plant Growth", GROWTH_EXPLANATION),
        ("streak", "Anki streak", ANKI_STREAK_EXPLANATION),
        ("currency", "Garden Coins", GARDEN_CURRENCY_EXPLANATION),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("gardenStats", True)
        self.setAccessibleName("Garden study statistics")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 7, 8, 7)
        self.grid.setHorizontalSpacing(7)
        self.grid.setVerticalSpacing(7)
        self.cells: dict[str, QFrame] = {}
        self.values: dict[str, QLabel] = {}
        self.metric_copy: dict[str, tuple[str, str]] = {}
        for key, title, description in self.METRICS:
            cell = QFrame()
            cell.setProperty("gardenStatCell", True)
            cell.setAccessibleName(title)
            cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            apply_explanatory_tooltip(cell, description)
            content = QVBoxLayout(cell)
            content.setContentsMargins(9, 6, 9, 6)
            content.setSpacing(1)
            label = QLabel(title)
            label.setProperty("gardenStatLabel", True)
            value = QLabel("—")
            value.setProperty("gardenStatValue", True)
            value.setWordWrap(True)
            content.addWidget(label)
            content.addWidget(value)
            self.cells[key] = cell
            self.values[key] = value
            self.metric_copy[key] = (title, description)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        for key, _title, _description in self.METRICS:
            self.grid.removeWidget(self.cells[key])
        if compact:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 2)
            self.grid.addWidget(self.cells["streak"], 1, 0)
            self.grid.addWidget(self.cells["currency"], 1, 1)
            columns = 2
        else:
            for index, (key, _title, _description) in enumerate(self.METRICS):
                self.grid.addWidget(self.cells[key], 0, index)
            columns = len(self.METRICS)
        for column in range(len(self.METRICS)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

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
                        f"{title}: {value}. {explanation}"
                    )


class RearrangeBar(QFrame):
    """Mode-only controls kept separate from plant inspection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("movePanel", True)
        self.plant_id = ""
        self.bar_layout = QHBoxLayout(self)
        self.bar_layout.setContentsMargins(10, 8, 10, 8)
        copy = QVBoxLayout()
        title = QLabel("Move plant")
        title.setProperty("moveTitle", True)
        self.instructions = QLabel("")
        self.instructions.setTextFormat(Qt.TextFormat.PlainText)
        self.instructions.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(self.instructions)
        self.bar_layout.addLayout(copy, 1)
        self.cancel = QPushButton("Cancel")
        _set_button_variant(self.cancel, BUTTON_VARIANT_SECONDARY)
        self.cancel.setMinimumHeight(40)
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
    MIN_WINDOW_WIDTH = 620
    MIN_WINDOW_HEIGHT = 520
    DEFAULT_WINDOW_WIDTH = 1240
    DEFAULT_WINDOW_HEIGHT = 840
    COMPACT_LAYOUT_WIDTH = 900

    def __init__(self, mw_window: Any, engine: Any, storage: Any, config: Any) -> None:
        super().__init__(mw_window)
        self.engine = engine
        self.storage = storage
        self.config = config
        self.mw_window = mw_window
        self.settings_dialog: GardenSettingsDialog | None = None
        self.nursery_dialog: NurseryDialog | None = None
        self._starter_prompt_scheduled = False
        self._undo_placement: Any = None
        self._placement_draft: Any = None
        self._move_feedback_generation = 0
        self._stage_message_generation = 0
        self._pending_feedback_ack_ids: tuple[str, ...] = ()
        self._pending_transition_ack: tuple[Any, ...] = ()
        self._onboarding_just_completed = False
        self._onboarding_confirmation_generation = 0
        self._onboarding_save_error = ""
        self._compact_layout: bool | None = None
        self._application_filter_installed = False
        self._skip_next_show_refresh = False
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
                "Your Garden progress is safe, but the display could not refresh yet. "
                "Reopen the Garden to retry.",
                key="display_refresh",
            )
            raise
        self._skip_next_show_refresh = not self.isVisible()

    def prompt_starter_if_needed(self) -> None:
        if (
            not self._starter_prompt_scheduled
            and not bool(getattr(self.storage.state, "starter_selection_complete", True))
        ):
            self._starter_prompt_scheduled = True
            QTimer.singleShot(0, self._open_nursery)

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
            QFrame[plantCard='true'] {{ background:#102421; border:1px solid #78947c; border-radius:12px; }}
            QFrame[plantCardDock='true'] {{ background:transparent; border:0; }}
            QFrame[transientFeedback='true'] {{ background:transparent; border:0; }}
            QLabel[plantCardHeading='true'] {{ color:#f5f7e8; font-size:17px; font-weight:800; }}
            QLabel[plantCardSection='true'] {{ color:#d8b875; font-size:12px; font-weight:800; letter-spacing:.8px; }}
            QFrame[movePanel='true'] {{ background:#17342e; border-left:3px solid #d1ad69; border-radius:9px; }}
            QFrame[gardenStats='true'] {{ background:#0d211e; border:1px solid #29483c; border-radius:10px; }}
            QFrame[gardenStatCell='true'] {{ background:#142c27; border:1px solid #2a493e; border-radius:8px; }}
            QFrame[gardenStatCell='true']:hover {{ border-color:#547865; }}
            QFrame[gardenStatCell='true']:focus {{ border:2px solid #e5f2a6; }}
            QLabel[gardenStatLabel='true'] {{ color:#91aa9b; font-size:12px; font-weight:700; }}
            QLabel[gardenStatValue='true'] {{ color:#edf5ea; font-size:16px; font-weight:750; }}
            QFrame[onboarding='true'] {{ background:#17342e; border:1px solid #4e7867; border-radius:12px; }}
            QFrame[progressRow='true'] {{ background:#0d211e; border:1px solid #27443a; border-radius:9px; }}
            QFrame[progressRow='true'][completed='true'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QFrame[progressRow='true'][achievementState='locked'] {{ border-left:3px solid #52645d; }}
            QFrame[progressRow='true'][achievementState='in_progress'] {{ border-left:3px solid #d1ad69; }}
            QFrame[progressRow='true'][achievementState='unlocked'] {{ background:#10271f; border-left:3px solid #56ba7f; }}
            QLabel[typography='title'] {{ font-size: 20px; font-weight: 800; letter-spacing: 0.3px; }}
            QLabel[typography='section-title'] {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
            QLabel[typography='muted-body'] {{ font-size: 13px; color: {self.TEXT_MUTED}; }}
            QLabel[typography='status-chip'] {{ font-size: 12px; font-weight: 600; letter-spacing: 0.1px; }}
            QLabel[chip='true'] {{ padding: {self.CHIP_PADDING[0]}px {self.CHIP_PADDING[1]}px; background:{self.CHIP_BG}; border-radius:{self.CHIP_BORDER_RADIUS}px; }}
            QLabel[nurturingPill='true'] {{ padding:5px 10px; color:#f5e5ba; background:#5a4824; border:1px solid #8a6b34; border-radius:10px; font-weight:700; }}
            QLabel[actionMeta='true'], QLabel[rowCriteria='true'] {{ color:{self.TEXT_MUTED}; font-size:13px; }}
            QLabel[actionHint='true'] {{ color:#d8cba2; font-size:12px; padding-top:2px; }}
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
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setWidget(page)
        outer.addWidget(self.page_scroll)

        top = QFrame()
        top.setProperty("topBar", True)
        t_layout = QHBoxLayout(top)
        t_layout.setContentsMargins(4, 4, 4, 4)
        t_layout.setSpacing(self.CHIP_SPACING)
        self.title_label = QLabel(UI_TEXT["title_banner"])
        self._apply_typography(self.title_label, "title")
        self.title_subtitle = QLabel("Study. Nurture. Watch your garden grow.")
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
            "Change garden display preferences.",
        )
        self.nursery_recovery_btn = QPushButton("Open Nursery")
        _set_button_variant(self.nursery_recovery_btn, BUTTON_VARIANT_SECONDARY)
        self.nursery_recovery_btn.setAccessibleDescription(
            "Open the Nursery. This recovery action appears because its garden building is unavailable."
        )
        self.nursery_recovery_btn.clicked.connect(self._open_nursery)
        self.nursery_recovery_btn.hide()
        t_layout.addLayout(title_stack)
        t_layout.addStretch(1)
        t_layout.addWidget(self.nursery_recovery_btn)
        t_layout.addWidget(self.settings_btn)
        root.addWidget(top)

        self.onboarding_panel = QFrame()
        self.onboarding_panel.setProperty("onboarding", True)
        self.onboarding_panel.setAccessibleName("Getting started with Anki Garden")
        self.onboarding_layout = QHBoxLayout(self.onboarding_panel)
        self.onboarding_layout.setContentsMargins(*self.CARD_PADDING)
        onboarding_copy = QVBoxLayout()
        self.onboarding_title = QLabel("")
        self.onboarding_title.setProperty("rowTitle", True)
        self.onboarding_message = QLabel("")
        self.onboarding_message.setWordWrap(True)
        self._apply_typography(self.onboarding_message, "muted-body")
        onboarding_copy.addWidget(self.onboarding_title)
        onboarding_copy.addWidget(self.onboarding_message)
        self.onboarding_layout.addLayout(onboarding_copy, 1)
        self.onboarding_action = QPushButton("Show me")
        _set_button_variant(self.onboarding_action, BUTTON_VARIANT_PRIMARY)
        self.onboarding_action.clicked.connect(self._show_nursery_landmark)
        self.onboarding_layout.addWidget(self.onboarding_action)
        self.dismiss_onboarding = QPushButton("Dismiss tips")
        _set_button_variant(self.dismiss_onboarding, BUTTON_VARIANT_SECONDARY)
        self.dismiss_onboarding.setAccessibleDescription("Hide first-use garden guidance")
        self.dismiss_onboarding.clicked.connect(self._dismiss_onboarding)
        self.onboarding_layout.addWidget(self.dismiss_onboarding)
        root.addWidget(self.onboarding_panel)

        hero_card = self._card_frame()
        hero_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        h_layout = QVBoxLayout(hero_card)
        h_layout.setContentsMargins(*self.CARD_PADDING)
        h_layout.setSpacing(self.CARD_SPACING)
        self.scene = GardenSceneWidget()
        self.scene.placementRequested.connect(self._place_plant)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self.scene.landmarkActivated.connect(self._on_landmark_activated)
        self.scene.landmarksChanged.connect(self._sync_nursery_recovery)
        self.scene.placementStateChanged.connect(self._on_placement_state)
        self.scene.cancelPlacementRequested.connect(self._cancel_move)
        self.scene.cardGeometryChanged.connect(self._position_plant_card)
        self.scene.setMinimumHeight(260)
        self.garden_stats_bar = GardenStatsStrip()
        self.plant_card = PlantInfoCard(self.scene)
        self.plant_card.nurture.clicked.connect(lambda: self._nurture_plant(self.plant_card.plant_id))
        self.plant_card.fertilize.clicked.connect(lambda: self._open_fertilizer_menu(self.plant_card.plant_id))
        self.plant_card.move.clicked.connect(lambda: self._begin_move(self.plant_card.plant_id))
        self.plant_card.story.clicked.connect(lambda: self._open_plant_story(self.plant_card.plant_id))
        self.plant_card_dock = QFrame()
        self.plant_card_dock.setProperty("plantCardDock", True)
        self.plant_card_dock_layout = QVBoxLayout(self.plant_card_dock)
        self.plant_card_dock_layout.setContentsMargins(0, 0, 0, 0)
        self.plant_card_dock_layout.setSpacing(0)
        self.plant_card_dock_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.plant_card_dock.hide()
        self.rearrange_bar = RearrangeBar()
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
        feedback_layout = QVBoxLayout(self.feedback_panel)
        feedback_layout.setContentsMargins(0, 0, 0, 0)
        feedback_layout.setSpacing(5)
        feedback_layout.addLayout(placement_row)
        feedback_layout.addWidget(self.stage_transition_note)
        feedback_layout.addWidget(self.same_day_catchup_note)
        feedback_layout.addWidget(self.status_notice)
        h_layout.addWidget(self.garden_stats_bar)
        # All temporary guidance and results belong before the artwork they
        # describe. Below a full-height scene they can be valid but invisible.
        h_layout.addWidget(self.rearrange_bar)
        h_layout.addWidget(self.feedback_panel)
        h_layout.addWidget(self.scene)
        h_layout.addWidget(self.plant_card_dock)
        root.addWidget(hero_card)

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
        self.achievement_list = ProgressList("Achievement progress")
        self.collection_list = ProgressList("Plant collection")
        self.details_tabs = QTabWidget()
        self.details_tabs.setDocumentMode(True)
        self.details_tabs.setAccessibleName("Garden progress details")
        self.details_tabs.addTab(self.today_list, UI_TEXT["today_progress_title"])
        self.details_tabs.addTab(self.achievement_list, "Achievements")
        self.details_tabs.addTab(self.collection_list, "Collection")
        self.details_tabs.setTabToolTip(0, "See today’s card answers, Growth, and Garden Coin rewards.")
        self.details_tabs.setTabToolTip(1, "View long-term milestones and unlocked achievements.")
        self.details_tabs.setTabToolTip(2, "View plant names, locations, stages, and Growth.")
        self.today_heading = QLabel("Today’s progress")
        self._apply_typography(self.today_heading, "section-title")
        self.today_summary = QLabel("")
        self.today_summary.setWordWrap(True)
        self._apply_typography(self.today_summary, "muted-body")
        self.today_list.rows.insertWidget(0, self.today_summary)
        self.today_list.rows.insertWidget(0, self.today_heading)
        self.details_tabs.hide()
        progress_row = QHBoxLayout()
        self.progress_toggle = QPushButton("Progress")
        self.progress_toggle.setCheckable(True)
        self.progress_toggle.setAccessibleName("Show garden progress")
        _set_button_variant(self.progress_toggle, BUTTON_VARIANT_SECONDARY)
        self.progress_toggle.toggled.connect(self._set_progress_expanded)
        progress_row.addWidget(self.progress_toggle)
        progress_row.addStretch(1)
        root.addLayout(progress_row)
        root.addWidget(self.details_tabs)

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)

    def _set_progress_expanded(self, expanded: bool) -> None:
        self.details_tabs.setVisible(bool(expanded))
        self.progress_toggle.setText("Hide progress" if expanded else "Progress")
        self.progress_toggle.setAccessibleName(
            "Hide garden progress" if expanded else "Show garden progress"
        )
        if expanded:
            QTimer.singleShot(
                0,
                lambda: self.page_scroll.ensureWidgetVisible(self.details_tabs, 12, 12),
            )

    def refresh_all(self, *, acknowledge: bool | None = None) -> None:
        if acknowledge is None:
            try:
                acknowledge = bool(self.isVisible())
            except RuntimeError:
                acknowledge = False
        DISPLAY_TELEMETRY.track_render("dashboard")
        state = self.storage.state
        notice = _learner_text(USER_NOTICES.current.message)
        self.status_notice.setText(notice)
        self.status_notice.setVisible(bool(notice))
        self.status_notice.setStyleSheet("color:#ffd0d0;" if notice else "")
        self.status_notice.setAccessibleDescription(notice)
        stats = state.daily_stats
        streak_days = max(0, int(state.streak_days))
        streak_bonus = self.engine.current_streak_bonus_percent()
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
        else:
            progress = growth_display(active.growth_points)
            active_growth = (
                f"{active.growth_points:,} Growth\nFully grown"
                if progress.fully_grown else
                f"{active.growth_points:,} Growth\n"
                f"Needs {progress.points_remaining:,} more to reach "
                f"{format_status_label(progress.next_stage or 'next stage')}"
            )
        self.garden_stats_bar.set_values(
            growth=active_growth,
            streak=streak_value,
            currency=f"{state.currency_balance:,}",
        )
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
        self.stage_transition_note.setVisible(bool(progress_message))
        self.stage_transition_note.setAccessibleDescription(progress_message)
        if progress_message:
            QTimer.singleShot(4200, lambda: self._clear_stage_message(stage_generation))

        selected_id = self.scene.selected_plant_id()
        self.scene.set_scene(
            {
                "weather": state.selected_weather,
                "theme": str(self.config.value("visual_theme", "verdant_twilight")),
                "health": min(1.0, 0.5 + (streak_bonus / 50.0)),
                "growth": min(1.0, stats.growth_earned / max(10, stats.reviewed * 10)),
                "unlocked_slots": state.unlocked_slots,
                "streak_days": state.streak_days,
                "streak_bonus_percent": streak_bonus,
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
                "plants": [
                    self._plant_scene_payload(plant)
                    for plant in state.plants
                    if plant.slot_index is not None
                ],
            }
        )
        self._on_scene_selection(selected_id or "")

        self.today_list.clear()
        self.today_heading = QLabel("Today’s progress")
        self._apply_typography(self.today_heading, "section-title")
        self.today_summary = QLabel(
            f"{_card_answer_count(stats.reviewed)}\n"
            f"{stats.growth_earned:,} Growth today"
        )
        self.today_summary.setWordWrap(True)
        self._apply_typography(self.today_summary, "muted-body")
        self.today_list.add_row(self.today_heading)
        self.today_list.add_row(self.today_summary)
        due_row = ProgressRow()
        due_row.set_item(
            "Finish all due cards",
            "Finish today’s available review and learning cards.",
            1 if stats.completed_due_cards else 0,
            1,
            completed=stats.completed_due_cards,
            value_text="Complete" if stats.completed_due_cards else "Not yet complete",
            completion_text="Complete\n+10 Garden Coins",
            explanation=(
                f"{ALL_DUE_EXPLANATION} At least one card answer is required. "
                "The reward is 10 Garden Coins."
            ),
        )
        self.today_list.add_row(due_row)
        growth_row = ProgressRow()
        growth_row.set_information(
            "Today’s Plant Growth",
            "Growth earned from today’s card answers.",
            (
                f"{stats.base_growth:,} base + {stats.streak_bonus_growth:,} streak + "
                f"{stats.fertilizer_growth:,} Fertilizer = {stats.growth_earned:,} Growth"
            ),
            explanation=GROWTH_EXPLANATION,
        )
        self.today_list.add_row(growth_row)
        currency_heading = QLabel("Recent Garden Coins")
        self._apply_typography(currency_heading, "section-title")
        self.today_list.add_row(currency_heading)
        recent_transactions = list(reversed(state.currency_transactions[-5:]))
        if not recent_transactions:
            empty_currency = QLabel("No Garden Coins earned or spent yet.")
            self._apply_typography(empty_currency, "muted-body")
            self.today_list.add_row(empty_currency)
        for transaction in recent_transactions:
            sign = "+" if transaction.delta > 0 else ""
            activity = QLabel(
                f"{sign}{transaction.delta:,}: {transaction.reason}\n"
                f"Balance: {transaction.balance:,}"
            )
            activity.setTextFormat(Qt.TextFormat.PlainText)
            activity.setWordWrap(True)
            activity.setProperty("actionMeta", True)
            self.today_list.add_row(activity)
        self.today_list.finish()

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
        self._refresh_collection_list()
        self._pending_feedback_ack_ids = tuple(event.event_id for event in feedback)
        self._pending_transition_ack = tuple(transitions)
        if acknowledge:
            self.acknowledge_rendered_feedback()

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
        self.stage_transition_note.setText("")
        self.stage_transition_note.setAccessibleDescription("")
        self.stage_transition_note.hide()

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
        self.plant_card.set_selected(plant)
        self._position_plant_card()
        if plant is not None:
            QTimer.singleShot(0, self._ensure_selected_card_visible)

    def _on_landmark_activated(self, action_id: str) -> None:
        handlers = {"garden.nursery.open": self._open_nursery}
        handler = handlers.get(str(action_id))
        if handler is not None:
            self._complete_onboarding()
            handler()

    def _open_nursery(self) -> None:
        if self.scene._interaction.placing:
            return
        self.scene.dismiss_selection()
        self.nursery_dialog = NurseryDialog(self, self.engine, self.storage)
        self.nursery_dialog.exec()
        if not bool(getattr(self.storage.state, "starter_selection_complete", True)):
            self._starter_prompt_scheduled = False
        self._refresh_after_commit("Nursery dialog")

    def _show_nursery_landmark(self) -> None:
        if not self.scene.focus_landmark("garden.nursery.open"):
            self._open_nursery()

    def _sync_nursery_recovery(self) -> None:
        """Expose a button only when artwork-first Nursery navigation failed."""
        available = self.scene.landmark_geometry("garden.nursery.open") is not None
        self.nursery_recovery_btn.setVisible(
            not available and not self.scene._interaction.placing
        )

    def _on_placement_state(self, active: bool) -> None:
        self.plant_card.hide()
        self.plant_card_dock.hide()
        self.rearrange_bar.setVisible(active)
        self._sync_nursery_recovery()

    def resizeEvent(self, event: Any) -> None:
        if hasattr(self, "onboarding_layout"):
            self._apply_responsive_layout(event.size().width())
        self._update_scene_height(event.size().height())
        QTimer.singleShot(0, self._position_plant_card)
        super().resizeEvent(event)

    def _apply_responsive_layout(self, width: int) -> None:
        compact = dashboard_layout_is_compact(width)
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        self.onboarding_layout.setDirection(direction)
        self.milestone_layout.setDirection(direction)
        self.rearrange_bar.set_compact(compact)
        self.garden_stats_bar.set_compact(compact)
        self._set_plant_card_mode(compact)

    def _set_plant_card_mode(self, compact: bool) -> None:
        if compact:
            self._dock_plant_card()
            return
        if self.plant_card.parentWidget() is not self.scene:
            self.plant_card_dock_layout.removeWidget(self.plant_card)
            self.plant_card.setParent(self.scene)
        self.plant_card_dock.hide()

    def _dock_plant_card(self) -> None:
        """Use the external card region when an in-scene card cannot fit safely."""
        if self.plant_card.parentWidget() is not self.plant_card_dock:
            self.plant_card.setParent(self.plant_card_dock)
            self.plant_card_dock_layout.addWidget(self.plant_card)
        self.plant_card.setMinimumWidth(0)
        self.plant_card.setMaximumWidth(560)
        self.plant_card_dock.show()
        self.plant_card.show()

    def _position_plant_card(self) -> None:
        if not hasattr(self, "plant_card") or not self.plant_card.plant_id or self.scene._interaction.placing:
            if hasattr(self, "plant_card"):
                self.plant_card.hide()
            if hasattr(self, "plant_card_dock"):
                self.plant_card_dock.hide()
            return
        if self._compact_layout:
            self._dock_plant_card()
            return
        if self.plant_card.parentWidget() is not self.scene:
            self.plant_card_dock_layout.removeWidget(self.plant_card)
            self.plant_card.setParent(self.scene)
        self.plant_card_dock.hide()
        available_width = max(220, self.scene.width() - 24)
        self.plant_card.setFixedWidth(min(360, available_width))
        self.plant_card.adjustSize()
        card_height = min(max(220, self.plant_card.sizeHint().height()), max(220, self.scene.height() - 24))
        geometry = self.scene.card_geometry(self.plant_card.width(), card_height)
        if geometry is None:
            self._dock_plant_card()
            return
        self.plant_card.setGeometry(
            round(geometry.x()), round(geometry.y()), round(geometry.width()), round(geometry.height())
        )
        self.plant_card.show()
        self.plant_card.raise_()

    def _ensure_selected_card_visible(self) -> None:
        if self.plant_card.plant_id and self.plant_card.isVisible():
            self.page_scroll.ensureWidgetVisible(self.plant_card, 12, 12)

    def _ensure_move_controls_visible(self) -> None:
        target = self.rearrange_bar if self.rearrange_bar.isVisible() else self.placement_note
        if target.isVisible():
            self.page_scroll.ensureWidgetVisible(target, 12, 12)

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
        available_width = max(1, int(self.width()) - self.ROOT_MARGINS[0] - self.ROOT_MARGINS[2] - 24)
        scene_aspect = 4 / 3 if available_width < 620 else 16 / 9 if available_width < 1400 else 12 / 5
        target = max(280, min(800, int(available_width / scene_aspect)))
        self.scene.setMinimumHeight(target)
        self.scene.setMaximumHeight(target)

    def refresh_external_surfaces(self) -> None:
        """Refresh Anki webviews after a dashboard mutation changes home-card data."""
        try:
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
        except Exception:
            logger.exception("Anki Garden: unable to refresh Anki home surfaces")

    def _refresh_after_commit(self, context: str) -> None:
        """Refresh views without turning a saved mutation into an ambiguous failure."""
        USER_NOTICES.clear(key="display_refresh")
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: %s was saved but the Garden refresh failed", context)
            USER_NOTICES.publish(
                "Your Garden change was saved, but the display could not refresh yet. Reopen the Garden to retry.",
                key="display_refresh",
            )
        try:
            self.refresh_external_surfaces()
        except Exception:
            logger.exception("Anki Garden: %s was saved but Anki home refresh failed", context)

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
            "growth_today": self.storage.state.daily_stats.plant_growth.get(plant.plant_id, 0),
            "reviews_remaining": reviews_remaining,
            "fertilizer_text": self._fertilizer_text(plant),
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
            "weather": state.selected_weather,
            "unlocked_slots": state.unlocked_slots,
            "growth": active_progress,
            "streak_days": state.streak_days,
            "streak_bonus_percent": self.engine.current_streak_bonus_percent(),
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
        total_minutes = max(1, (remaining + 59) // 60)
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
            self._refresh_selected_plant_card()
            self._complete_first_nurture_guidance()
            return
        ok, message = self.engine.set_active_plant(plant_id)
        if not ok:
            QMessageBox.warning(self, UI_TEXT["app_title"], _learner_text(message))
            return
        self._refresh_after_commit("nurtured-plant choice")
        self._complete_first_nurture_guidance()

    def _open_plant_story(self, plant_id: str) -> None:
        dialog = PlantStoryDialog(self, self.engine, plant_id)
        dialog.exec()
        self._refresh_after_commit("Plant Story")

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
        move_message = f"Moving {name}. Choose a highlighted garden space. Press Escape to cancel."
        self.rearrange_bar.plant_id = plant_id
        self.rearrange_bar.instructions.setText(move_message)
        if self.scene.begin_move(plant_id, self.engine.valid_destination_slots(draft)):
            self.rearrange_bar.show()
            QTimer.singleShot(0, self._ensure_move_controls_visible)
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
                f"Space {slot + 1} — swap with {occupied[slot]}"
                if slot in occupied else f"Space {slot + 1} — empty",
                slot,
            )
            for slot in range(max(0, min(6, int(self.storage.state.unlocked_slots))))
            if slot != current_slot and slot in valid_slots
        ])

    def _cancel_move(self) -> None:
        self._move_feedback_generation += 1
        self._placement_draft = None
        self.scene.finish_move("Move cancelled. Plant selection remains available.")
        self.rearrange_bar.hide()
        try:
            self.refresh_all()
        except Exception:
            logger.exception("Anki Garden: move cancelled but persisted scene did not refresh")
        self._clear_move_feedback()

    def _finish_failed_move(self, message: str) -> None:
        """Return the scene to persisted state after any terminal move error."""
        message = _learner_text(message)
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
        self.placement_note.setFocus()
        QTimer.singleShot(0, self._ensure_move_controls_visible)
        self.undo_move_btn.setVisible(self._undo_placement is not None)

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
        self.placement_note.setText("Plant arrangement saved.")
        self.placement_note.setAccessibleDescription("Plant arrangement saved.")
        self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.placement_note.show()
        self.undo_move_btn.setVisible(self._undo_placement is not None)
        self.placement_note.setFocus()
        QTimer.singleShot(0, self._ensure_move_controls_visible)

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
        self.placement_note.setText(result)
        self.placement_note.setAccessibleDescription(result)
        self.placement_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        self.placement_note.show()
        self.undo_move_btn.setVisible(self._undo_placement is not None)
        self.placement_note.setFocus()
        QTimer.singleShot(0, self._ensure_move_controls_visible)
        self._move_feedback_generation += 1
        generation = self._move_feedback_generation
        QTimer.singleShot(6000, lambda: self._clear_move_feedback(generation))

    def _undo_move(self) -> None:
        if self._placement_draft is not None:
            ok, message = self.engine.undo_staged_placement(self._placement_draft)
            if ok:
                plant_id = self._placement_draft.selected_plant_id
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
        starter_incomplete = not bool(
            getattr(self.storage.state, "starter_selection_complete", True)
        )
        dismissed = int(self.config.value("onboarding_version", 0) or 0) >= CURRENT_ONBOARDING_VERSION
        visible = not dismissed
        self.onboarding_panel.setVisible(visible)
        if not visible:
            return
        title = "Choose your first plant" if starter_incomplete else "Find the Nursery"
        message = self._onboarding_save_error or (
            "Your first plant is free. The glowing Nursery building opens your choices."
            if starter_incomplete else
            "The glowing Nursery building is where you collect plants and unlock garden spaces."
        )
        self.onboarding_title.setText(title)
        self.onboarding_message.setText(message)
        self.onboarding_action.setText("Show me")
        self.onboarding_action.setVisible(True)
        self.dismiss_onboarding.setVisible(True)
        self.onboarding_panel.setAccessibleDescription(f"{title}. {message}")

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
        self._complete_onboarding()

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
        planted_count = sum(1 for plant in state.plants if plant.planted)
        available_count = int(self.engine.catalog_summary().get("available_count", 0))
        space_noun = "space" if int(state.unlocked_slots) == 1 else "spaces"
        heading = QLabel(
            f"{_plant_count(len(state.plants))} collected. "
            f"{_plant_count(available_count)} available now. "
            f"{planted_count} of {state.unlocked_slots} {space_noun} occupied."
        )
        heading.setWordWrap(True)
        self._apply_typography(heading, "section-title")
        self.collection_list.add_row(heading)
        for plant in sorted(state.plants, key=lambda item: (item.slot_index is None, item.slot_index or 0, item.name)):
            row = QFrame()
            row.setProperty("progressRow", True)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 8, 10, 8)
            copy = QVBoxLayout()
            title = QLabel(f"{plant.name}\n{format_status_label(plant.species)}")
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            title.setMinimumWidth(0)
            title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            title.setProperty("rowTitle", True)
            location = f"Space {plant.slot_index + 1}" if plant.planted else "In your collection"
            active = "\nBeing nurtured" if state.active_plant_id == plant.plant_id else ""
            details = QLabel(
                f"{format_status_label(plant.growth_stage)} stage, "
                f"{plant.growth_points:,} Growth\n{location}{active}"
            )
            details.setTextFormat(Qt.TextFormat.PlainText)
            details.setWordWrap(True)
            details.setMinimumWidth(0)
            details.setProperty("rowCriteria", True)
            copy.addWidget(title)
            copy.addWidget(details)
            layout.addLayout(copy, 1)
            self.collection_list.add_row(row)
        self.collection_list.finish()

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
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Fertilize {plant.name}")
        dialog.setMinimumSize(450, 330)
        dialog.resize(*_fit_dialog_to_screen(dialog, 520, 430, width_ratio=0.72, height_ratio=0.72))
        dialog.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#091b18; color:#edf5ea; }
            QFrame[fertilizerCard='true'] { background:#102622; border:1px solid #345348; border-radius:10px; }
            QFrame[fertilizerCard='true'][unaffordable='true'] { background:#0d201c; border-color:#2a4339; }
            QLabel[fertilizerMeta='true'] { color:#aac0b1; }
            QLabel[fertilizerBalance='true'] { color:#f1d58a; font-weight:700; }
            QLabel[currentFertilizer='true'] { background:#17342e; border:1px solid #42675a; border-radius:9px; padding:7px 9px; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        title = QLabel(f"Fertilize {plant.name}")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:18px; font-weight:800;")
        subtitle = QLabel("Choose a timed Growth boost for this plant.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("fertilizerMeta", True)
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
            f"Current Fertilizer\n{self._fertilizer_text(plant)}"
            if current_fertilizer is not None else
            "Current Fertilizer\nNone active"
        )
        current_status.setTextFormat(Qt.TextFormat.PlainText)
        current_status.setWordWrap(True)
        current_status.setProperty("currentFertilizer", True)
        current_status.setAccessibleName("Current Fertilizer status")
        current_status.setAccessibleDescription(current_status.text().replace("\n", ". "))
        balance_value = int(self.storage.state.currency_balance)
        balance = QLabel(f"{balance_value:,} Garden Coins available")
        balance.setProperty("fertilizerBalance", True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(current_status)
        layout.addWidget(balance)
        purchase_status = QLabel("")
        purchase_status.setTextFormat(Qt.TextFormat.PlainText)
        purchase_status.setWordWrap(True)
        purchase_status.setAccessibleName("Fertilizer purchase status")
        purchase_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        purchase_status.hide()
        layout.addWidget(purchase_status)
        for tier, spec in self.engine.FERTILIZERS.items():
            hours = spec.duration_seconds // 3600
            duration = f"{hours} hour" if hours == 1 else f"{hours} hours"
            card = QFrame()
            card.setProperty("fertilizerCard", True)
            row = QHBoxLayout(card)
            row.setContentsMargins(11, 9, 11, 9)
            row.setSpacing(10)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            name = QLabel(spec.name)
            name.setStyleSheet("font-weight:700;")
            affordable, affordability = _affordability_status(spec.price, balance_value)
            detail = QLabel(
                f"+{spec.growth_per_answer} Growth per answer for {duration}\n"
                f"{spec.price:,} Garden Coins. {affordability}"
            )
            detail.setProperty("fertilizerMeta", True)
            detail.setWordWrap(True)
            copy.addWidget(name)
            copy.addWidget(detail)
            row.addLayout(copy, 1)
            action_label = _fertilizer_action_label(
                current_tier,
                str(tier),
                spec.name,
            )
            choose = QPushButton(action_label)
            _set_button_variant(
                choose,
                BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
            )
            choose.setAccessibleName(
                f"{action_label} for {spec.price:,} Garden Coins"
            )
            choose.setAccessibleDescription(
                f"{action_label}. {spec.name} adds {spec.growth_per_answer} Growth per answer for {duration}. "
                f"Costs {spec.price:,} Garden Coins. {affordability}"
            )
            choose.setEnabled(affordable)
            if not affordable:
                card.setProperty("unaffordable", True)
                card.setAccessibleName(f"{spec.name} is not affordable yet")
                apply_explanatory_tooltip(
                    card,
                    f"{spec.name} costs {spec.price:,} Garden Coins. {affordability}",
                )
                card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            choose.setMinimumHeight(36)
            choose.clicked.connect(
                lambda _checked=False, selected_tier=tier, target=dialog, status=purchase_status:
                self._purchase_fertilizer_from_dialog(plant_id, selected_tier, target, status)
            )
            row.addWidget(choose)
            layout.addWidget(card)
        cancel = QPushButton("Cancel")
        _set_button_variant(cancel, BUTTON_VARIANT_SECONDARY)
        cancel.clicked.connect(dialog.reject)
        layout.addWidget(cancel, 0, Qt.AlignmentFlag.AlignRight)
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
            self.status_notice.setText(message)
            self.status_notice.setAccessibleDescription(message)
            self.status_notice.setStyleSheet("color:#9ef3b0;")
            self.status_notice.show()
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
