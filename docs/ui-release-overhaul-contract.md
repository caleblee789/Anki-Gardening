# Anki Garden UI release contract

Status: implemented contract for Anki Garden 2.1.0, state schema 25, and UI
capture contract v25. Source code and persisted behavior are authoritative.

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
| Sync completion | One centered, nonmodal Sync Rewards receipt over stable Anki Home, with **Close** and **Open Garden** actions |

Home previews expose no scene actions, and Settings does not duplicate that
preview. The full Garden alone owns plant selection, move destinations, and
landmark activation.

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

## Persistence and failure behavior

- Schema 25 persists resumable `OnboardingProgress`, exact hundredth-Growth
  units, Stored Growth, checkpoint and Full Bloom metadata, Today’s Cards
  projection state, independent displayed Decoration and locked/queued Garden
  Bonus/Scenery loadouts, independent environment guarantees, timed Fertilizer
  periods/queues, card-counted Booster batches,
  inventory, bounded purchase/Growth-Charge replay records, and the durable
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

- Verdant Twilight V6, its geometry-compatible Scenery reskins, seven static
  Garden Decorations with one shared pad, six fixed planter spaces, and the
  current plant/item art remain the visual foundation.
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

## Capture and acceptance contract

Capture contract v25 has two registry-derived ordered evidence tiers under
`QT_SCALE_FACTOR=1.0`. The `representative` profile is the preflight and the
`full` profile is the final release authority. The current registry derives an
18-surface/two-sheet preflight and a 34-surface/five-sheet full profile after
retiring 98 redundant or behavioral-only IDs, including every watering-can
capture. These totals
remain generated rather than fixed acceptance constants. A passing
preflight may seed overlapping full-profile states; it does not replace the
full release set.

The independent validator must report contract 25, exact agreement with the
compiled active registry, and zero rejecting acquisition or lifecycle failures.
Detailed semantic, copy, text-fit, geometry, layout, scroll, and duplicate-view
findings remain visible review advisories rather than being silently normalized.
Production and capture archives must retain exact shared-payload parity and distinct
capability identities. Native dialogs accept only a direct widget grab; Home
and Reviewer prefer a verified app-owned Qt/WebView capture and label any
identity-verified compositor use as fallback. Per-state evidence may be reused
when its surface and dependency digests remain exact. Unknown, shared, or
unowned changes fail closed. The PNG, environment, record hash, and
recursively closed local lineage must remain valid in either case; a failed
replacement blocks older evidence until a newer passing capture clears that
invalidation.

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
