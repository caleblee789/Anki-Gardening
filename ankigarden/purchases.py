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

from .balance_catalog import (
    BED_UNLOCK_BY_NUMBER,
    CONSUMABLE_BY_ID,
    canonical_consumable_id,
)


class PurchaseKind(str, Enum):
    SPECIES = "species"
    GROWTH_CHARGE = "growth_charge"
    FERTILIZER = "fertilizer"
    GARDEN_FEATURE = "garden_feature"
    SCENERY = "scenery"
    COSMETIC = "cosmetic"
    BED = "bed"

    @classmethod
    def _missing_(cls, value: object) -> "PurchaseKind | None":
        # Supported migration window for persisted schema-22 purchase records.
        if str(value) == "weather":
            return cls.GARDEN_FEATURE
        return None


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
    QUEUED = "queued"
    REPLACED = "replaced"
    UNLOCKED = "unlocked"
    OWNED_NOT_EQUIPPED = "owned_not_equipped"


class PurchaseAction(str, Enum):
    """Learner-facing consequence of confirming a purchase."""

    PURCHASE = "purchase"
    PURCHASE_APPLY = "purchase_apply"
    PURCHASE_QUEUE = "purchase_queue"
    EXTEND = "extend"
    PURCHASE_REPLACE = "purchase_replace"
    UNLOCK = "unlock"


class PurchaseAppearanceState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class FertilizerStoredItemDisposition(str, Enum):
    """Explicit inventory action; renderers never infer it from schedules."""

    ADD_ONE_HOUR = "add_one_hour"
    ADD_TWO_HOURS = "add_two_hours"
    QUEUE = "queue"
    USE = "use"

    @property
    def action_text(self) -> str:
        return {
            FertilizerStoredItemDisposition.ADD_ONE_HOUR: "Add 1 hour",
            FertilizerStoredItemDisposition.ADD_TWO_HOURS: "Add 2 hours",
            FertilizerStoredItemDisposition.QUEUE: "Queue",
            FertilizerStoredItemDisposition.USE: "Use",
        }[self]


@dataclass(frozen=True)
class FertilizerStoredItemProjection:
    disposition: FertilizerStoredItemDisposition
    action_text: str
    duration_delta_seconds: int
    card_queue_delta: int
    expires_at_ms: int | None = None


def fertilizer_stored_item_projection(
    disposition: FertilizerStoredItemDisposition | str,
    *,
    duration_delta_seconds: int = 0,
    card_queue_delta: int = 0,
    expires_at_ms: int | None = None,
) -> FertilizerStoredItemProjection:
    """Project an authoritative fertilizer result without schedule arithmetic."""

    resolved = FertilizerStoredItemDisposition(disposition)
    duration_delta = int(duration_delta_seconds)
    queue_delta = int(card_queue_delta)
    if duration_delta < 0 or queue_delta < 0:
        raise ValueError("Fertilizer result deltas cannot be negative")
    if expires_at_ms is not None and (
        isinstance(expires_at_ms, bool)
        or not isinstance(expires_at_ms, int)
        or expires_at_ms <= 0
    ):
        raise ValueError("expires_at_ms must be a positive epoch millisecond")
    required_duration = {
        FertilizerStoredItemDisposition.ADD_ONE_HOUR: 3_600,
        FertilizerStoredItemDisposition.ADD_TWO_HOURS: 7_200,
    }.get(resolved)
    if required_duration is not None and duration_delta != required_duration:
        raise ValueError(
            f"{resolved.value} requires duration_delta_seconds={required_duration}"
        )
    if required_duration is not None and expires_at_ms is None:
        raise ValueError(
            f"{resolved.value} requires an absolute expires_at_ms"
        )
    if required_duration is not None and queue_delta:
        raise ValueError(f"{resolved.value} cannot add card-counted queue value")
    if resolved in {
        FertilizerStoredItemDisposition.QUEUE,
        FertilizerStoredItemDisposition.USE,
    } and duration_delta:
        raise ValueError(f"{resolved.value} cannot add timed duration")
    if resolved in {
        FertilizerStoredItemDisposition.QUEUE,
        FertilizerStoredItemDisposition.USE,
    } and expires_at_ms is not None:
        raise ValueError(
            f"{resolved.value} is card-counted and cannot have expires_at_ms"
        )
    return FertilizerStoredItemProjection(
        resolved,
        resolved.action_text,
        duration_delta,
        queue_delta,
        expires_at_ms,
    )


def fertilizer_action_label(
    disposition: PurchaseDisposition,
    *,
    owned: bool,
) -> str:
    """Return the frozen card-counted Fertilizer action vocabulary."""

    try:
        resolved = PurchaseDisposition(disposition)
    except (TypeError, ValueError):
        resolved = PurchaseDisposition.APPLIED
    if resolved in {PurchaseDisposition.EXTENDED, PurchaseDisposition.QUEUED}:
        return "Use next" if owned else "Buy and use next"
    return "Use"


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
    current_cards_remaining: int = 0
    card_count: int = 0
    resulting_cards_remaining: int = 0
    queued_doses: int = 0
    fertilizer_stored_item_disposition: FertilizerStoredItemDisposition | None = None
    duration_delta_seconds: int = 0
    card_queue_delta: int = 0
    fertilizer_expires_at_ms: int | None = None

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


@dataclass(frozen=True)
class PurchaseTransactionRow:
    key: str
    label: str
    amount_coins: int


@dataclass(frozen=True)
class PurchaseProjection:
    """Small, stable purchase API for renderer-owned surfaces."""

    item_id: str
    action_text: str
    price_coins: int | None
    wallet_balance_coins: int
    transaction_rows: tuple[PurchaseTransactionRow, ...]
    can_commit: bool
    blocking_reason: str
    appearance_state: PurchaseAppearanceState
    fertilizer_stored_item: FertilizerStoredItemProjection | None = None


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


def _coin_amount(value: int, *, formal: bool = False) -> str:
    """Format a price or balance delta with locale-style grouping and grammar."""

    del formal
    amount = max(0, int(value))
    unit = "Garden Coin" if amount == 1 else "Garden Coins"
    return f"{amount:,} {unit}"


def _compact_effect(value: str) -> str:
    effect = _without_period(value)
    replacements = (
        (" per eligible Anki card answer", " per card"),
        (" per Anki card answer", " per card"),
        (" per card answer", " per card"),
        (" per answer", " per card"),
        (" when used", ""),
    )
    for old, new in replacements:
        effect = effect.replace(old, new)
    return effect


def _eligible_answer_effect(value: str) -> str:
    """Normalize a Fertilizer buff to the canonical learner-facing unit."""

    effect = _without_period(value)
    effect = re.sub(
        r"\s+per\s+(?:eligible\s+)?(?:Anki\s+)?(?:card\s+)?answer$",
        "",
        effect,
        flags=re.IGNORECASE,
    )
    effect = re.sub(r"\s+per\s+card$", "", effect, flags=re.IGNORECASE)
    return f"{effect or 'Growth'} per eligible card"


def _effect_duration(value: str) -> str:
    """Return a duration that reads naturally after adds or queued."""

    return _without_period(value).removeprefix("Lasts ")


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
    _price: int,
) -> tuple[str, str, str]:
    short = {
        PurchaseAction.PURCHASE: "Buy",
        PurchaseAction.PURCHASE_APPLY: "Buy and apply",
        PurchaseAction.PURCHASE_QUEUE: "Buy and use next",
        PurchaseAction.EXTEND: "Extend",
        PurchaseAction.PURCHASE_REPLACE: "Buy and replace",
        PurchaseAction.UNLOCK: "Unlock",
    }[action]
    processing = {
        PurchaseAction.PURCHASE: "Buying…",
        PurchaseAction.PURCHASE_APPLY: "Applying…",
        PurchaseAction.PURCHASE_QUEUE: "Queueing…",
        PurchaseAction.EXTEND: "Extending…",
        PurchaseAction.PURCHASE_REPLACE: "Applying…",
        PurchaseAction.UNLOCK: "Unlocking…",
    }[action]
    return short, short, processing


def _canonical_action_text(quote: PurchaseQuote, action: PurchaseAction) -> str:
    if quote.kind is PurchaseKind.GROWTH_CHARGE:
        item = CONSUMABLE_BY_ID.get(canonical_consumable_id(quote.item_id))
        return str(getattr(item, "purchase_action_text", "") or "Buy charge")
    if quote.kind is PurchaseKind.FERTILIZER and action is PurchaseAction.PURCHASE_QUEUE:
        item = CONSUMABLE_BY_ID.get(canonical_consumable_id(quote.item_id))
        return str(getattr(item, "queued_purchase_action_text", "") or "Buy and use next")
    if quote.kind is PurchaseKind.FERTILIZER:
        if quote.disposition is PurchaseDisposition.INVENTORY:
            return "Buy fertilizer"
        return "Buy and use next" if quote.disposition is PurchaseDisposition.EXTENDED else "Buy and use"
    if quote.kind is PurchaseKind.BED:
        _before, bed_number = _bed_unlock_counts(quote)
        definition = BED_UNLOCK_BY_NUMBER.get(bed_number)
        return str(
            getattr(definition, "purchase_action_text", "")
            or f"Unlock Bed {bed_number}"
        )
    return _priced_action(action, quote.total_price)[0]


def _stale_price_copy(item_name: str, message: str, current_price: int) -> str:
    """Compress the engine's exact stale-price result into one reconfirmation."""

    match = re.search(
        r"changed from\s+([\d,]+)\s+to\s+([\d,]+)\s+Garden Coins",
        str(message),
        flags=re.IGNORECASE,
    )
    if match is not None:
        old_price, new_price = match.groups()
        old_amount = int(old_price.replace(",", ""))
        new_amount = int(new_price.replace(",", ""))
        return (
            f"The price changed from {_coin_amount(old_amount, formal=True)} "
            f"to {_coin_amount(new_amount, formal=True)}."
        )
    return f"{item_name} now costs {_coin_amount(current_price, formal=True)}."


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
    show_item_name = False

    if quote.kind is PurchaseKind.SPECIES:
        species_name = item_name[:-5] if item_name.lower().endswith(" seed") else item_name
        title = f"Buy {item_name}?"
        outcome = f"Adds {item_name} to your collection as a new plant."
        success_message = f"{item_name} added."
        next_actions = ("Place in garden", "View in collection")
    elif quote.kind is PurchaseKind.GROWTH_CHARGE:
        title = f"Buy {item_name}?"
        growth_effect = re.sub(
            r"\s+when used$",
            "",
            _without_period(quote.descriptor.buff).lstrip("+"),
            flags=re.IGNORECASE,
        )
        outcome = f"Adds {growth_effect or 'Growth'} to one plant when used."
        # The title already carries the item identity. Repeating it beside the
        # artwork creates a visually duplicated heading in the compact dialog.
        show_item_name = False
        success_message = f"{item_name} added."
        next_actions = ("Use growth charge", "Keep browsing")
        facts.append(PurchaseFact(
            "inventory",
            "You own",
            f"{max(0, int(quote.inventory_before)):,} → "
            f"{max(0, int(quote.inventory_after)):,}",
        ))
    elif quote.kind is PurchaseKind.FERTILIZER:
        fertilizer_target = target_name or "your nurtured plant"
        if quote.disposition is PurchaseDisposition.INVENTORY:
            title = f"Buy {item_name}?"
            outcome = f"Adds one {item_name} to your supplies."
            activity_label = f"Purchased {item_name} for inventory"
            success_message = f"{item_name} added to inventory."
            next_actions = ("Keep browsing",)
        elif quote.disposition is PurchaseDisposition.QUEUED:
            action = PurchaseAction.PURCHASE_QUEUE
            title = f"Buy {item_name}?"
            outcome = (
                f"Starts after {quote.current_item_name or 'the active Fertilizer'} "
                f"ends, then lasts {_effect_duration(quote.descriptor.duration)}. "
                f"{_eligible_answer_effect(quote.descriptor.buff)}."
            )
            activity_label = f"Queued {item_name} on {fertilizer_target}"
            success_message = f"{item_name} queued."
        elif quote.disposition is PurchaseDisposition.EXTENDED:
            action = PurchaseAction.EXTEND
            title = f"Extend {item_name}?"
            outcome = (
                f"Adds {_effect_duration(quote.descriptor.duration)} to "
                f"{fertilizer_target}."
            )
            activity_label = f"Extended {item_name} on {fertilizer_target}"
            success_message = f"{item_name} extended."
        else:
            action = PurchaseAction.PURCHASE_APPLY
            title = f"Buy {item_name}?"
            outcome = (
                f"{fertilizer_target} · {_compact_effect(quote.descriptor.buff)} · "
                f"{_without_period(quote.descriptor.duration)}"
            )
            activity_label = f"Applied {item_name} to {fertilizer_target}"
            success_message = f"{item_name} applied."
        if quote.disposition is not PurchaseDisposition.INVENTORY:
            next_actions = ("View plant", "Keep browsing")
    elif quote.kind in {PurchaseKind.GARDEN_FEATURE, PurchaseKind.SCENERY}:
        title = f"Buy {item_name}?"
        outcome = "Adds it to garden decorations and scenery."
        preview_style = PurchasePreviewStyle.LANDSCAPE
        success_message = f"{item_name} added to your collection."
        next_actions = ("View in collection", "Keep browsing")
    elif quote.kind is PurchaseKind.COSMETIC:
        title = f"Buy {item_name}?"
        outcome = "Adds a cosmetic-only Display Decoration to your collection."
        preview_style = PurchasePreviewStyle.SQUARE
        success_message = f"{item_name} added to your collection."
        next_actions = ("View in collection", "Keep browsing")
    else:
        action = PurchaseAction.UNLOCK
        bed_name = item_name.replace("Garden bed", "Bed").replace("Garden Bed", "Bed")
        title = f"Unlock {bed_name}?"
        outcome = (
            "Adds one permanent garden bed. Each other planted bed adds a 10% "
            "Shared Growth share. A Full Bloom plant still adds its share."
        )
        preview_style = PurchasePreviewStyle.GARDEN_BED
        activity_label = f"Unlocked {item_name}"
        success_message = f"{bed_name} unlocked."
        next_actions = ("View garden", "Keep browsing")

    primary_label, primary_accessible, processing_label = _priced_action(
        action, quote.total_price
    )
    primary_label = _canonical_action_text(quote, action)
    primary_accessible = primary_label
    display_title = title
    display_outcome = outcome
    visible_facts = tuple(facts)
    show_preview = True
    show_cost = True
    balance_after: int | None = quote.balance_after
    secondary_label = "Cancel"
    primary_route = ""
    terminal = False
    retry = False
    show_category = False

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
        shortfall = max(
            0,
            int(quote.total_price) - max(0, int(quote.balance_before)),
        )
        shortfall_unit = "Garden Coin" if shortfall == 1 else "Garden Coins"
        display_outcome = (
            f"You need {shortfall:,} more {shortfall_unit} to buy {item_name}."
        )
        visible_facts = ()
        badges = []
        balance_after = None
        # Preserve the proposal context so the disabled Buy action explains
        # exactly what is unavailable instead of routing away from the item.
        show_cost = True
        show_preview = True
        secondary_label = "Close"
        primary_label, primary_accessible, _processing = _priced_action(
            action,
            quote.total_price,
        )
        primary_label = _canonical_action_text(quote, action)
        primary_accessible = primary_label
        primary_route = ""
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
        target_name=(
            target_name
            if quote.kind is PurchaseKind.FERTILIZER
            and quote.disposition is not PurchaseDisposition.INVENTORY
            else ""
        ),
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


def purchase_projection(
    quote: PurchaseQuote,
    *,
    status: PurchaseStatus | None = None,
    message: str = "",
    ignore_status: bool = False,
) -> PurchaseProjection:
    """Return the price-free action and exact transaction data separately."""

    effective_status = (
        PurchaseStatus.READY
        if ignore_status
        else status if status is not None else quote.status
    )
    presentation = purchase_presentation(
        quote,
        status=status,
        message=message,
        ignore_status=ignore_status,
    )
    rows: list[PurchaseTransactionRow] = []
    if presentation.show_cost:
        rows.append(PurchaseTransactionRow("price", "Price", quote.total_price))
        rows.append(
            PurchaseTransactionRow("balance", "Balance", quote.balance_before)
        )
        if presentation.balance_after is not None:
            rows.append(
                PurchaseTransactionRow(
                    "balance_after",
                    "After purchase",
                    presentation.balance_after,
                )
            )
    stored_item: FertilizerStoredItemProjection | None = None
    if quote.fertilizer_stored_item_disposition is not None:
        stored_item = fertilizer_stored_item_projection(
            quote.fertilizer_stored_item_disposition,
            duration_delta_seconds=quote.duration_delta_seconds,
            card_queue_delta=quote.card_queue_delta,
            expires_at_ms=quote.fertilizer_expires_at_ms,
        )
    can_commit = effective_status is PurchaseStatus.READY
    blocking_reason = (
        ""
        if can_commit or effective_status is PurchaseStatus.SUCCESS
        else str(message or quote.message or presentation.outcome)
    )
    action_text = str(presentation.primary_label)
    if quote.kind is PurchaseKind.FERTILIZER and stored_item is not None:
        action_text = (
            _canonical_action_text(quote, presentation.action)
            if quote.total_price > 0
            else stored_item.action_text
        )
    elif quote.kind is PurchaseKind.BED:
        action_text = _canonical_action_text(quote, PurchaseAction.UNLOCK)
    return PurchaseProjection(
        item_id=str(quote.item_id),
        action_text=action_text,
        price_coins=(
            None if quote.kind is PurchaseKind.BED else quote.total_price
        ),
        wallet_balance_coins=max(0, int(quote.balance_before)),
        transaction_rows=tuple(rows),
        can_commit=can_commit,
        blocking_reason=blocking_reason,
        appearance_state=(
            PurchaseAppearanceState.ENABLED
            if can_commit
            else PurchaseAppearanceState.DISABLED
        ),
        fertilizer_stored_item=stored_item,
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
    fertilizer_stored_item_disposition: FertilizerStoredItemDisposition | None = None
    duration_delta_seconds: int = 0
    card_queue_delta: int = 0
    fertilizer_expires_at_ms: int | None = None

    @property
    def success(self) -> bool:
        return self.status is PurchaseStatus.SUCCESS

    @property
    def fertilizer_stored_item(self) -> FertilizerStoredItemProjection | None:
        if self.fertilizer_stored_item_disposition is None:
            return None
        return fertilizer_stored_item_projection(
            self.fertilizer_stored_item_disposition,
            duration_delta_seconds=self.duration_delta_seconds,
            card_queue_delta=self.card_queue_delta,
            expires_at_ms=self.fertilizer_expires_at_ms,
        )

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
            "fertilizer_stored_item_disposition": (
                None
                if self.fertilizer_stored_item_disposition is None
                else self.fertilizer_stored_item_disposition.value
            ),
            "duration_delta_seconds": self.duration_delta_seconds,
            "card_queue_delta": self.card_queue_delta,
            "fertilizer_expires_at_ms": self.fertilizer_expires_at_ms,
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
        raw_fertilizer_disposition = value.get("fertilizer_stored_item_disposition")
        fertilizer_disposition: FertilizerStoredItemDisposition | None = None
        if raw_fertilizer_disposition is not None:
            try:
                fertilizer_disposition = FertilizerStoredItemDisposition(
                    str(raw_fertilizer_disposition)
                )
            except ValueError:
                return None
        duration_delta_seconds = value.get("duration_delta_seconds", 0)
        card_queue_delta = value.get("card_queue_delta", 0)
        if any(
            not isinstance(candidate, int)
            or isinstance(candidate, bool)
            or candidate < 0
            for candidate in (duration_delta_seconds, card_queue_delta)
        ):
            return None
        fertilizer_expires_at_ms = value.get("fertilizer_expires_at_ms")
        if fertilizer_expires_at_ms is not None and (
            not isinstance(fertilizer_expires_at_ms, int)
            or isinstance(fertilizer_expires_at_ms, bool)
            or fertilizer_expires_at_ms <= 0
        ):
            return None
        if fertilizer_disposition is not None:
            try:
                fertilizer_stored_item_projection(
                    fertilizer_disposition,
                    duration_delta_seconds=duration_delta_seconds,
                    card_queue_delta=card_queue_delta,
                    expires_at_ms=fertilizer_expires_at_ms,
                )
            except ValueError:
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
            fertilizer_stored_item_disposition=fertilizer_disposition,
            duration_delta_seconds=duration_delta_seconds,
            card_queue_delta=card_queue_delta,
            fertilizer_expires_at_ms=fertilizer_expires_at_ms,
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
