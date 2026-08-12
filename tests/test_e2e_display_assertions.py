import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.models.state import DailyStats, GardenState, Plant


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


class _DB:
    def __init__(self, return_value=0):
        self.return_value = return_value

    def scalar(self, _query, _cutoff):
        return self.return_value


def _install_fake_aqt(monkeypatch, *, review_count: int):
    hooks = _Hooks()

    aqt_mod = types.ModuleType("aqt")
    aqt_mod.mw = SimpleNamespace(
        form=SimpleNamespace(menuTools=SimpleNamespace(addAction=lambda _a: None), toolbar=SimpleNamespace(addAction=lambda _a: None)),
        reviewer=None,
        col=SimpleNamespace(db=_DB(return_value=review_count), sched=SimpleNamespace(day_cutoff=123)),
    )

    qt_mod = types.ModuleType("aqt.qt")
    qt_mod.QAction = _Action
    qt_mod.QPushButton = _Button

    utils_mod = types.ModuleType("aqt.utils")
    utils_mod.showWarning = lambda _msg: None
    utils_mod.showInfo = lambda _msg: None

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

    dashboard_mod.GardenDashboard = _Dashboard

    monkeypatch.setitem(sys.modules, "aqt", aqt_mod)
    monkeypatch.setitem(sys.modules, "aqt.qt", qt_mod)
    monkeypatch.setitem(sys.modules, "aqt.utils", utils_mod)
    monkeypatch.setitem(sys.modules, "aqt.gui_hooks", hooks)
    monkeypatch.setitem(sys.modules, "ankigarden.ui.dashboard", dashboard_mod)

    return aqt_mod


def _seed_state(_unused: int = 50) -> GardenState:
    return GardenState(
        streak_days=8,
        selected_weather="gentle_rain",
        daily_stats=DailyStats(
            reviewed=12,
            base_growth=30,
            streak_bonus_growth=6,
            bonus_growth=6,
            growth_earned=36,
        ),
        active_plant_id="p-1",
        currency_balance=35,
        plants=[
            Plant(plant_id="p-1", species="bonsai", name="Aster", slot_index=0, growth_points=250),
            Plant(plant_id="p-2", species="wisteria", name="Wisp", slot_index=1, growth_points=50_000),
        ],
    )


def _build_seeded_app(monkeypatch, *, review_count: int, growth_cap: int = 220):
    aqt_mod = _install_fake_aqt(monkeypatch, review_count=review_count)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw

    app = addon.AnkiGardenApp.__new__(addon.AnkiGardenApp)
    app.dashboard = None
    app._home_widget_hooked = False
    app._home_bridge_hooked = False
    app._home_widget_controller = addon.HomeWidgetStateController()
    app._apply_same_day_catchup = lambda: None
    app.engine = SimpleNamespace(rollover_if_needed=lambda: None)
    app.storage = SimpleNamespace(state=_seed_state(growth_cap))
    app.config = SimpleNamespace(value=lambda _key, default=None: default)
    return app


def test_journey_load_home_to_dashboard_displays_exact_seeded_kpis(monkeypatch):
    app = _build_seeded_app(monkeypatch, review_count=27, growth_cap=240)

    html = app._build_home_garden_html()

    assert 'data-state="success"' in html
    assert 'data-testid="home-reviews"' not in html
    assert 'data-testid="home-title" aria-label="My Garden"' in html
    assert 'data-testid="home-support" title="Aster · Seed · 250 / 500 Growth"' in html
    assert "Aster, Seed stage, 250 of 500 Growth; 8-day streak; 35 Garden Coins" in html
    assert 'data-testid="home-weather"' not in html


def test_journey_review_session_then_refresh_persists_exact_values(monkeypatch):
    app = _build_seeded_app(monkeypatch, review_count=18, growth_cap=240)

    before = app._build_home_garden_html()
    assert 'data-testid="home-reviews"' not in before
    assert 'data-testid="home-support" title="Aster · Seed · 250 / 500 Growth"' in before

    app.storage.state.daily_stats.base_growth = 54
    app.storage.state.daily_stats.streak_bonus_growth = 6
    app.storage.state.daily_stats.bonus_growth = 6
    app.storage.state.daily_stats.growth_earned = 60
    app.storage.state.plants[0].growth_points = 310
    app.storage.state.streak_days = 9
    app.storage.state.selected_weather = "cloudy"

    updated = app._build_home_garden_html()
    refreshed = app._build_home_garden_html()

    assert 'data-testid="home-support" title="Aster · Seed · 310 / 500 Growth"' in updated
    assert "9-day streak" in updated
    assert 'data-testid="home-weather"' not in updated

    assert 'data-testid="home-support" title="Aster · Seed · 310 / 500 Growth"' in refreshed
    assert "9-day streak" in refreshed
    assert 'data-testid="home-weather"' not in refreshed


def test_journey_navigation_between_home_contexts_keeps_values_without_duplication(monkeypatch):
    app = _build_seeded_app(monkeypatch, review_count=42, growth_cap=210)

    deck_content = SimpleNamespace(body="<main>Deck Browser</main>")
    overview_content = SimpleNamespace(body="<main>Overview</main>")
    deck_ctx = type("DeckBrowser", (), {})()
    overview_ctx = type("Overview", (), {})()

    app._inject_home_garden_webview(deck_content, deck_ctx)
    app._inject_home_garden_webview(overview_content, overview_ctx)
    app._inject_home_garden_webview(deck_content, deck_ctx)

    assert deck_content.body.count('<div id="ag-home-root"') == 1
    assert overview_content.body.count('<div id="ag-home-root"') == 1

    for rendered in (deck_content.body, overview_content.body):
        assert 'data-testid="home-reviews"' not in rendered
        assert 'data-testid="home-support" title="Aster · Seed · 250 / 500 Growth"' in rendered
        assert "Aster, Seed stage, 250 of 500 Growth; 8-day streak; 35 Garden Coins" in rendered
