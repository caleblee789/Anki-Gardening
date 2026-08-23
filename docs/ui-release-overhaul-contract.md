# Anki Garden UI release contract

Status: implemented contract for Anki Garden 2.1.0, state schema 21, and UI
capture contract v19. Source code and persisted behavior are authoritative.

## Authority map

- `GardenStorage` owns SQLite initialization/import, verification, backup, and
  atomic replacement of the materialized `GardenState` snapshot.
- `GardenGameEngine` owns progression, purchases, Growth Charges, loadout
  mutation, reward transitions, and rollback boundaries.
- The SQLite reward ledger owns unbounded reward-event, answer-lineage,
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
| Deck Browser or Overview card | Compact, noninteractive preview with Open Garden, starter, loading, stale, partial, and retry states |
| Open Garden | Full scene-first Garden with its name, three metric buttons, Collection, Settings, and interactive landmarks |
| Plant selection | Contextual native actions for Nurture, Move, Story, Fertilizer, and Growth Charge when eligible |
| Garden Progress or a metric | Focused Plant Growth, Anki streak, Garden Coins, Achievements, or Collection page |
| Cottage or Collection action | Collection page in the existing Garden Progress window |
| Nursery landmark | Four-tab Nursery for Plants, Supplements, Garden spaces, and Weather/Scenery |
| Settings action or Anki menu | Staged settings and diagnostics with explicit save/cancel behavior |

Home and Settings previews expose no scene actions. The full Garden alone owns
plant selection, move destinations, and landmark activation.

## Growth and reward flow

One eligible normal Anki answer creates one engine-owned transaction:

1. Review ingestion normalizes the answer and stable lineage identity.
2. The nurtured unfinished plant receives the full base award plus eligible
   streak, Fertilizer, Booster, Weather, and Scenery modifiers.
3. Every other planted unfinished plant receives the exact 20% passive
   allocation, carried in fifths without loss or duplication.
4. Stage transitions, recurring rewards, achievements, Garden Finds, and
   feedback are committed with state and ledger rows or rolled back together.
5. UI surfaces render the committed result and canonical presentation models.

Growth Charges and Garden-Find Growth are direct-Growth paths and do not fan
out. Recurring daily, seventh-day, all-due, achievement, stage, and Find rewards
use stable identities and cannot be replayed into duplicate grants.

## Purchase and loadout flow

Every species, Growth Charge, Fertilizer, Weather, Scenery, and Garden-bed
purchase follows the same quote/confirm/commit boundary:

1. The engine issues a typed quote with request ID, price, balance, target,
   disposition, and consequences.
2. Confirmation renders only that quote; it performs no calculation.
3. Submission revalidates price, balance, target, availability, and ownership.
4. Debit and grant/application/unlock commit atomically with the completed
   request record.
5. Exact replay returns the recorded outcome; typed stale or terminal errors do
   not mutate state; persistence failure restores the pre-request snapshot.

Collection owns Weather/Scenery inspection, reversible preview, equipment, and
visibility drafts. `apply_garden_loadout()` is the sole atomic mutation path.
Nursery purchases never auto-equip an environment item.

## Persistence and failure behavior

- Schema 21 persists resumable `OnboardingProgress`, one
  `GardenLoadoutState`, exact passive residuals, inventory, active effects, and
  bounded purchase/Growth-Charge replay records.
- Supported JSON state is imported once with a backup; database verification,
  read, backup, and save failures fail closed.
- Capture-only hover, focus, route, scroll, filter, viewport, and local preview
  drafts never enter persisted Garden state.
- Stale Home responses are rejected by revision/request identity. Recoverable
  display failures retain the last valid content with a textual status.
- Failed starter, move, purchase, loadout, or Growth-Charge saves restore the
  last committed state and provide an explicit retry or safe exit.

## Visual, responsive, and accessibility contract

- Verdant Twilight V6, its geometry-compatible Scenery reskins, seven Weather
  overlays, six fixed planter spaces, and the current plant/item art remain the
  visual foundation.
- Dialogs have one vertical scroll owner, reachable content, stable footer
  actions, and no hidden horizontal overflow.
- Shared layout modes reflow content instead of scaling the whole UI. Minimum,
  default, large, breakpoint, 150%, and 200% geometry are automated even though
  they are not duplicate screenshot faces.
- Controls retain at least 44 px targets, visible keyboard focus, accessible
  names/descriptions, logical order, focus restoration, and non-color state
  cues.
- Reduced motion combines OS and add-on preferences. Hidden widgets stop
  animation; Reviewer feedback preserves focus and does not activate itself.
- Missing or unreadable artwork preserves the item/plant identity and renders
  the code-native graphical fallback.

## Capture and acceptance contract

Capture contract v19 contains 126 distinct functional/state faces in source
order. Each is captured exactly once under `QT_SCALE_FACTOR=1.0`; responsive
and scaling duplicates are excluded.

The canonical evidence is:

- manifest:
  `build/ui-face-captures/capture-sequence-20260823-000843/20260823-000847/manifest.json`;
- contact-sheet index:
  `build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260823-000843/contact-sheet-set.json`;
- evidence ZIP: `build/ui-face-captures/anki-garden-ui-faces-20260823-000843.zip`.

The independent validator must report contract 19, 126/126 captures, zero
failures or text-layout warnings, and 17/17 valid contact sheets. Production and
capture archives must retain exact shared-payload parity and distinct
capability identities.

Automated/macOS Qt evidence does not close final-production restart and
persistence, native Windows/Linux, true OS scale and mixed-DPI transitions,
screen-reader, contrast, keyboard-walkthrough, human/device visual, or complete
end-to-end acceptance. Those gates remain explicit and unrun until separately
performed and recorded.

## Change rule

Any behavior or UI change must update the authoritative source, the smallest
relevant contract document, and existing high-risk tests. A new release capture
is obtained only after implementation and non-GUI gates are complete. Old
capture counts, package hashes, branch plans, and intermediate reports must not
be promoted as current evidence.
