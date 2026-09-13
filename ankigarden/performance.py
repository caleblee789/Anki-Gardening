from __future__ import annotations

"""Opt-in, bounded runtime timing samples for local performance diagnostics.

The learner-facing add-on never enables this recorder on its own.  A developer
can set ``ANKI_GARDEN_PERF_TRACE=1`` and, optionally,
``ANKI_GARDEN_PERF_OUTPUT=/absolute/path/to/samples.json`` before launching a
disposable Anki profile.  Keeping the recorder here (rather than in capture
code) lets the exact production package be measured without changing behavior.
"""

import atexit
import json
import math
import os
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Callable, Deque, Iterable


PERFORMANCE_TRACE_ENV = "ANKI_GARDEN_PERF_TRACE"
PERFORMANCE_OUTPUT_ENV = "ANKI_GARDEN_PERF_OUTPUT"
DEFAULT_MAX_SAMPLES = 256


def _environment_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class PerformanceSummary:
    name: str
    count: int
    median_ms: float
    p95_ms: float
    maximum_ms: float


class RuntimePerformanceRecorder:
    """Collect a bounded number of monotonic timing samples per operation."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        max_samples: int = DEFAULT_MAX_SAMPLES,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.enabled = (
            _environment_flag(PERFORMANCE_TRACE_ENV)
            if enabled is None
            else bool(enabled)
        )
        self.max_samples = max(1, int(max_samples))
        self._clock = clock
        self._samples: dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.max_samples)
        )
        self._lock = RLock()
        self._counters: dict[str, int] = defaultdict(int)
        self._lifetime: dict[str, dict[str, float | int]] = {}
        self._answer_events: Deque[dict[str, object]] = deque(maxlen=self.max_samples * 24)
        self._active_answer = ""
        self._answer_actions: OrderedDict[str, str] = OrderedDict()

    def answer_stage(self, stage: str, answer_id: str = "", *, reason: str = "", related_answer_id: str = "") -> None:
        """Bounded monotonic milestones; never capture card contents."""
        if not self.enabled:
            return
        now = self._clock()
        with self._lock:
            if stage == "action":
                self._active_answer = answer_id or str(now)
            elif stage == "hook" and not self._active_answer:
                self._active_answer = str(now)
            action = (self._answer_actions.get(related_answer_id)
                      or self._answer_actions.get(answer_id) or self._active_answer)
            if answer_id and action:
                self._answer_actions[answer_id] = action
                self._answer_actions.move_to_end(answer_id)
                while len(self._answer_actions) > self.max_samples * 2:
                    self._answer_actions.popitem(last=False)
            self._answer_events.append({
                "stage": stage, "answer_id": answer_id or self._active_answer,
                "action_id": action, "at_ms": now * 1000,
                "reason": reason,
            })
            if stage == "hook_finished":
                self._active_answer = ""

    def begin(self) -> float | None:
        """Return a start marker, or ``None`` when diagnostics are disabled."""

        return self._clock() if self.enabled else None

    def finish(self, name: str, started: float | None) -> None:
        if started is None or not self.enabled:
            return
        self.record(name, max(0.0, (self._clock() - started) * 1000.0))

    def record(self, name: str, elapsed_ms: float) -> None:
        if not self.enabled:
            return
        normalized = str(name or "").strip()
        if not normalized:
            return
        value = max(0.0, float(elapsed_ms))
        with self._lock:
            self._samples[normalized].append(value)
            totals = self._lifetime.setdefault(normalized, {
                "count": 0, "maximum_ms": 0.0, "total_ms": 0.0,
                "over_50_ms": 0, "over_250_ms": 0,
            })
            totals["count"] += 1
            totals["maximum_ms"] = max(totals["maximum_ms"], value)
            totals["total_ms"] += value
            totals["over_50_ms"] += int(value > 50)
            totals["over_250_ms"] += int(value > 250)

    def samples(self, name: str) -> tuple[float, ...]:
        with self._lock:
            return tuple(self._samples.get(str(name), ()))

    def count(self, name: str, amount: int = 1) -> None:
        if self.enabled:
            with self._lock:
                self._counters[str(name)] += int(amount)

    @staticmethod
    def _percentile(sorted_values: Iterable[float], fraction: float) -> float:
        values = tuple(sorted_values)
        if not values:
            return 0.0
        rank = max(
            0,
            min(len(values) - 1, int(math.ceil(len(values) * fraction)) - 1),
        )
        return float(values[rank])

    def summary(self, name: str) -> PerformanceSummary:
        values = tuple(sorted(self.samples(name)))
        middle = len(values) // 2
        median = (
            0.0
            if not values
            else values[middle]
            if len(values) % 2
            else (values[middle - 1] + values[middle]) / 2.0
        )
        return PerformanceSummary(
            name=str(name),
            count=len(values),
            median_ms=round(float(median), 3),
            p95_ms=round(self._percentile(values, 0.95), 3),
            maximum_ms=round(float(values[-1]) if values else 0.0, 3),
        )

    def summaries(self) -> tuple[PerformanceSummary, ...]:
        with self._lock:
            names = tuple(sorted(self._samples))
        return tuple(self.summary(name) for name in names)

    def payload(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema_version": 1,
                "sample_limit_per_operation": self.max_samples,
                "operations": [asdict(summary) for summary in self.summaries()],
                "counters": dict(self._counters),
                "lifetime": {name: dict(values) for name, values in self._lifetime.items()},
                "answer_events": list(self._answer_events),
            }

    def write_json(self, destination: str | Path) -> Path:
        target = Path(destination)
        if not target.is_absolute():
            raise ValueError("Performance output must use an absolute path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(
            json.dumps(self.payload(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


RUNTIME_PERFORMANCE = RuntimePerformanceRecorder()


def timed(name: str):
    """Keep tracing opt-in without changing the wrapped API."""
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            started = RUNTIME_PERFORMANCE.begin()
            try:
                return function(*args, **kwargs)
            finally:
                RUNTIME_PERFORMANCE.finish(name, started)
        return measured
    return decorate


def watch_event_loop(parent) -> None:
    if not RUNTIME_PERFORMANCE.enabled:
        return
    from aqt.qt import QTimer
    timer = QTimer(parent)
    timer.setInterval(25)
    previous = time.perf_counter()
    def tick():
        nonlocal previous
        now = time.perf_counter()
        RUNTIME_PERFORMANCE.record("event-loop.delay", max(0.0, (now - previous) * 1000 - 25))
        previous = now
    timer.timeout.connect(tick)
    timer.start()
    parent._garden_performance_timer = timer


def _export_enabled_samples() -> None:
    destination = os.environ.get(PERFORMANCE_OUTPUT_ENV, "").strip()
    if not destination or not RUNTIME_PERFORMANCE.enabled:
        return
    try:
        RUNTIME_PERFORMANCE.write_json(destination)
    except Exception:
        # Diagnostics must never interfere with Anki shutdown or learner data.
        return


if (
    RUNTIME_PERFORMANCE.enabled
    and os.environ.get(PERFORMANCE_OUTPUT_ENV, "").strip()
):
    atexit.register(_export_enabled_samples)
