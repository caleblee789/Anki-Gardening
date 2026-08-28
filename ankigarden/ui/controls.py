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

    thumb_radius = 8.0
    thumb_x = (
        TOGGLE_VISUAL_WIDTH - 10.0
        if checked else 10.0
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(
        GARDEN_THEME["action_text"]
        if checked else GARDEN_THEME["text_primary"]
    ))
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
        self.setIconSize(QSize(TOGGLE_VISUAL_WIDTH, TOGGLE_VISUAL_HEIGHT))
        if label:
            self.setAccessibleName(label)
        self.toggled.connect(self._sync_state)
        self._sync_state(self.isChecked())

    def _sync_state(self, checked: bool) -> None:
        self.setIcon(_switch_icon(bool(checked), self.isEnabled()))
        self.setProperty("switchState", "on" if checked else "off")
        name = str(self.accessibleName() or self.text() or "Garden setting")
        self.setAccessibleDescription(
            f"{name} is {'on' if checked else 'off'}."
        )
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def setChecked(self, checked: bool) -> None:
        """Refresh the icon even when callers temporarily block signals."""

        super().setChecked(bool(checked))
        self._sync_state(bool(checked))

    def changeEvent(self, event: Any) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._sync_state(self.isChecked())


GardenSwitch = GardenToggleSwitch


__all__ = ["GardenSwitch", "GardenToggleSwitch"]
