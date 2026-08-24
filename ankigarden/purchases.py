"""Shared, renderer-neutral Garden Coin purchase contracts."""

from __future__ import annotations

import hashlib
import json
import re
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


class PurchaseAction(str, Enum):
    """Learner-facing consequence of confirming a purchase."""

    PURCHASE = "purchase"
    PURCHASE_APPLY = "purchase_apply"
    EXTEND = "extend"
    PURCHASE_REPLACE = "purchase_replace"
    UNLOCK = "unlock"


class PurchasePreviewStyle(str, Enum):
    SQUARE = "square"
    LANDSCAPE = "landscape"
    GARDEN_BED = "garden_bed"


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

    def mechanics_rows(self) -> tuple[tuple[str, str], ...]:
        """Return the non-redundant mechanics shown on catalog cards."""

        return self.detail_rows()[1:]

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
    duration_seconds: int = 0
    resulting_seconds_remaining: int = 0
    inventory_before: int = 0
    inventory_after: int = 0
    current_equipped_name: str = ""

    @property
    def ready(self) -> bool:
        return self.status is PurchaseStatus.READY

    @property
    def total_price(self) -> int:
        return max(0, int(self.unit_price)) * max(1, int(self.quantity))


@dataclass(frozen=True)
class PurchaseFact:
    """One decision-relevant fact; an empty label renders as plain outcome copy."""

    key: str
    label: str
    value: str
    emphasized: bool = False


@dataclass(frozen=True)
class PurchasePresentation:
    """Contextual customer-facing projection of one authoritative quote."""

    action: PurchaseAction
    title: str
    item_name: str
    category: str
    outcome: str
    facts: tuple[PurchaseFact, ...]
    badges: tuple[str, ...]
    more_details: tuple[PurchaseFact, ...]
    preview_style: PurchasePreviewStyle
    target_name: str
    price: int
    balance_before: int
    balance_after: int | None
    show_preview: bool
    show_cost: bool
    show_item_name: bool
    show_category: bool
    primary_label: str
    primary_accessible_name: str
    processing_label: str
    secondary_label: str
    update_label: str = ""
    primary_route: str = ""
    terminal: bool = False
    retry: bool = False
    activity_label: str = ""
    success_message: str = ""
    next_actions: tuple[str, ...] = ()


def compact_duration(seconds: int) -> str:
    """Return stable, decision-scale duration copy without seconds jitter."""

    total_minutes = max(0, int(seconds) // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "Under 1m"


def _without_period(value: str) -> str:
    return str(value or "").strip().rstrip(".")


def _compact_effect(value: str) -> str:
    effect = _without_period(value)
    replacements = (
        (" per eligible Anki card answer", " per card"),
        (" per Anki card answer", " per card"),
        (" when used", ""),
    )
    for old, new in replacements:
        effect = effect.replace(old, new)
    return effect


def _bed_unlock_counts(quote: PurchaseQuote) -> tuple[int, int]:
    """Derive display-only sequential bed counts from the quoted bed identity."""

    resulting = 1
    for identity in (quote.item_id, quote.item_name):
        try:
            resulting = max(
                1,
                int(str(identity).replace("_", " ").rsplit(" ", 1)[-1]),
            )
            break
        except (TypeError, ValueError):
            continue
    return max(0, resulting - 1), resulting


def _priced_action(
    action: PurchaseAction,
    price: int,
) -> tuple[str, str, str]:
    short = {
        PurchaseAction.PURCHASE: "Buy",
        PurchaseAction.PURCHASE_APPLY: "Buy and apply",
        PurchaseAction.EXTEND: "Extend",
        PurchaseAction.PURCHASE_REPLACE: "Buy and replace",
        PurchaseAction.UNLOCK: "Unlock",
    }[action]
    processing = {
        PurchaseAction.PURCHASE: "Buying…",
        PurchaseAction.PURCHASE_APPLY: "Applying…",
        PurchaseAction.EXTEND: "Extending…",
        PurchaseAction.PURCHASE_REPLACE: "Applying…",
        PurchaseAction.UNLOCK: "Unlocking…",
    }[action]
    return (
        short,
        f"{short} for {max(0, int(price)):,} Garden Coins",
        processing,
    )


def _stale_price_copy(item_name: str, message: str, current_price: int) -> str:
    """Compress the engine's exact stale-price result into one reconfirmation."""

    match = re.search(
        r"changed from\s+([\d,]+)\s+to\s+([\d,]+)\s+Garden Coins",
        str(message),
        flags=re.IGNORECASE,
    )
    if match is not None:
        old_price, new_price = match.groups()
        return f"The price changed from {old_price} to {new_price} Garden Coins."
    return f"{item_name} now costs {max(0, int(current_price)):,} Garden Coins."


def _sentence_duration(seconds: int, fallback: str) -> str:
    """Keep financially relevant lost time exact at sub-minute boundaries."""

    remaining = max(0, int(seconds))
    if remaining < 60:
        unit = "second" if remaining == 1 else "seconds"
        return f"{remaining} {unit}"
    return (
        _without_period(fallback)
        .removesuffix(" remaining")
        .removesuffix(" left")
        or compact_duration(remaining)
    )


def purchase_presentation(
    quote: PurchaseQuote,
    *,
    status: PurchaseStatus | None = None,
    message: str = "",
    ignore_status: bool = False,
) -> PurchasePresentation:
    """Project one quote into applicable-only purchase copy and actions."""

    effective_status = (
        PurchaseStatus.READY
        if ignore_status
        else status if status is not None else quote.status
    )
    item_name = str(quote.item_name or "Garden item")
    category = str(quote.category or "Garden item")
    target_name = str(quote.target_name or "")
    facts: list[PurchaseFact] = []
    badges: list[str] = []
    more_details: list[PurchaseFact] = []
    preview_style = PurchasePreviewStyle.SQUARE
    action = PurchaseAction.PURCHASE
    outcome = ""
    # Activity labels are persisted internal ledger reasons. Keep their stable
    # wording even though visible buttons use the shorter "Buy" verb.
    activity_label = f"Purchased {item_name}"
    success_message = f"{item_name} added."
    next_actions = ("Keep browsing",)
    update_label = ""

    if quote.kind is PurchaseKind.SPECIES:
        species_name = item_name[:-5] if item_name.lower().endswith(" seed") else item_name
        title = f"Buy {item_name}?"
        outcome = f"Adds {species_name} to your collection."
        success_message = f"{species_name} added."
        next_actions = ("Place in Garden", "View Collection")
    elif quote.kind is PurchaseKind.GROWTH_CHARGE:
        title = f"Buy {item_name}?"
        outcome = f"Adds one {item_name} to your inventory."
        success_message = f"{item_name} added."
        next_actions = ("Use charge", "Keep browsing")
    elif quote.kind is PurchaseKind.FERTILIZER:
        fertilizer_target = target_name or "your nurtured plant"
        if quote.replacement_required:
            action = PurchaseAction.PURCHASE_REPLACE
            current_name = str(quote.current_item_name or "Fertilizer")
            title = f"Replace {current_name}?"
            lost_time = _sentence_duration(
                quote.current_seconds_remaining,
                quote.current_duration,
            )
            outcome = (
                f"{item_name} starts immediately. You will lose {lost_time} of "
                f"{current_name}."
            )
            activity_label = f"Replaced Fertilizer with {item_name} on {fertilizer_target}"
            success_message = f"{item_name} applied."
        elif quote.disposition is PurchaseDisposition.EXTENDED:
            action = PurchaseAction.EXTEND
            title = f"Extend {item_name}?"
            outcome = (
                f"Adds {_without_period(quote.descriptor.duration)} to "
                f"{fertilizer_target}."
            )
            activity_label = f"Extended {item_name} on {fertilizer_target}"
            success_message = f"{item_name} extended."
        else:
            action = PurchaseAction.PURCHASE_APPLY
            title = f"Buy and apply {item_name}?"
            outcome = (
                f"{fertilizer_target} · {_compact_effect(quote.descriptor.buff)} "
                f"for {_without_period(quote.descriptor.duration)}"
            )
            activity_label = f"Applied {item_name} to {fertilizer_target}"
            success_message = f"{item_name} applied."
        next_actions = ("View plant", "Keep browsing")
    elif quote.kind in {PurchaseKind.WEATHER, PurchaseKind.SCENERY}:
        title = f"Buy {item_name}?"
        outcome = "Adds it to Weather and Scenery."
        preview_style = PurchasePreviewStyle.LANDSCAPE
        success_message = f"{item_name} added to your collection."
        next_actions = ("View Collection", "Keep browsing")
    else:
        action = PurchaseAction.UNLOCK
        bed_name = item_name.replace("Garden bed", "Bed").replace("Garden Bed", "Bed")
        title = f"Unlock {bed_name}?"
        outcome = "Adds one permanent planting space."
        preview_style = PurchasePreviewStyle.GARDEN_BED
        activity_label = f"Unlocked {item_name}"
        success_message = f"{bed_name} unlocked."
        next_actions = ("View Garden", "Keep browsing")

    primary_label, primary_accessible, processing_label = _priced_action(
        action, quote.total_price
    )
    display_title = title
    display_outcome = outcome
    visible_facts = tuple(facts)
    show_preview = True
    show_cost = True
    balance_after: int | None = quote.balance_after
    secondary_label = "Keep current" if quote.replacement_required else "Cancel"
    primary_route = ""
    terminal = False
    retry = False
    show_item_name = False
    show_category = False

    if quote.replacement_required:
        current_short = str(quote.current_item_name or "Fertilizer").removesuffix(
            " Fertilizer"
        )
        new_short = item_name.removesuffix(" Fertilizer")
        secondary_label = f"Keep {current_short}"
        primary_label = f"Buy {new_short}"
        primary_accessible = f"Buy {item_name} for {quote.total_price:,} Garden Coins"

    if effective_status is PurchaseStatus.PERSISTENCE_FAILURE:
        display_title = "Purchase failed"
        failed_result = (
            f"{item_name} was not applied."
            if quote.kind is PurchaseKind.FERTILIZER
            else f"{item_name} was not unlocked."
            if quote.kind is PurchaseKind.BED
            else f"{item_name} was not added."
        )
        display_outcome = f"{failed_result}\nNo Garden Coins were spent."
        badges = []
        more_details = []
        visible_facts = ()
        balance_after = quote.balance_before
        show_cost = False
        show_preview = False
        secondary_label = "Cancel"
        primary_label = "Try again"
        primary_accessible = f"Try purchasing {item_name} again"
        processing_label = _priced_action(action, quote.total_price)[2]
        retry = True
    elif effective_status is PurchaseStatus.INSUFFICIENT_COINS:
        display_title = "Not enough Garden Coins"
        display_outcome = (
            f"{item_name} costs {quote.total_price:,} Garden Coins.\n"
            f"Current balance: {max(0, quote.balance_before):,}"
        )
        visible_facts = ()
        badges = []
        balance_after = None
        show_cost = False
        show_preview = False
        secondary_label = "Close"
        primary_label = "Ways to earn"
        primary_accessible = primary_label
        primary_route = "ways_to_earn"
        terminal = True
    elif effective_status is PurchaseStatus.ITEM_UNAVAILABLE:
        unavailable_name = (
            "Growth Charge"
            if quote.kind is PurchaseKind.GROWTH_CHARGE
            else item_name if item_name.lower() != "unavailable item" else category
        )
        display_title = f"{unavailable_name} unavailable"
        display_outcome = "This item is unavailable right now."
        visible_facts = ()
        badges = []
        more_details = []
        show_cost = False
        show_preview = False
        balance_after = None
        secondary_label = "Close"
        primary_label = "Back to Nursery"
        primary_accessible = primary_label
        primary_route = "nursery"
        terminal = True
    elif effective_status is PurchaseStatus.ALREADY_OWNED:
        display_title = "Already in your collection"
        display_outcome = ""
        visible_facts = ()
        badges = []
        show_cost = False
        show_preview = True
        balance_after = None
        secondary_label = ""
        primary_route = "collection"
        primary_label = "View in Collection"
        primary_accessible = primary_label
        show_item_name = True
        terminal = True
    elif effective_status in {
        PurchaseStatus.TARGET_INVALID,
        PurchaseStatus.REQUEST_ID_CONFLICT,
        PurchaseStatus.REPLACEMENT_REQUIRED,
    }:
        display_title = {
            PurchaseStatus.TARGET_INVALID: "Choose another plant",
            PurchaseStatus.REQUEST_ID_CONFLICT: "Purchase failed",
            PurchaseStatus.REPLACEMENT_REQUIRED: f"Replace {quote.current_item_name or 'Fertilizer'}?",
        }[effective_status]
        invalid_message = (
            f"This plant cannot use {item_name}."
            if effective_status is PurchaseStatus.TARGET_INVALID
            else "No Garden Coins were spent."
            if effective_status is PurchaseStatus.REQUEST_ID_CONFLICT
            else outcome
        )
        display_outcome = invalid_message
        visible_facts = ()
        badges = []
        show_cost = False
        show_preview = False
        balance_after = None
        secondary_label = "Cancel"
        primary_label = (
            "Choose plant"
            if effective_status is PurchaseStatus.TARGET_INVALID
            else "Try again"
        )
        primary_accessible = primary_label
        primary_route = (
            "garden" if effective_status is PurchaseStatus.TARGET_INVALID else ""
        )
        terminal = effective_status is PurchaseStatus.TARGET_INVALID
        retry = effective_status is PurchaseStatus.REQUEST_ID_CONFLICT
    elif effective_status in {
        PurchaseStatus.STALE_PRICE,
        PurchaseStatus.STALE_BALANCE,
        PurchaseStatus.STALE_TARGET,
    }:
        display_title = {
            PurchaseStatus.STALE_PRICE: "Price changed",
            PurchaseStatus.STALE_BALANCE: title,
            PurchaseStatus.STALE_TARGET: "Item updated",
        }[effective_status]
        stale_outcome = str(
            message
            or quote.message
            or "Review the updated purchase terms before continuing."
        )
        display_outcome = (
            _stale_price_copy(item_name, stale_outcome, quote.total_price)
            if effective_status is PurchaseStatus.STALE_PRICE
            else outcome
            if effective_status is PurchaseStatus.STALE_BALANCE
            else "Review the current item."
        )
        update_label = (
            "Balance updated"
            if effective_status is PurchaseStatus.STALE_BALANCE
            else ""
        )
        show_item_name = effective_status is PurchaseStatus.STALE_PRICE
        badges = []
        primary_label = "Buy" if action is PurchaseAction.PURCHASE else primary_label
        primary_accessible = (
            f"{primary_label} for {max(0, quote.total_price):,} Garden Coins"
        )

    if effective_status not in {
        PurchaseStatus.READY,
        PurchaseStatus.SUCCESS,
    }:
        activity_label = ""
        success_message = ""
        next_actions = ()

    return PurchasePresentation(
        action=action,
        title=display_title,
        item_name=item_name,
        category=category,
        outcome=display_outcome,
        facts=visible_facts,
        badges=tuple(badges),
        more_details=tuple(more_details),
        preview_style=preview_style,
        target_name="",
        price=quote.total_price,
        balance_before=quote.balance_before,
        balance_after=balance_after,
        show_preview=show_preview,
        show_cost=show_cost,
        show_item_name=show_item_name,
        show_category=show_category,
        primary_label=primary_label,
        primary_accessible_name=primary_accessible,
        processing_label=processing_label,
        secondary_label=secondary_label,
        update_label=update_label,
        primary_route=primary_route,
        terminal=terminal,
        retry=retry,
        activity_label=activity_label,
        success_message=success_message,
        next_actions=next_actions,
    )


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
