from __future__ import annotations

import pytest


def test_building_clicks_cover_architecture_under_application_button_styling(monkeypatch):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        import json
        from pathlib import Path
        from aqt.qt import QApplication, QPoint, Qt
        from PyQt6.QtTest import QTest
        from ankigarden.ui.scene import GardenSceneWidget
        from ankigarden.ui.theme import tool_button_stylesheet
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")

    application = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1] / "ankigarden"
    manifest = json.loads((root / "assets/manifest.json").read_text())
    background = next(row for row in manifest["assets"]
                      if row["asset_id"] == "bg_verdant_twilight_any_soil_master_v6")
    scene = GardenSceneWidget()
    scene.setStyleSheet(tool_button_stylesheet())
    scene.set_scene({"plants": [], "asset_paths": {"background": {
        "asset_root": str(root), "placement": background["placement"],
    }}})
    scene.show()
    fired = []
    scene.landmarkActivated.connect(fired.append)
    try:
        for width, height in ((618, 412), (1200, 800)):
            scene.resize(width, height)
            application.processEvents()
            # Independent image-cover coordinates: roof, wall, and door, then sky.
            for action, points, sky in (
                ("garden.nursery.open", [(230, 210), (208, 266), (249, 300)], (300, 150)),
                ("garden.trophies.open", [(1235, 180), (1240, 266), (1300, 302)], (1165, 140)),
            ):
                def project(point):
                    return QPoint(round(point[0] * width / 1448),
                                  round(point[1] * width / 1448 - height * .06))
                for point in points:
                    position = project(point)
                    button = scene.childAt(position)
                    assert button is not None
                    fired.clear()
                    QTest.mouseClick(button, Qt.MouseButton.LeftButton,
                                     pos=position - button.pos())
                    assert fired == [action]
                    assert not button.hasFocus() and not button.underMouse()
                    scene.hide()
                    scene.show()
                    application.processEvents()
                    assert not button.hasFocus()
                assert scene.childAt(project(sky)) is not button
    finally:
        scene.close()
        scene.deleteLater()


def test_toast_replacement_expiry_and_disposal_when_qt_is_available(monkeypatch):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication, QEvent, QWidget
        from PyQt6.QtTest import QSignalSpy, QTest
        from ankigarden.ui.dashboard import ToastRegion
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.show()
    toast = ToastRegion(owner)
    cleared = QSignalSpy(toast.cleared)
    toast.setFixedWidth(320)
    toast.show_message("Applied\n" + "Checkpoint reward. +1 Coin\n" * 100)
    application.processEvents()
    assert toast.message.text() == "Applied"
    assert cleared.wait(2500)
    assert not toast.isVisible()
    toast.show_message("A very long Garden update " * 100)
    application.processEvents()
    assert len(toast.message.text().splitlines()) <= 2
    assert all(toast.message.fontMetrics().horizontalAdvance(line) <= toast.message.contentsRect().width()
               for line in toast.message.text().splitlines())
    toast.show_message("Old update", duration_ms=1, fade_ms=1)
    toast.show_message("Replacement", duration_ms=0, dismissible=True)
    QTest.qWait(40)
    assert toast.isVisible() and toast.message.text() == "Replacement"
    toast.dismiss.click()
    assert not toast.isVisible()
    cleared = QSignalSpy(toast.cleared)
    toast.show_message("Reduced motion", duration_ms=1, fade_ms=1, motion_enabled=False)
    assert cleared.wait(2000)
    assert not toast.isVisible()
    toast.show_message("Disposing", duration_ms=1, fade_ms=1)
    owner.close()
    owner.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(40)


pytestmark = pytest.mark.release_evidence


def test_starter_previews_cycle_independently_without_choosing_a_plant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from pathlib import Path
        from types import SimpleNamespace

        from aqt.qt import QApplication, QDialog, QHBoxLayout, QPushButton, QSize, Qt
        from PyQt6.QtTest import QTest
        from ankigarden.capture.runtime import _UiFaceCaptureRunner
        from ankigarden.ui.dashboard import GardenIconButton, _StarterPlantCard, _asset_preview_label
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")

    assets = Path(__file__).resolve().parents[1] / "ankigarden/assets/v6_storybook_gouache/plants"
    engine = SimpleNamespace(
        state={"plants": []},
        resolve_plant_image=lambda species, stage: str(
            assets / species / stage / f"{species}_{stage}_twilight_v6.webp"
        ),
    )
    application = QApplication.instance() or QApplication([])
    dialog = QDialog()
    layout = QHBoxLayout(dialog)
    choices = []
    cards = [_StarterPlantCard(engine, species, lambda: False, dialog)
             for species in ("rose", "bonsai")]
    for card in cards:
        card.chosen.connect(choices.append)
        layout.addWidget(card)
    default = QPushButton("Choose a bed", dialog)
    default.setDefault(True)
    default.clicked.connect(lambda: choices.append("default"))
    layout.addWidget(default)
    ordinary_icon = GardenIconButton("chevron-right", "Ordinary navigation", dialog)
    layout.addWidget(ordinary_icon)
    dialog.show()
    application.processEvents()
    try:
        auditor = _UiFaceCaptureRunner.__new__(_UiFaceCaptureRunner)
        audit, _warnings = auditor._visual_contract_audit(dialog, "starter-preview-regression")
        assert "icon-control-size" not in audit["issues"]
        ordinary_icon.setIconSize(QSize(12, 12))
        audit, _warnings = auditor._visual_contract_audit(dialog, "starter-preview-regression")
        assert "icon-control-size" in audit["issues"]
        ordinary_icon.setIconSize(QSize(18, 18))
        assert [card.stage_label.text() for card in cards] == ["Preview: Full Bloom", "Preview: Full Bloom"]
        assert "undiscovered" not in cards[0].artwork.accessibleName().lower()
        arrow_positions = (cards[0].previous.x(), cards[0].next_button.x())
        for stage, title in (
            ("Seed", "Rose Seed"), ("Sprout", "Rose Sprout"),
            ("Young", "Young Rose"), ("Mature", "Mature Rose"),
            ("Flowering", "Flowering Rose"), ("Full Bloom", "Full Bloom Rose"),
        ):
            QTest.mouseClick(cards[0].next_button, Qt.MouseButton.LeftButton)
            application.processEvents()
            assert (cards[0].previous.x(), cards[0].next_button.x()) == arrow_positions
            assert cards[0].stage_label.text() == f"Preview: {stage}"
            assert cards[0].stage_label.accessibleName() == title
            assert cards[0].artwork.accessibleName() == f"{title} stage preview"
            assert cards[1].stage_label.text() == "Preview: Full Bloom"
        QTest.keyClick(cards[0].next_button, Qt.Key.Key_Return)
        assert cards[0].stage_label.text() == "Preview: Seed"
        QTest.keyClick(cards[0].previous, Qt.Key.Key_Space)
        assert cards[0].stage_label.text() == "Preview: Full Bloom"
        assert choices == []
        assert engine.state == {"plants": []}

        # Previewing a starter must not reveal Full Bloom on other surfaces.
        concealed = _asset_preview_label(engine, "rose", "rare")
        assert concealed.accessibleName() == "Full Bloom Rose undiscovered"
        concealed.deleteLater()
        QTest.keyClick(cards[0].selection, Qt.Key.Key_Return)
        assert choices == ["rose"]
    finally:
        dialog.close()
        dialog.deleteLater()
        application.processEvents()


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

    grid._defer_reflow = True
    for _index in range(38):
        card = QFrame()
        grid.add_card(card)
        assert card.parentWidget() is grid.container
        assert not card.isWindow()
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


def test_collection_hides_dormant_landmarks_and_retains_enabled_layout(
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
    from ankigarden import feature_availability

    dormant = CollectionSection(engine, PlantCollectionPane(), None)
    assert tuple(dormant.subtabs.buttons) == (
        CollectionTab.PLANTS, CollectionTab.APPEARANCE,
    )
    dormant.set_current(CollectionTab.GARDEN_LANDMARKS, focus_tier_id="lily_pond")
    assert dormant.current_tab is CollectionTab.PLANTS
    dormant.close()
    dormant.deleteLater()
    application.processEvents()

    # Keep the retained pane usable for a later release without exposing it now.
    monkeypatch.setattr(feature_availability, "LANDMARKS_ENABLED", True)
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


@pytest.mark.parametrize("initial_session_state", ["expanded", "collapsed", "hidden"])
def test_reviewer_mouse_targets_dragging_effects_and_feed(monkeypatch, initial_session_state):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from dataclasses import replace
        from aqt.qt import QApplication, QLabel, QPoint, Qt, QWidget
        from PyQt6.QtTest import QTest
        from test_garden_studio_advanced_scroll_regression import _live_engine_fixture
        from ankigarden.models.state import CardEffectBatch
        from ankigarden.reward_presentation import RewardBundleProjection, RewardHero, RewardItemProjection
        from ankigarden.ui.reviewer_hud import project_reviewer_hud
        from ankigarden.ui.reviewer_hud_widget import ReviewGardenHud
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    application = QApplication.instance() or QApplication([])
    config, storage, engine = _live_engine_fixture()
    plant = engine.active_plant()
    plant.fertilizer_card_batches = [CardEffectBatch("fertilizer_premium", 800, 400, 398)]
    plant.booster_card_batches = [CardEffectBatch("booster_potion", 100, 100, 45)]
    owner = QWidget()
    owner.resize(1200, 900)
    owner.show()
    opened, positions = [], []
    hud = ReviewGardenHud(owner, on_open_garden=lambda: opened.append("garden"),
                          on_open_plant=lambda plant_id: opened.append(plant_id),
                          on_open_activity=lambda: opened.append("activity"),
                          on_open_supplies=opened.append, on_position_changed=positions.append,
                          resolve_reward_art=engine.resolve_item_asset, animations_enabled=False)
    hud.set_callbacks(on_open_plant=lambda plant_id: opened.append(plant_id), on_open_supplies=opened.append,
                      on_open_activity=lambda: opened.append("activity"),
                      on_position_changed=positions.append, on_toggle_collapsed=lambda value: hud.set_collapsed(value),
                      resolve_reward_art=engine.resolve_item_asset, animations_enabled=False)
    projection = project_reviewer_hud(engine, storage.state)
    hud.update_projection(projection)
    QTest.qWait(40)

    def click(widget):
        QTest.mouseClick(owner.windowHandle(), Qt.MouseButton.LeftButton, pos=widget.mapTo(owner, widget.rect().center()))
        application.processEvents()

    try:
        click(hud._header_title)
        assert not opened and not hud._collapsed
        click(hud._collapse_button)
        assert hud._collapsed
        click(hud._collapsed_tab)
        assert not hud._collapsed
        click(hud._plant_name)
        assert opened == [plant.plant_id]
        click(hud._consumable_pills['fertilizer'])
        click(hud._consumable_pills['booster'])
        assert opened[-2:] == ['fertilizer', 'booster']
        assert hud._consumable_pills['fertilizer'].property('remainingCards') == 398

        before = hud.pos()
        pointer = hud._header_title.mapTo(owner, QPoint(20, 12))
        QTest.mousePress(owner.windowHandle(), Qt.MouseButton.LeftButton, pos=pointer)
        QTest.mouseMove(owner.windowHandle(), pointer + QPoint(-180, 80), delay=20)
        QTest.mouseRelease(owner.windowHandle(), Qt.MouseButton.LeftButton, pos=pointer + QPoint(-180, 80))
        assert hud.pos() != before and positions[-1]['custom']
        moved = hud.pos()
        hud.update_projection(replace(projection, position=(positions[-1]['x'], positions[-1]['y'])))
        assert hud.pos() == moved
        assert opened == [plant.plant_id, 'fertilizer', 'booster']

        click(hud._collapse_button)
        assert hud._collapsed
        collapsed_before = hud.pos()
        pointer = hud._collapsed_tab.mapTo(owner, hud._collapsed_tab.rect().center())
        QTest.mousePress(owner.windowHandle(), Qt.MouseButton.LeftButton, pos=pointer)
        QTest.mouseMove(owner.windowHandle(), pointer + QPoint(-150, 50), delay=20)
        QTest.mouseRelease(owner.windowHandle(), Qt.MouseButton.LeftButton, pos=pointer + QPoint(-150, 50))
        assert hud._collapsed and hud.pos() != collapsed_before
        assert len(positions) == 2
        saved = (positions[-1]['x'], positions[-1]['y'])
        hud.update_projection(replace(projection, collapsed=True, position=saved))
        right_edge = hud.geometry().right()
        click(hud._collapsed_tab)
        assert not hud._collapsed and hud.geometry().right() == right_edge
        assert hud._position == saved and len(positions) == 2

        if initial_session_state == "hidden":
            owner.hide()
        elif initial_session_state == "collapsed":
            hud.set_collapsed(True)
        hud.restore_reward_state({"feed_expanded": False})
        for n in range(8):
            item = RewardItemProjection(f'coin-{n}', RewardHero.COIN_OR_BOOSTER, 'Checkpoint reward', 'Garden reward', garden_coins=2)
            hud.present_reward(RewardBundleProjection(f'answer-{n}', '2026-09-06T12:00:00Z', (item,)))
        hud.update_session_totals({"footer_growth_units": 12_600})
        owner.show()
        hud.set_collapsed(False)
        QTest.qWait(40)
        assert not hud._reward_feed.isVisibleTo(hud)
        assert not hud._reward_details_toggle.isVisibleTo(hud)
        assert hud._reward_feed.model.rowCount() == 8
        assert hud._session_history_toggle.y() > max(tile.geometry().bottom() for tile in hud._session_metric_tiles)
        initial_height = hud.height()
        initial_footer = hud._session_footer.geometry()
        opened.clear()
        for target in (hud._session_heading, *hud._session_metric_tiles, hud._session_history_toggle):
            click(target)
            assert opened[-1] == "activity"
            assert not hud._reward_feed.isVisibleTo(hud)
        assert opened == ["activity"] * 5
        opened.clear()
        click(hud._session_history_chevron)
        assert hud._reward_feed.isVisibleTo(hud)
        click(hud._session_history_chevron)
        assert not hud._reward_feed.isVisibleTo(hud)
        assert all(tile.isVisibleTo(hud) for tile in hud._session_metric_tiles)
        assert hud.height() == initial_height
        assert hud._session_footer.geometry() == initial_footer
        assert not opened
        click(hud._session_history_chevron)
        assert hud._reward_feed.isVisibleTo(hud)
        assert all(not hud._reward_feed.delegate.artwork_for(entry.item).isNull()
                   for entry in hud._reward_feed.model.entries)
        bar = hud._reward_feed.view.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        before_scroll = bar.value()
        item = RewardItemProjection('new-coin', RewardHero.COIN_OR_BOOSTER, 'Garden reward', 'Garden reward', garden_coins=3)
        hud.present_reward(RewardBundleProjection('new-answer', '2026-09-06T12:00:01Z', (item,)))
        assert before_scroll > 0
        assert bar.value() == 0
        plant.fertilizer_card_batches.clear()
        plant.booster_card_batches.clear()
        hud.update_projection(project_reviewer_hud(engine, storage.state))
        assert hud._consumables.isHidden()
    finally:
        hud.dispose()
        owner.close()
        owner.deleteLater()
        application.processEvents()
