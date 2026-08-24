# Anki Garden 2.1.0 release notes

## Garden progression and rewards

- Every eligible answer grants 10 base Growth. The active-streak bonus is
  0/5/10/15/20/25% at days 1/7/14/30/100/365. The nurtured unfinished plant
  receives the full committed award, while each other planted unfinished plant
  receives an exact 20% allocation with persisted fifths.
- Garden Find Growth is intentionally different. It is direct Growth to the
  answer-time nurtured plant, receives no streak modifier, and never fans out.
- The first eligible answer of each Anki day grants 2 Garden Coins. Every
  seventh consecutive eligible day grants 10; day 7 is the same payout as the
  one-time 7-Day Anki Streak achievement, never a duplicate award.
- Finishing a valid all-due day grants 10 Garden Coins once that day. A valid
  result requires at least one due card at the start and at least one eligible
  answer. The first valid completion also unlocks live-only All Clear for 5
  additional Coins.
- Ten one-time achievements use one shared registry. Streak rewards are +10 at
  day 7, +100 and one Small Growth Charge at day 30, +300 at day 100, and +1,000
  at day 365. Century Day grants +25 Coins; Deep Roots grants one Standard
  Growth Charge; Clear Recall grants +10 Coins; Perfect Canopy grants one Small
  Growth Charge; No-Again Day grants +15 Coins; and All Clear grants +5 Coins.
  Only the nine reliably derivable achievements may be reconstructed from
  history. All Clear and every recurring reward remain live-only. Historical
  Growth, stage rewards, Garden Finds, Fertilizer, Booster Potions, and
  repeatable consumables are never backfilled.
- Garden Finds replace the obsolete answer-drop loop. The Standard pool has
  drought protection, a three-per-day cap, registry-driven rewards, and a
  guaranteed 75th drought answer. The independent environment pool grants only
  unowned Weather or Scenery and retains stepped Ultra pity.
- Rich Compost grants one Basic Fertilizer consumable. Existing Fertilizer,
  Booster Potion, Growth Charge, environment, and purchase services remain the
  only owners of item effects and transactions. Booster Potions are not sold in
  the Nursery; they are earned from the Standard Garden Find pool or eligible
  daily Scenery rewards.
- Small and Standard Growth Charges remain current acquisition paths. A Grand
  Growth Charge is not currently obtainable. If one is present in imported
  development state, it remains usable.
- Stable answer identities, reward-event keys, and normalized ledger rows
  prevent duplicate Growth or rewards across reanswer, retry, restart, sync,
  and rerender. Correlation IDs group related receipts for presentation.

Earlier development designs for Permanent Streak XP, a variable daily Coin
track, a guaranteed weekly Small Growth Charge, a separate streak-milestone
subsystem, a day-14 payout, and ordered random-drop bands are not part of this
release.

## Interface overhaul

- The fixed-height Home preview now keeps only the Garden name, nurtured plant,
  Growth, and **Open Garden** across ready, loading, stale, error, and disabled
  states. Today, Anki streak, and Garden Coins remain in the full Garden and
  Garden Progress, and **Open Garden** stays reachable after render failure.
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
  **Reduce animations**, **Show reviewer rewards**, and a separate read-only
  **Diagnostics** tab. Production mutation controls remain excluded.

The proposed four-theme system and every downstream palette matrix are outside
this release. Anki Garden retains its established styling.

## Persistence and development-state compatibility

- Schema 21 installs a verified SQLite reward database as the authoritative
  state and idempotency boundary. Legacy JSON is backed up and imported
  atomically.
- Reward receipts, processed answers, answer lineages, finalized days, Garden
  Find outcomes/counts, and replay authorities are normalized while bounded
  presentation caches remain available to the UI.
- Imported development state preserves plants, exact passive residuals,
  onboarding, purchases, Growth Charges, loadout, entitlements, intervals, and
  scheduler-day state. Read, backup, or save failure remains fail-closed. The
  add-on has no released-user migration base.

## Release validation status

Automated source, simulation, and package gates must pass before live capture.
Exact-package Anki startup, restart, interactive acceptance, the complete v21
126-surface/17-sheet canonical-100%-scale capture, geometry validation,
full-resolution visual
review, final archive path, and SHA-256 belong to the immutable capture report
for the final combined package. Resize, breakpoint, 150%, and 200% screenshot
duplicates are excluded; responsive geometry remains automated. Native
Windows/Linux, 125%/150%, true OS scaling, forced colors, screen-reader, and
broader human/device acceptance remain separate unless actually run. This note
does not substitute for that evidence.
