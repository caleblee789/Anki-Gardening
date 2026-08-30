"""Small set of learner-facing copy contracts shared by Garden surfaces."""

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
    "Your first plant is free and will be added to your collection. "
    "Appearance only. Every plant grows at the same rate."
)
NURSERY_STARTER_COUNT = ""
DISABLED_STARTER_TABS = "More Nursery sections are available after choosing a starter."
COST_FREE = "Free"
PAID_COST_TEMPLATE = "{amount} {unit}"

STARTER_CONFIRMATION_TEMPLATE = "Choose {plant_name}?"
REVIEWER_NO_STARTER_NOTICE = "Choose a starter to earn Growth."
STARTER_READY_TEMPLATE = "{plant_name} is now earning Growth."
ACTIVE_GROWTH_TITLE = "Nurtured"
ACTIVE_GROWTH_GUIDANCE = ""

FULLY_GROWN_MESSAGE = "Choose another plant to keep earning Growth."
FULLY_GROWN_ACTION = "Choose another plant"
ALL_PLANTS_COMPLETE = "All plants are fully grown."

METRIC_AFFORDANCE = "Open details"
KEYBOARD_HINT = "Use the arrow keys to explore plants. Press Enter to open the selected item."

HOME_ACTIVE_ACTION = "Open Garden"
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
    """Return one learner-facing price using singular-aware ``coin`` copy."""

    normalized = max(0, int(amount))
    return PAID_COST_TEMPLATE.format(
        amount=f"{normalized:,}",
        unit="coin" if normalized == 1 else "coins",
    )
