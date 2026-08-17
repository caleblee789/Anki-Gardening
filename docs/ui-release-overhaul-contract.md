# Anki Garden UI release-overhaul contract

Status: implementation contract for Release 2.1.0. Current source declares
capture contract v16 with 191 ordered surfaces for the authoritative Growth
distribution and targetable Growth Charge overhaul. The requested v8 reference
remains the primary visual baseline but is incomplete at 139/146. The current
v16 run at
`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`
is complete and independently validator-clean at 191/191; it reconciles the
formerly missing IDs 019 and 064-069 without replacing the requested v8 visual
authority. This document records the current implementation boundary and the
still-separate native-platform and human-acceptance gates.

The source code and persisted-state behavior are authoritative. Existing UI
documents remain useful context, but any conflict called out in
[Documentation drift](#documentation-drift-to-reconcile) must be resolved in
favor of the traced implementation until a product decision explicitly changes
the contract.

## Authority and current baseline

The current mutable product boundary is schema 20 in
`user_files/garden_state.json`. It includes the authoritative resumable
`OnboardingProgress` state, canonical `GardenLoadoutState`, exact per-plant
passive-Growth residuals, canonical daily source/allocation ledgers, and bounded
completed purchase and Growth Charge replay ledgers.
`GardenStorage` loads, migrates, repairs, backs up, and atomically replaces that
file. Anki add-on configuration is a separate persistence domain managed by
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

That v9 run is historical pre-overhaul evidence. The subsequent source declared
capture contract v10 with 149 ordered
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

This closes manifest and contact-sheet completeness for the pre-change v10
source only. It does not establish native Windows, true OS 100/150/200-percent,
deliberate mixed-DPI transition, human assistive-technology, contrast, or full
product visual acceptance.

Capture contract v11 appended IDs 150-156 for starter placement, starter
completion, Home preview loading/error/stale, onboarding persistence failure,
and move persistence failure. IDs 001-149 retain their semantic identities.

The frozen v11 foundation run is:

`build/ui-face-captures/capture-sequence-20260816-173425/20260816-173427`

Its manifest, ordered records, and filesystem agree on 156 PNGs, including IDs
019 and 064-069. It records `complete: true`, zero failures, zero text/layout
warnings, complete fixture validation and manifest writing, 60 of 60 required
dialog-scroll audits passing, all 13 responsive-stability pairs passing, and a
12-cycle dialog-memory probe with zero watched-class deltas. The manifest-owned
20-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-173425`
is complete. A fresh independent repository-validator invocation reported all
156 surfaces and all 20 pages valid. The capture report records
`quality_status: clean`; the capture package SHA-256 is
`b4dada22a21891de3deebc022e268d20adef54c3bff6b34b76cdd7c5b370e342`.

This closes automated visual completeness for the frozen v11 source. It does
not establish native Windows, true OS-level
100/150/200-percent or high-DPI acceptance, human assistive-technology review,
contrast review, or full product visual acceptance.

Capture contract v12 preserves IDs 001-156 and appends ID 157,
`collection-known-not-collected-overview`, to pin the Collection mystery rule:
catalog species identity and Seed-through-Flowering previews remain known even
before collection; only the matching Rare artwork remains hidden until that
species reaches Rare.

The final v12 run is:

`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933`

Its manifest, ordered records, and filesystem agree on all 157 PNGs, including
019, 064-069, and the new 157. It records `complete: true`, zero failures, zero
text/layout warnings, complete fixture validation and manifest writing, 61 of
61 required dialog-scroll audits, all 13 responsive-stability pairs, and a
passing 12-cycle dialog-memory probe with zero watched-class deltas. The
manifest-owned 20-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-190930`
is complete and independently validator-clean. The capture package contains
267 files, is 81,825,556 bytes, and has SHA-256
`5249980b1990bade85a9b19c4c16f178185f632b025ba913d9b8c73d0c66a9a6`.

This closes automated visual completeness for the pre-purchase-overhaul v12
source on the captured macOS Qt mixed-display run. It does not establish native Windows, true OS-level
100/150/200-percent or high-DPI acceptance, human assistive-technology review,
contrast review, or full product visual acceptance.

Capture contract v14 preserves IDs 001-157 and the purchase IDs 158-181 for the
shared purchase confirmations, loading and typed error states, purchase
receipts, Fertilizer replacement breakpoint probes, Nursery empty state, and
Collection environment-mechanics state. The final v14 run at
`build/ui-face-captures/capture-sequence-20260817-003223/20260817-003226`
records exactly 181 ordered screenshots, zero capture failures or text-layout
warnings, complete fixture validation and manifest writing, 80 passing dialog-
scroll audits, all 13 responsive-stability pairs, and a passing 12-cycle dialog-
memory probe with zero watched-class deltas. IDs 019 and 064-069 are present.
The complete 23-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260817-003223`
and exact manifest independently validate as `valid` for 181 surfaces.

The immutable capture package contains 268 files, is 81,851,719 bytes, and has
SHA-256 `02ea6c23cd9b658b9e2829ead54e172e5d9ab5f16c0082e248c38f852e9f2fa9`.
The complete capture archive is 157,147,399 bytes with SHA-256
`8851d0b99a1da03cbec40f75ec6f5c5edab7fb225ec6184659629e4db576fd65`.
This closes pre-consolidation automated visual completeness on the captured
macOS Qt mixed-display run; it does not close the native-platform or human-
acceptance gates below.

Capture contract v15 preserves the 181 established IDs, replaces the retired
Customize labels at 030-032 and 116-120 with Collection loadout-detail and
preview semantics, and appends 182-183 for persistence rollback and
Collection-origin plant placement. The clean v15 run is:

`build/ui-face-captures/capture-sequence-20260817-054742/20260817-054745`

Its manifest, ordered records, and filesystem agree on all 183 PNGs. It is
`complete: true` with zero failures and zero text/layout warnings; IDs 019,
064-069, 182, and 183 are present. The manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260817-054742`
contains 24 complete pages and independently validates. The immutable capture
package contains 269 files, is 81,859,371 bytes, and has SHA-256
`7cbd24edf3a8832ede3e83c4c8da74d690c264e76b1fa2b8ff66a6f4c47cd8c9`.
The evidence ZIP is 160,899,994 bytes with SHA-256
`9a082c0dab1fc788a20c51b244d290a29448650675198d0a69d83671cbd11f54`.
The run records requested Qt scale 1.5 and mixed primary/secondary macOS display
provenance. This closes predecessor-source automated visual completeness, not the
native Windows, true OS-level 100/150/200-percent, high-DPI, mixed-DPI
transition, human assistive-technology, or full product visual-acceptance gates.

Capture contract v16 preserves IDs 001-183, renames ID 026 to
`progress-overview-redirect-growth`, and requires IDs 111-115 to render Plant
Growth instead of the retired Overview page. It appends IDs 184-191 for Growth
Charge ready, empty-inventory, loading/disabled, stale-inventory, invalid-target,
persistence-failure, success-with-stage-reward, and minimum-responsive states.

The final current-source v16 run is:

`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`

Its manifest, ordered records, and filesystem agree on all 191 PNGs, including
019, 064-069, and 184-191. It records `complete: true`, zero failures, zero
text/layout warnings, complete fixture validation and manifest writing, all 88
required dialog-scroll audits passing, all 13 responsive-stability pairs
passing, and a passing 12-cycle dialog-memory probe. All captures used the
primary macOS display at DPR 3.0 under requested Qt scale 1.5. The manifest-
owned 24-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260817-134654`
and exact manifest independently validate as `valid` for 191 surfaces.

The immutable capture package contains 270 files, is 81,874,326 bytes, and has
SHA-256 `eafd92e9b2dc560fbca215456b61fc0e2bd74f0d3c0233c0c269071bc0cc3c78`.
The evidence ZIP is 159,349,727 bytes with SHA-256
`d994dcd8a7cdd90ffe0a196c96b3cd7b8cbd67c7185df691dd85a5da4e89b4a3`.
This closes current-source automated manifest and contact-sheet completeness,
not the native Windows, true OS-level 100/150/200-percent, high/mixed-DPI,
keyboard-walkthrough, contrast, screen-reader, or human visual-acceptance gates.

## Approved downstream decisions

The following decisions define this implementation:

1. Schema 20 preserves the six-step, atomic, resumable onboarding state machine,
   exact passive fifths, canonical Growth source/allocation maps, and bounded
   purchase and Growth Charge replay ledgers. It collapses legacy equipment
   mirrors into one canonical `GardenLoadoutState`; schema-19 migration preserves
   undisaggregated current-day Growth in an explicit stale bucket.
   Add-on `onboarding_version` is migration input only, never renderer authority.
2. One renderer-neutral `GardenPreviewSnapshot` owns compact preview phase,
   scene data, title, summary, weather/scenery identity, motion, and scene fade.
3. One logical-coordinate `SceneGeometryLayout` owns bed, plant, selection,
   watering-can, move, hotspot, occlusion, safe-bound, and popover geometry.
4. The cottage opens Collection directly in the existing Garden Progress
   dialog. Collection owns collectible inspection, plant placement, reversible
   previews, and atomic Weather/Scenery/Decoration loadout mutations.
5. Native Windows and true OS-level 100/150/200/high-DPI acceptance remain
   separate release gates. Local logical-scale proxies do not close them.
6. Collection species identities and ordinary stage artwork are known catalog
   information everywhere. Only Rare artwork is mysterious, and it unlocks per
   species when that species reaches Rare.
7. `EffectDescriptor`, `PurchaseQuote`, `PurchaseRequest`, `PurchaseOutcome`,
   and `CompletedPurchaseRequest` are the shared commerce contracts. The
   engine owns quote and confirmation revalidation; renderers do not debit,
   grant, apply, equip, or unlock directly.

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
| 003, 150-151, 155 | First-run Garden | `GardenDashboard` | Open Garden before starter completion | Native Qt plus `GardenSceneWidget`; schema-20 state with resumable onboarding semantics and scene projection | Introduction, Nursery, confirmation, placement, nurture, completion, persistence error, and resume variants |
| 004-006 | Starter Nursery and confirmation | `NurseryDialog`, `StarterConfirmationDialog` | First-run route from Dashboard | Native Qt; release-ready asset catalog plus onboarding and ownership state | Choose, confirm, cancel/back; locked/no-stock, missing artwork, disabled, and action-above-footer variants |
| 007-008, 018-019, 064-069, 152-154 | Normal, nurtured, and watering Home | Anki Home card | Deck Browser/Overview hooks | Home HTML/CSS from `GardenPreviewSnapshot`; active plant, slots, metrics, currency, environment, and asset placement | Open Garden, Retry; no nurtured plant, active plant, watering marker per slot, loading, partial, error, and stale states |
| 009-012, 016, 042-055, 058-063, 087-103, 156 | Full Garden, plant interaction, Move, stress, focus, responsive, scaling | `GardenDashboard`, `GardenSceneWidget`, `PlantInfoCard` / `AnchoredPlantPopover` | Open Garden; scene selection; header and landmark actions | Native scene payload from engine state and shared `SceneGeometryLayout` | Select, Nurture, Fertilize, Move/swap, Story, Garden Progress, Collection, Settings, Undo; hover/focus, long values, all stages/plots, rollback, narrow/scaling variants |
| 013-015, 056-057, 136-143, 161-162, 173, 175-179 | Fertilizer and replacement confirmation | `PurchaseConfirmationDialog`, `FertilizerReplacementDialog` | Selected plant -> Fertilize | Native Qt; current state from `fertilizer_status()`, new terms from the engine quote, target, active interval/history, balance, and replay ledger | Purchase & Apply, Extend, Purchase & Replace, Keep current; unaffordable, active, expiring, persistence error, exact discarded time, and measured responsive variants |
| 017, 126-130 | Plant Story | `PlantStoryDialog` | Selected plant -> Story | Native Qt; plant identity, stage, Growth, memories, discovery, shared forecast/fertilizer projections, and asset metadata | Rename, cancel/close; new/no-memory, one/many memories, fully grown, Rare locked, missing art, save-error, and responsive variants |
| 020-021, 026, 111-115 | Plant Growth and stale Overview redirect | Plant Growth page in `GardenProgressDialog` | Plant Growth metric, General Progress, stale `overview` alias | Native Qt from `GardenUiSnapshot`; schema-20 daily study sources, per-plant nurtured/passive/direct allocations, residual fifths, stage projection, and planted-slot order | Inspect exact reconciling totals, expand/collapse Growth Breakdown, target a Charge; zero/nonzero, stale alias, and responsive variants |
| 022-025 | Streak and Garden Coins details | Focused pages in `GardenProgressDialog` | Dashboard metric buttons | Native Qt; review totals, streak, currency, and canonical reward ledger | Navigate/close; new, active, history, empty, and error variants |
| 027-032, 070-076, 116-120, 144-149, 157, 181-183 | Achievements, Collection, loadout details, species overview | `GardenProgressDialog`, `CollectibleDetailDialog`, species overview `GardenDialog` | Header Collection, cottage, metric routes, Nursery/Settings compatibility routes | Native Qt; registry-derived categories, plant instances, canonical loadout, shared descriptors, ownership/equipment/mystery metadata, and assets | Search/filter/sort, inspect, preview/apply/cancel/unequip, plant/place/move/remove/nurture, navigate; empty, locked, mystery, rollback, placement, mechanics, and responsive variants |
| 033-036, 077-081, 121-125, 158-174, 180 | Nursery catalog and commerce | `NurseryDialog`, `PurchaseConfirmationDialog` | Nursery landmark, first-run route, related product route | Native Qt; catalogs and `GardenGameEngine` projections over schema-20 state, shared descriptors, replay-safe quotes, normalized artwork metadata | Choose, Purchase, Use, open Collection, Unlock bed, Plant in garden, Move, Remove from garden; ready/loading/typed-error/success/empty/owned/locked/missing-art/footer variants |
| 184-191 | Growth Charge confirmation and receipt | `GrowthChargeConfirmationDialog` | Selected plant action or per-plant Plant Growth action | Native Qt over renderer-neutral quote/request/outcome contracts; target, inventory, Growth, scenery reward terms, and bounded replay ledger are revalidated at commit | Select Charge type, cancel, use, open Nursery, close receipt; ready, empty, loading, stale, invalid, rollback, rewarded success, and minimum-responsive variants |
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
| Fresh Garden | Choose first plant | `NurseryDialog` in starter mode, then `StarterConfirmationDialog` and scene placement | Species choice and confirmation persist without creating a plant; placement creates it atomically; Nurture remains separate |
| Dashboard header | Progress | Last valid session page in `GardenProgressDialog`, defaulting to Plant Growth | None; stale `overview` and unknown page keys normalize to Plant Growth |
| Dashboard header | Collection | Existing `GardenProgressDialog` Collection page | None |
| Dashboard header | Settings | `GardenSettingsDialog` | None until Save settings |
| Nursery landmark | Activate | `NurseryDialog` | None until a product action commits |
| Cottage landmark | Activate | Existing `GardenProgressDialog` Collection page | None; rapid activation is coalesced |
| Metric card | Plant Growth / Anki streak / Garden Coins | Focused `GardenProgressDialog` page | None |
| Selected plant card | Nurture | Engine `set_active_plant()` | Atomically changes future Growth routing and active periods |
| Selected plant card | Fertilize | Dedicated Fertilizer dialog | None until Purchase/Extend/Replace commits |
| Selected plant card or Plant Growth row | Growth Charge | Target-specific `GrowthChargeConfirmationDialog` | Atomic commit consumes one Charge and applies direct Growth only to the selected owned, planted, unfinished plant; no study buffs or passive fan-out |
| Selected plant card | Move | Scene placement mode | Destination commit changes slots atomically; Undo is session-local |
| Selected plant card | Story | `PlantStoryDialog` | None except a confirmed rename |
| Collection plant | Plant in garden | Engine `plant_from_collection()` | Atomically assigns an empty unlocked slot |
| Garden plant | Move to Collection | Engine `move_to_collection()` | Atomically clears its slot; prohibited for the nurtured plant |
| Collection species | Inspect | Species overview dialog | None |
| Collection collectible | Inspect or Preview | `CollectibleDetailDialog` | Preview is transient and restores the persisted appearance on cancel |
| Collection loadout detail | Apply changes | Engine `apply_garden_loadout()` | Atomically commits Weather, Scenery, Decoration, and visibility; failure restores the previous loadout |

Unknown Home bridge messages and unknown landmark action IDs must pass through
or fail closed without mutating Garden state. Move mode disables interactive
landmarks. Home and Settings previews never expose scene landmarks as actions.

Garden Progress keeps its last valid page only for the open application
session. `overview` is a compatibility input normalized to `growth`; it is not
a registered page, persisted route, or renderer. Unknown page keys also fall
back to Plant Growth. Target IDs passed to the Charge dialog remain transient
and are revalidated by the engine before any mutation.

## Persistence map

| State domain | Authority and path | Writers | Atomicity and idempotency contract |
|---|---|---|---|
| Garden progression, onboarding, economy, and loadout | `GardenState`, `user_files/garden_state.json`, schema 20 | `GardenGameEngine` through `GardenStorage.save()` | Same-directory temporary file and replace; guarded engine transitions restore state and pending stage transitions on failure; one persisted `GardenLoadoutState`; positive revlog IDs deduplicate study events; bounded purchase and Growth Charge ledgers replay successful request IDs; passive residuals persist as integer fifths |
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
3. Answer-time `active_plant_periods` resolves the owned, planted, unfinished
   plant being nurtured when the answer occurred.
4. The engine projects 10 base Growth plus percentage and flat Streak,
   Fertilizer, Booster, Weather, Scenery, and other contributions exactly once.
   `DailyStats` records those study sources; their sum is the final nurtured
   allocation, not total Garden Growth.
5. The nurtured plant receives the complete capped result. Every other eligible
   planted unfinished plant, ordered by slot and plant ID, adds that result to
   its persisted fifth accumulator, credits the whole `divmod(..., 5)` result,
   and retains the remainder. No passive plant reruns the modifier projection.
6. Each plant caps independently at Rare. The shared crossing path records one
   memory, notification, and `stage:{plant}:{stage}` Coin reward per crossing;
   only a plant that becomes fully grown discards its unusable residual.
7. Growth, residuals, daily source/allocation maps, processed revlog identity,
   feedback, rewards, and stage transitions save as one transaction. Failure
   restores both state and pending transitions.
8. After commit, Dashboard, Home, Plant Story, notifications, rewards, and
   diagnostics project the same canonical snapshot. A failed read, cutoff, or
   save advances no cursor and grants no partial Growth.

`ReviewAward.allocations` is the immutable per-plant result and
`ReviewAward.total_garden_growth` is a projection. `StageTransition` carries
plant name and source (`study_nurtured`, `study_passive`, `growth_charge`, or
`direct_reward`). Compatibility totals on `DailyStats` are computed properties,
not independently writable state.

## Growth Charge transaction flow

`ankigarden/growth.py` defines frozen `GrowthChargeQuote`,
`GrowthChargeRequest`, `GrowthChargeOutcome`, reward projection, status, and
completed-request records. A quote covers target identity/artwork, slot and
eligibility, current and projected Growth/stage, capped grant, exact stage Coin
rewards, Charge inventory before/after, and an opaque token over every
reward-affecting term including Scenery.

Confirmation checks the bounded replay ledger, validates the canonical request
UUID, then re-quotes current target, inventory, Growth, slot, completion state,
and reward terms. Identical retries return the stored outcome; conflicting UUID
reuse fails closed. Success decrements one Charge, applies direct Growth without
study modifiers or passive fan-out, runs the shared stage/reward path, queues
feedback, writes the replay record, and saves once. Failure restores inventory,
Growth, residuals, rewards, feedback, ledger, and pending transitions.

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

### Shared implemented contracts

`ankigarden/purchases.py` defines frozen `EffectDescriptor`, `PurchaseQuote`,
`PurchaseRequest`, `PurchaseOutcome`, and `CompletedPurchaseRequest` contracts.
The quote includes item/artwork/category identity, quantity one, current and
resulting balance, target, intended disposition, exact descriptor, current
Fertilizer comparison data where applicable, and an opaque token over the
quoted state. The request carries a caller-generated canonical UUID, quoted
token, expected price and balance, target, and explicit replacement
authorization.

### Quote, confirmation, and replay

`GardenGameEngine.quote_purchase()` covers species, Growth Charges,
Fertilizer, Weather, Scenery, and the next sequential bed. It returns typed
ready, insufficient, unavailable, already-owned, invalid-target, or stale-bed
terms without mutating state. `confirm_purchase()` first checks the bounded
completed-request ledger, then rebuilds the quote and revalidates item
availability, quantity, price, balance, ownership, target, active Fertilizer,
replacement authorization, and next-bed identity.

A confirmed request snapshots the complete state, debits Coins, grants or
applies the item, queues feedback, records the successful outcome, and performs
one atomic save. Any failure restores the snapshot. The same request UUID and
canonical fingerprint returns its saved `PurchaseOutcome` without another
debit or grant; conflicting reuse fails closed. A failed save records no
completed request, so the original request can be retried safely.

Schema 20 stores at most 500 completed purchase requests and 500 completed
Growth Charge requests separately from the 500-entry currency ledger. Earlier
migrations preserve onboarding, review-ledger, ownership, balance, placement,
and effect state. Legacy `purchase_*` engine methods are compatibility adapters
over the same quote/confirmation mutation path.

### Renderer contract

Every Garden Coin action opens `PurchaseConfirmationDialog` (replacement uses
its named `FertilizerReplacementDialog` subclass). The dialog never performs a
debit or grant. It shows the quote, prevents re-entry while submitting, and
passes its stable request to the engine. Stale price, balance, or target terms
are refreshed in place but never committed silently. Success receipts are
rendered from `PurchaseOutcome`; failures retain the original request for a
safe retry when recovery is possible.

`PurchasePresentation` is the shared customer-facing projection derived from
the quote, purchase intent, live state, and typed error. It supplies the title,
concise outcome, applicable decision facts, action label, price/balance strip,
target or inventory/equipment transition, processing copy, receipt, and
recovery actions. Nursery cards, confirmations, receipts, Collection mechanics,
and Garden Coin activity use these canonical mechanics and action terms rather
than duplicating product copy.

Ready confirmations show the item, what happens, two to four material facts,
the price, and the resulting balance. They omit inapplicable fields instead of
rendering `Not applicable`, `None`, `Replaces nothing`, or an irrelevant
quantity of one. The title is not repeated as a body question. Optional
nonessential mechanics live under **More details**. At 820 x 535, standard
confirmations have no scrollbar; the footer remains pinned and the single body
scroll region activates only when narrower content genuinely exceeds its
viewport. Terminal errors remove irrelevant mechanics and purchase controls;
recoverable failures retain only the terms needed to retry safely.

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
placement helpers. `AssetPlacement.thumbnail_bounds`,
`thumbnail_optical_center`, `thumbnail_scale`, and `thumbnail_safe_padding`
form the normalized thumbnail contract, with alpha bounds as the automatic
fallback. Plant Story, Collection, Nursery, species overview, Home, Dashboard,
Settings preview, and fallback thumbnails may not invent per-surface crop
offsets. Aspect ratio is preserved, meaningful foliage and roots remain inside
the safe frame, and the same normalized source is reused at each size. Catalog
species identities and Seed-through-Flowering artwork are known everywhere;
Rare art alone remains hidden until the matching species reaches Rare.

Cards-left and Fertilizer copy are also renderer-neutral projections.
`growth_forecast()` consumes the engine's next-card award projection so stage,
effective Growth-per-card, active buffs, singular/plural grammar, and fully
grown handling have one source. `fertilizer_status()` owns the structured name,
exact effect, stable duration, under-one-minute, expired, inactive, and
accessible-text states. Native surfaces render these projections and never
recalculate them from visible labels.

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
3. each far/middle/near planter base and direct-soil support surface;
4. plants ordered inside that perspective band;
5. the nurtured-plant watering can in the same band, clear of the normalized
   opaque planter-and-soil exclusion and behind that band's foreground art;
6. each band's planter rim/foreground occlusion;
7. selection, hover, and keyboard-focus contours;
8. procedural Weather motion;
9. Nursery and cottage landmarks;
10. Move dimmer, valid/invalid destinations, and placeholders;
11. status/help overlays and card connector.

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

Garden state owns collectible inventory/entitlements and exactly one canonical
`GardenLoadoutState`: selected Weather, Scenery, optional Decoration, and the
independent artwork-visibility switches. Legacy selected/equipped fields are
load-time migration input and compatibility projections, not persisted mirrors.
Validation repairs selections to owned items. Visibility affects rendering only.
Passive effects use selected IDs even when artwork is hidden
(`ankigarden/game.py:896-918`).

`apply_garden_loadout()` validates ownership and atomically saves the complete
loadout. The compatibility `apply_environment_loadout()` route delegates to it.
Collection stages the complete draft, previews without persistence, restores
the current appearance on cancel, and is the sole UI owner of Equip and
artwork-visibility changes.

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

Known current exceptions are nested scrolling in Settings Display (behavior
scroll plus GardenStudio controls scroll,
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
| Collection loadout detail | 920 px | Library and preview become two columns |
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

The v12 capture set covers one focused Dashboard control and one reduced-motion
Settings state; v14 additionally declares safe initial focus and disabled
submission states for purchase confirmation. Neither is evidence of complete tab order,
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
| Use | Consume an already-owned Growth Charge on any owned, planted, unfinished target, or a Booster on the current eligible nurtured plant. | Consumption and effect are saved together; failure consumes nothing. |
| Equip | Select one owned Weather or Scenery passive. | No Coin debit. Re-equipping the current item is an idempotent no-op. |
| Unequip | No supported action in Release 2.1.0. | Exactly one Weather and one Scenery remain selected. Hiding artwork is not Unequip and does not disable its passive. |
| Plant in garden | Assign one owned stored plant instance to an empty unlocked garden space. | Preserves all plant identity and progression. |
| Move | Relocate or swap a planted instance through direct scene placement. | Valid destination saves immediately; the open-session Undo may restore the latest placement. |
| Move to Collection | Remove a non-nurtured planted instance from its slot without deleting it. | Preserves Growth, memories, Fertilizer, Booster, and identity. This is the approved canonical learner-facing phrase; **Store** is not a competing action label. |
| Replace | Confirm discarding the remaining interval of a different active Fertilizer and activate the purchased tier. | Old interval is truncated/archived; debit and replacement save together. |
| Nurture | Route future eligible review Growth to one unfinished planted plant. | Updates active plant periods. It never moves or backfills prior Growth. |
| Fertilize | Open and complete the target-plant Fertilizer purchase flow. Same tier extends; another active tier requires Replace. | Purchase, interval history, activation/extension, balance, and ledger commit together. |

Purchase actions now use **Purchase**; Garden Spaces use the product-specific
**Unlock** label while still invoking the purchase transaction. Fertilizer uses
**Purchase & Apply**, **Extend**, or **Purchase & Replace** according to the
quoted disposition. **Apply changes** remains limited to saving a Collection
loadout draft and is not currency language. Placement and storage controls
use **Plant in garden**, **Move**, and **Move to Collection**; the former
**Buy**, **Apply**, **Shelve**, and ambiguous **Plant** purchase/placement labels
are not part of the current commerce UI.

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
concept. Rows explicitly marked proposed remain non-persisted unless stated.

| Requested concept | Repository contract | Decision |
|---|---|---|
| Plant display model | `PlantUiSnapshot`, `GardenUiSnapshot` | Extend the shared projection; do not create a second saved plant model. |
| Plant asset metadata | `AssetPlacement`, `ResolvedAsset` | Extend manifest/asset validation only through these types. |
| Effect descriptor | Frozen `EffectDescriptor` plus catalog projections | Implemented in `ankigarden/purchases.py`; Nursery and Collection consume the same exact mechanics. |
| Collectible descriptor | `CatalogItem` plus ownership projection | Reuse catalog plus state-derived ownership; do not persist UI cards. |
| Purchase intent/result | `PurchaseQuote`, `PurchaseRequest`, `PurchaseOutcome`, `CompletedPurchaseRequest` | Implemented shared contracts; the engine quotes, revalidates, commits, and replays outcomes. |
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
| Progress and Collection | `GardenProgressDialog`, Collection builders, and `CollectibleDetailDialog` in `ankigarden/ui/dashboard.py`; sole UI owner of collectible browsing, previews, Equip, and visibility mutations | Shared state, scene, Nursery, assets |
| Nursery and economy | `NurseryDialog`/Fertilizer ranges in `ankigarden/ui/dashboard.py`, purchase methods in `ankigarden/game.py`, `ankigarden/environment.py` | Transactions, assets, Collection |
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

Schema 18 is the current state boundary. Supported prior-schema migration is
backup-first and fail-closed (`ankigarden/storage.py` and
`docs/ui/data_contracts.md`). `scene_geometry_version` is independently
persisted and migrated (`ankigarden/models/state.py:278` and
`ankigarden/game.py:235-257`).

- `OnboardingProgress` is persisted Garden state; display snapshots, action
  descriptors, dialog targets, and scene-layer IDs remain projections only.
- The completed Apply/Shelve action-label rename requires no data migration.
- Schema-17-to-18 migration creates the required backup, preserves all existing
  state fields, and initializes a separately bounded 500-record
  completed-purchase history keyed by `PurchaseRequest.request_id`.
- Completed records store the canonical request fingerprint and successful
  `PurchaseOutcome`. Exact replay returns that outcome without another debit,
  grant, activation, or replacement; conflicting ID reuse fails closed.
- Migrated states do not backfill purchase-request records. They begin with an
  empty request history while retaining their existing currency ledger.
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

1. Schema-18 `GardenState` is the one mutable product source; Anki config is a
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
    fixture. Species identity and ordinary stages remain known throughout the
    Collection; Rare artwork remains locked per species until that species
    reaches Rare.
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
- Capture and next-step scheduling were independent in v8, allowing a window to
  close or the next fixture to begin before the current pixmap was secured. The
  v16 harness chains capture, cleanup, and advancement in that order.

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

Those results validate the historical v9 source only. The v10/149 contract
added the three Collection resize fixtures and followed source changes across
the responsive, dialog, control, and accessibility foundations. The v9 run
cannot serve as later after-change evidence.

The preserved pre-change run at
`build/ui-face-captures/capture-sequence-20260816-134539/20260816-134543`
regenerated all 149 v10 fixtures. The subsequent frozen v11 run at
`build/ui-face-captures/capture-sequence-20260816-173425/20260816-173427`
regenerated all 156 fixtures. Its exact manifest and 20-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`: status `valid`,
capture count 156, surface count 156, and page count 20. The manifest also
records all 60 required dialog-scroll audits, all 13 responsive-stability
pairs, and the 12-cycle dialog-memory probe as passing. This is complete
automated macOS Qt capture evidence for the frozen v11 source.

The pre-purchase-overhaul v12 run at
`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933`
regenerated all 157 fixtures. Its exact manifest and 20-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`: status `valid`,
capture count 157, surface count 157, and page count 20. The manifest records
all 61 required dialog-scroll audits, all 13 responsive-stability pairs, and
the 12-cycle dialog-memory probe as passing. This is complete automated macOS
Qt evidence for v12.

The pre-consolidation v14 run at
`build/ui-face-captures/capture-sequence-20260817-003223/20260817-003226`
regenerated all 181 fixtures. Its exact manifest and 23-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`: status `valid`,
capture count 181, surface count 181, and page count 23. The manifest records
all 80 required dialog-scroll audits, all 13 responsive-stability pairs, and
the 12-cycle dialog-memory probe as passing, with zero failures or text-layout
warnings.

The predecessor-source v15 run at
`build/ui-face-captures/capture-sequence-20260817-054742/20260817-054745`
regenerated all 183 fixtures. Its exact manifest and 24-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`; the manifest is
complete with zero failures and zero text/layout warnings. It includes the
renamed Collection loadout/detail states at 030-032 and 116-120, retained IDs
019 and 064-069, and new rollback/placement states 182-183.

The final current-source v16 run at
`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`
regenerated all 191 fixtures. Its exact manifest and 24-page manifest-owned
contact-sheet index passed `scripts/validate_ui_capture.py`: status `valid`,
capture count 191, surface count 191, and page count 24. The manifest records
all 88 required dialog-scroll audits, all 13 responsive-stability pairs, and
the 12-cycle dialog-memory probe as passing, with zero capture failures or
text/layout warnings. IDs 019 and 064-069 are present; IDs 184-191 prove the
target-specific Growth Charge confirmation states, including an exact 420x400
minimum-responsive fixture.

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
requested resize heights. The v16 run captured all 191 surfaces on the primary
macOS display at DPR 3.0 under requested Qt scale 1.5; that cleaner provenance
still does not substitute for native OS scale or cross-platform acceptance.

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
- Older entry-point documents assign environment mutations to a separate
  Customize dialog. Schema 20 and capture contract v16 keep Collection as the
  canonical browser, preview surface, and atomic loadout owner; old callers are
  compatibility routes into Collection.
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
