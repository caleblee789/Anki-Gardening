from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DIALOG_LAYOUT_METRICS,
    DIALOG_SCROLL_CONTRACT,
    DIALOG_VIEW_HEIGHT_PROFILES,
    DIALOG_VIEW_POLICIES,
    DialogCloseBlocker,
    DialogClosePolicy,
    DialogCloseReason,
    DialogCaptureTelemetryRecord,
    DialogGeometryTelemetryRecord,
    DialogLayoutMetrics,
    DialogSizeClass,
    DialogSizeProfile,
    DialogScrollContract,
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
    resolved_dialog_geometry,
    resolved_dialog_view_width,
    resolve_widget_layout,
    should_schedule_content_fit,
    should_preserve_transition_height,
    text_column_width,
    workspace_content_fit_natural_height,
)


def test_widget_layout_resolver_accepts_qt_methods_and_stored_layouts() -> None:
    method_layout = object()
    stored_layout = object()

    class MethodWidget:
        def layout(self) -> object:
            return method_layout

    class StoredWidget:
        layout = stored_layout

    assert resolve_widget_layout(MethodWidget()) is method_layout
    assert resolve_widget_layout(StoredWidget()) is stored_layout
    assert resolve_widget_layout(None) is None


def test_shared_dialog_regions_use_the_release_spacing_and_scroll_contract() -> None:
    metrics = DIALOG_LAYOUT_METRICS
    assert isinstance(metrics, DialogLayoutMetrics)
    assert metrics.horizontal_padding == 24
    assert metrics.compact_body_padding == 20
    assert metrics.body_margins == (24, 16, 24, 24)
    assert metrics.footer_margins == (24, 12, 24, 16)
    assert metrics.card_padding == 16
    assert metrics.section_gap == 16
    assert metrics.row_gap == 12
    assert metrics.action_gap == 8

    scrolling = DIALOG_SCROLL_CONTRACT
    assert isinstance(scrolling, DialogScrollContract)
    assert scrolling.header_pinned is True
    assert scrolling.tabs_pinned is True
    assert scrolling.footer_pinned is True
    assert scrolling.central_body_scrolls is True
    assert scrolling.horizontal_scrolls is False
    assert scrolling.body_minimum_height == 0
    assert scrolling.bottom_padding == 24
    assert scrolling.scrollbar_clearance == 8
    assert scrolling.overflow_owner_count == 1


def test_every_dialog_size_class_has_a_sane_policy() -> None:
    assert set(DIALOG_SIZE_POLICIES) == set(DialogSizeClass)
    for policy in DIALOG_SIZE_POLICIES.values():
        assert 0 < policy.min_width <= policy.preferred_width <= policy.max_width
        assert 0 < policy.min_height <= policy.preferred_height <= policy.max_height
        assert 0 < policy.width_ratio <= 1
        assert 0 < policy.height_ratio <= 1
        assert isinstance(policy, DialogSizeProfile)
        assert isinstance(policy.window_mode, DialogWindowMode)


def test_every_non_canvas_dialog_content_fits_with_one_central_scroll_owner() -> None:
    for policy in DIALOG_SIZE_POLICIES.values():
        if policy.window_mode is DialogWindowMode.CANVAS:
            assert policy.content_fit is False
        else:
            assert policy.content_fit is True
    assert DIALOG_SCROLL_CONTRACT.central_body_scrolls is True
    assert DIALOG_SCROLL_CONTRACT.overflow_owner_count == 1
    assert DIALOG_SCROLL_CONTRACT.horizontal_scrolls is False


def test_content_fit_scheduler_includes_workspace_but_never_canvas() -> None:
    assert should_schedule_content_fit(
        DialogWindowMode.CONTENT,
        policy_content_fit=True,
    )
    assert should_schedule_content_fit(
        DialogWindowMode.WORKSPACE,
        policy_content_fit=True,
    )
    assert not should_schedule_content_fit(
        DialogWindowMode.CANVAS,
        policy_content_fit=True,
    )
    assert not should_schedule_content_fit(
        DialogWindowMode.WORKSPACE,
        policy_content_fit=False,
    )


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
    ) == (500, 190)


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


def test_dialog_geometry_exposes_screen_clamped_minimum_initial_and_maximum() -> None:
    large = resolved_dialog_geometry(DialogSizeClass.SETTINGS, 2560, 1440)
    assert large.minimum_size == (800, 480)
    assert large.initial_size == (820, 510)
    assert large.maximum_size == (840, 720)

    small = resolved_dialog_geometry(DialogSizeClass.SETTINGS, 760, 560)
    assert small.minimum_size == (712, 480)
    assert small.initial_size == (712, 510)
    assert small.maximum_size == (712, 512)
    assert small.maximum_width <= 760 - 48
    assert small.maximum_height <= 560 - 48


def test_release_dialog_families_use_authoritative_content_fit_geometry() -> None:
    expected = {
        DialogSizeClass.COMPACT_STATUS: (500, 190),
        DialogSizeClass.TRANSACTION: (540, 250),
        DialogSizeClass.FERTILIZER: (660, 360),
        DialogSizeClass.SETTINGS: (820, 510),
        DialogSizeClass.NURSERY: (940, 420),
        DialogSizeClass.PROGRESS: (950, 570),
        DialogSizeClass.LOADOUT: (1000, 540),
        DialogSizeClass.PLANT_STORY: (760, 500),
        DialogSizeClass.SPECIES_DETAIL: (820, 550),
        DialogSizeClass.GROWTH_CHARGE: (500, 300),
        DialogSizeClass.GARDEN_WORKSPACE: (1240, 840),
    }
    for family, size in expected.items():
        assert resolved_dialog_size(family, 2560, 1440) == size

    content_fit_families = set(expected) - {
        DialogSizeClass.GARDEN_WORKSPACE,
    }
    assert all(
        DIALOG_SIZE_POLICIES[family].content_fit
        for family in content_fit_families
    )
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].screen_margin == 24
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].preserve_transition_height is True
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.PROGRESS].content_fit is True


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
            "growth-charge": (500, 500, 500, 270, 280, 300),
            "replacement": (500, 520, 540, 230, 300, 340),
        },
        DialogSizeClass.FERTILIZER: {
            "default": (640, 660, 680, 470, 490, 520),
            "selection": (640, 660, 680, 470, 490, 520),
            "replacement": (500, 520, 540, 230, 260, 290),
        },
        DialogSizeClass.SETTINGS: {
            "display": (800, 820, 840, 390, 400, 420),
            "advanced": (800, 820, 840, 700, 700, 720),
            "diagnostics-clean": (760, 780, 800, 280, 300, 320),
            "diagnostics-warning": (760, 780, 800, 280, 300, 320),
            "diagnostics-expanded": (760, 780, 800, 430, 470, 520),
        },
        DialogSizeClass.NURSERY: {
            "starter": (925, 940, 950, 370, 380, 410),
            "plants": (925, 940, 950, 300, 360, 520),
            "owned": (925, 940, 950, 470, 500, 530),
            "fertilizer": (925, 940, 950, 500, 506, 541),
            "spaces": (925, 940, 950, 300, 480, 580),
            "garden_features": (925, 940, 950, 488, 575, 580),
            "collection-complete": (925, 940, 950, 308, 323, 338),
            "collection-complete-receipt": (925, 940, 950, 390, 400, 410),
            "empty": (925, 940, 950, 300, 335, 370),
        },
        DialogSizeClass.PROGRESS: {
            "growth": (940, 940, 960, 501, 501, 510),
            "today": (940, 950, 960, 564, 570, 580),
            "streak": (940, 940, 960, 440, 460, 480),
            "currency": (940, 950, 960, 340, 380, 440),
            "achievements": (950, 950, 950, 570, 570, 570),
            "collection": (950, 950, 950, 570, 570, 570),
            "collection-empty": (940, 950, 960, 360, 400, 460),
        },
        DialogSizeClass.LOADOUT: {
            "default": (980, 1000, 1020, 704, 704, 704),
        },
        DialogSizeClass.PLANT_STORY: {
            "default": (740, 760, 780, 480, 500, 520),
        },
        DialogSizeClass.SPECIES_DETAIL: {
            "default": (800, 820, 840, 520, 550, 570),
            "uncollected": (800, 820, 840, 520, 550, 570),
        },
        DialogSizeClass.GROWTH_CHARGE: {
            "ready": (480, 500, 510, 350, 375, 400),
            "loading": (480, 500, 510, 350, 375, 400),
            "stale": (500, 510, 540, 380, 410, 450),
            "success": (480, 500, 510, 300, 320, 340),
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
    ) is True


def test_workspace_content_fit_replaces_the_allocated_viewport_with_content() -> None:
    assert workspace_content_fit_natural_height(
        340,
        window_mode=DialogWindowMode.WORKSPACE,
        window_height=340,
        viewport_height=181,
        scroll_content_height=218,
    ) == 377
    # The same natural result remains stable after the viewport expands.
    assert workspace_content_fit_natural_height(
        340,
        window_mode=DialogWindowMode.WORKSPACE,
        window_height=377,
        viewport_height=218,
        scroll_content_height=218,
    ) == 377
    assert workspace_content_fit_natural_height(
        340,
        window_mode=DialogWindowMode.CONTENT,
        window_height=340,
        viewport_height=181,
        scroll_content_height=218,
    ) == 340


def test_nursery_spaces_profile_fits_endgame_and_committed_banner() -> None:
    profile = dialog_height_profile(DialogSizeClass.NURSERY, "spaces")
    ordinary_height = workspace_content_fit_natural_height(
        330,
        window_mode=DialogWindowMode.WORKSPACE,
        window_height=330,
        viewport_height=178,
        scroll_content_height=328,
    )
    banner_height = workspace_content_fit_natural_height(
        330,
        window_mode=DialogWindowMode.WORKSPACE,
        window_height=330,
        viewport_height=98,
        scroll_content_height=346,
    )

    assert ordinary_height == 480
    assert banner_height == 578
    assert profile.preferred_height >= ordinary_height
    assert profile.max_height >= banner_height


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
