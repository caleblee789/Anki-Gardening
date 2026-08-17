"""Shared, renderer-neutral Garden Coin purchase contracts."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class PurchaseKind(str, Enum):
    SPECIES = "species"
    GROWTH_CHARGE = "growth_charge"
    FERTILIZER = "fertilizer"
    WEATHER = "weather"
    SCENERY = "scenery"
    BED = "bed"


class PurchaseStatus(str, Enum):
    READY = "ready"
    SUCCESS = "success"
    INSUFFICIENT_COINS = "insufficient_coins"
    PERSISTENCE_FAILURE = "persistence_failure"
    ITEM_UNAVAILABLE = "item_unavailable"
    ALREADY_OWNED = "already_owned"
    TARGET_INVALID = "target_invalid"
    STALE_PRICE = "stale_price"
    STALE_BALANCE = "stale_balance"
    STALE_TARGET = "stale_target"
    REPLACEMENT_REQUIRED = "replacement_required"
    REQUEST_ID_CONFLICT = "request_id_conflict"


class PurchaseDisposition(str, Enum):
    COLLECTION = "collection"
    INVENTORY = "inventory"
    APPLIED = "applied"
    EXTENDED = "extended"
    REPLACED = "replaced"
    UNLOCKED = "unlocked"
    OWNED_NOT_EQUIPPED = "owned_not_equipped"


@dataclass(frozen=True)
class EffectDescriptor:
    """Exact mechanics shared by commerce and Collection renderers."""

    function: str
    buff: str
    activation_condition: str
    duration: str
    stacking: str
    replacement: str
    unlock_requirement: str

    def detail_rows(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Function", self.function),
            ("Effect", self.buff),
            ("Activation", self.activation_condition),
            ("Duration", self.duration),
            ("Stacking", self.stacking),
            ("Replacement", self.replacement),
            ("Unlock", self.unlock_requirement),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "function": self.function,
            "buff": self.buff,
            "activation_condition": self.activation_condition,
            "duration": self.duration,
            "stacking": self.stacking,
            "replacement": self.replacement,
            "unlock_requirement": self.unlock_requirement,
        }

    @staticmethod
    def from_dict(value: Any) -> "EffectDescriptor | None":
        if not isinstance(value, dict):
            return None
        keys = (
            "function",
            "buff",
            "activation_condition",
            "duration",
            "stacking",
            "replacement",
            "unlock_requirement",
        )
        if any(not isinstance(value.get(key), str) for key in keys):
            return None
        return EffectDescriptor(**{key: str(value[key]) for key in keys})


@dataclass(frozen=True)
class PurchaseQuote:
    kind: PurchaseKind
    item_id: str
    item_name: str
    category: str
    artwork_category: str
    artwork_key: str
    quantity: int
    unit_price: int
    balance_before: int
    balance_after: int
    target_id: str | None
    target_name: str
    disposition: PurchaseDisposition
    descriptor: EffectDescriptor
    quote_token: str
    status: PurchaseStatus = PurchaseStatus.READY
    message: str = ""
    replacement_required: bool = False
    current_item_name: str = ""
    current_effect: str = ""
    current_duration: str = ""
    current_seconds_remaining: int = 0

    @property
    def ready(self) -> bool:
        return self.status is PurchaseStatus.READY

    @property
    def total_price(self) -> int:
        return max(0, int(self.unit_price)) * max(1, int(self.quantity))


@dataclass(frozen=True)
class PurchaseRequest:
    request_id: str
    kind: PurchaseKind
    item_id: str
    quantity: int
    quote_token: str
    expected_price: int
    expected_balance: int
    target_id: str | None = None
    authorize_replacement: bool = False

    @staticmethod
    def from_quote(
        quote: PurchaseQuote,
        *,
        request_id: str | None = None,
        authorize_replacement: bool = False,
    ) -> "PurchaseRequest":
        return PurchaseRequest(
            request_id=str(request_id or uuid.uuid4()),
            kind=quote.kind,
            item_id=quote.item_id,
            quantity=quote.quantity,
            quote_token=quote.quote_token,
            expected_price=quote.total_price,
            expected_balance=quote.balance_before,
            target_id=quote.target_id,
            authorize_replacement=bool(authorize_replacement),
        )

    def fingerprint(self) -> str:
        payload = {
            "kind": self.kind.value,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "quote_token": self.quote_token,
            "expected_price": self.expected_price,
            "expected_balance": self.expected_balance,
            "target_id": self.target_id,
            "authorize_replacement": self.authorize_replacement,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PurchaseOutcome:
    status: PurchaseStatus
    item_id: str
    item_name: str
    category: str
    quantity: int
    amount_spent: int
    new_balance: int
    disposition: PurchaseDisposition
    message: str
    next_actions: tuple[str, ...] = ()
    result_id: str = ""
    applied: bool = False
    equipped: bool = False

    @property
    def success(self) -> bool:
        return self.status is PurchaseStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "category": self.category,
            "quantity": self.quantity,
            "amount_spent": self.amount_spent,
            "new_balance": self.new_balance,
            "disposition": self.disposition.value,
            "message": self.message,
            "next_actions": list(self.next_actions),
            "result_id": self.result_id,
            "applied": self.applied,
            "equipped": self.equipped,
        }

    @staticmethod
    def from_dict(value: Any) -> "PurchaseOutcome | None":
        if not isinstance(value, dict):
            return None
        try:
            status = PurchaseStatus(str(value.get("status", "")))
            disposition = PurchaseDisposition(str(value.get("disposition", "")))
        except ValueError:
            return None
        string_keys = ("item_id", "item_name", "category", "message")
        if any(not isinstance(value.get(key), str) for key in string_keys):
            return None
        int_keys = ("quantity", "amount_spent", "new_balance")
        if any(
            not isinstance(value.get(key), int) or isinstance(value.get(key), bool)
            for key in int_keys
        ):
            return None
        if (
            int(value["quantity"]) != 1
            or int(value["amount_spent"]) < 0
            or int(value["new_balance"]) < 0
        ):
            return None
        raw_actions = value.get("next_actions", [])
        if not isinstance(raw_actions, list) or any(
            not isinstance(action, str) for action in raw_actions
        ):
            return None
        applied = value.get("applied", False)
        equipped = value.get("equipped", False)
        result_id = value.get("result_id", "")
        if not isinstance(result_id, str):
            return None
        if not isinstance(applied, bool) or not isinstance(equipped, bool):
            return None
        return PurchaseOutcome(
            status=status,
            item_id=str(value["item_id"]),
            item_name=str(value["item_name"]),
            category=str(value["category"]),
            quantity=int(value["quantity"]),
            amount_spent=int(value["amount_spent"]),
            new_balance=int(value["new_balance"]),
            disposition=disposition,
            message=str(value["message"]),
            next_actions=tuple(raw_actions),
            result_id=result_id,
            applied=applied,
            equipped=equipped,
        )


@dataclass(frozen=True)
class CompletedPurchaseRequest:
    request_id: str
    request_fingerprint: str
    outcome: PurchaseOutcome
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "outcome": self.outcome.to_dict(),
            "occurred_at": self.occurred_at,
        }

    @staticmethod
    def from_dict(value: Any) -> "CompletedPurchaseRequest | None":
        if not isinstance(value, dict):
            return None
        request_id = value.get("request_id")
        fingerprint = value.get("request_fingerprint")
        occurred_at = value.get("occurred_at")
        outcome = PurchaseOutcome.from_dict(value.get("outcome"))
        valid_request_id = False
        try:
            valid_request_id = (
                isinstance(request_id, str)
                and str(uuid.UUID(request_id)) == request_id
            )
        except (ValueError, TypeError, AttributeError):
            pass
        valid_occurred_at = False
        if isinstance(occurred_at, str):
            try:
                parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                valid_occurred_at = parsed.tzinfo is not None
            except ValueError:
                pass
        if (
            not isinstance(request_id, str)
            or not valid_request_id
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or fingerprint != fingerprint.lower()
            or any(character not in "0123456789abcdef" for character in fingerprint)
            or not isinstance(occurred_at, str)
            or not valid_occurred_at
            or outcome is None
            or not outcome.success
        ):
            return None
        return CompletedPurchaseRequest(
            request_id=request_id,
            request_fingerprint=fingerprint,
            outcome=outcome,
            occurred_at=occurred_at,
        )
