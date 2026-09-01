# UI state scenarios

## Fresh garden and starter

- Schema 27 begins with two unlocked direct-soil spaces, no plants, Seedling Sign
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
  action. The other unlocked space remains empty. Nursery selection, placement
  copy, and creation retain the same species identity and created `plant_id`;
  a default Bonsai is displayed as **Bonsai Plant**.
- Cards completed before starter selection still count toward study
  totals and the Anki streak, but receive no retroactive plant Growth or
  recurring rewards. Reliably reconstructable one-time achievements are handled
  separately by authoritative history reconciliation.
- If no species is release-ready, Nursery explains that it is stocking plants
  and leaves starter selection incomplete.

## Shared presentation projections

- `PlantIdentity(plant_id, display_name, species_name)` keeps the durable plant
  instance, learner-visible name, and species label separate for every renderer.
- The six visible stages are Seed, Sprout, Young, Mature, Flowering, and Full
  Bloom. Persisted `rare` remains compatible but is never visible; the compact
  HUD says `Sprout · 2 of 6 stages`.
- Collection completion reports `10 of 10 species discovered` separately from
  `30 of 39 collection entries discovered`; 30 is never labeled as plants.
- Garden appearance presents four independent rows: Scenery, Displayed
  decoration, Active garden bonus, and Visual effects.
- Standard Finds and Garden discoveries retain their internal ledger/event IDs
  but use distinct player-facing labels.

## Home preview

- Deck Browser and Overview show the Verdant Twilight scene, nurtured-plant
  Growth, and one **Open Garden** action. Today’s Cards, streak, and Garden
  Coins remain in the full Garden and Progress surfaces.
- Plants, garden spaces, and the Nursery landmark are noninteractive. No card
  collection denominator, milestone ruler, or duplicate actions appear.
- Loading, empty, disabled, success, stale, and recoverable-error states use one
  preview snapshot. Stale content retains the last valid scene and adds a text
  updating indicator. Background, Garden Decoration, scenery, plants, and foreground
  share one fade/effects layer. The nurtured plant remains identified in the
  summary; no watering can is composed into the scene.

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

- Each eligible completed card credits exact Answer Growth—10 base plus streak,
  active Fertilizer, Booster, the Anki-day-locked Garden Bonus, and locked Scenery—to the nurtured
  plant. Every other planted plant creates exact 20% Shared Growth. A growing
  source receives its share; a Full Bloom source divides its share across all
  planted plants still growing, including the nurtured plant. Instant Growth
  receives no card modifiers and is not shared. Every lane
  redirects or enters Stored Growth instead of losing value.
- Choosing **Nurture** changes only future routing. Previously earned Growth
  never moves.
- Reviewer HUD, full Garden, selected-plant card, and the persisted schema-27
  state snapshot agree after refresh.
- The expanded HUD reserves 296 px at top 44/right 16, measures its lower edge
  from Anki's answer controls with a 72 px fallback, and collapses rather than
  squeezing at narrow widths.
- Before normal sync, Garden records a clean desktop review-history boundary.
  Every newly unseen supported post-activation answer introduced beyond it is
  processed exactly once across its original Anki day, including delayed lower
  IDs and distinct answer events for the same card. Past-day answers receive
  their normal per-answer rewards; Today’s Cards completion is considered only
  for a cautiously proven current-day transition. Unsupported rows create no
  Growth and are not consumed.
- Rewards, processed identities, and one pending nonmodal Sync Rewards receipt
  commit atomically. Restart and repeated sync do not replay them. Initial setup
  and one-way collection replacement establish a non-awarding baseline.
- Sync summary milestones paint deterministically: Full Bloom, stage change,
  the highest valid checkpoint in the resulting stage, then ordinary Growth.
  Superseded checkpoints do not paint or leak into Home banners. The canonical
  receipt reconciles `420 + 80 + 20 = 520`.
- Session Summary and Sync Rewards share one coordinator for mutual exclusion,
  Escape ownership, focus restoration, and safe upper-right Sync docking.

## Today’s Cards and Garden Coins

- The learner must complete at least one eligible card before Today’s Cards can
  award Coins.
- A live collection-wide check includes scheduler-available New, Learning, and
  Review cards, including active filtered decks and active deck limits.
- New-to-Learning and relearning transitions stay outstanding until complete;
  repeated answers do not inflate progress. Suspended and buried cards are
  excluded while unavailable.
  Restoring a due card before completion makes it an obligation; later due work
  never revokes an already-earned award.
- Completion credits +10 Garden Coins once. Cloudy Drift adds +5 Coins;
  Rainbow Sunshower adds +100 Instant Growth. The locked Scenery grants its
  completion gift.
- The first eligible completed card grants +2 Garden Coins, every seventh consecutive
  eligible day grants +10, and day 7 integrates that recurring payout with its
  one-time achievement. The first valid Today’s Cards completion also grants
  the separate +5 Review Day Complete reward.
- The canonical expanded HUD reconciles `176 + 18 = 194`; Session Summary uses
  the independent daily total `126 + 19 = 145`.
- The 30-Day Anki Streak reward is **100 Garden Coins + 1 Small Growth Charge**
  in achievement cards, receipts, and summaries.
- Standard Finds use centralized protection and a three-per-day cap. The full
  Garden may explain those mechanics; the persistent HUD shows a Find only as a
  committed reward reveal and never shows the cap, guarantee, daily limit, or
  internal gap counter. Either Find pool may stack with
  predictable rewards, but stable internal card/pool identities are
  consumed exactly once and pre-activation history is never rolled.

Exact presentation states:

- In progress: `18 cards remaining` and `176 cards complete`.
- Waiting: `2 more cards will be due in 6 minutes`.
- Complete: `TODAY’S CARDS COMPLETE`, `+10 Garden Coins earned`, and
  `176 cards complete`.
- Ineligible: `NO COMPLETION REWARD TODAY` and `No cards were due today!`.
- Unavailable: `CARD STATUS UNAVAILABLE` and `Anki Garden could not verify
  today’s cards. Normal Garden Growth is unaffected.`

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
- The canonical Small Growth Charge confirmation and receipt show 450→550
  Growth, Seed→Sprout, two charges→one, and 50/2,000 toward Young.
  Separate painted cases prove no transition and no stage reward; Full Bloom
  rejection and overflow conservation retain their existing engine behavior.

## Anki streak, Fertilizer, and Booster Potions

- Startup, sync, rollover, and completed cards reconstruct the current consecutive
  Anki-day streak from review history. Growth tiers are 0%, 5%, 10%, 15%, 20%,
  and 25% at days 1, 7, 14, 30, 100, and 365.
- Fertilize opens the dedicated Fertilizer dialog. Basic, Quality, and Magical
  cards show exact Garden Coin cost and `+1 for 1 hour`, `+2 for 2 hours`, or
  `+3 for 4 hours`.
- Selection, quote, confirmation, and the active or queued period retain one
  immutable source `plant_id`. Actions use **Apply/Queue** and
  **Buy and apply/Buy and queue**. **Extend** is reserved for the same-tier
  extension disposition.
- Fertilizer uses wall-clock time, including time outside review. Purchasing the
  same tier extends its remaining time. Another tier queues without discarding
  either duration. A sixth queued/active dose is rejected without consuming
  inventory.
- A rare Booster Potion is not sold. It adds +5 Growth for 100 applicable
  cards, stacks with Fertilizer, and another Potion extends the count. Herbalist’s
  Hourglass or Full Moon changes one activation to 125 cards; together they
  provide 150 cards.
- At Full Bloom, remaining Fertilizer time and Booster cards transfer to the
  automatic next plant or wait for the next Nurture choice.
- Small and Standard Growth Charges are repeat purchases for 30 and 125 Coins;
  Grand is not currently obtainable. If already present in imported development
  state, it remains usable. They add 100, 500, or 2,000 Instant Growth, follow
  milestone rewards, and consume only if the state saves. Overflow redirects
  or becomes Stored Growth.

## Nursery landmark and catalog

- Nursery and the cottage use separate forgiving hit targets and
  silhouette-following hover/focus outlines with anchored in-scene labels.
  Click, Enter, or Space opens Nursery or Garden Progress.
- Move mode disables both landmarks. Home previews never expose them as actions,
  and Settings does not render a scene preview.
- Nursery tabs are **Plants**, **Fertilizers and boosts**, **Garden beds**,
  and **Garden Decorations and Scenery**. Plants retains computed
  ownership/availability counts with no
  hard-coded roster denominator and provides an artwork carousel for all stages.
- A configured species appears for selection or purchase only when all six
  Verdant Twilight V6 stages are local, release-preferred, geometry-valid
  `direct_soil` assets. Incomplete lines remain hidden.
- All 60 species-stage assets serialize `visual_scale_correction`, use a
  calibrated thumbnail scale, and validate against all six V6 bed positions.
- An already-owned legacy species remains visible, plantable, and progress-safe
  even when it is not currently stocked.
- Moving to Collection preserves Growth, memories, Fertilizer, and Booster
  state. The plant currently being nurtured must be changed before it can be
  moved to Collection.
- Space unlocks are contiguous and transactional. Only the next bed is priced
  and enabled; its confirmation revalidates the next index before debit. All
  six V6 spaces accept direct-soil plants.

## Garden Decorations, Scenery, and reward Collection

- Nursery offers only free/purchasable environment choices. Each one-time
  purchase is transactional and remains unequipped until the learner chooses it
  through Collection's loadout detail.
- Collection shows the decoration displayed in Garden, today’s locked Garden
  Bonus, any bonus queued for the next Anki day, today’s locked Scenery,
  queued Scenery for tomorrow, exact
  effect/cap/acquisition, and finite tier-discovery progress. It owns reversible
  previews plus atomic selection, queue, and visibility changes.
- The one Garden Bonus stacks with the Scenery passive. Turning off a visual
  layer or displaying another prop does not turn off its mechanical bonus.
- The first eligible answer locks the Garden Bonus for the Anki day. Scenery
  locks independently on the first progression action; later mechanical
  selections queue for the next Anki day.
- Scenery gifts require Today’s Cards completion and never backfill. Halloween
  chooses Small 85%, Standard 10%, or Booster 5%; Full Moon grants a Booster
  every fourth qualifying completion.
- Rare, Very Rare, and Ultra discoveries have independent 5,000, 20,000, and
  50,000 hard guarantees. An unlock resets only its tier.

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
- **Up next** describes the next checkpoint and approximate cards remaining,
  or the completion record at Full Bloom.

## Settings

- Verdant Twilight appears as a compact read-only current-style card without a
  duplicate garden preview.
- Applicable Garden display and notification choices remain. Garden Decoration/Scenery,
  art quality/detail/performance, animation, and **Fine tune** controls are
  absent; balanced art and reduced-motion behavior are automatic.
- **Show reviewer HUD** defaults on. The separate **Show reviewer rewards**
  setting controls active major dock reveals, not the core plant projection or
  committed session footer.
- **Show rewards after syncing** defaults on and controls only presentation of
  the already-committed pending Sync Rewards receipt.
- Staged controls update unsaved-state feedback immediately without changing
  persistence. **Cancel** restores persisted values; **Restore defaults** only stages
  defaults; **Save settings** commits once and shows a temporary confirmation.
- **Diagnostics** remains a separate tab with refreshable, copyable display
  diagnostics. The production package has no state-mutation controls; temporary
  confirm/back up/populate/restore tools appear only in an explicitly built,
  disposable capture package.
- Wide layout places controls beside the structured appearance summary; compact
  layout stacks and scrolls without restoring the removed live scene preview.
  Reduced motion is honored without hiding information.

## Migration, invalid data, and failures

- Schema 15 development state gains the schema-16 neutral environment
  entitlements, visibility, zero Charges, daily claims, Ultra pity, and separate
  Growth-source defaults. Schema 16 then upgrades to schema 17 with resumable
  onboarding: empty gardens start at introduction, planted incomplete starters
  resume at nurture, and established Gardens migrate to done. Older supported
  schemas continue through the established stage/ledger migration boundary.
  Schema 17 then upgrades through the purchase, loadout, and exact-Growth
  boundaries in schemas 18-20. Schema 21 imports the state into SQLite. Schema
  22 backs up either schema-21 JSON or authoritative SQLite before adding Stored
  Growth, milestone/completion state, timed Fertilizer queues, Booster card
  effects, loadout schedules, and
  finite discovery counters. Schemas 23–25 replace Weather identities with
  Garden Decorations, split displayed artwork from the active Garden Bonus,
  add independent Anki-day Bonus locking, and add the durable pending sync
  receipt. All supported schema-10–26 paths converge on schema 27; the
  schema-26 migration preserves plants, wallet balance, Stored Growth, and
  prior claims while adding the current cumulative economy authorities without
  retroactive rewards.
  Cutoff, database, backup, and state-write failures preserve the original data
  and retry without advancing review state.
- The first transition to scene geometry 6 refreshes incompatible visual
  placement only; it does not change plant progression. The migration notice
  explains any plant returned to Collection.
- Schema 27 repairs bounded numeric values, duplicate IDs/species/slots, invalid
  `active_plant_id`, and malformed story/economy/reward records.
- Unreadable state is copied to `garden_state.invalid.json`; other unsupported
  schemas are backed up before recovery.
- Failed state or settings writes restore the prior in-memory value. Due-data
  failure grants no completion reward. Missing artwork preserves the named plant,
  stage, and progression through fallback rendering.

## v26 scenario evidence

Capture contract v26 uses contract schema 2 and scenario schema 3. It registers
18 representative and 34 full surfaces and produces two and five sheets.
`scenario_id`, `fixture_id`, and one-based `scenario_step` are mandatory in
specs, dependency digests, runtime records, manifests, validators, PNG metadata,
and sheet indexes. Shared fixture IDs establish sequential lineage for
`first_run`, `fertilizer_queue`, and `growth_charge_transition`; v25 evidence is
never reused. Surfaces 27–30 use the named one-step scenarios
`reviewer_hud_base`, `session_summary`, `sync_rewards`, and
`reviewer_hud_full_bloom`.

Hard gates cover deprecated visible copy, root/DOM overflow, progress
fractions, asset mappings, Reviewer exclusion rectangles, four-state scrolling,
and lineage. Current run paths, archive and capture hashes, artifact sizes, and
validation totals are recorded only in the
[final 2.2.0 UI audit](final-ui-audit-2.2.0.md) and the
[five-page contact-sheet index](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json).
`quality_status: review-required` and `release_ready: false` remain unchanged;
manual macOS interaction, Windows/Linux, mixed-DPI, forced-colors,
screen-reader, broader-keyboard, and human release approval remain open.
