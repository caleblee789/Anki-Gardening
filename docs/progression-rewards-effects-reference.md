# Anki Garden progression, rewards, and effects

> Current working-tree reference for schema 25. This describes active
> player-facing mechanics. Development tools and retired compatibility fields
> are excluded.

## The three Growth concepts

### Answer Growth

Each eligible completed card calculates:

**10 base Growth + streak + Fertilizer + Booster Potion + Garden Bonus + Scenery**

- Again, Hard, Good, and Easy give equal ordinary Growth. Rate cards honestly.
- The nurtured unfinished plant receives the full award.
- Every other planted plant creates a separate 20% Shared Growth share.
- A plant still growing receives its own share. A Full Bloom plant’s share is
  divided exactly among all planted plants still growing, including the
  nurtured plant.
- Shared fractions and hundredth-Growth values are preserved exactly.

### Instant Growth

Garden Finds, completion effects, Growth Charges, and other fixed awards grant
Instant Growth. It receives no card modifiers and is not shared.

### Milestone rewards

Today’s Cards, streak cycles, plant checkpoints, stage completion,
achievements, and environment discoveries grant Coins, items, or collection
progress. These rewards remain separate from Growth calculation.

## Activation and value protection

- Growth and repeatable rewards begin after starter setup and the first Nurture
  selection. Earlier progression is not backfilled.
- New, learning, relearning, and review cards all count when eligible.
- Every eligible completed card earns its full calculated value after
  progression is active.
- Growth first fills its intended plant, then continues through planted
  unfinished plants in slot order. Any remainder enters **Stored Growth**.
- Stored Growth waits for an explicit Nurture choice after a no-target period.
  Overflow caused by Full Bloom continues automatically.
- Shared Growth is calculated from the original Answer Growth, not from the
  amount the current plant could accept.
- Fertilizer time runs continuously after activation; Booster card counts
  decrease only when the Potion actually applies.

## Plant Growth and checkpoints

| Stage reached | Total Growth | 25% | 50% | 75% | Completion | Stage pool |
|---|---:|---:|---:|---:|---:|---:|
| Sprout | 500 | 1 | 1 | 1 | 2 | 5 Coins |
| Young | 2,500 | 2 | 2 | 2 | 4 | 10 Coins |
| Mature | 8,000 | 4 | 4 | 4 | 8 | 20 Coins |
| Flowering | 20,000 | 7 | 7 | 7 | 14 | 35 Coins |
| Full Bloom | 50,000 | 10 | 10 | 10 | 20 | 50 Coins |

- Internal persistence retains the legacy final-stage identifier; all
  player-facing copy says **Full Bloom**.
- A single Growth event may cross and reward several checkpoints or stages.
- Autumn Hearth adds 50% to checkpoint and stage Coins. Fractional bonus Coins
  carry between payouts instead of being rounded independently.
- The complete base total remains 120 Coins per plant.
- The final stage shows visual progress every 10%, with Coin payouts at 25%,
  50%, 75%, and completion.
- Full Bloom also grants one Small Growth Charge, a permanent collection card,
  completion statistics, and automatic selection of the next planted
  unfinished plant.

Species are cosmetic. Every species uses identical Growth and reward rules.

## Anki streak

The streak percentage applies only to the 10 base Growth. Hundredth-Growth
precision preserves fractional value.

| Active streak | Bonus | Base plus streak per card |
|---|---:|---:|
| Days 1–6 | 0% | 10 |
| Days 7–13 | +5% | 10.5 |
| Days 14–29 | +10% | 11 |
| Days 30–99 | +15% | 11.5 |
| Days 100–364 | +20% | 12 |
| Day 365 onward | +25% | 12.5 |

Missing an active Anki day resets only the bonus. Plants, Coins, Stored Growth,
completed stages, and collection progress remain unchanged.

## Today’s Cards and recurring rewards

An Anki day follows Anki's configured next-day cutoff.

| Trigger | Reward | Conditions |
|---|---|---|
| First eligible completed card | 2 Garden Coins | Once per active Anki day |
| Every seventh streak day | 10 Garden Coins | Days 7, 14, 21, and so on |
| Today’s Cards complete | 10 Garden Coins plus the locked Scenery completion gift | Once per eligible Anki day |
| First valid completion | Additional 5 Garden Coins through **Review Day Complete** | Live-only; never backfilled |

Today’s Cards is a live collection-wide state:

- Scheduler-available New, Learning, and Review cards count within Anki's
  active collection-wide deck limits, including filtered decks.
- A New card that enters Learning remains one outstanding card until its
  scheduler obligation is complete; repeated answers do not inflate progress.
- Suspended and buried cards remain excluded while unavailable.
- Restored cards can return the day to an incomplete state before reward grant.
- If Anki Garden cannot verify the state, the reward fails closed while normal
  Garden Growth continues.
- The Anki-day-locked Garden Bonus and locked Scenery determine completion effects.

Approved HUD copy:

- In progress: **18 cards remaining** and **176 cards complete**.
- Waiting: **2 more cards will be due in 6 minutes**.
- Complete: **TODAY’S CARDS COMPLETE**, **+10 Garden Coins earned**,
  **176 cards complete**.
- Ineligible: **NO COMPLETION REWARD TODAY** and **No cards were due today!**
- Unavailable: **CARD STATUS UNAVAILABLE** and **Anki Garden could not verify
  today’s cards. Normal Garden Growth is unaffected.**

The activity count is informational. It has no denominator, progress bar,
threshold color, checkmark, or separate reward.

## Post-sync rewards

Before normal sync, Garden establishes a clean boundary from review history
already present on the desktop. After sync, every newly unseen supported
post-activation answer beyond that boundary is processed exactly once across
its original Anki day, including delayed lower-ID rows and distinct answers for
the same card.

- Past-day answers receive normal per-answer Growth, rewards, Finds,
  discoveries, and progression effects.
- Today’s Cards completion is evaluated only for the current Anki day when its
  live transition can be proven.
- Rewards and one pending nonmodal Sync Rewards receipt commit atomically.
- Initial setup and one-way collection replacement create a non-awarding
  baseline instead of replaying history.
- **Show rewards after syncing** defaults on and controls only presentation;
  reward processing is unchanged when it is off.

## Consumables

| Item | Acquisition | Effect |
|---|---|---|
| Basic Fertilizer | Nursery: 30 Coins; Rich Compost Find | +1 Growth per eligible card for 1 hour |
| Quality Fertilizer | Nursery: 100 Coins | +2 Growth per eligible card for 2 hours |
| Magical Fertilizer | Nursery: 300 Coins | +3 Growth per eligible card for 4 hours |
| Booster Potion | Bottled Rain Find and qualifying Scenery gifts; not sold | +5 Growth for the next 100 applicable cards |
| Small Growth Charge | Nursery: 30 Coins; milestones, Finds, and gifts | +100 Instant Growth |
| Standard Growth Charge | Nursery: 125 Coins; Finds and gifts | +500 Instant Growth |
| Grand Growth Charge | Compatibility inventory only | +2,000 Instant Growth |

### Fertilizer and Booster rules

- Fertilizer uses wall-clock time, including time outside the reviewer, so more
  cards completed during its window produce more total Growth.
- Reusing the same Fertilizer tier extends its remaining time.
- A different Fertilizer tier queues behind the active tier without discarding
  either duration.
- Booster Potion stacks with Fertilizer; another Potion extends its count.
- Up to five paid Fertilizer doses and five Booster doses may be active or
  queued per plant. A rejected sixth dose remains in inventory.
- At Full Bloom, remaining Fertilizer time and Booster cards transfer to the
  automatically selected plant. If no eligible plant exists, the remaining
  value waits for the next Nurture choice.
- Herbalist’s Hourglass and Full Moon Garden extend each Booster activation:

  | Locked effects when used | Booster cards |
  |---|---:|
  | Neither | 100 |
  | Herbalist’s Hourglass | 125 |
  | Full Moon Garden | 125 |
  | Both | 150 |

### Growth Charge rules

- A Charge can target any owned, planted, unfinished plant.
- It is consumed only in the successful transaction that grants its value.
- It receives no streak, Fertilizer, Booster, Garden Decoration, or Scenery modifier and
  is not shared.
- Overflow continues to other eligible plants or Stored Growth.
- Every crossed checkpoint and stage still grants its milestone reward.

## Daily loadout

Exactly one owned Garden Decoration may be displayed, exactly one owned
decoration supplies the Garden Bonus, and exactly one Scenery may be selected.

- The first eligible answer locks the selected Garden Bonus for the Anki day.
- Changing the Garden Bonus after that lock queues it for the next Anki day;
  bonuses cannot stack.
- The displayed decoration is cosmetic and may change independently at any time.
- Scenery selection is free before the day's first progression event. The first
  eligible completed card, Growth Charge, or other progression event locks it
  until the next Anki cutoff.
- After the first eligible answer, completion gifts, Potion extensions, and
  card effects use the locked Garden Bonus. Before that answer, the decoration
  labeled Ready for today is authoritative.
- Hiding artwork does not disable its locked effect.

## Garden Decorations

| Garden Decoration | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | None |
| Wind Chime | Nursery: 100 Coins | +1 Growth every 10 eligible cards |
| Harvest Bell | Nursery: 175 Coins | +5 Coins when Today’s Cards is complete |
| Watering Station | Nursery: 250 Coins | +1 Growth every 5 eligible cards |
| Herbalist’s Hourglass | Nursery: 350 Coins | Booster Potions add 25% more Booster cards |
| Firefly Lantern | Rare discovery | +3 Growth every 4 eligible cards |
| Prism Trellis | Very Rare discovery | Banks 1.5 direct Growth per eligible card and releases it when Today’s Cards is complete |

## Scenery

| Scenery | Acquisition | Locked effect |
|---|---|---|
| Verdant Twilight | Included | Cosmetic only |
| Spring Bloom | Nursery: 400 Coins | +1 Growth on the first 25 eligible cards |
| Golden Summer | Nursery: 600 Coins | +1 Growth on even-numbered cards among the first 100 |
| Autumn Hearth | Nursery: 500 Coins | +50% checkpoint and stage Coins with fractional carry |
| Snow-Covered Garden | Nursery: 1,200 Coins | 1 Small Growth Charge when Today’s Cards is complete |
| Rainbow Horizon | Rare discovery | +1 Growth on the first 100 eligible cards |
| Halloween Garden | Very Rare discovery | Completion gift: 85% Small Charge, 10% Standard Charge, 5% Booster |
| Full Moon Garden | Ultra discovery | Booster every fourth qualifying completion; +25 cards to Booster activations |
| Celestial Eclipse | Ultra discovery | +2 Growth on the first 100 eligible cards |

## Garden Finds

Every newly processed eligible card checks independent Standard and environment
pools. Reprocessing, retrying, or rerendering the same card cannot reroll it.

### Standard Finds

- Protection increases the chance after long gaps and guarantees a Find by the
  75th eligible card without one.
- The guaranteed Find is at least Uncommon.
- At most three Standard Finds may be earned per Anki day.
- After the cap, Find progress pauses until the next Anki day.
- Reward weights never change because no plant is selected. Instant Growth is
  stored when it cannot be applied.
- The full Garden may explain the daily cap and protection state. The persistent
  reviewer shows a Find only as a committed reward reveal.
- The cap, guarantee state, and internal gap counter are never shown in the HUD,
  tooltip, collapsed view, or Session Summary.

| Find | Tier | Reward | Nominal share |
|---|---|---|---:|
| Coin Sprout | Common | 2 Coins | 18% |
| Garden Pouch | Common | 4 Coins | 17% |
| Morning Dew | Common | 40 Instant Growth | 20% |
| Sun Patch | Common | 60 Instant Growth | 15% |
| Hidden Coin Cache | Uncommon | 8 Coins | 9% |
| Growth Burst | Uncommon | 100 Instant Growth | 9% |
| Charged Seed | Uncommon | 1 Small Growth Charge | 6% |
| Buried Coin Cache | Rare | 20 Coins | 2% |
| Rich Compost | Rare | 1 Basic Fertilizer | 1.5% |
| Bottled Rain | Rare | 1 Booster Potion | 1.5% |
| Root Core | Exceptional | 1 Standard Growth Charge | 0.6% |
| Garden Treasury | Exceptional | 40 Coins | 0.4% |

### Environment discoveries

Each tier has an independent counter and a finite guarantee. Unlocking one tier
resets only that tier and selects uniformly among its unowned items.

| Tier | Base chance | Hard guarantee |
|---|---:|---:|
| Rare | 1 in 2,500 | 5,000 eligible cards |
| Very Rare | 1 in 10,000 | 20,000 eligible cards |
| Ultra | 1 in 25,000 | 50,000 eligible cards |

A completed tier stops rolling. Collection displays deterministic progress to
the next tier guarantee; the reviewer does not show raw counters.

## Achievements and historical recognition

Achievements never reward avoiding Again.

| Achievement | Requirement | Reward |
|---|---|---|
| 7-Day Anki Streak | Reach 7 active days | 10 Coins |
| 30-Day Anki Streak | Reach 30 active days | 100 Coins + 1 Small Charge |
| 100-Day Anki Streak | Reach 100 active days | 300 Coins |
| 365-Day Anki Streak | Reach 365 active days | 1,000 Coins |
| Century Day | Complete 100 eligible cards in one Anki day | 25 Coins |
| Deep Roots | Complete 1,000 eligible cards | 1 Standard Charge |
| Review Day Complete | Complete Today’s Cards for the first time | 5 Coins |

Historical badges are consolidated into one **Legacy Harvest**. Historical
economic rewards are capped at 500 Coins and never grant consumables.

## Beds and garden-wide output

Each other planted plant creates one 20% Shared Growth share, so beds increase
garden-wide output even after individual plants reach Full Bloom:

| Planted plants | Garden output while any plant is unfinished |
|---|---:|
| 1 | 100% |
| 2 | 120% |
| 3 | 140% |
| 4 | 160% |
| 5 | 180% |
| 6 | 200% |

If a share’s source plant is still growing, that plant receives the share. If
the source is at Full Bloom, its share is divided exactly among all planted
plants still growing. The nurtured plant may therefore receive redistributed
Shared Growth. Unplanted plants create no share.

Bed cards disclose **Each other planted bed adds a 20% Shared Growth share** and
show the current aggregate output. Six planted beds retain 200% total output
while at least one plant remains unfinished.

| Capacity | Cost |
|---|---:|
| Beds 1–2 | Included |
| Bed 3 | 150 Coins |
| Bed 4 | 300 Coins |
| Bed 5 | 500 Coins |
| Bed 6 | 800 Coins |

## Persistence and presentation authority

Schema 25 persists exact hundredth-Growth units, Stored Growth, milestone
claims, Full Bloom metadata, Today’s Cards state, daily loadout locks and queue,
environment guarantees, timed Fertilizer intervals/queues, and card-counted
Booster batches, independent displayed Decoration and active Garden Bonus
choices, and the pending sync receipt. Supported schema-10–24 state migrates
fail-closed; schema-21 JSON and SQLite profiles are backed up at their
historical migration boundary.

The engine returns the committed Growth breakdown and routing receipt. The UI
does not independently calculate Growth, remaining cards, milestones, or reward
state.

The reviewer HUD shows global Today’s Cards progress, prominent plant/stage art,
checkpoint progress, next-answer and committed-answer Growth, compact active
effects, one integrated major reward reveal, and nonzero committed session
totals. Projected quantities use `card/cards`; the immediate action remains
`Next answer`. It keeps exact Growth lanes, environment names, Find
cap/protection state, and irrelevant Stored Growth out of the persistent view
while retaining those typed facts for detailed surfaces.

## Explicit non-mechanics

There is no plant decay, watering obligation, missed-day loss, rating-button
Growth multiplier, randomized ordinary Growth, rotating quest list, additional
currency, or unlimited environment stacking.

## Source authority

- [Game engine](../ankigarden/game.py)
- [Environment and Growth Charge catalogs](../ankigarden/environment.py)
- [Achievement registry](../ankigarden/achievements.py)
- [Garden Find registries](../ankigarden/garden_finds.py)
- [Growth contracts](../ankigarden/growth.py)
- [Schema-25 state](../ankigarden/models/state.py)
- [Detailed data contracts](ui/data_contracts.md)
- [Reviewer HUD specification](reviewer-hud-specification.md)
