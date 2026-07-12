from __future__ import annotations

import logging
from typing import Any

from aqt import mw

from ..game import difficulty_from_factor, queue_and_lapse_from_revlog_type


logger = logging.getLogger(__name__)


class ReviewerHookHandler:
    def __init__(self, engine: Any, storage: Any) -> None:
        self.engine = engine
        self.storage = storage

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        difficulty = difficulty_from_factor(getattr(card, "factor", 2500))
        revlog_id = self.storage.max_revlog_id() if hasattr(self.storage, "max_revlog_id") else 0
        review_type = (
            self.storage.review_type_for_revlog_id(revlog_id)
            if revlog_id and hasattr(self.storage, "review_type_for_revlog_id")
            else None
        )
        semantics = queue_and_lapse_from_revlog_type(review_type, ease)
        queue = semantics[0] if semantics is not None else getattr(card, "queue", 2)
        lapse_count = semantics[1] if semantics is not None else int(getattr(card, "lapses", 0))
        payload = {
            "queue": queue,
            "ease": ease,
            "deck_id": getattr(card, "did", None),
            "difficulty": difficulty,
            "lapse_count": lapse_count,
            "revlog_id": revlog_id,
        }
        try:
            self.engine.register_review(payload)
        except Exception:
            logger.exception("Anki Garden: review progress could not be saved")
            return

        try:
            due = mw.col.sched.counts()
            self.engine.set_due_completion(sum(due) == 0)
        except Exception:
            pass
