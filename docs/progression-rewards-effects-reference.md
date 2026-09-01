# Anki Garden progression, rewards, and effects

> Current working-tree reference for Anki Garden 2.2.0 and state schema 27.
> Runtime, storage, presentation, capture, and simulation consume the immutable
> catalog in `ankigarden/balance_catalog.py`. Runtime source and committed
> engine results remain authoritative when prose and implementation disagree.

## Economy principles

- Every eligible committed answer gives the same ordinary Growth for Again,
  Hard, Good, and Easy. Review speed, deck, card type, interval, difficulty,
  lapse count, and accuracy do not change its value.
- Growth is the card-volume progression axis. Garden Coins are paced mainly by
  active days, Today’s Cards completion, achievements, Finds, and plant
  milestones.
- Nothing earned is deleted. Growth that cannot fit in its intended plant is
  routed through other planted unfinished plants and then into **Stored
  Growth**.
- The Garden has no decay, watering obligation, missed-day loss, speed bonus,
  accuracy streak, daily card ceiling, maintenance tax, random paid purchase,
  or second spendable currency.

## Answer Growth, Shared Growth, and Instant Growth

One eligible committed answer calculates one primary lane in exact
hundredth-Growth units:

```text
10 base Growth
+ Garden Rhythm applied to the 10 base Growth only
+ active Fertilizer Growth
+ active Booster Potion Growth
+ snapshotted Garden Bonus Growth
+ snapshotted Scenery Effect Growth
```

The engine applies that primary lane to the nurtured plant. Each other planted
bed then creates one separate Shared Growth lane equal to exactly 10% of the
primary Answer Growth.

- An unfinished source plant receives its own Shared lane.
- A Full Bloom source bed still creates its lane. That lane is divided across
  all planted unfinished plants, including the nurtured plant.
- Hundredth-unit division remainders follow deterministic bed order.
- Every lane redirects overflow through planted unfinished plants in stable
  slot order. The final remainder becomes Stored Growth.
- One through six planted beds therefore produce 100%, 110%, 120%, 130%,
  140%, or 150% total output while a valid unfinished target exists.

Garden Finds, Growth Charges, Prism Trellis release, Firefly Lantern, and other
fixed awards grant **Instant Growth**. Instant Growth receives no Rhythm,
Fertilizer, Booster, Garden Bonus, Scenery, or Shared Growth fan-out.

After the first Full Bloom, the learner may acknowledge one active long-term
target: Garden Landmark, Cultivation Mastery for a Full Bloom species, or
Garden Legacy after it unlocks. Plant routing always finishes first. Only final
overflow reaches that target, and any remainder enters Stored Growth. With no
acknowledged target, the entire final remainder stays in Stored Growth.
Switching targets never removes earlier funding.

The engine records exact integer units separately as generated Growth, plant
credit, lifetime routing into storage, current Stored Growth balance, and
Landmark, Mastery, or Legacy contributions. Every generated event reconciles
to plant credit plus project credit plus the Stored Growth balance change. A
manual contribution generates no Growth: its positive project credit exactly
matches its negative Stored Growth change.

## Plant stages and milestone rewards

| Stage reached | Total Growth | Base cards | 25% | 50% | 75% | Completion | Stage pool |
|---|---:|---:|---:|---:|---:|---:|---:|
| Seed | 0 | 0 | — | — | — | — | — |
| Sprout | 400 | 40 | 1 | 1 | 1 | 2 | 5 Garden Coins |
| Young | 2,000 | 200 | 2 | 2 | 2 | 4 | 10 Garden Coins |
| Mature | 6,000 | 600 | 4 | 4 | 4 | 8 | 20 Garden Coins |
| Flowering | 15,000 | 1,500 | 7 | 7 | 7 | 14 | 35 Garden Coins |
| Full Bloom | 35,000 | 3,500 | 10 | 10 | 10 | 20 | 50 Garden Coins |

- The complete first-time Garden Coin value remains 120 Garden Coins per plant.
- A single Growth transaction may cross several checkpoints or stages. Stable
  event identities prevent any checkpoint, stage, or completion from paying
  twice.
- Autumn Hearth adds 50% to checkpoint and first-time stage Garden Coins. Fractional
  bonus Garden Coins carry between payouts instead of rounding independently.
- Full Bloom grants one Small Growth Charge, a permanent Full Bloom record,
  collection and achievement progress, and the next valid nurtured target.
- The durable artwork identifier `rare` is accepted only as a compatibility
  alias. Player-facing and catalog copy use **Full Bloom**.

## Garden Rhythm

Anki streak remains visible and continues to power streak Garden Coins and streak
achievements, but it is not a Growth multiplier. **Garden Rhythm** supplies the
only routine percentage bonus.

At the first eligible answer of an Anki day, the engine counts verified
Today’s Cards completions among the prior seven eligible study days and stores
an immutable daily snapshot:

| Completed eligible days | Base Growth bonus |
|---:|---:|
| 0–1 | 0% |
| 2 | 2% |
| 3 | 4% |
| 4 | 6% |
| 5 | 8% |
| 6–7 | 10% |

- An eligible study day contains at least one eligible committed answer.
- Days without an eligible answer are excluded rather than counted as a
  failure.
- Today’s completion can affect a future day; it does not rewrite the current
  day’s snapshot.
- One incomplete study day can lower the rolling result by only one tier. There
  is no total-reset cliff.
- Garden Rhythm applies only to the 10 base Growth.
- If historical sync cannot prove a closed day’s snapshot, Rhythm and permanent
  loadout effects fail closed for that day. Ordinary Growth and card-counted
  consumables still apply.

## Today’s Cards and recurring Garden Coins

An Anki day follows Anki’s configured next-day cutoff.

| Trigger | Reward | Conditions |
|---|---:|---|
| First eligible committed answer | 4 Garden Coins | Once per Anki day |
| Every seventh Anki streak day | 10 Garden Coins | Days 7, 14, 21, and so on |
| Today’s Cards complete | 8 Garden Coins | Once per verified eligible Anki day |
| Garden Cycle | 30 Garden Coins | Every fifth valid Today’s Cards completion |
| Harvest Bell completion | 5 Garden Coins | Garden Bonus must be in that day’s snapshot |
| Autumn Hearth completion | 4 Garden Coins | Scenery Effect must be in that day’s snapshot |

The first seventh-day recurring event and the 7-Day Anki Streak achievement
share one integrated payout of 10 Garden Coins. Garden Cycle completions do not
need to be consecutive: a missing day does not reset progress, while a no-card
day does not count. The fifth completion reward commits automatically with
Today’s Cards and is never modified by Harvest Bell or Autumn Hearth.

Today’s Cards is collection-wide and fail-closed. It includes scheduler-
available New, Learning, Relearning, and Review obligations under Anki’s active
limits, including active filtered decks. Repeated learning answers do not
inflate the obligation count. Suspended and buried cards remain excluded while
unavailable. If verification fails, the completion reward is withheld while
normal Garden Growth continues.

Approved compact copy uses **cards left** and **Today’s Cards Complete**. A user
who cannot finish retains every card’s Growth and every Find already committed.
Answers after completion still grow plants and remain eligible for Finds.

## Plants and earned beds

All ten current species are appearance-only choices and use identical Growth,
milestone, mastery, and economic rules:

| Species | Starter | Non-starter price |
|---|---|---:|
| Bonsai | Eligible | 250 Garden Coins |
| Rose | Eligible | 250 Garden Coins |
| Sunflower | Eligible | 250 Garden Coins |
| Lavender | Eligible | 250 Garden Coins |
| Hydrangea | Eligible | 250 Garden Coins |
| Peony | Eligible | 250 Garden Coins |
| Foxglove | Eligible | 250 Garden Coins |
| Japanese Maple | Eligible | 250 Garden Coins |
| Wisteria | Eligible | 250 Garden Coins |
| Dahlia | Eligible | 250 Garden Coins |

One chosen starter is free. A later plant purchase adds ownership but never
auto-equips or auto-plants the species.

Beds are progression rewards, not purchases:

| Bed | Unlock |
|---:|---|
| 1–2 | Included |
| 3 | First plant reaches Mature |
| 4 | First unique species reaches Full Bloom |
| 5 | Three unique species reach Full Bloom |
| 6 | Six unique species reach Full Bloom |

Only unique current species count toward Full Bloom bed unlocks. Mastery ranks
cannot repeat these rewards.

## Consumables

| Item | Acquisition | Effect |
|---|---|---|
| Basic Fertilizer | 30 Garden Coins; Rich Compost Find | +1 Answer Growth for the next 100 eligible cards |
| Quality Fertilizer | 100 Garden Coins | +2 Answer Growth for the next 200 eligible cards |
| Magical Fertilizer | 300 Garden Coins | +3 Answer Growth for the next 400 eligible cards |
| Booster Potion | Finds and active environment effects | +5 Answer Growth for the next 100 eligible cards |
| Small Growth Charge | 30 Garden Coins; rewards | +100 Instant Growth |
| Standard Growth Charge | 125 Garden Coins; rewards | +500 Instant Growth |
| Grand Growth Charge | Botanical Collection, Old Growth, major rewards | +2,000 Instant Growth |

### Fertilizer and Booster rules

- Fertilizer is card-counted and never expires with wall-clock time. Closing
  Anki, pausing, or reading slowly does not consume value.
- Only an eligible committed answer that receives the effect consumes a card.
- One Fertilizer potency is active at a time. Same-tier doses add card counts;
  different tiers remain in FIFO activation order.
- Up to five Fertilizer doses and five Booster doses may be active or queued on
  a plant. A rejected dose remains in inventory.
- A Booster may run concurrently with one active Fertilizer. Another Booster
  extends its remaining card count rather than increasing potency.
- Herbalist’s Hourglass snapshots an extra 25 cards when a Booster is
  activated, for 125 cards total. Full Moon Garden awards Potions but does not
  extend them.
- A Full Bloom transition transfers remaining card-counted effects to the next
  eligible nurtured plant or preserves them until a valid target is chosen.
- Remaining cards persist exactly across restart and sync.

### Growth Charge rules

- A Charge may target any owned, planted, unfinished plant. The nurtured plant
  is the default target.
- It is consumed only in the same successful transaction that grants Growth.
- It receives no modifiers or Shared Growth.
- Every normal checkpoint and stage crossing still resolves. Excess continues
  through unfinished planted targets and then into Stored Growth.

## Appearance and daily effect snapshot

The four loadout choices are independent:

```text
display_decoration_id
active_garden_bonus_id
display_scenery_id
active_scenery_effect_id
```

The displayed Decoration and displayed Scenery control appearance only. The
active Garden Bonus and Scenery Effect control mechanics. A user may therefore
display one owned item while using another owned item’s effect.

At the first eligible answer, the engine atomically snapshots Garden Rhythm,
the active Garden Bonus, and the active Scenery Effect for that Anki day.
Appearance may change immediately. Mechanical changes after the snapshot queue
for the next Anki day and cannot rewrite committed results. Purchases never
auto-display or auto-equip.

## Garden Bonuses

Only one snapshotted Garden Bonus is active.

| Decoration | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | None |
| Wind Chime | 100 Garden Coins | Every 10 eligible answers, +1 Answer Growth; remainder persists across days |
| Harvest Bell | 175 Garden Coins | +5 Garden Coins when Today’s Cards is complete |
| Watering Station | 250 Garden Coins | Every fifth eligible answer among the first 100 of the Anki day, +1 Answer Growth |
| Herbalist’s Hourglass | 350 Garden Coins | Every 30 active completion days, gain 1 Booster Potion; activated Potions receive 25 extra cards |
| Firefly Lantern | Rare discovery | Every fifth eligible answer, +3 Instant Growth to the unfinished planted plant closest to its next checkpoint |
| Prism Trellis | Very Rare discovery | Bank 1 Growth for each of the first 100 eligible cards per day, up to 300; release the bank on Today’s Cards completion while active |

Wind Chime and Hourglass progress persists while unequipped, but advances only
when the bonus is active. Watering Station’s first-100 allowance resets at the
Anki-day boundary. Firefly ties resolve by remaining Growth, bed, then species.
Prism value persists through incomplete days and is never confiscated.

## Scenery Effects

Only one snapshotted Scenery Effect is active.

| Scenery | Acquisition | Scenery Effect |
|---|---|---|
| Verdant Twilight | Included | None |
| Spring Bloom | 400 Garden Coins | +2 Answer Growth on the first 20 eligible cards each Anki day |
| Golden Summer | 600 Garden Coins | +1 Answer Growth on every second eligible card among the first 120 each Anki day |
| Autumn Hearth | 500 Garden Coins | +4 Garden Coins on Today’s Cards completion and +50% checkpoint/stage Garden Coins |
| Snow-Covered Garden | 1,200 Garden Coins | Every second active Today’s Cards completion grants 1 Small Growth Charge |
| Rainbow Horizon | Rare discovery | +1 Answer Growth on the first 75 eligible cards each Anki day |
| Halloween Garden | Very Rare discovery | Completion gift: Small Charge 95%, Standard Charge 4%, Booster Potion 1% |
| Full Moon Garden | Ultra Rare discovery | Every sixth active Today’s Cards completion grants 1 Booster Potion |
| Celestial Eclipse | Ultra Rare discovery | +1 Answer Growth on the first 125 eligible cards each Anki day |

Snow and Full Moon completion remainders pause instead of disappearing while a
different effect is active. Halloween outcomes are deterministic from the
committed reward identity and cannot reroll on retry, sync, undo lineage,
rerender, or restart.

## Standard Garden Finds

Every newly processed eligible answer checks the Standard Find pool
independently from environment discovery. The drought schedule is:

| Drought answer | Chance |
|---:|---:|
| 1–40 | 1 in 100 |
| 41–60 | 1 in 40 |
| 61–74 | 1 in 20 |
| 75 | Guaranteed, at least Uncommon |

The daily cap rises with committed eligible answers:

| Eligible answers today | Standard Find cap |
|---:|---:|
| 0–199 | 3 |
| 200–399 | 4 |
| 400+ | 5 |

While capped, the Standard roll and drought counter pause. If the cap rises
later that day, the preserved drought state resumes. Environment discoveries
are never blocked by this cap.

| Find | Tier | Reward | Nominal share |
|---|---|---|---:|
| Coin Sprout | Common | 2 Garden Coins | 18% |
| Garden Pouch | Common | 4 Garden Coins | 17% |
| Morning Dew | Common | 40 Instant Growth | 20% |
| Sun Patch | Common | 60 Instant Growth | 15% |
| Hidden Coin Cache | Uncommon | 8 Garden Coins | 9% |
| Growth Burst | Uncommon | 100 Instant Growth | 9% |
| Charged Seed | Uncommon | 1 Small Growth Charge | 6% |
| Buried Coin Cache | Rare | 20 Garden Coins | 2% |
| Rich Compost | Rare | 1 Basic Fertilizer | 1.5% |
| Bottled Rain | Rare | 1 Booster Potion | 1.5% |
| Root Core | Exceptional | 1 Standard Growth Charge | 0.6% |
| Garden Treasury | Exceptional | 40 Garden Coins | 0.4% |

**Rich Compost** is presentation copy for a committed Basic Fertilizer grant;
there is no separate Rich Compost inventory item.

## Environment discovery and dual pity

Each tier has independent card and Today’s Cards-completion counters. The next
unowned item in that tier is guaranteed by whichever threshold arrives first:

| Tier | Base chance | Card guarantee | Completion guarantee | Items |
|---|---:|---:|---:|---|
| Rare | 1 in 2,500 | 10,000 cards | 60 completions | Firefly Lantern, Rainbow Horizon |
| Very Rare | 1 in 10,000 | 40,000 cards | 180 completions | Prism Trellis, Halloween Garden |
| Ultra Rare | 1 in 25,000 | 50,000 cards per item | 365 completions per item | Full Moon Garden, Celestial Eclipse |

- Completion pity advances only on a verified completion day with at least one
  eligible committed answer.
- A successful tier discovery resets that tier’s card and completion counters.
- Draws select uniformly from unowned items in the winning tier. Completed
  tiers stop rolling and duplicates cannot be awarded.
- Simultaneous natural successes award only the rarest natural result.
  Simultaneously forced pity tiers award every forced result.
- Standard Find caps never suppress environment discovery.

## Achievements

Achievements do not reward answer rating, accuracy, speed, or avoiding Again.

| Achievement | Requirement | Reward |
|---|---|---|
| 7-Day Anki Streak | 7-day streak | 10 Garden Coins |
| 30-Day Anki Streak | 30-day streak | 100 Garden Coins + Small Charge |
| 100-Day Anki Streak | 100-day streak | 300 Garden Coins |
| 365-Day Anki Streak | 365-day streak | 1,000 Garden Coins |
| Century Day | 100 eligible cards in one Anki day | 25 Garden Coins |
| Deep Roots | 1,000 lifetime eligible answers | Standard Charge |
| Review Day | First Today’s Cards completion | 5 Garden Coins |
| First Canopy | First plant reaches Mature | Bed 3 |
| First Full Bloom | First unique species reaches Full Bloom | Bed 4 |
| Growing Garden | Three unique species at Full Bloom | Bed 5 |
| Flourishing Garden | Six unique species at Full Bloom | Bed 6 + Standard Charge |
| Botanical Collection | All ten species at Full Bloom | Grand Charge + Botanist’s Plaque |
| Ten Harvests | 10 cumulative completions | 25 Garden Coins |
| Fifty Harvests | 50 cumulative completions | 50 Garden Coins + Small Charge |
| Hundred Harvests | 100 cumulative completions | 100 Garden Coins + Standard Charge |
| Year of Harvests | 365 cumulative completions | 300 Garden Coins + Garden Journal |
| Deep Canopy | 10,000 lifetime eligible answers | 50 Garden Coins |
| Established Roots | 25,000 lifetime eligible answers | 100 Garden Coins + Standard Charge |
| Old Growth | 50,000 lifetime eligible answers | 200 Garden Coins + Grand Charge |
| Ancient Garden | 100,000 lifetime eligible answers | Golden Trowel |

Completion achievements are cumulative, not consecutive. Missing a day never
removes their progress.

## Cosmetic Display Decorations

These items change only the displayed decoration and never change rewards:

| Item | Acquisition | Price |
|---|---|---:|
| Seedling Sign | Included | — |
| Garden Bench | Purchase | 150 Garden Coins |
| Birdhouse | Purchase | 200 Garden Coins |
| Butterfly House | Purchase | 250 Garden Coins |
| Stone Lantern | Purchase | 300 Garden Coins |
| Sundial | Purchase | 400 Garden Coins |
| Botanist’s Plaque | Botanical Collection | — |
| Garden Journal | Year of Harvests | — |
| Golden Trowel | Ancient Garden | — |

Cosmetics are direct, one-time acquisitions with real catalog artwork. They do
not use random purchases, duplicates, gameplay effects, or auto-display.

## Garden Landmark

Garden Landmark unlocks after the first Full Bloom. Its Growth funding is one
continuous cumulative construction track; visual claims are sequential,
cosmetic, and non-compounding:

| Tier | Landmark | Stored Growth | Garden Coins | Cumulative Stored Growth |
|---:|---|---:|---:|---:|
| 1 | Mossy Stone Path | 25,000 | 250 | 25,000 |
| 2 | Birdbath Terrace | 75,000 | 350 | 100,000 |
| 3 | Lily Pond | 175,000 | 550 | 275,000 |
| 4 | Wooden Footbridge | 350,000 | 800 | 625,000 |
| 5 | Garden Pergola | 650,000 | 1,200 | 1,275,000 |
| 6 | Glasshouse Conservatory | 1,200,000 | 2,000 | 2,475,000 |

- Selecting the active Landmark target never spends value. Final plant overflow
  funds the track only after the learner acknowledges it.
- Manual contributions use a quote, fingerprint, fresh-state revalidation,
  exact Stored Growth debit, exact project credit, and one durable identity.
- Growth can continue past an unpaid tier and prefund later tiers up to the
  2,475,000-Growth track maximum.
- Once a cumulative threshold is funded, its separate sequential claim spends
  only the listed Garden Coins and never deducts Growth again.
- Older completed appearances remain selectable. If no project is selected,
  Stored Growth stays in reserve.
- Landmark completion grants no Growth multiplier, Garden Coin faucet, Find bonus, or
  additional effect slot.

## Cultivation Mastery

After a current species reaches Full Bloom, its cosmetic Mastery track may be
funded continuously and its ranks claimed in order:

| Rank | Incremental Growth | Cumulative Growth | Claim cost | Cosmetic reward |
|---|---:|---:|---:|---|
| Bronze | 25,000 | 25,000 | 50 Garden Coins | Bronze plant trim |
| Silver | 50,000 | 75,000 | 100 Garden Coins | Silver trim and journal border |
| Gold | 100,000 | 175,000 | 200 Garden Coins | Gold trim and restrained pollinator effect |
| Iridescent | 200,000 | 375,000 | 400 Garden Coins | Iridescent trim and ambient motes |

One species requires 375,000 funded Growth and 750 Garden Coins across its four
claims; all ten require 3,750,000 funded Growth and 7,500 Garden Coins. Funding
may continue past an unpaid rank. Switching the active species preserves all
prior progress, and claims debit Garden Coins only.

Mastery does not reset the plant, repeat normal stage Garden Coins, increase Growth or
Find odds, unlock another effect slot, or count again toward bed achievements.
Each contribution and claim is protected from duplicate or out-of-order
commit, and no species can exceed 375,000 funded Growth.

## Garden Legacy

Garden Legacy unlocks after all 2,475,000 Landmark Growth and all ten species’
375,000 Mastery Growth tracks are funded. Outstanding Garden Coin claims do not
block it. Each cosmetic Legacy level consumes exactly 500,000 Growth, costs no
Garden Coins, has no maximum level, and grants no gameplay effect. Continued
Growth advances a numeric level and restrained Botanist’s Plaque-style prestige
treatment without creating Growth, Garden Coins, Finds, rarity, or slots.

## Collection and reward presentation

The compact Collection registry contains 39 actual collectible entries across
plants, Garden Bonuses, Scenery, beds, and Growth items. Long-term project
tiers, Mastery ranks, Legacy levels, and cosmetic status records have their own
progress projections and do not inflate the Collection grid denominator.
Species completion and whole-Collection completion remain separate; the
canonical populated fixture says **10 of 10 species discovered** and
**30 of 39 collection entries discovered**.

Routine answers show plant movement and restrained periodic-effect feedback.
Major celebrations are reserved for stages, Full Bloom, bed unlocks,
achievements, environment discoveries, Landmark completion, Mastery completion,
and Botanical Collection. Garden Finds use actual item art and committed reward
copy. Session Summary reports only committed card, Growth, Shared Growth,
Stored Growth, Garden Coin, Find, item, milestone, completion, Landmark, and Mastery
deltas; it does not expose raw odds, drought counters, debug routing, or
uncommitted projections.

## Persistence, migration, and replay authority

Schema 27 stores exact hundredth-Growth units, Stored Growth, card-counted
Fertilizer and Booster queues, Garden Rhythm and effect snapshots, independent
appearance/effect choices, persistent effect counters, dual environment pity,
earned beds, active Growth target acknowledgement, cumulative Landmark and
Mastery funding and claims, Garden Legacy, Garden Cycle, and
provenance-qualified lifetime economy aggregates.

The player-facing Garden Coin history remains bounded to the newest 500 entries.
Permanent SQLite authorities are independent from those presentation caches:
answer consumption, Find outcomes, discoveries, purchases, Charge uses,
Landmark requests, Mastery requests, migration grants, and immutable daily
economy snapshots cannot be pruned merely because an old receipt is hidden.
Lifetime aggregates retain source/sink totals without replaying UI history.

Schema-26 migration preserves every plant, wallet balance, and Stored Growth
unit and:

- adds Garden Cycle without retroactive rewards of 30 Garden Coins, deriving only
  a trustworthy completion-history remainder and otherwise starting at zero;
- raises claimed Landmark and Mastery tracks to their cumulative funded floors
  without revoking claims or charging Growth or Garden Coins again;
- preserves partial endgame funding, selectable claimed Landmark appearances,
  and exact Stored Growth, while clearing the active target for acknowledgement;
- initializes Garden Legacy at level 0 with 0 progress and marks
  unreconstructable lifetime Growth history incomplete instead of fabricating
  totals.

Earlier supported migrations still:

- converts remaining timed Fertilizer proportionally with ceiling to 100, 200,
  or 400 remaining cards;
- preserves owned beds, marks their progression unlocks claimed, and credits
  150/300/500/800 Garden Coins for Beds 3–6 through idempotent migration events;
- preserves every plant, refunds only a recorded amount above 250 Garden Coins, and
  never debits a cheaper historical purchase;
- converts retained Rich Compost inventory into Basic Fertilizer;
- derives Garden Rhythm only from reliable committed history and otherwise
  starts it at zero without retroactive Growth;
- carries the old Full Moon four-completion remainder into the new
  six-completion cadence at the same fractional position, rounding up so a
  positive earned fraction is never erased;
- preserves card pity, starts completion-day pity at zero, and never removes an
  owned environment or grants retroactive pity;
- preserve existing Stored Growth without automatically contributing it to a
  project.

All purchase, Growth, reward, Landmark, Mastery, migration, and discovery
transactions revalidate and commit atomically. Save failure restores state and
ledger staging. Retry, sync, undo lineage, rerender, and restart cannot reroll
or duplicate an already resolved outcome.

## Post-sync rewards

Before normal sync, Garden establishes a clean boundary from review history
already present on the desktop. Newly unseen supported post-activation answers
then process exactly once under their original Anki day. A historical day uses
its immutable economy snapshot; when that snapshot cannot be proven, permanent
Rhythm/loadout effects fail closed rather than being inferred from current
choices. Today’s Cards completion is granted only when the current live
collection-wide transition can be verified.

Rewards and one pending nonmodal Sync Rewards receipt commit atomically.
Disabling **Show rewards after syncing** changes only presentation.

## Source authority

- [Canonical balance catalog](../ankigarden/balance_catalog.py)
- [Game engine](../ankigarden/game.py)
- [Economy progression contracts](../ankigarden/economy_progression.py)
- [Environment adapters](../ankigarden/environment.py)
- [Achievement registry](../ankigarden/achievements.py)
- [Garden Find resolver](../ankigarden/garden_finds.py)
- [Growth transactions](../ankigarden/growth.py)
- [Schema-27 state](../ankigarden/models/state.py)
- [Permanent reward ledger](../ankigarden/reward_ledger.py)
- [Schema migration](../ankigarden/storage.py)
- [Collection projection](../ankigarden/collectibles.py)
- [Detailed data contracts](ui/data_contracts.md)

## Evidence boundary

The implemented source and automated evidence do not by themselves approve a
release. Exact-package native Anki/macOS interaction, accessibility, remaining
platform checks, and human review stay separate. Any capture report with
`quality_status: review-required` or `release_ready: false` remains review
evidence, not release approval.
