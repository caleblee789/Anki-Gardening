"""Permanent, read-only overview of the garden's plant beds."""
from __future__ import annotations

from aqt.qt import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QScrollArea,
    QSize, QSizePolicy, Qt, QTimer, QVBoxLayout, QWidget,
)

from ..balance_catalog import CONSUMABLE_BY_ID
from ..plant_beds import PlantBedProgress, plant_bed_progress
from .controls import GardenWrappingLabel
from .formatters import GardenDateService
from .icons import garden_icon_pixmap
from .theme import GARDEN_THEME, SemanticRole, set_semantic_role


def _label(text, size, weight=400, line_height=16, *, secondary=False):
    label = GardenWrappingLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setMinimumHeight(line_height)
    label.setProperty("textLineHeight", line_height)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    label.setStyleSheet(
        f"background:transparent;border:0;padding:0;font-size:{size}px;font-weight:{weight};"
        f"color:{GARDEN_THEME['text_secondary' if secondary else 'text_primary']};"
    )
    return label


class PlantBedCard(QFrame):
    def __init__(self, row: PlantBedProgress, artwork, parent=None):
        super().__init__(parent)
        self.row = row
        self.setProperty("plantBedCard", True)
        self.setProperty("bedId", row.bed_id)
        self.setAccessibleName(f"Bed {row.bed_number}. {row.status}. {row.requirement}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        border = GARDEN_THEME['action_accent' if row.next_bed else 'subtle_border']
        self.setStyleSheet(
            f"QFrame[plantBedCard='true'] {{background:{GARDEN_THEME['raised_surface']};"
            f"border:1px solid {border};border-radius:8px;}}"
            f"QFrame[plantBedCard='true']:focus {{border-color:{GARDEN_THEME['focus_ring']};}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(_label(f"Bed {row.bed_number}", 14, 600, 20), 1)
        badge = QFrame(self)
        badge.setAccessibleName(row.status)
        badge.setMinimumHeight(22)
        badge.setStyleSheet(f"background:{GARDEN_THEME['selected_surface']};border:0;border-radius:6px;")
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(8, 3, 8, 3)
        badge_layout.setSpacing(4)
        icon = QLabel(badge)
        icon.setFixedSize(14, 14)
        icon.setPixmap(garden_icon_pixmap("check" if row.unlocked else "lock", 14,
                                         color=GARDEN_THEME['action_accent' if row.unlocked or row.next_bed else 'text_secondary']))
        badge_layout.addWidget(icon)
        status = _label(row.status, 12, 600)
        status.setWordWrap(False)
        badge_layout.addWidget(status)
        heading.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)
        layout.addSpacing(6)
        layout.addWidget(_label(row.requirement, 13, line_height=18))
        if not row.unlocked:
            layout.addSpacing(4)
            layout.addWidget(_label(f"{row.current} of {row.target} species", 12, 500))
            layout.addSpacing(6)
            bar = QProgressBar(self)
            bar.setProperty("semanticId", f"progress.plant_beds.{row.bed_id}")
            set_semantic_role(bar, SemanticRole.PROGRESS)
            bar.setAccessibleName(f"Bed {row.bed_number} unlock progress")
            bar.setAccessibleDescription(f"{row.current} of {row.target} species")
            bar.setRange(0, 1000)
            bar.setValue(round(row.progress * 1000))
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            bar.setStyleSheet(
                f"QProgressBar {{background:{GARDEN_THEME['selected_surface']};border:0;border-radius:2px;min-height:4px;max-height:4px;padding:0;}}"
                f"QProgressBar::chunk {{background:{GARDEN_THEME['action_accent']};border-radius:2px;}}"
            )
            layout.addWidget(bar)
        for item_id, quantity in row.bonus_items:
            layout.addSpacing(4)
            reward = QHBoxLayout()
            reward.setSpacing(6)
            reward.addWidget(_label("Bonus received" if row.bonus_received else "Bonus reward", 12, 500),
                             0, Qt.AlignmentFlag.AlignTop)
            item = CONSUMABLE_BY_ID[item_id]
            reward.addWidget(artwork(item_id, item.display_name), 0, Qt.AlignmentFlag.AlignTop)
            reward.addWidget(_label(f"{quantity} × {item.display_name}", 12, 500), 1)
            layout.addLayout(reward)
        if row.unlocked and row.unlocked_at:
            layout.addSpacing(4)
            date = GardenDateService().format_date(row.unlocked_at)
            layout.addWidget(_label(f"Unlocked {date}", 12, secondary=True))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(max(1, width))

    def sizeHint(self):
        return QSize(350, self.heightForWidth(max(1, self.width())))

    def minimumSizeHint(self):
        return QSize(0, self.layout().minimumSize().height())


class PlantBedsPage(QScrollArea):
    def __init__(self, engine, artwork, parent=None):
        super().__init__(parent)
        self.engine, self.artwork = engine, artwork
        self._rows = None
        self.cards = {}
        self.setObjectName("plantBedsPage")
        self.setAccessibleName("Plant Beds")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        host = QWidget(self)
        host.setObjectName("plantBedsInterior")
        host.setStyleSheet(f"QWidget#plantBedsInterior {{background:{GARDEN_THEME['garden_background']};}}")
        self.setWidget(host)
        outer = QVBoxLayout(host)
        # The shared Progress navigation supplies 8 px of the 12 px top gap.
        outer.setContentsMargins(24, 4, 24, 16)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.content = QWidget(host)
        self.content.setMaximumWidth(1040)
        self.content.setMinimumWidth(0)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        body = QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        title = _label("Plant beds", 16, 600, 22)
        self.count = _label("", 13, 500, 18, secondary=True)
        heading.addWidget(title, 1)
        heading.addWidget(self.count)
        body.addLayout(heading)
        body.addSpacing(4)
        self.starter_summary = _label("", 12, secondary=True)
        self.starter_summary.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        body.addWidget(self.starter_summary)
        body.addSpacing(10)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        body.addLayout(self.grid)
        outer.addWidget(self.content)

    def refresh(self):
        rows = plant_bed_progress(self.engine.state)
        if rows == self._rows:
            return
        self._rows = rows
        position = self.verticalScrollBar().value()
        focused = next((key for key, card in self.cards.items() if card.hasFocus()), None)
        for card in self.cards.values():
            self.grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = {row.bed_id: PlantBedCard(row, self.artwork, self.content)
                      for row in rows if not row.starter}
        self.count.setText(f"{sum(row.unlocked for row in rows)} of {len(rows)} unlocked")
        starters = [str(row.bed_number) for row in rows if row.starter]
        numbers = " and ".join(starters) if len(starters) <= 2 else ", ".join(starters[:-1]) + " and " + starters[-1]
        self.starter_summary.setText(
            f"Beds {numbers} are available from the start." if len(starters) > 1
            else f"Bed {numbers} is available from the start."
        )
        self.starter_summary.setVisible(bool(starters))
        self._reflow()
        if focused in self.cards:
            self.cards[focused].setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(position))

    def _reflow(self):
        if not hasattr(self, "content"):
            return
        width = min(1040, max(1, self.viewport().width() - 48))
        columns = 1 if width < 720 else 2
        self.content.setFixedWidth(width)
        for card in self.cards.values():
            self.grid.removeWidget(card)
        for row in range(len(self.cards)):
            self.grid.setRowMinimumHeight(row, 0)
            self.grid.setRowStretch(row, 0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        cards = tuple(self.cards.values())
        for index, card in enumerate(cards):
            self.grid.addWidget(card, index // columns, index % columns)
        self.content.updateGeometry()

    def reveal_bed(self, bed_id):
        self.refresh()
        card = self.cards.get(str(bed_id))
        if card is not None:
            self.ensureWidgetVisible(card, 0, 12)
            card.setFocus(Qt.FocusReason.OtherFocusReason)
        elif any(row.starter and row.bed_id == str(bed_id) for row in self._rows):
            self.ensureWidgetVisible(self.starter_summary, 0, 12)
            self.starter_summary.setFocus(Qt.FocusReason.OtherFocusReason)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()
