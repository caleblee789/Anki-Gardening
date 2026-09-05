# Anki Garden 2.2.0 UI polish — source and state map

Implementation baseline: `8d67b0e07510b60a1306715e325db3c5d3debdfe` on main. Existing unmerged branches were inspected and left intact. Prior source/package evidence is preserved in `build/ui-release-polish-20260904-191901/baseline.json` and `before/`.

The supplied revised Garden image governs surfaces 05–08. Contact-sheet padding and Anki host backgrounds are outside the add-on UI.

| Surfaces | Existing source owners |
| --- | --- |
| 01, 30 | `ui/home_widget.py`: home projection, scoped HTML/CSS, shared copy |
| 02–04 | `ui/dashboard.py`: GardenDashboard inline starter and placement; `capture/workspace.py` |
| 05–08 | GardenDashboard, PlantInfoCard, NurturedPlantBar; `ui/scene.py`, `ui/plant_display.py` |
| 09–10 | GardenDashboard._open_fertilizer_menu; NurseryDialog compact item rows |
| 11 | GardenDashboard collection species grid and CollectionSubtabs |
| 12 | GardenDashboard._build_species_overview_dialog and species stage strip |
| 13 | PlantStoryDialog and MemoryTimeline |
| 14–15 | CollectibleDetailDialog and shared scene/environment renderer |
| 16 | LandmarkProjectOverview and LandmarkTierList |
| 17–20, 23 | NurseryDialog catalogs, shared item rows, purchase receipt |
| 21–22 | PurchaseConfirmationDialog; `purchases.py` presentation of authoritative quotes |
| 24–25 | GardenDetailsDialog._refresh_today; `ui/reviewer_hud.py` Today projection |
| 26 | GardenDashboard achievements; `reward_presentation.py` achievement projections |
| 27 | GardenDetailsDialog._refresh_currency; stored currency transactions |
| 28–29 | GardenSettingsDialog, `ui/garden_studio.py`, existing diagnostics projection |
| 31, 34 | `ui/reviewer_hud_widget.py`, `ui/reviewer_hud.py` |
| 32 | `ui/session_summary_card.py`, frozen `ui/session_summary.py` payload |
| 33 | `ui/sync_reward_summary.py`, existing reconciliation processor |
| 35–36 | GrowthChargeConfirmationDialog and engine quote/outcome |

Shared source owners are `ui/theme.py`, `ui/formatters.py`, `ui/copy.py`, existing dashboard shell, cards, tabs, disclosures, and `ui/dialog_foundations.py`. No new component framework or domain model is introduced.

## Verified state contracts

- Selection is the scene interaction's pinned plant ID. Nurturing is `state.active_plant_id`. Locating the nurtured plant opens its scene inspector; dismissal does not mutate nurturing.
- Starter selection stores a reversible pending species. Only confirmed placement creates the free plant. Surface 03 now records returning from placement with the tile selection retained.
- Displayed decoration, selected scenery, and visibility are independent from locked daily bonuses and later selections. Existing appearance Undo only restores fields changed by that operation.
- Fertilizer use/next and purchase previews consume existing domain projections, including the actual predecessor. Buying a Growth Charge adds inventory; applying it is a separate targeted transaction.
- Completion and reward state come from `daily_completion.status`, `reward_claimed`, and committed daily completion flags. Zero remaining alone does not announce a reward. No new activity requirement was added.
- Starting workload is rebased when Anki's queues change while completed work is preserved. Rollover uses the configured local Anki study-day boundary.
- Currency transactions retain up to 500 entries. Their sums are recorded totals, not proven lifetime totals. Missing history does not imply a zero balance or fabricated transactions.
- Species cards group plant types and use the highest achieved stage among owned instances. Species artwork preview remains separate from individual history and preserves concealed Full Bloom art.
- Landmark activation selects future Growth routing, contribution spends Stored Growth, and building is its own domain operation with a Coin cost.
- Session totals, Garden Find events, awarded item quantities, and discoveries remain separate. Reconciliation QA uses the real detector, processor, and engine with temporary in-memory storage; live AnkiWeb transport is outside this run.

## Implemented changes

- Shared botanical colors, aligned main and secondary tabs, compact actions, disclosures, artwork frames, and consistent number formatting retain the existing font scale.
- The 3:2 Garden scene and persistent nurtured footer form one aligned group. A compact floating inspector keeps selection separate from nurturing, anchors to the selected bed, and places Move in More. Supplies and details preserve their intended plant.
- Starter tiles advance directly to reversible bed placement. Collection cards omit the redundant single-plant count and explain their highest owned stage. Species previews remain distinct from individual plant history.
- Shop plant cards put View stages beneath the name and the Coin icon beside the price. Supplies, appearance libraries, active and later bonuses, and purchase confirmations use clear contextual actions and compact ownership summaries.
- Today uses committed completion and reward state. Coin history reports recorded totals. Settings preserve Save/Cancel and keep artwork diagnostics behind a disclosure.
- Home, reviewer, session and sync summaries share the presentation system. Growth Charge previews and results distinguish expected rewards from committed outcomes.
- The supplies callback now calls the existing dialog fitting API, fixing the reported `fit_content_height` AttributeError. All four native header tabs use equal widget geometry, correcting the Shop tab's measured four-pixel offset.
- Existing test fixtures now use the revised visible labels and v27 surface counts. The balance-analysis replay and accelerated model respect the existing five-dose Booster cap; a fixed Halloween seed/day fixture prevents presentation-copy edits from changing that test's expected draw. These repairs affect validation tooling, not gameplay.

Progression thresholds, prices, reward amounts, inventory accounting, acquisition, scheduling, and sync reconciliation rules were not changed.

## Validation and capture evidence

Evidence lives in `build/ui-release-polish-20260904-191901/`:

- Focused existing tests: **484 passed, 8 skipped** (`focused-tests.log`).
- Final scoped fast suite: **1,565 passed, 21 skipped** (`merge-fast-final.log`). The full annual release simulation was explicitly excluded; its affected scenario passed all 365 checkpoints and 2,610 answers (`merge-bounded-parity.log`).
- Final local release-evidence checks: **779 passed, 16 skipped** (`merge-release-evidence.log`). Native Qt behavior was separately exercised in the proof and capture runs below.
- Production ZIP integrity, all 322 source/archive entries, artwork audit, compilation, documentation links, and patch whitespace passed. GitHub Actions could not start because of the account's billing/spending limit; remote CI is not represented as passing.
- Existing Qt inspector and selection regressions: **2 passed, 17 deselected** (`qt-tests.log`).
- Native Qt proof: 1040 × 720 and 860 × 580 Garden windows, selection versus nurturing, edge placement, long names, child dialogs, settings, and compact purchase/supplies geometry (`qt-proof.log`, `nav-probe.log`).
- Native action walkthrough: starter Back/reselection/single commit, selection and nurturing, move/swap/cancel/Undo, settings Save/Cancel, and purchase cancellation/commit passed (`native-walkthrough.json`).
- The real sync detector, processor and engine processed three new answers once; repeated and no-change batches produced no duplicate rewards or receipt (`sync-pipeline-check.json`). This check used temporary in-memory storage.
- The existing pass-three capture completed **36 of 36** fresh native surfaces, independent validation, package derivative parity, and graceful Anki shutdown. It used Anki 26.8.1, Qt 6.11, macOS, normal text size and 100% Qt scale in a disposable sync-disabled profile. Surface 03 documents returning from placement, retaining the starter tile selection.

The five sheets were rebuilt from that completed capture on request, without another Anki capture:

- [Contact-sheet index](../../build/ui-release-polish-20260904-191901/native-pass-3/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-203429/contact-sheet-set.json)
- [Capture report and original image references](../../build/ui-release-polish-20260904-191901/native-pass-3/full/capture-sequence-20260904-203429/capture-report.json)

Captured production package: `candidate-3/anki_garden.ankiaddon`, SHA-256 `87ec8e098d592460965eb4031ead361065df0a7a6858e656fa113a257113358e`.
Capture derivative: SHA-256 `f50a0aff783f05fbc16fb24041aa8d0c57d09b3b69e398e021c70669f7d3eda8`; all **321 shared payload entries** matched that production package.

## Evidence limits

Two subsequent refinements are outside the captured package: the Fertilizer dialog family fits to the common 446-pixel supplies height, and the sync summary uses the shared Growth icon and accent. The current production archive includes those changes: SHA-256 `b8b1304c6d96e62d147963763d4dcf70cec184a7a4620a5f8ebc9f5b9cd50f37`. The existing sheets remain bound to their original package; they are not represented as exact visual evidence of these two later changes.

The independent capture validator passed, and all five rebuilt sheets were inspected for consistency. Native high-risk screens were inspected at full size. The local finishing report records final merge checks. The full 66-scenario annual economy simulation is outside this UI finishing pass; only its affected scenario is checked. Human visual acceptance, full-screen Spaces behavior, live AnkiWeb transport, and a memory leak probe were not certified by this run. `quality_status` remains `review-required` and `release_ready` remains `false`; merging does not grant release approval.
