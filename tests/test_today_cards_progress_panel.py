from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "ankigarden/ui/dashboard.py"
SOURCE = DASHBOARD_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(DASHBOARD_PATH))


def _class_node(name: str) -> ast.ClassDef:
    return next(
        node
        for node in TREE.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    return next(
        node
        for node in _class_node(class_name).body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _method_source(class_name: str, method_name: str) -> str:
    return ast.get_source_segment(SOURCE, _method_node(class_name, method_name)) or ""


def _function_node(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compiled_function(name: str, namespace: dict[str, Any]) -> Any:
    scope = {"Any": Any, **namespace}
    function_source = ast.get_source_segment(SOURCE, _function_node(name)) or ""
    exec(textwrap.dedent(function_source), scope)
    return scope[name]


def _class_constant(class_name: str, constant_name: str) -> Any:
    assignment = next(
        node
        for node in _class_node(class_name).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == constant_name
            for target in node.targets
        )
    )
    return ast.literal_eval(assignment.value)


def _today_cards_factory(
    status: str,
    heading: str,
    primary: str,
    secondary: tuple[str, ...] = (),
    progress_value: int = 0,
    progress_maximum: int = 0,
    finds_line: str = "",
    finds_detail: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        heading=heading,
        primary=primary,
        secondary=secondary,
        progress_value=progress_value,
        progress_maximum=progress_maximum,
        finds_line=finds_line,
        finds_detail=finds_detail,
        reviewed_count=176,
        remaining_count=18,
        completion_reward_coins=10,
    )


def _page_projection_function() -> Any:
    garden_features = {
        "rain": SimpleNamespace(name="Watering Station"),
        "snow": SimpleNamespace(name="Herbalist’s Hourglass"),
    }
    scenery = {
        "spring": SimpleNamespace(name="Spring Bloom"),
        "moon": SimpleNamespace(name="Full Moon Garden"),
    }
    return _compiled_function(
        "_today_cards_page_projection",
        {
            "TodayCardsPageProjection": lambda **values: SimpleNamespace(**values),
            "TodayCardsProjection": _today_cards_factory,
            "project_today_cards": lambda _state, now_ms=None: _today_cards_factory(
                "in_progress",
                "TODAY’S CARDS",
                "18 cards remaining",
                (
                    "176 cards complete",
                    "+10 Garden Coins when today’s cards are complete",
                ),
                finds_line="Garden Finds · 2 of 3 today",
            ),
            "_catalog_display_name": lambda catalog, item_id: catalog[item_id].name,
            "_today_cutoff_text": lambda value: f"cutoff:{value}",
            "GARDEN_FEATURE_CATALOG": garden_features,
            "SCENERY_CATALOG": scenery,
            "DEFAULT_GARDEN_FEATURE_ID": "rain",
            "DEFAULT_SCENERY_ID": "spring",
        },
    )


def test_today_cards_is_a_lazy_garden_progress_page() -> None:
    metric_tabs = _class_constant("GardenDetailsDialog", "METRIC_TABS")
    page_labels = _class_constant("GardenProgressDialog", "PAGE_LABELS")
    refresh_source = _method_source("GardenDetailsDialog", "_refresh_metric_page")

    assert ("today", "Today’s Cards") in metric_tabs
    assert ("today", "Today’s Cards") in page_labels
    assert 'normalized == "today"' in refresh_source
    assert "self._refresh_today(layout)" in refresh_source


def test_currency_footer_visibility_uses_page_identity_not_an_index() -> None:
    source = _method_source("GardenDetailsDialog", "_sync_context_action")

    assert 'key == "currency"' in source
    assert "index == 2" not in source


def test_today_page_copy_has_no_goal_or_find_drought_language() -> None:
    method = _method_node("GardenDetailsDialog", "_refresh_today")
    literals = "\n".join(
        node.value
        for node in ast.walk(method)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ).casefold()

    for forbidden in (
        "all clear",
        "daily care",
        "required cards",
        "answers",
        "drought",
        "52 / 75",
    ):
        assert forbidden not in literals
    assert "at start" in literals
    assert "remaining today" in literals
    assert "anki cutoff" in literals
    assert "queued for tomorrow" in literals


def test_today_projection_shows_exact_find_state_and_changed_queue_only() -> None:
    project = _page_projection_function()
    state = SimpleNamespace(
        daily_completion=SimpleNamespace(
            starting_required_cards=194,
            remaining_required_reviews=16,
            remaining_learning_steps=0,
            future_learning_steps_before_cutoff=2,
            cutoff_at_ms=123_000,
        ),
        daily_stats=SimpleNamespace(day="2026-08-28"),
            daily_loadout=SimpleNamespace(
                scheduler_day="2026-08-28",
                locked_at_ms=100,
                garden_bonus_anki_day_id="2026-08-28",
                garden_bonus_locked_at_ms=100,
                pending_garden_feature_id="snow",
            queued_scenery_id="moon",
        ),
        selected_garden_feature="rain",
        selected_background="spring",
    )
    storage = SimpleNamespace(state=state, current_day_end_ms=lambda: 999_000)
    engine = SimpleNamespace(
        garden_find_status=lambda: SimpleNamespace(
            finds_today=3,
            daily_cap=3,
            daily_limit_reached=True,
            next_card_guaranteed=False,
        ),
        locked_environment_id=lambda kind: "rain" if kind == "garden_feature" else "spring",
    )

    result = project(engine, storage)

    assert result.starting_cards == 194
    assert result.remaining_cards == 18
    assert result.cutoff_text == "cutoff:123000"
    assert result.status.finds_line == (
        "Garden Finds · 3 of 3 today · Daily limit reached"
    )
    assert result.status.finds_detail == ""
    assert result.status.heading == "TODAY’S CARDS"
    assert result.status.primary == "18 cards remaining"
    assert result.status.secondary == ("176 cards complete",)
    assert result.weather_name == "Watering Station"
    assert result.scenery_name == "Spring Bloom"
    assert result.loadout_locked is True
    assert result.queued_weather_name == "Herbalist’s Hourglass"
    assert result.queued_scenery_name == "Full Moon Garden"
    assert result.claim_state == "pending"


def test_today_projection_uses_unavailable_copy_when_verification_fails() -> None:
    project = _page_projection_function()
    state = SimpleNamespace(
        daily_completion=SimpleNamespace(cutoff_at_ms=0),
        daily_stats=SimpleNamespace(day="2026-08-28"),
        daily_loadout=SimpleNamespace(
            scheduler_day="",
            locked_at_ms=0,
            pending_garden_feature_id="",
            queued_scenery_id="",
        ),
        selected_garden_feature="rain",
        selected_background="spring",
    )
    storage = SimpleNamespace(state=state, current_day_end_ms=lambda: 999_000)
    engine = SimpleNamespace(
        garden_find_status=lambda: SimpleNamespace(
            finds_today=2,
            daily_cap=3,
            daily_limit_reached=False,
            next_card_guaranteed=True,
        ),
        locked_environment_id=lambda kind: "rain" if kind == "garden_feature" else "spring",
    )

    result = project(engine, storage, verification_failed=True)

    assert result.status.heading == "CARD STATUS UNAVAILABLE"
    assert result.status.primary == (
        "Anki Garden could not verify today’s cards. "
        "Normal Garden Growth is unaffected."
    )
    assert result.status.finds_line == "Garden Find · Next card guaranteed"
    assert result.starting_cards is None
    assert result.remaining_cards is None
    assert result.claim_state == "unavailable"


def test_today_page_defers_an_incomplete_tomorrow_card_below_the_first_fold() -> None:
    source = _method_source("GardenDetailsDialog", "_refresh_today")

    assert 'queued_spacer.setProperty("completeSectionSpacer", True)' in source
    assert "self._register_complete_section_boundary(queued, queued_spacer)" in source
