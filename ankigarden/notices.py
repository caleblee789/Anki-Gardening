from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class UserNotice:
    message: str = ""
    created_at: float = 0.0


class NoticeChannel:
    def __init__(self) -> None:
        self.current = UserNotice()
        self._last_emitted_at = 0.0

    def publish(self, message: str, *, throttle_seconds: float = 8.0) -> bool:
        now = time.monotonic()
        self.current = UserNotice(str(message), now)
        if now - self._last_emitted_at < throttle_seconds:
            return False
        self._last_emitted_at = now
        return True

    def clear(self) -> None:
        self.current = UserNotice()


USER_NOTICES = NoticeChannel()
