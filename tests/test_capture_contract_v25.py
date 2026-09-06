from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.capture.acquisition import (
    AcquisitionCandidate,
    AcquisitionIdentity,
    select_candidate,
)
from ankigarden.capture.contract import (
    ContractValidationError,
    compile_contract,
    contract_diff,
    load_compiled_contract,
    validate_contract_payload,
)
from ankigarden.capture.lifecycle import FailureLedger, build_capture_plan
from ankigarden.capture.model import CaptureResult, ProfilePlacement
from ankigarden.capture.registry import REGISTRY, SurfaceRegistry
from scripts import capture_sequence
from scripts.capture_evidence import _reconstruct_renderer_ownership_proof
from scripts.package_addon import CAPTURE_BUILD, PRODUCTION_BUILD, package_files
from scripts.validate_ui_capture import (
    DEFAULT_CAPTURE_SOURCE,
    load_capture_contract,
    load_capture_scenario_contracts,
    load_expected_state_evidence_contracts,
    foreground_request_issue_codes,
)


def _candidate(backend: str, **changes: object) -> AcquisitionCandidate:
    values: dict[str, object] = {
        "backend": backend,
        "pixmap": object(),
        "semantic_state_valid": True,
        "overlay_pixels_present": True,
    }
    values.update(changes)
    return AcquisitionCandidate(**values)


def _result(
    surface_id: str,
    *,
    accepted: bool,
    classification: str,
) -> CaptureResult:
    return CaptureResult(
        surface_id=surface_id,
        scenario_id=REGISTRY[surface_id].scenario_id,
        fixture_id=REGISTRY[surface_id].fixture_id,
        scenario_step=REGISTRY[surface_id].scenario_step,
        accepted=accepted,
        backend="qt-widget-grab",
        rejected_candidates=(),
        process_id=1,
        window_id=2,
        window_role="dialog",
        logical_geometry=(0, 0, 10, 10),
        pixel_geometry=(10, 10),
        device_pixel_ratio=1.0,
        checkpoint=REGISTRY[surface_id].checkpoint,
        semantic_audit={"passed": accepted},
        pixel_audit={"passed": accepted},
        dependency_digest=REGISTRY.surface_digest(surface_id),
        failure_classification=classification,
    )


def _replace_full_placement(
    stable_id: str,
    placement: ProfilePlacement,
):
    surface = REGISTRY[stable_id]
    return replace(
        surface,
        placements=tuple(
            placement if current.profile == "full" else current
            for current in surface.placements
        ),
    )


def _runtime_tree() -> ast.Module:
    runtime_path = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    )
    return ast.parse(runtime_path.read_text("utf-8"))


def _runtime_literal(name: str) -> object:
    for node in _runtime_tree().body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if any(
            isinstance(target, ast.Name) and target.id == name
            for target in targets
        ):
            return ast.literal_eval(value)
    raise AssertionError(f"missing runtime assignment {name}")


def _compiled_runtime_function(name: str):
    method = next(
        node
        for node in _runtime_tree().body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    future = ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )
    namespace: dict[str, object] = {}
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(body=[future, method], type_ignores=[])
            ),
            "ankigarden/capture/runtime.py",
            "exec",
        ),
        namespace,
    )
    return namespace[name]


def _runtime_method_source(class_name: str, method_name: str) -> str:
    owner = next(
        node
        for node in _runtime_tree().body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    runtime_path = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    )
    segment = ast.get_source_segment(runtime_path.read_text("utf-8"), method)
    assert segment is not None
    return segment






def _compiled_runtime_method(
    class_name: str,
    method_name: str,
    namespace: dict[str, object],
):
    owner = next(
        node
        for node in _runtime_tree().body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    future = ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(body=[future, method], type_ignores=[])
            ),
            "ankigarden/capture/runtime.py",
            "exec",
        ),
        namespace,
    )
    return namespace[method_name]


def test_compiled_contract_is_current_and_validator_consumes_it() -> None:
    compiled = load_compiled_contract()

    assert compiled == compile_contract()
    assert compiled["schema_version"] == 2
    assert compiled["contract_version"] == 29
    assert compiled["scenario_schema_version"] == 3
    full = load_capture_contract(DEFAULT_CAPTURE_SOURCE, profile="full")
    states = load_expected_state_evidence_contracts(
        DEFAULT_CAPTURE_SOURCE,
        contract=full,
    )
    assert full.labels == REGISTRY.profile_labels("full")
    assert set(states) == set(full.labels)


def test_v25_contract_is_frozen_and_v26_scenario_identity_is_complete() -> None:
    v25_path = (
        Path(capture_sequence.REPO_ROOT)
        / "ankigarden"
        / "capture"
        / "capture-contract-v25.json"
    )
    assert hashlib.sha256(v25_path.read_bytes()).hexdigest() == (
        "f05d8737b5343776d1ac8bdd6ba0cb379c5065efc2fa067714097d80c4917de0"
    )

    compiled = load_compiled_contract()
    active_rows = {
        row["id"]: row
        for row in compiled["surfaces"]
        if row["active"] is True
    }
    expected_overrides = {
        "starter-deck-browser-home": ("garden_first_run", 1),
        "garden-starter-picker": ("garden_first_run", 2),
        "garden-starter-selected": ("garden_first_run", 3),
        "garden-starter-placement": ("garden_first_run", 4),
        "fertilizer-active": ("fertilizer_queue", 1),
        "purchase-confirmation-fertilizer-queue": ("fertilizer_queue", 2),
        "reviewer-hud-expanded": ("reviewer_hud_base", 1),
        "session-summary-after-review": ("session_summary", 1),
        "sync-rewards-summary": ("sync_rewards", 1),
        "reviewer-reward-dock-bundle": ("reviewer_hud_full_bloom", 1),
        "growth-charge-use-ready": ("growth_charge_transition", 1),
        "growth-charge-success-stage-reward": ("growth_charge_transition", 2),
    }
    for stable_id, row in active_rows.items():
        scenario_id, scenario_step = expected_overrides.get(
            stable_id,
            (stable_id, 1),
        )
        assert row["scenario_id"] == scenario_id
        assert row["fixture_id"] == f"{scenario_id}-v1"
        assert row["scenario_step"] == scenario_step
    assert all(
        {"scenario_id", "fixture_id", "scenario_step"} <= set(row)
        for row in compiled["surfaces"]
    )

    contract = load_capture_contract(DEFAULT_CAPTURE_SOURCE, profile="full")
    scenarios = load_capture_scenario_contracts(
        DEFAULT_CAPTURE_SOURCE,
        contract=contract,
    )
    for label in contract.labels:
        assert scenarios[label]["scenario_id"] == active_rows[label]["scenario_id"]
        assert scenarios[label]["fixture_id"] == active_rows[label]["fixture_id"]
        assert scenarios[label]["scenario_step"] == active_rows[label][
            "scenario_step"
        ]


def test_v26_shared_scenario_checkpoint_lineage_is_fail_closed() -> None:
    queue_id = "garden-starter-placement"
    queue = REGISTRY[queue_id]
    with pytest.raises(ValueError, match="multiple seeded checkpoint lineages"):
        SurfaceRegistry(
            replace(
                surface,
                checkpoint_cohort="development-stress",
                checkpoint="development-stress",
                internal_setups=("development-stress", "transaction-snapshot"),
            )
            if surface.stable_id == queue_id
            else surface
            for surface in REGISTRY.surfaces
        )

    tampered = copy.deepcopy(compile_contract())
    raw_queue = next(
        row for row in tampered["surfaces"]
        if row["id"] == queue.stable_id
    )
    raw_queue.update({
        "checkpoint_cohort": "development-stress",
        "checkpoint": "development-stress",
        "internal_setups": ["development-stress", "transaction-snapshot"],
    })
    with pytest.raises(ContractValidationError) as error:
        validate_contract_payload(tampered)
    assert (
        "scenario 'garden_first_run' has multiple seeded checkpoint lineages"
        in error.value.issues
    )


def test_v26_contract_hard_gates_scenario_and_profile_totals() -> None:
    compiled = compile_contract()
    bad_scenario = copy.deepcopy(compiled)
    first = next(
        row for row in bad_scenario["surfaces"]
        if row["id"] == "starter-deck-browser-home"
    )
    first["scenario_step"] = 2
    with pytest.raises(ContractValidationError) as scenario_error:
        validate_contract_payload(bad_scenario)
    assert any(
        "unexpected v29 scenario identity" in issue
        for issue in scenario_error.value.issues
    )

    bad_totals = copy.deepcopy(compiled)
    bad_totals["profiles"]["representative"]["surface_count"] = 18
    with pytest.raises(ContractValidationError) as totals_error:
        validate_contract_payload(bad_totals)
    assert "profile 'representative' surface count is stale" in totals_error.value.issues


def test_current_topology_is_dynamic_and_redundant_ids_stay_reserved() -> None:
    compiled = load_compiled_contract()

    assert compiled["surface_count"] == len(REGISTRY.active_surfaces)
    assert compiled["profiles"]["representative"]["surface_count"] == len(
        REGISTRY.profile_labels("representative")
    )
    assert compiled["profiles"]["full"]["surface_count"] == len(
        REGISTRY.profile_labels("full")
    )
    assert set(compiled["retired_ids"]) == {
        surface.stable_id for surface in REGISTRY.retired_surfaces
    }
    assert {
        surface.stable_id
        for surface in REGISTRY.surfaces
        if surface.stable_id.startswith("watering-can-")
    } <= set(compiled["retired_ids"])
    assert not any(
        stable_id.startswith("watering-can-")
        for stable_id in REGISTRY.profile_labels("full")
    )
    assert len(REGISTRY.profile_labels("representative")) == 22
    assert len(REGISTRY.profile_labels("full")) == 51
    assert not REGISTRY["nursery-weather-scenery"].active
    assert "nursery-weather-scenery" in compiled["retired_ids"]
    assert REGISTRY.profile_page_count("representative") == 5
    assert REGISTRY.profile_page_count("full") == 5
    from scripts.capture_support import paginate_contact_sheet_groups
    pages = compiled["profiles"]["full"]["contact_sheets"]
    assigned = [label for page in pages for label in page["labels"]]
    assert [len(page["labels"]) for page in pages] == [12, 10, 12, 10, 7]
    assert len(assigned) == len(set(assigned)) == 51
    assert set(assigned) == set(REGISTRY.profile_labels("full"))
    assert assigned != list(REGISTRY.profile_labels("full"))
    rendered = paginate_contact_sheet_groups(
        [(name, list(labels)) for name, labels in REGISTRY.profile_groups("full")],
        explicit_pages=pages,
    )
    assert len(rendered) == 5
    assert [len(page[0][1]) for page in rendered] == [12, 10, 12, 10, 7]
    assert "starter-selection-confirmation" in compiled["retired_ids"]
    assert REGISTRY["starter-selection-confirmation"].placements == ()
    runtime_source = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    ).read_text("utf-8")
    assert "_capture_starter_confirmation" not in runtime_source


def test_primary_today_cards_and_reward_receipt_surfaces_are_active() -> None:
    full = set(REGISTRY.profile_labels("full"))
    assert {"progress-today-page", "reviewer-hud-expanded", "reviewer-reward-dock-bundle", "session-summary-after-review", "sync-rewards-summary"} <= full
    assert "shop-fertilizer-confirmation" in full


def test_reward_presentation_surfaces_own_direct_imports() -> None:
    """Keep exact renderer ownership closed over reward presentation imports."""

    for surface in REGISTRY.active_surfaces:
        dependencies = set(surface.owned_module_dependencies)
        if "reward_presentation.py" in dependencies:
            assert {
                "garden_finds.py",
                "ui/session_summary.py",
            } <= dependencies, surface.stable_id




def test_session_summary_capture_issue_reducer_is_fail_closed() -> None:
    check = _compiled_runtime_function("session_summary_capture_issue_codes")
    evidence = {
        "visible": True,
        "contained": True,
        "viewport_size_passed": True,
        "parent_is_main_webview": True,
        "focus_safe": True,
        "shell_siblings": True,
        "footer_viewport_clear": True,
        "last_body_reachable": True,
        "final_boost_reachable": True,
        "copy_passed": True,
        "zero_sections_passed": True,
        "accounting_passed": True,
        "progress_passed": True,
        "authoritative_cards_total_passed": True,
        "actions_passed": True,
        "highlights_passed": True,
        "art_passed": True,
        "boost_art_passed": True,
        "boost_layout_passed": True,
        "garden_item_taxonomy_passed": True,
        "standard_find_identity_passed": True,
        "hero_spacing_passed": True,
        "static_card_semantics_passed": True,
        "open_garden_capitalization_passed": True,
        "bounds": [1274, 20, 416, 780],
        "expected_bounds": [1274, 20, 416, 780],
        "container_size": [1710, 1041],
        "summary_home_clearance_measured": True,
        "summary_home_clearance_horizontal_overlap": False,
        "summary_home_clearance_bottom": None,
        "summary_home_clearance_source": "none",
        "summary_home_clearance_applied": False,
        "summary_home_clearance_telemetry": {
            "schema_version": 1,
            "source": "home-garden-dom",
            "measured": True,
            "rect": {"left": 80, "right": 620, "bottom": 240},
            "viewport": {"width": 1710, "height": 1041},
        },
        "right_margin": 20,
        "top_margin": 20,
        "bottom_margin": 20,
        "header_height": 56,
        "scroll_count": 1,
        "horizontal_scroll_maximum": 0,
        "vertical_scroll_maximum": 0,
        "information_order": [
            "hero",
            "today",
            "highlights",
            "rewards",
            "active_boosts",
        ],
        "reward_metric_order": [
            "growth_applied",
            "garden_coins",
            "standard_finds",
        ],
        "project_progress_placement": "breakdown",
        "landmark_growth_units": 0,
        "project_growth_units": 12_500,
        "project_allocation_count": 1,
        "growth_breakdown_expanded": False,
        "expanded_accounting_copy_passed": False,
        "device_pixel_ratio": 2.0,
    }

    assert check(
        evidence,
        require_little_scroll=True,
        require_retina=True,
    ) == ()
    assert check(
        {**evidence, "vertical_scroll_maximum": 120},
        require_scroll=True,
    ) == ()
    assert check({
        **evidence,
        "compact_density": True,
        "header_height": 44,
    }) == ()
    assert check({
        **evidence,
        "compact_density": True,
        "header_height": 52,
    }) == ("header-height",)
    assert check(
        {**evidence, "vertical_scroll_maximum": 1},
        require_little_scroll=True,
    ) == ("unexpected-default-scroll",)
    assert check(evidence, require_scroll=True) == ("missing-required-scroll",)
    assert check({
        **evidence,
        "authoritative_cards_total_passed": False,
    }) == ("authoritative-cards-total-passed",)
    assert check(
        {
            **evidence,
            "footer_viewport_clear": False,
            "art_passed": False,
            "growth_breakdown_expanded": True,
            "expanded_accounting_copy_passed": False,
            "device_pixel_ratio": 1.0,
        },
        require_expanded=True,
        require_retina=True,
    ) == (
        "footer-viewport-clear",
        "art-passed",
        "expanded-accounting-copy",
        "retina-device-pixel-ratio",
    )


def test_session_summary_content_matrix_reducers_are_fail_closed() -> None:
    check_state = _compiled_runtime_function(
        "session_summary_content_state_issue_codes"
    )
    check_matrix = _compiled_runtime_function(
        "session_summary_content_matrix_issue_codes"
    )
    state_requirements = {
        "complete": (
            "complete_copy",
            "complete_progress",
            "complete_actions",
        ),
        "sparse-zero-sections": (
            "zero_sections_omitted",
            "zero_rows_omitted",
        ),
        "long-names-six-digit-totals": (
            "long_names_preserved",
            "six_digit_totals_present",
            "long_find_item_preserved",
            "retina_find_art_present",
        ),
        "highlight-overflow-max-two": (
            "highlight_source_overflow",
            "highlight_max_two",
            "highlight_overflow_preserved",
            "highlight_priority_preserved",
        ),
        "missing-art-branded-fallback": (
            "missing_art_detected",
            "branded_fallback_present",
        ),
        "finds-three-identical": (
            "finds_reconciled",
            "single_find_group",
            "identical_find_quantity_aggregated",
            "granted_item_copy_present",
        ),
        "finds-three-distinct": (
            "finds_reconciled",
            "three_find_groups",
            "distinct_find_groups_visible",
            "distinct_find_art_provenance",
            "granted_item_copy_present",
        ),
        "finds-unreconciled-omitted": (
            "finds_unreconciled",
            "partial_find_list_omitted",
            "find_total_preserved",
        ),
        "no-finds": (
            "find_metric_omitted",
            "find_rows_omitted",
        ),
        "no-boosts": (
            "boost_section_omitted",
            "boost_rows_omitted",
        ),
        "one-boost": (
            "one_boost_row",
            "single_boost_group",
        ),
        "expanded-reward-details": (
            "reward_details_expanded",
            "expanded_accounting_complete",
            "all_find_groups_reachable",
        ),
        "dark-appearance": (
            "dark_palette_applied",
            "appearance_tokens_applied",
        ),
        "light-appearance": (
            "light_palette_applied",
            "appearance_tokens_applied",
        ),
        "hero-spacing": (
            "hero_spacing_compact",
            "hero_copy_grouped",
        ),
        "static-card-semantics": (
            "highlight_cards_static",
            "reward_metrics_static",
            "boost_rows_static",
            "static_cards_focus_safe",
            "static_cards_noninteractive_cursor",
        ),
    }
    records: dict[str, object] = {}
    for name, requirements in state_requirements.items():
        evidence = {
            "visible": True,
            "contained": True,
            "single_scroll_owner": True,
            "no_horizontal_overflow": True,
            "explicit_cards_total": True,
            **{requirement: True for requirement in requirements},
        }
        assert check_state(name, evidence) == ()
        records[name] = {**evidence, "passed": True}

    assert check_state("unknown", {}) == ("unknown-content-state",)
    assert check_state(
        "complete",
        {
            key: value
            for key, value in dict(records["complete"]).items()
            if key not in {"explicit_cards_total", "passed"}
        },
    ) == ("explicit-cards-total",)
    assert check_state(
        "highlight-overflow-max-two",
        {
            "visible": True,
            "contained": True,
            "single_scroll_owner": True,
            "no_horizontal_overflow": True,
            "explicit_cards_total": True,
            "highlight_source_overflow": True,
            "highlight_max_two": False,
            "highlight_overflow_preserved": True,
            "highlight_priority_preserved": True,
        },
    ) == ("highlight-max-two",)
    assert check_matrix(
        records,
        canonical_payload_restored=True,
    ) == ()
    assert check_matrix(
        {
            **records,
            "missing-art-branded-fallback": {
                **dict(records["missing-art-branded-fallback"]),
                "passed": False,
            },
        },
        canonical_payload_restored=False,
    ) == (
        "content-state-failed:missing-art-branded-fallback",
        "canonical-payload-not-restored",
    )


def test_session_summary_capture_fixture_binds_exact_accounting_and_art() -> None:
    source = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_session_summary_after_review",
    )

    assert "plant_growth_total_units=148_600" in source
    assert "shared_growth_total_units=59_400" in source
    assert "StoredGrowthTotal(1_250, 1_250, 0)" in source
    assert '"Review rewards",\n                    17' in source
    assert '"Full Bloom bonus",\n                    50' in source
    assert '"capture-coins-full-bloom",\n                    "full_bloom_bonus"' in source
    assert 'source="full_bloom_bonus"' in source
    assert 'coin_award_event_ids=("capture-coins-full-bloom",)' in source
    assert "coin_included_in_total=True" in source
    assert 'resolve_plant_asset(\n                "wisteria",\n                "rare"' in source
    assert '"firefly_lantern",\n                "Firefly Lantern"' in source
    assert '"garden_feature",\n                "Rare"' in source
    assert 'unlock_category="garden_item"' in source
    assert "capture_home_new_cards = 1" in source
    assert "capture_home_learn_cards = 0" in source
    assert "capture_home_due_cards = 18" in source
    assert "capture_today_cards_total = (" in source
    assert source.count("cards_total=capture_today_cards_total") == 2
    assert "cards_remaining=capture_cards_remaining" in source
    assert "total_finds=3" in source
    assert '"find_small_charge",\n                    "Charged Seed"' in source
    assert '"+1 Small Growth Charge"' in source
    assert '"ui_growth_charge_small"' in source
    assert 'item_id="growth_charge_small"' in source
    assert source.count("quantity=1") >= 3
    assert '"Garden Pouch"' in source
    assert '"garden_pouch"' in source
    assert '"Morning Dew"' in source
    assert '"morning_dew"' in source
    assert "reward_receipts=(" in source


def test_sync_reward_capture_fixture_is_rich_multiday_and_nonmodal() -> None:
    subtitle = _runtime_literal("SYNC_REWARD_CAPTURE_SUBTITLE")
    facts = _runtime_literal("SYNC_REWARD_CAPTURE_MODEL_FACTS")
    capture = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_sync_rewards_summary",
    )
    audit = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_sync_reward_summary_geometry_audit",
    )
    runtime_source = (
        Path(capture_sequence.REPO_ROOT)
        / "ankigarden"
        / "capture"
        / "runtime.py"
    ).read_text("utf-8")

    assert subtitle == "Rewards added after syncing"
    assert facts == {
        "anki_days": ("2026-08-28", "2026-08-29"),
        "eligible_answer_count": 42,
        "growth_total_units": 52_000,
        "plant_growth_units": 42_000,
        "shared_growth_delta_units": 8_000,
        "stored_growth_delta_units": 0,
        "landmark_growth_delta_units": 2_000,
        "mastery_growth_delta_units": 0,
        "legacy_growth_delta_units": 0,
        "project_allocations": (("landmark", "garden_landmark", 2_000),),
        "garden_coin_delta": 12,
        "find_quantity": 0,
        "environment_count": 1,
        "progression_event_count": 2,
        "all_clear_coin_reward": 0,
        "fertilizer_remaining_seconds": 0,
        "fertilizer_item_id": "",
        "booster_cards_remaining": 0,
        "booster_item_id": "",
    }
    assert "SyncRewardSummaryCard(" in capture
    assert "animations_enabled=False" in capture
    assert '"firefly_lantern"' in capture
    assert '"Wisteria reached Full Bloom"' in capture
    assert 'display_text="75% toward Flowering reached"' in capture
    assert "plant_results=(" in capture
    assert "all_clear_earned=False" in capture
    assert "_sync_reward_summary_geometry_audit" in capture
    assert "_capture_and_advance(\n                    label,\n                    mw," in capture
    assert "sync_reward_summary_geometry" in audit
    assert "len(scrolls) == 1" in audit
    assert "WA_ShowWithoutActivating" in audit
    assert "Qt.FocusPolicy.NoFocus" in audit
    assert "400 <= int(bounds[2]) <= 480" in audit
    assert "int(bounds[1]) == 24" in audit
    assert "SYNC_REWARD_CAPTURE_SUBTITLE" in audit
    assert 'candidate.property("gardenAssetThumbnail") is True' in audit
    assert '"checkpoint_badge"' in audit
    assert '"initial_reward_visible": initial_reward_visible' in audit
    assert '"boost_art_passed": boost_art_passed' in audit
    stability = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_home_surface_stability_signature",
    )
    stability_wait = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_wait_for_home_visual_stability",
    )
    assert 'label == "sync-rewards-summary"' in stability
    assert 'metrics["generic_content_passed"]' in stability
    assert 'else metrics["passed"]' in stability
    assert "_home_surface_stability_signature(label, widget)" in stability_wait
    assert '"sync-rewards-summary",\n        }:\n            surface = "deckBrowser"' in (
        runtime_source
    )




def test_session_summary_capture_runs_viewport_matrix_before_acquisition() -> None:
    scenario = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_session_summary_after_review",
    )
    matrix = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_exercise_session_summary_viewports",
    )
    postcondition = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )

    assert "_exercise_session_summary_viewports" in scenario
    assert "def matrix_ready(" in scenario
    assert "matrix.get(\"passed\", False)" in scenario
    assert "SESSION_SUMMARY_VIEWPORT_SPECS" in matrix
    assert 'name == "1280x720"' in matrix
    assert 'records["stable_scrollbar_gutter"]' in matrix
    assert 'set(collapsed_body_widths.values()) == {408}' in matrix
    assert 'find_named("ankiGardenSessionBreakdownToggle")' in matrix
    assert "mw.showMaximized()" in matrix
    assert "SESSION_SUMMARY_REQUIRED_CONTENT_STATES" in matrix
    assert "def exercise_content_states" in matrix
    assert "_set_session_summary_capture_payload" in matrix
    assert "session_summary_content_matrix_issue_codes" in matrix
    assert 'records["content_states"]' in matrix
    assert "canonical_payload_restored" in matrix
    assert '"finds-three-identical"' in matrix
    assert '"finds-three-distinct"' in matrix
    assert '"distinct_find_art_provenance"' in (
        Path(capture_sequence.REPO_ROOT)
        / "ankigarden"
        / "capture"
        / "runtime.py"
    ).read_text("utf-8")
    assert '"finds-unreconciled-omitted"' in matrix
    assert '"no-finds"' in matrix
    assert '"no-boosts"' in matrix
    assert '"one-boost"' in matrix
    assert '"expanded-reward-details"' in matrix
    assert 'name == "dark-appearance"' in matrix
    assert 'name == "light-appearance"' in matrix
    assert '"hero-spacing"' in matrix
    assert '"static-card-semantics"' in matrix
    assert "reward_amount=123_456" in matrix
    assert '"+123,456 Small Growth Charges from the "' in matrix
    assert "capture_home_new_cards = 1" in scenario
    assert "capture_home_learn_cards = 0" in scenario
    assert "capture_home_due_cards = 18" in scenario
    assert 'observed.get("remainingAfter")' in scenario
    assert '"session_summary_content_matrix": content_matrix' in scenario
    assert '"19 cards remaining" in normalized_summary_copy' in postcondition
    assert '"126 of 145 cards completed" in normalized_summary_copy' in postcondition
    assert '"reward breakdown" in normalized_summary_copy' in postcondition
    assert 'home_counts.get("newAfter") == "1"' in postcondition
    assert 'home_counts.get("learnAfter") == "0"' in postcondition
    assert 'home_counts.get("dueAfter") == "18"' in postcondition
    assert 'home_counts.get("remainingAfter") == 19' in postcondition


def test_collection_capture_summary_matches_current_catalog_fixture() -> None:
    postcondition = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_fixture_postcondition",
    )
    assert "expected_collected_count = 30" in postcondition
    assert "expected_collectible_count = 39" in postcondition
    assert 'count_widget.property("collectedCount")' in postcondition
    assert 'count_widget.property("collectibleCount")' in postcondition




def test_retired_ids_are_reserved_and_no_longer_active() -> None:
    stable_id = REGISTRY.profile_labels("full")[-1]
    retired = REGISTRY.retire(stable_id, "surface removed from the product")

    assert stable_id not in retired.profile_labels("full")
    assert retired[stable_id].retired_reason
    with pytest.raises(ValueError, match="permanently reserved"):
        retired.add(REGISTRY[stable_id])


def test_reordering_changes_only_profile_topology() -> None:
    first_id, second_id = "collection-plants-page", "collection-species-details"
    first = next(item for item in REGISTRY[first_id].placements if item.profile == "full")
    second = next(item for item in REGISTRY[second_id].placements if item.profile == "full")
    swapped = SurfaceRegistry(
        _replace_full_placement(second_id, replace(first, profile="full"))
        if surface.stable_id == second_id
        else _replace_full_placement(first_id, replace(second, profile="full"))
        if surface.stable_id == first_id
        else surface
        for surface in REGISTRY.surfaces
    )

    assert swapped.profile_labels("full")[first.order] == second_id
    assert swapped.profile_labels("full")[second.order] == first_id
    assert swapped.surface_digest(first_id) == REGISTRY.surface_digest(first_id)
    assert swapped.profile_digest("full") != REGISTRY.profile_digest("full")


def test_profile_rejects_a_dependency_after_its_dependent_surface() -> None:
    prerequisite_id = "garden-inspector-nurtured"
    dependent_id = "active-deck-browser-home-after-nurture"
    prerequisite = next(
        item for item in REGISTRY[prerequisite_id].placements if item.profile == "full"
    )
    dependent = next(
        item for item in REGISTRY[dependent_id].placements if item.profile == "full"
    )

    with pytest.raises(ValueError, match="places prerequisite"):
        SurfaceRegistry(
            _replace_full_placement(
                prerequisite_id,
                replace(prerequisite, order=dependent.order),
            )
            if surface.stable_id == prerequisite_id
            else _replace_full_placement(
                dependent_id,
                replace(dependent, order=prerequisite.order),
            )
            if surface.stable_id == dependent_id
            else surface
            for surface in REGISTRY.surfaces
        )


def test_native_dialog_grab_is_fail_closed_without_screen_fallback() -> None:
    spec = REGISTRY["garden-starter-picker"]
    semantic_advisory = select_candidate(
        spec,
        (
            _candidate(
                "qt-widget-grab",
                semantic_state_valid=False,
                overlay_pixels_present=False,
            ),
        ),
    )
    decision = select_candidate(
        spec,
        (
            _candidate("qt-widget-grab", blank=True),
            _candidate("foreground-screen-region"),
        ),
    )

    assert semantic_advisory.accepted is not None
    assert decision.accepted is None
    assert decision.failure_reason == "blank-pixmap"
    assert {row.reason for row in decision.rejected} == {
        "backend-not-allowed",
        "blank-pixmap",
    }


def test_home_prefers_app_owned_webview_and_requires_exact_fallback_identity() -> None:
    spec = REGISTRY["starter-deck-browser-home"]
    identity = AcquisitionIdentity(11, 22, "main-window", (1, 2, 800, 600), 1.0)
    native = _candidate("qt-shell-with-webview")
    fallback = _candidate(
        "foreground-screen-region",
        process_id=11,
        window_id=22,
        window_role="main-window",
        bounds=(1, 2, 800, 600),
    )

    assert select_candidate(
        spec,
        (fallback, native),
        expected_identity=identity,
    ).accepted is native
    rejected = select_candidate(
        spec,
        (replace(native, blank=True), replace(fallback, process_id=99)),
        expected_identity=identity,
    )
    assert rejected.accepted is None
    assert rejected.failure_reason == "no-verified-capture-candidate"
    assert [row.reason for row in rejected.rejected] == [
        "blank-pixmap",
        "process-id-mismatch",
    ]

    families = {label: REGISTRY[label].renderer_family
                for label in REGISTRY.profile_labels("full")}
    requests = [{"label": label, "reason": reason, "confirmed": False,
                 "process_id": 11, "window_id": 22}
                for label, family in families.items() if family == "AnkiQt"
                for reason in ("pointer-neutralization", "app-owned-home-composite-not-ready")]
    assert len(requests) > 2
    assert foreground_request_issue_codes(requests, families) == ()
    assert foreground_request_issue_codes([*requests, requests[0]], families)
    assert foreground_request_issue_codes(
        [{**requests[0], "label": "garden-starter-picker"}], families,
    )
    assert foreground_request_issue_codes(
        [{**requests[0], "window_id": None}], families,
    )



def test_move_mode_semantic_copy_facts_are_declared() -> None:
    required = set(REGISTRY["move-mode"].state_contract["required_facts"])

    assert {"move_bonsai_title", "move_swap_copy"}.issubset(required)


def test_capture_plan_keeps_checkpoint_domains_inside_one_session() -> None:
    requested = ("garden-starter-picker", "garden-inspector-nurtured", "reviewer-hud-expanded")
    plan = build_capture_plan(REGISTRY, profile="representative", requested=requested)
    assert plan.requested == requested
    assert tuple(label for _name, labels in plan.cohorts for label in labels) == requested


def test_reviewer_readiness_callback_failure_restores_fixture_once() -> None:
    callbacks = []
    events = []
    web = SimpleNamespace(
        isVisible=lambda: True,
        page=lambda: SimpleNamespace(
            runJavaScript=lambda *_args: _args[-1]({"ready": True}),
        ),
    )
    namespace = {
        "mw": SimpleNamespace(state="review", reviewer=SimpleNamespace(web=web)),
        "QTimer": SimpleNamespace(singleShot=lambda _delay, callback: callbacks.append(callback)),
        "logger": SimpleNamespace(exception=lambda *_args: None),
    }
    guard = _compiled_runtime_method("_UiFaceCaptureRunner", "_one_shot_async_callback", namespace)
    wait = _compiled_runtime_method("_UiFaceCaptureRunner", "_wait_for_reviewer_surface", namespace)
    harness = SimpleNamespace(_failures=[], _next_after=lambda _delay: events.append("next"))
    harness._one_shot_async_callback = lambda *args, **kwargs: guard(harness, *args, **kwargs)

    def failed_ready():
        raise RuntimeError("Reviewer fixture failed after the card was ready")

    wait(harness, "workspace-reviewer-collapsed", failed_ready,
         on_error=lambda: events.append("restored"))
    for callback in callbacks:
        callback()
    assert events == ["restored", "next"]
    assert len(harness._failures) == 1
    assert harness._failures[0]["label"] == "workspace-reviewer-collapsed"






def test_diagnostics_fixture_records_missing_artwork_with_keyword_arguments() -> None:
    runtime_path = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    )
    runtime_tree = ast.parse(runtime_path.read_text())
    fixture_method = next(
        node
        for node in ast.walk(runtime_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_capture_settings_warning_after"
    )
    recorder_call = next(
        node
        for node in ast.walk(fixture_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_record_missing_artwork"
    )

    assert recorder_call.args == []
    assert {keyword.arg for keyword in recorder_call.keywords} == {
        "category",
        "item_key",
        "source_path",
    }


def test_failure_ledger_isolates_local_checkpoint_and_run_gate_failures() -> None:
    local_id = "garden-starter-picker"
    checkpoint_id = "garden-inspector-nurtured"
    ledger = FailureLedger(REGISTRY)

    ledger.record(_result(local_id, accepted=False, classification="surface-local"))
    assert ledger.may_continue(local_id, cleanup_restored=True)
    assert not ledger.may_continue(local_id, cleanup_restored=False)

    ledger.record(
        _result(checkpoint_id, accepted=False, classification="checkpoint-domain")
    )
    cohort = REGISTRY[checkpoint_id].checkpoint_cohort
    assert all(
        ledger.blocked.get(surface.stable_id) == checkpoint_id
        for surface in REGISTRY.active_surfaces
        if surface.checkpoint_cohort == cohort and surface.stable_id != checkpoint_id
    )

    ledger.record(_result("reviewer-reward-dock-bundle", accepted=False, classification="run-gate"))
    assert ledger.release_blockers == ["reviewer-reward-dock-bundle"]


def test_inspection_cli_is_non_mutating_and_registry_derived(capsys: pytest.CaptureFixture[str]) -> None:
    contract_path = Path(capture_sequence.CAPTURE_CONTRACT_PATH)
    before = contract_path.read_bytes()

    assert capture_sequence.main(["--list-surfaces"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in listed["surfaces"]] == list(
        REGISTRY.profile_labels("full")
    )
    assert capture_sequence.main([
        "--plan-only",
        "--surface",
        "garden-starter-picker",
    ]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["process_count"] == 1
    assert planned["process_strategy"] == "single-session"
    assert planned["run_gate_process"] == "same-session-or-zero-surface-when-reused"
    assert capture_sequence.main([
        "--plan-only", "--profile", "full", "--fresh-baseline",
    ]) == 0
    full = json.loads(capsys.readouterr().out)
    assert full["requested"] == full["execution"] == list(REGISTRY.profile_labels("full"))
    assert full["process_count"] == 1
    assert full["capture_mode"] == "fresh-baseline"
    assert full["historical_reuse_allowed"] is False
    assert contract_path.read_bytes() == before


def test_production_package_excludes_complete_capture_subtree() -> None:
    production = {
        path.relative_to(Path(capture_sequence.REPO_ROOT) / "ankigarden").as_posix()
        for path in package_files(PRODUCTION_BUILD)
    }
    capture = {
        path.relative_to(Path(capture_sequence.REPO_ROOT) / "ankigarden").as_posix()
        for path in package_files(CAPTURE_BUILD)
    }

    assert "capture_ui_faces.py" not in production
    assert not any(name.startswith("capture/") for name in production)
    assert "capture_ui_faces.py" in capture
    assert "capture/runtime.py" in capture
    assert "capture/capture-contract-v25.json" in capture
    assert "capture/capture-contract-v26.json" in capture
    assert production < capture
