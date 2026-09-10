"""Sequential earned feedback inside the compact review HUD's existing rail."""
from __future__ import annotations

from collections import deque

from aqt.qt import (
    QEasingCurve, QHBoxLayout, QLabel, QPainter, QPalette, QTimer,
    QVariantAnimation, QStackedLayout, QWidget, Qt,
)

from .icons import garden_icon
from .reward_rarity import reward_treatment
from .session_summary import format_growth_units
from .theme import GARDEN_THEME, apply_tabular_numerals


class _FadingLabel(QLabel):
    """Paint text opacity directly so stacked native grabs retain idle copy."""

    def opacity(self):
        return getattr(self, "_text_opacity", 1.0)

    def setOpacity(self, value):
        self._text_opacity = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(self.opacity())
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        pixmap = self.pixmap()
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(self.contentsRect(), pixmap)
        else:
            painter.drawText(self.contentsRect(), self.alignment(), self.text())


class _FadingRow(QWidget):
    def opacity(self):
        return getattr(self, "_row_opacity", 1.0)

    def setOpacity(self, value):
        self._row_opacity = float(value)
        for label in self.findChildren(_FadingLabel):
            label.setOpacity(value)


class CollapsedRewardFeedback(QWidget):
    """One inline slot: committed Growth, then milestone art, then Coins.

    This owns only the visual sequence. The HUD keeps the authoritative bundle,
    history, duplicate protection, and expanded-reward lifecycle.
    """

    def __init__(self, hud):
        super().__init__(hud._collapsed_tab)
        self.hud = hud
        self._major_id = ""
        self._seen_major_ids = set()
        self._frames = deque()
        self._pending = {}
        self._current = None
        self._current_major = False
        self._paused_ms = 0
        self._motion = None
        self.setObjectName("reviewerHudCollapsedFeedback")
        self.setProperty("semanticId", "reviewer.hud.collapsed-feedback")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(0)
        self.setMinimumHeight(0)
        self.setStyleSheet("background:transparent;border:0;")
        # These layers occupy the existing 18px reward line throughout every
        # state. Only opacity changes; neither can intercept the tile click.
        self.setFixedHeight(18)
        layout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.idle = _FadingLabel(self)
        self.idle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.idle.setStyleSheet(f"color:{GARDEN_THEME['text_secondary']};font-size:12px;font-weight:400;")
        self.idle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.idle_effect = self.idle
        layout.addWidget(self.idle)
        self.metric_row = _FadingRow(self)
        self.metric_row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        metric = QHBoxLayout(self.metric_row)
        metric.setContentsMargins(0, 0, 0, 0)
        metric.setSpacing(4)
        metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.metric_icon = _FadingLabel(self.metric_row)
        self.metric_icon.setFixedSize(12, 12)
        metric.addWidget(self.metric_icon)
        self.amount = _FadingLabel(self.metric_row)
        self.amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.amount.setTextFormat(Qt.TextFormat.PlainText)
        apply_tabular_numerals(self.amount)
        metric.addWidget(self.amount)
        # Retained read-only capture accessor; not a second visible line.
        self.caption = QLabel(self)
        self.caption.hide()
        self.reward_effect = self.metric_row
        layout.addWidget(self.metric_row)
        self._disposed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)
        self._clear_display()

    @property
    def major_pending(self):
        return bool(self._frames or (self._current is not None and self._current_major))

    def set_major(self, identity, frames, coins, allocations):
        if identity in self._seen_major_ids:
            self.resume()
            return
        self._seen_major_ids.add(identity)
        self._major_id = identity
        self.setProperty("rewardBundleId", identity)
        # Preserve pending resource messages when a newer major event arrives.
        # Decorative notices can coalesce, but committed Coins and Growth each
        # retain a finite turn in the display sequence.
        self._frames = deque(frames[-1:])
        self.add_routine(allocations, coins)
        if self._current is None:
            self._advance()

    def add_routine(self, allocations, coins=0):
        # A routine answer should acknowledge its Growth immediately instead
        # of waiting for the Coin frame's full reading time.
        for label, units in (*allocations, ("Coins", coins)):
            if units > 0:
                resource = "Coins" if label == "Coins" else "Growth"
                self._pending[resource] = self._pending.get(resource, 0) + units
        if self._current is not None and not self._current_major and "Growth" in self._pending:
            # A new answer need not wait behind an already displayed resource.
            # Merge an in-flight Growth pulse; Coins have already been shown.
            if self._current.get("label") == "Growth":
                self._pending["Growth"] += self._current["units"]
            self._timer.stop()
            self._advance()
            return
        if self._current is None:
            self._advance()

    def _amount_frame(self, label, units):
        coin = label == "Coins"
        return {"label": label, "units": units, "caption": {"Growth stored": "Stored", "Shared Growth": "Shared"}.get(label, ""),
                "icon": "coin" if coin else "growth", "duration": 950,
                "color": GARDEN_THEME["coin_accent" if coin else "reviewer_hud_growth_strong"]}

    def _advance(self):
        if self._disposed:
            return
        finished_major = self._current is not None and self._current_major
        self._current = None
        self._current_major = False
        if "Growth" in self._pending:
            self._current = self._amount_frame("Growth", self._pending.pop("Growth"))
        elif self._frames:
            self._current = self._frames.popleft()
            self._current_major = True
        elif self._pending:
            label = next(iter(self._pending))
            self._current = self._amount_frame(label, self._pending.pop(label))
        if finished_major:
            QTimer.singleShot(0, lambda: self.hud._maybe_archive_current_reward() if not self.hud._disposed else None)
        self.setProperty("sequencePending", self.major_pending)
        if self._current is None:
            self._clear_display()
            return
        self._render(self._current)
        if self.hud._collapsed:
            self._timer.start(self._current["duration"])
        else:
            self._paused_ms = self._current["duration"]

    def update_idle(self):
        nurture = getattr(getattr(self.hud, "_projection", None), "nurture", None)
        valid = bool(nurture is not None and getattr(nurture, "plant_id", ""))
        text = ("Full Bloom" if bool(getattr(nurture, "fully_grown", False)) else
                f"{int(self.hud._collapsed_ring.property('progressPercent') or 0)}%") if valid else ""
        self.idle.setText(text)
        self.hud._collapsed_tab.setProperty("collapsedNextValueCopy", text)
        self.hud._collapsed_tab.setProperty("collapsedNextVisibleCopy", text if self._current is None else "")

    def _render(self, frame, *, animate=True):
        color = frame["color"]
        units = frame.get("units")
        self.caption.setText(str(frame.get("caption", "")))
        if units is not None:
            exact = f"+{units:,}" if frame["label"] == "Coins" else format_growth_units(units, signed=True)
            ratio = max(1.0, self.devicePixelRatioF())
            icon = garden_icon(frame["icon"], color=color).pixmap(round(12 * ratio), round(12 * ratio))
            icon.setDevicePixelRatio(ratio)
            self.metric_icon.setPixmap(icon)
            self.metric_icon.show()
            self.amount.setStyleSheet(f"color:{color};font-size:13px;font-weight:600;")
            self.amount.ensurePolished()
            spacing = min(4, max(0, self.width() - 12 - self.amount.fontMetrics().horizontalAdvance(exact)))
            self.metric_row.layout().setSpacing(spacing)
            self.amount.setText(exact)
            tooltip = f"{exact} {frame['label']}"
        else:
            self.metric_icon.hide()
            text = str(frame.get("caption", "Reward")).replace("\nReached", "").replace("\n", " ")
            self.amount.setStyleSheet(f"color:{color};font-size:12px;font-weight:600;")
            if "Discovery" in text:
                text = "Discovery"
            elif "Find" in text:
                text = "Garden Find"
            self.amount.setText(text)
            tooltip = str(frame.get("detail") or text)
        self.setProperty("feedbackCopy", tooltip)
        self.amount.setToolTip(tooltip)
        self.amount.setAccessibleName(tooltip)
        self.update_idle()
        self._exchange(True, animate=animate)
        if animate:
            self.hud.pulse_collapsed_plant(color)

    def _clear_display(self):
        self.update_idle()
        self.setProperty("feedbackCopy", "")
        self.caption.clear()
        self.setProperty("sequencePending", False)
        self._exchange(False)

    def _exchange(self, reward, *, animate=True):
        if self._motion is not None:
            self._motion.stop()
            self._motion.deleteLater()
            self._motion = None
        target = 1.0 if reward else 0.0
        def settle():
            # At rest, paint only the active layer in the fixed status slot.
            self.metric_row.setVisible(reward)
            self.idle.setVisible(not reward)
        if not animate or not self.hud._animations_enabled:
            self.reward_effect.setOpacity(target)
            self.idle_effect.setOpacity(1.0 - target)
            settle()
            return
        self.idle.show()
        self.metric_row.show()
        motion = QVariantAnimation(self)
        self._motion = motion
        motion.setDuration(140)
        motion.setStartValue(self.reward_effect.opacity())
        motion.setEndValue(target)
        def render(value):
            if self._motion is motion and not self._disposed:
                self.reward_effect.setOpacity(float(value))
                self.idle_effect.setOpacity(1.0 - float(value))
        def finish():
            if self._motion is motion and not self._disposed:
                render(target)
                settle()
                self._motion = None
                motion.deleteLater()
        motion.valueChanged.connect(render)
        motion.finished.connect(finish)
        motion.start()

    def export_state(self):
        """Keep the current frame and hold across an in-process HUD remount."""
        remaining = self._timer.remainingTime() if self._timer.isActive() else self._paused_ms
        return {
            "major_id": self._major_id,
            "seen_major_ids": tuple(self._seen_major_ids),
            "frames": tuple(dict(frame) for frame in self._frames),
            "pending": dict(self._pending),
            "current": dict(self._current) if self._current is not None else None,
            "current_major": self._current_major,
            "remaining_ms": max(1, remaining) if self._current is not None else 0,
        }

    def restore_state(self, state):
        if not isinstance(state, dict):
            return
        self._timer.stop()
        self._major_id = state.get("major_id", "")
        self._seen_major_ids = set(state.get("seen_major_ids", ()))
        self._frames = deque(dict(frame) for frame in state.get("frames", ()))
        self._pending = dict(state.get("pending", {}))
        current = state.get("current")
        self._current = dict(current) if current is not None else None
        self._current_major = bool(state.get("current_major"))
        self._paused_ms = max(1, int(state.get("remaining_ms", 0)))
        self.setProperty("rewardBundleId", self._major_id)
        self.setProperty("sequencePending", self.major_pending)
        if self._current is None:
            self._clear_display()
        else:
            self._render(self._current, animate=False)

    def clear_major(self):
        self._major_id = ""
        self.setProperty("rewardBundleId", "")
        self._frames.clear()
        if self._current_major:
            self._timer.stop()
            self._current = None
            self._current_major = False
            self._advance()

    def suspend(self):
        if self._timer.isActive():
            self._paused_ms = max(1, self._timer.remainingTime())
            self._timer.stop()

    def resume(self):
        if self._current is not None and self.hud._collapsed and not self._timer.isActive():
            self._timer.start(self._paused_ms or self._current["duration"])
            self._paused_ms = 0

    def dispose(self):
        self._disposed = True
        self._timer.stop()
        if self._motion is not None:
            self._motion.stop()
        self._frames.clear()
        self._pending.clear()
