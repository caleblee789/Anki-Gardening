from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DIALOG_VIEW_HEIGHT_PROFILES,
    DIALOG_VIEW_POLICIES,
    DialogCloseBlocker,
    DialogClosePolicy,
    DialogCloseReason,
    DialogCaptureTelemetryRecord,
    DialogGeometryTelemetryRecord,
    DialogSizeClass,
    DialogSizeProfile,
    DialogWindowMode,
    DialogViewState,
    InitialFocusPolicy,
    ScrollbarTelemetryRecord,
    dialog_height_profile,
    dialog_window_mode,
    dialog_view_policy,
    content_fit_geometry_limited,
    merge_content_fit_preservation,
    resolve_dialog_close,
    resolved_dialog_size,
    resolved_dialog_view_width,
    should_preserve_transition_height,
    text_column_width,
)


def test_every_dialog_size_class_has_a_sane_policy() -> None:
    assert set(DIALOG_SIZE_POLICIES) == set(DialogSizeClass)
    for policy in DIALOG_SIZE_POLICIES.values():
        assert 0 < policy.min_width <= policy.preferred_width <= policy.max_width
        assert 0 < policy.min_height <= policy.preferred_height <= policy.max_height
        assert 0 < policy.width_ratio <= 1
        assert 0 < policy.height_ratio <= 1
        assert isinstance(policy, DialogSizeProfile)
        assert isinstance(policy.window_mode, DialogWindowMode)


def test_dialog_families_declare_one_first_class_native_window_mode() -> None:
    assert dialog_window_mode(DialogSizeClass.GARDEN_WORKSPACE) is DialogWindowMode.CANVAS
    assert dialog_window_mode(DialogSizeClass.TRANSACTION) is DialogWindowMode.CONTENT
    assert dialog_window_mode(DialogSizeClass.COMPACT_STATUS) is DialogWindowMode.CONTENT
    assert dialog_window_mode(DialogSizeClass.GROWTH_CHARGE) is DialogWindowMode.CONTENT

    workspace_families = {
        DialogSizeClass.FERTILIZER,
        DialogSizeClass.SETTINGS,
        DialogSizeClass.NURSERY,
        DialogSizeClass.PROGRESS,
        DialogSizeClass.LOADOUT,
        DialogSizeClass.PLANT_STORY,
        DialogSizeClass.SPECIES_DETAIL,
        DialogSizeClass.STANDARD_TEXT,
        DialogSizeClass.CATALOG,
        DialogSizeClass.PREVIEW,
    }
    assert all(
        dialog_window_mode(family) is DialogWindowMode.WORKSPACE
        for family in workspace_families
    )


def test_compact_confirmation_does_not_expand_with_a_large_screen() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPACT_CONFIRMATION,
        2560,
        1440,
    ) == (500, 200)


def test_comparison_dialog_grows_for_cards_without_becoming_screen_sized() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPARISON,
        2560,
        1440,
    ) == (540, 250)


def test_preview_dialog_uses_large_screen_without_exceeding_policy() -> None:
    width, height = resolved_dialog_size(DialogSizeClass.PREVIEW, 2560, 1440)
    assert (width, height) == (1120, 760)


def test_dialog_size_clamps_to_small_available_geometry() -> None:
    assert resolved_dialog_size(DialogSizeClass.CATALOG, 500, 360) == (452, 312)


def test_release_dialog_families_use_authoritative_content_fit_geometry() -> None:
    expected = {
        DialogSizeClass.COMPACT_STATUS: (500, 200),
        DialogSizeClass.TRANSACTION: (540, 250),
        DialogSizeClass.FERTILIZER: (720, 405),
        DialogSizeClass.SETTINGS: (900, 490),
        DialogSizeClass.NURSERY: (950, 540),
        DialogSizeClass.PROGRESS: (980, 520),
        DialogSizeClass.LOADOUT: (1000, 540),
        DialogSizeClass.PLANT_STORY: (840, 525),
        DialogSizeClass.SPECIES_DETAIL: (860, 570),
        DialogSizeClass.GROWTH_CHARGE: (540, 315),
        DialogSizeClass.GARDEN_WORKSPACE: (1240, 840),
    }
    for family, size in expected.items():
        assert resolved_dialog_size(family, 2560, 1440) == size

    content_fit_families = set(expected) - {DialogSizeClass.GARDEN_WORKSPACE}
    assert all(
        DIALOG_SIZE_POLICIES[family].content_fit
        for family in content_fit_families
    )
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].screen_margin == 24
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].preserve_transition_height is True


def test_named_dialog_views_match_the_authoritative_width_and_height_profiles() -> None:
    expected = {
        DialogSizeClass.COMPACT_STATUS: {
            "default": (480, 500, 520, 180, 200, 210),
        },
        DialogSizeClass.TRANSACTION: {
            "default": (480, 500, 520, 210, 230, 250),
            "simple": (480, 500, 520, 210, 230, 250),
            "loading": (480, 500, 520, 210, 230, 250),
            "complex": (540, 570, 600, 250, 295, 340),
            "growth-charge": (500, 500, 500, 220, 230, 240),
        },
        DialogSizeClass.FERTILIZER: {
            "default": (700, 720, 740, 390, 405, 420),
            "selection": (700, 720, 740, 390, 405, 420),
            "replacement": (560, 590, 620, 250, 275, 300),
        },
        DialogSizeClass.SETTINGS: {
            "display": (880, 900, 920, 480, 500, 520),
            "advanced": (880, 900, 920, 540, 565, 590),
            "diagnostics-clean": (820, 880, 900, 330, 360, 390),
            "diagnostics-warning": (820, 860, 900, 310, 325, 340),
            "diagnostics-expanded": (820, 880, 900, 500, 545, 590),
        },
        DialogSizeClass.NURSERY: {
            "starter": (950, 950, 950, 470, 485, 500),
            "plants": (930, 950, 970, 520, 545, 570),
            "owned": (920, 950, 980, 470, 500, 530),
            "fertilizer": (930, 950, 970, 490, 515, 540),
            "spaces": (900, 925, 950, 340, 355, 370),
            "weather": (930, 950, 970, 500, 525, 550),
            "collection-complete": (900, 925, 950, 280, 300, 320),
            "empty": (920, 950, 980, 300, 335, 370),
        },
        DialogSizeClass.PROGRESS: {
            "growth": (940, 960, 980, 500, 520, 540),
            "streak": (940, 960, 980, 540, 560, 580),
            "currency": (880, 920, 940, 330, 345, 360),
            "achievements": (940, 980, 980, 600, 600, 640),
            "collection": (940, 960, 980, 520, 550, 580),
            "collection-empty": (940, 960, 980, 350, 380, 410),
        },
        DialogSizeClass.LOADOUT: {
            "default": (980, 1000, 1020, 520, 540, 560),
        },
        DialogSizeClass.PLANT_STORY: {
            "default": (800, 840, 860, 500, 525, 550),
        },
        DialogSizeClass.SPECIES_DETAIL: {
            "default": (840, 860, 900, 540, 570, 590),
            "uncollected": (840, 860, 900, 540, 560, 590),
        },
            DialogSizeClass.GROWTH_CHARGE: {
                "ready": (500, 510, 520, 270, 285, 300),
                "loading": (500, 510, 520, 270, 285, 300),
                "stale": (500, 510, 540, 270, 300, 310),
            },
    }

    for family, views in expected.items():
        policy = DIALOG_SIZE_POLICIES[family]
        assert set(views) <= set(DIALOG_VIEW_HEIGHT_PROFILES[family])
        for view_key, dimensions in views.items():
            profile = dialog_height_profile(family, view_key)
            actual = (
                profile.min_width or policy.min_width,
                profile.preferred_width or policy.preferred_width,
                profile.max_width or policy.max_width,
                profile.min_height,
                profile.preferred_height,
                profile.max_height,
            )
            assert actual == dimensions


def test_view_width_resolution_prefers_each_view_not_the_family_width() -> None:
    assert resolved_dialog_view_width(
        DialogSizeClass.TRANSACTION,
        "simple",
        2_000,
    ) == 500
    assert resolved_dialog_view_width(
        DialogSizeClass.TRANSACTION,
        "complex",
        2_000,
    ) == 570
    assert resolved_dialog_view_width(
        DialogSizeClass.TRANSACTION,
        "simple",
        490,
    ) == 490


def test_content_fit_constraint_detection_is_width_and_height_aware() -> None:
    common = {
        "window_mode": DialogWindowMode.CONTENT,
        "preferred_width": 500,
        "preferred_height": 230,
        "fitted_width": 500,
        "fitted_height": 210,
    }
    assert content_fit_geometry_limited(
        **common,
        screen_width_cap=1_000,
        screen_height_cap=1_000,
    ) is False
    assert content_fit_geometry_limited(
        **{**common, "fitted_width": 490},
        screen_width_cap=490,
        screen_height_cap=1_000,
    ) is True
    assert content_fit_geometry_limited(
        **common,
        screen_width_cap=1_000,
        screen_height_cap=220,
    ) is True
    assert content_fit_geometry_limited(
        **common,
        screen_width_cap=1_000,
        screen_height_cap=1_000,
        natural_width=540,
    ) is False
    assert content_fit_geometry_limited(
        **common,
        screen_width_cap=1_000,
        screen_height_cap=1_000,
        natural_height=260,
    ) is False
    assert content_fit_geometry_limited(
        **{**common, "fitted_width": 490},
        screen_width_cap=490,
        screen_height_cap=1_000,
        natural_width=540,
    ) is True
    assert content_fit_geometry_limited(
        **{**common, "fitted_height": 220},
        screen_width_cap=1_000,
        screen_height_cap=220,
        natural_height=260,
    ) is True
    assert content_fit_geometry_limited(
        **{**common, "window_mode": DialogWindowMode.WORKSPACE},
        screen_width_cap=490,
        screen_height_cap=220,
        natural_width=540,
        natural_height=260,
    ) is False


def test_tabbed_empty_views_keep_the_workspace_window_mode() -> None:
    assert "empty" in DIALOG_VIEW_HEIGHT_PROFILES[DialogSizeClass.NURSERY]
    assert "collection-empty" in DIALOG_VIEW_HEIGHT_PROFILES[DialogSizeClass.PROGRESS]
    assert dialog_window_mode(DialogSizeClass.NURSERY) is DialogWindowMode.WORKSPACE
    assert dialog_window_mode(DialogSizeClass.PROGRESS) is DialogWindowMode.WORKSPACE


def test_dialog_state_and_focus_values_are_stable_contracts() -> None:
    assert set(DIALOG_VIEW_POLICIES) == set(DialogViewState)
    assert DialogViewState.READY.value == "ready"
    assert DialogViewState.VALIDATING.value == "validating"
    assert DialogViewState.COMMITTING.value == "committing"
    assert DialogViewState.LOADING.value == "loading"
    assert DialogViewState.STALE_PROPOSAL.value == "stale-proposal"
    assert DialogViewState.BUSINESS_RULE_BLOCKED.value == "business-rule-blocked"
    assert DialogViewState.RECOVERABLE_FAILURE.value == "recoverable-failure"
    assert DialogViewState.PERSISTENCE_FAILURE.value == "persistence-failure"
    assert DialogViewState.SUCCESS.value == "success"
    assert DialogViewState.ERROR.value == "error"
    assert dialog_view_policy(DialogViewState.VALIDATING).busy is True
    assert dialog_view_policy(DialogViewState.COMMITTING).busy is True
    assert dialog_view_policy(DialogViewState.STALE_PROPOSAL).feedback_tone == "warning"
    assert dialog_view_policy(DialogViewState.RECOVERABLE_FAILURE).retryable is True
    assert dialog_view_policy(DialogViewState.PERSISTENCE_FAILURE).assertive is True
    assert dialog_view_policy(DialogViewState.SUCCESS).feedback_tone == "success"
    assert InitialFocusPolicy.SAFE_ACTION.value == "safe-action"


def test_dialog_close_policy_is_opt_in_and_prioritizes_in_flight_work() -> None:
    permissive = DialogClosePolicy()
    assert resolve_dialog_close(
        permissive,
        DialogCloseReason.ESCAPE,
        dirty=True,
        in_flight=True,
    ).allowed is True

    protected = DialogClosePolicy(
        protect_dirty=True,
        protect_in_flight=True,
    )
    in_flight = resolve_dialog_close(
        protected,
        DialogCloseReason.WINDOW_CLOSE,
        dirty=True,
        in_flight=True,
    )
    assert in_flight.allowed is False
    assert in_flight.reason is DialogCloseReason.WINDOW_CLOSE
    assert in_flight.blocked_by is DialogCloseBlocker.IN_FLIGHT

    dirty = resolve_dialog_close(
        protected,
        DialogCloseReason.CLOSE_BUTTON,
        dirty=True,
    )
    assert dirty.blocked_by is DialogCloseBlocker.DIRTY
    assert resolve_dialog_close(
        protected,
        DialogCloseReason.CLOSE_BUTTON,
        dirty=True,
        dirty_confirmed=True,
    ).allowed is True


def test_text_column_uses_a_character_measurement_not_a_fixed_screenshot_width() -> None:
    assert text_column_width(9) == 612
    assert text_column_width(0, 0) == 1


def test_content_fit_coalescing_gives_terminal_shrink_precedence() -> None:
    assert merge_content_fit_preservation(None, None) is None
    assert merge_content_fit_preservation(None, True) is True
    assert merge_content_fit_preservation(True, False) is False
    assert merge_content_fit_preservation(False, True) is False

    assert should_preserve_transition_height(
        policy_enabled=True,
        in_flight=True,
        requested=True,
        preserved_height=300,
    ) is True
    for request in (None, True, False):
        assert should_preserve_transition_height(
            policy_enabled=True,
            in_flight=False,
            requested=request,
            preserved_height=300,
        ) is False
    assert should_preserve_transition_height(
        policy_enabled=True,
        in_flight=True,
        requested=False,
        preserved_height=300,
    ) is False


def test_capture_telemetry_records_are_serializable_and_explicit() -> None:
    scrollbar = ScrollbarTelemetryRecord(
        name="Details",
        minimum=0,
        maximum=120,
        value=12,
        visible=True,
        overflow_owner=True,
    )
    record = DialogCaptureTelemetryRecord(
        client_surface_fill=0.94,
        nursery_root_offset=10,
        content_to_footer_gap=16,
        maximum_action_width_ratio=0.24,
        scrollbars=(scrollbar,),
        minimum_rendered_text_size=12.0,
        tooltip_widget_count=1,
        elided_widget_count=1,
        elision_without_tooltip_count=0,
        overflow_owner_count=1,
        window_mode=DialogWindowMode.WORKSPACE.value,
        client_bounds=DialogGeometryTelemetryRecord(0, 0, 900, 490),
        body_bounds=DialogGeometryTelemetryRecord(24, 82, 852, 338),
        footer_bounds=DialogGeometryTelemetryRecord(24, 430, 852, 42),
        settled_size=(900, 490),
        content_fit_pending=False,
        safety_scroll_active=False,
    )
    payload = record.as_dict()
    assert payload["clientSurfaceFill"] == 0.94
    assert payload["nurseryRootOffset"] == 10
    assert payload["contentToFooterGap"] == 16
    assert payload["maximumActionWidthRatio"] == 0.24
    assert payload["minimumRenderedTextSize"] == 12.0
    assert payload["scrollbars"] == [scrollbar.as_dict()]
    assert payload["windowMode"] == "workspace"
    assert payload["clientBounds"] == {"x": 0, "y": 0, "width": 900, "height": 490}
    assert payload["bodyBounds"] == {"x": 24, "y": 82, "width": 852, "height": 338}
    assert payload["footerBounds"] == {"x": 24, "y": 430, "width": 852, "height": 42}
    assert payload["settledSize"] == {"width": 900, "height": 490}
    assert payload["contentFitPending"] is False
    assert payload["safetyScrollActive"] is False
