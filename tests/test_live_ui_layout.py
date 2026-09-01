from __future__ import annotations

import pytest


pytestmark = pytest.mark.release_evidence


def test_progress_grid_preserves_full_single_and_empty_heights_when_qt_is_available(
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
    tall_card = QFrame()
    tall_card.setMinimumHeight(310)
    grid.add_card(tall_card)
    grid.add_card(QFrame())
    grid.finish()
    application.processEvents()
    boundaries = tuple(grid.container.property("safeRowBoundaries") or ())
    assert boundaries and int(boundaries[0]) >= 316

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


def test_collection_subtabs_preserve_state_and_landmarks_fit_canonical_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the 950 px dialog's Collection content without launching Anki."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from pathlib import Path
        from types import SimpleNamespace

        from aqt.qt import QApplication, QFrame, QLabel, QPushButton
        from ankigarden.economy_progression import (
            GrowthTargetRef,
            GrowthTargetType,
            build_growth_projects_snapshot,
        )
        from ankigarden.ui.dashboard import (
            CollectionFilterControls,
            CollectionSection,
            CollectionTab,
            GardenLandmarksPane,
            LandmarkProjectOverview,
            LandmarkTierList,
            PlantCollectionPane,
        )
        from ankigarden.ui.garden_asset_thumbnail import GardenAssetThumbnail
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")

    asset_root = Path(__file__).resolve().parents[1] / "ankigarden" / "assets"

    class _AssetEngine:
        @staticmethod
        def resolve_item_asset(asset_id: str):
            normalized = str(asset_id or "")
            if normalized in {"garden_coin", "stored_growth"}:
                path = (
                    asset_root
                    / "v6_storybook_gouache"
                    / "ui"
                    / f"{normalized}.webp"
                )
            else:
                path = (
                    asset_root
                    / "v6_storybook_gouache"
                    / "landmarks"
                    / f"{normalized}.webp"
                )
            return SimpleNamespace(path=path)

    application = QApplication.instance() or QApplication([])
    engine = _AssetEngine()
    target = GrowthTargetRef(GrowthTargetType.LANDMARK, "garden_landmark")
    snapshot = build_growth_projects_snapshot(
        state_revision=4,
        stored_balance_units=50_000_000,
        wallet_balance_coins=9_999,
        full_bloom_species=("bonsai",),
        active_target=target,
        active_target_activation_identity="layout-test",
        landmark_growth_units_funded=10_000_000,
    )

    plants = PlantCollectionPane()
    controls = CollectionFilterControls(
        query="rose",
        status="collected",
        category="plants",
        sort_order="name",
        set_query=lambda _value: None,
        set_status=lambda _value: None,
        set_category=lambda _value: None,
        set_sort_order=lambda _value: None,
        clear_filters=lambda: None,
    )
    plants.set_fixed_header(controls)
    for _index in range(24):
        card = QFrame()
        card.setFixedHeight(158)
        plants.add_card(card)
    plants.finish()

    landmarks = GardenLandmarksPane()
    previous_threshold = 0
    tier_growth: dict[str, int] = {}
    for tier in snapshot.landmark_track.tiers:
        tier_growth[tier.tier_id] = (
            tier.cumulative_growth_threshold_units - previous_threshold
        )
        previous_threshold = tier.cumulative_growth_threshold_units
    overview = LandmarkProjectOverview(
        engine,
        snapshot,
        snapshot.landmark_track,
        overview_artwork_id=snapshot.landmark_track.artwork_id,
        on_activate=lambda: None,
        on_contribute=lambda: None,
    )
    tiers = LandmarkTierList(
        engine,
        snapshot,
        snapshot.landmark_track,
        displayed_tier_id="",
        tier_growth_units_by_id=tier_growth,
        on_claim=lambda _tier_id: None,
        on_use=lambda _tier_id: None,
    )
    landmarks.replace_content((overview, tiers), preserve_scroll=False)
    collection = CollectionSection(engine, plants, landmarks)
    # 950 px outer dialog minus shell margins and the 160 px navigation rail.
    collection.resize(720, 455)
    collection.show()
    application.processEvents()
    application.processEvents()

    assert collection.current_tab is CollectionTab.PLANTS
    assert controls.search.text() == "rose"
    assert controls.status_combo.currentData() == "collected"
    assert controls.category_combo.currentData() == "plants"
    assert controls.sort_combo.currentData() == "name"
    plant_bar = plants.scroll.verticalScrollBar()
    assert plant_bar.maximum() > 0
    plant_position = min(96, plant_bar.maximum())
    plant_bar.setValue(plant_position)

    collection.set_current(CollectionTab.GARDEN_LANDMARKS)
    application.processEvents()
    landmark_bar = landmarks.scroll.verticalScrollBar()
    assert landmark_bar.maximum() > 0
    landmark_position = min(84, landmark_bar.maximum())
    landmark_bar.setValue(landmark_position)
    collection.set_current(CollectionTab.PLANTS)
    collection.set_current(CollectionTab.GARDEN_LANDMARKS)
    application.processEvents()

    assert plant_bar.value() == plant_position
    assert landmark_bar.value() == landmark_position
    assert controls.search.text() == "rose"
    assert landmarks.scroll.horizontalScrollBar().maximum() == 0
    assert len(tiers.rows) == 6
    for row in tiers.rows.values():
        assert row.geometry().right() < landmarks.content.width()
        for button in row.findChildren(QPushButton):
            assert row.rect().contains(button.geometry().center())
    thumbnails = collection.findChildren(GardenAssetThumbnail)
    assert thumbnails
    assert all(not bool(item.property("gardenAssetFallback")) for item in thumbnails)
    tier_art = [
        item
        for item in collection.findChildren(QLabel)
        if bool(item.property("landmarkTierArtwork"))
    ]
    assert len(tier_art) == 6
    assert all(not bool(item.property("itemArtworkFallback")) for item in tier_art)

    collection.close()
    collection.deleteLater()
    application.processEvents()
