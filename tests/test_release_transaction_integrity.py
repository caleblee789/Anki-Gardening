from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.environment import CatalogItem, SCENERY_CATALOG, WEATHER_CATALOG
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
from ankigarden.storage import DueObligationStatus
from ankigarden.ui.copy import cost_label


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "ankigarden" / "ui" / "dashboard.py"
ADDON_PATH = ROOT / "ankigarden" / "addon.py"


class _Config:
    def __init__(self) -> None:
        self.data = dict(DEFAULT_CONFIG)

    def value(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def nested(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _Storage:
    def __init__(self) -> None:
        self.day = "2026-08-08"
        self.day_start_ms = 1_786_100_000_000
        self.now_ms = 1_786_150_000_000
        self.state = GardenState(
            plants=[
                Plant("p1", "bonsai", "Moss", 0),
                Plant("p2", "rose", "Briar", 1),
            ],
            active_plant_id="p1",
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.now_ms - 10_000)
            ],
        )
        self.addon_dir = ROOT / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.save_count = 0
        self.fail_save = False

    def save(self) -> None:
        self.save_count += 1
        if self.fail_save:
            raise OSError("disk full")

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return DueObligationStatus()

    def load_asset_metadata(self) -> dict[str, Any]:
        return {}

    def save_asset_metadata(self, _data: dict[str, Any]) -> None:
        return None


def _make_engine() -> tuple[GardenGameEngine, _Storage]:
    storage = _Storage()
    engine = GardenGameEngine(_Config(), storage)
    engine.assets.release_ready_plant_species = (
        lambda **_kwargs: tuple(engine.SPECIES_PRICES)
    )
    return engine, storage


def _method_node(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    module = ast.parse(path.read_text("utf-8"))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text("utf-8")
    segment = ast.get_source_segment(
        source,
        _method_node(path, class_name, method_name),
    )
    assert segment is not None
    return segment


def _compiled_method(
    path: Path,
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    method = _method_node(path, class_name, method_name)
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    globals_dict = dict(namespace or {})
    exec(compile(module, str(path), "exec"), globals_dict)
    return globals_dict[method_name]


def _set_control_enabled_stub(
    widget: Any,
    enabled: bool,
    **_kwargs: Any,
) -> None:
    widget.setEnabled(enabled)


@pytest.mark.parametrize(
    "purchase_kind",
    ["fertilizer", "species", "bed", "growth_charge", "weather"],
)
def test_unaffordable_purchase_never_debits_or_mutates_state(
    purchase_kind: str,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 0
    before = storage.state.to_dict()
    saves_before = storage.save_count

    if purchase_kind == "fertilizer":
        result = engine.purchase_fertilizer("p1", "basic")
    elif purchase_kind == "species":
        result = engine.purchase_species("sunflower")
    elif purchase_kind == "bed":
        result = engine.purchase_next_bed()
    elif purchase_kind == "growth_charge":
        result = engine.purchase_growth_charge("growth_charge_small")
    else:
        result = engine.purchase_environment("weather", "breeze")

    assert result[0] is False
    assert storage.state.to_dict() == before
    assert storage.state.currency_transactions == []
    assert storage.save_count == saves_before


def test_fertilizer_replacement_debits_once_and_rolls_back_on_save_failure() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    engine._now_seconds = lambda: 1_000.0
    assert engine.purchase_fertilizer("p1", "basic")[0]

    engine._now_seconds = lambda: 1_200.0
    balance_before = storage.state.currency_balance
    transaction_count_before = len(storage.state.currency_transactions)
    ok, _message = engine.purchase_fertilizer(
        "p1",
        "premium",
        replace_active=True,
    )

    assert ok
    new_transactions = storage.state.currency_transactions[transaction_count_before:]
    assert len(new_transactions) == 1
    assert new_transactions[0].delta == -engine.FERTILIZERS["premium"].price
    assert storage.state.currency_balance == (
        balance_before - engine.FERTILIZERS["premium"].price
    )
    assert storage.state.plants[0].fertilizer is not None
    assert storage.state.plants[0].fertilizer.tier == "premium"

    failing_engine, failing_storage = _make_engine()
    failing_storage.state.currency_balance = 500
    failing_engine._now_seconds = lambda: 1_000.0
    assert failing_engine.purchase_fertilizer("p1", "basic")[0]
    failing_engine._now_seconds = lambda: 1_200.0
    before_failed_replacement = failing_storage.state.to_dict()
    failing_storage.fail_save = True

    ok, message = failing_engine.purchase_fertilizer(
        "p1",
        "premium",
        replace_active=True,
    )

    assert not ok
    assert "no Garden Coins were spent" in message
    assert failing_storage.state.to_dict() == before_failed_replacement


def test_every_nursery_transaction_routes_through_the_shared_pending_guard() -> None:
    begin = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_begin_catalog_transaction",
    )
    release = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_catalog_transaction",
    )
    nursery = SimpleNamespace(_catalog_transaction_pending=False)

    assert begin(nursery) is True
    assert begin(nursery) is False
    release(nursery)
    assert begin(nursery) is True

    guarded_methods = (
        "_purchase_fertilizer",
        "_use_booster",
        "_purchase_growth_charge",
        "_use_growth_charge",
        "_purchase_environment",
        "_purchase_species",
        "_unlock_bed",
    )
    for method_name in guarded_methods:
        method = _method_node(DASHBOARD_PATH, "NurseryDialog", method_name)
        first_statement = method.body[0]
        assert isinstance(first_statement, ast.If), method_name
        guard_calls = [
            node
            for node in ast.walk(first_statement.test)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_begin_catalog_transaction"
        ]
        assert guard_calls, method_name
        assert any(
            isinstance(node, ast.Return)
            for statement in first_statement.body
            for node in ast.walk(statement)
        ), method_name

    release_source = _method_source(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_schedule_catalog_transaction_release",
    )
    assert "QTimer.singleShot(350, self._release_catalog_transaction)" in release_source


def test_environment_receipt_stays_bound_to_the_completed_product() -> None:
    purchase_environment = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_purchase_environment",
        {
            "WEATHER_CATALOG": WEATHER_CATALOG,
            "SCENERY_CATALOG": SCENERY_CATALOG,
        },
    )
    observed: dict[str, Any] = {}
    nursery = SimpleNamespace(
        _begin_catalog_transaction=lambda: True,
        engine=SimpleNamespace(
            purchase_environment=lambda kind, item_id: (
                True,
                f"completed:{kind}:{item_id}",
            )
        ),
        _refresh_parent=lambda: None,
        refresh=lambda: None,
        _preview_environment_item=lambda product: observed.setdefault(
            "preview_product", product
        ),
        _show_product_receipt=lambda product, message: observed.update(
            receipt_product=product,
            message=message,
        ),
        _show_result=lambda ok, message: observed.update(result=(ok, message)),
        _schedule_catalog_transaction_release=lambda: observed.update(released=True),
    )

    purchase_environment(nursery, "weather", "breeze")

    purchased = observed["receipt_product"]
    assert purchased is WEATHER_CATALOG["breeze"]
    assert observed["preview_product"] is purchased
    assert purchased.item_id == "breeze"
    assert purchased.name == "Soft Breeze"
    assert purchased.price == 100
    assert observed["message"] == "completed:weather:breeze"
    assert observed["released"] is True

    class _Status:
        def setText(self, text: str) -> None:
            self.text = text

        def setAccessibleDescription(self, text: str) -> None:
            self.accessible_description = text

        def accessibleDescription(self) -> str:
            return self.accessible_description

        def setStyleSheet(self, text: str) -> None:
            self.style = text

        def show(self) -> None:
            self.visible = True

        def setFocus(self) -> None:
            self.focused = True

        def setToolTip(self, text: str) -> None:
            self.tooltip = text

    status = _Status()
    receipt_actions = SimpleNamespace(show=lambda: setattr(receipt_actions, "visible", True))
    show_receipt = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_show_product_receipt",
        {
            "CatalogItem": CatalogItem,
            "_learner_text": lambda text: text,
            "cost_label": cost_label,
        },
    )
    announcements: list[str] = []
    show_receipt(
        SimpleNamespace(
            _status_generation=0,
            status=status,
            receipt_actions=receipt_actions,
            accessibility_announcer=SimpleNamespace(
                announce=lambda message, **_kwargs: announcements.append(message)
            ),
        ),
        purchased,
        observed["message"],
    )

    assert status.text == (
        "Soft Breeze unlocked\n"
        "Cost: 100 Garden Coins\n"
        "Owned · Ready in Customize Garden"
    )
    assert "Soft Breeze unlocked" in status.accessible_description
    assert "Cost: 100 Garden Coins" in status.accessible_description
    assert "Owned · Ready in Customize Garden" in status.accessible_description
    assert receipt_actions.visible is True
    assert announcements == [status.accessible_description]


def test_catalog_engine_exception_keeps_double_activation_guarded_until_release() -> None:
    purchase_growth_charge = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_purchase_growth_charge",
    )
    begin = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_begin_catalog_transaction",
    )
    release = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_catalog_transaction",
    )
    scheduled: list[Any] = []
    failures: list[tuple[str, bool]] = []
    engine_calls = 0

    def fail_purchase(_charge_id: str) -> tuple[bool, str]:
        nonlocal engine_calls
        engine_calls += 1
        raise RuntimeError("injected engine failure")

    nursery = SimpleNamespace(_catalog_transaction_pending=False)
    nursery._begin_catalog_transaction = lambda: begin(nursery)
    nursery._release_catalog_transaction = lambda: release(nursery)
    nursery._schedule_catalog_transaction_release = lambda: scheduled.append(
        nursery._release_catalog_transaction
    )
    nursery._show_catalog_transaction_exception = (
        lambda context, *, committed: failures.append((context, committed))
    )
    nursery._show_result = lambda *_args: None
    nursery._refresh_parent = lambda: None
    nursery.refresh = lambda: None
    nursery.engine = SimpleNamespace(purchase_growth_charge=fail_purchase)

    purchase_growth_charge(nursery, "growth_charge_small")
    purchase_growth_charge(nursery, "growth_charge_small")

    assert engine_calls == 1
    assert failures == [("Growth Charge purchase", False)]
    assert nursery._catalog_transaction_pending is True
    assert len(scheduled) == 1

    scheduled.pop()()
    assert nursery._catalog_transaction_pending is False


def test_catalog_refresh_exception_reports_saved_change_without_duplicate_use() -> None:
    use_booster = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_use_booster",
    )
    begin = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_begin_catalog_transaction",
    )
    release = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_catalog_transaction",
    )
    scheduled: list[Any] = []
    failures: list[tuple[str, bool]] = []
    engine_calls = 0

    def use_once() -> tuple[bool, str]:
        nonlocal engine_calls
        engine_calls += 1
        return True, "Booster applied"

    def fail_refresh() -> None:
        raise RuntimeError("injected refresh failure")

    nursery = SimpleNamespace(_catalog_transaction_pending=False)
    nursery._begin_catalog_transaction = lambda: begin(nursery)
    nursery._release_catalog_transaction = lambda: release(nursery)
    nursery._schedule_catalog_transaction_release = lambda: scheduled.append(
        nursery._release_catalog_transaction
    )
    nursery._show_catalog_transaction_exception = (
        lambda context, *, committed: failures.append((context, committed))
    )
    nursery._show_result = lambda *_args: None
    nursery._refresh_parent = fail_refresh
    nursery.refresh = lambda: None
    nursery.engine = SimpleNamespace(use_booster_potion=use_once)

    use_booster(nursery)
    use_booster(nursery)

    assert engine_calls == 1
    assert failures == [("Booster use", True)]
    assert nursery._catalog_transaction_pending is True
    assert len(scheduled) == 1

    scheduled.pop()()
    assert nursery._catalog_transaction_pending is False


@pytest.mark.parametrize(
    ("failure_phase", "committed"),
    (("engine", False), ("refresh", True)),
)
def test_bed_unlock_exception_restores_both_guards_and_button(
    failure_phase: str,
    committed: bool,
) -> None:
    scheduled: list[Any] = []
    unlock_bed = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_unlock_bed",
        {
            "QTimer": SimpleNamespace(
                singleShot=lambda _delay, callback: scheduled.append(callback)
            ),
            "set_control_enabled": _set_control_enabled_stub,
        },
    )
    begin = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_begin_catalog_transaction",
    )
    release = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_catalog_transaction",
    )
    release_bed = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_bed_purchase",
        {
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
            "set_control_enabled": _set_control_enabled_stub,
        },
    )

    class _Button:
        enabled = True
        visible = True

        def isEnabled(self) -> bool:
            return self.enabled

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = bool(enabled)

        def isVisible(self) -> bool:
            return self.visible

    failures: list[tuple[str, bool]] = []
    engine_calls = 0

    def purchase_next_bed() -> tuple[bool, str]:
        nonlocal engine_calls
        engine_calls += 1
        if failure_phase == "engine":
            raise RuntimeError("injected engine failure")
        return True, "Garden space unlocked"

    def refresh_parent() -> None:
        if failure_phase == "refresh":
            raise RuntimeError("injected refresh failure")

    button = _Button()
    nursery = SimpleNamespace(
        _catalog_transaction_pending=False,
        _bed_purchase_pending=False,
        _bed_button_restore_enabled=False,
        bed_button=button,
        storage=SimpleNamespace(
            state=SimpleNamespace(
                starter_selection_complete=True,
                currency_balance=500,
            )
        ),
        engine=SimpleNamespace(
            purchase_next_bed=purchase_next_bed,
            next_bed_price=lambda: 250,
        ),
    )
    nursery._begin_catalog_transaction = lambda: begin(nursery)
    nursery._release_catalog_transaction = lambda: release(nursery)
    nursery._release_bed_purchase = lambda: release_bed(nursery)
    nursery._show_catalog_transaction_exception = (
        lambda context, *, committed: failures.append((context, committed))
    )
    nursery._show_result = lambda *_args: None
    nursery._refresh_parent = refresh_parent
    nursery.refresh = lambda: None

    unlock_bed(nursery)
    unlock_bed(nursery)

    assert engine_calls == 1
    assert failures == [("garden-space purchase", committed)]
    assert nursery._catalog_transaction_pending is True
    assert nursery._bed_purchase_pending is True
    assert button.enabled is False
    assert len(scheduled) == 1

    scheduled.pop()()
    assert nursery._catalog_transaction_pending is False
    assert nursery._bed_purchase_pending is False
    assert button.enabled is True


@pytest.mark.parametrize(
    ("committed", "message_fragment"),
    (
        (False, "could not confirm that change"),
        (True, "change was saved"),
    ),
)
def test_catalog_exception_recovery_logs_and_surfaces_safe_guidance(
    committed: bool,
    message_fragment: str,
) -> None:
    log_calls: list[tuple[Any, ...]] = []
    results: list[tuple[bool, str]] = []
    show_exception = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_show_catalog_transaction_exception",
        {
            "logger": SimpleNamespace(
                exception=lambda *args, **_kwargs: log_calls.append(args)
            )
        },
    )
    nursery = SimpleNamespace(
        _show_result=lambda ok, message: results.append((ok, message))
    )

    try:
        raise RuntimeError("injected transaction failure")
    except RuntimeError:
        show_exception(nursery, "test transaction", committed=committed)

    assert log_calls
    assert results and results[0][0] is False
    assert message_fragment in results[0][1]
    assert "reopen the Nursery" in results[0][1]


def test_production_addon_ignores_capture_environment_without_build_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maybe_start_capture = _compiled_method(
        ADDON_PATH,
        "AnkiGardenApp",
        "_maybe_start_ui_face_capture",
        {
            "CAPTURE_HARNESS_ENABLED": False,
            "os": os,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )
    monkeypatch.setenv("ANKI_GARDEN_CAPTURE_UI_FACES", "1")
    app = SimpleNamespace(_ui_face_capture_active=False)

    maybe_start_capture(app)

    assert app._ui_face_capture_active is False
