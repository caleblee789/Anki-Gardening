# AnkiHub full-upload reward preservation — 2026-09-09

**Result: fixed and verified on the frozen candidate, including a real AnkiHub-triggered upload.** Five pending eligible reviews earned 50 Growth and 4 Coins after upload. Repeat sync and restart did not duplicate rewards. This resolves the scoped upload issue, not the other release gates.

## Change

Garden now identifies Anki's `aqt.sync.full_upload` through an idempotent wrapper that preserves the original call and wrapper chain. A window-scoped marker exists only during that call; Garden's synchronous temporary-close hook captures the upload classification for the ensuing asynchronous lifecycle.

Confirmed uploads suspend and invalidate background readers without consuming pending history as a replacement baseline. Reopening retains any active sync suspension; completion resumes ordinary reward reconciliation. Upload recovery does not create a downloaded-study receipt or dismiss an existing pending receipt. The fallback detector path follows the same distinction. Early completion, synchronous failure before database closure, repeated callbacks, and profile closure are handled explicitly.

Downloads and unclassified temporary closures retain the existing conservative replacement behavior. Reward amounts, progression rules, storage schemas, AnkiHub source, and public APIs are unchanged. There is no retrospective backfill of previously consumed history.

Only `ankigarden/addon.py`, `ankigarden/runtime.py`, and the existing startup/lifecycle and history-index test files were modified for this fix. Pre-existing changes were preserved. The task-specific diff is retained in the evidence directory.

## Verification

- **181 passed** across the existing startup/lifecycle, history-index, sync detector/processor/presenter, session integration, canonicalization, and package suites. Existing fixtures were extended; no new test file was added.
- The five-review reproduction still loses all five rewards through the old replacement path, including retry. Normal upload reconciliation credits all five once.
- Coverage includes pending answers with and without deferred-local metadata, recovered-result attribution, existing full-download baseline protection, duplicate callbacks, early completion, profile cleanup, failed upload initiation, and wrapper argument/exception preservation in both wrapper orders.
- **Anki 25.07:** its real `full_upload` function and real collection close/reopen passed success, failure, and cancellation cases with controlled network transport. This was an offscreen library/runtime check, not the bundled application or a live network test on 25.07.
- `git diff --check` passed. All 268 installed production payloads matched the frozen archive.

## Actual AnkiHub upload

The native run used macOS, Anki 26.08.1, AnkiHub 2026-08-27.1, and a fresh disposable profile, `Codex QA AnkiHub Upload 20260909`. Process, window, filesystem, collection path, and sync identity were checked. The user signed into AnkiHub themselves; AnkiWeb used the previously identified dedicated test account. The normal profile was not modified.

The installed AnkiHub integration downloaded subscribed decks through its normal UI. Because initial deck installation did not itself require full upload, a local-only field-order mismatch was saved in the disposable BLS/ACLS note type. After that fixture was synced to the test AnkiWeb account, AnkiHub downloaded the authoritative note type and displayed its normal **Some changes require a full sync** dialog. Accepting that repair triggered its automatic full upload. The log and lifecycle observer independently recorded the AnkiHub trigger and `replacement: false`.

A QA observer invoked Anki's native Grade Now operation for five disposable cards at the pre-close hook, while Garden reconciliation was suspended and before Anki closed/uploaded the collection. These reviews had no deferred-local metadata. This deliberately arranged the race condition; it was not five manual reviewer clicks and did not mock the upload or the reward engine.

| State | Counted reviews | Plant Growth | Coins | Pending sync receipt |
|---|---:|---:|---:|---|
| Before the accepted upload | 5 | 100 | 51 | None |
| After reconciliation | 10 | 150 | 55 | None |
| After another actual sync | 10 | 150 | 55 | None |
| After process restart | 10 | 150 | 55 | None |

The accepted upload therefore credited **5 reviews, 50 Growth, and 4 Coins**. Repeat/restart comparisons also preserved Find state, supplies, processed review IDs, and plant state. The repaired field order matched its original server-defined order, and Garden's SQLite integrity check returned `ok`.

Automatic AnkiWeb sync and AnkiWeb media sync remained disabled throughout. AnkiHub media downloading initially began during deck installation, then was stopped and disabled through its supported environment flag before the accepted reward test. No shared-deck contributions were submitted.

## Evidence and qualifications

- [Frozen production candidate](../build/ankihub-upload-fix-20260909/candidate.ankiaddon)
- SHA-256: `2c7dabdaef330af33961a23981735d8e13182ace30c63ac35260082f635b977d`
- [Completion record](../build/ankihub-upload-fix-20260909/completion.json), [test output](../build/ankihub-upload-fix-20260909/final-tests.txt), and [native evidence](../build/ankihub-upload-fix-20260909/native-evidence/).

An earlier actual upload used a planted but not yet nurtured starter. It preserved review counts but could not establish progression-reward acceptance; those observations remain separate under `live-*`. The accepted, active-plant run is under `live2-*`. Other retained setup failures include an unsaved field-order fixture, a helper import-name mismatch, minimum-version translation/exception-constructor setup, an early readback while sync was running, and a corrected Growth unit-scale assertion. None are counted as passing product checks. Intermittent computer-use capture errors were followed by fresh window-state verification.

Concurrent work changed `ui/scene.py`, `ui/welcome.py`, and `ui/welcome_animation.py` after the candidate was frozen. This native evidence applies to the linked archive; it is not acceptance of those later changes. The upload implementation itself remained byte-identical to the tested candidate. The root distribution archive was not replaced, and nothing was committed or published by this task.
