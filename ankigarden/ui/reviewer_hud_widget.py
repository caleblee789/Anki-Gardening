"""Persistent native Qt component for the Reviewer Garden HUD."""

from __future__ import annotations

from collections import deque
import re
from typing import Any, Callable, Literal, Mapping, Optional

from .formatters import format_garden_coins, format_growth, format_quantity, format_status_label
from .plant_art import normalized_plant_pixmap
from .reviewer_hud import (
    FULL_BLOOM_GROWTH_ROUTE_COPY,
    HUD_ANSWER_CONTROLS_SCHEMA_VERSION,
    HUD_CONTROLS_CLEARANCE,
    HUD_HEADER_LEFT_INSET,
    HUD_HEADER_RIGHT_INSET,
    HUD_TOP_MARGIN,
    ReviewerHudProjection,
    format_growth_units,
    reviewer_hud_geometry,
    reviewer_hud_header_actions_width,
    reviewer_hud_safe_bottom,
    reviewer_hud_width,
)
from .theme import GARDEN_THEME, apply_tabular_numerals


try:  # Source-contract and projection tests run without Anki/Qt installed.
    from aqt.qt import (
        QColor,
        QEasingCurve,
        QEvent,
        QFrame,
        QGraphicsDropShadowEffect,
        QGraphicsOpacityEffect,
        QGridLayout,
        QHBoxLayout,
        QIcon,
        QLabel,
        QLinearGradient,
        QMenu,
        QPainter,
        QPen,
        QPixmap,
        QProgressBar,
        QRectF,
        QScrollArea,
        QSize,
        QSizePolicy,
        QTimer,
        QToolButton,
        QVariantAnimation,
        QVBoxLayout,
        QWidget,
        Qt,
    )

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - only outside Anki.
    QColor = object  # type: ignore[assignment,misc]
    QEasingCurve = object  # type: ignore[assignment,misc]
    QEvent = object  # type: ignore[assignment,misc]
    QFrame = object  # type: ignore[assignment,misc]
    QGraphicsDropShadowEffect = object  # type: ignore[assignment,misc]
    QGraphicsOpacityEffect = object  # type: ignore[assignment,misc]
    QGridLayout = object  # type: ignore[assignment,misc]
    QHBoxLayout = object  # type: ignore[assignment,misc]
    QIcon = object  # type: ignore[assignment,misc]
    QLabel = object  # type: ignore[assignment,misc]
    QLinearGradient = object  # type: ignore[assignment,misc]
    QMenu = object  # type: ignore[assignment,misc]
    QPainter = object  # type: ignore[assignment,misc]
    QPen = object  # type: ignore[assignment,misc]
    QPixmap = object  # type: ignore[assignment,misc]
    QProgressBar = object  # type: ignore[assignment,misc]
    QRectF = object  # type: ignore[assignment,misc]
    QScrollArea = object  # type: ignore[assignment,misc]
    QSize = object  # type: ignore[assignment,misc]
    QSizePolicy = object  # type: ignore[assignment,misc]
    QTimer = object  # type: ignore[assignment,misc]
    QToolButton = object  # type: ignore[assignment,misc]
    QVariantAnimation = object  # type: ignore[assignment,misc]
    QVBoxLayout = object  # type: ignore[assignment,misc]
    QWidget = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc


Callback = Optional[Callable[..., None]]
RewardRevealState = Literal[
    "hidden",
    "celebrating",
    "settled",
    "details_open",
    "archived",
]
_REWARD_HISTORY_PAGE_SIZE = 4
_REVEAL_HOLD_MS = 3_200
_COMPACT_REWARD_MIN_HEIGHT = 130
_COMPACT_REWARD_MAX_HEIGHT = 150
_REWARD_SCROLL_MAX_HEIGHT = 360
_ANSWER_ROW_SWAP_MS = 150
_PROJECTION_APPLY_DELAY_MS = 220
_PROGRESS_FILL_MS = 420
_PLANT_PULSE_MS = 300
_SESSION_HIGHLIGHT_MS = 600
_FULL_BLOOM_PULSE_MS = 680
_NEXT_PROJECTION_RESTORE_MS = 850
_ROUTINE_SESSION_RELEASE_MS = _PROJECTION_APPLY_DELAY_MS + _PROGRESS_FILL_MS
_SESSION_METRIC_FONT_PX = 12
_SESSION_METRIC_SPACING = 3
_TODAY_PROGRESS_SCALE = 1_000
_TODAY_INCOMPLETE_VISUAL_MAX = 985
_ANSWER_CONTROLS_RESIZE_SETTLE_MS = 180


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError("ReviewGardenHud requires Anki's Qt runtime") from _QT_IMPORT_ERROR


def _value(source: Any, *names: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        for name in names:
            if name in source:
                return source[name]
        return default
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return default


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _property_int_tuple(
    value: Any,
    names: tuple[str, ...],
) -> tuple[int, ...] | None:
    """Normalize a QVariant list, mapping, or QRect-like host property."""

    raw_values: tuple[Any, ...]
    if isinstance(value, Mapping):
        try:
            raw_values = tuple(value[name] for name in names)
        except KeyError:
            aliases = {"x": "left", "y": "top"}
            try:
                raw_values = tuple(
                    value[aliases.get(name, name)] for name in names
                )
            except KeyError:
                return None
    elif isinstance(value, (tuple, list)) and len(value) == len(names):
        raw_values = tuple(value)
    else:
        resolved: list[Any] = []
        for name in names:
            getter = getattr(value, name, None)
            if getter is None:
                return None
            try:
                resolved.append(getter() if callable(getter) else getter)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return None
        raw_values = tuple(resolved)
    try:
        return tuple(int(round(float(item))) for item in raw_values)
    except (TypeError, ValueError, OverflowError):
        return None


def _call(callback: Callback, *args: Any) -> None:
    if not callable(callback):
        return
    try:
        callback(*args)
    except TypeError:
        callback()


def _repolish(widget: Any) -> None:
    try:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    except Exception:
        pass


def _set_decoration(widget: Any) -> None:
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    except Exception:
        pass


def _bundle_id(bundle: Any) -> str:
    return str(_value(bundle, "bundle_id", "event_id", "correlation_id", default="") or "")


def _bundle_hero(bundle: Any) -> Any:
    return _value(bundle, "hero", "hero_item", default=bundle)


def _hero_kind(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    raw = _value(hero, "kind", "reward_type", "milestone_type", default="")
    return str(getattr(raw, "value", raw) or "").lower()


def _bundle_has_kind(bundle: Any, kind: str) -> bool:
    expected = str(kind or "").replace("-", "_").lower()
    items = tuple(_value(bundle, "all_items", "items", default=()) or ())
    if not items:
        items = (_bundle_hero(bundle),)
    for item in items:
        raw = _value(item, "kind", default="")
        actual = str(getattr(raw, "value", raw) or "").replace("-", "_").lower()
        if actual == expected:
            return True
    return False


def _bundle_priority(bundle: Any) -> int:
    explicit = _value(bundle, "priority", default=None)
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    hero_kind = _value(_bundle_hero(bundle), "kind", default=None)
    hero_priority = getattr(hero_kind, "priority", None)
    if hero_priority is not None:
        try:
            return int(hero_priority)
        except (TypeError, ValueError):
            pass
    kind = _hero_kind(bundle)
    return {
        "full_bloom": 0,
        "full-bloom": 0,
        "stage_change": 1,
        "stage-change": 1,
        "environment_discovery": 2,
        "environment-discovery": 2,
        "garden_find": 3,
        "garden-find": 3,
        "checkpoint": 4,
        "coin": 5,
        "booster": 5,
        "growth": 6,
    }.get(kind, 5)


def _bundle_routine_only(bundle: Any) -> bool:
    return bool(_value(bundle, "routine_only", default=False))


def _compact_projection(bundle: Any) -> Any:
    return _value(bundle, "compact_projection", "compact", default=None)


def _compact_summary_label(summary: Any) -> str:
    label = str(_value(summary, "label", default="") or "").strip()
    label = re.sub(
        r"\bbooster\b(?!\s+potion\b)",
        "Booster Potion",
        label,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\bgrowth\b", "Growth", label, flags=re.IGNORECASE)


def reward_summary_cell_width_weight(
    text_width: int,
    *,
    icon_width: int = 12,
    spacing: int = 2,
    horizontal_inset: int = 4,
) -> int:
    """Return a bounded layout weight for one compact reward summary."""

    return max(
        1,
        int(text_width or 0)
        + max(0, int(icon_width or 0))
        + max(0, int(spacing or 0))
        + max(0, int(horizontal_inset or 0)),
    )


def session_footer_metric_row_width(
    metric_widths: tuple[int, ...],
    *,
    separator_width: int,
    spacing: int = _SESSION_METRIC_SPACING,
) -> int:
    """Return the rendered width of one complete session-metric row."""

    widths = tuple(max(0, int(width or 0)) for width in metric_widths)
    if not widths:
        return 0
    join_width = max(0, int(separator_width or 0)) + (2 * max(0, int(spacing)))
    return sum(widths) + ((len(widths) - 1) * join_width)


def _compact_visible_summaries(bundle: Any) -> tuple[Any, ...]:
    compact = _compact_projection(bundle)
    values = tuple(_value(compact, "visible_summaries", default=()) or ())
    if compact is not None:
        return values[:2]
    return _secondary_items(bundle)[:2]


def _compact_hidden_summaries(bundle: Any) -> tuple[Any, ...]:
    compact = _compact_projection(bundle)
    return tuple(_value(compact, "hidden_summaries", default=()) or ())


def _structured_reward_details(bundle: Any) -> tuple[Any, ...]:
    return tuple(_value(bundle, "detail_rows", default=()) or ())


def _reward_eyebrow(bundle: Any) -> str:
    compact = _compact_projection(bundle)
    explicit = str(_value(compact, "eyebrow", default="") or "").strip()
    if explicit:
        return explicit
    kind = _hero_kind(bundle).replace("-", "_")
    return {
        "full_bloom": "MILESTONE REACHED",
        "stage_change": "MILESTONE REACHED",
        "garden_find": "STANDARD FIND",
        "checkpoint": "CHECKPOINT REACHED",
        "environment_discovery": "DISCOVERY",
    }.get(kind, "REWARD EARNED")


def _reward_hero_title(bundle: Any) -> str:
    compact = _compact_projection(bundle)
    title = str(
        _value(compact, "hero_title", default="") or _hero_title(bundle)
    ).strip()
    if (
        _hero_kind(bundle).replace("-", "_") == "full_bloom"
        and title.casefold() in {"full bloom", "full bloom achieved"}
    ):
        return "Full Bloom reached"
    return title


def _reward_hero_subtitle(bundle: Any) -> str:
    compact = _compact_projection(bundle)
    explicit = str(_value(compact, "hero_subtitle", default="") or "").strip()
    return explicit or _hero_category(bundle)


def _full_bloom_plant_name(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    explicit = str(_value(hero, "plant_name", default="") or "").strip()
    if explicit:
        return explicit
    subtitle = _reward_hero_subtitle(bundle)
    if subtitle and subtitle.casefold() not in {"full bloom", "milestone reached"}:
        return subtitle
    title = _hero_title(bundle)
    return title if title.casefold() != "full bloom achieved" else "Completed plant"


def _full_bloom_plant_class(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    return str(
        _value(hero, "plant_class", "species_name", "species", default="") or ""
    ).replace("_", " ").strip().title()


def _full_bloom_plant_id(bundle: Any) -> str:
    return str(_value(_bundle_hero(bundle), "plant_id", default="") or "")


def _format_coin_balance(value: Any, *, exact_fits: bool = True) -> str:
    """Keep release-boundary balances exact and compact only on collision."""

    target = _integer(value)
    exact = f"{target:,}"
    if target <= 1_000_000 or exact_fits:
        return exact
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if target >= divisor:
            amount = target / divisor
            rendered = f"{amount:.1f}".rstrip("0").rstrip(".")
            return f"{rendered}{suffix}"
    return exact


def _checkpoint_marker_states(
    progress_percent: Any,
    next_checkpoint_percent: Any,
    checkpoints: tuple[int, ...] = (25, 50, 75, 100),
) -> tuple[str, ...]:
    progress = max(0, min(100, _integer(progress_percent)))
    next_checkpoint = max(0, min(100, _integer(next_checkpoint_percent)))
    return tuple(
        "next"
        if checkpoint == next_checkpoint
        else "completed"
        if progress >= checkpoint
        else "future"
        for checkpoint in checkpoints
    )


def _checkpoint_sequence_is_chronological(
    checkpoints: tuple[int, ...],
) -> bool:
    """Accept increasing markers plus an explicit 100 -> next-stage reset."""

    return all(
        current > previous or previous == 100
        for previous, current in zip(checkpoints, checkpoints[1:])
    )


def _effect_overflow_label(count: Any) -> str:
    normalized = _integer(count)
    if not normalized:
        return ""
    return f"{format_quantity(normalized, 'more effect', 'more effects')} ›"


def _effect_display_text(value: Any) -> str:
    """Separate an effect's identity from its bounded reviewer status."""

    text = " ".join(str(value or "").split())
    if not text or " · " in text:
        return (
            f"Booster Potion{text[len('Booster'):]}"
            if text == "Booster" or text.startswith("Booster · ")
            else text
        )
    if text == "Booster":
        return "Booster Potion"
    if text.startswith("Booster "):
        return f"Booster Potion · {text[len('Booster '):]}"
    for prefix in (
        "Garden decoration",
        "Garden Rhythm",
        "Fertilizer",
        "Booster Potion",
        "Scenery",
    ):
        if text == prefix:
            return text
        if text.startswith(f"{prefix} "):
            return f"{prefix} · {text[len(prefix) + 1:]}"
    return text


def _ground_shadow_metrics(
    stage: Any,
    visible_width: Any,
    visible_bottom: Any,
    region_height: Any,
) -> tuple[float, float, float]:
    """Return a stage-aware ``(width, center_y, height)`` ground ellipse."""

    try:
        width = max(1.0, float(visible_width))
    except (TypeError, ValueError):
        width = 72.0
    try:
        baseline = float(visible_bottom)
    except (TypeError, ValueError):
        baseline = 124.0
    try:
        height_limit = max(1.0, float(region_height))
    except (TypeError, ValueError):
        height_limit = 146.0
    key = str(stage or "").casefold().replace("-", "_")
    bounds = {
        "seed": (70.0, 85.0),
        "sprout": (85.0, 105.0),
        "young": (115.0, 140.0),
        "mature": (145.0, 180.0),
        "flowering": (145.0, 180.0),
        "rare": (145.0, 180.0),
        "full_bloom": (145.0, 180.0),
    }.get(key, (85.0, 140.0))
    shadow_width = max(bounds[0], min(bounds[1], width * 1.35))
    shadow_height = 7.0
    center_y = max(4.0, min(height_limit - 4.0, baseline + 1.0))
    return shadow_width, center_y, shadow_height


def _pixmap_visible_geometry(pixmap: Any) -> tuple[float, float]:
    """Return alpha-bounded logical width and bottom for a cached plant pixmap."""

    try:
        image = pixmap.toImage()
        width = int(image.width())
        height = int(image.height())
        ratio = max(1.0, float(pixmap.devicePixelRatio()))
    except Exception:
        return (0.0, 0.0)
    if width <= 0 or height <= 0:
        return (0.0, 0.0)
    left, right, bottom = width, -1, -1
    # Artwork changes at most once per projected stage, so an alpha scan here
    # is cheaper and more accurate than carrying stage-specific shadow assets.
    for y in range(height):
        row_has_alpha = False
        for x in range(width):
            try:
                opaque = int(image.pixelColor(x, y).alpha()) > 8
            except Exception:
                opaque = False
            if not opaque:
                continue
            left = min(left, x)
            right = max(right, x)
            row_has_alpha = True
        if row_has_alpha:
            bottom = y
    if right < left or bottom < 0:
        return (0.0, 0.0)
    return ((right - left + 1) / ratio, (bottom + 1) / ratio)


def _alpha_cropped_pixmap(pixmap: Any, *, padding: float = 0.08) -> Any:
    """Crop transparent canvas padding while retaining a small optical halo."""

    try:
        width = int(pixmap.width())
        height = int(pixmap.height())
        bounds = pixmap.mask().boundingRect()
    except Exception:
        return pixmap
    if not bounds.isValid() or bounds.width() <= 0 or bounds.height() <= 0:
        return pixmap
    visible_width = int(bounds.width())
    visible_height = int(bounds.height())
    pad_x = round(visible_width * max(0.0, min(0.5, padding)))
    pad_y = round(visible_height * max(0.0, min(0.5, padding)))
    crop_left = max(0, int(bounds.x()) - pad_x)
    crop_top = max(0, int(bounds.y()) - pad_y)
    crop_right = min(width, int(bounds.x()) + visible_width + pad_x)
    crop_bottom = min(height, int(bounds.y()) + visible_height + pad_y)
    try:
        return pixmap.copy(
            crop_left,
            crop_top,
            max(1, crop_right - crop_left),
            max(1, crop_bottom - crop_top),
        )
    except Exception:
        return pixmap


def _session_metric_labels(
    growth_units: Any,
    coins: Any,
    finds: Any,
) -> tuple[str, ...]:
    values = (
        _session_metric_text(0, growth_units),
        _session_metric_text(1, coins),
        _session_metric_text(2, finds),
    )
    return tuple(value for value in values if value)


def _session_metric_increases(
    previous: tuple[Any, Any, Any],
    current: tuple[Any, Any, Any],
) -> tuple[bool, bool, bool]:
    """Identify changes from committed totals, not an in-flight count-up."""

    return tuple(
        _integer(current[index]) > _integer(previous[index])
        for index in range(3)
    )  # type: ignore[return-value]


def _session_metric_text(index: int, value: Any) -> str:
    normalized = _integer(value)
    if not normalized:
        return ""
    if index == 0:
        return f"{format_growth_units(normalized, signed=True)} Growth"
    if index == 1:
        return format_garden_coins(normalized, signed=True)
    return format_quantity(normalized, "Garden Find")


def _session_coin_count(snapshot: Any) -> int:
    """Prefer the canonical compact-footer Coin count when it is available."""

    footer_count = _value(snapshot, "footer_coin_count", default=None)
    if footer_count is not None:
        return _integer(footer_count)
    return _integer(_value(snapshot, "garden_coins_earned", "coins", default=0))


def _session_find_count(snapshot: Any) -> int:
    """Preserve an explicit zero from the canonical compact Find projection."""

    footer_count = _value(snapshot, "footer_find_count", default=None)
    if footer_count is not None:
        return _integer(footer_count)
    legacy_count = _value(snapshot, "find_count", default=None)
    if legacy_count is not None:
        return _integer(legacy_count)
    return len(tuple(_value(snapshot, "standard_finds", default=()) or ()))


def _hero_title(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    return str(
        _value(
            hero,
            "title",
            "display_name",
            "name",
            "item_name",
            default="Reward earned",
        )
        or "Reward earned"
    )


def _hero_category(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    explicit = str(_value(hero, "category_label", "category", "label", default="") or "")
    if explicit and explicit != _hero_title(bundle):
        return explicit
    kind = _hero_kind(bundle).replace("_", " ").replace("-", " ").strip()
    return kind.title() if kind else "Garden reward"


def _hero_rarity(bundle: Any) -> str:
    return str(_value(_bundle_hero(bundle), "rarity", "tier", default="") or "")


def _hero_art(bundle: Any) -> str:
    hero = _bundle_hero(bundle)
    raw = _value(
        hero,
        "art_path",
        "art_asset",
        "artwork_ref",
        "plant_art_asset",
        default="",
    )
    return str(getattr(raw, "path", raw) or "")


def _hero_amounts(bundle: Any) -> tuple[int, int]:
    hero = _bundle_hero(bundle)
    growth_units = _integer(
        _value(hero, "growth_units", "growth_total_units", default=0)
    )
    if not growth_units:
        growth_points = _integer(_value(hero, "growth", "growth_amount", default=0))
        growth_units = growth_points * 100
    displayed_coin_delta = _value(bundle, "displayed_coin_delta", default=None)
    if displayed_coin_delta is not None:
        coins = _integer(displayed_coin_delta)
    else:
        coins = _integer(
            _value(
                hero,
                "garden_coins",
                "coins",
                "coins_total",
                "coin_amount",
                "coin_reward",
                default=0,
            )
        )
    return growth_units, coins


def _inventory_name(item_id: Any) -> str:
    """Return compact learner-facing copy for an engine-owned inventory ID."""

    normalized = str(item_id or "").strip().split(":")[-1]
    return normalized.replace("_", " ").strip().title() or "Garden Item"


def _inventory_amount_labels(item: Any) -> tuple[str, ...]:
    canonical = tuple(
        _value(item, "learner_inventory_labels", default=()) or ()
    )
    if canonical:
        return tuple(str(value) for value in canonical if str(value).strip())
    values: list[str] = []
    for raw_item_id, raw_quantity in tuple(
        _value(item, "inventory_items", default=()) or ()
    ):
        quantity = _integer(raw_quantity)
        if not quantity:
            continue
        name = _inventory_name(raw_item_id)
        if quantity != 1 and not name.casefold().endswith("s"):
            name += "s"
        values.append(f"+{quantity:,} {name}")
    return tuple(values)


def _hero_inventory_labels(bundle: Any) -> tuple[str, ...]:
    return _inventory_amount_labels(_bundle_hero(bundle))


def _secondary_items(bundle: Any) -> tuple[Any, ...]:
    return tuple(_value(bundle, "secondary_items", "secondary", default=()) or ())[:3]


def _all_secondary_items(bundle: Any) -> tuple[Any, ...]:
    items = tuple(_value(bundle, "all_items", "items", default=()) or ())
    if items:
        return items[1:]
    return tuple(_value(bundle, "secondary_items", "secondary", default=()) or ())


def _bundle_growth_units(bundle: Any) -> int:
    items = tuple(_value(bundle, "all_items", "items", default=()) or ())
    if not items:
        items = (_bundle_hero(bundle),)
    return sum(
        _integer(_value(item, "growth_units", "growth_total_units", default=0))
        for item in items
    )


def _secondary_label(item: Any) -> str:
    kind = _hero_kind(item).replace("-", "_")
    if kind in {"full_bloom", "stage_change", "checkpoint"}:
        label = str(
            _value(
                item,
                "detail",
                "category_label",
                "title",
                default="",
            )
            or ""
        )
    else:
        label = str(
            _value(
                item,
                "short_label",
                "title",
                "display_name",
                "label",
                default="",
            )
            or ""
        )
    growth = _integer(_value(item, "growth_units", default=0))
    coins = _integer(_value(item, "garden_coins", "coins", "coin_amount", default=0))
    amounts: list[str] = []
    if growth:
        amounts.append(f"{format_growth_units(growth, signed=True)} Growth")
    if coins:
        amounts.append(format_garden_coins(coins, signed=True))
    amounts.extend(_inventory_amount_labels(item))
    return " · ".join(value for value in (label, *amounts) if value) or "Reward"


class _ClickableFrame(QFrame):  # type: ignore[misc,valid-type]
    def __init__(self, parent: Any = None, callback: Callback = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.set_callback(callback)

    def set_callback(self, callback: Callback) -> None:
        self._activate_callback = callback
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if callable(callback) else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event: Any) -> None:
        try:
            is_left = event.button() == Qt.MouseButton.LeftButton
        except Exception:
            is_left = True
        if is_left:
            _call(self._activate_callback)
            try:
                event.accept()
            except Exception:
                pass
            return
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass


class _ElidedLabel(QLabel):  # type: ignore[misc,valid-type]
    def __init__(self, text: str = "", parent: Any = None) -> None:
        super().__init__("", parent)
        self._full_text = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: Any) -> None:
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self.setAccessibleName(self._full_text)
        self._sync()

    def _sync(self) -> None:
        try:
            width = max(1, self.contentsRect().width())
            visible = self.fontMetrics().elidedText(
                self._full_text,
                Qt.TextElideMode.ElideRight,
                width,
            )
        except Exception:
            visible = self._full_text
        QLabel.setText(self, visible)
        self.setProperty("textElided", visible != self._full_text)

    def resizeEvent(self, event: Any) -> None:
        self._sync()
        try:
            super().resizeEvent(event)
        except Exception:
            pass


class _EffectLabel(_ElidedLabel):  # type: ignore[misc,valid-type]
    """Keep one compact effect phrase readable across at most two lines."""

    def __init__(self, text: str = "", parent: Any = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)

    def _sync(self) -> None:
        text = " ".join(self._full_text.split())
        try:
            metrics = self.fontMetrics()
            width = max(1, self.contentsRect().width())
            visible = text
            if text and metrics.horizontalAdvance(text) > width:
                words = text.split()
                first: list[str] = []
                while words:
                    candidate = " ".join((*first, words[0]))
                    if first and metrics.horizontalAdvance(candidate) > width:
                        break
                    first.append(words.pop(0))
                first_line = " ".join(first)
                second_line = " ".join(words)
                if metrics.horizontalAdvance(first_line) > width:
                    first_line = metrics.elidedText(
                        first_line,
                        Qt.TextElideMode.ElideRight,
                        width,
                    )
                if metrics.horizontalAdvance(second_line) > width:
                    second_line = metrics.elidedText(
                        second_line,
                        Qt.TextElideMode.ElideRight,
                        width,
                    )
                visible = first_line + (
                    f"\n{second_line}" if second_line else ""
                )
            wrapped = "\n" in visible
            line_count = 2 if wrapped else 1
            label_height = metrics.lineSpacing() * line_count + (
                2 if wrapped else 0
            )
            self.setMinimumHeight(label_height)
            self.setMaximumHeight(label_height)
        except Exception:
            visible = text
            wrapped = False
        QLabel.setText(self, visible)
        clamped = " ".join(visible.split()) != text
        self.setProperty("textElided", clamped)
        self.setProperty("effectWrapped", wrapped)


class _TwoLineLabel(QLabel):  # type: ignore[misc,valid-type]
    """Wrap normal names to two lines, eliding only overflow beyond line two."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__("", parent)
        self._full_text = ""
        self.setMinimumWidth(0)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: Any) -> None:
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self.setAccessibleName(self._full_text)
        self._sync()

    def _sync(self) -> None:
        text = self._full_text.strip()
        try:
            metrics = self.fontMetrics()
            width = max(1, self.contentsRect().width())
            line_count = 1 if self.property("singleLine") else 2
            self.setMinimumHeight(metrics.lineSpacing() * line_count + 3)
            self.setMaximumHeight(metrics.lineSpacing() * line_count + 3)
            if not text or metrics.horizontalAdvance(text) <= width:
                visible = text
            else:
                words = text.split()
                first: list[str] = []
                while words:
                    candidate = " ".join((*first, words[0]))
                    if first and metrics.horizontalAdvance(candidate) > width:
                        break
                    first.append(words.pop(0))
                    if metrics.horizontalAdvance(" ".join(first)) > width:
                        first[-1] = metrics.elidedText(
                            first[-1], Qt.TextElideMode.ElideRight, width
                        )
                        break
                first_line = " ".join(first)
                second_line = metrics.elidedText(
                    " ".join(words),
                    Qt.TextElideMode.ElideRight,
                    width,
                )
                visible = first_line + (f"\n{second_line}" if second_line else "")
        except Exception:
            visible = text
        QLabel.setText(self, visible)
        self.setProperty("textClamped", visible.replace("\n", " ") != text)

    def resizeEvent(self, event: Any) -> None:
        self._sync()
        try:
            super().resizeEvent(event)
        except Exception:
            pass


class _PreferredHeightScrollArea(QScrollArea):  # type: ignore[misc,valid-type]
    """Report a bounded preferred height while remaining shrinkable."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._preferred_height = 1

    def set_preferred_height(self, height: int) -> None:
        self._preferred_height = max(1, int(height))
        self.updateGeometry()

    def sizeHint(self) -> Any:  # noqa: N802 - Qt API
        hint = super().sizeHint()
        hint.setHeight(self._preferred_height)
        return hint

    def minimumSizeHint(self) -> Any:  # noqa: N802 - Qt API
        hint = super().minimumSizeHint()
        hint.setHeight(1)
        return hint


class _ArtRegion(QFrame):  # type: ignore[misc,valid-type]
    """Transparent art stage with a soft, non-rectangular ground shadow."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._particle_progress = 0.0
        self._ground_shadow_width = 92.0
        self._ground_shadow_center_y = 126.0
        self._ground_shadow_height = 7.0

    def set_grounding(
        self,
        stage: Any,
        visible_width: Any,
        visible_bottom: Any,
    ) -> None:
        width, center_y, height = _ground_shadow_metrics(
            stage,
            visible_width,
            visible_bottom,
            self.height(),
        )
        self._ground_shadow_width = width
        self._ground_shadow_center_y = center_y
        self._ground_shadow_height = height
        self.setProperty("groundShadowWidth", round(width, 2))
        self.setProperty("groundShadowCenterY", round(center_y, 2))
        self.setProperty("groundShadowHeight", round(height, 2))
        self.setProperty("groundShadowStage", str(stage or ""))
        self.update()

    def set_particle_progress(self, progress: Any) -> None:
        try:
            normalized = max(0.0, min(1.0, float(progress)))
        except (TypeError, ValueError):
            normalized = 0.0
        self._particle_progress = normalized
        self.setProperty("localizedParticleProgress", round(normalized, 3))
        self.update()

    def paintEvent(self, event: Any) -> None:
        try:
            super().paintEvent(event)
        except Exception:
            pass
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        # Four translucent ellipses approximate a soft four-pixel blur without
        # applying a graphics effect to the plant or allocating another layer.
        width = min(float(self.width()) - 8.0, self._ground_shadow_width)
        center_y = self._ground_shadow_center_y
        height = self._ground_shadow_height
        for expansion, alpha in ((4.0, 4), (2.5, 7), (1.0, 10), (0.0, 16)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawEllipse(QRectF(
                (float(self.width()) - width - expansion * 2.0) / 2.0,
                center_y - (height + expansion) / 2.0,
                width + expansion * 2.0,
                height + expansion,
            ))
        progress = self._particle_progress
        if 0.0 < progress < 1.0:
            wave = 1.0 - abs((progress * 2.0) - 1.0)
            center_x = float(self.width()) / 2.0
            center_y = float(self.height()) * 0.48
            particle_specs = (
                (-32.0, -19.0, -13.0, -15.0, 3.0),
                (-18.0, -35.0, -8.0, -18.0, 2.3),
                (18.0, -34.0, 8.0, -18.0, 2.5),
                (33.0, -18.0, 14.0, -14.0, 3.0),
                (-39.0, 2.0, -12.0, -7.0, 2.2),
                (39.0, 1.0, 12.0, -8.0, 2.2),
            )
            color = QColor(GARDEN_THEME["reviewer_hud_coin"])
            color.setAlpha(max(0, min(190, round(190 * wave))))
            painter.setBrush(color)
            for x, y, travel_x, travel_y, radius in particle_specs:
                particle_x = center_x + x + (travel_x * progress)
                particle_y = center_y + y + (travel_y * progress)
                painter.drawEllipse(QRectF(
                    particle_x - radius,
                    particle_y - radius,
                    radius * 2.0,
                    radius * 2.0,
                ))
        painter.end()


class CheckpointTrack(QWidget):  # type: ignore[misc,valid-type]
    """Paint progress and checkpoint dots into one uncluttered native track."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewerHudCheckpointTrack")
        self.setProperty("semanticId", "reviewer.hud.checkpoint-track")
        self.setFixedHeight(18)
        self.setMinimumWidth(1)
        self._progress = 0.0
        self._next_checkpoint = 0
        self._reward_coins = 0
        self._checkpoints: tuple[int, ...] = (25, 50, 75, 100)
        self._animation: Any | None = None
        self._pulse = 0.0
        self._pulse_checkpoint = 0
        self._pulse_animation: Any | None = None
        self._checkpoint_crossing_active = False
        self._checkpoint_sequence_revision = 0
        self._checkpoint_reached_callbacks: list[Callable[[], None]] = []
        self.setProperty("crossedCheckpoints", ())
        self.setProperty("checkpointSequenceChronological", True)
        self.setProperty("currentPositionHandleVisible", False)
        self.setProperty("completedCheckpointCount", 0)
        self.setProperty("checkpointPercents", self._checkpoints)
        self.setProperty("markerShape", "diamond-tick")
        self.setProperty("interactive", False)
        _set_decoration(self)

    def sizeHint(self) -> Any:
        return QSize(240, 18)

    def set_checkpoint(self, percent: int, reward_coins: int = 0) -> None:
        self._next_checkpoint = max(0, min(100, int(percent or 0)))
        self._reward_coins = max(0, int(reward_coins or 0))
        self.setProperty("nextCheckpointPercent", self._next_checkpoint)
        self.setProperty("nextCheckpointRewardCoins", self._reward_coins)
        self._sync_marker_properties()
        self.update()

    def set_milestones(self, checkpoints: Any) -> None:
        normalized = tuple(sorted({
            max(1, min(100, int(value)))
            for value in tuple(checkpoints or ())
        }))
        self._checkpoints = normalized or (25, 50, 75, 100)
        self.setProperty("checkpointPercents", self._checkpoints)
        self._sync_marker_properties()
        self.update()

    def set_progress(
        self,
        percent: int,
        *,
        animate: bool = False,
        duration: int = _PROGRESS_FILL_MS,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        target = float(max(0, min(100, int(percent or 0))))
        self.setProperty("progressPercent", int(target))
        if not animate or abs(target - self._progress) < 0.5:
            self._progress = target
            self._sync_marker_properties()
            self.update()
            if callable(on_finished):
                on_finished()
            return
        if self._animation is not None:
            try:
                self._animation.stop()
            except Exception:
                pass
        animation = QVariantAnimation(self)
        animation.setStartValue(self._progress)
        animation.setEndValue(target)
        animation.setDuration(max(150, int(duration)))
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: (
                self._set_animated_progress(value)
                if self._animation is animation
                else None
            )
        )
        def finish() -> None:
            if self._animation is not animation:
                return
            self._animation = None
            if callable(on_finished):
                on_finished()

        animation.finished.connect(finish)
        self._animation = animation
        animation.start()

    def _set_animated_progress(self, value: Any) -> None:
        try:
            self._progress = float(value)
        except (TypeError, ValueError):
            return
        self._sync_marker_properties()
        self.update()

    def _sync_marker_properties(self) -> None:
        states = _checkpoint_marker_states(
            self._progress,
            self._next_checkpoint,
            self._checkpoints,
        )
        self.setProperty(
            "completedCheckpointCount",
            sum(state == "completed" for state in states),
        )
        self.setProperty("checkpointMarkerStates", ",".join(states))

    def pulse_checkpoint(
        self,
        percent: int | None = None,
        *,
        duration: int = 360,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        if self._pulse_animation is not None:
            try:
                self._pulse_animation.stop()
            except Exception:
                pass
        self._pulse_checkpoint = max(
            0,
            min(100, int(self._next_checkpoint if percent is None else percent)),
        )
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.5, 1.0)
        animation.setEndValue(0.0)
        animation.setDuration(max(180, int(duration)))
        animation.valueChanged.connect(
            lambda value: (
                self._set_pulse(value)
                if self._pulse_animation is animation
                else None
            )
        )
        def finish() -> None:
            if self._pulse_animation is not animation:
                return
            self._pulse_animation = None
            self._pulse = 0.0
            self._pulse_checkpoint = 0
            self.update()
            if callable(on_finished):
                on_finished()

        animation.finished.connect(finish)
        self._pulse_animation = animation
        animation.start()

    @property
    def checkpoint_crossing_active(self) -> bool:
        return self._checkpoint_crossing_active

    def when_checkpoint_reached(self, callback: Callable[[], None]) -> None:
        """Run a reward reveal after the reached marker has pulsed."""

        if not callable(callback):
            return
        if self._checkpoint_crossing_active:
            self._checkpoint_reached_callbacks.append(callback)
        else:
            callback()

    def _emit_checkpoint_reached(self) -> None:
        callbacks = tuple(self._checkpoint_reached_callbacks)
        self._checkpoint_reached_callbacks.clear()
        for callback in callbacks:
            try:
                callback()
            except Exception:
                continue

    def animate_checkpoint_crossing(
        self,
        *,
        reached_checkpoint: int,
        reached_reward_coins: int,
        final_percent: int,
        next_checkpoint: int,
        next_reward_coins: int,
    ) -> None:
        """Compatibility delegate for a one-marker checkpoint sequence."""

        self.animate_checkpoint_sequence(
            reached_checkpoints=(reached_checkpoint,),
            reached_reward_coins=reached_reward_coins,
            final_percent=final_percent,
            next_checkpoint=next_checkpoint,
            next_reward_coins=next_reward_coins,
        )

    def animate_checkpoint_sequence(
        self,
        *,
        reached_checkpoints: tuple[int, ...],
        reached_reward_coins: int,
        final_percent: int,
        next_checkpoint: int,
        next_reward_coins: int,
    ) -> None:
        """Animate every crossed marker before revealing the consolidated bundle."""

        if self._checkpoint_crossing_active:
            # Rapid answers must not strand the preceding committed reward.
            self._checkpoint_crossing_active = False
            self._emit_checkpoint_reached()
        self._checkpoint_sequence_revision += 1
        revision = self._checkpoint_sequence_revision
        for animation_name in ("_animation", "_pulse_animation"):
            animation = getattr(self, animation_name, None)
            if animation is not None:
                try:
                    animation.stop()
                except Exception:
                    pass
            setattr(self, animation_name, None)
        self._pulse = 0.0
        self._pulse_checkpoint = 0
        self._checkpoint_crossing_active = True
        reached = tuple(
            max(0, min(100, int(checkpoint or 0)))
            for checkpoint in reached_checkpoints
            if int(checkpoint or 0) in self._checkpoints
        )
        self.setProperty("crossedCheckpoints", reached)
        self.setProperty(
            "checkpointSequenceChronological",
            _checkpoint_sequence_is_chronological(reached),
        )
        final = max(0, min(100, int(final_percent or 0)))
        if not reached:
            self._checkpoint_crossing_active = False
            self.set_checkpoint(next_checkpoint, next_reward_coins)
            self.set_progress(final, animate=True)
            self._emit_checkpoint_reached()
            return

        def finish_sequence() -> None:
            if revision != self._checkpoint_sequence_revision:
                return
            self._checkpoint_crossing_active = False
            self._emit_checkpoint_reached()
            self.set_checkpoint(next_checkpoint, next_reward_coins)
            if final < reached[-1]:
                # A stage boundary starts a fresh stage-relative track.
                self._progress = 0.0
                self._sync_marker_properties()
                self.update()
            self.set_progress(final, animate=True, duration=320)

        def animate_marker(index: int) -> None:
            if revision != self._checkpoint_sequence_revision:
                return
            checkpoint = reached[index]
            if index and checkpoint <= reached[index - 1]:
                # Markers are stage-relative. Crossing 100 starts the next
                # stage (or redirected plant) at an empty track before its
                # 25/50/75 markers animate.
                self._progress = 0.0
                self._sync_marker_properties()
                self.update()
            self.set_checkpoint(
                checkpoint,
                reached_reward_coins if index == 0 else 0,
            )

            def after_pulse() -> None:
                if revision != self._checkpoint_sequence_revision:
                    return
                if index + 1 < len(reached):
                    animate_marker(index + 1)
                else:
                    finish_sequence()

            self.set_progress(
                checkpoint,
                animate=True,
                duration=300,
                on_finished=lambda: self.pulse_checkpoint(
                    checkpoint,
                    duration=300,
                    on_finished=after_pulse,
                ),
            )

        animate_marker(0)

    def _set_pulse(self, value: Any) -> None:
        try:
            self._pulse = float(value)
        except (TypeError, ValueError):
            self._pulse = 0.0
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.contentsRect()
        left = 4.0
        right = max(left + 1.0, float(rect.width()) - 4.0)
        width = right - left
        track = QRectF(left, 5.0, width, 8.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(GARDEN_THEME["reviewer_hud_growth_track"]))
        painter.drawRoundedRect(track, 4.0, 4.0)
        fill_width = width * max(0.0, min(100.0, self._progress)) / 100.0
        if fill_width > 0:
            gradient = QLinearGradient(left, 0.0, right, 0.0)
            gradient.setColorAt(0.0, QColor(GARDEN_THEME["reviewer_hud_growth"]))
            gradient.setColorAt(1.0, QColor(GARDEN_THEME["reviewer_hud_growth_strong"]))
            painter.setBrush(gradient)
            painter.drawRoundedRect(QRectF(left, 5.0, fill_width, 8.0), 4.0, 4.0)
        for checkpoint in (self._checkpoints if self.property("showMarkers") else ()):
            natural_x = left + width * checkpoint / 100.0
            # Keep endpoint markers clear of the rounded track edge. Interior
            # checkpoint coordinates remain data-driven and visually exact.
            x = max(left + 2.5, min(right - 2.5, natural_x))
            is_next = checkpoint == self._next_checkpoint
            is_completed = self._progress + 0.001 >= checkpoint and not is_next
            is_pulsing = checkpoint == self._pulse_checkpoint
            color = (
                GARDEN_THEME["reviewer_hud_coin"]
                if is_next
                else GARDEN_THEME["reviewer_hud_growth"]
                if is_completed
                else GARDEN_THEME["text_muted"]
            )
            painter.setBrush(QColor(color))
            if is_completed or is_next:
                size = 7.0 + (2.0 * self._pulse if is_pulsing else 0.0)
                painter.setPen(QPen(
                    QColor(GARDEN_THEME["reviewer_hud_growth_track"]),
                    1.5,
                ))
                painter.save()
                painter.translate(x, 9.0)
                painter.rotate(45.0)
                painter.drawRoundedRect(
                    QRectF(-size / 2.0, -size / 2.0, size, size),
                    1.0,
                    1.0,
                )
                painter.restore()
            else:
                diameter = 4.5 + (1.0 * self._pulse if is_pulsing else 0.0)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QRectF(
                    x - diameter / 2.0,
                    9.0 - diameter / 2.0,
                    diameter,
                    diameter,
                ))
        painter.end()


class _MiniProgressRing(QWidget):  # type: ignore[misc,valid-type]
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._progress = 0
        self.setFixedSize(36, 36)
        _set_decoration(self)

    def set_progress(self, value: int) -> None:
        self._progress = max(0, min(100, int(value or 0)))
        self.setProperty("progressPercent", self._progress)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(3.5, 3.5, 29.0, 29.0)
        painter.setPen(QPen(QColor(GARDEN_THEME["reviewer_hud_growth_track"]), 3.0))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(GARDEN_THEME["reviewer_hud_growth"]), 3.0))
        painter.drawArc(rect, 90 * 16, -round(360 * 16 * self._progress / 100))
        painter.end()


class ReviewGardenHud(QFrame):  # type: ignore[misc,valid-type]
    """One mounted reviewer HUD whose child values update in place."""

    def __init__(
        self,
        parent: Any,
        *,
        on_open_garden: Callback = None,
        on_open_plant: Callback = None,
        on_open_collection: Callback = None,
        on_select_plant: Callback = None,
        on_choose_plant: Callback = None,
        on_toggle_collapsed: Callback = None,
        on_request_answer_controls: Callback = None,
        on_expand_rewards: Callback = None,
        on_effects_overflow: Callback = None,
        on_open_reward: Callback = None,
        resolve_reward_art: Callback = None,
        animations_enabled: bool = True,
    ) -> None:
        _require_qt()
        if parent is None:
            raise ValueError("ReviewGardenHud requires a reviewer viewport parent")
        super().__init__(parent)
        self._viewport_parent = parent
        self._on_open_garden = on_open_garden
        self._on_open_plant = on_open_plant
        self._on_open_collection = on_open_collection
        self._on_select_plant = on_select_plant
        self._on_choose_plant = on_choose_plant
        self._on_toggle_collapsed = on_toggle_collapsed
        self._on_request_answer_controls = on_request_answer_controls
        self._answer_controls_resize_revision = 0
        self._on_expand_rewards = on_expand_rewards
        self._on_effects_overflow = on_effects_overflow
        self._on_open_reward = on_open_reward
        self._resolve_reward_art = resolve_reward_art
        self._animations_enabled = bool(animations_enabled)
        self._projection: ReviewerHudProjection | None = None
        self._plant_selector_menu: Any | None = None
        self._plant_full_pixmap: Any | None = None
        self._disposed = False
        self._layout_reposition_pending = False
        self._collapsed = False
        self._body_compact_level = 0
        self._effect_details_requested = False
        self._dock = "right"
        self._revision = 0
        self._art_key: tuple[Any, ...] | None = None
        self._coin_animation: Any | None = None
        self._committed_coin_balance: int | None = None
        self._displayed_coin_balance = 0
        self._coin_feedback_revision = 0
        self._growth_feedback_revision = 0
        self._today_feedback_revision = 0
        self._session_feedback_revision = 0
        self._art_animation: Any | None = None
        self._plant_motion_animation: Any | None = None
        self._plant_motion_source: Any | None = None
        self._plant_motion_origin: tuple[int, int] | None = None
        self._answer_row_animation: Any | None = None
        self._today_animation: Any | None = None
        self._today_copy_animation: Any | None = None
        self._reward_reveal_animation: Any | None = None
        self._session_count_animation: Any | None = None
        self._reward_full_pixmap: Any | None = None
        self._celebration_revision = 0
        self._current_reward: Any | None = None
        self._reward_details_expanded = False
        self._reward_minimum_hold_elapsed = False
        self._reward_next_commit_seen = False
        self._reward_reveal_state: RewardRevealState = "hidden"
        # Opening an older history row temporarily replaces the reveal's
        # contents, but it must not replace the live reward lifecycle.  Keep
        # the live event and its remaining hold here so it can be restored
        # without another fade, celebration, or queue insertion.
        self._history_reward_inspection: dict[str, Any] | None = None
        self._reward_presentation_mode = ""
        self._full_bloom_bundle: Any | None = None
        self._settled_full_bloom_bundle: Any | None = None
        self._stage_change_bundle: Any | None = None
        # Routine bundles compact directly into totals, so this queue contains
        # only major events and must not evict one merely because answers were
        # completed quickly.
        self._reward_queue: deque[Any] = deque()
        self._checkpoint_pending_bundles: list[Any] = []
        self._reward_history: deque[Any] = deque()
        self._reward_history_page = 0
        self._reward_art_cache: dict[str, Any] = {}
        self._seen_bundle_ids: set[str] = set()
        self._seen_commit_ids: set[str] = set()
        self._unseen_major = 0
        self._session_totals = (0, 0, 0)
        self._displayed_session_totals = (0, 0, 0)
        self._session_has_results = False
        self._deferred_coin_update: tuple[int, bool] | None = None
        self._deferred_session_snapshot: Any | None = None
        self._checkpoint_feedback_callback_registered = False
        self._applying_deferred_checkpoint_feedback = False
        self._today_completion_feedback_active = False
        self._routine_projection_feedback_active = False

        self.setObjectName("ankiGardenReviewerHud")
        self.setProperty("semanticId", "reviewer.hud")
        self.setProperty("reviewerOverlay", True)
        self.setProperty("hudMounted", True)
        self.setProperty("hudCollapsed", False)
        self.setProperty("hudDock", "right")
        self.setProperty("hudContentHeight", 0)
        self.setProperty("hudRewardVisible", False)
        self.setProperty("hudRewardMinimumHoldElapsed", False)
        self.setProperty("hudRewardNextCommitSeen", False)
        self.setProperty("hudRewardRevealState", "hidden")
        self.setProperty("hudRewardHistoryCount", 0)
        self.setProperty("hudUnseenMajorRewards", 0)
        self.setProperty("hudHistoricalRewardInspection", False)
        self.setProperty("hudSessionVisible", False)
        self.setProperty("hudRewardDockVisible", False)
        self.setProperty("hudBodyCompactLevel", 0)
        self.setProperty("hudOptionalEffectsCollapsed", False)
        self.setProperty("hudOptionalArtworkCompact", False)
        self.setProperty("hudOptionalCheckpointCopyCollapsed", False)
        self.setProperty("motionEnabled", self._animations_enabled)
        self.setProperty("hudAnswerRowSwapMs", _ANSWER_ROW_SWAP_MS)
        self.setProperty("hudProgressFillMs", _PROGRESS_FILL_MS)
        self.setProperty(
            "hudRoutineSessionReleaseDelayMs", _ROUTINE_SESSION_RELEASE_MS
        )
        self.setProperty("hudPlantPulseMs", _PLANT_PULSE_MS)
        self.setProperty("hudFullBloomPulseMs", _FULL_BLOOM_PULSE_MS)
        self.setProperty("hudSessionHighlightMs", _SESSION_HIGHLIGHT_MS)
        self.setProperty(
            "hudNextProjectionRestoreMs", _NEXT_PROJECTION_RESTORE_MS
        )
        self.setProperty("reviewerControlClearance", HUD_CONTROLS_CLEARANCE)
        self.setProperty(
            "hudAnswerControlsSchemaVersion",
            HUD_ANSWER_CONTROLS_SCHEMA_VERSION,
        )
        self.setProperty("hudAnswerControlsRect", None)
        self.setProperty("hudAnswerControlsTop", None)
        self.setProperty("hudAnswerControlsClearance", HUD_CONTROLS_CLEARANCE)
        self.setProperty("hudAnswerControlsSource", "fallback")
        self.setProperty("hudAnswerControlsMeasured", False)
        self.setProperty("hudAnswerControlsViewport", None)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Anki Garden review progress")
        self._apply_style()
        self._build_shell()

        self._reward_timer = QTimer(self)
        self._reward_timer.setSingleShot(True)
        self._reward_timer.timeout.connect(self._mark_reward_hold_elapsed)
        try:
            parent.installEventFilter(self)
        except Exception:
            self._viewport_parent = None
        self.show()
        self.reposition()

    @property
    def widget(self) -> Any:
        return self

    @property
    def projection(self) -> ReviewerHudProjection | None:
        return self._projection

    @property
    def reward_history(self) -> tuple[Any, ...]:
        return tuple(self._reward_history)

    @property
    def active_reward_bundle(self) -> Any | None:
        return self._current_reward

    def export_reward_state(self) -> dict[str, Any]:
        """Preserve the exact readable and queued reward state on remount."""

        pending: list[Any] = []
        pending_ids: set[str] = set()
        for bundle in (
            *tuple(self._checkpoint_pending_bundles),
            *tuple(self._reward_queue),
        ):
            identity = _bundle_id(bundle)
            if not identity or identity in pending_ids:
                continue
            pending_ids.add(identity)
            pending.append(bundle)
        current = ReviewGardenHud._capture_current_reward_runtime_state(self)
        current_identity = _bundle_id(current.get("bundle")) if current else ""
        if current_identity:
            pending = [
                bundle
                for bundle in pending
                if _bundle_id(bundle) != current_identity
            ]
        return {
            "seen_bundle_ids": tuple(self._seen_bundle_ids),
            "seen_commit_ids": tuple(getattr(self, "_seen_commit_ids", set())),
            "history": tuple(self._reward_history),
            "pending": tuple(pending),
            "unseen_major": max(0, int(self._unseen_major)),
            "current": current,
        }

    def _capture_current_reward_runtime_state(self) -> dict[str, Any] | None:
        inspected = getattr(self, "_history_reward_inspection", None)
        if inspected is not None:
            return dict(inspected)
        if self._current_reward is None:
            return None
        remaining = 0
        if not self._reward_minimum_hold_elapsed:
            try:
                remaining = max(0, int(self._reward_timer.remainingTime()))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                remaining = 0
        return {
            "bundle": self._current_reward,
            "minimum_hold_elapsed": bool(self._reward_minimum_hold_elapsed),
            "details_expanded": bool(self._reward_details_expanded),
            "next_commit_seen": bool(
                getattr(self, "_reward_next_commit_seen", False)
            ),
            "reveal_state": ReviewGardenHud._current_reward_reveal_state(self),
            "hold_remaining_ms": remaining,
        }

    def restore_reward_state(self, snapshot: Mapping[str, Any] | None) -> None:
        if not isinstance(snapshot, Mapping):
            return
        self._seen_bundle_ids.update(
            str(identity)
            for identity in tuple(snapshot.get("seen_bundle_ids", ()) or ())
            if str(identity)
        )
        seen_commit_ids = getattr(self, "_seen_commit_ids", None)
        if seen_commit_ids is None:
            seen_commit_ids = set()
            self._seen_commit_ids = seen_commit_ids
        seen_commit_ids.update(
            str(identity)
            for identity in tuple(snapshot.get("seen_commit_ids", ()) or ())
            if str(identity)
        )
        self._reward_history.clear()
        self._reward_history.extend(
            bundle
            for bundle in tuple(snapshot.get("history", ()) or ())
            if _bundle_id(bundle)
        )
        self._reward_history_page = 0
        self._checkpoint_pending_bundles.clear()
        self._reward_queue.clear()
        current = snapshot.get("current")
        current_state = current if isinstance(current, Mapping) else None
        current_bundle = current_state.get("bundle") if current_state else None
        current_identity = _bundle_id(current_bundle)
        self._reward_queue.extend(
            bundle
            for bundle in tuple(snapshot.get("pending", ()) or ())
            if _bundle_id(bundle) and _bundle_id(bundle) != current_identity
        )
        self._unseen_major = max(0, int(snapshot.get("unseen_major", 0) or 0))
        self.setProperty("hudRewardHistoryCount", len(self._reward_history))
        self._sync_history_rows()
        self._sync_unseen_badge()
        self._history_reward_inspection = None
        self.setProperty("hudHistoricalRewardInspection", False)
        if current_identity:
            self._show_reward(
                current_bundle,
                expanded=bool(current_state.get("details_expanded", False)),
                presentation="restored",
                minimum_hold_elapsed=bool(
                    current_state.get("minimum_hold_elapsed", False)
                ),
                next_commit_seen=bool(
                    current_state.get("next_commit_seen", False)
                ),
                reveal_state=str(current_state.get("reveal_state", "") or ""),
                hold_remaining_ms=max(
                    0,
                    int(current_state.get("hold_remaining_ms", 0) or 0),
                ),
            )
        elif not self._collapsed and self._current_reward is None and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())
        else:
            self._sync_reward_dock_visibility()

    def set_callbacks(
        self,
        *,
        on_open_garden: Callback = None,
        on_open_plant: Callback = None,
        on_open_collection: Callback = None,
        on_select_plant: Callback = None,
        on_choose_plant: Callback = None,
        on_toggle_collapsed: Callback = None,
        on_request_answer_controls: Callback = None,
        on_expand_rewards: Callback = None,
        on_effects_overflow: Callback = None,
        on_open_reward: Callback = None,
        resolve_reward_art: Callback = None,
        animations_enabled: bool | None = None,
    ) -> None:
        self._on_open_garden = on_open_garden
        self._on_open_plant = on_open_plant
        self._on_open_collection = on_open_collection
        self._on_select_plant = on_select_plant
        self._on_choose_plant = on_choose_plant
        self._on_toggle_collapsed = on_toggle_collapsed
        self._on_request_answer_controls = on_request_answer_controls
        self._on_expand_rewards = on_expand_rewards
        self._on_effects_overflow = on_effects_overflow
        self._on_open_reward = on_open_reward
        self._resolve_reward_art = resolve_reward_art
        if animations_enabled is not None:
            self._animations_enabled = bool(animations_enabled)
            self.setProperty("motionEnabled", self._animations_enabled)
            if not self._animations_enabled:
                self._settle_plant_motion()
                self._art_region.setProperty("artPulse", False)
                _repolish(self._art_region)
                self._session_feedback_revision += 1
                self._stop_session_count_animation()
                self._set_session_metric_values(self._session_totals)
                self._clear_session_highlight(self._session_feedback_revision)
        self._header.set_callback(self._open_garden)
        self._plant_card.set_callback(self._open_plant)

    def _apply_style(self) -> None:
        t = GARDEN_THEME
        self.setStyleSheet(
            "QFrame#ankiGardenReviewerHud {"
            f"background:{t['reviewer_hud_shell']};"
            "border:1px solid rgba(112,220,170,77);"
            "border-radius:14px;}"
            "QFrame#reviewerHudHeader {background:transparent;border:0;"
            "border-bottom:1px solid " + t["reviewer_hud_divider"] + ";}"
            "QFrame#reviewerHudHeader:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame[hudCard='true'] {background:" + t["reviewer_hud_surface"] + ";border-radius:12px;}"
            "QFrame[hudCard='true'][cardRole='subtle'] {border:1px solid rgba(112,220,170,26);}"
            "QFrame[hudCard='true'][cardRole='standard'] {background:transparent;border:0;}"
            "QFrame#reviewerHudTodayCard[completionSettling='true'] {border-color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QFrame#reviewerHudPlantCard:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudPlantCard[celebration='stage-change'] {border-color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QFrame#reviewerHudPlantCard[celebration='full-bloom'] {border-color:" + t["reviewer_hud_coin"] + ";}"
            "QFrame#reviewerHudArtRegion {background:qradialgradient(cx:0.5,cy:0.54,radius:0.52,"
            "fx:0.5,fy:0.54,stop:0 rgba(103,220,169,42),stop:1 rgba(13,48,39,0));border:0;}"
            "QFrame#reviewerHudArtRegion[artPulse='true'] {background:qradialgradient(cx:0.5,cy:0.54,radius:0.56,"
            "fx:0.5,fy:0.54,stop:0 rgba(132,237,189,78),stop:1 rgba(13,48,39,0));}"
            "QFrame#reviewerHudArtRegion[fullBloomSettled='true'] {background:qradialgradient(cx:0.5,cy:0.54,radius:0.58,"
            "fx:0.5,fy:0.54,stop:0 rgba(240,194,79,42),stop:0.42 rgba(103,220,169,28),stop:1 rgba(13,48,39,0));}"
            "QFrame#reviewerHudArtRegion[fullBloomLightRays='true'] {background:qradialgradient(cx:0.5,cy:0.52,radius:0.62,"
            "fx:0.5,fy:0.52,stop:0 rgba(240,194,79,96),stop:0.45 rgba(103,220,169,52),stop:1 rgba(13,48,39,0));}"
            "QFrame#reviewerHudNextAnswer {background:transparent;border:0;}"
            "QFrame#reviewerHudNextAnswer[resultState='applied'] {background:rgba(103,220,169,30);}"
            "QFrame#reviewerHudGrowthDestination {background:rgba(103,220,169,13);"
            "border:1px solid rgba(112,220,170,43);border-radius:9px;}"
            "QLabel[hudGrowthDestinationHeading='true'] {color:" + t["text_primary"] + ";"
            "font-size:12px;font-weight:650;}"
            "QFrame#reviewerHudRewardDockSurface {background:transparent;border:0;}"
            "QFrame#reviewerHudRewardReveal {background:transparent;border:0;border-radius:11px;}"
            "QFrame#reviewerHudRewardReveal[activeMilestone='true'] {"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 rgba(241,201,75,9),stop:0.34 rgba(241,201,75,0));}"
            "QFrame#reviewerHudRewardAccent {border:0;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 rgba(241,201,75,0),stop:0.5 rgba(241,201,75,140),"
            "stop:1 rgba(241,201,75,0));}"
            "QFrame#reviewerHudRewardDivider {background:" + t["reviewer_hud_divider"] + ";border:0;}"
            "QFrame#reviewerHudSessionFooter {background:transparent;border:0;border-radius:0;}"
            "QFrame#reviewerHudSessionFooter[historyAvailable='true']:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudRewardHistory {background:transparent;border:0;}"
            "QFrame[hudHistoryRow='true'] {background:transparent;border:0;border-radius:7px;}"
            "QFrame[hudHistoryRow='true']:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudCollapsedTab {background:" + t["reviewer_hud_shell"] + ";"
            "border:1px solid " + t["reviewer_hud_border"] + ";border-radius:14px;}"
            "QLabel {color:" + t["text_primary"] + ";font-size:13px;background:transparent;border:0;}"
            "QLabel[hudSessionMetric='true'] {font-size:"
            + str(_SESSION_METRIC_FONT_PX)
            + "px;}"
            "QLabel[hudHeaderTitle='true'] {font-size:15px;font-weight:600;}"
            "QLabel[hudCoin='true'] {color:" + t["reviewer_hud_coin"] + ";font-weight:650;}"
            "QLabel[hudCoinDelta='true'] {color:" + t["reviewer_hud_coin"] + ";font-size:12px;font-weight:700;}"
            "QLabel[coinPulse='true'] {background:" + t["reviewer_hud_coin_soft"] + ";border-radius:8px;}"
            "QLabel[hudMuted='true'] {color:" + t["text_secondary"] + ";font-size:12px;}"
            "QLabel#reviewerHudTodayDetail[nearComplete='true'] {color:"
            + t["reviewer_hud_growth_strong"] + ";}"
            "QLabel[hudPlantName='true'] {font-size:18px;font-weight:650;}"
            "QLabel[hudStage='true'] {font-size:13px;font-weight:600;}"
            "QLabel[hudStage='true'][fullBloomAccent='true'] {color:" + t["reviewer_hud_coin"] + ";}"
            "QLabel[hudRewardTitle='true'] {font-size:14px;font-weight:600;}"
            "QLabel[hudGrowth='true'] {color:" + t["reviewer_hud_growth_strong"] + ";font-weight:700;}"
            "QLabel[hudEyebrow='true'] {color:" + t["text_secondary"] + ";font-size:11px;font-weight:700;}"
            "QLabel#reviewerHudRewardArt {background:rgba(103,220,169,18);border:0;border-radius:12px;}"
            "QLabel#reviewerHudRewardArt[milestoneMedallion='true'] {"
            "background:qradialgradient(cx:0.5,cy:0.5,radius:0.62,"
            "fx:0.5,fy:0.5,stop:0 rgba(241,201,75,34),"
            "stop:0.62 rgba(241,201,75,8),stop:1 rgba(241,201,75,0));"
            "border:1px solid rgba(241,201,75,89);border-radius:12px;}"
            "QLabel[hudRarity='true'] {background:rgba(103,220,169,28);"
            "color:" + t["reviewer_hud_growth_strong"] + ";border-radius:8px;padding:2px 7px;font-size:12px;font-weight:650;}"
            "QLabel[hudRarity='true'][rarityTone='uncommon'] {background:rgba(121,200,232,34);color:" + t["info"] + ";}"
            "QLabel[hudRarity='true'][rarityTone='rare'] {background:rgba(184,153,234,38);color:#D0B8F2;}"
            "QLabel[hudRarity='true'][rarityTone='exceptional'] {background:" + t["reviewer_hud_coin_soft"] + ";color:" + t["reviewer_hud_coin"] + ";}"
            "QFrame[hudEffectChip='true'] {background:" + t["reviewer_hud_surface_raised"] + ";"
            "color:" + t["text_primary"] + ";border:0;border-radius:8px;padding:0;font-size:12px;}"
            "QLabel[hudEffectLabel='true'] {font-size:12px;}"
            "QFrame[hudRewardMetric='true'] {background:rgba(255,255,255,10);border:0;border-radius:7px;}"
            "QLabel[hudRewardChip='true'] {background:transparent;color:" + t["text_primary"] + ";"
            "border:0;padding:0;font-size:11px;}"
            "QLabel[hudRewardChip='true'][metricTone='growth'] {color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QLabel[hudCollapsedStatus='true'] {color:" + t["text_secondary"] + ";"
            "font-size:10px;font-weight:650;}"
            "QLabel[hudCollapsedNext='true'] {color:" + t["reviewer_hud_growth_strong"] + ";"
            "font-size:9px;font-weight:700;}"
            "QLabel[metricChanged='true'] {background:rgba(103,220,169,24);border-radius:6px;}"
            "QProgressBar#reviewerHudTodayProgress {background:" + t["reviewer_hud_growth_track"] + ";"
            "border:0;border-radius:3px;min-height:6px;max-height:6px;}"
            "QProgressBar#reviewerHudTodayProgress::chunk {background:" + t["reviewer_hud_growth"] + ";border-radius:3px;}"
            "QToolButton {background:transparent;border:0;border-radius:8px;color:" + t["text_primary"] + ";padding:0;}"
            "QToolButton:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QToolButton#reviewerHudEffectsOverflow {background:transparent;color:" + t["text_secondary"] + ";"
            "padding:1px 0;font-size:12px;font-weight:600;text-align:right;}"
            "QToolButton#reviewerHudEffectsOverflow:hover {background:transparent;color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QToolButton#reviewerHudRewardDetailsToggle {background:transparent;color:"
            + t["reviewer_hud_growth_strong"]
            + ";padding:0;font-size:12px;font-weight:650;text-align:right;}"
            "QToolButton#reviewerHudRewardDetailsToggle:hover {background:transparent;color:"
            + t["reviewer_hud_growth"] + ";}"
            "QToolButton#reviewerHudSelectPlant {background:" + t["action_accent"] + ";"
            "border:1px solid " + t["action_accent"] + ";color:" + t["action_text"] + ";"
            "border-radius:8px;padding:0 10px;font-size:12px;font-weight:650;text-align:center;}"
            "QToolButton#reviewerHudSelectPlant:hover {background:" + t["action_hover"] + ";"
            "border-color:" + t["action_hover"] + ";}"
            "QToolButton#reviewerHudSelectPlant:pressed {background:" + t["action_pressed"] + ";"
            "border-color:" + t["action_pressed"] + ";}"
            "QScrollArea#reviewerHudBodyScroll {background:transparent;border:0;}"
            "QScrollArea#reviewerHudRewardScroll {background:transparent;border:0;}"
            "QWidget#reviewerHudBodyContents {background:transparent;}"
            "QWidget#reviewerHudRewardScrollContents {background:transparent;}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor("#66000000"))
        self.setGraphicsEffect(shadow)

    def _icon(self, name: str, size: int, color: str) -> Any:
        try:
            from .icons import garden_icon

            return garden_icon(name, color=color, logical_size=size)
        except Exception:
            return None

    def _icon_pixmap(self, name: str, size: int, color: str) -> Any:
        icon = self._icon(name, size, color)
        try:
            return icon.pixmap(size, size) if icon is not None else QPixmap()
        except Exception:
            return QPixmap()

    def _build_shell(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._expanded = QFrame(self)
        self._expanded.setObjectName("reviewerHudExpanded")
        self._expanded.setProperty("semanticId", "reviewer.hud.expanded")
        expanded_layout = QVBoxLayout(self._expanded)
        expanded_layout.setContentsMargins(0, 0, 0, 0)
        expanded_layout.setSpacing(0)

        self._header = _ClickableFrame(self._expanded, self._open_garden)
        self._header.setObjectName("reviewerHudHeader")
        self._header.setProperty("semanticId", "reviewer.hud.header")
        self._header.setFixedHeight(44)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(
            HUD_HEADER_LEFT_INSET,
            0,
            HUD_HEADER_RIGHT_INSET,
            0,
        )
        header_layout.setSpacing(0)
        self._title_group = QFrame(self._header)
        self._title_group.setObjectName("reviewerHudTitleGroup")
        _set_decoration(self._title_group)
        title_layout = QHBoxLayout(self._title_group)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        leaf = QLabel(self._header)
        leaf.setFixedSize(20, 20)
        leaf.setPixmap(self._icon_pixmap("growth", 19, GARDEN_THEME["reviewer_hud_growth"]))
        leaf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(leaf)
        title_layout.addWidget(leaf)
        self._header_title = QLabel("Anki Garden", self._header)
        self._header_title.setObjectName("reviewerHudHeaderTitle")
        self._header_title.setProperty("hudHeaderTitle", True)
        self._header_title.setMinimumWidth(0)
        _set_decoration(self._header_title)
        title_layout.addWidget(self._header_title)
        header_layout.addWidget(self._title_group)
        header_layout.addStretch(1)
        self._header_actions = QFrame(self._header)
        self._header_actions.setObjectName("reviewerHudHeaderActions")
        title_width = max(0, int(self._title_group.sizeHint().width()))
        header_actions_width = reviewer_hud_header_actions_width(title_width)
        self._header_actions.setFixedWidth(header_actions_width)
        _set_decoration(self._header_actions)
        actions_layout = QHBoxLayout(self._header_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addStretch(1)
        self._coin_cluster = QFrame(self._header_actions)
        self._coin_cluster.setObjectName("reviewerHudCoinCluster")
        self._coin_cluster.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        _set_decoration(self._coin_cluster)
        self.setProperty("hudHeaderTitleNaturalWidth", title_width)
        self.setProperty(
            "hudHeaderBalanceReservedWidth",
            header_actions_width,
        )
        coin_layout = QHBoxLayout(self._coin_cluster)
        coin_layout.setContentsMargins(0, 0, 0, 0)
        coin_layout.setSpacing(5)
        self._coin_icon = QLabel(self._coin_cluster)
        self._coin_icon.setFixedSize(17, 17)
        self._coin_icon.setPixmap(self._icon_pixmap("coin", 16, GARDEN_THEME["reviewer_hud_coin"]))
        _set_decoration(self._coin_icon)
        coin_layout.addWidget(self._coin_icon)
        self._coin_balance = QLabel("0", self._coin_cluster)
        self._coin_balance.setProperty("hudCoin", True)
        apply_tabular_numerals(self._coin_balance)
        self._coin_balance.setMinimumWidth(28)
        self._coin_balance.setMaximumWidth(74)
        self._coin_balance.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _set_decoration(self._coin_balance)
        coin_layout.addWidget(self._coin_balance)
        self._coin_delta = QLabel("", self._coin_cluster)
        self._coin_delta.setProperty("hudCoinDelta", True)
        apply_tabular_numerals(self._coin_delta)
        self._coin_delta.hide()
        _set_decoration(self._coin_delta)
        coin_layout.addWidget(self._coin_delta)
        actions_layout.addWidget(self._coin_cluster)
        self._collapse_button = QToolButton(self._header_actions)
        self._collapse_button.setObjectName("reviewerHudCollapseButton")
        self._collapse_button.setProperty("semanticId", "reviewer.hud.collapse")
        self._collapse_button.setFixedSize(32, 32)
        self._collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._collapse_button.setAccessibleName("Collapse Anki Garden review panel")
        self._collapse_button.setIcon(self._icon("chevron-up", 18, GARDEN_THEME["text_primary"]))
        self._collapse_button.clicked.connect(self._toggle_from_control)
        actions_layout.addWidget(self._collapse_button)
        header_layout.addWidget(self._header_actions)
        expanded_layout.addWidget(self._header)

        self._body_scroll = QScrollArea(self._expanded)
        self._body_scroll.setObjectName("reviewerHudBodyScroll")
        self._body_scroll.setProperty("semanticId", "reviewer.hud.body-scroll")
        self._body_scroll.setWidgetResizable(True)
        self._body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._body_contents = QWidget(self._body_scroll)
        self._body_contents.setObjectName("reviewerHudBodyContents")
        # Every child in the HUD either elides or wraps.  Let the scroll-area
        # viewport own the horizontal size so long fixture text cannot make a
        # hidden horizontal range while the scrollbar policy is AlwaysOff.
        self._body_contents.setMinimumWidth(0)
        self._body_contents.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        body = QVBoxLayout(self._body_contents)
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(10)
        self._body_layout = body
        self._build_today(body)
        self._build_plant(body)
        self._body_scroll.setWidget(self._body_contents)
        expanded_layout.addWidget(self._body_scroll, 1)
        self._build_reward_dock(expanded_layout)

        self._build_collapsed()
        root.addWidget(self._expanded)
        root.addWidget(self._collapsed_tab)
        self._collapsed_tab.hide()

    def _build_today(self, body: Any) -> None:
        self._today_card = QFrame(self._body_contents)
        self._today_card.setObjectName("reviewerHudTodayCard")
        self._today_card.setProperty("semanticId", "reviewer.hud.today")
        self._today_card.setProperty("hudCard", True)
        self._today_card.setProperty("cardRole", "subtle")
        self._today_card.setProperty("completionSettling", False)
        self._today_card.setMinimumHeight(68)
        self._today_card.setMaximumHeight(82)
        layout = QVBoxLayout(self._today_card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._today_check = QLabel(self._today_card)
        self._today_check.setFixedSize(18, 18)
        self._today_check.setPixmap(self._icon_pixmap("check-circle", 17, GARDEN_THEME["reviewer_hud_growth"]))
        _set_decoration(self._today_check)
        row.addWidget(self._today_check)
        self._today_heading = _ElidedLabel("Today’s cards", self._today_card)
        self._today_heading.setProperty("hudStage", True)
        _set_decoration(self._today_heading)
        row.addWidget(self._today_heading, 1)
        self._today_value = QLabel("", self._today_card)
        apply_tabular_numerals(self._today_value)
        _set_decoration(self._today_value)
        row.addWidget(self._today_value)
        layout.addLayout(row)
        self._today_progress = QProgressBar(self._today_card)
        self._today_progress.setObjectName("reviewerHudTodayProgress")
        self._today_progress.setProperty(
            "semanticId",
            "reviewer.hud.today-progress",
        )
        self._today_progress.setTextVisible(False)
        self._today_progress.setRange(0, _TODAY_PROGRESS_SCALE)
        _set_decoration(self._today_progress)
        layout.addWidget(self._today_progress)
        self._today_detail = QLabel("", self._today_card)
        self._today_detail.setObjectName("reviewerHudTodayDetail")
        self._today_detail.setProperty("hudMuted", True)
        self._today_detail.setProperty("nearComplete", False)
        apply_tabular_numerals(self._today_detail)
        _set_decoration(self._today_detail)
        layout.addWidget(self._today_detail)
        body.addWidget(self._today_card)

    def _build_plant(self, body: Any) -> None:
        self._plant_card = _ClickableFrame(self._body_contents, self._open_plant)
        self._plant_card.setObjectName("reviewerHudPlantCard")
        self._plant_card.setProperty("semanticId", "reviewer.hud.plant")
        self._plant_card.setProperty("hudCard", True)
        self._plant_card.setProperty("cardRole", "standard")
        self._plant_card.setProperty("celebration", "")
        self._plant_card.setProperty("fullBloomSettled", False)
        self._plant_layout = QVBoxLayout(self._plant_card)
        layout = self._plant_layout
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(6)
        metadata = QHBoxLayout()
        self._species = _ElidedLabel("", self._plant_card)
        self._species.setObjectName("reviewerHudPlantClass")
        self._species.setProperty("hudMuted", True)
        _set_decoration(self._species)
        metadata.addWidget(self._species, 1)
        # Bed remains engine metadata but is intentionally absent from the
        # persistent reviewer surface.
        self._bed = QLabel("", self._plant_card)
        self._bed.setProperty("hudMuted", True)
        _set_decoration(self._bed)
        self._bed.hide()
        layout.addLayout(metadata)
        self._plant_name = _TwoLineLabel(self._plant_card)
        self._plant_name.setObjectName("reviewerHudPlantName")
        self._plant_name.setProperty("hudPlantName", True)
        _set_decoration(self._plant_name)
        layout.insertWidget(0, self._plant_name)

        self._art_region = _ArtRegion(self._plant_card)
        self._art_region.setObjectName("reviewerHudArtRegion")
        self._art_region.setProperty("groundShadowVisible", True)
        self._art_region.setFixedHeight(146)
        art_layout = QVBoxLayout(self._art_region)
        art_layout.setContentsMargins(0, 2, 0, 2)
        self._plant_art = QLabel(self._art_region)
        self._plant_art.setFixedSize(136, 136)
        self._plant_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(self._plant_art)
        art_layout.addWidget(self._plant_art, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._art_region)

        stage_row = QHBoxLayout()
        self._stage = _ElidedLabel("", self._plant_card)
        self._stage.setProperty("hudStage", True)
        apply_tabular_numerals(self._stage)
        _set_decoration(self._stage)
        stage_row.addWidget(self._stage, 1)
        self._percent = QLabel("0%", self._plant_card)
        self._percent.setProperty("hudMuted", True)
        apply_tabular_numerals(self._percent)
        _set_decoration(self._percent)
        layout.addLayout(stage_row)
        self._progress_destination = QLabel("", self._plant_card)
        self._progress_destination.setProperty("hudMuted", True)
        _set_decoration(self._progress_destination)
        layout.addWidget(self._progress_destination)
        layout.addWidget(self._percent)
        self._checkpoint_track = CheckpointTrack(self._plant_card)
        layout.addWidget(self._checkpoint_track)
        self._checkpoint_distance_row = QFrame(self._plant_card)
        self._checkpoint_distance_row.setObjectName("reviewerHudCheckpointDistanceRow")
        self._checkpoint_distance_row.setProperty(
            "semanticId", "reviewer.hud.checkpoint-distance"
        )
        checkpoint_distance_layout = QVBoxLayout(self._checkpoint_distance_row)
        checkpoint_distance_layout.setContentsMargins(0, 0, 0, 0)
        checkpoint_distance_layout.setSpacing(2)
        self._checkpoint = _ElidedLabel("", self._checkpoint_distance_row)
        self._checkpoint.setProperty("hudMuted", True)
        apply_tabular_numerals(self._checkpoint)
        _set_decoration(self._checkpoint)
        checkpoint_distance_layout.addWidget(self._checkpoint)
        self._checkpoint_estimate = QLabel("", self._checkpoint_distance_row)
        self._checkpoint_estimate.setProperty("hudMuted", True)
        apply_tabular_numerals(self._checkpoint_estimate)
        self._checkpoint_estimate.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        _set_decoration(self._checkpoint_estimate)
        checkpoint_distance_layout.addWidget(self._checkpoint_estimate)
        self._checkpoint_distance_row.hide()
        layout.addWidget(self._checkpoint_distance_row)

        self._checkpoint_reward_row = QFrame(self._plant_card)
        self._checkpoint_reward_row.setObjectName("reviewerHudCheckpointRewardRow")
        checkpoint_reward_layout = QHBoxLayout(self._checkpoint_reward_row)
        checkpoint_reward_layout.setContentsMargins(0, 0, 0, 0)
        checkpoint_reward_layout.setSpacing(8)
        self._checkpoint_reward_context = QLabel(
            "Checkpoint reward", self._checkpoint_reward_row
        )
        self._checkpoint_reward_context.setProperty("hudMuted", True)
        _set_decoration(self._checkpoint_reward_context)
        checkpoint_reward_layout.addWidget(self._checkpoint_reward_context, 1)
        checkpoint_coin = QLabel(self._checkpoint_reward_row)
        checkpoint_coin.setFixedSize(15, 15)
        checkpoint_coin.setPixmap(
            self._icon_pixmap("coin", 14, GARDEN_THEME["reviewer_hud_coin"])
        )
        _set_decoration(checkpoint_coin)
        checkpoint_reward_layout.addWidget(checkpoint_coin)
        self._checkpoint_reward = QLabel("", self._checkpoint_reward_row)
        self._checkpoint_reward.setProperty("hudCoin", True)
        apply_tabular_numerals(self._checkpoint_reward)
        _set_decoration(self._checkpoint_reward)
        checkpoint_reward_layout.addWidget(self._checkpoint_reward)
        self._checkpoint_reward_row.hide()
        layout.addWidget(self._checkpoint_reward_row)

        self._next_answer = QFrame(self._plant_card)
        self._next_answer.setObjectName("reviewerHudNextAnswer")
        self._next_answer.setProperty("semanticId", "reviewer.hud.next-card")
        self._next_answer.setProperty("legacySemanticId", "reviewer.hud.next-answer")
        self._next_answer.setProperty("resultState", "projection")
        next_layout = QHBoxLayout(self._next_answer)
        next_layout.setContentsMargins(0, 4, 0, 0)
        next_layout.setSpacing(8)
        self._next_answer_label = QLabel("Next card total:", self._next_answer)
        self._next_answer_label.setObjectName("reviewerHudNextAnswerLabel")
        _set_decoration(self._next_answer_label)
        next_layout.addWidget(self._next_answer_label, 1)
        self._next_answer_value = QLabel("", self._next_answer)
        self._next_answer_value.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._next_answer_value)
        _set_decoration(self._next_answer_value)
        next_layout.addWidget(self._next_answer_value)
        layout.addWidget(self._next_answer)
        self._plant_message = QLabel("", self._plant_card)
        self._plant_message.setProperty("hudMuted", True)
        apply_tabular_numerals(self._plant_message)
        self._plant_message.setWordWrap(True)
        _set_decoration(self._plant_message)
        self._plant_message.hide()
        layout.addWidget(self._plant_message)

        self._growth_destination = _ClickableFrame(self._plant_card)
        self._growth_destination.setObjectName("reviewerHudGrowthDestination")
        self._growth_destination.setProperty(
            "semanticId", "reviewer.hud.growth-destination"
        )
        self._growth_destination.setProperty("destinationKind", "")
        destination_layout = QHBoxLayout(self._growth_destination)
        destination_layout.setContentsMargins(9, 7, 9, 7)
        destination_layout.setSpacing(8)
        self._growth_destination_icon = QLabel(self._growth_destination)
        self._growth_destination_icon.setFixedSize(22, 22)
        self._growth_destination_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._growth_destination_icon.setPixmap(
            self._icon_pixmap(
                "growth",
                19,
                GARDEN_THEME["reviewer_hud_growth"],
            )
        )
        _set_decoration(self._growth_destination_icon)
        destination_layout.addWidget(self._growth_destination_icon)
        destination_copy = QVBoxLayout()
        destination_copy.setContentsMargins(0, 0, 0, 0)
        destination_copy.setSpacing(1)
        self._growth_destination_heading = _ElidedLabel(
            "Stored Growth", self._growth_destination
        )
        self._growth_destination_heading.setProperty(
            "hudGrowthDestinationHeading", True
        )
        _set_decoration(self._growth_destination_heading)
        destination_copy.addWidget(self._growth_destination_heading)
        self._growth_destination_detail = QLabel("", self._growth_destination)
        self._growth_destination_detail.setProperty("hudMuted", True)
        self._growth_destination_detail.setWordWrap(True)
        apply_tabular_numerals(self._growth_destination_detail)
        _set_decoration(self._growth_destination_detail)
        destination_copy.addWidget(self._growth_destination_detail)
        destination_layout.addLayout(destination_copy, 1)
        self._growth_destination.hide()
        layout.addWidget(self._growth_destination)

        self._select_plant = QToolButton(self._plant_card)
        self._select_plant.setObjectName("reviewerHudSelectPlant")
        self._select_plant.setProperty("semanticId", "reviewer.hud.select-plant")
        self._select_plant.setProperty("actionRole", "primary")
        self._select_plant.setText("Choose next plant")
        self._select_plant.setMinimumHeight(28)
        self._select_plant.setMinimumWidth(
            self._select_plant.fontMetrics().horizontalAdvance(
                self._select_plant.text()
            )
            + 22
        )
        self._select_plant.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._select_plant.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_plant.clicked.connect(self._select_another_plant)
        self._select_plant.hide()
        layout.addWidget(self._select_plant, 0, Qt.AlignmentFlag.AlignLeft)

        self._effects = QFrame(self._plant_card)
        self._effects.setObjectName("reviewerHudEffects")
        self._effects.setProperty("semanticId", "reviewer.hud.effects")
        effects_layout = QGridLayout(self._effects)
        effects_layout.setContentsMargins(0, 0, 0, 0)
        effects_layout.setHorizontalSpacing(6)
        effects_layout.setVerticalSpacing(1)
        self._effects_single_column = False
        self._effect_chips: list[Any] = []
        self._effect_icons: list[Any] = []
        self._effect_labels: list[_EffectLabel] = []
        for _index in range(2):
            chip = QFrame(self._effects)
            chip.setProperty("hudEffectChip", True)
            chip.setFixedHeight(28)
            chip.setMinimumWidth(0)
            chip.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(1, 0, 1, 0)
            chip_layout.setSpacing(1)
            icon = QLabel(chip)
            icon.setFixedSize(18, 18)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setProperty("hudEffectArtwork", True)
            _set_decoration(icon)
            chip_layout.addWidget(icon)
            label = _EffectLabel("", chip)
            label.setProperty("hudEffectLabel", True)
            apply_tabular_numerals(label)
            label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            _set_decoration(label)
            chip_layout.addWidget(label, 1)
            chip.hide()
            effects_layout.addWidget(chip, 0, len(self._effect_chips))
            self._effect_chips.append(chip)
            self._effect_icons.append(icon)
            self._effect_labels.append(label)
        self._effects_overflow = QToolButton(self._effects)
        self._effects_overflow.setObjectName("reviewerHudEffectsOverflow")
        self._effects_overflow.setProperty("semanticId", "reviewer.hud.effects-overflow")
        self._effects_overflow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._effects_overflow.setMinimumHeight(24)
        apply_tabular_numerals(self._effects_overflow)
        self._effects_overflow.clicked.connect(self._toggle_effect_details)
        self._effects_overflow.hide()
        effects_layout.addWidget(
            self._effects_overflow,
            1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignRight,
        )
        effects_layout.setColumnStretch(0, 1)
        effects_layout.setColumnStretch(1, 1)
        self._effects.hide()
        layout.addWidget(self._effects)
        self._effect_details = QLabel("", self._plant_card)
        self._effect_details.setObjectName("reviewerHudEffectDetails")
        self._effect_details.setProperty("semanticId", "reviewer.hud.effect-details")
        self._effect_details.setProperty("hudMuted", True)
        apply_tabular_numerals(self._effect_details)
        self._effect_details.setWordWrap(True)
        self._effect_details.hide()
        _set_decoration(self._effect_details)
        layout.addWidget(self._effect_details)
        body.addWidget(self._plant_card)

    def _build_reward_dock(self, expanded_layout: Any) -> None:
        # One logical dock owns a bounded scroll-body and a sticky session
        # footer. The connected surface appears only after a nonzero result or
        # while a current reveal is visible.
        self._reward_dock = QFrame(self._expanded)
        self._reward_dock.setObjectName("reviewerHudRewardDock")
        self._reward_dock.setProperty("semanticId", "reviewer.hud.reward-dock")
        dock = QVBoxLayout(self._reward_dock)
        dock.setContentsMargins(10, 0, 10, 6)
        dock.setSpacing(0)

        self._reward_surface = QFrame(self._reward_dock)
        self._reward_surface.setObjectName("reviewerHudRewardDockSurface")
        self._reward_surface.setProperty("semanticId", "reviewer.hud.reward-surface")
        surface = QVBoxLayout(self._reward_surface)
        surface.setContentsMargins(0, 0, 0, 0)
        surface.setSpacing(0)
        dock.addWidget(self._reward_surface)

        self._reward_scroll = _PreferredHeightScrollArea(self._reward_surface)
        self._reward_scroll.setObjectName("reviewerHudRewardScroll")
        self._reward_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reward_scroll.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reward_scroll.setProperty("semanticId", "reviewer.hud.reward-scroll")
        self._reward_scroll.setWidgetResizable(True)
        self._reward_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._reward_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._reward_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._reward_scroll.setMaximumHeight(_REWARD_SCROLL_MAX_HEIGHT)
        self._reward_scroll_contents = QWidget(self._reward_scroll)
        self._reward_scroll_contents.setObjectName("reviewerHudRewardScrollContents")
        self._reward_scroll_contents.setMinimumWidth(0)
        self._reward_scroll_contents.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        scroll_body = QVBoxLayout(self._reward_scroll_contents)
        scroll_body.setContentsMargins(0, 0, 0, 0)
        scroll_body.setSpacing(0)

        self._reward_reveal = QFrame(self._reward_scroll_contents)
        self._reward_reveal.setObjectName("reviewerHudRewardReveal")
        self._reward_reveal.setProperty("semanticId", "reviewer.hud.reward-reveal")
        self._reward_reveal.setMinimumHeight(_COMPACT_REWARD_MIN_HEIGHT)
        self._reward_reveal.setMaximumHeight(_COMPACT_REWARD_MAX_HEIGHT)
        reveal = QVBoxLayout(self._reward_reveal)
        reveal.setContentsMargins(12, 5, 12, 7)
        reveal.setSpacing(2)

        self._reward_accent = QFrame(self._reward_reveal)
        self._reward_accent.setObjectName("reviewerHudRewardAccent")
        self._reward_accent.setFixedHeight(1)
        self._reward_accent.hide()
        _set_decoration(self._reward_accent)
        reveal.addWidget(self._reward_accent)

        self._reward_heading = QFrame(self._reward_reveal)
        self._reward_heading.setObjectName("reviewerHudRewardHeading")
        self._reward_heading.setProperty(
            "semanticId", "reviewer.hud.reward-heading"
        )
        self._reward_heading.setMinimumHeight(28)
        top = QHBoxLayout(self._reward_heading)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(7)
        self._reward_eyebrow = QLabel("GARDEN REWARD", self._reward_heading)
        self._reward_eyebrow.setObjectName("reviewerHudRewardEyebrow")
        self._reward_eyebrow.setProperty("hudEyebrow", True)
        _set_decoration(self._reward_eyebrow)
        top.addWidget(self._reward_eyebrow)
        top.addStretch(1)
        self._reward_rarity = QLabel("", self._reward_heading)
        self._reward_rarity.setProperty("hudRarity", True)
        _set_decoration(self._reward_rarity)
        top.addWidget(self._reward_rarity)
        self._reward_details_toggle = QToolButton(self._reward_heading)
        self._reward_details_toggle.setObjectName(
            "reviewerHudRewardDetailsToggle"
        )
        self._reward_details_toggle.setProperty(
            "semanticId", "reviewer.hud.reward-details-toggle"
        )
        self._reward_details_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reward_details_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reward_details_toggle.setMinimumHeight(28)
        self._reward_details_toggle.setText("Details ›")
        self._reward_details_toggle.setAccessibleName("Show reward details")
        self._reward_details_toggle.clicked.connect(self._open_current_reward)
        self._reward_details_toggle.hide()
        top.addWidget(self._reward_details_toggle)
        reveal.addWidget(self._reward_heading)
        hero = QHBoxLayout()
        hero.setSpacing(10)
        self._reward_art = QLabel(self._reward_reveal)
        self._reward_art.setObjectName("reviewerHudRewardArt")
        self._reward_art.setFixedSize(52, 52)
        self._reward_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(self._reward_art)
        hero.addWidget(self._reward_art)
        hero_copy = QVBoxLayout()
        self._reward_hero_copy = hero_copy
        self._reward_heading_milestone = False
        hero_copy.setSpacing(2)
        self._reward_title = _TwoLineLabel(self._reward_reveal)
        self._reward_title.setProperty("hudRewardTitle", True)
        _set_decoration(self._reward_title)
        hero_copy.addWidget(self._reward_title)
        self._reward_subtitle = _ElidedLabel("", self._reward_reveal)
        self._reward_subtitle.setObjectName("reviewerHudRewardSubtitle")
        self._reward_subtitle.setProperty("hudMuted", True)
        _set_decoration(self._reward_subtitle)
        hero_copy.addWidget(self._reward_subtitle)
        # Backward-compatible attribute for capture/runtime consumers.
        self._reward_category = self._reward_subtitle
        primary_values = QHBoxLayout()
        self._reward_primary_values = primary_values
        primary_values.setSpacing(8)
        self._reward_growth = QLabel("", self._reward_reveal)
        self._reward_growth.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._reward_growth)
        _set_decoration(self._reward_growth)
        primary_values.addWidget(self._reward_growth)
        self._reward_coin_icon = QLabel(self._reward_reveal)
        self._reward_coin_icon.setFixedSize(14, 14)
        self._reward_coin_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reward_coin_icon.setPixmap(self._icon_pixmap(
            "coin", 14, GARDEN_THEME["reviewer_hud_coin"]
        ))
        self._reward_coin_icon.hide()
        _set_decoration(self._reward_coin_icon)
        primary_values.addWidget(self._reward_coin_icon)
        self._reward_coins = QLabel("", self._reward_reveal)
        self._reward_coins.setProperty("hudCoin", True)
        apply_tabular_numerals(self._reward_coins)
        _set_decoration(self._reward_coins)
        primary_values.addWidget(self._reward_coins)
        self._reward_inventory = QLabel("", self._reward_reveal)
        self._reward_inventory.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._reward_inventory)
        _set_decoration(self._reward_inventory)
        primary_values.addWidget(self._reward_inventory)
        primary_values.addStretch(1)
        hero_copy.addLayout(primary_values)
        hero.addLayout(hero_copy, 1)
        reveal.addLayout(hero)

        self._reward_summary_row = QFrame(self._reward_reveal)
        self._reward_summary_row.setObjectName("reviewerHudRewardSummaryRow")
        summary_layout = QHBoxLayout(self._reward_summary_row)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)
        self._reward_summary_layout = summary_layout
        self._reward_summary_cells: list[Any] = []
        self._reward_summary_icons: list[Any] = []
        self._reward_summary_chips: list[_ElidedLabel] = []
        for index, object_name in enumerate((
            "reviewerHudRewardSummaryChip0",
            "reviewerHudRewardSummaryChip1",
        )):
            cell = QFrame(self._reward_summary_row)
            cell.setProperty("hudRewardMetric", True)
            cell.setMinimumHeight(22)
            cell_layout = QHBoxLayout(cell)
            # The fixed 296px safe area must fit both canonical semantic labels
            # without abbreviating them.  Keep the icon, but spend compact-chip
            # width on copy rather than decorative inset.
            cell_layout.setContentsMargins(2, 1, 2, 1)
            cell_layout.setSpacing(2)
            icon = QLabel(cell)
            icon.setFixedSize(12, 12)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _set_decoration(icon)
            cell_layout.addWidget(icon)
            chip = _ElidedLabel("", cell)
            chip.setObjectName(object_name)
            chip.setProperty("hudRewardChip", True)
            apply_tabular_numerals(chip)
            _set_decoration(chip)
            chip.hide()
            cell_layout.addWidget(chip, 1)
            cell.hide()
            summary_layout.addWidget(cell, 1)
            self._reward_summary_cells.append(cell)
            self._reward_summary_icons.append(icon)
            self._reward_summary_chips.append(chip)
        self._reward_summary_row.hide()
        reveal.addWidget(self._reward_summary_row)

        self._reward_detail_panel = QFrame(self._reward_reveal)
        self._reward_detail_panel.setObjectName("reviewerHudRewardDetails")
        self._reward_detail_panel.setProperty(
            "semanticId", "reviewer.hud.reward-details"
        )
        detail_layout = QVBoxLayout(self._reward_detail_panel)
        detail_layout.setContentsMargins(0, 4, 0, 2)
        detail_layout.setSpacing(5)
        detail_heading = QLabel("Reward details", self._reward_detail_panel)
        detail_heading.setProperty("hudEyebrow", True)
        _set_decoration(detail_heading)
        detail_layout.addWidget(detail_heading)
        self._reward_detail_rows: list[Any] = []
        self._reward_detail_artworks: list[QLabel] = []
        self._reward_detail_categories: list[_ElidedLabel] = []
        self._reward_detail_names: list[_ElidedLabel] = []
        self._reward_detail_values: list[QLabel] = []
        for _index in range(8):
            self._append_reward_detail_row()
        self._reward_detail_panel.hide()
        reveal.addWidget(self._reward_detail_panel)
        # Compatibility alias retained for older runtime probes.
        self._reward_secondary = QLabel("", self._reward_detail_panel)
        self._reward_secondary.hide()
        self._reward_reveal.hide()
        scroll_body.addWidget(self._reward_reveal)

        self._reward_history_panel = QFrame(self._reward_scroll_contents)
        self._reward_history_panel.setObjectName("reviewerHudRewardHistory")
        self._reward_history_panel.setProperty("semanticId", "reviewer.hud.reward-history")
        history_layout = QVBoxLayout(self._reward_history_panel)
        history_layout.setContentsMargins(10, 8, 10, 8)
        history_layout.setSpacing(5)
        history_heading = QLabel("Recent rewards", self._reward_history_panel)
        history_heading.setProperty("hudEyebrow", True)
        _set_decoration(history_heading)
        history_layout.addWidget(history_heading)
        self._history_rows: list[_ClickableFrame] = []
        self._history_labels: list[_ElidedLabel] = []
        for _index in range(_REWARD_HISTORY_PAGE_SIZE):
            row = _ClickableFrame(
                self._reward_history_panel,
                lambda index=_index: self._reopen_history_reward(index),
            )
            row.setProperty("hudHistoryRow", True)
            row.setProperty("semanticId", f"reviewer.hud.reward-history.{_index}")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 3, 4, 3)
            label = _ElidedLabel("", row)
            label.setProperty("hudMuted", True)
            apply_tabular_numerals(label)
            _set_decoration(label)
            row_layout.addWidget(label)
            row.hide()
            history_layout.addWidget(row)
            self._history_rows.append(row)
            self._history_labels.append(label)
        self._history_pager = QToolButton(self._reward_history_panel)
        self._history_pager.setObjectName("reviewerHudRewardHistoryMore")
        self._history_pager.setProperty(
            "semanticId", "reviewer.hud.reward-history.more"
        )
        self._history_pager.setMinimumHeight(28)
        apply_tabular_numerals(self._history_pager)
        self._history_pager.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._history_pager.clicked.connect(self._advance_reward_history_page)
        self._history_pager.hide()
        history_layout.addWidget(
            self._history_pager,
            0,
            Qt.AlignmentFlag.AlignRight,
        )
        self._reward_history_panel.hide()
        scroll_body.addWidget(self._reward_history_panel)
        self._reward_scroll.setWidget(self._reward_scroll_contents)
        self._reward_scroll.hide()
        surface.addWidget(self._reward_scroll)

        self._reward_divider = QFrame(self._reward_surface)
        self._reward_divider.setObjectName("reviewerHudRewardDivider")
        self._reward_divider.setProperty("semanticId", "reviewer.hud.reward-divider")
        self._reward_divider.setFixedHeight(1)
        self._reward_divider.hide()
        surface.addWidget(self._reward_divider)

        self._session_footer = _ClickableFrame(
            self._reward_surface,
            self._toggle_reward_history,
        )
        self._session_footer.setObjectName("reviewerHudSessionFooter")
        self._session_footer.setProperty("semanticId", "reviewer.hud.session-footer")
        self._session_footer.setProperty("historyAvailable", False)
        self._session_footer.setProperty("historyExpanded", False)
        self._session_footer.setCursor(Qt.CursorShape.ArrowCursor)
        self._session_footer.setFixedHeight(54)
        footer = QVBoxLayout(self._session_footer)
        footer.setContentsMargins(12, 7, 12, 7)
        footer.setSpacing(2)
        heading_row = QHBoxLayout()
        heading_row.setSpacing(4)
        self._session_heading = QLabel("This session", self._session_footer)
        self._session_heading.setProperty("hudMuted", True)
        _set_decoration(self._session_heading)
        heading_row.addWidget(self._session_heading)
        heading_row.addStretch(1)
        self._session_history_chevron = QLabel("", self._session_footer)
        self._session_history_chevron.setObjectName("reviewerHudSessionChevron")
        self._session_history_chevron.setProperty(
            "semanticId", "reviewer.hud.session-footer.chevron"
        )
        self._session_history_chevron.setProperty("hudMuted", True)
        self._session_history_chevron.setFixedWidth(14)
        self._session_history_chevron.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._session_history_chevron.hide()
        _set_decoration(self._session_history_chevron)
        heading_row.addWidget(self._session_history_chevron)
        footer.addLayout(heading_row)
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(_SESSION_METRIC_SPACING)
        metrics.setVerticalSpacing(2)
        self._session_metrics_layout = metrics
        self._session_growth = QLabel("", self._session_footer)
        self._session_growth.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._session_growth)
        _set_decoration(self._session_growth)
        metrics.addWidget(self._session_growth, 0, 0)
        self._session_growth_separator = QLabel("·", self._session_footer)
        self._session_growth_separator.setProperty("hudMuted", True)
        _set_decoration(self._session_growth_separator)
        metrics.addWidget(self._session_growth_separator, 0, 1)
        self._session_coins = QLabel("", self._session_footer)
        self._session_coins.setProperty("hudCoin", True)
        apply_tabular_numerals(self._session_coins)
        _set_decoration(self._session_coins)
        metrics.addWidget(self._session_coins, 0, 2)
        self._session_find_separator = QLabel("·", self._session_footer)
        self._session_find_separator.setProperty("hudMuted", True)
        _set_decoration(self._session_find_separator)
        metrics.addWidget(self._session_find_separator, 0, 3)
        self._session_finds = QLabel("", self._session_footer)
        apply_tabular_numerals(self._session_finds)
        _set_decoration(self._session_finds)
        metrics.addWidget(self._session_finds, 0, 4)
        for metric in (
            self._session_growth,
            self._session_growth_separator,
            self._session_coins,
            self._session_find_separator,
            self._session_finds,
        ):
            metric.setProperty("hudSessionMetric", True)
        metrics.setColumnStretch(5, 1)
        footer.addLayout(metrics)
        self._session_footer.hide()
        surface.addWidget(self._session_footer)
        self._reward_dock.hide()
        expanded_layout.addWidget(self._reward_dock)

    def _append_reward_detail_row(self) -> None:
        """Add one visible-detail slot without imposing a bundle-size ceiling."""

        index = len(self._reward_detail_rows)
        row = QFrame(self._reward_detail_panel)
        row.setProperty("hudRewardDetailRow", True)
        row.setProperty("semanticId", f"reviewer.hud.reward-details.{index}")
        row_layout = QGridLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setHorizontalSpacing(6)
        row_layout.setVerticalSpacing(1)
        artwork = QLabel(row)
        artwork.setFixedSize(28, 28)
        artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        artwork.setProperty("hudRewardDetailArtwork", True)
        _set_decoration(artwork)
        category = _ElidedLabel("", row)
        category.setProperty("hudMuted", True)
        _set_decoration(category)
        name = _ElidedLabel("", row)
        _set_decoration(name)
        value = QLabel("", row)
        apply_tabular_numerals(value)
        value.setWordWrap(True)
        value.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        value.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        _set_decoration(value)
        # Each field owns a full-width line.  A long milestone value must never
        # collapse the category/name column to zero; the bounded reward scroll
        # owns the resulting natural height.
        row_layout.addWidget(artwork, 0, 0, 3, 1, Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(category, 0, 1)
        row_layout.addWidget(name, 1, 1)
        row_layout.addWidget(value, 2, 1)
        row_layout.setColumnStretch(1, 1)
        row.hide()
        detail_layout = self._reward_detail_panel.layout()
        detail_layout.addWidget(row)
        self._reward_detail_rows.append(row)
        self._reward_detail_artworks.append(artwork)
        self._reward_detail_categories.append(category)
        self._reward_detail_names.append(name)
        self._reward_detail_values.append(value)

    def _ensure_reward_detail_rows(self, count: int) -> None:
        while len(self._reward_detail_rows) < max(0, int(count)):
            self._append_reward_detail_row()

    def _build_collapsed(self) -> None:
        self._collapsed_tab = _ClickableFrame(self, self._expand_from_tab)
        self._collapsed_tab.setObjectName("reviewerHudCollapsedTab")
        self._collapsed_tab.setProperty("semanticId", "reviewer.hud.collapsed-tab")
        self._collapsed_tab.setAccessibleName("Expand Anki Garden review panel")
        layout = QVBoxLayout(self._collapsed_tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        leaf = QLabel(self._collapsed_tab)
        leaf.setFixedSize(20, 20)
        leaf.setPixmap(self._icon_pixmap("growth", 19, GARDEN_THEME["reviewer_hud_growth"]))
        leaf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(leaf)
        layout.addWidget(leaf, 0, Qt.AlignmentFlag.AlignHCenter)
        self._collapsed_ring = _MiniProgressRing(self._collapsed_tab)
        self._collapsed_art = QLabel(self._collapsed_ring)
        self._collapsed_art.setFixedSize(28, 28)
        self._collapsed_art.move(4, 4)
        self._collapsed_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(self._collapsed_art)
        layout.addWidget(self._collapsed_ring, 0, Qt.AlignmentFlag.AlignHCenter)
        self._collapsed_status = QLabel("", self._collapsed_tab)
        self._collapsed_status.setProperty("hudCollapsedStatus", True)
        self._collapsed_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_status.setFixedHeight(12)
        apply_tabular_numerals(self._collapsed_status)
        _set_decoration(self._collapsed_status)
        layout.addWidget(self._collapsed_status)
        self._collapsed_next = QLabel("", self._collapsed_tab)
        self._collapsed_next.setObjectName("reviewerHudCollapsedNext")
        self._collapsed_next.setProperty(
            "semanticId", "reviewer.hud.collapsed-next"
        )
        self._collapsed_next.setProperty("hudCollapsedNext", True)
        self._collapsed_next.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_next.setWordWrap(True)
        self._collapsed_next.setFixedHeight(22)
        apply_tabular_numerals(self._collapsed_next)
        _set_decoration(self._collapsed_next)
        layout.addWidget(self._collapsed_next)
        self._collapsed_badge = QLabel("", self._collapsed_tab)
        self._collapsed_badge.setProperty("hudCoin", True)
        self._collapsed_badge.setFixedSize(20, 18)
        self._collapsed_badge.move(31, 4)
        apply_tabular_numerals(self._collapsed_badge)
        self._collapsed_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_badge.hide()
        _set_decoration(self._collapsed_badge)
        self._collapsed_badge.raise_()

    def _open_garden(self) -> None:
        _call(self._on_open_garden)

    def _open_plant(self) -> None:
        plant_id = self._projection.nurture.plant_id if self._projection else ""
        if plant_id:
            _call(self._on_open_plant, plant_id)
        else:
            _call(self._on_open_garden)

    def _open_growth_projects(self) -> None:
        """Open the canonical Collection route for project status or choice."""

        callback = self._on_open_collection
        _call(callback if callable(callback) else self._on_open_garden)

    def _select_another_plant(self) -> None:
        """Open an anchored chooser, falling back to Collection when needed."""

        choices = tuple(
            getattr(self._projection, "plant_choices", ()) or ()
        )
        if not choices or not callable(self._on_choose_plant):
            _call(self._on_select_plant)
            return
        current_menu = self._plant_selector_menu
        try:
            if current_menu is not None and current_menu.isVisible():
                current_menu.close()
                return
        except RuntimeError:
            self._plant_selector_menu = None

        try:
            menu = QMenu(self._select_plant)
            menu.setObjectName("reviewerHudPlantSelector")
            menu.setProperty("semanticId", "reviewer.hud.plant-selector")
            menu.setAccessibleName("Choose next plant")
            from aqt.qt import QProxyStyle, QStyle

            class PlantMenuStyle(QProxyStyle):
                def pixelMetric(self, metric, option=None, widget=None):
                    if metric == QStyle.PixelMetric.PM_SmallIconSize:
                        return 40
                    return super().pixelMetric(metric, option, widget)

            # QMenu has no setIconSize API. Its style owns the icon envelope.
            menu._plant_icon_style = PlantMenuStyle()
            menu.setStyle(menu._plant_icon_style)
            menu.setStyleSheet(
                "QMenu#reviewerHudPlantSelector {"
                f"background:{GARDEN_THEME['reviewer_hud_shell']};"
                "border:1px solid rgba(112,220,170,43);"
                "border-radius:10px;padding:6px;}"
                "QMenu#reviewerHudPlantSelector::item {"
                f"color:{GARDEN_THEME['text_primary']};"
                "min-height:40px;padding:5px 12px 5px 7px;"
                "border-radius:6px;}"
                "QMenu#reviewerHudPlantSelector::item:selected {"
                f"background:{GARDEN_THEME['reviewer_hud_surface_hover']};"
                f"color:{GARDEN_THEME['reviewer_hud_growth_strong']};}}"
            )
            tooltip_visibility = getattr(menu, "setToolTipsVisible", None)
            if callable(tooltip_visibility):
                tooltip_visibility(True)
            pixel_ratio = 2.0
            try:
                pixel_ratio = max(1.0, float(self.devicePixelRatioF()))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            for choice in choices:
                action = menu.addAction(str(choice.plant_name or "Plant"))
                action.setData(str(choice.plant_id or ""))
                context = " · ".join(
                    value
                    for value in (
                        str(choice.species_name or ""),
                        str(choice.stage_label or ""),
                    )
                    if value
                )
                if context:
                    action.setToolTip(context)
                if choice.art_path:
                    try:
                        pixmap = normalized_plant_pixmap(
                            choice.art_path,
                            choice.art_placement,
                            stage=choice.stage_key,
                            logical_size=40,
                            device_pixel_ratio=pixel_ratio,
                        )
                        if not pixmap.isNull():
                            action.setIcon(QIcon(pixmap))
                            action.setIconVisibleInMenu(True)
                    except Exception:
                        pass
                action.triggered.connect(
                    lambda _checked=False, plant_id=choice.plant_id:
                    self._choose_plant(plant_id)
                )
            self._plant_selector_menu = menu
            menu.aboutToHide.connect(
                lambda menu=menu: self._release_plant_selector(menu)
            )
            menu.popup(
                self._select_plant.mapToGlobal(
                    self._select_plant.rect().bottomLeft()
                )
            )
        except Exception:
            self._plant_selector_menu = None
            _call(self._on_select_plant)

    def _release_plant_selector(self, menu: Any) -> None:
        if self._plant_selector_menu is menu:
            self._plant_selector_menu = None
        try:
            menu.deleteLater()
        except RuntimeError:
            pass

    def _choose_plant(self, plant_id: str) -> None:
        """Commit one menu choice; stale choices use the Collection fallback."""

        callback = self._on_choose_plant
        if not callable(callback):
            _call(self._on_select_plant)
            return
        try:
            result = callback(str(plant_id or ""))
            accepted = (
                bool(result[0])
                if isinstance(result, tuple) and result
                else result is not False
            )
        except Exception:
            accepted = False
        if not accepted:
            QTimer.singleShot(0, lambda: _call(self._on_select_plant))

    def _open_current_reward(self) -> None:
        if self._current_reward is None:
            return
        if (
            self._reward_details_expanded
            and getattr(self, "_history_reward_inspection", None) is not None
        ):
            self._close_history_reward_inspection()
            return
        self._reward_details_expanded = not self._reward_details_expanded
        self._reward_reveal.setProperty(
            "rewardDetailsExpanded",
            self._reward_details_expanded,
        )
        ReviewGardenHud._set_reward_reveal_state(
            self,
            "details_open"
            if self._reward_details_expanded
            else "settled"
            if self._reward_minimum_hold_elapsed
            else "celebrating",
        )
        self._sync_current_reward_secondary()
        _call(self._on_open_reward, self._current_reward)
        if not self._reward_details_expanded:
            ReviewGardenHud._maybe_archive_current_reward(self)
        self.reposition()

    def _mark_reward_hold_elapsed(self) -> None:
        if self._current_reward is None:
            return
        self._reward_minimum_hold_elapsed = True
        self.setProperty("hudRewardMinimumHoldElapsed", True)
        if not bool(getattr(self, "_reward_details_expanded", False)):
            ReviewGardenHud._set_reward_reveal_state(self, "settled")
        ReviewGardenHud._maybe_archive_current_reward(self)

    def _current_reward_reveal_state(self) -> str:
        if getattr(self, "_current_reward", None) is None:
            return str(getattr(self, "_reward_reveal_state", "hidden") or "hidden")
        if bool(getattr(self, "_reward_details_expanded", False)):
            return "details_open"
        state = str(getattr(self, "_reward_reveal_state", "") or "")
        if state in {"celebrating", "settled", "archived"}:
            return state
        return (
            "settled"
            if bool(getattr(self, "_reward_minimum_hold_elapsed", False))
            else "celebrating"
        )

    def _set_reward_reveal_state(
        self,
        state: RewardRevealState,
    ) -> None:
        normalized: RewardRevealState = (
            state
            if state in {
                "hidden",
                "celebrating",
                "settled",
                "details_open",
                "archived",
            }
            else "hidden"
        )
        self._reward_reveal_state = normalized
        self.setProperty("hudRewardRevealState", normalized)
        reveal = getattr(self, "_reward_reveal", None)
        if reveal is not None:
            reveal.setProperty("rewardRevealState", normalized)

    def _maybe_archive_current_reward(self) -> bool:
        if (
            self._current_reward is None
            or not self._reward_minimum_hold_elapsed
            or not bool(getattr(self, "_reward_next_commit_seen", False))
            or bool(getattr(self, "_reward_details_expanded", False))
            or getattr(self, "_history_reward_inspection", None) is not None
        ):
            return False
        self._archive_current_reward()
        return True

    def _toggle_from_control(self, *_args: Any) -> None:
        self.set_collapsed(not self._collapsed, notify=True)

    def _expand_from_tab(self) -> None:
        self.set_collapsed(False, notify=True)
        self._unseen_major = 0
        self._sync_unseen_badge()
        if self._current_reward is None and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())

    def set_collapsed(self, collapsed: bool, *, notify: bool = False) -> None:
        changed = self._collapsed != bool(collapsed)
        self._collapsed = bool(collapsed)
        self.setProperty("hudCollapsed", self._collapsed)
        self._expanded.setVisible(not self._collapsed)
        self._collapsed_tab.setVisible(self._collapsed)
        # The expanded shell already hides all of its children.  Leaving the
        # active reward mounted preserves the one-shot reveal and its running
        # minimum hold across collapse/expand instead of requeueing and
        # presenting the event as though it had just been committed again.
        self._sync_reward_dock_visibility()
        self.reposition()
        if changed and notify:
            _call(self._on_toggle_collapsed, self._collapsed)

    def update_projection(
        self,
        projection: ReviewerHudProjection,
        *,
        animate: bool = False,
    ) -> None:
        if not isinstance(projection, ReviewerHudProjection):
            raise TypeError("projection must be a ReviewerHudProjection")
        previous = self._projection
        animate = bool(animate and self._animations_enabled)
        self._projection = projection
        self._revision += 1
        revision = self._revision
        self._dock = projection.dock
        self.setProperty("hudDock", projection.dock)
        self._collapse_button.setIcon(self._icon(
            "chevron-up",
            18,
            GARDEN_THEME["text_primary"],
        ))
        self.setProperty("hudProjectionRevision", self._revision)
        previous_nurture = previous.nurture if previous is not None else None
        self._today_completion_feedback_active = bool(
            animate
            and previous is not None
            and not previous.today.complete
            and projection.today.complete
        )
        self.setProperty(
            "hudTodayCompletionFeedbackActive",
            self._today_completion_feedback_active,
        )
        if self._settled_full_bloom_bundle is not None:
            settled_id = _full_bloom_plant_id(self._settled_full_bloom_bundle)
            projected_id = str(projection.nurture.plant_id or "")
            if projection.nurture.has_target and projected_id and projected_id != settled_id:
                self._settled_full_bloom_bundle = None
                self._plant_card.setProperty("fullBloomSettled", False)
        checkpoint_prepared = bool(
            animate
            and self._prepare_checkpoint_crossing(
                projection.nurture,
                previous_nurture,
            )
        )
        self._routine_projection_feedback_active = bool(
            animate
            and previous is not None
            and not checkpoint_prepared
            and not self._today_completion_feedback_active
        )
        self.setProperty(
            "hudRoutineProjectionFeedbackActive",
            self._routine_projection_feedback_active,
        )
        if self._routine_projection_feedback_active:
            self.setProperty("hudRoutineSessionReleasedAfterProgress", False)

        def apply_changed_values() -> None:
            if self._disposed or revision != self._revision:
                return
            self._update_today(
                projection.today,
                animate=animate,
                previous=previous.today if previous is not None else None,
            )
            self._update_coins(projection.coins, animate=animate)
            self._update_plant(
                projection.nurture,
                animate=animate,
                previous=previous_nurture,
                checkpoint_prepared=checkpoint_prepared,
            )
            self.reposition()
            if self._routine_projection_feedback_active:
                QTimer.singleShot(
                    _PROGRESS_FILL_MS,
                    lambda: self._finish_routine_projection_feedback(revision),
                )
            else:
                self._flush_deferred_checkpoint_feedback()

        self.set_collapsed(projection.collapsed)
        self.show()
        self.raise_()
        if animate:
            # The committed reward dock begins its reveal before header and
            # plant values move, preserving the answer -> result relationship.
            QTimer.singleShot(_PROJECTION_APPLY_DELAY_MS, apply_changed_values)
        else:
            apply_changed_values()

    def _finish_routine_projection_feedback(self, revision: int) -> None:
        """Release footer totals only after the committed progress fill settles."""

        if self._disposed or revision != self._revision:
            return
        self._routine_projection_feedback_active = False
        self.setProperty("hudRoutineProjectionFeedbackActive", False)
        self.setProperty("hudRoutineSessionReleasedAfterProgress", True)
        self._flush_deferred_checkpoint_feedback()

    def _update_coins(self, coins: int, *, animate: bool) -> None:
        target = max(0, int(coins or 0))
        if (
            (
                self._checkpoint_track.checkpoint_crossing_active
                or self._today_completion_feedback_active
                or self._routine_projection_feedback_active
            )
            and not self._applying_deferred_checkpoint_feedback
        ):
            self._deferred_coin_update = (target, bool(animate))
            self.setProperty("hudResultCoinUpdateDeferred", True)
            self.setProperty(
                "hudCheckpointCoinUpdateDeferred",
                self._checkpoint_track.checkpoint_crossing_active,
            )
            if self._checkpoint_track.checkpoint_crossing_active:
                self._register_checkpoint_feedback_flush()
            return
        self._deferred_coin_update = None
        committed_before = self._committed_coin_balance
        self._committed_coin_balance = target
        if committed_before is None:
            self._set_coin_balance_text(target)
            return
        if target == committed_before:
            if self._coin_animation is None:
                self._set_coin_balance_text(target)
            return
        current = max(0, int(getattr(self, "_displayed_coin_balance", target)))
        if not animate or target <= committed_before:
            if self._coin_animation is not None:
                try:
                    self._coin_animation.stop()
                except Exception:
                    pass
                self._coin_animation = None
            self._coin_feedback_revision += 1
            self._coin_delta.hide()
            self._coin_icon.setProperty("coinPulse", False)
            _repolish(self._coin_icon)
            self._set_coin_balance_text(target)
            return
        if self._coin_animation is not None:
            try:
                self._coin_animation.stop()
            except Exception:
                pass
        delta = target - committed_before
        self._coin_feedback_revision += 1
        feedback_revision = self._coin_feedback_revision
        self._coin_delta.setText(f"+{delta:,}")
        self._coin_delta.show()
        self._coin_icon.setProperty("coinPulse", True)
        _repolish(self._coin_icon)
        animation = QVariantAnimation(self)
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.setDuration(360)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: (
                self._set_coin_balance_text(int(value))
                if self._coin_animation is animation
                else None
            )
        )
        animation.finished.connect(
            lambda: (
                setattr(self, "_coin_animation", None)
                if self._coin_animation is animation
                else None
            )
        )
        self._coin_animation = animation
        animation.start()
        QTimer.singleShot(
            500,
            lambda: self._clear_coin_icon_pulse(feedback_revision),
        )
        QTimer.singleShot(
            900,
            lambda: self._clear_coin_delta(feedback_revision),
        )

    def _register_checkpoint_feedback_flush(self) -> None:
        if self._checkpoint_feedback_callback_registered:
            return
        self._checkpoint_feedback_callback_registered = True
        self._checkpoint_track.when_checkpoint_reached(
            self._flush_deferred_checkpoint_feedback
        )

    def _flush_deferred_checkpoint_feedback(self) -> None:
        self._checkpoint_feedback_callback_registered = False
        if (
            self._checkpoint_track.checkpoint_crossing_active
            or self._today_completion_feedback_active
            or self._routine_projection_feedback_active
        ):
            if self._checkpoint_track.checkpoint_crossing_active:
                self._register_checkpoint_feedback_flush()
            return
        coin_update = self._deferred_coin_update
        session_snapshot = self._deferred_session_snapshot
        self._deferred_coin_update = None
        self._deferred_session_snapshot = None
        self._applying_deferred_checkpoint_feedback = True
        try:
            if coin_update is not None:
                self._update_coins(coin_update[0], animate=coin_update[1])
            if session_snapshot is not None:
                self.update_session_totals(session_snapshot)
        finally:
            self._applying_deferred_checkpoint_feedback = False
            self.setProperty("hudCheckpointCoinUpdateDeferred", False)
            self.setProperty("hudResultCoinUpdateDeferred", False)
            self.setProperty("hudCheckpointSessionUpdateDeferred", False)
            self.setProperty("hudResultSessionUpdateDeferred", False)
            self.setProperty("hudRoutineSessionUpdateDeferred", False)

    def _set_coin_balance_text(self, coins: int) -> None:
        target = max(0, int(coins or 0))
        exact = f"{target:,}"
        try:
            exact_fits = (
                self._coin_balance.fontMetrics().horizontalAdvance(exact)
                <= self._coin_balance.maximumWidth()
            )
        except Exception:
            exact_fits = target <= 1_000_000
        rendered = _format_coin_balance(target, exact_fits=exact_fits)
        self._displayed_coin_balance = target
        self._coin_balance.setText(rendered)
        self._coin_balance.setAccessibleName(format_garden_coins(target))
        self._coin_balance.setToolTip(exact if rendered != exact else "")
        self._coin_balance.setProperty("exactCoinBalance", exact)
        self._coin_balance.setProperty(
            "compactCoinBalance",
            rendered if rendered != exact else "",
        )
        self.setProperty("hudCoinBalanceExact", exact)
        self.setProperty("hudCoinBalanceCompacted", rendered != exact)

    def _clear_coin_delta(self, revision: int | None = None) -> None:
        if revision is not None and revision != self._coin_feedback_revision:
            return
        self._coin_delta.hide()

    def _clear_coin_icon_pulse(self, revision: int | None = None) -> None:
        if revision is not None and revision != self._coin_feedback_revision:
            return
        self._coin_icon.setProperty("coinPulse", False)
        _repolish(self._coin_icon)

    def _update_today(
        self,
        today: Any,
        *,
        animate: bool = False,
        previous: Any = None,
    ) -> None:
        complete = str(today.status) == "complete"
        was_complete = bool(previous is not None and str(previous.status) == "complete")
        self._today_feedback_revision += 1
        revision = self._today_feedback_revision
        if self._today_animation is not None:
            try:
                self._today_animation.stop()
            except Exception:
                pass
            self._today_animation = None
        if self._today_copy_animation is not None:
            try:
                self._today_copy_animation.stop()
            except Exception:
                pass
            self._today_copy_animation = None
            self._today_card.setGraphicsEffect(None)
        if complete and not was_complete and animate:
            self._today_card.setProperty("completionStatus", "complete")
            self._today_card.setProperty("completionSettling", True)
            _repolish(self._today_card)
            self._today_check.hide()
            self._today_progress.show()
            previous_percent = max(
                0.0,
                min(
                    100.0,
                    float(getattr(previous, "progress_percent", 99) if previous else 99),
                ),
            )
            start = min(
                _TODAY_INCOMPLETE_VISUAL_MAX,
                round(previous_percent * 10.0),
            )
            self._today_progress.setValue(start)
            self._today_progress.setProperty(
                "displayedProgressPercent",
                round(start / 10.0, 1),
            )
            animation = QVariantAnimation(self)
            animation.setStartValue(start)
            animation.setEndValue(_TODAY_PROGRESS_SCALE)
            animation.setDuration(_PROGRESS_FILL_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)

            def set_progress(value: Any) -> None:
                if self._today_animation is not animation:
                    return
                displayed = max(0, min(_TODAY_PROGRESS_SCALE, int(value)))
                self._today_progress.setValue(displayed)
                self._today_progress.setProperty(
                    "displayedProgressPercent", round(displayed / 10.0, 1)
                )

            def finish() -> None:
                if self._today_animation is not animation:
                    return
                self._today_animation = None
                self._crossfade_today_completion_copy(today, revision)

            animation.valueChanged.connect(set_progress)
            animation.finished.connect(finish)
            self._today_animation = animation
            animation.start()
            return

        self._today_card.setProperty("completionSettling", False)
        _repolish(self._today_card)
        self._apply_today_copy(today)

    def _crossfade_today_completion_copy(self, today: Any, revision: int) -> None:
        applied = [False]

        def apply_and_release() -> None:
            if applied[0] or self._disposed or revision != self._today_feedback_revision:
                return
            applied[0] = True
            self._apply_today_copy(today)
            self._today_completion_feedback_active = False
            self.setProperty("hudTodayCompletionFeedbackActive", False)
            self._flush_deferred_checkpoint_feedback()
            QTimer.singleShot(
                1_500,
                lambda: self._settle_today_completion(revision),
            )

        if not self._animations_enabled:
            apply_and_release()
            return
        effect = QGraphicsOpacityEffect(self._today_card)
        self._today_card.setGraphicsEffect(effect)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(_ANSWER_ROW_SWAP_MS)

        def animate_value(raw: Any) -> None:
            if self._today_copy_animation is not animation:
                return
            progress = max(0.0, min(1.0, float(raw)))
            if progress >= 0.5:
                apply_and_release()
            effect.setOpacity(abs((progress * 2.0) - 1.0))

        def finish() -> None:
            if self._today_copy_animation is not animation:
                return
            apply_and_release()
            self._today_card.setGraphicsEffect(None)
            self._today_copy_animation = None

        animation.valueChanged.connect(animate_value)
        animation.finished.connect(finish)
        self._today_copy_animation = animation
        animation.start()

    def _apply_today_copy(self, today: Any) -> None:
        complete = str(today.status) == "complete"
        near_complete = bool(
            not complete
            and 0 < int(getattr(today, "remaining_count", 0) or 0) <= 5
        )
        self._today_card.setProperty("completionStatus", str(today.status))
        self._today_card.setProperty("globalScope", True)
        self._today_card.setProperty("nearComplete", near_complete)
        # The completed heading and its canonical Garden Coin reward share a
        # fixed 296 px safe area. The heading already communicates completion,
        # so keep the redundant check decoration out of that constrained row.
        self._today_check.hide()
        self._today_heading.set_full_text(today.heading)
        self._today_value.setText(today.primary)
        self._today_value.setProperty("hudCoin", complete)
        _repolish(self._today_value)
        detail = str(today.secondary[0]) if today.secondary else ""
        self._today_detail.setText(detail)
        self._today_detail.setProperty("nearComplete", near_complete)
        _repolish(self._today_detail)
        self._today_detail.setVisible(bool(detail))
        self._today_progress.setVisible(not complete and today.progress_maximum > 0)
        actual_percent = max(0.0, min(100.0, float(today.progress_percent)))
        displayed = (
            _TODAY_PROGRESS_SCALE
            if complete
            else min(
                _TODAY_INCOMPLETE_VISUAL_MAX,
                round(actual_percent * 10.0),
            )
        )
        self._today_progress.setValue(displayed)
        self._today_progress.setProperty(
            "displayedProgressPercent",
            round(displayed / 10.0, 1),
        )
        self._today_progress.setProperty(
            "minimumUnfilledLogicalPixels",
            0 if complete else 4,
        )
        self._today_progress.setProperty("actualProgressPercent", actual_percent)
        self._today_progress.setProperty("progressValue", int(today.progress_value))
        self._today_progress.setProperty("progressMaximum", int(today.progress_maximum))
        self._sync_collapsed_summary()

    def _sync_collapsed_summary(self) -> None:
        """Expose the daily state and next useful value in the compact tab."""

        projection = self._projection
        if projection is None:
            self._collapsed_status.clear()
            self._collapsed_next.clear()
            self._collapsed_tab.setToolTip("")
            self._collapsed_tab.setProperty("collapsedNextValueCopy", "")
            self._collapsed_tab.setProperty("collapsedNextVisibleCopy", "")
            return
        today = projection.today
        complete = bool(today.complete)
        if complete:
            compact_today = "Done"
            today_copy = "Today’s cards complete"
        elif int(getattr(today, "remaining_count", 0) or 0) > 0:
            remaining = int(today.remaining_count)
            compact_today = f"{remaining:,} remaining"
            today_copy = f"Today’s cards · {format_quantity(remaining, 'card')} remaining"
        else:
            compact_today = str(today.primary or "Today")
            today_copy = f"Today’s cards · {today.primary}"

        nurture = projection.nurture
        next_copy = ""
        compact_next = ""
        if str(getattr(nurture, "next_answer_value", "") or ""):
            next_value = str(nurture.next_answer_value)
            next_copy = f"Next card: {next_value}"
            compact_next = re.sub(
                r"\s+Growth$",
                "\nGrowth",
                next_value,
                flags=re.IGNORECASE,
            )
        else:
            destination = getattr(nurture, "growth_destination", None)
            if destination is not None:
                destination_kind = str(
                    getattr(destination, "kind", "") or "stored_growth"
                )
                next_copy = " · ".join(
                    value
                    for value in (
                        str(getattr(destination, "heading", "") or ""),
                        str(getattr(destination, "detail", "") or ""),
                    )
                    if value
                )
                compact_next = (
                    "Stored\nGrowth"
                    if destination_kind == "stored_growth"
                    else "Project\nprogress"
                )
            elif str(getattr(nurture, "checkpoint_line", "") or ""):
                next_copy = str(nurture.checkpoint_line)
                checkpoint_value = next_copy.split(" to ", 1)[0].strip()
                compact_next = re.sub(
                    r"\s+Growth$",
                    "\nGrowth",
                    checkpoint_value,
                    flags=re.IGNORECASE,
                )

        tooltip = "\n".join(value for value in (today_copy, next_copy) if value)
        self._collapsed_status.setText(compact_today)
        self._collapsed_next.setText(compact_next)
        self._collapsed_next.setVisible(bool(compact_next))
        self._collapsed_status.setToolTip(tooltip)
        self._collapsed_next.setToolTip(tooltip)
        self._collapsed_tab.setToolTip(tooltip)
        self._collapsed_tab.setAccessibleName(
            ". ".join(value for value in (today_copy, next_copy) if value)
        )
        self._collapsed_tab.setProperty("collapsedTodayCopy", today_copy)
        self._collapsed_tab.setProperty("collapsedNextValueCopy", next_copy)
        self._collapsed_tab.setProperty("collapsedNextVisibleCopy", compact_next)

    def _settle_today_completion(self, revision: int) -> None:
        if self._disposed or revision != self._today_feedback_revision:
            return
        self._today_card.setProperty("completionSettling", False)
        _repolish(self._today_card)

    @staticmethod
    def _crossed_checkpoint(nurture: Any, previous: Any) -> bool:
        return bool(
            previous is not None
            and previous.next_checkpoint_percent
            and (
                previous.next_checkpoint_percent != nurture.next_checkpoint_percent
                or nurture.progress_percent < previous.progress_percent
                or nurture.fully_grown
            )
        )

    @staticmethod
    def _crossed_checkpoints(nurture: Any, previous: Any) -> tuple[int, ...]:
        if previous is None or not previous.next_checkpoint_percent:
            return ()
        previous_progress = max(0, min(100, int(previous.progress_percent or 0)))
        final_progress = max(0, min(100, int(nurture.progress_percent or 0)))
        stage_boundary = bool(
            nurture.fully_grown or final_progress < previous_progress
        )
        markers = tuple(
            sorted({
                int(value)
                for value in (
                    *tuple(
                        getattr(previous, "checkpoint_percents", ()) or ()
                    ),
                    *tuple(
                        getattr(nurture, "checkpoint_percents", ()) or ()
                    ),
                )
                if 0 < int(value) <= 100
            })
        ) or (25, 50, 75, 100)
        if stage_boundary:
            previous_stage = tuple(
                marker
                for marker in markers
                if marker >= int(previous.next_checkpoint_percent)
            )
            if nurture.fully_grown or final_progress >= previous_progress:
                return previous_stage
            next_stage = tuple(
                marker
                for marker in markers
                if marker <= final_progress
            )
            return (*previous_stage, *next_stage)
        return tuple(
            marker
            for marker in markers
            if previous_progress < marker <= final_progress
        )

    def _prepare_checkpoint_crossing(self, nurture: Any, previous: Any) -> bool:
        if not self._crossed_checkpoint(nurture, previous):
            return False
        reached = self._crossed_checkpoints(nurture, previous)
        if not reached:
            reached = (int(previous.next_checkpoint_percent),)
        self._checkpoint_track.setVisible(True)
        self._checkpoint_track.animate_checkpoint_sequence(
            reached_checkpoints=reached,
            reached_reward_coins=previous.next_checkpoint_reward_coins,
            final_percent=nurture.progress_percent,
            next_checkpoint=nurture.next_checkpoint_percent,
            next_reward_coins=nurture.next_checkpoint_reward_coins,
        )
        return True

    def _update_plant(
        self,
        nurture: Any,
        *,
        animate: bool,
        previous: Any,
        checkpoint_prepared: bool = False,
    ) -> None:
        self._plant_layout.setContentsMargins(12, 11, 12, 11)
        self._plant_layout.setSpacing(6)
        self._art_region.setFixedHeight(146)
        self._art_region.setProperty("fullBloomSettled", False)
        self._plant_art.setFixedSize(136, 136)
        self._plant_card.setProperty("activePlantId", nurture.plant_id)
        self._plant_card.setProperty("environmentTone", nurture.environment_tone)
        self._plant_card.setProperty("fullyGrown", nurture.fully_grown)
        self._plant_card.setProperty(
            "allPlantsFullBloom", bool(nurture.all_plants_full_bloom)
        )
        self._plant_card.setProperty("plantClassLabel", nurture.species_name)
        self._plant_card.setProperty("titleAnchorStable", True)
        self.setProperty("hudActivePlantId", nurture.plant_id)
        self.setProperty("hudProgressPercent", nurture.progress_percent)
        self._species.set_full_text(nurture.species_name)
        self._bed.setText(nurture.bed_label)
        self._bed.hide()
        self._plant_name.set_full_text(
            nurture.plant_name if nurture.has_target else nurture.empty_heading
        )
        self._update_plant_art(nurture, animate=animate)
        normal = bool(nurture.has_target and not nurture.fully_grown)
        self._stage.set_full_text(nurture.stage_label)
        self._stage.setProperty("fullBloomAccent", bool(nurture.fully_grown))
        _repolish(self._stage)
        self._stage.setVisible(bool(nurture.stage_label))
        self._percent.setText(format_growth(nurture.stage_points, nurture.stage_goal) if nurture.next_stage_key else "Full Bloom")
        self._progress_destination.setText(f"To {format_status_label(nurture.next_stage_key)}" if nurture.next_stage_key else "")
        self._progress_destination.setVisible(normal)
        self._checkpoint_track.setProperty("showMarkers", bool(nurture.next_checkpoint_reward_coins))
        self._checkpoint_track.setToolTip(
            f"Stage milestones award Coins. Next milestone: {nurture.next_checkpoint_percent}%, {format_garden_coins(nurture.next_checkpoint_reward_coins, signed=True)}."
            if nurture.next_checkpoint_reward_coins else ""
        )
        self._percent.setVisible(normal)
        self._checkpoint_track.set_milestones(
            tuple(
                getattr(
                    nurture,
                    "checkpoint_percents",
                    (25, 50, 75, 100),
                )
                or (25, 50, 75, 100)
            )
        )
        crossed = bool(animate and self._crossed_checkpoint(nurture, previous))
        if checkpoint_prepared:
            pass
        elif crossed:
            reached = self._crossed_checkpoints(nurture, previous)
            if not reached:
                reached = (int(previous.next_checkpoint_percent),)
            self._checkpoint_track.setVisible(True)
            self._checkpoint_track.animate_checkpoint_sequence(
                reached_checkpoints=reached,
                reached_reward_coins=previous.next_checkpoint_reward_coins,
                final_percent=nurture.progress_percent,
                next_checkpoint=nurture.next_checkpoint_percent,
                next_reward_coins=nurture.next_checkpoint_reward_coins,
            )
        else:
            self._checkpoint_track.setVisible(normal)
            self._checkpoint_track.set_checkpoint(
                nurture.next_checkpoint_percent,
                nurture.next_checkpoint_reward_coins,
            )
            self._checkpoint_track.set_progress(
                nurture.progress_percent,
                animate=animate,
            )
        self._checkpoint.set_full_text(nurture.checkpoint_line)
        self._checkpoint_estimate.setText(nurture.estimate_line)
        self._checkpoint_distance_row.setVisible(
            bool(nurture.checkpoint_line or nurture.estimate_line)
        )
        self._checkpoint_reward.setText(
            format_garden_coins(
                nurture.next_checkpoint_reward_coins,
                signed=True,
            )
            if nurture.next_checkpoint_reward_coins
            else ""
        )
        self._checkpoint_reward_row.setVisible(bool(nurture.next_checkpoint_reward_coins))
        if str(self._next_answer.property("resultState") or "") != "applied":
            self._next_answer_label.setText("Next card total:")
            self._next_answer_value.setText(nurture.next_answer_value)
            self._next_answer.setVisible(bool(nurture.next_answer_value))
        message = "\n".join(
            value
            for value in (
                str(nurture.empty_message or ""),
                str(nurture.stored_growth_line or ""),
                (
                    "Choose a plant"
                    if not nurture.has_target and not nurture.all_plants_full_bloom
                    else ""
                ),
            )
            if value
        )
        self._plant_message.setText(message)
        self._plant_message.setVisible(bool(message))
        self._select_plant.hide()
        self._growth_destination.hide()
        self.setProperty("hudFullBloomNextAction", "")
        self.setProperty("hudGrowthDestinationKind", "")
        self.setProperty("hudGrowthDestinationId", "")
        self.setProperty("hudGrowthDestinationType", "")
        self.setProperty("hudGrowthDestinationArtworkId", "")
        self.setProperty("hudStoredGrowthUnits", 0)
        self._sync_effects(nurture)
        retained_bloom = self._settled_full_bloom_bundle
        if (
            retained_bloom is not None
            and nurture.has_target
            and nurture.plant_id
            and _full_bloom_plant_id(retained_bloom) != nurture.plant_id
        ):
            # Choosing the next plant must immediately restore the live
            # projection. The completed plant remains represented by the
            # active reward and session history instead of replacing it.
            self._settled_full_bloom_bundle = None
        if self._full_bloom_bundle is not None:
            self._apply_full_bloom_override(self._full_bloom_bundle)
        elif self._stage_change_bundle is not None:
            self._apply_stage_change_override(self._stage_change_bundle)
        elif self._settled_full_bloom_bundle is not None:
            self._apply_full_bloom_override(
                self._settled_full_bloom_bundle,
                settled=True,
            )
        elif nurture.fully_grown:
            self._apply_projected_full_bloom_settled(nurture)
        elif nurture.all_plants_full_bloom:
            self._sync_full_bloom_destination(nurture)
        self._sync_reward_identity_visibility()
        self._sync_collapsed_summary()

    def _sync_full_bloom_destination(self, nurture: Any | None = None) -> None:
        """Choose one explicit post-Full-Bloom action or committed status."""

        projection = self._projection
        nurture = nurture or (
            projection.nurture if projection is not None else None
        )
        choices = tuple(
            getattr(projection, "plant_choices", ()) or ()
            if projection is not None
            else ()
        )
        if choices:
            self._growth_destination.hide()
            self._growth_destination.set_callback(None)
            self._select_plant.show()
            self.setProperty("hudFullBloomNextAction", "choose_next_plant")
            self.setProperty("hudGrowthDestinationKind", "")
            self.setProperty("hudGrowthDestinationId", "")
            self.setProperty("hudGrowthDestinationType", "")
            self.setProperty("hudGrowthDestinationArtworkId", "")
            self.setProperty("hudStoredGrowthUnits", 0)
            return

        self._select_plant.hide()
        destination = getattr(nurture, "growth_destination", None)
        if destination is None:
            self._growth_destination.hide()
            self._growth_destination.set_callback(None)
            self.setProperty("hudFullBloomNextAction", "stored_growth")
            self.setProperty("hudGrowthDestinationKind", "stored_growth")
            self.setProperty("hudGrowthDestinationId", "")
            self.setProperty("hudGrowthDestinationType", "")
            self.setProperty("hudGrowthDestinationArtworkId", "")
            self.setProperty("hudStoredGrowthUnits", 0)
            return

        kind = str(getattr(destination, "kind", "") or "stored_growth")
        project_id = str(getattr(destination, "project_id", "") or "")
        target_type = str(getattr(destination, "target_type", "") or "")
        artwork_id = str(getattr(destination, "artwork_id", "") or "")
        heading = str(getattr(destination, "heading", "") or "Stored Growth")
        detail = str(getattr(destination, "detail", "") or "")
        stored_units = max(
            0,
            int(getattr(destination, "stored_growth_units", 0) or 0),
        )
        self._growth_destination_heading.set_full_text(heading)
        self._growth_destination_detail.setText(detail)
        self._growth_destination_detail.setVisible(bool(detail))
        self._growth_destination.setProperty("destinationKind", kind)
        self._growth_destination.setProperty("destinationId", project_id)
        self._growth_destination.setProperty("destinationType", target_type)
        self._growth_destination.setProperty("destinationArtworkId", artwork_id)
        self._growth_destination.setProperty("storedGrowthUnits", stored_units)
        actionable = kind in {"active_project", "choose_project"}
        self._growth_destination.set_callback(
            self._open_growth_projects if actionable else None
        )
        project_pixmap = self._effect_art_pixmap(artwork_id, 19)
        self._growth_destination_icon.setPixmap(
            project_pixmap
            if not project_pixmap.isNull() else
            self._icon_pixmap(
                "growth",
                19,
                GARDEN_THEME["reviewer_hud_growth"],
            )
        )
        self._growth_destination.setAccessibleName(
            " · ".join(
                value
                for value in (
                    heading,
                    detail,
                    "Open Collection" if actionable else "",
                )
                if value
            )
        )
        self._growth_destination.show()
        self.setProperty("hudFullBloomNextAction", "growth_destination")
        self.setProperty("hudGrowthDestinationKind", kind)
        self.setProperty("hudGrowthDestinationId", project_id)
        self.setProperty("hudGrowthDestinationType", target_type)
        self.setProperty("hudGrowthDestinationArtworkId", artwork_id)
        self.setProperty("hudStoredGrowthUnits", stored_units)

    def _update_plant_art(self, nurture: Any, *, animate: bool) -> None:
        self._collapsed_ring.set_progress(nurture.progress_percent)
        key = (
            nurture.art_path,
            repr(nurture.art_placement),
            nurture.stage_key,
        )
        if key == self._art_key:
            return
        self._art_key = key
        self._settle_plant_motion()
        try:
            previous_pixmap = QPixmap(self._plant_art.pixmap())
        except Exception:
            previous_pixmap = QPixmap()
        try:
            dpr = max(1.0, float(self.devicePixelRatioF()))
        except Exception:
            dpr = 2.0
        try:
            pixmap = normalized_plant_pixmap(
                nurture.art_path,
                nurture.art_placement,
                stage=nurture.stage_key or "seed",
                logical_size=136,
                device_pixel_ratio=dpr,
            )
        except Exception:
            pixmap = QPixmap()
        if pixmap.isNull():
            pixmap = self._icon_pixmap("plant", 72, GARDEN_THEME["reviewer_hud_growth"])
        self._plant_full_pixmap = QPixmap(pixmap)
        self._plant_art.setPixmap(pixmap)
        self._sync_art_grounding(pixmap, nurture.stage_key)
        try:
            collapsed = pixmap.scaled(
                28,
                28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            collapsed = pixmap
        self._collapsed_art.setPixmap(collapsed)
        if animate:
            self._fade_art_in(previous_pixmap)

    def _sync_art_grounding(self, pixmap: Any, stage: Any) -> None:
        visible_width, visible_bottom = _pixmap_visible_geometry(pixmap)
        if visible_width <= 0.0:
            visible_width = {
                "seed": 54.0,
                "sprout": 74.0,
                "young": 104.0,
                "mature": 148.0,
                "flowering": 154.0,
                "rare": 160.0,
            }.get(str(stage or "").casefold(), 96.0)
        if visible_bottom <= 0.0:
            visible_bottom = float(self._plant_art.height()) - 12.0
        label_offset = max(
            0.0,
            (float(self._art_region.height()) - float(self._plant_art.height())) / 2.0,
        )
        self._art_region.set_grounding(
            stage,
            visible_width,
            label_offset + visible_bottom,
        )

    def _fade_art_in(self, previous_pixmap: Any | None = None) -> None:
        if not self._animations_enabled:
            self._plant_art.setGraphicsEffect(None)
            return
        if self._art_animation is not None:
            try:
                self._art_animation.stop()
            except Exception:
                pass
        previous_label = getattr(self, "_art_transition_label", None)
        if previous_label is not None:
            try:
                previous_label.hide()
                previous_label.deleteLater()
            except Exception:
                pass
        self._art_transition_label = None

        new_effect = QGraphicsOpacityEffect(self._plant_art)
        self._plant_art.setGraphicsEffect(new_effect)
        old_effect = None
        try:
            has_previous = previous_pixmap is not None and not previous_pixmap.isNull()
        except Exception:
            has_previous = False
        if has_previous:
            previous_label = QLabel(self._art_region)
            art_width = max(1, int(self._plant_art.width()))
            art_height = max(1, int(self._plant_art.height()))
            previous_label.setFixedSize(art_width, art_height)
            previous_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            previous_label.setPixmap(previous_pixmap)
            previous_label.move(
                max(0, (self._art_region.width() - art_width) // 2),
                max(0, (self._art_region.height() - art_height) // 2),
            )
            _set_decoration(previous_label)
            old_effect = QGraphicsOpacityEffect(previous_label)
            previous_label.setGraphicsEffect(old_effect)
            previous_label.show()
            previous_label.raise_()
            self._art_transition_label = previous_label
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(350)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def set_opacity(value: Any) -> None:
            if self._art_animation is not animation:
                return
            progress = max(0.0, min(1.0, float(value)))
            new_effect.setOpacity(0.35 + (0.65 * progress))
            if old_effect is not None:
                old_effect.setOpacity(1.0 - progress)

        def finish() -> None:
            if self._art_animation is not animation:
                return
            self._plant_art.setGraphicsEffect(None)
            label = getattr(self, "_art_transition_label", None)
            if label is not None:
                label.hide()
                label.deleteLater()
            self._art_transition_label = None
            if self._art_animation is animation:
                self._art_animation = None

        animation.valueChanged.connect(set_opacity)
        animation.finished.connect(finish)
        self._art_animation = animation
        animation.start()

    def _settle_plant_motion(self) -> None:
        """Restore the fixed art canvas after a bounded feedback animation."""

        animation = self._plant_motion_animation
        self._plant_motion_animation = None
        if animation is not None:
            try:
                animation.stop()
            except Exception:
                pass
        source = self._plant_motion_source
        self._plant_motion_source = None
        try:
            if source is not None and not source.isNull():
                self._plant_art.setPixmap(source)
        except Exception:
            pass
        origin = self._plant_motion_origin
        self._plant_motion_origin = None
        if origin is not None:
            try:
                self._plant_art.move(origin[0], origin[1])
            except Exception:
                pass
        try:
            self._art_region.set_particle_progress(0.0)
        except Exception:
            pass
        self._art_region.setProperty("artLiftPx", 0)
        self._art_region.setProperty("artScale", 1.0)
        self._art_region.setProperty("fullBloomParticlesActive", False)

    def _start_plant_motion(self, *, full_bloom: bool = False) -> None:
        """Run one non-repeating pulse inside the existing 136px art canvas."""

        if not self._animations_enabled:
            self._settle_plant_motion()
            return
        self._settle_plant_motion()
        try:
            source = QPixmap(self._plant_art.pixmap())
        except Exception:
            source = QPixmap()
        if source.isNull():
            return
        self._plant_motion_source = source
        self._plant_motion_origin = (
            int(self._plant_art.x()),
            int(self._plant_art.y()),
        )
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(
            _FULL_BLOOM_PULSE_MS if full_bloom else _PLANT_PULSE_MS
        )
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def animate_value(raw: Any) -> None:
            if self._plant_motion_animation is not animation:
                return
            progress = max(0.0, min(1.0, float(raw)))
            wave = 1.0 - abs((progress * 2.0) - 1.0)
            origin = self._plant_motion_origin
            if origin is None:
                return
            lift = round((1.0 if full_bloom else 2.0) * wave)
            self._plant_art.move(origin[0], origin[1] - lift)
            self._art_region.setProperty("artLiftPx", lift)
            if full_bloom:
                scale = 1.0 + (0.045 * wave)
                scaled = source.scaled(
                    max(1, round(source.width() * scale)),
                    max(1, round(source.height() * scale)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._plant_art.setPixmap(scaled)
                self._art_region.setProperty("artScale", round(scale, 3))
                self._art_region.setProperty("fullBloomParticlesActive", True)
                self._art_region.set_particle_progress(progress)

        def finish() -> None:
            if self._plant_motion_animation is not animation:
                return
            self._settle_plant_motion()

        animation.valueChanged.connect(animate_value)
        animation.finished.connect(finish)
        self._plant_motion_animation = animation
        animation.start()

    def _effect_art_pixmap(self, reference: Any, size: int = 18) -> Any:
        """Resolve one compact active-effect item image through the shared catalog."""

        normalized = str(
            getattr(reference, "artwork_ref", "") or reference or ""
        )
        if not normalized or not callable(self._resolve_reward_art):
            return QPixmap()
        try:
            resolved = self._resolve_reward_art(reference)
        except Exception:
            resolved = None
        candidate_path = getattr(resolved, "path", resolved)
        if not candidate_path:
            return QPixmap()
        cache_key = f"effect:{candidate_path}"
        cached = self._reward_art_cache.get(cache_key)
        pixmap = QPixmap(cached) if cached is not None else QPixmap(str(candidate_path))
        if pixmap.isNull():
            return QPixmap()
        if cached is None:
            pixmap = _alpha_cropped_pixmap(pixmap, padding=0.05)
            self._reward_art_cache[cache_key] = QPixmap(pixmap)
            while len(self._reward_art_cache) > 32:
                self._reward_art_cache.pop(next(iter(self._reward_art_cache)))
        return pixmap.scaled(
            max(1, int(size)),
            max(1, int(size)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _sync_effects(self, nurture: Any) -> None:
        self._all_effects = tuple(
            _effect_display_text(value) for value in nurture.effect_chips
        )
        visible = tuple(
            _effect_display_text(value) for value in nurture.visible_effect_chips
        )
        art_refs = tuple(
            str(value or "")
            for value in getattr(nurture, "visible_effect_art_refs", ())
        )
        for index, label in enumerate(self._effect_labels):
            text = visible[index] if index < len(visible) else ""
            label.set_full_text(text)
            identity = text.split(" ", 1)[0].lower() if text else ""
            icon_name = identity if identity in {"fertilizer", "booster", "streak"} else "growth"
            artwork_ref = art_refs[index] if index < len(art_refs) else ""
            item_art = self._effect_art_pixmap(artwork_ref)
            uses_item_art = not item_art.isNull()
            self._effect_icons[index].setPixmap(
                item_art
                if uses_item_art
                else self._icon_pixmap(
                    icon_name,
                    14,
                    GARDEN_THEME["reviewer_hud_growth"],
                )
            )
            self._effect_icons[index].setProperty(
                "hudEffectArtworkRef",
                artwork_ref,
            )
            self._effect_icons[index].setProperty(
                "hudEffectUsesItemArt",
                uses_item_art,
            )
            self._effect_icons[index].setAccessibleName(
                f"{identity.title()} artwork" if uses_item_art else f"{identity.title()} icon"
            )
            self._effect_chips[index].setVisible(bool(text))
        overflow = int(nurture.effect_overflow_count)
        overflow_text = _effect_overflow_label(overflow)
        self._effects_overflow.setText(overflow_text)
        self._effects_overflow.setMinimumWidth(
            self._effects_overflow.fontMetrics().horizontalAdvance(overflow_text)
            + 12
        )
        self._effects_overflow.setProperty("overflowEffectCount", overflow)
        self._effects_overflow.setToolTip("\n".join(self._all_effects[2:]))
        self._effects_overflow.setVisible(overflow > 0)
        self._effects.setVisible(bool(visible or overflow))
        self._sync_effect_layout(visible)
        if overflow <= 0:
            self._effect_details_requested = False
            self._effect_details.hide()

    def _sync_effect_layout(self, visible: tuple[str, ...] | None = None) -> None:
        """Stack long passive effects rather than shrinking or clipping them."""

        texts = tuple(visible or ())
        layout = self._effects.layout()
        if layout is None:
            return
        available = int(self._effects.contentsRect().width())
        if available < 120:
            available = max(1, int(self.width()) - 46)
        column_width = max(1, (available - 6) // 2)
        required_widths = tuple(
            self._effect_labels[index].fontMetrics().horizontalAdvance(text)
            + 26
            for index, text in enumerate(texts[:2])
        )
        single_column = bool(
            len(texts) == 1
            or (
                len(texts) > 1
                and (
                    available < 262
                    # The layout can briefly report its unconstrained size
                    # hint before the 320px HUD width is applied. Cap the
                    # usable two-column width at the real compact-card column
                    # budget so long values stack instead of widening shell.
                    or any(
                        width > min(column_width, 136)
                        for width in required_widths
                    )
                )
            )
        )

        def fit_effect_rows() -> None:
            _repolish(self._effects)
            layout.invalidate()
            layout.activate()
            for index, label in enumerate(self._effect_labels):
                label._sync()
                target_height = max(
                    28,
                    int(label.minimumHeight()) + (
                        4 if label.property("effectWrapped") is True else 0
                    ),
                )
                self._effect_chips[index].setFixedHeight(target_height)
            layout.invalidate()
            layout.activate()
            for label in self._effect_labels:
                label._sync()

        if single_column == bool(self._effects_single_column):
            self._effects.setProperty("singleColumn", single_column)
            fit_effect_rows()
            self._effects.updateGeometry()
            return
        for chip in self._effect_chips:
            layout.removeWidget(chip)
        layout.removeWidget(self._effects_overflow)
        if single_column:
            for row, chip in enumerate(self._effect_chips):
                layout.addWidget(chip, row, 0, 1, 2)
            overflow_row = 2
        else:
            for column, chip in enumerate(self._effect_chips):
                layout.addWidget(chip, 0, column)
            overflow_row = 1
        layout.addWidget(
            self._effects_overflow,
            overflow_row,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignRight,
        )
        # Reinserting a hidden widget into a visible grid can show it again.
        for index, chip in enumerate(self._effect_chips):
            chip.setVisible(index < len(texts) and bool(texts[index]))
        self._effects_single_column = single_column
        self._effects.setProperty("singleColumn", single_column)
        layout.invalidate()
        layout.activate()
        self._effects.updateGeometry()
        self._plant_card.updateGeometry()
        fit_effect_rows()

    def _resize_normal_plant_art(self, region_height: int, art_size: int) -> None:
        """Resize normal-state art from its full-quality projection pixmap."""

        self._art_region.setFixedHeight(max(1, int(region_height)))
        self._plant_art.setFixedSize(max(1, int(art_size)), max(1, int(art_size)))
        source = getattr(self, "_plant_full_pixmap", None)
        try:
            if source is None or source.isNull():
                return
            dpr = max(1.0, float(source.devicePixelRatio()))
            physical = max(1, round(int(art_size) * dpr))
            resized = source.scaled(
                physical,
                physical,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            resized.setDevicePixelRatio(dpr)
            self._plant_art.setPixmap(resized)
            stage = (
                self._projection.nurture.stage_key
                if self._projection is not None
                else ""
            )
            self._sync_art_grounding(resized, stage)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def _apply_body_compact_level(self, level: int) -> None:
        """Collapse optional HUD detail in stages before body scrolling."""

        level = max(0, min(2, int(level)))
        nurture = self._projection.nurture if self._projection is not None else None
        full_bloom = bool(
            self._full_bloom_bundle is not None
            or self._settled_full_bloom_bundle is not None
            or self._plant_card.property("fullBloomSettled")
        )
        detail_level = level
        body_margin, body_spacing = ((6, 6), (6, 6), (4, 4))[level]
        if full_bloom:
            self._plant_layout.setContentsMargins(12, 4, 12, 4)
            self._plant_layout.setSpacing(4)
        self._body_layout.setContentsMargins(
            body_margin,
            body_margin,
            body_margin,
            body_margin,
        )
        self._body_layout.setSpacing(body_spacing)
        today_min, today_max, today_vertical_margin = (
            (58, 68, 6),
            (56, 64, 4),
            (54, 60, 4),
        )[detail_level]
        self._today_card.setMinimumHeight(today_min)
        self._today_card.setMaximumHeight(today_max)
        today_layout = self._today_card.layout()
        if today_layout is not None:
            today_layout.setContentsMargins(12, today_vertical_margin, 12, today_vertical_margin)

        if not full_bloom:
            plant_vertical_margin, plant_spacing, region_height, art_size = (
                (6, 4, 140, 136),
                (4, 4, 136, 132),
                (4, 3, 132, 128),
            )[level]
            self._plant_layout.setContentsMargins(
                12,
                plant_vertical_margin,
                12,
                plant_vertical_margin,
            )
            self._plant_layout.setSpacing(plant_spacing)
            self._resize_normal_plant_art(region_height, art_size)

            normal = bool(
                nurture is not None
                and nurture.has_target
                and not nurture.fully_grown
            )
            self._checkpoint_distance_row.setVisible(bool(
                level == 0
                and normal
                and (nurture.checkpoint_line or nurture.estimate_line)
            ))
            self._checkpoint_reward_row.setVisible(bool(
                level == 0
                and normal
                and nurture.next_checkpoint_reward_coins
            ))
            visible_effects = tuple(
                getattr(nurture, "visible_effect_chips", ()) or ()
            ) if nurture is not None else ()
            overflow = int(
                getattr(nurture, "effect_overflow_count", 0) or 0
            ) if nurture is not None else 0
            show_effects = bool(level == 0 and (visible_effects or overflow))
            self._effects.setVisible(show_effects)
            self._effect_details.setVisible(bool(
                show_effects
                and overflow > 0
                and self._effect_details_requested
            ))
            if show_effects:
                self._sync_effect_layout(visible_effects)

        self._body_compact_level = level
        self.setProperty("hudBodyCompactLevel", level)
        self.setProperty("hudOptionalEffectsCollapsed", bool(level >= 1))
        self.setProperty(
            "hudOptionalArtworkCompact",
            bool(level >= 1 and not full_bloom),
        )
        self.setProperty(
            "hudOptionalCheckpointCopyCollapsed",
            bool(level >= 2 and not full_bloom),
        )
        self._body_layout.invalidate()
        self._plant_layout.invalidate()
        self._body_contents.updateGeometry()
        self._plant_card.updateGeometry()

    def _toggle_effect_details(self) -> None:
        details = tuple(getattr(self, "_all_effects", ()) or ())[2:]
        if not details:
            return
        expanded = not self._effect_details.isVisible()
        self._effect_details_requested = expanded
        self._effect_details.setText(" · ".join(details))
        self._effect_details.setVisible(expanded)
        _call(self._on_effects_overflow, expanded)
        self.reposition()

    def animate_growth_delta(self, growth_units: int) -> None:
        """Compatibility name for the in-row committed Growth feedback."""

        units = max(0, int(growth_units or 0))
        if not units:
            return
        self._growth_feedback_revision += 1
        revision = self._growth_feedback_revision
        self._swap_next_answer_row(
            "This card:",
            f"{format_growth_units(units, signed=True)} Growth",
            state="applied",
        )
        self._next_answer.show()
        if self._animations_enabled:
            self._art_region.setProperty("artPulse", True)
            _repolish(self._art_region)
            self._start_plant_motion()
            QTimer.singleShot(
                _PLANT_PULSE_MS,
                lambda: self._clear_art_pulse(revision),
            )
        QTimer.singleShot(
            _NEXT_PROJECTION_RESTORE_MS,
            lambda: self._clear_growth_delta(revision),
        )
        self.reposition()

    def _swap_next_answer_row(
        self,
        label: str,
        value: str,
        *,
        state: str,
    ) -> None:
        def apply_copy() -> None:
            self._next_answer_label.setText(label)
            self._next_answer_value.setText(value)
            self._next_answer.setProperty("resultState", state)
            self._next_answer.setProperty("appliedResultVisible", state == "applied")
            _repolish(self._next_answer)

        if not self._animations_enabled:
            apply_copy()
            return
        if self._answer_row_animation is not None:
            try:
                self._answer_row_animation.stop()
            except Exception:
                pass
        self._next_answer.setGraphicsEffect(None)
        effect = QGraphicsOpacityEffect(self._next_answer)
        self._next_answer.setGraphicsEffect(effect)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(_ANSWER_ROW_SWAP_MS)
        switched = [False]

        def animate_value(raw: Any) -> None:
            if self._answer_row_animation is not animation:
                return
            progress = max(0.0, min(1.0, float(raw)))
            if progress >= 0.5 and not switched[0]:
                switched[0] = True
                apply_copy()
            effect.setOpacity(abs((progress * 2.0) - 1.0))

        def finish() -> None:
            if self._answer_row_animation is not animation:
                return
            if not switched[0]:
                apply_copy()
            self._next_answer.setGraphicsEffect(None)
            self._answer_row_animation = None

        animation.valueChanged.connect(animate_value)
        animation.finished.connect(finish)
        self._answer_row_animation = animation
        animation.start()

    def _clear_art_pulse(self, revision: int) -> None:
        if self._disposed or revision != self._growth_feedback_revision:
            return
        self._art_region.setProperty(
            "artPulse",
            bool(self._full_bloom_bundle and self._animations_enabled),
        )
        _repolish(self._art_region)

    def _clear_growth_delta(self, revision: int | None = None) -> None:
        if self._disposed or (
            revision is not None and revision != self._growth_feedback_revision
        ):
            return
        nurture = self._projection.nurture if self._projection is not None else None
        next_value = str(getattr(nurture, "next_answer_value", "") or "")
        self._swap_next_answer_row(
            "Next card total:",
            next_value,
            state="projection",
        )
        keep_hidden = bool(
            self._full_bloom_bundle
            or self._settled_full_bloom_bundle
            or nurture is None
            or not next_value
        )
        self._next_answer.setVisible(not keep_hidden)
        self._clear_art_pulse(self._growth_feedback_revision)
        self.reposition()

    def celebrate_milestone(self, kind: str, bundle: Any | None = None) -> None:
        normalized = str(kind or "").replace("_", "-").lower()
        celebration = "full-bloom" if normalized == "full-bloom" else "stage-change"
        self._celebration_revision += 1
        revision = self._celebration_revision
        if celebration == "full-bloom" and bundle is not None:
            self._settle_plant_motion()
            self._settled_full_bloom_bundle = None
            self._full_bloom_bundle = bundle
            self._plant_card.setProperty("fullBloomSettled", False)
            self._art_region.setProperty("fullBloomLightRays", True)
            self._apply_full_bloom_override(bundle)
        elif celebration == "stage-change" and bundle is not None:
            self._stage_change_bundle = bundle
            self._apply_stage_change_override(bundle)
        self._plant_card.setProperty("celebration", celebration)
        if celebration == "full-bloom" and self._animations_enabled:
            self._art_region.setProperty("artPulse", True)
            self._start_plant_motion(full_bloom=True)
        _repolish(self._art_region)
        _repolish(self._plant_card)
        QTimer.singleShot(
            2_200 if celebration == "full-bloom" else 1_600,
            lambda: self._clear_celebration(revision),
        )

    def _apply_full_bloom_override(
        self,
        bundle: Any,
        *,
        settled: bool = False,
    ) -> None:
        """Keep the just-completed plant visible after active-target rotation."""

        plant_class = _full_bloom_plant_class(bundle)
        if not plant_class and self._projection is not None:
            plant_class = str(self._projection.nurture.species_name or "")
        self._plant_name.set_full_text(_full_bloom_plant_name(bundle))
        self._species.set_full_text(plant_class)
        self._plant_card.setProperty("plantClassLabel", plant_class)
        self._plant_card.setProperty("fullBloomSettled", bool(settled))
        self._art_region.setProperty("fullBloomSettled", bool(settled))
        self._plant_layout.setContentsMargins(
            12,
            6 if settled else 8,
            12,
            6 if settled else 8,
        )
        self._plant_layout.setSpacing(4)
        self._stage.set_full_text("Full Bloom")
        self._stage.setProperty("fullBloomAccent", True)
        _repolish(self._stage)
        self._stage.show()
        self._percent.hide()
        self._progress_destination.hide()
        self._checkpoint_track.hide()
        self._checkpoint_distance_row.hide()
        self._checkpoint_reward_row.hide()
        self._next_answer.hide()
        self._effects.hide()
        self._effect_details.hide()
        projected = self._projection.nurture if self._projection is not None else None
        destination = getattr(projected, "growth_destination", None)
        route = str(getattr(destination, "route_copy", "") or "") or FULL_BLOOM_GROWTH_ROUTE_COPY
        self._plant_message.setText(
            "New Growth supports your project."
            if str(getattr(destination, "kind", "")) == "active_project" else
            "New Growth becomes Stored Growth."
            if bool(getattr(projected, "all_plants_full_bloom", False)) else
            "New Growth is shared or stored."
        )
        self._plant_card.setToolTip(route)
        self._plant_message.setAccessibleDescription(route)
        self._plant_message.show()
        self._sync_full_bloom_destination(projected)
        self._collapsed_ring.set_progress(100)
        art_region_size = 140
        # The settled card is shorter because the surrounding copy tightens,
        # not because the Full Bloom plant becomes secondary again.
        art_size = 136
        self._art_region.setFixedHeight(art_region_size)
        self._plant_art.setFixedSize(art_size, art_size)
        pixmap = self._reward_full_pixmap
        try:
            if pixmap is not None and not pixmap.isNull():
                full_bloom_pixmap = pixmap.scaled(
                    art_size,
                    art_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._plant_art.setPixmap(full_bloom_pixmap)
                self._sync_art_grounding(full_bloom_pixmap, "rare")
        except Exception:
            pass

    def _apply_projected_full_bloom_settled(self, nurture: Any) -> None:
        """Render a durable Full Bloom card without relying on reward state."""

        self._plant_layout.setContentsMargins(12, 6, 12, 6)
        self._plant_layout.setSpacing(4)
        self._plant_card.setProperty("fullBloomSettled", True)
        self._art_region.setProperty("fullBloomSettled", True)
        self._stage.set_full_text("Full Bloom")
        self._stage.setProperty("fullBloomAccent", True)
        _repolish(self._stage)
        self._stage.show()
        self._percent.hide()
        self._progress_destination.hide()
        self._checkpoint_track.hide()
        self._checkpoint_distance_row.hide()
        self._checkpoint_reward_row.hide()
        self._next_answer.hide()
        self._effects.hide()
        self._effect_details.hide()
        destination = getattr(nurture, "growth_destination", None)
        route = str(getattr(destination, "route_copy", "") or "") or FULL_BLOOM_GROWTH_ROUTE_COPY
        self._plant_message.setText(
            "New Growth supports your project."
            if str(getattr(destination, "kind", "")) == "active_project" else
            "New Growth becomes Stored Growth."
            if bool(getattr(nurture, "all_plants_full_bloom", False)) else
            "New Growth is shared or stored."
        )
        self._plant_card.setToolTip(route)
        self._plant_message.setAccessibleDescription(route)
        self._plant_message.show()
        self._sync_full_bloom_destination(nurture)
        self._collapsed_ring.set_progress(100)
        self._art_region.setFixedHeight(140)
        self._plant_art.setFixedSize(136, 136)
        try:
            pixmap = QPixmap(self._plant_art.pixmap())
            if not pixmap.isNull():
                settled_pixmap = pixmap.scaled(
                    132,
                    132,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._plant_art.setPixmap(settled_pixmap)
                self._sync_art_grounding(
                    settled_pixmap,
                    str(getattr(nurture, "stage_key", "") or "rare"),
                )
        except Exception:
            pass

    def _apply_stage_change_override(self, bundle: Any) -> None:
        hero = _bundle_hero(bundle)
        detail = str(_value(hero, "detail", default="") or "").strip()
        if detail.casefold().startswith("reached "):
            detail = detail[8:]
        self._stage.set_full_text(
            "Stage reached" + (f" · {detail}" if detail else "")
        )
        self._stage.show()

    def _clear_celebration(self, revision: int | None = None) -> None:
        if self._disposed:
            return
        if revision is not None and revision != self._celebration_revision:
            return
        full_bloom_bundle = self._full_bloom_bundle
        had_full_bloom = full_bloom_bundle is not None
        had_stage_change = self._stage_change_bundle is not None
        self._full_bloom_bundle = None
        self._stage_change_bundle = None
        self._plant_card.setProperty("celebration", "")
        self._art_region.setProperty("fullBloomLightRays", False)
        self._settle_plant_motion()
        self._art_region.setFixedHeight(146)
        self._plant_art.setFixedSize(136, 136)
        self._art_region.setProperty("artPulse", False)
        self._art_region.setProperty("fullBloomSettled", False)
        _repolish(self._art_region)
        _repolish(self._plant_card)
        if had_full_bloom and full_bloom_bundle is not None:
            projected = self._projection.nurture if self._projection is not None else None
            bloom_id = _full_bloom_plant_id(full_bloom_bundle)
            projected_id = str(getattr(projected, "plant_id", "") or "")
            selected_another = bool(
                projected is not None
                and projected.has_target
                and projected_id
                and projected_id != bloom_id
            )
            if not selected_another:
                self._settled_full_bloom_bundle = full_bloom_bundle
                self._apply_full_bloom_override(full_bloom_bundle, settled=True)
                self.reposition()
                return
        self._settled_full_bloom_bundle = None
        self._plant_card.setProperty("fullBloomSettled", False)
        if (had_full_bloom or had_stage_change) and self._projection is not None:
            self._art_key = None
            self._update_plant(
                self._projection.nurture,
                animate=False,
                previous=None,
            )

    def update_session_totals(self, snapshot: Any) -> None:
        """Consume the canonical live Session Summary snapshot directly."""

        if (
            (
                self._checkpoint_track.checkpoint_crossing_active
                or self._today_completion_feedback_active
                or self._routine_projection_feedback_active
            )
            and not self._applying_deferred_checkpoint_feedback
        ):
            self._deferred_session_snapshot = snapshot
            self.setProperty(
                "hudCheckpointSessionUpdateDeferred",
                self._checkpoint_track.checkpoint_crossing_active,
            )
            self.setProperty("hudResultSessionUpdateDeferred", True)
            self.setProperty(
                "hudRoutineSessionUpdateDeferred",
                self._routine_projection_feedback_active,
            )
            if self._checkpoint_track.checkpoint_crossing_active:
                self._register_checkpoint_feedback_flush()
            return
        self._deferred_session_snapshot = None

        growth_units = _integer(_value(snapshot, "footer_growth_units", default=0))
        if not growth_units:
            growth_units = sum(
                _integer(_value(snapshot, name, default=0))
                for name in (
                    "plant_growth_total_units",
                    "shared_growth_total_units",
                )
            )
            stored = _value(snapshot, "stored_growth", default=None)
            growth_units += _integer(_value(stored, "added_units", default=0))
        coins = _session_coin_count(snapshot)
        finds = _session_find_count(snapshot)
        previous = self._session_totals
        current = (growth_units, coins, finds)
        self._session_totals = current
        self._session_growth.setVisible(growth_units > 0)
        self._session_coins.setVisible(coins > 0)
        self._session_finds.setVisible(finds > 0)
        self._session_growth_separator.setVisible(growth_units > 0 and coins > 0)
        self._session_find_separator.setVisible(
            finds > 0 and (growth_units > 0 or coins > 0)
        )
        self._session_has_results = any(current)
        self._session_footer.setVisible(self._session_has_results)
        self._session_footer.setProperty("sessionGrowthUnits", growth_units)
        self._session_footer.setProperty("sessionCoins", coins)
        self._session_footer.setProperty("sessionFinds", finds)
        self.setProperty("hudSessionVisible", self._session_has_results)
        changed_metrics = _session_metric_increases(previous, current)
        if self._animations_enabled and any(changed_metrics):
            self._highlight_session_changes(
                self._displayed_session_totals,
                current,
                changed_metrics=changed_metrics,
            )
        else:
            self._session_feedback_revision += 1
            self._stop_session_count_animation()
            self._set_session_metric_values(current)
            self._clear_session_highlight(self._session_feedback_revision)
        self._sync_reward_dock_visibility()
        self.reposition()

    def _session_metric_widgets(self) -> tuple[Any, Any, Any]:
        return (
            self._session_growth,
            self._session_coins,
            self._session_finds,
        )

    def _sync_session_metric_wrap(self) -> None:
        """Wrap only between complete footer metrics when values grow long."""

        layout = getattr(self, "_session_metrics_layout", None)
        if layout is None:
            return
        expanded = bool(self._session_footer.property("historyExpanded"))
        for index, widget in enumerate(self._session_metric_widgets()):
            widget.setVisible(expanded and bool(self._session_totals[index]))
        self._session_heading.setText("This session · totals" if expanded else "This session")
        self._session_history_chevron.setVisible(self._session_has_results)
        self._set_session_history_chevron(expanded)
        if not expanded:
            self._session_growth_separator.hide()
            self._session_find_separator.hide()
            self._session_footer.setFixedHeight(32)
            self._session_footer.setToolTip(" · ".join(_session_metric_labels(*self._session_totals)))
            return
        was_wrapped = bool(self._session_footer.property("metricsWrapped"))
        separators = (
            self._session_growth_separator,
            self._session_find_separator,
        )
        metric_groups: list[tuple[Any, Any | None]] = []
        for widget, preferred_separator in (
            (self._session_growth, None),
            (self._session_coins, self._session_growth_separator),
            (self._session_finds, self._session_find_separator),
        ):
            if not widget.isVisible():
                continue
            metric_groups.append((
                widget,
                preferred_separator if metric_groups else None,
            ))
        for widget in (*self._session_metric_widgets(), *separators):
            layout.removeWidget(widget)
            if widget in separators:
                widget.hide()
        for column in range(7):
            layout.setColumnStretch(column, 0)

        available = int(self._session_footer.contentsRect().width()) - 24
        if available < 100:
            available = max(100, int(self.width()) - 46)
        row = 0
        column = 0
        occupied = 0
        separator_width = max(
            separator.sizeHint().width() for separator in separators
        )
        metric_spacing = max(0, int(layout.horizontalSpacing()))
        for widget, preferred_separator in metric_groups:
            metric_width = max(
                widget.sizeHint().width(),
                widget.fontMetrics().horizontalAdvance(widget.text()),
            )
            candidate_width = session_footer_metric_row_width(
                (occupied, metric_width) if occupied else (metric_width,),
                separator_width=separator_width,
                spacing=metric_spacing,
            )
            if occupied and candidate_width > available:
                row += 1
                column = 0
                occupied = 0
                candidate_width = metric_width
            if occupied:
                separator = preferred_separator or self._session_growth_separator
                separator.show()
                layout.addWidget(separator, row, column)
                column += 1
            layout.addWidget(widget, row, column)
            column += 1
            occupied = candidate_width
        layout.setColumnStretch(column, 1)
        wrapped = row > 0
        self._session_footer.setFixedHeight(68 if wrapped else 54)
        self._session_footer.setProperty("metricsWrapped", wrapped)
        self._session_footer.setProperty(
            "metricRowCount", row + 1 if metric_groups else 0
        )
        _repolish(self._session_footer)
        if wrapped != was_wrapped:
            self._schedule_layout_reposition()

    def _set_session_metric_values(
        self,
        values: tuple[int, int, int],
    ) -> None:
        normalized = tuple(_integer(value) for value in values)
        for index, widget in enumerate(self._session_metric_widgets()):
            widget.setText(_session_metric_text(index, normalized[index]))
        self._sync_session_metric_wrap()
        self._displayed_session_totals = normalized

    def _stop_session_count_animation(self) -> None:
        animation = self._session_count_animation
        self._session_count_animation = None
        if animation is not None:
            try:
                animation.stop()
            except Exception:
                pass

    def _highlight_session_changes(
        self,
        displayed_previous: tuple[int, int, int],
        current: tuple[int, int, int],
        *,
        changed_metrics: tuple[bool, bool, bool],
    ) -> None:
        self._session_feedback_revision += 1
        revision = self._session_feedback_revision
        self._stop_session_count_animation()
        for index, widget in enumerate(self._session_metric_widgets()):
            changed = changed_metrics[index]
            widget.setProperty("metricChanged", changed)
            final_text = _session_metric_text(index, current[index])
            try:
                widget.setMinimumWidth(max(
                    int(widget.minimumWidth()),
                    int(widget.fontMetrics().horizontalAdvance(final_text)),
                ))
            except Exception:
                pass
            _repolish(widget)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(_SESSION_HIGHLIGHT_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def animate_value(raw: Any) -> None:
            if self._session_count_animation is not animation:
                return
            progress = max(0.0, min(1.0, float(raw)))
            displayed = tuple(
                displayed_previous[index]
                + round(
                    (current[index] - displayed_previous[index]) * progress
                )
                if changed_metrics[index]
                else current[index]
                for index in range(3)
            )
            self._set_session_metric_values(displayed)

        def finish() -> None:
            if self._session_count_animation is not animation:
                return
            self._session_count_animation = None
            self._set_session_metric_values(current)
            self._clear_session_highlight(revision)

        animation.valueChanged.connect(animate_value)
        animation.finished.connect(finish)
        self._session_count_animation = animation
        animation.start()

    def _clear_session_highlight(self, revision: int) -> None:
        if self._disposed or revision != self._session_feedback_revision:
            return
        for widget in self._session_metric_widgets():
            widget.setProperty("metricChanged", False)
            _repolish(widget)

    def _sync_reward_dock_visibility(self) -> None:
        reveal_visible = bool(
            self._current_reward is not None and not self._reward_reveal.isHidden()
        )
        history_visible = bool(not self._reward_history_panel.isHidden())
        scroll_visible = reveal_visible or history_visible
        footer_visible = bool(self._session_has_results)
        self._sync_session_metric_wrap()
        divider_visible = scroll_visible and footer_visible
        dock_visible = scroll_visible or footer_visible
        self._reward_scroll.setVisible(scroll_visible)
        self._session_footer.setVisible(footer_visible)
        self._reward_divider.setVisible(divider_visible)
        actually_visible = dock_visible and not self._collapsed
        self._reward_dock.setVisible(actually_visible)
        self._reward_dock.setProperty("hasReveal", reveal_visible)
        self._reward_dock.setProperty("hasSession", footer_visible)
        self._reward_dock.setProperty(
            "integratedDividerVisible", divider_visible
        )
        self.setProperty("hudRewardDockVisible", actually_visible)
        self.setProperty("hudRewardDividerVisible", divider_visible)
        if scroll_visible:
            self._sync_reward_scroll_height()
        self._schedule_layout_reposition()

    def _schedule_layout_reposition(self) -> None:
        """Resize once Qt has applied pending dock and footer layout changes."""

        if self._layout_reposition_pending or self._disposed:
            return
        self._layout_reposition_pending = True

        def reposition_after_layout() -> None:
            self._layout_reposition_pending = False
            if not self._disposed:
                self.reposition()

        QTimer.singleShot(0, reposition_after_layout)

    def _sync_reward_scroll_height(self) -> None:
        natural = 0
        reveal_visible = not self._reward_reveal.isHidden()
        if reveal_visible:
            natural += max(
                self._reward_reveal.minimumHeight(),
                self._reward_reveal.sizeHint().height(),
            )
        history_visible = not self._reward_history_panel.isHidden()
        if history_visible:
            natural += max(1, self._reward_history_panel.sizeHint().height())
        if (
            reveal_visible
            and not history_visible
            and not self._reward_details_expanded
        ):
            # The compact reveal is intentionally a 130-150px surface.  Give
            # its viewport the full compact envelope so Qt's post-layout
            # contents adjustment cannot create a tiny, meaningless scrollbar
            # for the Details control or semantic summary chips.
            natural = max(natural, self._reward_reveal.minimumSizeHint().height())
        target = max(1, min(_REWARD_SCROLL_MAX_HEIGHT, natural))
        # The dock's size hint must include the compact disclosure control so
        # the sticky footer cannot cover it. The viewport keeps a one-pixel
        # minimum, allowing expanded details and history to shrink and scroll
        # on short windows while the main review body yields first.
        self._reward_scroll.setMinimumHeight(1)
        self._reward_scroll.setMaximumHeight(target)
        self._reward_scroll.set_preferred_height(target)
        self._reward_scroll.setProperty("naturalContentHeight", natural)

    def update_session(self, snapshot: Any) -> None:
        self.update_session_totals(snapshot)

    def notify_committed_card(self, event_id: str) -> bool:
        """Advance reveal lifecycle for a committed card with no reward bundle."""

        identity = str(event_id or "").strip()
        if not identity:
            return False
        seen_commit_ids = getattr(self, "_seen_commit_ids", None)
        if seen_commit_ids is None:
            seen_commit_ids = set()
            self._seen_commit_ids = seen_commit_ids
        if identity in seen_commit_ids:
            return True
        if getattr(self, "_history_reward_inspection", None) is not None:
            self._close_history_reward_inspection()
        seen_commit_ids.add(identity)
        if self._current_reward is not None:
            self._reward_next_commit_seen = True
            self.setProperty("hudRewardNextCommitSeen", True)
            ReviewGardenHud._maybe_archive_current_reward(self)
        return True

    def present_committed_result(
        self,
        bundle: Any,
        *,
        applied_growth_units: int = 0,
        reveal: bool = True,
    ) -> bool:
        """Accept one exact committed answer and coordinate its HUD feedback."""

        identity = _bundle_id(bundle)
        if not identity:
            return False
        if identity in self._seen_bundle_ids:
            return True
        if getattr(self, "_history_reward_inspection", None) is not None:
            # A history row is inspection-only. Restore the live event before
            # applying new-commit archive and queue rules.
            self._close_history_reward_inspection()
        if self._current_reward is not None:
            # A stable duplicate returned above and cannot satisfy this gate.
            # The live reveal archives only after both this distinct commit
            # and its reader-safe minimum hold have occurred.
            self._reward_next_commit_seen = True
            self.setProperty("hudRewardNextCommitSeen", True)
            ReviewGardenHud._maybe_archive_current_reward(self)
        seen_commit_ids = getattr(self, "_seen_commit_ids", None)
        if seen_commit_ids is None:
            seen_commit_ids = set()
            self._seen_commit_ids = seen_commit_ids
        seen_commit_ids.add(identity)
        self._seen_bundle_ids.add(identity)
        major = not _bundle_routine_only(bundle)
        # History reconciles to every accepted bundle, including routine
        # Growth, while only major bundles enter the reveal queue.
        self._reward_history.append(bundle)
        self._reward_history_page = 0
        self.setProperty("hudRewardHistoryCount", len(self._reward_history))
        self._sync_history_rows()
        growth_units = max(0, int(applied_growth_units or 0))
        if growth_units:
            self.animate_growth_delta(growth_units)
        if major and (self._collapsed or not reveal):
            self._unseen_major += 1
            self._sync_unseen_badge()
        if not reveal or not major:
            return True
        if self._collapsed:
            self._reward_queue.append(bundle)
            return True
        if (
            _bundle_has_kind(bundle, "checkpoint")
            and self._checkpoint_track.checkpoint_crossing_active
        ):
            self._checkpoint_pending_bundles.append(bundle)

            def release_checkpoint_bundle() -> None:
                identity = _bundle_id(bundle)
                self._checkpoint_pending_bundles = [
                    candidate
                    for candidate in self._checkpoint_pending_bundles
                    if _bundle_id(candidate) != identity
                ]
                self._enqueue_reward_reveal(bundle)

            self._checkpoint_track.when_checkpoint_reached(
                release_checkpoint_bundle
            )
            return True
        self._enqueue_reward_reveal(bundle)
        return True

    def present_reward(self, bundle: Any, *, reveal: bool = True) -> bool:
        """Backward-compatible delegate for callers without exact applied units."""

        return ReviewGardenHud.present_committed_result(
            self,
            bundle,
            applied_growth_units=_bundle_growth_units(bundle),
            reveal=reveal,
        )

    def _enqueue_reward_reveal(self, bundle: Any) -> None:
        """Keep one major reveal visible while preserving every queued major."""

        if self._collapsed:
            self._reward_queue.append(bundle)
            return
        if self._current_reward is not None:
            # Never evict an event before its reader-controlled lifecycle has
            # completed. One committed answer already arrives as one grouped
            # bundle, so later major events can wait in exact commit order.
            self._reward_queue.append(bundle)
            return
        self._show_reward(bundle)

    def _show_reward(
        self,
        bundle: Any,
        *,
        expanded: bool = False,
        presentation: str = "new",
        minimum_hold_elapsed: bool | None = None,
        next_commit_seen: bool = False,
        reveal_state: str = "",
        hold_remaining_ms: int | None = None,
    ) -> None:
        mode = str(presentation or "new").strip().casefold()
        if mode not in {"new", "restored", "history"}:
            mode = "new"
        self._reward_timer.stop()
        self._current_reward = bundle
        self._reward_details_expanded = bool(expanded)
        self._reward_minimum_hold_elapsed = (
            bool(expanded)
            if minimum_hold_elapsed is None
            else bool(minimum_hold_elapsed)
        )
        self._reward_next_commit_seen = bool(next_commit_seen)
        self._reward_presentation_mode = mode
        self.setProperty(
            "hudRewardMinimumHoldElapsed", self._reward_minimum_hold_elapsed
        )
        self.setProperty("hudRewardNextCommitSeen", self._reward_next_commit_seen)
        self._reward_reveal.setProperty("rewardDetailsExpanded", bool(expanded))
        restored_state = str(reveal_state or "").strip().casefold()
        if expanded:
            initial_state: RewardRevealState = "details_open"
        elif restored_state in {"celebrating", "settled"}:
            initial_state = restored_state  # type: ignore[assignment]
        elif self._reward_minimum_hold_elapsed:
            initial_state = "settled"
        else:
            initial_state = "celebrating"
        ReviewGardenHud._set_reward_reveal_state(
            self,
            initial_state,
        )
        self._reward_eyebrow.setText(_reward_eyebrow(bundle))
        compact_milestone = _hero_kind(bundle).replace("-", "_") in {"full_bloom", "stage_change"}
        if compact_milestone != self._reward_heading_milestone:
            heading = self._reward_heading.layout()
            heading.removeWidget(self._reward_title if self._reward_heading_milestone else self._reward_eyebrow)
            self._reward_hero_copy.removeWidget(self._reward_eyebrow if self._reward_heading_milestone else self._reward_title)
            heading.insertWidget(0, self._reward_title if compact_milestone else self._reward_eyebrow, 1 if compact_milestone else 0)
            self._reward_hero_copy.insertWidget(0, self._reward_eyebrow if compact_milestone else self._reward_title)
            heading.setStretch(1, 0 if compact_milestone else 1)
            self._reward_heading_milestone = compact_milestone
        self._reward_eyebrow.setVisible(not compact_milestone)
        self._reward_title.setProperty("singleLine", compact_milestone and mode != "history")
        self._reward_title.set_full_text("Recent rewards" if compact_milestone and mode != "history" else _reward_hero_title(bundle))
        self._sync_reward_identity_visibility()
        rarity = _hero_rarity(bundle)
        self._reward_rarity.setText(rarity.title())
        self._reward_rarity.setProperty("rarityTone", rarity.lower())
        _repolish(self._reward_rarity)
        self._reward_rarity.setVisible(bool(rarity))
        self._reward_reveal.setProperty("rewardRarity", rarity.lower())
        self._reward_reveal.setProperty("rewardBundleId", _bundle_id(bundle))
        normalized_kind = _hero_kind(bundle).replace("-", "_")
        active_milestone = normalized_kind in {"full_bloom", "stage_change"}
        self._reward_reveal.setProperty("activeMilestone", active_milestone)
        self._reward_accent.hide()
        _repolish(self._reward_reveal)
        growth_units, coins = _hero_amounts(bundle)
        self._reward_growth.setText(
            f"{format_growth_units(growth_units, signed=True)} Growth"
            if growth_units
            else ""
        )
        self._reward_growth.setVisible(bool(growth_units))
        self._reward_coins.setText(
            format_garden_coins(coins, signed=True) if coins else ""
        )
        self._reward_coins.setVisible(bool(coins))
        self._reward_coin_icon.setVisible(bool(coins))
        compact_values = compact_milestone and mode != "history"
        values_layout = self._reward_heading.layout() if compact_values else self._reward_primary_values
        values_layout.insertWidget(1 if compact_values else 1, self._reward_coin_icon)
        values_layout.insertWidget(2, self._reward_coins)
        if compact_values and coins:
            self._reward_coins.setText(format_garden_coins(coins, signed=True, include_unit=False))
        self._reward_coins.setAccessibleName(format_garden_coins(coins, signed=True))
        inventory_labels = _hero_inventory_labels(bundle)
        self._reward_inventory.setText(" · ".join(inventory_labels))
        self._reward_inventory.setVisible(bool(inventory_labels))
        self._sync_current_reward_secondary()
        retained_plant_art = self._reward_full_pixmap if mode == "history" else None
        self._set_reward_art(_bundle_hero(bundle), _hero_kind(bundle))
        # The completed plant already has the primary artwork region. Keep
        # separate artwork for rewards about other items or historical plants.
        self._reward_art.setVisible(not (active_milestone and mode != "history"))
        if mode == "history":
            # The reveal can display historical art, but the plant-card
            # override must continue to reference the live milestone art.
            self._reward_full_pixmap = retained_plant_art
        self._reward_reveal.show()
        self.setProperty("hudRewardVisible", True)
        self._sync_reward_dock_visibility()
        if mode == "new":
            self._fade_reward_in()
        else:
            if self._reward_reveal_animation is not None:
                try:
                    self._reward_reveal_animation.stop()
                except Exception:
                    pass
                self._reward_reveal_animation = None
            self._reward_reveal.setGraphicsEffect(None)
        kind = _hero_kind(bundle)
        if mode == "new" and kind in {
            "full_bloom",
            "full-bloom",
            "stage_change",
            "stage-change",
        }:
            self.celebrate_milestone(kind, bundle)
        hold_ms = _integer(_value(bundle, "hold_ms", default=_REVEAL_HOLD_MS))
        if self._reward_minimum_hold_elapsed:
            self._reward_timer.stop()
        elif hold_remaining_ms is not None:
            remaining = max(0, int(hold_remaining_ms or 0))
            if remaining:
                self._reward_timer.start(remaining)
            else:
                self._mark_reward_hold_elapsed()
        else:
            self._reward_timer.start(max(2_500, min(3_500, hold_ms or _REVEAL_HOLD_MS)))
        ReviewGardenHud._maybe_archive_current_reward(self)
        self.reposition()

    def _sync_reward_identity_visibility(self) -> None:
        """Reconcile reward identity with the plant currently shown above it."""

        bundle = self._current_reward
        if bundle is None:
            return
        subtitle = _reward_hero_subtitle(bundle)
        displayed_plant_id = str(
            self._projection.nurture.plant_id if self._projection is not None else ""
        )
        event_plant_id = _full_bloom_plant_id(bundle)
        event_plant_name = str(
            _value(_bundle_hero(bundle), "plant_name", default="") or ""
        ).strip()
        suppress_identity = bool(
            _hero_kind(bundle).replace("-", "_") in {"full_bloom", "stage_change"}
            and self._reward_presentation_mode != "history"
        ) or bool(
            displayed_plant_id
            and event_plant_id == displayed_plant_id
            and event_plant_name
            and subtitle.casefold() == event_plant_name.casefold()
        )
        self._reward_subtitle.set_full_text("" if suppress_identity else subtitle)
        self._reward_subtitle.setVisible(bool(subtitle and not suppress_identity))
        self._reward_reveal.setProperty(
            "activePlantIdentitySuppressed", suppress_identity
        )
        self._reward_reveal.setProperty("rewardEventPlantId", event_plant_id)
        self._reward_reveal.setProperty("displayedPlantId", displayed_plant_id)

    def _sync_current_reward_secondary(self) -> None:
        bundle = self._current_reward
        if bundle is None:
            for cell, chip in zip(
                self._reward_summary_cells,
                self._reward_summary_chips,
            ):
                chip.set_full_text("")
                chip.hide()
                cell.hide()
            self._reward_summary_row.hide()
            self._reward_secondary.clear()
            self._reward_secondary.hide()
            self._reward_detail_panel.hide()
            for row in self._reward_detail_rows:
                row.hide()
            self._reward_details_toggle.hide()
            return
        compact = _compact_projection(bundle)
        visible_summaries = _compact_visible_summaries(bundle)
        hidden_summaries = _compact_hidden_summaries(bundle)
        detail_rows = _structured_reward_details(bundle)
        detail_event_ids = tuple(dict.fromkeys(
            str(event_id)
            for detail in detail_rows
            for event_id in tuple(_value(detail, "event_ids", default=()) or ())
            if str(event_id)
        ))
        self._reward_reveal.setProperty("rewardDetailEventIds", detail_event_ids)
        if self._reward_details_expanded:
            self._ensure_reward_detail_rows(len(detail_rows))
            for cell, chip in zip(
                self._reward_summary_cells,
                self._reward_summary_chips,
            ):
                chip.hide()
                cell.hide()
            self._reward_summary_row.hide()
            compatibility_lines: list[str] = []
            for index, row in enumerate(self._reward_detail_rows):
                detail = detail_rows[index] if index < len(detail_rows) else None
                category = str(
                    _value(detail, "category_label", "category", default="") or ""
                )
                name = str(_value(detail, "name", default="") or "")
                value = str(_value(detail, "value", default="") or "")
                event_ids = tuple(
                    str(event_id)
                    for event_id in tuple(
                        _value(detail, "event_ids", default=()) or ()
                    )
                    if str(event_id)
                )
                artwork_ref = str(
                    _value(detail, "artwork_ref", "art_asset", default="") or ""
                )
                artwork = self._reward_detail_artworks[index]
                item_art = (
                    self._effect_art_pixmap(detail, 26)
                    if detail is not None and artwork_ref
                    else QPixmap()
                )
                uses_item_art = not item_art.isNull()
                if item_art.isNull() and detail is not None:
                    category_key = category.casefold()
                    fallback_icon = (
                        "environment-discovery"
                        if "discovery" in category_key else
                        "find"
                        if "find" in category_key else
                        "coin"
                        if "coin" in value.casefold() else
                        "growth"
                        if "growth" in value.casefold() else
                        "stage"
                    )
                    item_art = self._icon_pixmap(
                        fallback_icon,
                        24,
                        GARDEN_THEME["text_secondary"],
                    )
                artwork.setPixmap(item_art)
                artwork.setProperty("hudRewardDetailArtworkRef", artwork_ref)
                artwork.setProperty(
                    "hudRewardDetailUsesItemArt",
                    uses_item_art,
                )
                artwork.setAccessibleName(
                    f"{name or category or 'Reward'} artwork"
                )
                self._reward_detail_categories[index].set_full_text(category)
                self._reward_detail_names[index].set_full_text(name)
                value_widget = self._reward_detail_values[index]
                value_widget.setText(value)
                value_widget.setProperty("hudGrowth", "growth" in value.casefold())
                value_widget.setProperty(
                    "hudCoin", "coin" in value.casefold()
                )
                _repolish(value_widget)
                row.setProperty("rewardEventIds", event_ids)
                row.setVisible(bool(detail))
                if detail:
                    compatibility_lines.append(
                        " ".join(part for part in (category, name, value) if part)
                    )
            self._reward_secondary.setText("\n".join(compatibility_lines))
            self._reward_secondary.hide()
            self._reward_detail_panel.setVisible(bool(detail_rows))
        else:
            labels = [
                _compact_summary_label(summary) or _secondary_label(summary)
                for summary in visible_summaries[:2]
            ]
            for index, (cell, icon, chip) in enumerate(zip(
                self._reward_summary_cells,
                self._reward_summary_icons,
                self._reward_summary_chips,
            )):
                summary = visible_summaries[index] if index < len(visible_summaries) else None
                text = labels[index] if index < len(labels) else ""
                key = str(_value(summary, "key", default="") or "").casefold()
                raw_reward_type = _value(
                    summary,
                    "reward_type",
                    "semantic_type",
                    default=key,
                )
                reward_type = str(
                    getattr(raw_reward_type, "value", raw_reward_type) or key
                ).replace("-", "_").casefold()
                tone = "growth" if reward_type == "growth" else "default"
                icon_name = (
                    "growth"
                    if reward_type == "growth"
                    else "environment-discovery"
                    if reward_type == "environment_discovery"
                    else "find"
                    if reward_type == "garden_find"
                    else "coin"
                    if reward_type == "coins"
                    else "stage"
                )
                icon_color = (
                    GARDEN_THEME["reviewer_hud_growth"]
                    if tone == "growth"
                    else GARDEN_THEME["text_secondary"]
                )
                artwork_refs = tuple(
                    str(ref)
                    for ref in tuple(
                        _value(summary, "artwork_refs", default=()) or ()
                    )
                    if str(ref)
                )
                artwork_ref = str(
                    _value(summary, "artwork_ref", default="")
                    or (artwork_refs[0] if artwork_refs else "")
                    or ""
                )
                use_semantic_discovery_icon = bool(
                    reward_type == "environment_discovery"
                    and len(artwork_refs) > 1
                )
                item_art = (
                    QPixmap()
                    if use_semantic_discovery_icon
                    else self._effect_art_pixmap(
                        summary if summary is not None else artwork_ref,
                        12,
                    )
                )
                uses_item_art = not item_art.isNull()
                icon.setPixmap(
                    item_art
                    if uses_item_art
                    else self._icon_pixmap(icon_name, 12, icon_color)
                )
                icon.setProperty("hudRewardSummaryArtworkRef", artwork_ref)
                icon.setProperty("hudRewardSummaryArtworkRefs", artwork_refs)
                icon.setProperty("hudRewardSummaryUsesItemArt", uses_item_art)
                icon.setProperty(
                    "hudRewardSummaryIconKind",
                    "environment-discovery"
                    if use_semantic_discovery_icon
                    else "item-art"
                    if uses_item_art
                    else icon_name,
                )
                cell.setProperty("rewardType", reward_type)
                cell.setProperty(
                    "rewardRarity",
                    str(_value(summary, "rarity", default="") or "").casefold(),
                )
                text = text.replace("Garden discoveries", "Discoveries").replace("Garden discovery", "Discovery")
                chip.set_full_text(text)
                chip.setProperty("metricTone", tone)
                cell_layout = cell.layout()
                cell_margins = cell_layout.contentsMargins()
                width_weight = reward_summary_cell_width_weight(
                    chip.fontMetrics().horizontalAdvance(text),
                    icon_width=icon.width(),
                    spacing=cell_layout.spacing(),
                    horizontal_inset=(
                        cell_margins.left() + cell_margins.right()
                    ),
                )
                self._reward_summary_layout.setStretch(index, width_weight)
                cell.setProperty(
                    "hudRewardSummaryWidthWeight",
                    width_weight,
                )
                _repolish(chip)
                chip.setVisible(bool(text))
                cell.setVisible(bool(text))
            self._reward_summary_row.setVisible(bool(labels))
            self._reward_secondary.clear()
            self._reward_secondary.hide()
            self._reward_detail_panel.hide()
            for row in self._reward_detail_rows:
                row.hide()
        details_available = bool(detail_rows)
        details_text = "Hide details" if self._reward_details_expanded else "Details ›"
        self._reward_details_toggle.setText(details_text)
        self._reward_details_toggle.setAccessibleName(
            "Hide reward details"
            if self._reward_details_expanded
            else "Show reward details"
        )
        self._reward_details_toggle.setMinimumWidth(
            self._reward_details_toggle.fontMetrics().horizontalAdvance(details_text)
            + 12
        )
        self._reward_details_toggle.setVisible(details_available)
        self._reward_reveal.setProperty(
            "visibleRewardSummaryCount",
            min(2, len(visible_summaries)),
        )
        self._reward_reveal.setProperty(
            "hiddenRewardSummaryCount",
            len(hidden_summaries),
        )
        self._reward_reveal.setProperty(
            "hiddenRewardEventCount",
            _integer(
                _value(compact, "hidden_event_count", default=None)
                if compact is not None
                else _value(bundle, "remaining_count", default=0)
            ),
        )
        self._reward_reveal.setMaximumHeight(
            16_777_215
            if self._reward_details_expanded
            else _COMPACT_REWARD_MAX_HEIGHT
        )
        self._reward_reveal.setMinimumHeight(
            240
            if self._reward_details_expanded
            else 1
        )
        self._sync_reward_dock_visibility()

    def _set_reward_art(self, hero: Any, kind: str) -> None:
        resolved: Any = None
        if callable(self._resolve_reward_art):
            try:
                resolved = self._resolve_reward_art(hero)
            except Exception:
                resolved = None
        if resolved is None:
            resolved = _hero_art(hero)
        candidate_path = getattr(resolved, "path", resolved)
        normalized_kind = str(kind or "").replace("-", "_").casefold()
        if (
            normalized_kind in {"full_bloom", "stage_change"}
            and candidate_path
            and not hasattr(resolved, "isNull")
        ):
            cache_key = f"milestone-medallion:{candidate_path}"
            cached = self._reward_art_cache.get(cache_key)
            if cached is not None:
                pixmap = QPixmap(cached)
            else:
                try:
                    pixmap = _alpha_cropped_pixmap(QPixmap(str(candidate_path)))
                except Exception:
                    pixmap = QPixmap()
                if not pixmap.isNull():
                    self._reward_art_cache[cache_key] = QPixmap(pixmap)
                    while len(self._reward_art_cache) > 32:
                        self._reward_art_cache.pop(next(iter(self._reward_art_cache)))
        elif hasattr(resolved, "isNull"):
            pixmap = QPixmap(resolved)
        else:
            cache_key = str(candidate_path or "")
            cached = self._reward_art_cache.get(cache_key)
            pixmap = (
                QPixmap(cached)
                if cached is not None
                else QPixmap(cache_key)
                if cache_key
                else QPixmap()
            )
            if cache_key and cached is None and not pixmap.isNull():
                self._reward_art_cache[cache_key] = QPixmap(pixmap)
                while len(self._reward_art_cache) > 32:
                    self._reward_art_cache.pop(next(iter(self._reward_art_cache)))
        is_milestone = normalized_kind in {"full_bloom", "stage_change"}
        if not pixmap.isNull():
            self._reward_full_pixmap = QPixmap(pixmap)
            pixmap = pixmap.scaled(
                46 if is_milestone else 48,
                46 if is_milestone else 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            icon_name = "stage" if "stage" in kind or "bloom" in kind else "growth"
            pixmap = self._icon_pixmap(icon_name, 46, GARDEN_THEME["reviewer_hud_growth"])
            self._reward_full_pixmap = QPixmap(pixmap)
        self._reward_art.setPixmap(pixmap)
        self._reward_art.setProperty(
            "milestoneMedallion",
            is_milestone,
        )
        _repolish(self._reward_art)

    def _fade_reward_in(self) -> None:
        if not self._animations_enabled:
            self._reward_reveal.setGraphicsEffect(None)
            return
        if self._reward_reveal_animation is not None:
            try:
                self._reward_reveal_animation.stop()
            except Exception:
                pass
        effect = QGraphicsOpacityEffect(self._reward_reveal)
        self._reward_reveal.setGraphicsEffect(effect)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: (
                effect.setOpacity(float(value))
                if self._reward_reveal_animation is animation
                else None
            )
        )

        def finish() -> None:
            if self._reward_reveal_animation is not animation:
                return
            self._reward_reveal.setGraphicsEffect(None)
            self._reward_reveal_animation = None

        animation.finished.connect(finish)
        self._reward_reveal_animation = animation
        animation.start()

    def clear_reward(
        self,
        *,
        reveal_state: RewardRevealState = "hidden",
    ) -> None:
        self._reward_timer.stop()
        if self._reward_reveal_animation is not None:
            try:
                self._reward_reveal_animation.stop()
            except Exception:
                pass
            self._reward_reveal_animation = None
        self._reward_reveal.setGraphicsEffect(None)
        self._current_reward = None
        self._reward_details_expanded = False
        self._reward_minimum_hold_elapsed = False
        self._reward_next_commit_seen = False
        self._history_reward_inspection = None
        self._reward_presentation_mode = ""
        self.setProperty("hudRewardMinimumHoldElapsed", False)
        self.setProperty("hudRewardNextCommitSeen", False)
        self.setProperty("hudHistoricalRewardInspection", False)
        self._reward_reveal.setProperty("rewardDetailsExpanded", False)
        ReviewGardenHud._set_reward_reveal_state(self, reveal_state)
        self._reward_reveal.setProperty("activeMilestone", False)
        self._reward_accent.hide()
        _repolish(self._reward_reveal)
        self._reward_reveal.setMinimumHeight(_COMPACT_REWARD_MIN_HEIGHT)
        self._reward_reveal.setMaximumHeight(_COMPACT_REWARD_MAX_HEIGHT)
        self._reward_details_toggle.hide()
        self._reward_coin_icon.hide()
        self._reward_reveal.hide()
        self.setProperty("hudRewardVisible", False)
        self._sync_reward_dock_visibility()
        self.reposition()

    def _archive_current_reward(self) -> None:
        self.clear_reward(reveal_state="archived")
        if not self._collapsed and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())

    def _history_line(self, bundle: Any) -> str:
        if _value(bundle, "event_ids", default=None) is not None:
            category = str(_value(bundle, "category_label", default="") or "").strip()
            name = str(_value(bundle, "name", default="") or "").strip()
            value = str(_value(bundle, "value", default="") or "").strip()
            if category.casefold() in {"milestone", "routine growth"}:
                leading = name or category
            elif category and name:
                leading = f"{category}: {name}"
            else:
                leading = name or category
            return " · ".join(part for part in (leading, value) if part)
        growth_units, coins = _hero_amounts(bundle)
        amounts: list[str] = []
        if growth_units:
            amounts.append(f"{format_growth_units(growth_units, signed=True)} Growth")
        if coins:
            amounts.append(format_garden_coins(coins, signed=True))
        amounts.extend(_hero_inventory_labels(bundle))
        return " · ".join((_hero_title(bundle), *amounts))

    def _sync_history_rows(self) -> None:
        atomic_bundles = tuple(self._reward_history)
        try:
            from ..reward_presentation import project_reward_session_history

            projected = project_reward_session_history(atomic_bundles)
        except (ImportError, TypeError, ValueError):
            projected = ()
        if projected:
            routine_rows = tuple(
                row
                for row in projected
                if str(_value(row, "category_label", default="") or "").casefold()
                == "routine growth"
            )
            meaningful_rows = tuple(
                row for row in projected if row not in routine_rows
            )
            all_recent = (*tuple(reversed(meaningful_rows)), *routine_rows)
        else:
            all_recent = tuple(reversed(atomic_bundles))
        event_to_bundle: dict[str, Any] = {}
        for bundle in atomic_bundles:
            for item in tuple(_value(bundle, "all_items", "items", default=()) or ()):
                event_id = str(_value(item, "event_id", default="") or "")
                if event_id:
                    event_to_bundle.setdefault(event_id, bundle)
        page_size = len(self._history_labels)
        page_count = max(1, (len(all_recent) + page_size - 1) // page_size)
        self._reward_history_page %= page_count
        start = self._reward_history_page * page_size
        recent = all_recent[start : start + page_size]
        def source_bundle(row: Any) -> Any | None:
            event_ids = _value(row, "event_ids", default=None)
            if event_ids is None:
                return row
            if (
                str(_value(row, "category_label", default="") or "").casefold()
                == "routine growth"
            ):
                return None
            first_event_id = next(iter(tuple(event_ids or ())), "")
            return event_to_bundle.get(str(first_event_id or ""))

        self._visible_history_bundles = tuple(source_bundle(row) for row in recent)
        self._projected_history_count = len(all_recent)
        for index, label in enumerate(self._history_labels):
            text = self._history_line(recent[index]) if index < len(recent) else ""
            label.set_full_text(text)
            self._history_rows[index].setVisible(bool(text))
            self._history_rows[index].setCursor(
                Qt.CursorShape.PointingHandCursor
                if index < len(self._visible_history_bundles)
                and self._visible_history_bundles[index] is not None
                else Qt.CursorShape.ArrowCursor
            )
        self._history_pager.setVisible(len(all_recent) > page_size)
        self._history_pager.setText(
            "Latest rewards ↑"
            if self._reward_history_page + 1 >= page_count
            else "Earlier rewards ›"
        )
        self._history_pager.setProperty("historyPage", self._reward_history_page)
        self._history_pager.setProperty("historyPageCount", page_count)
        available = bool(all_recent) or self._session_has_results
        self._session_footer.setProperty("historyAvailable", available)
        history_expanded = bool(
            self._session_footer.property("historyExpanded")
        )
        self._set_session_history_chevron(history_expanded)
        self._session_history_chevron.setVisible(available)
        self._session_footer.setCursor(
            Qt.CursorShape.PointingHandCursor
            if available
            else Qt.CursorShape.ArrowCursor
        )
        _repolish(self._session_footer)

    def _advance_reward_history_page(self) -> None:
        history_count = max(
            0,
            int(getattr(self, "_projected_history_count", len(self._reward_history))),
        )
        if history_count <= len(self._history_labels):
            return
        page_size = len(self._history_labels)
        page_count = max(1, (history_count + page_size - 1) // page_size)
        self._reward_history_page = (self._reward_history_page + 1) % page_count
        self._sync_history_rows()
        self._sync_reward_dock_visibility()
        self.reposition()

    def _reopen_history_reward(self, index: int) -> None:
        recent = tuple(getattr(self, "_visible_history_bundles", ()) or ())
        if not (0 <= int(index) < len(recent)):
            return
        bundle = recent[int(index)]
        if bundle is None:
            return
        self._reward_history_panel.hide()
        self._session_footer.setProperty("historyExpanded", False)
        self._set_session_history_chevron(False)
        if (
            self._current_reward is not None
            and _bundle_id(self._current_reward) == _bundle_id(bundle)
        ):
            self._reward_details_expanded = True
            self._reward_reveal.setProperty("rewardDetailsExpanded", True)
            ReviewGardenHud._set_reward_reveal_state(self, "details_open")
            self._sync_current_reward_secondary()
            self._sync_reward_dock_visibility()
            self.reposition()
            return
        suspended = ReviewGardenHud._capture_current_reward_runtime_state(self) or {
            "bundle": None,
            "minimum_hold_elapsed": True,
            "details_expanded": False,
            "next_commit_seen": False,
            "reveal_state": "hidden",
            "hold_remaining_ms": 0,
        }
        self._history_reward_inspection = suspended
        self._reward_timer.stop()
        self.setProperty("hudHistoricalRewardInspection", True)
        self._show_reward(
            bundle,
            expanded=True,
            presentation="history",
            minimum_hold_elapsed=True,
        )

    def _close_history_reward_inspection(self) -> None:
        suspended = self._history_reward_inspection
        if suspended is None:
            return
        self._history_reward_inspection = None
        self.setProperty("hudHistoricalRewardInspection", False)
        bundle = suspended.get("bundle")
        if _bundle_id(bundle):
            self._show_reward(
                bundle,
                expanded=bool(suspended.get("details_expanded", False)),
                presentation="restored",
                minimum_hold_elapsed=bool(
                    suspended.get("minimum_hold_elapsed", False)
                ),
                next_commit_seen=bool(
                    suspended.get("next_commit_seen", False)
                ),
                reveal_state=str(suspended.get("reveal_state", "") or ""),
                hold_remaining_ms=max(
                    0,
                    int(suspended.get("hold_remaining_ms", 0) or 0),
                ),
            )
            return
        self.clear_reward()
        if not self._collapsed and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())

    def _toggle_reward_history(self) -> None:
        if not self._session_has_results:
            return
        expanded = not bool(self._session_footer.property("historyExpanded"))
        self._reward_history_panel.setVisible(expanded and bool(self._reward_history))
        self._session_footer.setProperty("historyExpanded", expanded)
        self._set_session_history_chevron(expanded)
        if expanded:
            self._unseen_major = 0
            self._sync_unseen_badge()
        _call(self._on_expand_rewards, expanded)
        self._sync_reward_dock_visibility()
        self.reposition()

    def _set_session_history_chevron(self, expanded: bool) -> None:
        direction = "up" if expanded else "down"
        self._session_history_chevron.setProperty(
            "chevronDirection", direction
        )
        self._session_history_chevron.setPixmap(self._icon_pixmap(
            f"chevron-{direction}",
            13,
            GARDEN_THEME["text_secondary"],
        ))
        self._session_history_chevron.setAccessibleName(
            "Collapse session history" if expanded else "Expand session history"
        )

    def _sync_unseen_badge(self) -> None:
        count = max(0, self._unseen_major)
        self._collapsed_badge.setText("9+" if count > 9 else str(count))
        self._collapsed_badge.setVisible(count > 0)
        self.setProperty("hudUnseenMajorRewards", count)

    def _host_answer_controls_geometry(
        self,
        parent: Any,
        viewport_width: int,
        viewport_height: int,
    ) -> tuple[int | None, tuple[int, int, int, int] | None, int, str]:
        """Resolve measured host/WebEngine geometry in HUD logical pixels."""

        viewport_width = max(1, int(viewport_width))
        viewport_height = max(1, int(viewport_height))

        def host_property(key: str) -> Any:
            try:
                return parent.property(key)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return None

        measured = host_property("reviewerAnswerControlsMeasured")
        rect = _property_int_tuple(
            host_property("reviewerAnswerControlsRect"),
            ("x", "y", "width", "height"),
        )
        measured_viewport = _property_int_tuple(
            host_property("reviewerAnswerControlsViewport"),
            ("width", "height"),
        )
        viewport_matches = bool(
            measured_viewport is None
            or (
                abs(measured_viewport[0] - viewport_width) <= 2
                and abs(measured_viewport[1] - viewport_height) <= 2
            )
        )
        if measured is not False and rect is not None and viewport_matches:
            x, top, width, height = rect
            if (
                x >= 0
                and viewport_height // 2 <= top <= viewport_height
                and width > 0
                and height > 0
                and x + width <= viewport_width + 2
                and top + height <= viewport_height + 2
            ):
                source = str(
                    host_property("reviewerAnswerControlsSource")
                    or "host-rect-property"
                )
                return top, rect, max(0, viewport_height - top), source

        for key in ("reviewerAnswerControlsTop", "answerControlsTop"):
            try:
                if key == "reviewerAnswerControlsTop" and (
                    measured is False or not viewport_matches
                ):
                    continue
                raw = host_property(key)
                if raw is not None:
                    value = int(raw)
                    if 0 < value <= viewport_height:
                        source = str(
                            host_property("reviewerAnswerControlsSource")
                            or "host-top-property"
                        )
                        return (
                            value,
                            None,
                            max(0, viewport_height - value),
                            source,
                        )
            except (TypeError, ValueError):
                pass

        candidates: list[tuple[int, tuple[int, int, int, int]]] = []
        try:
            children = parent.findChildren(QWidget)
        except (AttributeError, RuntimeError, TypeError):
            children = ()
        for child in children:
            try:
                if child is self or self.isAncestorOf(child) or not child.isVisible():
                    continue
                identity = " ".join(
                    str(value or "")
                    for value in (
                        child.objectName(),
                        child.accessibleName(),
                        child.text() if callable(getattr(child, "text", None)) else "",
                    )
                ).casefold().replace(" ", "")
                if not any(
                    marker in identity
                    for marker in (
                        "showanswer",
                        "answerbuttons",
                        "answerbutton",
                        "reviewerbottom",
                        "ease1",
                        "ease2",
                        "ease3",
                        "ease4",
                    )
                ):
                    continue
                point = child.mapTo(parent, child.rect().topLeft())
                x = int(point.x())
                top = int(point.y())
                width = max(1, int(child.width()))
                height = max(1, int(child.height()))
                if viewport_height // 2 <= top <= viewport_height:
                    candidates.append((top, (x, top, width, height)))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        if candidates:
            top, candidate_rect = min(candidates, key=lambda item: item[0])
            return (
                top,
                candidate_rect,
                max(0, viewport_height - top),
                "host-widget",
            )
        return None, None, HUD_CONTROLS_CLEARANCE, "fallback"

    def _host_answer_controls_top(
        self,
        parent: Any,
        viewport_height: int,
    ) -> tuple[int | None, str]:
        """Compatibility wrapper for callers that only need the top edge."""

        try:
            viewport_width = max(1, int(parent.width()))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            viewport_width = 1
        top, _rect, _clearance, source = self._host_answer_controls_geometry(
            parent,
            viewport_width,
            viewport_height,
        )
        return top, source

    def reposition(
        self,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        answer_controls_top: int | None = None,
    ) -> tuple[int, int, int, int]:
        parent = self.parentWidget()
        if parent is None:
            return (self.x(), self.y(), self.width(), self.height())
        try:
            width = max(1, int(parent.width() if viewport_width is None else viewport_width))
            height = max(1, int(parent.height() if viewport_height is None else viewport_height))
            detected_top = answer_controls_top
            detected_rect: tuple[int, int, int, int] | None = None
            detected_clearance = HUD_CONTROLS_CLEARANCE
            clearance_source = "argument" if detected_top is not None else "fallback"
            if detected_top is None:
                (
                    detected_top,
                    detected_rect,
                    detected_clearance,
                    clearance_source,
                ) = self._host_answer_controls_geometry(
                    parent,
                    width,
                    height,
                )
            else:
                detected_top = max(1, min(height, int(detected_top)))
                detected_clearance = max(0, height - detected_top)
            if self._collapsed:
                content_height = None
            else:
                body_layout = self._body_contents.layout()
                reward_layout = self._reward_dock.layout()
                natural_width = max(1, reviewer_hud_width(width) - 2)

                def natural_height(widget: Any, layout: Any) -> int:
                    layout.invalidate()
                    layout.activate()
                    widget.updateGeometry()
                    size_hint = max(1, int(widget.sizeHint().height()))
                    layout_hint = max(1, int(layout.sizeHint().height()))
                    try:
                        width_height = int(layout.heightForWidth(natural_width))
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        width_height = -1
                    return max(
                        size_hint,
                        layout_hint,
                        width_height if width_height >= 0 else 0,
                    )

                # Word-wrapped plant and reward labels can grow after their
                # text changes but before Qt updates the widget-level size
                # hint. Ask each layout for its height at the final HUD width
                # so the shell expands instead of needlessly scrolling at the
                # canonical reviewer size.
                self._apply_body_compact_level(1)
                body_height = natural_height(self._body_contents, body_layout)
                uncompacted_body_height = body_height
                reward_height = (
                    natural_height(self._reward_dock, reward_layout)
                    if not self._reward_dock.isHidden()
                    else 0
                )
                available_height = max(
                    1,
                    reviewer_hud_safe_bottom(height, detected_top)
                    - HUD_TOP_MARGIN,
                )
                full_bloom = bool(
                    self._full_bloom_bundle is not None
                    or self._settled_full_bloom_bundle is not None
                    or self._plant_card.property("fullBloomSettled")
                )
                if full_bloom:
                    if 46 + body_height + reward_height > 680:
                        # Keep milestone art and copy intact; tightening only
                        # the outer body gutters removes the canonical 10px
                        # scroll range before any optional content scrolls.
                        self._apply_body_compact_level(1)
                        body_height = natural_height(
                            self._body_contents,
                            body_layout,
                        )
                else:
                    for compact_level in (1, 2):
                        if 46 + body_height + reward_height <= min(420 + reward_height, available_height):
                            break
                        self._apply_body_compact_level(compact_level)
                        body_height = natural_height(
                            self._body_contents,
                            body_layout,
                        )
                # The styled shell contributes a one-pixel border on both
                # vertical edges. Include both the independently anchored
                # reward dock and the 44px header so the dock never steals
                # height from the daily/plant body at its natural size.
                content_height = 46 + body_height + reward_height
                self.setProperty("hudBodyNaturalHeight", body_height)
                self.setProperty(
                    "hudBodyUncompactedHeight", uncompacted_body_height
                )
                self.setProperty("hudRewardDockNaturalHeight", reward_height)
                self.setProperty(
                    "hudBodyScrollExpected",
                    bool(content_height > available_height),
                )
            geometry = reviewer_hud_geometry(
                width,
                height,
                collapsed=self._collapsed,
                dock=self._dock,
                content_height=content_height,
                answer_controls_top=detected_top,
            )
            self.setFixedSize(geometry[2], geometry[3])
            self.move(geometry[0], geometry[1])
            self.setProperty("hudContentHeight", int(content_height or geometry[3]))
            self.setProperty("reviewerViewportWidth", width)
            self.setProperty("reviewerViewportHeight", height)
            self.setProperty("hudAnswerControlsTop", detected_top)
            self.setProperty(
                "hudAnswerControlsRect",
                list(detected_rect) if detected_rect is not None else None,
            )
            self.setProperty(
                "hudAnswerControlsClearance",
                detected_clearance,
            )
            self.setProperty("hudAnswerControlsSource", clearance_source)
            self.setProperty(
                "hudAnswerControlsMeasured",
                detected_top is not None,
            )
            self.setProperty("hudAnswerControlsViewport", [width, height])
            self.raise_()
            return geometry
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return (self.x(), self.y(), self.width(), self.height())

    def _schedule_answer_controls_refresh(self) -> None:
        """Measure immediately and once more after resize geometry settles."""

        self._answer_controls_resize_revision += 1
        revision = self._answer_controls_resize_revision

        def request_if_current() -> None:
            if (
                self._disposed
                or revision != self._answer_controls_resize_revision
                or self._viewport_parent is None
            ):
                return
            _call(
                self._on_request_answer_controls,
                self._viewport_parent,
            )

        QTimer.singleShot(0, request_if_current)
        # WebEngine and the native bottom toolbar settle on separate event
        # turns. The second, debounced probe replaces any measurement whose
        # source or target dimensions changed during the immediate callback.
        QTimer.singleShot(
            _ANSWER_CONTROLS_RESIZE_SETTLE_MS,
            request_if_current,
        )

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self._viewport_parent:
            try:
                if event.type() in {QEvent.Type.Resize, QEvent.Type.Show}:
                    QTimer.singleShot(0, self.reposition)
                    self._schedule_answer_controls_refresh()
            except Exception:
                pass
        return False

    def dispose(self) -> None:
        self._disposed = True
        self._answer_controls_resize_revision += 1
        self._revision += 1
        self._coin_feedback_revision += 1
        self._growth_feedback_revision += 1
        self._today_feedback_revision += 1
        self._session_feedback_revision += 1
        self._celebration_revision += 1
        self._reward_timer.stop()
        self._settle_plant_motion()
        self._stop_session_count_animation()
        for animation_name in (
            "_coin_animation",
            "_art_animation",
            "_answer_row_animation",
            "_today_animation",
            "_today_copy_animation",
            "_reward_reveal_animation",
        ):
            animation = getattr(self, animation_name, None)
            if animation is not None:
                try:
                    animation.stop()
                except Exception:
                    pass
            setattr(self, animation_name, None)
        parent = self._viewport_parent
        if parent is not None:
            try:
                parent.removeEventFilter(self)
            except Exception:
                pass
        self._viewport_parent = None
        self.setProperty("hudMounted", False)
        self.hide()
        self.deleteLater()


__all__ = ["CheckpointTrack", "ReviewGardenHud"]
