from __future__ import annotations

from ankigarden.ui.formatters import format_plant_name

import ast
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


def _compiled_class_method(
    path: Path,
    class_name: str,
    method_name: str,
    namespace: dict[str, object] | None = None,
):
    node = _class_method_node(path, class_name, method_name)
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    scope: dict[str, object] = {"format_plant_name": format_plant_name, **(namespace or {})}
    exec(compile(module, str(path), "exec"), scope)
    return scope[method_name]


def test_native_accessibility_names_nurtured_state_without_a_visual_cue() -> None:
    update_description = _compiled_class_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "_update_scene_accessible_description",
    )
    scene = SimpleNamespace(
        scene={"plants": [{"name": "Briar", "species": "rose", "stage": "young", "is_active": True}]},
        interactive=False,
    )
    scene.setAccessibleDescription = lambda value: setattr(
        scene,
        "accessible_description",
        value,
    )

    update_description(scene)

    assert scene.accessible_description == (
        "This preview is not interactive. Young Rose is nurtured."
    )
    assert "Watering can" not in scene.accessible_description


def test_nurtured_badge_ignores_the_retired_stored_marker_icon() -> None:
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

    assert resolved_assets == []
    assert badge.icon.visible is False
    assert badge.icon.pixmap is None
