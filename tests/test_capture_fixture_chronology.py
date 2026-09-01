from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from ankigarden.capture.fixtures import (
    CAPTURE_DATE,
    STREAK_MILESTONE_DATES,
    achievement_completion_schedule,
    representative_collection_inventory_plan,
    validate_achievement_completion_schedule,
)
from ankigarden.collectibles import collection_entry_views
from ankigarden.models.state import (
    CURRENT_CATALOG_SPECIES_ORDER,
    MAX_GARDEN_SLOTS,
    GardenState,
)
from ankigarden.presentation import project_collection


@pytest.mark.parametrize(
    ("achievement_id", "streak_days"),
    (
        ("streak_7", 7),
        ("streak_30", 30),
        ("streak_100", 100),
        ("streak_365", 365),
    ),
)
def test_streak_fixture_uses_one_plausible_365_day_run(
    achievement_id: str,
    streak_days: int,
) -> None:
    streak_start = date(2025, 8, 29)
    assert STREAK_MILESTONE_DATES[achievement_id] == (
        streak_start + timedelta(days=streak_days - 1)
    )
    assert STREAK_MILESTONE_DATES[achievement_id] <= CAPTURE_DATE


def test_capture_achievement_schedule_is_distinct_and_never_future_dated() -> None:
    ids = (
        "first_growth",
        "streak_7",
        "collector",
        "streak_30",
        "streak_100",
        "streak_365",
    )
    schedule = achievement_completion_schedule(ids)

    assert CAPTURE_DATE == date(2026, 8, 28)
    assert set(schedule) == set(ids)
    assert len(set(schedule.values())) == len(schedule)
    assert max(schedule.values()) == CAPTURE_DATE
    assert validate_achievement_completion_schedule(schedule)


def test_runtime_capture_fixture_uses_the_shared_frozen_schedule() -> None:
    runtime = (
        Path(__file__).resolve().parents[1]
        / "ankigarden"
        / "capture"
        / "runtime.py"
    ).read_text("utf-8")

    assert "achievement_completion_schedule(" in runtime
    assert "validate_achievement_completion_schedule(" in runtime
    assert "date(2026, 8, 28)" not in runtime


def test_representative_collection_fixture_derives_truthful_30_of_39() -> None:
    state = GardenState()
    state.unlocked_species = list(CURRENT_CATALOG_SPECIES_ORDER)
    state.unlocked_slots = MAX_GARDEN_SLOTS
    plan = representative_collection_inventory_plan()
    state.inventory["garden_features"] = list(plan["garden_features"])
    state.inventory["scenery"] = list(plan["scenery"])
    state.consumables.update(dict(plan["consumables"]))

    views = collection_entry_views(state)
    projection = project_collection(state)

    assert len(views) == 39
    assert sum(1 for view in views if view.owned) == 30
    assert projection.species_text == "10 of 10 species discovered"
    assert (
        projection.collection_entries_text
        == "30 of 39 collection entries discovered"
    )
    assert {
        view.definition.source_id
        for view in views
        if view.definition.category == "growth_items" and not view.owned
    } == {
        "fertilizer_basic",
        "fertilizer_quality",
        "fertilizer_premium",
    }


def test_collection_purchase_fixture_truthfully_advances_29_to_30_entries() -> None:
    state = GardenState()
    state.unlocked_slots = MAX_GARDEN_SLOTS
    state.unlocked_species = [
        species
        for species in CURRENT_CATALOG_SPECIES_ORDER
        if species != "sunflower"
    ]
    plan = representative_collection_inventory_plan()
    state.inventory["garden_features"] = list(plan["garden_features"])
    state.inventory["scenery"] = list(plan["scenery"])
    state.consumables.update(dict(plan["consumables"]))

    before = project_collection(state)
    state.unlocked_species.append("sunflower")
    after = project_collection(state)

    assert before.species_text == "9 of 10 species discovered"
    assert before.collection_entries_text == "29 of 39 collection entries discovered"
    assert after.species_text == "10 of 10 species discovered"
    assert after.collection_entries_text == "30 of 39 collection entries discovered"
