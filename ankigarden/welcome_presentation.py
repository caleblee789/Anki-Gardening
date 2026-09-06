"""Read-only presentation of the first Garden's actual rewards."""
from __future__ import annotations

from dataclasses import dataclass

from .achievements import ACHIEVEMENTS_BY_ID
from .balance_catalog import CONSUMABLES, COSMETICS
from .models.welcome import WelcomeReceipt, WelcomeReward
from .ui.copy import past_study_intro


@dataclass(frozen=True)
class WelcomeRewardLine:
    label: str
    amount: int
    icon: str
    item_id: str = ""

    @property
    def text(self) -> str:
        return f"+{self.amount:,} {self.label}"


def welcome_reward_lines(rewards: tuple[WelcomeReward, ...]) -> tuple[WelcomeRewardLine, ...]:
    quantities: dict[tuple[str, str], int] = {}
    for reward in rewards:
        key = reward.reward_type, reward.item_id
        quantities[key] = quantities.get(key, 0) + reward.amount
    consumables = {str(item.consumable_id): item for item in CONSUMABLES}
    trophies = {str(item.cosmetic_id): item for item in COSMETICS}
    rows = []
    for (kind, item_id), amount in quantities.items():
        if kind == "coins":
            row = WelcomeRewardLine("Coins", amount, "coin")
        elif kind == "growth":
            row = WelcomeRewardLine("Growth", amount, "growth")
        elif kind == "inventory_item" and item_id in consumables:
            label = consumables[item_id].display_name
            row = WelcomeRewardLine(label + ("s" if amount != 1 else ""), amount, "growth", item_id)
        elif kind == "trophy" and item_id in trophies:
            row = WelcomeRewardLine(trophies[item_id].display_name, amount, "stage", item_id)
        else:
            continue
        rows.append(row)
    return tuple(sorted(rows, key=lambda row: (
        {"Growth": 0, "Coins": 1}.get(row.label, 2),
        {"growth_charge_small": 0, "growth_charge_standard": 1, "growth_charge_grand": 2}.get(row.item_id, 3),
        row.item_id,
    )))


@dataclass(frozen=True)
class WelcomePresentation:
    gift: tuple[WelcomeRewardLine, ...]
    history: tuple[WelcomeRewardLine, ...]
    history_intro: str
    achievement_count: int
    show_history: bool


def present_welcome(receipt: WelcomeReceipt) -> WelcomePresentation:
    gift = welcome_reward_lines(receipt.gift_rewards)
    history = welcome_reward_lines(receipt.history_rewards)
    count = sum(key in ACHIEVEMENTS_BY_ID for key in receipt.achievement_ids)
    return WelcomePresentation(
        gift, history,
        past_study_intro(receipt.history_review_count, has_rewards=bool(history or count)),
        count, bool(receipt.history_review_count or history or count),
    )
