"""Gardening Trophies in Progress → Trophy Room, also reached from the house."""
from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QColor, QFrame, QGridLayout, QHBoxLayout, QLabel, QLinearGradient,
    QPainter, QPen, QPixmap, QPushButton, QRadialGradient, QRectF, QScrollArea,
    QSize, QSizePolicy, Qt, QVBoxLayout, QWidget,
)

from ..trophies import TrophyPresentation, trophy_presentations
from .copy import inline_detail_copy, learner_card_copy
from .formatters import GardenDateService


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
        self.setMinimumWidth(300)
        self.setFixedHeight(190 if compact else 300)

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
        self.setFixedHeight(round(min(210 if self.compact else 340,
                                     max(145, self.width() * .34))))
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(780, 190 if self.compact else 300)

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
        bay_width = inner.width() / 3
        for i, trophy in enumerate(self.trophies):
            bay = QRectF(inner.left() + i * bay_width, inner.top(), bay_width, inner.height())
            light = QRadialGradient(bay.center().x(), bay.top() + 12, bay.height() * 1.25)
            light.setColorAt(0, QColor(224, 199, 128, 43))
            light.setColorAt(1, QColor(4, 17, 12, 150))
            p.fillRect(bay, light)
            p.setPen(QPen(QColor(189, 151, 96, 90), 1))
            p.drawLine(bay.topLeft(), bay.topRight())
            shelf_y = bay.bottom() - 4
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
                p.setOpacity(1 if trophy.unlocked else .28)
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
        self.setStyleSheet("""
            QFrame#achievementTrophyShowcase { background:#10291f; border:1px solid #395446; border-radius:14px; }
            QFrame#achievementTrophyShowcase QLabel { background:transparent; border:none; color:#e2e9d9; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        self.count = QLabel()
        self.count.setStyleSheet("color:#b2c6b4;font-size:12px;")
        row.addWidget(self.count)
        outer.addLayout(row)
        self.case = TrophyCase(engine, compact, self)
        outer.addWidget(self.case)
        self.details = QGridLayout()
        self.details.setHorizontalSpacing(22)
        self.details.setVerticalSpacing(7)
        outer.addLayout(self.details)
        self._labels: list[tuple[QLabel, ...]] = []
        for column in range(3):
            labels = []
            for row_index in range(4):
                label = QLabel()
                label.setWordWrap(True)
                label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                if row_index == 0:
                    label.setStyleSheet("font-size:14px;font-weight:600;color:#e9d6a7;")
                else:
                    label.setTextFormat(Qt.TextFormat.RichText)
                    label.setStyleSheet("font-size:12px;color:#b6c4b5;padding-top:4px;")
                self.details.addWidget(label, row_index, column)
                labels.append(label)
            self.details.setColumnStretch(column, 1)
            self._labels.append(tuple(labels))
        self.refresh()

    def refresh(self) -> None:
        trophies = trophy_presentations(self.engine.state)
        self.count.setText(f"{sum(t.unlocked for t in trophies)} / 3 unlocked")
        self.case.refresh(trophies)
        for trophy, labels in zip(trophies, self._labels):
            name, requirement, buff, obtained = labels
            name.setText(trophy.name)
            requirement.setText(inline_detail_copy("Unlock Requirement", trophy.requirement + (
                "" if trophy.unlocked else f"\nLocked · {trophy.progress_text}"
            )))
            buff.setText(inline_detail_copy("Permanent Bonus", learner_card_copy(trophy.buff)))
            buff.setAccessibleDescription(("Permanent bonus. " if trophy.unlocked else "Bonus after unlocking. ") + trophy.buff)
            date = (GardenDateService().format_date(trophy.obtained_at, scheduler_day=trophy.obtained_at if len(trophy.obtained_at) == 10 else "") if trophy.obtained_at
                    else "Not recorded" if trophy.unlocked else "Not yet obtained")
            obtained.setText(inline_detail_copy("Date obtained", date))
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
        host.setStyleSheet("QWidget#trophyRoomInterior {background:#0b2019;}")
        self.setWidget(host)
        outer = QVBoxLayout(host)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(16)
        header = QHBoxLayout()
        title = QLabel("Gardening Trophies")
        title.setStyleSheet("color:#ecdfbf;font-size:24px;font-weight:600;")
        header.addWidget(title)
        header.addStretch()
        self.back_button = QPushButton("Back to Garden")
        self.back_button.setAccessibleName("Back to Garden")
        self.back_button.clicked.connect(back)
        self.back_button.setStyleSheet("QPushButton {color:#e2e9d9;background:#244a39;border:1px solid #59735b;border-radius:8px;padding:9px 14px;}")
        header.addWidget(self.back_button)
        outer.addLayout(header)
        intro = QLabel("Each trophy unlocks a permanent bonus; all three work together.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#b7c8b8;font-size:14px;")
        outer.addWidget(intro)
        self.showcase = TrophyShowcase(engine, parent=host)
        outer.addWidget(self.showcase)
        outer.addStretch(1)

    def refresh(self) -> None:
        self.showcase.refresh()
