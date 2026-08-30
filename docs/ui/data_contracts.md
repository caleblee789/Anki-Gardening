# Progression state and presentation contract

The authoritative persisted boundary is the schema-26 reward database under
`user_files/`. Supported schema-10–25 state migrates fail-closed; schema-21 JSON
and SQLite authorities are backed up at their historical migration boundary.
Mutable state and caches never enter the distributable archive.

## Persisted authorities

- Exact Growth uses hundredth units. `Plant.growth_points` remains the whole
  compatibility value and `growth_remainder_units` stores 0–99 hundredths.
- `stored_growth_units` retains every Growth remainder that no planted
  unfinished plant can accept.
- `checkpoint_coin_carry_units` retains fractional milestone-Coin value.
- Each plant persists checkpoint and stage claims, completion date/time,
  contribution statistics, Full Bloom reward state, and card-counted
  Fertilizer/Booster queues.
- `DailyStats` persists `answer_growth_units`, `instant_growth_units`,
  `applied_growth_units`, `redirected_growth_units`, `shared_growth_units`, and
  `stored_growth_units`, plus `plant_applied_growth_units`,
  `plant_shared_growth_units`, and `plant_instant_growth_units` maps.
- `DailyCompletionState` is the technical Today’s Cards projection. Its
  obligation-oriented field names are internal and must never be rendered.
- The persisted loadout independently stores displayed Decoration, active
  Garden Bonus, displayed Scenery, and active Scenery Effect.
  `DailyEconomySnapshot` immutably captures Garden Rhythm and both mechanical
  choices on the first eligible answer; later effect changes queue for the next
  Anki day.
- `environment_pity_misses` and `environment_completion_pity_misses` store
  independent Rare, Very Rare, and Ultra discovery counters.
- `garden_project`, `cultivation_mastery`, and
  `lifetime_economy_aggregates` persist the non-compounding endgame and compact
  economic source/sink totals.
- `pending_sync_reward_summary` stores at most one committed, presentation-ready
  Sync Rewards receipt until the presenter successfully mounts it or the
  presentation setting explicitly suppresses it.
- Currency transactions, reward events, stable answer lineages, Find outcomes,
  finalized days, purchases, Growth Charges, Landmark requests, Mastery
  requests, and migration events remain permanent idempotency authorities
  independently from bounded presentation history.

## Renderer-neutral projections

UI surfaces consume shared presentation contracts rather than deriving labels
or counts locally:

- `PlantIdentity(plant_id, display_name, species_name)` preserves the durable
  instance and default display names such as **Bonsai Plant**.
- The canonical stage projection contains Seed, Sprout, Young, Mature,
  Flowering, and Full Bloom. Persisted `rare` remains the internal final-stage
  key; compact copy is `Sprout · 2 of 6 stages`.
- The collection projection keeps species, owned plant instances, and complete
  registry entries separate. Its canonical completion copy is
  `10 of 10 species discovered` and
  `30 of 93 collection entries discovered`.
- The appearance projection independently exposes Displayed decoration, Active
  garden bonus, Displayed scenery, and Active scenery effect.
- Standard Finds and Garden discoveries retain their existing ledger/event IDs
  while using distinct visible terms.

## Growth transaction

One eligible completed card creates one engine-owned transaction:

1. Calculate full Answer Growth in hundredth units: 10 base Growth, snapshotted
   Garden Rhythm on base only, Fertilizer, Booster, the snapshotted Garden
   Bonus, and snapshotted Scenery Effect.
2. Snapshot every other planted plant as a Shared Growth share source and every
   planted unfinished plant as a possible recipient.
3. Route the complete primary lane through the nurtured plant and then through
   planted unfinished plants in deterministic slot order.
4. Calculate one Shared lane for each other planted plant as exactly 10% of the
   original Answer Growth.
5. Give a still-growing source plant its own share. Divide a Full Bloom source’s
   share exactly among all planted plants still growing, including the nurtured
   plant. Preserve division remainders deterministically.
6. Place any remainder into Stored Growth.
7. Record every checkpoint and stage crossing in chronological order.
8. If the nurtured plant reaches Full Bloom, select the next planted unfinished
   plant and record the routing boundary at the event timestamp.
9. Commit the state, reward rows, Find outcomes, and answer identity atomically.

The returned receipt includes requested, applied, redirected, Shared, and
Stored units, per-source calculation, per-plant allocations, crossings, and the
automatic target change. The UI never recalculates it.

Instant Growth uses the same router without modifiers or Shared fan-out. Find
weights stay constant when no target exists; the complete reward becomes Stored
Growth when necessary. Growth Charges never consume paid value without routing
or storing the full amount.

The canonical Small Growth Charge projection is 450→550 total Growth,
Seed→Sprout, two charges→one, and 50/2,000 toward Young. No-transition and
no-stage-reward outcomes are separate successful projections; Full Bloom
rejection and overflow conservation remain engine decisions.

## Milestones and Full Bloom

Internal stage IDs and thresholds remain:

| Internal ID | Player label | Threshold |
|---|---|---:|
| `seed` | Seed | 0 |
| `sprout` | Sprout | 400 |
| `young` | Young | 2,000 |
| `mature` | Mature | 6,000 |
| `flowering` | Flowering | 15,000 |
| `rare` | Full Bloom | 35,000 |

Stage reward pools are distributed across 25%, 50%, 75%, and completion:

- Sprout: `1 / 1 / 1 / 2`
- Young: `2 / 2 / 2 / 4`
- Mature: `4 / 4 / 4 / 8`
- Flowering: `7 / 7 / 7 / 14`
- Full Bloom: `10 / 10 / 10 / 20`

Autumn Hearth applies 50% to the whole stream, carrying fractional Coins
between payouts. Full Bloom additionally grants one Small Growth Charge and a
permanent collection record. Exact event keys prevent checkpoint, stage, or
completion replay.

## Today’s Cards projection

The service evaluates one live collection-wide scheduler scope before reward
grant:

- Scheduler-available New, Learning, and Review cards count, including active
  filtered decks and active deck limits.
- New-to-Learning and relearning transitions remain outstanding until the card
  leaves that scope; repeated answers do not increment the completed count.
- Suspended and buried cards remain excluded while unavailable.
- Restored cards may return the state to incomplete before grant.
- At least one eligible card must be completed.
- Scheduler or due-tree uncertainty produces `unavailable` and grants nothing.
- Completion grants 10 Garden Coins plus the locked Scenery gift once.
- The first valid completion also grants the 5-Coin **Review Day Complete**
  achievement.

Projection states are `in_progress`, `waiting_for_learning`, `complete`,
`not_eligible`, and `unavailable`. Approved presentation copy is exact:

| State | Primary copy | Secondary copy |
|---|---|---|
| In progress | `18 cards left` | `176 cards complete` |
| Waiting | `2 more cards will be due in 6 minutes` | None |
| Complete | `TODAY’S CARDS COMPLETE` | `+10 Garden Coins earned` and `176 cards complete` |
| Not eligible | `NO COMPLETION REWARD TODAY` | `No cards were due today!` |
| Unavailable | `CARD STATUS UNAVAILABLE` | `Anki Garden could not verify today’s cards. Normal Garden Growth is unaffected.` |

Never render internal `all_due`, obligation, or required-card identifiers.
Never add explanatory commentary to the waiting or complete state. The activity
count is informational and has no denominator, threshold, progress bar,
checkmark, or reward.

## Card-counted Fertilizer and Booster

`CardEffectBatch` stores `effect_id`, Growth per card in exact units, total and
remaining cards, activation timestamp, and source event key:

- Basic Fertilizer: +1 Growth for 100 eligible cards.
- Quality Fertilizer: +2 Growth for 200 eligible cards.
- Magical Fertilizer: +3 Growth for 400 eligible cards.
- Booster Potion: +5 Growth for 100 eligible cards.
- Same-tier Fertilizer doses add card counts; different tiers remain FIFO.
- Elapsed wall-clock time never consumes a card-counted effect.

Selection, quote, confirmation, and the committed active or queued batch carry
the same immutable source `plant_id`. UI disposition labels are **Apply** or
**Queue** for owned inventory and **Buy and apply** or **Buy and queue** for a
purchase. **Extend** is reserved for the existing active same-tier extension.

- Herbalist’s Hourglass extends a newly activated Booster to 125 cards. Full
  Moon Garden awards Potions but does not extend them.
- Another Potion extends the remaining card count.
- Only an effect that contributes to an eligible committed answer decrements.

At Full Bloom, remaining Fertilizer and Booster cards transfer to the automatic
next plant. If no eligible plant exists, the value is retained for the next
Nurture choice. Five doses per plant and effect family may be active or queued;
a rejected dose remains in inventory.

## Daily loadout

The first eligible answer atomically snapshots Garden Rhythm, the selected
Garden Bonus, and the active Scenery Effect for the scheduler day. A later
mechanical selection writes only the next-Anki-day queue. Displayed Decoration
and displayed Scenery remain independent cosmetic choices that may change or
hide immediately. Completion effects, milestone modifiers, Booster extensions,
and card effects read the immutable snapshot. Visibility changes rendering,
not mechanics.

The normalized effects are defined in the progression reference. Purchases do
not auto-equip, and unlock ownership remains separate from selection.

## Post-sync reward reconciliation

Before a normal sync, Garden reconciles the review history already present on
the desktop and records a clean boundary. After sync, it processes every newly
unseen supported post-activation answer introduced beyond that boundary across
the answer’s original Anki day. Stable answer identities allow delayed lower-ID
rows and distinct answer events for the same card to apply exactly once.

- Past-day answers receive their normal per-answer Growth, recurring rewards,
  Finds, discoveries, and progression effects.
- Today’s Cards completion is evaluated only for the current Anki day and only
  when the live before/after transition can be proven.
- Excluded or unsupported rows create no Growth and are not consumed.
- Reward state, ledger rows, processed identities, and one pending nonmodal
  Sync Rewards receipt commit atomically. A failed save leaves the prior
  boundary and rewards available for safe retry.
- Initial setup and a one-way collection replacement establish a non-awarding
  baseline instead of replaying imported history.
- Repeating sync or restarting before successful mount neither duplicates
  rewards nor creates a second receipt. A successful mount clears only the
  matching durable payload; **Close** and **Open Garden** act on the visible
  in-memory receipt.
- Visible milestone priority is Full Bloom, stage change, the highest valid
  checkpoint in the resulting stage, then ordinary Growth. Superseded
  checkpoints do not paint, and sync-created transitions do not enter normal
  Home banners. The canonical Growth total reconciles `420 + 80 + 20 = 520`.

The receipt is presentation only and never drives reward calculation. The local
review-session accumulator and Session Summary exclude background sync rewards.

## Garden Finds and discoveries

Every newly processed eligible card checks independent Standard and environment
pools using its stable event identity.

- Standard chance increases after long gaps and guarantees a Find by the 75th
  eligible card without one.
- The guaranteed Find is at least Uncommon.
- The Standard cap is three below 200 answers, four at 200–399, and five at
  400 or more.
- At the current cap, progress pauses; it resumes from the preserved drought
  state if the cap rises later that day.
- No-target state never changes reward weights.
- Environment counters have finite 10,000 / 40,000 / 50,000 card guarantees and
  60 / 180 / 365 verified-completion guarantees for Rare / Very Rare / each
  Ultra item.
- An unlock resets only its tier and selects uniformly among unowned items.

The persistent HUD never exposes the Standard gap counter, probability band,
daily cap, guarantee state, or raw `n / 75` value. It shows a Find only after the
committed outcome exists. Full Garden help and Collection may show the relevant
mechanics and deterministic environment-tier progress.

## Reviewer presentation

The persistent HUD consumes engine-owned projections and stays mounted between
cards. It shows:

- global Today’s Cards progress;
- prominent nurtured plant art, stage, checkpoint, and next-answer Growth;
- at most two compact active-effect chips;
- one integrated major-reward reveal keyed by a stable committed event ID;
- a live footer from the local-session accumulator.

The expanded safe area is 296 px wide, top 44 px, and right 16 px. Its lower
edge uses measured answer-control clearance with a 72 px fallback; a narrow
viewport collapses the HUD. The canonical count projections reconcile
`176 + 18 = 194` in the HUD and `126 + 19 = 145` in Session Summary.

It does not persist raw Growth routing, Shared Growth math, environment names,
Find cap/protection state, or irrelevant Stored Growth. Routine completion
updates exact plant and session values in place. One committed answer produces
one ordered reward bundle with one event-specific hero, at most two categorized
compact summaries, and an event-ID-backed remainder action; detached toast
stacks do not exist. Atomic items remain intact for history and reconciliation.

The local review-session summary includes cards complete, applied/Shared/Stored
Growth, Coins, Finds, crossings, Today’s Cards state, remaining Fertilizer
cards, and remaining Booster cards. It
is in-memory only and excludes background sync catch-up.

Session Summary and Sync Rewards use one shared coordinator for mutual
exclusion, Escape ownership, safe focus restoration, and upper-right Sync
docking.

## Achievements and legacy policy

Clear Recall, Perfect Canopy, and No-Again Day do not exist. No reward depends
on avoiding Again. The 20 canonical achievements use streak, study volume,
Today’s Cards completion, plant progression, and collection milestones.

Historical badges are consolidated into one Legacy Harvest. Historical economy
is capped at 500 Coins and grants no consumables.

The 30-Day Anki Streak presentation always projects **100 Garden Coins + 1
Small Growth Charge**. Achievement cards, reward receipts, and summaries use
that same shared reward component list.

## Beds, collection, Landmark, and Mastery

Every other planted plant adds one 10% Shared Growth lane. A growing source
receives its own lane; a Full Bloom source’s lane divides among all planted
plants still growing. With one through six planted plants, aggregate garden
output is 100%, 110%, 120%, 130%, 140%, and 150% while at least one plant is
unfinished. Beds 1–2 are included; Beds 3–6 are achievement rewards at first
Mature and one/three/six unique Full Bloom species. Bed cards disclose the
share rule, redistribution, and current aggregate value.

Species, personality, names, planter styling, and placement do not change
Growth or rewards. One starter is free and all non-starter current species cost
250 Coins. Every species card states that Growth rules are identical.
All 60 species-stage placement records serialize `visual_scale_correction` and
a calibrated thumbnail scale, and validation exercises each record in all six
bed positions.

`GardenProjectState` stores one sequential selected project, exact contributed
Stored Growth, readiness, completed and displayed Landmark IDs, and explicit
auto-contribution. `CultivationMasteryState` stores the highest ordered rank per
current species. Both spend Stored Growth and Coins atomically and grant only
cosmetic progress.

## Configuration and privacy

- `show_reviewer_hud` defaults on.
- The existing reviewer-reward setting controls active major dock reveals, not
  the core plant projection or committed session footer.
- `show_rewards_after_syncing` defaults on and controls only whether the already
  committed pending Sync Rewards receipt is shown.
- Dock side and expanded/collapsed state persist.
- Reduced motion suppresses nonessential movement without changing state.
- Card content, note fields, and deck names are never stored in Garden state.

## Migration boundary

Schema 26 preserves exact source state before mutation and converges supported
schema-10–25 JSON/SQLite paths on the current contract:

1. Conserve every plant and exact Stored Growth unit when the Full Bloom cap
   changes to 35,000.
2. Convert timed Fertilizer proportionally with ceiling to 100/200/400-card
   batches; convert Rich Compost inventory to Basic Fertilizer.
3. Preserve previously owned beds, mark their progression claims, and stage
   fixed 150/300/500/800-Coin refunds as idempotent migration events.
4. Preserve plants and refund only a recorded plant purchase amount above 250
   Coins; never infer a debit or refund without purchase history.
5. Split displayed and active Decoration/Scenery choices, initialize immutable
   daily snapshots and completion pity without inventing history, and preserve
   existing card pity and environment ownership. Carry Full Moon's old
   four-completion remainder into the six-completion cadence at the same
   fractional position, rounding up so positive earned progress is preserved.
6. Add Landmark, Mastery, lifetime aggregates, and permanent idempotency tables
   without auto-spending Stored Growth or replaying historical rewards.
7. Commit SQLite at the expected revision; stop without overwrite on failure.

## v26 evidence boundary

Capture contract v26 is independent from persisted schema 26. It uses contract
schema 2 and scenario schema 3 with 18 representative/38 full surfaces and
two/six contact-sheet pages. All evidence layers require `scenario_id`,
`fixture_id`, and one-based `scenario_step`; shared fixture IDs preserve
sequential lineage, and v25 evidence is rejected.

Hard gates cover deprecated visible copy, root/DOM overflow, progress
fractions, asset mappings, Reviewer exclusion rectangles, four-state scroll
coverage, and lineage. Current run paths, archive and capture hashes, artifact
sizes, and validation totals are recorded only in the
[final 2.1.0 UI audit](final-ui-audit-2.1.0.md). That prerequisite evidence
does not approve 2.2.0. Automated evidence retains `quality_status:
review-required` and `release_ready: false`; manual macOS,
Windows/Linux, mixed-DPI, forced-colors, screen-reader, broader-keyboard, and
human approval remain open.
