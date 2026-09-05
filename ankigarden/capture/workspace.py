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
    """Record the selected beds at three native sizes, without changing game state."""
    dashboard = runner.app.dashboard
    selected = dashboard.scene.selected_plant_id()
    size = dashboard.size()
    motion = dashboard._plant_popover_motion_enabled
    output = runner.session_dir / "plant-menu-layouts"
    output.mkdir(exist_ok=True)
    records = []
    dashboard._plant_popover_motion_enabled = lambda: False
    try:
        for width, height in ((1040, 720), (860, 580), (1440, 900)):
            dashboard.resize(width, height)
            _settle()
            for plant in runner.app.storage.state.plants:
                if not plant.planted:
                    continue
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
                    "compact_bar": 72 <= bar.height() <= 80,
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
            choose = next(button for button in picker.findChildren(QPushButton) if button.text() == "Choose plant")
            if route in {"starter-selected", "starter-placement"}:
                choices[0].click()
            if route == "starter-placement":
                choose.click()
                _settle()
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
            disclosure = next(button for button in dashboard.progress_dialog.findChildren(QPushButton) if button.isVisibleTo(dashboard) and button.text() == "Details")
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
