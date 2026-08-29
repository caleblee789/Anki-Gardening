from __future__ import annotations

import pytest

from scripts.audit_assets import (
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
        "decorations": 1,
        "garden_features": 8,
        "plants": 60,
        "ui": 10,
    }
    assert RETINA_RASTER_MAX_CSS_SIZE == {
        "plants": (300, 300),
        "decorations": (160, 160),
        "garden_features": (210, 59),
        "ui": (96, 96),
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
