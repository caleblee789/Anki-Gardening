# Performance overhaul — 6 September 2026

This change removes full-history reconciliation from ordinary navigation and
Garden mutations, shows the saved Garden while startup verification runs, and
keeps reward writes durable and ordered. It does not change reward rates,
eligibility, artwork resolution, or Anki's scheduling decisions.

## Behavior

“Your Anki Garden is still updating” appears in light grey directly under the
Garden title while history is being verified after startup, sync, undo, an
unknown card operation, or a scheduler
boundary change. The saved Garden remains visible. Anki can commit reviews
during verification; Garden journals their local session attribution and
reconciles them afterward. Progress-dependent Garden changes wait for verified
state. The notice clears after reconciliation succeeds.

Routine Home, Decks, Overview, and Garden navigation reuse verified state.
Selecting a deck, changing note text, or changing the Garden does not by itself
rescan review history. The first history-index build is slower than subsequent
verification, but its collection reads and computation run outside UI callbacks.

## Measured native behavior

The final production candidate completed 12 review answers and Decks transitions,
12 Home refreshes after Garden changes, and eight dashboard refreshes. The
comparison below uses the same copied collection and initial Garden fixture.

| Operation | Original build | Performance candidate |
| --- | ---: | ---: |
| First UI callback after probe add-on load | 8,126 ms | 666 ms |
| Home refresh after Garden change, median | 4,160 ms (12 samples) | 4.81 ms (12 samples) |
| Decks after review, median | 4,155 ms (1 sample) | 14.76 ms (12 samples) |
| Garden answer callback, median | 46.26 ms (2 samples) | 11.38 ms (12 samples) |
| Garden answer callback, slowest tested | 48.52 ms | 21.36 ms |
| Dashboard refresh after change, median | 20.21 ms (8 samples) | 9.40 ms (8 samples) |

The actual Home-button click opened the saved Garden in 674 ms while background
verification was still pending. Cold verification took 14.13 seconds; restart
verification took 3.00 seconds in the background. Each launch performed one
content scan, with no repeated full-history reads during the 12 local answers
and navigation sequence. Restart preserved exactly 12,000 Growth units, 1,790
Coins, and 326,543 eligible lifetime answers, with zero probe errors and clean
exits. The baseline was partly overlapped by user interaction, so its limited
sample counts and timing variability must be retained when interpreting these
measurements.

HUD rendering still reached 95.8 ms, and the event-loop monitor recorded an
883 ms maximum delay during the complete cold run. The changes substantially
reduce recurring stalls; they do not establish a universal 50 ms foreground
latency guarantee.

## Implementation

- `runtime.py` coordinates serialized, paged Anki `QueryOp` reads and separate
  background computation. Generation checks cancel stale results after sync,
  undo, collection replacement, profile close, and changed day boundaries.
  Main-thread alias and reward commits use small adaptive batches.
- `history_index.py` stores raw review identities and daily sufficient
  statistics in a disposable SQLite index. Startup and uncertain mutations
  compare every eligible source row, including older edits, insertions, and
  deletions. This is not a maximum-ID-only validity check. The live indexed
  path does not have the old one-million-row history ceiling.
- Historical local day mapping caches ordinary day intervals. Ambiguous and
  nonexistent daylight-saving cutoffs retain the original wall-clock rule.
- The reward ledger streams newly committed economy events into versioned
  projections. Checkpoints and bounded Garden state commit atomically. A
  background audit recomputes projections from a consistent ledger copy at
  startup; direct storage callers retain synchronous validation. The existing
  full reducers remain correctness references.
- Deferred-review attribution and undo hints are journaled durably. Batched
  replay uses the original stable answer-lineage algorithm and exact per-day
  answer ordinals. Undo/re-answer cannot manufacture a second reward.
- One exact due snapshot is shared until a scheduler mutation, learning due
  time, or cutoff invalidates it. Committed-card evidence stays scoped to the
  answer that supplied it.
- Garden refreshes patch Garden-owned Home DOM instead of resetting all of
  Anki. Hidden pages refresh when needed. HUD updates consume committed results
  once, coalesce repeated callbacks, and preserve in-flight feedback when their
  projection has not changed.
- Optional timing includes bounded samples, total operation counts, lifetime
  maximum stalls, query-page timing, and the number of history rows read.
  Diagnostics are disabled by default.

## Evidence and reproducibility

Evidence root: `build/performance/overhaul-20260906-191407/`.
The baseline archive, source manifests, initial dirty diff, candidate source
snapshots, native probe drivers, and JSON results are preserved there.
Concurrent UI/artwork work in the checkout was preserved; the entire working
tree diff should not be attributed to this performance task.

The final performance evidence uses `candidate-performance-validated-source`,
derived from the native-tested notice build with a final correction that excludes
future-dated history from the achievement high-water mark. Its source manifest
and provenance record identify every input. The installable evidence candidate
is `anki_garden_performance_candidate.ankiaddon` in the evidence root, SHA-256
`ca834812a4f34632e69ae619fe180160a48bca0b8129957958e638c89d0d8413`.

Activity history and Mastery availability were being changed concurrently in the
shared checkout. Those edits remain present there but are outside this frozen
performance candidate. A separate combined snapshot passed 275 checks and failed
four checks involving the new ledger schema and changed Mastery behavior; see
`combined-candidate-checks.log`. This task does not certify that evolving combined
feature build. All 279 of the same checks pass on the final performance candidate.

The native dataset is a consistent read-only SQLite backup of the collection
that was open during this task: 37,561 cards, 438,269 revlog rows, and 326,531
eligible answers. No normal-profile Garden database was available, so both
builds received the same established synthetic Garden fixture. The normal
collection and add-ons were not installed over or used for test writes.
Collection media were not copied; these measurements concern Garden callback
and navigation overhead, not full card-media loading time.

Each native run uses Anki 26.8.1, a distinct `/private/tmp/anki-release-qa.*`
profile, a unique single-instance key, disconnected sync, and process/window/
filesystem/sync gates before interaction. A Qt mouse event on the actual Home
button also exercises opening the Garden while startup verification is active.

The component benchmark is reproducible with:

```sh
.venv/bin/python scripts/benchmark_history.py --output /private/tmp/garden-benchmark-new
```

The default creates 1,000,001 eligible reviews spanning 300,000 card IDs.
`--collection /absolute/path/to/a/copy/collection.anki2` instead reads an existing
copy without writing to it. Use a fresh output directory for each run.

On the million-review fixture, the indexed summary median was 4.15 ms versus
2,206 ms for the unchanged full reducer; all semantic result fields matched.
Peak process RSS before materializing the full reference was about 86 MB,
versus 737 MB after materializing and analyzing that reference. These are
component-process figures, not whole-Anki memory measurements. Cold indexing
took 10.2 seconds and complete warm verification 5.0 seconds, in background-
compatible pages. On the copied real history, summary medians were 8.47 ms
versus 767 ms, with 6.37-second cold indexing and 3.18-second warm verification.

## Correctness checks

Existing reward, economy, achievement, migration, purchase, undo, sync, Home,
dashboard, HUD, session-summary, and capture-contract tests were reused.
New integration coverage compares full versus batched replay, exact balances,
Growth, lineages, durable restart, stale background completion, deferred
undo/re-answer, old source mutations, cache corruption, and DST mapping.

The broad run passed 1,700 tests, with 23 skipped and 835 deselected, and exposed
one stale artwork-count assertion after concurrent artwork additions. That
assertion was changed to validate required identities and resolution of every
catalog entry; its follow-up suite passed. Later focused suites cover the final
HUD and lifecycle changes. No additional tests mirror individual cache calls.

The final frozen performance candidate passed all 279 focused checks. The v29
representative preflight captured 22 states, and the final audit captured all
50 states on five sheets at 100 percent scale on the primary display. Shared
production/capture payloads matched, text-layout warnings and capture failures
were zero, and the native capture process closed cleanly. All five final sheets
were visually inspected. The validator retains one advisory for identical
Collection overview/species-details pixels; human visual release approval is
still required. An extended memory-leak soak was not run.

The linked handoff contains the complete package provenance, raw evidence,
contact sheets, archive, manifest, capture report, and known acceptance limits:
[performance evidence handoff](../build/performance/overhaul-20260906-191407/HANDOFF.md).

The optional exhaustive annual balance matrix was interrupted after more than
ten minutes and excluded from the broad rerun. Reward pacing was not changed by
this task. The separate pacing acceptance hold documented in
`uncapped-progression-implementation-20260906.md` remains separate from these
performance checks.

## Acceptance boundaries

Native timings and package-bound visual/restart results are recorded with their
candidate hashes in the evidence report. Startup first-tick timing begins at a
probe add-on loaded before Garden; it is not a measurement of every installed
add-on in the user's normal Anki profile. Callback timings are not equivalent
to WebEngine first-paint timings.

The first creation of the full Garden window still takes several hundred
milliseconds. Some HUD mount/render callbacks can exceed the proposed 50 ms
foreground target; the overhaul does not claim every target is met. No public
upload, normal-profile installation, human release approval, or Windows QA is
implied by the automated and isolated native results.
