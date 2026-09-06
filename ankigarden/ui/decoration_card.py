"""A compact read-only inspector for the equipped garden decoration."""
from __future__ import annotations

from typing import Any

from aqt.qt import QColor, QFrame, QHBoxLayout, QLabel, QPainter, QPen, QPoint, QRectF, QSize, QPushButton, Qt, QVBoxLayout

from ..environment import GARDEN_FEATURE_CATALOG
from .copy import garden_bonus_summary
from .formatters import GardenDateService
from .icons import garden_icon
from .theme import GARDEN_THEME


class DecorationInfoCard(QFrame):
    def __init__(self, engine: Any, scene: Any) -> None:
        super().__init__(scene, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.engine = engine
        self.scene = scene
        self.setObjectName("gardenDecorationInspector")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"""
            QFrame#gardenDecorationInspector {{background:transparent;border:0;}}
            QLabel {{background:transparent;border:0;color:{GARDEN_THEME['text_primary']};}}
            QPushButton {{background:transparent;border:0;padding:0;border-radius:5px;}}
            QPushButton:hover {{background:{GARDEN_THEME['selected_surface']};}}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.name = QLabel(self)
        self.name.setMinimumWidth(0)
        self.name.setWordWrap(True)
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setStyleSheet("font-size:17px;font-weight:600;")
        self.heading = self.name
        header.addWidget(self.name, 1)
        self.close_button = QPushButton(self)
        self.close_button.setFixedSize(26, 26)
        self.close_button.setIcon(garden_icon("close", color=GARDEN_THEME["text_secondary"]))
        self.close_button.setIconSize(QSize(14, 14))
        self.close_button.setToolTip("Close decoration details")
        self.close_button.setAccessibleName("Close decoration details")
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        self.bonus = QLabel(self)
        self.bonus.setWordWrap(True)
        self.bonus.setTextFormat(Qt.TextFormat.PlainText)
        self.bonus.setStyleSheet(f"font-size:13px;color:{GARDEN_THEME['text_secondary']};")
        self.obtained = QLabel(self)
        self.obtained.setWordWrap(True)
        self.obtained.setTextFormat(Qt.TextFormat.PlainText)
        self.obtained.setStyleSheet(f"font-size:13px;color:{GARDEN_THEME['text_secondary']};")
        layout.addWidget(self.bonus)
        layout.addWidget(self.obtained)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border = QColor(GARDEN_THEME["focus_ring"])
        border.setAlpha(72)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(GARDEN_THEME["plant_popover_bg"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)

    def open_decoration(self, feature_id: str) -> None:
        item = GARDEN_FEATURE_CATALOG.get(str(feature_id))
        anchor = self.scene.decoration_geometry()
        if item is None or anchor is None:
            return
        self.name.setText(item.name)
        bonus = garden_bonus_summary(item.item_id, item.effect)
        self.bonus.setText(bonus)
        obtained_at = self.engine.garden_decoration_obtained_at(item.item_id)
        obtained = GardenDateService().format_date(obtained_at, scheduler_day=obtained_at if len(obtained_at) == 10 else "") if obtained_at else ""
        self.obtained.setText(f"Obtained {obtained}" if obtained else "")
        self.obtained.setVisible(bool(obtained))
        self.setAccessibleName(f"{item.name}. {bonus}" + (f" Obtained {obtained}." if obtained else ""))
        self.setFixedWidth(min(304, max(1, self.scene.width() - 24)))
        self.adjustSize()
        canvas = self.scene.rect().adjusted(12, 12, -12, -12)
        # Prefer a side with little artwork underneath. All geometry is local
        # until the final move to the popup's global coordinate system.
        obstacles = [self.scene.plant_geometry(str(plant.get("plant_id", "")))
                     for plant in self.scene.scene.get("plants", [])]
        candidates = []
        xs = (anchor.right() + 12, anchor.left() - self.width() - 12,
              anchor.center().x() - self.width() / 2, canvas.left(),
              canvas.right() - self.width())
        ys = (anchor.top(), anchor.top() - self.height() - 12, anchor.bottom() + 12,
              *range(canvas.top(), max(canvas.top() + 1, canvas.bottom() - self.height() + 1), 24))
        for x in xs:
            for y in ys:
                x = max(canvas.left(), min(x, canvas.right() - self.width()))
                y = max(canvas.top(), min(y, canvas.bottom() - self.height()))
                rect = QRectF(x, y, self.width(), self.height())
                selected_overlap = rect.intersected(anchor)
                overlaps = [rect.intersected(QRectF(other)) for other in obstacles if other is not None]
                covered_art = sum(max(0, other.width()) * max(0, other.height()) for other in overlaps)
                distance = (rect.center().x() - anchor.center().x()) ** 2 + (rect.center().y() - anchor.center().y()) ** 2
                score = (not selected_overlap.isEmpty(), covered_art, distance)
                candidates.append((score, rect))
        rect = min(candidates, key=lambda candidate: candidate[0])[1]
        self.move(self.scene.mapToGlobal(QPoint(round(rect.x()), round(rect.y()))))
        self.scene.set_decoration_inspected(True)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def hideEvent(self, event: Any) -> None:
        self.scene.set_decoration_inspected(False)
        super().hideEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.scene._feature_hotspot.setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        super().keyPressEvent(event)
