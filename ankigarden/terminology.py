"""Shared learner-facing explanations for Anki Garden gameplay terms."""

from .game import GardenGameEngine
from .models.state import STREAK_BONUS_TIERS


PASSIVE_GROWTH_PERCENT = 100 // GardenGameEngine.PASSIVE_GROWTH_DENOMINATOR
MAX_STREAK_BONUS_PERCENT = max(percent for _day, percent in STREAK_BONUS_TIERS)
PASSIVE_GROWTH_EXPLANATION = (
    "Other planted plants receive some of that Growth."
)

_FERTILIZER_EFFECTS = tuple(
    (
        spec.name.removesuffix(" Fertilizer"),
        int(spec.growth_per_answer),
    )
    for spec in GardenGameEngine.FERTILIZERS.values()
)
_FERTILIZER_EFFECT_TEXT = (
    ", ".join(
        f"{name} adds {amount:,}"
        for name, amount in _FERTILIZER_EFFECTS[:-1]
    )
    + ", and "
    + f"{_FERTILIZER_EFFECTS[-1][0]} adds {_FERTILIZER_EFFECTS[-1][1]:,}"
)

GROWTH_EXPLANATION = (
    "Card answers add Growth to your nurtured plant. Bonuses can add more."
)

ACTIVE_PLANT_EXPLANATION = (
    "Card Growth goes to the plant you nurture."
)

ANKI_STREAK_EXPLANATION = (
    "Your Anki streak counts study days in a row and can add up to "
    f"{MAX_STREAK_BONUS_PERCENT}% Growth."
)

ALL_DUE_EXPLANATION = (
    "Finish today’s due cards."
)

GARDEN_CURRENCY_EXPLANATION = (
    "Earn Garden Coins from cards, streaks, achievements, and Garden Finds. "
    "Spend them in the Nursery."
)

FERTILIZER_EXPLANATION = (
    "Fertilizer adds Growth to each card answer for a limited time."
)

PROGRESSION_SUMMARY = (
    "Card answers add Growth. Cards, streaks, achievements, and Garden Finds can also earn rewards."
)
