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
records all 183 surfaces. Current source declares capture contract v16 with 191
ordered surfaces. It preserves IDs 001-183, changes ID 026 to the stale Overview
redirect proof, points progress resize IDs 111-115 at Plant Growth, and appends
the Growth Charge states 184-191. The final current-source run at
`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`
is independently validator-clean at 191/191, including the formerly missing
IDs 019 and 064-069.

The table below uses the stable capture ID order from `CAPTURE_FACE_GROUPS`.
Current v16 preserves IDs 001-183 and appends Charge confirmation states
184-191. IDs 158-181 remain the purchase confirmations, typed errors, receipts,
purchase responsiveness, Nursery empty state, and Collection environment
mechanics; IDs 182-183 remain Collection rollback and placement states.
Capture contract v9 source-faithfully renamed ID 076 from
`streak-reward-claimed-unclaimed` to `streak-reward-earned-next`; the numeric ID
did not change in v9. Viewports for IDs 001-183 are retained logical Qt client
sizes; IDs 184-191 use their realized v16 logical sizes. A
`declared -> actual` value means a screen, widget, or native-frame constraint
normalized the request. Responsive modes come from the v14 manifest rather
than from stale v9 fixed-edge labels. The formerly missing Home rows use the
same 667x570 Anki window as their adjacent Home fixtures.

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

Contract v16 requires all 191 surfaces. The requested v8 visual baseline remains
139/146 and incomplete; no later complete run replaces its visual authority.
The final run at
`build/ui-face-captures/capture-sequence-20260817-134654/20260817-140427`
has exact ordered 191/191 agreement, including 019, 064-069, and 184-191, with
zero capture failures or text/layout warnings. All 88 dialog-scroll audits, all
13 responsive-stability pairs, and the 12-cycle dialog-memory probe pass. The
24-page manifest-owned contact-sheet set at
`build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260817-134654`
and the exact manifest pass the independent repository validator. This closes
current-source automated manifest and contact-sheet completeness; partial runs
remain diagnostic evidence only.

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
  current v10 behavior. Current v10 keeps both top-level compact and retains
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
| FH | First-run Anki Home; Deck Browser/Overview render hooks and Home bridge | Schema-20 `GardenState` onboarding, plants, Garden name, daily metrics, Coins, selected environment, shared asset metadata; transient request ID rejects stale responses | Choose first plant, Open Garden, Retry | Loading, no-starter/empty, success, partial, error, disabled opening, stale response | `_capture_starter_deck_browser()` / `_capture_starter_overview()`; real Home HTML |
| FG | First-run Garden; `AnkiGardenApp.open_dashboard()` | Same `GardenState` plus `select_garden_ui()` and scene payload; persisted onboarding owns the resumable step | Choose first plant, open Nursery | No starter, no release-ready stock, planted-before-Nurture, normal, save error | `_capture_starter_garden()`; native Dashboard/Scene |
| FN | Starter Nursery; first-run direct Nursery route | Release-ready six-stage asset catalog plus onboarding/species/plants/slots; no mutation until confirmed Choose | Choose, page/filter, back | No stock, locked/missing art, disabled, confirmation, footer reachability, save error | `_capture_starter_nursery_after()`; real catalog in starter mode |
| FC | Starter confirmation; selected Nursery starter | Selected release-ready species is transient; confirmation persists the species choice, while placement atomically creates one specific plant instance in the chosen bed | Confirm Choose, cancel/back | Enabled/disabled, save error, compact/wide | `_capture_starter_confirmation()` or resize matrix |
| H | Normal/active Home; Deck Browser/Overview hooks | Authoritative Garden state, active periods/plant, slots, Growth/streak/Coins, environment visibility, asset metadata; coordinator revision invalidates cache | Open Garden, Retry | Planted not nurtured, active, six marker slots, loading, partial, error, stale response | Home fixture methods plus source-backed DOM identity check |
| G | Dashboard, Garden, popovers, Move, focus, scaling and responsive states; Open Garden/scene/header/landmarks | Garden state plants/slots/active periods/name/Coins/effects/scene geometry; Move/selection/hover/focus/viewport are transient | Select, Nurture, Fertilize, Move, Move to Collection, Plant in garden, Story, Progress, Customize, Settings, Undo | Empty/loading/error, no selection, locked/disabled, success toast, save failure, long/dynamic values, all stages/plots, focus, narrow/high-DPI | Named `_capture_*` fixture or `_capture_resize_matrix_face()`; native Scene |
| F | Fertilizer dialog; selected plant -> Fertilize | Current effect from `fertilizer_status()`, new effect/target/price/balance/disposition from `PurchaseQuote`, and completed-request replay ledger | Purchase & Apply, Extend, Purchase & Replace, Keep current | Unaffordable, active, expiring/stale countdown, invalid target, persistence error, success receipt, responsive | `_capture_fertilize_after()`, expiring fixture, purchase fixtures, resize matrix |
| FR | Fertilizer replacement confirmation | Current name/effect/seconds remaining from `fertilizer_status()`; new name/effect/full duration, price, target, and replacement requirement from the engine quote | Keep current, Purchase & Replace | Exact discarded time, current/new cards, disabled/stale target, save error, compact/wide | `_capture_fertilizer_replacement_confirmation()`, v14 confirmation, or resize matrix |
| ST | Plant Story; selected plant -> Story | Plant identity/species/stage/Growth/memories/discovery and asset metadata; rename persists atomically | Rename/save, close, Choose another when eligible | No/one/many memories, locked Rare, missing art, success/error, responsive | `_capture_story_after()` or resize matrix |
| P | Plant Growth/Streak/Coins, Progress, Achievements and Collection; metric/header/cottage routes | Canonical study sources, per-plant nurtured/passive/direct allocations, residual fifths, streak, currency ledger, achievements/reward history, plants/species discovery, and environment ownership/status | Navigate, disclose Growth breakdown, target a Charge, filter, inspect species/effects, manage loadout, close | Zero/new/nonzero/fractional/active, empty/filter-empty, stale migration, locked, completed, at-risk/missed, earned/next, loading/error/disabled, responsive | Growth fixture, `_capture_metric()`, `_capture_progress_page()`, collection fixtures, resize matrix |
| SO | Species overview; any known catalog species | Catalog identity plus owned instances, highest reached stage/discovery, shared thumbnail metadata, and per-species Rare unlock | Inspect/close | Collected, known-not-collected, zero instances, locked Rare, missing art, responsive | `_build_species_overview_dialog()` plus capture/resize/known-not-collected fixture |
| C | Collection loadout detail and preview | One local draft over persisted inventory, selected Weather/Scenery and visual-only visibility flags; `apply_garden_loadout()` is the atomic commit | Choose owned effects, toggle artwork, apply, cancel preview | Clean/dirty, on/off, unowned/locked, success/error/rollback, responsive | Collection loadout/detail fixtures or resize matrix; native preview |
| N | Nursery commerce; Nursery landmark/first-run/related routes | Catalogs and engine projections over schema-20 state, shared effect descriptors, normalized artwork, purchase quotes, Coins/ledgers, ownership/inventory, slots, and release-ready assets | Choose, Purchase, Use, Unlock bed, Plant in garden, Move, Move to Collection, open Collection, browse | Owned/equipped/locked/disabled, ready/loading/typed error/success, empty/no stock, missing-art fallback, footer reachability, responsive | Nursery tab/stress/purchase fixtures or resize matrix |
| GC | Growth Charge confirmation; selected plant or Plant Growth row | Frozen quote/request/outcome contracts over target eligibility, Growth, selected Scenery reward terms, Charge inventory, and bounded completed-request ledger | Select Charge type, Use Growth Charge, Cancel, Open Nursery, Close receipt | Ready, empty, loading/disabled, stale inventory, invalid target, persistence rollback, rewarded success, minimum responsive | `_capture_growth_charge_dialog_fixture()`; native target-specific modal |
| SD | Settings and Diagnostics; Anki menu or Dashboard Settings | Staged Anki config plus separately persisted Garden name; runtime diagnostics/build capabilities/telemetry are derived | Save changes, cancel, restore defaults, toggle, expand/refresh/copy diagnostics | Clean/warning, dirty, invalid, rollback/error, production controls absent, reduced motion, responsive | Settings fixture methods or resize matrix; both scroll positions reset |

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
v16 run records all 191 surfaces on the primary display at DPR 3.0 under the
same requested scale. This is useful display provenance, but it is not native
mixed-DPI acceptance because the suite did not deliberately exercise cross-
display transitions.
There is no current native standard-scale, true OS 200-percent, or Windows
acceptance run. Capture 090 remains a logical Qt proxy, not true OS 200-percent
evidence. Responsive mode is transient capture metadata and is never persisted.

## Ordered surface inventory

| ID | Capture state | Profile | Component / renderer | Fixture data and preparation | Viewport (logical px) | Responsive mode | Owning agent |
|---:|---|:---:|---|---|---:|---|---|
| 001 | `starter-deck-browser-home` | FH | AnkiQt / Home HTML | Untouched schema-20 starter state on Deck Browser | 667x570 | default | Home + First run |
| 002 | `starter-overview-home` | FH | AnkiQt / Home HTML | Untouched schema-20 starter state on Overview | 667x570 | default | Home + First run |
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
| 037 | `settings-menu-display` | SD | GardenSettingsDialog / GardenStudioWidget | Settings opened through registered Anki menu action | 1048x643 | display | Settings + Diagnostics |
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
| 073 | `clear-recall-separate-conditions` | P | GardenProgressDialog | 83% accuracy and 12/20 answers shown separately | 1140x630 | wide | Progress + Collection |
| 074 | `streak-at-risk` | P | GardenProgressDialog | 7-day streak; no review today; last active yesterday | 1140x630 | wide | Progress + Collection |
| 075 | `streak-missed-day` | P | GardenProgressDialog | Ended streak: current 0, previous 3 days | 1140x630 | wide | Progress + Collection |
| 076 | `streak-reward-earned-next` | P | GardenProgressDialog | 14-day streak; 7/14 earned automatically; 30 next | 1140x630 | wide | Progress + Collection |
| 077 | `nursery-item-owned` | N | NurseryDialog | Owned Nursery plant card | 1048x643 | wide | Nursery + Economy |
| 078 | `nursery-item-locked` | N | NurseryDialog | 0 Coins/consumables; locked item disabled | 1048x643 | wide | Nursery + Economy |
| 079 | `nursery-purchase-success` | N | NurseryDialog | Real environment purchase and owned receipt state | 1048x643 | wide | Nursery + Economy |
| 080 | `nursery-final-row-above-footer` | N | NurseryDialog | Final Nursery row scrolled above fixed footer | 1048x643 | wide | Nursery + Economy |
| 081 | `missing-artwork-graphical-fallback` | N | NurseryDialog | All artwork resolvers forced missing; graphical fallbacks | 1048x643 | wide | Nursery + Economy |
| 082 | `settings-unsaved-changes` | SD | GardenSettingsDialog / GardenStudioWidget | Dirty Garden-name draft; Display scroll reset | 1048x643 | display | Settings + Diagnostics |
| 083 | `settings-validation-error` | SD | GardenSettingsDialog / GardenStudioWidget | Whitespace Garden name; inline validation error | 1048x643 | display | Settings + Diagnostics |
| 084 | `diagnostics-expanded` | SD | GardenSettingsDialog / GardenStudioWidget | Diagnostics details expanded | 1048x643 | troubleshooting-expanded | Settings + Diagnostics |
| 085 | `production-build-controls-absent` | SD | GardenSettingsDialog / GardenStudioWidget | Production capability branch; dev controls absent | 1048x643 | troubleshooting | Settings + Diagnostics |
| 086 | `reduced-motion-enabled` | SD | GardenSettingsDialog / GardenStudioWidget | Reduced Motion checked and scrolled into view | 1048x643 | display | Settings + Diagnostics |
| 087 | `keyboard-focus-state` | G | GardenDashboard / GardenSceneWidget | Progress action focused by keyboard | 1140x630 | compact | Garden + Scene |
| 088 | `narrow-window-responsive` | G | GardenDashboard / GardenSceneWidget | Dashboard resized to 760x620 | 760x620 | compact; metrics compact | Garden + Scene |
| 089 | `display-scaling-150` | G | GardenDashboard / GardenSceneWidget | Process `QT_SCALE_FACTOR=1.5` | 1140x630 | compact; metrics wide | Garden + Scene |
| 090 | `display-scaling-200-qt-representative` | G | GardenDashboard / GardenSceneWidget | 620x520 logical proxy; OS scale unchanged | 620x520 | narrow; metrics compact | Garden + Scene |
| 091 | `resize-dashboard-minimum` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-minimum` | 620x520 | narrow; metrics compact | Garden + Scene |
| 092 | `resize-dashboard-content-699` | G | GardenDashboard / GardenSceneWidget | Historical 699 px edge retained as a stability probe | 723x700 -> 723x699 | compact; metrics compact | Garden + Scene |
| 093 | `resize-dashboard-content-701` | G | GardenDashboard / GardenSceneWidget | Historical 701 px edge retained as a stability probe | 725x700 -> 725x699 | compact; metrics compact | Garden + Scene |
| 094 | `resize-dashboard-content-819` | G | GardenDashboard / GardenSceneWidget | Historical 819 px edge retained as a stability probe | 843x720 -> 843x699 | compact; metrics compact | Garden + Scene |
| 095 | `resize-dashboard-content-821` | G | GardenDashboard / GardenSceneWidget | Historical 821 px edge retained as a stability probe | 845x720 -> 845x699 | compact; metrics compact | Garden + Scene |
| 096 | `resize-dashboard-content-899` | G | GardenDashboard / GardenSceneWidget | Historical 899 px edge retained as a stability probe | 923x740 -> 923x699 | compact; metrics compact | Garden + Scene |
| 097 | `resize-dashboard-content-901` | G | GardenDashboard / GardenSceneWidget | Historical 901 px edge retained as a stability probe | 925x740 -> 925x699 | compact; metrics compact | Garden + Scene |
| 098 | `resize-dashboard-content-999` | G | GardenDashboard / GardenSceneWidget | Historical 999 px edge retained as a stability probe | 1023x760 -> 1023x699 | compact; metrics wide | Garden + Scene |
| 099 | `resize-dashboard-content-1001` | G | GardenDashboard / GardenSceneWidget | Historical 1001 px edge retained as a stability probe | 1025x760 -> 1025x699 | compact; metrics wide | Garden + Scene |
| 100 | `resize-dashboard-content-1359` | G | GardenDashboard / GardenSceneWidget | Historical 1359 px edge retained as a stability probe | 1383x900 -> 1383x699 | compact; metrics wide | Garden + Scene |
| 101 | `resize-dashboard-content-1361` | G | GardenDashboard / GardenSceneWidget | Historical 1361 px edge retained as a stability probe | 1385x900 -> 1385x699 | compact; metrics wide | Garden + Scene |
| 102 | `resize-dashboard-default` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-default` | 1240x840 -> 1240x699 | compact; metrics wide | Garden + Scene |
| 103 | `resize-dashboard-large` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-large` | 1440x960 -> 1440x699 | compact; metrics wide | Garden + Scene |
| 104 | `resize-settings-minimum` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-minimum` | 560x420 -> 640x460 | display | Settings + Diagnostics |
| 105 | `resize-settings-content-699` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-699` | 747x620 | display | Settings + Diagnostics |
| 106 | `resize-settings-content-701` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-701` | 749x620 | display | Settings + Diagnostics |
| 107 | `resize-settings-content-759` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-759` | 807x650 | display | Settings + Diagnostics |
| 108 | `resize-settings-content-761` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-761` | 809x650 | display | Settings + Diagnostics |
| 109 | `resize-settings-default` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-default` | 980x680 | display | Settings + Diagnostics |
| 110 | `resize-settings-large` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-large` | 1000x820 -> 1000x699 | display | Settings + Diagnostics |
| 111 | `resize-progress-minimum` | P | GardenProgressDialog | Plant Growth page; declared transition `default-to-minimum` | 720x500 | compact | Progress + Growth |
| 112 | `resize-progress-content-819` | P | GardenProgressDialog | Plant Growth historical low-edge stability probe | 867x620 | wide | Progress + Growth |
| 113 | `resize-progress-content-821` | P | GardenProgressDialog | Plant Growth historical high-edge stability probe | 869x620 | wide | Progress + Growth |
| 114 | `resize-progress-default` | P | GardenProgressDialog | Plant Growth transition `minimum-to-default` | 940x680 | wide | Progress + Growth |
| 115 | `resize-progress-large` | P | GardenProgressDialog | Plant Growth transition `default-to-large` | 1000x820 -> 1000x699 | wide | Progress + Growth |
| 116 | `resize-collectible-detail-minimum` | C | CollectibleDetailDialog | Collection loadout detail at declared minimum | 680x480 | compact | Collection + Environment |
| 117 | `resize-collectible-detail-content-819` | C | CollectibleDetailDialog | Loadout detail historical low-edge stability probe | 867x620 | compact | Collection + Environment |
| 118 | `resize-collectible-detail-content-821` | C | CollectibleDetailDialog | Loadout detail historical high-edge stability probe | 869x620 | compact | Collection + Environment |
| 119 | `resize-collectible-detail-default` | C | CollectibleDetailDialog | Loadout detail transition `minimum-to-default` | 1040x700 -> 1040x699 | wide | Collection + Environment |
| 120 | `resize-collectible-detail-large` | C | CollectibleDetailDialog | Loadout detail transition `default-to-large` | 1120x860 -> 1120x699 | wide | Collection + Environment |
| 121 | `resize-nursery-minimum` | N | NurseryDialog | Declared resize-matrix transition `nursery-minimum` | 640x460 | compact | Nursery + Economy |
| 122 | `resize-nursery-content-759` | N | NurseryDialog | Declared resize-matrix transition `nursery-content-759` | 795x600 | wide | Nursery + Economy |
| 123 | `resize-nursery-content-761` | N | NurseryDialog | Declared resize-matrix transition `nursery-content-761` | 797x600 | wide | Nursery + Economy |
| 124 | `resize-nursery-default` | N | NurseryDialog | Declared resize-matrix transition `nursery-default` | 840x640 | wide | Nursery + Economy |
| 125 | `resize-nursery-large` | N | NurseryDialog | Declared resize-matrix transition `nursery-large` | 1050x800 -> 1051x699 | wide | Nursery + Economy |
| 126 | `resize-story-minimum` | ST | PlantStoryDialog | Declared resize-matrix transition `story-minimum` | 480x400 | compact | Story + Collection |
| 127 | `resize-story-content-539` | ST | PlantStoryDialog | Declared resize-matrix transition `story-content-539` | 587x500 | wide | Story + Collection |
| 128 | `resize-story-content-541` | ST | PlantStoryDialog | Declared resize-matrix transition `story-content-541` | 589x500 | wide | Story + Collection |
| 129 | `resize-story-default` | ST | PlantStoryDialog | Declared resize-matrix transition `story-default` | 640x520 | wide | Story + Collection |
| 130 | `resize-story-large` | ST | PlantStoryDialog | Declared resize-matrix transition `story-large` | 900x800 -> 900x699 | wide | Story + Collection |
| 131 | `resize-starter-confirmation-minimum` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-minimum` | 360x280 | compact | First run |
| 132 | `resize-starter-confirmation-content-399` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-content-399` | 447x280 | wide | First run |
| 133 | `resize-starter-confirmation-content-401` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-content-401` | 449x280 | wide | First run |
| 134 | `resize-starter-confirmation-default` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-default` | 480x300 | wide | First run |
| 135 | `resize-starter-confirmation-large` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-large` | 520x360 | wide | First run |
| 136 | `resize-fertilizer-minimum` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-minimum` | 520x460 | default | Economy |
| 137 | `resize-fertilizer-default` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-default` | 600x580 | default | Economy |
| 138 | `resize-fertilizer-large` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-large` | 900x800 -> 900x676 | default | Economy |
| 139 | `resize-fertilizer-replacement-minimum` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-minimum` | 420x400 | compact | Economy |
| 140 | `resize-fertilizer-replacement-content-399` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-content-399` | 443x420 -> 443x400 | compact | Economy |
| 141 | `resize-fertilizer-replacement-content-401` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-content-401` | 445x420 -> 445x400 | compact | Economy |
| 142 | `resize-fertilizer-replacement-default` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-default` | 480x420 -> 480x400 | compact | Economy |
| 143 | `resize-fertilizer-replacement-large` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-large` | 820x660 -> 820x360 | wide | Economy |
| 144 | `resize-species-overview-minimum` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-minimum` | 500x420 -> 500x400 | default | Progress + Collection |
| 145 | `resize-species-overview-default` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-default` | 560x500 -> 560x400 | default | Progress + Collection |
| 146 | `resize-species-overview-large` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-large` | 900x800 -> 900x400 | default | Progress + Collection |
| 147 | `resize-collection-minimum` | P | GardenProgressDialog | Collection page; declared transition `default-to-minimum` | 720x500 | compact | Progress + Collection |
| 148 | `resize-collection-default` | P | GardenProgressDialog | Collection page; declared transition `minimum-to-default` | 940x680 | wide | Progress + Collection |
| 149 | `resize-collection-large` | P | GardenProgressDialog | Collection page; declared transition `default-to-large` | 1000x820 -> 1000x699 | wide | Progress + Collection |
| 150 | `starter-placement` | FG | GardenDashboard / GardenSceneWidget | Persisted placement step; no starter created; unlocked beds highlighted | 1177x630 target | compact target | First run + Garden |
| 151 | `starter-completion` | FG | GardenDashboard / GardenSceneWidget | Persisted completion step after the starter is nurtured, before destination choice | 1177x630 target | compact target | First run + Garden |
| 152 | `home-preview-loading` | H | AnkiQt / Home HTML | Explicit loading preview on Deck Browser | 667x570 target | default target | Home |
| 153 | `home-preview-error` | H | AnkiQt / Home HTML | Recoverable preview error on Overview | 667x570 target | default target | Home |
| 154 | `home-preview-stale` | H | AnkiQt / Home HTML | Last valid scene retained with textual updating status | 667x570 target | default target | Home |
| 155 | `onboarding-persistence-error` | FG | GardenDashboard / GardenSceneWidget | Failed introduction-to-Nursery save rolls back and announces the error | 1177x630 target | compact target | First run + Garden |
| 156 | `move-persistence-error` | G | GardenDashboard / GardenSceneWidget | Failed move save restores slots, retains selection, and offers retry | 1177x630 target | compact target | Garden + Scene |
| 157 | `collection-known-not-collected-overview` | SO | GardenDialog (`SpeciesOverviewDialog`) | Dahlia is catalog-known with zero collected/planted instances; Seed through Flowering preview, Rare mystery | 960x496 | default; wide split | Progress + Collection |
| 158 | `purchase-confirmation-species` | PC | PurchaseConfirmationDialog | Ready species quote; one purchased instance will be added to Collection | 820x535 | wide | Nursery + Economy |
| 159 | `purchase-confirmation-growth-charge` | PC | PurchaseConfirmationDialog | Ready Growth Charge quote; one owned consumable will be added to inventory | 820x535 | wide | Nursery + Economy |
| 160 | `purchase-confirmation-environment` | PC | PurchaseConfirmationDialog | Ready Weather quote with exact mechanics and owned-not-equipped disposition | 820x535 | wide | Nursery + Collection + Customize |
| 161 | `purchase-confirmation-fertilizer-application` | PC | PurchaseConfirmationDialog | Ready Basic Fertilizer quote for a named target with no active tier | 820x535 | wide | Nursery + Economy |
| 162 | `purchase-confirmation-fertilizer-extension` | PC | PurchaseConfirmationDialog | Same-tier Fertilizer quote describes extension without discarding active time | 820x535 | wide | Nursery + Economy |
| 163 | `purchase-confirmation-garden-bed` | PC | PurchaseConfirmationDialog | Ready quote for the next sequential bed with exact cost and resulting balance | 820x535 | wide | Nursery + Garden Spaces |
| 164 | `purchase-confirmation-loading-disabled` | PC | PurchaseConfirmationDialog | Submission in flight; stable loading copy and disabled actions prevent re-entry | 820x535 | wide | Nursery + Economy |
| 165 | `purchase-error-insufficient-coins` | PC | PurchaseConfirmationDialog | Terminal insufficient-Garden-Coins state with deficit and earning route | 820x400 | wide | Nursery + Economy |
| 166 | `purchase-error-persistence-failure` | PC | PurchaseConfirmationDialog | Recoverable save failure; debit/grant rollback and original request retry | 820x535 | wide | Nursery + Economy |
| 167 | `purchase-error-item-unavailable` | PC | PurchaseConfirmationDialog | Terminal unavailable state without stale terms or purchase action | 820x400 | wide | Nursery + Economy |
| 168 | `purchase-error-already-owned` | PC | PurchaseConfirmationDialog | Terminal already-owned entitlement state | 820x400 | wide | Nursery + Economy |
| 169 | `purchase-error-invalid-target` | PC | PurchaseConfirmationDialog | Terminal invalid Fertilizer target state | 820x400 | wide | Nursery + Economy |
| 170 | `purchase-error-stale-price` | PC | PurchaseConfirmationDialog | Price changed; refreshed terms are shown but never silently committed | 820x535 | wide | Nursery + Economy |
| 171 | `purchase-error-stale-balance` | PC | PurchaseConfirmationDialog | Balance changed; refreshed terms are shown but never silently committed | 820x535 | wide | Nursery + Economy |
| 172 | `purchase-success-inventory-collection` | N | NurseryDialog | Species receipt names the purchase, spend, new balance, Collection disposition, and Plant in garden action | 1048x643 | wide | Nursery + Collection |
| 173 | `purchase-success-fertilizer-applied` | N | NurseryDialog | Fertilizer receipt names the target and applied disposition | 1048x643 | wide | Nursery + Economy |
| 174 | `purchase-success-garden-bed-unlocked` | N | NurseryDialog | Bed receipt and Garden Spaces view visibly identify the newly unlocked bed | 1048x643 | wide | Nursery + Garden Spaces |
| 175 | `purchase-confirmation-minimum` | FR | FertilizerReplacementDialog | Replacement comparison at declared minimum | 420x400 | compact | Nursery + Economy |
| 176 | `purchase-confirmation-breakpoint-low` | FR | FertilizerReplacementDialog | Measured comparison threshold minus one logical pixel | 517x520 | compact | Nursery + Economy |
| 177 | `purchase-confirmation-breakpoint-high` | FR | FertilizerReplacementDialog | Measured comparison threshold plus one logical pixel | 519x520 | wide | Nursery + Economy |
| 178 | `purchase-confirmation-default` | FR | FertilizerReplacementDialog | Minimum-to-default comparison transition | 720x553 | wide | Nursery + Economy |
| 179 | `purchase-confirmation-large` | FR | FertilizerReplacementDialog | Default-to-large comparison transition | 820x553 | wide | Nursery + Economy |
| 180 | `nursery-empty-state` | N | NurseryDialog | Explicit all-species-collected empty state with footer clearance | 1048x643 | wide | Nursery + Economy |
| 181 | `collection-environment-mechanics` | P | GardenProgressDialog | Shared Weather/Scenery mechanics, ownership, textual Equipped state, and Customize route | 1000x699 | wide | Progress + Collection + Customize |
| 182 | `collection-loadout-persistence-error` | C | CollectibleDetailDialog | Atomic loadout save failure restores the prior persisted draft | 1120x699 | wide | Collection + Environment |
| 183 | `collection-origin-plant-placement` | G | GardenDashboard / GardenSceneWidget | Collection-origin plant placement into an unlocked Garden slot | 1140x699 | compact | Collection + Garden |
| 184 | `growth-charge-use-ready` | GC | GrowthChargeConfirmationDialog | Owned Small Charge and valid planted target; complete current/projected/reward terms | 820x614 | default | Growth + Economy |
| 185 | `growth-charge-empty-inventory` | GC | GrowthChargeConfirmationDialog | Valid target, zero Charge inventory, and in-empty-state Open Nursery action | 820x614 | default | Growth + Nursery |
| 186 | `growth-charge-loading-disabled` | GC | GrowthChargeConfirmationDialog | Submission in flight with selector, Cancel, and Use paths disabled | 820x614 | default | Growth + Economy |
| 187 | `growth-charge-stale-inventory` | GC | GrowthChargeConfirmationDialog | Inventory changes after quote; refreshed terms and inline stale alert, no mutation | 820x614 | default | Growth + Economy |
| 188 | `growth-charge-invalid-target` | GC | GrowthChargeConfirmationDialog | Owned but unplanted target rejected with visible non-color status | 820x614 | default | Growth + Collection |
| 189 | `growth-charge-persistence-failure` | GC | GrowthChargeConfirmationDialog | Deterministic save failure restores Growth, inventory, rewards, feedback, ledger, and transitions | 820x614 | default | Growth + Economy |
| 190 | `growth-charge-success-stage-reward` | GC | GrowthChargeConfirmationDialog | Small Charge crosses Seed to Sprout, grants one 5-Coin reward, and shows non-reusable receipt | 820x614 | default | Growth + Rewards |
| 191 | `growth-charge-minimum-responsive` | GC | GrowthChargeConfirmationDialog | Ready terms at exact minimum with one reachable body scroll and clear footer | 420x400 | default | Growth + Accessibility |

## Ownership and implementation boundary

“Owner” in the inventory is the downstream implementation role, not permission
to change shared files independently. `ankigarden/ui/dashboard.py` is the main
merge-conflict hotspot: First run, Garden, Progress, Customize, Nursery,
Settings, Story, and Economy all touch classes in that module. Shared state and
transaction owners must freeze any new projection/purchase/action interfaces
before surface agents depend on them. Accessibility/responsive work coordinates
with each surface owner rather than owning the whole module.

The complete 146/146 v9 run closes its historical manifest gap but is stale
after later source and capture-contract changes. The validator-clean v10 run
supplies 149/149 evidence; the v11 run supplies 156/156 frozen-foundation
evidence. The v12 run supplies 157/157 pre-purchase-overhaul evidence, including
the known-not-collected species state. The v14 and v15 runs supply complete
181/181 and 183/183 predecessor-source evidence respectively. The final v16 run
supplies independently validator-clean 191/191 current-source evidence. No
local capture by itself closes the native-platform, uncaptured variant, or
human-accessibility gates identified above.

Downstream implementation may start from this inventory. Native Windows, true
OS 100/150/200-percent scaling, and high/mixed-DPI evidence are required before
release acceptance, not before implementation begins. For environment state,
Progress Collection owns read-only ownership/status/details and may route to
Customize; Customize is the sole owner of Equip and visibility mutations.
