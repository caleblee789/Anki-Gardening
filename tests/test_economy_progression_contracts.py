from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from uuid import UUID

import pytest


os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden import balance_catalog  # noqa: E402
from ankigarden.economy_progression import (  # noqa: E402
    LANDMARK_GROWTH_COST_UNITS,
    LANDMARK_ORDER,
    MASTERY_GROWTH_COST_UNITS,
    MASTERY_RANK_ORDER,
    ContributionMode,
    GrowthProjectAction,
    GrowthProjectConfirmation,
    GrowthProjectRequest,
    GrowthTargetRef,
    GrowthTargetType,
    LandmarkAction,
    LandmarkProjectSnapshot,
    LandmarkRequest,
    MasteryRequest,
    MasterySnapshot,
    ProgressionDisposition,
    canonical_request_id,
    build_growth_projects_snapshot,
    growth_project_outcome_from_dict,
    landmark_snapshot,
    mastery_snapshot,
    next_landmark_id,
    next_mastery_rank_id,
    project_landmark_request,
    project_growth_project_request,
    project_mastery_request,
    quote_landmark_request,
    quote_growth_project_request,
    quote_mastery_request,
    request_fingerprint,
)


def request_id(number: int) -> str:
    return str(UUID(int=number))


def landmark_request(
    number: int,
    action: LandmarkAction,
    landmark_id: str,
    growth_units: int = 0,
) -> LandmarkRequest:
    return LandmarkRequest(request_id(number), action, landmark_id, growth_units)


def mastery_request(
    number: int,
    species_id: str,
    rank_id: str,
) -> MasteryRequest:
    return MasteryRequest(request_id(number), species_id, rank_id)


def test_cost_projections_use_exact_hundredth_growth_units() -> None:
    assert LANDMARK_ORDER == tuple(
        item.landmark_id.value for item in balance_catalog.LANDMARKS
    )
    assert LANDMARK_GROWTH_COST_UNITS == {
        item.landmark_id.value: item.growth_cost * 100
        for item in balance_catalog.LANDMARKS
    }
    assert MASTERY_RANK_ORDER == ("bronze", "silver", "gold", "iridescent")
    assert MASTERY_GROWTH_COST_UNITS == {
        "bronze": 2_500_000,
        "silver": 5_000_000,
        "gold": 10_000_000,
        "iridescent": 20_000_000,
    }
    assert all(isinstance(value, int) for value in LANDMARK_GROWTH_COST_UNITS.values())
    assert all(isinstance(value, int) for value in MASTERY_GROWTH_COST_UNITS.values())


def test_landmarks_reject_out_of_order_selection_and_incomplete_completion() -> None:
    initial = LandmarkProjectSnapshot()
    skip = landmark_request(1, LandmarkAction.SELECT, "birdbath_terrace")
    skip_quote = quote_landmark_request(initial, skip)
    assert skip_quote.disposition is ProgressionDisposition.INVALID_ORDER
    assert not skip_quote.can_apply
    assert project_landmark_request(initial, skip).snapshot is initial

    selected = project_landmark_request(
        initial,
        landmark_request(2, LandmarkAction.SELECT, "mossy_stone_path"),
    ).snapshot
    premature = landmark_request(3, LandmarkAction.COMPLETE, "mossy_stone_path")
    quote = quote_landmark_request(selected, premature, available_coins=10_000)
    assert quote.disposition is ProgressionDisposition.NOT_READY
    assert not quote.can_apply


def test_landmark_contribution_ready_completion_and_duplicate_projection() -> None:
    selected_outcome = project_landmark_request(
        LandmarkProjectSnapshot(),
        landmark_request(10, LandmarkAction.SELECT, "mossy_stone_path"),
    )
    assert selected_outcome.applied
    selected = selected_outcome.snapshot
    assert selected.selected_landmark_id == "mossy_stone_path"
    assert next_landmark_id(selected) == "mossy_stone_path"

    contribution = landmark_request(
        11,
        LandmarkAction.CONTRIBUTE,
        "mossy_stone_path",
        1_000_000,
    )
    insufficient = project_landmark_request(
        selected,
        contribution,
        available_growth_units=999_999,
    )
    assert insufficient.disposition is ProgressionDisposition.INSUFFICIENT_GROWTH
    assert not insufficient.applied
    assert insufficient.snapshot is selected

    partial = project_landmark_request(
        selected,
        contribution,
        available_growth_units=1_000_000,
    )
    assert partial.growth_spent_units == 1_000_000
    assert partial.snapshot.contributed_growth_units == 1_000_000
    assert not partial.snapshot.ready_to_complete

    # A request larger than the remainder is safely capped to the exact cost.
    finish = project_landmark_request(
        partial.snapshot,
        landmark_request(
            12,
            LandmarkAction.CONTRIBUTE,
            "mossy_stone_path",
            2_000_000,
        ),
        available_growth_units=1_500_000,
    )
    assert finish.growth_spent_units == 1_500_000
    assert finish.snapshot.contributed_growth_units == 2_500_000
    assert finish.snapshot.ready_to_complete

    complete_request = landmark_request(
        13,
        LandmarkAction.COMPLETE,
        "mossy_stone_path",
    )
    no_coins = project_landmark_request(
        finish.snapshot,
        complete_request,
        available_coins=249,
    )
    assert no_coins.disposition is ProgressionDisposition.INSUFFICIENT_COINS
    assert not no_coins.applied
    assert no_coins.snapshot.ready_to_complete

    completed = project_landmark_request(
        finish.snapshot,
        complete_request,
        available_coins=250,
    )
    assert completed.disposition is ProgressionDisposition.APPLIED
    assert completed.applied
    assert completed.coins_spent == 250
    assert completed.growth_spent_units == 0
    assert completed.snapshot == LandmarkProjectSnapshot(
        completed_landmark_ids=("mossy_stone_path",),
        displayed_landmark_id="mossy_stone_path",
    )

    duplicate = project_landmark_request(
        completed.snapshot,
        landmark_request(14, LandmarkAction.COMPLETE, "mossy_stone_path"),
        available_coins=999,
    )
    assert duplicate.disposition is ProgressionDisposition.ALREADY_COMPLETE
    assert not duplicate.applied
    assert duplicate.coins_spent == duplicate.growth_spent_units == 0
    assert duplicate.snapshot is completed.snapshot

    # Selecting the next project preserves completed and displayed history.
    next_project = project_landmark_request(
        completed.snapshot,
        landmark_request(15, LandmarkAction.SELECT, "birdbath_terrace"),
    )
    assert next_project.snapshot.completed_landmark_ids == ("mossy_stone_path",)
    assert next_project.snapshot.displayed_landmark_id == "mossy_stone_path"
    assert next_project.snapshot.selected_landmark_id == "birdbath_terrace"


def test_landmark_snapshot_validation_rejects_corrupt_sequence_state() -> None:
    with pytest.raises(ValueError, match="sequence prefix"):
        LandmarkProjectSnapshot(completed_landmark_ids=("birdbath_terrace",))
    with pytest.raises(ValueError, match="duplicates"):
        LandmarkProjectSnapshot(
            completed_landmark_ids=("mossy_stone_path", "mossy_stone_path")
        )
    with pytest.raises(ValueError, match="ready_to_complete"):
        LandmarkProjectSnapshot(
            selected_landmark_id="mossy_stone_path",
            contributed_growth_units=2_500_000,
            ready_to_complete=False,
        )
    with pytest.raises(ValueError, match="displayed Landmark"):
        LandmarkProjectSnapshot(displayed_landmark_id="mossy_stone_path")
    with pytest.raises(TypeError):
        landmark_snapshot(completed_landmark_ids="mossy_stone_path")


def test_mastery_requires_each_species_rank_in_order_and_both_resources() -> None:
    initial = MasterySnapshot()
    assert next_mastery_rank_id(initial, "bonsai") == "bronze"

    silver = mastery_request(20, "bonsai", "silver")
    invalid = quote_mastery_request(
        initial,
        silver,
        available_growth_units=99_000_000,
        available_coins=99_000,
    )
    assert invalid.disposition is ProgressionDisposition.INVALID_ORDER
    assert invalid.next_rank_id == "bronze"

    bronze = mastery_request(21, "bonsai", "bronze")
    growth_short = quote_mastery_request(
        initial,
        bronze,
        available_growth_units=2_499_999,
        available_coins=50,
    )
    assert growth_short.disposition is ProgressionDisposition.INSUFFICIENT_GROWTH
    coin_short = quote_mastery_request(
        initial,
        bronze,
        available_growth_units=2_500_000,
        available_coins=49,
    )
    assert coin_short.disposition is ProgressionDisposition.INSUFFICIENT_COINS

    unlocked = project_mastery_request(
        initial,
        bronze,
        available_growth_units=2_500_000,
        available_coins=50,
    )
    assert unlocked.applied
    assert unlocked.growth_spent_units == 2_500_000
    assert unlocked.coins_spent == 50
    assert unlocked.snapshot.rank_for("bonsai") == "bronze"
    assert next_mastery_rank_id(unlocked.snapshot, "bonsai") == "silver"

    duplicate = project_mastery_request(
        unlocked.snapshot,
        mastery_request(22, "bonsai", "bronze"),
        available_growth_units=99_000_000,
        available_coins=99_000,
    )
    assert duplicate.disposition is ProgressionDisposition.ALREADY_COMPLETE
    assert not duplicate.applied
    assert duplicate.snapshot is unlocked.snapshot
    assert duplicate.growth_spent_units == duplicate.coins_spent == 0

    skipped_gold = quote_mastery_request(
        unlocked.snapshot,
        mastery_request(23, "bonsai", "gold"),
        available_growth_units=99_000_000,
        available_coins=99_000,
    )
    assert skipped_gold.disposition is ProgressionDisposition.INVALID_ORDER

    silver_unlocked = project_mastery_request(
        unlocked.snapshot,
        mastery_request(24, "bonsai", "silver"),
        available_growth_units=5_000_000,
        available_coins=100,
    )
    assert silver_unlocked.snapshot.rank_for("bonsai") == "silver"
    assert silver_unlocked.growth_spent_units == 5_000_000
    assert silver_unlocked.coins_spent == 100

    rose = project_mastery_request(
        silver_unlocked.snapshot,
        mastery_request(25, "rose", "bronze"),
        available_growth_units=2_500_000,
        available_coins=50,
    )
    assert rose.snapshot.to_dict()["highest_rank_by_species"] == {
        "bonsai": "silver",
        "rose": "bronze",
    }


def test_mastery_snapshot_normalizes_order_and_rejects_unknown_entries() -> None:
    snapshot = mastery_snapshot({"rose": "bronze", "bonsai": "silver"})
    assert snapshot.highest_rank_by_species == (
        ("bonsai", "silver"),
        ("rose", "bronze"),
    )
    with pytest.raises(ValueError, match="canonical species order"):
        MasterySnapshot((("rose", "bronze"), ("bonsai", "silver")))
    with pytest.raises(ValueError, match="active catalog species"):
        mastery_snapshot({"fern": "bronze"})
    with pytest.raises(ValueError, match="canonical rank"):
        mastery_snapshot({"bonsai": "diamond"})


def test_canonical_uuid_fingerprints_and_outcomes_are_json_safe() -> None:
    request = landmark_request(
        30,
        LandmarkAction.SELECT,
        "mossy_stone_path",
    )
    assert canonical_request_id(request.request_id) == request.request_id
    assert request.fingerprint == request_fingerprint(request)
    assert request.fingerprint == landmark_request(
        30,
        LandmarkAction.SELECT,
        "mossy_stone_path",
    ).fingerprint
    assert request.fingerprint != landmark_request(
        31,
        LandmarkAction.SELECT,
        "mossy_stone_path",
    ).fingerprint

    outcome = project_landmark_request(LandmarkProjectSnapshot(), request)
    encoded = json.dumps(outcome.to_dict(), sort_keys=True, separators=(",", ":"))
    assert '"disposition":"applied"' in encoded
    assert outcome.to_dict()["request_fingerprint"] == request.fingerprint

    mastery = mastery_request(32, "bonsai", "bronze")
    mastery_outcome = project_mastery_request(
        MasterySnapshot(),
        mastery,
        available_growth_units=2_500_000,
        available_coins=50,
    )
    json.dumps(mastery_outcome.to_dict(), sort_keys=True)
    assert mastery_outcome.request_fingerprint == mastery.fingerprint

    with pytest.raises(ValueError, match="canonical lowercase"):
        LandmarkRequest(
            "123E4567-E89B-12D3-A456-426614174000",
            LandmarkAction.SELECT,
            "mossy_stone_path",
        )
    with pytest.raises(ValueError, match="canonical lowercase"):
        MasteryRequest(request_id(34).replace("-", ""), "bonsai", "bronze")
    with pytest.raises(TypeError):
        LandmarkRequest(request_id(35), "select", "mossy_stone_path")


def test_contracts_and_catalog_indexes_are_immutable() -> None:
    request = landmark_request(40, LandmarkAction.SELECT, "mossy_stone_path")
    with pytest.raises(FrozenInstanceError):
        request.landmark_id = "birdbath_terrace"
    with pytest.raises(TypeError):
        LANDMARK_GROWTH_COST_UNITS["mossy_stone_path"] = 1
    with pytest.raises(TypeError):
        MASTERY_GROWTH_COST_UNITS["bronze"] = 1


def test_cumulative_project_quote_claim_and_idempotency_contract() -> None:
    target = GrowthTargetRef(GrowthTargetType.LANDMARK, "garden_landmark")
    snapshot = build_growth_projects_snapshot(
        state_revision=7,
        stored_balance_units=300_000_000,
        wallet_balance_coins=5_000,
        full_bloom_species=("bonsai",),
    )
    assert snapshot.landmark_track.tiers[0].remaining_growth_units == 2_500_000
    assert snapshot.landmark_track.allowed_actions == ("activate",)
    activate = GrowthProjectRequest(
        request_id(50), 7, GrowthProjectAction.ACTIVATE, target
    )
    selected = project_growth_project_request(snapshot, activate)
    assert selected.applied
    assert selected.snapshot.landmark_track.allowed_actions == ("contribute",)
    assert selected.ledger_identity == f"growth-project:{activate.request_id}"
    assert (selected.state_revision_before, selected.state_revision_after) == (7, 8)
    assert len(selected.catalog_digest) == 64
    assert GrowthProjectConfirmation.from_quote(
        quote_growth_project_request(snapshot, activate)
    ).request_id == activate.request_id

    fund = GrowthProjectRequest(
        request_id(51),
        8,
        GrowthProjectAction.CONTRIBUTE,
        target,
        ContributionMode.MAXIMUM,
    )
    funded = project_growth_project_request(selected.snapshot, fund)
    assert funded.applied
    assert funded.snapshot.landmark_track.growth_units_funded == 247_500_000
    assert funded.snapshot.landmark_track.tiers[-1].funded
    assert not funded.snapshot.landmark_track.tiers[-1].claimed
    assert funded.snapshot.stored_balance_units == 52_500_000

    coin_short_snapshot = build_growth_projects_snapshot(
        state_revision=9,
        stored_balance_units=0,
        wallet_balance_coins=0,
        full_bloom_species=("bonsai",),
        active_target=target,
        active_target_activation_identity=activate.request_id,
        landmark_growth_units_funded=2_500_000,
    )
    coin_short = quote_growth_project_request(
        coin_short_snapshot,
        GrowthProjectRequest(
            request_id(53), 9, GrowthProjectAction.CLAIM, target,
            claim_id="mossy_stone_path",
        ),
    )
    assert coin_short.disposition is ProgressionDisposition.INSUFFICIENT_COINS
    assert coin_short.coin_cost == 250
    assert coin_short.wallet_balance_after_coins == 0

    claim = GrowthProjectRequest(
        request_id(52),
        9,
        GrowthProjectAction.CLAIM,
        target,
        claim_id="mossy_stone_path",
    )
    claimed = project_growth_project_request(funded.snapshot, claim)
    assert claimed.applied
    assert claimed.coins_spent == 250
    assert claimed.stored_balance_delta_units == 0
    assert claimed.snapshot.landmark_track.growth_units_funded == 247_500_000
    assert claimed.snapshot.landmark_track.highest_claimed_id == "mossy_stone_path"
    assert claimed.catalog_digest == quote_growth_project_request(
        funded.snapshot, claim
    ).catalog_digest
    assert growth_project_outcome_from_dict(claimed.to_dict()) == claimed
