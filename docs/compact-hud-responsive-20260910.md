# Compact HUD responsiveness fix — 2026-09-10

## Behavior and cause

Committed feedback now reaches the mounted compact HUD before full projection, history, and session-summary work. Compact sequencing runs independently of expanded celebrations. Growth is readable at full opacity on its first paint; the pulse remains. Pending Growth combines, including an update to currently displayed Growth when no earlier notice is waiting. Other rewards retain their order and reading times (950 ms resource amounts, 1,150 ms ordinary milestone, 1,650 ms Full Bloom). Duplicate committed IDs cannot replay feedback; remount and collapse preserve the active timer and pending queue.

Previously the compact path depended on broader display work, expanded reward timing, and an opacity entrance. Full session-summary reduction also grew with session history. The footer now derives ordinary-answer totals incrementally, rebuilding after reversals/recovery, and secondary compact refreshes are coalesced. The earlier reward-feed pagination fix remains included. Reward values, durable commits, ledger schema, and sync boundaries are unchanged.

## Exact package

`dist/anki_garden-compact-responsive.ankiaddon`

SHA256: `bae202f7bd43d86d4b9a22f6d4c09514678b9592945d2f6d5345392dccf9e5d1`

Five runtime files differ from the previously installed latency fix. The scoped archive excludes unrelated concurrent dashboard, caption, footer-spacing, and widget-layout edits in the checkout. Packaging selects only the owned widget methods over the installed baseline. Version metadata remains 2.2.0; byte parity, not the version string, identifies this fix.

## Validation

The final exact-archive native run used a disposable sync-disabled Anki 26.8.1 profile, 5,000 seeded session-history entries, Home Screen Dashboard and Progress Bar Reforged, and original card templates. The test window remained on top; the probe asserted compact mode. All isolation gates passed. It completed 24 answer actions, with no recorded errors and clean exit. Source collection media were not copied, so this is not a complete heavy-media comparison.

Native visible-label paint timings:

| Measurement | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Answer to ordinary/combined Growth paint, excluding prior reward holds | 21 | 28.96 ms | 32.13 ms | 36.54 ms |
| Feedback render to visible label paint | 29 | 13.93 ms | 16.77 ms | 16.85 ms |
| Answer to next-card frame | 24 | 63.72 ms | 78.07 ms | 80.65 ms |

Growth after Coins took approximately 958 ms; Growth after milestone plus Coins took approximately 2.11 seconds. These are the retained reading holds. A prior native burst run demonstrated two pending gains combined into +24 Growth. Paint measurements come from visible Qt label paint events, not invocation of the render function. Main-window screenshots did not capture the separate floating HUD and are not visual acceptance evidence.

A preliminary installed-baseline native run recorded seven Growth paints with median 216.5 ms, but profiling and incomplete exposure make it unsuitable for a matched p95 comparison. The isolated reducer benchmark showed baseline accept-plus-footer median growing from 0.058 ms at zero history to 5.277 ms at 5,000; the candidate stayed near 0.015 ms. The full matched short/long stability and next-card regression criteria remain unproven. Testing stopped after the successful final native check at the user's request to stop once fixed.

176 focused source tests passed during implementation, including session totals/reversals/recovery, reviewer and sync/history paths. Eleven Qt layout tests passed at the earlier source snapshot. The final archive passes both compact sequencing variants (animation enabled/disabled). Later unrelated caption/spacing assertions do not pass against this scoped package; the caption failure also reproduces against the baseline. They were not included or represented as passing final-package tests. `git diff --check` passes.

Evidence and scoped build scripts: `build/performance/compact-responsive-20260910/`, including `package.json`, `session-benchmark.json`, and `final-native/{probe,trace,exit}.json`.

## Installation

The normal installation currently matches the previous latency-fix archive in all payload files. Installation is prepared and will back up the five replaced files, reject unexpected installed-file drift, require Anki to be closed, and verify every payload file against the candidate afterward. Normal Anki was still running at the end of native validation. A reopened, user-driven review remains the final check of the reported experience.
