from __future__ import annotations

import logging
from typing import Any

from aqt import mw


logger = logging.getLogger(__name__)


class ReviewerHookHandler:
    def __init__(self, engine: Any, storage: Any) -> None:
        self.engine = engine
        self.storage = storage

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        factor = getattr(card, "factor", 2500)
        difficulty = max(0.1, min(1.0, (3000 - factor) / 2000))
        payload = {
            "queue": getattr(card, "queue", 2),
            "ease": ease,
            "deck_id": getattr(card, "did", None),
            "difficulty": difficulty,
            "lapse_count": int(getattr(card, "lapses", 0)),
            "revlog_id": self.storage.max_revlog_id() if hasattr(self.storage, "max_revlog_id") else 0,
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
