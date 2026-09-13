# Immediate HUD feedback — 2026-09-10

## Changes

The previous package was installed and Anki restarted, but the user continued to observe a 1–3 second HUD delay while the next question appeared promptly. Both the narrow tab and expanded panel were affected.

This follow-up changes only `hooks/reviewer.py`, `ui/reviewer_hud_widget.py`, and `runtime.py` over the exact installed baseline. It preserves additional installed layout work and all earlier history-pagination/incremental-total fixes.

- Both layouts accept committed feedback before full projection, broad state notifications, and feedback acknowledgements. A coalesced callback queue releases secondary work after a natural feedback paint. Next-question refreshes respect that boundary; hidden/disposed views release work without requiring a paint. No forced repaint or nested event loop is added to production.
- The expanded panel no longer waits 220 ms before applying progress, gates session totals behind a 420 ms progress animation, or spends 600 ms counting to the earned total. Values update directly; the existing highlight and plant pulse remain. The visible reward feed renders incoming amounts at full opacity. The hidden legacy “This card” row stays hidden.
- The narrow rail still combines Growth and keeps other rewards before it. Its 950 ms resource, 1,150 ms milestone, and 1,650 ms Full Bloom holds are unchanged. Those deliberate waits are separate from processing delay.
- Reconciliation now consumes a pending local-answer marker only when the matching operation notification arrives. An unrelated operation previously cleared that marker, allowing Anki's subsequent answer notification to trigger an unnecessary history scan. Unknown card operations continue to invalidate history; sync, Undo, and replacement safeguards remain.

The expanded timing chain and pre-paint secondary work were reproduced offline against the frozen installed baseline. The interleaved-operation attribution defect also failed an offline regression before its correction. The actual live source of every reported stall is not proven; no new live recording was made.

## Verification

No Anki application was launched, and no action was taken in the user's collection. The Qt harness used an offscreen QApplication with lightweight Anki adapters.

- Four baseline integration variants failed as expected, demonstrating that the old answer path performed secondary work before the feedback paint and/or withheld the exact visible total.
- 128 focused Python tests pass across the reviewer, session integration/totals, history reconciliation, and performance recorder. The initial pass had five outdated presentation stubs; after adapting those stubs to the deferred boundary, the affected 79-test subset passed. The other 49 tests were not repeated.
- Nine headless Qt cases pass against the exact candidate archive. They cover the complete answer-hook/next-question/visible-paint path in both layouts with motion enabled and disabled, resource order and combined Growth, Full Bloom hold and mode transfer, and existing layout interactions.
- `git diff --check` passes.

### Headless presentation timing

12 samples per scenario; milliseconds from committed-result submission to the first visible feedback-label paint event. These component figures are not physical-input-to-display or live-Anki measurements. The full callback order is checked separately by the integration regression.

| Layout | Prior answers | Median | p95 |
| --- | ---: | ---: | ---: |
| Expanded | 0 | 1.137 | 3.774 |
| Expanded | 500 | 2.164 | 2.320 |
| Expanded | 5,000 | 2.231 | 2.664 |
| Narrow | 0 | 0.666 | 0.816 |
| Narrow | 500 | 0.803 | 0.856 |
| Narrow | 5,000 | 0.746 | 0.902 |

No artificial resource holds were included in those timing samples. The user's next normal review remains the live acceptance check. If delay persists, capture a short bounded trace during normal reviewing before further changes.

## Package and installation

Archive: `dist/anki_garden-hud-immediate.ankiaddon`

SHA256: `837194fb8e521c235260828b3b04a1af18892816d1daabff216f751972bd1861`

Installed baseline SHA256: `d66ebcc0492f61941d846724d2e120bf9ca87578941503d8b780c8648ef0c552`

Version metadata remains 2.2.0; file parity and archive hash identify this patch. All 270 managed payload entries are retained, with only the three scoped modules replaced. No saved-state schema changes or migrations are required.

Installed after Anki closed. All 270 managed payload files match the exact candidate archive. The three replaced modules were backed up to `/Users/test/Library/Application Support/Anki2/anki-garden-backups/20260910-184931-hud-immediate`. The installer verified baseline parity before writing; settings and mutable Garden data were not replaced. Anki was not reopened.

Evidence: `build/performance/hud-immediate-20260910/` contains the baseline/candidate archives, scoped patch, regression output, headless timings, and guarded installer. `installation.json` records the completed backup and installed-file parity check.
