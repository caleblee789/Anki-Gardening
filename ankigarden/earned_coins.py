"""Pure Coin quotes shared by reward commits and previews."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CoinQuote:
    base_coins: int
    bonus_coins: int
    total_coins: int
    next_carry_units: int


def quote_earned_coins(base_coins: int, *, active_scenery_id: str,
                       carry_units: int) -> CoinQuote:
    from .balance_catalog import SCENERY_BY_ID

    base = max(0, int(base_coins))
    carry = max(0, min(99, int(carry_units)))
    percent = 0
    if active_scenery_id == "autumn":
        percent = next(effect.grant.amount for effect in SCENERY_BY_ID["autumn"].effects
                       if effect.grant is not None and str(effect.grant.kind) == "earned_coin_percent")
    bonus, remainder = divmod(base * percent + carry, 100)
    return CoinQuote(base, bonus, base + bonus, remainder)


def quote_completion_coins(core_coins: int, *, harvest_bell_coins: int = 0,
                           trophy_coins: int = 0, active_scenery_id: str,
                           carry_units: int) -> CoinQuote:
    base = bonus = 0
    for amount in (core_coins, trophy_coins, harvest_bell_coins):
        quote = quote_earned_coins(amount, active_scenery_id=active_scenery_id,
                                   carry_units=carry_units)
        base += quote.base_coins
        bonus += quote.bonus_coins
        carry_units = quote.next_carry_units
    return CoinQuote(base, bonus, base + bonus, carry_units)
