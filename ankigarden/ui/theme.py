"""Shared visual and semantic tokens for Anki Garden's native Qt interfaces.

The Home card has a separate WebView stylesheet, but it intentionally mirrors
these action and focus colors. This module does not import Qt at module load
time: release tooling and source-contract tests must be able to inspect the
tokens without an Anki runtime. The small widget helpers therefore use the
stable QWidget/QFont method surface through duck typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any


MIN_LEGIBLE_TEXT_SIZE = 12
MIN_BODY_TEXT_SIZE = 14


class TextRole(str, Enum):
    """Product typography roles shared by native Garden surfaces."""

    BRAND_EYEBROW = "brand-eyebrow"
    DISPLAY_TITLE = "display-title"
    SCREEN_TITLE = "screen-title"
    SECTION_HEADING = "section-heading"
    CARD_TITLE = "card-title"
    BODY = "body"
    SECONDARY = "secondary"
    METADATA = "metadata"
    BADGE = "badge"
    NUMERIC_DISPLAY = "numeric-display"
    BUTTON_LABEL = "button-label"

    # Readable aliases retain one source of truth for each token.
    BODY_TEXT = "body"
    SECONDARY_TEXT = "secondary"
    BADGE_TEXT = "badge"


@dataclass(frozen=True)
class TypographyToken:
    """Pixel-based text metrics suitable for Qt's high-DPI scaling model."""

    font_size_px: int
    line_height_px: int
    font_weight: int
    letter_spacing_px: float = 0.0
    tabular_numerals: bool = False

    def __post_init__(self) -> None:
        if self.font_size_px < MIN_LEGIBLE_TEXT_SIZE:
            raise ValueError("text tokens may not be smaller than the legible minimum")
        if self.line_height_px < self.font_size_px:
            raise ValueError("text token line height may not be smaller than its font")


# Labels, metadata, badges, and actions stay at 12 px or larger. Body and
# action copy have intentionally larger defaults so platform font substitution
# does not force them below a practical reading size.
TEXT_ROLE_TOKENS: dict[TextRole, TypographyToken] = {
    TextRole.BRAND_EYEBROW: TypographyToken(12, 17, 600, 0.8),
    TextRole.DISPLAY_TITLE: TypographyToken(32, 40, 800, -0.2),
    TextRole.SCREEN_TITLE: TypographyToken(24, 32, 700, -0.1),
    TextRole.SECTION_HEADING: TypographyToken(20, 28, 700),
    TextRole.CARD_TITLE: TypographyToken(16, 23, 700),
    TextRole.BODY: TypographyToken(14, 21, 400),
    TextRole.SECONDARY: TypographyToken(13, 19, 400),
    TextRole.METADATA: TypographyToken(12, 17, 600, 0.1),
    TextRole.BADGE: TypographyToken(12, 17, 700, 0.3),
    TextRole.NUMERIC_DISPLAY: TypographyToken(28, 34, 800, tabular_numerals=True),
    TextRole.BUTTON_LABEL: TypographyToken(14, 20, 600),
}

# Public compatibility/readability aliases. All three names reference the same
# dictionary rather than creating divergent typography sources.
TYPOGRAPHY_SCALE = TEXT_ROLE_TOKENS
TEXT_STYLES = TEXT_ROLE_TOKENS
TextStyle = TypographyToken


class SpacingToken(IntEnum):
    """A compact spacing scale that supports dense and roomy surfaces."""

    NONE = 0
    HAIRLINE = 2
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    XXXL = 40
    DISPLAY = 48


Spacing = SpacingToken
SPACING_SCALE: dict[str, int] = {
    token.name.lower(): int(token) for token in SpacingToken
}


class ControlVariant(str, Enum):
    """Shared visual priority for actionable controls."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    QUIET = "quiet"
    DESTRUCTIVE = "destructive"


class ButtonSize(str, Enum):
    """Shared native button geometry independent of visual priority."""

    COMPACT_ROW = "compact-row"
    SECONDARY = "secondary"
    PRIMARY = "primary"
    ONBOARDING = "onboarding"
    ICON = "icon"


@dataclass(frozen=True)
class ButtonSizeToken:
    height_px: int
    horizontal_padding_px: int
    square: bool = False

    def __post_init__(self) -> None:
        if self.height_px <= 0 or self.horizontal_padding_px < 0:
            raise ValueError("button size tokens must use positive geometry")


BUTTON_VARIANT_PRIMARY = ControlVariant.PRIMARY.value
BUTTON_VARIANT_SECONDARY = ControlVariant.SECONDARY.value
BUTTON_VARIANT_QUIET = ControlVariant.QUIET.value
BUTTON_VARIANT_DESTRUCTIVE = ControlVariant.DESTRUCTIVE.value

# Existing surfaces use ``tertiary``. Keep its value and selector stable while
# new work uses the clearer quiet role.
BUTTON_VARIANT_TERTIARY = "tertiary"

# Desktop controls intentionally remain compact. Keyboard focus, tooltips, and
# generous row spacing carry the accessibility affordance without turning the
# interface into a touch-sized control system.
MIN_HIT_TARGET = 34
CONTROL_MIN_HIT_TARGET = MIN_HIT_TARGET
BUTTON_MIN_HEIGHT = MIN_HIT_TARGET
BUTTON_VISUAL_HEIGHT = 34
PRIMARY_BUTTON_VISUAL_HEIGHT = 36
COMPACT_BUTTON_HEIGHT = 30
ONBOARDING_BUTTON_VISUAL_HEIGHT = 38
ICON_BUTTON_VISUAL_SIZE = 30
INPUT_VISUAL_HEIGHT = 36
TAB_VISUAL_HEIGHT = 38
TOGGLE_VISUAL_WIDTH = 36
TOGGLE_VISUAL_HEIGHT = 20
PLANT_ACTION_MIN_HEIGHT = MIN_HIT_TARGET
ICON_BUTTON_SIZE = ICON_BUTTON_VISUAL_SIZE
SCENE_HELP_BUTTON_SIZE = ICON_BUTTON_VISUAL_SIZE

BUTTON_SIZE_TOKENS: dict[ButtonSize, ButtonSizeToken] = {
    ButtonSize.COMPACT_ROW: ButtonSizeToken(COMPACT_BUTTON_HEIGHT, 10),
    ButtonSize.SECONDARY: ButtonSizeToken(BUTTON_VISUAL_HEIGHT, 14),
    ButtonSize.PRIMARY: ButtonSizeToken(PRIMARY_BUTTON_VISUAL_HEIGHT, 16),
    ButtonSize.ONBOARDING: ButtonSizeToken(ONBOARDING_BUTTON_VISUAL_HEIGHT, 16),
    ButtonSize.ICON: ButtonSizeToken(ICON_BUTTON_VISUAL_SIZE, 0, square=True),
}


class ThemeContext(str, Enum):
    GARDEN = "garden"
    NURSERY = "nursery"


SEMANTIC_COLORS = {
    "bg": "#071B14",
    "surface_1": "#0E2A20",
    "surface_2": "#14372A",
    "surface_3": "#1A4434",
    "text_primary": "#F2F5EC",
    "text_secondary": "#C7D2C9",
    "text_muted": "#95A99C",
    "primary": "#62D49A",
    "primary_hover": "#79E2AA",
    "primary_pressed": "#48B77F",
    "gold": "#E2B85F",
    "danger": "#D96570",
    "warning": "#D2A54F",
    "info": "#6BA8CC",
    "shop_surface_1": "#2A1E18",
    "shop_surface_2": "#3A291F",
    "shop_surface_3": "#493328",
}


GARDEN_THEME = {
    "garden_background": SEMANTIC_COLORS["bg"],
    "dialog_surface": SEMANTIC_COLORS["surface_1"],
    "raised_surface": SEMANTIC_COLORS["surface_2"],
    "selected_surface": SEMANTIC_COLORS["surface_3"],
    "subtle_border": "rgba(128, 178, 155, 0.22)",
    "strong_border": "#4F806E",
    "text_primary": SEMANTIC_COLORS["text_primary"],
    "text_secondary": SEMANTIC_COLORS["text_secondary"],
    "text_muted": SEMANTIC_COLORS["text_muted"],
    "action_accent": SEMANTIC_COLORS["primary"],
    "action_hover": SEMANTIC_COLORS["primary_hover"],
    "action_pressed": SEMANTIC_COLORS["primary_pressed"],
    "action_text": "#062017",
    "action_border": SEMANTIC_COLORS["primary"],
    "secondary_action": SEMANTIC_COLORS["surface_2"],
    "secondary_hover": SEMANTIC_COLORS["surface_3"],
    "secondary_pressed": SEMANTIC_COLORS["surface_1"],
    "secondary_border": "#4F806E",
    "disabled_surface": "#173029",
    "disabled_border": "#3F5C50",
    "disabled_text": "#A6B6AE",
    "growth_accent": SEMANTIC_COLORS["primary"],
    "coin_accent": SEMANTIC_COLORS["gold"],
    "success": SEMANTIC_COLORS["primary"],
    "warning": SEMANTIC_COLORS["warning"],
    "error": SEMANTIC_COLORS["danger"],
    "danger": SEMANTIC_COLORS["danger"],
    "info": SEMANTIC_COLORS["info"],
    "focus_ring": SEMANTIC_COLORS["primary_hover"],
    "shop_surface_1": SEMANTIC_COLORS["shop_surface_1"],
    "shop_surface_2": SEMANTIC_COLORS["shop_surface_2"],
    "shop_surface_3": SEMANTIC_COLORS["shop_surface_3"],
}

# Brown identifies Nursery catalogue content; the shell and controls remain on
# the shared green product palette.
NURSERY_THEME_OVERRIDES = {
    "shop_surface_1": SEMANTIC_COLORS["shop_surface_1"],
    "shop_surface_2": SEMANTIC_COLORS["shop_surface_2"],
    "shop_surface_3": SEMANTIC_COLORS["shop_surface_3"],
}
NURSERY_THEME = {**GARDEN_THEME, **NURSERY_THEME_OVERRIDES}


class SemanticRole(str, Enum):
    """Dynamic-property hooks for components that can be adopted gradually."""

    ICON_BUTTON = "icon-button"
    TABS = "tabs"
    SEGMENTED_FILTER = "segmented-filter"
    BADGE = "badge"
    PROGRESS = "progress"
    DISCLOSURE = "disclosure"
    TOOLTIP = "tooltip"
    BANNER = "banner"
    TOAST = "toast"
    EMPTY_STATE = "empty-state"
    MISSING_ART = "missing-art"

    FILTERS = "segmented-filter"
    MISSING_ART_STATE = "missing-art"


class FeedbackTone(str, Enum):
    NEUTRAL = "neutral"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


TEXT_ROLE_PROPERTY = "textRole"
CONTROL_VARIANT_PROPERTY = "variant"
SEMANTIC_ROLE_PROPERTY = "gardenRole"
SEMANTIC_TONE_PROPERTY = "gardenTone"
DISABLED_STATE_PROPERTY = "gardenDisabled"
DISABLED_REASON_PROPERTY = "disabledReason"
TABULAR_NUMERALS_PROPERTY = "tabularNumerals"
KEYBOARD_FOCUS_SURFACE_PROPERTY = "keyboardFocusSurface"
TABULAR_NUMERAL_FEATURE = "tnum"
TABULAR_NUMERAL_CSS = "font-variant-numeric: tabular-nums;"
_ENABLED_DESCRIPTION_PROPERTY = "gardenEnabledDescription"


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value).strip()


def _required_text(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} must be nonempty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must be nonempty")
    return text


def _set_property(widget: Any, name: str, value: Any) -> None:
    setter = getattr(widget, "setProperty", None)
    if not callable(setter):
        raise TypeError("semantic styling requires a Qt-style setProperty method")
    setter(name, value)


def _read_property(widget: Any, name: str) -> Any:
    getter = getattr(widget, "property", None)
    if not callable(getter):
        return None
    try:
        return getter(name)
    except Exception:
        return None


def _repolish(widget: Any) -> None:
    """Refresh QSS after a dynamic property change, if a style is available."""

    style_getter = getattr(widget, "style", None)
    if not callable(style_getter):
        return
    try:
        style = style_getter()
        if style is None:
            return
        unpolish = getattr(style, "unpolish", None)
        polish = getattr(style, "polish", None)
        if callable(unpolish):
            unpolish(widget)
        if callable(polish):
            polish(widget)
    except Exception:
        # A semantic helper must never make a control unusable because a
        # platform style cannot be refreshed at that instant.
        return


def theme_palette(context: ThemeContext | str = ThemeContext.GARDEN) -> dict[str, str]:
    """Return an isolated palette for the shared Garden or Nursery context."""

    value = _enum_value(context).lower()
    if value == ThemeContext.GARDEN.value:
        return dict(GARDEN_THEME)
    if value == ThemeContext.NURSERY.value:
        return dict(NURSERY_THEME)
    raise ValueError(f"unknown theme context: {context!r}")


def text_token(role: TextRole | str) -> TypographyToken:
    """Resolve one typography role while accepting serialized role values."""

    try:
        normalized = role if isinstance(role, TextRole) else TextRole(str(role))
    except ValueError as error:
        raise ValueError(f"unknown text role: {role!r}") from error
    return TEXT_ROLE_TOKENS[normalized]


def spacing(token: SpacingToken | str | int) -> int:
    """Resolve a named spacing token or validate an explicit scale value."""

    if isinstance(token, SpacingToken):
        return int(token)
    if isinstance(token, str):
        key = token.strip().lower()
        if key in SPACING_SCALE:
            return SPACING_SCALE[key]
        raise ValueError(f"unknown spacing token: {token!r}")
    value = int(token)
    if value not in SPACING_SCALE.values():
        raise ValueError(f"spacing value is outside the shared scale: {value}")
    return value


def apply_text_role(widget: Any, role: TextRole | str) -> TypographyToken:
    """Attach a text role and its minimum line metric to a Qt-like widget."""

    normalized = role if isinstance(role, TextRole) else TextRole(str(role))
    token = text_token(normalized)
    _set_property(widget, TEXT_ROLE_PROPERTY, normalized.value)
    _set_property(widget, "textLineHeight", token.line_height_px)

    minimum_height = getattr(widget, "minimumHeight", None)
    set_minimum_height = getattr(widget, "setMinimumHeight", None)
    if callable(set_minimum_height):
        current = 0
        if callable(minimum_height):
            try:
                current = int(minimum_height())
            except Exception:
                current = 0
        set_minimum_height(max(current, token.line_height_px))

    if token.tabular_numerals:
        apply_tabular_numerals(widget)
    _repolish(widget)
    return token


def _coerce_control_variant(variant: ControlVariant | str) -> ControlVariant:
    value = _enum_value(variant).lower()
    if value == BUTTON_VARIANT_TERTIARY:
        value = ControlVariant.QUIET.value
    try:
        return ControlVariant(value)
    except ValueError as error:
        raise ValueError(f"unknown control variant: {variant!r}") from error


def ensure_minimum_hit_target(
    widget: Any,
    *,
    width: int = MIN_HIT_TARGET,
    height: int = MIN_HIT_TARGET,
) -> Any:
    """Ensure a practical target without reducing a larger existing minimum."""

    requested_width = max(MIN_HIT_TARGET, int(width))
    requested_height = max(MIN_HIT_TARGET, int(height))

    def current_dimension(name: str) -> int:
        getter = getattr(widget, name, None)
        if not callable(getter):
            return 0
        try:
            return int(getter())
        except Exception:
            return 0

    target_width = max(current_dimension("minimumWidth"), requested_width)
    target_height = max(current_dimension("minimumHeight"), requested_height)
    set_minimum_size = getattr(widget, "setMinimumSize", None)
    if callable(set_minimum_size):
        try:
            set_minimum_size(target_width, target_height)
            return widget
        except TypeError:
            # Some test doubles and binding versions expose only the separate
            # width/height setters.
            pass

    width_setter = getattr(widget, "setMinimumWidth", None)
    height_setter = getattr(widget, "setMinimumHeight", None)
    if not callable(width_setter) or not callable(height_setter):
        raise TypeError("hit-target sizing requires Qt-style minimum-size methods")
    width_setter(target_width)
    height_setter(target_height)
    return widget


def apply_control_variant(widget: Any, variant: ControlVariant | str) -> ControlVariant:
    """Apply one shared control priority and refresh its dynamic QSS state."""

    normalized = _coerce_control_variant(variant)
    _set_property(widget, CONTROL_VARIANT_PROPERTY, normalized.value)
    _set_property(widget, "controlVariant", normalized.value)
    ensure_minimum_hit_target(widget)
    _repolish(widget)
    return normalized


set_control_variant = apply_control_variant


def apply_button_size(widget: Any, size: ButtonSize | str) -> ButtonSizeToken:
    """Apply one exact visual-height token to a Qt-like button.

    Horizontal sizing deliberately remains content-driven. The native shell
    assigns a non-expanding size policy, while this dependency-light helper
    supplies geometry and capture-visible properties without importing Qt.
    """

    try:
        normalized = size if isinstance(size, ButtonSize) else ButtonSize(str(size))
    except ValueError as error:
        raise ValueError(f"unknown button size: {size!r}") from error
    token = BUTTON_SIZE_TOKENS[normalized]
    _set_property(widget, "buttonSize", normalized.value)
    _set_property(widget, "visualControlSize", token.height_px)
    _set_property(widget, "horizontalPadding", token.horizontal_padding_px)

    minimum_height = getattr(widget, "setMinimumHeight", None)
    maximum_height = getattr(widget, "setMaximumHeight", None)
    if callable(minimum_height):
        minimum_height(token.height_px)
    if callable(maximum_height):
        maximum_height(token.height_px)
    if token.square:
        minimum_width = getattr(widget, "setMinimumWidth", None)
        maximum_width = getattr(widget, "setMaximumWidth", None)
        if callable(minimum_width):
            minimum_width(token.height_px)
        if callable(maximum_width):
            maximum_width(token.height_px)
    _repolish(widget)
    return token


def set_control_enabled(
    widget: Any,
    enabled: bool,
    *,
    disabled_reason: str | None = None,
    enabled_description: str | None = None,
) -> Any:
    """Set native enabled state and expose a color-independent reason.

    A disabled call requires a reason so assistive technology is not left with
    an unexplained unavailable action. The prior enabled description is saved
    once and restored when the control is re-enabled, making repeated state
    refreshes idempotent.
    """

    set_enabled = getattr(widget, "setEnabled", None)
    if not callable(set_enabled):
        raise TypeError("disabled semantics require a Qt-style setEnabled method")

    is_enabled = bool(enabled)
    reason = ""
    if not is_enabled:
        reason = _required_text(disabled_reason, "disabled_reason")

    description_getter = getattr(widget, "accessibleDescription", None)
    description_setter = getattr(widget, "setAccessibleDescription", None)
    was_disabled = _read_property(widget, DISABLED_STATE_PROPERTY) is True

    if enabled_description is not None:
        _set_property(
            widget,
            _ENABLED_DESCRIPTION_PROPERTY,
            str(enabled_description).strip(),
        )
    elif not is_enabled and not was_disabled:
        original = ""
        if callable(description_getter):
            try:
                original = str(description_getter())
            except Exception:
                original = ""
        _set_property(widget, _ENABLED_DESCRIPTION_PROPERTY, original)

    set_enabled(is_enabled)
    _set_property(widget, DISABLED_STATE_PROPERTY, not is_enabled)
    _set_property(widget, DISABLED_REASON_PROPERTY, reason)

    if callable(description_setter):
        if is_enabled:
            restored = (
                str(enabled_description).strip()
                if enabled_description is not None
                else _read_property(widget, _ENABLED_DESCRIPTION_PROPERTY)
            )
            if restored is not None:
                description_setter(str(restored))
        else:
            description_setter(reason)
    _repolish(widget)
    return widget


def set_disabled_semantics(
    widget: Any,
    disabled: bool,
    *,
    reason: str | None = None,
    enabled_description: str | None = None,
) -> Any:
    """Disabled-oriented alias for :func:`set_control_enabled`."""

    return set_control_enabled(
        widget,
        not bool(disabled),
        disabled_reason=reason,
        enabled_description=enabled_description,
    )


def set_keyboard_focus_surface(widget: Any) -> Any:
    """Opt a non-button focus target into the shared visible focus ring."""

    if not callable(getattr(widget, "setProperty", None)):
        raise TypeError("focus-surface styling requires a Qt-style setProperty method")
    _set_property(widget, KEYBOARD_FOCUS_SURFACE_PROPERTY, True)
    _repolish(widget)
    return widget


def set_icon_accessible_name(
    widget: Any,
    accessible_name: str,
    *,
    accessible_description: str | None = None,
    tooltip: str | None = None,
    ensure_hit_target: bool = True,
) -> Any:
    """Name an icon/glyph control without accepting the glyph as its name."""

    name = _required_text(accessible_name, "accessible_name")
    if not any(character.isalnum() for character in name):
        raise ValueError("accessible_name must describe the icon rather than repeat its glyph")
    name_setter = getattr(widget, "setAccessibleName", None)
    if not callable(name_setter):
        raise TypeError("icon naming requires a Qt-style setAccessibleName method")
    name_setter(name)

    if accessible_description is not None:
        description_setter = getattr(widget, "setAccessibleDescription", None)
        if callable(description_setter):
            description_setter(str(accessible_description).strip())
    if tooltip is not None:
        tooltip_setter = getattr(widget, "setToolTip", None)
        if callable(tooltip_setter):
            tooltip_setter(str(tooltip).strip())

    _set_property(widget, "iconButton", True)
    _set_property(widget, SEMANTIC_ROLE_PROPERTY, SemanticRole.ICON_BUTTON.value)
    if ensure_hit_target:
        ensure_minimum_hit_target(widget)
    _repolish(widget)
    return widget


def _qt_font_feature_tag(feature: str) -> Any | None:
    """Build a QFont.Tag when the running Qt version exposes OpenType tags."""

    try:
        from aqt.qt import QFont  # type: ignore[import-not-found]

        tag_type = getattr(QFont, "Tag", None)
        from_string = getattr(tag_type, "fromString", None)
        if callable(from_string):
            return from_string(feature)
    except Exception:
        return None
    return None


def apply_tabular_numerals(target: Any) -> bool:
    """Enable the OpenType ``tnum`` feature when supported.

    Qt versions before QFont feature control, fonts without the feature, and
    source-only test environments safely retain their original font. The
    dynamic property is still attached when possible so HTML/custom renderers
    and diagnostics can observe the requested numeric role.
    """

    property_target = target
    if callable(getattr(property_target, "setProperty", None)):
        _set_property(property_target, TABULAR_NUMERALS_PROPERTY, True)

    font_getter = getattr(target, "font", None)
    font = target
    is_widget = callable(font_getter)
    if is_widget:
        try:
            font = font_getter()
        except Exception:
            return False

    set_feature = getattr(font, "setFeature", None)
    if not callable(set_feature):
        return False

    candidates: list[Any] = []
    qt_tag = _qt_font_feature_tag(TABULAR_NUMERAL_FEATURE)
    if qt_tag is not None:
        candidates.append(qt_tag)
    # Strings support lightweight test doubles and future binding overloads;
    # unsupported signatures are caught without altering the font.
    candidates.extend((TABULAR_NUMERAL_FEATURE, TABULAR_NUMERAL_FEATURE.encode("ascii")))

    applied = False
    for candidate in candidates:
        try:
            set_feature(candidate, 1)
            applied = True
            break
        except Exception:
            continue
    if not applied:
        return False

    if is_widget:
        font_setter = getattr(target, "setFont", None)
        if callable(font_setter):
            try:
                font_setter(font)
            except Exception:
                return False
    return True


enable_tabular_numerals = apply_tabular_numerals


def set_semantic_role(
    widget: Any,
    role: SemanticRole | str,
    *,
    tone: FeedbackTone | str | None = None,
) -> SemanticRole:
    """Attach reusable component/tone hooks without owning feature content."""

    try:
        normalized = role if isinstance(role, SemanticRole) else SemanticRole(str(role))
    except ValueError as error:
        raise ValueError(f"unknown semantic role: {role!r}") from error
    _set_property(widget, SEMANTIC_ROLE_PROPERTY, normalized.value)
    if tone is None:
        _set_property(widget, SEMANTIC_TONE_PROPERTY, FeedbackTone.NEUTRAL.value)
    else:
        try:
            normalized_tone = (
                tone if isinstance(tone, FeedbackTone) else FeedbackTone(str(tone))
            )
        except ValueError as error:
            raise ValueError(f"unknown feedback tone: {tone!r}") from error
        _set_property(widget, SEMANTIC_TONE_PROPERTY, normalized_tone.value)
    _repolish(widget)
    return normalized


apply_semantic_role = set_semantic_role


def button_stylesheet(
    context: ThemeContext | str = ThemeContext.GARDEN,
) -> str:
    """Return the complete text-button contract, including safe defaults."""

    t = theme_palette(context)
    hover_border = "#5b836f"
    pressed_border = "#6d9581"
    primary_pressed_border = "#86bc91"
    return f"""
        QPushButton {{
            min-height: {BUTTON_MIN_HEIGHT}px;
            max-height: {BUTTON_VISUAL_HEIGHT}px;
            padding: 0 14px;
            border: 1px solid {t['secondary_border']};
            border-radius: 8px;
            background: {t['secondary_action']};
            color: {t['text_primary']};
            font-size: 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {t['secondary_hover']};
            border-color: {hover_border};
        }}
        QPushButton:pressed {{
            background: {t['secondary_pressed']};
            border-color: {pressed_border};
        }}
        QPushButton[variant='primary'] {{
            min-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            max-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            background: {t['action_accent']};
            border-color: {t['action_border']};
            color: {t['action_text']};
        }}
        QPushButton[variant='primary']:hover {{ background: {t['action_hover']}; }}
        QPushButton[variant='primary']:pressed {{
            background: {t['action_pressed']};
            border-color: {primary_pressed_border};
        }}
        QPushButton[variant='secondary'] {{
            background: {t['secondary_action']};
            border-color: {t['secondary_border']};
            color: {t['text_primary']};
        }}
        QPushButton[variant='secondary']:hover {{ background: {t['secondary_hover']}; }}
        QPushButton[variant='secondary']:pressed {{
            background: {t['secondary_pressed']};
            border-color: {pressed_border};
        }}
        QPushButton[variant='quiet'], QPushButton[variant='tertiary'] {{
            background: transparent;
            border-color: transparent;
            color: {t['text_secondary']};
        }}
        QPushButton[variant='quiet']:hover, QPushButton[variant='tertiary']:hover {{
            background: {t['secondary_hover']};
            border-color: {t['subtle_border']};
            color: {t['text_primary']};
        }}
        QPushButton[variant='destructive'] {{
            background: #6d2d2d;
            border-color: #a44a4a;
            color: #ffecec;
        }}
        QPushButton[variant='destructive']:hover {{ background: #7b3434; }}
        QPushButton[variant='destructive']:pressed {{ background: #562424; }}
        QPushButton[compactRowAction='true'] {{
            min-height: {COMPACT_BUTTON_HEIGHT}px;
            max-height: {COMPACT_BUTTON_HEIGHT}px;
            padding: 0 10px;
        }}
        QPushButton[buttonSize='compact-row'] {{
            min-height: {COMPACT_BUTTON_HEIGHT}px;
            max-height: {COMPACT_BUTTON_HEIGHT}px;
            padding: 0 10px;
        }}
        QPushButton[buttonSize='secondary'] {{
            min-height: {BUTTON_VISUAL_HEIGHT}px;
            max-height: {BUTTON_VISUAL_HEIGHT}px;
            padding: 0 14px;
        }}
        QPushButton[buttonSize='primary'] {{
            min-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            max-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            padding: 0 16px;
        }}
        QPushButton[buttonSize='onboarding'] {{
            min-height: {ONBOARDING_BUTTON_VISUAL_HEIGHT}px;
            max-height: {ONBOARDING_BUTTON_VISUAL_HEIGHT}px;
            padding: 0 16px;
        }}
        QPushButton[buttonSize='icon'] {{
            min-width: {ICON_BUTTON_VISUAL_SIZE}px;
            max-width: {ICON_BUTTON_VISUAL_SIZE}px;
            min-height: {ICON_BUTTON_VISUAL_SIZE}px;
            max-height: {ICON_BUTTON_VISUAL_SIZE}px;
            padding: 0;
        }}
        QPushButton:checked, QPushButton[selected='true'] {{
            background: {t['selected_surface']};
            border-color: {t['coin_accent']};
            color: {t['text_primary']};
            font-weight: 700;
        }}
        QPushButton:disabled {{
            background: {t['disabled_surface']};
            border-color: {t['disabled_border']};
            color: {t['disabled_text']};
        }}
        QPushButton:focus {{
            border: 2px solid {t['focus_ring']};
            padding: 0 13px;
        }}
    """


def tool_button_stylesheet(
    context: ThemeContext | str = ThemeContext.GARDEN,
) -> str:
    """Return the matching treatment for visible and icon tool buttons."""

    t = theme_palette(context)
    hover_border = "#5b836f"
    pressed_border = "#6d9581"
    return f"""
        QToolButton {{
            min-height: {BUTTON_MIN_HEIGHT}px;
            max-height: {BUTTON_VISUAL_HEIGHT}px;
            padding: 0 14px;
            color: {t['text_primary']};
            background: {t['secondary_action']};
            border: 1px solid {t['secondary_border']};
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            text-align: left;
        }}
        QToolButton:hover {{
            background: {t['secondary_hover']};
            border-color: {hover_border};
        }}
        QToolButton:pressed {{
            background: {t['secondary_pressed']};
            border-color: {pressed_border};
        }}
        QToolButton:checked {{
            background: {t['selected_surface']};
            border-color: {t['coin_accent']};
            font-weight: 700;
        }}
        QToolButton[variant='primary'] {{
            min-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            max-height: {PRIMARY_BUTTON_VISUAL_HEIGHT}px;
            background: {t['action_accent']};
            border-color: {t['action_border']};
            color: {t['action_text']};
        }}
        QToolButton[variant='primary']:hover {{
            background: {t['action_hover']};
        }}
        QToolButton[variant='primary']:pressed {{
            background: {t['action_pressed']};
        }}
        QToolButton[variant='quiet'], QToolButton[variant='tertiary'] {{
            background: transparent;
            border-color: transparent;
            color: {t['text_secondary']};
        }}
        QToolButton[variant='quiet']:hover, QToolButton[variant='tertiary']:hover {{
            background: {t['secondary_hover']};
            border-color: {t['subtle_border']};
            color: {t['text_primary']};
        }}
        QToolButton[variant='destructive'] {{
            background: #6d2d2d;
            border-color: #a44a4a;
            color: #ffecec;
        }}
        QToolButton[variant='destructive']:hover {{ background: #7b3434; }}
        QToolButton[variant='destructive']:pressed {{ background: #562424; }}
        QToolButton[gardenRole='icon-button'] {{
            min-width: {ICON_BUTTON_SIZE}px;
            min-height: {ICON_BUTTON_SIZE}px;
            max-width: {ICON_BUTTON_SIZE}px;
            max-height: {ICON_BUTTON_SIZE}px;
            padding: 0;
            text-align: center;
        }}
        QToolButton:focus {{
            border: 2px solid {t['focus_ring']};
            padding: 0 9px;
        }}
        QToolButton[gardenRole='icon-button']:focus {{ padding: 0; }}
        QToolButton:disabled {{
            background: {t['disabled_surface']};
            border-color: {t['disabled_border']};
            color: {t['disabled_text']};
        }}
    """


def typography_stylesheet(
    context: ThemeContext | str = ThemeContext.GARDEN,
) -> str:
    """Return opt-in QSS for every shared text role.

    Qt style sheets do not implement CSS ``line-height``. The corresponding
    line metric is applied by :func:`apply_text_role` and remains directly
    available in :data:`TEXT_ROLE_TOKENS` for wrapping/custom paint code.
    """

    t = theme_palette(context)
    colors = {
        TextRole.BRAND_EYEBROW: t["text_muted"],
        TextRole.DISPLAY_TITLE: t["text_primary"],
        TextRole.SCREEN_TITLE: t["text_primary"],
        TextRole.SECTION_HEADING: t["text_primary"],
        TextRole.CARD_TITLE: t["text_primary"],
        TextRole.BODY: t["text_primary"],
        TextRole.SECONDARY: t["text_secondary"],
        TextRole.METADATA: t["text_muted"],
        TextRole.BADGE: t["text_secondary"],
        TextRole.NUMERIC_DISPLAY: t["text_primary"],
        TextRole.BUTTON_LABEL: t["text_primary"],
    }
    rules: list[str] = []
    for role, token in TEXT_ROLE_TOKENS.items():
        rules.append(
            "\n".join(
                (
                    f"*[textRole='{role.value}'] {{",
                    f"    min-height: {token.line_height_px}px;",
                    f"    color: {colors[role]};",
                    f"    font-size: {token.font_size_px}px;",
                    f"    font-weight: {token.font_weight};",
                    f"    letter-spacing: {token.letter_spacing_px:g}px;",
                    "}",
                )
            )
        )
    return "\n".join(rules)


def semantic_component_stylesheet(
    context: ThemeContext | str = ThemeContext.GARDEN,
) -> str:
    """Return opt-in component QSS keyed by :class:`SemanticRole` properties."""

    t = theme_palette(context)
    return f"""
        QTabBar[gardenRole='tabs']::tab {{
            min-width: {MIN_HIT_TARGET}px;
            min-height: {TAB_VISUAL_HEIGHT}px;
            max-height: {TAB_VISUAL_HEIGHT}px;
            padding: 0 {SpacingToken.LG}px;
            color: {t['text_secondary']};
            background: transparent;
            border: 0;
            border-bottom: 3px solid transparent;
            font-size: {TEXT_ROLE_TOKENS[TextRole.BUTTON_LABEL].font_size_px}px;
            font-weight: 600;
        }}
        QTabBar[gardenRole='tabs']::tab:hover {{
            color: {t['text_primary']};
            background: {t['secondary_hover']};
        }}
        QTabBar[gardenRole='tabs']::tab:selected {{
            color: {t['text_primary']};
            border-bottom-color: {t['coin_accent']};
            font-weight: 700;
        }}
        QTabBar[gardenRole='tabs']:focus {{
            border: 2px solid {t['focus_ring']};
            border-radius: 8px;
        }}
        QPushButton[gardenRole='segmented-filter'] {{
            min-width: {MIN_HIT_TARGET}px;
            min-height: {COMPACT_BUTTON_HEIGHT}px;
            max-height: {COMPACT_BUTTON_HEIGHT}px;
            padding: 0 {SpacingToken.MD}px;
            color: {t['text_secondary']};
            background: {t['secondary_action']};
            border: 1px solid {t['secondary_border']};
            border-radius: 8px;
        }}
        QPushButton[gardenRole='segmented-filter']:checked {{
            padding: 0 {int(SpacingToken.MD) - 1}px;
            color: {t['text_primary']};
            background: {t['selected_surface']};
            border: 2px solid {t['coin_accent']};
            font-weight: 700;
        }}
        QPushButton[gardenRole='segmented-filter']:focus,
        QAbstractButton[gardenRole='disclosure']:focus {{
            border: 2px solid {t['focus_ring']};
        }}
        QCheckBox {{
            min-height: {MIN_HIT_TARGET}px;
            padding: 0 {SpacingToken.XS}px;
            color: {t['text_primary']};
            border: 2px solid transparent;
            border-radius: 6px;
        }}
        QCheckBox:focus {{
            border-color: {t['focus_ring']};
        }}
        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            background: {t['secondary_action']};
            border: 1px solid {t['strong_border']};
            border-radius: 5px;
        }}
        QCheckBox::indicator:checked {{
            background: {t['growth_accent']};
            border: 4px solid {t['selected_surface']};
        }}
        QFrame[keyboardFocusSurface='true']:focus,
        QLabel[keyboardFocusSurface='true']:focus {{
            border: 2px solid {t['focus_ring']};
            border-radius: 8px;
        }}
        QLabel[gardenRole='badge'] {{
            min-height: {TEXT_ROLE_TOKENS[TextRole.BADGE].line_height_px}px;
            padding: {SpacingToken.XS}px {SpacingToken.SM}px;
            color: {t['text_primary']};
            background: {t['selected_surface']};
            border: 1px solid {t['strong_border']};
            border-radius: 8px;
            font-size: {TEXT_ROLE_TOKENS[TextRole.BADGE].font_size_px}px;
            font-weight: {TEXT_ROLE_TOKENS[TextRole.BADGE].font_weight};
        }}
        QProgressBar[gardenRole='progress'] {{
            min-height: 12px;
            color: {t['text_primary']};
            background: {t['secondary_action']};
            border: 1px solid {t['strong_border']};
            border-radius: 6px;
            text-align: center;
        }}
        QProgressBar[gardenRole='progress']::chunk {{
            background: {t['growth_accent']};
            border-radius: 5px;
        }}
        QAbstractButton[gardenRole='disclosure'] {{
            min-width: {MIN_HIT_TARGET}px;
            min-height: {MIN_HIT_TARGET}px;
            padding: 0 {SpacingToken.SM}px;
            color: {t['text_secondary']};
            background: transparent;
            border: 1px solid transparent;
            border-bottom-color: {t['subtle_border']};
            text-align: left;
        }}
        QToolTip,
        QLabel[gardenRole='tooltip'] {{
            padding: {SpacingToken.SM}px {SpacingToken.MD}px;
            color: {t['text_primary']};
            background: {t['raised_surface']};
            border: 1px solid {t['strong_border']};
            border-radius: 6px;
            font-size: {TEXT_ROLE_TOKENS[TextRole.SECONDARY].font_size_px}px;
        }}
        QFrame[gardenRole='banner'],
        QFrame[gardenRole='toast'] {{
            padding: {SpacingToken.SM}px {SpacingToken.MD}px;
            color: {t['text_primary']};
            background: {t['raised_surface']};
            border: 0;
            border-left: 3px solid {t['strong_border']};
            border-radius: 8px;
        }}
        QFrame[gardenRole='banner'][gardenTone='success'],
        QFrame[gardenRole='toast'][gardenTone='success'] {{
            background: #163229;
            border-left-color: {t['success']};
        }}
        QFrame[gardenRole='banner'][gardenTone='warning'],
        QFrame[gardenRole='toast'][gardenTone='warning'] {{
            background: #302c1d;
            border-left-color: {t['warning']};
        }}
        QFrame[gardenRole='banner'][gardenTone='info'],
        QFrame[gardenRole='toast'][gardenTone='info'] {{
            background: #162b31;
            border-left-color: {t['info']};
        }}
        QFrame[gardenRole='banner'][gardenTone='error'],
        QFrame[gardenRole='toast'][gardenTone='error'] {{
            background: #322125;
            border-left-color: {t['error']};
        }}
        QLabel[imageFrame='true'] {{
            color: {t['text_secondary']};
            background: {t['secondary_action']};
            border: 1px solid {t['subtle_border']};
            border-radius: 10px;
        }}
        QFrame[gardenRole='empty-state'] {{
            padding: {SpacingToken.XL}px;
            color: {t['text_secondary']};
            background: {t['raised_surface']};
            border: 1px dashed {t['strong_border']};
            border-radius: 12px;
        }}
        QLabel[gardenRole='missing-art'],
        QFrame[gardenRole='missing-art'] {{
            min-width: {MIN_HIT_TARGET}px;
            min-height: {MIN_HIT_TARGET}px;
            padding: {SpacingToken.MD}px;
            color: {t['text_secondary']};
            background: {t['secondary_action']};
            border: 1px dashed {t['strong_border']};
            border-radius: 10px;
        }}
    """


semantic_stylesheet = semantic_component_stylesheet


def foundation_stylesheet(
    context: ThemeContext | str = ThemeContext.GARDEN,
) -> str:
    """Compose the shared opt-in foundation for a native surface."""

    return "\n".join(
        (
            "QWidget { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
            button_stylesheet(context),
            tool_button_stylesheet(context),
            typography_stylesheet(context),
            semantic_component_stylesheet(context),
        )
    )


def nursery_catalog_stylesheet() -> str:
    """Warm content treatment that never recolors Nursery shell chrome."""

    t = theme_palette(ThemeContext.NURSERY)
    return f"""
        QFrame[nurseryCatalog='true'], QWidget[nurseryCatalog='true'] {{
            background: {t['shop_surface_1']};
            border: 0;
        }}
        QFrame[nurseryCatalogCard='true'], QPushButton[nurseryCatalogCard='true'] {{
            background: {t['shop_surface_2']};
            border: 1px solid rgba(226, 184, 95, 0.28);
            border-radius: 10px;
        }}
        QFrame[nurseryCatalogCard='true'][selected='true'],
        QPushButton[nurseryCatalogCard='true']:checked {{
            background: {t['shop_surface_3']};
            border: 2px solid {t['focus_ring']};
        }}
    """
