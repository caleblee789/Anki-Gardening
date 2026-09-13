# HUD stopped updating after answers

## Confirmed cause

The installed `17db329253996b9c2dc5d739a3123113ae0d99a950dd98b8a982d3a552e1a21f`
archive matches all 271 managed live Garden files. Its reviewer hook supplied
only today's card history to the answer-identity reducer, alongside the card's
lifetime saved identity bindings. The reducer interpreted omitted older answers
as deleted answers and reused an older identity for the new answer. When that
identity had already earned a reward, duplicate protection suppressed the new
reward and its feedback. This is upstream of both HUD views and their animations.

The earlier synthetic latency fixture placed history before Garden activation;
those old identities were not consumed. It did not expose this regression.

## Change

Before assigning identities from a partial history window, check which saved
aliases still exist in Anki using batched, primary-key SELECT queries. Preserve
those lineages as present when finding genuine Undo/reanswer candidates. The
existing reducer still assigns fresh serials, preserves exact bindings, and
reuses genuinely deleted answer identities. The lookup uses Anki's authority
even when a disposable history index is stale or unavailable.

Only `storage.py` and `hooks/reviewer.py` differ from the installed baseline.
The package retains its existing 600 ms count-ups, combined Growth, reward
reading times, layout changes, and pagination. It changes neither reward values
nor saved-state schema. Previously misbound historical aliases are not rewritten:
they cannot safely be distinguished from legitimate restored Undo history.

## Verification

- Added one parameterized regression case using the real reward ledger and
  engine, with and without the history index. A previously rewarded card earns
  new Growth on the following day and reaches the HUD's accepted feedback queue.
  Duplicate callbacks and a genuine Undo/reanswer do not mint or replay rewards.
  Both variants failed before the fix and pass after it.
- 98 focused history, storage, reviewer, session-integration, and runtime checks
  passed. The new case was rerun after adding the explicit Undo assertion.
- Seven existing headless Qt checks passed, covering immediate committed
  feedback, count-ups, combined gains, reward order, refreshes, remounts, and
  reduced-motion/session behavior.
- Two short native Anki 26.8.1 runs used separate fresh, sync-disabled disposable
  profiles with synthetic cards and 80 previously consumed prior-day identities.
  Process, window, filesystem, and sync gates passed. Existing Anki processes
  were excluded; both test instances exited normally with no recorded errors.

| Exact archive | Accepted new answers | HUD updates |
| --- | ---: | ---: |
| Installed baseline | 0 / 8 | 0 / 8 |
| Fixed package | 8 / 8 | 8 / 8 |

Each native run included four compact and four expanded answers. With the fix,
ordinary compact Growth frames began at 12–17 ms in the two unqueued samples;
expanded totals first changed numerically at 37–44 ms. The first answer's Coins
frame intentionally preceded Growth by about 950 ms, and the following answer
combined its Growth into the active count-up. Intermediate numeric paints were
observed on all three requested surfaces. Session totals reached the exact
targets after the 600 ms animation. These are a small regression comparison,
not a p95 acceptance benchmark or confirmation of the user's live experience.

Offline identity-resolution p95 over 30 warm iterations was 0.008 / 1.062 /
12.014 ms for 0 / 500 / 5,000 historical aliases on the same card. This measures
only identity resolution, separately from native end-to-end feedback.

Evidence: `build/performance/hud-answer-identity-20260911/comparison.json`,
`identity-timings.json`, and the two run manifests. Native roots:
`/private/tmp/anki-release-qa.gst5uoj7` (baseline) and
`/private/tmp/anki-release-qa.fimuqv8o` (fixed).

## Package and installation

Archive: `dist/anki_garden-hud-answer-fix.ankiaddon`

SHA-256: `d2c16da504b6f474cfc6d23caea17a4c5ef52a0763b6765f1d75b0bc4916b998`

Built by overlaying only the two changed files on the verified installed
baseline. The exact archive above was used for the fixed native run.
Installed after the user closed live Anki. Only the two listed Garden code
files were replaced. All 271 managed installed files match the tested archive;
all 56 protected files retained their pre-install hashes. No live Anki process
was closed or reopened by the installer.

Backup: `/Users/test/Documents/Anki Gardening.nosync/build/performance/hud-answer-identity-20260911/backups/20260911-123332`.
Installation evidence: `build/performance/hud-answer-identity-20260911/installation.json`.
The next user-driven restart and review remain the live confirmation.
