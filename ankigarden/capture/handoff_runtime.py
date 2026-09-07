"""Capture-only native routes for the five v29 refinement assignments."""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from aqt import mw
from aqt.qt import QAbstractButton, QApplication, QLabel, QMenu, QPainter, QPoint, QPushButton, QScrollArea, QTimer, QWidget

from .workspace import _settle


def _popup_composite(owner, popup):
    """Bind the actual popup pixels to their actual location over its owner."""
    original = owner.grab
    previous = owner.__dict__.get("grab")

    def grab(*args, **kwargs):
        result = original(*args, **kwargs)
        origin = popup.mapToGlobal(QPoint(0, 0)) - owner.mapToGlobal(QPoint(0, 0))
        if not owner.rect().contains(popup.rect().translated(origin)):
            raise RuntimeError("Native popup extends outside its captured owner")
        painter = QPainter(result)
        painter.drawPixmap(origin, popup.grab())
        painter.end()
        return result

    owner.grab = grab
    def restore():
        if previous is None:
            if "grab" in owner.__dict__:
                delattr(owner, "grab")
        else:
            owner.grab = previous
    return restore


def capture_handoff_surface(runner, label, route, capture_and_advance):
    if route.startswith("reviewer-"):
        _capture_reviewer(runner, label, route, capture_and_advance)
        return

    def ready():
        from ..models.state import GardenState
        from ..ui.dashboard import GardenSettingsDialog

        dashboard = runner.app.dashboard
        engine = runner.app.engine
        storage = runner.app.storage
        snapshot = runner._capture_fixture_state_snapshot(label, exact_ledger_restore=True)
        cleanups = []
        closed = False
        checks = {}

        def cleanup():
            nonlocal closed
            if closed:
                return
            closed = True
            dashboard.welcome.suspend()
            for callback in reversed(cleanups):
                callback()
            runner._restore_capture_fixture_state(snapshot)
            dashboard.toast_region.clear()

        def fail(error):
            if closed:
                return
            runner._failures.append({"label": label, "reason": f"{type(error).__name__}: {error}"})
            cleanup()
            runner._next_after(150)

        def capture(popup=None):
            try:
                _settle()
                if popup is not None:
                    checks["popup_visible"] = popup.isVisible()
                    checks["popup_owned_by_capture_process"] = popup in QApplication.topLevelWidgets() or dashboard.isAncestorOf(popup)
                    cleanups.append(_popup_composite(dashboard, popup))
                    runner._capture_annotations.setdefault(label, {})["popup_composite"] = {
                        "object_name": popup.objectName(), "class": type(popup).__name__,
                        "source": "native QWidget pixels at owner-relative position",
                    }
                checks["owner_visible"] = dashboard.isVisible()
                runner._capture_annotations.setdefault(label, {})["handoff"] = checks
                if not checks or not all(value is True for value in checks.values()):
                    raise RuntimeError(f"Native handoff postconditions failed: {checks}")
                capture_and_advance(label, dashboard, close_callback=cleanup,
                                           cleanup_predicate=lambda: closed)
            except Exception as error:
                fail(error)

        try:
            dashboard.open_section("garden")
            dashboard.resize(1040, 720)
            dashboard.toast_region.clear()
            _settle()
            if route in {"starter-nurture", "welcome", "welcome-rewards"}:
                cleanups.append(runner._replace_capture_state(GardenState()))
                if route == "welcome-rewards":
                    from ..storage import HistoricalReviewEntry, HistoricalReviewSnapshot
                    today = date.fromisoformat(engine._scheduler_day())
                    entries = tuple(HistoricalReviewEntry(
                        revlog_id=n, card_id=42, ease=3, interval=1, last_interval=0,
                        factor=2500, response_time_ms=500, review_type=1, answer_ms=n,
                        scheduler_day=(today - timedelta(days=31 - min(29, (n-1)//167))).isoformat(),
                        card_day_ordinal=(n-1) % 167 + 1,
                    ) for n in range(1, 5001))
                    history = HistoricalReviewSnapshot(
                        entries=entries, high_water_revlog_id=5000, fingerprint="capture-welcome-5000-v1")
                    for name in ("load_eligible_review_history", "load_reconciliation_history"):
                        original = getattr(storage, name)
                        setattr(storage, name, lambda: history)
                        cleanups.append(lambda name=name, original=original: setattr(storage, name, original))
                    ok, message = engine.reconcile_reward_history()
                    if not ok:
                        raise RuntimeError(message)
                    checks["history_rewards_committed"] = bool(storage.state.welcome_receipt.history_rewards)
                engine.enter_starter_nursery()
                ok, message = engine.select_starter_species("bonsai")
                if not ok:
                    raise RuntimeError(message)
                ok, message, plant = engine.place_starter(0)
                if not ok or plant is None:
                    raise RuntimeError(message)
                dashboard.refresh_all(acknowledge=False)
                dashboard.open_section("garden")
                dashboard.scene.keep_card_open(plant.plant_id)
                dashboard._on_scene_selection(plant.plant_id)
                if route == "starter-nurture":
                    checks["starter_awaits_nurture"] = str(storage.state.onboarding.step.value) == "nurture"
                    checks["starter_card_visible"] = dashboard.plant_card.isVisible()
                else:
                    dashboard._nurture_plant(plant.plant_id)
                    _settle()
                    dashboard.welcome.maybe_present()
                    dashboard.welcome.settle()
                    _settle()
                    card = dashboard.welcome.card
                    receipt = storage.state.welcome_receipt
                    checks["gift_committed"] = receipt is not None and bool(receipt.gift_rewards)
                    checks["welcome_visible"] = card.isVisible()
                    checks["rewards_immediately_visible"] = card.expanded
                    checks["start_gardening_visible"] = card.start_gardening.isVisible()
                capture()
                return

            state = storage.state
            if route == "decoration-inspector":
                restore = runner._prepare_appearance_capture_fixture(label, dashboard)
                cleanups.append(restore)
                dashboard.open_section("garden")
                _settle()
                feature_id = state.loadout.display_decoration_id
                dashboard.decoration_card.open_decoration(feature_id)
                cleanups.append(dashboard.decoration_card.hide)
                checks["decoration_has_art_anchor"] = dashboard.scene.decoration_geometry() is not None
                capture(dashboard.decoration_card)
                return

            if route in {"collection-menu", "storage-confirmation"}:
                dashboard.open_section("collection", "plants")
                plant = next(p for p in state.plants if p.planted and p.plant_id != state.active_plant_id)
                dashboard.collection_plants_workspace.show_species(plant.species)
                overview = dashboard.collection_plants_workspace.species_page
                _settle()
                # Both routes invoke the production menu/confirmation handler.
                def open_capture():
                    if closed:
                        return
                    try:
                        popup = QApplication.activePopupWidget() if route == "collection-menu" else QApplication.activeModalWidget()
                        if popup is None:
                            popup = next(w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not dashboard and w is not overview and (isinstance(w, QMenu) if route == "collection-menu" else hasattr(w, "reject")))
                        cleanups.append(lambda: popup.close())
                        checks["source_plant_matches"] = plant.plant_id != state.active_plant_id
                        # Species details are already rendered inside the dashboard.
                        capture(popup)
                    except Exception as error:
                        fail(error)
                if route == "collection-menu":
                    row = next(widget for widget in overview.findChildren(QWidget)
                               if widget.property("speciesPlantId") == plant.plant_id)
                    anchor = next(button for button in row.findChildren(QAbstractButton)
                                  if button.property("speciesPlantAction") == "more")
                    scroll = next(s for s in overview.findChildren(QScrollArea) if s.isVisible())
                    scroll.ensureWidgetVisible(anchor, 8, 8)
                    _settle()
                    QTimer.singleShot(180, open_capture)
                    anchor.click()
                else:
                    QTimer.singleShot(180, open_capture)
                    dashboard._collection_plant_action("remove", plant.plant_id, overview)
                return

            if route in {"scenery-preview", "scenery-applied"}:
                cleanups.append(runner._prepare_appearance_capture_fixture(label, dashboard))
                dashboard.open_section("collection", "scenery")
                panel = dashboard.collection_section.appearance
                before = state.loadout.display_scenery_id
                panel._select_option("scenery", "spring")
                _settle()
                checks["preview_selected"] = panel._draft_scenery == "spring"
                checks["preview_equip_visible"] = panel.appearance_apply.isVisible() and panel.appearance_apply.text() == "Equip"
                checks["duplicate_scenery_summary_hidden"] = not panel.selected_title.isVisible() and not panel.bonus_effect.isVisible()
                if route == "scenery-applied":
                    panel.appearance_apply.click()
                    _settle()
                    checks["appearance_committed"] = storage.state.loadout.display_scenery_id == "spring"
                    checks["undo_visible"] = panel.appearance_undo_button.isVisible()
                else:
                    checks["preview_does_not_commit"] = storage.state.loadout.display_scenery_id == before
                capture()
                return

            if route in {"supplies-end", "achievements-end"}:
                if route == "supplies-end":
                    dashboard.open_section("shop", "supplies", item_id="charges")
                else:
                    dashboard.open_section("progress", "achievements")
                _settle()
                scrolls = [s for s in dashboard.findChildren(QScrollArea) if s.isVisibleTo(dashboard) and s.verticalScrollBar().maximum() > 0]
                if not scrolls:
                    raise RuntimeError("Expected a scrollable content owner")
                scroll = max(scrolls, key=lambda s:s.verticalScrollBar().maximum())
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                _settle()
                checks["scroll_at_end"] = scroll.verticalScrollBar().value() == scroll.verticalScrollBar().maximum()
                checks["no_horizontal_scroll"] = scroll.horizontalScrollBar().maximum() == 0
                capture()
                return

            if route == "trophies":
                from ..balance_catalog import ACHIEVEMENT_TROPHIES
                from ..models.state import Achievement
                from ..trophies import trophy_presentations
                for index, trophy in enumerate(ACHIEVEMENT_TROPHIES):
                    key = trophy.source_achievement_id
                    state.achievements[key] = Achievement(key, trophy.display_name, "", unlocked=index == 0,
                                                         progress=1.0 if index == 0 else .4,
                                                         unlocked_at=state.daily_stats.day if index == 0 else None)
                dashboard.open_section("progress", "trophies")
                dashboard.progress_dialog.trophy_room.refresh()
                statuses = [t.unlocked for t in trophy_presentations(state)]
                checks["mixed_trophy_states"] = any(statuses) and not all(statuses)
                capture()
                return

            if route in {"settings-dirty", "diagnostics-details"}:
                dialog = GardenSettingsDialog(dashboard, engine, runner.app.config)
                dialog.prepare_to_show()
                dialog.show()
                cleanups.append(lambda: runner._close_widget(dialog))
                if route == "settings-dirty":
                    dialog.garden_name_edit.setText("My Moonlit Garden")
                    _settle()
                    checks["save_enabled"] = dialog.save_settings.isEnabled()
                    checks["unsaved_indicator"] = dialog.unsaved_count.isVisible()
                    capture(dialog)
                else:
                    # Run the real filesystem check against a bounded manifest
                    # with one deliberately absent fixture path. The installed
                    # package and its artwork bytes remain untouched.
                    fault = TemporaryDirectory(prefix="anki-capture-diagnostics-", dir="/private/tmp")
                    cleanups.append(fault.cleanup)
                    assets_root = storage.assets_root
                    fault_file = "assets/capture_missing_scenery.webp"
                    Path(fault.name, "manifest.json").write_text(json.dumps({"assets": [{"file": fault_file}]}))
                    storage.assets_root = Path(fault.name)
                    cleanups.append(lambda: setattr(storage, "assets_root", assets_root))
                    dialog.diagnostics_toggle.setChecked(True)
                    dialog._begin_diagnostic_check()
                    def diagnosed():
                        try:
                            storage.assets_root = assets_root
                            dialog._refresh_debug_report()
                            dialog.report_details_toggle.setChecked(True)
                            _settle()
                            dialog.behavior_scroll.ensureWidgetVisible(dialog.debug_report, 0, 12)
                            dialog.behavior_scroll.verticalScrollBar().setValue(dialog.behavior_scroll.verticalScrollBar().maximum())
                            _settle()
                            checks["technical_details_expanded"] = dialog.report_details_toggle.isChecked()
                            checks["diagnostics_visible"] = dialog.diagnostics_content.isVisible()
                            checks["real_missing_file_warning"] = fault_file in dialog._checked_missing_artwork
                            checks["warning_in_report"] = fault_file in dialog.debug_report.toPlainText()
                            capture(dialog)
                        except Exception as error:
                            fail(error)
                    runner._wait_for(lambda: not dialog._diagnostic_check_pending, diagnosed, tries=100,
                                     failure_label=label, failure_reason="Diagnostics did not settle", on_error=cleanup)
                return
            raise ValueError(f"Unknown handoff route {route!r}")
        except Exception as error:
            fail(error)

    runner._with_dashboard(ready, failure_label=label)


def _capture_reviewer(runner, label, route, capture_and_advance):
    snapshot, plant_id = runner._prepare_growth_capture_fixture(populated=True)
    restored = False

    def cleanup():
        nonlocal restored
        if restored:
            return
        restored = True
        handler = runner.app.reviewer_hooks
        try:
            handler._hide_reward_list_panel()
            handler.on_state_change("capture-cleanup")
        finally:
            try:
                runner._leave_capture_reviewer()
            finally:
                runner._restore_growth_capture_fixture(snapshot)

    def ready():
        try:
            # The native card readiness gate has already passed. Let shared
            # acquisition settle the HUD and move the pointer; OS activation
            # is only a fallback, never a prerequisite for this fixture.
            handler = runner.app.reviewer_hooks
            handler._dismiss_reward_toast_stack()
            handler._ensure_reviewer_hud(force_collapsed=True, force_dock="right")
            hud = handler._reviewer_hud
            _settle()
            annotation = runner._capture_annotations.setdefault(label, {})
            hud_bounds = runner._external_widget_bounds_evidence(hud, mw)
            annotation["reviewer_hud_geometry"] = {
                "capture_bounds": list(hud_bounds["bounds"]),
                "source": "native collapsed HUD bounds", "visible": hud.isVisible(),
            }
            checks = {"hud_visible": hud.isVisible(), "hud_collapsed": bool(hud._collapsed),
                      "disposable_card_painted": runner._active_reviewer_dom_audit.get("ready") is True,
                      "hud_contained": hud_bounds.get("contained") is True}
            if route == "reviewer-rewards-list":
                from ..reward_presentation import project_committed_reward_bundle
                from ..ui.session_summary import CommittedSessionEvent, CoinAward, PlantGrowthDelta
                engine = runner.app.engine
                plant = engine.plant_story(plant_id)
                for number, (coins, growth, title) in enumerate(((0, 17, "Growth earned"), (7, 40, "Checkpoint reward"), (3, 20, "Garden reward")), 1):
                    identity = f"capture:{label}:{number}"
                    receipts = engine._grant_reward_bundle(
                        identity, source="plant_milestone" if number == 2 else "review", source_id=f"capture-answer-{number}",
                        correlation_id=identity, reason=title, title=title, coins=coins, growth=growth, plant=plant)
                    if not receipts:
                        raise RuntimeError("Committed history fixture produced no receipts")
                    event = CommittedSessionEvent(
                        event_id=identity, anki_day_id=receipts[0].scheduler_day,
                        occurred_at=receipts[0].occurred_at, reward_receipts=receipts,
                        plant_growth=(PlantGrowthDelta(plant_id, "Bonsai", sum(receipt.amount for receipt in receipts if receipt.reward_type == "growth") * 100),),
                        coin_awards=(CoinAward(identity + ":coins", "review", title, coins, correlation_id=identity),) if coins else ())
                    bundle = project_committed_reward_bundle(event)
                    if bundle is not None:
                        accumulator = handler._session_summary_accumulator
                        if accumulator is not None:
                            accumulator.accept_committed(event)
                        hud.present_reward(bundle)
                        handler._update_reviewer_hud_session_totals()
                        from PyQt6.QtTest import QTest
                        QTest.qWait(220)
                        supplemental = runner.session_dir / "reviewer-feedback"
                        supplemental.mkdir(exist_ok=True)
                        if hud._collapsed_feedback.property("feedbackCopy"):
                            if not hud.grab().save(str(supplemental / f"{number:02d}-collapsed-feedback.png")):
                                raise RuntimeError("Could not save collapsed reward evidence")
                runner.app.storage.save()
                hud.open_reward_history()
                _settle()
                panel = hud._reward_feed
                checks.pop("hud_collapsed", None)
                checks["hud_expanded"] = not hud._collapsed
                checks["reward_list_visible"] = panel.isVisible()
                bounds = runner._external_widget_bounds_evidence(hud, mw)
                annotation["reviewer_overlay_geometry"] = {
                    "capture_bounds": list(bounds["bounds"]),
                    "source": "integrated HUD history bounds", "visible": hud.isVisible(),
                }
                checks["reward_list_contained"] = bounds.get("contained") is True
                checks["opened_from_native_reward_summary"] = bool(hud._session_footer.property("historyExpanded"))
            annotation["handoff"] = checks
            if not all(checks.values()):
                raise RuntimeError(f"Reviewer postconditions failed: {checks}")
            capture_and_advance(label, mw, close_callback=cleanup,
                                       cleanup_predicate=lambda: str(mw.state) != "review",
                                       cleanup_timeout_ms=2600)
        except Exception as error:
            runner._failures.append({"label": label, "reason": f"{type(error).__name__}: {error}"})
            cleanup()
            runner._next_after(180)

    runner._with_capture_reviewer(label, ready, on_error=cleanup)
