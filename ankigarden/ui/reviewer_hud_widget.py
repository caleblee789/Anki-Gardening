"""Persistent native Qt component for the Reviewer Garden HUD."""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Mapping, Optional

from .formatters import format_quantity
from .plant_art import normalized_plant_pixmap
from .reviewer_hud import (
    ReviewerHudProjection,
    format_growth_units,
    reviewer_hud_geometry,
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
        QLabel,
        QLinearGradient,
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
    QLabel = object  # type: ignore[assignment,misc]
    QLinearGradient = object  # type: ignore[assignment,misc]
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
_REWARD_HISTORY_PAGE_SIZE = 4
_REVEAL_HOLD_MS = 3_200
_COMPACT_REWARD_MAX_HEIGHT = 188
_REWARD_SCROLL_MAX_HEIGHT = 248
_ANSWER_ROW_SWAP_MS = 150
_PROJECTION_APPLY_DELAY_MS = 220
_PROGRESS_FILL_MS = 420
_PLANT_PULSE_MS = 300
_SESSION_HIGHLIGHT_MS = 600
_FULL_BLOOM_PULSE_MS = 680
_NEXT_PROJECTION_RESTORE_MS = 850
_ROUTINE_SESSION_RELEASE_MS = _PROJECTION_APPLY_DELAY_MS + _PROGRESS_FILL_MS


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
    return str(_value(summary, "label", default="") or "").strip()


def _compact_visible_summaries(bundle: Any) -> tuple[Any, ...]:
    compact = _compact_projection(bundle)
    values = tuple(_value(compact, "visible_summaries", default=()) or ())
    if compact is not None:
        return values[:2]
    return _secondary_items(bundle)[:2]


def _compact_hidden_summaries(bundle: Any) -> tuple[Any, ...]:
    compact = _compact_projection(bundle)
    return tuple(_value(compact, "hidden_summaries", default=()) or ())


def _reward_eyebrow(bundle: Any) -> str:
    compact = _compact_projection(bundle)
    explicit = str(_value(compact, "eyebrow", default="") or "").strip()
    if explicit:
        return explicit
    kind = _hero_kind(bundle).replace("-", "_")
    return {
        "full_bloom": "MILESTONE REACHED",
        "stage_change": "MILESTONE REACHED",
        "garden_find": "GARDEN FIND",
        "checkpoint": "CHECKPOINT REACHED",
        "environment_discovery": "DISCOVERY",
    }.get(kind, "REWARD EARNED")


def _reward_hero_title(bundle: Any) -> str:
    compact = _compact_projection(bundle)
    return str(
        _value(compact, "hero_title", default="") or _hero_title(bundle)
    ).strip()


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
) -> tuple[str, str, str, str]:
    progress = max(0, min(100, _integer(progress_percent)))
    next_checkpoint = max(0, min(100, _integer(next_checkpoint_percent)))
    return tuple(
        "next"
        if checkpoint == next_checkpoint
        else "completed"
        if progress >= checkpoint
        else "future"
        for checkpoint in (25, 50, 75, 100)
    )  # type: ignore[return-value]


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
        return f"{format_growth_units(normalized, signed=True)} growth"
    if index == 1:
        return f"+{format_quantity(normalized, 'coin')}"
    return format_quantity(normalized, "find")


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
        amounts.append(f"{format_growth_units(growth, signed=True)} growth")
    if coins:
        amounts.append(f"+{coins:,} coins")
    amounts.extend(_inventory_amount_labels(item))
    return " · ".join(value for value in (label, *amounts) if value) or "Reward"


class _ClickableFrame(QFrame):  # type: ignore[misc,valid-type]
    def __init__(self, parent: Any = None, callback: Callback = None) -> None:
        super().__init__(parent)
        self._activate_callback = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_callback(self, callback: Callback) -> None:
        self._activate_callback = callback

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
            self.setMinimumHeight(metrics.lineSpacing() * 2 + 3)
            self.setMaximumHeight(metrics.lineSpacing() * 2 + 3)
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
        painter.setBrush(QColor("#26000000"))
        width = min(108.0, max(52.0, float(self.width()) * 0.42))
        painter.drawEllipse(QRectF(
            (float(self.width()) - width) / 2.0,
            max(0.0, float(self.height()) - 21.0),
            width,
            11.0,
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
        states = _checkpoint_marker_states(self._progress, self._next_checkpoint)
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
            if int(checkpoint or 0) in (25, 50, 75, 100)
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
        for checkpoint in (25, 50, 75, 100):
            x = left + width * checkpoint / 100.0
            is_next = checkpoint == self._next_checkpoint
            is_completed = self._progress + 0.001 >= checkpoint and not is_next
            is_pulsing = checkpoint == self._pulse_checkpoint
            radius = 3.0 + (1.5 * self._pulse if is_pulsing else 0.0)
            color = (
                GARDEN_THEME["reviewer_hud_coin"]
                if is_next
                else GARDEN_THEME["reviewer_hud_growth"]
                if is_completed
                else GARDEN_THEME["text_muted"]
            )
            painter.setBrush(QColor(color))
            painter.setPen(QPen(
                QColor(GARDEN_THEME["reviewer_hud_growth_track"]),
                1.5 if is_completed or is_next else 1.0,
            ))
            painter.drawEllipse(QRectF(x - radius, 9.0 - radius, radius * 2, radius * 2))
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
        on_toggle_collapsed: Callback = None,
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
        self._on_toggle_collapsed = on_toggle_collapsed
        self._on_expand_rewards = on_expand_rewards
        self._on_effects_overflow = on_effects_overflow
        self._on_open_reward = on_open_reward
        self._resolve_reward_art = resolve_reward_art
        self._animations_enabled = bool(animations_enabled)
        self._projection: ReviewerHudProjection | None = None
        self._disposed = False
        self._collapsed = False
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
        self.setProperty("hudRewardHistoryCount", 0)
        self.setProperty("hudUnseenMajorRewards", 0)
        self.setProperty("hudSessionVisible", False)
        self.setProperty("hudRewardDockVisible", False)
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
        self.setProperty("reviewerControlClearance", 112)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Anki Garden review progress")
        self._apply_style()
        self._build_shell()

        self._reward_timer = QTimer(self)
        self._reward_timer.setSingleShot(True)
        self._reward_timer.timeout.connect(self._compact_current_reward)
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
        """Preserve accepted-but-unrevealed bundles across a HUD remount."""

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
        return {
            "seen_bundle_ids": tuple(self._seen_bundle_ids),
            "history": tuple(self._reward_history),
            "pending": tuple(pending),
            "unseen_major": max(0, int(self._unseen_major)),
        }

    def restore_reward_state(self, snapshot: Mapping[str, Any] | None) -> None:
        if not isinstance(snapshot, Mapping):
            return
        self._seen_bundle_ids.update(
            str(identity)
            for identity in tuple(snapshot.get("seen_bundle_ids", ()) or ())
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
        self._reward_queue.extend(
            bundle
            for bundle in tuple(snapshot.get("pending", ()) or ())
            if _bundle_id(bundle)
        )
        self._unseen_major = max(0, int(snapshot.get("unseen_major", 0) or 0))
        self.setProperty("hudRewardHistoryCount", len(self._reward_history))
        self._sync_history_rows()
        self._sync_unseen_badge()
        if not self._collapsed and self._current_reward is None and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())
        else:
            self._sync_reward_dock_visibility()

    def set_callbacks(
        self,
        *,
        on_open_garden: Callback = None,
        on_open_plant: Callback = None,
        on_toggle_collapsed: Callback = None,
        on_expand_rewards: Callback = None,
        on_effects_overflow: Callback = None,
        on_open_reward: Callback = None,
        resolve_reward_art: Callback = None,
        animations_enabled: bool | None = None,
    ) -> None:
        self._on_open_garden = on_open_garden
        self._on_open_plant = on_open_plant
        self._on_toggle_collapsed = on_toggle_collapsed
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
            "border:1px solid rgba(112,218,169,92);"
            "border-radius:14px;}"
            "QFrame#reviewerHudHeader {background:transparent;border:0;"
            "border-bottom:1px solid " + t["reviewer_hud_divider"] + ";}"
            "QFrame#reviewerHudHeader:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame[hudCard='true'] {background:" + t["reviewer_hud_surface"] + ";border-radius:12px;}"
            "QFrame[hudCard='true'][cardRole='subtle'] {border:1px solid " + t["reviewer_hud_divider"] + ";}"
            "QFrame[hudCard='true'][cardRole='standard'] {border:1px solid " + t["reviewer_hud_border"] + ";}"
            "QFrame#reviewerHudTodayCard[completionSettling='true'] {border-color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QFrame#reviewerHudPlantCard:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudPlantCard[celebration='stage-change'] {border-color:" + t["reviewer_hud_growth_strong"] + ";}"
            "QFrame#reviewerHudPlantCard[celebration='full-bloom'] {border-color:" + t["reviewer_hud_coin"] + ";}"
            "QFrame#reviewerHudArtRegion {background:qradialgradient(cx:0.5,cy:0.54,radius:0.52,"
            "fx:0.5,fy:0.54,stop:0 rgba(103,220,169,42),stop:1 rgba(13,48,39,0));border:0;}"
            "QFrame#reviewerHudArtRegion[artPulse='true'] {background:qradialgradient(cx:0.5,cy:0.54,radius:0.56,"
            "fx:0.5,fy:0.54,stop:0 rgba(132,237,189,78),stop:1 rgba(13,48,39,0));}"
            "QFrame#reviewerHudArtRegion[fullBloomLightRays='true'] {background:qradialgradient(cx:0.5,cy:0.52,radius:0.62,"
            "fx:0.5,fy:0.52,stop:0 rgba(240,194,79,96),stop:0.45 rgba(103,220,169,52),stop:1 rgba(13,48,39,0));}"
            "QFrame#reviewerHudNextAnswer {background:rgba(103,220,169,18);border:0;border-radius:9px;}"
            "QFrame#reviewerHudNextAnswer[resultState='applied'] {background:rgba(103,220,169,30);}"
            "QFrame#reviewerHudRewardDockSurface {background:" + t["reviewer_hud_surface_raised"] + ";"
            "border:1px solid " + t["reviewer_hud_border"] + ";border-radius:12px;}"
            "QFrame#reviewerHudRewardReveal {background:transparent;border:0;border-radius:11px;}"
            "QFrame#reviewerHudRewardDivider {background:" + t["reviewer_hud_divider"] + ";border:0;}"
            "QFrame#reviewerHudSessionFooter {background:transparent;border:0;border-radius:0;}"
            "QFrame#reviewerHudSessionFooter[historyAvailable='true']:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudRewardHistory {background:transparent;border:0;}"
            "QFrame[hudHistoryRow='true'] {background:transparent;border:0;border-radius:7px;}"
            "QFrame[hudHistoryRow='true']:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QFrame#reviewerHudCollapsedTab {background:" + t["reviewer_hud_shell"] + ";"
            "border:1px solid " + t["reviewer_hud_border"] + ";border-radius:14px;}"
            "QLabel {color:" + t["text_primary"] + ";font-size:13px;background:transparent;border:0;}"
            "QLabel[hudHeaderTitle='true'] {font-size:15px;font-weight:600;}"
            "QLabel[hudCoin='true'] {color:" + t["reviewer_hud_coin"] + ";font-weight:650;}"
            "QLabel[hudCoinDelta='true'] {color:" + t["reviewer_hud_coin"] + ";font-size:12px;font-weight:700;}"
            "QLabel[coinPulse='true'] {background:" + t["reviewer_hud_coin_soft"] + ";border-radius:8px;}"
            "QLabel[hudMuted='true'] {color:" + t["text_secondary"] + ";font-size:12px;}"
            "QLabel[hudPlantName='true'] {font-size:20px;font-weight:650;}"
            "QLabel[hudStage='true'] {font-size:13px;font-weight:600;}"
            "QLabel[hudStage='true'][fullBloomAccent='true'] {color:" + t["reviewer_hud_coin"] + ";}"
            "QLabel[hudRewardTitle='true'] {font-size:16px;font-weight:650;}"
            "QLabel[hudGrowth='true'] {color:" + t["reviewer_hud_growth_strong"] + ";font-weight:700;}"
            "QLabel[hudEyebrow='true'] {color:" + t["text_secondary"] + ";font-size:12px;font-weight:700;}"
            "QLabel#reviewerHudRewardArt {background:rgba(103,220,169,24);border-radius:10px;}"
            "QLabel[hudRarity='true'] {background:rgba(103,220,169,28);"
            "color:" + t["reviewer_hud_growth_strong"] + ";border-radius:8px;padding:2px 7px;font-size:12px;font-weight:650;}"
            "QLabel[hudRarity='true'][rarityTone='uncommon'] {background:rgba(121,200,232,34);color:" + t["info"] + ";}"
            "QLabel[hudRarity='true'][rarityTone='rare'] {background:rgba(184,153,234,38);color:#D0B8F2;}"
            "QLabel[hudRarity='true'][rarityTone='exceptional'] {background:" + t["reviewer_hud_coin_soft"] + ";color:" + t["reviewer_hud_coin"] + ";}"
            "QFrame[hudEffectChip='true'] {background:" + t["reviewer_hud_surface_raised"] + ";"
            "color:" + t["text_primary"] + ";border:0;border-radius:8px;padding:0;font-size:12px;}"
            "QLabel[hudEffectLabel='true'] {font-size:12px;}"
            "QLabel[hudRewardChip='true'] {background:" + t["reviewer_hud_surface_raised"] + ";"
            "color:" + t["text_primary"] + ";border:0;border-radius:8px;padding:4px 7px;font-size:12px;}"
            "QLabel[metricChanged='true'] {background:rgba(103,220,169,24);border-radius:6px;}"
            "QProgressBar#reviewerHudTodayProgress {background:" + t["reviewer_hud_growth_track"] + ";"
            "border:0;border-radius:3px;min-height:6px;max-height:6px;}"
            "QProgressBar#reviewerHudTodayProgress::chunk {background:" + t["reviewer_hud_growth"] + ";border-radius:3px;}"
            "QToolButton {background:transparent;border:0;border-radius:8px;color:" + t["text_primary"] + ";padding:0;}"
            "QToolButton:hover {background:" + t["reviewer_hud_surface_hover"] + ";}"
            "QToolButton#reviewerHudEffectsOverflow {background:" + t["reviewer_hud_surface_raised"] + ";"
            "padding:3px 7px;font-size:12px;text-align:right;}"
            "QToolButton#reviewerHudRewardMore {color:" + t["reviewer_hud_growth_strong"] + ";"
            "padding:2px 7px;font-size:12px;font-weight:650;text-align:right;}"
            "QToolButton#reviewerHudSelectPlant {color:" + t["reviewer_hud_coin"] + ";"
            "padding:2px 7px;font-size:12px;font-weight:650;text-align:left;}"
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
        header_layout.setContentsMargins(12, 0, 6, 0)
        header_layout.setSpacing(7)
        leaf = QLabel(self._header)
        leaf.setFixedSize(20, 20)
        leaf.setPixmap(self._icon_pixmap("growth", 19, GARDEN_THEME["reviewer_hud_growth"]))
        leaf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(leaf)
        header_layout.addWidget(leaf)
        self._header_title = QLabel("Anki Garden", self._header)
        self._header_title.setObjectName("reviewerHudHeaderTitle")
        self._header_title.setProperty("hudHeaderTitle", True)
        self._header_title.setMinimumWidth(0)
        _set_decoration(self._header_title)
        header_layout.addWidget(self._header_title)
        header_layout.addStretch(1)
        self._coin_cluster = QFrame(self._header)
        self._coin_cluster.setObjectName("reviewerHudCoinCluster")
        self._coin_cluster.setFixedWidth(118)
        _set_decoration(self._coin_cluster)
        self.setProperty("hudHeaderBalanceReservedWidth", 118)
        coin_layout = QHBoxLayout(self._coin_cluster)
        coin_layout.setContentsMargins(0, 0, 0, 0)
        coin_layout.setSpacing(4)
        self._coin_icon = QLabel(self._coin_cluster)
        self._coin_icon.setFixedSize(17, 17)
        self._coin_icon.setPixmap(self._icon_pixmap("coin", 16, GARDEN_THEME["reviewer_hud_coin"]))
        _set_decoration(self._coin_icon)
        coin_layout.addWidget(self._coin_icon)
        self._coin_balance = QLabel("0", self._coin_cluster)
        self._coin_balance.setProperty("hudCoin", True)
        apply_tabular_numerals(self._coin_balance)
        self._coin_balance.setMinimumWidth(66)
        self._coin_balance.setMaximumWidth(66)
        self._coin_balance.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _set_decoration(self._coin_balance)
        coin_layout.addWidget(self._coin_balance)
        self._coin_delta = QLabel("", self._coin_cluster)
        self._coin_delta.setProperty("hudCoinDelta", True)
        apply_tabular_numerals(self._coin_delta)
        self._coin_delta.hide()
        _set_decoration(self._coin_delta)
        coin_layout.addWidget(self._coin_delta)
        header_layout.addWidget(self._coin_cluster)
        self._collapse_button = QToolButton(self._header)
        self._collapse_button.setObjectName("reviewerHudCollapseButton")
        self._collapse_button.setProperty("semanticId", "reviewer.hud.collapse")
        self._collapse_button.setFixedSize(32, 32)
        self._collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._collapse_button.setAccessibleName("Collapse Anki Garden review panel")
        self._collapse_button.setIcon(self._icon("chevron-right", 18, GARDEN_THEME["text_primary"]))
        self._collapse_button.clicked.connect(self._toggle_from_control)
        header_layout.addWidget(self._collapse_button)
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
        self._today_progress.setTextVisible(False)
        self._today_progress.setRange(0, 100)
        _set_decoration(self._today_progress)
        layout.addWidget(self._today_progress)
        self._today_detail = QLabel("", self._today_card)
        self._today_detail.setProperty("hudMuted", True)
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
        layout = QVBoxLayout(self._plant_card)
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
        layout.addWidget(self._plant_name)

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
        stage_row.addWidget(self._percent)
        layout.addLayout(stage_row)
        self._checkpoint_track = CheckpointTrack(self._plant_card)
        layout.addWidget(self._checkpoint_track)
        self._checkpoint_distance_row = QFrame(self._plant_card)
        self._checkpoint_distance_row.setObjectName("reviewerHudCheckpointDistanceRow")
        self._checkpoint_distance_row.setProperty(
            "semanticId", "reviewer.hud.checkpoint-distance"
        )
        checkpoint_distance_layout = QHBoxLayout(self._checkpoint_distance_row)
        checkpoint_distance_layout.setContentsMargins(0, 0, 0, 0)
        checkpoint_distance_layout.setSpacing(8)
        self._checkpoint = _ElidedLabel("", self._checkpoint_distance_row)
        self._checkpoint.setProperty("hudMuted", True)
        apply_tabular_numerals(self._checkpoint)
        _set_decoration(self._checkpoint)
        checkpoint_distance_layout.addWidget(self._checkpoint, 1)
        self._checkpoint_estimate = QLabel("", self._checkpoint_distance_row)
        self._checkpoint_estimate.setProperty("hudMuted", True)
        apply_tabular_numerals(self._checkpoint_estimate)
        self._checkpoint_estimate.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        _set_decoration(self._checkpoint_estimate)
        checkpoint_distance_layout.addWidget(self._checkpoint_estimate)
        self._checkpoint_distance_row.hide()
        layout.addWidget(self._checkpoint_distance_row)

        self._next_answer = QFrame(self._plant_card)
        self._next_answer.setObjectName("reviewerHudNextAnswer")
        self._next_answer.setProperty("semanticId", "reviewer.hud.next-answer")
        self._next_answer.setProperty("resultState", "projection")
        next_layout = QHBoxLayout(self._next_answer)
        next_layout.setContentsMargins(10, 7, 10, 7)
        next_layout.setSpacing(8)
        self._next_answer_label = QLabel("Next answer", self._next_answer)
        self._next_answer_label.setObjectName("reviewerHudNextAnswerLabel")
        _set_decoration(self._next_answer_label)
        next_layout.addWidget(self._next_answer_label, 1)
        self._next_answer_value = QLabel("", self._next_answer)
        self._next_answer_value.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._next_answer_value)
        _set_decoration(self._next_answer_value)
        next_layout.addWidget(self._next_answer_value)
        layout.addWidget(self._next_answer)

        self._checkpoint_reward_row = QFrame(self._plant_card)
        self._checkpoint_reward_row.setObjectName("reviewerHudCheckpointRewardRow")
        checkpoint_reward_layout = QHBoxLayout(self._checkpoint_reward_row)
        checkpoint_reward_layout.setContentsMargins(0, 0, 0, 0)
        checkpoint_reward_layout.setSpacing(4)
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
        self._checkpoint_reward_context = QLabel(
            "at next checkpoint", self._checkpoint_reward_row
        )
        self._checkpoint_reward_context.setProperty("hudMuted", True)
        _set_decoration(self._checkpoint_reward_context)
        checkpoint_reward_layout.addWidget(self._checkpoint_reward_context)
        checkpoint_reward_layout.addStretch(1)
        self._checkpoint_reward_row.hide()
        layout.addWidget(self._checkpoint_reward_row)
        self._plant_message = QLabel("", self._plant_card)
        self._plant_message.setProperty("hudMuted", True)
        apply_tabular_numerals(self._plant_message)
        self._plant_message.setWordWrap(True)
        _set_decoration(self._plant_message)
        self._plant_message.hide()
        layout.addWidget(self._plant_message)
        self._select_plant = QToolButton(self._plant_card)
        self._select_plant.setObjectName("reviewerHudSelectPlant")
        self._select_plant.setProperty("semanticId", "reviewer.hud.select-plant")
        self._select_plant.setText("Select another plant ›")
        self._select_plant.setMinimumHeight(32)
        self._select_plant.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._select_plant.clicked.connect(self._open_garden)
        self._select_plant.hide()
        layout.addWidget(self._select_plant, 0, Qt.AlignmentFlag.AlignLeft)

        self._effects = QFrame(self._plant_card)
        self._effects.setObjectName("reviewerHudEffects")
        self._effects.setProperty("semanticId", "reviewer.hud.effects")
        effects_layout = QGridLayout(self._effects)
        effects_layout.setContentsMargins(0, 0, 0, 0)
        effects_layout.setSpacing(6)
        self._effect_chips: list[Any] = []
        self._effect_icons: list[Any] = []
        self._effect_labels: list[_ElidedLabel] = []
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
            chip_layout.setContentsMargins(3, 0, 3, 0)
            chip_layout.setSpacing(2)
            icon = QLabel(chip)
            icon.setFixedSize(13, 13)
            _set_decoration(icon)
            chip_layout.addWidget(icon)
            label = _ElidedLabel("", chip)
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
        self._effects_overflow.setMinimumHeight(28)
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
        dock.setContentsMargins(10, 0, 10, 10)
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

        self._reward_reveal = _ClickableFrame(
            self._reward_scroll_contents,
            self._open_current_reward,
        )
        self._reward_reveal.setObjectName("reviewerHudRewardReveal")
        self._reward_reveal.setProperty("semanticId", "reviewer.hud.reward-reveal")
        self._reward_reveal.setMinimumHeight(128)
        self._reward_reveal.setMaximumHeight(_COMPACT_REWARD_MAX_HEIGHT)
        reveal = QVBoxLayout(self._reward_reveal)
        reveal.setContentsMargins(12, 10, 12, 10)
        reveal.setSpacing(5)
        top = QHBoxLayout()
        self._reward_eyebrow = QLabel("GARDEN REWARD", self._reward_reveal)
        self._reward_eyebrow.setObjectName("reviewerHudRewardEyebrow")
        self._reward_eyebrow.setProperty("hudEyebrow", True)
        _set_decoration(self._reward_eyebrow)
        top.addWidget(self._reward_eyebrow)
        top.addStretch(1)
        self._reward_rarity = QLabel("", self._reward_reveal)
        self._reward_rarity.setProperty("hudRarity", True)
        _set_decoration(self._reward_rarity)
        top.addWidget(self._reward_rarity)
        reveal.addLayout(top)
        hero = QHBoxLayout()
        hero.setSpacing(10)
        self._reward_art = QLabel(self._reward_reveal)
        self._reward_art.setObjectName("reviewerHudRewardArt")
        self._reward_art.setFixedSize(56, 56)
        self._reward_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_decoration(self._reward_art)
        hero.addWidget(self._reward_art)
        hero_copy = QVBoxLayout()
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
        primary_values.setSpacing(8)
        self._reward_growth = QLabel("", self._reward_reveal)
        self._reward_growth.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._reward_growth)
        _set_decoration(self._reward_growth)
        primary_values.addWidget(self._reward_growth)
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
        summary_layout.setSpacing(6)
        self._reward_summary_chips: list[_ElidedLabel] = []
        for index, object_name in enumerate((
            "reviewerHudRewardSummaryChip0",
            "reviewerHudRewardSummaryChip1",
        )):
            chip = _ElidedLabel("", self._reward_summary_row)
            chip.setObjectName(object_name)
            chip.setProperty("hudRewardChip", True)
            apply_tabular_numerals(chip)
            chip.setMinimumHeight(26)
            _set_decoration(chip)
            chip.hide()
            summary_layout.addWidget(chip, 1)
            self._reward_summary_chips.append(chip)
        self._reward_summary_row.hide()
        reveal.addWidget(self._reward_summary_row)

        self._reward_secondary = QLabel("", self._reward_reveal)
        self._reward_secondary.setProperty("hudMuted", True)
        apply_tabular_numerals(self._reward_secondary)
        self._reward_secondary.setWordWrap(True)
        _set_decoration(self._reward_secondary)
        self._reward_secondary.hide()
        reveal.addWidget(self._reward_secondary)

        reward_more_row = QHBoxLayout()
        reward_more_row.addStretch(1)
        self._reward_more = QToolButton(self._reward_reveal)
        self._reward_more.setObjectName("reviewerHudRewardMore")
        self._reward_more.setProperty("semanticId", "reviewer.hud.reward-more")
        self._reward_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reward_more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reward_more.setMinimumHeight(32)
        apply_tabular_numerals(self._reward_more)
        self._reward_more.clicked.connect(self._open_current_reward)
        self._reward_more.hide()
        reward_more_row.addWidget(
            self._reward_more,
            0,
            Qt.AlignmentFlag.AlignRight,
        )
        reveal.addLayout(reward_more_row)
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
        self._session_history_chevron = QLabel("›", self._session_footer)
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
        metrics = QHBoxLayout()
        metrics.setSpacing(5)
        self._session_growth = QLabel("", self._session_footer)
        self._session_growth.setProperty("hudGrowth", True)
        apply_tabular_numerals(self._session_growth)
        _set_decoration(self._session_growth)
        metrics.addWidget(self._session_growth)
        self._session_growth_separator = QLabel("·", self._session_footer)
        self._session_growth_separator.setProperty("hudMuted", True)
        _set_decoration(self._session_growth_separator)
        metrics.addWidget(self._session_growth_separator)
        self._session_coins = QLabel("", self._session_footer)
        self._session_coins.setProperty("hudCoin", True)
        apply_tabular_numerals(self._session_coins)
        _set_decoration(self._session_coins)
        metrics.addWidget(self._session_coins)
        self._session_find_separator = QLabel("·", self._session_footer)
        self._session_find_separator.setProperty("hudMuted", True)
        _set_decoration(self._session_find_separator)
        metrics.addWidget(self._session_find_separator)
        self._session_finds = QLabel("", self._session_footer)
        apply_tabular_numerals(self._session_finds)
        _set_decoration(self._session_finds)
        metrics.addWidget(self._session_finds)
        metrics.addStretch(1)
        footer.addLayout(metrics)
        self._session_footer.hide()
        surface.addWidget(self._session_footer)
        self._reward_dock.hide()
        expanded_layout.addWidget(self._reward_dock)

    def _build_collapsed(self) -> None:
        self._collapsed_tab = _ClickableFrame(self, self._expand_from_tab)
        self._collapsed_tab.setObjectName("reviewerHudCollapsedTab")
        self._collapsed_tab.setProperty("semanticId", "reviewer.hud.collapsed-tab")
        self._collapsed_tab.setAccessibleName("Expand Anki Garden review panel")
        layout = QVBoxLayout(self._collapsed_tab)
        layout.setContentsMargins(7, 8, 7, 8)
        layout.setSpacing(4)
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
        self._collapsed_badge = QLabel("", self._collapsed_tab)
        self._collapsed_badge.setProperty("hudCoin", True)
        apply_tabular_numerals(self._collapsed_badge)
        self._collapsed_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_badge.hide()
        _set_decoration(self._collapsed_badge)
        layout.addWidget(self._collapsed_badge)

    def _open_garden(self) -> None:
        _call(self._on_open_garden)

    def _open_plant(self) -> None:
        plant_id = self._projection.nurture.plant_id if self._projection else ""
        if plant_id:
            _call(self._on_open_plant, plant_id)
        else:
            _call(self._on_open_garden)

    def _open_current_reward(self) -> None:
        if self._current_reward is None:
            return
        self._reward_details_expanded = not self._reward_details_expanded
        self._reward_reveal.setProperty(
            "rewardDetailsExpanded",
            self._reward_details_expanded,
        )
        self._sync_current_reward_secondary()
        if self._reward_details_expanded:
            self._reward_timer.stop()
        else:
            self._reward_timer.start(_REVEAL_HOLD_MS)
        _call(self._on_open_reward, self._current_reward)
        self.reposition()

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
        if self._collapsed:
            if self._current_reward is not None:
                self._reward_queue.appendleft(self._current_reward)
                self._current_reward = None
                self._reward_timer.stop()
            self._reward_reveal.hide()
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
            "chevron-left" if projection.dock == "left" else "chevron-right",
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
        self._coin_balance.setAccessibleName(f"{exact} Garden Coins")
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
            start = max(
                0,
                min(99, int(getattr(previous, "progress_percent", 99) if previous else 99)),
            )
            self._today_progress.setValue(start)
            self._today_progress.setProperty("displayedProgressPercent", start)
            animation = QVariantAnimation(self)
            animation.setStartValue(start)
            animation.setEndValue(100)
            animation.setDuration(_PROGRESS_FILL_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)

            def set_progress(value: Any) -> None:
                if self._today_animation is not animation:
                    return
                displayed = max(0, min(100, int(value)))
                self._today_progress.setValue(displayed)
                self._today_progress.setProperty(
                    "displayedProgressPercent", displayed
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
        self._today_card.setProperty("completionStatus", str(today.status))
        self._today_card.setProperty("globalScope", True)
        self._today_check.setVisible(complete)
        self._today_heading.set_full_text(today.heading)
        self._today_value.setText(today.primary)
        self._today_value.setProperty("hudCoin", complete)
        _repolish(self._today_value)
        detail = str(today.secondary[0]) if today.secondary else ""
        self._today_detail.setText(detail)
        self._today_detail.setVisible(bool(detail))
        self._today_progress.setVisible(not complete and today.progress_maximum > 0)
        displayed = 100 if complete else min(99, int(today.progress_percent))
        self._today_progress.setValue(displayed)
        self._today_progress.setProperty("displayedProgressPercent", displayed)
        self._today_progress.setProperty("progressValue", int(today.progress_value))
        self._today_progress.setProperty("progressMaximum", int(today.progress_maximum))

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
        if stage_boundary:
            previous_stage = tuple(
                marker
                for marker in (25, 50, 75, 100)
                if marker >= int(previous.next_checkpoint_percent)
            )
            if nurture.fully_grown or final_progress >= previous_progress:
                return previous_stage
            next_stage = tuple(
                marker
                for marker in (25, 50, 75, 100)
                if marker <= final_progress
            )
            return (*previous_stage, *next_stage)
        return tuple(
            marker
            for marker in (25, 50, 75, 100)
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
        self._plant_card.setProperty("activePlantId", nurture.plant_id)
        self._plant_card.setProperty("environmentTone", nurture.environment_tone)
        self._plant_card.setProperty("fullyGrown", nurture.fully_grown)
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
        self._percent.setText(f"{nurture.progress_percent}%")
        self._percent.setVisible(normal)
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
            f"+{format_quantity(nurture.next_checkpoint_reward_coins, 'coin')}"
            if nurture.next_checkpoint_reward_coins
            else ""
        )
        self._checkpoint_reward_row.setVisible(bool(nurture.next_checkpoint_reward_coins))
        if str(self._next_answer.property("resultState") or "") != "applied":
            self._next_answer_label.setText("Next answer")
            self._next_answer_value.setText(nurture.next_answer_value)
            self._next_answer.setVisible(bool(nurture.next_answer_value))
        message = "\n".join(
            value
            for value in (
                str(nurture.empty_message or ""),
                str(nurture.stored_growth_line or ""),
                "Choose a plant" if not nurture.has_target else "",
            )
            if value
        )
        self._plant_message.setText(message)
        self._plant_message.setVisible(bool(message))
        self._select_plant.hide()
        self._sync_effects(nurture)
        if self._full_bloom_bundle is not None:
            self._apply_full_bloom_override(self._full_bloom_bundle)
        elif self._stage_change_bundle is not None:
            self._apply_stage_change_override(self._stage_change_bundle)
        elif self._settled_full_bloom_bundle is not None:
            self._apply_full_bloom_override(
                self._settled_full_bloom_bundle,
                settled=True,
            )

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
        self._plant_art.setPixmap(pixmap)
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

    def _sync_effects(self, nurture: Any) -> None:
        self._all_effects = tuple(nurture.effect_chips)
        visible = tuple(nurture.visible_effect_chips)
        for index, label in enumerate(self._effect_labels):
            text = visible[index] if index < len(visible) else ""
            label.set_full_text(text)
            identity = text.split(" ", 1)[0].lower() if text else ""
            icon_name = identity if identity in {"fertilizer", "booster", "streak"} else "growth"
            self._effect_icons[index].setPixmap(
                self._icon_pixmap(icon_name, 13, GARDEN_THEME["reviewer_hud_growth"])
            )
            self._effect_chips[index].setVisible(bool(text))
        overflow = int(nurture.effect_overflow_count)
        self._effects_overflow.setText(_effect_overflow_label(overflow))
        self._effects_overflow.setProperty("overflowEffectCount", overflow)
        self._effects_overflow.setToolTip("\n".join(self._all_effects[2:]))
        self._effects_overflow.setVisible(overflow > 0)
        self._effects.setVisible(bool(visible or overflow))
        if overflow <= 0:
            self._effect_details.hide()

    def _toggle_effect_details(self) -> None:
        details = tuple(getattr(self, "_all_effects", ()) or ())[2:]
        if not details:
            return
        expanded = not self._effect_details.isVisible()
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
            "Growth applied",
            f"{format_growth_units(units, signed=True)} growth",
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
            "Next answer",
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
        self._stage.set_full_text("Full Bloom")
        self._stage.setProperty("fullBloomAccent", True)
        _repolish(self._stage)
        self._stage.show()
        self._percent.hide()
        self._checkpoint_track.hide()
        self._checkpoint_distance_row.hide()
        self._checkpoint_reward_row.hide()
        self._next_answer.hide()
        self._effects.hide()
        self._effect_details.hide()
        self._plant_message.setText(
            "Future growth will be shared or stored until you select another plant."
        )
        self._plant_message.show()
        self._select_plant.setVisible(bool(settled))
        self._collapsed_ring.set_progress(100)
        self._art_region.setFixedHeight(146)
        self._plant_art.setFixedSize(136, 136)
        pixmap = self._reward_full_pixmap
        try:
            if pixmap is not None and not pixmap.isNull():
                self._plant_art.setPixmap(pixmap.scaled(
                    136,
                    136,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
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

    def _set_session_metric_values(
        self,
        values: tuple[int, int, int],
    ) -> None:
        normalized = tuple(_integer(value) for value in values)
        for index, widget in enumerate(self._session_metric_widgets()):
            widget.setText(_session_metric_text(index, normalized[index]))
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

    def _sync_reward_scroll_height(self) -> None:
        natural = 0
        if not self._reward_reveal.isHidden():
            natural += max(
                self._reward_reveal.minimumHeight(),
                self._reward_reveal.sizeHint().height(),
            )
        if not self._reward_history_panel.isHidden():
            natural += max(1, self._reward_history_panel.sizeHint().height())
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
            if _bundle_priority(bundle) < _bundle_priority(self._current_reward):
                self._reward_queue.appendleft(self._current_reward)
                self._show_reward(bundle)
            else:
                self._reward_queue.append(bundle)
            return
        self._show_reward(bundle)

    def _show_reward(self, bundle: Any, *, expanded: bool = False) -> None:
        self._current_reward = bundle
        self._reward_details_expanded = bool(expanded)
        self._reward_reveal.setProperty("rewardDetailsExpanded", bool(expanded))
        self._reward_eyebrow.setText(_reward_eyebrow(bundle))
        self._reward_title.set_full_text(_reward_hero_title(bundle))
        self._reward_subtitle.set_full_text(_reward_hero_subtitle(bundle))
        rarity = _hero_rarity(bundle)
        self._reward_rarity.setText(rarity.title())
        self._reward_rarity.setProperty("rarityTone", rarity.lower())
        _repolish(self._reward_rarity)
        self._reward_rarity.setVisible(bool(rarity))
        self._reward_reveal.setProperty("rewardRarity", rarity.lower())
        self._reward_reveal.setProperty("rewardBundleId", _bundle_id(bundle))
        growth_units, coins = _hero_amounts(bundle)
        self._reward_growth.setText(
            f"{format_growth_units(growth_units, signed=True)} growth"
            if growth_units
            else ""
        )
        self._reward_growth.setVisible(bool(growth_units))
        self._reward_coins.setText(f"+{coins:,} coins" if coins else "")
        self._reward_coins.setVisible(bool(coins))
        inventory_labels = _hero_inventory_labels(bundle)
        self._reward_inventory.setText(" · ".join(inventory_labels))
        self._reward_inventory.setVisible(bool(inventory_labels))
        self._sync_current_reward_secondary()
        self._set_reward_art(_bundle_hero(bundle), _hero_kind(bundle))
        self._reward_reveal.show()
        self.setProperty("hudRewardVisible", True)
        self._sync_reward_dock_visibility()
        self._fade_reward_in()
        kind = _hero_kind(bundle)
        if kind in {"full_bloom", "full-bloom", "stage_change", "stage-change"}:
            self.celebrate_milestone(kind, bundle)
        hold_ms = _integer(_value(bundle, "hold_ms", default=_REVEAL_HOLD_MS))
        if expanded:
            self._reward_timer.stop()
        else:
            self._reward_timer.start(max(2_500, min(3_500, hold_ms or _REVEAL_HOLD_MS)))
        self.reposition()

    def _sync_current_reward_secondary(self) -> None:
        bundle = self._current_reward
        if bundle is None:
            for chip in self._reward_summary_chips:
                chip.set_full_text("")
                chip.hide()
            self._reward_summary_row.hide()
            self._reward_secondary.clear()
            self._reward_secondary.hide()
            self._reward_more.hide()
            return
        compact = _compact_projection(bundle)
        visible_summaries = _compact_visible_summaries(bundle)
        hidden_summaries = _compact_hidden_summaries(bundle)
        if self._reward_details_expanded:
            labels = [_secondary_label(item) for item in _all_secondary_items(bundle)]
            for chip in self._reward_summary_chips:
                chip.hide()
            self._reward_summary_row.hide()
            self._reward_secondary.setText("\n".join(labels))
            self._reward_secondary.setVisible(bool(labels))
            more_text = "Show less" if labels else ""
        else:
            labels = [
                _compact_summary_label(summary) or _secondary_label(summary)
                for summary in visible_summaries[:2]
            ]
            for index, chip in enumerate(self._reward_summary_chips):
                text = labels[index] if index < len(labels) else ""
                chip.set_full_text(text)
                chip.setVisible(bool(text))
            self._reward_summary_row.setVisible(bool(labels))
            self._reward_secondary.clear()
            self._reward_secondary.hide()
            more_text = str(
                _value(compact, "more_label", default="")
                or _value(bundle, "more_label", default="")
                or ""
            )
        self._reward_more.setText(more_text)
        self._reward_more.setMinimumWidth(
            self._reward_more.fontMetrics().horizontalAdvance(more_text) + 28
            if more_text
            else 0
        )
        self._reward_more.setVisible(bool(more_text))
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
            320
            if self._reward_details_expanded
            else _COMPACT_REWARD_MAX_HEIGHT
        )
        self._reward_reveal.setMinimumHeight(
            320 if self._reward_details_expanded else 128
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
        if hasattr(resolved, "isNull"):
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
        if not pixmap.isNull():
            self._reward_full_pixmap = QPixmap(pixmap)
            pixmap = pixmap.scaled(
                56,
                56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            icon_name = "stage" if "stage" in kind or "bloom" in kind else "growth"
            pixmap = self._icon_pixmap(icon_name, 48, GARDEN_THEME["reviewer_hud_growth"])
            self._reward_full_pixmap = QPixmap(pixmap)
        self._reward_art.setPixmap(pixmap)

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

    def clear_reward(self) -> None:
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
        self._reward_reveal.setProperty("rewardDetailsExpanded", False)
        self._reward_reveal.setMinimumHeight(128)
        self._reward_reveal.setMaximumHeight(_COMPACT_REWARD_MAX_HEIGHT)
        self._reward_more.hide()
        self._reward_reveal.hide()
        self.setProperty("hudRewardVisible", False)
        self._sync_reward_dock_visibility()
        self.reposition()

    def _compact_current_reward(self) -> None:
        self.clear_reward()
        if not self._collapsed and self._reward_queue:
            self._show_reward(self._reward_queue.popleft())

    def _history_line(self, bundle: Any) -> str:
        growth_units, coins = _hero_amounts(bundle)
        amounts: list[str] = []
        if growth_units:
            amounts.append(f"{format_growth_units(growth_units, signed=True)} growth")
        if coins:
            amounts.append(f"+{coins:,} coins")
        amounts.extend(_hero_inventory_labels(bundle))
        return " · ".join((_hero_title(bundle), *amounts))

    def _sync_history_rows(self) -> None:
        all_recent = tuple(reversed(self._reward_history))
        page_size = len(self._history_labels)
        page_count = max(1, (len(all_recent) + page_size - 1) // page_size)
        self._reward_history_page %= page_count
        start = self._reward_history_page * page_size
        recent = all_recent[start : start + page_size]
        self._visible_history_bundles = recent
        for index, label in enumerate(self._history_labels):
            text = self._history_line(recent[index]) if index < len(recent) else ""
            label.set_full_text(text)
            self._history_rows[index].setVisible(bool(text))
        self._history_pager.setVisible(len(all_recent) > page_size)
        self._history_pager.setText(
            "Latest rewards ↑"
            if self._reward_history_page + 1 >= page_count
            else "Earlier rewards ›"
        )
        self._history_pager.setProperty("historyPage", self._reward_history_page)
        self._history_pager.setProperty("historyPageCount", page_count)
        available = bool(self._reward_history)
        self._session_footer.setProperty("historyAvailable", available)
        history_expanded = bool(
            self._session_footer.property("historyExpanded")
        )
        self._session_history_chevron.setText("⌄" if history_expanded else "›")
        self._session_history_chevron.setVisible(available)
        self._session_footer.setCursor(
            Qt.CursorShape.PointingHandCursor
            if available
            else Qt.CursorShape.ArrowCursor
        )
        _repolish(self._session_footer)

    def _advance_reward_history_page(self) -> None:
        if len(self._reward_history) <= len(self._history_labels):
            return
        page_size = len(self._history_labels)
        page_count = max(1, (len(self._reward_history) + page_size - 1) // page_size)
        self._reward_history_page = (self._reward_history_page + 1) % page_count
        self._sync_history_rows()
        self._sync_reward_dock_visibility()
        self.reposition()

    def _reopen_history_reward(self, index: int) -> None:
        recent = tuple(getattr(self, "_visible_history_bundles", ()) or ())
        if not (0 <= int(index) < len(recent)):
            return
        bundle = recent[int(index)]
        self._reward_history_panel.hide()
        if self._current_reward is not None and self._current_reward is not bundle:
            self._reward_queue.appendleft(self._current_reward)
        self._show_reward(bundle, expanded=True)

    def _toggle_reward_history(self) -> None:
        if not self._reward_history:
            return
        expanded = self._reward_history_panel.isHidden()
        self._reward_history_panel.setVisible(expanded)
        self._session_footer.setProperty("historyExpanded", expanded)
        self._session_history_chevron.setText("⌄" if expanded else "›")
        if expanded:
            self._unseen_major = 0
            self._sync_unseen_badge()
        _call(self._on_expand_rewards, expanded)
        self._sync_reward_dock_visibility()
        self.reposition()

    def _sync_unseen_badge(self) -> None:
        count = max(0, self._unseen_major)
        self._collapsed_badge.setText("9+" if count > 9 else str(count))
        self._collapsed_badge.setVisible(count > 0)
        self.setProperty("hudUnseenMajorRewards", count)

    def reposition(
        self,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> tuple[int, int, int, int]:
        parent = self.parentWidget()
        if parent is None:
            return (self.x(), self.y(), self.width(), self.height())
        try:
            width = max(1, int(parent.width() if viewport_width is None else viewport_width))
            height = max(1, int(parent.height() if viewport_height is None else viewport_height))
            if self._collapsed:
                content_height = None
            else:
                body_layout = self._body_contents.layout()
                reward_layout = self._reward_dock.layout()
                body_layout.activate()
                reward_layout.activate()
                natural_width = max(1, reviewer_hud_width(width) - 2)

                def natural_height(widget: Any, layout: Any) -> int:
                    size_hint = max(1, int(widget.sizeHint().height()))
                    try:
                        width_height = int(layout.heightForWidth(natural_width))
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        width_height = -1
                    return max(size_hint, width_height if width_height >= 0 else 0)

                # Word-wrapped plant and reward labels can grow after their
                # text changes but before Qt updates the widget-level size
                # hint. Ask each layout for its height at the final HUD width
                # so the shell expands instead of needlessly scrolling at the
                # canonical reviewer size.
                body_height = natural_height(self._body_contents, body_layout)
                reward_height = (
                    natural_height(self._reward_dock, reward_layout)
                    if not self._reward_dock.isHidden()
                    else 0
                )
                # The styled shell contributes a one-pixel border on both
                # vertical edges. Include both the independently anchored
                # reward dock and the 44px header so the dock never steals
                # height from the daily/plant body at its natural size.
                content_height = 46 + body_height + reward_height
                self.setProperty("hudBodyNaturalHeight", body_height)
                self.setProperty("hudRewardDockNaturalHeight", reward_height)
            geometry = reviewer_hud_geometry(
                width,
                height,
                collapsed=self._collapsed,
                dock=self._dock,
                content_height=content_height,
            )
            self.setFixedSize(geometry[2], geometry[3])
            self.move(geometry[0], geometry[1])
            self.setProperty("hudContentHeight", int(content_height or geometry[3]))
            self.setProperty("reviewerViewportWidth", width)
            self.setProperty("reviewerViewportHeight", height)
            self.raise_()
            return geometry
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return (self.x(), self.y(), self.width(), self.height())

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self._viewport_parent:
            try:
                if event.type() in {QEvent.Type.Resize, QEvent.Type.Show}:
                    QTimer.singleShot(0, self.reposition)
            except Exception:
                pass
        return False

    def dispose(self) -> None:
        self._disposed = True
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
