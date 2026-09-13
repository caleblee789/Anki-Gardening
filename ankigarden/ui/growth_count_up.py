"""Finite presentation-only counting toward an already committed Growth value."""
from __future__ import annotations

from aqt.qt import QEasingCurve, QVariantAnimation


GROWTH_COUNT_UP_MS = 600


class GrowthCountUp(QVariantAnimation):
    def __init__(self, parent, render):
        super().__init__(parent)
        self._render = render
        self.value = 0
        self.target = 0
        self.setDuration(GROWTH_COUNT_UP_MS)
        self.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.valueChanged.connect(lambda value: self._write(round(float(value))))
        self.finished.connect(lambda: self._write(self.target))

    def _write(self, value):
        self.value = int(value)
        self._render(self.value)

    def retarget(self, target, *, animate=True):
        target = max(0, int(target))
        if target == self.target and (self.value == target or
                                      (animate and self.state() != self.State.Stopped)):
            return
        previous_target = self.target
        start = self.value
        self.target = target
        self.blockSignals(True)
        self.stop()
        self.setStartValue(start)
        self.setEndValue(target)
        self.setCurrentTime(0)
        self.blockSignals(False)
        if not animate or target < previous_target or start == target:
            self._write(target)
            return
        self._write(start)
        self.start()

    def settle(self):
        self.stop()
        self._write(self.target)

    def snapshot(self):
        return {"start": int(self.startValue() or 0), "target": self.target,
                "value": self.value, "elapsed_ms": self.currentTime(),
                "active": self.state() != self.State.Stopped,
                "paused": self.state() == self.State.Paused}

    def restore(self, state):
        if not isinstance(state, dict):
            return
        self.blockSignals(True)
        self.stop()
        self.target = max(0, int(state.get("target", 0)))
        self.setStartValue(max(0, int(state.get("start", 0))))
        self.setEndValue(self.target)
        elapsed = max(0, min(GROWTH_COUNT_UP_MS, int(state.get("elapsed_ms", 0))))
        self.setCurrentTime(0)
        self.blockSignals(False)
        if state.get("active") and elapsed < GROWTH_COUNT_UP_MS:
            self.start()
            self.setCurrentTime(elapsed)
            if state.get("paused"):
                self.pause()
            self._write(int(state.get("value", self.value)))
        else:
            self._write(self.target)
