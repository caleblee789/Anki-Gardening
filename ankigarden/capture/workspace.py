"""Native capture routes for the consolidated Garden window."""

from ..feature_availability import landmarks_enabled
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from aqt.qt import QApplication, QEvent, QLabel, QPushButton, QRectF, QTabWidget, QTimer, Qt


def verify_capture_isolation():
    """Check the disposable identity before any automatic UI interaction."""
    from aqt import mw

    base = Path(os.environ["ANKI_GARDEN_CAPTURE_RUN_ROOT"]).resolve()
    profile = os.environ["ANKI_GARDEN_CAPTURE_PROFILE_NAME"]
    key = os.environ["ANKI_SINGLE_INSTANCE_KEY"]
    configured = mw.pm.profile
    checks = {
        "disposable_base": str(base).startswith("/private/tmp/anki-release-qa."),
        "profile_base_matches": Path(mw.pm.base).resolve() == base,
        "profile_name_matches": mw.pm.name == profile,
        "window_title_matches": profile in mw.windowTitle(),
        "collection_in_profile": (base / profile / "collection.anki2").is_file(),
        "sync_disconnected": not configured.get("syncKey"),
        "automatic_sync_disabled": not configured.get("autoSync", False),
        "media_sync_disabled": not configured.get("syncMedia", False),
        "unique_instance_key": len(key) >= 20,
    }
    result = {"checks": checks, "passed": all(checks.values()), "pid": os.getpid(), "profile": profile, "base": str(base), "window_title": mw.windowTitle(), "instance_key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:12]}
    if not result["passed"]:
        raise RuntimeError(f"Capture isolation failed: {checks}")
    return result


def _settle():
    app = QApplication.instance()
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()



def expand_contact_sheet_details(runner, label, widget):
    """Show real disclosure contents on representative contact-sheet surfaces."""
    from aqt.qt import QFrame, QScrollArea, QToolButton, QWidget

    targets = {"session-summary-after-review", "sync-rewards-summary"}
    if label not in targets or widget is None:
        return
    checks = {}
    class_name = ("SessionSummaryCard" if label == "session-summary-after-review"
                  else "SyncRewardSummaryCard")
    cards = [child for child in widget.findChildren(QWidget)
             if type(child).__name__ == class_name and child.isVisibleTo(widget)]
    if len(cards) != 1:
        raise RuntimeError(f"Expected one visible {class_name}, found {len(cards)}")
    card = cards[0]
    if label == "session-summary-after-review":
        toggle = card.findChild(QToolButton, "ankiGardenSessionProgressDisclosure")
        if toggle is not None and not card._progress_details_expanded:
            toggle.click()
        _settle()
        panel = card.findChild(QFrame, "ankiGardenSessionBreakdown")
        checks["session_details_expanded"] = (
            card._progress_details_expanded and panel is not None
            and panel.isVisibleTo(card))
    else:
        toggle = card._disclosure
        if toggle is not None and not card.expanded:
            toggle.click()
        _settle()
        checks["sync_details_expanded_or_all_content_visible"] = (
            card.expanded or card._disclosure is None)
    # Details live after the reward list; include their painted contents.
    for scroll in card.findChildren(QScrollArea):
        if scroll.isVisibleTo(card):
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    _settle()
    runner._capture_annotations.setdefault(label, {})["expanded_contact_sheet_details"] = checks
    if not checks or not all(checks.values()):
        raise RuntimeError(f"Expanded contact-sheet details failed: {label}: {checks}")


def plant_naming_audit(runner, widget):
    """Check real visible/accessibility copy against retired stored names."""
    import re
    from aqt.qt import QWidget
    from ..presentation import PlantIdentity

    state = runner.app.storage.state
    retired_names = {
        str(plant.name).strip() for plant in state.plants
        if str(plant.name).strip()
        and str(plant.name).strip() not in {
            PlantIdentity.from_plant(plant).display_name,
            PlantIdentity.from_plant(plant).species_name,
        }
    }
    visible = [child for child in (widget, *widget.findChildren(QWidget))
               if child.isVisibleTo(widget)]
    copy = []
    for child in visible:
        for accessor in ("text", "accessibleName", "accessibleDescription", "toolTip"):
            read = getattr(child, accessor, None)
            if callable(read):
                value = read()
                if isinstance(value, str):
                    copy.append(value)
    text = " ".join(copy)
    leaked = sorted(name for name in retired_names
                    if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text))
    rename_visible = "Rename plant" in text
    return {"custom_names_visible": leaked, "rename_visible": rename_visible,
            "passed": not leaked and not rename_visible}


def workspace_postcondition(runner, widget, route):
    """Read the current page and product state, rather than old dialog markup."""
    dashboard = runner.app.dashboard
    state = runner.app.storage.state
    visible = [child for child in widget.findChildren(QLabel) if child.isVisibleTo(widget) and child.text().strip()]
    actual = str(widget.property("captureWorkspaceRoute") or "")
    issues = []
    if "/" in route:
        section, subsection = route.split("/", 1)
        if str(dashboard.property("workspaceSection")) != section:
            issues.append("workspace-section")
        if section == "collection":
            current = dashboard.collection_section.current_tab
            current = str(getattr(current, "value", current))
            expected = "appearance" if subsection in {"scenery", "decorations"} else subsection
            if current != expected:
                issues.append("collection-tab")
            if subsection in {"scenery", "decorations"}:
                category = "scenery" if subsection == "scenery" else "garden_feature"
                if dashboard.collectible_detail_dialog._appearance_kind != category:
                    issues.append("appearance-category")
        elif section == "shop":
            index = {"plants": 0, "supplies": 1, "scenery": 2, "decorations": 3}[subsection]
            if dashboard._shop.catalog_tabs.currentIndex() != index:
                issues.append("shop-tab")
        elif section == "progress":
            navigation = dashboard.progress_dialog.navigation
            page = dashboard.progress_dialog._normalized_page(subsection, "today")
            if navigation.stack.currentIndex() != navigation.keys.index(page):
                issues.append("progress-tab")
    if route in {"starter", "starter-selected", "starter-placement"}:
        if state.plants or state.starter_selection_complete:
            issues.append("starter-created-before-placement")
        if route == "starter-placement" and not dashboard.scene._interaction.placing:
            issues.append("starter-placement-mode")
    if route.startswith("inspector") and not dashboard.plant_card.isVisibleTo(dashboard):
        issues.append("plant-inspector-visible")
    if route in {"garden", "inspector", "inspector-available"}:
        if dashboard.nurtured_plant_bar.plant_id != str(state.active_plant_id or ""):
            issues.append("nurtured-summary-target")
        if route == "garden" and dashboard.plant_card.isVisibleTo(dashboard):
            issues.append("dismissed-plant-menu")
        if route.startswith("inspector") and dashboard.plant_card.plant_id != dashboard.scene.selected_plant_id():
            issues.append("selected-plant-menu-target")
    if route in {"fertilizer", "charges"}:
        headings = {label.text() for label in widget.findChildren(QLabel)
                    if label.isVisibleTo(widget)}
        if (widget.property("suppliesLayout") != "unified"
                or widget.property("suppliesSection") != route
                or widget.findChild(QTabWidget) is not None
                or not {"Fertilizer", "Growth Charges"} <= headings):
            issues.append("use-item-panel")
    if route == "diagnostics" and not widget.diagnostics_content.isVisibleTo(widget):
        issues.append("diagnostics-expanded")
    details_facts = {}
    if route in {"progress/activity", "study-rewards-retained"}:
        from ..ui.activity_page import ActivityPage
        pages = dashboard.progress_dialog.findChildren(ActivityPage)
        panels = [page.study_rewards_card for page in pages if hasattr(page, "study_rewards_card")]
        details_facts["study_rewards_panel"] = len(panels) == 1 and panels[0].isVisibleTo(widget)
        summary = runner.app.engine.study_rewards_summary()
        retained = (summary["growth_percent"] == 10 and state.streak_days == 6
                    and summary["next_tier_days"] == 100)
        details_facts["retained_growth_after_break"] = retained
        if not details_facts["study_rewards_panel"] or retained != (route == "study-rewards-retained"):
            issues.append("study-rewards-state")
    if actual != route:
        issues.append("workspace-route")
    if not visible:
        issues.append("visible-content")
    naming = plant_naming_audit(runner, widget)
    if not naming["passed"]:
        issues.append("plant-naming")
    return {"workspace_route": actual, "visible_content": bool(visible),
            "plant_naming": naming, "issues": issues, **details_facts}


def capture_plant_menu_layouts(runner, *, sizes=((1040, 720), (860, 580))):
    """Inspect current and edge beds at the normal Garden window size."""
    dashboard = runner.app.dashboard
    selected = dashboard.scene.selected_plant_id()
    size = dashboard.size()
    motion = dashboard._plant_popover_motion_enabled
    output = runner.session_dir / "plant-menu-layouts"
    output.mkdir(exist_ok=True)
    records = []
    dashboard._plant_popover_motion_enabled = lambda: False
    draw_plant = dashboard.scene._draw_plant_asset
    painted_opacity = {}
    def observe_plant(painter, placement, plant):
        painted_opacity[str(plant.get("plant_id", ""))] = painter.opacity()
        return draw_plant(painter, placement, plant)
    dashboard.scene._draw_plant_asset = observe_plant
    try:
        for width, height in sizes:
            dashboard.resize(width, height)
            _settle()
            planted = [plant for plant in runner.app.storage.state.plants if plant.planted]
            targets = {plant.plant_id: plant for plant in (planted[0], max(planted, key=lambda plant: plant.slot_index))} if planted else {}
            for plant in targets.values():
                dashboard.scene.dismiss_selection()
                _settle()
                before_path = output / f"{width}x{height}-bed-{plant.slot_index + 1}-unselected.png"
                before_saved = dashboard.grab().save(str(before_path), "PNG")
                painted_opacity.clear()
                dashboard.scene.keep_card_open(plant.plant_id)
                dashboard._refresh_selected_plant_card()
                _settle()
                card = dashboard.plant_card
                bar = dashboard.nurtured_plant_bar
                bed = dashboard.scene.geometry_layout().bed(plant.slot_index)
                # Use the same painted-art and bed geometry as placement;
                # the broad hit target also includes transparent art padding.
                protected = (bed.visible_region, bed.selection_region, bed.planter_bounds) if bed else ()
                checks = {
                    "ordinary_selection_opaque": painted_opacity.get(plant.plant_id) == 1.0,
                    "unselected_screenshot_saved": bool(before_saved),
                    "popup_visible": card.isVisibleTo(dashboard),
                    "within_scene": dashboard.scene.rect().contains(card.geometry()),
                    "selected_plant_clear": bool(protected) and all(not QRectF(region.x, region.y, region.width, region.height).intersects(QRectF(card.geometry())) for region in protected),
                    "nurtured_target_preserved": bar.plant_id == str(runner.app.storage.state.active_plant_id or ""),
                    "compact_bar": 64 <= bar.height() <= 80,
                    "no_horizontal_scroll": card.content_scroll.horizontalScrollBar().maximum() == 0,
                    "content_fits": card.content_scroll.verticalScrollBar().maximum() == 0,
                    "local_scroll_available": card.content_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded,
                    "close_visible": card.close_btn.isVisibleTo(card),
                }
                path = output / f"{width}x{height}-bed-{plant.slot_index + 1}.png"
                saved = dashboard.grab().save(str(path), "PNG")
                checks["screenshot_saved"] = bool(saved)
                selected_opacity = dict(painted_opacity)
                slots_before = {item.plant_id: item.slot_index for item in planted}
                dashboard._begin_move(plant.plant_id)
                _settle()
                painted_opacity.clear()
                moving_path = output / f"{width}x{height}-bed-{plant.slot_index + 1}-moving.png"
                checks["moving_screenshot_saved"] = bool(dashboard.grab().save(str(moving_path), "PNG"))
                moving_opacity = dict(painted_opacity)
                checks["moving_plant_only_translucent"] = (
                    abs(moving_opacity.get(plant.plant_id, 1.0) - 0.78) < 0.001
                    and all(value == 1.0 for key, value in moving_opacity.items() if key != plant.plant_id)
                )
                dashboard._cancel_move()
                _settle()
                painted_opacity.clear()
                dashboard.grab()
                checks["cancel_restores_opacity_and_slots"] = (
                    painted_opacity.get(plant.plant_id) == 1.0
                    and slots_before == {item.plant_id: item.slot_index for item in planted}
                    and dashboard._placement_draft is None
                )
                records.append({"window": [dashboard.width(), dashboard.height()],
                                "plant_id": plant.plant_id, "bed": plant.slot_index + 1,
                                "popup": list(card.geometry().getRect()), "bar_height": bar.height(),
                                "screenshot": str(path), "unselected_screenshot": str(before_path),
                                "moving_screenshot": str(moving_path),
                                "painted_plant_opacity": selected_opacity,
                                "moving_plant_opacity": moving_opacity, "checks": checks})
    finally:
        if dashboard._placement_draft is not None:
            dashboard._cancel_move()
        dashboard.scene._draw_plant_asset = draw_plant
        dashboard._plant_popover_motion_enabled = motion
        dashboard.resize(size)
        if selected:
            dashboard.scene.keep_card_open(selected)
            dashboard._refresh_selected_plant_card()
        else:
            dashboard.scene.dismiss_selection()
        _settle()
    passed = bool(records) and all(all(row["checks"].values()) for row in records)
    (output / "layout-audit.json").write_text(json.dumps({"passed": passed, "records": records}, indent=2))
    if not passed:
        failures = [{"bed": row["bed"], "window": row["window"], "failed": [key for key, ok in row["checks"].items() if not ok]} for row in records if not all(row["checks"].values())]
        raise RuntimeError(f"Plant menu layout audit failed: {failures}")


def capture_garden_setup_supplement(runner):
    """Review the new setup states in the same isolated, exact-package session."""
    from ..models.state import CardEffectBatch, DailyEconomySnapshot, GardenProjectState
    from ..presentation import project_garden_setup
    from ..environment import GARDEN_FEATURE_CATALOG, SCENERY_CATALOG
    from ..bonus_copy import appearance_effect_groups
    from ..ui.dashboard import AppearanceEffectGroups

    if getattr(runner, "_setup_supplement_captured", False):
        return
    runner._setup_supplement_captured = True
    dashboard = runner.app.dashboard
    engine = runner.app.engine
    storage = runner.app.storage
    snapshot = runner._capture_fixture_state_snapshot("garden-setup-supplement", exact_ledger_restore=True)
    output = runner.session_dir / "garden-setup-supplement"
    output.mkdir(exist_ok=True)
    records = []
    checks = {}
    original_apply = engine.apply_garden_appearance
    original_size = dashboard.size()
    panel = dashboard.collection_section.appearance

    def save(name):
        _settle()
        path = output / (name + ".png")
        assert dashboard.grab().save(str(path), "PNG")
        records.append({"name": name, "screenshot": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "window": [dashboard.width(), dashboard.height()]})

    try:
        state = storage.state
        state.inventory["garden_features"] = ["seedling_sign", "watering_station", "wind_chime"]
        state.daily_economy_snapshot = DailyEconomySnapshot(
            anki_day=state.daily_stats.day,
            snapshot_source="local_review", snapshot_id="garden-setup-capture",
            active_garden_bonus_id="watering_station", active_scenery_effect_id="default",
        )
        state.loadout.display_decoration_id = "watering_station"
        state.loadout.visibility = {"garden_feature": False, "scenery": False}
        original_project = deepcopy(state.garden_project)
        state.garden_project = GardenProjectState(
            landmark_highest_claimed_tier=1,
            displayed_landmark_tier_id="mossy_stone_path",
        )
        plant = engine.active_plant() or state.plants[0]
        plant.name = "Juniper of the Moonlit Library Garden"
        plant.name_customized = True
        plant.fertilizer_card_batches = [CardEffectBatch("fertilizer_basic", 100, 100, 37)]
        plant.fertilizer_card_queue = [CardEffectBatch("fertilizer_quality", 200, 200, 200)]
        plant.booster_card_batches = [CardEffectBatch("booster_potion", 500, 100, 62)]
        dashboard.refresh_all()
        dashboard.open_section("collection", "scenery")
        before = deepcopy(storage.state.to_dict())
        committed = project_garden_setup(engine, storage)
        checks["legacy_hidden_equipment_displays"] = all(item.visible for item in committed.items if item.kind != "landmark")
        checks["visibility_switches_removed"] = not hasattr(panel, "show_weather") and not hasattr(panel, "show_scenery")
        checks["bonuses_paired_with_equipment"] = all(
            panel.setup_rows[item.kind][1].text() == item.appearance_name
            and panel.setup_rows[item.kind][3].text() == "\n\n".join(
                "\n".join((group.effect, *group.conditions))
                for group in appearance_effect_groups(item.appearance_id, state)
            )
            for item in committed.items if item.kind != "landmark"
        )
        panel._select_option("scenery", "spring")
        checks["preview_does_not_save"] = before == storage.state.to_dict()
        checks["preview_preserves_equipped_cards"] = all(
            panel.setup_rows[item.kind][1].text() == item.appearance_name
            for item in committed.items if item.kind != "landmark"
        )
        checks["collection_and_equipped_descriptions_match"] = all(
            any(groups.text() == panel.setup_rows[item.kind][3].text()
                for groups in panel._tiles[(item.kind, item.appearance_id)].findChildren(AppearanceEffectGroups))
            for item in committed.items if (item.kind, item.appearance_id) in panel._tiles
        )
        save("01-unsaved-scenery-preview")
        panel.discard_preview()
        checks["reset_does_not_save"] = before == storage.state.to_dict()
        dashboard.open_section("collection", "decorations")
        save("02-equipped-items-and-effects")
        checks["other_bonuses_section_removed"] = not hasattr(panel, "other_bonuses")
        if landmarks_enabled():
            dashboard.open_section("collection", "garden-landmarks")
            panel.preview_landmark("birdbath_terrace")
            checks["unbuilt_landmark_cannot_apply"] = not panel.appearance_apply.isEnabled()
            checks["landmark_preview_does_not_save"] = before == storage.state.to_dict()
            save("04-unbuilt-landmark-preview")
            panel.discard_preview()
        else:
            checks["landmark_setup_absent"] = "landmark" not in panel.setup_rows
            checks["landmark_tab_absent"] = all(
                tab.value != "garden-landmarks"
                for tab in dashboard.collection_section.subtabs.buttons
            )
        dashboard.open_section("collection", "scenery")
        displayed_project = deepcopy(storage.state.garden_project)
        storage.state.garden_project = deepcopy(original_project)
        panel._select_option("scenery", "spring")
        panel._apply_selected_appearance()
        after = project_garden_setup(engine, storage)
        records.append({"appearance_result": {"displayed": after.items[0].appearance_id, "bonus": after.items[0].bonus_id, "feedback": panel.appearance_feedback.text()}})
        checks["equipment_artwork_matches_effect"] = after.items[0].appearance_id == after.items[0].bonus_id == "spring"
        panel._undo_appearance()
        checks["undo_restores_equipment"] = storage.state.selected_background == before["loadout"]["display_scenery_id"]
        panel._select_option("scenery", "summer")
        failed_before = deepcopy(storage.state.to_dict())
        engine.apply_garden_appearance = lambda *args, **kwargs: (False, "Couldn’t save changes. Try again.")
        panel._apply_selected_appearance()
        checks["failed_save_preserves_state"] = failed_before == storage.state.to_dict()
        save("05-failed-save-feedback")
        engine.apply_garden_appearance = original_apply
        panel.discard_preview()
        storage.state.garden_project = deepcopy(displayed_project)
        dashboard.resize(1040, 720)
        dashboard.open_section("garden")
        storage.state.garden_project = deepcopy(original_project)
        ok, message = engine.apply_garden_appearance("seedling_sign", "spring", {"garden_feature": True, "scenery": True})
        checks["bright_scenery_saved"] = ok
        storage.state.garden_project = deepcopy(displayed_project)
        dashboard.refresh_all()
        save("08-bright-scenery")
        storage.state.inventory["garden_features"] = list(GARDEN_FEATURE_CATALOG)
        storage.state.inventory["scenery"] = list(SCENERY_CATALOG)
        dashboard.resize(1040, 720)
        dashboard.refresh_all()
        for index, (category, kind) in enumerate((
            ("scenery", "scenery"), ("decorations", "garden_feature"),
        )):
            dashboard.open_section("collection", category)
            _settle()
            tiles = [tile for (tile_kind, _), tile in panel._tiles.items() if tile_kind == kind]
            labels = [label for tile in tiles for label in tile.findChildren(QLabel)
                      if label.property("environmentName") or label.property("appearanceEffectCondition") is not None]
            checks[f"{category}_browsing_text_fits"] = bool(labels) and all(
                label.width() > 0 and label.height() >= max(0, label.heightForWidth(label.width()))
                for label in labels
            )
            scroll = next(scroll for scroll in panel._catalog_scrolls if scroll.isAncestorOf(tiles[0]))
            scroll.verticalScrollBar().setValue(0)
            save(f"{10 + index * 2:02d}-all-{category}-top")
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            save(f"{11 + index * 2:02d}-all-{category}-end")
    finally:
        engine.apply_garden_appearance = original_apply
        runner._restore_capture_fixture_state(snapshot)
        dashboard.resize(original_size)
        dashboard.refresh_all()
        dashboard.open_section("collection", "scenery")
        panel.discard_preview()
        _settle()
        (output / "setup-audit.json").write_text(json.dumps({"passed": all(checks.values()), "checks": checks, "records": records}, indent=2))
    if not checks or not all(checks.values()):
        raise RuntimeError(f"Garden setup verification failed: {checks}")


def capture_progress_narrow(runner):
    """Review two-column achievements, the minimum size, and the final row."""
    from aqt.qt import QWidget
    from ..ui.dashboard import achievement_presentations

    dashboard = runner.app.dashboard
    grid = dashboard.achievement_list
    scroll = grid.scroll
    size = dashboard.size()
    position = scroll.verticalScrollBar().value()
    output = runner.session_dir / "progress-narrow"
    output.mkdir(exist_ok=True)
    checks = {}
    try:
        for _ in range(8):
            _settle()
        checks["reference_two_columns"] = grid._columns == 2
        def achievement_text_fits():
            labels = [label for label in grid.container.findChildren(QLabel)
                      if label.text() and label.isVisibleTo(grid.container)]
            return all(label.width() > 0 and label.height() >= max(
                0, label.heightForWidth(label.width())) for label in labels)

        checks["reference_text_fits"] = achievement_text_fits()
        dashboard.resize(860, 580)
        for _ in range(8):
            _settle()
        scroll.verticalScrollBar().setValue(0)
        _settle()
        checks["narrow_size"] = dashboard.width() == 860 and dashboard.height() == 580
        checks["readable_columns"] = grid._columns == 2
        checks["narrow_text_fits"] = achievement_text_fits()
        expected_ids = {view.achievement_id for view in achievement_presentations(runner.app.storage.state)}
        actual_ids = {str(card.property("achievementId")) for card in grid.container.findChildren(QWidget)
                      if card.property("achievementId")}
        checks["all_achievements_present"] = actual_ids == expected_ids
        checks["all_growth_tiers_described"] = all(
            any(f"Permanent Growth bonus: +{view.permanent_growth_percent}%" in label.text()
                for card in grid.container.findChildren(QWidget)
                if card.property("achievementId") == view.achievement_id
                for label in card.findChildren(QLabel))
            for view in achievement_presentations(runner.app.storage.state)
            if view.permanent_growth_percent
        )
        checks["no_horizontal_scroll"] = scroll.horizontalScrollBar().maximum() == 0
        checks["top_saved"] = dashboard.grab().save(str(output / "achievements-top.png"), "PNG")
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        _settle()
        last = grid._entries[-1][0]
        bottom = last.mapTo(scroll.viewport(), last.rect().bottomRight()).y()
        checks["final_row_reachable"] = 0 <= bottom < scroll.viewport().height()
        checks["no_trailing_scroll_space"] = (
            scroll.viewport().height() - 1 - bottom
            <= grid.grid.contentsMargins().bottom() + 2
        )
        checks["end_saved"] = dashboard.grab().save(str(output / "achievements-end.png"), "PNG")
        result = {"passed": all(checks.values()), "window": [dashboard.width(), dashboard.height()],
                  "columns": grid._columns, "last_row_bottom": bottom,
                  "viewport_height": scroll.viewport().height(), "checks": checks}
        (output / "layout-audit.json").write_text(json.dumps(result, indent=2))
    finally:
        dashboard.resize(size)
        for _ in range(8):
            _settle()
        scroll.verticalScrollBar().setValue(position)
        _settle()
    if not checks or not all(checks.values()):
        raise RuntimeError(f"Progress narrow layout audit failed: {checks}")


def capture_plant_beds_layouts(runner, route):
    """Use the existing supplementary capture lane for size and navigation QA."""
    from aqt.qt import QProgressBar
    dashboard = runner.app.dashboard
    page = dashboard.progress_dialog.plant_beds
    output = runner.session_dir / "plant-beds-layouts" / route
    output.mkdir(parents=True, exist_ok=True)
    checks = {}
    measurements = {}
    before = runner.app.storage.state.to_dict()
    for width, height in ((1040, 720), (860, 580), (1440, 900)):
        dashboard.resize(width, height)
        _settle()
        cards = tuple(page.cards.values())
        rects = [card.geometry() for card in cards]
        checks[f"{width}_two_columns"] = rects[0].y() == rects[1].y() and rects[1].x() > rects[0].right()
        checks[f"{width}_equal_row_heights"] = all(rects[i].height() == rects[i + 1].height() for i in (0, 2))
        checks[f"{width}_controlled_width"] = page.content.width() <= 1040
        checks[f"{width}_no_horizontal_scroll"] = page.horizontalScrollBar().maximum() == 0
        checks[f"{width}_four_pixel_bars"] = all(bar.height() == 4 for bar in page.findChildren(QProgressBar))
        checks[f"{width}_content_driven_cards"] = all(card.minimumHeight() < 136 for card in cards)
        # Equal content can legitimately produce equal rows. Check that each
        # row fits its own content instead of requiring an arbitrary inequality.
        checks[f"{width}_row_heights_independent"] = all(
            abs(rects[i].height() - max(cards[j].heightForWidth(rects[j].width())
                                       for j in (i, i + 1))) <= 2
            for i in (0, 2)
        )
        measurements[str(width)] = {"card_heights": [rect.height() for rect in rects],
                                    "heading_to_grid_bottom": rects[-1].bottom() + 1}
        page.reveal_bed("bed_6")
        _settle()
        checks[f"{width}_focus"] = dashboard.focusWidget() is page.cards["bed_6"]
        checks[f"{width}_saved"] = dashboard.grab().save(str(output / f"plant-beds-{width}x{height}.png"), "PNG")
    dashboard.resize(1040, 720)
    dashboard.open_section("progress", "achievements")
    _settle()
    dashboard.achievement_list.scroll.verticalScrollBar().setValue(
        dashboard.achievement_list.scroll.verticalScrollBar().maximum())
    dashboard._open_achievement("flourishing_garden")
    _settle()
    checks["legacy_link_direct_destination"] = dashboard.progress_dialog.current_page_key() == "plant_beds"
    checks["legacy_link_focus"] = dashboard.focusWidget() is page.cards["bed_6"]
    page.reveal_bed("bed_1")
    _settle()
    checks["starter_link_focuses_summary"] = dashboard.focusWidget() is page.starter_summary
    checks["navigation_read_only"] = runner.app.storage.state.to_dict() == before
    page.starter_summary.clearFocus()
    page.verticalScrollBar().setValue(0)
    _settle()
    (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    (output / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise RuntimeError(f"Plant Beds layout/navigation checks failed: {checks}")


def capture_reviewer_appearance_effects(runner):
    """Measure every appearance description in the actual native detail widget."""
    from ..environment import SCENERY_CATALOG, GARDEN_FEATURE_CATALOG
    from ..ui.reviewer_hud import project_reviewer_hud
    from ..ui.reviewer_hud_widget import ReviewGardenHud

    state = runner.app.storage.state
    original_loadout = deepcopy(state.loadout)
    hud = ReviewGardenHud(runner.app.dashboard, animations_enabled=False)
    output = runner.session_dir / "appearance-effects" / "reviewer-details"
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    try:
        for item in (*SCENERY_CATALOG.values(), *GARDEN_FEATURE_CATALOG.values()):
            state.selected_background = item.item_id if item.kind == "scenery" else "default"
            state.selected_garden_feature = item.item_id if item.kind == "garden_feature" else "seedling_sign"
            hud.update_projection(project_reviewer_hud(runner.app.engine, state))
            _settle()
            hud._toggle_effect_details()
            _settle()
            detail = hud._effect_details
            text = detail.text()
            longest = max(detail.fontMetrics().horizontalAdvance(line) for line in text.splitlines())
            passed = (detail.isVisible() and not detail.wordWrap()
                      and f"{item.name}\n{item.effect}" in text
                      and longest + 24 <= detail.width()
                      and detail.screen().availableGeometry().contains(detail.frameGeometry()))
            path = output / f"{item.item_id}.png"
            checks.append({"item_id": item.item_id, "effect": item.effect, "fits": passed,
                           "visible": detail.isVisible(), "text_matches": f"{item.name}\n{item.effect}" in text,
                           "longest_line_width": longest,
                           "within_screen": detail.screen().availableGeometry().contains(detail.frameGeometry()),
                           "size": [detail.width(), detail.height()],
                           "saved": detail.grab().save(str(path), "PNG"), "path": str(path)})
            detail.hide()
    finally:
        state.loadout = original_loadout
        hud.dispose()
        hud.deleteLater()
        _settle()
    (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    if not all(row["fits"] and row["saved"] for row in checks):
        raise RuntimeError(f"Reviewer appearance descriptions failed: {output / 'checks.json'}")


def capture_appearance_effect_layouts(runner, route):
    """Check every catalog effect at the supported macOS viewport sizes."""
    from ..ui.dashboard import AppearanceEffectGroups
    from aqt.qt import QScrollArea

    dashboard = runner.app.dashboard
    original_size = dashboard.size()
    state = runner.app.storage.state
    original_inventory = deepcopy(state.inventory)
    if route.startswith("collection/"):
        from ..environment import SCENERY_CATALOG, GARDEN_FEATURE_CATALOG
        state.inventory["scenery"] = list(SCENERY_CATALOG)
        state.inventory["garden_features"] = list(GARDEN_FEATURE_CATALOG)
        dashboard.collectible_detail_dialog._rebuild_options()
    output = runner.session_dir / "appearance-effects" / route.replace("/", "-")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    try:
        for width, height in ((1280, 800), (1040, 720), (860, 580)):
            dashboard.resize(width, height)
            for _ in range(4):
                _settle()
            if route.startswith("collection/"):
                page = dashboard.collectible_detail_dialog
                original_kind = page._appearance_kind
                shell_positions = []
                for kind in ("scenery", "garden_feature", "scenery"):
                    page.show_category(kind)
                    for _ in range(4):
                        _settle()
                    shell_positions.append({
                        name: [widget.mapTo(dashboard, widget.rect().topLeft()).x(),
                               widget.mapTo(dashboard, widget.rect().topLeft()).y(),
                               widget.width(), widget.height()]
                        for name, widget in (("preview", page.preview_scene),
                                             ("preview_header", page.setup_preview_title),
                                             ("tabs", page.option_tabs.tabBar()),
                                             ("equipped", page.equipped_panel))
                    })
                page.show_category(original_kind)
                for _ in range(4):
                    _settle()
                switch_path = output / f"{width}x{height}-category-switch.png"
                records.append({"item_id": "category-switch", "effect": "Preview and tabs stay in place",
                                "size": [dashboard.width(), dashboard.height()], "requested_size": [width, height],
                                "fits": shell_positions[0] == shell_positions[1] == shell_positions[2],
                                "positions": shell_positions,
                                "saved": dashboard.grab().save(str(switch_path), "PNG"), "path": str(switch_path)})
                page.body_scroll.verticalScrollBar().setValue(0)
                _settle()
                viewport = page.body_scroll.viewport()
                from aqt.qt import QPoint, QRect
                fits = all(viewport.rect().contains(QRect(card.mapTo(viewport, QPoint(0, 0)), card.size()))
                           for kind, card in page.equipped_cards.items() if kind in {"scenery", "garden_feature"})
                path = output / f"{width}x{height}-equipped.png"
                records.append({"item_id": "equipped-viewport", "effect": "Both equipped items visible",
                                "size": [dashboard.width(), dashboard.height()], "requested_size": [width, height],
                                "fits": fits, "saved": dashboard.grab().save(str(path), "PNG"), "path": str(path)})
            groups = [group for group in dashboard.findChildren(AppearanceEffectGroups)
                      if group.isVisibleTo(dashboard)]
            for index, group in enumerate(groups):
                scroll = group.parentWidget()
                while scroll is not None and not isinstance(scroll, QScrollArea):
                    scroll = scroll.parentWidget()
                if scroll is not None:
                    scroll.ensureWidgetVisible(group, 0, 8)
                    _settle()
                labels = group.findChildren(QLabel)
                passed = bool(labels) and all(
                    text.contentsRect().width() > 0
                    and (text.heightForWidth(text.width()) <= text.height() if text.wordWrap()
                         else text.fontMetrics().horizontalAdvance(text.text()) <= text.contentsRect().width())
                    for text in labels
                )
                path = output / f"{width}x{height}-{index:02d}.png"
                saved = dashboard.grab().save(str(path), "PNG")
                records.append({"item_id": group._item_id, "effect": group.text(),
                                "size": [dashboard.width(), dashboard.height()],
                                "requested_size": [width, height], "fits": passed,
                                "saved": saved, "path": str(path)})
            for scroll in dashboard.findChildren(QScrollArea):
                if scroll.isVisibleTo(dashboard):
                    scroll.verticalScrollBar().setValue(0)
        if route == "shop/decorations":
            capture_reviewer_appearance_effects(runner)
            from ..purchases import PurchaseKind
            from ..ui.dashboard import PurchaseConfirmationDialog
            for kind, item_id, inventory_key in (
                (PurchaseKind.GARDEN_FEATURE, "herbalist_hourglass", "garden_features"),
                (PurchaseKind.SCENERY, "snowy", "scenery"),
            ):
                state.inventory[inventory_key] = [value for value in state.inventory[inventory_key] if value != item_id]
                quote = runner.app.engine.quote_purchase(kind, item_id)
                dialog = PurchaseConfirmationDialog(dashboard, runner.app.engine, quote)
                dialog.show()
                _settle()
                effect = dialog.fact_value_labels.get("effect")
                passed = effect is not None and not effect.wordWrap() and (
                    effect.fontMetrics().horizontalAdvance(effect.text()) <= effect.contentsRect().width())
                path = output / f"confirmation-{item_id}.png"
                saved = dialog.grab().save(str(path), "PNG")
                records.append({"item_id": item_id, "effect": effect.text() if effect else "",
                                "size": [dialog.width(), dialog.height()],
                                "requested_size": [dialog.width(), dialog.height()],
                                "fits": passed, "saved": saved, "path": str(path)})
                dialog.close()
                dialog.deleteLater()
    finally:
        state.inventory = original_inventory
        if route.startswith("collection/"):
            dashboard.collectible_detail_dialog._rebuild_options()
        dashboard.resize(original_size)
        _settle()
    (output / "checks.json").write_text(json.dumps(records, indent=2) + "\n")
    if not records or not all(row["fits"] and row["saved"] and row["size"] == row["requested_size"]
                              for row in records):
        raise RuntimeError(f"Appearance effect layout failed: {output / 'checks.json'}")


def capture_workspace_surface(runner, label, route, capture_and_advance):
    def ready():
        from ..models.state import CardEffectBatch
        from ..purchases import PurchaseKind, PurchaseRequest
        from ..ui.dashboard import GardenSettingsDialog, PlantStoryDialog, PurchaseConfirmationDialog

        dashboard = runner.app.dashboard
        engine = runner.app.engine
        state = runner.app.storage.state
        dashboard.open_section("garden")
        dashboard.resize(1040, 720)
        dashboard.toast_region.clear()
        cleanup = None
        widget = dashboard
        plant = engine.active_plant() or next(iter(state.plants), None)

        if route.startswith("starter"):
            dashboard._refresh_onboarding()
            picker = dashboard._inline_starter
            choices = [button for button in picker.findChildren(QPushButton) if button.property("environmentTile")]
            if route in {"starter-selected", "starter-placement"}:
                choices[0].click()
                _settle()
            if route == "starter-placement":
                dashboard._starter_continue.click()
                _settle()
                pending_species = state.onboarding.pending_species
                dashboard.scene.lockedBedActivated.emit(2)
                _settle()
                guidance_visible = dashboard.locked_bed_card.isVisible()
                guidance_path = runner.session_dir / "locked-bed-guidance.png"
                dashboard.locked_bed_card.grab().save(str(guidance_path), "PNG")
                dashboard.locked_bed_card.view_achievement.click()
                _settle()
                navigation_checks = {
                    "guidance_visible": guidance_visible,
                    "bed_progress_destination": (dashboard._workspace_section == "progress"
                                                 and dashboard.progress_dialog.current_page_key() == "plant_beds"),
                    "movement_ended": not dashboard.scene._interaction.placing,
                    "starter_retained": state.onboarding.pending_species == pending_species,
                }
                dashboard.open_section("garden")
                _settle()
                dashboard._starter_continue.click()
                _settle()
                navigation_checks["starter_placement_resumed"] = (
                    dashboard.scene._interaction.placing
                    and state.onboarding.pending_species == pending_species
                    and not state.plants
                )
                runner._capture_annotations.setdefault(label, {})["locked_target_navigation"] = navigation_checks
                if not all(navigation_checks.values()):
                    raise RuntimeError(f"Locked target navigation failed: {navigation_checks}")
                dashboard.scene._interaction.destination_slot = 0
                dashboard._on_placement_destination_changed(0)
        elif "/" in route:
            section, subsection = route.split("/", 1)
            if section == "shop" and subsection == "plants":
                snapshot = runner._capture_fixture_state_snapshot(label, exact_ledger_restore=True)
                cleanup = lambda: runner._restore_capture_fixture_state(snapshot)
                missing = {"sunflower", "peony", "hydrangea"}
                state.plants = [item for item in state.plants if item.species not in missing]
                state.unlocked_species = [item for item in state.unlocked_species if item not in missing]
                runner.app.storage.save()
            if section == "collection" and subsection in {"scenery", "decorations"}:
                cleanup = runner._prepare_appearance_capture_fixture(label, dashboard)
            dashboard.open_section(section, subsection)
            if section == "progress" and subsection == "achievements":
                capture_progress_narrow(runner)
                dashboard.achievement_list.scroll.verticalScrollBar().setValue(0)
                _settle()
            if section == "collection" and subsection == "scenery":
                capture_garden_setup_supplement(runner)
                if landmarks_enabled():
                    from .landmark_audit import capture_landmark_audit
                    capture_landmark_audit(runner)
        elif route == "garden":
            dashboard.scene.dismiss_selection()
        elif route in {"inspector", "inspector-available", "move"}:
            if route == "inspector":
                # Commit the ordinary Nurture action once, including its memory,
                # so the later Anki Home view has the same truthful lineage.
                state.active_plant_id = None
                dashboard._nurture_plant(plant.plant_id)
                runner._development_stress_checkpoint = deepcopy(state.to_dict())
            elif route == "inspector-available":
                plant = next(item for item in state.plants if item.planted and item.plant_id != state.active_plant_id and not item.fully_grown)
            dashboard.scene.keep_card_open(plant.plant_id)
            dashboard._on_scene_selection(plant.plant_id)
            if route == "inspector":
                capture_plant_menu_layouts(runner)
            if route == "move":
                dashboard._begin_move(plant.plant_id)
                cleanup = dashboard._cancel_move
        elif route in {"fertilizer", "charges"}:
            state.consumables.update(fertilizer_basic=2, fertilizer_quality=1, growth_charge_small=2, growth_charge_medium=1)
            if route == "fertilizer":
                plant.fertilizer_card_batches = [CardEffectBatch("fertilizer_basic", 100, 100, 100)]

            def capture_picker():
                dialog = dashboard.fertilizer_dialog
                dialog.focus_supply_group("charges" if route == "charges" else "fertilizer")
                capture(dialog, lambda: runner._close_widget(dialog))

            QTimer.singleShot(80, capture_picker)
            dashboard._open_fertilizer_menu(plant.plant_id, supply_group=route)
            return
        elif route in {"plant", "species"}:
            dashboard.open_section("collection", "plants")
            workspace = dashboard.collection_plants_workspace
            # These historical IDs now cover the same unified panel:
            # a planted species versus a plant kept in storage.
            if route == "plant":
                plant = next((candidate for candidate in runner.app.storage.state.plants if not candidate.planted), plant)
                workspace.show_plant(plant.plant_id)
            else:
                workspace.show_species(plant.species)
            widget = dashboard
        elif route in {"settings", "diagnostics"}:
            widget = GardenSettingsDialog(dashboard, engine, runner.app.config)
            widget.prepare_to_show()
            if route == "diagnostics":
                widget.diagnostics_toggle.setChecked(True)
        elif route == "study-rewards-retained":
            engine._ensure_achievements()
            for achievement_id in ("streak_7", "streak_30"):
                state.achievements[achievement_id].unlocked = True
                state.achievements[achievement_id].progress = 1.0
            for achievement_id in ("streak_100", "streak_365"):
                state.achievements[achievement_id].unlocked = False
                state.achievements[achievement_id].progress = 0.0
            state.streak_days = 6
            state.last_active_day = state.daily_stats.day
            dashboard.open_section("progress", "today")
        elif route == "purchase-fertilizer":
            plant.fertilizer_card_batches = [CardEffectBatch("fertilizer_basic", 100, 100, 100)]
            quote = engine.quote_purchase(PurchaseKind.FERTILIZER, "premium", target_id=plant.plant_id)
            widget = PurchaseConfirmationDialog(dashboard, engine, quote)
        elif route == "purchase-receipt":
            snapshot = runner._capture_fixture_state_snapshot(label, exact_ledger_restore=True)
            cleanup = lambda: runner._restore_capture_fixture_state(snapshot)
            missing = {"sunflower", "peony", "hydrangea"}
            state.plants = [item for item in state.plants if item.species not in missing]
            state.unlocked_species = [item for item in state.unlocked_species if item not in missing]
            runner.app.storage.save()
            quote = engine.quote_purchase(PurchaseKind.SPECIES, "sunflower")
            outcome = engine.confirm_purchase(PurchaseRequest.from_quote(quote))
            if not outcome.success:
                cleanup()
                raise RuntimeError(f"Purchase fixture failed: {outcome.message}")
            dashboard.open_section("shop", "plants")
            dashboard._shop._show_purchase_receipt(outcome)
        else:
            raise ValueError(f"Unknown workspace capture route: {route}")
        if route in {"progress/activity", "study-rewards-retained"}:
            dashboard.progress_dialog._refresh_metric_page("today")
            dashboard.resize(1440, 1000)
            _settle()
            dashboard.progress_dialog.body_scrolls["today"].verticalScrollBar().setValue(0)
        if widget is not dashboard:
            widget.show()
            cleanup = lambda target=widget: runner._close_widget(target)
        capture(widget, cleanup)

    def capture(widget, cleanup):
        widget.setProperty("captureWorkspaceRoute", route)
        _settle()
        if route in {"collection/scenery", "collection/decorations", "shop/scenery", "shop/decorations"}:
            capture_appearance_effect_layouts(runner, route)
        if route in {"progress/activity", "study-rewards-retained"}:
            capture_study_reward_layouts(runner, route)
        if route == "diagnostics":
            if widget._diagnostic_check_pending:
                QTimer.singleShot(20, lambda: capture(widget, cleanup))
                return
            # Captures intentionally reveal the diagnostic result; the real
            # disclosure preserves the user's scroll position on expansion.
            widget.behavior_scroll.ensureWidgetVisible(widget.report_details_toggle, 0, 12)
            _settle()
        capture_and_advance(
            label, widget, close_callback=cleanup,
            cleanup_predicate=(lambda: True) if widget is runner.app.dashboard else None,
        )

    runner._with_dashboard(ready, failure_label=label)


def capture_study_reward_layouts(runner, route):
    """Supplement existing Activity fixtures with minimum-size and link evidence."""
    import json
    from aqt.qt import QPushButton
    from ..ui.activity_page import ActivityPage

    dashboard = runner.app.dashboard
    original_size = dashboard.size()
    output = runner.session_dir / "study-rewards-layouts"
    output.mkdir(exist_ok=True)
    records = []
    try:
        for size_name, width, height in (
            ("reference", original_size.width(), original_size.height()),
            ("minimum", dashboard.minimumWidth(), dashboard.minimumHeight()),
        ):
            dashboard.resize(width, height)
            _settle()
            page = next(page for page in dashboard.findChildren(ActivityPage)
                        if page.isVisibleTo(dashboard))
            card = page.study_rewards_card
            labels = [label for label in card.findChildren(QLabel) if label.text()]
            visible_text = " ".join(label.text() for label in labels)
            checks = {
                "labels_fit": all(label.width() > 0 and label.height() >= max(
                    0, label.heightForWidth(label.width())) for label in labels),
                "single_panel": visible_text.count("Study rewards") == 1,
                "retired_copy_absent": all(text not in visible_text for text in (
                    "Garden Rhythm", "View details", "Reward details", "New Anki day", "qualifying days")),
                "no_horizontal_scroll": dashboard.progress_dialog.body_scrolls["today"].horizontalScrollBar().maximum() == 0,
            }
            path = output / f"{route.replace('/', '-')}-{size_name}.png"
            checks["saved"] = dashboard.grab().save(str(path), "PNG")
            records.append({"size": [dashboard.width(), dashboard.height()],
                            "screenshot": str(path), "checks": checks})
            if not all(checks.values()):
                raise AssertionError(f"Study rewards layout failed: {records[-1]}")
        before = runner.app.storage.state.to_dict()
        target_id = runner.app.engine.study_rewards_summary()["achievement_id"]
        button = next(button for button in card.findChildren(QPushButton)
                      if button.property("semanticId") == "progress.study-rewards-achievements")
        button.click()
        _settle()
        focused = dashboard.focusWidget()
        link_check = (focused is not None and focused.property("achievementId") == target_id)
        if not link_check or before != runner.app.storage.state.to_dict():
            raise AssertionError("Study rewards achievement link failed or changed reward state")
        records.append({"achievement_id": target_id, "link_reveals_achievement": link_check,
                        "navigation_preserves_state": True})
    finally:
        (output / f"{route.replace('/', '-')}.json").write_text(json.dumps(records, indent=2))
        dashboard.resize(original_size)
        dashboard.open_section("progress", "today")
        _settle()


def compact_reward_audit(runner, card):
    """Measure the release card and its real scroll owner, without old layout snapshots."""
    from aqt.qt import QAbstractButton, QScrollArea, Qt

    if card is None:
        return {"checks": {"visible": False}, "passed": False}
    parent = card.parentWidget()
    geometry = runner._widget_bounds_evidence(card, parent)
    visible = lambda child: child.isVisibleTo(card)
    labels = [child for child in card.findChildren(QLabel) if visible(child)]
    buttons = [child for child in card.findChildren(QAbstractButton) if visible(child)]
    text = " ".join(str(child.text()) for child in [*labels, *buttons])
    scrolls = [child for child in card.findChildren(QScrollArea) if visible(child)]
    ranges = [{"horizontal": scroll.horizontalScrollBar().maximum(),
               "vertical": scroll.verticalScrollBar().maximum()} for scroll in scrolls]
    expanded = bool(getattr(card, "_details_expanded", False) or getattr(card, "_expanded", False))
    is_hud = type(card).__name__ == "ReviewGardenHud"
    expected_width = 296 if is_hud else 400
    checks = {
        "visible": card.isVisible() and bool(text.strip()),
        "contained": geometry.get("contained") is True,
        "compact_width": card.width() == min(expected_width, max(1, parent.width() - 48)),
        "bounded_height": 100 <= card.height() <= (parent.height() if is_hud else 520),
        "single_scroll_owner": sum(row["vertical"] > 0 for row in ranges) <= 1,
        "no_horizontal_overflow": all(row["horizontal"] == 0 for row in ranges),
        "scrollable_rewards": is_hud or (len(scrolls) == 1
            and scrolls[0].verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded),
        "nonmodal": not card.isWindow() and card.focusPolicy() == Qt.FocusPolicy.NoFocus,
    }
    checks["plant_naming"] = plant_naming_audit(runner, card)["passed"]
    if is_hud:
        empty_effects = [chip for chip in getattr(card, "_effect_chips", ())
                         if visible(chip) and not any(label.text().strip() for label in chip.findChildren(QLabel))]
        checks["no_empty_effect_rows"] = not empty_effects
    pinned = getattr(card, "_summary_fixed", None)
    if pinned is not None and scrolls:
        scroll = scrolls[0]
        origin = pinned.mapTo(card, pinned.rect().topLeft())
        footer = card._footer
        footer_origin = footer.mapTo(card, footer.rect().topLeft())
        bar = scroll.verticalScrollBar()
        previous = bar.value()
        bar.setValue(bar.maximum())
        _settle()
        checks["totals_and_studied_count_pinned"] = (
            pinned.isVisibleTo(card) and not scroll.isAncestorOf(pinned)
            and pinned.mapTo(card, pinned.rect().topLeft()) == origin
        )
        checks["footer_actions_pinned"] = (footer.isVisibleTo(card)
            and not scroll.isAncestorOf(footer)
            and footer.mapTo(card, footer.rect().topLeft()) == footer_origin)
        bar.setValue(previous)
        _settle()
        checks["growth_breakdown_removed"] = not any(
            phrase in text for phrase in ("Growth distribution", "Plants affected", "Plant growth")
        )
    return {**geometry, "scope": "current compact card", "checks": checks,
            "copy": " ".join(text.split()), "expanded": expanded, "scroll_ranges": ranges,
            "copy_passed": checks["visible"], "content_passed": checks["visible"],
            "nonmodal": {"focus_policy": "NoFocus", "is_window": card.isWindow()},
            "nonmodal_passed": checks["nonmodal"], "passed": all(checks.values())}


def compact_reward_disclosure_audit(runner, card):
    """Exercise the one Details control and restore the captured default view."""
    first = compact_reward_audit(runner, card)
    toggle = getattr(card, "_toggle_details", None) or getattr(card, "_toggle_expanded", None)
    if not callable(toggle):
        return first
    toggle()
    _settle()
    expanded = compact_reward_audit(runner, card)
    toggle()
    _settle()
    final = compact_reward_audit(runner, card)
    return {"scope": "Details open and close", "collapsed": first, "expanded": expanded,
            "restored": final, "passed": first["passed"] and expanded["passed"] and final["passed"]}


def capture_plant_artwork_audit(runner, hud):
    """Record actual menu rendering and alpha bounds at every thumbnail role."""
    from ..ui.plant_art import normalized_plant_pixmap
    from aqt.qt import QImage, QPainter, QColor, QPixmap
    from dataclasses import replace
    from ..ui.reviewer_hud import project_plant_choices

    if getattr(runner, "_plant_artwork_audit_captured", False):
        return
    output = runner.session_dir / "plant-artwork-audit"
    output.mkdir(exist_ok=True)
    engine = runner.app.engine
    species = list(engine.catalog_summary().get("release_ready_species", ()))
    stages = ("seed", "sprout", "young", "mature", "flowering", "rare")
    records = []
    gallery = QPixmap(960, len(species) * 156 + 36)
    gallery.fill(QColor("#081e17"))
    painter = QPainter(gallery)
    painter.setPen(QColor("#e9e8d2"))
    for column, stage in enumerate(stages):
        painter.drawText(column * 160 + 12, 24, "Full Bloom" if stage == "rare" else stage.title())
    for row, plant_type in enumerate(species):
        for column, stage in enumerate(stages):
            asset = engine.resolve_plant_asset(plant_type, stage)
            for size in (28, 40, 44, 48, 56, 72, 88, 112, 128, 136):
                pixmap = normalized_plant_pixmap(asset, stage=stage, logical_size=size, device_pixel_ratio=2)
                image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                points = [(x, y) for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x, y).alpha() > 24]
                if points:
                    bounds = [min(x for x, y in points), min(y for x, y in points), max(x for x, y in points) + 1, max(y for x, y in points) + 1]
                    visible = [(bounds[2] - bounds[0]) / 2, (bounds[3] - bounds[1]) / 2]
                else:
                    visible = [0, 0]
                records.append({"species": plant_type, "stage": stage, "container": size, "visible_art": visible})
                if size == 128:
                    painter.drawPixmap(column * 160 + 16, row * 156 + 36, pixmap)
            painter.drawText(column * 160 + 12, row * 156 + 184, str(plant_type).replace("_", " ").title())
    painter.end()
    gallery.save(str(output / "all-plant-stages.png"), "PNG")
    # The preceding HUD matrix uses synthetic choices without artwork. Reuse
    # the real read-only choice projection for the artwork acceptance view.
    original_projection = hud._projection
    menu_saved = False
    icons_visible = False
    try:
        choices = project_plant_choices(engine, runner.app.storage.state)
        hud._projection = replace(original_projection, plant_choices=choices)
        current_menu = getattr(hud, "_plant_selector_menu", None)
        if current_menu is not None:
            current_menu.close()
        from PyQt6.QtTest import QTest
        QTest.qWait(60)
        hud._select_another_plant()
        menu = getattr(hud, "_plant_selector_menu", None)
        for _ in range(10):
            QTest.qWait(30)
            if menu is not None and menu.isVisible() and menu.size().width() > 0:
                break
        menu_saved = bool(menu and menu.isVisible() and menu.grab().save(str(output / "select-plant-menu.png"), "PNG"))
        icons_visible = bool(menu and menu.actions() and all(
            not action.icon().isNull() and action.isIconVisibleInMenu() for action in menu.actions()
        ))
        if menu:
            menu.close()
    finally:
        hud._projection = original_projection
    (output / "artwork-audit.json").write_text(json.dumps({"menu_captured": menu_saved, "menu_icons_present": icons_visible,
        "choice_count": len(choices), "choose_callback_available": callable(hud._on_choose_plant),
        "hud_visible": hud.isVisible(), "records": records}, indent=2))
    if not menu_saved or not icons_visible:
        raise RuntimeError("Plant chooser did not open for its native artwork audit")
    runner._plant_artwork_audit_captured = True
