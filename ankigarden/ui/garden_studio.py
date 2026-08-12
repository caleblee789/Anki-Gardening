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
    QPixmap,
    QSizePolicy,
    QSlider,
    QToolButton,
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
    "theme_label": "Garden style",
    "asset_quality_label": "Artwork detail",
    "animation_label": "Weather motion",
    "particle_label": "Weather detail",
    "home_widget_label": "Show garden on home screens",
    "progress_notifications_label": "Show progress notifications",
}


def _describe_control(widget: QWidget, text: str) -> None:
    widget.setToolTip(text)
    widget.setAccessibleDescription(text)


class GardenStudioWidget(QWidget):
    """Responsive persistent settings and an explicitly non-saved preview."""

    persistentChanged = pyqtSignal()

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
        self.scene = GardenSceneWidget(interactive=False)
        self.scene.setMinimumHeight(230)
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
        self.setStyleSheet(
            "QLabel[settingsHeading='true'] { font-size:15px; font-weight:700; }"
            "QLabel[settingsNote='true'] { color:#aebfc3; font-size:12px; }"
            "QLabel[settingValue='true'] { color:#d9e7df; background:#17342e; border-radius:8px; padding:3px 7px; min-width:58px; }"
            "QFrame[settingsSection='true'] { border-top:1px solid rgba(130,160,168,.22); }"
            "QFrame[themeCard='true'] { background:#17342e; border:1px solid #4e7867; border-radius:10px; }"
            "QFrame[previewPanel='true'] { background:#0d211e; border:1px solid #345348; border-radius:12px; }"
            "QToolButton { color:#edf5ea; background:#152d28; border:1px solid #42675a; border-radius:9px; padding:7px 9px; font-weight:650; text-align:left; }"
            "QToolButton:hover { background:#1e3b34; border-color:#5b836f; }"
            "QToolButton:checked { background:#244c3d; border-color:#6d8e70; }"
            "QToolButton:focus { border:2px solid #e5f2a6; padding:6px 8px; }"
            "QComboBox { color:#edf5ea; background:#142c27; border:1px solid #42675a; border-radius:8px; padding:6px 28px 6px 8px; min-height:24px; }"
            "QComboBox:hover { border-color:#5b836f; }"
            "QComboBox:focus { border:2px solid #e5f2a6; padding:5px 27px 5px 7px; }"
            "QComboBox::drop-down { border:0; width:24px; }"
            "QComboBox QAbstractItemView { color:#edf5ea; background:#142c27; selection-background-color:#2d7653; border:1px solid #42675a; }"
            "QSlider::groove:horizontal { height:6px; background:#203d36; border-radius:3px; }"
            "QSlider::sub-page:horizontal { background:#58b77b; border-radius:3px; }"
            "QSlider::handle:horizontal { width:16px; height:16px; margin:-5px 0; background:#e5f2a6; border:2px solid #2d7653; border-radius:9px; }"
            "QSlider::handle:horizontal:hover { background:#f4f8cf; border-color:#58b77b; }"
            "QSlider:disabled { color:#74877d; }"
            "QCheckBox { color:#edf5ea; border:1px solid transparent; border-radius:5px; padding:2px; }"
            "QCheckBox:focus { border-color:#e5f2a6; }"
            "QCheckBox::indicator { width:17px; height:17px; background:#102622; border:1px solid #527563; border-radius:4px; }"
            "QCheckBox::indicator:hover { border-color:#78a189; }"
            "QCheckBox::indicator:checked { background:#58b77b; border:4px solid #17342e; }"
            "QCheckBox::indicator:disabled { background:#1c2a28; border-color:#344840; }"
        )
        self.root_layout = QHBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(18)
        self.controls = QFrame()
        self.controls.setMinimumWidth(270)
        self.controls.setMaximumWidth(360)
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

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
        self.theme_card.setAccessibleName("Current garden style: Verdant Twilight")
        theme_layout = QHBoxLayout(self.theme_card)
        theme_layout.setContentsMargins(12, 10, 12, 10)
        self.theme_thumbnail = QLabel()
        self.theme_thumbnail.setFixedSize(96, 54)
        self.theme_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_thumbnail.setAccessibleName("Verdant Twilight preview")
        self.theme_thumbnail.setStyleSheet("background:#0b2926; border-radius:7px;")
        theme_copy = QVBoxLayout()
        theme_title = QLabel("Verdant Twilight")
        theme_title.setProperty("settingsHeading", True)
        theme_note = QLabel("Current garden style")
        theme_note.setProperty("settingsNote", True)
        theme_copy.addWidget(theme_title)
        theme_copy.addWidget(theme_note)
        theme_layout.addWidget(self.theme_thumbnail)
        theme_layout.addLayout(theme_copy, 1)
        controls_layout.addWidget(self.theme_card)

        self.animations_enabled = QCheckBox()
        self.animations_enabled.setAccessibleName(STUDIO_TEXT["animations_label"])
        _describe_control(
            self.animations_enabled,
            "Turn all Garden weather motion on or off.",
        )
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

        motion, motion_form = self._section(
            "Motion",
            "Turn off garden motion when you prefer a quieter study screen.",
        )
        motion_form.addRow(STUDIO_TEXT["animations_label"], self.animations_enabled)
        # Weather motion is automatic and honors the saved reduced-motion
        # accessibility flag. It is no longer exposed as a visual loadout
        # control now that Weather is collectible. Give the hidden section an
        # explicit Qt parent so its preview controls stay alive without
        # mounting the retired section in the visible layout.
        motion.setParent(self.controls)
        motion.hide()

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
        integration, integration_form = self._section("Garden display")
        integration_form.addRow(STUDIO_TEXT["home_widget_label"], self.show_home_widget)
        integration_form.addRow(STUDIO_TEXT["progress_notifications_label"], self.show_progress_notifications)
        controls_layout.addWidget(integration)
        environment_note = QLabel(
            "Choose, equip, show, or hide collectible Weather and Scenery in "
            "House → Weather & Scenery."
        )
        environment_note.setWordWrap(True)
        environment_note.setProperty("settingsNote", True)
        controls_layout.addWidget(environment_note)

        self.fine_tune_toggle = QToolButton()
        self.fine_tune_toggle.setText("Fine tune")
        self.fine_tune_toggle.setCheckable(True)
        self.fine_tune_toggle.setChecked(False)
        self.fine_tune_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.fine_tune_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.fine_tune_toggle.setAccessibleName("Show fine-tune settings")
        self.fine_tune_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.fine_tune_toggle.setMinimumHeight(36)
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
        controls_layout.addStretch(1)

        self.preview_panel = QFrame()
        self.preview_panel.setProperty("previewPanel", True)
        self.preview_panel.setAccessibleName("Garden preview")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(5)
        preview_title = QLabel("Preview")
        preview_title.setProperty("settingsHeading", True)
        preview_note = QLabel("See how your plants and spaces will look before you save.")
        preview_note.setWordWrap(True)
        preview_note.setProperty("settingsNote", True)
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(preview_note)
        preview_layout.addWidget(self.scene, 1)

        self.root_layout.addWidget(self.controls, 0)
        self.root_layout.addWidget(self.preview_panel, 1)

        self.asset_quality_combo.currentIndexChanged.connect(self._on_persistent_preview_change)
        self.animations_enabled.toggled.connect(self._on_animation_toggled)
        self.animations_enabled.toggled.connect(self._update_motion_controls)
        self.show_home_widget.toggled.connect(self._on_persistent_change)
        self.show_progress_notifications.toggled.connect(self._on_persistent_change)
        self.fine_tune_toggle.toggled.connect(self._set_fine_tune_expanded)
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

    def _set_fine_tune_expanded(self, expanded: bool) -> None:
        self.fine_tune_section.setVisible(bool(expanded))
        self.fine_tune_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.fine_tune_toggle.setAccessibleName(
            "Hide fine-tune settings" if expanded else "Show fine-tune settings"
        )

    def collapse_preview_examples(self) -> None:
        """Compatibility hook used by the settings dialog when it is reopened."""
        self.fine_tune_toggle.setChecked(False)

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
            enabled = self._animation_flags[0] and not self._animation_flags[1]
            self.animations_enabled.setChecked(enabled)
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
        self.controls.setMaximumWidth(16777215 if compact else 360)

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

    def _on_animation_toggled(self, *_args: Any) -> None:
        if not self._loading_controls:
            self._animation_control_changed = True
        self._on_persistent_preview_change()

    def _on_slider_changed(self, key: str) -> None:
        if not self._loading_controls and key in self._override_control_changed:
            self._override_control_changed[key] = True
        self.preview["animation_intensity"] = self.anim_slider.value() / 100.0
        self.preview["weather_particle_density"] = self.particle_slider.value() / 100.0
        self._update_slider_labels()
        self._on_persistent_change()
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
        self.scene.set_scene({
            "weather": preview_weather,
            "growth": growth,
            "theme": self.preview["theme"],
            "animation_intensity": self.preview["animation_intensity"],
            "weather_particle_density": self.preview["weather_particle_density"],
            "motion_enabled": self.animations_enabled.isChecked(),
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
                self.animations_enabled.isChecked(),
                not self.animations_enabled.isChecked(),
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
