# Anki Garden UI surface inventory

Status: Release 2.1.0 foundation inventory. The authoritative reference input is
`build/ui-face-captures/capture-sequence-20260815-170054/20260815-170057`, read
together with its manifest, metadata, logs, fixture source, and contact sheets.
That v8 run contains 139 of 146 required PNGs and `complete: false`. Capture
contract v9 reconciled it in
`build/ui-face-captures/capture-sequence-20260815-220049/20260815-220051` with
146 of 146 PNGs and `complete: true`. This closes the manifest-owned macOS Qt
capture set; it is not full product, platform, or human visual acceptance.

The table below uses the stable capture ID order from `CAPTURE_FACE_GROUPS`.
Capture contract v9 source-faithfully renames ID 076 from
`streak-reward-claimed-unclaimed` to `streak-reward-earned-next`; the numeric ID
and total count do not change. Viewports are logical Qt client sizes from the
reconciled v9 manifest. A `declared -> actual` value means the screen or widget
constraint normalized the request. The formerly missing Home rows use the same
667x570 Anki window as their adjacent Home fixtures.

## Capture reconciliation and visual-audit status

The seven missing files are exactly the suspected IDs:

| ID | Required state | Why it is absent |
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
- 039 still presents partial Advanced-tab context at a scroll boundary: the
  helper tail is visible while its Garden-name block is above the viewport.
- 066 still ellipsizes the Home detail line at the fixed Home width.
- 111 clips the final “s” in Achievements at the minimum Progress width. This is
  a real downstream layout risk, not fixed by the foundation harness.
- 090 is byte-identical to 091 because it is only a 620x520 logical proxy. Its
  manifest explicitly says the OS display scale did not change.
- In v8, 100-103 normalized to the same 1140x699 window and were byte-identical.
  The v9 run preserves their requested widths: 100 is 1383x699 in compact mode
  and 101 is 1385x699 in wide mode, so the breakpoint pair is distinct. The
  available screen still caps several requested resize heights at 699 pixels.

The v8 and v9 values of zero text-layout warnings are automated threshold
results. They cover visible native label/button glyph boxes, selected ancestor boundaries,
and a coarse branded-pixel Home gate. It does not evaluate WebEngine copy,
fixture correctness, scroll-hidden controls, sticky-header overlap, contrast,
visual hierarchy, duplicate frames, native Windows behavior, or true OS-level
standard/200-percent scaling.

## Profile expansion

Every inventory row names a profile. The profile supplies the requested
user-facing surface, entry point, persistence dependencies, primary actions,
and empty/loading/locked/success/error variants for that row; the row then adds
its exact fixture, component, viewport, mode, and owner.

| Profile | User-facing surface and entry point | Persistence and source of truth | Primary actions | Required variants, including uncaptured gaps | Fixture implementation |
|---|---|---|---|---|---|
| FH | First-run Anki Home; Deck Browser/Overview render hooks and Home bridge | Schema-16 `GardenState` onboarding, plants, Garden name, daily metrics, Coins, selected environment, shared asset metadata; transient request ID rejects stale responses | Choose first plant, Open Garden, Retry | Loading, no-starter/empty, success, partial, error, disabled opening, stale response | `_capture_starter_deck_browser()` / `_capture_starter_overview()`; real Home HTML |
| FG | First-run Garden; `AnkiGardenApp.open_dashboard()` | Same `GardenState` plus `select_garden_ui()` and scene payload; onboarding step is transient config/UI projection | Choose first plant, open Nursery | No starter, no release-ready stock, planted-before-Nurture, normal, save error | `_capture_starter_garden()`; native Dashboard/Scene |
| FN | Starter Nursery; first-run direct Nursery route | Release-ready six-stage asset catalog plus onboarding/species/plants/slots; no mutation until confirmed Choose | Choose, page/filter, back | No stock, locked/missing art, disabled, confirmation, footer reachability, save error | `_capture_starter_nursery_after()`; real catalog in starter mode |
| FC | Starter confirmation; selected Nursery starter | Selected release-ready species is transient; confirmed `choose_starter()` atomically persists one plant and completion | Confirm Choose, cancel/back | Enabled/disabled, save error, compact/wide | `_capture_starter_confirmation()` or resize matrix |
| H | Normal/active Home; Deck Browser/Overview hooks | Authoritative Garden state, active periods/plant, slots, Growth/streak/Coins, environment visibility, asset metadata; coordinator revision invalidates cache | Open Garden, Retry | Planted not nurtured, active, six marker slots, loading, partial, error, stale response | Home fixture methods plus source-backed DOM identity check |
| G | Dashboard, Garden, popovers, Move, focus, scaling and responsive states; Open Garden/scene/header/landmarks | Garden state plants/slots/active periods/name/Coins/effects/scene geometry; Move/selection/hover/focus/viewport are transient | Select, Nurture, Fertilize, Move, Store, Plant, Story, Progress, Customize, Settings, Undo | Empty/loading/error, no selection, locked/disabled, success toast, save failure, long/dynamic values, all stages/plots, focus, narrow/high-DPI | Named `_capture_*` fixture or `_capture_resize_matrix_face()`; native Scene |
| F | Fertilizer dialog; selected plant -> Fertilize | Target plant, nurtured/fully-grown capability, balance/ledger and fertilizer interval/history; engine transaction is authoritative | Purchase/Fertilize, Extend, Replace, cancel | Unaffordable disabled, affordable, active, expiring/stale countdown, success/error, responsive | `_capture_fertilize_after()`, expiring fixture, resize matrix |
| FR | Fertilizer replacement confirmation | Same fertilizer transaction state; discarded remaining time is transient confirmation data | Replace, cancel | Current/new tier, remaining time, disabled/stale target, save error, compact/wide | `_capture_fertilizer_replacement_confirmation()` or resize matrix |
| ST | Plant Story; selected plant -> Story | Plant identity/species/stage/Growth/memories/discovery and asset metadata; rename persists atomically | Rename/save, close, Choose another when eligible | No/one/many memories, locked Rare, missing art, success/error, responsive | `_capture_story_after()` or resize matrix |
| P | Growth/Streak/Coins, Progress, Achievements and Collection; metric/header/cottage routes | Daily source counters, totals, streak, currency ledger, achievements/reward history, plants/species discovery, environment inventory/equipment | Navigate, filter, inspect species, equip/toggle visibility where exposed, close | Zero/new/nonzero/active, empty/filter-empty, locked, completed, at-risk/missed, earned/next, loading/error/disabled, responsive | `_capture_metric()`, `_capture_progress_page()`, collection fixtures, resize matrix |
| SO | Species overview; discovered Collection species | Owned plant instances, highest stage/discovery, memories and asset metadata | Inspect/close | Missing/removed instance, locked Rare, missing art, responsive | `_build_species_overview_dialog()` plus capture/resize fixture |
| C | Customize Garden; Dashboard header | One local draft over persisted inventory, selected Weather/Scenery and visual-only visibility flags; `apply_environment_loadout()` is the commit | Choose owned effects, toggle artwork, Save changes, cancel | Clean/dirty, on/off, unowned/locked, success/error, responsive | Customize fixtures or resize matrix; native GardenStudio/Scene preview |
| N | Nursery commerce; Nursery landmark/first-run/related routes | Catalog, Coins/ledger, owned species/instances, consumables, slots, environment inventory and release-ready assets | Choose, Purchase/Buy, Unlock, Use, Plant, browse | Owned, locked/disabled, success/error, empty/no stock, missing-art fallback, footer reachability, responsive | Nursery tab/stress fixtures or resize matrix |
| SD | Settings and Diagnostics; Anki menu or Dashboard Settings | Staged Anki config plus separately persisted Garden name; runtime diagnostics/build capabilities/telemetry are derived | Save changes, cancel, restore defaults, toggle, expand/refresh/copy diagnostics | Clean/warning, dirty, invalid, rollback/error, production controls absent, reduced motion, responsive | Settings fixture methods or resize matrix; both scroll positions reset |

All product mutations in these profiles must remain engine-authoritative,
rollback-safe, and atomically saved. Capture-only viewport, route, hover, focus,
filter, and draft state must never enter `garden_state.json`. Fixed purchases and
review/reward events already use stable event keys; repeatable purchase retry
idempotency remains a downstream contract gap documented in
`docs/ui-release-overhaul-contract.md`.

## Display and viewport interpretation

The reference v8 set used the primary macOS display. The final v9 set records a
mixed-display run: six first-run captures used the secondary display at DPR
1.5 and 140 captures used the primary display at DPR 3.0, all under the same
requested `QT_SCALE_FACTOR=1.5` process configuration. This is useful
multi-display provenance, but it is not native mixed-DPI acceptance because
the suite did not deliberately exercise cross-display transitions. There is no
current native standard-scale, true OS 200-percent, or Windows acceptance run.
Capture 090 remains a logical Qt proxy, not true OS 200-percent evidence.
Responsive mode is transient capture metadata and is never persisted.

## Ordered surface inventory

| ID | Capture state | Profile | Component / renderer | Fixture data and preparation | Viewport (logical px) | Responsive mode | Owning agent |
|---:|---|:---:|---|---|---:|---|---|
| 001 | `starter-deck-browser-home` | FH | AnkiQt / Home HTML | Untouched schema-16 starter state on Deck Browser | 667x570 | default | Home + First run |
| 002 | `starter-overview-home` | FH | AnkiQt / Home HTML | Untouched schema-16 starter state on Overview | 667x570 | default | Home + First run |
| 003 | `starter-garden-onboarding` | FG | GardenDashboard / GardenSceneWidget | Untouched state; onboarding step 1 visible | 1177x630 | compact | First run + Garden |
| 004 | `starter-nursery-plants` | FN | NurseryDialog | Release-ready starter catalog; no owned plant | 840x588 | wide | Nursery + First run |
| 005 | `starter-selection-confirmation` | FC | StarterConfirmationDialog | First release-ready species awaiting confirmation | 480x300 | wide | First run |
| 006 | `starter-action-above-footer` | FN | NurseryDialog | Starter action scrolled above fixed footer | 840x588 | wide | Nursery + First run |
| 007 | `deck-browser-home` | H | AnkiQt / Home HTML | Real Choose commit; planted starter, `active_plant_id=None` | 667x570 | default | Home |
| 008 | `overview-home` | H | AnkiQt / Home HTML | Real Choose commit; planted starter, `active_plant_id=None` | 667x570 | default | Home |
| 009 | `full-garden` | G | GardenDashboard / GardenSceneWidget | Planted-before-Nurture dashboard overview | 1177x630 | compact | Garden + Scene |
| 010 | `hover-outline` | G | GardenDashboard / GardenSceneWidget | Representative plant hovered, not selected | 1177x630 | compact | Garden + Scene |
| 011 | `selected-plant-not-nurtured` | G | GardenDashboard / GardenSceneWidget | Starter selected before Nurture | 1177x630 | compact | Garden + Scene |
| 012 | `selected-plant-nurtured` | G | GardenDashboard / GardenSceneWidget | Real Nurture commit plus first-Nurture memory | 1177x630 | compact | Garden + Scene |
| 013 | `fertilizer-unaffordable` | F | DialogShell (`FertilizerDialog`) | 0 Coins; no fertilizer | 600x580 | default | Economy |
| 014 | `fertilizer-affordable` | F | DialogShell (`FertilizerDialog`) | 500 Coins; no fertilizer | 600x580 | default | Economy |
| 015 | `fertilizer-active` | F | DialogShell (`FertilizerDialog`) | 500 Coins; active Basic fertilizer | 600x580 | default | Economy |
| 016 | `move-mode` | G | GardenDashboard / GardenSceneWidget | Active plant in placement draft | 1177x630 | compact | Garden + Scene |
| 017 | `plant-story` | ST | PlantStoryDialog | Selected plant identity, stage, Growth, and memories | 640x520 | wide | Story + Collection |
| 018 | `active-deck-browser-home-after-nurture` | H | AnkiQt / Home HTML | Persisted first-Nurture state on Deck Browser | 667x570 | default | Home |
| 019 | `active-overview-home-after-nurture` | H | AnkiQt / Home HTML | Persisted first-Nurture state on Overview | 667x570 | default | Home |
| 020 | `growth-zero` | P | GardenProgressDialog | Daily Growth and source counters zeroed | 940x604 | wide | Progress + Collection |
| 021 | `growth-nonzero` | P | GardenProgressDialog | 1,250 Growth with nonzero source allocation | 940x604 | wide | Progress + Collection |
| 022 | `streak-new` | P | GardenProgressDialog | New 0-day streak presentation | 940x604 | wide | Progress + Collection |
| 023 | `streak-active` | P | GardenProgressDialog | Active current-day streak presentation | 940x604 | wide | Progress + Collection |
| 024 | `coins-zero` | P | GardenProgressDialog | 0 Coins and empty ledger | 940x604 | wide | Progress + Collection |
| 025 | `coins-activity` | P | GardenProgressDialog | 0 start plus real stage/streak credits in ledger | 940x604 | wide | Progress + Collection |
| 026 | `progress-overview` | P | GardenProgressDialog | Progress route: overview | 940x604 | wide | Progress + Collection |
| 027 | `progress-achievements` | P | GardenProgressDialog | Progress route: achievements | 940x604 | wide | Progress + Collection |
| 028 | `progress-collection` | P | GardenProgressDialog | Progress route: collection | 940x604 | wide | Progress + Collection |
| 029 | `collection-species-overview` | SO | GardenDialog (`SpeciesOverviewDialog`) | Owned species selected from Collection | 560x500 | default | Progress + Collection |
| 030 | `customize-garden` | C | CustomizeGardenDialog / GardenStudioWidget | Persisted loadout copied into clean Customize draft | 1040x630 | default | Customize + Environment |
| 031 | `customize-effects-on` | C | CustomizeGardenDialog / GardenStudioWidget | Local Customize draft with Weather/Scenery visible | 1040x630 | default | Customize + Environment |
| 032 | `customize-effects-off` | C | CustomizeGardenDialog / GardenStudioWidget | Local Customize draft with both visuals hidden | 1040x630 | default | Customize + Environment |
| 033 | `nursery-plants` | N | NurseryDialog | Nursery tab 1 catalog projection | 840x600 | wide | Nursery + Economy |
| 034 | `nursery-fertilizer-booster` | N | NurseryDialog | Nursery tab 2 catalog projection | 840x600 | wide | Nursery + Economy |
| 035 | `nursery-garden-spaces` | N | NurseryDialog | Nursery tab 3 catalog projection | 840x600 | wide | Nursery + Economy |
| 036 | `nursery-weather-scenery` | N | NurseryDialog | Nursery tab 4 catalog projection | 840x600 | wide | Nursery + Economy |
| 037 | `settings-menu-display` | SD | GardenSettingsDialog / GardenStudioWidget | Settings opened through registered Anki menu action | 980x629 | display | Settings + Diagnostics |
| 038 | `settings-display` | SD | GardenSettingsDialog / GardenStudioWidget | Display tab reset to top | 980x629 | display | Settings + Diagnostics |
| 039 | `settings-display-advanced-open` | SD | GardenSettingsDialog / GardenStudioWidget | Display tab with Advanced controls expanded | 980x629 | display | Settings + Diagnostics |
| 040 | `diagnostics-clean` | SD | GardenSettingsDialog / GardenStudioWidget | Troubleshooting with clean runtime telemetry | 980x629 | troubleshooting | Settings + Diagnostics |
| 041 | `diagnostics-warning` | SD | GardenSettingsDialog / GardenStudioWidget | Injected required-field telemetry warning | 980x629 | troubleshooting | Settings + Diagnostics |
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
| 056 | `fertilizer-expiring-under-minute` | F | DialogShell (`FertilizerDialog`) | Basic fertilizer expires in 45 seconds | 600x580 | default | Economy |
| 057 | `fertilizer-replacement-confirmation` | FR | FertilizerReplacementDialog | Active Basic -> Premium replacement confirmation | 480x420 | wide | Economy |
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
| 070 | `collection-several-discovered` | P | GardenProgressDialog | Exactly 4 of 10 release species discovered; remainder locked | 940x604 | wide | Progress + Collection |
| 071 | `collection-no-filter-matches` | P | GardenProgressDialog | Locked filter after all species temporarily discovered | 940x604 | wide | Progress + Collection |
| 072 | `achievement-completed` | P | GardenProgressDialog | Coherent completed achievement thresholds | 940x604 | wide | Progress + Collection |
| 073 | `clear-recall-separate-conditions` | P | GardenProgressDialog | 83% accuracy and 12/20 answers shown separately | 940x604 | wide | Progress + Collection |
| 074 | `streak-at-risk` | P | GardenProgressDialog | 7-day streak; no review today; last active yesterday | 940x604 | wide | Progress + Collection |
| 075 | `streak-missed-day` | P | GardenProgressDialog | Ended streak: current 0, previous 3 days | 940x604 | wide | Progress + Collection |
| 076 | `streak-reward-earned-next` | P | GardenProgressDialog | 14-day streak; 7/14 earned automatically; 30 next | 940x604 | wide | Progress + Collection |
| 077 | `nursery-item-owned` | N | NurseryDialog | Owned Nursery plant card | 840x600 | wide | Nursery + Economy |
| 078 | `nursery-item-locked` | N | NurseryDialog | 0 Coins/consumables; locked item disabled | 840x600 | wide | Nursery + Economy |
| 079 | `nursery-purchase-success` | N | NurseryDialog | Real environment purchase and owned receipt state | 840x600 | wide | Nursery + Economy |
| 080 | `nursery-final-row-above-footer` | N | NurseryDialog | Final Nursery row scrolled above fixed footer | 840x600 | wide | Nursery + Economy |
| 081 | `missing-artwork-graphical-fallback` | N | NurseryDialog | All artwork resolvers forced missing; graphical fallbacks | 840x600 | wide | Nursery + Economy |
| 082 | `settings-unsaved-changes` | SD | GardenSettingsDialog / GardenStudioWidget | Dirty Garden-name draft; Display scroll reset | 980x629 | display | Settings + Diagnostics |
| 083 | `settings-validation-error` | SD | GardenSettingsDialog / GardenStudioWidget | Whitespace Garden name; inline validation error | 980x629 | display | Settings + Diagnostics |
| 084 | `diagnostics-expanded` | SD | GardenSettingsDialog / GardenStudioWidget | Diagnostics details expanded | 980x629 | troubleshooting-expanded | Settings + Diagnostics |
| 085 | `production-build-controls-absent` | SD | GardenSettingsDialog / GardenStudioWidget | Production capability branch; dev controls absent | 980x629 | troubleshooting | Settings + Diagnostics |
| 086 | `reduced-motion-enabled` | SD | GardenSettingsDialog / GardenStudioWidget | Reduced Motion checked and scrolled into view | 980x629 | display | Settings + Diagnostics |
| 087 | `keyboard-focus-state` | G | GardenDashboard / GardenSceneWidget | Progress action focused by keyboard | 1140x630 | compact | Garden + Scene |
| 088 | `narrow-window-responsive` | G | GardenDashboard / GardenSceneWidget | Dashboard resized to 760x620 | 760x620 | narrow | Garden + Scene |
| 089 | `display-scaling-150` | G | GardenDashboard / GardenSceneWidget | Process `QT_SCALE_FACTOR=1.5` | 1140x630 | compact | Garden + Scene |
| 090 | `display-scaling-200-qt-representative` | G | GardenDashboard / GardenSceneWidget | 620x520 logical proxy; OS scale unchanged | 620x520 | narrow | Garden + Scene |
| 091 | `resize-dashboard-minimum` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-minimum` | 620x520 | narrow | Garden + Scene |
| 092 | `resize-dashboard-content-699` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-699` | 723x700 -> 723x699 | narrow | Garden + Scene |
| 093 | `resize-dashboard-content-701` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-701` | 725x700 -> 725x699 | narrow | Garden + Scene |
| 094 | `resize-dashboard-content-819` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-819` | 843x720 -> 843x699 | narrow | Garden + Scene |
| 095 | `resize-dashboard-content-821` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-821` | 845x720 -> 845x699 | compact | Garden + Scene |
| 096 | `resize-dashboard-content-899` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-899` | 923x740 -> 923x699 | compact | Garden + Scene |
| 097 | `resize-dashboard-content-901` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-901` | 925x740 -> 925x699 | compact | Garden + Scene |
| 098 | `resize-dashboard-content-999` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-999` | 1023x760 -> 1023x699 | compact | Garden + Scene |
| 099 | `resize-dashboard-content-1001` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-1001` | 1025x760 -> 1025x699 | compact | Garden + Scene |
| 100 | `resize-dashboard-content-1359` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-1359` | 1383x900 -> 1383x699 | compact | Garden + Scene |
| 101 | `resize-dashboard-content-1361` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-content-1361` | 1385x900 -> 1385x699 | wide | Garden + Scene |
| 102 | `resize-dashboard-default` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-default` | 1240x840 -> 1240x699 | compact | Garden + Scene |
| 103 | `resize-dashboard-large` | G | GardenDashboard / GardenSceneWidget | Declared resize-matrix transition `dashboard-large` | 1440x960 -> 1440x699 | wide | Garden + Scene |
| 104 | `resize-settings-minimum` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-minimum` | 560x420 | display | Settings + Diagnostics |
| 105 | `resize-settings-content-699` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-699` | 747x620 | display | Settings + Diagnostics |
| 106 | `resize-settings-content-701` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-701` | 749x620 | display | Settings + Diagnostics |
| 107 | `resize-settings-content-759` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-759` | 807x650 | display | Settings + Diagnostics |
| 108 | `resize-settings-content-761` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-content-761` | 809x650 | display | Settings + Diagnostics |
| 109 | `resize-settings-default` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-default` | 980x680 | display | Settings + Diagnostics |
| 110 | `resize-settings-large` | SD | GardenSettingsDialog / GardenStudioWidget | Declared resize-matrix transition `settings-large` | 1000x820 -> 1000x699 | display | Settings + Diagnostics |
| 111 | `resize-progress-minimum` | P | GardenProgressDialog | Declared resize-matrix transition `progress-minimum` | 720x500 | compact | Progress + Collection |
| 112 | `resize-progress-content-819` | P | GardenProgressDialog | Declared resize-matrix transition `progress-content-819` | 867x620 -> 867x604 | compact | Progress + Collection |
| 113 | `resize-progress-content-821` | P | GardenProgressDialog | Declared resize-matrix transition `progress-content-821` | 869x620 -> 869x604 | wide | Progress + Collection |
| 114 | `resize-progress-default` | P | GardenProgressDialog | Declared resize-matrix transition `progress-default` | 940x680 -> 940x604 | wide | Progress + Collection |
| 115 | `resize-progress-large` | P | GardenProgressDialog | Declared resize-matrix transition `progress-large` | 1000x820 -> 1000x604 | wide | Progress + Collection |
| 116 | `resize-customize-minimum` | C | CustomizeGardenDialog / GardenStudioWidget | Declared resize-matrix transition `customize-minimum` | 680x480 | compact | Customize + Environment |
| 117 | `resize-customize-content-819` | C | CustomizeGardenDialog / GardenStudioWidget | Declared resize-matrix transition `customize-content-819` | 867x620 | compact | Customize + Environment |
| 118 | `resize-customize-content-821` | C | CustomizeGardenDialog / GardenStudioWidget | Declared resize-matrix transition `customize-content-821` | 869x620 | wide | Customize + Environment |
| 119 | `resize-customize-default` | C | CustomizeGardenDialog / GardenStudioWidget | Declared resize-matrix transition `customize-default` | 1040x700 -> 1040x699 | wide | Customize + Environment |
| 120 | `resize-customize-large` | C | CustomizeGardenDialog / GardenStudioWidget | Declared resize-matrix transition `customize-large` | 1120x860 -> 1120x699 | wide | Customize + Environment |
| 121 | `resize-nursery-minimum` | N | NurseryDialog | Declared resize-matrix transition `nursery-minimum` | 640x460 | compact | Nursery + Economy |
| 122 | `resize-nursery-content-759` | N | NurseryDialog | Declared resize-matrix transition `nursery-content-759` | 795x600 | compact | Nursery + Economy |
| 123 | `resize-nursery-content-761` | N | NurseryDialog | Declared resize-matrix transition `nursery-content-761` | 797x600 | wide | Nursery + Economy |
| 124 | `resize-nursery-default` | N | NurseryDialog | Declared resize-matrix transition `nursery-default` | 840x640 | wide | Nursery + Economy |
| 125 | `resize-nursery-large` | N | NurseryDialog | Declared resize-matrix transition `nursery-large` | 1050x800 -> 1051x699 | wide | Nursery + Economy |
| 126 | `resize-story-minimum` | ST | PlantStoryDialog | Declared resize-matrix transition `story-minimum` | 480x400 | compact | Story + Collection |
| 127 | `resize-story-content-539` | ST | PlantStoryDialog | Declared resize-matrix transition `story-content-539` | 587x500 | compact | Story + Collection |
| 128 | `resize-story-content-541` | ST | PlantStoryDialog | Declared resize-matrix transition `story-content-541` | 589x500 | wide | Story + Collection |
| 129 | `resize-story-default` | ST | PlantStoryDialog | Declared resize-matrix transition `story-default` | 640x520 | wide | Story + Collection |
| 130 | `resize-story-large` | ST | PlantStoryDialog | Declared resize-matrix transition `story-large` | 640x680 | wide | Story + Collection |
| 131 | `resize-starter-confirmation-minimum` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-minimum` | 360x250 | compact | First run |
| 132 | `resize-starter-confirmation-content-399` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-content-399` | 447x280 | compact | First run |
| 133 | `resize-starter-confirmation-content-401` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-content-401` | 449x280 | wide | First run |
| 134 | `resize-starter-confirmation-default` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-default` | 480x300 | wide | First run |
| 135 | `resize-starter-confirmation-large` | FC | StarterConfirmationDialog | Declared resize-matrix transition `starter-confirmation-large` | 520x360 | wide | First run |
| 136 | `resize-fertilizer-minimum` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-minimum` | 520x460 | default | Economy |
| 137 | `resize-fertilizer-default` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-default` | 600x580 | default | Economy |
| 138 | `resize-fertilizer-large` | F | DialogShell (`FertilizerDialog`) | Declared resize-matrix transition `fertilizer-large` | 760x760 -> 760x676 | default | Economy |
| 139 | `resize-fertilizer-replacement-minimum` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-minimum` | 420x400 | compact | Economy |
| 140 | `resize-fertilizer-replacement-content-399` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-content-399` | 443x420 | compact | Economy |
| 141 | `resize-fertilizer-replacement-content-401` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-content-401` | 445x420 | wide | Economy |
| 142 | `resize-fertilizer-replacement-default` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-default` | 480x420 | wide | Economy |
| 143 | `resize-fertilizer-replacement-large` | FR | FertilizerReplacementDialog | Declared resize-matrix transition `fertilizer-replacement-large` | 560x500 | wide | Economy |
| 144 | `resize-species-overview-minimum` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-minimum` | 500x420 | default | Progress + Collection |
| 145 | `resize-species-overview-default` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-default` | 560x500 | default | Progress + Collection |
| 146 | `resize-species-overview-large` | SO | GardenDialog (`SpeciesOverviewDialog`) | Declared resize-matrix transition `species-overview-large` | 760x700 -> 760x699 | default | Progress + Collection |

## Ownership and implementation boundary

“Owner” in the inventory is the downstream implementation role, not permission
to change shared files independently. `ankigarden/ui/dashboard.py` is the main
merge-conflict hotspot: First run, Garden, Progress, Customize, Nursery,
Settings, Story, and Economy all touch classes in that module. Shared state and
transaction owners must freeze any new projection/purchase/action interfaces
before surface agents depend on them. Accessibility/responsive work coordinates
with each surface owner rather than owning the whole module.

This foundation does not implement the uncaptured loading, error, rollback,
Windows, true standard-scale, or true 200-percent variants listed in the
profiles. Those remain explicit downstream coverage requirements. The complete
146/146 v9 run closes the manifest gap; it does not close those native platform
and variant gaps or the visual residuals identified above.
