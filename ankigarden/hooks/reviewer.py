from __future__ import annotations

import logging
from typing import Any, Callable

from aqt import mw

from ..game import difficulty_from_factor, queue_and_lapse_from_revlog_type
from ..notices import USER_NOTICES
from ..storage import unprocessed_revlog_entries
from ..ui.copy import REVIEWER_NO_STARTER_NOTICE


logger = logging.getLogger(__name__)


class ReviewerHookHandler:
    def __init__(
        self,
        engine: Any,
        storage: Any,
        state_changed: Callable[[str], None] | None = None,
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.state_changed = state_changed
        self._last_notified_event = ""
        self._reward_toast: Any | None = None
        self._reviewer_notice: Any | None = None
        self._reviewer_notice_shown = False
        self._reviewer_session_window: Any | None = None

    def on_question(self, *_args: Any, **_kwargs: Any) -> None:
        """Show one non-modal eligibility reminder before a reviewer answer."""

        if bool(getattr(getattr(self.storage, "state", None), "starter_selection_complete", False)):
            self._hide_no_starter_notice()
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

    def _show_no_starter_notice(self) -> None:
        try:
            from aqt.qt import QFrame, QLabel, QTimer, Qt

            previous = self._reviewer_notice
            if previous is not None:
                previous.hide()
                previous.deleteLater()
            notice = QFrame(mw)
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
            width_attr = getattr(mw, "width", None)
            parent_width = int(width_attr()) if callable(width_attr) else int(width_attr or 720)
            parent_width = max(parent_width, notice.width())
            notice.move(max(12, parent_width - notice.width() - 18), 18)
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
        if not events:
            return
        priority = {
            "environment_drop": 100,
            "charge_drop": 90,
            "booster_drop": 60,
            "coin_drop": 50,
            "stage": 40,
            "currency": 35,
            "streak": 30,
            "growth_milestone": 10,
        }
        event = max(
            events,
            key=lambda item: (
                priority.get(str(getattr(item, "kind", "")), 20),
                str(getattr(item, "occurred_at", "")),
            ),
        )
        if event.event_id == self._last_notified_event:
            return
        rendered = self._show_reward_toast(event)
        if not rendered:
            return
        self._last_notified_event = event.event_id
        try:
            consume = getattr(self.engine, "consume_feedback", None)
            if callable(consume):
                consume(event_ids=(event.event_id,))
        except Exception:
            # The event was rendered. Keep its id locally so a transient save
            # failure does not show the same reward twice during this session.
            logger.debug("Anki Garden: unable to acknowledge rendered feedback", exc_info=True)

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

            parent = mw
            previous = self._reward_toast
            if previous is not None:
                try:
                    previous.hide()
                    previous.deleteLater()
                except Exception:
                    pass

            toast = QFrame(parent)
            toast.setObjectName("ankiGardenRewardToast")
            toast.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            toast.setAccessibleName(
                f"{getattr(event, 'title', '') or 'Anki Garden update'}. "
                f"{getattr(event, 'message', '')}"
            )
            toast.setStyleSheet(
                "QFrame#ankiGardenRewardToast {"
                " background: #13352d; border: 1px solid #5f8c72;"
                " border-radius: 14px; }"
                "QLabel#ankiGardenRewardTitle { color: #f5df9a;"
                " font-size: 14px; font-weight: 700; }"
                "QLabel#ankiGardenRewardMessage { color: #e8f1eb;"
                " font-size: 12px; }"
                "QLabel#ankiGardenRewardArt { background: #0b251f;"
                " border: 1px solid #345a4c; border-radius: 11px;"
                " color: #f5df9a; font-size: 24px; }"
            )
            row = QHBoxLayout(toast)
            row.setContentsMargins(12, 10, 14, 10)
            row.setSpacing(11)

            art = QLabel("✦")
            art.setObjectName("ankiGardenRewardArt")
            art.setFixedSize(58, 58)
            art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art.setAccessibleName("Reward artwork")
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
                    48,
                    48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            row.addWidget(art)

            copy = QVBoxLayout()
            copy.setSpacing(3)
            title = QLabel(getattr(event, "title", "") or self._reward_title(event))
            title.setObjectName("ankiGardenRewardTitle")
            message = QLabel(str(getattr(event, "message", "")))
            message.setObjectName("ankiGardenRewardMessage")
            message.setWordWrap(True)
            copy.addWidget(title)
            copy.addWidget(message)
            row.addLayout(copy, 1)

            toast.setFixedWidth(390)
            toast.adjustSize()
            parent_width = max(toast.width(), int(parent.width()))
            parent_height = max(toast.height(), int(parent.height()))
            toast.move(
                max(16, parent_width - toast.width() - 20),
                max(16, parent_height - toast.height() - 54),
            )
            toast.show()
            toast.raise_()
            self._reward_toast = toast

            def dismiss() -> None:
                if self._reward_toast is toast:
                    self._reward_toast = None
                toast.hide()
                toast.deleteLater()

            QTimer.singleShot(4200, dismiss)
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
            "environment_drop": "A rare garden discovery",
            "charge_drop": "A Growth Charge appeared",
            "booster_drop": "A rare garden gift",
            "coin_drop": "A little garden gift",
            "growth_milestone": "Growing beautifully",
            "streak": "Anki streak milestone",
            "currency": "Garden Coins earned",
        }.get(str(getattr(event, "kind", "")), "Your garden is growing")

    def _reward_artwork(self, event: Any, pixmap_type: Any) -> tuple[Any | None, Any | None]:
        asset_key = str(getattr(event, "asset_key", "") or "")
        asset_category = str(getattr(event, "asset_category", "") or "")
        if asset_category == "ui" and asset_key:
            resolver = getattr(self.engine, "resolve_item_asset", None)
            try:
                asset = resolver(asset_key) if callable(resolver) else None
                path = getattr(asset, "path", None)
                if path:
                    return pixmap_type(str(path)), None
            except Exception:
                logger.debug("Anki Garden: unable to resolve reward item art", exc_info=True)
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
