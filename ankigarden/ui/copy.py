"""Small set of learner-facing copy contracts shared by Garden surfaces."""

import re

from .formatters import format_garden_coins

FALLBACK_GARDEN_NAME = "My Garden"

HOME_NO_STARTER_TITLE = "Choose your starter"
HOME_NO_STARTER_BODY = "Your first plant is free."
HOME_NO_STARTER_ACCESSIBLE = (
    "Choose your starter. Your first plant is free. Choose starter."
)
CHOOSE_STARTER_ACTION = "Choose starter"

GARDEN_SETUP_TITLE = "Choose your starter"
GARDEN_SETUP_BODY = (
    "Your first plant is free. All starter plants grow at the same rate."
)
GARDEN_SETUP_SECONDARY_ACTION = "Skip for now"
GARDEN_NURTURE_TITLE = "Nurture your first plant"
GARDEN_NURTURE_BODY = (
    "Nurture this plant to send card Growth here."
)
GARDEN_NURTURE_ACTION = "Open plant"

NURSERY_STARTER_TITLE = "Choose your starter"
# The preceding first-run step already explains that every starter is free and
# grows at the same rate. Keep this compatibility token empty so the Nursery
# header does not repeat that guidance.
NURSERY_STARTER_RATIONALE = ""
NURSERY_STARTER_COUNT = ""
DISABLED_STARTER_TABS = "More Nursery sections are available after choosing a starter."
COST_FREE = "Free"
STARTER_CONFIRMATION_TEMPLATE = "Choose {plant_name}?"
REVIEWER_NO_STARTER_NOTICE = "Choose a starter to earn Growth."
STARTER_READY_TEMPLATE = "{plant_name} is now your nurtured plant."
ACTIVE_GROWTH_TITLE = "Nurtured"
ACTIVE_GROWTH_GUIDANCE = ""

FULLY_GROWN_MESSAGE = "Choose next plant to keep earning Growth."
FULLY_GROWN_ACTION = "Choose next plant"
ALL_PLANTS_COMPLETE = "All plants are fully grown."

METRIC_AFFORDANCE = "Open details"
KEYBOARD_HINT = "Use the arrow keys to explore plants. Press Enter to open the selected item."

HOME_ACTIVE_ACTION = "Open garden"
NURTURED_STATUS = "Nurtured"
NO_DISPLAY_ISSUES = "No display issues found"
GROWTH_BREAKDOWN = "Growth breakdown"

REDUCED_MOTION_LABEL = "Reduce motion"
REDUCED_MOTION_DESCRIPTION = "Limits movement and transitions."
REWARD_DISCLOSURE = "How rewards work"
STARTER_SAVE_ERROR = "Couldn’t save your garden. Nothing was changed."

GARDEN_LANDMARK_DESCRIPTION = (
    "Fund this permanent cosmetic garden feature with Stored Growth, then claim "
    "each completed tier with Garden Coins."
)
GARDEN_LANDMARK_ACTIVE_ROUTING = (
    "Stored Growth earned after Full Bloom is routed to this project."
)
GARDEN_LANDMARK_UNLOCK_TITLE = (
    "Garden Landmarks unlock after your first Full Bloom"
)
GARDEN_LANDMARK_UNLOCK_BODY = (
    "Bring one plant to Full Bloom to begin funding this permanent cosmetic "
    "construction track."
)

# These terms are learner-facing authorities. Internal enum values, schemas,
# telemetry, and developer diagnostics intentionally keep their stable names.
GARDEN_APPEARANCE = "Garden appearance"
EDIT_APPEARANCE_ACTION = "Edit appearance"
OPEN_NURSERY_ACTION = "Open nursery"
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
        f"Starts after {predecessor}.\n"
        f"Adds {fertilizer_effect_copy(growth_per_card)} for the next "
        f"{card_count_label(card_count)}."
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
