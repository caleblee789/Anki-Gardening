"""Shared, high-DPI environment preview composition for native surfaces.

Scenery is rendered directly. Garden Features (and their legacy Weather aliases)
are composited over the selected scenery, so discovery cards show the earned
visual state instead of a generic symbol.
Callers may provide their own branded fallback while the shared success path
remains pixel-identical across the Garden dashboard and Session Summary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from ..environment import DEFAULT_SCENERY_ID, CatalogItem


logger = logging.getLogger(__name__)


try:  # Source-contract tests can import this module without Anki/Qt present.
    from aqt.qt import QPainter, QPixmap, QRectF, Qt

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only outside Anki/Qt.
    QPainter = object  # type: ignore[assignment,misc]
    QPixmap = object  # type: ignore[assignment,misc]
    QRectF = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc

try:  # QtSvg is optional on a few host/export surfaces.
    from aqt.qt import QSvgRenderer
except Exception:  # pragma: no cover - host export variance.
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore[no-redef]
    except Exception:  # pragma: no cover
        try:
            from PyQt5.QtSvg import QSvgRenderer  # type: ignore[no-redef]
        except Exception:  # pragma: no cover
            QSvgRenderer = None  # type: ignore[assignment]


EnvironmentFallback = Callable[..., Any]


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError(
            "environment preview art requires Anki's Qt runtime"
        ) from _QT_IMPORT_ERROR


def preview_source_pixmap(path: Any) -> Any:
    """Load raster or SVG preview art through the host's Qt renderer."""

    _require_qt()
    if not path:
        return QPixmap()
    source_path = Path(str(path))
    if source_path.suffix.lower() != ".svg":
        return QPixmap(str(source_path))
    if QSvgRenderer is None:
        return QPixmap()
    renderer = QSvgRenderer(str(source_path))
    if not renderer.isValid():
        return QPixmap()
    default_size = renderer.defaultSize()
    width = max(1, int(default_size.width()))
    height = max(1, int(default_size.height()))
    preview = QPixmap(width, height)
    preview.fill(Qt.GlobalColor.transparent)
    painter = QPainter(preview)
    try:
        renderer.render(painter, QRectF(0, 0, width, height))
    finally:
        painter.end()
    return preview


def cover_pixmap(source: Any, width: int, height: int) -> Any:
    """Return a center-cropped preview without distortion or upscaling."""

    _require_qt()
    if source.isNull() or width <= 0 or height <= 0:
        return QPixmap()
    cover_scale = max(
        float(width) / max(1, source.width()),
        float(height) / max(1, source.height()),
    )
    scale = min(1.0, cover_scale)
    scaled_width = max(1, round(source.width() * scale))
    scaled_height = max(1, round(source.height() * scale))
    scaled = (
        source
        if scaled_width == source.width() and scaled_height == source.height()
        else source.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    result = QPixmap(width, height)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(
            (width - scaled.width()) // 2,
            (height - scaled.height()) // 2,
            scaled,
        )
    finally:
        painter.end()
    return result


def contain_pixmap(source: Any, width: int, height: int) -> Any:
    """Return a centered transparent preview without cropping or upscaling."""

    _require_qt()
    if source.isNull() or width <= 0 or height <= 0:
        return QPixmap()
    scale = min(
        1.0,
        float(width) / max(1, source.width()),
        float(height) / max(1, source.height()),
    )
    scaled_width = max(1, round(source.width() * scale))
    scaled_height = max(1, round(source.height() * scale))
    scaled = (
        source
        if scaled_width == source.width() and scaled_height == source.height()
        else source.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    result = QPixmap(width, height)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(
            (width - scaled.width()) // 2,
            (height - scaled.height()) // 2,
            scaled,
        )
    finally:
        painter.end()
    return result


def environment_preview_pixmap(
    engine: Any,
    item: CatalogItem,
    width: int,
    height: int,
    *,
    scenery_id: str = DEFAULT_SCENERY_ID,
    fallback: EnvironmentFallback | None = None,
) -> Any:
    """Render Scenery directly or one isolated Garden Feature cutout."""

    _require_qt()

    def missing(*, category: str, item_key: str, source_path: Any) -> Any:
        if fallback is None:
            return QPixmap()
        return fallback(
            width,
            height,
            category=category,
            item_key=item_key,
            source_path=source_path,
        )

    try:
        if item.kind == "garden_feature":
            feature_resolver = getattr(
                engine,
                "resolve_garden_feature_preview_asset",
                None,
            )
            feature_asset = (
                feature_resolver(item.item_id)
                if callable(feature_resolver)
                else None
            )
            feature_path = getattr(feature_asset, "path", None)
            feature = contain_pixmap(
                preview_source_pixmap(feature_path),
                width,
                height,
            )
            if feature.isNull():
                return missing(
                    category="garden_feature",
                    item_key=item.item_id,
                    source_path=feature_path,
                )
            return feature

        base_asset = engine.resolve_scenery_preview_asset(item.item_id)
        base_path = getattr(base_asset, "path", None)
        result = cover_pixmap(
            preview_source_pixmap(base_path),
            width,
            height,
        )
        if result.isNull():
            return missing(
                category=item.kind,
                item_key=item.item_id,
                source_path=base_path,
            )
        return result
    except Exception:
        logger.exception(
            "Anki Garden: environment preview composition failed for %s",
            item.item_id,
        )
        return missing(
            category=item.kind,
            item_key=item.item_id,
            source_path=None,
        )


__all__ = [
    "contain_pixmap",
    "cover_pixmap",
    "environment_preview_pixmap",
    "preview_source_pixmap",
]
