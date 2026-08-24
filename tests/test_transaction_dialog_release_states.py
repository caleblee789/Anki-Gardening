from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "ankigarden" / "ui" / "dashboard.py"


def _class(name: str) -> ast.ClassDef:
    tree = ast.parse(DASHBOARD.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(class_name: str, method_name: str) -> str:
    source = DASHBOARD.read_text(encoding="utf-8")
    node = next(
        child
        for child in _class(class_name).body
        if isinstance(child, ast.FunctionDef) and child.name == method_name
    )
    return ast.get_source_segment(source, node) or ""


def test_purchase_watchdog_returns_to_the_same_idempotent_request() -> None:
    constructor = _method("PurchaseConfirmationDialog", "__init__")
    submit = _method("PurchaseConfirmationDialog", "_submit")
    commit = _method("PurchaseConfirmationDialog", "_commit")
    timeout = _method("PurchaseConfirmationDialog", "_transaction_timed_out")

    assert "self._commit_watchdog.timeout.connect" in constructor
    assert "self._commit_watchdog.start()" in submit
    assert "self.engine.confirm_purchase(self.request)" in commit
    assert "PurchaseRequest.from_quote" not in timeout
    assert 'self.setProperty("transactionTimedOut", True)' in timeout


def test_growth_charge_attempt_reuses_request_until_quote_changes() -> None:
    refresh = _method("GrowthChargeConfirmationDialog", "_refresh_quote")
    commit = _method("GrowthChargeConfirmationDialog", "_commit")
    timeout = _method("GrowthChargeConfirmationDialog", "_transaction_timed_out")

    assert "self.request.fingerprint() != request.fingerprint()" in refresh
    assert "request = self.request" in commit
    assert "GrowthChargeRequest.from_quote" not in commit
    assert "GrowthChargeRequest.from_quote" not in timeout
    assert 'self.setProperty("transactionTimedOut", True)' in timeout


def test_growth_charge_empty_state_owns_its_primary_action_in_the_footer() -> None:
    constructor = _method("GrowthChargeConfirmationDialog", "__init__")
    populate = _method("GrowthChargeConfirmationDialog", "_populate_inventory")

    empty_state_call = constructor.split("self.empty_inventory = EmptyState(", 1)[1].split(
        ")\n", 1
    )[0]
    assert "action=self.nursery_action" not in empty_state_call
    assert "self.footer_layout.addWidget(self.nursery_action)" in constructor
    assert "self.nursery_action.setVisible(not has_inventory)" in populate


def test_growth_charge_stale_state_keeps_the_refreshed_result_visible() -> None:
    failure = _method("GrowthChargeConfirmationDialog", "_show_failed_outcome")

    assert "GrowthChargeStatus.STALE_INVENTORY" in failure
    assert "GrowthChargeStatus.STALE_TARGET" in failure
    assert "self.facts_card.setVisible(self.quote is not None)" in failure
    assert "self.outcome_heading.setVisible(self.quote is not None)" in failure


def test_growth_charge_invalid_and_success_states_expose_concrete_semantics() -> None:
    refresh = _method("GrowthChargeConfirmationDialog", "_refresh_quote")
    failure = _method("GrowthChargeConfirmationDialog", "_show_failed_outcome")
    receipt = _method("GrowthChargeConfirmationDialog", "_show_receipt")

    assert "GrowthChargeTargetState(quote.target_state)" in refresh
    assert "target_state.value" in failure
    assert 'f"{stage_name} reward"' not in receipt
    assert "self.target_stage.hide()" in receipt
    assert "self.cancel_action.hide()" in receipt
