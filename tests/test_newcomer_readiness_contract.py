from __future__ import annotations

import ast
from pathlib import Path

from ankigarden.ui.copy import (
    ALL_PLANTS_COMPLETE,
    ACTIVE_GROWTH_GUIDANCE,
    ACTIVE_GROWTH_TITLE,
    CHOOSE_STARTER_ACTION,
    COST_FREE,
    DISABLED_STARTER_TABS,
    FULLY_GROWN_ACTION,
    FULLY_GROWN_MESSAGE,
    GARDEN_SETUP_BODY,
    GARDEN_SETUP_SECONDARY_ACTION,
    GARDEN_SETUP_TITLE,
    HOME_NO_STARTER_ACCESSIBLE,
    HOME_NO_STARTER_BODY,
    HOME_NO_STARTER_TITLE,
    KEYBOARD_HINT,
    METRIC_AFFORDANCE,
    NURSERY_STARTER_COUNT,
    NURSERY_STARTER_RATIONALE,
    NURSERY_STARTER_TITLE,
    PAID_COST_TEMPLATE,
    REDUCED_MOTION_DESCRIPTION,
    REDUCED_MOTION_LABEL,
    REWARD_DISCLOSURE,
    STARTER_SAVE_ERROR,
    starter_confirmation,
    starter_ready_next_step,
)
from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    render_home_widget,
)


ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def _method_source(relative: str, class_name: str, method_name: str) -> str:
    source = _source(relative)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    segment = ast.get_source_segment(source, child)
                    assert segment is not None
                    return segment
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _home_data(*, starter_selected: bool, garden_name: str = "My Garden") -> HomeWidgetData:
    return HomeWidgetData(
        reviews_today=0,
        growth_earned=0,
        base_growth=0,
        streak_bonus_growth=0,
        fertilizer_growth=0,
        bonus_growth=0,
        all_due_completed=False,
        streak_days=0,
        streak_bonus_percent=0,
        next_streak_day=1,
        next_streak_bonus_percent=0,
        garden_currency=0,
        weather="sunny",
        garden_name=garden_name,
        starter_selected=starter_selected,
    )


def test_no_starter_home_is_decision_oriented_and_keeps_the_name_fallback_visible() -> None:
    html = render_home_widget(
        HomeWidgetSnapshot(
            request_id=1,
            phase="success",
            data=_home_data(starter_selected=False, garden_name=""),
        )
    )

    assert f'aria-label="{CHOOSE_STARTER_ACTION}"' in html
    assert HOME_NO_STARTER_ACCESSIBLE in html
    assert CHOOSE_STARTER_ACTION in html
    assert 'data-anki-garden-command="anki-garden:choose-starter"' in html
    assert 'data-testid="home-title" aria-label="Choose a starter"' in html
    assert "Answer your first card" not in html
    assert 'data-testid="home-streak"' not in html
    assert 'data-testid="home-currency"' not in html
    assert "Ultra pity" not in html
    assert "1 in 100,000" not in html


def test_canonical_copy_inventory_is_centralized() -> None:
    copy = _source("ankigarden/ui/copy.py")
    expected_names = {
        "HOME_NO_STARTER_TITLE",
        "HOME_NO_STARTER_BODY",
        "GARDEN_SETUP_TITLE",
        "GARDEN_SETUP_BODY",
        "NURSERY_STARTER_TITLE",
        "NURSERY_STARTER_RATIONALE",
        "NURSERY_STARTER_COUNT",
        "DISABLED_STARTER_TABS",
        "COST_FREE",
        "PAID_COST_TEMPLATE",
        "FULLY_GROWN_MESSAGE",
        "FULLY_GROWN_ACTION",
        "ALL_PLANTS_COMPLETE",
        "METRIC_AFFORDANCE",
        "KEYBOARD_HINT",
        "REDUCED_MOTION_LABEL",
        "REDUCED_MOTION_DESCRIPTION",
        "REWARD_DISCLOSURE",
        "STARTER_SAVE_ERROR",
    }
    assert all(name in copy for name in expected_names)
    assert GARDEN_SETUP_SECONDARY_ACTION == "Later"
    assert NURSERY_STARTER_COUNT == ""
    assert STARTER_SAVE_ERROR == "Couldn’t save your garden. Nothing was changed."
    assert starter_confirmation("Rose Plant") == "Choose Rose Plant?"
    assert starter_ready_next_step("Rose Plant") == "Rose Plant is now nurtured."
    assert ACTIVE_GROWTH_TITLE == "Nurtured"
    assert ACTIVE_GROWTH_GUIDANCE == ""


def test_starter_mode_explains_the_low_pressure_choice_and_disabled_tabs() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    nursery = dashboard.split("class NurseryDialog", 1)[1].split(
        "class PlantInfoCard", 1
    )[0]

    for name in (
        "NURSERY_STARTER_TITLE",
        "NURSERY_STARTER_RATIONALE",
        "NURSERY_STARTER_COUNT",
    ):
        assert name in _source("ankigarden/ui/copy.py")
    assert "NURSERY_STARTER_TITLE" in nursery
    assert "if starter_mode" in nursery
    assert "NURSERY_STARTER_RATIONALE" in nursery
    assert "NURSERY_STARTER_COUNT" in nursery
    assert "self.catalog_tabs.tabBar().setTabVisible(index, not starter_mode)" in nursery
    assert "self.catalog_tabs.tabBar().setVisible(not starter_mode)" in nursery
    assert "self.coin_resource.setVisible(not starter_mode)" in nursery
    assert 'self.close_button.setText("Not now" if starter_mode else "Close")' in nursery
    assert "self.close_button.clicked.connect(self._close_nursery)" in nursery
    assert "self._starter_card(species)" in nursery
    assert "available = available[:4]" in nursery
    assert "self.catalog_tabs.setAccessibleDescription" in nursery
    assert "Cost: Free" not in nursery  # the visible label is centralized
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    assert "COST_FREE" not in available_card
    assert "cost_label(price)" in available_card
    assert "if starter_mode:" in available_card
    assert "self._starter_card(species)" in available_card
    starter_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_starter_card"
    )
    assert "Starting stage:" not in starter_card
    assert "seed_title(species_name)" in starter_card
    assert "COST_FREE" in starter_card
    assert 'QPushButton("Choose")' in starter_card
    assert 'f"Choose {item_name} as your first plant"' in starter_card
    assert 'QPushButton("View stages")' in starter_card
    assert "Free starter" not in available_card
    assert "Included with your free starter" not in available_card


def test_onboarding_copy_has_one_instruction_owner_per_visible_surface() -> None:
    copy = _source("ankigarden/ui/copy.py")
    contracts = _source("ankigarden/ui/state_contracts.py")
    refresh_onboarding = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_onboarding"
    )
    stats = _method_source(
        "ankigarden/ui/dashboard.py", "GardenStatsStrip", "set_growth_details"
    )
    completion = _method_source(
        "ankigarden/ui/dashboard.py",
        "GardenDashboard",
        "_onboarding_completion_receipt",
    )
    failure = _method_source(
        "ankigarden/ui/dashboard.py",
        "GardenDashboard",
        "_onboarding_failure_receipt",
    )
    open_starter = _method_source(
        "ankigarden/ui/dashboard.py",
        "GardenDashboard",
        "_open_starter_nursery",
    )

    assert 'HOME_NO_STARTER_BODY = ""' in copy
    assert 'HOME_NO_STARTER_ACCESSIBLE = "Choose a starter for your garden."' in copy
    assert '"No plant selected"' in contracts
    assert '"Ready to nurture"' in contracts
    assert '"NO PLANT SELECTED"' in stats
    assert '"READY TO NURTURE"' in stats
    assert "self.growth_value.hide()" in stats
    assert 'self.progress["growth"].hide()' in stats
    assert refresh_onboarding.count('"Not now"') == 3
    assert refresh_onboarding.count('"Back"') == 2
    assert "self._set_onboarding_shield(visible)" in refresh_onboarding
    assert '"Return to Anki"' in refresh_onboarding
    assert '"Explore garden"' in refresh_onboarding
    assert '"Try again"' in refresh_onboarding
    assert '"Return to setup"' in refresh_onboarding
    assert 'f"{plant_name}, your {species}, is growing in {bed}. "' in completion
    assert '"Future qualifying Anki card answers now generate Growth."' in completion
    assert '"No starter, garden bed, or nurture choice was saved."' in failure
    assert '"Your starter choice is still saved. No garden bed or nurture "' in failure
    assert '"Your last saved setup is unchanged."' in failure
    assert "last committed setup state" not in failure
    assert "self._onboarding_save_error = message" in open_starter
    assert "self.toast_region.show_message" not in open_starter


def test_nursery_tab_intros_do_not_repeat_section_details() -> None:
    sync_intro = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_sync_catalog_intro"
    )

    assert '2: "Make room for a larger plant collection."' in sync_intro
    assert '3: "Collect a new look for the garden."' in sync_intro
    assert "Garden spaces unlock permanently and in order." not in sync_intro
    assert "Preview collectible Weather and Scenery before buying." not in sync_intro
    nursery = _source("ankigarden/ui/dashboard.py")
    assert '"Unlocks follow the order shown below."' in nursery
    assert '"Each unlock adds one permanent planting space."' not in nursery


def test_onboarding_and_navigation_use_one_direct_starter_route() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    addon = _source("ankigarden/addon.py")
    setup = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_present_starter_setup_if_needed"
    )
    show_landmark = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_show_nursery_landmark"
    )

    assert "QInputDialog" not in dashboard
    assert "prompt_starter_if_needed" not in addon
    assert "_open_starter_nursery" in dashboard
    assert "self._open_starter_nursery()" in show_landmark
    assert "self.storage.state.onboarding.step != OnboardingStep.DONE" in setup
    assert "opening_starter" in addon
    assert "starter_selected_callback" in addon
    assert "starter_selected_callback" in dashboard
    choose_starter = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_choose_starter"
    )
    open_dashboard = _method_source(
        "ankigarden/addon.py", "AnkiGardenApp", "_open_dashboard_when_ready"
    )
    assert "self.engine.select_starter_species(species)" in choose_starter
    assert "self._starter_choice_pending" in choose_starter
    assert "Starter setup could not be saved." in choose_starter
    assert "the last committed Garden setup is unchanged" in choose_starter
    assert "Choose the plant " in choose_starter
    assert "again to retry, or select Not now." in choose_starter
    assert "except Exception:" in choose_starter
    assert "starter choice save failed unexpectedly" in choose_starter
    assert "if not ok:" in choose_starter
    assert "return" in choose_starter
    assert "self.accept()" in choose_starter
    assert "StarterConfirmationDialog" not in choose_starter
    assert "QTimer.singleShot(0, open_starter)" in open_dashboard


def test_fully_grown_and_accessibility_copy_are_rendered_at_the_action_site() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    scene = _source("ankigarden/ui/scene.py")
    assert FULLY_GROWN_MESSAGE in _source("ankigarden/ui/copy.py")
    assert FULLY_GROWN_ACTION in _source("ankigarden/ui/copy.py")
    assert "self.choose_another = QPushButton(FULLY_GROWN_ACTION)" in dashboard
    assert "self.choose_another.show()" in dashboard
    assert "All_PLANTS_COMPLETE" not in dashboard
    assert "ALL_PLANTS_COMPLETE" in dashboard
    assert KEYBOARD_HINT in scene
    assert "focusInEvent" in scene and "_show_keyboard_hint" in scene
    focus_in = _method_source("ankigarden/ui/scene.py", "GardenSceneWidget", "focusInEvent")
    assert "_show_keyboard_hint" in focus_in
    assert "MouseFocusReason" not in focus_in


def test_reduced_motion_is_visible_and_suppresses_scene_motion() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    scene = _source("ankigarden/ui/scene.py")
    assert 'self.reduced_motion = QCheckBox()' in studio
    assert "self.motion_row = ToggleSettingRow(" in studio
    assert 'self.advanced_actions_layout.addWidget(self.motion_row)' in studio
    assert '"reduced_motion": animation_flags[1]' in studio
    assert "effective_motion_enabled(" in studio
    assert "os_reader=lambda: self._system_reduced_motion" in studio
    assert 'if transition_ids and bool(self.scene.get("motion_enabled", True)):' in scene
    assert 'if bool(self.scene.get("motion_enabled", True)):' in scene
    assert 'if not self.timer.isActive()' in scene
    assert "def show_nurture_feedback" in scene
    assert 'if not bool(self.scene.get("motion_enabled", True)):' in scene


def test_onboarding_coachmark_is_removed_only_after_persisted_completion() -> None:
    onboarding = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_onboarding"
    )
    assert "if step == OnboardingStep.DONE:" in onboarding
    assert "self.onboarding_panel.hide()" in onboarding
    assert "self._set_onboarding_shield(False)" in onboarding
    assert "ux_state == UX_ACTIVE_GROWTH" not in onboarding
    assert "guided = step != OnboardingStep.DONE" in onboarding
    assert "self.progress_btn.setVisible(not guided)" in onboarding
