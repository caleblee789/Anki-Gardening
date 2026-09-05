"""Small set of learner-facing copy contracts shared by Garden surfaces."""

import re

from .formatters import format_garden_coins

FALLBACK_GARDEN_NAME = "My Garden"

HOME_NO_STARTER_TITLE = "Grow your first plant"
HOME_NO_STARTER_BODY = "Your first plant is free."
HOME_NO_STARTER_ACCESSIBLE = "Grow your first plant. Your first plant is free. Choose a plant."
CHOOSE_STARTER_ACTION = "Choose a plant"

GARDEN_SETUP_TITLE = "Choose your first plant"
GARDEN_SETUP_BODY = "Pick one free plant for your garden."
GARDEN_SETUP_SECONDARY_ACTION = "Skip for now"
GARDEN_NURTURE_TITLE = "Nurture your first plant"
GARDEN_NURTURE_BODY = (
    "Nurture this plant to grow it as you study."
)
GARDEN_NURTURE_ACTION = "Open plant"

NURSERY_STARTER_TITLE = "Choose your first plant"
NURSERY_STARTER_RATIONALE = (
    "Your first plant is free. All plants grow at the same rate."
)
NURSERY_STARTER_COUNT = ""
DISABLED_STARTER_TABS = "The Shop opens after you choose a plant."
COST_FREE = "Free"
STARTER_CONFIRMATION_TEMPLATE = "Choose {plant_name}?"
REVIEWER_NO_STARTER_NOTICE = "Choose a plant to earn Growth."
STARTER_READY_TEMPLATE = "{plant_name} is now your nurtured plant."
ACTIVE_GROWTH_TITLE = "Nurtured"
ACTIVE_GROWTH_GUIDANCE = ""

FULLY_GROWN_MESSAGE = "Choose another plant to nurture."
FULLY_GROWN_ACTION = "Choose next plant"
ALL_PLANTS_COMPLETE = "All plants are fully grown."

METRIC_AFFORDANCE = "Open details"
KEYBOARD_HINT = "Use the arrow keys to explore plants. Press Enter to open the selected item."

HOME_ACTIVE_ACTION = "Open garden"
NURTURED_STATUS = "Nurtured"
NO_DISPLAY_ISSUES = "All artwork is available"
GROWTH_BREAKDOWN = "Growth breakdown"

REDUCED_MOTION_LABEL = "Reduce motion"
REDUCED_MOTION_DESCRIPTION = "Limits movement and transitions."
REWARD_DISCLOSURE = "How rewards work"
STARTER_SAVE_ERROR = "Couldn’t save your garden. Nothing was changed."

GARDEN_LANDMARK_DESCRIPTION = (
    "Use Stored Growth and Coins to build landmarks for your garden."
)
GARDEN_LANDMARK_ACTIVE_ROUTING = (
    "New Stored Growth goes toward this landmark."
)
GARDEN_LANDMARK_UNLOCK_TITLE = (
    "Garden Landmarks unlock after your first Full Bloom"
)
GARDEN_LANDMARK_UNLOCK_BODY = (
    "Grow one plant to Full Bloom to start building landmarks."
)

# These terms are learner-facing authorities. Internal enum values, schemas,
# telemetry, and developer diagnostics intentionally keep their stable names.
GARDEN_APPEARANCE = "Garden appearance"
EDIT_APPEARANCE_ACTION = "Edit appearance"
OPEN_NURSERY_ACTION = "Shop"
TRY_AGAIN_ACTION = "Try again"
TECHNICAL_DETAILS_ACTION = "Technical details"


def starter_confirmation(plant_name: str) -> str:
    return STARTER_CONFIRMATION_TEMPLATE.format(plant_name=str(plant_name))


def starter_ready_next_step(plant_name: str) -> str:
    return STARTER_READY_TEMPLATE.format(plant_name=str(plant_name))


def seed_title(species_name: str) -> str:
    """Return the shared visible title for a Nursery seed purchase."""

    return f"{str(species_name).strip()} Seed"


def cost_label(amount: int) -> str:
    """Return one learner-facing price using canonical Garden Coin copy."""

    normalized = max(0, int(amount))
    return format_garden_coins(normalized)


def card_count_label(amount: int) -> str:
    """Return a singular-aware card quantity for visible cadence copy."""

    normalized = max(0, int(amount))
    return f"{normalized:,} {'card' if normalized == 1 else 'cards'}"


def fertilizer_effect_copy(growth_per_card: int) -> str:
    """Return the exact visible Fertilizer effect contract."""

    return f"+{max(0, int(growth_per_card)):,} Growth per card"


def fertilizer_duration_copy(card_count: int) -> str:
    """Return the exact visible duration for one Fertilizer dose."""

    return f"Lasts for {card_count_label(card_count)}"


def fertilizer_queue_copy(
    predecessor_name: str,
    *,
    growth_per_card: int,
    card_count: int,
) -> str:
    """Return the two-line queued-dose consequence without implied overlap."""

    predecessor = str(predecessor_name or "the active Fertilizer").strip()
    return (
        f"{fertilizer_effect_copy(growth_per_card)} for "
        f"{card_count_label(card_count)} once it starts.\n"
        f"Starts after {predecessor}."
    )


_GARDEN_BONUS_EFFECT_COPY = {
    "watering_station": (
        "Earn +1 bonus Growth every 5 cards during your first 100 cards each day."
    ),
    "wind_chime": "Earn +1 bonus Growth every 10 cards.",
    "firefly_lantern": (
        "Every 5 cards, the unfinished plant nearest its next checkpoint gains "
        "+3 Growth."
    ),
    "autumn": (
        "Finish today’s cards for +4 Coins. Plant checkpoints and first-time "
        "stage rewards give 50% more Coins."
    ),
    "snowy": (
        "Earn a Small Growth Charge every second day you finish today’s cards with this bonus."
    ),
    "full_moon": (
        "Earn a Booster Potion every sixth day you finish today’s cards with this bonus."
    ),
    "herbalist_hourglass": (
        "Earn a Booster Potion every 30 days you finish today’s cards with this bonus. "
        "Potions started with this bonus last 25 extra cards."
    ),
    "prism_trellis": (
        "Set aside 1 Growth on each of your first 100 cards per day, up to 300. "
        "Finish today’s cards with this bonus to release it."
    ),
}


def learner_card_copy(value: object) -> str:
    """Remove internal eligibility/review cadence terms from visible copy only."""

    text = str(value or "")
    replacements = (
        (r"\beligible card answers\b", "cards"),
        (r"\beligible card answer\b", "card"),
        (r"\beligible cards\b", "cards"),
        (r"\beligible card\b", "card"),
        (r"\breviews remaining\b", "cards remaining"),
        (r"\breview remaining\b", "card remaining"),
        (r"\bper review\b", "per card"),
        (r"\bNursery\b", "Shop"),
        (r"\bDisplay Decoration\b", "decoration"),
        (r"\bScenery appearance\b", "scenery"),
        (r"\bGarden Coins\b", "Coins"),
        (r"\bGarden Coin\b", "Coin"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def garden_bonus_effect_copy(item_id: str, fallback: object = "") -> str:
    """Resolve exact player-facing bonus mechanics from one stable catalog ID."""

    normalized = str(item_id or "").strip().casefold()
    return _GARDEN_BONUS_EFFECT_COPY.get(
        normalized,
        learner_card_copy(fallback).strip(),
    )


def project_feedback_copy(value: object) -> str:
    """Translate backend project-state vocabulary at the presentation boundary."""

    text = str(value or "")
    phrase_replacements = (
        ("Fund all Landmark and Mastery tracks first.",
         "Complete all Garden Landmark and Cultivation Mastery projects first."),
        ("Landmark track is fully funded.", "Garden Landmark is completed."),
        ("This Mastery track is fully funded.",
         "This Cultivation Mastery project is completed."),
        ("This Growth project is fully funded.", "This Growth project is completed."),
        ("Fund and claim earlier tiers first.",
         "Complete the earlier rewards first."),
        ("This tier is already claimed.", "This reward is already completed."),
    )
    for internal, visible in phrase_replacements:
        text = text.replace(internal, visible)
    text = re.sub(r"\bclaimable\b", "reward ready", text, flags=re.IGNORECASE)
    text = re.sub(r"\bclaimed\b", "completed", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfunded\b", "in progress", text, flags=re.IGNORECASE)
    return text
