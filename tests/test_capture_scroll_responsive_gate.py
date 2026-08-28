from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_ui_capture import (
    CaptureValidationError,
    dialog_scroll_audit_issue_codes,
    load_dialog_scroll_capture_coverage,
)


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "ankigarden" / "capture" / "runtime.py"


def _module() -> ast.Module:
    return ast.parse(CAPTURE.read_text("utf-8"))


def _literal_assignment(name: str) -> Any:
    for node in _module().body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(value)
    raise AssertionError(f"missing assignment {name}")


def _compiled_functions(*names: str) -> dict[str, Any]:
    selected = [
        node
        for node in _module().body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in selected} == set(names)
    future = ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )
    namespace: dict[str, Any] = {"Any": Any}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[])),
            str(CAPTURE),
            "exec",
        ),
        namespace,
    )
    return namespace


def _method_source(class_name: str, method_name: str) -> str:
    owner = next(
        node
        for node in _module().body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    segment = ast.get_source_segment(CAPTURE.read_text("utf-8"), method)
    assert segment is not None
    return segment


def _valid_scroll_geometry() -> dict[str, Any]:
    return {
        "registered_count": 4,
        "active_count": 1,
        "footer_visible": True,
        "footer_height": 64,
        "footer_top": 400,
        "viewport_top": 100,
        "viewport_height": 300,
        "declared_clearance": 64,
        "layout_clearance": 64,
        "content_height": 300,
        "content_size_hint_height": 240,
        "content_minimum_size_hint_height": 220,
        "scroll_minimum": 0,
        "scroll_maximum": 0,
        "last_body_child_bottom": 300,
        "last_body_child_bottom_at_scroll_end": 400,
        "require_no_scroll": False,
    }


def _valid_progress_scroll_audit() -> dict[str, Any]:
    return {
        "applicable": True,
        "surface": "Garden Progress",
        "expected_page_semantic": "GardenProgressDialog:achievements",
        "actual_page_semantic": "GardenProgressDialog:achievements",
        "scroll_name": "Achievement progress scroll area",
        "expected_scroll_name": "",
        "registered_count": 5,
        "active_count": 1,
        "expected_active_count": 1,
        "window_mode": "workspace",
        "content_screen_limited": False,
        "footer_visible": False,
        "footer_height": 0,
        "footer_top": 0,
        "viewport_top": 134,
        "viewport_height": 418,
        "viewport_bottom": 552,
        "declared_clearance": 0,
        "layout_clearance": 0,
        "content_height": 866,
        "content_size_hint_height": 866,
        "content_minimum_size_hint_height": 866,
        "scroll_minimum": 0,
        "scroll_maximum": 448,
        "last_body_child_bottom": 848,
        "last_body_child_bottom_at_scroll_end": 534,
        "require_no_scroll": False,
        "required_content_height": 866,
        "reachable_content_height": 866,
        "fixed_progress_header": True,
        "complete_row_available_height": 420,
        "complete_row_viewport_height": 418,
        "complete_row_bottom_gutter": 2,
        "complete_row_content_origin_y": 0,
        "complete_row_bottom_padding": 18,
        "complete_row_boundaries": [148, 266, 418, 570],
        "complete_row_eligible_boundaries": [148, 266, 418],
        "issues": [],
        "passed": True,
    }


def test_scroll_geometry_accepts_short_and_reachable_long_content() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    short = _valid_scroll_geometry()
    # Four registered tab pages with one visible owner proves hidden pages do
    # not count as nested active scrolling.
    assert check(**short) == ()

    long = dict(short)
    long.update({
        "viewport_height": 240,
        "footer_top": 340,
        "content_height": 720,
        "content_size_hint_height": 720,
        "content_minimum_size_hint_height": 680,
        "scroll_maximum": 480,
        "last_body_child_bottom": 720,
        "last_body_child_bottom_at_scroll_end": 340,
    })
    assert check(**long) == ()


def test_scroll_geometry_does_not_treat_preferred_height_as_mandatory() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    geometry = _valid_scroll_geometry()
    geometry.update({
        "viewport_height": 240,
        "footer_top": 340,
        "content_height": 360,
        "content_size_hint_height": 420,
        "content_minimum_size_hint_height": 340,
        "scroll_maximum": 120,
        "last_body_child_bottom": 360,
        "last_body_child_bottom_at_scroll_end": 340,
    })

    assert check(**geometry) == ()


def test_scroll_geometry_rejects_missing_nested_and_min_height_failures() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    missing = _valid_scroll_geometry()
    missing["active_count"] = 0
    assert check(**missing) == ("active-scroll-count",)
    nested = _valid_scroll_geometry()
    nested["active_count"] = 2
    assert check(**nested) == ("active-scroll-count",)

    unreachable = _valid_scroll_geometry()
    unreachable.update({
        "viewport_height": 200,
        "footer_top": 300,
        "content_height": 700,
        "content_size_hint_height": 700,
        "content_minimum_size_hint_height": 650,
        "scroll_maximum": 499,
        "last_body_child_bottom": 700,
        "last_body_child_bottom_at_scroll_end": 301,
    })
    assert "unreachable-scroll-content" in check(**unreachable)


def test_capture_and_validator_reject_the_same_invalid_scroll_metrics() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    geometry = _valid_scroll_geometry()
    geometry.update({
        "footer_visible": False,
        "footer_height": 64,
        "footer_top": 0,
        "viewport_top": 0,
        "viewport_height": 0,
        "declared_clearance": 0,
        "layout_clearance": 0,
        "content_height": 0,
        "content_size_hint_height": -1,
        "content_minimum_size_hint_height": 0,
        "scroll_minimum": 4,
        "scroll_maximum": 3,
        "last_body_child_bottom": 0,
        "last_body_child_bottom_at_scroll_end": 0,
    })
    capture_issues = check(**geometry)
    audit = {
        "applicable": True,
        "scroll_name": "Test scroll",
        "expected_scroll_name": "",
        **geometry,
        "viewport_bottom": 0,
        "required_content_height": 0,
        "reachable_content_height": 0,
        "issues": [],
        "passed": True,
    }

    assert capture_issues == dialog_scroll_audit_issue_codes(audit)
    assert "negative-scroll-metric:content_size_hint_height" in capture_issues
    assert "invalid-scroll-metric:viewport_height" in capture_issues
    assert "invalid-scroll-metric:content_height" in capture_issues
    assert "invalid-scroll-range" in capture_issues
    assert "hidden-footer-height" in capture_issues


def test_scroll_geometry_requires_exact_clearance_and_no_footer_overlap() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    geometry = _valid_scroll_geometry()
    geometry.update({
        "declared_clearance": 63,
        "layout_clearance": 65,
        "footer_top": 399,
    })
    assert check(**geometry) == (
        "last-body-child-under-footer",
        "footer-clearance-mismatch",
        "footer-viewport-overlap",
    )


def test_scroll_geometry_rejects_body_under_footer_and_compact_scroll() -> None:
    check = _compiled_functions("dialog_scroll_geometry_issue_codes")[
        "dialog_scroll_geometry_issue_codes"
    ]
    geometry = _valid_scroll_geometry()
    geometry.update({
        "last_body_child_bottom": 302,
        "last_body_child_bottom_at_scroll_end": 401,
        "require_no_scroll": True,
        "scroll_maximum": 1,
    })

    assert check(**geometry) == (
        "last-body-child-under-footer",
        "compact-transaction-scroll-range",
    )




def test_dialog_scroll_auditor_imports_its_concrete_scroll_type() -> None:
    qt_import = next(
        node
        for node in _module().body
        if isinstance(node, ast.ImportFrom)
        and node.module == "aqt.qt"
    )
    imported = {alias.name for alias in qt_import.names}

    assert "QAbstractScrollArea" in imported
    assert "QScrollArea" in imported


def test_all_eleven_scroll_surfaces_retain_exhaustive_diagnostic_evidence() -> None:
    coverage = _literal_assignment("DIALOG_SCROLL_CAPTURE_COVERAGE")
    semantics = _literal_assignment("DIALOG_SCROLL_CAPTURE_SEMANTICS")
    assert set(coverage) == {
        "Purchase confirmation",
        "Nursery",
        "Fertilizer selection",
        "Fertilizer replacement",
        "Plant Story",
        "Species overview",
        "Settings",
        "Garden Progress",
        "Growth Charge confirmation",
        "Collection",
        "Collection loadout details",
    }
    groups = _literal_assignment("EXHAUSTIVE_CAPTURE_FACE_GROUPS")
    contract = {
        label
        for _group, labels in groups
        for label in labels
    }
    flattened = [label for labels in coverage.values() for label in labels]
    assert set(semantics) == set(flattened)
    assert len(flattened) == len(set(flattened))
    assert len(flattened) == 40
    for surface, labels in coverage.items():
        assert labels
        assert set(labels) <= contract
        assert all(not label.startswith("resize-") for label in labels)
    release_labels = {
        label
        for _group, labels in _literal_assignment("CAPTURE_FACE_GROUPS")
        for label in labels
    }
    assert release_labels < contract
    assert "growth-charge-use-ready" in coverage[
        "Growth Charge confirmation"
    ]
    assert coverage["Collection"] == (
        "progress-collection",
        "collection-several-discovered",
        "collection-no-filter-matches",
    )
    assert {
        semantics[label] for label in coverage["Collection"]
    } == {"GardenProgressDialog:collection"}
    responsive_dialog_edges = {
        "resize-settings-content-699",
        "resize-settings-content-701",
        "resize-settings-content-759",
        "resize-settings-content-761",
        "resize-progress-content-819",
        "resize-progress-content-821",
        "resize-collectible-detail-content-819",
        "resize-collectible-detail-content-821",
        "resize-nursery-content-759",
        "resize-nursery-content-761",
        "resize-story-content-539",
        "resize-story-content-541",
        "resize-fertilizer-replacement-content-399",
        "resize-fertilizer-replacement-content-401",
        "purchase-confirmation-breakpoint-low",
        "purchase-confirmation-breakpoint-high",
    }
    assert responsive_dialog_edges.isdisjoint(flattened)
    resize_labels = {
        spec[0]
        for spec in (
            *_literal_assignment("RESIZE_MATRIX_SPECS"),
            *_literal_assignment("PURCHASE_CONFIRMATION_RESIZE_SPECS"),
        )
    }
    assert responsive_dialog_edges <= resize_labels




def test_large_probes_use_semantic_growth_without_enlarging_starter() -> None:
    specs = {spec[0]: spec for spec in _literal_assignment("RESIZE_MATRIX_SPECS")}
    assert specs["resize-story-large"][3:5] == (940, 800)
    assert specs["resize-fertilizer-large"][3:5] == (940, 800)
    assert specs["resize-species-overview-large"][3:5] == (940, 800)
    assert specs["resize-fertilizer-replacement-large"][3:5] == (820, 535)
    assert not any("starter-confirmation" in label for label in specs)
    assert specs["resize-collection-minimum"][3:5] == (720, 500)
    assert specs["resize-collection-default"][3:5] == (1120, 800)
    assert specs["resize-collection-large"][3:5] == (1180, 880)




def test_responsive_pair_comparison_ignores_width_delta_but_not_state() -> None:
    functions = _compiled_functions(
        "responsive_semantic_maps",
        "responsive_stability_pair_issue_codes",
    )
    compare = functions["responsive_stability_pair_issue_codes"]
    low = [{
        "semantic_id": "settings.display-studio",
        "mode": "compact",
        "available_width": 699,
        "threshold_width": 760,
        "region_order": ["controls", "preview"],
    }]
    high = [{**low[0], "available_width": 701}]
    assert compare(low, high) == ()

    changed = [{**high[0], "mode": "wide"}]
    assert compare(low, changed) == (
        "semantic-state-mismatch:settings.display-studio",
    )


def test_conflicting_duplicate_responsive_semantic_ids_fail_closed() -> None:
    functions = _compiled_functions(
        "responsive_semantic_maps",
        "responsive_stability_pair_issue_codes",
    )
    semantic_maps = functions["responsive_semantic_maps"]
    entry = {
        "semantic_id": "dashboard.header-full",
        "mode": "wide",
        "available_width": 1200,
        "threshold_width": 998,
        "region_order": ["title", "metrics", "actions"],
    }
    _exact, _stable, conflicts = semantic_maps(
        [entry, {**entry, "available_width": 1180}]
    )
    assert conflicts == ("dashboard.header-full",)








def test_validator_recomputes_positive_scroll_geometry_and_page_identity() -> None:
    audit = {
        "applicable": True,
        "surface": "Collection",
        "expected_page_semantic": "GardenProgressDialog:collection",
        "actual_page_semantic": "GardenProgressDialog:collection",
        "scroll_name": "Collection scroll",
        "expected_scroll_name": "",
        "registered_count": 1,
        "active_count": 1,
        "footer_visible": True,
        "footer_height": 64,
        "footer_top": 400,
        "viewport_top": 100,
        "viewport_height": 300,
        "viewport_bottom": 400,
        "declared_clearance": 64,
        "layout_clearance": 64,
        "content_height": 720,
        "content_size_hint_height": 700,
        "content_minimum_size_hint_height": 680,
        "scroll_minimum": 0,
        "scroll_maximum": 420,
        "last_body_child_bottom": 720,
        "last_body_child_bottom_at_scroll_end": 400,
        "require_no_scroll": False,
        "required_content_height": 720,
        "reachable_content_height": 720,
        "issues": [],
        "passed": True,
    }
    assert dialog_scroll_audit_issue_codes(
        audit,
        expected_surface="Collection",
        expected_page_semantic="GardenProgressDialog:collection",
    ) == ()

    wrong_page = {**audit, "actual_page_semantic": "GardenProgressDialog:growth"}
    assert "actual-scroll-page-semantic-mismatch" in dialog_scroll_audit_issue_codes(
        wrong_page,
        expected_surface="Collection",
        expected_page_semantic="GardenProgressDialog:collection",
    )
    unreachable = {
        **audit,
        "scroll_maximum": 419,
        "reachable_content_height": 719,
    }
    assert "unreachable-scroll-content" in dialog_scroll_audit_issue_codes(
        unreachable,
    )


def test_progress_scroll_audit_proves_fixed_header_complete_fold_and_padding() -> None:
    audit = _valid_progress_scroll_audit()

    assert dialog_scroll_audit_issue_codes(
        audit,
        expected_surface="Garden Progress",
        expected_page_semantic="GardenProgressDialog:achievements",
    ) == ()


def test_progress_scroll_audit_rejects_large_gutter_and_missing_contracts() -> None:
    audit = {
        **_valid_progress_scroll_audit(),
        "fixed_progress_header": False,
        "complete_row_available_height": 570,
        "complete_row_bottom_gutter": 152,
        "complete_row_bottom_padding": 11,
    }

    issues = dialog_scroll_audit_issue_codes(audit)

    assert "missing-fixed-progress-header" in issues
    assert "excess-complete-row-gutter" in issues
    assert "insufficient-progress-bottom-padding" in issues


def test_home_and_vertical_settings_capture_bounds_match_the_release_layout() -> None:
    home_source = _method_source("_UiFaceCaptureRunner", "_wait_for_home_surface")
    settings_source = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_settings_display_advanced_ready",
    )
    module = _module()
    no_scroll_assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "CANONICAL_NO_SCROLL_CAPTURE_LABELS"
            for target in node.targets
        )
    )
    assert isinstance(no_scroll_assignment.value, ast.Call)
    no_scroll_labels = ast.literal_eval(no_scroll_assignment.value.args[0])

    assert "Math.round(homeActionRect.width) <= 128" in home_source
    assert "settings-display-advanced-open" in no_scroll_labels
    assert "scroll.ensureWidgetVisible(" not in settings_source
    assert "outer_vertical_range <= 1" in settings_source
    assert "outer_horizontal_range <= 1" in settings_source
    assert "inner_vertical_range <= 1" in settings_source
    assert "scroll.verticalScrollBar().setValue(0)" in settings_source

    starter_postcondition = _method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    assert "Plant in Bed" in starter_postcondition
    assert "Place in Bed" not in starter_postcondition


def test_loadout_first_fold_reserves_two_complete_native_tile_rows() -> None:
    dashboard_source = (ROOT / "ankigarden" / "ui" / "dashboard.py").read_text(
        "utf-8"
    )

    assert "self.option_tabs.setFixedHeight(304)" in dashboard_source
    assert "scroll.setFixedHeight(260)" in dashboard_source
