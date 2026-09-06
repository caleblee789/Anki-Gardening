# Plant redesign integration

The coordinator owns integration of the ten completed species tasks. Each task
is named `Plant Name - Redesign`. Completed species tasks receive another message
only when a concrete defect in that species' artwork needs correction.

## Plan and acceptance

- [x] Receive all ten final handoffs and verify their current files, source
  pixels, and prior manifest-entry hashes. Use Dahlia's revised single tuber Seed,
  Sunflower's revised partially buried Seed, and Wisteria's final run.
- [x] Merge the 60 reviewed entries, install the staged Foxglove and Sunflower
  images, retain source provenance, preserve installer placement calibration, and
  refresh the affected pixel baselines.
- [x] Resolve shared scenery lighting, cache identity, contact/cast shadows,
  Seed anchoring, and physical-size image sampling.
- [x] Review all ten species together across six growth stages, nine sceneries,
  planting positions, and Garden/Home layouts.
- [x] Inventory every plant-art consumer and audit correct replacement,
  positioning, sizing, optical centering, padding, baseline, and aspect ratio.
  Check clipping, overlap, stale images, and intended locked placeholders.
- [x] Verify those consumers at their actual sizes in relevant light/dark themes,
  1x/2x display densities, compact layouts, and selection/ownership states. Check
  asset changes, stage changes, reopening, restart, and theme/scenery changes.
- [x] Run the appropriate existing validation, build a combined package, and
  inspect affected surfaces in fresh isolated Anki.
- [x] Deliver consolidated visual evidence, validation results, and remaining
  issues for the user's review.

The icon inventory includes Garden and Home; Collection and species overview;
Nursery and Shop; details, story and growth views; Reviewer and HUD; rewards,
recaps, receipts and summaries; menus, buttons, dialogs, and any additional
plant-art consumers found in code. Shared resolution or layout problems are
fixed centrally.

**User constraint:** Preserve the existing Home Screen and garden preview,
including its layout, dimensions, framing, and overlays. Do not redesign it.
The new canonical plant artwork and reviewed metadata are displayed through its
existing consumers. Home retains its original lighting and scaling rules; new
scenery grades and readability corrections apply only to native Garden.
The proposed Home changes were reverted byte-for-byte to the pre-integration
module. Existing cropping is documented rather than used to justify a redesign.

File integrity and automated geometry checks do not establish visual acceptance.
Species evidence is retained as submitted; combined evidence is produced in a
separate integration directory. Existing unrelated working-tree changes remain
outside this integration.

## Combined evidence

Evidence is collected in `build/plant-redesign-integration/20260905/`:

- `catalog-verification.json`: all 60 versioned source hashes, runtime hashes,
  exact lossless pixels, frozen pixel baselines and plant Retina density pass.
- `combined-render-manifest.json`: 1,278 native Garden scenarios and 7,668
  placements, with zero geometry warnings; 234 scene renders and 2,880 icon
  renders across 24 logical sizes at 1×/2×.
- `home-equivalence.json` and `qt-home-and-refresh.json`: Home and the shared
  asset resolver are byte-identical to the saved files. With identical updated
  art and metadata, 9,720 layouts, 540 HTML outputs and 27 Qt pixel pairs match.
- `garden-cache-checks.json`: native scenery appearance changes, physical draw
  sizes at both densities, stage changes and reopening pass actual Qt checks.
- `review.html`: consolidated native Garden and icon review with actual-size
  selectors and light/dark sheets. `surface-checklist.md` records each consumer,
  relevant icon sizes, tests, preserved Home limits and outstanding issues.

Focused tests: 981 passed, 11 skipped. The five failures in the earlier broader
UI/package run are resolved by the approved validation updates. All 82 affected
checks pass, including the release-evidence checks, and the full asset audit passes.
Catalog expectations now match three cosmetics and seven Garden features; Home's
existing starter-only breakpoint is explicitly allowed; earned-decoration preview
expectations match the retired visibility flags; the extracted Settings fixture
receives the real title constant. The user approved a strict 110 MiB package limit.
The lossless candidate remains 108.487 MiB; two new builds exactly match its hash.
No production rendering, artwork, metadata or mechanics changed in these fixes.

The final native audit captured all 51 v29 surfaces in fresh sync-disabled Anki,
passed independent validation and produced five contact sheets without text-layout
warnings. The unchanged package hash keeps that evidence applicable. `handoff.md`
links the candidate, visual review, raw archive and reports. Human visual acceptance
remains separate. The user subsequently authorized squashing all completed work
into main; this does not authorize a public release.

The user-requested remaining-cards row has been removed from the collapsed
Reviewer HUD. The plant ring, next Growth value and expand action remain. All
49 existing Reviewer/capture checks pass after this change, and the native widget
check verifies visible copy, artwork and empty-state reset. Candidate SHA-256:
`8be63226a6b4ffccee17bb30f7e5200dcbf31dca9f28e34fdab9d71c6d739760`.

Controlled normal-startup restart passed in the same disposable profile: all 60
rendered plant icons and saved plant state matched, isolation and sync-off gates
passed on both launches, and both processes exited cleanly. The temporary QA
observer was archived outside the disposable add-ons. See `native-restart-checks.json`.

## Combined-work merge validation

The five planned validation fixes pass all 82 affected checks. Two deterministic
builds match the reviewed candidate SHA-256 exactly. No production file was changed
by this validation follow-up. The broader default suite reports 1,686 passed,
21 skipped, 818 deselected and seven failed checks; it is not a clean full-suite gate.

The Wind Chime parity fixture was updated from the retired ten-answer cadence to
five answers. All 27 focused equivalence checkpoints pass. The longer annual check
then exposes a separate day-36 mismatch for `very_light:optimal_coin:landmark_mastery`:
`environment_effect_growth_units` is 0 in the simulator and 12,500 in the engine.
Three existing Settings assertions expect content-fit/480 height, a Collection
loadout assertion expects retired visibility flags, and two old plant-placement
assertions conflict with the reviewed Rare scale and asymmetric anchor calibration.
These seven broader checks remain outstanding; production behavior and reviewed
artwork were preserved. See `validation-fixes/full-tests.log` and
`validation-fixes/balance-release-recheck.log` in the integration evidence folder.

The user authorized squashing all completed working-tree changes into main.
That combined scope includes the existing welcome, trophies, balance, UI and capture
work as well as plant integration. Frozen sources and evidence remain preserved.
The merge does not constitute human visual acceptance or public release approval.
