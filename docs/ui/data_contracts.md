# Progression state contract

The persisted boundary is `user_files/garden_state.json`, currently schema version `16`. Mutable data and cache files never enter the distributable archive.

## Authoritative fields

- Totals: `streak_days` (Anki days in a row with at least one card answer), `total_reviews` (card-answer events), `total_correct`, and `total_wrong`.
- Today: `daily_stats.day`, answer counters, `base_growth`, `streak_bonus_growth`, `fertilizer_growth`, `booster_growth`, `weather_growth`, `scenery_growth`, `charge_growth`, `bonus_growth`, `growth_earned`, per-plant Growth, daily environment claims, and the all-due completion flag.
- Garden identity: `garden_name` is profile-wide plain text, normalized to one-line whitespace and capped at 40 characters. `garden_setup_version` distinguishes first-use naming from later edits.
- Plants: stable ID, one supported species, generated/editable name, optional garden-space slot, non-negative Growth, a fractional bonus remainder, planted date, semantic story memories, optional current Fertilizer and Booster intervals, and bounded histories of replaced or expired intervals.
- Nurture routing: `active_plant_id` and timestamped `active_plant_periods` remain the internal compatibility fields. The UI calls this choice **Nurture**. A card answer goes to the nurtured unfinished plant at its answer time, and existing Growth never moves when the learner nurtures another plant.
- Streak Growth: `streak_days` is the only consistency progression value. The current streak bonus is 0% at day 1, +5% at day 7, +10% at day 14, +15% at day 30, +20% at day 100, and +25% at day 365. It is reconciled from authoritative Anki review history at startup, sync, rollover, and live answers; no seven-day history is stored.
- Economy: `currency_balance`, an idempotent transaction ledger with a user-facing reason and resulting balance, once-ever claimed streak milestones, a stable reward seed, `eligible_reward_count`, `ultra_pity_misses`, bounded drop history, Booster/Charge inventory, and bounded pending feedback. Learner-facing copy calls the balance **Garden Coins**; the serialized field name does not change.
- Environment: owned Weather and Scenery entitlements, one equipped ID for each kind, and independent Weather/Scenery visibility switches. Visibility changes rendering only; equipped passives remain active. Default entitlements are Clear Skies and Verdant Twilight.
- Collection: `starter_selection_complete`, `unlocked_species`, two to six
  unlocked direct-soil spaces in `unlocked_slots`, and at most six planted
  plants. The configured roster currently contains ten species, but the UI never
  presents that number as a collection denominator. A fresh garden chooses one
  free release-ready starter; shelved plants keep all progress.
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
direct passives after the base/streak calculation. Fertilizer, Booster, Weather,
and Scenery stack. Fractional streak Growth is carried deterministically;
bonuses never reduce the 10 base Growth. Eclipse's +10 is a flat Scenery source,
not a multiplier over any other source.

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
nurtured unfinished plant creates a two-hour interval that adds +5 direct
Growth per eligible answer and stacks with Fertilizer. Using another Potion
extends the same interval. Current-day interval history is bounded so a late
same-day sync receives exactly the Booster active at answer time. Equipped Snow
Flurry adds 10% and Full Moon Garden adds 25% to the duration of each Potion
used; the extensions are additive.

Small, Standard, and Grand Growth Charges add 100, 500, and 2,000 direct Growth
to the nurtured unfinished plant, capped at Rare. Small and Standard are repeat
purchases for 30 and 125 Garden Coins; Grand is earn-only. Charge use crosses
normal stages and grants normal stage Coins, records its Growth separately, and
consumes the item only in the same successful state transaction. With no
unfinished nurtured plant or on save failure, nothing is consumed.

Exactly one Weather and one Scenery are equipped. Purchases are one-time and do
not auto-equip. Clear Skies and Verdant Twilight are free neutral defaults.
Purchasable Weather is Soft Breeze (100), Cloudy Drift (175), Gentle Rain (250),
and Snow Flurry (350). Purchasable Scenery is Spring Bloom (400), Golden Summer
(600), Autumn Hearth (800), and Snow-Covered Garden (1,200). Drop-only choices
remain visible in Collection with revealed effect/earning copy and silhouetted
art until owned.

Rare rewards are determined from a stable per-garden seed and authoritative
revlog ID only after duplicate detection. Each eligible answer checks these
independent bands in order and stops after the first hit:

| Order | Reward band | Chance per eligible answer |
|---:|---|---:|
| 1 | Ultra Rare environment | 1 in 100,000 before pity |
| 2 | Grand Growth Charge | 1 in 30,000 |
| 3 | Very Rare environment | 1 in 20,000 |
| 4 | Standard Growth Charge | 1 in 8,000 |
| 5 | Rare environment | 1 in 5,000 |
| 6 | Booster Potion | 1 in 5,000 |
| 7 | Small Growth Charge | 1 in 2,000 |
| 8 | 50 Garden Coins | 1 in 800 |

An environment tier selects uniformly among unowned items. Completing the Rare
tier substitutes a Standard Charge; completing the Very Rare or Ultra tier
substitutes a Grand Charge. Ultra misses 0–74,999 use 1 in 100,000; 75,000–
84,999 use 1 in 90,000; 85,000–94,999 use 1 in 80,000; 95,000–104,999 use 1 in
70,000; 105,000–114,999 use 1 in 60,000; and 115,000 or more use 1 in 50,000.
There is no guaranteed drop. Only an Ultra environment resets the miss counter.

Snow-Covered Garden, Halloween Garden, and Full Moon Garden can grant a daily
gift on the first eligible answer. Halloween chooses Small Charge 70%, Standard
Charge 25%, or Booster Potion 5%. A daily gift consumes that answer's one reward
slot, requires an answer that Anki day, and never backfills a missed day. Drop
IDs and currency transactions are idempotent. Historical streak reconstruction
never replays Growth or rewards.

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
Nursery's fourth tab sells purchasable Weather and Scenery. The cottage's
**Weather & Scenery** tab owns loadout, visibility, all-item Collection details,
odds, and pity display. A committed placement and its resulting plant slots are
persisted; the temporary Undo snapshot lasts only for the open Garden session.

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
without writing. Troubleshooting diagnostics do not enter garden state. The
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
unlocked species materialize as visible, plantable, shelved zero-Growth plants
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
or a random gift.

Migration backup or save failure is fail-closed: the original state is not
overwritten and a fresh state is not returned as though conversion succeeded.

Removed Quest, Vitality, seven-day-history, daily-goal, history-import,
milestone-choice, and rare-variant fields are discarded. Schemas 10 through 15
are migrated; any other unsupported schema is copied to a schema-labeled backup
and starts a fresh recovery garden. Unreadable JSON is copied to
`garden_state.invalid.json` before recovery.
