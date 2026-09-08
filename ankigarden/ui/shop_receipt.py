"""Visible-time expiry for the Shop's committed purchase shortcut only."""

from __future__ import annotations

from time import monotonic

from aqt.qt import (
    QApplication, QEvent, QGraphicsOpacityEffect, QObject, QPropertyAnimation,
    QTimer,
)


class ShopReceiptLifetime(QObject):
    """Pause a receipt while its actions are hovered or keyboard-focused.

    The controller has no purchase or inventory references. Each timer and fade
    belongs to one displayed receipt, including callbacks already queued by Qt.
    """

    def __init__(self, receipt, owner) -> None:
        super().__init__(owner)
        self.receipt = receipt
        self.owner = owner
        self._generation = 0
        self._active = False
        self._remaining_ms = 0.0
        self._started_at = None
        self._timer = None
        self._animation = None
        self._effect = None
        self._hovered = False
        self._motion_enabled = True
        receipt.installEventFilter(self)
        owner.installEventFilter(self)
        receipt.cleared.connect(self.cancel)
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def start(self, *, motion_enabled: bool = True) -> None:
        self.cancel()
        self._active = True
        self._remaining_ms = 8000.0
        self._motion_enabled = bool(motion_enabled)
        self._hovered = self.receipt.underMouse()
        self._resume()

    def cancel(self) -> None:
        self._generation += 1
        self._active = False
        self._pause()

    def _protected(self) -> bool:
        focus = QApplication.focusWidget()
        return bool(self._hovered or focus is self.receipt
                    or (focus is not None and self.receipt.isAncestorOf(focus)))

    def _pause(self) -> None:
        if self._started_at is not None:
            elapsed = (monotonic() - self._started_at) * 1000
            self._remaining_ms = max(0.0, self._remaining_ms - elapsed)
            self._started_at = None
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        if self._effect is not None:
            self._effect.setOpacity(1.0)
            self._effect.setEnabled(False)

    def _resume(self) -> None:
        if (not self._active or not self.receipt.isVisible()
                or self._protected() or self._timer is not None
                or self._animation is not None):
            return
        generation = self._generation
        if self._remaining_ms <= 0:
            self._fade(generation)
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        self._timer = timer
        self._started_at = monotonic()

        def elapsed() -> None:
            if generation != self._generation or self._timer is not timer:
                return
            self._pause()
            self._resume()

        timer.timeout.connect(elapsed)
        timer.start(max(1, int(self._remaining_ms + 0.999)))

    def _fade(self, generation: int) -> None:
        if not self._motion_enabled:
            self.receipt.clear()
            return
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self.receipt)
            self.receipt.setGraphicsEffect(self._effect)
        self._effect.setEnabled(True)
        animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation = animation
        animation.setDuration(200)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)

        def finished() -> None:
            if (generation == self._generation and self._animation is animation
                    and self._active and not self._protected()):
                self.receipt.clear()

        animation.finished.connect(finished)
        animation.start()

    def _focus_changed(self, _previous, _current) -> None:
        if not self._active:
            return
        if self._protected():
            self._pause()
        else:
            self._resume()

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if watched is self.owner and kind in (QEvent.Type.Hide, QEvent.Type.Close):
            was_active = self._active
            self.cancel()
            if was_active:
                self.receipt.clear()
        elif watched is self.receipt:
            if kind == QEvent.Type.Enter:
                self._hovered = True
                self._pause()
            elif kind == QEvent.Type.Leave:
                self._hovered = False
                self._resume()
            elif kind == QEvent.Type.Hide:
                self._pause()
            elif kind == QEvent.Type.Show:
                self._resume()
        return False
