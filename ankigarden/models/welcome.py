"""Durable receipts for first-time setup, independent of the reward ledger.

Amounts describe already-committed grants. Presentation acknowledgement never
owns reward eligibility, and this receipt is not pruned with recent feedback.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable


WELCOME_EVENT_KEY = "welcome:first-garden:v1"
WELCOME_GROWTH = 100
WELCOME_COINS = 50
WELCOME_STATUSES = frozenset({"collecting", "ready", "started", "acknowledged"})
MAX_WELCOME_REWARDS = 96


@dataclass(frozen=True)
class WelcomeReward:
    event_key: str
    reward_type: str
    amount: int
    item_id: str = ""

    @classmethod
    def from_dict(cls, value: Any) -> WelcomeReward:
        if not isinstance(value, dict):
            raise ValueError("welcome reward must be an object")
        event_key = value.get("event_key")
        kind = value.get("reward_type")
        amount = value.get("amount")
        item_id = value.get("item_id", "")
        if (
            not isinstance(event_key, str) or not 0 < len(event_key) <= 240
            or kind not in {"coins", "growth", "inventory_item", "trophy"}
            or type(amount) is not int or not 0 < amount <= 1_000_000_000
            or not isinstance(item_id, str) or len(item_id) > 120
            or (kind in {"inventory_item", "trophy"} and not item_id)
        ):
            raise ValueError("invalid welcome reward")
        return cls(event_key, kind, amount, item_id)


def merge_welcome_rewards(
    existing: Iterable[WelcomeReward], added: Iterable[WelcomeReward],
) -> tuple[WelcomeReward, ...]:
    rows = {}
    for row in (*tuple(existing), *tuple(added)):
        identity = (row.event_key, row.reward_type, row.item_id)
        previous = rows.setdefault(identity, row)
        if previous != row:
            raise ValueError("conflicting welcome reward identity")
    if len(rows) > MAX_WELCOME_REWARDS:
        raise ValueError("welcome receipt exceeds its reward bound")
    return tuple(rows.values())


@dataclass(frozen=True)
class WelcomeReceipt:
    receipt_id: str = WELCOME_EVENT_KEY
    status: str = "collecting"
    history_review_count: int | None = None
    history_rewards: tuple[WelcomeReward, ...] = ()
    achievement_ids: tuple[str, ...] = ()
    gift_rewards: tuple[WelcomeReward, ...] = ()
    plant_id: str = ""
    species: str = ""
    growth_before_units: int = 0
    growth_after_units: int = 0

    @property
    def pending(self) -> bool:
        return self.status in {"ready", "started"}

    def with_history(
        self, *, review_count: int | None = None,
        rewards: Iterable[WelcomeReward] = (), achievement_ids: Iterable[str] = (),
    ) -> WelcomeReceipt:
        if self.status != "collecting":
            return self
        return replace(
            self,
            history_review_count=(
                self.history_review_count if review_count is None else max(0, int(review_count))
            ),
            history_rewards=merge_welcome_rewards(self.history_rewards, rewards),
            achievement_ids=tuple(dict.fromkeys((*self.achievement_ids, *achievement_ids))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1, **asdict(self),
            "history_rewards": [asdict(row) for row in self.history_rewards],
            "achievement_ids": list(self.achievement_ids),
            "gift_rewards": [asdict(row) for row in self.gift_rewards],
        }

    @classmethod
    def from_dict(cls, value: Any) -> WelcomeReceipt | None:
        if value is None:
            return None
        try:
            if not isinstance(value, dict) or value.get("version") != 1:
                raise ValueError("unsupported welcome receipt")
            if value.get("receipt_id") != WELCOME_EVENT_KEY:
                raise ValueError("unknown welcome identity")
            status = value.get("status")
            if status not in WELCOME_STATUSES:
                raise ValueError("unknown welcome status")
            count = value.get("history_review_count")
            if count is not None and (type(count) is not int or not 0 <= count <= 1_000_000_000):
                raise ValueError("invalid historical review count")
            groups = []
            for key in ("history_rewards", "gift_rewards"):
                raw = value.get(key, [])
                if not isinstance(raw, (list, tuple)) or len(raw) > MAX_WELCOME_REWARDS:
                    raise ValueError("invalid welcome reward group")
                groups.append(merge_welcome_rewards((), (WelcomeReward.from_dict(row) for row in raw)))
            ids = value.get("achievement_ids", [])
            if not isinstance(ids, (list, tuple)) or len(ids) > 64 or any(
                not isinstance(item, str) or not 0 < len(item) <= 120 for item in ids
            ):
                raise ValueError("invalid welcome achievements")
            plant_id, species = value.get("plant_id", ""), value.get("species", "")
            if any(not isinstance(item, str) or len(item) > 120 for item in (plant_id, species)):
                raise ValueError("invalid welcome plant")
            before, after = value.get("growth_before_units", 0), value.get("growth_after_units", 0)
            if any(type(item) is not int or not 0 <= item <= 1_000_000_000_000 for item in (before, after)):
                raise ValueError("invalid welcome Growth")
            if after < before or (status != "collecting" and not plant_id):
                raise ValueError("incomplete welcome receipt")
            return cls(WELCOME_EVENT_KEY, status, count, groups[0], tuple(dict.fromkeys(ids)),
                       groups[1], plant_id, species, before, after)
        except (TypeError, ValueError):
            # The durable reward event still prevents replay if presentation
            # data is damaged. Never turn malformed display data into a grant.
            return None
