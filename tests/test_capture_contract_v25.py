from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

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
    assert compiled["contract_version"] == 26
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
        "starter-deck-browser-home": ("first_run", 1),
        "starter-garden-onboarding": ("first_run", 2),
        "starter-nursery-plants": ("first_run", 3),
        "starter-placement": ("first_run", 4),
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
    queue_id = "purchase-confirmation-fertilizer-queue"
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
        "scenario 'fertilizer_queue' has multiple seeded checkpoint lineages"
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
        "unexpected v26 scenario identity" in issue
        for issue in scenario_error.value.issues
    )

    bad_totals = copy.deepcopy(compiled)
    bad_totals["profiles"]["representative"]["surface_count"] = 17
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
    assert len(REGISTRY.profile_labels("representative")) == 18
    assert len(REGISTRY.profile_labels("full")) == 34
    assert REGISTRY.profile_labels("full")[23] == (
        "nursery-garden-decorations-scenery"
    )
    assert not REGISTRY["nursery-weather-scenery"].active
    assert "nursery-weather-scenery" in compiled["retired_ids"]
    representative_labels = REGISTRY.profile_labels("representative")
    assert representative_labels[12] == "reviewer-hud-expanded"
    assert representative_labels[13] == "session-summary-after-review"
    assert representative_labels[14] == "sync-rewards-summary"
    assert representative_labels[15] == "reviewer-reward-dock-bundle"
    assert REGISTRY.profile_page_count("representative") == 2
    assert REGISTRY.profile_page_count("full") == 5
    assert "starter-selection-confirmation" in compiled["retired_ids"]
    assert REGISTRY["starter-selection-confirmation"].placements == ()
    runtime_source = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    ).read_text("utf-8")
    assert "_capture_starter_confirmation" not in runtime_source


def test_primary_today_cards_and_reward_receipt_surfaces_are_active() -> None:
    representative = REGISTRY.profile_labels("representative")
    full = REGISTRY.profile_labels("full")

    assert {
        "reviewer-hud-expanded",
        "reviewer-reward-dock-bundle",
        "session-summary-after-review",
        "sync-rewards-summary",
    } <= set(representative)
    assert "progress-today-cards" not in representative
    assert {
        "progress-today-cards",
        "reviewer-hud-expanded",
        "reviewer-reward-dock-bundle",
        "session-summary-after-review",
        "sync-rewards-summary",
    } <= set(full)
    assert full.index("progress-today-cards") < full.index("growth-nonzero")

    assert "purchase-confirmation-fertilizer-queue" in full
    assert "fertilizer-replacement-confirmation" not in full
    assert not REGISTRY["fertilizer-replacement-confirmation"].active
    queue = REGISTRY["purchase-confirmation-fertilizer-queue"]
    assert queue.renderer_family == "PurchaseConfirmationDialog"
    assert queue.state_contract["profile"]["purchase_status"] == "ready"
    assert "fertilizer_queue_confirmation" in queue.state_contract[
        "required_facts"
    ]
    source = REGISTRY["fertilizer-active"]
    assert "fertilizer_flow_source" in source.state_contract["required_facts"]

    today = REGISTRY["progress-today-cards"]
    assert today.renderer_family == "GardenProgressDialog"
    assert today.state_contract["profile"]["page"] == "today"
    assert "today_cards_progress_surface" in today.state_contract["required_facts"]

    hud = REGISTRY["reviewer-hud-expanded"]
    assert hud.state_contract["kind"] == "reviewer_hud"
    assert hud.state_contract["profile"]["expanded"] is True
    assert hud.state_contract["profile"]["dock"] == "right"
    assert "ui/reviewer_hud_widget.py" in hud.owned_module_dependencies
    assert {
        "reviewer_hud_visible",
        "reviewer_hud_geometry",
        "reviewer_hud_viewport_matrix",
        "reviewer_hud_content_matrix",
        "reviewer_hud_resilience_matrix",
        "reviewer_window_screen_filling",
    } <= set(hud.state_contract["required_facts"])

    summary = REGISTRY["session-summary-after-review"]
    assert summary.renderer_family == "AnkiQt"
    assert {
        "session_summary_visible",
        "session_summary_geometry",
        "session_summary_copy",
        "session_summary_viewport_matrix",
        "session_summary_content_matrix",
        "session_summary_home_counts",
        "session_summary_window_screen_filling",
    } <= set(summary.state_contract["required_facts"])

    sync_summary = REGISTRY["sync-rewards-summary"]
    assert sync_summary.renderer_family == "AnkiQt"
    assert sync_summary.executor == "_capture_sync_rewards_summary"
    assert set(sync_summary.owned_module_dependencies) == {
        "asset_manager.py",
        "garden_finds.py",
        "models/sync_reward.py",
        "reward_presentation.py",
        "ui/environment_art.py",
        "ui/garden_asset_thumbnail.py",
        "ui/plant_art.py",
        "ui/session_summary.py",
        "ui/session_summary_card.py",
        "ui/sync_reward_summary.py",
    }
    assert {
        "sync_reward_summary_visible",
        "sync_reward_summary_geometry",
        "sync_reward_summary_copy",
        "sync_reward_summary_content",
        "sync_reward_summary_nonmodal",
        "sync_reward_summary_window_screen_filling",
    } <= set(sync_summary.state_contract["required_facts"])

    retired_stack = REGISTRY["reviewer-find-stacked-sync"]
    assert retired_stack.active is False
    assert retired_stack.placements == ()
    assert "integrated" in retired_stack.retired_reason.casefold()

    reward_dock = REGISTRY["reviewer-reward-dock-bundle"]
    assert reward_dock.state_contract["kind"] == "reviewer_hud"
    assert reward_dock.state_contract["profile"]["reward_event_count"] == 7
    assert "ui/reviewer_hud_widget.py" in reward_dock.owned_module_dependencies
    assert {
        "reviewer_reward_dock_visible",
        "reviewer_reward_dock_geometry",
        "reviewer_reward_bundle",
        "reviewer_session_footer",
        "reviewer_reward_interaction_matrix",
        "reviewer_hud_content_matrix",
        "canonical_reviewer_reward_projection",
    } <= set(reward_dock.state_contract["required_facts"])


def test_session_summary_responsive_evidence_is_transient_not_new_surfaces() -> None:
    specs = _runtime_literal("SESSION_SUMMARY_VIEWPORT_SPECS")
    content_states = _runtime_literal("SESSION_SUMMARY_REQUIRED_CONTENT_STATES")

    assert specs == (
        ("1280x720", 1280, 720, False, True, False),
        ("1440x900", 1440, 900, True, False, False),
        ("1600x960", 1600, 960, True, False, False),
        ("retina-1710x1041", 1710, 1041, True, False, True),
    )
    labels = set(REGISTRY.profile_labels("representative")) | set(
        REGISTRY.profile_labels("full")
    )
    assert {row[0] for row in specs}.isdisjoint(labels)
    assert content_states == (
        "complete",
        "sparse-zero-sections",
        "long-names-six-digit-totals",
        "highlight-overflow-max-two",
        "missing-art-branded-fallback",
        "finds-three-identical",
        "finds-three-distinct",
        "finds-unreconciled-omitted",
        "no-finds",
        "no-boosts",
        "one-boost",
        "expanded-reward-details",
        "dark-appearance",
        "light-appearance",
        "hero-spacing",
        "static-card-semantics",
    )
    assert set(content_states).isdisjoint(labels)
    assert len(REGISTRY.profile_labels("representative")) == 18
    assert len(REGISTRY.profile_labels("full")) == 34


def test_reward_presentation_surfaces_own_session_summary_import() -> None:
    """Keep exact renderer ownership closed over reward presentation imports."""

    for surface in REGISTRY.active_surfaces:
        dependencies = set(surface.owned_module_dependencies)
        if "reward_presentation.py" in dependencies:
            assert "ui/session_summary.py" in dependencies, surface.stable_id


def test_reviewer_hud_acceptance_matrix_is_transient_and_complete() -> None:
    window_states = _runtime_literal("REVIEWER_HUD_REQUIRED_WINDOW_STATES")
    viewport_specs = _runtime_literal("REVIEWER_HUD_VIEWPORT_SPECS")
    baseline_states = _runtime_literal("REVIEWER_HUD_BASELINE_CONTENT_STATES")
    reward_states = _runtime_literal("REVIEWER_REWARD_CONTENT_STATES")
    resilience_states = _runtime_literal("REVIEWER_HUD_RESILIENCE_STATES")
    required_states = _runtime_literal("REVIEWER_HUD_REQUIRED_CONTENT_STATES")

    assert window_states == (
        "1710x1041",
        "1600x1000",
        "1280x800",
        "short-height",
        "expanded",
        "collapsed",
    )
    assert len(viewport_specs) == 5
    assert set().union(*(set(spec[5]) for spec in viewport_specs)) == set(window_states)
    assert required_states == (*baseline_states, *reward_states)
    assert len(required_states) == 46
    assert len(set(required_states)) == 46
    assert baseline_states == (
        "18-cards-left",
        "1-card-left",
        "no-session-rewards",
        "growth-only",
        "growth-and-coins",
        "progress-10-percent",
        "progress-38-percent",
        "before-checkpoint",
        "exact-checkpoint",
        "checkpoint-marker-semantics",
        "early-stage-art",
        "mature-stage-art",
        "zero-effects",
        "one-effect",
        "two-effects",
        "three-plus-effects",
        "long-effects-one-column",
        "short-plant-name",
        "two-line-plant-name",
        "estimate-1-card",
        "estimate-14-cards",
        "estimate-1240-cards",
        "checkpoint-crossing",
        "multiple-checkpoints-one-answer",
        "stage-change",
        "coin-balance-248",
        "coin-balance-9999",
        "coin-balance-10013",
        "coin-balance-999999",
        "coin-balance-1000000",
        "header-stable-grouping",
        "short-height",
    )
    assert reward_states == (
        "all-cards-complete",
        "one-garden-find",
        "discovery-new-wording",
        "full-bloom",
        "full-bloom-celebration",
        "full-bloom-settled",
        "full-bloom-details",
        "full-bloom-several-secondary",
        "reward-details-action-copy",
        "settled-height-or-safe-scroll",
        "full-bloom-short-height",
        "session-footer-reconciliation",
        "reward-reveal-lifecycle",
        "session-history-named-growth",
    )
    assert resilience_states == (
        "no-active-plant",
        "stored-growth",
        "collapsed-unseen-reward",
        "rapid-successive-rewards",
        "collection-sync-hud-open",
        "reviewer-reload-after-reward",
        "history-reopen",
        "no-replay",
        "details-pause-archive",
        "archive-after-next-commit",
    )

    labels = set(REGISTRY.profile_labels("representative")) | set(
        REGISTRY.profile_labels("full")
    )
    assert {spec[0] for spec in viewport_specs}.isdisjoint(labels)
    assert set(required_states).isdisjoint(labels)

    expanded = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_reviewer_hud_expanded",
    )
    reward = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_capture_reviewer_reward_dock_bundle",
    )
    matrix = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_exercise_reviewer_hud_acceptance_matrix",
    )
    reward_matrix = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_exercise_reviewer_reward_interaction_matrix",
    )
    reward_geometry = _runtime_method_source(
        "_UiFaceCaptureRunner",
        "_reviewer_reward_dock_geometry_audit",
    )
    widget_source = (
        Path(capture_sequence.REPO_ROOT)
        / "ankigarden"
        / "ui"
        / "reviewer_hud_widget.py"
    ).read_text("utf-8")
    assert "_exercise_reviewer_hud_acceptance_matrix" in expanded
    assert "reviewer_hud_viewport_matrix" in expanded
    assert "reviewer_hud_content_matrix" in expanded
    assert "reviewer_hud_resilience_matrix" in expanded
    assert "_exercise_reviewer_reward_interaction_matrix" in reward
    assert "reviewer_reward_interaction_matrix" in reward
    for hook in (
        "checkpointPercents",
        "checkpointMarkerStates",
        "currentPositionHandleVisible",
        "reviewerHudTitleGroup",
        "reviewerHudHeaderActions",
        "hudHeaderBalanceReservedWidth",
    ):
        assert hook in matrix
        assert hook in widget_source
    for hook in (
        "hudRewardSummaryIconKind",
        "milestoneMedallion",
        "rewardDetailEventIds",
        "rewardEventIds",
        "rewardRevealState",
    ):
        assert hook in reward_matrix
        assert hook in widget_source
    assert "reviewerHudRewardDetailsToggle" in reward_geometry
    assert "reviewerHudRewardDetailsToggle" in widget_source
    assert "_reward_details_toggle" in reward_matrix
    assert 'compact["details_click_height"] >= 28' in reward_matrix
    assert "self._reward_details_toggle.setMinimumHeight(28)" in widget_source
    assert 'ReviewGardenHud._set_reward_reveal_state(self, "settled")' in widget_source
    assert 'self.clear_reward(reveal_state="archived")' in widget_source
    assert "project_reward_session_history(atomic_bundles)" in widget_source
    assert 'self._effects.setProperty("singleColumn", single_column)' in widget_source
    assert 'self._today_card.setProperty("nearComplete", near_complete)' in widget_source
    assert "diameter = 4.5" in widget_source
    assert "min(right - 2.5, natural_x)" in widget_source
    assert '"Checkpoint reward", self._checkpoint_reward_row' in widget_source
    assert len(REGISTRY.profile_labels("representative")) == 18
    assert len(REGISTRY.profile_labels("full")) == 34


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

    assert subtitle == "Rewards from 42 card answers on another device."
    assert facts == {
        "anki_days": ("2026-08-28", "2026-08-29"),
        "eligible_answer_count": 42,
        "growth_total_units": 52_000,
        "plant_growth_units": 42_000,
        "shared_growth_delta_units": 8_000,
        "stored_growth_delta_units": 2_000,
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


def test_sync_reward_home_stability_uses_painted_content_without_weakening_home():
    class FakeSize:
        def width(self) -> int:
            return 1710

        def height(self) -> int:
            return 950

    class FakeLayout:
        def sizeHint(self) -> FakeSize:
            return FakeSize()

    class FakeWeb:
        def isVisible(self) -> bool:
            return True

        def width(self) -> int:
            return 1710

        def height(self) -> int:
            return 950

        def grab(self) -> object:
            return object()

    class FakeWidget:
        def __init__(self) -> None:
            self.web = FakeWeb()

        def layout(self) -> FakeLayout:
            return FakeLayout()

        def findChildren(self, _kind: type) -> list[object]:
            return []

        def isVisible(self) -> bool:
            return True

        def width(self) -> int:
            return 1710

        def height(self) -> int:
            return 950

        def property(self, _name: str) -> str:
            return "default"

    class FakeScrollArea:
        pass

    class FakeRunner:
        def __init__(self) -> None:
            self.metrics = {
                "generic_content_passed": True,
                "passed": False,
            }

        def _sample_pixmap_digest(self, _pixmap: object) -> str:
            return "stable-paint-digest"

        def _home_pixmap_metrics(
            self,
            _pixmap: object,
            *,
            expected_width: int,
            expected_height: int,
        ) -> dict[str, bool]:
            assert (expected_width, expected_height) == (1710, 950)
            return dict(self.metrics)

    main_window = FakeWidget()
    signature = _compiled_runtime_method(
        "_UiFaceCaptureRunner",
        "_home_surface_stability_signature",
        {
            "QWidget": FakeWidget,
            "QAbstractScrollArea": FakeScrollArea,
            "mw": main_window,
        },
    )
    runner = FakeRunner()

    sync = signature(runner, "sync-rewards-summary", main_window)
    ordinary_home = signature(runner, "starter-deck-browser-home", main_window)

    assert sync[:2] == ("home-semantic-paint", True)
    assert ordinary_home[:2] == ("home-semantic-paint", False)
    assert sync[2:] == ordinary_home[2:]

    runner.metrics = {
        "generic_content_passed": True,
        "passed": True,
    }
    assert signature(
        runner,
        "starter-deck-browser-home",
        main_window,
    )[1] is True

    runner.metrics = {
        "generic_content_passed": False,
        "passed": False,
    }
    assert signature(runner, "sync-rewards-summary", main_window)[1] is False


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
    assert '"19 remaining" in normalized_summary_copy' in postcondition
    assert '"126 of 145 completed" in normalized_summary_copy' in postcondition
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


def test_session_summary_find_overflow_disclosure_is_separate_from_plus_three_fixture() -> None:
    source = (
        Path(capture_sequence.REPO_ROOT)
        / "ankigarden"
        / "ui"
        / "session_summary_card.py"
    ).read_text("utf-8")

    assert "visible_limit: int = 3" in source
    assert 'more.setText(f"View {hidden_quantity:,} more Standard Finds")' in source
    assert "more.clicked.connect(self._expand_find_breakdown)" in source


def test_retired_ids_are_reserved_and_no_longer_active() -> None:
    stable_id = REGISTRY.profile_labels("full")[-1]
    retired = REGISTRY.retire(stable_id, "surface removed from the product")

    assert stable_id not in retired.profile_labels("full")
    assert retired[stable_id].retired_reason
    with pytest.raises(ValueError, match="permanently reserved"):
        retired.add(REGISTRY[stable_id])


def test_reordering_changes_only_profile_topology() -> None:
    first_id, second_id = REGISTRY.profile_labels("full")[:2]
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

    assert swapped.profile_labels("full")[:2] == (second_id, first_id)
    assert swapped.surface_digest(first_id) == REGISTRY.surface_digest(first_id)
    assert swapped.profile_digest("full") != REGISTRY.profile_digest("full")


def test_profile_rejects_a_dependency_after_its_dependent_surface() -> None:
    prerequisite_id = "selected-plant-nurtured"
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
    spec = REGISTRY["starter-garden-onboarding"]
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

    runtime_source = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    ).read_text("utf-8")
    assert "mw.showMaximized()" in runtime_source
    assert '"screen-filling-maximized"' in runtime_source
    assert '"home_window_fullscreen"' in runtime_source
    assert "growthTrackGeometryPassed" in runtime_source
    assert '"home_progress_geometry"' in runtime_source
    for label in (
        "starter-deck-browser-home",
        "active-deck-browser-home-after-nurture",
        "session-summary-after-review",
    ):
        assert "home_progress_geometry" in REGISTRY[label].state_contract[
            "required_facts"
        ]


def test_move_mode_semantic_copy_facts_are_declared() -> None:
    required = set(REGISTRY["move-mode"].state_contract["required_facts"])

    assert {"move_bonsai_title", "move_swap_copy"}.issubset(required)


def test_capture_plan_keeps_checkpoint_domains_inside_one_session() -> None:
    requested = (
        "starter-garden-onboarding",
        "selected-plant-nurtured",
        "reviewer-reward-dock-bundle",
    )
    plan = build_capture_plan(REGISTRY, profile="representative", requested=requested)

    assert plan.requested == requested
    assert [name for name, _labels in plan.cohorts] == [
        "starter",
        "nurtured",
        "reviewer-transaction",
    ]
    assert tuple(label for _name, labels in plan.cohorts for label in labels) == requested


def test_selected_plant_capture_runs_matrix_without_expanding_registry() -> None:
    runtime_path = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    )
    source = runtime_path.read_text("utf-8")
    tree = ast.parse(source)
    matrix = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_audit_plant_popover_window_matrix"
    )
    matrix_source = ast.get_source_segment(source, matrix) or ""

    assert "((1_536, 1_024), (1_440, 900), (1_280, 800))" in matrix_source
    assert '"top-left"' in matrix_source
    assert '"top-right"' in matrix_source
    assert '"center"' in matrix_source
    assert '"bottom-left"' in matrix_source
    assert '"bottom-right"' in matrix_source
    assert "for toast_visible in (False, True)" in matrix_source
    assert "expected_case_count" in matrix_source
    assert len(REGISTRY.profile_labels("full")) == 34
    assert "selected-plant-nurtured" in REGISTRY.profile_labels("full")


@pytest.mark.parametrize(
    "telemetry_field",
    (
        "dpr_stroke_contracts",
        "root_and_container_overflow_passed",
        "reserved_scrollbar_area_passed",
        "fixed_regions_passed",
        "overflow_menu_containment_passed",
        "switch_visibility_passed",
        "settings_home_card_switch_visible",
        "reviewer_reserved_zones_passed",
    ),
)
def test_v25_runtime_emits_release_blocker_geometry_telemetry(
    telemetry_field: str,
) -> None:
    runtime_path = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    )
    assert f'"{telemetry_field}"' in runtime_path.read_text("utf-8")


@pytest.mark.release_evidence
def test_capture_renderer_dependency_map_is_closed_for_active_v25_surfaces() -> None:
    contract = json.loads(Path(capture_sequence.CAPTURE_CONTRACT_PATH).read_text())
    active_surfaces = [
        row for row in contract["surfaces"] if row.get("active")
    ]
    labels = [row["id"] for row in active_surfaces]
    renderer_families = {
        row["id"]: row["renderer_family"]
        for row in active_surfaces
    }
    dashboard_source = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "ui" / "dashboard.py"
    ).read_bytes()
    capture_source = (
        Path(capture_sequence.REPO_ROOT) / "ankigarden" / "capture" / "runtime.py"
    ).read_bytes()
    proof = _reconstruct_renderer_ownership_proof(
        capture_source=capture_source,
        dashboard_source=dashboard_source,
        labels=labels,
        renderer_families=renderer_families,
        production_archive_sha256="0" * 64,
    )

    assert "GardenDashboard" in proof["class_owners"]
    assert "NurseryDialog" in proof["class_owners"]


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
    local_id = "starter-garden-onboarding"
    checkpoint_id = "selected-plant-nurtured"
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
        "starter-garden-onboarding",
    ]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["process_count"] == 1
    assert planned["process_strategy"] == "single-session"
    assert planned["run_gate_process"] == "same-session-or-zero-surface-when-reused"
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
