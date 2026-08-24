# Anki Garden 2.1.0 final UI audit

Status: final v22 representative capture and release merge are pending.

## Current acceptance contract

Capture contract v22 owns 26 distinct interfaces in five ordered groups. A
release run must capture all 26 once at `QT_SCALE_FACTOR=1.0`, produce four
validated contact-sheet pages, and report zero capture failures and zero text or
geometry warnings. Raw manifest-owned PNGs are the runtime geometry authority.

The optional `full` profile retains the earlier 126-state sequence for targeted
diagnosis. Automated tests own alternate loading, empty, warning, error,
success, accessibility, stress, responsive, and memory-cycle coverage; those
states are not repeated in the release contact sheet.

## Preserved incomplete attempt

The user-authorized single capture invocation on 2026-08-24 is preserved at:

- root: `build/ui-face-captures/capture-sequence-20260824-143922`;
- partial manifest:
  `build/ui-face-captures/capture-sequence-20260824-143922/20260824-143926/manifest.json`;
- log: `build/ui-face-captures/capture-sequence-20260824-143922/anki.log`.

That v21 attempt stopped at 50/126 screenshots and reported failures and layout
warnings, so it produced no accepted contact-sheet set. It is diagnostic
material only and must not be represented as release evidence. The attempted
production candidate was SHA-256
`7808511f873cd8b8b414dcb56738381e13c3f164c37e2b1abfa9b9bf8f27b8a9`; its
capture derivative was SHA-256
`c5f005820558ee5f3fbbf726ed6c3d5d4781a3456b7dad8f6216ebbf50e84b69`.

The shared native telemetry import failure, text-fit button shrinkage, stale
Garden minimum height, hidden Nursery feedback host, capture-fixture copy/state
drift, and transaction audit assumptions found by that attempt have been
corrected. The release sequence was then reduced to one stable state per
distinct interface to avoid treating the contact sheet as a second exhaustive
test suite.

## Validation status

- Focused v22 capture, validator, dialog, and transaction checks: 114 passed.
- Full repository suite: 1,916 passed and 9 skipped.
- Focused exact-package checks: 11 passed; artwork audit, Python compilation,
  archive integrity, and whitespace checks passed.
- Final production archive: 274 entries, 81,902,124 bytes, SHA-256
  `b6f0c830dde38dea7f58869ba637d345a1cd35d112284f3006153eaa59dac152`.
- Source/archive parity: 274/274 package payloads are byte-identical.
- No second GUI capture has been started. It requires explicit user
  authorization because the user requested only one attempt while using this
  computer.

## Unrun acceptance

Until separately run and recorded, the following remain open:

- final v22 26/26 raw capture and 4/4 contact-sheet validation and review;
- exact final-package restart and interactive persistence journeys;
- native Windows/Linux GUI behavior and true OS 125%/150% or mixed-DPI scaling;
- forced colors, screen-reader, contrast, broader keyboard walkthrough, and
  human/device visual acceptance.

No predecessor capture, source test, or capture derivative closes those gates.
