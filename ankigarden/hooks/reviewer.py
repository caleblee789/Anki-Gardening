from __future__ import annotations
from ..reward_presentation import reward_content_visible

from ..presentation import PlantIdentity, plant_species_name, plant_stage_event

import logging
import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping
import uuid

from aqt import mw

from ..config import DEFAULT_CONFIG
from ..environment import (
    SCENERY_CATALOG,
    WEATHER_CATALOG,
    canonical_garden_feature_id,
)
from ..game import (
    CommittedAnswerResult,
    difficulty_from_factor,
    queue_and_lapse_from_revlog_type,
)
from ..growth import GROWTH_STAGES
from ..garden_finds import standard_find_artwork_ref
from ..notices import USER_NOTICES
from ..performance import RUNTIME_PERFORMANCE, timed
from ..storage import (
    _parse_answer_lineage_key, assign_stable_answer_identities,
    unprocessed_revlog_entries,
)
from ..ui.copy import REVIEWER_NO_STARTER_NOTICE
from ..ui.reviewer_hud import (
    HUD_ANSWER_CONTROLS_SCHEMA_VERSION,
    HUD_CONTROLS_CLEARANCE,
    ReviewerHudProjection,
    create_reviewer_hud,
    project_reviewer_hud,
    reviewer_hud_geometry,
    should_start_collapsed,
)
from ..ui.session_summary import (
    BoosterSnapshot,
    CoinAward,
    CommittedSessionEvent,
    EffectsSnapshot,
    EnvironmentDiscovery,
    FertilizerSnapshot,
    PlantGrowthDelta,
    PlantMilestone,
    PlantStateSnapshot,
    ReviewContinuationTarget,
    SessionEndSnapshot,
    SessionProjectGrowthAllocation,
    SessionStartSnapshot,
    SessionSummaryAccumulator,
    SessionSummaryPayload,
    encode_session_record,
    decode_session_record,
    StandardFind,
    TodayCardsSnapshot,
)
from ..ui.theme import GARDEN_THEME
from ..ui.transient_summary_coordinator import dispose_unmounted_summary_card


logger = logging.getLogger(__name__)


REVIEWER_ANSWER_CONTROLS_SCHEMA_VERSION = HUD_ANSWER_CONTROLS_SCHEMA_VERSION
REVIEWER_ANSWER_CONTROLS_SOURCE = "webengine-dom"
REVIEWER_ANSWER_CONTROLS_FALLBACK_CLEARANCE = HUD_CONTROLS_CLEARANCE


def reviewer_answer_controls_measurement_script() -> str:
    """Return the WebEngine probe for Anki's visible answer controls.

    Coordinates are CSS pixels relative to the Reviewer webview viewport;
    the receiver converts them to native logical pixels using webview zoom. The
    selector list intentionally targets answer controls rather than Anki's
    whole bottom bar so Edit/More/navigation chrome cannot shrink the HUD.
    """

    return r"""
(() => {
  const schemaVersion = 1;
  const source = "webengine-dom";
  const viewport = {
    width: Math.max(1, Math.round(window.innerWidth || 0)),
    height: Math.max(1, Math.round(window.innerHeight || 0)),
  };
  const selectors = [
    "#answer-buttons",
    ".answer-buttons",
    "[data-testid='answer-buttons']",
    "[data-testid='reviewer-answer-controls']",
    ".reviewer-answer-controls",
    ".answer-controls",
    "#ansbut",
    "#show-answer",
    "button[data-testid='show-answer']",
    "#ease1",
    "#ease2",
    "#ease3",
    "#ease4",
    "button[data-ease]"
  ];
  const nodes = [];
  const seen = new Set();
  for (const selector of selectors) {
    for (const node of document.querySelectorAll(selector)) {
      if (seen.has(node)) continue;
      seen.add(node);
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity || "1") === 0 ||
        rect.width <= 0 ||
        rect.height <= 0 ||
        rect.right <= 0 ||
        rect.bottom <= 0 ||
        rect.left >= viewport.width ||
        rect.top >= viewport.height
      ) continue;
      nodes.push(rect);
    }
  }
  if (!nodes.length) {
    return {
      schema_version: schemaVersion,
      source,
      measured: false,
      viewport,
      rect: null,
      clearance: null,
      matched_nodes: 0,
    };
  }
  const left = Math.max(0, Math.floor(Math.min(...nodes.map(rect => rect.left))));
  const top = Math.max(0, Math.floor(Math.min(...nodes.map(rect => rect.top))));
  const right = Math.min(
    viewport.width,
    Math.ceil(Math.max(...nodes.map(rect => rect.right)))
  );
  const bottom = Math.min(
    viewport.height,
    Math.ceil(Math.max(...nodes.map(rect => rect.bottom)))
  );
  return {
    schema_version: schemaVersion,
    source,
    measured: true,
    viewport,
    rect: {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
    },
    clearance: Math.max(0, viewport.height - top),
    matched_nodes: nodes.length,
  };
})()
""".strip()


def normalize_reviewer_answer_controls_telemetry(
    payload: Any,
    *,
    viewport_width: int,
    viewport_height: int,
    zoom_factor: float = 1.0,
) -> dict[str, Any] | None:
    """Validate one WebEngine answer-control measurement fail closed."""

    if not isinstance(payload, Mapping):
        return None
    try:
        zoom_factor = float(zoom_factor)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(zoom_factor) or zoom_factor <= 0:
        return None
    try:
        schema_version = int(payload.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        return None
    if (
        schema_version != REVIEWER_ANSWER_CONTROLS_SCHEMA_VERSION
        or payload.get("measured") is not True
        or str(payload.get("source", "") or "")
        != REVIEWER_ANSWER_CONTROLS_SOURCE
    ):
        return None

    viewport = payload.get("viewport")
    rect = payload.get("rect")
    if not isinstance(viewport, Mapping) or not isinstance(rect, Mapping):
        return None
    try:
        measured_width = int(round(float(viewport.get("width", 0) or 0) * zoom_factor))
        measured_height = int(round(float(viewport.get("height", 0) or 0) * zoom_factor))
        x = int(round(float(rect.get("x", 0) or 0) * zoom_factor))
        y = int(round(float(rect.get("y", 0) or 0) * zoom_factor))
        width = int(round(float(rect.get("width", 0) or 0) * zoom_factor))
        height = int(round(float(rect.get("height", 0) or 0) * zoom_factor))
        matched_nodes = max(0, int(payload.get("matched_nodes", 0) or 0))
    except (TypeError, ValueError, OverflowError):
        return None

    expected_width = max(1, int(viewport_width))
    expected_height = max(1, int(viewport_height))
    # A callback can arrive after a native resize. Reject that stale geometry
    # instead of applying it in a new coordinate space.
    if (
        abs(measured_width - expected_width) > 2
        or abs(measured_height - expected_height) > 2
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > expected_width + 2
        or y + height > expected_height + 2
    ):
        return None

    return {
        "schema_version": REVIEWER_ANSWER_CONTROLS_SCHEMA_VERSION,
        "source": REVIEWER_ANSWER_CONTROLS_SOURCE,
        "measured": True,
        "viewport": (expected_width, expected_height),
        "rect": (x, y, width, height),
        "top": y,
        "clearance": max(0, expected_height - y),
        "matched_nodes": matched_nodes,
    }


def _standard_find_is_notable(outcome: Any) -> bool:
    """Promote only explicitly notable or canonically rare standard finds."""

    return bool(
        getattr(outcome, "notable", False)
        or str(getattr(outcome, "tier", "") or "").strip().casefold()
        in {"rare", "exceptional"}
    )


def bounded_reviewer_overlay_position(
    viewport_width: int,
    viewport_height: int,
    overlay_width: int,
    overlay_height: int,
    *,
    preferred_y: int = 16,
    margin: int = 16,
) -> tuple[int, int]:
    """Clamp one reviewer overlay wholly inside the reviewer viewport."""

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))
    overlay_width = max(1, int(overlay_width))
    overlay_height = max(1, int(overlay_height))
    margin = max(0, int(margin))
    maximum_x = max(0, viewport_width - overlay_width)
    maximum_y = max(0, viewport_height - overlay_height)
    return (
        max(0, min(maximum_x, viewport_width - overlay_width - margin)),
        max(0, min(maximum_y, max(margin, int(preferred_y)))),
    )


def reviewer_reward_overlay_position(
    viewport_width: int,
    viewport_height: int,
    overlay_width: int,
    overlay_height: int,
    *,
    margin: int = 16,
    reviewer_controls_clearance: int = 144,
) -> tuple[int, int]:
    """Anchor reward feedback at right, above Anki's answer controls."""

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))
    overlay_width = max(1, int(overlay_width))
    overlay_height = max(1, int(overlay_height))
    margin = max(0, int(margin))
    controls_clearance = max(margin, int(reviewer_controls_clearance))
    return bounded_reviewer_overlay_position(
        viewport_width,
        viewport_height,
        overlay_width,
        overlay_height,
        preferred_y=viewport_height - overlay_height - controls_clearance,
        margin=margin,
    )


def reviewer_overlay_parent(main_window: Any) -> Any:
    """Resolve the visible Reviewer webview, never an add-on dashboard child."""

    reviewer = getattr(main_window, "reviewer", None)
    for candidate in (
        getattr(reviewer, "web", None),
        getattr(main_window, "web", None),
    ):
        if (
            candidate is not None
            and callable(getattr(candidate, "width", None))
            and callable(getattr(candidate, "height", None))
        ):
            return candidate
    central_widget = getattr(main_window, "centralWidget", None)
    if callable(central_widget):
        candidate = central_widget()
        if candidate is not None:
            return candidate
    return main_window


def reviewer_answer_controls_webview(main_window: Any) -> Any | None:
    """Resolve the WebEngine that actually paints Anki's answer buttons."""

    reviewer = getattr(main_window, "reviewer", None)
    bottom = getattr(reviewer, "bottom", None)
    for candidate in (
        getattr(reviewer, "bottomWeb", None),
        getattr(bottom, "web", None),
        getattr(main_window, "bottomWeb", None),
        getattr(reviewer, "web", None),
    ):
        if (
            candidate is not None
            and callable(getattr(candidate, "width", None))
            and callable(getattr(candidate, "height", None))
            and (
                callable(getattr(candidate, "evalWithCallback", None))
                or callable(getattr(candidate, "page", None))
            )
        ):
            return candidate
    return None


def session_summary_parent(main_window: Any) -> Any:
    """Resolve Anki's current main content after the Reviewer has unmounted."""

    for candidate in (
        getattr(main_window, "web", None),
        (
            main_window.centralWidget()
            if callable(getattr(main_window, "centralWidget", None))
            else None
        ),
    ):
        if (
            candidate is not None
            and callable(getattr(candidate, "width", None))
            and callable(getattr(candidate, "height", None))
        ):
            return candidate
    return main_window


def session_summary_exclusion_measurement_script() -> str:
    """Measure the Home garden card in the summary overlay coordinate space."""

    return r"""
(() => {
  const schemaVersion = 1;
  const source = "home-garden-dom";
  const viewport = {
    width: Math.max(1, Math.round(window.innerWidth || 0)),
    height: Math.max(1, Math.round(window.innerHeight || 0)),
  };
  const root = document.querySelector("#ag-home-root");
  if (!root) {
    return {schema_version: schemaVersion, source, measured: false, viewport};
  }
  const style = window.getComputedStyle(root);
  const rect = root.getBoundingClientRect();
  const measured = !(
    style.display === "none" ||
    style.visibility === "hidden" ||
    Number(style.opacity || "1") === 0 ||
    rect.width <= 0 ||
    rect.height <= 0 ||
    rect.right <= 0 ||
    rect.bottom <= 0 ||
    rect.left >= viewport.width ||
    rect.top >= viewport.height
  );
  return {
    schema_version: schemaVersion,
    source,
    measured,
    viewport,
    rect: measured ? {
      left: Math.max(0, Math.floor(rect.left)),
      top: Math.max(0, Math.floor(rect.top)),
      right: Math.min(viewport.width, Math.ceil(rect.right)),
      bottom: Math.min(viewport.height, Math.ceil(rect.bottom)),
    } : null,
  };
})()
"""


def reviewer_modal_active(main_window: Any) -> bool:
    """Keep reward feedback queued while any application modal is active."""

    active_modal: Any | None = None
    try:
        from aqt.qt import QApplication

        active_modal = QApplication.activeModalWidget()
    except (AttributeError, ImportError, RuntimeError):
        app = getattr(main_window, "app", None)
        resolver = getattr(app, "activeModalWidget", None)
        if callable(resolver):
            try:
                active_modal = resolver()
            except RuntimeError:
                active_modal = None
    return active_modal is not None


@dataclass(frozen=True)
class ReviewerRewardFeedback:
    """One focus-safe reviewer projection for all currently pending rewards."""

    event_id: str
    event_ids: tuple[str, ...]
    kind: str
    message: str
    occurred_at: str
    plant_id: str | None = None
    title: str = ""
    asset_category: str = ""
    asset_key: str = ""
    amount: int = 0
    correlation_id: str = ""
    tier: str = ""
    reward_detail: str = ""
    coins_total: int = 0
    growth_total: int = 0
    environment_total: int = 0
    find_count: int = 0


class GardenToastStack:
    """Shared reviewer-stack geometry and timing contract."""

    MAX_VISIBLE = 2
    PREFERRED_WIDTH = 292
    NARROW_VIEWPORT_WIDTH = 480
    GAP = 8
    AUTO_DISMISS_MS = 5_000
    HOVER_RESUME_MS = 2_000

    @classmethod
    def is_compact(cls, viewport_width: int) -> bool:
        return max(1, int(viewport_width)) <= cls.NARROW_VIEWPORT_WIDTH

    @classmethod
    def toast_width(cls, viewport_width: int) -> int:
        return min(cls.PREFERRED_WIDTH, max(1, int(viewport_width) - 32))

    @classmethod
    def project(cls, pending_count: int, viewport_width: int) -> ReviewerToastProjection:
        """Project pending notifications without exposing a third card."""

        pending_count = max(0, int(pending_count))
        compact = cls.is_compact(viewport_width)
        if pending_count == 0:
            return ReviewerToastProjection(0, 0, compact, False)
        if compact:
            return ReviewerToastProjection(1, pending_count - 1, True, False)
        if pending_count <= cls.MAX_VISIBLE:
            return ReviewerToastProjection(pending_count, 0, False, False)
        return ReviewerToastProjection(
            cls.MAX_VISIBLE,
            pending_count - 1,
            False,
            True,
        )


@dataclass(frozen=True)
class ReviewerToastProjection:
    visible_count: int
    overflow_count: int
    compact: bool
    summary_visible: bool


class ReviewerHookHandler:
    def __init__(
        self,
        engine: Any,
        storage: Any,
        state_changed: Callable[[str], None] | None = None,
        history_invalidated: Callable[[str], None] | None = None,
        open_garden: Callable[..., None] | None = None,
        summary_coordinator: Any | None = None,
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.state_changed = state_changed
        self.history_invalidated = history_invalidated
        self.open_garden = open_garden
        self.summary_coordinator = summary_coordinator
        self._local_answer_fast_path_ready = False
        self._last_notified_event = ""
        self._notified_event_ids: set[str] = set()
        self._reward_toast: Any | None = None
        self._reward_toasts: list[Any] = []
        self._reward_toast_overflow = 0
        self._reward_toast_history: list[Any] = []
        self._reward_list_panel: Any | None = None
        self._reward_feedback_deferred_for_modal = False
        self._reviewer_notice: Any | None = None
        self._reviewer_notice_shown = False
        self._reviewer_session_window: Any | None = None
        self._reviewer_hud: Any | None = None
        self._reviewer_hud_projection: ReviewerHudProjection | None = None
        self._reviewer_hud_reward_state: dict[str, Any] | None = None
        self._reviewer_hud_narrow_forced = False
        self._reviewer_answer_controls_generation = 0
        self._reviewer_growth_pulse: Any | None = None
        # Legacy engines can still produce the exact immutable session event
        # without the newer ``CommittedAnswerResult`` wrapper.  Keep that
        # event in the same pending stream so every value admitted to the live
        # footer is also represented by an expandable reward-history bundle.
        self._pending_reviewer_results: list[
            tuple[CommittedAnswerResult | None, CommittedSessionEvent]
        ] = []
        self._presented_reviewer_result_ids: set[str] = set()
        self._pending_reviewer_acknowledgements: list[CommittedAnswerResult] = []
        self._session_summary_accumulator: SessionSummaryAccumulator | None = None
        self._saved_review_sessions: dict[str, Any] = {}
        self._restored_session_id = ""
        self._profile_closing = False
        self._session_summary_card: Any | None = None
        self._pending_session_summary: Any | None = None
        self._session_summary_render_scheduled = False
        self._session_summary_escape_shortcut: Any | None = None
        self._session_summary_exclusion_filter: Any | None = None
        self._session_summary_exclusion_parent: Any | None = None
        self._session_summary_exclusion_generation = 0
        self._session_cutoff_generation = 0
        self._session_summary_presentation_generation = 0
        self._session_summary_continuation_in_progress = False
        self._presented_session_summary_payload: Any | None = None
        self._review_window_token = ""
        self._review_window_started_after_revlog_id = 0
        self._review_window_answer_revlog_ids: set[int] = set()

    def _session_now_ms(self) -> int:
        resolver = getattr(self.storage, "current_time_ms", None)
        if callable(resolver):
            try:
                return max(0, int(resolver()))
            except Exception:
                pass
        return max(0, int(datetime.now(tz=timezone.utc).timestamp() * 1_000))

    def _session_now_iso(self) -> str:
        return datetime.fromtimestamp(
            self._session_now_ms() / 1_000,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")

    @staticmethod
    def _session_event_iso(answered_at_ms: Any) -> str:
        try:
            event_ms = max(0, int(answered_at_ms))
        except (TypeError, ValueError):
            event_ms = 0
        if event_ms <= 0:
            return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        return datetime.fromtimestamp(
            event_ms / 1_000,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")

    def _today_cards_snapshot(self, *, refresh: bool) -> TodayCardsSnapshot:
        """Freeze one state-driven Today’s Cards projection."""

        state = getattr(self.storage, "state", None)
        completion = getattr(state, "daily_completion", None)
        if refresh and not getattr(self.storage, "runtime_pending", False):
            try:
                resolver = getattr(self.engine, "today_cards_status", None)
                due = getattr(self.storage, "due_obligations", None)
                if callable(resolver):
                    completion = resolver(due() if callable(due) else None)
            except Exception:
                completion = None
        if completion is None:
            return TodayCardsSnapshot(
                status="unavailable",
                cards_total=None,
                scope="unavailable",
            )

        status = str(getattr(completion, "status", "unavailable") or "unavailable")
        if status not in {
            "in_progress",
            "waiting_for_learning",
            "complete",
            "not_eligible",
            "unavailable",
        }:
            status = "unavailable"
        cards_completed = max(
            0,
            int(
                getattr(
                    completion,
                    "starting_required_cards_completed",
                    0,
                )
                or 0
            ),
        )
        waiting_cards = max(
            0,
            int(
                getattr(completion, "future_learning_steps_before_cutoff", 0)
                or 0
            ),
        )
        next_due_at_ms = max(
            0,
            int(getattr(completion, "next_learning_due_at_ms", 0) or 0),
        )
        next_due_seconds = max(
            0,
            int(math.ceil((next_due_at_ms - self._session_now_ms()) / 1_000)),
        ) if next_due_at_ms else 0
        remaining = sum(
            max(0, int(getattr(completion, field, 0) or 0))
            for field in (
                "remaining_new_cards",
                "remaining_required_reviews",
                "remaining_learning_steps",
                "future_learning_steps_before_cutoff",
            )
        )
        currently_due = sum(
            max(0, int(getattr(completion, field, 0) or 0))
            for field in (
                "remaining_new_cards",
                "remaining_required_reviews",
                "remaining_learning_steps",
            )
        )
        verified_remaining = (
            None if status == "unavailable" else (0 if status in {
                "complete", "not_eligible"
            } else remaining)
        )
        if status == "unavailable":
            cards_total = None
        else:
            cards_total = max(
                0,
                int(getattr(completion, "starting_required_cards", 0) or 0),
            )
            if cards_total != (
                cards_completed + max(0, int(verified_remaining or 0))
            ):
                logger.debug(
                    "Anki Garden: Today’s Cards obligation projection is inconsistent"
                )
                return TodayCardsSnapshot(
                    status="unavailable",
                    cards_total=None,
                    scope="unavailable",
                )
        continuation_target = (
            self._review_continuation_target(currently_due)
            if (
                status == "in_progress"
                and currently_due > 0
                and waiting_cards == 0
                and currently_due == max(0, int(verified_remaining or 0))
            )
            else None
        )
        scope = "unavailable" if status == "unavailable" else "all_decks"
        contributing_deck_count = (
            0 if scope == "unavailable" else self._today_contributing_deck_count()
        )
        return TodayCardsSnapshot(
            status=status,
            cards_remaining=verified_remaining,
            cards_completed=cards_completed,
            cards_total=cards_total,
            waiting_cards=waiting_cards,
            currently_due_cards=currently_due,
            next_due_in_seconds=next_due_seconds,
            kind="reviewable",
            scope=scope,
            scope_label="" if scope == "unavailable" else "All decks",
            contributing_deck_count=contributing_deck_count,
            can_continue_reviews=continuation_target is not None,
            continuation_target=continuation_target,
        )

    @staticmethod
    def _due_tree_node_total(node: Any) -> int:
        total = sum(
            max(0, int(getattr(node, primary, getattr(node, fallback, 0)) or 0))
            for primary, fallback in (
                ("new_count", "new"),
                ("learn_count", "lrn"),
                ("review_count", "rev"),
            )
        )
        try:
            deck_id = int(getattr(node, "deck_id", getattr(node, "did", 0)) or 0)
        except (TypeError, ValueError):
            deck_id = 0
        if total == 0 and deck_id == 0:
            return sum(
                ReviewerHookHandler._due_tree_node_total(child)
                for child in tuple(getattr(node, "children", ()) or ())
            )
        return total

    @classmethod
    def _due_tree_contributor_count(cls, node: Any) -> int:
        """Count concrete deck branches contributing cards to one due tree."""

        total = cls._due_tree_node_total(node)
        if total <= 0:
            return 0
        children = tuple(getattr(node, "children", ()) or ())
        child_count = sum(cls._due_tree_contributor_count(child) for child in children)
        child_total = sum(cls._due_tree_node_total(child) for child in children)
        try:
            deck_id = int(getattr(node, "deck_id", getattr(node, "did", 0)) or 0)
        except (TypeError, ValueError):
            deck_id = 0
        direct = 1 if deck_id > 0 and total > child_total else 0
        return max(1 if deck_id > 0 else 0, direct + child_count)

    def _due_tree(self) -> Any | None:
        shared_tree = getattr(self.storage, "due_tree", None)
        if callable(shared_tree):
            return shared_tree()
        collection = getattr(getattr(self.storage, "mw", None), "col", None)
        if collection is None:
            collection = getattr(mw, "col", None)
        scheduler = getattr(collection, "sched", None)
        resolver = getattr(scheduler, "deck_due_tree", None)
        if not callable(resolver):
            return None
        try:
            return resolver()
        except Exception:
            logger.debug(
                "Anki Garden: review continuation tree is unavailable",
                exc_info=True,
            )
            return None

    def _today_contributing_deck_count(self) -> int:
        tree = self._due_tree()
        if tree is None:
            return 1
        return max(1, self._due_tree_contributor_count(tree))

    @classmethod
    def _selectable_due_subtree(cls, node: Any, required_cards: int) -> Any | None:
        """Return the narrowest selectable subtree that owns every Today’s Card."""

        required_cards = max(0, int(required_cards))
        if required_cards <= 0 or cls._due_tree_node_total(node) != required_cards:
            return None
        matching_children = [
            child
            for child in tuple(getattr(node, "children", ()) or ())
            if cls._due_tree_node_total(child) == required_cards
        ]
        if len(matching_children) == 1:
            nested = cls._selectable_due_subtree(matching_children[0], required_cards)
            if nested is not None:
                return nested
        try:
            deck_id = int(getattr(node, "deck_id", getattr(node, "did", 0)) or 0)
        except (TypeError, ValueError):
            deck_id = 0
        return node if deck_id > 0 else None

    def _review_continuation_target(
        self,
        currently_due_cards: int,
    ) -> ReviewContinuationTarget | None:
        if currently_due_cards <= 0:
            return None
        collection = getattr(getattr(self.storage, "mw", None), "col", None) or getattr(mw, "col", None)
        decks = getattr(collection, "decks", None)
        selected = getattr(decks, "get_current_id", None)
        if not callable(selected):
            selected = getattr(decks, "selected", None)
        try:
            current_id = int(selected()) if callable(selected) else 0
        except (TypeError, ValueError):
            return None
        tree = self._due_tree()
        if tree is None or current_id <= 0:
            return None
        # Continue the selected study flow. Remaining work in another deck
        # does not make this receipt a navigation shortcut to that deck.
        pending = [tree]
        node = None
        while pending:
            candidate = pending.pop()
            if int(getattr(candidate, "deck_id", getattr(candidate, "did", 0)) or 0) == current_id:
                node = candidate
                break
            pending.extend(tuple(getattr(candidate, "children", ()) or ()))
        if node is None or self._due_tree_node_total(node) <= 0:
            return None
        try:
            deck_id = int(getattr(node, "deck_id", getattr(node, "did", 0)) or 0)
        except (TypeError, ValueError):
            return None
        children = tuple(getattr(node, "children", ()) or ())
        label = str(
            getattr(node, "name", "")
            or getattr(node, "deck_name", "")
            or ""
        )
        return ReviewContinuationTarget(
            kind="parent_deck" if children else "deck",
            deck_id=deck_id,
            label=label,
        )

    def _effects_snapshot(self, *, at_ms: int | None = None) -> EffectsSnapshot:
        from ..ui.active_consumables import project_active_consumables
        fertilizers: list[FertilizerSnapshot] = []
        boosters: list[BoosterSnapshot] = []
        for effect in project_active_consumables(self.engine, now_ms=at_ms):
            source = effect.source_event_ids[0] if len(effect.source_event_ids) == 1 else ""
            if effect.family == "fertilizer":
                tier = effect.item_id.removeprefix("fertilizer_")
                fertilizers.append(FertilizerSnapshot(
                    effect_id=f"fertilizer:{effect.target_id}:{tier}", name=effect.name,
                    remaining_seconds=0, remaining_cards=effect.remaining_cards,
                    plant_id=effect.target_id, plant_name=effect.target_name, source_event_id=source,
                ))
            else:
                boosters.append(BoosterSnapshot(
                    effect_id=f"booster:{effect.target_id}", remaining_cards=effect.remaining_cards,
                    plant_id=effect.target_id, plant_name=effect.target_name, source_event_id=source,
                ))
        return EffectsSnapshot(tuple(fertilizers), tuple(boosters))

    @staticmethod
    def _plant_growth_units(plant: Any) -> int:
        try:
            return max(0, int(getattr(plant, "growth_units")))
        except (AttributeError, TypeError, ValueError):
            return max(0, int(getattr(plant, "growth_points", 0) or 0)) * 100

    @staticmethod
    def _owned_environment_ids(state: Any) -> frozenset[str]:
        """Return canonical ownership plus supported migration-window aliases."""

        inventory = getattr(state, "inventory", {}) or {}
        feature_ids = tuple(inventory.get("garden_features", ()) or ())
        legacy_weather_ids = tuple(inventory.get("weather", ()) or ())
        owned = {
            str(item_id)
            for item_id in (*feature_ids, *legacy_weather_ids)
            if str(item_id)
        }
        owned.update(
            canonical_garden_feature_id(item_id)
            for item_id in (*feature_ids, *legacy_weather_ids)
            if canonical_garden_feature_id(item_id)
        )
        owned.update(
            str(item_id)
            for item_id in tuple(inventory.get("scenery", ()) or ())
            if str(item_id)
        )
        return frozenset(owned)

    def _plant_art_asset(self, plant: Any) -> str:
        resolver = getattr(self.engine, "resolve_plant_asset", None)
        if not callable(resolver):
            return ""
        try:
            asset = resolver(
                str(getattr(plant, "species", "") or ""),
                str(getattr(plant, "growth_stage", "seed") or "seed"),
            )
            return str(getattr(asset, "path", "") or "")
        except Exception:
            return ""

    def _session_start_snapshot(self) -> SessionStartSnapshot:
        state = getattr(self.storage, "state", None)
        plants = tuple(getattr(state, "plants", ()) or ())
        milestone_ids: set[str] = set()
        for plant in plants:
            plant_id = str(getattr(plant, "plant_id", "") or "")
            for claim in tuple(getattr(plant, "checkpoint_claims", ()) or ()):
                try:
                    next_stage, percent = str(claim).split(":", 1)
                except ValueError:
                    continue
                milestone_ids.add(
                    f"stage_checkpoint:{plant_id}:{next_stage}:{percent}"
                )
            milestone_ids.update(
                f"stage:{plant_id}:{stage}"
                for stage in tuple(getattr(plant, "stage_reward_claims", ()) or ())
            )
        outcomes = getattr(state, "garden_find_outcomes", {}) or {}
        owned_environment_ids = self._owned_environment_ids(state)
        return SessionStartSnapshot(
            today_cards=self._today_cards_snapshot(refresh=True),
            effects=self._effects_snapshot(),
            coin_balance=max(0, int(getattr(state, "currency_balance", 0) or 0)),
            stored_growth_units=max(
                0, int(getattr(state, "stored_growth_units", 0) or 0)
            ),
            plants=tuple(
                PlantStateSnapshot(
                    str(getattr(plant, "plant_id", "") or "unknown"),
                    self._plant_growth_units(plant),
                    str(getattr(plant, "growth_stage", "") or ""),
                )
                for plant in plants
                if str(getattr(plant, "plant_id", "") or "")
            ),
            existing_event_ids=frozenset((
                *(
                    self._transaction_identity(item)
                    for item in tuple(
                        getattr(state, "currency_transactions", ()) or ()
                    )
                ),
                *(
                    str(getattr(item, "event_key", "") or "")
                    for item in tuple(
                        getattr(state, "recent_reward_receipts", ()) or ()
                    )
                    if str(getattr(item, "event_key", "") or "")
                ),
            )),
            existing_standard_find_event_ids=frozenset(str(key) for key in outcomes),
            existing_milestone_event_ids=frozenset(milestone_ids),
            owned_environment_ids=owned_environment_ids,
        )

    def _session_end_snapshot(self, *, refresh_today: bool) -> SessionEndSnapshot:
        return SessionEndSnapshot(
            self._today_cards_snapshot(refresh=refresh_today),
            self._effects_snapshot(),
        )

    def _begin_session_summary(
        self,
        *,
        today_cards_available: bool = True,
    ) -> None:
        day = self.scheduler_day(self.storage)
        try:
            begin_feature_session = getattr(self.engine, "begin_review_session", None)
            if callable(begin_feature_session):
                begin_feature_session()
            start_snapshot = self._session_start_snapshot()
            if not today_cards_available:
                start_snapshot = replace(
                    start_snapshot,
                    today_cards=TodayCardsSnapshot(
                        status="unavailable",
                        cards_total=None,
                        scope="unavailable",
                    ),
                )
            self._session_summary_accumulator = SessionSummaryAccumulator(
                session_id=(
                    f"review-session:{self._review_window_token}"
                    if self._review_window_token
                    else f"review-session:{uuid.uuid4().hex}"
                ),
                started_at=self._session_now_iso(),
                anki_day_id=day,
                start_snapshot=start_snapshot,
            )
            begin_activity = getattr(self.storage, "begin_activity_session", None)
            if callable(begin_activity):
                begin_activity(self._session_summary_accumulator.session_id,
                               self._session_summary_accumulator.started_at)
            self._schedule_session_cutoff_split()
        except Exception:
            logger.debug(
                "Anki Garden: Session Summary could not start",
                exc_info=True,
            )
            self._session_summary_accumulator = None

    def _schedule_session_cutoff_split(self) -> None:
        """Arm one in-memory cutoff check for a still-open reviewer session."""

        accumulator = self._session_summary_accumulator
        if accumulator is None:
            return
        bounds = getattr(self.storage, "current_scheduler_day_bounds_ms", None)
        if not callable(bounds):
            return
        try:
            _day_start_ms, cutoff_ms = bounds()
            delay_ms = max(1, int(cutoff_ms) - self._session_now_ms() + 25)
            from aqt.qt import QTimer
        except Exception:
            return
        self._session_cutoff_generation += 1
        generation = self._session_cutoff_generation
        QTimer.singleShot(
            min(delay_ms, 2_000_000_000),
            lambda: self._on_session_cutoff(generation),
        )

    def _on_session_cutoff(self, generation: int) -> None:
        accumulator = self._session_summary_accumulator
        if (
            accumulator is None
            or int(generation) != self._session_cutoff_generation
        ):
            return
        current_day = self.scheduler_day(self.storage)
        if current_day == accumulator.current_anki_day_id:
            # Scheduler authorities can update a fraction after the nominal
            # boundary. Retry without blocking Anki's event loop.
            try:
                from aqt.qt import QTimer

                QTimer.singleShot(500, lambda: self._on_session_cutoff(generation))
            except Exception:
                pass
            return
        old_end_snapshot = self._session_end_snapshot(refresh_today=False)
        try:
            observe = getattr(self.engine, "observe_due_start", None)
            due = getattr(self.storage, "due_obligations", None)
            if callable(observe):
                observe(due() if callable(due) else None)
        except Exception:
            logger.debug(
                "Anki Garden: Today’s Cards baseline was unavailable at cutoff",
                exc_info=True,
            )
        self._split_session_summary_day_if_needed(
            current_day=current_day,
            old_end_snapshot=old_end_snapshot,
        )

    def _split_session_summary_day_if_needed(
        self,
        *,
        current_day: str,
        old_end_snapshot: SessionEndSnapshot | None = None,
    ) -> None:
        accumulator = self._session_summary_accumulator
        if accumulator is None or current_day == accumulator.current_anki_day_id:
            return
        ended_at = self._session_now_iso()
        try:
            accumulator.split_anki_day(
                ended_at=ended_at,
                end_snapshot=(
                    old_end_snapshot
                    if old_end_snapshot is not None
                    else self._session_end_snapshot(refresh_today=False)
                ),
                next_anki_day_id=current_day,
                next_started_at=ended_at,
                next_start_snapshot=self._session_start_snapshot(),
            )
            self._schedule_session_cutoff_split()
        except Exception:
            logger.debug(
                "Anki Garden: Session Summary day split was unavailable",
                exc_info=True,
            )

    @staticmethod
    def _transaction_identity(transaction: Any) -> str:
        return str(
            getattr(transaction, "transaction_id", "")
            or getattr(transaction, "event_key", "")
            or id(transaction)
        )

    @staticmethod
    def _reward_receipt_identity(receipt: Any) -> tuple[Any, ...]:
        return (
            str(getattr(receipt, "event_key", "") or ""),
            str(getattr(receipt, "reward_type", "") or ""),
            str(getattr(receipt, "source", "") or ""),
            str(getattr(receipt, "source_id", "") or ""),
            str(getattr(receipt, "correlation_id", "") or ""),
            int(getattr(receipt, "amount", 0) or 0),
            str(getattr(receipt, "item_id", "") or ""),
            str(getattr(receipt, "plant_id", "") or ""),
        )

    def _session_event_baseline(self) -> dict[str, Any]:
        state = getattr(self.storage, "state", None)
        plants = tuple(getattr(state, "plants", ()) or ())
        return {
            "plant_units": {
                str(getattr(plant, "plant_id", "") or ""): self._plant_growth_units(plant)
                for plant in plants
                if str(getattr(plant, "plant_id", "") or "")
            },
            "stored_units": max(0, int(getattr(state, "stored_growth_units", 0) or 0)),
            "landmark_units": max(
                0,
                int(
                    getattr(
                        getattr(state, "garden_project", None),
                        "contributed_growth_units",
                        0,
                    )
                    or 0
                ),
            ),
            "transaction_ids": {
                self._transaction_identity(item)
                for item in tuple(getattr(state, "currency_transactions", ()) or ())
            },
            "find_outcome_ids": set(
                str(key)
                for key in (getattr(state, "garden_find_outcomes", {}) or {})
            ),
            "reward_receipt_ids": {
                self._reward_receipt_identity(item)
                for item in tuple(
                    getattr(state, "recent_reward_receipts", ()) or ()
                )
            },
            "owned_environment_ids": set(self._owned_environment_ids(state)),
        }

    def _result_plant_art_asset(self, plant: Any) -> str:
        resolver = getattr(self.engine, "resolve_plant_asset", None)
        if not callable(resolver) or plant is None:
            return ""
        try:
            asset = resolver(
                str(getattr(plant, "species", "") or ""),
                str(
                    getattr(plant, "stage", "")
                    or getattr(plant, "growth_stage", "seed")
                    or "seed"
                ),
            )
            return str(getattr(asset, "path", "") or "")
        except Exception:
            return ""

    @timed("review.session-event")
    def _session_event_from_result(
        self,
        result: CommittedAnswerResult,
    ) -> CommittedSessionEvent | None:
        """Translate one immutable engine result without reading mutable state."""

        event_id = str(result.event_id or result.correlation_id or "")
        if not event_id:
            return None
        before = {plant.plant_id: plant for plant in result.plants_before}
        after = {plant.plant_id: plant for plant in result.plants_after}
        shared_by_plant: dict[str, int] = {}
        for allocation in tuple(result.award.allocations or ()):
            if str(getattr(allocation, "role", "") or "") != "passive":
                continue
            plant_id = str(getattr(allocation, "plant_id", "") or "")
            units = max(0, int(getattr(allocation, "applied_units", 0) or 0))
            if plant_id and units:
                shared_by_plant[plant_id] = (
                    shared_by_plant.get(plant_id, 0) + units
                )

        plant_growth: list[PlantGrowthDelta] = []
        shared_growth: list[PlantGrowthDelta] = []
        for plant_id, current in after.items():
            previous_units = max(
                0,
                int(getattr(before.get(plant_id), "growth_units", 0) or 0),
            )
            delta = max(0, int(current.growth_units) - previous_units)
            shared = min(delta, shared_by_plant.get(plant_id, 0))
            common = {
                "plant_id": plant_id,
                "plant_name": PlantIdentity.from_plant(current).display_name,
                "species_name": str(current.species or "").replace("_", " ").title(),
                "art_asset": self._result_plant_art_asset(current),
            }
            if delta - shared > 0:
                plant_growth.append(PlantGrowthDelta(
                    growth_units=delta - shared,
                    **common,
                ))
            if shared > 0:
                shared_growth.append(PlantGrowthDelta(
                    growth_units=shared,
                    **common,
                ))

        coin_awards = tuple(
            CoinAward(
                event_id=str(
                    getattr(transaction, "transaction_id", "")
                    or getattr(transaction, "event_key", "")
                ),
                source_type=str(getattr(transaction, "source", "") or "garden_reward"),
                source_label=str(getattr(transaction, "reason", "") or "Garden reward"),
                amount=max(0, int(getattr(transaction, "delta", 0) or 0)),
                event_key=str(getattr(transaction, "event_key", "") or ""),
                transaction_id=str(getattr(transaction, "transaction_id", "") or ""),
                source_id=str(getattr(transaction, "source_id", "") or ""),
                correlation_id=str(getattr(transaction, "correlation_id", "") or event_id),
                included_in_total=bool(
                    getattr(transaction, "included_in_total", True)
                ),
            )
            for transaction in result.currency_transactions
            if int(getattr(transaction, "delta", 0) or 0) > 0
        )
        coin_by_event_key = {
            award.event_key: award
            for award in coin_awards
            if award.event_key
        }

        standard_finds = tuple(
            StandardFind(
                event_id=str(getattr(outcome, "outcome_key", "") or outcome.answer_key),
                find_id=str(outcome.reward_id or "garden_find"),
                find_name=str(outcome.display_name or "Garden Find"),
                rarity=str(outcome.tier or ""),
                reward_type=str(outcome.reward_type or ""),
                reward_label=str(outcome.description or ""),
                reward_amount=max(0, int(outcome.amount or 0)),
                art_asset=standard_find_artwork_ref(
                    str(outcome.reward_id or ""),
                    str(outcome.artwork_ref or ""),
                ),
                occurred_at=str(outcome.occurred_at or ""),
                item_id=str(outcome.item_id or ""),
                quantity=1,
                notable=_standard_find_is_notable(outcome),
            )
            for outcome in result.garden_find_outcomes
            if str(outcome.pool_id or "") == "standard"
            and str(outcome.status or "") == "hit"
        )

        milestones: list[PlantMilestone] = []
        stage_rows: dict[str, list[tuple[str, Any, str]]] = {}
        for transaction in result.currency_transactions:
            event_key = str(getattr(transaction, "event_key", "") or "")
            parts = event_key.split(":")
            if len(parts) == 4 and parts[0] == "stage_checkpoint":
                _kind, plant_id, next_stage, percent_text = parts
                plant = after.get(plant_id) or before.get(plant_id)
                if plant is None:
                    continue
                try:
                    percent = max(0, int(percent_text))
                except (TypeError, ValueError):
                    continue
                coin = coin_by_event_key.get(event_key)
                milestones.append(PlantMilestone(
                    event_id=event_key,
                    plant_id=plant_id,
                    plant_name=plant_species_name(plant),
                    milestone_type="checkpoint",
                    occurred_at=str(getattr(transaction, "occurred_at", "") or self._session_now_iso()),
                    plant_art_asset=self._result_plant_art_asset(plant),
                    plant_class=str(getattr(plant, "species", "") or "")
                    .replace("_", " ")
                    .title(),
                    checkpoint_percent=percent,
                    new_stage=next_stage,
                    coin_reward=(coin.amount if coin is not None else 0),
                    coin_award_event_ids=(coin.event_id,) if coin is not None else (),
                    coin_included_in_total=(
                        coin.included_in_total if coin is not None else False
                    ),
                ))
            elif len(parts) == 3 and parts[0] == "stage":
                _kind, plant_id, next_stage = parts
                stage_rows.setdefault(plant_id, []).append((
                    next_stage,
                    transaction,
                    event_key,
                ))

        for plant_id, crossings in stage_rows.items():
            plant = after.get(plant_id) or before.get(plant_id)
            if plant is None:
                continue
            ordered = sorted(
                crossings,
                key=lambda item: (
                    GROWTH_STAGES.index(item[0])
                    if item[0] in GROWTH_STAGES
                    else len(GROWTH_STAGES),
                    item[2],
                ),
            )
            first_stage = ordered[0][0]
            try:
                first_index = GROWTH_STAGES.index(first_stage)
                previous_stage = GROWTH_STAGES[max(0, first_index - 1)]
            except ValueError:
                previous_stage = ""
            for next_stage, transaction, event_key in ordered:
                coin = coin_by_event_key.get(event_key)
                milestones.append(PlantMilestone(
                    event_id=event_key,
                    plant_id=plant_id,
                    plant_name=plant_species_name(plant),
                    milestone_type=(
                        "full_bloom" if next_stage == "rare" else "stage_change"
                    ),
                    occurred_at=str(
                        getattr(transaction, "occurred_at", "")
                        or self._session_now_iso()
                    ),
                    plant_art_asset=self._result_plant_art_asset(plant),
                    plant_class=str(getattr(plant, "species", "") or "")
                    .replace("_", " ")
                    .title(),
                    previous_stage=previous_stage,
                    new_stage=next_stage,
                    stage_path=tuple(
                        value
                        for value in (previous_stage, next_stage)
                        if value
                    ),
                    coin_reward=(coin.amount if coin is not None else 0),
                    coin_award_event_ids=(coin.event_id,) if coin is not None else (),
                    coin_included_in_total=(
                        coin.included_in_total if coin is not None else False
                    ),
                ))
                previous_stage = next_stage

        discoveries: list[EnvironmentDiscovery] = []
        seen_discoveries: set[str] = set()
        for receipt in result.reward_receipts:
            if str(receipt.source or "") != "garden_find_environment":
                continue
            item_id = canonical_garden_feature_id(
                receipt.item_id or receipt.source_id or ""
            )
            if not item_id or item_id in seen_discoveries:
                continue
            seen_discoveries.add(item_id)
            item = WEATHER_CATALOG.get(item_id) or SCENERY_CATALOG.get(item_id)
            if item is None:
                continue
            discoveries.append(EnvironmentDiscovery(
                event_id=f"{receipt.event_key}:{item_id}",
                environment_id=item_id,
                environment_name=str(getattr(item, "name", "") or item_id.replace("_", " ").title()),
                environment_kind=(
                    "garden_feature"
                    if str(getattr(item, "kind", "")) == "garden_feature"
                    else str(getattr(item, "kind", "") or "scenery")
                ),
                rarity=str(getattr(item, "rarity", "") or ""),
                art_asset=item_id,
                effect_summary=str(
                    getattr(item, "effect", "") or "Garden decoration or scenery"
                ),
                occurred_at=str(receipt.occurred_at or self._session_now_iso()),
            ))

        project_allocations: list[SessionProjectGrowthAllocation] = []
        for allocation in tuple(
            getattr(result, "project_allocations", ()) or ()
        ):
            target_type = getattr(allocation, "target_type", "")
            target_type = getattr(target_type, "value", target_type)
            units = int(getattr(allocation, "units", 0) or 0)
            # Engine projections may carry zero-unit quotes; Session rows are
            # committed credit only and therefore remain strictly positive.
            if units <= 0:
                continue
            project_allocations.append(SessionProjectGrowthAllocation(
                target_type=str(target_type),
                target_id=str(getattr(allocation, "target_id", "") or ""),
                units=units,
            ))

        return CommittedSessionEvent(
            event_id=event_id,
            anki_day_id=str(result.scheduler_day or self.scheduler_day(self.storage)),
            occurred_at=self._session_event_iso(result.occurred_at_ms),
            cards_completed=max(0, int(result.cards_completed)),
            plant_growth=tuple(plant_growth),
            shared_growth=tuple(shared_growth),
            stored_growth_delta_units=int(result.stored_growth_delta_units),
            project_allocations=tuple(project_allocations),
            landmark_growth_delta_units=max(
                0, int(result.landmark_growth_delta_units)
            ),
            coin_awards=coin_awards,
            standard_finds=standard_finds,
            milestones=tuple(milestones),
            environment_discoveries=tuple(discoveries),
            reward_receipts=tuple(result.reward_receipts),
            total_finds=max(0, int(result.standard_find_count)),
        )

    def _committed_session_event(
        self,
        *,
        payload: Mapping[str, Any],
        award: Any,
        baseline: Mapping[str, Any],
    ) -> CommittedSessionEvent | None:
        """Translate one proven local commit into immutable exact facts."""

        event_id = str(getattr(award, "correlation_id", "") or "")
        if not event_id:
            return None
        state = getattr(self.storage, "state", None)
        plants = tuple(getattr(state, "plants", ()) or ())
        plants_by_id = {
            str(getattr(plant, "plant_id", "") or ""): plant
            for plant in plants
            if str(getattr(plant, "plant_id", "") or "")
        }
        before_units = dict(baseline.get("plant_units", {}) or {})
        after_units = {
            plant_id: self._plant_growth_units(plant)
            for plant_id, plant in plants_by_id.items()
        }
        shared_by_plant: dict[str, int] = {}
        for allocation in tuple(getattr(award, "allocations", ()) or ()):
            if str(getattr(allocation, "role", "") or "") != "passive":
                continue
            plant_id = str(getattr(allocation, "plant_id", "") or "")
            units = max(0, int(getattr(allocation, "applied_units", 0) or 0))
            if plant_id and units:
                shared_by_plant[plant_id] = shared_by_plant.get(plant_id, 0) + units

        def growth_delta(plant_id: str, units: int) -> PlantGrowthDelta:
            plant = plants_by_id[plant_id]
            return PlantGrowthDelta(
                plant_id,
                PlantIdentity.from_plant(plant).display_name,
                units,
                str(getattr(plant, "species", "") or "").replace("_", " ").title(),
                self._plant_art_asset(plant),
            )

        plant_growth: list[PlantGrowthDelta] = []
        shared_growth: list[PlantGrowthDelta] = []
        for plant_id, current in after_units.items():
            applied = max(0, current - max(0, int(before_units.get(plant_id, 0) or 0)))
            shared = min(applied, max(0, int(shared_by_plant.get(plant_id, 0) or 0)))
            if applied - shared > 0:
                plant_growth.append(growth_delta(plant_id, applied - shared))
            if shared > 0:
                shared_growth.append(growth_delta(plant_id, shared))

        previous_transaction_ids = set(baseline.get("transaction_ids", set()) or set())
        new_transactions = tuple(
            item
            for item in tuple(getattr(state, "currency_transactions", ()) or ())
            if self._transaction_identity(item) not in previous_transaction_ids
            and int(getattr(item, "delta", 0) or 0) > 0
        )
        coin_awards = tuple(
            CoinAward(
                event_id=self._transaction_identity(item),
                source_type=str(getattr(item, "source", "") or "garden_reward"),
                source_label=str(getattr(item, "reason", "") or "Garden reward"),
                amount=int(getattr(item, "delta", 0) or 0),
                event_key=str(getattr(item, "event_key", "") or ""),
                transaction_id=str(getattr(item, "transaction_id", "") or ""),
                source_id=str(getattr(item, "source_id", "") or ""),
                correlation_id=str(
                    getattr(item, "correlation_id", "") or event_id
                ),
                included_in_total=bool(
                    getattr(item, "included_in_total", True)
                ),
            )
            for item in new_transactions
        )
        coin_by_event_key = {
            item.event_key: item for item in coin_awards if item.event_key
        }

        previous_find_ids = set(baseline.get("find_outcome_ids", set()) or set())
        outcomes = getattr(state, "garden_find_outcomes", {}) or {}
        standard_finds: list[StandardFind] = []
        for outcome_key, outcome in outcomes.items():
            if str(outcome_key) in previous_find_ids:
                continue
            if (
                str(getattr(outcome, "pool_id", "") or "") != "standard"
                or str(getattr(outcome, "status", "") or "") != "hit"
            ):
                continue
            reward_label = str(getattr(outcome, "description", "") or "")
            standard_finds.append(StandardFind(
                str(outcome_key),
                str(getattr(outcome, "reward_id", "") or "garden_find"),
                str(getattr(outcome, "display_name", "") or "Garden Find"),
                str(getattr(outcome, "tier", "") or ""),
                str(getattr(outcome, "reward_type", "") or ""),
                reward_label,
                max(0, int(getattr(outcome, "amount", 0) or 0)),
                standard_find_artwork_ref(
                    str(getattr(outcome, "reward_id", "") or ""),
                    str(getattr(outcome, "artwork_ref", "") or ""),
                ),
                str(getattr(outcome, "occurred_at", "") or ""),
                str(getattr(outcome, "item_id", "") or ""),
                1,
                _standard_find_is_notable(outcome),
            ))

        transaction_by_key = {
            str(getattr(item, "event_key", "") or ""): item
            for item in new_transactions
        }
        milestones: list[PlantMilestone] = []
        stage_transactions: dict[str, list[tuple[str, Any, str]]] = {}
        for reward_key, transaction in transaction_by_key.items():
            parts = reward_key.split(":")
            if len(parts) == 4 and parts[0] == "stage_checkpoint":
                _kind, plant_id, next_stage, percent_text = parts
                plant = plants_by_id.get(plant_id)
                if plant is None:
                    continue
                try:
                    percent = max(0, int(percent_text))
                except (TypeError, ValueError):
                    continue
                coin = coin_by_event_key.get(reward_key)
                milestones.append(PlantMilestone(
                    reward_key,
                    plant_id,
                    PlantIdentity.from_plant(plant).display_name,
                    "checkpoint",
                    str(getattr(transaction, "occurred_at", "") or self._session_now_iso()),
                    self._plant_art_asset(plant),
                    plant_class=str(getattr(plant, "species", "") or "")
                    .replace("_", " ")
                    .title(),
                    checkpoint_percent=percent,
                    new_stage=next_stage,
                    coin_reward=(coin.amount if coin is not None else 0),
                    coin_award_event_ids=(coin.event_id,) if coin is not None else (),
                    coin_included_in_total=(
                        coin.included_in_total if coin is not None else False
                    ),
                ))
            elif len(parts) == 3 and parts[0] == "stage":
                _kind, plant_id, next_stage = parts
                stage_transactions.setdefault(plant_id, []).append((
                    next_stage,
                    transaction,
                    reward_key,
                ))

        for plant_id, crossings in stage_transactions.items():
            plant = plants_by_id.get(plant_id)
            if plant is None:
                continue
            ordered_crossings = sorted(
                crossings,
                key=lambda item: (
                    GROWTH_STAGES.index(item[0])
                    if item[0] in GROWTH_STAGES
                    else len(GROWTH_STAGES),
                    item[2],
                ),
            )
            first_stage = ordered_crossings[0][0]
            try:
                first_index = GROWTH_STAGES.index(first_stage)
                previous_stage = GROWTH_STAGES[max(0, first_index - 1)]
            except ValueError:
                previous_stage = ""
            for next_stage, transaction, event_key in ordered_crossings:
                coin = coin_by_event_key.get(event_key)
                milestones.append(PlantMilestone(
                    event_key,
                    plant_id,
                    PlantIdentity.from_plant(plant).display_name,
                    "full_bloom" if next_stage == "rare" else "stage_change",
                    str(
                        getattr(transaction, "occurred_at", "")
                        or self._session_now_iso()
                    ),
                    self._plant_art_asset(plant),
                    plant_class=str(getattr(plant, "species", "") or "")
                    .replace("_", " ")
                    .title(),
                    previous_stage=previous_stage,
                    new_stage=next_stage,
                    stage_path=tuple(
                        value
                        for value in (previous_stage, next_stage)
                        if value
                    ),
                    coin_reward=(coin.amount if coin is not None else 0),
                    coin_award_event_ids=(coin.event_id,) if coin is not None else (),
                    coin_included_in_total=(
                        coin.included_in_total if coin is not None else False
                    ),
                ))
                previous_stage = next_stage

        owned_before = set(baseline.get("owned_environment_ids", set()) or set())
        discoveries: list[EnvironmentDiscovery] = []
        for item_id in tuple(getattr(award, "garden_find_ids", ()) or ()):
            legacy_id = str(item_id or "")
            normalized = canonical_garden_feature_id(legacy_id)
            if (
                not normalized
                or normalized in owned_before
                or legacy_id in owned_before
            ):
                continue
            catalog = WEATHER_CATALOG if normalized in WEATHER_CATALOG else SCENERY_CATALOG
            item = catalog.get(normalized)
            if item is None:
                continue
            discoveries.append(EnvironmentDiscovery(
                f"{event_id}:environment:{normalized}",
                normalized,
                str(getattr(item, "name", "") or normalized.replace("_", " ").title()),
                (
                    "garden_feature"
                    if str(getattr(item, "kind", "")) == "garden_feature"
                    else str(getattr(item, "kind", "") or "scenery")
                ),
                str(getattr(item, "rarity", "") or ""),
                normalized,
                str(
                    getattr(item, "effect", "") or "Garden decoration or scenery"
                ),
                self._session_event_iso(payload.get("answered_at_ms", 0)),
            ))

        stored_after = max(0, int(getattr(state, "stored_growth_units", 0) or 0))
        stored_before = max(0, int(baseline.get("stored_units", 0) or 0))
        landmark_after = max(
            0,
            int(
                getattr(
                    getattr(state, "garden_project", None),
                    "contributed_growth_units",
                    0,
                )
                or 0
            ),
        )
        landmark_before = max(
            0, int(baseline.get("landmark_units", 0) or 0)
        )
        previous_receipt_ids = set(
            baseline.get("reward_receipt_ids", set()) or set()
        )
        reward_receipts = tuple(
            item
            for item in tuple(
                getattr(state, "recent_reward_receipts", ()) or ()
            )
            if self._reward_receipt_identity(item) not in previous_receipt_ids
        )
        return CommittedSessionEvent(
            event_id=event_id,
            anki_day_id=str(payload.get("scheduler_day") or self.scheduler_day(self.storage)),
            occurred_at=self._session_event_iso(payload.get("answered_at_ms", 0)),
            cards_completed=1,
            plant_growth=tuple(plant_growth),
            shared_growth=tuple(shared_growth),
            stored_growth_delta_units=stored_after - stored_before,
            landmark_growth_delta_units=max(
                0, landmark_after - landmark_before
            ),
            coin_awards=coin_awards,
            standard_finds=tuple(standard_finds),
            milestones=tuple(milestones),
            environment_discoveries=tuple(discoveries),
            reward_receipts=reward_receipts,
            total_finds=sum(item.quantity for item in standard_finds),
        )

    def on_question(self, *_args: Any, **_kwargs: Any) -> None:
        """Show one non-modal eligibility reminder before a reviewer answer."""
        runtime = getattr(self.storage, "runtime_coordinator", None)
        if runtime is not None:
            runtime.request("review question")
        if getattr(self.storage, "runtime_pending", False):
            if self._session_summary_accumulator is None:
                self._start_reviewer_session_totals(today_cards_available=False)
            self._ensure_reviewer_hud()
            return
        current_day = self.scheduler_day(self.storage)
        accumulator = self._session_summary_accumulator
        old_end_snapshot = None
        if (
            accumulator is not None
            and current_day != accumulator.current_anki_day_id
        ):
            # Freeze the outgoing day before observe_due_start rolls the engine
            # into Anki's new scheduler day.
            old_end_snapshot = self._session_end_snapshot(refresh_today=False)
        try:
            observe = getattr(self.engine, "observe_due_start", None)
            if callable(observe):
                observe(self.storage.due_obligations())
        except Exception:
            logger.debug(
                "Anki Garden: unable to record the pre-answer due baseline",
                exc_info=True,
            )
        if old_end_snapshot is not None:
            self._split_session_summary_day_if_needed(
                current_day=current_day,
                old_end_snapshot=old_end_snapshot,
            )

        reviewer_window = getattr(mw, "reviewer", None)
        if reviewer_window is not None and reviewer_window is not self._reviewer_session_window:
            self._reviewer_session_window = reviewer_window
            self._reviewer_notice_shown = False
            self._hide_no_starter_notice()
            self._start_reviewer_session_totals()

        if bool(getattr(getattr(self.storage, "state", None), "starter_selection_complete", False)):
            self._hide_no_starter_notice()
            self._ensure_reviewer_hud()
            if (
                self._reward_feedback_deferred_for_modal
                and not reviewer_modal_active(mw)
            ):
                self._reward_feedback_deferred_for_modal = False
                self._show_optional_progress_feedback()
            return
        if self._reviewer_notice_shown:
            return
        self._reviewer_notice_shown = True
        self._show_no_starter_notice()

    def on_answer_shown(self, *_args: Any, **_kwargs: Any) -> None:
        """Refresh measured answer-button geometry after Anki reveals it."""

        if str(getattr(mw, "state", "") or "") != "review":
            return
        if getattr(self, "_reviewer_hud", None) is None:
            self._ensure_reviewer_hud()
            return
        self._request_reviewer_answer_control_geometry(
            reviewer_overlay_parent(mw)
        )

    def on_starter_selected(self) -> None:
        """Remove the session reminder as soon as starter persistence succeeds."""

        self._reviewer_notice_shown = False
        self._hide_no_starter_notice()
        self._ensure_reviewer_hud()

    def refresh_from_external_state(self) -> None:
        """Refresh an open HUD after sync/maintenance without replaying rewards."""

        if str(getattr(mw, "state", "") or "") != "review":
            return
        self._ensure_reviewer_hud()

    def on_state_will_change(
        self,
        new_state: str,
        old_state: str = "",
        *_args: Any,
    ) -> None:
        """Dismiss an already-presented summary before unrelated navigation."""

        if self._session_summary_continuation_in_progress:
            return
        if str(old_state or "") != "review" or str(new_state or "") == "review":
            self.dismiss_session_summary_for_navigation()

    def on_state_change(
        self,
        new_state: str,
        old_state: str = "",
        *_args: Any,
    ) -> None:
        """Unmount Reviewer-only feedback before another Anki surface paints."""

        if str(new_state or "") == "review":
            self._hide_session_summary(clear_pending=True)
            self._ensure_reviewer_hud()
            return
        if str(old_state or "") == "review":
            self._show_reviewer_session_summary()
        elif not self._session_summary_continuation_in_progress:
            self.dismiss_session_summary_for_navigation()
        self._hide_reward_toast()
        self._hide_reviewer_hud()
        self._hide_no_starter_notice()
        self._reviewer_session_window = None
        self._reviewer_notice_shown = False
        self._reviewer_hud_narrow_forced = False
        self.present_saved_review_session()

    def _start_reviewer_session_totals(
        self,
        *,
        today_cards_available: bool = True,
    ) -> None:
        """Start the event-sourced local session after the first question."""

        self._reviewer_session_window = getattr(mw, "reviewer", None)
        self._pending_reviewer_results = []
        self._presented_reviewer_result_ids = set()
        self._reviewer_hud_reward_state = None
        self._review_window_token = uuid.uuid4().hex
        self._review_window_started_after_revlog_id = max(
            0,
            int(
                getattr(
                    getattr(self.storage, "state", None),
                    "last_processed_revlog_id",
                    0,
                )
                or 0
            ),
        )
        self._review_window_answer_revlog_ids = set()
        self._begin_session_summary(
            today_cards_available=today_cards_available,
        )

    def _show_reviewer_session_summary(self) -> None:
        if self._review_window_answer_revlog_ids and getattr(self.storage, "runtime_pending", False):
            self.preserve_session_for_close(closing=False)
        accumulator = self._session_summary_accumulator
        self._session_summary_accumulator = None
        self._review_window_token = ""
        self._review_window_started_after_revlog_id = 0
        self._review_window_answer_revlog_ids = set()
        end_feature_session = getattr(self.engine, "end_review_session", None)
        if callable(end_feature_session):
            end_feature_session()
        self._session_cutoff_generation += 1
        if accumulator is None:
            return
        try:
            finish_activity = getattr(self.storage, "finish_activity_session", None)
            if callable(finish_activity):
                try:
                    finish_activity(accumulator.session_id, self._session_now_iso())
                except Exception:
                    logger.exception("Anki Garden: session end could not be saved")
            accumulator.finalize(
                ended_at=self._session_now_iso(),
                end_snapshot=self._session_end_snapshot(refresh_today=True),
            )
            payload = accumulator.take_finalized_payload()
        except Exception:
            logger.debug(
                "Anki Garden: Session Summary could not be finalized",
                exc_info=True,
            )
            return
        if payload is None:
            return
        self._session_summary_presentation_generation += 1
        self._pending_session_summary = payload
        self._refresh_post_session_surfaces()
        self._schedule_session_summary_render()

    def _save_review_sessions(self) -> None:
        manager = getattr(mw, "pm", None)
        profile = getattr(manager, "profile", None)
        if isinstance(profile, dict):
            profile["anki_garden_review_sessions"] = dict(self._saved_review_sessions)
            manager.save()

    def restore_review_sessions(self) -> None:
        """Load only this Anki profile's unshown local sessions."""
        self._profile_closing = False
        # Anki may import add-ons before selecting a profile. Its profile
        # attribute exists but is None until profile_did_open retries recovery.
        profile = getattr(getattr(mw, "pm", None), "profile", None)
        raw = profile.get("anki_garden_review_sessions", {}) if isinstance(profile, dict) else {}
        self._saved_review_sessions = dict(raw) if isinstance(raw, dict) else {}
        for session_id, record in tuple(self._saved_review_sessions.items()):
            try:
                if record["version"] != 1:
                    raise ValueError("Unsupported saved session version")
                if "payload" in record:
                    if not isinstance(decode_session_record(record["payload"]), SessionSummaryPayload):
                        raise ValueError("Invalid saved session payload")
                else:
                    SessionSummaryAccumulator.from_recovery_checkpoint(record["checkpoint"])
                    if not isinstance(decode_session_record(record["end"]), SessionEndSnapshot):
                        raise ValueError("Invalid saved session ending")
                    {int(value) for value in record["pending_ids"]}
            except (KeyError, TypeError, ValueError, AttributeError):
                logger.exception("Anki Garden: invalid saved session was ignored")
                self._saved_review_sessions.pop(session_id)

    def preserve_session_for_close(self, *, closing: bool = True) -> None:
        """Called after cancellable close dialogs, while the collection is open."""
        accumulator = self._session_summary_accumulator
        if accumulator is not None:
            ended_at = self._session_now_iso()
            end = self._session_end_snapshot(refresh_today=False)
            if accumulator.cards_completed or self._review_window_answer_revlog_ids:
                self._saved_review_sessions[accumulator.session_id] = {
                    "version": 1, "checkpoint": accumulator.recovery_checkpoint(),
                    "pending_ids": sorted(self._review_window_answer_revlog_ids),
                    "ended_at": ended_at, "end": encode_session_record(end),
                }
        elif self._pending_session_summary is not None:
            payload = self._pending_session_summary
            self._saved_review_sessions[payload.session_id] = {
                "version": 1, "payload": encode_session_record(payload),
            }
        self._save_review_sessions()
        end_feature_session = getattr(self.engine, "end_review_session", None)
        if callable(end_feature_session):
            end_feature_session()
        self._profile_closing = closing
        self._session_summary_accumulator = None
        self._review_window_token = ""
        self._review_window_answer_revlog_ids = set()
        self._session_cutoff_generation += 1

    def accept_reconciled_results(self, results: Any) -> None:
        """Route delayed local commits back to their original review session."""
        local = [row for row in results if row.origin in {"local", "local_recovery"}]
        accumulator = self._session_summary_accumulator
        for result in local:
            if RUNTIME_PERFORMANCE.enabled:
                RUNTIME_PERFORMANCE.answer_stage("committed", str(result.event_id),
                    related_answer_id=str(result.occurred_at_ms), reason="reconciled")
            if accumulator is not None and result.occurred_at_ms in self._review_window_answer_revlog_ids:
                event = self._session_event_from_result(result)
                if event is not None and accumulator.accept_committed(event):
                    self._pending_reviewer_results.append((result, event))
                self._review_window_answer_revlog_ids.discard(result.occurred_at_ms)
        changed = False
        for record in self._saved_review_sessions.values():
            pending = set(record.get("pending_ids", ()))
            matching = [row for row in local if row.occurred_at_ms in pending]
            if not matching:
                continue
            accumulator = SessionSummaryAccumulator.from_recovery_checkpoint(record["checkpoint"])
            for result in matching:
                event = self._session_event_from_result(result)
                if event is not None:
                    accumulator.accept_committed(event)
                pending.discard(result.occurred_at_ms)
            record["checkpoint"] = accumulator.recovery_checkpoint()
            record["pending_ids"] = sorted(pending)
            changed = True
        if changed:
            self._save_review_sessions()

    def present_saved_review_session(self) -> None:
        if (self._profile_closing or getattr(self.storage, "runtime_pending", False)
                or self._pending_session_summary is not None or self._session_summary_card is not None
                or str(getattr(mw, "state", "")) not in {"deckBrowser", "overview"}):
            return
        for session_id, record in tuple(self._saved_review_sessions.items()):
            try:
                if record["version"] != 1:
                    raise ValueError("Unsupported saved session version")
                if "payload" in record:
                    payload = decode_session_record(record["payload"])
                else:
                    accumulator = SessionSummaryAccumulator.from_recovery_checkpoint(record["checkpoint"])
                    # Verification has settled; an unmatched deferred answer may
                    # have been undone. Only committed events enter the receipt.
                    payload = accumulator.finalize(ended_at=record["ended_at"],
                                                   end_snapshot=decode_session_record(record["end"]))
                if payload is None:
                    del self._saved_review_sessions[session_id]
                    self._save_review_sessions()
                    continue
                if not isinstance(payload, SessionSummaryPayload):
                    raise ValueError("Invalid saved Session Summary")
                finish_activity = getattr(self.storage, "finish_activity_session", None)
                if callable(finish_activity):
                    try:
                        finish_activity(session_id, payload.ended_at)
                    except Exception:
                        logger.exception("Anki Garden: recovered session end could not be saved")
                self._restored_session_id = session_id
                self._pending_session_summary = payload
                self._session_summary_presentation_generation += 1
                self._schedule_session_summary_render()
                return
            except (KeyError, TypeError, ValueError, AttributeError):
                logger.exception("Anki Garden: saved session summary could not be restored")
                # A malformed presentation record must not disable rewards or
                # repeatedly block all other summaries. Keep it for diagnosis.
                self._saved_review_sessions.pop(session_id)

    def close_for_profile(self) -> None:
        self._profile_closing = True
        self._restored_session_id = ""
        self._hide_session_summary(clear_pending=True)
        self._hide_reviewer_hud()
        self._session_summary_accumulator = None
        self._reviewer_session_window = None
        self._pending_reviewer_results = []
        self._review_window_answer_revlog_ids = set()
        self._review_window_token = ""
        self._session_cutoff_generation += 1

    def _refresh_post_session_surfaces(self) -> None:
        """Refresh the visible Anki/Garden state before mounting the summary.

        Session Summary is deliberately nonmodal, so the Deck Browser or
        Overview behind it is part of the same presentation.  Publish one
        post-commit revision before asking Anki to repaint that surface; the
        home Garden banner and the frozen summary payload will then read the
        same committed storage state.
        """

        if callable(self.state_changed):
            try:
                self.state_changed("Session summary committed")
            except Exception:
                logger.debug(
                    "Anki Garden: post-session state revision could not be published",
                    exc_info=True,
                )
        state_name = str(getattr(mw, "state", "") or "")
        surface_name = {
            "deckBrowser": "deckBrowser",
            "overview": "overview",
        }.get(state_name)
        if surface_name is None:
            return
        runtime = getattr(self.storage, "runtime_coordinator", None)
        if runtime is not None:
            # Anki is already completing this navigation. Update only Garden
            # after the transition instead of loading the whole page twice.
            from aqt.qt import QTimer
            QTimer.singleShot(0, runtime.app._refresh_home_surface)
            return
        try:
            surface = getattr(mw, surface_name, None)
            refresh = getattr(surface, "refresh", None)
            if callable(refresh):
                refresh()
        except Exception:
            # Rewards are already committed and the summary remains useful;
            # a repaint failure must never roll state back or block dismissal.
            logger.debug(
                "Anki Garden: post-session Anki surface could not refresh",
                exc_info=True,
            )

    def _dispose_session_summary_exclusion_tracking(self) -> None:
        """Detach the Home-card geometry watcher owned by a summary card."""

        geometry_filter = self._session_summary_exclusion_filter
        parent = self._session_summary_exclusion_parent
        self._session_summary_exclusion_filter = None
        self._session_summary_exclusion_parent = None
        self._session_summary_exclusion_generation += 1
        if geometry_filter is None:
            return
        if parent is not None:
            try:
                parent.removeEventFilter(geometry_filter)
            except (AttributeError, RuntimeError, TypeError):
                pass
        try:
            geometry_filter.deleteLater()
        except (AttributeError, RuntimeError):
            pass

    def _request_session_summary_exclusion_geometry(
        self,
        card: Any,
        parent: Any,
        *,
        retries_remaining: int = 0,
    ) -> bool:
        """Keep the nonmodal summary clear of the painted Home garden card."""

        if (
            card is None
            or card is not self._session_summary_card
            or parent is not self._session_summary_exclusion_parent
        ):
            return False
        try:
            from aqt.qt import QTimer

            parent_width = max(1, int(parent.width()))
            parent_height = max(1, int(parent.height()))
        except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
            return False

        self._session_summary_exclusion_generation += 1
        generation = self._session_summary_exclusion_generation

        def retry() -> None:
            if retries_remaining <= 0:
                return
            QTimer.singleShot(
                120,
                lambda: self._request_session_summary_exclusion_geometry(
                    card,
                    parent,
                    retries_remaining=retries_remaining - 1,
                ),
            )

        def accept(payload: Any) -> None:
            if (
                generation != self._session_summary_exclusion_generation
                or card is not self._session_summary_card
                or parent is not self._session_summary_exclusion_parent
            ):
                return
            row = payload if isinstance(payload, dict) else {}
            viewport = row.get("viewport")
            rect = row.get("rect")
            measured = bool(
                row.get("schema_version") == 1
                and row.get("source") == "home-garden-dom"
                and row.get("measured") is True
                and isinstance(viewport, dict)
                and abs(int(viewport.get("width", 0) or 0) - parent_width) <= 2
                and abs(int(viewport.get("height", 0) or 0) - parent_height) <= 2
                and isinstance(rect, dict)
            )
            reserved_top: int | None = None
            horizontal_overlap = False
            if measured:
                try:
                    root_left = int(rect.get("left", -1))
                    root_right = int(rect.get("right", -1))
                    root_bottom = int(rect.get("bottom", -1))
                    card_left = int(card.x())
                    card_right = card_left + int(card.width())
                    horizontal_overlap = bool(
                        min(root_right, card_right) > max(root_left, card_left)
                    )
                    if horizontal_overlap and 0 < root_bottom < parent_height:
                        reserved_top = root_bottom
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    measured = False
                    reserved_top = None
            try:
                card.setProperty("summaryHomeClearanceMeasured", measured)
                card.setProperty(
                    "summaryHomeClearanceHorizontalOverlap",
                    horizontal_overlap,
                )
                card.setProperty("summaryHomeClearanceTelemetry", dict(row))
                card.set_reserved_top(
                    reserved_top,
                    source=(
                        "home-garden-dom"
                        if reserved_top is not None else
                        "none"
                    ),
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return
            if not measured:
                retry()

        script = session_summary_exclusion_measurement_script()
        evaluate = getattr(parent, "evalWithCallback", None)
        if callable(evaluate):
            try:
                evaluate(script, accept)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.debug(
                    "Anki Garden: Home garden geometry could not be measured",
                    exc_info=True,
                )
        try:
            page = parent.page()
            run_javascript = getattr(page, "runJavaScript", None)
        except (AttributeError, RuntimeError, TypeError):
            run_javascript = None
        if callable(run_javascript):
            try:
                run_javascript(script, accept)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.debug(
                    "Anki Garden: Home geometry bridge failed",
                    exc_info=True,
                )
        accept(None)
        return False

    def _install_session_summary_exclusion_tracking(
        self,
        card: Any,
        parent: Any,
    ) -> None:
        """Re-measure the Home card whenever the native host is resized."""

        self._dispose_session_summary_exclusion_tracking()
        try:
            from aqt.qt import QEvent, QObject, QTimer
        except ImportError:
            return
        owner = self

        class _SessionSummaryExclusionFilter(QObject):
            def eventFilter(self, watched: Any, event: Any) -> bool:
                if (
                    watched is parent
                    and event.type() in {
                        QEvent.Type.Resize,
                        QEvent.Type.Show,
                        QEvent.Type.LayoutRequest,
                    }
                ):
                    QTimer.singleShot(
                        0,
                        lambda: owner._request_session_summary_exclusion_geometry(
                            card,
                            parent,
                            retries_remaining=2,
                        ),
                    )
                return False

        geometry_filter = _SessionSummaryExclusionFilter(card)
        try:
            parent.installEventFilter(geometry_filter)
        except (AttributeError, RuntimeError, TypeError):
            geometry_filter.deleteLater()
            return
        self._session_summary_exclusion_filter = geometry_filter
        self._session_summary_exclusion_parent = parent
        card.setProperty("summaryHomeClearanceTracking", True)
        QTimer.singleShot(
            0,
            lambda: self._request_session_summary_exclusion_geometry(
                card,
                parent,
                retries_remaining=8,
            ),
        )

    def _hide_session_summary(self, *, clear_pending: bool = False) -> None:
        card = self._session_summary_card
        self._session_summary_card = None
        self._dispose_session_summary_exclusion_tracking()
        if card is not None:
            try:
                card.close()
            except (AttributeError, RuntimeError):
                pass
        shortcut = self._session_summary_escape_shortcut
        self._session_summary_escape_shortcut = None
        self._dispose_session_summary_shortcut(shortcut)
        coordinator = self.summary_coordinator
        release = getattr(coordinator, "release", None)
        if callable(release):
            release("session")
        if clear_pending:
            self._restored_session_id = ""
            self._session_summary_presentation_generation += 1
            self._pending_session_summary = None
            self._session_summary_render_scheduled = False
            self._presented_session_summary_payload = None

    @staticmethod
    def _dispose_session_summary_shortcut(shortcut: Any | None) -> None:
        if shortcut is None:
            return
        try:
            shortcut.setEnabled(False)
        except (AttributeError, RuntimeError):
            pass
        try:
            shortcut.deleteLater()
        except (AttributeError, RuntimeError):
            pass

    def _schedule_session_summary_render(self, delay_ms: int = 0) -> None:
        if self._session_summary_render_scheduled:
            return
        if self._pending_session_summary is None:
            return
        self._session_summary_render_scheduled = True
        generation = self._session_summary_presentation_generation
        try:
            from aqt.qt import QTimer

            QTimer.singleShot(
                max(0, int(delay_ms)),
                lambda: self._present_pending_session_summary(generation),
            )
        except Exception:
            self._session_summary_render_scheduled = False
            logger.debug(
                "Anki Garden: Session Summary render could not be scheduled",
                exc_info=True,
            )

    @staticmethod
    def _anki_is_closing() -> bool:
        try:
            from aqt.qt import QApplication

            closing = getattr(QApplication, "closingDown", None)
            return bool(closing()) if callable(closing) else False
        except Exception:
            return False

    def _present_pending_session_summary(
        self,
        expected_generation: int | None = None,
    ) -> None:
        if (
            expected_generation is not None
            and int(expected_generation)
            != self._session_summary_presentation_generation
        ):
            return
        self._session_summary_render_scheduled = False
        payload = self._pending_session_summary
        if payload is None:
            return
        if self._profile_closing or self._anki_is_closing():
            return
        if (getattr(self.storage, "runtime_pending", False)
                or str(getattr(mw, "state", "")) not in {"deckBrowser", "overview"}):
            self._schedule_session_summary_render(150)
            return
        if reviewer_modal_active(mw):
            self._schedule_session_summary_render(150)
            return
        card: Any | None = None
        shortcut: Any | None = None
        try:
            from aqt.qt import QKeySequence, QShortcut, Qt
            from ..ui.session_summary_card import SessionSummaryCard

            parent = session_summary_parent(mw)
            self._hide_session_summary(clear_pending=False)
            coordinator = self.summary_coordinator
            acquire = getattr(coordinator, "acquire", None)
            if callable(acquire):
                acquire("session", self._dismiss_session_summary)
            card = SessionSummaryCard(
                parent,
                payload,
                on_dismiss=self._dismiss_session_summary,
                on_open_garden=self._open_garden_from_session_summary,
                on_continue_reviews=self._continue_reviews_from_session_summary,
                engine=self.engine,
                animations_enabled=self._session_summary_animations_enabled(),
            )
            card.show()
            shortcut = QShortcut(QKeySequence("Escape"), mw)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self._dismiss_session_summary_on_escape)
            self._session_summary_card = card
            self._session_summary_escape_shortcut = shortcut
            self._install_session_summary_exclusion_tracking(card, parent)
            self._presented_session_summary_payload = payload
            self._pending_session_summary = None
            if self._restored_session_id:
                self._saved_review_sessions.pop(self._restored_session_id, None)
                self._restored_session_id = ""
                try:
                    self._save_review_sessions()
                except Exception:
                    logger.exception("Anki Garden: presented session receipt could not be cleared")
        except Exception:
            self._dispose_session_summary_shortcut(shortcut)
            dispose_unmounted_summary_card(card)
            release = getattr(self.summary_coordinator, "release", None)
            if callable(release):
                release("session")
            logger.debug(
                "Anki Garden: Session Summary could not be rendered",
                exc_info=True,
            )

    def _dismiss_session_summary_on_escape(self) -> None:
        if reviewer_modal_active(mw):
            return
        coordinator = self.summary_coordinator
        owns = getattr(coordinator, "owns", None)
        if callable(owns) and not bool(owns("session")):
            return
        dismiss_active = getattr(coordinator, "dismiss", None)
        if callable(dismiss_active):
            dismiss_active("escape")
            return
        self._dismiss_session_summary()

    def _dismiss_session_summary(self) -> None:
        self._hide_session_summary(clear_pending=True)
        self.present_saved_review_session()

    def dismiss_session_summary_for_navigation(self, *_args: Any) -> None:
        """Cancel both visible and delayed summary presentation exactly once."""

        if self._session_summary_continuation_in_progress:
            return
        self._hide_session_summary(clear_pending=True)

    def _session_summary_animations_enabled(self) -> bool:
        try:
            from ..ui.accessibility import effective_motion_enabled

            return effective_motion_enabled(
                bool(self._hud_config_value(
                    "enable_animations",
                    DEFAULT_CONFIG["enable_animations"],
                )),
                bool(self._hud_config_value(
                    "reduced_motion",
                    DEFAULT_CONFIG["reduced_motion"],
                )),
            )
        except Exception:
            return False

    def _continue_reviews_from_session_summary(self) -> bool:
        """Start Anki's reviewer for the revalidated continuation deck.

        The card deliberately stays mounted until the transition succeeds;
        this gives keyboard and pointer users a recoverable failure state.
        """

        payload = self._presented_session_summary_payload
        terminal_today = getattr(payload, "terminal_today_cards", None)
        target = getattr(terminal_today, "continuation_target", None)
        if (
            terminal_today is None
            or not bool(getattr(terminal_today, "can_continue_reviews", False))
            or target is None
        ):
            return False

        original_deck_id: int | None = None
        select_deck: Callable[[int], Any] | None = None
        target_deck_id: int | None = None
        try:
            refreshed = self._today_cards_snapshot(refresh=True)
            refreshed_target = getattr(refreshed, "continuation_target", None)
            if (
                not bool(getattr(refreshed, "can_continue_reviews", False))
                or refreshed_target is None
                or str(getattr(refreshed, "scope", ""))
                != str(getattr(terminal_today, "scope", ""))
                or str(getattr(refreshed, "kind", ""))
                != str(getattr(terminal_today, "kind", ""))
                or str(getattr(refreshed_target, "kind", ""))
                != str(getattr(target, "kind", ""))
                or getattr(refreshed_target, "deck_id", None)
                != getattr(target, "deck_id", None)
            ):
                return False
            move_to_state = getattr(mw, "moveToState", None)
            collection = getattr(mw, "col", None)
            start_timebox = getattr(collection, "startTimebox", None)
            if not callable(move_to_state) or not callable(start_timebox):
                return False
            decks = getattr(collection, "decks", None)
            select_deck = getattr(decks, "select", None)
            target_deck_id = getattr(target, "deck_id", None)
            if target_deck_id is None or not callable(select_deck):
                return False
            current_id_resolver = getattr(decks, "get_current_id", None)
            if not callable(current_id_resolver):
                current_id_resolver = getattr(decks, "selected", None)
            original_deck_id = (
                int(current_id_resolver())
                if callable(current_id_resolver)
                else None
            )
            select_deck(int(target_deck_id))
            if (
                callable(current_id_resolver)
                and int(current_id_resolver()) != int(target_deck_id)
            ):
                if original_deck_id is not None:
                    select_deck(original_deck_id)
                return False
            self._session_summary_continuation_in_progress = True
            # Overview.refresh() renders asynchronously. Visiting overview here
            # can overwrite the review page after its bridge handler is active,
            # leaving a visible Study now button that the reviewer cannot handle.
            start_timebox()
            move_to_state("review")
            succeeded = str(getattr(mw, "state", "") or "") == "review"
            if succeeded:
                self._hide_session_summary(clear_pending=True)
            elif original_deck_id is not None:
                select_deck(original_deck_id)
            return succeeded
        except Exception:
            if (
                callable(select_deck)
                and original_deck_id is not None
                and str(getattr(mw, "state", "") or "") != "review"
            ):
                try:
                    select_deck(original_deck_id)
                except Exception:
                    pass
            logger.debug(
                "Anki Garden: reviews could not resume from Session Summary",
                exc_info=True,
            )
            return False
        finally:
            self._session_summary_continuation_in_progress = False

    def _open_garden_from_session_summary(self) -> None:
        callback = self.open_garden
        self._dismiss_session_summary()
        if not callable(callback):
            return
        try:
            from aqt.qt import QTimer

            QTimer.singleShot(0, callback)
        except Exception:
            logger.debug(
                "Anki Garden: Garden could not open from Session Summary",
                exc_info=True,
            )

    def _open_garden_from_reviewer_hud(self) -> None:
        callback = self.open_garden
        if not callable(callback):
            return
        try:
            callback()
        except Exception:
            logger.debug(
                "Anki Garden: Garden could not open from Reviewer HUD",
                exc_info=True,
            )

    def _open_collection_from_reviewer_hud(self) -> None:
        """Open the app-owned Collection route without leaving a stale HUD."""

        garden_callback = self.open_garden
        owner = getattr(garden_callback, "__self__", None)
        callback = getattr(owner, "open_collection", None)
        if not callable(callback):
            return
        try:
            callback()
        except Exception:
            logger.debug(
                "Anki Garden: Collection could not open from Reviewer HUD",
                exc_info=True,
            )

    def _open_supplies_from_reviewer_hud(self, group: str) -> None:
        owner = getattr(self.open_garden, "__self__", None)
        callback = getattr(owner, "open_supplies", None)
        if callable(callback):
            callback(group)

    def _open_activity_from_reviewer_hud(self) -> None:
        owner = getattr(self.open_garden, "__self__", None)
        callback = getattr(owner, "open_activity", None)
        if callable(callback):
            callback()

    def _save_reviewer_hud_position(self, position: dict[str, Any]) -> None:
        self._persist_hud_preferences(reviewer_hud_position=position)

    def _open_active_plant_from_reviewer_hud(self, plant_id: str = "") -> None:
        callback = self.open_garden
        if not callable(callback):
            return
        plant_id = str(plant_id or getattr(
            getattr(self.storage, "state", None),
            "active_plant_id",
            "",
        ) or "")
        try:
            callback(plant_id=plant_id)
        except TypeError:
            callback()
        except Exception:
            logger.debug(
                "Anki Garden: active plant could not open from Reviewer HUD",
                exc_info=True,
            )

    def _select_another_plant_from_reviewer_hud(self) -> None:
        """Open plant selection while leaving the current reviewer state intact."""

        callback = self.open_garden
        if not callable(callback):
            return
        try:
            callback(select_another_plant=True)
        except TypeError:
            # Compatibility with integrations that still expose the former
            # no-argument Garden opener. They can still reach the Garden even
            # though only the current add-on provides the direct selector.
            callback()
        except Exception:
            logger.debug(
                "Anki Garden: plant selection could not open from Reviewer HUD",
                exc_info=True,
            )

    def _choose_plant_from_reviewer_hud(self, plant_id: str) -> bool:
        """Atomically nurture one projected choice without leaving Reviewer."""

        plant_id = str(plant_id or "")
        setter = getattr(self.engine, "set_active_plant", None)
        if not plant_id or not callable(setter):
            return False
        try:
            ok, _message = setter(plant_id)
        except Exception:
            logger.debug(
                "Anki Garden: reviewer plant choice could not be committed",
                exc_info=True,
            )
            return False
        if not bool(ok):
            logger.debug(
                "Anki Garden: reviewer plant choice was rejected by the engine"
            )
            return False
        if callable(self.state_changed):
            try:
                self.state_changed("Active plant changed")
            except Exception:
                logger.debug(
                    "Anki Garden: reviewer plant choice could not publish state",
                    exc_info=True,
                )
        # Refresh the mounted projection in place. This deliberately leaves
        # the current Anki card and the session accumulator untouched.
        self._ensure_reviewer_hud()
        return True

    def _resolve_reviewer_reward_art(self, hero: Any) -> Any | None:
        """Resolve canonical reward references without teaching the widget catalogs."""

        kind_source = getattr(hero, "kind", "") or getattr(hero, "reward_type", "")
        kind = str(getattr(kind_source, "value", kind_source) or "")
        if kind in {"full_bloom", "stage_change"}:
            species = str(getattr(hero, "plant_class", "") or "").casefold().replace(" ", "_")
            if not species:
                plant_id = str(getattr(hero, "plant_id", "") or "")
                plant = next((plant for plant in getattr(getattr(self.engine, "state", None), "plants", ())
                              if str(getattr(plant, "plant_id", "")) == plant_id), None)
                species = str(getattr(plant, "species", "") or "")
            stage = "rare" if kind == "full_bloom" else str(getattr(hero, "new_stage", "") or "")
            resolver = getattr(self.engine, "resolve_plant_asset", None)
            if species and stage and callable(resolver):
                try:
                    resolved = resolver(species, stage)
                    if resolved is not None:
                        return resolved
                except Exception:
                    pass
        asset_key = str(
            hero
            if isinstance(hero, str)
            else getattr(hero, "artwork_ref", "")
            or getattr(hero, "art_asset", "")
            or ""
        )
        if kind == "checkpoint":
            asset_key = "checkpoint_badge"
        elif not asset_key and getattr(hero, "inventory_items", ()):
            asset_key = str(hero.inventory_items[0][0])
        elif kind == "coin_or_booster" and not getattr(hero, "inventory_items", ()):
            if asset_key.removeprefix("ui_") in {"", "garden_coin", "garden_coins", "growth", "growth_resource"}:
                asset_key = "garden_reward"
        if not asset_key:
            return None
        # Garden Finds retain the logical Growth reference in their ledger;
        # the current artwork catalog names the same resource explicitly.
        asset_key = {"growth": "growth_resource"}.get(asset_key, asset_key)
        resolver_names = (
            (
                "resolve_garden_feature_preview_asset",
                "resolve_scenery_preview_asset",
                "resolve_item_asset",
            )
            if kind == "environment_discovery"
            else ("resolve_item_asset", "resolve_garden_feature_preview_asset", "resolve_scenery_preview_asset")
        )
        for resolver_name in resolver_names:
            resolver = getattr(self.engine, resolver_name, None)
            if not callable(resolver):
                continue
            try:
                resolved = resolver(asset_key)
            except Exception:
                continue
            if resolved is not None:
                return resolved
        return None

    def _hud_config_value(self, key: str, default: Any) -> Any:
        config = getattr(self.engine, "config", None)
        resolver = getattr(config, "value", None)
        if not callable(resolver):
            return default
        try:
            return resolver(key, default)
        except Exception:
            return default

    def _persist_hud_preferences(self, **changes: Any) -> None:
        config = getattr(self.engine, "config", None)
        persist = getattr(config, "update", None)
        if not callable(persist):
            return
        try:
            persist(dict(changes))
        except Exception:
            logger.debug(
                "Anki Garden: Reviewer HUD preference could not be saved",
                exc_info=True,
            )

    def _hide_reviewer_hud(self) -> None:
        self._reviewer_answer_controls_generation += 1
        panel = getattr(self, "_reviewer_hud", None)
        parent = getattr(self, "_reviewer_hud_parent", None)
        resize_filter = getattr(self, "_reviewer_hud_parent_filter", None)
        if panel is not None:
            export_reward_state = getattr(panel, "export_reward_state", None)
            if callable(export_reward_state):
                try:
                    self._reviewer_hud_reward_state = dict(export_reward_state())
                except Exception:
                    logger.debug(
                        "Anki Garden: Reviewer HUD reward state could not be preserved",
                        exc_info=True,
                    )
        self._reviewer_hud = None
        self._reviewer_hud_projection = None
        self._reviewer_growth_pulse = None
        self._reviewer_hud_parent = None
        self._reviewer_hud_parent_filter = None
        if parent is not None and resize_filter is not None:
            try:
                parent.removeEventFilter(resize_filter)
                resize_filter.deleteLater()
            except RuntimeError:
                pass
        if panel is None:
            return
        try:
            dispose = getattr(panel, "dispose", None)
            if callable(dispose):
                dispose()
            else:
                panel.hide()
                panel.deleteLater()
        except Exception:
            pass

    def set_reviewer_hud_dock(self, side: str) -> None:
        """Persist the supported left/right dock choice and repaint in place."""

        dock = "left" if str(side) == "left" else "right"
        self._persist_hud_preferences(reviewer_hud_dock=dock, reviewer_hud_position={"custom": False, "x": 1.0, "y": 0.0})
        self._ensure_reviewer_hud(force_dock=dock)

    def _toggle_reviewer_hud(self, collapsed: bool | None = None) -> None:
        projection = getattr(self, "_reviewer_hud_projection", None)
        if collapsed is None:
            collapsed = not bool(getattr(projection, "collapsed", False))
        else:
            collapsed = bool(collapsed)
        self._reviewer_hud_narrow_forced = True
        self._persist_hud_preferences(reviewer_hud_collapsed=collapsed)
        self._ensure_reviewer_hud(force_collapsed=collapsed)

    @timed("review.session-totals")
    def _update_reviewer_hud_session_totals(self) -> None:
        panel = getattr(self, "_reviewer_hud", None)
        accumulator = self._session_summary_accumulator
        update_totals = getattr(panel, "update_session_totals", None)
        if accumulator is None or not callable(update_totals):
            return
        try:
            snapshot = accumulator.hud_snapshot() if hasattr(accumulator, "hud_snapshot") else accumulator.live_snapshot(
                ended_at=self._session_now_iso(),
                end_snapshot=self._session_end_snapshot(refresh_today=False),
            )
            update_totals(snapshot)
        except Exception:
            logger.debug(
                "Anki Garden: Reviewer HUD session totals could not refresh",
                exc_info=True,
            )

    def _acknowledge_reviewer_result_feedback(
        self,
        result: CommittedAnswerResult,
    ) -> None:
        peek = getattr(self.engine, "peek_feedback", None)
        if not callable(peek):
            return
        try:
            matching = [
                event
                for event in tuple(peek())
                if self._feedback_correlation_id(event)
                == str(result.correlation_id)
            ]
        except Exception:
            return
        if not matching:
            return
        self._notified_event_ids.update(
            str(getattr(event, "event_id", "") or "")
            for event in matching
            if str(getattr(event, "event_id", "") or "")
        )
        self._acknowledge_presented_feedback(matching)

    def _retry_reviewer_feedback_acknowledgements(self) -> None:
        if not self._notified_event_ids:
            return
        peek = getattr(self.engine, "peek_feedback", None)
        if not callable(peek):
            return
        try:
            self._acknowledge_presented_feedback(list(peek()))
        except Exception:
            return

    @timed("review.feedback")
    def _flush_pending_reviewer_results(self) -> None:
        panel = getattr(self, "_reviewer_hud", None)
        present_committed = getattr(panel, "present_committed_result", None)
        present_reward = getattr(panel, "present_reward", None)
        notify_committed = getattr(panel, "notify_committed_card", None)
        if (
            not callable(present_committed)
            and not callable(present_reward)
            and not callable(notify_committed)
        ):
            return
        try:
            from ..reward_presentation import project_committed_reward_bundle
        except Exception:
            return
        reveal = bool(self._hud_config_value(
            "show_progress_notifications",
            DEFAULT_CONFIG.get("show_progress_notifications", True),
        ))
        remaining: list[
            tuple[CommittedAnswerResult | None, CommittedSessionEvent]
        ] = []
        blocked = False
        for result, session_event in self._pending_reviewer_results:
            result_id = str(
                (result.event_id or result.correlation_id)
                if result is not None
                else session_event.event_id
            )
            if result_id in self._presented_reviewer_result_ids:
                continue
            if blocked:
                remaining.append((result, session_event))
                continue
            try:
                bundle = project_committed_reward_bundle(
                    session_event,
                    receipts=(
                        result.reward_receipts
                        if result is not None
                        else session_event.reward_receipts
                    ),
                )
                if bundle is not None and callable(present_committed):
                    applied_growth_units = (
                        max(0, int(result.award.total_growth_units))
                        if result is not None
                        else (
                            sum(
                                max(0, int(item.growth_units))
                                for item in session_event.plant_growth
                            )
                            + max(
                                0,
                                int(session_event.stored_growth_delta_units),
                            )
                        )
                    )
                    accepted = bool(
                        present_committed(
                            bundle,
                            applied_growth_units=applied_growth_units,
                            reveal=reveal,
                        )
                    )
                elif bundle is not None:
                    accepted = bool(present_reward(bundle, reveal=reveal))
                elif callable(notify_committed):
                    accepted = bool(notify_committed(result_id))
                else:
                    accepted = True
                if not accepted:
                    blocked = True
                    remaining.append((result, session_event))
                    continue
            except Exception:
                logger.debug(
                    "Anki Garden: committed reward bundle could not enter the HUD",
                    exc_info=True,
                )
                blocked = True
                remaining.append((result, session_event))
                continue
            self._presented_reviewer_result_ids.add(result_id)
            if result is not None:
                self._pending_reviewer_acknowledgements.append(result)
        self._pending_reviewer_results = remaining
        self._update_reviewer_hud_session_totals()
        defer = getattr(panel, "defer_until_feedback_paint", None)
        if callable(defer):
            defer(self._finish_reviewer_feedback_acknowledgements)
        else:
            self._finish_reviewer_feedback_acknowledgements()

    def _finish_reviewer_feedback_acknowledgements(self) -> None:
        results = self._pending_reviewer_acknowledgements
        self._pending_reviewer_acknowledgements = []
        for result in results:
            self._acknowledge_reviewer_result_feedback(result)
        self._retry_reviewer_feedback_acknowledgements()

    @timed("review.hud")
    def _ensure_reviewer_hud(
        self,
        *,
        force_collapsed: bool | None = None,
        force_dock: str | None = None,
    ) -> None:
        """Mount or refresh one focus-safe HUD inside the Reviewer webview."""

        panel = getattr(self, "_reviewer_hud", None)
        if (force_collapsed is None and force_dock is None
                and str(getattr(mw, "state", "")) == "review"
                and bool(getattr(panel, "feedback_paint_pending", False))):
            # A next-question hook can arrive before the first paint of the
            # answer result. Keep its scheduled refresh behind that paint too.
            defer = getattr(panel, "defer_until_feedback_paint", None)
            if callable(defer):
                defer(self._ensure_reviewer_hud)
                return
        self._reviewer_hud_refresh_queued = False

        if str(getattr(mw, "state", "") or "") != "review":
            self._hide_reviewer_hud()
            return
        if not bool(self._hud_config_value(
            "show_reviewer_hud",
            DEFAULT_CONFIG.get("show_reviewer_hud", True),
        )):
            self._hide_reviewer_hud()
            return
        state = getattr(self.storage, "state", None)
        if state is None or not bool(getattr(state, "starter_selection_complete", False)):
            self._hide_reviewer_hud()
            return
        parent = reviewer_overlay_parent(mw)
        reviewer = getattr(mw, "reviewer", None)
        reviewer_web = getattr(reviewer, "web", None)
        if reviewer_web is None or parent is not reviewer_web:
            self._hide_reviewer_hud()
            return
        try:
            viewport_width = max(1, int(parent.width()))
            viewport_height = max(1, int(parent.height()))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            self._hide_reviewer_hud()
            return

        saved_collapsed = bool(self._hud_config_value("reviewer_hud_collapsed", False))
        if force_collapsed is None:
            collapsed = saved_collapsed
            if (
                self._reviewer_hud is None
                and not self._reviewer_hud_narrow_forced
                and should_start_collapsed(viewport_width, saved_collapsed)
            ):
                collapsed = True
                self._reviewer_hud_narrow_forced = True
        else:
            collapsed = bool(force_collapsed)
        dock = (
            str(force_dock)
            if force_dock is not None
            else str(self._hud_config_value("reviewer_hud_dock", "right"))
        )
        projection = project_reviewer_hud(
            self.engine,
            state,
            collapsed=collapsed,
            dock=dock,
            position=self._hud_config_value("reviewer_hud_position", {}),
        )
        self._render_reviewer_hud(
            parent,
            projection,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    def _publish_reviewer_answer_controls_telemetry(
        self,
        parent: Any,
        telemetry: Mapping[str, Any] | None,
        *,
        generation: int,
        viewport_width: int,
        viewport_height: int,
    ) -> bool:
        """Publish the measured WebEngine rectangle in Qt logical pixels."""

        setter = getattr(parent, "setProperty", None)
        if not callable(setter):
            return False
        if telemetry is None:
            values: dict[str, Any] = {
                "reviewerAnswerControlsSchemaVersion": (
                    REVIEWER_ANSWER_CONTROLS_SCHEMA_VERSION
                ),
                "reviewerAnswerControlsRect": None,
                "reviewerAnswerControlsTop": None,
                "reviewerAnswerControlsClearance": (
                    REVIEWER_ANSWER_CONTROLS_FALLBACK_CLEARANCE
                ),
                "reviewerAnswerControlsViewport": [
                    max(1, int(viewport_width)),
                    max(1, int(viewport_height)),
                ],
                "reviewerAnswerControlsSource": "fallback",
                "reviewerAnswerControlsMeasured": False,
                "reviewerAnswerControlsMatchedNodes": 0,
                "reviewerAnswerControlsTelemetryState": "fallback",
                "reviewerAnswerControlsRevision": max(0, int(generation)),
            }
        else:
            rect = tuple(telemetry.get("rect", ()) or ())
            viewport = tuple(telemetry.get("viewport", ()) or ())
            values = {
                "reviewerAnswerControlsSchemaVersion": int(
                    telemetry["schema_version"]
                ),
                "reviewerAnswerControlsRect": list(rect),
                "reviewerAnswerControlsTop": int(telemetry["top"]),
                "reviewerAnswerControlsClearance": int(
                    telemetry["clearance"]
                ),
                "reviewerAnswerControlsViewport": list(viewport),
                "reviewerAnswerControlsSource": str(telemetry["source"]),
                "reviewerAnswerControlsMeasured": True,
                "reviewerAnswerControlsMatchedNodes": int(
                    telemetry.get("matched_nodes", 0) or 0
                ),
                "reviewerAnswerControlsTelemetryState": "measured",
                "reviewerAnswerControlsRevision": max(0, int(generation)),
            }
        try:
            for key, value in values.items():
                setter(key, value)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def _accept_reviewer_answer_controls_telemetry(
        self,
        parent: Any,
        source_webview: Any,
        generation: int,
        parent_width: int,
        parent_height: int,
        source_width: int,
        source_height: int,
        payload: Any,
    ) -> None:
        """Accept only the latest measurement for the current Reviewer view."""

        if generation != self._reviewer_answer_controls_generation:
            return
        reviewer = getattr(mw, "reviewer", None)
        if (
            str(getattr(mw, "state", "") or "") != "review"
            or getattr(reviewer, "web", None) is not parent
            or reviewer_answer_controls_webview(mw) is not source_webview
        ):
            return
        try:
            live_width = max(1, int(parent.width()))
            live_height = max(1, int(parent.height()))
            live_source_width = max(1, int(source_webview.width()))
            live_source_height = max(1, int(source_webview.height()))
            zoom_factor = float(getattr(source_webview, "zoomFactor", lambda: 1.0)())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return
        if (
            live_width != int(parent_width)
            or live_height != int(parent_height)
            or live_source_width != int(source_width)
            or live_source_height != int(source_height)
        ):
            telemetry = None
        else:
            telemetry = normalize_reviewer_answer_controls_telemetry(
                payload,
                viewport_width=live_source_width,
                viewport_height=live_source_height,
                zoom_factor=zoom_factor,
            )
            if telemetry is not None and source_webview is not parent:
                try:
                    source_origin = source_webview.mapToGlobal(
                        source_webview.rect().topLeft()
                    )
                    target_origin = parent.mapFromGlobal(source_origin)
                    offset_x = int(target_origin.x())
                    offset_y = int(target_origin.y())
                    rect_x, rect_y, rect_width, rect_height = tuple(
                        telemetry["rect"]
                    )
                    raw_left = offset_x + int(rect_x)
                    raw_top = offset_y + int(rect_y)
                    raw_right = raw_left + int(rect_width)
                    raw_bottom = raw_top + int(rect_height)
                    left = max(0, min(live_width, raw_left))
                    top = max(0, min(live_height, raw_top))
                    right = max(
                        left + 1,
                        min(live_width, raw_right),
                    )
                    bottom = max(
                        top + 1,
                        min(live_height, raw_bottom),
                    )
                    telemetry = {
                        **telemetry,
                        "viewport": (live_width, live_height),
                        "rect": (
                            left,
                            top,
                            max(1, right - left),
                            max(1, bottom - top),
                        ),
                        "top": top,
                        "clearance": max(0, live_height - top),
                    }
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    telemetry = None
            elif telemetry is not None:
                telemetry = {
                    **telemetry,
                    "viewport": (live_width, live_height),
                    "top": int(telemetry["rect"][1]),
                    "clearance": max(
                        0,
                        live_height - int(telemetry["rect"][1]),
                    ),
                }
        published = self._publish_reviewer_answer_controls_telemetry(
            parent,
            telemetry,
            generation=generation,
            viewport_width=live_width,
            viewport_height=live_height,
        )
        panel = getattr(self, "_reviewer_hud", None)
        reposition = getattr(panel, "reposition", None)
        if not callable(reposition):
            return
        try:
            panel_parent = getattr(panel, "parentWidget", lambda: parent)()
            if panel_parent is not parent:
                return
            if published:
                reposition(live_width, live_height)
            elif telemetry is not None:
                reposition(
                    live_width,
                    live_height,
                    answer_controls_top=int(telemetry["top"]),
                )
            else:
                reposition(live_width, live_height)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return

    def _request_reviewer_answer_control_geometry(
        self,
        parent: Any | None = None,
    ) -> bool:
        """Measure answer controls through the current Reviewer WebEngine."""

        reviewer = getattr(mw, "reviewer", None)
        reviewer_web = getattr(reviewer, "web", None)
        target = reviewer_web if parent is None else parent
        if (
            str(getattr(mw, "state", "") or "") != "review"
            or target is None
            or target is not reviewer_web
        ):
            return False
        try:
            parent_width = max(1, int(target.width()))
            parent_height = max(1, int(target.height()))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        source_webview = reviewer_answer_controls_webview(mw)
        if source_webview is None:
            return False
        try:
            source_width = max(1, int(source_webview.width()))
            source_height = max(1, int(source_webview.height()))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

        self._reviewer_answer_controls_generation += 1
        generation = self._reviewer_answer_controls_generation
        script = reviewer_answer_controls_measurement_script()

        def accept(payload: Any) -> None:
            self._accept_reviewer_answer_controls_telemetry(
                target,
                source_webview,
                generation,
                parent_width,
                parent_height,
                source_width,
                source_height,
                payload,
            )

        evaluate = getattr(source_webview, "evalWithCallback", None)
        if callable(evaluate):
            try:
                evaluate(script, accept)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.debug(
                    "Anki Garden: Reviewer answer controls could not be measured",
                    exc_info=True,
                )

        try:
            page = source_webview.page()
            run_javascript = getattr(page, "runJavaScript", None)
        except (AttributeError, RuntimeError, TypeError):
            run_javascript = None
        if callable(run_javascript):
            try:
                run_javascript(script, accept)
                return True
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.debug(
                    "Anki Garden: Reviewer WebEngine measurement bridge failed",
                    exc_info=True,
                )

        self._accept_reviewer_answer_controls_telemetry(
            target,
            source_webview,
            generation,
            parent_width,
            parent_height,
            source_width,
            source_height,
            None,
        )
        return False

    def _render_reviewer_hud(
        self,
        parent: Any,
        projection: ReviewerHudProjection,
        *,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        """Update one mounted HUD instead of rebuilding it per answer."""

        panel = getattr(self, "_reviewer_hud", None)
        panel_created = False
        same_parent = False
        if panel is not None:
            try:
                same_parent = panel.parentWidget() is parent
            except RuntimeError:
                panel = None
        update_projection = getattr(panel, "update_projection", None)
        if panel is None or not same_parent or not callable(update_projection):
            if getattr(self, "_reviewer_hud", None) is not None:
                self._hide_reviewer_hud()
            try:
                panel = create_reviewer_hud(
                    parent,
                    on_open_garden=self._open_garden_from_reviewer_hud,
                    on_open_plant=self._open_active_plant_from_reviewer_hud,
                    on_open_activity=self._open_activity_from_reviewer_hud,
                    on_open_supplies=self._open_supplies_from_reviewer_hud,
                    on_position_changed=self._save_reviewer_hud_position,
                    on_open_collection=self._open_collection_from_reviewer_hud,
                    on_select_plant=self._select_another_plant_from_reviewer_hud,
                    on_choose_plant=self._choose_plant_from_reviewer_hud,
                    on_toggle_collapsed=self._toggle_reviewer_hud,
                    on_request_answer_controls=(
                        self._request_reviewer_answer_control_geometry
                    ),
                    resolve_reward_art=self._resolve_reviewer_reward_art,
                    animations_enabled=self._session_summary_animations_enabled(),
                )
            except Exception:
                logger.debug(
                    "Anki Garden: unable to mount Reviewer HUD",
                    exc_info=True,
                )
                self._hide_reviewer_hud()
                return
            self._reviewer_hud = panel
            self._reviewer_hud_parent = parent
            self._reviewer_hud_parent_filter = None
            update_projection = getattr(panel, "update_projection", None)
            panel_created = True
            animate = False
        else:
            set_callbacks = getattr(panel, "set_callbacks", None)
            if callable(set_callbacks):
                try:
                    set_callbacks(
                        on_open_garden=self._open_garden_from_reviewer_hud,
                        on_open_plant=self._open_active_plant_from_reviewer_hud,
                        on_open_activity=self._open_activity_from_reviewer_hud,
                        on_open_supplies=self._open_supplies_from_reviewer_hud,
                        on_position_changed=self._save_reviewer_hud_position,
                        on_open_collection=self._open_collection_from_reviewer_hud,
                        on_select_plant=self._select_another_plant_from_reviewer_hud,
                        on_choose_plant=self._choose_plant_from_reviewer_hud,
                        on_toggle_collapsed=self._toggle_reviewer_hud,
                        on_request_answer_controls=(
                            self._request_reviewer_answer_control_geometry
                        ),
                        resolve_reward_art=self._resolve_reviewer_reward_art,
                        animations_enabled=self._session_summary_animations_enabled(),
                    )
                except Exception:
                    self._hide_reviewer_hud()
                    return
            animate = bool(self._pending_reviewer_results)

        self._reviewer_hud_projection = projection
        try:
            update_projection(projection, animate=animate)
            if panel_created and self._reviewer_hud_reward_state is not None:
                restore_reward_state = getattr(panel, "restore_reward_state", None)
                if callable(restore_reward_state):
                    restore_reward_state(self._reviewer_hud_reward_state)
                    self._reviewer_hud_reward_state = None
            reposition = getattr(panel, "reposition", None)
            if callable(reposition):
                reposition(viewport_width, viewport_height)
            self._request_reviewer_answer_control_geometry(parent)
        except Exception:
            logger.debug(
                "Anki Garden: Reviewer HUD could not refresh in place",
                exc_info=True,
            )
            self._hide_reviewer_hud()
            return
        if self._pending_reviewer_results:
            # Let the mounted HUD accept the exact committed result before its
            # shared accumulator snapshot advances. This keeps the applied-row,
            # checkpoint/reveal, and changed-total feedback in causal order.
            self._flush_pending_reviewer_results()
        else:
            self._update_reviewer_hud_session_totals()

    def _render_reviewer_hud_legacy(
        self,
        parent: Any,
        projection: ReviewerHudProjection,
        *,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        try:
            from aqt.qt import (
                QEvent,
                QFrame,
                QHBoxLayout,
                QLabel,
                QObject,
                QPixmap,
                QProgressBar,
                QPushButton,
                QScrollArea,
                QSize,
                QSizePolicy,
                QTimer,
                QVBoxLayout,
                QWidget,
                Qt,
            )
            from ..ui.icons import garden_icon

            class _HudElidingLabel(QLabel):
                """Keep one-line HUD titles bounded while preserving full copy."""

                def __init__(self, text: str, owner: Any = None) -> None:
                    super().__init__("", owner)
                    self._full_text = str(text)
                    self.setAccessibleName(self._full_text)
                    self.setSizePolicy(
                        QSizePolicy.Policy.Ignored,
                        QSizePolicy.Policy.Preferred,
                    )
                    self.setMinimumWidth(0)
                    self._refresh_text()

                def resizeEvent(self, event: Any) -> None:
                    super().resizeEvent(event)
                    self._refresh_text()

                def _refresh_text(self) -> None:
                    available = max(1, int(self.contentsRect().width()))
                    visible = self.fontMetrics().elidedText(
                        self._full_text,
                        Qt.TextElideMode.ElideRight,
                        available,
                    )
                    if super().text() != visible:
                        super().setText(visible)
                    elided = visible != self._full_text
                    self.setProperty("textElided", elided)
                    self.setProperty("fullText", self._full_text)
                    self.setToolTip(self._full_text if elided else "")

            self._hide_reviewer_hud()
            x, y, width, height = reviewer_hud_geometry(
                viewport_width,
                viewport_height,
                collapsed=projection.collapsed,
                dock=projection.dock,
            )
            panel = QFrame(parent)
            panel.setObjectName("ankiGardenReviewerHud")
            panel.setProperty("semanticId", "reviewer.hud")
            panel.setProperty("reviewerOverlay", True)
            panel.setProperty("hudCollapsed", projection.collapsed)
            panel.setProperty("hudDock", projection.dock)
            panel.setProperty("reviewerControlClearance", 112)
            panel.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            panel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            panel.setFixedSize(width, height)
            panel.move(x, y)
            panel.setAccessibleName("Anki Garden review panel")
            panel.setStyleSheet(
                "QFrame#ankiGardenReviewerHud {"
                f"background:{GARDEN_THEME['elevated_surface']};"
                f"border:1px solid {GARDEN_THEME['strong_border']};"
                "border-radius:16px;}"
                "QFrame[hudCard='true'] {"
                f"background:{GARDEN_THEME['raised_surface']};"
                f"border:1px solid {GARDEN_THEME['subtle_border']};"
                "border-radius:12px;}"
                f"QLabel {{color:{GARDEN_THEME['text_primary']};font-size:12px;}}"
                f"QLabel[hudMuted='true'] {{color:{GARDEN_THEME['text_secondary']};font-size:11px;}}"
                f"QLabel[hudSection='true'] {{color:{GARDEN_THEME['text_secondary']};font-size:11px;font-weight:700;}}"
                f"QLabel[hudPrimary='true'] {{color:{GARDEN_THEME['text_primary']};font-size:20px;font-weight:700;}}"
                f"QLabel[hudPlantName='true'] {{color:{GARDEN_THEME['text_primary']};font-size:22px;font-weight:700;}}"
                f"QLabel[hudCoin='true'] {{color:{GARDEN_THEME['coin_accent']};font-size:12px;font-weight:700;}}"
                f"QLabel[hudGrowth='true'] {{color:{GARDEN_THEME['growth_accent']};font-size:13px;font-weight:700;}}"
                f"QLabel[hudFind='true'] {{color:{GARDEN_THEME['text_primary']};font-size:11px;font-weight:600;}}"
                f"QLabel[hudChip='true'] {{color:{GARDEN_THEME['text_primary']};background:{GARDEN_THEME['selected_surface']};"
                f"border:1px solid {GARDEN_THEME['subtle_border']};border-radius:7px;padding:3px 6px;font-size:10.5px;font-weight:600;}}"
                f"QProgressBar {{background:{GARDEN_THEME['garden_background']};border:0;border-radius:4px;min-height:8px;max-height:8px;text-align:center;}}"
                f"QProgressBar::chunk {{background:{GARDEN_THEME['growth_accent']};border-radius:4px;}}"
                "QPushButton {background:transparent;border:0;border-radius:7px;padding:0;}"
                "QPushButton[hudPrimaryAction='true'] {"
                f"background:{GARDEN_THEME['selected_surface']};"
                f"border:1px solid {GARDEN_THEME['strong_border']};"
                f"color:{GARDEN_THEME['text_primary']};"
                "min-height:32px;padding:4px 10px;font-size:12px;font-weight:700;}"
                f"QPushButton:hover {{background:{GARDEN_THEME['selected_surface']};}}"
            )

            def finalize_panel() -> None:
                self._reviewer_hud = panel
                self._reviewer_hud_projection = projection

                def reposition() -> None:
                    if getattr(self, "_reviewer_hud", None) is not panel:
                        return
                    try:
                        current_width = max(1, int(parent.width()))
                        current_height = max(1, int(parent.height()))
                        next_geometry = reviewer_hud_geometry(
                            current_width,
                            current_height,
                            collapsed=projection.collapsed,
                            dock=projection.dock,
                        )
                        panel.setFixedSize(next_geometry[2], next_geometry[3])
                        panel.move(next_geometry[0], next_geometry[1])
                        panel.raise_()
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        return

                class _HudParentFilter(QObject):
                    def eventFilter(self, watched: Any, event: Any) -> bool:
                        if event.type() in {
                            QEvent.Type.Resize,
                            QEvent.Type.Show,
                        }:
                            QTimer.singleShot(0, reposition)
                        return False

                resize_filter = _HudParentFilter(panel)
                parent.installEventFilter(resize_filter)
                self._reviewer_hud_parent = parent
                self._reviewer_hud_parent_filter = resize_filter
                panel.show()
                reposition()

            if projection.collapsed:
                root = QVBoxLayout(panel)
                root.setContentsMargins(4, 6, 4, 6)
                root.setSpacing(3)
                expand = QPushButton(panel)
                expand.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                expand.setCursor(Qt.CursorShape.PointingHandCursor)
                today = projection.today
                if today.status == "complete":
                    top = "✓"
                elif today.status == "waiting_for_learning":
                    top = "…"
                elif today.status == "in_progress":
                    try:
                        top = today.primary.split()[0]
                        top = "99+" if int(top.replace(",", "")) > 99 else top
                    except (ValueError, IndexError):
                        top = "•"
                else:
                    top = "—"
                plant_percent = (
                    f"{projection.nurture.progress_percent}%"
                    if projection.nurture.has_target
                    else "•"
                )
                expand.setText(f"{top}\nCARDS\n\n{plant_percent}\n›")
                expand.setAccessibleName(
                    ". ".join(
                        part
                        for part in (
                            today.primary,
                            projection.nurture.plant_name,
                            projection.nurture.checkpoint_line,
                            "Expand Anki Garden",
                        )
                        if part
                    )
                )
                expand.clicked.connect(self._toggle_reviewer_hud)
                root.addWidget(expand, 1)
                finalize_panel()
                return

            root = QVBoxLayout(panel)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            header = QFrame(panel)
            header.setFixedHeight(48)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(12, 6, 8, 6)
            header_layout.setSpacing(7)
            mark = QLabel()
            mark.setPixmap(garden_icon("growth", color=GARDEN_THEME["growth_accent"]).pixmap(20, 20))
            mark.setAccessibleName("Anki Garden")
            header_layout.addWidget(mark)
            title = QLabel("Anki Garden")
            title.setStyleSheet("font-size:15px;font-weight:700;")
            header_layout.addWidget(title, 1)
            coin = QLabel(f"{projection.coins:,}")
            coin.setProperty("hudCoin", True)
            coin.setAccessibleName(f"{projection.coins:,} Garden Coins")
            header_layout.addWidget(coin)
            collapse = QPushButton()
            collapse.setFixedSize(32, 32)
            collapse.setIcon(garden_icon(
                "chevron-right" if projection.dock == "right" else "chevron-left",
                color=GARDEN_THEME["text_primary"],
            ))
            collapse.setIconSize(QSize(18, 18))
            collapse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            collapse.setAccessibleName("Collapse Anki Garden")
            collapse.setCursor(Qt.CursorShape.PointingHandCursor)
            collapse.clicked.connect(self._toggle_reviewer_hud)
            header_layout.addWidget(collapse)
            root.addWidget(header)

            scroll = QScrollArea(panel)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(12, 10, 12, 14)
            body_layout.setSpacing(10)

            today_card = QFrame()
            today_card.setProperty("hudCard", True)
            today_layout = QVBoxLayout(today_card)
            today_layout.setContentsMargins(12, 11, 12, 11)
            today_layout.setSpacing(6)
            today_heading_row = QHBoxLayout()
            today_heading_row.setContentsMargins(0, 0, 0, 0)
            today_heading_row.setSpacing(6)
            today_heading = QLabel(projection.today.heading)
            today_heading.setProperty("hudSection", True)
            today_heading.setWordWrap(True)
            today_heading_row.addWidget(today_heading, 1)
            scope = QLabel("ALL DECKS")
            scope.setProperty("hudChip", True)
            scope.setToolTip(
                "Current deck limits and filtered decks are respected."
            )
            scope.setAccessibleName("All decks")
            today_heading_row.addWidget(scope)
            today_layout.addLayout(today_heading_row)
            today_primary = QLabel(projection.today.primary)
            today_primary.setProperty("hudPrimary", projection.today.status == "in_progress")
            today_primary.setProperty("hudCoin", projection.today.status == "complete")
            today_primary.setWordWrap(True)
            today_layout.addWidget(today_primary)
            if projection.today.progress_maximum > 0:
                due_progress = QProgressBar()
                due_progress.setProperty(
                    "semanticId",
                    "reviewer.hud.today-progress",
                )
                due_progress.setRange(0, projection.today.progress_maximum)
                due_progress.setValue(projection.today.progress_value)
                due_progress.setTextVisible(False)
                due_progress.setAccessibleName(
                    f"{projection.today.progress_value:,} of "
                    f"{projection.today.progress_maximum:,} starting cards complete"
                )
                today_layout.addWidget(due_progress)
            for line in projection.today.secondary:
                label = QLabel(line)
                label.setProperty("hudMuted", True)
                label.setWordWrap(True)
                today_layout.addWidget(label)
            if projection.today.finds_line:
                find = QLabel(projection.today.finds_line)
                find.setProperty("hudFind", True)
                find.setWordWrap(True)
                today_layout.addWidget(find)
            if projection.today.finds_detail:
                detail = QLabel(projection.today.finds_detail)
                detail.setProperty("hudMuted", True)
                today_layout.addWidget(detail)
            body_layout.addWidget(today_card)

            nurture_card = QFrame()
            nurture_card.setProperty("hudCard", True)
            nurture_layout = QVBoxLayout(nurture_card)
            nurture_layout.setContentsMargins(12, 11, 12, 12)
            nurture_layout.setSpacing(6)
            if not projection.nurture.has_target:
                empty_heading = QLabel(projection.nurture.empty_heading)
                empty_heading.setProperty("hudSection", True)
                nurture_layout.addWidget(empty_heading)
                empty_message = QLabel(projection.nurture.empty_message)
                empty_message.setWordWrap(True)
                nurture_layout.addWidget(empty_message)
                if projection.nurture.stored_growth_line:
                    stored = QLabel(projection.nurture.stored_growth_line)
                    stored.setProperty("hudGrowth", True)
                    nurture_layout.addWidget(stored)
                choose = QPushButton("Choose a plant")
                choose.setProperty("hudPrimaryAction", True)
                choose.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                choose.setCursor(Qt.CursorShape.PointingHandCursor)
                choose.setAccessibleName("Choose a plant")
                if callable(self.open_garden):
                    choose.clicked.connect(
                        lambda: QTimer.singleShot(0, self.open_garden)
                    )
                else:
                    choose.setEnabled(False)
                nurture_layout.addWidget(choose)
            else:
                metadata = QHBoxLayout()
                if projection.nurture.species_name:
                    species = _HudElidingLabel(
                        projection.nurture.species_name
                    )
                    species.setProperty("hudMuted", True)
                    metadata.addWidget(species, 1)
                else:
                    metadata.addStretch(1)
                bed = QLabel(projection.nurture.bed_label)
                bed.setProperty("hudMuted", True)
                metadata.addWidget(bed)
                nurture_layout.addLayout(metadata)
                context = QLabel("CURRENTLY NURTURING")
                context.setProperty("hudSection", True)
                nurture_layout.addWidget(context)
                plant_name = _HudElidingLabel(projection.nurture.plant_name)
                plant_name.setProperty("hudPlantName", True)
                nurture_layout.addWidget(plant_name)

                art = QLabel()
                art.setAlignment(Qt.AlignmentFlag.AlignCenter)
                art.setMinimumHeight(80)
                art.setMaximumHeight(104)
                art.setAccessibleName(
                    projection.nurture.plant_name
                )
                try:
                    plant = next(
                        item for item in getattr(self.storage.state, "plants", ())
                        if str(getattr(item, "plant_id", "")) == projection.nurture.plant_id
                    )
                    asset = self.engine.resolve_plant_asset(
                        str(getattr(plant, "species", "")),
                        str(getattr(plant, "growth_stage", "seed")),
                    )
                    pixmap = QPixmap(str(getattr(asset, "path", "") or ""))
                    if not pixmap.isNull():
                        art.setPixmap(pixmap.scaled(
                            96,
                            96,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        ))
                    else:
                        art.setPixmap(garden_icon(
                            "plant",
                            color=GARDEN_THEME["growth_accent"],
                        ).pixmap(72, 72))
                except Exception:
                    art.setPixmap(garden_icon("plant", color=GARDEN_THEME["growth_accent"]).pixmap(72, 72))
                nurture_layout.addWidget(art)

                stage_row = QHBoxLayout()
                stage = QLabel(projection.nurture.stage_label)
                stage.setProperty("hudSection", True)
                stage.hide()
                percent = QLabel(f"{projection.nurture.progress_percent}%")
                percent.setProperty("hudMuted", True)
                stage_row.addWidget(percent)
                nurture_layout.addLayout(stage_row)
                plant_progress = QProgressBar()
                plant_progress.setProperty(
                    "semanticId",
                    "reviewer.hud.plant-stage-progress",
                )
                plant_progress.setRange(0, 100)
                plant_progress.setValue(projection.nurture.progress_percent)
                plant_progress.setTextVisible(False)
                plant_progress.setAccessibleName(
                    f"{projection.nurture.stage_label} "
                    f"{projection.nurture.progress_percent} percent"
                )
                nurture_layout.addWidget(plant_progress)
                markers = QLabel("25%        50%        75%")
                markers.setProperty("hudMuted", True)
                markers.setAlignment(Qt.AlignmentFlag.AlignCenter)
                markers.setAccessibleName("Stage checkpoints at 25, 50, and 75 percent")
                nurture_layout.addWidget(markers)
                for line in (
                    projection.nurture.checkpoint_line,
                    projection.nurture.estimate_line,
                    projection.nurture.next_stage_line,
                ):
                    if line:
                        label = QLabel(line)
                        label.setProperty("hudMuted", True)
                        label.setWordWrap(True)
                        nurture_layout.addWidget(label)
                if projection.nurture.next_card_line:
                    next_card = QLabel(projection.nurture.next_card_line)
                    next_card.setProperty("hudGrowth", True)
                    nurture_layout.addWidget(next_card)
                pulse = QLabel("")
                pulse.setProperty("hudGrowth", True)
                pulse.hide()
                nurture_layout.addWidget(pulse)
                self._reviewer_growth_pulse = pulse
                if projection.nurture.shared_line:
                    shared = QLabel(projection.nurture.shared_line)
                    shared.setProperty("hudMuted", True)
                    shared.setWordWrap(True)
                    nurture_layout.addWidget(shared)
                if projection.nurture.environment_line:
                    environment = QLabel(projection.nurture.environment_line)
                    environment.setProperty("hudMuted", True)
                    environment.setWordWrap(True)
                    nurture_layout.addWidget(environment)
                for chip_text in projection.nurture.effect_chips[:4]:
                    chip = QLabel(chip_text)
                    chip.setProperty("hudChip", True)
                    chip.setWordWrap(True)
                    nurture_layout.addWidget(chip)
                if projection.nurture.queued_line:
                    queued = QLabel(projection.nurture.queued_line)
                    queued.setProperty("hudMuted", True)
                    queued.setWordWrap(True)
                    nurture_layout.addWidget(queued)
                if projection.nurture.stored_growth_line:
                    stored = QLabel(projection.nurture.stored_growth_line)
                    stored.setProperty("hudGrowth", True)
                    nurture_layout.addWidget(stored)
            body_layout.addWidget(nurture_card)
            body_layout.addStretch(1)
            scroll.setWidget(body)
            root.addWidget(scroll, 1)

            finalize_panel()
        except Exception:
            logger.debug("Anki Garden: unable to render Reviewer HUD", exc_info=True)
            self._hide_reviewer_hud()

    @staticmethod
    def _committed_growth_snapshot(state: Any) -> dict[str, int]:
        stats = getattr(state, "daily_stats", None)
        return {
            field: max(0, int(getattr(stats, field, 0) or 0))
            for field in (
                "answer_growth_units",
                "applied_growth_units",
                "redirected_growth_units",
                "shared_growth_units",
                "stored_growth_units",
            )
        }

    def _show_committed_growth_feedback(
        self,
        before: Mapping[str, int],
        projected_award: Any | None,
        *,
        legacy_total_growth: int = 0,
    ) -> None:
        """Render the engine-projected total plus committed routing deltas."""

        state = getattr(self.storage, "state", None)
        after = self._committed_growth_snapshot(state)
        delta = {
            field: max(0, int(after.get(field, 0)) - int(before.get(field, 0)))
            for field in after
        }
        total_units = max(0, int(delta.get("answer_growth_units", 0)))
        if total_units <= 0 and projected_award is not None:
            total_units = max(
                0,
                int(getattr(projected_award, "total_growth_units", 0) or 0),
            )
        if total_units <= 0:
            total_units = max(0, int(legacy_total_growth)) * 100
        pulse = getattr(self, "_reviewer_growth_pulse", None)
        projection = getattr(self, "_reviewer_hud_projection", None)
        if (
            total_units <= 0
            or pulse is None
            or bool(getattr(projection, "collapsed", False))
        ):
            return
        try:
            from aqt.qt import QTimer
            from ..ui.reviewer_hud import format_growth_units

            pulse.setText(f"{format_growth_units(total_units, signed=True)} Growth")
            pulse.setToolTip("")
            pulse.setAccessibleName(
                f"{format_growth_units(total_units, signed=True)} Growth"
            )
            pulse.show()
            QTimer.singleShot(1_800, pulse.hide)
        except (AttributeError, RuntimeError):
            return

    def _hide_reward_toast(self) -> None:
        self._hide_reward_list_panel()
        toasts = list(getattr(self, "_reward_toasts", []) or [])
        toast = self._reward_toast
        if toast is not None and toast not in toasts:
            toasts.append(toast)
        self._reward_toasts = []
        self._reward_toast_overflow = 0
        self._reward_toast_history = []
        self._reward_toast = None
        if not toasts:
            return
        for toast in toasts:
            try:
                timer = getattr(toast, "_garden_dismiss_timer", None)
                if timer is not None:
                    timer.stop()
                toast.hide()
                toast.deleteLater()
            except Exception:
                logger.debug(
                    "Anki Garden: reviewer reward feedback could not be hidden",
                    exc_info=True,
                )

    def _hide_reward_list_panel(self) -> None:
        panel = getattr(self, "_reward_list_panel", None)
        self._reward_list_panel = None
        if panel is None:
            return
        try:
            panel.hide()
            panel.deleteLater()
        except RuntimeError:
            pass

    def _close_reward_list_panel(self) -> None:
        """Close the expanded list and resume the synchronized toast clock."""

        self._hide_reward_list_panel()
        self._resume_reward_toast_stack()

    def _pause_reward_toast_stack(self) -> None:
        for toast in list(getattr(self, "_reward_toasts", []) or []):
            try:
                timer = getattr(toast, "_garden_dismiss_timer", None)
                if timer is not None:
                    timer.stop()
            except RuntimeError:
                continue

    def _resume_reward_toast_stack(self) -> None:
        for toast in list(getattr(self, "_reward_toasts", []) or []):
            try:
                timer = getattr(toast, "_garden_dismiss_timer", None)
                if timer is not None:
                    timer.start(GardenToastStack.HOVER_RESUME_MS)
            except RuntimeError:
                continue

    def _dismiss_reward_toast_stack(self) -> None:
        """Dismiss one synchronized generation without intermediate jumps."""

        toasts = list(getattr(self, "_reward_toasts", []) or [])
        self._reward_toasts = []
        self._reward_toast = None
        self._reward_toast_overflow = 0
        self._reward_toast_history = []
        self._hide_reward_list_panel()
        for toast in toasts:
            try:
                timer = getattr(toast, "_garden_dismiss_timer", None)
                if timer is not None:
                    timer.stop()
                toast.hide()
                toast.deleteLater()
            except RuntimeError:
                continue

    @staticmethod
    def _reward_history_key(event: Any) -> str:
        event_id = str(getattr(event, "event_id", "") or "")
        if event_id:
            return event_id
        event_ids = tuple(getattr(event, "event_ids", ()) or ())
        return "|".join(str(value) for value in event_ids)

    def _remember_reward_toast_event(self, event: Any) -> None:
        key = self._reward_history_key(event)
        history = list(getattr(self, "_reward_toast_history", []) or [])
        if key and any(self._reward_history_key(item) == key for item in history):
            return
        history.append(event)
        self._reward_toast_history = history[-20:]

    def _expand_reward_summary(self, parent: Any) -> None:
        """Open the canonical current-session history next to its HUD trigger."""
        self._hide_reward_list_panel()
        hud = getattr(self, "_reviewer_hud", None)
        if hud is not None:
            hud.open_reward_history()

    def _position_reward_toast_stack(self, parent: Any) -> None:
        """Stack at most two cards above Anki's answer controls."""

        viewport_width = max(1, int(parent.width()))
        viewport_height = max(1, int(parent.height()))
        reserved_height = min(128, max(88, viewport_height // 5))
        controls_top = max(0, viewport_height - reserved_height)
        toast_bottom_cap = max(16, controls_top - 16)
        hud = getattr(self, "_reviewer_hud", None)
        hud_projection = getattr(self, "_reviewer_hud_projection", None)
        inside_hud = hud is not None and not bool(
            getattr(hud_projection, "collapsed", False)
        )
        if inside_hud:
            try:
                hud_left = int(hud.x())
                hud_top = int(hud.y())
                hud_width = int(hud.width())
                hud_bottom = min(
                    int(hud.y()) + int(hud.height()) - 12,
                    toast_bottom_cap,
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                inside_hud = False
        next_bottom = (
            max(hud_top + 60, hud_bottom)
            if inside_hud
            else toast_bottom_cap
        )
        live: list[Any] = []
        for toast in reversed(list(getattr(self, "_reward_toasts", []) or [])):
            try:
                if inside_hud:
                    x = max(
                        hud_left,
                        min(
                            hud_left + hud_width - int(toast.width()),
                            hud_left + max(0, (hud_width - int(toast.width())) // 2),
                        ),
                    )
                    y = max(hud_top + 48, next_bottom - int(toast.height()))
                else:
                    x, _preferred_y = reviewer_reward_overlay_position(
                        viewport_width,
                        viewport_height,
                        toast.width(),
                        toast.height(),
                        margin=16,
                    )
                    y = max(16, next_bottom - int(toast.height()))
                toast.move(x, y)
                toast.setProperty("rewardInsideHud", inside_hud)
                toast.setProperty(
                    "reviewerViewportBounded",
                    bool(
                        x >= 0
                        and y >= 0
                        and x + toast.width() <= viewport_width
                        and y + toast.height() <= viewport_height
                    ),
                )
                next_bottom = y - GardenToastStack.GAP
                live.append(toast)
            except RuntimeError:
                continue
        self._reward_toasts = list(reversed(live))

    @staticmethod
    def _reward_toast_notification_count(toast: Any) -> int:
        """Count notifications represented by one visible toast widget."""

        overflow = max(0, int(toast.property("rewardOverflowCount") or 0))
        if bool(toast.property("rewardSummary")):
            return overflow
        return 1 + overflow

    def _discard_reward_toast_widget(self, toast: Any) -> None:
        """Unmount one projection without acknowledging its queued event."""

        self._reward_toasts = [
            item
            for item in getattr(self, "_reward_toasts", [])
            if item is not toast
        ]
        if self._reward_toast is toast:
            self._reward_toast = None
        try:
            timer = getattr(toast, "_garden_dismiss_timer", None)
            if timer is not None:
                timer.stop()
            toast.hide()
            toast.deleteLater()
        except RuntimeError:
            return

    def _set_reward_summary(self, toast: Any, count: int, empty_pixmap: Any) -> None:
        count = max(1, int(count))
        overflow_copy = f"+{count} more rewards"
        toast.setProperty("rewardSummary", True)
        toast.setProperty("compactToast", False)
        toast.setProperty("rewardOverflowCount", count)
        toast.setAccessibleName(f"Garden rewards. {overflow_copy}.")
        toast._garden_title_label.setText("Garden rewards")
        toast._garden_detail_label.setText(overflow_copy)
        toast._garden_detail_label.show()
        toast._garden_message_label.hide()
        toast._garden_overflow_label.hide()
        toast._garden_tier_label.hide()
        toast._garden_art_label.setPixmap(empty_pixmap)
        toast._garden_art_label.setText("")
        toast._garden_art_label.hide()
        toast._garden_activate_callback = (
            lambda target=toast: self._expand_reward_summary(
                getattr(target, "parentWidget", lambda: None)()
            )
        )
        toast._garden_dismiss_timer.start(GardenToastStack.AUTO_DISMISS_MS)

    def _prepare_reward_toast_queue(
        self,
        parent: Any,
        viewport_width: int,
        empty_pixmap: Any,
    ) -> ReviewerToastProjection:
        """Collapse prior projections before mounting the newest notification."""

        visible: list[Any] = []
        pending_before = 0
        for toast in list(getattr(self, "_reward_toasts", []) or []):
            try:
                pending_before += self._reward_toast_notification_count(toast)
                visible.append(toast)
            except RuntimeError:
                continue
        self._reward_toasts = visible
        projection = GardenToastStack.project(pending_before + 1, viewport_width)
        self._reward_toast_overflow = projection.overflow_count

        if projection.compact:
            for toast in list(visible):
                self._discard_reward_toast_widget(toast)
            return projection

        if projection.summary_visible:
            summary = next(
                (
                    toast
                    for toast in visible
                    if bool(toast.property("rewardSummary"))
                ),
                visible[0] if visible else None,
            )
            for toast in list(visible):
                if toast is not summary:
                    self._discard_reward_toast_widget(toast)
            if summary is not None:
                self._set_reward_summary(
                    summary,
                    projection.overflow_count,
                    empty_pixmap,
                )
                self._reward_toasts = [summary]
                summary.raise_()
            return projection

        # A single compact toast may survive a viewport expansion. Restore it
        # to the ordinary presentation before adding the second notification.
        for toast in visible:
            try:
                toast.setProperty("compactToast", False)
                toast.setProperty("rewardOverflowCount", 0)
                toast._garden_overflow_label.hide()
            except RuntimeError:
                continue
        self._position_reward_toast_stack(parent)
        return projection

    def _dismiss_reward_toast(self, toast: Any) -> None:
        try:
            self._hide_reward_list_panel()
            if (
                bool(toast.property("rewardSummary"))
                or bool(toast.property("compactToast"))
            ):
                self._reward_toast_overflow = 0
                self._reward_toast_history = []
            else:
                event_key = str(toast.property("rewardEventKey") or "")
                self._reward_toast_history = [
                    event
                    for event in getattr(self, "_reward_toast_history", [])
                    if self._reward_history_key(event) != event_key
                ]
            self._reward_toasts = [
                item
                for item in getattr(self, "_reward_toasts", [])
                if item is not toast
            ]
            if self._reward_toast is toast:
                self._reward_toast = (
                    self._reward_toasts[-1]
                    if self._reward_toasts else
                    None
                )
            timer = getattr(toast, "_garden_dismiss_timer", None)
            if timer is not None:
                timer.stop()
            parent = toast.parentWidget()
            toast.hide()
            toast.deleteLater()
            if parent is not None:
                self._position_reward_toast_stack(parent)
        except RuntimeError:
            return

    def _show_no_starter_notice(self) -> None:
        try:
            from aqt.qt import QFrame, QLabel, QTimer, Qt

            parent = reviewer_overlay_parent(mw)
            previous = self._reviewer_notice
            if previous is not None:
                previous.hide()
                previous.deleteLater()
            notice = QFrame(parent)
            notice.setObjectName("ankiGardenReviewerStarterNotice")
            notice.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            notice.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            notice.setStyleSheet(
                f"QFrame#ankiGardenReviewerStarterNotice {{ background:{GARDEN_THEME['elevated_surface']}; "
                f"border:1px solid {GARDEN_THEME['subtle_border']}; border-radius:8px; padding:7px 10px; }}"
                f"QLabel {{ color:{GARDEN_THEME['text_primary']}; font-size:12px; }}"
            )
            label = QLabel(REVIEWER_NO_STARTER_NOTICE, notice)
            label.setWordWrap(True)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.setAccessibleName(REVIEWER_NO_STARTER_NOTICE)
            notice.adjustSize()
            parent_width = max(1, int(parent.width()))
            parent_height = max(1, int(parent.height()))
            notice_width = min(
                max(1, int(notice.width())),
                max(1, parent_width - 24),
            )
            notice.setFixedWidth(notice_width)
            x, y = reviewer_reward_overlay_position(
                parent_width,
                parent_height,
                notice.width(),
                notice.height(),
                margin=12,
            )
            notice.move(x, y)
            notice.show()
            notice.raise_()
            self._reviewer_notice = notice
            QTimer.singleShot(6000, self._hide_no_starter_notice)
        except Exception:
            logger.debug("Anki Garden: reviewer starter notice could not be shown", exc_info=True)

    def _hide_no_starter_notice(self) -> None:
        notice = self._reviewer_notice
        self._reviewer_notice = None
        if notice is None:
            return
        try:
            notice.hide()
            notice.deleteLater()
        except Exception:
            logger.debug("Anki Garden: reviewer starter notice could not be hidden", exc_info=True)

    @staticmethod
    def review_payload_from_row(
        row: tuple[Any, ...],
        collection: Any,
        *,
        answer_identity: str = "",
        scheduler_day: str = "",
        deck_ids: Mapping[int, int] | None = None,
    ) -> dict[str, Any] | None:
        """Convert one authoritative revlog row into Garden answer semantics."""
        rid, cid, ease, ivl, last_ivl, factor, _answer_ms, review_type = row
        semantics = queue_and_lapse_from_revlog_type(review_type, ease)
        if semantics is None:
            return None
        queue, lapse_count = semantics
        deck_id = None
        card_id = int(cid)
        if deck_ids is not None:
            try:
                if card_id in deck_ids:
                    deck_id = int(deck_ids[card_id])
            except (TypeError, ValueError):
                deck_id = None
        try:
            if deck_id is None:
                deck_id = int(collection.get_card(card_id).did)
        except Exception:
            pass
        difficulty = difficulty_from_factor(factor)
        if int(ease) == 1:
            difficulty = min(1.0, difficulty + 0.15)
        return {
            "ease": int(ease),
            "deck_id": deck_id,
            "difficulty": difficulty,
            "lapse_count": lapse_count,
            "queue": queue,
            "interval_delta": max(0, int(ivl) - max(0, int(last_ivl))),
            "revlog_id": int(rid),
            "card_id": card_id,
            "answered_at_ms": int(rid),
            "answer_identity": str(answer_identity or f"revlog:{int(rid)}"),
            "scheduler_day": str(scheduler_day),
        }

    @staticmethod
    def scheduler_day(storage: Any) -> str:
        """Use Anki's day authority, with a test-adapter compatibility fallback."""

        resolver = getattr(storage, "current_scheduler_day", None)
        if callable(resolver):
            return str(resolver())
        saved_day = getattr(
            getattr(getattr(storage, "state", None), "daily_stats", None),
            "day",
            "",
        )
        return str(saved_day or date.today().isoformat())

    @staticmethod
    def stable_answer_identities(
        rows: list[tuple[Any, ...]],
        *,
        scheduler_day: str,
        existing_bindings: dict[str, str] | None = None,
        reanswer_hints: dict[str, int] | None = None,
        present_lineages: Iterable[str] = (),
    ) -> dict[int, str]:
        """Prepare lineages without mutating live state before its transaction."""

        eligible = [
            (int(row[0]), int(row[1]), str(scheduler_day))
            for row in rows
            if len(row) >= 8
            and queue_and_lapse_from_revlog_type(row[7], row[2]) is not None
        ]
        identities, _updated = assign_stable_answer_identities(
            eligible,
            existing_bindings,
            reanswer_hints,
            present_lineages=present_lineages,
        )
        return identities

    @staticmethod
    def unseen_revlog_rows(rows: list[tuple[Any, ...]], state: Any) -> list[tuple[Any, ...]]:
        return unprocessed_revlog_entries(state, rows)

    def mark_history_reconciled(self) -> None:
        """Allow narrow local reads after one complete successful history pass."""

        self._local_answer_fast_path_ready = True

    def invalidate_history(self, _reason: str = "") -> None:
        """Revoke local-answer proof without recursively notifying the app."""

        self._local_answer_fast_path_ready = False
        if _reason == "review undo":
            settle = getattr(getattr(self, "_reviewer_hud", None), "settle_growth_counts", None)
            if callable(settle):
                settle()

    def _report_history_invalidation(self, reason: str) -> None:
        self.invalidate_history(reason)
        callback = self.history_invalidated
        if callback is None:
            return
        try:
            callback(reason)
        except Exception:
            logger.debug(
                "Anki Garden: history invalidation callback failed",
                exc_info=True,
            )

    @staticmethod
    def _card_id(card: Any) -> int:
        for attribute in ("id", "card_id"):
            raw_value = getattr(card, attribute, None)
            try:
                value = raw_value() if callable(raw_value) else raw_value
                normalized = int(value or 0)
            except (TypeError, ValueError):
                continue
            if normalized > 0:
                return normalized
        return 0

    def _deck_ids_for_rows(
        self,
        rows: list[tuple[Any, ...]],
    ) -> Mapping[int, int] | None:
        resolver = getattr(self.storage, "deck_ids_for_cards", None)
        if not callable(resolver):
            return None
        try:
            return resolver({int(row[1]) for row in rows})
        except Exception:
            # Deck identity is optional review metadata. Preserve the existing
            # per-card fallback instead of deferring otherwise valid Growth.
            logger.debug(
                "Anki Garden: batched review deck lookup unavailable",
                exc_info=True,
            )
            return None

    @timed("review.local-proof")
    def _proven_local_answer(
        self,
        card: Any,
        ease: int,
        last_processed: int,
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]] | None:
        if not bool(getattr(self, "_local_answer_fast_path_ready", False)):
            return None
        loader = getattr(self.storage, "load_proven_local_answer", None)
        card_id = self._card_id(card)
        if not callable(loader) or card_id <= 0:
            return None
        pending_resolver = getattr(self.storage, "pending_reanswer_lineages", None)
        try:
            pending = (
                pending_resolver()
                if callable(pending_resolver)
                else getattr(self.storage.state, "pending_reanswer_lineages", {})
            )
            # An outstanding Undo belongs to its card, including reanswers on
            # another scheduler day. It must not force every unrelated answer
            # through a fresh history scan after history has been verified.
            for lineage in pending:
                parsed = _parse_answer_lineage_key(lineage)
                if parsed is None or parsed[1] == card_id:
                    return None
            proof = loader(
                after_id=last_processed,
                card_id=card_id,
                ease=int(ease),
            )
        except Exception:
            logger.debug(
                "Anki Garden: local-answer proof failed; using full-day history",
                exc_info=True,
            )
            return None
        if proof is None:
            return None
        row = getattr(proof, "row", None)
        card_day_rows = getattr(proof, "card_day_rows", None)
        if row is None or card_day_rows is None:
            return None
        normalized_row = tuple(row)
        normalized_context = [tuple(item) for item in card_day_rows]
        if (
            len(normalized_row) < 8
            or queue_and_lapse_from_revlog_type(
                normalized_row[7], normalized_row[2]
            ) is None
        ):
            return None
        return [normalized_row], normalized_context

    def _current_review_revlog_id(
        self,
        rows: list[tuple[Any, ...]],
        card: Any,
        ease: int,
        *,
        proven_local_commit: bool,
    ) -> int:
        """Bind this hook invocation to one unambiguous current-window row."""

        card_id = self._card_id(card)
        floor = max(
            0,
            int(self._review_window_started_after_revlog_id),
        )
        candidates = [
            tuple(row)
            for row in rows
            if len(row) >= 8
            # A proven append belongs to this hook even when an imported
            # future timestamp inflated the scalar cursor at session start.
            and (proven_local_commit or int(row[0]) > floor)
            and int(row[1]) == card_id
            and int(row[2]) == int(ease)
            and queue_and_lapse_from_revlog_type(row[7], row[2]) is not None
        ]
        if len(candidates) != 1:
            return 0
        candidate_id = int(candidates[0][0])
        if proven_local_commit:
            return candidate_id
        # A recovery read may contain older local rows or newly synced rows.
        # Only its unique newest eligible row can be attributed to this live
        # answer hook; ambiguity fails closed for Session Summary admission.
        newest_id = max((int(row[0]) for row in rows), default=0)
        return candidate_id if candidate_id == newest_id else 0

    def _remember_deferred_answer(self, card: Any, ease: int, reason: str) -> None:
        """Keep a failed local answer attached to its session for recovery."""
        runtime = getattr(self.storage, "runtime_coordinator", None)
        if runtime is None:
            return
        try:
            revlog_id = runtime.defer_answer(card, ease, self._review_window_token)
            RUNTIME_PERFORMANCE.answer_stage("deferred", str(revlog_id), reason=reason)
            if revlog_id:
                self._review_window_answer_revlog_ids.add(revlog_id)
        except Exception:
            logger.exception("Anki Garden: local review attribution could not be saved")

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        started = RUNTIME_PERFORMANCE.begin()
        RUNTIME_PERFORMANCE.answer_stage("hook")
        try:
            self._process_answer(reviewer, card, ease)
        finally:
            RUNTIME_PERFORMANCE.finish("review.answer", started)
            RUNTIME_PERFORMANCE.answer_stage("hook_finished")

    def _process_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        invalidator = getattr(self.storage, "invalidate_due_snapshot", None)
        if callable(invalidator):
            invalidator()
        runtime = getattr(self.storage, "runtime_coordinator", None)
        if runtime is not None:
            runtime.request("review answer")
            runtime.note_local_answer(reviewer)
            if getattr(self.storage, "runtime_pending", False):
                RUNTIME_PERFORMANCE.answer_stage("deferred", reason="reconciliation")
                if not self._review_window_token:
                    self._start_reviewer_session_totals(today_cards_available=False)
                self._remember_deferred_answer(card, ease, "reconciliation")
                return
        if self._session_summary_accumulator is None:
            # The first-question hook is the authoritative pre-answer
            # baseline. If it was unavailable, retain session rewards but do
            # not invent Today progress from a post-answer scheduler state.
            self._start_reviewer_session_totals(today_cards_available=False)
        elif not self._review_window_token:
            self._review_window_token = uuid.uuid4().hex
            self._review_window_started_after_revlog_id = max(
                0,
                int(
                    getattr(
                        getattr(self.storage, "state", None),
                        "last_processed_revlog_id",
                        0,
                    )
                    or 0
                ),
            )
        else:
            current_day = self.scheduler_day(self.storage)
            if (
                current_day
                != self._session_summary_accumulator.current_anki_day_id
            ):
                old_end_snapshot = self._session_end_snapshot(
                    refresh_today=False,
                )
                try:
                    observe = getattr(self.engine, "observe_due_start", None)
                    due = getattr(self.storage, "due_obligations", None)
                    if callable(observe):
                        observe(due() if callable(due) else None)
                except Exception:
                    logger.debug(
                        "Anki Garden: cutoff baseline could not refresh before card commit",
                        exc_info=True,
                    )
                self._split_session_summary_day_if_needed(
                    current_day=current_day,
                    old_end_snapshot=old_end_snapshot,
                )
        last_processed = int(
            getattr(getattr(self.storage, "state", None), "last_processed_revlog_id", 0) or 0
        )
        try:
            prepare_ledger = getattr(self.storage, "ensure_revlog_ledger_ready", None)
            if callable(prepare_ledger):
                prepare_ledger()
        except Exception:
            logger.exception(
                "Anki Garden: review-history ledger unavailable; deferring this answer to catch-up"
            )
            self._report_history_invalidation("review ledger unavailable")
            self._remember_deferred_answer(card, ease, "review ledger unavailable")
            self._show_deferred_history_notice()
            return
        local_history = self._proven_local_answer(card, ease, last_processed)
        RUNTIME_PERFORMANCE.answer_stage("history_ready")
        proven_local_commit = local_history is not None
        if local_history is None:
            if runtime is not None:
                self._report_history_invalidation("local answer was ambiguous")
                self._remember_deferred_answer(card, ease, "ambiguous_local_answer")
                return
            if bool(getattr(self, "_local_answer_fast_path_ready", False)):
                self._report_history_invalidation("local answer was ambiguous")
            try:
                newest_revlog_id = self.storage.max_revlog_id()
            except Exception:
                logger.exception(
                    "Anki Garden: review-history id unavailable; deferring this answer to catch-up"
                )
                self._report_history_invalidation("review high-water unavailable")
                self._show_deferred_history_notice()
                return
            if newest_revlog_id <= last_processed:
                logger.warning(
                    "Anki Garden: scalar revlog cursor did not advance; checking the day ledger (%s <= %s)",
                    newest_revlog_id,
                    last_processed,
                )
            try:
                day_rows = self.storage.load_new_revlog_entries(last_processed)
            except Exception:
                logger.exception(
                    "Anki Garden: unseen review history unavailable; deferring this answer to catch-up"
                )
                self._report_history_invalidation("full-day review history unavailable")
                self._show_deferred_history_notice()
                return
            rows = self.unseen_revlog_rows(day_rows, self.storage.state)
        else:
            rows, day_rows = local_history
        if not rows:
            # The reviewer hook can run before the just-written revlog row is
            # visible to a read. Leaving the cursor untouched lets maintenance
            # reconcile it once the collection transaction is complete.
            logger.warning(
                "Anki Garden: newest revlog row was not readable yet; deferring to catch-up"
            )
            self._report_history_invalidation("newest review row unavailable")
            self._show_deferred_history_notice()
            return

        collection = getattr(getattr(self.storage, "mw", None), "col", None)
        if collection is None:
            collection = getattr(mw, "col", None)
        latest_read_id = max(int(row[0]) for row in rows)
        scheduler_day = self.scheduler_day(self.storage)
        current_review_revlog_id = self._current_review_revlog_id(
            rows,
            card,
            ease,
            proven_local_commit=proven_local_commit,
        )
        if current_review_revlog_id > 0:
            self._review_window_answer_revlog_ids.add(current_review_revlog_id)
        try:
            binding_resolver = getattr(
                self.storage, "answer_lineage_bindings_for_cards", None
            )
            existing_bindings = (
                binding_resolver({int(row[1]) for row in day_rows})
                if callable(binding_resolver)
                else getattr(self.storage.state, "answer_lineage_bindings", {})
            )
            presence_resolver = getattr(self.storage, "present_answer_lineages", None)
            present_lineages = (
                presence_resolver(existing_bindings)
                if callable(presence_resolver) else ()
            )
            identities = self.stable_answer_identities(
                day_rows,
                scheduler_day=scheduler_day,
                existing_bindings=existing_bindings,
                reanswer_hints=getattr(
                    self.storage.state, "pending_reanswer_lineages", {}
                ),
                present_lineages=present_lineages,
            )
        except Exception:
            logger.exception("Anki Garden: answer identity verification failed")
            self._report_history_invalidation("answer identities unavailable")
            self._remember_deferred_answer(card, ease, "answer identities unavailable")
            self._show_deferred_history_notice()
            return
        deck_ids = self._deck_ids_for_rows(rows)
        payloads = [
            payload
            for payload in (
                self.review_payload_from_row(
                    row,
                    collection,
                    answer_identity=identities.get(int(row[0]), ""),
                    scheduler_day=scheduler_day,
                    deck_ids=deck_ids,
                )
                for row in rows
            )
            if payload is not None
        ]
        result_origin = (
            "local"
            if proven_local_commit and len(payloads) == 1
            else "local_recovery"
        )
        for payload in payloads:
            payload["origin"] = result_origin
            if int(payload.get("revlog_id", 0) or 0) == current_review_revlog_id:
                payload["review_window_token"] = self._review_window_token
        session_baseline = (
            self._session_event_baseline()
            if proven_local_commit and len(payloads) == 1
            else None
        )
        committed_before = self._committed_growth_snapshot(self.storage.state)
        projected_award: Any | None = None
        if len(payloads) == 1:
            projector = getattr(self.engine, "project_review_growth", None)
            if callable(projector):
                try:
                    projected_award = projector(
                        now=max(0, int(payloads[0].get("answered_at_ms", 0) or 0)) / 1000,
                        answer_number=max(
                            1,
                            int(getattr(self.storage.state.daily_stats, "reviewed", 0) or 0)
                            + 1,
                        ),
                    )
                except Exception:
                    logger.debug(
                        "Anki Garden: committed Growth preview was unavailable",
                        exc_info=True,
                    )
        committed_growth = 0
        committed_awards: tuple[Any, ...] = ()
        committed_results: tuple[CommittedAnswerResult, ...] = ()
        due_status: Any | None = None
        due_status_resolved = False
        RUNTIME_PERFORMANCE.answer_stage("due_started")
        try:
            due_resolver = getattr(self.storage, "due_obligations", None)
            if callable(due_resolver):
                committed_card_ids = tuple(sorted({
                    int(payload.get("card_id", 0) or 0)
                    for payload in payloads
                    if int(payload.get("card_id", 0) or 0) > 0
                }))
                try:
                    due_status = due_resolver(
                        committed_card_ids=committed_card_ids,
                    )
                except TypeError:
                    # Compatibility for test and third-party storage adapters.
                    # The engine still fails closed when an aggregate shrink
                    # exceeds the number of committed answers.
                    due_status = due_resolver()
                due_status_resolved = True
        except Exception:
            logger.debug(
                "Anki Garden: due status unavailable during answer commit",
                exc_info=True,
            )
        RUNTIME_PERFORMANCE.answer_stage("due_finished")
        try:
            # Commit every unseen row as one state transaction. In particular,
            # never jump the cursor to only the newest answer after an earlier
            # Garden save failed.
            result_commit = getattr(
                self.engine,
                "apply_same_day_reviews_with_results",
                None,
            )
            if callable(result_commit):
                committed_results = tuple(result_commit(
                    payloads,
                    latest_revlog_id=latest_read_id,
                    due_status=due_status if due_status_resolved else None,
                ))
                committed_awards = tuple(
                    result.award for result in committed_results
                )
                for result in committed_results:
                    RUNTIME_PERFORMANCE.answer_stage("committed", str(result.event_id))
                committed_growth = sum(
                    max(0, int(result.award.total_growth))
                    for result in committed_results
                )
            else:
                detailed_commit = getattr(
                    self.engine,
                    "apply_same_day_reviews_with_awards",
                    None,
                )
                if callable(detailed_commit):
                    committed_awards = tuple(detailed_commit(
                        payloads,
                        latest_revlog_id=latest_read_id,
                    ))
                    committed_growth = sum(
                        max(0, int(getattr(item, "total_growth", 0) or 0))
                        for item in committed_awards
                    )
                else:
                    committed_growth = self.engine.apply_same_day_reviews(
                        payloads,
                        latest_revlog_id=latest_read_id,
                    )
        except Exception:
            logger.exception("Anki Garden: review progress could not be saved")
            self._report_history_invalidation("review save failed")
            self._remember_deferred_answer(card, ease, "review save failed")
            message = (
                "Your card is safe in Anki, but Garden couldn’t save its Growth. "
                "Open garden to try again."
            )
            if USER_NOTICES.publish(message, key="review_history"):
                try:
                    from aqt.utils import tooltip
                    tooltip(message, period=7000, parent=mw)
                except Exception:
                    logger.debug("Anki Garden: unable to show review-save notice", exc_info=True)
            return

        if runtime is not None:
            for row in rows:
                runtime.answer_committed(tuple(row), scheduler_day)
        self.mark_history_reconciled()
        USER_NOTICES.clear(key="review_history")

        if bool(getattr(getattr(self.storage, "state", None), "starter_selection_complete", False)):
            self._hide_no_starter_notice()

        if not committed_results or not due_status_resolved:
            try:
                self.engine.evaluate_all_due(
                    due_status
                    if due_status_resolved
                    else self.storage.due_obligations(),
                    record_completed_delta=True,
                )
            except Exception:
                logger.debug(
                    "Anki Garden: unable to evaluate all-due completion after review",
                    exc_info=True,
                )

        accepted_results: list[
            tuple[CommittedAnswerResult | None, CommittedSessionEvent]
        ] = []
        accumulator = self._session_summary_accumulator
        if committed_results and accumulator is not None:
            for result in committed_results:
                if result.origin not in {"local", "local_recovery"}:
                    continue
                result_revlog_id = max(
                    0,
                    int(getattr(result, "occurred_at_ms", 0) or 0),
                )
                if result_revlog_id not in self._review_window_answer_revlog_ids:
                    continue
                try:
                    session_event = self._session_event_from_result(result)
                    if (
                        session_event is not None
                        and accumulator.accept_committed(session_event)
                    ):
                        accepted_results.append((result, session_event))
                    self._review_window_answer_revlog_ids.discard(result_revlog_id)
                except Exception:
                    logger.debug(
                        "Anki Garden: committed card could not enter Session Summary",
                        exc_info=True,
                    )
        elif (
            session_baseline is not None
            and len(committed_awards) == 1
            and len(payloads) == 1
            and accumulator is not None
        ):
            # Compatibility for alternate engines that have not adopted the
            # typed committed-result API yet.
            try:
                session_event = self._committed_session_event(
                    payload=payloads[0],
                    award=committed_awards[0],
                    baseline=session_baseline,
                )
                if (
                    session_event is not None
                    and accumulator.accept_committed(session_event)
                ):
                    accepted_results.append((None, session_event))
            except Exception:
                logger.debug(
                    "Anki Garden: committed card could not enter Session Summary",
                    exc_info=True,
                )
        self._pending_reviewer_results.extend(accepted_results)
        panel = getattr(self, "_reviewer_hud", None)
        if (runtime is not None and panel is not None
                and str(getattr(mw, "state", "")) == "review"):
            self._flush_pending_reviewer_results()
        defer = getattr(panel, "defer_until_feedback_paint", None)
        if callable(defer):
            defer(self._publish_committed_review_change)
        else:
            self._publish_committed_review_change()
        if runtime is not None:
            self._queue_committed_hud_refresh()
        else:
            self._ensure_reviewer_hud()
            if self._pending_reviewer_results:
                self._flush_pending_reviewer_results()
        if not committed_results:
            self._show_committed_growth_feedback(
                committed_before,
                committed_awards[0] if len(committed_awards) == 1 else projected_award,
                legacy_total_growth=max(0, int(committed_growth or 0)),
            )

    def _publish_committed_review_change(self) -> None:
        if self.state_changed is not None:
            try:
                self.state_changed("Card complete")
            except Exception:
                logger.debug("Anki Garden: unable to publish review state change", exc_info=True)

    def _queue_committed_hud_refresh(self) -> None:
        """Let readable feedback paint before refreshing the full projection.

        A question hook may draw first; in that case it consumes this request.
        Results remain queued until the mounted HUD accepts them, and the
        Session Summary already owns the committed events when leaving review.
        """
        if getattr(self, "_reviewer_hud_refresh_queued", False):
            return
        self._reviewer_hud_refresh_queued = True

        def refresh() -> None:
            if not getattr(self, "_reviewer_hud_refresh_queued", False):
                return
            self._reviewer_hud_refresh_queued = False
            self._ensure_reviewer_hud()
            if self._pending_reviewer_results:
                self._flush_pending_reviewer_results()

        defer = getattr(getattr(self, "_reviewer_hud", None), "defer_until_feedback_paint", None)
        if callable(defer):
            defer(refresh)
            return
        try:
            from aqt.qt import QTimer
            QTimer.singleShot(0, refresh)
        except ImportError:
            refresh()

    @staticmethod
    def _show_deferred_history_notice() -> None:
        message = (
            "Your card is safe in Anki. Garden will add it when review history is available."
        )
        if USER_NOTICES.publish(message, key="review_history"):
            try:
                from aqt.utils import tooltip

                tooltip(message, period=7000, parent=mw)
            except Exception:
                logger.debug("Anki Garden: unable to show deferred-review notice", exc_info=True)

    def _show_optional_progress_feedback(self) -> None:
        config = getattr(self.engine, "config", None)
        if config is None or not bool(config.value(
            "show_progress_notifications",
            DEFAULT_CONFIG["show_progress_notifications"],
        )):
            return
        events = list(self.engine.peek_feedback())
        if not events:
            return
        unnotified = [
            event
            for event in events
            if str(getattr(event, "event_id", "") or "")
            not in self._notified_event_ids
        ]
        if not unnotified:
            self._acknowledge_presented_feedback(events)
            return
        groups: list[list[Any]] = []
        group_indexes: dict[str, int] = {}
        for raw_event in unnotified:
            key = (
                self._feedback_correlation_id(raw_event)
                or str(getattr(raw_event, "event_id", "") or "")
            )
            if key not in group_indexes:
                group_indexes[key] = len(groups)
                groups.append([])
            groups[group_indexes[key]].append(raw_event)
        for group in groups:
            event = self._consolidated_reward_feedback(group)
            if event is None:
                continue
            if not self._show_reward_toast(event):
                break
            self._last_notified_event = event.event_id
            self._notified_event_ids.update(event.event_ids)
        self._acknowledge_presented_feedback(events)

    def _acknowledge_presented_feedback(self, events: list[Any]) -> None:
        """Retry persistence without rendering already-presented reward IDs."""

        event_ids = tuple(dict.fromkeys(
            event_id
            for event in events
            for event_id in (
                str(getattr(event, "event_id", "") or ""),
            )
            if event_id in self._notified_event_ids
        ))
        if not event_ids:
            return
        consume = getattr(self.engine, "consume_feedback", None)
        if not callable(consume):
            return
        try:
            consume(event_ids=event_ids)
        except Exception:
            # Keep each rendered ID locally. A later call retries persistence
            # without adding those rewards to another visible summary.
            logger.debug("Anki Garden: unable to acknowledge rendered feedback", exc_info=True)
            return
        self._notified_event_ids.difference_update(event_ids)

    def _consolidated_reward_feedback(
        self,
        events: list[Any] | tuple[Any, ...],
    ) -> ReviewerRewardFeedback | None:
        """Project pending atomic events as one reviewer notification.

        Reward granting and grouping remain engine-owned. This final adapter
        only combines pending presentation events, as can happen after a sync
        or when several reward correlations become visible together.
        """

        unique: list[Any] = []
        seen_ids: set[str] = set()
        for event in events:
            if not reward_content_visible(event):
                continue
            event_id = str(getattr(event, "event_id", "") or "")
            if not event_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            unique.append(event)
        if not unique:
            return None
        unique.sort(key=self._reward_stack_priority)

        presentations = self._garden_find_presentations(unique)
        find_events = [
            event
            for event in unique
            if str(getattr(event, "kind", "")) == "garden_find"
        ]
        preferred = (
            find_events[-1]
            if find_events
            else max(unique, key=lambda item: str(getattr(item, "occurred_at", "")))
        )
        event_ids = tuple(str(getattr(event, "event_id")) for event in unique)
        combined_id = "reviewer-summary:" + "|".join(event_ids)
        coins_total, growth_total, environment_total = self._typed_reward_totals(unique)
        reward_parts = []
        if coins_total:
            reward_parts.append(
                f"+{coins_total:,} "
                f"{'Garden Coin' if coins_total == 1 else 'Garden Coins'}"
            )
        if growth_total:
            reward_parts.append(f"+{growth_total:,} Growth")
        nonreward_messages = tuple(dict.fromkeys(
            self._player_reward_copy(getattr(event, "message", ""))
            for event in unique
            if not self._is_reward_feedback_event(event)
            and self._player_reward_copy(getattr(event, "message", ""))
        ))
        if nonreward_messages and not reward_parts:
            reward_parts.append(nonreward_messages[0])
        message = " · ".join(reward_parts)
        title = self._player_reward_copy(getattr(preferred, "title", ""))
        tier = ""
        reward_detail = ""
        asset_category = str(getattr(preferred, "asset_category", "") or "")
        asset_key = str(getattr(preferred, "asset_key", "") or "")

        if presentations:
            find = presentations[0]
            if str(find.pool_id) == "environment":
                discovery_name = str(find.display_name or "").strip()
                title = (
                    f"{discovery_name} discovered"
                    if discovery_name else
                    "Garden discovery"
                )
            else:
                title = "Garden Find"
            tier = self._display_tier(find.tier)
            if str(find.pool_id) == "environment" and environment_total:
                message = "Added to Garden decorations"
            elif not message:
                message = self._player_reward_copy(find.description)
            first_find = presentations[0]
            asset_key = str(first_find.artwork_ref or asset_key)
            asset_category = (
                "environment"
                if str(first_find.pool_id) == "environment"
                else "ui"
            )
        elif find_events:
            title = (
                title.removeprefix("Garden Find:")
                .removeprefix("Standard Find:")
                .strip()
                or "Garden reward"
            )

        find_count = max(len(find_events), len(presentations))
        if find_count > 1:
            discovery_count = sum(
                1
                for presentation in presentations
                if str(presentation.pool_id) == "environment"
            )
            standard_count = max(0, len(presentations) - discovery_count)
            if discovery_count and standard_count:
                standard_label = (
                    "Garden Find" if standard_count == 1 else "Garden Finds"
                )
                discovery_label = (
                    "Garden discovery"
                    if discovery_count == 1 else
                    "Garden discoveries"
                )
                title = f"{standard_label} and {discovery_label}"
                mixed_parts = list(reward_parts)
                if not mixed_parts:
                    mixed_parts.append(f"{standard_label} added")
                mixed_parts.append(f"{discovery_label} added")
                message = " · ".join(mixed_parts)
            elif discovery_count:
                title = "Garden discoveries"
                message = "Added to Garden decorations"
            else:
                title = "Garden Finds"
                message = " · ".join(reward_parts) or "Garden Finds added"
        if not message:
            message = self._aggregate_reward_messages(unique)

        if not title:
            title = "Garden rewards" if len(unique) > 1 else "Review reward"
        elif "sync" in title.casefold():
            title = "Garden rewards"
        return ReviewerRewardFeedback(
            event_id=combined_id,
            event_ids=event_ids,
            kind="garden_find" if find_events else "reward_summary",
            message=self._player_reward_copy(message),
            occurred_at=max(
                str(getattr(event, "occurred_at", "")) for event in unique
            ),
            plant_id=str(getattr(preferred, "plant_id", "") or "") or None,
            title=self._player_reward_copy(title),
            asset_category=asset_category,
            asset_key=asset_key,
            correlation_id=self._feedback_correlation_id(preferred),
            tier=tier,
            reward_detail=self._player_reward_copy(reward_detail),
            coins_total=coins_total,
            growth_total=growth_total,
            environment_total=environment_total,
            find_count=find_count,
        )

    def _typed_reward_totals(
        self,
        events: list[Any],
    ) -> tuple[int, int, int]:
        """Sum authoritative typed reward summaries once per correlation."""

        try:
            from ..reward_presentation import recent_reward_summaries

            summaries = recent_reward_summaries(self.storage.state)
        except (AttributeError, ImportError, TypeError, ValueError):
            return 0, 0, 0
        by_correlation = {
            str(summary.correlation_id): summary for summary in summaries
        }
        correlations = tuple(dict.fromkeys(
            correlation
            for event in events
            if self._is_reward_feedback_event(event)
            and (correlation := self._feedback_correlation_id(event))
        ))
        selected = [
            by_correlation[correlation]
            for correlation in correlations
            if correlation in by_correlation
        ]
        coins = sum(max(0, int(summary.coins_total)) for summary in selected)
        growth = sum(max(0, int(summary.growth_total)) for summary in selected)
        environments = sum(
            max(0, int(line.amount))
            for summary in selected
            for line in summary.lines
            if str(line.reward_type) == "environment_item"
        )
        return coins, growth, environments

    @staticmethod
    def _is_reward_feedback_event(event: Any) -> bool:
        return str(getattr(event, "kind", "") or "") in {
            "garden_find",
            "reward_summary",
        }

    @staticmethod
    def _player_reward_copy(value: Any) -> str:
        """Normalize legacy engine prose at the final learner-facing boundary."""

        text = str(value or "").strip()
        for before, after in (
            ("All due cards finished", "Today’s cards complete"),
            ("Anki day complete", "Today’s cards complete"),
            ("All Clear", "Today’s cards complete"),
            ("all clear", "today’s cards complete"),
            ("Rare stage reached", "Full Bloom"),
            ("rare stage reached", "Full Bloom"),
            ("reached Rare", "reached Full Bloom"),
            ("required cards", "cards"),
            ("Required cards", "Cards"),
        ):
            text = text.replace(before, after)
        text = re.sub(r"\banswers\b", "cards", text)
        text = re.sub(r"\bAnswers\b", "Cards", text)
        text = re.sub(r"\banswer\b", "card", text)
        text = re.sub(r"\bAnswer\b", "Card", text)
        return text

    @classmethod
    def _reward_stack_priority(cls, event: Any) -> tuple[int, str, str]:
        """Apply the approved order inside one committed correlation."""

        haystack = " ".join((
            str(getattr(event, "kind", "") or ""),
            str(getattr(event, "title", "") or ""),
            str(getattr(event, "message", "") or ""),
            str(getattr(event, "event_id", "") or ""),
        )).casefold()
        priority = 8
        if "full bloom" in haystack or "rare stage" in haystack:
            priority = 0
        elif "environment" in haystack or "weather discovered" in haystack or "scenery discovered" in haystack:
            priority = 1
        elif "new stage" in haystack or "stage:" in haystack:
            priority = 2
        elif "achievement" in haystack or "unlocked" in haystack:
            priority = 3
        elif "checkpoint" in haystack or "milestone" in haystack:
            priority = 4
        elif "garden_find" in haystack or "garden find" in haystack:
            priority = 5
        elif "all_due" in haystack or "today’s cards" in haystack or "streak" in haystack:
            priority = 6
        elif str(getattr(event, "kind", "") or "") == "reward_summary":
            priority = 7
        return (
            priority,
            str(getattr(event, "occurred_at", "") or ""),
            str(getattr(event, "event_id", "") or ""),
        )

    @staticmethod
    def _feedback_correlation_id(event: Any) -> str:
        correlation_id = str(getattr(event, "correlation_id", "") or "")
        if correlation_id:
            return correlation_id
        event_id = str(getattr(event, "event_id", "") or "")
        prefix = "reward-summary:"
        return event_id[len(prefix):] if event_id.startswith(prefix) else ""

    def _aggregate_reward_messages(self, events: list[Any]) -> str:
        """Render committed typed summaries without interpreting display prose."""

        achievement_definitions: Any = {}
        try:
            from ..achievements import ACHIEVEMENTS_BY_ID as achievement_definitions
            from ..reward_presentation import recent_reward_summaries

            summaries = recent_reward_summaries(self.storage.state)
        except (AttributeError, ImportError, TypeError, ValueError):
            summaries = ()

        summaries_by_correlation = {
            summary.correlation_id: summary for summary in summaries
        }
        parts: list[str] = []
        rendered_correlations: set[str] = set()
        for event in events:
            correlation_id = self._feedback_correlation_id(event)
            is_reward_event = self._is_reward_feedback_event(event)
            if (
                is_reward_event
                and correlation_id
                and correlation_id in rendered_correlations
            ):
                continue
            summary = (
                summaries_by_correlation.get(correlation_id)
                if is_reward_event
                else None
            )
            if summary is not None and correlation_id not in rendered_correlations:
                typed_parts = (
                    [self._player_reward_copy(summary.learner_text)]
                    if summary.learner_text else []
                )
                from ..achievements import milestone_unlocked_text
                achievement_names = [
                    milestone_unlocked_text(achievement_id)
                    for achievement_id in summary.achievement_ids
                    if achievement_id in achievement_definitions
                ]
                if achievement_names:
                    typed_parts.append(", ".join(achievement_names))
                if typed_parts:
                    parts.append("; ".join(typed_parts))
                    rendered_correlations.add(correlation_id)
                    continue

            # Non-reward feedback and pruned legacy reward summaries remain
            # opaque. Their prose is never parsed or numerically combined.
            message = self._player_reward_copy(getattr(event, "message", ""))
            if message and message not in parts:
                parts.append(message)
        return "; ".join(parts) or "Your Garden rewards were recorded."

    def _garden_find_presentations(self, events: list[Any]) -> tuple[Any, ...]:
        """Join pending Find events to their persisted display metadata."""

        try:
            from ..reward_presentation import lookup
        except Exception:
            return ()

        event_correlations = {
            self._feedback_correlation_id(event)
            for event in events
            if str(getattr(event, "kind", "")) == "garden_find"
        }
        event_correlations.discard("")
        answer_keys = {
            correlation[len("answer:"):]
            for correlation in event_correlations
            if correlation.startswith("answer:")
        }
        state = getattr(self.storage, "state", None)
        outcome_keys: list[tuple[str, str]] = []
        for receipt in getattr(state, "recent_reward_receipts", ()):
            if (
                str(getattr(receipt, "correlation_id", "")) not in event_correlations
                or str(getattr(receipt, "source", ""))
                not in {"garden_find", "garden_find_environment"}
            ):
                continue
            payload = str(getattr(receipt, "event_key", ""))
            if not payload.startswith("garden_find:"):
                continue
            answer_key, separator, pool_id = payload[len("garden_find:"):].rpartition(":")
            if separator and answer_key and pool_id:
                outcome_keys.append((pool_id, answer_key))

        resolver = getattr(self.storage, "recent_garden_find_outcomes", None)
        cached_outcomes = tuple(
            getattr(state, "garden_find_outcomes", {}).values()
        )
        if callable(resolver):
            try:
                stored_outcomes = tuple(resolver(limit=32))
            except Exception:
                stored_outcomes = ()
            # The bounded state cache contains the just-committed result even
            # when an adapter's historical query is stale or unavailable.
            by_outcome_key = {
                (
                    str(getattr(outcome, "pool_id", "")),
                    str(getattr(outcome, "answer_key", "")),
                ): outcome
                for outcome in stored_outcomes
            }
            by_outcome_key.update({
                (
                    str(getattr(outcome, "pool_id", "")),
                    str(getattr(outcome, "answer_key", "")),
                ): outcome
                for outcome in cached_outcomes
            })
            outcomes = tuple(by_outcome_key.values())
        else:
            outcomes = cached_outcomes
        if not outcome_keys and answer_keys:
            outcome_keys.extend(
                (str(getattr(outcome, "pool_id", "")), str(getattr(outcome, "answer_key", "")))
                for outcome in outcomes
                if str(getattr(outcome, "answer_key", "")) in answer_keys
            )

        registry = getattr(self.engine, "garden_find_registry", None)
        by_key = {
            (str(getattr(outcome, "pool_id", "")), str(getattr(outcome, "answer_key", ""))): outcome
            for outcome in outcomes
        }
        result: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for key in outcome_keys:
            if key in seen or key not in by_key:
                continue
            presentation = lookup(by_key[key], registry=registry)
            if presentation is not None:
                result.append(presentation)
                seen.add(key)
        return tuple(result)

    @staticmethod
    def _aggregate_find_details(presentations: tuple[Any, ...]) -> str:
        counts: dict[tuple[str, str], int] = {}
        for find in presentations:
            key = (str(find.display_name), str(find.description))
            counts[key] = counts.get(key, 0) + 1
        return "; ".join(
            f"{name} — {reward}" + (f" ×{count}" if count > 1 else "")
            for (name, reward), count in counts.items()
        )

    @staticmethod
    def _display_tier(tier: str) -> str:
        normalized = str(tier or "").replace("_environment", "").replace("_", " ")
        return normalized.title()

    def _show_reward_toast(self, event: Any) -> bool:
        """Render a quiet, image-led reward card without taking reviewer focus."""

        try:
            from aqt.qt import (
                QFrame,
                QHBoxLayout,
                QLabel,
                QPixmap,
                QPushButton,
                QSize,
                QTimer,
                QVBoxLayout,
                Qt,
            )

            class RewardToastFrame(QFrame):
                """Focus-safe toast whose timeout pauses while inspected."""

                def enterEvent(self, hover_event: Any) -> None:
                    callback = getattr(self, "_garden_pause_callback", None)
                    if callable(callback):
                        callback()
                    super().enterEvent(hover_event)

                def leaveEvent(self, hover_event: Any) -> None:
                    callback = getattr(self, "_garden_resume_callback", None)
                    if callable(callback):
                        callback()
                    super().leaveEvent(hover_event)

                def mouseReleaseEvent(self, mouse_event: Any) -> None:
                    callback = (
                        getattr(self, "_garden_activate_callback", None)
                        if bool(self.property("rewardSummary"))
                        else getattr(self, "_garden_dismiss_callback", None)
                    )
                    if (
                        mouse_event.button() == Qt.MouseButton.LeftButton
                        and callable(callback)
                    ):
                        callback()
                        mouse_event.accept()
                        return
                    super().mouseReleaseEvent(mouse_event)

            if str(getattr(mw, "state", "") or "") != "review":
                self._hide_reward_toast()
                return False
            parent = reviewer_overlay_parent(mw)
            reviewer = getattr(mw, "reviewer", None)
            reviewer_web = getattr(reviewer, "web", None)
            if reviewer_web is None or parent is not reviewer_web:
                self._hide_reward_toast()
                return False
            if reviewer_modal_active(mw):
                self._reward_feedback_deferred_for_modal = True
                return False

            self._reward_feedback_deferred_for_modal = False
            self._remember_reward_toast_event(event)
            viewport_width = max(1, int(parent.width()))
            viewport_height = max(1, int(parent.height()))
            projection = self._prepare_reward_toast_queue(
                parent,
                viewport_width,
                QPixmap(),
            )

            toast = RewardToastFrame(parent)
            toast.setObjectName("ankiGardenRewardToast")
            toast.setProperty("semanticId", "reviewer.reward-toast")
            toast.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            toast.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            toast.setMouseTracking(True)
            toast.setCursor(Qt.CursorShape.PointingHandCursor)
            toast.setProperty("rewardSummary", False)
            toast.setProperty("compactToast", projection.compact)
            toast.setProperty(
                "rewardOverflowCount",
                projection.overflow_count if projection.compact else 0,
            )
            toast.setProperty("rewardNotificationCount", 1)
            toast.setProperty(
                "rewardEventKey",
                self._reward_history_key(event),
            )
            toast.setProperty(
                "findTier",
                str(getattr(event, "tier", "") or "").strip().lower(),
            )
            toast.setProperty(
                "rewardEventCount",
                len(tuple(getattr(event, "event_ids", ()) or ())),
            )
            toast.setProperty(
                "rewardFindCount",
                max(0, int(getattr(event, "find_count", 0) or 0)),
            )
            toast.setProperty(
                "rewardHasTitle",
                bool(str(getattr(event, "title", "") or "").strip()),
            )
            toast.setProperty(
                "rewardHasMessage",
                bool(str(getattr(event, "message", "") or "").strip()),
            )
            toast.setProperty(
                "rewardHasDetail",
                bool(str(getattr(event, "reward_detail", "") or "").strip()),
            )
            accessible_parts = [
                self._player_reward_copy(
                    getattr(event, "title", "") or "Anki Garden update"
                ),
                str(getattr(event, "tier", "") or ""),
                self._player_reward_copy(getattr(event, "reward_detail", "")),
                self._player_reward_copy(getattr(event, "message", "")),
            ]
            if projection.compact and projection.overflow_count:
                accessible_parts.append(
                    f"+{projection.overflow_count} more rewards"
                )
            toast.setAccessibleName(
                ". ".join(part for part in accessible_parts if part)
            )
            toast.setStyleSheet(
                "QFrame#ankiGardenRewardToast {"
                f" background: {GARDEN_THEME['elevated_surface']}; border: 1px solid {GARDEN_THEME['subtle_border']};"
                " border-radius: 14px; }"
                f"QLabel#ankiGardenRewardTitle {{ color: {GARDEN_THEME['text_primary']};"
                " font-size: 13px; font-weight: 600; }"
                f"QLabel#ankiGardenRewardMessage {{ color: {GARDEN_THEME['text_primary']};"
                " font-size: 12px; }"
                f"QLabel#ankiGardenRewardDetail {{ color: {GARDEN_THEME['text_secondary']};"
                " font-size: 13px; font-weight: 600; }"
                f"QLabel#ankiGardenRewardOverflow {{ color: {GARDEN_THEME['text_secondary']};"
                " font-size: 12px; font-weight: 600; }"
                f"QLabel#ankiGardenRewardTier {{ color: {GARDEN_THEME['text_secondary']};"
                f" background: {GARDEN_THEME['selected_surface']}; border: 1px solid {GARDEN_THEME['strong_border']};"
                " border-radius: 6px; padding: 1px 5px; font-size: 11px; }"
                "QLabel#ankiGardenRewardTier[findTier=\"rare\"] {"
                f" color:{GARDEN_THEME['info']}; background:{GARDEN_THEME['selected_surface']}; border-color:{GARDEN_THEME['info']}; }}"
                "QLabel#ankiGardenRewardTier[findTier=\"exceptional\"] {"
                f" color:{GARDEN_THEME['coin_accent']}; background:{GARDEN_THEME['selected_surface']}; border-color:{GARDEN_THEME['coin_accent']}; }}"
                f"QLabel#ankiGardenRewardArt {{ background: {GARDEN_THEME['garden_background']};"
                f" border: 1px solid {GARDEN_THEME['subtle_border']}; border-radius: 11px;"
                f" color: {GARDEN_THEME['coin_accent']}; font-size: 24px; }}"
                "QPushButton#ankiGardenRewardClose { background: transparent;"
                f" border: 0; border-radius: 6px; color: {GARDEN_THEME['text_secondary']};"
                " font-size: 16px; font-weight: 600; padding: 0; }"
                "QPushButton#ankiGardenRewardClose:hover {"
                f" background: {GARDEN_THEME['elevated_surface']}; color: {GARDEN_THEME['text_primary']}; }}"
            )
            row = QHBoxLayout(toast)
            row.setContentsMargins(10, 8, 12, 8)
            row.setSpacing(8)

            art = QLabel("")
            art.setObjectName("ankiGardenRewardArt")
            art.setFixedSize(36, 36)
            art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art.setAccessibleName(self._reward_artwork_accessible_name(event))
            pixmap, bounds = self._reward_artwork(event, QPixmap)
            if pixmap is not None and not pixmap.isNull():
                if bounds is not None:
                    try:
                        x, y, width, height = (float(part) for part in bounds)
                        padding = 0.08
                        left = max(0.0, x - width * padding)
                        top = max(0.0, y - height * padding)
                        right = min(1.0, x + width * (1.0 + padding))
                        bottom = min(1.0, y + height * (1.0 + padding))
                        source_width, source_height = pixmap.width(), pixmap.height()
                        crop_x = max(0, min(source_width - 1, round(left * source_width)))
                        crop_y = max(0, min(source_height - 1, round(top * source_height)))
                        crop_width = max(
                            1, min(source_width - crop_x, round((right - left) * source_width))
                        )
                        crop_height = max(
                            1, min(source_height - crop_y, round((bottom - top) * source_height))
                        )
                        cropped = pixmap.copy(crop_x, crop_y, crop_width, crop_height)
                        if not cropped.isNull():
                            pixmap = cropped
                    except (TypeError, ValueError):
                        pass
                art.setText("")
                art.setPixmap(pixmap.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                try:
                    from ..ui.icons import garden_icon

                    icon_name = (
                        "coin"
                        if str(getattr(event, "asset_key", ""))
                        in {"garden_coin", "garden_coins"}
                        else "growth"
                    )
                    icon_color = (
                        GARDEN_THEME["coin_accent"]
                        if icon_name == "coin"
                        else GARDEN_THEME["growth_accent"]
                    )
                    art.setPixmap(
                        garden_icon(icon_name, color=icon_color).pixmap(32, 32)
                    )
                except Exception:
                    pass
            row.addWidget(art)

            copy = QVBoxLayout()
            copy.setSpacing(3)
            title = QLabel(self._player_reward_copy(
                getattr(event, "title", "") or self._reward_title(event)
            ))
            title.setObjectName("ankiGardenRewardTitle")
            tier_text = str(getattr(event, "tier", "") or "")
            tier: Any | None = None
            if tier_text:
                header = QHBoxLayout()
                header.setSpacing(7)
                header.addWidget(
                    title,
                    1,
                    Qt.AlignmentFlag.AlignBaseline,
                )
                tier = QLabel(tier_text)
                tier.setObjectName("ankiGardenRewardTier")
                tier.setProperty(
                    "findTier",
                    str(getattr(event, "tier", "") or "").strip().lower(),
                )
                tier_kind = (
                    "Garden discovery"
                    if str(getattr(event, "asset_category", "") or "")
                    == "environment"
                    else "Garden Find"
                )
                tier.setAccessibleName(f"{tier_kind} tier: {tier_text}")
                header.addWidget(
                    tier,
                    0,
                    Qt.AlignmentFlag.AlignBaseline,
                )
                copy.addLayout(header)
            else:
                copy.addWidget(title)
            reward_detail = self._player_reward_copy(
                getattr(event, "reward_detail", "")
            )
            reward = QLabel(reward_detail)
            reward.setObjectName("ankiGardenRewardDetail")
            reward.setWordWrap(True)
            reward.setVisible(bool(reward_detail))
            copy.addWidget(reward)
            message_text = self._player_reward_copy(getattr(event, "message", ""))
            if str(getattr(event, "kind", "") or "") == "garden_find":
                # A correlated Find is one notification even when it awards
                # multiple typed resources. Preserve the event model while
                # rendering each reward on its own compact line.
                message_text = "\n".join(
                    part.strip()
                    for part in message_text.replace("\n", " · ").split(" · ")
                    if part.strip()
                )
            message = QLabel(message_text)
            message.setObjectName("ankiGardenRewardMessage")
            message.setWordWrap(True)
            message.setVisible(bool(
                message_text
                and message_text != reward_detail
                and (not projection.compact or not reward_detail)
            ))
            copy.addWidget(message)
            overflow_copy = (
                f"+{projection.overflow_count} more rewards"
                if projection.compact and projection.overflow_count
                else ""
            )
            overflow = QLabel(overflow_copy)
            overflow.setObjectName("ankiGardenRewardOverflow")
            overflow.setVisible(bool(overflow_copy))
            copy.addWidget(overflow)
            row.addLayout(copy, 1)

            close = QPushButton("")
            close.setObjectName("ankiGardenRewardClose")
            close.setFixedSize(32, 32)
            from ..ui.icons import garden_icon

            close.setIcon(
                garden_icon(
                    "close",
                    color=GARDEN_THEME["text_secondary"],
                )
            )
            close.setIconSize(QSize(18, 18))
            close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            close.setAccessibleName("Close Garden reward notification")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.clicked.connect(
                lambda _checked=False, target=toast:
                self._dismiss_reward_toast(target)
            )
            row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

            if tier is None:
                hidden_tier = QLabel("", toast)
                hidden_tier.hide()
            else:
                hidden_tier = tier
            toast._garden_title_label = title
            toast._garden_tier_label = hidden_tier
            toast._garden_detail_label = reward
            toast._garden_message_label = message
            toast._garden_overflow_label = overflow
            toast._garden_art_label = art
            toast._garden_dismiss_callback = (
                lambda target=toast: self._dismiss_reward_toast(target)
            )
            toast._garden_pause_callback = self._pause_reward_toast_stack
            toast._garden_resume_callback = self._resume_reward_toast_stack
            toast._garden_hover_resume_ms = GardenToastStack.HOVER_RESUME_MS
            if projection.compact and projection.overflow_count:
                toast._garden_activate_callback = (
                    lambda parent=parent: self._expand_reward_summary(parent)
                )

            toast_width = GardenToastStack.toast_width(viewport_width)
            hud = getattr(self, "_reviewer_hud", None)
            hud_projection = getattr(self, "_reviewer_hud_projection", None)
            if hud is not None and not bool(getattr(hud_projection, "collapsed", False)):
                try:
                    toast_width = min(toast_width, max(1, int(hud.width()) - 12))
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
            toast.setFixedWidth(toast_width)
            toast.adjustSize()
            projected_visible = max(
                1,
                min(
                    GardenToastStack.MAX_VISIBLE,
                    len(self._reward_toasts) + 1,
                ),
            )
            stack_budget = max(56, int(viewport_height * 0.40))
            per_toast_budget = max(
                48,
                (
                    stack_budget
                    - GardenToastStack.GAP * (projected_visible - 1)
                ) // projected_visible,
            )
            maximum_height = min(
                64 if projection.compact else 72,
                per_toast_budget,
            )
            preferred_height = max(48, min(maximum_height, toast.sizeHint().height()))
            toast.setFixedHeight(
                min(preferred_height, max(1, viewport_height - 32))
            )
            x, y = reviewer_reward_overlay_position(
                viewport_width,
                viewport_height,
                toast.width(),
                toast.height(),
                margin=16,
            )
            toast.move(x, y)
            toast.setProperty("reviewerOverlay", True)
            toast.setProperty(
                "reviewerOverlayAnchor",
                "reviewer-webview-right-above-controls",
            )
            toast.setProperty("reviewerViewportMargin", 16)
            toast.setProperty("reviewerControlClearance", 144)
            toast.setProperty("reviewerControlGap", 16)
            toast.setProperty("reviewerToastGap", GardenToastStack.GAP)
            toast.setProperty("reviewerViewportWidth", viewport_width)
            toast.setProperty("reviewerViewportHeight", viewport_height)
            toast.setProperty(
                "reviewerViewportBounded",
                bool(
                    x >= 0
                    and y >= 0
                    and x + toast.width() <= viewport_width
                    and y + toast.height() <= viewport_height
                ),
            )
            toast.show()
            toast.raise_()
            dismiss_timer = QTimer(toast)
            dismiss_timer.setSingleShot(True)
            dismiss_timer.timeout.connect(self._dismiss_reward_toast_stack)
            toast._garden_dismiss_timer = dismiss_timer
            self._reward_toasts.append(toast)
            self._reward_toast = toast
            self._position_reward_toast_stack(parent)
            for live_toast in list(self._reward_toasts):
                timer = getattr(live_toast, "_garden_dismiss_timer", None)
                if timer is not None:
                    timer.start(GardenToastStack.AUTO_DISMISS_MS)
            return True
        except Exception:
            logger.debug("Anki Garden: unable to show image reward feedback", exc_info=True)
            try:
                from aqt.utils import tooltip

                tooltip(str(getattr(event, "message", "")), period=4000, parent=mw)
                return True
            except Exception:
                logger.debug("Anki Garden: unable to show fallback reward feedback", exc_info=True)
                return False

    @staticmethod
    def _reward_title(event: Any) -> str:
        if str(getattr(event, "kind", "")) == "garden_find":
            return (
                "Garden discovery"
                if str(getattr(event, "asset_category", "") or "")
                == "environment"
                else "Garden Find"
            )
        return {
            "reward_summary": "Review rewards",
        }.get(str(getattr(event, "kind", "")), "Garden reward")

    @staticmethod
    def _reward_artwork_glyph(event: Any) -> str:
        """Compatibility adapter; reviewer artwork now uses the shared icon family."""

        return ""

    @staticmethod
    def _reward_artwork_accessible_name(event: Any) -> str:
        return {
            "growth": "Growth icon",
            "garden_coin": "Garden Coin icon",
            "garden_coins": "Garden Coin icon",
            "garden_pouch": "Garden Pouch artwork",
            "morning_dew": "Morning Dew artwork",
        }.get(str(getattr(event, "asset_key", "") or ""), "Reward artwork")

    def _reward_artwork(self, event: Any, pixmap_type: Any) -> tuple[Any | None, Any | None]:
        asset_key = str(getattr(event, "asset_key", "") or "")
        asset_category = str(getattr(event, "asset_category", "") or "")
        if asset_category == "ui" and asset_key:
            asset_key = {
                "ui_growth_charge_small": "growth_charge_small",
                "ui_growth_charge_standard": "growth_charge_standard",
                "ui_fertilizer_basic": "fertilizer_basic",
                "ui_rich_compost": "rich_compost",
                "ui_booster_potion": "booster_potion",
            }.get(asset_key, asset_key)
            resolver = getattr(self.engine, "resolve_item_asset", None)
            try:
                asset = resolver(asset_key) if callable(resolver) else None
                path = getattr(asset, "path", None)
                if path:
                    return pixmap_type(str(path)), None
            except Exception:
                logger.debug("Anki Garden: unable to resolve reward item art", exc_info=True)
        if asset_category == "environment" and asset_key:
            for resolver_name in (
                "resolve_garden_feature_preview_asset",
                "resolve_scenery_preview_asset",
            ):
                resolver = getattr(self.engine, resolver_name, None)
                try:
                    asset = resolver(asset_key) if callable(resolver) else None
                    path = getattr(asset, "path", None)
                    if path:
                        return pixmap_type(str(path)), None
                except Exception:
                    logger.debug(
                        "Anki Garden: unable to resolve Garden Find environment art",
                        exc_info=True,
                    )
        if asset_category in {"garden_features", "weather", "backgrounds"} and asset_key:
            resolver = getattr(
                self.engine,
                "resolve_garden_feature_preview_asset"
                if asset_category in {"garden_features", "weather"}
                else "resolve_scenery_preview_asset",
                None,
            )
            try:
                asset = resolver(asset_key) if callable(resolver) else None
                path = getattr(asset, "path", None)
                if path:
                    return pixmap_type(str(path)), None
            except Exception:
                logger.debug(
                    "Anki Garden: unable to resolve environment reward art",
                    exc_info=True,
                )
        plant_id = str(getattr(event, "plant_id", "") or "")
        if plant_id:
            plant = next(
                (
                    item for item in getattr(getattr(self.engine, "state", None), "plants", [])
                    if str(getattr(item, "plant_id", "")) == plant_id
                ),
                None,
            )
            if plant is not None:
                try:
                    asset = self.engine.resolve_plant_asset(
                        str(getattr(plant, "species", "")),
                        str(getattr(plant, "growth_stage", "seed")),
                    )
                    path = getattr(asset, "path", None)
                    placement = getattr(asset, "placement", None)
                    bounds = (
                        placement.get("visible_bounds", placement.get("art_bounds"))
                        if isinstance(placement, dict)
                        else getattr(
                            placement,
                            "visible_bounds",
                            getattr(placement, "art_bounds", None),
                        )
                    )
                    return (pixmap_type(str(path)), bounds) if path else (None, None)
                except Exception:
                    logger.debug("Anki Garden: unable to resolve reward plant art", exc_info=True)
        return None, None
