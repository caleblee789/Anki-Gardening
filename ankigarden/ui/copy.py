"""Small set of learner-facing copy contracts shared by Garden surfaces."""

from .formatters import format_garden_coins

FALLBACK_GARDEN_NAME = "My Garden"

HOME_NO_STARTER_TITLE = "Start your garden"
HOME_NO_STARTER_BODY = "Your first plant is free."
HOME_NO_STARTER_ACCESSIBLE = "Start your garden. Your first plant is free. Choose starter."
CHOOSE_STARTER_ACTION = "Choose starter"

GARDEN_SETUP_TITLE = "Choose your starter"
GARDEN_SETUP_BODY = "Pick one free plant for your garden."
GARDEN_SETUP_SECONDARY_ACTION = "Skip for now"
GARDEN_NURTURE_TITLE = "Nurture your first plant"
GARDEN_NURTURE_BODY = (
    "Nurture this plant to send card Growth here."
)
GARDEN_NURTURE_ACTION = "Open plant"

NURSERY_STARTER_TITLE = "Choose your starter"
NURSERY_STARTER_RATIONALE = (
    "Your first plant is free and will be added to your collection."
)
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
