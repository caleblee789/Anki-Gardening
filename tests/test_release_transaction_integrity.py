from __future__ import annotations

import ast
import os
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.environment import (
    CatalogItem,
    GROWTH_CHARGES,
    SCENERY_CATALOG,
    WEATHER_CATALOG,
)
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    ActivePlantPeriod,
    DailyStats,
    Fertilizer,
    GardenState,
    Plant,
)
from ankigarden.purchases import (
    PurchaseAction,
    PurchaseDisposition,
    PurchaseKind,
    PurchaseOutcome,
    PurchaseRequest,
    PurchaseStatus,
    purchase_presentation,
)
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


@pytest.mark.parametrize(
    ("kind", "item_id", "target_id", "expected_name", "expected_price"),
    (
        (PurchaseKind.SPECIES, "sunflower", None, "Sunflower Seed", 150),
        (
            PurchaseKind.GROWTH_CHARGE,
            "growth_charge_small",
            None,
            "Small Growth Charge",
            30,
        ),
        (PurchaseKind.FERTILIZER, "basic", "p1", "Basic Fertilizer", 25),
        (PurchaseKind.WEATHER, "breeze", None, "Soft Breeze", 100),
        (PurchaseKind.SCENERY, "spring", None, "Spring Bloom", 400),
        (PurchaseKind.BED, "next", None, "Garden Bed 3", 150),
    ),
)
def test_purchase_quotes_share_exact_current_terms(
    kind: PurchaseKind,
    item_id: str,
    target_id: str | None,
    expected_name: str,
    expected_price: int,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000

    quote = engine.quote_purchase(kind, item_id, target_id=target_id)

    assert quote.ready
    assert quote.item_name == expected_name
    assert quote.total_price == expected_price
    assert quote.balance_before == 5_000
    assert quote.balance_after == 5_000 - expected_price
    assert quote.quantity == 1
    assert quote.descriptor.function
    assert quote.descriptor.buff
    assert quote.descriptor.activation_condition
    assert quote.descriptor.duration
    assert quote.descriptor.stacking
    assert quote.descriptor.replacement
    assert quote.descriptor.unlock_requirement
    assert quote.descriptor.mechanics_rows() == quote.descriptor.detail_rows()[1:]
    assert tuple(label for label, _value in quote.descriptor.mechanics_rows()) == (
        "Effect",
        "Activation",
        "Duration",
        "Stacking",
        "Replacement",
        "Unlock",
    )


@pytest.mark.parametrize(
    ("kind", "item_id", "target_id", "title", "action", "fact_keys"),
    (
        (
            PurchaseKind.SPECIES,
            "sunflower",
            None,
            "Purchase Sunflower Seed",
            PurchaseAction.PURCHASE,
            {"collection"},
        ),
        (
            PurchaseKind.GROWTH_CHARGE,
            "growth_charge_small",
            None,
            "Purchase Small Growth Charge",
            PurchaseAction.PURCHASE,
            {"effect", "inventory"},
        ),
        (
            PurchaseKind.FERTILIZER,
            "basic",
            "p1",
            "Purchase and apply Basic Fertilizer",
            PurchaseAction.PURCHASE_APPLY,
            {"effect", "condition"},
        ),
        (
            PurchaseKind.WEATHER,
            "breeze",
            None,
            "Purchase Soft Breeze",
            PurchaseAction.PURCHASE,
            {"effect", "equipment_limit"},
        ),
        (
            PurchaseKind.BED,
            "next",
            None,
            "Unlock Garden Bed 3",
            PurchaseAction.UNLOCK,
            {"unlocked_beds"},
        ),
    ),
)
def test_purchase_presentation_shows_only_decision_relevant_copy(
    kind: PurchaseKind,
    item_id: str,
    target_id: str | None,
    title: str,
    action: PurchaseAction,
    fact_keys: set[str],
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000

    quote = engine.quote_purchase(kind, item_id, target_id=target_id)
    presentation = purchase_presentation(quote)
    visible = " ".join((
        presentation.title,
        presentation.outcome,
        *(fact.value for fact in presentation.facts),
        *presentation.badges,
    ))

    assert presentation.title == title
    assert presentation.action is action
    assert {fact.key for fact in presentation.facts} == fact_keys
    assert "·" not in presentation.primary_label
    assert presentation.primary_accessible_name.endswith(
        f"for {quote.total_price:,} Garden Coins"
    )
    assert presentation.balance_after == 5_000 - quote.total_price
    if kind is PurchaseKind.SPECIES:
        assert presentation.outcome.endswith("Growth begins when planted.")
        assert "No Growth while in Collection" not in visible
    assert all(
        noise not in visible
        for noise in (
            "Not applicable",
            "Replaces nothing",
            "Quantity: 1",
            "Are you sure",
        )
    )


def test_fertilizer_presentations_distinguish_extension_and_replacement() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    engine._now_seconds = lambda: 1_000.0
    storage.state.plants[0].fertilizer = Fertilizer(
        "basic",
        1,
        3_700.0,
        900.0,
    )

    extension_quote = engine.quote_purchase(
        PurchaseKind.FERTILIZER,
        "basic",
        target_id="p1",
    )
    extension = purchase_presentation(extension_quote)
    assert extension.action is PurchaseAction.EXTEND
    assert extension.title == "Extend Basic Fertilizer"
    assert extension.primary_label == "Extend"
    assert extension_quote.current_seconds_remaining == 2_700
    assert extension_quote.resulting_seconds_remaining == 6_300
    assert next(
        fact.value for fact in extension.facts if fact.key == "remaining"
    ) == "45m → 1h 45m"

    replacement_quote = engine.quote_purchase(
        PurchaseKind.FERTILIZER,
        "premium",
        target_id="p1",
    )
    replacement = purchase_presentation(replacement_quote)
    assert replacement.action is PurchaseAction.PURCHASE_REPLACE
    assert replacement.primary_label == "Purchase and replace"
    assert replacement.secondary_label == "Keep current"
    assert replacement_quote.current_seconds_remaining == 2_700

    failed_replacement = purchase_presentation(
        replacement_quote,
        status=PurchaseStatus.PERSISTENCE_FAILURE,
    )
    assert failed_replacement.secondary_label == "Cancel"
    assert failed_replacement.balance_after == replacement_quote.balance_before
    assert failed_replacement.facts == ()
    assert {fact.key for fact in failed_replacement.more_details} == {
        "effect",
        "duration",
        "retry_balance",
    }

    extended = engine.confirm_purchase(PurchaseRequest.from_quote(extension_quote))
    assert extended.success
    assert extended.message == (
        "Basic Fertilizer extended to 1h 45m remaining on Moss."
    )
    assert storage.state.currency_transactions[-1].reason == (
        "Extended Basic Fertilizer on Moss"
    )


@pytest.mark.parametrize(
    ("status", "title", "primary", "show_cost", "balance_after"),
    (
        (
            PurchaseStatus.INSUFFICIENT_COINS,
            "Not enough Garden Coins",
            "View Ways to Earn",
            True,
            None,
        ),
        (
            PurchaseStatus.PERSISTENCE_FAILURE,
            "Purchase could not be saved",
            "Try again",
            True,
            5_000,
        ),
        (
            PurchaseStatus.ITEM_UNAVAILABLE,
            "Small Growth Charge unavailable",
            "Return to Nursery",
            False,
            None,
        ),
    ),
)
def test_purchase_error_presentations_have_distinct_recovery_actions(
    status: PurchaseStatus,
    title: str,
    primary: str,
    show_cost: bool,
    balance_after: int | None,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000
    quote = engine.quote_purchase(
        PurchaseKind.GROWTH_CHARGE,
        "growth_charge_small",
    )
    if status is PurchaseStatus.INSUFFICIENT_COINS:
        quote = replace(quote, balance_before=0, balance_after=-30)

    presentation = purchase_presentation(quote, status=status)

    assert presentation.title == title
    assert presentation.primary_label == primary
    assert presentation.show_cost is show_cost
    assert presentation.balance_after == balance_after
    assert presentation.terminal is (status is not PurchaseStatus.PERSISTENCE_FAILURE)
    if status is PurchaseStatus.PERSISTENCE_FAILURE:
        assert presentation.outcome == (
            "Purchase could not be saved. No Garden Coins were spent and no item was added."
        )
        assert presentation.facts == ()
        details = {fact.key: fact.value for fact in presentation.more_details}
        assert details["inventory"] == "0 → 1"
        assert details["retry_balance"] == "5,000 → 4,970"
        assert presentation.badges == ()
    if presentation.terminal:
        assert presentation.badges == ()


@pytest.mark.parametrize(
    "status",
    tuple(
        status
        for status in PurchaseStatus
        if status not in {PurchaseStatus.READY, PurchaseStatus.SUCCESS}
    ),
)
def test_non_success_purchase_presentations_never_expose_receipt_copy(
    status: PurchaseStatus,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000
    quote = engine.quote_purchase(
        PurchaseKind.GROWTH_CHARGE,
        "growth_charge_small",
    )

    presentation = purchase_presentation(quote, status=status)

    assert presentation.activity_label == ""
    assert presentation.success_message == ""
    assert presentation.next_actions == ()


@pytest.mark.parametrize(
    "status",
    (
        PurchaseStatus.STALE_PRICE,
        PurchaseStatus.STALE_BALANCE,
        PurchaseStatus.STALE_TARGET,
    ),
)
def test_stale_purchase_terms_use_one_concise_reconfirmation(
    status: PurchaseStatus,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000
    quote = engine.quote_purchase(
        PurchaseKind.GROWTH_CHARGE,
        "growth_charge_small",
    )

    presentation = purchase_presentation(quote, status=status)
    facts = {fact.key: fact for fact in presentation.facts}

    assert presentation.badges == ()
    assert "No purchase was made" not in presentation.outcome
    assert "preview" not in presentation.outcome.casefold()
    assert presentation.balance_after == 4_970
    assert all("Preview" not in fact.label for fact in presentation.facts)
    assert facts["inventory"].value == "0 → 1"
    assert "balance_preview" not in facts
    assert presentation.primary_label == "Confirm purchase"


@pytest.mark.parametrize(
    ("kind", "item_id", "target_id"),
    (
        (PurchaseKind.SPECIES, "sunflower", None),
        (PurchaseKind.GROWTH_CHARGE, "growth_charge_small", None),
        (PurchaseKind.FERTILIZER, "basic", "p1"),
        (PurchaseKind.WEATHER, "breeze", None),
        (PurchaseKind.SCENERY, "spring", None),
        (PurchaseKind.BED, "next", None),
    ),
)
def test_every_purchase_kind_commits_one_atomic_debit_and_grant(
    kind: PurchaseKind,
    item_id: str,
    target_id: str | None,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 5_000
    before_balance = storage.state.currency_balance
    saves_before = storage.save_count
    quote = engine.quote_purchase(kind, item_id, target_id=target_id)
    presentation = purchase_presentation(quote)

    outcome = engine.confirm_purchase(PurchaseRequest.from_quote(quote))

    assert outcome.success
    assert storage.state.currency_balance == before_balance - quote.total_price
    assert storage.save_count == saves_before + 1
    assert storage.state.currency_transactions[-1].delta == -quote.total_price
    assert storage.state.currency_transactions[-1].reason == {
        PurchaseKind.SPECIES: "Purchased Sunflower Seed",
        PurchaseKind.GROWTH_CHARGE: "Purchased Small Growth Charge",
        PurchaseKind.FERTILIZER: "Applied Basic Fertilizer to Moss",
        PurchaseKind.WEATHER: "Purchased Soft Breeze",
        PurchaseKind.SCENERY: "Purchased Spring Bloom",
        PurchaseKind.BED: "Unlocked Garden Bed 3",
    }[kind]
    assert storage.state.completed_purchase_requests[-1].outcome == outcome
    assert outcome.message == {
        PurchaseKind.SPECIES: "Sunflower added to your collection.",
        PurchaseKind.GROWTH_CHARGE: "Small Growth Charge added to your inventory.",
        PurchaseKind.FERTILIZER: "Basic Fertilizer applied to Moss for 1 hour.",
        PurchaseKind.WEATHER: "Soft Breeze unlocked. Preview or equip it in Collection.",
        PurchaseKind.SCENERY: "Spring Bloom unlocked. Preview or equip it in Collection.",
        PurchaseKind.BED: "Garden Bed 3 unlocked.",
    }[kind]
    assert outcome.message == presentation.success_message
    assert outcome.next_actions == presentation.next_actions
    if kind is PurchaseKind.SPECIES:
        assert any(plant.species == item_id for plant in storage.state.plants)
    elif kind is PurchaseKind.GROWTH_CHARGE:
        assert storage.state.consumables[item_id] == 1
    elif kind is PurchaseKind.FERTILIZER:
        assert storage.state.plants[0].fertilizer is not None
        assert storage.state.plants[0].fertilizer.tier == item_id
    elif kind is PurchaseKind.WEATHER:
        assert item_id in storage.state.inventory["weather"]
    elif kind is PurchaseKind.SCENERY:
        assert item_id in storage.state.inventory["scenery"]
    else:
        assert storage.state.unlocked_slots == 3


def test_confirm_purchase_is_atomic_idempotent_and_rejects_request_id_conflict() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    quote = engine.quote_purchase(PurchaseKind.SPECIES, "sunflower")
    request_id = str(uuid.uuid4())
    request = PurchaseRequest.from_quote(quote, request_id=request_id)

    first = engine.confirm_purchase(request)
    second = engine.confirm_purchase(request)

    assert first.success
    assert second == first
    assert storage.state.currency_balance == 350
    assert len([plant for plant in storage.state.plants if plant.species == "sunflower"]) == 1
    assert len([
        transaction
        for transaction in storage.state.currency_transactions
        if transaction.event_key == f"purchase-request:{request_id}"
    ]) == 1
    assert len(storage.state.completed_purchase_requests) == 1

    other_quote = engine.quote_purchase(PurchaseKind.GROWTH_CHARGE, "growth_charge_small")
    conflict = engine.confirm_purchase(PurchaseRequest.from_quote(
        other_quote,
        request_id=request_id,
    ))

    assert conflict.status is PurchaseStatus.REQUEST_ID_CONFLICT
    assert storage.state.currency_balance == 350
    assert storage.state.consumables["growth_charge_small"] == 0


def test_confirm_purchase_rejects_noncanonical_uuid_without_mutation() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    quote = engine.quote_purchase(PurchaseKind.GROWTH_CHARGE, "growth_charge_small")
    request = replace(
        PurchaseRequest.from_quote(quote),
        request_id=f"{{{uuid.uuid4()}}}",
    )
    before = storage.state.to_dict()
    saves_before = storage.save_count

    outcome = engine.confirm_purchase(request)

    assert outcome.status is PurchaseStatus.REQUEST_ID_CONFLICT
    assert storage.state.to_dict() == before
    assert storage.save_count == saves_before


def test_persistence_failure_rolls_back_and_same_request_can_be_retried() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    quote = engine.quote_purchase(PurchaseKind.WEATHER, "breeze")
    request = PurchaseRequest.from_quote(quote, request_id=str(uuid.uuid4()))
    before = storage.state.to_dict()
    storage.fail_save = True

    failed = engine.confirm_purchase(request)

    assert failed.status is PurchaseStatus.PERSISTENCE_FAILURE
    assert storage.state.to_dict() == before
    assert not engine.owns_environment("weather", "breeze")

    storage.fail_save = False
    retried = engine.confirm_purchase(request)

    assert retried.success
    assert engine.owns_environment("weather", "breeze")
    assert storage.state.currency_balance == 400


def test_confirmation_distinguishes_stale_terms_and_target_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500

    price_quote = engine.quote_purchase(
        PurchaseKind.GROWTH_CHARGE,
        "growth_charge_small",
    )
    price_request = PurchaseRequest.from_quote(price_quote)
    monkeypatch.setitem(
        GROWTH_CHARGES,
        "growth_charge_small",
        replace(GROWTH_CHARGES["growth_charge_small"], price=31),
    )
    assert engine.confirm_purchase(price_request).status is PurchaseStatus.STALE_PRICE

    balance_quote = engine.quote_purchase(PurchaseKind.SCENERY, "spring")
    balance_request = PurchaseRequest.from_quote(balance_quote)
    storage.state.currency_balance += 1
    assert engine.confirm_purchase(balance_request).status is PurchaseStatus.STALE_BALANCE

    fertilizer_quote = engine.quote_purchase(
        PurchaseKind.FERTILIZER,
        "basic",
        target_id="p1",
    )
    fertilizer_request = PurchaseRequest.from_quote(fertilizer_quote)
    storage.state.active_plant_id = None
    assert engine.confirm_purchase(fertilizer_request).status is PurchaseStatus.TARGET_INVALID

    storage.state.active_plant_id = "p1"
    bed_quote = engine.quote_purchase(PurchaseKind.BED, "next")
    bed_request = PurchaseRequest.from_quote(bed_quote)
    storage.state.unlocked_slots += 1
    assert engine.confirm_purchase(bed_request).status is PurchaseStatus.STALE_TARGET


@pytest.mark.parametrize(
    ("setup", "kind", "item_id", "target_id", "expected"),
    (
        ("insufficient", PurchaseKind.GROWTH_CHARGE, "growth_charge_small", None, PurchaseStatus.INSUFFICIENT_COINS),
        ("normal", PurchaseKind.GROWTH_CHARGE, "missing", None, PurchaseStatus.ITEM_UNAVAILABLE),
        ("normal", PurchaseKind.WEATHER, "sunny", None, PurchaseStatus.ALREADY_OWNED),
        ("normal", PurchaseKind.FERTILIZER, "basic", "missing", PurchaseStatus.TARGET_INVALID),
    ),
)
def test_purchase_quotes_expose_recoverable_typed_failures(
    setup: str,
    kind: PurchaseKind,
    item_id: str,
    target_id: str | None,
    expected: PurchaseStatus,
) -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 0 if setup == "insufficient" else 5_000

    quote = engine.quote_purchase(kind, item_id, target_id=target_id)

    assert quote.status is expected
    assert not quote.ready
    assert quote.message


def test_fertilizer_replacement_requires_explicit_authorization_and_records_discard() -> None:
    engine, storage = _make_engine()
    storage.state.currency_balance = 500
    engine._now_seconds = lambda: 1_000.0
    assert engine.purchase_fertilizer("p1", "basic")[0]
    engine._now_seconds = lambda: 1_200.0
    quote = engine.quote_purchase(
        PurchaseKind.FERTILIZER,
        "premium",
        target_id="p1",
    )

    assert quote.replacement_required
    assert quote.current_item_name == "Basic Fertilizer"
    assert quote.current_seconds_remaining == 3_400
    assert engine.confirm_purchase(PurchaseRequest.from_quote(quote)).status is (
        PurchaseStatus.REPLACEMENT_REQUIRED
    )

    replaced = engine.confirm_purchase(PurchaseRequest.from_quote(
        quote,
        authorize_replacement=True,
    ))
    assert replaced.success
    assert replaced.applied
    assert replaced.disposition.value == "replaced"
    assert replaced.message == (
        "Magical Fertilizer replaced the Fertilizer on Moss for 4 hours."
    )
    assert storage.state.currency_transactions[-1].reason == (
        "Replaced Fertilizer with Magical Fertilizer on Moss"
    )


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
        "_use_basic_fertilizer",
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


def test_purchase_dialog_converts_unexpected_engine_failure_to_recoverable_error() -> None:
    constructor = _method_source(
        DASHBOARD_PATH,
        "PurchaseConfirmationDialog",
        "__init__",
    )
    commit = _method_source(
        DASHBOARD_PATH,
        "PurchaseConfirmationDialog",
        "_commit",
    )

    assert "try:" in commit
    assert "self.engine.confirm_purchase(self.request)" in commit
    assert "except Exception:" in commit
    assert "PurchaseStatus.PERSISTENCE_FAILURE" in commit
    assert "no Garden Coins were spent" in commit
    assert "self.presentation = purchase_presentation(" in commit
    assert "ignore_status=True" in commit
    assert "if refreshed.ready:" in commit
    assert "self._show_status_banner(" in commit
    assert "balance_only_refresh" not in commit
    assert constructor.index("root.addWidget(self.status)") < constructor.index(
        "root.addWidget(self.content_scroll, 1)"
    )
    assert "content.addWidget(self.status)" not in constructor


def test_environment_receipt_stays_bound_to_the_completed_product() -> None:
    purchase_environment = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_purchase_environment",
        {
            "PurchaseKind": PurchaseKind,
            "WEATHER_CATALOG": WEATHER_CATALOG,
            "SCENERY_CATALOG": SCENERY_CATALOG,
        },
    )
    observed: dict[str, Any] = {}
    outcome = PurchaseOutcome(
        status=PurchaseStatus.SUCCESS,
        item_id="breeze",
        item_name="Soft Breeze",
        category="Weather",
        quantity=1,
        amount_spent=100,
        new_balance=400,
        disposition=PurchaseDisposition.OWNED_NOT_EQUIPPED,
        message="Soft Breeze unlocked. Preview or equip it in Collection.",
        next_actions=("Open Collection", "Continue shopping"),
    )
    nursery = SimpleNamespace(
        _begin_catalog_transaction=lambda: True,
        _execute_purchase=lambda kind, item_id: (
            observed.update(kind=kind, item_id=item_id) or outcome
        ),
        _preview_environment_item=lambda product: observed.setdefault(
            "preview_product", product
        ),
        _show_result=lambda ok, message: observed.update(result=(ok, message)),
        _show_catalog_transaction_exception=lambda *_args, **_kwargs: None,
        _schedule_catalog_transaction_release=lambda: observed.update(released=True),
    )

    purchase_environment(nursery, "weather", "breeze")

    purchased = observed["preview_product"]
    assert purchased is WEATHER_CATALOG["breeze"]
    assert purchased.item_id == "breeze"
    assert purchased.name == "Soft Breeze"
    assert purchased.price == 100
    assert observed["kind"] is PurchaseKind.WEATHER
    assert observed["item_id"] == "breeze"
    assert observed["released"] is True

    class _Status:
        def hide(self) -> None:
            self.visible = False

    status = _Status()
    toast_result: dict[str, Any] = {}
    toast = SimpleNamespace(
        action=object(),
        show_message=lambda message, **kwargs: toast_result.update(
            message=message,
            **kwargs,
        ),
    )
    show_receipt = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_show_purchase_receipt",
        {
            "PurchaseDisposition": PurchaseDisposition,
            "PurchaseKind": PurchaseKind,
            "PurchaseOutcome": PurchaseOutcome,
            "PurchasePresentation": object,
            "_learner_text": lambda text: text,
            "_set_button_variant": lambda *_args: None,
            "BUTTON_VARIANT_PRIMARY": "primary",
            "QTimer": SimpleNamespace(singleShot=lambda *_args: None),
        },
    )
    show_receipt(
        SimpleNamespace(
            _status_generation=0,
            _receipt_outcome=None,
            status=status,
            nursery_toast=toast,
            _follow_receipt_action=lambda: None,
        ),
        outcome,
        SimpleNamespace(facts=(), target_name=""),
    )

    assert status.visible is False
    assert toast_result["message"] == "Soft Breeze unlocked"
    assert toast_result["action_text"] == "Open Collection"
    assert toast_result["duration_ms"] == 6_000
    assert toast_result["dismissible"] is True


def test_catalog_engine_exception_keeps_double_activation_guarded_until_release() -> None:
    purchase_growth_charge = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_purchase_growth_charge",
        {"PurchaseKind": PurchaseKind},
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

    def fail_purchase(_kind: PurchaseKind, _charge_id: str) -> None:
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
    nursery._execute_purchase = fail_purchase

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


def test_nursery_rich_compost_confirms_exact_replacement_and_uses_item_once() -> None:
    confirmations: list[tuple[str, str]] = []
    engine_calls: list[tuple[str, bool]] = []
    scheduled: list[Any] = []
    refreshes: list[str] = []
    results: list[tuple[bool, str]] = []
    inventory = {"fertilizer_basic": 2}

    class _Confirmation:
        @staticmethod
        def confirm(_parent: Any, title: str, message: str) -> bool:
            confirmations.append((title, message))
            return True

    use_fertilizer = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_use_basic_fertilizer",
        {
            "ConfirmationDialog": _Confirmation,
            "collectible_registry": lambda: (
                SimpleNamespace(
                    item_id="growth_items:fertilizer_basic",
                    name="Rich Compost",
                ),
            ),
            "fertilizer_status": lambda *_args, **_kwargs: SimpleNamespace(
                active=True,
                name="Quality Fertilizer",
                duration="1h 00m remaining",
                seconds_remaining=3_600,
            ),
            "_learner_text": str,
            "time": SimpleNamespace(time=lambda: 1_000.0),
        },
    )
    plant = SimpleNamespace(
        plant_id="p1",
        name="Moss",
        fertilizer=SimpleNamespace(tier="quality"),
    )
    basic = SimpleNamespace(
        tier="basic",
        name="Basic Fertilizer",
        growth_per_answer=1,
        duration_seconds=3_600,
    )

    def use_item(plant_id: str, *, replace_active: bool) -> tuple[bool, str]:
        engine_calls.append((plant_id, replace_active))
        if len(engine_calls) == 1:
            inventory["fertilizer_basic"] -= 1
            return True, "Basic Fertilizer applied"
        return False, "Basic Fertilizer could not be used because it was not saved."

    nursery = SimpleNamespace(_catalog_transaction_pending=False)
    nursery._begin_catalog_transaction = lambda: not nursery._catalog_transaction_pending
    nursery._schedule_catalog_transaction_release = lambda: scheduled.append(True)
    nursery._show_catalog_transaction_exception = lambda *_args, **_kwargs: None
    nursery._show_result = lambda ok, message: results.append((ok, message))
    nursery._refresh_parent = lambda: refreshes.append("parent")
    nursery.refresh = lambda: refreshes.append("nursery")
    nursery.storage = SimpleNamespace(
        state=SimpleNamespace(consumables=inventory)
    )
    nursery.engine = SimpleNamespace(
        active_plant=lambda: plant,
        _now_seconds=lambda: 1_000.0,
        _duration_label=lambda _seconds: "1 hour",
        FERTILIZERS={"basic": basic},
        use_fertilizer_item=use_item,
    )

    use_fertilizer(nursery)
    use_fertilizer(nursery)

    assert engine_calls == [("p1", True), ("p1", True)]
    assert inventory == {"fertilizer_basic": 1}
    assert refreshes == ["parent", "nursery"]
    assert scheduled == [True, True]
    assert confirmations[0][0] == "Replace active Fertilizer?"
    assert "Quality Fertilizer" in confirmations[0][1]
    assert "3,600 seconds" in confirmations[0][1]
    assert "cannot be recovered" in confirmations[0][1]
    assert results[0] == (True, "Basic Fertilizer applied")
    assert results[1][0] is False
    assert "Rich Compost was not used" in results[1][1]
    assert "Committed Rich Compost inventory count: 1 (unchanged)" in results[1][1]
    assert "Active Fertilizer on Moss: Quality Fertilizer (unchanged)" in results[1][1]


@pytest.mark.parametrize(
    ("failure_phase", "committed"),
    (("confirmation", False),),
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
            "PurchaseKind": PurchaseKind,
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

    def execute_purchase(_kind: PurchaseKind, _item_id: str) -> None:
        nonlocal engine_calls
        engine_calls += 1
        raise RuntimeError("injected confirmation failure")

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
    nursery._execute_purchase = execute_purchase

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
    properties: dict[str, str] = {}
    nursery = SimpleNamespace(
        _show_result=lambda ok, message: results.append((ok, message)),
        status=SimpleNamespace(
            setProperty=lambda name, value: properties.__setitem__(name, value)
        ),
    )

    try:
        raise RuntimeError("injected transaction failure")
    except RuntimeError:
        show_exception(nursery, "test transaction", committed=committed)

    assert log_calls
    assert results and results[0][0] is False
    assert message_fragment in results[0][1]
    assert "reopen the Nursery" in results[0][1]
    assert properties == (
        {"transactionPresentation": "committed-result-with-refresh-failure"}
        if committed else {}
    )


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
