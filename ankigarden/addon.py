from __future__ import annotations

import json
import logging
import os
from html import escape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from aqt import mw
from aqt.gui_hooks import reviewer_did_answer_card
try:
    from aqt.gui_hooks import reviewer_did_show_question
except (ImportError, AttributeError):
    reviewer_did_show_question = None
from aqt.qt import QAction

from .config import ConfigManager
from .build_capabilities import CAPTURE_HARNESS_ENABLED
from .display_telemetry import DISPLAY_TELEMETRY
from .game import GardenGameEngine
from .hooks.reviewer import ReviewerHookHandler
from .notices import USER_NOTICES
from .storage import GardenStorage, SchedulerBoundaryError
from .ui.dashboard import GardenDashboard
from .ui.state import GardenUiCoordinator
from .ui.home_widget import (
    HomeWidgetStateController,
    build_home_widget_success_data,
    render_home_widget,
)

logger = logging.getLogger(__name__)

CALEB_ADDONS_MENU_TITLE = "Caleb M. Add-ons Settings"
CALEB_ADDONS_MENU_OBJECT_NAME = "caleb_m_addons_menu"
GARDEN_SETTINGS_ACTION_TEXT = "Anki Garden settings"


def _qt_action_text(action: Any) -> str:
    """Return an action label without relying on a particular Qt binding."""
    text = getattr(action, "text", None)
    try:
        value = text() if callable(text) else text
    except Exception:
        value = ""
    return str(value or getattr(action, "label", "")).replace("&", "").strip()


def _qt_menu_title(menu: Any) -> str:
    title = getattr(menu, "title", None)
    try:
        value = title() if callable(title) else title
    except Exception:
        value = ""
    return str(value or "").replace("&", "").strip()


def _qt_object_name(widget: Any) -> str:
    name = getattr(widget, "objectName", None)
    try:
        value = name() if callable(name) else name
    except Exception:
        value = ""
    return str(value or "").strip()


def _menu_actions(menu: Any) -> list[Any]:
    actions = getattr(menu, "actions", None)
    try:
        value = actions() if callable(actions) else actions
    except Exception:
        value = []
    return list(value or [])


def _iter_submenus(menu: Any, seen: set[int] | None = None):
    """Yield nested QMenus, including the tuple-shaped test doubles."""
    seen = seen or set()
    if id(menu) in seen:
        return
    seen.add(id(menu))
    for submenu in getattr(menu, "submenus", []) or []:
        if submenu is not None:
            yield submenu
            yield from _iter_submenus(submenu, seen)
    for action in _menu_actions(menu):
        if isinstance(action, tuple) and len(action) >= 2:
            action = action[1]
        getter = getattr(action, "menu", None)
        if not callable(getter):
            continue
        try:
            submenu = getter()
        except Exception:
            submenu = None
        if submenu is not None:
            yield submenu
            yield from _iter_submenus(submenu, seen)


class AnkiGardenApp:
    def __init__(self) -> None:
        self.config = ConfigManager(mw)
        self.storage = GardenStorage(mw, self.config)
        self.engine = GardenGameEngine(self.config, self.storage)
        self.state_events = GardenUiCoordinator(mw)
        self.state_events.stateChanged.connect(self._invalidate_home_cache)
        self.reviewer_hooks = ReviewerHookHandler(
            self.engine,
            self.storage,
            state_changed=self.state_events.notify,
        )
        self.dashboard: Optional[GardenDashboard] = None
        self._settings_action: Optional[QAction] = None
        self._home_widget_hooked = False
        self._home_bridge_hooked = False
        self._reviewer_hooked = False
        self._sync_hooked = False
        self._sync_callback = self._on_sync_finished
        self._home_widget_controller = HomeWidgetStateController()
        self._home_html_cache: str | None = None
        self._home_html_revision = -1
        self._dashboard_open_pending = False
        self._dashboard_open_attempts = 0
        self._dashboard_open_failures = 0
        self._settings_open_pending = False
        self._starter_open_pending = False

    def _invalidate_home_cache(self, _reason: str = "") -> None:
        self._home_html_cache = None
        self._home_html_revision = -1

    def setup(self) -> None:
        try:
            mw.addonManager.setWebExports(__name__, r"assets/.*\.(svg|png|webp)")
        except Exception:
            logger.exception("Anki Garden: unable to register bundled web assets")
        self._setup_settings_menu()
        self._setup_home_screen_widget()
        self._setup_reviewer_hook()
        self._setup_sync_hooks()
        self._run_garden_maintenance("startup")
        self._maybe_start_ui_face_capture()

    def _maybe_start_ui_face_capture(self) -> None:
        if (
            not CAPTURE_HARNESS_ENABLED
            or os.environ.get("ANKI_GARDEN_CAPTURE_UI_FACES") != "1"
        ):
            return
        if getattr(self, "_ui_face_capture_active", False):
            return
        self._ui_face_capture_active = True
        try:
            from .capture_ui_faces import start_capture

            start_capture(self)
        except Exception:
            logger.exception("Anki Garden: unable to start UI-face capture mode")

    def _run_garden_maintenance(self, source: str) -> bool:
        """Run rollover and revlog catch-up behind one fail-closed boundary."""
        try:
            prepare_ledger = getattr(self.storage, "ensure_revlog_ledger_ready", None)
            if callable(prepare_ledger):
                prepare_ledger()
            self.engine.rollover_if_needed()
            reconcile_streak = getattr(self.engine, "reconcile_retrospective_streak", None)
            if callable(reconcile_streak):
                # This only updates the scalar streak and unclaimed historical
                # Coin milestones. It never replays Growth or random drops.
                reconcile_streak()
            catchup_result = self._apply_same_day_catchup()
        except SchedulerBoundaryError:
            # Anki constructs add-ons before the collection scheduler is fully
            # available. That startup state is expected and will be retried by
            # the first collection-backed entry point, so do not emit a scary
            # exception trace or a premature learner warning.
            logger.info(
                "Anki Garden: maintenance waiting for scheduler during %s",
                source,
            )
            if source != "startup":
                USER_NOTICES.publish(
                    "Garden progress is temporarily paused while review history is unavailable. "
                    "Your Anki reviews are safe, and Garden will retry automatically.",
                    key="review_history",
                )
            return False
        except Exception:
            logger.exception("Anki Garden: maintenance deferred during %s", source)
            USER_NOTICES.publish(
                "Garden progress is temporarily paused while review history is unavailable. "
                "Your Anki reviews are safe, and Garden will retry automatically.",
                key="review_history",
            )
            return False
        USER_NOTICES.clear(key="review_history")
        if isinstance(catchup_result, tuple) and len(catchup_result) == 2:
            review_count, growth_gain = catchup_result
        else:
            review_count, growth_gain = 0, 0
        self._refresh_dashboard_after_maintenance(
            max(0, int(review_count)), max(0, int(growth_gain))
        )
        return True

    def _refresh_dashboard_after_maintenance(
        self, review_count: int, growth_gain: int
    ) -> None:
        """Update a live Garden after commit without re-entering home rendering."""
        dashboard = self.dashboard
        if dashboard is None:
            return
        USER_NOTICES.clear(key="display_refresh")
        try:
            refresh = getattr(dashboard, "refresh_all", None)
            if callable(refresh):
                refresh()
        except Exception:
            logger.debug("Anki Garden: live Garden could not refresh after maintenance", exc_info=True)
            USER_NOTICES.publish(
                "Your garden progress is safe, but the display could not refresh. "
                "Reopen Anki Garden to try again.",
                key="display_refresh",
            )
        try:
            feedback = getattr(dashboard, "show_same_day_catchup_feedback", None)
            if callable(feedback):
                feedback(review_count, growth_gain)
        except Exception:
            logger.debug("Anki Garden: synced-review notice could not refresh", exc_info=True)

    def _setup_reviewer_hook(self) -> None:
        if self._reviewer_hooked:
            return
        reviewer_did_answer_card.append(self.reviewer_hooks.on_answer)
        question_handler = getattr(self.reviewer_hooks, "on_question", None)
        if reviewer_did_show_question is not None and callable(question_handler):
            reviewer_did_show_question.append(question_handler)
        self._reviewer_hooked = True

    def _settings_menu_bar(self) -> Any:
        """Resolve Anki's shared top-level add-on menu across Qt versions."""
        form = getattr(mw, "form", None)
        menu_bar = getattr(form, "menubar", None)
        if menu_bar is None:
            getter = getattr(mw, "menuBar", None)
            menu_bar = getter() if callable(getter) else None
        return menu_bar

    def _shared_addons_settings_menu(self) -> Any:
        menu_bar = self._settings_menu_bar()
        if menu_bar is None:
            return None

        existing = getattr(mw, "_caleb_m_addons_menu", None)
        if existing is not None:
            try:
                if _qt_menu_title(existing) == CALEB_ADDONS_MENU_TITLE or _qt_object_name(existing) == CALEB_ADDONS_MENU_OBJECT_NAME:
                    return existing
            except RuntimeError:
                pass

        candidates = [menu_bar, *_iter_submenus(menu_bar)]
        for submenu in candidates:
            if (
                _qt_object_name(submenu) == CALEB_ADDONS_MENU_OBJECT_NAME
                or _qt_menu_title(submenu) == CALEB_ADDONS_MENU_TITLE
            ):
                setter = getattr(submenu, "setObjectName", None)
                if callable(setter):
                    try:
                        setter(CALEB_ADDONS_MENU_OBJECT_NAME)
                    except Exception:
                        logger.debug("Anki Garden: unable to name shared settings menu", exc_info=True)
                try:
                    mw._caleb_m_addons_menu = submenu
                except Exception:
                    pass
                return submenu

        add_menu = getattr(menu_bar, "addMenu", None)
        if not callable(add_menu):
            return None
        try:
            submenu = add_menu(CALEB_ADDONS_MENU_TITLE)
        except Exception:
            logger.exception("Anki Garden: unable to create the shared add-on settings menu")
            return None
        setter = getattr(submenu, "setObjectName", None)
        if callable(setter):
            try:
                setter(CALEB_ADDONS_MENU_OBJECT_NAME)
            except Exception:
                logger.debug("Anki Garden: unable to name shared settings menu", exc_info=True)
        try:
            mw._caleb_m_addons_menu = submenu
        except Exception:
            pass
        return submenu

    def _setup_settings_menu(self) -> None:
        """Register Garden settings beside the user's other add-on settings."""
        if getattr(self, "_settings_action", None) is not None:
            return
        submenu = self._shared_addons_settings_menu()
        if submenu is None:
            # The dashboard still exposes Settings. This is only a menu
            # integration enhancement and must never prevent the add-on from
            # starting on older/custom Anki shells.
            logger.debug("Anki Garden: shared add-on settings menu is unavailable")
            return
        for action in _menu_actions(submenu):
            if _qt_action_text(action) == GARDEN_SETTINGS_ACTION_TEXT:
                self._settings_action = action
                return
        action = QAction(GARDEN_SETTINGS_ACTION_TEXT, mw)
        action.triggered.connect(self.open_settings)
        try:
            submenu.addAction(action)
        except Exception:
            logger.exception("Anki Garden: unable to register the Garden settings menu action")
            return
        self._settings_action = action

    def open_settings(self) -> None:
        """Open the dashboard and then its settings dialog."""
        self._settings_open_pending = True
        self.open_dashboard()

    def open_starter_selection(self) -> None:
        """Open a visible Garden first, then its starter-mode Nursery."""
        self._starter_open_pending = True
        self.open_dashboard()

    def open_dashboard(self) -> None:
        if getattr(self, "_dashboard_open_pending", False):
            return
        self._dashboard_open_pending = True
        self._dashboard_open_attempts = 0
        self._dashboard_open_failures = 0
        self._schedule_dashboard_open(0)

    def _schedule_dashboard_open(self, delay_ms: int) -> None:
        try:
            from aqt.qt import QTimer

            QTimer.singleShot(max(0, int(delay_ms)), self._open_dashboard_when_ready)
        except Exception:
            self._dashboard_open_pending = False
            self._settings_open_pending = False
            self._starter_open_pending = False
            logger.exception("Anki Garden: unable to schedule dashboard opening")
            self._notify_dashboard_open_failure(
                "Anki Garden could not schedule its window. Please restart Anki and try again."
            )

    def _dashboard_is_alive(self) -> bool:
        if self.dashboard is None:
            return False
        try:
            # Calling a Qt method is enough to detect a deleted C++ object;
            # visibility itself is intentionally not used as a gate because a
            # hidden dashboard can be shown again after a home-screen click.
            self.dashboard.isVisible()
            return True
        except RuntimeError:
            self.dashboard = None
            return False

    def _clear_dashboard_reference(
        self, expected: object | None = None, *_args: object
    ) -> None:
        if expected is None or self.dashboard is expected:
            self.dashboard = None

    def _open_dashboard_when_ready(self) -> None:
        collection = getattr(mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            self._dashboard_open_attempts += 1
            if self._dashboard_open_attempts <= 10:
                self._schedule_dashboard_open(100)
                return
            self._dashboard_open_pending = False
            self._settings_open_pending = False
            self._starter_open_pending = False
            logger.warning("Anki Garden: dashboard opening timed out while waiting for the collection")
            self._notify_dashboard_open_failure(
                "Anki Garden is still waiting for the collection to finish opening. Please try again."
            )
            return
        candidate = None
        retry_scheduled = False
        try:
            self._run_garden_maintenance("dashboard open")
            if not self._dashboard_is_alive():
                coordinator = getattr(self, "state_events", None)
                if coordinator is None:
                    coordinator = GardenUiCoordinator(mw)
                    self.state_events = coordinator
                reviewer_hooks = getattr(self, "reviewer_hooks", None)
                starter_selected_callback = getattr(
                    reviewer_hooks, "on_starter_selected", None
                )
                candidate = GardenDashboard(
                    mw,
                    self.engine,
                    self.storage,
                    self.config,
                    coordinator,
                    starter_selected_callback,
                )
                destroyed = getattr(candidate, "destroyed", None)
                if destroyed is not None and callable(getattr(destroyed, "connect", None)):
                    destroyed.connect(
                        lambda *_args, expected=candidate:
                        self._clear_dashboard_reference(expected)
                    )
                self.dashboard = candidate
            prepare = getattr(self.dashboard, "prepare_to_show", None)
            if callable(prepare):
                prepare()
            else:
                self.dashboard.refresh_all()
            present_over_parent = getattr(self.dashboard, "present_over_parent", None)
            presentation_result = None
            if callable(present_over_parent):
                presentation_result = present_over_parent()
                if presentation_result is not None and not bool(presentation_result):
                    raise RuntimeError("dashboard refused presentation")
            else:
                show_normal = getattr(self.dashboard, "showNormal", None)
                if callable(show_normal):
                    show_normal()
                else:
                    self.dashboard.show()
            if not bool(self.dashboard.isVisible()):
                raise RuntimeError("dashboard presentation did not produce a visible window")
            acknowledge = getattr(self.dashboard, "acknowledge_rendered_feedback", None)
            if callable(acknowledge):
                acknowledge()
            opening_settings = bool(getattr(self, "_settings_open_pending", False))
            opening_starter = bool(getattr(self, "_starter_open_pending", False))
            if opening_settings:
                self._settings_open_pending = False
                try:
                    open_settings = getattr(self.dashboard, "_open_settings", None)
                    if callable(open_settings):
                        open_settings()
                except Exception:
                    # A settings dialog failure must not make the already-open
                    # garden look like an opener failure.
                    logger.exception("Anki Garden: settings dialog failed to open")
            elif opening_starter:
                self._starter_open_pending = False
                open_starter = getattr(self.dashboard, "_open_starter_nursery", None)
                if callable(open_starter):
                    # Let the successful show/raise/activate turn complete
                    # before entering the modal Nursery. This prevents a
                    # Home bridge click from racing the parent Garden window.
                    from aqt.qt import QTimer

                    QTimer.singleShot(0, open_starter)
            else:
                prompt_starter = getattr(self.dashboard, "_present_starter_setup_if_needed", None)
                if callable(prompt_starter):
                    prompt_starter()
        except Exception:
            failed_dashboard = self.dashboard
            if failed_dashboard is not None:
                try:
                    close = getattr(failed_dashboard, "close", None)
                    if callable(close):
                        close()
                    delete_later = getattr(failed_dashboard, "deleteLater", None)
                    if callable(delete_later):
                        delete_later()
                except Exception:
                    logger.debug("Anki Garden: failed dashboard could not be disposed", exc_info=True)
            if candidate is not None and self.dashboard is candidate:
                self.dashboard = None
            elif candidate is None and self.dashboard is not None:
                # A refresh/show failure can leave a Python wrapper around a
                # deleted or half-constructed QDialog. Do not keep reusing it
                # on the next click; the next attempt must build a clean
                # window.
                self.dashboard = None
            logger.exception("Anki Garden: dashboard failed to open; the next attempt may retry")
            failures = int(getattr(self, "_dashboard_open_failures", 0)) + 1
            self._dashboard_open_failures = failures
            if failures <= 2:
                # Home-screen webviews can still be tearing down their bridge
                # when pycmd arrives. Retry on the Qt event loop before showing
                # a terminal warning, so a transient race is invisible.
                retry_scheduled = True
                logger.warning("Anki Garden: transient dashboard-open failure; retry %s/2", failures)
            else:
                # This request is over. Discard its destination as well as its
                # retry state so a later ordinary Open Garden action cannot
                # inherit a stale request to open Settings.
                self._settings_open_pending = False
                self._starter_open_pending = False
                self._notify_dashboard_open_failure(
                    "Anki Garden could not open its window. No garden progress was changed; please try again."
                )
        finally:
            if retry_scheduled:
                self._schedule_dashboard_open(120)
            else:
                self._dashboard_open_pending = False

    @staticmethod
    def _notify_dashboard_open_failure(message: str) -> None:
        try:
            from aqt.utils import showWarning

            showWarning(message)
        except Exception:
            logger.debug("Anki Garden: unable to show dashboard-open warning", exc_info=True)

    def _setup_sync_hooks(self) -> None:
        if self._sync_hooked:
            return
        try:
            from aqt import gui_hooks

            if hasattr(gui_hooks, "sync_did_finish"):
                gui_hooks.sync_did_finish.append(self._sync_callback)
                self._sync_hooked = True
        except Exception:
            logger.exception("Anki Garden: failed to attach sync hooks")

    def _on_sync_finished(self, *_args: object, **_kwargs: object) -> None:
        self._run_garden_maintenance("sync completion")

    def _setup_home_screen_widget(self) -> None:
        if self._home_widget_hooked:
            return

        try:
            from aqt import gui_hooks
        except Exception:
            logger.exception("Anki Garden: unable to import gui_hooks for home-screen injection")
            return

        attached_hooks: list[str] = []

        if hasattr(gui_hooks, "webview_will_set_content"):
            gui_hooks.webview_will_set_content.append(self._inject_home_garden_webview)
            attached_hooks.append("webview_will_set_content")
        if hasattr(gui_hooks, "deck_browser_will_render_content"):
            gui_hooks.deck_browser_will_render_content.append(self._inject_home_garden)
            attached_hooks.append("deck_browser_will_render_content")
        if hasattr(gui_hooks, "overview_will_render_content"):
            gui_hooks.overview_will_render_content.append(self._inject_home_garden)
            attached_hooks.append("overview_will_render_content")
        if hasattr(gui_hooks, "webview_did_inject_style_into_page"):
            gui_hooks.webview_did_inject_style_into_page.append(
                self._inject_home_garden_finished_overview
            )
            attached_hooks.append("webview_did_inject_style_into_page")

        if attached_hooks:
            self._home_widget_hooked = True
            logger.info("Anki Garden attached home-screen hooks: %s", ", ".join(attached_hooks))
            if hasattr(gui_hooks, "webview_did_receive_js_message") and not self._home_bridge_hooked:
                gui_hooks.webview_did_receive_js_message.append(self._handle_home_bridge_message)
                self._home_bridge_hooked = True
        else:
            logger.warning("Anki Garden: no supported home-screen hooks available on this Anki version")

    def _handle_home_bridge_message(self, handled: tuple[bool, object], message: str, context: object) -> tuple[bool, object]:
        if not message.startswith("anki-garden:") or not self._is_main_screen_context(context):
            return handled
        command = message.partition(":")[2]
        if command == "open":
            self.open_dashboard()
            return True, None
        if command == "choose-starter":
            self.open_starter_selection()
            return True, None
        if command == "refresh":
            self._invalidate_home_cache("home retry")
            self._run_garden_maintenance("home retry")
            reset = getattr(mw, "reset", None)
            if callable(reset):
                reset()
            return True, None
        return handled

    def _inject_home_garden(self, _page: object, content: object) -> None:
        if not self.config.value("show_home_widget", True):
            return
        for attribute in ("stats", "table"):
            existing = getattr(content, attribute, None)
            if isinstance(existing, str) and "ag-home-root" in existing:
                return
        html = self._home_garden_html_for_injection()
        if hasattr(content, "stats") and isinstance(content.stats, str):
            content.stats += html
            return

        if hasattr(content, "table") and isinstance(content.table, str):
            content.table += html

    def _context_name(self, context: object) -> str:
        cls = type(context)
        module = getattr(cls, "__module__", "")
        qualname = getattr(cls, "__qualname__", cls.__name__)
        return f"{module}.{qualname}".lower()

    def _is_main_screen_context(self, context: object) -> bool:
        context_name = self._context_name(context)
        is_primary_home_context = any(name in context_name for name in ("deckbrowser", "overview", "homescreen"))
        is_lower_bar_context = any(name in context_name for name in ("bottom", "toolbar", "statusbar", "footer"))
        return is_primary_home_context and not is_lower_bar_context

    def _inject_home_garden_webview(self, web_content: object, context: object) -> None:
        if not self.config.value("show_home_widget", True):
            return
        context_name = self._context_name(context)
        if not self._is_main_screen_context(context):
            logger.debug("Anki Garden: skipping home injection for non-primary context %s", context_name)
            return

        body = getattr(web_content, "body", None)
        if isinstance(body, str) and "ag-home-root" in body:
            return
        logger.debug("Anki Garden: injecting home garden into context %s", context_name)
        html = self._home_garden_html_for_injection()

        if isinstance(body, str) and "ag-home-root" not in body:
            web_content.body = body + html

    def _inject_home_garden_finished_overview(self, webview: object) -> None:
        """Inject into Anki's external Congratulations page after it loads."""
        if not self.config.value("show_home_widget", True):
            return
        if webview is not getattr(mw, "web", None):
            return
        if getattr(mw, "state", None) != "overview":
            return

        try:
            url = webview.url()
            path = str(url.path()).rstrip("/")
        except Exception:
            logger.debug(
                "Anki Garden: unable to identify external overview page",
                exc_info=True,
            )
            return
        if path not in {"/_anki/pages/congrats.html", "/congrats"}:
            return

        evaluate = getattr(webview, "eval", None)
        if not callable(evaluate):
            return

        html = self._home_garden_html_for_injection()
        evaluate(
            f"""
(() => {{
  let root = document.getElementById("ag-home-root");
  if (!root) {{
    const template = document.createElement("template");
    template.innerHTML = {json.dumps(html)};
    for (const sourceScript of template.content.querySelectorAll("script")) {{
      sourceScript.remove();
    }}
    document.body.appendChild(template.content);
    root = document.getElementById("ag-home-root");
  }}
  if (!root) return;

  for (const sourceScript of root.querySelectorAll("script")) {{
    sourceScript.remove();
  }}

  const bindBridgeButton = (selector, command, pendingText = "") => {{
    const button = root.querySelector(selector);
    if (!button) return;
    button.removeAttribute("onclick");
    if (button.dataset.ankiGardenBridgeBound === "true") return;
    button.dataset.ankiGardenBridgeBound = "true";
    const originalText = button.textContent;
    button.addEventListener("click", () => {{
      if (button.disabled) return;
      const bridge = typeof window.bridgeCommand === "function"
        ? window.bridgeCommand
        : window.pycmd;
      if (typeof bridge !== "function") return;
      if (pendingText) {{
        button.disabled = true;
        button.textContent = pendingText;
        window.setTimeout(() => {{
          button.disabled = false;
          button.textContent = originalText;
        }}, 1500);
      }}
      bridge(command);
    }});
  }};
  const homeOpen = root.querySelector('[data-testid="home-open"]');
  const homeOpenCommand = homeOpen?.dataset.ankiGardenCommand || "anki-garden:open";
  bindBridgeButton('[data-testid="home-open"]', homeOpenCommand, "Opening…");
  bindBridgeButton('[data-testid="home-retry"]', "anki-garden:refresh");

  if (root.dataset.ankiGardenTooltipBound !== "true") {{
    root.dataset.ankiGardenTooltipBound = "true";
    const tip = root.querySelector(".ag-home__tooltip");
    if (tip) {{
      let active = null;
      const position = (element) => {{
        if (!element || tip.hidden) return;
        const rect = element.getBoundingClientRect();
        const margin = 8;
        const gap = 6;
        const maxLeft = Math.max(margin, window.innerWidth - tip.offsetWidth - margin);
        tip.style.left = Math.min(maxLeft, Math.max(margin, rect.left)) + "px";
        const maxTop = Math.max(margin, window.innerHeight - tip.offsetHeight - margin);
        const below = rect.bottom + gap;
        const above = rect.top - tip.offsetHeight - gap;
        tip.style.top = (below <= maxTop ? below : (above >= margin ? above : maxTop)) + "px";
      }};
      const clear = () => {{
        if (active && active.getAttribute("aria-describedby") === tip.id) {{
          active.removeAttribute("aria-describedby");
        }}
        active = null;
        tip.hidden = true;
      }};
      const show = (event) => {{
        const element = event.target.closest("[data-tooltip]");
        if (!element) return;
        if (active !== element) clear();
        active = element;
        active.setAttribute("aria-describedby", tip.id);
        tip.textContent = element.dataset.tooltip;
        tip.hidden = false;
        window.requestAnimationFrame(() => position(active));
      }};
      const hide = (event) => {{
        const related = event.relatedTarget;
        const next = related && typeof related.closest === "function"
          ? related.closest("[data-tooltip]")
          : null;
        if (next === active) return;
        clear();
      }};
      root.addEventListener("mouseover", show);
      root.addEventListener("focusin", show);
      root.addEventListener("mouseout", hide);
      root.addEventListener("focusout", hide);
      window.addEventListener("resize", () => position(active), {{ passive: true }});
      window.addEventListener("scroll", () => position(active), {{ passive: true, capture: true }});
    }}
  }}
}})();
"""
        )

    def _home_garden_html_for_injection(self) -> str:
        """Refresh Garden state without allowing it to abort Anki home rendering."""
        state_events = getattr(self, "state_events", None)
        revision = int(getattr(state_events, "revision", 0))
        cached_html = getattr(self, "_home_html_cache", None)
        cached_revision = int(getattr(self, "_home_html_revision", -1))
        if cached_html is not None and cached_revision == revision:
            return cached_html
        if not self._run_garden_maintenance("home rendering"):
            request_id = self._home_widget_controller.begin_request()
            self._home_widget_controller.resolve_error(
                request_id,
                "Garden progress could not refresh. Your Anki screen is still available; retry the Garden.",
            )
            html = render_home_widget(self._home_widget_controller.snapshot)
        else:
            html = self._build_home_garden_html()
        self._home_html_cache = html
        self._home_html_revision = int(getattr(state_events, "revision", revision))
        return html

    def _build_home_garden_html(self) -> str:
        request_id = self._home_widget_controller.begin_request()
        try:
            state = self.storage.state
            peek_transitions = getattr(self.engine, "peek_stage_transitions", None)
            transitions = peek_transitions() if callable(peek_transitions) else []
            transition_message_builder = getattr(self.engine, "stage_transition_message", None)
            transition_message = transition_message_builder(transitions) if callable(transition_message_builder) else ""
            scene_items = self._home_scene_items()
            data = build_home_widget_success_data(
                state=state,
                reviews_today=self._reviews_today(),
                scene_items=scene_items,
                background_placement=getattr(self, "_home_background_placement", {}),
                stage_transition_message=transition_message,
                background_url=self._home_background_url(),
                garden_overlay_url=self._home_garden_overlay_url(),
                nurtured_marker_url=self._home_nurtured_marker_url(),
                nurtured_marker_spout_right_url=(
                    self._home_nurtured_marker_spout_right_url()
                ),
                status_notice=USER_NOTICES.current.message,
            )
            self._home_widget_controller.resolve_success(request_id, data)
        except Exception:
            logger.exception("Anki Garden: failed to build home garden html")
            self._home_widget_controller.resolve_error(request_id, "Unable to load garden stats right now. Retry to refresh.")
        return render_home_widget(self._home_widget_controller.snapshot)

    def _plant_badges_html(self) -> str:
        plants = self.storage.state.plants[:4]
        if not plants:
            return '<div class="ag-home__plant"><div class="ag-home__plant-name">Seedling</div></div>'
        badges = []
        for plant in plants:
            plant_name = escape(str(plant.name))
            image_html = self._plant_badge_image_html(plant)
            badges.append(
                f'<div class="ag-home__plant">{image_html}'
                f'<div class="ag-home__plant-name">{plant_name}</div></div>'
            )
        return "".join(badges)

    def _home_scene_items(self) -> list[dict[str, object]]:
        try:
            background = getattr(self.engine, "resolve_background_asset", lambda: None)()
        except Exception:
            logger.debug("Anki Garden: unable to resolve home scene background placement", exc_info=True)
            background = None
        background_placement = background.placement.to_dict() if background is not None else {}
        surface_profile = background_placement.get("surface_profile")
        variants = surface_profile.get("variants", {}) if isinstance(surface_profile, dict) else {}
        if isinstance(variants, dict):
            addon_root = Path(__file__).parent.resolve()
            for variant in variants.values():
                if not isinstance(variant, dict):
                    continue
                for source_key, url_key in (("file", "url"), ("occlusion_file", "occlusion_url")):
                    rel = str(variant.get(source_key, ""))
                    variant[url_key] = self._asset_web_url(addon_root / rel) if rel else ""
                raw_layers = variant.get("occlusion_layers", {})
                if isinstance(raw_layers, dict):
                    variant["occlusion_layer_urls"] = {
                        layer: self._asset_web_url(addon_root / str(rel))
                        for layer, rel in raw_layers.items()
                        if layer in {"rear", "front"} and rel
                    }
        planter_family = (
            surface_profile.get("planter_family", {})
            if isinstance(surface_profile, dict)
            else {}
        )
        planter_variants = (
            planter_family.get("variants", {})
            if isinstance(planter_family, dict)
            else {}
        )
        if isinstance(planter_variants, dict):
            addon_root = Path(__file__).parent.resolve()
            for variant in planter_variants.values():
                if not isinstance(variant, dict):
                    continue
                for source_key, url_key in (
                    ("file", "url"),
                    ("foreground_file", "foreground_url"),
                ):
                    rel = str(variant.get(source_key, ""))
                    variant[url_key] = self._asset_web_url(addon_root / rel) if rel else ""
        background_theme = str((background.metadata.get("slot") or {}).get("theme", "verdant_twilight")) if background is not None else "verdant_twilight"
        # The Home renderer needs surface variants and empty-bed anchors even
        # before a starter is chosen or when every plant is shelved.
        self._home_background_placement = background_placement
        items: list[dict[str, object]] = []
        planted = [plant for plant in self.storage.state.plants if plant.slot_index is not None]
        for plant in sorted(planted, key=lambda row: int(row.slot_index))[:6]:
            try:
                asset = self.engine.resolve_plant_asset(plant.species, plant.growth_stage)
            except Exception:
                logger.debug("Anki Garden: unable to resolve home scene plant artwork", exc_info=True)
                asset = None
            item = {
                "plant_id": plant.plant_id,
                "slot_index": plant.slot_index,
                "name": plant.name,
                "species": plant.species,
                "stage": plant.growth_stage,
                "is_active": plant.plant_id == self.storage.state.active_plant_id,
                "url": self._asset_web_url(asset.path) if asset is not None else "",
                "placement": asset.placement.to_dict() if asset is not None else {},
                "canvas_aspect": (
                    float(asset.metadata.get("width", 1)) / max(1.0, float(asset.metadata.get("height", 1)))
                    if asset is not None else 1.0
                ),
                "background_placement": background_placement,
                "background_theme": background_theme,
            }
            items.append(item)
        return items

    def _plant_badge_image_html(self, plant: object) -> str:
        resolver = getattr(self.engine, "resolve_plant_image", None)
        if resolver is None:
            return ""
        try:
            path = resolver(plant.species, plant.growth_stage)
        except Exception:
            logger.debug("Anki Garden: unable to resolve home widget plant image", exc_info=True)
            return ""
        if not path:
            return ""
        src = self._asset_web_url(path)
        if not src:
            return ""
        plant_name = escape(str(getattr(plant, "name", "Plant")), quote=True)
        return f'<img class="ag-home__plant-thumb" src="{src}" alt="{plant_name}">'

    def _home_background_url(self) -> str:
        resolver = getattr(self.engine, "resolve_background_asset", None)
        try:
            asset = resolver() if callable(resolver) else None
            path = asset.path if asset is not None and hasattr(asset, "path") else self.engine.resolve_background_image()
        except Exception:
            logger.debug("Anki Garden: unable to resolve home widget background", exc_info=True)
            return ""
        return self._asset_web_url(path)

    def _home_garden_overlay_url(self) -> str:
        resolver = getattr(self.engine, "resolve_garden_overlay_asset", None)
        try:
            asset = resolver() if callable(resolver) else None
            path = asset.path if asset is not None and hasattr(asset, "path") else None
        except Exception:
            logger.debug("Anki Garden: unable to resolve home garden-bed overlay", exc_info=True)
            return ""
        return self._asset_web_url(path)

    def _home_nurtured_marker_url(self) -> str:
        resolver = getattr(self.engine, "resolve_nurtured_marker_asset", None)
        try:
            asset = resolver() if callable(resolver) else None
            path = (
                asset.path
                if asset is not None and hasattr(asset, "path")
                else self.engine.resolve_nurtured_marker_image()
            )
        except Exception:
            logger.debug(
                "Anki Garden: unable to resolve home Nurturing marker",
                exc_info=True,
            )
            return ""
        return self._asset_web_url(path)

    def _home_nurtured_marker_spout_right_url(self) -> str:
        resolver = getattr(
            self.engine,
            "resolve_nurtured_marker_spout_right_asset",
            None,
        )
        try:
            asset = resolver() if callable(resolver) else None
            image_resolver = getattr(
                self.engine,
                "resolve_nurtured_marker_spout_right_image",
                None,
            )
            path = (
                asset.path
                if asset is not None and hasattr(asset, "path")
                else image_resolver() if callable(image_resolver) else None
            )
        except Exception:
            logger.debug(
                "Anki Garden: unable to resolve right-facing Nurturing marker",
                exc_info=True,
            )
            return ""
        return self._asset_web_url(path)

    def _asset_web_url(self, path: object) -> str:
        if not path:
            return ""
        try:
            image_path = Path(str(path)).expanduser()
            if not image_path.exists() or not image_path.is_file() or image_path.suffix.lower() not in {".svg", ".png", ".webp"}:
                return ""
            addon_dir = Path(__file__).parent.resolve()
            relative = image_path.resolve().relative_to(addon_dir).as_posix()
            package = mw.addonManager.addonFromModule(__name__)
            return f"/_addons/{quote(str(package), safe='')}/{quote(relative, safe='/')}"
        except Exception:
            return ""

    def _reviews_today(self) -> int:
        fallback = int(getattr(self.storage.state.daily_stats, "reviewed", 0))
        try:
            collection = getattr(mw, "col", None)
            if collection is None or getattr(collection, "db", None) is None:
                DISPLAY_TELEMETRY.record_missing_or_invalid_field(
                    route="home_widget",
                    field="collection.db",
                    reason="missing_collection_db",
                    required=True,
                )
                DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="reviews_today")
                return fallback
            day_start_ms, day_end_ms = self.storage.current_scheduler_day_bounds_ms()
            day_start_ms = int(day_start_ms)
            day_end_ms = int(day_end_ms)
            if day_start_ms <= 0 or day_end_ms <= day_start_ms:
                DISPLAY_TELEMETRY.record_missing_or_invalid_field(
                    route="home_widget",
                    field="scheduler.day_cutoff",
                    reason="invalid_day_cutoff",
                    required=True,
                )
                DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="reviews_today")
                return fallback
            count = collection.db.scalar(
                "select count(*) from revlog where id >= ? and id < ? "
                "and type in (0, 1, 2, 3)",
                day_start_ms,
                day_end_ms,
            )
            return max(0, int(count or 0))
        except Exception as exc:
            DISPLAY_TELEMETRY.track_parsing_exception(route="home_widget", field="reviews_today", exc=exc)
            DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="reviews_today")
            return fallback

    def _apply_same_day_catchup(self) -> tuple[int, int]:
        collection = getattr(mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RuntimeError("Anki review history is not available yet")
        last_id = int(self.storage.state.last_processed_revlog_id or 0)
        day_rows = self.storage.load_new_revlog_entries(last_id)
        rows = ReviewerHookHandler.unseen_revlog_rows(day_rows, self.storage.state)
        if not rows:
            if last_id == 0:
                # Use the scheduler-day boundary as a historical sentinel.
                # Reading max(id) after an empty row query has a race: a review
                # committed between those reads could be skipped forever.
                bootstrap_id = max(0, int(self.storage.current_day_start_ms()) - 1)
                previous_floor = int(
                    getattr(self.storage.state, "processed_revlog_floor", 0) or 0
                )
                previous_ids = list(
                    getattr(self.storage.state, "processed_revlog_ids", []) or []
                )
                self.storage.state.last_processed_revlog_id = bootstrap_id
                self.storage.state.processed_revlog_floor = bootstrap_id
                self.storage.state.processed_revlog_ids = []
                try:
                    self.storage.save()
                except Exception:
                    self.storage.state.last_processed_revlog_id = last_id
                    self.storage.state.processed_revlog_floor = previous_floor
                    self.storage.state.processed_revlog_ids = previous_ids
                    raise
            if self.dashboard:
                try:
                    self.dashboard.show_same_day_catchup_feedback(0, 0)
                except Exception:
                    logger.debug("Anki Garden: unable to clear synced-review notice", exc_info=True)
            return 0, 0

        payloads = []
        latest_id = last_id
        for row in rows:
            rid = int(row[0])
            latest_id = max(latest_id, int(rid))
            payload = ReviewerHookHandler.review_payload_from_row(row, collection)
            # Manual and rescheduled revlog rows are not answered cards and must
            # advance the cursor without producing Garden progress.
            if payload is not None:
                payloads.append(payload)
        gained = self.engine.apply_same_day_reviews(payloads, latest_revlog_id=latest_id)
        try:
            self.engine.evaluate_all_due(self.storage.due_obligations())
        except Exception:
            logger.debug("Anki Garden: unable to evaluate all-due completion after catch-up", exc_info=True)
        return len(payloads), gained

_app: Optional[AnkiGardenApp] = None


def setup_addon() -> None:
    global _app
    if mw is None:
        return
    _app = AnkiGardenApp()
    _app.setup()
