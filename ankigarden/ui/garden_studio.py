from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from aqt.qt import (
    QCheckBox,
    QBoxLayout,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
)

from ..config import DEFAULT_CONFIG
from .scene import GardenSceneWidget
from .plant_display import growth_display, settings_layout_is_compact

STUDIO_TEXT = {
    "preview_plant_name": "Preview Plant",
    "animations_label": "Animate weather",
    "theme_label": "Theme",
    "asset_quality_label": "Artwork detail",
    "weather_label": "Preview weather",
    "growth_stage_label": "Preview growth stage",
    "animation_label": "Weather motion",
    "particle_label": "Weather detail",
    "daily_goal_label": "Daily growth goal",
    "home_widget_label": "Show garden on home screens",
}


class GardenStudioWidget(QWidget):
    """Responsive persistent settings and an explicitly non-saved preview."""

    persistentChanged = pyqtSignal()

    def __init__(
        self,
        config: Any,
        asset_resolver: Callable[[str, str, str, str], dict[str, str | None]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.asset_resolver = asset_resolver
        self.preview = self._default_preview()
        self.scene = GardenSceneWidget(interactive=False)
        self.scene.setMinimumHeight(250)
        self._compact_layout: bool | None = None
        self._loading_controls = True
        self._build_ui()
        self._loading_controls = False
        self._apply_preview()

    def _default_preview(self) -> dict[str, Any]:
        return {
            "theme": self._normalize_theme(str(self.config.value("visual_theme", "verdant_dusk"))),
            "weather": "breeze",
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
        self.setStyleSheet(
            "QLabel[settingsHeading='true'] { font-size:15px; font-weight:700; }"
            "QLabel[settingsNote='true'] { color:#aebfc3; font-size:12px; }"
            "QFrame[settingsSection='true'] { border-top:1px solid rgba(130,160,168,.22); }"
        )
        self.root_layout = QHBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(18)
        self.controls = QFrame()
        self.controls.setMaximumWidth(390)
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName(STUDIO_TEXT["theme_label"])
        self.theme_combo.addItem("Verdant Dusk", "verdant_dusk")
        self.theme_combo.addItem("Morning Bloom", "verdant_dawn")
        self.theme_combo.addItem("Moonlit Study", "moonlit_study")

        self.asset_quality_combo = QComboBox()
        self.asset_quality_combo.setAccessibleName(STUDIO_TEXT["asset_quality_label"])
        self.asset_quality_combo.addItem("Balanced", "balanced")
        self.asset_quality_combo.addItem("Performance", "performance")
        self.asset_quality_combo.addItem("Ultra", "ultra")

        appearance, appearance_form = self._section("Appearance")
        appearance_form.addRow(STUDIO_TEXT["theme_label"], self.theme_combo)
        appearance_form.addRow(STUDIO_TEXT["asset_quality_label"], self.asset_quality_combo)
        controls_layout.addWidget(appearance)

        self.animations_enabled = QCheckBox()
        self.animations_enabled.setAccessibleName(STUDIO_TEXT["animations_label"])
        self.anim_slider = QSlider(Qt.Orientation.Horizontal)
        self.anim_slider.setAccessibleName(STUDIO_TEXT["animation_label"])
        self.anim_slider.setRange(0, 100)
        self.anim_value = QLabel()
        self.anim_value.setAccessibleName("Motion amount value")
        anim_row = QHBoxLayout()
        anim_row.addWidget(self.anim_slider, 1)
        anim_row.addWidget(self.anim_value)

        self.particle_slider = QSlider(Qt.Orientation.Horizontal)
        self.particle_slider.setAccessibleName(STUDIO_TEXT["particle_label"])
        self.particle_slider.setRange(20, 125)
        self.particle_value = QLabel()
        self.particle_value.setAccessibleName("Weather detail value")
        particle_row = QHBoxLayout()
        particle_row.addWidget(self.particle_slider, 1)
        particle_row.addWidget(self.particle_value)

        motion, motion_form = self._section("Motion and weather")
        motion_form.addRow(STUDIO_TEXT["animations_label"], self.animations_enabled)
        motion_form.addRow(STUDIO_TEXT["animation_label"], anim_row)
        motion_form.addRow(STUDIO_TEXT["particle_label"], particle_row)
        controls_layout.addWidget(motion)

        self.daily_goal = QSpinBox()
        self.daily_goal.setAccessibleName(STUDIO_TEXT["daily_goal_label"])
        self.daily_goal.setRange(10, 2000)
        self.daily_goal.setSingleStep(10)
        progress, progress_form = self._section("Progress")
        progress_form.addRow(STUDIO_TEXT["daily_goal_label"], self.daily_goal)
        controls_layout.addWidget(progress)

        self.show_home_widget = QCheckBox()
        self.show_home_widget.setAccessibleName(STUDIO_TEXT["home_widget_label"])
        integration, integration_form = self._section("Anki integration")
        integration_form.addRow(STUDIO_TEXT["home_widget_label"], self.show_home_widget)
        controls_layout.addWidget(integration)

        self.weather_combo = QComboBox()
        self.weather_combo.setAccessibleName(STUDIO_TEXT["weather_label"])
        for weather in ["breeze", "cloudy", "gentle_rain", "fireflies", "sunny"]:
            self.weather_combo.addItem(weather.replace("_", " ").title(), weather)
        self.growth_stage_combo = QComboBox()
        self.growth_stage_combo.setAccessibleName(STUDIO_TEXT["growth_stage_label"])
        for stage in ["seed", "sprout", "young", "mature", "flowering", "rare"]:
            self.growth_stage_combo.addItem(stage.title(), stage)
        preview, preview_form = self._section(
            "Preview only",
            "These demonstration controls update the preview and are never saved.",
        )
        preview_form.addRow(STUDIO_TEXT["weather_label"], self.weather_combo)
        preview_form.addRow(STUDIO_TEXT["growth_stage_label"], self.growth_stage_combo)
        controls_layout.addWidget(preview)
        controls_layout.addStretch(1)

        self.root_layout.addWidget(self.controls, 0)
        self.root_layout.addWidget(self.scene, 1)

        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.asset_quality_combo.currentIndexChanged.connect(self._on_persistent_preview_change)
        self.animations_enabled.toggled.connect(self._on_persistent_preview_change)
        self.animations_enabled.toggled.connect(self._update_motion_controls)
        self.daily_goal.valueChanged.connect(self._on_persistent_change)
        self.show_home_widget.toggled.connect(self._on_persistent_change)
        self.weather_combo.currentIndexChanged.connect(self._on_preview_toggle)
        self.growth_stage_combo.currentIndexChanged.connect(self._on_preview_toggle)
        self.anim_slider.valueChanged.connect(self._on_slider_changed)
        self.particle_slider.valueChanged.connect(self._on_slider_changed)

        self.apply_persistent_payload(self._config_payload())
        self.reset_preview_defaults()
        self._update_slider_labels()
        self._update_motion_controls()
        self._apply_responsive_layout(self.width())

    def _config_payload(self) -> dict[str, Any]:
        return {
            "visual_theme": self.config.value("visual_theme", DEFAULT_CONFIG["visual_theme"]),
            "enable_animations": self.config.value("enable_animations", DEFAULT_CONFIG["enable_animations"]),
            "reduced_motion": self.config.value("reduced_motion", DEFAULT_CONFIG["reduced_motion"]),
            "daily_goal": self.config.value("daily_goal", DEFAULT_CONFIG["daily_goal"]),
            "show_home_widget": self.config.value("show_home_widget", DEFAULT_CONFIG["show_home_widget"]),
            "assets": {"quality_preference": self.config.nested("assets", "quality_preference", default="balanced")},
            "theme_overrides": {
                "animation_intensity": self.config.nested("theme_overrides", "animation_intensity", default=0.7),
                "weather_particle_density": self.config.nested("theme_overrides", "weather_particle_density", default=1.0),
            },
        }

    def apply_persistent_payload(self, payload: dict[str, Any]) -> None:
        self._loading_controls = True
        try:
            theme = self._normalize_theme(str(payload.get("visual_theme", "verdant_dusk")))
            self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(theme)))
            quality = str(payload.get("assets", {}).get("quality_preference", "balanced"))
            self.asset_quality_combo.setCurrentIndex(max(0, self.asset_quality_combo.findData(quality)))
            enabled = bool(payload.get("enable_animations", True)) and not bool(payload.get("reduced_motion", False))
            self.animations_enabled.setChecked(enabled)
            self.daily_goal.setValue(int(payload.get("daily_goal", 140)))
            self.show_home_widget.setChecked(bool(payload.get("show_home_widget", True)))
            overrides = payload.get("theme_overrides", {})
            self.anim_slider.setValue(int(float(overrides.get("animation_intensity", 0.7)) * 100))
            self.particle_slider.setValue(int(float(overrides.get("weather_particle_density", 1.0)) * 100))
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
            for key in ("visual_theme", "enable_animations", "reduced_motion", "daily_goal", "show_home_widget", "assets", "theme_overrides")
        }
        self.apply_persistent_payload(payload)
        self.reset_preview_defaults()
        self.persistentChanged.emit()

    def reset_preview_defaults(self) -> None:
        self._loading_controls = True
        try:
            self.weather_combo.setCurrentIndex(max(0, self.weather_combo.findData("breeze")))
            self.growth_stage_combo.setCurrentIndex(max(0, self.growth_stage_combo.findData("young")))
            self.preview["weather"] = "breeze"
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
        self.controls.setMaximumWidth(16777215 if compact else 390)

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
        enabled = self.animations_enabled.isChecked()
        for widget in (self.anim_slider, self.particle_slider, self.anim_value, self.particle_value):
            widget.setEnabled(enabled)

    def _on_persistent_change(self, *_args: Any) -> None:
        if not self._loading_controls:
            self.persistentChanged.emit()

    def _on_persistent_preview_change(self, *_args: Any) -> None:
        self._on_persistent_change()
        self._apply_preview()

    def _on_theme_changed(self, *_args: Any) -> None:
        self.preview["theme"] = self._normalize_theme(str(self.theme_combo.currentData()))
        self._on_persistent_change()
        self._apply_preview()

    def _on_preview_toggle(self, *_args: Any) -> None:
        self.preview["weather"] = str(self.weather_combo.currentData())
        self.preview["growth_stage"] = str(self.growth_stage_combo.currentData())
        self._apply_preview()

    def _on_slider_changed(self, *_args: Any) -> None:
        self.preview["animation_intensity"] = self.anim_slider.value() / 100.0
        self.preview["weather_particle_density"] = self.particle_slider.value() / 100.0
        self._update_slider_labels()
        self._on_persistent_change()
        self._apply_preview()

    def _apply_preview(self) -> None:
        growth = 0.85 if self.preview["growth_stage"] in ("flowering", "rare") else 0.45
        if self.preview["growth_stage"] in ("seed", "sprout"):
            growth = 0.15
        quality = str(self.asset_quality_combo.currentData() or "balanced")
        asset_paths: dict[str, Any] = {}
        if self.asset_resolver:
            try:
                asset_paths = self.asset_resolver(
                    self._normalize_theme(str(self.preview["theme"])),
                    str(self.preview["weather"]),
                    str(self.preview["growth_stage"]),
                    quality,
                )
            except Exception:
                asset_paths = {}
        preview_assets = asset_paths.get("plants", {}) if isinstance(asset_paths.get("plants"), dict) else {}
        preview_points = {"seed": 0, "sprout": 80, "young": 220, "mature": 480, "flowering": 900, "rare": 1400}.get(
            str(self.preview["growth_stage"]), 0
        )
        preview_growth = growth_display(preview_points, self.preview["growth_stage"] == "rare")
        self.scene.set_scene({
            "weather": self.preview["weather"],
            "growth": growth,
            "health": 0.85,
            "theme": self.preview["theme"],
            "animation_intensity": self.preview["animation_intensity"],
            "weather_particle_density": self.preview["weather_particle_density"],
            "motion_enabled": self.animations_enabled.isChecked(),
            "asset_paths": {
                "background": asset_paths.get("background"),
                "garden_overlay": asset_paths.get("garden_overlay"),
                "weather": asset_paths.get("weather"),
            },
            "plants": [
                {
                    "plant_id": f"preview-{species}", "slot_index": slot_index, "name": species.title(),
                    "species": species, "stage": self.preview["growth_stage"], "vitality": 0.95,
                    "health_label": "Thriving", "growth_points": preview_points,
                    "next_stage": preview_growth.next_stage, "stage_progress": preview_growth.progress,
                    "stage_points": preview_growth.stage_points, "stage_goal": preview_growth.stage_goal,
                    "fully_grown": preview_growth.fully_grown, "is_focus": slot_index == 0,
                    "asset": preview_assets.get(species) or (asset_paths.get("plant") if species == "rose" else None),
                }
                for slot_index, species in enumerate(("bonsai", "rose", "sunbloom"))
            ],
        })

    def build_theme_payload(self) -> dict[str, Any]:
        quality = str(self.asset_quality_combo.currentData())
        return {
            "visual_theme": self._normalize_theme(str(self.theme_combo.currentData())),
            "enable_animations": self.animations_enabled.isChecked(),
            "reduced_motion": not self.animations_enabled.isChecked(),
            "daily_goal": self.daily_goal.value(),
            "show_home_widget": self.show_home_widget.isChecked(),
            "assets": {"quality_preference": quality},
            "theme_overrides": {
                "animation_intensity": self.anim_slider.value() / 100.0,
                "weather_particle_density": self.particle_slider.value() / 100.0,
            },
        }

    def _normalize_theme(self, theme: str) -> str:
        return {"morning_bloom": "verdant_dawn"}.get(str(theme), str(theme))
