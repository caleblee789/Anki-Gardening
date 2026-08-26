# Anki Garden 2.1.0 final UI audit

Status: final v25 exhaustive capture and release acceptance are pending.

## Current acceptance contract

Capture contract v25 owns registry-derived `representative` preflight and
`full` final-release profiles. Visual review reduced the current topology to
16 representative and 31 full surfaces, producing two and five sheets. The 95
retired IDs remain reserved, and no watering-can capture remains active. Totals
are generated from the registry rather than fixed runtime rules.
Both run at `QT_SCALE_FACTOR=1.0` and require exact compiled-contract order,
zero gross acquisition or lifecycle failures. Text, semantic, layout, scroll,
and duplicate-view findings are retained as non-blocking review advisories. The preflight may
contribute unchanged overlapping surface evidence, but final acceptance
requires a complete validated full manifest, exact-package clean-shutdown
binding, and a formal sheet set. A normal profile uses one Anki process for all
selected surfaces; memory-leak probing is not part of capture. Raw manifest-owned
PNGs are the runtime geometry authority.

## Latest v24 comparison evidence

The newest automated v24 full attempt is preserved at
`build/ui-face-captures/full/capture-sequence-20260825-153624`. Its assembled
manifest contains 125 of 126 valid surfaces: 124 were reused and
`progress-overview-redirect-growth` was replaced. The attempted replacement for
`streak-achievement-earned-next` failed its fixture postcondition, so no prior
pixel was substituted. The manifest also has no valid run-level authority.

The underlying attempt manifest at
`build/ui-face-captures/full/capture-sequence-20260825-153624/20260825-153742/manifest.json`
records a passing clean shutdown but a failed Nursery memory gate. After 12
visible-and-closed cycles, the total widget count grew by 24: 12 `QLabel` and
12 `QPushButton` instances. That result remains a release blocker rather than
being normalized as cache growth.

The manually assembled set at
`build/ui-face-captures/full/visual-all-surfaces-20260825-154038` contains all
126 v24 PNGs and 17 reviewed contact sheets with no recorded visual findings.
Its manifest explicitly records `visual_review_only: true` and
`release_evidence: false`; its production package hash is
`72a137563b4cb6922cc4e2b4e68f5235d219ce872edf07e0bf078b7593778e25`.
It is comparison material only and cannot seed the first v25 formal baseline.

## Preserved incomplete attempts

The latest user-authorized capture invocation on 2026-08-24 is preserved at:

- root: `build/ui-face-captures/capture-sequence-20260824-154028`;
- manifest:
  `build/ui-face-captures/capture-sequence-20260824-154028/20260824-154032/manifest.json`;
- log: `build/ui-face-captures/capture-sequence-20260824-154028/anki.log`;
- capture derivative:
  `build/ui-face-captures/capture-sequence-20260824-154028/anki_garden_capture.ankiaddon`.

That v22 representative run finished in 58.6 seconds and wrote all 26/26 raw
PNGs. It failed closed with 25 fixture/layout failures and 25 warning records,
so `complete` and `fixture_validations_complete` are false and no contact
sheets, report, or evidence archive were generated. The manifest is SHA-256
`c81c2737572ee6b29bd41191c77aa2b3264d277640b2ee23e109d6a6ecce6fc7`;
the log is SHA-256
`9f97783a079438f1bab2d960b2c92a9c4ad93b417a2e8711782a12a8a79256f5`.
The attempted production candidate was SHA-256
`b6f0c830dde38dea7f58869ba637d345a1cd35d112284f3006153eaa59dac152`;
its byte-matched capture derivative was SHA-256
`c64c49ae3be805c87ae7cbd5055bff070a95242660d2a32486b9e8ecfaf721bb`.

Raw-PNG review separated real defects from audit defects. The follow-up source
fixes now own exact native button border telemetry, text-fit floors, hidden-tab
scrollbar visibility, canonical `31 of 38 collectibles collected` state,
reversible partial Nursery fixtures, the 1240 by 840 Garden scene cap, and a
Reviewer capture that requires a real card while Garden is closed. These fixes
have passed the repository gates below but have not been represented as visual
release evidence because the user limited GUI capture to one new attempt.

The earlier v21 diagnostic attempt remains preserved at:

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

The shared native telemetry import failure, stale Garden minimum height, hidden
Nursery feedback host, capture-fixture copy/state drift, and transaction audit
assumptions found by that attempt were corrected before v22. The release
sequence was then reduced to one stable state per distinct interface to avoid
treating the contact sheet as a second exhaustive test suite.

## Historical validation snapshot

- Focused v22 capture, validator, dialog, and transaction checks: 129 passed.
- Full repository suite: 1,917 passed and 10 skipped.
- Focused exact-package checks: 11 passed; artwork audit, Python compilation,
  archive integrity, and whitespace checks passed.
- Current production archive: 274 entries, 81,902,954 bytes, SHA-256
  `c7619cf8ea52c0e6a001c22d6f2b1002c477b4d04a4cdf8bdb0210f779c2a6fb`.
- Source/archive parity: 274/274 package payloads are byte-identical.
- The streamlined `capture-sequence` skill passes its structural validator.
- No subsequent GUI capture has been started. It requires explicit user
  authorization because the latest v22 attempt consumed the one requested run.

## Unrun acceptance

Until separately run and recorded, the following remain open:

- v25 representative raw preflight and contact-sheet validation and review;
- final v25 full raw capture and contact-sheet validation and review;
- exact final-package restart and interactive persistence journeys;
- native Windows/Linux GUI behavior and true OS 125%/150% or mixed-DPI scaling;
- forced colors, screen-reader, contrast, broader keyboard walkthrough, and
  human/device visual acceptance.

No predecessor capture, source test, or capture derivative closes those gates.
