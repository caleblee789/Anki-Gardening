"""The first Garden celebration and its progressively disclosed reward receipt."""
from __future__ import annotations

import time
from typing import Any

from aqt.qt import (
    QEvent, QFrame, QHBoxLayout, QLabel, QObject, QPushButton, QScrollArea,
    QSize, QSizePolicy, QTimer, QVBoxLayout, QWidget, Qt,
)

from ..models.state import GROWTH_UNITS_PER_POINT
from ..welcome_presentation import present_welcome
from .copy import WELCOME_BODY, WELCOME_REWARDS_ACTION, WELCOME_TITLE
from .formatters import format_stage_progress, format_status_label
from .icons import garden_icon
from .plant_display import growth_display
from .reward_receipt import receipt_event_row, receipt_style
from .session_summary_card import _alpha_bounded_thumbnail, _source_pixmap, session_summary_palette
from .welcome_animation import WELCOME_DURATION


class WelcomeCard(QFrame):
    """One child card: a short greeting, with details available on request."""

    def __init__(self, parent: QWidget, dismiss: Any, engine: Any) -> None:
        super().__init__(parent)
        self._engine = engine
        self.setObjectName("gardenWelcomeCard")
        self.setProperty("rewardReceipt", True)
        self.setAccessibleName(WELCOME_TITLE)
        self._palette = session_summary_palette()
        self.setStyleSheet(receipt_style(self._palette) + f"""
            QFrame#gardenWelcomeCard {{ border-radius:16px; }}
            QLabel {{ background:transparent; border:0; color:{self._palette['text_primary']}; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:0; }}
            QPushButton:focus {{ border:2px solid {self._palette['growth_accent']}; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        heading = QHBoxLayout()
        self._heading_layout = heading
        heading.setSpacing(10)
        title = self._label(WELCOME_TITLE, 19, bold=True)
        heading.addWidget(title, 1)
        self.close_button = QPushButton(self)
        self.close_button.setObjectName("gardenWelcomeClose")
        self.close_button.setProperty("receiptClose", True)
        self.close_button.setIcon(garden_icon("close", color=self._palette["text_secondary"]))
        self.close_button.setIconSize(QSize(14, 14))
        self.close_button.setFixedSize(26, 26)
        self.close_button.setAutoDefault(False)
        self.close_button.setDefault(False)
        self.close_button.setAccessibleName("Close welcome")
        self.close_button.setToolTip("Close welcome")
        self.close_button.clicked.connect(dismiss)
        heading.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(heading)
        self.body = self._label(WELCOME_BODY, 13)
        root.addWidget(self.body)
        self.details = QScrollArea(self)
        self.details.setObjectName("gardenWelcomeRewards")
        self.details.setWidgetResizable(True)
        self.details.setFrameShape(QFrame.Shape.NoFrame)
        self.details.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details.setMinimumHeight(0)
        self.details.hide()
        root.addWidget(self.details, 1)
        actions = QHBoxLayout()
        self._actions_layout = actions
        actions.setContentsMargins(0, 0, 0, 0)
        self.view_rewards = QPushButton(WELCOME_REWARDS_ACTION, self)
        self.view_rewards.setObjectName("gardenWelcomeViewRewards")
        self.view_rewards.setProperty("receiptPrimary", True)
        self.view_rewards.setFixedHeight(34)
        self.view_rewards.setAutoDefault(False)
        self.view_rewards.setDefault(False)
        self.view_rewards.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_rewards.clicked.connect(self._toggle_details)
        actions.addWidget(self.view_rewards)
        actions.addStretch(1)
        root.addLayout(actions)
        self.expanded = False
        self.hide()

    def _label(self, text: str, size: int, *, bold: bool = False) -> QLabel:
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(f"font-size:{size}px;font-weight:{600 if bold else 400};")
        return label

    def set_receipt(self, receipt: Any) -> None:
        presentation = present_welcome(receipt)
        content = QWidget(self.details)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 2, 10, 6)
        layout.setSpacing(8)
        layout.addWidget(self._label("Welcome gift", 14, bold=True))
        gift = QHBoxLayout()
        gift.setSpacing(12)
        for reward in presentation.gift:
            gift.addWidget(self._reward_row(reward), 1)
        layout.addLayout(gift)
        if presentation.show_history:
            layout.addSpacing(10)
            layout.addWidget(self._label("Past Anki study", 14, bold=True))
            intro = self._label(presentation.history_intro, 13)
            intro.setObjectName("gardenWelcomePastStudy")
            layout.addWidget(intro)
            for reward in presentation.history:
                layout.addWidget(self._reward_row(reward))
            if presentation.achievement_count:
                count = presentation.achievement_count
                layout.addWidget(self._label(
                    f"{count} {'achievement' if count == 1 else 'achievements'} earned", 13, bold=True,
                ))
        layout.addStretch(1)
        self.details.setWidget(content)
        self.expanded = False
        self.body.show()
        self.details.hide()
        self.view_rewards.setText(WELCOME_REWARDS_ACTION)

    def _reward_row(self, reward: Any) -> QWidget:
        art = QLabel(self)
        art.setFixedSize(32, 32)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = self._palette["coin_accent" if reward.icon in {"coin", "stage"} else "growth_accent"]
        pixmap = garden_icon(reward.icon, color=color).pixmap(22, 22)
        source_path = f"icon:{reward.icon}"
        if reward.item_id:
            # Resolve the same catalog artwork used by the review HUD and
            # shared reward receipts, including each distinct charge size.
            try:
                asset = self._engine.resolve_item_asset(reward.item_id)
                path = str(getattr(asset, "path", "") or "")
                source = _source_pixmap(path) if path else None
                if source is not None and not source.isNull():
                    pixmap = _alpha_bounded_thumbnail(source, 32)
                    source_path = path
            except Exception:
                pass  # Retain the semantic icon if bundled art is unavailable.
        art.setPixmap(pixmap)
        art.setProperty("welcomeRewardArt", source_path)
        art.setProperty("welcomeRewardItem", reward.item_id)
        row = receipt_event_row(self, art, reward.text)
        row.layout.setContentsMargins(6, 3, 6, 3)
        row.widget.setAccessibleName(reward.text)
        return row.widget

    def _toggle_details(self) -> None:
        self.expanded = not self.expanded
        self.body.setVisible(not self.expanded)
        self.details.setVisible(self.expanded)
        self.view_rewards.setText("Hide rewards" if self.expanded else WELCOME_REWARDS_ACTION)
        self.reposition()

    def reposition(self) -> None:
        parent = self.parentWidget()
        width = min(500, max(0, parent.width() - 32))
        self.setFixedWidth(width)
        # Reserve the main navigation and nurtured-plant bar. Only the optional
        # details scroll; the heading, close button and disclosure stay visible.
        self.layout().activate()
        compact = self.layout().totalHeightForWidth(width)
        if compact < 0:
            compact = self.sizeHint().height()
        desired = compact
        if self.expanded and self.details.widget() is not None:
            margins = self.layout().contentsMargins()
            border = 2 * self.frameWidth()
            inner_width = max(0, width - border - margins.left() - margins.right())
            content = self.details.widget()
            content_height = content.layout().totalHeightForWidth(max(0, inner_width - 16))
            if content_height < 0:
                content_height = content.sizeHint().height()
            content_height = max(content_height, content.minimumSizeHint().height())
            heading_height = self._heading_layout.totalHeightForWidth(inner_width)
            if heading_height < 0:
                heading_height = self._heading_layout.sizeHint().height()
            desired = (content_height + heading_height + self._actions_layout.sizeHint().height()
                       + margins.top() + margins.bottom() + border + 2 * self.layout().spacing())
        height = min(max(0, parent.height() - 32), 540, desired)
        self.setFixedHeight(max(0, height))
        self.move((parent.width() - width) // 2, 16)
        self.raise_()


class WelcomeController(QObject):
    """Presentation can be interrupted; committed rewards never depend on it."""

    def __init__(self, dashboard: Any) -> None:
        super().__init__(dashboard)
        self.dashboard = dashboard
        self.scene = dashboard.scene
        self.card = WelcomeCard(self.scene, self.dismiss, dashboard.engine)
        self.skip = QPushButton("Skip animation", self.scene)
        self.skip.setObjectName("gardenWelcomeSkip")
        self.skip.setProperty("receiptSecondary", True)
        self.skip.setStyleSheet(receipt_style(session_summary_palette()))
        self.skip.setFixedSize(126, 32)
        self.skip.setAutoDefault(False)
        self.skip.setDefault(False)
        self.skip.clicked.connect(self.settle)
        self.skip.hide()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.receipt = None
        self._started_at = 0.0
        self.scene.installEventFilter(self)
        self.card.installEventFilter(self)
        self.card.view_rewards.installEventFilter(self)
        self.card.close_button.installEventFilter(self)
        self.skip.installEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        kind = event.type()
        if watched is self.scene:
            if kind == QEvent.Type.Show:
                QTimer.singleShot(0, self.maybe_present)
            elif kind == QEvent.Type.Hide:
                self.suspend()
            elif kind == QEvent.Type.Resize:
                self.card.reposition()
                self.skip.move(max(0, self.scene.width() - self.skip.width() - 16), 16)
        if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            return self.handle_escape()
        return False

    def handle_escape(self) -> bool:
        if self.timer.isActive():
            self.settle()
            return True
        if self.card.isVisible():
            self.dismiss()
            return True
        return False

    def maybe_present(self) -> None:
        receipt = self.dashboard.storage.state.welcome_receipt
        if (
            receipt is None or not receipt.pending or not self.scene.isVisible()
            or self.dashboard._workspace_section != "garden"
            or self.timer.isActive() or self.card.isVisible()
        ):
            return
        self.receipt = receipt
        self.card.set_receipt(receipt)
        should_animate = receipt.status == "ready" and bool(self.scene.scene.get("motion_enabled", True))
        if not self.dashboard.engine.mark_welcome_presented(receipt.receipt_id):
            # A failed acknowledgement must not hide an already-saved gift.
            should_animate = False
        if should_animate:
            self._started_at = time.monotonic()
            self.skip.move(max(0, self.scene.width() - self.skip.width() - 16), 16)
            self.skip.show()
            self.skip.raise_()
            self._tick()
            self.timer.start()
        else:
            self.settle()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started_at
        if elapsed >= WELCOME_DURATION or not self.scene.scene.get("motion_enabled", True):
            self.settle()
            return
        if not self.scene.isVisible():
            self.suspend()
            return
        self.scene.set_welcome_frame(self.receipt.plant_id, elapsed)
        phase = min(1.0, max(0.0, (elapsed - 0.4) / 1.35))
        eased = 1 - (1 - phase) ** 3
        units = self.receipt.growth_before_units + round(
            (self.receipt.growth_after_units - self.receipt.growth_before_units) * eased
        )
        bar = self.dashboard.nurtured_plant_bar
        if bar.plant_id == self.receipt.plant_id:
            progress = growth_display(units / GROWTH_UNITS_PER_POINT)
            bar.progress.setRange(0, max(1, int(progress.stage_goal)) * GROWTH_UNITS_PER_POINT)
            bar.progress.setValue(round(progress.stage_points * GROWTH_UNITS_PER_POINT))
            bar.growth_label.setText(format_stage_progress(
                progress.stage_points, progress.stage_goal, format_status_label(progress.next_stage or "the next stage"),
            ))

    def _stop_animation(self) -> None:
        self.timer.stop()
        self.skip.hide()
        self.scene.set_welcome_frame("", None)
        bar = self.dashboard.nurtured_plant_bar
        plant = next((row for row in self.scene.scene.get("plants", []) if row.get("plant_id") == bar.plant_id), None)
        bar.set_plant(plant)

    def settle(self) -> None:
        self._stop_animation()
        if self.receipt is not None and self.scene.isVisible():
            self.card.show()
            self.card.reposition()
            self.dashboard.accessibility_announcer.announce(f"{WELCOME_TITLE} {WELCOME_BODY}")

    def suspend(self) -> None:
        self._stop_animation()
        self.card.hide()

    def dismiss(self) -> None:
        if self.receipt is None:
            return
        if self.dashboard.engine.mark_welcome_presented(self.receipt.receipt_id, acknowledged=True):
            self.suspend()
            self.dashboard.workspace_buttons["garden"].setFocus()
        else:
            self.dashboard.toast_region.show_message("Couldn’t save this change. Please try closing the welcome again.", error=True)
