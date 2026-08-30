from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path

from scripts.validate_ui_capture import (
    collection_loadout_state_matrix_issue_codes,
    cosmetic_purchase_display_issue_codes,
    earned_bed_unlock_issue_codes,
    landmark_transaction_state_issue_codes,
    mastery_transaction_state_issue_codes,
    nursery_bed_incomplete_state_issue_codes,
    nursery_environment_fixture_issue_codes,
    nursery_supplement_state_matrix_issue_codes,
)


ROOT = Path(__file__).resolve().parents[1]


def test_collection_loadout_capture_requires_separate_scenery_effect_copy() -> None:
    evidence = {
        "structured_values": {
            "scenery": "Verdant Twilight",
            "displayed_decoration": "Seedling Sign",
            "active_bonus": "Seedling Sign",
            "active_scenery_effect": "Verdant Twilight",
            "visual_effects": "On",
        },
        "structured_values_visible": True,
        "initial_apply_enabled": False,
        "dirty_apply_enabled": True,
        "restored_apply_enabled": False,
        "selection_preserved_across_tabs": True,
        "selected_tile_checked_after_tabs": True,
        "dirty_state_painted": True,
        "restored_state_painted": True,
        "restored_to_persisted_draft": True,
        "selected_scenery_id": "autumn",
        "preview_size": [548, 308],
        "passed": True,
    }
    assert collection_loadout_state_matrix_issue_codes(evidence) == ()

    missing_effect = deepcopy(evidence)
    del missing_effect["structured_values"]["active_scenery_effect"]
    assert "collection-loadout-structured-value-keys" in (
        collection_loadout_state_matrix_issue_codes(missing_effect)
    )


def _fertilizer_matrix() -> dict[str, object]:
    return {
        "records": {
            "sufficient-balance": {
                "balance": 500,
                "balance_copy": "500",
                "item_id": "premium",
                "price_copy": "300 coins",
                "action": "Buy and apply",
                "action_disposition": "apply",
                "action_enabled": True,
                "painted": True,
            },
            "stored-multiple": {
                "item_id": "fertilizer_basic",
                "item_name": "Rich Compost",
                "owned_copy": "3 owned",
                "action": "Apply",
                "action_disposition": "apply",
                "meta_copy": (
                    "+1 Growth per eligible card answer · "
                    "Lasts 100 eligible cards"
                ),
                "artwork_ref": "rich_compost",
                "artwork_source_matches": True,
                "artwork_fallback": False,
                "booster_item_id": "booster_potion",
                "booster_owned_copy": "2 owned",
                "booster_action": "Use",
                "booster_painted": True,
                "painted": True,
            },
            "active": {
                "engine_tier": "basic",
                "item_id": "fertilizer_basic",
                "owned_copy": "2 owned",
                "action": "Extend",
                "action_disposition": "extend",
                "status_phase": "active",
                "status_copy": (
                    "Basic Fertilizer · +1 Growth per eligible card answer · "
                    "100 cards left"
                ),
                "painted": True,
            },
            "queued": {
                "engine_tiers": ["quality"],
                "item_id": "fertilizer_quality",
                "owned_copy": "1 owned",
                "queued_copy": "Queued",
                "action": "Extend",
                "action_disposition": "extend",
                "final_basic_action": "Queue",
                "final_basic_action_disposition": "queue",
                "final_basic_painted": True,
                "final_quality_action": "Extend",
                "final_quality_action_disposition": "extend",
                "final_quality_painted": True,
                "meta_copy": (
                    "+2 Growth per eligible card answer · "
                    "Lasts 200 eligible cards"
                ),
                "painted": True,
            },
        },
        "passed": True,
    }


def test_fertilizer_capture_contract_is_card_counted() -> None:
    evidence = _fertilizer_matrix()
    assert nursery_supplement_state_matrix_issue_codes(evidence) == ()

    wall_clock = deepcopy(evidence)
    wall_clock["records"]["stored-multiple"]["meta_copy"] = (
        "+1 Growth per eligible card answer · Lasts 1 hour"
    )
    assert (
        "nursery-supplement-stored-multiple:meta_copy"
        in nursery_supplement_state_matrix_issue_codes(wall_clock)
    )

    timed_active = deepcopy(evidence)
    timed_active["records"]["active"]["status_copy"] = (
        "Basic Fertilizer · +1 Growth per eligible card answer · 1 hour left"
    )
    assert (
        "nursery-supplement-active:status_copy"
        in nursery_supplement_state_matrix_issue_codes(timed_active)
    )

    ambiguous_allowance = deepcopy(evidence)
    ambiguous_allowance["records"]["queued"]["meta_copy"] = (
        "+2 Growth per eligible card answer · Lasts 200 cards"
    )
    assert (
        "nursery-supplement-queued:meta_copy"
        in nursery_supplement_state_matrix_issue_codes(ambiguous_allowance)
    )


def test_active_capture_sources_have_no_fertilizer_clock_copy_or_polling() -> None:
    paths = (
        ROOT / "ankigarden/capture/runtime.py",
        ROOT / "scripts/validate_ui_capture.py",
        ROOT / "ankigarden/capture/capture-contract-v26.json",
    )
    joined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "Lasts 1 hour",
        "Lasts 2 hours",
        "1 hour left",
        "1 hour remaining",
        "Extend 1h",
        "fertilizer_remaining_seconds",
        "_sync_fertilizer_timer",
        "_refresh_timed_plant_statuses",
    ):
        assert forbidden not in joined


def test_bed_capture_contract_requires_earned_capacity_and_endgame_routes() -> None:
    evidence = {
        "unlocked_beds": 2,
        "summary": "2 of 6 beds unlocked",
        "next_bed_number": 3,
        "next_requirement": "First plant reaches Mature",
        "guidance": (
            "Next: Bed 3 · First plant reaches Mature. "
            "Garden beds are earned through plant progression."
        ),
        "purchase_action_present": False,
        "coin_price_present": False,
        "endgame_title": "Stored Growth projects",
        "landmark_copy": "Garden Landmark · Unlocks at first Full Bloom",
        "mastery_copy": "Cultivation Mastery · 0 species eligible",
        "endgame_action": "Open Collection",
        "endgame_painted": True,
        "painted": True,
        "contained": True,
        "passed": True,
    }
    assert nursery_bed_incomplete_state_issue_codes(evidence) == ()

    paywalled = {**evidence, "purchase_action_present": True}
    assert (
        "nursery-bed-incomplete:purchase_action_present"
        in nursery_bed_incomplete_state_issue_codes(paywalled)
    )


def test_environment_capture_contract_includes_direct_purchase_cosmetics() -> None:
    evidence = {
        "displayed_decoration": {
            "item_id": "seedling_sign",
            "ownership_state": "owned",
            "display_state": "displayed",
            "display_action": "Displayed",
            "bonus_action": "Select today’s bonus",
            "painted": True,
        },
        "active_bonus": {
            "item_id": "watering_station",
            "ownership_state": "owned",
            "bonus_state": "active",
            "action": "Garden Bonus active today",
            "painted": True,
        },
        "purchasable": {
            "item_id": "wind_chime",
            "ownership_state": "available",
            "price": 100,
            "action": "Buy",
            "action_enabled": True,
            "painted": True,
        },
        "locked": {
            "item_id": "firefly_lantern",
            "ownership_state": "locked",
            "price": 0,
            "action": "How to unlock",
            "action_enabled": False,
            "painted": True,
        },
        "scenery_heading": {
            "text": "Scenery",
            "reachable": True,
            "painted": True,
        },
        "cosmetics": {
            "heading": "Display decorations",
            "independence_copy": (
                "Cosmetic appearance is independent from your active Garden "
                "Bonus."
            ),
            "prices": {
                "garden_bench": "150 coins",
                "birdhouse": "200 coins",
                "butterfly_house": "250 coins",
                "stone_lantern": "300 coins",
                "sundial": "400 coins",
            },
            "actions": {
                "garden_bench": "Buy",
                "birdhouse": "Buy",
                "butterfly_house": "Buy",
                "stone_lantern": "Buy",
                "sundial": "Buy",
            },
            "cosmetic_only": True,
            "all_painted": True,
        },
        "fixture_profiles": ["full", "representative"],
        "reversible": True,
    }
    assert nursery_environment_fixture_issue_codes(evidence) == ()

    wrong_price = deepcopy(evidence)
    wrong_price["cosmetics"]["prices"]["sundial"] = "350 coins"
    assert (
        "nursery-environment-cosmetics:prices"
        in nursery_environment_fixture_issue_codes(wrong_price)
    )


def test_compiled_contract_requires_release_economy_capture_facts() -> None:
    contract = json.loads(
        (ROOT / "ankigarden/capture/capture-contract-v26.json").read_text(
            encoding="utf-8"
        )
    )
    surfaces = {surface["id"]: surface for surface in contract["surfaces"]}

    expected = {
        "starter-nursery-plants": "starter_economy",
        "reviewer-hud-expanded": "garden_rhythm_effect",
        "purchase-confirmation-species": "species_uniform_price",
        "nursery-garden-spaces": "nursery_bed_incomplete_state",
        "nursery-garden-decorations-scenery": (
            "garden_decoration_scenery_fixture"
        ),
    }
    for surface_id, fact in expected.items():
        required = surfaces[surface_id]["state_contract"]["required_facts"]
        assert fact in required


def _landmark_transaction() -> dict[str, object]:
    return {
        "landmark_id": "mossy_stone_path",
        "display_name": "Mossy Stone Path",
        "selected_applied": True,
        "partial_spent_units": 1_000_000,
        "partial_contributed_units": 1_000_000,
        "partial_ready": False,
        "finish_requested_units": 2_000_000,
        "finish_spent_units": 1_500_000,
        "ready_contributed_units": 2_500_000,
        "ready_to_complete": True,
        "completion_applied": True,
        "completion_growth_spent_units": 0,
        "completion_coins_spent": 250,
        "stored_growth_before_units": 3_000_000,
        "stored_growth_after_units": 500_000,
        "coin_balance_before": 300,
        "coin_balance_after": 50,
        "completed_landmark_ids": ["mossy_stone_path"],
        "displayed_landmark_id": "mossy_stone_path",
        "next_landmark_id": "birdbath_terrace",
        "feedback_kind": "landmark",
        "feedback_title": "Mossy Stone Path",
        "feedback_message": "Garden Landmark completed.",
        "feedback_asset_category": "landmarks",
        "feedback_asset_key": "mossy_stone_path",
        "feedback_visible": True,
        "landmark_scene_painted": True,
        "completed_row_name": "Mossy Stone Path",
        "completed_row_status": "Displayed in Garden",
        "completed_row_fully_visible": True,
        "completed_row_painted": True,
        "replay_idempotent": True,
        "reversible": True,
        "painted": True,
    }


def _mastery_transaction() -> dict[str, object]:
    return {
        "species_id": "bonsai",
        "rank_id": "bronze",
        "applied": True,
        "growth_spent_units": 2_500_000,
        "coins_spent": 50,
        "stored_growth_before_units": 3_000_000,
        "stored_growth_after_units": 500_000,
        "coin_balance_before": 100,
        "coin_balance_after": 50,
        "highest_rank_by_species": {"bonsai": "bronze"},
        "next_rank_id": "silver",
        "visible_rank_copy": "Bonsai · Bronze",
        "visible_next_action": "Unlock Silver",
        "visible_next_cost": (
            "Costs 50,000 Stored Growth and 100 Garden Coins."
        ),
        "feedback_kind": "mastery",
        "feedback_title": "Bonsai Bronze",
        "feedback_message": "Cultivation Mastery unlocked.",
        "feedback_asset_category": "mastery",
        "feedback_asset_key": "bronze",
        "mastery_artwork_painted": True,
        "mastery_overlay_painted": True,
        "replay_idempotent": True,
        "card_fully_visible": True,
        "reversible": True,
        "painted": True,
    }


def _cosmetic_transaction() -> dict[str, object]:
    return {
        "item_id": "garden_bench",
        "item_name": "Garden Bench",
        "quoted_price": 150,
        "amount_spent": 150,
        "balance_before": 500,
        "balance_after": 350,
        "purchase_success": True,
        "purchase_disposition": "owned_not_equipped",
        "purchase_equipped": False,
        "displayed_before_purchase": "seedling_sign",
        "displayed_after_purchase": "seedling_sign",
        "display_action_succeeded": True,
        "displayed_after_action": "garden_bench",
        "active_bonus_before": "watering_station",
        "active_bonus_after_purchase": "watering_station",
        "active_bonus_after_display": "watering_station",
        "visible_displayed_decoration": "Garden Bench",
        "visible_active_bonus": "Watering Station",
        "owned_once": True,
        "preview_painted": True,
        "reversible": True,
        "painted": True,
    }


def _bed_unlock_transaction() -> dict[str, object]:
    return {
        "charge_id": "growth_charge_small",
        "previous_growth": 5_900,
        "resulting_growth": 6_000,
        "previous_stage": "young",
        "resulting_stage": "mature",
        "growth_granted": 100,
        "charge_success": True,
        "first_canopy_unlocked": True,
        "earned_bed_unlocks": [3],
        "unlocked_beds_before": 2,
        "unlocked_beds_after": 3,
        "achievement_name": "First Canopy",
        "reward_summary": "Bed 3 unlocked",
        "celebration_copy": "First Canopy · Bed 3 unlocked",
        "celebration_visible": True,
        "visible_status": "Unlocked",
        "replay_idempotent": True,
        "card_fully_visible": True,
        "reversible": True,
        "painted": True,
    }


def test_new_economy_transaction_reducers_accept_only_exact_state() -> None:
    records = (
        (
            _landmark_transaction(),
            landmark_transaction_state_issue_codes,
            "completion_coins_spent",
        ),
        (
            _mastery_transaction(),
            mastery_transaction_state_issue_codes,
            "mastery_artwork_painted",
        ),
        (
            _cosmetic_transaction(),
            cosmetic_purchase_display_issue_codes,
            "active_bonus_after_display",
        ),
        (
            _bed_unlock_transaction(),
            earned_bed_unlock_issue_codes,
            "celebration_visible",
        ),
    )
    for evidence, validator, mutation_key in records:
        assert validator(evidence) == ()
        invalid = deepcopy(evidence)
        invalid[mutation_key] = None
        assert validator(invalid)


def test_v26_full_contract_owns_four_transaction_scenarios() -> None:
    contract = json.loads(
        (ROOT / "ankigarden/capture/capture-contract-v26.json").read_text(
            encoding="utf-8"
        )
    )
    expected = (
        (
            "landmark-contribution-completion",
            "_capture_landmark_contribution_completion",
            "landmark_transaction_state",
            "landmark-completed-row",
        ),
        (
            "mastery-rank-completion",
            "_capture_mastery_rank_completion",
            "mastery_transaction_state",
            "mastery-rank-card",
        ),
        (
            "cosmetic-purchase-display-independent",
            "_capture_cosmetic_purchase_display_independent",
            "cosmetic_purchase_display_independence",
            "cosmetic-display-preview",
        ),
        (
            "earned-bed-unlock-celebration",
            "_capture_earned_bed_unlock_celebration",
            "earned_bed_unlock_celebration",
            "earned-bed-unlock-card",
        ),
    )
    surfaces = {surface["id"]: surface for surface in contract["surfaces"]}
    full_labels = [
        label
        for group in contract["profiles"]["full"]["groups"]
        for label in group["labels"]
    ]
    representative_labels = [
        label
        for group in contract["profiles"]["representative"]["groups"]
        for label in group["labels"]
    ]
    assert contract["surface_count"] == 38
    assert contract["profiles"]["full"]["surface_count"] == 38
    assert contract["profiles"]["full"]["contact_sheet_page_count"] == 6
    assert full_labels[-4:] == [row[0] for row in expected]
    for scenario_id, executor, fact, pixel_key in expected:
        surface = surfaces[scenario_id]
        assert surface["scenario_id"] == scenario_id
        assert surface["fixture_id"] == f"{scenario_id}-v1"
        assert surface["scenario_step"] == 1
        assert surface["executor"] == executor
        assert fact in surface["state_contract"]["required_facts"]
        assert f"rendered-pixels:{pixel_key}" in surface[
            "evidence_requirements"
        ]
        assert scenario_id in full_labels
        assert scenario_id not in representative_labels


def test_transaction_runtime_uses_fixed_ids_and_exact_ledger_restore() -> None:
    source = (ROOT / "ankigarden/capture/runtime.py").read_text(
        encoding="utf-8"
    )
    for request_suffix in ("2201", "2202", "2203", "2204", "2211", "2221", "2231"):
        assert f"00000000-0000-0000-0000-00000000{request_suffix}" in source
    assert source.count("exact_ledger_restore=True") >= 4
    assert 'status_message="First Canopy · Bed 3 unlocked"' in source
    assert '"earned-bed-unlock-celebration": 2' in source
    assert "status_copy == expected_status_copy" in source


def test_full_nursery_uses_the_deterministic_partial_catalog_fixture() -> None:
    source = (ROOT / "ankigarden/capture/runtime.py").read_text(
        encoding="utf-8"
    )
    fixture_source = source.split(
        "def _prepare_representative_nursery_fixture(",
        1,
    )[1].split(
        "def _prepare_nursery_plants_fixture(",
        1,
    )[0]

    assert 'self._capture_profile != "representative"' not in fixture_source
    assert "state.plants = [representative]" in fixture_source
    assert "state.unlocked_slots = 2" in fixture_source



def test_persistent_landmark_and_mastery_capture_semantics_are_source_owned() -> None:
    dashboard_source = (ROOT / "ankigarden/ui/dashboard.py").read_text(
        encoding="utf-8"
    )
    runtime_source = (ROOT / "ankigarden/capture/runtime.py").read_text(
        encoding="utf-8"
    )
    for semantic_property in (
        'setProperty("completedLandmark", True)',
        'setProperty("landmarkCompletionName", True)',
        '"landmarkCompletionStatus"',
        'setProperty("cultivationMastery", True)',
        '"Bronze Cultivation artwork"',
    ):
        assert semantic_property in dashboard_source or semantic_property in runtime_source
    assert '"landmark-completed-row"' in runtime_source
    assert '"mastery-rank-card"' in runtime_source
    assert '"mastery-bronze" in feature_trace' in runtime_source


def _runtime_function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_runtime_maps_economy_progress_surfaces_to_collection() -> None:
    source = (ROOT / "ankigarden/capture/runtime.py").read_text(
        encoding="utf-8"
    )
    function = _runtime_function(source, "expected_capture_state_profile")
    collection_labels = next(
        {
            value.value
            for value in node.elts
            if isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        }
        for node in ast.walk(function)
        if isinstance(node, ast.Set)
        and any(
            isinstance(value, ast.Constant)
            and value.value == "progress-collection"
            for value in node.elts
        )
    )
    assert {
        "landmark-contribution-completion",
        "mastery-rank-completion",
    }.issubset(collection_labels)


def test_economy_collection_targets_drain_reset_before_scrolling() -> None:
    source = (ROOT / "ankigarden/capture/runtime.py").read_text(
        encoding="utf-8"
    )
    helper = ast.get_source_segment(
        source,
        _runtime_function(source, "_reveal_collection_capture_target"),
    )
    assert helper is not None
    first_event_drain = helper.index("QApplication.processEvents()")
    explicit_scroll = helper.index("bar = scroll.verticalScrollBar()")
    ensure_visible = helper.index("scroll.ensureWidgetVisible(target, 0, 24)")
    final_event_drain = helper.rindex("QApplication.processEvents()")
    assert first_event_drain < explicit_scroll < ensure_visible < final_event_drain

    for name in (
        "_audit_landmark_transaction_collection",
        "_audit_mastery_transaction_collection",
    ):
        audit = ast.get_source_segment(
            source,
            _runtime_function(source, name),
        )
        assert audit is not None
        assert "self._reveal_collection_capture_target(" in audit
        assert "ensureWidgetVisible" not in audit


def test_collection_alone_adds_endgame_safe_trailing_padding() -> None:
    source = (ROOT / "ankigarden/ui/dashboard.py").read_text(
        encoding="utf-8"
    )
    override = "self.collection_list.grid.setContentsMargins(6, 6, 22, 28)"
    assert source.count(override) == 1
    assert "self.achievement_list.grid.setContentsMargins(6, 6, 22, 28)" not in source
    assert "self.grid.setContentsMargins(6, 6, 22, 18)" in source
