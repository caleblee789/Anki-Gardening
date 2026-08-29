# Anki Garden 2.1.0 UI evidence

Status: the current full v25 capture is complete and its five contact sheets
have been visually inspected for obvious clipping, overlap, and acquisition
errors. The generated report intentionally remains `review-required` with
`release_ready: false`; native and platform release acceptance remain separate
gates.

## Current acceptance contract

Capture contract v25 compiles the Qt-free surface registry into two profiles:

| Profile | Surfaces | Sheets | Evidence tier |
|---|---:|---:|---|
| `representative` | 17 | 2 | Preflight |
| `full` | 33 | 5 | Final-release automation |

The counts are generated observations rather than fixed acceptance constants.
Retired or behavioral-only IDs remain reserved, including the retired starter
confirmation and every watering-can capture. Both profiles use
`QT_SCALE_FACTOR=1.0`. Raw manifest-owned PNGs are the geometry authority;
contact sheets are presentation aids.

Detailed semantic, copy, text-fit, layout, scroll, and duplicate-view findings
remain visible review advisories. They are not silently normalized, and a valid
automated manifest or agent visual pass is not human release approval.

## Current full evidence

- Fresh acquisition run:
  `build/ui-face-captures/full/capture-sequence-20260829-020658`
- Final sheet run:
  `build/ui-face-captures/full/capture-sequence-20260829-021235`
- Manifest: `assembled/manifest.json` in the final sheet run
- Contact sheets:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260829-021235`
- Contact-sheet index: `contact-sheet-set.json` in that directory
- Evidence archive:
  `build/ui-face-captures/full/anki-garden-ui-faces-20260829-021235.zip`
- Result: the fresh-baseline run captured 33/33 surfaces with zero reused
  faces. The final run reused only that explicitly supplied fresh manifest and
  rendered five sheets, with valid surface/contact-sheet validation,
  responsive stability, fixture validation, dialog-scroll audit, and clean
  process shutdown.
- Review telemetry: zero capture failures, zero capture advisories, zero
  release-validation advisories, and zero text-layout warnings.
- Visual disposition: all five sheets inspected; the Home Growth meter is
  contained below its copy without clipping or scrollbar-like overflow, and the
  six garden beds retain their intended non-overlapping layout.

The full report's automated release gate passed. Its overall release state
remains nonready because manual native and platform acceptance have not been
signed off.

## Representative evidence boundary

The current representative preflight is
`build/ui-face-captures/representative/capture-sequence-20260829-014916`.
It contains 17/17 surfaces across two valid contact sheets, with no issues,
advisories, text-layout warnings, or recapture requests and with clean process
shutdown. Surface 13 was freshly captured after the final HUD and acceptance
repairs; the other 16 surfaces were reused only through exact compatible
per-surface lineage. The resulting assembled set is bound to the same production
and capture package hashes as the current full evidence.

## Package binding

The current full evidence binds these exact artifacts:

- capture-contract digest:
  `c666e2661b805f1240b98c41a1fbb56ffa58c30491bd298ec973be558f1d17e2`
- capture package SHA-256:
  `10adcb80faa4aa96632bdff987c6a38d204adcde92a3e81ac30f7843a81ff07d`
- production package SHA-256:
  `5a8652e8fead1b623813dcd99776ac6e05bc3e0755dca146431a075b5351fac5`
- full evidence archive SHA-256:
  `5a6c0334b6e03e54069fd40b35ab4e0513aa9e9d71f81fd1c1568054da855b1c`
- representative evidence archive SHA-256:
  `4650bb0c62802a072418adc3f069a759832eac70c5614f4f5560fab85219b39c`
- shared production/capture payload SHA-256 (283 entries):
  `79cb45c05f59bc737fec65090b876c23e71e63f1fe4bdd4ca5cfa68f98b0710e`

The production archive is `dist/anki_garden.ankiaddon`. Capture derivatives
cannot overwrite it and remain excluded from the distributable.

## Current source validation

The final source, documentation, and package were validated on 2026-08-29:

- fast lane: 1,233 passed, 19 skipped, and 811 deselected;
- release-evidence lane: 798 passed, 13 skipped, and 1,252 deselected;
- explicit union: 2,031 passed and 32 skipped;
- focused Home, planter, reviewer-HUD, Session Summary, capture-contract, and
  visual-acceptance tests: 357 passed and 6 skipped;
- artwork audit: 9 backgrounds, 1 decoration, 8 Garden Features, 60 plant
  images, and 10 UI images;
- Python compilation, manifest parsing, capture-contract doctor, ZIP integrity,
  source/archive parity, and `git diff --check`:
  passed; and
- deterministic production build: 284 files and 85,302,586 bytes, with SHA-256
  `5a8652e8fead1b623813dcd99776ac6e05bc3e0755dca146431a075b5351fac5`
  before and after rebuild.

## Local evidence retention

The capture runner preserves retained evidence according to its profile policy.
Historical capture output was not manually overwritten or deleted. Source
artwork, runtime user data, the virtual environment, and the production archive
were not part of evidence pruning.

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
