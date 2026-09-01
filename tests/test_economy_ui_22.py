import ast
from pathlib import Path
from types import SimpleNamespace

from ankigarden.balance_catalog import COSMETICS, COSMETIC_BY_ID
from ankigarden.environment import CatalogItem
from ankigarden.models.state import CardEffectBatch, GardenState
from ankigarden.ui.economy_presenters import (
    bed_unlock_rows,
    cosmetic_rows,
    landmark_summary,
    mastery_summary,
)
from ankigarden.ui.plant_presenters import fertilizer_status
from ankigarden.ui.reviewer_hud import _active_effect_rows
from ankigarden.ui.session_summary import EffectRow
from ankigarden.ui.session_summary_card import session_effect_remaining_text


def batch(effect_id: str, remaining: int, total: int) -> CardEffectBatch:
    return CardEffectBatch(effect_id, 100, total, remaining)


def test_fertilizer_status_is_card_counted_fifo_and_time_invariant() -> None:
    engine = SimpleNamespace(FERTILIZERS={
        "basic": SimpleNamespace(name="Basic Fertilizer"),
        "quality": SimpleNamespace(name="Quality Fertilizer"),
    })
    plant = SimpleNamespace(
        fertilizer_card_batches=(
            batch("fertilizer_basic", 17, 100),
            batch("fertilizer_basic", 80, 100),
        ),
        fertilizer_card_queue=(batch("fertilizer_quality", 200, 200),),
    )

    early = fertilizer_status(engine, plant, now=1)
    late = fertilizer_status(engine, plant, now=9_999_999_999)

    assert early == late
    assert early.duration == "97 cards left"
    assert early.cards_remaining == 97
    assert early.total_cards == 200
    assert early.queued_doses == 1
    assert early.seconds_remaining == 0
    assert "queued dose" in early.accessible_text


def test_reviewer_effect_rows_use_cards_and_garden_rhythm() -> None:
    plant = SimpleNamespace(
        fertilizer_card_batches=(batch("fertilizer_basic", 23, 100),),
        booster_card_batches=(),
    )
    engine = SimpleNamespace(
        state=SimpleNamespace(wind_chime_progress=4),
        active_garden_feature_id=lambda: "wind_chime",
    )
    award = SimpleNamespace(
        weather_growth_units=0,
        scenery_growth_units=0,
        streak_growth_units=20,
    )

    rows = _active_effect_rows(engine, plant, award, now_ms=1)

    assert ("Fertilizer · 23 cards", "fertilizer_basic") in rows
    assert ("Garden Rhythm · +0.2 growth", "") in rows
    assert not any(" h" in label or " min" in label for label, _asset in rows)


def test_session_effect_copy_never_uses_wall_clock() -> None:
    effect = EffectRow(
        "fertilizer",
        "fertilizer:plant:basic",
        "Basic Fertilizer",
        "",
        remaining_seconds=3_600,
        remaining_cards=1,
        expires_at_epoch_seconds=99_999_999_999,
    )

    assert session_effect_remaining_text(effect, now_epoch_seconds=0) == "1 card left"
    assert session_effect_remaining_text(effect, now_epoch_seconds=99_999_999_999) == "1 card left"


def test_beds_are_presented_as_earned_milestones() -> None:
    state = SimpleNamespace(unlocked_slots=3)
    rows = bed_unlock_rows(state)

    assert [row.unlocked for row in rows] == [True, True, True, False, False, False]
    assert rows[3].requirement == "First unique species reaches Full Bloom"
    assert rows[5].requirement == "6 unique species reach Full Bloom"
    assert rows[2].action_text == "Unlock Bed 3"
    assert rows[2].artwork_id == "bg_verdant_twilight_any_soil_master_v6"
    assert rows[2].unlock_policy == "automatic_achievement"
    assert rows[2].price_coins is None
    assert rows[2].can_commit is False


def test_cosmetic_projection_keeps_display_separate_from_bonus() -> None:
    state = GardenState()
    state.inventory["cosmetics"] = ["garden_bench"]
    state.loadout.display_decoration_id = "garden_bench"
    state.loadout.active_garden_bonus_id = "watering_station"

    rows = {row.item_id: row for row in cosmetic_rows(state)}

    assert rows["garden_bench"].owned
    assert rows["garden_bench"].displayed
    assert rows["garden_bench"].price == 150
    assert state.loadout.active_garden_bonus_id == "watering_station"


def _compiled_dashboard_method(
    method_name: str,
    globals_map: dict[str, object],
):
    source = Path("ankigarden/ui/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    function.decorator_list = []
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_map)
    exec(compile(module, "<dashboard-method>", "exec"), namespace)
    return namespace[method_name]


def test_collection_appearance_picker_projects_and_owns_cosmetics() -> None:
    project = _compiled_dashboard_method(
        "_cosmetic_appearance_items",
        {"CatalogItem": CatalogItem, "COSMETICS": COSMETICS},
    )
    owns = _compiled_dashboard_method(
        "_owns_appearance_item",
        {"CatalogItem": CatalogItem, "COSMETIC_BY_ID": COSMETIC_BY_ID},
    )
    items = {item.item_id: item for item in project()}
    state = GardenState()
    state.inventory["cosmetics"] = ["garden_bench"]
    dialog = SimpleNamespace(
        storage=SimpleNamespace(state=state),
        engine=SimpleNamespace(owns_environment=lambda _kind, _item_id: False),
    )

    assert set(items) == {str(item.cosmetic_id) for item in COSMETICS}
    assert items["garden_bench"].name == "Garden Bench"
    assert items["garden_bench"].kind == "garden_feature"
    assert owns(dialog, items["garden_bench"]) is True
    assert owns(dialog, items["birdhouse"]) is False


def test_collection_appearance_rebuild_and_preview_use_cosmetic_authority() -> None:
    source = Path("ankigarden/ui/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    rebuild_calls = {
        node.func.attr
        for node in ast.walk(methods["_rebuild_options"])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }
    preview_names = {
        node.id
        for node in ast.walk(methods["_refresh_preview"])
        if isinstance(node, ast.Name)
    }

    assert "_cosmetic_appearance_items" in rebuild_calls
    assert "_owns_appearance_item" in rebuild_calls
    assert "COSMETIC_BY_ID" in preview_names


def test_collection_appearance_apply_is_one_engine_transaction() -> None:
    source = Path("ankigarden/ui/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    apply_method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_draft"
    )
    engine_calls = [
        node.func.attr
        for node in ast.walk(apply_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self"
        and node.func.value.attr == "engine"
    ]

    assert engine_calls == ["apply_garden_appearance"]


def _appearance_apply_test_dialog(engine: object) -> tuple[SimpleNamespace, list[str]]:
    messages: list[str] = []
    failure_copy = _compiled_dashboard_method(
        "_appearance_apply_failure_copy",
        {},
    )

    class PreviewFeedback:
        def setFocus(self) -> None:
            return None

        def accessibleDescription(self) -> str:
            return messages[-1]

    dialog = SimpleNamespace(
        _loadout_save_pending=False,
        _loadout_failure=False,
        _draft_weather="wind_chime",
        _draft_scenery="verdant_twilight",
        _draft_visibility={"garden_feature": True, "scenery": True},
        engine=engine,
        preview_feedback=PreviewFeedback(),
        accessibility_announcer=SimpleNamespace(
            announce=lambda *_args, **_kwargs: None,
        ),
        set_dialog_in_flight=lambda _enabled: None,
        setProperty=lambda _name, _value: None,
        _sync_dirty_state=lambda: None,
        _show_preview_feedback=lambda message, **_kwargs: messages.append(message),
        _appearance_apply_failure_copy=failure_copy,
    )
    return dialog, messages


def test_collection_appearance_apply_shows_engine_reason_and_rollback_outcome() -> None:
    apply_draft = _compiled_dashboard_method(
        "_apply_draft",
        {
            "AnnouncementPriority": SimpleNamespace(ASSERTIVE="assertive"),
            "FeedbackTone": SimpleNamespace(ERROR="error"),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )
    reason = "That Display Decoration is not owned."
    dialog, messages = _appearance_apply_test_dialog(
        SimpleNamespace(
            apply_garden_appearance=lambda *_args, **_kwargs: (False, reason),
        )
    )

    apply_draft(dialog)

    assert messages == [
        f"{reason} Your current Garden appearance is unchanged."
    ]
    assert dialog._loadout_failure is True


def test_collection_appearance_apply_exception_uses_safe_generic_error() -> None:
    apply_draft = _compiled_dashboard_method(
        "_apply_draft",
        {
            "AnnouncementPriority": SimpleNamespace(ASSERTIVE="assertive"),
            "FeedbackTone": SimpleNamespace(ERROR="error"),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )

    def raise_internal_error(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("private persistence detail")

    dialog, messages = _appearance_apply_test_dialog(
        SimpleNamespace(apply_garden_appearance=raise_internal_error)
    )

    apply_draft(dialog)

    assert messages == [
        "Could not apply changes. "
        "Your current Garden appearance is unchanged."
    ]
    assert "private persistence detail" not in messages[0]
    assert dialog._loadout_failure is True


def test_endgame_presenters_consume_engine_catalog_summaries() -> None:
    engine = SimpleNamespace(
        landmark_catalog_summary=lambda: {
            "unlocked": True,
            "stored_growth_units": 12_500,
            "auto_contribute": False,
            "selected_landmark_id": "mossy_stone_path",
            "next_landmark_id": "mossy_stone_path",
            "displayed_landmark_id": "",
            "completed_landmark_ids": [],
            "contributed_growth_units": 2_500,
            "required_growth_units": 2_500_000,
            "ready_to_complete": False,
            "items": ({
                "landmark_id": "mossy_stone_path",
                "display_name": "Mossy Stone Path",
                "growth_cost_units": 2_500_000,
                "coin_cost": 250,
                "completed": False,
                "selected": True,
                "displayed": False,
            },),
        },
        mastery_catalog_summary=lambda: {
            "stored_growth_units": 12_500,
            "species": ({
                "species_id": "bonsai",
                "eligible": True,
                "current_rank_id": "bronze",
                "next_rank_id": "silver",
            },),
        },
    )

    landmark = landmark_summary(engine)
    mastery = mastery_summary(engine)

    assert landmark.rows[0].name == "Mossy Stone Path"
    assert landmark.contributed_growth_units == 2_500
    assert mastery.rows[0].next_rank_id == "silver"
