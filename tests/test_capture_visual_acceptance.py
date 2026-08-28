from __future__ import annotations

from copy import deepcopy

from scripts.validate_ui_capture import (
    growth_charge_rendered_value_issue_codes,
    reviewer_stack_issue_codes,
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
        "stage_badge": "Sprout",
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
        "reward_texts": ["Stage reward", "+5 Garden Coins"],
        "primary_action": "View plant",
        "secondary_action": "Close",
        "resulting_growth": 550,
        "stage_carryover": 50,
        "next_stage_goal": 2_000,
        "inventory_remaining": 1,
        "stage_reward_total": 5,
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


def test_reviewer_stack_proves_six_events_newest_plus_summary_at_292px() -> None:
    stack = {
        "requested_event_count": 6,
        "visible_toast_count": 2,
        "summary_toast_count": 1,
        "regular_toast_count": 1,
        "summary_copy": "+5 more rewards ›",
        "newest_expected_title": "Garden Find",
        "newest_expected_message": "A Small Growth Charge was added.",
        "newest_visible_title": "Garden Find",
        "newest_visible_message": "A Small Growth Charge was added.",
        "newest_event_visible": True,
        "passed": True,
    }
    geometry = {
        "passed": True,
        "width": 292,
        "expected_width": 292,
        "width_exact": True,
    }
    geometries = [deepcopy(geometry), deepcopy(geometry)]
    assert reviewer_stack_issue_codes(stack, geometries) == ()

    old_contract = {
        **stack,
        "requested_event_count": 4,
        "visible_toast_count": 3,
        "summary_copy": "+2 more rewards",
    }
    issues = reviewer_stack_issue_codes(old_contract, geometries)
    assert "reviewer-stack-mismatch:requested_event_count" in issues
    assert "reviewer-stack-mismatch:visible_toast_count" in issues
    assert "reviewer-stack-mismatch:summary_copy" in issues

    wide = [deepcopy(geometry), {**geometry, "width": 300}]
    assert "reviewer-stack-geometry-mismatch" in reviewer_stack_issue_codes(
        stack,
        wide,
    )
