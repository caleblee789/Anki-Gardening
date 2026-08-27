from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping

from aqt import mw

from ..config import DEFAULT_CONFIG
from ..game import difficulty_from_factor, queue_and_lapse_from_revlog_type
from ..notices import USER_NOTICES
from ..performance import RUNTIME_PERFORMANCE
from ..storage import assign_stable_answer_identities, unprocessed_revlog_entries
from ..ui.copy import REVIEWER_NO_STARTER_NOTICE


logger = logging.getLogger(__name__)


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
    reviewer_controls_clearance: int = 112,
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
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.state_changed = state_changed
        self.history_invalidated = history_invalidated
        self._local_answer_fast_path_ready = False
        self._last_notified_event = ""
        self._notified_event_ids: set[str] = set()
        self._reward_toast: Any | None = None
        self._reward_toasts: list[Any] = []
        self._reward_toast_overflow = 0
        self._reward_feedback_deferred_for_modal = False
        self._reviewer_notice: Any | None = None
        self._reviewer_notice_shown = False
        self._reviewer_session_window: Any | None = None

    def on_question(self, *_args: Any, **_kwargs: Any) -> None:
        """Show one non-modal eligibility reminder before a reviewer answer."""

        try:
            observe = getattr(self.engine, "observe_due_start", None)
            if callable(observe):
                observe(self.storage.due_obligations())
        except Exception:
            logger.debug(
                "Anki Garden: unable to record the pre-answer due baseline",
                exc_info=True,
            )

        if bool(getattr(getattr(self.storage, "state", None), "starter_selection_complete", False)):
            self._hide_no_starter_notice()
            if (
                self._reward_feedback_deferred_for_modal
                and not reviewer_modal_active(mw)
            ):
                self._reward_feedback_deferred_for_modal = False
                self._show_optional_progress_feedback()
            return
        reviewer_window = getattr(mw, "reviewer", None)
        if reviewer_window is not None and reviewer_window is not self._reviewer_session_window:
            self._reviewer_session_window = reviewer_window
            self._reviewer_notice_shown = False
            self._hide_no_starter_notice()
        if self._reviewer_notice_shown:
            return
        self._reviewer_notice_shown = True
        self._show_no_starter_notice()

    def on_starter_selected(self) -> None:
        """Remove the session reminder as soon as starter persistence succeeds."""

        self._reviewer_notice_shown = False
        self._hide_no_starter_notice()

    def on_state_change(self, new_state: str, *_args: Any) -> None:
        """Unmount Reviewer-only feedback before another Anki surface paints."""

        if str(new_state or "") == "review":
            return
        self._hide_reward_toast()
        self._hide_no_starter_notice()
        self._reviewer_session_window = None
        self._reviewer_notice_shown = False

    def _hide_reward_toast(self) -> None:
        toasts = list(getattr(self, "_reward_toasts", []) or [])
        toast = self._reward_toast
        if toast is not None and toast not in toasts:
            toasts.append(toast)
        self._reward_toasts = []
        self._reward_toast_overflow = 0
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

    def _position_reward_toast_stack(self, parent: Any) -> None:
        """Stack at most two cards above Anki's answer controls."""

        viewport_width = max(1, int(parent.width()))
        viewport_height = max(1, int(parent.height()))
        next_bottom = max(16, viewport_height - 112)
        live: list[Any] = []
        for toast in reversed(list(getattr(self, "_reward_toasts", []) or [])):
            try:
                x, _preferred_y = reviewer_reward_overlay_position(
                    viewport_width,
                    viewport_height,
                    toast.width(),
                    toast.height(),
                    margin=16,
                )
                y = max(16, next_bottom - int(toast.height()))
                toast.move(x, y)
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
        toast._garden_art_label.setText("+")
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
            if (
                bool(toast.property("rewardSummary"))
                or bool(toast.property("compactToast"))
            ):
                self._reward_toast_overflow = 0
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
                "QFrame#ankiGardenReviewerStarterNotice { background:#17342e; "
                "border:1px solid #557665; border-radius:8px; padding:7px 10px; }"
                "QLabel { color:#e8f1eb; font-size:12px; }"
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
            if pending:
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

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        started = RUNTIME_PERFORMANCE.begin()
        try:
            self._process_answer(reviewer, card, ease)
        finally:
            RUNTIME_PERFORMANCE.finish("review.answer", started)

    def _process_answer(self, reviewer: Any, card: Any, ease: int) -> None:
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
            self._show_deferred_history_notice()
            return
        local_history = self._proven_local_answer(card, ease, last_processed)
        if local_history is None:
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
        binding_resolver = getattr(
            self.storage, "answer_lineage_bindings_for_cards", None
        )
        existing_bindings = (
            binding_resolver({int(row[1]) for row in day_rows})
            if callable(binding_resolver)
            else getattr(self.storage.state, "answer_lineage_bindings", {})
        )
        identities = self.stable_answer_identities(
            day_rows,
            scheduler_day=scheduler_day,
            existing_bindings=existing_bindings,
            reanswer_hints=getattr(
                self.storage.state, "pending_reanswer_lineages", {}
            ),
        )
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
        try:
            # Commit every unseen row as one state transaction. In particular,
            # never jump the cursor to only the newest answer after an earlier
            # Garden save failed.
            self.engine.apply_same_day_reviews(
                payloads,
                latest_revlog_id=latest_read_id,
            )
        except Exception:
            logger.exception("Anki Garden: review progress could not be saved")
            self._report_history_invalidation("review save failed")
            message = (
                "Your card answer is safe in Anki, but Garden couldn’t save its Growth. "
                "Open garden to try again."
            )
            if USER_NOTICES.publish(message, key="review_history"):
                try:
                    from aqt.utils import tooltip
                    tooltip(message, period=7000, parent=mw)
                except Exception:
                    logger.debug("Anki Garden: unable to show review-save notice", exc_info=True)
            return

        self.mark_history_reconciled()
        USER_NOTICES.clear(key="review_history")

        if bool(getattr(getattr(self.storage, "state", None), "starter_selection_complete", False)):
            self._hide_no_starter_notice()

        try:
            self.engine.evaluate_all_due(self.storage.due_obligations())
        except Exception:
            logger.debug("Anki Garden: unable to evaluate all-due completion after review", exc_info=True)
        if self.state_changed is not None:
            try:
                self.state_changed("Card answer counted")
            except Exception:
                logger.debug("Anki Garden: unable to publish review state change", exc_info=True)
        self._show_optional_progress_feedback()

    @staticmethod
    def _show_deferred_history_notice() -> None:
        message = (
            "Your card answer is safe in Anki. Garden will add it when review history is available."
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
        event = self._consolidated_reward_feedback(unnotified)
        if event is None:
            return
        rendered = self._show_reward_toast(event)
        if not rendered:
            return
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
            event_id = str(getattr(event, "event_id", "") or "")
            if not event_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            unique.append(event)
        if not unique:
            return None

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
            str(getattr(event, "message", "") or "").strip()
            for event in unique
            if not self._is_reward_feedback_event(event)
            and str(getattr(event, "message", "") or "").strip()
        ))
        if nonreward_messages and not reward_parts:
            reward_parts.append(nonreward_messages[0])
        message = " · ".join(reward_parts)
        title = str(getattr(preferred, "title", "") or "")
        tier = ""
        reward_detail = ""
        asset_category = str(getattr(preferred, "asset_category", "") or "")
        asset_key = str(getattr(preferred, "asset_key", "") or "")

        if presentations:
            find = presentations[0]
            title = "Garden Find"
            tier = self._display_tier(find.tier)
            if str(find.pool_id) == "environment" and environment_total:
                message = "Added to Weather and Scenery"
            elif not message:
                message = str(find.description)
            first_find = presentations[0]
            asset_key = str(first_find.artwork_ref or asset_key)
            asset_category = (
                "environment"
                if str(first_find.pool_id) == "environment"
                else "ui"
            )
        elif find_events:
            title = title.removeprefix("Garden Find:").strip() or "Garden reward"

        find_count = max(len(find_events), len(presentations))
        if find_count > 1:
            title = "Garden Find"
            message = " · ".join(reward_parts) or "Garden rewards added"
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
            message=message,
            occurred_at=max(
                str(getattr(event, "occurred_at", "")) for event in unique
            ),
            plant_id=str(getattr(preferred, "plant_id", "") or "") or None,
            title=title,
            asset_category=asset_category,
            asset_key=asset_key,
            correlation_id=self._feedback_correlation_id(preferred),
            tier=tier,
            reward_detail=reward_detail,
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
                typed_parts = [summary.learner_text] if summary.learner_text else []
                achievement_names = [
                    achievement_definitions[achievement_id].name
                    for achievement_id in summary.achievement_ids
                    if achievement_id in achievement_definitions
                ]
                if achievement_names:
                    typed_parts.append("Unlocked " + ", ".join(achievement_names))
                if typed_parts:
                    parts.append("; ".join(typed_parts))
                    rendered_correlations.add(correlation_id)
                    continue

            # Non-reward feedback and pruned legacy reward summaries remain
            # opaque. Their prose is never parsed or numerically combined.
            message = str(getattr(event, "message", "") or "").strip()
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
                QTimer,
                QVBoxLayout,
                Qt,
            )

            class RewardToastFrame(QFrame):
                """Focus-safe toast whose timeout pauses while inspected."""

                def enterEvent(self, hover_event: Any) -> None:
                    timer = getattr(self, "_garden_dismiss_timer", None)
                    if timer is not None:
                        timer.stop()
                    super().enterEvent(hover_event)

                def leaveEvent(self, hover_event: Any) -> None:
                    timer = getattr(self, "_garden_dismiss_timer", None)
                    if timer is not None:
                        timer.start(GardenToastStack.HOVER_RESUME_MS)
                    super().leaveEvent(hover_event)

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
            toast.setProperty("rewardSummary", False)
            toast.setProperty("compactToast", projection.compact)
            toast.setProperty(
                "rewardOverflowCount",
                projection.overflow_count if projection.compact else 0,
            )
            toast.setProperty("rewardNotificationCount", 1)
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
                str(getattr(event, "title", "") or "Anki Garden update"),
                str(getattr(event, "tier", "") or ""),
                str(getattr(event, "reward_detail", "") or ""),
                str(getattr(event, "message", "") or ""),
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
                " background: #13352d; border: 1px solid #416353;"
                " border-radius: 14px; }"
                "QLabel#ankiGardenRewardTitle { color: #f5df9a;"
                " font-size: 13px; font-weight: 600; }"
                "QLabel#ankiGardenRewardMessage { color: #e8f1eb;"
                " font-size: 12px; }"
                "QLabel#ankiGardenRewardDetail { color: #f5df9a;"
                " font-size: 13px; font-weight: 600; }"
                "QLabel#ankiGardenRewardOverflow { color: #bad5c3;"
                " font-size: 12px; font-weight: 600; }"
                "QLabel#ankiGardenRewardTier { color: #bad5c3;"
                " background: #21483d; border: 1px solid #4e7765;"
                " border-radius: 7px; padding: 1px 6px; font-size: 12px; }"
                "QLabel#ankiGardenRewardTier[findTier=\"rare\"] {"
                " color:#d8e8ff; background:#263f50; border-color:#647d99; }"
                "QLabel#ankiGardenRewardTier[findTier=\"exceptional\"] {"
                " color:#eadfff; background:#3b324d; border-color:#8773a8; }"
                "QLabel#ankiGardenRewardArt { background: #0b251f;"
                " border: 1px solid #345a4c; border-radius: 11px;"
                " color: #f5df9a; font-size: 24px; }"
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
                    art.setPixmap(
                        garden_icon(icon_name, color="#f5df9a").pixmap(32, 32)
                    )
                except Exception:
                    pass
            row.addWidget(art)

            copy = QVBoxLayout()
            copy.setSpacing(3)
            title = QLabel(getattr(event, "title", "") or self._reward_title(event))
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
                tier.setAccessibleName(f"Garden Find tier: {tier_text}")
                header.addWidget(
                    tier,
                    0,
                    Qt.AlignmentFlag.AlignBaseline,
                )
                copy.addLayout(header)
            else:
                copy.addWidget(title)
            reward_detail = str(getattr(event, "reward_detail", "") or "")
            reward = QLabel(reward_detail)
            reward.setObjectName("ankiGardenRewardDetail")
            reward.setWordWrap(True)
            reward.setVisible(bool(reward_detail))
            copy.addWidget(reward)
            message_text = str(getattr(event, "message", "") or "")
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

            toast.setFixedWidth(GardenToastStack.toast_width(viewport_width))
            toast.adjustSize()
            maximum_height = 64 if projection.compact else 72
            preferred_height = max(56, min(maximum_height, toast.sizeHint().height()))
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
            toast.setProperty("reviewerControlClearance", 112)
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
            dismiss_timer.timeout.connect(
                lambda toast=toast: self._dismiss_reward_toast(toast)
            )
            toast._garden_dismiss_timer = dismiss_timer
            self._reward_toasts.append(toast)
            self._reward_toast = toast
            self._position_reward_toast_stack(parent)
            dismiss_timer.start(GardenToastStack.AUTO_DISMISS_MS)
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
        return {
            "garden_find": "Garden Find",
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
        }.get(str(getattr(event, "asset_key", "") or ""), "Reward artwork")

    def _reward_artwork(self, event: Any, pixmap_type: Any) -> tuple[Any | None, Any | None]:
        asset_key = str(getattr(event, "asset_key", "") or "")
        asset_category = str(getattr(event, "asset_category", "") or "")
        if asset_category == "ui" and asset_key:
            asset_key = {
                "ui_growth_charge_small": "growth_charge_small",
                "ui_growth_charge_standard": "growth_charge_standard",
                "ui_fertilizer_basic": "fertilizer_basic",
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
                "resolve_weather_preview_asset",
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
        if asset_category in {"weather", "backgrounds"} and asset_key:
            resolver = getattr(
                self.engine,
                "resolve_weather_preview_asset"
                if asset_category == "weather"
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
