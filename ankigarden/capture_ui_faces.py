"""Automated UI-face screenshot capture for disposable Anki runs.

Capture logic is intentionally conservative and activated only when
``ANKI_GARDEN_CAPTURE_UI_FACES`` is set. It uses only Qt-native screenshot
paths and closes transient dialogs after each face to keep the sequence stable.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from aqt import mw
from aqt.qt import QApplication, QDialog, QGuiApplication, QTabWidget, QTimer


logger = logging.getLogger(__name__)


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
        self._failures: list[dict[str, str]] = []
        self._step_index = 0
        self._capture_index = 1
        self._starter_seed_attempts = 0
        self._capture_display = "primary"
        self._steps = [
            self._capture_deck_browser,
            self._capture_overview,
            self._capture_addon_settings_menu,
            self._capture_full_garden,
            self._capture_selected_card,
            self._capture_nurture,
            self._capture_fertilize,
            self._capture_move,
            self._capture_story,
            self._capture_metric_growth,
            self._capture_metric_streak,
            self._capture_metric_currency,
            self._capture_progress,
            self._capture_settings_display,
            self._capture_settings_troubleshooting,
        ]

    def start(self) -> None:
        """Kick off capture after collection load and dashboard prerequisites."""
        self._wait_for_collection(self._prepare_capture_window, tries=120)

    def _prepare_capture_window(self) -> None:
        self._move_to_capture_display(mw)
        QTimer.singleShot(300, self._prepare_capture_state)

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

    def _wait_for(self, predicate: Callable[[], bool], on_ready: Callable[[], None], *, tries: int = 80) -> None:
        try:
            if predicate():
                on_ready()
                return
        except Exception:
            pass
        if tries <= 0:
            on_ready()
            return
        QTimer.singleShot(120, lambda: self._wait_for(predicate, on_ready, tries=tries - 1))

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
        dashboard = getattr(self.app, "dashboard", None)
        try:
            if dashboard is not None and bool(dashboard.isVisible()):
                self._move_to_capture_display(dashboard)
                on_ready()
                return
        except Exception:
            pass
        self.app.open_dashboard()
        def dashboard_ready() -> None:
            self._move_to_capture_display(getattr(self.app, "dashboard", None))
            on_ready()
        self._wait_for_dashboard(dashboard_ready)

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
                self._capture_records.append({
                    "label": label,
                    "path": str(path),
                    "widget": type(widget).__name__,
                    "width": int(widget.width()),
                    "height": int(widget.height()),
                })
            else:
                self._failures.append({"label": label, "reason": "PNG save failed"})
        except Exception:
            self._failures.append({"label": label, "reason": "Unexpected capture exception"})
            logger.debug("Anki Garden capture: screenshot failed for %s", label, exc_info=True)

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

    def _select_plant(self) -> str:
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
        open_metric = getattr(dashboard, "_open_metric_details", None)
        if callable(open_metric):
            open_metric(metric)
        expected_index = {"growth": 0, "streak": 1, "currency": 2}.get(metric, 0)

        def _dialog_ready() -> None:
            dialog = getattr(dashboard, "details_dialog", None)
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
                getattr(dashboard, "details_dialog", None)
                and dashboard.details_dialog.isVisible()
                and dashboard.details_dialog.tabs.currentIndex() == expected_index
            ),
            _dialog_ready,
            tries=50,
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
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        selector = getattr(dashboard, "_on_scene_selection", None)
        keep_open = getattr(getattr(dashboard, "scene", None), "keep_card_open", None)
        if callable(keep_open):
            keep_open(plant_id)
        if callable(selector):
            selector(plant_id)
        self._capture_and_advance(
            "selected-plant-card",
            dashboard,
            capture_delay_ms=400,
            next_ms=900,
        )

    def _capture_nurture(self) -> None:
        self._with_dashboard(self._capture_nurture_after)

    def _capture_nurture_after(self) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        nurture = getattr(dashboard, "_nurture_plant", None)
        if callable(nurture):
            nurture(plant_id)
        self._capture_and_advance(
            "selected-plant-nurture",
            dashboard,
            capture_delay_ms=260,
            next_ms=850,
        )

    def _capture_fertilize(self) -> None:
        self._with_dashboard(self._capture_fertilize_after)

    def _capture_fertilize_after(self) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        fertilize = getattr(dashboard, "_open_fertilizer_menu", None)
        if not callable(fertilize):
            self._close_dashboard()
            self._next_after(250)
            return
        def ready() -> None:
            dialog = getattr(dashboard, "fertilizer_dialog", None)
            self._capture_and_advance(
                "selected-plant-fertilize",
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
            "selected-plant-move",
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
                "selected-plant-story",
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
            ),
        )
        story(plant_id)

    def _capture_metric_growth(self) -> None:
        self._with_dashboard(lambda: self._capture_metric("growth", "metric-growth"))

    def _capture_metric_streak(self) -> None:
        self._with_dashboard(lambda: self._capture_metric("streak", "metric-streak"))

    def _capture_metric_currency(self) -> None:
        self._with_dashboard(lambda: self._capture_metric("currency", "metric-currency"))

    def _capture_progress(self) -> None:
        self._with_dashboard(self._capture_progress_after)

    def _capture_progress_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_progress = getattr(dashboard, "_open_progress", None)
        if callable(open_progress):
            open_progress()
        def ready() -> None:
            dialog = getattr(dashboard, "progress_dialog", None)
            self._capture_and_advance(
                "garden-progress",
                dialog,
                capture_delay_ms=220,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=620,
                next_ms=1000,
            )
        self._wait_for(
            lambda: bool(
                getattr(dashboard, "progress_dialog", None)
                and dashboard.progress_dialog.isVisible()
            ),
            ready,
            tries=80,
        )

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
        )

    def _capture_settings_troubleshooting_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 1)
        self._capture_and_advance(
            "settings-troubleshooting",
            settings_dialog,
            capture_delay_ms=500,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _finish(self) -> None:
        manifest = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "capture_display": self._capture_display,
            "screenshots": self._screenshots,
            "captures": self._capture_records,
            "failures": self._failures,
            "expected_count": len(self._steps),
            "complete": len(self._screenshots) == len(self._steps) and not self._failures,
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
