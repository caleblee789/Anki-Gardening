from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_settings_preview_uses_compact_desktop_geometry() -> None:
    source = _source("ankigarden/ui/garden_studio.py")
    preview = source.split("class HomeGardenPreview", 1)[1].split(
        "class GardenStudioWidget", 1
    )[0]

    assert "self.setMinimumHeight(144)" in preview
    assert "self.setMaximumHeight(144)" in preview
    assert "scene.setMinimumHeight(144)" in preview
    assert "scene.setMaximumHeight(144)" in preview
    assert "min-height:32px; max-height:32px" in source
    assert "QComboBox {{" in source and "min-height:36px; max-height:36px" in source
    assert "QSlider {{ min-height:36px; max-height:36px" in source
    assert "QCheckBox {{ min-height:36px; max-height:36px" in source
    assert "width:32px; height:18px; border-radius:9px" in source

