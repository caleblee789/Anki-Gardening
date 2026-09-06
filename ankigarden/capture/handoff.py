"""Qt-free refinement-sheet assignments, independent of acquisition order."""

# ID, native route, representative preflight. These IDs are newly allocated;
# retired IDs in earlier contracts remain permanently reserved.
ADDITIONS = (
    ("workspace-starter-awaiting-nurture", "starter-nurture", False),
    ("workspace-welcome-settled", "welcome", False),
    ("workspace-welcome-rewards-expanded", "welcome-rewards", True),
    ("workspace-decoration-inspector", "decoration-inspector", True),
    ("workspace-collection-plant-menu", "collection-menu", True),
    ("workspace-collection-storage-confirmation", "storage-confirmation", False),
    ("workspace-scenery-preview", "scenery-preview", False),
    ("workspace-scenery-applied-undo", "scenery-applied", False),
    ("workspace-additional-bonuses-expanded", "additional-bonuses", False),
    ("workspace-shop-supplies-scroll-end", "supplies-end", False),
    ("workspace-trophy-room", "trophies", True),
    ("workspace-achievements-scroll-end", "achievements-end", False),
    ("workspace-settings-unsaved", "settings-dirty", False),
    ("workspace-diagnostics-warning-details", "diagnostics-details", False),
    ("workspace-reviewer-collapsed", "reviewer-collapsed", False),
    ("workspace-reviewer-rewards-list", "reviewer-rewards-list", True),
)

SHEETS = (
    ("Garden and onboarding", (
        "starter-deck-browser-home", "garden-starter-picker",
        "garden-starter-selected", "garden-starter-placement",
        "workspace-starter-awaiting-nurture", "workspace-welcome-settled",
        "workspace-welcome-rewards-expanded", "garden-overview",
        "garden-inspector-nurtured", "garden-inspector-available",
        "garden-move-plant", "workspace-decoration-inspector",
    )),
    ("Collection and appearance", (
        "collection-plants-page", "collection-species-details",
        "collection-plant-details", "workspace-collection-plant-menu",
        "workspace-collection-storage-confirmation", "collection-scenery-page",
        "workspace-scenery-preview", "workspace-scenery-applied-undo",
        "collection-decorations-page", "workspace-additional-bonuses-expanded",
    )),
    ("Shop and item use", (
        "shop-plants-page", "shop-scenery-page", "shop-decorations-page",
        "shop-supplies-page", "workspace-shop-supplies-scroll-end",
        "shop-fertilizer-confirmation", "purchase-confirmation-growth-charge",
        "shop-purchase-receipt", "garden-use-fertilizer",
        "garden-use-growth-charges", "growth-charge-use-ready",
        "growth-charge-success-stage-reward",
    )),
    ("Progress and settings", (
        "progress-today-page", "progress-today-details",
        "progress-achievements-page", "workspace-achievements-scroll-end",
        "workspace-trophy-room", "progress-coins-page", "garden-settings",
        "workspace-settings-unsaved", "garden-diagnostics",
        "workspace-diagnostics-warning-details",
    )),
    ("Anki integration and rewards", (
        "active-deck-browser-home-after-nurture", "reviewer-hud-expanded",
        "workspace-reviewer-collapsed", "reviewer-reward-dock-bundle",
        "workspace-reviewer-rewards-list", "session-summary-after-review",
        "sync-rewards-summary",
    )),
)


def sheet_layout(labels):
    """Project the five review assignments onto one acquisition profile."""
    selected = set(labels)
    return [
        {"sheet": index, "name": name,
         "labels": [label for label in members if label in selected]}
        for index, (name, members) in enumerate(SHEETS, 1)
        if selected.intersection(members)
    ]
