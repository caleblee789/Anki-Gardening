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
  [capture-sequence-20260831-154002/assembled/manifest.json](../../build/ui-face-captures/representative/capture-sequence-20260831-154002/assembled/manifest.json)
- Full manifest:
  [capture-sequence-20260831-155312/assembled/manifest.json](../../build/ui-face-captures/full/capture-sequence-20260831-155312/assembled/manifest.json)
- Full capture report:
  [capture-sequence-20260831-155312/capture-report.json](../../build/ui-face-captures/full/capture-sequence-20260831-155312/capture-report.json)
- Five-sheet directory:
  `build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312`
- Contact-sheet index:
  [contact-sheet-set.json](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json)
- Evidence archive:
  [anki-garden-ui-faces-20260831-155312.zip](../../build/ui-face-captures/full/anki-garden-ui-faces-20260831-155312.zip)

The representative manifest is complete at 18/18 with SHA-256
`e9b55cb2cb4e073e90fddd8c54c3a01c795da617f3e2397de84adab4c0303121`.
The full manifest is complete at 34/34 with SHA-256
`acacad3f9df86139014993f4b35fec1302bd9128de6c909ab7cb1f7cfd3f6aae`.
The full report is valid, records no outstanding recapture, and has SHA-256
`5965b91ab7b4b32a5e3a40708ca9367330056348882bfae0a303962f709c6c9e`.
The five-page index is complete with SHA-256
`2e69c2bc1076b9d82a1273c02643457dc5e169c04b89697cb597c35ec9d15747`.

All 18 representative raws, all 34 full raws, and all five final sheets were
reviewed. The final Move Mode correction is present: current and destination
treatments use the intended mint hierarchy, and the planter contours follow
the full rendered planter shells rather than the former inner-soil ellipses.
No remaining user-facing contour defect was recorded.

That review is the documented Codex visual pass recorded in the separate
ledger. The generated sheet index intentionally retains `Automated checks
passed; visual review pending` because independent human review remains open;
the index was not mutated after generation to imply that acceptance.

## Package and archive binding

The evidence binds these exact artifacts:

| Artifact | Files | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Production `dist/anki_garden.ankiaddon` | 322 | 100,389,172 | `f782d6b58ddd682bc92cacea4f28de44caf481a7e2e1e39a1bb44d558dda8971` |
| Capture derivative | 334 | 100,781,416 | `c57848064ee03db9a84454df0a434b3bc68da857a197b2d392e4b135a8618afd` |
| Full evidence ZIP | n/a | 26,126,453 | `8094c23a051c2d5e49d96d4f4f118160b791a94f7cfe8bd5b691d12a1593b8d3` |

Production/capture shared-payload parity is byte-identical across 321 entries.
The shared-payload digest is
`848e953fc3dbeddae2bc6ed67ee7114710ce21e0c93002b8ec640be26816a964`.
The capture derivative adds only the capture capability and mode payload; it
does not replace or mutate the production archive.

## Economy validation boundary

The canonical public-engine parity artifact is identified by SHA-256
`64d2396a52852228b1e744e4bc92e2ce9633a0f6231fa3c9bb43433c73befe89`.
It is the authority for engine replay/parity; the UI consumes frozen economy
projections and committed results rather than reproducing prices, Growth,
reward, balance, project, or queue calculations.

The final 10,000-run balance report and its PDF are still pending return from
the external economy validation lane. They are not claimed as delivered by
this audit and must be added with their final paths and hashes when returned.

## Local automated validation

Exactly one complete pytest union was run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ag-ui-final \
./.venv/bin/python -m pytest -q -p no:cacheprovider -o addopts=''
```

It reported 2,311 passed, 35 skipped, and 3 failed. Each failure was corrected
in its nearest existing test node, and those three focused nodes were rerun
green. A second complete union was intentionally not run, so the focused
reruns must not be restated as a second all-green full suite. No new UI test
file was created.

The proportional non-GUI release gates are valid: Python compilation, asset
audit, catalog validation, production package build, ZIP integrity, capture
doctor, standalone manifest/contact-sheet validation, and `git diff --check`.
These checks do not replace the open acceptance gates below.

## Regeneration and review accounting

This candidate has one complete regeneration cycle. The accepted evidence was
assembled through dependency-closed targeted recapture and exact validated
reuse; the final `155312` sheet pass reused all 34 accepted surface records and
did not recapture unrelated UI. Earlier targeted native probes were incomplete
diagnostic iterations within the same correction cycle. They produced no final
sheet set and do not increment the complete regeneration-cycle count.

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
