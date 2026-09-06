"""Shared manifest-backed artwork thumbnail for compact Garden receipts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..asset_manager import bundled_ui_asset_path
from .environment_art import cover_pixmap, preview_source_pixmap
from .icons import _active_device_pixel_ratio
from .plant_art import normalized_plant_pixmap


try:  # Pure model tests import receipt modules without Anki's Qt runtime.
    from aqt.qt import QLabel, QPixmap, Qt

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - only outside Anki.
    QLabel = object  # type: ignore[assignment,misc]
    QPixmap = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc


FALLBACK_UI_ASSET_ID = "garden_placeholder"


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError("GardenAssetThumbnail requires Anki's Qt runtime") from _QT_IMPORT_ERROR


def _path_from_asset(value: Any) -> Path | None:
    raw = getattr(value, "path", value)
    if not raw:
        return None
    candidate = Path(str(raw))
    return candidate if candidate.is_file() else None


def _bundled_ui_path(asset_id: str) -> Path | None:
    return bundled_ui_asset_path(asset_id)


class GardenAssetThumbnail(QLabel):  # type: ignore[misc,valid-type]
    """One artwork label with shared resolution, scaling, and safe fallback."""

    def __init__(
        self,
        parent: Any,
        *,
        engine: Any | None,
        asset_id: str,
        asset_type: str,
        width: int,
        height: int | None = None,
        stage: str = "",
        explicit_path: str = "",
        rarity: str = "",
        fallback_asset_id: str = FALLBACK_UI_ASSET_ID,
    ) -> None:
        _require_qt()
        super().__init__(parent)
        self._engine = engine
        self._asset_id = str(asset_id or "")
        self._asset_type = str(asset_type or "ui")
        self._stage = str(stage or "")
        self._fallback_asset_id = str(fallback_asset_id or FALLBACK_UI_ASSET_ID)
        logical_width = max(1, int(width))
        logical_height = max(1, int(height if height is not None else width))
        self.setFixedSize(logical_width, logical_height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("gardenAssetThumbnail", True)
        self.setProperty("gardenAssetId", self._asset_id)
        self.setProperty("gardenAssetType", self._asset_type)
        self.setProperty("gardenAssetRarity", str(rarity or ""))

        pixmap, source = self._render(
            logical_width,
            logical_height,
            explicit_path=str(explicit_path or ""),
        )
        fallback_used = pixmap.isNull()
        if fallback_used:
            fallback_path = self._resolve_ui_path(self._fallback_asset_id)
            pixmap = self._contained_pixmap(fallback_path, logical_width, logical_height)
            source = fallback_path
        self.setProperty("gardenAssetSource", str(source or ""))
        self.setProperty("gardenAssetFallback", fallback_used)
        if not pixmap.isNull():
            self.setPixmap(pixmap)
        self.setAccessibleName(f"{self._asset_type.replace('_', ' ').title()} artwork")

    def _resolve_ui_path(self, asset_id: str) -> Path | None:
        resolver = getattr(self._engine, "resolve_item_asset", None)
        if callable(resolver):
            try:
                resolved = _path_from_asset(resolver(str(asset_id).removeprefix("ui_")))
                if resolved is not None:
                    return resolved
            except Exception:
                pass
        return _bundled_ui_path(asset_id)

    def _resolve_path(self, explicit_path: str) -> tuple[Path | None, Any | None]:
        if self._asset_type == "plant":
            resolver = getattr(self._engine, "resolve_plant_asset", None)
            if callable(resolver):
                try:
                    asset = resolver(self._asset_id, self._stage)
                    path = _path_from_asset(asset)
                    if path is not None:
                        return path, asset
                except Exception:
                    pass
            return _path_from_asset(explicit_path), None
        if self._asset_type == "environment":
            for name in (
                "resolve_scenery_preview_asset",
                "resolve_garden_feature_preview_asset",
                "resolve_item_asset",
            ):
                resolver = getattr(self._engine, name, None)
                if not callable(resolver):
                    continue
                try:
                    asset = resolver(self._asset_id)
                    path = _path_from_asset(asset)
                    if path is not None:
                        return path, asset
                except Exception:
                    continue
            return _path_from_asset(explicit_path), None

        # Canonical manifest identities win over presentation-model paths. This
        # keeps existing reward, currency, and boost artwork consistent across
        # every Garden surface; an explicit path is only a legacy/fallback route.
        resolved = self._resolve_ui_path(self._asset_id)
        if resolved is not None:
            return resolved, None
        return _path_from_asset(explicit_path), None

    @staticmethod
    def _contained_pixmap(path: Path | None, width: int, height: int) -> Any:
        source = QPixmap(str(path)) if path is not None else QPixmap()
        if source.isNull():
            return QPixmap()
        dpr = _active_device_pixel_ratio()
        pixmap = source.scaled(
            max(1, round(width * dpr)),
            max(1, round(height * dpr)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def _render(
        self,
        width: int,
        height: int,
        *,
        explicit_path: str,
    ) -> tuple[Any, Path | None]:
        path, asset = self._resolve_path(explicit_path)
        if path is None:
            return QPixmap(), None
        if self._asset_type == "plant" and width == height:
            pixmap = normalized_plant_pixmap(
                asset or path,
                stage=self._stage,
                logical_size=width,
            )
            return pixmap, path
        source = preview_source_pixmap(path)
        if self._asset_type == "environment":
            return cover_pixmap(source, width, height), path
        return self._contained_pixmap(path, width, height), path


__all__ = ["FALLBACK_UI_ASSET_ID", "GardenAssetThumbnail"]
