# Exact-package native functional journeys

Use the current [feature matrix](feature-evidence-matrix.md) and
[progression reference](progression-rewards-effects-reference.md). This replaces
the earlier schema-27 journey and its retired economy and UI expectations.

## Preparation and identity

1. Preserve the working-tree candidate and prior archive. Build the production
   archive with the repository builder; record SHA-256 and inspect its contents.
2. Install only into a fresh disposable Anki base/profile with automatic/media
   sync disabled and credentials absent. Verify PID, launch arguments, unique
   profile title, instance key, filesystem location, and installed payload bytes.
3. Exclude all pre-existing Anki processes/windows. Recheck identity after every
   restart. Keep task-only QA helpers separate from the production add-on.

## Learner journeys

1. **Fresh start:** Open Home and Settings before choosing a plant. Select a free
   starter, place it in an unlocked bed, nurture it, and finish onboarding. Close
   and resume intermediate steps. Verify species identity, one welcome payout,
   and no retroactive per-answer reward for pre-activation reviews.
2. **Real study:** Create synthetic cards and answer Again, Hard, Good, and Easy
   through Anki’s reviewer. Reconcile revlog entries with eligible-answer totals,
   Growth, Coins, and receipts. Include learning repeats and undo/re-answer.
3. **Daily completion:** Exercise new, learning, review, waiting, buried/suspended,
   filtered/limited decks, and unavailable scheduler states. Repeated refreshes or
   extra answers must not duplicate first-card or completion grants. Include an
   Anki-day boundary in deterministic reconciliation coverage.
4. **Commerce:** Purchase a species, each applicable supply type, scenery, and a
   decoration. Check ownership, balance, target, inventory, and card-effect queue.
   Test insufficient funds, stale confirmation, duplicate request, failed save,
   and retry. For synthetic funds, maintain consistent transaction history before
   comparing complete serialized snapshots.
5. **Plant management:** Plant/store/nurture, move to an empty bed, swap occupied
   beds, cancel, and undo. Reject locked beds and invalid targets without losing
   existing progress. Verify Growth Charge conservation and Full Bloom behavior.
6. **Equipment and progress:** Preview without equipping, equip owned items, and
   verify matching effect descriptions. Inspect Activity, achievements, trophies,
   earned beds, and Collection. Deferred Landmarks/Mastery/Legacy must not offer
   active spending or new-progress controls.
7. **Usability:** Navigate Garden, Collection, Shop, Progress, and Settings at
   narrow and normal window sizes. Check keyboard/Escape behavior, reduced motion,
   enlarged text, both Anki themes, missing-art fallback, and reviewer answer-control
   clearance. Use the normal UI action handlers when evaluating refresh behavior;
   direct engine mutations require an explicit UI refresh in a harness.
8. **Restart and upgrade:** Save settings and committed progress, quit only the
   disposable PID, relaunch, and verify values and replay identities. Exercise a
   supported legacy-state fixture in a separate disposable base; never downgrade
   an established profile in place to create a migration fixture.
9. **Sync reconciliation:** Use controlled synthetic imported review history for
   delayed/duplicate/multi-day events and replacement boundaries. Do not describe
   these as an actual AnkiWeb sync. A network sync journey requires a separate
   disposable test account and its own evidence.

## Evidence and acceptance

Record each scenario as passed, failed, or unverified, with artifact identity,
reproduction, before/after observations, and any task-harness limitations. Timing
samples must exclude deliberate waits and distinguish cold from warm operations.

Require passing applicable automated checks, native core journeys, conserved
state, and no unresolved confirmed functional defect for functional acceptance.
Windows is tested when an existing environment is readily available; otherwise
record portability review and native Windows as unverified. Do not equate Linux
CI checks with a native desktop UI pass. Keep the separate pacing hold and public
release approval visible in the final report.
