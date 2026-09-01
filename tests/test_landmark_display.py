from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ankigarden

from ankigarden.asset_manager import AssetManager
from ankigarden.config import DEFAULT_CONFIG
from ankigarden.game import GardenGameEngine
from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    render_home_widget,
)
from ankigarden.ui.landmark_display import (
    GARDEN_LANDMARK_ANCHOR,
    project_garden_landmark_rect,
)


class _Config:
    def value(self, key: str, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys: str, default=None):
        value = DEFAULT_CONFIG
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
            if value is None:
                return default
        return value


class _Storage:
    def __init__(self) -> None:
        self.addon_dir = Path(ankigarden.__file__).resolve().parent
        self.assets_root = self.addon_dir / "assets"

    @staticmethod
    def load_asset_metadata() -> dict:
        return {}

    @staticmethod
    def save_asset_metadata(_value: dict) -> None:
        return None


def _home_data(**changes) -> HomeWidgetData:
    baseline = HomeWidgetData(
        reviews_today=0,
        growth_earned=0,
        base_growth=0,
        streak_bonus_growth=0,
        fertilizer_growth=0,
        bonus_growth=0,
        all_due_completed=False,
        streak_days=0,
        streak_bonus_percent=0,
        next_streak_day=None,
        next_streak_bonus_percent=None,
        garden_currency=0,
        weather="seedling_sign",
        starter_selected=True,
    )
    return replace(baseline, **changes)


def test_home_and_main_scene_project_the_same_fixed_landmark_anchor() -> None:
    home = project_garden_landmark_rect(0.0, 0.0, 1000.0, 420.0)
    main = project_garden_landmark_rect(0.0, 0.0, 1260.0, 840.0)

    for projected, width, height in ((home, 1000.0, 420.0), (main, 1260.0, 840.0)):
        left, top, projected_width, projected_height = projected
        assert left / width == GARDEN_LANDMARK_ANCHOR.left
        assert top / height == GARDEN_LANDMARK_ANCHOR.top
        assert projected_width / width == GARDEN_LANDMARK_ANCHOR.width
        assert projected_height / height == GARDEN_LANDMARK_ANCHOR.height
    assert GARDEN_LANDMARK_ANCHOR.identity == "0.360,0.180,0.280,0.520"


def test_home_landmark_is_absent_until_displayed_identity_and_asset_are_present() -> None:
    empty_html = render_home_widget(
        HomeWidgetSnapshot(1, "success", _home_data())
    )
    missing_asset_html = render_home_widget(
        HomeWidgetSnapshot(
            2,
            "success",
            _home_data(landmark_id="mossy_stone_path"),
        )
    )
    displayed_html = render_home_widget(
        HomeWidgetSnapshot(
            3,
            "success",
            _home_data(
                landmark_id="mossy_stone_path",
                landmark_url="/_addons/garden/landmark.webp",
            ),
        )
    )

    assert 'data-testid="home-garden-landmark"' not in empty_html
    assert 'data-testid="home-garden-landmark"' not in missing_asset_html
    assert 'data-testid="home-garden-landmark"' in displayed_html
    assert 'data-landmark="mossy_stone_path"' in displayed_html
    assert 'data-landmark-anchor="0.360,0.180,0.280,0.520"' in displayed_html


def test_completed_displayed_project_resolves_the_matching_landmark_asset_identity() -> None:
    manager = AssetManager(_Config(), _Storage())
    project = SimpleNamespace(
        selected_project_id="birdbath_terrace",
        displayed_project_id="mossy_stone_path",
        completed_project_ids=["mossy_stone_path"],
    )
    engine = SimpleNamespace(
        assets=manager,
        config=_Config(),
        state=SimpleNamespace(garden_project=project),
    )

    resolved = GardenGameEngine.resolve_landmark_asset(engine)

    assert resolved is not None
    assert resolved.category == "landmarks"
    assert resolved.asset_id == "landmark_mossy_stone_path"
    assert resolved.metadata["slot"]["key"] == "mossy_stone_path"
    assert resolved.path.name == "landmark_mossy_stone_path.webp"

    project.displayed_project_id = ""
    assert GardenGameEngine.resolve_landmark_asset(engine) is None
    project.displayed_project_id = "birdbath_terrace"
    assert GardenGameEngine.resolve_landmark_asset(engine) is None
