# Anki Garden 2.2.0 release notes

> Working-tree release candidate. Automated validation and generated evidence
> do not replace exact-package native, platform, accessibility, or human
> approval.

## Fairer study progression

- Again, Hard, Good, and Easy remain economically equal at 10 base Growth.
- Plant stages now begin at 0/400/2,000/6,000/15,000/35,000 Growth. Full Bloom
  keeps its first-time milestone pool of 120 Garden Coins and Small Growth Charge.
- Each other planted bed adds one exact 10% Shared Growth lane, for 150% output
  with six beds. Full Bloom beds continue contributing while another planted
  plant is still growing.
- Garden Rhythm replaces streak Growth: verified Today’s Cards completions
  among the prior seven eligible study days add 0–10% to base Growth without a
  total-reset cliff. Anki streak still grants its recurring Garden Coins and badges.
- Beds 3–6 are earned at Mature and unique Full Bloom milestones rather than
  purchased.
- The first eligible answer now grants 4 Garden Coins and Today’s Cards grants
  8, preserving the ordinary completed-day total. Every fifth valid Today’s
  Cards completion adds an automatic Garden Cycle reward of 30 Garden Coins;
  missing days do not reset it.

## Equal purchases and card-counted value

- Any one starter is free and every other current species costs 250 Garden Coins.
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
- Paid Scenery now has distinct short-day, general-Growth, Garden Coin, and delayed
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
  lifetime answer milestones, Grand Charges, and three earned Gardening Trophies to the
  original seven achievements.
- Progress → Trophy Room and the garden house open one Gardening Trophies case.
  The Plaque adds +1 Growth per eligible card, the Journal adds +5 Coins per
  completed review day, and the Trowel raises Shared Growth to 15%. All three
  bonuses activate permanently after unlocking; Growth Charges stay unchanged.
- Five decorative-only paid props are retired. Original artwork and historical
  ownership are preserved; an equipped retired item falls back to Seedling Sign.
- Outdoor decorations use individual ground-contact metadata and subtle shadows.
  Tall props appear in front of the middle bed. Home omits decoration artwork.
- Four cumulative Cultivation Mastery ranks per species provide cosmetic
  favorite-plant goals after Full Bloom; unpaid ranks do not block later Growth
  funding.
- A learner-acknowledged active project receives only final overflow after
  plant routing. Existing Stored Growth can be contributed with a revalidated
  atomic quote, while no-target play preserves the complete reserve.

## Persistence and migration

- State schema 30 retains durable trophy activation boundaries and stores exact card-effect queues, daily Garden Rhythm
  snapshots, unified equipment, dual environment pity, earned beds,
  Garden Cycle, active Growth targets, cumulative project funding
  and claims, and provenance-qualified lifetime economy
  aggregates.
- Scenery and decorations can be equipped throughout the day. Their artwork
  and effects stay together; old pending selections are discarded while
  displayed items, earned rewards, and saved progress are preserved.
- Permanent answer, Find, discovery, purchase, Charge, project, and
  migration identities live independently from bounded UI receipt history.
- Timed Fertilizer converts proportionally to cards with ceiling. Existing paid
  beds remain unlocked and receive their fixed Garden Coin refunds. Recorded plant
  purchases above 250 Garden Coins receive only the difference; cheaper purchases are
  never debited. Rich Compost inventory becomes Basic Fertilizer.
- Existing Full Moon progress carries from the old four-completion cadence to
  the new six-completion cadence proportionally, rounded up so positive earned
  progress is not erased.
- Existing Stored Growth, project claims and partial progress, and
  owned environments are preserved. Migration never auto-spends Stored Growth,
  recharges a claim, grants a retroactive Garden Cycle, or grants retroactive
  calendar pity.

The complete current mechanics and catalog are documented in the
[progression, rewards, and effects reference](progression-rewards-effects-reference.md).
