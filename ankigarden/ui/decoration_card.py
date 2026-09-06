"""A small read-only inspector for the equipped garden decoration."""
from __future__ import annotations

from typing import Any

from aqt.qt import QFrame, QLabel, QPoint, QRect, Qt, QVBoxLayout

from ..environment import GARDEN_FEATURE_CATALOG
from .copy import garden_bonus_summary, inline_detail_copy
from .formatters import GardenDateService
from .theme import GARDEN_THEME


class DecorationInfoCard(QFrame):
    def __init__(self, engine: Any, scene: Any) -> None:
        super().__init__(scene, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.engine = engine
        self.scene = scene
        self.setObjectName("gardenDecorationInspector")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"""
            QFrame#gardenDecorationInspector {{
                background:{GARDEN_THEME['plant_popover_bg']};
                border:1px solid {GARDEN_THEME['plant_popover_border']};border-radius:12px;
            }}
            QLabel {{background:transparent;border:0;color:{GARDEN_THEME['text_primary']};}}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self.heading = QLabel("Garden Decoration")
        self.heading.setStyleSheet(f"font-size:17px;font-weight:600;color:{GARDEN_THEME['text_primary']};")
        layout.addWidget(self.heading)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{GARDEN_THEME['plant_popover_divider']};border:0;")
        layout.addWidget(divider)
        self.name = QLabel()
        self.name.setWordWrap(True)
        self.name.setStyleSheet("font-size:15px;font-weight:600;")
        self.bonus = QLabel()
        self.bonus.setWordWrap(True)
        self.bonus.setTextFormat(Qt.TextFormat.RichText)
        self.bonus.setStyleSheet(f"font-size:13px;color:{GARDEN_THEME['text_secondary']};")
        self.obtained = QLabel()
        self.obtained.setWordWrap(True)
        self.obtained.setTextFormat(Qt.TextFormat.RichText)
        self.obtained.setStyleSheet(f"font-size:13px;color:{GARDEN_THEME['text_secondary']};")
        layout.addWidget(self.name)
        layout.addWidget(self.bonus)
        layout.addWidget(self.obtained)

    def open_decoration(self, feature_id: str) -> None:
        item = GARDEN_FEATURE_CATALOG.get(str(feature_id))
        anchor = self.scene.decoration_geometry()
        if item is None or anchor is None:
            return
        self.name.setText(item.name)
        bonus = garden_bonus_summary(item.item_id, item.effect)
        self.bonus.setText(inline_detail_copy("Garden Bonus", bonus))
        obtained_at = self.engine.garden_decoration_obtained_at(item.item_id)
        obtained = GardenDateService().format_date(obtained_at, scheduler_day=obtained_at if len(obtained_at) == 10 else "") if obtained_at else "Not recorded"
        self.obtained.setText(inline_detail_copy("Date obtained", obtained))
        self.setAccessibleName(f"Garden Decoration. {item.name}. Garden Bonus: {bonus}. Date obtained: {obtained}.")
        self.setFixedWidth(min(304, max(240, self.scene.width() - 24)))
        self.adjustSize()
        canvas = QRect(self.scene.mapToGlobal(QPoint(0, 0)), self.scene.size()).adjusted(12, 12, -12, -12)
        point = self.scene.mapToGlobal(anchor.topRight().toPoint())
        x = min(canvas.right() - self.width(), max(canvas.left(), point.x() + 10))
        y = min(canvas.bottom() - self.height(), max(canvas.top(), point.y() + round(anchor.height() * .45)))
        self.move(x, y)
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
