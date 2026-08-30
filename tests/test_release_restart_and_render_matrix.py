from __future__ import annotations

import ast
import json
import math
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ankigarden.config import DEFAULT_CONFIG, ConfigManager
from ankigarden.game import GardenGameEngine
from ankigarden.models.state import (
    DailyStats,
    GardenState,
    OnboardingStep,
)
from ankigarden.storage import DueObligationStatus, GardenStorage
from ankigarden.ui.plant_display import (
    NURTURED_MARKER_MAX_GROUND_DELTA_RATIO,
    NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO,
    Rect,
    hit_test,
    nurtured_badge_rect,
    nurtured_marker_fallback_rect,
    nurtured_marker_placement,
    nurtured_marker_rect,
    plant_layout,
    planter_draw_rect,
    smart_card_rect,
)
from ankigarden.ui.state_contracts import OnboardingState, onboarding_state_display
from scripts.validate_full_catalog_layout import _scenario_warnings


pytestmark = pytest.mark.release_evidence


ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "ankigarden" / "ui" / "scene.py"
MANIFEST_PATH = ROOT / "ankigarden" / "assets" / "manifest.json"
SCENE_WIDTH = 1_093
SCENE_HEIGHT = 615


class _EngineConfig:
    def __init__(self) -> None:
        self.data = dict(DEFAULT_CONFIG)

    def value(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def nested(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _RestartStorage(GardenStorage):
    def __init__(
        self,
        data_path: Path,
        state: GardenState | None = None,
    ) -> None:
        self.day = "2026-08-08"
        self.day_start_ms = 1_786_100_000_000
        self.now_ms = 1_786_150_000_000
        self.mw = SimpleNamespace(col=None)
        self.config = _EngineConfig()
        self.addon_dir = ROOT / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.data_path = Path(data_path)
        self.user_files_dir = self.data_path.parent
        self.cache_dir = self.user_files_dir / "cache"
        self.metadata_dir = self.user_files_dir
        self.asset_metadata = self.user_files_dir / "asset_metadata.json"
        self.state = state or self._load()
        self._ensure_defaults()

    def restart(self) -> _RestartStorage:
        restarted = _RestartStorage(self.data_path)
        restarted.day = self.day
        restarted.day_start_ms = self.day_start_ms
        restarted.now_ms = self.now_ms
        return restarted

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return DueObligationStatus()

    def load_asset_metadata(self) -> dict[str, Any]:
        return {}

    def save_asset_metadata(self, _data: dict[str, Any]) -> None:
        return None


class _AddonManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def addonFromModule(self, _module: str) -> str:
        return "anki_garden"

    def getConfig(self, _key: str) -> dict[str, Any]:
        return deepcopy(self.config)

    def writeConfig(self, _key: str, payload: dict[str, Any]) -> None:
        self.config = deepcopy(payload)


def _engine(storage: _RestartStorage) -> GardenGameEngine:
    engine = GardenGameEngine(_EngineConfig(), storage)
    engine.assets.release_ready_plant_species = (
        lambda **_kwargs: tuple(engine.SPECIES_PRICES)
    )
    return engine


def _restart(
    engine: GardenGameEngine,
    storage: _RestartStorage,
    *,
    acknowledge_feedback: bool = False,
) -> tuple[GardenGameEngine, _RestartStorage]:
    if acknowledge_feedback and engine.peek_feedback():
        engine.consume_feedback()
    assert json.loads(storage.data_path.read_text("utf-8")) == storage.state.to_dict()
    restarted_storage = storage.restart()
    restarted_engine = _engine(restarted_storage)
    assert restarted_storage.state.pending_feedback == []
    return restarted_engine, restarted_storage


def test_committed_starter_undo_does_not_reuse_a_stale_ledger_checkpoint(
    tmp_path: Path,
) -> None:
    storage = _RestartStorage(
        tmp_path / "garden_state.json",
        GardenState(daily_stats=DailyStats(day="2026-08-08")),
    )
    engine = _engine(storage)
    checkpoint = object()
    rollback_calls: list[object] = []

    storage.reward_ledger_checkpoint = lambda: checkpoint  # type: ignore[method-assign]

    def reject_stale_checkpoint(value: object) -> None:
        rollback_calls.append(value)
        raise AssertionError("a committed checkpoint must not be rolled back")

    storage.rollback_reward_ledger = reject_stale_checkpoint  # type: ignore[method-assign]

    assert engine.enter_starter_nursery()[0]
    assert engine.select_starter_species("bonsai")[0]
    ok, _message, starter, change = engine.place_starter_with_change(0)

    assert ok and starter is not None and change is not None
    assert change._before.ledger_checkpoint is None
    assert engine.undo_starter_placement(change)[0]
    assert rollback_calls == []
    assert storage.state.onboarding.step is OnboardingStep.PLACEMENT
    assert storage.state.onboarding.pending_species == "bonsai"
    assert storage.state.plants == []


def test_committed_release_journey_survives_each_restart_without_replaying_ui_state(
    tmp_path: Path,
) -> None:
    storage = _RestartStorage(
        tmp_path / "garden_state.json",
        GardenState(
            daily_stats=DailyStats(day="2026-08-08"),
            currency_balance=5_000,
        ),
    )
    engine = _engine(storage)

    assert storage.state.onboarding.step is OnboardingStep.INTRODUCTION
    assert engine.enter_starter_nursery()[0]
    engine, storage = _restart(engine, storage)
    assert storage.state.onboarding.step is OnboardingStep.NURSERY

    before_failed_choice = storage.state.to_dict()
    original_save = storage.save
    storage.save = lambda: (_ for _ in ()).throw(OSError("disk full"))
    try:
        assert engine.select_starter_species("bonsai")[0] is False
    finally:
        storage.save = original_save
    assert storage.state.to_dict() == before_failed_choice

    assert engine.select_starter_species("bonsai")[0]
    engine, storage = _restart(engine, storage)
    assert storage.state.onboarding.step is OnboardingStep.PLACEMENT
    assert storage.state.onboarding.pending_species == "bonsai"
    assert storage.state.plants == []

    ok, _message, starter, placement_change = engine.place_starter_with_change(0)
    assert ok and starter is not None and placement_change is not None
    original_name = storage.state.garden_name
    storage.state.garden_name = "Changed after placement"
    assert engine.undo_starter_placement(placement_change)[0] is False
    storage.state.garden_name = original_name
    assert engine.undo_starter_placement(placement_change)[0]
    assert storage.state.onboarding.step is OnboardingStep.PLACEMENT
    assert storage.state.onboarding.pending_species == "bonsai"
    assert storage.state.plants == []

    ok, _message, starter, placement_change = engine.place_starter_with_change(0)
    assert ok and starter is not None and placement_change is not None
    starter_id = starter.plant_id
    repeated_ok, _repeated_message, repeated_starter, repeated_change = (
        engine.place_starter_with_change(0)
    )
    assert repeated_ok and repeated_starter is starter and repeated_change is None
    assert [plant.plant_id for plant in storage.state.plants] == [starter_id]
    engine, storage = _restart(engine, storage, acknowledge_feedback=True)
    assert storage.state.starter_selection_complete is True
    assert [plant.species for plant in storage.state.plants] == ["bonsai"]
    assert storage.state.active_plant_id is None
    assert storage.state.onboarding.step is OnboardingStep.NURTURE
    assert onboarding_state_display(storage.state, 0).state is (
        OnboardingState.STARTER_PLANTED_NOT_NURTURED
    )

    assert engine.set_active_plant(starter_id)[0]
    assert engine.set_active_plant(starter_id)[0]
    engine, storage = _restart(engine, storage, acknowledge_feedback=True)
    starter = engine.plant_story(starter_id)
    assert starter is not None
    assert storage.state.active_plant_id == starter_id
    assert [memory.memory_id for memory in starter.memories].count("nurture:first") == 1
    assert onboarding_state_display(storage.state, 0).state is (
        OnboardingState.NURTURED_PLANT_ASSIGNED
    )
    assert storage.state.onboarding.step is OnboardingStep.COMPLETION

    assert engine.finish_onboarding()[0]
    engine, storage = _restart(engine, storage)
    assert storage.state.onboarding.step is OnboardingStep.DONE
    assert onboarding_state_display(storage.state, 0).state is (
        OnboardingState.ONBOARDING_COMPLETE
    )

    growth_before_move = starter.growth_points
    assert engine.place_plant(starter_id, 1)[0]
    engine, storage = _restart(engine, storage)
    assert engine.plant_story(starter_id).slot_index == 1
    assert storage.state.active_plant_id == starter_id
    assert engine.plant_story(starter_id).growth_points == growth_before_move

    assert engine.purchase_fertilizer(starter_id, "quality")[0]
    assert engine.purchase_fertilizer(starter_id, "premium")[0]
    fertilizer_balance = storage.state.currency_balance
    fertilized_starter = engine.plant_story(starter_id)
    assert fertilized_starter is not None
    assert fertilized_starter.fertilizer is None
    assert fertilized_starter.fertilizer_history == []
    assert [
        (
            batch.effect_id,
            batch.growth_per_card_units,
            batch.total_cards,
            batch.remaining_cards,
        )
        for batch in fertilized_starter.fertilizer_card_batches
    ] == [("fertilizer_quality", 200, 200, 200)]
    assert [
        (
            batch.effect_id,
            batch.growth_per_card_units,
            batch.total_cards,
            batch.remaining_cards,
        )
        for batch in fertilized_starter.fertilizer_card_queue
    ] == [("fertilizer_premium", 300, 400, 400)]
    fertilizer_queue = [
        batch.__dict__.copy()
        for batch in (
            *fertilized_starter.fertilizer_card_batches,
            *fertilized_starter.fertilizer_card_queue,
        )
    ]
    persisted_state = json.loads(storage.data_path.read_text("utf-8"))
    persisted_starter = next(
        plant
        for plant in persisted_state["plants"]
        if plant["plant_id"] == starter_id
    )
    assert persisted_starter["card_effect_queue"] == {
        "fertilizer_batches": fertilizer_queue,
        "booster_remaining_cards": 0,
    }

    engine, storage = _restart(engine, storage, acknowledge_feedback=True)
    starter = engine.plant_story(starter_id)
    assert starter is not None
    assert starter.fertilizer is None
    assert starter.fertilizer_history == []
    assert [batch.__dict__ for batch in starter.fertilizer_card_batches] == [
        fertilizer_queue[0]
    ]
    assert [batch.__dict__ for batch in starter.fertilizer_card_queue] == [
        fertilizer_queue[1]
    ]
    assert starter.card_effect_queue.to_dict() == {
        "fertilizer_batches": fertilizer_queue,
        "booster_remaining_cards": 0,
    }
    far_future = (storage.now_ms + 365 * 24 * 60 * 60 * 1_000) / 1_000
    projected = engine.project_review_growth(starter, now=far_future)
    assert projected.fertilizer_growth == 2
    assert projected.fertilizer_growth_units == 200
    assert [
        batch.remaining_cards
        for batch in (
            *starter.fertilizer_card_batches,
            *starter.fertilizer_card_queue,
        )
    ] == [200, 400]
    assert storage.state.currency_balance == fertilizer_balance
    fertilizer_requests = [
        record
        for record in storage.state.completed_purchase_requests
        if record.outcome.item_id == "quality"
        and record.outcome.category == "Fertilizer"
    ]
    assert len(fertilizer_requests) == 1
    premium_requests = [
        record
        for record in storage.state.completed_purchase_requests
        if record.outcome.item_id == "premium"
        and record.outcome.category == "Fertilizer"
    ]
    assert len(premium_requests) == 1
    assert fertilizer_queue[0]["source_event_key"] == (
        f"purchase-request:{fertilizer_requests[0].request_id}"
    )
    assert fertilizer_queue[1]["source_event_key"] == (
        f"purchase-request:{premium_requests[0].request_id}"
    )
    assert len([
        transaction
        for transaction in storage.state.currency_transactions
        if transaction.event_key
        == f"purchase-request:{fertilizer_requests[0].request_id}"
    ]) == 1
    assert len([
        transaction
        for transaction in storage.state.currency_transactions
        if transaction.event_key
        == f"purchase-request:{premium_requests[0].request_id}"
    ]) == 1

    assert engine.purchase_environment("scenery", "spring")[0]
    purchase_balance = storage.state.currency_balance
    engine, storage = _restart(engine, storage, acknowledge_feedback=True)
    assert "spring" in storage.state.inventory["scenery"]
    assert storage.state.selected_background == "default"
    assert storage.state.currency_balance == purchase_balance
    scenery_requests = [
        record
        for record in storage.state.completed_purchase_requests
        if record.outcome.item_id == "spring"
        and record.outcome.category == "Scenery"
    ]
    assert len(scenery_requests) == 1
    assert len([
        transaction
        for transaction in storage.state.currency_transactions
        if transaction.event_key
        == f"purchase-request:{scenery_requests[0].request_id}"
    ]) == 1

    equipped, message = engine.equip_environment("scenery", "spring")
    assert equipped
    assert message == "Spring Bloom effect is ready for today."
    engine, storage = _restart(engine, storage)
    assert storage.state.selected_background == "default"
    assert storage.state.equipped["background"] == "default"
    assert storage.state.loadout.active_scenery_effect_id == "spring"
    assert storage.state.daily_loadout.queued_scenery_id == ""
    assert storage.state.daily_loadout.queued_for_day == ""

    storage.day = "2026-08-09"
    engine.rollover_if_needed()
    engine, storage = _restart(engine, storage)
    assert storage.state.selected_background == "default"
    assert storage.state.equipped["background"] == "default"
    assert storage.state.loadout.active_scenery_effect_id == "spring"

    assert engine.rename_garden("Moss and Moon")[0]
    engine, storage = _restart(engine, storage)
    assert storage.state.garden_name == "Moss and Moon"
    assert storage.state.garden_setup_version == 1

    assert engine.rename_plant(starter_id, "Briar Moon")[0]
    engine, storage = _restart(engine, storage)
    renamed = engine.plant_story(starter_id)
    assert renamed is not None
    assert renamed.name == "Briar Moon"
    assert renamed.name_customized is True
    assert onboarding_state_display(storage.state, 0).state is (
        OnboardingState.ONBOARDING_COMPLETE
    )

    addon_manager = _AddonManager()
    config = ConfigManager(SimpleNamespace(addonManager=addon_manager))
    config.update({
        "show_home_widget": False,
        "show_progress_notifications": False,
        "show_reviewer_hud": False,
        "reviewer_hud_collapsed": True,
        "reviewer_hud_dock": "left",
        "reduced_motion": True,
        "theme_overrides": {
            "animation_intensity": 0.4,
        },
    })
    reopened_config = ConfigManager(SimpleNamespace(addonManager=addon_manager))
    assert reopened_config.value("show_home_widget") is False
    assert reopened_config.value("show_progress_notifications") is False
    assert reopened_config.value("show_reviewer_hud") is False
    assert reopened_config.value("reviewer_hud_collapsed") is True
    assert reopened_config.value("reviewer_hud_dock") == "left"
    assert reopened_config.value("reduced_motion") is True
    assert reopened_config.nested("theme_overrides", "animation_intensity") == 0.4


def _compiled_scene_method(
    method_name: str,
    namespace: dict[str, Any],
) -> Any:
    source = SCENE_PATH.read_text("utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "GardenSceneWidget":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    child.decorator_list = []
                    isolated = ast.Module(body=[child], type_ignores=[])
                    ast.fix_missing_locations(isolated)
                    globals_dict = dict(namespace)
                    exec(compile(isolated, str(SCENE_PATH), "exec"), globals_dict)
                    return globals_dict[method_name]
    raise AssertionError(f"Missing GardenSceneWidget.{method_name}")


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self._x = float(x)
        self._y = float(y)

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y


class _RectF:
    def __init__(
        self,
        x: float | _RectF,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> None:
        if isinstance(x, _RectF):
            self._x = x._x
            self._y = x._y
            self._width = x._width
            self._height = x._height
            return
        assert y is not None and width is not None and height is not None
        self._x = float(x)
        self._y = float(y)
        self._width = float(width)
        self._height = float(height)

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y

    def width(self) -> float:
        return self._width

    def height(self) -> float:
        return self._height

    def left(self) -> float:
        return self._x

    def right(self) -> float:
        return self._x + self._width

    def top(self) -> float:
        return self._y

    def bottom(self) -> float:
        return self._y + self._height

    def center(self) -> _Point:
        return _Point(
            self._x + self._width / 2,
            self._y + self._height / 2,
        )

    def adjusted(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> _RectF:
        return _RectF(
            self._x + left,
            self._y + top,
            self._width + right - left,
            self._height + bottom - top,
        )

    def as_rect(self) -> Rect:
        return Rect(self._x, self._y, self._width, self._height)


class _Color:
    def __init__(self, *_args: Any) -> None:
        self.alpha = 255

    def setAlpha(self, alpha: int) -> None:
        self.alpha = int(alpha)


class _Pen:
    def __init__(self, *_args: Any) -> None:
        pass


class _PainterPath:
    def moveTo(self, *_args: Any) -> None:
        pass

    def lineTo(self, *_args: Any) -> None:
        pass

    def closeSubpath(self) -> None:
        pass

    def cubicTo(self, *_args: Any) -> None:
        pass


class _Painter:
    def __init__(self) -> None:
        self.ellipses: list[Any] = []
        self.lines: list[tuple[_Point, _Point]] = []
        self.paths: list[Any] = []

    def save(self) -> None:
        pass

    def restore(self) -> None:
        pass

    def setBrush(self, *_args: Any) -> None:
        pass

    def setPen(self, *_args: Any) -> None:
        pass

    def setRenderHint(self, *_args: Any) -> None:
        pass

    def drawEllipse(self, *args: Any) -> None:
        self.ellipses.append(args)

    def drawPath(self, *args: Any) -> None:
        self.paths.append(args)

    def drawLine(self, start: _Point, end: _Point) -> None:
        self.lines.append((start, end))


class _Timer:
    def __init__(self) -> None:
        self.started: list[int] = []

    def isActive(self) -> bool:
        return False

    def start(self, interval: int) -> None:
        self.started.append(interval)


class _SingleShot:
    calls: list[tuple[int, Any]] = []

    @classmethod
    def singleShot(cls, delay: int, callback: Any) -> None:
        cls.calls.append((delay, callback))


_QT = SimpleNamespace(
    BrushStyle=SimpleNamespace(NoBrush=object()),
    PenStyle=SimpleNamespace(NoPen=object(), SolidLine=object()),
)
_SCENE_NAMESPACE = {
    "Any": Any,
    "QPainter": SimpleNamespace(
        RenderHint=SimpleNamespace(Antialiasing=object()),
    ),
    "PlantPlacement": object,
    "QRectF": _RectF,
    "QPointF": _Point,
    "QColor": _Color,
    "QPen": _Pen,
    "QPainterPath": _PainterPath,
    "QTimer": _SingleShot,
    "Qt": _QT,
    "Rect": Rect,
    "GARDEN_THEME": {
        "focus_ring": "#77c9a3",
        "coin_accent": "#dfbd57",
        "action_text": "#ffffff",
        "plant_popover_border": "#77c9a3",
        "plant_popover_bg": "#174b3c",
    },
    "math": math,
    "nurtured_badge_rect": nurtured_badge_rect,
    "nurtured_marker_fallback_rect": nurtured_marker_fallback_rect,
    "nurtured_marker_placement": nurtured_marker_placement,
    "nurtured_marker_rect": nurtured_marker_rect,
    "planter_draw_rect": planter_draw_rect,
    "time": time,
}


def _manifest_rows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = json.loads(MANIFEST_PATH.read_text("utf-8"))["assets"]
    backgrounds = [
        row
        for row in rows
        if row.get("category") == "backgrounds"
        and row.get("release_preferred") is True
    ]
    plants = [row for row in rows if row.get("category") == "plants"]
    assert len(backgrounds) == 1
    assert len(plants) == 60
    return backgrounds[0], plants


def _scene_items(
    target_asset: dict[str, Any],
    selected_plot: int,
    nurtured: bool,
    assets_by_species_stage: dict[tuple[str, str], dict[str, Any]],
    species_order: tuple[str, ...],
) -> list[dict[str, Any]]:
    target_species = str(target_asset["slot"]["species"])
    target_stage = str(target_asset["slot"]["stage"])
    neighbors = iter(species for species in species_order if species != target_species)
    result: list[dict[str, Any]] = []
    for slot in range(6):
        asset = (
            target_asset
            if slot == selected_plot
            else assets_by_species_stage[(next(neighbors), target_stage)]
        )
        result.append({
            "plant_id": f"{asset['asset_id']}-{slot}",
            "slot_index": slot,
            "species": asset["slot"]["species"],
            "stage": asset["slot"]["stage"],
            "placement": asset["placement"],
            "canvas_aspect": float(asset["width"]) / float(asset["height"]),
            "is_active": nurtured and slot == selected_plot,
        })
    return result


def test_every_species_stage_plot_selected_nurtured_and_motion_combination_is_safe() -> None:
    background, assets = _manifest_rows()
    selected_ring = _compiled_scene_method("_draw_selected_bed_ring", _SCENE_NAMESPACE)
    nurtured_marker = _compiled_scene_method("_draw_nurtured_marker", _SCENE_NAMESPACE)
    marker_protected_regions = _compiled_scene_method(
        "nurtured_marker_protected_regions",
        _SCENE_NAMESPACE,
    )
    draw_connector = _compiled_scene_method("_draw_card_connector", _SCENE_NAMESPACE)
    animate_move = _compiled_scene_method("animate_plant_move", _SCENE_NAMESPACE)
    docked_overlay = SimpleNamespace(
        _card_connector_rect=_RectF(12, 180, 1_069, 420),
        _status_rect=_RectF(16, 14, 430, 68),
        _card_popover_placement=SimpleNamespace(docked=True),
    )
    docked_regions = marker_protected_regions(docked_overlay)
    assert [region.as_rect() for region in docked_regions] == [
        Rect(16, 14, 430, 68)
    ]
    docked_overlay._card_popover_placement = SimpleNamespace(docked=False)
    assert [region.as_rect() for region in marker_protected_regions(docked_overlay)] == [
        Rect(12, 180, 1_069, 420),
        Rect(16, 14, 430, 68),
    ]

    assets_by_species_stage = {
        (str(asset["slot"]["species"]), str(asset["slot"]["stage"])): asset
        for asset in assets
    }
    species_order = tuple(sorted({species for species, _stage in assets_by_species_stage}))
    assert len(species_order) == 10
    scenarios = 0
    missing_popovers: set[tuple[str, str, int]] = set()
    marker_reserved_docks: set[tuple[str, str, int]] = set()
    layout_cache: dict[tuple[str, int, bool], list[Any]] = {}
    maximum_marker_distance: tuple[float, tuple[str, int, bool] | None] = (
        0.0,
        None,
    )
    maximum_marker_ground_delta: tuple[
        float,
        tuple[str, int, bool] | None,
    ] = (0.0, None)
    for asset in assets:
        for selected_plot in range(6):
            for selected in (False, True):
                for nurtured in (False, True):
                    for reduced_motion in (False, True):
                        layout_key = (
                            str(asset["asset_id"]),
                            selected_plot,
                            nurtured,
                        )
                        layouts = layout_cache.get(layout_key)
                        if layouts is None:
                            layouts = plant_layout(
                                SCENE_WIDTH,
                                SCENE_HEIGHT,
                                _scene_items(
                                    asset,
                                    selected_plot,
                                    nurtured,
                                    assets_by_species_stage,
                                    species_order,
                                ),
                                background["placement"],
                                composition_count=6,
                                protected_status=False,
                            )
                            assert _scenario_warnings(
                                layouts,
                                width=SCENE_WIDTH,
                                height=SCENE_HEIGHT,
                                count=6,
                                move_mode=False,
                                surface_context="dashboard",
                            ) == []
                            layout_cache[layout_key] = layouts
                        target = next(
                            layout
                            for layout in layouts
                            if layout.slot_index == selected_plot
                        )
                        assert 0 <= target.visible.x <= target.visible.right <= SCENE_WIDTH
                        assert 0 <= target.visible.y <= target.visible.bottom <= SCENE_HEIGHT
                        assert target.contact_plane.contains(*target.ground_anchor)
                        assert target.grounding.contact_shadow.area > 0
                        assert target.grounding.cast_shadow.area > 0
                        assert target.hit.width >= 44 and target.hit.height >= 44
                        assert hit_test(
                            [target],
                            target.hit.x + target.hit.width / 2,
                            target.hit.y + target.hit.height / 2,
                        ) == 0

                        card = None
                        if selected:
                            ring_painter = _Painter()
                            selected_ring(
                                SimpleNamespace(_nurture_pulse_started_at=None),
                                ring_painter,
                                target,
                                nurtured=nurtured,
                            )
                            assert len(ring_painter.ellipses) == 1
                            ring = ring_painter.ellipses[0][0].as_rect()
                            assert 0 <= ring.x and ring.right <= SCENE_WIDTH
                            assert 0 <= ring.y and ring.bottom <= SCENE_HEIGHT

                            selected_hit = target.hit.expanded(8, 8)
                            card_obstacles = [
                                layout.hit.expanded(8, 8)
                                for layout in layouts
                                if layout.slot_index != selected_plot
                            ]
                            if nurtured:
                                family = background["placement"][
                                    "surface_profile"
                                ]["planter_family"]
                                marker_reservation = nurtured_marker_placement(
                                    SCENE_WIDTH,
                                    SCENE_HEIGHT,
                                    target,
                                    planter_rect=planter_draw_rect(target, family),
                                    obstacles=[
                                        layout.visible.expanded(4, 4)
                                        for layout in layouts
                                    ],
                                )
                                card_obstacles.append(
                                    marker_reservation.pulse_bounds.expanded(4, 4)
                                )
                            card = smart_card_rect(
                                SCENE_WIDTH,
                                SCENE_HEIGHT,
                                target.smart_card_anchor.x
                                + target.smart_card_anchor.width / 2,
                                target.smart_card_anchor.y,
                                # The live dashboard caps the in-scene card at
                                # 320 px; wider stress cards are not reachable.
                                card_width=320,
                                card_height=220,
                                obstacles=card_obstacles,
                                protected_obstacle=selected_hit,
                            )
                            if card is None:
                                unavailable_case = (
                                    str(asset["slot"]["species"]),
                                    str(asset["slot"]["stage"]),
                                    selected_plot + 1,
                                )
                                if nurtured:
                                    marker_reserved_docks.add(unavailable_case)
                                else:
                                    missing_popovers.add(unavailable_case)
                            else:
                                card_rect = Rect(*card)
                                assert not card_rect.intersects(selected_hit)
                                assert 0 <= card_rect.x and card_rect.right <= SCENE_WIDTH
                                assert 0 <= card_rect.y and card_rect.bottom <= SCENE_HEIGHT

                                connector_painter = _Painter()
                                plant_rect = _RectF(
                                    target.hit.x,
                                    target.hit.y,
                                    target.hit.width,
                                    target.hit.height,
                                )
                                if card_rect.right <= target.hit.x:
                                    connector_side = "left"
                                    connector_end = (
                                        card_rect.right,
                                        max(
                                            card_rect.y + 20,
                                            min(
                                                target.hit.y + target.hit.height / 2,
                                                card_rect.bottom - 20,
                                            ),
                                        ),
                                    )
                                elif card_rect.x >= target.hit.right:
                                    connector_side = "right"
                                    connector_end = (
                                        card_rect.x,
                                        max(
                                            card_rect.y + 20,
                                            min(
                                                target.hit.y + target.hit.height / 2,
                                                card_rect.bottom - 20,
                                            ),
                                        ),
                                    )
                                elif card_rect.bottom <= target.hit.y:
                                    connector_side = "above"
                                    connector_end = (
                                        max(
                                            card_rect.x + 20,
                                            min(
                                                target.hit.x + target.hit.width / 2,
                                                card_rect.right - 20,
                                            ),
                                        ),
                                        card_rect.bottom,
                                    )
                                else:
                                    connector_side = "below"
                                    connector_end = (
                                        max(
                                            card_rect.x + 20,
                                            min(
                                                target.hit.x + target.hit.width / 2,
                                                card_rect.right - 20,
                                            ),
                                        ),
                                        card_rect.y,
                                    )
                                connector_scene = SimpleNamespace(
                                    _interaction=SimpleNamespace(
                                        placing=False,
                                        pinned_id=f"{asset['asset_id']}-{selected_plot}",
                                    ),
                                    _card_connector_rect=_RectF(*card),
                                    _plant_hit_rects={
                                        f"{asset['asset_id']}-{selected_plot}": plant_rect
                                    },
                                    _card_connector_plant_id=(
                                        f"{asset['asset_id']}-{selected_plot}"
                                    ),
                                    _card_popover_placement=SimpleNamespace(
                                        docked=False,
                                        chosen_side=connector_side,
                                        connector_end=connector_end,
                                    ),
                                )
                                draw_connector(connector_scene, connector_painter)
                                assert len(connector_painter.paths) == 1

                        if nurtured:
                            marker_painter = _Painter()
                            family = background["placement"]["surface_profile"][
                                "planter_family"
                            ]
                            marker_scene = SimpleNamespace(
                                _nurture_pulse_id="",
                                _nurture_pulse_started_at=None,
                                _slot_placements={
                                    layout.slot_index: layout for layout in layouts
                                },
                                _planter_family_record=lambda: family,
                                _card_connector_rect=(
                                    _RectF(*card) if card is not None else None
                                ),
                                _status_rect=None,
                                _card_popover_placement=SimpleNamespace(docked=False),
                                _asset_path=lambda _key: None,
                                width=lambda: SCENE_WIDTH,
                                height=lambda: SCENE_HEIGHT,
                            )
                            marker_scene.nurtured_marker_protected_regions = (
                                lambda: marker_protected_regions(marker_scene)
                            )
                            nurtured_marker(
                                marker_scene,
                                marker_painter,
                                target,
                                {"plant_id": f"{asset['asset_id']}-{selected_plot}"},
                                scene_layouts=layouts,
                            )
                            placement = marker_scene._nurtured_marker_placement
                            expected_side = placement.side
                            assert expected_side in {"left", "right"}
                            expected_orientation = (
                                "spout-right"
                                if expected_side == "left"
                                else "spout-left"
                            )
                            expected_asset = (
                                "nurtured_marker_spout_right"
                                if expected_side == "left"
                                else "nurtured_marker"
                            )
                            assert placement.used_fallback is False
                            assert placement.side == expected_side
                            assert placement.orientation == expected_orientation
                            assert placement.asset_key == expected_asset
                            assert 44 <= placement.rect.width <= 88
                            assert placement.rect.width == placement.rect.height
                            assert 0 <= placement.pulse_bounds.x
                            assert placement.pulse_bounds.right <= SCENE_WIDTH
                            assert 0 <= placement.pulse_bounds.y
                            assert placement.pulse_bounds.bottom <= SCENE_HEIGHT
                            blockers = [
                                layout.visible.expanded(4, 4) for layout in layouts
                            ]
                            if card is not None:
                                blockers.append(Rect(*card).expanded(4, 4))
                            assert not any(
                                placement.pulse_bounds.intersects(blocker)
                                for blocker in blockers
                            )
                            planter = planter_draw_rect(target, family)
                            marker_center_x = (
                                placement.rect.x + placement.rect.width / 2
                            )
                            marker_ground_y = (
                                placement.rect.y + placement.rect.height * 0.916
                            )
                            plant_distance = math.hypot(
                                marker_center_x - target.ground_anchor[0],
                                marker_ground_y - target.ground_anchor[1],
                            )
                            distance_ratio = plant_distance / planter.width
                            distance_case = (
                                asset["asset_id"],
                                selected_plot,
                                selected,
                            )
                            maximum_marker_distance = max(
                                maximum_marker_distance,
                                (distance_ratio, distance_case),
                                key=lambda item: item[0],
                            )
                            ground_delta_ratio = abs(
                                marker_ground_y - target.ground_anchor[1]
                            ) / placement.rect.width
                            maximum_marker_ground_delta = max(
                                maximum_marker_ground_delta,
                                (ground_delta_ratio, distance_case),
                                key=lambda item: item[0],
                            )
                            if expected_side == "left":
                                assert marker_center_x < target.ground_anchor[0]
                            else:
                                assert marker_center_x > target.ground_anchor[0]
                            assert len(marker_painter.ellipses) == 2
                            contact_shadow = marker_painter.ellipses[0][0].as_rect()
                            assert contact_shadow == placement.contact_shadow
                            assert 0 <= contact_shadow.x
                            assert contact_shadow.right <= SCENE_WIDTH
                            assert 0 <= contact_shadow.y
                            assert contact_shadow.bottom <= SCENE_HEIGHT
                            marker = marker_painter.ellipses[1][0].as_rect()
                            assert 0 <= marker.x and marker.right <= SCENE_WIDTH
                            assert 0 <= marker.y and marker.bottom <= SCENE_HEIGHT
                            assert not marker.intersects(target.visible)

                        _SingleShot.calls = []
                        timer = _Timer()
                        motion_scene = SimpleNamespace(
                            scene={"motion_enabled": not reduced_motion},
                            _move_transition=None,
                            timer=timer,
                            isVisible=lambda: True,
                            _sync_animation_timer=lambda: timer.start(16),
                            _finish_move_transition=lambda: None,
                            update=lambda: None,
                        )
                        animate_move(motion_scene, "target", 0, selected_plot)
                        if reduced_motion:
                            assert motion_scene._move_transition is None
                            assert timer.started == []
                            assert _SingleShot.calls == []
                        else:
                            assert motion_scene._move_transition is not None
                            assert timer.started == [16]
                            assert [delay for delay, _callback in _SingleShot.calls] == [220]
                        scenarios += 1

    assert scenarios == 60 * 6 * 2 * 2 * 2 == 2_880
    assert missing_popovers == set(), sorted(missing_popovers)
    assert marker_reserved_docks == set(), sorted(marker_reserved_docks)
    assert (
        maximum_marker_distance[0]
        <= NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO
    ), maximum_marker_distance
    assert (
        maximum_marker_ground_delta[0]
        <= NURTURED_MARKER_MAX_GROUND_DELTA_RATIO
    ), maximum_marker_ground_delta
