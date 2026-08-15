from __future__ import annotations

from datetime import date
from pathlib import Path

from ankigarden.models.state import (
    Achievement,
    DailyStats,
    GardenState,
    Plant,
    PlantMemory,
)
from ankigarden.terminology import FERTILIZER_EXPLANATION
from ankigarden.ui.state_contracts import (
    CURRENT_ONBOARDING_VERSION,
    DailyProgressState,
    OnboardingState,
    StreakPresentationState,
    achievement_progress_display,
    daily_progress_display,
    onboarding_state_display,
    streak_presentation,
)


ROOT = Path(__file__).resolve().parents[1]


def test_learner_copy_does_not_reintroduce_eligible_card_wording() -> None:
    learner_surfaces = (
        "ankigarden/ui/copy.py",
        "ankigarden/ui/dashboard.py",
        "ankigarden/ui/plant_display.py",
        "ankigarden/ui/scene.py",
        "ankigarden/ui/state_contracts.py",
        "ankigarden/terminology.py",
    )
    for relative in learner_surfaces:
        source = (ROOT / relative).read_text("utf-8").lower()
        assert "eligible card" not in source, relative
        assert "eligible answer" not in source, relative


def _starter(*, active: bool = False, first_nurture: bool = False) -> GardenState:
    memories = [PlantMemory("planted", "planted", "2026-08-12")]
    if first_nurture:
        memories.append(
            PlantMemory("nurture:first", "first_nurture", "2026-08-12")
        )
    plant = Plant("starter", "bonsai", "Moss", 0, growth_points=0, memories=memories)
    return GardenState(
        starter_selection_complete=True,
        plants=[plant],
        active_plant_id=plant.plant_id if active else None,
    )


def test_onboarding_state_contract_keeps_selection_planting_and_nurture_distinct() -> None:
    no_starter = onboarding_state_display(GardenState(), 0)
    selected = onboarding_state_display(GardenState(), 0, starter_selected=True)
    planted = onboarding_state_display(_starter(), CURRENT_ONBOARDING_VERSION)

    assert no_starter.state is OnboardingState.NO_STARTER
    assert no_starter.header_label == "No plant selected"
    assert selected.state is OnboardingState.STARTER_SELECTED
    assert selected.header_label == "Selected plant"
    assert planted.state is OnboardingState.STARTER_PLANTED_NOT_NURTURED
    assert planted.header_label == "Ready to nurture"
    assert planted.primary_action == "Nurture"
    assert planted.nurtured_marker_visible is False
    assert planted.onboarding_complete is False


def test_zero_growth_active_plant_is_nurtured_without_using_growth_as_evidence() -> None:
    display = onboarding_state_display(_starter(active=True), 0)

    assert display.state is OnboardingState.NURTURED_PLANT_ASSIGNED
    assert display.header_label == "Nurtured plant"
    assert display.nurtured_marker_visible is True
    assert display.primary_action is None


def test_first_nurture_memory_prevents_onboarding_replay_when_preference_is_stale() -> None:
    display = onboarding_state_display(
        _starter(active=True, first_nurture=True),
        onboarding_version=0,
    )

    assert display.state is OnboardingState.ONBOARDING_COMPLETE
    assert display.onboarding_complete is True
    assert display.nurtured_marker_visible is True


def test_onboarding_preference_cannot_make_an_unassigned_starter_look_nurtured() -> None:
    display = onboarding_state_display(
        _starter(active=False),
        onboarding_version=CURRENT_ONBOARDING_VERSION,
    )

    assert display.state is OnboardingState.STARTER_PLANTED_NOT_NURTURED
    assert display.nurtured_marker_visible is False


def test_completed_one_time_achievement_uses_immutable_thresholds() -> None:
    state = GardenState(
        streak_days=0,
        daily_stats=DailyStats(reviewed=0, correct=0, wrong=0),
    )
    achievement = Achievement(
        "streak_7",
        "7-Day Anki Streak",
        "",
        unlocked=True,
        unlocked_at="2026-08-01T12:00:00+00:00",
    )

    display = achievement_progress_display(achievement, state)

    assert display.completed is True
    assert (display.current, display.target) == (7, 7)
    assert display.value_text == "7 of 7 Anki days"


def test_clear_recall_has_separate_live_condition_rows() -> None:
    achievement = Achievement("retention_90", "Clear Recall", "")
    state = GardenState(
        daily_stats=DailyStats(reviewed=12, correct=10, wrong=2),
    )

    display = achievement_progress_display(achievement, state)

    assert [(row.label, row.value_text, row.satisfied) for row in display.conditions] == [
        ("Accuracy", "83% / 90%", False),
        ("Anki card answers", "12 / 20", False),
    ]


def test_completed_clear_recall_conditions_do_not_regress_with_new_day_counters() -> None:
    achievement = Achievement(
        "retention_90",
        "Clear Recall",
        "",
        unlocked=True,
        unlocked_at="2026-08-01T12:00:00+00:00",
    )
    state = GardenState(
        daily_stats=DailyStats(reviewed=3, correct=1, wrong=2),
    )

    display = achievement_progress_display(achievement, state)

    assert display.completed is True
    assert (display.current, display.target) == (90, 90)
    assert [(row.label, row.value_text, row.satisfied) for row in display.conditions] == [
        ("Accuracy", "90% / 90%", True),
        ("Anki card answers", "20 / 20", True),
    ]


def test_streak_presentation_distinguishes_new_active_at_risk_and_ended() -> None:
    today = date(2026, 8, 12)

    new = streak_presentation(0, None, 0, today=today)
    active = streak_presentation(0, None, 1, today=today)
    at_risk = streak_presentation(3, "2026-08-11", 0, today=today)
    ended = streak_presentation(3, "2026-08-10", 0, today=today)

    assert (new.state, new.status_label, new.current_days) == (
        StreakPresentationState.NEW,
        "Start today",
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
    assert ended.message == "Answer an Anki card to begin a new streak."
    assert ended.previous_days == 3
    assert ended.missed_day == date(2026, 8, 11)


def test_daily_progress_state_machine_never_offers_a_contradictory_action() -> None:
    remaining = daily_progress_display(4, reward_complete=False, reviewed_today=2)
    completed = daily_progress_display(
        0,
        reward_complete=True,
        reviewed_today=12,
        reward_outcome="15 Garden Coins rewarded.",
    )
    activation = daily_progress_display(0, reward_complete=False, reviewed_today=0)
    supported_activation = daily_progress_display(
        0,
        reward_complete=False,
        reviewed_today=0,
        custom_study_supported=True,
    )
    no_due = daily_progress_display(0, reward_complete=False, reviewed_today=12)

    assert remaining.state is DailyProgressState.IN_PROGRESS
    assert remaining.summary == "4 cards remaining"
    assert remaining.action_label == "Continue studying"
    assert remaining.action_enabled is True

    assert completed.state is DailyProgressState.COMPLETE
    assert completed.summary == "Today’s study goal is complete"
    assert completed.reward_outcome == "15 Garden Coins rewarded."
    assert completed.action_label is None

    assert activation.state is DailyProgressState.ACTIVATION_REQUIRED
    assert activation.summary == "No cards are due today"
    assert activation.detail == (
        "Answer one Anki card through custom study to activate today’s reward."
    )
    assert activation.action_label is None
    assert activation.action_enabled is False
    assert supported_activation.action_label == "Open custom study"
    assert supported_activation.action_kind == "customStudy"
    assert supported_activation.action_enabled is True

    assert no_due.state is DailyProgressState.NO_DUE
    assert no_due.action_label is None
    assert no_due.action_enabled is False


def test_fertilizer_explanation_uses_eligible_answer_semantics() -> None:
    assert "Growth per Anki card answer" in FERTILIZER_EXPLANATION
    assert "Growth per answer" not in FERTILIZER_EXPLANATION
