# Anki Garden 2.2.0 release notes

> Working-tree release candidate. Automated validation and generated evidence
> do not replace exact-package native, platform, accessibility, or human
> approval.

## Fairer study progression

- Again, Hard, Good, and Easy remain economically equal at 10 base Growth.
- Plant stages now begin at 0/400/2,000/6,000/15,000/35,000 Growth. Full Bloom
  keeps its 120-Coin first-time milestone pool and Small Growth Charge.
- Each other planted bed adds one exact 10% Shared Growth lane, for 150% output
  with six beds. Full Bloom beds continue contributing while another planted
  plant is still growing.
- Garden Rhythm replaces streak Growth: verified Today’s Cards completions
  among the prior seven eligible study days add 0–10% to base Growth without a
  total-reset cliff. Anki streak still grants its recurring Coins and badges.
- Beds 3–6 are earned at Mature and unique Full Bloom milestones rather than
  purchased.

## Equal purchases and card-counted value

- Any one starter is free and every other current species costs 250 Coins.
  Appearance does not change Growth or rewards.
- Basic, Quality, and Magical Fertilizer now grant +1/100, +2/200, and +3/400
  eligible cards. Time outside Anki never consumes purchased value.
- Fertilizer tiers use a persistent FIFO card queue. Booster Potion remains
  +5 for 100 cards, or 125 when activated with Herbalist’s Hourglass.
- Grand Growth Charge now has real achievement routes through Botanical
  Collection and Old Growth.

## Rebalanced Bonuses, Scenery, and Finds

- Displayed Decoration and active Garden Bonus are independent. Displayed
  Scenery and active Scenery Effect are independent. The first eligible answer
  snapshots Garden Rhythm and both mechanical effects for the day.
- Wind Chime remains uncapped; Watering Station is stronger for the first 100
  cards; Hourglass awards a Booster every 30 active completions and extends
  activated Potions by 25 cards.
- Paid Scenery now has distinct short-day, general-Growth, Coin, and delayed
  Charge roles. Firefly Lantern, Prism Trellis, Rainbow Horizon, Halloween
  Garden, Full Moon Garden, and Celestial Eclipse use the canonical 2.2.0
  effects in `balance_catalog.py`.
- Standard Find protection still guarantees an at-least-Uncommon result by
  drought answer 75. The daily cap is now 3 below 200 cards, 4 from 200–399,
  and 5 at 400 or more; capped drought progress pauses and resumes.
- Rare, Very Rare, and Ultra Rare discoveries retain 1-in-2,500/10,000/25,000
  base odds and add 60/180/365-completion guarantees alongside
  10,000/40,000/50,000-card guarantees.

## Longer-term collection

- Thirteen cumulative achievements add earned beds, completion milestones,
  lifetime answer milestones, Grand Charges, and three earned cosmetics to the
  original seven achievements.
- Five cosmetic-only Display Decorations are available for 150–400 Coins.
- Six sequential Garden Landmark projects turn Stored Growth into persistent
  scene transformations after the first Full Bloom.
- Four Cultivation Mastery ranks per species provide cosmetic favorite-plant
  goals after Full Bloom.
- Landmark and Mastery spend Stored Growth and Coins atomically but never add
  recursive Growth, Coin, Find, or loadout-slot power.

## Persistence and migration

- State schema 26 stores exact card-effect queues, immutable daily economy
  snapshots, appearance/effect separation, dual environment pity, earned beds,
  Landmark and Mastery state, and lifetime economy aggregates.
- Permanent answer, Find, discovery, purchase, Charge, Landmark, Mastery, and
  migration identities live independently from bounded UI receipt history.
- Timed Fertilizer converts proportionally to cards with ceiling. Existing paid
  beds remain unlocked and receive their fixed Coin refunds. Recorded plant
  purchases above 250 Coins receive only the difference; cheaper purchases are
  never debited. Rich Compost inventory becomes Basic Fertilizer.
- Existing Full Moon progress carries from the old four-completion cadence to
  the new six-completion cadence proportionally, rounded up so positive earned
  progress is not erased.
- Existing Stored Growth and owned environments are preserved. Migration never
  auto-spends Stored Growth or grants retroactive calendar pity.

The complete current mechanics and catalog are documented in the
[progression, rewards, and effects reference](progression-rewards-effects-reference.md).
