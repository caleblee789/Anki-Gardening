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
        "PURCHASE_CONFIRMATION_RESIZE_SPECS",
        "GROWTH_CHARGE_RESIZE_SPECS",
        "RESIZE_MATRIX_LAYOUT_MODES",
        "_HOME_CAPTURE_LABELS",
        "_DASHBOARD_CAPTURE_LABELS",
        "_PROGRESS_CAPTURE_LABELS",
        "_REVIEWER_CAPTURE_LABELS",
        "_GROWTH_CHARGE_CAPTURE_LABELS",
        "_NURSERY_CAPTURE_LABELS",
        "_SETTINGS_CAPTURE_LABELS",
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

    assert _literal_assignment("CAPTURE_CONTRACT_VERSION") == 19

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
            "progress-overview-redirect-growth",
            "progress-achievements",
            "progress-collection",
            "collection-species-overview",
        )
    assert groups["Collection loadout details"] == (
        "collection-loadout-detail",
        "collection-preview-active",
        "collection-preview-restored",
    )
    assert groups["Nursery"] == (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        )
    assert groups["Settings"] == (
            "settings-home-preview-disabled",
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
        "clear-recall-canonical-projection",
        "streak-at-risk",
        "streak-missed-day",
        "streak-achievement-earned-next",
    )
    assert groups["Release stress — Nursery"] == (
        "nursery-item-owned",
        "nursery-item-locked",
        "nursery-purchase-success",
        "nursery-final-row-above-footer",
        "missing-artwork-graphical-fallback",
    )
    assert groups["Release stress — Settings and reviewer rewards"] == (
        "settings-unsaved-changes",
        "settings-validation-error",
        "diagnostics-expanded",
        "production-build-controls-absent",
        "reviewer-find-common-reduced-motion",
        "reviewer-find-environment",
        "reviewer-find-stacked-sync",
    )
    assert groups["Accessibility"] == (
        "reduced-motion-enabled",
        "keyboard-focus-state",
    )
    assert "Responsive resize matrix" not in groups
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
    assert groups["Release overhaul — purchase confirmations and outcomes"] == (
        "purchase-confirmation-species",
        "purchase-confirmation-growth-charge",
        "purchase-confirmation-environment",
        "purchase-confirmation-fertilizer-application",
        "purchase-confirmation-fertilizer-extension",
        "purchase-confirmation-garden-bed",
        "purchase-confirmation-loading-disabled",
        "purchase-error-insufficient-coins",
        "purchase-error-persistence-failure",
        "purchase-error-item-unavailable",
        "purchase-error-already-owned",
        "purchase-error-invalid-target",
        "purchase-error-stale-price",
        "purchase-error-stale-balance",
        "purchase-success-inventory-collection",
        "purchase-success-fertilizer-applied",
        "purchase-success-garden-bed-unlocked",
        "nursery-empty-state",
        "collection-environment-mechanics",
    )
    assert groups["Collection consolidation — transactional states"] == (
        "collection-loadout-persistence-error",
        "collection-origin-plant-placement",
    )
    assert groups["Growth overhaul — Charge confirmation states"] == (
        "growth-charge-use-ready",
        "growth-charge-empty-inventory",
        "growth-charge-loading-disabled",
        "growth-charge-stale-inventory",
        "growth-charge-invalid-target",
        "growth-charge-persistence-failure",
        "growth-charge-success-stage-reward",
    )
    labels = [label for group in groups.values() for label in group]
    assert len(labels) == 126
    assert len(labels) == len(set(labels))
    excluded_visual_probes = {
        "narrow-window-responsive",
        "display-scaling-150",
        "display-scaling-200-qt-representative",
        "growth-charge-minimum-responsive",
        *(
            spec[0]
            for spec in _literal_assignment("RESIZE_MATRIX_SPECS")
        ),
        *(
            spec[0]
            for spec in _literal_assignment("PURCHASE_CONFIRMATION_RESIZE_SPECS")
        ),
    }
    assert excluded_visual_probes.isdisjoint(labels)
    purchase_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_purchase_dialog_fixture",
    )
    fixture_postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    growth_charge_annotation = _method_source(
        "_UiFaceCaptureRunner",
        "_growth_charge_capture_annotation",
    )
    collection_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_collection_environment_mechanics",
    )
    prepare_capture_window = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_capture_window",
    )
    capture_now = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_now",
    )
    assert '"error_banner_visible": error_banner_visible' in purchase_fixture
    assert "not error_variant or error_banner_visible" in purchase_fixture
    assert '"banned_noise_absent"' in purchase_fixture
    assert (
        '"primary_action": _displayed_button_text(dialog.purchase_action)'
        not in purchase_fixture
    )
    assert 'str(dialog.presentation.primary_label)' in purchase_fixture
    assert '"canonical_primary_action": canonical_primary_action' in purchase_fixture
    assert '"refreshed_request_matches_live_terms"' in purchase_fixture
    assert "restore_stale_price_catalog" in purchase_fixture
    assert "on_error=registered_cleanup" in purchase_fixture
    assert '"unavailable_terminal"' in purchase_fixture
    assert 'if variant == "invalid-target"' in purchase_fixture
    assert 'and "Return to Collection" in visible_buttons' in fixture_postcondition
    assert '== "Applying Growth Charge…"' in fixture_postcondition
    assert '== "Choose another plant"' in fixture_postcondition
    assert '== "View plant"' in fixture_postcondition
    assert '== "Applying Growth Charge…"' in growth_charge_annotation
    assert 'dialog.use_action.text() == "Choose another plant"' in growth_charge_annotation
    assert 'dialog.use_action.text() == "View plant"' in growth_charge_annotation
    assert 'dialog.cancel_action.text() == "Close"' in growth_charge_annotation
    assert '"current",' in fixture_postcondition
    assert '"projected",' in fixture_postcondition
    assert '"stage",' in fixture_postcondition
    assert '"inventory",' in fixture_postcondition
    assert '"Growth Charge applied"' in fixture_postcondition
    assert "scroll_maximum == 0" not in fixture_postcondition
    assert '"loadout_routes_enabled": bool(loadout_buttons)' in collection_fixture
    assert '"action_buttons_fully_visible": action_buttons_fully_visible' in collection_fixture
    assert "scrollbar.setValue(scrollbar.maximum())" in collection_fixture
    assert '"complete_effects_visible"' in collection_fixture
    assert '"loadout_summary_visible"' in collection_fixture
    assert 'dashboard._collection_category = "weather"' in collection_fixture
    assert 'dashboard._collection_query = WEATHER_CATALOG["breeze"].name' in collection_fixture
    assert 'mechanics_button.setChecked(True)' in collection_fixture
    assert 'scroll.ensureWidgetVisible(mechanics_button, 0, 80)' in collection_fixture
    assert '"Equipped appearance" in labels' in collection_fixture
    assert 'all(button.isEnabled() for button in loadout_buttons)' in collection_fixture
    assert "devicePixelRatio()" in prepare_capture_window
    assert "self._capture_force_primary = True" in prepare_capture_window
    assert "if widget is not mw:" in capture_now
    starter_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_starter_placement",
    )
    schedule = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_and_advance",
    )
    assert "before_capture=stabilize_placement" in starter_fixture
    assert "before_capture()" in schedule


def test_every_capture_fixture_has_one_exact_renderer_family() -> None:
    contract = _compiled_renderer_family_contract()
    groups = contract["CAPTURE_FACE_GROUPS"]
    resolver = contract["expected_capture_window_family"]
    assert isinstance(groups, tuple)
    assert callable(resolver)
    labels = [label for _group, group_labels in groups for label in group_labels]
    families = [resolver(label) for label in labels]

    assert all(families)
    assert Counter(families) == Counter({
        "AnkiQt": 18,
        "GardenDashboard": 32,
        "GardenProgressDialog": 17,
        "GardenSettingsDialog": 10,
        "NurseryDialog": 15,
        "CollectibleDetailDialog": 4,
        "FertilizerDialog": 4,
        "StarterConfirmationDialog": 1,
        "PlantStoryDialog": 1,
        "FertilizerReplacementDialog": 1,
        "SpeciesOverviewDialog": 2,
        "PurchaseConfirmationDialog": 14,
        "GrowthChargeConfirmationDialog": 7,
    })


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
    assert len({profile["profile_id"] for profile in profiles}) == 126
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
    assert resolver("resize-dashboard-content-1359") == {}
    assert resolver("resize-progress-minimum") == {}
    assert resolver("growth-charge-minimum-responsive") == {}


def test_collection_preview_capture_tracks_the_registry_derived_effects_tab() -> None:
    preview = _method_source(
        "_UiFaceCaptureRunner", "_capture_collection_preview_after"
    )
    semantic = _method_source(
        "_UiFaceCaptureRunner", "_dialog_surface_page_semantic"
    )

    assert "dialog.option_tabs.indexOf(dialog.effects_page)" in preview
    assert "dirty_preview_created" in preview
    assert "dialog._reset_preview()" in preview
    assert '"reset_path_invoked": reset_path_invoked' in preview
    assert '"committed_state_unchanged": committed_state_unchanged' in preview
    assert '0: "loadout", 1: "loadout", 2: "loadout", 3: "preview"' in semantic


def test_capture_runner_drives_every_tab_and_exports_its_contract() -> None:
    source = CAPTURE_PATH.read_text("utf-8")

    for key, label in (
        ("achievements", "progress-achievements"),
        ("collection", "progress-collection"),
    ):
        assert f'self._capture_progress_page("{key}", "{label}")' in source
    redirect = _method_source("_UiFaceCaptureRunner", "_capture_progress_today")
    assert 'label = "progress-overview-redirect-growth"' in redirect
    assert 'dialog.open_page("overview")' in redirect
    assert 'current_page == "growth"' in redirect
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
        "collection-preview-active",
        "collection-preview-restored",
        "settings-display-advanced-open",
        "starter-placement",
        "starter-completion",
        "home-preview-loading",
        "home-preview-error",
        "home-preview-stale",
        "onboarding-persistence-error",
        "move-persistence-error",
        "collection-loadout-persistence-error",
        "collection-origin-plant-placement",
    ):
        assert f'"{label}"' in source
    for index, label in (
        (0, "nursery-plants"),
        (2, "nursery-garden-spaces"),
    ):
        assert f'self._capture_nursery_tab({index}, "{label}")' in source
    weather_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_nursery_weather_scenery",
    )
    assert 'label = "nursery-weather-scenery"' in weather_fixture
    assert 'preview_names = ("Clear Skies preview", "Soft Breeze preview")' in weather_fixture
    assert "ready_audit=audit" in weather_fixture
    assert 'preview.property("gardenRole")' in weather_fixture
    assert '"preview_signatures_distinct"' in weather_fixture
    fertilizer_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_nursery_fertilizer_booster",
    )
    fixture_postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    assert 'label = "nursery-fertilizer-booster"' in fertilizer_fixture
    assert 'definition.item_id == "growth_items:fertilizer_basic"' in fertilizer_fixture
    assert 'state.consumables["fertilizer_basic"] = max(' in fertilizer_fixture
    assert "fixture_setup=setup" in fertilizer_fixture
    assert "ready_audit=audit" in fertilizer_fixture
    assert '"stored_find_fertilizer_usable"' in fixture_postcondition

    assert '"capture_contract_version": CAPTURE_CONTRACT_VERSION' in source
    assert '"capture_groups": [' in source
    assert '"expected_faces": expected_labels' in source
    assert "captured_labels == expected_labels" in source


def test_resize_matrix_covers_every_custom_window_family_and_breakpoint_edge() -> None:
    specs = (
        *_literal_assignment("RESIZE_MATRIX_SPECS"),
        *_literal_assignment("PURCHASE_CONFIRMATION_RESIZE_SPECS"),
        *_literal_assignment("GROWTH_CHARGE_RESIZE_SPECS"),
    )
    layout_modes = _literal_assignment("RESIZE_MATRIX_LAYOUT_MODES")
    families = {spec[1] for spec in specs}

    assert families == {
        "dashboard",
        "settings",
        "progress",
        "collection",
        "collectible-detail",
        "nursery",
        "story",
        "starter-confirmation",
        "fertilizer",
        "fertilizer-replacement",
        "species-overview",
        "purchase-confirmation",
        "growth-charge",
    }
    assert all(spec[3] > 0 and spec[4] > 0 for spec in specs)
    assert sum("historical-edge-low-stability-probe" == spec[2] for spec in specs) == 13
    assert sum("historical-edge-high-stability-probe" == spec[2] for spec in specs) == 13
    assert sum("measured-threshold-minus-one" == spec[2] for spec in specs) == 1
    assert sum("measured-threshold-plus-one" == spec[2] for spec in specs) == 1
    by_label = {spec[0]: spec for spec in specs}
    assert by_label["purchase-confirmation-breakpoint-low"][3] == 517
    assert by_label["purchase-confirmation-breakpoint-high"][3] == 519
    comparison_threshold = 220 + 220 + 10 + 24
    assert 517 - 44 == comparison_threshold - 1
    assert 519 - 44 == comparison_threshold + 1
    assert set(layout_modes) == {spec[0] for spec in specs}
    assert layout_modes["geometry-growth-charge-minimum"] == "compact"
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
        ("resize-collectible-detail-content-819", "resize-collectible-detail-content-821"),
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


def test_capture_manifest_records_canonical_geometry_and_responsive_telemetry() -> None:
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
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
    assert "[int(widget.width()), int(widget.height())]" in capture_now
    assert '"canonical-open"' in capture_now
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

    measured_breakpoint = classify(
        label="purchase-confirmation-breakpoint-low",
        declared_size=[517, 520],
        actual_size=[517, 520],
        minimum_size=[420, 400],
        maximum_size=[820, 660],
        screen_limited=False,
        constraint_limited=False,
        native_normalized=False,
        normalization_reason="",
    )
    assert measured_breakpoint["accepted"] is True
    assert measured_breakpoint["breakpoint_fixture"] is True


def test_capture_timeouts_and_step_exceptions_fail_closed() -> None:
    next_step = _method_source("_UiFaceCaptureRunner", "_next_step")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")
    wait = _method_source("_UiFaceCaptureRunner", "_wait_for")
    collection = _method_source("_UiFaceCaptureRunner", "_wait_for_collection")
    dashboard = _method_source("_UiFaceCaptureRunner", "_wait_for_dashboard")
    seed = _method_source("_UiFaceCaptureRunner", "_prepare_capture_state")

    assert "Capture step" in next_step
    assert "type(exc).__name__" in next_step
    assert "if self._fatal_fixture_restore_failure:" in next_step
    assert "and not self._fatal_fixture_restore_failure" in finish
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
    growth_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_growth_capture_fixture",
    )
    growth_restore = _method_source(
        "_UiFaceCaptureRunner",
        "_restore_growth_capture_fixture",
    )
    reward_restore = _method_source(
        "_UiFaceCaptureRunner",
        "_restore_reward_capture_fixture",
    )
    with_dashboard = _method_source("_UiFaceCaptureRunner", "_with_dashboard")

    assert "populated=False" in growth_zero
    assert "populated=True" in growth_nonzero
    assert "points = (1_250, 2_450, 7_950)" in growth_fixture
    assert "stats.plant_nurtured_growth" in growth_fixture
    assert "stats.plant_passive_growth_fifths" in growth_fixture
    assert "stats.plant_charge_growth" in growth_fixture
    assert "state.onboarding.starter_plant_id = plants[0].plant_id" in growth_fixture
    assert "self._restore_capture_fixture_state(snapshot)" in growth_restore
    assert "self._restore_capture_fixture_state(snapshot)" in reward_restore
    assert "except Exception" not in growth_restore
    assert "except Exception" not in reward_restore
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
    assert "root.querySelector('[data-testid=\"home-open\"]')" in source
    assert "homeAction.dataset.ankiGardenCommand" in source
    assert "capture_label: str" in source
    assert "visibleRoots[visibleRoots.length - 1]" in source
    assert "command.endsWith(':open')" in source
    assert "const canonicalSettled = fixtureState.startsWith('preview-')" in source
    assert "root.dataset.state === 'success'" in source
    assert "failedImageCount === 0" in source
    assert "!previewStatusPresent" in source
    assert "!loadingPresent" in source
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
    fertilize = _method_source("_UiFaceCaptureRunner", "_capture_fertilize_after")
    prepare_expiring = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_expiring_fertilizer",
    )
    expiring = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fertilizer_expiring",
    )
    popover = _method_source("_UiFaceCaptureRunner", "_capture_popover_slot")
    reveal = _method_source(
        "_UiFaceCaptureRunner",
        "_reveal_capture_plant_card",
    )

    assert "FertilizerReplacementDialog" in finder
    assert "QMessageBox" not in finder
    assert "_visible_fertilizer_replacement_dialog" in replacement
    assert "purchase_fertilizer" not in fertilize
    assert "purchase_fertilizer" not in prepare_expiring
    assert "Fertilizer(" in fertilize
    assert "Fertilizer(" in prepare_expiring
    assert "_capture_fixture_state_snapshot(label)" in fertilize
    assert "_capture_fixture_state_snapshot(label)" in expiring
    assert "_capture_fixture_state_snapshot(label)" in replacement
    assert "on_error=cleanup" in fertilize
    assert "on_error=registered_cleanup" in expiring
    assert "on_error=registered_cleanup" in replacement
    assert "dashboard.plant_card.isVisible()" in popover
    assert "reveal_plant_card=True" in popover
    assert "scroll.ensureWidgetVisible(card, 0, 24)" in reveal
    assert '"plant_card_fully_visible": contained' in reveal


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
    capture_source = CAPTURE_PATH.read_text("utf-8")
    fixture_snapshot = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_state_snapshot",
    )
    fixture_restore = _method_source(
        "_UiFaceCaptureRunner",
        "_restore_capture_fixture_state",
    )
    achievement = _method_source("_UiFaceCaptureRunner", "_capture_achievement_completed")
    streak_active = _method_source("_UiFaceCaptureRunner", "_capture_streak_active")
    streak_state = _method_source("_UiFaceCaptureRunner", "_set_streak_capture_state")
    streak_receipts = _method_source(
        "_UiFaceCaptureRunner",
        "_append_canonical_streak_reward_receipts",
    )
    missed_streak = _method_source("_UiFaceCaptureRunner", "_capture_streak_missed_day")
    fixture_postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    streak_achievement = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_streak_achievement_states",
    )
    reward_history = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_reward_history_capture_fixture",
    )
    reviewer_feedback = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_canonical_reviewer_feedback_fixture",
    )
    reviewer_capture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_reviewer_find_feedback",
    )
    reviewer_wait = _method_source(
        "_UiFaceCaptureRunner",
        "_with_capture_reviewer",
    )
    capture_home = _method_source("_UiFaceCaptureRunner", "_capture_home_pixmap")
    capture_now = _method_source("_UiFaceCaptureRunner", "_capture_now")
    collection = _method_source("_UiFaceCaptureRunner", "_capture_collection_several")
    known_species = _method_source(
        "_UiFaceCaptureRunner", "_capture_known_uncollected_species_overview"
    )
    starter_placement = _method_source(
        "_UiFaceCaptureRunner", "_capture_starter_placement"
    )
    purchase = _method_source("_UiFaceCaptureRunner", "_capture_nursery_purchase_success")
    purchase_snapshot = _method_source(
        "_UiFaceCaptureRunner",
        "_purchase_capture_snapshot",
    )
    purchase_success = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_purchase_success_fixture",
    )
    growth_charge_prepare = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_growth_charge_capture",
    )
    growth_charge_restore = _method_source(
        "_UiFaceCaptureRunner",
        "_restore_growth_charge_capture",
    )
    growth_charge_capture = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_growth_charge_dialog_fixture",
    )
    nursery_locked = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_nursery_locked_item",
    )
    loadout_error = _method_source(
        "_UiFaceCaptureRunner", "_capture_collection_loadout_persistence_error"
    )

    assert "exact_ledger_restore: bool = False" in fixture_snapshot
    assert "self.app.engine._state_snapshot()" not in capture_source
    assert 'os.environ.get("ANKI_GARDEN_CAPTURE_UI_FACES") != "1"' in fixture_snapshot
    assert 'getattr(storage, "_reward_ledger", None) is None' in fixture_snapshot
    assert "if not callable(has_staged):" in fixture_snapshot
    assert "if has_staged():" in fixture_snapshot
    assert "storage.create_development_backup()" in fixture_snapshot
    assert '"capture_plant_id_order"' in fixture_snapshot
    assert 'backup_path.suffix != ".sqlite3"' in fixture_snapshot
    assert fixture_snapshot.index("backup_path =") < fixture_snapshot.rindex(
        "snapshot = engine._state_snapshot()"
    )
    assert "ledger.rollback_all()" in fixture_restore
    assert "storage.restore_development_backup(Path(backup_value))" in fixture_restore
    assert "self.app.engine.state.__dict__.clear()" in fixture_restore
    assert "self.app.engine.state.__dict__.update(restored.__dict__)" in fixture_restore
    assert "storage.state = self.app.engine.state" in fixture_restore
    assert "restore_capture_plant_order(" in fixture_restore
    authoritative_restore = fixture_restore.index(
        "storage.restore_development_backup(Path(backup_value))"
    )
    completion_latch = fixture_restore.index(
        'setattr(snapshot, "capture_restore_complete", True)',
        authoritative_restore,
    )
    assert authoritative_restore < completion_latch < fixture_restore.index(
        "self._refresh_capture_dashboard()"
    )
    assert "self._fatal_fixture_restore_failure = True" in fixture_restore
    assert '"Capture fixture state restoration raised "' in fixture_restore

    assert "state.currency_transactions.clear()" in purchase_snapshot
    assert "state.completed_purchase_requests.clear()" in purchase_snapshot
    assert "exact_ledger_restore=True" in purchase_success
    assert purchase_success.index(
        'cleanup_holder["callback"] = cleanup'
    ) < purchase_success.index("self.app.engine.confirm_purchase(")
    assert "on_error=registered_cleanup" in purchase_success

    assert "state.onboarding.starter_plant_id = plant.plant_id" in growth_charge_prepare
    assert "self.app.engine._pending_stage_transitions" in growth_charge_restore
    assert "self._restore_capture_fixture_state(snapshot)" in growth_charge_restore
    assert 'exact_ledger_restore=variant == "success"' in growth_charge_capture
    assert growth_charge_capture.index(
        'cleanup_holder["callback"] = cleanup'
    ) < growth_charge_capture.index("dialog._commit()")
    assert "on_error=registered_cleanup" in growth_charge_capture

    assert "_capture_fixture_state_snapshot(label)" in nursery_locked
    assert "_restore_capture_fixture_state(snapshot)" in nursery_locked
    assert "on_error=cleanup" in nursery_locked

    assert "ACHIEVEMENT_DEFINITIONS" in achievement
    assert "_prepare_canonical_achievement_capture_fixture" in achievement
    assert "completed_ids=completed_ids" in achievement
    assert '"reward_summaries"' in achievement
    assert "claimed_streak_rewards" not in achievement

    assert "StreakPresentationState.ENDED" in missed_streak
    assert "presentation.current_days == 0" in missed_streak
    assert 'ACHIEVEMENTS_BY_ID["streak_7"].progress_target' in missed_streak
    assert "presentation.previous_days == previous_days" in missed_streak
    assert '"previous_streak_days": previous_days' in missed_streak
    assert "current_streak_days=presentation.current_days" in missed_streak
    assert '"weekly_reward_status": weekly_reward.status' in missed_streak
    assert '"missed_day_weekly_reward_projection"' in fixture_postcondition
    assert "weekly_reward.status in visible_label_texts" in fixture_postcondition
    assert 'completed_ids=("streak_7",)' in streak_achievement
    assert 'item.achievement_id == "streak_30"' in streak_achievement
    assert '"streak-achievement-earned-next"' in streak_achievement
    assert '"next_growth_bonus_days"' in streak_achievement
    assert "claimed_streak_rewards" not in streak_achievement
    assert "RewardReceipt(" in streak_receipts
    assert 'source="daily_activity"' in streak_receipts
    assert 'source="achievement" if first_cycle else "weekly_streak"' in streak_receipts
    assert "_append_canonical_streak_reward_receipts(" in streak_active
    assert 'ACHIEVEMENTS_BY_ID["streak_7"]' in streak_active
    assert "streak_days=streak_days" in streak_active
    assert "definition.reward.coins" in streak_active
    assert "reward_rules[\"daily_activity\"].awarded_today" in streak_active
    assert "if reviewed > 0:" in streak_state
    assert "_append_canonical_streak_reward_receipts(streak_days=days)" in streak_state

    assert "STANDARD_FIND_REGISTRY" in reward_history
    assert "RewardReceipt(" in reward_history
    assert "GardenFindOutcome(" in reward_history
    assert 'stacked_correlation = "capture-review:stacked-achievement"' in reward_history
    assert "receipt.correlation_id == stacked_correlation" in reward_history
    assert '"find_morning_dew"' in reward_history
    assert '"find_fertilizer"' in reward_history
    assert "inventory_item_id" in reward_history
    assert '"direct_growth_has_passive_wording"' in reward_history
    assert "STANDARD_FIND_REGISTRY" in reviewer_feedback
    assert "SPECIAL_ENVIRONMENT_POOL" in reviewer_feedback
    assert "ENVIRONMENT_POOL_ID" in reviewer_feedback
    assert "ENVIRONMENT_POOL_VERSION" in reviewer_feedback
    assert 'source="garden_find_environment"' in reviewer_feedback
    assert "recent_reward_summaries(state)" in reviewer_feedback
    assert "GardenFindOutcome(" in reviewer_feedback
    assert "RewardReceipt(" in reviewer_feedback
    assert "self.app.engine._queue_reward_feedback(" in reviewer_feedback
    assert reviewer_feedback.count("self.app.engine._queue_reward_feedback(") == 1
    assert 'sync_correlation = f"sync:capture-reviewer:{day_value}"' in reviewer_feedback
    assert 'title="Synced review rewards"' in reviewer_feedback
    assert 'feedback.message == expected_message' in reviewer_feedback
    assert "feedback.amount == 0" in reviewer_feedback
    assert "expected_total = sum" not in reviewer_feedback
    assert "handler._consolidated_reward_feedback(" in reviewer_feedback
    assert "all_receipt_groups_share_correlation" in reviewer_feedback
    assert 'cleanup_holder["callback"] = cleanup' in reviewer_capture
    assert "on_error=registered_cleanup" in reviewer_capture
    assert "on_error=on_error" in reviewer_wait
    assert reviewer_capture.index('cleanup_holder["callback"] = cleanup') < reviewer_capture.index(
        'config = getattr(self.app, "config", None)'
    )
    assert "required_overlays" in capture_home
    assert "self._pixmap_contains_overlay" in capture_home
    assert 'method += "-with-overlays"' in capture_home
    assert 'annotation["required_overlay_pixels_present"]' in capture_now
    assert "Reviewer reward toast was not present in the captured pixels" in capture_now
    assert 'ACHIEVEMENTS_BY_ID["retention_90"]' in capture_source
    assert 'annotation.get("expected_feedback_message", "")' in capture_source
    assert "canonical_feedback_message" in capture_source
    assert 'environment_item_ids=("fireflies",)' in capture_source
    assert '"reviewer-find-exceptional"' not in capture_source
    assert "ReviewerRewardFeedback(" not in capture_source
    for retired_contract in (
        "claimed_streak_rewards",
        "STREAK_REWARD_MILESTONES",
        "achievement_progress_display",
        "_credit_currency",
        "growth_charge_grand",
        "COIN_DROP_AMOUNT",
        "1 in 800",
        "1-in-800",
        "Streak XP",
    ):
        assert retired_contract not in capture_source

    assert "][:4]" in collection.replace(" ", "")
    assert "discovered_count == 4" in collection
    assert 'restore_callback=restore' in collection

    assert 'label = "collection-known-not-collected-overview"' in known_species
    assert 'dialog.property("collectionState")' in known_species
    assert '"not-collected"' in known_species
    assert '"Undiscovered Rare stage silhouette"' in known_species
    assert 'close_callback=lambda: (self._close_widget(dialog), restore())' in known_species
    assert "engine.state.loadout.to_dict()" in loadout_error
    assert "before == after" in loadout_error

    assert 'dashboard.scene.finish_move("Preparing starter placement capture.")' in starter_placement
    assert "dashboard._placement_draft = None" in starter_placement
    assert "close_ms=2300" in starter_placement
    assert "next_ms=2600" in starter_placement

    assert "self.app.engine.quote_purchase(purchase_kind, item.item_id)" in purchase
    assert "self.app.engine.confirm_purchase(" in purchase
    assert "PurchaseRequest.from_quote(quote)" in purchase
    assert "outcome.success" in purchase
    assert "dialog._preview_environment_item(item)" in purchase
    assert "owns_environment(item.kind, item.item_id)" in purchase
    assert "dialog.environment_feature_title.text()" in purchase
    assert "exact_ledger_restore=True" in purchase
    assert "state.currency_transactions.clear()" in purchase
    assert "state.completed_purchase_requests.clear()" in purchase
    assert "on_error=cleanup" in purchase


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
    assert "preview_with_phase" not in home
    assert "Updating garden preview" not in home
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
            "collection-loadout-detail",
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
            _requested_scale_factor="1.0",
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
    assert 'bool(row[2]["required_overlays_present"])' in capture_home
    assert 'row[2]["passed"] or (' in capture_home
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
    assert "self._move_to_capture_display(widget)" not in capture_home


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


def test_capture_display_move_relocates_once_then_becomes_idempotent() -> None:
    calls: list[object] = []

    class Geometry:
        def __init__(self, x: int, y: int, width: int, height: int) -> None:
            self._x = x
            self._y = y
            self._width = width
            self._height = height

        def x(self) -> int:
            return self._x

        def y(self) -> int:
            return self._y

        def width(self) -> int:
            return self._width

        def height(self) -> int:
            return self._height

    class Screen:
        def availableGeometry(self) -> Geometry:
            return Geometry(0, 0, 1920, 1080)

    target_screen = Screen()
    other_screen = Screen()

    class Handle:
        def __init__(self, widget: "Widget") -> None:
            self.widget = widget

        def screen(self) -> Screen:
            return self.widget.current_screen

        def setScreen(self, screen: Screen) -> None:
            calls.append(("setScreen", screen))
            self.widget.current_screen = screen

    class Widget:
        def __init__(self) -> None:
            self.current_screen = other_screen
            self.frame = Geometry(-1000, 0, 1000, 800)

        def windowHandle(self) -> Handle:
            return Handle(self)

        def frameGeometry(self) -> Geometry:
            return self.frame

        def width(self) -> int:
            return 1000

        def height(self) -> int:
            return 800

        def move(self, x: int, y: int) -> None:
            calls.append(("move", x, y))
            self.frame = Geometry(x, y, 1000, 800)

    move_to_display = _compiled_method(
        "_UiFaceCaptureRunner",
        "_move_to_capture_display",
        QGuiApplication=SimpleNamespace(
            screens=lambda: [target_screen],
            primaryScreen=lambda: target_screen,
        ),
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
        os=SimpleNamespace(environ={}),
    )
    runner = SimpleNamespace(
        _capture_display="secondary",
        _capture_force_primary=False,
    )

    widget = Widget()
    move_to_display(runner, widget)
    first_call_count = len(calls)
    move_to_display(runner, widget)

    assert calls == [
        ("setScreen", target_screen),
        ("move", 24, 24),
    ]
    assert len(calls) == first_call_count
    assert runner._capture_display == "primary"

    target_screen.devicePixelRatio = lambda: 2.0
    other_screen.devicePixelRatio = lambda: 1.0
    timers: list[tuple[int, object]] = []
    prepare_capture_window = _compiled_method(
        "_UiFaceCaptureRunner",
        "_prepare_capture_window",
        QGuiApplication=SimpleNamespace(
            screens=lambda: [target_screen, other_screen],
        ),
        QTimer=SimpleNamespace(
            singleShot=lambda delay, callback: timers.append((delay, callback)),
        ),
        logger=SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            debug=lambda *_args, **_kwargs: None,
        ),
        os=SimpleNamespace(environ={}),
        mw=object(),
    )
    prepared: list[bool] = []
    prepare_runner = SimpleNamespace(
        _capture_force_primary=False,
        _move_to_capture_display=lambda _widget: prepared.append(
            prepare_runner._capture_force_primary
        ),
        _prepare_starter_phase=lambda: None,
    )

    prepare_capture_window(prepare_runner)

    assert prepare_runner._capture_force_primary is True
    assert prepared == [True]
    assert timers == [(300, prepare_runner._prepare_starter_phase)]


def test_secondary_home_capture_never_accepts_desktop_or_moves_synchronously() -> None:
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
        _home_capture_ready_attempts=3,
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

    runner._home_pixmap_metrics = metrics
    runner._move_to_capture_display = lambda _target: (_ for _ in ()).throw(
        AssertionError("Home capture must not move WebEngine synchronously")
    )

    pixmap, method, foreground = capture_home(runner, widget)
    assert pixmap is None
    assert method == "semantic-window-not-ready"
    assert foreground is True
    assert runner._capture_force_primary is True
    assert widget.capture_display == "secondary"
    assert process_events == [True, True, True, True]
    assert len(warnings) == 3
    assert warnings[0][1] == "secondary"
    assert warnings[0][2][0] == {
        "method": "foreground-screen-region",
        "pixel_size": [2002, 1710],
        "generic": True,
        "semantic": False,
        "brand_ratio": 0.0,
        "required_overlays_present": True,
    }


def test_remaining_release_faces_prepare_and_audit_their_exact_ui_states() -> None:
    clear_recall = _method_source(
        "_UiFaceCaptureRunner", "_capture_clear_recall_projection"
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
    move_destinations = _method_source(
        "_UiFaceCaptureRunner", "_capture_move_mixed_destinations"
    )
    postcondition = _method_source(
        "_UiFaceCaptureRunner", "_capture_fixture_postcondition"
    )
    production = _method_source(
        "_UiFaceCaptureRunner", "_capture_production_controls_absent"
    )

    assert "achievement_presentation" in clear_recall
    assert 'ACHIEVEMENTS_BY_ID["retention_90"]' in clear_recall
    assert "definition.minimum_answers" in clear_recall
    assert "definition.progress_target" in clear_recall
    assert "definition.reward.coins" in clear_recall
    assert '"condition_lines": list(projection.condition_lines)' in clear_recall
    assert "achievement_progress_display" not in clear_recall

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
    assert "reveal_plant_card=True" in fully_grown

    assert "scrollbar.setValue(scrollbar.maximum())" in move_destinations
    assert "scrollbar.setValue(0)" in move_destinations
    assert "close_callback=cleanup" in move_destinations
    assert "scroll_child_bounds(" in postcondition
    assert '"move_scene_fully_visible"' in postcondition

    assert "GardenSettingsDialog(" in production
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
    assert '"development_controls_implemented": False' in production


def test_release_capture_has_no_scale_or_resize_proxy_runtime_paths() -> None:
    source = CAPTURE_PATH.read_text("utf-8")
    module = ast.parse(source)
    runner = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "_UiFaceCaptureRunner"
    )
    methods = {
        node.name for node in runner.body if isinstance(node, ast.FunctionDef)
    }

    assert {
        "_capture_display_scaling_200_representative",
        "_capture_requested_size",
        "_capture_resize_matrix_face",
        "_capture_purchase_confirmation_resize",
        "_capture_growth_charge_minimum_responsive",
    }.isdisjoint(methods)
    labels = {
        label
        for _group, group_labels in _literal_assignment("CAPTURE_FACE_GROUPS")
        for label in group_labels
    }
    assert {
        "narrow-window-responsive",
        "display-scaling-150",
        "display-scaling-200-qt-representative",
        "growth-charge-minimum-responsive",
    }.isdisjoint(labels)
    assert "record[\"audit\"] = dict(annotation)" in _method_source(
        "_UiFaceCaptureRunner", "_capture_now"
    )


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
        before_capture = kwargs.get("before_capture")
        assert callable(before_capture)
        before_capture()
        assert button.hasFocus() is True
        events.append("capture")
        callback = kwargs.get("close_callback")
        assert callable(callback)
        callback()
        callback()

    runner._capture_and_advance = capture_and_advance
    runner._with_dashboard = lambda ready, **_kwargs: ready()

    capture_focus(runner)

    assert events == [
        "events",
        "focus",
        "events",
        "focus",
        "capture",
        "clear",
        "events",
    ]
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
    assert '"keyboard_focus_fixture_cleared"' not in postcondition
    assert 'state_name.startswith("resize-dashboard-")' not in postcondition
    assert "focus_owner is button" in postcondition
    assert "close_callback=clear_focus_once" in keyboard
    assert "before_capture=focus_before_capture" in keyboard
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
    growth_annotation = _method_source(
        "_UiFaceCaptureRunner",
        "_growth_charge_capture_annotation",
    )
    placement = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_collection_origin_plant_placement",
    )

    assert "expected_capture_state_profile(label)" in postcondition
    assert '"ordered_fixture_label"' in postcondition
    assert '"dom_fixture_ready"' in postcondition
    assert '"progress_page"' in postcondition
    assert '"nursery_tab"' in postcondition
    assert '"settings_tab"' in postcondition
    assert 'kind == "resize"' not in postcondition
    assert '"collection_no_results_visible"' in postcondition
    assert '"restored_preview_status_cleared"' in postcondition
    assert '"restored_preview_transition"' in postcondition
    assert 'annotation.get("persisted_visibility"' in postcondition
    assert '"stale_purchase_values_are_previews"' in postcondition
    assert '"onboarding_copy_clear_of_actions"' in postcondition
    onboarding_geometry = _method_source(
        "_UiFaceCaptureRunner",
        "_onboarding_copy_geometry",
    )
    assert '"message_height_sufficient"' in onboarding_geometry
    assert 'annotation.get("target_card_fully_visible", False)' in postcondition
    assert 'annotation.get("plant_card_fully_visible", False)' in postcondition
    assert '"distinct_weather_preview_art"' in postcondition
    assert 'int(widget.unsaved.margin()) >= 8' in postcondition
    assert '"unified_dimmed_weather_scenery_scene"' not in postcondition
    assert 'state_name == "collection-origin-plant-placement"' in postcondition
    for proof in (
        "badge_text_fits",
        "badges_contained",
        "badges_pairwise_non_overlapping",
        "badges_clear_plant_artwork",
        "scene_fully_visible",
    ):
        assert proof in postcondition
        assert proof in placement
    assert "QFontMetricsF" in placement
    assert "badge_metrics.horizontalAdvance" in placement
    assert "badge.intersects(previous)" in placement
    assert "badge.intersects(obstacle)" in placement
    assert "self._capture_fixture_postcondition(" in capture
    assert '"postcondition": postcondition' in capture
    assert "postcondition.get(\"passed\", False)" in capture
    assert 'dict(record.get("fixture_validation", {})).get("passed", False)' in finish
    assert 'variant == "minimum"' not in growth_annotation
    assert '"compact_summary_contained"' not in growth_annotation


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
        events: list[str] = []
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
            events.append("activate")
            advance_global_provenance()
            return True

        runner._move_to_capture_display = (
            lambda _widget: events.append("move")
        )
        runner._activate_current_process_window = activate
        advances: list[int] = []

        def advance(delay: int) -> None:
            advances.append(delay)
            advance_global_provenance()

        runner._next_after = advance
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
        if widget is home_widget:
            assert runner._active_fixture_source == "ordered-step-002:_capture_overview"
            assert events == ["move", "activate"]
        else:
            assert runner._active_fixture_source == "ordered-step-001:_capture_deck_browser"
            assert events == []
        assert advances == []
        assert len(timer_callbacks) == 1
        callback = timer_callbacks.pop()
        assert callable(callback)
        callback()
        assert len(saved) == 1
        assert advances == [80]
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


def test_capture_cleanup_and_advance_are_chained_after_the_screenshot() -> None:
    events: list[str] = []
    timer_callbacks: list[tuple[int, object]] = []
    qtimer = SimpleNamespace(
        singleShot=lambda delay, callback: timer_callbacks.append((delay, callback)),
    )
    schedule = _compiled_method(
        "_UiFaceCaptureRunner",
        "_capture_and_advance",
        QTimer=qtimer,
        logger=SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            exception=lambda *_args, **_kwargs: None,
        ),
        mw=object(),
        time=SimpleNamespace(perf_counter=lambda: 123.0),
    )
    runner = SimpleNamespace(
        _capture_requested_monotonic={},
        _failures=[],
        _reserve_capture_identity=lambda label: (
            81,
            label,
            "ordered-step-075:_capture_missing_artwork_fallback",
            label,
        ),
        _capture_now=lambda *_args, **_kwargs: events.append("capture"),
        _next_after=lambda delay: events.append(f"advance:{delay}"),
    )

    schedule(
        runner,
        "missing-artwork-graphical-fallback",
        object(),
        capture_delay_ms=520,
        close_callback=lambda: events.append("close"),
        close_ms=850,
        next_ms=1200,
    )

    assert events == []
    assert [delay for delay, _callback in timer_callbacks] == [520]
    timer_callbacks.pop(0)[1]()
    assert events == ["capture"]
    assert [delay for delay, _callback in timer_callbacks] == [330]
    timer_callbacks.pop(0)[1]()
    assert events == ["capture", "close", "advance:350"]


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


def test_collection_and_canonical_achievement_fixtures_restore_on_close() -> None:
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
        "_capture_clear_recall_projection",
    )
    achievement_fixture = _method_source(
        "_UiFaceCaptureRunner",
        "_prepare_canonical_achievement_capture_fixture",
    )
    progress_page = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_progress_page_after",
    )
    no_matches = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_collection_no_matches",
    )

    assert "def restore_fixture()" in collection_filter
    assert "on_error=restore_fixture" in collection_filter
    assert "finally:\n                        restore_fixture()" in collection_filter
    assert "scroll.ensureWidgetVisible(no_results, 0, 80)" in collection_filter
    assert '"empty_state_viewport_bounds"' in collection_filter
    assert "def collection_ready()" in collection_filter
    assert "no_results.isVisible()" in collection_filter
    assert "def restore()" in collection_several
    assert "except Exception:\n            restore()" in collection_several
    assert "self._refresh_capture_dashboard()" in collection_several
    assert "dashboard._collection_filter = original_filter" in collection_several
    assert collection_several.index("original_plants =") < collection_several.index(
        "if not self._ensure_development_stress_state():"
    )

    assert "self._capture_fixture_state_snapshot(" in achievement_fixture
    assert "self.app.engine._ensure_achievements()" in achievement_fixture
    assert "self.app.engine._refresh_achievement_progress()" in achievement_fixture
    assert "achievement_presentations(state)" in achievement_fixture
    assert "achievement_progress_display" not in achievement_fixture
    assert "achievement_presentation" in clear_recall
    assert '"canonical_projection": True' in clear_recall
    assert "restore_callback=lambda:" in clear_recall
    assert "_restore_reward_capture_fixture(snapshot)" in clear_recall
    assert "finally:\n                    if restore_callback is not None:" in progress_page
    assert "on_error=restore_callback" in progress_page
    assert 'candidate.property("achievementId")' in progress_page
    assert '== "retention_90"' in progress_page
    assert "scroll.ensureWidgetVisible(target, 0, 24)" in progress_page
    assert '"target_card_fully_visible": contained' in progress_page
    guard = 'if not self._ensure_development_stress_state():'
    assert guard in no_matches
    assert no_matches.index(guard) < no_matches.index(
        'self._capture_collection_filter('
    )
    assert "collectible_views(state)" in no_matches
    assert 'view.definition.category != "growth_items"' in no_matches
    assert "state.consumables[item_id] = max(" in no_matches
    assert "self._capture_fixture_state_snapshot(label)" in no_matches
    assert "restore_callback=restore" in no_matches
    assert "except Exception:\n            restore()" in no_matches
    assert "self._next_after(200)" in no_matches


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


def test_responsive_geometry_specs_are_automated_data_not_release_steps() -> None:
    source = _method_source("_UiFaceCaptureRunner", "__init__")
    release_labels = {
        label
        for _group, labels in _literal_assignment("CAPTURE_FACE_GROUPS")
        for label in labels
    }
    geometry_specs = (
        *_literal_assignment("RESIZE_MATRIX_SPECS"),
        *_literal_assignment("PURCHASE_CONFIRMATION_RESIZE_SPECS"),
        *_literal_assignment("GROWTH_CHARGE_RESIZE_SPECS"),
    )

    assert "_capture_resize_matrix_face" not in source
    assert "_capture_purchase_confirmation_resize" not in source
    assert "_capture_growth_charge_minimum_responsive" not in source
    assert release_labels.isdisjoint(spec[0] for spec in geometry_specs)
    assert {spec[1] for spec in geometry_specs} >= {
        "dashboard",
        "progress",
        "collection",
        "purchase-confirmation",
        "growth-charge",
    }


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
    restore_order = _compiled_function("restore_capture_plant_order")
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

    restored = restore_order(
        list(reversed(first)),
        tuple(plant.plant_id for plant in first),
    )
    assert [id(plant) for plant in restored] == [id(plant) for plant in first]
    try:
        restore_order(first[:-1], tuple(plant.plant_id for plant in first))
    except ValueError:
        pass
    else:
        raise AssertionError("A partial capture restore must fail closed")


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
    assert "state.onboarding.starter_plant_id = plants[0].plant_id" in setup
    assert "state.currency_transactions.clear()" in setup
    assert "self.app.storage.save()" in setup
    assert setup.index("self.app.storage.save()") < setup.index(
        "self._development_stress_ready = True"
    )
    assert '"canonical_development_species_order"' in postcondition
    assert '"canonical_development_plant_ids"' in postcondition
    assert '"canonical_development_generated_names"' in postcondition
    assert 'state_name.startswith("resize-")' not in postcondition


def test_text_layout_audit_only_exempts_intentionally_scrolled_out_content() -> None:
    audit = _method_source("_UiFaceCaptureRunner", "_find_text_layout_warnings")
    qt_exemption = _method_source(
        "_UiFaceCaptureRunner",
        "_text_candidate_is_intentionally_scrolled_out",
    )

    assert "int(candidate.width()) <= 0" in audit
    assert "int(candidate.height()) <= 0" in audit
    assert "candidate.window() is not root.window()" in audit
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


def test_reviewer_capture_prepares_one_basic_card_with_current_anki_api() -> None:
    events: list[object] = []
    basic_notetype = object()

    class Decks:
        def id(self, name: str) -> int:
            events.append(("deck", name))
            return 42

        def select(self, deck_id: int) -> None:
            events.append(("select", deck_id))

    class Models:
        def by_name(self, name: str) -> object:
            events.append(("notetype", name))
            return basic_notetype

        def current(self) -> None:
            raise AssertionError("Basic should be resolved by name")

    class Collection:
        decks = Decks()
        models = Models()

        def new_note(self, notetype: object) -> dict[str, str]:
            assert notetype is basic_notetype
            events.append(("new_note", notetype))
            return {"Front": "", "Back": ""}

        def add_note(self, note: dict[str, str], deck_id: int) -> None:
            events.append(("add_note", dict(note), deck_id))

        def reset(self) -> None:
            events.append("reset")

    prepare = _compiled_method(
        "_UiFaceCaptureRunner",
        "_prepare_reviewer_capture_card",
        mw=SimpleNamespace(col=Collection()),
        logger=SimpleNamespace(exception=lambda *_args, **_kwargs: None),
    )
    runner = SimpleNamespace(_reviewer_capture_card_ready=False)

    assert prepare(runner) is True
    assert prepare(runner) is True
    assert events == [
        ("deck", "Anki Garden Capture"),
        ("notetype", "Basic"),
        ("new_note", basic_notetype),
        (
            "add_note",
            {
                "Front": "What did this review uncover?",
                "Back": "A Garden Find.",
            },
            42,
        ),
        ("select", 42),
        "reset",
    ]


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
        _fatal_fixture_restore_failure=False,
        _failures=[],
        _performance_samples={},
        _requested_scale_factor="1.0",
        _screenshots=["face-1.png"],
        _text_layout_warnings=[],
        session_dir=invalid_session_dir,
    )

    finish(runner)

    assert exits == [1]
