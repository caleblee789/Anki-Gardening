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
    QPainter,
    QPen,
    QPointF,
    QPixmap,
    QRectF,
    QSize,
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
        name = str(self.accessibleName() or self.text() or "Garden setting")
        self.setAccessibleDescription(
            f"{name} is {'on' if checked else 'off'}."
        )
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.setFixedSize(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT)

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


GardenSwitch = GardenToggleSwitch


__all__ = ["GardenSwitch", "GardenToggleSwitch"]
