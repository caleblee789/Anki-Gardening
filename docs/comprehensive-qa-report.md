# Comprehensive QA and remediation report

- Date: 2026-08-15
- Branch: `codex/release-optimize-20260813`
- Anki runtime target: 26.08
- Package line: `2.1.0`, state schema 16, scene geometry 6

Status: historical frozen-candidate report. Its v8 139/146 and 146/146 records
remain evidence for the source audited on 2026-08-15, not for current source.
Current source is governed by capture contract v19 with 126 distinct ordered
surfaces captured once at canonical 100% scale. The final run at
`build/ui-face-captures/capture-sequence-20260823-000843` is complete and clean:
126/126 faces, 17 manifest-owned sheets, requested scale factor `1.0`, zero
capture failures, zero text-layout warnings, and valid manifest/contact-sheet
release validation. Resize, breakpoint, 150%, and 200% screenshot duplicates
are excluded while responsive geometry remains an automated release gate.
The schema-17 v12 run at
`build/ui-face-captures/capture-sequence-20260816-190930/20260816-190933` is
the 157/157 warning-free, validator-clean pre-purchase-overhaul baseline. The
historical v14 capture at
`build/ui-face-captures/capture-sequence-20260817-003223/20260817-003226`
is validator-clean at 181/181 with 23 complete contact sheets.
See `docs/ui-release-overhaul-contract.md` for the current implementation and
the remaining native-platform, human-accessibility, and visual-acceptance
boundaries.

## Historical release status

Verdant Twilight V6, its geometry-compatible environment library, and the
schema 16 garden-first interface supersede the
earlier placement candidate. Do not reuse old package hashes, hard-coded test or
asset counts, screenshots, or runtime acceptance claims. The repository and
package gates below are complete. The owner authorized release publication with
the seven explicitly listed macOS Home-capture omissions and the incomplete
exact-production live gate recorded here; neither boundary is relabeled as a
pass.

## Historical candidate verification

- Automated gates: 1,536 tests passed in 84.21 seconds; isolated-cache Python
  compilation, local Markdown-link audit, asset audit, and `git diff --check`
  passed.
- Asset audit: 9 backgrounds, 60 plant-stage sprites, 9 UI/planter assets,
  7 Weather overlays, and 1 decoration. The dedicated lossless pixel/container,
  planter, scene-profile, landmark, and item-art gate passed 50 tests.
- Production package gates: deterministic rebuild, ZIP integrity, exact ordered
  source/archive parity, production-only capabilities, and the ratcheted 78 MiB
  ceiling passed for 262 files. The archive is 81,702,743 bytes (77.92 MiB),
  SHA-256 `9d60b0d1b9523ca3f8c2b9e14be186c8b5ca19137f63064d1edfe15c99aa5b79`.
  This is 11,761 bytes smaller than the frozen pre-optimization package while
  retaining the exact manifest-owned image bytes.
- Capture-package gates: the separate explicit 263-file archive passed ZIP
  integrity and exact parity at 81,737,735 bytes, SHA-256
  `14114da87e24f4683bbcefdcdcca0ba2340263641d867bd9651bdbe7d28ddfeb`.
  It alone enables the capture harness; it cannot overwrite production.
- Runtime asset validation over the 79 primary raster entries reduced cold-pass
  file reads from 49,103,132 bytes to 1,580 bytes. Median validation time moved
  from 5.210 ms to 3.201 ms cold and 1.882 ms cached, while ordinary resolution
  now performs zero metadata writes. Cache identity includes resolved path,
  size, and modification time; rerolls and legacy local/remote records retain
  their established behavior.
- Runtime WebPs are already lossless VP8L without ICC/EXIF/XMP payloads or
  duplicate file hashes. Representative maximum-effort re-encoding produced no
  smaller exact-pixel background/occlusion output; transparent alternatives
  that changed hidden RGB were rejected under the exact-RGBA contract.
- Historical pre-freeze evidence covers capture contract v8 at 146/146 ordered
  surfaces and 150% UI scaling with zero failures or layout warnings. The exact
  final capture archive then produced 139/146 uniform-primary screenshots with
  zero text-layout warnings. It safely omitted
  `active-overview-home-after-nurture` and the six watering-can Home faces after
  macOS refused an exact-window pixmap; no desktop or wrong-window pixels were
  accepted. A separate bounded diagnostic captured the six watering-can Home
  faces 6/6 clean. The owner explicitly authorized publication without the
  seven missing frames; the final manifest remains incomplete by design.
- Exact-production startup used Anki 26.08.1, disposable profile
  `Anki Garden 2.1.0 Release 20260815-1711`, instance-key fingerprint
  `3fdbc25e59f9`, and production SHA-256 `9d60b0d1...5b79`. Process and
  filesystem identity passed and the add-on registered its hooks, but no unique
  PID-owned window title was returned and the disposable PID opened a connection
  to `sync11.ankiweb.net` despite disconnected/auto-sync-off profile metadata.
  The run was stopped immediately and was not restarted. Window, sync, and
  restart acceptance therefore remain explicitly waived, not passed.

## Current release outcome

| Area | Current result |
|---|---|
| State and transactions | Schema 21 keeps onboarding, loadout, passive-Growth residuals, reward/answer/Find/finalized-day identity, and purchase/Growth Charge replay under the shared engine/storage transaction boundary. |
| Rewards and Finds | UI surfaces read the authoritative reward-presentation and registry projections plus committed transaction results. They do not calculate reward amounts, achievement requirements, Find probabilities, inventory effects, or acquisition rules. Normal-answer receipts retain nurtured and passive exact-fifths allocations; Garden Find Growth is presented as direct Growth only. |
| Garden, Progress, Nursery, and Collection | The canonical dashboard, dialogs, popovers, responsive scroll behavior, loading/empty/error/success states, transaction receipts, environment previews, and collection placement routes are represented in the v19 capture contract. |
| Accessibility and responsive behavior | Keyboard focus, reduced motion, accessible descriptions, scroll containment, and breakpoint/scale geometry remain automated contracts. Native screen-reader and platform GUI acceptance remain separate. |
| Styling | Existing Garden styling is preserved. The superseded four-theme integration and its palette matrices are not part of this release. |

## Current automated and package evidence

- Full regression suite: 1,856 passed and 8 skipped.
- Focused post-capture-fix checks: 3 passed; Python compilation and
  `git diff --check` passed. The broad suite was intentionally not repeated for
  the final capture-only/coachmark geometry adjustment.
- Package tests: 10 passed before final capture framing work.
- Production archive: 273 entries, 81,884,216 bytes, SHA-256
  `005cae6ee1278bcdc68756f6d36b9e3857c3babbec5124219e8eea9930189dc7`.
- Capture derivative: SHA-256
  `10e7760fb1dfa098acfaab018693fa3acb281c4bcdaccb9b401550b31a2d43ff`.
  All 272 shared payloads are byte-identical, with shared-payload SHA-256
  `47eb2980055297b05753c9c8739dd110ba2c45260b20afbcef39151106d92a9d`.
- Capture contract v19: 126/126 faces, 17 sheets, requested scale factor 1.0,
  zero failures, zero text-layout warnings, `quality_status: clean`, and release
  validation `valid`.

## August 10 Weather and Scenery overhaul evidence

- Automated regression: 1,358 tests passed in 23.38 seconds.
- Asset audit: 9 backgrounds, 60 plants, 7 balanced Weather overlays, 7 UI
  assets, and 1 decoration; canonical Scenery alpha masks and V6 placements
  passed.
- Visual review: all nine 4:3, 16:9, and home plates preserve the six beds,
  Nursery, cottage, and path while remaining visually distinct.
- Final archive: 249 files, 78,369,480 bytes, SHA-256
  `077cdf68e76ca69ad03096ee1d9ad6ddbc1e6a8b14fa21888a97a44835aeb4bb`;
  ZIP integrity, compilation, package-content parity, and `git diff --check`
  passed.
- Exact-package isolated startup used Anki 26.08, profile
  `Codex QA Weather Final 20260810-234142`, base
  `/private/tmp/anki-release-qa.lr6q83ma`, and instance-key fingerprint
  `e6c51dabb84b`. Process, filesystem, and sync-disabled gates passed; the
  candidate imported, registered its hooks, and deferred pre-collection
  maintenance without an error traceback. The Mac was locked, so the
  required PID-owned window gate and all UI interactions/restart assertions were
  intentionally not attempted. PID 55512 exited and its WAL closed. Runtime UI
  acceptance therefore remains partial rather than passed.

## Historical August 10 V6 plant-library revision evidence

This checkpoint predates the current schema-16 environment bundle. Its archive
size, hash, and test count are historical only. The ten-line Verdant Twilight
library established one standardized progression:
Seed, Sprout, Young, Mature, Flowering, and Rare. All 60 canonical plant sprites
have exact source-master/hash metadata, normalized transparent canvases, and
bottom-center direct-soil placement. Rare stages use a related but structurally
different silhouette plus species-specific color/material and restrained magical
effects; Flowering remains the natural botanical peak.

- Strict review builder: 10/10 complete lines and three current review sheets in
  `build/twilight-full-library-review/`.
- Source audit: 60 exact-key `#FF00FF` masters verified; no missing or
  unmanifested V6 runtime sprites.
- Responsive placement: 210 plant assets across 20,160 scenarios, with 0
  failures and 0 warnings.
- Automated regression: 1,310 tests passed; isolated-cache compilation,
  package checks, ZIP integrity, and `git diff --check` passed.
- Final archive: 480 files, 201,812,727 bytes, SHA-256
  `34110916fa719c3442326608772c5581a7c7cb30faa21f78f963667f27241b7c`.
- Cleanup: 190 MiB of rejected candidates, duplicate Rose aliases, obsolete V4
  evidence, stale/mislabelled live-QA output, caches, and reproducible superseded
  review folders were moved to the recoverable macOS Trash bundle
  `Anki-Garden-cleanup-20260810-v6-library`. Accepted masters, compatibility
  inputs, the current full-library sheets, and final provenance were retained.

At that August 10 checkpoint, exact-package isolated-Anki checks verified the unique process, window,
filesystem, and sync-disabled profile gates, the ten-species Nursery, the Home
Widget, and the live Rose Seed scene. The remaining live Flowering/Rare A/B
capture was interrupted when the Mac locked; that checkpoint's live acceptance
therefore remained partial. It is historical evidence, not the current v19
capture result.

## Required exact-package isolated-Anki acceptance

Use a fresh, uniquely named disposable base/profile with sync disabled. Before
interacting—and again after restarting only the disposable process—verify:

1. Process identity: no command was forwarded to an existing normal Anki
   process.
2. Window identity: the visible window belongs to the unique disposable
   profile.
3. Filesystem identity: loaded add-on and collection paths are inside the
   disposable base.
4. Sync identity: the disposable profile is logged out or otherwise provably
   sync-disabled.

Then complete every journey in `e2e_display_assertions.md`, including fresh
Garden naming, starter choice, preselection review behavior, both home surfaces,
both scene landmarks, metric details, four-tab Nursery, environment collection
loadout/visibility, all Scenery/Weather combinations, Growth Charges, collection
transactions, direct Move and Undo, Fertilizer/Booster cards, seeded reward
receipts, achievement and Garden Find projections, real reviews and catch-up,
Story, Settings,
accessibility, reduced motion, responsive layouts, and restart persistence.

The catch-up journey must include an out-of-order lower ID after a higher ID,
prior-day and future/device-skew rows, database/cutoff/save failure followed by
retry, and a restart. Only supported rows in `[scheduler-day start, cutoff)` may
be marked processed; every eligible row must apply exactly once. The Fertilizer
journey must sync answers before, during, and after activation, then repeat after
same-tier extension, tier replacement, expired repurchase, Booster stacking, and
restart.

Record strict live acceptance only after all four gates and every required
journey pass. A disposable macOS startup/import smoke passed for the immediately
preceding production package before the final UI/capture-only fixes; it proves
launch/import isolation only, not final-SHA runtime, full journeys, restart, or
persistence. Native Windows/Linux GUI, screen-reader, human/device, and strict
end-to-end live acceptance remain unrun.
