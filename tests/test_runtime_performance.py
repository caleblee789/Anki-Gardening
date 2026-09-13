from __future__ import annotations

import json

import pytest

from ankigarden.performance import RuntimePerformanceRecorder
from scripts.profile_runtime import _comparison_row


def test_runtime_performance_recorder_is_disabled_without_overhead() -> None:
    calls: list[bool] = []
    recorder = RuntimePerformanceRecorder(
        enabled=False,
        clock=lambda: calls.append(True) or 1.0,
    )

    marker = recorder.begin()
    recorder.answer_stage("action", "answer-1")
    recorder.answer_stage("feedback_painted", "answer-1")
    recorder.finish("review.answer", marker)

    assert marker is None
    assert calls == []
    assert recorder.summaries() == ()


def test_runtime_performance_recorder_bounds_and_summarizes_samples() -> None:
    recorder = RuntimePerformanceRecorder(enabled=True, max_samples=3)
    for value in (1.0, 2.0, 3.0, 4.0):
        recorder.record("dashboard.refresh", value)

    assert recorder.samples("dashboard.refresh") == (2.0, 3.0, 4.0)
    summary = recorder.summary("dashboard.refresh")
    assert summary.count == 3
    assert summary.median_ms == 3.0
    assert summary.p95_ms == 4.0
    assert summary.maximum_ms == 4.0
    for i in range(1000):
        recorder.answer_stage("action", str(i))
    events = recorder.payload()["answer_events"]
    assert len(events) <= 3 * 24
    assert events[-1]["answer_id"] == "999"
    recorder.answer_stage("deferred", "revlog-999")
    recorder.answer_stage("hook_finished")
    recorder.answer_stage("action", "1000")
    recorder.answer_stage("committed", "commit-999", related_answer_id="revlog-999")
    recorder.answer_stage("hook_finished")
    recorder.answer_stage("feedback_painted", "commit-999")
    assert recorder.payload()["answer_events"][-1]["action_id"] == "999"
    assert len(recorder._answer_actions) <= 6


def test_runtime_performance_export_is_absolute_and_atomic(tmp_path) -> None:
    recorder = RuntimePerformanceRecorder(enabled=True)
    recorder.record("home.render", 12.5)

    with pytest.raises(ValueError, match="absolute"):
        recorder.write_json("relative.json")

    output = recorder.write_json(tmp_path / "runtime.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["operations"] == [{
        "count": 1,
        "maximum_ms": 12.5,
        "median_ms": 12.5,
        "name": "home.render",
        "p95_ms": 12.5,
    }]
    assert not (tmp_path / "runtime.json.tmp").exists()


def test_runtime_comparison_marks_unexercised_candidate_paths_missing() -> None:
    baseline = {
        "count": 5,
        "median_ms": 10.0,
        "p95_ms": 20.0,
    }

    assert _comparison_row("review.answer", None, baseline) == (
        "review.answer",
        "0",
        "missing",
        "missing",
        "n/a",
        "n/a",
    )
