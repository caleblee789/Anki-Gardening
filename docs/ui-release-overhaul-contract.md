# Anki Garden UI release contract

Status: implemented working-tree contract for Anki Garden 2.2.0, state schema 26, and UI
capture contract v26, contract schema 2 and scenario schema 3. Source code and
persisted behavior are authoritative.

## Authority map

- `GardenStorage` owns SQLite initialization/import, verification, backup, and
  atomic replacement of the materialized `GardenState` snapshot.
- `GardenGameEngine` owns progression, purchases, Growth Charges, loadout
  mutation, Landmark, Mastery, reward transitions, and rollback boundaries.
- `ankigarden.balance_catalog` is the immutable numeric and catalog authority
  consumed by runtime, presentation, capture, tests, and simulation.
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
  remains stable while rendering **Full Bloom**; default identities such as
  **Bonsai Plant** propagate across first-run selection, placement, and the
  created plant.
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
  UI renders `Sprout · 2 of 6 stages`.
- `PlantIdentity(plant_id, display_name, species_name)` is renderer-neutral and
  preserves defaults such as **Bonsai Plant** across onboarding, placement,
  Garden, Progress, and transaction surfaces.
- Collection counts are deliberately orthogonal. The canonical fixture renders
  `10 of 10 species discovered` and separately
  `30 of 93 collection entries discovered`; 30 is never labeled as plants.
- Appearance projects Displayed decoration, Active garden bonus, Displayed
  scenery, and Active scenery effect independently. Appearance remains
  cosmetic and independent of the snapshotted or queued mechanics.
- Standard Finds and Garden discoveries use distinct player-facing labels while
  the engine and ledger retain their stable internal event IDs.

## Growth and reward flow

One eligible completed card creates one engine-owned transaction:

1. Review ingestion normalizes the card event and stable lineage identity.
2. The nurtured unfinished plant receives full Answer Growth: 10 base plus
   snapshotted Garden Rhythm, card-counted Fertilizer and Booster, Garden Bonus,
   and Scenery Effect.
3. Every other planted plant creates one exact 10% Shared Growth lane. A plant
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
   emphasizes the global number of cards left; completion becomes **Today’s
   Cards Complete**, the exact Coin reward, and the committed cards-complete
   total. Internal scheduler and obligation
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

Every species, Growth Charge, Fertilizer, Garden Bonus, Scenery, and cosmetic
purchase follows the same quote/confirm/commit boundary:

1. The engine issues a typed quote with request ID, price, balance, target,
   disposition, and consequences.
2. Confirmation renders only that quote; it performs no calculation.
3. Submission revalidates price, balance, target, availability, and ownership.
4. Debit and grant/application commit atomically with the completed
   request record.
5. Exact replay returns the recorded outcome; typed stale or terminal errors do
   not mutate state; persistence failure restores the pre-request snapshot.

Collection owns Decoration/Scenery inspection, reversible preview, effect and
appearance drafts. The first eligible answer immutably snapshots Garden Rhythm,
the active Garden Bonus, and active Scenery Effect. Later mechanical selections
queue for the next Anki day; both appearance choices may change immediately.
`apply_garden_appearance()` is the sole atomic combined mutation path. Nursery
purchases never auto-equip or auto-display, and visibility never changes
mechanics.

Fertilizer binds one immutable source `plant_id` through selection, quote,
confirmation, application, and a queued card batch. Owned actions are **Apply** or
**Queue**; purchases are **Buy and apply** or **Buy and queue**. **Extend** is
reserved for the existing same-tier extension disposition. A different tier
queues FIFO without changing the source plant or discarding remaining cards.

## Persistence and failure behavior

- Schema 26 persists resumable `OnboardingProgress`, exact hundredth-Growth
  units, Stored Growth, checkpoint and Full Bloom metadata, Today’s Cards
  projection state, immutable Rhythm/effect snapshots, independent appearance
  and effect choices, dual environment guarantees, card-counted Fertilizer and
  Booster queues, earned beds, Landmark, Mastery, lifetime aggregates,
  inventory, bounded UI receipts plus permanent economy identities, and the durable
  pending Sync Rewards receipt.
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

- Verdant Twilight V6, its geometry-compatible Scenery reskins, seven Garden
  Bonus masters with one shared pad, eight Display Decorations, six Landmark
  assets, four Mastery overlays, six fixed beds, and current plant/item art
  remain the visual foundation.
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
hashes belong in `docs/ui/final-ui-audit-2.1.0.md` after the accepted run.

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
