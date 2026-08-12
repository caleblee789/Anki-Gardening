"""Automated UI-face screenshot capture for disposable Anki runs.

Capture logic is intentionally conservative and activated only when
``ANKI_GARDEN_CAPTURE_UI_FACES`` is set. It uses only Qt-native screenshot
paths and closes transient dialogs after each face to keep the sequence stable.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from aqt import mw
from aqt.qt import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QGuiApplication,
    QLabel,
    QMessageBox,
    QTabWidget,
    QTimer,
    Qt,
    QWidget,
)


logger = logging.getLogger(__name__)


CAPTURE_CONTRACT_VERSION = 4
CAPTURE_FACE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "First run",
        (
            "starter-deck-browser-home",
            "starter-overview-home",
            "starter-garden-onboarding",
            "starter-nursery-plants",
        ),
    ),
    (
        "Anki home",
        (
            "deck-browser-home",
            "overview-home",
        ),
    ),
    (
        "Garden",
        (
            "full-garden",
            "selected-plant-not-nurtured",
            "selected-plant-nurtured",
            "fertilizer-unaffordable",
            "fertilizer-affordable",
            "fertilizer-active",
            "move-mode",
            "plant-story",
        ),
    ),
    (
        "Garden Progress",
        (
            "growth-zero",
            "growth-nonzero",
            "streak-new",
            "streak-active",
            "coins-zero",
            "coins-activity",
            "progress-overview",
            "progress-achievements",
            "progress-collection",
        ),
    ),
    ("Customize", ("customize-garden",)),
    (
        "Nursery",
        (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        ),
    ),
    (
        "Settings",
        (
            "settings-menu-display",
            "settings-display",
            "diagnostics-clean",
            "diagnostics-warning",
        ),
    ),
    (
        "Release stress — Garden",
        (
            "long-garden-name",
            "long-plant-name",
            "four-digit-coin-balance",
            "growth-near-stage-completion",
            "all-six-beds-occupied",
            "plant-at-every-stage",
            "popover-plot-1",
            "popover-plot-2",
            "popover-plot-3",
            "popover-plot-4",
            "popover-plot-5",
            "popover-plot-6",
            "move-occupied-empty-destinations",
            "fertilizer-expiring-under-minute",
            "fertilizer-replacement-confirmation",
        ),
    ),
    (
        "Release stress — Progress",
        (
            "collection-several-discovered",
            "collection-no-filter-matches",
            "achievement-completed",
            "streak-at-risk",
            "streak-missed-day",
            "streak-reward-claimed-unclaimed",
        ),
    ),
    (
        "Release stress — Nursery",
        (
            "nursery-item-owned",
            "nursery-item-locked",
            "nursery-purchase-success",
        ),
    ),
    (
        "Release stress — Settings",
        (
            "settings-unsaved-changes",
            "settings-validation-error",
            "diagnostics-expanded",
        ),
    ),
    (
        "Accessibility and responsive",
        (
            "reduced-motion-enabled",
            "keyboard-focus-state",
            "narrow-window-responsive",
            "display-scaling-150",
        ),
    ),
)
CAPTURE_FACE_LABELS = tuple(
    label
    for _group, labels in CAPTURE_FACE_GROUPS
    for label in labels
)


def start_capture(app: Any) -> None:
    """Launch the UI-face capture sequence for a running add-on instance."""
    _UiFaceCaptureRunner(app).start()


class _UiFaceCaptureRunner:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.capture_root = Path(
            os.environ.get(
                "ANKI_GARDEN_UI_CAPTURE_DIR",
                os.environ.get(
                    "ANKI_GARDEN_CAPTURE_DIR",
                    str(Path(__file__).resolve().parent / ".." / "build" / "ui-face-captures"),
                ),
            )
        ).expanduser()
        self.session_dir = self.capture_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._screenshots: list[str] = []
        self._capture_records: list[dict[str, Any]] = []
        self._text_layout_warnings: list[dict[str, Any]] = []
        self._failures: list[dict[str, str]] = []
        self._step_index = 0
        self._capture_index = 1
        self._starter_seed_attempts = 0
        self._capture_display = "primary"
        self._requested_scale_factor = os.environ.get("QT_SCALE_FACTOR", "system")
        self._phase = "starter"
        self._starter_steps = [
            self._capture_starter_deck_browser,
            self._capture_starter_overview,
            self._capture_starter_garden,
            self._capture_starter_nursery,
        ]
        self._release_steps = [
            self._capture_deck_browser,
            self._capture_overview,
            self._capture_full_garden,
            self._capture_selected_card,
            self._capture_nurture,
            self._capture_fertilize,
            self._capture_fertilize_affordable,
            self._capture_fertilize_active,
            self._capture_move,
            self._capture_story,
            self._capture_growth_zero,
            self._capture_growth_nonzero,
            self._capture_streak_new,
            self._capture_streak_active,
            self._capture_coins_zero,
            self._capture_coins_activity,
            self._capture_progress_today,
            self._capture_progress_achievements,
            self._capture_progress_collection,
            self._capture_customize_garden,
            self._capture_nursery_plants,
            self._capture_nursery_fertilizer_booster,
            self._capture_nursery_garden_spaces,
            self._capture_nursery_weather_scenery,
            self._capture_addon_settings_menu,
            self._capture_settings_display,
            self._capture_settings_troubleshooting,
            self._capture_settings_warning,
            self._capture_long_garden_name,
            self._capture_long_plant_name,
            self._capture_four_digit_coin_balance,
            self._capture_growth_near_stage_completion,
            self._capture_all_six_beds,
            self._capture_all_six_stages,
            *(lambda slot=slot: self._capture_popover_slot(slot) for slot in range(6)),
            self._capture_move_mixed_destinations,
            self._capture_fertilizer_expiring,
            self._capture_fertilizer_replacement_confirmation,
            self._capture_collection_several,
            self._capture_collection_no_matches,
            self._capture_achievement_completed,
            self._capture_streak_at_risk,
            self._capture_streak_missed_day,
            self._capture_streak_reward_states,
            self._capture_nursery_owned_item,
            self._capture_nursery_locked_item,
            self._capture_nursery_purchase_success,
            self._capture_settings_unsaved,
            self._capture_settings_validation_error,
            self._capture_diagnostics_expanded,
            self._capture_reduced_motion,
            self._capture_keyboard_focus,
            self._capture_narrow_window,
            self._capture_display_scaling,
        ]
        self._steps = self._starter_steps

    def start(self) -> None:
        """Kick off capture after collection load and dashboard prerequisites."""
        self._wait_for_collection(self._prepare_capture_window, tries=120)

    def _prepare_capture_window(self) -> None:
        self._move_to_capture_display(mw)
        QTimer.singleShot(300, self._prepare_starter_phase)

    def _prepare_starter_phase(self, *, tries: int = 80) -> None:
        """Require the disposable profile's untouched first-run state."""
        state = getattr(self.app.storage, "state", None)
        if state is None:
            if tries <= 0:
                self._failures.append({
                    "label": "starter-state",
                    "reason": "Garden state was unavailable before first-run capture",
                })
                self._next_step()
                return
            QTimer.singleShot(
                120,
                lambda: self._prepare_starter_phase(tries=tries - 1),
            )
            return
        if bool(getattr(state, "starter_selection_complete", False)) or list(
            getattr(state, "plants", []) or []
        ):
            self._failures.append({
                "label": "starter-state",
                "reason": "Disposable profile was not in untouched first-run state",
            })
        self._next_step()

    def _move_to_capture_display(self, widget: Any | None) -> None:
        """Use the second display for isolated capture when one is available."""
        if widget is None:
            return
        if os.environ.get("ANKI_GARDEN_CAPTURE_SECOND_MONITOR", "1").lower() in {"0", "false", "no"}:
            return
        try:
            screens = list(QGuiApplication.screens())
        except Exception:
            screens = []
        if len(screens) < 2:
            return
        screen = screens[1]
        try:
            handle = widget.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
            geometry = screen.availableGeometry()
            current = widget.size()
            maximum_width = max(320, geometry.width() - 48)
            maximum_height = max(240, geometry.height() - 48)
            if current.width() > maximum_width or current.height() > maximum_height:
                widget.resize(
                    min(current.width(), maximum_width),
                    min(current.height(), maximum_height),
                )
            widget.move(geometry.x() + 24, geometry.y() + 24)
            self._capture_display = "secondary"
        except Exception:
            logger.debug("Anki Garden capture: could not move to second display", exc_info=True)

    def _prepare_capture_state(self) -> None:
        if self._ensure_capture_state():
            reset = getattr(mw, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception:
                    logger.debug("Anki Garden capture: seeded Home refresh failed", exc_info=True)
            self._phase = "release"
            self._steps = self._release_steps
            self._step_index = 0
            QTimer.singleShot(800, self._next_step)
            return
        if self._starter_seed_attempts >= 80:
            self._next_step()
            return
        self._starter_seed_attempts += 1
        QTimer.singleShot(250, self._prepare_capture_state)

    def _ensure_capture_state(self) -> bool:
        """Make capture deterministic by ensuring at least one planted starter exists."""
        state = getattr(self.app.storage, "state", None)
        if state is None:
            return False
        plants = list(getattr(state, "plants", []) or [])
        if bool(getattr(state, "starter_selection_complete", False)) and plants:
            if not getattr(state, "active_plant_id", None):
                for candidate in plants:
                    plant_id = getattr(candidate, "plant_id", "")
                    if plant_id:
                        self.app.engine.set_active_plant(plant_id)
                        break
            return True
        ready = getattr(self.app.engine, "release_ready_species", None)
        choose_starter = getattr(self.app.engine, "choose_starter", None)
        if ready is None or choose_starter is None:
            return True
        try:
            candidates = list(ready())
        except Exception:
            return False
        if not candidates:
            return False
        species = str(candidates[0]).lower()
        try:
            ok, _message, plant = choose_starter(species)
            if ok and plant is not None:
                try:
                    self.app.storage.state.starter_selection_complete = True
                except Exception:
                    pass
                try:
                    self.app.storage.state.active_plant_id = getattr(plant, "plant_id", "")
                except Exception:
                    pass
                return True
        except Exception:
            logger.debug("Anki Garden capture: starter bootstrap waiting for scheduler", exc_info=True)
        return False

    def _next_step(self) -> None:
        if self._step_index >= len(self._steps):
            if self._phase == "starter":
                self._phase = "seeding"
                self._close_top_level_dialogs()
                self._close_dashboard()
                QTimer.singleShot(350, self._prepare_capture_state)
                return
            self._finish()
            return
        current = self._steps[self._step_index]
        self._step_index += 1
        try:
            current()
        except Exception:
            logger.exception("Anki Garden capture: step failed, moving on")
            self._next_after(300)

    def _next_after(self, delay_ms: int) -> None:
        QTimer.singleShot(max(80, int(delay_ms)), self._next_step)

    def _wait_for_collection(self, ready: Callable[[], None], *, tries: int = 40) -> None:
        collection = getattr(mw, "col", None)
        if collection is not None and getattr(collection, "db", None) is not None:
            ready()
            return
        if tries <= 0:
            ready()
            return
        QTimer.singleShot(120, lambda: self._wait_for_collection(ready, tries=tries - 1))

    def _wait_for_dashboard(self, ready: Callable[[], None], *, tries: int = 80) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        visible = False
        if dashboard is not None:
            try:
                visible = bool(dashboard.isVisible())
            except Exception:
                visible = True
        if visible:
            ready()
            return
        if tries <= 0:
            ready()
            return
        QTimer.singleShot(120, lambda: self._wait_for_dashboard(ready, tries=tries - 1))

    def _wait_for(
        self,
        predicate: Callable[[], bool],
        on_ready: Callable[[], None],
        *,
        tries: int = 80,
        failure_label: str = "",
        failure_reason: str = "",
    ) -> None:
        try:
            if predicate():
                on_ready()
                return
        except Exception:
            pass
        if tries <= 0:
            if failure_label:
                self._failures.append({
                    "label": failure_label,
                    "reason": failure_reason or "Timed out waiting for the requested UI surface",
                })
                self._next_after(120)
                return
            on_ready()
            return
        QTimer.singleShot(
            120,
            lambda: self._wait_for(
                predicate,
                on_ready,
                tries=tries - 1,
                failure_label=failure_label,
                failure_reason=failure_reason,
            ),
        )

    def _wait_for_home_surface(
        self,
        state: str,
        on_ready: Callable[[], None],
        *,
        tries: int = 100,
    ) -> None:
        if str(getattr(mw, "state", "")) != state:
            if tries <= 0:
                self._failures.append({"label": state, "reason": "Anki surface did not become active"})
                self._next_after(120)
                return
            QTimer.singleShot(
                120,
                lambda: self._wait_for_home_surface(state, on_ready, tries=tries - 1),
            )
            return
        web = getattr(mw, "web", None)
        evaluate = getattr(web, "evalWithCallback", None)
        if not callable(evaluate):
            on_ready()
            return
        script = """
            (() => {
              const root = document.querySelector('#ag-home-root');
              if (!root || !['success', 'partial'].includes(root.dataset.state)) return false;
              const rect = root.getBoundingClientRect();
              if (rect.width < 100 || rect.height < 100) return false;
              return [...root.querySelectorAll('img')].every(img => img.complete);
            })()
        """

        def resolved(ready: Any) -> None:
            if bool(ready):
                QTimer.singleShot(32, on_ready)
            elif tries <= 0:
                self._failures.append({"label": state, "reason": "Home widget never reached painted success or partial state"})
                self._next_after(120)
            else:
                QTimer.singleShot(
                    120,
                    lambda: self._wait_for_home_surface(state, on_ready, tries=tries - 1),
                )

        try:
            evaluate(script, resolved)
        except Exception:
            if tries <= 0:
                self._failures.append({"label": state, "reason": "Home widget readiness evaluation failed"})
                self._next_after(120)
            else:
                QTimer.singleShot(
                    120,
                    lambda: self._wait_for_home_surface(state, on_ready, tries=tries - 1),
                )

    def _with_dashboard(self, on_ready: Callable[[], None]) -> None:
        def prepare_dashboard() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            toast = getattr(dashboard, "toast_region", None)
            clear_toast = getattr(toast, "clear", None)
            if callable(clear_toast):
                clear_toast()
            self._move_to_capture_display(dashboard)
            on_ready()

        dashboard = getattr(self.app, "dashboard", None)
        try:
            if dashboard is not None and bool(dashboard.isVisible()):
                prepare_dashboard()
                return
        except Exception:
            pass
        self.app.open_dashboard()
        self._wait_for_dashboard(prepare_dashboard)

    def _capture_now(self, label: str, widget: Any | None = None) -> None:
        path = self.session_dir / f"{self._capture_index:02d}-{label}.png"
        self._capture_index += 1
        app = QApplication.instance()
        if app is None:
            self._failures.append({"label": label, "reason": "Qt application unavailable"})
            return
        app.processEvents()
        if widget is None:
            self._failures.append({"label": label, "reason": "Expected capture widget was not provided"})
            return
        try:
            if not bool(widget.isVisible()) or widget.width() <= 0 or widget.height() <= 0:
                self._failures.append({"label": label, "reason": "Expected capture widget was not visible with nonzero geometry"})
                return
            self._move_to_capture_display(widget)
            app.processEvents()
            pixmap = widget.grab()
            if pixmap is None:
                self._failures.append({"label": label, "reason": "Qt returned no pixmap"})
                return
            if pixmap.isNull():
                screen = QGuiApplication.primaryScreen()
                if screen is None:
                    self._failures.append({"label": label, "reason": "No screen available for fallback capture"})
                    return
                try:
                    pixmap = screen.grabWindow(int(widget.winId()))
                except Exception:
                    self._failures.append({"label": label, "reason": "Window fallback capture failed"})
                    return
                if pixmap.isNull():
                    self._failures.append({"label": label, "reason": "Captured pixmap was null"})
                    return
            if pixmap.save(str(path), "png"):
                self._screenshots.append(str(path))
                text_layout_warnings = self._find_text_layout_warnings(widget)
                for warning in text_layout_warnings:
                    warning["capture"] = label
                self._text_layout_warnings.extend(text_layout_warnings)
                self._capture_records.append({
                    "label": label,
                    "path": str(path),
                    "widget": type(widget).__name__,
                    "width": int(widget.width()),
                    "height": int(widget.height()),
                    "text_layout_warnings": text_layout_warnings,
                })
            else:
                self._failures.append({"label": label, "reason": "PNG save failed"})
        except Exception:
            self._failures.append({"label": label, "reason": "Unexpected capture exception"})
            logger.debug("Anki Garden capture: screenshot failed for %s", label, exc_info=True)

    @staticmethod
    def _find_text_layout_warnings(root: QWidget) -> list[dict[str, Any]]:
        """Report visible native text whose widget geometry cannot contain it.

        This supplements image review with a deterministic guard against the
        failure mode where Qt compresses a label inside a fixed-height card.
        Scroll-view content is safe: the check compares text with its own
        widget, not with the currently visible part of the viewport.
        """

        warnings: list[dict[str, Any]] = []
        candidates = [root, *root.findChildren(QWidget)]
        for candidate in candidates:
            if not isinstance(candidate, (QLabel, QAbstractButton)):
                continue
            try:
                if not candidate.isVisibleTo(root):
                    continue
                text = str(candidate.text() or "").strip()
                if not text or "<" in text:
                    continue
                metrics = candidate.fontMetrics()
                contents = candidate.contentsRect()
                available_width = max(1, int(contents.width()))
                # Qt style-sheet padding can shrink ``contentsRect()`` even
                # though the label paints and clips against its full widget
                # bounds.  Audit the actual paint boundary vertically, and use
                # tight glyph bounds so ascender/descender leading does not
                # turn compact chips and metric values into false positives.
                available_height = max(1, int(candidate.height()))
                lines = text.splitlines() or [text]
                required_height = 0
                for line in lines:
                    line_height = max(1, int(metrics.tightBoundingRect(line or " ").height()))
                    if isinstance(candidate, QLabel) and candidate.wordWrap():
                        advance = max(1, int(metrics.horizontalAdvance(line or " ")))
                        wrapped_lines = max(1, (advance + available_width - 1) // available_width)
                    else:
                        wrapped_lines = 1
                    required_height += line_height * wrapped_lines

                vertical_clip = required_height > available_height + 2
                horizontal_clip = False
                if isinstance(candidate, QLabel) and not candidate.wordWrap() and "\n" not in text:
                    horizontal_clip = metrics.horizontalAdvance(text) > available_width + 1
                elif isinstance(candidate, QAbstractButton) and len(text) > 2:
                    horizontal_clip = metrics.horizontalAdvance(text) > max(
                        1,
                        available_width - 12,
                    )
                # A label can contain its own glyphs but still be cut off by a
                # fixed-height parent. Walk native ancestors to catch that
                # failure. Content that is intentionally reachable through a
                # scroll bar is exempt only on the scrollable axis.
                ancestor_clip_horizontal = False
                ancestor_clip_vertical = False
                allow_scroll_horizontal = False
                allow_scroll_vertical = False
                scroll_ancestor = candidate.parentWidget()
                while scroll_ancestor is not None:
                    if isinstance(scroll_ancestor, QAbstractScrollArea):
                        allow_scroll_horizontal = allow_scroll_horizontal or (
                            scroll_ancestor.horizontalScrollBarPolicy()
                            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        )
                        allow_scroll_vertical = allow_scroll_vertical or (
                            scroll_ancestor.verticalScrollBarPolicy()
                            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        )
                    if scroll_ancestor is root:
                        break
                    scroll_ancestor = scroll_ancestor.parentWidget()
                ancestor = candidate.parentWidget()
                while ancestor is not None:
                    # A layout container is an implementation detail, not a
                    # paint boundary. Qt can legitimately let a child extend
                    # through that container while the enclosing styled frame
                    # owns the visible surface. Audit native paint boundaries
                    # and the capture root, which catches real card/frame
                    # clipping without treating layout negotiation as damage.
                    checks_paint_boundary = (
                        isinstance(ancestor, (QFrame, QAbstractButton, QAbstractScrollArea))
                        or ancestor is root
                    )
                    if not checks_paint_boundary:
                        ancestor = ancestor.parentWidget()
                        continue
                    position = candidate.mapTo(
                        ancestor,
                        candidate.rect().topLeft(),
                    )
                    left = int(position.x())
                    top = int(position.y())
                    right = left + int(candidate.width())
                    bottom = top + int(candidate.height())
                    if not allow_scroll_horizontal and (
                        left < -2 or right > int(ancestor.width()) + 2
                    ):
                        ancestor_clip_horizontal = True
                    if not allow_scroll_vertical and (
                        top < -2 or bottom > int(ancestor.height()) + 2
                    ):
                        ancestor_clip_vertical = True
                    if ancestor_clip_horizontal or ancestor_clip_vertical or ancestor is root:
                        break
                    ancestor = ancestor.parentWidget()
                horizontal_clip = horizontal_clip or ancestor_clip_horizontal
                vertical_clip = vertical_clip or ancestor_clip_vertical
                if not vertical_clip and not horizontal_clip:
                    continue
                warnings.append({
                    "widget": type(candidate).__name__,
                    "object_name": str(candidate.objectName() or ""),
                    "text": text[:120],
                    "width": int(candidate.width()),
                    "height": int(candidate.height()),
                    "required_height": int(required_height),
                    "horizontal_clip": horizontal_clip,
                    "vertical_clip": vertical_clip,
                    "ancestor_clip_horizontal": ancestor_clip_horizontal,
                    "ancestor_clip_vertical": ancestor_clip_vertical,
                })
            except Exception:
                logger.debug("Anki Garden capture: text geometry audit failed", exc_info=True)
        return warnings

    def _capture_and_advance(
        self,
        label: str,
        widget: Any | None = None,
        *,
        capture_delay_ms: int = 260,
        close_ms: int | None = None,
        close_callback: Callable[[], None] | None = None,
        next_ms: int = 900,
    ) -> None:
        QTimer.singleShot(
            max(20, int(capture_delay_ms)),
            lambda: self._capture_now(label, widget),
        )
        if close_callback is not None:
            if close_ms is None:
                close_ms = max(220, int(capture_delay_ms) + 180)
            QTimer.singleShot(max(60, int(close_ms)), close_callback)
        self._next_after(next_ms)

    def _close_widget(self, widget: Any | None) -> None:
        if widget is None:
            return
        try:
            if isinstance(widget, QDialog):
                # Capture dialogs may be running a nested exec() loop. done()
                # exits that loop directly and avoids first-run prompts reopening
                # before the capture sequence can advance.
                widget.done(0)
            else:
                widget.close()
        except Exception:
            pass

    def _close_top_level_dialogs(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        for window in app.topLevelWidgets():
            if window is mw:
                continue
            if not isinstance(window, QDialog):
                continue
            if not window.isVisible():
                continue
            try:
                window.close()
            except Exception:
                pass

    def _close_dashboard(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        self._close_widget(dashboard)

    def _select_plant(self, *, activate: bool = True) -> str:
        state = getattr(self.app.storage, "state", None)
        plants = list(getattr(state, "plants", []) or []) if state is not None else []
        if not plants:
            return ""
        active_id = getattr(state, "active_plant_id", "")
        if active_id:
            return str(active_id)
        for plant in plants:
            if getattr(plant, "plant_id", ""):
                first = str(plant.plant_id)
                if activate:
                    try:
                        self.app.engine.set_active_plant(first)
                    except Exception:
                        pass
                return first
        return ""

    def _switch_surface(self, state: str) -> None:
        if getattr(mw, "state", None) == state:
            return
        move_to_state = getattr(mw, "moveToState", None)
        if callable(move_to_state):
            try:
                move_to_state(state)
                return
            except Exception:
                logger.debug("Anki Garden capture: moveToState failed for %s", state, exc_info=True)
        for method_name in (
            f"on{state[0].upper() + state[1:]}",
            f"show{state[0].upper() + state[1:]}",
            f"show_{state}",
            state,
        ):
            method = getattr(mw, method_name, None)
            if callable(method):
                try:
                    method()
                except TypeError:
                    method(state)
                except Exception:
                    logger.debug("Anki Garden capture: surface switch failed for %s", method_name, exc_info=True)
                return
        set_state = getattr(mw, "setState", None)
        if callable(set_state):
            try:
                set_state(state)
                return
            except Exception:
                pass
        set_state_old = getattr(mw, "set_state", None)
        if callable(set_state_old):
            try:
                set_state_old(state)
            except Exception:
                pass

    def _find_settings_dialog(self) -> QDialog | None:
        dashboard = getattr(self.app, "dashboard", None)
        dialog = getattr(dashboard, "settings_dialog", None)
        if dialog is not None:
            return dialog
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and "setting" in widget.windowTitle().lower():
                return widget
        return None

    def _set_settings_tab(self, settings_dialog: QDialog | None, index: int) -> None:
        if settings_dialog is None:
            return
        for widget in settings_dialog.findChildren(QTabWidget):
            if widget.count() > index:
                widget.setCurrentIndex(index)
                return

    def _capture_metric(self, metric: str, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(200)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        if dialog is None:
            self._failures.append({
                "label": label,
                "reason": "Garden metric dialog was unavailable",
            })
            self._next_after(200)
            return
        refresh = getattr(dialog, "refresh", None)
        if callable(refresh):
            refresh()
        navigation = getattr(dialog, "navigation", None)
        if navigation is None or metric not in getattr(navigation, "keys", []):
            self._failures.append({
                "label": label,
                "reason": f"Garden Progress page {metric!r} was unavailable",
            })
            self._next_after(200)
            return
        navigation.set_current(metric)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def _dialog_ready() -> None:
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=260,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=620,
                next_ms=1000,
            )
            if dialog is not None:
                QTimer.singleShot(650, lambda: self._close_widget(dialog))
            else:
                # keep moving if dialog creation failed
                QTimer.singleShot(0, self._close_dashboard)

        self._wait_for(
            lambda: bool(
                dialog.isVisible()
                and navigation.stack.currentIndex() == navigation.keys.index(metric)
            ),
            _dialog_ready,
            tries=50,
            failure_label=label,
            failure_reason=f"{metric} metric dialog did not become ready",
        )

    def _capture_starter_deck_browser(self) -> None:
        self._switch_surface("overview")

        def enter_fresh_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            QTimer.singleShot(
                500,
                lambda: self._wait_for_home_surface(
                    "deckBrowser",
                    lambda: self._capture_and_advance(
                        "starter-deck-browser-home",
                        mw,
                        capture_delay_ms=650,
                        next_ms=1200,
                    ),
                ),
            )

        QTimer.singleShot(500, enter_fresh_deck_browser)

    def _capture_starter_overview(self) -> None:
        self._switch_surface("overview")
        QTimer.singleShot(
            350,
            lambda: self._wait_for_home_surface(
                "overview",
                lambda: self._capture_and_advance(
                    "starter-overview-home",
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _capture_starter_garden(self) -> None:
        def dashboard_ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)

            def onboarding_ready() -> None:
                self._capture_and_advance(
                    "starter-garden-onboarding",
                    dashboard,
                    capture_delay_ms=420,
                    next_ms=1000,
                )

            self._wait_for(
                lambda: bool(
                    dashboard is not None
                    and dashboard.isVisible()
                    and getattr(dashboard, "onboarding_panel", None)
                    and dashboard.onboarding_panel.isVisible()
                ),
                onboarding_ready,
                tries=80,
                failure_label="starter-garden-onboarding",
                failure_reason="First-run Garden guidance did not become visible",
            )

        self._with_dashboard(dashboard_ready)

    def _capture_starter_nursery(self) -> None:
        self._with_dashboard(self._capture_starter_nursery_after)

    def _capture_starter_nursery_after(self) -> None:
        from .ui.dashboard import NurseryDialog

        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._failures.append({
                "label": "starter-nursery-plants",
                "reason": "Starter Nursery parent was unavailable",
            })
            self._next_after(250)
            return

        # The product route intentionally uses QDialog.exec(). Capture this
        # surface non-modally so teardown cannot become trapped in that nested
        # event loop while the first-run prompt is still eligible to reopen.
        dialog = NurseryDialog(dashboard, self.app.engine, self.app.storage)
        dashboard.nursery_dialog = dialog
        dialog.catalog_tabs.setCurrentIndex(0)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        self._move_to_capture_display(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def ready() -> None:
            self._capture_and_advance(
                "starter-nursery-plants",
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "nursery_dialog", None)
                    is dialog
                    and dialog.isVisible()
                    and dialog.catalog_tabs.currentIndex() == 0
                    and bool(getattr(dialog, "_starter_mode", False))
                ),
                ready,
                tries=80,
                failure_label="starter-nursery-plants",
                failure_reason="Starter Nursery Plants tab did not become ready",
            ),
        )

    def _capture_deck_browser(self) -> None:
        # A disposable profile starts on Deck Browser before deterministic
        # Garden seeding. Force a real state transition so Anki replaces that
        # pre-seed DOM instead of letting its old successful root satisfy the
        # readiness predicate during the page fade.
        self._switch_surface("overview")

        def enter_fresh_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            QTimer.singleShot(
                500,
                lambda: self._wait_for_home_surface(
                    "deckBrowser",
                    lambda: self._capture_and_advance(
                        "deck-browser-home",
                        mw,
                        capture_delay_ms=650,
                        next_ms=1200,
                    ),
                ),
            )

        QTimer.singleShot(500, enter_fresh_deck_browser)

    def _capture_overview(self) -> None:
        self._switch_surface("overview")
        QTimer.singleShot(
            350,
            lambda: self._wait_for_home_surface(
                "overview",
                lambda: self._capture_and_advance(
                    "overview-home",
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _capture_addon_settings_menu(self) -> None:
        action = getattr(self.app, "_settings_action", None)
        if action is not None and hasattr(action, "trigger"):
            action.trigger()
        else:
            self.app.open_settings()

        def _ready() -> None:
            dialog = self._find_settings_dialog()
            self._capture_and_advance(
                "settings-menu-display",
                dialog,
                capture_delay_ms=400,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=700,
                next_ms=1200,
            )
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            _ready,
            tries=80,
            failure_label="settings-menu-display",
            failure_reason="Settings dialog did not open from the Anki menu action",
        )

    def _capture_full_garden(self) -> None:
        self._with_dashboard(lambda: self._capture_and_advance(
            "full-garden",
            self.app.dashboard,
            capture_delay_ms=500,
            next_ms=900,
        ))

    def _capture_selected_card(self) -> None:
        self._with_dashboard(self._capture_selected_card_after)

    def _capture_selected_card_after(self) -> None:
        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        # Exercise the consequential before-state explicitly; starter creation
        # normally nurtures the first plant immediately.
        self.app.storage.state.active_plant_id = None
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()
        selector = getattr(dashboard, "_on_scene_selection", None)
        keep_open = getattr(getattr(dashboard, "scene", None), "keep_card_open", None)
        if callable(keep_open):
            keep_open(plant_id)
        if callable(selector):
            selector(plant_id)
        self._capture_and_advance(
            "selected-plant-not-nurtured",
            dashboard,
            capture_delay_ms=400,
            next_ms=900,
        )

    def _capture_nurture(self) -> None:
        self._with_dashboard(self._capture_nurture_after)

    def _capture_nurture_after(self) -> None:
        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        nurture = getattr(dashboard, "_nurture_plant", None)
        if callable(nurture):
            nurture(plant_id)
        self._capture_and_advance(
            "selected-plant-nurtured",
            dashboard,
            capture_delay_ms=260,
            next_ms=850,
        )

    def _capture_fertilize(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-unaffordable", "unaffordable")
        )

    def _capture_fertilize_affordable(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-affordable", "affordable")
        )

    def _capture_fertilize_active(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-active", "active")
        )

    def _capture_fertilize_after(self, label: str, state_variant: str) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        state = self.app.storage.state
        plant = self.app.engine.plant_story(plant_id)
        if plant is not None and state_variant in {"unaffordable", "affordable", "active"}:
            plant.fertilizer = None
        state.currency_balance = 0 if state_variant == "unaffordable" else 500
        if state_variant == "active":
            purchase = getattr(self.app.engine, "purchase_fertilizer", None)
            if callable(purchase):
                purchase(plant_id, "basic")
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()
        fertilize = getattr(dashboard, "_open_fertilizer_menu", None)
        if not callable(fertilize):
            self._close_dashboard()
            self._next_after(250)
            return
        def ready() -> None:
            dialog = getattr(dashboard, "fertilizer_dialog", None)
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=220,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=620,
                next_ms=1000,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "fertilizer_dialog", None)
                    and dashboard.fertilizer_dialog.isVisible()
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason="Fertilizer dialog did not become ready",
            ),
        )
        fertilize(plant_id)

    def _capture_move(self) -> None:
        self._with_dashboard(self._capture_move_after)

    def _capture_move_after(self) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        begin_move = getattr(dashboard, "_begin_move", None)
        if callable(begin_move):
            begin_move(plant_id)
        cancel_move = getattr(dashboard, "_cancel_move", None)
        self._capture_and_advance(
            "move-mode",
            dashboard,
            capture_delay_ms=500,
            close_callback=lambda: (cancel_move() if callable(cancel_move) else self._close_dashboard()),
            close_ms=800,
            next_ms=1200,
        )

    def _capture_story(self) -> None:
        self._with_dashboard(self._capture_story_after)

    def _capture_story_after(self) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        story = getattr(dashboard, "_open_plant_story", None)
        if not callable(story):
            self._close_dashboard()
            self._next_after(250)
            return
        def ready() -> None:
            dialog = getattr(dashboard, "story_dialog", None)
            self._capture_and_advance(
                "plant-story",
                dialog,
                capture_delay_ms=220,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=650,
                next_ms=1000,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "story_dialog", None)
                    and dashboard.story_dialog.isVisible()
                ),
                ready,
                tries=80,
                failure_label="plant-story",
                failure_reason="Plant Story dialog did not become ready",
            ),
        )
        story(plant_id)

    def _refresh_capture_dashboard(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()

    def _capture_growth_zero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            plant = self.app.engine.active_plant()
            if plant is not None:
                plant.growth_points = 0
            stats = state.daily_stats
            for field in (
                "growth_earned", "base_growth", "streak_bonus_growth",
                "fertilizer_growth", "booster_growth", "weather_growth",
                "scenery_growth", "charge_growth",
            ):
                setattr(stats, field, 0)
            self._refresh_capture_dashboard()
            self._capture_metric("growth", "growth-zero")

        self._with_dashboard(ready)

    def _capture_growth_nonzero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            plant = self.app.engine.active_plant()
            if plant is not None:
                plant.growth_points = 1_250
            stats = state.daily_stats
            stats.growth_earned = 37
            stats.base_growth = 30
            stats.streak_bonus_growth = 3
            stats.fertilizer_growth = 4
            stats.booster_growth = 0
            stats.weather_growth = 0
            stats.scenery_growth = 0
            stats.charge_growth = 0
            self._refresh_capture_dashboard()
            self._capture_metric("growth", "growth-nonzero")

        self._with_dashboard(ready)

    def _capture_streak_new(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.streak_days = 0
            state.daily_stats.reviewed = 0
            self._refresh_capture_dashboard()
            self._capture_metric("streak", "streak-new")

        self._with_dashboard(ready)

    def _capture_streak_active(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.streak_days = 7
            state.daily_stats.reviewed = 12
            state.daily_stats.correct = 10
            state.daily_stats.wrong = 2
            state.last_active_day = str(state.daily_stats.day)
            streak_achievement = state.achievements.get("streak_7")
            if streak_achievement is not None:
                streak_achievement.unlocked = True
                streak_achievement.progress = 1.0
                streak_achievement.unlocked_at = str(state.daily_stats.day)
            self._refresh_capture_dashboard()
            self._capture_metric("streak", "streak-active")

        self._with_dashboard(ready)

    def _capture_coins_zero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.currency_balance = 0
            state.currency_transactions.clear()
            self._refresh_capture_dashboard()
            self._capture_metric("currency", "coins-zero")

        self._with_dashboard(ready)

    def _capture_coins_activity(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.currency_balance = 0
            state.currency_transactions.clear()
            credit = getattr(self.app.engine, "_credit_currency", None)
            if callable(credit):
                credit("capture:stage", "Reached Sprout", 5)
                credit("capture:streak", "7-day Anki streak", 25)
            self._refresh_capture_dashboard()
            self._capture_metric("currency", "coins-activity")

        self._with_dashboard(ready)

    def _capture_progress_page(self, key: str, label: str) -> None:
        self._with_dashboard(
            lambda: self._capture_progress_page_after(key, label)
        )

    def _capture_collection_filter(self, selected: str, label: str) -> None:
        """Open Collection, then apply its filter after the dialog refresh."""
        def after() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            dialog = getattr(dashboard, "progress_dialog", None)
            navigation = getattr(dialog, "navigation", None) if dialog is not None else None
            if dashboard is None or dialog is None or navigation is None:
                self._failures.append({
                    "label": label,
                    "reason": "Garden Progress Collection was unavailable",
                })
                self._next_after(250)
                return
            refresh = getattr(dialog, "refresh", None)
            if callable(refresh):
                refresh()
            navigation.set_current("collection")
            dashboard._set_collection_filter(selected)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            def ready() -> None:
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=820,
                    next_ms=1160,
                )

            self._wait_for(
                lambda: bool(
                    dialog.isVisible()
                    and navigation.stack.currentIndex()
                    == navigation.keys.index("collection")
                    and dashboard._collection_filter == selected
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason=f"Collection filter {selected!r} did not become ready",
            )

        self._with_dashboard(after)

    def _capture_progress_page_after(self, key: str, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        navigation = getattr(dialog, "navigation", None) if dialog is not None else None
        if dialog is None or navigation is None or key not in getattr(navigation, "keys", []):
            self._failures.append({
                "label": label,
                "reason": "Garden Progress dialog or requested page was unavailable",
            })
            self._next_after(250)
            return
        refresh = getattr(dialog, "refresh", None)
        if callable(refresh):
            refresh()
        navigation.set_current(key)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def ready() -> None:
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=360,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=760,
                next_ms=1100,
            )

        self._wait_for(
            lambda: bool(
                dialog.isVisible()
                and navigation.stack.currentIndex() == navigation.keys.index(key)
            ),
            ready,
            tries=80,
            failure_label=label,
            failure_reason=f"Garden Progress page {key!r} did not become ready",
        )

    def _capture_progress_today(self) -> None:
        self._capture_progress_page("overview", "progress-overview")

    def _capture_progress_achievements(self) -> None:
        self._capture_progress_page("achievements", "progress-achievements")

    def _capture_progress_collection(self) -> None:
        self._capture_progress_page("collection", "progress-collection")

    def _capture_customize_garden(self) -> None:
        self._with_dashboard(self._capture_customize_garden_after)

    def _capture_customize_garden_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        opener = getattr(dashboard, "_open_customize", None)
        if dashboard is None or not callable(opener):
            self._failures.append({
                "label": "customize-garden",
                "reason": "Customize Garden opener was unavailable",
            })
            self._next_after(250)
            return
        opener()
        dialog = getattr(dashboard, "customize_dialog", None)
        self._wait_for(
            lambda: bool(dialog is not None and dialog.isVisible()),
            lambda: self._capture_and_advance(
                "customize-garden",
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            ),
            tries=80,
            failure_label="customize-garden",
            failure_reason="Customize Garden did not become ready",
        )

    def _capture_nursery_tab(self, index: int, label: str) -> None:
        self._with_dashboard(
            lambda: self._capture_nursery_tab_after(index, label)
        )

    def _capture_nursery_tab_after(self, index: int, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        open_nursery = getattr(dashboard, "_open_nursery", None)
        if dashboard is None or not callable(open_nursery):
            self._failures.append({
                "label": label,
                "reason": "Nursery opener was unavailable",
            })
            self._next_after(250)
            return

        def ready() -> None:
            dialog = getattr(dashboard, "nursery_dialog", None)
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "nursery_dialog", None)
                    and dashboard.nursery_dialog.isVisible()
                    and dashboard.nursery_dialog.catalog_tabs.count() > index
                    and dashboard.nursery_dialog.catalog_tabs.currentIndex() == index
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason=f"Nursery tab {index + 1} did not become ready",
            ),
        )
        open_nursery(index)

    def _capture_nursery_plants(self) -> None:
        self._capture_nursery_tab(0, "nursery-plants")

    def _capture_nursery_fertilizer_booster(self) -> None:
        self._capture_nursery_tab(1, "nursery-fertilizer-booster")

    def _capture_nursery_garden_spaces(self) -> None:
        self._capture_nursery_tab(2, "nursery-garden-spaces")

    def _capture_nursery_weather_scenery(self) -> None:
        self._capture_nursery_tab(3, "nursery-weather-scenery")

    def _capture_settings_display(self) -> None:
        self._with_dashboard(self._capture_settings_display_after)

    def _capture_settings_display_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_display_ready,
            tries=80,
            failure_label="settings-display",
            failure_reason="Settings Display tab did not become ready",
        )

    def _capture_settings_display_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 0)
        self._capture_and_advance(
            "settings-display",
            settings_dialog,
            capture_delay_ms=450,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_settings_troubleshooting(self) -> None:
        self._with_dashboard(self._capture_settings_troubleshooting_after)

    def _capture_settings_troubleshooting_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_troubleshooting_ready,
            tries=80,
            failure_label="diagnostics-clean",
            failure_reason="Settings Troubleshooting tab did not become ready",
        )

    def _capture_settings_troubleshooting_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 1)
        self._capture_and_advance(
            "diagnostics-clean",
            settings_dialog,
            capture_delay_ms=500,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_settings_warning(self) -> None:
        self._with_dashboard(self._capture_settings_warning_after)

    def _capture_settings_warning_after(self) -> None:
        from .display_telemetry import DISPLAY_TELEMETRY

        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="capture",
            field="preview_artwork",
            reason="Intentional screenshot-regression warning state",
            required=True,
        )
        dashboard = getattr(self.app, "dashboard", None)
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_warning_ready,
            tries=80,
            failure_label="diagnostics-warning",
            failure_reason="Diagnostics warning state did not become ready",
        )

    def _capture_settings_warning_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 1)
        refresh = getattr(settings_dialog, "_refresh_debug_report", None)
        if callable(refresh):
            refresh()
        self._capture_and_advance(
            "diagnostics-warning",
            settings_dialog,
            capture_delay_ms=500,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_dashboard_stress(
        self,
        label: str,
        mutate: Callable[[], None] | None = None,
        *,
        delay_ms: int = 480,
    ) -> None:
        def ready() -> None:
            if mutate is not None:
                mutate()
            self._refresh_capture_dashboard()
            self._capture_and_advance(
                label,
                self.app.dashboard,
                capture_delay_ms=delay_ms,
                next_ms=980,
            )

        self._with_dashboard(ready)

    def _capture_long_garden_name(self) -> None:
        self._capture_dashboard_stress(
            "long-garden-name",
            lambda: setattr(
                self.app.storage.state,
                "garden_name",
                "The Moonlit Conservatory at Willow Ridge"[:40],
            ),
        )

    def _capture_long_plant_name(self) -> None:
        def mutate() -> None:
            plant = self.app.engine.active_plant() or self.app.storage.state.plants[0]
            plant.name = "Bonsai of the Everlasting Twilight Grove"[:40]
            plant.name_customized = True

        self._capture_dashboard_stress("long-plant-name", mutate)

    def _capture_four_digit_coin_balance(self) -> None:
        self._capture_dashboard_stress(
            "four-digit-coin-balance",
            lambda: setattr(self.app.storage.state, "currency_balance", 9_999),
        )

    def _capture_growth_near_stage_completion(self) -> None:
        from .models.state import GROWTH_THRESHOLDS

        def mutate() -> None:
            plant = self.app.engine.active_plant() or self.app.storage.state.plants[0]
            plant.growth_points = GROWTH_THRESHOLDS[-1] - 25
            self.app.storage.state.active_plant_id = plant.plant_id
            dashboard = self.app.dashboard
            dashboard.scene.keep_card_open(plant.plant_id)
            dashboard._on_scene_selection(plant.plant_id)

        self._capture_dashboard_stress(
            "growth-near-stage-completion",
            mutate,
            delay_ms=560,
        )

    def _ensure_development_stress_state(self) -> bool:
        if bool(getattr(self, "_development_stress_ready", False)):
            return True
        from .models.state import GROWTH_THRESHOLDS, MAX_GARDEN_SLOTS

        ok, message = self.app.engine.development_populate()
        if not ok:
            self._failures.append({
                "label": "development-stress-state",
                "reason": str(message),
            })
            return False
        plants = list(self.app.storage.state.plants)
        if len(plants) < MAX_GARDEN_SLOTS:
            self._failures.append({
                "label": "development-stress-state",
                "reason": "Development population did not create six plants",
            })
            return False
        for index, plant in enumerate(plants):
            plant.slot_index = index if index < MAX_GARDEN_SLOTS else None
            if index < MAX_GARDEN_SLOTS:
                plant.growth_points = GROWTH_THRESHOLDS[index]
        state = self.app.storage.state
        state.unlocked_slots = MAX_GARDEN_SLOTS
        state.currency_balance = 9_999
        state.active_plant_id = plants[0].plant_id
        self._development_stress_ready = True
        self._refresh_capture_dashboard()
        return True

    def _capture_all_six_beds(self) -> None:
        def mutate() -> None:
            self._ensure_development_stress_state()
            self.app.dashboard.scene.dismiss_selection()

        self._capture_dashboard_stress("all-six-beds-occupied", mutate, delay_ms=620)

    def _capture_all_six_stages(self) -> None:
        self._capture_dashboard_stress(
            "plant-at-every-stage",
            self._ensure_development_stress_state,
            delay_ms=620,
        )

    def _capture_popover_slot(self, slot: int) -> None:
        label = f"popover-plot-{slot + 1}"

        def mutate() -> None:
            if not self._ensure_development_stress_state():
                return
            plant = next(
                row for row in self.app.storage.state.plants
                if row.slot_index == slot
            )
            dashboard = self.app.dashboard
            dashboard.scene.keep_card_open(plant.plant_id)
            dashboard._on_scene_selection(plant.plant_id)

        self._capture_dashboard_stress(label, mutate, delay_ms=520)

    def _capture_move_mixed_destinations(self) -> None:
        def ready() -> None:
            if not self._ensure_development_stress_state():
                self._next_after(200)
                return
            plants = list(self.app.storage.state.plants)
            for plant in plants[:4]:
                plant.slot_index = plants.index(plant)
            for plant in plants[4:]:
                plant.slot_index = None
            active = plants[0]
            self.app.storage.state.active_plant_id = active.plant_id
            dashboard = self.app.dashboard
            dashboard.refresh_all()
            dashboard._begin_move(active.plant_id)
            self._capture_and_advance(
                "move-occupied-empty-destinations",
                dashboard,
                capture_delay_ms=560,
                close_callback=dashboard._cancel_move,
                close_ms=820,
                next_ms=1150,
            )

        self._with_dashboard(ready)

    def _prepare_expiring_fertilizer(self) -> str:
        if not self._ensure_development_stress_state():
            return ""
        plant = self.app.storage.state.plants[0]
        plant.slot_index = 0
        self.app.storage.state.active_plant_id = plant.plant_id
        current = getattr(plant, "fertilizer", None)
        if current is None or not current.active(time.time()) or current.tier != "basic":
            self.app.engine.purchase_fertilizer(
                plant.plant_id,
                "basic",
                replace_active=bool(current and current.active(time.time())),
            )
            current = plant.fertilizer
        if current is not None:
            current.expires_at = time.time() + 45
        self._refresh_capture_dashboard()
        return plant.plant_id

    def _capture_fertilizer_expiring(self) -> None:
        def ready() -> None:
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                self._next_after(200)
                return

            def dialog_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)
                self._capture_and_advance(
                    "fertilizer-expiring-under-minute",
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=760,
                    next_ms=1100,
                )

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "fertilizer_dialog", None)
                        and dashboard.fertilizer_dialog.isVisible()
                    ),
                    dialog_ready,
                    failure_label="fertilizer-expiring-under-minute",
                    failure_reason="Expiring Fertilizer dialog did not become ready",
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(ready)

    def _visible_message_box(self) -> QMessageBox | None:
        app = QApplication.instance()
        if app is None:
            return None
        return next(
            (
                widget for widget in app.topLevelWidgets()
                if isinstance(widget, QMessageBox) and widget.isVisible()
            ),
            None,
        )

    def _capture_fertilizer_replacement_confirmation(self) -> None:
        def ready() -> None:
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                self._next_after(200)
                return

            def fertilizer_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)
                replace = next(
                    (
                        button for button in dialog.findChildren(QAbstractButton)
                        if button.text().startswith("Replace for") and button.isEnabled()
                    ),
                    None,
                )
                if replace is None:
                    self._failures.append({
                        "label": "fertilizer-replacement-confirmation",
                        "reason": "No enabled replacement action was available",
                    })
                    self._close_widget(dialog)
                    self._next_after(200)
                    return

                def confirmation_ready() -> None:
                    message_box = self._visible_message_box()

                    def close_confirmation() -> None:
                        self._close_widget(message_box)
                        self._close_widget(dialog)

                    self._capture_and_advance(
                        "fertilizer-replacement-confirmation",
                        message_box,
                        capture_delay_ms=320,
                        close_callback=close_confirmation,
                        close_ms=700,
                        next_ms=1100,
                    )

                self._wait_for(
                    lambda: self._visible_message_box() is not None,
                    confirmation_ready,
                    tries=80,
                    failure_label="fertilizer-replacement-confirmation",
                    failure_reason="Replacement confirmation did not become visible",
                )
                QTimer.singleShot(80, replace.click)

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "fertilizer_dialog", None)
                        and dashboard.fertilizer_dialog.isVisible()
                    ),
                    fertilizer_ready,
                    failure_label="fertilizer-replacement-confirmation",
                    failure_reason="Fertilizer dialog did not become ready",
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(ready)

    def _capture_collection_several(self) -> None:
        self._ensure_development_stress_state()
        self._capture_collection_filter("all", "collection-several-discovered")

    def _capture_collection_no_matches(self) -> None:
        self._ensure_development_stress_state()
        self._capture_collection_filter("locked", "collection-no-filter-matches")

    def _capture_achievement_completed(self) -> None:
        self._ensure_development_stress_state()
        self._capture_progress_page("achievements", "achievement-completed")

    def _set_streak_capture_state(
        self,
        *,
        days: int,
        reviewed: int,
        last_active_offset: int,
        claimed: list[int] | None = None,
    ) -> None:
        state = self.app.storage.state
        try:
            current_day = date.fromisoformat(str(state.daily_stats.day)[:10])
        except (TypeError, ValueError):
            current_day = date.today()
            state.daily_stats.day = current_day.isoformat()
        state.streak_days = days
        state.daily_stats.reviewed = reviewed
        state.last_active_day = (current_day + timedelta(days=last_active_offset)).isoformat()
        if claimed is not None:
            state.claimed_streak_rewards = list(claimed)
        self._refresh_capture_dashboard()

    def _capture_streak_at_risk(self) -> None:
        self._set_streak_capture_state(days=7, reviewed=0, last_active_offset=-1)
        self._capture_metric("streak", "streak-at-risk")

    def _capture_streak_missed_day(self) -> None:
        self._set_streak_capture_state(days=3, reviewed=0, last_active_offset=-2)
        self._capture_metric("streak", "streak-missed-day")

    def _capture_streak_reward_states(self) -> None:
        self._set_streak_capture_state(
            days=14,
            reviewed=12,
            last_active_offset=0,
            claimed=[7],
        )
        self._capture_metric("streak", "streak-reward-claimed-unclaimed")

    def _capture_nursery_owned_item(self) -> None:
        self._ensure_development_stress_state()
        self._capture_nursery_tab(0, "nursery-item-owned")

    def _capture_custom_nursery(
        self,
        index: int,
        label: str,
        on_ready: Callable[[Any], None],
    ) -> None:
        def dashboard_ready() -> None:
            dashboard = self.app.dashboard

            def dialog_ready() -> None:
                dialog = dashboard.nursery_dialog
                on_ready(dialog)

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "nursery_dialog", None)
                        and dashboard.nursery_dialog.isVisible()
                        and dashboard.nursery_dialog.catalog_tabs.currentIndex() == index
                    ),
                    dialog_ready,
                    failure_label=label,
                    failure_reason=f"Nursery stress state {label!r} did not become ready",
                ),
            )
            dashboard._open_nursery(index)

        self._with_dashboard(dashboard_ready)

    def _capture_nursery_locked_item(self) -> None:
        self.app.storage.state.currency_balance = 0
        for key in list(self.app.storage.state.consumables):
            self.app.storage.state.consumables[key] = 0

        def ready(dialog: Any) -> None:
            scrollbar = dialog.supplements_scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self._capture_and_advance(
                "nursery-item-locked",
                dialog,
                capture_delay_ms=520,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=850,
                next_ms=1200,
            )

        self._capture_custom_nursery(1, "nursery-item-locked", ready)

    def _capture_nursery_purchase_success(self) -> None:
        from .environment import SCENERY_CATALOG, WEATHER_CATALOG

        state = self.app.storage.state
        state.currency_balance = 100_000
        item = next(
            entry for entry in [*WEATHER_CATALOG.values(), *SCENERY_CATALOG.values()]
            if entry.acquisition == "purchase"
        )
        inventory_key = "weather" if item.kind == "weather" else "scenery"
        state.inventory[inventory_key] = [
            key for key in state.inventory.get(inventory_key, [])
            if key != item.item_id
        ]
        if item.kind == "scenery":
            state.inventory["backgrounds"] = [
                key for key in state.inventory.get("backgrounds", [])
                if key != item.item_id
            ]

        def ready(dialog: Any) -> None:
            ok, message = self.app.engine.purchase_environment(item.kind, item.item_id)
            dialog.refresh()
            dialog._show_result(ok, message)
            self._capture_and_advance(
                "nursery-purchase-success",
                dialog,
                capture_delay_ms=520,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=900,
                next_ms=1250,
            )

        self._capture_custom_nursery(3, "nursery-purchase-success", ready)

    def _capture_custom_settings(
        self,
        label: str,
        tab: int,
        prepare: Callable[[Any], None],
    ) -> None:
        def dashboard_ready() -> None:
            dashboard = self.app.dashboard
            dashboard._open_settings()

            def settings_ready() -> None:
                dialog = self._find_settings_dialog()
                self._set_settings_tab(dialog, tab)
                prepare(dialog)
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=480,
                    close_callback=lambda: self._close_settings_capture(dialog),
                    close_ms=880,
                    next_ms=1250,
                )

            self._wait_for(
                lambda: bool(
                    self._find_settings_dialog() is not None
                    and self._find_settings_dialog().isVisible()
                ),
                settings_ready,
                failure_label=label,
                failure_reason=f"Settings stress state {label!r} did not become ready",
            )

        self._with_dashboard(dashboard_ready)

    @staticmethod
    def _close_settings_capture(dialog: Any) -> None:
        """Restore the saved draft so stress captures never open a discard prompt."""
        try:
            dialog.behavior.apply_persistent_payload(dialog._persisted_payload)
            dialog.garden_name_edit.setText(dialog._persisted_name)
            QDialog.reject(dialog)
        except Exception:
            dialog.close()

    def _capture_settings_unsaved(self) -> None:
        self._capture_custom_settings(
            "settings-unsaved-changes",
            0,
            lambda dialog: dialog.garden_name_edit.setText("Unsaved Moonlit Garden"),
        )

    def _capture_settings_validation_error(self) -> None:
        self._capture_custom_settings(
            "settings-validation-error",
            0,
            lambda dialog: dialog.garden_name_edit.setText("   "),
        )

    def _capture_diagnostics_expanded(self) -> None:
        def prepare(dialog: Any) -> None:
            dialog._refresh_debug_report()
            dialog.report_details_toggle.setChecked(True)

        self._capture_custom_settings("diagnostics-expanded", 1, prepare)

    def _capture_reduced_motion(self) -> None:
        try:
            self.app.dashboard.config.update({"reduced_motion": True})
        except Exception:
            logger.debug("Anki Garden capture: could not persist reduced motion", exc_info=True)
        self._capture_custom_settings(
            "reduced-motion-enabled",
            0,
            lambda dialog: dialog.behavior.reduced_motion.setChecked(True),
        )

    def _capture_keyboard_focus(self) -> None:
        def ready() -> None:
            dashboard = self.app.dashboard
            dashboard.progress_btn.setFocus(Qt.FocusReason.TabFocusReason)
            self._capture_and_advance(
                "keyboard-focus-state",
                dashboard,
                capture_delay_ms=420,
                next_ms=900,
            )

        self._with_dashboard(ready)

    def _capture_narrow_window(self) -> None:
        def ready() -> None:
            dashboard = self.app.dashboard
            previous = dashboard.size()
            dashboard.resize(760, 620)

            def restore() -> None:
                dashboard.resize(previous)

            self._capture_and_advance(
                "narrow-window-responsive",
                dashboard,
                capture_delay_ms=620,
                close_callback=restore,
                close_ms=900,
                next_ms=1200,
            )

        self._with_dashboard(ready)

    def _capture_display_scaling(self) -> None:
        if self._requested_scale_factor not in {"1.5", "1.50", "1.500"}:
            self._failures.append({
                "label": "display-scaling-150",
                "reason": (
                    "The release capture must be launched with QT_SCALE_FACTOR=1.5 "
                    "to verify the 150 percent display state"
                ),
            })
        self._capture_dashboard_stress("display-scaling-150", delay_ms=620)

    def _finish(self) -> None:
        captured_labels = [
            str(record.get("label", ""))
            for record in self._capture_records
        ]
        expected_labels = list(CAPTURE_FACE_LABELS)
        manifest = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "capture_contract_version": CAPTURE_CONTRACT_VERSION,
            "capture_display": self._capture_display,
            "requested_scale_factor": self._requested_scale_factor,
            "capture_groups": [
                {"name": group, "labels": list(labels)}
                for group, labels in CAPTURE_FACE_GROUPS
            ],
            "expected_faces": expected_labels,
            "screenshots": self._screenshots,
            "captures": self._capture_records,
            "text_layout_warnings": self._text_layout_warnings,
            "failures": self._failures,
            "expected_count": len(expected_labels),
            "complete": (
                captured_labels == expected_labels
                and len(self._screenshots) == len(expected_labels)
                and not self._failures
                and not self._text_layout_warnings
            ),
        }
        try:
            self._close_top_level_dialogs()
            self._close_dashboard()
        except Exception:
            pass
        try:
            manifest_path = self.session_dir / "manifest.json"
            manifest_path.write_text(
                __import__("json").dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Anki Garden capture: could not write manifest", exc_info=True)
        if os.environ.get("ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE") == "1":
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(350, app.quit)
