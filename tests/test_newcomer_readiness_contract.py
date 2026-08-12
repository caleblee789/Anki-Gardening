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

    assert f'aria-label="{HOME_NO_STARTER_TITLE}"' in html
    assert HOME_NO_STARTER_BODY in html
    assert HOME_NO_STARTER_ACCESSIBLE in html
    assert CHOOSE_STARTER_ACTION in html
    assert 'data-anki-garden-command="anki-garden:choose-starter"' in html
    assert 'data-testid="home-title" aria-label="Choose your first plant"' in html
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
    assert GARDEN_SETUP_SECONDARY_ACTION == "Not now"
    assert starter_confirmation("Rose Plant") == (
        "Rose Plant is planted and ready to nurture. "
        "Nurture it before studying so eligible answers can add Growth."
    )
    assert starter_ready_next_step("Rose Plant") == (
        "Rose Plant is ready. Answer an eligible card to give it Growth."
    )
    assert ACTIVE_GROWTH_TITLE == "Growth is underway"
    assert "nurtured plant" in ACTIVE_GROWTH_GUIDANCE
    assert "Nurture" in ACTIVE_GROWTH_GUIDANCE


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
    assert "NURSERY_STARTER_TITLE if starter_mode" in nursery
    assert "NURSERY_STARTER_RATIONALE" in nursery
    assert "NURSERY_STARTER_COUNT" in nursery
    assert "self.catalog_tabs.tabBar().setTabVisible(index, not starter_mode)" in nursery
    assert "self.coin_resource.setVisible(not starter_mode)" in nursery
    assert 'self.close_button.setText("Back to garden" if starter_mode else "Close")' in nursery
    assert "self._starter_card(species)" in nursery
    assert "self.catalog_tabs.setAccessibleDescription" in nursery
    assert "Cost: Free" not in nursery  # the visible label is centralized
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    assert "COST_FREE" not in available_card
    assert "PAID_COST_TEMPLATE" in available_card
    assert "if starter_mode:" in available_card
    assert "self._starter_card(species)" in available_card
    starter_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_starter_card"
    )
    assert "Starting stage:" in starter_card
    assert 'QPushButton(f"Choose {species_name}")' in starter_card
    assert 'QPushButton("View stages")' in starter_card
    assert "Free starter" not in available_card
    assert "Included with your free starter" not in available_card


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
    assert "starter_selection_complete" in setup
    assert "opening_starter" in addon
    assert "starter_selected_callback" in addon
    assert "starter_selected_callback" in dashboard
    choose_starter = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_choose_starter"
    )
    open_dashboard = _method_source(
        "ankigarden/addon.py", "AnkiGardenApp", "_open_dashboard_when_ready"
    )
    assert "StarterConfirmationDialog" in choose_starter
    assert "QDialog.DialogCode.Accepted" in choose_starter
    assert "self.refresh()" in choose_starter
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
    assert 'controls_layout.addWidget(self.motion_row)' in studio
    assert '"reduced_motion": animation_flags[1]' in studio
    assert 'not self.reduced_motion.isChecked()' in studio
    assert 'if transition_ids and bool(self.scene.get("motion_enabled", True)):' in scene
    assert 'if bool(self.scene.get("motion_enabled", True)):' in scene
    assert 'if not self.timer.isActive()' in scene
    assert "def show_nurture_feedback" in scene
    assert 'if not bool(self.scene.get("motion_enabled", True)):' in scene


def test_onboarding_coachmark_is_removed_after_starter_selection() -> None:
    onboarding = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_onboarding"
    )
    assert "starter_incomplete" in onboarding
    assert "self.onboarding_panel.hide()" in onboarding
    assert "ux_state == UX_ACTIVE_GROWTH" not in onboarding
    assert "permanent coachmark" in onboarding
