from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QCheckBox,
    QBoxLayout,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QLabel,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .scene import GardenSceneWidget
from .plant_display import growth_display, settings_layout_is_compact

STUDIO_TEXT = {
    "preview_plant_name": "Preview Plant",
    "animations_label": "Animate garden",
    "theme_label": "Theme",
    "asset_quality_label": "Artwork quality",
    "weather_label": "Preview weather",
    "growth_stage_label": "Preview growth stage",
    "animation_label": "Motion amount",
    "particle_label": "Weather detail",
    "daily_goal_label": "Daily growth goal",
    "home_widget_label": "Show garden on home screens",
}


class GardenStudioWidget(QWidget):
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
        self.scene.setMinimumHeight(320)
        self._compact_layout: bool | None = None
        self._build_ui()
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

    def _build_ui(self) -> None:
        self.root_layout = QHBoxLayout(self)
        self.controls = QFrame()
        self.controls.setMaximumWidth(340)
        form = QFormLayout(self.controls)

        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName(STUDIO_TEXT["theme_label"])
        self.theme_combo.addItem("Verdant Dusk", "verdant_dusk")
        self.theme_combo.addItem("Morning Bloom", "verdant_dawn")
        self.theme_combo.addItem("Moonlit Study", "moonlit_study")
        current_theme = self._normalize_theme(str(self.config.value("visual_theme", "verdant_dusk")))
        theme_idx = max(0, self.theme_combo.findData(current_theme))
        self.theme_combo.setCurrentIndex(theme_idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        self.asset_quality_combo = QComboBox()
        self.asset_quality_combo.setAccessibleName(STUDIO_TEXT["asset_quality_label"])
        self.asset_quality_combo.addItem("Balanced", "balanced")
        self.asset_quality_combo.addItem("Performance", "performance")
        self.asset_quality_combo.addItem("Ultra", "ultra")
        current_quality = self.config.nested(
            "assets",
            "quality_preference",
            default=self.config.value("asset_quality", "balanced"),
        )
        idx = max(0, self.asset_quality_combo.findData(current_quality))
        self.asset_quality_combo.setCurrentIndex(idx)
        self.asset_quality_combo.currentIndexChanged.connect(self._apply_preview)

        self.animations_enabled = QCheckBox()
        self.animations_enabled.setAccessibleName(STUDIO_TEXT["animations_label"])
        self.animations_enabled.setChecked(
            bool(self.config.value("enable_animations", True))
            and not bool(self.config.value("reduced_motion", False))
        )
        self.animations_enabled.toggled.connect(self._apply_preview)
        self.animations_enabled.toggled.connect(self._update_motion_controls)

        self.daily_goal = QSpinBox()
        self.daily_goal.setAccessibleName(STUDIO_TEXT["daily_goal_label"])
        self.daily_goal.setRange(10, 2000)
        self.daily_goal.setSingleStep(10)
        self.daily_goal.setValue(int(self.config.value("daily_goal", 140)))

        self.show_home_widget = QCheckBox()
        self.show_home_widget.setAccessibleName(STUDIO_TEXT["home_widget_label"])
        self.show_home_widget.setChecked(bool(self.config.value("show_home_widget", True)))

        self.weather_combo = QComboBox()
        self.weather_combo.setAccessibleName(STUDIO_TEXT["weather_label"])
        for weather in ["breeze", "cloudy", "gentle_rain", "fireflies", "sunny"]:
            self.weather_combo.addItem(weather.replace("_", " ").title(), weather)
        self.weather_combo.currentIndexChanged.connect(self._on_preview_toggle)

        self.growth_stage_combo = QComboBox()
        self.growth_stage_combo.setAccessibleName(STUDIO_TEXT["growth_stage_label"])
        for stage in ["seed", "sprout", "young", "mature", "flowering", "rare"]:
            self.growth_stage_combo.addItem(stage.title(), stage)
        self.growth_stage_combo.setCurrentIndex(2)
        self.growth_stage_combo.currentIndexChanged.connect(self._on_preview_toggle)

        self.anim_slider = QSlider(Qt.Orientation.Horizontal)
        self.anim_slider.setAccessibleName(STUDIO_TEXT["animation_label"])
        self.anim_slider.setRange(0, 100)
        self.anim_slider.setValue(int(self.preview["animation_intensity"] * 100))
        self.anim_slider.valueChanged.connect(self._on_slider_changed)

        self.particle_slider = QSlider(Qt.Orientation.Horizontal)
        self.particle_slider.setAccessibleName(STUDIO_TEXT["particle_label"])
        self.particle_slider.setRange(20, 125)
        self.particle_slider.setValue(int(self.preview["weather_particle_density"] * 100))
        self.particle_slider.valueChanged.connect(self._on_slider_changed)

        form.addRow(STUDIO_TEXT["theme_label"], self.theme_combo)
        form.addRow(STUDIO_TEXT["asset_quality_label"], self.asset_quality_combo)
        form.addRow(STUDIO_TEXT["animations_label"], self.animations_enabled)
        form.addRow(STUDIO_TEXT["daily_goal_label"], self.daily_goal)
        form.addRow(STUDIO_TEXT["home_widget_label"], self.show_home_widget)
        form.addRow(STUDIO_TEXT["weather_label"], self.weather_combo)
        form.addRow(STUDIO_TEXT["growth_stage_label"], self.growth_stage_combo)
        self.anim_value = QLabel()
        self.anim_value.setAccessibleName("Motion amount value")
        anim_row = QHBoxLayout()
        anim_row.addWidget(self.anim_slider, 1)
        anim_row.addWidget(self.anim_value)
        self.particle_value = QLabel()
        self.particle_value.setAccessibleName("Weather detail value")
        particle_row = QHBoxLayout()
        particle_row.addWidget(self.particle_slider, 1)
        particle_row.addWidget(self.particle_value)
        form.addRow(STUDIO_TEXT["animation_label"], anim_row)
        form.addRow(STUDIO_TEXT["particle_label"], particle_row)

        self.root_layout.addWidget(self.controls, 0)
        self.root_layout.addWidget(self.scene, 1)
        self._update_slider_labels()
        self._update_motion_controls()
        self._apply_responsive_layout(self.width())

    def _apply_responsive_layout(self, width: int) -> None:
        compact = settings_layout_is_compact(width)
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self.root_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        self.controls.setMaximumWidth(16777215 if compact else 340)

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

    def _on_theme_changed(self) -> None:
        self.preview["theme"] = self._normalize_theme(str(self.theme_combo.currentData()))
        self._apply_preview()

    def _on_preview_toggle(self) -> None:
        self.preview["weather"] = str(self.weather_combo.currentData())
        self.preview["growth_stage"] = str(self.growth_stage_combo.currentData())
        self._apply_preview()

    def _on_slider_changed(self) -> None:
        self.preview["animation_intensity"] = self.anim_slider.value() / 100.0
        self.preview["weather_particle_density"] = self.particle_slider.value() / 100.0
        self._update_slider_labels()
        self._apply_preview()

    def _apply_preview(self) -> None:
        growth = 0.85 if self.preview["growth_stage"] in ("flowering", "rare") else 0.45
        if self.preview["growth_stage"] in ("seed", "sprout"):
            growth = 0.15
        quality = str(self.asset_quality_combo.currentData() or "balanced")
        asset_paths: dict[str, str | None] = {}
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
        preview_points = {
            "seed": 0, "sprout": 80, "young": 220,
            "mature": 480, "flowering": 900, "rare": 1400,
        }.get(str(self.preview["growth_stage"]), 0)
        preview_growth = growth_display(preview_points, self.preview["growth_stage"] == "rare")
        scene_payload = {
            "weather": self.preview["weather"],
            "growth": growth,
            "health": 0.85,
            "theme": self.preview["theme"],
            "animation_intensity": self.preview["animation_intensity"],
            "weather_particle_density": self.preview["weather_particle_density"],
            "motion_enabled": self.animations_enabled.isChecked(),
            "asset_paths": {
                "background": asset_paths.get("background"),
                "weather": asset_paths.get("weather"),
            },
            "plants": [
                {
                    "plant_id": f"preview-{species}",
                    "slot_index": slot_index,
                    "name": species.title(),
                    "species": species,
                    "stage": self.preview["growth_stage"],
                    "vitality": 0.95,
                    "health_label": "Thriving",
                    "growth_points": preview_points,
                    "next_stage": preview_growth.next_stage,
                    "stage_progress": preview_growth.progress,
                    "stage_points": preview_growth.stage_points,
                    "stage_goal": preview_growth.stage_goal,
                    "fully_grown": preview_growth.fully_grown,
                    "is_focus": slot_index == 0,
                    "asset": preview_assets.get(species) or (asset_paths.get("plant") if species == "rose" else None),
                }
                for slot_index, species in enumerate(("bonsai", "rose", "sunbloom"))
            ],
        }
        self.scene.set_scene(scene_payload)

    def build_theme_payload(self) -> dict[str, Any]:
        quality = str(self.asset_quality_combo.currentData())
        return {
            "visual_theme": self._normalize_theme(str(self.theme_combo.currentData())),
            "enable_animations": self.animations_enabled.isChecked(),
            "reduced_motion": not self.animations_enabled.isChecked(),
            "daily_goal": self.daily_goal.value(),
            "show_home_widget": self.show_home_widget.isChecked(),
            "assets": {
                "quality_preference": quality,
            },
            "theme_overrides": {
                "animation_intensity": self.anim_slider.value() / 100.0,
                "weather_particle_density": self.particle_slider.value() / 100.0,
            },
        }

    def _normalize_theme(self, theme: str) -> str:
        return {"morning_bloom": "verdant_dawn"}.get(str(theme), str(theme))
