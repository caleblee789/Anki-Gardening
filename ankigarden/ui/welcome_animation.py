"""Finite, silent welcome artwork, anchored to the starter's existing bed."""
from __future__ import annotations

import math

from aqt.qt import QColor, QPainterPath, QPen, QPointF, QRadialGradient, Qt


WELCOME_DURATION = 2.8


def welcome_wobble(elapsed: float) -> float:
    phase = min(1.0, max(0.0, (elapsed - 0.35) / 1.6))
    return math.sin(phase * math.pi * 6) * math.sin(phase * math.pi) * 4.0


def draw_welcome_shower(painter, anchor, width: float, elapsed: float, canvas) -> None:
    """Draw a bounded set of leaves and Coins; never derive or grant rewards."""
    if not 0 <= elapsed < WELCOME_DURATION:
        return
    x, y = anchor
    scale = max(0.65, min(1.3, width / 160))
    fade = min(1.0, elapsed / 0.25, (WELCOME_DURATION - elapsed) / 0.55)
    painter.save()
    painter.setClipRect(canvas)
    painter.setPen(Qt.PenStyle.NoPen)
    glow = QRadialGradient(QPointF(x, y - 12 * scale), 85 * scale)
    glow.setColorAt(0, QColor(153, 230, 166, round(92 * fade)))
    glow.setColorAt(0.55, QColor(117, 219, 161, round(35 * fade)))
    glow.setColorAt(1, QColor(117, 219, 161, 0))
    painter.setBrush(glow)
    painter.drawEllipse(QPointF(x, y - 12 * scale), 85 * scale, 60 * scale)

    # Twelve staggered leaves converge into the soil. Paths and counts are
    # deterministic, independent of study volume and the ambient frame rate.
    for index in range(12):
        age = (elapsed - 0.22 - index * 0.065) / 0.85
        if not 0 <= age <= 1:
            continue
        spread = ((index * 47) % 101 - 50) * 1.65 * scale
        px = x + spread * (1 - age) + math.sin(age * math.pi * 2 + index) * 10 * scale
        py = y - 20 * scale - (1 - age * age) * 145 * scale
        painter.save()
        painter.setOpacity(min(1.0, age * 6, (1 - age) * 7))
        painter.translate(px, py)
        painter.rotate(index * 31 + age * 150)
        painter.scale(scale, scale)
        leaf = QPainterPath(QPointF(-7, 0))
        leaf.cubicTo(-3, -8, 5, -7, 8, -2)
        leaf.cubicTo(4, 6, -3, 7, -7, 0)
        painter.setBrush(QColor("#BEE6A0" if index % 3 else "#E8C568"))
        painter.drawPath(leaf)
        painter.setPen(QPen(QColor("#628E65"), 0.8))
        painter.drawLine(QPointF(-5, 0), QPointF(5, -1))
        painter.restore()

    # Coins resolve upwards toward the wallet, separate from plant Growth.
    for index in range(6):
        age = (elapsed - 1.48 - index * 0.07) / 0.67
        if not 0 <= age <= 1:
            continue
        destination_x = canvas.right() - 36 * scale
        destination_y = canvas.top() + 22 * scale
        eased = age * age
        px = x + (destination_x - x) * eased + (index - 2.5) * 7 * scale * (1 - age)
        py = y - 35 * scale + (destination_y - y + 35 * scale) * eased
        painter.save()
        painter.setOpacity(min(1.0, age * 8, (1 - age) * 5))
        painter.setBrush(QColor("#E8C568"))
        painter.setPen(QPen(QColor("#9E7737"), 1.2))
        painter.drawEllipse(QPointF(px, py), 6 * scale, 6 * scale)
        painter.setPen(QPen(QColor("#FFF0B6"), 1.2))
        painter.drawLine(QPointF(px, py - 3 * scale), QPointF(px, py + 3 * scale))
        painter.restore()

    # A few quiet glints finish the landing; no flashing or full-scene dimmer.
    for index in range(6):
        age = (elapsed - 1.05 - index * 0.08) / 0.65
        if not 0 <= age <= 1:
            continue
        angle = index * math.pi / 3
        radius = (25 + age * 34) * scale
        px, py = x + math.cos(angle) * radius, y - 28 * scale + math.sin(angle) * radius * 0.45
        size = math.sin(age * math.pi) * 4 * scale
        painter.setPen(QPen(QColor("#FFF0B6"), 1.4))
        painter.drawLine(QPointF(px - size, py), QPointF(px + size, py))
        painter.drawLine(QPointF(px, py - size), QPointF(px, py + size))
    painter.restore()
