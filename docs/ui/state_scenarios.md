# UI state scenarios

## Fresh garden and starter

- Schema 14 begins with two unlocked direct-soil spaces, no plants, and
  `starter_selection_complete=false`.
- The first **Open Garden** automatically opens the same Nursery used later.
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

- The permanent strip contains exactly Plant Growth, Anki streak, and Garden
  Coins, each with a one-sentence explanatory tooltip.
- **Progress** begins collapsed. Expanding it reveals Today, Achievements,
  Collection, detailed Growth/all-due information, and recent Garden Coin
  credits or spends.
- Selecting a plant is the only way to show plant-specific details; the compact
  card keeps Nurture, Fertilize, Move, and Story in a stable order.

## Active study day

- Each supported review-log answer increments answer and accuracy totals and
  immediately credits 10 base Growth plus the current streak bonus and active
  Fertilizer Growth to the answer-time nurtured unfinished plant.
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
- Completion credits +10 Garden Coins once and records the reason, delta, and
  resulting internal `currency_balance`.
- Streak and plant-stage rewards use the same idempotent ledger. No card answer
  grants Garden Coins directly.

## Anki streak and Fertilizer

- The first answer starts or continues the Anki streak; a missed Anki day resets
  the next streak to day 1. Growth tiers are 0%, 5%, 10%, 15%, 20%, and 25% at
  days 1, 7, 14, 30, 100, and 365.
- Fertilize opens Basic, Quality, and Premium cards showing exact Garden Coin
  cost, +1/+2/+3 Growth per answer, and one/two/four-hour duration.
- Buying the same tier extends its deadline. Choosing another active tier
  requires confirmation that the old remaining time will be discarded.
- Replacement archives the completed portion of the old tier; repurchase after
  expiry retains the old interval. Late same-day answers use the tier active at
  answer time, while pre-activation and expiry-boundary answers receive none.
- Expiration removes only the temporary bonus. Failed or history-cap-blocked
  purchases preserve the previous plant and Garden Coin balance.

## Nursery landmark and catalog

- The full-Garden Nursery entrance has a restrained hover/focus glow, pointer,
  accessible name, and **Open Nursery** tooltip. Click, Enter, or Space opens
  Nursery and dismisses an open plant card.
- Move mode disables the landmark. The home and Settings previews never expose
  it as an action.
- Nursery shows **Your plants** and **Available now**, plus computed collection
  and availability counts with no hard-coded roster denominator.
- A configured species appears for selection or purchase only when all six
  Verdant Twilight V6 stages are local, release-preferred, geometry-valid
  `direct_soil` assets. Incomplete lines remain hidden.
- An already-owned legacy species remains visible, plantable, and progress-safe
  even when it is not currently stocked.
- Shelving preserves Growth, memories, and Fertilizer. The plant currently being
  nurtured must be changed before it can be shelved.
- Space unlocks are contiguous and transactional. All six V6 spaces accept
  direct-soil plants.

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
- Garden display and Motion are primary. Artwork detail, weather motion, and
  weather detail begin collapsed under **Fine tune**.
- Staged controls update the preview immediately without changing persistence.
  **Cancel** restores persisted values; **Restore defaults** only stages
  defaults; **Save settings** commits once and shows a temporary confirmation.
- **Troubleshooting** remains a separate tab with refreshable, copyable display
  diagnostics.
- Wide layout places controls beside preview; compact layout stacks and scrolls.
  Reduced motion disables motion/detail controls without hiding information.

## Migration, invalid data, and failures

- Schema 10 is copied to its schema-labeled backup and converted stage-for-stage.
  Schemas 11, 12, and 13 migrate to schema 14 as established gardens with starter
  selection complete. Existing IDs, names, Growth, stories, collection,
  Fertilizer, and economy remain intact. Fertilizer gains a conservative
  activation boundary; current-schema replacement and expired repurchase keep
  bounded prior intervals for answer-time attribution. An atomic current-day
  ID-ledger seed prevents duplicate or missed out-of-order synced answers across
  restarts. Cutoff, database, backup, and state-write failures preserve the
  original data and retry without advancing review state.
- The first transition to scene geometry 6 refreshes incompatible visual
  placement only; it does not change plant progression. The migration notice
  explains any plant returned to Collection.
- Schema 14 repairs bounded numeric values, duplicate IDs/species/slots, invalid
  `active_plant_id`, and malformed story/economy records.
- Unreadable state is copied to `garden_state.invalid.json`; other unsupported
  schemas are backed up before recovery.
- Failed state or settings writes restore the prior in-memory value. Due-data
  failure grants no all-due reward. Missing artwork preserves the named plant,
  stage, and progression through fallback rendering.
