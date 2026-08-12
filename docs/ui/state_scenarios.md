# UI state scenarios

## Fresh garden and starter

- Schema 16 begins with two unlocked direct-soil spaces, no plants, Clear Skies
  plus Verdant Twilight entitlements, visible environment layers, incomplete
  naming setup, and `starter_selection_complete=false`.
- The first **Open Garden** asks for a Garden name, then automatically opens the
  same Nursery used later.
  Every release-ready species is offered as one free starter; the current bundle
  supplies complete Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony,
  Foxglove, Japanese Maple, Wisteria, and Dahlia lines.
- The selected Seed-stage starter occupies the first space and becomes the
  plant being nurtured. The second space remains empty, and
  `starter_selection_complete` becomes true only after a successful save.
- Card answers completed before starter selection still count toward study
  totals and the Anki streak, but give no plant Growth and are never backfilled.
- If no species is release-ready, Nursery explains that it is stocking plants
  and leaves starter selection incomplete.

## Home preview

- Deck Browser and Overview show the Verdant Twilight scene, nurtured-plant
  Growth, Anki streak, Garden Coins, and one **Open Garden** action.
- Plants, garden spaces, and the Nursery landmark are noninteractive. No card
  counts, collection denominator, milestone ruler, or duplicate actions appear.
- Loading, unavailable, and recoverable-error states retain the normal card
  layout, accessible status semantics, and a working Retry where appropriate.

## Full Garden information hierarchy

- The themed frame integrates the centered Garden name, Progress, and Settings
  above Plant Growth, Anki streak, Garden Coins, and the scene. Rename is in the
  Settings Display tab.
- Plant Growth and Anki streak include relative mini bars. All three metric
  buttons open focused details with exact rules and progress.
- Header **Progress** and the cottage open the same window with Today,
  Achievements, Collection, Weather & Scenery, and How it grows.
- Selecting a plant is the only way to show plant-specific details; the compact
  card keeps Nurture, Fertilize, Move, and Story in a stable order.

## Active study day

- Each supported review-log answer increments answer and accuracy totals and
  immediately credits 10 base Growth plus the current streak, active Fertilizer,
  active Booster, equipped Weather, and equipped Scenery Growth to the
  answer-time nurtured unfinished plant.
- Choosing **Nurture** changes only future routing. Previously earned Growth
  never moves.
- Deck Browser, Overview, full Garden, selected-plant card, and persisted JSON
  agree after refresh.
- Same-day synced answers reconcile against the persisted current-day ID ledger
  and catch up exactly once in revlog order, including a lower ID that arrives
  after a higher one. Prior-day and future/device-skew rows are neither credited
  nor marked processed.

## All due and Garden Coins

- The learner must answer at least one card before all due can award Coins.
- A live collection-wide check includes due reviews and introduced
  learning/relearning steps due before cutoff, including active filtered decks.
- Unseen new, suspended, and buried cards are excluded while unavailable.
  Restoring a due card before completion makes it an obligation; later due work
  never revokes an already-earned award.
- Completion credits the base +10 Garden Coins once and records the reason,
  delta, and resulting internal `currency_balance`. Cloudy Drift adds +2 Coins;
  Rainbow Sunshower adds +5 Growth.
- Streak and plant-stage rewards use the same idempotent ledger. One ordered
  deterministic reward band may grant an environment, Growth Charge, Booster
  Potion, or 50 Garden Coins; it is never replayed from historical reviews.

## Anki streak, Fertilizer, and Booster Potions

- Startup, sync, rollover, and live answers reconstruct the current consecutive
  Anki-day streak from review history. Growth tiers are 0%, 5%, 10%, 15%, 20%,
  and 25% at days 1, 7, 14, 30, 100, and 365.
- Fertilize opens Nursery's Supplements & Boosters tab. Basic, Quality, and
  Magical Fertilizer cards show exact Garden Coin
  cost, +1/+2/+3 Growth per answer, and one/two/four-hour duration.
- Buying the same tier extends its deadline. Choosing another active tier
  requires confirmation that the old remaining time will be discarded.
- Replacement archives the completed portion of the old tier; repurchase after
  expiry retains the old interval. Late same-day answers use the tier active at
  answer time, while pre-activation and expiry-boundary answers receive none.
- Expiration removes only the temporary bonus. Failed or history-cap-blocked
  purchases preserve the previous plant and Garden Coin balance.
- A rare Booster Potion is not sold. It adds +5 Growth per answer for two hours,
  stacks with Fertilizer, and another Potion extends the active interval. Snow
  Flurry and Full Moon add 10% and 25% duration when equipped.
- Small and Standard Growth Charges are repeat purchases for 30 and 125 Coins;
  Grand is earn-only. They add 100, 500, or 2,000 Growth to the nurtured
  unfinished plant, follow stage rewards, cap at Rare, and consume only if the
  state saves.

## Nursery landmark and catalog

- Nursery and the cottage use separate forgiving hit targets and
  silhouette-following hover/focus outlines with anchored in-scene labels.
  Click, Enter, or Space opens Nursery or Garden Progress.
- Move mode disables both landmarks. Home and Settings previews never expose
  them as actions.
- Nursery tabs are **Plants**, **Supplements & Boosters**, **Permanent
  Upgrades**, and **Weather & Scenery**. Plants retains computed
  ownership/availability counts with no
  hard-coded roster denominator and provides an artwork carousel for all stages.
- A configured species appears for selection or purchase only when all six
  Verdant Twilight V6 stages are local, release-preferred, geometry-valid
  `direct_soil` assets. Incomplete lines remain hidden.
- An already-owned legacy species remains visible, plantable, and progress-safe
  even when it is not currently stocked.
- Shelving preserves Growth, memories, Fertilizer, and Booster state. The plant currently being
  nurtured must be changed before it can be shelved.
- Space unlocks are contiguous and transactional. All six V6 spaces accept
  direct-soil plants.

## Weather, Scenery, and reward Collection

- Nursery offers only free/purchasable environment choices. Each one-time
  purchase is transactional and remains unequipped until the learner chooses it
  in the cottage's Weather & Scenery tab.
- Collection shows one equipped Weather and one Scenery, independent visual
  switches, every passive/how-to-earn entry, exact ordered drop odds, and the
  current Ultra pity denominator. Locked drop-only art is a silhouette; its
  rules are not hidden.
- Equipped passives stack. Turning off a visual layer does not turn off its
  passive. Weather, Scenery, and Charge Growth remain separate in details.
- Daily Scenery gifts require that day's first eligible answer, use the answer's
  sole reward slot, and never backfill. Halloween chooses Small 70%, Standard
  25%, or Booster 5%.
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
  diagnostics plus temporary confirm/back up/populate/restore development tools.
- Wide layout places controls beside preview; compact layout stacks and scrolls.
  Reduced motion is honored without hiding information.

## Migration, invalid data, and failures

- Schema 15 development state upgrades to schema 16 with neutral environment
  entitlements, visibility, zero Charges, daily claims, Ultra pity, and separate
  Growth-source defaults. Older supported
  schemas continue through the established stage/ledger migration boundary. An
  atomic current-day ID-ledger seed prevents duplicate or missed out-of-order
  synced answers across restarts. Cutoff, database, backup, and state-write
  failures preserve the original data and retry without advancing review state.
- The first transition to scene geometry 6 refreshes incompatible visual
  placement only; it does not change plant progression. The migration notice
  explains any plant returned to Collection.
- Schema 16 repairs bounded numeric values, duplicate IDs/species/slots, invalid
  `active_plant_id`, and malformed story/economy/reward records.
- Unreadable state is copied to `garden_state.invalid.json`; other unsupported
  schemas are backed up before recovery.
- Failed state or settings writes restore the prior in-memory value. Due-data
  failure grants no all-due reward. Missing artwork preserves the named plant,
  stage, and progression through fallback rendering.
