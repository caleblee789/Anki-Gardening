"""Capture the v27 single-window navigation while retaining historical IDs."""

from copy import deepcopy

from ._surface_specs import SURFACE_ROWS as LEGACY_ROWS


# (surface ID, renderer, route, representative). Empty routes retain the
# established Anki/reward executor and its transaction fixture.
GROUPS = (
    ("First run", (
        ("starter-deck-browser-home", "AnkiQt", "", False),
        ("garden-starter-picker", "GardenDashboard", "starter", True),
        ("garden-starter-selected", "GardenDashboard", "starter-selected", False),
        ("garden-starter-placement", "GardenDashboard", "starter-placement", True),
    )),
    ("Garden", (
        ("garden-overview", "GardenDashboard", "garden", True),
        ("garden-inspector-nurtured", "GardenDashboard", "inspector", True),
        ("garden-inspector-available", "GardenDashboard", "inspector-available", False),
        ("garden-move-plant", "GardenDashboard", "move", False),
        ("garden-use-fertilizer", "FertilizerDialog", "fertilizer", True),
        ("garden-use-growth-charges", "FertilizerDialog", "charges", False),
    )),
    ("Collection", (
        ("collection-plants-page", "GardenDashboard", "collection/plants", True),
        ("collection-species-details", "SpeciesOverviewDialog", "species", False),
        ("collection-plant-details", "PlantStoryDialog", "plant", True),
        ("collection-scenery-page", "GardenDashboard", "collection/scenery", True),
        ("collection-decorations-page", "GardenDashboard", "collection/decorations", False),
        ("collection-landmarks-page", "GardenDashboard", "collection/garden-landmarks", True),
    )),
    ("Shop", (
        ("shop-plants-page", "GardenDashboard", "shop/plants", False),
        ("shop-supplies-page", "GardenDashboard", "shop/supplies", True),
        ("shop-scenery-page", "GardenDashboard", "shop/scenery", False),
        ("shop-decorations-page", "GardenDashboard", "shop/decorations", True),
        ("shop-fertilizer-confirmation", "PurchaseConfirmationDialog", "purchase-fertilizer", False),
        ("purchase-confirmation-growth-charge", "PurchaseConfirmationDialog", "", True),
        ("shop-purchase-receipt", "GardenDashboard", "purchase-receipt", False),
    )),
    ("Progress and Settings", (
        ("progress-today-page", "GardenDashboard", "progress/today", True),
        ("progress-today-details", "GardenDashboard", "today-details", False),
        ("progress-achievements-page", "GardenDashboard", "progress/achievements", False),
        ("progress-coins-page", "GardenDashboard", "progress/currency", False),
        ("garden-settings", "GardenSettingsDialog", "settings", True),
        ("garden-diagnostics", "GardenSettingsDialog", "diagnostics", False),
    )),
    ("Anki and Rewards", (
        ("active-deck-browser-home-after-nurture", "AnkiQt", "", False),
        ("reviewer-hud-expanded", "AnkiQt", "", True),
        ("session-summary-after-review", "AnkiQt", "", True),
        ("sync-rewards-summary", "AnkiQt", "", True),
        ("reviewer-reward-dock-bundle", "AnkiQt", "", False),
        ("growth-charge-use-ready", "GrowthChargeConfirmationDialog", "", True),
        ("growth-charge-success-stage-reward", "GrowthChargeConfirmationDialog", "", False),
    )),
)


def workspace_surface_rows():
    old = {row["id"]: row for row in LEGACY_ROWS}
    active = {row[0] for _, group in GROUPS for row in group}
    rows = []
    for original in LEGACY_ROWS:
        if original["id"] in active:
            continue
        row = deepcopy(original)
        if row["active"]:
            row.update(active=False, placements=(), retired_reason=(
                "Replaced by the v27 single-window Garden, Collection, Shop, "
                "and Progress surfaces. Historical evidence remains unchanged."
            ))
        rows.append(row)
    full_order = representative_order = 0
    first_run_ids = [row[0] for row in GROUPS[0][1]]
    for group_order, (group_name, group) in enumerate(GROUPS):
        representative_within = 0
        for within, (label, family, route, representative) in enumerate(group):
            placements = [("full", group_name, group_order, full_order, within)]
            full_order += 1
            if representative:
                placements.append(("representative", group_name, group_order, representative_order, representative_within))
                representative_order += 1
                representative_within += 1
            if not route:
                row = deepcopy(old[label])
                row["placements"] = tuple(placements)
            else:
                first_run = group_order == 0
                setup = "fresh-first-run" if first_run else "development-stress"
                scenario = "garden_first_run" if first_run else label
                row = {
                    "id": label, "active": True, "retired_reason": "",
                    "placements": tuple(placements),
                    "executor": "_capture_workspace_surface", "arguments": (label, route),
                    "scenario_id": scenario, "fixture_id": f"{scenario}-v1",
                    "scenario_step": within + 1 if first_run else 1,
                    "renderer_family": family, "acquisition_policy": "qt-widget-grab",
                    "allow_foreground_fallback": False,
                    "checkpoint_cohort": "starter" if first_run else "development-stress",
                    "checkpoint": setup, "internal_setups": (setup,),
                    "prerequisites": tuple(first_run_ids[:within]) if first_run else (),
                    "readiness": ("semantic-state", "two-stable-painted-frames", "visible-nonzero-geometry"),
                    "cleanup": ("close-dialog", "drain-deferred-delete", "restore-checkpoint"),
                    "evidence_requirements": ("fixture-identity", "geometry", "semantic-state", "nonblank-pixels"),
                    "owned_dependency_groups": (),
                    "owned_module_dependencies": ("ui/dashboard.py", "ui/dialog_foundations.py", "ui/theme.py", "ui/copy.py", "ui/garden_studio.py", "ui/formatters.py", "ui/plant_display.py", "ui/scene.py"),
                    "state_contract": {
                        "kind": "workspace",
                        "profile": {"profile_id": label, "window_family": family, "kind": "workspace", "state": label, "route": route},
                        "required_facts": ("ordered_fixture_label", "state_profile_declared", "window_family", "workspace_route", "visible_content"),
                        "expected_fact_values": {"ordered_fixture_label": label, "state_profile_declared": label, "window_family": family, "workspace_route": route, "visible_content": True},
                        "fact_constraints": {},
                    },
                }
            if label in {"reviewer-hud-expanded", "session-summary-after-review", "sync-rewards-summary", "reviewer-reward-dock-bundle"}:
                row["state_contract"] = {
                    "kind": "workspace-reward",
                    "profile": {"profile_id": label, "window_family": family, "kind": "workspace-reward", "state": label},
                    "required_facts": ("ordered_fixture_label", "state_profile_declared", "window_family", "compact_reward_checks", "reward_surface_visible"),
                    "expected_fact_values": {"ordered_fixture_label": label, "state_profile_declared": label, "window_family": family, "reward_surface_visible": True},
                    "fact_constraints": {},
                }
            if route == "shop/scenery":
                row["evidence_requirements"] += ("scroll:GardenDashboard:shop/scenery",)
            if group_order == 0:
                row.update(scenario_id="garden_first_run", fixture_id="garden_first_run-v1", scenario_step=within + 1)
            if label == "garden-starter-selected":
                row["workflow_revision"] = "Selection retained after Back from placement; no mandatory confirmation step."
            if label == "active-deck-browser-home-after-nurture":
                row["prerequisites"] = ("garden-inspector-nurtured",)
            rows.append(row)
    return tuple(rows)


SURFACE_ROWS = workspace_surface_rows()
