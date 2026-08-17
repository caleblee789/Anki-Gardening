from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from ..models.state import OnboardingStep


CURRENT_ONBOARDING_VERSION = 3


class OnboardingState(str, Enum):
    NO_STARTER = "noStarter"
    STARTER_SELECTED = "starterSelected"
    STARTER_PLANTED_NOT_NURTURED = "starterPlantedNotNurtured"
    NURTURED_PLANT_ASSIGNED = "nurturedPlantAssigned"
    ONBOARDING_COMPLETE = "onboardingComplete"


@dataclass(frozen=True)
class OnboardingStateDisplay:
    state: OnboardingState
    header_label: str
    primary_action: str | None
    nurtured_marker_visible: bool
    onboarding_complete: bool
    step: OnboardingStep | None = None
    counted_step: int | None = None
    total_steps: int = 6


def onboarding_state_display(
    garden_state: Any,
    onboarding_version: Any,
    *,
    starter_selected: bool = False,
) -> OnboardingStateDisplay:
    """Derive the first-plant lifecycle from persisted Garden evidence.

    Schema-18 Garden state preserves authoritative schema-17 onboarding
    progress. The separate add-on
    preference is consulted only by legacy callers that have no persisted
    progress object, and can never make an empty or merely planted garden look
    nurtured.
    """
    persisted = getattr(garden_state, "onboarding", None)
    persisted_step = getattr(persisted, "step", None)
    if isinstance(persisted_step, str):
        try:
            persisted_step = OnboardingStep(persisted_step)
        except ValueError:
            persisted_step = None
    if isinstance(persisted_step, OnboardingStep):
        projections = {
            OnboardingStep.INTRODUCTION: (
                OnboardingState.NO_STARTER,
                "No plant selected",
                "Choose starter",
                False,
                False,
                1,
            ),
            OnboardingStep.NURSERY: (
                OnboardingState.STARTER_SELECTED,
                "Choose a starter",
                "Choose starter",
                False,
                False,
                2,
            ),
            OnboardingStep.CONFIRMATION: (
                OnboardingState.STARTER_SELECTED,
                "Starter selected",
                "Continue",
                False,
                False,
                3,
            ),
            OnboardingStep.PLACEMENT: (
                OnboardingState.STARTER_SELECTED,
                "Ready to place",
                "Place starter",
                False,
                False,
                4,
            ),
            OnboardingStep.NURTURE: (
                OnboardingState.STARTER_PLANTED_NOT_NURTURED,
                "Ready to nurture",
                "Nurture",
                False,
                False,
                5,
            ),
            OnboardingStep.COMPLETION: (
                OnboardingState.NURTURED_PLANT_ASSIGNED,
                "Nurtured plant",
                "Explore Garden",
                True,
                False,
                6,
            ),
            OnboardingStep.DONE: (
                OnboardingState.ONBOARDING_COMPLETE,
                "Nurtured plant",
                None,
                True,
                True,
                None,
            ),
        }
        state, label, action, marker, complete, number = projections[persisted_step]
        return OnboardingStateDisplay(
            state,
            label,
            action,
            marker,
            complete,
            step=persisted_step,
            counted_step=number,
        )

    plants = tuple(getattr(garden_state, "plants", ()) or ())
    has_starter = bool(plants) and (
        bool(getattr(garden_state, "starter_selection_complete", False))
        or any(getattr(plant, "slot_index", None) is not None for plant in plants)
    )
    active_id = str(getattr(garden_state, "active_plant_id", "") or "")
    active_is_persisted = bool(active_id) and any(
        str(getattr(plant, "plant_id", "") or "") == active_id
        for plant in plants
    )
    first_nurture_committed = any(
        str(getattr(memory, "kind", "") or "") == "first_nurture"
        or str(getattr(memory, "memory_id", "") or "") == "nurture:first"
        for plant in plants
        for memory in tuple(getattr(plant, "memories", ()) or ())
    )
    version = _nonnegative_int(onboarding_version)

    if not has_starter:
        if starter_selected:
            return OnboardingStateDisplay(
                OnboardingState.STARTER_SELECTED,
                "Selected plant",
                "Plant starter",
                False,
                False,
            )
        return OnboardingStateDisplay(
            OnboardingState.NO_STARTER,
            "No plant selected",
            "Choose starter",
            False,
            False,
        )

    # The durable first-Nurture event wins over a stale add-on preference, so
    # reopening Anki cannot replay onboarding after the Garden commit succeeded.
    if first_nurture_committed:
        return OnboardingStateDisplay(
            OnboardingState.ONBOARDING_COMPLETE,
            "Nurtured plant",
            None,
            True,
            True,
        )

    # Legacy states can contain a valid active assignment without the memory
    # introduced later. It is nurtured, but remains distinct from the durable
    # first-Nurture completion state until the legacy preference confirms it.
    if active_is_persisted:
        if version >= CURRENT_ONBOARDING_VERSION:
            return OnboardingStateDisplay(
                OnboardingState.ONBOARDING_COMPLETE,
                "Nurtured plant",
                None,
                True,
                True,
            )
        return OnboardingStateDisplay(
            OnboardingState.NURTURED_PLANT_ASSIGNED,
            "Nurtured plant",
            None,
            True,
            False,
        )

    return OnboardingStateDisplay(
        OnboardingState.STARTER_PLANTED_NOT_NURTURED,
        "Ready to nurture",
        "Nurture",
        False,
        False,
    )


@dataclass(frozen=True)
class AchievementConditionDisplay:
    label: str
    current: int
    target: int
    value_text: str
    satisfied: bool


@dataclass(frozen=True)
class AchievementProgressDisplay:
    current: int
    target: int
    value_text: str
    criteria_text: str
    completed: bool = False
    conditions: tuple[AchievementConditionDisplay, ...] = ()


def achievement_progress_display(achievement: Any, state: Any) -> AchievementProgressDisplay:
    """Project achievement progress without regressing completed cards.

    Known one-time achievements have immutable thresholds. Once unlocked, the
    satisfied thresholds are a valid derived completion snapshot even when the
    current Anki day has reset its counters.
    """
    stats = getattr(state, "daily_stats", None)
    reviewed = _nonnegative_int(getattr(stats, "reviewed", 0))
    wrong = _nonnegative_int(getattr(stats, "wrong", 0))
    accuracy = _percentage(getattr(stats, "accuracy", 0.0))
    achievement_id = str(getattr(achievement, "achievement_id", "") or "")
    completed = bool(getattr(achievement, "unlocked", False))

    definitions: dict[str, tuple[int, int, str, str]] = {
        "streak_7": (
            _nonnegative_int(getattr(state, "streak_days", 0)),
            7,
            "Anki days",
            "Answer at least one card on 7 Anki days in a row.",
        ),
        "streak_30": (
            _nonnegative_int(getattr(state, "streak_days", 0)),
            30,
            "Anki days",
            "Answer at least one card on 30 Anki days in a row.",
        ),
        "reviews_100_day": (
            reviewed,
            100,
            "card answers",
            "Record 100 card answers in one Anki day.",
        ),
        "reviews_1000_total": (
            _nonnegative_int(getattr(state, "total_reviews", 0)),
            1_000,
            "card answers",
            "Record 1,000 total card answers.",
        ),
        "retention_90": (
            accuracy,
            90,
            "% accuracy",
            "Reach 90% accuracy after at least 20 card answers today.",
        ),
        "retention_100": (
            reviewed if wrong == 0 else 0,
            30,
            "card answers",
            "Complete 30 card answers today without choosing Again.",
        ),
        "all_due_done": (
            1 if bool(getattr(stats, "completed_due_cards", False)) else 0,
            1,
            "complete",
            "Finish all due cards in the collection today.",
        ),
        "no_lapse": (
            reviewed if wrong == 0 else 0,
            40,
            "card answers",
            "Complete 40 card answers today without choosing Again.",
        ),
    }
    current, target, unit, criteria = definitions.get(
        achievement_id,
        (
            int(round(float(getattr(achievement, "progress", 0.0) or 0.0) * 100)),
            100,
            "%",
            str(getattr(achievement, "description", "") or ""),
        ),
    )
    current = _nonnegative_int(current)
    target = max(1, _nonnegative_int(target))
    if completed:
        current = target

    conditions: tuple[AchievementConditionDisplay, ...] = ()
    if achievement_id == "retention_90":
        condition_accuracy = 90 if completed else accuracy
        condition_answers = 20 if completed else reviewed
        conditions = (
            AchievementConditionDisplay(
                "Accuracy",
                condition_accuracy,
                90,
                f"{condition_accuracy}% / 90%",
                condition_accuracy >= 90,
            ),
            AchievementConditionDisplay(
                "Anki card answers",
                condition_answers,
                20,
                f"{condition_answers:,} / 20",
                condition_answers >= 20,
            ),
        )
        value_text = (
            f"{condition_accuracy} of 90% accuracy; "
            f"{condition_answers:,} of 20 card answers"
        )
    elif achievement_id == "all_due_done":
        value_text = "1 of 1 complete" if current else "0 of 1 complete"
    else:
        value_text = f"{current:,} of {target:,} {unit}"

    return AchievementProgressDisplay(
        current,
        target,
        value_text,
        criteria,
        completed,
        conditions,
    )


class StreakPresentationState(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    AT_RISK = "atRisk"
    ENDED = "ended"


@dataclass(frozen=True)
class StreakPresentation:
    state: StreakPresentationState
    current_days: int
    status_label: str
    message: str
    semantic: str
    previous_days: int = 0
    missed_day: date | None = None


def streak_presentation(
    streak_days: Any,
    last_active_day: Any,
    reviewed_today: Any,
    *,
    today: date | None = None,
) -> StreakPresentation:
    """Return date-authoritative streak presentation without mutating state."""
    current_day = today or date.today()
    last_day = _date_value(last_active_day)
    days = _nonnegative_int(streak_days)
    reviewed = _nonnegative_int(reviewed_today)

    if reviewed > 0 or last_day == current_day:
        active_days = max(1, days)
        return StreakPresentation(
            StreakPresentationState.ACTIVE,
            active_days,
            "Active",
            "",
            "success",
        )

    if last_day == current_day - timedelta(days=1) and days > 0:
        return StreakPresentation(
            StreakPresentationState.AT_RISK,
            days,
            "At risk",
            "Answer an Anki card today to continue your streak.",
            "warning",
        )

    if last_day is not None:
        missed_day = last_day + timedelta(days=1) if last_day < current_day else None
        return StreakPresentation(
            StreakPresentationState.ENDED,
            0,
            "Streak ended",
            "Answer an Anki card to begin a new streak.",
            "missed",
            previous_days=days,
            missed_day=missed_day,
        )

    return StreakPresentation(
        StreakPresentationState.NEW,
        0,
        "Start today",
        "Answer an Anki card to begin a new streak.",
        "start",
    )


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _percentage(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value or 0.0) * 100))))
    except (TypeError, ValueError, OverflowError):
        return 0


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None
