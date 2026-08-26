"""Capture-only infrastructure for exact Anki Garden UI evidence.

This package is excluded from production archives.  The capture derivative
ships it beside the tiny :mod:`ankigarden.capture_ui_faces` bootstrap.
"""

from __future__ import annotations

from .contract import (
    CAPTURE_CONTRACT_PATH,
    compile_contract,
    contract_digest,
    load_compiled_contract,
)
from .model import CaptureResult, ProfilePlacement, RunGateResult, SurfaceSpec
from .registry import REGISTRY, SurfaceRegistry

__all__ = (
    "CAPTURE_CONTRACT_PATH",
    "CaptureResult",
    "ProfilePlacement",
    "REGISTRY",
    "RunGateResult",
    "SurfaceRegistry",
    "SurfaceSpec",
    "compile_contract",
    "contract_digest",
    "load_compiled_contract",
)
