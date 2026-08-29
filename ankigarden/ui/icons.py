"""One code-native SVG icon family for Garden product surfaces."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


ICON_VIEWBOX = 24
ICON_STROKE_WIDTH = 1.8

# Paths deliberately use round caps/joins and the same 24 px grid.  Feature
# surfaces consume names from this registry instead of mixing glyphs, emoji,
# and platform-dependent standard icons.
GARDEN_ICON_PATHS: dict[str, str] = {
    # Keep the close mark as two independent strokes. QtSvg has historically
    # dropped the second sub-path of a compound, open path at some DPRs.
    "close": '<path d="M6 6L18 18"/><path d="M18 6L6 18"/>',
    "check": '<path d="m5 12.5 4.2 4.2L19 7"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.6 2.6L16.5 9"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "chevron-left": '<path d="m15 5-7 7 7 7"/>',
    "chevron-right": '<path d="m9 5 7 7-7 7"/>',
    "chevron-up": '<path d="m5 15 7-7 7 7"/>',
    "chevron-down": '<path d="m5 9 7 7 7-7"/>',
    "rename": '<path d="m4 20 4.2-1 10.3-10.3a2.1 2.1 0 0 0-3-3L5.2 16 4 20Z"/><path d="m13.8 7.4 3 3M4 20h6"/>',
    "coin": '<circle cx="12" cy="12" r="8"/><path d="M9 10.2c0-1.3 1.2-2.2 3-2.2s3 .8 3 2-1.2 1.7-3 2-3 .8-3 2 1.2 2 3 2 3-.9 3-2.2M12 6v12"/>',
    "growth": '<path d="M12 20V9M12 14c-4.8 0-7-2.6-7-7 4.7 0 7 2.4 7 7Zm0-2c4.8 0 7-2.6 7-7-4.7 0-7 2.4-7 7Z"/>',
    "streak": '<path d="M13.5 3.5c.5 3-1 4.2-2.3 5.6C9.8 10.5 9 12 10 14c-2.2-.7-3-2.5-2.7-4.4C5.3 11.2 4 13.3 4 15.5A8 8 0 0 0 20 15c0-4.5-3-8.2-6.5-11.5ZM12 20c-1.8 0-3.2-1.3-3.2-3 0-1.3.8-2.3 2.1-3.5-.1 1.6.8 2.2 1.5 2.8.7-.9 1.1-1.8.8-3.2 1.4 1.2 2 2.5 2 3.7 0 1.8-1.4 3.2-3.2 3.2Z"/>',
    "stage": '<path d="M12 3l2.3 4.7 5.2.8-3.8 3.7.9 5.2-4.6-2.5-4.6 2.5.9-5.2-3.8-3.7 5.2-.8L12 3Z"/>',
    "collection": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h5"/>',
    "storage": '<path d="M5 8h14v11H5z"/><path d="M4 5h16v3H4zM9 12h6"/>',
    "find": '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 4 4M10.5 13V9M10.5 10.5c-2.3 0-3.5-1.2-3.5-3.5 2.3 0 3.5 1.2 3.5 3.5Zm0-1.5c2.3 0 3.5-1.2 3.5-3.5-2.3 0-3.5 1.2-3.5 3.5Z"/>',
    "environment": '<path d="M3.5 18.5h17v-13h-17z"/><path d="m4 16 5-5 3 3 2.5-2.5 5.5 5M16.5 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/>',
    "fertilizer": '<path d="M9 3h6v4l2 2v10a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9l2-2V3Z"/><path d="M9 7h6M9.5 14h5M12 11v6"/>',
    "booster": '<path d="m13.5 2-7 11h5L10.5 22l7-12h-5l1-8Z"/>',
    "reviews": '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8 8h8M8 12h5M10 16l4-2-4-2v4Z"/>',
    "completed-collection": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="m7.5 12 2.6 2.6 6.4-6.4"/>',
    "lock": '<rect x="6" y="10" width="12" height="10" rx="2"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/>',
    "settings": '<circle cx="12" cy="12" r="3.25"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1"/>',
    "open-garden": '<path d="M3.5 20.5h17M5.5 20.5v-9l6.5-6 6.5 6v9M9 20.5v-5h6v5"/><path d="M12 11V5M12 8.5c-2.7 0-4-1.5-4-4 2.7 0 4 1.4 4 4Zm0-1.5c2.7 0 4-1.5 4-4-2.7 0-4 1.4-4 4Z"/>',
    "nursery": '<path d="M4 20h16M6 20v-8l6-6 6 6v8M9 20v-5h6v5M5 9l7-6 7 6"/>',
    "plant": '<path d="M12 20v-9M12 14c-4 0-6-2.1-6-6 4 0 6 2 6 6Zm0-3c4 0 6-2.1 6-6-4 0-6 2-6 6ZM7 20h10"/>',
    "warning": '<path d="M12 4 3 20h18L12 4Z"/><path d="M12 9v5M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 0 1 5.2 1c0 2-2.7 2.1-2.7 4M12 17h.01"/>',
    "reset": '<path d="M4 7v5h5"/><path d="M5.5 10a7 7 0 1 1 .8 6.8"/>',
    "refresh": '<path d="M4 7v5h5M20 17v-5h-5"/><path d="M5.7 9.7A7.2 7.2 0 0 1 18.8 7M18.3 14.3A7.2 7.2 0 0 1 5.2 17"/>',
    "overflow": '<path d="M5 12h.01M12 12h.01M19 12h.01" stroke-width="3.2"/>',
    "bed": '<path d="M4 15c2.2-2 4.8-3 8-3s5.8 1 8 3v4H4v-4Z"/><path d="M7 12V8h10v4M9 8V5h6v3"/>',
    "completed-beds": '<path d="M3.5 15c2.3-2 5-3 8.5-3s6.2 1 8.5 3v4.5h-17V15Z"/><path d="m8 8.5 2.4 2.4 5.6-5.6"/>',
    "currency": '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 9.5c.4-1.2 1.6-2 3.5-2 2.2 0 3.5 1 3.5 2.3 0 3.3-7 1.2-7 4.5 0 1.4 1.4 2.3 3.7 2.3 1.8 0 3.1-.7 3.6-1.9M12 5.5v13"/>',
}


def garden_icon_svg(name: str, *, color: str = "#F2F5EC") -> str:
    """Return a complete SVG payload for a registered icon."""

    key = str(name).strip().lower()
    if key not in GARDEN_ICON_PATHS:
        raise KeyError(f"unknown Garden icon: {name!r}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON_VIEWBOX} {ICON_VIEWBOX}" '
        f'fill="none" stroke="{color}" '
        f'stroke-width="{ICON_STROKE_WIDTH}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{GARDEN_ICON_PATHS[key]}</svg>'
    )


def _svg_renderer_type() -> Any | None:
    """Resolve QtSvg across Anki, PyQt 6, and PyQt 5 export layouts."""

    try:
        from aqt.qt import QSvgRenderer

        if QSvgRenderer is not None:
            return QSvgRenderer
    except Exception:
        pass
    try:
        from PyQt6.QtSvg import QSvgRenderer

        if QSvgRenderer is not None:
            return QSvgRenderer
    except Exception:
        pass
    try:
        from PyQt5.QtSvg import QSvgRenderer

        if QSvgRenderer is not None:
            return QSvgRenderer
    except Exception:
        pass
    return None


def _active_device_pixel_ratio() -> float:
    """Return the active logical-to-physical pixel ratio without importing Qt early."""

    try:
        from aqt.qt import QApplication

        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                return max(1.0, float(screen.devicePixelRatio()))
    except Exception:
        pass
    return 1.0


@lru_cache(maxsize=256)
def _cached_garden_icon_pixmap(
    identity: str,
    logical_size: int,
    color: str,
    device_pixel_ratio: float,
) -> Any | None:
    """Render one immutable icon variant for a normalized cache key."""

    from aqt.qt import QByteArray, QPainter, QPixmap, Qt

    renderer_type = _svg_renderer_type()
    if renderer_type is None:
        return None
    renderer = renderer_type(
        QByteArray(garden_icon_svg(identity, color=color).encode("utf-8"))
    )
    is_valid = getattr(renderer, "isValid", None)
    if callable(is_valid) and not is_valid():
        return None
    physical_size = max(1, int(round(logical_size * device_pixel_ratio)))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    # Paint into the pixmap while it still exposes its physical dimensions.
    # Setting the DPR first makes QtSvg fit the SVG to the physical extent and
    # then apply the painter's logical DPR transform a second time. On Retina
    # that clips the lower/right half of every multi-stroke icon: an X becomes
    # one slash, a chevron becomes one segment, and a circle becomes an arc.
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    set_device_pixel_ratio = getattr(pixmap, "setDevicePixelRatio", None)
    if callable(set_device_pixel_ratio):
        set_device_pixel_ratio(device_pixel_ratio)
    if pixmap.isNull():
        return None
    return pixmap


def garden_icon_pixmap(
    identity: str,
    logical_size: int,
    *,
    color: str = "#F2F5EC",
    device_pixel_ratio: float | None = None,
) -> Any | None:
    """Return a cached, DPR-aware pixmap for a registered icon identity."""

    key = str(identity).strip().lower()
    if key not in GARDEN_ICON_PATHS:
        raise KeyError(f"unknown Garden icon: {identity!r}")
    size = int(logical_size)
    if size <= 0:
        raise ValueError("logical icon size must be positive")
    dpr = (
        _active_device_pixel_ratio()
        if device_pixel_ratio is None
        else float(device_pixel_ratio)
    )
    if dpr <= 0:
        raise ValueError("device pixel ratio must be positive")
    return _cached_garden_icon_pixmap(key, size, str(color), round(dpr, 3))


def clear_garden_icon_pixmap_cache() -> None:
    """Clear cached Qt objects when the host application is shutting down."""

    _cached_garden_icon_pixmap.cache_clear()


def garden_icon(
    name: str,
    *,
    color: str = "#F2F5EC",
    logical_size: int = 40,
    device_pixel_ratio: float | None = None,
) -> Any:
    """Build a QIcon lazily from the shared DPR-aware pixmap cache."""

    from aqt.qt import QIcon

    pixmap = garden_icon_pixmap(
        name,
        logical_size,
        color=color,
        device_pixel_ratio=device_pixel_ratio,
    )
    return QIcon() if pixmap is None else QIcon(pixmap)
