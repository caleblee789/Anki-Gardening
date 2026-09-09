# Anki Garden / FSRS Helper compatibility — 2026-09-09

The tested Garden candidate correctly preserved earned rewards and prevented duplicate rewards across the grading, scheduling, history-editing, and lifecycle cases below. One Garden presentation defect was fixed and retested. AJT has a reproducible large-batch failure without Garden installed. This is a qualified compatibility result, not a claim that every combination is bug-free.

The existing distribution archive and normal Anki profile were preserved. Nothing was published or installed into the normal profile.

## Candidate and environment

| Item | Recorded value |
|---|---|
| Garden | 2.2.0 candidate, including the working tree's existing changes |
| Starting commit | `38a7478075c3a1a5e22fc330e1b3534100361b64` |
| Anki | 26.08.1 (`39e4b0b4`) |
| Runtime | Python 3.13.14; Qt / PyQt 6.11.0 |
| Platform | macOS 26.6.2, ARM64 |
| FSRS Helper | `759844606`; installed modification timestamp `1778741397` (2026-05-14) |
| AJT Card Management | `1021636467`; installed modification timestamp `1771706674` (2026-02-21) |
| Initial candidate SHA-256 | `21d8d2cafc54fc58076f86f5913400a4a3fb37bbed7fdc5b8fa29f8ce51b208f` |
| Fixed candidate SHA-256 | `a620e19906adc0a17c63d78156dfa8a25459a8bb6157f4a85274c9d839307f9e` |
| Preserved distribution SHA-256 | `05b807b7ce23550001b8dc250325d314c0f3ce0d54a0bfd19b4201cb239e4a0d` |

Neither companion declares a useful version string in its installed metadata. Their exact source-file hashes are retained in `companions.json`. All 268 final package entries matched the frozen candidate source and the disposable installation. The final package is 96,607,354 bytes. Only `ankigarden/addon.py` and `ankigarden/runtime.py` changed from the frozen production source during this work.

Artifacts: [complete evidence directory](</Users/test/Documents/Anki Gardening.nosync/build/fsrs-helper-compatibility-20260909-1942>), [final candidate](</Users/test/Documents/Anki Gardening.nosync/build/fsrs-helper-compatibility-20260909-1942/candidate-final.ankiaddon>).

## Method and isolation

Two disposable bases were used: `/private/tmp/anki-release-qa.vmco2vun` with Garden, and `/private/tmp/anki-release-qa.cai81ee4` without Garden. Both had the same installed FSRS Helper and AJT source. Profile names, process IDs, collection paths, window identities, unique Anki instance keys, and disconnected sync settings were checked. Automatic sync and media sync were disabled. Separate app copies gave the test windows distinct application identities. The normal Anki process remained running; test processes were closed afterward.

The fixture initially contained 1,164 synthetic cards and 3,348 older review records. Later sibling cases added 15 actual Cloze siblings. The control collection was copied from a consistent synthetic baseline. Thirteen paired operations produced zero differences in the compared scheduling fields and normalized review content with and without Garden. Review IDs and elapsed answer timing were excluded from that comparison.

Tests ran inside the actual Anki application. They invoked Anki's real native grading operation and installed AJT / FSRS entrypoints, with real collection transactions, callbacks, undo, and Garden persistence. Helper input dialogs received predetermined fixture values. AJT selection tests used its actual selection controller with a minimal Browser-compatible parent. Reviewer and sync ordering tests invoked public hooks around real committed synthetic answers. They did not contact AnkiWeb.

Home, Garden, and Activity were rendered and inspected through native widget captures. Browser was opened, closed, and reopened through Anki's own dialog manager. Pointer/keyboard execution of every menu command was not verified: accessibility inspection earlier triggered a native Qt crash. The operation-level results should not be described as manual menu acceptance.

## Coverage and results

The evidence contains 89 main scenario observations, including failed and superseded attempts. Eleven targeted final-package regression cases passed, followed by an additional explicit Load Balance case and native window lifecycle checks. The wider matrix ran on the initial candidate; affected behavior was rerun after the two-file presentation fix.

| Area | Result and coverage |
|---|---|
| Native and AJT grading | Passed all four ratings, individually and in mixed batches covering new, learning, relearning, overdue, due, and future review cards. Existing reward eligibility and amounts were preserved. This was a representative matrix, not every rating × state × batch-size permutation. |
| Selection boundaries | Empty native/AJT selections, AJT unavailable-only and mixed selections, and AJT rejection of 31 cards passed. AJT skipped suspended/buried cards. Native Anki actually answered the tested suspended/buried cards; Garden counted those committed answers. |
| Large grading batches | Native 30-card grading passed. AJT 28 passed; AJT 29 and 30 failed independently of Garden. See the failure below. |
| Undo and repetition | Native batches and AJT 28-card batches passed undo, redo, and different-rating re-answer checks. Earned rewards were retained; re-answering did not duplicate them. Undo before reconciliation and a clean answer-during-verification retest passed. |
| Rescheduling | Selected, deck-wide, collection-wide, recent-history, repeated rescheduling, and undo passed without answer rewards or supply consumption. An explicit 1,000-card selection changed all 1,000 card records on the initial candidate. The final repeat selected 1,000 and changed 872. |
| Postpone / Advance | Actual review workload moved from 0 to 12 and back to 0; Garden's due counts matched the authoritative query. No answer rewards were created. |
| Load Balance / Easy Days / Break / Flatten | Passed installed helper operations, including weekly and specific easy dates, Schedule a Break, and Flatten. Load Balance was already enabled and was explicitly confirmed and rerun on the final candidate. |
| Siblings and hook order | Disperse Siblings and automatic dispersal during simulated reviewer callbacks passed in both Garden-first and Helper-first order. |
| History changes | Remedy Hard Misuse, its undo, clear custom data, creation/repetition/removal of manual scheduling records, and subsequent answers passed. Prior rewards remained intact. |
| Combined operations | Grade then reschedule, reschedule then answer, active fertilizer, filtered decks with rescheduling on/off, and multiple decks/presets passed. Undo/re-answer did not consume supplies twice. |
| False completion prevention | Moving all remaining due cards out of today produced zero due cards without awarding completion Coins, Finds, Growth, or consuming supplies. Existing conservative completion-status behavior is described below. |
| Simulated sync | Automatic rescheduling/dispersal, incoming synthetic reviews, reversed callback order, and repeated completion callbacks passed exactly-once reward checks. The final summary counts were 2, then 5 after three more simulated incoming answers; later browser answers and repeated sync callbacks did not inflate them. |
| Lifecycle | Home/Garden/Activity refresh, Browser close/reopen, operation settling, and restart passed through native application calls. Restart preserved 240 counted answers, 72 Coins, card data, and review history, with no recurring sync popup. |

Each main case retains before/after card rows, review rows, full Garden state, reward deltas, and settling results. An additional comparison of 54 clean no-reward-change observations checked Finds, inventories, reward-event keys, environment completion claims, and pity counters; no differences were found. The approximately one-second scenario timings include a deliberate minimum wait and are not performance benchmarks.

## Fixed Garden defect: browser grades shown as sync rewards

Reproduction on the initial package:

1. Start the disconnected synthetic profile and let history verification finish.
2. Grade a card using the native Browser grading operation, without starting sync.
3. Let Garden reconcile the new review.
4. A “Rewards after syncing” popup appears and can accumulate subsequent browser grades.

The isolated reproduction increased counted answers from 201 to 202 while sync was inactive and displayed a one-answer sync summary. Generic reconciliation used the sync summary preference as its only presentation gate. View refreshes could also replace the recorded reconciliation reason, so checking that reason alone would be unreliable.

The coordinator now retains an explicit sync-completion signal until reconciliation settles. Only reconciliation associated with that signal can present a sync reward summary. Ordinary browser grading still earns its existing rewards. Helper operations and Home refreshes cannot erase a legitimate pending sync signal; completion and profile close clear it. No reward amounts, scheduler behavior, saved-state schema, or migration changed.

The existing background-reconciliation regression test was extended. No new test file was added. Final validation passed:

```text
.venv/bin/python -m pytest tests/test_history_index.py tests/test_addon_startup_and_home.py tests/test_sync_reward_processor.py tests/test_sync_reward_presenter.py tests/test_sync_reward_canonicalization.py tests/test_sync_review_detector.py -q
124 passed in 9.01s
git diff --check: passed
```

The final native cases verified no summary for native/AJT browser grades, correct summaries after simulated sync in both hook orders, no inflation from subsequent grades or rescheduling, no duplicate summary on repeated callbacks, native 30-card undo/redo, and a 1,000-card reschedule. Restart verification passed. Evidence: `wrong-sync-summary-before-fix.json`, matching screenshot, `fixed-summary-checks.json`, and `final-restart-verification.json`.

## Remaining AJT failure

On the installed AJT version, grading 29 or 30 eligible cards raises `target undo op not found` after committing the review rows. The same failure occurs in the control profile with Garden absent. A 28-card AJT batch succeeds. AJT's custom undo entry appears to be evicted by its own per-card operations before the final undo merge.

This is not a rejected operation that leaves all cards unchanged: reviews have already been written. The failed operation does not emit the normal successful operation callback, so Garden catches up after a later successful operation or restart. Recovery retained the committed rewards without duplication. Use Anki's native Grade Now for large batches; its tested 30-card batch and undo/redo succeeded.

The two failed 30-card attempts and four following contaminated observations remain in the raw evidence. They are not passes. The affected undo/re-answer and pending-verification cases were repeated cleanly using the working 28-card AJT batch. Independent control evidence is in `control/comparison/ajt-batch-{28,29,30}-without-garden.json`. Installed AJT source was not modified.

## Remaining display behavior and verification limits

- Activity still labels reconciled browser answers “Synced study.” This is a cosmetic classification in the existing history path; it does not change totals, rewards, or the fixed popup behavior. It was left unchanged under the instruction not to fix immaterial issues.
- After scheduling removes required cards, the existing completion safeguard can show “Status unavailable” with `obligation_disappearance_unverified`, even though current due counts correctly reach zero. The combined fixture retained that status through restart. It withholds an unverified completion reward. This behavior was documented rather than changing the agreed reward rules.
- Opening Garden while the final verification was pending logged a caught welcome-acknowledgement save refusal (“Garden is still updating”). Once verification settled, the welcome could be dismissed and the unchanged reward state persisted. No normal grading operation failed; this transient refusal was left unchanged.
- Native Qt accessibility inspection crashed the disposable app twice. No Garden attribution was established. Per the user's direction, the native crash was not pursued. Later native window operations completed without that accessibility inspection.
- The reported duplicate `revlog.id` error came from the synthetic sibling fixture, not a user grading/rescheduling action. The fixture was corrected to allocate unique IDs. Evidence serialization and a check of an already-deleted Browser wrapper were also corrected in the disposable harness. These are not product failures.
- Garden's durable ledger and history-index SQLite integrity checks returned `ok`. Generic SQLite could not run a full Anki collection integrity check because Anki's `unicase` collation was unavailable; native restart and exact card/review persistence were verified instead.
- Actual AnkiWeb synchronization, other operating systems/Anki versions, every possible add-on load order, manual execution of every menu/dialog, long-term performance, and publication remain unverified or outside this run.

## Evidence index

All files below are in the linked evidence directory:

| Artifact | Purpose |
|---|---|
| `initial-manifest.json`, `companions.json` | Frozen starting source, dirty-tree status, package and installed companion hashes |
| `final-package-verification.json`, `final-integrity.json` | Final package parity, unchanged distribution/installed companion source, integrity and process closure |
| `case-summary.json`, `cases/` | Raw observations and detailed before/after records, including unsuccessful attempts |
| `control-comparison.json`, `control/comparison/` | Thirteen paired operations and independent AJT failure reproduction |
| `reward-invariants.json` | Additional Finds, inventory, and completion-reward comparisons |
| `fixed-summary-checks.json` | Final popup and exactly-once summary assertions |
| `final-restart-verification.json`, `ui-lifecycle-verification.json` | Restart and native window lifecycle results |
| `fixed-final-home.png`, `fixed-garden-settled.png`, `fixed-activity-refreshed.png`, `fixed-browser-reopened.png` | Final native rendered surfaces |
| `commands/`, `responses/` | Reproduction commands, results, and per-command profile/process identity gates |

