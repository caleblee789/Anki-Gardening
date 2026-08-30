from __future__ import annotations

import ast
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from ankigarden.game import GROWTH_THRESHOLDS, GardenGameEngine
from ankigarden.purchases import PurchaseDisposition, fertilizer_action_label
from ankigarden.ui.copy import NURSERY_STARTER_RATIONALE
from ankigarden.ui.plant_presenters import fertilizer_status


DASHBOARD = (
    Path(__file__).resolve().parents[1] / "ankigarden" / "ui" / "dashboard.py"
)


def test_fertilizer_action_vocabulary_uses_the_authoritative_disposition() -> None:
    assert fertilizer_action_label(PurchaseDisposition.APPLIED, owned=True) == "Apply"
    assert fertilizer_action_label(PurchaseDisposition.QUEUED, owned=True) == "Queue"
    assert fertilizer_action_label(PurchaseDisposition.EXTENDED, owned=True) == "Extend"
    assert (
        fertilizer_action_label(PurchaseDisposition.APPLIED, owned=False)
        == "Buy and apply"
    )
    assert (
        fertilizer_action_label(PurchaseDisposition.QUEUED, owned=False)
        == "Buy and queue"
    )
    assert (
        fertilizer_action_label(PurchaseDisposition.EXTENDED, owned=False)
        == "Extend"
    )


def test_fertilizer_inventory_card_derives_active_card_batch_tier() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    nursery = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NurseryDialog"
    )
    inventory_card = next(
        node
        for node in nursery.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fertilizer_inventory_card"
    )
    method_source = ast.get_source_segment(source, inventory_card) or ""
    assigned_names = {
        node.id
        for node in ast.walk(inventory_card)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }

    assert "active_fertilizer" in assigned_names
    assert "active_fertilizer = active_batches[0] if active_batches else None" in method_source
    assert 'getattr(active_fertilizer, "effect_id", "")' in method_source
    assert 'getattr(active_fertilizer, "tier", "")' not in method_source


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


def test_nursery_catalog_helpers_cover_costs_receipts_empty_states_and_folds() -> None:
    compact_cost = _compiled_function("_compact_catalog_cost")
    compact_shortfall = _compiled_function("_compact_catalog_shortfall")
    receipt_actions = _compiled_function("_nursery_collection_receipt_actions")
    empty_copy = _compiled_function("_nursery_empty_state_copy")
    product_visible = _compiled_function("_nursery_catalog_product_visible")
    prioritize_environment = _compiled_function(
        "_prioritize_nursery_environment_items",
        {"CatalogItem": Any, "Callable": Callable},
    )
    fold_plan = _compiled_function("_catalog_fold_alignment_plan")

    assert compact_cost(1) == "1 coin"
    assert compact_cost(100) == "100 coins"
    assert compact_shortfall(1, 0) == "Need 1 more coin"
    assert compact_shortfall(100, 0) == "Need 100 more coins"
    assert compact_shortfall(100, 100) == ""
    assert receipt_actions(False) == ("Place in garden", "View collection")
    assert receipt_actions(True) == ("Place in garden",)
    complete_collection = SimpleNamespace(
        species_text="10 of 10 species discovered",
        collection_entries_text="30 of 93 collection entries discovered",
    )
    assert empty_copy(
        starter_mode=False,
        collection_complete=True,
        collection_projection=complete_collection,
    ) == (
        "10 of 10 species discovered",
        "30 of 93 collection entries discovered",
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


def test_nursery_starter_copy_and_uniform_plant_price_presentation() -> None:
    assert NURSERY_STARTER_RATIONALE == (
        "Your first plant is free and will be added to your collection. "
        "Appearance only. Every plant grows at the same rate."
    )
    assert set(GardenGameEngine.SPECIES_PRICES.values()) == {250}

    compact_cost = _compiled_function("_compact_catalog_cost")
    assert compact_cost(250) == "250 coins"

    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    nursery = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NurseryDialog"
    )
    available_card = next(
        node
        for node in nursery.body
        if isinstance(node, ast.FunctionDef) and node.name == "_available_card"
    )
    method_source = ast.get_source_segment(source, available_card) or ""
    assert "price = presentation.price" in method_source
    assert "meta = QLabel(_compact_catalog_cost(price))" in method_source


def test_nursery_beds_are_earned_without_coin_purchase_actions() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NurseryDialog"
    )
    methods = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_space_progression"
    }

    assert methods.keys() == {"_space_progression"}
    method_source = methods["_space_progression"]
    assert "bed_unlock_rows" in method_source
    assert "earned through plant progression" in method_source
    assert "_garden_coin_count" not in method_source


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
    assert 'if str(definition.source_id) == "fertilizer_basic"' in method_source
    assert 'else str(definition.source_id or "")' in method_source
    assert "icon = _item_preview_label(" in method_source
    assert 'icon.setProperty("collectibleItemArtwork", True)' in method_source
    assert 'icon.setProperty("collectibleItemArtworkRef", artwork_ref)' in method_source
    assert '"growth_items": "growth"' not in method_source


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
    engine.state = {
        "plants": [
            {
                "species": "rose",
                "stage": "flowering",
                "growth_points": GROWTH_THRESHOLDS[-1] - 1,
            },
            {
                "species": "bonsai",
                "stage": "rare",
                "growth_points": GROWTH_THRESHOLDS[-1],
            },
        ]
    }
    assert not rare_stage_unlocked(engine, "rose")
    engine.state["plants"][0]["growth_points"] = GROWTH_THRESHOLDS[-1]
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
    assert not compact(
        total_count=3,
        visible_count=2,
        selected_filter="all",
        show_all=False,
    )


def test_shared_plant_presenter_covers_fertilizer_cards() -> None:
    engine = SimpleNamespace(
        FERTILIZERS={"basic": SimpleNamespace(name="Basic Fertilizer")}
    )
    plant = SimpleNamespace(
        plant_id="plant-1",
        growth_stage="seed",
        growth_points=0,
        fully_grown=False,
        fertilizer_card_batches=[SimpleNamespace(
            effect_id="fertilizer_basic",
            growth_per_card_units=100,
            total_cards=100,
            remaining_cards=55,
        )],
        fertilizer_card_queue=[],
    )

    active = fertilizer_status(engine, plant, now=1_000.0)
    assert (active.name, active.effect, active.duration) == (
        "Basic Fertilizer",
        "+1 Growth per eligible card answer",
        "55 cards left",
    )
    assert fertilizer_status(engine, plant, now=9_999_999_999.0).duration == "55 cards left"
    plant.fertilizer_card_batches[0].remaining_cards = 0
    assert fertilizer_status(engine, plant, now=1_000.0).phase == "inactive"
