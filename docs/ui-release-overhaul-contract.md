# Anki Garden UI release-overhaul contract

Status: foundation contract for Release 2.1.0. The current source capture
contract is v10 with 149 ordered surfaces. Its after-change macOS Qt capture is
complete and validator-clean. This document records the current implementation
boundary and the rules that downstream UI work must preserve. It is not
approval to implement product-specific redesigns.

The source code and persisted-state behavior are authoritative. Existing UI
documents remain useful context, but any conflict called out in
[Documentation drift](#documentation-drift-to-reconcile) must be resolved in
favor of the traced implementation until a product decision explicitly changes
the contract.

## Authority and current baseline

The current mutable product boundary is schema 16 in
`user_files/garden_state.json`. `GardenStorage` loads, migrates, repairs, backs
up, and atomically replaces that file (`ankigarden/storage.py:362-432`). Anki
add-on configuration is a separate persistence domain managed by
`ConfigManager` (`ankigarden/config.py:11-29,133-180`).

The authoritative visual reference input is:

`build/ui-face-captures/capture-sequence-20260815-170054/20260815-170057`

Its manifest declares capture contract version 8 and 146 required surfaces,
but contains 139 screenshots, seven failures, and `complete: false`. The
missing required states in that reference run are exactly:

| Capture ID | Required state | Recorded v8 failure |
|---:|---|---|
| 019 | `active-overview-home-after-nurture` | Qt returned no pixmap after the exact Anki Home window failed to become foreground. |
| 064 | `watering-can-deck-browser-plot-1` | Same foreground-window failure. |
| 065 | `watering-can-deck-browser-plot-3` | Same foreground-window failure. |
| 066 | `watering-can-deck-browser-plot-5` | Same foreground-window failure. |
| 067 | `watering-can-overview-plot-2` | Same foreground-window failure. |
| 068 | `watering-can-overview-plot-4` | Same foreground-window failure. |
| 069 | `watering-can-overview-plot-6` | Same foreground-window failure. |

The failure originates in `_capture_home_pixmap()`, which rejects a Home image
when foreground activation fails (`ankigarden/capture_ui_faces.py:1320-1327`).
The caller then reports the less-specific pixmap error
(`ankigarden/capture_ui_faces.py:1711-1719`). The active Overview fixture is at
`ankigarden/capture_ui_faces.py:2980-3002`; watering Home fixtures are at
`ankigarden/capture_ui_faces.py:3937-3970`.

Capture contract v9 reconciled that reference in:

`build/ui-face-captures/capture-sequence-20260815-220049/20260815-220051`

The fresh run regenerated all IDs 001-146, including 019 and 064-069. Its
manifest, ordered records, and filesystem agree on 146 PNGs, with zero failures,
zero warnings, zero fixture-provenance mismatches, and `complete: true`; its
manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260815-220049`
has 19 pages. The independent repository validator reported all 146 surfaces
and all 19 pages valid. Two clean same-stamp renders produced matching SHA-256
hashes for all 19 pages and the set index. This satisfies the
manifest-completeness and deterministic-contact-sheet conditions for this
macOS Qt 1.5 run. The manifest records both primary and secondary display
provenance; it does not establish full product visual acceptance or native
Windows, standard-scale, true OS 200-percent, or deliberate mixed-DPI coverage.

That v9 run is historical pre-overhaul evidence and is stale for the current
source. The current source declares capture contract v10 with 149 ordered
surfaces. IDs 001-146 retain their established identities, and IDs 147-149 add
`resize-collection-minimum`, `resize-collection-default`, and
`resize-collection-large` for the actual Collection page in
`GardenProgressDialog`.

The current after-change capture is:

`build/ui-face-captures/capture-sequence-20260816-134539/20260816-134543`

Its manifest, ordered records, and filesystem agree on all 149 PNGs, including
019, 064-069, and 147-149. It records capture contract v10, `complete: true`,
empty `failures` and `text_layout_warnings`, complete fixture validation and
manifest writing, 60 of 60 required dialog-scroll audit records passing, and
all 13 responsive-stability pairs passing. Its 12-cycle Nursery memory probe
opened and closed every cycle and reported zero delta for every watched dialog
family; `NurseryDialog` remained at 7 instances before and after. The
manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-134539`
contains 19 pages and is marked complete. A fresh invocation of the independent
repository validator reported 149 surfaces and all 19 pages valid. The capture
report records `quality_status: clean` and package SHA-256
`feb06adc124a8fcd3e5babaddd7681ce8f5e9c36ba59b516f6d5a43bc73df771`.

This closes current manifest and contact-sheet completeness for this macOS Qt
run. It does not establish native Windows, true OS 100/150/200-percent,
deliberate mixed-DPI transition, human assistive-technology, contrast, or full
product visual acceptance.

## Approved downstream decisions

The following product decisions were approved on 2026-08-16. They define the
target contract for downstream implementation; they do not claim that schema
or product behavior has already changed in this foundation branch.

1. This cross-cutting layout/accessibility assignment keeps schema 16. Durable
   retry idempotency for repeatable Fertilizer and Growth Charge purchases is a
   separate release blocker and must be resolved in a focused state/transaction
   change before release. A UI in-flight flag is not accepted as that fix.
2. **Customize Garden** is the sole canonical owner of Weather/Scenery Equip
   and artwork-visibility changes. **Progress Collection** remains the owner of
   discovery, ownership, status, and details; it may route to Customize but may
   not commit equipment or visibility changes directly.
3. Native Windows, true OS 100/150/200-percent scaling, and high/mixed-DPI
   validation are mandatory completion gates for this assignment, as well as
   release-acceptance gates. macOS logical-viewport proxies do not satisfy
   those platform claims.

## Architecture boundary

`AnkiGardenApp` owns one `ConfigManager`, `GardenStorage`, `GardenGameEngine`,
`GardenUiCoordinator`, and reviewer handler (`ankigarden/addon.py:103-134`). The
app registers assets, menu entries, Home hooks, reviewer hooks, sync hooks,
maintenance, and the optional capture harness (`ankigarden/addon.py:135-160`).

The intended state flow is:

1. An entry point requests a route or semantic action.
2. The engine validates business capability against the current `GardenState`.
3. A mutating engine operation snapshots state, changes it, and either saves
   atomically or restores the snapshot (`ankigarden/game.py:259-273`).
4. `GardenUiCoordinator` advances its revision after a successful commit and
   invalidates dependent surfaces (`ankigarden/ui/state.py:108-117`).
5. Native Qt and Home HTML render from a shared projection of the same saved
   state, never from independently persisted view state.

No downstream implementation may introduce a second source of truth for a
business state, infer a capability from visible copy, or mutate persisted state
directly from a renderer.

## Screen-to-component map

The complete per-capture record belongs in `docs/ui-surface-inventory.md`. This
map defines the implementation boundary shared by capture states in each
surface family.

| Capture IDs | User-facing surface | Component or dialog | Entry point | Renderer and authoritative state | Primary actions and required variants |
|---|---|---|---|---|---|
| 001-002 | First-run Deck Browser and Overview | Anki Home card | Anki Deck Browser/Overview hooks | `render_home_widget()` HTML/CSS from `GardenUiSnapshot`; onboarding, garden, metrics, currency, environment, and manifest asset metadata | Open Garden, starter route, Retry; loading, starter-empty, partial, recoverable error, and stale-response rejection |
| 003 | First-run Garden | `GardenDashboard` | Open Garden before starter completion | Native Qt plus `GardenSceneWidget`; schema-16 onboarding and scene projection | Choose first plant; no-stock, save-error, planted-not-nurtured, and normal variants |
| 004-006 | Starter Nursery and confirmation | `NurseryDialog`, `StarterConfirmationDialog` | First-run route from Dashboard | Native Qt; release-ready asset catalog plus onboarding and ownership state | Choose, confirm, cancel/back; locked/no-stock, missing artwork, disabled, and action-above-footer variants |
| 007-008, 018-019, 064-069 | Normal, nurtured, and watering Home | Anki Home card | Deck Browser/Overview hooks | Home HTML/CSS from shared garden projection; active plant, slots, metrics, currency, environment, and asset placement | Open Garden, Retry; no nurtured plant, active plant, watering marker per slot, loading, partial, error, and stale states |
| 009-012, 016, 042-055, 058-063, 087-103 | Full Garden, plant interaction, Move, stress, focus, responsive, scaling | `GardenDashboard`, `GardenSceneWidget`, `PlantInfoCard` / `AnchoredPlantPopover` | Open Garden; scene selection; header and landmark actions | Native scene payload from engine state and manifest geometry | Select, Nurture, Fertilize, Move, Move to Collection, Plant, Story, Progress, Customize, Settings, Undo; hover/focus, long values, all stages/plots, full-grown, invalid destination, save error, narrow/scaling variants |
| 013-015, 056-057, 136-143 | Fertilizer and replacement confirmation | `DialogShell`, `FertilizerReplacementDialog` | Selected plant -> Fertilize | Native Qt; target plant, active interval/history, nurtured capability, balance, and transaction ledger | Purchase/Extend/Replace, cancel; unaffordable, affordable, active, expiring, history-cap, save-error, and responsive variants |
| 017, 126-130 | Plant Story | `PlantStoryDialog` | Selected plant -> Story | Native Qt; plant identity, stage, Growth, memories, discovery, and asset metadata | Rename, cancel/close; new/no-memory, one/many memories, fully grown, Rare locked, missing art, save-error, and responsive variants |
| 020-025 | Growth, streak, and Garden Coins details | Focused pages in `GardenProgressDialog` | Dashboard metric buttons | Native Qt; daily source allocation, review totals, streak, currency, and ledger | Navigate/close; zero, new, nonzero, active, history, empty, and error variants |
| 026-029, 070-076, 144-149 | Garden Progress, Achievements, Collection, species overview | `GardenProgressDialog`, species overview `GardenDialog` | Header Progress, cottage, metric routes, Collection selection | Native Qt; totals, daily stats, achievements/rewards, plants, discovery, environment ownership/status, and assets | Filter, inspect, open Customize for equipment changes, navigate; several/none/filter-empty/locked/completed/at-risk/missed/automatically-earned/next and responsive variants |
| 030-032, 116-120 | Customize Garden | `CustomizeGardenDialog` | Dashboard header Customize | Native Qt with `GardenStudioWidget`/`GardenSceneWidget` preview; one transient draft over persisted environment loadout | Select owned Weather/Scenery, toggle visuals, Save changes, cancel; on/off, locked, clean/dirty, save-success/error, and responsive variants |
| 033-036, 077-081, 121-125 | Nursery catalog and commerce | `NurseryDialog` | Nursery landmark, first-run route, related product route | Native Qt; catalog, balance, ownership, consumables, spaces, environment inventory, release-ready asset records | Choose, Purchase, Use, Plant, browse; owned, locked/disabled, success/error, empty/no-stock, missing-art fallback, final-row/footer, and responsive variants |
| 037-041, 082-086, 104-110 | Settings and Diagnostics | `GardenSettingsDialog`, `GardenStudioWidget` | Add-on settings menu or Dashboard Settings | Native Qt; staged Anki config plus separately persisted garden name; diagnostics/build capabilities are derived runtime data | Save settings, cancel, restore defaults, toggle, refresh/copy/expand diagnostics; clean/warning, dirty, invalid, save rollback/error, production-controls-absent, reduced-motion, and responsive variants |

Window opening, selection, open tabs, filters, Nursery pages, Move drafts, hover,
focus, and resize mode are transient UI state. They must not be added to
`garden_state.json`.

## Route and entry-point map

The current application uses direct app/dialog method calls and a small Home
webview bridge, not a general routing framework.

| Origin | User action | Current destination | State effect |
|---|---|---|---|
| Add-on menu | Anki Garden settings | `GardenSettingsDialog` | None until Save settings |
| Deck Browser or Overview Home card | Open Garden | Cached/constructed `GardenDashboard` | None; a fresh garden queues starter flow |
| Fresh Garden | Choose first plant | `NurseryDialog` in starter mode, then `StarterConfirmationDialog` | Confirmed starter purchase/placement saves once; Nurture remains separate |
| Dashboard header | Progress | `GardenProgressDialog` overview | None |
| Dashboard header | Customize | `CustomizeGardenDialog` | None until Save changes |
| Dashboard header | Settings | `GardenSettingsDialog` | None until Save settings |
| Nursery landmark | Activate | `NurseryDialog` | None until a product action commits |
| Cottage landmark | Activate | `GardenProgressDialog` | None |
| Metric card | Plant Growth / Anki streak / Garden Coins | Focused `GardenProgressDialog` page | None |
| Selected plant card | Nurture | Engine `set_active_plant()` | Atomically changes future Growth routing and active periods |
| Selected plant card | Fertilize | Dedicated Fertilizer dialog | None until Purchase/Extend/Replace commits |
| Selected plant card | Move | Scene placement mode | Destination commit changes slots atomically; Undo is session-local |
| Selected plant card | Story | `PlantStoryDialog` | None except a confirmed rename |
| Collection plant | Plant | Engine `plant_from_collection()` | Atomically assigns an empty unlocked slot |
| Garden plant | Move to Collection | Engine `move_to_collection()` | Atomically clears its slot; prohibited for the nurtured plant |
| Collection species | Inspect | Species overview dialog | None |
| Progress Collection | Inspect environment ownership/status | Species/effect details or route to Customize | No direct equipment or visibility mutation |
| Customize | Save changes | Engine `apply_environment_loadout()` | Atomically commits both selected effects and both visibility switches |

Unknown Home bridge messages and unknown landmark action IDs must pass through
or fail closed without mutating Garden state. Move mode disables interactive
landmarks. Home and Settings previews never expose scene landmarks as actions.

### Proposed route contract

`DialogRoute` does not exist as a central model. Before multiple agents add new
entry paths, introduce a small, UI-only `DialogTarget` enum/dataclass rather
than a router framework. Proposed fields are:

```python
@dataclass(frozen=True)
class DialogTarget:  # proposed, not implemented
    surface: Literal[
        "dashboard", "settings", "nursery", "progress", "customize",
        "plant_story", "fertilizer", "species_overview"
    ]
    page: str | None = None
    plant_id: str | None = None
    starter_mode: bool = False
```

It is transient, contains no business state, and must be validated by the
destination before use.

## Persistence map

| State domain | Authority and path | Writers | Atomicity and idempotency contract |
|---|---|---|---|
| Garden progression and economy | `GardenState`, `user_files/garden_state.json`, schema 16 | `GardenGameEngine` through `GardenStorage.save()` | Same-directory temporary file and replace; engine snapshot/restore on failure; event and revlog keys deduplicate repeatable delivery |
| Garden configuration | Anki add-on config through `ConfigManager` | Settings Save | Anki configuration write; staged UI values are not authoritative before success |
| Garden name | `GardenState.garden_name` | Engine rename from Settings | Atomic Garden state transaction; Settings performs best-effort config rollback if the separate name save fails |
| Plant identity and story | Plant records inside `GardenState` | Plant Story rename and engine-authored semantic memories | Atomic Garden state transaction; card/deck/note content is never persisted |
| Assets and placement metadata | Bundled manifest and local assets | Build/release tooling only | Read-only at runtime; exact validated files and metadata determine availability and geometry |
| Build capabilities and diagnostics | Runtime/build metadata and telemetry | Build/runtime instrumentation | Derived and non-product; never enters Garden state |
| Dialog, focus, hover, filters, selection, drafts | In-memory Qt/Home controller state | Surface controller | Never persisted unless an explicit semantic action commits |
| Move Undo snapshot | Open Dashboard session | Move controller | Temporary only; latest committed placement is persisted |
| Capture fixtures | Disposable capture profile | Capture harness and development-only helpers | Must declare whether each fixture is saved or in-memory, reset prerequisites, and verify postconditions before capture |

Settings spans two persistence domains. It currently writes add-on config first,
then the Garden name, and attempts to restore config if the name save fails
(`ankigarden/ui/dashboard.py:2583-2683`). This is recoverable but not a single
filesystem transaction. Downstream work must not describe it as cross-file
atomic.

Rewards, review ingestion, fixed purchases, equipment, placement, and uses must
remain atomic and idempotent. A disabled button or in-flight UI flag is not an
idempotency mechanism.

## Growth-event flow

The authoritative flow is:

1. Reviewer hooks read supported authoritative Anki revlog rows in the current
   scheduler-day window (`ankigarden/hooks/reviewer.py:100-219`).
2. The engine rejects already processed rows using the floor plus bounded,
   sorted revlog-ID ledger.
3. Answer-time `active_plant_periods` resolves the unfinished plant being
   nurtured when the answer occurred (`ankigarden/game.py:757-877`).
4. The engine allocates 10 base Growth, deterministic fractional streak Growth,
   Fertilizer, Booster, Weather, and Scenery contributions in that order, with
   each source retained separately (`ankigarden/game.py:920-998`).
5. Total Growth caps at Rare. Stage crossings, semantic memories, DailyStats,
   processed IDs, feedback, and any reward are part of the same saved state
   transaction.
6. After commit, the coordinator refreshes Dashboard/Home projections. A failed
   read, cutoff, or save advances no cursor and grants no partial Growth.

Current repository models already cover most of the requested interface:

- `ReviewAward` is the current per-review Growth allocation/result.
- `StageTransition` records a stage crossing.
- `DailyStats` persists per-source allocation totals.
- `FeedbackEvent` is the queued user-facing notification.

These should be extended if needed; a parallel persisted `GrowthEvent` or
`GrowthAllocation` model must not be introduced.

## Reward-event flow

1. Scheduler-day startup reconciles the current streak and uses a deterministic
   event key for a once-per-milestone Coin reward
   (`ankigarden/game.py:817-845`).
2. Each new eligible revlog ID derives reward entropy from the stable garden
   seed and authoritative ID only after duplicate rejection.
3. Ordered reward bands stop at the first hit. Environment ownership,
   consumables, Growth Charges, or Coins are granted in the same state
   transaction as the answer (`ankigarden/game.py:1000-1262`).
4. Daily scenery gifts and all-due rewards use stable per-day event keys and do
   not backfill missed days (`ankigarden/game.py:1355-1408`).
5. Currency credits/debits deduplicate `event_key`, append the reason and
   resulting balance, and save atomically (`ankigarden/game.py:1437-1475`).
6. The reviewer chooses a feedback priority, renders it, and consumes it only
   after rendering (`ankigarden/hooks/reviewer.py:234-340`).

`CurrencyTransaction`, `FeedbackEvent`, and `RewardDrop` remain the persisted
record types. User-facing reward copy must be derived from those records, not
used to reconstruct them.

## Purchase transaction flow

### Current fixed-entitlement flow

`purchase_environment()` validates the catalog entry, ownership,
purchasability, and balance; derives a deterministic product event key; debits
Coins; grants inventory; queues feedback; and saves once
(`ankigarden/game.py:1614-1655`). Purchase does not auto-equip.

Species and space purchases likewise have deterministic keys
(`ankigarden/game.py:2018-2072`). Repeating a successful ownership purchase
must be a no-op rather than a second debit.

### Current repeatable-product gap

Growth Charge and Fertilizer purchases are snapshot/restore atomic, but generate
a UUID inside the engine (`ankigarden/game.py:1736-1755,1860-1933`). UI in-flight
guards prevent a live double-click but cannot deduplicate a caller retry after
an uncertain result or process restart. This does not yet satisfy the desired
end-to-end idempotency contract.

### Proposed purchase interfaces

Use repository-style frozen dataclasses with names such as `PurchaseRequest`
and `PurchaseOutcome`; these are proposed, not implemented:

```python
@dataclass(frozen=True)
class PurchaseRequest:
    request_id: str                 # caller-stable idempotency key
    product_kind: Literal[
        "species", "garden_space", "environment", "fertilizer",
        "growth_charge"
    ]
    product_id: str
    expected_price: int
    target_plant_id: str | None = None

@dataclass(frozen=True)
class PurchaseOutcome:
    ok: bool
    request_id: str
    message: str
    transaction_event_key: str | None = None
    acquired_quantity: int = 0
    balance_after: int | None = None
    state_changed: bool = False
```

The engine, not the dialog, validates price, capability, ownership, target, and
replacement rules. The same `request_id` must produce the recorded outcome
without a second debit, grant, activation, or replacement. The persistence and
migration design belongs to the separate transaction-hardening blocker; it is
not part of this schema-16 layout/accessibility change.

## Plant asset and thumbnail pipeline

The existing repository types are the contract:

- `AssetPlacement` carries anchors, crop, layer, bounds, support geometry,
  scene geometry, layout profiles, and surface profile.
- `ResolvedAsset` carries the validated local path, asset/category IDs,
  placement, and metadata payload (`ankigarden/asset_manager.py:500-737`).
- `AssetManager` loads/indexes the manifest, resolves UI/runtime variants, and
  maps slots (`ankigarden/asset_manager.py:806-887,984-1097`).

A plant species is release-ready only if all six exact local stages exist,
validate, are release-preferred, and use compatible V6 direct-soil geometry
(`ankigarden/asset_manager.py:1102-1198`). Existing ownership remains
authoritative when a species is temporarily unavailable in the storefront.

All plant artwork consumers must resolve through these types and shared
placement helpers. Plant Story, Collection, Nursery, Home, Dashboard, Settings
preview, and fallback thumbnails may not invent per-surface crop offsets. Rare
art remains hidden until the matching species has been discovered at Rare.

The requested `PlantDisplayModel` and `PlantAssetMetadata` concepts are already
represented by `PlantUiSnapshot` / `GardenUiSnapshot` and
`AssetPlacement` / `ResolvedAsset`. Extend those projections rather than create
another persisted model. Raw untyped scene dictionaries should gradually be
adapted at the projection boundary, not treated as an alternate state source.

Missing artwork must preserve the plant name, species, stage, Growth, and
action capability through a stable painterly fallback. A fixture may not
silently substitute another species or stage.

## Scene-layer pipeline

`GardenSceneWidget` consumes the engine preview payload, sanitizes it, validates
asset paths, and paints the scene (`ankigarden/ui/scene.py:73-260,2251-2302`).
The current semantic layer order is:

1. sky or background fallback;
2. background scenery/decoration;
3. legacy or split occlusion and planter-family rear layers;
4. direct-soil support surfaces;
5. plants ordered by semantic far/middle/near and rear/front placement;
6. foreground occlusion;
7. selection, hover, and keyboard-focus contours;
8. procedural Weather motion;
9. Nursery and cottage landmarks;
10. nurtured-plant watering marker;
11. Move dimmer, valid/invalid destinations, and placeholders;
12. status/help overlays and card connector.

This order preserves the painterly Garden composition and plant grounding. No
global transform/zoom or arbitrary per-item visual correction may replace
manifest metadata or a reusable layout rule.

### Proposed scene layer identifier

There is no central `SceneLayer` model. A small `SceneLayerId` `Literal` or enum
may name the order above for manifest validation and tests. It is a render
contract only and must not be persisted in Garden state.

`_draw_weather_asset()` and `_draw_garden_overlay_asset()` currently have no
call sites (`ankigarden/ui/scene.py:2680+,2773+`); active Weather rendering is
procedural. Downstream work must either connect those bitmap payloads
deliberately with tests or document them as non-rendered. It must not assume
that resolving the payload proves a layer is visible.

## Weather and Scenery state

`CatalogItem` is the current effect/collectible descriptor. It includes kind,
rarity, acquisition, effect copy, earning guidance, price, and drop tier
(`ankigarden/environment.py:23-41`). `GrowthChargeSpec` and Fertilizer specs are
the corresponding current product descriptors.

Garden state owns:

- environment inventory/entitlements;
- exactly one selected Weather ID and one selected Scenery ID;
- a compatibility `equipped` mirror;
- independent `weather_visible` and `scenery_visible` switches.

Validation repairs selection to an owned item and mirrors compatibility state
(`ankigarden/models/state.py:465-487`). Visibility affects rendering only.
Passive effects use selected IDs even when artwork is hidden
(`ankigarden/game.py:896-918`).

`equip_environment()` is owned-only and idempotent when already selected.
`set_environment_visibility()` changes only visibility.
`apply_environment_loadout()` validates and atomically saves both selected
items and both switches (`ankigarden/game.py:1657-1734`).

Customize stages and commits the whole loadout and is the approved sole owner
of Weather/Scenery Equip and artwork-visibility changes. Progress Collection's
current direct equipment and visibility controls are legacy behavior to remove
downstream. Collection must remain read-only for environment ownership, status,
and details, with an optional route to Customize for changes.

## Collection and equipment state

Plants are stable instances. Species ownership, a plant instance, and a planted
slot are distinct states:

- Purchasing a species creates a stored zero-Growth plant instance.
- Plant assigns an owned stored instance to an empty unlocked slot.
- Move to Collection clears its slot and preserves identity, Growth,
  memories, Fertilizer, and Booster.
- The currently nurtured plant cannot be stored until another unfinished plant
  is nurtured.
- Move relocates or swaps planted instances without recreating them.
- Exactly one Weather and one Scenery are selected; there is currently no
  valid unequipped/null state.

Collection filters, selection, dialog routes, and catalog pages are transient.
Ownership, plant instances, unlocked spaces, selected equipment, visibility,
and consumable counts are persisted.

## Dialog architecture

`DialogShell` is the native ownership/lifecycle boundary. It uses a Tool window
on macOS and Dialog elsewhere, attaches to its owner, gates Space activation,
restores focus, handles Escape, and hides rather than destroying cached dialogs
(`ankigarden/ui/dashboard.py:334-667`). `GardenDialog` provides shared header,
tabs, body, and a footer that is a sibling after the body rather than an overlay
(`ankigarden/ui/dashboard.py:668-825`).

Every dialog must have:

- one intentional scroll region for the active page;
- a footer that never covers content;
- a stable minimum size and content-driven responsive mode;
- Escape/cancel semantics that do not commit drafts;
- focus returned to the originating control;
- accessible names and visible focus;
- loading, empty, error, disabled, success, and stale-state handling where the
  data or transaction can enter that condition;
- stable space for timers, balances, validation, and long translated values.

Known current exceptions are nested scrolling in Customize (outer body plus
per-option scrolls, `ankigarden/ui/dashboard.py:7015-7058`) and Settings Display
(behavior scroll plus GardenStudio controls scroll,
`ankigarden/ui/dashboard.py:2261-2273`). These are downstream layout risks, not
permission for a foundation rewrite.

## Current responsive ranges

Native surfaces use the owning content container, live minimum-size hints, and
a shared 24 logical-pixel reserve. The values below are minimum content floors;
localized or platform font metrics may raise a threshold, but a historical
two-pixel probe must retain the same semantic mode on both sides.

| Surface / region | Representative source floor; clean-v10 observed threshold | Independent behavior |
|---|---:|---|
| Dashboard top-level shell | 620 px minimum | Minimum supported window remains intentionally narrow |
| Dashboard full header | About 1,595 px; 1,568 inner px in the resize states | A 230 px title region, full-copy metrics, complete measured actions, two 12 px gaps, and the 24 px reserve fit in one row |
| Dashboard title and actions | About 639 px; 632 inner px in the resize states | Complete title and action copy fit in one row without involving metric density |
| Dashboard metric full copy | 968 px; 948 inner px observed | The source regression floor uses 944 px of content plus the 24 px reserve; the live run measured its active font/content at 924 px plus the same reserve |
| Dashboard Growth identity | Live content measurement; 187-506 px observed | Plant name, stage, and Growth value use their own semantic range instead of clipping or changing the whole header |
| Dashboard milestone | 750 px | Copy, progress, and choices become one row |
| Dashboard rearrange actions | 584 px | Full move guidance |
| Settings Display studio | 684 px | Controls and preview become two columns |
| Settings footer | 240 px; 250 px observed | Persistent actions share one row |
| Garden Progress | 768 px | Navigation rail and page become two columns |
| Customize Garden | 920 px | Library and preview become two columns |
| Nursery hero | 638 px | Context and Garden Coins share one row |
| Plant Story hero | 480 px | Artwork and identity share one row |
| Starter actions | 272 px | Actions share one row |
| Fertilizer replacement comparison | 474 px | Comparison cards share one row |

Each controller publishes its semantic region order, owning width, measured
threshold, and mode for deterministic capture audits. Layout reflow preserves
source and focus order. Home uses container-scoped 420/469 px refinements, not
viewport media queries. Scene aspect, plant fit, and minimum scene height now
blend across responsive ranges instead of switching at a single pixel. The
selected-plant card attempts content-aware in-scene placement and docks only
when no protected overlay lane is available.

Dashboard header composition and metric density are independent. The clean v10
resize/scaling fixtures observe thresholds of 1,568 inner px for the complete
header, 632 px for title plus actions, and 948 px for full metric copy. Earlier
Dashboard content states 003, 009-012, and 016 measure shorter visible actions
and record 1,502/566/948 px; the threshold is intentionally content-derived.
The final manifest also records `dashboard.growth-identity` independently: it
uses compact presentation with compact metrics through the 901 probe and wide
presentation from the 999 probe upward, while long-name and near-stage fixtures
publish their own measured requirements.
Every captured Dashboard resize state through the 1440 px large window is
top-level `compact`; only the 620 px minimum is top-level `narrow`. Metric copy
is compact through the historical 901 px probe and wide from the 999 px probe
upward. These are realized macOS values, not fixed cross-platform constants:
localized or platform font metrics may move them while preserving the same
content-first policy and stable semantic pair results.

Global CSS transforms, Qt scaling transforms, and fixed screenshot-specific
offsets are prohibited. Standard scale, 150%, 200%, and high-DPI behavior must
be accepted using real display-scale evidence on both macOS and Windows in
addition to logical resize fixtures.

## Existing accessibility mechanisms

The current stack provides:

- shared visible-focus styling in `ankigarden/ui/theme.py:126-162`;
- dialog tab/control focus styling in `ankigarden/ui/dashboard.py:776-824`;
- scene accessible names/descriptions and keyboard navigation in
  `ankigarden/ui/scene.py:121-175,1816-2249`;
- scene focus outlines independent of color
  (`ankigarden/ui/scene.py:1141-1149`);
- Home ARIA status, loading/empty/error/retry states, and `:focus-visible`
  (`ankigarden/ui/home_widget.py:309,458-526,950-1086`);
- request IDs that discard stale Home responses
  (`ankigarden/ui/home_widget.py:75-117`);
- persisted reduced-motion preference, which stops scene motion and stabilizes
  hover (`ankigarden/ui/dashboard.py:8058-8061` and
  `ankigarden/ui/scene.py:191-213`).

Every new interactive control must be keyboard reachable, expose a meaningful
accessible name, and have a non-color state cue. Status, locked, equipped,
selected, success, warning, and error states require text or icon semantics in
addition to color. Motion must have a reduced-motion equivalent without lost
information.

The current capture set covers one focused Dashboard control and one
reduced-motion Settings state. It is not evidence of complete tab order,
screen-reader behavior, Windows focus rendering, high-contrast behavior, or
motion behavior at each display scale.

## Semantic action vocabulary

Business actions must have one stable semantic ID. Visible copy, accessible
copy, confirmation text, analytics, and persistence code should refer to that
same action rather than overloading a generic verb.

| Term | Contract meaning | Persistence effect |
|---|---|---|
| Choose | Select one option and, when confirmed, commit the explicitly described free or owned choice. Starter Choose means acquire and plant the free starter; it does not Nurture it. | Only confirmation commits. A navigation-only “Choose plant” needs a different action ID. |
| Purchase | Exchange Garden Coins for an entitlement, consumable, timed effect, species, or space. | Debit and acquisition/activation are one atomic, idempotent engine transaction. Purchase never implies Equip or Use except the explicitly combined Fertilizer purchase-and-activation transaction. |
| Use | Consume an already-owned Growth Charge or Booster on the current eligible nurtured plant. | Consumption and effect are saved together; failure consumes nothing. |
| Equip | Select one owned Weather or Scenery passive. | No Coin debit. Re-equipping the current item is an idempotent no-op. |
| Unequip | No supported action in Release 2.1.0. | Exactly one Weather and one Scenery remain selected. Hiding artwork is not Unequip and does not disable its passive. |
| Plant | Assign one owned stored plant instance to an empty unlocked garden space. | Preserves all plant identity and progression. |
| Move | Relocate or swap a planted instance through direct scene placement. | Valid destination saves immediately; the open-session Undo may restore the latest placement. |
| Move to Collection | Remove a non-nurtured planted instance from its slot without deleting it. | Preserves Growth, memories, Fertilizer, Booster, and identity. This is the approved canonical learner-facing phrase; **Store** is not a competing action label. |
| Replace | Confirm discarding the remaining interval of a different active Fertilizer and activate the purchased tier. | Old interval is truncated/archived; debit and replacement save together. |
| Nurture | Route future eligible review Growth to one unfinished planted plant. | Updates active plant periods. It never moves or backfills prior Growth. |
| Fertilize | Open and complete the target-plant Fertilizer purchase flow. Same tier extends; another active tier requires Replace. | Purchase, interval history, activation/extension, balance, and ledger commit together. |

Current product buttons often use **Buy** or **Unlock** where the semantic
action is Purchase. That is acceptable only if the action ID, accessible label,
and transaction contract remain unambiguous.

### Current ambiguous `Apply` uses

All current user-facing uses must be resolved deliberately:

1. Nursery Fertilizer uses visible **Apply** and accessible “Apply [tier] for
   [price] Coins” (`ankigarden/ui/dashboard.py:4094-4115`). It actually purchases
   and activates a timed product. Its semantic action is Purchase/Fertilize.
2. The dedicated Fertilizer dialog uses **Apply** when no tier is active and
   **Replace** when another tier is active
   (`ankigarden/ui/dashboard.py:10284-10333`). Its helper independently returns
   Use/Extend/Replace (`ankigarden/ui/dashboard.py:1595-1606`), so visible and
   accessible semantics can disagree. Use one vocabulary such as
   Purchase/Extend/Replace.
3. Customize uses **Apply changes** to commit the environment draft
   (`ankigarden/ui/dashboard.py:6958-6965,7037-7041,7279-7306`). Its semantic
   action is Save changes, not product Use or Purchase.
4. Progress copy says “Apply timed Growth bonuses”
   (`ankigarden/ui/dashboard.py:6724`). This is explanatory prose, but “Use” is
   clearer and consistent with consumables.

### Current ambiguous `Shelve` uses

The current UI/state copy uses Shelve/Shelved at
`ankigarden/ui/dashboard.py:3838,3850-3868,9307,9854-9857`. The engine operation
is `move_to_collection()` (`ankigarden/game.py:2103-2115`). **Move to
Collection** is the approved canonical learner-facing action and must replace
**Shelve** in downstream UI work; use a corresponding Collection-based state
phrase rather than **Shelved**. No current visible **Remove**, **Store**, or
**Unequip** action exists.

### Proposed shared action descriptor

`UserFacingAction` does not exist. Introduce a UI-only `UiActionSpec` if shared
copy and accessibility work needs centralization:

```python
@dataclass(frozen=True)
class UiActionSpec:  # proposed, not implemented
    action_id: str
    label: str
    accessible_label: str
    target_kind: str | None = None
    requires_confirmation: bool = False
    mutation_kind: Literal["none", "draft", "atomic_state", "config"] = "none"
```

This descriptor does not decide capability or execute mutations. The engine
remains the authority for both.

## Shared interface decisions

Use the existing repository names where they already express the required
concept. Proposed types below are explicitly non-persisted unless stated.

| Requested concept | Repository contract | Decision |
|---|---|---|
| Plant display model | `PlantUiSnapshot`, `GardenUiSnapshot` | Extend the shared projection; do not create a second saved plant model. |
| Plant asset metadata | `AssetPlacement`, `ResolvedAsset` | Extend manifest/asset validation only through these types. |
| Effect descriptor | `CatalogItem`, `GrowthChargeSpec`, Fertilizer spec | Reuse; a display Protocol may expose shared card fields without flattening business differences. |
| Collectible descriptor | `CatalogItem` plus ownership projection | Reuse catalog plus state-derived ownership; do not persist UI cards. |
| Purchase intent/result | Proposed `PurchaseRequest`, `PurchaseOutcome` | Resolve in the separate transaction-hardening blocker before release; this assignment does not select or ship a migration. |
| Growth event | `ReviewAward`, `StageTransition`, `FeedbackEvent` | Extend current types; no parallel event log. |
| Growth allocation | `ReviewAward` source fields and persisted `DailyStats` | Preserve separate source accounting. |
| Dialog route | Proposed `DialogTarget` | Transient enum/dataclass; no routing framework. |
| Scene layer | Proposed `SceneLayerId` | Render-only enum/Literal matching the preserved painter order. |
| User-facing action | Proposed `UiActionSpec` | Centralizes language/a11y/confirmation metadata only. |

## File ownership for downstream agents

| Owner | Primary files or contiguous regions | Must coordinate with |
|---|---|---|
| Foundation and capture | `ankigarden/capture_ui_faces.py`, repo capture validator/tests, capture/inventory/contract docs | Every agent that changes a captured state |
| Shared state and transactions | `ankigarden/models/state.py`, `ankigarden/storage.py`, `ankigarden/game.py`, `ankigarden/ui/state.py`, any new small shared-contract module | Economy, Progress, Home, migrations |
| Home | Home hook/bridge ranges in `ankigarden/addon.py`, `ankigarden/ui/home_widget.py` | Shared state, assets, capture |
| Garden and scene | `GardenDashboard`/`PlantInfoCard` ranges in `ankigarden/ui/dashboard.py`, `ankigarden/ui/scene.py`, `ankigarden/ui/plant_display.py` | Progress, accessibility, assets |
| Progress and Collection | `GardenProgressDialog` and Collection builders in `ankigarden/ui/dashboard.py`; environment ownership/status/details are read-only here | Customize routing, shared state |
| Nursery and economy | `NurseryDialog`/Fertilizer ranges in `ankigarden/ui/dashboard.py`, purchase methods in `ankigarden/game.py`, `ankigarden/environment.py` | Transactions, assets, Customize |
| Customize and environment | `CustomizeGardenDialog` ranges and environment preview/loadout; sole owner of Equip and visibility mutations | Progress Collection routing, scene, Settings preview |
| Settings and Diagnostics | `GardenSettingsDialog` ranges, `ankigarden/ui/garden_studio.py`, `ankigarden/config.py` | Shared dialog/accessibility code |
| Asset pipeline | `ankigarden/asset_manager.py`, asset manifest, asset validation tests | Home, Scene, Nursery, Story |
| Accessibility and responsive | `ankigarden/ui/theme.py`, shared dialog helpers, cross-surface tests | All surface owners; coordinate rather than edit every surface concurrently |

## Known merge-conflict areas

The highest-risk file is `ankigarden/ui/dashboard.py`, which contains most
dialogs and Dashboard behavior in one large module. Other shared hotspots are:

- `ankigarden/game.py`;
- `ankigarden/models/state.py`;
- `ankigarden/capture_ui_faces.py`;
- Home-facing ranges of `ankigarden/addon.py`;
- the bundled asset manifest;
- broad contract tests such as `tests/test_ui_overhaul_contract.py`.

Before parallel product work, land and freeze shared DTO/action vocabulary and
capture validation. Allocate `dashboard.py` by contiguous class ranges. Do not
allow multiple agents to edit `DialogShell`, shared style helpers, or the same
engine transaction functions independently. Every agent must rebase on the
foundation commit before generating its deterministic captures.

## Migration requirements

Schema 16 remains the current state boundary. Supported prior-schema migration
is backup-first and fail-closed (`ankigarden/storage.py:377-415` and
`docs/ui/data_contracts.md`). `scene_geometry_version` is independently
persisted and migrated (`ankigarden/models/state.py:278` and
`ankigarden/game.py:235-257`).

- Display snapshots, action descriptors, dialog targets, and scene-layer IDs
  are projections only and require no persistence migration.
- Renaming Apply or Shelve requires no data migration.
- Implement schema 17 with a bounded completed-purchase-request history keyed
  by `PurchaseRequest.request_id`, separate from
  `currency_transactions.event_key`. Store enough of `PurchaseOutcome` to
  replay an identical request without repeating any debit, grant, activation,
  or replacement. Reject conflicting reuse of an existing request ID.
- Do not silently backfill purchase-request records. Schema-16 states begin
  with an empty request history while retaining their existing currency ledger.
- Do not silently backfill purchase intents, Growth, rewards, active periods,
  ownership, or collection placement.
- Preserve the selected/equipped compatibility mirror until an explicit
  migration removes it.
- Any schema migration must make an exact backup before conversion, be
  retryable, preserve the source on failure, and never return fresh state as if
  migration succeeded.

## Product invariants

Downstream implementation must preserve all of the following unless the user
explicitly approves a contract change:

1. Schema-16 `GardenState` is the one mutable product source; Anki config is a
   separate domain.
2. A confirmed starter is planted but not nurtured. Answers before Nurture
   still count toward study totals but grant no plant Growth and never backfill.
3. Nurture routes future Growth by answer-time active periods. Existing Growth
   never moves when the nurtured plant changes.
4. Review, reward, and currency events apply exactly once. Save failure restores
   pre-event state and advances no authoritative cursor.
5. Growth sources remain separately accounted and total Growth caps at Rare.
   A fully grown plant no longer receives active routing.
6. Purchase does not auto-equip. Exactly one Weather and one Scenery are
   selected; visual visibility is independent from passive behavior.
7. Purchase, Use, equipment, placement, reward, and Growth changes are atomic.
   Repeatable user intents must be idempotent across retry, not only guarded
   against double-click.
8. Plant, Move to Collection, and Move preserve the stable plant instance, Growth, memories,
   Fertilizer, Booster, and identity.
9. Six V6 direct-soil slots, manifest support geometry, crop, and painterly
   layering are visual contracts. Runtime fitting may scale but may not move a
   semantic plant base away from its support center.
10. Home, Dashboard, dialogs, and previews derive from the same Garden state and
    asset metadata. Coordinator revision invalidates Home after commits.
11. A release-ready species requires all six validated local stages. Missing
    art uses a named, stable graphical fallback and never substitutes another
    fixture. Rare previews remain locked until discovered.
12. The dark evergreen identity remains shared. Nursery may retain its warmer
    contextual palette while using common controls, focus, spacing, and
    interaction conventions.
13. Dialogs preserve owner, keyboard, focus return, Escape/cancel, one-scroll,
    and non-overlaying-footer behavior.
14. Color is never the sole state signal. Reduced motion never removes
    information.
15. Dynamic balances, timers, names, translated labels, and validation messages
    reserve layout space and do not shift or clip adjacent controls.
16. The implementation remains native Qt plus the existing Home HTML renderer.
    No framework rewrite or heavy dependency is allowed without demonstrated
    necessity and approval.
17. Capture fixtures are deterministic, explicit, isolated where state could
    leak, and verified against postconditions before saving a frame.

## Capture quality and known coverage limits

The capture harness defines its ordered groups, viewport fixtures, and final
manifest contract in `ankigarden/capture_ui_faces.py`. The following were
verified defects in the reference v8 harness, not acceptable release behavior:

- `_next_step()` catches arbitrary exceptions and advances without necessarily
  adding a failure (`ankigarden/capture_ui_faces.py:722-738`).
- Dashboard and Collection waits may call their ready callback after retry
  exhaustion (`ankigarden/capture_ui_faces.py:743-767`).
- Starter seeding can exhaust retries without an explicit seed failure
  (`ankigarden/capture_ui_faces.py:670-687`).
- Generic waits can invoke `on_ready()` after timeout if no failure label was
  supplied (`ankigarden/capture_ui_faces.py:769-803`).
- Capture and next-step scheduling are independent
  (`ankigarden/capture_ui_faces.py:2147-2170`).

The foundation implementation adds repository-owned manifest and contact-sheet
validation in `scripts/validate_ui_capture.py`, with automated tests for the
source-owned ordered contract, fixture identity, image evidence, failures,
warnings, and deterministic sheet topology. The repaired v9 harness completed a
fresh 146-of-146 run at
`build/ui-face-captures/capture-sequence-20260815-220049/20260815-220051`.
All 146 ordered fixtures regenerated, 019 and 064-069 were recovered, and the
manifest reports `complete: true` with zero failures, zero warnings, and zero
fixture-provenance mismatches. The 19 contact pages and exact manifest passed
the strict independent repository validator for all 146 surfaces and 19 pages.
Two clean same-stamp renders matched on all 20 page/index artifact hashes. The
live postconditions also pin the development-population stress state to the
canonical catalog order: `bonsai`, `rose`, `sunflower`, `lavender`,
`hydrangea`, `peony`, `foxglove`, `japanese_maple`, `wisteria`, `dahlia`.

Those results validate the historical v9 source only. The current v10/149
contract adds the three Collection resize fixtures and follows source changes
across the responsive, dialog, control, and accessibility foundations. The v9
run cannot serve as current after-change evidence.

The current after-change run at
`build/ui-face-captures/capture-sequence-20260816-134539/20260816-134543`
regenerated all 149 fixtures. Its exact manifest and the 19-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`: status `valid`,
capture count 149, surface count 149, and page count 19. The manifest also
records all 60 required dialog-scroll audits and all 13 responsive-stability
pairs as passing. This is complete current capture evidence, subject to the
visual, accessibility, and platform boundaries below.

`text_layout_warnings: 0` means only that automated Qt label/button glyph and
ancestor-clip heuristics passed for captured widgets. The Home semantic pixel
gate checks broad image properties. Neither establishes correct copy, correct
fixture data, nonblank WebEngine content, contrast, hierarchy, discoverability,
or human visual quality.

The v9 manifest records `capture_display: mixed`: six first-run files came from
the secondary macOS display at DPR 1.5 and 140 files came from the primary
display at DPR 3.0, under requested Qt scale 1.5. In the current v10 run, six
files came from the secondary display at DPR 1.5 and 143 came from the primary
display at DPR 3.0, again under requested Qt scale 1.5. Capture 090 is a logical
620 x 520 proxy and explicitly does not change OS display scaling. Neither run
provides native standard-scale, true OS 200%, Windows, Windows-high-DPI, or
deliberate mixed-DPI transition acceptance. In historical v9, 100 was 1383x699
compact, 101 was 1385x699 wide, and 103 reached 1440x699 wide. Current v10 keeps
100, 101, and 103 top-level compact; the available screen still caps several
requested resize heights.

The complete count must not be confused with unrestricted product visual
acceptance. Targeted inspection of the final raw PNGs confirms that 039 is the
intentional Advanced-scroll context fixture, not a clipping defect; 066 shows
the full Home identity and Growth value; 090 and 091 keep the compact Dashboard
identity readable; 111 wraps the Progress navigation without clipping; 57 and
143 fit their wide replacement content at the realized 820x360 client size
with `scroll_maximum: 0`; 146 fits at 900x400; and the minimum Collection state
147 remains readable and operable. This
closes the previously reported 066/111 defects and the targeted 090/091/143/146/
147 checks. The zero text-layout-warning value still records automated
thresholds, not human assistive-technology acceptance. The capture log contains
expected Home-candidate and intentional warning-fixture messages; report
`quality_status: clean` is not a claim that the process log contains no warning
lines.

The v8 stress fixtures mutated shared in-memory state in sequence, and later
resize captures inherited that state. Deterministic order is not sufficient to
prove fixture isolation. Each v9 record now identifies its immutable scheduled
fixture source, declares and verifies source-backed postconditions, and rejects
an adjacent same-renderer state. Accessibility setup is explicitly unwound:
the reduced-motion fixture restores its baseline before the focus fixture, and
the focus fixture is cleared before narrow, display-scaling, and resize states.
Downstream fixture changes must preserve that provenance and cleanup evidence
and restore every temporary mutation.

## Documentation drift to reconcile

The following existing statements do not match current source behavior:

- `docs/ui/state_scenarios.md` says starter selection immediately makes the
  starter nurtured. `choose_starter()` leaves `active_plant_id` unset, and the
  current capture suite explicitly tests planted-before-Nurture
  (`ankigarden/game.py:1804-1858`).
- `docs/ui/state_scenarios.md` and `docs/ui/entrypoint_matrix.md` say Fertilize
  opens a Nursery supplements tab. The current selected-plant action opens a
  dedicated Fertilizer dialog (`ankigarden/ui/dashboard.py:10093-10350`).
- `docs/ui/entrypoint_matrix.md` assigns environment loadout and visibility to
  Progress/Collection alone. Current source exposes both the Dashboard
  Customize route and direct Progress Collection controls
  (`ankigarden/ui/dashboard.py:7635-7648,7884-7894,9900-10079`). The approved
  target makes Customize canonical and removes the direct Progress mutations.
- Existing docs call Nursery tabs **Supplements & Boosters** and **Permanent
  Upgrades**. Current source labels them **Fertilizer and Boosters** and
  **Garden Spaces** (`ankigarden/ui/dashboard.py:3461-3530`).
- `docs/ui/final-ui-audit-2.1.0.md` treats the 139/146 run as final under a prior
  waiver. This contract supersedes that waiver.

Update or annotate those documents in the foundation documentation change so
future agents do not implement stale behavior.

## Contract-change and acceptance rule

Product-specific agents may refine presentation within their assigned files,
but must not change business semantics, persistence, saved-state migration,
scene geometry, asset eligibility, entry-point ownership, or the vocabulary
above without an explicit reviewed contract change.

A changed surface is complete only when its unit/contract tests pass, its real
state transition is traced through the engine, its loading/empty/error/disabled/
success/stale variants are handled where relevant, and every affected capture
ID is regenerated deterministically in a complete fail-closed suite.

Product implementation may begin without waiting for additional platform
captures. Release approval may not be granted until the complete relevant
surface and timing contract passes natively on Windows and with true OS
100-percent, 150-percent, and 200-percent scaling plus high/mixed-DPI display
coverage. Logical resize or Qt scaling proxies do not satisfy that gate.
