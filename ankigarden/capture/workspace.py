"""Native capture routes for the consolidated Garden window."""

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
            if current != subsection:
                issues.append("collection-tab")
        elif section == "shop":
            index = {"plants": 0, "supplies": 1, "scenery": 2, "decorations": 3}[subsection]
            if dashboard._shop.catalog_tabs.currentIndex() != index:
                issues.append("shop-tab")
        elif section == "progress":
            navigation = dashboard.progress_dialog.navigation
            if navigation.stack.currentIndex() != navigation.keys.index(subsection):
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
        tabs = widget.findChild(QTabWidget)
        if tabs is None or tabs.currentIndex() != (1 if route == "charges" else 0):
            issues.append("use-item-tab")
    if route == "diagnostics" and not widget.diagnostics_content.isVisibleTo(widget):
        issues.append("diagnostics-expanded")
    if actual != route:
        issues.append("workspace-route")
    if not visible:
        issues.append("visible-content")
    return {"workspace_route": actual, "visible_content": bool(visible), "issues": issues}


def capture_plant_menu_layouts(runner):
    """Inspect the current and edge bed at the two supported release sizes."""
    dashboard = runner.app.dashboard
    selected = dashboard.scene.selected_plant_id()
    size = dashboard.size()
    motion = dashboard._plant_popover_motion_enabled
    output = runner.session_dir / "plant-menu-layouts"
    output.mkdir(exist_ok=True)
    records = []
    dashboard._plant_popover_motion_enabled = lambda: False
    try:
        for width, height in ((1040, 720), (860, 580)):
            dashboard.resize(width, height)
            _settle()
            planted = [plant for plant in runner.app.storage.state.plants if plant.planted]
            targets = {plant.plant_id: plant for plant in (planted[0], max(planted, key=lambda plant: plant.slot_index))} if planted else {}
            for plant in targets.values():
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
                records.append({"window": [dashboard.width(), dashboard.height()],
                                "plant_id": plant.plant_id, "bed": plant.slot_index + 1,
                                "popup": list(card.geometry().getRect()), "bar_height": bar.height(),
                                "screenshot": str(path), "checks": checks})
    finally:
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
    from datetime import date, timedelta
    from ..models.state import CardEffectBatch, DailyEconomySnapshot, GardenProjectState
    from ..presentation import project_garden_setup
    from ..environment import GARDEN_FEATURE_CATALOG, SCENERY_CATALOG

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
            anki_day=state.daily_stats.day, garden_rhythm_percent=4,
            snapshot_source="local_review", snapshot_id="garden-setup-capture",
            active_garden_bonus_id="watering_station", active_scenery_effect_id="default",
        )
        state.daily_loadout.pending_garden_feature_id = "wind_chime"
        state.daily_loadout.queued_for_day = (date.fromisoformat(state.daily_stats.day) + timedelta(days=1)).isoformat()
        state.daily_loadout.queued_scenery_id = "spring"
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
        panel._select_option("scenery", "spring")
        checks["preview_does_not_save"] = before == storage.state.to_dict()
        save("01-unsaved-scenery-preview")
        panel.discard_preview()
        checks["reset_does_not_save"] = before == storage.state.to_dict()
        dashboard.open_section("collection", "decorations")
        save("02-independent-appearance-bonuses-and-schedule")
        panel.scheduled_bonuses.button.click()
        _settle()
        panel.setup_scroll.ensureWidgetVisible(panel.scheduled_host, 0, 0)
        save("09-scheduled-bonus-details")
        panel.scheduled_bonuses.button.click()
        panel.setup_scroll.verticalScrollBar().setValue(0)
        panel.other_bonuses.button.click()
        _settle()
        panel.setup_scroll.ensureWidgetVisible(panel.other_bonuses, 0, 0)
        save("03-other-active-bonuses")
        panel.other_bonuses.button.click()
        dashboard.open_section("collection", "garden-landmarks")
        panel.preview_landmark("birdbath_terrace")
        checks["unbuilt_landmark_cannot_apply"] = not panel.appearance_apply.isEnabled()
        checks["landmark_preview_does_not_save"] = before == storage.state.to_dict()
        save("04-unbuilt-landmark-preview")
        panel.discard_preview()
        dashboard.open_section("collection", "scenery")
        displayed_project = deepcopy(storage.state.garden_project)
        storage.state.garden_project = deepcopy(original_project)
        panel._select_option("scenery", "spring")
        panel._apply_selected_appearance()
        after = project_garden_setup(engine, storage)
        records.append({"appearance_result": {"displayed": after.items[0].appearance_id, "bonus": after.items[0].bonus_id, "feedback": panel.appearance_feedback.text()}})
        checks["appearance_preserves_bonus"] = after.items[0].appearance_id == "spring" and after.items[0].bonus_id == "default"
        panel._undo_appearance()
        checks["undo_restores_appearance_only"] = storage.state.selected_background == before["loadout"]["display_scenery_id"]
        panel._select_option("scenery", "summer")
        failed_before = deepcopy(storage.state.to_dict())
        engine.apply_garden_appearance = lambda *args, **kwargs: (False, "Couldn’t save changes. Try again.")
        panel._apply_selected_appearance()
        checks["failed_save_preserves_state"] = failed_before == storage.state.to_dict()
        save("05-failed-save-feedback")
        engine.apply_garden_appearance = original_apply
        panel.discard_preview()
        storage.state.garden_project = deepcopy(displayed_project)
        dashboard.resize(860, 580)
        dashboard.open_section("collection", "decorations")
        save("06-compact-garden-setup")
        panel.other_bonuses.button.click()
        _settle()
        panel.setup_scroll.ensureWidgetVisible(panel.other_bonuses, 0, 0)
        save("07-compact-additional-bonuses")
        panel.other_bonuses.button.click()
        dashboard.resize(1040, 720)
        dashboard.open_section("garden")
        storage.state.garden_project = deepcopy(original_project)
        ok, message = engine.apply_garden_appearance("seedling_sign", "spring", {"garden_feature": True, "scenery": True})
        checks["bright_scenery_saved"] = ok
        storage.state.garden_project = deepcopy(displayed_project)
        dashboard.refresh_all()
        save("08-bright-scenery-and-displayed-landmark")
        storage.state.inventory["garden_features"] = list(GARDEN_FEATURE_CATALOG)
        storage.state.inventory["scenery"] = list(SCENERY_CATALOG)
        dashboard.resize(860, 580)
        dashboard.refresh_all()
        for index, (category, kind) in enumerate((
            ("scenery", "scenery"), ("decorations", "garden_feature"),
        )):
            dashboard.open_section("collection", category)
            _settle()
            tiles = [tile for (tile_kind, _), tile in panel._tiles.items() if tile_kind == kind]
            labels = [label for tile in tiles for label in tile.findChildren(QLabel)
                      if label.property("environmentName") or label.property("environmentEffect")]
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
    """Review one practical narrow size and the reachable final achievement row."""
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
        dashboard.resize(860, 580)
        for _ in range(8):
            _settle()
        scroll.verticalScrollBar().setValue(0)
        _settle()
        checks["narrow_size"] = dashboard.width() == 860 and dashboard.height() == 580
        checks["readable_columns"] = grid._columns == 2
        expected_ids = {view.achievement_id for view in achievement_presentations(runner.app.storage.state)}
        actual_ids = {str(card.property("achievementId")) for card in grid.container.findChildren(QWidget)
                      if card.property("achievementId")}
        checks["all_achievements_present"] = actual_ids == expected_ids
        checks["no_horizontal_scroll"] = scroll.horizontalScrollBar().maximum() == 0
        checks["top_saved"] = dashboard.grab().save(str(output / "achievements-top.png"), "PNG")
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        _settle()
        last = grid._entries[-1][0]
        bottom = last.mapTo(scroll.viewport(), last.rect().bottomRight()).y()
        checks["final_row_reachable"] = 0 <= bottom < scroll.viewport().height()
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
            if route == "starter-selected":
                # The former confirmation screen is now the retained tile
                # selection after returning from placement without planting.
                dashboard._cancel_move()
                _settle()
            if route == "starter-placement":
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
            if section == "collection" and subsection == "scenery":
                capture_garden_setup_supplement(runner)
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
                dialog.findChild(QTabWidget).setCurrentIndex(1 if route == "charges" else 0)
                capture(dialog, lambda: runner._close_widget(dialog))

            QTimer.singleShot(80, capture_picker)
            dashboard._open_fertilizer_menu(plant.plant_id)
            return
        elif route == "plant":
            widget = PlantStoryDialog(dashboard, engine, plant.plant_id)
        elif route == "species":
            widget = dashboard._build_species_overview_dialog(plant.species)
        elif route in {"settings", "diagnostics"}:
            widget = GardenSettingsDialog(dashboard, engine, runner.app.config)
            widget.prepare_to_show()
            if route == "diagnostics":
                widget.diagnostics_toggle.setChecked(True)
        elif route == "today-details":
            dashboard.open_section("progress", "today")
            _settle()
            disclosure = next(button for button in dashboard.progress_dialog.findChildren(QPushButton) if button.isVisibleTo(dashboard) and button.parentWidget().property("semanticId") == "progress.today-details")
            disclosure.click()
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
        if widget is not dashboard:
            widget.show()
            cleanup = lambda target=widget: runner._close_widget(target)
        capture(widget, cleanup)

    def capture(widget, cleanup):
        widget.setProperty("captureWorkspaceRoute", route)
        _settle()
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
        "collapsed_content_fits": expanded or all(row["vertical"] == 0 for row in ranges),
        "nonmodal": not card.isWindow() and card.focusPolicy() == Qt.FocusPolicy.NoFocus,
    }
    if is_hud:
        empty_effects = [chip for chip in getattr(card, "_effect_chips", ())
                         if visible(chip) and not any(label.text().strip() for label in chip.findChildren(QLabel))]
        checks["no_empty_effect_rows"] = not empty_effects
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
