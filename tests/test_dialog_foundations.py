from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_VIEW_POLICIES,
    DIALOG_SIZE_POLICIES,
    DialogCloseBlocker,
    DialogClosePolicy,
    DialogCloseReason,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
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
    ) == (560, 320)


def test_comparison_dialog_grows_for_cards_without_becoming_screen_sized() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPARISON,
        2560,
        1440,
    ) == (680, 460)


def test_preview_dialog_uses_large_screen_without_exceeding_policy() -> None:
    width, height = resolved_dialog_size(DialogSizeClass.PREVIEW, 2560, 1440)
    assert (width, height) == (1120, 760)


def test_dialog_size_clamps_to_small_available_geometry() -> None:
    assert resolved_dialog_size(DialogSizeClass.CATALOG, 500, 360) == (452, 312)


def test_release_dialog_families_use_locked_content_fit_geometry() -> None:
    expected = {
        DialogSizeClass.COMPACT_STATUS: (560, 320),
        DialogSizeClass.TRANSACTION: (680, 460),
        DialogSizeClass.FERTILIZER: (760, 520),
        DialogSizeClass.SETTINGS: (1020, 690),
        DialogSizeClass.NURSERY: (1100, 720),
        DialogSizeClass.PROGRESS: (1120, 800),
        DialogSizeClass.LOADOUT: (1160, 810),
        DialogSizeClass.GARDEN_WORKSPACE: (1240, 840),
    }
    for family, size in expected.items():
        assert resolved_dialog_size(family, 2560, 1440) == size
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].content_fit is True
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].screen_margin == 24
    assert DIALOG_SIZE_POLICIES[DialogSizeClass.TRANSACTION].preserve_transition_height is True


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
