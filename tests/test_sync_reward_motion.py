from __future__ import annotations

import inspect

from ankigarden.models.sync_reward import SyncRewardSummary
from ankigarden.ui.sync_reward_summary import (
    SYNC_REWARD_FULL_BLOOM_PULSE_MS,
    SYNC_REWARD_METRIC_ANIMATION_MS,
    SyncRewardSummaryCard,
    _format_metric_number,
    _parse_metric_number,
    sync_reward_motion_plan,
)


def _summary(**changes) -> SyncRewardSummary:
    payload = {
        "batch_id": "batch-a",
        "anki_days": ("2026-08-29",),
        "eligible_answer_count": 1_234,
        "growth_total_units": 123_450,
        "garden_coin_delta": 12,
        "plant_growth": ({
            "plant_id": "bluebell",
            "plant_name": "Bluebell",
            "growth_delta_units": 123_450,
            "stage_before": "mature",
            "stage_after": "flowering",
            "stage_progress_before": 55,
            "stage_progress_after": 68,
        },),
        "progression_events": ({
            "event_id": "wisteria:bloom",
            "plant_id": "wisteria",
            "event_type": "full_bloom",
            "display_text": "Wisteria reached Full Bloom",
        },),
        "source_batch_ids": ("batch-a",),
    }
    payload.update(changes)
    return SyncRewardSummary(**payload)


def test_metric_number_format_preserves_sign_grouping_and_decimal_precision() -> None:
    parsed = _parse_metric_number("+12,345.6")

    assert parsed == (123_456, 1, True)
    assert _format_metric_number(*parsed) == "+12,345.6"
    assert _format_metric_number(0, 1, True) == "+0.0"
    assert _format_metric_number(-98_765, 1, False) == "-9,876.5"


def test_initial_motion_plan_counts_from_zero_and_emphasizes_full_bloom_once() -> None:
    plan = sync_reward_motion_plan(_summary())
    metrics = {motion.label: motion for motion in plan.metrics}

    assert set(metrics) == {"Card answers", "Growth", "Garden Coins"}
    assert metrics["Card answers"].start_scaled == 0
    assert metrics["Card answers"].final_text == "1,234"
    assert metrics["Growth"].start_scaled == 0
    assert metrics["Growth"].final_text == "+1,234.5"
    assert metrics["Growth"].decimal_places == 1
    assert metrics["Growth"].show_plus is True
    assert metrics["Garden Coins"].final_text == "+12"
    assert [motion.plant_key for motion in plan.plant_progress] == [
        "wisteria",
        "bluebell",
    ]
    assert plan.plant_progress[0].start_value == 0
    assert plan.plant_progress[0].start_stage == ""
    assert plan.plant_progress[1].start_value == 55
    assert plan.plant_progress[1].start_stage == "mature"
    assert plan.full_bloom_event_keys == frozenset({"wisteria:bloom"})


def test_update_motion_plan_contains_only_changed_metrics_progress_and_events() -> None:
    previous = _summary()
    updated = _summary(
        eligible_answer_count=1_242,
        garden_coin_delta=20,
        plant_growth=({
            "plant_id": "bluebell",
            "plant_name": "Bluebell",
            "growth_delta_units": 123_450,
            "stage_before": "mature",
            "stage_after": "flowering",
            "stage_progress_before": 55,
            "stage_progress_after": 74,
        }, {
            "plant_id": "fern",
            "plant_name": "Fern",
            "growth_delta_units": 100,
            "stage_before": "young",
            "stage_after": "young",
            "stage_progress_before": 10,
            "stage_progress_after": 15,
        }),
        progression_events=(
            previous.progression_events[0],
            {
                "event_id": "fern:bloom",
                "plant_id": "fern",
                "event_type": "full_bloom",
                "display_text": "Fern reached Full Bloom",
            },
        ),
    )

    plan = sync_reward_motion_plan(updated, previous=previous)
    metrics = {motion.label: motion for motion in plan.metrics}
    progress = {motion.plant_key: motion for motion in plan.plant_progress}

    assert set(metrics) == {"Card answers", "Garden Coins"}
    assert metrics["Card answers"].start_scaled == 1_234
    assert metrics["Card answers"].end_scaled == 1_242
    assert metrics["Garden Coins"].start_scaled == 12
    assert metrics["Garden Coins"].end_scaled == 20
    assert "Growth" not in metrics
    assert set(progress) == {"bluebell", "fern"}
    assert progress["bluebell"].start_value == 68
    assert progress["bluebell"].start_stage == "flowering"
    assert progress["fern"].start_value == 10
    assert plan.full_bloom_event_keys == frozenset({"fern:bloom"})


def test_unchanged_update_has_no_motion_to_replay() -> None:
    summary = _summary()
    plan = sync_reward_motion_plan(summary, previous=summary)

    assert plan.metrics == ()
    assert plan.plant_progress == ()
    assert plan.full_bloom_event_keys == frozenset()


def test_sync_reward_motion_is_bounded_one_shot_and_reduced_motion_guarded() -> None:
    show_source = inspect.getsource(SyncRewardSummaryCard.showEvent)
    metric_source = inspect.getsource(SyncRewardSummaryCard._metric_tile)
    plant_source = inspect.getsource(SyncRewardSummaryCard._plant_row)
    bloom_source = inspect.getsource(
        SyncRewardSummaryCard._start_full_bloom_emphasis
    )

    assert SYNC_REWARD_METRIC_ANIMATION_MS == 360
    assert SYNC_REWARD_FULL_BLOOM_PULSE_MS == 520
    assert SYNC_REWARD_FULL_BLOOM_PULSE_MS <= 600
    assert "self._entrance_started" in show_source
    assert "not self._animations_enabled" in show_source
    assert "fade.setDuration(180)" in show_source
    assert "QPoint(0, 4)" in show_source
    assert "if not self._animations_enabled or motion is None" in metric_source
    assert "QVariantAnimation(self)" in metric_source
    assert "animation.setLoopCount(1)" in metric_source
    assert "motion.final_text" in metric_source
    assert "self._animations_enabled and motion is not None" in plant_source
    assert "progress.setValue(progress_target)" in plant_source
    assert "QSequentialAnimationGroup" in plant_source
    assert "if not self._animations_enabled" in bloom_source
    assert "animation.setKeyValueAt(0.5, 1.0)" in bloom_source
    assert "animation.setLoopCount(1)" in bloom_source


def test_model_updates_diff_motion_but_disclosure_rebuilds_without_it() -> None:
    update_source = inspect.getsource(SyncRewardSummaryCard.update_model)
    disclosure_source = inspect.getsource(SyncRewardSummaryCard._toggle_expanded)

    assert "previous = self._summary" in update_source
    assert "sync_reward_motion_plan(summary, previous=previous)" in update_source
    assert "self._rebuild_body(motion=motion)" in update_source
    assert "sync_reward_motion_plan" not in disclosure_source
    assert "self._rebuild_body()" in disclosure_source
