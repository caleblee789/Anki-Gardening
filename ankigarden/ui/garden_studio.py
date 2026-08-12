from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from aqt.qt import (
    QCheckBox,
    QBoxLayout,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPixmap,
    QSizePolicy,
    QSlider,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
)

from ..config import DEFAULT_CONFIG
from .copy import REDUCED_MOTION_DESCRIPTION, REDUCED_MOTION_LABEL
from .scene import GardenSceneWidget
from .plant_display import growth_display, settings_layout_is_compact
from .theme import BUTTON_MIN_HEIGHT, GARDEN_THEME, tool_button_stylesheet

STUDIO_TEXT = {
    "preview_plant_name": "Preview Plant",
    "animations_label": REDUCED_MOTION_LABEL,
    "reduced_motion_description": REDUCED_MOTION_DESCRIPTION,
    "theme_label": "Garden style",
    "asset_quality_label": "Artwork detail",
    "animation_label": "Weather motion",
    "particle_label": "Weather detail",
    "home_widget_label": "Show garden preview on home screens",
    "progress_notifications_label": "Show reviewer reward notices",
}


def _describe_control(widget: QWidget, text: str) -> None:
    widget.setToolTip(text)
    widget.setAccessibleDescription(text)


class ToggleSettingRow(QFrame):
    """A full-row click target with a native, keyboard-operable switch."""

    def __init__(
        self,
        title: str,
        description: str,
        control: QCheckBox,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.control = control
        self.setProperty("toggleSettingRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setProperty("settingsHeading", True)
        heading.setWordWrap(True)
        heading.setMinimumWidth(0)
        note = QLabel(description)
        note.setProperty("settingsNote", True)
        note.setWordWrap(True)
        copy.addWidget(heading)
        copy.addWidget(note)
        layout.addLayout(copy, 1)
        control.setText("")
        control.setProperty("toggleSwitch", True)
        control.setAccessibleName(title)
        control.setAccessibleDescription(description)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.control.isEnabled():
            self.control.toggle()
            self.control.setFocus()
            event.accept()
            return
        super().mousePressEvent(event)


class HomeGardenPreview(QFrame):
    """Native mirror of the compact Home preview's artwork-first hierarchy."""

    def __init__(self, scene: GardenSceneWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("homeGardenPreview", True)
        self.setAccessibleName("Home preview")
        self.setMinimumHeight(168)
        self.setMaximumHeight(180)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        scene.setMinimumHeight(168)
        scene.setMaximumHeight(180)
        grid.addWidget(scene, 0, 0)
        self.scrim = QFrame()
        self.scrim.setProperty("previewScrim", True)
        scrim_layout = QHBoxLayout(self.scrim)
        scrim_layout.setContentsMargins(16, 22, 16, 12)
        scrim_layout.setSpacing(12)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        eyebrow = QLabel("ANKI GARDEN")
        eyebrow.setProperty("previewEyebrow", True)
        self.title = QLabel("My Garden")
        self.title.setProperty("previewTitle", True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.support = QLabel("No nurtured plant · Open the garden to choose one")
        self.support.setProperty("previewSupport", True)
        self.support.setTextFormat(Qt.TextFormat.PlainText)
        identity.addWidget(eyebrow)
        identity.addWidget(self.title)
        identity.addWidget(self.support)
        scrim_layout.addLayout(identity, 1)
        self.action = QLabel("Open garden")
        self.action.setProperty("previewAction", True)
        self.action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action.setAccessibleName("Home preview action: Open garden")
        scrim_layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(self.scrim, 0, 0, Qt.AlignmentFlag.AlignBottom)

    def set_content(self, title: str, support: str, *, enabled: bool) -> None:
        safe_title = str(title or "My Garden")
        safe_support = str(support)
        self.title.setText(safe_title)
        self.title.setToolTip(safe_title)
        self.support.setText(safe_support)
        self.support.setToolTip(safe_support)
        self.setEnabled(bool(enabled))
        self.setAccessibleDescription(
            f"{safe_title}. {safe_support}. "
            + ("Shown on Anki home screens." if enabled else "Hidden on Anki home screens.")
        )


class GardenStudioWidget(QWidget):
    """Responsive persistent settings and an explicitly non-saved preview."""

    persistentChanged = pyqtSignal()
    manageEnvironmentRequested = pyqtSignal()

    def __init__(
        self,
        config: Any,
        asset_resolver: Callable[..., dict[str, Any]] | None = None,
        garden_snapshot_provider: Callable[[], dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.asset_resolver = asset_resolver
        self.garden_snapshot_provider = garden_snapshot_provider
        self._animation_flags = (
            bool(self.config.value("enable_animations", True)),
            bool(self.config.value("reduced_motion", False)),
        )
        self._animation_control_changed = False
        self._override_values = {
            "animation_intensity": float(
                self.config.nested("theme_overrides", "animation_intensity", default=0.7)
            ),
            "weather_particle_density": float(
                self.config.nested("theme_overrides", "weather_particle_density", default=1.0)
            ),
        }
        self._override_control_changed = {
            "animation_intensity": False,
            "weather_particle_density": False,
        }
        self.preview = self._default_preview()
        self._preview_garden_name = str(
            self._garden_snapshot().get("garden_name") or "My Garden"
        )
        self.scene = GardenSceneWidget(interactive=False)
        self.scene.setMinimumHeight(168)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._apply_preview)
        self._compact_layout: bool | None = None
        self._loading_controls = True
        self._build_ui()
        self._loading_controls = False
        self._apply_preview()

    def _default_preview(self) -> dict[str, Any]:
        snapshot = self._garden_snapshot()
        return {
            "theme": self._normalize_theme(str(self.config.value("visual_theme", "verdant_twilight"))),
            "weather": str(snapshot.get("weather") or "breeze"),
            "growth_stage": "young",
            "animation_intensity": float(self.config.nested("theme_overrides", "animation_intensity", default=0.7)),
            "weather_particle_density": float(
                self.config.nested("theme_overrides", "weather_particle_density", default=1.0)
            ),
        }

    @staticmethod
    def _section(title: str, description: str = "") -> tuple[QFrame, QFormLayout]:
        frame = QFrame()
        frame.setProperty("settingsSection", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 7, 0, 7)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setProperty("settingsHeading", True)
        layout.addWidget(heading)
        if description:
            note = QLabel(description)
            note.setWordWrap(True)
            note.setProperty("settingsNote", True)
            layout.addWidget(note)
        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        layout.addLayout(form)
        return frame, form

    def _build_ui(self) -> None:
        t = GARDEN_THEME
        self.setStyleSheet(f"""
            QLabel[settingsHeading='true'] {{ color:{t['text_primary']}; font-size:15px; font-weight:700; }}
            QLabel[settingsNote='true'] {{ color:{t['text_muted']}; font-size:13px; }}
            QLabel[settingValue='true'] {{ color:#d9e7df; background:#17342e; border-radius:8px; padding:3px 7px; min-width:58px; }}
            QFrame[settingsSection='true'] {{ border:0; }}
            QFrame[settingsControls='true'] {{ background:{t['raised_surface']}; border:0; border-radius:12px; }}
            QFrame[themeCard='true'] {{ background:transparent; border:0; }}
            QFrame[previewPanel='true'] {{ background:{t['raised_surface']}; border:0; border-radius:12px; }}
            QFrame[homeGardenPreview='true'] {{ background:{t['garden_background']}; border:1px solid {t['subtle_border']}; border-radius:12px; }}
            QFrame[homeGardenPreview='true']:disabled {{ border-color:{t['disabled_border']}; }}
            QFrame[previewScrim='true'] {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(5,20,16,0),stop:.42 rgba(5,20,16,215),stop:1 rgba(5,20,16,248)); border:0; }}
            QLabel[previewEyebrow='true'] {{ color:{t['coin_accent']}; font-size:11px; font-weight:700; letter-spacing:1px; }}
            QLabel[previewTitle='true'] {{ color:{t['text_primary']}; font-size:19px; font-weight:700; }}
            QLabel[previewSupport='true'] {{ color:{t['text_secondary']}; font-size:13px; }}
            QLabel[previewAction='true'] {{ min-height:40px; padding:0 14px; color:{t['action_text']}; background:{t['action_accent']}; border-radius:8px; font-size:14px; font-weight:600; }}
            QFrame[toggleSettingRow='true'] {{ background:transparent; border:0; }}
            QComboBox {{ color:{t['text_primary']}; background:#142c27; border:1px solid {t['secondary_border']}; border-radius:8px; padding:6px 28px 6px 8px; min-height:26px; }}
            QComboBox:hover {{ border-color:#5b836f; }}
            QComboBox:focus {{ border:2px solid {t['focus_ring']}; padding:5px 27px 5px 7px; }}
            QComboBox::drop-down {{ border:0; width:24px; }}
            QComboBox QAbstractItemView {{ color:{t['text_primary']}; background:#142c27; selection-background-color:{t['action_accent']}; border:1px solid {t['secondary_border']}; }}
            QSlider::groove:horizontal {{ height:6px; background:#203d36; border-radius:3px; }}
            QSlider::sub-page:horizontal {{ background:{t['growth_accent']}; border-radius:3px; }}
            QSlider::handle:horizontal {{ width:18px; height:18px; margin:-6px 0; background:{t['focus_ring']}; border:2px solid {t['action_accent']}; border-radius:10px; }}
            QSlider::handle:horizontal:hover {{ background:#f4f8cf; border-color:{t['growth_accent']}; }}
            QSlider:disabled {{ color:#74877d; }}
            QCheckBox {{ min-height:40px; color:{t['text_primary']}; border:1px solid transparent; border-radius:6px; padding:2px 4px; }}
            QCheckBox:focus {{ border-color:{t['focus_ring']}; }}
            QCheckBox::indicator {{ width:20px; height:20px; background:#102622; border:1px solid #527563; border-radius:5px; }}
            QCheckBox::indicator:hover {{ border-color:#78a189; }}
            QCheckBox::indicator:checked {{ background:{t['growth_accent']}; border:4px solid #17342e; }}
            QCheckBox::indicator:disabled {{ background:{t['disabled_surface']}; border-color:{t['disabled_border']}; }}
            QCheckBox[toggleSwitch='true']::indicator {{ width:38px; height:22px; border-radius:11px; border:1px solid {t['strong_border']}; background:#20312c; }}
            QCheckBox[toggleSwitch='true']::indicator:checked {{ border:1px solid {t['growth_accent']}; background:{t['action_accent']}; }}
        """ + tool_button_stylesheet())
        self.root_layout = QHBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(20)
        self.controls = QFrame()
        self.controls.setProperty("settingsControls", True)
        self.controls.setMinimumWidth(340)
        self.controls.setMaximumWidth(380)
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setSpacing(12)

        self.asset_quality_combo = QComboBox()
        self.asset_quality_combo.setAccessibleName(STUDIO_TEXT["asset_quality_label"])
        self.asset_quality_combo.addItem("Balanced", "balanced")
        self.asset_quality_combo.addItem("Performance", "performance")
        self.asset_quality_combo.addItem("Ultra", "ultra")
        _describe_control(
            self.asset_quality_combo,
            "Performance favors speed with lighter artwork. Balanced keeps detail and speed even. "
            "Ultra uses the most detailed artwork and may use more memory.",
        )

        self.theme_card = QFrame()
        self.theme_card.setProperty("themeCard", True)
        self.theme_card.setAccessibleName("Current Scenery: Verdant Twilight")
        theme_layout = QHBoxLayout(self.theme_card)
        theme_layout.setContentsMargins(12, 10, 12, 10)
        self.theme_thumbnail = QLabel()
        self.theme_thumbnail.setFixedSize(96, 54)
        self.theme_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_thumbnail.setAccessibleName("Verdant Twilight preview")
        self.theme_thumbnail.setStyleSheet("background:#0b2926; border-radius:7px;")
        theme_copy = QVBoxLayout()
        theme_title = QLabel("Scenery")
        theme_title.setProperty("settingsHeading", True)
        theme_title.setWordWrap(True)
        theme_value = QLabel("Verdant Twilight")
        theme_value.setStyleSheet("font-weight:600;")
        theme_note = QLabel("Changes the garden weather and background appearance.")
        theme_note.setWordWrap(True)
        theme_note.setProperty("settingsNote", True)
        theme_copy.addWidget(theme_title)
        theme_copy.addWidget(theme_value)
        theme_copy.addWidget(theme_note)
        theme_layout.addWidget(self.theme_thumbnail)
        theme_layout.addLayout(theme_copy, 1)
        controls_layout.addWidget(self.theme_card)
        self.manage_environment = QToolButton()
        self.manage_environment.setText("Customize Garden")
        self.manage_environment.setAccessibleDescription(
            "Open the separate Customize Garden surface for Weather and Scenery."
        )
        self.manage_environment.clicked.connect(self.manageEnvironmentRequested.emit)
        controls_layout.addWidget(self.manage_environment)

        self.reduced_motion = QCheckBox()
        self.reduced_motion.setAccessibleName(REDUCED_MOTION_LABEL)
        _describe_control(
            self.reduced_motion,
            REDUCED_MOTION_DESCRIPTION,
        )
        # Compatibility alias for callers that used the old internal widget
        # name. Its checked state now directly represents reduced motion.
        self.animations_enabled = self.reduced_motion
        self.anim_slider = QSlider(Qt.Orientation.Horizontal)
        self.anim_slider.setAccessibleName(STUDIO_TEXT["animation_label"])
        self.anim_slider.setRange(0, 100)
        _describe_control(
            self.anim_slider,
            "Adjust how strongly weather moves. Lower values are calmer; higher values are more active.",
        )
        self.anim_value = QLabel()
        self.anim_value.setAccessibleName("Motion amount value")
        self.anim_value.setProperty("settingValue", True)
        anim_row = QHBoxLayout()
        anim_row.addWidget(self.anim_slider, 1)
        anim_row.addWidget(self.anim_value)

        self.particle_slider = QSlider(Qt.Orientation.Horizontal)
        self.particle_slider.setAccessibleName(STUDIO_TEXT["particle_label"])
        self.particle_slider.setRange(10, 200)
        _describe_control(
            self.particle_slider,
            "Adjust how much weather detail appears. Lower values use fewer effects; higher values use more.",
        )
        self.particle_value = QLabel()
        self.particle_value.setAccessibleName("Weather detail value")
        self.particle_value.setProperty("settingValue", True)
        particle_row = QHBoxLayout()
        particle_row.addWidget(self.particle_slider, 1)
        particle_row.addWidget(self.particle_value)

        self.motion_row = ToggleSettingRow(
            REDUCED_MOTION_LABEL,
            REDUCED_MOTION_DESCRIPTION,
            self.reduced_motion,
        )
        controls_layout.addWidget(self.motion_row)

        self.show_home_widget = QCheckBox()
        self.show_home_widget.setAccessibleName(STUDIO_TEXT["home_widget_label"])
        _describe_control(
            self.show_home_widget,
            "Show or hide the Garden summary on Anki home screens.",
        )
        self.show_progress_notifications = QCheckBox()
        self.show_progress_notifications.setAccessibleName(STUDIO_TEXT["progress_notifications_label"])
        _describe_control(
            self.show_progress_notifications,
            "Show brief Garden progress notifications after studying.",
        )
        self.home_preview_row = ToggleSettingRow(
            STUDIO_TEXT["home_widget_label"],
            "Show this compact Garden preview in the Deck Browser and Deck Overview.",
            self.show_home_widget,
        )
        controls_layout.insertWidget(0, self.home_preview_row)

        self.fine_tune_toggle = QToolButton()
        self.fine_tune_toggle.setText("Fine tune")
        self.fine_tune_toggle.setCheckable(True)
        self.fine_tune_toggle.setChecked(False)
        self.fine_tune_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.fine_tune_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.fine_tune_toggle.setAccessibleName("Show fine-tune settings")
        self.fine_tune_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.fine_tune_toggle.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.fine_tune_section, fine_tune_form = self._section(
            "Weather effects",
            "Adjust weather motion and density only when you need to.",
        )
        # Artwork Detail previously only changed weather-overlay variants while
        # implying that all plant/background art would change. Preserve the
        # stored compatibility value, but remove the misleading visible control.
        self.asset_quality_combo.hide()
        fine_tune_form.addRow(STUDIO_TEXT["animation_label"], anim_row)
        fine_tune_form.addRow(STUDIO_TEXT["particle_label"], particle_row)
        self.fine_tune_section.hide()
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setAccessibleName("Show advanced display settings")
        self.advanced_panel = QFrame()
        self.advanced_panel.setProperty("settingsSection", True)
        self.advanced_actions_layout = QVBoxLayout(self.advanced_panel)
        self.advanced_actions_layout.setContentsMargins(0, 8, 0, 0)
        self.advanced_actions_layout.setSpacing(8)
        self.notifications_row = ToggleSettingRow(
            STUDIO_TEXT["progress_notifications_label"],
            "Show brief Growth and reward notices after studying.",
            self.show_progress_notifications,
        )
        self.advanced_actions_layout.addWidget(self.notifications_row)
        self.advanced_panel.hide()
        controls_layout.addWidget(self.advanced_toggle)
        controls_layout.addWidget(self.advanced_panel)
        controls_layout.addStretch(1)

        self.preview_panel = QFrame()
        self.preview_panel.setProperty("previewPanel", True)
        self.preview_panel.setAccessibleName("Garden preview")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)
        preview_title = QLabel("Home preview")
        preview_title.setProperty("settingsHeading", True)
        preview_note = QLabel(
            "This is how the garden will appear on Anki home screens."
        )
        preview_note.setWordWrap(True)
        preview_note.setProperty("settingsNote", True)
        self.preview_disabled_note = QLabel("Home-screen preview is turned off.")
        self.preview_disabled_note.setWordWrap(True)
        self.preview_disabled_note.setStyleSheet("color:#e6c47a; font-weight:700;")
        self.preview_disabled_note.hide()
        self.home_preview = HomeGardenPreview(self.scene)
        self.preview_name = self.home_preview.title
        self.preview_metrics = self.home_preview.support
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.home_preview)
        preview_layout.addWidget(preview_note)
        preview_layout.addWidget(self.preview_disabled_note)

        self.root_layout.addWidget(self.controls, 0)
        self.root_layout.addWidget(self.preview_panel, 1)

        self.asset_quality_combo.currentIndexChanged.connect(self._on_persistent_preview_change)
        self.reduced_motion.toggled.connect(self._on_reduced_motion_toggled)
        self.reduced_motion.toggled.connect(self._update_motion_controls)
        self.show_home_widget.toggled.connect(self._on_persistent_change)
        self.show_home_widget.toggled.connect(self._sync_switch_copy)
        self.show_home_widget.toggled.connect(self._sync_preview_enabled)
        self.show_progress_notifications.toggled.connect(self._on_persistent_change)
        self.show_progress_notifications.toggled.connect(self._sync_switch_copy)
        self.fine_tune_toggle.toggled.connect(self._set_fine_tune_expanded)
        self.advanced_toggle.toggled.connect(self._set_advanced_expanded)
        self.anim_slider.valueChanged.connect(
            lambda _value: self._on_slider_changed("animation_intensity")
        )
        self.particle_slider.valueChanged.connect(
            lambda _value: self._on_slider_changed("weather_particle_density")
        )

        self.apply_persistent_payload(self._config_payload())
        self.reset_preview_defaults()
        self._update_slider_labels()
        self._update_motion_controls()
        self._apply_responsive_layout(self.width())

    def _sync_switch_copy(self, checked: bool) -> None:
        sender = self.sender()
        if isinstance(sender, QCheckBox):
            sender.setAccessibleDescription("On" if checked else "Off")

    def _sync_preview_enabled(self, checked: bool) -> None:
        self.preview_disabled_note.setVisible(not checked)
        self.home_preview.setEnabled(checked)

    def set_preview_garden_name(self, name: str) -> None:
        self._preview_garden_name = str(name or "My Garden")
        self.preview_name.setText(self._preview_garden_name)
        self.preview_name.setToolTip(self._preview_garden_name)

    def _set_fine_tune_expanded(self, expanded: bool) -> None:
        self.fine_tune_section.setVisible(bool(expanded))
        self.fine_tune_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.fine_tune_toggle.setAccessibleName(
            "Hide fine-tune settings" if expanded else "Show fine-tune settings"
        )

    def _set_advanced_expanded(self, expanded: bool) -> None:
        self.advanced_panel.setVisible(bool(expanded))
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.advanced_toggle.setAccessibleName(
            "Hide advanced display settings" if expanded else "Show advanced display settings"
        )

    def collapse_preview_examples(self) -> None:
        """Compatibility hook used by the settings dialog when it is reopened."""
        self.fine_tune_toggle.setChecked(False)
        self.advanced_toggle.setChecked(False)

    def _config_payload(self) -> dict[str, Any]:
        return {
            "visual_theme": self.config.value("visual_theme", DEFAULT_CONFIG["visual_theme"]),
            "enable_animations": self.config.value("enable_animations", DEFAULT_CONFIG["enable_animations"]),
            "reduced_motion": self.config.value("reduced_motion", DEFAULT_CONFIG["reduced_motion"]),
            "show_home_widget": self.config.value("show_home_widget", DEFAULT_CONFIG["show_home_widget"]),
            "show_progress_notifications": self.config.value(
                "show_progress_notifications", DEFAULT_CONFIG["show_progress_notifications"]
            ),
            "assets": {"quality_preference": self.config.nested("assets", "quality_preference", default="balanced")},
            "theme_overrides": {
                "animation_intensity": self.config.nested("theme_overrides", "animation_intensity", default=0.7),
                "weather_particle_density": self.config.nested("theme_overrides", "weather_particle_density", default=1.0),
            },
        }

    def apply_persistent_payload(self, payload: dict[str, Any]) -> None:
        self._preview_timer.stop()
        self._loading_controls = True
        try:
            theme = self._normalize_theme(str(payload.get("visual_theme", "verdant_twilight")))
            quality = str(payload.get("assets", {}).get("quality_preference", "balanced"))
            self.asset_quality_combo.setCurrentIndex(max(0, self.asset_quality_combo.findData(quality)))
            self._animation_flags = (
                bool(payload.get("enable_animations", True)),
                bool(payload.get("reduced_motion", False)),
            )
            self._animation_control_changed = False
            self.reduced_motion.setChecked(bool(payload.get("reduced_motion", False)))
            self.show_home_widget.setChecked(bool(payload.get("show_home_widget", True)))
            self.show_progress_notifications.setChecked(bool(payload.get("show_progress_notifications", False)))
            overrides = payload.get("theme_overrides", {})
            self._override_values = {
                "animation_intensity": float(overrides.get("animation_intensity", 0.7)),
                "weather_particle_density": float(overrides.get("weather_particle_density", 1.0)),
            }
            self._override_control_changed = {
                "animation_intensity": False,
                "weather_particle_density": False,
            }
            self.anim_slider.setValue(round(self._override_values["animation_intensity"] * 100))
            self.particle_slider.setValue(round(self._override_values["weather_particle_density"] * 100))
            self.preview["theme"] = theme
            self.preview["animation_intensity"] = self.anim_slider.value() / 100.0
            self.preview["weather_particle_density"] = self.particle_slider.value() / 100.0
            self._update_slider_labels()
            self._update_motion_controls()
            self._apply_preview()
        finally:
            self._loading_controls = False

    def restore_persistent_defaults(self) -> None:
        payload = {
            key: deepcopy(DEFAULT_CONFIG[key])
            for key in (
                "visual_theme", "enable_animations", "reduced_motion",
                "show_home_widget", "show_progress_notifications", "assets", "theme_overrides",
            )
        }
        self.apply_persistent_payload(payload)
        self.reset_preview_defaults()
        self.persistentChanged.emit()

    def reset_preview_defaults(self) -> None:
        self._preview_timer.stop()
        self._loading_controls = True
        try:
            self.preview["weather"] = str(self._garden_snapshot().get("weather") or "breeze")
            self.preview["growth_stage"] = "young"
            self._apply_preview()
        finally:
            self._loading_controls = False

    def _apply_responsive_layout(self, width: int) -> None:
        compact = settings_layout_is_compact(width)
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self.root_layout.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        self.controls.setMaximumWidth(16777215 if compact else 380)

    def resizeEvent(self, event: Any) -> None:
        self._apply_responsive_layout(event.size().width())
        super().resizeEvent(event)

    def _update_slider_labels(self) -> None:
        self.anim_value.setText(self._level_label(self.anim_slider.value(), 35, 75))
        self.particle_value.setText(self._level_label(self.particle_slider.value(), 60, 110))

    @staticmethod
    def _level_label(value: int, low_max: int, standard_max: int) -> str:
        if value <= low_max:
            return "Low"
        if value <= standard_max:
            return "Standard"
        return "High"

    def _update_motion_controls(self) -> None:
        enabled = bool(self._animation_flags[0]) and not self.reduced_motion.isChecked()
        for widget in (self.anim_slider, self.particle_slider, self.anim_value, self.particle_value):
            widget.setEnabled(enabled)

    def _on_persistent_change(self, *_args: Any) -> None:
        if not self._loading_controls:
            self.persistentChanged.emit()

    def _on_persistent_preview_change(self, *_args: Any) -> None:
        self._on_persistent_change()
        self._schedule_preview()

    def _on_reduced_motion_toggled(self, *_args: Any) -> None:
        if not self._loading_controls:
            self._animation_control_changed = True
        self._on_persistent_preview_change()

    # Keep the old method callable for integrations that used it as an
    # internal signal handler during the previous settings layout.
    def _on_animation_toggled(self, *_args: Any) -> None:
        self._on_reduced_motion_toggled(*_args)

    def _on_slider_changed(self, key: str) -> None:
        if not self._loading_controls and key in self._override_control_changed:
            self._override_control_changed[key] = True
        self.preview["animation_intensity"] = self.anim_slider.value() / 100.0
        self.preview["weather_particle_density"] = self.particle_slider.value() / 100.0
        self._update_slider_labels()
        self._on_persistent_change()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if not self._loading_controls and not self.reduced_motion.isChecked():
            self._preview_timer.start()
        elif self.reduced_motion.isChecked():
            self._preview_timer.stop()
            self._apply_preview()

    def _apply_preview(self) -> None:
        snapshot = self._garden_snapshot()
        real_plants = snapshot.get("plants", [])
        if not isinstance(real_plants, list):
            real_plants = []
        preview_weather = (
            str(snapshot.get("weather") or self.preview["weather"])
            if self.garden_snapshot_provider is not None
            else str(self.preview["weather"])
        )
        growth = max(0.0, min(1.0, float(snapshot.get("growth", 0.0) or 0.0)))
        if self.garden_snapshot_provider is None:
            growth = 0.85 if self.preview["growth_stage"] in ("flowering", "rare") else 0.45
            if self.preview["growth_stage"] in ("seed", "sprout"):
                growth = 0.15
        quality = "balanced"
        asset_paths: dict[str, Any] = {}
        if self.asset_resolver:
            try:
                try:
                    asset_paths = self.asset_resolver(
                        self._normalize_theme(str(self.preview["theme"])),
                        preview_weather,
                        str(self.preview["growth_stage"]),
                        quality,
                        real_plants,
                    )
                except TypeError:
                    asset_paths = self.asset_resolver(
                        self._normalize_theme(str(self.preview["theme"])),
                        preview_weather,
                        str(self.preview["growth_stage"]),
                        quality,
                    )
            except Exception:
                asset_paths = {}
        preview_assets = asset_paths.get("plants", {}) if isinstance(asset_paths.get("plants"), dict) else {}
        background_asset = asset_paths.get("background")
        background_path = (
            background_asset.get("path")
            if isinstance(background_asset, dict)
            else background_asset
        )
        background_pixmap = QPixmap(str(background_path)) if background_path else QPixmap()
        if background_pixmap.isNull():
            self.theme_thumbnail.setText("Verdant\nTwilight")
        else:
            self.theme_thumbnail.setPixmap(background_pixmap.scaled(
                self.theme_thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        preview_points = {"seed": 0, "sprout": 500, "young": 2_500, "mature": 8_000, "flowering": 20_000, "rare": 50_000}.get(
            str(self.preview["growth_stage"]), 0
        )
        preview_growth = growth_display(preview_points)
        if self.garden_snapshot_provider is not None:
            scene_plants = []
            for item in real_plants:
                if not isinstance(item, dict):
                    continue
                points = max(0, int(item.get("growth_points", 0) or 0))
                display = growth_display(points)
                species = str(item.get("species") or "plant")
                scene_plants.append({
                    **item,
                    "stage": str(item.get("stage") or display.stage),
                    "growth_points": points,
                    "next_stage": display.next_stage,
                    "stage_progress": display.progress,
                    "stage_points": display.stage_points,
                    "stage_goal": display.stage_goal,
                    "fully_grown": display.fully_grown,
                    "asset": preview_assets.get(species),
                })
        else:
            scene_plants = [
                {
                    "plant_id": f"preview-{species}", "slot_index": slot_index,
                    "name": species.replace("_", " ").title(),
                    "species": species, "stage": self.preview["growth_stage"],
                    "growth_points": preview_points,
                    "next_stage": preview_growth.next_stage, "stage_progress": preview_growth.progress,
                    "stage_points": preview_growth.stage_points, "stage_goal": preview_growth.stage_goal,
                    "fully_grown": preview_growth.fully_grown, "is_active": slot_index == 0,
                    "asset": preview_assets.get(species) or (asset_paths.get("plant") if species == "rose" else None),
                }
                for slot_index, species in enumerate(("bonsai", "rose", "sunflower"))
            ]
        active = next(
            (item for item in scene_plants if isinstance(item, dict) and item.get("is_active")),
            scene_plants[0] if scene_plants else {},
        )
        plant_name = str(active.get("name") or "No nurtured plant")
        stage = str(active.get("stage") or "seed").replace("_", " ").title()
        stage_points = max(0, int(active.get("stage_points", 0) or 0))
        stage_goal = max(0, int(active.get("stage_goal", 0) or 0))
        support = (
            f"{plant_name} · {stage} · {stage_points:,} / {stage_goal:,} Growth"
            if active else
            "No nurtured plant · Open the garden to choose one"
        )
        self.home_preview.set_content(
            self._preview_garden_name,
            support,
            enabled=self.show_home_widget.isChecked(),
        )
        self.scene.set_scene({
            "weather": preview_weather,
            "growth": growth,
            "theme": self.preview["theme"],
            "animation_intensity": self.preview["animation_intensity"],
            "weather_particle_density": self.preview["weather_particle_density"],
            "motion_enabled": bool(self._animation_flags[0]) and not self.reduced_motion.isChecked(),
            "asset_paths": {
                "background": asset_paths.get("background"),
                "garden_overlay": asset_paths.get("garden_overlay"),
                "weather": asset_paths.get("weather"),
            },
            "unlocked_slots": int(snapshot.get("unlocked_slots", 6) or 6),
            "streak_days": int(snapshot.get("streak_days", 0) or 0),
            "streak_bonus_percent": int(snapshot.get("streak_bonus_percent", 0) or 0),
            # The Settings preview is about artwork and motion. Its old demo
            # percentage could contradict the real garden, so keep the status
            # overlay out of this read-only preview.
            "show_status_overlay": False,
            "plants": scene_plants,
        })

    def _garden_snapshot(self) -> dict[str, Any]:
        if self.garden_snapshot_provider is None:
            return {}
        try:
            snapshot = self.garden_snapshot_provider()
        except Exception:
            return {}
        return snapshot if isinstance(snapshot, dict) else {}

    def build_theme_payload(self) -> dict[str, Any]:
        quality = "balanced"
        animation_flags = (
            (
                self._animation_flags[0],
                self.reduced_motion.isChecked(),
            )
            if self._animation_control_changed
            else self._animation_flags
        )
        return {
            "visual_theme": "verdant_twilight",
            "enable_animations": animation_flags[0],
            "reduced_motion": animation_flags[1],
            "show_home_widget": self.show_home_widget.isChecked(),
            "show_progress_notifications": self.show_progress_notifications.isChecked(),
            "assets": {"quality_preference": quality},
            "theme_overrides": {
                "animation_intensity": (
                    self.anim_slider.value() / 100.0
                    if self._override_control_changed["animation_intensity"]
                    else self._override_values["animation_intensity"]
                ),
                "weather_particle_density": (
                    self.particle_slider.value() / 100.0
                    if self._override_control_changed["weather_particle_density"]
                    else self._override_values["weather_particle_density"]
                ),
            },
        }

    def _normalize_theme(self, theme: str) -> str:
        return {
            "morning_bloom": "verdant_twilight",
            "verdant_dawn": "verdant_twilight",
            "verdant_dusk": "verdant_twilight",
            "moonlit_study": "verdant_twilight",
        }.get(str(theme), str(theme))
