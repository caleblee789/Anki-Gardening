from __future__ import annotations

from pathlib import Path

import pytest


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


def test_settings_advanced_actions_reserve_footer_clearance() -> None:
    source = _source("ankigarden/ui/garden_studio.py")

    assert "self.advanced_actions_layout.setContentsMargins(0, 8, 0, 16)" in source
    assert "self.controls_scroll.setVerticalScrollBarPolicy(" in source
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in source


def test_progress_card_grid_owns_content_driven_row_geometry() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    grid = source.split("class ProgressCardGrid", 1)[1].split(
        "class ResponsiveTileGrid", 1
    )[0]

    assert "minimum_card_height: int = 136" in grid
    assert "self.grid.setRowMinimumHeight(row_index, 0)" in grid
    assert "self.grid.setRowStretch(row_index, 0)" in grid
    assert "row_minimums: dict[int, int] = {}" in grid
    assert "self.grid.setRowMinimumHeight(row_index, max(0, int(minimum)))" in grid
    assert "self.container.setMinimumHeight(required_height)" in grid
    assert 'self.container.setProperty("contentRowCount", len(row_minimums))' in grid
    assert "QTimer.singleShot(0, self._reflow)" in grid


def test_scene_toasts_use_compact_overlay_geometry() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    toast = source.split("class ToastRegion", 1)[1].split(
        "class _TooltipFocusFilter", 1
    )[0]
    position = source.split("def _position_scene_overlays", 1)[1].split(
        "def _position_onboarding_coachmark", 1
    )[0]

    assert "layout.setContentsMargins(8, 6, 8, 6)" in toast
    assert "self.setMinimumHeight(44)" in toast
    assert "self.setMaximumHeight(84)" in toast
    assert "available_width = max(1, self.scene.width() - (inset * 2))" in position
    assert "available_height = max(1, self.scene.height() - (inset * 2))" in position
    assert "min(84, max(44, self.toast_region.sizeHint().height()))" in position
    assert "self.scene.height() - toast_height - inset" in position


def test_plant_story_uses_compact_artwork_stages_and_timeline_spacing() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    timeline = source.split("class MemoryTimeline", 1)[1].split(
        "class PlantStoryDialog", 1
    )[0]
    story = source.split("class PlantStoryDialog", 1)[1].split(
        "class StarterConfirmationDialog", 1
    )[0]

    assert "self.layout.setContentsMargins(6, 0, 6, 0)" in timeline
    assert "row_layout.setContentsMargins(8, 4, 4, 4)" in timeline
    assert "self._story_artwork_size = 132" in story
    assert "node.setMinimumHeight(78)" in story
    assert "stage_preview.setFixedSize(42, 42)" in story
    assert "size = 112 if mode == COMPACT_MODE else 132" in story
    assert "size=42" in story


def test_starter_confirmation_is_a_non_scrolling_decision_dialog() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    starter = source.split("class StarterConfirmationDialog", 1)[1].split(
        "class NurseryDialog", 1
    )[0]

    assert "content_host.setAccessibleName(\"Starter choice details\")" in starter
    assert "layout.addWidget(content_host, 1)" in starter
    assert "QScrollArea" not in starter
    assert "register_scroll_region" not in starter


def test_loadout_preview_feedback_is_an_aspect_fitted_scene_overlay() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    loadout = source.split("class CollectibleDetailDialog", 1)[1].split(
        "class GardenDashboard", 1
    )[0]

    assert "self.preview_feedback = ToastRegion(self.preview_scene)" in loadout
    assert "preview_layout.addWidget(self.preview_feedback)" not in loadout
    assert "self.preview_scene.installEventFilter(self)" in loadout
    assert "available_width * 9 / 16" in loadout
    assert "max(260, min(420" in loadout
    assert "self.preview_feedback.setGeometry(" in loadout
    assert "self.preview_feedback.show_message(" in loadout
    assert "duration_ms=0 if error else duration_ms" in loadout


def test_nursery_uses_compact_cards_overlays_and_starter_only_footer() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    nursery = source.split("class NurseryDialog", 1)[1].split(
        "class PlantInfoCard", 1
    )[0]

    assert "root.setContentsMargins(14, 10, 14, 10)" in nursery
    assert "resource_layout = QHBoxLayout(self.coin_resource)" in nursery
    assert "self.coins.setMinimumWidth(0)" in nursery
    assert "root.addWidget(self.nursery_toast)" not in nursery
    assert "root.addWidget(self.status)" not in nursery
    assert "def _position_nursery_overlays(self)" in nursery
    assert "self.nursery_footer.setVisible(starter_mode)" in nursery
    assert "self._plant_artwork(species, GROWTH_STAGES[0], 84)" in nursery
    assert "self._environment_artwork(item, width=180, height=101)" in nursery
    assert "self.environment_feature_art.setMaximumSize(220, 124)" in nursery
    assert "maximum_columns=3" in nursery


def test_plant_popover_is_compact_and_omits_inactive_boost_actions() -> None:
    source = _source("ankigarden/ui/dashboard.py")
    card = source.split("class PlantInfoCard", 1)[1].split(
        "class GardenStatsStrip", 1
    )[0]

    assert "self.setMinimumWidth(280)" in card
    assert "self.setMaximumWidth(300)" in card
    assert "layout.setContentsMargins(12, 10, 12, 12)" in card
    assert "self.actions.addWidget(self.fertilize, 1, 0)" not in card
    assert "self.actions.addWidget(self.growth_charge, 1, 1)" not in card
    assert "self.fertilize.setVisible(active and not fully_grown)" in card
    assert "self.growth_charge.setVisible(active and not fully_grown)" in card


def test_live_progress_grid_preserves_full_single_and_empty_heights_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication, QFrame
        from ankigarden.ui.dashboard import ProgressCardGrid
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")

    application = QApplication.instance() or QApplication([])
    grid = ProgressCardGrid(
        "Collection geometry test",
        wide_columns=4,
        minimum_item_width=160,
        minimum_card_height=224,
    )
    grid.resize(900, 420)
    grid.show()

    for _index in range(38):
        grid.add_card(QFrame())
    grid.finish()
    application.processEvents()
    assert int(grid.container.property("contentRowCount")) == 10
    assert grid.container.minimumHeight() >= 10 * 224

    grid.clear()
    grid.add_card(QFrame())
    grid.finish()
    application.processEvents()
    assert int(grid.container.property("contentRowCount")) == 1
    assert grid.container.minimumHeight() >= 224

    grid.clear()
    grid.add_empty("No matches")
    grid.finish()
    application.processEvents()
    assert int(grid.container.property("contentRowCount")) == 1
    assert grid.container.minimumHeight() > 0

    grid.close()
    grid.deleteLater()
    application.processEvents()
