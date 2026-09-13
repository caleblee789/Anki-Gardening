The Garden update is installed. It fixes a reproduced cause of the consistent per-card delay and restores the requested Growth animations. Strict latency acceptance is incomplete: the expanded view and next-card timing targets were missed in the larger add-on comparison. The user's next normal restart and review remains the live confirmation.

**Identified cause.** `_proven_local_answer()` rejected the fast path whenever *any* outstanding reanswer/Undo record existed. Consequently, an unrelated card's perfectly ordinary answer invalidated verified history and entered deferred reconciliation. Unresolved Undo records can remain across sessions. A read-only inspection found 33 such records in the installed Garden database, which contained 327,675 historical answer lineages. The live collection was not opened for testing.

A disposable reproduction with an unrelated pending Undo deferred all 24 answers. With 327,000 synthetic historical reviews, the baseline repeatedly reread history. In the 40,080-card/200-background-deck fixture, it read 3,597,097 history rows over the run; median recorded reconciliation duration was 1,111.805 ms, including startup/fixture samples. Concentrating the same history on 80 cards produced a 5,520.786 ms median. Initial history verification is deliberately retained; it is distinct from normal reviewing.

The fix permits the proven local path when pending Undo records belong to other cards. Same-card reanswers, malformed identities, and revoked verification still fail closed. Sync, import, actual Undo, and ambiguous append checks remain unchanged. The final archive deferred zero of 24 ordinary answers in both large-history fixtures. Its 327,000 history reads occurred during initial fixture verification, with no additional full-history reads during reviewing.

**Animation changes.** One internal `GrowthCountUp` helper uses 600 ms OutCubic counting in compact +Growth, expanded This session Growth, and Recent rewards Card Growth. Session totals animate from the displayed amount. New amount frames begin at zero; combined amounts retarget from the current display. Canonical committed values remain separate from animation values. Duplicate deliveries and unchanged refreshes leave active counts alone. Remount snapshots preserve elapsed animation time and remaining compact holds. Reduced motion and the Undo boundary settle transient counting at committed values; authoritative total decreases apply immediately. Other rewards still precede compact Growth, with 950/1,150/1,650 ms holds. Existing art, dimensions, pulses, combined Growth, and feed pagination remain intact.

The opt-in timing recorder now retains bounded action/commit associations across asynchronous reconciliation and paint callbacks. It remains disabled by default and records no card contents.

**Verification.** All automated reviews used disposable, sync-disabled profiles in the installed Anki 26.08.1, with synthetic cards, unique instance keys, isolated preferences/cache/add-on data, and process/window/filesystem/sync gates. Existing live windows were excluded. The relevant copied add-ons were Progress Bar Reforged, FSRS Helper, and Home Screen Dashboard. Credentials were excluded and Python external account connections blocked. No other add-on code was changed. Authenticated AMBOSS/AnkiHub paths and complex user card templates were not exercised; native cards used the Basic template.

The focused Python pass passed 131 tests across reviewer HUD, session integration/recovery, reconciliation/Undo, summary totals/reversals, and performance recording. Seven real-Qt scenarios passed, including first-serviced paint before secondary work, intermediate/exact final counts, rapid combined gains, duplicates, refreshes, remounts, reduced motion, and Undo settling. Existing checkpoint/Full Bloom and 950/1,150/1,650 ms sequencing cases were reused.

Headless paint-path benchmarks used histories of 0, 500, and 5,000 session answers. Expanded p95 was 3.760/3.306/3.281 ms; compact p95 was 0.827/0.939/0.847 ms. These are component timings and do not establish native or live responsiveness.

**Native measurements against the exact archive.** Values below are p95 milliseconds. Profiled first answers and designated frame-capture answers are excluded. Compact ordinary onset excludes explicit reward/queue holds; onset measures the new Growth frame, whose number then counts upward. Expanded onset measures the first painted numerical change, not the final value at 600 ms.

| Scenario | Compact ordinary onset | Compact eligible-to-paint | Expanded numerical onset | Next card, compact | Next card, expanded |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed baseline, Garden alone | 18.350 | 5.499 | 18.225 | 69.464 | 46.217 |
| Final archive, Garden alone | 18.069 | 5.809 | 98.068 | 55.066 | 90.756 |
| Installed baseline, large fixture + copied add-ons + pending Undo | 752.077* | 4.764* | Not independently correlated | 88.022 | 84.130 |
| Final archive, same large fixture | 94.205 | 39.688 | 200.086 | 136.580 | 160.797 |

*The baseline's deferred recovery combined multiple answers before display. Only four compact answers could be individually correlated through first paint; this is not a complete per-answer acceptance distribution. The final ordinary compact sample has seven answers; expanded has eleven. The direct 24/24-to-0/24 deferral comparison is the stronger evidence for the identified cause.

Compact eligible-to-paint met 50 ms in these runs. Both views met 100 ms onset with Garden alone. Expanded onset in the larger fixture missed 100 ms, and next-card p95 regression exceeded 10 ms. These targets are not reported as passing. Progress Bar Reforged's question callback reached 60.283 ms in that larger final run; Garden's collection-wide due calculation also remained measurable (35.749 ms p95). Those observations do not establish that either is the sole remaining cause of latency.

Intentional compact waits were recorded separately: the checkpoint plus Coin frame delayed Growth by about 2.09–2.11 seconds, and the next answer waited about 0.41–0.53 seconds behind it. Counting runs within the existing 950 ms Growth frame; 600 ms is animation duration, not an added delay before showing feedback.

Native widget-paint samples contain intermediate values on all three requested surfaces. The frame sequence shows expanded totals and combined Card Growth approaching and reaching their exact amounts. macOS window-server grabs returned no pixels in the later runs, so those images are explicitly named `widget-*` and are Qt widget-render captures from the visible isolated Anki window. They are not claimed as compositor screenshots or human live approval.

Raw run metadata, callback traces, profiles, headless results, and the timing reducer are under [the evidence directory](</Users/test/Documents/Anki Gardening.nosync/build/performance/hud-countup-20260910>). Run metadata retains each disposable base path. The useful final frame files are in `/private/tmp/anki-release-qa.luoi8zj0/` and the Garden-only run is `/private/tmp/anki-release-qa.p0wz9_te/`.

**Package and installation.** The scoped build overlays six files on the frozen installed baseline: `hooks/reviewer.py`, `performance.py`, `ui/collapsed_reward_feedback.py`, `ui/reviewer_hud_widget.py`, `ui/reward_feed.py`, and new `ui/growth_count_up.py`. Other installed layout changes and unrelated checkout edits were preserved. There is no reward-ledger or saved-state migration, economy change, or public release.

- Baseline SHA-256: `837194fb8e521c235260828b3b04a1af18892816d1daabff216f751972bd1861`.
- [Final archive](</Users/test/Documents/Anki Gardening.nosync/dist/anki_garden-hud-countup.ankiaddon>) SHA-256: `17db329253996b9c2dc5d739a3123113ae0d99a950dd98b8a982d3a552e1a21f`.
- Installation occurred only after the process gate confirmed Anki was closed. Anki was not closed or reopened automatically.
- Five replaced files were backed up outside the live profile at [the backup directory](</Users/test/Documents/Anki Gardening.nosync/build/performance/hud-countup-20260910/backups/20260910-201239>); the sixth file is new.
- All 271 managed installed files matched the archive. Hashes of 56 protected files—including collection databases, Garden saved data/settings, add-on configuration metadata, and shared preferences—were unchanged across installation. Other add-ons received no writes.
- [Installation record](</Users/test/Documents/Anki Gardening.nosync/build/performance/hud-countup-20260910/installation.json>) contains the exact parity and backup evidence.

The installed version label remains 2.2.0; archive hash and file parity identify this update precisely. The reproduced history-rescan bug is fixed in isolated testing. Resolution of the user's reported live delay is awaiting their next normal review.
