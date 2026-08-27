"""One code-native SVG icon family for Garden product surfaces."""

from __future__ import annotations

from typing import Any


ICON_VIEWBOX = 24
ICON_STROKE_WIDTH = 1.8

# Paths deliberately use round caps/joins and the same 24 px grid.  Feature
# surfaces consume names from this registry instead of mixing glyphs, emoji,
# and platform-dependent standard icons.
GARDEN_ICON_PATHS: dict[str, str] = {
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "coin": '<circle cx="12" cy="12" r="8"/><path d="M9 10.2c0-1.3 1.2-2.2 3-2.2s3 .8 3 2-1.2 1.7-3 2-3 .8-3 2 1.2 2 3 2 3-.9 3-2.2M12 6v12"/>',
    "growth": '<path d="M12 20V9M12 14c-4.8 0-7-2.6-7-7 4.7 0 7 2.4 7 7Zm0-2c4.8 0 7-2.6 7-7-4.7 0-7 2.4-7 7Z"/>',
    "streak": '<path d="M13.5 3.5c.5 3-1 4.2-2.3 5.6C9.8 10.5 9 12 10 14c-2.2-.7-3-2.5-2.7-4.4C5.3 11.2 4 13.3 4 15.5A8 8 0 0 0 20 15c0-4.5-3-8.2-6.5-11.5ZM12 20c-1.8 0-3.2-1.3-3.2-3 0-1.3.8-2.3 2.1-3.5-.1 1.6.8 2.2 1.5 2.8.7-.9 1.1-1.8.8-3.2 1.4 1.2 2 2.5 2 3.7 0 1.8-1.4 3.2-3.2 3.2Z"/>',
    "stage": '<path d="M12 3l2.3 4.7 5.2.8-3.8 3.7.9 5.2-4.6-2.5-4.6 2.5.9-5.2-3.8-3.7 5.2-.8L12 3Z"/>',
    "collection": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h5"/>',
    "lock": '<rect x="6" y="10" width="12" height="10" rx="2"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7a6.9 6.9 0 0 0-.8-1.8l.9-1.9L15 4l-1.9.9a6.9 6.9 0 0 0-1.8-.8L10.5 2h-3l-.7 2.1a6.9 6.9 0 0 0-1.8.8L3.1 4 1 6.1 1.9 8a6.9 6.9 0 0 0-.8 1.8L-1 10.5v3l2.1.7a6.9 6.9 0 0 0 .8 1.8L1 17.9 3.1 20l1.9-.9a6.9 6.9 0 0 0 1.8.8l.7 2.1h3l.7-2.1a6.9 6.9 0 0 0 1.8-.8l1.9.9 2.1-2.1-.9-1.9a6.9 6.9 0 0 0 .8-1.8l2.1-.7Z" transform="translate(3 0) scale(.75)"/>',
    "nursery": '<path d="M4 20h16M6 20v-8l6-6 6 6v8M9 20v-5h6v5M5 9l7-6 7 6"/>',
    "plant": '<path d="M12 20v-9M12 14c-4 0-6-2.1-6-6 4 0 6 2 6 6Zm0-3c4 0 6-2.1 6-6-4 0-6 2-6 6ZM7 20h10"/>',
    "warning": '<path d="M12 4 3 20h18L12 4Z"/><path d="M12 9v5M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 0 1 5.2 1c0 2-2.7 2.1-2.7 4M12 17h.01"/>',
    "reset": '<path d="M4 7v5h5"/><path d="M5.5 10a7 7 0 1 1 .8 6.8"/>',
    "overflow": '<circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/>',
    "bed": '<path d="M4 15c2.2-2 4.8-3 8-3s5.8 1 8 3v4H4v-4Z"/><path d="M7 12V8h10v4M9 8V5h6v3"/>',
}


def garden_icon_svg(name: str, *, color: str = "#F2F5EC") -> str:
    """Return a complete SVG payload for a registered icon."""

    key = str(name).strip().lower()
    if key not in GARDEN_ICON_PATHS:
        raise KeyError(f"unknown Garden icon: {name!r}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON_VIEWBOX} {ICON_VIEWBOX}" '
        f'style="color:{color}" fill="none" stroke="currentColor" '
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


def garden_icon(name: str, *, color: str = "#F2F5EC") -> Any:
    """Build a QIcon lazily so source tooling can import the registry."""

    from aqt.qt import QByteArray, QIcon, QPainter, QPixmap, Qt

    renderer_type = _svg_renderer_type()
    if renderer_type is None:
        return QIcon()
    renderer = renderer_type(
        QByteArray(garden_icon_svg(name, color=color).encode("utf-8"))
    )
    is_valid = getattr(renderer, "isValid", None)
    if callable(is_valid) and not is_valid():
        return QIcon()
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap)
