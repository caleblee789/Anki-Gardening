"""Shared arbitration for nonmodal Session and Sync summary surfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def dispose_unmounted_summary_card(card: Any | None) -> None:
    """Remove a locally-created card that never became its owner's card.

    Session Summary's normal ``close()`` path notifies its owner.  A presenter
    failure can happen before that owner stores the local card, so detach the
    callbacks first: cleanup then stays local, happens before coordinator
    ownership is released, and cannot recurse into a second close.
    """

    if card is None:
        return
    for callback_name in ("_on_dismiss", "_on_open_garden"):
        try:
            if hasattr(card, callback_name):
                setattr(card, callback_name, None)
        except Exception:
            pass
    try:
        close = getattr(card, "close", None)
        if callable(close):
            close()
    except Exception:
        pass
    still_visible = True
    try:
        visible = getattr(card, "isVisible", None)
        if callable(visible):
            still_visible = bool(visible())
    except Exception:
        pass
    if still_visible:
        try:
            hide = getattr(card, "hide", None)
            if callable(hide):
                hide()
        except Exception:
            pass
    try:
        delete_later = getattr(card, "deleteLater", None)
        if callable(delete_later):
            delete_later()
    except Exception:
        pass


class TransientSummaryCoordinator:
    """Give one transient summary exclusive ownership of the host viewport.

    The summaries retain their own persistence and rendering lifecycles.  This
    coordinator owns only the cross-surface concerns: mutual exclusion, one
    Escape target, and returning focus after a nonmodal card is dismissed.
    """

    def __init__(
        self,
        focus_getter: Callable[[], Any | None] | None = None,
    ) -> None:
        self._focus_getter = focus_getter
        self._active_kind = ""
        self._dismiss_active: Callable[[], None] | None = None
        self._return_focus: Any | None = None

    @property
    def active_kind(self) -> str:
        return self._active_kind

    def owns(self, kind: str) -> bool:
        return bool(self._active_kind == str(kind or ""))

    def _capture_focus(self) -> None:
        if self._return_focus is not None or not callable(self._focus_getter):
            return
        try:
            self._return_focus = self._focus_getter()
        except Exception:
            self._return_focus = None

    def acquire(self, kind: str, dismiss: Callable[[], None]) -> None:
        normalized = str(kind or "").strip()
        if not normalized:
            raise ValueError("summary kind must not be empty")
        if not callable(dismiss):
            raise TypeError("dismiss must be callable")
        self._capture_focus()
        if self._active_kind and self._active_kind != normalized:
            previous = self._dismiss_active
            # Clear ownership first so the previous surface can release itself
            # without restoring focus between the two summary presentations.
            self._active_kind = ""
            self._dismiss_active = None
            if callable(previous):
                previous()
        self._active_kind = normalized
        self._dismiss_active = dismiss

    def dismiss(self, reason: str = "") -> bool:
        del reason
        callback = self._dismiss_active
        if not self._active_kind or not callable(callback):
            return False
        callback()
        return True

    def release(self, kind: str, *, restore_focus: bool = True) -> bool:
        if not self.owns(kind):
            return False
        self._active_kind = ""
        self._dismiss_active = None
        target = self._return_focus
        self._return_focus = None
        if not restore_focus or target is None:
            return True
        try:
            visible = getattr(target, "isVisible", None)
            enabled = getattr(target, "isEnabled", None)
            if callable(visible) and not bool(visible()):
                return True
            if callable(enabled) and not bool(enabled()):
                return True
            setter = getattr(target, "setFocus", None)
            if callable(setter):
                setter()
        except (AttributeError, RuntimeError):
            pass
        return True


__all__ = ["TransientSummaryCoordinator", "dispose_unmounted_summary_card"]
