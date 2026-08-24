from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "ankigarden" / "ui" / "dashboard.py"
CAPTURE = ROOT / "ankigarden" / "capture_ui_faces.py"


def _method_source(class_name: str, method_name: str) -> str:
    source = DASHBOARD.read_text("utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    return ast.get_source_segment(source, method) or ""


def test_collection_no_matches_keeps_one_filter_action_and_sparse_profile() -> None:
    refresh = _method_source("GardenDashboard", "_refresh_collection_list")
    page_changed = _method_source("GardenProgressDialog", "_page_changed")
    profile = _method_source("GardenProgressDialog", "_view_profile_for_page")
    capture = CAPTURE.read_text("utf-8")

    assert "action=clear_filters" not in refresh
    assert 'self.collection_list.setProperty("emptyResult", is_empty)' in refresh
    assert "progress_dialog._view_profile_for_page" in refresh
    assert "self._view_profile_for_page(str(key))" in page_changed
    assert '"collection-empty"' in profile
    assert 'annotation.get("empty_state_actions") == []' in capture
    assert 'annotation.get("filter_clear_visible", False)' in capture
