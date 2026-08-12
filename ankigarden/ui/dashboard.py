from __future__ import annotations

import logging
import time
from copy import deepcopy
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import Any

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
    QTimer,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    QColor,
    QSizePolicy,
    QGuiApplication,
    QInputDialog,
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
from ..display_telemetry import DISPLAY_TELEMETRY
from ..environment import (
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
    STREAK_BONUS_TIERS,
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

    label = QLabel()
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
        "seed": 0.46,
        "sprout": 0.58,
        "young": 0.70,
        "mature": 0.82,
        "flowering": 0.86,
        "rare": 0.86,
    }.get(str(stage).lower(), 0.72)
    target = max(24, round(size * stage_fill))
    label.setPixmap(pixmap.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ))
    return label


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
    """A scrollable, content-sized list used by one Garden Progress tab."""

    def __init__(self, accessible_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self.container = QWidget()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAccessibleName(f"{accessible_name} scroll area")
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(5)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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
        self.save_settings = QPushButton("Save changes")
        self.save_settings.setAccessibleName("Save Anki Garden settings")
        _set_button_variant(self.save_settings, BUTTON_VARIANT_PRIMARY)
        self.save_settings.clicked.connect(self._save_visual_settings)
        self.save_settings.setEnabled(False)
        self.restore_defaults = QPushButton("Restore defaults")
        self.restore_defaults.setAccessibleName("Select the default Anki Garden settings")
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
        garden_name_panel = QFrame()
        garden_name_panel.setProperty("settingsSection", True)
        garden_name_layout = QHBoxLayout(garden_name_panel)
        garden_name_copy = QVBoxLayout()
        garden_name_label = QLabel("Garden name")
        garden_name_label.setStyleSheet("font-weight:700;")
        self.garden_name_value = QLabel("")
        self.garden_name_value.setAccessibleName("Current garden name")
        self.garden_name_value.setWordWrap(True)
        garden_name_copy.addWidget(garden_name_label)
        garden_name_copy.addWidget(self.garden_name_value)
        self.rename_garden_btn = QPushButton("Rename garden")
        self.rename_garden_btn.setAccessibleName("Rename garden")
        _set_button_variant(self.rename_garden_btn, BUTTON_VARIANT_SECONDARY)
        self.rename_garden_btn.clicked.connect(self._rename_garden)
        garden_name_layout.addLayout(garden_name_copy, 1)
        garden_name_layout.addWidget(self.rename_garden_btn)
        behavior_layout.addWidget(garden_name_panel)
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
        self._development_backup_path: Path | None = None
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

        tabs.addTab(behavior, "Display")
        tabs.addTab(advanced, UI_TEXT["tab_advanced"])
        self._refresh_garden_name()

    def prepare_to_show(self) -> None:
        self._save_status_generation += 1
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
        self.garden_name_value.setText(name)
        self.garden_name_value.setToolTip(name)

    def _rename_garden(self) -> None:
        current = str(getattr(self.engine.state, "garden_name", "My Garden") or "My Garden")
        name, accepted = QInputDialog.getText(
            self,
            "Rename Garden",
            f"Garden name (up to {MAX_GARDEN_NAME_LENGTH} characters):",
            text=current,
        )
        if not accepted:
            return
        ok, message = self.engine.rename_garden(str(name))
        if not ok:
            QMessageBox.warning(self, "Garden name", message)
            return
        self._refresh_garden_name()
        parent = self.parent()
        refresh_committed = getattr(parent, "_refresh_after_commit", None)
        if callable(refresh_committed):
            refresh_committed("Garden rename")

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
            self.save_status.setText("Defaults selected — save to apply")
            self.save_status.setAccessibleDescription(
                "Default settings are selected but have not been saved."
            )
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
            self._show_save_error("Settings could not be saved. Your previous choices are still active.")
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
        self.artwork.setFixedSize(132, 132)
        self.artwork.setProperty("stagePreview", True)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setAccessibleName("Plant artwork")
        identity_text = QVBoxLayout()
        name_caption = QLabel("Plant name")
        name_caption.setStyleSheet("color:#d8b875; font-size:11px; font-weight:800;")
        identity_text.addWidget(name_caption)
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
        timeline_label = QLabel("Memories")
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
        self.stage_progress = LabeledProgress("Plant progress to the next stage")
        up_next_layout.addWidget(self.stage_progress)
        root.addWidget(self.up_next)
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
            f"Species: {format_status_label(plant.species)}\n"
            f"Stage: {stage}\n"
            f"Growth: {plant.growth_points:,}{active}\n"
            f"Planted {self._local_date(plant.planted_on)}"
        )
        preview = _asset_preview_label(
            self.engine, plant.species, plant.growth_stage, size=132
        )
        self.artwork.setAccessibleName(preview.accessibleName())
        if preview.pixmap() is None or preview.pixmap().isNull():
            self.artwork.setText(format_status_label(plant.species))
            self.artwork.setPixmap(QPixmap())
        else:
            self.artwork.setText("")
            self.artwork.setPixmap(preview.pixmap())
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
            self.stage_progress.set_progress(
                "Rare stage", 1, 1, value_text="Fully grown"
            )
        else:
            next_stage = format_status_label(progress.next_stage or "next stage")
            answers = max(1, (progress.points_remaining + 9) // 10)
            self.up_next_text.setText(
                f"Reach {next_stage} with {progress.points_remaining:,} more Growth "
                f"(about {_card_answer_count(answers)} before bonuses)."
            )
            self.stage_progress.set_progress(
                f"Progress to {next_stage}",
                progress.stage_points,
                max(1, progress.stage_goal),
                value_text=(
                    f"{progress.stage_points:,} of {progress.stage_goal:,} Growth"
                ),
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
        self.setMinimumSize(720, 480)
        self.resize(*_fit_dialog_to_screen(self, 840, 640, width_ratio=0.88, height_ratio=0.84))
        self.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#241813; color:#f5ead7; }
            QFrame[nurseryHero='true'] { background:transparent; border:0; border-bottom:1px solid #604333; border-radius:0; }
            QFrame[nurseryResource='true'] { background:#34231c; border:1px solid #6f503b; border-radius:10px; }
            QFrame[nurseryPlant='true'] { background:#38261f; border:1px solid #71513c; border-radius:12px; }
            QFrame[nurseryPlant='true']:hover { background:#402b22; border-color:#9b7650; }
            QFrame[nurseryPlant='true'][unaffordable='true'] { background:#2b201c; border-color:#574337; }
            QFrame[nurseryGrowing='true'] { background:#35271f; border:1px solid #7d5d43; border-left:3px solid #b88a52; border-radius:10px; }
            QLabel[nurseryEyebrow='true'] { color:#d5ad70; font-size:12px; font-weight:800; letter-spacing:1.2px; }
            QLabel[nurseryTitle='true'] { font-size:30px; font-weight:800; }
            QLabel[nurserySection='true'] { color:#f8e8cf; font-size:19px; font-weight:800; padding:11px 2px 1px 2px; }
            QLabel[nurserySectionNote='true'] { color:#bca991; font-size:13px; padding:0 2px 4px 2px; }
            QLabel[nurseryPlantName='true'] { color:#fff3da; font-size:19px; font-weight:800; }
            QLabel[nurseryMeta='true'] { color:#d6c4ac; font-size:14px; }
            QLabel[nurseryOwnership='true'] { color:#d5ad70; font-size:11px; font-weight:800; letter-spacing:.8px; }
            QLabel[nurseryStageName='true'] { color:#fff3da; font-size:16px; font-weight:800; }
            QLabel[nurseryStageCount='true'] { color:#bca991; font-size:12px; }
            QLabel[nurseryShortfall='true'] { color:#edc783; font-size:12px; }
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
            QTabBar::tab { min-height:32px; padding:4px 10px; color:#cdbba5; background:#2d201a; border:1px solid #5b4232; font-size:13px; font-weight:650; }
            QTabBar::tab:hover { color:#fff3da; background:#3d2a21; border-color:#846044; }
            QTabBar::tab:selected { color:#fff3da; background:#4d3528; border-color:#b88a52; }
            QPushButton[nurseryCarouselNav='true'] { padding:2px 4px; font-size:12px; font-weight:700; }
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
        self.heading = QLabel("Choose your first plant")
        self.heading.setProperty("nurseryTitle", True)
        self.intro = QLabel("Your first plant is free. Choose the one you would like to nurture.")
        self.intro.setWordWrap(True)
        self.intro.setProperty("nurseryMeta", True)
        copy.addWidget(eyebrow)
        copy.addWidget(self.heading)
        copy.addWidget(self.intro)
        hero_layout.addLayout(copy, 1)
        resource = QFrame()
        resource.setProperty("nurseryResource", True)
        resource_layout = QVBoxLayout(resource)
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
        hero_layout.addWidget(resource, 0, Qt.AlignmentFlag.AlignVCenter)
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
        self.catalog_tabs.addTab(self.supplements_scroll, "Boosters")

        self.upgrades_scroll = QScrollArea()
        self.upgrades_scroll.setWidgetResizable(True)
        self.upgrades_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.upgrades_catalog = QWidget()
        self.upgrades_layout = QVBoxLayout(self.upgrades_catalog)
        self.upgrades_layout.setContentsMargins(6, 6, 6, 6)
        self.upgrades_layout.setSpacing(9)
        self.upgrades_scroll.setWidget(self.upgrades_catalog)
        self.catalog_tabs.addTab(self.upgrades_scroll, "Upgrades")

        self.environment_scroll = QScrollArea()
        self.environment_scroll.setWidgetResizable(True)
        self.environment_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.environment_catalog = QWidget()
        self.environment_layout = QVBoxLayout(self.environment_catalog)
        self.environment_layout.setContentsMargins(6, 6, 6, 6)
        self.environment_layout.setSpacing(9)
        self.environment_scroll.setWidget(self.environment_catalog)
        self.catalog_tabs.addTab(self.environment_scroll, "Environment")
        root.addWidget(self.catalog_tabs, 1)

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
        self.bed_affordability = QLabel("")
        self.bed_affordability.setWordWrap(True)
        self.bed_affordability.setProperty("nurseryShortfall", True)
        self.bed_affordability.setAccessibleName("Garden space affordability")
        self.bed_affordability.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
            button.setFixedSize(84, 32)
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
        kicker = QLabel("CURRENTLY GROWING")
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
        action = QPushButton("Shelve")
        _set_button_variant(action, BUTTON_VARIANT_SECONDARY)
        action.setMinimumHeight(36)
        action.setEnabled(False)
        reason = "Finish or switch your active plant first."
        action.setAccessibleName(f"Shelve {plant.name}")
        action.setAccessibleDescription(reason)
        action.setToolTip(reason)
        action.clicked.connect(
            lambda _checked=False, plant_id=plant.plant_id:
            self._set_placement(plant_id, True)
        )
        row.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        card.setAccessibleDescription(
            f"Currently growing {plant.name}. {stage} Stage. {progress_text}. {reason}"
        )
        return card

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
            reason = "Finish or switch your active plant first."
            card.setAccessibleDescription(reason)
            action.setToolTip(reason)
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
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(9)
        identity = QHBoxLayout()
        identity.setSpacing(8)
        species_name = format_status_label(species)
        title = QLabel(species_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setProperty("nurseryPlantName", True)
        ownership = QLabel("NOT COLLECTED")
        ownership.setProperty("nurseryOwnership", True)
        identity.addWidget(title, 1)
        identity.addWidget(ownership, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(identity)
        card_layout.addWidget(
            self._plant_stage_carousel(species),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        price = int(self.engine.SPECIES_PRICES.get(species, 0))
        balance = int(self.storage.state.currency_balance)
        affordable, affordability = _affordability_status(price, balance)
        if starter_mode:
            affordable = True
            affordability = "Included with your free starter."
        price_text = "Free" if starter_mode else f"{price:,} Garden Coins"
        visible_terms = (
            "Free starter"
            if starter_mode else
            price_text
        )
        meta = QLabel(visible_terms)
        meta.setProperty("nurseryMeta", True)
        meta.setWordWrap(True)
        affordability_label = QLabel(
            "Included with your free starter"
            if starter_mode else
            _compact_affordability_status(price, balance, ready_text="Ready to unlock")
        )
        affordability_label.setProperty("nurseryShortfall", True)
        affordability_label.setWordWrap(True)
        action = QPushButton("Choose" if starter_mode else "Unlock")
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if starter_mode else BUTTON_VARIANT_SECONDARY,
        )
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
        action.setMinimumHeight(36)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        price_stack = QVBoxLayout()
        price_stack.setSpacing(0)
        price_stack.addWidget(meta)
        price_stack.addWidget(affordability_label)
        footer.addLayout(price_stack, 1)
        footer.addWidget(action, 0, Qt.AlignmentFlag.AlignBottom)
        card_layout.addLayout(footer)
        return card

    def _item_artwork(self, key: str, accessible_name: str, size: int = 96) -> QLabel:
        label = QLabel()
        label.setFixedSize(size, size)
        label.setProperty("nurseryArtwork", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleName(accessible_name)
        path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "v6_storybook_gouache"
            / "ui"
            / f"{key}.png"
        )
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
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
            f"fertilizer_{tier}", f"{spec.name} bag preview"
        ))
        copy = QVBoxLayout()
        title = QLabel(spec.name)
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        duration_hours = max(1, spec.duration_seconds // 3600)
        meta = QLabel(
            f"+{spec.growth_per_answer} Growth per answer for {duration_hours} "
            f"{'hour' if duration_hours == 1 else 'hours'}\n"
            f"{spec.price:,} Garden Coins"
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        active = self.engine.active_plant()
        affordable = self.storage.state.currency_balance >= spec.price
        action = QPushButton("Use on nurtured plant")
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
            "booster_potion", "Booster Potion preview"
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
            spec.charge_id, f"{spec.name} preview"
        ))
        copy = QVBoxLayout()
        title = QLabel(f"{spec.name} — {count} owned")
        title.setStyleSheet("font-weight:700;")
        meta = QLabel(
            f"Adds up to {spec.growth:,} Growth to the nurtured plant, capped at Rare.\n"
            + (
                f"{spec.price:,} Garden Coins each."
                if spec.price is not None
                else "Earn-only; never sold."
            )
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        actions = QVBoxLayout()
        if spec.price is not None:
            buy = QPushButton("Buy one")
            affordable = self.storage.state.currency_balance >= spec.price
            _set_button_variant(
                buy,
                BUTTON_VARIANT_PRIMARY if affordable else BUTTON_VARIANT_SECONDARY,
            )
            buy.setEnabled(affordable)
            buy.setAccessibleDescription(
                f"Buy one {spec.name} for {spec.price:,} Garden Coins."
                if affordable else
                f"Need {spec.price - self.storage.state.currency_balance:,} more Garden Coins."
            )
            buy.clicked.connect(
                lambda _checked=False, charge_id=spec.charge_id:
                self._purchase_growth_charge(charge_id)
            )
            actions.addWidget(buy)
        active = self.engine.active_plant()
        use = QPushButton("Use on nurtured plant")
        _set_button_variant(
            use,
            BUTTON_VARIANT_PRIMARY if count > 0 and active is not None else BUTTON_VARIANT_SECONDARY,
        )
        use.setEnabled(count > 0 and active is not None)
        use.setAccessibleDescription(
            f"Use one {spec.name} on {active.name}."
            if count > 0 and active is not None else
            "Own this charge and nurture an unfinished planted plant first."
        )
        use.clicked.connect(
            lambda _checked=False, charge_id=spec.charge_id:
            self._use_growth_charge(charge_id)
        )
        actions.addWidget(use)
        row.addLayout(actions)
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
        resolver_name = (
            "resolve_weather_preview_asset"
            if item.kind == "weather"
            else "resolve_scenery_preview_asset"
        )
        resolver = getattr(self.engine, resolver_name, None)
        try:
            asset = resolver(item.item_id) if callable(resolver) else None
        except Exception:
            asset = None
        path = getattr(asset, "path", None)
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            label.setText(item.name)
            label.setWordWrap(True)
        else:
            label.setPixmap(pixmap.scaled(
                width - 10,
                height - 10,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        return label

    def _environment_shop_card(self, item: CatalogItem) -> QFrame:
        owned = self.engine.owns_environment(item.kind, item.item_id)
        card = QFrame()
        card.setProperty("nurseryPlant", True)
        row = QHBoxLayout(card)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(10)
        row.addWidget(self._environment_artwork(item))
        copy = QVBoxLayout()
        title = QLabel(f"{item.name} — {item.rarity}")
        title.setStyleSheet("font-weight:700;")
        title.setWordWrap(True)
        meta = QLabel(
            f"{item.effect}\n"
            + (
                f"One-time price: {item.price:,} Garden Coins."
                if item.price is not None else
                "Included with every garden."
            )
        )
        meta.setWordWrap(True)
        meta.setProperty("nurseryMeta", True)
        copy.addWidget(title)
        copy.addWidget(meta)
        row.addLayout(copy, 1)
        action = QPushButton(
            "Owned — equip in House" if owned else f"Buy for {item.price:,} Coins"
        )
        affordable = bool(
            item.price is not None
            and self.storage.state.currency_balance >= item.price
        )
        action.setEnabled(not owned and affordable)
        _set_button_variant(
            action,
            BUTTON_VARIANT_PRIMARY if not owned and affordable else BUTTON_VARIANT_SECONDARY,
        )
        action.setAccessibleDescription(
            f"{item.name} is owned. Equip it in House, Weather & Scenery."
            if owned else
            f"Buy {item.name} once for {item.price:,} Garden Coins."
            if affordable else
            f"Need {int(item.price or 0) - self.storage.state.currency_balance:,} more Garden Coins."
        )
        action.clicked.connect(
            lambda _checked=False, kind=item.kind, item_id=item.item_id:
            self._purchase_environment(kind, item_id)
        )
        row.addWidget(action)
        return card

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

    def refresh(self) -> None:
        self._clear_catalog()
        self._clear_section(self.supplements_layout)
        self._clear_section(self.upgrades_layout)
        self._clear_section(self.environment_layout)
        state = self.storage.state
        starter_mode = not bool(getattr(state, "starter_selection_complete", True))
        self.catalog_tabs.setTabEnabled(1, not starter_mode)
        self.catalog_tabs.setTabEnabled(2, not starter_mode)
        self.catalog_tabs.setTabEnabled(3, not starter_mode)
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
        self.heading.setText("Choose your first plant" if starter_mode else "Build your collection")
        intro_text = (
            f"{catalog_summary} — your first plant is free"
            if starter_mode else
            catalog_summary
        )
        self.intro.setText(intro_text)
        self.intro.setAccessibleDescription(intro_text)
        active = self.engine.active_plant()
        if active is not None:
            self.catalog_layout.addWidget(self._currently_growing_strip(active))
        collection_plants = [
            plant for plant in state.plants
            if active is None or plant.plant_id != active.plant_id
        ]
        if collection_plants:
            self._section_label(
                "Your collection",
                "Collected plants stay with you and can be returned to the garden whenever space is available.",
            )
            for plant in sorted(collection_plants, key=lambda item: (item.slot_index is None, item.name.lower())):
                self.catalog_layout.addWidget(self._owned_card(plant))
        self._section_label(
            "Botanical catalog",
            "Preview every growth stage before adding a new species to your collection.",
        )
        if available:
            available_grid_host = QWidget()
            available_grid = QGridLayout(available_grid_host)
            available_grid.setContentsMargins(0, 0, 0, 0)
            available_grid.setHorizontalSpacing(9)
            available_grid.setVerticalSpacing(9)
            for index, species in enumerate(available):
                available_grid.addWidget(
                    self._available_card(species, starter_mode),
                    index // 2,
                    index % 2,
                )
            available_grid.setColumnStretch(0, 1)
            available_grid.setColumnStretch(1, 1)
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
            supplement_intro = QLabel(
                "Fertilizer is applied immediately. Booster Potions and Growth Charges "
                "stay in your collection until you use them."
            )
            supplement_intro.setWordWrap(True)
            supplement_intro.setProperty("nurseryMeta", True)
            self.supplements_layout.addWidget(supplement_intro)
            for tier in ("basic", "quality", "premium"):
                self.supplements_layout.addWidget(self._supplement_card(tier))
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
            for index in range(6):
                self.upgrades_layout.addWidget(self._space_card(index))
            self.upgrades_layout.addStretch(1)

            environment_intro = QLabel(
                "Buy each shop item once. Purchases unlock the full artwork and passive, "
                "but never equip automatically. Drop-only discoveries and all loadout "
                "controls live in House → Weather & Scenery."
            )
            environment_intro.setWordWrap(True)
            environment_intro.setProperty("nurseryMeta", True)
            self.environment_layout.addWidget(environment_intro)
            for heading, catalog in (
                ("Weather", WEATHER_CATALOG),
                ("Scenery", SCENERY_CATALOG),
            ):
                label = QLabel(heading)
                label.setProperty("nurserySection", True)
                self.environment_layout.addWidget(label)
                for item in catalog.values():
                    if item.acquisition in {"free", "purchase"}:
                        self.environment_layout.addWidget(
                            self._environment_shop_card(item)
                        )
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("plantCard", True)
        self.setAccessibleName("Selected plant details")
        self.plant_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        self.heading = QLabel("")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setProperty("plantCardHeading", True)
        self.heading.setWordWrap(True)
        self.identity = QLabel("")
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.identity.setProperty("plantStageBadge", True)
        self.identity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.identity.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.growth_section = QLabel("GROWTH")
        self.growth_section.setProperty("plantCardSection", True)
        self.stage_progress = LabeledProgress("Selected plant growth")
        self.stage_progress.label.setProperty("plantProgressLabel", True)
        self.stage_progress.value_label.setProperty("plantGrowthValue", True)
        self.growth_summary = QLabel("")
        self.fertilizer_summary = QLabel("")
        for label in (self.growth_summary, self.fertilizer_summary):
            label.setWordWrap(True)
            label.setProperty("actionMeta", True)
        self.fertilizer_summary.hide()
        self.status_row = QFrame()
        self.status_row.setProperty("plantStatus", True)
        status_layout = QHBoxLayout(self.status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        status_label = QLabel("STATUS")
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
        layout.addWidget(self.heading)
        layout.addWidget(self.identity)
        layout.addWidget(self.growth_section)
        layout.addWidget(self.stage_progress)
        layout.addWidget(self.growth_summary)
        layout.addWidget(self.status_row)
        layout.addWidget(self.action_hint)

        self.nurture = QPushButton("Nurture")
        self.fertilize = QPushButton("Fertilize")
        self.move = QPushButton("Move")
        self.story = QPushButton("Story")
        _set_button_variant(self.fertilize, BUTTON_VARIANT_PRIMARY)
        for button in (self.nurture, self.move, self.story):
            _set_button_variant(button, BUTTON_VARIANT_SECONDARY)
        apply_explanatory_tooltip(self.nurture, ACTIVE_PLANT_EXPLANATION)
        apply_explanatory_tooltip(self.fertilize, FERTILIZER_EXPLANATION)
        apply_explanatory_tooltip(self.move, "Move this plant to another highlighted garden space.")
        apply_explanatory_tooltip(self.story, "View this plant’s name, age, and growth history.")
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        actions.addWidget(self.nurture, 0, 0, 1, 2)
        actions.addWidget(self.fertilize, 1, 0, 1, 2)
        actions.addWidget(self.story, 2, 0)
        actions.addWidget(self.move, 2, 1)
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
        stage = format_status_label(plant.get("stage") or "seed")
        self.heading.setText(name)
        self.identity.setText(f"{stage} Stage")
        growth_points = max(0, int(plant.get("growth_points", 0) or 0))
        if bool(plant.get("fully_grown")):
            self.stage_progress.set_progress("Final stage", 1, 1, value_text="Rare stage, fully grown")
            self.growth_summary.setText(f"{growth_points:,} total Growth")
        else:
            stage_points = max(0, int(plant.get("stage_points", 0) or 0))
            stage_goal = max(1, int(plant.get("stage_goal", 1) or 1))
            self.stage_progress.set_progress("Next stage", stage_points, stage_goal)
            remaining = max(0, int(plant.get("points_remaining", 0) or 0))
            reviews_remaining = max(0, int(plant.get("reviews_remaining", 0) or 0))
            self.growth_summary.setText(f"{remaining:,} Growth remaining")
            self.growth_summary.setAccessibleDescription(
                f"{remaining:,} Growth remaining. "
                f"About {_card_answer_count(reviews_remaining)} before bonuses."
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
        self.nurture.setVisible(not active and not fully_grown)
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
        self.status_value.setText(
            "Fully grown" if fully_grown else "Being nurtured" if active else "Not nurtured"
        )
        self.action_hint.setText(action_hint)
        self.action_hint.setAccessibleDescription(action_hint)
        self.nurture.setAccessibleDescription(f"{ACTIVE_PLANT_EXPLANATION} {nurture_reason}")
        self.fertilize.setAccessibleDescription(f"{FERTILIZER_EXPLANATION} {fertilizer_reason}")
        self.show()


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
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.cells: dict[str, QPushButton] = {}
        self.values: dict[str, QLabel] = {}
        self.progress: dict[str, QProgressBar] = {}
        self.metric_copy: dict[str, tuple[str, str]] = {}
        for key, title, description in self.METRICS:
            cell = QPushButton()
            cell.setProperty("gardenStatCell", True)
            cell.setProperty("metric", key)
            cell.setAccessibleName(title)
            cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setMinimumHeight(132)
            cell.clicked.connect(
                lambda _checked=False, metric=key: self.metricActivated.emit(metric)
            )
            apply_explanatory_tooltip(cell, description)
            self.cells[key] = cell
            self.metric_copy[key] = (title, description)

        growth_layout = QVBoxLayout(self.cells["growth"])
        growth_layout.setContentsMargins(14, 10, 14, 11)
        growth_layout.setSpacing(4)
        growth_kicker = QLabel("PLANT GROWTH")
        growth_kicker.setProperty("gardenStatLabel", True)
        growth_identity = QHBoxLayout()
        growth_identity.setSpacing(8)
        self.growth_name = QLabel("Choose a plant")
        self.growth_name.setProperty("gardenPlantName", True)
        self.growth_name.setWordWrap(True)
        self.growth_stage = QLabel("")
        self.growth_stage.setProperty("gardenStageBadge", True)
        self.growth_stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.growth_stage.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        growth_identity.addWidget(self.growth_name, 1)
        growth_identity.addWidget(self.growth_stage, 0)
        growth_value_row = QHBoxLayout()
        growth_value_row.setSpacing(8)
        growth_label = QLabel("GROWTH")
        growth_label.setProperty("gardenStatLabel", True)
        self.growth_value = QLabel("0 / 0")
        self.growth_value.setProperty("gardenGrowthValue", True)
        growth_value_row.addWidget(growth_label)
        growth_value_row.addStretch(1)
        growth_value_row.addWidget(self.growth_value)
        growth_bar = QProgressBar()
        growth_bar.setRange(0, 1000)
        growth_bar.setValue(0)
        growth_bar.setTextVisible(False)
        growth_bar.setFixedHeight(8)
        growth_bar.setAccessibleName("Nurtured plant Growth")
        growth_bar.setProperty("metricProgress", True)
        self.growth_support = QLabel("Choose an unfinished plant to begin earning Growth")
        self.growth_support.setProperty("gardenStatSupport", True)
        self.growth_support.setWordWrap(True)
        growth_layout.addWidget(growth_kicker)
        growth_layout.addLayout(growth_identity)
        growth_layout.addLayout(growth_value_row)
        growth_layout.addWidget(growth_bar)
        growth_layout.addWidget(self.growth_support)
        growth_layout.addStretch(1)
        growth_affordance = QLabel("View details ›")
        growth_affordance.setProperty("gardenDetailsAffordance", True)
        growth_affordance.setAlignment(Qt.AlignmentFlag.AlignRight)
        growth_layout.addWidget(growth_affordance)

        streak_layout = QVBoxLayout(self.cells["streak"])
        streak_layout.setContentsMargins(13, 10, 13, 11)
        streak_layout.setSpacing(5)
        streak_heading = QHBoxLayout()
        streak_heading.setSpacing(6)
        streak_label = QLabel("ANKI STREAK")
        streak_label.setProperty("gardenStatLabel", True)
        self.streak_bonus = QLabel("")
        self.streak_bonus.setProperty("gardenBonusBadge", True)
        self.streak_bonus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.streak_bonus.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        streak_heading.addWidget(streak_label)
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
        self.streak_support.setWordWrap(True)
        streak_layout.addLayout(streak_heading)
        streak_layout.addLayout(streak_value_row)
        streak_layout.addWidget(self.streak_support)
        streak_layout.addStretch(1)
        streak_affordance = QLabel("View details ›")
        streak_affordance.setProperty("gardenDetailsAffordance", True)
        streak_affordance.setAlignment(Qt.AlignmentFlag.AlignRight)
        streak_layout.addWidget(streak_affordance)

        currency_layout = QVBoxLayout(self.cells["currency"])
        currency_layout.setContentsMargins(13, 10, 13, 11)
        currency_layout.setSpacing(5)
        currency_label = QLabel("GARDEN COINS")
        currency_label.setProperty("gardenStatLabel", True)
        self.currency_value = QLabel("0")
        self.currency_value.setProperty("gardenLargeValue", True)
        self.currency_support = QLabel("Spend in the Nursery")
        self.currency_support.setProperty("gardenStatSupport", True)
        self.currency_support.setWordWrap(True)
        currency_layout.addWidget(currency_label)
        currency_layout.addWidget(self.currency_value)
        currency_layout.addWidget(self.currency_support)
        currency_layout.addStretch(1)
        currency_affordance = QLabel("View details ›")
        currency_affordance.setProperty("gardenDetailsAffordance", True)
        currency_affordance.setAlignment(Qt.AlignmentFlag.AlignRight)
        currency_layout.addWidget(currency_affordance)

        self.values = {
            "growth": self.growth_value,
            "streak": self.streak_number,
            "currency": self.currency_value,
        }
        self.progress = {"growth": growth_bar}
        # Every visible child belongs to one semantic, clickable metric card.
        for cell in self.cells.values():
            for child in cell.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        for key, _title, _description in self.METRICS:
            self.grid.removeWidget(self.cells[key])
        if compact:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 2)
            self.grid.addWidget(self.cells["streak"], 1, 0)
            self.grid.addWidget(self.cells["currency"], 1, 1)
            stretches = (1, 1, 0, 0)
        else:
            self.grid.addWidget(self.cells["growth"], 0, 0, 1, 2)
            self.grid.addWidget(self.cells["streak"], 0, 2)
            self.grid.addWidget(self.cells["currency"], 0, 3)
            stretches = (1, 1, 1, 1)
        for column, stretch in enumerate(stretches):
            self.grid.setColumnStretch(column, stretch)

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
                        f"Open {title} details. {value}. {explanation}"
                    )

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
            self.growth_value.setText("—")
            self.growth_support.setText("Choose an unfinished plant to begin earning Growth")
        else:
            self.growth_value.setText(
                "Complete" if fully_grown else f"{max(0, int(total_growth)):,} Growth"
            )
            self.growth_support.setText(
                "Rare Stage — Fully grown"
                if fully_grown else
                f"{max(0, int(remaining)):,} to {next_stage or 'the next stage'}"
            )
        self.set_progress(
            "growth", safe_current, safe_maximum, accessible_text=accessible_text
        )
        self.cells["growth"].setAccessibleDescription(
            f"Open Plant Growth details. {accessible_text} {GROWTH_EXPLANATION}"
        )

    def set_streak_details(
        self,
        *,
        days: int,
        bonus_percent: int,
        support: str,
    ) -> None:
        safe_days = max(0, int(days))
        self.streak_number.setText(f"{safe_days:,}")
        self.streak_unit.setText("day" if safe_days == 1 else "days")
        self.streak_bonus.setText(f"+{max(0, int(bonus_percent))}% Growth")
        self.streak_support.setText(str(support))
        title, explanation = self.metric_copy["streak"]
        self.cells["streak"].setAccessibleDescription(
            f"Open {title} details. {safe_days:,} days; +{max(0, int(bonus_percent))}% Growth. "
            f"{support}. {explanation}"
        )

    def set_currency_details(self, balance: int) -> None:
        safe_balance = max(0, int(balance))
        self.currency_value.setText(f"{safe_balance:,}")
        title, explanation = self.metric_copy["currency"]
        self.cells["currency"].setAccessibleDescription(
            f"Open {title} details. {safe_balance:,} Garden Coins. {explanation}"
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


class GardenProgressDialog(QDialog):
    """Modeless home for the dashboard's long-form progress views."""

    def __init__(self, parent: QWidget, tabs: QTabWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Garden Progress")
        self.setModal(False)
        self.setMinimumSize(520, 420)
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("Garden Progress")
        title.setStyleSheet("font-size:20px; font-weight:800;")
        intro = QLabel(
            "See what your studying has earned, what advances each system, "
            "and what comes next."
        )
        intro.setWordWrap(True)
        intro.setProperty("actionMeta", True)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(tabs, 1)
        close = QPushButton("Close")
        _set_button_variant(close, BUTTON_VARIANT_SECONDARY)
        close.clicked.connect(self.close)
        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(close)
        layout.addLayout(controls)


class GardenDetailsDialog(QDialog):
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
        super().__init__(parent)
        self.engine = engine
        self.storage = storage
        self.open_nursery = open_nursery
        self._show_all_transactions = False
        self.setWindowTitle("Garden Details")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(680, 500)
        self.setMaximumWidth(780)
        screen = parent.screen() if hasattr(parent, "screen") else None
        maximum_height = max(
            500,
            int(screen.availableGeometry().height()) - 96 if screen is not None else 620,
        )
        self.setMaximumHeight(maximum_height)
        self.resize(740, min(570, maximum_height))
        self.setStyleSheet(_button_stylesheet() + """
            QDialog { background:#0a1715; color:#edf5ea; }
            QWidget[detailBodyPanel='true'] { background:#0d211e; }
            QLabel[detailTitle='true'] { color:#f5f7e8; font-size:20px; font-weight:800; }
            QLabel[detailSection='true'] { color:#f3f6e9; font-size:14px; font-weight:750; }
            QLabel[detailBody='true'] { color:#c5d3c9; font-size:14px; }
            QLabel[detailSupport='true'] { color:#a9bdb0; font-size:13px; }
            QLabel[detailMetric='true'] { color:#f5f7e8; font-size:31px; font-weight:800; }
            QLabel[detailGoldMetric='true'] { color:#f0ca78; font-size:32px; font-weight:800; }
            QLabel[detailBadge='true'] { color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:800; }
            QLabel[detailStatus='true'] { color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 8px; font-size:12px; font-weight:700; }
            QLabel[detailTableHeader='true'] { color:#91aa9b; font-size:11px; font-weight:800; }
            QLabel[detailPositive='true'] { color:#8ee0a8; font-size:13px; font-weight:700; }
            QLabel[detailNegative='true'] { color:#f0b4a9; font-size:13px; font-weight:700; }
            QLabel[detailCoinIcon='true'] { color:#352514; background:#e1b85e; border:2px solid #f3d58f; border-radius:25px; font-size:20px; font-weight:900; }
            QFrame[detailHero='true'] { background:#17342e; border:1px solid #557665; border-radius:12px; }
            QFrame[detailCard='true'] { background:#102622; border:1px solid #345348; border-radius:11px; }
            QFrame[detailRow='true'] { border:0; border-bottom:1px solid #29463c; }
            QFrame[detailStage='true'] { background:#102622; border:1px solid #345348; border-radius:10px; }
            QFrame[detailStage='true'][detailStageState='completed'] { background:#132820; border-color:#456b57; }
            QFrame[detailStage='true'][detailStageState='current'] { background:#1a382f; border:2px solid #d1ad69; }
            QFrame[detailStage='true'][detailStageState='upcoming'] { background:#0d1e1b; border-color:#2b4239; }
            QProgressBar { border:0; border-radius:4px; background:#203d35; min-height:8px; max-height:8px; }
            QProgressBar::chunk { border-radius:4px; background:#65c487; }
            QTabWidget::pane { border:1px solid #345348; border-radius:12px; background:#0d211e; top:-1px; }
            QTabBar::tab { min-height:32px; padding:4px 14px; color:#aac0b1; background:#0d211e; border:1px solid #2c493e; font-size:13px; font-weight:700; }
            QTabBar::tab:hover { color:#f4f3df; background:#17342e; border-color:#557665; }
            QTabBar::tab:selected { color:#f4f3df; background:#244c3d; border-color:#78947c; }
            QTabBar::tab:focus { border:2px solid #e5f2a6; }
            QScrollArea { background:transparent; border:0; }
            QPushButton[detailDisclosure='true'] { text-align:left; min-height:26px; background:transparent; border:1px solid #345348; color:#c8d8cd; }
            QPushButton[detailDisclosure='true']:hover { background:#17342e; border-color:#78947c; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        title = QLabel("Garden Details")
        title.setProperty("detailTitle", True)
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setAccessibleName("Garden detail sections")
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.body_layouts: dict[str, QVBoxLayout] = {}
        for key, label in self.METRIC_TABS:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setAccessibleName(f"{label} details")
            body = QWidget()
            body.setProperty("detailBodyPanel", True)
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(18, 18, 18, 18)
            body_layout.setSpacing(18)
            scroll.setWidget(body)
            self.tabs.addTab(scroll, label)
            self.body_layouts[key] = body_layout
        self.tabs.currentChanged.connect(self._sync_context_action)
        root.addWidget(self.tabs, 1)

        self.context_row = QWidget()
        context_layout = QHBoxLayout(self.context_row)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.addStretch(1)
        self.nursery = QPushButton("Open Nursery")
        self.nursery.setMinimumHeight(40)
        _set_button_variant(self.nursery, BUTTON_VARIANT_PRIMARY)
        self.nursery.clicked.connect(self._open_nursery)
        context_layout.addWidget(self.nursery)
        root.addWidget(self.context_row)
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
        self.context_row.setVisible(self.tabs.currentIndex() == 2)

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
    ) -> None:
        button = QPushButton(f"View {title.lower()}")
        button.setCheckable(True)
        button.setProperty("detailDisclosure", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleDescription(f"Expand or collapse {title.lower()}")
        panel = QFrame()
        panel.setProperty("detailCard", True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 8, 12, 8)
        panel_layout.setSpacing(0)
        for label, value in rows:
            self._value_row(panel_layout, label, value)
        panel.hide()

        def sync(checked: bool) -> None:
            panel.setVisible(checked)
            button.setText(
                f"Hide {title.lower()}" if checked else f"View {title.lower()}"
            )

        button.toggled.connect(sync)
        layout.addWidget(button)
        layout.addWidget(panel)

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
            empty_layout.addWidget(self._label("No active plant", "detailSection"))
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
            self.engine, plant.species, plant.growth_stage, size=72
        ), 0, Qt.AlignmentFlag.AlignTop)
        identity = QVBoxLayout()
        identity.setSpacing(5)
        kicker = self._label("ACTIVE PLANT", "detailSupport")
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name = self._label(plant.name, "detailSection")
        name.setStyleSheet("font-size:20px; font-weight:800;")
        stage = self._label(format_status_label(display.stage), "detailBadge")
        stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stage.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        name_row.addWidget(name, 1)
        name_row.addWidget(stage)
        total = self._label(f"{plant.growth_points:,} total Growth", "detailBody")
        identity.addWidget(kicker)
        identity.addLayout(name_row)
        identity.addWidget(total)
        progress = LabeledProgress("Active plant Growth to the next stage")
        if display.fully_grown:
            progress.set_progress("Rare Stage", 1, 1, value_text="Fully grown")
        else:
            next_stage = format_status_label(display.next_stage or "next stage")
            progress.set_progress(
                f"{display.stage_points:,} / {display.stage_goal:,} Growth",
                display.stage_points,
                max(1, display.stage_goal),
                value_text=f"{display.points_remaining:,} to {next_stage}",
            )
        identity.addWidget(progress)
        hero_layout.addLayout(identity, 1)
        layout.addWidget(hero)

        stats = self.storage.state.daily_stats
        today = QFrame()
        today.setProperty("detailCard", True)
        today_layout = QVBoxLayout(today)
        today_layout.setContentsMargins(14, 12, 14, 12)
        today_layout.setSpacing(2)
        today_heading = QHBoxLayout()
        today_heading.addWidget(self._label("Today", "detailSection"), 1)
        total_label = self._label(f"+{stats.growth_earned:,} Growth", "detailSection")
        total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        today_heading.addWidget(total_label)
        today_layout.addLayout(today_heading)
        contributions = [
            ("Base", int(stats.base_growth)),
            ("Anki Streak", int(stats.streak_bonus_growth)),
            ("Fertilizer", int(stats.fertilizer_growth)),
            ("Booster", int(getattr(stats, "booster_growth", 0))),
            ("Weather", int(getattr(stats, "weather_growth", 0))),
            ("Scenery", int(getattr(stats, "scenery_growth", 0))),
            ("Growth Charges", int(getattr(stats, "charge_growth", 0))),
        ]
        recorded = sum(value for _label, value in contributions)
        if recorded != int(stats.growth_earned):
            contributions.append(("Other recorded Growth", int(stats.growth_earned) - recorded))
        active_rows = [(label, value) for label, value in contributions if value != 0]
        inactive_rows = [(label, value) for label, value in contributions if value == 0]
        if active_rows:
            for label, value in active_rows:
                prefix = "" if label == "Base" else "+" if value > 0 else ""
                self._value_row(today_layout, label, f"{prefix}{value:,}")
        else:
            today_layout.addWidget(self._label("No Growth recorded today.", "detailSupport"))
        self._value_row(today_layout, "Total", f"{stats.growth_earned:,}", total=True)
        if inactive_rows:
            self._disclosure(
                today_layout,
                "inactive modifiers",
                [(label, "0") for label, _value in inactive_rows],
            )
        today.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        apply_explanatory_tooltip(today, GROWTH_EXPLANATION)
        layout.addWidget(today)

        self._section_label(layout, "Growth stages")
        stage_scroll = QScrollArea()
        stage_scroll.setFrameShape(QFrame.Shape.NoFrame)
        stage_scroll.setWidgetResizable(False)
        stage_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        stage_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stage_scroll.setMinimumHeight(178)
        stage_host = QWidget()
        stage_host.setMinimumWidth(654)
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
            stage_card.setMinimumWidth(102)
            stage_layout = QVBoxLayout(stage_card)
            stage_layout.setContentsMargins(7, 7, 7, 7)
            stage_layout.setSpacing(3)
            stage_layout.addWidget(_asset_preview_label(
                self.engine, plant.species, stage_key, size=64
            ), 0, Qt.AlignmentFlag.AlignHCenter)
            stage_name = self._label(format_status_label(stage_key), "detailSection")
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            threshold = self._label(
                f"{GROWTH_THRESHOLDS[index]:,} Growth", "detailSupport"
            )
            threshold.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status = self._label(
                "Completed" if state == "completed" else
                "Current" if state == "current" else
                "Upcoming",
                "detailSupport",
            )
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(stage_name)
            stage_layout.addWidget(threshold)
            stage_layout.addWidget(status)
            stage_card.setAccessibleName(
                f"{format_status_label(stage_key)} stage. {GROWTH_THRESHOLDS[index]:,} Growth. {status.text()}."
            )
            stages.addWidget(stage_card)
        stage_scroll.setWidget(stage_host)
        layout.addWidget(stage_scroll)

    def _streak_reward_text(self, day: int, percent: int) -> str:
        if day == 1 and percent == 0:
            return "Streak activated"
        parts = [f"+{percent}% Growth"]
        coins = int(self.engine.STREAK_CURRENCY.get(day, 0) or 0)
        if coins:
            parts.append(_garden_coin_count(coins))
        return ", ".join(parts)

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
            "Streak reset" if days == 0 else
            "Maintained today" if maintained_today else
            "Not yet maintained today"
        )
        cutoff_text = ""
        try:
            cutoff_ms = int(self.storage.current_day_end_ms())
            if cutoff_ms > 0:
                cutoff = datetime.fromtimestamp(cutoff_ms / 1000)
                cutoff_time = cutoff.strftime("%I:%M %p").lstrip("0")
                cutoff_text = f"Anki day rolls over at {cutoff_time}"
        except (AttributeError, OSError, TypeError, ValueError):
            cutoff_text = ""

        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 15, 18, 15)
        hero_layout.setSpacing(5)
        status_row = QHBoxLayout()
        metric = self._label(_day_count(days), "detailMetric")
        status = self._label(status_text, "detailStatus")
        status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(metric, 1)
        status_row.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(status_row)
        hero_layout.addWidget(self._label("Current Anki Streak", "detailBody"))
        hero_layout.addWidget(self._label(
            f"Current Growth bonus: +{bonus}%", "detailSection"
        ))
        if cutoff_text:
            hero_layout.addWidget(self._label(cutoff_text, "detailSupport"))
        layout.addWidget(hero)

        next_tier = next(
            ((day, percent) for day, percent in STREAK_BONUS_TIERS if days < day),
            None,
        )
        progress_card = QFrame()
        progress_card.setProperty("detailCard", True)
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(14, 12, 14, 12)
        progress_layout.setSpacing(7)
        if next_tier is None:
            progress_layout.addWidget(self._label(
                "All Growth bonus milestones completed", "detailSection"
            ))
            progress_layout.addWidget(self._label(
                f"+{bonus}% Growth bonus active. Your streak can continue as a personal record.",
                "detailBody",
            ))
        else:
            next_day, next_percent = next_tier
            progress_layout.addWidget(self._label(
                f"{days:,} / {next_day:,} days", "detailSection"
            ))
            progress_layout.addWidget(self._label(
                f"{next_day - days:,} {'day' if next_day - days == 1 else 'days'} to the next milestone",
                "detailSupport",
            ))
            progress_layout.addWidget(self._label(
                f"Reward: {self._streak_reward_text(next_day, next_percent)}",
                "detailBody",
            ))
            progress = QProgressBar()
            progress.setRange(0, max(1, next_day))
            progress.setValue(min(days, next_day))
            progress.setTextVisible(False)
            progress.setAccessibleName("Progress to the next Anki streak milestone")
            progress.setAccessibleDescription(f"{days:,} of {next_day:,} days")
            progress_layout.addWidget(progress)
        layout.addWidget(progress_card)

        self._section_label(layout, "Milestones")
        milestone_card = QFrame()
        milestone_card.setProperty("detailCard", True)
        milestone_grid = QGridLayout(milestone_card)
        milestone_grid.setContentsMargins(14, 11, 14, 11)
        milestone_grid.setHorizontalSpacing(14)
        milestone_grid.setVerticalSpacing(8)
        for column, heading in enumerate(("Milestone", "Reward", "Status")):
            header = self._label(heading.upper(), "detailTableHeader")
            if column == 2:
                header.setAlignment(Qt.AlignmentFlag.AlignRight)
            milestone_grid.addWidget(header, 0, column)
        next_day = next_tier[0] if next_tier is not None else None
        for row, (day, percent) in enumerate(STREAK_BONUS_TIERS, start=1):
            reached = days >= day
            status_text = "Reached" if reached else "Next" if day == next_day else "Upcoming"
            milestone = self._label(_day_count(day), "detailBody")
            reward = self._label(self._streak_reward_text(day, percent), "detailBody")
            status = self._label(status_text, "detailSupport")
            status.setAlignment(Qt.AlignmentFlag.AlignRight)
            milestone_grid.addWidget(milestone, row, 0)
            milestone_grid.addWidget(reward, row, 1)
            milestone_grid.addWidget(status, row, 2)
        milestone_grid.setColumnStretch(1, 1)
        layout.addWidget(milestone_card)
        self._disclosure(
            layout,
            "how the streak works",
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
        balance_copy.addWidget(self._label(f"{balance:,}", "detailGoldMetric"))
        balance_copy.addWidget(self._label("Garden Coins available", "detailBody"))
        hero_layout.addWidget(icon)
        hero_layout.addLayout(balance_copy, 1)
        layout.addWidget(hero)

        self._section_label(layout, "Recent activity")
        transactions = sorted(
            self.storage.state.currency_transactions,
            key=lambda transaction: str(getattr(transaction, "occurred_at", "")),
            reverse=True,
        )
        ledger = QFrame()
        ledger.setProperty("detailCard", True)
        ledger_grid = QGridLayout(ledger)
        ledger_grid.setContentsMargins(14, 11, 14, 11)
        ledger_grid.setHorizontalSpacing(14)
        ledger_grid.setVerticalSpacing(8)
        for column, heading in enumerate(("Date", "Activity", "Coins", "Balance")):
            header = self._label(heading.upper(), "detailTableHeader")
            if column >= 2:
                header.setAlignment(Qt.AlignmentFlag.AlignRight)
            ledger_grid.addWidget(header, 0, column)
        visible = transactions if self._show_all_transactions else transactions[:8]
        if not visible:
            empty = self._label(
                "No Garden Coin activity yet. Earnings and Nursery purchases will appear here.",
                "detailSupport",
            )
            ledger_grid.addWidget(empty, 1, 0, 1, 4)
        for row, transaction in enumerate(visible, start=1):
            delta = int(transaction.delta)
            date_label = self._label(_transaction_date(transaction.occurred_at), "detailSupport")
            reason = self._label(str(transaction.reason), "detailBody")
            amount = self._label(
                f"{'+' if delta > 0 else ''}{delta:,}",
                "detailPositive" if delta >= 0 else "detailNegative",
            )
            amount.setAlignment(Qt.AlignmentFlag.AlignRight)
            resulting = self._label(f"{int(transaction.balance):,}", "detailBody")
            resulting.setAlignment(Qt.AlignmentFlag.AlignRight)
            ledger_grid.addWidget(date_label, row, 0)
            ledger_grid.addWidget(reason, row, 1)
            ledger_grid.addWidget(amount, row, 2)
            ledger_grid.addWidget(resulting, row, 3)
        ledger_grid.setColumnStretch(1, 1)
        layout.addWidget(ledger)
        if len(transactions) > 8 and not self._show_all_transactions:
            view_all = QPushButton("View all activity")
            view_all.setProperty("detailDisclosure", True)
            view_all.setMinimumHeight(40)

            def show_all() -> None:
                self._show_all_transactions = True
                self._clear_layout(layout)
                self._refresh_currency(layout)
                layout.addStretch(1)

            view_all.clicked.connect(show_all)
            layout.addWidget(view_all)

        stage_rewards = ", ".join(
            f"{format_status_label(stage)} +{amount:,}"
            for stage, amount in self.engine.STAGE_CURRENCY.items()
        )
        streak_rewards = ", ".join(
            f"{_day_count(day)} +{amount:,}"
            for day, amount in self.engine.STREAK_CURRENCY.items()
        )
        self._disclosure(
            layout,
            "how to earn Coins",
            [
                ("New plant stages", stage_rewards),
                ("Anki streak milestones", streak_rewards),
                ("Finish all due cards", "Daily Garden Coin reward"),
                ("Rare study gift", f"+{int(self.engine.COIN_DROP_AMOUNT):,}"),
            ],
        )
        self._disclosure(
            layout,
            "what Coins can purchase",
            [
                ("Plants", "Unlock new species in the Nursery"),
                ("Fertilizer", "Apply timed Growth bonuses"),
                ("Garden spaces", "Permanently expand planting capacity"),
                ("Environment", "Unlock purchasable Weather and Scenery"),
            ],
        )

    def _open_nursery(self) -> None:
        self.close()
        if callable(self.open_nursery):
            QTimer.singleShot(0, self.open_nursery)

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
                "Your garden progress is safe, but the display could not refresh. "
                "Reopen Anki Garden to try again.",
                key="display_refresh",
            )
            raise
        self._skip_next_show_refresh = not self.isVisible()

    def prompt_starter_if_needed(self) -> None:
        if not self._prompt_garden_name_if_needed():
            return
        if (
            not self._starter_prompt_scheduled
            and not bool(getattr(self.storage.state, "starter_selection_complete", True))
        ):
            self._starter_prompt_scheduled = True
            QTimer.singleShot(0, self._open_nursery)

    def _prompt_garden_name_if_needed(self) -> bool:
        if int(getattr(self.storage.state, "garden_setup_version", 0) or 0) >= 1:
            return True
        name, accepted = QInputDialog.getText(
            self,
            "Name Your Garden",
            (
                "Choose the name shown on your Garden and Anki home preview "
                f"(up to {MAX_GARDEN_NAME_LENGTH} characters):"
            ),
            text="My Garden",
        )
        if not accepted:
            return False
        ok, message = self.engine.rename_garden(str(name), complete_setup=True)
        if not ok:
            QMessageBox.warning(self, "Name Your Garden", message)
            return False
        self._refresh_after_commit("Garden setup")
        return True

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
            QFrame[topBar='true'] {{ background:#102a25; border:1px solid #29483c; border-radius:10px; }}
            QFrame[actionBar='true'] {{ background:#0d211e; border-top:1px solid #345348; border-radius:10px; }}
            QFrame[plantCard='true'] {{ background:#102421; border:2px solid #78947c; border-radius:14px; }}
            QFrame[plantCardDock='true'] {{ background:transparent; border:0; }}
            QFrame[transientFeedback='true'] {{ background:transparent; border:0; }}
            QLabel[plantCardHeading='true'] {{ color:#f5f7e8; font-size:24px; font-weight:800; }}
            QLabel[plantStageBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:800; letter-spacing:.8px; }}
            QLabel[plantCardSection='true'] {{ color:#d8b875; font-size:11px; font-weight:800; letter-spacing:1px; padding-top:3px; }}
            QLabel[plantProgressLabel='true'] {{ color:#aac0b1; font-size:13px; }}
            QLabel[plantGrowthValue='true'] {{ color:#f5f7e8; font-size:26px; font-weight:800; }}
            QFrame[plantStatus='true'] {{ background:#17312b; border:1px solid #315146; border-radius:8px; padding:7px 9px; }}
            QLabel[plantStatusLabel='true'] {{ color:#91aa9b; font-size:11px; font-weight:800; letter-spacing:.8px; }}
            QLabel[plantStatusValue='true'] {{ color:#e9d9ac; font-size:13px; font-weight:700; }}
            QFrame[movePanel='true'] {{ background:#17342e; border-left:3px solid #d1ad69; border-radius:9px; }}
            QFrame[gardenStats='true'] {{ background:#0d211e; border:1px solid #29483c; border-radius:12px; }}
            QPushButton[gardenStatCell='true'] {{ text-align:left; background:#122923; border:1px solid #2a493e; border-radius:10px; padding:0; }}
            QPushButton[gardenStatCell='true'][metric='growth'] {{ background:#17352d; border:1px solid #709078; }}
            QPushButton[gardenStatCell='true']:hover {{ background:#19372f; border-color:#8ead94; }}
            QPushButton[gardenStatCell='true'][metric='growth']:hover {{ background:#1d4035; border-color:#a8c4a7; }}
            QPushButton[gardenStatCell='true']:pressed {{ background:#0f241f; border-color:#d1ad69; }}
            QPushButton[gardenStatCell='true']:focus {{ border:2px solid #e5f2a6; }}
            QLabel[gardenStatLabel='true'] {{ color:#91aa9b; font-size:11px; font-weight:800; letter-spacing:.8px; }}
            QLabel[gardenPlantName='true'] {{ color:#f5f7e8; font-size:24px; font-weight:800; }}
            QLabel[gardenStageBadge='true'] {{ color:#efd79d; background:#3c4529; border:1px solid #7c7445; border-radius:8px; padding:4px 8px; font-size:11px; font-weight:800; letter-spacing:.7px; }}
            QLabel[gardenGrowthValue='true'] {{ color:#f5f7e8; font-size:30px; font-weight:800; }}
            QLabel[gardenLargeValue='true'] {{ color:#f5f7e8; font-size:32px; font-weight:800; }}
            QLabel[gardenValueUnit='true'] {{ color:#c8d5cb; font-size:17px; padding-bottom:3px; }}
            QLabel[gardenBonusBadge='true'] {{ color:#dff3bc; background:#284936; border:1px solid #54775d; border-radius:8px; padding:4px 7px; font-size:11px; font-weight:700; }}
            QLabel[gardenStatSupport='true'] {{ color:#9db2a5; font-size:13px; }}
            QLabel[gardenDetailsAffordance='true'] {{ color:#d8b875; font-size:12px; font-weight:700; }}
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
            QPushButton[headerAction='true'] {{ min-height:24px; max-height:24px; min-width:82px; font-size:14px; }}
            QProgressBar {{ border-radius: 7px; border: 1px solid {self.CARD_BORDER}; background: #132029; }}
            QProgressBar::chunk {{ background: #58b77b; border-radius: 6px; }}
            QProgressBar[metricProgress='true'] {{ border:0; border-radius:4px; background:#203d35; }}
            QProgressBar[metricProgress='true']::chunk {{ border-radius:4px; background:#65c487; }}
            QLabel[stagePreview='true'] {{ background:#0c211d; border:1px solid #315045; border-radius:9px; color:#aac0b1; }}
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
        t_layout.setContentsMargins(14, 8, 14, 8)
        t_layout.setSpacing(12)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        self.product_label = QLabel("ANKI GARDEN")
        self.product_label.setStyleSheet(
            "color:#d8b875; font-size:11px; font-weight:800; letter-spacing:1.2px;"
        )
        self.title_label = QLabel("")
        self._apply_typography(self.title_label, "title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(True)
        title_stack.addWidget(self.product_label)
        title_stack.addWidget(self.title_label)
        self.progress_btn = QPushButton("Progress")
        self.progress_btn.setProperty("headerAction", True)
        _set_button_variant(self.progress_btn, BUTTON_VARIANT_SECONDARY)
        self.progress_btn.setAccessibleDescription(
            "Open today, achievement, collection, and progression details."
        )
        self.progress_btn.clicked.connect(self._open_progress)
        self.settings_btn = QPushButton(UI_TEXT["open_settings"])
        self.settings_btn.setProperty("headerAction", True)
        _set_button_variant(self.settings_btn, BUTTON_VARIANT_SECONDARY)
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
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(self.nursery_recovery_btn)
        action_row.addWidget(self.progress_btn)
        action_row.addWidget(self.settings_btn)
        t_layout.addLayout(title_stack, 1)
        t_layout.addLayout(action_row, 0)

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
        self.garden_stats_bar.metricActivated.connect(self._open_metric_details)
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
        h_layout.addWidget(top)
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
        self.environment_collection_scroll = QScrollArea()
        self.environment_collection_scroll.setWidgetResizable(True)
        self.environment_collection_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.environment_collection_widget = QWidget()
        self.environment_collection_layout = QVBoxLayout(
            self.environment_collection_widget
        )
        self.environment_collection_layout.setContentsMargins(12, 12, 12, 12)
        self.environment_collection_layout.setSpacing(9)
        self.environment_collection_scroll.setWidget(
            self.environment_collection_widget
        )
        self.environment_collection_tab_index = self.details_tabs.addTab(
            self.environment_collection_scroll,
            "Weather & Scenery",
        )
        how_progresses = QWidget()
        how_layout = QVBoxLayout(how_progresses)
        how_layout.setContentsMargins(14, 14, 14, 14)
        how_layout.setSpacing(10)
        for heading, copy in (
            (
                "Plant Growth",
                "Each eligible card answer gives the nurtured plant 10 base Growth. "
                "Anki streak, Fertilizer, Booster, equipped Weather and Scenery, "
                "and Growth Charges can add more.",
            ),
            (
                "Garden Coins",
                "Coins come from new plant stages, streak milestones, finishing all due "
                "cards, and rare study gifts. Spend them in the Nursery.",
            ),
            (
                "Collection and spaces",
                "Plants remain in your collection after purchase. Garden-space upgrades "
                "determine how many can be planted at once.",
            ),
        ):
            heading_label = QLabel(heading)
            self._apply_typography(heading_label, "section-title")
            copy_label = QLabel(copy)
            copy_label.setWordWrap(True)
            self._apply_typography(copy_label, "muted-body")
            how_layout.addWidget(heading_label)
            how_layout.addWidget(copy_label)
        how_layout.addStretch(1)
        self.details_tabs.addTab(how_progresses, "How it grows")
        self.details_tabs.setTabToolTip(0, "See today’s card answers, Growth, and Garden Coin rewards.")
        self.details_tabs.setTabToolTip(1, "View long-term milestones and unlocked achievements.")
        self.details_tabs.setTabToolTip(2, "View plant names, locations, stages, and Growth.")
        self.details_tabs.setTabToolTip(
            self.environment_collection_tab_index,
            "Equip owned Weather and Scenery, hide either visual layer, and see every passive and exact drop chance.",
        )
        self.today_summary = QLabel("")
        self.today_summary.setWordWrap(True)
        self._apply_typography(self.today_summary, "muted-body")
        self.today_list.rows.insertWidget(0, self.today_summary)
        self.progress_dialog = GardenProgressDialog(self, self.details_tabs)
        self._progress_return_focus: QWidget | None = None
        self.progress_dialog.finished.connect(self._restore_progress_focus)
        self.details_dialog = GardenDetailsDialog(
            self,
            self.engine,
            self.storage,
            self._open_nursery,
        )
        self._metric_return_focus: QWidget | None = None
        self.details_dialog.finished.connect(self._restore_metric_focus)

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)

    def _open_progress(self) -> None:
        if self.details_dialog.isVisible():
            self.details_dialog.close()
        self._progress_return_focus = self.focusWidget()
        self.details_tabs.show()
        self.progress_dialog.show()
        self.progress_dialog.raise_()
        self.progress_dialog.activateWindow()

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
        self.details_dialog.open_metric(key)

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
        garden_name = str(getattr(state, "garden_name", "My Garden") or "My Garden")
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
            currency=f"{state.currency_balance:,}",
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
        self.garden_stats_bar.set_currency_details(state.currency_balance)
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

        self.today_list.clear()
        self.today_summary = QLabel(
            f"{_card_answer_count(stats.reviewed)}\n"
            f"{stats.growth_earned:,} Growth today"
        )
        self.today_summary.setWordWrap(True)
        self._apply_typography(self.today_summary, "muted-body")
        self.today_list.add_row(self.today_summary)
        due_row = ProgressRow()
        all_due_coins = 12 if state.selected_weather == "cloudy" else 10
        all_due_growth = 5 if state.selected_weather == "rainbow_sunshower" else 0
        due_row.set_item(
            "Finish all due cards",
            "Today’s available review and learning cards.",
            1 if stats.completed_due_cards else 0,
            1,
            completed=stats.completed_due_cards,
            value_text="Complete" if stats.completed_due_cards else "Not yet complete",
            completion_text=(
                f"Complete\n+{all_due_coins} Garden Coins"
                + (f" and +{all_due_growth} Growth" if all_due_growth else "")
            ),
            explanation=(
                f"{ALL_DUE_EXPLANATION} At least one card answer is required. "
                f"The current reward is {all_due_coins} Garden Coins"
                + (f" and {all_due_growth} Growth." if all_due_growth else ".")
            ),
        )
        self.today_list.add_row(due_row)
        growth_row = ProgressRow()
        growth_row.set_information(
            "Growth earned",
            "How today’s card answers became Growth.",
            (
                f"{stats.base_growth:,} base + {stats.streak_bonus_growth:,} streak + "
                f"{stats.fertilizer_growth:,} Fertilizer + "
                f"{getattr(stats, 'booster_growth', 0):,} Booster + "
                f"{getattr(stats, 'weather_growth', 0):,} Weather + "
                f"{getattr(stats, 'scenery_growth', 0):,} Scenery + "
                f"{getattr(stats, 'charge_growth', 0):,} Charges = "
                f"{stats.growth_earned:,} Growth"
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
        self._refresh_environment_collection()
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
        self.details_tabs.setTabText(
            self.environment_collection_tab_index,
            "Weather & Scenery — New" if environment_new else "Weather & Scenery",
        )
        if self.details_dialog.isVisible():
            self.details_dialog.refresh()
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
        action = str(action_id)
        handlers = {
            "garden.nursery.open": self._open_nursery,
            "garden.progress.open": self._open_progress,
        }
        handler = handlers.get(action)
        if handler is not None:
            if action == "garden.nursery.open":
                self._complete_onboarding()
            handler()

    def _open_nursery(self, tab_index: int = 0) -> None:
        if self.scene._interaction.placing:
            return
        if self.details_dialog.isVisible():
            self.details_dialog.close()
        self.scene.dismiss_selection()
        self.nursery_dialog = NurseryDialog(self, self.engine, self.storage)
        self.nursery_dialog.catalog_tabs.setCurrentIndex(
            max(0, min(3, int(tab_index)))
        )
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
        available_height = max(280, int(viewport_height or self.height()) - 220)
        target = max(280, min(650, available_height, int(available_width / scene_aspect)))
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
                "Your change was saved, but the display could not refresh. "
                "Reopen Anki Garden to try again.",
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
            "Your starter is free. Use the glowing Nursery building to see your choices."
            if starter_incomplete else
            "Use the glowing building to collect plants and unlock garden spaces."
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
            location = f"Space {plant.slot_index + 1}" if plant.planted else "Shelved"
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
        resolver = getattr(
            self.engine,
            "resolve_weather_preview_asset"
            if item.kind == "weather"
            else "resolve_scenery_preview_asset",
            None,
        )
        try:
            asset = resolver(item.item_id) if callable(resolver) else None
        except Exception:
            asset = None
        path = getattr(asset, "path", None)
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            label.setText(item.name)
            label.setWordWrap(True)
        else:
            label.setPixmap(pixmap.scaled(
                176,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
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
        odds_heading = QLabel("Exact review-drop odds")
        self._apply_typography(odds_heading, "section-title")
        self.environment_collection_layout.addWidget(odds_heading)
        odds_lines = [
            "Each eligible post-starter card answer checks these bands in order; at most one reward can win. A daily scenery gift uses that answer's reward slot.",
            *(
                f"{row['name']}: 1 in {row['denominator']:,}"
                for row in odds.get("bands", [])
            ),
            (
                f"Ultra pity: {int(odds.get('ultra_pity_misses', 0)):,} misses; "
                f"current Ultra chance 1 in {int(odds.get('ultra_denominator', 100000)):,}. "
                "The denominator improves to 90,000 at 75,000 misses, then 80,000 at 85,000, "
                "70,000 at 95,000, 60,000 at 105,000, and 50,000 at 115,000. "
                "There is no guaranteed drop; only an Ultra-band hit resets pity."
            ),
            "Tier choice is uniform among unowned items. Once a tier is complete, Rare becomes a Standard Charge; Very Rare and Ultra Rare become a Grand Charge.",
        ]
        odds_copy = QLabel("\n".join(odds_lines))
        odds_copy.setTextFormat(Qt.TextFormat.PlainText)
        odds_copy.setWordWrap(True)
        odds_copy.setProperty("rowCriteria", True)
        self.environment_collection_layout.addWidget(odds_copy)
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
        self._open_nursery(tab_index=1)
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
            visible_affordability = _compact_affordability_status(
                spec.price,
                balance_value,
                ready_text="Ready to use",
            )
            detail = QLabel(
                f"+{spec.growth_per_answer} Growth per answer for {duration}\n"
                f"{spec.price:,} Garden Coins. {visible_affordability}"
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
