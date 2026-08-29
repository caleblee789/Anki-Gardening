from __future__ import annotations

from copy import deepcopy

from ankigarden.ui.sync_reward_summary import sync_reward_summary_geometry
from scripts.validate_ui_capture import (
    growth_charge_rendered_value_issue_codes,
    reviewer_hud_acceptance_matrix_issue_codes,
    reviewer_reward_dock_issue_codes,
    streak_fold_geometry_issue_codes,
    visible_action_geometry_issue_codes,
    web_root_overflow_issue_codes,
)


def test_sync_reward_capture_geometry_is_centered_and_viewport_bounded() -> None:
    canonical = sync_reward_summary_geometry(1280, 720, 900)

    assert canonical == (412, 22, 456, 640)
    assert canonical[0] * 2 + canonical[2] == 1280
    assert canonical[1] == 22

    compact = sync_reward_summary_geometry(430, 300, 900)
    assert compact == (24, 22, 382, 252)
    assert compact[0] * 2 + compact[2] == 430
    assert compact[0] >= 0
    assert compact[1] + compact[3] <= 300


def test_web_root_overflow_requires_exact_document_measurement() -> None:
    evidence = {
        "source": "document.documentElement",
        "client_width": 667,
        "scroll_width": 667,
        "horizontal_overflow": 0,
        "passed": True,
    }
    assert web_root_overflow_issue_codes(evidence) == ()

    overflow = {**evidence, "scroll_width": 680, "horizontal_overflow": 13}
    assert "web-root-horizontal-overflow" in web_root_overflow_issue_codes(
        overflow
    )

    inconsistent = {**evidence, "horizontal_overflow": 4}
    assert (
        "web-root-overflow-arithmetic-mismatch"
        in web_root_overflow_issue_codes(inconsistent)
    )


def _action_visual() -> dict[str, object]:
    return {
        "visible_actions": [
            {
                "index": 0,
                "bounds": [20, 20, 80, 36],
                "clip_owner": "Garden dialog",
                "visible": True,
                "contained_in_dialog": True,
                "contained_in_owner": True,
                "pairwise_eligible": True,
            },
            {
                "index": 1,
                "bounds": [112, 20, 92, 36],
                "clip_owner": "Garden dialog",
                "visible": True,
                "contained_in_dialog": True,
                "contained_in_owner": True,
                "pairwise_eligible": True,
            },
        ],
        "visible_action_count": 2,
        "dialog_size": [500, 300],
        "visible_actions_contained": True,
        "visible_action_overlaps": [],
        "visible_actions_non_overlapping": True,
    }


def test_visible_action_geometry_recomputes_containment_and_overlap() -> None:
    valid = _action_visual()
    assert visible_action_geometry_issue_codes(valid) == ()

    outside = deepcopy(valid)
    outside["visible_actions"][0]["contained_in_owner"] = False
    outside["visible_actions_contained"] = False
    assert "visible-action-outside-container" in (
        visible_action_geometry_issue_codes(outside)
    )

    outside_dialog = deepcopy(valid)
    outside_dialog["visible_actions"][1]["bounds"] = [480, 20, 92, 36]
    outside_dialog["visible_actions"][1]["contained_in_dialog"] = False
    outside_dialog["visible_actions_contained"] = False
    assert "visible-action-outside-dialog-bounds" in (
        visible_action_geometry_issue_codes(outside_dialog)
    )

    overlapping = deepcopy(valid)
    overlapping["visible_actions"][1]["bounds"] = [90, 20, 92, 36]
    overlapping["visible_action_overlaps"] = [
        {"actions": [0, 1], "width": 10, "height": 36}
    ]
    overlapping["visible_actions_non_overlapping"] = False
    issues = visible_action_geometry_issue_codes(overlapping)
    assert "overlapping-visible-actions" in issues
    assert "visible-actions-overlap-not-passed" in issues


def _streak_fold() -> dict[str, object]:
    return {
        "scroll_name": "Anki Streak details",
        "at_initial_fold": True,
        "viewport_size": [892, 420],
        "configured_bottom_padding": 24,
        "measured_bottom_padding": 24,
        "detail_cards": [
            {
                "index": 0,
                "semantic_id": "",
                "bounds": [0, 280, 280, 96],
                "intersects_first_fold": True,
                "contained_in_first_fold": True,
            },
            {
                "index": 1,
                "semantic_id": "",
                "bounds": [292, 280, 280, 96],
                "intersects_first_fold": True,
                "contained_in_first_fold": True,
            },
            {
                "index": 2,
                "semantic_id": "",
                "bounds": [584, 280, 280, 96],
                "intersects_first_fold": True,
                "contained_in_first_fold": True,
            },
        ],
        "partial_detail_card_indexes": [],
        "passed": True,
    }


def test_streak_fold_rejects_partial_card_and_short_bottom_padding() -> None:
    assert streak_fold_geometry_issue_codes(_streak_fold()) == ()

    complete_fold_without_visible_detail_cards = _streak_fold()
    complete_fold_without_visible_detail_cards["detail_cards"] = []
    assert streak_fold_geometry_issue_codes(
        complete_fold_without_visible_detail_cards
    ) == ()

    partial = _streak_fold()
    partial["detail_cards"][2]["bounds"] = [584, 390, 280, 96]
    partial["detail_cards"][2]["contained_in_first_fold"] = False
    partial["partial_detail_card_indexes"] = [2]
    partial["passed"] = False
    assert "partially-visible-streak-detail-card" in (
        streak_fold_geometry_issue_codes(partial)
    )

    shallow = _streak_fold()
    shallow["configured_bottom_padding"] = 18
    shallow["measured_bottom_padding"] = 18
    shallow["passed"] = False
    issues = streak_fold_geometry_issue_codes(shallow)
    assert "insufficient-streak-configured-bottom-padding" in issues
    assert "insufficient-streak-measured-bottom-padding" in issues


def test_growth_charge_ready_and_success_require_rendered_carryover() -> None:
    ready = {
        "applicable": True,
        "variant": "ready",
        "growth_label": "Total Growth",
        "growth_value": "450 → 550",
        "inventory_label": "Charges remaining",
        "inventory_value": "2 → 1",
        "stage_badge": "Result: Sprout",
        "stage_badge_accessible": "New stage: Sprout",
        "stage_progress": "50 / 2,000 toward Young",
        "primary_action": "Use 1 charge",
        "current_growth": 450,
        "projected_growth": 550,
        "inventory_before": 2,
        "inventory_after": 1,
        "stage_carryover": 50,
        "next_stage_goal": 2_000,
        "passed": True,
    }
    assert growth_charge_rendered_value_issue_codes(
        "growth-charge-use-ready",
        ready,
    ) == ()
    stale_ready = {**ready, "stage_progress": "550 total Growth"}
    assert (
        "growth-charge-rendered-value-mismatch:stage_progress"
        in growth_charge_rendered_value_issue_codes(
            "growth-charge-use-ready",
            stale_ready,
        )
    )

    success = {
        "applicable": True,
        "variant": "success",
        "stage_transition": "Seed → Sprout",
        "receipt_copy": (
            "+100 Growth · 1 growth charge remaining\n"
            "Next-stage progress · 50 / 2,000 toward Young"
        ),
        "stage_reward_heading": "Stage reward",
        "reward_texts": ["Stage reward", "+2 Garden Coins"],
        "primary_action": "View plant",
        "secondary_action": "Close",
        "resulting_growth": 550,
        "stage_carryover": 50,
        "next_stage_goal": 2_000,
        "inventory_remaining": 1,
        "stage_reward_total": 2,
        "passed": True,
    }
    assert growth_charge_rendered_value_issue_codes(
        "growth-charge-success-stage-reward",
        success,
    ) == ()
    lost_carryover = {**success, "stage_carryover": 0}
    assert (
        "growth-charge-rendered-value-mismatch:stage_carryover"
        in growth_charge_rendered_value_issue_codes(
            "growth-charge-success-stage-reward",
            lost_carryover,
        )
    )


def test_reviewer_reward_dock_proves_one_seven_result_bundle_in_normal_flow() -> None:
    bundle = {
        "event_count": 7,
        "active_reveal_count": 1,
        "hero_count": 1,
        "eyebrow": "MILESTONE REACHED",
        "hero_title": "Full Bloom achieved",
        "projected_hero_subtitle": "Juniper of the Moonlit Library Garden",
        "hero_subtitle": "",
        "active_plant_identity_suppressed": True,
        "secondary_summary_count": 2,
        "details_action_copy": "Details ›",
        "details_action_heading_row": True,
        "obsolete_bottom_details_absent": True,
        "milestone_chevron_absent": True,
        "individual_close_button_count": 0,
        "detached_toast_count": 0,
        "session_footer_visible": True,
        "integrated_divider_visible": True,
        "same_commit_bundle": True,
        "presented_once": True,
        "stable_event_ids": True,
        "bundle_id": "answer:committed:1",
        "rendered_bundle_id": "answer:committed:1",
        "hero_event_id": "reward:full-bloom",
        "visible_summary_labels": ["1 Garden Find", "2 new discoveries"],
        "visible_summary_reward_types": [
            "garden_find",
            "environment_discovery",
        ],
        "visible_summary_artwork_refs": [
            "morning_dew",
            "firefly_lantern",
        ],
        "visible_summary_event_ids": [
            ["reward:find"],
            ["reward:environment-a", "reward:environment-b"],
        ],
        "passed": True,
    }
    geometry = {
        "passed": True,
        "dock_visible": True,
        "hud_reward_visible": True,
        "full_bloom_settled": True,
        "reward_bundle_id": "answer:committed:1",
        "contained_in_hud": True,
        "in_normal_flow": True,
        "overlaps_bottom_controls": False,
        "horizontal_scroll_maximum": 0,
        "reveal_height": 132,
        "footer_height": 52,
        "single_outer_surface": True,
        "divider_visible": True,
        "divider_count": 1,
        "hero_components_contained": True,
        "hero_components_non_overlapping": True,
        "title_details_non_overlapping": True,
        "details_heading_aligned": True,
        "details_click_height": 28,
        "details_visible_in_scroll_viewport": True,
        "details_footer_non_overlapping": True,
        "details_divider_clearance": 10,
        "obsolete_bottom_details_present": False,
        "obsolete_milestone_disclosure_present": False,
        "compact_vertical_scroll_maximum": 0,
    }
    assert reviewer_reward_dock_issue_codes(bundle, geometry) == ()

    stacked_contract = {
        **bundle,
        "event_count": 4,
        "active_reveal_count": 3,
        "details_action_copy": "View reward details ›",
    }
    issues = reviewer_reward_dock_issue_codes(stacked_contract, geometry)
    assert "reviewer-reward-bundle-mismatch:event_count" in issues
    assert "reviewer-reward-bundle-mismatch:active_reveal_count" in issues
    assert "reviewer-reward-bundle-mismatch:details_action_copy" in issues

    detached = {
        **geometry,
        "contained_in_hud": False,
        "in_normal_flow": False,
    }
    assert (
        "reviewer-reward-dock-geometry-mismatch"
        in reviewer_reward_dock_issue_codes(
            bundle,
            detached,
        )
    )

    wrong_bundle = {**geometry, "reward_bundle_id": "answer:committed:2"}
    assert (
        "reviewer-reward-dock-geometry-mismatch"
        in reviewer_reward_dock_issue_codes(bundle, wrong_bundle)
    )

    for regression in (
        {"full_bloom_settled": False},
        {"title_details_non_overlapping": False},
        {"details_click_height": 27},
        {"details_visible_in_scroll_viewport": False},
        {"details_footer_non_overlapping": False},
        {"details_divider_clearance": 7},
        {"obsolete_bottom_details_present": True},
        {"obsolete_milestone_disclosure_present": True},
        {"compact_vertical_scroll_maximum": 1},
    ):
        assert (
            "reviewer-reward-dock-geometry-mismatch"
            in reviewer_reward_dock_issue_codes(
                bundle,
                {**geometry, **regression},
            )
        )


def _reviewer_baseline_content() -> dict[str, object]:
    rows: dict[str, object] = {
        "18-cards-left": {
            "remaining_count": 18,
            "copy": "18 cards left",
        },
        "1-card-left": {
            "remaining_count": 1,
            "copy": "1 card left",
            "near_complete_card": True,
            "near_complete_detail": True,
            "displayed_progress_percent": 98.5,
            "progress_value": 985,
            "progress_maximum": 1_000,
            "minimum_unfilled_logical_pixels": 4,
            "estimated_unfilled_logical_pixels": 4,
            "progress_logical_width": 280,
            "visible_end_gap": True,
            "daily_completion_transition": {
                "before": {
                    "displayed_progress_percent": 98.5,
                    "heading": "Today’s cards",
                    "header_balance": 250,
                    "session_coins": 0,
                },
                "initial": {
                    "transition_active": True,
                    "completion_settling": True,
                    "displayed_progress_percent": 98.5,
                    "heading": "Today’s cards",
                    "coin_update_deferred": True,
                    "session_update_deferred": True,
                    "header_balance": 250,
                    "session_coins": 0,
                },
                "final": {
                    "transition_active": False,
                    "completion_status": "complete",
                    "heading": "All cards complete",
                    "reward_copy": "+10 coins",
                    "displayed_progress_percent": 100,
                    "header_balance": 260,
                    "session_coins": 10,
                    "session_metric_copy": ["+18 growth", "+10 coins"],
                },
                "passed": True,
            },
        },
        "no-session-rewards": {
            "dock_visible": False,
            "session_footer_visible": False,
        },
        "growth-only": {
            "metric_keys": ["growth"],
            "metric_copy": ["+18 growth"],
            "divider_visible": False,
            "routine_committed_answer_sequence": {
                "presented": True,
                "progress_before": 10,
                "session_before": 0,
                "session_update_deferred": True,
                "applied": {
                    "label": "Growth applied",
                    "value": "+18 growth",
                    "result_state": "applied",
                    "progress_percent": 10,
                    "art_pulse": True,
                    "session_growth_units": 0,
                },
                "settled": {
                    "progress_percent": 18,
                    "routine_feedback_active": False,
                    "session_growth_units": 1_800,
                    "session_metric_copy": ["+18 growth"],
                    "released_after_progress": True,
                },
                "restored": {
                    "label": "Next answer",
                    "value": "+18 growth",
                    "result_state": "projection",
                    "art_pulse": False,
                    "reward_visible": False,
                },
                "passed": True,
            },
        },
        "growth-and-coins": {
            "metric_keys": ["growth", "coins"],
            "metric_copy": ["+18 growth", "+2 coins"],
            "zero_categories_omitted": True,
        },
        "two-effects": {
            "visible_effect_count": 2,
            "overflow_visible": False,
            "effect_chip_bounds": [[0, 0, 130, 28], [136, 0, 130, 28]],
            "effect_label_bounds": [[20, 0, 100, 28], [20, 0, 100, 28]],
            "effect_chips_contained": True,
            "effect_labels_contained": True,
            "effect_labels_unclipped": True,
            "effect_art_passed": True,
            "effect_chip_overlap_pairs": [],
            "overflow_contained": True,
        },
        "three-plus-effects": {
            "visible_effect_count": 2,
            "overflow_visible": True,
            "overflow_text": "1 more effect ›",
            "overflow_right_aligned": True,
            "effect_chip_bounds": [[0, 0, 130, 28], [136, 0, 130, 28]],
            "effect_label_bounds": [[20, 0, 100, 28], [20, 0, 100, 28]],
            "effect_chips_contained": True,
            "effect_labels_contained": True,
            "effect_labels_unclipped": True,
            "effect_art_passed": True,
            "effect_chip_overlap_pairs": [],
            "overflow_contained": True,
        },
        "long-effects-one-column": {
            "visible_effect_count": 2,
            "overflow_visible": False,
            "single_column": True,
            "vertically_stacked": True,
            "effect_chip_bounds": [[0, 0, 266, 28], [0, 28, 266, 28]],
            "effect_label_bounds": [[20, 0, 236, 28], [20, 0, 236, 28]],
            "effect_chips_contained": True,
            "effect_labels_contained": True,
            "effect_labels_unclipped": True,
            "effect_art_passed": True,
            "effect_chip_overlap_pairs": [],
            "overflow_contained": True,
        },
        "short-plant-name": {
            "title": "Rose",
            "class_label": "Bonsai",
            "title_anchor_stable": True,
            "title_bounds": [10, 30, 280, 40],
            "art_bounds": [10, 70, 280, 146],
            "progress_bounds": [10, 216, 280, 18],
            "components_contained": True,
            "components_ordered": True,
            "declared_title_anchor_stable": True,
        },
        "two-line-plant-name": {
            "title_line_count": 2,
            "title_clamped": False,
            "class_label": "Bonsai",
            "title_anchor_stable": True,
            "title_bounds": [10, 30, 280, 40],
            "art_bounds": [10, 70, 280, 146],
            "progress_bounds": [10, 216, 280, 18],
            "short_title_bounds": [10, 30, 280, 40],
            "short_art_bounds": [10, 70, 280, 146],
            "short_progress_bounds": [10, 216, 280, 18],
            "components_contained": True,
            "components_ordered": True,
            "declared_title_anchor_stable": True,
            "title_position_stable": True,
            "art_position_stable": True,
            "progress_position_stable": True,
        },
        "checkpoint-crossing": {
            "crossed_checkpoints": [25],
            "marker_states": {
                "25": "completed",
                "50": "next",
                "75": "future",
                "100": "future",
            },
            "current_position_handle": False,
            "excess_progress_preserved": True,
            "post_commit_sequence": {
                "presented": True,
                "deferred_before_marker": {
                    "coin_update": True,
                    "session_update": True,
                    "header_balance": 248,
                    "session_growth_units": 0,
                },
                "marker_snapshot": {
                    "progress_percent": 25,
                    "reward_visible": False,
                    "header_balance": 248,
                },
                "reveal_snapshot": {
                    "progress_percent": 25,
                    "reward_visible": True,
                    "eyebrow": "CHECKPOINT REACHED",
                    "hero_title": "25% checkpoint",
                    "coin_copy": "+2 coins",
                    "header_balance": 248,
                },
                "sequence": [
                    "marker-reached",
                    "reward-revealed",
                    "excess-fill-complete",
                    "header-increment-settled",
                ],
                "expected_sequence": [
                    "marker-reached",
                    "reward-revealed",
                    "excess-fill-complete",
                    "header-increment-settled",
                ],
                "eyebrow": "CHECKPOINT REACHED",
                "hero_title": "25% checkpoint",
                "coin_copy": "+2 coins",
                "final_progress_percent": 38,
                "final_header_balance": 250,
                "final_session_metric_copy": ["+18 growth", "+2 coins"],
                "marker_before_reveal": True,
                "reward_before_excess_fill": True,
                "header_increment_deferred": True,
                "passed": True,
            },
        },
        "multiple-checkpoints-one-answer": {
            "crossed_checkpoints": [25, 50],
            "chronological": True,
            "final_progress_percent": 55,
            "next_checkpoint_percent": 75,
        },
        "stage-change": {
            "stage_changed": True,
            "celebration": "stage-change",
        },
        "coin-balance-248": {
            "exact_value": 248,
            "rendered_text": "248",
            "compacted": False,
            "header_anchors_stable": True,
        },
        "coin-balance-9999": {
            "exact_value": 9_999,
            "rendered_text": "9,999",
            "compacted": False,
            "header_anchors_stable": True,
        },
        "coin-balance-10013": {
            "exact_value": 10_013,
            "rendered_text": "10,013",
            "compacted": False,
            "header_anchors_stable": True,
            "large_balance_samples": [
                {
                    "exact_value": 999_999,
                    "rendered_text": "999,999",
                    "compacted": False,
                    "header_anchors_stable": True,
                    "passed": True,
                },
                {
                    "exact_value": 1_000_000,
                    "rendered_text": "1,000,000",
                    "compacted": False,
                    "header_anchors_stable": True,
                    "passed": True,
                },
            ],
        },
        "short-height": {
            "horizontal_scroll_maximum": 0,
            "vertical_scroll_maximum": 12,
            "overlaps_bottom_controls": False,
            "minimum_art_preserved": True,
            "major_reward_visible": True,
            "session_footer_visible": True,
            "integrated_divider_visible": True,
            "reward_dock_contained": True,
            "reward_reveal_contained": True,
            "reward_reveal_viewport_contained": True,
            "session_footer_contained": True,
            "reward_reveal_bounds": [10, 0, 300, 128],
            "divider_bounds": [10, 128, 300, 1],
            "session_footer_bounds": [10, 129, 300, 54],
            "reward_footer_non_overlapping": True,
            "divider_between_reward_and_footer": True,
            "sticky_header_and_dock": True,
            "session_metric_copy": ["+18 growth", "+2 coins"],
            "baseline_short_viewport_passed": True,
        },
    }
    header_anchors = [
        [12, 0, 104, 44],
        [142, 0, 170, 44],
        [274, 6, 32, 32],
    ]
    for state in (
        "coin-balance-248",
        "coin-balance-9999",
        "coin-balance-10013",
    ):
        row = rows[state]
        assert isinstance(row, dict)
        row.update({
            "header_anchors": header_anchors,
            "header_group_object_names": [
                "reviewerHudTitleGroup",
                "reviewerHudHeaderActions",
            ],
            "header_reserved_width": 170,
            "balance_cluster_contained": True,
        })
    progress_markers = {
        "25": "completed",
        "50": "next",
        "75": "future",
        "100": "future",
    }
    rows.update({
        "progress-10-percent": {
            "stage_percent_copy": "10%",
            "track_progress_percent": 10,
            "painted_progress_percent": 10,
            "marker_states": {
                "25": "next",
                "50": "future",
                "75": "future",
                "100": "future",
            },
            "current_position_handle": False,
        },
        "progress-38-percent": {
            "stage_percent_copy": "38%",
            "track_progress_percent": 38,
            "painted_progress_percent": 38,
            "marker_states": progress_markers,
            "current_position_handle": False,
        },
        "before-checkpoint": {
            "stage_percent_copy": "24%",
            "track_progress_percent": 24,
            "painted_progress_percent": 24,
            "marker_states": {
                "25": "next",
                "50": "future",
                "75": "future",
                "100": "future",
            },
            "current_position_handle": False,
        },
        "exact-checkpoint": {
            "stage_percent_copy": "25%",
            "track_progress_percent": 25,
            "painted_progress_percent": 25,
            "marker_states": progress_markers,
            "current_position_handle": False,
        },
        "checkpoint-marker-semantics": {
            "semantic_id": "reviewer.hud.checkpoint-track",
            "checkpoint_percents": [25, 50, 75, 100],
            "marker_states": progress_markers,
            "transparent_for_mouse": True,
            "focus_safe": True,
            "is_abstract_slider": False,
            "current_position_handle": False,
            "marker_shape": "diamond-tick",
            "future_marker_diameter": 4.5,
            "final_endpoint_inset": 2.5,
            "final_endpoint_inside_track": True,
            "checkpoint_reward_context": "Checkpoint reward",
        },
        "early-stage-art": {
            "stage_key": "sprout",
            "stage_copy": "Sprout · Stage 1 of 5",
            "art_path": "/capture/bonsai_sprout.webp",
            "pixmap_present": True,
            "pixmap_cache_key": 101,
            "ground_shadow_stage": "sprout",
            "art_region_height": 146,
            "plant_art_height": 136,
            "visible_plant_width": 48.0,
            "ground_shadow_width": 92.0,
            "distinct_from_other_stage": True,
        },
        "mature-stage-art": {
            "stage_key": "mature",
            "stage_copy": "Mature · Stage 3 of 5",
            "art_path": "/capture/bonsai_mature.webp",
            "pixmap_present": True,
            "pixmap_cache_key": 202,
            "ground_shadow_stage": "mature",
            "art_region_height": 146,
            "plant_art_height": 136,
            "distinct_from_other_stage": True,
        },
        "zero-effects": {
            "visible_effect_count": 0,
            "overflow_visible": False,
            "effect_chip_bounds": [],
            "effect_label_bounds": [],
            "effect_chips_contained": True,
            "effect_labels_contained": True,
            "effect_labels_unclipped": True,
            "effect_art_passed": True,
            "effect_chip_overlap_pairs": [],
            "overflow_contained": True,
        },
        "one-effect": {
            "visible_effect_count": 1,
            "overflow_visible": False,
            "effect_chip_bounds": [[0, 0, 266, 28]],
            "effect_label_bounds": [[20, 0, 236, 28]],
            "effect_chips_contained": True,
            "effect_labels_contained": True,
            "effect_labels_unclipped": True,
            "effect_art_passed": True,
            "effect_chip_overlap_pairs": [],
            "overflow_contained": True,
        },
        "estimate-1-card": {
            "estimated_cards": 1,
            "rendered_text": "~1 card",
            "contained": True,
            "text_fits": True,
            "uses_cards_copy": True,
        },
        "estimate-14-cards": {
            "estimated_cards": 14,
            "rendered_text": "~14 cards",
            "contained": True,
            "text_fits": True,
            "uses_cards_copy": True,
        },
        "estimate-1240-cards": {
            "estimated_cards": 1_240,
            "rendered_text": "~1,240 cards",
            "contained": True,
            "text_fits": True,
            "uses_cards_copy": True,
        },
        "coin-balance-999999": {
            "exact_value": 999_999,
            "rendered_text": "999,999",
            "compacted": False,
            "header_anchors": header_anchors,
            "header_anchors_stable": True,
            "header_group_object_names": [
                "reviewerHudTitleGroup",
                "reviewerHudHeaderActions",
            ],
            "header_reserved_width": 170,
            "balance_cluster_contained": True,
        },
        "coin-balance-1000000": {
            "exact_value": 1_000_000,
            "rendered_text": "1,000,000",
            "compacted": False,
            "header_anchors": header_anchors,
            "header_anchors_stable": True,
            "header_group_object_names": [
                "reviewerHudTitleGroup",
                "reviewerHudHeaderActions",
            ],
            "header_reserved_width": 170,
            "balance_cluster_contained": True,
        },
        "header-stable-grouping": {
            "balance_states": [
                "coin-balance-248",
                "coin-balance-9999",
                "coin-balance-10013",
                "coin-balance-999999",
                "coin-balance-1000000",
            ],
            "object_names": [
                "reviewerHudTitleGroup",
                "reviewerHudHeaderActions",
            ],
            "reserved_width": 170,
            "anchor_snapshots": [header_anchors] * 5,
        },
    })
    for row in rows.values():
        assert isinstance(row, dict)
        if "marker_states" in row:
            row.setdefault("marker_shape", "diamond-tick")
        row["passed"] = True
    rows["passed"] = True
    return rows


def _reviewer_reward_content() -> dict[str, object]:
    settled_copy = "Future growth will be shared or stored."
    expected_detail_rows = [
        {
            "category": category,
            "name": name,
            "value": value,
            "event_ids": [event_id],
        }
        for category, name, value, event_id in (
            ("Milestone", "Full Bloom achieved", "+14 coins", "event:1"),
            ("Growth applied", "Plant Growth", "+40 growth", "event:2"),
            ("Garden Coins", "Garden Coins", "+14 coins", "event:3"),
            ("Discovery", "Firefly Evening", "New", "event:4"),
            ("Discovery", "Morning Dew", "New", "event:5"),
            ("Garden Find", "Moonlit Seed", "Common", "event:6"),
            ("Additional effect", "Fertilizer", "1h 24m", "event:7"),
        )
    ]
    visible_detail_rows = [
        {
            **row,
            "category_visible_text": row["category"],
            "name_visible_text": row["name"],
        }
        for row in expected_detail_rows
    ]
    rows: dict[str, object] = {
        "all-cards-complete": {
            "completion_status": "complete",
            "heading": "All cards complete",
            "displayed_progress_percent": 100,
            "reward_copy": "+10 coins",
        },
        "one-garden-find": {"find_count": 1, "footer_copy": "1 find"},
        "discovery-new-wording": {
            "visible_summary_labels": ["1 Garden Find", "2 new discoveries"],
            "discovery_summary": "2 new discoveries",
        },
        "full-bloom": {
            "eyebrow": "MILESTONE REACHED",
            "hero_title": "Full Bloom achieved",
            "hero_subtitle": "",
            "active_plant_identity_suppressed": True,
            "class_label": "Bonsai",
            "bed_visible": False,
            "settled": True,
            "temporary_gold_cleared": True,
            "settled_copy": settled_copy,
            "select_another_visible": True,
            "select_another_copy": "Choose next plant ›",
            "art_scale": 1.0,
            "particles_active": False,
        },
        "full-bloom-celebration": {
            "celebration": "full-bloom",
            "settled": False,
            "temporary_gold_visible": True,
            "motion_animation_active": True,
            "art_scale": 1.04,
            "particles_active": True,
            "select_another_visible": False,
        },
        "full-bloom-settled": {
            "settled": True,
            "temporary_gold_cleared": True,
            "settled_copy": settled_copy,
            "select_another_visible": True,
            "select_another_copy": "Choose next plant ›",
            "art_scale": 1.0,
            "particles_active": False,
        },
        "full-bloom-details": {
            "details_expanded": True,
            "all_secondary_items_present": True,
            "details_action_copy": "Hide details",
            "maximum_height": 16_777_215,
            "detail_row_count": 7,
            "visible_detail_rows": visible_detail_rows,
            "expected_detail_rows": expected_detail_rows,
            "visible_detail_rows_match": True,
            "detail_event_ids_reconciled": True,
            "detail_panel_visible": True,
            "reveal_state": "details_open",
            "vertical_scroll_maximum": 96,
        },
        "full-bloom-several-secondary": {
            "hero_subtitle": "",
            "active_plant_identity_suppressed": True,
            "visible_summary_count": 2,
            "visible_summary_labels": ["1 Garden Find", "2 new discoveries"],
            "visible_summary_rows": [
                {
                    "label": "1 Garden Find",
                    "reward_type": "garden_find",
                    "artwork_ref": "morning_dew",
                    "uses_item_art": True,
                    "icon_present": True,
                    "icon_kind": "item-art",
                },
                {
                    "label": "2 new discoveries",
                    "reward_type": "environment_discovery",
                    "artwork_ref": "firefly_lantern",
                    "uses_item_art": False,
                    "icon_present": True,
                    "icon_kind": "environment-discovery",
                },
            ],
            "details_action_copy": "Details ›",
            "details_click_height": 28,
            "details_heading_aligned": True,
            "reveal_height": 140,
            "title_details_non_overlapping": True,
            "detail_event_ids_reconciled": True,
            "obsolete_bottom_details_present": False,
            "obsolete_milestone_disclosure_present": False,
            "milestone_medallion": True,
            "medallion_pixmap_present": True,
            "reveal_state": "celebrating",
        },
        "reward-details-action-copy": {
            "collapsed_action_copy": "Details ›",
            "minimum_click_height": 28,
            "event_ids_reconciled": True,
            "heading_row_action": True,
            "obsolete_bottom_action_absent": True,
            "milestone_chevron_absent": True,
        },
        "settled-height-or-safe-scroll": {
            "safe_area_passed": True,
            "horizontal_scroll_maximum": 0,
            "height_at_most_660": True,
            "safe_scroll": False,
        },
        "full-bloom-short-height": {
            "requested_host_size": [1_280, 600],
            "host_size": [1_280, 600],
            "host_shortened": True,
            "hud_height": 476,
            "hud_safe_area_passed": True,
            "horizontal_scroll_maximum": 0,
            "middle_vertical_scroll_maximum": 44,
            "middle_content_fits": False,
            "middle_scroll_owns_overflow": True,
            "major_reward_visible": True,
            "session_footer_visible": True,
            "fixed_header_visible": True,
            "fixed_header_outside_middle_scroll": True,
            "fixed_session_footer_outside_middle_scroll": True,
            "fixed_regions_non_overlapping": True,
            "sticky_reward_and_footer": True,
            "reward_footer_non_overlapping": True,
            "reveal_height": 145,
            "canonical_viewport_restored": True,
        },
        "session-footer-reconciliation": {
            "bundle_id": "answer:committed:1",
            "history_bundle_ids": ["answer:committed:1"],
            "footer_growth_units": 4_000,
            "live_growth_units": 4_000,
            "footer_coins": 14,
            "live_coins": 14,
            "footer_finds": 1,
            "live_finds": 1,
            "footer_copy": ["+40 growth", "+14 coins", "1 find"],
        },
        "reward-reveal-lifecycle": {
            "celebrating": "celebrating",
            "details_open": "details_open",
            "settled": "settled",
            "archived": "archived",
            "details_paused_archive": True,
        },
        "session-history-named-growth": {
            "meaningful_names": [
                "Full Bloom achieved",
                "Mature reached",
                "75% checkpoint",
                "Morning Dew",
                "Firefly Lantern",
                "Verdant Twilight",
                "Booster extended",
            ],
            "routine_row_count": 1,
            "routine_name": "Growth applied",
            "routine_value": "+6 Growth",
            "routine_event_ids": ["capture-routine-growth-next-commit"],
            "routine_line": "Growth applied · +6 Growth",
            "routine_non_clickable": True,
        },
    }
    for row in rows.values():
        assert isinstance(row, dict)
        row["passed"] = True
    rows["passed"] = True
    return rows


def _reviewer_reward_interactions() -> dict[str, object]:
    rows: dict[str, object] = {
        name: {"passed": True}
        for name in (
            "collapsed-unseen-reward",
            "overflow-expanded",
            "rapid-successive-rewards",
            "collection-sync-hud-open",
            "reviewer-reload-after-reward",
            "history-remount-idempotence",
            "history-reopen",
        )
    }
    rows["details-pause-archive"] = {
        "routine_commit_accepted": True,
        "state_before_commit": "details_open",
        "state_after_commit": "details_open",
        "details_remained_open": True,
        "next_commit_seen": True,
        "reward_remained_visible": True,
        "active_bundle_preserved": True,
        "history_advanced_once": True,
        "passed": True,
    }
    rows["archive-after-next-commit"] = {
        "reveal_state": "archived",
        "details_expanded": False,
        "reward_visible": False,
        "active_reward_cleared": True,
        "history_count": 2,
        "passed": True,
    }
    rows["no-replay"] = {
        "duplicate_call_idempotently_accepted": True,
        "history_count_before": 3,
        "history_count_after": 3,
        "queue_count_before": 0,
        "queue_count_after": 0,
        "reveal_visible_before": True,
        "reveal_visible_after": True,
        "rendered_bundle_before": "answer:committed:1",
        "rendered_bundle_after": "answer:committed:1",
        "seen_id_preserved": True,
        "sync_state_preserved": True,
        "resize_reposition_preserved": True,
        "details_round_trip_preserved": True,
        "duplicate_projection_accepted": True,
        "projection_update_exercised": True,
        "next_card_projection_preserved": True,
        "passed": True,
    }
    rows["passed"] = True
    return rows


def test_reviewer_reward_matrix_rejects_copy_disclosure_and_replay_regressions() -> None:
    content = _reviewer_reward_content()
    interactions = _reviewer_reward_interactions()
    assert reviewer_hud_acceptance_matrix_issue_codes(
        "reviewer-reward-dock-bundle",
        None,
        content,
        interactions=interactions,
    ) == ()

    old_discovery_copy = deepcopy(content)
    old_discovery_copy["discovery-new-wording"]["discovery_summary"] = (
        "2 discoveries"
    )
    assert (
        "reviewer-hud-content-semantic-mismatch:discovery-new-wording"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            old_discovery_copy,
            interactions=interactions,
        )
    )

    missing_detail_identity = deepcopy(content)
    missing_detail_identity["full-bloom-details"][
        "detail_event_ids_reconciled"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-details"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            missing_detail_identity,
            interactions=interactions,
        )
    )

    hidden_detail_copy_only = deepcopy(content)
    hidden_detail_copy_only["full-bloom-details"]["visible_detail_rows"][0][
        "category_visible_text"
    ] = ""
    hidden_detail_copy_only["full-bloom-details"][
        "visible_detail_rows_match"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-details"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            hidden_detail_copy_only,
            interactions=interactions,
        )
    )

    repeated_active_identity = deepcopy(content)
    repeated_active_identity["full-bloom"]["hero_subtitle"] = (
        "Juniper of the Moonlit Library Garden"
    )
    repeated_active_identity["full-bloom"][
        "active_plant_identity_suppressed"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            repeated_active_identity,
            interactions=interactions,
        )
    )

    undersized_compact_reveal = deepcopy(content)
    undersized_compact_reveal["full-bloom-several-secondary"][
        "reveal_height"
    ] = 129
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-several-secondary"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            undersized_compact_reveal,
            interactions=interactions,
        )
    )

    undersized_disclosure = deepcopy(content)
    undersized_disclosure["full-bloom-several-secondary"][
        "details_click_height"
    ] = 27
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-several-secondary"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            undersized_disclosure,
            interactions=interactions,
        )
    )

    unsafe_short_full_bloom = deepcopy(content)
    unsafe_short_full_bloom["full-bloom-short-height"][
        "session_footer_visible"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-short-height"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            unsafe_short_full_bloom,
            interactions=interactions,
        )
    )

    stale_settled_copy = deepcopy(content)
    stale_settled_copy["full-bloom-settled"]["settled_copy"] = (
        "Future growth will be shared or stored until you select another plant."
    )
    assert (
        "reviewer-hud-content-semantic-mismatch:full-bloom-settled"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            stale_settled_copy,
            interactions=interactions,
        )
    )

    replayed = deepcopy(interactions)
    replayed["no-replay"]["history_count_after"] = 4
    assert (
        "reviewer-reward-interaction-semantic-mismatch:no-replay"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            content,
            interactions=replayed,
        )
    )

    resized_replay = deepcopy(interactions)
    resized_replay["no-replay"]["resize_reposition_preserved"] = False
    assert (
        "reviewer-reward-interaction-semantic-mismatch:no-replay"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-reward-dock-bundle",
            None,
            content,
            interactions=resized_replay,
        )
    )


def test_reviewer_hud_release_matrix_rejects_end_gap_and_overflow_regressions() -> None:
    viewport = {
        "1710x1041-expanded": {"passed": True},
        "1600x1000-expanded": {"passed": True},
        "1280x800-expanded": {"passed": True},
        "1280x600-short-expanded": {"passed": True},
        "1280x800-collapsed": {"passed": True},
        "covered_requirements": [
            "1710x1041",
            "1600x1000",
            "1280x800",
            "short-height",
            "expanded",
            "collapsed",
        ],
        "passed": True,
    }
    resilience = {
        "no-active-plant": {"passed": True},
        "stored-growth": {"passed": True},
        "passed": True,
    }
    content = _reviewer_baseline_content()

    assert reviewer_hud_acceptance_matrix_issue_codes(
        "reviewer-hud-expanded",
        viewport,
        content,
        resilience=resilience,
    ) == ()

    no_gap = deepcopy(content)
    no_gap["1-card-left"]["displayed_progress_percent"] = 100
    no_gap["1-card-left"]["visible_end_gap"] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:1-card-left"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            no_gap,
            resilience=resilience,
        )
    )

    inaccurate_one_left = deepcopy(content)
    inaccurate_one_left["1-card-left"]["progress_value"] = 990
    assert (
        "reviewer-hud-content-semantic-mismatch:1-card-left"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            inaccurate_one_left,
            resilience=resilience,
        )
    )

    too_small_one_left_gap = deepcopy(content)
    too_small_one_left_gap["1-card-left"][
        "minimum_unfilled_logical_pixels"
    ] = 3
    too_small_one_left_gap["1-card-left"][
        "estimated_unfilled_logical_pixels"
    ] = 3
    assert (
        "reviewer-hud-content-semantic-mismatch:1-card-left"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            too_small_one_left_gap,
            resilience=resilience,
        )
    )

    missing_near_complete_emphasis = deepcopy(content)
    missing_near_complete_emphasis["1-card-left"][
        "near_complete_detail"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:1-card-left"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            missing_near_complete_emphasis,
            resilience=resilience,
        )
    )

    slider_like_markers = deepcopy(content)
    slider_like_markers["checkpoint-marker-semantics"]["marker_shape"] = (
        "hollow-circle"
    )
    assert (
        "reviewer-hud-content-semantic-mismatch:checkpoint-marker-semantics"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            slider_like_markers,
            resilience=resilience,
        )
    )

    oversized_future_dots = deepcopy(content)
    oversized_future_dots["checkpoint-marker-semantics"][
        "future_marker_diameter"
    ] = 5.0
    assert (
        "reviewer-hud-content-semantic-mismatch:checkpoint-marker-semantics"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            oversized_future_dots,
            resilience=resilience,
        )
    )

    undersized_sprout = deepcopy(content)
    undersized_sprout["early-stage-art"]["visible_plant_width"] = 44.0
    assert (
        "reviewer-hud-content-semantic-mismatch:early-stage-art"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            undersized_sprout,
            resilience=resilience,
        )
    )

    long_effects_not_stacked = deepcopy(content)
    long_effects_not_stacked["long-effects-one-column"][
        "single_column"
    ] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:long-effects-one-column"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            long_effects_not_stacked,
            resilience=resilience,
        )
    )

    left_overflow = deepcopy(content)
    left_overflow["three-plus-effects"]["overflow_right_aligned"] = False
    assert (
        "reviewer-hud-content-semantic-mismatch:three-plus-effects"
        in reviewer_hud_acceptance_matrix_issue_codes(
            "reviewer-hud-expanded",
            viewport,
            left_overflow,
            resilience=resilience,
        )
    )


def test_reviewer_hud_release_matrix_rejects_each_measured_sequence_regression() -> None:
    viewport = {
        "1710x1041-expanded": {"passed": True},
        "1600x1000-expanded": {"passed": True},
        "1280x800-expanded": {"passed": True},
        "1280x600-short-expanded": {"passed": True},
        "1280x800-collapsed": {"passed": True},
        "covered_requirements": [
            "1710x1041",
            "1600x1000",
            "1280x800",
            "short-height",
            "expanded",
            "collapsed",
        ],
        "passed": True,
    }
    resilience = {
        "no-active-plant": {"passed": True},
        "stored-growth": {"passed": True},
        "passed": True,
    }

    def set_path(row: dict[str, object], path: tuple[object, ...], value: object) -> None:
        target: object = row
        for key in path[:-1]:
            if isinstance(key, int):
                assert isinstance(target, list)
            else:
                assert isinstance(target, dict)
            target = target[key]
        final_key = path[-1]
        if isinstance(final_key, int):
            assert isinstance(target, list)
        else:
            assert isinstance(target, dict)
        target[final_key] = value

    regressions: tuple[tuple[str, tuple[object, ...], object], ...] = (
        # Effect chips and their labels must have valid measured bounds, stay
        # contained, not overlap, and render their full unelided copy.
        ("two-effects", ("effect_chip_bounds", 0, 2), 0),
        ("two-effects", ("effect_label_bounds", 0, 2), 0),
        ("two-effects", ("effect_chips_contained",), False),
        ("two-effects", ("effect_labels_contained",), False),
        ("two-effects", ("effect_labels_unclipped",), False),
        ("two-effects", ("effect_chip_overlap_pairs",), [[0, 1]]),
        ("two-effects", ("overflow_contained",), False),
        ("three-plus-effects", ("overflow_contained",), False),
        # Title stability is based on actual title/art/progress geometry, not a
        # widget property that could remain true while the layout moves.
        ("short-plant-name", ("title_bounds", 2), 0),
        ("short-plant-name", ("art_bounds", 2), 0),
        ("short-plant-name", ("progress_bounds", 2), 0),
        ("short-plant-name", ("components_contained",), False),
        ("short-plant-name", ("components_ordered",), False),
        ("short-plant-name", ("declared_title_anchor_stable",), False),
        ("short-plant-name", ("title_anchor_stable",), False),
        ("two-line-plant-name", ("short_title_bounds", 2), 0),
        ("two-line-plant-name", ("short_art_bounds", 2), 0),
        ("two-line-plant-name", ("short_progress_bounds", 2), 0),
        ("two-line-plant-name", ("title_position_stable",), False),
        ("two-line-plant-name", ("art_position_stable",), False),
        ("two-line-plant-name", ("progress_position_stable",), False),
        ("two-line-plant-name", ("title_bounds", 0), 11),
        ("two-line-plant-name", ("art_bounds", 0), 11),
        ("two-line-plant-name", ("progress_bounds", 0), 11),
        # Checkpoint reward copy, marker/reveal/excess-fill ordering, and both
        # deferred session/header commits are all release requirements.
        ("checkpoint-crossing", ("post_commit_sequence", "passed"), False),
        ("checkpoint-crossing", ("post_commit_sequence", "presented"), False),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "deferred_before_marker", "coin_update"),
            False,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "deferred_before_marker", "session_update"),
            False,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "deferred_before_marker", "header_balance"),
            249,
        ),
        (
            "checkpoint-crossing",
            (
                "post_commit_sequence",
                "deferred_before_marker",
                "session_growth_units",
            ),
            1_800,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "marker_snapshot", "progress_percent"),
            24,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "marker_snapshot", "reward_visible"),
            True,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "marker_snapshot", "header_balance"),
            250,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "progress_percent"),
            38,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "reward_visible"),
            False,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "eyebrow"),
            "MILESTONE REACHED",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "hero_title"),
            "Milestone reached",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "coin_copy"),
            "+1 coin",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reveal_snapshot", "header_balance"),
            250,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "sequence"),
            [
                "marker-reached",
                "reward-revealed",
                "header-increment-settled",
                "excess-fill-complete",
            ],
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "expected_sequence"),
            [
                "marker-reached",
                "excess-fill-complete",
                "reward-revealed",
                "header-increment-settled",
            ],
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "eyebrow"),
            "MILESTONE REACHED",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "hero_title"),
            "Milestone reached",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "coin_copy"),
            "+1 coin",
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "final_progress_percent"),
            25,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "final_header_balance"),
            248,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "final_session_metric_copy"),
            ["+18 growth"],
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "marker_before_reveal"),
            False,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "reward_before_excess_fill"),
            False,
        ),
        (
            "checkpoint-crossing",
            ("post_commit_sequence", "header_increment_deferred"),
            False,
        ),
        # Routine answers must show applied feedback, then commit progress and
        # session growth, then restore the projected next-answer state.
        ("growth-only", ("routine_committed_answer_sequence", "passed"), False),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "presented"),
            False,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "progress_before"),
            11,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "session_before"),
            1_800,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "session_update_deferred"),
            False,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "applied", "label"),
            "Next answer",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "applied", "value"),
            "+10 growth",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "applied", "result_state"),
            "projection",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "applied", "progress_percent"),
            18,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "applied", "art_pulse"),
            False,
        ),
        (
            "growth-only",
            (
                "routine_committed_answer_sequence",
                "applied",
                "session_growth_units",
            ),
            1_800,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "settled", "progress_percent"),
            10,
        ),
        (
            "growth-only",
            (
                "routine_committed_answer_sequence",
                "settled",
                "routine_feedback_active",
            ),
            True,
        ),
        (
            "growth-only",
            (
                "routine_committed_answer_sequence",
                "settled",
                "session_growth_units",
            ),
            0,
        ),
        (
            "growth-only",
            (
                "routine_committed_answer_sequence",
                "settled",
                "session_metric_copy",
            ),
            [],
        ),
        (
            "growth-only",
            (
                "routine_committed_answer_sequence",
                "settled",
                "released_after_progress",
            ),
            False,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "restored", "label"),
            "Growth applied",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "restored", "value"),
            "+10 growth",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "restored", "result_state"),
            "applied",
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "restored", "art_pulse"),
            True,
        ),
        (
            "growth-only",
            ("routine_committed_answer_sequence", "restored", "reward_visible"),
            True,
        ),
        # Daily completion must keep the old copy/balance/session during the
        # transition, then atomically settle the complete state.
        (
            "1-card-left",
            ("daily_completion_transition", "passed"),
            False,
        ),
        (
            "1-card-left",
            (
                "daily_completion_transition",
                "before",
                "displayed_progress_percent",
            ),
            100,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "before", "heading"),
            "All cards complete",
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "before", "header_balance"),
            260,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "before", "session_coins"),
            10,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "initial", "transition_active"),
            False,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "initial", "completion_settling"),
            False,
        ),
        (
            "1-card-left",
            (
                "daily_completion_transition",
                "initial",
                "displayed_progress_percent",
            ),
            100,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "initial", "heading"),
            "All cards complete",
        ),
        (
            "1-card-left",
            (
                "daily_completion_transition",
                "initial",
                "coin_update_deferred",
            ),
            False,
        ),
        (
            "1-card-left",
            (
                "daily_completion_transition",
                "initial",
                "session_update_deferred",
            ),
            False,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "initial", "header_balance"),
            260,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "initial", "session_coins"),
            10,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "transition_active"),
            True,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "completion_status"),
            "in-progress",
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "heading"),
            "Today’s cards",
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "reward_copy"),
            "+9 coins",
        ),
        (
            "1-card-left",
            (
                "daily_completion_transition",
                "final",
                "displayed_progress_percent",
            ),
            99,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "header_balance"),
            250,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "session_coins"),
            0,
        ),
        (
            "1-card-left",
            ("daily_completion_transition", "final", "session_metric_copy"),
            ["+18 growth"],
        ),
        # Short-height major reward and pre-existing footer must coexist inside
        # the dock while the body owns any necessary vertical scrolling.
        ("short-height", ("major_reward_visible",), False),
        ("short-height", ("session_footer_visible",), False),
        ("short-height", ("integrated_divider_visible",), False),
        ("short-height", ("reward_dock_contained",), False),
        ("short-height", ("reward_reveal_contained",), False),
        ("short-height", ("reward_reveal_viewport_contained",), False),
        ("short-height", ("session_footer_contained",), False),
        ("short-height", ("reward_reveal_bounds", 2), 0),
        ("short-height", ("divider_bounds", 2), 0),
        ("short-height", ("session_footer_bounds", 2), 0),
        ("short-height", ("reward_reveal_bounds", 3), 130),
        ("short-height", ("divider_bounds", 1), 127),
        ("short-height", ("session_footer_bounds", 1), 128),
        ("short-height", ("reward_footer_non_overlapping",), False),
        ("short-height", ("divider_between_reward_and_footer",), False),
        ("short-height", ("sticky_header_and_dock",), False),
        ("short-height", ("session_metric_copy",), ["+18 growth"]),
        ("short-height", ("baseline_short_viewport_passed",), False),
    )

    for state, path, bad_value in regressions:
        broken = _reviewer_baseline_content()
        row = broken[state]
        assert isinstance(row, dict)
        set_path(row, path, bad_value)
        assert (
            f"reviewer-hud-content-semantic-mismatch:{state}"
            in reviewer_hud_acceptance_matrix_issue_codes(
                "reviewer-hud-expanded",
                viewport,
                broken,
                resilience=resilience,
            )
        ), (state, path)
