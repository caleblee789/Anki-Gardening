from __future__ import annotations

from ankigarden.models.sync_reward import (
    SyncRewardSummary,
    SyncPlantCheckpoint,
    SyncPlantResult,
    prioritized_sync_plant_results,
)


def _checkpoint(event_id: str, percent: int, stage: str) -> SyncPlantCheckpoint:
    return SyncPlantCheckpoint(
        event_id=event_id,
        percent=percent,
        stage_name=stage,
        display_text=f"{percent}% toward {stage} reached",
    )


def test_stage_change_supersedes_prior_stage_checkpoint() -> None:
    result = SyncPlantResult(
        plant_id="rose",
        display_name="Rose Plant",
        stage_before="mature",
        stage_after="flowering",
        stage_progress_after=68,
        next_stage="rare",
        checkpoints=(_checkpoint("checkpoint:rose:75:flowering", 75, "Flowering"),),
        stage_event_id="stage:rose:flowering",
        stage_event_text="Rose Plant reached Flowering",
    )

    assert result.canonical_checkpoints == ()
    assert result.primary_milestone.kind == "stage_change"
    assert result.primary_milestone.display_text == "Rose Plant reached Flowering"
    assert result.to_dict()["checkpoints"] == []


def test_only_highest_reached_checkpoint_in_current_stage_survives() -> None:
    result = SyncPlantResult(
        plant_id="rose",
        display_name="Rose Plant",
        stage_before="flowering",
        stage_after="flowering",
        stage_progress_after=68,
        next_stage="rare",
        checkpoints=(
            _checkpoint("old-stage", 75, "Flowering"),
            _checkpoint("future-checkpoint", 75, "Full Bloom"),
            _checkpoint("reached-25", 25, "Full Bloom"),
            _checkpoint("reached-50", 50, "Full Bloom"),
        ),
    )

    assert [item.event_id for item in result.canonical_checkpoints] == [
        "reached-50"
    ]
    assert result.primary_milestone.kind == "checkpoint"
    assert result.primary_milestone.checkpoint_percent == 50


def test_full_bloom_has_deterministic_priority_over_other_milestones() -> None:
    growth = SyncPlantResult("dahlia", "Dahlia Plant", growth_delta_units=100)
    checkpoint = SyncPlantResult(
        "rose",
        "Rose Plant",
        stage_before="flowering",
        stage_after="flowering",
        stage_progress_after=50,
        next_stage="rare",
        checkpoints=(_checkpoint("checkpoint", 50, "Full Bloom"),),
    )
    stage = SyncPlantResult(
        "bonsai",
        "Bonsai Plant",
        stage_before="seed",
        stage_after="sprout",
    )
    bloom = SyncPlantResult(
        "wisteria",
        "Wisteria Plant",
        stage_before="flowering",
        stage_after="rare",
        fully_grown=True,
        full_bloom=True,
    )

    ordered = prioritized_sync_plant_results((growth, checkpoint, stage, bloom))

    assert [item.primary_milestone.kind for item in ordered] == [
        "full_bloom",
        "stage_change",
        "checkpoint",
        "growth",
    ]
    assert ordered[0].canonical_checkpoints == ()

    summary = SyncRewardSummary(
        batch_id="priority-batch",
        anki_days=("2026-08-29",),
        eligible_answer_count=4,
        growth_total_units=400,
        plant_results=(growth, checkpoint, stage, bloom),
    )
    assert [
        item.primary_milestone.kind
        for item in summary.grouped_plant_results
    ] == [
        "full_bloom",
        "stage_change",
        "checkpoint",
        "growth",
    ]
