from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from aqt.qt import QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRectF, QTimer, QWidget, Qt, QColor

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
from .plant_display import PlantInteractionState, plant_layout, smart_card_rect

SCENE_TEXT = {
    "live_garden_label": "Your live study garden",
    "growth_energy_label": "Daily growth energy: {growth}",
    "fallback_message": (
        "We couldn't render the animated garden view.\n"
        "Your study progress, growth updates, and rewards are still being tracked."
    ),
}


class GardenSceneWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(320)
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
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Interactive study garden")
        self._hover_close_timer = QTimer(self)
        self._hover_close_timer.setSingleShot(True)
        self._hover_close_timer.setInterval(180)
        self._hover_close_timer.timeout.connect(self._clear_unpinned_hover)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(42)

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
        transition_ids = {
            str(item.get("plant_id"))
            for item in self.scene.get("stage_transitions", [])
            if isinstance(item, dict)
        }
        if transition_ids and transition_ids != previous_ids:
            self._transition_started_at = time.monotonic()
            QTimer.singleShot(int(self._transition_duration * 1000), self._finish_stage_transition)
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

    def _layout_plants(self, width: float, height: float) -> list[tuple[dict[str, Any], float, float, QRectF]]:
        plants = self.scene.get("plants", [])
        rows = plant_layout(width, height, len(plants))
        result: list[tuple[dict[str, Any], float, float, QRectF]] = []
        self._plant_hit_rects = {}
        self._plant_anchors = {}
        for plant, (x, baseline, hit_x, hit_y, hit_w, hit_h) in zip(plants, rows):
            plant_id = str(plant.get("plant_id", ""))
            hit_rect = QRectF(hit_x, hit_y, hit_w, hit_h)
            if plant_id:
                self._plant_hit_rects[plant_id] = hit_rect
                self._plant_anchors[plant_id] = (x, baseline)
            result.append((plant, x, baseline, hit_rect))
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

            for i in range(26):
                x = (i * 67 + int(self.phase * 15)) % max(1, r.width())
                y = r.height() * 0.7 + 26 * math.sin(self.phase + i / 2)
                painter.setBrush(QColor(255, 255, 255, 18))
                painter.drawEllipse(QRectF(x, y, 2.5, 2.5))

            plants = self.scene.get("plants", [])
            if not plants:
                self._draw_fallback_scene(painter, r)
                return

            plant_rows = self._layout_plants(r.width(), r.height())
            focused_id = self._interaction.focused_id(self._plant_ids()) if self.hasFocus() else None
            for idx, (plant, x, base_y, _hit_rect) in enumerate(plant_rows):
                plant_id = str(plant.get("plant_id", ""))
                emphasized = plant_id in {
                    self._interaction.hovered_id,
                    self._interaction.pinned_id,
                    focused_id,
                }
                sway = 6 * math.sin(self.phase + idx) if self.scene.get("motion_enabled", True) else 0.0
                self._draw_plant_footprint(painter, x, base_y, idx, emphasized)
                transition = self._transition_for_plant(plant)
                transition_progress = self._transition_progress() if transition else None
                if transition:
                    self._draw_transition_glow(painter, x, base_y, transition, transition_progress)
                painter.save()
                if transition_progress is not None and self.scene.get("motion_enabled", True):
                    reveal_scale = self._transition_scale(transition_progress)
                    painter.translate(x, base_y)
                    painter.scale(reveal_scale, reveal_scale)
                    painter.translate(-x, -base_y)
                if not self._draw_plant_asset(painter, x + sway, base_y, plant):
                    self._draw_plant(painter, x + sway, base_y, plant, idx)
                painter.restore()
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

            text_outline = QColor(6, 18, 15, 185 if night else 165)
            painter.setPen(QPen(text_outline, 2.2))
            painter.drawText(18, 32, SCENE_TEXT["live_garden_label"])
            growth_label = format_percent(growth)
            painter.drawText(18, 52, SCENE_TEXT["growth_energy_label"].format(growth=growth_label))
            painter.setPen(QColor(222, 249, 233, glow))
            painter.drawText(18, 32, SCENE_TEXT["live_garden_label"])
            painter.drawText(18, 52, SCENE_TEXT["growth_energy_label"].format(growth=growth_label))
            self._draw_smart_card(painter, r)
        except Exception:
            self._draw_fallback_scene(painter, r)

    def _draw_plant_footprint(self, painter: QPainter, x: float, base_y: float, index: int, emphasized: bool) -> None:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        if emphasized:
            painter.setBrush(QColor(229, 242, 166, 52))
            painter.drawEllipse(QRectF(x - 68, base_y - 176, 136, 168))
        else:
            painter.setBrush(QColor(210, 232, 174, 18))
            painter.drawEllipse(QRectF(x - 55, base_y - 158, 110, 148))
        painter.setBrush(QColor(7, 15, 13, 104 if emphasized else 78))
        painter.drawEllipse(QRectF(x - 53, base_y - 9, 112, 24))
        painter.setBrush(QColor(72, 55, 39, 142))
        painter.drawEllipse(QRectF(x - 42, base_y - 7, 84, 17))
        painter.setPen(QPen(QColor(238, 218, 154, 120 if emphasized else 52), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(x - 47, base_y - 13, 94, 25), 20 * 16, 140 * 16)
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
        plant_id = self._interaction.active_id
        plant = self._plant_for_id(plant_id)
        anchor = self._plant_anchors.get(plant_id or "")
        if plant is None or anchor is None:
            self._card_rect = None
            return
        x, y, width, height = smart_card_rect(rect.width(), rect.height(), anchor[0], anchor[1])
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
        painter.drawText(int(left), int(top), f"{name}  {'✦' if rare else ''}")
        font.setBold(False)
        font.setPointSize(max(9, font.pointSize() - 2))
        painter.setFont(font)
        painter.setPen(QColor(183, 207, 194))
        painter.drawText(int(left), int(top + 24), f"{species} • {stage}")
        vitality = int(round(self._clamp(self._coerce_float(plant.get("vitality", 0.0), 0.0), 0.0, 1.0) * 100))
        points = max(0, int(self._coerce_float(plant.get("growth_points", 0), 0)))
        painter.setPen(QColor(222, 235, 221))
        painter.drawText(int(left), int(top + 51), f"Vitality  {vitality}%     Growth  {points} GP")
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
            remaining = max(0, int(self._coerce_float(plant.get("points_remaining", 0), 0)))
            status = f"{remaining} GP until {next_stage}"
        painter.drawText(int(left), int(top + 101), status)
        painter.setPen(QColor(151, 181, 163))
        hint = "Pinned • click outside or press Esc" if self._interaction.pinned_id else "Click plant to keep this open"
        painter.drawText(int(left), int(top + 137), hint)
        painter.restore()

    def _event_position(self, event: Any) -> Any:
        return event.position() if hasattr(event, "position") else event.pos()

    def _plant_at(self, position: Any) -> str | None:
        for plant_id, hit_rect in reversed(list(self._plant_hit_rects.items())):
            if hit_rect.contains(position):
                return plant_id
        return None

    def _clear_unpinned_hover(self) -> None:
        if self._interaction.pinned_id is None:
            self._interaction.hover(None)
            self.unsetCursor()
            self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        position = self._event_position(event)
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
        position = self._event_position(event)
        plant_id = self._plant_at(position)
        if plant_id:
            self._interaction.toggle_pin(plant_id)
            ids = self._plant_ids()
            if plant_id in ids:
                self._interaction.focused_index = ids.index(plant_id)
            self.setFocus()
        elif self._card_rect is None or not self._card_rect.contains(position):
            self._interaction.dismiss()
        self.update()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        plant_ids = self._plant_ids()
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._interaction.cycle_focus(plant_ids, -1)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._interaction.cycle_focus(plant_ids, 1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            focused = self._interaction.focused_id(plant_ids)
            if focused:
                self._interaction.toggle_pin(focused)
        elif event.key() == Qt.Key.Key_Escape:
            self._interaction.dismiss()
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

    def _asset_path(self, key: str) -> str | None:
        asset_paths = self.scene.get("asset_paths", {})
        if not isinstance(asset_paths, dict):
            return None
        value = asset_paths.get(key)
        if not value:
            return None
        path = Path(str(value)).expanduser()
        if not path.exists() or not path.is_file() or path.suffix.lower() not in {".svg", ".png", ".webp"}:
            return None
        return str(path)

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

    def _draw_raster(self, painter: QPainter, path: str, box: QRectF, cover: bool, opacity: float) -> bool:
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
        target = QRectF(box.x() + (box.width() - draw_w) / 2, box.y() + (box.height() - draw_h) / 2, draw_w, draw_h)
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

    def _draw_asset_cover(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0) -> bool:
        if Path(path).suffix.lower() == ".svg":
            return self._draw_svg_cover(painter, path, box, opacity)
        return self._draw_raster(painter, path, box, cover=True, opacity=opacity)

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

    def _draw_svg_cover(self, painter: QPainter, path: str, box: QRectF, opacity: float = 1.0) -> bool:
        renderer = self._renderer_for(path)
        if renderer is None:
            return False
        default_size = renderer.defaultSize()
        source_w = max(1, default_size.width())
        source_h = max(1, default_size.height())
        scale = max(box.width() / source_w, box.height() / source_h)
        draw_w = source_w * scale
        draw_h = source_h * scale
        target = QRectF(box.x() + (box.width() - draw_w) / 2, box.y() + (box.height() - draw_h) / 2, draw_w, draw_h)
        painter.save()
        painter.setOpacity(opacity)
        renderer.render(painter, target)
        painter.restore()
        return True

    def _draw_background_asset(self, painter: QPainter, rect: Any) -> bool:
        path = self._asset_path("background")
        if not path:
            return False
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.92)

    def _draw_weather_asset(self, painter: QPainter, rect: Any) -> bool:
        path = self._asset_path("weather")
        if not path:
            return False
        return self._draw_asset_cover(painter, path, QRectF(rect), opacity=0.26)

    def _draw_decoration_asset(self, painter: QPainter, rect: Any) -> bool:
        path = self._asset_path("decoration")
        if not path:
            return False
        box = QRectF(rect.width() * 0.68, rect.height() * 0.48, rect.width() * 0.27, rect.height() * 0.38)
        return self._draw_asset_contain(painter, path, box, opacity=0.96)

    def _draw_plant_asset(self, painter: QPainter, x: float, y: float, plant: dict[str, Any]) -> bool:
        path = plant.get("image_path") or self._asset_path("plant")
        if not path:
            return False
        stage = str(plant.get("stage", "young"))
        normalized_path = str(path).replace("\\", "/")
        is_mound_based_v3 = (
            "/v3_storybook_gouache/plants/" in normalized_path
            and "/plants/rose/" not in normalized_path
        )
        if is_mound_based_v3:
            # Dirt-mound families share a full-size canvas and ground baseline.
            # Their internal silhouette bounds carry the dramatic stage growth.
            scale = 1.0
        elif "_unified.png" in normalized_path:
            # The seed and sprout paintings devote more of their canvas to the
            # shared pot. Normalize those two canvases so the pot remains a
            # stable visual anchor while the plant silhouette grows around it.
            scale = {"seed": 0.72, "sprout": 0.72}.get(stage, 1.0)
        else:
            scale = {"seed": 0.44, "sprout": 0.52, "young": 0.66, "mature": 0.84, "flowering": 0.94, "rare": 1.0}.get(stage, 0.7)
        box = QRectF(x - (88 * scale), y - (178 * scale), 176 * scale, 184 * scale)
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
