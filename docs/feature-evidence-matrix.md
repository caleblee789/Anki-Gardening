# Functional acceptance

This matrix covers the current schema-30 candidate. Expected mechanics come from
`ankigarden/balance_catalog.py`, the persisted-state contract, and
[the current progression reference](progression-rewards-effects-reference.md).
Older schema-27 counts, timed Fertilizer, queued equipment, capped Standard Finds,
and paid beds are not acceptance expectations for this candidate.

Record evidence against an exact production archive hash. For current results
and release status, use the [documentation index](README.md#release-status);
for commands and evidence requirements, use the [development guide](development.md).

| Area | Required behavior | Existing automated coverage | Native acceptance |
|---|---|---|---|
| Startup and lifecycle | Recoverable initialization; one set of hooks and menu actions; safe collection close/reopen. | Startup/Home, runtime, configuration tests. | Fresh install, reopen, restart, Settings entry, no add-on warning. |
| Starter and plants | One free starter; selection, placement, nurture, and completion persist independently; welcome rewards do not replay. | Release state, engine, migration, restart tests. | Resume onboarding, verify chosen species, place/nurture, finish, restart. |
| Reviews and daily progress | Eligible answers count once; all ratings receive equal base Growth; daily completion follows Anki scheduler obligations. | Reviewer, engine, history, Today’s Cards tests. | Real answers, repeated learning cards, undo/re-answer, empty/waiting decks, completion. |
| Rewards and presentation | Growth, Coins, discoveries, milestones, and Activity agree with committed event identities. Receipt dismissal never grants or reverses rewards. | Ledger, reward projections, session/sync summary tests. | Reviewer, Garden, Activity, and restart agree; no overlapping or focus-stealing summaries. |
| Purchases and supplies | Revalidate quote and target; atomically debit and acquire/apply; exact retries are idempotent. Fertilizer and Booster value is card-counted. | Transaction integrity, economy, Growth Charge tests. | Buy/use active product types; insufficient funds, stale quote, double-submit, failed save/retry; conserve inventory and Growth. |
| Placement and equipment | Move/swap/undo saves atomically. Equipping commits appearance and effect together; preview does not equip. | Garden features, environment, interaction, restart tests. | Mouse/keyboard placement, cancellation, undo, preview/equip, rejected ownership. |
| Progression | Earned beds, permanent streak tiers, trophies, uncapped Standard Finds, and stored overflow follow the current catalog. Deferred features preserve old state without new spending/progress. | Engine, achievements, schema, balance parity tests. | Milestone/Full Bloom and earned-bed displays; no active deferred-feature controls. |
| Persistence and reconciliation | Supported upgrades retain progress, ownership, claims, and replay identities. Backup precedes destructive recovery. Repeated or delayed history cannot double-credit rewards. | Storage migration, reward state, sync detector/processor, transaction/restart tests. | Upgrade fixture and controlled restart. Synthetic imported history is reconciliation evidence, not live AnkiWeb evidence. |
| UI and responsiveness | Current values, usable controls, keyboard dismissal, readable enlarged text, and bounded scrolling; art failure remains recoverable. | Existing native Qt layout, settings, interaction, asset tests. | Garden, Collection, Shop, Progress/Activity, Settings, reviewer; narrow/normal widths, themes and reduced motion. |
| Packaging | Production archive excludes capture/development capabilities and includes every active runtime asset. | Package reproducibility, asset and production/capture parity tests. | Install and verify payload bytes from the exact archive; record SHA-256. |

## Native functional journeys

### Preparation and identity

1. Preserve the working-tree candidate and prior archive. Build the production
   archive with the repository builder; record SHA-256 and inspect its contents.
2. Install only into a fresh disposable Anki base/profile with automatic/media
   sync disabled and credentials absent. Verify PID, launch arguments, unique
   profile title, instance key, filesystem location, and installed payload bytes.
3. Exclude all pre-existing Anki processes/windows. Recheck identity after every
   restart. Keep task-only QA helpers separate from the production add-on.

### Learner journeys

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

### Evidence and acceptance

Record each scenario as passed, failed, or unverified, with artifact identity,
reproduction, before/after observations, and any task-harness limitations. Timing
samples must exclude deliberate waits and distinguish cold from warm operations.

Require passing applicable automated checks, native core journeys, conserved
state, and no unresolved confirmed functional defect for functional acceptance.
Record native platform/version coverage separately from portability or CI checks.
Use the [release notes](release-notes-2.2.0.md) for accepted progression pacing;
keep public release approval separate.
