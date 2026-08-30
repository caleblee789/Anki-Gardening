# Progression state and presentation contract

The authoritative persisted boundary is the schema-25 reward database under
`user_files/`. Supported schema-10–24 state migrates fail-closed; schema-21 JSON
and SQLite authorities are backed up at their historical migration boundary.
Mutable state and caches never enter the distributable archive.

## Persisted authorities

- Exact Growth uses hundredth units. `Plant.growth_points` remains the whole
  compatibility value and `growth_remainder_units` stores 0–99 hundredths.
- `stored_growth_units` retains every Growth remainder that no planted
  unfinished plant can accept.
- `streak_growth_remainder_units` and `checkpoint_coin_carry_units` retain
  fractional progression and reward value.
- Each plant persists checkpoint and stage claims, completion date/time,
  contribution statistics, Full Bloom reward state, timed Fertilizer periods
  and queues, and card-counted Booster batches.
- `DailyStats` persists `answer_growth_units`, `instant_growth_units`,
  `applied_growth_units`, `redirected_growth_units`, `shared_growth_units`, and
  `stored_growth_units`, plus `plant_applied_growth_units`,
  `plant_shared_growth_units`, and `plant_instant_growth_units` maps.
- `DailyCompletionState` is the technical Today’s Cards projection. Its
  obligation-oriented field names are internal and must never be rendered.
- The persisted loadout keeps the displayed Garden Decoration separate from the
  selected Garden Bonus. `DailyLoadoutSchedule` stores today’s independently
  locked Garden Bonus and Scenery plus their next-Anki-day queues.
- `environment_pity_misses` stores independent Rare, Very Rare, and Ultra
  discovery counters.
- `pending_sync_reward_summary` stores at most one committed, presentation-ready
  Sync Rewards receipt until the presenter successfully mounts it or the
  presentation setting explicitly suppresses it.
- Currency transactions, reward events, stable answer lineages, Find outcomes,
  finalized days, purchase requests, and Growth Charge requests remain the
  idempotency authorities.

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
  `30 of 39 collection entries discovered`.
- The appearance projection independently exposes Scenery, Displayed
  decoration, Active garden bonus, and Visual effects.
- Standard Finds and Garden discoveries retain their existing ledger/event IDs
  while using distinct visible terms.

## Growth transaction

One eligible completed card creates one engine-owned transaction:

1. Calculate full Answer Growth in hundredth units: 10 base Growth, streak,
   Fertilizer, Booster, the Anki-day-locked Garden Bonus, and locked Scenery.
2. Snapshot every other planted plant as a Shared Growth share source and every
   planted unfinished plant as a possible recipient.
3. Route the complete primary lane through the nurtured plant and then through
   planted unfinished plants in deterministic slot order.
4. Calculate one Shared lane for each other planted plant as exactly 20% of the
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
| `sprout` | Sprout | 500 |
| `young` | Young | 2,500 |
| `mature` | Mature | 8,000 |
| `flowering` | Flowering | 20,000 |
| `rare` | Full Bloom | 50,000 |

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
| In progress | `18 cards remaining` | `176 cards complete` |
| Waiting | `2 more cards will be due in 6 minutes` | None |
| Complete | `TODAY’S CARDS COMPLETE` | `+10 Garden Coins earned` and `176 cards complete` |
| Not eligible | `NO COMPLETION REWARD TODAY` | `No cards were due today!` |
| Unavailable | `CARD STATUS UNAVAILABLE` | `Anki Garden could not verify today’s cards. Normal Garden Growth is unaffected.` |

Never render internal `all_due`, obligation, or required-card identifiers.
Never add explanatory commentary to the waiting or complete state. The activity
count is informational and has no denominator, threshold, progress bar,
checkmark, or reward.

## Timed Fertilizer and card-counted Booster

Fertilizer stores an ordered set of wall-clock periods with tier, Growth per
card, start, end, and source identity:

- Basic: +1 Growth per eligible card for 1 hour.
- Quality: +2 Growth per eligible card for 2 hours.
- Magical: +3 Growth per eligible card for 4 hours.
- Reusing the active tier extends its end time.
- A different tier starts when the preceding queued period ends, preserving
  both durations.
- Elapsed time continues outside the reviewer.

Selection, quote, confirmation, and the committed active or queued period carry
the same immutable source `plant_id`. UI disposition labels are **Apply** or
**Queue** for owned inventory and **Buy and apply** or **Buy and queue** for a
purchase. **Extend** is reserved for the existing active same-tier extension.

`CardEffectBatch` is the Booster authority. It stores `effect_id`, derived
`growth_per_card_units`, activated and remaining card counts, activation
timestamp, and source event key.

- Booster Potion: +5 Growth for 100 applicable cards.
- Herbalist’s Hourglass extends a new Booster to 125 cards; Full Moon Garden
  also provides 125; together they provide 150.
- Another Potion extends the remaining card count.
- Only a Booster that contributes decrements.

At Full Bloom, Fertilizer’s remaining duration and Booster’s remaining cards
transfer to the automatic next plant. If no eligible plant exists, the value is
retained for the next Nurture choice. Five doses per plant and effect family may
be active or queued; a rejected dose remains in inventory.

## Daily loadout

The first eligible answer locks the selected Garden Bonus for the scheduler
day. Scenery locks independently on the first progression action, including a
review, Growth Charge, or consumable activation. A later Garden Bonus or
Scenery selection writes only the next-Anki-day queue. The displayed Garden
Decoration remains an independent cosmetic choice that may change or hide
immediately. Completion effects, milestone modifiers, Booster extensions, and
card effects read the locked mechanics. Visibility changes rendering, not
mechanics.

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
- A maximum of three Standard Finds may be granted in one Anki day.
- At the cap, progress pauses until the next day.
- No-target state never changes reward weights.
- Environment counters have finite 5,000 / 20,000 / 50,000 hard guarantees for
  Rare / Very Rare / Ultra.
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
Growth, Coins, Finds, crossings, Today’s Cards state, remaining Fertilizer time,
and remaining Booster cards. It
is in-memory only and excludes background sync catch-up.

Session Summary and Sync Rewards use one shared coordinator for mutual
exclusion, Escape ownership, safe focus restoration, and upper-right Sync
docking.

## Achievements and legacy policy

Clear Recall, Perfect Canopy, and No-Again Day do not exist. No reward depends
on avoiding Again. Current achievements use streak, study volume, or Today’s
Cards completion.

Historical badges are consolidated into one Legacy Harvest. Historical economy
is capped at 500 Coins and grants no consumables.

The 30-Day Anki Streak presentation always projects **100 Garden Coins + 1
Small Growth Charge**. Achievement cards, reward receipts, and summaries use
that same shared reward component list.

## Beds and collection

Every other planted plant adds one 20% Shared Growth lane. A growing source
receives its own lane; a Full Bloom source’s lane divides among all planted
plants still growing. With one through six planted plants, aggregate garden
output is 100%, 120%, 140%, 160%, 180%, and 200% while at least one plant is
unfinished. Bed cards disclose the share rule, redistribution, and current
aggregate value.

Species, personality, names, planter styling, and placement do not change
Growth or rewards. Every species card states that Growth rules are identical.
All 60 species-stage placement records serialize `visual_scale_correction` and
a calibrated thumbnail scale, and validation exercises each record in all six
bed positions.

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

Schema 22 upgrades both legacy JSON and authoritative SQLite schema-21 state:

1. Preserve the exact source before mutation.
2. Add exact Growth, Stored Growth, milestone, completion, daily loadout,
   discovery, timed Fertilizer queue, and Booster-card fields.
3. Preclaim already-crossed checkpoints and stages.
4. Preserve active Fertilizer remaining time and queued duration. Convert a
   legacy timed Booster into its full fixed card-count dose so paid value is not
   destroyed.
5. Preserve plants, wallet, inventory, streak, unlocks, reward identities,
   answer lineages, Find outcomes, and transaction ledgers.
6. Commit SQLite at the expected revision; stop without overwrite on failure.

Schemas 23–25 then replace persisted Weather identities with Garden
Decorations, split displayed artwork from the active Garden Bonus, add
independent Anki-day Bonus locking, and add the durable pending sync receipt.
All supported schema-10–24 JSON/SQLite paths converge on schema 25. Unsupported
or unreadable state is preserved before recovery.

## v26 evidence boundary

Capture contract v26 is independent from persisted schema 25. It uses contract
schema 2 and scenario schema 3 with 18 representative/34 full surfaces and
two/five contact-sheet pages. All evidence layers require `scenario_id`,
`fixture_id`, and one-based `scenario_step`; shared fixture IDs preserve
sequential lineage, and v25 evidence is rejected.

Hard gates cover deprecated visible copy, root/DOM overflow, progress
fractions, asset mappings, Reviewer exclusion rectangles, four-state scroll
coverage, and lineage. Current run paths, archive and capture hashes, artifact
sizes, and validation totals are recorded only in the
[final 2.1.0 UI audit](final-ui-audit-2.1.0.md). Automated evidence retains
`quality_status: review-required` and `release_ready: false`; manual macOS,
Windows/Linux, mixed-DPI, forced-colors, screen-reader, broader-keyboard, and
human approval remain open.
