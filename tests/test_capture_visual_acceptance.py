from __future__ import annotations

from copy import deepcopy

from scripts.validate_ui_capture import (
    growth_charge_rendered_value_issue_codes,
    reviewer_hud_acceptance_matrix_issue_codes,
    reviewer_reward_dock_issue_codes,
    streak_fold_geometry_issue_codes,
    visible_action_geometry_issue_codes,
    web_root_overflow_issue_codes,
)


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
        "hero_subtitle": "Juniper of the Moonlit Library Garden",
        "secondary_summary_count": 2,
        "hidden_reward_count": 2,
        "more_label": "2 more rewards ›",
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
        "visible_summary_labels": ["+40 growth", "2 discoveries"],
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
        "more_right_aligned": True,
        "more_click_height": 32,
        "more_visible_in_scroll_viewport": True,
        "more_footer_non_overlapping": True,
        "more_divider_clearance": 10,
        "compact_vertical_scroll_maximum": 0,
    }
    assert reviewer_reward_dock_issue_codes(bundle, geometry) == ()

    stacked_contract = {
        **bundle,
        "event_count": 4,
        "active_reveal_count": 3,
        "more_label": "+2 more rewards",
    }
    issues = reviewer_reward_dock_issue_codes(stacked_contract, geometry)
    assert "reviewer-reward-bundle-mismatch:event_count" in issues
    assert "reviewer-reward-bundle-mismatch:active_reveal_count" in issues
    assert "reviewer-reward-bundle-mismatch:more_label" in issues

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
        {"more_click_height": 31},
        {"more_visible_in_scroll_viewport": False},
        {"more_footer_non_overlapping": False},
        {"more_divider_clearance": 7},
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
            "displayed_progress_percent": 99,
            "visible_end_gap": True,
            "daily_completion_transition": {
                "before": {
                    "displayed_progress_percent": 99,
                    "heading": "Today’s cards",
                    "header_balance": 250,
                    "session_coins": 0,
                },
                "initial": {
                    "transition_active": True,
                    "completion_settling": True,
                    "displayed_progress_percent": 99,
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
                    "hero_title": "Checkpoint reached",
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
                "hero_title": "Checkpoint reached",
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
    for row in rows.values():
        assert isinstance(row, dict)
        row["passed"] = True
    rows["passed"] = True
    return rows


def test_reviewer_hud_release_matrix_rejects_end_gap_and_overflow_regressions() -> None:
    viewport = {
        "1600x1000-expanded": {"passed": True},
        "1280x800-expanded": {"passed": True},
        "1280x600-short-expanded": {"passed": True},
        "1280x800-collapsed": {"passed": True},
        "covered_requirements": [
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
        "1600x1000-expanded": {"passed": True},
        "1280x800-expanded": {"passed": True},
        "1280x600-short-expanded": {"passed": True},
        "1280x800-collapsed": {"passed": True},
        "covered_requirements": [
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
