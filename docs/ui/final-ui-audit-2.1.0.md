# Anki Garden 2.1.0 UI evidence

Status: automated v25 capture validation is complete; visual and native release
acceptance remain pending. Both retained reports have `quality_status` set to
`review-required` and `release_ready` set to `false`.

## Current acceptance contract

Capture contract v25 compiles the Qt-free surface registry into two profiles:

| Profile | Surfaces | Sheets | Evidence tier |
|---|---:|---:|---|
| `representative` | 15 | 2 | Preflight |
| `full` | 30 | 5 | Final-release automation |

The counts are generated observations rather than fixed acceptance constants.
Retired or behavioral-only IDs remain reserved, including the retired starter
confirmation and every watering-can capture. Both profiles use
`QT_SCALE_FACTOR=1.0`. Raw manifest-owned PNGs are the geometry authority;
contact sheets are presentation aids.

Detailed semantic, copy, text-fit, layout, scroll, and duplicate-view findings
remain visible review advisories. They are not silently normalized, and a valid
automated manifest is not human visual approval.

## Retained representative evidence

- Run: `build/ui-face-captures/representative/capture-sequence-20260828-080319`
- Manifest: `assembled/manifest.json`
- Contact sheets:
  `build/ui-face-captures/representative/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260828-080319`
- Evidence archive:
  `build/ui-face-captures/representative/anki-garden-ui-faces-20260828-080319.zip`
- Result: 15/15 surfaces, two sheets, 2 captured faces, 13 reused faces, no
  recapture requirement, valid surface/contact-sheet validation, and clean
  process shutdown.
- Review telemetry: three text-layout warning records and 13 audit advisories.

## Retained full evidence

- Run: `build/ui-face-captures/full/capture-sequence-20260828-080449`
- Manifest: `assembled/manifest.json`
- Contact sheets:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260828-080449`
- Evidence archive:
  `build/ui-face-captures/full/anki-garden-ui-faces-20260828-080449.zip`
- Result: 30/30 surfaces, five sheets, 2 captured faces, 28 reused faces, no
  recapture requirement, valid surface/contact-sheet validation, and clean
  process shutdown.
- Review telemetry: five text-layout warning records and 22 audit advisories.

The full report's automated release gate passed. Its overall release state is
still nonready because the retained advisories and manual acceptance boundaries
have not been signed off.

## Package binding

Both retained profiles used the same capture derivative:

- capture package SHA-256:
  `03a86d9f8a30088c25b2d7ce8291884989a9e7135c05f64a5080ac1b7dc354d1`
- production package SHA-256:
  `f8f962a8731ac79b9627a5260cd04588de4574b10eca98b8e7d172854d1bb86c`
- full evidence archive SHA-256:
  `d92c6ce6a986e360a746f79d863b74b030e21d63fe6a9b96ab70d198c391d1c6`
- representative evidence archive SHA-256:
  `4e346fd966b9c40b366d87be78fe8e48c3af555ebf9d42ae8c320bb90c5d0417`

The production archive is `dist/anki_garden.ankiaddon`. Capture derivatives
cannot overwrite it and remain excluded from the distributable.

## Current source validation

The post-cleanup source and documentation were validated on 2026-08-28:

- fast lane: 1,039 passed, 795 deselected;
- release-evidence lane: 782 passed, 13 skipped, 1,039 deselected;
- explicit union: 1,821 passed, 13 skipped;
- artwork audit: 9 backgrounds, 1 decoration, 60 plant images, 9 UI images,
  and 7 Weather images;
- Python compilation, manifest parsing, capture-contract doctor, representative
  and full plan generation, both retained-manifest validators, ZIP integrity,
  README relative-link targets, and `git diff --check`: passed; and
- deterministic production build: 277 files, 81,958,606 bytes, with 277/277
  source payloads byte-identical to the archive.

## Local evidence retention

The 2026-08-28 release cleanup retained the newest complete run, matching
evidence archive, and matching contact-sheet set for each profile. Superseded
legacy, partial, diagnostic, and complete capture output was removed at the
user's request. Source artwork, runtime user data, the virtual environment, and
the production archive were not part of that deletion.

## Remaining acceptance

The following gates remain open until separately run and recorded:

- human review and disposition of every retained visual advisory;
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
