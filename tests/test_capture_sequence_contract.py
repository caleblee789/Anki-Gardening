from __future__ import annotations

import ast
import re
import textwrap
from collections import Counter
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


def _compiled_function(function_name: str, **globals_: object) -> object:
    source = CAPTURE_PATH.read_text("utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            namespace = dict(globals_)
            exec(
                compile(
                    "from __future__ import annotations\n" + segment,
                    str(CAPTURE_PATH),
                    "exec",
                ),
                namespace,
            )
            return namespace[function_name]
    raise AssertionError(f"Missing function {function_name}")


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


def _compiled_renderer_family_contract() -> dict[str, object]:
    source = CAPTURE_PATH.read_text("utf-8")
    module = ast.parse(source)
    assignment_names = {
        "CAPTURE_FACE_GROUPS",
        "RESIZE_MATRIX_SPECS",
        "RESIZE_MATRIX_LAYOUT_MODES",
        "_HOME_CAPTURE_LABELS",
        "_DASHBOARD_CAPTURE_LABELS",
        "_PROGRESS_CAPTURE_LABELS",
        "_NURSERY_CAPTURE_LABELS",
        "_SETTINGS_CAPTURE_LABELS",
        "_RESIZE_WINDOW_FAMILIES",
    }
    selected: list[ast.stmt] = []
    for node in module.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Name) and target.id in assignment_names
                for target in targets
            ):
                selected.append(node)
        elif (
            isinstance(node, ast.FunctionDef)
            and node.name in {
                "expected_capture_window_family",
                "expected_capture_state_profile",
            }
        ):
            selected.append(node)
    namespace: dict[str, object] = {"Any": object, "re": re}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(CAPTURE_PATH), "exec"),
        namespace,
    )
    return namespace


def test_capture_contract_covers_every_public_surface_group() -> None:
    groups = dict(_literal_assignment("CAPTURE_FACE_GROUPS"))

    assert _literal_assignment("CAPTURE_CONTRACT_VERSION") == 12

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
        "streak-reward-earned-next",
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
    assert groups["Release overhaul — resumable and resilient states"] == (
        "starter-placement",
        "starter-completion",
        "home-preview-loading",
        "home-preview-error",
        "home-preview-stale",
        "onboarding-persistence-error",
        "move-persistence-error",
        "collection-known-not-collected-overview",
    )
    labels = [label for group in groups.values() for label in group]
    assert len(labels) == 157
    assert len(labels) == len(set(labels))


def test_every_capture_fixture_has_one_exact_renderer_family() -> None:
    contract = _compiled_renderer_family_contract()
    groups = contract["CAPTURE_FACE_GROUPS"]
    resolver = contract["expected_capture_window_family"]
    assert isinstance(groups, tuple)
    assert callable(resolver)
    labels = [label for _group, group_labels in groups for label in group_labels]
    families = [resolver(label) for label in labels]

    assert all(families)
    assert Counter(families) == {
        "AnkiQt": 15,
        "GardenDashboard": 47,
        "GardenProgressDialog": 24,
        "GardenSettingsDialog": 17,
        "NurseryDialog": 16,
        "CustomizeGardenDialog": 8,
        "FertilizerDialog": 7,
        "StarterConfirmationDialog": 6,
        "PlantStoryDialog": 6,
        "FertilizerReplacementDialog": 6,
        "SpeciesOverviewDialog": 5,
    }


def test_every_capture_fixture_has_one_state_specific_profile() -> None:
    contract = _compiled_renderer_family_contract()
    groups = contract["CAPTURE_FACE_GROUPS"]
    resolver = contract["expected_capture_state_profile"]
    assert isinstance(groups, tuple)
    assert callable(resolver)
    labels = [label for _group, group_labels in groups for label in group_labels]
    profiles = [resolver(label) for label in labels]

    assert all(profile for profile in profiles)
    assert [profile["profile_id"] for profile in profiles] == labels
    assert len({profile["profile_id"] for profile in profiles}) == 157
    assert all(profile.get("kind") for profile in profiles)
    assert resolver("deck-browser-home")["fixture_state"] == (
        "starter-planted-not-nurtured"
    )
    assert resolver("active-overview-home-after-nurture")["fixture_state"] == (
        "nurtured-active"
    )
    assert resolver("home-preview-loading")["fixture_state"] == "preview-loading"
    assert resolver("home-preview-error")["surface"] == "overview"
    assert resolver("home-preview-stale")["fixture_state"] == "preview-stale"
    assert resolver("resize-dashboard-content-1359")["declared_client_size"] == [
        1383,
        900,
    ]
    assert resolver("resize-dashboard-content-1359")["layout_mode"] == "compact"
    assert resolver("resize-dashboard-content-1361")["layout_mode"] == "compact"
    assert resolver("resize-progress-minimum")["canonical_page"] == "overview"
    assert resolver("resize-collection-minimum")["canonical_page"] == "collection"


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
        "starter-placement",
        "starter-completion",
        "home-preview-loading",
        "home-preview-error",
        "home-preview-stale",
        "onboarding-persistence-error",
        "move-persistence-error",
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
    layout_modes = _literal_assignment("RESIZE_MATRIX_LAYOUT_MODES")
    families = {spec[1] for spec in specs}

    assert families == {
        "dashboard",
        "settings",
        "progress",
        "collection",
        "customize",
        "nursery",
        "story",
        "starter-confirmation",
        "fertilizer",
        "fertilizer-replacement",
        "species-overview",
    }
    assert all(spec[3] > 0 and spec[4] > 0 for spec in specs)
    assert sum("historical-edge-low-stability-probe" == spec[2] for spec in specs) == 13
    assert sum("historical-edge-high-stability-probe" == spec[2] for spec in specs) == 13
    assert set(layout_modes) == {spec[0] for spec in specs}
    assert all(layout_modes[spec[0]] in {"default", "display", "narrow", "compact", "wide"} for spec in specs)
    paired_ids = (
        ("resize-dashboard-content-699", "resize-dashboard-content-701"),
        ("resize-dashboard-content-819", "resize-dashboard-content-821"),
        ("resize-dashboard-content-899", "resize-dashboard-content-901"),
        ("resize-dashboard-content-999", "resize-dashboard-content-1001"),
        ("resize-dashboard-content-1359", "resize-dashboard-content-1361"),
        ("resize-settings-content-699", "resize-settings-content-701"),
        ("resize-settings-content-759", "resize-settings-content-761"),
        ("resize-progress-content-819", "resize-progress-content-821"),
        ("resize-customize-content-819", "resize-customize-content-821"),
        ("resize-nursery-content-759", "resize-nursery-content-761"),
        ("resize-story-content-539", "resize-story-content-541"),
        (
            "resize-starter-confirmation-content-399",
            "resize-starter-confirmation-content-401",
        ),
        (
            "resize-fertilizer-replacement-content-399",
            "resize-fertilizer-replacement-content-401",
        ),
    )
    assert all(layout_modes[low] == layout_modes[high] for low, high in paired_ids)


def test_capture_manifest_records_geometry_and_fails_unexplained_or_unsafe_drift() -> None:
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
        '"geometry_drift_accepted"',
        '"geometry_acceptance"',
        '"frame_overhead"',
        '"frame_size"',
        '"device_pixel_ratio"',
        '"layout_mode"',
        '"transition_path"',
        '"geometry_layout_warnings"',
    ):
        assert field in capture_now
    assert "exact_size_reached" in capture_now
    assert "Unexplained or unsafe geometry drift" in capture_now
    assert "geometry_acceptance.get(\"accepted\", False)" in capture_now
    assert "Geometry audit found" in capture_now
    assert "widget.resize(initial_width, initial_height)" in requested
    assert "widget.resize(target_width, target_height)" in requested
    assert '"declared_client_size": [declared_width, declared_height]' in requested
    assert '"requested_client_size": [declared_width, declared_height]' in requested
    assert "min(declared_width, screen_maximum_width" not in requested
    assert "min(declared_height, screen_maximum_height" not in requested
    assert "forbidden-horizontal-overflow" in geometry_audit
    assert "painted-frame-outside-root" in geometry_audit


def test_resize_geometry_accepts_only_explained_safe_drift() -> None:
    classify = _compiled_function("resize_geometry_acceptance", Any=object)
    common = {
        "label": "resize-dashboard-content-1359",
        "declared_size": [1383, 900],
        "minimum_size": [620, 520],
        "maximum_size": [16777215, 16777215],
        "constraint_limited": False,
    }

    explained = classify(
        **common,
        actual_size=[1383, 699],
        screen_limited=True,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    assert explained["accepted"] is True
    assert explained["breakpoint_width_within_one"] is True
    assert explained["safe_bounded_height"] is True

    unexplained = classify(
        **common,
        actual_size=[1383, 699],
        screen_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    assert unexplained["accepted"] is False
    assert unexplained["provenance_explains_drift"] is False

    crossed_breakpoint = classify(
        **common,
        actual_size=[1380, 699],
        screen_limited=True,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    assert crossed_breakpoint["accepted"] is False
    assert crossed_breakpoint["breakpoint_width_within_one"] is False

    unsafe_height = classify(
        **common,
        actual_size=[1383, 400],
        screen_limited=True,
        native_normalized=True,
        normalization_reason=(
            "extends-beyond-available-screen,native-frame-or-scale"
        ),
    )
    assert unsafe_height["accepted"] is False
    assert unsafe_height["safe_bounded_height"] is False


def test_capture_timeouts_and_step_exceptions_fail_closed() -> None:
    next_step = _method_source("_UiFaceCaptureRunner", "_next_step")
    wait = _method_source("_UiFaceCaptureRunner", "_wait_for")
    collection = _method_source("_UiFaceCaptureRunner", "_wait_for_collection")
    dashboard = _method_source("_UiFaceCaptureRunner", "_wait_for_dashboard")
    seed = _method_source("_UiFaceCaptureRunner", "_prepare_capture_state")

    assert "Capture step" in next_step
    assert "type(exc).__name__" in next_step
    assert "on_ready()" not in wait.split("if tries <= 0:", 1)[1]
    assert '"Timed out waiting for the requested UI surface"' in wait
    assert '"Anki collection did not become ready before capture"' in collection
    assert '"Garden Dashboard did not become visible before capture"' in dashboard
    assert '"release-fixture-seed"' in seed
    assert "self._finish()" in seed


def test_capture_readiness_callbacks_are_one_shot_and_fail_closed() -> None:
    wrapper = _method_source("_UiFaceCaptureRunner", "_one_shot_async_callback")
    collection = _method_source("_UiFaceCaptureRunner", "_wait_for_collection")
    dashboard = _method_source("_UiFaceCaptureRunner", "_wait_for_dashboard")
    wait = _method_source("_UiFaceCaptureRunner", "_wait_for")
    home = _method_source("_UiFaceCaptureRunner", "_wait_for_home_surface")

    assert "if called:" in wrapper
    assert "called = True" in wrapper
    assert "Capture readiness callback raised" in wrapper
    assert "_one_shot_async_callback" in collection
    assert "_one_shot_async_callback" in dashboard
    assert "_one_shot_async_callback" in wait
    assert "resolved_once = self._one_shot_async_callback" in home


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
    assert 'fixture_state = "starter-not-selected"' in source
    assert 'fixture_state = "starter-planted-not-nurtured"' in source
    assert 'fixture_state = "nurtured-active"' in source
    assert "root.dataset.activeSlot" in source
    assert "capture_label: str" in source
    assert "visibleRoots[visibleRoots.length - 1]" in source
    assert "command.endsWith(':open')" in source
    assert 'if tries in {75, 50, 25}:' in source
    assert 'invalidate(f"capture readiness retry for {capture_label}")' in source
    assert '"last DOM observation"' not in source
    assert "last DOM observation" in source
    assert "Home fixture identity could not be verified without WebEngine" in source


def test_home_capture_call_sites_supply_the_exact_manifest_label() -> None:
    source = CAPTURE_PATH.read_text("utf-8")

    for surface, label in (
        ("deckBrowser", "starter-deck-browser-home"),
        ("overview", "starter-overview-home"),
        ("deckBrowser", "deck-browser-home"),
        ("overview", "overview-home"),
    ):
        assert f'self._wait_for_home_surface(\n                    "{surface}",\n                    "{label}"' in source or (
            f'self._wait_for_home_surface(\n                "{surface}",\n                "{label}"' in source
        )


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
    prepare = _method_source("_UiFaceCaptureRunner", "_prepare_capture_state")
    planted = _method_source("_UiFaceCaptureRunner", "_capture_selected_card_after")
    nurtured = _method_source("_UiFaceCaptureRunner", "_capture_nurture_after")

    assert "enter_starter_nursery" in seed
    assert "select_starter_species" in seed
    assert "confirm_starter_species" in seed
    assert "place_starter(0)" in seed
    assert "active_plant_id =" not in seed
    assert "set_active_plant" not in seed
    assert 'notify("Capture starter fixture committed")' in prepare
    assert "onboarding_state_display" in planted
    assert "OnboardingState.STARTER_PLANTED_NOT_NURTURED" in planted
    assert "active_plant_id =" not in planted
    assert 'getattr(dashboard, "_nurture_plant", None)' in nurtured
    assert '== "first_nurture"' in nurtured
    assert '== "nurture:first"' in nurtured
    assert "finish_onboarding()" in nurtured


def test_capture_p0_fixtures_are_coherent_and_transaction_bound() -> None:
    achievement = _method_source("_UiFaceCaptureRunner", "_capture_achievement_completed")
    missed_streak = _method_source("_UiFaceCaptureRunner", "_capture_streak_missed_day")
    streak_rewards = _method_source("_UiFaceCaptureRunner", "_capture_streak_reward_states")
    collection = _method_source("_UiFaceCaptureRunner", "_capture_collection_several")
    known_species = _method_source(
        "_UiFaceCaptureRunner", "_capture_known_uncollected_species_overview"
    )
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
    assert '"streak-reward-earned-next"' in streak_rewards
    assert '"manual_claim_action_supported": False' in streak_rewards

    assert "][:4]" in collection.replace(" ", "")
    assert "discovered_count == 4" in collection
    assert 'restore_callback=restore' in collection

    assert 'label = "collection-known-not-collected-overview"' in known_species
    assert 'dialog.property("collectionState")' in known_species
    assert '"not-collected"' in known_species
    assert '"Rare stage undiscovered"' in known_species
    assert 'close_callback=lambda: (self._close_widget(dialog), restore())' in known_species

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
    assert "WATERING_CAPTURE_GROWTH_POINTS" in select_slot
    assert "state.garden_name = WATERING_CAPTURE_GARDEN_NAME" in select_slot
    assert "item.slot_index = index if index < 6 else None" in select_slot
    assert 'f"watering-can-garden-plot-{slot + 1}"' in garden
    assert 'surface == "deckBrowser"' in home
    assert 'self._switch_surface(surface)' in home
    assert "data-marker-orientation" in home_audit
    assert "resolved_side" in home_audit
    assert "resolved_side" in qt_audit
    assert "data-marker-pulse" in home_audit
    assert "data-marker-target-ground" in home_audit
    assert "data-marker-planter-rect" in home_audit
    assert "marker was too far from the nurtured plant" in home_audit
    assert "NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO" in home_audit
    assert "pulse_rect.intersects(blocker)" in qt_audit
    assert "nurtured_marker_protected_regions" in qt_audit
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
    assert "fixture_validations_complete" in finish
    assert "complete and manifest_write_succeeded" in finish
    assert "app.exit(exit_code)" in finish


def test_capture_manifest_reports_per_face_and_aggregate_display_provenance(
    tmp_path: Path,
) -> None:
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    finish_source = _method_source("_UiFaceCaptureRunner", "_finish")
    finish = _compiled_method(
        "_UiFaceCaptureRunner",
        "_finish",
        QApplication=SimpleNamespace(instance=lambda: None),
        CAPTURE_CONTRACT_VERSION=9,
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
    assert "allow_screen_capture=foreground_confirmed" in capture_home
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
    assert 'annotation["home_foreground_confirmed"] = foreground_confirmed' in capture_now
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
    assert '"app-owned-home-surface-not-ready"' in capture_home
    assert '"semantic-window-not-ready"' in capture_home
    assert 'if self._capture_display == "secondary"' in capture_home
    assert "self._capture_force_primary = True" in capture_home
    assert "self._move_to_capture_display(widget)" in capture_home


def test_home_capture_uses_only_the_app_owned_qt_surface_without_foreground() -> None:
    class Pixmap:
        def isNull(self) -> bool:
            return False

    class Widget:
        def grab(self) -> Pixmap:
            return Pixmap()

        def width(self) -> int:
            return 667

        def height(self) -> int:
            return 570

    warnings: list[tuple[object, ...]] = []
    capture_home = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_home_pixmap",
        QApplication=SimpleNamespace(instance=lambda: None),
        QGuiApplication=SimpleNamespace(
            primaryScreen=lambda: (_ for _ in ()).throw(
                AssertionError("screen capture must not run without foreground")
            ),
        ),
        logger=SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            warning=lambda *args: warnings.append(args),
        ),
        mw=SimpleNamespace(web=None),
        time=SimpleNamespace(sleep=lambda _seconds: None),
    )
    runner = SimpleNamespace(
        _activate_current_process_window=lambda _widget: False,
        _capture_display="primary",
        _capture_force_primary=True,
        _home_pixmap_metrics=lambda *_args, **_kwargs: {
            "generic_content_passed": True,
            "semantic_identity_passed": True,
            "passed": True,
            "brand_sample_ratio": 0.01,
            "dark_shell_sample_ratio": 0.1,
        },
    )
    pixmap, method, foreground = capture_home(runner, Widget())
    assert isinstance(pixmap, Pixmap)
    assert method == "qt-widget"
    assert foreground is False
    assert "limiting capture to the app-owned Qt surface" in str(warnings[0][0])


def test_home_capture_waits_for_late_webengine_semantic_paint() -> None:
    class Pixmap:
        def __init__(self, attempt: int) -> None:
            self.attempt = attempt

        def isNull(self) -> bool:
            return False

        def toImage(self) -> "Pixmap":
            return self

        def width(self) -> int:
            return 1001

        def height(self) -> int:
            return 855

    class Widget:
        def __init__(self) -> None:
            self.attempts = 0
            self.updates = 0

        def grab(self) -> Pixmap:
            self.attempts += 1
            return Pixmap(self.attempts)

        def update(self) -> None:
            self.updates += 1

        def width(self) -> int:
            return 667

        def height(self) -> int:
            return 570

    process_events: list[bool] = []
    capture_home = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_home_pixmap",
        QApplication=SimpleNamespace(
            instance=lambda: SimpleNamespace(
                processEvents=lambda: process_events.append(True),
            ),
        ),
        QGuiApplication=SimpleNamespace(primaryScreen=lambda: None),
        logger=SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
        ),
        mw=SimpleNamespace(web=None),
        time=SimpleNamespace(sleep=lambda _seconds: None),
    )
    runner = SimpleNamespace(
        _activate_current_process_window=lambda _widget: False,
        _capture_display="primary",
        _capture_force_primary=True,
        _home_capture_ready_attempts=6,
        _home_pixmap_metrics=lambda candidate, **_expected: {
            "generic_content_passed": candidate.attempt >= 5,
            "semantic_identity_passed": candidate.attempt >= 5,
            "passed": candidate.attempt >= 5,
            "brand_sample_ratio": 0.01 if candidate.attempt >= 5 else 0.0,
            "dark_shell_sample_ratio": 0.1 if candidate.attempt >= 5 else 0.0,
        },
    )
    widget = Widget()

    pixmap, method, foreground = capture_home(runner, widget)

    assert pixmap.attempt == 5
    assert method == "qt-widget"
    assert foreground is False
    assert widget.attempts == 5
    assert widget.updates == 4
    assert len(process_events) == 8


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

    pixmap, method, foreground = capture_home(runner, widget)
    assert method == "foreground-screen-region"
    assert pixmap.name == "garden"
    assert foreground is True
    assert runner._capture_force_primary is True
    assert widget.capture_display == "primary"
    assert process_events == [True, True]
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


def test_settings_fixtures_reset_scroll_and_reveal_reduced_motion() -> None:
    tab = _method_source("_UiFaceCaptureRunner", "_set_settings_tab")
    custom = _method_source("_UiFaceCaptureRunner", "_capture_custom_settings")
    reduced = _method_source(
        "_UiFaceCaptureRunner",
        "_show_reduced_motion_fixture",
    )
    capture = _method_source("_UiFaceCaptureRunner", "_capture_reduced_motion")

    assert "scroll.verticalScrollBar().setValue(0)" in tab
    assert "scroll.horizontalScrollBar().setValue(0)" in tab
    assert "controls_scroll" in reduced
    assert "ensureWidgetVisible(control" in reduced
    assert 'str(scroll.accessibleName() or "") == "Display settings"' in reduced
    assert "self._show_reduced_motion_fixture" in capture
    assert 'config_update({"reduced_motion": True})' in capture
    assert "restore_callback=restore_reduced_motion" in capture
    assert "restore_callback: Callable[[], None] | None = None" in custom
    assert "close_callback=cleanup_once" in custom
    assert "on_error=cleanup_once" in custom
    assert "cleanup_complete" in custom


def test_custom_settings_cleanup_runs_once_on_success_timeout_and_error() -> None:
    capture_custom = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_custom_settings",
    )

    def exercise(mode: str) -> tuple[list[str], list[dict[str, str]]]:
        events: list[str] = []
        dialog = SimpleNamespace()
        runner = SimpleNamespace(
            _failures=[],
            app=SimpleNamespace(
                dashboard=SimpleNamespace(
                    _open_settings=lambda: events.append("open"),
                ),
            ),
        )
        runner._find_settings_dialog = lambda: dialog
        runner._set_settings_tab = (
            lambda found, tab: events.append(f"tab:{tab}")
        )
        runner._close_settings_capture = (
            lambda found: events.append("close")
        )

        def capture_and_advance(
            _label: str,
            _widget: object,
            **kwargs: object,
        ) -> None:
            events.append("capture")
            callback = kwargs.get("close_callback")
            assert callable(callback)
            callback()
            callback()

        def wait_for(
            _predicate: object,
            on_ready: object,
            **kwargs: object,
        ) -> None:
            on_error = kwargs.get("on_error")
            assert callable(on_error)
            if mode == "timeout":
                on_error()
                on_error()
                return
            assert callable(on_ready)
            try:
                on_ready()
            except RuntimeError:
                on_error()
                on_error()

        def with_dashboard(on_ready: object, **kwargs: object) -> None:
            on_error = kwargs.get("on_error")
            assert callable(on_error)
            if mode == "dashboard-error":
                on_error()
                on_error()
                return
            assert callable(on_ready)
            on_ready()

        runner._capture_and_advance = capture_and_advance
        runner._wait_for = wait_for
        runner._with_dashboard = with_dashboard

        def prepare(_dialog: object) -> None:
            events.append("prepare")
            if mode == "prepare-error":
                raise RuntimeError("fixture preparation failed")

        def restore() -> None:
            events.append("restore")
            if mode == "restore-error":
                raise RuntimeError("fixture restoration failed")

        capture_custom(
            runner,
            "fixture",
            0,
            prepare,
            restore_callback=restore,
        )
        return events, runner._failures

    success, success_failures = exercise("success")
    timeout, timeout_failures = exercise("timeout")
    prepare_error, prepare_failures = exercise("prepare-error")
    dashboard_error, dashboard_failures = exercise("dashboard-error")
    restore_error, restore_failures = exercise("restore-error")

    assert success == ["open", "tab:0", "prepare", "capture", "close", "restore"]
    assert timeout == ["open", "close", "restore"]
    assert prepare_error == ["open", "tab:0", "prepare", "close", "restore"]
    assert dashboard_error == ["close", "restore"]
    assert restore_error == ["open", "tab:0", "prepare", "capture", "close", "restore"]
    assert not success_failures
    assert not timeout_failures
    assert not prepare_failures
    assert not dashboard_failures
    assert [failure["reason"] for failure in restore_failures] == [
        "Settings fixture state restoration failed: RuntimeError"
    ]


def test_keyboard_focus_fixture_clears_its_focus_before_advancing() -> None:
    events: list[str] = []

    class Button:
        focused = False

        def setFocus(self, _reason: object) -> None:
            self.focused = True
            events.append("focus")

        def clearFocus(self) -> None:
            self.focused = False
            events.append("clear")

        def hasFocus(self) -> bool:
            return bool(self.focused)

    button = Button()
    application = SimpleNamespace(processEvents=lambda: events.append("events"))
    qapplication = SimpleNamespace(
        instance=lambda: application,
        focusWidget=lambda: button if button.focused else None,
    )
    capture_focus = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_keyboard_focus",
        QApplication=qapplication,
        Qt=SimpleNamespace(
            FocusReason=SimpleNamespace(TabFocusReason="tab"),
        ),
    )
    dashboard = SimpleNamespace(progress_btn=button)
    runner = SimpleNamespace(
        _failures=[],
        app=SimpleNamespace(dashboard=dashboard),
    )

    def capture_and_advance(
        label: str,
        widget: object,
        **kwargs: object,
    ) -> None:
        assert label == "keyboard-focus-state"
        assert widget is dashboard
        assert button.hasFocus() is True
        events.append("capture")
        callback = kwargs.get("close_callback")
        assert callable(callback)
        callback()
        callback()

    runner._capture_and_advance = capture_and_advance
    runner._with_dashboard = lambda ready, **_kwargs: ready()

    capture_focus(runner)

    assert events == ["focus", "events", "capture", "clear", "events"]
    assert button.hasFocus() is False
    assert runner._failures == []


def test_accessibility_fixture_postconditions_prove_isolation() -> None:
    postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    keyboard = _method_source("_UiFaceCaptureRunner", "_capture_keyboard_focus")

    assert 'state_name == "keyboard-focus-state"' in postcondition
    assert '"reduced_motion_config_enabled"' in postcondition
    assert '"reduced_motion_baseline_restored"' in postcondition
    assert '"keyboard_focus_owner"' in postcondition
    assert '"keyboard_focus_fixture_cleared"' in postcondition
    assert 'state_name.startswith("resize-dashboard-")' in postcondition
    assert "focus_owner is button" in postcondition
    assert "focus_owner is not progress_button" in postcondition
    assert "close_callback=clear_focus_once" in keyboard
    assert "on_error=clear_focus_once" in keyboard
    assert "cleanup_complete" in keyboard
    assert '"Keyboard-focus fixture cleanup failed: "' in keyboard
    assert "self._failures.append" in keyboard


def test_capture_records_surface_timings_and_repeated_dialog_retention() -> None:
    wait = _method_source("_UiFaceCaptureRunner", "_wait_for")
    probe = _method_source("_UiFaceCaptureRunner", "_run_dialog_memory_probe")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")

    assert "started_monotonic" in wait
    assert 'f"surface_ready:{failure_label}"' in wait
    assert "cycles: int = 12" in probe
    assert "app.allWidgets()" in probe
    assert 'getattr(dashboard, "_open_nursery", None)' in probe
    assert 'observation["visible"]' in probe
    assert 'observation["closed"]' in probe
    assert "visible_cycles == 12" in probe
    assert "closed_cycles == 12" in probe
    assert "QCoreApplication.sendPostedEvents" in probe
    assert "QEvent.Type.DeferredDelete" in probe
    assert 'watched_delta["NurseryDialog"] == 0' in probe
    assert "exactly zero retained NurseryDialog widgets" in probe
    assert '"current_rss_available": False' in probe
    assert '"watched_class_delta"' in probe
    assert '"dialog_memory_probe"' in finish
    assert "memory_probe_complete" in finish
    assert "and memory_probe_complete" in finish


def test_fixture_postconditions_are_required_for_every_saved_face() -> None:
    capture = _method_source("_UiFaceCaptureRunner", "_capture_now")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")
    postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )

    assert "expected_capture_state_profile(label)" in postcondition
    assert '"ordered_fixture_label"' in postcondition
    assert '"dom_fixture_ready"' in postcondition
    assert '"progress_page"' in postcondition
    assert '"nursery_tab"' in postcondition
    assert '"settings_tab"' in postcondition
    assert '"declared_client_size"' in postcondition
    assert '"layout_mode"' in postcondition
    assert '"geometry_acceptance"' in postcondition
    assert '"canonical_progress_page"' in postcondition
    assert "self._capture_fixture_postcondition(" in capture
    assert '"postcondition": postcondition' in capture
    assert "postcondition.get(\"passed\", False)" in capture
    assert 'dict(record.get("fixture_validation", {})).get("passed", False)' in finish


def test_delayed_capture_keeps_reserved_identity_after_global_provenance_advances() -> None:
    home_widget = object()
    timer_callbacks: list[object] = []
    qtimer = SimpleNamespace(
        singleShot=lambda _delay, callback: timer_callbacks.append(callback),
    )
    reserve = _compiled_method(
        "_UiFaceCaptureRunner",
        "_reserve_capture_identity",
    )
    schedule = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_and_advance",
        QTimer=qtimer,
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
        mw=home_widget,
        time=SimpleNamespace(perf_counter=lambda: 123.0),
    )

    def exercise(widget: object) -> tuple[object, ...]:
        timer_callbacks.clear()
        saved: list[tuple[object, ...]] = []
        runner = SimpleNamespace(
            _active_fixture_expected_label="deck-browser-home",
            _active_fixture_source="ordered-step-001:_capture_deck_browser",
            _capture_index=7,
            _capture_requested_monotonic={},
        )
        runner._reserve_capture_identity = (
            lambda label: reserve(runner, label)
        )

        def advance_global_provenance() -> None:
            runner._active_fixture_expected_label = "overview-home"
            runner._active_fixture_source = "ordered-step-002:_capture_overview"

        def activate(_widget: object) -> bool:
            # Home activation pumps Qt events in production. Simulate a
            # provenance advance before the delayed screenshot callback.
            advance_global_provenance()
            return True

        runner._activate_current_process_window = activate
        runner._next_after = lambda _delay: advance_global_provenance()
        runner._capture_now = lambda label, captured_widget, **kwargs: saved.append(
            (label, captured_widget, kwargs["capture_identity"])
        )

        schedule(
            runner,
            "deck-browser-home",
            widget,
            capture_delay_ms=20,
            next_ms=80,
        )

        assert runner._capture_index == 8
        assert runner._active_fixture_source == "ordered-step-002:_capture_overview"
        assert len(timer_callbacks) == 1
        callback = timer_callbacks.pop()
        assert callable(callback)
        callback()
        assert len(saved) == 1
        return saved[0]

    generic = exercise(object())
    home = exercise(home_widget)
    expected_identity = (
        7,
        "deck-browser-home",
        "ordered-step-001:_capture_deck_browser",
        "deck-browser-home",
    )

    assert generic[0] == home[0] == "deck-browser-home"
    assert generic[2] == home[2] == expected_identity


def test_capture_identity_mismatches_fail_before_reading_qt_or_saving() -> None:
    capture_now = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_now",
        time=SimpleNamespace(perf_counter=lambda: 10.0),
    )
    runner = SimpleNamespace(_failures=[])

    capture_now(runner, "deck-browser-home", capture_identity=None)
    capture_now(
        runner,
        "deck-browser-home",
        capture_identity=(
            7,
            "overview-home",
            "ordered-step-001:_capture_deck_browser",
            "deck-browser-home",
        ),
    )
    capture_now(
        runner,
        "deck-browser-home",
        capture_identity=(
            0,
            "deck-browser-home",
            "stale-global-source",
            "overview-home",
        ),
    )

    assert [failure["reason"] for failure in runner._failures] == [
        "Scheduled capture identity snapshot was missing or malformed",
        (
            "Scheduled capture identity did not match the requested fixture: "
            "scheduled_label"
        ),
        (
            "Scheduled capture identity did not match the requested fixture: "
            "capture_id, fixture_source, expected_fixture_label"
        ),
    ]


def test_saved_capture_provenance_never_reads_mutable_next_step_globals() -> None:
    reserve = _method_source("_UiFaceCaptureRunner", "_reserve_capture_identity")
    schedule = _method_source("_UiFaceCaptureRunner", "_capture_and_advance")
    capture = _method_source("_UiFaceCaptureRunner", "_capture_now")
    postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )

    assert "self._capture_index = capture_id + 1" in reserve
    assert 'getattr(self, "_active_fixture_source", "")' in reserve
    assert 'getattr(self, "_active_fixture_expected_label", "")' in reserve
    assert schedule.index("self._reserve_capture_identity(label)") < schedule.index(
        "self._activate_current_process_window(widget)"
    )
    assert "lambda identity=capture_identity" in schedule
    assert "capture_identity=identity" in schedule
    assert '"fixture_source": fixture_source' in capture
    assert "expected_fixture_label=expected_fixture_label" in capture
    assert "self._active_fixture_source" not in capture
    assert "self._active_fixture_expected_label" not in capture
    assert "self._capture_index" not in capture
    assert "expected_fixture_label: str" in postcondition
    assert "self._active_fixture_expected_label" not in postcondition


def test_collection_and_clear_recall_fixtures_restore_on_failure_and_close() -> None:
    collection_filter = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_collection_filter",
    )
    collection_several = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_collection_several",
    )
    clear_recall = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_clear_recall_conditions",
    )
    progress_page = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_progress_page_after",
    )

    assert "def restore_fixture()" in collection_filter
    assert "on_error=restore_fixture" in collection_filter
    assert "finally:\n                        restore_fixture()" in collection_filter
    assert "def restore()" in collection_several
    assert "except Exception:\n            restore()" in collection_several
    assert "self._refresh_capture_dashboard()" in collection_several
    assert "dashboard._collection_filter = original_filter" in collection_several
    assert collection_several.index("original_plants =") < collection_several.index(
        "if not self._ensure_development_stress_state():"
    )

    assert "achievement_snapshots" in clear_recall
    assert "for item in state.achievements.values():" in clear_recall
    assert "item.unlocked = False" in clear_recall
    assert '"achievement_state_isolated": True' in clear_recall
    assert "restore_callback=restore" in clear_recall
    assert "finally:\n                    if restore_callback is not None:" in progress_page
    assert "on_error=restore_callback" in progress_page


def test_capture_scope_matches_the_pixel_acquisition_method() -> None:
    capture = _method_source("_UiFaceCaptureRunner", "_capture_now")

    assert 'if capture_method in {' in capture
    assert '"foreground-screen-region"' in capture
    assert '"native-window"' in capture
    assert '"app-owned-qt-surface"' in capture
    scope_branch = capture.split('annotation["home_capture_scope"] = (', 1)[1].split(
        ")\n", 1
    )[0]
    assert "foreground_confirmed" not in scope_branch


def test_duplicate_minimum_dashboard_geometry_has_two_explicit_audit_purposes() -> None:
    representative = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_display_scaling_200_representative",
    )
    requested = _method_source("_UiFaceCaptureRunner", "_capture_requested_size")

    assert '"same_logical_geometry_as": "resize-dashboard-minimum"' in representative
    assert '"distinct_audit_purpose": "200 percent scaling representative"' in representative
    assert 'if label == "resize-dashboard-minimum":' in requested
    assert '"same_logical_geometry_as": "display-scaling-200-qt-representative"' in requested
    assert '"distinct_audit_purpose": "responsive minimum resize transition"' in requested


def test_progress_resize_faces_route_to_their_declared_page() -> None:
    resize = _method_source("_UiFaceCaptureRunner", "_capture_resize_matrix_face")
    route_position = resize.index("navigation.set_current(target_page)")
    refresh_position = resize.index("refresh()", route_position)
    capture_position = resize.index("capture_widget(progress, close=True)")

    assert route_position < refresh_position < capture_position
    assert 'target_page = "collection" if family == "collection" else "overview"' in resize
    assert "target_page not in keys" in resize
    assert "Garden Progress {target_page} was unavailable" in resize


def test_watering_faces_clear_unrelated_stress_state_and_audit_the_name() -> None:
    setup = _method_source("_UiFaceCaptureRunner", "_set_nurtured_capture_slot")
    postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )

    assert "CURRENT_CATALOG_SPECIES_ORDER" in setup
    assert "state.garden_name = WATERING_CAPTURE_GARDEN_NAME" in setup
    assert "state.currency_balance = WATERING_CAPTURE_CURRENCY_BALANCE" in setup
    assert "item.growth_points = WATERING_CAPTURE_GROWTH_POINTS" in setup
    assert "item.fertilizer = None" in setup
    assert 'if label.startswith("watering-can-"):' in postcondition
    assert '"canonical_watering_garden_name"' in postcondition
    assert '"canonical_watering_currency_balance"' in postcondition
    assert '"canonical_watering_plant_names"' in postcondition
    assert '"canonical_watering_growth"' in postcondition


def test_development_stress_permutations_normalize_to_one_source_order() -> None:
    normalize = _compiled_function("canonicalize_development_stress_plants")
    species_order = tuple(_literal_assignment("DEVELOPMENT_STRESS_SPECIES_ORDER"))

    def plants_for(permutation: tuple[str, ...]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                plant_id=f"dev_{species}",
                species=species,
                name=f"randomized-{index}",
                name_customized=True,
            )
            for index, species in enumerate(permutation)
        ]

    first_input = plants_for(species_order[3:] + species_order[:3])
    second_input = plants_for(tuple(reversed(species_order)))
    first_instances = {id(plant) for plant in first_input}
    second_instances = {id(plant) for plant in second_input}
    generated_name = lambda species: (
        f"{species.replace('_', ' ').title()} Plant"[:40]
    )

    first = normalize(first_input, species_order, generated_name)
    second = normalize(second_input, species_order, generated_name)
    expected_names = [generated_name(species) for species in species_order]

    assert [plant.species for plant in first] == list(species_order)
    assert [plant.species for plant in second] == list(species_order)
    assert [plant.plant_id for plant in first] == [
        f"dev_{species}" for species in species_order
    ]
    assert [plant.plant_id for plant in second] == [
        f"dev_{species}" for species in species_order
    ]
    assert [plant.name for plant in first] == expected_names
    assert [plant.name for plant in second] == expected_names
    assert not any(plant.name_customized for plant in [*first, *second])
    assert {id(plant) for plant in first} == first_instances
    assert {id(plant) for plant in second} == second_instances
    assert len(first) == len(second) == 10


def test_development_stress_state_binds_catalog_assets_and_live_order_fact() -> None:
    setup = _method_source(
        "_UiFaceCaptureRunner",
        "_ensure_development_stress_state",
    )
    postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )

    assert "CURRENT_CATALOG_SPECIES_ORDER" in setup
    assert "self.app.engine.release_ready_species()" in setup
    assert "DEVELOPMENT_STRESS_SPECIES_ORDER" in setup
    assert "canonicalize_development_stress_plants(" in setup
    assert "self.app.engine._generated_name" in setup
    assert "state.plants = plants" in setup
    assert "len(plants) != len(declared_order)" in setup
    assert "len(set(canonical_ids)) != len(declared_order)" in setup
    assert "GROWTH_THRESHOLDS[index % len(GROWTH_THRESHOLDS)]" in setup
    assert "state.active_plant_id = plants[0].plant_id" in setup
    assert '"canonical_development_species_order"' in postcondition
    assert '"canonical_development_plant_ids"' in postcondition
    assert '"canonical_development_generated_names"' in postcondition
    assert 'state_name.startswith("resize-")' in postcondition


def test_text_layout_audit_only_exempts_intentionally_scrolled_out_content() -> None:
    audit = _method_source("_UiFaceCaptureRunner", "_find_text_layout_warnings")
    qt_exemption = _method_source(
        "_UiFaceCaptureRunner",
        "_text_candidate_is_intentionally_scrolled_out",
    )

    assert "int(candidate.width()) <= 0" in audit
    assert "int(candidate.height()) <= 0" in audit
    assert "visible_region = candidate.visibleRegion()" in audit
    assert "visible_region.isEmpty()" in audit
    assert "_text_candidate_is_intentionally_scrolled_out" in audit
    assert '"kind": "empty-visible-region"' in audit
    assert audit.index("_text_candidate_is_intentionally_scrolled_out") < audit.index(
        '"kind": "empty-visible-region"'
    )
    assert "isinstance(ancestor, QAbstractScrollArea)" in qt_exemption
    assert "horizontal.maximum()" in qt_exemption
    assert "vertical.maximum()" in qt_exemption
    assert "intentional_scroll_viewport_exemption(" in qt_exemption
    assert "ink_width = int(metrics.tightBoundingRect(text).width())" in audit
    assert "horizontal_clip = ink_width > available_width + 2" in audit


def test_scroll_viewport_exemption_rejects_covered_or_forbidden_axis_controls() -> None:
    exempt = _compiled_function("intentional_scroll_viewport_exemption")
    viewport = [0, 0, 300, 200]

    assert exempt(
        candidate_rect=[10, 240, 120, 30],
        viewport_rect=viewport,
        horizontal_scrollable=False,
        vertical_scrollable=True,
    ) is True
    assert exempt(
        candidate_rect=[10, 240, 120, 30],
        viewport_rect=viewport,
        horizontal_scrollable=False,
        vertical_scrollable=False,
    ) is False
    # A control geometrically inside the viewport but covered by another
    # widget is never mistaken for intentionally scrolled-out content.
    assert exempt(
        candidate_rect=[10, 40, 120, 30],
        viewport_rect=viewport,
        horizontal_scrollable=True,
        vertical_scrollable=True,
    ) is False
    # Being out on an unreachable horizontal axis remains a failure even when
    # the vertical axis is intentionally scrollable.
    assert exempt(
        candidate_rect=[340, 240, 120, 30],
        viewport_rect=viewport,
        horizontal_scrollable=False,
        vertical_scrollable=True,
    ) is False
    assert exempt(
        candidate_rect=[340, 40, 120, 30],
        viewport_rect=viewport,
        horizontal_scrollable=True,
        vertical_scrollable=False,
    ) is True


def test_manifest_write_failure_forces_a_nonzero_exit(tmp_path: Path) -> None:
    exits: list[int] = []
    app = SimpleNamespace(exit=lambda code: exits.append(int(code)))
    finish = _compiled_method(
        "_UiFaceCaptureRunner",
        "_finish",
        QApplication=SimpleNamespace(instance=lambda: app),
        CAPTURE_CONTRACT_VERSION=9,
        QTimer=SimpleNamespace(singleShot=lambda _delay, callback: callback()),
        datetime=datetime,
        logger=SimpleNamespace(error=lambda *_args, **_kwargs: None),
        os=SimpleNamespace(environ={}),
    )
    invalid_session_dir = tmp_path / "not-a-directory"
    invalid_session_dir.write_text("occupied", encoding="utf-8")
    record = {
        "capture_id": 1,
        "label": "face-1",
        "capture_display": "primary",
        "fixture_validation": {"passed": True},
    }
    runner = SimpleNamespace(
        _finished=False,
        _capture_display="primary",
        _capture_face_groups=(("Test", ("face-1",)),),
        _capture_face_labels=("face-1",),
        _capture_profile="test",
        _capture_records=[record],
        _close_dashboard=lambda: None,
        _close_top_level_dialogs=lambda: None,
        _dialog_memory_probe={"status": "not-run"},
        _failures=[],
        _performance_samples={},
        _requested_scale_factor="1.5",
        _screenshots=["face-1.png"],
        _text_layout_warnings=[],
        session_dir=invalid_session_dir,
    )

    finish(runner)

    assert exits == [1]
