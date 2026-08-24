"""Small set of learner-facing copy contracts shared by Garden surfaces."""

FALLBACK_GARDEN_NAME = "My Garden"

HOME_NO_STARTER_TITLE = "Choose a starter"
HOME_NO_STARTER_BODY = ""
HOME_NO_STARTER_ACCESSIBLE = "Choose a starter for your garden."
CHOOSE_STARTER_ACTION = "Choose starter"

GARDEN_SETUP_TITLE = "Choose a starter"
GARDEN_SETUP_BODY = "Pick a free plant for your garden."
GARDEN_SETUP_SECONDARY_ACTION = "Later"
GARDEN_NURTURE_TITLE = "Nurture your first plant"
GARDEN_NURTURE_BODY = (
    "Nurture this plant so future Anki card answers add Growth here."
)
GARDEN_NURTURE_ACTION = "Open plant"

NURSERY_STARTER_TITLE = "Choose a starter"
NURSERY_STARTER_RATIONALE = "Your first plant is free."
NURSERY_STARTER_COUNT = ""
DISABLED_STARTER_TABS = "Items and Garden spaces are available after choosing a starter."
COST_FREE = "Free"
PAID_COST_TEMPLATE = "{amount} Garden Coins"

STARTER_CONFIRMATION_TEMPLATE = "Choose {plant_name}?"
REVIEWER_NO_STARTER_NOTICE = (
    "Choose a starter before studying to earn Growth. "
    "Earlier Growth and repeatable rewards are not backfilled; reliably "
    "reconstructable one-time achievements may be."
)
STARTER_READY_TEMPLATE = "{plant_name} is now nurtured."
ACTIVE_GROWTH_TITLE = "Nurtured"
ACTIVE_GROWTH_GUIDANCE = ""

FULLY_GROWN_MESSAGE = "Nurture another plant."
FULLY_GROWN_ACTION = "Nurture another plant"
ALL_PLANTS_COMPLETE = (
    "All of your current plants are fully grown. Add another plant to continue growing."
)

METRIC_AFFORDANCE = "Open details"
KEYBOARD_HINT = "Use the arrow keys to explore plants. Press Enter to open the selected item."

HOME_ACTIVE_ACTION = "Open garden"
NURTURED_STATUS = "Nurtured"
NO_DISPLAY_ISSUES = "No display issues found"
GROWTH_BREAKDOWN = "Growth breakdown"

REDUCED_MOTION_LABEL = "Reduce motion"
REDUCED_MOTION_DESCRIPTION = "Limits animation and pulsing."
REWARD_DISCLOSURE = "How rewards work"
STARTER_SAVE_ERROR = "Couldn’t save your garden. Nothing was changed."

# These terms are learner-facing authorities. Internal enum values, schemas,
# telemetry, and developer diagnostics intentionally keep their stable names.
GARDEN_APPEARANCE = "Garden appearance"
EDIT_APPEARANCE_ACTION = "Edit appearance"
OPEN_NURSERY_ACTION = "Open Nursery"
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
    """Return one learner-facing Garden Coin cost label."""

    return PAID_COST_TEMPLATE.format(amount=f"{max(0, int(amount)):,}")
