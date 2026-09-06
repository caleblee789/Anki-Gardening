# Garden navigation performance — 2026-09-06

Implemented quick, soft hover feedback and removed redundant navigation and rendering work. Changes are uncommitted and preserve the surrounding work in progress.

## Behavior

- Hover uses 100 ms elapsed-time fades, an 80 ms exit grace period that does not restart while crossing empty space, and 16 ms frames only during interaction transitions. Repeated movement within one plant adds no repaint requests.
- Hover repaints cover changed artwork bounds; alpha hit-test images and display-resolution contour masks use bounded caches. The original artwork remains full resolution.
- Static raster scenes stop the animation timer after settling. Fallback sun/petal animation, move transitions, nurture effects, and reduced-motion behavior remain supported.
- Collection filtering and sorting reuse cards and unchanged species details. State changes still rebuild current content; empty results and selection remain reconciled. Batched cards receive a parent before visibility changes, and deferred layout passes are coalesced.
- Reopening an unchanged current section skips redundant presentation/layout work. Explicit subsection/item/focus requests still dispatch. Timing is opt-in through the existing performance recorder; no public API or saved-state migration was introduced.

## Measured results

Native Anki 26.08.1 on this Mac, six planted species, 810 × 540 logical scene, Retina DPR 2. The saved pre-change scene class and dashboard handlers were compared with the candidate in the same process using the same dependencies and fixture. These are local samples, not cross-machine guarantees.

| Operation | Baseline median ms | Candidate median ms | Candidate p95 ms |
| --- | ---: | ---: | ---: |
| Collection filtering | 100.721 | 1.080 | 1.261 |
| Reopening the current Garden section | 25.072 | 0.001 | 0.001 |
| Garden/Collection round trip | 65.526 | 68.632 | 70.285 |
| Warm hovered-scene render | 7.400 | 7.075 | 7.976 |

The native paint handler drew the first highlight in **19.4–21.1 ms across all six plants**. This measures application rendering, not physical display scanout. Pointer handling p95 was 0.023 ms. One cold hovered-scene render measured 300.9 → 35.6 ms. Cold full collection rebuild samples were 104.9 → 123.3 ms; full rebuilds are not claimed as improved. The normal idle scene stops repainting entirely once hover/effects settle.

## Validation

- Focused performance, interaction, recorder, and planter checks: **67 passed, 1 skipped**.
- Existing live Qt layout checks using Anki's installed Qt runtime: **3 passed**; the grid check now also covers parent ownership during batching.
- **26 native behavioral assertions passed**, covering card/detail reuse, filtering/empty states, alpha hit-test parity, keyboard selection, pinned highlight ownership, Escape, committed move/undo, reduced motion, timer settling, fallback animation, and bounded caches.
- Unhovered artwork was pixel-identical to the baseline at 620 × 414, 810 × 540, and 1260 × 840 in both day and night settings. Native Garden, Collection, and hover renders were inspected. This is targeted QA, not complete release-capture or owner comfort acceptance.
- Broader suite recorded **1,683 passed, 12 failed, 21 skipped, 817 deselected**. Failures involve balance/economy, capture contracts, artwork metadata, and reward-summary motion outside these edits. A temporary pre-change checkout reproduced overlapping failures; surrounding work changed during the run, so the broader suite is not claimed green. See `final-suite.log` and `baseline-failures.log` in the evidence folder.
- ZIP integrity and exact package parity for all three modified runtime files passed at native validation. A subsequent concurrent edit added mastery/overflow copy to `dashboard.py`; that edit is preserved in the working tree and is absent from this frozen tested package. The performance methods remain identical to the tested snapshot. Final idle-rendering edits received the focused and native checks above after the broad run.

## Candidate and evidence

Evidence: `build/performance/garden-navigation-20260906/`.

Candidate: `garden-navigation.ankiaddon` in that folder; SHA-256 `155470a970fb55b4306b3fa91102080199ec7fd88137ed1e2cddb029d8643440`.

Native QA used only `/private/tmp/anki-release-qa.ridlhu2d`, profile `Codex Garden Performance 20260906`, with automatic/media sync disabled and credentials absent. Process, window, filesystem, and sync identity gates were checked after each controlled restart. App-wide UI automation was stopped when it resolved a normal Anki window; subsequent checks and shutdown were bound to the disposable process. The final disposable PID 13383 was confirmed exited. Nothing was published or installed into the normal profile.

Remaining acceptance: owner assessment of comfort, broader release checks, and physical non-Retina/platform coverage.
