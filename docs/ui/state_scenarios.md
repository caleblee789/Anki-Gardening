# UI state scenarios

## Fresh garden and starter

- Schema 21 begins with two unlocked direct-soil spaces, no plants, Clear Skies
  plus Verdant Twilight entitlements, visible environment layers,
  `starter_selection_complete=false`, and onboarding at `introduction`.
- Anki Home is the unnumbered entry/resume surface. The Garden counts six saved
  steps: introduction, Starter Nursery, confirmation, placement, nurture
  selection, and completion. Closing a dialog or Anki preserves the current
  step; `Not now` appears only where resuming is safe.
- Every release-ready species is offered as one free starter; the current bundle
  supplies complete Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony,
  Foxglove, Japanese Maple, Wisteria, and Dahlia lines.
- Species choice and confirmation do not create a plant. Placement atomically
  creates the Seed-stage starter in the selected unlocked bed. Nurture then
  atomically makes it active; completion saves `done` before either destination
  action. The other unlocked space remains empty.
- Card answers completed before starter selection still count toward study
  totals and the Anki streak, but receive no retroactive plant Growth or
  recurring rewards. Reliably reconstructable one-time achievements are handled
  separately by authoritative history reconciliation.
- If no species is release-ready, Nursery explains that it is stocking plants
  and leaves starter selection incomplete.

## Home preview

- Deck Browser and Overview show the Verdant Twilight scene, nurtured-plant
  Growth, today's answer count, Anki streak, Garden Coins, the closest locked
  immediate achievement when useful, and one **Open Garden** action.
- Plants, garden spaces, and the Nursery landmark are noninteractive. No card
  collection denominator, milestone ruler, or duplicate actions appear.
- Loading, empty, disabled, success, stale, and recoverable-error states use one
  preview snapshot. Stale content retains the last valid scene and adds a text
  updating indicator. Background, weather, scenery, plants, foreground, and
  watering can share one fade/effects layer.

## Full Garden information hierarchy

- The themed frame gives the elided Garden name the primary title position,
  followed by Garden Progress, Collection, and secondary Settings navigation
  above Plant Growth, Anki streak, Garden Coins, and the scene. Rename is in the
  Settings Display tab.
- Plant Growth and Anki streak include relative mini bars. All three metric
  buttons open focused details with exact rules and progress.
- Header **Garden Progress** opens its primary page. Header **Collection** and
  the cottage reuse that window and select Collection without duplicates.
- Selecting a plant is the only way to show plant-specific details; the compact
  card keeps Nurture, Fertilize, Growth Charge, Move, and Story in a stable
  order.

## Active study day

- Each supported review-log answer increments answer and accuracy totals and
  credits 10 base Growth plus the current streak, active Fertilizer, active
  Booster, equipped Weather, and equipped Scenery Growth to the answer-time
  nurtured unfinished plant. Every other planted, unfinished plant receives an
  exact 20% allocation carried in persisted fifths. Direct Garden Find Growth
  goes only to the nurtured plant, with no streak modifier or passive fan-out.
- Choosing **Nurture** changes only future routing. Previously earned Growth
  never moves.
- Deck Browser, Overview, full Garden, selected-plant card, and the persisted
  schema-21 state snapshot agree after refresh.
- Same-day synced answers reconcile against the persisted current-day ID ledger
  and catch up exactly once in revlog order, including a lower ID that arrives
  after a higher one. Prior-day and future/device-skew rows are neither credited
  nor marked processed.

## All due and Garden Coins

- The learner must record at least one eligible answer before all due can award
  Coins.
- A live collection-wide check includes due reviews and introduced
  learning/relearning steps due before cutoff, including active filtered decks.
- Unseen new, suspended, and buried cards are excluded while unavailable.
  Restoring a due card before completion makes it an obligation; later due work
  never revokes an already-earned award.
- Completion credits the base +10 Garden Coins once and records the reason,
  delta, and resulting internal `currency_balance`. Cloudy Drift adds +2 Coins;
  Rainbow Sunshower adds +5 Growth.
- The first eligible answer grants +2 Garden Coins, every seventh consecutive
  eligible day grants +10, and day 7 integrates that recurring payout with its
  one-time achievement. The first valid all-due completion also grants the
  separate +5 All Clear achievement reward.
- A Standard Garden Find uses the centralized registry, persistent drought
  protection, and a three-per-Anki-day cap. Its independent environment pool
  retains the configured rare tiers and Ultra pity. Either pool may stack with
  the other and with predictable rewards, but stable answer/pool identities are
  consumed exactly once and pre-activation history is never rolled.

## Garden Coin purchase confirmation and replay

- Every Coin purchase opens one shared confirmation with artwork/fallback,
  item/category/quantity, current and resulting balance, exact mechanics, and
  target where applicable. Cancel owns initial focus and Escape closes safely.
- Confirmation revalidates item availability, ownership, price, balance,
  target, Fertilizer state, and next-bed identity. Changed terms are shown as a
  typed stale state and never silently committed.
- Debit, grant/application/unlock, feedback, and completed-request record save
  in one snapshot transaction. Persistence failure restores every in-memory
  field and leaves the request safely retryable.
- Repeating a successful UUID with identical canonical terms returns the stored
  receipt without another debit or grant. Reusing that UUID with different
  terms fails closed.
- Receipts show the item, spend, new balance, disposition, and direct next
  action. Typed errors distinguish insufficient Coins, persistence failure,
  unavailable/already-owned items, invalid targets, stale price/balance, and
  request-ID conflict.

## Anki streak, Fertilizer, and Booster Potions

- Startup, sync, rollover, and live answers reconstruct the current consecutive
  Anki-day streak from review history. Growth tiers are 0%, 5%, 10%, 15%, 20%,
  and 25% at days 1, 7, 14, 30, 100, and 365.
- Fertilize opens the dedicated Fertilizer dialog. Basic, Quality, and Magical
  cards show exact Garden Coin
  cost, +1/+2/+3 Growth per answer, and one/two/four-hour duration.
- Purchasing the same tier extends its deadline. Purchasing another active
  tier requires confirmation that the exact remaining time will be discarded.
- Replacement archives the completed portion of the old tier; repurchase after
  expiry retains the old interval. Late same-day answers use the tier active at
  answer time, while pre-activation and expiry-boundary answers receive none.
- Expiration removes only the temporary bonus. Failed or history-cap-blocked
  purchases preserve the previous plant and Garden Coin balance.
- A rare Booster Potion is not sold. It adds +5 Growth per answer for two hours,
  stacks with Fertilizer, and another Potion extends the active interval. Snow
  Flurry and Full Moon add 10% and 25% duration when equipped.
- Small and Standard Growth Charges are repeat purchases for 30 and 125 Coins;
  Grand is not currently obtainable. If already present in imported development
  state, it remains usable. They add 100, 500, or 2,000 Growth to any selected
  owned, planted, unfinished plant, follow stage rewards, cap at Rare, and
  consume only if the state saves. They receive no study modifier or passive
  fan-out.

## Nursery landmark and catalog

- Nursery and the cottage use separate forgiving hit targets and
  silhouette-following hover/focus outlines with anchored in-scene labels.
  Click, Enter, or Space opens Nursery or Garden Progress.
- Move mode disables both landmarks. Home and Settings previews never expose
  them as actions.
- Nursery tabs are **Plants**, **Fertilizer and Boosters**, **Garden Spaces**,
  and **Weather and Scenery**. Plants retains computed
  ownership/availability counts with no
  hard-coded roster denominator and provides an artwork carousel for all stages.
- A configured species appears for selection or purchase only when all six
  Verdant Twilight V6 stages are local, release-preferred, geometry-valid
  `direct_soil` assets. Incomplete lines remain hidden.
- An already-owned legacy species remains visible, plantable, and progress-safe
  even when it is not currently stocked.
- Moving to Collection preserves Growth, memories, Fertilizer, and Booster
  state. The plant currently being nurtured must be changed before it can be
  moved to Collection.
- Space unlocks are contiguous and transactional. Only the next bed is priced
  and enabled; its confirmation revalidates the next index before debit. All
  six V6 spaces accept direct-soil plants.

## Weather, Scenery, and reward Collection

- Nursery offers only free/purchasable environment choices. Each one-time
  purchase is transactional and remains unequipped until the learner chooses it
  through Collection's loadout detail.
- Collection shows one equipped Weather and one Scenery, every exact
  function/buff/activation/duration/stacking/replacement/unlock rule, ordered
  drop odds, and the current Ultra pity denominator. It owns reversible
  previews plus atomic equipment and visibility changes. Locked Find-only art
  is a silhouette; its rules are not hidden.
- Equipped passives stack. Turning off a visual layer does not turn off its
  passive. Weather, Scenery, and Charge Growth remain separate in details.
- Daily Scenery gifts require that day's first eligible answer and never
  backfill. They keep independent event identities and do not suppress either
  Garden Find pool. Halloween chooses Small 70%, Standard 25%, or Booster 5%.
- Ultra pity has no guarantee, improves stepwise after 75,000 misses to no better
  than 1 in 50,000, and resets only when an Ultra environment is obtained.

## Plant selection and direct Move

- Default plants have no emphasis; hover or keyboard focus adds a restrained
  highlight without opening information or moving artwork.
- Clicking visible art selects one plant, applies stronger stationary emphasis,
  and opens the compact card. Another plant transfers selection; outside click
  or Escape dismisses it.
- **Move** closes inspection and highlights valid scene spaces. Choosing an
  empty space moves; choosing an occupied space swaps; a locked space rejects.
- A valid destination saves immediately. There is no destination dropdown or
  Done action. Escape or Cancel exits before placement, failed save restores the
  prior arrangement, and temporary **Undo** restores the latest committed move.
- Overlap hit testing selects the visually topmost plant. Plant hit regions and
  move-space targets remain distinct.

## Plant Story

- The compact hero shows artwork, editable name, species, stage, planted date,
  total Growth, and whether the plant is being nurtured.
- The pencil control opens inline rename; Escape cancels editing and a failed
  save leaves the old name intact.
- Semantic memories render oldest to newest with local dates. A new plant gets
  a warm early-story message rather than a large empty panel.
- **Up next** describes the next growth stage and approximate base card answers,
  or the fully-grown continuation message at Rare.

## Settings

- Verdant Twilight appears as a read-only current-style card beside a real,
  noninteractive garden preview.
- Applicable Garden display and notification choices remain. Weather/Scenery,
  art quality/detail/performance, animation, and **Fine tune** controls are
  absent; balanced art and reduced-motion behavior are automatic.
- Staged controls update the preview immediately without changing persistence.
  **Cancel** restores persisted values; **Restore defaults** only stages
  defaults; **Save settings** commits once and shows a temporary confirmation.
- **Troubleshooting** remains a separate tab with refreshable, copyable display
  diagnostics. The production package has no state-mutation controls; temporary
  confirm/back up/populate/restore tools appear only in an explicitly built,
  disposable capture package.
- Wide layout places controls beside preview; compact layout stacks and scrolls.
  Reduced motion is honored without hiding information.

## Migration, invalid data, and failures

- Schema 15 development state gains the schema-16 neutral environment
  entitlements, visibility, zero Charges, daily claims, Ultra pity, and separate
  Growth-source defaults. Schema 16 then upgrades to schema 17 with resumable
  onboarding: empty gardens start at introduction, planted incomplete starters
  resume at nurture, and established Gardens migrate to done. Older supported
  schemas continue through the established stage/ledger migration boundary.
  Schema 17 then upgrades through the purchase, loadout, and exact-fifths Growth
  boundaries in schemas 18-20. Schema 21 imports the migrated state into a
  verified SQLite reward database, preserves a pre-SQLite JSON backup, and
  normalizes reward events, answer lineages, Find outcomes, and finalized days.
  Cutoff, database, backup, and state-write failures preserve the original data
  and retry without advancing review state.
- The first transition to scene geometry 6 refreshes incompatible visual
  placement only; it does not change plant progression. The migration notice
  explains any plant returned to Collection.
- Schema 21 repairs bounded numeric values, duplicate IDs/species/slots, invalid
  `active_plant_id`, and malformed story/economy/reward records.
- Unreadable state is copied to `garden_state.invalid.json`; other unsupported
  schemas are backed up before recovery.
- Failed state or settings writes restore the prior in-memory value. Due-data
  failure grants no all-due reward. Missing artwork preserves the named plant,
  stage, and progression through fallback rendering.
