"""Capture the v27 single-window navigation while retaining historical IDs."""

from copy import deepcopy
from ..feature_availability import landmarks_enabled

from ._surface_specs import SURFACE_ROWS as LEGACY_ROWS
from .handoff import ADDITIONS, RETIRED_SURFACES


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
        # Unified supplies: active Fertilizer versus charge-focused, no-active-effect state.
        ("garden-use-fertilizer", "FertilizerDialog", "fertilizer", True),
        ("garden-use-growth-charges", "FertilizerDialog", "charges", False),
    )),
    ("Collection", (
        ("collection-plants-page", "GardenDashboard", "collection/plants", True),
        ("collection-species-details", "GardenDashboard", "species", False),
        ("collection-plant-details", "GardenDashboard", "plant", True),
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
        ("progress-today-page", "GardenDashboard", "progress/activity", True),
        ("progress-today-details", "GardenDashboard", "study-rewards-retained", False),
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


# The v27 contract retains the historical Landmark surface. Only active
# release routes participate in the current capture inventory.
GROUPS = tuple(
    (name, tuple(row for row in rows if row[0] != "collection-landmarks-page" or landmarks_enabled()))
    for name, rows in GROUPS
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
                    "owned_module_dependencies": ("capture/workspace.py", "feature_availability.py", "ui/dashboard.py", "ui/dialog_foundations.py", "ui/theme.py", "ui/copy.py", "ui/garden_studio.py", "ui/formatters.py", "ui/plant_display.py", "ui/scene.py") + (("ui/collection_workspace.py",) if group_name == "Collection" else ()),
                    "state_contract": {
                        "kind": "workspace",
                        "profile": {"profile_id": label, "window_family": family, "kind": "workspace", "state": label, "route": route},
                        "required_facts": ("ordered_fixture_label", "state_profile_declared", "window_family", "workspace_route", "visible_content", "plant_naming"),
                        "expected_fact_values": {"ordered_fixture_label": label, "state_profile_declared": label, "window_family": family, "workspace_route": route, "visible_content": True,
                                                 "plant_naming": {"custom_names_visible": (), "rename_visible": False, "passed": True}},
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
    template = next(row for row in rows if row["id"] == "garden-overview")
    full_within = representative_within = 0
    for label, route, representative in ADDITIONS:
        row = deepcopy(template)
        retired_reason = RETIRED_SURFACES.get(label, "")
        placements = []
        if not retired_reason:
            placements.append(("full", "Refinement views", len(GROUPS), full_order, full_within))
            full_order += 1
            full_within += 1
            if representative:
                placements.append(("representative", "Refinement views", len(GROUPS), representative_order, representative_within))
                representative_order += 1
                representative_within += 1
        family = "AnkiQt" if route.startswith("reviewer-") else "GardenDashboard"
        row.update(id=label, active=not bool(retired_reason), retired_reason=retired_reason,
                   placements=tuple(placements), executor="_capture_handoff_surface",
                   arguments=(label, route), scenario_id=label, fixture_id=f"{label}-v1",
                   scenario_step=1, renderer_family=family)
        row["owned_module_dependencies"] += ("capture/handoff_runtime.py", "ui/welcome.py", "ui/welcome_animation.py", "welcome_presentation.py", "models/welcome.py", "ui/trophy_room.py", "trophies.py", "ui/decoration_card.py", "ui/reviewer_hud_widget.py", "hooks/reviewer.py")
        if route in {"collection-menu", "storage-confirmation"}:
            row["owned_module_dependencies"] += ("ui/collection_workspace.py",)
        if route.startswith("reviewer-"):
            row.update(acquisition_policy="qt-shell-webview-verified", allow_foreground_fallback=True)
        row["state_contract"] = {
            "kind": "workspace-handoff", "profile": {"profile_id": label, "window_family": family,
                "kind": "workspace-handoff", "state": label, "route": route},
            "required_facts": ("ordered_fixture_label", "state_profile_declared", "window_family", "handoff_checks"),
            "expected_fact_values": {"ordered_fixture_label": label, "state_profile_declared": label,
                                    "window_family": family, "handoff_checks": True},
            "fact_constraints": {},
        }
        if route.startswith("reviewer-"):
            row["state_contract"]["reviewable_native_ui_issues"] = ("reviewer-collapsed-status-width",)
        rows.append(row)
    for row in rows:
        if row.get("active"):
            row["owned_module_dependencies"] += ("ui/plant_beds.py", "plant_beds.py", "achievements.py")
        if row["id"].startswith("progress-plant-beds-"):
            row["workflow_revision"] = "Starter-bed summary and compact content-driven two-by-two grid for Beds 3 through 6; shared eligibility and independent bonus receipts."
        if row.get("active") and row["id"] in {
            "progress-today-page", "progress-today-details", "progress-coins-page",
        }:
            row["owned_module_dependencies"] += ("ui/activity_page.py", "activity.py", "reward_ledger.py")
            row["workflow_revision"] = "Activity has one Study rewards panel with two daily Coin rewards and permanent achievement Growth tiers."
        if row.get("active") and row["id"] in {"progress-today-page", "progress-today-details"}:
            retained = row["id"] == "progress-today-details"
            row["workflow_revision"] += (
                " Capture a retained 10 percent Growth tier after a broken streak, current streak six days, next tier 100 days."
                if retained else " Capture Study rewards at 100 percent."
            )
            row["state_contract"]["required_facts"] += ("study_rewards_panel", "retained_growth_after_break")
            row["state_contract"]["expected_fact_values"].update(
                study_rewards_panel=True, retained_growth_after_break=retained)
        if row.get("active") and row["id"] == "active-deck-browser-home-after-nurture":
            row["owned_module_dependencies"] += ("capture/reviewer_feedback.py",)
        if row.get("active") and row["id"] in {
            "reviewer-hud-expanded", "reviewer-reward-dock-bundle",
            "workspace-reviewer-collapsed", "workspace-reviewer-rewards-list",
            "session-summary-after-review", "sync-rewards-summary",
        }:
            row["owned_module_dependencies"] += (
                "ui/reward_feed.py", "ui/active_consumables.py", "ui/reward_rarity.py",
                "ui/reward_receipt.py", "reward_presentation.py", "capture/reviewer_feedback.py",
                "garden_finds.py", "ui/session_summary.py",
            )
    return tuple(rows)


SURFACE_ROWS = workspace_surface_rows()
