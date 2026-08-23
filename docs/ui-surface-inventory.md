# Anki Garden UI surface inventory

Status: Release 2.1.0 foundation inventory. The authoritative reference input is
`build/ui-face-captures/capture-sequence-20260815-170054/20260815-170057`, read
together with its manifest, metadata, logs, fixture source, and contact sheets.
That v8 run contains 139 of 146 required PNGs and `complete: false`. Historical
capture contract v9 reconciled it in
`build/ui-face-captures/capture-sequence-20260815-220049/20260815-220051` with
146 of 146 PNGs and `complete: true`. That closes the historical v9 macOS Qt
set only. Capture contract v10 added three Collection resize states; its
validator-clean macOS Qt run at
`build/ui-face-captures/capture-sequence-20260816-134539/20260816-134543` is
149 of 149. Capture contract v11 added resilient states 150-156. The v12 run at
`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933` is
the complete 157-of-157 pre-purchase-overhaul baseline. Capture contract v14
added purchase states through 181, and v15 added Collection transaction states
182-183. Its validator-clean predecessor run at
`build/ui-face-captures/capture-sequence-20260817-054742/20260817-054745`
records all 183 surfaces. Current source declares capture contract v19 with 126
distinct ordered surfaces and states. It retains the functional and state
coverage introduced through v18, including the disabled-Home-preview Settings
state, Settings validation failure, expanded diagnostics, the production-build
capability branch, canonical Clear Recall and streak-achievement projections,
real Reviewer Garden Find notifications, and Growth Charge outcomes. Each distinct face is
captured once at canonical 100% scale under `QT_SCALE_FACTOR=1.0`. Resize,
breakpoint, 150%, and 200% screenshot duplicates are excluded; responsive
geometry remains an automated release gate outside the screenshot manifest.
The older complete v16 run is predecessor-source evidence only. The final
current-source v19 run is complete at 126/126 faces in the exact 17-sheet set
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260823-000843`.

The table below uses the current capture order from `CAPTURE_FACE_GROUPS`.
Contract v19 filters the predecessor list to distinct functional and state
faces, then renumbers the retained labels 001-126 in manifest order. Purchase
confirmations, typed errors, receipts, Nursery empty state, Collection
transaction states, and Growth Charge confirmation/outcome states remain; only
resize, breakpoint, and scale duplicates are omitted. Capture contract v9
source-faithfully renamed the old ID 076 from
`streak-reward-claimed-unclaimed` to `streak-reward-earned-next`; later reward
work replaced that label with `streak-achievement-earned-next`, now v19 ID 076.
Viewports use their declared logical Qt client sizes; final realized dimensions
for the three Reviewer faces come from the v19 manifest at
`build/ui-face-captures/capture-sequence-20260823-000843/20260823-000847/manifest.json`.
A
`declared -> actual` value means a screen, widget, or native-frame constraint
normalized the request. Responsive modes recorded on retained faces describe
their canonical fixture, not additional breakpoint screenshots. The formerly
missing Home rows use the same 667x570 Anki window as their adjacent Home
fixtures.

## Capture reconciliation and visual-audit status

In the requested v8 reference, the seven missing files are exactly the
suspected IDs:

| ID | Required state | Why it is absent from v8 |
|---:|---|---|
| 019 | `active-overview-home-after-nurture` | The exact Anki Home window failed the macOS foreground/key-window gate; `_capture_home_pixmap()` returned no image and the caller reduced that to `Qt returned no pixmap`. |
| 064-066 | Deck Browser watering markers in plots 1, 3, and 5 | Same foreground/key-window failure; the fixtures and persisted active-slot states were present. |
| 067-069 | Overview watering markers in plots 2, 4, and 6 | Same foreground/key-window failure; the fixtures and persisted active-slot states were present. |

The v8 manifest, capture records, and filesystem agree on 139 files, with no
extra, zero-byte, or misnumbered PNG. The external capture runner returned
nonzero, but the in-Anki v8 harness had timeout and exception paths that could
advance without a precise fixture failure. Contract v9 closes those paths,
records an expected-versus-actual renderer family for every row, and restricts
a non-foreground Home fallback to the app-owned Qt/WebEngine composition.

The fresh v9 run regenerated all IDs 001-146 and recovered exactly 019 and
064-069. Its manifest, ordered records, and filesystem agree on 146 PNGs, with
zero failures, zero warnings, zero fixture-provenance mismatches, and
`complete: true`. The contact-sheet generator
produced 19 pages in
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260815-220049`,
and the independent repository validator reported all 146 surfaces and all 19
pages valid. Two clean regenerations with the same stamp produced identical
SHA-256 hashes for all 19 pages and the set index. The stress fixtures also
verify the canonical species order `bonsai`, `rose`, `sunflower`, `lavender`,
`hydrangea`, `peony`, `foxglove`, `japanese_maple`, `wisteria`, `dahlia`. No
required fixture silently fell back to a neighboring renderer or state
according to the v9 immutable scheduled provenance and live-postcondition
records. The reduced-motion fixture restores its baseline before focus capture,
and the focus owner is cleared before narrow, scaling, and resize fixtures.

The v9 result is historical and stale for the current source. Capture contract
v10 regenerated all 149 ordered IDs, including 019, 064-069, and the new
Collection states 147-149, at
`build/ui-face-captures/capture-sequence-20260816-134539/20260816-134543`.
Its manifest and filesystem agree on 149 PNGs with `complete: true`, empty
`failures` and `text_layout_warnings`, complete fixture validation, 60 of 60
required dialog-scroll audits passing, and all 13 responsive-stability pairs
passing. The complete 19-page manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-134539`
and exact manifest passed the independent repository validator.

The frozen v11 run regenerated all IDs 001-156 at
`build/ui-face-captures/capture-sequence-20260816-173425/20260816-173427`.
Its manifest and filesystem agree on 156 PNGs with `complete: true`, zero
failures and text/layout warnings, complete fixture validation, 60 of 60
dialog-scroll audits, all 13 responsive-stability pairs, and a passing 12-cycle
dialog-memory probe. The complete 20-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-173425`
and exact manifest passed the independent repository validator for all 156
surfaces. IDs 019 and 064-069 are present and pass their fixture and geometry
audits.

The pre-purchase-overhaul v12 run regenerated all IDs 001-157 at
`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933`.
Its manifest and filesystem agree on 157 PNGs with `complete: true`, zero
failures and text/layout warnings, complete fixture validation, 61 of 61
dialog-scroll audits, all 13 responsive-stability pairs, and a passing 12-cycle
dialog-memory probe. The complete 20-page contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260816-190930`
and exact manifest passed the independent repository validator for all 157
surfaces. IDs 019 and 064-069 remain present. ID 157 explicitly proves that a
known catalog species with zero collected instances keeps its identity and
ordinary stage previews while Rare remains mysterious.

Contract v14 retains those identities and the 24 source-owned purchase fixtures.
The final run at
`build/ui-face-captures/capture-sequence-20260817-003223/20260817-003226`
has exact ordered 181/181 agreement, including 019 and 064-069, with zero
capture failures or text/layout warnings, 80 passing dialog-scroll audits, all
13 responsive-stability pairs, five confirmation resize modes, and 23 complete
contact-sheet pages. The exact manifest and contact-sheet index pass the
independent repository validator.

Contract v15 replaced the retired Customize identities at 030-032 and 116-120
with Collection loadout-detail and preview identities, then appended 182-183.
The run at
`build/ui-face-captures/capture-sequence-20260817-054742/20260817-054745`
has exact ordered 183/183 agreement, zero failures or text/layout warnings, and
a complete validator-clean 24-page contact-sheet set. It is predecessor-source
evidence only after the v16 Growth overhaul.

Contract v16 required all 191 surfaces. The requested v8 visual baseline remains
139/146 and incomplete; no later complete run replaces its visual authority.
The v16 run at
`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`
has exact ordered 191/191 agreement, including 019, 064-069, and 184-191, with
zero capture failures or text/layout warnings. All 88 dialog-scroll audits, all
13 responsive-stability pairs, and the 12-cycle dialog-memory probe pass. The
24-page manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260817-134654`
and the exact manifest pass the independent repository validator. This closes
v16 predecessor-source automated completeness only.

Contract v19 contains 126 distinct surfaces and states and requires exactly 17
contact sheets. Its final current-source run at canonical 100% scale is
intentionally pending. No earlier run, partial run, or complete-looking v16 set
is acceptance for the v19 reward, achievement, and Reviewer Find fixtures.

Manual review of every raw PNG and all 18 partial contact sheets found these
successful-file exceptions in the v8 baseline:

- 007 is byte-identical to 001 and 008 is byte-identical to 002. Both normal
  Home captures show stale first-run copy instead of the real planted-before-
  Nurture state. The direct engine starter transaction did not invalidate the
  Home HTML cache, while readiness checked only a generic painted state.
- 046 contains the development-population toast. Contract v9 clears transient
  capture setup feedback before the frame.
- 070 says 10 of 10 species discovered, contradicting “several.” Contract v9
  uses and audits a deterministic 4-of-10 fixture.
- The former 076 name claimed a claimed/unclaimed distinction the product does
  not implement. Rewards are automatic; the visible state is 7/14 earned and
  30 days next. Contract v9 renames the fixture rather than preserving false
  coverage.
- 082, 083, and 086 inherit stale nested scroll positions. The Garden-name row
  is partly hidden under the tabs, and 086 does not show its Reduced Motion
  control. Contract v9 resets both Settings scroll regions and explicitly
  reveals the checked control.
- Capture 039 intentionally presents partial Advanced-tab context at a scroll
  boundary to prove that long Settings content is scrollable. It is not a
  clipping defect.
- In the v8 baseline, 066 ellipsizes the Home detail line at the fixed Home
  width.
- In the v8 baseline, 111 clips the final “s” in Achievements at the minimum
  Progress width. This is a real downstream layout risk, not fixed by the
  foundation harness.
- 090 is byte-identical to 091 because it is only a 620x520 logical proxy. Its
  manifest explicitly says the OS display scale did not change.
- In v8, 100-103 normalized to the same 1140x699 window and were byte-identical.
  The v9 run preserved their requested widths: 100 was 1383x699 compact and 101
  was 1385x699 wide. That old fixed-edge mode change is historical, not the
  historical v10 behavior. The v10 source kept both top-level compact and retained
  the pair as a stability probe. The available screen still capped several
  requested resize heights at 699 pixels.

The v8, v9, and v10 values of zero text-layout warnings are automated threshold
results. They cover visible native label/button glyph boxes, selected ancestor
boundaries, and a coarse branded-pixel Home gate. They do not evaluate
WebEngine copy, fixture correctness, scroll-hidden controls, sticky-header
overlap, contrast, visual hierarchy, duplicate frames, native Windows behavior,
or true OS-level standard/200-percent scaling.

Targeted inspection of the final v10 raw PNGs confirms that 066 no longer
ellipsizes the Home detail, 090/091 keep the compact Dashboard identity
readable, 111 wraps the Progress navigation without clipping, 57/143 fit their
wide replacement content at 820x360 with no scrolling, 146 fits at 900x400,
and 147 remains usable at the
minimum Collection size. Capture 039 is the intentional scroll-context fixture
described above. This screenshot inspection is not human assistive-technology
acceptance.

## Profile expansion

Every inventory row names a profile. The profile supplies the requested
user-facing surface, entry point, persistence dependencies, primary actions,
and empty/loading/locked/success/error variants for that row; the row then adds
its exact fixture, component, viewport, mode, and owner.

| Profile | User-facing surface and entry point | Persistence and source of truth | Primary actions | Required variants, including uncaptured gaps | Fixture implementation |
|---|---|---|---|---|---|
| FH | First-run Anki Home; Deck Browser/Overview render hooks and Home bridge | Schema-21 `GardenState` projection: onboarding, plants, Garden name, daily metrics, Coins, selected environment, shared asset metadata; transient request ID rejects stale responses | Choose first plant, Open Garden, Retry | Loading, no-starter/empty, success, partial, error, disabled opening, stale response | `_capture_starter_deck_browser()` / `_capture_starter_overview()`; real Home HTML |
| FG | First-run Garden; `AnkiGardenApp.open_dashboard()` | Same `GardenState` plus `select_garden_ui()` and scene payload; persisted onboarding owns the resumable step | Choose first plant, open Nursery | No starter, no release-ready stock, planted-before-Nurture, normal, save error | `_capture_starter_garden()`; native Dashboard/Scene |
| FN | Starter Nursery; first-run direct Nursery route | Release-ready six-stage asset catalog plus onboarding/species/plants/slots; no mutation until confirmed Choose | Choose, page/filter, back | No stock, locked/missing art, disabled, confirmation, footer reachability, save error | `_capture_starter_nursery_after()`; real catalog in starter mode |
| FC | Starter confirmation; selected Nursery starter | Selected release-ready species is transient; confirmation persists the species choice, while placement atomically creates one specific plant instance in the chosen bed | Confirm Choose, cancel/back | Enabled/disabled, save error, compact/wide | `_capture_starter_confirmation()`; responsive geometry is automated |
| H | Normal/active Home; Deck Browser/Overview hooks | Authoritative Garden state, active periods/plant, slots, Growth/streak/Coins, environment visibility, asset metadata; coordinator revision invalidates cache | Open Garden, Retry | Planted not nurtured, active, six marker slots, loading, partial, error, stale response | Home fixture methods plus source-backed DOM identity check |
| G | Dashboard, Garden, popovers, Move, focus, scaling and responsive states; Open Garden/scene/header/landmarks | Garden state plants/slots/active periods/name/Coins/effects/scene geometry; Move/selection/hover/focus/viewport are transient | Select, Nurture, Fertilize, Growth Charge, Move, Return to Collection, Plant in garden, Story, Garden Progress, Collection, Settings, Undo | Empty/loading/error, no selection, locked/disabled, success toast, save failure, long/dynamic values, all stages/plots, focus, narrow/high-DPI | Named `_capture_*` fixture for distinct states; responsive/high-DPI geometry is automated |
| F | Fertilizer dialog; selected plant -> Fertilize | Current effect from `fertilizer_status()`, new effect/target/price/balance/disposition from `PurchaseQuote`, and completed-request replay ledger | Purchase & Apply, Extend, Purchase & Replace, Keep current | Unaffordable, active, expiring/stale countdown, invalid target, persistence error, success receipt, responsive | `_capture_fertilize_after()`, expiring fixture, and purchase fixtures; responsive geometry is automated |
| FR | Fertilizer replacement confirmation | Current name/effect/seconds remaining from `fertilizer_status()`; new name/effect/full duration, price, target, and replacement requirement from the engine quote | Keep current, Purchase & Replace | Exact discarded time, current/new cards, disabled/stale target, save error, compact/wide | `_capture_fertilizer_replacement_confirmation()` and v14 confirmation; responsive geometry is automated |
| ST | Plant Story; selected plant -> Story | Plant identity/species/stage/Growth/memories/discovery and asset metadata; rename persists atomically | Rename/save, close, Choose another when eligible | No/one/many memories, locked Rare, missing art, success/error, responsive | `_capture_story_after()` for the distinct state; responsive geometry is automated |
| P | Plant Growth/Streak/Coins, Progress, Achievements and Collection; metric/header/cottage routes | Canonical study sources, per-plant nurtured/passive/direct allocations, residual fifths, streak, currency ledger, achievements/reward history, plants/species discovery, and environment ownership/status | Navigate, disclose Growth breakdown, target a Charge, filter, inspect species/effects, manage loadout, close | Zero/new/nonzero/fractional/active, empty/filter-empty, stale migration, locked, completed, at-risk/missed, earned/next, loading/error/disabled, responsive | Growth fixture, `_capture_metric()`, `_capture_progress_page()`, and collection fixtures; responsive geometry is automated |
| SO | Species overview; any known catalog species | Catalog identity plus owned instances, highest reached stage/discovery, shared thumbnail metadata, and per-species Rare unlock | Inspect/close | Collected, known-not-collected, zero instances, locked Rare, missing art, responsive | `_build_species_overview_dialog()` plus distinct overview fixtures; responsive geometry is automated |
| C | Collection loadout detail and preview | One local draft over persisted inventory, selected Weather/Scenery and visual-only visibility flags; `apply_garden_loadout()` is the atomic commit | Choose owned effects, toggle artwork, apply, cancel preview | Clean/dirty, on/off, unowned/locked, success/error/rollback, responsive | Collection loadout/detail fixtures and native preview; responsive geometry is automated |
| N | Nursery commerce; Nursery landmark/first-run/related routes | Catalogs and engine projections over schema-21 state, shared effect descriptors, normalized artwork, purchase quotes, Coins/ledgers, ownership/inventory, slots, and release-ready assets | Choose, Purchase, Use, Unlock bed, Plant in garden, Move, Return to Collection, open Collection, browse | Owned/equipped/locked/disabled, ready/loading/typed error/success, empty/no stock, missing-art fallback, footer reachability, responsive | Nursery tab/stress/purchase fixtures; responsive geometry is automated |
| GC | Growth Charge confirmation; selected plant or Plant Growth row | Frozen quote/request/outcome contracts over target eligibility, Growth, selected Scenery reward terms, Charge inventory, and bounded completed-request ledger | Select Charge type, Use Growth Charge, Cancel, Open Nursery, Close receipt | Ready, empty, loading/disabled, stale inventory, invalid target, persistence rollback, rewarded success, minimum responsive | `_capture_growth_charge_dialog_fixture()` for distinct states; minimum-responsive geometry is automated |
| SD | Settings and Diagnostics; Anki menu or Dashboard Settings | Staged Anki config plus separately persisted Garden name; runtime diagnostics/build capabilities/telemetry are derived | Save changes, cancel, restore defaults, toggle, expand/refresh/copy diagnostics | Clean/warning, dirty, rollback/error, reduced motion, responsive | Settings fixture methods for distinct states; responsive geometry is automated and both scroll positions reset |
| R | Real Anki Reviewer plus nonmodal reward notification | Persisted reward/find outcomes joined through canonical presentation registries; the Reviewer adapter renders one consolidated focus-safe result and acknowledges every rendered event ID | Continue reviewing; no dismissal required | Common under reduced motion, Rare environment Find, stacked synchronized Finds and achievement/reward summary, keyboard-focus preservation | `_capture_reviewer_find_*()` through the real Reviewer state and `ReviewerRewardFeedback` |

All product mutations in these profiles must remain engine-authoritative,
rollback-safe, and atomically saved. Capture-only viewport, route, hover, focus,
filter, and draft state must never enter `garden_state.json`. Review/reward
events retain stable event keys; every Coin purchase and Growth Charge use has a
separate bounded completed-request replay ledger and one engine-owned atomic
mutation path.

## Display and viewport interpretation

The reference v8 set used the primary macOS display. The final v9 set records a
mixed-display run: six first-run captures used the secondary display at DPR
1.5 and 140 captures used the primary display at DPR 3.0. The v10 run
records six captures on the secondary display at DPR 1.5 and 143 on the primary
display at DPR 3.0. The v12 run records six captures on the secondary
display at DPR 1.5 and 151 on the primary display at DPR 3.0. These runs used
requested `QT_SCALE_FACTOR=1.5`. The v14 and v15 runs likewise record mixed
secondary and primary display provenance under requested scale factor 1.5. The
v16 predecessor run records all 191 surfaces on the primary display at DPR 3.0
under the same requested scale. No v19 display provenance exists until the
pending canonical-100% run under `QT_SCALE_FACTOR=1.0`. Historical provenance
is useful, but it is not native
mixed-DPI acceptance because the suite did not deliberately exercise cross-
display transitions.
There is no current native standard-scale, true OS 200-percent, or Windows
acceptance run. Historical predecessor capture 090 was a logical Qt proxy, not
true OS 200-percent evidence. Responsive mode is transient capture metadata and
is never persisted.

## Ordered surface inventory

| ID | Capture state | Profile | Component / renderer | Fixture data and preparation | Viewport (logical px) | Responsive mode | Owning agent |
|---:|---|:---:|---|---|---:|---|---|
| 001 | `starter-deck-browser-home` | FH | AnkiQt / Home HTML | Untouched schema-21 starter state on Deck Browser | 667x570 | default | Home + First run |
| 002 | `starter-overview-home` | FH | AnkiQt / Home HTML | Untouched schema-21 starter state on Overview | 667x570 | default | Home + First run |
| 003 | `starter-garden-onboarding` | FG | GardenDashboard / GardenSceneWidget | Untouched state; onboarding step 1 visible | 1177x630 | compact | First run + Garden |
| 004 | `starter-nursery-plants` | FN | NurseryDialog | Release-ready starter catalog; no owned plant | 1177x630 | wide | Nursery + First run |
| 005 | `starter-selection-confirmation` | FC | StarterConfirmationDialog | First release-ready species awaiting confirmation | 480x300 | wide | First run |
| 006 | `starter-action-above-footer` | FN | NurseryDialog | Starter action scrolled above fixed footer | 1177x630 | wide | Nursery + First run |
| 007 | `deck-browser-home` | H | AnkiQt / Home HTML | Real Choose commit; planted starter, `active_plant_id=None` | 667x570 | default | Home |
| 008 | `overview-home` | H | AnkiQt / Home HTML | Real Choose commit; planted starter, `active_plant_id=None` | 667x570 | default | Home |
| 009 | `full-garden` | G | GardenDashboard / GardenSceneWidget | Planted-before-Nurture dashboard overview | 1177x630 | compact | Garden + Scene |
| 010 | `hover-outline` | G | GardenDashboard / GardenSceneWidget | Representative plant hovered, not selected | 1177x630 | compact | Garden + Scene |
| 011 | `selected-plant-not-nurtured` | G | GardenDashboard / GardenSceneWidget | Starter selected before Nurture | 1177x630 | compact | Garden + Scene |
| 012 | `selected-plant-nurtured` | G | GardenDashboard / GardenSceneWidget | Real Nurture commit plus first-Nurture memory | 1177x630 | compact | Garden + Scene |
| 013 | `fertilizer-unaffordable` | F | DialogShell (`FertilizerDialog`) | 0 Coins; no fertilizer | 960x629 | default | Economy |
| 014 | `fertilizer-affordable` | F | DialogShell (`FertilizerDialog`) | 500 Coins; no fertilizer | 960x629 | default | Economy |
| 015 | `fertilizer-active` | F | DialogShell (`FertilizerDialog`) | 500 Coins; active Basic fertilizer | 960x629 | default | Economy |
| 016 | `move-mode` | G | GardenDashboard / GardenSceneWidget | Active plant in placement draft | 1177x630 | compact | Garden + Scene |
| 017 | `plant-story` | ST | PlantStoryDialog | Selected plant identity, stage, Growth, and memories | 960x629 | wide | Story + Collection |
| 018 | `active-deck-browser-home-after-nurture` | H | AnkiQt / Home HTML | Persisted first-Nurture state on Deck Browser | 667x570 | default | Home |
| 019 | `active-overview-home-after-nurture` | H | AnkiQt / Home HTML | Persisted first-Nurture state on Overview | 667x570 | default | Home |
| 020 | `growth-zero` | P | GardenProgressDialog | Three planted plants; canonical study sources and target allocations all zero | 1140x630 | wide | Progress + Growth |
| 021 | `growth-nonzero` | P | GardenProgressDialog | Three planted plants; all modifier rows, 53 study Growth, exact fractional passive allocations, Charge/direct Growth, and reconciling totals | 1140x630 | wide | Progress + Growth |
| 022 | `streak-new` | P | GardenProgressDialog | New 0-day streak presentation | 1140x630 | wide | Progress + Collection |
| 023 | `streak-active` | P | GardenProgressDialog | Active current-day streak presentation | 1140x630 | wide | Progress + Collection |
| 024 | `coins-zero` | P | GardenProgressDialog | 0 Coins and empty ledger | 1140x630 | wide | Progress + Collection |
| 025 | `coins-activity` | P | GardenProgressDialog | 0 start plus real stage/streak credits in ledger | 1140x630 | wide | Progress + Collection |
| 026 | `progress-overview-redirect-growth` | P | GardenProgressDialog | Stale `overview` route normalized to registered Plant Growth page | 1140x630 | wide | Progress + Growth |
| 027 | `progress-achievements` | P | GardenProgressDialog | Progress route: achievements | 1140x630 | wide | Progress + Collection |
| 028 | `progress-collection` | P | GardenProgressDialog | Progress route: collection | 1140x630 | wide | Progress + Collection |
| 029 | `collection-species-overview` | SO | GardenDialog (`SpeciesOverviewDialog`) | Owned species selected from Collection | 960x400 | default | Progress + Collection |
| 030 | `collection-loadout-detail` | C | CollectibleDetailDialog | Canonical saved Weather/Scenery loadout and ownership details | 1139x644 | wide | Collection + Environment |
| 031 | `collection-preview-active` | C | CollectibleDetailDialog | Reversible local preview with Weather/Scenery effects visible | 1139x644 | wide | Collection + Environment |
| 032 | `collection-preview-restored` | C | CollectibleDetailDialog | Preview cancelled and persisted appearance restored | 1139x644 | wide | Collection + Environment |
| 033 | `nursery-plants` | N | NurseryDialog | Nursery tab 1 catalog projection | 1048x643 | wide | Nursery + Economy |
| 034 | `nursery-fertilizer-booster` | N | NurseryDialog | Nursery tab 2 catalog projection | 1048x643 | wide | Nursery + Economy |
| 035 | `nursery-garden-spaces` | N | NurseryDialog | Nursery tab 3 catalog projection | 1048x643 | wide | Nursery + Economy |
| 036 | `nursery-weather-scenery` | N | NurseryDialog | Nursery tab 4 catalog projection | 1048x643 | wide | Nursery + Economy |
| 037 | `settings-home-preview-disabled` | SD | GardenSettingsDialog / GardenStudioWidget | Settings opened through the registered Anki menu with the unsaved Home preview toggle disabled | 1048x643 | display | Settings + Diagnostics |
| 038 | `settings-display` | SD | GardenSettingsDialog / GardenStudioWidget | Display tab reset to top | 1048x643 | display | Settings + Diagnostics |
| 039 | `settings-display-advanced-open` | SD | GardenSettingsDialog / GardenStudioWidget | Display tab with Advanced controls expanded | 1048x643 | display | Settings + Diagnostics |
| 040 | `diagnostics-clean` | SD | GardenSettingsDialog / GardenStudioWidget | Troubleshooting with clean runtime telemetry | 1048x643 | troubleshooting | Settings + Diagnostics |
| 041 | `diagnostics-warning` | SD | GardenSettingsDialog / GardenStudioWidget | Injected required-field telemetry warning | 1048x643 | troubleshooting | Settings + Diagnostics |
| 042 | `long-garden-name` | G | GardenDashboard / GardenSceneWidget | Maximum-length Garden name | 1140x630 | compact | Garden + Scene |
| 043 | `long-plant-name` | G | GardenDashboard / GardenSceneWidget | Maximum-length plant name | 1140x630 | compact | Garden + Scene |
| 044 | `four-digit-coin-balance` | G | GardenDashboard / GardenSceneWidget | 9,999-Coin balance | 1140x630 | compact | Garden + Scene |
| 045 | `growth-near-stage-completion` | G | GardenDashboard / GardenSceneWidget | Active plant 25 Growth below Rare threshold | 1140x630 | compact | Garden + Scene |
| 046 | `all-six-beds-occupied` | G | GardenDashboard / GardenSceneWidget | Development fixture; six occupied plots; toast cleared | 1140x630 | compact | Garden + Scene |
| 047 | `plant-at-every-stage` | G | GardenDashboard / GardenSceneWidget | Six plots mapped to Seed through Rare stages | 1140x630 | compact | Garden + Scene |
| 048 | `fully-grown-plant-without-fertilize` | G | GardenDashboard / GardenSceneWidget | Fully grown selected plant; Fertilize hidden | 1140x630 | compact | Garden + Scene |
| 049 | `popover-plot-1` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 1 | 1140x630 | compact | Garden + Scene |
| 050 | `popover-plot-2` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 2 | 1140x630 | compact | Garden + Scene |
| 051 | `popover-plot-3` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 3 | 1140x630 | compact | Garden + Scene |
| 052 | `popover-plot-4` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 4 | 1140x630 | compact | Garden + Scene |
| 053 | `popover-plot-5` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 5 | 1140x630 | compact | Garden + Scene |
| 054 | `popover-plot-6` | G | GardenDashboard / GardenSceneWidget | Persistent popover opened for plot 6 | 1140x630 | compact | Garden + Scene |
| 055 | `move-occupied-empty-destinations` | G | GardenDashboard / GardenSceneWidget | Four occupied and two empty Move destinations | 1140x630 | compact | Garden + Scene |
| 056 | `fertilizer-expiring-under-minute` | F | DialogShell (`FertilizerDialog`) | Basic fertilizer expires in 45 seconds | 960x629 | default | Economy |
| 057 | `fertilizer-replacement-confirmation` | FR | FertilizerReplacementDialog | Active Basic -> Premium replacement confirmation | 820x360 | wide | Economy |
| 058 | `watering-can-garden-plot-1` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 1 | 1140x630 | compact | Garden + Scene |
| 059 | `watering-can-garden-plot-2` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 2 | 1140x630 | compact | Garden + Scene |
| 060 | `watering-can-garden-plot-3` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 3 | 1140x630 | compact | Garden + Scene |
| 061 | `watering-can-garden-plot-4` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 4 | 1140x630 | compact | Garden + Scene |
| 062 | `watering-can-garden-plot-5` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 5 | 1140x630 | compact | Garden + Scene |
| 063 | `watering-can-garden-plot-6` | G | GardenDashboard / GardenSceneWidget | Nurtured marker committed to Garden plot 6 | 1140x630 | compact | Garden + Scene |
| 064 | `watering-can-deck-browser-plot-1` | H | AnkiQt / Home HTML | Nurtured marker on Deck Browser plot 1 | 667x570 | default | Home |
| 065 | `watering-can-deck-browser-plot-3` | H | AnkiQt / Home HTML | Nurtured marker on Deck Browser plot 3 | 667x570 | default | Home |
| 066 | `watering-can-deck-browser-plot-5` | H | AnkiQt / Home HTML | Nurtured marker on Deck Browser plot 5 | 667x570 | default | Home |
| 067 | `watering-can-overview-plot-2` | H | AnkiQt / Home HTML | Nurtured marker on Overview plot 2 | 667x570 | default | Home |
| 068 | `watering-can-overview-plot-4` | H | AnkiQt / Home HTML | Nurtured marker on Overview plot 4 | 667x570 | default | Home |
| 069 | `watering-can-overview-plot-6` | H | AnkiQt / Home HTML | Nurtured marker on Overview plot 6 | 667x570 | default | Home |
| 070 | `collection-several-discovered` | P | GardenProgressDialog | Exactly 4 of 10 catalog species collected; all identities remain known and Rare stays gated per species | 1140x630 | wide | Progress + Collection |
| 071 | `collection-no-filter-matches` | P | GardenProgressDialog | All 10 species collected; Not collected filter produces the explicit empty result | 1140x630 | wide | Progress + Collection |
| 072 | `achievement-completed` | P | GardenProgressDialog | Coherent completed achievement thresholds | 1140x630 | wide | Progress + Collection |
| 073 | `clear-recall-canonical-projection` | P | GardenProgressDialog | Canonical Clear Recall projection: 12/20 answers, 83% non-Again, exact +10-Coin reward | 1140x630 | wide | Progress + Collection |
| 074 | `streak-at-risk` | P | GardenProgressDialog | 7-day streak; no review today; last active yesterday | 1140x630 | wide | Progress + Collection |
| 075 | `streak-missed-day` | P | GardenProgressDialog | Ended streak: current 0, previous 3 days | 1140x630 | wide | Progress + Collection |
| 076 | `streak-achievement-earned-next` | P | GardenProgressDialog | 14-day streak; 7-Day achievement earned once; day-30 Growth tier and 30-Day achievement next | 1140x630 | wide | Progress + Collection |
| 077 | `nursery-item-owned` | N | NurseryDialog | Owned Nursery plant card | 1048x643 | wide | Nursery + Economy |
| 078 | `nursery-item-locked` | N | NurseryDialog | 0 Coins/consumables; locked item disabled | 1048x643 | wide | Nursery + Economy |
| 079 | `nursery-purchase-success` | N | NurseryDialog | Real environment purchase and owned receipt state | 1048x643 | wide | Nursery + Economy |
| 080 | `nursery-final-row-above-footer` | N | NurseryDialog | Final Nursery row scrolled above fixed footer | 1048x643 | wide | Nursery + Economy |
| 081 | `missing-artwork-graphical-fallback` | N | NurseryDialog | All artwork resolvers forced missing; graphical fallbacks | 1048x643 | wide | Nursery + Economy |
| 082 | `settings-unsaved-changes` | SD | GardenSettingsDialog / GardenStudioWidget | Dirty Garden-name draft; Display scroll reset | 1048x643 | display | Settings + Diagnostics |
| 083 | `settings-validation-error` | SD | GardenSettingsDialog / GardenStudioWidget | Whitespace Garden name; inline validation error | 1048x643 | display | Settings + Diagnostics |
| 084 | `diagnostics-expanded` | SD | GardenSettingsDialog / GardenStudioWidget | Diagnostics details expanded | 1048x643 | troubleshooting-expanded | Settings + Diagnostics |
| 085 | `production-build-controls-absent` | SD | GardenSettingsDialog / GardenStudioWidget | Production capability branch; development controls absent | 1048x643 | troubleshooting | Settings + Diagnostics |
| 086 | `reviewer-find-common-reduced-motion` | R | AnkiQt / ReviewerRewardFeedback | Canonical Morning Dew Find joined with the active-day reward; Common treatment under reduced motion; focus preserved | Pending v19 manifest | reviewer | Reviewer + Rewards |
| 087 | `reviewer-find-environment` | R | AnkiQt / ReviewerRewardFeedback | Canonical Firefly Evening environment Find; exact collection entitlement and restrained Rare treatment | Pending v19 manifest | reviewer | Reviewer + Rewards |
| 088 | `reviewer-find-stacked-sync` | R | AnkiQt / ReviewerRewardFeedback | Canonical stacked synchronized Finds plus active-day and Perfect Canopy results in one focus-safe summary | Pending v19 manifest | reviewer | Reviewer + Rewards |
| 089 | `reduced-motion-enabled` | SD | GardenSettingsDialog / GardenStudioWidget | Reduced Motion checked and scrolled into view | 1048x643 | display | Settings + Diagnostics |
| 090 | `keyboard-focus-state` | G | GardenDashboard / GardenSceneWidget | Progress action focused by keyboard | 1140x630 | compact | Garden + Scene |
| 091 | `starter-placement` | FG | GardenDashboard / GardenSceneWidget | Persisted placement step; no starter created; unlocked beds highlighted | 1177x630 target | compact target | First run + Garden |
| 092 | `starter-completion` | FG | GardenDashboard / GardenSceneWidget | Persisted completion step after the starter is nurtured, before destination choice | 1177x630 target | compact target | First run + Garden |
| 093 | `home-preview-loading` | H | AnkiQt / Home HTML | Explicit loading preview on Deck Browser | 667x570 target | default target | Home |
| 094 | `home-preview-error` | H | AnkiQt / Home HTML | Recoverable preview error on Overview | 667x570 target | default target | Home |
| 095 | `home-preview-stale` | H | AnkiQt / Home HTML | Last valid scene retained with textual updating status | 667x570 target | default target | Home |
| 096 | `onboarding-persistence-error` | FG | GardenDashboard / GardenSceneWidget | Failed introduction-to-Nursery save rolls back and announces the error | 1177x630 target | compact target | First run + Garden |
| 097 | `move-persistence-error` | G | GardenDashboard / GardenSceneWidget | Failed move save restores slots, retains selection, and offers retry | 1177x630 target | compact target | Garden + Scene |
| 098 | `collection-known-not-collected-overview` | SO | GardenDialog (`SpeciesOverviewDialog`) | Dahlia is catalog-known with zero collected/planted instances; Seed through Flowering preview, Rare mystery | 960x496 | default; wide split | Progress + Collection |
| 099 | `purchase-confirmation-species` | PC | PurchaseConfirmationDialog | Ready species quote; one purchased instance will be added to Collection | 820x535 | wide | Nursery + Economy |
| 100 | `purchase-confirmation-growth-charge` | PC | PurchaseConfirmationDialog | Ready Growth Charge quote; one owned consumable will be added to inventory | 820x535 | wide | Nursery + Economy |
| 101 | `purchase-confirmation-environment` | PC | PurchaseConfirmationDialog | Ready Weather quote with exact mechanics and owned-not-equipped disposition | 820x535 | wide | Nursery + Collection |
| 102 | `purchase-confirmation-fertilizer-application` | PC | PurchaseConfirmationDialog | Ready Basic Fertilizer quote for a named target with no active tier | 820x535 | wide | Nursery + Economy |
| 103 | `purchase-confirmation-fertilizer-extension` | PC | PurchaseConfirmationDialog | Same-tier Fertilizer quote describes extension without discarding active time | 820x535 | wide | Nursery + Economy |
| 104 | `purchase-confirmation-garden-bed` | PC | PurchaseConfirmationDialog | Ready quote for the next sequential bed with exact cost and resulting balance | 820x535 | wide | Nursery + Garden Spaces |
| 105 | `purchase-confirmation-loading-disabled` | PC | PurchaseConfirmationDialog | Submission in flight; stable loading copy and disabled actions prevent re-entry | 820x535 | wide | Nursery + Economy |
| 106 | `purchase-error-insufficient-coins` | PC | PurchaseConfirmationDialog | Terminal insufficient-Garden-Coins state with deficit and earning route | 820x400 | wide | Nursery + Economy |
| 107 | `purchase-error-persistence-failure` | PC | PurchaseConfirmationDialog | Recoverable save failure; debit/grant rollback and original request retry | 820x535 | wide | Nursery + Economy |
| 108 | `purchase-error-item-unavailable` | PC | PurchaseConfirmationDialog | Terminal unavailable state without stale terms or purchase action | 820x400 | wide | Nursery + Economy |
| 109 | `purchase-error-already-owned` | PC | PurchaseConfirmationDialog | Terminal already-owned entitlement state | 820x400 | wide | Nursery + Economy |
| 110 | `purchase-error-invalid-target` | PC | PurchaseConfirmationDialog | Terminal invalid Fertilizer target state | 820x400 | wide | Nursery + Economy |
| 111 | `purchase-error-stale-price` | PC | PurchaseConfirmationDialog | Price changed; refreshed terms are shown but never silently committed | 820x535 | wide | Nursery + Economy |
| 112 | `purchase-error-stale-balance` | PC | PurchaseConfirmationDialog | Balance changed; refreshed terms are shown but never silently committed | 820x535 | wide | Nursery + Economy |
| 113 | `purchase-success-inventory-collection` | N | NurseryDialog | Species receipt names the purchase, spend, new balance, Collection disposition, and Plant in garden action | 1048x643 | wide | Nursery + Collection |
| 114 | `purchase-success-fertilizer-applied` | N | NurseryDialog | Fertilizer receipt names the target and applied disposition | 1048x643 | wide | Nursery + Economy |
| 115 | `purchase-success-garden-bed-unlocked` | N | NurseryDialog | Bed receipt and Garden Spaces view visibly identify the newly unlocked bed | 1048x643 | wide | Nursery + Garden Spaces |
| 116 | `nursery-empty-state` | N | NurseryDialog | Explicit all-species-collected empty state with footer clearance | 1048x643 | wide | Nursery + Economy |
| 117 | `collection-environment-mechanics` | P | GardenProgressDialog | Shared Weather/Scenery mechanics, ownership, textual Equipped state, and Collection-owned Manage loadout route | 1000x699 | wide | Progress + Collection |
| 118 | `collection-loadout-persistence-error` | C | CollectibleDetailDialog | Atomic loadout save failure restores the prior persisted draft | 1120x699 | wide | Collection + Environment |
| 119 | `collection-origin-plant-placement` | G | GardenDashboard / GardenSceneWidget | Collection-origin plant placement into an unlocked Garden slot | 1140x699 | compact | Collection + Garden |
| 120 | `growth-charge-use-ready` | GC | GrowthChargeConfirmationDialog | Owned Small Charge and valid planted target; complete current/projected/reward terms | 820x614 | default | Growth + Economy |
| 121 | `growth-charge-empty-inventory` | GC | GrowthChargeConfirmationDialog | Valid target, zero Charge inventory, and in-empty-state Open Nursery action | 820x614 | default | Growth + Nursery |
| 122 | `growth-charge-loading-disabled` | GC | GrowthChargeConfirmationDialog | Submission in flight with selector, Cancel, and Use paths disabled | 820x614 | default | Growth + Economy |
| 123 | `growth-charge-stale-inventory` | GC | GrowthChargeConfirmationDialog | Inventory changes after quote; refreshed terms and inline stale alert, no mutation | 820x614 | default | Growth + Economy |
| 124 | `growth-charge-invalid-target` | GC | GrowthChargeConfirmationDialog | Owned but unplanted target rejected with visible non-color status | 820x614 | default | Growth + Collection |
| 125 | `growth-charge-persistence-failure` | GC | GrowthChargeConfirmationDialog | Deterministic save failure restores Growth, inventory, rewards, feedback, ledger, and transitions | 820x614 | default | Growth + Economy |
| 126 | `growth-charge-success-stage-reward` | GC | GrowthChargeConfirmationDialog | Small Charge crosses Seed to Sprout, grants the canonical stage reward, and shows a non-reusable receipt | 820x614 | default | Growth + Rewards |

## Ownership and implementation boundary

“Owner” in the inventory is the downstream implementation role, not permission
to change shared files independently. `ankigarden/ui/dashboard.py` is the main
merge-conflict hotspot: First run, Garden, Progress, Collection loadout, Nursery,
Settings, Story, and Economy all touch classes in that module. Shared state and
transaction owners must freeze any new projection/purchase/action interfaces
before surface agents depend on them. Accessibility/responsive work coordinates
with each surface owner rather than owning the whole module.

The complete 146/146 v9 run closes its historical manifest gap but is stale
after later source and capture-contract changes. The validator-clean v10 run
supplies 149/149 evidence; the v11 run supplies 156/156 frozen-foundation
evidence. The v12 run supplies 157/157 pre-purchase-overhaul evidence, including
the known-not-collected species state. The v14 and v15 runs supply complete
181/181 and 183/183 predecessor-source evidence respectively. The complete v16
run supplies independently validator-clean 191/191 predecessor-source evidence.
The current v19 canonical-100% run and exact 17-sheet set are complete and
validator-clean, closing current-source automated capture completeness. No
local capture by itself closes the native-platform or human-accessibility gates
identified above.

Downstream implementation may start from this inventory. Resize, breakpoint,
150%, and 200% screenshot duplicates are not required. Responsive and scaling
geometry remain automated, while native-platform and human-accessibility
acceptance stay separate. For environment state,
Garden Progress Collection owns ownership/status/details and routes to its
loadout detail; that detail owns preview, equipment, and visibility mutations.
