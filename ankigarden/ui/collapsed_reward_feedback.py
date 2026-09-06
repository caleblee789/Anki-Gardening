"""Sequential earned feedback inside the compact review HUD's existing rail."""
from __future__ import annotations

from collections import deque

from aqt.qt import (
    QEasingCurve, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QTimer,
    QVariantAnimation, QVBoxLayout, QWidget, Qt,
)

from .icons import garden_icon
from .reward_rarity import reward_treatment
from .session_summary import format_growth_units
from .theme import GARDEN_THEME, apply_tabular_numerals


class CollapsedRewardFeedback(QWidget):
    """One inline slot: milestone art, then Coins, then committed Growth.

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.art = QLabel(self)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setFixedHeight(32)
        layout.addWidget(self.art)
        self.metric_row = QWidget(self)
        metric = QHBoxLayout(self.metric_row)
        metric.setContentsMargins(0, 0, 0, 0)
        metric.setSpacing(4)
        metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.metric_icon = QLabel(self.metric_row)
        self.metric_icon.setFixedSize(12, 12)
        metric.addWidget(self.metric_icon)
        self.amount = QLabel(self.metric_row)
        self.amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.amount.setTextFormat(Qt.TextFormat.PlainText)
        apply_tabular_numerals(self.amount)
        metric.addWidget(self.amount)
        layout.addWidget(self.metric_row)
        self.caption = QLabel(self)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(False)
        self.caption.setStyleSheet("font-size:11px;font-weight:600;")
        layout.addWidget(self.caption)
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
        self._frames = deque(frames)
        if coins:
            self._frames.append(self._amount_frame("Coins", coins))
        self._frames.extend(self._amount_frame(label, units) for label, units in allocations if units > 0)
        # A new milestone takes this single slot; it never creates another HUD.
        self._timer.stop()
        self._current = None
        self._current_major = False
        self._advance()

    def add_routine(self, allocations, coins=0):
        amounts = (("Coins", coins), *allocations)
        for label, units in amounts:
            if units <= 0:
                continue
            if self._current and not self._current_major and self._current.get("label") == label:
                self._current = self._amount_frame(label, self._current["units"] + units)
                self._render(self._current, animate=False)
                self._timer.start(950)
            else:
                self._pending[label] = self._pending.get(label, 0) + units
        if self._current is None:
            self._advance()

    def _amount_frame(self, label, units):
        coin = label == "Coins"
        return {"label": label, "units": units, "caption": {"Growth stored": "Stored", "Shared Growth": "Shared"}.get(label, ""),
                "icon": "coin" if coin else "growth", "duration": 950,
                "color": GARDEN_THEME["coin_accent" if coin else "reviewer_hud_growth_strong"]}

    def _advance(self):
        finished_major = self._current is not None and self._current_major
        self._current = None
        self._current_major = False
        if self._frames:
            self._current = self._frames.popleft()
            self._current_major = True
        else:
            if finished_major:
                QTimer.singleShot(0, lambda: self.hud._maybe_archive_current_reward() if not self.hud._disposed else None)
            if self._pending:
                label = "Coins" if self._pending.get("Coins", 0) else next(iter(self._pending))
                self._current = self._amount_frame(label, self._pending.pop(label))
        self.setProperty("sequencePending", self.major_pending)
        if self._current is None:
            self._clear_display()
            return
        self._render(self._current)
        if self.hud._collapsed:
            self._timer.start(self._current["duration"])
        else:
            self._paused_ms = self._current["duration"]

    def _render(self, frame, *, animate=True):
        color = frame["color"]
        treatment = reward_treatment(frame.get("treatment", ""))
        self.art.setStyleSheet("background:transparent;border:0;")
        self.hud._collapsed_tab.setProperty("rewardTone", treatment.key)
        self.hud._collapsed_tab.setStyleSheet(
            f"QFrame#reviewerHudCollapsedTab {{border:1px solid {treatment.color};}}"
            if treatment.notable else "")
        units = frame.get("units")
        ratio = max(1.0, self.devicePixelRatioF())
        if units is not None:
            self.art.hide()
            self.metric_icon.setPixmap(garden_icon(frame["icon"], color=color, logical_size=12).pixmap(round(12 * ratio), round(12 * ratio)))
            icon = self.metric_icon.pixmap()
            icon.setDevicePixelRatio(ratio)
            self.metric_icon.setPixmap(icon)
            exact = f"+{units:,}" if frame["label"] == "Coins" else format_growth_units(units, signed=True)
            self.amount.setStyleSheet(f"color:{color};font-size:13px;font-weight:600;")
            self.amount.ensurePolished()
            self.amount.setText(self._fit_amount(exact, units, frame["label"]))
            self.metric_row.show()
            unit_name = "Coin" if frame["label"] == "Coins" and units == 1 else frame["label"]
            tooltip = f"{exact} {unit_name}"
        else:
            self.metric_row.hide()
            pixmap = frame.get("pixmap")
            if pixmap is None or pixmap.isNull():
                pixmap = garden_icon(frame.get("icon", "find"), color=color).pixmap(round(32 * ratio), round(32 * ratio))
            art = pixmap.scaled(round(32 * ratio), round(32 * ratio), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            art.setDevicePixelRatio(ratio)
            self.art.setPixmap(art)
            self.art.show()
            tooltip = frame.get("detail") or frame["caption"].replace("\n", " ")
        self.caption.setText(frame["caption"])
        self.caption.setStyleSheet(f"color:{color};font-size:11px;font-weight:600;")
        self.caption.setVisible(bool(frame["caption"]))
        self._fit_labels()
        self._sync_content_height()
        self.setProperty("feedbackCopy", tooltip)
        self.hud._collapsed_tab.setToolTip(f"{tooltip}\nOpen Anki Garden")
        if animate and self.hud._animations_enabled:
            self._fade_in()
            self.hud.pulse_collapsed_plant(color, artwork=self.art if treatment.notable else None)

    def _fit_amount(self, exact, units, label):
        metrics = self.amount.fontMetrics()
        available = max(1, self.width() - 16)
        if metrics.horizontalAdvance(exact) <= available:
            return exact
        value = units if label == "Coins" else units / 100
        for divisor, suffix in ((1_000, "K"), (1_000_000, "M"), (1_000_000_000, "B"), (1_000_000_000_000, "T")):
            if value < divisor:
                continue
            for precision in (1, 0):
                number = f"{value / divisor:.{precision}f}"
                if precision:
                    number = number.rstrip("0").rstrip(".")
                candidate = f"+{number}{suffix}"
                if metrics.horizontalAdvance(candidate) <= available:
                    return candidate
        # A bounded scientific form is reserved for extraordinary values; the
        # tooltip/history still expose the original exact committed amount.
        return f"+{value:.0e}"

    def _fit_labels(self):
        width = max(1, self.width())
        self.art.setFixedWidth(width)
        self.metric_row.setFixedWidth(width)
        self.caption.setFixedWidth(width)
        self.caption.ensurePolished()
        self.amount.ensurePolished()
        line_count = max(1, len(self.caption.text().splitlines()))
        self.caption.setFixedHeight(self.caption.fontMetrics().lineSpacing() * line_count)
        amount_height = max(16, self.amount.fontMetrics().height())
        self.amount.setFixedSize(self.amount.fontMetrics().horizontalAdvance(self.amount.text()), amount_height)
        self.metric_row.setFixedHeight(amount_height)

    def _sync_content_height(self):
        """Hug the visible frame instead of reserving empty milestone space."""
        visible = [widget for widget in (self.art, self.metric_row, self.caption)
                   if not widget.isHidden()]
        height = sum(widget.height() for widget in visible)
        height += self.layout().spacing() * max(0, len(visible) - 1)
        changed = self.height() != height or self.isHidden() != (height == 0)
        self.setFixedHeight(height)
        self.setVisible(height > 0)
        if changed and self.hud._collapsed:
            QTimer.singleShot(0, lambda: self.hud.reposition() if not self.hud._disposed else None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current is not None:
            self._render(self._current, animate=False)
        else:
            self._fit_labels()

    def _clear_display(self):
        for widget in (self.art, self.metric_row, self.caption):
            widget.hide()
        self._sync_content_height()
        self.setProperty("feedbackCopy", "")
        self.setProperty("sequencePending", False)
        self.hud._collapsed_tab.setToolTip("Open Anki Garden")
        self.hud._collapsed_tab.setStyleSheet("")
        self.hud._collapsed_tab.setProperty("rewardTone", "")

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

    def _fade_in(self):
        if self._motion is not None:
            self._motion.stop()
            self._motion.deleteLater()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        motion = QVariantAnimation(self)
        self._motion = motion
        motion.setDuration(160)
        motion.setStartValue(0.0)
        motion.setEndValue(1.0)
        motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        motion.valueChanged.connect(effect.setOpacity)
        motion.finished.connect(lambda: self.setGraphicsEffect(None) if self._motion is motion else None)
        motion.start()

    def dispose(self):
        self._timer.stop()
        if self._motion is not None:
            self._motion.stop()
        self._frames.clear()
        self._pending.clear()
