from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from aqt import mw
from aqt.gui_hooks import reviewer_did_answer_card
from aqt.qt import QAction

from .config import ConfigManager
from .display_telemetry import DISPLAY_TELEMETRY
from .game import GardenGameEngine, difficulty_from_factor, queue_and_lapse_from_revlog_type
from .hooks.reviewer import ReviewerHookHandler
from .notices import USER_NOTICES
from .storage import GardenStorage
from .ui.dashboard import GardenDashboard
from .ui.home_widget import (
    HomeWidgetStateController,
    build_home_widget_success_data,
    render_home_widget,
)
from .ui.plant_display import growth_display

logger = logging.getLogger(__name__)


class AnkiGardenApp:
    def __init__(self) -> None:
        self.config = ConfigManager(mw)
        self.storage = GardenStorage(mw, self.config)
        self.engine = GardenGameEngine(self.config, self.storage)
        self.reviewer_hooks = ReviewerHookHandler(self.engine, self.storage)
        self.dashboard: Optional[GardenDashboard] = None
        self._menu_action: Optional[QAction] = None
        self._home_widget_hooked = False
        self._home_bridge_hooked = False
        self._reviewer_hooked = False
        self._sync_hooked = False
        self._sync_callback = self._on_sync_finished
        self._home_widget_controller = HomeWidgetStateController()
        self._dashboard_open_pending = False
        self._dashboard_open_attempts = 0

    def setup(self) -> None:
        try:
            mw.addonManager.setWebExports(__name__, r"assets/.*\.(svg|png|webp)")
        except Exception:
            logger.exception("Anki Garden: unable to register bundled web assets")
        self._setup_menu()
        self._setup_home_screen_widget()
        self._setup_reviewer_hook()
        self._setup_sync_hooks()
        self._apply_retrospective_growth()
        self.engine.rollover_if_needed()

    def _setup_reviewer_hook(self) -> None:
        if self._reviewer_hooked:
            return
        reviewer_did_answer_card.append(self.reviewer_hooks.on_answer)
        self._reviewer_hooked = True

    def _setup_menu(self) -> None:
        if self._menu_action is not None:
            return

        existing_actions = []
        menu_tools = getattr(getattr(mw, "form", None), "menuTools", None)
        if menu_tools is not None and hasattr(menu_tools, "actions"):
            try:
                existing_actions = list(menu_tools.actions())
            except Exception:
                existing_actions = []

        for action in existing_actions:
            if getattr(action, "text", lambda: "")() == "Anki Garden":
                self._menu_action = action
                logger.debug("Anki Garden menu action already registered.")
                return

        action = QAction("Anki Garden", mw)
        action.triggered.connect(self.open_dashboard)
        mw.form.menuTools.addAction(action)
        self._menu_action = action

    def open_dashboard(self) -> None:
        if getattr(self, "_dashboard_open_pending", False):
            return
        self._dashboard_open_pending = True
        self._dashboard_open_attempts = 0
        self._schedule_dashboard_open(0)

    def _schedule_dashboard_open(self, delay_ms: int) -> None:
        try:
            from aqt.qt import QTimer

            QTimer.singleShot(max(0, int(delay_ms)), self._open_dashboard_when_ready)
        except Exception:
            self._dashboard_open_pending = False
            logger.exception("Anki Garden: unable to schedule dashboard opening")

    def _dashboard_is_alive(self) -> bool:
        if self.dashboard is None:
            return False
        try:
            self.dashboard.isVisible()
            return True
        except RuntimeError:
            self.dashboard = None
            return False

    def _clear_dashboard_reference(self, *_args: object) -> None:
        self.dashboard = None

    def _open_dashboard_when_ready(self) -> None:
        collection = getattr(mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            self._dashboard_open_attempts += 1
            if self._dashboard_open_attempts <= 10:
                self._schedule_dashboard_open(100)
                return
            self._dashboard_open_pending = False
            logger.warning("Anki Garden: dashboard opening timed out while waiting for the collection")
            self._notify_dashboard_open_failure(
                "Anki Garden is still waiting for the collection to finish opening. Please try again."
            )
            return
        candidate = None
        try:
            self._apply_retrospective_growth()
            self.engine.rollover_if_needed()
            if not self._dashboard_is_alive():
                candidate = GardenDashboard(mw, self.engine, self.storage, self.config)
                candidate.destroyed.connect(self._clear_dashboard_reference)
                self.dashboard = candidate
            self.dashboard.refresh_all()
            show_normal = getattr(self.dashboard, "showNormal", None)
            if callable(show_normal):
                show_normal()
            else:
                self.dashboard.show()
            self.dashboard.raise_()
            activate = getattr(self.dashboard, "activateWindow", None)
            if callable(activate):
                activate()
        except Exception:
            if candidate is not None and self.dashboard is candidate:
                self.dashboard = None
            logger.exception("Anki Garden: dashboard failed to open; the next attempt may retry")
            self._notify_dashboard_open_failure(
                "Anki Garden could not open its window. No garden progress was changed; please try again."
            )
        finally:
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
        self._apply_retrospective_growth()

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
        if command == "refresh":
            self.engine.rollover_if_needed()
            self._apply_retrospective_growth()
            reset = getattr(mw, "reset", None)
            if callable(reset):
                reset()
            return True, None
        return handled

    def _inject_home_garden(self, _page: object, content: object) -> None:
        if not self.config.value("show_home_widget", True):
            return
        self.engine.rollover_if_needed()
        self._apply_retrospective_growth()

        html = self._build_home_garden_html()
        if hasattr(content, "stats") and isinstance(content.stats, str):
            if "ag-home-root" not in content.stats:
                content.stats += html
            return

        if hasattr(content, "table") and isinstance(content.table, str):
            if "ag-home-root" not in content.table:
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

        logger.debug("Anki Garden: injecting home garden into context %s", context_name)
        self.engine.rollover_if_needed()
        self._apply_retrospective_growth()
        html = self._build_home_garden_html()

        body = getattr(web_content, "body", None)
        if isinstance(body, str) and "ag-home-root" not in body:
            web_content.body = body + html

    def _build_home_garden_html(self) -> str:
        request_id = self._home_widget_controller.begin_request()
        try:
            state = self.storage.state
            focus_resolver = getattr(self.engine, "focus_plant", None)
            focus_plant = focus_resolver() if callable(focus_resolver) else None
            next_milestone_resolver = getattr(self.engine, "next_milestone", None)
            pending_milestone_resolver = getattr(self.engine, "pending_milestone", None)
            peek_transitions = getattr(self.engine, "peek_stage_transitions", None)
            transitions = peek_transitions() if callable(peek_transitions) else []
            transition_message_builder = getattr(self.engine, "stage_transition_message", None)
            transition_message = transition_message_builder(transitions) if callable(transition_message_builder) else ""
            data = build_home_widget_success_data(
                state=state,
                reviews_today=self._reviews_today(),
                health_ratio=self.engine.garden_health_index(),
                growth_cap=max(1, int(self.config.value("daily_goal", 140))),
                scene_items=self._home_scene_items(),
                stage_transition_message=transition_message,
                background_url=self._home_background_url(),
                garden_overlay_url=self._home_garden_overlay_url(),
                focus_plant=focus_plant,
                focus_display=(
                    growth_display(focus_plant.growth_points, focus_plant.rare_variant)
                    if focus_plant is not None else None
                ),
                next_milestone=(next_milestone_resolver() if callable(next_milestone_resolver) else None),
                milestone_ready=(
                    pending_milestone_resolver() is not None if callable(pending_milestone_resolver) else False
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
        background_theme = str((background.metadata.get("slot") or {}).get("theme", "verdant_dusk")) if background is not None else "verdant_dusk"
        items: list[dict[str, object]] = []
        for plant in sorted(self.storage.state.plants, key=lambda row: row.slot_index)[:6]:
            try:
                asset = self.engine.resolve_plant_asset(plant.species, plant.growth_stage, plant.rare_variant)
            except Exception:
                logger.debug("Anki Garden: unable to resolve home scene plant artwork", exc_info=True)
                asset = None
            item = {
                "plant_id": plant.plant_id,
                "slot_index": plant.slot_index,
                "name": plant.name,
                "species": plant.species,
                "stage": plant.growth_stage,
                "is_focus": plant.plant_id == self.storage.state.focus_plant_id,
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
            path = resolver(plant.species, plant.growth_stage, plant.rare_variant)
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
            sched = getattr(collection, "sched", None)
            day_cutoff = getattr(sched, "day_cutoff", None)
            if day_cutoff is None:
                day_cutoff = getattr(sched, "dayCutoff", None)
            if day_cutoff is None:
                DISPLAY_TELEMETRY.record_missing_or_invalid_field(
                    route="home_widget",
                    field="scheduler.day_cutoff",
                    reason="missing_day_cutoff",
                    required=True,
                )
                DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="reviews_today")
                return fallback
            cutoff_ms = max(0, (int(day_cutoff) - 86_400) * 1000)
            count = collection.db.scalar(
                "select count(*) from revlog where id > ? and type in (0, 1, 2, 3)", cutoff_ms
            )
            return max(0, int(count or 0))
        except Exception as exc:
            DISPLAY_TELEMETRY.track_parsing_exception(route="home_widget", field="reviews_today", exc=exc)
            DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="reviews_today")
            return fallback

    def _apply_retrospective_growth(self) -> None:
        collection = getattr(mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            return
        last_id = int(self.storage.state.retrospective_last_revlog_id or 0)
        rows = self.storage.load_new_revlog_entries(last_id)
        if not rows:
            if last_id == 0:
                self.storage.state.retrospective_last_revlog_id = self.storage.max_revlog_id()
                self.storage.save()
            return

        payloads = []
        latest_id = last_id
        current_day_start_ms = self.storage.current_day_cutoff_ms()
        for rid, cid, ease, ivl, last_ivl, factor, _ms, qtype in rows:
            latest_id = max(latest_id, int(rid))
            # Synced historical reviews must advance the cursor without being
            # misreported as reviews completed today.
            if current_day_start_ms and int(rid) < current_day_start_ms:
                continue
            retrospective_kind = queue_and_lapse_from_revlog_type(qtype, ease)
            # Manual and rescheduled revlog rows are not answered cards and must
            # advance the cursor without producing garden progress.
            if retrospective_kind is None:
                continue
            queue, lapse_count = retrospective_kind
            deck_id = None
            try:
                card = mw.col.get_card(int(cid))
                deck_id = int(card.did)
            except Exception:
                pass
            delta_ivl = max(0, int(ivl) - max(0, int(last_ivl)))
            difficulty = difficulty_from_factor(factor)
            if int(ease) == 1:
                difficulty = min(1.0, difficulty + 0.15)
            payloads.append(
                {
                    "ease": int(ease),
                    "deck_id": deck_id,
                    "difficulty": difficulty,
                    "lapse_count": lapse_count,
                    "queue": queue,
                    "interval_delta": delta_ivl,
                }
            )
        gained = self.engine.apply_retrospective_reviews(payloads, latest_revlog_id=latest_id)
        if self.dashboard:
            self.dashboard.show_retrospective_feedback(len(payloads), gained)

_app: Optional[AnkiGardenApp] = None


def setup_addon() -> None:
    global _app
    if mw is None:
        return
    _app = AnkiGardenApp()
    _app.setup()
