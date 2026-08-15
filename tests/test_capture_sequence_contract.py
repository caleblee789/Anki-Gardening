from __future__ import annotations

import ast
import textwrap
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = ROOT / "ankigarden" / "capture_ui_faces.py"


def _method_source(class_name: str, method_name: str) -> str:
    source = CAPTURE_PATH.read_text("utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    segment = ast.get_source_segment(source, child)
                    assert segment is not None
                    return segment
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _compiled_method(class_name: str, method_name: str, **globals_: object) -> object:
    namespace = dict(globals_)
    source = textwrap.dedent(_method_source(class_name, method_name))
    exec(
        compile(
            f"from __future__ import annotations\n{source}",
            str(CAPTURE_PATH),
            "exec",
        ),
        namespace,
    )
    return namespace[method_name]


def _literal_assignment(name: str) -> object:
    module = ast.parse(CAPTURE_PATH.read_text("utf-8"))
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} was not found")


def test_capture_contract_covers_every_public_surface_group() -> None:
    groups = dict(_literal_assignment("CAPTURE_FACE_GROUPS"))

    assert _literal_assignment("CAPTURE_CONTRACT_VERSION") == 8

    assert groups["First run"] == (
            "starter-deck-browser-home",
            "starter-overview-home",
            "starter-garden-onboarding",
            "starter-nursery-plants",
            "starter-selection-confirmation",
            "starter-action-above-footer",
        )
    assert groups["Anki home"] == ("deck-browser-home", "overview-home")
    assert groups["Garden"] == (
            "full-garden",
            "hover-outline",
            "selected-plant-not-nurtured",
            "selected-plant-nurtured",
            "fertilizer-unaffordable",
            "fertilizer-affordable",
            "fertilizer-active",
            "move-mode",
            "plant-story",
        )
    assert groups["Anki home — active after Nurture"] == (
        "active-deck-browser-home-after-nurture",
        "active-overview-home-after-nurture",
    )
    assert groups["Garden Progress"] == (
            "growth-zero",
            "growth-nonzero",
            "streak-new",
            "streak-active",
            "coins-zero",
            "coins-activity",
            "progress-overview",
            "progress-achievements",
            "progress-collection",
            "collection-species-overview",
        )
    assert groups["Customize"] == (
        "customize-garden",
        "customize-effects-on",
        "customize-effects-off",
    )
    assert groups["Nursery"] == (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        )
    assert groups["Settings"] == (
            "settings-menu-display",
            "settings-display",
            "settings-display-advanced-open",
            "diagnostics-clean",
            "diagnostics-warning",
        )
    assert groups["Release stress — Garden"] == (
        "long-garden-name",
        "long-plant-name",
        "four-digit-coin-balance",
        "growth-near-stage-completion",
        "all-six-beds-occupied",
        "plant-at-every-stage",
        "fully-grown-plant-without-fertilize",
        "popover-plot-1",
        "popover-plot-2",
        "popover-plot-3",
        "popover-plot-4",
        "popover-plot-5",
        "popover-plot-6",
        "move-occupied-empty-destinations",
        "fertilizer-expiring-under-minute",
        "fertilizer-replacement-confirmation",
    )
    assert groups["Watering can — all six plots"] == (
        "watering-can-garden-plot-1",
        "watering-can-garden-plot-2",
        "watering-can-garden-plot-3",
        "watering-can-garden-plot-4",
        "watering-can-garden-plot-5",
        "watering-can-garden-plot-6",
        "watering-can-deck-browser-plot-1",
        "watering-can-deck-browser-plot-3",
        "watering-can-deck-browser-plot-5",
        "watering-can-overview-plot-2",
        "watering-can-overview-plot-4",
        "watering-can-overview-plot-6",
    )
    assert groups["Release stress — Progress"] == (
        "collection-several-discovered",
        "collection-no-filter-matches",
        "achievement-completed",
        "clear-recall-separate-conditions",
        "streak-at-risk",
        "streak-missed-day",
        "streak-reward-claimed-unclaimed",
    )
    assert groups["Release stress — Nursery"] == (
        "nursery-item-owned",
        "nursery-item-locked",
        "nursery-purchase-success",
        "nursery-final-row-above-footer",
        "missing-artwork-graphical-fallback",
    )
    assert groups["Release stress — Settings"] == (
        "settings-unsaved-changes",
        "settings-validation-error",
        "diagnostics-expanded",
        "production-build-controls-absent",
    )
    assert groups["Accessibility and responsive"] == (
        "reduced-motion-enabled",
        "keyboard-focus-state",
        "narrow-window-responsive",
        "display-scaling-150",
        "display-scaling-200-qt-representative",
    )
    assert groups["Responsive resize matrix"] == tuple(
        spec[0] for spec in _literal_assignment("RESIZE_MATRIX_SPECS")
    )
    labels = [label for group in groups.values() for label in group]
    assert len(labels) == 146
    assert len(labels) == len(set(labels))


def test_capture_runner_drives_every_tab_and_exports_its_contract() -> None:
    source = CAPTURE_PATH.read_text("utf-8")

    for key, label in (
        ("overview", "progress-overview"),
        ("achievements", "progress-achievements"),
        ("collection", "progress-collection"),
    ):
        assert f'self._capture_progress_page("{key}", "{label}")' in source
    for label in (
        "fertilizer-unaffordable",
        "fertilizer-affordable",
        "fertilizer-active",
        "growth-zero",
        "growth-nonzero",
        "streak-new",
        "streak-active",
        "coins-zero",
        "coins-activity",
        "diagnostics-clean",
        "diagnostics-warning",
        "customize-effects-on",
        "customize-effects-off",
        "settings-display-advanced-open",
    ):
        assert f'"{label}"' in source
    for index, label in enumerate(
        (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        )
    ):
        assert f'self._capture_nursery_tab({index}, "{label}")' in source

    assert '"capture_contract_version": CAPTURE_CONTRACT_VERSION' in source
    assert '"capture_groups": [' in source
    assert '"expected_faces": expected_labels' in source
    assert "captured_labels == expected_labels" in source


def test_resize_matrix_covers_every_custom_window_family_and_breakpoint_edge() -> None:
    specs = _literal_assignment("RESIZE_MATRIX_SPECS")
    families = {spec[1] for spec in specs}

    assert families == {
        "dashboard",
        "settings",
        "progress",
        "customize",
        "nursery",
        "story",
        "starter-confirmation",
        "fertilizer",
        "fertilizer-replacement",
        "species-overview",
    }
    assert all(spec[3] > 0 and spec[4] > 0 for spec in specs)
    assert any("below-700" in spec[2] for spec in specs)
    assert any("above-700" in spec[2] for spec in specs)
    assert any("below-760" in spec[2] for spec in specs)
    assert any("above-760" in spec[2] for spec in specs)
    assert any("below-820" in spec[2] for spec in specs)
    assert any("above-820" in spec[2] for spec in specs)
    assert any("below-900" in spec[2] for spec in specs)
    assert any("above-900" in spec[2] for spec in specs)
    assert any("below-1000" in spec[2] for spec in specs)
    assert any("above-1000" in spec[2] for spec in specs)
    assert any("below-1360" in spec[2] for spec in specs)
    assert any("above-1360" in spec[2] for spec in specs)


def test_capture_manifest_records_exact_geometry_and_fails_on_clamping() -> None:
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    requested = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_requested_size",
    )
    geometry_audit = _method_source(
        "_UiFaceCaptureRunner",
        "_find_geometry_layout_warnings",
    )

    for field in (
        '"window_family"',
        '"declared_client_size"',
        '"requested_client_size"',
        '"actual_client_size"',
        '"available_screen_size"',
        '"screen_limited"',
        '"constraint_limited"',
        '"native_normalized"',
        '"normalization_reason"',
        '"frame_overhead"',
        '"frame_size"',
        '"device_pixel_ratio"',
        '"layout_mode"',
        '"transition_path"',
        '"geometry_layout_warnings"',
    ):
        assert field in capture_now
    assert "exact_size_reached" in capture_now
    assert "clamped the requested" in capture_now
    assert "Geometry audit found" in capture_now
    assert "widget.resize(initial_width, initial_height)" in requested
    assert "widget.resize(target_width, target_height)" in requested
    assert '"declared_client_size": [declared_width, declared_height]' in requested
    assert '"requested_client_size": [normalized_width, normalized_height]' in requested
    assert "forbidden-horizontal-overflow" in geometry_audit
    assert "painted-frame-outside-root" in geometry_audit


def test_capture_state_variants_use_writable_sources_and_clear_stale_toasts() -> None:
    growth_zero = _method_source("_UiFaceCaptureRunner", "_capture_growth_zero")
    growth_nonzero = _method_source("_UiFaceCaptureRunner", "_capture_growth_nonzero")
    with_dashboard = _method_source("_UiFaceCaptureRunner", "_with_dashboard")

    assert "plant.growth_points = 0" in growth_zero
    assert "plant.growth_points = 1_250" in growth_nonzero
    assert "plant.growth_stage =" not in growth_zero
    assert "plant.growth_stage =" not in growth_nonzero
    assert 'getattr(dashboard, "toast_region", None)' in with_dashboard
    assert "clear_toast()" in with_dashboard


def test_starter_nursery_capture_does_not_depend_on_a_nested_modal_loop() -> None:
    source = _method_source("_UiFaceCaptureRunner", "_capture_starter_nursery_after")

    assert "NurseryDialog" in source
    assert "setModal(False)" in source
    assert "_open_starter_nursery" not in source


def test_plant_story_capture_does_not_depend_on_a_nested_modal_loop() -> None:
    source = _method_source("_UiFaceCaptureRunner", "_capture_story_after")

    assert "PlantStoryDialog" in source
    assert "setModal(False)" in source
    assert "_open_plant_story" not in source


def test_home_capture_readiness_has_a_webview_callback_watchdog() -> None:
    source = _method_source("_UiFaceCaptureRunner", "_wait_for_home_surface")

    assert "callback_watchdog" in source
    assert "QTimer.singleShot(750, callback_watchdog)" in source
    assert "retry_or_fail()" in source


def test_capture_binds_to_branded_replacement_and_keeps_every_popover_visible() -> None:
    finder = _method_source(
        "_UiFaceCaptureRunner",
        "_visible_fertilizer_replacement_dialog",
    )
    replacement = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fertilizer_replacement_confirmation",
    )
    popover = _method_source("_UiFaceCaptureRunner", "_capture_popover_slot")

    assert "FertilizerReplacementDialog" in finder
    assert "QMessageBox" not in finder
    assert "_visible_fertilizer_replacement_dialog" in replacement
    assert "dashboard.plant_card.isVisible()" in popover


def test_capture_uses_the_real_starter_then_nurture_state_boundary() -> None:
    seed = _method_source("_UiFaceCaptureRunner", "_ensure_capture_state")
    planted = _method_source("_UiFaceCaptureRunner", "_capture_selected_card_after")
    nurtured = _method_source("_UiFaceCaptureRunner", "_capture_nurture_after")

    assert "choose_starter(species)" in seed
    assert "active_plant_id =" not in seed
    assert "set_active_plant" not in seed
    assert "onboarding_state_display" in planted
    assert "OnboardingState.STARTER_PLANTED_NOT_NURTURED" in planted
    assert "active_plant_id =" not in planted
    assert 'getattr(dashboard, "_nurture_plant", None)' in nurtured
    assert '== "first_nurture"' in nurtured
    assert '== "nurture:first"' in nurtured


def test_capture_p0_fixtures_are_coherent_and_transaction_bound() -> None:
    achievement = _method_source("_UiFaceCaptureRunner", "_capture_achievement_completed")
    missed_streak = _method_source("_UiFaceCaptureRunner", "_capture_streak_missed_day")
    streak_rewards = _method_source("_UiFaceCaptureRunner", "_capture_streak_reward_states")
    purchase = _method_source("_UiFaceCaptureRunner", "_capture_nursery_purchase_success")

    assert "stats.reviewed = 100" in achievement
    assert "stats.correct = 100" in achievement
    assert "stats.wrong = 0" in achievement
    assert "stats.completed_due_cards = True" in achievement
    assert "state.total_reviews = max(1_000" in achievement
    assert "state.streak_days = max(30" in achievement
    assert "{7, 14, 30}" in achievement

    assert "StreakPresentationState.ENDED" in missed_streak
    assert "presentation.current_days == 0" in missed_streak
    assert "presentation.previous_days == 3" in missed_streak
    assert "claimed=[7, 14]" in streak_rewards

    assert "dialog._purchase_environment(item.kind, item.item_id)" in purchase
    assert purchase.count("dialog._preview_environment_item(item)") == 2
    assert "owns_environment(item.kind, item.item_id)" in purchase
    assert "dialog.environment_feature_title.text()" in purchase


def test_active_home_faces_run_only_after_the_real_nurture_transaction() -> None:
    init = _method_source("_UiFaceCaptureRunner", "__init__")
    audit = _method_source("_UiFaceCaptureRunner", "_nurtured_capture_plant_id")
    deck_browser = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_active_deck_browser_after_nurture",
    )
    overview = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_active_overview_after_nurture",
    )

    assert init.index("self._capture_nurture,") < init.index(
        "self._capture_active_deck_browser_after_nurture,"
    )
    assert init.index("self._capture_active_deck_browser_after_nurture,") < init.index(
        "self._capture_active_overview_after_nurture,"
    )
    assert 'getattr(state, "active_plant_id", "")' in audit
    assert '== "first_nurture"' in audit
    assert '== "nurture:first"' in audit
    assert "_nurtured_capture_plant_id(label)" in deck_browser
    assert 'self._switch_surface("deckBrowser")' in deck_browser
    assert '"active-deck-browser-home-after-nurture"' in deck_browser
    assert "_nurtured_capture_plant_id(label)" in overview
    assert 'self._switch_surface("overview")' in overview
    assert '"active-overview-home-after-nurture"' in overview


def test_watering_can_faces_cover_six_native_and_six_home_plot_positions() -> None:
    init = _method_source("_UiFaceCaptureRunner", "__init__")
    select_slot = _method_source(
        "_UiFaceCaptureRunner",
        "_set_nurtured_capture_slot",
    )
    garden = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_watering_can_garden_plot",
    )
    home = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_watering_can_home_plot",
    )
    qt_audit = _method_source(
        "_UiFaceCaptureRunner",
        "_audit_qt_nurtured_marker",
    )
    home_audit = _method_source(
        "_UiFaceCaptureRunner",
        "_audit_home_nurtured_marker",
    )
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")

    assert "for slot in range(6)" in init
    assert "for slot in (0, 2, 4)" in init
    assert "for slot in (1, 3, 5)" in init
    assert "self.app.engine.set_active_plant(plant.plant_id)" in select_slot
    assert "GROWTH_THRESHOLDS[-2]" in select_slot
    assert "item.slot_index = index if index < 6 else None" in select_slot
    assert 'f"watering-can-garden-plot-{slot + 1}"' in garden
    assert 'surface == "deckBrowser"' in home
    assert 'self._switch_surface(surface)' in home
    assert '"data-marker-orientation"' in home_audit
    assert "data-marker-pulse" in home_audit
    assert "data-marker-target-ground" in home_audit
    assert "data-marker-planter-rect" in home_audit
    assert "marker was too far from the nurtured plant" in home_audit
    assert "NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO" in home_audit
    assert "pulse_rect.intersects(blocker)" in qt_audit
    assert "marker was too far from the nurtured plant" in qt_audit
    assert "NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO" in qt_audit
    assert 'diagnostic.get("used_fallback", True)' in qt_audit
    assert "probe = scene.grab()" in qt_audit
    assert "_audit_nurtured_marker_capture(label, widget)" in capture_now


def test_watering_can_capture_profile_skips_unrelated_release_interfaces() -> None:
    groups = dict(_literal_assignment("WATERING_CAN_CAPTURE_FACE_GROUPS"))
    init = _method_source("_UiFaceCaptureRunner", "__init__")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")

    assert groups == {
        "Watering can — marker-critical interfaces": (
            "selected-plant-nurtured",
            "customize-garden",
            "settings-display",
            "all-six-beds-occupied",
            "watering-can-garden-plot-1",
            "watering-can-garden-plot-2",
            "watering-can-garden-plot-3",
            "watering-can-garden-plot-4",
            "watering-can-garden-plot-5",
            "watering-can-garden-plot-6",
            "watering-can-deck-browser-plot-1",
            "watering-can-deck-browser-plot-3",
            "watering-can-deck-browser-plot-5",
            "watering-can-overview-plot-2",
            "watering-can-overview-plot-4",
            "watering-can-overview-plot-6",
            "reduced-motion-enabled",
            "narrow-window-responsive",
            "display-scaling-150",
            "display-scaling-200-qt-representative",
        )
    }
    assert 'os.environ.get("ANKI_GARDEN_CAPTURE_PROFILE", "full")' in init
    assert 'if self._capture_profile == "watering-can":' in init
    assert "self._starter_steps = []" in init
    assert "self._capture_nurture," in init
    assert "self._capture_keyboard_focus" not in init.split(
        'if self._capture_profile == "watering-can":', 1
    )[1]
    assert "expected_labels = list(self._capture_face_labels)" in finish
    assert '"capture_profile": self._capture_profile' in finish
    assert "for group, labels in self._capture_face_groups" in finish


def test_capture_manifest_reports_per_face_and_aggregate_display_provenance(
    tmp_path: Path,
) -> None:
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    finish_source = _method_source("_UiFaceCaptureRunner", "_finish")
    finish = _compiled_method(
        "_UiFaceCaptureRunner",
        "_finish",
        QApplication=SimpleNamespace(instance=lambda: None),
        CAPTURE_CONTRACT_VERSION=8,
        QTimer=SimpleNamespace(singleShot=lambda *_args: None),
        datetime=datetime,
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
        os=SimpleNamespace(environ={}),
    )

    assert '"capture_display": self._capture_display' in capture_now
    assert '"capture_display": capture_display' in finish_source
    assert '"capture_displays": capture_displays' in finish_source

    def write_manifest(displays: list[str], directory_name: str) -> dict[str, object]:
        labels = [f"face-{index}" for index in range(len(displays))]
        session_dir = tmp_path / directory_name
        session_dir.mkdir()
        runner = SimpleNamespace(
            _capture_display=displays[-1],
            _capture_face_groups=(("Test", tuple(labels)),),
            _capture_face_labels=tuple(labels),
            _capture_profile="test",
            _capture_records=[
                {"label": label, "capture_display": display}
                for label, display in zip(labels, displays)
            ],
            _close_dashboard=lambda: None,
            _close_top_level_dialogs=lambda: None,
            _failures=[],
            _requested_scale_factor="1.5",
            _screenshots=[f"{label}.png" for label in labels],
            _text_layout_warnings=[],
            session_dir=session_dir,
        )
        finish(runner)
        return __import__("json").loads(
            (session_dir / "manifest.json").read_text("utf-8")
        )

    uniform = write_manifest(["primary", "primary"], "uniform")
    assert uniform["capture_display"] == "primary"
    assert uniform["capture_displays"] == ["primary"]
    assert [
        record["capture_display"] for record in uniform["captures"]
    ] == ["primary", "primary"]

    mixed = write_manifest(
        ["secondary", "secondary", "primary", "primary"],
        "mixed",
    )
    assert mixed["capture_display"] == "mixed"
    assert mixed["capture_displays"] == ["secondary", "primary"]
    assert [
        record["capture_display"] for record in mixed["captures"]
    ] == ["secondary", "secondary", "primary", "primary"]


def test_home_only_capture_profile_uses_screen_compositing_and_rejects_blank_shells() -> None:
    groups = dict(_literal_assignment("WATERING_CAN_HOME_CAPTURE_FACE_GROUPS"))
    init = _method_source("_UiFaceCaptureRunner", "__init__")
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    capture_home = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_home_pixmap",
    )
    pixmap_metrics = _method_source(
        "_UiFaceCaptureRunner",
        "_home_pixmap_metrics",
    )
    pixmap_audit = _method_source(
        "_UiFaceCaptureRunner",
        "_audit_home_pixmap",
    )
    activate_window = _method_source(
        "_UiFaceCaptureRunner",
        "_activate_current_process_window",
    )
    capture_and_advance = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_and_advance",
    )
    move_to_display = _method_source(
        "_UiFaceCaptureRunner",
        "_move_to_capture_display",
    )

    assert groups == {
        "Watering can — Anki Home only": (
            "watering-can-deck-browser-plot-1",
            "watering-can-deck-browser-plot-3",
            "watering-can-deck-browser-plot-5",
            "watering-can-overview-plot-2",
            "watering-can-overview-plot-4",
            "watering-can-overview-plot-6",
        )
    }
    assert 'elif self._capture_profile == "watering-can-home":' in init
    home_branch = init.split(
        'elif self._capture_profile == "watering-can-home":', 1
    )[1].split('elif self._capture_profile != "full":', 1)[0]
    assert "self._capture_nurture" not in home_branch
    assert "for slot in (0, 2, 4)" in home_branch
    assert "for slot in (1, 3, 5)" in home_branch
    assert "self._capture_home_pixmap(widget)" in capture_now
    assert capture_home.index(
        "self._activate_current_process_window(widget)"
    ) < capture_home.index("candidates:")
    assert 'return None, "foreground-window-not-ready"' in capture_home
    assert "screen.grabWindow(" in capture_home
    assert "int(widget.winId())" in capture_home
    assert "widget.mapToGlobal(widget.rect().topLeft())" in capture_home
    assert "origin.x() - screen_geometry.x()" in capture_home
    assert "origin.y() - screen_geometry.y()" in capture_home
    assert "web_pixmap = web.grab()" in capture_home
    assert "QPainter(shell_pixmap)" in capture_home
    assert '"qt-shell-with-webview"' in capture_home
    assert '"foreground-screen-region"' in capture_home
    assert '"native-window"' in capture_home
    assert 'if row[2]["passed"]' in capture_home
    assert "self._audit_home_pixmap(" in capture_now
    assert "expected_width=int(widget.width())" in capture_now
    assert "expected_height=int(widget.height())" in capture_now
    assert 'annotation["home_capture_method"] = capture_method' in capture_now
    assert "dominant_ratio < 0.92" in pixmap_metrics
    assert "saturated_ratio >= 0.04" in pixmap_metrics
    assert "aspect_ratio_error <= 0.12" in pixmap_metrics
    assert "brand_ratio >= 0.001" in pixmap_metrics
    assert "dark_ratio >= 0.003" in pixmap_metrics
    assert '"semantic_identity_passed": semantic_passed' in pixmap_metrics
    assert "branded Garden" in pixmap_audit
    assert "self._activate_current_process_window(widget)" in capture_and_advance
    assert 'platform.system() != "Darwin"' in activate_window
    assert 'ctypes.CDLL("/usr/lib/libobjc.A.dylib")' in activate_window
    assert 'objc_get_class(b"NSRunningApplication")' in activate_window
    assert 'sel_register_name(b"currentApplication")' in activate_window
    assert 'sel_register_name(b"activateWithOptions:")' in activate_window
    assert 'sel_register_name(b"makeKeyAndOrderFront:")' in activate_window
    assert 'sel_register_name(b"isActive")' in activate_window
    assert 'sel_register_name(b"isKeyWindow")' in activate_window
    assert "for _attempt in range(5):" in activate_window
    assert "and not self._capture_force_primary" in move_to_display
    assert "branded or viable" not in capture_home
    assert 'return None, "semantic-window-not-ready"' in capture_home
    assert 'if self._capture_display == "secondary"' in capture_home
    assert "self._capture_force_primary = True" in capture_home
    assert "self._move_to_capture_display(widget)" in capture_home


def test_home_capture_waits_for_exact_foreground_window_before_grabbing_pixels() -> None:
    warnings: list[str] = []
    capture_home = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_home_pixmap",
        logger=SimpleNamespace(warning=lambda message: warnings.append(message)),
    )

    class GrabProbe:
        def windowHandle(self) -> object:
            raise AssertionError("capture source reached before foreground readiness")

    runner = SimpleNamespace(
        _activate_current_process_window=lambda _widget: False,
    )
    assert capture_home(runner, GrabProbe()) == (
        None,
        "foreground-window-not-ready",
    )
    assert warnings == [
        "Anki Garden capture: exact Anki Home window did not become foreground"
    ]


def test_current_window_activation_keeps_the_cross_platform_qt_path() -> None:
    calls: list[object] = []

    class Handle:
        def requestActivate(self) -> None:
            calls.append("requestActivate")

    class Widget:
        def show(self) -> None:
            calls.append("show")

        def windowHandle(self) -> Handle:
            calls.append("windowHandle")
            return Handle()

        def raise_(self) -> None:
            calls.append("raise")

        def activateWindow(self) -> None:
            calls.append("activateWindow")

        def update(self) -> None:
            calls.append("widget.update")

        def isVisible(self) -> bool:
            calls.append("isVisible")
            return True

    class App:
        def setActiveWindow(self, widget: object) -> None:
            calls.append(("setActiveWindow", widget))

        def processEvents(self) -> None:
            calls.append("processEvents")

    widget = Widget()
    app = App()
    activate_window = _compiled_method(
        "_UiFaceCaptureRunner",
        "_activate_current_process_window",
        QApplication=SimpleNamespace(instance=lambda: app),
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
        mw=SimpleNamespace(
            web=SimpleNamespace(update=lambda: calls.append("web.update")),
        ),
        platform=SimpleNamespace(system=lambda: "Linux"),
    )

    assert activate_window(object(), widget) is True
    assert calls == [
        "show",
        "windowHandle",
        "requestActivate",
        "raise",
        "activateWindow",
        ("setActiveWindow", widget),
        "widget.update",
        "web.update",
        "processEvents",
        "isVisible",
    ]


def test_secondary_home_capture_retries_on_primary_instead_of_selecting_desktop() -> None:
    class Pixmap:
        def __init__(self, name: str, width: int, height: int) -> None:
            self.name = name
            self._width = width
            self._height = height

        def isNull(self) -> bool:
            return False

        def toImage(self) -> "Pixmap":
            return self

        def width(self) -> int:
            return self._width

        def height(self) -> int:
            return self._height

    class Point:
        def x(self) -> int:
            return 0

        def y(self) -> int:
            return 0

    class Rect:
        def topLeft(self) -> Point:
            return Point()

    class Screen:
        def __init__(self, widget: "Widget", name: str) -> None:
            self.widget = widget
            self.name = name

        def geometry(self) -> Point:
            return Point()

        def grabWindow(self, window_id: int, *_geometry: int) -> Pixmap:
            if self.name == "primary" and window_id == 0:
                return Pixmap("garden", 2002, 1710)
            if window_id == 0:
                return Pixmap("desktop", 2002, 1710)
            return Pixmap("blank-native", 1001, 855)

    class Handle:
        def __init__(self, widget: "Widget") -> None:
            self.widget = widget

        def screen(self) -> Screen:
            return Screen(self.widget, self.widget.capture_display)

    class Widget:
        def __init__(self) -> None:
            self.capture_display = "secondary"

        def windowHandle(self) -> Handle:
            return Handle(self)

        def mapToGlobal(self, _point: Point) -> Point:
            return Point()

        def rect(self) -> Rect:
            return Rect()

        def width(self) -> int:
            return 667

        def height(self) -> int:
            return 570

        def grab(self) -> Pixmap:
            return Pixmap("blank-widget", 1001, 855)

        def winId(self) -> int:
            return 42

    widget = Widget()
    warnings: list[tuple[object, ...]] = []
    process_events: list[bool] = []
    capture_home = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_home_pixmap",
        QApplication=SimpleNamespace(
            instance=lambda: SimpleNamespace(
                processEvents=lambda: process_events.append(True),
            ),
        ),
        QGuiApplication=SimpleNamespace(
            primaryScreen=lambda: Screen(widget, "primary"),
        ),
        QPainter=object,
        logger=SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            warning=lambda *args: warnings.append(args),
        ),
        mw=SimpleNamespace(web=None),
        time=SimpleNamespace(sleep=lambda _seconds: None),
    )
    runner = SimpleNamespace(
        _capture_display="secondary",
        _capture_force_primary=False,
        _activate_current_process_window=lambda _widget: True,
    )

    def metrics(candidate: Pixmap, **_expected: int) -> dict[str, object]:
        semantic = candidate.name == "garden"
        return {
            "generic_content_passed": candidate.name == "desktop",
            "semantic_identity_passed": semantic,
            "passed": semantic,
            "brand_sample_ratio": 0.01 if semantic else 0.0,
            "dark_shell_sample_ratio": 0.1 if semantic else 0.0,
        }

    def move_to_display(target: Widget) -> None:
        runner._capture_display = "primary"
        target.capture_display = "primary"

    runner._home_pixmap_metrics = metrics
    runner._move_to_capture_display = move_to_display

    pixmap, method = capture_home(runner, widget)
    assert method == "foreground-screen-region"
    assert pixmap.name == "garden"
    assert runner._capture_force_primary is True
    assert widget.capture_display == "primary"
    assert process_events == [True]
    assert len(warnings) == 1
    assert warnings[0][1] == "secondary"
    assert warnings[0][2][0] == {
        "method": "foreground-screen-region",
        "pixel_size": [2002, 1710],
        "generic": True,
        "semantic": False,
        "brand_ratio": 0.0,
    }


def test_remaining_release_faces_prepare_and_audit_their_exact_ui_states() -> None:
    clear_recall = _method_source(
        "_UiFaceCaptureRunner", "_capture_clear_recall_conditions"
    )
    starter = _method_source(
        "_UiFaceCaptureRunner", "_capture_starter_nursery_after"
    )
    final_row = _method_source(
        "_UiFaceCaptureRunner", "_capture_nursery_final_row"
    )
    footer_audit = _method_source(
        "_UiFaceCaptureRunner", "_audit_nursery_action_above_footer"
    )
    missing_artwork = _method_source(
        "_UiFaceCaptureRunner", "_capture_missing_artwork_fallback"
    )
    fully_grown = _method_source(
        "_UiFaceCaptureRunner", "_capture_fully_grown_without_fertilize"
    )
    production = _method_source(
        "_UiFaceCaptureRunner", "_capture_production_controls_absent"
    )

    assert "stats.reviewed = 12" in clear_recall
    assert "stats.correct = 10" in clear_recall
    assert "stats.wrong = 2" in clear_recall
    assert '("Accuracy", "83% / 90%")' in clear_recall
    assert '("Anki card answers", "12 / 20")' in clear_recall

    assert 'button_prefix="Choose"' in starter
    assert 'row="first"' in starter
    assert "dialog.scroll.ensureWidgetVisible(first_action, 0, 28)" in starter
    assert "scrollbar.maximum()" in final_row
    assert 'row="last"' in final_row
    assert "button.mapTo(viewport" in footer_audit
    assert "footer.mapTo(dialog" in footer_audit

    assert 'lambda _item_id: None' in missing_artwork
    assert "dialog._preview_environment_item(item)" in missing_artwork
    assert "not pixmap.isNull()" in missing_artwork
    assert "_asset_preview_label(" in missing_artwork
    assert "_item_preview_label(" in missing_artwork
    assert '"resolve_plant_asset"' in missing_artwork
    assert '"resolve_plant_image"' in missing_artwork
    assert '"resolve_item_asset"' in missing_artwork
    for audit_field in (
        "environment_text_placeholder_absent",
        "plant_graphical_pixmap_present",
        "plant_text_placeholder_absent",
        "plant_geometry_stable",
        "item_graphical_pixmap_present",
        "item_text_placeholder_absent",
        "item_geometry_stable",
    ):
        assert audit_field in missing_artwork

    assert 'getattr(plant, "fully_grown", False)' in fully_grown
    assert "dashboard.plant_card.fertilize.isVisible()" in fully_grown
    assert "dashboard.plant_card.choose_another.isVisible()" in fully_grown

    assert "dashboard_ui.DEVELOPMENT_MUTATION_ENABLED = False" in production
    for control in (
        "unlock_development",
        "development_panel",
        "populate_development",
        "restore_development",
        "Unlock development tools",
        "Populate test garden",
        "Restore backup",
    ):
        assert control in production
    assert '"production_capability_branch_forced": True' in production


def test_200_percent_face_is_a_labeled_qt_representative_with_manifest_audit() -> None:
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    representative = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_display_scaling_200_representative",
    )

    assert '"display-scaling-200-qt-representative"' in representative
    assert "dashboard.MIN_WINDOW_WIDTH" in representative
    assert "dashboard.MIN_WINDOW_HEIGHT" in representative
    assert '"representative_kind": "deterministic-qt-logical-viewport"' in representative
    assert '"effective_scale_percent": 200' in representative
    assert '"os_display_scaling_changed": False' in representative
    assert "self._requested_scale_factor" in representative
    assert "os.environ" not in representative
    assert "record[\"audit\"] = dict(annotation)" in capture_now
    assert 'if label == "display-scaling-150":' in capture_now
    assert '"scene_top_gap": scene_top_gap' in capture_now
    assert "scene_top_gap <= 24" in capture_now
    assert "title_stack_extra_height <= 16" in capture_now
    assert '"feedback_panel_visible": bool(dashboard.feedback_panel.isVisible())' in capture_now
