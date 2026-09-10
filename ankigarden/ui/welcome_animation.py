"""Finite, silent welcome artwork, anchored to the starter's existing bed."""
from __future__ import annotations

import math

from aqt.qt import QColor, QLinearGradient, QPainterPath, QPen, QPointF, QRadialGradient, Qt


WELCOME_DURATION = 3.4
WELCOME_REVEAL_START = 2.7


def _phase(elapsed: float, start: float, duration: float) -> float:
    return min(1.0, max(0.0, (elapsed - start) / duration))


def _scale(width: float) -> float:
    return max(0.65, min(1.65, width / 160))


def welcome_wobble(elapsed: float) -> float:
    phase = _phase(elapsed, 0.58, 0.85)
    return math.sin(phase * math.pi * 2) * math.sin(phase * math.pi) * 3.0


def welcome_lift(elapsed: float, width: float) -> float:
    """One small grounded bounce; the plant's artwork and growth stage stay intact."""
    return math.sin(_phase(elapsed, 0.58, 0.85) * math.pi) * 9 * _scale(width)


def draw_welcome_glow(painter, anchor, width: float, elapsed: float) -> None:
    """Paint the gathering light behind the plant so its silhouette stays clear."""
    if not 0 <= elapsed < WELCOME_DURATION:
        return
    x, y = anchor
    scale = _scale(width)
    fade = _phase(elapsed, 0, 0.5) * (1 - _phase(elapsed, 2.2, 1.2))
    bloom = math.sin(_phase(elapsed, 0.5, 1.2) * math.pi)
    radius = (95 + bloom * 40) * scale
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.save()
    painter.translate(x, y - 18 * scale)
    painter.scale(1, 0.8)
    glow = QRadialGradient(QPointF(0, 0), radius)
    glow.setColorAt(0, QColor(239, 226, 156, round(135 * fade)))
    glow.setColorAt(0.35, QColor(140, 236, 183, round(82 * fade)))
    glow.setColorAt(1, QColor(111, 226, 175, 0))
    painter.setBrush(glow)
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    painter.restore()
    for index in range(2):
        age = (elapsed - 0.6 - index * 0.18) / 1.1
        if not 0 <= age <= 1:
            continue
        radius = (18 + (1 - (1 - age) ** 3) * 105) * scale
        color = QColor("#F4D98A" if index else "#B5F4D1")
        color.setAlpha(round(155 * (1 - age) ** 2))
        painter.setPen(QPen(color, (2.6 - age) * scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(x, y - 3 * scale), radius, radius * 0.34)
    painter.restore()


def _spark(painter, x: float, y: float, size: float, color: QColor) -> None:
    path = QPainterPath(QPointF(x, y - size))
    path.lineTo(x + size * 0.25, y - size * 0.25)
    path.lineTo(x + size, y)
    path.lineTo(x + size * 0.25, y + size * 0.25)
    path.lineTo(x, y + size)
    path.lineTo(x - size * 0.25, y + size * 0.25)
    path.lineTo(x - size, y)
    path.lineTo(x - size * 0.25, y - size * 0.25)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)


def draw_welcome_shower(painter, anchor, width: float, elapsed: float, canvas) -> None:
    """Draw bounded, deterministic particles; never derive or grant rewards."""
    if not 0 <= elapsed < WELCOME_DURATION:
        return
    x, y = anchor
    scale = _scale(width)
    painter.save()
    painter.setClipRect(canvas)
    painter.setPen(Qt.PenStyle.NoPen)

    # A spiral gathers at the seed, then opens into a fan of drifting leaves.
    for index in range(16):
        age = (elapsed - index * 0.028) / 1.9
        if not 0 <= age <= 1:
            continue
        gather = min(1.0, age / 0.4)
        release = max(0.0, (age - 0.4) / 0.6)
        angle = index * math.tau / 16 + gather * 1.7 + release * 0.55
        radius = (95 * (1 - gather) ** 2 + 12 + 108 * math.sin(release * math.pi / 2)) * scale
        px = x + math.cos(angle) * radius
        py = y - 24 * scale + math.sin(angle) * radius * 0.6 - release * 40 * scale
        painter.save()
        painter.setOpacity(min(1.0, age * 8, (1 - age) * 3))
        painter.translate(px, py)
        painter.rotate(math.degrees(angle) + release * 100)
        painter.scale(scale, scale)
        leaf = QPainterPath(QPointF(-7, 0))
        leaf.cubicTo(-3, -8, 5, -7, 8, -2)
        leaf.cubicTo(4, 6, -3, 7, -7, 0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#BEEAB3" if index % 3 else "#EFD087"))
        painter.drawPath(leaf)
        painter.setPen(QPen(QColor("#67956E"), 0.8))
        painter.drawLine(QPointF(-5, 0), QPointF(5, -1))
        painter.restore()

    # A single expanding burst, with fine trails rather than a flashing screen.
    for index in range(18):
        age = (elapsed - 0.62 - index * 0.018) / 1.2
        if not 0 <= age <= 1:
            continue
        angle = index * math.tau / 18
        distance = (18 + (75 + index % 4 * 14) * (1 - (1 - age) ** 3)) * scale
        px = x + math.cos(angle) * distance
        py = y - 23 * scale + math.sin(angle) * distance * 0.68 - age * 20 * scale
        color = QColor("#FFE9AA" if index % 3 == 0 else "#C7F8D6")
        color.setAlpha(round(220 * math.sin(age * math.pi)))
        trail = (1 - age) * 15 * scale
        painter.setPen(QPen(color, 1.2 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(px - math.cos(angle) * trail, py - math.sin(angle) * trail * 0.68), QPointF(px, py))
        _spark(painter, px, py, math.sin(age * math.pi) * (3 + index % 3) * scale, color)

    # Ten illustrative Coins fan up above the bed; their count is not the grant.
    for index in range(10):
        age = (elapsed - 1.4 - index * 0.045) / 1.12
        if not 0 <= age <= 1:
            continue
        spread = (index - 4.5) * 17 * scale

        def position(t: float) -> QPointF:
            return QPointF(x + spread * math.sin(t * math.pi / 2),
                           y - (28 + (112 + index % 3 * 13) * math.sin(t * math.pi * 0.6)) * scale)

        painter.save()
        painter.setOpacity(min(1.0, age * 8, (1 - age) * 4))
        painter.setPen(Qt.PenStyle.NoPen)
        for step in range(1, 6):
            previous = age - step * 0.028
            if previous < 0:
                continue
            painter.setBrush(QColor(244, 210, 119, round(90 * (1 - step / 6))))
            painter.drawEllipse(position(previous), (3 - step * 0.35) * scale, (3 - step * 0.35) * scale)
        center = position(age)
        radius = 7.5 * scale
        gold = QLinearGradient(center.x() - radius, center.y() - radius, center.x() + radius, center.y() + radius)
        gold.setColorAt(0, QColor("#FFF2BB"))
        gold.setColorAt(0.45, QColor("#F4CE6A"))
        gold.setColorAt(1, QColor("#BD8236"))
        painter.setBrush(gold)
        painter.setPen(QPen(QColor("#9D712E"), scale))
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#FFECB0"), scale))
        painter.drawEllipse(center, radius * 0.65, radius * 0.65)
        painter.drawLine(QPointF(center.x(), center.y() - radius * 0.38), QPointF(center.x(), center.y() + radius * 0.38))
        painter.restore()

    # Slow, staggered glints bridge the burst into the welcome card reveal.
    for index in range(12):
        age = (elapsed - 1.85 - index * 0.07) / 0.78
        if not 0 <= age <= 1:
            continue
        angle = index * 2.4
        radius = (34 + index % 4 * 20) * scale
        color = QColor("#FFF0BB" if index % 2 else "#C7F8D6")
        color.setAlpha(round(210 * math.sin(age * math.pi)))
        _spark(painter, x + math.cos(angle) * radius,
               y - 30 * scale + math.sin(angle) * radius * 0.6 - age * 12 * scale,
               math.sin(age * math.pi) * 4 * scale, color)
    painter.restore()
