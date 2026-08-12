"""Shared visual tokens for Anki Garden's native Qt interfaces.

The Home card has a separate WebView stylesheet, but it intentionally mirrors
these action and focus colors. Keeping the native controls here prevents a new
dialog from silently falling back to Anki's platform-gray button palette.
"""

from __future__ import annotations


BUTTON_VARIANT_PRIMARY = "primary"
BUTTON_VARIANT_SECONDARY = "secondary"
BUTTON_VARIANT_TERTIARY = "tertiary"
BUTTON_VARIANT_DESTRUCTIVE = "destructive"

# Forty-four pixels is the shared effective target, including icon-only and
# plant actions. Compact visual controls may opt into 40 px only when their
# parent row preserves the 44 px hit area.
BUTTON_MIN_HEIGHT = 44
COMPACT_BUTTON_HEIGHT = 40
PLANT_ACTION_MIN_HEIGHT = 44
ICON_BUTTON_SIZE = 44
SCENE_HELP_BUTTON_SIZE = 44

GARDEN_THEME = {
    "garden_background": "#071A15",
    "dialog_surface": "#0C261F",
    "raised_surface": "#123228",
    "selected_surface": "#173B30",
    "subtle_border": "rgba(128, 178, 155, 0.22)",
    "strong_border": "#4F806E",
    "text_primary": "#F4F7F5",
    "text_secondary": "#CBD6D0",
    "text_muted": "#ACBBB3",
    "action_accent": "#5CC58B",
    "action_hover": "#71D39C",
    "action_pressed": "#49AA75",
    "action_text": "#062017",
    "action_border": "#5CC58B",
    "secondary_action": "#123228",
    "secondary_hover": "#173B30",
    "secondary_pressed": "#0C261F",
    "secondary_border": "#4F806E",
    "disabled_surface": "#173029",
    "disabled_border": "#3F5C50",
    "disabled_text": "#A6B6AE",
    "growth_accent": "#5CC58B",
    "coin_accent": "#E7C96A",
    "success": "#82E2AC",
    "warning": "#E7C96A",
    "error": "#E27B78",
    "focus_ring": "#82E2AC",
}


def button_stylesheet() -> str:
    """Return the complete text-button contract, including safe defaults."""

    t = GARDEN_THEME
    return f"""
        QPushButton {{
            min-height: {BUTTON_MIN_HEIGHT}px;
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
            border-color: #5b836f;
        }}
        QPushButton:pressed {{
            background: {t['secondary_pressed']};
            border-color: #6d9581;
        }}
        QPushButton[variant='primary'] {{
            background: {t['action_accent']};
            border-color: {t['action_border']};
            color: {t['action_text']};
        }}
        QPushButton[variant='primary']:hover {{ background: {t['action_hover']}; }}
        QPushButton[variant='primary']:pressed {{
            background: {t['action_pressed']};
            border-color: #86bc91;
        }}
        QPushButton[variant='secondary'] {{
            background: {t['secondary_action']};
            border-color: {t['secondary_border']};
            color: {t['text_primary']};
        }}
        QPushButton[variant='secondary']:hover {{ background: {t['secondary_hover']}; }}
        QPushButton[variant='secondary']:pressed {{
            background: {t['secondary_pressed']};
            border-color: #6d9581;
        }}
        QPushButton[variant='tertiary'] {{
            background: transparent;
            border-color: transparent;
            color: {t['text_secondary']};
        }}
        QPushButton[variant='tertiary']:hover {{
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
        QPushButton:checked, QPushButton[selected='true'] {{
            background: #344f35;
            border-color: #9a8751;
            color: #f5e5ba;
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


def tool_button_stylesheet() -> str:
    """Return the matching secondary-action treatment for visible tool buttons."""

    t = GARDEN_THEME
    return f"""
        QToolButton {{
            min-height: {BUTTON_MIN_HEIGHT}px;
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
            border-color: #5b836f;
        }}
        QToolButton:pressed {{
            background: {t['secondary_pressed']};
            border-color: #6d9581;
        }}
        QToolButton:checked {{
            background: {t['selected_surface']};
            border-color: #6d8e70;
        }}
        QToolButton:focus {{
            border: 2px solid {t['focus_ring']};
            padding: 0 9px;
        }}
        QToolButton:disabled {{
            background: {t['disabled_surface']};
            border-color: {t['disabled_border']};
            color: {t['disabled_text']};
        }}
    """
