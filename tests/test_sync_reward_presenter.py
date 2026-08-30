from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from ankigarden.models.sync_reward import SyncRewardSummary
from ankigarden.sync_reward_presenter import SyncRewardPresenter


def _summary(batch: str, count: int = 4) -> SyncRewardSummary:
    return SyncRewardSummary(
        batch_id=batch,
        anki_days=("2026-08-29",),
        eligible_answer_count=count,
        growth_total_units=count * 100,
        source_batch_ids=(batch,),
    )


class _Parent:
    def width(self) -> int:
        return 900

    def height(self) -> int:
        return 700

    def isVisible(self) -> bool:
        return True


class _Card:
    def __init__(self, summary: SyncRewardSummary) -> None:
        self.summary = summary
        self.shown = False
        self.closed = False
        self.updates: list[SyncRewardSummary] = []

    def show(self) -> None:
        self.shown = True

    def isVisible(self) -> bool:
        return self.shown and not self.closed

    def raise_(self) -> None:
        return None

    def update_model(self, summary: SyncRewardSummary) -> None:
        self.summary = summary
        self.updates.append(summary)

    def close(self) -> None:
        self.closed = True


class _Storage:
    def __init__(self) -> None:
        self.state = SimpleNamespace(pending_sync_reward_summary=None)
        self.saves = 0

    def save(self) -> None:
        self.saves += 1


class _Presenter(SyncRewardPresenter):
    def __init__(self, *args, **kwargs) -> None:
        self.created: list[_Card] = []
        self.scheduled: list[int] = []
        super().__init__(*args, **kwargs)

    def _resolve_parent(self):
        return _Parent()

    def _schedule_present(self, delay_ms: int) -> None:
        self.scheduled.append(delay_ms)

    def _create_card(self, parent, summary):
        del parent
        card = _Card(summary)
        self.created.append(card)
        return card

    def _install_escape_shortcut(self) -> None:
        # Source-only presenter tests have no Qt runtime. Tests that exercise
        # shortcut failure override this method explicitly.
        return None


def _presenter(storage: _Storage, *, enabled=True, can_present=None):
    opened: list[str] = []
    mw = SimpleNamespace(state="deckBrowser")
    presenter = _Presenter(
        mw,
        storage,
        enabled=lambda: enabled,
        open_garden=lambda: opened.append("garden"),
        can_present=can_present,
    )
    return presenter, mw, opened


def test_successful_mount_acknowledges_matching_durable_receipt() -> None:
    storage = _Storage()
    summary = _summary("a")
    storage.state.pending_sync_reward_summary = summary.to_dict()
    presenter, _mw, _opened = _presenter(storage)

    assert presenter.enqueue(summary) == summary
    assert presenter.visible is False
    presenter.retry()

    assert presenter.visible is True
    assert len(presenter.created) == 1
    assert storage.state.pending_sync_reward_summary is None
    assert storage.saves == 1


def test_reviewer_and_other_surface_gate_defer_without_losing_pending() -> None:
    storage = _Storage()
    summary = _summary("a")
    storage.state.pending_sync_reward_summary = summary.to_dict()
    gate = {"open": False}
    presenter, mw, _opened = _presenter(
        storage,
        can_present=lambda: gate["open"],
    )
    mw.state = "review"
    presenter.enqueue(summary)
    presenter.retry()

    assert presenter.visible is False
    assert presenter.pending == summary
    assert storage.state.pending_sync_reward_summary is not None

    mw.state = "deckBrowser"
    gate["open"] = True
    presenter.retry()
    assert presenter.visible is True
    assert storage.state.pending_sync_reward_summary is None


def test_visible_card_merges_new_batch_without_stacking() -> None:
    storage = _Storage()
    first = _summary("a", 4)
    storage.state.pending_sync_reward_summary = first.to_dict()
    presenter, _mw, _opened = _presenter(storage)
    presenter.enqueue(first)
    presenter.retry()
    card = presenter.created[0]

    second = _summary("b", 6)
    storage.state.pending_sync_reward_summary = second.to_dict()
    merged = presenter.enqueue(second)

    assert len(presenter.created) == 1
    assert card.updates == [merged]
    assert merged is not None
    assert merged.eligible_answer_count == 10
    assert set(merged.source_batch_ids) == {"a", "b"}
    assert storage.state.pending_sync_reward_summary is None
    assert storage.saves == 2


def test_guard_never_clears_a_newer_merged_receipt() -> None:
    storage = _Storage()
    first = _summary("a", 4)
    newer = first.merge(_summary("b", 6))
    storage.state.pending_sync_reward_summary = newer.to_dict()
    presenter, _mw, _opened = _presenter(storage)

    presenter.enqueue(first)
    presenter.retry()

    assert presenter.visible is True
    assert storage.state.pending_sync_reward_summary == newer.to_dict()
    assert storage.saves == 0


def test_guard_never_clears_newer_payload_reusing_same_batch_identity() -> None:
    storage = _Storage()
    first = _summary("a", 4)
    newer = replace(
        first,
        eligible_answer_count=5,
        growth_total_units=500,
        additional_answer_count=1,
    )
    storage.state.pending_sync_reward_summary = newer.to_dict()
    presenter, _mw, _opened = _presenter(storage)

    presenter.enqueue(first)
    presenter.retry()

    assert storage.state.pending_sync_reward_summary == newer.to_dict()
    assert storage.saves == 0


def test_render_failure_keeps_in_memory_and_durable_pending() -> None:
    class _FailingPresenter(_Presenter):
        def _create_card(self, parent, summary):
            del parent, summary
            raise RuntimeError("renderer unavailable")

    storage = _Storage()
    summary = _summary("a")
    storage.state.pending_sync_reward_summary = summary.to_dict()
    presenter = _FailingPresenter(
        SimpleNamespace(state="deckBrowser"),
        storage,
        enabled=lambda: True,
        open_garden=lambda: None,
    )

    presenter.enqueue(summary)
    presenter.retry()

    assert presenter.visible is False
    assert presenter.pending == summary
    assert storage.state.pending_sync_reward_summary == summary.to_dict()
    assert storage.saves == 0


def test_failed_open_card_update_retries_in_place_without_stacking() -> None:
    class _FlakyCard(_Card):
        def __init__(self, summary: SyncRewardSummary) -> None:
            super().__init__(summary)
            self.fail_next_update = True

        def update_model(self, summary: SyncRewardSummary) -> None:
            if self.fail_next_update:
                self.fail_next_update = False
                raise RuntimeError("transient update failure")
            super().update_model(summary)

    class _FlakyPresenter(_Presenter):
        def _create_card(self, parent, summary):
            del parent
            card = _FlakyCard(summary)
            self.created.append(card)
            return card

    storage = _Storage()
    first = _summary("a", 4)
    storage.state.pending_sync_reward_summary = first.to_dict()
    presenter = _FlakyPresenter(
        SimpleNamespace(state="deckBrowser"),
        storage,
        enabled=lambda: True,
        open_garden=lambda: None,
    )
    presenter.enqueue(first)
    presenter.retry()

    second = _summary("b", 6)
    storage.state.pending_sync_reward_summary = second.to_dict()
    presenter.enqueue(second)
    assert presenter.pending == second
    assert storage.state.pending_sync_reward_summary == second.to_dict()

    presenter.retry()

    assert len(presenter.created) == 1
    assert presenter.pending is None
    assert presenter.current is not None
    assert presenter.current.eligible_answer_count == 10
    assert storage.state.pending_sync_reward_summary is None
    assert storage.saves == 2


def test_disabled_setting_suppresses_receipt_but_not_rewards() -> None:
    storage = _Storage()
    summary = _summary("a")
    storage.state.pending_sync_reward_summary = summary.to_dict()
    presenter, _mw, _opened = _presenter(storage, enabled=False)

    assert presenter.enqueue(summary) is None
    assert presenter.visible is False
    assert presenter.pending is None
    assert storage.state.pending_sync_reward_summary is None
    assert storage.saves == 1


def test_profile_close_releases_card_but_preserves_unmounted_durable_receipt() -> None:
    storage = _Storage()
    summary = _summary("a")
    storage.state.pending_sync_reward_summary = summary.to_dict()
    presenter, mw, _opened = _presenter(storage)
    mw.state = "review"
    presenter.enqueue(summary)

    presenter.close_for_profile()

    assert presenter.visible is False
    assert presenter.pending is None
    assert storage.state.pending_sync_reward_summary == summary.to_dict()
    assert storage.saves == 0


def test_escape_is_modal_guarded_and_routes_only_the_owned_sync_summary(
    monkeypatch,
) -> None:
    class _Coordinator:
        def __init__(self) -> None:
            self.active_kind = "sync"
            self.dismissed: list[str] = []

        def owns(self, kind: str) -> bool:
            return self.active_kind == kind

        def dismiss(self, reason: str) -> bool:
            self.dismissed.append(reason)
            return True

    coordinator = _Coordinator()
    presenter = _Presenter(
        SimpleNamespace(state="deckBrowser"),
        _Storage(),
        enabled=lambda: True,
        open_garden=lambda: None,
        summary_coordinator=coordinator,
    )

    monkeypatch.setattr(presenter, "_modal_active", lambda: True)
    presenter._dismiss_on_escape()
    assert coordinator.dismissed == []

    monkeypatch.setattr(presenter, "_modal_active", lambda: False)
    coordinator.active_kind = "session"
    presenter._dismiss_on_escape()
    assert coordinator.dismissed == []

    coordinator.active_kind = "sync"
    presenter._dismiss_on_escape()
    assert coordinator.dismissed == ["escape"]
