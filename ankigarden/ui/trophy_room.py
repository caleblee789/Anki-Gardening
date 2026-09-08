"""Gardening Trophies in Progress → Trophy Room, also reached from the house."""
from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QBoxLayout, QColor, QEvent, QFrame, QGridLayout, QHBoxLayout, QLabel, QLinearGradient,
    QPainter, QPen, QPixmap, QPushButton, QRadialGradient, QRectF, QScrollArea,
    QSize, QSizePolicy, QTimer, Qt, QVBoxLayout, QWidget,
)

from ..trophies import TrophyPresentation, trophy_presentations
from .controls import GardenWrappingLabel
from .formatters import GardenDateService
from .theme import (
    GARDEN_THEME, TextRole, apply_text_role, apply_control_variant,
    BUTTON_VARIANT_SECONDARY, ButtonSize, apply_button_size,
)


class TrophyCase(QWidget):
    """Resolution-independent walnut case; each cutout rests on its shelf."""

    def __init__(self, engine: Any, compact: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.engine = engine
        self.compact = compact
        self.trophies: tuple[TrophyPresentation, ...] = ()
        self._art: dict[str, tuple[QPixmap, tuple[float, ...]]] = {}
        self.setAccessibleName("Gardening Trophies display case")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(190 if compact else 250)

    def refresh(self, trophies: tuple[TrophyPresentation, ...]) -> None:
        self.trophies = trophies
        for trophy in trophies:
            if trophy.asset_id in self._art:
                continue
            asset = self.engine.resolve_item_asset(trophy.asset_id)
            if asset is not None:
                self._art[trophy.asset_id] = (
                    QPixmap(str(asset.path)), tuple(asset.placement.art_bounds)
                )
        self.setAccessibleDescription(". ".join(
            f"{item.name}: {item.status}. {item.buff}. {item.requirement}."
            for item in trophies
        ))
        self.update()

    def resizeEvent(self, event) -> None:
        single = len(self.trophies) == 1
        self.setFixedHeight(round(min(190 if self.compact else 220 if single else 250,
                                     max(180 if single else 145, self.width() * (.55 if single else .30)))))
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(780, 190 if self.compact else 250)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        wood = QLinearGradient(box.topLeft(), box.bottomRight())
        for pos, color in ((0, "#856246"), (.12, "#493526"), (.60, "#392c23"), (1, "#70523a")):
            wood.setColorAt(pos, QColor(color))
        p.setPen(QPen(QColor("#b79865"), 1))
        p.setBrush(wood)
        p.drawRoundedRect(box, 13, 13)
        inner = box.adjusted(13, 13, -13, -22)
        p.fillRect(inner, QColor("#10281f"))
        # Three evenly framed recesses share a continuous, grounded shelf.
        bay_width = inner.width() / max(1, len(self.trophies))
        for i, trophy in enumerate(self.trophies):
            bay = QRectF(inner.left() + i * bay_width, inner.top(), bay_width, inner.height())
            light = QRadialGradient(bay.center().x(), bay.top() + 12, bay.height() * 1.25)
            light.setColorAt(0, QColor(224, 199, 128, 43))
            light.setColorAt(1, QColor(4, 17, 12, 150))
            p.fillRect(bay, light)
            p.setPen(QPen(QColor(189, 151, 96, 90), 1))
            p.drawLine(bay.topLeft(), bay.topRight())
            shelf_y = bay.bottom() - 1
            art = self._art.get(trophy.asset_id)
            if art is not None and not art[0].isNull():
                pixmap, bounds = art
                l, t, w, h = bounds
                source = QRectF(l * pixmap.width(), t * pixmap.height(),
                                w * pixmap.width(), h * pixmap.height())
                scale = min((bay.width() - 34) / source.width(),
                            (bay.height() - 25) / source.height())
                target = QRectF(bay.center().x() - source.width() * scale / 2,
                                shelf_y - source.height() * scale,
                                source.width() * scale, source.height() * scale)
                p.save()
                p.translate(target.center().x(), shelf_y)
                p.scale(target.width() * .45, 4)
                shadow = QRadialGradient(0, 0, 1)
                shadow.setColorAt(0, QColor(0, 0, 0, 130))
                shadow.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(shadow)
                p.drawEllipse(QRectF(-1, -1, 2, 2))
                p.restore()
                p.setOpacity(1 if trophy.unlocked else .38)
                p.drawPixmap(target, pixmap, source)
                p.setOpacity(1)
            if i:
                p.fillRect(QRectF(bay.left() - 3, bay.top(), 6, bay.height() + 4), wood)
                p.setPen(QPen(QColor(201, 174, 115, 105), 1))
                p.drawLine(bay.topLeft(), bay.bottomLeft())
        shelf = QRectF(inner.left() - 3, inner.bottom(), inner.width() + 6, 9)
        shelf_light = QLinearGradient(shelf.topLeft(), shelf.bottomLeft())
        shelf_light.setColorAt(0, QColor("#bb9260"))
        shelf_light.setColorAt(.22, QColor("#805d3b"))
        shelf_light.setColorAt(1, QColor("#35271c"))
        p.fillRect(shelf, shelf_light)
        p.setPen(QPen(QColor(215, 196, 145, 100), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box.adjusted(5, 5, -5, -5), 9, 9)
        p.end()


class TrophyShowcase(QFrame):
    def __init__(self, engine: Any, *, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.compact = compact
        self.setObjectName("achievementTrophyShowcase")
        self.setStyleSheet(f"""
            QFrame#achievementTrophyShowcase {{ background:{GARDEN_THEME['raised_surface']}; border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:12px; }}
            QFrame#achievementTrophyShowcase QLabel {{ background:transparent; border:none; color:{GARDEN_THEME['text_primary']}; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)
        row = QHBoxLayout()
        self.header_row = row
        self.count = QLabel()
        apply_text_role(self.count, TextRole.SECONDARY)
        self.count.setStyleSheet(f"color:{GARDEN_THEME['text_secondary']};")
        row.addWidget(self.count)
        outer.addLayout(row)
        self.case = TrophyCase(engine, compact, self)
        self.details = QGridLayout()
        self.details.setHorizontalSpacing(16)
        self.details.setVerticalSpacing(12)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addLayout(self.details)
        self._labels: list[tuple[QLabel, ...]] = []
        self._panels: list[QWidget] = []
        self._single_cases: list[TrophyCase] = []
        self._stacked: bool | None = None
        for column in range(3):
            panel = QWidget(self)
            panel.setMinimumWidth(0)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(6, 0, 6, 0)
            panel_layout.setSpacing(4)
            panel_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            labels = []
            for row_index in range(5):
                label = GardenWrappingLabel()
                label.setWordWrap(True)
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                label.setMinimumWidth(0)
                if row_index == 0:
                    apply_text_role(label, TextRole.CARD_TITLE)
                    label.setStyleSheet(f"color:{GARDEN_THEME['coin_accent']};")
                else:
                    apply_text_role(label, TextRole.METADATA if row_index == 4 else TextRole.SECONDARY)
                    label.setStyleSheet(f"color:{GARDEN_THEME['text_muted' if row_index == 4 else 'text_secondary']};")
                label.setTextFormat(Qt.TextFormat.PlainText)
                panel_layout.addWidget(label)
                labels.append(label)
            self._panels.append(panel)
            self._single_cases.append(TrophyCase(engine, compact, self))
            self._labels.append(tuple(labels))
        self._reflow()
        self.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        # The three descriptions need room for their natural text size even
        # when the host width itself has not changed (for example larger text).
        detail_width = max((label.fontMetrics().horizontalAdvance("Unlock progress") + 28
                            for labels in self._labels for label in labels[1:4]), default=0)
        stacked = self.width() < max(720, detail_width * 3 + 56)
        if stacked == self._stacked:
            return
        self._stacked = stacked
        while self.details.count():
            self.details.takeAt(0)
        for column in range(3):
            self.details.setColumnStretch(column, 1 if not stacked or column == 0 else 0)
        self.case.setVisible(not stacked)
        if not stacked:
            self.details.addWidget(self.case, 0, 0, 1, 3)
        for column, (case, panel) in enumerate(zip(self._single_cases, self._panels)):
            case.setVisible(stacked)
            if stacked:
                self.details.addWidget(case, column * 2, 0)
                self.details.addWidget(panel, column * 2 + 1, 0)
            else:
                self.details.addWidget(panel, 1, column)
        self.updateGeometry()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            QTimer.singleShot(0, self._reflow)

    def refresh(self) -> None:
        trophies = trophy_presentations(self.engine.state)
        self.count.setText(f"{sum(t.unlocked for t in trophies)} of {len(trophies)} unlocked")
        self.case.refresh(trophies)
        for trophy, labels, case in zip(trophies, self._labels, self._single_cases):
            case.refresh((trophy,))
            name, status, buff, requirement, obtained = labels
            name.setText(trophy.name)
            active = trophy.unlocked and bool(getattr(self.engine.state, "trophy_activation_ms", {}).get(trophy.trophy_id))
            status.setText(trophy.status)
            status.setStyleSheet(f"color:{GARDEN_THEME['action_accent' if active else 'text_secondary']};")
            requirement.setText(f"{trophy.requirement}\nUnlock progress: {trophy.progress_text}")
            requirement.setVisible(not trophy.unlocked)
            bonus_label = "Permanent bonus" if active else "Bonus when unlocked"
            effect = trophy.buff
            if trophy.trophy_id == "golden_trowel":
                effect += "\n" + self.engine.overflow_destination_summary()
            buff.setText(effect)
            buff.setAccessibleDescription(bonus_label + ". " + effect)
            date = (GardenDateService().format_date(trophy.obtained_at, scheduler_day=trophy.obtained_at if len(trophy.obtained_at) == 10 else "") if trophy.obtained_at
                    else "")
            obtained.setText(f"Unlocked {date}" if date else "Unlock date unavailable" if trophy.unlocked else "")
            obtained.setVisible(trophy.unlocked)
        self.setAccessibleName("Gardening Trophies")


class TrophyRoomPage(QScrollArea):
    def __init__(self, engine: Any, back: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("trophyRoomPage")
        self.setAccessibleName("Trophy Room")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget(self)
        host.setObjectName("trophyRoomInterior")
        host.setStyleSheet(f"QWidget#trophyRoomInterior {{background:{GARDEN_THEME['garden_background']};}}")
        self.setWidget(host)
        outer = QVBoxLayout(host)
        outer.setContentsMargins(24, 12, 24, 20)
        outer.setSpacing(12)
        header = QHBoxLayout()
        self.header_layout = header
        header.setSpacing(12)
        title = GardenWrappingLabel("Trophies")
        self.title = title
        title.setMinimumWidth(0)
        title.setWordWrap(True)
        apply_text_role(title, TextRole.SCREEN_TITLE)
        header.addWidget(title, 1)
        outer.addLayout(header)
        intro = GardenWrappingLabel("Unlocked trophies grant permanent bonuses automatically.")
        intro.setWordWrap(True)
        apply_text_role(intro, TextRole.SECONDARY)
        intro.setStyleSheet(f"color:{GARDEN_THEME['text_secondary']};")
        outer.addWidget(intro)
        self.showcase = TrophyShowcase(engine, parent=host)
        self.showcase.header_row.removeWidget(self.showcase.count)
        header.addWidget(self.showcase.count)
        outer.addWidget(self.showcase)
        outer.addStretch(1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_header()

    def _sync_header(self) -> None:
        if not hasattr(self, "showcase"):
            return
        needed = self.title.fontMetrics().horizontalAdvance(self.title.text()) + self.showcase.count.sizeHint().width() + 12
        compact = self.viewport().width() - 48 < needed
        self.header_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        self.header_layout.setAlignment(self.showcase.count, Qt.AlignmentFlag.AlignLeft if compact else Qt.AlignmentFlag.AlignVCenter)

    def refresh(self) -> None:
        self.showcase.refresh()
