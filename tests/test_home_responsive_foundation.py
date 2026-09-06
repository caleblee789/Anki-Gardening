from __future__ import annotations

from pathlib import Path

import pytest

from ankigarden.ui.home_widget import (
    HOME_COMPACT_CONTAINER_MAX_WIDTH,
    HOME_LAYOUT_COMPACT,
    HOME_LAYOUT_NARROW,
    HOME_LAYOUT_STANDARD,
    HOME_NARROW_CONTAINER_MAX_WIDTH,
    HOME_WIDGET_STYLE,
    HomeWidgetStateController,
    home_container_layout,
    render_home_widget,
)


@pytest.mark.parametrize(
    ("threshold", "expected"),
    (
        (
            HOME_NARROW_CONTAINER_MAX_WIDTH,
            {
                -2: HOME_LAYOUT_NARROW,
                -1: HOME_LAYOUT_NARROW,
                0: HOME_LAYOUT_NARROW,
                1: HOME_LAYOUT_COMPACT,
                2: HOME_LAYOUT_COMPACT,
            },
        ),
        (
            HOME_COMPACT_CONTAINER_MAX_WIDTH,
            {
                -2: HOME_LAYOUT_COMPACT,
                -1: HOME_LAYOUT_COMPACT,
                0: HOME_LAYOUT_COMPACT,
                1: HOME_LAYOUT_STANDARD,
                2: HOME_LAYOUT_STANDARD,
            },
        ),
    ),
)
def test_home_container_ranges_are_deterministic_at_every_boundary(
    threshold: int,
    expected: dict[int, str],
) -> None:
    assert {
        offset: home_container_layout(threshold + offset)
        for offset in (-2, -1, 0, 1, 2)
    } == expected


def test_home_breakpoints_are_container_scoped_and_have_no_viewport_width_cliffs() -> None:
    assert HOME_WIDGET_STYLE.count("@container") == 2
    assert "@container (max-width: 400px)" in HOME_WIDGET_STYLE
    assert "@container (max-width:340px)" in HOME_WIDGET_STYLE
    # Preserve the reviewed starter-only exception without permitting viewport
    # breakpoints to change the regular Home banner.
    starter_breakpoint = '''@media (max-width:560px) {
  #ag-home-root[data-home-mode="starter"] .ag-home__identity-row { grid-template-columns:minmax(0,1fr); row-gap:12px; }
  #ag-home-root[data-home-mode="starter"] .ag-home__identity-row > button { grid-column:1; justify-self:start; }
  #ag-home-root[data-home-mode="starter"] .ag-home__artwork-zone { display:none; }
}'''
    assert HOME_WIDGET_STYLE.count(starter_breakpoint) == 1
    assert "@media (max-width" not in HOME_WIDGET_STYLE.replace(starter_breakpoint, "")
    assert ".ag-home__metrics { grid-template-columns" not in HOME_WIDGET_STYLE
    assert ".ag-home__scene { height:160px; }" not in HOME_WIDGET_STYLE
    assert "height:176px" not in HOME_WIDGET_STYLE


def test_home_banner_keeps_progress_and_action_readable_on_narrow_containers() -> None:
    assert "width:min(calc(100% - 48px), 520px)" in HOME_WIDGET_STYLE
    assert "max-width:520px" in HOME_WIDGET_STYLE
    assert "margin:24px auto 18px" in HOME_WIDGET_STYLE
    assert (
        "grid-template-columns:minmax(0,260px) minmax(0,1fr) max-content"
        in HOME_WIDGET_STYLE
    )
    assert "min-width:112px !important" in HOME_WIDGET_STYLE
    assert "width:260px" in HOME_WIDGET_STYLE
    assert "bottom:auto; width:100%" in HOME_WIDGET_STYLE
    assert (
        ".ag-home__support,.ag-home__progress-copy,.ag-home__growth-track { display:none; }"
        not in HOME_WIDGET_STYLE
    )
    assert HOME_WIDGET_STYLE.index(
        "@container (max-width: 400px)"
    ) < HOME_WIDGET_STYLE.index("@container (max-width:340px)")
    assert "white-space:nowrap" in HOME_WIDGET_STYLE




@pytest.mark.parametrize(
    ("enable_animations", "reduced_motion", "expected_mode"),
    (
        (True, False, "standard"),
        (False, False, "reduced"),
        (True, True, "reduced"),
        (False, True, "reduced"),
    ),
)
def test_addon_motion_preferences_are_preserved_across_request_states(
    enable_animations: bool,
    reduced_motion: bool,
    expected_mode: str,
) -> None:
    controller = HomeWidgetStateController()
    controller.set_motion_preferences(
        enable_animations=enable_animations,
        reduced_motion=reduced_motion,
    )
    request_id = controller.begin_request()
    assert request_id == 1

    loading_html = render_home_widget(controller.snapshot)
    assert controller.resolve_error(request_id, "Temporary problem") is True
    error_html = render_home_widget(controller.snapshot)

    assert f'data-motion="{expected_mode}"' in loading_html
    assert f'data-motion="{expected_mode}"' in error_html
    assert controller.snapshot.enable_animations is enable_animations
    assert controller.snapshot.reduced_motion is reduced_motion


def test_os_and_addon_reduced_motion_form_one_effective_css_policy() -> None:
    assert "pointer-events:none" in HOME_WIDGET_STYLE
    assert '#ag-home-root[data-motion="reduced"] { transition:none; }' in HOME_WIDGET_STYLE
    assert '#ag-home-root[data-motion="reduced"]:hover { transform:none; }' in HOME_WIDGET_STYLE
    assert (
        '#ag-home-root[data-motion="reduced"] button:active { transform:none; }'
        in HOME_WIDGET_STYLE
    )
    assert "@media (prefers-reduced-motion: reduce)" in HOME_WIDGET_STYLE
    media_policy = HOME_WIDGET_STYLE.split(
        "@media (prefers-reduced-motion: reduce)",
        1,
    )[1].split("}", 3)
    assert any("transition:none" in rule for rule in media_policy)
    assert any("transform:none" in rule for rule in media_policy)




def test_invalid_home_container_width_fails_closed() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        home_container_layout(float("nan"))
