from __future__ import annotations

from ankigarden.ui.icons import (
    GARDEN_ICON_PATHS,
    ICON_STROKE_WIDTH,
    ICON_VIEWBOX,
    garden_icon_svg,
)


def test_release_icons_share_one_grid_and_stroke_contract() -> None:
    assert ICON_VIEWBOX == 24
    assert ICON_STROKE_WIDTH == 1.8
    assert {
        "close",
        "coin",
        "growth",
        "streak",
        "stage",
        "collection",
        "lock",
        "settings",
        "nursery",
        "plant",
        "warning",
        "info",
    } <= set(GARDEN_ICON_PATHS)
    for name in GARDEN_ICON_PATHS:
        payload = garden_icon_svg(name, color="#123456")
        assert 'viewBox="0 0 24 24"' in payload
        assert 'stroke="#123456"' in payload
        assert 'stroke-width="1.8"' in payload
