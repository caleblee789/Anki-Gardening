# Deletion recovery verification — 2026-09-08

Implemented automatic persistence of progress and settings in
`<Anki base>/anki-garden-data`, preserving the existing shared garden across
profiles in that base. Migration uses a read-only SQLite online copy (including
committed WAL), stages settings and database together, validates the staged
database, and publishes under a crash-released OS lock. Existing durable data
always wins. Invalid or unsupported legacy JSON now stops without resetting.

## Focused checks

207 tests passed across persistence, configuration, storage migration, reward
state, reward ledger, startup/home integration, and settings overflow checks.
New persistence coverage includes reinstall, stale installed data, committed WAL,
legacy JSON, concurrent initialization, failed publication/retry, settings write
failure, malformed/unsupported data, profile reopening, and independent bases.
Existing corruption tests were updated to require preservation without reset.

## Native acceptance

Anki 26.8.1 on macOS, disposable base `/private/tmp/anki-release-qa.ehxp1dl3`,
profile `Codex QA Garden Persistence 20260908`, instance-key fingerprint
`36b3518db494`. Both launches verified process/base/profile/window identity,
package bytes, disconnected sync, and disabled automatic/media sync before test
actions. Existing instances were excluded; normal profiles were not used.

- Completed onboarding, placed/nurtured a rose, answered four actual Anki reviews,
  bought fertilizer, verified duplicate purchase idempotency, moved the plant to
  the second bed, and changed settings.
- Closed the disposable app and deleted its entire installed Garden directory.
  Hashes proved all durable files were unchanged by deletion.
- Reinstalled and verified restored plants, balance, purchase records, placement,
  review totals, onboarding and settings. Reconciliation produced no duplicate
  rewards. A fifth real review and another settings change saved successfully.
- Inspected the recovery notice in the Settings Support section. Closed the
  disposable instance and read its stopped database to verify the fifth review,
  plants, balance and settings remained saved. SQLite integrity returned `ok`.

The initial package was `c55134b5c09083a1e500500574191cc7ea58adc319ca2db63157875e58a61150`.
Before reinstall, the notice was moved out of the Artwork check disclosure into
the visible Support section. Final package:
`5387884c326a536730d8fdaef3e212a036cc388d45b4fc49002b7acd9e6ef1b7`.
Final source/package parity passed. Evidence, command results, screenshots,
deletion hashes and the candidate archive are in `build/persistence-20260908/`.

Windows/Linux native acceptance and public publication were not performed.
This verifies local deletion recovery, not device-loss recovery or tamper-proof
progress. Unrelated pre-existing dashboard and scene edits were retained.

## Final review and lifecycle correction

Final review found and fixed a cancelled-close defect: Anki emits
`profile_will_close` before asking dialogs to close, so cancelling could leave
Garden paused with its database closed. Cleanup now runs after the main window's
actual `_unloadProfile` completes. Supported Anki versions have no public
`profile_did_close` hook; the wrapper preserves the original method's arguments,
return value and exception behavior. Repeated hook setup remains idempotent.

The expanded focused suite passed **290 tests**, including a regression check
for cancelled unload, runtime reconciliation, sync reward canonicalization and
transaction integrity. Final source/package parity and whitespace checks passed.
The final candidate supersedes the earlier archive above:
`ee86f6388778beaa6f752d3b72b10f15754720ed9ecbf2cb522cc533aebedbbf`.

Native follow-up uses the same verified disposable base, with sync disconnected.
The clean results are under `build/persistence-final-checks-20260908/verified/`:
cancelled unload retains writable progress/settings; completed unload closes the
database/runtime; reopening preserves the shared state object and plants; an
actual review after reopening is rewarded once and saved with valid integrity.
The first follow-up harness run reused a timer after profile reopening and
re-entered a command; it is retained for diagnosis and excluded from the clean
acceptance results. The disposable helper was corrected before rerunning.
