"""Shared native Garden controls that require Qt painting.

Dependency-light sizes and colors remain in :mod:`ankigarden.ui.theme`.  This
module owns the corresponding interactive widgets so Settings, Appearance,
and future dialogs do not recreate state visuals independently.
"""

from __future__ import annotations

from typing import Any

from aqt.qt import (
    QCheckBox,
    QColor,
    QEvent,
    QIcon,
    QLabel,
    QLayout,
    QPainter,
    QPen,
    QPointF,
    QPixmap,
    QRectF,
    QRect,
    QSize,
    QSizePolicy,
    QTimer,
    Qt,
    QWidget,
)

from .theme import (
    GARDEN_THEME,
    TOGGLE_VISUAL_HEIGHT,
    TOGGLE_VISUAL_WIDTH,
)


def _switch_icon(checked: bool, enabled: bool) -> QIcon:
    """Paint a conventional track and positional thumb at logical size."""

    pixmap = QPixmap(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setOpacity(1.0 if enabled else 0.48)

    bounds = QRectF(
        0.5,
        0.5,
        float(TOGGLE_VISUAL_WIDTH - 1),
        float(TOGGLE_VISUAL_HEIGHT - 1),
    )
    painter.setPen(QPen(QColor(
        GARDEN_THEME["growth_accent"]
        if checked else GARDEN_THEME["strong_border"]
    ), 1.0))
    painter.setBrush(QColor(
        GARDEN_THEME["action_accent"]
        if checked else GARDEN_THEME["disabled_surface"]
    ))
    radius = TOGGLE_VISUAL_HEIGHT / 2 - 0.5
    painter.drawRoundedRect(bounds, radius, radius)

    thumb_radius = 9.0
    thumb_x = (
        TOGGLE_VISUAL_WIDTH - 11.0
        if checked else 11.0
    )
    painter.setPen(Qt.PenStyle.NoPen)
    # The enabled mint track always uses the same light thumb as the off
    # state. A dark thumb reads as a hole rather than a movable control.
    painter.setBrush(QColor(GARDEN_THEME["text_primary"]))
    painter.drawEllipse(
        QPointF(thumb_x, TOGGLE_VISUAL_HEIGHT / 2),
        thumb_radius,
        thumb_radius,
    )
    painter.end()
    return QIcon(pixmap)


class GardenToggleSwitch(QCheckBox):
    """Keyboard-operable switch whose state is visible by thumb position."""

    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setProperty("toggleSwitch", True)
        self.setProperty("gardenRole", "switch")
        # Retain QCheckBox semantics, but own exactly one 38 x 22 visual. The
        # native indicator plus an icon produced a duplicate, clipped thumb on
        # Retina displays even when QSS attempted to collapse the indicator.
        self.setFixedSize(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT)
        self.setStyleSheet(
            "QCheckBox {"
            f"min-width:{TOGGLE_VISUAL_WIDTH}px;max-width:{TOGGLE_VISUAL_WIDTH}px;"
            f"min-height:{TOGGLE_VISUAL_HEIGHT}px;max-height:{TOGGLE_VISUAL_HEIGHT}px;"
            "padding:0;border:0;background:transparent;"
            "} QCheckBox::indicator {width:0;height:0;border:0;}"
        )
        self.setIconSize(QSize(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT))
        if label:
            self.setAccessibleName(label)
        self.toggled.connect(self._sync_state)
        self._sync_state(self.isChecked())

    def _sync_state(self, checked: bool) -> None:
        self.setIcon(_switch_icon(bool(checked), self.isEnabled()))
        self.setProperty("switchState", "on" if checked else "off")
        self.setProperty("switchThumbTone", "light")
        self._sync_accessible_description()
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.setFixedSize(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT)

    def setAccessibleDescription(self, description: str) -> None:
        """Keep the setting explanation when its checked state changes."""

        self._setting_description = str(description or "").strip()
        self._sync_accessible_description()

    def _sync_accessible_description(self) -> None:
        description = str(getattr(self, "_setting_description", "") or "").rstrip(". ")
        state = "On" if self.isChecked() else "Off"
        super().setAccessibleDescription(f"{description}. {state}." if description else f"{state}.")

    def setChecked(self, checked: bool) -> None:
        """Refresh the icon even when callers temporarily block signals."""

        super().setChecked(bool(checked))
        self._sync_state(bool(checked))

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._sync_state(self.isChecked())

    def paintEvent(self, event: Any) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setOpacity(1.0 if self.isEnabled() else 0.48)
            checked = bool(self.isChecked())
            bounds = QRectF(
                0.5,
                0.5,
                float(TOGGLE_VISUAL_WIDTH - 1),
                float(TOGGLE_VISUAL_HEIGHT - 1),
            )
            border_color = (
                GARDEN_THEME["growth_accent"]
                if checked else GARDEN_THEME["strong_border"]
            )
            if self.hasFocus() and bool(self.property("keyboardFocusVisible")):
                border_color = GARDEN_THEME["focus_ring"]
            painter.setPen(QPen(QColor(border_color), 1.0))
            painter.setBrush(QColor(
                GARDEN_THEME["action_accent"]
                if checked else GARDEN_THEME["disabled_surface"]
            ))
            radius = TOGGLE_VISUAL_HEIGHT / 2 - 0.5
            painter.drawRoundedRect(bounds, radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(GARDEN_THEME["text_primary"]))
            painter.drawEllipse(
                QPointF(
                    TOGGLE_VISUAL_WIDTH - 11.0 if checked else 11.0,
                    TOGGLE_VISUAL_HEIGHT / 2,
                ),
                9.0,
                9.0,
            )
        finally:
            painter.end()


class GardenWrappingLabel(QLabel):
    """Reserve every wrapped line when a scroll page is narrower than its text."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def _fit_height(self) -> None:
        if self.width() > 0:
            # QLabel.heightForWidth includes its current minimum. Release the
            # previous measurement before measuring a wider line, otherwise a
            # briefly narrow parent permanently leaves oversized blank rows.
            self.setMinimumHeight(0)
            height = max(int(self.property("textLineHeight") or 0),
                         self.fontMetrics().height(), self.heightForWidth(self.width()))
            self.setMinimumHeight(height)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            QTimer.singleShot(0, self._fit_height)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._fit_height()


GardenSwitch = GardenToggleSwitch


class GardenFlowLayout(QLayout):
    """Wrap intact inline controls using their measured sizes and normal page flow."""

    def __init__(self, parent=None, *, spacing=12, row_spacing=6, justify=False):
        super().__init__(parent)
        self._items = []
        self.row_spacing = row_spacing
        self.justify = justify
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), measure=True)

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, measure=False)

    def _arrange(self, rect, *, measure):
        rows, row, used = [], [], 0
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            width = min(rect.width(), size.width())
            if row and used + self.spacing() + width > rect.width():
                rows.append(row)
                row, used = [], 0
            height = item.heightForWidth(width) if item.hasHeightForWidth() else size.height()
            row.append((item, width, height))
            used += width + (self.spacing() if len(row) > 1 else 0)
        if row:
            rows.append(row)
        y = rect.y()
        for row in rows:
            height = max(h for _, _, h in row)
            gap = self.spacing()
            if self.justify and len(row) > 1:
                gap = max(gap, (rect.width() - sum(w for _, w, _ in row)) // (len(row) - 1))
            x = rect.x()
            for item, width, item_height in row:
                if not measure:
                    item.setGeometry(QRect(x, y + (height - item_height) // 2, width, item_height))
                x += width + gap
            y += height + self.row_spacing
        return y - rect.y() - (self.row_spacing if rows else 0)


__all__ = ["GardenSwitch", "GardenToggleSwitch", "GardenWrappingLabel", "GardenFlowLayout"]
