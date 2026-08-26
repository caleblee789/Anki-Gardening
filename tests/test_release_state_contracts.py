from __future__ import annotations

from datetime import date
from pathlib import Path

from ankigarden.models.state import (
    GardenState,
    OnboardingProgress,
    OnboardingStep,
    Plant,
    PlantMemory,
)
from ankigarden.reward_presentation import achievement_presentations
from ankigarden.terminology import FERTILIZER_EXPLANATION
from ankigarden.ui.state_contracts import (
    CURRENT_ONBOARDING_VERSION,
    OnboardingState,
    StreakPresentationState,
    onboarding_state_display,
    streak_presentation,
)


ROOT = Path(__file__).resolve().parents[1]




def _starter(
    *,
    active: bool = False,
    first_nurture: bool = False,
    step: OnboardingStep | None = None,
) -> GardenState:
    memories = [PlantMemory("planted", "planted", "2026-08-12")]
    if first_nurture:
        memories.append(
            PlantMemory("nurture:first", "first_nurture", "2026-08-12")
        )
    plant = Plant("starter", "bonsai", "Moss", 0, growth_points=0, memories=memories)
    resolved_step = step or (
        OnboardingStep.COMPLETION if active else OnboardingStep.NURTURE
    )
    return GardenState(
        starter_selection_complete=True,
        plants=[plant],
        active_plant_id=plant.plant_id if active else None,
        onboarding=OnboardingProgress(
            step=resolved_step,
            starter_plant_id=plant.plant_id,
        ),
    )


def test_onboarding_state_contract_keeps_selection_planting_and_nurture_distinct() -> None:
    no_starter = onboarding_state_display(GardenState(), 0)
    selected_state = GardenState(
        onboarding=OnboardingProgress(
            step=OnboardingStep.CONFIRMATION,
            pending_species="bonsai",
        )
    )
    selected = onboarding_state_display(selected_state, 0, starter_selected=True)
    planted = onboarding_state_display(_starter(), CURRENT_ONBOARDING_VERSION)

    assert no_starter.state is OnboardingState.NO_STARTER
    assert no_starter.header_label == "No plant selected"
    assert selected.state is OnboardingState.STARTER_SELECTED
    assert selected.header_label == "Starter selected"
    assert selected.counted_step == 3
    assert planted.state is OnboardingState.STARTER_PLANTED_NOT_NURTURED
    assert planted.header_label == "Ready to nurture"
    assert planted.primary_action == "Nurture"
    assert planted.nurtured_marker_visible is False
    assert planted.onboarding_complete is False
    assert planted.counted_step == 5


def test_zero_growth_active_plant_is_nurtured_without_using_growth_as_evidence() -> None:
    display = onboarding_state_display(_starter(active=True), 0)

    assert display.state is OnboardingState.NURTURED_PLANT_ASSIGNED
    assert display.header_label == "Nurtured plant"
    assert display.nurtured_marker_visible is False
    assert display.primary_action == "Return to Anki"
    assert display.step is OnboardingStep.COMPLETION
    assert display.counted_step == 6


def test_persisted_done_prevents_onboarding_replay_when_preference_is_stale() -> None:
    display = onboarding_state_display(
        _starter(
            active=True,
            first_nurture=True,
            step=OnboardingStep.DONE,
        ),
        onboarding_version=0,
    )

    assert display.state is OnboardingState.ONBOARDING_COMPLETE
    assert display.onboarding_complete is True
    assert display.nurtured_marker_visible is False


def test_onboarding_preference_cannot_make_an_unassigned_starter_look_nurtured() -> None:
    display = onboarding_state_display(
        _starter(active=False),
        onboarding_version=CURRENT_ONBOARDING_VERSION,
    )

    assert display.state is OnboardingState.STARTER_PLANTED_NOT_NURTURED
    assert display.nurtured_marker_visible is False


def test_canonical_achievement_projection_includes_every_streak_threshold() -> None:
    streaks = tuple(
        (projection.achievement_id, projection.progress_target)
        for projection in achievement_presentations(GardenState())
        if projection.progress_metric == "streak_days"
    )

    assert streaks == (
        ("streak_7", 7),
        ("streak_30", 30),
        ("streak_100", 100),
        ("streak_365", 365),
    )


def test_canonical_clear_recall_projection_does_not_round_a_near_miss_up() -> None:
    state = GardenState()
    state.daily_stats.reviewed = 29
    state.daily_stats.correct = 26
    state.daily_stats.wrong = 3

    projection = next(
        item
        for item in achievement_presentations(state)
        if item.achievement_id == "retention_90"
    )

    assert projection.condition_lines == (
        "29 card answers, 89.7% accuracy",
    )


def test_streak_presentation_distinguishes_new_active_at_risk_and_ended() -> None:
    today = date(2026, 8, 12)

    new = streak_presentation(0, None, 0, today=today)
    active = streak_presentation(0, None, 1, today=today)
    at_risk = streak_presentation(3, "2026-08-11", 0, today=today)
    ended = streak_presentation(3, "2026-08-10", 0, today=today)

    assert (new.state, new.status_label, new.current_days) == (
        StreakPresentationState.NEW,
        "No active streak",
        0,
    )
    assert (active.state, active.current_days) == (StreakPresentationState.ACTIVE, 1)
    assert (at_risk.state, at_risk.status_label, at_risk.current_days) == (
        StreakPresentationState.AT_RISK,
        "At risk",
        3,
    )
    assert (ended.state, ended.status_label, ended.current_days) == (
        StreakPresentationState.ENDED,
        "Streak ended",
        0,
    )
    assert new.message == "Answer one card today to begin a streak."
    assert at_risk.message == "Answer one card today to keep your streak."
    assert ended.message == "Answer one card to begin a new streak."
    assert ended.previous_days == 3
    assert ended.missed_day == date(2026, 8, 11)


def test_fertilizer_explanation_uses_concise_card_answer_copy() -> None:
    assert "Growth to each card answer" in FERTILIZER_EXPLANATION
    assert "Growth per answer" not in FERTILIZER_EXPLANATION
