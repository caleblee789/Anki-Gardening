from __future__ import annotations

import pytest

from ankigarden.growth import (
    GrowthChargeStatus,
    GrowthChargeTargetState,
    project_growth_charge_application,
    stage_progress,
)


@pytest.mark.parametrize(
    ("boundary", "before_stage", "at_stage"),
    [
        (400, "seed", "sprout"),
        (2_000, "sprout", "young"),
        (6_000, "young", "mature"),
        (15_000, "mature", "flowering"),
        (35_000, "flowering", "rare"),
    ],
)
def test_every_release_stage_boundary_is_exact(
    boundary: int,
    before_stage: str,
    at_stage: str,
) -> None:
    assert stage_progress(boundary - 1).stage == before_stage
    assert stage_progress(boundary).stage == at_stage


def test_growth_charge_projects_350_to_450_and_seed_to_sprout_exactly() -> None:
    projection = project_growth_charge_application(350, 100, 2)

    assert projection.status is GrowthChargeStatus.READY
    assert (projection.current_growth, projection.projected_growth) == (350, 450)
    assert (projection.current_stage, projection.projected_stage) == (
        "seed",
        "sprout",
    )
    assert projection.completed_stages == ("sprout",)
    assert projection.will_transition
    assert (projection.inventory_before, projection.inventory_after) == (2, 1)
    assert (projection.stage_points_after, projection.stage_goal_after) == (
        50,
        1_600,
    )
    assert projection.next_stage == "young"
    assert projection.conserved


def test_growth_charge_no_transition_keeps_stage_local_progress_exact() -> None:
    projection = project_growth_charge_application(600, 100, 2)

    assert (projection.current_stage, projection.projected_stage) == (
        "sprout",
        "sprout",
    )
    assert not projection.will_transition
    assert projection.completed_stages == ()
    assert (projection.stage_points_after, projection.stage_goal_after) == (
        300,
        1_600,
    )


def test_growth_charge_rejects_full_bloom_without_consuming_inventory() -> None:
    projection = project_growth_charge_application(35_000, 100, 2)

    assert projection.status is GrowthChargeStatus.TARGET_INVALID
    assert projection.target_state is GrowthChargeTargetState.FULLY_GROWN
    assert projection.projected_growth == 35_000
    assert projection.inventory_after == 2
    assert projection.applied_growth == projection.overflow_growth == 0
    assert projection.unconsumed_growth == 100
    assert projection.conserved


def test_growth_charge_preserves_overflow_for_engine_routing() -> None:
    projection = project_growth_charge_application(34_950, 100, 2)

    assert projection.status is GrowthChargeStatus.READY
    assert projection.projected_growth == 35_000
    assert projection.projected_stage == "rare"
    assert projection.applied_growth == 50
    assert projection.overflow_growth == 50
    assert projection.granted_growth == 100
    assert projection.inventory_after == 1
    assert projection.conserved
