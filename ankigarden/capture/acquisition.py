"""Pure acquisition-policy selection used by the Qt runtime and fast tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .model import CandidateRejection, SurfaceSpec


@dataclass(frozen=True)
class AcquisitionIdentity:
    process_id: int
    window_id: int
    window_role: str
    bounds: tuple[int, int, int, int]
    device_pixel_ratio: float


@dataclass(frozen=True)
class AcquisitionCandidate:
    backend: str
    pixmap: Any = field(compare=False, repr=False)
    process_id: int | None = None
    window_id: int | None = None
    window_role: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    device_pixel_ratio: float = 1.0
    null: bool = False
    blank: bool = False
    painted: bool = True
    semantic_state_valid: bool = False
    overlay_pixels_present: bool = True


@dataclass(frozen=True)
class AcquisitionDecision:
    accepted: AcquisitionCandidate | None
    rejected: tuple[CandidateRejection, ...]
    failure_reason: str = ""


def _reject(candidate: AcquisitionCandidate, reason: str) -> CandidateRejection:
    return CandidateRejection(
        candidate.backend,
        reason,
        {
            "process_id": candidate.process_id,
            "window_id": candidate.window_id,
            "window_role": candidate.window_role,
            "bounds": list(candidate.bounds),
            "device_pixel_ratio": candidate.device_pixel_ratio,
        },
    )


def _pixel_issue(
    candidate: AcquisitionCandidate,
    *,
    require_semantic_identity: bool,
    require_overlay: bool,
) -> str:
    """Return only acquisition defects that can reject this candidate.

    A direct Qt grab is accepted on pixel integrity alone. Detailed semantic
    state belongs to the review audit and must not turn a real, painted dialog
    into a failed capture. Home/Reviewer composites are the exception: their
    semantic identity and required overlay prove that the WebView/shell image
    is the requested app-owned surface rather than a plausible wrong window.
    """

    if candidate.pixmap is None or candidate.null:
        return "null-pixmap"
    if candidate.blank:
        return "blank-pixmap"
    if not candidate.painted:
        return "unpainted-frame"
    if require_semantic_identity and not candidate.semantic_state_valid:
        return "semantic-state-mismatch"
    if require_overlay and not candidate.overlay_pixels_present:
        return "required-overlay-missing"
    return ""


def _identity_issue(
    candidate: AcquisitionCandidate,
    expected: AcquisitionIdentity,
) -> str:
    if candidate.process_id != expected.process_id:
        return "process-id-mismatch"
    if candidate.window_id != expected.window_id:
        return "window-id-mismatch"
    if candidate.window_role != expected.window_role:
        return "window-role-mismatch"
    if candidate.bounds != expected.bounds:
        return "window-bounds-mismatch"
    if abs(candidate.device_pixel_ratio - expected.device_pixel_ratio) > 0.001:
        return "device-pixel-ratio-mismatch"
    return ""


def select_candidate(
    spec: SurfaceSpec,
    candidates: Sequence[AcquisitionCandidate],
    *,
    expected_identity: AcquisitionIdentity | None = None,
) -> AcquisitionDecision:
    """Select the most accurate allowed candidate and retain every rejection.

    Native dialogs accept only a direct QWidget grab.  App-owned Home and
    Reviewer shells prefer the verified Qt shell/WebView composite; a
    compositor candidate is considered only when every native identity field
    and the semantic/pixel audits match.
    """

    rejected: list[CandidateRejection] = []
    if spec.acquisition_policy == "qt-widget-grab":
        rejected.extend(
            _reject(candidate, "backend-not-allowed")
            for candidate in candidates
            if candidate.backend != "qt-widget-grab"
        )
        direct = [candidate for candidate in candidates if candidate.backend == "qt-widget-grab"]
        if not direct:
            return AcquisitionDecision(None, (), "direct-widget-grab-missing")
        candidate = direct[0]
        issue = _pixel_issue(
            candidate,
            require_semantic_identity=False,
            require_overlay=False,
        )
        if issue:
            rejected.append(_reject(candidate, issue))
            return AcquisitionDecision(None, tuple(rejected), issue)
        return AcquisitionDecision(candidate, tuple(rejected))

    preferred = [
        candidate for candidate in candidates
        if candidate.backend == "qt-shell-with-webview"
    ]
    fallback = [
        candidate for candidate in candidates
        if candidate.backend in {"foreground-screen-region", "native-window"}
    ]
    rejected.extend(
        _reject(candidate, "backend-not-allowed")
        for candidate in candidates
        if candidate not in preferred and candidate not in fallback
    )
    for candidate in preferred:
        issue = _pixel_issue(
            candidate,
            require_semantic_identity=True,
            require_overlay=True,
        )
        if not issue:
            return AcquisitionDecision(candidate, tuple(rejected))
        rejected.append(_reject(candidate, issue))

    if not spec.allow_foreground_fallback:
        return AcquisitionDecision(None, tuple(rejected), "foreground-fallback-forbidden")
    if expected_identity is None:
        return AcquisitionDecision(None, tuple(rejected), "foreground-identity-missing")
    for candidate in fallback:
        issue = _identity_issue(candidate, expected_identity) or _pixel_issue(
            candidate,
            require_semantic_identity=True,
            require_overlay=True,
        )
        if not issue:
            return AcquisitionDecision(candidate, tuple(rejected))
        rejected.append(_reject(candidate, issue))
    return AcquisitionDecision(None, tuple(rejected), "no-verified-capture-candidate")
