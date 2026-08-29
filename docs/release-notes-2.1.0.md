# Anki Garden 2.1.0 release notes

## Garden progression and rewards

- Every eligible completed card grants 10 base Growth. The active-streak bonus
  remains 0/5/10/15/20/25% at days 1/7/14/30/100/365. Again, Hard, Good, and
  Easy give equal ordinary Growth, so cards should be rated honestly.
- The nurtured unfinished plant receives full Answer Growth. Every other
  planted plant creates an exact 20% Shared Growth share. A Full Bloom plant’s
  share divides among planted plants still growing, so six planted beds retain
  200% output while any plant remains unfinished.
- Earned Growth can no longer disappear at a plant cap or when no plant is
  selected. Overflow continues through eligible plants or becomes Stored
  Growth. Growth Charges and Garden Finds grant Instant Growth with the same
  no-loss routing.
- Plant stage Coin pools are now distributed across 25%, 50%, 75%, and
  completion checkpoints. Full Bloom also grants a Small Growth Charge, a
  permanent collection record, completion details, and automatic continuation
  to the next unfinished plant.
- The first eligible completed card of each Anki day grants 2 Garden Coins.
  Every seventh consecutive active day grants 10 Coins. Completing Today’s
  Cards grants 10 Coins and the locked Scenery completion gift once that day.
  The first valid completion also grants the one-time 5-Coin **Review Day
  Complete** achievement.
- Rating-based achievements and their economic rewards have been removed.
  Existing streak, volume, plant, Find, collection, and completion milestones
  remain safe to pursue without changing Anki ratings. Historical recognition
  appears as one **Legacy Harvest**, capped at 500 historical Coins and no
  historical consumables.
- Standard Garden Finds retain rising protection, a finite guarantee, and a
  three-per-day cap. The guaranteed Find is at least Uncommon. The full Garden
  may explain those mechanics; the persistent Reviewer shows a Find only when
  it is committed and never shows cap, protection, or gap counters.
- Rare, Very Rare, and Ultra environment discoveries now have separate finite
  guarantees at 5,000, 20,000, and 50,000 eligible cards. Random ownership no
  longer creates an unbounded wait.
- Weather and Scenery are chosen for an Anki day. The first progression event
  locks both artwork and mechanics; later changes are **Queued for tomorrow**.
  Environment power is normalized, including capped Celestial Eclipse and a
  meaningful Rainbow Sunshower completion award.
- Fertilizer uses wall-clock time to reward faster review: Basic grants +1 for
  one hour, Quality +2 for two hours, and Magical +3 for four hours. The same
  tier extends; another tier queues without losing duration. Booster Potions
  remain card-counted.
- Rich Compost grants Basic Fertilizer. Booster Potions remain Find or Scenery
  gifts rather than Nursery purchases. Small and Standard Growth Charges remain
  available; imported Grand Charges remain usable.
- Stable completed-card identities, reward-event keys, and normalized ledger
  rows prevent duplicate Growth or rewards across retry, restart, sync, and
  rerender. Correlation IDs group related receipts for presentation.

Earlier development designs for Permanent Streak XP, a variable daily Coin
track, a separate study target, a guaranteed weekly Small Growth Charge, a
separate streak-milestone subsystem, a day-14 payout, and ordered random-drop
bands are not part of this release.

## Interface overhaul

- The fixed-height Home preview now keeps only the Garden name, nurtured plant,
  Growth, and **Open Garden** across ready, loading, stale, error, and disabled
  states. Today’s Cards, Anki streak, and Garden Coins remain in the full Garden
  and Garden Progress, and **Open Garden** stays reachable after render failure.
- Starter setup shows cost and consequences before confirmation, keeps
  placement transactional, reports unchanged committed state on failure, and
  finishes with a concise setup receipt.
- The Garden dashboard preserves metrics across responsive widths, anchors
  plant details when safe, docks them when measured content cannot fit, and
  gives move, swap, starter, and Collection placement sessions stale-callback
  protection.
- Plant Story, Garden Progress, Achievements, reward history, Garden Finds,
  Garden Coins, Collection, Nursery, loadout, Fertilizer, purchase, and Growth
  Charge surfaces now share scheduled content fitting, one overflow owner,
  normal-flow feedback/footer, compact button variants, focus, and typed
  transaction-state contracts.
- Reward surfaces consume committed projections from
  `ankigarden.reward_presentation`; UI components no longer reconstruct reward
  eligibility, thresholds, amounts, or earned state.
- Collection search, sort, status, and category controls reflow without a
  horizontal chip scroller. Species, environment, consumable, missing-art, and
  empty-result cards retain structured non-color status cues.
- Nursery uses a canonical 950 px family width, tab-specific fitted heights,
  responsive three-to-two-column cards, and one feedback host below the tabs.
  Purchase receipts use **Place in Garden**, **View Collection**, and
  **View Garden** without overlaying the catalog.
- Stale purchase balance refresh keeps the affordable confirmation visible with
  a **Balance updated** chip; Growth Charges show **Availability updated** and a
  structured Seed → Sprout receipt without duplicating transaction logic.
- Settings uses staged edits, an accurate unsaved-change count, compact
  Discard/Save actions, Restore defaults, dirty-close protection, validation,
  **Reduce animations**, a default-on **Show reviewer HUD** setting, the
  separate **Show reviewer rewards** setting for active major dock reveals, and a
  read-only **Diagnostics** tab. Production mutation controls remain excluded.
- The persistent reviewer HUD hugs its content and shows global Today’s Cards,
  prominent plant/checkpoint progress, next-answer Growth, and compact active
  effects. It hides raw routing, environment names, Find limits, and irrelevant
  Stored Growth while retaining those exact typed facts for detailed views.
- Correlated rewards are consolidated into one integrated dock bundle with one
  event-specific hero, at most two categorized summaries, and an exact
  event-ID-backed remainder action. Full Bloom suppresses redundant intermediate
  stages in the compact view; routine Growth briefly shows **Growth applied**
  and updates a zero-free **This session** footer without opening a full reveal.
  Leaving the reviewer produces a local session summary using cards
  complete and committed Growth, Coins, Finds, crossings, Stored Growth, and
  remaining Fertilizer time and Booster cards.

The proposed four-theme system and every downstream palette matrix are outside
this release. Anki Garden retains its established styling.

## Persistence and development-state compatibility

- Schema 22 retains the verified SQLite reward database as the authoritative
  state and idempotency boundary. Schema-21 JSON and SQLite profiles are backed
  up before migration.
- Reward receipts, processed cards, completed-card lineages, finalized days, Garden
  Find outcomes/counts, and replay authorities are normalized while bounded
  presentation caches remain available to the UI.
- Migrated state preserves plants, exact Growth, Stored Growth, checkpoints,
  Full Bloom records, onboarding, purchases, Growth Charges, entitlements,
  locked/queued loadouts, environment guarantees, timed Fertilizer queues,
  card-counted Booster effects, and Today’s Cards state. Read, backup, or save
  failure remains fail-closed. The
  add-on has no released-user migration base.

## Release validation status

Automated source, simulation, and package gates must pass before live capture.
Exact-package Anki startup, restart, interactive acceptance, the v25
registry-derived representative preflight and complete full-profile
canonical-100%-scale final capture, same-process clean-shutdown evidence,
geometry validation, full-resolution visual
review, final archive path, and SHA-256 belong to the immutable capture report
for the final combined package. The preflight may seed unchanged overlapping
states, but cannot substitute for the final full-profile evidence. Additional
125%, 150%, and 200% screenshot matrices remain a separate platform gate. Native
Windows/Linux, 125%/150%, true OS scaling, forced colors, screen-reader, and
broader human/device acceptance remain separate unless actually run. This note
does not substitute for that evidence.
