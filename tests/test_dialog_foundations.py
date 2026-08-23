from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DIALOG_VIEW_HEIGHT_PROFILES,
    DIALOG_VIEW_POLICIES,
    DialogCloseBlocker,
    DialogClosePolicy,
    DialogCloseReason,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
    dialog_height_profile,
    dialog_view_policy,
    resolve_dialog_close,
    resolved_dialog_size,
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
    ) == (540, 250)


def test_comparison_dialog_grows_for_cards_without_becoming_screen_sized() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPARISON,
        2560,
        1440,
    ) == (620, 290)


def test_preview_dialog_uses_large_screen_without_exceeding_policy() -> None:
    width, height = resolved_dialog_size(DialogSizeClass.PREVIEW, 2560, 1440)
    assert (width, height) == (1120, 760)


def test_dialog_size_clamps_to_small_available_geometry() -> None:
    assert resolved_dialog_size(DialogSizeClass.CATALOG, 500, 360) == (452, 312)


def test_release_dialog_families_use_authoritative_content_fit_geometry() -> None:
    expected = {
        DialogSizeClass.COMPACT_STATUS: (540, 250),
        DialogSizeClass.TRANSACTION: (620, 290),
        DialogSizeClass.FERTILIZER: (720, 480),
        DialogSizeClass.SETTINGS: (980, 525),
        DialogSizeClass.NURSERY: (1080, 660),
        DialogSizeClass.PROGRESS: (1080, 650),
        DialogSizeClass.LOADOUT: (1080, 630),
        DialogSizeClass.PLANT_STORY: (840, 570),
        DialogSizeClass.SPECIES_DETAIL: (920, 620),
        DialogSizeClass.GROWTH_CHARGE: (620, 380),
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
            "display": (940, 980, 1000, 500, 525, 550),
            "advanced": (940, 980, 1000, 580, 610, 640),
            "diagnostics-clean": (900, 930, 960, 440, 470, 500),
            "diagnostics-expanded": (940, 980, 1000, 580, 620, 660),
        },
        DialogSizeClass.NURSERY: {
            "plants": (1040, 1080, 1100, 660, 680, 700),
            "fertilizer": (1040, 1080, 1100, 600, 620, 640),
            "spaces": (1040, 1080, 1100, 470, 495, 520),
            "weather": (1040, 1080, 1100, 600, 625, 650),
            "empty": (1040, 1080, 1100, 400, 430, 460),
        },
        DialogSizeClass.PROGRESS: {
            "growth": (1040, 1080, 1120, 620, 660, 700),
            "streak": (1040, 1080, 1120, 680, 710, 740),
            "currency": (1040, 1080, 1120, 520, 560, 600),
            "achievements": (1040, 1080, 1120, 700, 720, 740),
            "collection": (1040, 1080, 1120, 680, 710, 740),
        },
        DialogSizeClass.LOADOUT: {
            "default": (1040, 1080, 1120, 600, 630, 650),
        },
        DialogSizeClass.PLANT_STORY: {
            "default": (800, 840, 860, 540, 570, 600),
        },
        DialogSizeClass.SPECIES_DETAIL: {
            "default": (880, 920, 940, 580, 620, 650),
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
