"""Cached, alpha-aware plant thumbnails for compact native surfaces.

Plant stage artwork is intentionally authored on a generous transparent
canvas. Scaling that entire canvas into a reviewer label makes the visible
plant look tiny. This helper crops by manifest placement metadata, preserves
the optical centre, and caches the high-DPI result without altering source
assets.
"""

from __future__ import annotations

from collections import OrderedDict
from math import isfinite, sqrt
from pathlib import Path
from typing import Any


try:  # Projection and source-contract tests run without Anki/Qt installed.
    from aqt.qt import QPainter, QPixmap, Qt

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - only outside Anki.
    QPainter = object  # type: ignore[assignment,misc]
    QPixmap = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc


_PIXMAP_CACHE_LIMIT = 72
_PIXMAP_CACHE: "OrderedDict[tuple[Any, ...], Any]" = OrderedDict()

THUMBNAIL_STAGE_FILL: dict[str, float] = {
    "seed": 0.66,
    "sprout": 0.73,
    "young": 0.80,
    "mature": 0.87,
    "flowering": 0.91,
    "rare": 1.00,
}

# Optical correction may enlarge a small authored silhouette, but each stage
# still owns a stable compact-canvas envelope.  Without this second bound a
# scene-calibrated early plant can grow larger than the next stage in Reviewer
# and Nursery thumbnails even though the surrounding canvas never changes.
THUMBNAIL_STAGE_MAX_FILL: dict[str, float] = {
    "seed": 0.76,
    "sprout": 0.73,
    "young": 0.90,
    "mature": 0.96,
    "flowering": 0.98,
    "rare": 1.00,
}


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError("normalized plant art requires Anki's Qt runtime") from _QT_IMPORT_ERROR


def _placement_value(placement: Any, key: str, default: Any) -> Any:
    if isinstance(placement, dict):
        return placement.get(key, default)
    return getattr(placement, key, default) if placement is not None else default


def padded_preview_bounds(
    value: Any,
    *,
    padding: float = 0.10,
) -> tuple[float, float, float, float]:
    """Expand normalized content bounds without restoring the empty canvas."""

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return (0.0, 0.0, 1.0, 1.0)
    try:
        x, y, width, height = (float(part) for part in value)
    except (TypeError, ValueError):
        return (0.0, 0.0, 1.0, 1.0)
    if (
        not all(isfinite(part) for part in (x, y, width, height))
        or width <= 0
        or height <= 0
    ):
        return (0.0, 0.0, 1.0, 1.0)
    safe_padding = max(0.0, min(0.5, float(padding)))
    left = max(0.0, x - width * safe_padding)
    top = max(0.0, y - height * safe_padding)
    right = min(1.0, x + width * (1.0 + safe_padding))
    bottom = min(1.0, y + height * (1.0 + safe_padding))
    if right <= left or bottom <= top:
        return (0.0, 0.0, 1.0, 1.0)
    return (left, top, right - left, bottom - top)


def _asset_parts(asset_or_path: Any, placement: Any) -> tuple[str, Any]:
    if asset_or_path is None:
        return "", placement
    asset_path = getattr(asset_or_path, "path", None)
    if asset_path is not None:
        return str(asset_path), (
            placement
            if placement is not None
            else getattr(asset_or_path, "placement", None)
        )
    return str(asset_or_path), placement


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calibrated_thumbnail_scale(placement: Any) -> float:
    """Return an explicit thumbnail scale or a bounded optical calibration.

    ``visual_scale_correction`` is authored for soil-plane scene layout. When
    a raw manifest row has no independent thumbnail scale, invert only the
    square root of that scene correction. This preserves species character
    while preventing compact early-stage art from becoming an unreadable dot.
    """

    explicit = _placement_value(placement, "thumbnail_scale", None)
    if explicit is not None:
        return max(0.5, min(1.5, _number(explicit, 1.0)))
    visual = max(
        0.5,
        min(
            1.5,
            _number(
                _placement_value(placement, "visual_scale_correction", 1.0),
                1.0,
            ),
        ),
    )
    return max(0.85, min(1.20, 1.0 / sqrt(visual)))


def calibrated_thumbnail_fill(stage: Any, placement: Any) -> float:
    """Combine authored optical scale with the canonical stage envelope."""

    stage_key = str(stage or "").lower()
    base_fill = THUMBNAIL_STAGE_FILL.get(stage_key, 0.92)
    maximum_fill = THUMBNAIL_STAGE_MAX_FILL.get(stage_key, 1.00)
    return min(maximum_fill, base_fill * calibrated_thumbnail_scale(placement))


def _placement_fingerprint(placement: Any) -> tuple[Any, ...]:
    return tuple(
        repr(_placement_value(placement, key, None))
        for key in (
            "thumbnail_bounds",
            "art_bounds",
            "visible_bounds",
            "thumbnail_optical_center",
            "focal_point",
            "thumbnail_scale",
            "visual_scale_correction",
            "max_visible_width",
            "max_visible_height",
            "thumbnail_safe_padding",
        )
    )


def _source_identity(path: str) -> tuple[Any, ...]:
    if not path:
        return ("", 0, 0)
    try:
        stat = Path(path).stat()
        return (str(Path(path).resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    except (OSError, RuntimeError, ValueError):
        return (path, 0, 0)


def clear_plant_art_cache() -> None:
    """Drop decoded thumbnails, primarily for asset hot-reload tooling."""

    _PIXMAP_CACHE.clear()


def normalized_plant_pixmap(
    asset_or_path: Any,
    placement: Any = None,
    *,
    stage: str,
    logical_size: int = 108,
    device_pixel_ratio: float = 2.0,
) -> Any:
    """Render one metadata-cropped, optically centred high-DPI thumbnail."""

    _require_qt()
    path, placement = _asset_parts(asset_or_path, placement)
    logical_size = max(1, int(logical_size))
    ratio = max(1.0, min(4.0, _number(device_pixel_ratio, 2.0)))
    cache_key = (
        *_source_identity(path),
        str(stage or "").lower(),
        logical_size,
        round(ratio, 2),
        *_placement_fingerprint(placement),
    )
    cached = _PIXMAP_CACHE.get(cache_key)
    if cached is not None:
        _PIXMAP_CACHE.move_to_end(cache_key)
        return QPixmap(cached)

    source = QPixmap(path) if path else QPixmap()
    if source.isNull():
        return QPixmap()
    bounds = _placement_value(
        placement,
        "thumbnail_bounds",
        _placement_value(
            placement,
            "art_bounds",
            _placement_value(placement, "visible_bounds", None),
        ),
    )
    safe_padding = _number(
        _placement_value(placement, "thumbnail_safe_padding", 0.10),
        0.10,
    )
    left, top, width, height = padded_preview_bounds(
        bounds,
        padding=safe_padding,
    )
    source_width, source_height = source.width(), source.height()
    crop_x = max(0, min(source_width - 1, round(left * source_width)))
    crop_y = max(0, min(source_height - 1, round(top * source_height)))
    crop_width = max(1, min(source_width - crop_x, round(width * source_width)))
    crop_height = max(1, min(source_height - crop_y, round(height * source_height)))
    cropped = source.copy(crop_x, crop_y, crop_width, crop_height)
    if cropped.isNull():
        cropped = source
        left, top, width, height = (0.0, 0.0, 1.0, 1.0)

    # Reviewer art uses a stable logical canvas. Stage fill and per-asset
    # optical calibration change only the art inside that unchanged region.
    stage_fill = calibrated_thumbnail_fill(stage, placement)
    target = max(16, min(logical_size, round(logical_size * stage_fill)))
    max_visible_width = max(
        0.1,
        min(1.0, _number(_placement_value(placement, "max_visible_width", 1.0), 1.0)),
    )
    max_visible_height = max(
        0.1,
        min(1.0, _number(_placement_value(placement, "max_visible_height", 1.0), 1.0)),
    )
    pixel_canvas = max(1, round(logical_size * ratio))
    target_width = max(
        1,
        min(
            round(target * ratio),
            cropped.width(),
            round(pixel_canvas * max_visible_width),
        ),
    )
    target_height = max(
        1,
        min(
            round(target * ratio),
            cropped.height(),
            round(pixel_canvas * max_visible_height),
        ),
    )
    scaled = cropped.scaled(
        target_width,
        target_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    optical = _placement_value(
        placement,
        "thumbnail_optical_center",
        _placement_value(placement, "focal_point", (0.5, 0.5)),
    )
    try:
        optical_x, optical_y = float(optical[0]), float(optical[1])
    except (TypeError, ValueError, IndexError):
        optical_x, optical_y = (0.5, 0.5)
    relative_x = max(0.0, min(1.0, (optical_x - left) / max(width, 0.0001)))
    relative_y = max(0.0, min(1.0, (optical_y - top) / max(height, 0.0001)))
    draw_x = round(pixel_canvas / 2 - relative_x * scaled.width())
    draw_y = round(pixel_canvas / 2 - relative_y * scaled.height())
    draw_x = max(0, min(pixel_canvas - scaled.width(), draw_x))
    draw_y = max(0, min(pixel_canvas - scaled.height(), draw_y))

    result = QPixmap(pixel_canvas, pixel_canvas)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(draw_x, draw_y, scaled)
    painter.end()
    result.setDevicePixelRatio(ratio)

    _PIXMAP_CACHE[cache_key] = QPixmap(result)
    _PIXMAP_CACHE.move_to_end(cache_key)
    while len(_PIXMAP_CACHE) > _PIXMAP_CACHE_LIMIT:
        _PIXMAP_CACHE.popitem(last=False)
    return result


__all__ = [
    "THUMBNAIL_STAGE_FILL",
    "THUMBNAIL_STAGE_MAX_FILL",
    "calibrated_thumbnail_fill",
    "calibrated_thumbnail_scale",
    "clear_plant_art_cache",
    "normalized_plant_pixmap",
    "padded_preview_bounds",
]
