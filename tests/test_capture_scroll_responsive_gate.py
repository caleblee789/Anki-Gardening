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
CAPTURE = ROOT / "ankigarden" / "capture_ui_faces.py"


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
    })
    capture_issues = check(**geometry)
    audit = {
        "applicable": True,
        "scroll_name": "Test scroll",
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
        "footer-clearance-mismatch",
        "footer-layout-clearance-mismatch",
        "footer-viewport-overlap",
    )


def test_dialog_scroll_audit_is_visible_owner_aware_and_fail_closed() -> None:
    source = _method_source("_UiFaceCaptureRunner", "_find_geometry_layout_warnings")
    assert "scroll.isVisibleTo(root)" in source
    assert "scroll.window() is not root" in source
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in source
    assert '"missing-active-vertical-scroll-region"' in source
    assert '"multiple-active-vertical-scroll-regions"' in source
    assert '"dialog-scroll-contract-audit-error"' in source
    assert "content.sizeHint().height()" in source
    assert "content.minimumSizeHint().height()" in source
    assert "viewport.mapTo(root" in source
    assert "footer.mapTo(root" in source
    assert 'scroll.property("footerClearance")' in source
    assert "visible_content_bottom" in source
    assert "descendant.isVisibleTo(content)" in source


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


def test_all_ten_scroll_surfaces_have_canonical_and_size_evidence() -> None:
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
        "Collection",
        "Collection loadout details",
    }
    groups = _literal_assignment("CAPTURE_FACE_GROUPS")
    contract = {
        label
        for _group, labels in groups
        for label in labels
    }
    flattened = [label for labels in coverage.values() for label in labels]
    assert set(semantics) == set(flattened)
    assert len(flattened) == len(set(flattened))
    for surface, labels in coverage.items():
        assert labels
        assert set(labels) <= contract
        assert any(not label.startswith("resize-") for label in labels)
        assert any(label.endswith("-minimum") for label in labels)
        assert any(label.endswith("-default") for label in labels)
        assert any(label.endswith("-large") for label in labels)
    assert coverage["Collection"] == (
        "progress-collection",
        "collection-several-discovered",
        "collection-no-filter-matches",
        "resize-collection-minimum",
        "resize-collection-default",
        "resize-collection-large",
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
    assert responsive_dialog_edges <= set(flattened)


def test_scroll_coverage_loader_rejects_ambiguous_surface_ownership(
    tmp_path: Path,
) -> None:
    source = CAPTURE.read_text("utf-8")
    ambiguous = source.replace(
        '    "Collection": (\n        "progress-collection",',
        '    "Collection": (\n        "resize-progress-minimum",\n'
        '        "progress-collection",',
        1,
    )
    changed = tmp_path / "ambiguous_capture_ui_faces.py"
    changed.write_text(ambiguous, encoding="utf-8")

    with pytest.raises(CaptureValidationError, match="multiple surfaces"):
        load_dialog_scroll_capture_coverage(changed)


def test_large_probes_use_semantic_growth_without_enlarging_starter() -> None:
    specs = {spec[0]: spec for spec in _literal_assignment("RESIZE_MATRIX_SPECS")}
    assert specs["resize-story-large"][3:5] == (900, 800)
    assert specs["resize-fertilizer-large"][3:5] == (900, 800)
    assert specs["resize-species-overview-large"][3:5] == (900, 800)
    assert specs["resize-fertilizer-replacement-large"][3:5] == (820, 660)
    assert specs["resize-starter-confirmation-large"][3:5] == (520, 360)
    assert specs["resize-collection-minimum"][3:5] == (720, 500)
    assert specs["resize-collection-default"][3:5] == (940, 680)
    assert specs["resize-collection-large"][3:5] == (1000, 820)


def test_resize_and_footer_stress_fixtures_reset_deferred_ui_state() -> None:
    resize = _method_source("_UiFaceCaptureRunner", "_capture_resize_matrix_face")
    final_row = _method_source("_UiFaceCaptureRunner", "_capture_nursery_final_row")

    prepare_position = resize.index("prepare()")
    tab_position = resize.index("option_tabs.setCurrentIndex(0)", prepare_position)
    capture_position = resize.index("capture_widget(detail, close=True)", tab_position)
    assert prepare_position < tab_position < capture_position

    capture_ready = final_row.split("def capture_ready()", 1)[1]
    audit_position = capture_ready.index("self._audit_nursery_action_above_footer")
    before_audit = capture_ready[:audit_position]
    assert before_audit.count("scrollbar.setValue(scrollbar.maximum())") == 2
    assert "QApplication.processEvents()" in before_audit


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


def test_capture_records_visible_semantics_and_finishes_all_stability_pairs() -> None:
    capture = _method_source("_UiFaceCaptureRunner", "_capture_now")
    telemetry = _method_source("_UiFaceCaptureRunner", "_responsive_semantic_telemetry")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")
    report = _method_source("_UiFaceCaptureRunner", "_responsive_stability_report")
    pairs = _literal_assignment("RESPONSIVE_STABILITY_PAIRS")

    assert len(pairs) == 13
    assert '"responsive_semantics": responsive_semantics' in capture
    for property_name in (
        "responsiveRegion",
        "responsiveMode",
        "responsiveAvailableWidth",
        "responsiveThreshold",
        "responsiveRegionOrder",
    ):
        assert property_name in telemetry
    assert "candidate.isVisibleTo(root)" in telemetry
    assert "candidate.window() is not root" in telemetry
    assert '"conflicting-responsive-semantic-id"' in telemetry
    assert "RESPONSIVE_STABILITY_PAIRS" in report
    assert "responsive_stability_pair_issue_codes" in report
    assert "and responsive_stability_complete" in finish
    assert '"responsive_stability_complete": responsive_stability_complete' in finish


def test_capture_finish_requires_positive_scroll_metrics_and_surface_identity() -> None:
    capture = _method_source("_UiFaceCaptureRunner", "_capture_now")
    report = _method_source("_UiFaceCaptureRunner", "_dialog_scroll_coverage_report")
    finish = _method_source("_UiFaceCaptureRunner", "_finish")

    assert '"dialog_scroll_audit": dialog_scroll_audit' in capture
    assert "DIALOG_SCROLL_CAPTURE_COVERAGE" in report
    assert "DIALOG_SCROLL_CAPTURE_SEMANTICS" in report
    assert "scroll-fixture-identity-not-proven" in report
    assert "dialog_scroll_geometry_issue_codes" in report
    for metric in (
        "registered_count",
        "active_count",
        "footer_height",
        "viewport_height",
        "declared_clearance",
        "layout_clearance",
        "required_content_height",
        "reachable_content_height",
    ):
        assert metric in report
    assert "and dialog_scroll_audits_complete" in finish
    assert '"dialog_scroll_audits_complete": dialog_scroll_audits_complete' in finish


def test_capture_scroll_summary_uses_the_same_laid_out_reachability_rule() -> None:
    report = _method_source("_UiFaceCaptureRunner", "_dialog_scroll_coverage_report")
    required_block = report.split("required = max(", 1)[1].split(
        "reachable =",
        1,
    )[0]

    assert 'audit["content_height"]' in required_block
    assert 'audit["content_minimum_size_hint_height"]' in required_block
    assert 'audit["content_size_hint_height"]' not in required_block


def test_validator_recomputes_positive_scroll_geometry_and_page_identity() -> None:
    audit = {
        "applicable": True,
        "surface": "Collection",
        "expected_page_semantic": "GardenProgressDialog:collection",
        "actual_page_semantic": "GardenProgressDialog:collection",
        "scroll_name": "Collection scroll",
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

    wrong_page = {**audit, "actual_page_semantic": "GardenProgressDialog:overview"}
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
