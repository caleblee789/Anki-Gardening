from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ankigarden.ui.render_cache import BoundedLruCache


ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "ankigarden" / "ui" / "scene.py"


def _compiled_scene_method(
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    source = SCENE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    scene_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenSceneWidget"
    )
    method = next(
        node
        for node in scene_class.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    scope: dict[str, Any] = {"Any": Any}
    scope.update(namespace or {})
    exec(textwrap.dedent(ast.get_source_segment(source, method) or ""), scope)
    return scope[method_name]


def test_bounded_render_cache_uses_lru_eviction_and_hard_limit() -> None:
    cache: BoundedLruCache[str, int] = BoundedLruCache(2)
    cache["background"] = 1
    cache["plant"] = 2
    assert cache.get("background") == 1

    cache["weather"] = 3

    assert len(cache) == 2
    assert "background" in cache
    assert "plant" not in cache
    assert cache.get("weather") == 3


def test_bounded_render_cache_can_remember_a_negative_lookup() -> None:
    cache: BoundedLruCache[str, object | None] = BoundedLruCache(1)
    cache["missing"] = None

    assert "missing" in cache
    assert cache.get("missing") is None
    assert len(cache) == 1


class _Timer:
    def __init__(self, *, active: bool = False, interval: int = 0) -> None:
        self.active = active
        self.current_interval = interval
        self.starts: list[int] = []
        self.stops = 0

    def isActive(self) -> bool:
        return self.active

    def interval(self) -> int:
        return self.current_interval

    def start(self, interval: int) -> None:
        self.active = True
        self.current_interval = int(interval)
        self.starts.append(int(interval))

    def stop(self) -> None:
        self.active = False
        self.stops += 1


def test_animation_timer_stops_when_static_and_restores_effect_cadences() -> None:
    sync = _compiled_scene_method(
        "_sync_animation_timer",
        {
            "ANIMATION_INTERVAL_MS": 42,
            "MOVE_ANIMATION_INTERVAL_MS": 16,
        },
    )
    timer = _Timer(active=True, interval=42)
    scene = SimpleNamespace(
        timer=timer,
        scene={"motion_enabled": True},
        _interaction=SimpleNamespace(hovered_id=None),
        _plant_ids=lambda: [],
        hasFocus=lambda: False,
        _hover_opacity={},
        _move_transition=None,
        _animation_tick_required=lambda: False,
    )

    sync(scene)
    assert timer.stops == 1

    scene._animation_tick_required = lambda: True
    sync(scene)
    assert timer.starts == [42]

    sync(scene)
    assert timer.starts == [42]

    scene._move_transition = {"plant_id": "plant-a"}
    sync(scene)
    assert timer.starts[-1] == 16

    scene._move_transition = None
    sync(scene)
    assert timer.starts[-1] == 42


def test_motion_disabled_timer_sync_snaps_hover_highlight_state() -> None:
    sync = _compiled_scene_method(
        "_sync_animation_timer",
        {
            "ANIMATION_INTERVAL_MS": 42,
            "MOVE_ANIMATION_INTERVAL_MS": 16,
        },
    )
    timer = _Timer(active=True, interval=42)
    interaction = SimpleNamespace(
        hovered_id="plant-a",
        focused_id=lambda _ids: None,
    )
    scene = SimpleNamespace(
        timer=timer,
        scene={"motion_enabled": False},
        _interaction=interaction,
        _plant_ids=lambda: ["plant-a"],
        hasFocus=lambda: False,
        _hover_opacity={},
        _move_transition=None,
        _animation_tick_required=lambda: False,
    )

    sync(scene)
    assert scene._hover_opacity == {"plant-a": 1.0}
    assert timer.active is False

    interaction.hovered_id = None
    sync(scene)
    assert scene._hover_opacity == {}


def test_animation_tick_requirement_covers_every_visual_effect() -> None:
    required = _compiled_scene_method("_animation_tick_required")
    scene = SimpleNamespace(
        scene={"motion_enabled": True, "animation_intensity": 0.0},
        isVisible=lambda: True,
        _clamp=lambda value, low, high: max(low, min(high, value)),
        _coerce_float=lambda value, default: float(value),
        _transition_started_at=None,
        _nurture_pulse_started_at=None,
        _move_transition=None,
        _hover_fade_active=lambda: False,
    )

    assert required(scene) is False
    scene.scene["animation_intensity"] = 0.4
    assert required(scene) is True
    scene.scene["animation_intensity"] = 0.0

    for attribute in (
        "_transition_started_at",
        "_nurture_pulse_started_at",
        "_move_transition",
    ):
        setattr(scene, attribute, {"active": True})
        assert required(scene) is True
        setattr(scene, attribute, None)

    scene._hover_fade_active = lambda: True
    assert required(scene) is True
    scene.isVisible = lambda: False
    assert required(scene) is False


def test_scene_refresh_invalidates_only_changed_cache_domains() -> None:
    class Timer:
        @staticmethod
        def singleShot(_delay: int, _callback: Any) -> None:
            return None

    set_scene = _compiled_scene_method(
        "set_scene",
        {"QTimer": Timer, "time": SimpleNamespace(monotonic=lambda: 1.0)},
    )
    base = {
        "plants": [{"plant_id": "plant-a", "slot_index": 0}],
        "asset_paths": {"background": {"path": "/garden.webp"}},
        "stage_transitions": [],
        "motion_enabled": True,
        "health": 0.5,
    }
    calls = {"layout": 0, "inputs": 0, "images": 0}
    interaction = SimpleNamespace(
        pinned_id=None,
        focused_index=-1,
        placing=False,
        reconcile=lambda _ids: None,
        dismiss=lambda: None,
    )

    def layout_signature(payload: dict[str, Any]) -> str:
        return repr(
            (
                [
                    (row.get("slot_index"), row.get("placement"), row.get("asset"))
                    for row in payload.get("plants", [])
                ],
                payload.get("asset_paths", {}).get("background", {}),
                bool(payload.get("show_status_overlay", True)),
            )
        )

    scene = SimpleNamespace(
        scene=dict(base),
        _sanitize_scene_payload=lambda payload: dict(payload),
        _layout_signature_for_scene=layout_signature,
        _asset_payload_signature=repr(base["asset_paths"]),
        _layout_payload_signature=layout_signature(base),
        _invalidate_layout_cache=lambda: calls.__setitem__(
            "layout", calls["layout"] + 1
        ),
        _reset_scene_input_caches=lambda: calls.__setitem__(
            "inputs", calls["inputs"] + 1
        ),
        _clear_image_render_caches=lambda: calls.__setitem__(
            "images", calls["images"] + 1
        ),
        _interaction=interaction,
        _plant_ids=lambda: [
            str(row["plant_id"]) for row in scene.scene.get("plants", [])
        ],
        _hover_opacity={},
        interactive=False,
        _transition_generation=0,
        _transition_started_at=None,
        _transition_duration=1.0,
        _update_scene_accessible_description=lambda: None,
        _sync_animation_timer=lambda: None,
        update=lambda: None,
        _sync_landmark_hotspot=lambda: None,
        cardGeometryChanged=SimpleNamespace(emit=lambda: None),
    )

    health_only = {**base, "health": 0.8}
    set_scene(scene, health_only)
    assert calls == {"layout": 0, "inputs": 0, "images": 0}

    moved = {
        **health_only,
        "plants": [{"plant_id": "plant-a", "slot_index": 1}],
    }
    set_scene(scene, moved)
    assert calls == {"layout": 1, "inputs": 0, "images": 0}

    changed_assets = {
        **moved,
        "asset_paths": {"background": {"path": "/autumn.webp"}},
    }
    set_scene(scene, changed_assets)
    assert calls == {"layout": 2, "inputs": 1, "images": 1}


def test_layout_projection_is_reused_within_unchanged_scene_geometry() -> None:
    source = SCENE_PATH.read_text(encoding="utf-8")
    method = source.split("def _layout_plants", 1)[1].split(
        "def uses_native_destination_selector", 1
    )[0]

    assert "cache_key = (" in method
    assert "if layout_cache is not None and cache_key in layout_cache:" in method
    assert "layout_cache[cache_key] = (" in method
    assert "tuple(rows)" in method
    assert "return associate_current_plants(cached_rows)" in method


def test_cached_layout_reassociates_the_current_nongeometry_plant_payload() -> None:
    class RectF:
        def __init__(self, x: float, y: float, width: float, height: float) -> None:
            self.values = (x, y, width, height)

        def adjusted(self, *_values: float) -> RectF:
            return self

    hit = SimpleNamespace(x=1.0, y=2.0, width=30.0, height=40.0)
    anchor = SimpleNamespace(x=5.0, y=6.0, width=20.0)
    row = SimpleNamespace(
        slot_index=0,
        hit=hit,
        smart_card_anchor=anchor,
    )
    bed = SimpleNamespace(
        selection_region=hit,
        popover_anchor=(11.0, 12.0),
    )
    geometry = SimpleNamespace(bed=lambda _slot: bed)
    layout_calls: list[int] = []

    def plant_layout(*_args: Any, **_kwargs: Any) -> list[Any]:
        layout_calls.append(1)
        return [row]

    class GeometryLayout:
        @staticmethod
        def from_placements(*_args: Any, **_kwargs: Any) -> Any:
            return geometry

    class CanvasRect:
        @staticmethod
        def x() -> float:
            return 0.0

        @staticmethod
        def y() -> float:
            return 0.0

        @staticmethod
        def width() -> float:
            return 800.0

        @staticmethod
        def height() -> float:
            return 600.0

    layout_plants = _compiled_scene_method(
        "_layout_plants",
        {
            "PlantPlacement": object,
            "QRectF": RectF,
            "plant_layout_item": lambda item, slot: {
                **dict(item),
                "slot_index": slot,
            },
            "plant_layout": plant_layout,
            "SceneGeometryLayout": GeometryLayout,
            "Rect": lambda x, y, width, height: SimpleNamespace(
                x=x,
                y=y,
                width=width,
                height=height,
            ),
            "translated_plant_placement": lambda placement, _x, _y: placement,
        },
    )
    interaction = SimpleNamespace(placing=False)
    scene = SimpleNamespace(
        scene={
            "plants": [
                {
                    "plant_id": "plant-old",
                    "slot_index": 0,
                    "name": "Old name",
                    "is_active": False,
                }
            ],
            "asset_paths": {},
        },
        _interaction=interaction,
        _layout_payload_signature="same-geometry",
        _layout_cache=BoundedLruCache(4),
        devicePixelRatioF=lambda: 1.0,
        _planter_family_record=lambda: {},
        _garden_canvas_rect=lambda _width, _height: CanvasRect(),
    )

    first = layout_plants(scene, 800, 600)
    assert first[0][0]["name"] == "Old name"
    assert layout_calls == [1]

    scene.scene = {
        "plants": [
            {
                "plant_id": "plant-current",
                "slot_index": 0,
                "name": "Current name",
                "is_active": True,
            }
        ],
        "asset_paths": {},
    }
    second = layout_plants(scene, 800, 600)

    assert layout_calls == [1]
    assert second[0][0]["name"] == "Current name"
    assert second[0][0]["is_active"] is True
    assert set(scene._plant_hit_rects) == {"plant-current"}
