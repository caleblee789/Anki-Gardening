# Anki Garden progression, rewards, and effects

> Current working-tree reference for schema 21, reviewed 2026-08-27. This
> describes active player-facing mechanics. Development-only population tools
> and retired compatibility fields are excluded.

## At a glance

An eligible card answer normally produces:

**10 base Growth + streak Growth + Fertilizer + Booster Potion + equipped
Weather + equipped Scenery**, capped by the nurtured plant's remaining distance
to Rare.

- The nurtured unfinished plant receives the full normal award.
- Every other planted, unfinished plant separately receives exactly 20% of that
  same award. Fractional fifths persist until they become whole Growth.
- Garden Find Growth, all-due Growth, and Growth Charges are direct Growth.
  They do not receive study modifiers and do not fan out to other plants.
- Crossing a plant stage by any Growth source grants that stage's Garden Coins.
- Garden Coins, items, achievements, and collectible unlocks can stack on the
  same answer when their independent conditions are met.

## Activation and eligible answers

- Growth and repeatable rewards begin only after the learner completes starter
  setup and chooses an unfinished plant to nurture. Earlier Growth, recurring
  rewards, and Garden Finds are not backfilled.
- New, learning, relearning, and review answers all count. Again, Hard, Good,
  and Easy all give the same 10 base Growth; answer quality affects accuracy
  statistics and recall achievements, not ordinary Growth.
- The Anki day follows Anki's configured next-day cutoff. One eligible answer
  makes the day active for streak purposes.
- The current streak and derivable one-time achievements are reconstructed from
  authoritative Anki history. All Clear, recurring rewards, ordinary Growth,
  and Garden Finds are never historically inferred.
- If no unfinished plant is nurtured, ordinary Growth pauses. Coin rewards,
  non-Growth Finds, daily item gifts, and achievement tracking can still
  continue after progression has been activated.

## Plant Growth and stages

| Stage | Total Growth | Base stage reward | With Autumn Hearth |
|---|---:|---:|---:|
| Seed | 0 | — | — |
| Sprout | 500 | 5 Coins | 6 Coins |
| Young | 2,500 | 10 Coins | 13 Coins |
| Mature | 8,000 | 20 Coins | 25 Coins |
| Flowering | 20,000 | 35 Coins | 44 Coins |
| Rare | 50,000 | 50 Coins | 63 Coins |

- Rare is final and all Growth is capped at 50,000.
- A single award can cross multiple stages and grants every crossed stage
  reward. Passive Growth can also trigger a stage reward on another plant.
- Autumn Hearth increases stage Coins only by 25%, with half-Coins rounded up.
  It does not boost daily, achievement, all-due, or Garden Find Coins.
- The 25%, 50%, and 75% points within a stage produce progress feedback only.
  They do not grant currency or items.
- Reaching Rare clears that plant as the nurture target; another unfinished
  plant must be selected for ordinary Growth to resume.

## Anki streak Growth

The streak percentage applies only to the 10 base Growth. Fractional bonuses
are carried per plant, so nothing is lost to rounding.

| Active streak | Bonus | Long-run base + streak per answer |
|---|---:|---:|
| Days 1–6 | 0% | 10 |
| Days 7–13 | +5% | 10.5 |
| Days 14–29 | +10% | 11 |
| Days 30–99 | +15% | 11.5 |
| Days 100–364 | +20% | 12 |
| Day 365 onward | +25% | 12.5 |

Missing an active Anki day resets the next active day to streak day 1.

## Recurring and stage rewards

| Trigger | Reward | Repeatability and conditions |
|---|---|---|
| First eligible answer of an Anki day | 2 Garden Coins | Once per active day |
| Every seventh streak day | 10 Garden Coins | Days 7, 14, 21, and so on |
| Finish all due cards | 10 Garden Coins | Once per eligible Anki day |
| Plant reaches a new stage | 5 / 10 / 20 / 35 / 50 Garden Coins | Once per stage, per plant; Autumn Hearth can boost this |
| Standard Garden Find | Coins, direct Growth, or a consumable | Up to three hits per Anki day |
| Environment Garden Find | One unowned Weather or Scenery item | Independent of the Standard pool |
| Achievement | Its one-time reward bundle | Once per achievement |

The day-7 achievement and the first seven-day cycle are one integrated 10-Coin
payout, not two separate 10-Coin rewards.

### All-due details

The all-due check is live and collection-wide at award time:

- The day must have begun with a verified due review or learning obligation,
  and at least one eligible answer must have been completed.
- Due reviews and introduced learning/relearning steps before the next-day
  cutoff count. Active filtered decks and active deck limits are respected.
- Unseen new cards do not count until introduced. Suspended or buried cards do
  not count while unavailable, but block completion if restored and then due.
- If the due tree or scheduler cutoff is unavailable, the reward fails closed.
- Cloudy Drift changes the all-due payout to 12 Coins.
- Rainbow Sunshower adds 5 direct Growth to the currently nurtured unfinished
  plant.
- The first valid completion also unlocks All Clear for 5 additional Coins.

## Consumables and direct-Growth items

| Item | Acquisition | Effect |
|---|---|---|
| Basic Fertilizer | Nursery: 25 Coins; Rich Compost Garden Find | +1 Growth per answer for 1 hour |
| Quality Fertilizer | Nursery: 65 Coins | +2 Growth per answer for 2 hours |
| Magical Fertilizer | Nursery: 150 Coins | +3 Growth per answer for 4 hours |
| Booster Potion | Bottled Rain Find; Halloween or Full Moon daily gift; not sold | +5 Growth per answer for 2 hours |
| Small Growth Charge | Nursery: 30 Coins; achievements, Finds, and daily Scenery gifts | +100 direct Growth when used |
| Standard Growth Charge | Nursery: 125 Coins; achievements, Finds, and Halloween gift | +500 direct Growth when used |
| Grand Growth Charge | Not currently obtainable; imported development inventory remains usable | +2,000 direct Growth when used |

### Timed-item rules

- Fertilizer and Booster Potion attach to one plant and apply only when that
  unfinished plant is the answer-time nurture target.
- One Fertilizer tier is active on a plant at a time. Reusing the same tier
  extends its remaining duration. A different active tier requires
  confirmation, replaces it, and discards the remaining future time.
- Booster Potion stacks with Fertilizer. Another Potion extends the current
  Booster interval rather than replacing it.
- Snow Flurry adds 10% to each Potion duration and Full Moon Garden adds 25%;
  the extensions are additive when equipped at use time:

  | Equipped duration effects | Time added per Potion |
  |---|---:|
  | Neither | 2 hours |
  | Snow Flurry | 2 hours 12 minutes |
  | Full Moon Garden | 2 hours 30 minutes |
  | Both | 2 hours 42 minutes |

### Growth Charge rules

- A Charge can target any owned, planted, unfinished plant; it need not be the
  current nurture target.
- Charges are consumed only in the same successful transaction that applies
  their Growth.
- They ignore streak, Fertilizer, Booster, Weather, Scenery, and passive
  fan-out, but still trigger every stage and stage-Coin reward they cross.

## Weather

Exactly one Weather is equipped. Purchases are permanent unlocks but do not
auto-equip.

| Weather | Rarity / acquisition | Effect while equipped |
|---|---|---|
| Clear Skies | Common; included | Neutral; no mechanical effect |
| Soft Breeze | Common; Nursery 100 Coins | +1 Growth on answers 1–10 each Anki day |
| Cloudy Drift | Common; Nursery 175 Coins | +2 Coins when all due cards are finished |
| Gentle Rain | Uncommon; Nursery 250 Coins | +1 Growth on answers 1–20 each Anki day |
| Snow Flurry | Uncommon; Nursery 350 Coins | Booster Potions last 10% longer |
| Firefly Evening | Rare; Rare environment Find | +5 Growth on answers 1–5 each Anki day |
| Rainbow Sunshower | Very Rare; Very Rare environment Find | +5 direct Growth when all due cards are finished |

## Scenery

Exactly one Scenery is equipped. Its passive stacks with the equipped Weather.

| Scenery | Rarity / acquisition | Effect while equipped |
|---|---|---|
| Verdant Twilight | Common; included | Neutral; no mechanical effect |
| Spring Bloom | Common; Nursery 400 Coins | +1 Growth on answers 1–25 each Anki day |
| Golden Summer | Uncommon; Nursery 600 Coins | +1 Growth on every even-numbered answer |
| Autumn Hearth | Uncommon; Nursery 800 Coins | +25% Coins from plant stage rewards; half-Coins round up |
| Snow-Covered Garden | Rare; Nursery 1,200 Coins | Once daily: 1 Small Growth Charge |
| Rainbow Horizon | Rare; Rare environment Find | +1 Growth on every answer |
| Halloween Garden | Very Rare; Very Rare environment Find | Once daily: Small Charge 70%, Standard Charge 25%, or Booster Potion 5% |
| Full Moon Garden | Ultra Rare; Ultra environment Find | Once daily: 1 Booster Potion; each Potion lasts 25% longer |
| Celestial Eclipse | Ultra Rare; Ultra environment Find | +10 flat Scenery Growth per answer, effectively doubling only the 10 base Growth |

Daily Scenery gifts trigger once per Anki day on the first eligible answer
processed while that Scenery is equipped. They remain independent of both
Garden Find pools.

### Environment rules shared by Weather and Scenery

- Weather and Scenery stack with each other and with streak, Fertilizer, and
  Booster Potion on an ordinary answer.
- Hiding a Weather or Scenery visual layer does not disable its equipped
  passive.
- Changing the equipped item replaces only that kind's active passive;
  ownership remains.
- Limited-answer effects use the answer's ordinal within the Anki day, not its
  correctness.
- All-due, stage-Coin, and Potion-duration effects are evaluated when their
  respective event occurs.

## Garden Finds

Each newly processed eligible answer checks two independent, deterministic
pools. Reprocessing, retrying, or rerendering the same answer cannot reroll it.
A Standard Find and an environment Find can both succeed on the same answer,
alongside daily rewards, Scenery gifts, achievements, and stage rewards.

### Standard pool cadence

The drought count persists across Anki days and resets after a Standard hit.

| Consecutive Standard misses before this roll | Hit chance |
|---|---:|
| 0–39 | 1 in 100 |
| 40–59 | 1 in 40 |
| 60–73 | 1 in 20 |
| 74 | Guaranteed |

- At most three Standard Finds can be earned in one Anki day.
- After the daily cap, Standard rolls pause and the drought count does not
  advance until a later day.
- Direct-Growth entries are removed when no unfinished nurture target is
  available; the remaining weights are then renormalized.

### Standard reward selection

These are the nominal shares after a hit when every entry is eligible:

| Find | Tier | Reward | Share |
|---|---|---|---:|
| Coin Sprout | Common | 2 Coins | 18% |
| Garden Pouch | Common | 4 Coins | 17% |
| Morning Dew | Common | 40 direct Growth | 20% |
| Sun Patch | Common | 60 direct Growth | 15% |
| Hidden Coin Cache | Uncommon | 8 Coins | 9% |
| Growth Burst | Uncommon | 100 direct Growth | 9% |
| Charged Seed | Uncommon | 1 Small Growth Charge | 6% |
| Buried Coin Cache | Rare | 20 Coins | 2% |
| Rich Compost | Rare | 1 Basic Fertilizer | 1.5% |
| Bottled Rain | Rare | 1 Booster Potion | 1.5% |
| Root Core | Exceptional | 1 Standard Growth Charge | 0.6% |
| Garden Treasury | Exceptional | 40 Coins | 0.4% |

Garden Find Growth goes only to the answer-time nurtured unfinished plant. It
is capped at Rare, receives no modifiers, and has no passive fan-out.

### Unowned-environment pool

Tiers are checked rarest-first. A successful tier chooses uniformly among its
currently unowned items, so the per-item chance changes as items are collected.
At most one environment item is granted per answer.

| Tier | Tier chance | Items |
|---|---:|---|
| Ultra | Starts at 1 in 100,000 | Full Moon Garden, Celestial Eclipse |
| Very Rare | 1 in 20,000 | Rainbow Sunshower, Halloween Garden |
| Rare | 1 in 5,000 | Firefly Evening, Rainbow Horizon |

Ultra pity has no guarantee. Only an Ultra unlock resets it:

| Ultra misses | Ultra tier chance |
|---|---:|
| 0–74,999 | 1 in 100,000 |
| 75,000–84,999 | 1 in 90,000 |
| 85,000–94,999 | 1 in 80,000 |
| 95,000–104,999 | 1 in 70,000 |
| 105,000–114,999 | 1 in 60,000 |
| 115,000+ | 1 in 50,000 |

## Achievements

Every achievement is one-time. Hard, Good, and Easy are non-Again answers;
Again resets the Perfect Canopy run and counts against daily recall.

| Achievement | Requirement | Reward | Evaluation |
|---|---|---|---|
| 7-Day Anki Streak | Reach a 7-day active streak | 10 Coins | Immediate; history-derivable; integrated with that day's seven-day cycle |
| 30-Day Anki Streak | Reach 30 days | 100 Coins + 1 Small Charge | Immediate; history-derivable |
| 100-Day Anki Streak | Reach 100 days | 300 Coins | Immediate; history-derivable |
| 365-Day Anki Streak | Reach 365 days | 1,000 Coins | Immediate; history-derivable |
| Century Day | Reach 100 eligible answers in one Anki day | 25 Coins | Immediate at answer 100; history-derivable |
| Deep Roots | Reach 1,000 lifetime eligible answers | 1 Standard Charge | Immediate; history-derivable |
| Clear Recall | Close a day with at least 20 answers and at least 90% non-Again | 10 Coins | Finalized only after the day closes; history-derivable |
| Perfect Canopy | Complete 30 consecutive eligible answers without Again | 1 Small Charge | Immediate; history-derivable |
| No-Again Day | Close a day with at least 40 answers and no Again | 15 Coins | Finalized only after the day closes; history-derivable |
| All Clear | Complete the first valid all-due day | 5 Coins | Live-only; never backfilled |

## Collection and economy progression

### Plant species

One release-ready starter is free. Each other current species is a one-time
Nursery purchase:

| Species | Coins | Species | Coins |
|---|---:|---|---:|
| Bonsai | 100 | Peony | 300 |
| Rose | 100 | Foxglove | 350 |
| Sunflower | 150 | Japanese Maple | 400 |
| Lavender | 200 | Wisteria | 500 |
| Hydrangea | 250 | Dahlia | 600 |

All current species use the same Growth, stage, reward, and buff rules. Species,
personality, name, and bed position do not change earnings. Moving a plant to
Collection preserves its Growth, timed-item history, and story.

### Garden beds

| Capacity | Cost |
|---|---:|
| Beds 1–2 | Included |
| Bed 3 | 150 Coins |
| Bed 4 | 300 Coins |
| Bed 5 | 500 Coins |
| Bed 6 | 800 Coins |

Beds add placement capacity only; they do not multiply Growth. More planted,
unfinished plants can nevertheless receive more independent 20% passive
allocations.

### Included and compatibility-only items

- Clear Skies, Verdant Twilight, two beds, the ceramic planter style, and the
  Garden Lantern are included. The planter, lantern, and visual placement are
  cosmetic and provide no progression multiplier.
- Existing legacy species remain loadable and keep ordinary plant mechanics,
  but they are not current Nursery stock.
- Grand Growth Charges already present in imported development state remain
  usable, but no active reward or purchase path grants them.

## Explicit non-mechanics

The current system has no Quest or Vitality track, Permanent Streak XP,
variable daily Coin track, guaranteed weekly Growth Charge, separate old
streak-milestone payout, answer-difficulty Growth multiplier, automatic reward
Weather, or watering progression. Seasonal and visibility settings affect
presentation, not the equipped reward rules above.

## Source authority

This reference was reconciled against the current working tree's domain
registries and engine:

- [Game engine](../ankigarden/game.py)
- [Environment and Growth Charge catalogs](../ankigarden/environment.py)
- [Achievement registry](../ankigarden/achievements.py)
- [Garden Find registries and odds](../ankigarden/garden_finds.py)
- [Growth contracts](../ankigarden/growth.py)
- [Schema-21 state](../ankigarden/models/state.py)
- [Detailed progression contract](ui/data_contracts.md)
