from __future__ import annotations

import ast
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from ankigarden.game import GROWTH_THRESHOLDS
from ankigarden.ui.plant_presenters import fertilizer_status


DASHBOARD = (
    Path(__file__).resolve().parents[1] / "ankigarden" / "ui" / "dashboard.py"
)


def _compiled_function(
    function_name: str,
    namespace: dict[str, object] | None = None,
):
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    scope: dict[str, object] = dict(namespace or {})
    exec(compile(module, str(DASHBOARD), "exec"), scope)
    return scope[function_name]


def test_preview_bounds_expand_valid_art_and_reject_invalid_metadata() -> None:
    crop = _compiled_function(
        "_padded_preview_bounds",
        {"Any": Any, "isfinite": isfinite},
    )

    assert tuple(round(value, 3) for value in crop((0.4, 0.6, 0.2, 0.2))) == (
        0.38,
        0.58,
        0.24,
        0.24,
    )
    assert crop(None) == (0.0, 0.0, 1.0, 1.0)
    assert crop((float("nan"), 0.2, 0.4, 0.4)) == (0.0, 0.0, 1.0, 1.0)


def test_nursery_catalog_helpers_cover_shortfalls_receipts_empty_states_and_folds() -> None:
    compact_shortfall = _compiled_function("_compact_catalog_shortfall")
    receipt_actions = _compiled_function("_nursery_collection_receipt_actions")
    empty_copy = _compiled_function("_nursery_empty_state_copy")
    product_visible = _compiled_function("_nursery_catalog_product_visible")
    prioritize_environment = _compiled_function(
        "_prioritize_nursery_environment_items",
        {"CatalogItem": Any, "Callable": Callable},
    )
    fold_plan = _compiled_function("_catalog_fold_alignment_plan")

    assert compact_shortfall(1, 0) == "Need 1 more Garden Coin"
    assert compact_shortfall(100, 0) == "Need 100 more Garden Coins"
    assert compact_shortfall(100, 100) == ""
    assert receipt_actions(False) == ("Place in garden", "View collection")
    assert receipt_actions(True) == ("Place in garden",)
    complete_collection = SimpleNamespace(
        species_text="10 of 10 species discovered",
        collection_entries_text="30 of 39 collection entries discovered",
    )
    assert empty_copy(
        starter_mode=False,
        collection_complete=True,
        collection_projection=complete_collection,
    ) == (
        "10 of 10 species discovered",
        "30 of 39 collection entries discovered",
    )
    assert empty_copy(
        starter_mode=False,
        collection_complete=False,
        collection_projection=SimpleNamespace(
            species_text="4 of 10 species discovered",
        ),
    ) == (
        "New species are being prepared",
        "4 of 10 species discovered",
    )
    assert product_visible("purchase", "soft_breeze", "clear_skies")
    assert not product_visible("purchase", "clear_skies", "clear_skies")
    assert product_visible("drop", "rain", "clear_skies")
    items = [
        SimpleNamespace(item_id="harvest_bell", purchasable=True),
        SimpleNamespace(item_id="firefly_lantern", purchasable=False),
        SimpleNamespace(item_id="seedling_sign", purchasable=False),
        SimpleNamespace(item_id="wind_chime", purchasable=True),
    ]
    assert [
        item.item_id
        for item in prioritize_environment(
            items,
            displayed_item_id="seedling_sign",
            owned_item_ids={"seedling_sign"},
        )
    ] == [
        "seedling_sign",
        "harvest_bell",
        "firefly_lantern",
        "wind_chime",
    ]
    assert fold_plan(
        viewport_height=300,
        row_spans=((220, 308),),
        window_height=525,
        minimum_window_height=500,
        maximum_window_height=550,
    ) == (533, 0, False)
    assert fold_plan(
        viewport_height=300,
        row_spans=((288, 388),),
        window_height=500,
        minimum_window_height=500,
        maximum_window_height=500,
    ) == (None, 12, False)
    assert fold_plan(
        viewport_height=300,
        row_spans=((200, 400),),
        window_height=500,
        minimum_window_height=500,
        maximum_window_height=500,
    ) == (None, 0, True)


def test_recent_find_rows_render_canonical_artwork_refs() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_garden_find_preview_label"
    )
    helper_source = ast.get_source_segment(source, helper) or ""
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "GardenDetailsDialog"
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_add_recent_garden_finds"
    )
    method_source = ast.get_source_segment(source, method) or ""

    assert 'getattr(finding, "artwork_ref", "")' in helper_source
    assert '"ui_growth_charge_small": "growth_charge_small"' in helper_source
    assert 'artwork_ref not in {' in helper_source
    assert '_item_preview_label(' in helper_source
    assert 'if pool_id == "environment" and artwork_ref:' in helper_source
    assert '"resolve_garden_feature_preview_asset"' in helper_source
    assert 'label.setProperty("gardenFindArtworkRef", artwork_ref)' in helper_source
    assert "_garden_find_preview_label(self.engine, finding)" in method_source
    assert 'grid.addWidget(find_cell, row, 1)' in method_source


def test_collection_growth_items_render_their_canonical_artwork() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenDashboard"
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_collectible_registry_card"
    )
    method_source = ast.get_source_segment(source, method) or ""

    assert 'if definition.category == "growth_items":' in method_source
    assert 'artwork_ref = str(definition.source_id or "")' in method_source
    assert "icon = _item_preview_label(" in method_source
    assert 'icon.setProperty("collectibleItemArtwork", True)' in method_source
    assert 'icon.setProperty("collectibleItemArtworkRef", artwork_ref)' in method_source
    assert '"growth_items": "growth"' not in method_source


def test_collection_uses_persistent_plant_and_landmark_subtabs() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    for class_name in (
        "CollectionSubtabs",
        "PlantCollectionPane",
        "GardenLandmarksPane",
        "CollectionSection",
        "LandmarkProjectOverview",
        "LandmarkTierList",
        "LandmarkTierRow",
    ):
        assert class_name in classes
    assert "_growth_projects_panel" not in source
    assert 'setPlaceholderText("Search plants")' in source
    plant_pane_source = ast.get_source_segment(
        source,
        classes["PlantCollectionPane"],
    ) or ""
    assert "wide_columns=4" in plant_pane_source
    assert "minimum_item_width=160" in plant_pane_source
    assert "minimum_card_height=168" in plant_pane_source

    dashboard = classes["GardenDashboard"]
    refresh = next(
        node
        for node in dashboard.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_refresh_collection_list_content"
    )
    refresh_source = ast.get_source_segment(source, refresh) or ""
    assert "CollectionFilterControls(" in refresh_source
    assert "collection_list.add_full_width(\n            self.collection_growth_projects_panel" not in refresh_source
    assert "self.collection_section.set_plant_summary(" in refresh_source
    assert "self._refresh_garden_landmarks_content()" in refresh_source
    assert "if refresh_landmarks:" in refresh_source

    filter_methods = "\n".join(
        ast.get_source_segment(source, node) or ""
        for node in dashboard.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_set_collection_filter",
            "_set_collection_category",
            "_set_collection_query",
            "_set_collection_sort",
            "_clear_collection_filters",
        }
    )
    assert filter_methods.count(
        "_refresh_collection_list(refresh_landmarks=False)"
    ) == 5

    subtabs_source = ast.get_source_segment(
        source, classes["CollectionSubtabs"]
    ) or ""
    assert 'CollectionTab.PLANTS, "Plants"' in subtabs_source
    assert 'CollectionTab.GARDEN_LANDMARKS, "Garden Landmarks"' in subtabs_source
    assert "Garden Landmarks claimed" in subtabs_source
    assert 'setPlaceholderText("Search landmarks")' in source
    assert "class LandmarkFilterControls" in source

    landmarks_source = ast.get_source_segment(
        source, classes["GardenLandmarksPane"]
    ) or ""
    overview_source = ast.get_source_segment(
        source, classes["LandmarkProjectOverview"]
    ) or ""
    tier_row_source = ast.get_source_segment(
        source, classes["LandmarkTierRow"]
    ) or ""
    assert landmarks_source.count("QScrollArea(") == 1
    assert "ScrollBarAlwaysOff" in landmarks_source
    assert "QScrollArea(" not in overview_source
    assert "QScrollArea(" not in tier_row_source
    assert "size=88" in overview_source
    assert "setFixedHeight(36)" in overview_source
    assert "setMaximumWidth(145)" in overview_source
    assert "size=58" in tier_row_source
    assert "setMinimumHeight(168)" in tier_row_source
    assert "setFixedHeight(36)" in tier_row_source
    assert "setMaximumWidth(140)" in tier_row_source
    assert "tier.artwork_id" in tier_row_source
    assert 'asset_id="ui_garden_coin"' in tier_row_source

    collection_set_current = next(
        node
        for node in classes["CollectionSection"].body
        if isinstance(node, ast.FunctionDef) and node.name == "set_current"
    )
    collection_set_current_source = ast.get_source_segment(
        source, collection_set_current
    ) or ""
    assert "QTimer.singleShot" not in collection_set_current_source
    progress_open = next(
        node
        for node in classes["GardenProgressDialog"].body
        if isinstance(node, ast.FunctionDef) and node.name == "open_collection"
    )
    progress_open_source = ast.get_source_segment(source, progress_open) or ""
    assert progress_open_source.index('self.open_page("collection")') < (
        progress_open_source.index("QTimer.singleShot(0, focuser)")
    )


def test_landmark_tier_ui_state_keeps_progress_claims_and_selection_independent() -> None:
    state = _compiled_function("_landmark_tier_ui_state")
    common = {
        "project_unlocked": True,
        "tier_id": "birdbath_terrace",
        "funded": False,
        "claimed": False,
        "claimable": False,
        "displayed_tier_id": "",
        "project_active": False,
        "project_funded_units": 0,
        "previous_threshold_units": 2_500_000,
        "cumulative_threshold_units": 10_000_000,
        "next_unfunded_id": "birdbath_terrace",
    }

    assert state(**{**common, "project_unlocked": False}) == (
        "locked",
        "Locked",
    )
    assert state(**{**common, "project_active": True}) == (
        "in-progress",
        "In progress",
    )
    assert state(
        **{
            **common,
            "project_funded_units": 5_000_000,
        }
    ) == ("in-progress", "In progress")
    assert state(**{**common, "funded": True}) == ("funded", "Funded")
    assert state(
        **{**common, "funded": True, "claimable": True}
    ) == ("ready-to-claim", "Ready to claim")
    assert state(
        **{**common, "funded": True, "claimed": True}
    ) == ("claimed", "Claimed")
    assert state(
        **{
            **common,
            "funded": True,
            "claimed": True,
            "displayed_tier_id": "birdbath_terrace",
        }
    ) == ("in-use", "In use")

    project_status = _compiled_function("_landmark_project_ui_status")
    assert project_status(
        project_unlocked=False,
        project_active=False,
        funded_growth_units=0,
        claimed_tier_count=0,
        tier_count=6,
    ) == "Locked"
    assert project_status(
        project_unlocked=True,
        project_active=False,
        funded_growth_units=0,
        claimed_tier_count=0,
        tier_count=6,
    ) == "Not started"
    assert project_status(
        project_unlocked=True,
        project_active=True,
        funded_growth_units=2_500_000,
        claimed_tier_count=0,
        tier_count=6,
    ) == "Active project"
    assert project_status(
        project_unlocked=True,
        project_active=False,
        funded_growth_units=2_500_000,
        claimed_tier_count=0,
        tier_count=6,
    ) == "In progress"
    assert project_status(
        project_unlocked=True,
        project_active=False,
        funded_growth_units=247_500_000,
        claimed_tier_count=6,
        tier_count=6,
    ) == "Complete"


def test_named_fertilizer_receipts_reuse_the_item_artwork() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    nursery = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NurseryDialog"
    )
    receipt = next(
        node
        for node in nursery.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_show_purchase_receipt"
    )
    receipt_source = ast.get_source_segment(source, receipt) or ""
    dashboard = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenDashboard"
    )
    stored_use = next(
        node
        for node in dashboard.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_use_owned_fertilizer_from_dialog"
    )
    stored_source = ast.get_source_segment(source, stored_use) or ""

    assert 'str(outcome.category).casefold() == "fertilizer"' in receipt_source
    assert 'artwork_ref = f"fertilizer_{tier}"' in receipt_source
    assert "purchased_artwork = preview.pixmap()" in receipt_source
    assert "artwork=purchased_artwork" in receipt_source
    assert 'f"fertilizer_{normalized_tier}"' in stored_source
    assert "artwork=artwork" in stored_source


def test_rare_stage_visibility_uses_species_specific_progress() -> None:
    rare_stage_unlocked = _compiled_function(
        "_rare_stage_unlocked",
        {"Any": Any, "GROWTH_THRESHOLDS": GROWTH_THRESHOLDS},
    )
    engine = SimpleNamespace(state={"plants": []})

    assert not rare_stage_unlocked(engine, "rose")
    rare_threshold = GROWTH_THRESHOLDS[-1]
    engine.state = {
        "plants": [
            {
                "species": "rose",
                "stage": "flowering",
                "growth_points": rare_threshold - 1,
            },
            {
                "species": "bonsai",
                "stage": "rare",
                "growth_points": rare_threshold,
            },
        ]
    }
    assert not rare_stage_unlocked(engine, "rose")
    engine.state["plants"][0]["growth_points"] = rare_threshold
    assert rare_stage_unlocked(engine, "rose")


def test_learner_text_normalizes_legacy_separator_messages() -> None:
    learner_text = _compiled_function("_learner_text", {"Any": Any})
    separator = chr(0xB7)

    for legacy_message in (
        f"Milestone reached {separator} +10 Garden Coins",
        f"Milestone reached{separator}+10 Garden Coins",
        f"Milestone reached  {separator}  +10 Garden Coins",
    ):
        assert learner_text(legacy_message) == "Milestone reached\n+10 Garden Coins"
    assert learner_text(f"One{separator}{separator}Two") == "One\nTwo"


def test_count_helpers_pluralize_and_clamp_learner_facing_values() -> None:
    plant_count = _compiled_function("_plant_count")
    card_answer_count = _compiled_function("_card_answer_count")
    minute_count = _compiled_function("_minute_count")

    assert plant_count(-1) == "0 plants"
    assert plant_count(1) == "1 plant"
    assert plant_count(1_000) == "1,000 plants"
    assert card_answer_count(0) == "0 cards"
    assert card_answer_count(1) == "1 card"
    assert card_answer_count(2) == "2 cards"
    assert minute_count(0) == "0 minutes"
    assert minute_count(1) == "1 minute"
    assert minute_count(2) == "2 minutes"


def test_affordability_helpers_report_ready_and_shortfall_states() -> None:
    affordability = _compiled_function("_affordability_status")
    compact = _compiled_function("_compact_affordability_status")

    assert affordability(25, 25) == (True, "Affordable now.")
    assert affordability(25, 24) == (False, "Need 1 more Garden Coin.")
    assert affordability(150, 25) == (False, "Need 125 more Garden Coins.")
    assert compact(25, 25, ready_text="Ready to unlock") == "Ready to unlock"
    assert compact(150, 25, ready_text="Ready to unlock") == "125 more needed"


def test_progress_layout_helpers_use_real_row_and_transaction_geometry() -> None:
    boundaries = _compiled_function("_complete_row_boundaries")
    spacer_height = _compiled_function("_complete_section_spacer_height")
    grid_plan = _compiled_function("_coin_ledger_grid_plan")
    compact = _compiled_function("_coin_ledger_is_compact_unscrolled")

    assert boundaries([72, 224, 310], top_margin=6, spacing=10) == (78, 312, 632)
    assert boundaries([], top_margin=6, spacing=10) == ()
    assert spacer_height(410, 120, 500, added_spacing=18) == 72
    assert spacer_height(410, 120, 560, added_spacing=18) == 0
    assert spacer_height(40, 600, 500, added_spacing=18) == 0
    assert grid_plan(2) == ((0, 1, None), (1, 3, 2))
    assert compact(
        total_count=2,
        visible_count=2,
        selected_filter="all",
        show_all=False,
    )
    assert compact(
        total_count=3,
        visible_count=2,
        selected_filter="earned",
        show_all=False,
    )
    assert compact(
        total_count=8,
        visible_count=4,
        selected_filter="all",
        show_all=False,
    )
    assert not compact(
        total_count=8,
        visible_count=8,
        selected_filter="all",
        show_all=True,
    )


def test_shared_plant_presenter_covers_fertilizer_time() -> None:
    engine = SimpleNamespace(
        FERTILIZERS={"basic": SimpleNamespace(name="Basic Fertilizer")}
    )
    active_batch = SimpleNamespace(
        effect_id="fertilizer_basic",
        growth_per_card_units=100,
        total_cards=100,
        remaining_cards=37,
    )
    plant = SimpleNamespace(
        plant_id="plant-1",
        growth_stage="seed",
        growth_points=0,
        fully_grown=False,
        fertilizer_card_batches=[active_batch],
        fertilizer_card_queue=[],
        fertilizer=SimpleNamespace(
            tier="basic",
            growth_per_answer=1,
            expires_at_ms=7_900_000,
        ),
    )

    active = fertilizer_status(engine, plant, now=1_000.0)
    assert (active.name, active.effect, active.duration) == (
        "Basic Fertilizer",
        "+1 Growth per card",
        "37 cards remaining",
    )
    assert active.cards_remaining == 37
    assert active.expires_at_ms is None

    plant.fertilizer_card_batches = []
    plant.fertilizer.expires_at_ms = 1_030_000
    assert (
        fertilizer_status(engine, plant, now=1_000.0).duration
        == "30 seconds left"
    )
    plant.fertilizer.expires_at_ms = 999_000
    assert fertilizer_status(engine, plant, now=1_000.0).duration == "Expired"


def test_contact_sheet_three_uses_shared_release_components_and_copy() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "class StageTile" in source
    assert "class RewardChip" in source
    assert source.count("stage_card = StageTile(") == 2
    assert "stages = PlantStageStrip(" in source
    assert 'f"{safe_amount:,} {visible_name}"' in source
    assert '("streak", "Anki Streak")' in source
    assert 'content_title = QLabel("Garden Coin activity")' in source
    assert '("Date", "Source", "Change", "Balance after")' in source
    assert 'button.setFixedHeight(36)' in source
    assert 'QPushButton { font-size:13px; }' in source
    assert "min-height:32px; max-height:32px" in source
    assert "min-height:36px; max-height:36px" in source
    assert "min-height:24px; max-height:24px" in source
    assert "min-height:8px; max-height:8px" in source
    assert '"No plants match these filters."' in source
    assert '"No Garden Landmarks match these filters."' in source
    assert "collection items discovered" in source
    assert 'f"Nursery: {cost_label(species_price)}"' in source
    assert '[("Nurture", "nurture"), ("More", "more")]' in source
    assert 'view_action = menu.addAction("View plant")' in source
    assert "Entries" not in (
        source[
            source.index("def _refresh_collection_list_content"):
            source.index("def _set_collection_filter")
        ]
    )

    tree = ast.parse(source, filename=str(DASHBOARD))
    dashboard = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GardenDashboard"
    )
    plant_action = next(
        node for node in dashboard.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_collection_plant_action"
    )
    plant_action_source = ast.get_source_segment(source, plant_action) or ""
    assert "self.engine.set_active_plant(plant_id)" in plant_action_source
    assert "daily_care" not in plant_action_source.casefold()
