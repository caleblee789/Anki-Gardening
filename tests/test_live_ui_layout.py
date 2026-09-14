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


def test_windows_starter_notice_fits_wrapped_text_and_reviewer(monkeypatch):
    from types import SimpleNamespace
    from aqt.qt import QApplication, QLabel, QWidget
    from test_session_summary_integration import _load_reviewer_module

    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    module = _load_reviewer_module(monkeypatch)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"), raising=False)
    monkeypatch.setattr(module, "reviewer_overlay_parent", lambda _mw: owner)
    handler = module.ReviewerHookHandler(SimpleNamespace(), SimpleNamespace())
    try:
        for width in (180, 720):
            owner.resize(width, 480)
            owner.show()
            handler._show_no_starter_notice()
            application.processEvents()
            notice = handler._reviewer_notice
            assert notice is not None and notice.isVisible()
            label = notice.findChild(QLabel)
            assert owner.rect().contains(notice.geometry())
            assert notice.contentsRect().contains(label.geometry())
            assert label.height() >= label.heightForWidth(label.width())
            handler._hide_no_starter_notice()
    finally:
        handler._hide_no_starter_notice()
        owner.close()
        owner.deleteLater()


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


def test_reviewer_session_cells_stay_compact_across_collapse_and_large_totals(monkeypatch):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication, QLabel, Qt, QWidget
        from PyQt6.QtTest import QTest
        from ankigarden.ui.reviewer_hud import NurtureProjection, ReviewerHudProjection, TodayCardsProjection
        from ankigarden.ui.reviewer_hud_widget import ReviewGardenHud
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(1200, 900)
    hud = ReviewGardenHud(owner, animations_enabled=False)
    hud.update_projection(ReviewerHudProjection(
        108, TodayCardsProjection("in_progress", "Today", "1 / 2"),
        NurtureProjection(True, plant_id="p1", plant_name="Flowering Bonsai",
                          stage_points=12_345, stage_goal=14_000, next_stage_key="rare"),
        True, "right",
    ))
    try:
        # Receive totals while hidden/collapsed, then expand repeatedly with
        # the reported amount, a large session, and small totals again.
        owner.show()
        hud.set_collapsed(False)
        QTest.qWait(40)
        track = hud._checkpoint_track
        track_bottom = track.mapTo(hud._body_contents, track.rect().bottomLeft()).y() + 1
        assert hud._body_contents.height() - track_bottom == 8
        for growth_units, exact, count in ((185_145, "+1,851.45", 10),
                                           (123_456_789_000, "+1,234,567,890", 1_234_567_890),
                                           (12_600, "+126", 0)):
            hud.set_collapsed(True)
            hud.update_session_totals({"footer_growth_units": growth_units,
                                       "footer_coin_count": count, "footer_find_count": count})
            owner.show()
            hud.set_collapsed(False)
            QTest.qWait(40)
            cells = [tile.geometry() for tile in hud._session_metric_tiles]
            assert len({cell.y() for cell in cells}) == 1
            assert max(cell.height() for cell in cells) <= 80
            assert max(cell.width() for cell in cells) - min(cell.width() for cell in cells) <= 1
            for tile in hud._session_metric_tiles:
                caption = next(label for label in tile.findChildren(QLabel)
                               if label.property("receiptMetricLabel"))
                assert not caption.wordWrap()
                assert caption.fontMetrics().horizontalAdvance(caption.text()) <= caption.contentsRect().width()
                assert caption.height() < caption.fontMetrics().lineSpacing() * 2
            for amount, full in ((hud._session_growth, exact),
                                 (hud._session_coins, f"+{count:,}" if count else "0"),
                                 (hud._session_finds, f"{count:,}")):
                assert amount.fontMetrics().horizontalAdvance(amount.text()) <= amount.contentsRect().width()
                assert amount.accessibleName() == full
                if amount.text() != full:
                    assert amount.toolTip() == full
                    assert full in amount.parentWidget().toolTip()
            assert hud.width() == 296
            growth = hud._percent
            required = growth.fontMetrics().boundingRect(
                growth.contentsRect(), int(Qt.TextFlag.TextWordWrap), growth.text())
            assert growth.height() >= required.height()
            assert hud._body_scroll.verticalScrollBar().maximum() == 0
    finally:
        hud.dispose()
        owner.close()
        owner.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("animations_enabled", [False, True])
def test_compact_hud_rewards_precede_coalesced_growth(monkeypatch, animations_enabled):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from dataclasses import replace
        from aqt.qt import QApplication, QWidget
        from PyQt6.QtTest import QTest
        from ankigarden.ui.reviewer_hud import NurtureProjection, ReviewerHudProjection, TodayCardsProjection
        from ankigarden.ui.reviewer_hud_widget import ReviewGardenHud
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(1200, 900)
    hud = ReviewGardenHud(owner, animations_enabled=animations_enabled)
    projection = ReviewerHudProjection(
        100, TodayCardsProjection("in_progress", "Today", "1 / 20"),
        NurtureProjection(True, plant_id="p1", plant_name="Rose", progress_percent=10),
        True, "right",
    )
    try:
        hud.update_projection(projection)
        hud.update_projection(replace(
            projection, nurture=replace(projection.nurture, progress_percent=20),
        ), animate=True)
        # Committed compact progress and Growth do not wait for a reveal timer.
        assert hud.property("hudProgressPercent") == 20
        feedback = hud._collapsed_feedback
        feedback.enqueue("a", (), 3, (("Growth", 1_000), ("Shared Growth", 200)))
        assert feedback.property("feedbackCopy") == "+3 Coins"
        assert feedback.amount.opacity() == 1.0
        feedback.enqueue("b", (), 2, (("Growth stored", 500),))
        # Repeated delivery neither repeats a notice nor increases Growth.
        feedback.enqueue("b", (), 2, (("Growth stored", 500),))
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == "+2 Coins"
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == "+17 Growth"
        count = feedback._growth_count
        assert count.target == 1700
        assert count.value == (0 if animations_enabled else 1700)
        QTest.qWait(100)
        if animations_enabled:
            assert 0 < count.value < 1700
        displayed = count.value
        feedback.enqueue("c", (), 0, (("Growth", 300),))
        assert feedback.property("feedbackCopy") == "+20 Growth"
        assert count.value == (displayed if animations_enabled else 2000)
        assert count.target == 2000
        feedback.enqueue("c", (), 0, (("Growth", 300),))
        assert count.target == 2000
        feedback.suspend()
        saved = feedback.export_state()
        QTest.qWait(30)
        assert count.value == saved["growth_count"]["value"]
        feedback.restore_state(saved)
        assert feedback.property("feedbackCopy") == "+20 Growth"
        assert feedback.export_state()["remaining_ms"] == saved["remaining_ms"]
        feedback.resume()
        QTest.qWait(630)
        assert feedback.amount.text() == "+20"
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == ""
        feedback.enqueue("checkpoint", [{
            "caption": "Checkpoint", "color": "#ffffff", "duration": 1_150,
        }], 4, (("Growth", 1_200),))
        assert feedback.property("feedbackCopy") == "Checkpoint"
        # Expanded reward archival cannot consume compact frames.
        feedback.clear_major()
        assert feedback.property("feedbackCopy") == "Checkpoint"
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == "+4 Coins"
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == "+12 Growth"
        assert feedback._current["duration"] == 950
        feedback.enqueue("bloom", [{
            "caption": "Full Bloom", "color": "#ffffff", "duration": 1_650,
        }], 0, ())
        feedback._timer.stop()
        feedback._advance()
        assert feedback.property("feedbackCopy") == "Full Bloom"
        assert feedback._current["duration"] == 1_650
        hud.set_collapsed(False)
        paused = feedback.export_state()["remaining_ms"]
        hud.set_collapsed(True)
        assert feedback.property("feedbackCopy") == "Full Bloom"
        assert 0 < feedback._timer.remainingTime() <= paused

    finally:
        hud.dispose()
        owner.close()
        owner.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("collapsed", [False, True])
@pytest.mark.parametrize("animations_enabled", [False, True])
def test_committed_hud_feedback_paints_before_secondary_work(monkeypatch, collapsed, animations_enabled):
    """Exercise the answer hook, next-question refresh, and real Qt paint."""
    from dataclasses import replace
    from pathlib import Path
    from types import SimpleNamespace
    from aqt.qt import QApplication, QEvent, QObject, QWidget
    from PyQt6.QtTest import QTest
    from test_session_summary_integration import (
        DAY, _load_reviewer_module, _ReviewerStorage, _ReviewerEngine,
    )
    from ankigarden.ui.reviewer_hud import NurtureProjection, ReviewerHudProjection, TodayCardsProjection
    from ankigarden.ui.reviewer_hud_widget import ReviewGardenHud
    from ankigarden.ui.session_summary import CommittedSessionEvent, PlantGrowthDelta

    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(1200, 900)
    owner.show()
    hud = ReviewGardenHud(owner, animations_enabled=animations_enabled)
    projection = ReviewerHudProjection(100,
        TodayCardsProjection("in_progress", "Today", "1 / 20"),
        NurtureProjection(True, plant_id="p1", plant_name="Mature Bonsai",
            progress_percent=87, stage_key="mature", next_stage_key="flowering",
            stage_points=7885, stage_goal=9000,
            next_checkpoint_percent=100, next_checkpoint_reward_coins=8,
            checkpoint_line="1,115 Growth to next milestone", estimate_line="About 86 cards",
            effect_chips=("Seedling Sign\nAppearance only", "Verdant Twilight\nAppearance only"),
            art_path=str(Path(__file__).resolve().parents[1] / "ankigarden/assets/v6_storybook_gouache/plants/bonsai/mature/bonsai_mature_twilight_v6.webp")),
        collapsed, "right")
    hud.update_projection(projection)
    hud.update_session_totals({"footer_growth_units": 0, "footer_drop_count": 0})
    QTest.qWait(10)
    stages = []
    overlaps = []
    target = hud._collapsed_feedback.amount if collapsed else hud._session_growth

    class Observer(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint and watched.isVisible():
                if watched is target:
                    stages.append("paint")
                if watched is hud._percent:
                    art, growth, track = (widget.geometry() for widget in
                        (hud._art_region, hud._percent, hud._checkpoint_track))
                    if art.bottom() >= growth.top() or growth.bottom() >= track.top():
                        overlaps.append((art.getRect(), growth.getRect(), track.getRect()))
            return False

    observer = Observer(owner)
    application.installEventFilter(observer)
    module = _load_reviewer_module(monkeypatch)
    reviewer = SimpleNamespace(web=owner)
    module.mw.reviewer = reviewer
    storage = _ReviewerStorage(proven=True)
    storage.state.starter_selection_complete = True
    storage.runtime_pending = False
    storage.runtime_coordinator = SimpleNamespace(
        request=lambda _reason: True, note_local_answer=lambda _reviewer: None,
        answer_committed=lambda *_args: None,
    )
    engine = _ReviewerEngine(storage)
    handler = module.ReviewerHookHandler(engine, storage,
        state_changed=lambda _reason: stages.append("state"))
    handler._reviewer_hud = hud
    handler._reviewer_session_window = reviewer
    monkeypatch.setattr(handler, "_hud_config_value", lambda key, default=None:
        animations_enabled if key == "enable_animations" else default)
    events = []
    handler._session_summary_accumulator = SimpleNamespace(
        current_anki_day_id=DAY,
        accept_committed=lambda event: events.append(event) or True,
        hud_snapshot=lambda: {"footer_growth_units": len(events) * 1000, "footer_drop_count": 0},
    )
    handler.mark_history_reconciled()
    monkeypatch.setattr(handler, "_session_event_from_result", lambda result: CommittedSessionEvent(
        event_id=result.event_id, anki_day_id=DAY, occurred_at="2026-08-28T10:00:00Z",
        plant_growth=(PlantGrowthDelta("p1", "Rose", 1000),)))
    monkeypatch.setattr(handler, "_committed_growth_snapshot", lambda _state: {})
    monkeypatch.setattr(handler, "_acknowledge_reviewer_result_feedback", lambda _result: stages.append("ack"))
    monkeypatch.setattr(handler, "_retry_reviewer_feedback_acknowledgements", lambda: None)
    monkeypatch.setattr(handler, "_request_reviewer_answer_control_geometry", lambda *_args: None)
    monkeypatch.setattr(module, "reviewer_overlay_parent", lambda _mw: owner)
    monkeypatch.setattr(module, "project_reviewer_hud", lambda *_args, **_kwargs:
        stages.append("projection") or replace(projection, nurture=replace(projection.nurture, progress_percent=88, stage_points=7898)))
    try:
        handler.on_answer(reviewer, SimpleNamespace(id=7), 3)
        handler.on_question()
        assert len(events) == 1
        counter = hud._collapsed_feedback._growth_count if collapsed else hud._session_growth_count
        assert counter.target == 1000
        assert counter.value == (0 if animations_enabled else 1000)
        assert not any(stage in stages for stage in ("ack", "state", "projection"))
        if collapsed:
            assert target.opacity() == 1.0
        QTest.qWait(40)
        assert not overlaps
        assert "paint" in stages
        for secondary in ("ack", "state", "projection"):
            assert stages.index("paint") < stages.index(secondary)
        if animations_enabled:
            assert 0 < counter.value < 1000
        else:
            assert target.text() == "+10"
        assert not hud.feedback_paint_pending
        # An unchanged projection, duplicate callback, or totals refresh cannot
        # restart the earned count. Completion remains exact after 600 ms.
        elapsed = counter.currentTime()
        handler.on_question()
        hud.update_session_totals({"footer_growth_units": 1000, "footer_drop_count": 0})
        assert counter.currentTime() >= elapsed
        feed = hud._reward_feed
        if not collapsed and animations_enabled:
            assert len(feed.delegate.growth_counts) == 1
            feed_counter = next(iter(feed.delegate.growth_counts.values()))
            assert 0 < feed_counter.value < feed_counter.target == 1000
        previous_value = counter.value
        storage.row = (3_000, *storage.row[1:])
        handler.on_answer(reviewer, SimpleNamespace(id=7), 3)
        assert counter.target == 2000
        assert counter.value == (previous_value if animations_enabled else 2000)
        QTest.qWait(80)
        bundle = hud.reward_history[-1]
        count_time = counter.currentTime()
        hud.present_committed_result(bundle, applied_growth_units=1000)
        assert counter.target == 2000 and counter.currentTime() == count_time
        # Remounts retain active counts and exact combined history amounts.
        state = hud.export_reward_state()
        displayed = counter.value
        hud.dispose()
        hud = ReviewGardenHud(owner, animations_enabled=animations_enabled)
        handler._reviewer_hud = hud
        hud.update_projection(projection)
        hud.restore_reward_state(state)
        counter = hud._collapsed_feedback._growth_count if collapsed else hud._session_growth_count
        target = hud._collapsed_feedback.amount if collapsed else hud._session_growth
        assert counter.value == displayed and counter.target == 2000
        assert hud._reward_feed.model.entries[-1].item.growth_units == 2000
        if not collapsed and animations_enabled:
            assert hud._reward_feed.export_count_state() == state["feed_counts"]
        QTest.qWait(630)
        assert target.text() == "+20"
        assert not hud._reward_feed.delegate.growth_counts
        # An authoritative decrease snaps to its exact value immediately.
        hud.set_collapsed(False)
        hud.update_session_totals({"footer_growth_units": 3000, "footer_drop_count": 0})
        handler.invalidate_history("review undo")
        assert hud._session_growth_count.value == 3000
        assert hud._session_growth_count.state() == hud._session_growth_count.State.Stopped
        hud.update_session_totals({"footer_growth_units": 1000, "footer_drop_count": 0})
        assert hud._session_growth.text() == "+10"
        QTest.qWait(30)
        assert hud._session_growth.text() == "+10"
        # A changed projection must leave the growth row below the artwork,
        # even when the next paint precedes Qt's queued child-layout pass.
        hud.update_projection(replace(projection, collapsed=False,
            nurture=replace(projection.nurture, stage_points=7900)))
        hud._percent.repaint()
        assert not overlaps
    finally:
        application.removeEventFilter(observer)
        hud.dispose()
        owner.close()
        owner.deleteLater()
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
        assert all(pill.isVisible() for pill in hud._consumable_pills.values())

        if initial_session_state == "hidden":
            owner.hide()
        elif initial_session_state == "collapsed":
            hud.set_collapsed(True)
        hud.restore_reward_state({"feed_expanded": False})
        for n in range(200):
            item = RewardItemProjection(f'coin-{n}', RewardHero.COIN_OR_BOOSTER, 'Checkpoint reward', 'Garden reward', garden_coins=2)
            hud.present_reward(RewardBundleProjection(f'answer-{n}', '2026-09-06T12:00:00Z', (item,)))
        hud.update_session_totals({"footer_growth_units": 12_600})
        owner.show()
        hud.set_collapsed(False)
        QTest.qWait(40)
        assert not hud._reward_feed.isVisibleTo(hud)
        assert not hud._reward_details_toggle.isVisibleTo(hud)
        model = hud._reward_feed.model
        assert len(model.entries) == 200
        assert model.rowCount() < len(model.entries)
        assert hud._session_history_toggle.y() > max(tile.geometry().bottom() for tile in hud._session_metric_tiles)
        initial_height = hud.height()
        initial_footer = hud._session_footer.geometry()
        opened.clear()
        for target in (hud._session_heading, *hud._session_metric_tiles):
            previous_count = len(opened)
            click(target)
            assert len(opened) == previous_count + 1, target.objectName()
            assert opened[-1] == "activity"
            assert not hud._reward_feed.isVisibleTo(hud)
        assert opened == ["activity"] * 4
        group = hud._session_totals_card
        for point in (QPoint(2, 2), QPoint(group.width() - 3, group.height() - 3)):
            previous_count = len(opened)
            QTest.mouseClick(group, Qt.MouseButton.LeftButton, pos=point)
            assert len(opened) == previous_count + 1
            assert opened[-1] == "activity"
        assert group.geometry().bottom() < hud._session_history_toggle.geometry().top()
        opened.clear()
        click(hud._session_history_toggle)
        assert not opened
        assert not hud._reward_feed.isVisibleTo(hud)
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
        # Scrolling older pages must reach every original reward, in order.
        for _ in range(10):
            QTest.qWait(10)
            bar.setValue(bar.maximum())
            if not model.canFetchMore():
                break
        assert not model.canFetchMore()
        assert [model.data(model.index(i), Qt.ItemDataRole.UserRole).item.event_id
                for i in range(model.rowCount())] == [f'coin-{i}' for i in reversed(range(200))]
        before_scroll = bar.value()
        item = RewardItemProjection('new-coin', RewardHero.COIN_OR_BOOSTER, 'Garden reward', 'Garden reward', garden_coins=3)
        hud.present_reward(RewardBundleProjection('new-answer', '2026-09-06T12:00:01Z', (item,)))
        assert before_scroll > 0
        assert bar.value() == 0
        assert len(model.entries) == 201
        assert model.rowCount() < len(model.entries)
        assert model.data(model.index(0), Qt.ItemDataRole.UserRole).item.event_id == 'new-coin'
        # A native short reviewer must keep the Growth line above the pinned
        # totals and the visible feed, including after collapsing and expanding.
        owner.resize(1200, 480)
        owner.setProperty("reviewerAnswerControlsTop", 480)
        hud.set_collapsed(True)
        hud.set_collapsed(False)
        QTest.qWait(40)
        growth_bottom = hud._percent.mapTo(hud._body_scroll.viewport(), hud._percent.rect().bottomRight()).y()
        assert growth_bottom < hud._body_scroll.viewport().height()
        assert hud._reward_feed.isVisibleTo(hud)
        plant.fertilizer_card_batches.clear()
        plant.booster_card_batches.clear()
        hud.update_projection(project_reviewer_hud(engine, storage.state))
        assert hud._consumables.isHidden()
        # Activating or expiring counters changes only the space below the
        # track, including when artwork must shrink in a short reviewer.
        hud.restore_reward_state({"feed_expanded": False})
        hud.present_reward(RewardBundleProjection('spacing-reward', '2026-09-06T12:00:02Z', (item,)), reveal=False)
        for height, feed_expanded in ((900, False), (900, True), (480, False), (480, True)):
            owner.resize(1200, height)
            owner.setProperty("reviewerAnswerControlsTop", height)
            if bool(hud._session_footer.property("historyExpanded")) != feed_expanded:
                click(hud._session_history_chevron)
            anchors = []
            for families in ((), ("fertilizer",), ("fertilizer", "booster"), ("booster",), ()):
                plant.fertilizer_card_batches = ([CardEffectBatch("fertilizer_premium", 800, 400, 44)]
                                                if "fertilizer" in families else [])
                plant.booster_card_batches = ([CardEffectBatch("booster_potion", 100, 100, 45)]
                                             if "booster" in families else [])
                hud.update_projection(replace(project_reviewer_hud(engine, storage.state), position=None, collapsed=False))
                hud.set_collapsed(True)
                hud.set_collapsed(False)
                QTest.qWait(40)
                anchors.append(tuple((w.mapTo(hud, QPoint()).x(), w.mapTo(hud, QPoint()).y(), w.width(), w.height())
                                     for w in (hud._art_region, hud._percent, hud._checkpoint_track)))
                track_bottom = hud._checkpoint_track.mapTo(hud, QPoint(0, hud._checkpoint_track.height())).y()
                pills = [hud._consumable_pills[family] for family in families]
                assert hud._consumables.isHidden() == (not families)
                if pills:
                    assert pills[0].mapTo(hud, QPoint()).y() - track_bottom == 6
                    assert hud._consumables.height() == 24 * len(pills) + 6 * (len(pills) - 1)
                    for pill in pills:
                        assert pill.height() == 24
                        previous_count = len(opened)
                        click(pill)
                        assert len(opened) == previous_count + 1
                    end = pills[-1].mapTo(hud, QPoint(0, pills[-1].height())).y()
                else:
                    end = track_bottom
                assert hud._session_totals_card.mapTo(hud, QPoint()).y() - end == 8, (height, feed_expanded, families)
            assert all(anchor == anchors[0] for anchor in anchors)
    finally:
        hud.dispose()
        owner.close()
        owner.deleteLater()
        application.processEvents()
