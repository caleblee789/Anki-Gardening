import importlib
import inspect
import json
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

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
        self.webview_did_inject_style_into_page = []
        self.webview_did_receive_js_message = []
        self.sync_did_finish = []
        self.reviewer_did_answer_card = []
        self.reviewer_did_show_question = []
        self.state_did_change = []


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

        def scalar(self, _query, *_bounds):
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
            self.shown = False

        def refresh_all(self):
            return None

        def show(self):
            self.shown = True

        def isVisible(self):
            return self.shown

        def raise_(self):
            return None

        def show_same_day_catchup_feedback(self, *_args, **_kwargs):
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
    app.dashboard = None
    app._home_widget_hooked = False
    app._home_bridge_hooked = False
    app._reviewer_hooked = False
    app._sync_hooked = False
    app._sync_callback = app._on_sync_finished
    app._home_widget_controller = HomeWidgetStateController()
    app._dashboard_open_pending = False
    app._dashboard_open_attempts = 0
    app._dashboard_open_failures = 0
    app._settings_open_pending = False
    app._apply_same_day_catchup = lambda: None
    app.engine = SimpleNamespace(rollover_if_needed=lambda: None)
    app.storage = SimpleNamespace(
        state=SimpleNamespace(
            daily_stats=SimpleNamespace(reviewed=14, growth_earned=28),
            selected_weather="sunny",
            plants=[],
            streak_days=5,
            last_processed_revlog_id=0,
        ),
        current_day_start_ms=lambda: 1,
        current_scheduler_day_bounds_ms=lambda: (1, 2),
    )
    app.config = SimpleNamespace(value=lambda _key, default=None: default)
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


def test_setup_does_not_register_a_direct_tools_action(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw

    app = _new_app(addon)
    for method in (
        "_setup_settings_menu",
        "_setup_home_screen_widget",
        "_setup_reviewer_hook",
        "_setup_sync_hooks",
    ):
        setattr(app, method, lambda: None)
    app._run_garden_maintenance = lambda _source: True
    app.setup()

    actions = aqt_mod.mw.form.menuTools.actions()
    assert not [a for a in actions if a.text() == "Anki Garden"]


def test_startup_and_sync_use_the_same_recoverable_maintenance_boundary(monkeypatch):
    _aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    for method in (
        "_setup_settings_menu",
        "_setup_home_screen_widget",
        "_setup_reviewer_hook",
        "_setup_sync_hooks",
    ):
        setattr(app, method, lambda: None)
    sources = []
    app._run_garden_maintenance = lambda source: sources.append(source) or False

    app.setup()
    app._on_sync_finished()

    assert sources == ["startup", "sync completion"]


@pytest.mark.parametrize(
    ("source", "expects_notice"),
    (("startup", False), ("home rendering", True)),
)
def test_expected_scheduler_unavailability_defers_without_an_error_trace(
    monkeypatch, caplog, source: str, expects_notice: bool
):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    def unavailable():
        raise addon.SchedulerBoundaryError("cutoff unavailable")

    app.storage.ensure_revlog_ledger_ready = unavailable
    addon.USER_NOTICES.clear()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ankigarden.addon"):
        assert app._run_garden_maintenance(source) is False

    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert bool(addon.USER_NOTICES.current.message) is expects_notice
    if expects_notice:
        assert addon.USER_NOTICES.current.key == "review_history"


def test_successful_maintenance_clears_a_stale_user_notice(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    calls = []
    app.storage.ensure_revlog_ledger_ready = lambda: calls.append("ledger")
    app.engine.rollover_if_needed = lambda: calls.append("rollover")
    app._apply_same_day_catchup = lambda: calls.append("catch-up")
    addon.USER_NOTICES.clear()
    addon.USER_NOTICES.publish("Review-history catch-up is temporarily unavailable.", throttle_seconds=0)

    assert app._run_garden_maintenance("test") is True

    assert calls == ["ledger", "rollover", "catch-up"]
    assert addon.USER_NOTICES.current.message == ""


@pytest.mark.parametrize(
    ("notice_key", "should_clear"),
    (
        ("review_history", True),
        (None, True),
        ("display_refresh", False),
        ("other_warning", False),
    ),
)
def test_successful_maintenance_clears_only_review_history_or_legacy_notice(
    monkeypatch, notice_key, should_clear
):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.storage.ensure_revlog_ledger_ready = lambda: None
    app.engine.rollover_if_needed = lambda: None
    app._apply_same_day_catchup = lambda: (0, 0)
    addon.USER_NOTICES.clear()
    if notice_key is None:
        addon.USER_NOTICES.publish("Legacy review-history warning.", throttle_seconds=0)
    else:
        addon.USER_NOTICES.publish(
            f"{notice_key} warning.", key=notice_key, throttle_seconds=0
        )

    assert app._run_garden_maintenance("test") is True

    if should_clear:
        assert addon.USER_NOTICES.current.message == ""
    else:
        assert addon.USER_NOTICES.current.message == f"{notice_key} warning."
        assert addon.USER_NOTICES.current.key == notice_key


def test_authoritative_reviewer_success_clears_only_current_review_history_notice(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    notices = reviewer_module.USER_NOTICES
    notices.clear()

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(last_processed_revlog_id=100)
            self.fail_read = True
            self.row_id = 200
            self.mw = aqt_mod.mw

        def ensure_revlog_ledger_ready(self):
            return None

        def max_revlog_id(self):
            if self.fail_read:
                raise RuntimeError("review history unavailable")
            return self.row_id

        def load_new_revlog_entries(self, _last_processed):
            return [(self.row_id, 7, 3, 10, 5, 2500, 100, 1)]

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.config = SimpleNamespace(value=lambda _key, default=None: default)
            self.applied: list[int] = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            self.applied.extend(payload["revlog_id"] for payload in payloads)
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return len(payloads) * 10

        def evaluate_all_due(self, _status):
            return False, ""

        def peek_feedback(self):
            return []

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)

    handler.on_answer(None, SimpleNamespace(), 3)
    assert notices.current.key == "review_history"

    storage.fail_read = False
    handler.on_answer(None, SimpleNamespace(), 3)
    assert engine.applied == [200]
    assert notices.current.message == ""

    storage.fail_read = True
    storage.row_id = 300
    handler.on_answer(None, SimpleNamespace(), 3)
    assert notices.current.key == "review_history"
    notices.publish(
        "The Garden display could not refresh.",
        key="display_refresh",
        throttle_seconds=0,
    )

    storage.fail_read = False
    handler.on_answer(None, SimpleNamespace(), 3)

    assert engine.applied == [200, 300]
    assert notices.current.message == "The Garden display could not refresh."
    assert notices.current.key == "display_refresh"


def test_reviewer_starter_notice_is_once_per_reviewer_session_and_clears_on_selection(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw

    storage = SimpleNamespace(state=SimpleNamespace(starter_selection_complete=False))
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)
    shown: list[str] = []
    hidden: list[str] = []
    handler._show_no_starter_notice = lambda: shown.append("shown")
    handler._hide_no_starter_notice = lambda: hidden.append("hidden")
    aqt_mod.mw.reviewer = object()

    handler.on_question()
    handler.on_question()
    assert shown == ["shown"]

    handler.on_starter_selected()
    assert hidden[-1:] == ["hidden"]
    storage.state.starter_selection_complete = True
    handler.on_question()
    assert shown == ["shown"]

    # A new reviewer window begins a fresh, session-scoped reminder budget.
    storage.state.starter_selection_complete = False
    aqt_mod.mw.reviewer = object()
    handler.on_question()
    assert shown == ["shown", "shown"]

    notice_source = inspect.getsource(
        reviewer_module.ReviewerHookHandler._show_no_starter_notice
    )
    assert "reviewer_reward_overlay_position(" in notice_source
    assert "margin=12" in notice_source


def test_reviewer_overlay_uses_reviewer_webview_and_clears_answer_controls(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))

    reviewer_web = SimpleNamespace(width=lambda: 667, height=lambda: 570)
    main_web = SimpleNamespace(width=lambda: 900, height=lambda: 700)
    aqt_mod.mw.reviewer = SimpleNamespace(web=reviewer_web)
    aqt_mod.mw.web = main_web

    assert reviewer_module.reviewer_overlay_parent(aqt_mod.mw) is reviewer_web
    assert reviewer_module.reviewer_reward_overlay_position(
        667,
        570,
        360,
        88,
    ) == (291, 338)

    x, y = reviewer_module.reviewer_reward_overlay_position(
        667,
        570,
        400,
        104,
    )
    assert (x, y) == (251, 322)
    assert x == 667 - 400 - 16
    assert y == 570 - 104 - 144
    assert x + 400 <= 667
    assert y + 104 <= 570


def test_reviewer_toast_queue_caps_six_events_and_compacts_narrow_viewports(
    monkeypatch,
):
    _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))

    wide = [
        reviewer_module.GardenToastStack.project(count, 667)
        for count in range(1, 7)
    ]
    assert reviewer_module.GardenToastStack.MAX_VISIBLE == 2
    assert reviewer_module.GardenToastStack.PREFERRED_WIDTH == 292
    assert reviewer_module.GardenToastStack.GAP == 8
    assert reviewer_module.GardenToastStack.toast_width(667) == 292
    assert max(item.visible_count for item in wide) == 2
    assert wide[1].summary_visible is False
    assert wide[-1] == reviewer_module.ReviewerToastProjection(
        visible_count=2,
        overflow_count=5,
        compact=False,
        summary_visible=True,
    )

    narrow = reviewer_module.GardenToastStack.project(6, 420)
    assert narrow == reviewer_module.ReviewerToastProjection(
        visible_count=1,
        overflow_count=5,
        compact=True,
        summary_visible=False,
    )

    class _ToastPart:
        def setText(self, _text):
            return None

        def setPixmap(self, _pixmap):
            return None

        def show(self):
            return None

        def hide(self):
            return None

    class _ToastTimer:
        def start(self, _milliseconds):
            return None

        def stop(self):
            return None

    class _Toast:
        def __init__(self, projection):
            self.properties = {
                "rewardSummary": False,
                "compactToast": projection.compact,
                "rewardOverflowCount": (
                    projection.overflow_count if projection.compact else 0
                ),
            }
            self._garden_title_label = _ToastPart()
            self._garden_detail_label = _ToastPart()
            self._garden_message_label = _ToastPart()
            self._garden_overflow_label = _ToastPart()
            self._garden_tier_label = _ToastPart()
            self._garden_art_label = _ToastPart()
            self._garden_dismiss_timer = _ToastTimer()

        def property(self, name):
            return self.properties.get(name)

        def setProperty(self, name, value):
            self.properties[name] = value

        def setAccessibleName(self, _name):
            return None

        def width(self):
            return 292

        def height(self):
            return 64

        def move(self, _x, _y):
            return None

        def hide(self):
            return None

        def deleteLater(self):
            return None

        def raise_(self):
            return None

    parent = SimpleNamespace(width=lambda: 667, height=lambda: 570)
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), SimpleNamespace())
    for _event in range(6):
        projection = handler._prepare_reward_toast_queue(parent, 667, object())
        newest = _Toast(projection)
        handler._reward_toasts.append(newest)
        handler._reward_toast = newest

    assert len(handler._reward_toasts) == 2
    summary, newest = handler._reward_toasts
    assert summary.property("rewardSummary") is True
    assert summary.property("rewardOverflowCount") == 5
    assert newest.property("rewardSummary") is False

    compact_parent = SimpleNamespace(width=lambda: 420, height=lambda: 570)
    compact_handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(),
    )
    for _event in range(6):
        projection = compact_handler._prepare_reward_toast_queue(
            compact_parent,
            420,
            object(),
        )
        newest = _Toast(projection)
        compact_handler._reward_toasts.append(newest)
        compact_handler._reward_toast = newest

    assert len(compact_handler._reward_toasts) == 1
    compact = compact_handler._reward_toasts[0]
    assert compact.property("compactToast") is True
    assert compact.property("rewardOverflowCount") == 5


def test_reviewer_modal_deferral_retries_on_next_question(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    aqt_mod.mw.app = SimpleNamespace(activeModalWidget=lambda: object())
    assert reviewer_module.reviewer_modal_active(aqt_mod.mw) is True
    aqt_mod.mw.app = SimpleNamespace(activeModalWidget=lambda: None)
    assert reviewer_module.reviewer_modal_active(aqt_mod.mw) is False
    storage = SimpleNamespace(
        state=SimpleNamespace(starter_selection_complete=True),
        due_obligations=lambda: (),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)
    retried: list[str] = []
    handler._reward_feedback_deferred_for_modal = True
    handler._show_optional_progress_feedback = lambda: retried.append("retried")

    monkeypatch.setattr(reviewer_module, "reviewer_modal_active", lambda _mw: True)
    handler.on_question()
    assert retried == []
    assert handler._reward_feedback_deferred_for_modal is True

    monkeypatch.setattr(reviewer_module, "reviewer_modal_active", lambda _mw: False)
    handler.on_question()
    assert retried == ["retried"]
    assert handler._reward_feedback_deferred_for_modal is False


def test_reviewer_reward_overlay_is_focus_safe_and_uses_bounded_card_geometry(
    monkeypatch,
):
    _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    source = inspect.getsource(reviewer_module.ReviewerHookHandler._show_reward_toast)

    assert "reviewer_overlay_parent(mw)" in source
    assert "WA_ShowWithoutActivating" in source
    assert "WA_TransparentForMouseEvents" not in source
    assert "Qt.FocusPolicy.NoFocus" in source
    assert "class RewardToastFrame" in source
    assert "def enterEvent" in source
    assert "def leaveEvent" in source
    assert "GardenToastStack.AUTO_DISMISS_MS" in source
    assert "GardenToastStack.HOVER_RESUME_MS" in source
    assert "GardenToastStack.toast_width(viewport_width)" in source
    assert "stack_budget = max(56, int(viewport_height * 0.40))" in source
    assert "maximum_height = min(" in source
    assert "per_toast_budget" in source
    assert "Qt.AlignmentFlag.AlignBaseline" in source
    assert "reviewer_reward_overlay_position(" in source
    assert "reviewer_modal_active(mw)" in source
    assert "_prepare_reward_toast_queue(" in source
    assert "setMouseTracking(True)" in source
    assert '"reviewer-webview-right-above-controls"' in source
    assert '"reviewerViewportMargin", 16' in source
    assert '"reviewerControlClearance", 144' in source
    assert '"reviewerControlGap", 16' in source
    assert 'getattr(mw, "state", "")' in source
    assert "parent is not reviewer_web" in source
    assert ".setFocus(" not in source
    assert "keyPressEvent" not in source


def test_reviewer_reward_unmounts_when_anki_leaves_reviewer(monkeypatch):
    _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), SimpleNamespace())

    class Toast:
        def __init__(self) -> None:
            self.hidden = False
            self.deleted = False

        def hide(self) -> None:
            self.hidden = True

        def deleteLater(self) -> None:
            self.deleted = True

    toast = Toast()
    handler._reward_toast = toast
    handler._reviewer_session_window = object()
    handler._reviewer_notice_shown = True
    handler.on_state_change("deckBrowser", "review")

    assert handler._reward_toast is None
    assert toast.hidden is True
    assert toast.deleted is True
    assert handler._reviewer_session_window is None
    assert handler._reviewer_notice_shown is False


def test_reviewer_exit_summary_is_local_card_based_and_nonmodal(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    from ankigarden.ui.session_summary import (
        CommittedSessionEvent,
        SessionStartSnapshot,
        SessionSummaryAccumulator,
        TodayCardsSnapshot,
        project_session_day,
    )

    legacy_tooltips: list[str] = []
    sys.modules["aqt.utils"].tooltip = (
        lambda message, **_kwargs: legacy_tooltips.append(str(message))
    )
    state = SimpleNamespace(
        currency_balance=17,
        daily_stats=SimpleNamespace(day="2026-08-28", reviewed=126),
        daily_completion=SimpleNamespace(
            status="in_progress",
            remaining_required_reviews=18,
            remaining_learning_steps=0,
            future_learning_steps_before_cutoff=0,
        ),
        plants=[],
    )
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(state=state),
    )
    accumulator = SessionSummaryAccumulator(
        session_id="local-session",
        started_at="2026-08-28T10:00:00Z",
        anki_day_id="2026-08-28",
        start_snapshot=SessionStartSnapshot(
            TodayCardsSnapshot("in_progress", cards_remaining=144)
        ),
    )
    for index in range(126):
        accumulator.accept_committed(CommittedSessionEvent(
            event_id=f"answer:local:{index}",
            anki_day_id="2026-08-28",
            occurred_at=f"2026-08-28T10:{index // 60:02d}:{index % 60:02d}Z",
        ))
    handler._session_summary_accumulator = accumulator
    scheduled: list[object] = []
    monkeypatch.setattr(
        handler,
        "_schedule_session_summary_render",
        lambda: scheduled.append(handler._pending_session_summary),
    )

    handler.on_state_change("deckBrowser", "review")

    assert legacy_tooltips == []
    assert len(scheduled) == 1
    payload = scheduled[0]
    assert payload.cards_completed == 126
    projection = project_session_day(payload.segments[0])
    assert projection.cards_completed_value == "126"
    assert projection.cards_completed_label == "cards completed this session"
    assert projection.result_rows == ()


def test_reviewer_save_failure_uses_review_history_notice_key_and_success_clears_it(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    notices = reviewer_module.USER_NOTICES
    notices.clear()

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(last_processed_revlog_id=100)
            self.mw = aqt_mod.mw

        def ensure_revlog_ledger_ready(self):
            return None

        def max_revlog_id(self):
            return 200

        def load_new_revlog_entries(self, _last_processed):
            return [(200, 7, 3, 10, 5, 2500, 100, 1)]

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.fail_save = True
            self.config = SimpleNamespace(value=lambda _key, default=None: default)

        def apply_same_day_reviews(self, _payloads, *, latest_revlog_id):
            if self.fail_save:
                raise OSError("Garden save unavailable")
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return 10

        def evaluate_all_due(self, _status):
            return False, ""

        def peek_feedback(self):
            return []

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)

    handler.on_answer(None, SimpleNamespace(), 3)
    assert notices.current.key == "review_history"

    engine.fail_save = False
    handler.on_answer(None, SimpleNamespace(), 3)
    assert storage.state.last_processed_revlog_id == 200
    assert notices.current.message == ""


def test_reviewer_reward_feedback_keeps_delayed_correlations_separate_with_find_metadata(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    state_module = importlib.import_module("ankigarden.models.state")
    GardenFindOutcome = state_module.GardenFindOutcome
    GardenState = state_module.GardenState
    RewardReceipt = state_module.RewardReceipt
    standard_pool_version = importlib.import_module(
        "ankigarden.garden_finds"
    ).STANDARD_POOL_VERSION
    events = [
        SimpleNamespace(
            event_id="reward-summary:answer:base",
            kind="reward_summary",
            title="Review rewards",
            message="+999 coins reconstructed from stale prose",
            occurred_at="2026-08-10T10:00:00",
            amount=999,
        ),
        SimpleNamespace(
            event_id="reward-summary:answer:abc",
            kind="garden_find",
            title="Garden Find: Morning Dew",
            message="+40 Growth; +4 coins; Unlocked stale display copy",
            occurred_at="2026-08-10T10:01:00",
            amount=44,
            asset_category="ui",
            asset_key="growth",
        ),
        SimpleNamespace(
            event_id="garden-notice:answer:abc",
            kind="garden_notice",
            message="A separate Garden notice remains unchanged",
            occurred_at="2026-08-10T10:02:00",
            amount=5_000,
            correlation_id="answer:abc",
        ),
    ]
    outcome = GardenFindOutcome(
        answer_key="abc",
        scheduler_day="2026-08-10",
        status="hit",
        pool_id="standard",
        pool_version=standard_pool_version,
        occurred_at="2026-08-10T10:01:00",
        reward_id="find_morning_dew",
        reward_type="growth",
        amount=40,
        display_name="Morning Dew",
        description="+40 Growth",
        tier="Common",
        artwork_ref="growth",
    )
    state = GardenState(
        garden_find_outcomes={outcome.outcome_key: outcome},
        recent_reward_receipts=[
            RewardReceipt(
                event_key="daily_activity:2026-08-10",
                reward_type="coins",
                source="daily_activity",
                source_id="2026-08-10",
                scheduler_day="2026-08-10",
                correlation_id="answer:base",
                occurred_at="2026-08-10T10:00:00",
                amount=2,
            ),
            RewardReceipt(
                event_key="garden_find:abc:standard",
                reward_type="growth",
                source="garden_find",
                source_id="find_morning_dew",
                scheduler_day="2026-08-10",
                correlation_id="answer:abc",
                occurred_at="2026-08-10T10:01:00",
                amount=40,
                plant_id="plant:1",
                title="Morning Dew",
            ),
            RewardReceipt(
                event_key="achievement:all_due_done",
                reward_type="coins",
                source="achievement",
                source_id="all_due_done",
                scheduler_day="2026-08-10",
                correlation_id="answer:abc",
                occurred_at="2026-08-10T10:01:00",
                amount=5,
                title="All Clear",
            ),
        ],
    )
    shown: list[object] = []
    consumed: list[tuple[str, ...]] = []
    engine = SimpleNamespace(
        config=SimpleNamespace(
            value=lambda key, default=None: True if key == "show_progress_notifications" else default
        ),
        peek_feedback=lambda: list(events),
        consume_feedback=lambda *, event_ids: consumed.append(tuple(event_ids)),
    )
    storage = SimpleNamespace(
        state=state,
        # The just-committed bounded cache remains presentation authority when
        # a historical adapter query has not surfaced the row yet.
        recent_garden_find_outcomes=lambda *, limit: (),
    )
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    handler._show_reward_toast = lambda event: shown.append(event) or True

    handler._show_optional_progress_feedback()

    assert len(shown) == 2
    earlier, feedback = shown
    assert earlier.event_ids == (events[0].event_id,)
    assert earlier.message == "+2 Garden Coins"
    assert feedback.event_ids == (events[1].event_id, events[2].event_id)
    assert feedback.title == "Garden Find"
    assert feedback.message == "+5 Garden Coins · +40 Growth"
    assert feedback.reward_detail == ""
    assert (feedback.coins_total, feedback.growth_total) == (5, 40)
    assert feedback.tier == "Common"
    assert (feedback.asset_category, feedback.asset_key) == ("ui", "growth")
    assert feedback.amount == 0
    assert feedback.correlation_id == "answer:abc"
    assert consumed == [tuple(event.event_id for event in events)]
    assert handler._last_notified_event == feedback.event_id


def test_reviewer_does_not_consume_reward_when_feedback_cannot_render(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    event = SimpleNamespace(
        event_id="reward:2",
        kind="reward_summary",
        occurred_at="2026-08-10T10:02:00",
    )
    consumed: list[tuple[str, ...]] = []
    engine = SimpleNamespace(
        config=SimpleNamespace(value=lambda _key, _default=None: True),
        peek_feedback=lambda: [event],
        consume_feedback=lambda *, event_ids: consumed.append(tuple(event_ids)),
    )
    handler = reviewer_module.ReviewerHookHandler(engine, SimpleNamespace())
    handler._show_reward_toast = lambda _event: False

    handler._show_optional_progress_feedback()

    assert consumed == []
    assert handler._last_notified_event == ""


def test_reviewer_reward_copy_reports_environment_and_grouped_results() -> None:
    reviewer_module = importlib.import_module("ankigarden.hooks.reviewer")
    handler = reviewer_module.ReviewerHookHandler(
        SimpleNamespace(),
        SimpleNamespace(),
    )
    events = [
        SimpleNamespace(
            event_id=f"garden-find:{index}",
            kind="garden_find",
            title="Garden Find",
            message="",
            occurred_at=f"2026-08-10T10:0{index}:00",
            plant_id="plant:1",
            asset_category="environment",
            asset_key="firefly_evening",
            correlation_id=f"answer:{index}",
        )
        for index in range(1, 4)
    ]
    environment_find = SimpleNamespace(
        display_name="Firefly Evening",
        tier="rare",
        pool_id="environment",
        description="",
        artwork_ref="firefly_evening",
    )
    handler._garden_find_presentations = lambda _events: (environment_find,)
    handler._typed_reward_totals = lambda _events: (0, 0, 1)

    environment = handler._consolidated_reward_feedback(events[:1])

    assert environment is not None
    assert environment.title == "Garden Find"
    assert environment.tier == "Rare"
    assert environment.message == "Added to Garden Features"

    grouped_finds = tuple(
        SimpleNamespace(
            display_name=name,
            tier="common",
            pool_id="standard",
            description="",
            artwork_ref="growth",
        )
        for name in ("Morning Dew", "Fresh Soil", "Sun Shower")
    )
    handler._garden_find_presentations = lambda _events: grouped_finds
    handler._typed_reward_totals = lambda _events: (6, 80, 0)

    grouped = handler._consolidated_reward_feedback(events)

    assert grouped is not None
    assert grouped.title == "Garden Find"
    assert grouped.message == "+6 Garden Coins · +80 Growth"

    handler._typed_reward_totals = lambda _events: (1, 0, 0)
    singular = handler._consolidated_reward_feedback(events[:1])
    assert singular is not None
    assert singular.message == "+1 Garden Coin"


def test_reviewer_ack_failure_does_not_repeat_presented_rewards_when_new_feedback_arrives(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    first = SimpleNamespace(
        event_id="reward:first",
        kind="reward_summary",
        message="+2 Garden Coins",
        occurred_at="2026-08-10T10:00:00",
        amount=2,
    )
    second = SimpleNamespace(
        event_id="reward:second",
        kind="reward_summary",
        message="+40 Growth",
        occurred_at="2026-08-10T10:01:00",
        amount=40,
    )
    pending = [first]
    consume_attempts: list[tuple[str, ...]] = []

    def fail_consume(*, event_ids):
        consume_attempts.append(tuple(event_ids))
        raise RuntimeError("temporary persistence failure")

    engine = SimpleNamespace(
        config=SimpleNamespace(value=lambda _key, _default=None: True),
        peek_feedback=lambda: list(pending),
        consume_feedback=fail_consume,
    )
    storage = SimpleNamespace(
        state=SimpleNamespace(recent_reward_receipts=[], garden_find_outcomes={}),
    )
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    shown: list[object] = []
    handler._show_reward_toast = lambda event: shown.append(event) or True

    handler._show_optional_progress_feedback()
    pending.append(second)
    handler._show_optional_progress_feedback()
    handler._show_optional_progress_feedback()

    assert [event.event_ids for event in shown] == [
        ("reward:first",),
        ("reward:second",),
    ]
    assert [event.message for event in shown] == [
        "+2 Garden Coins",
        "+40 Growth",
    ]
    assert consume_attempts == [
        ("reward:first",),
        ("reward:first", "reward:second"),
        ("reward:first", "reward:second"),
    ]
    assert pending == [first, second]


def test_successful_maintenance_clears_notice_before_live_dashboard_refresh_without_reentry(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    events: list[object] = []
    resets: list[str] = []
    aqt_mod.mw.reset = lambda: resets.append("reset")
    app.storage.ensure_revlog_ledger_ready = lambda: events.append("ledger")
    app.engine.rollover_if_needed = lambda: events.append("rollover")
    app._apply_same_day_catchup = lambda: events.append("catch-up")

    class Dashboard:
        def isVisible(self):
            return True

        def refresh_all(self, **_kwargs):
            events.append(("refresh", addon.USER_NOTICES.current.message))

        def refresh_external_surfaces(self):
            events.append("external")

    app.dashboard = Dashboard()
    addon.USER_NOTICES.clear()
    addon.USER_NOTICES.publish("Stale catch-up warning.", throttle_seconds=0)

    assert app._run_garden_maintenance("test") is True

    assert events == ["ledger", "rollover", "catch-up", ("refresh", "")]
    assert resets == []


def test_dashboard_refresh_failure_does_not_flip_maintenance_success_or_repeat_progress(
    monkeypatch,
):
    _aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    calls = {"ledger": 0, "rollover": 0, "catch-up": 0, "refresh": 0}
    app.storage.ensure_revlog_ledger_ready = lambda: calls.__setitem__(
        "ledger", calls["ledger"] + 1
    )
    app.engine.rollover_if_needed = lambda: calls.__setitem__(
        "rollover", calls["rollover"] + 1
    )
    app._apply_same_day_catchup = lambda: calls.__setitem__(
        "catch-up", calls["catch-up"] + 1
    )

    class Dashboard:
        def isVisible(self):
            return True

        def refresh_all(self, **_kwargs):
            calls["refresh"] += 1
            raise RuntimeError("deleted dashboard wrapper")

    app.dashboard = Dashboard()
    addon.USER_NOTICES.clear()
    addon.USER_NOTICES.publish("Stale catch-up warning.", throttle_seconds=0)

    assert app._run_garden_maintenance("test") is True

    assert calls == {"ledger": 1, "rollover": 1, "catch-up": 1, "refresh": 1}
    assert addon.USER_NOTICES.current.key == "display_refresh"
    assert "update the garden" in addon.USER_NOTICES.current.message.lower()




def test_no_row_catchup_clears_any_visible_same_day_message(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    del app._apply_same_day_catchup
    visible_feedback: list[tuple[int, int]] = []
    app.storage.state.last_processed_revlog_id = 100
    app.storage.load_new_revlog_entries = lambda _after_id: []
    due_status = SimpleNamespace(complete=False, remaining_required_reviews=3)
    app.storage.due_obligations = lambda: due_status
    evaluated = []
    app.engine.evaluate_all_due = lambda status: evaluated.append(status) or (False, "")
    app.dashboard = SimpleNamespace(
        show_same_day_catchup_feedback=lambda count, growth: visible_feedback.append(
            (count, growth)
        )
    )

    app._apply_same_day_catchup()

    assert visible_feedback == [(0, 0)]
    assert evaluated == [due_status]


def test_maintenance_refreshes_reviewer_hud_without_open_dashboard(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    refreshed: list[str] = []
    app.reviewer_hooks = SimpleNamespace(
        refresh_from_external_state=lambda: refreshed.append("reviewer")
    )
    app.dashboard = None

    app._refresh_dashboard_after_maintenance(0, 0)

    assert refreshed == ["reviewer"]


def test_settings_action_joins_shared_caleb_addons_menu(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))

    class _Submenu(_Menu):
        def __init__(self, title):
            super().__init__()
            self._title = title
            self._object_name = ""

        def title(self):
            return self._title

        def setObjectName(self, value):
            self._object_name = value

    class _MenuAction:
        def __init__(self, submenu):
            self._submenu = submenu

        def text(self):
            return self._submenu.title()

        def menu(self):
            return self._submenu

    class _MenuBar(_Menu):
        def addMenu(self, title):
            submenu = _Submenu(title)
            self._actions.append(_MenuAction(submenu))
            return submenu

    menubar = _MenuBar()
    aqt_mod.mw.form.menubar = menubar
    app = _new_app(addon)

    app._setup_settings_menu()
    app._setup_settings_menu()

    menus = [action.menu() for action in menubar.actions()]
    assert len(menus) == 1
    assert menus[0].title() == "Caleb M. Add-ons Settings"
    assert [action.text() for action in menus[0].actions()] == ["Anki Garden settings"]


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
        SimpleNamespace(name="Rose", species="rose", growth_stage="young"),
    ]
    app.engine.resolve_plant_image = lambda *_args: str(plant_svg)

    html = app._plant_badges_html()

    assert 'class="ag-home__plant-thumb"' in html
    assert '/_addons/anki_garden/assets/rose.svg' in html
    assert "ag-home__plant-emoji" not in html


def test_home_badges_never_fall_back_to_system_emoji_when_artwork_is_unavailable(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.storage.state.plants = [
        SimpleNamespace(name="Rose", species="rose", growth_stage="young"),
    ]
    app.engine.resolve_plant_image = lambda *_args: None

    html = app._plant_badges_html()

    assert "ag-home__plant-emoji" not in html
    assert "ag-home__plant-thumb" not in html
    assert "Rose" in html


def test_home_scene_keeps_named_plant_when_asset_resolution_fails(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.storage.state.active_plant_id = "plant-1"
    app.storage.state.plants = [
        SimpleNamespace(
            plant_id="plant-1",
            name="Rose",
            species="rose",
            growth_stage="flowering",
            slot_index=0,
        ),
    ]
    app.engine.resolve_background_asset = lambda: None
    app.engine.resolve_plant_asset = lambda *_args: None

    items = app._home_scene_items()

    assert items == [{
        "plant_id": "plant-1",
        "slot_index": 0,
        "name": "Rose",
        "species": "rose",
        "stage": "flowering",
        "is_active": True,
        "url": "",
        "placement": {},
        "canvas_aspect": 1.0,
        "background_placement": {},
        "background_theme": "verdant_twilight",
    }]


def test_home_render_peeks_at_stage_transition_without_consuming_it(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    transition = SimpleNamespace(species="rose", new_stage="flowering")
    calls = {"peek": 0, "consume": 0}

    def peek():
        calls["peek"] += 1
        return [transition]

    app.engine.peek_stage_transitions = peek
    app.engine.consume_stage_transitions = lambda: calls.__setitem__("consume", calls["consume"] + 1)
    app.engine.stage_transition_message = lambda _items: "Your Rose reached Flowering!"

    first = app._build_home_garden_html()
    second = app._build_home_garden_html()

    assert "Your Rose reached Flowering!" in first
    assert "Your Rose reached Flowering!" in second
    assert calls == {"peek": 2, "consume": 0}


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


def test_same_day_catchup_read_failure_never_bootstraps_cursor_or_saves(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    storage_module = importlib.import_module("ankigarden.storage")
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app._apply_same_day_catchup = addon.AnkiGardenApp._apply_same_day_catchup.__get__(app)
    calls = {"max": 0, "save": 0, "apply": 0}

    def fail_rows(_after_id):
        raise storage_module.RevlogReadError("revlog unavailable")

    def max_revlog_id():
        calls["max"] += 1
        return 999

    app.storage = SimpleNamespace(
        state=SimpleNamespace(last_processed_revlog_id=0),
        load_new_revlog_entries=fail_rows,
        max_revlog_id=max_revlog_id,
        save=lambda: calls.__setitem__("save", calls["save"] + 1),
    )
    app.engine = SimpleNamespace(
        apply_same_day_reviews=lambda *_args, **_kwargs: calls.__setitem__(
            "apply", calls["apply"] + 1
        )
    )

    with pytest.raises(storage_module.RevlogReadError, match="revlog unavailable"):
        app._apply_same_day_catchup()

    assert app.storage.state.last_processed_revlog_id == 0
    assert calls == {"max": 0, "save": 0, "apply": 0}


def test_empty_bootstrap_uses_day_boundary_without_racing_a_new_max_row(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app._apply_same_day_catchup = addon.AnkiGardenApp._apply_same_day_catchup.__get__(app)

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(last_processed_revlog_id=0)
            self.rows = []
            self.save_calls = 0

        def load_new_revlog_entries(self, after_id):
            return [row for row in self.rows if row[0] > max(after_id, 99)]

        def current_day_start_ms(self):
            return 100

        def max_revlog_id(self):
            raise AssertionError("bootstrap must not race against a separate max query")

        def save(self):
            self.save_calls += 1

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.credited = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            self.credited.extend(payload["revlog_id"] for payload in payloads)
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return len(payloads) * 10

        def evaluate_all_due(self, _status):
            return False, ""

    storage = Storage()
    engine = Engine(storage)
    app.storage = storage
    app.engine = engine

    app._apply_same_day_catchup()
    assert storage.state.last_processed_revlog_id == 99
    assert storage.save_calls == 1

    storage.rows.append((100, 7, 3, 10, 5, 2500, 100, 1))
    app._apply_same_day_catchup()

    assert engine.credited == [100]
    assert storage.state.last_processed_revlog_id == 100


def test_structured_home_injection_keeps_native_content_and_shows_retry_on_rollover_failure(
    monkeypatch,
):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app.engine.rollover_if_needed = lambda: (_ for _ in ()).throw(
        RuntimeError("rollover unavailable")
    )
    content = SimpleNamespace(stats="<div>Native deck stats</div>")

    app._inject_home_garden(object(), content)

    assert content.stats.startswith("<div>Native deck stats</div>")
    assert 'data-state="error"' in content.stats
    assert 'data-testid="home-retry"' in content.stats


def test_webview_home_injection_keeps_native_content_and_shows_retry_on_catchup_failure(
    monkeypatch,
):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app._apply_same_day_catchup = lambda: (_ for _ in ()).throw(
        RuntimeError("catch-up unavailable")
    )
    web_content = SimpleNamespace(body="<main>Native overview</main>")

    app._inject_home_garden_webview(web_content, type("Overview", (), {})())

    assert web_content.body.startswith("<main>Native overview</main>")
    assert 'data-state="error"' in web_content.body
    assert 'data-testid="home-retry"' in web_content.body


def test_home_visibility_setting_gates_all_injection_paths(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.config = SimpleNamespace(value=lambda key, default=None: False if key == "show_home_widget" else default)

    finished_overview = SimpleNamespace(
        url=lambda: SimpleNamespace(path=lambda: "/_anki/pages/congrats.html"),
        scripts=[],
    )
    finished_overview.eval = finished_overview.scripts.append
    aqt_mod.mw.web = finished_overview
    aqt_mod.mw.state = "overview"

    content = SimpleNamespace(stats="<div>stats</div>")
    web_content = SimpleNamespace(body="<main></main>")
    app._inject_home_garden(object(), content)
    app._inject_home_garden_webview(web_content, type("DeckBrowser", (), {})())
    app._inject_home_garden_finished_overview(finished_overview)

    assert "ag-home-root" not in content.stats
    assert "ag-home-root" not in web_content.body
    assert finished_overview.scripts == []


def test_setup_home_widget_registers_available_hooks(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)

    app._setup_home_screen_widget()

    assert app._inject_home_garden_webview in hooks.webview_will_set_content
    assert app._inject_home_garden in hooks.deck_browser_will_render_content
    assert app._inject_home_garden in hooks.overview_will_render_content
    assert (
        app._inject_home_garden_finished_overview
        in hooks.webview_did_inject_style_into_page
    )
    assert app._handle_home_bridge_message in hooks.webview_did_receive_js_message


def test_finished_empty_deck_overview_injects_into_congratulations_page(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))

    class Url:
        def path(self):
            return "/_anki/pages/congrats.html"

    class WebView:
        def __init__(self):
            self.scripts = []

        def url(self):
            return Url()

        def eval(self, script):
            self.scripts.append(script)

    webview = WebView()
    aqt_mod.mw.web = webview
    aqt_mod.mw.state = "overview"
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    rendered = (
        '<style>#ag-home-root { color: green; }</style>'
        '<div id="ag-home-root"><script>window.gardenReady = true;</script></div>'
    )
    app._home_garden_html_for_injection = lambda: rendered

    app._inject_home_garden_finished_overview(webview)

    assert len(webview.scripts) == 1
    script = webview.scripts[0]
    assert 'document.getElementById("ag-home-root")' in script
    assert json.dumps(rendered) in script
    assert 'template.content.querySelectorAll("script")' in script
    assert "sourceScript.remove()" in script
    assert 'template.content.querySelector("#ag-home-root")' in script
    assert "root.replaceWith(replacement)" in script
    assert 'document.createElement("script")' not in script
    assert 'button.removeAttribute("onclick")' in script
    assert 'button.addEventListener("click"' in script
    assert 'window.bridgeCommand === "function"' in script
    assert '"anki-garden:open"' in script
    assert '"anki-garden:refresh"' in script
    assert "ankiGardenBridgeBound" in script
    assert "ankiGardenTooltipBound" in script


def test_finished_overview_bridge_command_reaches_open_dashboard(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    opened = []
    app.open_dashboard = lambda: opened.append(True)

    handled = app._handle_home_bridge_message(
        (False, None),
        "anki-garden:open",
        type("Overview", (), {})(),
    )

    assert handled == (True, None)
    assert opened == [True]


@pytest.mark.parametrize(
    ("state", "path", "is_main_webview"),
    [
        ("deckBrowser", "/_anki/pages/congrats.html", True),
        ("overview", "/decks", True),
        ("overview", "/_anki/pages/congrats.html", False),
    ],
)
def test_finished_overview_injection_is_scoped_to_main_congratulations_page(
    monkeypatch, state, path, is_main_webview
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))

    class Url:
        def path(self):
            return path

    class WebView:
        def __init__(self):
            self.scripts = []

        def url(self):
            return Url()

        def eval(self, script):
            self.scripts.append(script)

    target = WebView()
    aqt_mod.mw.web = target if is_main_webview else WebView()
    aqt_mod.mw.state = state
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app._home_garden_html_for_injection = lambda: '<div id="ag-home-root"></div>'

    app._inject_home_garden_finished_overview(target)

    assert target.scripts == []


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


def test_home_bridge_failed_retry_still_resets_to_a_recoverable_home_state(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    resets = []
    aqt_mod.mw.reset = lambda: resets.append(True)
    app._apply_same_day_catchup = lambda: (_ for _ in ()).throw(
        RuntimeError("retry unavailable")
    )

    handled = app._handle_home_bridge_message(
        (False, None),
        "anki-garden:refresh",
        type("Overview", (), {})(),
    )

    assert handled == (True, None)
    assert resets == [True]


def test_setup_home_widget_is_idempotent(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    app._home_widget_hooked = False

    app._setup_home_screen_widget()
    app._setup_home_screen_widget()

    assert hooks.webview_will_set_content.count(app._inject_home_garden_webview) == 1
    assert (
        hooks.webview_did_inject_style_into_page.count(
            app._inject_home_garden_finished_overview
        )
        == 1
    )


def test_dashboard_open_coordinator_coalesces_repeated_requests(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    del app.open_dashboard
    scheduled = []
    app._dashboard_open_pending = False
    app._schedule_dashboard_open = lambda delay: scheduled.append(delay)

    app.open_dashboard()
    app.open_dashboard()

    assert scheduled == [0]


def test_dashboard_construction_failure_does_not_poison_retry(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    del app.open_dashboard
    app._dashboard_open_pending = True
    app._dashboard_open_attempts = 0
    app.dashboard = None
    attempts = []

    class Dashboard:
        def __init__(self, *_args):
            attempts.append("construct")
            if len(attempts) == 1:
                raise RuntimeError("first-open race")
            self.destroyed = _Signal()
            self.shown = False

        def refresh_all(self):
            attempts.append("refresh")

        def showNormal(self):
            self.shown = True

        def raise_(self):
            attempts.append("raise")

        def activateWindow(self):
            attempts.append("activate")

        def isVisible(self):
            return self.shown

    monkeypatch.setattr(addon, "GardenDashboard", Dashboard)

    app._open_dashboard_when_ready()
    assert app.dashboard is None
    assert app._dashboard_open_pending is False

    app._dashboard_open_pending = True
    app._open_dashboard_when_ready()

    assert app.dashboard is not None
    assert app.dashboard.shown is True
    assert attempts.count("construct") == 2


def test_late_destroyed_signal_from_failed_dashboard_cannot_clear_replacement(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    instances = []

    class Dashboard:
        def __init__(self, *_args):
            self.index = len(instances)
            self.destroyed = _Signal()
            self.shown = False
            instances.append(self)

        def isVisible(self):
            return self.shown

        def prepare_to_show(self):
            return None

        def showNormal(self):
            if self.index == 0:
                raise RuntimeError("first dashboard failed")
            self.shown = True

        def raise_(self):
            return None

        def activateWindow(self):
            return None

        def acknowledge_rendered_feedback(self):
            return None

        def _present_starter_setup_if_needed(self):
            return None

        def close(self):
            return None

        def deleteLater(self):
            return None

    monkeypatch.setattr(addon, "GardenDashboard", Dashboard)
    app = _new_app(addon)
    del app.open_dashboard
    app._run_garden_maintenance = lambda _source: True
    app._schedule_dashboard_open = lambda _delay: None

    app._dashboard_open_pending = True
    app._open_dashboard_when_ready()
    assert app.dashboard is None

    app._dashboard_open_pending = True
    app._open_dashboard_when_ready()
    replacement = app.dashboard
    assert replacement is instances[1]

    instances[0].destroyed.emit()

    assert app.dashboard is replacement


def test_dashboard_still_opens_when_maintenance_is_safely_deferred(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    del app.open_dashboard
    app._dashboard_open_pending = True
    sources = []
    app._run_garden_maintenance = lambda source: sources.append(source) or False

    app._open_dashboard_when_ready()

    assert sources == ["dashboard open"]
    assert app.dashboard is not None
    assert app._dashboard_open_pending is False


def test_dashboard_feedback_is_acknowledged_only_after_a_successful_show(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw

    class Dashboard:
        def __init__(self, *, fail_show: bool) -> None:
            self.fail_show = fail_show
            self.shown = False
            self.events: list[str] = []

        def isVisible(self):
            return self.shown

        def prepare_to_show(self):
            self.events.append("prepare")

        def showNormal(self):
            self.events.append("show")
            if self.fail_show:
                raise RuntimeError("show failed")
            self.shown = True

        def raise_(self):
            self.events.append("raise")

        def activateWindow(self):
            self.events.append("activate")

        def acknowledge_rendered_feedback(self):
            self.events.append("acknowledge")

        def _present_starter_setup_if_needed(self):
            self.events.append("starter")

    successful = Dashboard(fail_show=False)
    app = _new_app(addon)
    app.dashboard = successful
    app._dashboard_open_pending = True
    app._run_garden_maintenance = lambda _source: True

    app._open_dashboard_when_ready()

    assert successful.events.count("acknowledge") == 1
    assert successful.events.index("show") < successful.events.index("acknowledge")

    failed = Dashboard(fail_show=True)
    failing_app = _new_app(addon)
    failing_app.dashboard = failed
    failing_app._dashboard_open_pending = True
    failing_app._run_garden_maintenance = lambda _source: True
    failing_app._schedule_dashboard_open = lambda _delay: None

    failing_app._open_dashboard_when_ready()

    assert "acknowledge" not in failed.events

    refused = Dashboard(fail_show=False)
    refused.present_over_parent = lambda: refused.events.append("present") or False
    refusing_app = _new_app(addon)
    refusing_app.dashboard = refused
    refusing_app._dashboard_open_pending = True
    refusing_app._run_garden_maintenance = lambda _source: True
    retries = []
    refusing_app._schedule_dashboard_open = lambda delay: retries.append(delay)

    refusing_app._open_dashboard_when_ready()

    assert refused.events == ["prepare", "present"]
    assert "acknowledge" not in refused.events
    assert refusing_app.dashboard is None
    assert retries == [120]


def test_settings_entry_opens_settings_without_prompting_for_a_starter(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    calls = []

    app.dashboard = SimpleNamespace(
        isVisible=lambda: True,
        refresh_all=lambda: calls.append("refresh"),
        showNormal=lambda: calls.append("show"),
        raise_=lambda: calls.append("raise"),
        activateWindow=lambda: calls.append("activate"),
        _open_settings=lambda: calls.append("settings"),
        _present_starter_setup_if_needed=lambda: calls.append("starter"),
    )
    app._dashboard_open_pending = True
    app._settings_open_pending = True

    app._open_dashboard_when_ready()

    assert "settings" in calls
    assert "starter" not in calls
    assert app._settings_open_pending is False
    assert app._dashboard_open_pending is False


def test_schedule_failure_clears_pending_settings_destination(monkeypatch):
    aqt_mod, _hooks, warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app._dashboard_open_pending = True
    app._settings_open_pending = True

    # The fake Qt module intentionally has no QTimer, exercising the terminal
    # scheduling error without starting an event loop.
    app._schedule_dashboard_open(0)

    assert app._dashboard_open_pending is False
    assert app._settings_open_pending is False
    assert warnings


def test_collection_timeout_clears_pending_settings_destination(monkeypatch):
    aqt_mod, _hooks, warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app._dashboard_open_pending = True
    app._settings_open_pending = True
    app._dashboard_open_attempts = 10
    aqt_mod.mw.col = None

    app._open_dashboard_when_ready()

    assert app._dashboard_open_pending is False
    assert app._settings_open_pending is False
    assert warnings


def test_terminal_dashboard_failure_clears_pending_settings_destination(monkeypatch):
    aqt_mod, _hooks, warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.dashboard = SimpleNamespace(
        isVisible=lambda: True,
        refresh_all=lambda: (_ for _ in ()).throw(RuntimeError("refresh failed")),
    )
    app._dashboard_open_pending = True
    app._settings_open_pending = True
    app._dashboard_open_failures = 2

    app._open_dashboard_when_ready()

    assert app.dashboard is None
    assert app._dashboard_open_pending is False
    assert app._settings_open_pending is False
    assert warnings


def test_transient_dashboard_failure_preserves_settings_destination_for_retry(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.dashboard = SimpleNamespace(
        isVisible=lambda: True,
        refresh_all=lambda: (_ for _ in ()).throw(RuntimeError("refresh failed")),
    )
    app._dashboard_open_pending = True
    app._settings_open_pending = True
    scheduled = []
    app._schedule_dashboard_open = lambda delay: scheduled.append(delay)

    app._open_dashboard_when_ready()

    assert app.dashboard is None
    assert app._dashboard_open_pending is True
    assert app._settings_open_pending is True
    assert scheduled == [120]


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


def test_reviewer_setup_registers_surface_cleanup_once(monkeypatch):
    _aqt_mod, hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    on_answer = lambda *_args: None
    on_state_change = lambda *_args: None
    app.reviewer_hooks = SimpleNamespace(
        on_answer=on_answer,
        on_state_change=on_state_change,
    )

    app._setup_reviewer_hook()
    app._setup_reviewer_hook()

    assert hooks.state_did_change.count(on_state_change) == 1


def test_reviews_today_counts_supported_revlog_answers(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.storage.state.daily_stats.reviewed = 999
    aqt_mod.mw.col.db.return_value = 42

    html = app._build_home_garden_html()

    assert app._reviews_today() == 42
    assert 'data-testid="home-reviews"' not in html
    assert '<div class="ag-home__metric-label">Card answers</div>' not in html


def test_reviews_today_never_queries_all_history_without_an_authoritative_day_start(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    addon.mw = aqt_mod.mw
    app = _new_app(addon)
    app.storage.state.daily_stats.reviewed = 17
    app.storage.current_scheduler_day_bounds_ms = lambda: (_ for _ in ()).throw(
        RuntimeError("cutoff unavailable")
    )
    aqt_mod.mw.col.db.scalar = lambda *_args: (_ for _ in ()).throw(
        AssertionError("history query must not run")
    )

    assert app._reviews_today() == 17


def test_failed_live_revlog_read_is_credited_by_catchup_exactly_once(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    storage_module = importlib.import_module("ankigarden.storage")
    notices = importlib.import_module("ankigarden.notices").USER_NOTICES
    notices.clear()
    addon.mw = aqt_mod.mw

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(last_processed_revlog_id=100)
            self.max_calls = 0
            self.save_calls = 0

        def max_revlog_id(self):
            self.max_calls += 1
            raise storage_module.RevlogReadError("max id unavailable")

        def review_type_for_revlog_id(self, _revlog_id):
            return 1

        def load_new_revlog_entries(self, after_id):
            if after_id < 200:
                return [(200, 7, 3, 10, 5, 2500, 100, 1)]
            return []

        def current_day_start_ms(self):
            return 150

        def due_obligations(self):
            return SimpleNamespace(complete=False)

        def save(self):
            self.save_calls += 1

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.live_payloads = []
            self.catchup_payloads = []

        def register_review(self, payload):
            self.live_payloads.append(payload)

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            for payload in payloads:
                if payload["revlog_id"] > self.storage.state.last_processed_revlog_id:
                    self.catchup_payloads.append(payload)
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return len(payloads) * 10

        def evaluate_all_due(self, _status):
            return False, ""

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    handler.on_answer(
        None,
        SimpleNamespace(factor=2500, queue=2, lapses=0, did=1),
        3,
    )

    app = _new_app(addon)
    app.storage = storage
    app.engine = engine
    app._apply_same_day_catchup = addon.AnkiGardenApp._apply_same_day_catchup.__get__(app)
    app._apply_same_day_catchup()
    app._apply_same_day_catchup()

    assert engine.live_payloads == []
    assert [payload["revlog_id"] for payload in engine.catchup_payloads] == [200]
    assert storage.state.last_processed_revlog_id == 200
    assert storage.save_calls == 0
    assert "will add it when review history is available" in notices.current.message


def test_reviewer_reconciles_earlier_failed_answer_with_next_callback_exactly_once(
    monkeypatch,
):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    addon.mw = aqt_mod.mw

    answer_a = (150, 7, 3, 10, 5, 2500, 100, 1)
    answer_b = (200, 8, 4, 20, 10, 2300, 100, 1)

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(last_processed_revlog_id=100)
            self.rows = [answer_a]

        def max_revlog_id(self):
            return max(row[0] for row in self.rows)

        def load_new_revlog_entries(self, after_id):
            return [row for row in self.rows if row[0] > after_id]

        def current_day_start_ms(self):
            return 125

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.attempts = []
            self.credited = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            ids = [payload["revlog_id"] for payload in payloads]
            self.attempts.append(ids)
            if len(self.attempts) == 1:
                raise OSError("review A state save failed")
            self.credited.extend(
                revlog_id
                for revlog_id in ids
                if revlog_id > self.storage.state.last_processed_revlog_id
            )
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return len(ids) * 10

        def evaluate_all_due(self, _status):
            return False, ""

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    card = SimpleNamespace(factor=2500, queue=2, lapses=0, did=1)

    handler.on_answer(None, card, 3)
    assert storage.state.last_processed_revlog_id == 100
    storage.rows.append(answer_b)
    handler.on_answer(None, card, 4)

    app = _new_app(addon)
    app.storage = storage
    app.engine = engine
    app._apply_same_day_catchup = addon.AnkiGardenApp._apply_same_day_catchup.__get__(app)
    app._apply_same_day_catchup()

    assert engine.attempts == [[150], [150, 200]]
    assert engine.credited == [150, 200]
    assert storage.state.last_processed_revlog_id == 200


def test_reviewer_counts_late_lower_same_day_id_despite_unchanged_scalar_max(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(
                last_processed_revlog_id=200,
                processed_revlog_floor=100,
                processed_revlog_ids=[200],
            )

        def max_revlog_id(self):
            return 200

        def load_new_revlog_entries(self, _after_id):
            return [
                (150, 7, 3, 10, 5, 2500, 100, 1),
                (200, 8, 4, 20, 10, 2300, 100, 1),
            ]

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.credited = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            ids = [payload["revlog_id"] for payload in payloads]
            self.credited.extend(ids)
            self.storage.state.processed_revlog_ids.extend(ids)
            self.storage.state.processed_revlog_ids.sort()
            self.storage.state.last_processed_revlog_id = max(
                self.storage.state.last_processed_revlog_id,
                latest_revlog_id,
            )
            return len(ids) * 10

        def evaluate_all_due(self, _status):
            return False, ""

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    card = SimpleNamespace(factor=2500, queue=2, lapses=0, did=1)

    handler.on_answer(None, card, 3)
    handler.on_answer(None, card, 3)

    assert engine.credited == [150]
    assert storage.state.processed_revlog_ids == [150, 200]
    assert storage.state.last_processed_revlog_id == 200


def test_catchup_never_counts_or_consumes_future_device_skew_row(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    storage_module = importlib.import_module("ankigarden.storage")
    addon.mw = aqt_mod.mw

    rows = [
        (150, 7, 3, 10, 5, 2500, 100, 1),
        (180, 7, 4, 20, 10, 2300, 100, 1),
        (250, 8, 4, 20, 10, 2300, 100, 1),
    ]

    class FilteringDb:
        def all(self, _query, lower, upper, limit):
            return [row for row in rows if lower < row[0] < upper][:limit]

    db = FilteringDb()
    aqt_mod.mw.col.db = db
    storage = object.__new__(storage_module.GardenStorage)
    storage.mw = aqt_mod.mw
    storage.state = importlib.import_module("ankigarden.models.state").GardenState(
        last_processed_revlog_id=180,
        processed_revlog_floor=99,
        processed_revlog_ids=[180],
    )
    storage.current_scheduler_day_bounds_ms = lambda: (100, 200)
    storage.current_scheduler_day = lambda: "2026-08-21"
    storage.current_day_start_ms = lambda: 100
    storage.due_obligations = lambda: SimpleNamespace(complete=False)
    binding_requests = []
    storage.answer_lineage_bindings_for_cards = lambda card_ids: (
        binding_requests.append(set(card_ids))
        or {"180": "v1|2026-08-21|7|1"}
    )

    class Engine:
        def __init__(self):
            self.ids = []
            self.last_identity = ""

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            self.ids.extend(payload["revlog_id"] for payload in payloads)
            self.last_identity = payloads[-1]["answer_identity"] if payloads else ""
            storage.state.processed_revlog_ids.extend(self.ids)
            storage.state.processed_revlog_ids.sort()
            storage.state.last_processed_revlog_id = latest_revlog_id
            return len(payloads) * 10

        def evaluate_all_due(self, _status):
            return False, ""

    app = _new_app(addon)
    app.storage = storage
    app.engine = Engine()
    app._apply_same_day_catchup = addon.AnkiGardenApp._apply_same_day_catchup.__get__(app)

    app._apply_same_day_catchup()

    assert app.engine.ids == [150]
    assert binding_requests == [{7}]
    assert app.engine.last_identity == "v1|2026-08-21|7|2"
    assert storage.state.last_processed_revlog_id == 180
    assert 250 not in storage.state.processed_revlog_ids


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


def test_same_day_catchup_revlog_mapping_matches_live_queue_semantics(monkeypatch):
    _install_fake_aqt(monkeypatch)
    game = importlib.reload(importlib.import_module("ankigarden.game"))

    assert game.queue_and_lapse_from_revlog_type(0, 3) == (1, 0)
    assert game.queue_and_lapse_from_revlog_type(1, 3) == (2, 0)
    assert game.queue_and_lapse_from_revlog_type(2, 3) == (1, 1)
    assert game.queue_and_lapse_from_revlog_type(3, 1) == (2, 1)
    assert game.queue_and_lapse_from_revlog_type(4, 3) is None


def test_maintenance_reuses_only_an_unchanged_authoritative_signature(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    calls: list[str] = []
    signature = ["2026-08-27", 200, 7]
    app.storage.maintenance_signature = lambda: tuple(signature)
    app.storage.ensure_revlog_ledger_ready = lambda: calls.append("ledger")
    app.engine.rollover_if_needed = lambda: calls.append("rollover")
    app.engine.reconcile_reward_history = lambda: calls.append("history") or (
        True,
        "ok",
    )
    app._apply_same_day_catchup = lambda: calls.append("catch-up") or (0, 0)
    app.reviewer_hooks = SimpleNamespace(
        mark_history_reconciled=lambda: calls.append("proof"),
        invalidate_history=lambda reason: calls.append(f"invalidate:{reason}"),
    )

    assert app._run_garden_maintenance("home rendering") is True
    assert app._run_garden_maintenance("dashboard open") is True
    assert calls == ["ledger", "rollover", "history", "catch-up", "proof", "proof"]

    signature[1] = 201
    assert app._run_garden_maintenance("home rendering") is True
    assert calls[-5:] == ["ledger", "rollover", "history", "catch-up", "proof"]

    app._invalidate_maintenance_cache("explicit test invalidation")
    assert app._run_garden_maintenance("home rendering") is True
    assert calls[-5:] == ["ledger", "rollover", "history", "catch-up", "proof"]


def test_reviewer_uses_proven_local_answer_without_a_full_day_scan(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    row = (200, 7, 3, 10, 5, 2500, 100, 1)
    calls: list[object] = []

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(
                last_processed_revlog_id=100,
                processed_revlog_floor=99,
                processed_revlog_ids=[],
                pending_reanswer_lineages={},
                starter_selection_complete=False,
            )
            self.mw = aqt_mod.mw

        def ensure_revlog_ledger_ready(self):
            calls.append("ledger")

        def pending_reanswer_lineages(self):
            return {}

        def load_proven_local_answer(self, **kwargs):
            calls.append(("local", kwargs))
            return SimpleNamespace(row=row, card_day_rows=(row,))

        def max_revlog_id(self):
            raise AssertionError("the proven local path must not query max(id)")

        def load_new_revlog_entries(self, _after_id):
            raise AssertionError("the proven local path must not scan the full day")

        def answer_lineage_bindings_for_cards(self, card_ids):
            calls.append(("bindings", set(card_ids)))
            return {}

        def deck_ids_for_cards(self, card_ids):
            calls.append(("decks", set(card_ids)))
            return {7: 55}

        def current_scheduler_day(self):
            return "2026-08-27"

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.payloads = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            self.payloads.extend(payloads)
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            self.storage.state.processed_revlog_ids.append(latest_revlog_id)
            return 10

        def evaluate_all_due(self, _status):
            return False, ""

    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(engine, storage)
    handler.mark_history_reconciled()

    handler.on_answer(None, SimpleNamespace(id=7), 3)

    assert [payload["revlog_id"] for payload in engine.payloads] == [200]
    assert engine.payloads[0]["deck_id"] == 55
    assert calls == [
        "ledger",
        ("local", {"after_id": 100, "card_id": 7, "ease": 3}),
        ("bindings", {7}),
        ("decks", {7}),
    ]


def test_ambiguous_local_answer_revokes_proof_and_uses_full_day_fallback(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw
    row = (200, 7, 4, 20, 10, 2300, 100, 1)
    calls: list[object] = []

    class Storage:
        def __init__(self):
            self.state = SimpleNamespace(
                last_processed_revlog_id=100,
                processed_revlog_floor=99,
                processed_revlog_ids=[],
                pending_reanswer_lineages={},
                starter_selection_complete=False,
            )
            self.mw = aqt_mod.mw

        def ensure_revlog_ledger_ready(self):
            return None

        def pending_reanswer_lineages(self):
            return {}

        def load_proven_local_answer(self, **_kwargs):
            calls.append("local-ambiguous")
            return None

        def max_revlog_id(self):
            calls.append("max")
            return 200

        def load_new_revlog_entries(self, _after_id):
            calls.append("full-day")
            return [row]

        def current_scheduler_day(self):
            return "2026-08-27"

        def due_obligations(self):
            return SimpleNamespace(complete=False)

    class Engine:
        def __init__(self, storage):
            self.storage = storage
            self.credited: list[int] = []

        def apply_same_day_reviews(self, payloads, *, latest_revlog_id):
            self.credited.extend(payload["revlog_id"] for payload in payloads)
            self.storage.state.last_processed_revlog_id = latest_revlog_id
            return 10

        def evaluate_all_due(self, _status):
            return False, ""

    invalidations: list[str] = []
    storage = Storage()
    engine = Engine(storage)
    handler = reviewer_module.ReviewerHookHandler(
        engine,
        storage,
        history_invalidated=invalidations.append,
    )
    handler.mark_history_reconciled()

    handler.on_answer(None, SimpleNamespace(id=7), 4)

    assert calls == ["local-ambiguous", "max", "full-day"]
    assert invalidations == ["local answer was ambiguous"]
    assert engine.credited == [200]
    assert handler._local_answer_fast_path_ready is True


def test_sync_undo_and_collection_reload_explicitly_revoke_history_proof(monkeypatch):
    _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    app = _new_app(addon)
    events: list[str] = []
    app.reviewer_hooks = SimpleNamespace(
        invalidate_history=lambda reason: events.append(f"invalidate:{reason}")
    )
    app._run_garden_maintenance = lambda source: events.append(f"run:{source}") or True
    app.engine.record_review_undo = lambda **_kwargs: events.append("undo-record") or False
    app.storage.current_time_ms = lambda: 123

    app._on_sync_finished()
    app._on_state_did_undo(SimpleNamespace(changes=SimpleNamespace(study_queues=True)))
    app._on_collection_did_load()

    assert events == [
        "invalidate:sync completion",
        "run:sync completion",
        "invalidate:review undo",
        "undo-record",
        "invalidate:collection reload",
    ]


def test_runtime_timing_finishes_for_early_reviewer_and_maintenance_failures(monkeypatch):
    aqt_mod, _hooks, _warnings, _infos = _install_fake_aqt(monkeypatch)
    addon = importlib.reload(importlib.import_module("ankigarden.addon"))
    reviewer_module = importlib.reload(importlib.import_module("ankigarden.hooks.reviewer"))
    reviewer_module.mw = aqt_mod.mw

    class Recorder:
        def __init__(self):
            self.finished: list[tuple[str, object]] = []

        def begin(self):
            return "marker"

        def finish(self, name, marker):
            self.finished.append((name, marker))

    recorder = Recorder()
    monkeypatch.setattr(addon, "RUNTIME_PERFORMANCE", recorder)
    monkeypatch.setattr(reviewer_module, "RUNTIME_PERFORMANCE", recorder)

    app = _new_app(addon)
    app.storage.ensure_revlog_ledger_ready = lambda: (_ for _ in ()).throw(
        RuntimeError("unavailable")
    )
    assert app._run_garden_maintenance("unknown source") is False

    storage = SimpleNamespace(
        state=SimpleNamespace(last_processed_revlog_id=0),
        ensure_revlog_ledger_ready=lambda: (_ for _ in ()).throw(
            RuntimeError("unavailable")
        ),
    )
    handler = reviewer_module.ReviewerHookHandler(SimpleNamespace(), storage)
    handler.on_answer(None, SimpleNamespace(id=1), 3)

    assert recorder.finished == [
        ("maintenance.other", "marker"),
        ("review.answer", "marker"),
    ]
