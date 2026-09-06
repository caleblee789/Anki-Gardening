"""Shop-only optical framing; original Garden placement assets stay unchanged."""
from __future__ import annotations

from aqt.qt import (
    QColor, QLabel, QPainter, QPixmap, QRectF, QRegion, QSize, QSizePolicy, Qt,
)


class ShopProductArtwork(QLabel):
    """Contain a landscape or trim transparent margins around a product cutout."""

    def __init__(self, source: QPixmap, *, item_id: str, landscape: bool = False,
                 locked: bool = False) -> None:
        super().__init__()
        self._landscape = bool(landscape)
        self._locked = bool(locked)
        self._item_id = str(item_id)
        self._source = QPixmap()
        self.setMinimumWidth(0)
        self.setFixedHeight(156 if landscape else 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setProperty("shopProductArtwork", True)
        self.setProperty("catalogArtworkLocked", locked)
        self.set_source(source)

    def set_source(self, source: QPixmap) -> None:
        self._source = QPixmap(source)
        if not self._landscape and not source.isNull() and source.hasAlphaChannel():
            bounds = QRegion(source.mask()).boundingRect()
            if not bounds.isEmpty():
                # Keep a small edge margin around every complete silhouette.
                bounds = bounds.adjusted(-2, -2, 2, 2).intersected(source.rect())
                self._source = source.copy(bounds)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(280, self.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.height())

    def paintEvent(self, event: object) -> None:
        if self._source.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._locked:
            painter.setOpacity(0.38)
        inset = 0 if self._landscape else 4
        available = self.rect().adjusted(inset, inset, -inset, -inset)
        # The narrow Wind Chime needs more height than the broad Watering Station.
        optical = {"wind_chime": 1.0, "harvest_bell": 0.96,
                   "watering_station": 0.92, "herbalist_hourglass": 0.98}.get(self._item_id, 0.96)
        height = available.height() if self._landscape else available.height() * optical
        ratio = min(available.width() / self._source.width(), height / self._source.height(),
                    1.0 / max(1.0, self.devicePixelRatioF()))
        width, height = self._source.width() * ratio, self._source.height() * ratio
        top = (self.height() - height) / 2 if self._landscape else self.height() - inset - height
        rect = QRectF((self.width() - width) / 2, top, width, height)
        painter.drawPixmap(rect, self._source, QRectF(self._source.rect()))
        painter.end()
