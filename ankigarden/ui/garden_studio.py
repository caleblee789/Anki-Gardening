from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QSlider,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .scene import GardenSceneWidget

STUDIO_TEXT = {
    "preview_plant_name": "Preview Plant",
    "animations_label": "Animate garden",
    "theme_label": "Theme",
    "asset_quality_label": "Artwork quality",
    "weather_label": "Preview weather",
    "growth_stage_label": "Preview growth stage",
    "animation_label": "Motion amount",
    "particle_label": "Weather detail",
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
        self.scene = GardenSceneWidget()
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
        root = QHBoxLayout(self)
        controls = QFrame()
        controls.setMaximumWidth(340)
        form = QFormLayout(controls)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Verdant Dusk", "verdant_dusk")
        self.theme_combo.addItem("Morning Bloom", "verdant_dawn")
        self.theme_combo.addItem("Moonlit Study", "moonlit_study")
        current_theme = self._normalize_theme(str(self.config.value("visual_theme", "verdant_dusk")))
        theme_idx = max(0, self.theme_combo.findData(current_theme))
        self.theme_combo.setCurrentIndex(theme_idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        self.asset_quality_combo = QComboBox()
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
        self.animations_enabled.setChecked(
            bool(self.config.value("enable_animations", True))
            and not bool(self.config.value("reduced_motion", False))
        )
        self.animations_enabled.toggled.connect(self._apply_preview)

        self.weather_combo = QComboBox()
        for weather in ["breeze", "cloudy", "gentle_rain", "fireflies", "sunny"]:
            self.weather_combo.addItem(weather.replace("_", " ").title(), weather)
        self.weather_combo.currentIndexChanged.connect(self._on_preview_toggle)

        self.growth_stage_combo = QComboBox()
        for stage in ["seed", "sprout", "young", "mature", "flowering", "rare"]:
            self.growth_stage_combo.addItem(stage.title(), stage)
        self.growth_stage_combo.setCurrentIndex(2)
        self.growth_stage_combo.currentIndexChanged.connect(self._on_preview_toggle)

        self.anim_slider = QSlider(Qt.Orientation.Horizontal)
        self.anim_slider.setRange(0, 100)
        self.anim_slider.setValue(int(self.preview["animation_intensity"] * 100))
        self.anim_slider.valueChanged.connect(self._on_slider_changed)

        self.particle_slider = QSlider(Qt.Orientation.Horizontal)
        self.particle_slider.setRange(10, 200)
        self.particle_slider.setValue(int(self.preview["weather_particle_density"] * 100))
        self.particle_slider.valueChanged.connect(self._on_slider_changed)

        form.addRow(STUDIO_TEXT["theme_label"], self.theme_combo)
        form.addRow(STUDIO_TEXT["asset_quality_label"], self.asset_quality_combo)
        form.addRow(STUDIO_TEXT["animations_label"], self.animations_enabled)
        form.addRow(STUDIO_TEXT["weather_label"], self.weather_combo)
        form.addRow(STUDIO_TEXT["growth_stage_label"], self.growth_stage_combo)
        form.addRow(STUDIO_TEXT["animation_label"], self.anim_slider)
        form.addRow(STUDIO_TEXT["particle_label"], self.particle_slider)

        root.addWidget(controls, 0)
        root.addWidget(self.scene, 1)

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
