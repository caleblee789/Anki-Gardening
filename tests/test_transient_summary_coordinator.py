from __future__ import annotations
from ankigarden.ui.transient_summary_coordinator import (
    TransientSummaryCoordinator,
)


class _FocusTarget:
    def __init__(self) -> None:
        self.focus_calls = 0

    def isVisible(self) -> bool:
        return True

    def isEnabled(self) -> bool:
        return True

    def setFocus(self) -> None:
        self.focus_calls += 1


def test_summary_coordinator_replaces_surface_without_intermediate_focus_jump() -> None:
    focus = _FocusTarget()
    coordinator = TransientSummaryCoordinator(lambda: focus)
    dismissed: list[str] = []

    def dismiss_sync() -> None:
        dismissed.append("sync")
        coordinator.release("sync")

    def dismiss_session() -> None:
        dismissed.append("session")
        coordinator.release("session")

    coordinator.acquire("sync", dismiss_sync)
    coordinator.acquire("session", dismiss_session)

    assert dismissed == ["sync"]
    assert coordinator.active_kind == "session"
    assert focus.focus_calls == 0

    assert coordinator.dismiss("escape") is True
    assert dismissed == ["sync", "session"]
    assert coordinator.active_kind == ""
    assert focus.focus_calls == 1


def test_summary_coordinator_releases_only_the_owner() -> None:
    coordinator = TransientSummaryCoordinator()
    coordinator.acquire("sync", lambda: None)

    assert coordinator.release("session") is False
    assert coordinator.owns("sync") is True
    assert coordinator.release("sync", restore_focus=False) is True
    assert coordinator.active_kind == ""
