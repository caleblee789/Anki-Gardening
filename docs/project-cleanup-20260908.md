# Project cleanup — 2026-09-08

The user authorized retiring superseded local build output to recover disk space,
while preserving the main add-on package, current evidence, canonical artwork,
and active work. This explicitly expanded the initial policy that retained every
incomplete capture attempt.

## Result

- Removed **76,769 files**, totaling **113,829,032,113 bytes** of old output,
  duplicate packages, and disposable metadata across both cleanup passes.
- The expanded pass increased available disk space by **112,260,079,616 bytes**.
  The build directory decreased from approximately **116 GiB to 11 GiB**.
- Preserved **16,721 diagnostic records** in a **1,435,712,985-byte** compressed
  archive. Every archived member was read back and checked against its SHA-256.
- Preserved runtime code, tests, scripts, canonical artwork and source masters,
  disabled-feature artwork, authoring inputs referenced by provenance, user
  data, current performance/progression audits, and the active native QA work.
- Preserved the newest three validated full capture sets, one older set needed
  by their recorded lineage, and the sole validated representative set. Their
  original manifests, packages, images, contact sheets, and archives remain.
  Older failed attempts and superseded output were retired under the expanded
  authorization. Automatic capture retention behavior was not changed.

Historical documents may still identify retired local image or package paths.
Those records describe earlier candidates; the diagnostic archive preserves
their text and metadata, not the retired binary images and packages.

## Package and source protection

The pending integration and sync fixes were committed separately as `c653b5a`.
The local reference `backup/pre-cleanup-20260908-215731` preserves that snapshot,
including the two previously unpushed commits. Merge validation used a separate
Git worktree because an active QA task was editing the shared dashboard file.
That task's ongoing changes were preserved independently.

Across the expanded cleanup, **1,044 protected source/package files** retained
their hashes. The 267-entry production archive remained byte-identical:

```text
SHA-256: 05b807b7ce23550001b8dc250325d314c0f3ce0d54a0bfd19b4201cb239e4a0d
Bytes:   96,602,342
```

No runtime artwork was deleted: all 266 artwork files are referenced by the
source manifest. The production builder continues to select the active asset
set and exclude dormant/authoring-only package content.

## Validation

- Frozen candidate: **2,556 passed, 58 skipped, 1 deselected** across the existing
  test lanes. The deselected test is the long annual release-parity replay;
  this cleanup does not certify that separate release gate.
- Focused startup, history, sync, reviewer, package, resolver, and capture
  checks: **197 passed**.
- Asset audit, ZIP integrity, deterministic source/archive parity, and retained
  capture validation passed. No new tests were added.
- GitHub Actions was unable to start on the existing main branch because the
  account's payments or spending limit require attention. Local validation is
  recorded separately from hosted CI.

## Local audit and diagnostic recovery

The ignored evidence directory is
`build/project-cleanup-20260908-215731/`. It contains the initial and expanded
deletion inventories, per-file hashes, deletion journals, protected-source
verification, package identities, and test logs.

`retired-build-diagnostics.tar.gz` contains the original repository-relative
names of the retired diagnostic records. Inspect or extract selected records
into a separate temporary directory when investigating historical work. The
diagnostic archive is not a backup of the retired binary output.
