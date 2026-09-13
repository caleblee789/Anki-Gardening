# Review engine bug fixes — 2026-09-12

Three confirmed defects were fixed and installed. Reward rules, combined Growth, reward ordering, count-up animations, and HUD layout are unchanged.

## Confirmed defects and changes

1. **A future-dated history cursor could block current-card feedback.** The local-answer proof used a persisted scalar cursor even when it pointed beyond today's scheduler boundary. The session filter could then reject an otherwise proven local answer. The local proof now uses today's processed history when that scalar is in the future, and the session filter accepts a uniquely proven local append. Ambiguous history still requires reconciliation; no persistent cursor or history is rewritten.
2. **A trailing duplicate could suppress the final due-card reward.** Batch processing released the previous accepted answer before determining whether the next payload was a duplicate. A duplicate at the end could leave no answer to receive the completion reward. The last accepted answer now remains pending until another answer is accepted or the batch finishes, preserving final reward attribution.
3. **Temporary read/save failures could lose local session attribution.** Identity lookup exceptions could escape the answer hook, while a save failure could later recover as unattributed history. These paths now preserve the deferred card and session context, invalidate verification, and recover through the existing reconciliation mechanism. Feedback remains tied to committed rewards and duplicate recovery is ignored.

## Verification

The original defects were reproduced with existing test fixtures before applying the fixes. Existing tests were extended where possible; one parameterized integration test covers the meaningful read/save recovery failure modes.

- Core engine, storage, reward ledger, history, reconciliation, Undo, and session tests: **397 passed**.
- Existing focused Qt HUD tests: **7 passed**, including feedback sequencing, committed-feedback paint, and session cells.
- Changed modules compile, and the checkout whitespace check passes.
- One disposable, sync-disabled native Anki **26.8.1** run exercised the exact candidate archive. Process, window, filesystem, and sync isolation checks passed. No live collection or review interaction was performed.
- The native fixture included 80 previously consumed answer identities and a future scalar cursor. All eight new answers updated the session exactly once: four in compact mode and four in expanded mode.
- Answer 5 intentionally failed its first Garden save. It was the only deferred answer and recovered without a duplicate review. Final committed Growth, plant allocation, and the HUD session target all equal **120 Growth**: 80 Card Growth plus a legitimate 40 Growth Morning Dew Find. The apparent excess noticed during inspection was this existing Find reward, not an additional defect.
- Count-ups produced intermediate painted values and exact completed values. Native execution exited normally without driver errors. All **271 managed Garden files** in the isolated instance matched the candidate archive.

This was a focused correctness pass. It does not establish that every possible review-engine defect is absent or replace the user's next normal live review as confirmation of responsiveness. No additional add-on matrix or comparative latency benchmark was run in this pass.

Native evidence: `build/performance/review-engine-bugfix-20260912/native-verification.json`; retained raw probe, trace, isolation gates, and exit result are in the adjacent `native/` directory.

## Package and installation

- Archive: `dist/anki_garden-review-engine-fix.ankiaddon`
- SHA-256: `dd11268a1e08557fcaa7ea6d2418e27bfed3e3469c0c6423f08379c3828090d7`
- Installed baseline SHA-256: `d2c16da504b6f474cfc6d23caea17a4c5ef52a0763b6765f1d75b0bc4916b998`
- The archive overlays only `game.py`, `hooks/reviewer.py`, and `storage.py` onto the frozen installed baseline. Other installed layout fixes and unrelated checkout edits are preserved.
- Anki was confirmed closed before installation. Only those three managed code files were replaced. All **271 managed installed files** match the verified archive.
- Replaced code backup: `build/performance/review-engine-bugfix-20260912/backups/20260912-190836/`.
- Protected collection files, Garden progress and settings, shared preferences, installed user files, and add-on metadata have identical before/after hashes. No saved-state migration or retroactive reward recalculation was performed.
- Installation evidence: `build/performance/review-engine-bugfix-20260912/installation.json`.

The update will load on the user's next normal Anki launch. Live Anki was not closed or reopened automatically.
