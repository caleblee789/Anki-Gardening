# Progression state contract

The authoritative persisted boundary is the schema-21 reward database under
`user_files/`. A legacy `garden_state.json` is imported atomically and retained
as migration evidence; mutable data and cache files never enter the
distributable archive.

## Authoritative fields

- Totals: `streak_days` (Anki days in a row with at least one eligible answer), `total_reviews` (card-answer events), `total_correct`, and `total_wrong`.
- Today: `daily_stats.day`, answer counters, `base_growth`, `streak_bonus_growth`, `fertilizer_growth`, `booster_growth`, `weather_growth`, `scenery_growth`, `charge_growth`, `bonus_growth`, `growth_earned`, per-plant Growth, daily environment claims, and the all-due completion flag.
- Garden identity: `garden_name` is profile-wide plain text, normalized to one-line whitespace and capped at 40 characters. `garden_setup_version` distinguishes first-use naming from later edits.
- Plants: stable ID, one supported species, generated/editable name, optional garden-space slot, non-negative Growth, a fractional bonus remainder, planted date, semantic story memories, optional current Fertilizer and Booster intervals, and bounded histories of replaced or expired intervals.
- Nurture routing: `active_plant_id` and timestamped `active_plant_periods` remain the internal compatibility fields. The UI calls this choice **Nurture**. A card answer gives the full committed normal-answer award to the answer-time nurtured unfinished plant. Each other planted unfinished plant also receives an exact 20% passive allocation, carried in persisted fifths. Existing Growth never moves when the learner nurtures another plant.
- Streak Growth: `streak_days` is the only consistency progression value. The current streak bonus is 0% at day 1, +5% at day 7, +10% at day 14, +15% at day 30, +20% at day 100, and +25% at day 365. It is reconciled from authoritative Anki review history at startup, sync, rollover, and live answers; no seven-day history is stored.
- Rewards and economy: `currency_balance`, the append-only reward and transaction ledger, applied reward-event keys, grouped recent receipts, stable processed-answer identities and lineage bindings, achievement history/finalized-day fingerprints, Garden Find activation/drought/daily-count state, bounded visible Find outcomes, consumables, and the separate bounded purchase and Growth Charge replay ledgers. Learner-facing copy calls the balance **Garden Coins**; the compatibility field name does not change.
- Environment: owned Weather and Scenery entitlements, one equipped ID for each kind, and independent Weather/Scenery visibility switches. Visibility changes rendering only; equipped passives remain active. Default entitlements are Clear Skies and Verdant Twilight.
- Collection: `starter_selection_complete`, `unlocked_species`, two to six
  unlocked direct-soil spaces in `unlocked_slots`, and at most six planted
  plants. The configured roster currently contains ten species, but the UI never
  presents that number as a collection denominator. A fresh garden chooses one
  free release-ready starter; plants moved to Collection keep all progress.
- Review ingestion: `processed_revlog_floor` and the bounded, sorted
  `processed_revlog_ids` ledger are authoritative for the current scheduler
  day. `last_processed_revlog_id` remains a monotonic compatibility cursor, but
  it does not exclude a lower ID that arrives later. A
  `revlog_ledger_migration_pending` marker makes conversion from the old scalar
  cursor retryable and atomic.
- Scene geometry: `scene_geometry_version` is independent of schema version.
  The first V6 load clears only visual slots, preserves all plant identity and
  progression, seats one deterministic unfinished nurtured plant on the nearest
  named direct-soil surface, returns the others to Collection, and emits one
  concise placement-refresh notice. All six V6 slots accept direct-soil plants;
  runtime fitting may shrink but never translate a semantic base
  away from its painted support-line center.

## Growth and stages

One eligible card answer gives the unfinished plant identified by
`active_plant_id`—shown to the learner as the plant they **Nurture**—10 base
Growth. The current streak tier adds a deterministic percentage bonus,
unexpired Fertilizer adds a direct +1, +2, or +3 Growth, and an active Booster
Potion adds +5 Growth per answer. Equipped Weather and Scenery add their exact
direct effects after the base/streak calculation. Fertilizer, Booster, Weather,
and Scenery stack. Fractional streak Growth is carried deterministically;
bonuses never reduce the 10 base Growth. Eclipse's +10 is a flat Scenery source,
not a multiplier over any other source.

The nurtured plant receives the full committed normal-answer award. Every other
planted unfinished plant independently receives exactly one fifth of that same
award. Whole Growth is credited immediately; residual fifths remain on that
plant until later eligible answers make another whole point. The daily UI reads
the committed nurtured, passive-exact-fifths, passive-credited, and remainder
fields. Garden Find Growth is the explicit exception: it is direct Growth to
the answer-time nurtured plant only, with no streak modifier or passive fan-out.

The existing stage names and artwork remain authoritative:

| Stage | Total Growth threshold |
|---|---:|
| Seed | 0 |
| Sprout | 500 |
| Young | 2,500 |
| Mature | 8,000 |
| Flowering | 20,000 |
| Rare | 50,000 |

Rare is final. Growth is capped at 50,000 without overflow, the internal active
route is cleared, and the learner chooses **Nurture** on another unfinished
plant.

## Exact all-due contract

All due is a live collection-wide check at award time, not a snapshot of cards due at scheduler-day start.

- Review obligations use Anki’s deck due tree, including active filtered decks and respecting active deck limits.
- Introduced learning and relearning cards remain obligations when their steps are due before the scheduler-day cutoff, including intraday learning and interday relearning queues.
- Unseen new cards are not obligations until introduced by an answer.
- Suspended and buried cards are excluded while unavailable. If restored before the award and then due, they block completion.
- At least one eligible answer in the scheduler day is required.
- The base +10 Garden Coin reward is granted at most once, is recorded with its reason, and is never revoked if the live due set changes later. Equipped Cloudy Drift adds +2 Coins; equipped Rainbow Sunshower adds +5 direct Weather Growth to the nurtured unfinished plant.
- If Anki cannot provide the scheduler cutoff or due tree, the check fails closed and grants nothing.

## Fertilizer contract

Fertilizer belongs to one plant. Every activation interval stores its tier,
tier-derived direct Growth per answer, inclusive Unix activation timestamp, and
exclusive Unix expiration timestamp. An answer receives Basic +1, Quality +2,
or Magical +3 only when the answer-time plant routing selects that plant and
`started_at <= answer_time < expires_at`.

The current interval remains in `fertilizer` for UI compatibility. Replacing it,
or purchasing again after it expires, retains the preceding interval in the
bounded `fertilizer_history` list so a late same-day sync uses the tier that was
active when the answer occurred. Extending the same active tier preserves its
original activation and lengthens its expiry without creating an overlapping
interval. Replacing another active tier requires confirmation, truncates the old
interval at replacement time, and starts the new tier then. Repurchasing after
expiry retains the old interval's original expiry and begins a new interval at
purchase time. If the history cap is reached, the purchase fails before spending
Garden Coins. Intervals wholly before a new authoritative scheduler day are
pruned because those rows are no longer eligible for catch-up; intervals
overlapping the new day remain.

## Booster, Growth Charge, environment, and reward contract

A Booster Potion is a non-purchasable consumable. Using one on the current
nurtured unfinished plant creates a two-hour interval that adds +5 Growth per
eligible answer and stacks with Fertilizer. Using another Potion extends the
same interval. Current-day interval history is bounded so a late same-day sync
receives exactly the Booster active at answer time. Equipped Snow Flurry adds
10% and Full Moon Garden adds 25% to each Potion duration; the extensions are
additive.

Small, Standard, and Grand Growth Charges add 100, 500, and 2,000 direct Growth
to any selected owned, planted, unfinished plant, capped at Rare. Small and
Standard are repeat purchases for 30 and 125 Garden Coins. Grand remains usable
if present in imported development state but is not currently obtainable.
Charge use crosses normal stages, grants normal stage Coins, records its Growth
separately, and consumes the item only in the same successful transaction. It
never receives study modifiers or passive fan-out.

Exactly one Weather and one Scenery are equipped. Purchases are one-time and do
not auto-equip. Clear Skies and Verdant Twilight are free neutral defaults.
Purchasable Weather is Soft Breeze (100), Cloudy Drift (175), Gentle Rain (250),
and Snow Flurry (350). Purchasable Scenery is Spring Bloom (400), Golden Summer
(600), Autumn Hearth (800), and Snow-Covered Garden (1,200). Find-only choices
remain visible in Collection with registry-derived earning copy and
silhouetted art until owned.

### Recurring and one-time rewards

- The first eligible answer of each active Anki day grants 2 Garden Coins.
- Every seventh active-streak day grants 10 Garden Coins. Day 7 is one
  integrated payout with the one-time 7-Day Anki Streak achievement, not a
  duplicate grant.
- Finishing a valid all-due day grants 10 Garden Coins plus any equipped
  environment effect. The first valid day also unlocks **All Clear** for an
  additional 5 Garden Coins.
- Stage rewards and every one-time achievement are separate atomic events and
  may stack with the recurring rewards above.
- Permanent Streak XP, the old variable daily Coin track, the guaranteed weekly
  Small Growth Charge, and the former separate streak-milestone subsystem do
  not exist.

The achievement registry is the only requirements-and-rewards authority:

| Achievement | Requirement | Reward |
|---|---|---|
| 7-Day Anki Streak | Reach a 7-day active Anki streak | 10 Garden Coins |
| 30-Day Anki Streak | Reach 30 days | 100 Garden Coins and 1 Small Growth Charge |
| 100-Day Anki Streak | Reach 100 days | 300 Garden Coins |
| 365-Day Anki Streak | Reach 365 days | 1,000 Garden Coins |
| Century Day | 100 eligible answers in one Anki day | 25 Garden Coins |
| Deep Roots | 1,000 lifetime eligible answers | 1 Standard Growth Charge |
| Clear Recall | Close a day with at least 20 eligible answers and at least 90% non-Again | 10 Garden Coins |
| Perfect Canopy | 30 consecutive eligible answers without Again | 1 Small Growth Charge |
| No-Again Day | Close a day with at least 40 eligible answers and no Again | 15 Garden Coins |
| All Clear | Complete the first valid all-due Anki day | 5 Garden Coins |

Only derivable one-time achievements are reconstructed from history. Open-day
finalization is never inferred early. Recurring rewards, answer Growth, Garden
Finds, and All Clear are never historically backfilled.

### Garden Finds

After Garden Find activation, each newly processed eligible answer checks the
Standard pool and the independent unowned-environment pool using its stable
answer identity. A Standard Find uses drought protection: answers 1–40 are
`1 in 100`, answers 41–60 are `1 in 40`, answers 61–74 are `1 in 20`, and
answer 75 is guaranteed. A maximum of three Standard Finds may be earned in one
Anki day. The registry then selects one currently eligible reward:

| Find | Result | Selection share after a Standard hit |
|---|---|---:|
| Coin Sprout | 2 Garden Coins | 18% |
| Garden Pouch | 4 Garden Coins | 17% |
| Morning Dew | 40 direct Growth | 20% |
| Sun Patch | 60 direct Growth | 15% |
| Hidden Coin Cache | 8 Garden Coins | 9% |
| Growth Burst | 100 direct Growth | 9% |
| Charged Seed | 1 Small Growth Charge | 6% |
| Buried Coin Cache | 20 Garden Coins | 2% |
| Rich Compost | 1 Basic Fertilizer | 1.5% |
| Bottled Rain | 1 Booster Potion | 1.5% |
| Root Core | 1 Standard Growth Charge | 0.6% |
| Garden Treasury | 40 Garden Coins | 0.4% |

The environment pool checks unowned items rarest-first at `1 in 100,000`,
`1 in 20,000`, and `1 in 5,000`. Ultra misses 0–74,999 use 1 in 100,000;
75,000–84,999 use 1 in 90,000; 85,000–94,999 use 1 in 80,000;
95,000–104,999 use 1 in 70,000; 105,000–114,999 use 1 in 60,000; and
115,000 or more use 1 in 50,000. There is no guarantee, and only an Ultra
environment resets the counter.

A Standard and environment Find can both succeed for the same answer. Daily
scenery gifts, recurring rewards, achievements, stage rewards, and Finds keep
separate event keys but share the answer correlation ID so presentation can
show one accurate stacked receipt. Snow-Covered Garden, Halloween Garden, and
Full Moon Garden keep their existing daily gifts; those gifts do not suppress
either Find pool. Garden Find Growth goes directly to the nurtured plant only.
Rich Compost increments `consumables['fertilizer_basic']`; the existing
Fertilizer service owns its effect. Stable event and answer ledgers make all
paths idempotent across retry, restart, sync, and rerender.

## Scheduler-day review ingestion

The authoritative review window is `[scheduler-day start, next-day cutoff)` in
Anki's local scheduler calendar. Its start is derived from the local rollover
boundary rather than by subtracting a fixed 24 hours, preserving DST behavior.
Only supported revlog answer types inside that half-open window are candidates.
Prior-day and future/device-skew rows are neither credited nor marked processed.

Live reviewer callbacks and same-day catch-up reconcile the full bounded window
against the persisted ID ledger. This counts a late lower-ID row exactly once
without recounting a previously seen higher ID. Review progress, Growth, the ID
ledger, and the compatibility cursor save in one transaction. A failed database
read, unavailable/invalid cutoff, safety-bound overflow, or failed state write
does not advance either cursor or save partial Growth; the next safe maintenance
entry point retries. Home injection keeps Anki's normal Deck Browser or Overview
content when maintenance is deferred.

At an authoritative new-day rollover, the ledger floor becomes scheduler-day
start minus one and the daily ID list is cleared. It is never seeded from the
global compatibility cursor, so a future or clock-skewed historical maximum
cannot suppress legitimate new-day rows.

## Derived catalog and UI state

Nursery availability is not persisted. `release_ready_plant_species()` derives
it from local release-preferred Verdant Twilight V6 assets, and
`catalog_summary()` derives **Your plants**, **Available now**, and their counts
from that result plus saved ownership. A species is acquisition-ready only when
all six stages are valid geometry-v2 `direct_soil` entries. Bonsai, Rose,
Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and
Dahlia currently meet the bundled contract.
Existing ownership remains authoritative
even if a species is not currently stocked.

Dashboard selection, open metric/Progress/Plant Story/Nursery dialogs, Nursery
catalog page, and an in-progress Move draft are transient UI state. The
Nursery's fourth tab sells purchasable Weather and Scenery. The cottage opens
the **Collection** page in Garden Progress. Collection owns loadout, visibility,
all-item details, odds, and pity display through a reversible preview whose
Apply action commits atomically. A committed placement and its resulting plant
slots are persisted; the temporary Undo snapshot lasts only for the open Garden
session.

Scene interaction geometry is also derived. `SceneGeometryLayout` projects the
six normalized bed records into logical coordinates after each resize or DPR
change. Each planter perspective variant retains one normalized
`accessory_exclusions` record measured from its opaque alpha bounds for asset
compatibility, but native and Home scenes neither render nor reserve the stored
watering-can accessory. Popover placement is transient and returns its chosen
side, connector, usable height, avoided beds, and docked state without entering
`garden_state.json`.

## Configuration contract

Configuration retains legacy internal visual keys for saved-state compatibility,
but no longer exposes Weather selection, automatic/seasonal Weather, art
quality, animation, performance, or Fine tune controls. Runtime art uses the
balanced tier automatically and respects reduced motion automatically. Settings
keeps the applicable Garden display and notification choices. Environment
loadout and visibility belong to the cottage Collection window, not Settings.

Settings edits are staged. The noninteractive live preview may reflect staged
values, but active configuration changes only after `writeConfig` succeeds.
Cancel reapplies the persisted payload, and Restore defaults stages values
without writing. Diagnostics reports do not enter garden state. The
production package exposes no state-mutation controls. An explicitly requested,
isolated capture build adds a temporary development action that backs up state
before atomically populating the current catalog, all Weather and Scenery
entitlements, all six spaces, at least 100,000 Garden Coins, and test
consumables; Restore backup reverses it without changing Anki revlog.

## Privacy and migration boundary

Plant stories store only event kind, scheduler-day date, numeric landmark, and optional stage transition. Deck names, note fields, card text, and review content are never stored.

Schema 10 is the oldest retained development migration. Anki Garden has not yet
shipped, so preserving development progress is not a release requirement; this
path remains as a fail-closed convenience for test profiles. Before conversion,
the exact source is copied to `garden_state.schema-10.legacy.json`. Compatible
identity, name, slot, species unlock, story, total-review, appearance, and
revlog-cursor data is retained. Legacy Growth is translated to the same stage
and within-stage percentage under the current thresholds, avoiding visual
regression without preserving a parallel points system. Entitlement-only
unlocked species materialize as visible, plantable, Collection-stored zero-Growth plants
instead of becoming phantom ownership or requiring another purchase.

Schemas 11, 12, and 13 migrate to schema 14 as established gardens with starter
selection complete. The revlog migration remains pending until an authoritative
scheduler-day read can atomically seed currently present IDs at or below the
legacy scalar cursor as already processed, then replace the daily floor with
scheduler-day start minus one. A lower ID that arrives after migration therefore
remains discoverable, and the seeded ledger survives ordinary restarts. Legacy
Fertilizer receives a conservative migration-time activation floor, so an older
synced answer cannot gain a bonus whose purchase time is unknown. New schema-14
replacements and renewals then retain bounded answer-time history as described
above. Schema 14 development state upgrades to schema 15 with a default Garden
name, reward seed/history, and empty Booster inventory. Schema 15 upgrades to
schema 16 with neutral environment entitlements, visible layers, zero Charges,
zero Ultra misses, empty daily environment claims, and separate Weather,
Scenery, and Charge Growth counters. No historical review is replayed as Growth
or a random gift. Schema 16 upgrades to schema 17 with a persisted
`OnboardingProgress(version, step, pending_species, starter_plant_id)` record.
Empty gardens resume at introduction, planted starters without nurture evidence
resume at nurture, and established or completed gardens migrate to `done`. The
legacy add-on `onboarding_version` is read only as migration evidence; schema-17
renderers and transitions use the Garden-state record as their authority.
Schema 17 upgrades to schema 18 after an exact backup and initializes the
bounded purchase replay ledger. Schema 19 collapses legacy appearance mirrors
into one canonical loadout. Schema 20 adds exact nurtured/passive Growth
accounting and a bounded Growth Charge replay ledger without attributing older
current-day totals to invented sources.

Schema 21 adds the reward-event and processed-answer authorities, grouped
reward receipts, achievement reconstruction/finalization state, Garden Find
state, and Basic Fertilizer inventory. The JSON payload is then imported once
into a temporary SQLite reward database, verified, backed up online, and
atomically installed. The source JSON is preserved as a timestamped
`pre-sqlite` backup. Unbounded idempotency authorities live in normalized
ledger tables; the materialized state snapshot keeps bounded presentation
caches. A database read or integrity failure is backed up and stops startup
before overwrite.

Completed purchase and Growth Charge records retain caller-generated request
identities, canonical fingerprints, committed results, and completion times.
Exact replay returns the committed result without another debit, grant, or item
use. Reusing an identity with different terms fails closed. A failed save
restores the full in-memory snapshot and creates no replay record.

Migration backup or save failure is fail-closed: the original state is not
overwritten and a fresh state is not returned as though conversion succeeded.

Removed Quest, Vitality, Permanent Streak XP, seven-day-history, daily-goal,
history-import, milestone-choice, obsolete random-drop counters, and
rare-variant fields are not restored as parallel authorities. Schemas 10
through 20 are migrated; any other unsupported JSON schema is copied to a
schema-labeled backup and starts a fresh recovery garden. Unreadable JSON is
copied to `garden_state.invalid.json` before recovery.
