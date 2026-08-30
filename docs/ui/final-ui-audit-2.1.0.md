# Anki Garden 2.1.0 UI evidence

Status: the current full v26 capture and its five contact sheets have passed
independent automated validation and 34/34 original-resolution raw-image
review. The generated report intentionally remains
`quality_status: review-required` with `release_ready: false`; human, native,
and platform release acceptance remain separate gates.

## Current acceptance contract

Capture contract v26 uses contract schema 2 and scenario schema 3 to compile
the Qt-free surface registry into two profiles:

| Profile | Surfaces | Sheets | Evidence tier |
|---|---:|---:|---|
| `representative` | 18 | 2 | Preflight |
| `full` | 34 | 5 | Final-release automation |

The counts are generated observations rather than fixed acceptance constants.
Retired or behavioral-only IDs remain reserved, including
`nursery-weather-scenery`, the retired starter confirmation, detached Reviewer
stacks, and every watering-can capture. Both profiles use
`QT_SCALE_FACTOR=1.0`. Raw manifest-owned PNGs are the geometry authority;
contact sheets are presentation aids.

Every v26 spec, dependency digest, runtime record, manifest row, validator
result, contact-sheet index entry, and PNG metadata record carries
`scenario_id`, `fixture_id`, and one-based `scenario_step`. The shared seeded
lineages are:

| Ordinals | Scenario | Fixture lineage |
|---|---|---|
| 01–04 | `first_run` | `first_run-v1` |
| 09–10 | `fertilizer_queue` | `fertilizer_queue-v1` |
| 33–34 | `growth_charge_transition` | `growth_charge_transition-v1` |

The named single-surface scenarios are `reviewer_hud_base` at 27,
`session_summary` at 28, `sync_rewards` at 29, and
`reviewer_hud_full_bloom` at 30. Other surfaces default to their stable ID,
fixture `v1`, and step 1. V25 evidence is frozen historical evidence and is
categorically rejected for v26 reuse.

Deprecated visible copy, DOM/root overflow, progress fractions, asset mapping,
Reviewer exclusion rectangles, four-state scrolling, acquisition identity,
lifecycle, and scenario/state identity are hard gates. Compatibility keys and
historical migration tests have narrow non-visible allowlists only.

## Current evidence

- Fresh representative baseline with reuse disabled:
  `build/ui-face-captures/representative/capture-sequence-20260830-092533`
- Fresh full 34-surface baseline with reuse disabled:
  `build/ui-face-captures/full/capture-sequence-20260830-092931`
- Corrected sequential raw run for surfaces 05–10 and 31:
  `build/ui-face-captures/full/capture-sequence-20260830-100734`
- Exact-package raw refresh for 31 invalidated surfaces, with three exact
  surface reuses:
  `build/ui-face-captures/full/capture-sequence-20260830-103121`
- Final assembled and sheet run:
  `build/ui-face-captures/full/capture-sequence-20260830-103800`
- Final manifest:
  [assembled/manifest.json](../../build/ui-face-captures/full/capture-sequence-20260830-103800/assembled/manifest.json)
- Final capture report:
  [capture-report.json](../../build/ui-face-captures/full/capture-sequence-20260830-103800/capture-report.json)
- Final contact sheets:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260830-103800`
- Contact-sheet index:
  [contact-sheet-set.json](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260830-103800/contact-sheet-set.json).

The final assembly validator reported a valid 34-surface/five-page set,
`automated_release_gate_passed: true`, and `release_ready: false`. The final
exact-package raw refresh freshly captured 31 surfaces and exact-reused only
Settings, Diagnostics, and the Growth Charge purchase confirmation from the
previous reviewed evidence. The final assembly then exact-reused all 34 images
from that reviewed raw manifest without recapturing UI. All 34 current raw
PNGs were reviewed at their original macOS 100% dimensions, and all five
generated sheets were reviewed at full resolution; 34/34 raw surfaces and 5/5
sheets passed. This visual disposition is evidence review, not human release
approval.

The reviewed fixtures include these cross-surface invariants:

- Collection: `10 of 10 species discovered` and separately
  `30 of 39 collection entries discovered`;
- Reviewer HUD: `176 + 18 = 194`, with `Sprout · 2 of 6 stages`;
- Session Summary: `126 + 19 = 145`;
- Sync Rewards: `420 + 80 + 20 = 520`;
- Reviewer safe area: width 296, top 44, right 16, measured answer-control
  clearance with a 72 px fallback and narrow-layout collapse; and
- asset calibration: serialized `visual_scale_correction`, all 60
  species-stage assets, and all six bed positions.

## Package binding

The current evidence binds these exact artifacts:

- capture-contract digest:
  `17d3b81df9351a4aec6e0ffc9ecc2fe5233c0211c9ef103f2819e707f6a1bf07`;
- production package `dist/anki_garden.ankiaddon`: 300 files,
  85,707,953 bytes, SHA-256
  `d80499b0be7971888360f53cccaa381696f5e73b5a5b69a3e4a6703e51908354`;
  and
- byte-matched capture derivative in each current evidence run: 312 files,
  86,086,907 bytes, SHA-256
  `829ec3406809164d2708ecadfb328e62c1e237fe4c224e3ed493bf937c6f48fd`.

The preserved final evidence archive is
`build/ui-face-captures/full/anki-garden-ui-faces-20260830-103800.zip`,
25,417,495 bytes, SHA-256
`ddb1a064a01be4b7b8d2c4625fe2aceff49d15f9f5af6d028cf5ec835963b7b0`.

The capture derivative adds capture-only capability and cannot overwrite the
production archive. Shared production payload parity remains required; neither
artifact is published by this evidence workflow.

## Local validation boundary

Before the intentional test cleanup, the last completed local lanes reported:

- fast pytest: 1,546 passed, 23 skipped, 820 deselected;
- release-evidence pytest: 805 passed, 15 skipped, 1,569 deselected; and
- explicit full union: 2,351 passed, 38 skipped.

The test additions were then simplified at explicit user direction: brittle
source-scraping, fixed-pixel screenshot locks, and oversized mocked-Qt failure
harnesses were removed while compact engine/state/coordinator behavior checks
were retained. No further local test, compile, Markdown/link, or diff-check
command was run after that cleanup. Those earlier counts must not be read as a
post-cleanup run; the required pull-request checks remain the merge authority.

The last pre-cleanup compilation, artwork audit, deterministic package build,
archive integrity, and shared-payload parity checks passed. The final capture
workflow then rebuilt the current byte-matched derivative, assembled the
reviewed 34-surface set, and completed its manifest/contact-sheet validation.
The current derivative's standalone zero-surface clean-shutdown gate was not
rerun locally after its capture-only correction. These automated results
support review but do not replace the open human, native macOS, or
cross-platform acceptance gates.

## Local evidence retention

Only the newest complete full five-page contact-sheet directory is retained as
the active presentation set. Superseded full and representative sheet sets
were moved recoverably to `/private/tmp` only after the final set passed
independent validation and visual inspection; they are intentionally not
linked as active evidence. Raw capture runs, manifests, reports, lineage,
evidence archives, the production and capture archives, source artwork, and
the untracked economy PDF remain preserved.

## Remaining acceptance

The following gates remain open until separately run and recorded:

- human release approval of the current five-sheet full set;
- full-screen macOS interaction through the Garden and each nested dialog,
  including confirmation that no action switches Spaces or creates a stray
  top-level window;
- native Windows and Linux behavior;
- true OS 125%/150% and mixed-DPI behavior;
- forced colors, screen-reader, contrast, broader keyboard, and device-level
  visual acceptance; and
- a fresh exact-package capture if implementation or packaged assets change
  after the hashes recorded above.

Prior local tests, package parity, contact-sheet completeness, the automated
release gate, and 34/34 raw-image review do not close these gates by
themselves. The add-on remains `quality_status: review-required`,
`release_ready: false`, and unpublished.
