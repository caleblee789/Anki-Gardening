# Anki Garden 2.2.0 UI evidence

Status: the combined Anki Garden 2.2.0 candidate has a valid v26
representative preflight, a valid 34-surface final manifest, five validated
contact sheets, exact production/capture payload parity, and complete visual
review of the final raw PNGs and sheets. The authoritative report intentionally
remains `quality_status: review-required` with `release_ready: false`.
Automated and Codex visual review are evidence, not independent human, native
platform, accessibility, or device release approval.

## Acceptance contract

Capture contract v26 remains the checked-in UI authority:

| Profile | Surfaces | Sheets | Evidence tier |
| --- | ---: | ---: | --- |
| `representative` | 18 | 2 | Preflight |
| `full` | 34 | 5 | Final-release automation |

Both profiles use the production 2.2.0 package and canonical 100% capture
scale. Manifest-owned raw PNGs are the geometry authority; contact sheets are
indexed presentation aids. The combined economy boundary is state schema 27,
reward-ledger schema 3, balance-report schema 2, and asset-manifest schema 3.
The validated economy catalog digest is
`93bd87a24d73922ed42423c7dceb98aa08c1ab58cb251bfca2d65350a73754c7`.

## Final evidence

- Representative manifest:
  [capture-sequence-20260901-002619/assembled/manifest.json](../../build/ui-face-captures/representative/capture-sequence-20260901-002619/assembled/manifest.json)
- Representative capture report:
  [capture-sequence-20260901-002619/capture-report.json](../../build/ui-face-captures/representative/capture-sequence-20260901-002619/capture-report.json)
- Representative two-sheet index:
  [contact-sheet-set.json](../../build/ui-face-captures/representative/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260901-002619/contact-sheet-set.json)
- Representative evidence archive:
  [anki-garden-ui-faces-20260901-002619.zip](../../build/ui-face-captures/representative/anki-garden-ui-faces-20260901-002619.zip)
- Full manifest:
  [capture-sequence-20260901-002050/assembled/manifest.json](../../build/ui-face-captures/full/capture-sequence-20260901-002050/assembled/manifest.json)
- Full capture report:
  [capture-sequence-20260901-002050/capture-report.json](../../build/ui-face-captures/full/capture-sequence-20260901-002050/capture-report.json)
- Five-sheet directory:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260901-002050`
- Contact-sheet index:
  [contact-sheet-set.json](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260901-002050/contact-sheet-set.json)
- Evidence archive:
  [anki-garden-ui-faces-20260901-002050.zip](../../build/ui-face-captures/full/anki-garden-ui-faces-20260901-002050.zip)

The full final-release manifest is complete at 34/34 with SHA-256
`6f8e4fc7f222693572165a2680833c87859b196230dfc9d07f128da226e131e7`.
Every full surface was freshly captured in this run (`captured_faces` contains
all 34 surfaces and `reused_faces` is empty). The full report is valid, records
no audit advisory or outstanding recapture, and has SHA-256
`42412002746d602e55e6fe31101ec27dd3f000ec6a525bab61043449e08d79aa`.
The five-page index is complete with SHA-256
`0292d4e775510b7892df6c5cea21cc732fb39a43d41c8cc6e00b5f760ecb3952`.

The representative manifest is complete at 18/18 with SHA-256
`bc430eb2056137a5a461400f29410f290ee859358f67f6ddec9bf9f0d72b25c1`.
It was assembled only from the exact final full manifest: `captured_faces` is
empty and all 18 representative surfaces are recorded in `reused_faces`. Its
report SHA-256 is
`1c6e2d6724b483dd6a8bb41ba03d07b9e1467eb91160c09a636aa7846ad04b56`,
and its two-page index SHA-256 is
`6f77fe969db7f019d45745ba823f7edb5c13c4654b446869523cc16d296669a4`.

All 34 full manifest-owned raw PNGs, all five full sheets, and both
representative sheets were reviewed at original resolution. No gross clipping,
overlap, missing artwork, stale copy, or alignment defect was recorded. The
review included the full Garden header, Move Mode, Collection tabs and Species
Overview states, Nursery Bed 3 copy, Settings, Reviewer HUD, Session Summary,
Sync Rewards, and Growth Charge confirmation/success states.

That review is the documented Codex visual pass recorded in the separate
ledger. The generated sheet index intentionally retains `Automated checks
passed; visual review pending` because independent human review remains open;
the index was not mutated after generation to imply that acceptance.

## Package and archive binding

The evidence binds these exact artifacts:

| Artifact | Files | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Production `dist/anki_garden.ankiaddon` | 322 | 100,410,805 | `2c6f06f675110bbaf4ae99581311ef3e580c6e21ca56046d6ea1e4f067335468` |
| Capture derivative | 334 | 100,811,192 | `d8165d22b1670d185a3ce292e55ee7f34e7740082e948152af41eed0b4e9d1f2` |
| Full evidence ZIP | n/a | 41,952,947 | `26a3a6de38df942f79c2ef02855dd1feaa3baf83723dadb2c5c9b44337b6e02a` |
| Representative evidence ZIP | n/a | 14,079,522 | `a6d6a53d28bdce373ae4c5623eec564df37250d8c5a6156080b4c0907280d052` |

Production/capture shared-payload parity is byte-identical across 321 entries.
The shared-payload digest is
`db3515bc22cbd0b931be9f579ebf47c0cc6b7e1e2b7e25b4cc61cdfe6e0834f8`.
The capture derivative adds only the capture capability and mode payload; it
does not replace or mutate the production archive.

The capture contract digest is
`bfe80c845b4f18619de748603f2d4eb8e3133c75019303623fc7d01d466856ce`;
the full environment, evidence-schema, and scenario-contract digests are
`3b365abc854753dc049378e8f534c7a6afc32f6d6dbd9e3a149c5251d4ff1bb7`,
`79b824fe249b0b3fa31a4efae44afaa73590efc95685dfcf8ab79fa5c90b2091`,
and `1a315dbc76925cad61a021cb3193a898f9afb50b00801b0775cff72e674c9d90`.

## Economy validation boundary

The canonical public-engine parity artifact is identified by SHA-256
`64d2396a52852228b1e744e4bc92e2ce9633a0f6231fa3c9bb43433c73befe89`.
It is the authority for engine replay/parity; the UI consumes frozen economy
projections and committed results rather than reproducing prices, Growth,
reward, balance, project, or queue calculations.

The tracked
`output/pdf/anki-garden-economy-progression-balance-analysis.pdf` is retained
as an older 2026-08-29 artifact (136,824 bytes; SHA-256
`da17fe13e600f18397bd8f5ff7e22e627f14cb6e995bc371c53aaf3c4e382468`).
No matching frozen input bundle establishes it as the final return for this
integrated candidate. Receipt and audit of the final 10,000-run balance return
therefore remain open and are not claimed by this UI audit.

## Local automated validation

The complete non-heavy pytest union was run with canonical repository options
and reported 2,395 passed, 37 skipped, and 1 deselected. The separately gated
heavy public-engine/package parity test passed in 1,346.16 seconds.

```bash
PYTHONPYCACHEPREFIX=/private/tmp/<task> \
./.venv/bin/python -m pytest -q -p no:cacheprovider -o addopts='' \
  --ignore=tests/test_public_engine_package_parity.py

PYTHONPYCACHEPREFIX=/private/tmp/<task> \
./.venv/bin/python -m pytest -q -p no:cacheprovider -o addopts='' \
  tests/test_public_engine_package_parity.py
```

After native diagnostic fixes, the focused static and capture contracts were
rerun green: 100 passed for the combined header/Collection repair set, 95
passed with 2 skipped and 10 deselected for the Species/Bed set, 88 passed with
19 deselected for reviewer-settle and Species outer geometry, and 67 passed
with 7 deselected for the final Species close-control contract. The skips are
isolated Qt tests unavailable outside Anki, not failures.

The proportional non-GUI release gates are valid: Python compilation, asset
audit, catalog validation, production package build, ZIP integrity, capture
doctor, standalone manifest/contact-sheet validation, and `git diff --check`.
These checks do not replace the open acceptance gates below.

## Regeneration and review accounting

This candidate has one accepted complete full regeneration cycle. The final
`002050` run freshly acquired all 34 surfaces without reuse. Earlier targeted
native probes were diagnostic iterations and are superseded. The subsequent
`002619` representative preflight was deliberately assembled through explicit
exact reuse from the accepted full manifest; no older evidence set was
considered.

The final review covered every manifest-owned raw PNG and every generated
sheet, including cross-surface terminology, artwork identity, arithmetic,
button hierarchy, mint/gold semantics, dialog geometry, clipping, scrolling,
and the final Move Mode planter contours. This is a documented visual-evidence
review, not independent human release approval.

## Remaining acceptance

The following gates remain open:

- receipt and audit of the final 10,000-run balance report and PDF;
- independent human release approval of the current five-sheet set;
- broader native macOS interaction, including full-screen and Space behavior;
- native Windows and Linux acceptance;
- true OS 125%/150% and mixed-DPI behavior;
- broader keyboard, forced-colors, screen-reader, and contrast review; and
- device-level acceptance.

Any implementation, packaged asset, catalog, or manifest change after the
hashes above invalidates this evidence and requires proportionate rebuilding
and recapture. Until every separate acceptance gate is closed, the combined
candidate remains `quality_status: review-required`, `release_ready: false`,
and unpublished.
