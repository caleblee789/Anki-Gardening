# Anki Garden progression, rewards, and effects

> Current working-tree reference for Anki Garden 2.2.0 and state schema 30.
> Runtime, storage, presentation, capture, and simulation consume the immutable
> catalog in `ankigarden/balance_catalog.py`. Runtime source and committed
> engine results remain authoritative when prose and implementation disagree.

## Current feature availability

Landmarks, Cultivation Mastery, and Garden Legacy are dormant for this release. Their catalog, artwork, saved
funding, claims, selections, and transaction contracts remain available to
developer tests. The runtime and UI share the internal
`ankigarden/feature_availability.py` policy, which defaults to disabled.
A saved active project receives no new funding: final overflow goes to Stored
Growth, and new deferred-project actions cannot spend resources. No save migration,
refund, automatic target switch, or later backfill is performed.

The deferred-system sections below document retained backend contracts for future use.
Existing Mastery appearances and Legacy levels are hidden and receive no new progress.
Historical reward records remain intact, while dormant feature details are omitted
from learner-facing summaries. Full Bloom is the final visible plant stage.
Stored Growth has no spending option in this version. Its positive balance appears
beside Coins only on Garden and in the expanded reviewer's storage-destination
state. Zero balances occupy no UI space; receipts show positive additions only.

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
+ retained streak achievement percentage applied to the 10 base Growth only
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

Garden Finds, Growth Charges, Prism Trellis completion rewards, Firefly Lantern, and other
fixed awards grant **Instant Growth**. Instant Growth receives no streak percentage,
Fertilizer, Booster, Garden Bonus, Scenery, or Shared Growth fan-out.

Plant routing always finishes first. In this release, the entire final remainder
enters Stored Growth, including when a save retains an active deferred project.
The retained developer backend can route overflow to an explicitly enabled
Landmark, Mastery, or Legacy project; production defaults disable all three.
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
- Autumn Hearth adds 15% to all newly earned gameplay Coins, including checkpoints
  and stages. Fractional bonus Coins carry between payouts.
- Full Bloom grants one Small Growth Charge, a permanent Full Bloom record,
  collection and achievement progress, and the next valid nurtured target.
- The durable artwork identifier `rare` is accepted only as a compatibility
  alias. Player-facing and catalog copy use **Full Bloom**.

## Permanent streak Growth bonus

The existing streak achievements unlock one retained percentage. Each value is
the total bonus, not an addition to an earlier tier.

| Consecutive study days | Total permanent base-card Growth bonus |
|---:|---:|
| Fewer than 7 | 0% |
| 7 | 5% |
| 30 | 10% |
| 100 | 15% |
| 365 | 20% |

A study day needs at least one eligible committed answer, without an accuracy
or completion requirement. The achievement unlock records are the persistent
authority for the highest earned tier. A broken streak resets progress toward
the next achievement but never removes an unlocked bonus. Separate streaks do
not combine, and reaching an unlocked milestone again grants nothing extra.

The percentage applies once to the 10 base Growth from each answer, before
independent equipment and supply additions. Shared Growth distributes the
result without applying the percentage again. Direct Growth rewards, including
Growth Charges and completion rewards, receive no streak percentage.

## Study rewards and daily Garden Coins

An Anki day follows Anki’s configured next-day cutoff.

| Trigger | Reward | Conditions |
|---|---:|---|
| Study 1 card | 4 Garden Coins | First eligible committed answer, once per Anki day |
| Finish all cards due today | 16 Garden Coins | Once per verified eligible Anki day |

These are core amounts. The shared earned-Coin pipeline applies equipped item
effects and supplies both the pure display quote and the committed amount.
Opening, refreshing, or syncing a display never reapplies a modifier. Earned
states and their actual amounts come from persistent reward records, even if
more cards appear or the equipped item changes later.

There is no global five-completion cycle or recurring weekly streak payout.
Completion history, cumulative achievements, and item-owned counters remain.

Today’s Cards is collection-wide and fail-closed. It includes scheduler-
available New, Learning, Relearning, and Review obligations under Anki’s active
limits, including active filtered decks. Repeated learning answers do not
inflate the obligation count. Suspended and buried cards remain excluded while
unavailable. If verification fails, the completion reward is withheld while
normal Garden Growth continues.

The requirement is named **Finish all cards due today**. Multi-day requirements
use **Finish all cards due on 15 days**, with the actual interval supplied by
the catalog. A visible zero-due count is not proof that a reward was earned.
Empty workloads say **No cards due today**. A user who cannot finish retains
every card’s Growth and every Find already committed.

Activity has one content-sized Study rewards panel with the two daily rows,
retained Growth percentage, current streak, next higher tier, and a link that
reveals that achievement. The complete ladder remains in Achievements.
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
- Potions provide 100 cards per dose, independent of scenery and decoration ownership.
- A Full Bloom transition transfers remaining effects to the next eligible
  nurtured plant. Once every current catalog species is Full Bloom, remaining
  doses move to persistent garden-wide queues, including plants in Collection.
  Fertilizer and Potions then enhance normal Answer Growth and its Shared Growth.
- Garden-wide activations keep the five-dose limit per family. Inherited queues
  above that limit retain every card and drain before accepting more doses.
- Remaining cards persist exactly across restart and sync.

### Growth Charge rules

- A Charge may target any owned, planted, unfinished plant. The nurtured plant
  is the default target.
- It is consumed only in the same successful transaction that grants Growth.
- It receives no modifiers or Shared Growth.
- Every normal checkpoint and stage crossing still resolves. Excess continues
  through unfinished planted targets and then into Stored Growth.
  After all catalog species bloom, Charges use this garden route
  without a plant selection. Quotes and receipts identify the actual allocation.

## Equipment and daily reward context

`display_decoration_id` and `display_scenery_id` are the two equipped selections.
Each item supplies both its artwork and its catalog effect. Cosmetic decorations
supply no effect. Apply and Equip commit the same selection; previews do not.
Selections may change throughout the day. Subsequent reward events use the
newly equipped item, without recalculating previously awarded rewards. Purchases
never auto-equip. Hiding artwork preserves the equipped item and its effect.

Daily snapshot equipment IDs are historical metadata, not reward authorities.
Sync reconciliation captures the equipped
items once per batch and uses them for unseen eligible reviews, including
past-day reviews. First-N limits use each review's original Anki day and card
position. Today’s Cards completion still requires the current-day live transition.
Swapping preserves cadence counters, applicable equipment daily limits, and the duration
already granted to activated consumables. Equipping itself grants no rewards.

## Garden Bonuses

The equipped decoration supplies at most one Garden Bonus.

| Decoration | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | Appearance only |
| Wind Chime | 100 Garden Coins | +1 Growth every 5 cards |
| Harvest Bell | 175 Garden Coins | Finish all cards due today: +5 Coins |
| Watering Station | 250 Garden Coins | First 200 cards daily: +1 Growth per 2 cards |
| Herbalist’s Hourglass | 350 Garden Coins | Finish all cards due on 15 days: +1 Booster Potion |
| Firefly Lantern | Rare discovery | +3 Growth every 5 cards |
| Prism Trellis | Very Rare discovery | Finish all cards due today: +100 Growth |

Wind Chime and Hourglass progress persists while unequipped, but advances only
when the bonus is active. Watering Station’s first-200 allowance resets at the
Anki-day boundary. Firefly follows the nurtured plant and normal overflow.
Prism awards its fixed Growth only on valid completion; legacy bank fields remain inert.

## Scenery Effects

The equipped scenery supplies its Scenery Effect.

| Scenery | Acquisition | Scenery Effect |
|---|---|---|
| Verdant Twilight | Included | Appearance only |
| Spring Bloom | 400 Garden Coins | First 20 cards daily: +2 Growth each |
| Golden Summer | 600 Garden Coins | First 120 cards daily: +1 Growth per 2 cards |
| Autumn Hearth | 500 Garden Coins | Earn 15% more Coins |
| Snow-Covered Garden | 1,200 Garden Coins | Finish all cards due today: +50 Growth |
| Rainbow Horizon | Rare discovery | First 75 cards daily: +1 Growth each |
| Halloween Garden | Very Rare discovery | Finish all cards due today: 1 mystery gift |
| Full Moon Garden | Ultra Rare discovery | Finish all cards due on 4 days: +1 Booster Potion |
| Celestial Eclipse | Ultra Rare discovery | First 125 cards daily: +1 Growth each |

Hourglass and Full Moon completion remainders pause instead of disappearing while a
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

Standard Finds have no daily limit. Every new eligible answer advances the
existing chance and 75-answer guarantee sequence; successful Finds reset it.
Saved drought counters resume unchanged. Counts retain actual totals, and
historical outcomes are never rerolled or compensated. Environment discoveries
remain independent.

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
- Standard Finds and environment discoveries use independent rules.

## Achievements

Achievements do not reward answer rating, accuracy, speed, or avoiding Again.

| Achievement | Requirement | Reward |
|---|---|---|
| 7-Day Anki Streak | 7-day streak | Total permanent base-card Growth bonus: +5% |
| 30-Day Anki Streak | 30-day streak | Total permanent base-card Growth bonus: +10%; 100 Garden Coins + Small Charge |
| 100-Day Anki Streak | 100-day streak | Total permanent base-card Growth bonus: +15%; 300 Garden Coins |
| 365-Day Anki Streak | 365-day streak | Total permanent base-card Growth bonus: +20%; 1,000 Garden Coins |
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

## Gardening Trophies

Progress → Trophy Room and the garden house open the same three-bay display
case. Trophies activate automatically after unlocking and all three stack with
equipped scenery and the garden decoration.

| Trophy | Unlock requirement | Permanent bonus |
|---|---|---|
| Botanist’s Plaque | All 10 species at Full Bloom | +1 Growth per eligible card, included before Shared Growth |
| Garden Journal | 365 verified completed review days | +5 Garden Coins for each subsequent Today’s Cards completion, once per Anki day |
| Golden Trowel | 100,000 eligible answers | Shared Growth increases from 10% to 15% for each other planted bed |

Trophies have no Equip action and do not appear outdoors. Bonuses begin after
the saved activation boundary; historical reviews and completions are not paid
again. Existing unlocked trophies receive their activation boundary once on
upgrade. Growth Charges retain their fixed values and never receive trophy
multipliers or Shared Growth.

Garden Bench, Birdhouse, Butterfly House, Stone Lantern, and Sundial are retired
from purchasing and display. Their original artwork is saved under
`artwork_source/retired_cosmetics/`, outside the add-on. Historical ownership and
transactions remain intact. An equipped retired prop or trophy falls back to the
included Seedling Sign. Outdoor decoration art is omitted from the Home preview.

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

## Cultivation Mastery (deferred backend)

When explicitly enabled for developer fixtures, after a current species reaches Full Bloom, its cosmetic Mastery track may be
grown continuously through normal overflow and its appearances unlocked in order. Choose a species in its Collection details; optional Add Stored Growth spending remains available. The explicit Unlock appearance button pays the existing Coin cost:

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

## Garden Legacy (deferred backend)

In the retained developer backend, Garden Legacy unlocks after all 2,475,000 Landmark Growth and all ten species’
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

Schema 30 stores exact hundredth-Growth units, Stored Growth, card-counted
Fertilizer and Booster queues, daily reward records, unified equipment choices, persistent effect counters, dual environment pity,
earned beds, active Growth target acknowledgement, cumulative Landmark and
Mastery funding and claims, Garden Legacy, retained achievement unlocks, and
provenance-qualified lifetime economy aggregates.

The player-facing Garden Coin history remains bounded to the newest 500 entries.
Permanent SQLite authorities are independent from those presentation caches:
answer consumption, Find outcomes, discoveries, purchases, Charge uses,
Landmark requests, Mastery requests, migration grants, and immutable daily
economy snapshots cannot be pruned merely because an old receipt is hidden.
Lifetime aggregates retain source/sink totals without replaying UI history.

Schema-26 migration preserves every plant, wallet balance, and Stored Growth
unit and:

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
then process exactly once under their original Anki day. The retained achievement
tier applies to base card Growth, and sync captures current equipment for the
batch. Existing committed rewards are not recalculated. Completion is granted
only when the current live
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


### Schema 30 late-game supplies

The schema-29 upgrade preserves balances, reward claims, onboarding receipts,
activation times, and remaining card batches. Carried Wind Chime and Watering
Station cadence credit settles once on the next qualifying equipped answer;
Watering Station retains separate Anki-day counters. It does not reissue prior
migration grants. Garden-wide batches and committed destination receipts survive
save/reload and failed transactions with the same inventory and Growth totals.
