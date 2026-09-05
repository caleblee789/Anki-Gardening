from __future__ import annotations

import ast
import runpy
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
        self.maximum_width = 16_777_215
        self.maximum_height = 16_777_215
        self.accessible_name = ""
        self.accessible_description = "Available action"
        self.tooltip = ""
        self._cursor: object | None = "pointing"
        self.cursor_events: list[object | None] = []
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

    def setMaximumHeight(self, height: int) -> None:
        self.maximum_height = height

    def setMinimumWidth(self, width: int) -> None:
        self.minimum_width = width

    def setMaximumWidth(self, width: int) -> None:
        self.maximum_width = width

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

    def cursor(self) -> object | None:
        return self._cursor

    def setCursor(self, cursor: object) -> None:
        self._cursor = cursor
        self.cursor_events.append(cursor)

    def unsetCursor(self) -> None:
        self._cursor = None
        self.cursor_events.append(None)

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
        "brand-eyebrow",
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
    assert 13 <= tokens[text_role.BUTTON_LABEL].font_size_px <= 14
    assert tokens[text_role.SECTION_HEADING].font_size_px <= 19
    assert all(token.font_weight <= 700 for token in tokens.values())
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
    assert values[-1] == 32
    assert scope["SPACING_SCALE"] == {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "dialog-body": 20,
        "xl": 24,
        "xxl": 32,
    }
    assert scope["spacing"]("md") == 12
    assert scope["spacing"](spacing_token.XL) == 24
    assert scope["spacing"]("display") == 32
    assert scope["spacing"]("dialog-body") == 20
    with pytest.raises(ValueError, match="outside the shared scale"):
        scope["spacing"](13)

    assert scope["GARDEN_COLOR_TOKENS"] is scope["SEMANTIC_COLORS"]
    assert scope["COLOR_TOKENS"] is scope["SEMANTIC_COLORS"]
    assert scope["RADIUS_SCALE"] == {"sm": 6, "md": 8, "lg": 12}
    assert scope["CONTROL_HEIGHT_SCALE"] == {
        "compact": 28,
        "default": 32,
        "primary": 32,
    }
    assert scope["PROGRESS_BAR_HEIGHT"] == 6
    assert len(set(scope["GREEN_SURFACE_LEVELS"])) == 4
    assert scope["SEMANTIC_COLORS"]["gold"] != scope["SEMANTIC_COLORS"]["warning"]
    assert scope["SEMANTIC_COLORS"]["rare"] not in {
        scope["SEMANTIC_COLORS"]["gold"],
        scope["SEMANTIC_COLORS"]["warning"],
    }
    expected_colors = {
        "bg": "#081C16",
        "surface_deep": "#0B1F1B",
        "surface_1": "#0D2A21",
        "surface_2": "#14382C",
        "surface_hover": "#164C3D",
        "primary": "#62D6A1",
        "primary_hover": "#75E4AE",
        "primary_pressed": "#4FC58C",
        "gold": "#E8C568",
        "warning_bg": "#44281C",
        "danger": "#DB8C83",
    }
    assert expected_colors.items() <= scope["SEMANTIC_COLORS"].items()


def test_plant_popover_palette_is_centralized_and_semantic() -> None:
    theme = _theme_scope()["GARDEN_THEME"]
    expected = {
        "plant_popover_bg",
        "plant_popover_raised",
        "plant_popover_border",
        "plant_popover_status_surface",
        "plant_popover_status_border",
        "plant_popover_status_text",
        "plant_popover_progress_track",
        "plant_popover_divider",
        "plant_popover_danger_surface",
        "plant_popover_danger_hover",
        "plant_popover_danger_pressed",
        "plant_popover_danger_border",
        "plant_popover_danger_text",
        "plant_popover_shadow",
    }

    assert expected <= theme.keys()
    assert theme["plant_popover_bg"] != theme["plant_popover_raised"]
    assert theme["plant_popover_status_surface"] != theme["action_accent"]
    assert theme["plant_popover_danger_surface"] != theme["danger"]


def test_control_variants_keep_legacy_tertiary_and_compact_desktop_targets() -> None:
    scope = _theme_scope()
    control_variant = scope["ControlVariant"]

    assert {variant.value for variant in control_variant} == {
        "primary",
        "secondary",
        "quiet",
        "destructive",
    }
    assert scope["BUTTON_VARIANT_TERTIARY"] == "tertiary"
    assert scope["MIN_HIT_TARGET"] == 28
    assert scope["BUTTON_MIN_HEIGHT"] == 28
    assert scope["PRIMARY_BUTTON_VISUAL_HEIGHT"] == 32
    assert scope["INPUT_VISUAL_HEIGHT"] == 32
    assert scope["ICON_BUTTON_VISUAL_SIZE"] == 28
    assert scope["ICON_BUTTON_SIZE"] == 28

    buttons = scope["button_stylesheet"]()
    tools = scope["tool_button_stylesheet"]()
    assert "QPushButton[variant='quiet']" in buttons
    assert "QPushButton[variant='tertiary']" in buttons
    assert "QPushButton[variant='destructive']" in buttons
    assert "QPushButton:disabled" in buttons
    assert "QPushButton:enabled:hover" in buttons
    assert "QPushButton:disabled:hover" in buttons
    assert "QPushButton[pending='true']" in buttons
    assert "QPushButton[keyboardFocusVisible='true']:focus" in buttons
    assert "font-size: 13px" in buttons
    assert f"border-color: {scope['GARDEN_THEME']['growth_accent']}" in buttons
    assert f"border-color: {scope['GARDEN_THEME']['focus_ring']}" in buttons
    assert "QPushButton[keyboardFocusVisible='true']:focus {\n            border-color:" in buttons
    assert "QToolButton[gardenRole='icon-button']" in tools
    assert "QToolButton:enabled:hover" in tools
    assert "QToolButton:disabled:hover" in tools
    assert "QToolButton[pending='true']" in tools
    assert "font-size: 13px" in tools


def test_button_size_tokens_are_exact_and_apply_without_forcing_width() -> None:
    scope = _theme_scope()
    button_size = scope["ButtonSize"]
    tokens = scope["BUTTON_SIZE_TOKENS"]

    assert {
        size.value: (tokens[size].height_px, tokens[size].horizontal_padding_px)
        for size in button_size
    } == {
        "compact-row": (28, 10),
        "banner": (32, 10),
        "secondary": (32, 12),
        "primary": (32, 12),
        "onboarding": (32, 12),
        "icon": (28, 0),
    }
    widget = _Widget()
    token = scope["apply_button_size"](widget, "onboarding")
    assert token is tokens[button_size.ONBOARDING]
    assert widget.properties["buttonSize"] == "onboarding"
    assert widget.properties["visualControlSize"] == 32
    assert (widget.minimum_height, widget.maximum_height) == (32, 32)
    assert (widget.minimum_width, widget.maximum_width) == (0, 16_777_215)

    scope["apply_button_size"](widget, button_size.ICON)
    assert (widget.minimum_width, widget.maximum_width) == (28, 28)


def test_capture_button_calibration_matches_release_button_tokens() -> None:
    scope = _theme_scope()
    button_size = scope["ButtonSize"]
    tokens = scope["BUTTON_SIZE_TOKENS"]
    runtime_tree = ast.parse(
        (ROOT / "ankigarden/capture/runtime.py").read_text(encoding="utf-8")
    )
    capture_heights = next(
        ast.literal_eval(node.value)
        for node in runtime_tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "CAPTURE_BUTTON_HEIGHTS"
    )

    assert capture_heights == {
        size.value: tokens[size].height_px for size in button_size
    }


def test_non_button_geometry_tokens_apply_inputs_selects_switches_and_tabs() -> None:
    scope = _theme_scope()
    geometry = scope["ControlGeometry"]
    tokens = scope["CONTROL_GEOMETRY_TOKENS"]

    assert {
        role.value: (tokens[role].width_px, tokens[role].height_px)
        for role in geometry
    } == {
        "icon-button": (28, 28),
        "input": (None, 32),
        "select": (None, 32),
        "switch": (38, 22),
        "tab": (None, 34),
    }

    input_widget = _Widget()
    scope["apply_input_geometry"](input_widget)
    assert (input_widget.minimum_height, input_widget.maximum_height) == (32, 32)
    assert input_widget.properties["gardenControl"] == "input"

    switch = _Widget()
    scope["apply_switch_geometry"](switch)
    assert (switch.minimum_width, switch.maximum_width) == (38, 38)
    assert (switch.minimum_height, switch.maximum_height) == (22, 22)


def test_shared_scrollbars_paint_no_native_corner_or_line_controls() -> None:
    stylesheet = _theme_scope()["semantic_component_stylesheet"]()

    assert "QAbstractScrollArea::corner" in stylesheet
    assert "QScrollBar:vertical" in stylesheet
    assert "width: 6px" in stylesheet
    assert "QScrollBar::add-line:vertical" in stylesheet
    assert "QScrollBar::sub-line:vertical" in stylesheet
    assert "height: 0" in stylesheet


def test_shared_toggle_widget_paints_track_thumb_and_enabled_state() -> None:
    source = (ROOT / "ankigarden/ui/controls.py").read_text(encoding="utf-8")

    assert "class GardenToggleSwitch(QCheckBox)" in source
    assert "painter.drawRoundedRect" in source
    assert "painter.drawEllipse" in source
    assert '"on" if checked else "off"' in source
    assert "QEvent.Type.EnabledChange" in source
    assert 'GARDEN_THEME["action_text"]\n        if checked' not in source
    assert 'setProperty("switchThumbTone", "light")' in source


def test_semantic_colors_sentence_case_and_status_chips_have_one_authority() -> None:
    scope = _theme_scope()
    role = scope["SemanticColorRole"]
    colors = scope["SEMANTIC_COLORS"]

    assert scope["semantic_color"](role.PRIMARY_ACTION) == colors["primary"]
    assert scope["semantic_color"]("coin") == colors["gold"]
    assert scope["semantic_color"]("warning") == colors["warning"]
    assert scope["semantic_color"]("destructive") == colors["danger"]
    assert scope["semantic_color"]("full-bloom") == colors["rare"]
    assert scope["semantic_color"]("stage") == colors["surface_2"]
    assert scope["sentence_case_label"](
        "garden decorations and scenery"
    ) == "Garden decorations and scenery"

    widget = _Widget()
    tone = scope["apply_status_chip"](widget, "rare")
    assert tone is scope["StatusChipTone"].RARE
    assert widget.properties["gardenRole"] == "status-badge"
    assert widget.properties["statusTone"] == "rare"
    assert widget.properties["statusInteractive"] is False
    assert widget.properties["statusShadow"] is False
    assert (widget.minimum_height, widget.maximum_height) == (20, 22)

    stylesheet = scope["semantic_component_stylesheet"]()
    assert "QLabel[gardenRole='status-badge'][statusTone='rare']" in stylesheet


def test_control_helpers_apply_variant_and_restore_disabled_description() -> None:
    scope = _theme_scope()
    widget = _Widget()

    normalized = scope["apply_control_variant"](widget, "tertiary")
    assert normalized is scope["ControlVariant"].QUIET
    assert widget.properties["variant"] == "quiet"
    assert (widget.minimum_width, widget.minimum_height) == (28, 28)

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
    assert widget.properties["controlCursor"] == "forbidden"
    assert widget._cursor != "pointing"

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
    assert widget.properties["controlCursor"] == "restored"
    assert widget._cursor == "pointing"
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
    assert (widget.minimum_width, widget.minimum_height) == (28, 28)


def test_non_button_focus_surface_uses_the_shared_visible_ring_hook() -> None:
    scope = _theme_scope()
    widget = _Widget()

    assert scope["set_keyboard_focus_surface"](widget) is widget
    assert widget.properties["keyboardFocusSurface"] is True
    assert ("polish", widget) in widget._style.events

    stylesheet = scope["semantic_component_stylesheet"]()
    assert "QFrame[keyboardFocusSurface='true'][keyboardFocusVisible='true']:focus" in stylesheet
    assert "QLabel[keyboardFocusSurface='true'][keyboardFocusVisible='true']:focus" in stylesheet
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




def test_action_palettes_keep_legible_contrast_in_every_interaction_state() -> None:
    scope = _theme_scope()
    garden = scope["GARDEN_THEME"]
    nursery = scope["NURSERY_THEME"]
    combinations = (
        *((garden["action_text"], garden[key]) for key in (
            "action_accent",
            "action_hover",
            "action_pressed",
        )),
        *((garden["text_primary"], garden[key]) for key in (
            "secondary_action",
            "secondary_hover",
            "secondary_pressed",
        )),
        (garden["disabled_text"], garden["disabled_surface"]),
        *((nursery["action_text"], nursery[key]) for key in (
            "action_accent",
            "action_hover",
            "action_pressed",
        )),
    )

    assert all(_contrast(foreground, background) >= 4.5 for foreground, background in combinations)


def test_foundation_stylesheet_composes_existing_and_opt_in_apis() -> None:
    scope = _theme_scope()
    stylesheet = scope["foundation_stylesheet"]()

    assert "QPushButton {" in stylesheet
    assert "QToolButton {" in stylesheet
    assert "*[textRole='screen-title']" in stylesheet
    assert "QFrame[gardenRole='empty-state']" in stylesheet
