from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from aqt.qt import (
    QColor, QEvent, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QPointF, QRectF, QTimer, QToolTip, QWidget, Qt, pyqtSignal,
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
from .plant_display import PlantInteractionState, PlantPlacement, Rect, plant_layout, smart_card_rect

SCENE_TEXT = {
    "live_garden_label": "Your garden",
    "fallback_message": (
        "We couldn't render the animated garden view.\n"
        "Your study progress, growth updates, and rewards are still being tracked."
    ),
}


class GardenSceneWidget(QWidget):
    nurtureRequested = pyqtSignal(str)
    placementRequested = pyqtSignal(str, int)
    storyRequested = pyqtSignal(str)
    cardOpened = pyqtSignal()
    selectionChanged = pyqtSignal(str)
    placementStateChanged = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None, *, interactive: bool = True) -> None:
        super().__init__(parent)
        self.setMinimumHeight(420)
        self.phase = 0.0
        self.scene: dict[str, Any] = {"plants": [], "weather": "breeze", "health": 0.7, "growth": 0.2}
        self._svg_cache: dict[str, Any] = {}
        self._raster_cache: dict[str, QPixmap] = {}
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
        self._slot_placements: dict[int, PlantPlacement] = {}
        self._press_position: Any = None
        self._press_plant_id: str | None = None
        self._drag_started = False
        self._drag_position: Any = None
        self._inline_message = ""
        self._card_action_index = 0
        self.interactive = bool(interactive)
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
        return max(420, min(720, int(width * 0.75)))

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
        self.placementStateChanged.emit(False)
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
        safe_scene["plants"] = [plant for plant in plants if isinstance(plant, dict)] if isinstance(plants, list) else []
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
        zone = background_placement.get("planting_zone", {})
        by_slot = {int(plant.get("slot_index", index)): plant for index, plant in enumerate(plants)}
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", len(plants)))))
        slot_items = [dict(by_slot.get(index, {}), slot_index=index) for index in range(unlocked)]
        rows = plant_layout(width, height, slot_items, zone if isinstance(zone, dict) else None)
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
            self._draw_decoration_asset(painter, r)

            for i in range(16):
                x = (i * 67 + int(self.phase * 15)) % max(1, r.width())
                y = r.height() * 0.28 + (i % 5) * r.height() * 0.07 + 14 * math.sin(self.phase + i / 2)
                painter.setBrush(QColor(255, 255, 255, 18))
                painter.drawEllipse(QRectF(x, y, 2.5, 2.5))

            plants = self.scene.get("plants", [])
            if not plants:
                self._clear_hit_targets()
                self._draw_fallback_scene(painter, r)
                return

            plant_rows = self._layout_plants(r.width(), r.height())
            self._draw_slot_placeholders(painter)
            focused_id = self._interaction.focused_id(self._plant_ids()) if self.hasFocus() else None
            for idx, (plant, layout) in enumerate(plant_rows):
                x = layout.footprint.x + layout.footprint.width / 2
                base_y = layout.depth
                plant_id = str(plant.get("plant_id", ""))
                emphasized = plant_id in {
                    self._interaction.hovered_id,
                    self._interaction.pinned_id,
                    focused_id,
                }
                if plant.get("is_focus"):
                    emphasized = True
                sway = 6 * math.sin(self.phase + idx) if self.scene.get("motion_enabled", True) else 0.0
                self._draw_plant_footprint(painter, layout, plant, emphasized)
                transition = self._transition_for_plant(plant)
                transition_progress = self._transition_progress() if transition else None
                if transition:
                    self._draw_transition_glow(painter, x, base_y, transition, transition_progress)
                painter.save()
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
                    painter.translate(x, base_y)
                    painter.scale(1.06, 1.06)
                    painter.translate(-x, -base_y - 8)
                if transition_progress is not None and self.scene.get("motion_enabled", True):
                    reveal_scale = self._transition_scale(transition_progress)
                    painter.translate(x, base_y)
                    painter.scale(reveal_scale, reveal_scale)
                    painter.translate(-x, -base_y)
                if not self._draw_plant_asset(painter, layout, plant, sway):
                    self._draw_plant(painter, x + sway, base_y, plant, idx)
                painter.restore()
                if str(self._plant_placement(plant).get("base_type", "legacy")) == "legacy":
                    self._draw_foreground_growth(painter, x, base_y, idx, emphasized)
                if growth > 0.05:
                    painter.setPen(Qt.PenStyle.NoPen)
                    pulse_alpha = int(25 + 40 * (0.5 + 0.5 * math.sin(self.phase * 2 + idx)))
                    painter.setBrush(QColor(142, 247, 158, pulse_alpha))
                    painter.drawEllipse(QRectF(x - 26, base_y - 130, 52, 52))

            weather = self.scene.get("weather", "breeze")
            weather_overlay_drawn = self._draw_weather_asset(painter, r)
            density = self._clamp(self._coerce_float(self.scene.get("weather_particle_density", 1.0), 1.0), 0.2, 1.25)
            if weather_overlay_drawn:
                density *= 0.55
            if weather in ("gentle_rain", "cloudy"):
                weather_alpha = int(56 + (26 * density))
                pen = QPen(QColor(170, 205, 255, weather_alpha), 1)
                painter.setPen(pen)
                for i in range(int(34 * density)):
                    x = (i * 41 + int(self.phase * 65)) % max(1, r.width())
                    y = (i * 17 + int(self.phase * 95)) % max(1, r.height())
                    painter.drawLine(int(x), int(y), int(x - 5), int(y + 12))
            elif weather == "fireflies":
                painter.setPen(Qt.PenStyle.NoPen)
                for i in range(int(22 * density)):
                    x = (i * 59 + int(self.phase * 28)) % max(1, r.width())
                    y = r.height() * 0.22 + ((i * 31) % int(r.height() * 0.58))
                    firefly_alpha = int(75 + (25 * density))
                    painter.setBrush(QColor(247, 237, 130, firefly_alpha))
                    painter.drawEllipse(QRectF(x, y, 3.5, 3.5))

            self._draw_status_overlay(painter, r, growth, glow)
            if self.interactive:
                self._draw_smart_card(painter, r)
        except Exception:
            self._clear_hit_targets()
            self._draw_fallback_scene(painter, r)

    def _draw_status_overlay(self, painter: QPainter, rect: Any, growth: float, glow: int) -> None:
        labels = [
            f"{max(0, int(self._coerce_float(self.scene.get('streak_days', 0), 0)))} day streak",
            f"{format_percent(growth)} of today's growth goal",
            f"{format_percent(self.scene.get('health', 0.0))} garden health",
        ]
        panel_width = min(470.0, max(1.0, rect.width() - 32.0))
        compact = panel_width < 390
        panel_height = 78 if compact else 62
        panel = QRectF(16, 14, panel_width, panel_height)
        self._status_rect = panel
        painter.save()
        painter.setPen(QPen(QColor(226, 239, 222, 62), 1))
        painter.setBrush(QColor(9, 22, 20, 192))
        painter.drawRoundedRect(panel, 14, 14)
        painter.setPen(QColor(235, 248, 232, glow))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(30, 38, SCENE_TEXT["live_garden_label"])
        font.setBold(False)
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(QColor(205, 225, 211))
        available_width = max(1, int(panel.width() - 28))
        if compact:
            metrics = painter.fontMetrics()
            painter.drawText(30, 59, metrics.elidedText(" • ".join(labels[:2]), Qt.TextElideMode.ElideRight, available_width))
            painter.drawText(30, 75, metrics.elidedText(labels[2], Qt.TextElideMode.ElideRight, available_width))
        else:
            painter.drawText(
                30,
                61,
                painter.fontMetrics().elidedText(
                    "   •   ".join(labels), Qt.TextElideMode.ElideRight, available_width
                ),
            )
        painter.restore()

    def _plant_placement(self, plant: dict[str, Any]) -> dict[str, Any]:
        asset = plant.get("asset")
        placement = asset.get("placement", {}) if isinstance(asset, dict) else {}
        return placement if isinstance(placement, dict) else {}

    def _draw_plant_footprint(self, painter: QPainter, layout: PlantPlacement, plant: dict[str, Any], emphasized: bool) -> None:
        x = layout.footprint.x + layout.footprint.width / 2
        base_y = layout.depth
        base_type = str(self._plant_placement(plant).get("base_type", "legacy"))
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        footprint = QRectF(layout.footprint.x, layout.footprint.y, layout.footprint.width, layout.footprint.height)
        footprint.translate(0, -footprint.height() * 0.38)
        if plant.get("is_focus"):
            painter.setBrush(QColor(229, 242, 166, 35))
            painter.drawEllipse(footprint.adjusted(-20, -7, 20, 7))
        if emphasized and base_type != "pot":
            painter.setPen(QPen(QColor(229, 242, 166, 125), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_ring = footprint.adjusted(-18, -5, 18, 5)
            painter.drawEllipse(focus_ring)
        painter.setBrush(QColor(7, 15, 13, 104 if emphasized else 68))
        painter.drawEllipse(footprint)
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
                f"Plant health: {health_label} ({vitality}%)", Qt.TextElideMode.ElideRight, text_width
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

    def _draw_slot_placeholders(self, painter: QPainter) -> None:
        if not self._interaction.placing:
            return
        occupied = {int(plant.get("slot_index", -1)) for plant in self.scene.get("plants", [])}
        for slot, layout in self._slot_placements.items():
            empty = slot not in occupied
            active = slot == self._interaction.destination_slot
            footprint = QRectF(layout.footprint.x, layout.footprint.y, layout.footprint.width, layout.footprint.height)
            painter.save()
            painter.setPen(QPen(QColor(229, 242, 166, 190 if active else 70), 2 if active else 1))
            painter.setBrush(QColor(94, 68, 45, 125 if active else 52))
            painter.drawEllipse(footprint.adjusted(-10, -4, 10, 4))
            painter.setPen(QColor(242, 247, 211, 230 if active else 125))
            label = "Move here" if active else ("Swap here" if not empty else "Open space")
            painter.drawText(footprint.adjusted(-34, -24, 34, 4), Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()

    def event(self, event: Any) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            # QHelpEvent.pos() still returns QPoint on Qt 6, while QRectF.contains()
            # accepts QPointF (or numeric coordinates). Normal mouse events expose
            # position(), so this incompatibility only appears during a tooltip.
            raw_position = event.position() if hasattr(event, "position") else event.pos()
            position = QPointF(raw_position)
            text = ""
            if self._nurture_rect is not None and self._nurture_rect.contains(position):
                text = (
                    "The nurtured plant gets 80% of growth earned from reviews. "
                    "The remaining 20% is shared among your other plants."
                )
                if len(self.scene.get("plants", [])) <= 1:
                    text = "Your only plant receives all growth earned from reviews."
            elif self._health_rect is not None and self._health_rect.contains(position):
                text = (
                    "Plant health reflects recent study consistency. "
                    "Reviewing restores it; missed days lower it."
                )
            elif self._status_rect is not None and self._status_rect.contains(position):
                text = (
                    "Review cards to fill today's growth goal. Garden health combines plant health, "
                    "recent activity, streak, review volume, and accuracy."
                )
            if text:
                global_position = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                QToolTip.showText(global_position, text, self)
                return True
        return super().event(event)

    def _event_position(self, event: Any) -> Any:
        return event.position() if hasattr(event, "position") else event.pos()

    def _plant_at(self, position: Any) -> str | None:
        for plant_id, hit_rect in reversed(list(self._plant_hit_rects.items())):
            if hit_rect.contains(position):
                return plant_id
        return None

    def _slot_at(self, position: Any) -> int | None:
        for slot, layout in self._slot_placements.items():
            target = QRectF(layout.hit.x, layout.hit.y, layout.hit.width, layout.hit.height).adjusted(-12, -8, 12, 12)
            if target.contains(position):
                return slot
        return None

    def _slot_for_plant(self, plant_id: str) -> int | None:
        plant = self._plant_for_id(plant_id)
        return int(plant.get("slot_index")) if plant is not None else None

    def _valid_slots(self) -> list[int]:
        return sorted(self._slot_placements)

    def _begin_move(self, plant_id: str, *, keyboard: bool) -> bool:
        origin = self._slot_for_plant(plant_id)
        if origin is None:
            return False
        started = self._interaction.begin_placement(plant_id, origin, self._valid_slots(), keyboard=keyboard)
        if started:
            self._inline_message = "Choose a garden space • Enter to place • Esc to cancel" if keyboard else "Drag to an outlined garden space"
            self.setAccessibleName(f"Moving {self._plant_for_id(plant_id).get('name', 'plant')}; choose garden space")
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
        if self._press_plant_id and self._press_position is not None:
            delta = position - self._press_position
            if not self._drag_started and (abs(delta.x()) + abs(delta.y())) >= 8:
                self._drag_started = self._begin_move(self._press_plant_id, keyboard=False)
            if self._drag_started:
                self._drag_position = position
                slot = self._slot_at(position)
                self._interaction.choose_destination(slot, self._valid_slots()) if slot is not None else None
                self.setCursor(Qt.CursorShape.ClosedHandCursor if slot is not None else Qt.CursorShape.ForbiddenCursor)
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
                self._interaction.choose_destination(slot, self._valid_slots())
            request = self._interaction.complete_placement() if slot is not None else None
            if request is not None and request[1] != self._slot_for_plant(request[0]):
                self.placementRequested.emit(request[0], request[1])
            else:
                self._inline_message = "Move cancelled"
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
                        "Plant action card. Nurture gives this plant 80 percent of review growth; "
                        "the rest is shared. Use left and right for Nurture, Move, or View story; Enter activates."
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
            if self._interaction.placing:
                self._interaction.cancel_placement()
                self._inline_message = "Move cancelled"
            super().keyPressEvent(event)
            self.update()
            return
        if self._interaction.move_mode:
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                self._interaction.cycle_destination(self._valid_slots(), -1)
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                self._interaction.cycle_destination(self._valid_slots(), 1)
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                request = self._interaction.complete_placement()
                self.placementStateChanged.emit(False)
                if request is not None and request[1] != self._slot_for_plant(request[0]):
                    self.placementRequested.emit(request[0], request[1])
                else:
                    self._inline_message = "Move cancelled"
            elif event.key() == Qt.Key.Key_Escape:
                self._interaction.cancel_placement()
                self._inline_message = "Move cancelled"
                self.placementStateChanged.emit(False)
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
                        "Plant action card. Nurture gives this plant 80 percent of review growth; "
                        "the rest is shared. Use left and right for Nurture, Move, or View story; Enter activates."
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
        path, placement = self._asset_record("background")
        if not path:
            return False
        crop = str(placement.get("crop", "cover"))
        if crop == "contain":
            return self._draw_asset_contain(painter, path, QRectF(rect), opacity=0.96)
        focal = placement.get("focal_point", [0.5, 0.5])
        focal_pair = (float(focal[0]), float(focal[1])) if isinstance(focal, (list, tuple)) and len(focal) == 2 else (0.5, 0.5)
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.96, focal=focal_pair)

    def _draw_weather_asset(self, painter: QPainter, rect: Any) -> bool:
        if str(self.scene.get("weather", "")) == "sunny":
            return False
        path, placement = self._asset_record("weather")
        if not path:
            return False
        crop = str(placement.get("crop", "cover"))
        draw = self._draw_asset_contain if crop == "contain" else self._draw_asset_cover
        return draw(painter, path, QRectF(rect), opacity=0.24)

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

    def _draw_plant_asset(self, painter: QPainter, layout: PlantPlacement, plant: dict[str, Any], sway: float = 0.0) -> bool:
        path, placement = self._asset_record("plant", plant.get("asset") or plant.get("image_path"))
        if not path:
            return False
        box = QRectF(layout.draw.x + sway, layout.draw.y, layout.draw.width, layout.draw.height)
        return self._draw_asset_contain(painter, str(path), box, opacity=0.98)

    def _transition_for_plant(self, plant: dict[str, Any]) -> dict[str, Any] | None:
        plant_id = str(plant.get("plant_id", ""))
        for transition in self.scene.get("stage_transitions", []):
            if isinstance(transition, dict) and str(transition.get("plant_id", "")) == plant_id:
                return transition
        return None

    def _transition_progress(self) -> float:
        if self._transition_started_at is None:
            return 0.0
        return self._clamp((time.monotonic() - self._transition_started_at) / self._transition_duration, 0.0, 1.0)

    def _transition_scale(self, progress: float) -> float:
        # Quick rise with a gentle overshoot, settling at the normal scale.
        if progress < 0.45:
            return 0.84 + (0.24 * (progress / 0.45))
        return 1.08 - (0.08 * ((progress - 0.45) / 0.55))

    def _draw_transition_glow(
        self,
        painter: QPainter,
        x: float,
        base_y: float,
        transition: dict[str, Any],
        progress: float | None,
    ) -> None:
        rare = str(transition.get("new_stage", "")) == "rare"
        fade = 1.0 if progress is None or not self.scene.get("motion_enabled", True) else max(0.0, 1.0 - progress)
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(255, 211, 105, int((118 if rare else 82) * fade))
        painter.setBrush(color)
        radius = 92 if rare else 76
        painter.drawEllipse(QRectF(x - radius, base_y - 160, radius * 2, radius * 1.55))
        particle_count = 8 if rare else 5
        for index in range(particle_count):
            angle = (math.pi * 2 * index / particle_count) + self.phase
            distance = 54 + (index % 3) * 10
            px = x + math.cos(angle) * distance
            py = base_y - 96 + math.sin(angle) * distance * 0.65
            painter.setBrush(QColor(255, 226, 139, int((190 if rare else 145) * fade)))
            painter.drawEllipse(QRectF(px - 2.5, py - 2.5, 5, 5))

    def _draw_plant(self, painter: QPainter, x: float, y: float, plant: dict[str, Any], idx: int) -> None:
        stage_scale = {"seed": 0.35, "sprout": 0.5, "young": 0.72, "mature": 0.93, "flowering": 1.08, "rare": 1.15}
        stage = plant.get("stage", "seed")
        scale = stage_scale.get(stage, 0.6)
        vitality = self._clamp(self._coerce_float(plant.get("vitality", 0.8), 0.8), 0.2, 1.0)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(62, 45, 38))
        painter.drawEllipse(QRectF(x - 27, y - 14, 54, 23))

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
