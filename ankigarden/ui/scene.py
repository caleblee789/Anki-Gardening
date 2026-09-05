from __future__ import annotations

import math
import logging
import os
import stat
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from aqt.qt import (
    QColor, QEvent, QFont, QImage, QLinearGradient, QRadialGradient, QPainter, QPainterPath, QPen, QPixmap,
    QPointF, QRectF, QTimer, QToolButton, QToolTip, QLabel, QWidget, Qt, pyqtSignal,
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
from .garden_feature_layout import garden_feature_layout
from .landmark_display import (
    landmark_asset_identity_matches,
    landmark_scene_lighting,
    mastery_asset_identity_matches,
    project_landmark_artwork_rect,
    project_landmark_contact_shadow_rect,
)
from .accessibility import AccessibilityAnnouncer, AnnouncementPriority
from ..build_capabilities import CAPTURE_HARNESS_ENABLED
from ..performance import RUNTIME_PERFORMANCE
from .landmarks import (
    DEFAULT_LANDMARK_ACTIONS,
    LandmarkAction,
    normalized_landmark_action,
    project_landmark_bounds,
    project_landmark_outline_paths,
    project_landmark_polygon,
    resolve_scene_landmarks,
)
from .plant_display import (
    NurturedMarkerPlacement,
    PLANT_POPOVER_COMPACT_BREAKPOINT,
    PLANT_POPOVER_MAX_HEIGHT,
    PLANT_POPOVER_MIN_HEIGHT,
    PLANT_POPOVER_MIN_WIDTH,
    PLANT_POPOVER_PREFERRED_WIDTH,
    PopoverPlacement,
    SceneGeometryLayout,
    PlantInteractionState,
    PlantPlacement,
    Rect,
    bed_badge_rect,
    bed_interaction_state,
    contained_canvas_rect,
    move_badge_label,
    move_target_state,
    nurtured_marker_fallback_rect,
    nurtured_marker_placement,
    plant_layout,
    plant_layout_item,
    planter_draw_rect,
    partition_scene_rows,
    repair_unique_slot_items,
    requires_native_destination_selector,
    scene_height_for_width,
    scene_profile_name,
    scene_surface_variant,
    smart_card_rect,
    status_overlay_rect,
    theme_integration_profile,
    translated_plant_placement,
)
from ..terminology import PROGRESSION_SUMMARY
from .copy import KEYBOARD_HINT
from .render_cache import BoundedLruCache
from .theme import GARDEN_THEME, SCENE_HELP_BUTTON_SIZE

SCENE_TEXT = {
    "live_garden_label": "Your garden",
    "fallback_message": (
        "We couldn't render the animated garden view.\n"
        "Your cards, Growth, and rewards are still being tracked."
    ),
}

STATS_HELP_TEXT = PROGRESSION_SUMMARY
PLANT_HOVER_OUTLINE_WIDTH = 1.65
PLANT_HOVER_OUTLINE_OPACITY = 0.55
ANIMATION_INTERVAL_MS = 42
MOVE_ANIMATION_INTERVAL_MS = 16
LAYOUT_CACHE_LIMIT = 4
FILE_IDENTITY_CACHE_LIMIT = 64
SURFACE_CACHE_LIMIT = 12
RASTER_CACHE_LIMIT = 32
SVG_CACHE_LIMIT = 12
GRADED_RASTER_CACHE_LIMIT = 48
HIGHLIGHT_CACHE_LIMIT = 32


logger = logging.getLogger(__name__)


class GardenSceneWidget(QWidget):
    placementRequested = pyqtSignal(str, int, int)
    placementDestinationChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal(str)
    placementStateChanged = pyqtSignal(bool)
    cancelPlacementRequested = pyqtSignal()
    moveSessionRequested = pyqtSignal(str)
    cardGeometryChanged = pyqtSignal()
    landmarkActivated = pyqtSignal(str)
    landmarksChanged = pyqtSignal()
    HOVER_FADE_STEP = 0.30

    def __init__(self, parent: QWidget | None = None, *, interactive: bool = True) -> None:
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.phase = 0.0
        self.scene: dict[str, Any] = {
            "plants": [],
            "garden_feature": "seedling_sign",
            "health": 0.7,
            "growth": 0.2,
        }
        self._svg_cache: BoundedLruCache[tuple[Any, ...], Any] = (
            BoundedLruCache(SVG_CACHE_LIMIT)
        )
        self._raster_cache: BoundedLruCache[tuple[Any, ...], QPixmap] = (
            BoundedLruCache(RASTER_CACHE_LIMIT)
        )
        self._graded_raster_cache: BoundedLruCache[tuple[Any, ...], QPixmap] = (
            BoundedLruCache(GRADED_RASTER_CACHE_LIMIT)
        )
        self._highlight_pixmap_cache: BoundedLruCache[tuple[Any, ...], QPixmap] = (
            BoundedLruCache(HIGHLIGHT_CACHE_LIMIT)
        )
        self._landmark_lighting_cache: BoundedLruCache[tuple[Any, ...], QPixmap] = (
            BoundedLruCache(SURFACE_CACHE_LIMIT)
        )
        self._file_identity_cache: BoundedLruCache[
            str, tuple[int, int, int, int] | None
        ] = BoundedLruCache(FILE_IDENTITY_CACHE_LIMIT)
        self._surface_asset_cache: BoundedLruCache[tuple[Any, ...], tuple[Any, ...]] = (
            BoundedLruCache(SURFACE_CACHE_LIMIT)
        )
        self._surface_occlusion_cache: BoundedLruCache[tuple[Any, ...], str | None] = (
            BoundedLruCache(SURFACE_CACHE_LIMIT * 2)
        )
        self._layout_cache: BoundedLruCache[tuple[Any, ...], tuple[Any, ...]] = (
            BoundedLruCache(LAYOUT_CACHE_LIMIT)
        )
        self._planter_family_cache: dict[str, Any] = {}
        self._planter_family_cache_valid = False
        self._asset_payload_signature = repr(self.scene.get("asset_paths", {}))
        self._layout_payload_signature = self._layout_signature_for_scene(self.scene)
        self._transition_started_at: float | None = None
        self._transition_duration = 1.4
        self._transition_generation = 0
        self._nurture_pulse_id = ""
        self._nurture_pulse_started_at: float | None = None
        self._nurtured_marker_placement: NurturedMarkerPlacement | None = None
        self._interaction = PlantInteractionState()
        self._plant_hit_rects: dict[str, QRectF] = {}
        self._plant_anchors: dict[str, tuple[float, float]] = {}
        self._card_connector_rect: QRectF | None = None
        self._card_connector_plant_id = ""
        self._card_popover_placement: PopoverPlacement | None = None
        self._status_rect: QRectF | None = None
        self._stats_help_visible = False
        self._slot_placements: dict[int, PlantPlacement] = {}
        self._painted_move_labels: dict[int, str] = {}
        self._painted_locked_beds: dict[int, dict[str, Any]] = {}
        self._scene_geometry_layout: SceneGeometryLayout | None = None
        self._allowed_move_slots: set[int] | None = None
        self._starter_placement = False
        self._placement_generation = 0
        self._active_placement_token: int | None = None
        self._hovered_move_slot: int | None = None
        self._press_position: Any = None
        self._press_plant_id: str | None = None
        self._drag_started = False
        self._drag_position: Any = None
        self._inline_message = ""
        self._move_transition: dict[str, Any] | None = None
        self._hover_opacity: dict[str, float] = {}
        self._keyboard_hint_timer = QTimer(self)
        self._keyboard_hint_timer.setSingleShot(True)
        self._keyboard_hint_timer.setInterval(5000)
        self._keyboard_hint_timer.timeout.connect(self._hide_keyboard_hint)
        self._keyboard_hint_suppressed = False
        self.interactive = bool(interactive)
        self.accessibility_announcer = AccessibilityAnnouncer(self)
        self._stats_help_button = QToolButton(self)
        self._stats_help_button.setText("?")
        self._stats_help_button.setAccessibleName("About garden statistics")
        self._stats_help_button.setAccessibleDescription(STATS_HELP_TEXT)
        self._stats_help_button.setToolTip(STATS_HELP_TEXT)
        self._stats_help_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._stats_help_button.setFixedSize(
            SCENE_HELP_BUTTON_SIZE,
            SCENE_HELP_BUTTON_SIZE,
        )
        self._stats_help_button.setStyleSheet(
            f"QToolButton {{ color:#e7f4e8; background:rgba(39,67,61,.96); border:1px solid rgba(226,239,222,.45); "
            f"border-radius:{SCENE_HELP_BUTTON_SIZE // 2}px; font-weight:600; }} "
            f"QToolButton:enabled:hover {{ background:#355a4d; border-color:#8eb09a; }} "
            f"QToolButton[keyboardFocusVisible='true']:focus {{ border:2px solid {GARDEN_THEME['focus_ring']}; }}"
        )
        self._stats_help_button.installEventFilter(self)
        self._stats_help_button.clicked.connect(self._focus_stats_help)
        # This control already belongs to the scene. Keeping that invariant is
        # important because setVisible(True) on a parentless widget creates a
        # temporary top-level macOS window and can change full-screen Spaces.
        self._stats_help_button.setVisible(self.interactive)
        self._keyboard_hint = QLabel(KEYBOARD_HINT, self)
        self._keyboard_hint.setObjectName("ankiGardenKeyboardHint")
        self._keyboard_hint.setWordWrap(True)
        self._keyboard_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._keyboard_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._keyboard_hint.setAccessibleName(KEYBOARD_HINT)
        self._keyboard_hint.setStyleSheet(
            "QLabel#ankiGardenKeyboardHint { color:#f1f6e7; background:rgba(17,48,40,.94); "
            "border:1px solid #78947c; border-radius:8px; padding:5px 9px; font-size:13px; }"
        )
        self._keyboard_hint.hide()
        self._landmark_actions: dict[str, LandmarkAction] = dict(DEFAULT_LANDMARK_ACTIONS)
        self._landmark_action_by_id: dict[str, str] = {}
        self._landmark_rects: dict[str, QRectF] = {}
        self._landmark_polygons: dict[str, tuple[tuple[float, float], ...]] = {}
        self._landmark_outline_paths: dict[
            str, tuple[tuple[tuple[float, float], ...], ...]
        ] = {}
        self._landmark_labels: dict[str, str] = {}
        self._landmark_hotspots: dict[str, QToolButton] = {}
        self._landmark_action_id = ""  # Compatibility alias for the first active landmark.
        self._nursery_hotspot = self._create_landmark_hotspot("nursery_entrance")
        self._nursery_hotspot.setText("")
        self._nursery_hotspot.setAccessibleName("Shop")
        self._nursery_hotspot.setAccessibleDescription("Open nursery")
        self._nursery_hotspot.setToolTip("Open nursery")
        self.placementStateChanged.connect(lambda _active: self._sync_landmark_hotspot())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.interactive else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Interactive garden" if self.interactive else "Garden preview")
        self.setAccessibleDescription(
            f"Select a plant to view its actions. {KEYBOARD_HINT}"
            if self.interactive else "This preview is not interactive."
        )
        self._hover_close_timer = QTimer(self)
        self._hover_close_timer.setSingleShot(True)
        self._hover_close_timer.setInterval(180)
        self._hover_close_timer.timeout.connect(self._clear_hover)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._feature_layer_trace: list[str] = []

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return scene_height_for_width(width)

    def _garden_canvas_rect(
        self,
        width: float | None = None,
        height: float | None = None,
    ) -> QRectF:
        """Return the centered 1260 x 840 design canvas for this viewport."""

        canvas = contained_canvas_rect(
            self.width() if width is None else width,
            self.height() if height is None else height,
        )
        return QRectF(canvas.x, canvas.y, canvas.width, canvas.height)

    def _hover_fade_active(self) -> bool:
        target = self._interaction.hovered_id or (
            self._interaction.focused_id(self._plant_ids())
            if self.hasFocus() else None
        )
        candidates = set(self._hover_opacity)
        if target:
            candidates.add(target)
        for plant_id in candidates:
            current = self._hover_opacity.get(plant_id, 0.0)
            desired = 1.0 if plant_id == target else 0.0
            if abs(current - desired) > 1e-9:
                return True
        return False

    def _animation_tick_required(self) -> bool:
        """Return whether another frame can change visible scene pixels."""

        if (
            not self.isVisible()
            or not bool(self.scene.get("motion_enabled", True))
        ):
            return False
        intensity = self._clamp(
            self._coerce_float(
                self.scene.get("animation_intensity", 0.7),
                0.7,
            ),
            0.0,
            1.0,
        )
        return bool(
            intensity > 0.0
            or self._transition_started_at is not None
            or self._nurture_pulse_started_at is not None
            or self._move_transition is not None
            or self._hover_fade_active()
        )

    def _sync_animation_timer(self) -> None:
        if not bool(self.scene.get("motion_enabled", True)):
            target = self._interaction.hovered_id or (
                self._interaction.focused_id(self._plant_ids())
                if self.hasFocus() else None
            )
            self._hover_opacity = {target: 1.0} if target else {}
        should_run = self._animation_tick_required()
        if should_run:
            desired_interval = (
                MOVE_ANIMATION_INTERVAL_MS
                if self._move_transition is not None
                else ANIMATION_INTERVAL_MS
            )
            current_interval = (
                int(self.timer.interval())
                if hasattr(self.timer, "interval") else -1
            )
            if not self.timer.isActive() or current_interval != desired_interval:
                self.timer.start(desired_interval)
        elif self.timer.isActive():
            self.timer.stop()

    def set_motion_enabled(self, enabled: bool) -> None:
        self.scene["motion_enabled"] = bool(enabled)
        if not enabled:
            hovered = self._interaction.hovered_id
            self._hover_opacity = {hovered: 1.0} if hovered else {}
        self._sync_animation_timer()
        self.update()

    def show_nurture_feedback(self, plant_id: str) -> None:
        """Give a brief, state-explaining pulse without changing scene geometry."""

        self._nurture_pulse_id = str(plant_id)
        if not bool(self.scene.get("motion_enabled", True)):
            self._nurture_pulse_started_at = None
            self.update()
            return
        self._nurture_pulse_started_at = time.monotonic()
        QTimer.singleShot(220, self._finish_nurture_pulse)
        self._sync_animation_timer()
        self.update()

    def _finish_nurture_pulse(self) -> None:
        self._nurture_pulse_started_at = None
        self._nurture_pulse_id = ""
        self._sync_animation_timer()
        self.update()

    def hideEvent(self, event: Any) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._sync_animation_timer()

    def set_scene(self, payload: dict[str, Any]) -> None:
        previous_ids = {
            str(item.get("plant_id"))
            for item in self.scene.get("stage_transitions", [])
            if isinstance(item, dict)
        }
        next_scene = self._sanitize_scene_payload(payload)
        next_asset_signature = repr(next_scene.get("asset_paths", {}))
        signature_builder = getattr(self, "_layout_signature_for_scene", None)
        next_layout_signature = (
            signature_builder(next_scene)
            if callable(signature_builder)
            else repr(
                (
                    next_scene.get("plants", []),
                    next_scene.get("asset_paths", {}).get("background", {}),
                    bool(next_scene.get("show_status_overlay", True)),
                )
            )
        )
        previous_asset_signature = getattr(
            self,
            "_asset_payload_signature",
            repr(self.scene.get("asset_paths", {})),
        )
        previous_layout_signature = getattr(
            self,
            "_layout_payload_signature",
            repr(
                (
                    self.scene.get("plants", []),
                    self.scene.get("asset_paths", {}).get("background", {}),
                    bool(self.scene.get("show_status_overlay", True)),
                )
            ),
        )
        assets_changed = next_asset_signature != previous_asset_signature
        layout_changed = next_layout_signature != previous_layout_signature
        self.scene = next_scene
        self._asset_payload_signature = next_asset_signature
        self._layout_payload_signature = next_layout_signature
        invalidate_layout = getattr(self, "_invalidate_layout_cache", None)
        if layout_changed and callable(invalidate_layout):
            invalidate_layout()
        reset_scene_inputs = getattr(self, "_reset_scene_input_caches", None)
        if assets_changed and callable(reset_scene_inputs):
            reset_scene_inputs()
        clear_images = getattr(self, "_clear_image_render_caches", None)
        if assets_changed and callable(clear_images):
            clear_images()
        set_motion = getattr(self, "set_motion_enabled", None)
        if callable(set_motion):
            set_motion(bool(self.scene.get("motion_enabled", True)))
        self._interaction.reconcile(self._plant_ids())
        sync_emphasis = getattr(self, "_sync_emphasis_state_properties", None)
        if callable(sync_emphasis):
            sync_emphasis()
        if (
            getattr(self, "_active_placement_token", None) is not None
            and not self._interaction.placing
        ):
            self._invalidate_placement_session()
        valid_ids = set(self._plant_ids())
        self._hover_opacity = {
            plant_id: opacity for plant_id, opacity in self._hover_opacity.items() if plant_id in valid_ids
        }
        if not self.interactive:
            self._interaction.dismiss()
        transition_ids = {
            str(item.get("plant_id"))
            for item in self.scene.get("stage_transitions", [])
            if isinstance(item, dict)
        }
        if transition_ids != previous_ids:
            self._transition_generation += 1
            if transition_ids and bool(self.scene.get("motion_enabled", True)):
                self._transition_started_at = time.monotonic()
                generation = self._transition_generation
                QTimer.singleShot(
                    int(self._transition_duration * 1000),
                    lambda: self._finish_stage_transition(generation),
                )
            else:
                self._transition_started_at = None
        sync_animation = getattr(self, "_sync_animation_timer", None)
        if callable(sync_animation):
            sync_animation()
        if self.interactive:
            if self._interaction.pinned_id:
                self._announce_focused_plant(selected=True)
            elif self._interaction.focused_index >= 0:
                self._announce_focused_plant()
            else:
                self._update_scene_accessible_description()
        else:
            self._update_scene_accessible_description()
        self.update()
        self._sync_landmark_hotspot()
        QTimer.singleShot(0, self.cardGeometryChanged.emit)

    def set_interactive(self, interactive: bool) -> None:
        self.interactive = bool(interactive)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.interactive else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Interactive garden" if self.interactive else "Garden preview")
        if not self.interactive:
            self._interaction.cancel_placement()
            self._invalidate_placement_session()
            self._interaction.dismiss()
            self._clear_hit_targets()
            self._stats_help_visible = False
        self._update_scene_accessible_description()
        self._stats_help_button.setVisible(self.interactive)
        self._sync_landmark_hotspot()
        self.update()

    def update_plant_slots(self, slots: dict[str, int]) -> bool:
        """Update persisted plant positions without rebuilding artwork payloads."""
        normalized = {str(plant_id): int(slot) for plant_id, slot in slots.items()}
        changed = False
        for plant in self.scene.get("plants", []):
            plant_id = str(plant.get("plant_id", ""))
            if plant_id not in normalized:
                continue
            slot = normalized[plant_id]
            if plant.get("slot_index") != slot:
                plant["slot_index"] = slot
                changed = True
        if not changed:
            return False
        invalidate_layout = getattr(self, "_invalidate_layout_cache", None)
        if callable(invalidate_layout):
            invalidate_layout()
        signature_builder = getattr(self, "_layout_signature_for_scene", None)
        if callable(signature_builder):
            self._layout_payload_signature = signature_builder(self.scene)
        self._slot_placements.clear()
        self.update()
        self._sync_landmark_hotspot()
        QTimer.singleShot(0, self.cardGeometryChanged.emit)
        return True

    def _update_scene_accessible_description(self) -> None:
        active = next((
            plant for plant in self.scene.get("plants", [])
            if isinstance(plant, dict) and bool(plant.get("is_active"))
        ), None)
        nurtured_description = ""
        if active is not None:
            name = str(active.get("name") or active.get("species") or "This plant")
            nurtured_description = f" {name} is nurtured."
        base = (
            f"Select a plant to view its actions. {KEYBOARD_HINT}"
            if self.interactive else
            "This preview is not interactive."
        )
        self.setAccessibleDescription(base + nurtured_description)

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
        elif watched in self._landmark_hotspots.values():
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            ):
                watched.click()
                event.accept()
                return True
            if event.type() in (
                QEvent.Type.Enter,
                QEvent.Type.Leave,
                QEvent.Type.FocusIn,
                QEvent.Type.FocusOut,
            ):
                self.update()
        return super().eventFilter(watched, event)

    def _focus_stats_help(self) -> None:
        self._stats_help_button.setFocus(Qt.FocusReason.MouseFocusReason)
        self._stats_help_visible = True
        self.update()

    def _clear_hit_targets(self) -> None:
        self._invalidate_layout_cache()
        self._plant_hit_rects.clear()
        self._plant_anchors.clear()
        self._slot_placements.clear()
        self._scene_geometry_layout = None
        self._status_rect = None

    def _invalidate_layout_cache(self) -> None:
        cache = getattr(self, "_layout_cache", None)
        if cache is not None:
            cache.clear()

    @staticmethod
    def _layout_signature_for_scene(scene: dict[str, Any]) -> str:
        asset_paths = scene.get("asset_paths", {})
        background = (
            asset_paths.get("background", {})
            if isinstance(asset_paths, dict) else {}
        )
        plants = scene.get("plants", [])
        geometry_rows = []
        for plant in plants if isinstance(plants, list) else []:
            if not isinstance(plant, dict):
                continue
            geometry_rows.append(
                (
                    plant.get("slot_index"),
                    plant.get("placement"),
                    plant.get("asset"),
                    plant.get("canvas_aspect"),
                )
            )
        return repr(
            (
                tuple(geometry_rows),
                background,
                bool(scene.get("show_status_overlay", True)),
            )
        )

    def _reset_scene_input_caches(self) -> None:
        for name in (
            "_file_identity_cache",
            "_surface_asset_cache",
            "_surface_occlusion_cache",
        ):
            cache = getattr(self, name, None)
            if cache is not None:
                cache.clear()
        self._planter_family_cache = {}
        self._planter_family_cache_valid = False

    def _clear_image_render_caches(self) -> None:
        for name in (
            "_svg_cache",
            "_raster_cache",
            "_graded_raster_cache",
            "_highlight_pixmap_cache",
            "_landmark_lighting_cache",
        ):
            cache = getattr(self, name, None)
            if cache is not None:
                cache.clear()

    def clear_render_caches(self) -> None:
        """Drop bounded scene caches after an explicit runtime asset change."""

        self._invalidate_layout_cache()
        self._reset_scene_input_caches()
        self._clear_image_render_caches()
        self.update()

    def _activate_placement_session(self) -> int:
        """Issue one token that makes queued destination callbacks fail closed."""

        self._placement_generation += 1
        self._active_placement_token = self._placement_generation
        return self._placement_generation

    def _invalidate_placement_session(self) -> None:
        if self._active_placement_token is None:
            return
        self._placement_generation += 1
        self._active_placement_token = None

    def active_placement_token(self) -> int | None:
        return self._active_placement_token

    def _emit_placement_request(self, request: tuple[str, int]) -> None:
        token = self._active_placement_token
        if token is None:
            return
        self.placementRequested.emit(request[0], request[1], token)

    def confirm_selected_placement(self) -> bool:
        """Commit a deliberately selected starter destination."""

        if not self._interaction.placing or not self._starter_placement:
            return False
        request = self._interaction.complete_placement()
        if request is None:
            return False
        self._inline_message = "Saving placement…"
        self._emit_placement_request(request)
        self.update()
        return True

    def begin_move(self, plant_id: str, valid_slots: list[int] | None = None) -> bool:
        if not self.interactive:
            return False
        self._allowed_move_slots = set(valid_slots) if valid_slots is not None else None
        self._hovered_move_slot = None
        started = self._begin_move(plant_id, keyboard=True)
        if started:
            self._activate_placement_session()
            self._interaction.pinned_id = None
            self._interaction.hovered_id = None
            self.selectionChanged.emit("")
            self.placementStateChanged.emit(True)
            self._sync_landmark_hotspot()
            self.setFocus()
            self.update()
        return started

    def begin_starter_placement(self, valid_slots: list[int]) -> bool:
        """Select an initial bed without inventing a transient Plant record."""

        if not self.interactive:
            return False
        valid = sorted({int(slot) for slot in valid_slots if int(slot) >= 0})
        self._allowed_move_slots = set(valid)
        self._hovered_move_slot = None
        started = self._interaction.begin_unplaced("__starter__", valid)
        if not started:
            return False
        self._activate_placement_session()
        self._starter_placement = True
        self._inline_message = "Choose a bed."
        self.setAccessibleName("Place your starter plant")
        self.setAccessibleDescription(
            self._placement_accessible_description(
                "Choose an unlocked bed for your starter."
            )
        )
        self.placementStateChanged.emit(True)
        self._sync_landmark_hotspot()
        self.setFocus()
        self.update()
        return True

    def begin_collection_placement(
        self,
        plant_id: str,
        valid_slots: list[int],
    ) -> bool:
        """Select an empty bed for an owned plant without mutating its state."""

        if not self.interactive:
            return False
        valid = sorted({int(slot) for slot in valid_slots if int(slot) >= 0})
        self._allowed_move_slots = set(valid)
        self._hovered_move_slot = None
        started = self._interaction.begin_unplaced(str(plant_id), valid)
        if not started:
            return False
        self._activate_placement_session()
        self._starter_placement = False
        self._inline_message = "Choose a bed."
        self.setAccessibleName("Plant from Collection")
        self.setAccessibleDescription(
            self._placement_accessible_description(
                "Choose an empty bed for this Collection plant."
            )
        )
        self.placementStateChanged.emit(True)
        self._sync_landmark_hotspot()
        self.setFocus()
        self.update()
        return True

    def finish_move(self, message: str = "Move finished. Plant selection remains available.") -> None:
        """Reset every scene-owned move affordance without requesting a cancel.

        The dashboard calls this after it has accepted or rejected a persisted
        placement.  Keeping that path signal-free prevents a completed save
        from re-entering the dashboard's cancel handler.
        """
        invalidate_session = getattr(self, "_invalidate_placement_session", None)
        if callable(invalidate_session):
            invalidate_session()
        self._interaction.cancel_placement()
        self._allowed_move_slots = None
        self._starter_placement = False
        self._hovered_move_slot = None
        self._press_position = None
        self._press_plant_id = None
        self._drag_started = False
        self._drag_position = None
        self._inline_message = str(message or "")
        self._clear_hit_targets()
        self.unsetCursor()
        QToolTip.hideText()
        self._finish_move_accessibility(
            str(message or "Plant selection remains available.")
        )
        self.placementStateChanged.emit(False)
        self.update()

    def cancel_move(self) -> None:
        """Cancel a learner-initiated move and notify the persistence owner."""
        self.finish_move("Move canceled.")
        self.cancelPlacementRequested.emit()

    def _finish_stage_transition(self, generation: int) -> None:
        if generation != self._transition_generation:
            return
        self._transition_started_at = None
        self.scene["stage_transitions"] = []
        sync_animation = getattr(self, "_sync_animation_timer", None)
        if callable(sync_animation):
            sync_animation()
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
            self._coerce_float(safe_scene.get("animation_intensity", 0.7), 0.7), 0.0, 1.0
        )
        plants = safe_scene.get("plants", [])
        valid_plants = [plant for plant in plants if isinstance(plant, dict)] if isinstance(plants, list) else []
        repaired_plants = repair_unique_slot_items(valid_plants)
        nurtured_seen = False
        for plant in repaired_plants:
            # A resolved plant asset carries its catalog slot.  Fail closed to
            # the intentional botanical fallback when a stale renderer payload
            # points at another species or stage; labels, hit targets, and art
            # must always describe the same plant entity.
            asset = plant.get("asset")
            identity_matches = getattr(
                self,
                "_plant_asset_identity_matches",
                None,
            )
            if callable(identity_matches) and not identity_matches(plant, asset):
                plant["asset"] = None
            mastery_rank = str(plant.get("mastery_rank_id", "") or "")
            mastery_asset = plant.get("mastery_asset")
            if not mastery_asset_identity_matches(mastery_asset, mastery_rank):
                plant["mastery_rank_id"] = ""
                plant["mastery_asset"] = None
            nurtured = bool(plant.get("is_active")) and not nurtured_seen
            plant["is_active"] = nurtured
            nurtured_seen = nurtured_seen or nurtured
        safe_scene["plants"] = repaired_plants
        transitions = safe_scene.get("stage_transitions", [])
        safe_scene["stage_transitions"] = transitions if isinstance(transitions, list) else []
        asset_paths = safe_scene.get("asset_paths", {})
        safe_scene["asset_paths"] = (
            dict(asset_paths) if isinstance(asset_paths, dict) else {}
        )
        safe_scene["motion_enabled"] = bool(safe_scene.get("motion_enabled", True))
        safe_scene["garden_feature_visible"] = bool(
            safe_scene.get(
                "garden_feature_visible",
                safe_scene.get("weather_visible", True),
            )
        )
        safe_scene["visible_scenery"] = str(
            safe_scene.get("visible_scenery", safe_scene.get("scenery", "default"))
            or "default"
        )
        landmark_id = str(safe_scene.get("landmark_id", "") or "")
        landmark_asset = safe_scene["asset_paths"].get("landmark")
        if landmark_asset_identity_matches(landmark_asset, landmark_id):
            safe_scene["landmark_id"] = landmark_id
        else:
            safe_scene["landmark_id"] = ""
            safe_scene["asset_paths"].pop("landmark", None)
        safe_scene["show_locked_bed_badges"] = bool(
            safe_scene.get("show_locked_bed_badges", True)
        )
        safe_scene["debug_placement"] = bool(
            CAPTURE_HARNESS_ENABLED
            and (
                safe_scene.get("debug_placement", False)
                or os.environ.get("ANKI_GARDEN_PLACEMENT_DEBUG") == "1"
            )
        )
        return safe_scene

    def _tick(self) -> None:
        performance_started = RUNTIME_PERFORMANCE.begin()
        intensity = self._clamp(self._coerce_float(self.scene.get("animation_intensity", 0.7), 0.7), 0.0, 1.0)
        self.phase += 0.0 if intensity <= 0 else 0.02 + (0.06 * intensity)
        target = self._interaction.hovered_id or (
            self._interaction.focused_id(self._plant_ids()) if self.hasFocus() else None
        )
        for plant_id in set(self._hover_opacity) | ({target} if target else set()):
            current = self._hover_opacity.get(plant_id, 0.0)
            desired = 1.0 if plant_id == target else 0.0
            if current < desired:
                current = min(desired, current + self.HOVER_FADE_STEP)
            elif current > desired:
                current = max(desired, current - self.HOVER_FADE_STEP)
            if current <= 0.0:
                self._hover_opacity.pop(plant_id, None)
            else:
                self._hover_opacity[plant_id] = current
        self.update()
        self._sync_animation_timer()
        RUNTIME_PERFORMANCE.finish("scene.tick", performance_started)

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

    def selected_plant_id(self) -> str | None:
        return self._interaction.pinned_id

    def emphasis_state(self) -> dict[str, Any]:
        """Return independent hover, selection, nurture, and bed identities."""

        nurtured = next(
            (
                str(plant.get("plant_id", ""))
                for plant in self.scene.get("plants", [])
                if bool(plant.get("is_active"))
            ),
            "",
        )
        return {
            "hovered_plant_id": str(self._interaction.hovered_id or ""),
            "selected_plant_id": str(self._interaction.pinned_id or ""),
            "nurtured_plant_id": nurtured,
            "current_bed_id": self._interaction.drag_origin_slot,
            "available_destination_ids": tuple(self._destination_slots())
            if self._interaction.placing else (),
            "hovered_destination_id": self._hovered_move_slot,
        }

    def _sync_emphasis_state_properties(self) -> None:
        for key, value in self.emphasis_state().items():
            property_name = "scene" + "".join(
                part.capitalize() for part in key.split("_")
            )
            self.setProperty(property_name, value)

    def dismiss_selection(self) -> None:
        if self._interaction.pinned_id is None:
            return
        self._interaction.dismiss()
        self.set_keyboard_hint_suppressed(False)
        self._card_connector_rect = None
        self._card_connector_plant_id = ""
        self._sync_landmark_occlusion()
        self._inline_message = ""
        self._announce_focused_plant()
        self.selectionChanged.emit("")
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._sync_animation_timer()
        self.update()

    def set_keyboard_hint_suppressed(self, suppressed: bool) -> None:
        """Keep the global keyboard banner out of selected-plant panels."""

        self._keyboard_hint_suppressed = bool(suppressed)
        if self._keyboard_hint_suppressed:
            self._hide_keyboard_hint()

    def register_landmark_action(self, action_id: str, accessible_name: str, tooltip: str) -> bool:
        """Register an intentional scene action before manifest geometry can expose it."""

        normalized = normalized_landmark_action(accessible_name, tooltip)
        normalized_id = str(action_id or "").strip()
        if not normalized_id or normalized is None:
            return False
        self._landmark_actions[normalized_id] = normalized
        self._sync_landmark_hotspot()
        return True

    def unregister_landmark_action(self, action_id: str) -> None:
        """Remove an action and immediately hide any matching manifest landmark."""

        normalized_id = str(action_id or "").strip()
        if normalized_id == "garden.nursery.open":
            return
        self._landmark_actions.pop(normalized_id, None)
        self._sync_landmark_hotspot()

    def landmark_geometry(self, action_id: str) -> QRectF | None:
        """Return current scene geometry for onboarding callouts, if available."""

        normalized_id = str(action_id or "").strip()
        for landmark_id, resolved_action in self._landmark_action_by_id.items():
            if resolved_action == normalized_id:
                rect = self._landmark_rects.get(landmark_id)
                return QRectF(rect) if rect is not None else None
        return None

    def focus_landmark(self, action_id: str) -> bool:
        """Focus a visible landmark without activating it (used by first-use guidance)."""

        normalized_id = str(action_id or "").strip()
        for landmark_id, resolved_action in self._landmark_action_by_id.items():
            button = self._landmark_hotspots.get(landmark_id)
            if resolved_action == normalized_id and button is not None and button.isVisible():
                button.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        return False

    def _create_landmark_hotspot(self, landmark_id: str) -> QToolButton:
        button = QToolButton(self)
        button.setText("")
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton { background:transparent; border:0; }"
        )
        button.clicked.connect(
            lambda _checked=False, landmark_id=landmark_id: self._activate_landmark_by_id(landmark_id)
        )
        button.installEventFilter(self)
        button.hide()
        self._landmark_hotspots[landmark_id] = button
        return button

    def _landmark_placement(self) -> dict[str, Any]:
        asset_paths = self.scene.get("asset_paths", {})
        background = asset_paths.get("background", {}) if isinstance(asset_paths, dict) else {}
        placement = background.get("placement", {}) if isinstance(background, dict) else {}
        return placement if isinstance(placement, dict) else {}

    def _sync_landmark_hotspot(self) -> None:
        for button in self._landmark_hotspots.values():
            button.hide()
        self._landmark_action_id = ""
        self._landmark_action_by_id.clear()
        self._landmark_rects.clear()
        getattr(self, "_landmark_polygons", {}).clear()
        getattr(self, "_landmark_outline_paths", {}).clear()
        getattr(self, "_landmark_labels", {}).clear()
        if self._interaction.placing:
            self.landmarksChanged.emit()
            return

        canvas = self._garden_canvas_rect()
        background_path, _legacy, variant, _name = self._surface_asset_record(
            canvas.width(), canvas.height()
        )
        if background_path is None or self._pixmap_for(background_path) is None:
            self.landmarksChanged.emit()
            return

        placement = self._landmark_placement()
        landmarks = resolve_scene_landmarks(
            placement,
            width=canvas.width(),
            height=canvas.height(),
            interactive=self.interactive,
            actions=self._landmark_actions,
        )
        source_aspect = float(variant.get("width", 4)) / max(1.0, float(variant.get("height", 3)))
        focal_raw = variant.get("focal_point", [0.5, 0.5])
        focal = (
            (float(focal_raw[0]), float(focal_raw[1]))
            if isinstance(focal_raw, (list, tuple)) and len(focal_raw) == 2
            else (0.5, 0.5)
        )
        for landmark in landmarks:
            geometry = project_landmark_bounds(
                landmark,
                width=canvas.width(),
                height=canvas.height(),
                source_aspect=source_aspect,
                focal=focal,
            )
            if geometry is None:
                continue
            button = self._landmark_hotspots.get(landmark.landmark_id)
            if button is None:
                button = self._create_landmark_hotspot(landmark.landmark_id)
            button.setAccessibleName(landmark.accessible_name)
            button.setAccessibleDescription(landmark.tooltip)
            button.setToolTip("")
            absolute_geometry = (
                int(round(canvas.x())) + geometry[0],
                int(round(canvas.y())) + geometry[1],
                geometry[2],
                geometry[3],
            )
            button.setGeometry(*absolute_geometry)
            button.show()
            button.raise_()
            self._landmark_action_by_id[landmark.landmark_id] = landmark.action_id
            self._landmark_rects[landmark.landmark_id] = QRectF(*absolute_geometry)
            self._landmark_polygons[landmark.landmark_id] = tuple(
                (x + canvas.x(), y + canvas.y())
                for x, y in project_landmark_polygon(
                    landmark,
                    width=canvas.width(),
                    height=canvas.height(),
                    source_aspect=source_aspect,
                    focal=focal,
                )
            )
            self._landmark_outline_paths[landmark.landmark_id] = tuple(
                tuple((x + canvas.x(), y + canvas.y()) for x, y in path)
                for path in project_landmark_outline_paths(
                    landmark,
                    width=canvas.width(),
                    height=canvas.height(),
                    source_aspect=source_aspect,
                    focal=focal,
                )
            )
            self._landmark_labels[landmark.landmark_id] = landmark.accessible_name
        self._landmark_action_id = next(iter(self._landmark_action_by_id.values()), "")
        self._sync_landmark_occlusion()
        self.landmarksChanged.emit()

    def _sync_landmark_occlusion(self) -> None:
        # Transparent building targets must not remain clickable underneath
        # the inspector. Dismissal restores their ordinary scene behavior.
        for landmark_id, rect in self._landmark_rects.items():
            button = self._landmark_hotspots.get(landmark_id)
            if button is not None:
                button.setVisible(
                    self._card_connector_rect is None
                    or not self._card_connector_rect.intersects(rect)
                )

    def _activate_landmark_by_id(self, landmark_id: str) -> None:
        self._activate_landmark(self._landmark_action_by_id.get(str(landmark_id), ""))

    def _activate_landmark(self, action_id: str | None = None) -> None:
        normalized_id = str(action_id or self._landmark_action_id or "").strip()
        if (
            not self.interactive
            or self._interaction.placing
            or normalized_id not in self._landmark_actions
            or normalized_id not in self._landmark_action_by_id.values()
        ):
            return
        was_selected = self._interaction.pinned_id is not None
        self._interaction.dismiss()
        if was_selected:
            self.set_keyboard_hint_suppressed(False)
        self._inline_message = ""
        if was_selected:
            self.selectionChanged.emit("")
        self.landmarkActivated.emit(normalized_id)
        self.update()

    def card_geometry(
        self,
        card_width: int,
        card_height: int,
        *,
        minimum_width: int | None = None,
        minimum_height: int | None = None,
        extra_obstacles: tuple[QRectF, ...] = (),
    ) -> QRectF | None:
        plant_id = self._interaction.pinned_id
        previous = self._card_popover_placement if self._card_connector_plant_id == plant_id else None
        if not plant_id or self._interaction.placing:
            self._card_popover_placement = None
            return None
        layout_rows = self._layout_plants(self.width(), self.height())
        plant_lookup = getattr(self, "_plant_for_id", None)
        if not callable(plant_lookup):
            anchor = self._plant_anchors.get(plant_id)
            selected_rect = self._plant_hit_rects.get(plant_id)
            if anchor is None:
                return None
            if selected_rect is not None:
                anchor = (
                    selected_rect.x() + selected_rect.width() + 4.0,
                    selected_rect.y() + selected_rect.height() / 2.0,
                )
            legacy_obstacles = [
                Rect(hit.x(), hit.y(), hit.width(), hit.height()).expanded(8.0, 8.0)
                for other_id, hit in self._plant_hit_rects.items()
                if other_id != plant_id
            ]
            legacy_obstacles.extend(
                Rect(
                    obstacle.x(), obstacle.y(),
                    obstacle.width(), obstacle.height(),
                )
                for obstacle in extra_obstacles
                if obstacle is not None and not obstacle.isEmpty()
            )
            legacy = smart_card_rect(
                self.width(),
                self.height(),
                anchor[0],
                anchor[1],
                card_width=float(card_width),
                card_height=float(card_height),
                obstacles=legacy_obstacles,
                protected_obstacle=(
                    Rect(
                        selected_rect.x(), selected_rect.y(),
                        selected_rect.width(), selected_rect.height(),
                    ).expanded(14.0, 14.0)
                    if selected_rect is not None else None
                ),
            )
            if legacy is None:
                self._card_popover_placement = None
                return None
            self._card_popover_placement = None
            return QRectF(*legacy)
        selected_plant = plant_lookup(plant_id)
        selected_slot = (
            int(selected_plant.get("slot_index", -1))
            if selected_plant is not None else -1
        )
        geometry_layout = self._scene_geometry_layout
        if geometry_layout is None or geometry_layout.bed(selected_slot) is None:
            self._card_popover_placement = None
            return None
        # The selected plant is an obstacle too. Prefer a clean side lane; the
        # geometry helper uses the least-obstructive in-scene fallback only for
        # very dense compositions.
        obstacles: list[Rect] = []
        if self._status_rect is not None:
            obstacles.append(Rect(
                self._status_rect.x(), self._status_rect.y(),
                self._status_rect.width(), self._status_rect.height(),
            ))
        obstacles.extend(
            Rect(
                obstacle.x(), obstacle.y(),
                obstacle.width(), obstacle.height(),
            )
            for obstacle in extra_obstacles
            if obstacle is not None and not obstacle.isEmpty()
        )
        # The image can be letterboxed inside this widget. Overlays can use
        # those surrounding lanes without changing any bed or artwork geometry.
        overlay_layout = replace(
            geometry_layout,
            scene_bounds=Rect(0.0, 0.0, float(self.width()), float(self.height())),
        )
        placement = overlay_layout.resolve_popover(
            selected_slot,
            (float(card_width), float(card_height)),
            (
                min(
                    float(card_width),
                    float(minimum_width)
                    if minimum_width is not None else
                    PLANT_POPOVER_MIN_WIDTH,
                ),
                min(
                    float(card_height),
                    float(minimum_height)
                    if minimum_height is not None else
                    PLANT_POPOVER_MIN_HEIGHT,
                ),
            ),
            obstacles,
            allow_docked=None,
            preferred_side=previous.chosen_side if previous is not None else None,
        )
        self._card_popover_placement = placement
        box = placement.rectangle
        result = QRectF(box.x, box.y, box.width, box.height)
        self._card_connector_rect = result
        self._card_connector_plant_id = plant_id
        self._sync_landmark_occlusion()
        self.update()
        return result

    def card_popover_placement(self) -> PopoverPlacement | None:
        """Return the most recently resolved placement for the selected card."""

        return self._card_popover_placement

    def plant_geometry(self, plant_id: str) -> QRectF | None:
        """Return current in-scene plant geometry for anchored native overlays."""

        self._layout_plants(self.width(), self.height())
        geometry = self._plant_hit_rects.get(str(plant_id))
        return QRectF(geometry) if geometry is not None else None

    def geometry_layout(self) -> SceneGeometryLayout:
        """Return freshly projected logical geometry for external panels."""

        self._layout_plants(self.width(), self.height())
        if self._scene_geometry_layout is None:
            raise RuntimeError("garden scene geometry is unavailable")
        return self._scene_geometry_layout

    def nurtured_marker_geometry(self) -> dict[str, Any] | None:
        """Expose the resolved marker lane for capture and runtime diagnostics."""

        placement = self._nurtured_marker_placement
        if placement is None:
            return None
        rect = placement.rect
        pulse = placement.pulse_bounds
        contact_shadow = placement.contact_shadow
        active_slot = next(
            (
                int(plant.get("slot_index", -1))
                for plant in self.scene.get("plants", [])
                if isinstance(plant, dict) and bool(plant.get("is_active"))
            ),
            -1,
        )
        slot_placements = getattr(self, "_slot_placements", {})
        target_layout = (
            slot_placements.get(active_slot)
            if isinstance(slot_placements, dict) else None
        )
        target_ground = (
            list(target_layout.ground_anchor)
            if isinstance(target_layout, PlantPlacement) else []
        )
        plant_distance = (
            math.hypot(
                rect.x + rect.width / 2 - target_layout.ground_anchor[0],
                rect.y + rect.height * 0.916 - target_layout.ground_anchor[1],
            )
            if isinstance(target_layout, PlantPlacement) else None
        )
        return {
            "slot_index": active_slot,
            "rect": [rect.x, rect.y, rect.width, rect.height],
            "pulse_bounds": [pulse.x, pulse.y, pulse.width, pulse.height],
            "contact_shadow": [
                contact_shadow.x,
                contact_shadow.y,
                contact_shadow.width,
                contact_shadow.height,
            ],
            "planter_rect": [
                placement.planter_rect.x,
                placement.planter_rect.y,
                placement.planter_rect.width,
                placement.planter_rect.height,
            ],
            "target_ground": target_ground,
            "plant_distance": plant_distance,
            "side": placement.side,
            "orientation": placement.orientation,
            "asset_key": placement.asset_key,
            "used_fallback": placement.used_fallback,
            "perspective_scale": placement.perspective_scale,
        }

    def nurtured_marker_protected_regions(self) -> tuple[QRectF, ...]:
        """Return scene-world overlays that the watering can must avoid.

        A bottom-docked plant panel is interface chrome layered above the scene,
        not an object within the garden. Its connector relationship remains
        visible, but reserving the panel's full rectangle would make every
        underlying accessory lane impossible. Side/above/below popovers and
        the scene status panel remain genuine marker obstacles.
        """

        regions: list[QRectF] = []
        popover = self._card_popover_placement
        if self._card_connector_rect is not None and not bool(
            getattr(popover, "docked", False)
        ):
            regions.append(QRectF(self._card_connector_rect))
        if self._status_rect is not None:
            regions.append(QRectF(self._status_rect))
        return tuple(regions)

    def set_card_connector_geometry(self, geometry: QRectF | None, plant_id: str = "") -> None:
        self._card_connector_rect = QRectF(geometry) if geometry is not None else None
        self._card_connector_plant_id = str(plant_id) if geometry is not None else ""
        self._sync_landmark_occlusion()
        self.update()

    def animate_plant_move(self, plant_id: str, origin_slot: int, destination_slot: int) -> None:
        """Animate a saved move for 200 ms, or transition immediately when reduced."""

        if not bool(self.scene.get("motion_enabled", True)):
            self._move_transition = None
            self.update()
            return
        self._move_transition = {
            "plant_id": str(plant_id),
            "origin_slot": int(origin_slot),
            "destination_slot": int(destination_slot),
            "started_at": time.monotonic(),
            "duration": 0.2,
        }
        self._sync_animation_timer()
        QTimer.singleShot(220, self._finish_move_transition)
        self.update()

    def _finish_move_transition(self) -> None:
        self._move_transition = None
        self._sync_animation_timer()
        self.update()

    def keep_card_open(self, plant_id: str, message: str = "") -> None:
        changed = self._interaction.pinned_id != plant_id
        plant_ids = self._plant_ids()
        if plant_id in plant_ids:
            self._interaction.pinned_id = plant_id
            self._interaction.focused_index = plant_ids.index(plant_id)
            self._interaction.hover(plant_id)
            self.set_keyboard_hint_suppressed(True)
        self._inline_message = message
        if changed and self._interaction.pinned_id == plant_id:
            self.selectionChanged.emit(plant_id)
        self._sync_animation_timer()
        self.update()

    def _layout_plants(self, width: float, height: float) -> list[tuple[dict[str, Any], PlantPlacement]]:
        plants = sorted(self.scene.get("plants", []), key=lambda row: int(row.get("slot_index", 0)))[:6]
        background = self.scene.get("asset_paths", {}).get("background", {})
        background_placement = background.get("placement", {}) if isinstance(background, dict) else {}
        canvas_qrect = self._garden_canvas_rect(width, height)
        canvas = Rect(
            canvas_qrect.x(),
            canvas_qrect.y(),
            canvas_qrect.width(),
            canvas_qrect.height(),
        )
        by_slot = {int(plant.get("slot_index", index)): plant for index, plant in enumerate(plants)}
        dpr_getter = getattr(self, "devicePixelRatioF", None)
        dpr = float(dpr_getter()) if callable(dpr_getter) else 1.0
        cache_key = (
            float(width),
            float(height),
            dpr,
            bool(self._interaction.placing),
            getattr(self, "_layout_payload_signature", ""),
        )

        def associate_current_plants(
            rows: tuple[PlantPlacement, ...] | list[PlantPlacement],
        ) -> list[tuple[dict[str, Any], PlantPlacement]]:
            result: list[tuple[dict[str, Any], PlantPlacement]] = []
            self._plant_hit_rects = {}
            self._plant_anchors = {}
            self._slot_placements = {row.slot_index: row for row in rows}
            geometry = self._scene_geometry_layout
            for row in rows:
                plant = by_slot.get(row.slot_index, {})
                plant_id = str(plant.get("plant_id", ""))
                bed_geometry = geometry.bed(row.slot_index) if geometry is not None else None
                hit = bed_geometry.selection_region if bed_geometry is not None else row.hit
                hit_rect = QRectF(hit.x, hit.y, hit.width, hit.height).adjusted(
                    -8.0, -6.0, 8.0, 6.0
                )
                if plant_id:
                    self._plant_hit_rects[plant_id] = hit_rect
                    self._plant_anchors[plant_id] = (
                        bed_geometry.popover_anchor
                        if bed_geometry is not None else
                        (
                            row.smart_card_anchor.x + row.smart_card_anchor.width / 2,
                            row.smart_card_anchor.y,
                        )
                    )
                    result.append((plant, row))
            return result

        layout_cache = getattr(self, "_layout_cache", None)
        if layout_cache is not None and cache_key in layout_cache:
            cached = layout_cache.get(cache_key)
            if cached is not None:
                cached_rows, self._scene_geometry_layout = cached
                return associate_current_plants(cached_rows)
        slot_items: list[dict[str, Any]] = []
        for index in range(6):
            slot_items.append(plant_layout_item(by_slot.get(index, {}), index))
        local_rows = plant_layout(
            canvas.width,
            canvas.height,
            slot_items,
            background_placement if isinstance(background_placement, dict) else None,
            composition_count=max(1, len(plants)),
            protected_status=bool(self.scene.get("show_status_overlay", True)),
            reserve_move_controls=self._interaction.placing,
        )
        rows = [
            translated_plant_placement(row, canvas.x, canvas.y)
            for row in local_rows
        ]
        family = self._planter_family_record()
        self._scene_geometry_layout = SceneGeometryLayout.from_placements(
            width,
            height,
            rows,
            device_pixel_ratio=dpr,
            planter_family=family,
            scene_bounds=canvas,
        )
        result = associate_current_plants(rows)
        if layout_cache is not None:
            layout_cache[cache_key] = (
                tuple(rows),
                self._scene_geometry_layout,
            )
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
        performance_started = RUNTIME_PERFORMANCE.begin()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        viewport = self.rect()
        r = self._garden_canvas_rect()
        painter.fillRect(viewport, QColor(GARDEN_THEME["garden_background"]))
        painter.save()
        painter.setClipRect(r)
        try:
            sky = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
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
            background_drawn = self._draw_background_asset(
                painter,
                r,
                edge_rect=viewport,
            )
            growth = self._clamp(self._coerce_float(self.scene.get("growth", 0.0), 0.0), 0.0, 1.0)

            if not background_drawn:
                sun_x = r.x() + r.width() * (0.75 + 0.02 * math.sin(self.phase / 4))
                sun_y = r.y() + r.height() * 0.2
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 220, 130, 95))
                painter.drawEllipse(QRectF(sun_x - 55, sun_y - 55, 110, 110))
                painter.setBrush(QColor(150, 255, 170, int(18 + growth * 40)))
                painter.drawEllipse(QRectF(sun_x - 80, sun_y - 80, 160, 160))

                ground = QLinearGradient(
                    r.left(),
                    r.y() + r.height() * 0.56,
                    r.left(),
                    r.bottom(),
                )
                ground.setColorAt(0.0, QColor(45, 90, 54))
                ground.setColorAt(1.0, QColor(26, 54, 32))
                painter.setBrush(ground)
                painter.drawRoundedRect(
                    QRectF(
                        r.x(),
                        r.y() + r.height() * 0.56,
                        r.width(),
                        r.height() * 0.44,
                    ),
                    0,
                    0,
                )
            # Blend only the background perimeter. Foreground artwork and hit
            # geometry are painted afterwards and retain their original anchors.
            edge = min(36.0, r.width() / 12.0, r.height() / 12.0)
            base = QColor(GARDEN_THEME["garden_background"])
            clear = QColor(base)
            clear.setAlpha(0)
            for x1, y1, x2, y2, area in (
                (r.left(), r.top(), r.left() + edge, r.top(), QRectF(r.left(), r.top(), edge, r.height())),
                (r.right(), r.top(), r.right() - edge, r.top(), QRectF(r.right() - edge, r.top(), edge, r.height())),
                (r.left(), r.top(), r.left(), r.top() + edge, QRectF(r.left(), r.top(), r.width(), edge)),
                (r.left(), r.bottom(), r.left(), r.bottom() - edge, QRectF(r.left(), r.bottom() - edge, r.width(), edge)),
            ):
                fade = QLinearGradient(x1, y1, x2, y2)
                fade.setColorAt(0, base)
                fade.setColorAt(1, clear)
                painter.fillRect(area, fade)
            plant_rows = self._layout_plants(self.width(), self.height())
            self._feature_layer_trace = ["background"]
            self._draw_garden_feature(painter, r)
            self._draw_garden_landmark(painter, r)
            # Runtime soil is resolved from the same six PlantPlacement rows as
            # artwork and interaction. No separate legacy bed overlay ships.

            planter_family = self._planter_family_record()
            replaces_surface_occlusion = bool(
                planter_family
                and planter_family.get("background_contract") == "bedless_v1"
                and planter_family.get("replace_surface_occlusion", True)
            )
            split_occlusion = (
                not replaces_surface_occlusion
                and self._has_split_surface_occlusion(r.width(), r.height())
            )
            # Legacy theme overlays retain their original background behavior.
            # Dusk v2 instead inserts separate ledge/dust layers between rows.
            if not replaces_surface_occlusion and not split_occlusion:
                self._draw_surface_occlusion_asset(painter, r)

            self._nurtured_marker_placement = None
            self._draw_physical_beds(painter)
            focused_id = self._interaction.focused_id(self._plant_ids()) if self.hasFocus() else None
            dragged_rows = [row for row in plant_rows if str(row[0].get("plant_id", "")) == self._interaction.dragged_id and self._drag_started]
            plant_rows = [row for row in plant_rows if row not in dragged_rows] + dragged_rows
            physical_rows = partition_scene_rows(plant_rows)

            def translated_target(plant: dict[str, Any], layout: PlantPlacement) -> tuple[float, float]:
                x = layout.footprint.x + layout.footprint.width / 2
                base_y = layout.depth
                if str(plant.get("plant_id", "")) != self._interaction.dragged_id or not self._drag_started:
                    transition = self._move_transition
                    if (
                        isinstance(transition, dict)
                        and str(plant.get("plant_id", "")) == str(transition.get("plant_id", ""))
                    ):
                        origin = self._slot_placements.get(int(transition.get("origin_slot", -1)))
                        destination = self._slot_placements.get(int(transition.get("destination_slot", -1)))
                        if origin is not None and destination is not None:
                            duration = max(0.001, float(transition.get("duration", 0.2)))
                            progress = min(
                                1.0,
                                max(0.0, (time.monotonic() - float(transition.get("started_at", 0.0))) / duration),
                            )
                            eased = 1.0 - (1.0 - progress) ** 3
                            origin_x = origin.footprint.x + origin.footprint.width / 2
                            destination_x = destination.footprint.x + destination.footprint.width / 2
                            return (
                                x + (origin_x - destination_x) * (1.0 - eased),
                                base_y + (origin.depth - destination.depth) * (1.0 - eased),
                            )
                    return x, base_y
                destination = self._interaction.destination_slot
                target = self._slot_placements.get(destination) if destination is not None else None
                if target is not None:
                    return target.footprint.x + target.footprint.width / 2, target.depth
                if self._drag_position is not None:
                    return self._drag_position.x(), self._drag_position.y()
                return x, base_y

            render_groups = (
                [
                    (
                        depth_band,
                        sorted(
                            (
                                item
                                for item in plant_rows
                                if item[1].depth_band == depth_band
                            ),
                            key=lambda item: item[1].z_depth,
                        ),
                    )
                    for depth_band in ("far", "middle", "near")
                ]
                if planter_family
                else [
                    (row_name, physical_rows[row_name])
                    for row_name in ("rear", "front")
                ]
            )

            for row_name, row_items in render_groups:
                if planter_family:
                    self._draw_planter_family_band(
                        painter,
                        row_name,
                        planter_family,
                        foreground=False,
                    )
                for plant, layout in row_items:
                    x = layout.footprint.x + layout.footprint.width / 2
                    base_y = layout.depth
                    target_x, target_y = translated_target(plant, layout)
                    painter.save()
                    painter.translate(target_x - x, target_y - base_y)
                    self._draw_plant_grounding(painter, layout, plant)
                    painter.restore()

                for idx, (plant, layout) in enumerate(row_items):
                    x = layout.footprint.x + layout.footprint.width / 2
                    base_y = layout.depth
                    target_x, target_y = translated_target(plant, layout)
                    plant_id = str(plant.get("plant_id", ""))
                    selected = not self._interaction.placing and plant_id == self._interaction.pinned_id
                    hover_target = plant_id == (self._interaction.hovered_id or focused_id)
                    keyboard_focused = bool(
                        self.hasFocus()
                        and not self._interaction.pinned_id
                        and plant_id == focused_id
                    )
                    hovered = 0.0 if self._interaction.pinned_id else self._hover_opacity.get(
                        plant_id,
                        1.0 if hover_target and not self.timer.isActive() else 0.0,
                    )
                    transition = self._transition_for_plant(plant)
                    painter.save()
                    if plant_id == self._interaction.dragged_id and self._drag_started:
                        painter.setOpacity(0.78)
                    painter.translate(target_x - x, target_y - base_y)
                    if transition:
                        self._draw_transition_glow(painter, layout, transition)
                    self._draw_plant_artwork_highlight(
                        painter,
                        layout,
                        plant,
                        selected=False,
                        hovered=hovered,
                        keyboard_focused=False,
                    )
                    asset_drawn = self._draw_plant_asset(painter, layout, plant)
                    if not asset_drawn:
                        self._draw_plant(painter, x, base_y, plant, idx)
                    self._draw_mastery_overlay(painter, layout, plant)
                    if str(self._plant_placement(plant).get("base_type", "legacy")) == "legacy":
                        self._draw_foreground_growth(painter, x, base_y, idx, selected)
                    painter.restore()

                if planter_family:
                    self._draw_planter_family_band(
                        painter,
                        row_name,
                        planter_family,
                        foreground=True,
                    )
                elif split_occlusion:
                    self._draw_surface_occlusion_asset(painter, r, layer=row_name)

            # Selected and keyboard-focus contours are a final UI layer so the
            # visible lower vessel edge remains outlined at the surface seam.
            # They trace artwork alpha; no detached ground ellipse is drawn.
            for plant, layout in plant_rows:
                x = layout.footprint.x + layout.footprint.width / 2
                base_y = layout.depth
                plant_id = str(plant.get("plant_id", ""))
                selected = not self._interaction.placing and plant_id == self._interaction.pinned_id
                keyboard_focused = bool(
                    self.hasFocus()
                    and not self._interaction.pinned_id
                    and plant_id == focused_id
                )
                if not selected and not keyboard_focused:
                    continue
                target_x, target_y = translated_target(plant, layout)
                painter.save()
                painter.translate(target_x - x, target_y - base_y)
                if selected:
                    self._draw_selected_bed_ring(
                        painter,
                        layout,
                        nurtured=bool(plant.get("is_active")),
                    )
                self._draw_plant_artwork_highlight(
                    painter,
                    layout,
                    plant,
                    selected=False,
                    hovered=0.0,
                    keyboard_focused=keyboard_focused,
                )
                painter.restore()

            if bool(self.scene.get("debug_placement", False)):
                self._draw_placement_debug(painter, plant_rows)

            self._feature_layer_trace.append("scene-content")

            self._draw_landmark_affordances(painter)
            if bool(self.scene.get("show_locked_bed_badges", True)):
                self._draw_locked_bed_overlays(painter)
            else:
                self._painted_locked_beds = {}
            if self._interaction.placing:
                # Move choices sit above a uniform 15% scene dimmer. This keeps
                # the artwork legible while making destination states dominant.
                painter.fillRect(r, QColor(0, 0, 0, 38))
            self._draw_slot_placeholders(painter)
            self._draw_status_overlay(painter, r, growth, glow)
            if self._stats_help_visible:
                self._draw_stats_help(painter, r)
            self._draw_card_connector(painter)
            # Selected-plant details and real keyboard-focusable actions live in
            # the compact native card positioned over this canvas.
        except Exception:
            self._clear_hit_targets()
            self._draw_fallback_scene(painter, r)
        finally:
            painter.restore()
        RUNTIME_PERFORMANCE.finish("scene.paint", performance_started)

    def _draw_landmark_affordances(self, painter: QPainter) -> None:
        """Trace building silhouettes while keeping generous rectangular hits."""

        if self._interaction.placing:
            return
        canvas = self._garden_canvas_rect()
        for landmark_id, button in self._landmark_hotspots.items():
            if not button.isVisible() or not (button.underMouse() or button.hasFocus()):
                continue
            outline_paths = self._landmark_outline_paths.get(landmark_id, ())
            points = self._landmark_polygons.get(landmark_id, ())
            if not outline_paths and len(points) < 3:
                continue
            path = QPainterPath()
            if outline_paths:
                for outline in outline_paths:
                    path.moveTo(QPointF(*outline[0]))
                    for point in outline[1:]:
                        path.lineTo(QPointF(*point))
            else:
                path.moveTo(QPointF(*points[0]))
                for point in points[1:]:
                    path.lineTo(QPointF(*point))
                path.closeSubpath()
            focused = button.hasFocus()
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(
                QColor("#e5f2a6") if focused else QColor(244, 213, 138, 235),
                3.0 if focused else 2.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            bounds = path.boundingRect()
            label_text = self._landmark_labels.get(landmark_id, "Open")
            metrics = painter.fontMetrics()
            label_width = min(
                max(84.0, float(metrics.horizontalAdvance(label_text) + 24)),
                max(84.0, float(canvas.width() - 16)),
            )
            label_height = 28.0
            label_x = max(
                canvas.left() + 8.0,
                min(
                    canvas.right() - label_width - 8.0,
                    bounds.center().x() - label_width / 2,
                ),
            )
            below = bounds.bottom() + 7.0
            label_y = (
                below
                if below + label_height <= canvas.bottom() - 8
                else bounds.top() - label_height - 7.0
            )
            label_rect = QRectF(
                label_x,
                max(canvas.top() + 8.0, label_y),
                label_width,
                label_height,
            )
            painter.setPen(QPen(QColor(244, 213, 138, 130), 1.0))
            painter.setBrush(QColor(18, 32, 27, 226))
            painter.drawRoundedRect(label_rect, 10, 10)
            painter.setPen(QColor(247, 239, 214))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label_text)
            painter.restore()

    def _draw_card_connector(self, painter: QPainter) -> None:
        """Paint the card-edge pointer chosen by the shared geometry solver."""

        if self._interaction.placing:
            return
        plant_id = str(self._interaction.pinned_id or "")
        card = self._card_connector_rect
        placement = self._card_popover_placement
        if (
            not plant_id
            or plant_id != self._card_connector_plant_id
            or card is None
            or placement is None
            or placement.docked
            or not placement.connector_visible
        ):
            return
        side = str(placement.chosen_side)
        edge_x, edge_y = placement.connector_end
        depth = 8.0
        half_base = 5.0
        path = QPainterPath()
        if side == "right":
            path.moveTo(QPointF(card.left() - depth, edge_y))
            path.lineTo(QPointF(card.left(), edge_y - half_base))
            path.lineTo(QPointF(card.left(), edge_y + half_base))
        elif side == "left":
            path.moveTo(QPointF(card.right() + depth, edge_y))
            path.lineTo(QPointF(card.right(), edge_y - half_base))
            path.lineTo(QPointF(card.right(), edge_y + half_base))
        elif side == "above":
            path.moveTo(QPointF(edge_x, card.bottom() + depth))
            path.lineTo(QPointF(edge_x - half_base, card.bottom()))
            path.lineTo(QPointF(edge_x + half_base, card.bottom()))
        elif side == "below":
            path.moveTo(QPointF(edge_x, card.top() - depth))
            path.lineTo(QPointF(edge_x - half_base, card.top()))
            path.lineTo(QPointF(edge_x + half_base, card.top()))
        else:
            return
        path.closeSubpath()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        connector_color = QColor(GARDEN_THEME["focus_ring"])
        connector_color.setAlpha(238)
        painter.setPen(QPen(connector_color, 2.0))
        painter.setBrush(QColor(GARDEN_THEME["plant_popover_bg"]))
        painter.drawPath(path)
        painter.restore()

    def _draw_status_overlay(self, painter: QPainter, rect: Any, growth: float, glow: int) -> None:
        status_geometry = status_overlay_rect(
            rect.width(),
            protected=bool(self.scene.get("show_status_overlay", True)),
        )
        if status_geometry is None:
            self._status_rect = None
            self._stats_help_button.hide()
            return
        self._stats_help_button.setVisible(self.interactive)
        streak_days = max(0, int(self._coerce_float(self.scene.get("streak_days", 0), 0)))
        streak_bonus = max(0, int(self._coerce_float(self.scene.get("streak_bonus_percent", 0), 0)))
        if streak_days <= 0:
            streak_label = "Study today to start your Anki streak"
        elif streak_bonus > 0:
            streak_label = (
                f"{streak_days}-day Anki streak · "
                f"Garden Rhythm +{streak_bonus}% Growth"
            )
        else:
            streak_label = f"{streak_days}-day Anki streak"
        labels = [streak_label, f"{format_percent(growth)} Growth today"]
        panel = QRectF(
            rect.x() + status_geometry.x,
            rect.y() + status_geometry.y,
            status_geometry.width,
            status_geometry.height,
        )
        self._status_rect = panel
        help_x = int(panel.right() - SCENE_HELP_BUTTON_SIZE - 10)
        help_y = int(panel.top() + 8)
        self._stats_help_button.setGeometry(
            help_x,
            help_y,
            SCENE_HELP_BUTTON_SIZE,
            SCENE_HELP_BUTTON_SIZE,
        )
        painter.save()
        painter.setPen(QPen(QColor(207, 226, 211, 82), 1.0))
        painter.setBrush(QColor(10, 24, 21, 188))
        painter.drawRoundedRect(panel, 12, 12)
        painter.setPen(QPen(QColor(4, 10, 9, 110), 1))
        painter.drawRoundedRect(panel.adjusted(2, 2, -2, -2), 10, 10)
        painter.setPen(QColor(235, 248, 232, glow))
        font = painter.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        content_left = panel.left() + 16
        text_right = panel.right() - SCENE_HELP_BUTTON_SIZE - 24
        painter.drawText(
            QRectF(content_left, panel.top() + 6, max(1.0, text_right - content_left), 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            SCENE_TEXT["live_garden_label"],
        )
        font.setBold(False)
        font.setPointSize(max(12, font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(QColor(205, 225, 211))
        available_width = max(1, int(text_right - content_left))
        painter.drawText(
            QRectF(content_left, panel.top() + 29, available_width, panel.height() - 34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            "\n".join(labels),
        )
        painter.restore()

    def _draw_stats_help(self, painter: QPainter, rect: Any) -> None:
        if self._status_rect is None:
            return
        width = min(390.0, max(180.0, rect.width() - 32.0))
        panel = QRectF(
            rect.x() + 16,
            self._status_rect.bottom() + 8,
            width,
            60,
        )
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
        if not self._plant_asset_identity_matches(plant, asset):
            return {}
        placement = asset.get("placement", {}) if isinstance(asset, dict) else {}
        return placement if isinstance(placement, dict) else {}

    def _highlight_pixmap_for(self, path: str, color: str, radius: int) -> QPixmap | None:
        """Return a cached dilated-alpha-minus-source outer contour."""
        radius = max(1, min(12, int(radius)))
        identity = self._file_identity_for(path)
        if identity is None:
            return None
        key = (path, identity, color, radius)
        cached = self._highlight_pixmap_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached
        source = self._pixmap_for(path)
        if source is None:
            return None
        solid = QPixmap(source.size())
        solid.fill(Qt.GlobalColor.transparent)
        solid_painter = QPainter(solid)
        solid_painter.drawPixmap(0, 0, source)
        solid_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        solid_painter.fillRect(solid.rect(), QColor(color))
        solid_painter.end()
        padding = radius + 1
        edge = QPixmap(source.width() + padding * 2, source.height() + padding * 2)
        edge.fill(Qt.GlobalColor.transparent)
        edge_painter = QPainter(edge)
        # Draw a compact disk of alpha offsets. The padded canvas is essential:
        # otherwise artwork touching the PNG's bottom edge loses its selected
        # contour exactly where the pot meets the soil or stone surface.
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    edge_painter.drawPixmap(padding + dx, padding + dy, solid)
        edge_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        edge_painter.drawPixmap(padding, padding, source)
        edge_painter.end()
        self._highlight_pixmap_cache[key] = edge
        return edge

    def _draw_plant_artwork_highlight(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        plant: dict[str, Any],
        *,
        selected: bool,
        hovered: float,
        keyboard_focused: bool,
    ) -> bool:
        """Draw a restrained alpha-following outline behind visible artwork."""
        if not selected and not keyboard_focused and hovered <= 0.0:
            return False
        path, _placement = self._plant_asset_record(plant)
        if not path:
            return False
        source = self._pixmap_for(path)
        emphasized = selected or keyboard_focused
        # Selection remains neutral/cyan-green regardless of nurture state.
        color = GARDEN_THEME["focus_ring"] if emphasized else "#d7edcf"
        if source is None:
            return False
        box = self._plant_draw_box(layout, plant)
        source_w, source_h = max(1, source.width()), max(1, source.height())
        scale = min(box.width() / source_w, box.height() / source_h)
        target = QRectF(
            box.x() + (box.width() - source_w * scale) / 2,
            box.y() + (box.height() - source_h * scale) / 2,
            source_w * scale,
            source_h * scale,
        )
        desired_width = 2.0 if emphasized else PLANT_HOVER_OUTLINE_WIDTH
        source_radius = max(1, min(12, round(desired_width / max(0.01, scale))))
        edge = self._highlight_pixmap_for(path, color, source_radius)
        if edge is None:
            return False
        padding = source_radius + 1
        edge_target = QRectF(
            target.x() - padding * scale,
            target.y() - padding * scale,
            target.width() + padding * scale * 2,
            target.height() + padding * scale * 2,
        )
        painter.save()
        painter.setOpacity(
            0.62 if emphasized else PLANT_HOVER_OUTLINE_OPACITY * hovered
        )
        painter.drawPixmap(edge_target, edge, QRectF(edge.rect()))
        painter.restore()
        return True

    def _draw_selected_bed_ring(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        *,
        nurtured: bool,
    ) -> None:
        del nurtured
        pulse = 0.0
        if self._nurture_pulse_started_at is not None:
            elapsed = max(0.0, time.monotonic() - self._nurture_pulse_started_at)
            pulse = math.sin(min(1.0, elapsed / 0.22) * math.pi)
        draw_asset_outline = getattr(self, "_draw_planter_asset_outline", None)
        if callable(draw_asset_outline) and draw_asset_outline(
            painter,
            layout,
            color=GARDEN_THEME["focus_ring"],
            width=2.0,
            opacity=0.78 + pulse * 0.14,
        ):
            return

        # Legacy and degraded surfaces have no planter-family alpha to trace.
        # Keep their established geometry fallback instead of losing focus.
        bed = QRectF(
            layout.bed_footprint.x,
            layout.bed_footprint.y,
            layout.bed_footprint.width,
            layout.bed_footprint.height,
        )
        horizontal = max(4.0, bed.width() * 0.05)
        vertical = max(2.0, bed.height() * 0.08)
        ring = bed.adjusted(-horizontal, -vertical, horizontal, vertical)
        color = QColor(GARDEN_THEME["focus_ring"])
        color.setAlpha(round(199 + pulse * 35))
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2.0))
        painter.drawEllipse(ring)
        painter.restore()

    def _draw_nurtured_marker(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        plant: dict[str, Any],
        *,
        scene_layouts: list[PlantPlacement] | None = None,
    ) -> None:
        family_resolver = getattr(self, "_planter_family_record", None)
        family = family_resolver() if callable(family_resolver) else {}
        planter = planter_draw_rect(layout, family)
        occupied_layouts = list(scene_layouts or [layout])
        obstacles = [
            item.visible.expanded(4.0, 4.0)
            for item in occupied_layouts
        ]
        protected = [
            Rect(
                qt_rect.x(),
                qt_rect.y(),
                qt_rect.width(),
                qt_rect.height(),
            ).expanded(4.0, 4.0)
            for qt_rect in self.nurtured_marker_protected_regions()
        ]
        geometry_layout = getattr(self, "_scene_geometry_layout", None)
        if geometry_layout is not None and geometry_layout.bed(layout.slot_index) is not None:
            resolved = geometry_layout.resolve_watering_can(
                layout.slot_index,
                layout,
                obstacles=obstacles,
                protected_regions=protected,
            )
        else:
            resolved = nurtured_marker_placement(
                self.width(),
                self.height(),
                layout,
                planter_rect=planter,
                obstacles=obstacles,
                protected_regions=protected,
            )
        self._nurtured_marker_placement = resolved
        contact_shadow = QRectF(
            resolved.contact_shadow.x,
            resolved.contact_shadow.y,
            resolved.contact_shadow.width,
            resolved.contact_shadow.height,
        )
        if contact_shadow.width() > 0 and contact_shadow.height() > 0:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            shadow_color = QColor("#172019")
            shadow_color.setAlpha(82)
            painter.setBrush(shadow_color)
            painter.drawEllipse(contact_shadow)
            painter.restore()
        marker = QRectF(
            resolved.rect.x,
            resolved.rect.y,
            resolved.rect.width,
            resolved.rect.height,
        )
        pulse = 0.0
        if (
            str(plant.get("plant_id", "")) == getattr(self, "_nurture_pulse_id", "")
            and getattr(self, "_nurture_pulse_started_at", None) is not None
        ):
            elapsed = max(0.0, time.monotonic() - self._nurture_pulse_started_at)
            pulse = math.sin(min(1.0, elapsed / 0.22) * math.pi)
        if pulse:
            expansion = marker.width() * pulse * 0.04
            marker = marker.adjusted(-expansion, -expansion, expansion, expansion)

        path_resolver = getattr(self, "_asset_path", None)
        marker_path = (
            path_resolver(resolved.asset_key)
            if callable(path_resolver) else None
        )
        asset_drawer = getattr(self, "_draw_asset_contain", None)
        if (
            not resolved.used_fallback
            and marker_path
            and callable(asset_drawer)
            and asset_drawer(painter, marker_path, marker)
        ):
            return

        # Missing or unreadable artwork must not remove the state cue. Keep a
        # compact version of the previous badge inside the same safe marker box.
        badge = nurtured_marker_fallback_rect(resolved)
        fallback = QRectF(badge.x, badge.y, badge.width, badge.height)
        center = fallback.center()
        center_x = center.x()
        center_y = center.y()
        radius = fallback.width() / 2
        marker_accent = GARDEN_THEME["focus_ring"]
        painter.save()
        painter.setPen(
            QPen(QColor(GARDEN_THEME.get("strong_border", marker_accent)), 1.5)
        )
        painter.setBrush(
            QColor(GARDEN_THEME.get("action_accent", marker_accent))
        )
        painter.drawEllipse(fallback)
        leaf = QPainterPath()
        leaf.moveTo(center_x - radius * 0.42, center_y + radius * 0.18)
        leaf.cubicTo(
            center_x - radius * 0.36,
            center_y - radius * 0.5,
            center_x + radius * 0.42,
            center_y - radius * 0.48,
            center_x + radius * 0.36,
            center_y + radius * 0.18,
        )
        leaf.cubicTo(
            center_x + radius * 0.08,
            center_y + radius * 0.02,
            center_x - radius * 0.08,
            center_y + radius * 0.02,
            center_x - radius * 0.42,
            center_y + radius * 0.18,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(GARDEN_THEME["action_text"]))
        painter.drawPath(leaf)
        painter.restore()

    def _draw_plant_grounding(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        plant: dict[str, Any],
    ) -> None:
        """Draw clipped cast and contact shadows before plant artwork."""
        base_type = str(self._plant_placement(plant).get("base_type", "legacy"))
        painter.save()
        plane = QPainterPath()
        if layout.grounding.shadow_plane:
            first_x, first_y = layout.grounding.shadow_plane[0]
            plane.moveTo(first_x, first_y)
            for point_x, point_y in layout.grounding.shadow_plane[1:]:
                plane.lineTo(point_x, point_y)
            plane.closeSubpath()
            painter.setClipPath(plane, Qt.ClipOperation.IntersectClip)
        painter.setPen(Qt.PenStyle.NoPen)
        stone = layout.grounding.surface_kind == "stone"
        cast_color = QColor(layout.grounding.cast_color)
        contact_color = QColor(layout.grounding.contact_color)
        if not cast_color.isValid():
            cast_color = QColor(*(35, 32, 29) if stone else (67, 43, 27))
        if not contact_color.isValid():
            contact_color = QColor(*(28, 27, 25) if stone else (72, 47, 30))
        cast = layout.grounding.cast_shadow
        cast_box = QRectF(cast.x, cast.y, cast.width, cast.height)
        cast_alpha = max(0, min(255, round(layout.grounding.cast_opacity * 255)))
        for inset, alpha_factor in ((0.0, .34), (.12, .52)):
            shade = QColor(cast_color)
            shade.setAlpha(round(cast_alpha * alpha_factor))
            painter.setBrush(shade)
            painter.drawEllipse(cast_box.adjusted(cast_box.width() * inset, cast_box.height() * inset,
                                                  -cast_box.width() * inset, -cast_box.height() * inset))
        contact = layout.grounding.contact_shadow
        contact_box = QRectF(contact.x, contact.y, contact.width, contact.height)
        base_alpha = max(0, min(255, round(layout.grounding.contact_opacity * 255)))
        for inset, alpha_factor in ((-.14, .28), (-.04, .52), (.10, .90)):
            shade = QColor(contact_color)
            shade.setAlpha(round(base_alpha * alpha_factor))
            painter.setBrush(shade)
            painter.drawEllipse(contact_box.adjusted(contact_box.width() * inset, contact_box.height() * inset,
                                                     -contact_box.width() * inset, -contact_box.height() * inset))
        if base_type == "legacy":
            soil = contact_box.adjusted(contact_box.width() * .12, 0, -contact_box.width() * .12, -contact_box.height() * .28)
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

    def _draw_physical_beds(self, painter: QPainter) -> None:
        """Paint theme-aware empty, occupied, and locked soil from resolved slots."""
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", 0))))
        occupied = {int(plant.get("slot_index", -1)) for plant in self.scene.get("plants", [])}
        self._painted_locked_beds = {}
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
            # Registered v4 surfaces are already painted into the locked
            # environment plate. Painting a second generic soil blob would make
            # stone plinths look plantable and would obscure their real centers.
            if layout.surface_id:
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

    def _draw_locked_bed_overlays(self, painter: QPainter) -> None:
        """Mark locked beds without covering the authored garden artwork."""

        unlocked = max(
            0,
            min(6, int(self.scene.get("unlocked_slots", 0))),
        )
        family_resolver = getattr(self, "_planter_family_record", None)
        planter_family = (
            family_resolver() if callable(family_resolver) else {}
        )
        self._painted_locked_beds = {}
        for slot, layout in self._slot_placements.items():
            if int(slot) < unlocked:
                continue
            bed = QRectF(
                layout.bed_footprint.x,
                layout.bed_footprint.y,
                layout.bed_footprint.width,
                layout.bed_footprint.height,
            )
            planter = planter_draw_rect(layout, planter_family)
            painter.save()
            # The badge is the complete locked treatment. The previous
            # planter-sized translucent rounded rectangle made adjacent beds
            # merge into a foggy panel and obscured the source artwork.
            badge_height = max(22.0, min(26.0, bed.width() * 0.18))
            badge_width = badge_height
            badge_rect = QRectF(
                planter.x + planter.width / 2 - badge_width / 2,
                planter.y + planter.height / 2 - badge_height / 2,
                badge_width,
                badge_height,
            )
            locked_border = QColor(GARDEN_THEME["text_muted"])
            locked_border.setAlpha(150)
            painter.setPen(QPen(locked_border, 1.0))
            painter.setBrush(QColor(8, 37, 28, 170))
            painter.drawRoundedRect(
                badge_rect,
                badge_height * 0.28,
                badge_height * 0.28,
            )
            body_width = badge_width * 0.46
            body_height = badge_height * 0.35
            body_rect = QRectF(
                badge_rect.center().x() - body_width / 2,
                badge_rect.center().y() - body_height * 0.02,
                body_width,
                body_height,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            locked_icon = QColor(GARDEN_THEME["text_muted"])
            locked_icon.setAlpha(175)
            painter.setBrush(locked_icon)
            painter.drawRoundedRect(body_rect, 2.0, 2.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(locked_icon, 1.6))
            painter.drawArc(
                QRectF(
                    body_rect.left() + body_width * 0.18,
                    body_rect.top() - body_height * 0.84,
                    body_width * 0.64,
                    body_height * 1.18,
                ),
                0,
                180 * 16,
            )
            self._painted_locked_beds[int(slot)] = {
                "overlay_bounds": [
                    round(float(badge_rect.x()), 2),
                    round(float(badge_rect.y()), 2),
                    round(float(badge_rect.width()), 2),
                    round(float(badge_rect.height()), 2),
                ],
                "badge_bounds": [
                    round(float(badge_rect.x()), 2),
                    round(float(badge_rect.y()), 2),
                    round(float(badge_rect.width()), 2),
                    round(float(badge_rect.height()), 2),
                ],
                "relative_visual_strength": 0.58,
                "interactive": False,
            }
            painter.restore()

    def _draw_slot_placeholders(self, painter: QPainter) -> None:
        sync_emphasis = getattr(self, "_sync_emphasis_state_properties", None)
        if callable(sync_emphasis):
            sync_emphasis()
        self._painted_move_labels = {}
        if not self._interaction.placing:
            return
        family_resolver = getattr(self, "_planter_family_record", None)
        planter_family = family_resolver() if callable(family_resolver) else {}
        draw_asset_outline = getattr(self, "_draw_planter_asset_outline", None)
        occupied = {int(plant.get("slot_index", -1)) for plant in self.scene.get("plants", [])}
        occupant_names = {
            int(plant.get("slot_index", -1)): str(plant.get("name") or plant.get("species") or "plant")
            for plant in self.scene.get("plants", [])
        }
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", len(occupied)))))
        origin = self._interaction.drag_origin_slot
        valid_destinations = set(self._destination_slots())
        hovered_slot = self._hovered_move_slot
        placed_badges: list[Rect] = []
        obstacle_rows = [
            (int(plant.get("slot_index", -1)), layout.visible.expanded(4.0, 3.0))
            for plant, layout in self._layout_plants(self.width(), self.height())
        ]
        for slot, layout in self._slot_placements.items():
            target_state = move_target_state(
                slot,
                origin_slot=origin,
                valid_destination_slots=valid_destinations,
                unlocked_slots=unlocked,
            )
            starter_placement = bool(
                getattr(self, "_starter_placement", False)
                or origin is None
                or origin < 0
            )
            projected = bed_interaction_state(
                slot,
                origin_slot=origin,
                destination_slot=(
                    slot
                    if slot == hovered_slot and target_state == "valid"
                    else self._interaction.destination_slot
                ),
                unlocked_slots=unlocked,
                occupied_slots=occupied,
                occupant_names=occupant_names,
                starter_placement=starter_placement,
            )
            label, semantic_state = projected.label, projected.state
            current = target_state == "current"
            blocked = target_state in {"locked", "unavailable"}
            occupied_target = slot in occupied and not current
            swap_target = target_state == "valid" and occupied_target
            hovered = target_state == "valid" and slot == hovered_slot
            selected_destination = (
                target_state == "valid"
                and slot == self._interaction.destination_slot
            )
            active = hovered or selected_destination
            if target_state == "unavailable":
                label = (
                    f"Occupied by {occupant_names.get(slot, 'plant')}; invalid destination"
                    if occupied_target else
                    "Invalid destination"
                )
            elif target_state == "locked":
                label = "Locked"
            visual_label = label
            footprint = QRectF(
                layout.bed_footprint.x,
                layout.bed_footprint.y,
                layout.bed_footprint.width,
                layout.bed_footprint.height,
            )
            painter.save()
            if blocked:
                painter.restore()
                continue
            if current:
                pen_color, fill_color = QColor(126, 190, 201, 205), QColor(49, 93, 101, 70)
            elif swap_target:
                pen_color = QColor(
                    GARDEN_THEME["action_hover"]
                    if active else GARDEN_THEME["action_accent"]
                )
                pen_color.setAlpha(245 if active else 118)
                fill_color = QColor(54, 161, 104, 96 if active else 20)
            else:
                pen_color = QColor(GARDEN_THEME["action_hover"] if active else GARDEN_THEME["action_accent"])
                pen_color.setAlpha(245 if active else 112)
                fill_color = QColor(54, 161, 104, 100 if active else 18)
            outline_width = 2.0 if active else 1.25
            outline_drawn = bool(
                callable(draw_asset_outline)
                and (current or target_state == "valid")
                and draw_asset_outline(
                    painter,
                    layout,
                    color=pen_color.name(),
                    width=outline_width,
                    opacity=pen_color.alphaF(),
                    family=planter_family,
                )
            )
            if not outline_drawn:
                pen = QPen(pen_color, outline_width)
                if (
                    target_state == "valid"
                    and not hovered
                    and not selected_destination
                ):
                    pen.setStyle(Qt.PenStyle.DashLine)
                    pen.setDashPattern([4.0, 3.0])
                painter.setPen(pen)
                painter.setBrush(fill_color)
                # Legacy surfaces retain their established ellipse fallback.
                if layout.depth_band == "far":
                    move_footprint = footprint.adjusted(-6, -3, 6, 3)
                else:
                    horizontal_padding = max(6.0, layout.bed_footprint.width * 0.08)
                    vertical_padding = max(3.0, layout.bed_footprint.height * 0.12)
                    move_footprint = footprint.adjusted(
                        -horizontal_padding,
                        -vertical_padding,
                        horizontal_padding,
                        vertical_padding,
                    )
                painter.drawEllipse(move_footprint)
            # Only current and actionable destinations receive move treatment.
            if target_state == "valid":
                preview = getattr(self, "_draw_move_preview", None)
                if active and not occupied_target and callable(preview):
                    preview(painter, slot)
            # Destination rings remain visible, but action copy appears only
            # for the current keyboard/hover target. The origin keeps its
            # persistent Current chip for orientation.
            if not current and not active:
                painter.restore()
                continue
            obstacles = [obstacle for _obstacle_slot, obstacle in obstacle_rows] + placed_badges
            canvas_qrect = self._garden_canvas_rect()
            badge = bed_badge_rect(
                layout,
                visual_label,
                self.width(),
                self.height(),
                obstacles,
                canvas_bounds=Rect(
                    canvas_qrect.x(),
                    canvas_qrect.y(),
                    canvas_qrect.width(),
                    canvas_qrect.height(),
                ),
            )
            placed_badges.append(badge)
            badge_rect = QRectF(badge.x, badge.y, badge.width, badge.height)
            if active:
                badge_pen = QColor(GARDEN_THEME["action_hover"])
                badge_fill = QColor(24, 70, 56, 232)
                badge_text = QColor(GARDEN_THEME["text_primary"])
            elif swap_target:
                badge_pen = QColor(GARDEN_THEME["action_accent"])
                badge_pen.setAlpha(180)
                badge_fill = QColor(24, 70, 56, 210)
                badge_text = QColor(GARDEN_THEME["text_primary"])
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
            badge_font = painter.font()
            badge_font.setPointSizeF(12.0)
            badge_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(badge_font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, visual_label)
            self._painted_move_labels[int(slot)] = visual_label
            painter.restore()

    def _draw_move_preview(self, painter: QPainter, destination_slot: int) -> None:
        plant_id = str(self._interaction.dragged_id or self._interaction.pinned_id or "")
        plant = self._plant_for_id(plant_id)
        origin = self._slot_placements.get(self._interaction.drag_origin_slot)
        destination = self._slot_placements.get(int(destination_slot))
        if plant is None or origin is None or destination is None:
            return
        origin_x = origin.footprint.x + origin.footprint.width / 2
        destination_x = destination.footprint.x + destination.footprint.width / 2
        painter.save()
        painter.setOpacity(0.46)
        painter.translate(destination_x - origin_x, destination.depth - origin.depth)
        if not self._draw_plant_asset(painter, origin, plant):
            self._draw_plant(
                painter,
                origin_x,
                origin.depth,
                plant,
                max(0, int(destination_slot)),
            )
        self._draw_mastery_overlay(painter, origin, plant)
        painter.restore()

    def _event_position(self, event: Any) -> Any:
        return event.position() if hasattr(event, "position") else event.pos()

    def _plant_at(self, position: Any) -> str | None:
        candidates: list[tuple[float, str]] = []
        for plant_id, hit_rect in self._plant_hit_rects.items():
            if not hit_rect.contains(position):
                continue
            plant = self._plant_for_id(plant_id)
            slot = int(plant.get("slot_index", -1)) if plant is not None else -1
            layout = self._slot_placements.get(slot)
            candidates.append((float(layout.z_depth) if layout is not None else -1.0, plant_id))
        for _depth, plant_id in sorted(candidates, reverse=True):
            plant = self._plant_for_id(plant_id)
            slot = int(plant.get("slot_index", -1)) if plant is not None else -1
            layout = self._slot_placements.get(slot)
            if plant is None or layout is None:
                continue
            geometry = getattr(self, "_scene_geometry_layout", None)
            bed = geometry.bed(slot) if geometry is not None else None
            if bed is not None and bed.move_target.contains(
                float(position.x()), float(position.y())
            ):
                return plant_id
            path, _placement = self._plant_asset_record(plant)
            pixmap = self._pixmap_for(path) if path else None
            if pixmap is None or pixmap.isNull():
                return plant_id
            box = self._plant_draw_box(layout, plant)
            if not box.contains(position):
                continue
            source_x = int(
                max(0, min(pixmap.width() - 1, (position.x() - box.x()) / max(1.0, box.width()) * pixmap.width()))
            )
            source_y = int(
                max(0, min(pixmap.height() - 1, (position.y() - box.y()) / max(1.0, box.height()) * pixmap.height()))
            )
            if pixmap.toImage().pixelColor(source_x, source_y).alpha() >= 24:
                return plant_id
        return None

    def _announce_focused_plant(self, *, selected: bool = False) -> None:
        keyboard_hint = globals().get(
            "KEYBOARD_HINT",
            "Use the arrow keys to explore plants. Press Enter to open the selected item.",
        )
        plant_ids = self._plant_ids()
        plant_id = self._interaction.pinned_id or self._interaction.focused_id(plant_ids)
        plant = next(
            (row for row in self.scene.get("plants", []) if str(row.get("plant_id", "")) == plant_id),
            None,
        )
        if not isinstance(plant, dict):
            self.setAccessibleDescription(f"Use the arrow keys to explore plants in the garden. {keyboard_hint}")
            return
        name = str(plant.get("name") or plant.get("species") or "Plant")
        species = str(plant.get("species") or "plant").replace("_", " ").title()
        stage = str(plant.get("stage") or "seed").replace("_", " ").title()
        nurtured = f" {name} is nurtured." if bool(plant.get("is_active")) else ""
        if selected:
            description = (
                f"{name}, {species}, {stage}, selected. "
                f"Use Tab to reach plant actions and Details in the plant menu."
                f"{nurtured} {keyboard_hint}"
            )
        else:
            description = (
                f"Focused plant: {name}, {species}, {stage}. "
                f"Press Enter to select it, or use the arrow keys to explore."
                f"{nurtured} {keyboard_hint}"
            )
        self.setAccessibleName(f"Garden plant: {name}")
        self.setAccessibleDescription(description)

    def _slot_at(self, position: Any) -> int | None:
        geometry = getattr(self, "_scene_geometry_layout", None)
        if geometry is not None and hasattr(geometry, "beds"):
            matches = [
                bed for bed in geometry.beds
                if bed.hotspot.contains(float(position.x()), float(position.y()))
            ]
            if matches:
                # Foreground beds win the only possible clipped-envelope edge
                # ambiguity, matching the scene's paint order at every DPR.
                return max(matches, key=lambda bed: bed.depth).bed_id
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
        # Slot validity is state, not paint timing. A persistence rollback can
        # refresh the scene payload and restart move mode before the next paint
        # has rebuilt ``_slot_placements``; the unlocked count remains the
        # authoritative source for all six deterministic bed IDs.
        valid = list(range(unlocked))
        if self._allowed_move_slots is not None:
            valid = [slot for slot in valid if slot in self._allowed_move_slots]
        return valid

    def _destination_slots(self) -> list[int]:
        origin = self._interaction.drag_origin_slot
        return [slot for slot in self._valid_slots() if slot != origin]

    def _placement_target_descriptions(self) -> list[str]:
        """Expose the complete six-bed state map to assistive technology."""

        origin = self._interaction.drag_origin_slot
        destinations = set(self._destination_slots())
        unlocked = max(0, min(6, int(self.scene.get("unlocked_slots", 0))))
        occupants = {
            int(plant.get("slot_index", -1)): str(
                plant.get("name") or plant.get("species") or "plant"
            )
            for plant in self.scene.get("plants", [])
        }
        descriptions: list[str] = []
        for slot in range(6):
            state = move_target_state(
                slot,
                origin_slot=origin,
                valid_destination_slots=destinations,
                unlocked_slots=unlocked,
            )
            occupant = occupants.get(slot, "")
            if state == "current":
                label = "current bed"
            elif state == "locked":
                label = "locked bed"
            elif state == "unavailable" and occupant:
                label = f"occupied by {occupant}; invalid destination"
            elif state == "unavailable":
                label = "invalid destination"
            elif occupant:
                label = f"occupied by {occupant}"
            elif self._starter_placement or origin is None:
                label = "place here"
            else:
                label = "move here"
            descriptions.append(f"Garden bed {slot + 1}: {label}")
        return descriptions

    def _placement_accessible_description(self, introduction: str) -> str:
        target_map = "; ".join(self._placement_target_descriptions())
        return (
            f"{introduction} {target_map}. Use the arrow keys to move among available beds, "
            "then press Enter. Press Escape to cancel."
        )

    def _cycle_destination(self, direction: int) -> int | None:
        destination = self._interaction.cycle_destination(self._valid_slots(), direction)
        if destination == self._interaction.drag_origin_slot and self._destination_slots():
            destination = self._interaction.cycle_destination(self._valid_slots(), direction)
        self._announce_destination(destination)
        return destination

    def _spatial_destination(self, key: Any) -> int | None:
        """Choose the nearest valid bed in the pressed visual direction."""

        destinations = self._destination_slots()
        if not destinations:
            return None
        current_slot = self._interaction.destination_slot
        current_bed = (
            self._scene_geometry_layout.bed(current_slot)
            if self._scene_geometry_layout is not None and current_slot is not None
            else None
        )
        if current_bed is None:
            chosen = destinations[0]
            self._interaction.choose_destination(chosen, destinations)
            self._announce_destination(chosen)
            return chosen
        origin_x = current_bed.move_target.x + current_bed.move_target.width / 2
        origin_y = current_bed.move_target.y + current_bed.move_target.height / 2
        direction = {
            Qt.Key.Key_Left: (-1.0, 0.0),
            Qt.Key.Key_Right: (1.0, 0.0),
            Qt.Key.Key_Up: (0.0, -1.0),
            Qt.Key.Key_Down: (0.0, 1.0),
        }.get(key)
        if direction is None:
            return None
        dx_direction, dy_direction = direction
        candidates: list[tuple[float, float, int]] = []
        for slot in destinations:
            if slot == current_slot or self._scene_geometry_layout is None:
                continue
            bed = self._scene_geometry_layout.bed(slot)
            if bed is None:
                continue
            x = bed.move_target.x + bed.move_target.width / 2
            y = bed.move_target.y + bed.move_target.height / 2
            dx = x - origin_x
            dy = y - origin_y
            primary = dx * dx_direction + dy * dy_direction
            if primary <= 0:
                continue
            cross = abs(dx * dy_direction - dy * dx_direction)
            candidates.append((cross * 2.0 + primary, primary, slot))
        if candidates:
            chosen = min(candidates)[2]
        else:
            # Wrap to the far edge in the requested direction while keeping
            # perpendicular travel as small as possible.
            edge_candidates: list[tuple[float, float, int]] = []
            for slot in destinations:
                if self._scene_geometry_layout is None:
                    continue
                bed = self._scene_geometry_layout.bed(slot)
                if bed is None:
                    continue
                x = bed.move_target.x + bed.move_target.width / 2
                y = bed.move_target.y + bed.move_target.height / 2
                primary = x * dx_direction + y * dy_direction
                cross = abs((x - origin_x) * dy_direction - (y - origin_y) * dx_direction)
                edge_candidates.append((-primary, cross, slot))
            chosen = min(edge_candidates)[2] if edge_candidates else destinations[0]
        self._interaction.choose_destination(chosen, destinations)
        self._announce_destination(chosen)
        return chosen

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
        if (
            (
                getattr(self, "_starter_placement", False)
                or self._interaction.drag_origin_slot is None
                or self._interaction.drag_origin_slot < 0
            )
            and label == "Move here"
        ):
            label = "Place here"
        self.setAccessibleName(f"Garden bed {slot + 1}: {label}")
        self.setAccessibleDescription(
            f"Garden bed {slot + 1} selected: {label}. "
            "Press Enter to confirm, or Escape to cancel. "
            + "; ".join(self._placement_target_descriptions())
        )

    def _finish_move_accessibility(self, message: str) -> None:
        self.setAccessibleName("Interactive garden")
        self.setAccessibleDescription(message)
        normalized = str(message or "").lower()
        self.accessibility_announcer.announce(
            message,
            priority=(
                AnnouncementPriority.ASSERTIVE
                if any(
                    token in normalized
                    for token in ("failed", "could not", "unavailable", "error")
                )
                else AnnouncementPriority.POLITE
            ),
        )

    def _begin_move(self, plant_id: str, *, keyboard: bool) -> bool:
        origin = self._slot_for_plant(plant_id)
        if origin is None:
            return False
        started = self._interaction.begin_placement(plant_id, origin, self._valid_slots(), keyboard=keyboard)
        if started:
            name = self._plant_for_id(plant_id).get("name", "plant")
            self._inline_message = "Select a destination bed."
            self.setAccessibleName(f"Move {name}. Select a destination bed.")
            self.setAccessibleDescription(
                self._placement_accessible_description(
                    "Select a destination bed."
                )
            )
        return started

    def _clear_hover(self) -> None:
        self._interaction.hover(None)
        sync_animation = getattr(self, "_sync_animation_timer", None)
        if callable(sync_animation):
            sync_animation()
        elif not self.timer.isActive():
            self._hover_opacity.clear()
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
            valid_destinations = set(self._destination_slots())
            target_state = move_target_state(
                hover_slot,
                origin_slot=self._interaction.drag_origin_slot,
                valid_destination_slots=valid_destinations,
                unlocked_slots=unlocked,
            )
            hover_changed = hover_slot != self._hovered_move_slot
            self._hovered_move_slot = hover_slot
            # Destination meaning is painted in the scene and announced to
            # assistive technology. Native tooltips obscure neighboring beds,
            # so they are intentionally suppressed for the complete move mode.
            QToolTip.hideText()
            if target_state == "locked":
                self._inline_message = "That bed is locked."
            elif target_state == "unavailable":
                self._inline_message = "Choose another bed."
            elif target_state == "current":
                self._inline_message = "Current bed."
            elif target_state == "valid":
                occupied = {
                    int(plant.get("slot_index", -1))
                    for plant in self.scene.get("plants", [])
                }
                occupant_names = {
                    int(plant.get("slot_index", -1)): str(
                        plant.get("name") or plant.get("species") or "plant"
                    )
                    for plant in self.scene.get("plants", [])
                }
                projected = bed_interaction_state(
                    int(hover_slot),
                    origin_slot=self._interaction.drag_origin_slot,
                    destination_slot=int(hover_slot),
                    unlocked_slots=unlocked,
                    occupied_slots=occupied,
                    occupant_names=occupant_names,
                    starter_placement=bool(
                        getattr(self, "_starter_placement", False)
                        or self._interaction.drag_origin_slot is None
                        or self._interaction.drag_origin_slot < 0
                    ),
                )
                self._inline_message = f"{projected.label}."
            if self._press_plant_id and self._press_position is not None:
                delta = position - self._press_position
                if not self._drag_started and (abs(delta.x()) + abs(delta.y())) >= 8:
                    self._drag_started = True
                if self._drag_started:
                    self._drag_position = position
                    valid = target_state == "valid"
                    if valid and self._interaction.choose_destination(hover_slot, list(valid_destinations)):
                        self._announce_destination(hover_slot)
                    self.setCursor(
                        Qt.CursorShape.ClosedHandCursor
                        if valid else Qt.CursorShape.ForbiddenCursor
                    )
                    self.update()
                    return
            if target_state == "valid":
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif target_state == "unavailable":
                self.setCursor(Qt.CursorShape.ForbiddenCursor)
            else:
                self.unsetCursor()
            if hover_changed:
                self.update()
            super().mouseMoveEvent(event)
            return
        plant_id = self._plant_at(position)
        if self._interaction.pinned_id is not None:
            # A pinned selection owns the highlight channel. Other plants stay
            # clickable without flashing hover outlines behind the popover.
            if self._interaction.hovered_id != self._interaction.pinned_id:
                self._interaction.hover(self._interaction.pinned_id)
                self._hover_opacity.clear()
                self.update()
            if plant_id:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            super().mouseMoveEvent(event)
            return
        if plant_id:
            self._hover_close_timer.stop()
            self._interaction.hover(plant_id)
            sync_animation = getattr(self, "_sync_animation_timer", None)
            if callable(sync_animation):
                sync_animation()
            elif not self.timer.isActive():
                self._hover_opacity = {plant_id: 1.0}
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()
        else:
            self._hover_close_timer.start()
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if self._interaction.placing:
            self._hovered_move_slot = None
            QToolTip.hideText()
            self.unsetCursor()
            self.update()
        self._hover_close_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event: Any) -> None:
        if not self.interactive or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = self._event_position(event)
        if self._interaction.placing and not self._drag_started:
            slot = self._slot_at(position)
            if slot == self._interaction.drag_origin_slot:
                self._inline_message = "Current bed."
                self.update()
                return
            if slot is not None:
                if self._interaction.choose_destination(slot, self._destination_slots()):
                    self._announce_destination(slot)
                    if self._starter_placement:
                        self._inline_message = f"Bed {slot + 1} selected"
                        self.placementDestinationChanged.emit(int(slot))
                        self.update()
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
                    if (
                        (
                            getattr(self, "_starter_placement", False)
                            or self._interaction.drag_origin_slot is None
                            or self._interaction.drag_origin_slot < 0
                        )
                        and label == "Move here"
                    ):
                        label = "Place here"
                    request = self._interaction.complete_placement()
                    if request is not None:
                        self._inline_message = f"Saving {label.lower()}…"
                        self.setAccessibleDescription(
                            f"{label} selected for garden bed {slot + 1}. Saving move."
                        )
                        self._emit_placement_request(request)
                else:
                    state = move_target_state(
                        slot,
                        origin_slot=self._interaction.drag_origin_slot,
                        valid_destination_slots=self._destination_slots(),
                        unlocked_slots=int(self.scene.get("unlocked_slots", 0)),
                    )
                    self._inline_message = (
                        "That bed is locked"
                        if state == "locked" else
                        "Choose another bed"
                    )
                    self.setAccessibleName(
                        f"Garden bed {slot + 1}: "
                        + ("Locked" if state == "locked" else "Invalid destination")
                    )
                    self.setAccessibleDescription(
                        f"{self._inline_message}. "
                        + "; ".join(self._placement_target_descriptions())
                        + ". Press Escape to cancel."
                    )
                    self.accessibility_announcer.announce(
                        self._inline_message,
                        priority=AnnouncementPriority.POLITE,
                        target=self,
                    )
                self.update()
                return
            # Clicking outside a destination is intentionally inert. Escape or
            # the visible Back/Cancel action remains the cancellation path.
            self._inline_message = "Choose a bed."
            self.update()
            return
        plant_id = self._plant_at(position)
        if plant_id:
            self._press_position = position
            self._press_plant_id = plant_id
            self._drag_started = False
            self.setFocus()
        else:
            self._interaction.cancel_placement()
            was_selected = self._interaction.pinned_id is not None
            self._interaction.dismiss()
            if was_selected:
                self.set_keyboard_hint_suppressed(False)
            self._inline_message = ""
            if was_selected:
                self._announce_focused_plant()
                self.selectionChanged.emit("")
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if not self.interactive or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        position = self._event_position(event)
        if self._drag_started:
            slot = self._slot_at(position)
            origin = self._interaction.drag_origin_slot
            destinations = self._destination_slots()
            valid = slot in destinations if slot is not None else False
            if valid and self._interaction.choose_destination(slot, destinations):
                self._announce_destination(slot)
            # Never reuse a previously highlighted destination when the mouse
            # is released over a locked, unavailable, or outside region.
            request = self._interaction.complete_placement() if valid else None
            if request is not None and request[1] != origin:
                self._inline_message = "Saving move…"
                self.setAccessibleDescription("Saving the selected plant move.")
                self._emit_placement_request(request)
            else:
                self.cancel_move()
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
                    self.set_keyboard_hint_suppressed(True)
                    self._announce_focused_plant(selected=True)
                elif was_pinned and not self._interaction.pinned_id:
                    self.set_keyboard_hint_suppressed(False)
                    self._announce_focused_plant()
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
            if event.key() in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
            ):
                self._hovered_move_slot = None
                self._spatial_destination(event.key())
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                origin = self._interaction.drag_origin_slot
                destination = self._interaction.destination_slot
                request = (
                    self._interaction.complete_placement()
                    if destination is not None and destination != origin
                    else None
                )
                if request is not None and request[1] != origin:
                    self._inline_message = "Saving move…"
                    self.setAccessibleDescription("Saving the selected plant move.")
                    self._emit_placement_request(request)
                else:
                    # The source bed is context, not a cancellation shortcut.
                    # Keep move mode active until a valid destination is chosen
                    # or the explicit Cancel/Escape path is used.
                    self._inline_message = "Current bed."
                    self.update()
            elif event.key() == Qt.Key.Key_Escape:
                self.cancel_move()
            else:
                super().keyPressEvent(event)
                return
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._interaction.cycle_focus(plant_ids, -1)
            self._announce_focused_plant()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._interaction.cycle_focus(plant_ids, 1)
            self._announce_focused_plant()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            focused = self._interaction.focused_id(plant_ids)
            if focused:
                self._interaction.toggle_pin(focused)
                self._inline_message = ""
                if self._interaction.pinned_id:
                    self.set_keyboard_hint_suppressed(True)
                    self._announce_focused_plant(selected=True)
                else:
                    self.set_keyboard_hint_suppressed(False)
                    self._announce_focused_plant()
                self.selectionChanged.emit(self._interaction.pinned_id or "")
        elif event.key() == Qt.Key.Key_Escape:
            was_selected = self._interaction.pinned_id is not None
            self._interaction.dismiss()
            if was_selected:
                self.set_keyboard_hint_suppressed(False)
            self._inline_message = ""
            if was_selected:
                self._announce_focused_plant()
                self.selectionChanged.emit("")
        else:
            super().keyPressEvent(event)
            return
        sync_animation = getattr(self, "_sync_animation_timer", None)
        if callable(sync_animation):
            sync_animation()
        self.update()

    def focusInEvent(self, event: Any) -> None:
        if self._interaction.focused_index < 0:
            self._interaction.cycle_focus(self._plant_ids(), 1)
        reason = event.reason() if hasattr(event, "reason") else None
        keyboard_reasons = {
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        }
        if reason in keyboard_reasons:
            self._show_keyboard_hint()
        self._announce_focused_plant()
        self._sync_animation_timer()
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        self._interaction.hover(None)
        self._hide_keyboard_hint()
        super().focusOutEvent(event)
        self._sync_animation_timer()
        self.update()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._invalidate_layout_cache()
        self._position_keyboard_hint()
        self._sync_landmark_hotspot()
        QTimer.singleShot(0, self.cardGeometryChanged.emit)

    def changeEvent(self, event: Any) -> None:
        event_type = event.type() if hasattr(event, "type") else None
        type_enum = getattr(QEvent, "Type", None)
        geometry_events = {
            value
            for value in (
                getattr(type_enum, "DevicePixelRatioChange", None),
                getattr(type_enum, "ScreenChangeInternal", None),
                getattr(type_enum, "ApplicationFontChange", None),
            )
            if value is not None
        }
        if event_type in geometry_events:
            self._scene_geometry_layout = None
            self._clear_hit_targets()
            self.update()
            QTimer.singleShot(0, self.cardGeometryChanged.emit)
        super().changeEvent(event)

    def _position_keyboard_hint(self) -> None:
        if not hasattr(self, "_keyboard_hint"):
            return
        canvas = self._garden_canvas_rect()
        width = max(1, min(440, int(canvas.width()) - 24))
        self._keyboard_hint.setFixedWidth(width)
        height = max(28, self._keyboard_hint.sizeHint().height())
        self._keyboard_hint.setGeometry(
            max(int(canvas.left()) + 12, int(canvas.center().x() - width / 2)),
            max(int(canvas.top()) + 8, int(canvas.bottom()) - height - 12),
            width,
            height,
        )

    def _show_keyboard_hint(self) -> None:
        if (
            getattr(self, "_keyboard_hint_suppressed", False)
            or self._interaction.pinned_id is not None
        ):
            self._hide_keyboard_hint()
            return
        self._position_keyboard_hint()
        self._keyboard_hint.show()
        self._keyboard_hint.raise_()
        self._keyboard_hint_timer.start()

    def _hide_keyboard_hint(self) -> None:
        self._keyboard_hint_timer.stop()
        self._keyboard_hint.hide()

    def _file_identity_for(self, path: str | Path) -> tuple[int, int, int, int] | None:
        """Return one cached filesystem identity for the current scene epoch."""

        normalized = str(Path(path).expanduser())
        cache = getattr(self, "_file_identity_cache", None)
        if cache is not None and normalized in cache:
            return cache.get(normalized)
        try:
            metadata = Path(normalized).stat()
            identity = (
                int(metadata.st_dev),
                int(metadata.st_ino),
                int(metadata.st_size),
                int(metadata.st_mtime_ns),
            ) if stat.S_ISREG(metadata.st_mode) else None
        except (OSError, ValueError):
            identity = None
        if cache is not None:
            cache[normalized] = identity
        return identity

    @staticmethod
    def _plant_asset_identity_matches(plant: dict[str, Any], value: Any) -> bool:
        """Return whether a resolved catalog asset belongs to this plant view."""

        if not isinstance(value, dict):
            return True
        metadata = value.get("metadata", {})
        slot = metadata.get("slot", {}) if isinstance(metadata, dict) else {}
        if not isinstance(slot, dict):
            return True
        for plant_key, slot_key in (("species", "species"), ("stage", "stage")):
            expected = str(plant.get(plant_key, "") or "").strip().casefold()
            actual = str(slot.get(slot_key, "") or "").strip().casefold()
            if expected and actual and expected != actual:
                return False
        return True

    def _plant_asset_record(
        self,
        plant: dict[str, Any],
    ) -> tuple[str | None, dict[str, Any]]:
        value = plant.get("asset") or plant.get("image_path")
        if not self._plant_asset_identity_matches(plant, value):
            return None, {}
        return self._asset_record("plant", value)

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
        if (
            path.suffix.lower() not in {".svg", ".png", ".webp"}
            or self._file_identity_for(path) is None
        ):
            return None, placement
        return str(path), placement

    def _asset_path(self, key: str) -> str | None:
        return self._asset_record(key)[0]

    def _surface_asset_record(
        self, width: float, height: float, *, surface_context: str = "dashboard"
    ) -> tuple[str | None, str | None, dict[str, Any], str]:
        cache_key = (float(width), float(height), str(surface_context))
        cache = getattr(self, "_surface_asset_cache", None)
        if cache is not None and cache_key in cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached  # type: ignore[return-value]
        asset_paths = self.scene.get("asset_paths", {})
        background = asset_paths.get("background", {}) if isinstance(asset_paths, dict) else {}
        if not isinstance(background, dict):
            result = (None, None, {}, "")
            if cache is not None:
                cache[cache_key] = result
            return result
        placement = background.get("placement", {})
        if not isinstance(placement, dict):
            placement = {}
        variant_name, variant = scene_surface_variant(
            placement, width, height, surface_context
        )
        root = Path(str(background.get("asset_root", ""))).expanduser()
        root_valid = root.is_dir()
        root_resolved = root.resolve() if root_valid else root

        def resolve(key: str) -> str | None:
            rel = str(variant.get(key, ""))
            if not rel or not root_valid:
                return None
            candidate = (root / rel).resolve()
            try:
                candidate.relative_to(root_resolved)
            except (OSError, ValueError):
                return None
            if (
                candidate.suffix.lower() not in {".png", ".webp"}
                or self._file_identity_for(candidate) is None
            ):
                return None
            return str(candidate)

        result = (resolve("file"), resolve("occlusion_file"), variant, variant_name)
        if cache is not None:
            cache[cache_key] = result
        return result

    def _surface_occlusion_path(self, width: float, height: float, layer: str) -> str | None:
        cache_key = (float(width), float(height), str(layer))
        cache = getattr(self, "_surface_occlusion_cache", None)
        if cache is not None and cache_key in cache:
            return cache.get(cache_key)
        asset_paths = self.scene.get("asset_paths", {})
        background = asset_paths.get("background", {}) if isinstance(asset_paths, dict) else {}
        if not isinstance(background, dict):
            return None
        _background_path, _legacy_path, variant, _variant_name = self._surface_asset_record(width, height)
        layers = variant.get("occlusion_layers", {})
        relative = str(layers.get(layer, "")) if isinstance(layers, dict) else ""
        root = Path(str(background.get("asset_root", ""))).expanduser()
        if not relative or not root.is_dir():
            return None
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except (OSError, ValueError):
            return None
        result = (
            str(candidate)
            if candidate.suffix.lower() in {".png", ".webp"}
            and self._file_identity_for(candidate) is not None
            else None
        )
        if cache is not None:
            cache[cache_key] = result
        return result

    def _planter_family_record(self) -> dict[str, Any]:
        """Return a validated, globally mapped planter family for this scene."""
        if bool(getattr(self, "_planter_family_cache_valid", False)):
            return getattr(self, "_planter_family_cache", {})
        asset_paths = self.scene.get("asset_paths", {})
        background = asset_paths.get("background", {}) if isinstance(asset_paths, dict) else {}
        if not isinstance(background, dict):
            return {}
        placement = background.get("placement", {})
        surface_profile = placement.get("surface_profile", {}) if isinstance(placement, dict) else {}
        family = surface_profile.get("planter_family", {}) if isinstance(surface_profile, dict) else {}
        variants = family.get("variants", {}) if isinstance(family, dict) else {}
        root = Path(str(background.get("asset_root", ""))).expanduser()
        if (
            not isinstance(family, dict)
            or family.get("background_contract") != "bedless_v1"
            or not bool(family.get("replace_surface_occlusion", True))
            or not isinstance(variants, dict)
            or not root.is_dir()
        ):
            self._planter_family_cache = {}
            self._planter_family_cache_valid = True
            return {}
        resolved_variants: dict[str, dict[str, Any]] = {}
        root_resolved = root.resolve()
        identity_getter = getattr(self, "_file_identity_for", None)
        degraded = False
        for variant_name in ("back", "middle", "front"):
            variant = variants.get(variant_name)
            if not isinstance(variant, dict):
                variant = {}
                degraded = True
            resolved = dict(variant)
            for key in ("file", "foreground_file"):
                relative = str(variant.get(key, ""))
                candidate = (root / relative).resolve()
                try:
                    candidate.relative_to(root_resolved)
                except (OSError, ValueError):
                    resolved[key] = ""
                    degraded = True
                    continue
                if (
                    candidate.suffix.lower() not in {".png", ".webp"}
                    or (
                        identity_getter(candidate) is None
                        if callable(identity_getter)
                        else not candidate.is_file()
                    )
                ):
                    resolved[key] = ""
                    degraded = True
                else:
                    resolved[key] = str(candidate)
            resolved_variants[variant_name] = resolved
        result = dict(family)
        result["variants"] = resolved_variants
        result["degraded"] = degraded
        self._planter_family_cache = result
        self._planter_family_cache_valid = True
        return result

    def _planter_layer_record(
        self,
        layout: PlantPlacement,
        family: dict[str, Any],
        *,
        foreground: bool,
    ) -> tuple[str, QRectF] | None:
        """Resolve the exact asset and box used to paint one planter layer."""

        variant_name = {
            "far": "back",
            "middle": "middle",
            "near": "front",
        }.get(str(layout.depth_band), "")
        variants = family.get("variants", {})
        variant = variants.get(variant_name, {}) if isinstance(variants, dict) else {}
        if not isinstance(variant, dict):
            return None
        resolved_box = planter_draw_rect(layout, family)
        box = QRectF(
            resolved_box.x,
            resolved_box.y,
            resolved_box.width,
            resolved_box.height,
        )
        path = str(variant.get("foreground_file" if foreground else "file", ""))
        return path, box

    def _draw_planter_asset_outline(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        *,
        color: str,
        width: float,
        opacity: float,
        family: dict[str, Any] | None = None,
    ) -> bool:
        """Trace the rendered planter alpha instead of drawing a loose ellipse."""

        resolved_family = family if isinstance(family, dict) else self._planter_family_record()
        record = self._planter_layer_record(
            layout,
            resolved_family,
            foreground=False,
        )
        if record is None:
            return False
        path, box = record
        source = self._pixmap_for(path) if path else None
        if source is None or box.width() <= 0 or box.height() <= 0:
            return False
        source_width = max(1, source.width())
        source_height = max(1, source.height())
        scale = min(box.width() / source_width, box.height() / source_height)
        if scale <= 0:
            return False
        target = QRectF(
            box.x() + (box.width() - source_width * scale) / 2,
            box.y() + (box.height() - source_height * scale) / 2,
            source_width * scale,
            source_height * scale,
        )
        source_radius = max(
            1,
            min(12, round(max(1.0, float(width)) / max(0.01, scale))),
        )
        edge = self._highlight_pixmap_for(path, str(color), source_radius)
        if edge is None:
            return False
        padding = source_radius + 1
        edge_target = QRectF(
            target.x() - padding * scale,
            target.y() - padding * scale,
            target.width() + padding * scale * 2,
            target.height() + padding * scale * 2,
        )
        painter.save()
        painter.setOpacity(self._clamp(float(opacity), 0.0, 1.0))
        painter.drawPixmap(edge_target, edge, QRectF(edge.rect()))
        painter.restore()
        return True

    @staticmethod
    def _draw_planter_fallback(
        painter: QPainter,
        box: QRectF,
        *,
        foreground: bool,
        depth_band: str,
    ) -> None:
        """Keep bed support visible when a planter layer cannot be decoded."""

        depth_alpha = {"far": 150, "middle": 174, "near": 198}.get(
            str(depth_band), 174
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rim_height = max(2.0, box.height() * 0.22)
        rim = QRectF(
            box.left() + box.width() * 0.10,
            box.top() + box.height() * 0.31,
            box.width() * 0.80,
            rim_height,
        )
        if foreground:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            edge = QColor("#B59A72")
            edge.setAlpha(min(230, depth_alpha + 28))
            painter.setPen(QPen(edge, max(1.2, box.height() * 0.035)))
            painter.drawArc(rim, 180 * 16, 180 * 16)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            stone = QColor("#6E685E")
            stone.setAlpha(depth_alpha)
            painter.setBrush(stone)
            body = QPainterPath()
            body.moveTo(rim.left(), rim.center().y())
            body.cubicTo(
                rim.left() + box.width() * 0.05,
                box.bottom() - box.height() * 0.08,
                rim.right() - box.width() * 0.05,
                box.bottom() - box.height() * 0.08,
                rim.right(),
                rim.center().y(),
            )
            body.lineTo(rim.left(), rim.center().y())
            body.closeSubpath()
            painter.drawPath(body)
            soil = QColor("#5D402C")
            soil.setAlpha(min(235, depth_alpha + 25))
            painter.setBrush(soil)
            painter.drawEllipse(rim)
        painter.restore()

    def _draw_planter_family_band(
        self,
        painter: QPainter,
        depth_band: str,
        family: dict[str, Any],
        *,
        foreground: bool,
    ) -> bool:
        """Draw only planter art inside fixed slots; plant geometry is untouched."""
        drawn = False
        for layout in sorted(self._slot_placements.values(), key=lambda item: item.z_depth):
            if layout.depth_band != depth_band:
                continue
            record = self._planter_layer_record(
                layout,
                family,
                foreground=foreground,
            )
            if record is None:
                continue
            path, box = record
            layer_drawn = bool(path) and self._draw_asset_contain(
                painter, path, box, opacity=1.0
            )
            if not layer_drawn:
                self._draw_planter_fallback(
                    painter,
                    box,
                    foreground=foreground,
                    depth_band=depth_band,
                )
                layer_drawn = True
            drawn = layer_drawn or drawn
        return drawn

    def _has_split_surface_occlusion(self, width: float, height: float) -> bool:
        return all(self._surface_occlusion_path(width, height, row) for row in ("rear", "front"))

    def _placement_number(self, placement: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
        try:
            return self._clamp(float(placement.get(key, default)), low, high)
        except (TypeError, ValueError):
            return default

    def _renderer_for(self, path: str) -> Any | None:
        if QSvgRenderer is None:
            return None
        identity = self._file_identity_for(path)
        if identity is None:
            return None
        cache_key = (str(path), identity)
        renderer = self._svg_cache.get(cache_key)
        if renderer is None:
            renderer = QSvgRenderer(path)
            self._svg_cache[cache_key] = renderer
        return renderer if renderer.isValid() else None

    def _pixmap_for(self, path: str) -> QPixmap | None:
        identity = self._file_identity_for(path)
        if identity is None:
            return None
        cache_key = (str(path), identity)
        pixmap = self._raster_cache.get(cache_key)
        if pixmap is None:
            pixmap = QPixmap(path)
            self._raster_cache[cache_key] = pixmap
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

    def _draw_background_asset(
        self,
        painter: QPainter,
        rect: Any,
        *,
        edge_rect: Any | None = None,
    ) -> bool:
        fallback_path, _placement = self._asset_record("background")
        surface_path, _occlusion_path, _surface_variant, _variant_name = self._surface_asset_record(
            rect.width(), rect.height()
        )
        path = surface_path or fallback_path
        if not path:
            return False
        box = QRectF(rect)
        foreground_drawn = self._draw_asset_cover(
            painter,
            path,
            box,
            opacity=0.98,
            focal=(0.5, 0.48),
        )
        return foreground_drawn

    def _draw_garden_feature(self, painter: QPainter, rect: QRectF) -> bool:
        if not bool(self.scene.get("garden_feature_visible", True)):
            return False
        feature_path = self._asset_path("garden_feature")
        pad_path = self._asset_path("garden_feature_pad")
        if not feature_path or not pad_path:
            return False
        layout = garden_feature_layout(
            rect.width(),
            rect.height(),
            str(self.scene.get("visible_scenery", "default") or "default"),
        )
        pad_box = QRectF(
            rect.x() + layout.pad.x,
            rect.y() + layout.pad.y,
            layout.pad.width,
            layout.pad.height,
        )
        feature_box = QRectF(
            rect.x() + layout.feature.x,
            rect.y() + layout.feature.y,
            layout.feature.width,
            layout.feature.height,
        )
        painter.save()
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        pad_opacity = 0.94 if layout.presentation_class == "light" else 0.86
        pad_drawn = self._draw_asset_contain(
            painter, pad_path, pad_box, opacity=pad_opacity
        )
        feature_drawn = self._draw_asset_contain(
            painter, feature_path, feature_box, opacity=1.0
        )
        painter.restore()
        if pad_drawn:
            self._feature_layer_trace.append("garden-feature-pad")
        if feature_drawn:
            self._feature_layer_trace.append("garden-feature")
        return feature_drawn

    def _landmark_pixmap(self, path: str) -> QPixmap | None:
        """Light a cached copy for the scene, keeping the cutout fully opaque."""
        brightness, saturation = landmark_scene_lighting(
            str(self.scene.get("visible_scenery", "default")),
        )
        key = (path, self._file_identity_for(path), brightness, saturation)
        cached = self._landmark_lighting_cache.get(key)
        if cached is not None:
            return cached
        source = self._pixmap_for(path)
        if source is None:
            return None
        image = source.scaled(
            512, 512, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ).toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
        tone = QPainter(image)
        tone.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        tone.setOpacity(1.0 - saturation)
        tone.drawImage(0, 0, gray)
        tone.setOpacity(1.0)
        tone.fillRect(image.rect(), QColor(0, 0, 0, round(255 * (1.0 - brightness))))
        tone.end()
        result = QPixmap.fromImage(image)
        self._landmark_lighting_cache[key] = result
        return result

    def _draw_garden_landmark(self, painter: QPainter, rect: QRectF) -> bool:
        """Paint the exact completed Landmark at the Home-shared anchor."""

        landmark_id = str(self.scene.get("landmark_id", "") or "")
        asset_paths = self.scene.get("asset_paths", {})
        value = (
            asset_paths.get("landmark")
            if isinstance(asset_paths, dict)
            else None
        )
        if not landmark_asset_identity_matches(value, landmark_id):
            return False
        path, _placement = self._asset_record("landmark", value)
        if not path:
            return False
        pixmap = self._landmark_pixmap(path)
        if pixmap is None:
            return False
        x, y, width, height = project_landmark_artwork_rect(
            rect.x(),
            rect.y(),
            rect.width(),
            rect.height(),
            landmark_id,
        )
        painter.save()
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        shadow = QRectF(*project_landmark_contact_shadow_rect(
            rect.x(), rect.y(), rect.width(), rect.height(), landmark_id,
        ))
        painter.save()
        painter.translate(shadow.center())
        painter.scale(shadow.width() / 2, shadow.height() / 2)
        gradient = QRadialGradient(0, 0, 1)
        gradient.setColorAt(0, QColor(3, 20, 11, 68))
        gradient.setColorAt(0.55, QColor(3, 20, 11, 32))
        gradient.setColorAt(1, QColor(3, 20, 11, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(-1, -1, 2, 2))
        painter.restore()
        target = QRectF(x, y, width, height)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.restore()
        self._feature_layer_trace.append("garden-landmark")
        return True

    def _draw_surface_occlusion_asset(
        self, painter: QPainter, rect: Any, *, layer: str | None = None
    ) -> bool:
        _background_path, legacy_path, _variant, _variant_name = self._surface_asset_record(
            rect.width(), rect.height()
        )
        path = self._surface_occlusion_path(rect.width(), rect.height(), layer) if layer else legacy_path
        if not path:
            return False
        return self._draw_asset_cover(
            painter,
            path,
            QRectF(rect),
            opacity=1.0,
            focal=(0.5, 0.48),
        )

    def _draw_garden_overlay_asset(self, painter: QPainter, rect: Any) -> bool:
        path, _placement = self._asset_record("garden_overlay")
        if not path:
            return False
        return self._draw_asset_contain(
            painter,
            path,
            QRectF(rect),
            opacity=0.96,
        )

    def _draw_placement_debug(
        self,
        painter: QPainter,
        plant_rows: list[tuple[dict[str, Any], PlantPlacement]],
    ) -> None:
        """Paint semantic placement geometry without changing interaction state."""
        painter.save()
        canvas = self._garden_canvas_rect()
        font = painter.font()
        font.setPointSizeF(max(7.0, min(9.0, canvas.width() / 115.0)))
        painter.setFont(font)
        for z_order, (plant, layout) in enumerate(plant_rows):
            visible = QRectF(
                layout.visible.x,
                layout.visible.y,
                layout.visible.width,
                layout.visible.height,
            )
            envelope = QRectF(
                layout.slot_envelope.x,
                layout.slot_envelope.y,
                layout.slot_envelope.width,
                layout.slot_envelope.height,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(79, 226, 139, 205), 1.2, Qt.PenStyle.DashLine))
            painter.drawRect(visible)
            painter.setPen(QPen(QColor(89, 175, 255, 180), 1.0, Qt.PenStyle.DotLine))
            painter.drawRect(envelope)

            if layout.grounding.shadow_plane:
                shadow_plane = QPainterPath()
                shadow_plane.moveTo(*layout.grounding.shadow_plane[0])
                for point in layout.grounding.shadow_plane[1:]:
                    shadow_plane.lineTo(*point)
                shadow_plane.closeSubpath()
                painter.setPen(QPen(QColor(190, 128, 255, 205), 1.1, Qt.PenStyle.DashLine))
                painter.drawPath(shadow_plane)
            if len(layout.grounding.support_line) >= 2:
                painter.setPen(QPen(QColor(255, 238, 86, 235), 2.0))
                for first, second in zip(
                    layout.grounding.support_line,
                    layout.grounding.support_line[1:],
                ):
                    painter.drawLine(int(first[0]), int(first[1]), int(second[0]), int(second[1]))
            contact = layout.grounding.contact_shadow
            cast = layout.grounding.cast_shadow
            painter.setPen(QPen(QColor(255, 204, 92, 210), 1.0))
            painter.drawRect(QRectF(contact.x, contact.y, contact.width, contact.height))
            painter.setPen(QPen(QColor(180, 110, 66, 205), 1.0, Qt.PenStyle.DotLine))
            painter.drawRect(QRectF(cast.x, cast.y, cast.width, cast.height))

            anchor_x, anchor_y = layout.ground_anchor
            painter.setPen(QPen(QColor(255, 88, 91, 235), 1.6))
            painter.drawLine(int(anchor_x - 6), int(anchor_y), int(anchor_x + 6), int(anchor_y))
            painter.drawLine(int(anchor_x), int(anchor_y - 6), int(anchor_x), int(anchor_y + 6))

            species = str(plant.get("species", "plant")).replace("_", " ").title()
            stage = str(plant.get("stage", "")).title()
            warning = " / ".join(layout.validation_warnings)
            label = (
                f"{species} {stage} | {layout.layout_family} | {layout.surface_kind}/{layout.depth_band} | "
                f"scale {layout.effective_scale:.2f} | light {layout.grounding.lighting.light_amount:.2f} | z {z_order}"
            )
            if warning:
                label += f" | WARNING: {warning}"
            metrics = painter.fontMetrics()
            label_width = min(
                canvas.width() - 8.0,
                float(metrics.horizontalAdvance(label) + 10),
            )
            label_height = float(metrics.height() + 6)
            label_x = max(
                canvas.left() + 4.0,
                min(canvas.right() - label_width - 4.0, visible.x),
            )
            label_y = max(
                canvas.top() + 4.0,
                min(
                    canvas.bottom() - label_height - 4.0,
                    visible.y - label_height - 2.0,
                ),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(10, 20, 18, 210))
            painter.drawRoundedRect(QRectF(label_x, label_y, label_width, label_height), 3.0, 3.0)
            painter.setPen(QPen(QColor(245, 249, 239, 235), 1.0))
            painter.drawText(int(label_x + 5), int(label_y + metrics.ascent() + 3), label)
        painter.restore()

    @staticmethod
    def _plant_draw_box(layout: PlantPlacement, plant: dict[str, Any]) -> QRectF:
        """Return the rendered box, enlarging only hard-to-read seed artwork."""

        box = QRectF(layout.draw.x, layout.draw.y, layout.draw.width, layout.draw.height)
        if str(plant.get("stage") or "").lower() != "seed":
            return box
        scale = 1.12
        width = box.width() * scale
        height = box.height() * scale
        return QRectF(
            box.center().x() - width / 2,
            box.bottom() - height,
            width,
            height,
        )

    def _draw_plant_asset(self, painter: QPainter, layout: PlantPlacement, plant: dict[str, Any]) -> bool:
        path, placement = self._plant_asset_record(plant)
        if not path:
            return False
        box = self._plant_draw_box(layout, plant)
        depth_band = layout.shadow_depth
        theme = str(self.scene.get("theme", "verdant_twilight"))
        if theme in {"verdant_dusk", "verdant_twilight"} and layout.grounding.lighting.tint_alpha > 0:
            lighting = layout.grounding.lighting
            profile = {
                "contrast": lighting.contrast,
                "saturation": lighting.saturation,
                "exposure": lighting.exposure,
                "tint": lighting.tint,
                "tint_alpha": lighting.tint_alpha,
                "light_amount": lighting.light_amount,
                "key_strength": lighting.key_strength,
                "base_ao": lighting.base_ao,
            }
        else:
            canvas = self._garden_canvas_rect()
            profile = theme_integration_profile(
                theme,
                depth_band,
                (layout.ground_anchor[0] - canvas.x())
                / max(1.0, canvas.width()),
                (layout.ground_anchor[1] - canvas.y())
                / max(1.0, canvas.height()),
            )
        source = self._pixmap_for(str(path))
        if source is None:
            return self._draw_asset_contain(painter, str(path), box, opacity=1.0)
        light_bucket = round(float(profile.get("light_amount", .5)) * 20)
        identity = self._file_identity_for(str(path))
        if identity is None:
            return self._draw_asset_contain(painter, str(path), box, opacity=1.0)
        cache_key = (str(path), identity, theme, depth_band, light_bucket)
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
            exposure = float(profile.get("exposure", 0.0))
            if abs(exposure) >= .001:
                grade_painter.fillRect(
                    graded.rect(),
                    QColor(255, 244, 222, round(exposure * 255))
                    if exposure > 0
                    else QColor(15, 24, 22, round(abs(exposure) * 255)),
                )
            key_strength = max(0.0, min(0.08, float(profile.get("key_strength", 0.0))))
            if key_strength:
                key_gradient = QLinearGradient(0, 0, graded.width(), 0)
                key_gradient.setColorAt(0.0, QColor(255, 230, 190, 0))
                key_gradient.setColorAt(1.0, QColor(255, 230, 190, round(key_strength * 255)))
                grade_painter.fillRect(graded.rect(), key_gradient)
            base_ao = max(0.0, min(0.08, float(profile.get("base_ao", 0.0))))
            if base_ao:
                base_gradient = QLinearGradient(0, 0, 0, graded.height())
                base_gradient.setColorAt(0.70, QColor(10, 18, 16, 0))
                base_gradient.setColorAt(1.0, QColor(10, 18, 16, round(base_ao * 255)))
                grade_painter.fillRect(graded.rect(), base_gradient)
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
        painter.setOpacity(1.0)
        painter.drawPixmap(target, graded, QRectF(graded.rect()))
        painter.restore()
        return True

    def _draw_mastery_overlay(
        self,
        painter: QPainter,
        layout: PlantPlacement,
        plant: dict[str, Any],
    ) -> bool:
        """Paint the exact claimed Mastery treatment over its stable plant."""

        plant_id = str(plant.get("plant_id", "") or "")
        rank_id = str(plant.get("mastery_rank_id", "") or "")
        value = plant.get("mastery_asset")
        if (
            not plant_id
            or not mastery_asset_identity_matches(value, rank_id)
        ):
            return False
        path, _placement = self._asset_record("mastery", value)
        if not path:
            return False
        box = self._plant_draw_box(layout, plant)
        padding_x = box.width() * 0.05
        padding_y = box.height() * 0.05
        drawn = self._draw_asset_contain(
            painter,
            path,
            box.adjusted(-padding_x, -padding_y, padding_x, padding_y),
            opacity=0.96,
        )
        if drawn:
            self._feature_layer_trace.append(f"mastery-{rank_id}")
        return drawn

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
        if stage == "rare":
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
