from __future__ import annotations

import runpy
import re
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _theme_scope() -> dict[str, Any]:
    return runpy.run_path(str(ROOT / "ankigarden/ui/theme.py"))


def _relative_luminance(color: str) -> float:
    value = color.removeprefix("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class _Style:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def unpolish(self, widget: object) -> None:
        self.events.append(("unpolish", widget))

    def polish(self, widget: object) -> None:
        self.events.append(("polish", widget))


class _FeatureFont:
    def __init__(self) -> None:
        self.features: list[tuple[object, int]] = []

    def setFeature(self, feature: object, value: int) -> None:
        self.features.append((feature, value))


class _NoFeatureFont:
    pass


class _Widget:
    def __init__(self, font: object | None = None) -> None:
        self.properties: dict[str, object] = {}
        self.enabled = True
        self.minimum_width = 0
        self.minimum_height = 0
        self.accessible_name = ""
        self.accessible_description = "Available action"
        self.tooltip = ""
        self._font = font if font is not None else _NoFeatureFont()
        self.applied_font: object | None = None
        self._style = _Style()

    def setProperty(self, name: str, value: object) -> None:
        self.properties[name] = value

    def property(self, name: str) -> object | None:
        return self.properties.get(name)

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setMinimumSize(self, width: int, height: int) -> None:
        self.minimum_width = width
        self.minimum_height = height

    def setMinimumHeight(self, height: int) -> None:
        self.minimum_height = height

    def minimumWidth(self) -> int:
        return self.minimum_width

    def minimumHeight(self) -> int:
        return self.minimum_height

    def setAccessibleName(self, name: str) -> None:
        self.accessible_name = name

    def setAccessibleDescription(self, description: str) -> None:
        self.accessible_description = description

    def accessibleDescription(self) -> str:
        return self.accessible_description

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def font(self) -> object:
        return self._font

    def setFont(self, font: object) -> None:
        self.applied_font = font

    def style(self) -> _Style:
        return self._style


def test_text_roles_define_legible_type_and_line_metrics() -> None:
    scope = _theme_scope()
    text_role = scope["TextRole"]
    tokens = scope["TEXT_ROLE_TOKENS"]

    assert {role.value for role in text_role} == {
        "display-title",
        "screen-title",
        "section-heading",
        "card-title",
        "body",
        "secondary",
        "metadata",
        "badge",
        "numeric-display",
        "button-label",
    }
    assert scope["TYPOGRAPHY_SCALE"] is tokens
    assert scope["TEXT_STYLES"] is tokens
    assert all(
        token.font_size_px >= scope["MIN_LEGIBLE_TEXT_SIZE"]
        and token.line_height_px >= token.font_size_px
        for token in tokens.values()
    )
    assert tokens[text_role.BODY].font_size_px >= scope["MIN_BODY_TEXT_SIZE"]
    assert tokens[text_role.BUTTON_LABEL].font_size_px >= scope["MIN_BODY_TEXT_SIZE"]
    assert tokens[text_role.NUMERIC_DISPLAY].tabular_numerals is True

    stylesheet = scope["typography_stylesheet"]()
    for role in text_role:
        assert f"*[textRole='{role.value}']" in stylesheet
    assert "line-height" not in stylesheet


def test_spacing_scale_is_named_monotonic_and_rejects_ad_hoc_values() -> None:
    scope = _theme_scope()
    spacing_token = scope["SpacingToken"]
    values = [int(token) for token in spacing_token]

    assert values == sorted(set(values))
    assert values[0] == 0
    assert values[-1] == 48
    assert scope["spacing"]("md") == 12
    assert scope["spacing"](spacing_token.XL) == 24
    with pytest.raises(ValueError, match="outside the shared scale"):
        scope["spacing"](13)


def test_control_variants_keep_legacy_tertiary_and_44px_targets() -> None:
    scope = _theme_scope()
    control_variant = scope["ControlVariant"]

    assert {variant.value for variant in control_variant} == {
        "primary",
        "secondary",
        "quiet",
        "destructive",
    }
    assert scope["BUTTON_VARIANT_TERTIARY"] == "tertiary"
    assert scope["MIN_HIT_TARGET"] == 44
    assert scope["BUTTON_MIN_HEIGHT"] == 44
    assert scope["ICON_BUTTON_SIZE"] == 44

    buttons = scope["button_stylesheet"]()
    tools = scope["tool_button_stylesheet"]()
    assert "QPushButton[variant='quiet']" in buttons
    assert "QPushButton[variant='tertiary']" in buttons
    assert "QPushButton[variant='destructive']" in buttons
    assert "QPushButton:disabled" in buttons
    assert "QPushButton:focus" in buttons
    assert "QToolButton[gardenRole='icon-button']" in tools


def test_control_helpers_apply_variant_and_restore_disabled_description() -> None:
    scope = _theme_scope()
    widget = _Widget()

    normalized = scope["apply_control_variant"](widget, "tertiary")
    assert normalized is scope["ControlVariant"].QUIET
    assert widget.properties["variant"] == "quiet"
    assert (widget.minimum_width, widget.minimum_height) == (44, 44)

    with pytest.raises(ValueError, match="disabled_reason"):
        scope["set_control_enabled"](widget, False)

    scope["set_control_enabled"](
        widget,
        False,
        disabled_reason="Choose a plant before nurturing.",
    )
    assert widget.enabled is False
    assert widget.properties["gardenDisabled"] is True
    assert widget.properties["disabledReason"] == "Choose a plant before nurturing."
    assert widget.accessible_description == "Choose a plant before nurturing."

    # A second disabled refresh must not replace the saved enabled description.
    scope["set_disabled_semantics"](
        widget,
        True,
        reason="Still waiting for a plant.",
    )
    scope["set_disabled_semantics"](widget, False)
    assert widget.enabled is True
    assert widget.properties["gardenDisabled"] is False
    assert widget.properties["disabledReason"] == ""
    assert widget.accessible_description == "Available action"
    assert [event for event, _widget in widget._style.events].count("polish") >= 3


def test_icon_helper_requires_a_descriptive_name_and_preserves_hit_target() -> None:
    scope = _theme_scope()
    widget = _Widget()

    for glyph in ("?", "×", "  "):
        with pytest.raises(ValueError, match="accessible_name"):
            scope["set_icon_accessible_name"](widget, glyph)

    scope["set_icon_accessible_name"](
        widget,
        "Close Plant Story",
        accessible_description="Return focus to the plant card.",
        tooltip="Close",
    )
    assert widget.accessible_name == "Close Plant Story"
    assert widget.accessible_description == "Return focus to the plant card."
    assert widget.tooltip == "Close"
    assert widget.properties["iconButton"] is True
    assert widget.properties["gardenRole"] == "icon-button"
    assert (widget.minimum_width, widget.minimum_height) == (44, 44)


def test_non_button_focus_surface_uses_the_shared_visible_ring_hook() -> None:
    scope = _theme_scope()
    widget = _Widget()

    assert scope["set_keyboard_focus_surface"](widget) is widget
    assert widget.properties["keyboardFocusSurface"] is True
    assert ("polish", widget) in widget._style.events

    stylesheet = scope["semantic_component_stylesheet"]()
    assert "QFrame[keyboardFocusSurface='true']:focus" in stylesheet
    assert "QLabel[keyboardFocusSurface='true']:focus" in stylesheet
    assert scope["GARDEN_THEME"]["focus_ring"] in stylesheet


def test_tabular_numerals_apply_feature_with_a_safe_unsupported_fallback() -> None:
    scope = _theme_scope()
    feature_font = _FeatureFont()
    widget = _Widget(feature_font)

    assert scope["apply_tabular_numerals"](widget) is True
    assert widget.properties["tabularNumerals"] is True
    assert feature_font.features[0][1] == 1
    assert feature_font.features[0][0] is not None
    assert scope["TABULAR_NUMERAL_FEATURE"] == "tnum"
    assert widget.applied_font is feature_font

    unsupported = _Widget(_NoFeatureFont())
    assert scope["apply_tabular_numerals"](unsupported) is False
    assert unsupported.properties["tabularNumerals"] is True
    assert unsupported.applied_font is None

    token = scope["apply_text_role"](
        widget,
        scope["TextRole"].NUMERIC_DISPLAY,
    )
    assert token.tabular_numerals is True
    assert widget.properties["textRole"] == "numeric-display"
    assert widget.properties["textLineHeight"] == token.line_height_px


def test_semantic_component_hooks_cover_shared_states_and_nursery_palette() -> None:
    scope = _theme_scope()
    garden = scope["semantic_component_stylesheet"]("garden")
    nursery = scope["semantic_component_stylesheet"]("nursery")

    for role in (
        "tabs",
        "segmented-filter",
        "badge",
        "progress",
        "disclosure",
        "tooltip",
        "banner",
        "toast",
        "empty-state",
        "missing-art",
    ):
        assert f"gardenRole='{role}'" in garden
    assert "min-height: 44px" in garden
    assert "QCheckBox:focus" in garden
    assert "QCheckBox::indicator:checked" in garden
    assert scope["GARDEN_THEME"]["raised_surface"] in garden
    assert scope["NURSERY_THEME"]["raised_surface"] in nursery
    assert scope["NURSERY_THEME"]["focus_ring"] in nursery
    assert scope["NURSERY_THEME"]["raised_surface"] not in garden
    nursery_foundation = scope["foundation_stylesheet"]("nursery")
    assert scope["NURSERY_THEME"]["action_accent"] in nursery_foundation
    assert scope["NURSERY_THEME"]["secondary_action"] in nursery_foundation

    widget = _Widget()
    role = scope["set_semantic_role"](
        widget,
        scope["SemanticRole"].BANNER,
        tone=scope["FeedbackTone"].WARNING,
    )
    assert role is scope["SemanticRole"].BANNER
    assert widget.properties["gardenRole"] == "banner"
    assert widget.properties["gardenTone"] == "warning"


def test_nursery_action_override_keeps_legible_contrast() -> None:
    scope = _theme_scope()
    palette = scope["NURSERY_THEME"]

    for background in ("action_accent", "action_hover", "action_pressed"):
        assert _contrast(palette["action_text"], palette[background]) >= 4.5


def test_foundation_stylesheet_composes_existing_and_opt_in_apis() -> None:
    scope = _theme_scope()
    stylesheet = scope["foundation_stylesheet"]()

    assert "QPushButton {" in stylesheet
    assert "QToolButton {" in stylesheet
    assert "*[textRole='screen-title']" in stylesheet
    assert "QFrame[gardenRole='empty-state']" in stylesheet


def test_release_surfaces_do_not_render_text_below_the_legibility_floor() -> None:
    offenders: list[str] = []
    pattern = re.compile(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px")
    for relative in (
        "ankigarden/ui/dashboard.py",
        "ankigarden/ui/garden_studio.py",
        "ankigarden/ui/home_widget.py",
        "ankigarden/ui/theme.py",
    ):
        source = (ROOT / relative).read_text("utf-8")
        for match in pattern.finditer(source):
            if float(match.group(1)) < 12.0:
                line = source.count("\n", 0, match.start()) + 1
                offenders.append(f"{relative}:{line}={match.group(1)}px")
    assert offenders == []


def test_dynamic_growth_coin_countdown_and_progress_values_use_tabular_numerals() -> None:
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")
    home = (ROOT / "ankigarden/ui/home_widget.py").read_text("utf-8")

    for call in (
        "apply_tabular_numerals(self.value_label)",
        "apply_tabular_numerals(self.status)",
        "apply_tabular_numerals(self.coins)",
        "apply_tabular_numerals(growth_support)",
        "apply_tabular_numerals(charge_quantity)",
        "apply_tabular_numerals(metric)",
        "apply_tabular_numerals(bonus_value)",
        "apply_tabular_numerals(cutoff_value)",
        "apply_tabular_numerals(milestone)",
        "apply_tabular_numerals(reward)",
        "apply_tabular_numerals(balance_value)",
        "apply_tabular_numerals(amount)",
        "apply_tabular_numerals(resulting)",
        "apply_tabular_numerals(current_status)",
        "apply_tabular_numerals(balance)",
        "apply_tabular_numerals(self.status_value)",
        "apply_tabular_numerals(affordability_label)",
        "apply_tabular_numerals(helper)",
        "apply_tabular_numerals(stage_reward_label)",
        "apply_tabular_numerals(streak_reward)",
        "apply_tabular_numerals(shortfall_label)",
    ):
        assert call in dashboard
    assert dashboard.count("apply_tabular_numerals(value)") >= 2
    assert dashboard.count("apply_tabular_numerals(meta)") >= 6
    assert dashboard.count("apply_tabular_numerals(title)") >= 3
    assert dashboard.count("apply_tabular_numerals(detail)") >= 2
    assert "apply_tabular_numerals(label)" in dashboard
    assert "font-variant-numeric:tabular-nums" in home


def test_release_focus_targets_and_checkbox_controls_use_shared_foundations() -> None:
    dashboard = (ROOT / "ankigarden/ui/dashboard.py").read_text("utf-8")

    # The only StrongFocus target without the non-button ring hook is the
    # Garden metric QPushButton, which already has its own focused selector.
    assert dashboard.count("setFocusPolicy(Qt.FocusPolicy.StrongFocus)") == (
        dashboard.count("set_keyboard_focus_surface(") + 1
    )
    assert "self.garden_name_edit.setFixedHeight(BUTTON_MIN_HEIGHT)" in dashboard
    assert 'show_weather = QCheckBox("Show Weather")' in dashboard
    assert 'show_scenery = QCheckBox("Show Scenery")' in dashboard
