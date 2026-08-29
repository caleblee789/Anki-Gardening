from __future__ import annotations

import pytest

from scripts.audit_assets import (
    RETINA_PLANT_MIN_VISIBLE_HEIGHT,
    RETINA_RASTER_MAX_CSS_SIZE,
    RETINA_SCENERY_MAX_CSS_SIZE,
    _validate_retina_density,
    audit,
)


pytestmark = pytest.mark.release_evidence


def test_production_asset_catalog_passes_retina_density_gate() -> None:
    counts = audit()

    assert counts == {
        "backgrounds": 9,
        "garden_features": 8,
        "plants": 60,
        "ui": 19,
    }
    assert RETINA_RASTER_MAX_CSS_SIZE == {
        "plants": (300, 300),
        "garden_features": (210, 59),
        "ui": (96, 96),
    }
    assert RETINA_PLANT_MIN_VISIBLE_HEIGHT == {
        "seed": 164,
        "sprout": 188,
        "young": 212,
        "mature": 236,
        "flowering": 260,
        "rare": 272,
    }
    assert RETINA_SCENERY_MAX_CSS_SIZE == {
        "4:3": (640, 480),
        "16:9": (820, 460),
        "home": (440, 100),
    }


def test_retina_density_gate_rejects_undersized_required_raster() -> None:
    with pytest.raises(ValueError, match="Retina artwork is undersized"):
        _validate_retina_density(
            [
                {
                    "asset_id": "ui_too_small",
                    "category": "ui",
                    "format": "webp",
                    "width": 191,
                    "height": 192,
                }
            ]
        )


def test_retina_density_gate_rejects_tiny_plant_inside_large_canvas(
    tmp_path, monkeypatch
) -> None:
    from PIL import Image, ImageDraw

    addon = tmp_path / "ankigarden"
    path = addon / "assets/v6_storybook_gouache/plants/test.webp"
    path.parent.mkdir(parents=True)
    image = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((280, 500, 320, 560), fill=(90, 180, 120, 255))
    image.save(path, "WEBP", lossless=True)
    monkeypatch.setattr("scripts.audit_assets.ADDON", addon)

    with pytest.raises(ValueError, match="plant silhouette is undersized"):
        _validate_retina_density(
            [
                {
                    "asset_id": "plant_too_small",
                    "category": "plants",
                    "format": "webp",
                    "width": 600,
                    "height": 600,
                    "file": "assets/v6_storybook_gouache/plants/test.webp",
                    "slot": {"stage": "seed"},
                }
            ]
        )


def test_retina_density_gate_exempts_vector_backed_artwork() -> None:
    _validate_retina_density(
        [
            {
                "asset_id": "ui_vector",
                "category": "ui",
                "format": "svg",
                "width": 16,
                "height": 16,
            }
        ]
    )
