from __future__ import annotations

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
        *((garden[role], garden[surface])
          for role in ("text_primary", "text_secondary", "text_muted")
          for surface in ("dialog_surface", "raised_surface", "selected_surface",
                          "surface_hover", "shop_surface_1", "shop_surface_2")),
        (garden["disabled_text"], garden["disabled_surface"]),
        *((nursery["action_text"], nursery[key]) for key in (
            "action_accent",
            "action_hover",
            "action_pressed",
        )),
    )

    assert all(_contrast(foreground, background) >= 4.5 for foreground, background in combinations)


def test_text_declarations_preserve_inherited_properties() -> None:
    scope = _theme_scope()
    role = scope["TextRole"].BODY
    scope["TEXT_ROLE_TOKENS"][role] = scope["TypographyToken"](17, 40, 500, 1.5)

    assert scope["text_style"](role) == "font-size:17px;font-weight:500;"
    assert scope["text_style"](role, include_weight=False) == "font-size:17px;"


def test_legacy_palette_binding_preserves_order_and_case_behavior() -> None:
    scope = _theme_scope()
    assert scope["bind_palette_colors"](
        "color:#AABBCC; background:#aabbcc; border-color:#AaBbCc;",
        (("#AABBCC", "first"), ("#112233", "second")),
        {"first": "#112233", "second": "#445566"},
    ) == "color:#445566; background:#445566; border-color:#AaBbCc;"
