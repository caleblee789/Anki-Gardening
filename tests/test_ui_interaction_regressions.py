from __future__ import annotations

import ast
import json
import re
import textwrap
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ankigarden.game import GardenGameEngine
from ankigarden.models.state import GardenState, Plant, PlantMemory
from ankigarden.ui.home_widget import HomeWidgetData, HomeWidgetSnapshot, render_home_widget
from ankigarden.ui.plant_display import (
    PlantInteractionState,
    Rect,
    bed_badge_rect,
    chronological_memories,
    move_badge_label,
    move_target_state,
    plant_layout,
    story_is_just_beginning,
)


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "ankigarden/addon.py"
DASHBOARD_PATH = ROOT / "ankigarden/ui/dashboard.py"
SCENE_PATH = ROOT / "ankigarden/ui/scene.py"
STUDIO_PATH = ROOT / "ankigarden/ui/garden_studio.py"
GAME_PATH = ROOT / "ankigarden/game.py"


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text("utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    )
    return ast.get_source_segment(source, method) or ""


def _compiled_method(
    path: Path,
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    scope: dict[str, Any] = {"Any": Any}
    scope.update(namespace or {})
    exec(textwrap.dedent(_method_source(path, class_name, method_name)), scope)
    return scope[method_name]


def _home_data(**overrides: Any) -> HomeWidgetData:
    values = {
        "reviews_today": 3,
        "growth_earned": 30,
        "base_growth": 30,
        "streak_bonus_growth": 0,
        "fertilizer_growth": 0,
        "bonus_growth": 0,
        "all_due_completed": False,
        "streak_days": 1,
        "streak_bonus_percent": 0,
        "next_streak_day": 7,
        "next_streak_bonus_percent": 5,
        "garden_currency": 0,
        "weather": "breeze",
    }
    values.update(overrides)
    return HomeWidgetData(**values)


def test_transient_home_states_retain_a_stable_minimum_height() -> None:
    for phase in ("loading", "empty", "error"):
        html = render_home_widget(
            HomeWidgetSnapshot(1, phase, error_message="Temporary problem")
        )
        state_rule = html.split(".ag-home__state {", 1)[1].split("}", 1)[0]
        assert "min-height: 160px" in state_rule
        assert 'class="ag-home__state"' in html


def test_home_preview_has_one_explicit_action_and_a_keyboard_clickable_card() -> None:
    html = render_home_widget(HomeWidgetSnapshot(1, "success", _home_data()))

    assert 'data-tooltip=' not in html
    assert 'role="button" tabindex="0"' in html
    assert 'role="tooltip"' not in html
    assert html.count("onclick=") == 2
    assert "event.key==='Enter'||event.key===' '" in html
    assert html.count('data-testid="home-open"') == 1
    assert 'data-testid="home-scene" aria-hidden="true"' in html


def test_interaction_matrix_covers_modal_keyboard_swap_rollback_and_house_route() -> None:
    dashboard = DASHBOARD_PATH.read_text("utf-8")
    scene = SCENE_PATH.read_text("utf-8")
    game = GAME_PATH.read_text("utf-8")
    manifest = json.loads((ROOT / "ankigarden/assets/manifest.json").read_text("utf-8"))

    shield = _method_source(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_set_onboarding_shield",
    )
    focus_trap = _method_source(
        DASHBOARD_PATH,
        "GardenDashboard",
        "focusNextPrevChild",
    )
    assert "self.onboarding_shield.raise_()" in shield
    assert "self.onboarding_panel.raise_()" in shield
    assert "self.onboarding_action" in focus_trap
    assert "self.dismiss_onboarding" in focus_trap

    interaction = PlantInteractionState()
    assert interaction.cycle_focus(["left", "right"], 1) == "left"
    interaction.toggle_pin("left")
    assert interaction.pinned_id == "left"
    assert "_spatial_destination(event.key())" in scene

    place = _method_source(DASHBOARD_PATH, "GardenDashboard", "_place_plant")
    failed = _method_source(DASHBOARD_PATH, "GardenDashboard", "_finish_failed_move")
    assert "occupant" in place and "swapped" in place
    assert place.index("stage_placement") < place.index("commit_placement_draft")
    assert "_persist_or_restore(snapshot)" in game
    assert "self.refresh_all()" in failed
    assert "begin_placement_draft" in failed
    assert "error=True" in failed

    background = next(
        row for row in manifest["assets"]
        if row.get("category") == "backgrounds" and row.get("release_preferred") is True
    )
    house = next(
        row for row in background["placement"]["surface_profile"]["landmarks"]
        if row.get("landmark_id") == "garden_house"
    )
    open_collection = _method_source(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_open_collection",
    )
    assert house["action_id"] == "garden.collection.open"
    assert '"garden.collection.open": self._open_collection' in dashboard
    assert "self.progress_dialog.open_page(\"collection\")" in open_collection
    assert "self._collection_activation_pending" in open_collection


def test_six_plant_home_scene_keeps_each_depth_band_between_planter_layers() -> None:
    manifest = json.loads((ROOT / "ankigarden/assets/manifest.json").read_text("utf-8"))
    background = next(
        row for row in manifest["assets"]
        if row.get("category") == "backgrounds" and row.get("release_preferred") is True
    )
    plant_asset = next(
        row for row in manifest["assets"]
        if row.get("category") == "plants"
        and row.get("release_preferred") is True
        and "continuity_v6" in row.get("variants", [])
    )
    background_placement = deepcopy(background["placement"])
    for variant in background_placement["surface_profile"]["variants"].values():
        variant["url"] = "/background.png"
        variant["occlusion_layer_urls"] = {
            "rear": "/rear-occlusion.png",
            "front": "/front-occlusion.png",
        }
    for name, variant in background_placement["surface_profile"]["planter_family"]["variants"].items():
        variant["url"] = f"/{name}-planter.png"
        variant["foreground_url"] = f"/{name}-planter-foreground.png"
    plants = tuple(
        {
            "plant_id": f"plant-{slot}",
            "slot_index": slot,
            "name": f"Plant {slot + 1}",
            "species": "rose",
            "stage": "seed",
            "url": "/plant.png",
            "placement": plant_asset["placement"],
            "background_placement": background_placement,
        }
        for slot in range(6)
    )
    html = render_home_widget(
        HomeWidgetSnapshot(
            1,
            "success",
            _home_data(scene_items=plants, unlocked_slots=6, collection_count=6),
        )
    )
    art = html.split('data-testid="home-plants">', 1)[1].split("</div>\n    </div>", 1)[0]
    layers = [
        (kind, int(z_index))
        for kind, z_index in re.findall(
            r'<img class="ag-home__(planter|plant)[^>]*?z-index:(\d+)', art
        )
    ]

    assert [kind for kind, _z in layers] == [
        "planter", "planter", "plant", "plant", "planter", "planter",
        "planter", "planter", "plant", "plant", "planter", "planter",
        "planter", "planter", "plant", "plant", "planter", "planter",
    ]
    assert [z for kind, z in layers if kind == "plant"] == [11, 14, 41, 44, 71, 74]
    assert [z for kind, z in layers if kind == "planter"] == [
        4, 4, 28, 28,
        34, 34, 58, 58,
        64, 64, 88, 88,
    ]
    assert "occlusion" not in art


class _FakePainter:
    def __init__(self) -> None:
        self.ellipses: list[Any] = []
        self.badges: list[Any] = []
        self.labels: list[str] = []

    def save(self) -> None:
        return None

    def restore(self) -> None:
        return None

    def setPen(self, _pen: Any) -> None:
        return None

    def setBrush(self, _brush: Any) -> None:
        return None

    def drawEllipse(self, rect: Any) -> None:
        self.ellipses.append(rect)

    def drawRoundedRect(self, rect: Any, _x: float, _y: float) -> None:
        self.badges.append(rect)

    def drawText(self, _rect: Any, _alignment: Any, text: str) -> None:
        self.labels.append(text)

    def font(self) -> Any:
        return _FakeFont()

    def setFont(self, _font: Any) -> None:
        return None


class _FakeFont:
    def __init__(self) -> None:
        self._size = 12.0

    def pointSizeF(self) -> float:
        return self._size

    def setPointSizeF(self, value: float) -> None:
        self._size = value

    def setBold(self, _value: bool) -> None:
        return None


class _FakeRectF:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height

    def adjusted(self, left: float, top: float, right: float, bottom: float) -> "_FakeRectF":
        return _FakeRectF(
            self.x + left,
            self.y + top,
            self.width + right - left,
            self.height + bottom - top,
        )


class _FakeColor:
    def __init__(self, *_args: Any) -> None:
        pass

    def setAlpha(self, _value: int) -> None:
        return None


class _FakePen:
    def __init__(self, *_args: Any) -> None:
        pass


def test_compact_move_mode_paints_only_current_and_valid_destination_rings() -> None:
    draw_slots = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "_draw_slot_placeholders",
        {
            "QPainter": object,
            "QRectF": _FakeRectF,
            "QColor": _FakeColor,
            "QPen": _FakePen,
            "Qt": SimpleNamespace(AlignmentFlag=SimpleNamespace(AlignCenter=0)),
            "move_badge_label": move_badge_label,
            "move_target_state": move_target_state,
            "bed_badge_rect": bed_badge_rect,
            "GARDEN_THEME": {
                "action_hover": "#4AAE7B",
                "action_accent": "#329967",
            },
        },
    )
    placements = plant_layout(480, 320, 6)
    plants = [{"plant_id": "p0", "slot_index": 0, "name": "Briar"}]
    interaction = PlantInteractionState()
    assert interaction.begin_placement("p0", 0, [0, 1], keyboard=True)
    scene = SimpleNamespace(
        _interaction=interaction,
        scene={"plants": plants, "unlocked_slots": 2},
        _slot_placements={row.slot_index: row for row in placements},
        _hovered_move_slot=None,
        _destination_slots=lambda: [1],
        width=lambda: 480,
        height=lambda: 320,
        _layout_plants=lambda _width, _height: list(zip(plants, placements[:1])),
    )
    painter = _FakePainter()

    draw_slots(scene, painter)

    # Locked spaces remain pure background; only the current and valid target
    # rings appear, with one short label for the current location.
    assert len(painter.ellipses) == 2
    assert len(painter.badges) == 1
    assert painter.labels.count("+") == 1
    assert "Current" in painter.labels

    scene._hovered_move_slot = 4
    painter = _FakePainter()
    draw_slots(scene, painter)

    # A locked target becomes visible only while it is directly relevant.
    assert len(painter.ellipses) == 3
    assert len(painter.badges) == 2
    assert painter.labels.count("+") == 1
    assert "Current" in painter.labels
    assert "Locked" in painter.labels

    scene._hovered_move_slot = 1
    painter = _FakePainter()
    draw_slots(scene, painter)

    assert len(painter.ellipses) == 2
    assert len(painter.badges) == 2
    assert painter.labels.count("+") == 1
    assert "Current" in painter.labels
    assert "Move" in painter.labels


def test_selected_card_geometry_protects_selected_plant_and_can_request_dock() -> None:
    source = _method_source(
        SCENE_PATH,
        "GardenSceneWidget",
        "card_geometry",
    )
    assert "marker_reservation = geometry_layout.resolve_watering_can(" in source
    assert "marker_reservation.pulse_bounds.expanded(4.0, 4.0)" in source
    captured: list[tuple[list[Rect], Rect | None]] = []

    def no_clear_geometry(
        _width: float,
        _height: float,
        _anchor_x: float,
        _anchor_y: float,
        **kwargs: Any,
    ) -> None:
        captured.append((list(kwargs["obstacles"]), kwargs["protected_obstacle"]))
        return None

    card_geometry = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "card_geometry",
        {
            "QRectF": _FakeRectF,
            "Rect": Rect,
            "smart_card_rect": no_clear_geometry,
        },
    )

    class Hit:
        def __init__(self, x: float, y: float, width: float, height: float) -> None:
            self._values = (x, y, width, height)

        def x(self) -> float:
            return self._values[0]

        def y(self) -> float:
            return self._values[1]

        def width(self) -> float:
            return self._values[2]

        def height(self) -> float:
            return self._values[3]

    scene = SimpleNamespace(
        _interaction=SimpleNamespace(pinned_id="selected", placing=False),
        _layout_plants=lambda _width, _height: [],
        _plant_anchors={"selected": (200.0, 160.0)},
        _plant_hit_rects={
            "selected": Hit(100, 100, 80, 120),
            "neighbor": Hit(250, 120, 90, 110),
        },
        _status_rect=None,
        width=lambda: 620,
        height=lambda: 426,
    )

    assert card_geometry(scene, 360, 220) is None
    assert len(captured) == 1
    obstacles, protected = captured[0]
    assert obstacles == [Rect(242, 112, 106, 126)]
    assert protected == Rect(92, 92, 96, 136)


def test_move_pointer_feedback_uses_target_state_and_skips_plant_hover() -> None:
    mouse_move = _method_source(SCENE_PATH, "GardenSceneWidget", "mouseMoveEvent")
    release = _method_source(SCENE_PATH, "GardenSceneWidget", "mouseReleaseEvent")

    assert 'if target_state in {"valid", "current"}' in mouse_move
    assert "Qt.CursorShape.PointingHandCursor" in mouse_move
    assert 'elif target_state in {"locked", "unavailable"}' in mouse_move
    assert "Qt.CursorShape.ForbiddenCursor" in mouse_move
    assert mouse_move.index("super().mouseMoveEvent(event)\n            return") < mouse_move.index(
        "plant_id = self._plant_at(position)"
    )
    assert "request = self._interaction.complete_placement() if valid else None" in release


class _Signal:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def emit(self, *values: Any) -> None:
        self.values.append(values)


class _ToolTip:
    hide_count = 0

    @classmethod
    def hideText(cls) -> None:
        cls.hide_count += 1


def _move_scene() -> Any:
    finish_move = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "finish_move",
        {"QToolTip": _ToolTip},
    )
    cancel_move = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "cancel_move",
    )
    interaction = PlantInteractionState()
    assert interaction.begin_placement("p0", 0, [0, 1], keyboard=True)
    scene = SimpleNamespace(
        _interaction=interaction,
        _allowed_move_slots={0, 1},
        _press_position=object(),
        _press_plant_id="p0",
        _drag_started=True,
        _drag_position=object(),
        _inline_message="Moving",
        placementStateChanged=_Signal(),
        cancelPlacementRequested=_Signal(),
        _clear_hit_targets=lambda: setattr(scene, "cleared_hit_targets", True),
        unsetCursor=lambda: setattr(scene, "cursor_unset", True),
        _finish_move_accessibility=lambda message: setattr(scene, "announcement", message),
        update=lambda: setattr(scene, "updated", True),
    )
    scene.finish_move = lambda message="": finish_move(scene, message)
    scene.cancel_move = lambda: cancel_move(scene)
    return scene


def test_mouse_and_keyboard_origin_activation_use_complete_cancel_teardown() -> None:
    class MouseButton:
        LeftButton = "left"

    class Key:
        Key_Tab = "tab"
        Key_Backtab = "backtab"
        Key_Left = "left"
        Key_Up = "up"
        Key_Right = "right"
        Key_Down = "down"
        Key_Return = "return"
        Key_Enter = "enter"
        Key_Space = "space"
        Key_Escape = "escape"

    fake_qt = SimpleNamespace(MouseButton=MouseButton, Key=Key)
    mouse_press = _compiled_method(
        SCENE_PATH, "GardenSceneWidget", "mousePressEvent", {"Qt": fake_qt}
    )
    key_press = _compiled_method(
        SCENE_PATH, "GardenSceneWidget", "keyPressEvent", {"Qt": fake_qt}
    )

    mouse_scene = _move_scene()
    mouse_scene.interactive = True
    mouse_scene._drag_started = False
    mouse_scene._event_position = lambda event: event.position()
    mouse_scene._slot_at = lambda _position: 0
    mouse_event = SimpleNamespace(button=lambda: "left", position=lambda: object())
    mouse_press(mouse_scene, mouse_event)

    assert not mouse_scene._interaction.placing
    assert mouse_scene._allowed_move_slots is None
    assert mouse_scene.cancelPlacementRequested.values == [()]
    assert mouse_scene.placementStateChanged.values[-1] == (False,)

    keyboard_scene = _move_scene()
    keyboard_scene.interactive = True
    keyboard_scene._plant_ids = lambda: ["p0"]
    keyboard_event = SimpleNamespace(key=lambda: "return")
    key_press(keyboard_scene, keyboard_event)

    assert not keyboard_scene._interaction.placing
    assert keyboard_scene._allowed_move_slots is None
    assert keyboard_scene.cancelPlacementRequested.values == [()]
    assert keyboard_scene.placementStateChanged.values[-1] == (False,)


def test_focused_plant_accessibility_names_the_plant_and_available_actions() -> None:
    announce = _compiled_method(
        SCENE_PATH, "GardenSceneWidget", "_announce_focused_plant"
    )
    interaction = PlantInteractionState()
    interaction.focused_index = 0
    scene = SimpleNamespace(
        _interaction=interaction,
        scene={"plants": [{
            "plant_id": "p0",
            "name": "Briar",
            "species": "japanese_maple",
            "stage": "young",
        }]},
        _plant_ids=lambda: ["p0"],
        setAccessibleName=lambda value: setattr(scene, "accessible_name", value),
        setAccessibleDescription=lambda value: setattr(scene, "accessible_description", value),
    )

    announce(scene)
    assert scene.accessible_name == "Garden plant: Briar"
    assert scene.accessible_description == (
        "Focused plant: Briar, Japanese Maple, Young. "
        "Press Enter to select it, or use the arrow keys to explore. "
        "Use the arrow keys to explore plants. Press Enter to open the selected item."
    )

    announce(scene, selected=True)
    assert "Briar, Japanese Maple, Young, selected" in scene.accessible_description
    assert "Nurture, Fertilize, Move, and Story" in scene.accessible_description


def test_story_memory_order_survives_state_round_trip_on_the_same_day() -> None:
    plant = Plant(
        "p0",
        "rose",
        "Briar",
        0,
        memories=[
            PlantMemory("planted", "planted", "2026-08-08"),
            PlantMemory("nurture:first", "first_nurture", "2026-08-08"),
            PlantMemory("reviews:10", "reviews", "2026-08-07", value=10),
        ],
    )
    restored = GardenState.from_dict(
        GardenState(plants=[plant], active_plant_id="p0").to_dict()
    )
    memories = chronological_memories(restored.plants[0].memories)

    assert [memory.memory_id for memory in memories] == [
        "reviews:10", "planted", "nurture:first",
    ]
    assert story_is_just_beginning(memories) is False
    assert story_is_just_beginning([PlantMemory("planted", "planted", "2026-08-08")]) is True


def test_story_escape_cancels_rename_and_restores_focus_to_edit_button() -> None:
    class Timer:
        @staticmethod
        def singleShot(_delay: int, callback: Any) -> None:
            callback()

    set_editing = _compiled_method(
        DASHBOARD_PATH, "PlantStoryDialog", "_set_editing", {"QTimer": Timer}
    )
    cancel = _compiled_method(
        DASHBOARD_PATH, "PlantStoryDialog", "_cancel_rename"
    )
    calls: list[tuple[str, Any]] = []

    class Widget:
        def setVisible(self, value: bool) -> None:
            calls.append(("visible", value))

        def setFocus(self) -> None:
            calls.append(("focus", True))

        def selectAll(self) -> None:
            calls.append(("select", True))

        def setText(self, value: str) -> None:
            calls.append(("text", value))

        def setAccessibleDescription(self, value: str) -> None:
            calls.append(("description", value))

        def hide(self) -> None:
            calls.append(("hide", True))

    story = SimpleNamespace(
        name_heading=Widget(),
        name_edit=Widget(),
        save_name_btn=Widget(),
        cancel_name_btn=Widget(),
        edit_name_btn=Widget(),
        feedback=Widget(),
    )
    story._set_editing = lambda editing, restore_focus=False: set_editing(
        story, editing, restore_focus=restore_focus
    )

    cancel(story)

    assert ("description", "") in calls
    assert calls[-1] == ("focus", True)
    key_source = _method_source(DASHBOARD_PATH, "PlantStoryDialog", "keyPressEvent")
    assert "self.name_edit.isVisible()" in key_source
    assert "event.key() == Qt.Key.Key_Escape" in key_source
    assert key_source.index("self._cancel_rename()") < key_source.index("event.accept()")


def test_settings_snapshot_and_preview_resolver_keep_real_weather_plants_and_slots() -> None:
    snapshot = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_settings_scene_snapshot",
        {"growth_display": lambda _points: SimpleNamespace(progress=0.37)},
    )
    active = SimpleNamespace(growth_points=2_700)
    state = SimpleNamespace(
        selected_weather="gentle_rain",
        unlocked_slots=5,
        streak_days=14,
        active_plant_id="p1",
        plants=[
            SimpleNamespace(
                plant_id="p0", slot_index=4, name="Maple", species="japanese_maple",
                growth_stage="flowering", growth_points=21_000,
            ),
            SimpleNamespace(
                plant_id="p1", slot_index=1, name="Briar", species="rose",
                growth_stage="sprout", growth_points=650,
            ),
            SimpleNamespace(
                plant_id="shelved", slot_index=None, name="Shelf", species="bonsai",
                growth_stage="seed", growth_points=0,
            ),
        ],
    )
    dashboard = SimpleNamespace(
        storage=SimpleNamespace(state=state),
        engine=SimpleNamespace(
            active_plant=lambda: active,
            current_streak_bonus_percent=lambda: 10,
        ),
    )

    payload = snapshot(dashboard)

    assert payload["weather"] == "gentle_rain"
    assert payload["unlocked_slots"] == 5
    assert payload["growth"] == 0.37
    assert payload["streak_days"] == 14
    assert [(row["species"], row["stage"], row["slot_index"]) for row in payload["plants"]] == [
        ("japanese_maple", "flowering", 4),
        ("rose", "sprout", 1),
    ]

    class Asset:
        def __init__(self, key: str) -> None:
            self.key = key

        def to_payload(self) -> dict[str, str]:
            return {"key": self.key}

    class Assets:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def normalize_theme(self, theme: str) -> str:
            return theme

        def resolve(self, category: str, key: str, _slot: str, **_kwargs: Any) -> Asset:
            self.calls.append((category, key, str(_kwargs.get("quality_preference", ""))))
            return Asset(key)

    assets = Assets()
    engine = SimpleNamespace(
        assets=assets,
        seasonal_theme=lambda: "summer",
        local_time_band=lambda: "dusk",
        resolve_garden_overlay_asset=lambda **_kwargs: Asset("garden-overlay"),
        resolve_nurtured_marker_assets=lambda: {
            "spout_left": Asset("nurtured-marker"),
            "spout_right": Asset("nurtured-marker-spout-right"),
        },
    )
    resolved = GardenGameEngine.resolve_preview_assets(
        engine,
        "verdant_twilight",
        payload["weather"],
        "seed",
        "ultra",
        payload["plants"],
    )

    assert resolved["plants"]["japanese_maple"] == {
        "key": "japanese_maple_flowering"
    }
    assert resolved["plants"]["rose"] == {"key": "rose_sprout"}
    assert resolved["nurtured_marker"] == {"key": "nurtured-marker"}
    assert resolved["nurtured_marker_spout_right"] == {
        "key": "nurtured-marker-spout-right"
    }
    assert ("backgrounds", "bg_default_any", "balanced") in assets.calls
    assert ("weather", "weather_gentle_rain", "balanced") in assets.calls

    apply_preview = _method_source(STUDIO_PATH, "GardenStudioWidget", "_apply_preview")
    assert "preview_weather" in apply_preview
    assert "real_plants" in apply_preview
    assert '"unlocked_slots": int(snapshot.get("unlocked_slots", 6) or 6)' in apply_preview
    assert '"show_status_overlay": False' in apply_preview


def test_watering_can_is_shared_by_full_garden_and_native_previews() -> None:
    customize_preview = _method_source(
        DASHBOARD_PATH,
        "CustomizeGardenDialog",
        "_refresh_preview",
    )
    full_garden_refresh = _method_source(
        DASHBOARD_PATH,
        "GardenDashboard",
        "refresh_all",
    )
    settings_preview = _method_source(
        STUDIO_PATH,
        "GardenStudioWidget",
        "_apply_preview",
    )

    for source in (customize_preview, settings_preview, full_garden_refresh):
        assert '"nurtured_marker"' in source
        assert '"nurtured_marker_spout_right"' in source


def test_deck_browser_and_overview_previews_receive_watering_can_url() -> None:
    home_builder = _method_source(
        ADDON_PATH,
        "AnkiGardenApp",
        "_build_home_garden_html",
    )
    home_resolver = _method_source(
        ADDON_PATH,
        "AnkiGardenApp",
        "_home_nurtured_marker_url",
    )
    home_right_resolver = _method_source(
        ADDON_PATH,
        "AnkiGardenApp",
        "_home_nurtured_marker_spout_right_url",
    )

    assert "nurtured_marker_url=self._home_nurtured_marker_url()" in home_builder
    assert "nurtured_marker_spout_right_url=(" in home_builder
    assert "self._home_nurtured_marker_spout_right_url()" in home_builder
    assert '"resolve_nurtured_marker_asset"' in home_resolver
    assert "resolve_nurtured_marker_image" in home_resolver
    assert '"resolve_nurtured_marker_spout_right_asset"' in home_right_resolver
    assert "resolve_nurtured_marker_spout_right_image" in home_right_resolver


def test_native_watering_can_description_explains_future_growth_routing() -> None:
    accessible = _method_source(
        SCENE_PATH,
        "GardenSceneWidget",
        "_update_scene_accessible_description",
    )
    set_scene = _method_source(SCENE_PATH, "GardenSceneWidget", "set_scene")
    set_interactive = _method_source(
        SCENE_PATH,
        "GardenSceneWidget",
        "set_interactive",
    )

    assert (
        "Watering can: {name} is nurtured and receives Growth from future Anki card answers."
        in accessible
    )
    assert "_update_scene_accessible_description()" in set_scene
    assert "_update_scene_accessible_description()" in set_interactive


def test_visible_settings_are_raised_without_resetting_staged_controls() -> None:
    open_settings = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_open_settings",
        {"GardenSettingsDialog": object},
    )

    class Settings:
        def __init__(self, visible: bool) -> None:
            self.visible = visible
            self.calls: list[str] = []

        def isVisible(self) -> bool:
            return self.visible

        def raise_(self) -> None:
            self.calls.append("raise")

        def prepare_to_show(self) -> None:
            self.calls.append("prepare")

        def present_over_parent(self) -> None:
            self.calls.append("present")

    visible = Settings(True)
    open_settings(SimpleNamespace(settings_dialog=visible, engine=object(), config=object()))
    assert visible.calls == ["raise"]

    hidden = Settings(False)
    open_settings(SimpleNamespace(settings_dialog=hidden, engine=object(), config=object()))
    assert hidden.calls == ["prepare", "present"]


def test_nursery_bed_purchase_guard_blocks_double_activation_and_recovers() -> None:
    class Timer:
        callbacks: list[Any] = []

        @classmethod
        def singleShot(cls, _delay: int, callback: Any) -> None:
            cls.callbacks.append(callback)

    def set_control_enabled(widget: Any, enabled: bool, **_kwargs: Any) -> None:
        widget.setEnabled(enabled)

    unlock = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_unlock_bed",
        {"QTimer": Timer, "set_control_enabled": set_control_enabled},
    )
    release = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_release_bed_purchase",
        {"set_control_enabled": set_control_enabled},
    )
    begin_catalog_transaction = _compiled_method(
        DASHBOARD_PATH, "NurseryDialog", "_begin_catalog_transaction"
    )
    release_catalog_transaction = _compiled_method(
        DASHBOARD_PATH, "NurseryDialog", "_release_catalog_transaction"
    )

    class Button:
        def __init__(self) -> None:
            self.enabled = True
            self.visible = True

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

        def isVisible(self) -> bool:
            return self.visible

    class Engine:
        def __init__(self) -> None:
            self.purchases = 0
            self.price: int | None = 150

        def purchase_next_bed(self) -> tuple[bool, str]:
            self.purchases += 1
            return True, "Garden space unlocked."

        def next_bed_price(self) -> int | None:
            return self.price

    engine = Engine()
    nursery = SimpleNamespace(
        _bed_purchase_pending=False,
        _catalog_transaction_pending=False,
        bed_button=Button(),
        engine=engine,
        storage=SimpleNamespace(
            state=SimpleNamespace(
                starter_selection_complete=True,
                currency_balance=500,
            )
        ),
        _show_result=lambda ok, message: None,
        _refresh_parent=lambda: None,
        refresh=lambda: None,
    )
    nursery._begin_catalog_transaction = lambda: begin_catalog_transaction(nursery)
    nursery._release_catalog_transaction = lambda: release_catalog_transaction(nursery)
    nursery._release_bed_purchase = lambda: release(nursery)

    unlock(nursery)
    unlock(nursery)

    assert engine.purchases == 1
    assert nursery._bed_purchase_pending is True
    assert nursery._catalog_transaction_pending is True
    assert nursery.bed_button.enabled is False
    assert len(Timer.callbacks) == 1

    Timer.callbacks.pop()()
    assert nursery._bed_purchase_pending is False
    assert nursery._catalog_transaction_pending is False
    assert nursery.bed_button.enabled is True

    nursery.storage.state.starter_selection_complete = False
    release(nursery)
    assert nursery.bed_button.enabled is False
    nursery.storage.state.starter_selection_complete = True
    nursery.bed_button.visible = False
    release(nursery)
    assert nursery.bed_button.enabled is False
    nursery.bed_button.visible = True
    nursery.storage.state.currency_balance = 100
    release(nursery)
    assert nursery.bed_button.enabled is False
    nursery.storage.state.currency_balance = 500
    engine.price = None
    release(nursery)
    assert nursery.bed_button.enabled is False


def test_nursery_status_is_local_focusable_and_recovery_button_is_conditional() -> None:
    class Timer:
        callbacks: list[Any] = []

        @classmethod
        def singleShot(cls, _delay: int, callback: Any) -> None:
            cls.callbacks.append(callback)

    class Priority:
        POLITE = "polite"
        ASSERTIVE = "assertive"

    show_result = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_show_result",
        {
            "_learner_text": lambda value: value,
            "AnnouncementPriority": Priority,
            "QTimer": Timer,
        },
    )
    hide_status = _compiled_method(
        DASHBOARD_PATH,
        "NurseryDialog",
        "_hide_status_if_current",
    )
    sync_recovery = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_sync_nursery_recovery",
        {
            "UX_ACTIVE_GROWTH": "active_growth",
            "UX_NO_STARTER": "no_starter",
            "UX_STARTER_READY": "starter_ready",
            "CURRENT_ONBOARDING_VERSION": 2,
        },
    )

    class Status:
        def __init__(self) -> None:
            self.text = ""
            self.focused = False
            self.visible = False

        def setText(self, value: str) -> None:
            self.text = value

        def setStyleSheet(self, _value: str) -> None:
            return None

        def setAccessibleDescription(self, value: str) -> None:
            self.description = value

        def show(self) -> None:
            self.visible = True

        def hide(self) -> None:
            self.visible = False

        def setFocus(self) -> None:
            self.focused = True

    class ReceiptActions:
        def __init__(self) -> None:
            self.visible = True

        def hide(self) -> None:
            self.visible = False

    status = Status()
    receipt_actions = ReceiptActions()
    announcements: list[tuple[str, str]] = []
    nursery = SimpleNamespace(
        _status_generation=0,
        status=status,
        receipt_actions=receipt_actions,
        accessibility_announcer=SimpleNamespace(
            announce=lambda message, *, priority, target: announcements.append(
                (message, priority)
            )
        ),
    )
    nursery._hide_status_if_current = lambda generation: hide_status(
        nursery,
        generation,
    )
    show_result(
        nursery,
        False,
        "Not enough Garden Coins.",
    )
    assert (status.text, status.description, status.visible, status.focused) == (
        "Not enough Garden Coins.", "Not enough Garden Coins.", True, True,
    )
    assert receipt_actions.visible is False
    assert announcements[-1] == ("Not enough Garden Coins.", "assertive")

    show_result(nursery, True, "Garden space unlocked.")
    assert len(Timer.callbacks) == 1
    show_result(nursery, False, "A newer purchase failed.")
    Timer.callbacks.pop()()
    assert status.visible is True
    assert status.text == "A newer purchase failed."

    class Recovery:
        def setVisible(self, value: bool) -> None:
            self.visible = value

    recovery = Recovery()
    scene = SimpleNamespace(
        landmark_geometry=lambda _action: None,
        _interaction=SimpleNamespace(placing=False),
    )
    dashboard = SimpleNamespace(scene=scene, nursery_recovery_btn=recovery)
    sync_recovery(dashboard)
    assert recovery.visible is True
    scene._interaction.placing = True
    sync_recovery(dashboard)
    assert recovery.visible is False
    scene._interaction.placing = False
    scene.landmark_geometry = lambda _action: object()
    sync_recovery(dashboard)
    assert recovery.visible is False

    nursery_source = DASHBOARD_PATH.read_text("utf-8").split(
        "class NurseryDialog", 1
    )[1].split("class PlantInfoCard", 1)[0]
    assert "self.status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in nursery_source


def test_metric_cells_are_focusable_and_wrap_as_complete_groups_when_compact() -> None:
    set_compact = _compiled_method(
        DASHBOARD_PATH,
        "GardenStatsStrip",
        "set_compact",
        {
            "Qt": SimpleNamespace(
                AlignmentFlag=SimpleNamespace(AlignBottom="align-bottom")
            )
        },
    )

    class Grid:
        def __init__(self) -> None:
            self.positions: list[tuple[str, int, int, int, int]] = []
            self.stretches: list[tuple[int, int]] = []

        def removeWidget(self, _cell: Any) -> None:
            return None

        def addWidget(
            self,
            cell: Any,
            row: int,
            column: int,
            row_span: int = 1,
            column_span: int = 1,
        ) -> None:
            self.positions.append((cell, row, column, row_span, column_span))

        def setColumnStretch(self, column: int, stretch: int) -> None:
            self.stretches.append((column, stretch))

    class Layout:
        def __init__(self) -> None:
            self.insertions: list[tuple[Any, ...]] = []

        def removeWidget(self, _widget: Any) -> None:
            return None

        def addWidget(self, *_args: Any) -> None:
            return None

        def insertWidget(self, *args: Any) -> None:
            self.insertions.append(args)

    metrics = (("growth", "Growth", ""), ("streak", "Streak", ""), ("currency", "Coins", ""))
    strip = SimpleNamespace(
        METRICS=metrics,
        cells={key: key for key, _title, _description in metrics},
        grid=Grid(),
        growth_support=SimpleNamespace(setVisible=lambda value: None),
        streak_support=SimpleNamespace(setVisible=lambda value: None),
        currency_support=SimpleNamespace(setVisible=lambda value: None),
        streak_label=SimpleNamespace(
            setText=lambda value: None,
            setAccessibleName=lambda value: None,
            setMinimumWidth=lambda value: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 56),
        ),
        streak_bonus=SimpleNamespace(
            setText=lambda value: None,
            setMinimumWidth=lambda value: None,
        ),
        streak_heading=Layout(),
        streak_value_row=Layout(),
        _streak_bonus_percent=10,
        _streak_bonus_minimum_width=lambda compact: 53 if compact else 102,
    )

    set_compact(strip, True)

    assert strip.grid.positions == [
        ("growth", 0, 0, 1, 4),
        ("streak", 1, 0, 1, 2),
        ("currency", 1, 2, 1, 2),
    ]
    assert strip.grid.stretches == [(0, 1), (1, 1), (2, 1), (3, 1)]
    assert strip.streak_value_row.insertions == [
        (2, strip.streak_bonus, 0, "align-bottom")
    ]
    stats_source = DASHBOARD_PATH.read_text("utf-8").split(
        "class GardenStatsStrip", 1
    )[1].split("class RearrangeBar", 1)[0]
    assert "cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in stats_source
    assert "QPushButton[gardenStatCell='true']:focus" in DASHBOARD_PATH.read_text("utf-8")
    dashboard_source = DASHBOARD_PATH.read_text("utf-8")
    assert "font-size:12px" in dashboard_source.split("QLabel[gardenStatLabel", 1)[1].split("}", 1)[0]
    assert "font-size:16px" in dashboard_source.split("QLabel[gardenGrowthValue", 1)[1].split("}", 1)[0]
    assert "font-size:22px" in dashboard_source.split("QLabel[gardenLargeValue", 1)[1].split("}", 1)[0]


def test_selected_plant_card_distinguishes_nurtured_state_and_omits_inactive_boosts() -> None:
    source = _method_source(DASHBOARD_PATH, "PlantInfoCard", "set_selected")

    assert 'self.nurture.setVisible(not active and not fully_grown)' in source
    assert 'self.nurtured_badge.setVisible(active and not fully_grown)' in source
    assert 'BUTTON_VARIANT_PRIMARY if active and not fully_grown' in source
    assert "self.fertilizer_summary.set_status(fertilizer_projection)" in source
    constructor = _method_source(DASHBOARD_PATH, "PlantInfoCard", "__init__")
    assert "self.fertilizer_summary = FertilizerStatusBlock(allow_description=False)" in constructor
    assert 'self.booster_summary.setVisible(booster_growth > 0)' in source
    assert 'value_text=f"{stage_points:,} / {stage_goal:,} Growth"' in source
    assert "self.growth_summary.setText(" in source
    assert ".replace('card answer', 'eligible answer')" not in source
    assert 'forecast = plant.get("growth_forecast", {})' in source
    assert source.count("self.growth_remaining.hide()") == 2
    assert "self.growth_remaining.setText(" not in source
    assert "self.growth_summary.setAccessibleDescription(" in source
    assert 'f"{remaining:,} Growth remaining. {forecast_accessible}"' in source
    assert 'self.status_row.hide()' in source
    assert 'self._layout_actions(active=active, fully_grown=fully_grown)' in source


def test_troubleshooting_copy_confirmation_is_visible_and_refresh_resets_it() -> None:
    copy_report = _method_source(
        DASHBOARD_PATH, "GardenSettingsDialog", "_copy_debug_report"
    )
    refresh_report = _method_source(
        DASHBOARD_PATH, "GardenSettingsDialog", "_refresh_debug_report"
    )

    assert "QGuiApplication.clipboard().setText" in copy_report
    assert 'self.diagnostics_checked.setText("Report copied to clipboard")' in copy_report
    assert "self.diagnostics_card.setFocus()" in copy_report
    assert 'status = "No display issues detected"' in refresh_report
    assert 'status = "Garden display may be incomplete"' in refresh_report
    assert "contract_failures" in refresh_report
    assert "parsing_exceptions" in refresh_report
    assert 'f"Last checked {datetime.now().strftime' in refresh_report


def test_today_growth_row_is_neutral_information_not_a_completion_requirement() -> None:
    tooltips: list[tuple[Any, str]] = []
    set_information = _compiled_method(
        DASHBOARD_PATH,
        "ProgressRow",
        "set_information",
        {
            "apply_explanatory_tooltip": lambda widget, text: tooltips.append(
                (widget, text)
            )
        },
    )

    class Widget:
        def setText(self, value: str) -> None:
            self.text = value

        def setAccessibleName(self, value: str) -> None:
            self.accessible_name = value

        def setVisible(self, value: bool) -> None:
            self.visible = value

        def hide(self) -> None:
            self.visible = False

    row = SimpleNamespace(
        title=Widget(),
        criteria=Widget(),
        progress=Widget(),
        status=Widget(),
        properties={},
    )
    row.setProperty = lambda key, value: row.properties.__setitem__(key, value)
    row.setAccessibleName = lambda value: setattr(row, "accessible_name", value)
    row.setAccessibleDescription = lambda value: setattr(row, "accessible_description", value)

    set_information(
        row,
        "Growth earned",
        "How today’s card answers became Growth.",
        "30 Growth earned",
        explanation="Each counted card answer gives the nurtured plant base Growth.",
    )

    assert row.progress.visible is False
    assert row.status.visible is True
    assert row.status.text == "30 Growth earned"
    assert row.properties.get("completed") is False
    assert "recorded" in row.accessible_name.lower()
    row_tooltip = next(text for widget, text in tooltips if widget is row)
    assert "requirement" not in row_tooltip.lower()
    assert "Each counted card answer" in row_tooltip
    assert "Each counted card answer" in row.accessible_description

    refresh = _method_source(DASHBOARD_PATH, "GardenDetailsDialog", "_refresh_growth")
    assert "today = QFrame()" in refresh
    assert '"Growth breakdown"' in refresh
    assert 'StatSummary([' in refresh
    assert '("Total Growth",' in refresh
    assert 'if int(stats.growth_earned) == 0:' in refresh
    assert 'today_layout.addWidget(StatSummary([' in refresh


def test_move_failure_uses_one_scene_owned_teardown_and_focusable_feedback() -> None:
    class Timer:
        calls: list[tuple[int, Any]] = []

        @classmethod
        def singleShot(cls, delay: int, callback: Any) -> None:
            cls.calls.append((delay, callback))

    finish_failed = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_finish_failed_move",
        {"QTimer": Timer, "_learner_text": lambda value: value},
    )

    class Toast:
        def __init__(self) -> None:
            self.focused = False
            self.messages: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def show_message(self, *args: Any, **kwargs: Any) -> None:
            self.messages.append((args, kwargs))

        def setFocus(self) -> None:
            self.focused = True

    class Visible:
        def hide(self) -> None:
            self.hidden = True

    scene = SimpleNamespace(
        finish_move=lambda message: setattr(scene, "message", message),
        setFocus=lambda: setattr(scene, "focused", True),
        keep_card_open=lambda *_args: None,
    )
    toast = Toast()
    dashboard = SimpleNamespace(
        _placement_draft=object(),
        _undo_placement=None,
        scene=scene,
        rearrange_bar=Visible(),
        _position_scene_overlays=lambda: None,
        _refresh_selected_plant_card=lambda: None,
        toast_region=toast,
        refresh_all=lambda: setattr(dashboard, "refreshed", True),
    )

    finish_failed(dashboard, "The arrangement could not be saved.")

    assert dashboard._placement_draft is None
    assert scene.message == "Move not saved. The arrangement could not be saved."
    assert dashboard.rearrange_bar.hidden is True
    assert dashboard.refreshed is True
    assert scene.focused is True
    assert toast.messages == [
        (("The arrangement could not be saved.",), {"error": True, "duration_ms": 0})
    ]
    assert toast.focused is True

    place = _method_source(DASHBOARD_PATH, "GardenDashboard", "_place_plant")
    assert place.count("self._finish_failed_move(") == 3
    for private_scene_mutation in (
        "self.scene._interaction", "self.scene._clear_hit_targets",
        "self.scene.placementStateChanged.emit",
    ):
        assert private_scene_mutation not in place
    assert "self.scene.finish_move(" in place


def test_selected_card_uses_dock_when_no_safe_scene_geometry_exists() -> None:
    position = _compiled_method(
        DASHBOARD_PATH, "GardenDashboard", "_position_plant_card"
    )
    show_docked = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_show_docked_plant_card",
        {
            "Qt": SimpleNamespace(
                AlignmentFlag=SimpleNamespace(AlignHCenter="center")
            )
        },
    )

    scene = SimpleNamespace(
        _interaction=SimpleNamespace(placing=False),
        width=lambda: 900,
        height=lambda: 480,
        card_geometry=lambda _width, _height: None,
    )

    class Card:
        plant_id = "plant-a"

        def __init__(self) -> None:
            self.parent = scene
            self.choose_another = SimpleNamespace(isVisible=lambda: False)

        def parentWidget(self) -> Any:
            return self.parent

        def setParent(self, parent: Any) -> None:
            self.parent = parent

        def setMaximumWidth(self, width: int) -> None:
            self.maximum_width = width

        def setFixedWidth(self, width: int) -> None:
            self.fixed_width = width

        def setMinimumHeight(self, height: int) -> None:
            self.minimum_height = height

        def set_docked_mode(self, docked: bool) -> None:
            self.docked = docked

        def layout(self) -> None:
            return None

        def adjustSize(self) -> None:
            return None

        def sizeHint(self) -> Any:
            return SimpleNamespace(height=lambda: 240)

        def width(self) -> int:
            return self.fixed_width

        def hide(self) -> None:
            self.hidden = True

        def show(self) -> None:
            self.shown = True

    class Dock:
        def width(self) -> int:
            return 880

        def hide(self) -> None:
            self.hidden = True

        def show(self) -> None:
            self.shown = True

    class DockLayout:
        def addWidget(self, *_args: Any) -> None:
            self.added = True

    dock = Dock()
    dashboard = SimpleNamespace(
        plant_card=Card(),
        plant_card_dock=dock,
        plant_card_dock_layout=DockLayout(),
        scene=scene,
        _compact_layout=False,
    )
    dashboard._show_docked_plant_card = lambda *, full_width: show_docked(
        dashboard,
        full_width=full_width,
    )

    position(dashboard)

    assert dashboard.plant_card.parent is dock
    assert dashboard.plant_card.shown is True
    assert dashboard.plant_card.fixed_width == 640
    assert dock.shown is True
    dashboard_source = DASHBOARD_PATH.read_text("utf-8")
    assert "self.plant_card_dock = QFrame()" in dashboard_source
    assert "geometry = self.scene.card_geometry(" in dashboard_source
    assert "if geometry is None:" in dashboard_source
    assert "narrow_sheet = self.scene.width() < 540" not in dashboard_source


def test_external_surface_refresh_never_resets_reviewer_and_only_refreshes_home_views() -> None:
    refresh_external = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "refresh_external_surfaces",
        {"logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None)},
    )

    class Surface:
        def __init__(self) -> None:
            self.refreshes = 0

        def refresh(self) -> None:
            self.refreshes += 1

    for state, expected_resets, expected_deck, expected_overview in (
        ("review", 0, 0, 0),
        ("reviewer", 0, 0, 0),
        ("deckBrowser", 1, 1, 0),
        ("overview", 1, 0, 1),
    ):
        deck = Surface()
        overview = Surface()
        resets: list[str] = []
        dashboard = SimpleNamespace(
            mw_window=SimpleNamespace(
                state=state,
                deckBrowser=deck,
                overview=overview,
                reset=lambda: resets.append("reset"),
            )
        )

        refresh_external(dashboard)

        assert resets == ["reset"] * expected_resets
        assert deck.refreshes == expected_deck
        assert overview.refreshes == expected_overview


def test_external_surface_refresh_skips_clean_dashboard() -> None:
    refresh_external = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "refresh_external_surfaces",
        {"logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None)},
    )
    resets: list[str] = []
    dashboard = SimpleNamespace(
        _home_surface_dirty=False,
        mw_window=SimpleNamespace(
            state="deckBrowser",
            deckBrowser=SimpleNamespace(refresh=lambda: resets.append("refresh")),
            reset=lambda: resets.append("reset"),
        ),
    )

    refresh_external(dashboard)

    assert resets == []


def test_move_state_event_updates_only_the_move_scene() -> None:
    state_changed = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_on_state_changed",
        {"logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None)},
    )
    calls: list[str] = []
    dashboard = SimpleNamespace(
        _home_surface_dirty=False,
        isVisible=lambda: True,
        _refresh_move_scene=lambda: calls.append("move"),
        refresh_all=lambda: calls.append("full"),
    )

    state_changed(dashboard, "plant move")

    assert calls == ["move"]
    assert dashboard._home_surface_dirty is True


def test_scene_slot_update_reuses_existing_asset_payloads() -> None:
    update_slots = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "update_plant_slots",
        {"QTimer": SimpleNamespace(singleShot=lambda _delay, callback: callback())},
    )
    updates: list[str] = []
    scene = SimpleNamespace(
        scene={
            "plants": [
                {"plant_id": "a", "slot_index": 0, "asset": {"path": "a.png"}},
                {"plant_id": "b", "slot_index": 1, "asset": {"path": "b.png"}},
            ]
        },
        _slot_placements={0: object()},
        update=lambda: updates.append("update"),
        _sync_landmark_hotspot=lambda: updates.append("landmarks"),
        cardGeometryChanged=SimpleNamespace(emit=lambda: updates.append("geometry")),
    )

    assert update_slots(scene, {"a": 2, "b": 1}) is True
    assert scene.scene["plants"][0]["slot_index"] == 2
    assert scene.scene["plants"][0]["asset"] == {"path": "a.png"}
    assert updates == ["update", "landmarks", "geometry"]


def test_successful_post_commit_event_clears_only_prior_display_notice() -> None:
    from ankigarden.notices import USER_NOTICES

    refresh_after_commit = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_refresh_after_commit",
        {
            "USER_NOTICES": USER_NOTICES,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )
    calls: list[str] = []
    dashboard = SimpleNamespace(
        state_events=SimpleNamespace(
            notify=lambda context: calls.append(f"event:{context}")
        )
    )

    try:
        USER_NOTICES.clear()
        USER_NOTICES.publish(
            "The Garden display could not refresh.",
            key="display_refresh",
            throttle_seconds=0,
        )

        refresh_after_commit(dashboard, "test change")

        assert calls == ["event:test change"]
        assert USER_NOTICES.current.message == ""

        USER_NOTICES.publish(
            "Review history is temporarily unavailable.",
            key="review_history",
            throttle_seconds=0,
        )
        refresh_after_commit(dashboard, "another change")

        assert calls[-1] == "event:another change"
        assert USER_NOTICES.current.key == "review_history"
        assert USER_NOTICES.current.message == "Review history is temporarily unavailable."
    finally:
        USER_NOTICES.clear()


def test_prepare_to_show_renders_feedback_without_acknowledging_it() -> None:
    notice_calls: list[tuple[str, str]] = []
    notices = SimpleNamespace(
        clear=lambda *, key: notice_calls.append(("clear", key)),
        publish=lambda _message, *, key: notice_calls.append(("publish", key)),
    )
    prepare = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "prepare_to_show",
        {"USER_NOTICES": notices},
    )
    refresh_calls: list[bool] = []
    dashboard = SimpleNamespace(
        refresh_all=lambda *, acknowledge=True: refresh_calls.append(
            bool(acknowledge)
        ),
        isVisible=lambda: False,
        _skip_next_show_refresh=False,
    )

    prepare(dashboard)

    assert refresh_calls == [False]
    assert dashboard._skip_next_show_refresh is True
    assert notice_calls == [("clear", "display_refresh")]


def test_refresh_all_default_acknowledges_only_when_dashboard_is_visible() -> None:
    refresh = _method_source(DASHBOARD_PATH, "GardenDashboard", "refresh_all")
    decision = refresh.split("DISPLAY_TELEMETRY.track_render", 1)[0]
    acknowledgement = refresh.rsplit("if acknowledge:", 1)[1]

    assert "acknowledge: bool | None = None" in refresh.splitlines()[0]
    assert "if acknowledge is None:" in decision
    assert "acknowledge = bool(self.isVisible())" in decision
    assert "except RuntimeError:" in decision
    assert "acknowledge = False" in decision
    assert "self.acknowledge_rendered_feedback()" in acknowledgement

    parsed = ast.parse(textwrap.dedent(refresh))
    original = next(node for node in parsed.body if isinstance(node, ast.FunctionDef))
    visibility_if = next(
        node for node in original.body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "acknowledge is None"
    )
    acknowledge_if = next(
        node for node in reversed(original.body)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "acknowledge"
    )
    probe = ast.FunctionDef(
        name="refresh_ack_probe",
        args=deepcopy(original.args),
        body=[deepcopy(visibility_if), deepcopy(acknowledge_if)],
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    module = ast.fix_missing_locations(ast.Module(body=[probe], type_ignores=[]))
    scope: dict[str, Any] = {}
    exec(compile(module, "<refresh-ack-probe>", "exec"), scope)
    decide = scope["refresh_ack_probe"]

    for visible, explicit, expected in (
        (False, None, 0),
        (True, None, 1),
        (False, True, 1),
        (True, False, 0),
    ):
        calls: list[str] = []
        dashboard = SimpleNamespace(
            isVisible=lambda visible=visible: visible,
            acknowledge_rendered_feedback=lambda: calls.append("acknowledge"),
        )
        decide(dashboard, acknowledge=explicit)
        assert len(calls) == expected


def test_rendered_feedback_acknowledgement_uses_exact_ids_after_queue_churn() -> None:
    acknowledge = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "acknowledge_rendered_feedback",
        {"logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None)},
    )

    class Engine:
        def __init__(self) -> None:
            self.feedback = ["rendered:B", "new:C", "new:D"]
            self.requests: list[tuple[str, ...]] = []

        def consume_feedback(self, *, event_ids: tuple[str, ...]):
            self.requests.append(tuple(event_ids))
            expected = set(event_ids)
            consumed = [event_id for event_id in self.feedback if event_id in expected]
            self.feedback = [event_id for event_id in self.feedback if event_id not in expected]
            return consumed

        def consume_stage_transitions(self, **_kwargs):
            raise AssertionError("No transition acknowledgement was rendered")

    engine = Engine()
    dashboard = SimpleNamespace(
        engine=engine,
        _pending_feedback_ack_ids=("rendered:A", "rendered:B"),
        _pending_transition_ack=(),
    )

    acknowledge(dashboard)

    assert engine.requests == [("rendered:A", "rendered:B")]
    assert engine.feedback == ["new:C", "new:D"]
    assert dashboard._pending_feedback_ack_ids == ()

    refresh = _method_source(DASHBOARD_PATH, "GardenDashboard", "refresh_all")
    assert "tuple(event.event_id for event in feedback)" in refresh
    assert "_pending_feedback_ack_count" not in refresh


def test_feedback_and_transition_acknowledgements_retry_independently() -> None:
    acknowledge = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "acknowledge_rendered_feedback",
        {"logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None)},
    )
    rendered_transition = object()

    class Engine:
        def __init__(self) -> None:
            self.feedback = ["rendered:A"]
            self.feedback_requests: list[tuple[str, ...]] = []
            self.transition_requests: list[tuple[Any, ...]] = []

        def consume_feedback(self, *, event_ids: tuple[str, ...]):
            self.feedback_requests.append(tuple(event_ids))
            expected = set(event_ids)
            self.feedback = [event_id for event_id in self.feedback if event_id not in expected]

        def consume_stage_transitions(self, *, transitions: tuple[Any, ...]):
            self.transition_requests.append(tuple(transitions))
            if len(self.transition_requests) == 1:
                raise OSError("transition acknowledgement unavailable")

    engine = Engine()
    dashboard = SimpleNamespace(
        engine=engine,
        _pending_feedback_ack_ids=("rendered:A",),
        _pending_transition_ack=(rendered_transition,),
    )

    acknowledge(dashboard)

    assert engine.feedback == []
    assert dashboard._pending_feedback_ack_ids == ()
    assert dashboard._pending_transition_ack == (rendered_transition,)

    engine.feedback.append("new:B")
    acknowledge(dashboard)

    assert engine.feedback == ["new:B"]
    assert engine.feedback_requests == [("rendered:A",)]
    assert engine.transition_requests == [
        (rendered_transition,), (rendered_transition,),
    ]
    assert dashboard._pending_transition_ack == ()


def test_successful_persisted_move_undo_uses_post_commit_refresh_boundary() -> None:
    class Timer:
        calls: list[tuple[int, Any]] = []

        @classmethod
        def singleShot(cls, delay: int, callback: Any) -> None:
            cls.calls.append((delay, callback))

    undo = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_undo_move",
        {
            "QTimer": Timer,
            "_learner_text": lambda value: value,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )

    post_commit: list[str] = []
    direct_refreshes: list[str] = []
    popup_messages: list[str] = []
    scene = SimpleNamespace(setFocus=lambda: setattr(scene, "focused", True))
    dashboard = SimpleNamespace(
        _placement_draft=None,
        _undo_placement=object(),
        engine=SimpleNamespace(
            restore_placement=lambda _change: (True, "Arrangement restored.", object())
        ),
        _refresh_after_commit=lambda context: post_commit.append(context),
        refresh_all=lambda: direct_refreshes.append("dashboard"),
        refresh_external_surfaces=lambda: direct_refreshes.append("external"),
        toast_region=SimpleNamespace(
            show_message=lambda message, **_kwargs: popup_messages.append(message)
        ),
        scene=scene,
    )

    undo(dashboard)

    assert dashboard._undo_placement is None
    assert post_commit == ["move undo"]
    assert direct_refreshes == []
    assert popup_messages == ["Move undone."]
    assert scene.focused is True


def test_starting_new_move_clears_the_previous_popup_before_new_failure() -> None:
    class Timer:
        calls: list[tuple[int, Any]] = []

        @classmethod
        def singleShot(cls, delay: int, callback: Any) -> None:
            cls.calls.append((delay, callback))

    begin_move = _compiled_method(
        DASHBOARD_PATH, "GardenDashboard", "_begin_move", {"QTimer": Timer}
    )
    finish_failed = _compiled_method(
        DASHBOARD_PATH,
        "GardenDashboard",
        "_finish_failed_move",
        {
            "QTimer": Timer,
            "_learner_text": lambda value: value,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )
    class Visible:
        plant_id = ""

        def __init__(self) -> None:
            self.title = SimpleNamespace(setText=lambda value: setattr(self, "heading", value))
            self.instructions = SimpleNamespace(setText=lambda value: setattr(self, "instruction", value))

        def show(self) -> None:
            self.visible = True

        def hide(self) -> None:
            self.visible = False

        def setVisible(self, value: bool) -> None:
            self.visible = value

    class Toast:
        def __init__(self) -> None:
            self.events: list[Any] = []

        def clear(self) -> None:
            self.events.append("clear")

        def show_message(self, *args: Any, **kwargs: Any) -> None:
            self.events.append((args, kwargs))

        def setFocus(self) -> None:
            self.events.append("focus")

    draft = SimpleNamespace(
        selected_plant_id="plant-a",
        scene_slots=lambda: {"plant-a": 0},
    )
    rearrange = Visible()
    toast = Toast()
    scene = SimpleNamespace(
        keep_card_open=lambda *_args: None,
        begin_move=lambda plant_id, slots: (
            setattr(scene, "retry", (plant_id, slots)) or True
        ),
        finish_move=lambda message: setattr(scene, "message", message),
        setFocus=lambda: setattr(scene, "focused", True),
    )
    dashboard = SimpleNamespace(
        _undo_placement=object(),
        _placement_draft=None,
        engine=SimpleNamespace(
            begin_placement_draft=lambda _plant_id: (True, "", draft),
            valid_destination_slots=lambda _draft: [0, 1],
        ),
        storage=SimpleNamespace(
            state=SimpleNamespace(
                plants=[SimpleNamespace(plant_id="plant-a", name="Aster")]
            )
        ),
        scene=scene,
        rearrange_bar=rearrange,
        _position_scene_overlays=lambda: None,
        _refresh_selected_plant_card=lambda: None,
        toast_region=toast,
        refresh_all=lambda: None,
    )

    begin_move(dashboard, "plant-a")
    finish_failed(dashboard, "The arrangement could not be saved.")

    assert toast.events == [
        "clear",
        (("The arrangement could not be saved.",), {"error": True, "duration_ms": 0}),
        "focus",
    ]
    assert scene.focused is True
    assert scene.retry == ("plant-a", [0, 1])
    assert dashboard._placement_draft is draft
    assert rearrange.visible is True


def test_long_plant_names_wrap_in_nursery_and_collection_rows() -> None:
    nursery_card = _method_source(DASHBOARD_PATH, "NurseryDialog", "_owned_card")
    collection = _method_source(
        DASHBOARD_PATH, "GardenDashboard", "_refresh_collection_list"
    )

    assert "title.setTextFormat(Qt.TextFormat.PlainText)" in nursery_card
    assert "title.setWordWrap(True)" in nursery_card
    assert "title.setWordWrap(True)" in collection
    assert "format_status_label(species)" in collection
    assert "title.setWordWrap(True)" in collection
    assert "status.setWordWrap(True)" in collection


def test_fertilizer_buttons_describe_tier_cost_and_effect_for_accessibility() -> None:
    fertilizer_menu = _method_source(
        DASHBOARD_PATH, "GardenDashboard", "_open_fertilizer_menu"
    )

    assert "choose.setAccessibleDescription(" in fertilizer_menu
    for required in ("spec.name", "spec.price", "spec.growth_per_answer", "duration"):
        assert required in fertilizer_menu
    assert 'duration = f"{hours} hour" if hours == 1 else f"{hours} hours"' in fertilizer_menu
    assert "Garden Coins" in fertilizer_menu
    assert "Growth per Anki card answer" in fertilizer_menu
    assert "Growth per answer" not in fertilizer_menu


def test_stage_transition_generation_ignores_stale_timer_and_reannounces_selection() -> None:
    class Timer:
        calls: list[tuple[int, Any]] = []

        @classmethod
        def singleShot(cls, delay: int, callback: Any) -> None:
            cls.calls.append((delay, callback))

    finish_transition = _compiled_method(
        SCENE_PATH, "GardenSceneWidget", "_finish_stage_transition"
    )
    set_scene = _compiled_method(
        SCENE_PATH,
        "GardenSceneWidget",
        "set_scene",
        {"QTimer": Timer, "time": SimpleNamespace(monotonic=lambda: 123.0)},
    )

    class Interaction:
        def __init__(self) -> None:
            self.pinned_id: str | None = "plant-a"
            self.focused_index = 0

        def reconcile(self, _plant_ids: list[str]) -> None:
            return None

        def dismiss(self) -> None:
            self.pinned_id = None
            self.focused_index = -1

    announcements: list[bool] = []
    card_geometry_emits: list[str] = []
    scene = SimpleNamespace(
        scene={"stage_transitions": []},
        _sanitize_scene_payload=lambda payload: dict(payload),
        _interaction=Interaction(),
        _plant_ids=lambda: [
            str(row["plant_id"]) for row in scene.scene.get("plants", [])
        ],
        _hover_opacity={},
        interactive=True,
        _transition_generation=0,
        _transition_started_at=None,
        _transition_duration=1.0,
        _announce_focused_plant=lambda selected=False: announcements.append(bool(selected)),
        update=lambda: setattr(scene, "updates", getattr(scene, "updates", 0) + 1),
        _sync_landmark_hotspot=lambda: None,
        cardGeometryChanged=SimpleNamespace(
            emit=lambda: card_geometry_emits.append("emit")
        ),
    )
    scene._finish_stage_transition = lambda generation: finish_transition(scene, generation)

    first = {
        "plants": [{"plant_id": "plant-a"}],
        "stage_transitions": [{"plant_id": "plant-a"}],
    }
    second = {
        "plants": [{"plant_id": "plant-a"}],
        "stage_transitions": [{"plant_id": "plant-b"}],
    }
    set_scene(scene, first)
    set_scene(scene, second)

    transition_callbacks = [callback for delay, callback in Timer.calls if delay == 1000]
    assert len(transition_callbacks) == 2
    assert announcements == [True, True]

    transition_callbacks[0]()
    assert scene.scene["stage_transitions"] == [{"plant_id": "plant-b"}]
    assert scene._transition_started_at == 123.0

    transition_callbacks[1]()
    assert scene.scene["stage_transitions"] == []
    assert scene._transition_started_at is None

    scene._interaction.pinned_id = None
    scene._interaction.focused_index = 0
    set_scene(scene, {"plants": [{"plant_id": "plant-a"}], "stage_transitions": []})
    assert announcements[-1] is False


def test_missing_or_corrupt_surface_suppresses_all_landmark_hotspots() -> None:
    sync_hotspots = _compiled_method(
        SCENE_PATH, "GardenSceneWidget", "_sync_landmark_hotspot"
    )

    class Hotspot:
        def __init__(self) -> None:
            self.visible = True

        def hide(self) -> None:
            self.visible = False

    for background_path, pixmap in ((None, object()), (Path("/bad/surface.png"), None)):
        hotspot = Hotspot()
        changes: list[str] = []
        pixmap_calls: list[Path] = []
        scene = SimpleNamespace(
            _landmark_hotspots={"nursery": hotspot},
            _landmark_action_id="garden.nursery.open",
            _landmark_action_by_id={"nursery": "garden.nursery.open"},
            _landmark_rects={"nursery": object()},
            _landmark_polygons={"nursery": object()},
            _landmark_outline_paths={"nursery": object()},
            _landmark_labels={"nursery": "Nursery"},
            _interaction=SimpleNamespace(placing=False),
            landmarksChanged=SimpleNamespace(emit=lambda: changes.append("changed")),
            _surface_asset_record=lambda _width, _height: (
                background_path, False, {}, ""
            ),
            _pixmap_for=lambda path: (pixmap_calls.append(path), pixmap)[1],
            width=lambda: 900,
            height=lambda: 600,
        )

        sync_hotspots(scene)

        assert hotspot.visible is False
        assert scene._landmark_action_id == ""
        assert scene._landmark_action_by_id == {}
        assert scene._landmark_rects == {}
        assert scene._landmark_polygons == {}
        assert scene._landmark_outline_paths == {}
        assert scene._landmark_labels == {}
        assert changes == ["changed"]
        assert pixmap_calls == ([] if background_path is None else [background_path])
