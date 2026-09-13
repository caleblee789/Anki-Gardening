"""A compact read-only inspector for the equipped garden decoration."""
from __future__ import annotations

from typing import Any

from aqt.qt import QColor, QEvent, QFrame, QHBoxLayout, QLabel, QPainter, QPen, QPoint, QRectF, QSize, QPushButton, QTimer, Qt, QVBoxLayout

from ..environment import GARDEN_FEATURE_CATALOG
from .copy import garden_bonus_summary
from .formatters import GardenDateService
from .icons import garden_icon
from .theme import GARDEN_THEME, TextRole, text_style


class DecorationInfoCard(QFrame):
    def __init__(self, engine: Any, scene: Any) -> None:
        super().__init__(scene, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.engine = engine
        self.scene = scene
        self._feature_id = ""
        self._position_pending = False
        self.setObjectName("gardenDecorationInspector")
        self.setProperty("anchoredGardenInspector", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"""
            QFrame[anchoredGardenInspector='true'] {{background:transparent;border:0;}}
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
        self.name.setStyleSheet(text_style(TextRole.CARD_TITLE))
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
        self.bonus.setStyleSheet(f"{text_style(TextRole.BODY, include_weight=False)}color:{GARDEN_THEME['text_secondary']};")
        self.obtained = QLabel(self)
        self.obtained.setWordWrap(True)
        self.obtained.setTextFormat(Qt.TextFormat.PlainText)
        self.obtained.setStyleSheet(f"{text_style(TextRole.SECONDARY, include_weight=False)}color:{GARDEN_THEME['text_secondary']};")
        layout.addWidget(self.bonus)
        layout.addWidget(self.obtained)
        scene.installEventFilter(self)
        scene.cardGeometryChanged.connect(self._schedule_position)

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
        anchor = self.scene.decoration_visible_geometry()
        if item is None or anchor is None:
            return
        self._feature_id = item.item_id
        self.name.setText(item.name)
        bonus = garden_bonus_summary(item.item_id, item.effect)
        self.bonus.setText(bonus)
        obtained_at = self.engine.garden_decoration_obtained_at(item.item_id)
        obtained = GardenDateService().format_date(obtained_at, scheduler_day=obtained_at if len(obtained_at) == 10 else "") if obtained_at else ""
        self.obtained.setText(f"Obtained {obtained}" if obtained else "")
        self.obtained.setVisible(bool(obtained))
        self.setAccessibleName(f"{item.name}. {bonus}" + (f" Obtained {obtained}." if obtained else ""))
        self._position_at(anchor)
        self.scene.set_decoration_inspected(True)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        # Native popup placement can adjust the first requested geometry.
        self._schedule_position()

    def _schedule_position(self) -> None:
        if self.isVisible() and not self._position_pending:
            self._position_pending = True
            QTimer.singleShot(0, self._reposition)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.scene:
            if event.type() == QEvent.Type.Hide:
                self.hide()
            elif event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.LayoutRequest):
                self._schedule_position()
        return super().eventFilter(watched, event)

    def _reposition(self) -> None:
        self._position_pending = False
        if not self.isVisible():
            return
        anchor = self.scene.decoration_visible_geometry()
        if anchor is None or str(self.scene.scene.get("garden_feature", "")) != self._feature_id:
            self.hide()
            return
        self._position_at(anchor)

    def _position_at(self, anchor: QRectF) -> None:
        # Keep descriptions inside the garden and near their visible artwork.
        canvas = QRectF(self.scene.rect())
        canvas = canvas.adjusted(12, 12, -12, -12)
        self.bonus.ensurePolished()
        required_width = self.bonus.fontMetrics().horizontalAdvance(self.bonus.text()) + 34
        preferred_width = min(round(canvas.width()), max(304, min(360, required_width)))
        geometry = self.scene.geometry_layout()
        obstacles = [QRectF(bounds.x, bounds.y, bounds.width, bounds.height)
                     for bed in geometry.beds
                     for bounds in (bed.visible_region, bed.planter_bounds)]
        controls = [QRectF(widget.geometry()) for widget in self.scene.findChildren(QFrame)
                    if widget.parentWidget() is self.scene and widget.isVisible()
                    and (widget.property("movePanel") or widget.property("toastRegion"))]
        widths = {preferred_width}
        for side_width in (anchor.left() - canvas.left() - 12,
                           canvas.right() - anchor.right() - 12):
            if side_width >= preferred_width:
                widths.add(min(preferred_width, round(side_width)))
        candidates = []
        for width in sorted(widths, reverse=True):
            self.setFixedWidth(width)
            self.layout().invalidate()
            height = max(self.layout().minimumSize().height(), self.layout().totalHeightForWidth(width))
            xs = (anchor.right() + 12, anchor.left() - width - 12,
                  anchor.center().x() - width / 2, canvas.left(), canvas.right() - width)
            ys = (anchor.center().y() - height / 2, anchor.top(), anchor.top() - height - 12,
                  anchor.bottom() + 12,
                  *range(round(canvas.top()), round(max(canvas.top() + 1, canvas.bottom() - height + 1)), 24))
            for x in xs:
                for y in ys:
                    x = max(canvas.left(), min(x, canvas.right() - width))
                    y = max(canvas.top(), min(y, canvas.bottom() - height))
                    rect = QRectF(x, y, width, height)
                    overlaps = [rect.intersected(other) for other in obstacles]
                    covered_art = sum(max(0, other.width()) * max(0, other.height()) for other in overlaps)
                    dx = max(anchor.left() - rect.right(), rect.left() - anchor.right(), 0)
                    dy = max(anchor.top() - rect.bottom(), rect.top() - anchor.bottom(), 0)
                    alignment = (rect.center().x() - anchor.center().x()) ** 2 + (rect.center().y() - anchor.center().y()) ** 2
                    score = (rect.intersects(anchor), any(rect.intersects(other) for other in controls),
                             .25 * covered_art + dx ** 2 + dy ** 2 + alignment + 4 * (preferred_width - width))
                    candidates.append((score, rect))
        rect = min(candidates, key=lambda candidate: candidate[0])[1]
        self.setFixedSize(round(rect.width()), round(rect.height()))
        self.move(self.scene.mapToGlobal(QPoint(round(rect.x()), round(rect.y()))))
        actual_origin = self.scene.mapFromGlobal(self.mapToGlobal(QPoint(0, 0)))
        actual_rect = QRectF(actual_origin.x(), actual_origin.y(), self.width(), self.height())
        self.scene.set_inspector_connector_geometry(actual_rect, anchor)

    def hideEvent(self, event: Any) -> None:
        self.scene.set_decoration_inspected(False)
        self.scene.set_inspector_connector_geometry(None)
        super().hideEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.scene._feature_hotspot.setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        super().keyPressEvent(event)


class LockedBedInfoCard(DecorationInfoCard):
    """The compact inspector links directly to shared bed progression."""

    def __init__(self, scene: Any, resolve_bed: Any, open_bed_progress: Any) -> None:
        super().__init__(None, scene)
        self.setObjectName("gardenLockedBedInspector")
        self._resolve_bed = resolve_bed
        self._open_bed_progress = open_bed_progress
        self._bed_slot: int | None = None
        self._bed_id = ""
        self.close_button.setToolTip("Close unlock requirement")
        self.close_button.setAccessibleName("Close unlock requirement")
        self.view_achievement = QPushButton("View bed progress", self)
        self.view_achievement.setMinimumHeight(30)
        self.view_achievement.setStyleSheet(
            f"QPushButton {{color:{GARDEN_THEME['text_primary']};background:{GARDEN_THEME['plant_popover_raised']};"
            f"border:1px solid {GARDEN_THEME['secondary_border']};border-radius:8px;padding:0 10px;font-weight:600;}}"
            f"QPushButton:hover {{background:{GARDEN_THEME['secondary_hover']};}}"
            f"QPushButton:focus {{border-color:{GARDEN_THEME['focus_ring']};}}"
        )
        self.view_achievement.clicked.connect(self._navigate)
        self.layout().addWidget(self.view_achievement, 0, Qt.AlignmentFlag.AlignLeft)

    def open_bed(self, slot: int) -> None:
        self._bed_slot = int(slot)
        if not self._refresh_target():
            return
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _refresh_target(self) -> bool:
        target = self._resolve_bed(self._bed_slot) if self._bed_slot is not None else None
        if target is None or target.unlocked:
            self.hide()
            return False
        bed = self.scene.geometry_layout().bed(self._bed_slot)
        if bed is None:
            self.hide()
            return False
        self._bed_id = target.bed_id
        self.name.setText(f"Bed {self._bed_slot + 1} locked")
        self.bonus.setText(target.requirement)
        self.obtained.setText(f"{target.current} of {target.target} species")
        self.obtained.show()
        self.setAccessibleName(f"{self.name.text()}. {target.requirement}. {self.obtained.text()}")
        self._position_at(QRectF(bed.planter_bounds.x, bed.planter_bounds.y,
                                bed.planter_bounds.width, bed.planter_bounds.height))
        return True

    def _reposition(self) -> None:
        self._position_pending = False
        if self.isVisible():
            self._refresh_target()

    def _navigate(self) -> None:
        bed_id = self._bed_id
        self.hide()
        if bed_id:
            self._open_bed_progress(bed_id)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.scene.setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        super().keyPressEvent(event)
