# Progression state and presentation contract

The authoritative persisted boundary is the schema-30 reward database under
`user_files/`. Supported schema-10–29 state migrates fail-closed; schema-21 JSON
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
  contribution statistics, Full Bloom reward state, card-counted Fertilizer
  queues, and card-counted Booster batches.
- `DailyStats` persists `answer_growth_units`, `instant_growth_units`,
  `applied_growth_units`, `redirected_growth_units`, `shared_growth_units`, and
  `stored_growth_units`, plus `plant_applied_growth_units`,
  `plant_shared_growth_units`, and `plant_instant_growth_units` maps.
- `DailyCompletionState` is the technical Today’s Cards projection. Its
  obligation-oriented field names are internal and must never be rendered.
- The persisted loadout has one equipped decoration and one equipped scenery.
  Their display IDs determine both artwork and catalog effects. Independent
  effect selections and `DailyLoadoutSchedule` are no longer serialized.
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
  instance ID and derives `display_name` through `plant_stage_title`: Seed and
  Sprout follow the species (`Rose Seed`, `Rose Sprout`); Young, Mature,
  Flowering, and Full Bloom precede it (`Young Rose`, `Mature Rose`,
  `Flowering Rose`, `Full Bloom Rose`). Titles, purchase copy,
  previews, tooltips, and accessible names use this same rule. The bare
  `species_name` remains available for milestone sentences. Plant names are not editable.
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
   Fertilizer, Booster, the equipped decoration, and equipped scenery.
2. Snapshot every other planted plant as a Shared Growth share source and every
   planted unfinished plant as a possible recipient.
3. Route the complete primary lane through the nurtured plant and then through
   planted unfinished plants in deterministic slot order.
4. Calculate one Shared lane for each other planted plant as exactly 10% of the
   original Answer Growth, or 15% after the permanent Garden Trowel unlock.
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

The canonical Small Growth Charge projection is 350→450 total Growth,
Seed→Sprout, two charges→one, and 50/1,600 toward Young. No-transition and
no-stage-reward outcomes are separate successful projections; Full Bloom
rejection and overflow conservation remain engine decisions.

## Milestones and Full Bloom

Internal stages remain `seed`, `sprout`, `young`, `mature`, `flowering`, and
`rare`; their visible names are Seed, Sprout, Young, Mature, Flowering, and
Full Bloom. Current thresholds are 0/400/2,000/6,000/15,000/35,000 Growth.
Use the catalog's checkpoint and completion pools through the shared projection;
[the progression reference](../progression-rewards-effects-reference.md) records
the current amounts. Exact event keys prevent milestone replay.

Autumn Hearth adds 15% to newly earned gameplay Coins, retaining fractional
carry between grants. Existing balances, purchases, refunds, reversals, and
replays do not create new earned income. Full Bloom retains its first-time
Small Growth Charge and permanent collection record.

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
- Completion grants 16 core Garden Coins plus applicable equipped effects once.
- The first valid completion also grants the 5-Coin **Review Day Complete**
  achievement.

Projection states are `in_progress`, `waiting_for_learning`, `complete`,
`not_eligible`, and `unavailable`. Approved presentation copy is exact:

| State | Primary copy | Secondary copy |
|---|---|---|
| In progress | `18 cards remaining` | `176 cards complete` |
| Waiting | `2 more cards will be due in 6 minutes` | None |
| Complete | `TODAY’S CARDS COMPLETE` | `+16 Garden Coins earned` and `176 cards complete` |
| Not eligible | `NO COMPLETION REWARD TODAY` | `No cards were due today!` |
| Unavailable | `CARD STATUS UNAVAILABLE` | `Anki Garden could not verify today’s cards. Normal Garden Growth is unaffected.` |

Never render internal `all_due`, obligation, or required-card identifiers.
Never add explanatory commentary to the waiting or complete state. The activity
count is informational and has no denominator, threshold, progress bar,
checkmark, or reward.

## Card-counted Fertilizer and Booster

`CardEffectBatch` stores effect identity, Growth per card, total/remaining cards,
activation timestamp, and source event key. Basic, Quality, and Magical Fertilizer
provide +1/+2/+3 Growth for 100/200/400 eligible answers; Potions provide +5 Growth
for 100 cards. Owning Hourglass and Full Moon adds 25 cards each to a newly
activated Potion. Their 30- and 6-completion gifts still require equipping.
Existing doses keep their recorded duration.

One contributing batch per family spends one card per committed eligible answer.
A different Fertilizer tier waits its turn; same-tier doses add coverage. Time away
from Anki consumes nothing. Five live doses per destination/family may be accepted.

At Full Bloom, remaining batches transfer to the next eligible plant. Once all
current catalog species bloom, remaining batches move once into persisted
`garden_card_effects`, including species outside the displayed garden. Inherited
queues above five doses are preserved and must drain below five before new use.
Fertilizer and Booster then enhance Answer Growth and its existing Shared Growth.

Engine consumable projections and purchase/Charge quotes expose an explicit
garden destination. Charges route their fixed 100/500/2,000 Growth through the
selected eligible Mastery project and Stored Growth without modifiers or Shared
Growth. Receipts display committed allocations. Invalid explicit plant targets
remain invalid. Completed gardens need no growing-plant selection.

Schema 30 carries all schema-29 value and onboarding history forward. Decoration
cadence credit settles once on the next qualifying equipped answer; daily credit
remains keyed by Anki day for delayed sync. Failed transactions restore queues,
Coins, Growth, inventory, and request identities together.

## Equipment

Apply, Equip, and legacy display/loadout entry points commit artwork and effects
atomically. Previews remain read-only; Undo equips the prior selection without
reversing rewards. No review, Growth Charge, or consumable activation locks
these choices. Only the seven functional garden decorations can be equipped. Their artwork
always displays in Garden and Garden Setup; the Home preview omits decorations. Legacy visibility fields remain readable but no longer hide items.
Ownership and purchases remain separate from equipment. Gardening Trophies
activate independently of equipment and have no outdoor display action.

Reward calculations read current equipment, including milestone, completion,
and Booster activation effects. Daily snapshots retain Garden Rhythm and legacy
metadata only. Sync captures one equipment pair for the batch and applies it to
unseen eligible reviews from any supported day, using their original day and
card ordinal for daily limits. Unknown historical Rhythm stays zero. Completed
reward events are never replayed when equipment changes.

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
- Standard Finds have no daily limit; saved drought progress continues between sessions.
- No-target state never changes reward weights.
- Environment tiers use 10,000 / 40,000 / 50,000 card guarantees and independent
  60 / 180 / 365 completion guarantees for Rare / Very Rare / Ultra Rare.
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
Growth, Coins, Finds, crossings, Today’s Cards state, remaining Fertilizer cards,
and remaining Booster cards. It
is in-memory only and excludes background sync catch-up.

Session Summary and Sync Rewards use one shared coordinator for mutual
exclusion, Escape ownership, safe focus restoration, and upper-right Sync
docking.

## Achievements and legacy policy

Clear Recall, Perfect Canopy, and No-Again Day do not exist. No reward depends
on avoiding Again. Current achievements use streak, study volume, or Today’s
Cards completion.

Past Anki review history grants each eligible study achievement once, using its
full catalog reward (Coins, Growth Charges, and the Golden Trowel). There is no
500-Coin cap. Plant progress, recurring daily/weekly rewards, random Finds,
Today's Cards completions, and Garden-only milestones are not replayed.

First-time setup collects those committed grants in a versioned
`welcome_receipt`. After selecting, planting, and nurturing the starter, the
engine atomically completes setup and applies `welcome:first-garden:v1`: 100
Instant Growth and 50 Coins. A new seed also earns its normal first checkpoint
Coin, so the welcome receipt displays **+100 Growth and +51 Coins**. The durable
reward ledger owns idempotency; neither the animation nor its acknowledgement
can grant rewards. Receipt status progresses from collecting to ready, started,
then acknowledged. Interrupted presentations reopen settled; completed gardens
without a receipt do not receive the new first-time gift retroactively.

The native Garden shows one finite, silent welcome animation and the approved
short greeting. **View rewards** reveals Welcome gift and Past Anki study. The
past-study count measures eligible review events, including repeated answers to
the same card. Numbers, items, and the achievement count come from the frozen
receipt, not a fresh calculation of theoretical eligibility. See
[first-garden-welcome.md](first-garden-welcome.md) for the complete reward table
and startup/display contract.

The 30-Day Anki Streak presentation always projects **100 Garden Coins + 1
Small Growth Charge**. Achievement cards, reward receipts, and summaries use
that same shared reward component list.

## Beds and collection

Every other planted plant adds one 10% Shared Growth lane. A growing source
receives its own lane; a Full Bloom source’s lane divides among all planted
plants still growing. With one through six planted plants, aggregate garden
output is 100%, 110%, 120%, 130%, 140%, and 150% while at least one plant is
unfinished. The permanent Garden Trowel increases each Shared lane to 15%. Bed cards disclose the share rule, redistribution, and current
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
All supported schema-10–29 JSON/SQLite paths converge on schema 30. The
schema-26 migration preserves every plant, wallet balance, Stored Growth unit,
and prior claim while adding the current cumulative economy authorities without
retroactive rewards. Unsupported or unreadable state is preserved before
recovery.

Schema 28 keeps each displayed item, derives its effect, and discards old
pending selections. It preserves rewards, progress, visibility, and banked
Growth. The schema-27-to-28 upgrade does not repeat earlier economy migrations.
Watering Station cadence is retained by Anki day so delayed sync cannot change
another day's progress. Existing SQLite snapshot rows remain historical records.

## Capture evidence boundary

Capture contracts are independent from persisted state versions. The current
v29 compiled registry defines active surfaces, scenarios, lineage, and evidence
requirements. Historical v26 captures and their counts cannot certify this
candidate. Record exact production/capture hashes and native/platform acceptance
separately; automated evidence never grants human or public-release approval.

## Gardening Trophies (schema 29)

`trophy_activation_ms` maps the three stable trophy IDs to their first activation
time. New unlocks persist this value with the achievement transaction; upgrade
initializes already unlocked trophies once. Rewards at or before that boundary
receive no bonus. `ReviewAward` records trophy Growth and the Shared Growth
ratio used for that event. `DailyStats.trophy_growth` reports the added primary
Growth. Garden Journal uses a separate durable per-day reward event and receipt,
so retries and sync cannot duplicate its five Coins. Existing one-off achievement
reward IDs and grants stay unchanged.

Trophy acquisition dates project `AchievementState.unlocked_at`; historical
backfills retain their recorded calendar date. Decoration dates use the first
permanent purchase or environment-discovery event, then saved display history.
The menu does not alter ownership, rewards, or acquisition dates. Missing legacy
records remain unknown. These are read-only projections, not new reward fields.
