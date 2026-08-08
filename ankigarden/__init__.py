"""Anki Garden add-on entrypoint."""

from __future__ import annotations

import logging
import os
import traceback
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _report_startup_error(exc: Exception) -> None:
    message = f"Anki Garden failed to start: {exc}"
    logger.error(message)
    logger.error(traceback.format_exc())

    try:
        from aqt.utils import showWarning

        showWarning(f"{message}\n\nSee console/log for traceback details.")
        return
    except Exception:
        pass

    try:
        from aqt.utils import showInfo

        showInfo(message)
    except Exception:
        # Keep imports safe in non-Anki environments.
        pass


def _initialize_addon(setup_func: Optional[Callable[[], None]] = None) -> bool:
    try:
        if setup_func is None:
            from .addon import setup_addon as setup_func

        setup_func()
        return True
    except Exception as exc:
        _report_startup_error(exc)
        return False


if os.environ.get("ANKI_GARDEN_SKIP_STARTUP") != "1":
    _initialize_addon()
