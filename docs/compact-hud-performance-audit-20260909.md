# Compact HUD answer-feedback audit — 2026-09-09

The compact HUD delayed committed Growth behind Coin and milestone messages. The correction changes presentation only: Growth enters the rail first, newly earned Growth merges into an active Growth frame or replaces an already displayed Coin frame, and compact progress no longer waits for the expanded dock's 220 ms reveal delay. A milestone that is already visible retains its reading time. Coin totals, original reward history, and the expanded reward lifecycle remain intact.

## Measured result

Matched isolated Anki 26.08.1 runs used the same copied collection and synthetic Garden state, with 12 Good answers per run. The baseline and final archives differ in exactly `ui/collapsed_reward_feedback.py` and `ui/reviewer_hud_widget.py`.

| Measurement | Baseline | Final |
| --- | ---: | ---: |
| Growth after an answer also awarding Coins | 972 ms | 42 ms |
| Growth on the first milestone answer | 2,172 ms | 53 ms |
| Next answer while previous resource feedback remains | 521 ms | 42 ms |
| Longest measured Growth delivery | 2,172 ms | 63 ms |
| Next-card frame, median (12 answers) | 65.3 ms | 65.6 ms |
| Garden answer callback, median / maximum | 18.9 / 24.8 ms | 24.1 / 31.7 ms |

The final run delivered 11 Growth-bearing results in 28–63 ms (median 40.2 ms). The baseline's last Growth frame had not appeared before its observation window ended; its aggregate includes 10 deliveries. The comparison fixes delayed feedback, not median next-card rendering or every component's execution time. The unchanged 140 ms crossfade still animates the resource appearance.

These timings start at Anki's native Good handler and end when the compact feedback renderer is invoked. They are not physical-input-to-monitor measurements. The next-card measurements use a WebEngine animation-frame acknowledgement. Profiling was enabled equally for the matched runs. Card HTML was simplified and collection media were not copied; this does not measure other installed add-ons or arbitrary media-heavy cards.

Final balances matched exactly: 1,790 Coins, 40,800 plant Growth units, and 326,565 eligible lifetime answers. Both runs completed with no probe errors and passed ledger integrity checks. There was one background history verification per run, with no repeat full-history scan during the answer sequence. Cold history verification and an initial HUD mount remain separate startup costs; this is not a universal latency guarantee.

## Verification

- 121 existing focused tests passed: reviewer HUD, session integration, runtime performance, history index, reward bundle projection, and sync processor.
- 11 native Qt layout/interaction checks passed. The added behavioral case runs with motion enabled and disabled, verifies immediate compact progress, Growth-before-Coins and Growth-before-milestone order, consecutive-answer coalescing, and preservation of every queued resource amount.
- `git diff --check` passed.
- Two additional four-answer native checks confirmed the Growth label and row were visible at full opacity 180 ms after delivery; direct feedback captures paint `+12` correctly. Whole-HUD widget grabs intermittently omit animated child content. The attempted screen capture showed an occluding application and was discarded, so physical monitor-paint acceptance is not claimed.
- All live runs used fresh disposable profiles, disconnected sync, unique instance keys, and process/window/filesystem/sync gates. They closed after testing. The normal profile was not modified.
- An initial unused legacy database fixture was incompatible with the current ledger schema; that attempt stopped before review interaction. The successful comparisons use the same supported JSON fixture and a fresh database.

## Evidence and scope

[Machine-readable results](../build/performance/compact-latency-20260909/results.json), native probe outputs, profiles, captures, launch metadata, frozen before-files, and all compared archives are retained under `build/performance/compact-latency-20260909/`.

The tested production-mode archive is [final.ankiaddon](../build/performance/compact-latency-20260909/final.ankiaddon), SHA-256 `8ff6ff10c2bc192f799f174f0f8ee9770309a60f82eed9168da8949bbfd846e2`. It is a frozen performance candidate, not a public release. Other work continued in this dirty checkout during the audit; subsequent changes in `addon.py` and `runtime.py` are outside this native snapshot. No commit, normal-profile installation, or public upload was performed.
