# Anki Garden 2.2.0 functional evidence matrix

This matrix covers the current schema-30 candidate. Expected mechanics come from
`ankigarden/balance_catalog.py`, the persisted-state contract, and
[the current progression reference](progression-rewards-effects-reference.md).
Older schema-27 counts, timed Fertilizer, queued equipment, capped Standard Finds,
and paid beds are not acceptance expectations for this candidate.

Passing automated checks does not certify native interaction, cross-platform
support, pacing, or public release approval. Record evidence against an exact
production archive hash; see [native journeys](e2e_display_assertions.md).

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

For a full functional audit, run both existing pytest lanes, then native journeys.
During fixes, rerun only affected checks. Add regression tests only for meaningful
behavior not already protected by a stable existing test.
