"""Nonmodal Qt renderer for finalized local review Session Summaries.

The event accumulator in :mod:`ankigarden.ui.session_summary` owns all facts.
This module only renders one frozen payload.  It deliberately creates a child
``QFrame`` instead of a dialog or page-wide overlay, so the Anki surface around
the card remains usable.
"""

from __future__ import annotations

from ..presentation import plant_stage_event

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..asset_manager import bundled_ui_asset_path
from ..garden_finds import STANDARD_FIND_RECEIPT_SOURCES
from ..environment import (
    DEFAULT_SCENERY_ID,
    GARDEN_FEATURE_CATALOG,
    SCENERY_CATALOG,
    canonical_garden_feature_id,
)
from ..reward_presentation import project_growth_allocations
from .accessibility import read_system_reduced_motion
from .environment_art import environment_preview_pixmap
from .formatters import format_garden_coins, format_plant_name, format_quantity, format_stage_progress
from .copy import cards_studied_text
from .icons import garden_icon
from .reward_rarity import apply_reward_treatment, reward_treatment
from .reward_receipt import fit_receipt_chrome, receipt_metrics_layout, build_receipt_shell, receipt_button, receipt_metric, receipt_event_row, receipt_style, receipt_body_height, reward_discovery_count
from .plant_art import normalized_plant_pixmap
from .session_summary import (
    EnvironmentDiscovery,
    PlantGrowthTotal,
    PlantMilestone,
    SessionDaySummary,
    SessionSummaryPayload,
    StandardFind,
    format_growth_units,
    project_session_day,
    session_coin_groups,
    unlock_category_copy,
)
from .theme import GARDEN_THEME, apply_tabular_numerals


SESSION_SUMMARY_DEFAULT_WIDTH = 400
SESSION_SUMMARY_MIN_WIDTH = 336
SESSION_SUMMARY_MAX_WIDTH = 400
SESSION_SUMMARY_EDGE_MARGIN = 20
SESSION_SUMMARY_VIEWPORT_VERTICAL_MARGIN = 32
SESSION_SUMMARY_PREFERRED_TOP_MARGIN = 48
SESSION_SUMMARY_MIN_VERTICAL_MARGIN = 16
# All reward details remain visible in one bounded, content-fitted scroll area.
SESSION_SUMMARY_MAX_HEIGHT: int | None = 520
SESSION_SUMMARY_HEADER_HEIGHT = 44
SESSION_SUMMARY_FOOTER_HEIGHT = 48
SESSION_SUMMARY_FRAME_BORDER_WIDTH = 1
SESSION_SUMMARY_COMPACT_HOST_HEIGHT = 903


@dataclass(frozen=True)
class SessionPlantProgress:
    name: str
    gain: str
    description: str
    stage_change: str
    stage: str
    current_units: int | None
    required_units: int | None
    fully_grown: bool


def session_plant_progress(
    species: str, before_units: int | None, gained_units: int, *, full_bloom: bool = False,
) -> SessionPlantProgress:
    """Present recorded session gains and exact within-stage hundredths together."""
    from ..growth import stage_presentation, stage_progress

    before = stage_progress(before_units // 100) if before_units is not None else None
    total_units = before_units + gained_units if before_units is not None else None
    after = stage_progress(total_units // 100) if total_units is not None else None
    fully_grown = full_bloom or bool(after is not None and after.fully_grown)
    stage = "rare" if fully_grown else after.stage if after is not None else ""
    current_units = required_units = None
    description = "Fully grown" if fully_grown else ""
    if after is not None and not fully_grown:
        current_units = total_units - after.stage_start * 100
        required_units = after.stage_goal * 100
        description = format_stage_progress(
            Decimal(current_units) / 100, Decimal(required_units) / 100, after.next_stage,
        )
    stage_change = ""
    if before is not None and after is not None:
        advanced = after.stage_index - before.stage_index
        if advanced > 0:
            destination = stage_presentation(after.stage).display_name
            stage_change = (f"Reached {destination}" if advanced == 1 else
                            f"Advanced {advanced} stages to {destination}")
    elif full_bloom:
        stage_change = "Reached Full Bloom"
    return SessionPlantProgress(
        name=format_plant_name({"species": species, "stage": stage}),
        gain=f"{format_growth_units(gained_units, signed=True)} Growth",
        description=description, stage_change=stage_change, stage=stage,
        current_units=current_units, required_units=required_units, fully_grown=fully_grown,
    )


def session_summary_palette(background_lightness: int | None = None) -> dict[str, str]:
    """Use the same Garden palette on the workspace and reward cards."""

    shared = {
        "elevated_surface": GARDEN_THEME["session_summary_panel_bg"],
        "raised_surface": GARDEN_THEME["session_summary_card_bg"],
        "selected_surface": GARDEN_THEME["session_summary_card_bg_raised"],
        "strong_border": GARDEN_THEME["session_summary_border"],
        "subtle_border": GARDEN_THEME["session_summary_border_subtle"],
        "divider": GARDEN_THEME["session_summary_divider"],
        "text_primary": GARDEN_THEME["session_summary_text_primary"],
        "text_secondary": GARDEN_THEME["session_summary_text_secondary"],
        "text_muted": GARDEN_THEME["session_summary_text_muted"],
        "metric_label": "#AEBFB7",
        "growth_accent": GARDEN_THEME["session_summary_growth"],
        "coin_accent": GARDEN_THEME["session_summary_coin"],
        "action_text": GARDEN_THEME["session_summary_primary_text"],
        "action_accent": GARDEN_THEME["session_summary_primary"],
        "action_hover": GARDEN_THEME["session_summary_primary_hover"],
        "action_pressed": GARDEN_THEME["session_summary_primary_pressed"],
        "secondary_action": "rgba(218, 235, 227, 15)",
        "secondary_border": GARDEN_THEME["session_summary_border_subtle"],
        "plant_popover_shadow": GARDEN_THEME["plant_popover_shadow"],
        "progress_track": GARDEN_THEME["session_summary_progress_track"],
        "find_accent": GARDEN_THEME["session_summary_find"],
        "milestone_accent": GARDEN_THEME["session_summary_milestone"],
        "highlight_surface": GARDEN_THEME["session_summary_highlight_surface"],
        "chip_surface": GARDEN_THEME["session_summary_chip_surface"],
        "today_surface": GARDEN_THEME["session_summary_card_bg_raised"],
        "boost_surface": GARDEN_THEME["session_summary_card_bg"],
        "receipt_panel": GARDEN_THEME["session_summary_panel_bg"],
        "receipt_primary_surface": GARDEN_THEME["surface_1"],
        "receipt_secondary_surface": GARDEN_THEME["surface_1"],
        "receipt_hover_surface": GARDEN_THEME["surface_2"],
        "receipt_text_primary": GARDEN_THEME["text_primary"],
        "receipt_text_secondary": GARDEN_THEME["text_secondary"],
        "receipt_text_muted": GARDEN_THEME["text_muted"],
        "receipt_primary_mint": GARDEN_THEME["growth_accent"],
        "receipt_coin": GARDEN_THEME["coin_accent"],
        "receipt_milestone": GARDEN_THEME["coin_accent"],
        "receipt_border": GARDEN_THEME["subtle_border"],
        "receipt_border_strong": GARDEN_THEME["subtle_border"],
    }
    return shared


def session_summary_geometry(
    viewport_width: int,
    viewport_height: int,
    content_height: int,
    *,
    preferred_width: int = SESSION_SUMMARY_DEFAULT_WIDTH,
    exclusion_top: int | None = None,
    reserved_top: int | None = None,
) -> tuple[int, int, int, int]:
    """Return a top-right, viewport-bounded ``(x, y, width, height)``.

    The preferred width and hard cap are both 400 px. On narrow windows the
    card contracts to preserve 20 px side margins. Prefer the approved 48 px
    top offset when the natural card also preserves the 16 px bottom safety
    margin. When the content is taller, fall back to 16 px at both edges and
    let only the body scroll. A measured ``exclusion_top`` keeps the card above
    lower host controls. A measured ``reserved_top`` keeps it below upper host
    content such as the Deck Browser Home garden card.
    """

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))
    available_bottom = viewport_height
    if exclusion_top is not None:
        try:
            available_bottom = max(
                1,
                min(viewport_height, int(exclusion_top)),
            )
        except (TypeError, ValueError):
            available_bottom = viewport_height
    available_top = 0
    if reserved_top is not None:
        try:
            available_top = max(
                0,
                min(available_bottom - 1, int(reserved_top)),
            )
        except (TypeError, ValueError):
            available_top = 0
    available_height = max(1, available_bottom - available_top)
    content_height = max(1, int(content_height))
    preferred_width = max(
        SESSION_SUMMARY_MIN_WIDTH,
        min(SESSION_SUMMARY_MAX_WIDTH, int(preferred_width)),
    )

    available_width = max(
        1,
        viewport_width - SESSION_SUMMARY_VIEWPORT_VERTICAL_MARGIN,
    )
    width = min(preferred_width, available_width)
    height_limit = max(1, available_height - SESSION_SUMMARY_VIEWPORT_VERTICAL_MARGIN)
    height = min(content_height, height_limit, SESSION_SUMMARY_MAX_HEIGHT or height_limit)
    x = max(
        0,
        viewport_width - width - SESSION_SUMMARY_EDGE_MARGIN,
    )
    preferred_height_limit = max(
        1,
        available_height
        - SESSION_SUMMARY_PREFERRED_TOP_MARGIN
        - SESSION_SUMMARY_MIN_VERTICAL_MARGIN,
    )
    top_margin = (
        SESSION_SUMMARY_PREFERRED_TOP_MARGIN
        if content_height <= preferred_height_limit
        else SESSION_SUMMARY_MIN_VERTICAL_MARGIN
    )
    y = available_top + min(
        top_margin,
        max(0, available_height - height),
    )
    return x, y, width, height


def session_summary_uses_compact_density(viewport_height: int) -> bool:
    """Use the measured short-window density below the Retina host height.

    Anki's 1440x900 and 1600x960 windows leave content hosts of roughly 813
    and 873 logical pixels after native chrome.  The compact variant preserves
    reward artwork and actions while removing default scrolling at both sizes.
    """

    return max(0, int(viewport_height)) < SESSION_SUMMARY_COMPACT_HOST_HEIGHT


def session_effect_remaining_text(
    effect: Any,
    *,
    now_epoch_seconds: float | None = None,
    fallback_remaining_seconds: int | None = None,
) -> str:
    """Return concise card-counted copy for an active effect row."""

    kind = str(getattr(effect, "kind", "") or "")
    if not kind:
        effect_id = str(getattr(effect, "effect_id", "") or "").casefold()
        kind = (
            "fertilizer"
            if "fertilizer" in effect_id or hasattr(effect, "remaining_seconds")
            else "booster"
        )
    remaining_cards = max(
        0,
        int(getattr(effect, "remaining_cards", 0) or 0),
    )
    if kind == "fertilizer":
        return (
            f"{format_quantity(remaining_cards, 'card')} remaining"
            if remaining_cards > 0
            else ""
        )

    remaining_cards = max(0, int(getattr(effect, "remaining_cards", 0) or 0))
    if remaining_cards <= 0:
        return ""
    noun = "card" if remaining_cards == 1 else "cards"
    return f"{remaining_cards:,} {noun} remaining"


def session_inventory_reward_lines(
    receipts: Sequence[Any],
) -> tuple[tuple[str, int, str], ...]:
    """Project exact inventory receipts through the shared reward presenter."""

    grouped: dict[str, list[Any]] = {}
    order: list[str] = []
    for receipt in receipts:
        identity = str(
            getattr(receipt, "correlation_id", "")
            or getattr(receipt, "event_key", "")
            or ""
        )
        if not identity:
            continue
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append(receipt)

    try:
        from ..reward_presentation import reward_summary
    except Exception:
        return ()

    projected: list[tuple[str, int, str]] = []
    for identity in order:
        try:
            summary = reward_summary(
                tuple(grouped[identity]),
                correlation_id=identity,
            )
        except (TypeError, ValueError):
            continue
        for line in summary.consolidated_lines:
            item_id = str(getattr(line, "item_id", "") or "")
            amount = max(0, int(getattr(line, "amount", 0) or 0))
            if (
                str(getattr(line, "reward_type", "") or "")
                != "inventory_item"
                or not item_id
                or amount <= 0
            ):
                continue
            projected.append((item_id, amount, str(line.learner_text)))
    return tuple(projected)


@dataclass(frozen=True)
class SessionEarnedItem:
    """One consolidated committed inventory grant with visible provenance."""

    item_id: str
    name: str
    art_reference: str
    quantity: int
    source_labels: tuple[str, ...]
    source_find_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()


def _session_item_source_label(source: Any, source_id: str = "") -> str:
    normalized = str(source or "").replace("-", "_").casefold()
    if normalized in STANDARD_FIND_RECEIPT_SOURCES or normalized.startswith("garden_find"):
        return "Garden Find"
    if "full_bloom" in normalized:
        return "Full Bloom"
    if "achievement" in normalized:
        from ..achievements import BED_MILESTONES
        if source_id in BED_MILESTONES:
            return f"Bed {BED_MILESTONES[source_id]} unlocked"
        return "Achievement"
    if "checkpoint" in normalized or normalized.startswith("stage"):
        return "Stage reward"
    if "completion_cycle" in normalized:
        return "Garden Cycle"
    if normalized in {"all_due", "all_clear", "todays_cards_completion"}:
        return "Today’s cards"
    return "Garden reward"


def session_earned_item_plan(summary: Any) -> tuple[SessionEarnedItem, ...]:
    """Consolidate item grants by stable item ID without changing quantities.

    Garden Find outcomes and typed reward receipts are two presentations of
    the same committed event in production. Find-linked receipts are therefore
    represented by the reconciled Find row once. Distinct committed events for
    the same item retain their quantities but share one earned-item row with
    every source identified.
    """

    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def add(
        *,
        item_id: str,
        name: str,
        art_reference: str,
        quantity: int,
        source_label: str,
        source_find_id: str = "",
        event_ids: Sequence[str] = (),
    ) -> None:
        normalized_id = str(item_id or "").strip()
        normalized_quantity = max(0, int(quantity or 0))
        if not normalized_id or normalized_quantity <= 0:
            return
        if normalized_id not in grouped:
            order.append(normalized_id)
            grouped[normalized_id] = {
                "name": str(name or "").strip() or normalized_id.replace("_", " ").title(),
                "art_reference": str(art_reference or "").strip() or normalized_id,
                "quantity": 0,
                "source_labels": [],
                "source_find_ids": [],
                "event_ids": [],
            }
        row = grouped[normalized_id]
        row["quantity"] += normalized_quantity
        for key, value in (
            ("source_labels", str(source_label or "").strip()),
            ("source_find_ids", str(source_find_id or "").strip()),
        ):
            if value and value not in row[key]:
                row[key].append(value)
        for event_id in event_ids:
            normalized_event = str(event_id or "").strip()
            if normalized_event and normalized_event not in row["event_ids"]:
                row["event_ids"].append(normalized_event)

    find_event_ids: set[str] = set()
    represented_find_item_ids: set[str] = set()
    if bool(getattr(summary, "find_items_reconciled", False)):
        standard_finds = tuple(getattr(summary, "standard_finds", ()) or ())
        for item in tuple(getattr(summary, "find_items", ()) or ()):
            if str(getattr(item, "reward_type", "") or "") != "inventory_item":
                continue
            item_id = str(getattr(item, "item_id", "") or "")
            if not item_id:
                continue
            represented_find_item_ids.add(item_id)
            find_id = str(getattr(item, "find_id", "") or "")
            linked_event_ids = tuple(
                str(getattr(find, "event_id", "") or "")
                for find in standard_finds
                if str(getattr(find, "find_id", "") or "") == find_id
                and str(getattr(find, "event_id", "") or "")
            )
            find_event_ids.update(linked_event_ids)
            add(
                item_id=item_id,
                name=str(getattr(item, "find_name", "") or "Earned item"),
                art_reference=item_id,
                quantity=max(0, int(getattr(item, "quantity", 0) or 0)),
                source_label="Garden Find",
                source_find_id=find_id,
                event_ids=linked_event_ids,
            )

    seen_receipts: set[tuple[str, str]] = set()
    for receipt in tuple(getattr(summary, "reward_receipts", ()) or ()):
        if str(getattr(receipt, "reward_type", "") or "") != "inventory_item":
            continue
        item_id = str(getattr(receipt, "item_id", "") or "")
        amount = max(0, int(getattr(receipt, "amount", 0) or 0))
        source = str(getattr(receipt, "source", "") or "")
        event_key = str(getattr(receipt, "event_key", "") or "")
        correlation_id = str(getattr(receipt, "correlation_id", "") or "")
        source_id = str(getattr(receipt, "source_id", "") or "")
        stable_event_identity = event_key or ":".join(
            value for value in (correlation_id, source, source_id) if value
        )
        receipt_identity = (stable_event_identity, item_id)
        if receipt_identity in seen_receipts:
            continue
        seen_receipts.add(receipt_identity)
        if (
            (source in STANDARD_FIND_RECEIPT_SOURCES
             or source.replace("-", "_").casefold().startswith("garden_find"))
            and item_id in represented_find_item_ids
        ):
            continue
        if find_event_ids.intersection({event_key, correlation_id, source_id}):
            continue
        projected = session_inventory_reward_lines((receipt,))
        learner_text = projected[0][2] if projected else ""
        prefix = f"+{amount:,} "
        name = (
            learner_text[len(prefix):]
            if learner_text.startswith(prefix)
            else str(getattr(receipt, "title", "") or "")
        )
        add(
            item_id=item_id,
            name=name,
            art_reference=item_id,
            quantity=amount,
            source_label=_session_item_source_label(source, source_id),
            event_ids=(event_key or correlation_id,),
        )

    return tuple(
        SessionEarnedItem(
            item_id=item_id,
            name=str(grouped[item_id]["name"]),
            art_reference=str(grouped[item_id]["art_reference"]),
            quantity=max(0, int(grouped[item_id]["quantity"])),
            source_labels=tuple(grouped[item_id]["source_labels"]),
            source_find_ids=tuple(grouped[item_id]["source_find_ids"]),
            event_ids=tuple(grouped[item_id]["event_ids"]),
        )
        for item_id in order
    )


def _session_project_status_text(project: Any) -> str:
    """Keep only learner-facing state from an engine-owned project status."""

    status_copy = str(getattr(project, "status_copy", "") or "")
    if status_copy.casefold().startswith((
        "reward ready",
        "in progress",
        "completed",
        "not started",
    )):
        return status_copy
    status = str(getattr(project, "status", "") or "")
    normalized = status.casefold()
    if "ready to claim" in normalized or "claimable" in normalized:
        return "Reward ready"
    if "claimed" in normalized or "complete" in normalized:
        return "Completed"
    if "funded" in normalized or "active" in normalized:
        return "In progress"
    return ""


def session_find_summary_plan(
    find_items: Sequence[tuple[str, str, str, int]],
    *,
    visible_limit: int = 3,
) -> tuple[tuple[tuple[str, str, str, int], ...], int]:
    """Keep up to three reconciled Find groups visible and account for the rest."""

    normalized = tuple(find_items)
    limit = max(1, int(visible_limit))
    visible = normalized[:limit]
    hidden_quantity = sum(
        max(0, int(item[3])) for item in normalized[len(visible):]
    )
    return visible, hidden_quantity


try:  # Keep the geometry helper importable in non-Anki test processes.
    from aqt.qt import (
        QColor,
        QApplication,
        QEasingCurve,
        QEvent,
        QFrame,
        QGraphicsDropShadowEffect,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QLabel,
        QPainter,
        QPixmap,
        QProgressBar,
        QPropertyAnimation,
        QPushButton,
        QRectF,
        QScrollArea,
        QSize,
        QSizePolicy,
        QToolButton,
        QTimer,
        QVBoxLayout,
        Qt,
    )

    _QT_AVAILABLE = True
    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only outside Anki/Qt.
    QColor = object  # type: ignore[assignment,misc]
    QApplication = object  # type: ignore[assignment,misc]
    QEasingCurve = object  # type: ignore[assignment,misc]
    QEvent = object  # type: ignore[assignment,misc]
    QFrame = object  # type: ignore[assignment,misc]
    QGraphicsDropShadowEffect = object  # type: ignore[assignment,misc]
    QGraphicsOpacityEffect = object  # type: ignore[assignment,misc]
    QHBoxLayout = object  # type: ignore[assignment,misc]
    QLabel = object  # type: ignore[assignment,misc]
    QPainter = object  # type: ignore[assignment,misc]
    QPixmap = object  # type: ignore[assignment,misc]
    QProgressBar = object  # type: ignore[assignment,misc]
    QPropertyAnimation = object  # type: ignore[assignment,misc]
    QPushButton = object  # type: ignore[assignment,misc]
    QRectF = object  # type: ignore[assignment,misc]
    QScrollArea = object  # type: ignore[assignment,misc]
    QSize = object  # type: ignore[assignment,misc]
    QSizePolicy = object  # type: ignore[assignment,misc]
    QToolButton = object  # type: ignore[assignment,misc]
    QTimer = object  # type: ignore[assignment,misc]
    QVBoxLayout = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    _QT_AVAILABLE = False
    _QT_IMPORT_ERROR = exc

try:  # QtSvg is optional in a few export-only test processes.
    from aqt.qt import QSvgRenderer
except Exception:  # pragma: no cover - host export variance.
    try:
        from PyQt6.QtSvg import QSvgRenderer  # type: ignore[no-redef]
    except Exception:  # pragma: no cover
        try:
            from PyQt5.QtSvg import QSvgRenderer  # type: ignore[no-redef]
        except Exception:  # pragma: no cover
            QSvgRenderer = None  # type: ignore[assignment]


def _require_qt() -> None:
    if not _QT_AVAILABLE:
        raise RuntimeError(
            "SessionSummaryCard requires Anki's Qt runtime"
        ) from _QT_IMPORT_ERROR


def _host_background_lightness(parent: Any) -> int | None:
    candidates = [parent]
    try:
        app = QApplication.instance()
        if app is not None:
            candidates.append(app)
    except Exception:
        pass
    for candidate in candidates:
        try:
            palette = candidate.palette()
            background_role = getattr(candidate, "backgroundRole", None)
            if callable(background_role):
                return int(palette.color(background_role()).lightness())
            return int(palette.window().color().lightness())
        except Exception:
            continue
    return None


def _title_case(value: str) -> str:
    normalized = str(value or "").replace("_", " ").strip()
    if normalized.casefold() == "rare":
        return "Full Bloom"
    return normalized.title()


def _source_pixmap(asset: Any) -> Any:
    """Load raster or SVG source art without substituting semantic glyphs."""

    path = Path(str(asset or ""))
    if not path.exists():
        return QPixmap()
    if path.suffix.casefold() != ".svg":
        return QPixmap(str(path))
    if QSvgRenderer is None:
        return QPixmap()
    try:
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return QPixmap()
        default_size = renderer.defaultSize()
        width = max(1, int(default_size.width()))
        height = max(1, int(default_size.height()))
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            renderer.render(painter, QRectF(0, 0, width, height))
        finally:
            painter.end()
        return pixmap
    except Exception:
        return QPixmap()


def _alpha_bounded_thumbnail(source: Any, size: int) -> Any:
    """Return a padded, alpha-bounded plant thumbnail at Retina resolution."""

    if source.isNull():
        return QPixmap()
    logical_size = max(1, int(size))
    crop = source
    try:
        bounds = source.mask().boundingRect()
        if bounds.isValid() and bounds.width() > 0 and bounds.height() > 0:
            padding = max(2, round(max(bounds.width(), bounds.height()) * 0.08))
            left = max(0, bounds.x() - padding)
            top = max(0, bounds.y() - padding)
            right = min(source.width(), bounds.x() + bounds.width() + padding)
            bottom = min(source.height(), bounds.y() + bounds.height() + padding)
            crop = source.copy(left, top, max(1, right - left), max(1, bottom - top))
    except Exception:
        crop = source
    physical = logical_size * 2
    scaled = crop.scaled(
        physical,
        physical,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(physical, physical)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(
            (physical - scaled.width()) // 2,
            (physical - scaled.height()) // 2,
            scaled,
        )
    finally:
        painter.end()
    result.setDevicePixelRatio(2.0)
    return result


class _WrappedNameLabel(QLabel):  # type: ignore[misc,valid-type]
    """A full-copy label that grows with wrapped text instead of truncating."""

    def __init__(self, text: str) -> None:
        super().__init__(str(text or ""))
        self._full_text = str(text or "")
        self.setAccessibleName(self._full_text)
        self.setWordWrap(True)
        self.setProperty("summaryTwoLineName", True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)


class SessionSummaryCard(QFrame):  # type: ignore[misc,valid-type]
    """A focus-safe child card for one finalized Session Summary payload."""

    def __init__(
        self,
        parent: Any,
        payload: SessionSummaryPayload,
        on_dismiss: Callable[[], None] | None = None,
        on_open_garden: Callable[[], None] | None = None,
        on_continue_reviews: Callable[[], bool] | None = None,
        engine: Any | None = None,
        animations_enabled: bool | None = None,
    ) -> None:
        _require_qt()
        if parent is None:
            raise ValueError("SessionSummaryCard requires a parent widget")
        if not isinstance(payload, SessionSummaryPayload):
            raise TypeError("payload must be a SessionSummaryPayload")
        if not payload.segments:
            raise ValueError("SessionSummaryPayload must contain a day segment")

        super().__init__(parent)
        self._payload = payload
        self._on_dismiss = on_dismiss
        self._on_open_garden = on_open_garden
        self._on_continue_reviews = on_continue_reviews
        self._engine = engine
        self._animations_enabled = (
            bool(animations_enabled)
            if animations_enabled is not None
            else read_system_reduced_motion() is not True
        )
        self._animation_started = False
        self._animations: list[Any] = []
        self._dismissed = False
        self._page_index = 0
        self._details_expanded = True
        self._progress_details_expanded = False
        self._show_all_growth = True
        self._exclusion_top: int | None = None
        self._exclusion_source = "none"
        self._reserved_top: int | None = None
        self._reserved_top_source = "none"
        self._boost_rows: dict[str, tuple[Any, Any, Any, Any | None]] = {}
        self._active_boosts_section: Any | None = None
        self._compact_density = session_summary_uses_compact_density(
            int(parent.height())
        )
        self._summary_theme = session_summary_palette(
            _host_background_lightness(parent)
        )
        self._filtered_parent = parent

        self.setObjectName("ankiGardenSessionSummary")
        self.setProperty("semanticId", "reviewer.session-summary")
        self.setProperty("reviewerOverlay", True)
        self.setProperty("summaryNonmodal", True)
        self.setProperty("summaryCompactDensity", self._compact_density)
        self.setProperty("summaryExclusionTop", None)
        self.setProperty("summaryExclusionSource", "none")
        self.setProperty("summaryExclusionApplied", False)
        self.setProperty("summaryHomeClearanceBottom", None)
        self.setProperty("summaryHomeClearanceSource", "none")
        self.setProperty("summaryHomeClearanceApplied", False)
        self.setProperty("summaryHomeClearanceTracking", False)
        self.setProperty("summaryHomeClearanceMeasured", False)
        self.setProperty("summaryHomeClearanceHorizontalOverlap", False)
        self.setProperty("summaryHomeClearanceTelemetry", {})
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Anki Garden Session Summary")
        self.setMinimumWidth(1)
        self.setMaximumWidth(SESSION_SUMMARY_MAX_WIDTH)

        self._apply_style()
        self._build_shell()
        self._apply_shell_density()
        self._rebuild_page()
        self.reposition()
        try:
            parent.installEventFilter(self)
        except Exception:
            self._filtered_parent = None

    @property
    def widget(self) -> Any:
        """Compatibility handle for owners that store renderer wrappers."""

        return self

    @property
    def payload(self) -> SessionSummaryPayload:
        return self._payload

    @property
    def page_index(self) -> int:
        return self._page_index

    def set_callbacks(
        self,
        *,
        on_dismiss: Callable[[], None] | None = None,
        on_open_garden: Callable[[], None] | None = None,
        on_continue_reviews: Callable[[], bool] | None = None,
    ) -> None:
        self._on_dismiss = on_dismiss
        self._on_open_garden = on_open_garden
        self._on_continue_reviews = on_continue_reviews

    def set_exclusion_top(
        self,
        exclusion_top: int | None,
        *,
        source: str = "host",
    ) -> tuple[int, int, int, int]:
        """Apply a measured lower-control boundary without scanning host UI."""

        if exclusion_top is None:
            self._exclusion_top = None
            self._exclusion_source = "none"
        else:
            try:
                self._exclusion_top = max(1, int(exclusion_top))
            except (TypeError, ValueError):
                self._exclusion_top = None
            self._exclusion_source = (
                str(source or "host")
                if self._exclusion_top is not None
                else "none"
            )
        return self.reposition()

    def set_reserved_top(
        self,
        reserved_top: int | None,
        *,
        source: str = "host",
    ) -> tuple[int, int, int, int]:
        """Reserve measured upper host content before positioning the card."""

        if reserved_top is None:
            self._reserved_top = None
            self._reserved_top_source = "none"
        else:
            try:
                self._reserved_top = max(0, int(reserved_top))
            except (TypeError, ValueError):
                self._reserved_top = None
            self._reserved_top_source = (
                str(source or "host")
                if self._reserved_top is not None
                else "none"
            )
        return self.reposition()

    def _apply_style(self) -> None:
        t = self._summary_theme
        self.setStyleSheet(
            "QFrame#ankiGardenSessionSummary {"
            f"background:{t['elevated_surface']};"
            f"border:1px solid {t['strong_border']};"
            "border-radius:16px;}"
            "QFrame#ankiGardenSessionHeader,"
            "QFrame#ankiGardenSessionFooter,"
            "QFrame#ankiGardenSessionBody {background:transparent;border:0;}"
            "QFrame[summaryDivider='true'] {"
            f"background:{t['divider']};border:0;min-height:1px;max-height:1px;}}"
            "QFrame[summaryStatus='true'] {"
            f"background:{t['today_surface']};border:0;border-radius:12px;}}"
            "QFrame[summaryStatus='true'][summaryComplete='true'] {"
            f"background:{t['selected_surface']};}}"
            "QFrame[summaryHighlight='true'] {"
            f"background:{t['highlight_surface']};"
            f"border:1px solid {t['subtle_border']};border-radius:12px;}}"
            "QFrame[summaryHighlight='true'][summaryHighlightKind='full_bloom'] {"
            f"border-left:3px solid {t['milestone_accent']};}}"
            "QFrame[summaryHighlightCompact='true'] {"
            "background:transparent;border:0;border-radius:0;}"
            "QFrame[summaryMediaRail='true'], QFrame[summaryMetric='true'] {"
            "background:transparent;border:0;border-radius:0;}"
            "QFrame[summaryRewardCard='true'] {"
            "background:transparent;border:0;"
            "border-radius:12px;}"
            "QFrame[summaryBoostCard='true'] {"
            f"background:{t['boost_surface']};border:1px solid {t['subtle_border']};"
            "border-radius:12px;}"
            "QFrame[summaryCoinChip='true'] {"
            f"background:{t['chip_surface']};border:0;border-radius:12px;}}"
            "QFrame[summaryMetricDivider='true'] {"
            f"background:{t['divider']};border:0;min-width:1px;max-width:1px;}}"
            "QFrame[summaryBoostRow='true'] {background:transparent;border:0;}"
            "QFrame[summaryBreakdownPanel='true'] {background:transparent;border:0;}"
            f"QLabel {{color:{t['text_primary']};font-size:13px;"
            "font-family:-apple-system, BlinkMacSystemFont, 'SF Pro Text', "
            "'Helvetica Neue', sans-serif;}"
            "QLabel[summaryTitle='true'] {font-size:20px;font-weight:600;}"
            "QLabel[summaryHero='true'] {font-size:40px;font-weight:700;}"
            "QLabel[summaryHeroLabel='true'] {"
            f"color:{t['text_secondary']};font-size:14px;font-weight:520;}}"
            "QLabel[summarySection='true'] {"
            f"color:{t['text_secondary']};font-size:12px;font-weight:650;}}"
            "QLabel[summaryValue='true'] {font-size:13px;font-weight:650;}"
            "QLabel[summaryGrowth='true'] {"
            f"color:{t['growth_accent']};font-size:20px;font-weight:700;}}"
            "QLabel[summaryCoin='true'] {"
            f"color:{t['coin_accent']};font-size:20px;font-weight:700;}}"
            "QLabel[summaryDetailGrowth='true'] {"
            f"color:{t['growth_accent']};font-size:13px;font-weight:650;}}"
            "QLabel[summaryDetailCoin='true'] {"
            f"color:{t['coin_accent']};font-size:13px;font-weight:650;}}"
            "QLabel[summaryCoinChipValue='true'] {"
            f"color:{t['coin_accent']};font-size:12px;font-weight:600;}}"
            "QLabel[summaryMuted='true'] {"
            f"color:{t['text_muted']};font-size:12px;font-weight:500;}}"
            "QLabel[summaryMetricLabel='true'] {"
            f"color:{t['metric_label']};font-size:12px;font-weight:520;}}"
            "QLabel[summarySupporting='true'] {"
            f"color:{t['text_secondary']};font-size:12px;font-weight:500;}}"
            "QLabel[summaryStatusTitle='true'] {font-size:14px;font-weight:600;}"
            "QLabel[summaryMilestone='true'] {font-size:15px;font-weight:650;}"
            "QLabel[summaryEyebrow='true'] {font-size:12px;font-weight:700;}"
            "QLabel[summaryFind='true'] {"
            f"color:{t['find_accent']};font-size:20px;font-weight:700;}}"
            "QLabel[summaryLongMetric='true'] {font-size:17px;}"
            "QLabel[summaryRarity='true'] {"
            f"color:{t['text_secondary']};font-size:12px;font-weight:650;}}"
            "QLabel[summarySourceBadge='true'] {"
            f"color:{t['find_accent']};background:{t['chip_surface']};"
            "border:0;border-radius:7px;padding:2px 6px;font-size:12px;font-weight:650;}"
            "QLabel[summaryFindName='true'] {font-size:13px;font-weight:580;}"
            "QLabel[summaryBoostName='true'] {font-size:13px;font-weight:550;}"
            "QLabel[summaryFindQuantity='true'], QLabel[summaryBoostValue='true'] {"
            "font-size:13px;font-weight:650;}"
            "QProgressBar#ankiGardenSessionTodayProgress {"
            f"background:{t['progress_track']};border:0;border-radius:3px;"
            "min-height:6px;max-height:6px;text-align:center;}"
            "QProgressBar#ankiGardenSessionTodayProgress::chunk {"
            f"background:{t['growth_accent']};border-radius:3px;}}"
            "QPushButton, QToolButton {"
            f"color:{t['text_primary']};background:transparent;border:0;"
            "border-radius:9px;padding:6px 14px;font-size:13px;font-weight:650;}"
            "QPushButton:hover, QToolButton:hover {"
            f"background:{t['selected_surface']};}}"
            "QPushButton:pressed, QToolButton:pressed {"
            f"background:{t['strong_border']};}}"
            "QPushButton[summaryPrimary='true'] {"
            f"color:{t['action_text']};background:{t['action_accent']};}}"
            "QPushButton[summaryPrimary='true']:hover {"
            f"background:{t['action_hover']};}}"
            "QPushButton[summaryPrimary='true']:pressed {"
            f"background:{t['action_pressed']};}}"
            "QPushButton[summarySecondary='true'] {"
            f"background:{t['secondary_action']};"
            f"border:1px solid {t['secondary_border']};}}"
            "QPushButton[summarySecondary='true']:pressed {"
            f"background:{t['selected_surface']};border:1px solid {t['strong_border']};}}"
            "QPushButton#ankiGardenSessionClose,"
            "QToolButton#ankiGardenSessionPreviousDay,"
            "QToolButton#ankiGardenSessionNextDay {padding:0;}"
            "QLabel[summaryEnvironmentArt='true'] {"
            "background:transparent;border:0;"
            "border-radius:8px;}"
            "QScrollArea#ankiGardenSessionScroll {background:transparent;border:0;}"
            "QScrollArea#ankiGardenSessionScroll > QWidget > QWidget {"
            "background:transparent;}"
            "QScrollBar:vertical {background:transparent;width:6px;margin:2px 0;}"
            "QScrollBar::handle:vertical {"
            f"background:{t['strong_border']};border-radius:3px;min-height:28px;}}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}"
        )

        try:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(26)
            shadow.setOffset(0, 8)
            shadow.setColor(QColor(t["plant_popover_shadow"]))
            self.setGraphicsEffect(shadow)
        except Exception:
            pass

    def _build_shell(self) -> None:
        shell = build_receipt_shell(self, "Session summary", self.close, self._summary_theme, prefix="ankiGardenSession")
        self._header, self._close_button = shell.header, shell.close
        self._scroll, self._footer, self._footer_layout = shell.scroll, shell.footer, shell.actions
        self._scroll.setObjectName("ankiGardenSessionScroll")
        self._summary_fixed = QFrame(self)
        self._summary_fixed.setObjectName("ankiGardenSessionPinnedSummary")
        self._summary_fixed.setProperty("summaryPinned", True)
        self._summary_fixed_layout = QVBoxLayout(self._summary_fixed)
        self._summary_fixed_layout.setContentsMargins(16, 8, 16, 8)
        self._summary_fixed_layout.setSpacing(10)
        self.layout().insertWidget(1, self._summary_fixed)
        self.setStyleSheet(self.styleSheet() + receipt_style(self._summary_theme))

    def _apply_shell_density(self) -> None:
        """Tighten only fixed shell chrome in measured short host viewports."""

        if self._compact_density:
            self._header.setFixedHeight(44)
            self._header.layout().setContentsMargins(16, 6, 16, 6)
            self._footer.setFixedHeight(48)
            self._footer_layout.setContentsMargins(12, 4, 12, 4)
            return
        self._header.setFixedHeight(SESSION_SUMMARY_HEADER_HEIGHT)
        self._header.layout().setContentsMargins(16, 7, 16, 7)
        self._footer.setFixedHeight(SESSION_SUMMARY_FOOTER_HEIGHT)
        self._footer_layout.setContentsMargins(16, 8, 16, 8)

    def _divider(self, parent: Any | None = None) -> Any:
        divider = QFrame(parent or self)
        divider.setProperty("summaryDivider", True)
        divider.setFixedHeight(1)
        divider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return divider

    @staticmethod
    def _clear_layout(layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            child_layout = item.layout()
            if child is not None:
                child.hide()
                child.deleteLater()
            elif child_layout is not None:
                SessionSummaryCard._clear_layout(child_layout)

    def _current_summary(self) -> SessionDaySummary:
        return self._payload.segments[self._page_index]

    def _reset_page_expansions(self) -> None:
        self._details_expanded = True
        self._progress_details_expanded = False
        self._show_all_growth = True

    def _rebuild_page(self) -> None:
        summary = self._current_summary()
        projection = project_session_day(summary)
        try:
            scroll_position = int(self._scroll.verticalScrollBar().value())
        except Exception:
            scroll_position = 0
        body = QFrame()
        body.setObjectName("ankiGardenSessionBody")
        body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            16,
            8 if self._compact_density else 14,
            16,
            8 if self._compact_density else 14,
        )
        # Rewards and plant journeys share one feed beneath the pinned totals.
        body_layout.setSpacing(8)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._clear_layout(self._summary_fixed_layout)
        if self._payload.page_count > 1:
            self._add_pager(self._summary_fixed_layout)

        self._active_boosts_section = None
        metrics = self._reward_metrics(summary, projection)
        inventory_rewards = self._inventory_rewards(summary)
        self.setProperty(
            "summaryRewardMetricOrder",
            [str(metric[0]) for metric in metrics],
        )
        self.setProperty(
            "summaryVisibleItemRewardCount", len(inventory_rewards)
        )
        self.setProperty(
            "summaryLandmarkGrowthUnits",
            max(
                0,
                int(getattr(summary, "landmark_growth_delta_units", 0) or 0),
            ),
        )
        self.setProperty(
            "summaryProjectGrowthUnits",
            max(0, int(getattr(summary, "project_growth_total_units", 0) or 0)),
        )
        self.setProperty(
            "summaryProjectAllocationCount",
            len(tuple(getattr(summary, "project_allocations", ()) or ())),
        )
        self.setProperty("summaryProjectProgressPlacement", "headline")
        self._add_hero(self._summary_fixed_layout, projection)
        self._add_reward_strip(self._summary_fixed_layout, metrics)
        self._summary_fixed_layout.addWidget(self._divider())
        # Rebuilding a visible receipt must make the replacement totals
        # measurable before its pinned region is resized.
        for index in range(self._summary_fixed_layout.count()):
            widget = self._summary_fixed_layout.itemAt(index).widget()
            if widget is not None:
                widget.show()
        self._summary_fixed_layout.activate()
        if self._has_highlights(summary, projection):
            self._add_highlights(body_layout, summary, projection)
        if inventory_rewards or self._find_items(summary):
            self._add_rewards_earned(
                body_layout,
                summary,
                projection,
                (),
                inventory_rewards,
            )

        self._add_plant_progress(body_layout, summary)
        active_effects = self._active_effects_for_payload(projection)
        if self._has_breakdown(summary, projection) or active_effects:
            self._add_breakdown(body_layout, summary, projection, active_effects=active_effects)

        self.setProperty("summaryDetailsAlwaysVisible", False)
        self.setProperty("summaryDailyCardsRemoved", True)
        self._body = body
        self._scroll.setWidget(body)
        try:
            self._scroll.verticalScrollBar().setValue(scroll_position)
        except Exception:
            pass
        terminal_today = getattr(self._payload, "terminal_today_cards", None)
        continue_available = bool(
            getattr(terminal_today, "can_continue_reviews", False)
            if terminal_today is not None
            else getattr(projection, "continue_reviews_available", False)
        )
        today_complete = bool(
            str(getattr(terminal_today, "status", "") or "") == "complete"
            if terminal_today is not None
            else getattr(getattr(projection, "today_cards", None), "is_complete", False)
        )
        self._rebuild_footer(
            bool(getattr(projection, "open_garden_available", True)),
            bool(
                continue_available
                and callable(self._on_continue_reviews)
            ),
            today_complete,
        )
        self.reposition()

    def _add_pager(self, layout: Any) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(6)
        label = QLabel(
            f"Anki day {self._page_index + 1} of {self._payload.page_count}"
        )
        label.setProperty("summaryMuted", True)
        row.addWidget(label, 1)

        previous = QToolButton()
        previous.setObjectName("ankiGardenSessionPreviousDay")
        previous.setIcon(
            garden_icon("chevron-left", color=self._summary_theme["text_secondary"])
        )
        previous.setIconSize(QSize(16, 16))
        previous.setFixedSize(28, 28)
        previous.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        previous.setCursor(Qt.CursorShape.PointingHandCursor)
        previous.setAccessibleName("Previous Anki day")
        previous.setEnabled(self._page_index > 0)
        previous.clicked.connect(lambda: self._set_page(self._page_index - 1))
        row.addWidget(previous)

        following = QToolButton()
        following.setObjectName("ankiGardenSessionNextDay")
        following.setIcon(
            garden_icon("chevron-right", color=self._summary_theme["text_secondary"])
        )
        following.setIconSize(QSize(16, 16))
        following.setFixedSize(28, 28)
        following.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        following.setCursor(Qt.CursorShape.PointingHandCursor)
        following.setAccessibleName("Next Anki day")
        following.setEnabled(self._page_index + 1 < self._payload.page_count)
        following.clicked.connect(lambda: self._set_page(self._page_index + 1))
        row.addWidget(following)
        layout.addLayout(row)

    def _set_page(self, index: int) -> None:
        normalized = max(0, min(self._payload.page_count - 1, int(index)))
        if normalized == self._page_index:
            return
        self._page_index = normalized
        self._reset_page_expansions()
        self._rebuild_page()

    def _add_hero(self, layout: Any, projection: Any) -> None:
        count = self._current_summary().cards_completed
        hero = QLabel(cards_studied_text(count) + " this session")
        hero.setWordWrap(True)
        hero.setObjectName("ankiGardenSessionHeroValue")
        hero.setProperty("receiptEventTitle", True)
        hero.setToolTip("Study answers in this session; a card may be studied more than once.")
        apply_tabular_numerals(hero)
        layout.addWidget(hero)

    def _section_heading(self, text: str) -> Any:
        from .reward_receipt import receipt_section_heading
        return receipt_section_heading(self, str(text or ""))

    @staticmethod
    def _has_highlights(summary: SessionDaySummary, projection: Any) -> bool:
        projected = getattr(projection, "highlights", None)
        if projected is not None:
            return bool(
                any(
                    str(getattr(item, "kind", "") or "") != "minor_checkpoint"
                    for item in (
                        *tuple(getattr(projected, "featured", ()) or ()),
                        *tuple(getattr(projected, "overflow", ()) or ()),
                    )
                )
            )
        return bool(
            summary.milestones
            or summary.environment_discoveries
            or any(
                bool(
                    getattr(
                        item,
                        "notable",
                        False,
                    )
                )
                for item in summary.standard_finds
            )
        )

    @staticmethod
    def _fallback_highlights(summary: SessionDaySummary) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        records: list[Any] = []
        for milestone_type in ("full_bloom",):
            records.extend(
                item for item in summary.milestones
                if item.milestone_type == milestone_type
            )
        records.extend(summary.environment_discoveries)
        for milestone_type in ("stage_change", "checkpoint"):
            records.extend(
                item for item in summary.milestones
                if item.milestone_type == milestone_type
            )
        records.extend(
            item for item in summary.standard_finds
            if bool(
                getattr(
                    item,
                    "notable",
                    False,
                )
            )
        )
        return tuple(records[:2]), tuple(records[2:])

    def _highlight_source(
        self,
        summary: SessionDaySummary,
        highlight: Any,
    ) -> Any:
        if isinstance(highlight, (PlantMilestone, EnvironmentDiscovery, StandardFind)):
            return highlight
        event_id = str(getattr(highlight, "event_id", "") or "")
        for record in (
            *summary.milestones,
            *summary.environment_discoveries,
            *summary.standard_finds,
        ):
            if str(getattr(record, "event_id", "") or "") == event_id:
                return record
        return highlight

    @staticmethod
    def _highlight_kind(highlight: Any) -> str:
        kind = str(getattr(highlight, "kind", "") or "")
        if kind:
            return kind
        if isinstance(highlight, PlantMilestone):
            if highlight.milestone_type == "checkpoint":
                return "major_checkpoint"
            return highlight.milestone_type
        if isinstance(highlight, EnvironmentDiscovery):
            return "environment"
        return "rare_reward"

    def _highlight_copy(
        self,
        highlight: Any,
        source: Any,
        *,
        displayed_coin_total: int = 0,
    ) -> tuple[str, str, str, str]:
        kind = self._highlight_kind(highlight)
        eyebrow = str(getattr(highlight, "eyebrow", "") or "")
        title = str(getattr(highlight, "title", "") or "")
        supporting = str(getattr(highlight, "supporting_text", "") or "")
        reward = str(getattr(highlight, "reward_text", "") or "")
        if isinstance(source, PlantMilestone):
            eyebrow = ""
            title = plant_stage_event(
                source.plant_class,
                "rare" if kind == "full_bloom" else source.new_stage,
                checkpoint_percent=source.checkpoint_percent if source.milestone_type == "checkpoint" else 0,
            )
            supporting = ""
            reward = ""
        elif isinstance(source, EnvironmentDiscovery):
            unlock_eyebrow, unlock_supporting = unlock_category_copy(
                str(getattr(source, "unlock_category", "") or "environment")
            )
            eyebrow = "New discovery"
            title = str(source.environment_name or "Garden discovery")
            supporting = ""
        elif isinstance(source, StandardFind):
            eyebrow = "Garden Find"
            title = title or source.find_name or "Garden Find"
            supporting = supporting or source.reward_label
        return eyebrow, title, supporting, reward

    def _add_highlights(self, layout: Any, summary: SessionDaySummary, projection: Any) -> None:
        container = QFrame()
        container.setObjectName("ankiGardenSessionHighlights")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)


        projected = getattr(projection, "highlights", None)
        if projected is not None:
            candidates = tuple(
                item
                for item in (
                    *tuple(getattr(projected, "featured", ()) or ()),
                    *tuple(getattr(projected, "overflow", ()) or ()),
                )
                if str(getattr(item, "kind", "") or "") != "minor_checkpoint"
            )
            featured = candidates[:2]
        else:
            featured, overflow = self._fallback_highlights(summary)
            candidates = (*featured, *overflow)
        represented_find_ids = {row[0] for row in self._find_items(summary)}
        represented_find_ids.update(find_id for item in self._inventory_rewards(summary) for find_id in item.source_find_ids)
        candidates = tuple(item for item in candidates
                           if not isinstance(self._highlight_source(summary, item), StandardFind)
                           or self._highlight_source(summary, item).find_id not in represented_find_ids)
        candidates = tuple(item for item in candidates
                           if not isinstance(self._highlight_source(summary, item), PlantMilestone)
                           or self._highlight_kind(item) == "full_bloom")
        progress_ids = {item.plant_id for item in (*summary.plant_growth_by_plant, *summary.shared_growth_by_plant)}
        candidates = tuple(item for item in candidates
                           if not isinstance(self._highlight_source(summary, item), PlantMilestone)
                           or self._highlight_source(summary, item).plant_id not in progress_ids)
        featured = candidates[:2]
        if not candidates:
            container.deleteLater()
            return
        for heading, grouped in (
            ("New discoveries", tuple(item for item in candidates if isinstance(self._highlight_source(summary, item), EnvironmentDiscovery))),
            ("Plant progress", tuple(item for item in candidates if isinstance(self._highlight_source(summary, item), PlantMilestone))),
            ("Other rewards", tuple(item for item in candidates if not isinstance(self._highlight_source(summary, item), (EnvironmentDiscovery, PlantMilestone)))),
        ):
            if grouped:
                container_layout.addWidget(self._section_heading(heading))
                for highlight in grouped:
                    self._add_compact_highlight_row(container_layout, summary, highlight)
        layout.addWidget(container)

    def _add_compact_highlight_row(self, layout: Any, summary: SessionDaySummary, highlight: Any) -> None:
        source = self._highlight_source(summary, highlight)
        kind = self._highlight_kind(highlight)
        eyebrow, title, supporting, reward = self._highlight_copy(highlight, source, displayed_coin_total=summary.garden_coins_total)
        if isinstance(source, PlantMilestone):
            art = self._plant_art_label(source, 44)
        elif isinstance(source, EnvironmentDiscovery):
            art = self._environment_art_label(source, 44, 44)
        else:
            art = self._reward_art_label(source, 44)
        detail = supporting
        if reward and self._details_expanded:
            detail = "\n".join(filter(None, (supporting, reward)))
        category = ("Checkpoint" if source.milestone_type == "checkpoint" else "Growth milestone") if isinstance(source, PlantMilestone) else eyebrow if isinstance(source, (EnvironmentDiscovery, StandardFind)) else ""
        event = receipt_event_row(self, art, title, detail=detail, milestone=kind == "full_bloom", reward=source,
                                  eyebrow=category,
                                  rarity_badge=kind == "full_bloom" or isinstance(source, (EnvironmentDiscovery, StandardFind)))
        event.widget.setProperty("summaryHighlight", True)
        event.widget.setProperty("summaryHighlightKind", kind)
        event.widget.setProperty("summaryHighlightCompact", True)
        event.widget.setProperty("summaryStatic", True)
        layout.addWidget(event.widget)

    def _add_highlight_card(
        self,
        layout: Any,
        summary: SessionDaySummary,
        highlight: Any,
    ) -> None:
        source = self._highlight_source(summary, highlight)
        kind = self._highlight_kind(highlight)
        eyebrow_text, title_text, supporting_text, reward_text = self._highlight_copy(
            highlight,
            source,
            displayed_coin_total=summary.garden_coins_total,
        )
        card = QFrame()
        card.setProperty("summaryHighlight", True)
        card.setProperty("summaryHighlightKind", kind)
        card.setProperty("summaryStatic", True)
        card.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        card.setAccessibleName(
            ". ".join(part for part in (eyebrow_text, title_text, supporting_text, reward_text) if part)
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(
            12,
            4 if self._compact_density else 8,
            12,
            4 if self._compact_density else 8,
        )
        row.setSpacing(12)

        source_unlock_category = str(
            getattr(source, "unlock_category", "")
            or getattr(highlight, "unlock_category", "")
            or ""
        )
        source_environment_kind = str(
            getattr(source, "environment_kind", "") or ""
        )
        garden_item = bool(
            source_unlock_category == "garden_item"
            or (
                not source_unlock_category
                and source_environment_kind in {"garden_feature", "weather"}
            )
        )
        if isinstance(source, EnvironmentDiscovery) or kind == "environment":
            art = self._environment_art_label(
                source,
                58 if garden_item else 88,
                58 if garden_item else 56,
            )
        elif isinstance(source, PlantMilestone) or kind in {
            "full_bloom", "stage_change", "major_checkpoint", "minor_checkpoint"
        }:
            art = self._plant_art_label(source, 60 if kind == "full_bloom" else 52)
        else:
            art = self._reward_art_label(source, 48)
        # Rarity stays on the title and indicator; keep the item art clear.
        media_rail = QFrame(card)
        media_rail.setProperty("summaryMediaRail", True)
        media_rail.setFixedWidth(88)
        media_layout = QHBoxLayout(media_rail)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(0)
        media_layout.addWidget(art, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(media_rail, 0, Qt.AlignmentFlag.AlignVCenter)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        eyebrow = QLabel(eyebrow_text)
        eyebrow.setProperty("summaryEyebrow", True)
        if kind == "full_bloom":
            eyebrow.setStyleSheet(f"color:{self._summary_theme['milestone_accent']};")
        title = self._name_label(title_text)
        title.setProperty("summaryMilestone", True)

        def reward_chip() -> Any:
            chip = QFrame()
            chip.setProperty("summaryCoinChip", True)
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 2, 8, 2)
            chip_layout.setSpacing(0)
            reward = QLabel(reward_text)
            reward.setProperty("summaryCoinChipValue", True)
            apply_tabular_numerals(reward)
            chip_layout.addWidget(reward)
            chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            chip.setMinimumHeight(22)
            return chip

        compact_reward_chip = bool(reward_text and len(reward_text) <= 24)
        if compact_reward_chip:
            eyebrow_row = QHBoxLayout()
            eyebrow_row.setSpacing(8)
            eyebrow_row.addWidget(eyebrow, 1, Qt.AlignmentFlag.AlignVCenter)
            eyebrow_row.addWidget(
                reward_chip(),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
            copy.addLayout(eyebrow_row)
        else:
            copy.addWidget(eyebrow)
        copy.addWidget(title)
        supporting = QLabel(supporting_text)
        supporting.setWordWrap(True)
        supporting.setProperty("summarySupporting", True)
        copy.addWidget(supporting)
        if reward_text and not compact_reward_chip:
            copy.addWidget(reward_chip(), 0, Qt.AlignmentFlag.AlignLeft)
        row.addLayout(copy, 1)
        treatment = apply_reward_treatment(card, source, title=title, artwork=art, full_bloom=kind == "full_bloom")
        if treatment.notable:
            eyebrow.setStyleSheet(f"color:{treatment.color};")
        layout.addWidget(card)

    @staticmethod
    def _reward_metrics(summary: SessionDaySummary, projection: Any) -> tuple[tuple[str, str, str, str], ...]:
        applied = int(
            getattr(
                projection,
                "growth_applied_total_units",
                summary.plant_growth_total_units
                + summary.shared_growth_total_units
                + summary.stored_growth.added_units,
            )
            or 0
        )
        return (
            ("garden_coins", "Coins", f"+{summary.garden_coins_total:,}" if summary.garden_coins_total else "0", "coin"),
            ("growth_applied", "Growth", format_growth_units(applied, signed=bool(applied)), "growth"),
            ("discoveries", "Items & finds", str(reward_discovery_count(summary)), "environment-discovery"),
        )

    @staticmethod
    def _inventory_rewards(
        summary: SessionDaySummary,
    ) -> tuple[SessionEarnedItem, ...]:
        return session_earned_item_plan(summary)

    @staticmethod
    def _find_items(
        summary: SessionDaySummary,
    ) -> tuple[tuple[str, str, str, int], ...]:
        """Return reconciled find identity, name, art and quantity records."""

        if hasattr(summary, "find_items"):
            if not bool(getattr(summary, "find_items_reconciled", False)):
                return ()
            source_items = tuple(getattr(summary, "find_items", ()) or ())
            projected = tuple(
                (
                    str(getattr(item, "find_id", "") or getattr(item, "item_id", "") or "find"),
                    str(getattr(item, "find_name", "") or "Garden Find"),
                    str(getattr(item, "art_asset", "") or getattr(item, "item_id", "") or ""),
                    max(0, int(getattr(item, "quantity", 0) or 0)),
                )
                for item in source_items
                if int(getattr(item, "quantity", 0) or 0) > 0
            )
        else:
            grouped: dict[str, list[Any]] = {}
            order: list[str] = []
            for item in tuple(getattr(summary, "standard_finds", ()) or ()):
                identity = str(
                    getattr(item, "find_id", "")
                    or getattr(item, "item_id", "")
                    or getattr(item, "find_name", "")
                    or "find"
                )
                if identity not in grouped:
                    grouped[identity] = []
                    order.append(identity)
                grouped[identity].append(item)
            records: list[tuple[str, str, str, int]] = []
            for identity in order:
                values = grouped[identity]
                first = values[0]
                records.append((
                    identity,
                    str(getattr(first, "find_name", "") or "Garden Find"),
                    str(
                        getattr(first, "art_asset", "")
                        or getattr(first, "item_id", "")
                        or ""
                    ),
                    sum(max(1, int(getattr(item, "quantity", 1) or 1)) for item in values),
                ))
            projected = tuple(records)

        explicit_total = int(
            getattr(summary, "total_finds", sum(item[3] for item in projected))
            or 0
        )
        if sum(item[3] for item in projected) != explicit_total:
            return ()
        return projected

    def _add_rewards_earned(
        self,
        layout: Any,
        summary: SessionDaySummary,
        projection: Any,
        metrics: Sequence[tuple[str, str, str, str]],
        inventory_rewards: Sequence[SessionEarnedItem],
    ) -> None:
        section = QFrame()
        section.setObjectName("ankiGardenSessionRewardsSection")
        section.setProperty("summaryRevealAfterHighlights", True)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)

        card = QFrame()
        card.setObjectName("ankiGardenSessionRewardCard")
        card.setProperty("summaryRewardCard", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(8)
        has_content = False
        if metrics:
            self._add_reward_strip(card_layout, metrics)
            has_content = True

        inventory_find_ids = {
            find_id
            for item in inventory_rewards
            for find_id in item.source_find_ids
        }
        find_items = tuple(
            item
            for item in self._find_items(summary)
            if item[0] not in inventory_find_ids
        )
        if find_items or any(item.source_find_ids for item in inventory_rewards):
            card_layout.addWidget(self._section_heading("Garden Finds"))
        if find_items and (self._details_expanded or not inventory_rewards):
            self._add_find_summary(card_layout, find_items)
            has_content = True

        if inventory_rewards:
            self._add_inventory_rewards(
                card_layout,
                tuple(item for item in inventory_rewards if item.source_find_ids),
            )
            other_items = tuple(item for item in inventory_rewards if not item.source_find_ids)
            if other_items:
                card_layout.addWidget(self._section_heading("Items earned"))
                self._add_inventory_rewards(card_layout, other_items)
            has_content = True

        section_layout.addWidget(card)
        layout.addWidget(section)

    def _add_inventory_rewards(
        self,
        layout: Any,
        rewards: Sequence[SessionEarnedItem],
    ) -> None:
        container = QFrame()
        container.setObjectName("ankiGardenSessionItemRewards")
        container.setProperty("summaryItemRewards", True)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)
        for index, item in enumerate(rewards):
            artwork = self._reward_art_label(item.art_reference, 32)
            find_source = next((find for find in self._current_summary().standard_finds
                                if find.find_id in item.source_find_ids), None) if len(item.source_find_ids) == 1 else None
            title = find_source.find_name if find_source is not None else item.name or "Earned item"
            detail = "\n".join(item.source_labels) if find_source is None else ""
            if find_source is not None:
                from ..reward_presentation import RewardLine
                detail = RewardLine("inventory_item", item.quantity, item.item_id).learner_text
            event = receipt_event_row(container, artwork, title, detail=detail, reward=item,
                                      eyebrow="Garden Find" if item.source_find_ids else "Item earned", rarity_badge=True)
            row_widget = event.widget
            row_widget.setProperty("summaryItemRewardKey", f"{item.item_id}:{index}")
            row_widget.setProperty("summaryItemRewardEventIds", item.event_ids)
            row_widget.setProperty("summaryItemRewardSources", item.source_labels)
            if find_source is None:
                quantity = QLabel(f"+{item.quantity:,}", row_widget)
                quantity.setProperty("summaryValue", True)
                apply_tabular_numerals(quantity)
                event.layout.addWidget(quantity, 0, Qt.AlignmentFlag.AlignVCenter)
            container_layout.addWidget(row_widget)
        layout.addWidget(container)

    def _add_reward_strip(self, layout: Any, metrics: Sequence[tuple[str, str, str, str]]) -> None:
        container = QFrame()
        container.setObjectName("ankiGardenSessionRewards")
        container.setProperty("summaryCanonicalMetricCount", len(metrics))
        row = receipt_metrics_layout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for key, label, value, icon in metrics:
            metric = receipt_metric(container, label, value, icon, self._summary_theme)
            metric.widget.setProperty("summaryMetric", True)
            metric.widget.setProperty("summaryMetricKey", key)
            metric.value.setProperty("summaryGrowth" if key == "growth_applied" else "summaryCoin" if key == "garden_coins" else "summaryFind", True)
            if key == "discoveries":
                metric.widget.setToolTip("Find events and item or unlock awards")
            row.addWidget(metric.widget, 1)
        layout.addWidget(container)

    def _add_find_summary(
        self,
        layout: Any,
        find_items: Sequence[tuple[str, str, str, int]],
    ) -> None:
        container = QFrame()
        container.setObjectName("ankiGardenSessionFindSummary")
        rows = QVBoxLayout(container)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(8)
        visible = tuple(find_items) if self._details_expanded else tuple(find_items[:1])
        for index, item in enumerate(visible):
            identity, name, art, quantity = item
            rows.addWidget(self._find_row_widget(
                identity,
                name,
                art,
                quantity,
                compact=True,
            ))
        layout.addWidget(container)

    def _find_row_widget(
        self,
        identity: str,
        name: str,
        art: str,
        quantity: int,
        *,
        compact: bool,
    ) -> Any:
        from ..garden_finds import standard_find_artwork_ref
        artwork = self._reward_art_label(standard_find_artwork_ref(identity, art), 32)
        event = receipt_event_row(self, artwork, name, reward=identity, eyebrow="Garden Find", rarity_badge=True)
        row_widget = event.widget
        row_widget.setProperty("summaryFindRow", True)
        row_widget.setProperty("summaryFindRowCompact", bool(compact))
        row_widget.setProperty("summaryFindId", identity)
        row_widget.setAccessibleName(f"{name} ×{max(1, int(quantity)):,}")
        event.title.setProperty("summaryFindName", True)
        from .reward_receipt import receipt_resource_values
        finds = tuple(find for find in self._current_summary().standard_finds if find.find_id == identity)
        coins = sum(find.reward_amount * find.quantity for find in finds if find.reward_type == "coins")
        growth = sum(find.reward_amount * find.quantity * 100 for find in finds if find.reward_type == "growth")
        if coins or growth:
            event.copy.addWidget(receipt_resource_values(row_widget, coins=coins, growth_units=growth, compact=True))
        value = QLabel(f"×{max(1, int(quantity)):,}")
        value.setProperty("summaryFindQuantity", True)
        apply_tabular_numerals(value)
        event.layout.addWidget(value, 0, Qt.AlignmentFlag.AlignVCenter)
        return row_widget

    def _project_growth_rows(self, summary: SessionDaySummary) -> tuple[Any, ...]:
        snapshot = None
        resolver = getattr(self._engine, "growth_projects_snapshot", None)
        if callable(resolver):
            try:
                snapshot = resolver()
            except Exception:
                snapshot = None
        return project_growth_allocations(
            tuple(getattr(summary, "project_allocations", ()) or ()),
            snapshot,
            landmark_growth_units=max(
                0,
                int(getattr(summary, "landmark_growth_delta_units", 0) or 0),
            ),
        )

    def _has_breakdown(self, summary: SessionDaySummary, projection: Any) -> bool:
        progress_ids = {item.plant_id for item in (*summary.plant_growth_by_plant, *summary.shared_growth_by_plant)}
        return bool(summary.stored_growth.added_units or summary.shared_growth_total_units or summary.project_growth_total_units or summary.stored_growth.used_units or any(
            plant_id not in progress_ids for plant_id, _label, _amount in session_coin_groups(
                summary, represented_find_ids={item[0] for item in self._find_items(summary)},
            )
        ))

    @staticmethod
    def _minor_checkpoints(summary: SessionDaySummary) -> tuple[PlantMilestone, ...]:
        """Checkpoint progress kept out of featured highlights but not discarded."""

        return tuple(
            milestone for milestone in summary.milestones
            if milestone.milestone_type == "checkpoint"
            and int(milestone.checkpoint_percent) < 75
        )

    def _add_breakdown(self, layout: Any, summary: SessionDaySummary, projection: Any, *, active_effects=()) -> None:
        panel = QFrame()
        panel.setObjectName("ankiGardenSessionBreakdown")
        panel.setProperty("summaryBreakdownPanel", True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 6)
        panel_layout.setSpacing(6)
        self._add_breakdown_details(panel_layout, summary, projection)
        if active_effects:
            self._add_active_boosts(panel_layout, active_effects)
        layout.addWidget(self._divider())
        toggle = QToolButton(self)
        toggle.setObjectName("ankiGardenSessionProgressDisclosure")
        toggle.setText("Details")
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setIcon(garden_icon("chevron-up" if self._progress_details_expanded else "chevron-down"))
        toggle.setMinimumHeight(24)
        toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toggle.setAccessibleName("Hide additional details" if self._progress_details_expanded else "Show additional details")
        toggle.setStyleSheet(f"QToolButton {{background:transparent;border:0;color:{self._summary_theme['text_secondary']};font-size:12px;padding:3px;}} QToolButton:hover {{color:{self._summary_theme['text_primary']};}}")
        toggle.clicked.connect(self._toggle_progress_details)
        layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(panel)
        # Parent the panel before showing it so macOS never treats it as a
        # separate top-level window and switches Spaces when Details expands.
        panel.setVisible(self._progress_details_expanded)

    def _toggle_progress_details(self) -> None:
        self._progress_details_expanded = not self._progress_details_expanded
        self._rebuild_page()

    def _breakdown_total_row(
        self,
        layout: Any,
        key: str,
        label_text: str,
        value_text: str,
        *,
        supporting_text: str = "",
        coin: bool = False,
        art_reference: str = "",
        target_type: str = "",
        target_id: str = "",
    ) -> None:
        row_widget = QFrame()
        row_widget.setProperty("summaryBreakdownRowKey", key)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)
        if art_reference:
            art = self._reward_art_label(
                art_reference,
                28,
                semantic_kind="Growth project",
                fallback_icon="growth",
            )
            art.setProperty("summaryProjectTargetType", target_type)
            art.setProperty("summaryProjectTargetId", target_id)
            row.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        label = self._name_label(label_text)
        copy.addWidget(label)
        if supporting_text:
            supporting = QLabel(supporting_text)
            supporting.setWordWrap(True)
            supporting.setProperty("summaryMuted", True)
            copy.addWidget(supporting)
        row.addLayout(copy, 1)
        value = QLabel(value_text)
        apply_tabular_numerals(value)
        value.setProperty(
            "summaryDetailCoin" if coin else "summaryDetailGrowth",
            True,
        )
        if coin:
            row.addWidget(self._reward_art_label("garden_coin", 14), 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(value, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(row_widget)

    def _add_plant_progress(self, layout: Any, summary: SessionDaySummary) -> None:
        growth = {}
        for item in (*summary.plant_growth_by_plant, *summary.shared_growth_by_plant):
            previous = growth.get(item.plant_id)
            growth[item.plant_id] = (item, item.growth_units + (previous[1] if previous else 0))
        starts = {item.plant_id: item for item in summary.plants_at_start}
        blooms = {item.plant_id for item in summary.milestones if item.milestone_type == "full_bloom"}
        coin_groups = session_coin_groups(summary)
        progression_coins = {plant_id: amount for plant_id, _label, amount in coin_groups if plant_id}
        if growth:
            layout.addWidget(self._section_heading("Plant progress"))
            from types import SimpleNamespace
            from .reward_receipt import receipt_progress_card
            for plant_id, (item, units) in growth.items():
                baseline = starts.get(plant_id)
                before_units = baseline.growth_units if baseline is not None else None
                full_bloom = plant_id in blooms
                details = session_plant_progress(
                    item.species_name or item.plant_name, before_units, units, full_bloom=full_bloom,
                )
                artwork = self._plant_art_label(SimpleNamespace(
                    plant_id=plant_id, species_name=item.species_name, art_asset=item.art_asset,
                    new_stage=details.stage,
                ), 48)
                progress = receipt_progress_card(layout.parentWidget(), artwork,
                    details.name, details.description,
                    progress_percent=0 if details.current_units is not None else None,
                    coins=progression_coins.get(plant_id, 0), palette=self._summary_theme,
                    full_bloom=full_bloom, growth_gain=details.gain, stage_change=details.stage_change)
                if details.current_units is not None:
                    progress.progress.setRange(0, details.required_units)
                    progress.progress.setValue(details.current_units)
                progress.widget.setProperty("summaryBreakdownRowKey", f"plant_progress:{plant_id}")
                progress.widget.setProperty("summaryHighlightKind", "full_bloom" if full_bloom else "plant_progress")
                progress.progress.setAccessibleName(f"{details.name} stage progress")
                progress.progress.setAccessibleDescription(details.description)
                layout.addWidget(progress.widget)

    def _add_breakdown_details(self, layout: Any, summary: SessionDaySummary, projection: Any) -> None:
        from .reward_receipt import receipt_growth_breakdown
        layout.addWidget(receipt_growth_breakdown(self,
            total_units=int(projection.growth_applied_total_units),
            plant_units=int(summary.growth_applied_total_units or 0),
            shared_units=summary.shared_growth_total_units,
            stored_units=summary.stored_growth.added_units,
            project_units=summary.project_growth_total_units,
            transferred_units=summary.stored_growth.used_units))
        progress_ids = {item.plant_id for item in (*summary.plant_growth_by_plant, *summary.shared_growth_by_plant)}
        coins = tuple((label, amount) for plant_id, label, amount in session_coin_groups(
                          summary, represented_find_ids={item[0] for item in self._find_items(summary)},
                      )
                      if plant_id not in progress_ids)
        if coins:
            layout.addWidget(self._section_heading("Coins"))
            for index, (label, amount) in enumerate(coins):
                self._breakdown_total_row(layout, f"coin_source:{index}", label, f"+{amount:,}", coin=True)

    def _active_effects_for_payload(self, projection: Any) -> tuple[Any, ...]:
        terminal = getattr(self._payload, "terminal_effects", None)
        if terminal is not None:
            values = tuple((
                *tuple(getattr(terminal, "fertilizers", ()) or ()),
                *tuple(getattr(terminal, "boosters", ()) or ()),
            ))
            if not values and isinstance(terminal, Sequence):
                values = tuple(terminal)
        else:
            values = tuple(getattr(projection, "effects_remaining", ()) or ())
        return tuple(
            effect
            for effect in values
            if not bool(getattr(effect, "ended_during_session", False))
            and bool(getattr(effect, "active", True))
            and bool(self._effect_value(effect))
        )

    def _effect_kind(self, effect: Any) -> str:
        kind = str(getattr(effect, "kind", "") or "")
        if kind:
            return kind
        effect_id = str(getattr(effect, "effect_id", "") or "").casefold()
        return (
            "fertilizer"
            if "fertilizer" in effect_id or hasattr(effect, "remaining_seconds")
            else "booster"
        )

    def _effect_art_reference(self, effect: Any) -> str:
        """Map one active effect to its bundled item artwork without using instance IDs."""

        kind = self._effect_kind(effect)
        if kind == "booster":
            return "booster_potion"
        if kind != "fertilizer":
            return ""
        effect_id = str(getattr(effect, "effect_id", "") or "")
        parts = effect_id.split(":")
        tier = parts[-1].casefold() if len(parts) > 2 and parts[0] == "fertilizer" else ""
        name = str(
            getattr(effect, "label", "")
            or getattr(effect, "name", "")
            or ""
        ).casefold()
        if tier not in {"basic", "quality", "premium"}:
            tier = (
                "quality"
                if "quality" in name
                else "premium"
                if "magical" in name or "premium" in name
                else "basic"
                if "basic" in name
                else ""
            )
        return f"fertilizer_{tier}" if tier in {"basic", "quality", "premium"} else ""

    def _effect_value(self, effect: Any) -> str:
        return session_effect_remaining_text(effect)

    def _add_active_boosts(self, layout: Any, effects: Sequence[Any]) -> None:
        section = QFrame()
        section.setObjectName("ankiGardenSessionActiveBoosts")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)
        section_layout.addWidget(self._section_heading("Active effects"))

        card = QFrame()
        card.setObjectName("ankiGardenSessionBoostCard")
        card.setProperty("summaryBoostCard", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        self._boost_rows = {}
        for index, effect in enumerate(effects):
            kind = self._effect_kind(effect)
            divider = None
            if index:
                divider = self._divider(card)
                card_layout.addWidget(divider)
            row_widget = QFrame(card)
            row_widget.setProperty("summaryBoostRow", True)
            row_widget.setProperty("summaryBoostKind", kind)
            # A single-line row remains 36 px, while a localized two-line name
            # may grow instead of clipping beneath the fixed remaining value.
            row_widget.setMinimumHeight(36)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 5, 12, 5)
            row_layout.setSpacing(8)
            effect_name = str(
                getattr(effect, "label", "")
                or getattr(effect, "name", "")
                or _title_case(kind)
            )
            if kind == "booster":
                effect_name = "Booster Potion"
            art_reference = self._effect_art_reference(effect)
            if art_reference == "fertilizer_premium":
                effect_name = "Magical Fertilizer"
            art = self._reward_art_label(
                art_reference,
                26,
                semantic_kind="active boost",
                fallback_icon=kind if kind in {"fertilizer", "booster"} else "find",
            )
            art.setProperty("summaryBoostArt", True)
            art.setProperty("summaryBoostArtReference", art_reference)
            art.setAccessibleName(f"{effect_name} artwork")
            row_layout.addWidget(art)
            label = self._name_label(effect_name)
            label.setProperty("summaryBoostName", True)
            row_layout.addWidget(label, 1)
            value = QLabel(self._effect_value(effect))
            value.setProperty("summaryBoostValue", True)
            apply_tabular_numerals(value)
            row_layout.addWidget(value)
            card_layout.addWidget(row_widget)
            identity = str(getattr(effect, "effect_id", "") or id(effect))
            self._boost_rows[identity] = (effect, row_widget, value, divider)
        section_layout.addWidget(card)
        self._active_boosts_section = section
        layout.addWidget(section)

    def _refresh_active_effects(self) -> None:
        any_visible = False
        previous_visible = False
        for effect, row_widget, value_label, divider in tuple(
            self._boost_rows.values()
        ):
            value = self._effect_value(effect)
            visible = bool(value)
            try:
                row_widget.setVisible(visible)
                value_label.setText(value)
                if divider is not None:
                    divider.setVisible(visible and previous_visible)
            except Exception:
                continue
            any_visible = any_visible or visible
            previous_visible = previous_visible or visible
        if self._active_boosts_section is not None:
            self._active_boosts_section.setVisible(any_visible)
        self.reposition()

    def _toggle_details(self) -> None:
        self._details_expanded = True
        self._rebuild_page()

    def _expand_find_breakdown(self) -> None:
        if self._details_expanded:
            return
        self._details_expanded = True
        self._rebuild_page()

    def _toggle_growth_details(self) -> None:
        self._show_all_growth = True
        self._rebuild_page()

    def _name_label(self, text: str) -> Any:
        full_text = str(text or "")
        label = _WrappedNameLabel(full_text)
        label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        label.setMinimumWidth(0)
        return label

    def _semantic_art_label(
        self,
        *,
        kind: str,
        source_path: str,
        pixmap: Any,
        logical_width: int,
        logical_height: int,
        fallback_icon: str,
        source_pixmap: Any | None = None,
    ) -> Any:
        label = QLabel()
        label.setFixedSize(logical_width, logical_height)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("summaryArtKind", kind)
        label.setProperty("summaryArtSource", str(source_path or ""))
        label.setProperty("summaryArtLogicalWidth", int(logical_width))
        label.setProperty("summaryArtLogicalHeight", int(logical_height))
        vector = Path(str(source_path or "")).suffix.casefold() == ".svg"
        label.setProperty("summaryArtVector", vector)
        inspected = source_pixmap if source_pixmap is not None else _source_pixmap(source_path)
        source_width = 0 if inspected.isNull() else int(inspected.width())
        source_height = 0 if inspected.isNull() else int(inspected.height())
        label.setProperty("summaryArtSourceWidth", source_width)
        label.setProperty("summaryArtSourceHeight", source_height)
        fallback = pixmap is None or pixmap.isNull()
        label.setProperty("summaryArtFallback", fallback)
        if fallback:
            pixmap = garden_icon(
                fallback_icon,
                color=self._summary_theme["growth_accent"],
                logical_size=min(logical_width, logical_height),
            ).pixmap(min(logical_width, logical_height), min(logical_width, logical_height))
            label.setAccessibleDescription(
                f"{_title_case(kind)} artwork is unavailable; a semantic fallback is shown."
            )
        label.setAccessibleName(f"{_title_case(kind)} artwork")
        label.setPixmap(pixmap)
        return label

    def _engine_plant(self, plant_id: str) -> Any | None:
        state = getattr(self._engine, "state", None)
        for plant in tuple(getattr(state, "plants", ()) or ()):
            if str(getattr(plant, "plant_id", "") or "") == str(plant_id or ""):
                return plant
        return None

    def _plant_art_label(self, record: Any, size: int) -> Any:
        if getattr(record, "milestone_type", "") == "checkpoint":
            return self._reward_art_label("checkpoint_badge", size, semantic_kind="checkpoint", fallback_icon="checkpoint")
        plant_id = str(getattr(record, "plant_id", "") or "")
        plant = self._engine_plant(plant_id)
        species = str(
            getattr(plant, "species", "")
            or getattr(record, "plant_class", "")
            or getattr(record, "species_name", "")
            or ""
        ).casefold().replace(" ", "_")
        stage = str(
            getattr(record, "new_stage", "")
            or getattr(plant, "growth_stage", "")
            or ("rare" if getattr(record, "milestone_type", "") == "full_bloom" else "")
        )
        source_path = str(
            getattr(record, "plant_art_asset", "")
            or getattr(record, "art_asset", "")
            or ""
        )
        placement = None
        resolver = getattr(self._engine, "resolve_plant_asset", None)
        if callable(resolver) and species and (stage or not source_path):
            try:
                resolved = resolver(species, stage or "seed")
                resolved_path = str(getattr(resolved, "path", "") or "")
                if resolved_path:
                    source_path = resolved_path
                    placement = getattr(resolved, "placement", None)
            except Exception:
                placement = None
        source = _source_pixmap(source_path)
        pixmap = QPixmap()
        if not source.isNull():
            if placement is not None:
                try:
                    pixmap = normalized_plant_pixmap(
                        source_path,
                        placement,
                        stage=stage,
                        logical_size=size,
                        device_pixel_ratio=2.0,
                    )
                except Exception:
                    pixmap = QPixmap()
            if pixmap.isNull():
                pixmap = _alpha_bounded_thumbnail(source, size)
        label = self._semantic_art_label(
            kind="plant",
            source_path=source_path,
            pixmap=pixmap,
            logical_width=size,
            logical_height=size,
            fallback_icon="plant",
            source_pixmap=source,
        )
        label.setProperty("summaryPlantId", plant_id)
        label.setProperty("summaryPlantStage", stage)
        return label

    @staticmethod
    def _cover_art(source: Any, width: int, height: int) -> Any:
        if source.isNull():
            return QPixmap()
        target_width = max(1, int(width) * 2)
        target_height = max(1, int(height) * 2)
        scaled = source.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        result = QPixmap(target_width, target_height)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        try:
            painter.drawPixmap(
                (target_width - scaled.width()) // 2,
                (target_height - scaled.height()) // 2,
                scaled,
            )
        finally:
            painter.end()
        result.setDevicePixelRatio(2.0)
        return result

    def _environment_art_label(self, record: Any, width: int, height: int) -> Any:
        raw_item_id = str(
            getattr(record, "environment_id", "")
            or getattr(record, "art_asset", "")
            or ""
        )
        record_kind = str(getattr(record, "environment_kind", "") or "")
        kind = record_kind
        feature_id = canonical_garden_feature_id(raw_item_id)
        if feature_id in GARDEN_FEATURE_CATALOG:
            item_id = feature_id
            item = GARDEN_FEATURE_CATALOG[feature_id]
        else:
            item_id = raw_item_id
            item = SCENERY_CATALOG.get(item_id)
        if item is not None:
            kind = str(getattr(item, "kind", "") or kind)
        source_path = ""
        is_feature = bool(
            record_kind in {"garden_item", "garden_feature", "weather"}
            or feature_id in GARDEN_FEATURE_CATALOG
            or kind == "garden_feature"
        )
        resolver = getattr(
            self._engine,
            "resolve_garden_feature_asset" if is_feature else "resolve_scenery_preview_asset",
            None,
        )
        if callable(resolver) and item_id:
            try:
                resolved = (
                    resolver(
                        item_id,
                        preview=True,
                        respect_visibility=False,
                    )
                    if is_feature
                    else resolver(item_id)
                )
                source_path = str(getattr(resolved, "path", "") or "")
            except TypeError:
                try:
                    resolved = (
                        resolver(item_id, preview=True)
                        if is_feature
                        else resolver(item_id)
                    )
                    source_path = str(getattr(resolved, "path", "") or "")
                except Exception:
                    source_path = ""
            except Exception:
                source_path = ""
        if not source_path:
            candidate = str(getattr(record, "art_asset", "") or "")
            source_path = candidate if Path(candidate).exists() else ""
        source = _source_pixmap(source_path)
        pixmap = QPixmap()
        if is_feature and not source.isNull():
            # Garden items are transparent collectible art, not scenery
            # thumbnails.  Showing the resolved source directly avoids an
            # invented inner frame or scene background around the item.
            pixmap = _alpha_bounded_thumbnail(source, min(width, height))
        elif self._engine is not None and item is not None:
            try:
                pixmap = environment_preview_pixmap(
                    self._engine,
                    item,
                    width * 2,
                    height * 2,
                    scenery_id=str(
                        getattr(getattr(self._engine, "state", None), "selected_background", "")
                        or DEFAULT_SCENERY_ID
                    ),
                )
                if not pixmap.isNull():
                    pixmap.setDevicePixelRatio(2.0)
            except Exception:
                pixmap = QPixmap()
        if pixmap.isNull() and not source.isNull():
            pixmap = self._cover_art(source, width, height)
        label = self._semantic_art_label(
            kind="garden_item" if is_feature else "environment",
            source_path=source_path,
            pixmap=pixmap,
            logical_width=width,
            logical_height=height,
            fallback_icon="environment",
            source_pixmap=source,
        )
        label.setProperty("summaryGardenItemArt", is_feature)
        label.setProperty("summaryEnvironmentArt", not is_feature)
        label.setProperty("summaryEnvironmentId", item_id)
        return label

    def _reward_art_label(
        self,
        record: Any,
        size: int,
        *,
        semantic_kind: str = "find",
        fallback_icon: str = "find",
    ) -> Any:
        reference = str(
            record
            if isinstance(record, str)
            else getattr(record, "art_asset", "") or ""
        )
        source_path = reference if Path(reference).exists() else ""
        pixmap = QPixmap()
        if not source_path and reference:
            item_key = {
                "garden_coins": "garden_coin",
                "growth": "growth_resource",
            }.get(reference, reference).removeprefix("ui_")
            resolver = getattr(self._engine, "resolve_item_asset", None)
            if callable(resolver):
                try:
                    resolved = resolver(item_key)
                    source_path = str(getattr(resolved, "path", "") or "")
                except Exception:
                    source_path = ""
            if not source_path:
                source_path = str(bundled_ui_asset_path(item_key) or "")
        source = _source_pixmap(source_path)
        if pixmap.isNull() and not source.isNull():
            pixmap = _alpha_bounded_thumbnail(source, size)
        label = self._semantic_art_label(
            kind=semantic_kind,
            source_path=source_path,
            pixmap=pixmap,
            logical_width=size,
            logical_height=size,
            fallback_icon=fallback_icon,
            source_pixmap=source,
        )
        label.setProperty("summaryRewardArtReference", reference)
        return label

    def _rebuild_footer(self, open_garden_available: bool, continue_reviews_available: bool, today_complete: bool) -> None:
        self._clear_layout(self._footer_layout)
        self._footer_layout.addStretch(1)
        can_continue = continue_reviews_available and not today_complete
        if not can_continue:
            close = receipt_button(self._footer, "Close", self.close, primary=not open_garden_available)
            close.setObjectName("ankiGardenSessionDone")
            self._footer_layout.addWidget(close)
        if open_garden_available:
            garden = receipt_button(self._footer, "Open garden", self._open_garden, primary=not can_continue)
            garden.setObjectName("ankiGardenSessionOpenGarden")
            garden.setProperty("summaryActionRole", "secondary" if can_continue else "primary")
            self._footer_layout.addWidget(garden)
        if can_continue:
            continuation = receipt_button(self._footer, "Continue studying", self._continue_reviews, primary=True)
            continuation.setObjectName("ankiGardenSessionContinueReviews")
            self._footer_layout.addWidget(continuation)
        self._footer.setProperty("summaryPrimaryAction", "continue_reviews" if can_continue else "open_garden" if open_garden_available else "close")
        self._footer.setProperty("summaryOpenGardenRole", "secondary" if can_continue else "primary" if open_garden_available else "unavailable")

    def _open_garden(self) -> None:
        callback = self._on_open_garden
        self.close()
        if callable(callback):
            callback()

    def _continue_reviews(self) -> None:
        callback = self._on_continue_reviews
        if not callable(callback):
            return
        try:
            succeeded = bool(callback())
        except Exception:
            succeeded = False
        if succeeded:
            self.close()
            return
        self.setProperty("summaryContinueFailed", True)
        try:
            from aqt.utils import tooltip

            tooltip(
                "Reviews could not be resumed. Open the deck and try again.",
                period=4_000,
                parent=self,
            )
        except Exception:
            pass

    def _natural_height(self) -> int:
        try:
            body_height = receipt_body_height(self._body, self._body.width())
        except Exception:
            body_height = 1
        return (
            int(self._header.height())
            + int(self._footer.height())
            + int(self._summary_fixed.height())
            + body_height
            + 2
            + (SESSION_SUMMARY_FRAME_BORDER_WIDTH * 2)
        )

    def reposition(
        self,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        exclusion_top: int | None = None,
        reserved_top: int | None = None,
    ) -> tuple[int, int, int, int]:
        """Resize and restore the card's upper-right viewport anchor."""

        parent = self.parentWidget()
        if parent is None:
            return (0, 0, max(1, int(self.width())), max(1, int(self.height())))
        width = max(1, int(parent.width())) if viewport_width is None else int(viewport_width)
        height = max(1, int(parent.height())) if viewport_height is None else int(viewport_height)
        if exclusion_top is not None:
            try:
                self._exclusion_top = max(1, int(exclusion_top))
                self._exclusion_source = "argument"
            except (TypeError, ValueError):
                pass
        resolved_exclusion_top = self._exclusion_top
        if reserved_top is not None:
            try:
                self._reserved_top = max(0, int(reserved_top))
                self._reserved_top_source = "argument"
            except (TypeError, ValueError):
                pass
        resolved_reserved_top = self._reserved_top

        compact_density = session_summary_uses_compact_density(height)
        if compact_density != self._compact_density:
            self._compact_density = compact_density
            self.setProperty("summaryCompactDensity", compact_density)
            self._apply_shell_density()
            self._rebuild_page()

        provisional = session_summary_geometry(
            width,
            height,
            1,
            exclusion_top=resolved_exclusion_top,
            reserved_top=resolved_reserved_top,
        )
        self.setFixedWidth(provisional[2])
        fit_receipt_chrome(self._header, self._footer, provisional[2])
        fixed_height = self._summary_fixed_layout.totalHeightForWidth(provisional[2])
        if fixed_height < 0:
            fixed_height = self._summary_fixed_layout.sizeHint().height()
        self._summary_fixed.setFixedHeight(max(1, fixed_height))
        try:
            # Reserve the styled 6 px scrollbar width even when it is absent.
            # This is the native-QScrollArea equivalent of scrollbar-gutter:
            # stable; body text never reflows merely because scrolling starts.
            stable_body_width = max(1, provisional[2] - 8)
            self._body.setFixedWidth(stable_body_width)
            self._body.resize(
                stable_body_width,
                max(1, int(self._body.height())),
            )
        except Exception:
            pass
        geometry = session_summary_geometry(
            width,
            height,
            self._natural_height(),
            exclusion_top=resolved_exclusion_top,
            reserved_top=resolved_reserved_top,
        )
        self.setFixedSize(geometry[2], geometry[3])
        self.move(geometry[0], geometry[1])
        self.setProperty("summaryViewportBounded", bool(
            geometry[0] >= 0
            and geometry[1] >= 0
            and geometry[0] + geometry[2] <= width
            and geometry[1] + geometry[3] <= height
        ))
        self.setProperty("summaryExclusionTop", resolved_exclusion_top)
        self.setProperty("summaryExclusionSource", self._exclusion_source)
        self.setProperty(
            "summaryExclusionApplied",
            bool(
                resolved_exclusion_top is not None
                and int(resolved_exclusion_top) < height
                and geometry[1] + geometry[3]
                <= min(height, int(resolved_exclusion_top))
            ),
        )
        self.setProperty("summaryHomeClearanceBottom", resolved_reserved_top)
        self.setProperty(
            "summaryHomeClearanceSource",
            self._reserved_top_source,
        )
        self.setProperty(
            "summaryHomeClearanceApplied",
            bool(
                resolved_reserved_top is not None
                and int(resolved_reserved_top) < height
                and geometry[1]
                >= int(resolved_reserved_top)
                + SESSION_SUMMARY_MIN_VERTICAL_MARGIN
                and geometry[1] + geometry[3] <= height
            ),
        )
        return geometry

    def eventFilter(self, watched: Any, event: Any) -> bool:
        """Keep the child card anchored as its host content area changes."""

        try:
            should_reposition = (
                watched is self._filtered_parent
                and not self._dismissed
                and event.type() in {
                    QEvent.Type.Resize,
                    QEvent.Type.Show,
                }
            )
        except Exception:
            should_reposition = False
        if should_reposition:
            self.reposition()
        try:
            return bool(super().eventFilter(watched, event))
        except Exception:
            return False

    def _remove_parent_event_filter(self) -> None:
        parent = self._filtered_parent
        self._filtered_parent = None
        if parent is None:
            return
        try:
            parent.removeEventFilter(self)
        except Exception:
            pass

    def show(self) -> None:
        """Show above page content without activating or focusing the card."""

        if self._dismissed:
            return
        self.reposition()
        super().show()
        self.raise_()
        self._start_entry_animation()

    def _start_entry_animation(self) -> None:
        """Fade in once without moving layout-managed receipt content."""

        if self._animation_started:
            return
        self._animation_started = True
        if not self._animations_enabled:
            return
        try:
            opacity = QGraphicsOpacityEffect(self._body)
            opacity.setOpacity(0.0)
            self._body.setGraphicsEffect(opacity)
            fade = QPropertyAnimation(opacity, b"opacity", self)
            fade.setDuration(200)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)

            def finish_fade() -> None:
                try:
                    self._body.setGraphicsEffect(None)
                except RuntimeError:
                    pass
                if fade in self._animations:
                    self._animations.remove(fade)
                fade.deleteLater()

            fade.finished.connect(finish_fade)
            self._animations.append(fade)
            fade.start()
        except Exception:
            self._body.setGraphicsEffect(None)

    def close(self) -> bool:
        """Dismiss this card exactly once and notify its owner."""

        if self._dismissed:
            return True
        self._dismissed = True
        for animation in tuple(self._animations):
            try:
                animation.stop()
            except Exception:
                pass
        self._animations.clear()
        self._remove_parent_event_filter()
        callback = self._on_dismiss
        self._on_dismiss = None
        result = bool(super().close())
        if callable(callback):
            callback()
        self.deleteLater()
        return result


__all__ = [
    "SESSION_SUMMARY_DEFAULT_WIDTH",
    "SESSION_SUMMARY_EDGE_MARGIN",
    "SESSION_SUMMARY_FOOTER_HEIGHT",
    "SESSION_SUMMARY_FRAME_BORDER_WIDTH",
    "SESSION_SUMMARY_COMPACT_HOST_HEIGHT",
    "SESSION_SUMMARY_HEADER_HEIGHT",
    "SESSION_SUMMARY_MAX_HEIGHT",
    "SESSION_SUMMARY_MAX_WIDTH",
    "SESSION_SUMMARY_MIN_WIDTH",
    "SESSION_SUMMARY_MIN_VERTICAL_MARGIN",
    "SESSION_SUMMARY_PREFERRED_TOP_MARGIN",
    "SESSION_SUMMARY_VIEWPORT_VERTICAL_MARGIN",
    "SessionEarnedItem",
    "SessionSummaryCard",
    "session_effect_remaining_text",
    "session_find_summary_plan",
    "session_earned_item_plan",
    "session_summary_geometry",
    "session_summary_uses_compact_density",
    "session_inventory_reward_lines",
    "session_summary_palette",
]
