from __future__ import annotations

import logging
from typing import Any

from aqt import mw

from ..game import difficulty_from_factor, queue_and_lapse_from_revlog_type
from ..notices import USER_NOTICES
from ..storage import unprocessed_revlog_entries


logger = logging.getLogger(__name__)


class ReviewerHookHandler:
    def __init__(self, engine: Any, storage: Any) -> None:
        self.engine = engine
        self.storage = storage
        self._last_notified_event = ""

    @staticmethod
    def review_payload_from_row(row: tuple[Any, ...], collection: Any) -> dict[str, Any] | None:
        """Convert one authoritative revlog row into Garden answer semantics."""
        rid, cid, ease, ivl, last_ivl, factor, _answer_ms, review_type = row
        semantics = queue_and_lapse_from_revlog_type(review_type, ease)
        if semantics is None:
            return None
        queue, lapse_count = semantics
        deck_id = None
        try:
            deck_id = int(collection.get_card(int(cid)).did)
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
            "answered_at_ms": int(rid),
        }

    @staticmethod
    def unseen_revlog_rows(rows: list[tuple[Any, ...]], state: Any) -> list[tuple[Any, ...]]:
        return unprocessed_revlog_entries(state, rows)

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        last_processed = int(
            getattr(getattr(self.storage, "state", None), "last_processed_revlog_id", 0) or 0
        )
        try:
            prepare_ledger = getattr(self.storage, "ensure_revlog_ledger_ready", None)
            if callable(prepare_ledger):
                prepare_ledger()
            newest_revlog_id = self.storage.max_revlog_id()
        except Exception:
            logger.exception(
                "Anki Garden: review-history id unavailable; deferring this answer to catch-up"
            )
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
            self._show_deferred_history_notice()
            return
        rows = self.unseen_revlog_rows(day_rows, self.storage.state)
        if not rows:
            # The reviewer hook can run before the just-written revlog row is
            # visible to a read. Leaving the cursor untouched lets maintenance
            # reconcile it once the collection transaction is complete.
            logger.warning(
                "Anki Garden: newest revlog row was not readable yet; deferring to catch-up"
            )
            self._show_deferred_history_notice()
            return

        collection = getattr(getattr(self.storage, "mw", None), "col", None)
        if collection is None:
            collection = getattr(mw, "col", None)
        latest_read_id = max(int(row[0]) for row in rows)
        payloads = [
            payload
            for payload in (
                self.review_payload_from_row(row, collection)
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
            message = (
                "Your card answer was saved in Anki, but its Garden Growth could not be saved. "
                "Open Anki Garden to retry after the problem is resolved."
            )
            if USER_NOTICES.publish(message, key="review_history"):
                try:
                    from aqt.utils import tooltip
                    tooltip(message, period=7000, parent=mw)
                except Exception:
                    logger.debug("Anki Garden: unable to show review-save notice", exc_info=True)
            return

        USER_NOTICES.clear(key="review_history")

        try:
            self.engine.evaluate_all_due(self.storage.due_obligations())
        except Exception:
            logger.debug("Anki Garden: unable to evaluate all-due completion after review", exc_info=True)
        self._show_optional_progress_feedback()

    @staticmethod
    def _show_deferred_history_notice() -> None:
        message = (
            "Your card answer is safe in Anki. Garden could not read it yet and will retry automatically."
        )
        if USER_NOTICES.publish(message, key="review_history"):
            try:
                from aqt.utils import tooltip

                tooltip(message, period=7000, parent=mw)
            except Exception:
                logger.debug("Anki Garden: unable to show deferred-review notice", exc_info=True)

    def _show_optional_progress_feedback(self) -> None:
        config = getattr(self.engine, "config", None)
        if config is None or not bool(config.value("show_progress_notifications", False)):
            return
        events = self.engine.peek_feedback()
        if not events or events[-1].event_id == self._last_notified_event:
            return
        event = events[-1]
        self._last_notified_event = event.event_id
        try:
            from aqt.utils import tooltip
            tooltip(event.message, period=3500, parent=mw)
        except Exception:
            logger.debug("Anki Garden: unable to show optional progress feedback", exc_info=True)
