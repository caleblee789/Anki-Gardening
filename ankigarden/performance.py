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
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
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

    def samples(self, name: str) -> tuple[float, ...]:
        with self._lock:
            return tuple(self._samples.get(str(name), ()))

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
        return {
            "schema_version": 1,
            "sample_limit_per_operation": self.max_samples,
            "operations": [asdict(summary) for summary in self.summaries()],
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
