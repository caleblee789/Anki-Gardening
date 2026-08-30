from __future__ import annotations

from ankigarden.growth import (
    GrowthChargeStatus,
    GrowthChargeTargetState,
    project_growth_charge_application,
)


def test_growth_charge_projects_450_to_550_and_seed_to_sprout_exactly() -> None:
    projection = project_growth_charge_application(450, 100, 2)

    assert projection.status is GrowthChargeStatus.READY
    assert (projection.current_growth, projection.projected_growth) == (450, 550)
    assert (projection.current_stage, projection.projected_stage) == (
        "seed",
        "sprout",
    )
    assert projection.completed_stages == ("sprout",)
    assert projection.will_transition
    assert (projection.inventory_before, projection.inventory_after) == (2, 1)
    assert (projection.stage_points_after, projection.stage_goal_after) == (
        50,
        2_000,
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
        200,
        2_000,
    )


def test_growth_charge_rejects_full_bloom_without_consuming_inventory() -> None:
    projection = project_growth_charge_application(50_000, 100, 2)

    assert projection.status is GrowthChargeStatus.TARGET_INVALID
    assert projection.target_state is GrowthChargeTargetState.FULLY_GROWN
    assert projection.projected_growth == 50_000
    assert projection.inventory_after == 2
    assert projection.applied_growth == projection.overflow_growth == 0
    assert projection.unconsumed_growth == 100
    assert projection.conserved


def test_growth_charge_preserves_overflow_for_engine_routing() -> None:
    projection = project_growth_charge_application(49_950, 100, 2)

    assert projection.status is GrowthChargeStatus.READY
    assert projection.projected_growth == 50_000
    assert projection.projected_stage == "rare"
    assert projection.applied_growth == 50
    assert projection.overflow_growth == 50
    assert projection.granted_growth == 100
    assert projection.inventory_after == 1
    assert projection.conserved

