# Anki Garden 2.1.0 UI evidence

Status: the current full v25 capture is complete and its five contact sheets
have been inspected for obvious clipping, overlap, and acquisition errors. The
generated report intentionally remains `review-required` with
`release_ready: false`; human, native, and platform release acceptance remain
separate gates.

## Current acceptance contract

Capture contract v25 compiles the Qt-free surface registry into two profiles:

| Profile | Surfaces | Sheets | Evidence tier |
|---|---:|---:|---|
| `representative` | 18 | 2 | Preflight |
| `full` | 34 | 5 | Final-release automation |

The counts are generated observations rather than fixed acceptance constants.
Retired or behavioral-only IDs remain reserved, including the retired starter
confirmation and every watering-can capture. Both profiles use
`QT_SCALE_FACTOR=1.0`. Raw manifest-owned PNGs are the geometry authority;
contact sheets are presentation aids.

Detailed semantic, copy, text-fit, layout, scroll, and duplicate-view findings
remain visible review advisories. They are not silently normalized, and a valid
automated manifest or agent visual pass is not human release approval.

## Current full evidence

- Final run:
  `build/ui-face-captures/full/capture-sequence-20260829-172210`
- Manifest: `assembled/manifest.json` in that run
- Contact sheets:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260829-172210`
- Contact-sheet index: `contact-sheet-set.json` in that directory
- Evidence archive:
  `build/ui-face-captures/full/anki-garden-ui-faces-20260829-172210.zip`
- Result: 34/34 surfaces and five sheets passed independent surface and
  contact-sheet validation with no recapture requests or text-layout warnings.
  Sixteen full-only surfaces were acquired in the final run; 18 surfaces were
  reused from the fresh representative preflight through compatible immutable
  per-surface lineage. Clean process shutdown passed.
- Review telemetry: one non-blocking advisory records that macOS refused to
  move the pointer to a neutral screen corner before the first Deck Browser
  capture. The app-owned Qt/WebView acquisition does not include the OS cursor;
  the saved surface passed semantic, geometry, stability, and visual review.
- Visual disposition: all five sheets were inspected. No obvious clipping,
  overlap, wrong-window acquisition, or contact-sheet framing defect was found.
  The Collection fixture reports the current 30-of-39 catalog, and the Sync
  Rewards surface proves two stable frames.

The full report's automated release gate passed. Its overall release state
remains nonready because manual native and platform acceptance have not been
signed off.

## Representative evidence boundary

The current representative preflight is
`build/ui-face-captures/representative/capture-sequence-20260829-171759`.
It freshly captured 18/18 surfaces across two valid contact sheets with no
issues, advisories, text-layout warnings, or recapture requests and with clean
process shutdown. Its Collection postcondition and Sync Rewards stability proof
both passed. It is preflight evidence only and does not set the automated
full-release gate.

## Package binding

The current evidence binds these exact artifacts:

- capture-contract digest:
  `74b9028d3b8bb696fa8f4a8af541211c28731693e4b4fc0fc8b7f6d16b79e882`
- full capture package SHA-256:
  `204ece1a4cea9cd998090f7d3a3f514fb25091bf59ccd0f0165abc56b43c139b`
- production package SHA-256:
  `1fbbaf58ce9cfcb1b9f6d3c8782f93fa4f699e40d5910798fd8bdee73c98b198`
- full evidence archive SHA-256:
  `e85d051f7633e165e5738953b70d136f2285577468cdc7a0dd2f6457f0d5eb01`
- representative capture package SHA-256:
  `cfeabae1cb4a96e46f5d6108269dfd1806cbfbc7265c4bcddbf58806aeb18241`
- representative evidence archive SHA-256:
  `a3df084c29eb0ec414cbe2f4035d599d71752af007c780d0daf5d1d7be998d6f`
- shared production/capture payload SHA-256 (297 entries):
  `1ba86dfd02413ee1b2eec6d0b39096f9f99bb79c3a9ffb460e936383c37e7b9c`

The production archive is `dist/anki_garden.ankiaddon`. Capture derivatives
cannot overwrite it and remain excluded from the distributable.

## Current source validation

The final source, documentation, and production package were validated on
2026-08-29:

- fast lane: 1,364 passed, 21 skipped, and 813 deselected;
- release-evidence lane: 800 passed, 13 skipped, and 1,385 deselected;
- explicit union: 2,164 passed and 34 skipped;
- focused package, asset-selection, and Retina checks: 26 passed and 13
  deselected;
- artwork audit: 9 backgrounds, 8 Garden Decoration assets, 60 plant images,
  and 19 UI images;
- Python compilation, capture-contract doctor, manifest/contact-sheet
  validation, ZIP integrity, source/archive parity, Markdown link checks, and
  `git diff --check`: passed; and
- deterministic production build: 298 files and 85,678,959 bytes, with SHA-256
  `1fbbaf58ce9cfcb1b9f6d3c8782f93fa4f699e40d5910798fd8bdee73c98b198`
  before and after rebuild.

## Local evidence retention

Only the newest full five-page contact-sheet directory is retained locally.
Superseded full and all representative contact-sheet directories were removed
after the current full set passed independent validation and visual inspection.
Raw capture runs, manifests, reports, lineage, evidence archives, the production
archive, source artwork, and mutable runtime user data were preserved.

## Remaining acceptance

The following gates remain open until separately run and recorded:

- human release approval of the current five-sheet full set;
- full-screen macOS interaction through the Garden and each nested dialog,
  including confirmation that no action switches Spaces or creates a stray
  top-level window;
- native Windows and Linux behavior;
- true OS 125%/150% and mixed-DPI behavior, forced colors, screen-reader,
  contrast, broader keyboard, and device-level visual acceptance; and
- a fresh exact-package capture if implementation or packaged assets change
  after the hashes recorded above.

Static tests, package parity, clean shutdown, or contact-sheet completeness do
not close these gates by themselves.
