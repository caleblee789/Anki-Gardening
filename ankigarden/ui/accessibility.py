from __future__ import annotations

import platform
import threading
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Callable, Optional


class AnnouncementPriority(str, Enum):
    """Screen-reader announcement priority.

    Assertive announcements interrupt speech and should be reserved for errors
    or another result that requires the user's immediate attention.
    """

    POLITE = "polite"
    ASSERTIVE = "assertive"


# Native accessibility constants are intentionally kept here instead of
# importing platform SDK wrappers. Anki bundles neither PyObjC nor pywin32.
_NS_ACCESSIBILITY_PRIORITY_LOW = 10
_NS_ACCESSIBILITY_PRIORITY_HIGH = 90
_EVENT_OBJECT_LIVEREGIONCHANGED = 0x8019
_OBJID_CLIENT = -4
_CHILDID_SELF = 0


class OperationGenerationGuard:
    """Reject callbacks that belong to an operation superseded by a newer one."""

    def __init__(self) -> None:
        self._generation = 0
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        with self._lock:
            return self._generation

    def begin(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def invalidate(self) -> int:
        """Invalidate every outstanding token and return the new generation."""

        return self.begin()

    def is_current(self, generation: int) -> bool:
        if isinstance(generation, bool) or not isinstance(generation, int):
            return False
        with self._lock:
            return generation > 0 and generation == self._generation

    def run_if_current(
        self,
        generation: int,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        if not self.is_current(generation):
            return False
        callback(*args, **kwargs)
        return True


@dataclass(frozen=True)
class EffectiveMotionPolicy:
    """Resolved animation policy with each authority retained for diagnostics."""

    enable_animations: bool
    addon_reduced_motion: bool
    os_reduced_motion: Optional[bool]

    @property
    def animations_enabled(self) -> bool:
        return (
            self.enable_animations
            and not self.addon_reduced_motion
            and self.os_reduced_motion is not True
        )

    @property
    def reduced_motion(self) -> bool:
        return not self.animations_enabled

    @property
    def os_preference_known(self) -> bool:
        return self.os_reduced_motion is not None


def _optional_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _parse_boolean_output(value: Any) -> Optional[bool]:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="strict")
        except Exception:
            return None
    token = str(value or "").strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return None


@lru_cache(maxsize=1)
def _macos_motion_reader() -> Callable[[], bool]:
    """Bind AppKit once; read the live setting on every policy request."""

    import ctypes

    appkit = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    # Separate signatures avoid changing the shared objc_msgSend binding's ABI.
    object_message = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )(("objc_msgSend", objc))
    bool_message = ctypes.CFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )(("objc_msgSend", objc))
    responds = ctypes.CFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )(("objc_msgSend", objc))
    workspace_class = objc.objc_getClass(b"NSWorkspace")
    workspace = object_message(
        workspace_class, objc.sel_registerName(b"sharedWorkspace")
    ) if workspace_class else None
    selector = objc.sel_registerName(b"accessibilityDisplayShouldReduceMotion")
    if not workspace or not responds(
        workspace, objc.sel_registerName(b"respondsToSelector:"), selector
    ):
        raise RuntimeError("macOS motion preference is unavailable")

    def read() -> bool:
        # Keep the framework and runtime bindings alive with the reader.
        _ = appkit, objc
        return bool(bool_message(workspace, selector))

    return read


def read_macos_reduced_motion(
    *,
    system_name: Optional[str] = None,
    runner: Optional[Callable[..., Any]] = None,
) -> Optional[bool]:
    """Read the macOS Reduce Motion preference, or ``None`` when unavailable.

    AppKit avoids spawning a process on every card and observes live preference
    changes. An explicitly supplied command runner remains available for older
    integrations. ``None`` means an unknown OS preference.
    """

    if (system_name or platform.system()) != "Darwin":
        return None
    if runner is None:
        try:
            return _optional_bool(_macos_motion_reader()())
        except Exception:
            return None
    command_runner = runner
    try:
        result = command_runner(
            ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        )
    except Exception:
        return None
    if getattr(result, "returncode", None) != 0:
        return None
    return _parse_boolean_output(getattr(result, "stdout", ""))


def _windows_client_area_animations_enabled() -> Optional[bool]:
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        system_parameters_info = user32.SystemParametersInfoW
        system_parameters_info.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        system_parameters_info.restype = ctypes.c_int
        enabled = ctypes.c_int()
        succeeded = system_parameters_info(
            0x1042,  # SPI_GETCLIENTAREAANIMATION
            0,
            ctypes.byref(enabled),
            0,
        )
        if not succeeded:
            return None
        return bool(enabled.value)
    except Exception:
        return None


def read_windows_reduced_motion(
    *,
    system_name: Optional[str] = None,
    animation_reader: Optional[Callable[[], Optional[bool]]] = None,
) -> Optional[bool]:
    """Read Windows client-area animation preference without third parties."""

    if (system_name or platform.system()) != "Windows":
        return None
    reader = animation_reader or _windows_client_area_animations_enabled
    try:
        animations_enabled = _optional_bool(reader())
    except Exception:
        return None
    if animations_enabled is None:
        return None
    return not animations_enabled


def read_system_reduced_motion(
    *,
    system_name: Optional[str] = None,
    macos_reader: Optional[Callable[[], Optional[bool]]] = None,
    windows_reader: Optional[Callable[[], Optional[bool]]] = None,
) -> Optional[bool]:
    """Return the native reduced-motion preference when it can be read safely."""

    name = system_name or platform.system()
    if name == "Darwin":
        reader = macos_reader or (
            lambda: read_macos_reduced_motion(system_name="Darwin")
        )
    elif name == "Windows":
        reader = windows_reader or (
            lambda: read_windows_reduced_motion(system_name="Windows")
        )
    else:
        return None
    try:
        return _optional_bool(reader())
    except Exception:
        return None


def effective_motion_policy(
    enable_animations: bool,
    reduced_motion: bool,
    *,
    os_reader: Optional[Callable[[], Optional[bool]]] = None,
) -> EffectiveMotionPolicy:
    """Combine app animation settings with the operating-system preference."""

    reader = os_reader or read_system_reduced_motion
    try:
        os_reduced_motion = _optional_bool(reader())
    except Exception:
        os_reduced_motion = None
    return EffectiveMotionPolicy(
        enable_animations=bool(enable_animations),
        addon_reduced_motion=bool(reduced_motion),
        os_reduced_motion=os_reduced_motion,
    )


def effective_motion_enabled(
    enable_animations: bool,
    reduced_motion: bool,
    *,
    os_reader: Optional[Callable[[], Optional[bool]]] = None,
) -> bool:
    return effective_motion_policy(
        enable_animations,
        reduced_motion,
        os_reader=os_reader,
    ).animations_enabled


def _load_qt_accessibility_api() -> Optional[Any]:
    """Load Qt accessibility types only when Anki's Qt shim is available."""

    try:
        from aqt import qt
    except Exception:
        return None
    accessible = getattr(qt, "QAccessible", None)
    if accessible is None:
        return None
    return SimpleNamespace(
        QAccessible=accessible,
        QAccessibleAnnouncementEvent=getattr(
            qt,
            "QAccessibleAnnouncementEvent",
            None,
        ),
        QAccessibleEvent=getattr(qt, "QAccessibleEvent", None),
    )


def _qt_enum_member(container: Any, enum_name: str, member_name: str) -> Any:
    enum = getattr(container, enum_name, None)
    member = getattr(enum, member_name, None) if enum is not None else None
    if member is not None:
        return member
    return getattr(container, member_name, None)


def _priority(value: Any) -> AnnouncementPriority:
    if isinstance(value, AnnouncementPriority):
        return value
    try:
        return AnnouncementPriority(str(value).strip().lower())
    except Exception:
        return AnnouncementPriority.POLITE


def _set_accessible_description(target: Any, message: str) -> bool:
    setter = getattr(target, "setAccessibleDescription", None)
    if not callable(setter):
        return False
    try:
        setter(message)
    except Exception:
        return False
    return True


def _native_widget_handle(target: Any) -> Optional[int]:
    """Return a live Qt widget's native view/HWND, or ``None`` when unverified."""

    if target is None:
        return None
    try:
        from aqt import qt

        widget_type = getattr(qt, "QWidget", None)
        if widget_type is None or not isinstance(target, widget_type):
            return None
    except Exception:
        return None

    # QWidget.winId() forces a native child window. That can change stacking,
    # clipping, and focus behavior merely because an announcement was posted.
    # effectiveWinId() instead returns the nearest native ancestor without
    # promoting an ordinary child; a top-level winId remains the safe fallback.
    effective_win_id = getattr(target, "effectiveWinId", None)
    if callable(effective_win_id):
        try:
            handle = int(effective_win_id())
        except Exception:
            handle = 0
        if handle > 0:
            return handle

    candidates = []
    window_getter = getattr(target, "window", None)
    if callable(window_getter):
        try:
            window = window_getter()
        except Exception:
            window = None
        if window is not None:
            candidates.append(window)

    for candidate in candidates:
        win_id = getattr(candidate, "winId", None)
        if not callable(win_id):
            continue
        try:
            handle = int(win_id())
        except Exception:
            continue
        if handle > 0:
            return handle
    return None


def _load_macos_accessibility_api() -> Optional[Any]:
    """Bind the small AppKit/CoreFoundation surface needed for announcements."""

    if platform.system() != "Darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        appkit_path = ctypes.util.find_library("AppKit") or (
            "/System/Library/Frameworks/AppKit.framework/AppKit"
        )
        core_foundation_path = ctypes.util.find_library("CoreFoundation") or (
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        appkit = ctypes.CDLL(appkit_path)
        core_foundation = ctypes.CDLL(core_foundation_path)

        post_notification = appkit.NSAccessibilityPostNotificationWithUserInfo
        post_notification.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        post_notification.restype = None

        create_string = core_foundation.CFStringCreateWithCString
        create_string.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        create_string.restype = ctypes.c_void_p

        create_number = core_foundation.CFNumberCreate
        create_number.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        create_number.restype = ctypes.c_void_p

        create_dictionary = core_foundation.CFDictionaryCreate
        create_dictionary.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        create_dictionary.restype = ctypes.c_void_p

        release = core_foundation.CFRelease
        release.argtypes = [ctypes.c_void_p]
        release.restype = None

        notification = ctypes.c_void_p.in_dll(
            appkit,
            "NSAccessibilityAnnouncementRequestedNotification",
        ).value
        announcement_key = ctypes.c_void_p.in_dll(
            appkit,
            "NSAccessibilityAnnouncementKey",
        ).value
        priority_key = ctypes.c_void_p.in_dll(
            appkit,
            "NSAccessibilityPriorityKey",
        ).value
        key_callbacks_symbol = ctypes.c_byte.in_dll(
            core_foundation,
            "kCFTypeDictionaryKeyCallBacks",
        )
        value_callbacks_symbol = ctypes.c_byte.in_dll(
            core_foundation,
            "kCFTypeDictionaryValueCallBacks",
        )
        key_callbacks = ctypes.c_void_p(ctypes.addressof(key_callbacks_symbol))
        value_callbacks = ctypes.c_void_p(ctypes.addressof(value_callbacks_symbol))
        if not all((notification, announcement_key, priority_key)):
            return None

        def post(handle: int, message: str, native_priority: int) -> bool:
            references = []
            try:
                message_ref = create_string(
                    None,
                    message.encode("utf-8"),
                    0x08000100,  # kCFStringEncodingUTF8
                )
                if not message_ref:
                    return False
                references.append(message_ref)

                priority_value = ctypes.c_longlong(native_priority)
                priority_ref = create_number(
                    None,
                    4,  # kCFNumberSInt64Type
                    ctypes.byref(priority_value),
                )
                if not priority_ref:
                    return False
                references.append(priority_ref)

                keys = (ctypes.c_void_p * 2)(announcement_key, priority_key)
                values = (ctypes.c_void_p * 2)(message_ref, priority_ref)
                user_info = create_dictionary(
                    None,
                    keys,
                    values,
                    2,
                    key_callbacks,
                    value_callbacks,
                )
                if not user_info:
                    return False
                references.append(user_info)
                post_notification(handle, notification, user_info)
                return True
            finally:
                for reference in reversed(references):
                    try:
                        release(reference)
                    except Exception:
                        pass

        return SimpleNamespace(post=post)
    except Exception:
        return None


def post_macos_accessibility_announcement(
    target: Any,
    message: Any,
    priority: Any = AnnouncementPriority.POLITE,
    *,
    system_name: Optional[str] = None,
    api_loader: Optional[Callable[[], Optional[Any]]] = None,
    handle_resolver: Optional[Callable[[Any], Optional[int]]] = None,
) -> bool:
    """Post an AppKit announcement with low or high native priority."""

    if (system_name or platform.system()) != "Darwin":
        return False
    text = str(message or "").strip()
    if not text:
        return False
    resolved_priority = _priority(priority)
    native_priority = (
        _NS_ACCESSIBILITY_PRIORITY_HIGH
        if resolved_priority is AnnouncementPriority.ASSERTIVE
        else _NS_ACCESSIBILITY_PRIORITY_LOW
    )
    try:
        handle = (handle_resolver or _native_widget_handle)(target)
        if not handle or int(handle) <= 0:
            return False
        api = (api_loader or _load_macos_accessibility_api)()
        poster = getattr(api, "post", None)
        if not callable(poster):
            return False
        return bool(poster(int(handle), text, native_priority))
    except Exception:
        return False


def _load_windows_accessibility_api() -> Optional[Any]:
    """Bind user32 NotifyWinEvent only when it exists."""

    if platform.system() != "Windows":
        return None
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        notify_win_event = user32.NotifyWinEvent
        notify_win_event.argtypes = [
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_long,
        ]
        notify_win_event.restype = None

        def notify(event: int, hwnd: int, object_id: int, child_id: int) -> bool:
            notify_win_event(event, hwnd, object_id, child_id)
            return True

        return SimpleNamespace(notify=notify)
    except Exception:
        return None


def post_windows_live_region_announcement(
    target: Any,
    message: Any,
    priority: Any = AnnouncementPriority.POLITE,
    *,
    system_name: Optional[str] = None,
    api_loader: Optional[Callable[[], Optional[Any]]] = None,
    hwnd_resolver: Optional[Callable[[Any], Optional[int]]] = None,
    description_setter: Optional[Callable[[Any, str], bool]] = None,
) -> bool:
    """Update the accessible description, then raise a Win32 live-region event.

    ``NotifyWinEvent`` has no priority field. The priority argument is accepted
    to keep the cross-platform call contract stable, while Windows assistive
    technology determines interruption behavior from its own live settings.
    """

    if (system_name or platform.system()) != "Windows":
        return False
    text = str(message or "").strip()
    if not text:
        return False
    _priority(priority)
    try:
        hwnd = (hwnd_resolver or _native_widget_handle)(target)
        if not hwnd or int(hwnd) <= 0:
            return False
        setter = description_setter or _set_accessible_description
        if not bool(setter(target, text)):
            return False
        api = (api_loader or _load_windows_accessibility_api)()
        notify = getattr(api, "notify", None)
        if not callable(notify):
            return False
        return bool(
            notify(
                _EVENT_OBJECT_LIVEREGIONCHANGED,
                int(hwnd),
                _OBJID_CLIENT,
                _CHILDID_SELF,
            )
        )
    except Exception:
        return False


def post_native_accessibility_announcement(
    target: Any,
    message: Any,
    priority: Any = AnnouncementPriority.POLITE,
    *,
    system_name: Optional[str] = None,
    macos_poster: Optional[Callable[[Any, str, AnnouncementPriority], Any]] = None,
    windows_poster: Optional[
        Callable[[Any, str, AnnouncementPriority], Any]
    ] = None,
) -> bool:
    """Route a live announcement to the current platform's native bridge."""

    text = str(message or "").strip()
    if not text:
        return False
    resolved_priority = _priority(priority)
    name = system_name or platform.system()
    try:
        if name == "Darwin":
            if macos_poster is not None:
                return bool(macos_poster(target, text, resolved_priority))
            return post_macos_accessibility_announcement(
                target,
                text,
                resolved_priority,
                system_name=name,
            )
        if name == "Windows":
            if windows_poster is not None:
                return bool(windows_poster(target, text, resolved_priority))
            return post_windows_live_region_announcement(
                target,
                text,
                resolved_priority,
                system_name=name,
            )
    except Exception:
        return False
    return False


class AccessibilityAnnouncer:
    """Deliver live announcements through Qt 6.8+ with safe older-Qt fallbacks."""

    def __init__(
        self,
        target: Any = None,
        *,
        qt_loader: Optional[Callable[[], Optional[Any]]] = None,
        native_bridge: Optional[
            Callable[[Any, str, AnnouncementPriority], Any]
        ] = None,
        fallback: Optional[Callable[[Any, str, AnnouncementPriority], Any]] = None,
        generation_guard: Optional[OperationGenerationGuard] = None,
    ) -> None:
        self.target = target
        self._qt_loader = qt_loader or _load_qt_accessibility_api
        self._native_bridge = native_bridge or post_native_accessibility_announcement
        self._fallback = fallback
        self.generation_guard = generation_guard or OperationGenerationGuard()
        self.last_message = ""
        self.last_priority = AnnouncementPriority.POLITE
        self.last_delivery = "none"

    def begin_operation(self) -> int:
        return self.generation_guard.begin()

    def invalidate_operations(self) -> int:
        return self.generation_guard.invalidate()

    def announce(
        self,
        message: Any,
        *,
        priority: Any = AnnouncementPriority.POLITE,
        target: Any = None,
        generation: Optional[int] = None,
    ) -> bool:
        text = str(message or "").strip()
        if not text:
            self.last_delivery = "none"
            return False
        if generation is not None and not self.generation_guard.is_current(generation):
            self.last_delivery = "stale"
            return False

        source = self.target if target is None else target
        resolved_priority = _priority(priority)
        self.last_message = text
        self.last_priority = resolved_priority

        try:
            qt_api = self._qt_loader()
        except Exception:
            qt_api = None
        if qt_api is not None and source is not None:
            if self._announce_with_qt(qt_api, source, text, resolved_priority):
                return True

        if source is not None:
            try:
                accepted = self._native_bridge(source, text, resolved_priority)
            except Exception:
                accepted = False
            if bool(accepted):
                self.last_delivery = "native"
                return True

        if self._set_accessible_description(source, text):
            self.last_delivery = "description"
            return True
        if self._fallback is not None:
            try:
                accepted = self._fallback(source, text, resolved_priority)
            except Exception:
                accepted = False
            self.last_delivery = "fallback" if accepted is not False else "none"
            return accepted is not False
        self.last_delivery = "none"
        return False

    def _announce_with_qt(
        self,
        qt_api: Any,
        source: Any,
        message: str,
        priority: AnnouncementPriority,
    ) -> bool:
        accessible = getattr(qt_api, "QAccessible", None)
        update = getattr(accessible, "updateAccessibility", None)
        if not callable(update):
            return False

        announcement_event = getattr(
            qt_api,
            "QAccessibleAnnouncementEvent",
            None,
        )
        if announcement_event is not None:
            try:
                event = announcement_event(source, message)
                setter = getattr(event, "setPoliteness", None)
                member_name = (
                    "Assertive"
                    if priority is AnnouncementPriority.ASSERTIVE
                    else "Polite"
                )
                qt_priority = _qt_enum_member(
                    accessible,
                    "AnnouncementPoliteness",
                    member_name,
                )
                if callable(setter) and qt_priority is not None:
                    setter(qt_priority)
                update(event)
                self.last_delivery = "announcement"
                return True
            except Exception:
                pass

        self._set_accessible_description(source, message)
        accessible_event = getattr(qt_api, "QAccessibleEvent", None)
        alert = _qt_enum_member(accessible, "Event", "Alert")
        if accessible_event is None or alert is None:
            return False
        try:
            update(accessible_event(source, alert))
        except Exception:
            return False
        self.last_delivery = "alert"
        return True

    @staticmethod
    def _set_accessible_description(target: Any, message: str) -> bool:
        return _set_accessible_description(target, message)


__all__ = [
    "AccessibilityAnnouncer",
    "AnnouncementPriority",
    "EffectiveMotionPolicy",
    "OperationGenerationGuard",
    "effective_motion_enabled",
    "effective_motion_policy",
    "read_macos_reduced_motion",
    "read_system_reduced_motion",
    "read_windows_reduced_motion",
    "post_macos_accessibility_announcement",
    "post_native_accessibility_announcement",
    "post_windows_live_region_announcement",
]
