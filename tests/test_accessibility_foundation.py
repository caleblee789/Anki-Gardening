from __future__ import annotations

from types import SimpleNamespace

import pytest

import ankigarden.ui.accessibility as accessibility
from ankigarden.ui.accessibility import (
    AccessibilityAnnouncer,
    AnnouncementPriority,
    OperationGenerationGuard,
    effective_motion_enabled,
    effective_motion_policy,
    post_macos_accessibility_announcement,
    post_native_accessibility_announcement,
    post_windows_live_region_announcement,
    read_macos_reduced_motion,
    read_system_reduced_motion,
    read_windows_reduced_motion,
)


class AccessibleTarget:
    def __init__(self) -> None:
        self.description = ""

    def setAccessibleDescription(self, message: str) -> None:
        self.description = message


class FakeAnnouncementEvent:
    def __init__(self, source: object, message: str) -> None:
        self.source = source
        self.message = message
        self.politeness = None

    def setPoliteness(self, politeness: object) -> None:
        self.politeness = politeness


class FakeAccessibleEvent:
    def __init__(self, source: object, event_type: object) -> None:
        self.source = source
        self.event_type = event_type


def _qt_api(*, announcement: bool = True, update_raises: bool = False) -> object:
    events: list[object] = []

    class AnnouncementPoliteness:
        Polite = "qt-polite"
        Assertive = "qt-assertive"

    class Event:
        Alert = "qt-alert"

    class QAccessible:
        @staticmethod
        def updateAccessibility(event: object) -> None:
            if update_raises:
                raise RuntimeError("accessibility backend unavailable")
            events.append(event)

    QAccessible.AnnouncementPoliteness = AnnouncementPoliteness
    QAccessible.Event = Event
    return SimpleNamespace(
        QAccessible=QAccessible,
        QAccessibleAnnouncementEvent=FakeAnnouncementEvent if announcement else None,
        QAccessibleEvent=FakeAccessibleEvent,
        events=events,
    )


def test_accessibility_module_imports_without_aqt_runtime() -> None:
    # Importing the module above succeeds in the repository venv, which has no aqt.
    assert AccessibilityAnnouncer.__module__ == "ankigarden.ui.accessibility"


@pytest.mark.parametrize(
    ("priority", "qt_priority"),
    [
        (AnnouncementPriority.POLITE, "qt-polite"),
        (AnnouncementPriority.ASSERTIVE, "qt-assertive"),
    ],
)
def test_announcer_uses_qt_announcement_event_with_requested_priority(
    priority: AnnouncementPriority,
    qt_priority: str,
) -> None:
    api = _qt_api()
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(target, qt_loader=lambda: api)

    assert announcer.announce("Purchase complete", priority=priority)
    assert len(api.events) == 1
    event = api.events[0]
    assert isinstance(event, FakeAnnouncementEvent)
    assert event.source is target
    assert event.message == "Purchase complete"
    assert event.politeness == qt_priority
    assert announcer.last_delivery == "announcement"


def test_announcer_keeps_qt_ahead_of_the_native_bridge() -> None:
    api = _qt_api()
    native_calls: list[object] = []
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(
        target,
        qt_loader=lambda: api,
        native_bridge=lambda *_args: native_calls.append(_args),
    )

    assert announcer.announce("Purchase complete")
    assert len(api.events) == 1
    assert native_calls == []


def test_announcer_uses_native_bridge_before_description_fallback() -> None:
    calls: list[tuple[object, str, AnnouncementPriority]] = []
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(
        target,
        qt_loader=lambda: None,
        native_bridge=lambda source, message, priority: calls.append(
            (source, message, priority)
        )
        or True,
    )

    assert announcer.announce("Equipment changed", priority="assertive")
    assert calls == [(target, "Equipment changed", AnnouncementPriority.ASSERTIVE)]
    assert target.description == ""
    assert announcer.last_delivery == "native"


def test_announcer_native_failure_is_safe_and_preserves_description_fallback() -> None:
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(
        target,
        qt_loader=lambda: None,
        native_bridge=lambda *_args: (_ for _ in ()).throw(
            RuntimeError("native backend unavailable")
        ),
    )

    assert announcer.announce("Garden saved")
    assert target.description == "Garden saved"
    assert announcer.last_delivery == "description"


def test_announcer_uses_alert_event_when_qt_lacks_announcement_event() -> None:
    api = _qt_api(announcement=False)
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(target, qt_loader=lambda: api)

    assert announcer.announce("Growth allocation failed", priority="assertive")
    assert target.description == "Growth allocation failed"
    assert len(api.events) == 1
    event = api.events[0]
    assert isinstance(event, FakeAccessibleEvent)
    assert event.event_type == "qt-alert"
    assert announcer.last_delivery == "alert"


def test_announcer_falls_back_to_accessible_description_when_qt_is_unavailable() -> None:
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(target, qt_loader=lambda: None)

    assert announcer.announce("Garden saved")
    assert target.description == "Garden saved"
    assert announcer.last_delivery == "description"


def test_announcer_never_leaks_qt_delivery_failures() -> None:
    api = _qt_api(update_raises=True)
    target = AccessibleTarget()
    announcer = AccessibilityAnnouncer(target, qt_loader=lambda: api)

    assert announcer.announce("Purchase could not be completed", priority="assertive")
    assert target.description == "Purchase could not be completed"
    assert announcer.last_delivery == "description"


def test_announcer_uses_injected_fallback_and_never_raises() -> None:
    calls: list[tuple[object, str, AnnouncementPriority]] = []
    target = object()
    announcer = AccessibilityAnnouncer(
        target,
        qt_loader=lambda: (_ for _ in ()).throw(RuntimeError("no Qt")),
        fallback=lambda source, message, priority: calls.append(
            (source, message, priority)
        ),
    )

    assert announcer.announce("Equipment changed", priority="assertive")
    assert calls == [(target, "Equipment changed", AnnouncementPriority.ASSERTIVE)]
    assert announcer.last_delivery == "fallback"


def test_announcer_rejects_empty_and_stale_messages() -> None:
    api = _qt_api()
    announcer = AccessibilityAnnouncer(object(), qt_loader=lambda: api)
    stale = announcer.begin_operation()
    current = announcer.begin_operation()

    assert not announcer.announce("", generation=current)
    assert announcer.last_delivery == "none"
    assert not announcer.announce("Old result", generation=stale)
    assert announcer.last_delivery == "stale"
    assert announcer.announce("Current result", generation=current)
    assert [event.message for event in api.events] == ["Current result"]


def test_announcer_does_not_dispatch_stale_message_to_native_bridge() -> None:
    native_calls: list[object] = []
    announcer = AccessibilityAnnouncer(
        object(),
        qt_loader=lambda: None,
        native_bridge=lambda *_args: native_calls.append(_args) or True,
    )
    stale = announcer.begin_operation()
    announcer.begin_operation()

    assert not announcer.announce("Old purchase", generation=stale)
    assert native_calls == []
    assert announcer.last_delivery == "stale"


@pytest.mark.parametrize(
    ("priority", "expected_native_priority"),
    [
        (AnnouncementPriority.POLITE, 10),
        (AnnouncementPriority.ASSERTIVE, 90),
        ("unknown", 10),
    ],
)
def test_macos_bridge_posts_announcement_with_native_priority(
    priority: object,
    expected_native_priority: int,
) -> None:
    calls: list[tuple[int, str, int]] = []
    api = SimpleNamespace(
        post=lambda handle, message, native_priority: calls.append(
            (handle, message, native_priority)
        )
        or True
    )

    assert post_macos_accessibility_announcement(
        object(),
        "  Purchase complete  ",
        priority,
        system_name="Darwin",
        api_loader=lambda: api,
        handle_resolver=lambda _target: 0x1234,
    )
    assert calls == [(0x1234, "Purchase complete", expected_native_priority)]


def test_macos_bridge_has_safe_platform_and_native_api_fallbacks() -> None:
    loader_calls: list[str] = []

    assert not post_macos_accessibility_announcement(
        object(),
        "Saved",
        system_name="Windows",
        api_loader=lambda: loader_calls.append("called"),
        handle_resolver=lambda _target: 1,
    )
    assert loader_calls == []
    assert not post_macos_accessibility_announcement(
        object(),
        "Saved",
        system_name="Darwin",
        api_loader=lambda: (_ for _ in ()).throw(OSError("AppKit unavailable")),
        handle_resolver=lambda _target: 1,
    )
    assert not post_macos_accessibility_announcement(
        object(),
        "Saved",
        system_name="Darwin",
        api_loader=lambda: SimpleNamespace(
            post=lambda *_args: (_ for _ in ()).throw(RuntimeError("post failed"))
        ),
        handle_resolver=lambda _target: 1,
    )
    assert not post_macos_accessibility_announcement(
        object(),
        "Saved",
        system_name="Darwin",
        api_loader=lambda: SimpleNamespace(post=lambda *_args: True),
        handle_resolver=lambda _target: None,
    )


@pytest.mark.parametrize(
    "priority",
    [AnnouncementPriority.POLITE, AnnouncementPriority.ASSERTIVE],
)
def test_windows_bridge_updates_description_before_live_region_event(
    priority: AnnouncementPriority,
) -> None:
    target = AccessibleTarget()
    order: list[object] = []

    def set_description(source: AccessibleTarget, message: str) -> bool:
        source.setAccessibleDescription(message)
        order.append(("description", message))
        return True

    def notify(event: int, hwnd: int, object_id: int, child_id: int) -> bool:
        assert target.description == "Purchase complete"
        order.append(("notify", event, hwnd, object_id, child_id))
        return True

    assert post_windows_live_region_announcement(
        target,
        "Purchase complete",
        priority,
        system_name="Windows",
        api_loader=lambda: SimpleNamespace(notify=notify),
        hwnd_resolver=lambda _target: 0x5678,
        description_setter=set_description,
    )
    assert order == [
        ("description", "Purchase complete"),
        ("notify", 0x8019, 0x5678, -4, 0),
    ]


def test_windows_bridge_has_safe_description_and_event_fallbacks() -> None:
    notify_calls: list[object] = []
    api = SimpleNamespace(notify=lambda *_args: notify_calls.append(_args) or True)

    assert not post_windows_live_region_announcement(
        object(),
        "Saved",
        system_name="Darwin",
        api_loader=lambda: api,
        hwnd_resolver=lambda _target: 1,
        description_setter=lambda *_args: True,
    )
    assert not post_windows_live_region_announcement(
        object(),
        "Saved",
        system_name="Windows",
        api_loader=lambda: api,
        hwnd_resolver=lambda _target: 1,
        description_setter=lambda *_args: False,
    )
    assert notify_calls == []
    assert not post_windows_live_region_announcement(
        object(),
        "Saved",
        system_name="Windows",
        api_loader=lambda: SimpleNamespace(
            notify=lambda *_args: (_ for _ in ()).throw(RuntimeError("notify failed"))
        ),
        hwnd_resolver=lambda _target: 1,
        description_setter=lambda *_args: True,
    )
    assert not post_windows_live_region_announcement(
        object(),
        "Saved",
        system_name="Windows",
        api_loader=lambda: api,
        hwnd_resolver=lambda _target: 0,
        description_setter=lambda *_args: True,
    )
    assert notify_calls == []


def test_native_bridge_dispatches_by_platform_and_never_raises() -> None:
    target = object()
    calls: list[tuple[str, object, str, AnnouncementPriority]] = []

    def macos_poster(
        source: object,
        message: str,
        priority: AnnouncementPriority,
    ) -> bool:
        calls.append(("macOS", source, message, priority))
        return True

    def windows_poster(
        source: object,
        message: str,
        priority: AnnouncementPriority,
    ) -> bool:
        calls.append(("Windows", source, message, priority))
        return True

    assert post_native_accessibility_announcement(
        target,
        "Saved",
        "assertive",
        system_name="Darwin",
        macos_poster=macos_poster,
        windows_poster=windows_poster,
    )
    assert post_native_accessibility_announcement(
        target,
        "Moved",
        system_name="Windows",
        macos_poster=macos_poster,
        windows_poster=windows_poster,
    )
    assert not post_native_accessibility_announcement(
        target,
        "Ignored",
        system_name="Linux",
        macos_poster=macos_poster,
        windows_poster=windows_poster,
    )
    assert calls == [
        ("macOS", target, "Saved", AnnouncementPriority.ASSERTIVE),
        ("Windows", target, "Moved", AnnouncementPriority.POLITE),
    ]
    assert not post_native_accessibility_announcement(
        target,
        "Failure",
        system_name="Darwin",
        macos_poster=lambda *_args: (_ for _ in ()).throw(RuntimeError("failed")),
    )


def test_native_handle_uses_effective_ancestor_without_promoting_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class QWidget:
        def effectiveWinId(self) -> int:
            calls.append("effective")
            return 0x1234

        def winId(self) -> int:
            calls.append("child-win-id")
            return 0x5678

        def window(self) -> object:
            calls.append("window")
            return self

    monkeypatch.setitem(
        __import__("sys").modules,
        "aqt",
        SimpleNamespace(qt=SimpleNamespace(QWidget=QWidget)),
    )
    target = QWidget()

    assert accessibility._native_widget_handle(target) == 0x1234
    assert calls == ["effective"]


def test_operation_generation_guard_runs_only_current_callbacks() -> None:
    guard = OperationGenerationGuard()
    stale = guard.begin()
    current = guard.begin()
    calls: list[str] = []

    assert not guard.run_if_current(stale, calls.append, "stale")
    assert guard.run_if_current(current, calls.append, "current")
    assert calls == ["current"]
    guard.invalidate()
    assert not guard.is_current(current)
    assert not guard.is_current(True)


@pytest.mark.parametrize(
    ("enabled", "addon_reduce", "os_reduce", "expected"),
    [
        (True, False, False, True),
        (True, False, None, True),
        (False, False, False, False),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
    ],
)
def test_effective_motion_policy_combines_all_three_authorities(
    enabled: bool,
    addon_reduce: bool,
    os_reduce: object,
    expected: bool,
) -> None:
    policy = effective_motion_policy(
        enabled,
        addon_reduce,
        os_reader=lambda: os_reduce,
    )

    assert policy.animations_enabled is expected
    assert policy.reduced_motion is (not expected)
    assert policy.os_preference_known is (os_reduce is not None)
    assert effective_motion_enabled(
        enabled,
        addon_reduce,
        os_reader=lambda: os_reduce,
    ) is expected


def test_effective_motion_policy_treats_reader_failure_as_unknown() -> None:
    policy = effective_motion_policy(
        True,
        False,
        os_reader=lambda: (_ for _ in ()).throw(OSError("unavailable")),
    )

    assert policy.os_reduced_motion is None
    assert policy.animations_enabled


@pytest.mark.parametrize(
    ("output", "expected"),
    [("1\n", True), ("true\n", True), ("0\n", False), ("false\n", False)],
)
def test_macos_reader_parses_defaults_output(output: str, expected: bool) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=output)

    assert read_macos_reduced_motion(system_name="Darwin", runner=runner) is expected
    assert calls[0][0] == [
        "defaults",
        "read",
        "com.apple.universalaccess",
        "reduceMotion",
    ]
    assert calls[0][1]["timeout"] == 0.5


def test_macos_reader_has_safe_platform_command_and_parse_fallbacks() -> None:
    called = False

    def runner(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise OSError("missing defaults")

    assert read_macos_reduced_motion(system_name="Windows", runner=runner) is None
    assert not called
    assert read_macos_reduced_motion(system_name="Darwin", runner=runner) is None
    assert read_macos_reduced_motion(
        system_name="Darwin",
        runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="maybe"),
    ) is None


@pytest.mark.parametrize(
    ("animations_enabled", "expected_reduce"),
    [(True, False), (False, True), (None, None)],
)
def test_windows_reader_inverts_client_area_animation_preference(
    animations_enabled: object,
    expected_reduce: object,
) -> None:
    assert read_windows_reduced_motion(
        system_name="Windows",
        animation_reader=lambda: animations_enabled,
    ) is expected_reduce


def test_windows_reader_has_safe_platform_and_api_fallbacks() -> None:
    called = False

    def reader() -> bool:
        nonlocal called
        called = True
        raise OSError("user32 unavailable")

    assert read_windows_reduced_motion(
        system_name="Darwin",
        animation_reader=reader,
    ) is None
    assert not called
    assert read_windows_reduced_motion(
        system_name="Windows",
        animation_reader=reader,
    ) is None


def test_system_reader_routes_by_platform_and_normalizes_results() -> None:
    assert read_system_reduced_motion(
        system_name="Darwin",
        macos_reader=lambda: True,
    ) is True
    assert read_system_reduced_motion(
        system_name="Windows",
        windows_reader=lambda: False,
    ) is False
    assert read_system_reduced_motion(
        system_name="Linux",
        macos_reader=lambda: True,
        windows_reader=lambda: True,
    ) is None
    assert read_system_reduced_motion(
        system_name="Darwin",
        macos_reader=lambda: "yes",
    ) is None
