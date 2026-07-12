import importlib
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ankigarden.ui.home_widget import HomeWidgetStateController


class _Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self):
        for callback in self._callbacks:
            callback()


class _Action:
    def __init__(self, text, _parent):
        self._text = text
        self.triggered = _Signal()

    def text(self):
        return self._text


class _Menu:
    def __init__(self):
        self._actions = []

    def addAction(self, action):
        self._actions.append(action)

    def actions(self):
        return list(self._actions)


class _Button:
    def __init__(self, *_args, **_kwargs):
        self.clicked = _Signal()

    def setToolTip(self, _tip):
        return None


class _Hooks:
    def __init__(self):
        self.deck_browser_will_render_content = []
        self.overview_will_render_content = []
        self.webview_will_set_content = []
        self.webview_did_receive_js_message = []
        self.sync_did_finish = []
        self.reviewer_did_answer_card = []
        self.reviewer_did_show_question = []


class _NonIterableHook:
    def __init__(self):
        self.callbacks = []

    def append(self, callback):
        self.callbacks.append(callback)


def _install_fake_aqt(monkeypatch):
    hooks = _Hooks()
    menu_tools = _Menu()
    toolbar = _Menu()
    warnings = []
    infos = []

    class _DB:
        def __init__(self):
            self.return_value = 0

        def scalar(self, _query, _cutoff):
            return self.return_value

    aqt_mod = types.ModuleType("aqt")
    aqt_mod.mw = SimpleNamespace(
        form=SimpleNamespace(menuTools=menu_tools, toolbar=toolbar),
        reviewer=None,
        col=SimpleNamespace(db=_DB(), sched=SimpleNamespace(day_cutoff=123)),
        addonManager=SimpleNamespace(
            addonFromModule=lambda _module: "anki_garden",
            setWebExports=lambda *_args: None,
        ),
    )
    aqt_mod.gui_hooks = hooks

    qt_mod = types.ModuleType("aqt.qt")
    qt_mod.QAction = _Action
    qt_mod.QPushButton = _Button

    utils_mod = types.ModuleType("aqt.utils")
    utils_mod.showWarning = lambda msg: warnings.append(msg)
    utils_mod.showInfo = lambda msg: infos.append(msg)

    dashboard_mod = types.ModuleType("ankigarden.ui.dashboard")

    class _Dashboard:
        def __init__(self, *_args, **_kwargs):
            pass

        def refresh_all(self):
            return None

        def show(self):
            return None

        def raise_(self):
            return None

        def show_retrospective_feedback(self, *_args, **_kwargs):
            return None

    dashboard_mod.GardenDashboard = _Dashboard


    monkeypatch.setitem(sys.modules, "aqt", aqt_mod)
    monkeypatch.setitem(sys.modules, "aqt.qt", qt_mod)
    monkeypatch.setitem(sys.modules, "aqt.utils", utils_mod)
    monkeypatch.setitem(sys.modules, "aqt.gui_hooks", hooks)
    monkeypatch.setitem(sys.modules, "ankigarden.ui.dashboard", dashboard_mod)

    return aqt_mod, hooks, warnings, infos


def _new_app(addon_module):
    app = addon_module.AnkiGardenApp.__new__(addon_module.AnkiGardenApp)
    app._menu_action = None
    app.dashboard = None
    app._home_widget_hooked = False
    app._home_bridge_hooked = False
    app._reviewer_hooked = False
    app._sync_hooked = False
    app._sync_callback = app._on_sync_finished
    app._home_widget_controller = HomeWidgetStateController()
    app._apply_retrospective_growth = lambda: None
    app.engine = SimpleNamespace(
        rollover_if_needed=lambda: None,
        garden_health_index=lambda: 0.73,
    )
    app.storage = SimpleNamespace(
        state=SimpleNamespace(
            daily_stats=SimpleNamespace(reviewed=14, growth_earned=28),
            selected_weather="sunny",
            plants=[],
            streak_days=5,
            retrospective_last_revlog_id=0,
        )
    )
    app.config = SimpleNamespace(value=lambda key, default=None: 220 if key == "daily_goal" else default)
    app.open_dashboard = lambda: setattr(app, "_opened", True)
    return app


def test_startup_path_logs_errors(monkeypatch, caplog):
    _install_fake_aqt(monkeypatch)
    ankigarden = importlib.reload(importlib.import_module("ankigarden"))

    caplog.set_level(logging.ERROR)

    def _boom():
        raise RuntimeError("broken setup")

    ok = ankigarden._initialize_addon(_boom)

    assert ok is False
    assert "failed to start" in caplog.text.lower()
    assert "traceback" in caplog.text.lower()


def test_setup_menu_registers_single_action_and_callback(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw

    app = _new_app(addon)
    app._setup_menu()
    app._setup_menu()

    actions = aqt_mod.mw.form.menuTools.actions()
    assert len([a for a in actions if a.text() == "Anki Garden"]) == 1

    action = actions[0]
    app._opened = False
    action.triggered.emit()
    assert app._opened is True


def test_home_html_contains_root_id(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    html = app._build_home_garden_html()

    assert "ag-home-root" in html


def test_home_badges_use_resolved_svg_thumbnail_when_available(monkeypatch, tmp_path):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    monkeypatch.setattr(addon, "__file__", str(tmp_path / "addon.py"))
    plant_svg = tmp_path / "assets" / "rose.svg"
    plant_svg.parent.mkdir()
    plant_svg.write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
    app.storage.state.plants = [
        SimpleNamespace(name="Rose", species="rose", growth_stage="young", rare_variant=False),
    ]
    app.engine.resolve_plant_image = lambda *_args: str(plant_svg)

    html = app._plant_badges_html()

    assert 'class="ag-home__plant-thumb"' in html
    assert '/_addons/anki_garden/assets/rose.svg' in html
    assert "ag-home__plant-emoji" not in html


def test_home_badges_fall_back_to_emoji_when_svg_unavailable(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.storage.state.plants = [
        SimpleNamespace(name="Rose", species="rose", growth_stage="young", rare_variant=False),
    ]
    app.engine.resolve_plant_image = lambda *_args: None

    html = app._plant_badges_html()

    assert "ag-home__plant-emoji" in html
    assert "ag-home__plant-thumb" not in html


def test_injection_idempotent_for_render_and_webview(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    content = SimpleNamespace(stats="<div>stats</div>")
    app._inject_home_garden(object(), content)
    first = content.stats
    app._inject_home_garden(object(), content)
    assert first == content.stats

    web_content = SimpleNamespace(body="<main></main>")
    deck_ctx = type("DeckBrowser", (), {})()
    app._inject_home_garden_webview(web_content, deck_ctx)
    first_body = web_content.body
    app._inject_home_garden_webview(web_content, deck_ctx)
    assert first_body == web_content.body


def test_home_visibility_setting_gates_both_injection_paths(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.config = SimpleNamespace(value=lambda key, default=None: False if key == "show_home_widget" else default)

    content = SimpleNamespace(stats="<div>stats</div>")
    web_content = SimpleNamespace(body="<main></main>")
    app._inject_home_garden(object(), content)
    app._inject_home_garden_webview(web_content, type("DeckBrowser", (), {})())

    assert "ag-home-root" not in content.stats
    assert "ag-home-root" not in web_content.body


def test_setup_home_widget_registers_available_hooks(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    app._setup_home_screen_widget()

    assert app._inject_home_garden_webview in hooks.webview_will_set_content
    assert app._inject_home_garden in hooks.deck_browser_will_render_content
    assert app._inject_home_garden in hooks.overview_will_render_content
    assert app._handle_home_bridge_message in hooks.webview_did_receive_js_message


def test_home_bridge_opens_and_refreshes_only_main_garden_context(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    opened = []
    resets = []
    app.open_dashboard = lambda: opened.append(True)
    aqt_mod.mw.reset = lambda: resets.append(True)
    deck_ctx = type("DeckBrowser", (), {})()

    assert app._handle_home_bridge_message((False, None), "anki-garden:open", deck_ctx)[0] is True
    assert app._handle_home_bridge_message((False, None), "anki-garden:refresh", deck_ctx)[0] is True
    assert opened == [True]
    assert resets == [True]


def test_setup_home_widget_is_idempotent(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app._home_widget_hooked = False

    app._setup_home_screen_widget()
    app._setup_home_screen_widget()

    assert hooks.webview_will_set_content.count(app._inject_home_garden_webview) == 1


def test_setup_sync_hook_is_idempotent(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    app._setup_sync_hooks()
    app._setup_sync_hooks()

    assert hooks.sync_did_finish.count(app._sync_callback) == 1


def test_generated_non_iterable_hooks_register_idempotently(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    reviewer_hook = _NonIterableHook()
    sync_hook = _NonIterableHook()
    monkeypatch.setattr(addon, "reviewer_did_answer_card", reviewer_hook)
    hooks.sync_did_finish = sync_hook

    app.reviewer_hooks = SimpleNamespace(on_answer=lambda *_args: None)
    app._setup_reviewer_hook()
    app._setup_reviewer_hook()
    app._setup_sync_hooks()
    app._setup_sync_hooks()

    assert len(reviewer_hook.callbacks) == 1
    assert len(sync_hook.callbacks) == 1


def test_cards_today_uses_collection_revlog_count(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.storage.state.daily_stats.reviewed = 999
    aqt_mod.mw.col.db.return_value = 42

    html = app._build_home_garden_html()

    assert 'data-testid="home-cards">Cards Today: 42' in html
    assert 'data-testid="home-cards">Cards Today: 999' not in html


def test_webview_injection_skips_bottom_bar_context(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    web_content = SimpleNamespace(body="<main></main>")
    bottom_ctx = type("DeckBrowserBottomBar", (), {})()

    app._inject_home_garden_webview(web_content, bottom_ctx)

    assert "ag-home-root" not in web_content.body


def test_main_screen_context_detection_excludes_lower_bars(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    deck_ctx = type("DeckBrowser", (), {})()
    overview_ctx = type("Overview", (), {})()
    bottom_ctx = type("OverviewBottomToolbar", (), {})()

    assert app._is_main_screen_context(deck_ctx) is True
    assert app._is_main_screen_context(overview_ctx) is True
    assert app._is_main_screen_context(bottom_ctx) is False
