from __future__ import annotations

import ast
import textwrap
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "ankigarden/ui/dashboard.py"


@lru_cache(maxsize=1)
def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _dashboard_tree() -> ast.Module:
    return ast.parse(_dashboard_source(), filename=str(DASHBOARD_PATH))


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    class_node = next(
        node for node in _dashboard_tree().body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _method_source(class_name: str, method_name: str) -> str:
    source = _dashboard_source()
    return ast.get_source_segment(source, _method_node(class_name, method_name)) or ""


def _compiled_method(
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    scope: dict[str, Any] = {"Any": Any}
    scope.update(namespace or {})
    exec(textwrap.dedent(_method_source(class_name, method_name)), scope)
    return scope[method_name]


def _named_calls(method: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name) and node.func.id == name
            or isinstance(node.func, ast.Attribute) and node.func.attr == name
        )
    ]


def test_dashboard_refresh_reuses_one_indexed_garden_projection() -> None:
    refresh = _method_node("GardenDashboard", "_refresh_all_content")
    payload = _method_node("GardenDashboard", "_plant_scene_payload")
    refresh_source = _method_source("GardenDashboard", "_refresh_all_content")
    payload_source = _method_source("GardenDashboard", "_plant_scene_payload")

    assert len(_named_calls(refresh, "select_garden_ui")) == 1
    assert "plant_snapshots_by_id = {" in refresh_source
    assert "plant_snapshots_by_id=plant_snapshots_by_id" in refresh_source
    assert "streak_bonus_percent=snapshot.streak_bonus_percent" in refresh_source
    assert "if plant_snapshots_by_id is None:" in payload_source
    assert "plant_snapshots_by_id.get(str(plant.plant_id))" in payload_source


def test_hidden_progress_catalogs_refresh_only_after_becoming_dirty() -> None:
    refresh_page = _compiled_method("GardenDashboard", "_refresh_progress_page")
    calls: list[str] = []
    dirty: set[str] = set()

    def refresh_achievements() -> None:
        calls.append("achievements")
        dirty.discard("achievements")

    def refresh_collection() -> None:
        calls.append("collection")
        dirty.discard("collection")

    dashboard = SimpleNamespace(
        _progress_page_dirty=dirty,
        _refresh_achievement_list=refresh_achievements,
        _refresh_collection_list=refresh_collection,
    )

    refresh_page(dashboard, "achievements")
    refresh_page(dashboard, "collection")
    assert calls == []

    dirty.update({"achievements", "collection"})
    refresh_page(dashboard, "achievements")
    refresh_page(dashboard, "achievements")
    refresh_page(dashboard, "collection")
    refresh_page(dashboard, "collection")
    assert calls == ["achievements", "collection"]


def test_dashboard_state_refresh_marks_every_progress_domain_dirty() -> None:
    mark_dirty = _compiled_method("GardenDashboard", "_mark_progress_pages_dirty")
    metric_marks: list[str] = []
    dashboard = SimpleNamespace(
        _progress_page_dirty=set(),
        progress_dialog=SimpleNamespace(
            mark_metric_pages_dirty=lambda: metric_marks.append("metrics")
        ),
    )

    mark_dirty(dashboard)

    assert dashboard._progress_page_dirty == {"achievements", "collection"}
    assert metric_marks == ["metrics"]


class _Timer:
    def __init__(self, active: bool = False) -> None:
        self.active = active
        self.starts = 0
        self.stops = 0

    def isActive(self) -> bool:
        return self.active

    def start(self) -> None:
        self.active = True
        self.starts += 1

    def stop(self) -> None:
        self.active = False
        self.stops += 1


def test_dashboard_timer_runs_only_for_visible_timed_statuses() -> None:
    sync = _compiled_method(
        "GardenDashboard",
        "_sync_fertilizer_timer",
        {"time": SimpleNamespace(time=lambda: 123.0)},
    )
    timer = _Timer()
    timed_checks: list[float] = []
    dashboard = SimpleNamespace(
        _fertilizer_timer=timer,
        isVisible=lambda: False,
        _has_visible_timed_plant_status=lambda *, now: timed_checks.append(now) or True,
    )

    sync(dashboard)
    assert timer.starts == 0
    assert timed_checks == []

    dashboard.isVisible = lambda: True
    sync(dashboard)
    assert timer.starts == 1
    assert timed_checks == [123.0]

    dashboard._has_visible_timed_plant_status = lambda *, now: False
    sync(dashboard)
    assert timer.stops == 1


def test_progress_pages_do_not_poll_when_no_visible_value_uses_wall_time() -> None:
    progress_init = _method_source("GardenDetailsDialog", "__init__")

    assert "_fertilizer_refresh_timer" not in progress_init
    assert "_refresh_timed_fertilizer" not in progress_init


def test_dashboard_timer_keeps_one_second_cadence_without_eager_start() -> None:
    dashboard_init = _method_source("GardenDashboard", "__init__")
    progress_open = _method_source("GardenProgressDialog", "open_page")

    assert "self._fertilizer_timer.setInterval(1_000)" in dashboard_init
    assert "self._fertilizer_timer.start()" not in dashboard_init
    assert "self.refresh()" not in progress_open
    assert "self.navigation.set_current(target)" in progress_open


def test_move_only_refresh_invalidates_lazy_progress_pages_first() -> None:
    source = _method_source("GardenDashboard", "_on_state_changed")

    assert "_mark_progress_pages_dirty()" in source
    assert source.index("_mark_progress_pages_dirty()") < source.index(
        "_refresh_move_scene()"
    )


def test_dashboard_refresh_timings_are_finished_on_failure_paths() -> None:
    for class_name, method_name, operation in (
        ("GardenDashboard", "refresh_all", "dashboard.refresh"),
        (
            "GardenDashboard",
            "_refresh_achievement_list",
            "dashboard.achievements.refresh",
        ),
        (
            "GardenDashboard",
            "_refresh_collection_list",
            "dashboard.collection.refresh",
        ),
    ):
        source = _method_source(class_name, method_name)
        node = _method_node(class_name, method_name)
        assert "RUNTIME_PERFORMANCE.begin()" in source
        assert operation in source
        assert any(isinstance(item, ast.Try) and item.finalbody for item in node.body)
