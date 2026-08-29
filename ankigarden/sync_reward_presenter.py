"""Lifecycle owner for the durable, nonmodal sync reward receipt."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .models.sync_reward import SyncRewardSummary
from .ui.sync_reward_summary import SyncRewardSummaryCard


logger = logging.getLogger(__name__)


try:  # Presenter contracts remain importable in source-only test processes.
    from aqt.qt import QApplication, QTimer
except Exception:  # pragma: no cover - exercised outside Anki's Qt runtime.
    QApplication = None  # type: ignore[assignment]
    QTimer = None  # type: ignore[assignment]


class SyncRewardPresenter:
    """Serialize, defer, mount, merge, and acknowledge sync reward receipts.

    ``storage.state.pending_sync_reward_summary`` remains the durable authority.
    A receipt is cleared only after the corresponding model mounted successfully
    (or presentation is explicitly suppressed by the setting), and only when a
    fresh read proves that no newer merged receipt has replaced it.
    """

    RETRY_DELAY_MS = 150

    def __init__(
        self,
        mw: Any,
        storage: Any,
        *,
        enabled: Callable[[], bool],
        open_garden: Callable[[], None],
        can_present: Callable[[], bool] | None = None,
    ) -> None:
        if not callable(enabled):
            raise TypeError("enabled must be callable")
        if not callable(open_garden):
            raise TypeError("open_garden must be callable")
        if can_present is not None and not callable(can_present):
            raise TypeError("can_present must be callable when provided")
        self.mw = mw
        self.storage = storage
        self.enabled = enabled
        self.open_garden = open_garden
        self.can_present = can_present
        # The normal integration passes ``AnkiGardenApp.open_dashboard`` as a
        # bound method. Resolve its engine without widening the public presenter
        # constructor, so the card can use canonical plant/item art resolvers.
        self.engine = getattr(getattr(open_garden, "__self__", None), "engine", None)
        self._pending_summary: SyncRewardSummary | None = None
        self._current_summary: SyncRewardSummary | None = None
        self._card: Any | None = None
        self._render_scheduled = False
        self._transitioning = False
        self._closing = False
        self._generation = 0
        self._last_render_error: Exception | None = None

    @property
    def visible(self) -> bool:
        card = self._card
        if card is None:
            return False
        resolver = getattr(card, "isVisible", None)
        if callable(resolver):
            try:
                return bool(resolver())
            except RuntimeError:
                return False
        return True

    @property
    def pending(self) -> SyncRewardSummary | None:
        return self._pending_summary

    @property
    def current(self) -> SyncRewardSummary | None:
        return self._current_summary

    @staticmethod
    def _source_ids(summary: SyncRewardSummary) -> frozenset[str]:
        values = summary.source_batch_ids or (summary.batch_id,)
        return frozenset(str(value) for value in values if str(value))

    @classmethod
    def _coalesce(
        cls,
        current: SyncRewardSummary | None,
        incoming: SyncRewardSummary,
    ) -> SyncRewardSummary:
        if current is None:
            return incoming
        current_ids = cls._source_ids(current)
        incoming_ids = cls._source_ids(incoming)
        # The engine normally passes its already-merged durable receipt. Treat
        # that cumulative model as authoritative instead of summing it twice.
        if current_ids and current_ids.issubset(incoming_ids):
            return incoming
        if incoming_ids and incoming_ids.issubset(current_ids):
            return current
        return current.merge(incoming)

    def _enabled_state(self) -> bool | None:
        try:
            return bool(self.enabled())
        except Exception:
            logger.debug(
                "Anki Garden: sync reward presentation setting unavailable",
                exc_info=True,
            )
            return None

    def enqueue(self, summary: SyncRewardSummary) -> SyncRewardSummary | None:
        """Queue or merge one durable receipt without ever stacking cards."""

        if not isinstance(summary, SyncRewardSummary):
            raise TypeError("summary must be a SyncRewardSummary")
        if not summary.meaningful:
            return None
        self._closing = False
        enabled = self._enabled_state()
        if enabled is False:
            self.dismiss("setting-disabled")
            self._guarded_clear_pending(summary, reason="setting disabled")
            self._pending_summary = None
            return None

        if self._card is not None:
            merged = self._coalesce(self._current_summary, summary)
            updater = getattr(self._card, "update_model", None)
            if not callable(updater):
                self._pending_summary = self._coalesce(
                    self._pending_summary,
                    summary,
                )
                return self._pending_summary
            try:
                updater(merged)
            except Exception as exc:
                self._last_render_error = exc
                self._pending_summary = self._coalesce(
                    self._pending_summary,
                    summary,
                )
                logger.debug(
                    "Anki Garden: open sync reward receipt could not update",
                    exc_info=True,
                )
                return self._pending_summary
            self._current_summary = merged
            pending = self._pending_summary
            if pending is not None and self._source_ids(pending).issubset(
                self._source_ids(summary)
            ):
                self._pending_summary = None
            # ``summary`` is the durable receipt supplied by the processor. The
            # visible model may additionally contain an older, already-acknowledged
            # batch, so guard against that supplied receipt rather than the UI sum.
            self._guarded_clear_pending(summary, reason="mounted update")
            return merged

        self._pending_summary = self._coalesce(self._pending_summary, summary)
        self._generation += 1
        self._schedule_present(0)
        return self._pending_summary

    def enqueue_or_merge(self, summary: SyncRewardSummary) -> SyncRewardSummary | None:
        """Readable alias for callers that describe the merge behavior explicitly."""

        return self.enqueue(summary)

    def restore_pending(self) -> SyncRewardSummary | None:
        """Load one persisted receipt after startup or profile activation."""

        raw = getattr(
            getattr(self.storage, "state", None),
            "pending_sync_reward_summary",
            None,
        )
        summary = SyncRewardSummary.from_dict(raw)
        if summary is None:
            return None
        return self.enqueue(summary)

    def retry(self) -> None:
        """Retry immediately after Anki reaches a stable non-review surface."""

        if self._closing:
            return
        self._render_scheduled = False
        self._present_pending(self._generation)

    def on_presentation_setting_changed(self) -> None:
        """Apply a saved setting change to queued or visible presentation."""

        enabled = self._enabled_state()
        if enabled is False:
            pending = self._pending_summary
            self.dismiss("setting-disabled")
            if pending is None:
                pending = SyncRewardSummary.from_dict(getattr(
                    getattr(self.storage, "state", None),
                    "pending_sync_reward_summary",
                    None,
                ))
            if pending is not None:
                self._guarded_clear_pending(pending, reason="setting disabled")
            self._pending_summary = None
            return
        if enabled is True:
            self.restore_pending()

    def on_state_will_change(
        self,
        new_state: str,
        old_state: str = "",
        *_args: Any,
    ) -> None:
        del old_state
        self._transitioning = True
        if str(new_state or "") == "review":
            self.dismiss("review")

    def on_state_change(
        self,
        new_state: str,
        old_state: str = "",
        *_args: Any,
    ) -> None:
        del old_state
        self._transitioning = False
        if str(new_state or "") == "review":
            self.dismiss("review")
            return
        self.retry()

    def dismiss(self, reason: str = "") -> None:
        """Close the mounted card; committed rewards remain untouched."""

        del reason
        self._generation += 1
        self._render_scheduled = False
        card = self._card
        self._card = None
        self._current_summary = None
        if card is not None:
            try:
                card.close()
            except (AttributeError, RuntimeError):
                pass

    def close_for_profile(self) -> None:
        """Release profile-owned Qt objects without clearing durable pending data."""

        self._closing = True
        self.dismiss("profile")
        self._pending_summary = None
        self._transitioning = False

    def _schedule_present(self, delay_ms: int) -> None:
        if self._render_scheduled or self._pending_summary is None or self._closing:
            return
        self._render_scheduled = True
        generation = self._generation
        if QTimer is None:
            # Source-only tests and export processes call ``retry()`` explicitly.
            self._render_scheduled = False
            return
        try:
            QTimer.singleShot(
                max(0, int(delay_ms)),
                lambda: self._present_pending(generation),
            )
        except Exception:
            self._render_scheduled = False
            logger.debug(
                "Anki Garden: sync reward presentation could not be scheduled",
                exc_info=True,
            )

    def _application_is_closing(self) -> bool:
        if self._closing:
            return True
        if QApplication is None:
            return False
        try:
            resolver = getattr(QApplication, "closingDown", None)
            return bool(resolver()) if callable(resolver) else False
        except Exception:
            return False

    def _modal_active(self) -> bool:
        if QApplication is None:
            return False
        try:
            return QApplication.activeModalWidget() is not None
        except Exception:
            return False

    def _resolve_parent(self) -> Any | None:
        for candidate in (
            getattr(self.mw, "web", None),
            (
                self.mw.centralWidget()
                if callable(getattr(self.mw, "centralWidget", None))
                else None
            ),
        ):
            if candidate is None:
                continue
            if callable(getattr(candidate, "width", None)) and callable(
                getattr(candidate, "height", None)
            ):
                return candidate
        return self.mw

    @staticmethod
    def _parent_is_stable(parent: Any) -> bool:
        if parent is None:
            return False
        try:
            if int(parent.width()) <= 0 or int(parent.height()) <= 0:
                return False
        except Exception:
            return False
        visible = getattr(parent, "isVisible", None)
        if callable(visible):
            try:
                if not bool(visible()):
                    return False
            except RuntimeError:
                return False
        return True

    def _host_can_present(self) -> bool:
        if self._application_is_closing() or self._transitioning:
            return False
        if str(getattr(self.mw, "state", "") or "") == "review":
            return False
        if self._modal_active():
            return False
        if callable(self.can_present):
            try:
                if not bool(self.can_present()):
                    return False
            except Exception:
                return False
        return True

    def _animations_enabled(self) -> bool:
        try:
            from .config import DEFAULT_CONFIG
            from .ui.accessibility import effective_motion_enabled

            config = getattr(self.storage, "config", None)
            value = getattr(config, "value", None)
            if not callable(value):
                return False
            return effective_motion_enabled(
                bool(value("enable_animations", DEFAULT_CONFIG["enable_animations"])),
                bool(value("reduced_motion", DEFAULT_CONFIG["reduced_motion"])),
            )
        except Exception:
            return False

    def _create_card(
        self,
        parent: Any,
        summary: SyncRewardSummary,
    ) -> SyncRewardSummaryCard:
        return SyncRewardSummaryCard(
            parent,
            summary,
            on_dismiss=self._on_card_dismissed,
            on_open_garden=self._on_open_garden,
            engine=self.engine,
            animations_enabled=self._animations_enabled(),
        )

    def _present_pending(self, expected_generation: int | None = None) -> None:
        if (
            expected_generation is not None
            and int(expected_generation) != self._generation
        ):
            return
        self._render_scheduled = False
        summary = self._pending_summary
        if summary is None:
            return
        if self._card is not None:
            # A prior in-place render failure deliberately retained this model.
            # Retry the same one-card update instead of opening another frame.
            self.enqueue(summary)
            return
        enabled = self._enabled_state()
        if enabled is False:
            self._guarded_clear_pending(summary, reason="setting disabled")
            if self._pending_summary is summary:
                self._pending_summary = None
            return
        if enabled is None or not self._host_can_present():
            self._schedule_present(self.RETRY_DELAY_MS)
            return
        parent = self._resolve_parent()
        if not self._parent_is_stable(parent):
            self._schedule_present(self.RETRY_DELAY_MS)
            return

        generation = self._generation
        try:
            card = self._create_card(parent, summary)
            card.show()
            visible = getattr(card, "isVisible", None)
            if callable(visible) and not bool(visible()):
                raise RuntimeError("sync reward card did not become visible")
            raise_card = getattr(card, "raise_", None)
            if callable(raise_card):
                raise_card()
        except Exception as exc:
            # Rewards and the pending receipt were already committed. Keep the
            # durable/in-memory model unchanged so a later stable state can retry.
            self._last_render_error = exc
            logger.debug(
                "Anki Garden: sync reward receipt could not be rendered",
                exc_info=True,
            )
            return

        if generation != self._generation or self._pending_summary is not summary:
            try:
                card.close()
            except Exception:
                pass
            return
        self._card = card
        self._current_summary = summary
        self._pending_summary = None
        self._last_render_error = None
        self._guarded_clear_pending(summary, reason="mounted")

    @classmethod
    def _same_persisted_receipt(
        cls,
        persisted: SyncRewardSummary,
        expected: SyncRewardSummary,
    ) -> bool:
        persisted_ids = cls._source_ids(persisted)
        expected_ids = cls._source_ids(expected)
        if persisted_ids and expected_ids:
            # Equality is stricter than a subset check by design: a strict
            # persisted superset is a newer merge and must remain pending. The
            # complete normalized payload check also protects a newer revision
            # that reused the same batch identities while adding display facts.
            return bool(
                persisted_ids == expected_ids
                and persisted.to_dict() == expected.to_dict()
            )
        return bool(
            persisted.batch_id == expected.batch_id
            and persisted.eligible_answer_count == expected.eligible_answer_count
        )

    def _guarded_clear_pending(
        self,
        expected: SyncRewardSummary,
        *,
        reason: str,
    ) -> bool:
        state = getattr(self.storage, "state", None)
        if state is None:
            return False
        raw = getattr(state, "pending_sync_reward_summary", None)
        if raw is None:
            return True
        persisted = SyncRewardSummary.from_dict(raw)
        if persisted is None or not self._same_persisted_receipt(persisted, expected):
            logger.debug(
                "Anki Garden: retained newer pending sync receipt during %s",
                reason,
            )
            return False
        state.pending_sync_reward_summary = None
        try:
            self.storage.save()
        except Exception:
            state.pending_sync_reward_summary = raw
            logger.debug(
                "Anki Garden: pending sync receipt acknowledgement could not save",
                exc_info=True,
            )
            return False
        return True

    def _on_card_dismissed(self) -> None:
        self._card = None
        self._current_summary = None
        if self._pending_summary is not None:
            self._schedule_present(0)

    def _on_open_garden(self) -> None:
        self._card = None
        self._current_summary = None
        try:
            self.open_garden()
        except Exception:
            logger.debug(
                "Anki Garden: Garden could not open from sync rewards",
                exc_info=True,
            )


__all__ = ["SyncRewardPresenter"]
