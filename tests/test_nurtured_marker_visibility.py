from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "ankigarden" / "ui" / "scene.py"
DASHBOARD_PATH = ROOT / "ankigarden" / "ui" / "dashboard.py"


def _class_method_node(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == method_name:
                return child
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _class_method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    node = _class_method_node(path, class_name, method_name)
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def _compiled_class_method(
    path: Path,
    class_name: str,
    method_name: str,
    namespace: dict[str, object] | None = None,
):
    node = _class_method_node(path, class_name, method_name)
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    scope: dict[str, object] = dict(namespace or {})
    exec(compile(module, str(path), "exec"), scope)
    return scope[method_name]


def test_native_scenes_do_not_compose_or_reserve_the_stored_marker() -> None:
    paint = _class_method_source(
        SCENE_PATH,
        "GardenSceneWidget",
        "paintEvent",
    )
    card_geometry = _class_method_source(
        SCENE_PATH,
        "GardenSceneWidget",
        "card_geometry",
    )

    assert "self._draw_nurtured_marker(" not in paint
    assert "self._nurtured_marker_placement = None" in paint
    assert "resolve_watering_can(" not in card_geometry


def test_native_accessibility_names_nurtured_state_without_a_visual_cue() -> None:
    update_description = _compiled_class_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "_update_scene_accessible_description",
    )
    scene = SimpleNamespace(
        scene={"plants": [{"name": "Briar", "is_active": True}]},
        interactive=False,
    )
    scene.setAccessibleDescription = lambda value: setattr(
        scene,
        "accessible_description",
        value,
    )

    update_description(scene)

    assert scene.accessible_description == (
        "This preview is not interactive. Briar is nurtured."
    )
    assert "Watering can" not in scene.accessible_description


def test_nurtured_badge_continues_to_display_the_stored_icon() -> None:
    rendered_icon = SimpleNamespace(isNull=lambda: False)
    resolved_assets: list[object] = []

    def render_icon(asset: object):
        resolved_assets.append(asset)
        return rendered_icon

    set_asset = _compiled_class_method(
        DASHBOARD_PATH,
        "NurturedPlantBadge",
        "set_asset",
        {
            "Any": Any,
            "_nurtured_badge_pixmap": render_icon,
        },
    )

    class Icon:
        visible = False
        pixmap: object | None = None

        def setVisible(self, visible: bool) -> None:
            self.visible = visible

        def setPixmap(self, pixmap: object) -> None:
            self.pixmap = pixmap

    badge = SimpleNamespace(icon=Icon())
    asset = object()

    set_asset(badge, asset)

    assert resolved_assets == [asset]
    assert badge.icon.visible is True
    assert badge.icon.pixmap is rendered_icon


def test_watering_can_assets_remain_manifest_backed_and_packaged() -> None:
    manifest = json.loads(
        (ROOT / "ankigarden" / "assets" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {
        str(row.get("asset_id")): row
        for row in manifest["assets"]
        if row.get("asset_id") in {
            "ui_nurtured_marker",
            "ui_nurtured_marker_spout_right",
        }
    }

    assert set(rows) == {
        "ui_nurtured_marker",
        "ui_nurtured_marker_spout_right",
    }
    for row in rows.values():
        assert (ROOT / "ankigarden" / str(row["file"])).is_file()
    assert (ROOT / "scripts" / "process_nurtured_marker_asset.py").is_file()
