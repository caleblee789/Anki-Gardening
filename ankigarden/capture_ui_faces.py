"""Compatibility bootstrap for the capture-only v26 runtime.

Production archives exclude both this file and :mod:`ankigarden.capture`.
Capture archives include them only when the immutable build capability enables
the harness.
"""

from __future__ import annotations

from typing import Any

from .build_capabilities import CAPTURE_HARNESS_ENABLED


def start_capture(app: Any) -> None:
    """Load the capture runtime only in an explicitly built capture archive."""

    if not CAPTURE_HARNESS_ENABLED:
        raise RuntimeError("capture harness is unavailable in a production build")
    from .capture.runtime import start_capture as run_capture

    run_capture(app)


__all__ = ("start_capture",)
