from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class UserNotice:
    message: str = ""
    created_at: float = 0.0
    key: str = ""


class NoticeChannel:
    def __init__(self) -> None:
        self.current = UserNotice()
        self._last_emitted_at = 0.0

    def publish(
        self,
        message: str,
        *,
        throttle_seconds: float = 8.0,
        key: str = "",
    ) -> bool:
        now = time.monotonic()
        self.current = UserNotice(str(message), now, str(key or ""))
        if now - self._last_emitted_at < throttle_seconds:
            return False
        self._last_emitted_at = now
        return True

    def clear(self, *, key: str | None = None) -> None:
        # Empty keys are retained for compatibility with notices created by
        # older builds; a typed recovery may safely retire that legacy warning.
        if key is not None and self.current.key not in ("", str(key)):
            return
        self.current = UserNotice()


USER_NOTICES = NoticeChannel()
