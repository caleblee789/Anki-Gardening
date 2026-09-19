# Anki Garden UI release contract

Historical schema-27/v26 architecture and display reference. Retired mechanics,
layout, capture counts, and pending gates below describe that period. Use the
[current documentation index](README.md) for product contracts and release status.
The engine/storage ownership principles remain useful; the historical examples
are not current UI acceptance expectations.

## Authority map

- `GardenStorage` owns SQLite initialization/import, verification, backup, and
  atomic replacement of the materialized `GardenState` snapshot.
- `GardenGameEngine` owns progression, purchases, Growth Charges, loadout
  mutation, reward transitions, and rollback boundaries.
- The SQLite reward ledger owns unbounded reward-event, completed-card-lineage,
  Garden-Find-outcome, and finalized-day idempotency.
- `achievement_presentations()`, `recent_garden_finds()`, and
  `recent_reward_summaries()` are the UI-facing reward authorities. Renderers
  must not recreate reward thresholds, amounts, odds, eligibility, or ledger
  decisions.
- `GardenUiCoordinator`, `GardenUiSnapshot`, and `GardenPreviewSnapshot` own
  shared Qt/Home projections and cache invalidation.
- Renderer-neutral stage, `PlantIdentity`, collection-count, appearance, and
  reward projections own learner-facing names and arithmetic. Internal `rare`
  remains stable while rendering **Full Bloom**; owned plant titles such as
  **Full Bloom Bonsai** derive from stage and species. Seed selection and Shop
  products retain **Bonsai Seed**.
- `SceneGeometryLayout` and the asset manifest own bed, plant, marker, move,
  landmark, occlusion, and popover geometry.
- `ConfigManager` owns add-on configuration separately from Garden state.

The detailed persistence rules are in `docs/ui/data_contracts.md`; supported
states are in `docs/ui/state_scenarios.md`.

## Product and navigation contract

| Entry point | Destination and behavior |
|---|---|
| Deck Browser or Overview card | Fixed-height, noninteractive preview with Garden name, nurtured plant, Growth, Open Garden, starter, loading, stale, partial, and retry states; Today’s Cards, Anki streak, and Garden Coins are omitted |
| Reviewer | Default-on, focus-safe Today’s Cards and plant-growth HUD with a one-click collapsed edge tab |
| Open Garden | Full scene-first Garden with its name, three metric buttons, Collection, Settings, and interactive landmarks |
| Plant selection | Contextual native actions for Nurture, Move, Story, Fertilizer, and Growth Charge when eligible |
| Garden Progress or a metric | Focused Plant Growth, Anki streak, Garden Coins, Achievements, or Collection page |
| Cottage or Collection action | Collection page in the existing Garden Progress window |
| Nursery landmark | Four-tab Nursery for Plants, Fertilizers and boosts, Garden beds, and Garden Decorations and Scenery |
| Settings action or Anki menu | Staged settings plus read-only Diagnostics with explicit save/discard behavior |
| Sync completion | One safely upper-right-docked, nonmodal Sync Rewards receipt over stable Anki Home, with **Close** and **Open Garden** actions |

Home previews expose no scene actions, and Settings does not duplicate that
preview. The full Garden alone owns plant selection, move destinations, and
landmark activation.

## Presentation projection contract

- The canonical stage projection has six positions: Seed, Sprout, Young,
  Mature, Flowering, and Full Bloom. It preserves internal `rare` while compact
  UI renders a single **Bonsai Sprout** heading.
- `PlantIdentity(plant_id, display_name, species_name)` is renderer-neutral and
  preserves durable plant IDs and derives titles from stage and species across
  Garden, Progress, and transaction targets. Rewards use sentences such as
  **Bonsai reached full bloom** based on each recorded event. Renaming is disabled.
- Collection counts are deliberately orthogonal. The canonical fixture renders
  `10 of 10 species discovered` and separately
  `30 of 39 collection entries discovered`; 30 is never labeled as plants.
- Appearance projects Scenery, Displayed decoration, Active garden bonus, and
  Visual effects as four independent rows. Displayed decoration remains
  cosmetic and independent of the locked or queued Garden Bonus.
- Standard Finds and Garden discoveries use distinct player-facing labels while
  the engine and ledger retain their stable internal event IDs.

## Growth and reward flow

One eligible completed card creates one engine-owned transaction:

1. Review ingestion normalizes the card event and stable lineage identity.
2. The nurtured unfinished plant receives full Answer Growth: the base award plus eligible
   streak, Fertilizer, Booster, Garden Bonus, and Scenery modifiers.
3. Every other planted plant creates one exact 20% Shared Growth share. A plant
   still growing receives its own share; a Full Bloom plant’s share is divided
   among all planted plants still growing, including the nurtured plant.
4. Overflow continues through planted unfinished plants in stable slot order;
   any remainder becomes Stored Growth.
5. Checkpoints, stage transitions, recurring rewards, achievements, Garden Finds, and
   feedback are committed with state and ledger rows or rolled back together.
6. UI surfaces render the committed result and canonical presentation models.

Growth Charges and Garden Find awards are Instant Growth paths and do not fan
out. First-card, seventh-day, Today’s Cards, achievement, checkpoint, stage,
and Find rewards use stable identities and cannot be replayed into duplicate
grants.

The reviewer HUD is persistent, content-driven, and enabled by default through
`show_reviewer_hud`. Its shell remains mounted between cards. The existing
reviewer-reward setting controls active major reward-dock reveals, while core
plant progress and the committed session footer remain available.

Before a normal sync, Garden establishes a clean desktop review-history
boundary. After sync it processes every newly unseen supported post-activation
answer across its original Anki days, including delayed lower-ID rows. Past-day
answers receive normal per-answer rewards; Today’s Cards completion is evaluated
only for the current Anki day when the live transition can be proven. Rewards
and one durable pending Sync Rewards receipt commit atomically. Initial setup
and one-way collection replacement establish non-awarding baselines. The
default-on `show_rewards_after_syncing` setting suppresses only presentation.

The HUD shows global Today’s Cards progress, prominent current-stage art,
checkpoint progress, next-answer Growth, and at most two compact active-effect
chips. It hides Find caps and protection state, raw shares and Shared Growth,
environment names, and irrelevant Stored Growth. In progress, Today’s Cards
emphasizes the global number left; completion becomes `All cards complete`, the
exact Coin reward, and `176 reviewed today`. Internal scheduler and obligation
identifiers never become player copy.

The canonical HUD fixture reconciles `176 + 18 = 194` cards due at the start
and identifies the plant as `Sprout · 2 of 6 stages`. Session Summary keeps its
local scope explicit with `126 + 19 = 145`; Sync Rewards keeps imported reward
arithmetic explicit with `420 + 80 + 20 = 520`. Session and Sync summaries are
nonmodal. One shared coordinator provides mutual exclusion, focus restoration,
single-owner Escape handling, and safe Sync docking, so summary surfaces never
compete or leak into normal Home banners.

Sync milestone presentation is deterministic: Full Bloom, stage change, the
highest valid checkpoint in the resulting stage, then ordinary Growth.
Superseded checkpoints are omitted.

Meaningful committed results appear in one integrated reward dock with a live,
zero-free `This session` footer. One answer produces one stable-ID bundle with
one event-specific hero, at most two categorized summaries, and an
event-ID-backed remainder action. Routine Growth folds into the plant and
session total without opening a full reveal. Detached toast stacks and
per-event X buttons do not exist.

## Purchase and loadout flow

Every species, Growth Charge, Fertilizer, Garden Decoration, Scenery, and Garden-bed
purchase follows the same quote/confirm/commit boundary:

1. The engine issues a typed quote with request ID, price, balance, target,
   disposition, and consequences.
2. Confirmation renders only that quote; it performs no calculation.
3. Submission revalidates price, balance, target, availability, and ownership.
4. Debit and grant/application/unlock commit atomically with the completed
   request record.
5. Exact replay returns the recorded outcome; typed stale or terminal errors do
   not mutate state; persistence failure restores the pre-request snapshot.

Collection owns Garden Decoration/Scenery inspection, reversible preview,
equipment, and visibility drafts. The displayed Decoration is an independent
cosmetic choice and may change or hide at any time. The first eligible answer
locks the active Garden Bonus for that Anki day; the first progression action
locks Scenery. Later mechanical selections queue for the next Anki day.
`apply_garden_loadout()` is the sole atomic mutation path. Nursery purchases
never auto-equip an environment item, and visibility never changes mechanics.

Fertilizer binds one immutable source `plant_id` through selection, quote,
confirmation, application, and a queued period. Owned actions are **Apply** or
**Queue**; purchases are **Buy and apply** or **Buy and queue**. **Extend** is
reserved for the existing same-tier extension disposition. A different tier
queues without changing the source plant or discarding remaining time.

## Persistence and failure behavior

- Schema 27 persists resumable `OnboardingProgress`, exact hundredth-Growth
  units, Stored Growth, checkpoint and Full Bloom metadata, Today’s Cards
  projection state, independent displayed Decoration and locked/queued Garden
  Bonus/Scenery loadouts, independent environment guarantees, card-counted
  Fertilizer and Booster queues, Garden Rhythm and daily economy snapshots,
  earned beds, Garden Cycle, active Growth targets, cumulative Landmark and
  Mastery funding and claims, Garden Legacy, inventory, bounded
  purchase/Growth-Charge replay records, and the durable pending Sync Rewards
  receipt.
- Schema-21 JSON and authoritative SQLite profiles are backed up before the
  migration; established reward authorities and historical identities remain
  intact.
- Supported JSON state is imported once with a backup; database verification,
  read, backup, and save failures fail closed.
- Capture-only hover, focus, route, scroll, filter, viewport, and local preview
  drafts never enter persisted Garden state.
- Stale Home responses are rejected by revision/request identity. Recoverable
  display failures retain the last valid content with a textual status.
- Failed starter, move, purchase, loadout, or Growth-Charge saves restore the
  last committed state and provide an explicit retry or safe exit.

## Visual, responsive, and accessibility contract

- Verdant Twilight V6, its geometry-compatible Scenery reskins, seven static
  Garden Decorations with one shared pad, six fixed planter spaces, and the
  current plant/item art remain the visual foundation.
- One shared Home-card shell renders starter, empty, active, zero, partial, and
  complete states. Individual progression and the species artwork gallery use
  two distinct six-stage strips rather than overloading one component.
- Shared semantics use sentence-case tabs, tabular metrics, noninteractive
  status chips, light switch thumbs, crisp lock/completion icons, a recognizable
  Settings gear, semantic colors, and a 20 px spacing rhythm.
- Dialogs schedule content fitting after layout, visibility, font, style,
  artwork, and state changes. They have one vertical overflow owner, reachable
  content, normal-flow feedback/footer actions, terminal-state shrinking, and
  no hidden horizontal overflow.
- Shared layout modes reflow content instead of scaling the whole UI. Minimum,
  default, large, breakpoint, 150%, and 200% geometry are automated even though
  they are not duplicate screenshot faces.
- Text-fit buttons use the shared 30 px compact-row, 34 px secondary, 36 px
  primary, 38 px onboarding, and 30 px icon variants. Controls retain visible
  keyboard focus, accessible names/descriptions and tooltips, logical order,
  focus restoration, and non-color state cues.
- Reduced motion combines OS and add-on preferences. Hidden widgets stop
  animation; Reviewer feedback preserves focus and does not activate itself.
- Missing or unreadable artwork preserves the item/plant identity and renders
  the code-native graphical fallback.
- Serialized placement metadata includes `visual_scale_correction` and
  calibrated thumbnail scaling. The release asset gate validates all 60
  species-stage assets and all six bed positions.
- The Reviewer safe area is 296 px wide, 44 px from the top, and 16 px from the
  right. It uses measured answer-control clearance with a 72 px fallback and
  collapses in narrow layouts before entering the answer controls.

## Capture and acceptance contract

Capture contract v26, contract schema 2 and scenario schema 3, has two
registry-derived ordered evidence tiers under `QT_SCALE_FACTOR=1.0`. The
`representative` profile is the preflight and the `full` profile is the final
release authority. The current registry derives an 18-surface/two-sheet
preflight and a 34-surface/five-sheet full profile after retiring redundant or
behavioral-only IDs, including every watering-can capture and
`nursery-weather-scenery`. Its ordinal-24 replacement is
`nursery-garden-decorations-scenery`. These totals remain generated rather than
fixed acceptance constants. A passing preflight does not replace the full
release set.

Every surface spec, dependency digest, runtime record, manifest row, validator
result, contact-sheet index entry, and PNG metadata record requires
`scenario_id`, `fixture_id`, and one-based `scenario_step`. Shared seeded
lineages are `first_run` 01–04, `fertilizer_queue` 09–10, and
`growth_charge_transition` 33–34. Named single-surface scenarios are
`reviewer_hud_base` (27), `session_summary` (28), `sync_rewards` (29), and
`reviewer_hud_full_bloom` (30). Other surfaces default to their stable ID,
fixture version `v1`, and step 1. A fixture identifies shared seeded lineage;
each step still has an exact state contract. V25 evidence is frozen and rejected
for all v26 reuse.

The independent validator must report contract 26, schema 2/scenario 3, exact
agreement with the compiled active registry, and zero rejecting failures.
Deprecated visible copy, DOM/root overflow, progress fractions, asset mapping,
Reviewer exclusion rectangles, four-state scrolling, acquisition/lifecycle,
and scenario/state identity are hard gates. Compatibility keys and historical
migration tests receive narrow non-visible allowlists only.

Production and capture archives must retain exact shared-payload parity and
distinct capability identities. Native dialogs accept only a direct widget
grab; Home and Reviewer prefer a verified app-owned Qt/WebView capture and
label any identity-verified compositor use as fallback. Per-state evidence may
be reused only within v26 when scenario identity, state, surface, and dependency
digests remain exact. Unknown, shared, or unowned changes fail closed. The PNG,
environment, record hash, and recursively closed local lineage must remain
valid in either case; a failed replacement blocks older evidence until a newer
passing capture clears that invalidation.

All selected surfaces run in one disposable Anki process. Checkpoint cohorts
remain logical restore and circuit-break domains inside that session; they no
longer cause relaunches. Clean shutdown is bound to the same process. A
zero-surface process is needed only when all PNGs are reusable but shutdown
evidence changed. Memory-leak stress testing is outside the capture workflow.

Raw manifest-owned PNGs are the runtime geometry authority. Contact sheets are
review aids: their screenshots are top-aligned on a visibly distinct light
frame and carry an explicit outline so unused sheet space cannot be mistaken
for an application modal or gutter. The final immutable evidence paths and
hashes are recorded in the
[final 2.2.0 UI audit](ui/final-ui-audit-2.2.0.md) and the
[five-page contact-sheet index](../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json).

Automated/macOS Qt evidence does not close native Windows/Linux, 125%/150% or
true OS scale and mixed-DPI transitions, forced colors, screen-reader,
contrast, broader keyboard walkthrough, human/device visual, or complete
end-to-end acceptance. Those gates remain explicit and unrun until separately
performed and recorded.

## Change rule

Any behavior or UI change must update the authoritative source, the smallest
relevant contract document, and existing high-risk tests. A new release capture
is obtained only after implementation and non-GUI gates are complete. Old
capture counts, package hashes, branch plans, and intermediate reports must not
be promoted as current evidence.

## Historical display matrix

This table preserves the former standalone display-validation matrix. Its source
mappings and canonical examples describe the schema-27/v26 UI; later gameplay
and presentation changes supersede the values and controls shown here.

| Surface value | Authoritative source | Presentation contract |
|---|---|---|
| Nurtured-plant Growth | `active_plant_id` plus the selected plant's Growth/stage display | Home and the compact Garden strip show the current nurtured plant's progress. If no unfinished plant is being nurtured, they explain that Growth is waiting rather than substituting a garden-wide total. |
| Plant identity and stage | Renderer-neutral `PlantIdentity(plant_id, display_name, species_name)` and the six-stage projection | Instance identity survives selection and transactions; individual titles such as **Full Bloom Bonsai** derive from stage and species; custom names are not displayed. Seed, Sprout, Young, Mature, Flowering, and Full Bloom are the only visible stages; internal `rare` remains compatible but is never painted. The compact HUD uses one **Bonsai Sprout** heading. |
| Anki streak | Retrospective Anki review history plus `streak_days`, `STREAK_BONUS_TIERS`, achievement projections, and committed recurring-reward receipts | Shows consecutive Anki days, the current Growth bonus, the next tier, the 2-Coin active-day and 10-Coin seventh-day rules, and registry-projected one-time streak achievements. It never reconstructs earned state from UI math. |
| Garden Coins | `currency_balance`, normalized reward and transaction rows, completed-request ledgers, and grouped reward summaries | Learner-facing UI consistently says Garden Coins. Purchase confirmation shows current and resulting balance; success shows the committed receipt; Progress groups reward lines by correlation identity without inventing grants. |
| Cards complete and Growth today | Schema-27 exact unit counters, per-plant applied/Shared/Instant maps, Stored Growth, and stable processed-card identities | Counts each eligible completed card once across live review, retry, duplicate events, and sync. Growth detail separates Answer Growth, Instant Growth, Shared Growth, redirection, and storage. |
| Today’s Cards | One live collection-wide scheduler projection over available New, Learning, and Review cards plus the committed completion and reward summary | The remaining count, denominator, progress fill, completion reward, and Continue Reviews route use the same scope. The canonical Reviewer case reconciles `176 + 18 = 194`; Session Summary separately reconciles `126 + 19 = 145`. It never treats answer count as obligation completion or exposes internal obligation names. |
| Achievements | `achievement_presentations(state)` joined from the canonical definition registry and persisted unlock/progress metadata | Cards show exact criteria, current/target progress, exact reward summary, unlock state/date, and whether a historical unlock was reconstructed. The 30-day reward is **100 Garden Coins + 1 Small Growth Charge** everywhere. No component owns alternate thresholds or rewards. |
| Garden Finds | `recent_garden_finds(state)`, persisted hit outcomes, Standard registry metadata, uncapped daily counts, and the unowned-environment pool | Recent Finds show committed name, tier, artwork/fallback, and reward. Instant Growth receipts show their complete routing. The full Garden shows Finds today and guarantee status; the persistent Reviewer shows a Find only when earned and never shows those counters. |
| Nursery counts | `catalog_summary()` and the user's collection | Shows dynamic text such as “2 plants collected. 1 plant available now.”; never a hard-coded roster denominator. |
| Nursery stock | Complete release-preferred Verdant Twilight V6 assets for every stage, valid geometry-v2 placement metadata, and `direct_soil` compatibility | Only complete lines appear for starter selection or purchase. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia satisfy the current bundled contract. All 60 species-stage assets serialize `visual_scale_correction`, use calibrated thumbnail scaling, and validate in all six bed positions; retired or incomplete lines remain hidden without affecting an already-owned plant. |
| Garden beds | `unlocked_slots`, planted count, growing recipients, space price tables, and the engine's next-bed quote | Two spaces begin unlocked; up to six can be used. Nursery explains that each other planted bed adds one 20% Shared Growth share, Full Bloom shares redistribute across plants still growing, and six planted beds retain 200% output while any plant remains unfinished. |
| Plant composition | `verdant_twilight_surface_v6`, six named support lines/contact planes, and depth-sorted placements | One to six plants remain grounded across supported full-Garden and home aspect ratios. Home uses the same art but exposes no scene interaction. |
| Scene landmarks | Registered Nursery/Progress actions plus manifest hit bounds, silhouette polygons, and label anchors | Full Garden provides artwork-following hover/focus outlines and in-scene labels with click/Enter/Space activation. Move mode disables them; home omits them. |
| Default, hover, and selected plant | `PlantInteractionState` plus geometry-v2 `interaction_bounds` | Default has no emphasis; hover/focus is restrained; selection is stronger and persistent. No scale or bounce is used. |
| Selected plant | Selected scene payload and committed Growth projection | Compact card shows identity, player-facing Full Bloom stage, checkpoint rewards, approximate cards remaining, Fertilizer time, Booster cards, Stored Growth state, and Nurture/Fertilize/Growth Charge/Move/Story. |
| Move state | `PlacementDraft`, valid destination slots, and the committed placement change | Scene highlights valid spaces. Selecting a space commits a move or swap immediately; Escape/Cancel exits before placement, save failure rolls back, and Undo restores the last committed arrangement. No destination dropdown or Done action is shown. |
| Nursery catalog | Release-ready plant lines, normalized artwork/fallback metadata, item specs, collection, inventory, shared effect descriptors, and the engine's purchase projections | Horizontally scrollable non-shrinking tabs separate Plants, Fertilizers and boosts, Garden beds, and Garden Decorations and Scenery. Text badges distinguish owned/locked/equipped states; all Coin actions open the shared confirmation. Booster Potions are reward-only, earned from Standard Garden Finds or eligible daily Scenery rewards. Environment purchases do not auto-equip; Small/Standard Charges are repeat purchases, while Grand is visibly not currently obtainable. |
| Fertilizer targeting | Engine quote plus immutable source `plant_id`, selected tier, active period, and queued periods | Selection, quote, confirmation, and the committed/queued period retain the same source plant. Actions use **Apply/Queue** and **Buy and apply/Buy and queue**; **Extend** appears only for the same-tier extension disposition. |
| Growth Charge | Engine-owned request, target identity, inventory, routing receipt, crossings, and stage reward | The canonical painted transition is 450→550 Growth, Seed→Sprout, two charges→one, and 50/2,000 toward Young. Independent success variants prove no transition and no stage reward; Full Bloom rejection and overflow conservation remain engine-owned. |
| Environment Collection | Schema-27 displayed Decoration, locked/queued Garden Bonus and Scenery, visibility, entitlements, shared effect descriptors, environment registry, and per-tier guarantees | Collection distinguishes displayed art from the active Garden Bonus, equipped today from queued for the next Anki day, and cosmetic visibility from mechanics. It shows exact effect/cap/acquisition and finite tier progress, and owns reversible previews plus atomic queue/visibility changes. |
| Collection counts | Shared registry projection over species and all collection entry types | Completion shows `10 of 10 species discovered` and separately `30 of 39 collection entries discovered`. Thirty is never labeled as a plant count. |
| Reviewer HUD | Engine-owned HUD projection, stable committed reward bundles, and the local-session accumulator | Persistent, content-driven presentation shows global Today’s Cards, prominent plant/stage progress, next checkpoint, next-answer Growth, compact active effects, one integrated major-reward reveal, and a live session footer. Its canonical safe area is 296 px wide, top 44 px, right 16 px, and clear of measured answer controls with a 72 px fallback; narrow layouts collapse. Raw routing, Shared Growth math, environment names, Find caps, and irrelevant Stored Growth stay out of the persistent view. |
| Sync Rewards | Review-history boundary, stable processed-answer identities, committed sync reward summary, reward ledger, and `pending_sync_reward_summary` | After normal sync, one safely upper-right-docked nonmodal receipt summarizes already-applied rewards across supported imported answers. Milestones order as Full Bloom, stage change, highest valid checkpoint in the resulting stage, then ordinary Growth; superseded checkpoints do not paint. The canonical total reconciles `420 + 80 + 20 = 520`. It omits specific device identity, survives restart until successfully mounted, never enters the local Session Summary or Home banners, and may be hidden without suppressing reward processing. |
| Transient summary coordination | Shared Session/Sync coordinator | Session Summary and Sync Rewards are mutually exclusive, share one Escape owner, restore the prior focus safely, and never leave two summaries mounted. |
| Plant Story | Stable plant ID plus semantic memories | Hero identifies the plant by stage and species, with current Growth; enlarged art and a stage-relative bar lead into oldest-to-newest memories and **Up next**. |
| Settings | Whitelisted Anki config, staged settings payload, and immutable build capabilities | **Show reviewer HUD** defaults on; the separate **Show reviewer rewards** setting controls active major dock reveals while core progress and session totals remain; default-on **Show rewards after syncing** controls only the Sync Rewards receipt. Garden Decoration/Scenery selection and visibility are absent. Art quality/detail/performance and Fine tune are absent; balanced art and OS reduced-motion behavior are automatic, while **Reduce animations** can request the same mode. Production **Diagnostics** is read-only; explicit backup/populate/restore controls appear only in an isolated capture build. |
| Responsive layout | Available dialog/webview geometry | Pages scroll vertically, Settings stacks at the compact breakpoint, cards remain onscreen, and no horizontal scrolling is required. |
