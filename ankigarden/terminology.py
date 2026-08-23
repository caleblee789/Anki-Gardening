"""Shared learner-facing explanations for Anki Garden gameplay terms."""

from .game import GardenGameEngine
from .models.state import STREAK_BONUS_TIERS


PASSIVE_GROWTH_PERCENT = 100 // GardenGameEngine.PASSIVE_GROWTH_DENOMINATOR
MAX_STREAK_BONUS_PERCENT = max(percent for _day, percent in STREAK_BONUS_TIERS)
PASSIVE_GROWTH_EXPLANATION = (
    "Other eligible planted plants receive "
    f"{PASSIVE_GROWTH_PERCENT} percent of that Growth after bonuses."
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
    "Growth is plant progress. Each card answer Garden can count starts with "
    f"{GardenGameEngine.BASE_GROWTH_PER_REVIEW:,} base Growth. The nurtured plant "
    f"receives full Growth. {PASSIVE_GROWTH_EXPLANATION} Anki streaks, Fertilizer, "
    "Booster Potions, equipped Weather, and Scenery contribute to study Growth once; "
    "Growth Charges apply only to their selected plant."
)

ACTIVE_PLANT_EXPLANATION = (
    "The plant you nurture receives full Growth from future card answers. "
    f"{PASSIVE_GROWTH_EXPLANATION} Growth already earned stays put."
)

ANKI_STREAK_EXPLANATION = (
    "Your Anki streak counts study days in a row and can add up to "
    f"{MAX_STREAK_BONUS_PERCENT}% Growth."
)

ALL_DUE_EXPLANATION = (
    "Finish every due review card and every introduced learning or relearning step due before "
    "Anki's next-day cutoff. Unseen new, suspended, and buried cards are excluded while unavailable."
)

GARDEN_CURRENCY_EXPLANATION = (
    "Garden Coins come from the first Anki card answer Garden can count each Anki day, every "
    "seventh consecutive counted day, finishing all due cards, plant stages, one-time achievements, "
    "and some Garden Finds. Spend them in the Nursery on plants, supplements, permanent "
    "upgrades, Weather, and Scenery."
)

FERTILIZER_EXPLANATION = (
    "Fertilizer temporarily adds bonus Growth to normal Anki card answers: "
    f"{_FERTILIZER_EFFECT_TEXT} Growth per Anki card answer while active. The resulting "
    "answer Growth goes in full to the plant you nurture. "
    f"{PASSIVE_GROWTH_EXPLANATION}"
)

PROGRESSION_SUMMARY = (
    "Card answers add Growth to the plant you nurture. Streaks, supplements, Weather, and "
    "Scenery can add bonus Growth, while daily activity, seven-day streak cycles, all-due "
    "completion, stages, one-time achievements, and Garden Finds can earn rewards."
)
