"""Small set of learner-facing copy contracts shared by Garden surfaces."""

from __future__ import annotations

import re
from html import escape

from ..models.state import DEFAULT_GARDEN_NAME
from ..bonus_copy import GARDEN_BONUS_EFFECT_COPY
from .formatters import format_garden_coins

GARDEN_TITLE = "Anki Garden"
FALLBACK_GARDEN_NAME = DEFAULT_GARDEN_NAME

WELCOME_TITLE = "Welcome to your new Anki Garden!"
WELCOME_BODY = (
    "Study each day to earn rewards and help your plants grow."
)
WELCOME_REWARDS_ACTION = "View rewards"


def past_study_intro(review_count: int | None, *, has_rewards: bool) -> str:
    """Count review events accurately, including repeat answers to one card."""
    if review_count is None:
        return "Your past study has earned you these rewards:" if has_rewards else ""
    count = max(0, int(review_count))
    noun = "card review" if count == 1 else "card reviews"
    total = f"You’ve completed {count:,} {noun} in Anki."
    return (
        f"Rewards from your {count:,} past Anki {'review' if count == 1 else 'reviews'}:"
        if has_rewards else
        f"{total} Keep studying to reach your first study milestone."
    )

HOME_NO_STARTER_TITLE = "Grow your first plant"
HOME_NO_STARTER_BODY = "Your first plant is free."
HOME_NO_STARTER_ACCESSIBLE = "Grow your first plant. Your first plant is free. Choose a plant."
CHOOSE_STARTER_ACTION = "Choose a plant"


def garden_preview_title(title: str) -> str:
    """Keep onboarding copy while hiding saved names in older previews."""
    return HOME_NO_STARTER_TITLE if title == HOME_NO_STARTER_TITLE else GARDEN_TITLE

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
    "Your first plant is free. It starts as a seed and grows as you study."
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

    from ..presentation import plant_stage_title

    return plant_stage_title(species_name, "seed")


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
        f"{card_count_label(card_count)}.\n"
        f"Starts after {predecessor}."
    )





def garden_bonus_summary(item_id: str, full_effect: str = "") -> str:
    """Use the same concise description in Collection and equipped-item cards."""
    if str(item_id) in {"seedling_sign", "default"}:
        return "No study bonus"
    return garden_bonus_effect_copy(item_id, full_effect) or "No study bonus"


def inline_detail_copy(label: str, value: str) -> str:
    """Keep short metadata beside its label; longer values wrap naturally."""
    return f"<b>{escape(label)}:</b> {escape(value).replace(chr(10), '<br>')}"


def learner_card_copy(value: object) -> str:
    """Remove internal eligibility/review cadence terms from visible copy only."""

    text = str(value or "")
    replacements = (
        (r"\beach Anki day\b", "each day"),
        (r"\bone Anki day\b", "one day"),
        (r"\b(\d+)-Day Anki Streak\b", r"\1-day Anki streak"),
        (r"\bnext study day\b", "tomorrow"),
        (r"\bNext study day\b", "Tomorrow"),
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
    return GARDEN_BONUS_EFFECT_COPY.get(
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


def scenery_effect_copy(item_id: str, fallback: object = "") -> str:
    """Use the same source-grounded benefit copy in Shop and Collection."""
    return garden_bonus_effect_copy(item_id, fallback)
