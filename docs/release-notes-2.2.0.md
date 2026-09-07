# Anki Garden 2.2.0 release notes

> Unreleased 2.2.0 release candidate. Public distribution remains on hold because the
> protected progression audit includes all-ten-species finishes by day 30.
> See the [combined integration report](ui/combined-integration-20260906.md).
> Automated checks do not replace exact-package native or human approval.

## Clearer Garden and reward panels

- Collection combines species and plant details in one panel. Appearance shares
  a single preview, Equip action, and Undo for scenery and decorations.
- The compact reviewer stays a narrow vertical strip. Earned items, milestones,
  Coins, and Growth appear inside it in priority order, with concise labels.
- Review, session, and sync panels share Coins, Growth, and Discoveries totals,
  consistent reward artwork, and matching rarity colors. Rare rewards briefly
  pulse; item artwork has no persistent glow.
- Session reward details remain visible. Today’s cards stay in Progress, leaving
  the review and session panels focused on the plant and earned rewards.
- Garden onboarding, plant placement, Shop, supplies, Progress, trophies, and
  Settings have tighter layouts and clearer actions. Plant artwork retains its
  authored proportions and grounding.
- Hover feedback settles quickly, static scenes stop unnecessary repainting,
  and bounded artwork caches reduce repeated reviewer rendering.

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
  +5 for 100 cards. Owning Herbalist’s Hourglass or Full Moon Garden adds
  25 cards to new Potions for each, up to 150 cards when both are owned.
- Grand Growth Charge now has real achievement routes through Botanical
  Collection and Old Growth.

## Rebalanced Bonuses, Scenery, and Finds

- Equipping scenery or a decoration saves its artwork and effect together.
  Previewing an item changes neither. Garden Rhythm retains its automatic
  daily snapshot.
- Wind Chime remains uncapped; Watering Station grants +1 Growth every second card
  among the first 200 each day; Hourglass awards a Booster every 30 active completions and extends
  activated Potions by 25 cards.
- Paid Scenery now has distinct short-day, general-Growth, Garden Coin, and delayed
  Charge roles. Firefly Lantern, Prism Trellis, Rainbow Horizon, Halloween
  Garden, Full Moon Garden, and Celestial Eclipse use the canonical 2.2.0
  effects in `balance_catalog.py`.
- Standard Find protection still guarantees an at-least-Uncommon result by
  drought answer 75, with no daily Standard Find limit. Saved drought progress
  resumes on the next eligible answer, and earlier outcomes stay unchanged.
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
- Cultivation Mastery and Garden Legacy join Landmarks as deferred features.
  Saved funding, claims, and selections remain intact; new progress and spending
  are disabled, and their controls, artwork overlays, and reward details are hidden.
- Final overflow after planted plants becomes Stored Growth. Its existing bottle
  icon and positive balance appear beside Coins on Garden and in relevant expanded
  reviewer states. Zero balances disappear completely. Stored Growth cannot be spent
  in this version; receipts show the amount added by each reward.

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
