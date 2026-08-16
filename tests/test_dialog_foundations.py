from __future__ import annotations

from ankigarden.ui.dialog_foundations import (
    DIALOG_SIZE_POLICIES,
    DialogSizeClass,
    DialogViewState,
    InitialFocusPolicy,
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
    ) == (480, 300)


def test_comparison_dialog_grows_for_cards_without_becoming_screen_sized() -> None:
    assert resolved_dialog_size(
        DialogSizeClass.COMPARISON,
        2560,
        1440,
    ) == (820, 660)


def test_preview_dialog_uses_large_screen_without_exceeding_policy() -> None:
    width, height = resolved_dialog_size(DialogSizeClass.PREVIEW, 2560, 1440)
    assert (width, height) == (1280, 960)


def test_dialog_size_clamps_to_small_available_geometry() -> None:
    assert resolved_dialog_size(DialogSizeClass.CATALOG, 500, 360) == (460, 324)


def test_dialog_state_and_focus_values_are_stable_contracts() -> None:
    assert DialogViewState.ERROR.value == "error"
    assert InitialFocusPolicy.SAFE_ACTION.value == "safe-action"


def test_text_column_uses_a_character_measurement_not_a_fixed_screenshot_width() -> None:
    assert text_column_width(9) == 612
    assert text_column_width(0, 0) == 1
