# Anki Garden UI surface inventory

The current capture contract is **v29**, schema 2, scenario schema 3. The full
profile contains **50 active surfaces on five explicit sheets**. Representative
preflight covers 22 surfaces across those same five assignments. Both use
canonical 100% UI scale; macOS Retina pixels remain at the native device ratio.

The authoritative registry is `ankigarden/capture/workspace_specs.py`, compiled
into `ankigarden/capture/capture-contract-v29.json`. The shared presentation map
is `ankigarden/capture/handoff.py`. The renderer, index and independent validator
consume the compiled `profiles[].contact_sheets` map. Each active surface also
carries `handoff.sheet`, `handoff.sheet_name` and `handoff.display_order`.

## Coverage and ownership

All 35 active v28 surfaces are retained, plus 15 active new views. Collection and Shop
remain separate assignments. Item-use dialogs and Growth Charge outcomes belong
to Shop so the complete purchase/use flow has one owner. The Garden/onboarding
owner integrates shared navigation, theme and copy changes. Agents should own
classes or methods in shared files, rather than replacing whole files.

Landmarks (`collection-landmarks-page`) is disabled by the current feature gate.
It is excluded from this set. Its prior 36-surface completed sets, stable ID and
historical evidence remain preserved; the disabled view is not counted as missing.

## Sheet 1: Garden and onboarding (12)

| Order | Stable surface ID | Native path | Coverage |
|---:|---|---|---|
| 1 | `starter-deck-browser-home` | Anki Decks → first-run Garden Home card | Retained |
| 2 | `garden-starter-picker` | Home card → Open Garden → choose first plant | Retained |
| 3 | `garden-starter-selected` | Select starter → placement → Back (selection retained) | Retained |
| 4 | `garden-starter-placement` | Choose starter → Choose a bed | Retained |
| 5 | `workspace-starter-awaiting-nurture` | Place starter → select its bed → Nurture available | New in v29 |
| 6 | `workspace-welcome-settled` | Nurture first starter → welcome animation settles | New in v29 |
| 7 | `workspace-welcome-rewards-expanded` | First Nurture → welcome → View rewards (past-study fixture) | New in v29 |
| 8 | `garden-overview` | Open Garden → Garden tab | Retained |
| 9 | `garden-inspector-nurtured` | Garden → select nurtured plant | Retained |
| 10 | `garden-inspector-available` | Garden → select another planted plant | Retained |
| 11 | `garden-move-plant` | Garden → plant inspector → More → Move | Retained |
| 12 | `workspace-decoration-inspector` | Garden → select displayed decoration | New in v29 |

## Sheet 2: Collection and appearance (9)

| Order | Stable surface ID | Native path | Coverage |
|---:|---|---|---|
| 1 | `collection-plants-page` | Collection → Plants | Retained |
| 2 | `collection-species-details` | Collection → Plants → select a species | Retained |
| 3 | `collection-plant-details` | Collection → Plants → species → plant name | Retained |
| 4 | `workspace-collection-plant-menu` | Collection → Plants → species → planted row overflow icon | New in v29 |
| 5 | `workspace-collection-storage-confirmation` | Collection → Plants → species → More → Move to storage | New in v29 |
| 6 | `collection-scenery-page` | Collection → Appearance → Scenery | Retained |
| 7 | `workspace-scenery-preview` | Collection → Appearance → Scenery → select Spring | New in v29 |
| 8 | `workspace-scenery-applied-undo` | Collection → Appearance → Scenery → select Spring → card Equip → Undo visible | New in v29 |
| 9 | `collection-decorations-page` | Collection → Appearance → Decorations | Retained |

## Sheet 3: Shop and item use (12)

| Order | Stable surface ID | Native path | Coverage |
|---:|---|---|---|
| 1 | `shop-plants-page` | Shop → Plants | Retained |
| 2 | `shop-scenery-page` | Shop → Scenery | Retained |
| 3 | `shop-decorations-page` | Shop → Decorations | Retained |
| 4 | `shop-supplies-page` | Shop → Supplies (top) | Retained |
| 5 | `workspace-shop-supplies-scroll-end` | Shop → Supplies → scroll to end (lower section) | New in v29 |
| 6 | `shop-fertilizer-confirmation` | Shop → Supplies → buy Fertilizer | Retained |
| 7 | `purchase-confirmation-growth-charge` | Shop → Supplies → buy Growth Charge | Retained |
| 8 | `shop-purchase-receipt` | Shop → Plants → buy Sunflower Seed → confirm purchase → receipt | Retained |
| 9 | `garden-use-fertilizer` | Garden → plant inspector → More → Plant supplies → Fertilizer | Retained |
| 10 | `garden-use-growth-charges` | Garden → plant inspector → More → Plant supplies → Growth Charges | Retained |
| 11 | `growth-charge-use-ready` | Choose Growth Charge → use confirmation | Retained |
| 12 | `growth-charge-success-stage-reward` | Confirm Growth Charge → committed stage reward | Retained |

## Sheet 4: Progress and settings (10)

| Order | Stable surface ID | Native path | Coverage |
|---:|---|---|---|
| 1 | `progress-today-page` | Progress → Today | Retained |
| 2 | `progress-today-details` | Progress → Today → expand details | Retained |
| 3 | `progress-achievements-page` | Progress → Achievements (top) | Retained |
| 4 | `workspace-achievements-scroll-end` | Progress → Achievements → scroll to end (final rows) | New in v29 |
| 5 | `workspace-trophy-room` | Progress → Trophy Room (locked and unlocked) | New in v29 |
| 6 | `progress-coins-page` | Progress → Coins | Retained |
| 7 | `garden-settings` | Workspace gear → Settings | Retained |
| 8 | `workspace-settings-unsaved` | Settings → edit Garden name → unsaved Save/Cancel state | New in v29 |
| 9 | `garden-diagnostics` | Settings → Artwork check → scroll to result | Retained |
| 10 | `workspace-diagnostics-warning-details` | Settings → Artwork check → warning → Technical details → scroll to end | New in v29 |

## Sheet 5: Anki integration and rewards (7)

| Order | Stable surface ID | Native path | Coverage |
|---:|---|---|---|
| 1 | `active-deck-browser-home-after-nurture` | Nurture plant → close Garden → Anki Decks Home card | Retained |
| 2 | `reviewer-hud-expanded` | Anki study → expand Garden Reviewer HUD | Retained |
| 3 | `workspace-reviewer-collapsed` | Anki study → collapse Garden Reviewer HUD | New in v29 |
| 4 | `reviewer-reward-dock-bundle` | Anki study → committed reward → integrated reward dock | Retained |
| 5 | `workspace-reviewer-rewards-list` | Collapsed Reviewer presentation → expand reward summary | New in v29 |
| 6 | `session-summary-after-review` | Study cards → leave Reviewer → Session Summary | Retained |
| 7 | `sync-rewards-summary` | Anki Home → Sync Rewards receipt (committed offline fixture; network sync disabled) | Retained |

## Capture execution

Acquisition order is independent of sheet placement. Preserve the first-run
scenario prerequisites and transaction sequence even when their images appear
in different sheet groups. The 15 active additional IDs use deterministic isolated
fixtures and per-surface postconditions. Onboarding, purchases and item use show
native actions and committed engine results. The expanded welcome fixture
reconciles 5,000 eligible past reviews through the engine; its gift and historical
rewards are not manually written presentation values.

Capture the current dirty source from a new timestamped snapshot, including
untracked runtime files and assets. Build the production archive inside that
snapshot, then verify its capture derivative byte-for-byte for all shared
runtime members. Never overwrite a prior source snapshot, archive or evidence set.

Use fresh disposable `/private/tmp/anki-release-qa.*` bases, sync-disabled
profiles, and verified process/window/filesystem identities. Keep normal dialog
sizes and maximized Home/Reviewer geometry. Popups are native widget pixels at
their actual positions over their owning workspace; webview captures verify the
HUD and reward-list overlays. The diagnostic-warning fixture runs the real
filesystem check with one deliberately absent manifest entry while leaving the
installed package untouched.

Run representative preflight, then full capture. Reuse only validated surfaces
from this task's frozen source baseline; renderer, fixture, package and scenario
digests must still match. Preserve valid partial captures on failure, and report
precise missing IDs instead of declaring an incomplete run complete. Additional
responsive and animation checks are supporting evidence, not more sheet tiles.

## Presentation and handoff

### Full capture in one launch

After the new plant assets are ready, freeze the current runtime and assets in
a new source snapshot and build its production archive. Run the snapshot's own
runner from inside that snapshot:

```bash
python scripts/capture_sequence.py --profile full --fresh-baseline --anki-version 26.8.1
```

This mode schedules all 51 surfaces in one disposable Anki process, includes
the process shutdown gate in that session, and disables historical screenshot
reuse. It then validates the raw set and renders the five sheets. It never
starts a second Anki process to repair a failed surface. The ordinary
incremental mode remains available when exact reuse is wanted.

Add `--plan-only` to inspect the complete ordered plan without launching Anki,
building packages or capturing images. Foreground fallback is bounded per
Home/Reviewer surface; normal dialogs retain native background capture.

The runner fixes have offline regression coverage. A fresh 51/51 native run
with the new plant assets is still pending and must be verified when capture
is authorized.

Produce five PNGs, each 3,000 pixels wide with two columns. Explicit sheet
boundaries replace the old five-row pagination limit: 12/10/12/10/7 surfaces
require 6/5/6/5/4 rows. Use consistent thumbnail boxes, native aspect ratios,
top alignment and clearly marked non-UI padding. Scroll-end views are named
explicitly. Each surface appears exactly once.

Each PNG receives a matching brief with stable IDs, native navigation paths,
full-resolution raw links, frozen code sections, ownership boundaries and observed
issues. The handoff includes a coverage index, raw PNGs, source inventory,
manifest, independent validation report, visual review and evidence archive.
`python scripts/build_refinement_handoff.py --help` describes the packager.

## Acceptance boundary

A completed full run requires 51 expected surfaces, 51 valid native PNGs, five
sheets and no omitted or duplicate assignments. Package hashes and each
surface-to-image binding must verify. Inspect every raw PNG and all five sheets
for the correct state, readable labels, complete controls, popup inclusion and
visible lower content. Raw manifest-owned PNGs are the geometry authority.

Fixture identity, native rendering, required overlay pixels, geometry, package
provenance and cleanup remain fail-closed. Observed UI polish issues belong in
the agent briefs; this task does not redesign the UI or change gameplay.
Completion is evidence preparation only: `quality_status: review-required`,
`release_ready: false`. It does not provide human release approval, publication,
Windows/Linux acceptance, mixed-DPI or exhaustive responsive/animation coverage.

### Native UI issue retained for refinement

The collapsed Reviewer HUD currently clips its cards-remaining text at its unchanged native width. Both new collapsed Reviewer views preserve that product behavior and record `reviewer-collapsed-status-width` in raw text warnings, audit `native_ui_issues`, visual review and agent brief 5. This one role-specific horizontal text issue is advisory for the refinement evidence; missing pixels, wrong states, window or control clipping, and all unrelated layout warnings remain blocking. This exception is not a product fix or release approval.

## Completed v29 handoff

The [September 5 grouped handoff](../build/ui-refinement-v29-20260905-184218/handoff-20260905-205811/README.md)
contains five sheets, five agent briefs and 51 independently validated native
captures, with no omitted or duplicate assignments. All raw images and sheets
were visually inspected. The [portable evidence archive](../build/ui-refinement-v29-20260905-184218/handoff-20260905-205811.zip)
includes the raw images, manifests, validation, frozen code references, verified
packages and source inventory. The obsolete scenery summary and Apply block
are removed in this baseline. Evidence remains `review-required` and
`release_ready: false`.
