"""Small set of learner-facing copy contracts shared by Garden surfaces."""

FALLBACK_GARDEN_NAME = "My Garden"

HOME_NO_STARTER_TITLE = "Choose your first plant"
HOME_NO_STARTER_BODY = (
    "Choose a plant before studying. Reviews completed beforehand cannot earn Growth."
)
HOME_NO_STARTER_ACCESSIBLE = (
    "Reviews completed before you choose a plant cannot earn Growth later."
)
CHOOSE_STARTER_ACTION = "Choose plant"

GARDEN_SETUP_TITLE = "Choose your first plant"
GARDEN_SETUP_BODY = (
    "Select a free starter, then nurture it so future eligible answers can grow it."
)
GARDEN_SETUP_SECONDARY_ACTION = "Not now"
GARDEN_NURTURE_TITLE = "Nurture your first plant"
GARDEN_NURTURE_BODY = (
    "Nurture this plant so future eligible answers add Growth here."
)
GARDEN_NURTURE_ACTION = "Open plant"

NURSERY_STARTER_TITLE = "Choose your starter"
NURSERY_STARTER_RATIONALE = (
    "All starter plants grow through the same six stages and earn Growth at the same rate. "
    "Choose the artwork and name you like."
)
NURSERY_STARTER_COUNT = "Choose one of 10 starter plants. Your first choice is free."
DISABLED_STARTER_TABS = "Items and Garden spaces are available after choosing a starter."
COST_FREE = "Cost: Free"
PAID_COST_TEMPLATE = "Cost: {amount} Garden Coins"

STARTER_CONFIRMATION_TEMPLATE = (
    "{plant_name} is planted and ready to nurture. "
    "Nurture it before studying so eligible answers can add Growth."
)
REVIEWER_NO_STARTER_NOTICE = (
    "Choose a starter before studying to earn Growth. "
    "Answers completed before setup are not backfilled."
)
STARTER_READY_TEMPLATE = "{plant_name} is ready. Answer an eligible card to give it Growth."
ACTIVE_GROWTH_TITLE = "Growth is underway"
ACTIVE_GROWTH_GUIDANCE = (
    "Growth goes to your nurtured plant. Use Nurture to choose another unfinished plant when you are ready."
)

FULLY_GROWN_MESSAGE = (
    "This plant is fully grown. Choose another unfinished plant to nurture."
)
FULLY_GROWN_ACTION = "Choose another plant"
ALL_PLANTS_COMPLETE = (
    "All of your current plants are fully grown. Add another plant to continue growing."
)

METRIC_AFFORDANCE = "Open details"
KEYBOARD_HINT = "Use the arrow keys to explore plants. Press Enter to open the selected item."

HOME_ACTIVE_ACTION = "Open garden"
HOME_PREVIEW_HELP = "This is how the garden will appear on Anki home screens."
NURTURED_STATUS = "Nurtured"
NO_DISPLAY_ISSUES = "No display issues detected"
GROWTH_BREAKDOWN = "Growth breakdown"

REDUCED_MOTION_LABEL = "Reduce motion"
REDUCED_MOTION_DESCRIPTION = (
    "Minimizes ambient animation, pulsing effects, and animated transitions."
)
REWARD_DISCLOSURE = "How rewards work"
STARTER_SAVE_ERROR = "Your starter could not be saved. No changes were made. Try again."


def starter_confirmation(plant_name: str) -> str:
    return STARTER_CONFIRMATION_TEMPLATE.format(plant_name=str(plant_name))


def starter_ready_next_step(plant_name: str) -> str:
    return STARTER_READY_TEMPLATE.format(plant_name=str(plant_name))
