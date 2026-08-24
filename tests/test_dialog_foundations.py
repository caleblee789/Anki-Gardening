from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DIALOG_VIEW_HEIGHT_PROFILES,
    DIALOG_VIEW_POLICIES,
    DialogCloseBlocker,
    DialogClosePolicy,
    DialogCloseReason,
    DialogCaptureTelemetryRecord,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
    ScrollbarTelemetryRecord,
    dialog_height_profile,
    dialog_view_policy,
    merge_content_fit_preservation,
    resolve_dialog_close,
    resolved_dialog_size,
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


def test_compact_confirmation_does_not_expand_with_a_large_screen() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPACT_CONFIRMATION,
        2560,
        1440,
    ) == (520, 220)


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
        DialogSizeClass.COMPACT_STATUS: (520, 220),
        DialogSizeClass.TRANSACTION: (540, 250),
        DialogSizeClass.FERTILIZER: (720, 430),
        DialogSizeClass.SETTINGS: (900, 490),
        DialogSizeClass.NURSERY: (950, 540),
        DialogSizeClass.PROGRESS: (980, 540),
        DialogSizeClass.LOADOUT: (1020, 610),
        DialogSizeClass.PLANT_STORY: (840, 595),
        DialogSizeClass.SPECIES_DETAIL: (920, 600),
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
        DialogSizeClass.SETTINGS: {
            "display": (880, 900, 920, 460, 485, 510),
            "advanced": (880, 900, 920, 540, 565, 590),
            "diagnostics-clean": (820, 880, 900, 330, 360, 390),
            "diagnostics-warning": (820, 880, 900, 360, 390, 420),
            "diagnostics-expanded": (820, 880, 900, 500, 545, 590),
        },
        DialogSizeClass.NURSERY: {
            "plants": (920, 950, 980, 540, 570, 600),
            "owned": (920, 950, 980, 470, 500, 530),
            "fertilizer": (920, 950, 980, 470, 500, 530),
            "spaces": (920, 950, 980, 380, 405, 430),
            "weather": (920, 950, 980, 480, 510, 540),
            "empty": (920, 950, 980, 300, 335, 370),
        },
        DialogSizeClass.PROGRESS: {
            "growth": (960, 980, 1000, 520, 540, 560),
            "streak": (960, 980, 1000, 560, 585, 610),
            "currency": (960, 980, 1000, 360, 390, 420),
            "achievements": (960, 980, 1000, 600, 625, 650),
            "collection": (960, 980, 1000, 540, 570, 600),
            "collection-empty": (960, 980, 1000, 350, 380, 410),
        },
        DialogSizeClass.LOADOUT: {
            "default": (1000, 1020, 1040, 560, 610, 650),
        },
        DialogSizeClass.PLANT_STORY: {
            "default": (800, 840, 860, 560, 595, 630),
        },
        DialogSizeClass.SPECIES_DETAIL: {
            "default": (880, 920, 940, 580, 600, 620),
            "uncollected": (880, 920, 940, 430, 455, 480),
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
    )
    payload = record.as_dict()
    assert payload["clientSurfaceFill"] == 0.94
    assert payload["nurseryRootOffset"] == 10
    assert payload["contentToFooterGap"] == 16
    assert payload["maximumActionWidthRatio"] == 0.24
    assert payload["minimumRenderedTextSize"] == 12.0
    assert payload["scrollbars"] == [scrollbar.as_dict()]
