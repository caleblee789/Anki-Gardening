# Anki Garden 2.2.0 release notes

> Unpublished 2.2.0 release candidate. The release owner accepted the current
> progression pacing on September 9, 2026, including high-volume completion
> within 30 days. No reward rules or balance values changed for that decision.
> Automated checks do not replace exact-package functional and visual acceptance
> or human release approval. Publication remains a separate action.

Final progression validation keeps all balance values unchanged. The fresh,
collection-first median at 200 answers/day is **103 days**, within the approved
90–120-day target. The [final progression report](../build/progression-finalization-20260912-235734/report.md)
contains simulation, test, production-engine, and exact-package evidence.
This is progression sign-off only; overall release approval remains separate.

## Clearer Garden and reward panels

- Naming the garden in Settings before choosing a starter preserves onboarding
  and its one-time welcome gift.
- Purchase receipts preserve capitalization in item effects and later sentences.
- Repeatedly closing the welcome screen no longer reports a false save failure.
- Fertilizer tooltips describe the active tier correctly, and growth-stage
  announcements do not repeat the same species name.

- Fresh gardens correctly show a zero-day streak until the first studied card.

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
- Streak achievements permanently unlock total base-card Growth bonuses of 5%,
  10%, 15%, and 20% at 7, 30, 100, and 365 consecutive study days. The highest
  unlocked tier remains after a streak ends and replaces Garden Rhythm and the
  former streak-dependent Growth tiers.
- Beds 3–6 are earned at Mature and unique Full Bloom milestones rather than
  purchased.
- The first eligible answer grants 4 Garden Coins. Finish all cards due today
  grants 16 core Garden Coins, once daily through the existing completion check.
  The global five-completion cycle and independent weekly streak Coins are gone.
  Activity combines daily rewards and retained Growth progress in one Study
  rewards panel; Achievements shows the full ladder in three columns where space
  permits.

## Equal purchases and card-counted value

- Any one starter is free and every other current species costs 250 Garden Coins.
  Appearance does not change Growth or rewards.
- Basic, Quality, and Magical Fertilizer now grant +1/100, +2/200, and +3/400
  eligible cards. Time outside Anki never consumes purchased value.
- Fertilizer tiers use a persistent FIFO card queue. Booster Potion remains
  +5 Growth per card for 100 cards, regardless of owned scenery or decorations.
- Grand Growth Charge now has real achievement routes through Botanical
  Collection and Old Growth.

## Rebalanced Bonuses, Scenery, and Finds

- Equipping an item saves its artwork and bonus together. Previewing an item
  does not activate its bonus; hiding its artwork does not disable the bonus.
- Wind Chime remains uncapped; Watering Station grants +1 Growth every second card
  among the first 200 each day.
- Herbalist’s Hourglass: Finish all cards due on 15 days: +1 Booster Potion.
  Full Moon Garden: Finish all cards due on 4 days: +1 Booster Potion.
  Both rewards repeat; the days need not be consecutive. Ownership no longer
  extends Potion duration.
- Autumn Hearth: Earn 15% more Coins. The bonus applies once to newly earned
  gameplay Coins while active, with fractional value retained between awards.
- Snow-Covered Garden: Finish all cards due today: +50 Growth. This replaces
  the stored 100-Growth charge awarded every two completed days.
- Every scenery and decoration has one complete effect line generated from
  `balance_catalog.py`. Halloween Garden: Finish all cards due today: 1 mystery
  gift. Its contents and probabilities are unchanged.
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

- State schema 30 retains durable trophy activation boundaries and stores exact card-effect queues, daily reward
  records, unified equipment, dual environment pity, earned beds,
  permanent achievement tiers, active Growth targets, cumulative project funding
  and claims, and provenance-qualified lifetime economy
  aggregates.
- Scenery and decorations retain their appearance controls, active-bonus
  eligibility, and daily reward limits.
- Permanent answer, Find, discovery, purchase, Charge, project, and
  migration identities live independently from bounded UI receipt history.
- Timed Fertilizer converts proportionally to cards with ceiling. Existing paid
  beds remain unlocked and receive their fixed Garden Coin refunds. Recorded plant
  purchases above 250 Garden Coins receive only the difference; cheaper purchases are
  never debited. Rich Compost inventory becomes Basic Fertilizer.
- Existing Stored Growth, project claims and partial progress, and
  owned environments are preserved. Migration never auto-spends Stored Growth,
  recharges a claim or grants retroactive
  calendar pity.

The complete current mechanics and catalog are documented in the
[progression, rewards, and effects reference](progression-rewards-effects-reference.md).
