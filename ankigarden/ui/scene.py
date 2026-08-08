from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from aqt.qt import (
    QColor, QEvent, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRectF, QTimer, QToolButton, QToolTip, QWidget, Qt, pyqtSignal,
)

try:
    from aqt.qt import QSvgRenderer
except Exception:
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore[no-redef]
    except Exception:
        try:
            from PyQt5.QtSvg import QSvgRenderer  # type: ignore[no-redef]
        except Exception:
            QSvgRenderer = None  # type: ignore[assignment]

from .formatters import format_percent
from .plant_display import (
    PlantInteractionState,
    PlantPlacement,
    Rect,
    bed_badge_rect,
    move_badge_label,
    plant_layout,
    plant_layout_item,
    repair_unique_slot_items,
    requires_native_destination_selector,
    scene_profile_name,
    scene_surface_variant,
    smart_card_rect,
    theme_integration_profile,
)

SCENE_TEXT = {
    "live_garden_label": "Your garden",
    "fallback_message": (
        "We couldn't render the animated garden view.\n"
        "Your study progress, growth updates, and rewards are still being tracked."
    ),
}

STATS_HELP_TEXT = (
    "Learn how streaks, daily growth, and vitality are calculated."
)


class GardenSceneWidget(QWidget):
    nurtureRequested = pyqtSignal(str)
    placementRequested = pyqtSignal(str, int)
    storyRequested = pyqtSignal(str)
    cardOpened = pyqtSignal()
    selectionChanged = pyqtSignal(str)
    placementStateChanged = pyqtSignal(bool)
    cancelPlacementRequested = pyqtSignal()
    moveSessionRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, interactive: bool = True) -> None:
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.phase = 0.0
        self.scene: dict[str, Any] = {"plants": [], "weather": "breeze", "health": 0.7, "growth": 0.2}
        self._svg_cache: dict[str, Any] = {}
        self._raster_cache: dict[str, QPixmap] = {}
        self._graded_raster_cache: dict[tuple[str, str, str], QPixmap] = {}
        self._transition_started_at: float | None = None
        self._transition_duration = 1.4
        self._interaction = PlantInteractionState()
        self._plant_hit_rects: dict[str, QRectF] = {}
        self._plant_anchors: dict[str, tuple[float, float]] = {}
        self._card_rect: QRectF | None = None
        self._nurture_rect: QRectF | None = None
        self._health_rect: QRectF | None = None
        self._move_rect: QRectF | None = None
        self._story_rect: QRectF | None = None
        self._status_rect: QRectF | None = None
        self._stats_help_visible = False
        self._slot_placements: dict[int, PlantPlacement] = {}
        self._press_position: Any = None
        self._press_plant_id: str | None = None
        self._drag_started = False
        self._drag_position: Any = None
        self._inline_message = ""
        self._card_action_index = 0
        self.interactive = bool(interactive)
        self._stats_help_button = QToolButton(self)
        self._stats_help_button.setText("?")
        self._stats_help_button.setAccessibleName("About garden statistics")
        self._stats_help_button.setAccessibleDescription(STATS_HELP_TEXT)
        self._stats_help_button.setToolTip(STATS_HELP_TEXT)
        self._stats_help_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._stats_help_button.setFixedSize(24, 24)
        self._stats_help_button.setStyleSheet(
            "QToolButton { color:#e7f4e8; background:rgba(39,67,61,.92); border:1px solid rgba(226,239,222,.35); "
            "border-radius:12px; font-weight:700; } QToolButton:hover, QToolButton:focus { border-color:#e5f2a6; }"
        )
        self._stats_help_button.installEventFilter(self)
        self._stats_help_button.clicked.connect(self._focus_stats_help)
        self._stats_help_button.setVisible(self.interactive)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.interactive else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Interactive study garden" if self.interactive else "Garden preview")
        self.setAccessibleDescription(
            "Select a plant to open accessible garden actions."
            if self.interactive else "Preview only. This garden does not contain interactive controls."
        )
        self._hover_close_timer = QTimer(self)
        self._hover_close_timer.setSingleShot(True)
        self._hover_close_timer.setInterval(180)
        self._hover_close_timer.timeout.connect(self._clear_unpinned_hover)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(42)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        aspect = 4 / 3 if width < 620 else 16 / 9 if width < 1400 else 12 / 5
        return max(250, min(800, int(width / aspect)))

    def set_motion_enabled(self, enabled: bool) -> None:
        if enabled and not self.timer.isActive():
            self.timer.start(42)
        elif not enabled and self.timer.isActive():
            self.timer.stop()
        self.update()

    def hideEvent(self, event: Any) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: Any) -> None:
        if bool(self.scene.get("motion_enabled", True)):
            self.timer.start(42)
        super().showEvent(event)

    def set_scene(self, payload: dict[str, Any]) -> None:
        previous_ids = {
            str(item.get("plant_id"))
            for item in self.scene.get("stage_transitions", [])
            if isinstance(item, dict)
        }
        self.scene = self._sanitize_scene_payload(payload)
        self._interaction.reconcile(self._plant_ids())
        if not self.interactive:
            self._interaction.dismiss()
        transition_ids = {
            str(item.get("plant_id"))
            for item in self.scene.get("stage_transitions", [])
            if isinstance(item, dict)
        }
        if transition_ids and transition_ids != previous_ids:
            self._transition_started_at = time.monotonic()
            QTimer.singleShot(int(self._transition_duration * 1000), self._finish_stage_transition)
        self.update()

    def set_interactive(self, interactive: bool) -> None:
        self.interactive = bool(interactive)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.interactive else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Interactive study garden" if self.interactive else "Garden preview")
        self.setAccessibleDescription(
            "Select a plant to open accessible garden actions."
            if self.interactive else "Preview only. This garden does not contain interactive controls."
        )
        if not self.interactive:
            self._interaction.cancel_placement()
            self._interaction.dismiss()
            self._clear_hit_targets()
            self._stats_help_visible = False
        self._stats_help_button.setVisible(self.interactive)
        self.update()

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self._stats_help_button:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
                self._stats_help_visible = True
                self.update()
            elif event.type() == QEvent.Type.Leave and not self._stats_help_button.hasFocus():
                self._stats_help_visible = False
                self.update()
            elif event.type() == QEvent.Type.FocusOut and not self._stats_help_button.underMouse():
                self._stats_help_visible = False
                self.update()
        return super().eventFilter(watched, event)

    def _focus_stats_help(self) -> None:
        self._stats_help_button.setFocus(Qt.FocusReason.MouseFocusReason)
        self._stats_help_visible = True
        self.update()

    def _clear_hit_targets(self) -> None:
        self._plant_hit_rects.clear()
        self._plant_anchors.clear()
        self._slot_placements.clear()
        self._card_rect = self._nurture_rect = self._health_rect = None
        self._move_rect = self._story_rect = self._status_rect = None

    def begin_move(self, plant_id: str) -> bool:
        if not self.interactive:
            return False
        started = self._begin_move(plant_id, keyboard=True)
        if started:
            self.placementStateChanged.emit(True)
            self.setFocus()
            self.update()
        return started

    def cancel_move(self) -> None:
        self._interaction.cancel_placement()
        self._inline_message = "Move cancelled"
        self._finish_move_accessibility("Move cancelled. Plant selection remains available.")
        self.placementStateChanged.emit(False)
        self.cancelPlacementRequested.emit()
        self.update()

    def _finish_stage_transition(self) -> None:
        self._transition_started_at = None
        self.scene["stage_transitions"] = []
        self.update()

    def _coerce_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _sanitize_scene_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_scene = dict(payload or {})
        safe_scene["growth"] = self._clamp(self._coerce_float(safe_scene.get("growth", 0.0), 0.0), 0.0, 1.0)
        safe_scene["health"] = self._clamp(self._coerce_float(safe_scene.get("health", 0.7), 0.7), 0.0, 1.0)
        safe_scene["animation_intensity"] = self._clamp(
            self._coerce_float(safe_scene.get("animation_intensity", 0.7), 0.7), 0.1, 1.6
        )
        safe_scene["weather_particle_density"] = self._clamp(
            self._coerce_float(safe_scene.get("weather_particle_density", 1.0), 1.0), 0.2, 1.25
        )
        plants = safe_scene.get("plants", [])
        valid_plants = [plant for plant in plants if isinstance(plant, dict)] if isinstance(plants, list) else []
        safe_scene["plants"] = repair_unique_slot_items(valid_plants)
        transitions = safe_scene.get("stage_transitions", [])
        safe_scene["stage_transitions"] = transitions if isinstance(transitions, list) else []
        asset_paths = safe_scene.get("asset_paths", {})
        safe_scene["asset_paths"] = asset_paths if isinstance(asset_paths, dict) else {}
        safe_scene["motion_enabled"] = bool(safe_scene.get("motion_enabled", True))
        self.set_motion_enabled(safe_scene["motion_enabled"])
        return safe_scene

    def _tick(self) -> None:
        intensity = self._clamp(self._coerce_float(self.scene.get("animation_intensity", 0.7), 0.7), 0.1, 1.6)
        self.phase += 0.02 + (0.06 * intensity)
        self.update()

    def _plant_ids(self) -> list[str]:
        return [str(plant.get("plant_id", "")) for plant in self.scene.get("plants", []) if plant.get("plant_id")]

    def _plant_for_id(self, plant_id: str | None) -> dict[str, Any] | None:
        if not plant_id:
            return None
        for plant in self.scene.get("plants", []):
            if str(plant.get("plant_id", "")) == plant_id:
                return plant
        return None

    def active_plant_id(self) -> str | None:
        return self._interaction.pinned_id or self._interaction.focused_id(self._plant_ids())

    def keep_card_open(self, plant_id: str, message: str = "") -> None:
        if plant_id in self._plant_ids():
            self._interaction.pinned_id = plant_id
        self._inline_message = message
        self.update()

    def _layout_plants(self, width: float, height: float) -> list[tuple[dict[str, Any], PlantPlacement]]:
        plants = sorted(self.scene.get("plants", []), key=lambda row: int(row.get("slot_index", 0)))[:6]
        background = self.scene.get("asset_paths", {}).get("background", {})
        background_placement = background.get("placement", {}) if isinstance(background, dict) else {}
        by_slot = {int(plant.get("slot_index", index)): plant for index, plant in enumerate(plants)}
        slot_items: list[dict[str, Any]] = []
        for index in range(6):
            slot_items.append(plant_layout_item(by_slot.get(index, {}), index))
        rows = plant_layout(
            width,
            height,
            slot_items,
            background_placement if isinstance(background_placement, dict) else None,
            composition_count=max(1, len(plants)),
            protected_status=bool(self.scene.get("show_status_overlay", True)),
            reserve_move_controls=self.width() >= 900,
        )
        result: list[tuple[dict[str, Any], PlantPlacement]] = []
        self._plant_hit_rects = {}
        self._plant_anchors = {}
        self._slot_placements = {row.slot_index: row for row in rows}
        for row in rows:
            plant = by_slot.get(row.slot_index, {})
            plant_id = str(plant.get("plant_id", ""))
            hit_rect = QRectF(row.hit.x, row.hit.y, row.hit.width, row.hit.height)
            if plant_id:
                self._plant_hit_rects[plant_id] = hit_rect
                self._plant_anchors[plant_id] = (row.smart_card_anchor.x + row.smart_card_anchor.width / 2, row.smart_card_anchor.y)
            if plant_id:
                result.append((plant, row))
        return result

    def uses_native_destination_selector(self) -> bool:
        """Return whether accessible in-scene destinations fit this composition."""
        rows = [layout for _plant, layout in self._layout_plants(self.width(), self.height())]
        occupied = {
            int(plant.get("slot_index", -1))
            for plant in self.scene.get("plants", [])
        }
        return requires_native_destination_selector(rows, self.width(), self.height(), occupied)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        try:
            sky = QLinearGradient(0, 0, 0, r.height())
            health = self._clamp(self._coerce_float(self.scene.get("health", 0.7), 0.7), 0.0, 1.0)
            glow = min(255, 90 + int(120 * health))
            night = bool(self.scene.get("night_mode", False))
            if night:
                sky.setColorAt(0.0, QColor(11, 18, 38))
                sky.setColorAt(0.55, QColor(20, 38, 64))
                sky.setColorAt(1.0, QColor(12, 24, 30))
            else:
                sky.setColorAt(0.0, QColor(18, 26, 46))
                sky.setColorAt(0.55, QColor(27, 60, 72))
                sky.setColorAt(1.0, QColor(16, 30, 26))
            painter.fillRect(r, sky)
            background_drawn = self._draw_background_asset(painter, r)
            growth = self._clamp(self._coerce_float(self.scene.get("growth", 0.0), 0.0), 0.0, 1.0)

            if not background_drawn:
                sun_x = r.width() * (0.75 + 0.02 * math.sin(self.phase / 4))
                sun_y = r.height() * 0.2
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 220, 130, 95 if self.scene.get("weather") != "cloudy" else 35))
                painter.drawEllipse(QRectF(sun_x - 55, sun_y - 55, 110, 110))
                painter.setBrush(QColor(150, 255, 170, int(18 + growth * 40)))
                painter.drawEllipse(QRectF(sun_x - 80, sun_y - 80, 160, 160))

                ground = QLinearGradient(0, r.height() * 0.56, 0, r.height())
                ground.setColorAt(0.0, QColor(45, 90, 54))
                ground.setColorAt(1.0, QColor(26, 54, 32))
                painter.setBrush(ground)
                painter.drawRoundedRect(QRectF(0, r.height() * 0.56, r.width(), r.height() * 0.44), 0, 0)
            # Runtime soil is resolved from the same six PlantPlacement rows as
            # artwork and interaction. The historical overlay remains packaged
            # only as a fallback; its static dark holes are not composited.
            self._draw_decoration_asset(painter, r)

            plants = self.scene.get("plants", [])
            plant_rows = self._layout_plants(r.width(), r.height())
            self._draw_physical_beds(painter)
            focused_id = self._interaction.focused_id(self._plant_ids()) if self.hasFocus() else None
            dragged_rows = [row for row in plant_rows if str(row[0].get("plant_id", "")) == self._interaction.dragged_id and self._drag_started]
            plant_rows = [row for row in plant_rows if row not in dragged_rows] + dragged_rows
            for idx, (plant, layout) in enumerate(plant_rows):
                x = layout.footprint.x + layout.footprint.width / 2
                base_y = layout.depth
                plant_id = str(plant.get("plant_id", ""))
                selected = plant_id in {self._interaction.pinned_id, focused_id}
                hovered = plant_id == self._interaction.hovered_id
                transition = self._transition_for_plant(plant)
                painter.save()
                if self._interaction.placing and plant_id != self._interaction.dragged_id:
                    painter.setOpacity(0.72)
                if plant_id == self._interaction.dragged_id and self._drag_started:
                    painter.setOpacity(0.78)
                    target_x, target_y = x, base_y
                    destination = self._interaction.destination_slot
                    target = self._slot_placements.get(destination) if destination is not None else None
                    if target is not None:
                        target_x = target.footprint.x + target.footprint.width / 2
                        target_y = target.depth
                    elif self._drag_position is not None:
                        target_x, target_y = self._drag_position.x(), self._drag_position.y()
                    painter.translate(target_x - x, target_y - base_y)
                if transition:
                    self._draw_transition_glow(painter, layout, transition)
                self._draw_plant_footprint(painter, layout, plant, selected=selected, hovered=hovered)
                asset_drawn = self._draw_plant_asset(painter, layout, plant)
                if not asset_drawn:
                    self._draw_plant(painter, x, base_y, plant, idx)
                if selected:
                    self._draw_selected_vessel_edge(painter, layout)
                if str(self._plant_placement(plant).get("base_type", "legacy")) == "legacy":
                    self._draw_foreground_growth(painter, x, base_y, idx, selected)
                painter.restore()

            # Registered terrace lips and paving debris sit in front of only
            # the final few pixels of each support, creating real occlusion.
            self._draw_surface_occlusion_asset(painter, r)

            weather = self.scene.get("weather", "breeze")
            weather_overlay_drawn = self._draw_weather_asset(painter, r)
            density = self._clamp(self._coerce_float(self.scene.get("weather_particle_density", 1.0), 1.0), 0.2, 1.25)
            if weather_overlay_drawn:
                density *= 0.55
            if bool(self.scene.get("motion_enabled", True)):
                self._draw_weather_motion(painter, r, str(weather), density)

            self._draw_slot_placeholders(painter)
            self._draw_status_overlay(painter, r, growth, glow)
            if self._stats_help_visible:
                self._draw_stats_help(painter, r)
            # Selected-plant details and real keyboard-focusable actions live in
            # the compact Qt action bar immediately below this canvas.
            self._card_rect = self._nurture_rect = self._move_rect = self._story_rect = None
        except Exception:
            self._clear_hit_targets()
            self._draw_fallback_scene(painter, r)

    def _draw_status_overlay(self, painter: QPainter, rect: Any, growth: float, glow: int) -> None:
        if not bool(self.scene.get("show_status_overlay", True)) or rect.width() < 520:
            self._status_rect = None
            self._stats_help_button.hide()
            return
        self._stats_help_button.setVisible(self.interactive)
        goal_label = "Daily goal complete" if growth >= 1.0 else f"{format_percent(growth)} daily goal"
        labels = [
            f"{max(0, int(self._coerce_float(self.scene.get('streak_days', 0), 0)))} day streak",
            goal_label,
            f"{format_percent(self.scene.get('health', 0.0))} vitality",
        ]
        panel_width = min(430.0, max(1.0, rect.width() - 32.0))
        narrow = rect.width() < 440
        panel_height = 78 if narrow else 68
        panel = QRectF(16, 14, panel_width, panel_height)
        self._status_rect = panel
        help_x = int(panel.right() - 38)
        help_y = int(panel.top() + 10)
        self._stats_help_button.setGeometry(help_x, help_y, 24, 24)
        painter.save()
        painter.setPen(QPen(QColor(207, 226, 211, 82), 1.0))
        painter.setBrush(QColor(10, 24, 21, 188))
        painter.drawRoundedRect(panel, 12, 12)
        painter.setPen(QPen(QColor(4, 10, 9, 110), 1))
        painter.drawRoundedRect(panel.adjusted(2, 2, -2, -2), 10, 10)
        painter.setPen(QColor(235, 248, 232, glow))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        content_left = panel.left() + 16
        text_right = panel.right() - 48
        painter.drawText(
            QRectF(content_left, panel.top() + 6, max(1.0, text_right - content_left), 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            SCENE_TEXT["live_garden_label"],
        )
        font.setBold(False)
        font.setPointSize(max(10, font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(QColor(205, 225, 211))
        available_width = max(1, int(text_right - content_left))
        painter.drawText(
            QRectF(content_left, panel.top() + 29, available_width, panel.height() - 34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            "  ·  ".join(labels),
        )
        painter.restore()

    def _draw_stats_help(self, painter: QPainter, rect: Any) -> None:
        if self._status_rect is None:
            return
        width = min(390.0, max(180.0, rect.width() - 32.0))
        panel = QRectF(16, self._status_rect.bottom() + 8, width, 60)
        painter.save()
        painter.setPen(QPen(QColor(226, 239, 222, 92), 1))
        painter.setBrush(QColor(9, 22, 20, 236))
        painter.drawRoundedRect(panel, 10, 10)
        painter.setPen(QColor(225, 240, 228))
        painter.drawText(
            panel.adjusted(12, 8, -12, -8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            STATS_HELP_TEXT,
        )
        painter.restore()

    def _plant_placement(self, plant: dict[str, Any]) -> dict[str, Any]:
        asset = plant.get("asset")
        placement = asset.get("placement", {}) if isinstance(asset, dict) else {}
        return placement if isinstance(placement, dict) else {}

    def _draw_plant_footprint(
        self, painter: QPainter, layout: PlantPlacement, plant: dict[str, Any], *, selected: bool, hovered: bool
    ) -> None:
        base_type = str(self._plant_placement(plant).get("base_type", "legacy"))
        painter.save()
        footprint = QRectF(layout.footprint.x, layout.footprint.y, layout.footprint.width, layout.footprint.height)
        if selected:
            arc = QPainterPath()
            left = footprint.left() - 7
            right = footprint.right() + 7
            baseline = layout.depth + footprint.height() * .18
            arc.moveTo(left, baseline)
            arc.cubicTo(
                left + footprint.width() * .22, baseline + footprint.height() * .55,
                right - footprint.width() * .28, baseline + footprint.height() * .42,
                right, baseline - footprint.height() * .08,
            )
            painter.setPen(QPen(QColor(218, 178, 102, 72), 2.0, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(arc)
            inner = QPainterPath()
            inner.moveTo(left + footprint.width() * .08, baseline - footprint.height() * .02)
            inner.cubicTo(
                left + footprint.width() * .30, baseline + footprint.height() * .36,
                right - footprint.width() * .32, baseline + footprint.height() * .31,
                right - footprint.width() * .07, baseline - footprint.height() * .10,
            )
            painter.setPen(QPen(QColor(239, 190, 98, 105), 1.5, Qt.PenStyle.SolidLine))
            painter.drawPath(inner)
            if self.hasFocus():
                painter.setPen(QPen(QColor(229, 242, 166, 175), 1.2, Qt.PenStyle.DashLine))
                painter.drawPath(arc)
        painter.setPen(Qt.PenStyle.NoPen)
        base = QRectF(layout.base_rect.x, layout.base_rect.y, layout.base_rect.width, layout.base_rect.height)
        support = QRectF(layout.support_rect.x, layout.support_rect.y, layout.support_rect.width, layout.support_rect.height)
        shadow_width = max(5.0, min(support.width() * .82, footprint.width()))
        shadow_height = max(3.0, min(shadow_width * .12, footprint.height()))
        contact_x = support.center().x() - shadow_width * .55
        contact_y = layout.depth - shadow_height * .38
        # Layered asymmetric lobes form one soft contact shadow with a subtle
        # lower-left bias, matching the paintings' upper-right light.
        base_alpha = max(0, min(255, int(round(layout.shadow_opacity * 255))))
        for spread, alpha_factor in ((1.24, .34), (1.06, .58), (.82, 1.0)):
            width = shadow_width * spread
            height = shadow_height * spread
            left = contact_x - (width - shadow_width) * .62
            top = contact_y - (height - shadow_height) * .45
            path = QPainterPath()
            path.moveTo(left, top + height * .55)
            path.cubicTo(
                left + width * .12, top + height * .08,
                left + width * .72, top,
                left + width, top + height * .42,
            )
            path.cubicTo(
                left + width * .86, top + height,
                left + width * .20, top + height * .96,
                left, top + height * .55,
            )
            painter.setBrush(QColor(83, 57, 38, int(base_alpha * alpha_factor)))
            painter.drawPath(path)
        if base_type == "legacy":
            soil = QRectF(footprint.x() + footprint.width() * .12, footprint.y(), footprint.width() * .76, footprint.height() * .72)
            painter.setBrush(QColor(72, 55, 39, 142))
            painter.drawEllipse(soil)
        painter.restore()

    def _draw_foreground_growth(self, painter: QPainter, x: float, base_y: float, index: int, emphasized: bool) -> None:
        painter.save()
        painter.setPen(QPen(QColor(63, 112, 63, 215), 2.0))
        for offset in (-39, -29, 31, 42):
            lean = -5 if (index + int(offset)) % 2 else 5
            painter.drawLine(int(x + offset), int(base_y + 4), int(x + offset + lean), int(base_y - 11 - abs(offset) % 6))
        if emphasized:
            painter.setPen(QPen(QColor(174, 221, 135, 210), 1.5))
            painter.drawLine(int(x - 34), int(base_y + 2), int(x - 39), int(base_y - 12))
            painter.drawLine(int(x + 36), int(base_y + 2), int(x + 41), int(base_y - 13))
        painter.restore()

    def _draw_smart_card(self, painter: QPainter, rect: Any) -> None:
        plant_id = self._interaction.pinned_id
        plant = self._plant_for_id(plant_id)
        anchor = self._plant_anchors.get(plant_id or "")
        if plant is None or anchor is None:
            self._card_rect = None
            self._nurture_rect = None
            self._health_rect = None
            self._move_rect = None
            self._story_rect = None
            return
        obstacles = [
            Rect(hit.x(), hit.y(), hit.width(), hit.height())
            for obstacle_id, hit in self._plant_hit_rects.items()
            if obstacle_id != plant_id
        ]
        panel_width = min(470.0, max(1.0, rect.width() - 32.0))
        obstacles.append(Rect(16.0, 14.0, panel_width, 78.0 if panel_width < 390 else 62.0))
        background = self.scene.get("asset_paths", {}).get("background", {})
        placement = background.get("placement", {}) if isinstance(background, dict) else {}
        zone = placement.get("planting_zone", {}) if isinstance(placement, dict) else {}
        planting_top = rect.height() * float(zone.get("far_y", 0.62)) if isinstance(zone, dict) else rect.height() * 0.62
        x, y, width, height = smart_card_rect(
            rect.width(), rect.height(), anchor[0], anchor[1], card_width=340.0, card_height=236.0,
            obstacles=obstacles, planting_top=planting_top
        )
        card = QRectF(x, y, width, height)
        self._card_rect = card
        painter.save()
        painter.setPen(QPen(QColor(119, 151, 126, 225), 1.4))
        painter.setBrush(QColor(18, 32, 32, 242))
        painter.drawRoundedRect(card, 14, 14)
        left = card.left() + 16
        top = card.top() + 24
        name = str(plant.get("name") or plant.get("species") or "Plant")
        species = str(plant.get("species") or "Plant").title()
        stage = str(plant.get("stage") or "Seed").title()
        rare = bool(plant.get("rare_variant")) or stage.lower() == "rare"
        painter.setPen(QColor(241, 249, 230))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(11, font.pointSize() + 1))
        painter.setFont(font)
        text_width = max(1, int(card.width() - 32))
        painter.drawText(
            int(left), int(top),
            painter.fontMetrics().elidedText(f"{name}  {'✦' if rare else ''}", Qt.TextElideMode.ElideRight, text_width),
        )
        font.setBold(False)
        font.setPointSize(max(9, font.pointSize() - 2))
        painter.setFont(font)
        painter.setPen(QColor(183, 207, 194))
        painter.drawText(
            int(left), int(top + 24),
            painter.fontMetrics().elidedText(f"{species} • {stage}", Qt.TextElideMode.ElideRight, text_width),
        )
        vitality = int(round(self._clamp(self._coerce_float(plant.get("vitality", 0.0), 0.0), 0.0, 1.0) * 100))
        health_label = str(plant.get("health_label") or ("Thriving" if vitality >= 85 else "Healthy" if vitality >= 65 else "Needs care"))
        painter.setPen(QColor(222, 235, 221))
        self._health_rect = QRectF(left, top + 35, card.width() - 32, 22)
        painter.drawText(
            int(left), int(top + 51),
            painter.fontMetrics().elidedText(
                f"Plant vitality: {health_label} ({vitality}%)", Qt.TextElideMode.ElideRight, text_width
            ),
        )
        bar = QRectF(left, top + 66, card.width() - 32, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(42, 62, 58))
        painter.drawRoundedRect(bar, 6, 6)
        progress = self._clamp(self._coerce_float(plant.get("stage_progress", 1.0), 1.0), 0.0, 1.0)
        painter.setBrush(QColor(92, 190, 123))
        painter.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * progress, bar.height()), 6, 6)
        painter.setPen(QColor(214, 231, 209))
        if plant.get("fully_grown"):
            status = "Fully grown"
        else:
            next_stage = str(plant.get("next_stage") or "next stage").title()
            stage_points = max(0, int(self._coerce_float(plant.get("stage_points", 0), 0)))
            stage_goal = max(1, int(self._coerce_float(plant.get("stage_goal", 1), 1)))
            status = f"{stage_points} of {stage_goal} growth points toward {next_stage}"
        painter.drawText(
            int(left), int(top + 101),
            painter.fontMetrics().elidedText(status, Qt.TextElideMode.ElideRight, text_width),
        )
        painter.setPen(QColor(151, 181, 163))
        hint = self._inline_message or (
            "Currently nurturing • receives 80% of review growth"
            if plant.get("is_focus") else "Review cards to earn growth"
        )
        painter.drawText(
            int(left), int(top + 127),
            painter.fontMetrics().elidedText(hint, Qt.TextElideMode.ElideRight, text_width),
        )
        # Actions live in PlantActionPanel as real Qt controls. The painted card
        # is deliberately informational so it never impersonates a button.
        self._nurture_rect = self._move_rect = self._story_rect = None
        painter.restore()

    def _draw_physical_beds(self, painter: QPainter) -> None:
        """Paint theme-aware empty, occupied, and locked soil from resolved slots."""
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", 0))))
        occupied = {int(plant.get("slot_index", -1)) for plant in self.scene.get("plants", [])}
        for slot, layout in self._slot_placements.items():
            bed = QRectF(
                layout.bed_footprint.x,
                layout.bed_footprint.y,
                layout.bed_footprint.width,
                layout.bed_footprint.height,
            )
            locked = slot >= unlocked
            is_occupied = slot in occupied
            painter.save()
            if locked:
                painter.restore()
                continue
            if is_occupied:
                painter.restore()
                continue
            painter.setPen(QPen(QColor(151, 101, 61, 76), 1.0))
            painter.setBrush(QColor(119, 78, 47, 98))
            path = QPainterPath()
            path.moveTo(bed.left(), bed.center().y())
            path.cubicTo(
                bed.left() + bed.width() * .08, bed.top(),
                bed.left() + bed.width() * .76, bed.top() + bed.height() * .04,
                bed.right(), bed.center().y() + bed.height() * .03,
            )
            path.cubicTo(
                bed.left() + bed.width() * .90, bed.bottom(),
                bed.left() + bed.width() * .17, bed.bottom() - bed.height() * .02,
                bed.left(), bed.center().y(),
            )
            painter.drawPath(path)
            painter.setPen(QPen(QColor(201, 147, 83, 34), 1))
            for factor in (0.26, 0.52, 0.74):
                painter.drawPoint(int(bed.left() + bed.width() * factor), int(bed.center().y()))
            painter.restore()

    def _draw_slot_placeholders(self, painter: QPainter) -> None:
        if not self._interaction.placing:
            return
        occupied = {int(plant.get("slot_index", -1)) for plant in self.scene.get("plants", [])}
        if requires_native_destination_selector(
            self._slot_placements.values(), self.width(), self.height(), occupied
        ):
            return
        occupant_names = {
            int(plant.get("slot_index", -1)): str(plant.get("name") or plant.get("species") or "plant")
            for plant in self.scene.get("plants", [])
        }
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", len(occupied)))))
        origin = self._interaction.drag_origin_slot
        placed_badges: list[Rect] = []
        obstacle_rows = [
            (int(plant.get("slot_index", -1)), layout.visible.expanded(4.0, 3.0))
            for plant, layout in self._layout_plants(self.width(), self.height())
        ]
        for slot, layout in self._slot_placements.items():
            label, state = move_badge_label(
                slot,
                origin_slot=origin,
                destination_slot=self._interaction.destination_slot,
                unlocked_slots=unlocked,
                occupied_slots=occupied,
                occupant_names=occupant_names,
            )
            visual_label = str(slot + 1)
            active = state == "active"
            locked = state == "locked"
            current = state == "current"
            footprint = QRectF(
                layout.bed_footprint.x,
                layout.bed_footprint.y,
                layout.bed_footprint.width,
                layout.bed_footprint.height,
            )
            painter.save()
            if locked:
                pen_color, fill_color = QColor(145, 156, 153, 62), QColor(35, 42, 42, 48)
            elif current:
                pen_color, fill_color = QColor(126, 190, 201, 118), QColor(49, 93, 101, 48)
            else:
                pen_color = QColor(229, 242, 166, 235 if active else 92)
                fill_color = QColor(111, 88, 49, 150 if active else 42)
            painter.setPen(QPen(pen_color, 2.4 if active and not locked else 1))
            painter.setBrush(fill_color)
            painter.drawEllipse(footprint.adjusted(-6, -3, 6, 3))
            if self.width() < 380 and not (active or current):
                painter.restore()
                continue
            obstacles = [obstacle for _obstacle_slot, obstacle in obstacle_rows] + placed_badges
            badge = bed_badge_rect(layout, visual_label, self.width(), self.height(), obstacles)
            placed_badges.append(badge)
            badge_rect = QRectF(badge.x, badge.y, badge.width, badge.height)
            if locked:
                badge_pen = QColor(158, 169, 164, 70)
                badge_fill = QColor(26, 34, 33, 138)
                badge_text = QColor(195, 205, 201, 112)
            elif active:
                badge_pen = QColor(239, 247, 184, 235)
                badge_fill = QColor(50, 78, 47, 232)
                badge_text = QColor(250, 253, 223)
            elif current:
                badge_pen = QColor(164, 211, 219, 126)
                badge_fill = QColor(32, 63, 69, 188)
                badge_text = QColor(222, 244, 246, 205)
            else:
                badge_pen = QColor(222, 231, 188, 82)
                badge_fill = QColor(29, 43, 35, 166)
                badge_text = QColor(228, 235, 213, 178)
            painter.setPen(QPen(badge_pen, 1))
            painter.setBrush(badge_fill)
            painter.drawRoundedRect(badge_rect, 10, 10)
            painter.setPen(badge_text)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, visual_label)
            painter.restore()

    def _event_position(self, event: Any) -> Any:
        return event.position() if hasattr(event, "position") else event.pos()

    def _plant_at(self, position: Any) -> str | None:
        for plant_id, hit_rect in reversed(list(self._plant_hit_rects.items())):
            if hit_rect.contains(position):
                return plant_id
        return None

    def _slot_at(self, position: Any) -> int | None:
        for slot, layout in self._slot_placements.items():
            target = QRectF(
                layout.bed_footprint.x,
                layout.bed_footprint.y,
                layout.bed_footprint.width,
                layout.bed_footprint.height,
            ).adjusted(-14, -10, 14, 12)
            if target.contains(position):
                return slot
        return None

    def _slot_for_plant(self, plant_id: str) -> int | None:
        plant = self._plant_for_id(plant_id)
        return int(plant.get("slot_index")) if plant is not None else None

    def _valid_slots(self) -> list[int]:
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", 0))))
        return [slot for slot in sorted(self._slot_placements) if slot < unlocked]

    def _destination_slots(self) -> list[int]:
        origin = self._interaction.drag_origin_slot
        return [slot for slot in self._valid_slots() if slot != origin]

    def _cycle_destination(self, direction: int) -> int | None:
        destination = self._interaction.cycle_destination(self._valid_slots(), direction)
        if destination == self._interaction.drag_origin_slot and self._destination_slots():
            destination = self._interaction.cycle_destination(self._valid_slots(), direction)
        self._announce_destination(destination)
        return destination

    def _announce_destination(self, slot: int | None) -> None:
        if slot is None:
            return
        occupied = {
            int(plant.get("slot_index", -1))
            for plant in self.scene.get("plants", [])
        }
        occupant_names = {
            int(plant.get("slot_index", -1)): str(plant.get("name") or plant.get("species") or "plant")
            for plant in self.scene.get("plants", [])
        }
        label, _state = move_badge_label(
            slot,
            origin_slot=self._interaction.drag_origin_slot,
            destination_slot=slot,
            unlocked_slots=int(self.scene.get("unlocked_slots", 0)),
            occupied_slots=occupied,
            occupant_names=occupant_names,
        )
        self.setAccessibleName(f"Bed {slot + 1}: {label}")
        self.setAccessibleDescription(
            f"Bed {slot + 1} selected. Press Enter to {label.lower()} this plant, "
            "or Escape to cancel."
        )

    def _finish_move_accessibility(self, message: str) -> None:
        self.setAccessibleName("Interactive study garden")
        self.setAccessibleDescription(message)

    def _begin_move(self, plant_id: str, *, keyboard: bool) -> bool:
        origin = self._slot_for_plant(plant_id)
        if origin is None:
            return False
        started = self._interaction.begin_placement(plant_id, origin, self._valid_slots(), keyboard=keyboard)
        if started:
            name = self._plant_for_id(plant_id).get("name", "plant")
            self._inline_message = f"Moving {name}. Choose a new location."
            self.setAccessibleName(f"Moving {name}. Choose a new location.")
            self.setAccessibleDescription(
                "Six fixed garden beds are shown. Unlocked open or occupied beds can be selected; "
                "locked beds cannot. Use arrow keys and Enter, click a bed, or drag the plant."
            )
        return started

    def _clear_unpinned_hover(self) -> None:
        if self._interaction.pinned_id is None:
            self._interaction.hover(None)
            self.unsetCursor()
            self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        if not self.interactive:
            super().mouseMoveEvent(event)
            return
        position = self._event_position(event)
        if self._interaction.placing:
            hover_slot = self._slot_at(position)
            unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", 0))))
            if hover_slot is not None and hover_slot >= unlocked:
                QToolTip.showText(
                    self.mapToGlobal(position.toPoint()),
                    "This garden space has not been unlocked yet.",
                    self,
                )
            else:
                QToolTip.hideText()
        if self._press_plant_id and self._press_position is not None:
            delta = position - self._press_position
            if not self._drag_started and (abs(delta.x()) + abs(delta.y())) >= 8:
                if not self._interaction.placing:
                    self.moveSessionRequested.emit(self._press_plant_id)
                self._drag_started = self._interaction.placing
                if self._drag_started:
                    self._interaction.move_mode = False
            if self._drag_started:
                self._drag_position = position
                slot = self._slot_at(position)
                valid = slot in self._destination_slots() if slot is not None else False
                if valid and self._interaction.choose_destination(slot, self._destination_slots()):
                    self._announce_destination(slot)
                self.setCursor(Qt.CursorShape.ClosedHandCursor if valid else Qt.CursorShape.ForbiddenCursor)
                self.update()
                return
        plant_id = self._plant_at(position)
        over_card = self._card_rect is not None and self._card_rect.contains(position)
        if plant_id:
            self._hover_close_timer.stop()
            self._interaction.hover(plant_id)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()
        elif over_card:
            self._hover_close_timer.stop()
            self.unsetCursor()
        elif self._interaction.pinned_id is None:
            self._hover_close_timer.start()
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if self._interaction.pinned_id is None:
            self._hover_close_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event: Any) -> None:
        if not self.interactive or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = self._event_position(event)
        if self._interaction.placing and not self._drag_started:
            slot = self._slot_at(position)
            if slot is not None:
                if self._interaction.choose_destination(slot, self._destination_slots()):
                    self._announce_destination(slot)
                    occupied = {
                        int(plant.get("slot_index", -1))
                        for plant in self.scene.get("plants", [])
                    }
                    occupant_names = {
                        int(plant.get("slot_index", -1)): str(plant.get("name") or plant.get("species") or "plant")
                        for plant in self.scene.get("plants", [])
                    }
                    label, _state = move_badge_label(
                        slot,
                        origin_slot=self._interaction.drag_origin_slot,
                        destination_slot=slot,
                        unlocked_slots=int(self.scene.get("unlocked_slots", 0)),
                        occupied_slots=occupied,
                        occupant_names=occupant_names,
                    )
                    request = self._interaction.complete_placement()
                    self._finish_move_accessibility(
                        f"{label} requested for bed {slot + 1}. Undo remains available after placement."
                    )
                    self.placementStateChanged.emit(False)
                    if request is not None and request[1] != self._slot_for_plant(request[0]):
                        self.placementRequested.emit(request[0], request[1])
                    else:
                        self._inline_message = "That plant is already in this space"
                else:
                    self._inline_message = "That garden space is locked"
                self.update()
                return
        if self._nurture_rect is not None and self._nurture_rect.contains(position) and self._interaction.pinned_id:
            plant = self._plant_for_id(self._interaction.pinned_id)
            if plant is not None and not plant.get("is_focus"):
                self.nurtureRequested.emit(self._interaction.pinned_id)
            return
        if self._move_rect is not None and self._move_rect.contains(position) and self._interaction.pinned_id:
            self._begin_move(self._interaction.pinned_id, keyboard=True)
            self.update()
            return
        if self._story_rect is not None and self._story_rect.contains(position) and self._interaction.pinned_id:
            self.storyRequested.emit(self._interaction.pinned_id)
            return
        plant_id = self._plant_at(position)
        if plant_id:
            self._press_position = position
            self._press_plant_id = plant_id
            self._drag_started = False
            self.setFocus()
        elif self._card_rect is None or not self._card_rect.contains(position):
            self._interaction.cancel_placement()
            self._interaction.dismiss()
            self._inline_message = ""
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if not self.interactive or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        position = self._event_position(event)
        if self._drag_started:
            slot = self._slot_at(position)
            if slot is not None:
                if self._interaction.choose_destination(slot, self._destination_slots()):
                    self._announce_destination(slot)
            request = self._interaction.complete_placement() if slot is not None else None
            self._finish_move_accessibility(
                "Plant placement requested. Undo remains available after placement."
                if request is not None
                else "Move cancelled. Plant selection remains available."
            )
            if request is not None and request[1] != self._slot_for_plant(request[0]):
                self.placementRequested.emit(request[0], request[1])
            else:
                self._inline_message = "Move cancelled"
                self.cancelPlacementRequested.emit()
            self.unsetCursor()
            self.placementStateChanged.emit(False)
        elif self._press_plant_id:
            plant_id = self._plant_at(position)
            if plant_id == self._press_plant_id:
                was_pinned = self._interaction.pinned_id == plant_id
                self._interaction.toggle_pin(plant_id)
                self._inline_message = ""
                ids = self._plant_ids()
                if plant_id in ids:
                    self._interaction.focused_index = ids.index(plant_id)
                if not was_pinned and self._interaction.pinned_id:
                    self._card_action_index = 0
                    self.setAccessibleDescription(
                        "Plant selected. Use Tab to reach Nurture, Move, and Story below the garden."
                    )
                    self.cardOpened.emit()
                self.selectionChanged.emit(self._interaction.pinned_id or "")
        self._press_position = None
        self._press_plant_id = None
        self._drag_started = False
        self._drag_position = None
        self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if not self.interactive:
            super().keyPressEvent(event)
            return
        plant_ids = self._plant_ids()
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            super().keyPressEvent(event)
            self.update()
            return
        if self._interaction.move_mode:
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                self._cycle_destination(-1)
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                self._cycle_destination(1)
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                request = self._interaction.complete_placement()
                self._finish_move_accessibility(
                    "Plant placement requested. Undo remains available after placement."
                    if request is not None
                    else "Move cancelled. Plant selection remains available."
                )
                self.placementStateChanged.emit(False)
                if request is not None and request[1] != self._slot_for_plant(request[0]):
                    self.placementRequested.emit(request[0], request[1])
                else:
                    self._inline_message = "Move cancelled"
            elif event.key() == Qt.Key.Key_Escape:
                self._interaction.cancel_placement()
                self._inline_message = "Move cancelled"
                self._finish_move_accessibility("Move cancelled. Plant selection remains available.")
                self.placementStateChanged.emit(False)
                self.cancelPlacementRequested.emit()
            else:
                super().keyPressEvent(event)
                return
        elif self._interaction.pinned_id and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._card_action_index = (self._card_action_index + (-1 if event.key() == Qt.Key.Key_Left else 1)) % 3
            action = ("Nurture", "Move", "View story")[self._card_action_index]
            self.setAccessibleName(f"{action} selected for plant action card")
        elif self._interaction.pinned_id and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._card_action_index == 0:
                plant = self._plant_for_id(self._interaction.pinned_id)
                if plant is not None and not plant.get("is_focus"):
                    self.nurtureRequested.emit(self._interaction.pinned_id)
            elif self._card_action_index == 1:
                self._begin_move(self._interaction.pinned_id, keyboard=True)
            else:
                self.storyRequested.emit(self._interaction.pinned_id)
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._interaction.cycle_focus(plant_ids, -1)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._interaction.cycle_focus(plant_ids, 1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            focused = self._interaction.focused_id(plant_ids)
            if focused:
                self._interaction.toggle_pin(focused)
                self._inline_message = ""
                if self._interaction.pinned_id:
                    self._card_action_index = 0
                    self.setAccessibleDescription(
                        "Plant selected. Use Tab to reach Nurture, Move, and Story below the garden."
                    )
                    self.cardOpened.emit()
        elif event.key() == Qt.Key.Key_Escape:
            self._interaction.dismiss()
            self._inline_message = ""
        else:
            super().keyPressEvent(event)
            return
        self.update()

    def focusInEvent(self, event: Any) -> None:
        if self._interaction.focused_index < 0:
            self._interaction.cycle_focus(self._plant_ids(), 1)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        if self._interaction.pinned_id is None:
            self._interaction.hover(None)
        self.update()
        super().focusOutEvent(event)

    def _asset_record(self, key: str, value: Any = None) -> tuple[str | None, dict[str, Any]]:
        asset_paths = self.scene.get("asset_paths", {})
        if value is None and isinstance(asset_paths, dict):
            value = asset_paths.get(key)
        if not value:
            return None, {}
        placement: dict[str, Any] = {}
        raw_path = value
        if isinstance(value, dict):
            raw_path = value.get("path")
            raw_placement = value.get("placement", {})
            if isinstance(raw_placement, dict):
                placement = raw_placement
        if not raw_path:
            return None, placement
        path = Path(str(raw_path)).expanduser()
        if not path.exists() or not path.is_file() or path.suffix.lower() not in {".svg", ".png", ".webp"}:
            return None, placement
        return str(path), placement

    def _asset_path(self, key: str) -> str | None:
        return self._asset_record(key)[0]

    def _surface_asset_record(
        self, width: float, height: float, *, surface_context: str = "dashboard"
    ) -> tuple[str | None, str | None, dict[str, Any], str]:
        asset_paths = self.scene.get("asset_paths", {})
        background = asset_paths.get("background", {}) if isinstance(asset_paths, dict) else {}
        if not isinstance(background, dict):
            return None, None, {}, ""
        placement = background.get("placement", {})
        if not isinstance(placement, dict):
            placement = {}
        variant_name, variant = scene_surface_variant(
            placement, width, height, surface_context
        )
        root = Path(str(background.get("asset_root", ""))).expanduser()

        def resolve(key: str) -> str | None:
            rel = str(variant.get(key, ""))
            if not rel or not root.is_dir():
                return None
            candidate = (root / rel).resolve()
            try:
                candidate.relative_to(root.resolve())
            except (OSError, ValueError):
                return None
            if not candidate.is_file() or candidate.suffix.lower() not in {".png", ".webp"}:
                return None
            return str(candidate)

        return resolve("file"), resolve("occlusion_file"), variant, variant_name

    def _placement_number(self, placement: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
        try:
            return self._clamp(float(placement.get(key, default)), low, high)
        except (TypeError, ValueError):
            return default

    def _renderer_for(self, path: str) -> Any | None:
        if QSvgRenderer is None:
            return None
        renderer = self._svg_cache.get(path)
        if renderer is None:
            renderer = QSvgRenderer(path)
            if not renderer.isValid():
                return None
            self._svg_cache[path] = renderer
        return renderer if renderer.isValid() else None

    def _pixmap_for(self, path: str) -> QPixmap | None:
        pixmap = self._raster_cache.get(path)
        if pixmap is None:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return None
            self._raster_cache[path] = pixmap
        return pixmap if not pixmap.isNull() else None

    def _draw_raster(self, painter: QPainter, path: str, box: QRectF, cover: bool, opacity: float,
                     focal: tuple[float, float] = (0.5, 0.5)) -> bool:
        pixmap = self._pixmap_for(path)
        if pixmap is None:
            return False
        source_w = max(1, pixmap.width())
        source_h = max(1, pixmap.height())
        scale = max(box.width() / source_w, box.height() / source_h) if cover else min(
            box.width() / source_w, box.height() / source_h
        )
        draw_w = source_w * scale
        draw_h = source_h * scale
        target = QRectF(box.x() - (draw_w - box.width()) * focal[0],
                        box.y() - (draw_h - box.height()) * focal[1], draw_w, draw_h)
        painter.save()
        painter.setOpacity(opacity)
        painter.setClipRect(box)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.restore()
        return True

    def _draw_asset_contain(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0) -> bool:
        if Path(path).suffix.lower() == ".svg":
            return self._draw_svg_contain(painter, path, box, opacity)
        return self._draw_raster(painter, path, box, cover=False, opacity=opacity)

    def _draw_asset_cover(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0,
                          focal: tuple[float, float] = (0.5, 0.5)) -> bool:
        if Path(path).suffix.lower() == ".svg":
            return self._draw_svg_cover(painter, path, box, opacity, focal)
        return self._draw_raster(painter, path, box, cover=True, opacity=opacity, focal=focal)

    def _draw_svg_contain(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0) -> bool:
        renderer = self._renderer_for(path)
        if renderer is None:
            return False
        default_size = renderer.defaultSize()
        source_w = max(1, default_size.width())
        source_h = max(1, default_size.height())
        scale = min(box.width() / source_w, box.height() / source_h)
        draw_w = source_w * scale
        draw_h = source_h * scale
        target = QRectF(box.x() + (box.width() - draw_w) / 2, box.y() + (box.height() - draw_h) / 2, draw_w, draw_h)
        painter.save()
        painter.setOpacity(opacity)
        renderer.render(painter, target)
        painter.restore()
        return True

    def _draw_svg_cover(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0,
                        focal: tuple[float, float] = (0.5, 0.5)) -> bool:
        renderer = self._renderer_for(path)
        if renderer is None:
            return False
        default_size = renderer.defaultSize()
        source_w = max(1, default_size.width())
        source_h = max(1, default_size.height())
        scale = max(box.width() / source_w, box.height() / source_h)
        draw_w = source_w * scale
        draw_h = source_h * scale
        target = QRectF(box.x() - (draw_w - box.width()) * focal[0],
                        box.y() - (draw_h - box.height()) * focal[1], draw_w, draw_h)
        painter.save()
        painter.setOpacity(opacity)
        renderer.render(painter, target)
        painter.restore()
        return True

    def _draw_background_asset(self, painter: QPainter, rect: Any) -> bool:
        fallback_path, placement = self._asset_record("background")
        surface_path, _occlusion_path, surface_variant, _variant_name = self._surface_asset_record(
            rect.width(), rect.height()
        )
        path = surface_path or fallback_path
        if not path:
            return False
        crop = str(placement.get("crop", "cover"))
        if crop == "contain":
            return self._draw_asset_contain(painter, path, QRectF(rect), opacity=0.96)
        profile_name = scene_profile_name(rect.width(), rect.height())
        profiles = placement.get("layout_profiles", {})
        profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
        focal = (
            surface_variant.get("focal_point")
            if surface_variant
            else profile.get("focal_point", placement.get("focal_point", [0.5, 0.5]))
            if isinstance(profile, dict)
            else placement.get("focal_point", [0.5, 0.5])
        )
        focal_pair = (float(focal[0]), float(focal[1])) if isinstance(focal, (list, tuple)) and len(focal) == 2 else (0.5, 0.5)
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.96, focal=focal_pair)

    def _draw_surface_occlusion_asset(self, painter: QPainter, rect: Any) -> bool:
        _background_path, path, variant, _variant_name = self._surface_asset_record(
            rect.width(), rect.height()
        )
        if not path:
            return False
        focal = variant.get("focal_point", [0.5, 0.5])
        focal_pair = (
            (float(focal[0]), float(focal[1]))
            if isinstance(focal, (list, tuple)) and len(focal) == 2
            else (0.5, 0.5)
        )
        return self._draw_asset_cover(
            painter, path, QRectF(rect), opacity=1.0, focal=focal_pair
        )

    def _draw_garden_overlay_asset(self, painter: QPainter, rect: Any) -> bool:
        path, placement = self._asset_record("garden_overlay")
        if not path:
            return False
        crop = str(placement.get("crop", "cover"))
        if crop == "contain":
            return self._draw_asset_contain(painter, path, QRectF(rect), opacity=0.96)
        background = self.scene.get("asset_paths", {}).get("background", {})
        background_placement = background.get("placement", {}) if isinstance(background, dict) else {}
        profile_name = scene_profile_name(rect.width(), rect.height())
        profiles = background_placement.get("layout_profiles", {}) if isinstance(background_placement, dict) else {}
        profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
        focal = profile.get("focal_point", [0.5, 0.5]) if isinstance(profile, dict) else [0.5, 0.5]
        focal_pair = (float(focal[0]), float(focal[1])) if isinstance(focal, (list, tuple)) and len(focal) == 2 else (0.5, 0.5)
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.96, focal=focal_pair)

    def _draw_weather_asset(self, painter: QPainter, rect: Any) -> bool:
        if str(self.scene.get("weather", "")) == "sunny":
            return False
        path, placement = self._asset_record("weather")
        if not path:
            return False
        crop = str(placement.get("crop", "cover"))
        if crop == "contain":
            return self._draw_asset_contain(painter, path, QRectF(rect), opacity=0.24)
        background = self.scene.get("asset_paths", {}).get("background", {})
        background_placement = background.get("placement", {}) if isinstance(background, dict) else {}
        profile_name = scene_profile_name(rect.width(), rect.height())
        profiles = background_placement.get("layout_profiles", {}) if isinstance(background_placement, dict) else {}
        profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
        focal = profile.get("focal_point", [0.5, 0.5]) if isinstance(profile, dict) else [0.5, 0.5]
        focal_pair = (float(focal[0]), float(focal[1])) if isinstance(focal, (list, tuple)) and len(focal) == 2 else (0.5, 0.5)
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.24, focal=focal_pair)

    def _draw_weather_motion(
        self, painter: QPainter, rect: Any, weather: str, density: float
    ) -> None:
        width = max(1, rect.width())
        height = max(1, rect.height())
        intensity = self._clamp(
            self._coerce_float(self.scene.get("animation_intensity", 0.7), 0.7), 0.1, 1.6
        )
        phase = self.phase * intensity
        painter.save()
        if weather == "gentle_rain":
            painter.setPen(QPen(QColor(170, 205, 255, int(70 + 35 * density)), 1.2))
            for index in range(max(8, int(42 * density))):
                x = (index * 47 + phase * 72) % width
                y = (index * 29 + phase * 112) % height
                painter.drawLine(int(x), int(y), int(x - 6), int(y + 15))
        elif weather == "fireflies":
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(max(6, int(24 * density))):
                x = (index * 61 + phase * (10 + index % 4)) % width
                base_y = height * 0.24 + ((index * 37) % max(1, int(height * 0.58)))
                y = base_y + math.sin(phase * 1.7 + index) * 10
                alpha = int(100 + 90 * (0.5 + 0.5 * math.sin(phase * 2.2 + index)))
                painter.setBrush(QColor(247, 237, 130, alpha))
                size = 3.0 + (index % 3)
                painter.drawEllipse(QRectF(x, y, size, size))
        elif weather == "cloudy":
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(max(3, int(6 * density))):
                cloud_width = width * (0.18 + 0.025 * (index % 3))
                x = ((index * width / 4) + phase * (7 + index)) % (width + cloud_width) - cloud_width
                y = height * (0.12 + 0.08 * (index % 3))
                painter.setBrush(QColor(205, 220, 225, 18 + index * 4))
                painter.drawEllipse(QRectF(x, y, cloud_width, height * 0.09))
        elif weather == "breeze":
            painter.setPen(QPen(QColor(220, 242, 225, 70), 1.4))
            for index in range(max(4, int(9 * density))):
                x = ((index * 113) + phase * (25 + index % 3)) % (width + 90) - 90
                y = height * (0.22 + 0.055 * (index % 7)) + math.sin(phase + index) * 7
                path = QPainterPath()
                path.moveTo(x, y)
                path.cubicTo(x + 24, y - 8, x + 52, y + 9, x + 82, y)
                painter.drawPath(path)
        else:  # sunny
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(max(5, int(12 * density))):
                x = (index * 83 + phase * (8 + index % 3)) % width
                y = (index * 47 + phase * 13) % height
                alpha = int(35 + 45 * (0.5 + 0.5 * math.sin(phase + index)))
                painter.setBrush(QColor(255, 226, 145, alpha))
                painter.drawEllipse(QRectF(x, y, 2.5, 2.5))
        painter.restore()

    def _draw_decoration_asset(self, painter: QPainter, rect: Any) -> bool:
        path, placement = self._asset_record("decoration")
        if not path:
            return False
        anchor_x = self._placement_number(placement, "anchor_x", 0.82, 0.0, 1.0)
        baseline_y = self._placement_number(placement, "baseline_y", 0.88, 0.0, 1.0)
        scale = self._placement_number(placement, "scale", 0.72, 0.1, 2.5)
        width = rect.width() * 0.25 * scale
        height = rect.height() * 0.42 * scale
        box = QRectF(rect.width() * anchor_x - width / 2, rect.height() * baseline_y - height, width, height)
        return self._draw_asset_contain(painter, path, box, opacity=0.96)

    def _draw_plant_asset(self, painter: QPainter, layout: PlantPlacement, plant: dict[str, Any]) -> bool:
        path, placement = self._asset_record("plant", plant.get("asset") or plant.get("image_path"))
        if not path:
            return False
        box = QRectF(layout.draw.x, layout.draw.y, layout.draw.width, layout.draw.height)
        depth_band = "rear" if layout.depth < self.height() * .68 else "front"
        theme = str(self.scene.get("theme", "verdant_dusk"))
        profile = theme_integration_profile(theme, depth_band)
        source = self._pixmap_for(str(path))
        if source is None:
            return self._draw_asset_contain(painter, str(path), box, opacity=float(profile["contrast"]))
        cache_key = (str(path), theme, depth_band)
        graded = self._graded_raster_cache.get(cache_key)
        if graded is None:
            graded = QPixmap(source.size())
            graded.fill(Qt.GlobalColor.transparent)
            grade_painter = QPainter(graded)
            grade_painter.drawPixmap(0, 0, source)
            grade_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            tint = QColor(str(profile["tint"]))
            # Tint alpha also supplies the small saturation reduction without
            # blurring or altering transparent pixels.
            tint.setAlphaF(float(profile["tint_alpha"]) + (1.0 - float(profile["saturation"])) * .18)
            grade_painter.fillRect(graded.rect(), tint)
            grade_painter.end()
            self._graded_raster_cache[cache_key] = graded
        source_w, source_h = max(1, graded.width()), max(1, graded.height())
        scale = min(box.width() / source_w, box.height() / source_h)
        target = QRectF(
            box.x() + (box.width() - source_w * scale) / 2,
            box.y() + (box.height() - source_h * scale) / 2,
            source_w * scale, source_h * scale,
        )
        painter.save()
        painter.setOpacity(float(profile["contrast"]))
        painter.drawPixmap(target, graded, QRectF(graded.rect()))
        painter.restore()
        return True

    def _draw_selected_vessel_edge(self, painter: QPainter, layout: PlantPlacement) -> None:
        support = QRectF(
            layout.support_rect.x, layout.support_rect.y,
            layout.support_rect.width, layout.support_rect.height,
        )
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(238, 181, 91, 105), 1.4))
        path = QPainterPath()
        path.moveTo(support.left() + support.width() * .08, support.bottom() - 1)
        path.cubicTo(
            support.left() + support.width() * .30, support.bottom() + 1,
            support.left() + support.width() * .68, support.bottom() + 1,
            support.right() - support.width() * .08, support.bottom() - 1,
        )
        painter.drawPath(path)
        base = QRectF(layout.base_rect.x, layout.base_rect.y, layout.base_rect.width, layout.base_rect.height)
        painter.setPen(QPen(QColor(244, 186, 89, 82), 1.2))
        left_edge = QPainterPath()
        left_edge.moveTo(base.left() + base.width() * .12, base.top() + base.height() * .28)
        left_edge.cubicTo(base.left() + 1, base.center().y(), base.left() + 2, base.bottom() - 2, base.left() + base.width() * .16, base.bottom())
        painter.drawPath(left_edge)
        painter.restore()

    def _transition_for_plant(self, plant: dict[str, Any]) -> dict[str, Any] | None:
        plant_id = str(plant.get("plant_id", ""))
        for transition in self.scene.get("stage_transitions", []):
            if isinstance(transition, dict) and str(transition.get("plant_id", "")) == plant_id:
                return transition
        return None

    def _draw_transition_glow(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        transition: dict[str, Any],
    ) -> None:
        rare = str(transition.get("new_stage", "")) == "rare"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 211, 105, 54 if rare else 38))
        footprint = QRectF(layout.footprint.x, layout.footprint.y, layout.footprint.width, layout.footprint.height)
        painter.drawEllipse(footprint.adjusted(-18, -7, 18, 7))

    def _draw_plant(self, painter: QPainter, x: float, y: float, plant: dict[str, Any], idx: int) -> None:
        stage_scale = {"seed": 0.35, "sprout": 0.5, "young": 0.72, "mature": 0.93, "flowering": 1.08, "rare": 1.15}
        stage = plant.get("stage", "seed")
        scale = stage_scale.get(stage, 0.6)
        vitality = self._clamp(self._coerce_float(plant.get("vitality", 0.8), 0.8), 0.2, 1.0)

        stem_width = 2.2 + (1.7 * scale)
        stem_color = QColor(72, 138, 72) if stage != "seed" else QColor(104, 120, 88)
        painter.setPen(QPen(stem_color, stem_width))
        stem_h = 95 * scale
        painter.drawLine(int(x), int(y), int(x), int(y - stem_h))

        leaf_palette = {
            "seed": QColor(126, 114, 90),
            "sprout": QColor(86, 162, 102),
            "young": QColor(54, 168, 102),
            "mature": QColor(42, 158, 94),
            "flowering": QColor(52, 176, 108),
            "rare": QColor(86, 198, 126),
        }
        leaf_color = leaf_palette.get(stage, QColor(45, 160, 96))
        leaf_color.setAlphaF(vitality)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(leaf_color)
        for side in (-1, 1):
            path = QPainterPath()
            path.moveTo(x, y - stem_h * 0.58)
            path.quadTo(x + side * 34 * scale, y - stem_h * 0.5, x + side * 16 * scale, y - stem_h * 0.28)
            path.quadTo(x + side * 6 * scale, y - stem_h * 0.38, x, y - stem_h * 0.58)
            painter.drawPath(path)

        if stage in ("mature", "flowering", "rare"):
            canopy_color = QColor(106, 186, 88, 190) if stage != "rare" else QColor(98, 203, 126, 205)
            painter.setBrush(canopy_color)
            painter.drawEllipse(QRectF(x - 18 * scale, y - stem_h - 26 * scale, 36 * scale, 34 * scale))
        if stage in ("flowering", "rare"):
            painter.setBrush(QColor(246, 126 + (idx * 20) % 85, 180, 220))
            for a in range(6):
                angle = (math.pi * 2 * a / 6.0) + self.phase / 5
                fx = x + math.cos(angle) * 11 * scale
                fy = y - stem_h - 14 * scale + math.sin(angle) * 11 * scale
                painter.drawEllipse(QRectF(fx - 5, fy - 5, 10, 10))
            painter.setBrush(QColor(255, 232, 148, 230))
            painter.drawEllipse(QRectF(x - 4, y - stem_h - 18 * scale, 8, 8))
        if stage == "rare" or plant.get("rare_variant"):
            painter.setPen(QPen(QColor(255, 230, 138, 190), 1.7))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(x - 30 * scale, y - stem_h - 42 * scale, 60 * scale, 54 * scale))

    def _draw_fallback_scene(self, painter: QPainter, rect: Any) -> None:
        fallback_gradient = QLinearGradient(0, 0, 0, rect.height())
        fallback_gradient.setColorAt(0.0, QColor(18, 35, 48))
        fallback_gradient.setColorAt(0.65, QColor(24, 55, 56))
        fallback_gradient.setColorAt(1.0, QColor(19, 44, 38))
        painter.fillRect(rect, fallback_gradient)
        painter.setPen(QPen(QColor(6, 18, 15, 170), 2))
        painter.drawText(
            rect.adjusted(20, 20, -20, -20),
            Qt.AlignmentFlag.AlignCenter,
            SCENE_TEXT["fallback_message"],
        )
        painter.setPen(QColor(223, 237, 223))
        painter.drawText(
            rect.adjusted(20, 20, -20, -20),
            Qt.AlignmentFlag.AlignCenter,
            SCENE_TEXT["fallback_message"],
        )
