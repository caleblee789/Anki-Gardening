from __future__ import annotations

import ast
from pathlib import Path

from ankigarden.ui.plant_display import PlantInteractionState


SCENE_PATH = Path(__file__).resolve().parents[1] / "ankigarden/ui/scene.py"
SCENE_SOURCE = SCENE_PATH.read_text()
SCENE_TREE = ast.parse(SCENE_SOURCE)


def _method_source(name: str) -> str:
    scene_class = next(
        node
        for node in SCENE_TREE.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenSceneWidget"
    )
    method = next(
        node
        for node in scene_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    return ast.get_source_segment(SCENE_SOURCE, method) or ""


def test_finish_move_is_public_complete_and_does_not_request_cancel() -> None:
    block = _method_source("finish_move")

    assert "self._interaction.cancel_placement()" in block
    for transient in (
        "self._allowed_move_slots = None",
        "self._press_position = None",
        "self._press_plant_id = None",
        "self._drag_started = False",
        "self._drag_position = None",
    ):
        assert transient in block
    assert "self._clear_hit_targets()" in block
    assert "self._finish_move_accessibility(" in block
    assert "self.placementStateChanged.emit(False)" in block
    assert "self.cancelPlacementRequested.emit()" not in block


def test_cancel_move_wraps_finish_then_notifies_dashboard_once() -> None:
    block = _method_source("cancel_move")

    assert block.count("self.finish_move(") == 1
    assert block.count("self.cancelPlacementRequested.emit()") == 1
    assert block.index("self.finish_move(") < block.index("self.cancelPlacementRequested.emit()")


def test_mouse_origin_cancels_but_empty_scene_keeps_the_dashboard_draft() -> None:
    block = _method_source("mousePressEvent")
    valid_slots = _method_source("_valid_slots")

    origin_branch = block.split("if slot == self._interaction.drag_origin_slot:", 1)[1]
    assert origin_branch.lstrip().startswith("self.cancel_move()")
    outside_branch = block.split("# Clicking outside a destination", 1)[1].split(
        "plant_id = self._plant_at(position)", 1
    )[0]
    assert "self.cancel_move()" not in outside_branch
    assert "Choose a highlighted garden space, or press Escape to cancel." in outside_branch
    assert "list(range(unlocked))" in valid_slots
    assert "sorted(self._slot_placements)" not in valid_slots


def test_keyboard_confirmation_on_origin_follows_cancel_path() -> None:
    block = _method_source("keyPressEvent")
    confirmation = block.split(
        "elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):",
        1,
    )[1].split("elif event.key() == Qt.Key.Key_Escape:", 1)[0]

    assert "origin = self._interaction.drag_origin_slot" in confirmation
    assert "request[1] != origin" in confirmation
    assert "else:\n                    self.cancel_move()" in confirmation

    state = PlantInteractionState()
    assert state.begin_placement("rose", 0, [0, 1], keyboard=True)
    origin_request = state.complete_placement()
    assert origin_request == ("rose", 0)
    assert origin_request[1] == 0
