"""Native, nonmodal receipt for Garden rewards introduced by Anki sync.

The reward engine owns every value in :class:`SyncRewardSummary`.  This module
only renders that already-committed presentation model.  It deliberately uses
a child ``QFrame`` instead of a dialog, so the Deck Browser or Overview behind
the card remains usable.
"""

from __future__ import annotations

from ..presentation import plant_stage_title, plant_stage_event

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..growth import stage_presentation
from ..models.sync_reward import SyncPlantResult, SyncRewardSummary
from ..reward_presentation import project_growth_allocations
from .formatters import (
    format_garden_coins,
    format_stage_progress,
    format_status_label,
)
from .garden_asset_thumbnail import GardenAssetThumbnail
from .icons import garden_icon, garden_icon_pixmap
from .session_summary import format_growth_units, plant_growth_journey
from .reward_rarity import apply_reward_treatment, reward_treatment
from .reward_receipt import fit_receipt_chrome, receipt_metrics_layout, build_receipt_shell, receipt_button, receipt_metric, receipt_event_row, receipt_style, receipt_body_height
from .session_summary_card import session_summary_palette
from .theme import apply_tabular_numerals


SYNC_REWARD_PREFERRED_WIDTH = 400
SYNC_REWARD_MIN_WIDTH = 336
SYNC_REWARD_MAX_WIDTH = 400
SYNC_REWARD_MAX_HEIGHT = 520
SYNC_REWARD_VIEWPORT_MARGIN = 24
SYNC_REWARD_TOP_OFFSET = 24
SYNC_REWARD_MIN_HEIGHT = 210
SYNC_REWARD_BODY_SPACING = 8
SYNC_REWARD_METRIC_ANIMATION_MS = 360
SYNC_REWARD_FULL_BLOOM_PULSE_MS = 520


def sync_reward_summary_geometry(
    viewport_width: int,
    viewport_height: int,
    content_height: int,
    *,
    preferred_width: int = SYNC_REWARD_PREFERRED_WIDTH,
) -> tuple[int, int, int, int]:
    """Return safe upper-right, viewport-bounded ``(x, y, width, height)``."""

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))
    available_width = max(1, viewport_width - (SYNC_REWARD_VIEWPORT_MARGIN * 2))
    desired_width = max(
        SYNC_REWARD_MIN_WIDTH,
        min(SYNC_REWARD_MAX_WIDTH, int(preferred_width)),
    )
    width = min(desired_width, available_width)
    height_limit = max(
        1,
        min(
            SYNC_REWARD_MAX_HEIGHT,
            viewport_height - (SYNC_REWARD_VIEWPORT_MARGIN * 2),
        ),
    )
    minimum_height = min(SYNC_REWARD_MIN_HEIGHT, height_limit)
    height = max(
        minimum_height,
        min(max(1, int(content_height)), height_limit),
    )
    x = max(0, viewport_width - width - SYNC_REWARD_VIEWPORT_MARGIN)
    y = min(SYNC_REWARD_TOP_OFFSET, max(0, viewport_height - height))
    return x, y, width, height


def _quantity(row: Mapping[str, Any]) -> int:
    try:
        return max(1, int(row.get("quantity", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _rarity_rank(value: Any) -> int:
    return reward_treatment(value).rank


def _find_rank(row: Mapping[str, Any]) -> tuple[int, int, str]:
    reward_id = str(row.get("reward_id", "") or "").casefold()
    reward_type = str(row.get("reward_type", "") or "").casefold()
    significance = 0
    if "booster" in reward_id:
        significance = 60
    elif "grand" in reward_id:
        significance = 50
    elif "standard" in reward_id:
        significance = 40
    elif "small" in reward_id:
        significance = 30
    elif reward_type in {"coins", "garden_coins", "currency"}:
        significance = 20
    return (-_rarity_rank(row.get("rarity")), -significance, reward_id)


@dataclass(frozen=True)
class SyncRewardVisibilityPlan:
    plant_growth: tuple[dict[str, Any], ...]
    environment_discoveries: tuple[dict[str, Any], ...]
    finds: tuple[dict[str, Any], ...]
    progression_events: tuple[dict[str, Any], ...]
    hidden_count: int


def _visible_with_pinned(
    rows: tuple[dict[str, Any], ...],
    limit: int,
    *,
    pinned: Callable[[Mapping[str, Any]], bool] | None = None,
) -> tuple[dict[str, Any], ...]:
    if len(rows) <= limit:
        return rows
    chosen: list[dict[str, Any]] = list(rows[:limit])
    if pinned is not None:
        for row in rows[limit:]:
            if pinned(row) and row not in chosen:
                chosen.append(row)
    return tuple(chosen)


def sync_reward_visibility_plan(
    summary: SyncRewardSummary,
    *,
    expanded: bool = False,
) -> SyncRewardVisibilityPlan:
    """Keep all committed rewards and plant journeys in the scrolling feed."""

    plants = tuple(result.to_dict() for result in summary.grouped_plant_results)
    environments = tuple(sorted(
        (dict(row) for row in summary.environment_discoveries),
        key=lambda row: (-_rarity_rank(row.get("rarity")), str(row.get("display_name", ""))),
    ))
    finds = tuple(sorted((dict(row) for row in summary.finds), key=_find_rank))
    events: tuple[dict[str, Any], ...] = ()
    if expanded:
        return SyncRewardVisibilityPlan(plants, environments, finds, events, 0)

    visible_plants = plants
    visible_environments = environments
    visible_finds = finds
    visible_events: tuple[dict[str, Any], ...] = ()
    hidden = (
        len(plants) - len(visible_plants)
        + len(environments) - len(visible_environments)
        + len(finds) - len(visible_finds)
        + len(events) - len(visible_events)
    )
    return SyncRewardVisibilityPlan(
        visible_plants,
        visible_environments,
        visible_finds,
        visible_events,
        max(0, hidden),
    )


def sync_reward_metric_plan(
    summary: SyncRewardSummary,
) -> tuple[tuple[str, str, str], ...]:
    """Return required totals plus independently labelled reward metrics.

    ``finds`` and ``environment_discoveries`` are separate committed streams.
    Keeping their projections separate prevents a Garden discovery from being
    presented as a Garden Find without changing either stream's persisted
    reward or event identity.
    """

    metrics: list[tuple[str, str, str]] = [
        (
            f"{summary.eligible_answer_count:,}",
            "card" if summary.eligible_answer_count == 1 else "cards",
            "sync_review_cards",
        ),
    ]
    discoveries = sum(_quantity(row) for row in summary.finds) + len(summary.environment_discoveries)
    metrics.extend((
        (f"+{summary.garden_coin_delta:,}" if summary.garden_coin_delta else "0", "Coins", "garden_coin"),
        (format_growth_units(summary.growth_total_units, signed=bool(summary.growth_total_units)), "Growth", "growth_resource"),
        (f"{discoveries:,}", "Discoveries", "garden_discovery"),
    ))
    return tuple(metrics)


def sync_reward_subtitle(summary: SyncRewardSummary) -> str:
    """Describe the committed sync quantity in the same unit shown elsewhere."""

    count = max(0, int(summary.eligible_answer_count or 0))
    noun = "review" if count == 1 else "reviews"
    return f"From {count:,} synced {noun}"


@dataclass(frozen=True)
class SyncRewardMetricMotion:
    """One numeric label transition expressed without a Qt dependency."""

    label: str
    start_scaled: int
    end_scaled: int
    decimal_places: int
    show_plus: bool
    final_text: str


@dataclass(frozen=True)
class SyncRewardPlantProgressMotion:
    """The previously rendered point for one changed plant stage bar."""

    plant_key: str
    start_value: int
    start_stage: str


@dataclass(frozen=True)
class SyncRewardMotionPlan:
    """Animations permitted for one initial mount or model replacement.

    An empty plan is intentionally used for disclosure-only body rebuilds.
    Keeping the diff calculation pure also leaves this module importable in
    source-only test and packaging processes where Anki's Qt shim is absent.
    """

    metrics: tuple[SyncRewardMetricMotion, ...] = ()
    plant_progress: tuple[SyncRewardPlantProgressMotion, ...] = ()
    full_bloom_event_keys: frozenset[str] = frozenset()


def _parse_metric_number(text: str) -> tuple[int, int, bool] | None:
    """Return ``(scaled value, decimal places, explicit plus)`` for a metric."""

    token = str(text or "").strip()
    if not token:
        return None
    show_plus = token.startswith("+")
    negative = token.startswith("-")
    if show_plus or negative:
        token = token[1:]
    token = token.replace(",", "")
    whole, separator, fraction = token.partition(".")
    if not whole.isdigit() or (separator and (not fraction or not fraction.isdigit())):
        return None
    decimal_places = len(fraction) if separator else 0
    scale = 10 ** decimal_places
    scaled = (int(whole) * scale) + (int(fraction) if fraction else 0)
    if negative:
        scaled = -scaled
    return scaled, decimal_places, show_plus


def _format_metric_number(
    scaled_value: int,
    decimal_places: int,
    show_plus: bool,
) -> str:
    """Format an animated metric without losing grouping, sign, or precision."""

    value = int(scaled_value)
    places = max(0, int(decimal_places))
    scale = 10 ** places
    magnitude = abs(value)
    whole = magnitude // scale
    fraction = magnitude % scale
    text = f"{whole:,}"
    if places:
        text = f"{text}.{fraction:0{places}d}"
    if value < 0:
        return f"-{text}"
    if show_plus:
        return f"+{text}"
    return text


def _rescale_metric_value(value: int, from_places: int, to_places: int) -> int:
    if from_places == to_places:
        return int(value)
    if from_places < to_places:
        return int(value) * (10 ** (to_places - from_places))
    divisor = 10 ** (from_places - to_places)
    magnitude = (abs(int(value)) + (divisor // 2)) // divisor
    return -magnitude if value < 0 else magnitude


def _plant_motion_key(row: Mapping[str, Any]) -> str:
    return str(
        row.get("plant_id", "")
        or row.get("plant_name", "")
        or row.get("plant_image", "")
        or "plant"
    )


def _plant_progress_target(row: Mapping[str, Any]) -> tuple[int, str]:
    stage = str(row.get("stage_after", "") or "")
    fully_grown = bool(row.get("fully_grown", False)) or stage.casefold() in {
        "rare",
        "full_bloom",
        "full bloom",
    }
    progress = max(
        0,
        min(100, int(row.get("stage_progress_after", 0) or 0)),
    )
    return (100 if fully_grown else progress), stage


def _plant_progress_copy(row: Mapping[str, Any]) -> str:
    """Format the committed stage-relative progress as canonical Growth."""

    current = stage_presentation(row.get("stage_after"))
    destination = stage_presentation(row.get("next_stage"))
    if (
        current is None
        or destination is None
        or destination.display_ordinal <= current.display_ordinal
    ):
        return ""
    goal = destination.threshold - current.threshold
    if goal <= 0:
        return ""
    percent = max(
        0,
        min(100, int(row.get("stage_progress_after", 0) or 0)),
    )
    total_units = row.get("growth_after_units")
    if total_units is None:
        return f"{percent}% to {destination.display_name}"
    relative_units = max(0, min(goal * 100, int(total_units) - current.threshold * 100))
    return f"{format_growth_units(relative_units)} / {goal:,} Growth to {destination.display_name}"



def _checkpoint_display_text(checkpoint: Mapping[str, Any], species: str) -> str:
    """Normalize committed checkpoint fields into grammatical visible copy."""

    try:
        percent = max(0, min(100, int(checkpoint.get("percent", 0) or 0)))
    except (TypeError, ValueError):
        percent = 0
    return plant_stage_event(species, checkpoint.get("stage_name", ""), checkpoint_percent=percent)


def _progress_event_key(row: Mapping[str, Any]) -> str:
    event_id = str(row.get("event_id", "") or "").strip()
    if event_id:
        return event_id
    return "|".join((
        str(row.get("plant_id", "") or ""),
        str(row.get("event_type", "") or ""),
        str(row.get("display_text", "") or ""),
    ))


def _full_bloom_key(row: Mapping[str, Any]) -> str:
    return str(
        row.get("stage_event_id", "")
        or f"plant:{row.get('plant_id', '')}:full_bloom"
    )


def sync_reward_motion_plan(
    summary: SyncRewardSummary,
    *,
    previous: SyncRewardSummary | None = None,
) -> SyncRewardMotionPlan:
    """Plan initial motion or only values changed by ``update_model``."""

    if not isinstance(summary, SyncRewardSummary):
        raise TypeError("summary must be a SyncRewardSummary")

    previous_metrics = {
        label: value
        for value, label, _icon_name in (
            sync_reward_metric_plan(previous) if previous is not None else ()
        )
    }
    metric_motion: list[SyncRewardMetricMotion] = []
    for final_text, label, _icon_name in sync_reward_metric_plan(summary):
        target = _parse_metric_number(final_text)
        if target is None:
            continue
        end_scaled, decimal_places, show_plus = target
        previous_text = previous_metrics.get(label)
        if previous is not None and previous_text == final_text:
            continue
        start_scaled = 0
        if previous_text is not None:
            old_value = _parse_metric_number(previous_text)
            if old_value is not None:
                start_scaled = _rescale_metric_value(
                    old_value[0],
                    old_value[1],
                    decimal_places,
                )
        if start_scaled == end_scaled:
            continue
        metric_motion.append(SyncRewardMetricMotion(
            label=label,
            start_scaled=start_scaled,
            end_scaled=end_scaled,
            decimal_places=decimal_places,
            show_plus=show_plus,
            final_text=final_text,
        ))

    previous_plants = {
        _plant_motion_key(row): dict(row)
        for row in (
            (result.to_dict() for result in previous.grouped_plant_results)
            if previous is not None
            else ()
        )
    }
    plant_motion: list[SyncRewardPlantProgressMotion] = []
    for result in summary.grouped_plant_results:
        row = result.to_dict()
        key = _plant_motion_key(row)
        target_value, target_stage = _plant_progress_target(row)
        old_row = previous_plants.get(key)
        if old_row is None:
            start_value = max(
                0,
                min(100, int(row.get("stage_progress_before", target_value) or 0)),
            )
            start_stage = str(row.get("stage_before", "") or "")
        else:
            start_value, start_stage = _plant_progress_target(old_row)
        if start_value == target_value and start_stage == target_stage:
            continue
        plant_motion.append(SyncRewardPlantProgressMotion(
            plant_key=key,
            start_value=start_value,
            start_stage=start_stage,
        ))

    previous_blooms = {
        _full_bloom_key(row)
        for row in (
            (result.to_dict() for result in previous.grouped_plant_results)
            if previous is not None
            else ()
        )
        if bool(row.get("full_bloom", False))
    }
    bloom_keys = frozenset(
        _full_bloom_key(row)
        for row in (result.to_dict() for result in summary.grouped_plant_results)
        if bool(row.get("full_bloom", False))
        if _full_bloom_key(row) not in previous_blooms
    )
    return SyncRewardMotionPlan(
        metrics=tuple(metric_motion),
        plant_progress=tuple(plant_motion),
        full_bloom_event_keys=bloom_keys,
    )


def _effect_lines(
    summary: SyncRewardSummary,
) -> tuple[tuple[str, str, str, str], ...]:
    lines: list[tuple[str, str, str, str]] = []
    if summary.fertilizer_state_changed and summary.fertilizer_cards_remaining > 0:
        fertilizer_names = {
            "fertilizer_basic": "Basic Fertilizer",
            "fertilizer_quality": "Quality Fertilizer",
            "fertilizer_premium": "Magical Fertilizer",
        }
        fertilizer_reference = " ".join((
            summary.fertilizer_item_id,
            summary.fertilizer_art_asset,
        )).casefold()
        name = next((
            display_name
            for item_id, display_name in fertilizer_names.items()
            if item_id in fertilizer_reference
        ), "Fertilizer")
        lines.append((
            "fertilizer",
            summary.fertilizer_item_id,
            (
                f"{name} active · {summary.fertilizer_cards_remaining:,} "
                f"{'card' if summary.fertilizer_cards_remaining == 1 else 'cards'} remaining"
            ),
            summary.fertilizer_art_asset,
        ))
    if summary.booster_state_changed and summary.booster_cards_remaining > 0:
        noun = "card" if summary.booster_cards_remaining == 1 else "cards"
        lines.append((
            "booster",
            summary.booster_item_id,
            f"Booster Potion active · {summary.booster_cards_remaining:,} {noun} remaining",
            summary.booster_art_asset,
        ))
    return tuple(lines)


try:  # Keep pure projection helpers importable without Anki's Qt runtime.
    from aqt.qt import (
        QEvent,
        QEasingCurve,
        QFrame,
        QPainter,
        QColor,
        QRectF,
        QPen,
        QGraphicsOpacityEffect,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPoint,
        QProgressBar,
        QPropertyAnimation,
        QPushButton,
        QScrollArea,
        QSequentialAnimationGroup,
        QSize,
        QSizePolicy,
        QToolButton,
        QTimer,
        QVariantAnimation,
        QVBoxLayout,
        QWidget,
        Qt,
    )

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - used by source-only test processes.
    QEvent = object  # type: ignore[assignment,misc]
    QEasingCurve = object  # type: ignore[assignment,misc]
    QFrame = object  # type: ignore[assignment,misc]
    QGraphicsOpacityEffect = object  # type: ignore[assignment,misc]
    QGridLayout = object  # type: ignore[assignment,misc]
    QHBoxLayout = object  # type: ignore[assignment,misc]
    QLabel = object  # type: ignore[assignment,misc]
    QPoint = object  # type: ignore[assignment,misc]
    QProgressBar = object  # type: ignore[assignment,misc]
    QPropertyAnimation = object  # type: ignore[assignment,misc]
    QPushButton = object  # type: ignore[assignment,misc]
    QScrollArea = object  # type: ignore[assignment,misc]
    QSequentialAnimationGroup = object  # type: ignore[assignment,misc]
    QSize = object  # type: ignore[assignment,misc]
    QSizePolicy = object  # type: ignore[assignment,misc]
    QToolButton = object  # type: ignore[assignment,misc]
    QTimer = object  # type: ignore[assignment,misc]
    QVariantAnimation = object  # type: ignore[assignment,misc]
    QVBoxLayout = object  # type: ignore[assignment,misc]
    QWidget = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError(
            "SyncRewardSummaryCard requires Anki's Qt runtime"
        ) from _QT_IMPORT_ERROR


def _host_background_lightness(parent: Any) -> int | None:
    try:
        return int(parent.palette().color(parent.backgroundRole()).lightness())
    except Exception:
        return None


class SyncRewardSummaryCard(QFrame):  # type: ignore[misc,valid-type]
    """One focus-safe, presentation-only sync reward receipt."""

    def __init__(
        self,
        parent: Any,
        summary: SyncRewardSummary,
        *,
        on_dismiss: Callable[[], None] | None = None,
        on_open_garden: Callable[[], None] | None = None,
        engine: Any | None = None,
        animations_enabled: bool = True,
    ) -> None:
        _require_qt()
        if parent is None:
            raise ValueError("SyncRewardSummaryCard requires a parent widget")
        if not isinstance(summary, SyncRewardSummary):
            raise TypeError("summary must be a SyncRewardSummary")
        if not summary.meaningful:
            raise ValueError("summary must contain a meaningful committed reward")

        super().__init__(parent)
        self._summary = summary
        self._on_dismiss = on_dismiss
        self._on_open_garden = on_open_garden
        self._engine = engine
        self._animations_enabled = bool(animations_enabled)
        self._expanded = False
        self._dismissed = False
        self._additional_line_visible = summary.additional_answer_count > 0
        self._filtered_parent = parent
        self._palette = session_summary_palette(_host_background_lightness(parent))
        self._entrance_started = False
        self._entrance_animations: list[Any] = []
        self._metric_animations: list[Any] = []
        self._progress_animations: list[Any] = []
        self._full_bloom_animations: list[Any] = []
        self._settled_reposition_pending = False

        self.setObjectName("ankiGardenSyncRewardSummary")
        self.setProperty("semanticId", "sync-rewards.summary")
        self.setProperty("summaryNonmodal", True)
        self.setProperty("summaryCentered", False)
        self.setProperty("summaryDock", "upper-right")
        self.setProperty("summaryFixedHeaderFooter", True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Anki Garden Sync Rewards")
        self.setMinimumWidth(1)
        self.setMaximumWidth(SYNC_REWARD_MAX_WIDTH)

        self._apply_style()
        self._build_shell()
        self._rebuild_body(motion=sync_reward_motion_plan(summary))
        self.reposition()
        try:
            parent.installEventFilter(self)
        except Exception:
            self._filtered_parent = None

    def paintEvent(self, event: Any) -> None:
        # A translucent child needs an explicit rounded fill; inheriting the
        # host palette either paints a square backing or loses the shell.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self._palette["receipt_panel"]))
        painter.setPen(QPen(QColor(self._palette["receipt_border_strong"]), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

    @property
    def model(self) -> SyncRewardSummary:
        return self._summary

    @property
    def expanded(self) -> bool:
        return self._expanded

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(f"""
            QFrame#ankiGardenSyncRewardSummary {{
                background:{p['receipt_panel']};
                border:1px solid {p['receipt_border_strong']};
                border-radius:16px;
            }}
            QLabel {{
                background:transparent;
                border:0;
                color:{p['receipt_text_primary']};
                font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}
            QLabel[syncSection='true'] {{
                color:{p['receipt_text_muted']}; font-size:13px; font-weight:600;
            }}
            QLabel[syncEyebrow='true'] {{font-size:16px;font-weight:600;}}
            QLabel[syncTitle='true'] {{font-size:14px;font-weight:600;}}
            QLabel[syncSubtitle='true'] {{ color:{p['receipt_text_secondary']}; font-size:13px; }}
            QFrame[syncMetric='true'], QFrame[syncPrimaryCard='true'] {{
                background:{p['receipt_primary_surface']};
                border:1px solid {p['receipt_border']};
                border-radius:11px;
            }}
            QFrame[syncRow='true'], QFrame[syncAllocationItem='true'] {{
                background:{p['receipt_secondary_surface']};
                border:0; border-radius:10px;
            }}
            QFrame[syncFullBloom='true'] {{
                background:{p['receipt_primary_surface']};
                border:0; border-left:3px solid {p['receipt_milestone']}; border-radius:0;
            }}
            QLabel[syncMetricValue='true'] {{ font-size:20px; font-weight:700; }}
            QLabel[syncMetricLabel='true'] {{
                color:{p['receipt_text_secondary']}; font-size:11px; font-weight:600;
            }}
            QLabel[syncPrimary='true'] {{ font-size:14px; font-weight:600; }}
            QLabel[syncSecondary='true'] {{ color:{p['receipt_text_secondary']}; font-size:12px; }}
            QLabel[syncMuted='true'] {{ color:{p['receipt_text_muted']}; font-size:12px; }}
            QLabel[syncAdditional='true'] {{
                color:{p['receipt_text_secondary']}; font-size:12px;
                background:{p['receipt_secondary_surface']}; border-radius:8px; padding:6px 8px;
            }}
            QProgressBar {{
                min-height:5px; max-height:5px; border:0; border-radius:3px;
                background:{p['progress_track']}; text-align:center;
            }}
            QProgressBar::chunk {{ background:{p['receipt_primary_mint']}; border-radius:3px; }}
            QScrollArea {{ background:transparent; border:0; }}
            QWidget#ankiGardenSyncRewardBody {{ background:transparent; border:0; }}
            QScrollBar:vertical {{ background:transparent; width:6px; margin:0; }}
            QScrollBar::handle:vertical {{
                background:rgba(189, 205, 197, 86); min-height:24px; border-radius:3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
            QPushButton, QToolButton {{
                min-height:32px; border-radius:9px;
                padding:0 14px; font-size:13px; font-weight:600;
                color:{p['receipt_text_primary']}; background:transparent; border:0;
            }}
            QPushButton:hover, QToolButton:hover {{ background:{p['receipt_hover_surface']}; }}
            QPushButton:pressed, QToolButton:pressed {{ background:{p['receipt_secondary_surface']}; }}
            QPushButton[syncPrimaryAction='true'] {{
                color:{p['action_text']}; background:{p['action_accent']};
            }}
            QPushButton[syncPrimaryAction='true']:hover {{ background:{p['action_hover']}; }}
            QPushButton[syncSecondaryAction='true'] {{
                background:transparent; border:1px solid {p['receipt_border_strong']};
            }}
            QPushButton[syncSecondaryAction='true']:hover {{
                background:{p['receipt_hover_surface']};
            }}
            QToolButton[syncClose='true'] {{
                min-width:32px; max-width:32px; min-height:32px; max-height:32px; padding:0;
            }}
            QFrame[syncFooter='true'] {{
                border:0; border-top:1px solid {p['divider']}; background:transparent;
            }}
        """)

    def _build_shell(self) -> None:
        shell = build_receipt_shell(self, "Rewards after syncing", self._dismiss, self._palette, prefix="ankiGardenSyncReward")
        self._shell, self._header = shell.root, shell.header
        self._close_button, self._eyebrow = shell.close, shell.title
        self._body_scroll, self._footer = shell.scroll, shell.footer
        self._body_scroll.setObjectName("ankiGardenSyncRewardBodyScroll")
        self._body_scroll.setProperty("syncBodyScrollOwner", True)
        self._summary_fixed = QFrame(self)
        self._summary_fixed.setObjectName("ankiGardenSyncPinnedSummary")
        self._summary_fixed_layout = QVBoxLayout(self._summary_fixed)
        self._summary_fixed_layout.setContentsMargins(16, 8, 16, 8)
        self._summary_fixed_layout.setSpacing(10)
        self._shell.insertWidget(1, self._summary_fixed)
        self._title = QLabel("", self._header)
        self._title.hide()
        self._subtitle = QLabel(sync_reward_subtitle(self._summary), self._header)
        self._subtitle.hide()
        self._reassurance = QLabel("", self._footer)
        self._reassurance.hide()
        shell.actions.addStretch(1)
        self._done_button = receipt_button(self._footer, "Close", self._dismiss, primary=False)
        self._open_button = receipt_button(self._footer, "Open garden", self._open_garden, primary=True)
        shell.actions.addWidget(self._done_button)
        shell.actions.addWidget(self._open_button)
        self._footer.setProperty("syncActionHierarchy", ["close:secondary", "open_garden:primary"])
        self.setStyleSheet(self.styleSheet() + receipt_style(self._palette))

    @staticmethod
    def _clear_layout(layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                SyncRewardSummaryCard._clear_layout(child_layout)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _new_body(self) -> QVBoxLayout:
        for collection_name in (
            "_metric_animations",
            "_progress_animations",
            "_full_bloom_animations",
        ):
            animations = list(getattr(self, collection_name, ()))
            setattr(self, collection_name, [])
            for animation in animations:
                try:
                    animation.stop()
                except (AttributeError, RuntimeError):
                    pass
        previous = self._body_scroll.takeWidget()
        if previous is not None:
            previous.deleteLater()
        body = QWidget(self._body_scroll)
        body.setObjectName("ankiGardenSyncRewardBody")
        body.setMinimumWidth(0)
        body.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 8, 16, 8)
        # Each reward remains a distinct card as the shared feed scrolls.
        layout.setSpacing(SYNC_REWARD_BODY_SPACING)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._body_scroll.setWidget(body)
        self._body_widget = body
        return layout

    def _section_heading(self, text: str, parent: Any) -> QLabel:
        label = QLabel(text, parent)
        label.setProperty("syncSection", True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _divider(self, parent: Any) -> QFrame:
        line = QFrame(parent)
        line.setFixedHeight(1)
        line.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        line.setStyleSheet(f"background:{self._palette['divider']};border:0;")
        return line

    def _metric_tile(
        self,
        value: str,
        label: str,
        icon_name: str,
        parent: Any,
        *,
        motion: SyncRewardMetricMotion | None = None,
    ) -> QFrame:
        semantic_icon = {
            "sync_review_cards": "reviews", "standard_find": "find",
            "garden_discovery": "environment-discovery", "garden_coin": "coin",
            "growth_resource": "growth",
        }.get(icon_name, "find")
        metric = receipt_metric(parent, label, value, semantic_icon, self._palette)
        tile, value_label = metric.widget, metric.value
        tile.setProperty("syncMetric", True)
        tile.setProperty("syncMetricKey", icon_name)
        value_label.setProperty("syncMetricValue", True)
        value_label.setProperty("syncMetricFinalValue", value)
        if not self._animations_enabled or motion is None:
            return tile

        animation = QVariantAnimation(self)
        animation.setStartValue(motion.start_scaled)
        animation.setEndValue(motion.end_scaled)
        animation.setDuration(SYNC_REWARD_METRIC_ANIMATION_MS)
        animation.setLoopCount(1)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        value_label.setProperty("syncMetricAnimationStart", motion.start_scaled)
        value_label.setProperty("syncMetricAnimationActive", True)

        def render_metric(raw_value: Any) -> None:
            if animation not in self._metric_animations:
                return
            try:
                current = int(round(float(raw_value)))
                value_label.setText(_format_metric_number(
                    current,
                    motion.decimal_places,
                    motion.show_plus,
                ))
            except (RuntimeError, TypeError, ValueError):
                return

        def finish_metric() -> None:
            try:
                value_label.setText(motion.final_text)
                value_label.setProperty("syncMetricAnimationActive", False)
            except RuntimeError:
                pass
            if animation in self._metric_animations:
                self._metric_animations.remove(animation)

        def start_metric() -> None:
            if self._dismissed or animation not in self._metric_animations:
                return
            try:
                value_label.setText(_format_metric_number(
                    motion.start_scaled,
                    motion.decimal_places,
                    motion.show_plus,
                ))
                animation.start()
            except RuntimeError:
                finish_metric()

        animation.valueChanged.connect(render_metric)
        animation.finished.connect(finish_metric)
        self._metric_animations.append(animation)
        # The final value was installed first for immediate layout/accessibility;
        # the next event-loop turn begins the brief visual count.
        QTimer.singleShot(0, start_metric)
        return tile

    def _resolved_art_path(
        self,
        kind: str,
        identity: str,
        *,
        stage: str = "",
        explicit: str = "",
    ) -> Path | None:
        for raw in (explicit, identity):
            if raw:
                candidate = Path(str(raw))
                if candidate.is_file():
                    return candidate
        resolver = None
        args: tuple[Any, ...] = ()
        if self._engine is not None and kind == "plant":
            resolver = getattr(self._engine, "resolve_plant_asset", None)
            args = (identity, stage)
        elif self._engine is not None and kind == "environment":
            for resolver_name in (
                "resolve_scenery_preview_asset",
                "resolve_garden_feature_preview_asset",
                "resolve_item_asset",
            ):
                candidate_resolver = getattr(self._engine, resolver_name, None)
                if not callable(candidate_resolver):
                    continue
                try:
                    asset = candidate_resolver(identity)
                    raw_path = getattr(asset, "path", None)
                    if raw_path and Path(str(raw_path)).is_file():
                        return Path(str(raw_path))
                except Exception:
                    continue
            return None
        elif self._engine is not None:
            resolver = getattr(self._engine, "resolve_item_asset", None)
            args = (identity,)
        if callable(resolver):
            try:
                asset = resolver(*args)
                raw_path = getattr(asset, "path", None)
                if raw_path and Path(str(raw_path)).is_file():
                    return Path(str(raw_path))
            except Exception:
                return None
        return None

    def _art_label(
        self,
        parent: Any,
        *,
        kind: str,
        identity: str,
        stage: str = "",
        explicit: str = "",
        width: int = 44,
        height: int = 44,
    ) -> GardenAssetThumbnail:
        label = GardenAssetThumbnail(
            parent,
            engine=self._engine,
            asset_id=identity,
            asset_type=kind,
            width=width,
            height=height,
            stage=stage,
            explicit_path=explicit,
        )
        label.setProperty("syncArtwork", True)
        label.setProperty("syncArtworkKind", str(kind))
        label.setProperty("syncArtworkIdentity", str(identity))
        label.setProperty("syncArtworkSource", label.property("gardenAssetSource"))
        label.setProperty("syncArtworkFallback", label.property("gardenAssetFallback"))
        return label

    def _plant_row(
        self,
        row: Mapping[str, Any],
        parent: Any,
        *,
        motion: SyncRewardPlantProgressMotion | None = None,
    ) -> QFrame:
        stage = str(row.get("stage_after", "") or "")
        full_bloom = (
            bool(row.get("full_bloom", False))
            or bool(row.get("fully_grown", False))
            or stage.casefold() in {"rare", "full_bloom", "full bloom"}
        )
        from .reward_receipt import receipt_progress_card
        species = str(row.get("species", "") or "")
        name = plant_stage_title(species, stage)
        stage_changed = bool(row.get("stage_event_id")) or bool(
            row.get("stage_before") and row.get("stage_after") != row.get("stage_before")
        )
        gained_units = max(0, int(row.get("growth_delta_units", 0) or 0))
        after_units = row.get("growth_after_units")
        before_units = max(0, int(after_units) - gained_units) if after_units is not None else None
        art = self._art_label(parent, kind="plant", identity=species, stage=stage,
                              explicit=str(row.get("artwork_asset", "") or ""), width=48, height=48)
        progress_target = max(0, min(100, int(row.get("stage_progress_after", 0) or 0)))
        journey = plant_growth_journey(species.replace("_", " ").title() or name, before_units, gained_units)
        if full_bloom and before_units is None:
            journey = plant_stage_event(species, "rare")
        card = receipt_progress_card(parent, art,
            "GROWTH MILESTONE" if full_bloom else "Growth milestone" if stage_changed else "Progress details",
            journey, progress_percent=progress_target, coins=max(0, int(row.get("progression_coins", 0) or 0)),
            palette=self._palette, full_bloom=full_bloom)
        frame = card.widget
        frame.setProperty("syncPrimaryCard", True)
        frame.setProperty("syncFullBloom", full_bloom)
        transition_source = str(row.get("stage_transition_source", "") or row.get("transition_source", "") or "")
        frame.setProperty("syncStageTransitionSource", transition_source)
        frame.setProperty("syncSharedGrowthSourceVisible", False)
        progress = card.progress
        progress.setProperty("semanticId", "sync-rewards.plant." + str(row.get("plant_id", "") or "unknown") + ".stage-progress")
        progress.setAccessibleName(f"{name} stage progress")
        progress_before = motion.start_value if motion is not None else progress_target
        stage_before = motion.start_stage if motion is not None else stage
        progress_changed = (
            progress_before != progress_target or stage_before != stage
        )
        if self._animations_enabled and motion is not None and progress_changed:
            if stage_before and stage and stage_before != stage:
                progress.setValue(progress_before)
                group = QSequentialAnimationGroup(self)
                complete_stage = QPropertyAnimation(progress, b"value")
                complete_stage.setDuration(150)
                complete_stage.setStartValue(progress_before)
                complete_stage.setEndValue(100)
                complete_stage.setEasingCurve(QEasingCurve.Type.OutCubic)
                enter_stage = QPropertyAnimation(progress, b"value")
                enter_stage.setDuration(210)
                enter_stage.setStartValue(0)
                enter_stage.setEndValue(progress_target)
                enter_stage.setEasingCurve(QEasingCurve.Type.OutCubic)
                group.addAnimation(complete_stage)
                group.addAnimation(enter_stage)
                animation = group
            else:
                progress.setValue(progress_before)
                progress_fill = QPropertyAnimation(progress, b"value", self)
                progress_fill.setDuration(360)
                progress_fill.setStartValue(progress_before)
                progress_fill.setEndValue(progress_target)
                progress_fill.setEasingCurve(QEasingCurve.Type.OutCubic)
                animation = progress_fill
            animation.setLoopCount(1)

            def finish_progress() -> None:
                try:
                    progress.setValue(progress_target)
                except RuntimeError:
                    pass
                if animation in self._progress_animations:
                    self._progress_animations.remove(animation)

            def start_progress() -> None:
                if self._dismissed or animation not in self._progress_animations:
                    return
                try:
                    animation.start()
                except RuntimeError:
                    finish_progress()

            animation.finished.connect(finish_progress)
            self._progress_animations.append(animation)
            QTimer.singleShot(0, start_progress)
        else:
            # Final copy and value are readable immediately under reduced motion.
            progress.setValue(progress_target)
        return frame

    def _start_full_bloom_emphasis(self, frame: Any) -> None:
        """Run one restrained, non-looping Full Bloom opacity pulse."""

        if not self._animations_enabled:
            return
        effect = QGraphicsOpacityEffect(frame)
        effect.setOpacity(1.0)
        frame.setGraphicsEffect(effect)
        frame.setProperty("syncFullBloomPulseActive", True)
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.5, 1.0)
        animation.setEndValue(0.0)
        animation.setDuration(SYNC_REWARD_FULL_BLOOM_PULSE_MS)
        animation.setLoopCount(1)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def render_pulse(raw_value: Any) -> None:
            if animation not in self._full_bloom_animations:
                return
            try:
                emphasis = max(0.0, min(1.0, float(raw_value)))
                effect.setOpacity(1.0 - (0.12 * emphasis))
            except (RuntimeError, TypeError, ValueError):
                return

        def finish_pulse() -> None:
            try:
                effect.setOpacity(1.0)
                frame.setGraphicsEffect(None)
                frame.setProperty("syncFullBloomPulseActive", False)
            except RuntimeError:
                pass
            if animation in self._full_bloom_animations:
                self._full_bloom_animations.remove(animation)

        def start_pulse() -> None:
            if self._dismissed or animation not in self._full_bloom_animations:
                return
            try:
                animation.start()
            except RuntimeError:
                finish_pulse()

        animation.valueChanged.connect(render_pulse)
        animation.finished.connect(finish_pulse)
        self._full_bloom_animations.append(animation)
        QTimer.singleShot(0, start_pulse)

    def _environment_row(self, row: Mapping[str, Any], parent: Any) -> QFrame:
        identity = str(row.get("environment_id", "") or "")
        art = self._art_label(parent, kind="environment", identity=identity,
            explicit=str(row.get("preview_asset", "") or ""), width=44, height=44)
        event = receipt_event_row(parent, art,
            str(row.get("display_name", "Garden discovery") or "Garden discovery"),
            reward=row, eyebrow="New discovery", rarity_badge=True)
        event.widget.setProperty("syncRow", True)
        event.widget.setProperty("syncRewardKind", "garden_discovery")
        event.widget.setProperty("syncRewardIdentity", identity)
        event.widget.setProperty("syncRewardEventId", str(row.get("event_id", "") or ""))
        return event.widget

    def _find_card(self, row: Mapping[str, Any], parent: Any) -> QFrame:
        from ..garden_finds import STANDARD_FIND_REGISTRY, standard_find_artwork_ref

        reward_id = str(row.get("reward_id", "") or "")
        art_reference = standard_find_artwork_ref(reward_id, str(row.get("image_asset", "") or ""))
        artwork = self._art_label(
            parent, kind="find", identity=art_reference or reward_id,
            explicit=art_reference, width=44, height=44,
        )
        title = str(row.get("display_name", reward_id) or reward_id or "Garden Find")
        amount = max(0, int(row.get("reward_amount_total", 0) or 0))
        kind = str(row.get("reward_type", "") or "")
        definition = next((find for find in STANDARD_FIND_REGISTRY if find.reward_id == reward_id), None)
        detail = ""
        if kind == "inventory_item" and definition is not None and definition.inventory_item_id:
            from ..reward_presentation import RewardLine
            detail = RewardLine("inventory_item", amount or _quantity(row), definition.inventory_item_id).learner_text
        event = receipt_event_row(parent, artwork, title,
            detail=detail, reward=row, eyebrow="Garden Find" if definition is not None else "Item earned", rarity_badge=True)
        frame = event.widget
        frame.setProperty("syncRow", True)
        frame.setProperty("syncRewardKind", "standard_find")
        frame.setProperty("syncRewardIdentity", reward_id)
        frame.setProperty("syncRewardEventId", str(row.get("event_id", "") or ""))
        quantity = _quantity(row)
        if amount and kind in {"growth", "coins"}:
            from .reward_receipt import receipt_resource_values
            event.copy.addWidget(receipt_resource_values(frame, coins=amount if kind == "coins" else 0,
                                                        growth_units=amount * 100 if kind == "growth" else 0))
        if quantity > 1:
            badge = QLabel(f"×{quantity:,}", frame)
            badge.setProperty("syncQuantity", True)
            badge.setProperty("syncPrimary", True)
            badge.setTextFormat(Qt.TextFormat.PlainText)
            apply_tabular_numerals(badge)
            event.layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        return frame

    def _project_growth_rows(self) -> tuple[Any, ...]:
        snapshot = None
        resolver = getattr(self._engine, "growth_projects_snapshot", None)
        if callable(resolver):
            try:
                snapshot = resolver()
            except Exception:
                snapshot = None
        return project_growth_allocations(
            tuple(getattr(self._summary, "project_allocations", ()) or ()),
            snapshot,
            landmark_growth_units=max(
                0,
                int(
                    getattr(
                        self._summary,
                        "landmark_growth_delta_units",
                        0,
                    )
                    or 0
                ),
            ),
        )

    def _growth_allocation_entries(self) -> tuple[tuple[Any, ...], ...]:
        entries: list[tuple[Any, ...]] = []
        for asset_id, units, label_text in (
            (
                "shared_growth",
                self._summary.shared_growth_delta_units,
                "Shared Growth",
            ),
            (
                "stored_growth",
                self._summary.stored_growth_delta_units,
                "Stored Growth added",
            ),
        ):
            if units > 0:
                entries.append((asset_id, units, label_text, "", "", "", ""))
        for project in self._project_growth_rows():
            normalized_status = str(project.status or "").casefold()
            projected_status_copy = str(
                getattr(project, "status_copy", "") or ""
            )
            state_copy = (
                projected_status_copy
                if projected_status_copy.casefold().startswith((
                    "reward ready",
                    "in progress",
                    "completed",
                    "not started",
                )) else
                "Reward ready"
                if "claimable" in normalized_status
                or "ready to claim" in normalized_status else
                "Completed"
                if "claimed" in normalized_status
                or "complete" in normalized_status else
                "In progress"
                if "funded" in normalized_status
                or "active" in normalized_status else
                ""
            )
            result_copy = f"Stored Growth added to {project.display_name}"
            entries.append((
                project.artwork_id or "growth_resource",
                project.units,
                result_copy,
                state_copy,
                project.target_type,
                project.target_id,
                " · ".join(
                    value
                    for value in (result_copy, state_copy, project.progress)
                    if value
                ),
            ))
        return tuple(entries)

    def _growth_allocation_strip(self, parent: Any) -> QFrame:
        strip = QFrame(parent)
        strip.setProperty("syncAllocationStrip", True)
        layout = QGridLayout(strip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        allocations = self._growth_allocation_entries()
        columns = 2 if len(allocations) > 2 else max(1, len(allocations))
        strip.setProperty("syncAllocationColumnCount", columns)
        for column in range(columns):
            layout.setColumnStretch(column, 1)
        for index, (
            asset_id,
            units,
            label_text,
            detail_text,
            target_type,
            target_id,
            accessible_detail,
        ) in enumerate(allocations):
            item = QFrame(strip)
            item.setProperty("syncAllocationItem", True)
            item.setMinimumWidth(0)
            item.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            item.setProperty("syncProjectTargetType", target_type)
            item.setProperty("syncProjectTargetId", target_id)
            item.setProperty("syncProjectGrowthUnits", int(units))
            if accessible_detail:
                item.setAccessibleDescription(accessible_detail)
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(8, 6, 8, 6)
            item_layout.setSpacing(8)
            item_layout.addWidget(self._art_label(
                item,
                kind="ui",
                identity=asset_id,
                width=22,
                height=22,
            ))
            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(0)
            amount = QLabel(format_growth_units(units, signed=True), item)
            amount.setProperty("syncPrimary", True)
            amount.setTextFormat(Qt.TextFormat.PlainText)
            apply_tabular_numerals(amount)
            copy.addWidget(amount)
            caption = QLabel(label_text, item)
            caption.setProperty("syncSecondary", True)
            caption.setMinimumWidth(0)
            caption.setWordWrap(True)
            caption.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            caption.setTextFormat(Qt.TextFormat.PlainText)
            copy.addWidget(caption)
            if detail_text:
                detail = QLabel(detail_text, item)
                detail.setProperty("syncMuted", True)
                detail.setWordWrap(True)
                detail.setTextFormat(Qt.TextFormat.PlainText)
                copy.addWidget(detail)
            item_layout.addLayout(copy, 1)
            layout.addWidget(item, index // columns, index % columns)
        return strip

    def _rewards_section(
        self,
        environments: tuple[dict[str, Any], ...],
        finds: tuple[dict[str, Any], ...],
        parent: Any,
    ) -> QFrame:
        section = QFrame(parent)
        section.setProperty("syncRewardsSection", True)
        section.setProperty(
            "syncRewardGroupOrder",
            ["standard_finds", "garden_discoveries"],
        )
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)
        for row in finds:
            section_layout.addWidget(self._find_card(row, section))
        for row in environments:
            section_layout.addWidget(self._environment_row(row, section))
        return section

    def _simple_row(
        self,
        text: str,
        parent: Any,
        *,
        detail: str = "",
        icon_name: str = "check-circle",
        art_identity: str = "",
        art_asset: str = "",
    ) -> QFrame:
        frame = QFrame(parent)
        frame.setProperty("syncRow", True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(9)
        icon = self._art_label(
            frame,
            kind=icon_name,
            identity=art_identity,
            explicit=art_asset,
            width=26,
            height=26,
        )
        icon.setProperty("syncBoostArtwork", True)
        icon.setProperty("syncBoostArtworkReference", art_identity)
        icon.setAccessibleName(f"{text.partition(' active')[0]} artwork")
        layout.addWidget(icon)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(1)
        primary = QLabel(text, frame)
        primary.setProperty("syncPrimary", True)
        primary.setWordWrap(True)
        primary.setTextFormat(Qt.TextFormat.PlainText)
        copy.addWidget(primary)
        if detail:
            secondary = QLabel(detail, frame)
            secondary.setProperty("syncSecondary", True)
            secondary.setWordWrap(True)
            secondary.setTextFormat(Qt.TextFormat.PlainText)
            copy.addWidget(secondary)
        layout.addLayout(copy, 1)
        return frame

    def _rebuild_body(
        self,
        *,
        motion: SyncRewardMotionPlan | None = None,
    ) -> None:
        self._subtitle.setText(sync_reward_subtitle(self._summary))
        layout = self._new_body()
        self._clear_layout(self._summary_fixed_layout)
        plan = sync_reward_visibility_plan(self._summary, expanded=self._expanded)
        motion = motion or SyncRewardMotionPlan()
        metric_motion = {item.label: item for item in motion.metrics}
        progress_motion = {
            item.plant_key: item for item in motion.plant_progress
        }

        if self._additional_line_visible and self._summary.additional_answer_count > 0:
            count = self._summary.additional_answer_count
            noun = "review was" if count == 1 else "reviews were"
            additional = QLabel(
                f"{count:,} additional {noun} added",
                self._body_widget,
            )
            additional.setProperty("syncAdditional", True)
            additional.setWordWrap(True)
            additional.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(additional)

        metrics_frame = QFrame(self._summary_fixed)
        metrics_frame.setProperty("syncMetricStrip", True)
        metrics_layout = receipt_metrics_layout(metrics_frame)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(6)
        all_metrics = sync_reward_metric_plan(self._summary)
        metrics = tuple(metric for metric in all_metrics if metric[2] != "sync_review_cards")
        count = max(0, int(self._summary.eligible_answer_count))
        headline = QLabel(sync_reward_subtitle(self._summary), self._summary_fixed)
        headline.setWordWrap(True)
        headline.setProperty("syncPrimary", True)
        apply_tabular_numerals(headline)
        headline.setToolTip("Study answers rewarded by this sync; a card may be studied more than once.")
        self.setProperty(
            "syncRewardMetricOrder", [str(metric[1]) for metric in metrics]
        )
        self.setProperty(
            "syncReviewCount", max(0, int(self._summary.eligible_answer_count))
        )
        self.setProperty(
            "syncGardenDiscoveryCount", len(self._summary.environment_discoveries)
        )
        # Match the review and session summaries: Coins, Growth, Discoveries.
        for value, label, icon_name in metrics:
            metrics_layout.addWidget(
                self._metric_tile(value, label, icon_name, metrics_frame,
                                  motion=metric_motion.get(label)),
                1,
            )
        self._summary_fixed_layout.addWidget(metrics_frame)
        self._summary_fixed_layout.addWidget(headline)
        divider = self._divider(self._summary_fixed)
        self._summary_fixed_layout.addWidget(divider)
        metrics_frame.show()
        headline.show()
        divider.show()
        self._summary_fixed_layout.activate()

        if plan.environment_discoveries or plan.finds:
            layout.addWidget(self._rewards_section(
                plan.environment_discoveries,
                plan.finds,
                self._body_widget,
            ))

        allocation_entries = self._growth_allocation_entries()
        effects = _effect_lines(self._summary)
        featured = tuple(row for row in plan.plant_growth if row.get("full_bloom"))
        for row in featured:
            plant_frame = self._plant_row(row, self._body_widget, motion=progress_motion.get(_plant_motion_key(row)))
            layout.addWidget(plant_frame)
            if _full_bloom_key(row) in motion.full_bloom_event_keys:
                self._start_full_bloom_emphasis(plant_frame)

        for row in plan.plant_growth:
            if row not in featured:
                layout.addWidget(self._plant_row(
                    row, self._body_widget, motion=progress_motion.get(_plant_motion_key(row)),
                ))

        collapsed_plan = sync_reward_visibility_plan(self._summary)
        hidden_count = (collapsed_plan.hidden_count + len(allocation_entries) + len(effects)
                        + int(self._summary.all_clear_earned))
        if hidden_count > 0 or self._expanded:
            layout.addWidget(self._divider(self._body_widget))
            self._disclosure = QToolButton(self._body_widget)
            self._disclosure.setText("Details")
            self._disclosure.setIcon(garden_icon("chevron-up" if self._expanded else "chevron-down", color=self._palette["text_secondary"]))
            self._disclosure.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self._disclosure.setProperty("syncDisclosure", True)
            self._disclosure.setAccessibleName(
                "Show less sync reward detail" if self._expanded
                else f"Show {hidden_count:,} more sync reward entries"
            )
            self._disclosure.clicked.connect(self._toggle_expanded)
            layout.addWidget(self._disclosure, 0, Qt.AlignmentFlag.AlignRight)
        else:
            self._disclosure = None

        if self._expanded and allocation_entries:
            layout.addWidget(self._growth_allocation_strip(self._body_widget))

        if self._expanded and self._summary.all_clear_earned:
            layout.addWidget(self._section_heading("TODAY’S CARDS", self._body_widget))
            detail = "All due cards are complete."
            if self._summary.all_clear_coin_reward > 0:
                detail = (
                    f"{detail}  +{format_garden_coins(self._summary.all_clear_coin_reward)}"
                )
            layout.addWidget(self._simple_row(
                "All Clear",
                self._body_widget,
                detail=detail,
                icon_name="ui",
                art_identity=(
                    "garden_coin"
                    if self._summary.all_clear_coin_reward > 0
                    else "sync_review_cards"
                ),
            ))

        if self._expanded and effects:
            layout.addWidget(self._section_heading("CURRENT BOOSTS", self._body_widget))
            for icon_name, art_identity, text, art_asset in effects:
                layout.addWidget(self._simple_row(
                    text,
                    self._body_widget,
                    icon_name=icon_name,
                    art_identity=art_identity,
                    art_asset=art_asset,
                ))

        self.reposition()
        self._schedule_settled_reposition()

    def update_model(self, summary: SyncRewardSummary) -> None:
        """Update the one mounted card while retaining disclosure state."""

        if not isinstance(summary, SyncRewardSummary):
            raise TypeError("summary must be a SyncRewardSummary")
        if not summary.meaningful:
            raise ValueError("summary must contain a meaningful committed reward")
        previous = self._summary
        motion = sync_reward_motion_plan(summary, previous=previous)
        self._summary = summary
        if summary.additional_answer_count > 0:
            self._additional_line_visible = True
        self._rebuild_body(motion=motion)

    def _toggle_expanded(self) -> None:
        self._additional_line_visible = False
        self._expanded = not self._expanded
        self._rebuild_body()

    def _natural_height(self) -> int:
        try:
            return self._header.height() + self._summary_fixed.height() + self._footer.height() + receipt_body_height(self._body_widget, self._body_widget.width()) + 4
        except (AttributeError, RuntimeError):
            return SYNC_REWARD_MIN_HEIGHT

    def _schedule_settled_reposition(self) -> None:
        """Refit once Qt has committed the scroll body's native size hint."""

        if self._dismissed or self._settled_reposition_pending:
            return
        self._settled_reposition_pending = True
        QTimer.singleShot(0, self._reposition_after_layout_settles)

    def _reposition_after_layout_settles(self) -> None:
        self._settled_reposition_pending = False
        if self._dismissed:
            return
        try:
            self.reposition()
        except RuntimeError:
            # The nonmodal receipt may have been deleted before the queued
            # layout turn. Its dismissal callback already owns teardown.
            return

    def reposition(
        self,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> tuple[int, int, int, int]:
        parent = self.parentWidget()
        if parent is None:
            return (0, 0, max(1, int(self.width())), max(1, int(self.height())))
        width = max(1, int(parent.width())) if viewport_width is None else int(viewport_width)
        height = max(1, int(parent.height())) if viewport_height is None else int(viewport_height)
        provisional = sync_reward_summary_geometry(width, height, 1)
        self.setFixedWidth(provisional[2])
        fit_receipt_chrome(self._header, self._footer, provisional[2])
        fixed_height = self._summary_fixed_layout.totalHeightForWidth(provisional[2])
        if fixed_height < 0:
            fixed_height = self._summary_fixed_layout.sizeHint().height()
        self._summary_fixed.setFixedHeight(max(1, fixed_height))
        self._body_widget.setFixedWidth(max(1, provisional[2] - 8))
        geometry = sync_reward_summary_geometry(
            width,
            height,
            self._natural_height(),
        )
        self.setFixedSize(geometry[2], geometry[3])
        self.move(geometry[0], geometry[1])
        self.setProperty("summaryViewportBounded", bool(
            geometry[0] >= 0
            and geometry[1] >= 0
            and geometry[0] + geometry[2] <= width
            and geometry[1] + geometry[3] <= height
        ))
        return geometry

    def eventFilter(self, watched: Any, event: Any) -> bool:
        try:
            if (
                watched is self._filtered_parent
                and not self._dismissed
                and event.type() in {QEvent.Type.Resize, QEvent.Type.Show}
            ):
                self.reposition()
        except Exception:
            pass
        return False

    def showEvent(self, event: Any) -> None:
        try:
            super().showEvent(event)
        except Exception:
            pass
        self.reposition()
        self._schedule_settled_reposition()
        if self._entrance_started or not self._animations_enabled:
            return
        self._entrance_started = True
        destination = self.pos()
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.0)
        self.setGraphicsEffect(opacity)
        fade = QPropertyAnimation(opacity, b"opacity", self)
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        rise = QPropertyAnimation(self, b"pos", self)
        rise.setDuration(180)
        rise.setStartValue(destination + QPoint(0, 4))
        rise.setEndValue(destination)
        rise.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finish_opacity() -> None:
            try:
                opacity.setOpacity(1.0)
                self.setGraphicsEffect(None)
            except RuntimeError:
                pass

        fade.finished.connect(finish_opacity)
        self._entrance_animations = [fade, rise]
        fade.start()
        rise.start()

    def _dismiss(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        callback = self._on_dismiss
        self.close()
        if callable(callback):
            callback()

    def _open_garden(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        callback = self._on_open_garden
        self.close()
        if callable(callback):
            callback()

    def closeEvent(self, event: Any) -> None:
        for collection_name in (
            "_entrance_animations",
            "_metric_animations",
            "_progress_animations",
            "_full_bloom_animations",
        ):
            animations = list(getattr(self, collection_name, ()))
            setattr(self, collection_name, [])
            for animation in animations:
                try:
                    animation.stop()
                except (AttributeError, RuntimeError):
                    pass
        parent = self._filtered_parent
        self._filtered_parent = None
        if parent is not None:
            try:
                parent.removeEventFilter(self)
            except Exception:
                pass
        try:
            super().closeEvent(event)
        except Exception:
            pass


__all__ = [
    "SYNC_REWARD_MAX_HEIGHT",
    "SYNC_REWARD_MAX_WIDTH",
    "SYNC_REWARD_METRIC_ANIMATION_MS",
    "SYNC_REWARD_FULL_BLOOM_PULSE_MS",
    "SYNC_REWARD_BODY_SPACING",
    "SYNC_REWARD_MIN_HEIGHT",
    "SYNC_REWARD_MIN_WIDTH",
    "SYNC_REWARD_PREFERRED_WIDTH",
    "SyncRewardSummaryCard",
    "SyncRewardMetricMotion",
    "SyncRewardMotionPlan",
    "SyncRewardPlantProgressMotion",
    "SyncRewardVisibilityPlan",
    "sync_reward_metric_plan",
    "sync_reward_motion_plan",
    "sync_reward_subtitle",
    "sync_reward_summary_geometry",
    "sync_reward_visibility_plan",
]
