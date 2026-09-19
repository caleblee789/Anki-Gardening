# Development guide

Commands below run from the repository root. For everyday use, see the [README](../README.md).

## Install from source

Copy or symlink `ankigarden/` into Anki’s `addons21` directory, then restart Anki. Open the Garden from its Deck Browser or Overview card. Open settings from **Caleb M. Add-ons Settings → Anki Garden settings**.

Build the deterministic production package with:

```bash
./.venv/bin/python scripts/package_addon.py --production
```

The artifact is atomically validated and written to
`dist/anki_garden.ankiaddon`. It excludes the capture harness and fixes all
development-mutation capabilities off. The complete `ankigarden/capture/`
subtree is capture-only. A UI-capture package must be requested explicitly and
written to a different path:

```bash
./.venv/bin/python scripts/package_addon.py --capture \
  --output build/ui-face-captures/anki_garden_capture.ankiaddon
```

Capture builds cannot overwrite the production artifact.

## Development checks

```bash
# Default suite:
./.venv/bin/pytest -q

# Package, capture, artwork, and required Qt release evidence (Qt environment):
python -m pytest -q -o addopts='' -m release_evidence --require-qt

# Explicit union of both lanes:
./.venv/bin/pytest -q -o addopts=''

# Non-mutating v29 capture diagnostics and registry inspection:
./.venv/bin/python scripts/capture_sequence.py --doctor
./.venv/bin/python scripts/capture_sequence.py --list-surfaces
./.venv/bin/python scripts/capture_sequence.py --plan-only --profile representative

# Incremental representative preflight, full release capture, or isolated shutdown gate:
./.venv/bin/python scripts/capture_sequence.py --profile representative --inactivity-timeout 240
./.venv/bin/python scripts/capture_sequence.py --profile full --inactivity-timeout 240
./.venv/bin/python scripts/capture_sequence.py --gate-only

PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-pycache ./.venv/bin/python -m compileall -q ankigarden scripts tests
./.venv/bin/python scripts/audit_assets.py
./.venv/bin/python scripts/package_addon.py --production
python3 -m zipfile -t dist/anki_garden.ankiaddon
git diff --check
```

### Optional runtime performance tracing

The production package includes a bounded timing recorder that is disabled by
default and never changes learner behavior. Before launching a sync-disabled
disposable Anki profile, set both variables below to collect at most 256 samples
per operation and write median, p95, and maximum timings at clean shutdown:

```bash
ANKI_GARDEN_PERF_TRACE=1
ANKI_GARDEN_PERF_OUTPUT=/absolute/path/runtime.json
```

Summarize one run, or compare it with an earlier trace, from the repository
root:

```bash
./.venv/bin/python scripts/profile_runtime.py /absolute/path/runtime.json
./.venv/bin/python scripts/profile_runtime.py /absolute/path/runtime.json \
  --baseline /absolute/path/baseline.json
```

The recorder also measures `dashboard.open` (maintenance, construction, and
presentation) and `dialog.observe-content` (coalesced observer installation).
Compare first opening separately from startup so shifted work is not mistaken
for an overall speedup. Keep
cold launches and warm navigation in separate samples, and keep timing
thresholds out of unit tests.

To search for smaller artwork encodings without changing the runtime assets:

```bash
./.venv/bin/python scripts/convert_runtime_assets_to_lossless_webp.py \
  --compare-output /absolute/path/new-lossless-comparison --workers 4
```

The destination must be new and outside `ankigarden/`. Each candidate preserves
full decoded RGBA bytes, dimensions, and ICC/EXIF/XMP metadata. The report
compares each image's ZIP contribution as well as its installed size. Original
bytes win ties; larger installed images are never selected. Verify staged
winners with the supported Anki Qt decoder before applying the report:

```bash
./.venv/bin/python scripts/convert_runtime_assets_to_lossless_webp.py \
  --apply-comparison /absolute/path/new-lossless-comparison/comparison.json
```

Application rechecks the manifest, original hashes, staged hashes, pixels,
metadata, and size savings before replacing any source asset. Preserve a
baseline checkout and production archive before applying an optimization.
For an isolated candidate, call `scripts.package_addon.build(output=...)`;
the production CLI intentionally targets the normal distribution path.

Use the [UI surface inventory](ui-surface-inventory.md) for active capture
profiles, sheet assignments, execution order, and handoff requirements.

Capture contract and orchestration tests are deliberately small and Qt-free;
the real exact-package Qt/WebView, shutdown, manifest, and contact-sheet
proof is produced by the repository capture command instead of simulated by a
large pytest matrix. The explicit union is the complete local check. The default suite currently
includes the annual 66-scenario economy replay. For a UI-only pass, the recorded
scoped command excludes that unrelated simulation:

```bash
./.venv/bin/pytest -q -k 'not test_complete_release_manifest_matches_the_real_engine'
```

CI gives the fast lane a
120-second outer timeout and each independently scheduled release-evidence
shard a 60-second timeout.

The Qt release command requires a Python environment with real Anki/PyQt6
bindings, Pillow, pytest, ReportLab, and pypdf. CI uses Python 3.13 and
`aqt[qt]==26.8.1` for its Qt shards. `--require-qt` stops immediately if those
bindings are missing and turns skipped release-evidence cases into failures.
The ordinary unit environment can still skip unavailable native checks; those
skips never establish native acceptance. CI retains JUnit results and dependency
versions for each release shard.

### Freeze and check release readiness

Current package identity, results, and pending work belong in the
[release status](README.md#release-status). Native journeys are maintained in
[functional acceptance](feature-evidence-matrix.md#native-functional-journeys).

Keep an immutable production archive, source identity, JUnit XML, validation logs,
native results, and open acceptance gates in one evidence directory. The release
record uses schema version 1, `source` from
`scripts.check_release_readiness.source_identity()`, a `package` artifact, and
the named `REQUIRED_GATES` from that module. Artifact records contain paths
relative to the evidence directory and SHA-256 hashes. Passing gates require
retained evidence; native and approval gates also carry the exact package hash.
Native endpoint gates record `platform: macOS` and their actual Anki version.
The required native endpoint is Anki 26.08.1. Anki 25.07 native acceptance is
unverified and is no longer a release blocker; this does not change the declared
compatibility range or establish native support for that version.
Leave human review pending until the release owner actually approves it.

```bash
# Validate recorded source/artifact integrity while acceptance is in progress:
./.venv/bin/python scripts/check_release_readiness.py /path/to/readiness.json --allow-pending
# Final gate: exits unsuccessfully while any required acceptance is incomplete:
./.venv/bin/python scripts/check_release_readiness.py /path/to/readiness.json
```

The gate checks current source and production payload parity, required JUnit
results, artifact hashes, native version/package bindings, and pending approvals.
It never treats an old scan or a capture completion marker as release approval.
Changing source requires refreshing affected evidence and its source identity.

Capture metadata uses the current JSON contract. Executable legacy scenario
metadata is rejected; its images must be recaptured. The refinement handoff
packager permits input files within the selected report directory. Use repeated
`--evidence-root /explicit/input/directory` arguments for sibling capture sets
or the production package directory. Snapshot paths and sheet filenames are
checked before output is created; report hashes establish consistency, not
trusted authorship. The balance PDF treats imported fields as literal text and
accepts no image-resource inputs.

## Shared UI styling

[`ankigarden/ui/theme.py`](../ankigarden/ui/theme.py) owns shared presentation
decisions and stays importable without Qt. Extend it before introducing another
palette or styling system. Existing widgets continue to own their layouts,
callbacks, state, and stylesheet application points.

| Shared definition | Current consumers |
| --- | --- |
| `GARDEN_THEME` control border and destructive-state roles | Push-button and tool-button stylesheet generators; Settings select hover border |
| `BUTTON_DEFAULT_HORIZONTAL_PADDING_PX`, `BUTTON_QSS_HORIZONTAL_PADDING`, `BUTTON_BORDER_WIDTH_PX` | Existing button generators, including compact-row, banner, secondary, primary, and onboarding selectors |
| `TEXT_ROLE_TOKENS` and `text_style()` | Dialog body/subtitle/caption/badge rules; starter and receipt card titles; Settings, Shop, and Move headings; decoration inspector text; button label metrics |
| `PLANT_DETAIL_TITLE_STYLE` | Plant Story heading and Progress plant-detail heading |
| `SECTION_PANEL_RADIUS_PX` and `raised_section_panel_style()` | Section/stat-summary, progress-row, appearance-card, and Settings control panels |
| `bind_palette_colors()` | Native dialog legacy-palette wrapper and Home WebView CSS initialization, with separate renderer-owned alias maps |
| `DIALOG_LAYOUT_METRICS` in `dialog_foundations.py` | Existing dialog layout defaults; layout metrics remain separate from QSS declarations |

`text_style(role)` emits only font size and weight. Use
`include_weight=False` where the current widget inherits its weight. It does
not set color, family, letter spacing, line height, minimum height, properties,
or repolishing. `apply_text_role()` still has its existing geometry semantics;
substituting it for a local font declaration can change wrapping and sizing.

Preserve these intentional variants and local exceptions:

- QSS padding for secondary/primary/onboarding buttons is 14/16/16 px; their
  existing `horizontalPadding` metadata remains 12 px. Tool-button alignment,
  selectors, and supported variants also retain their own contract.
- Raised section panels use 10 px corners; opt-in semantic cards use 8 px.
  Catalogue, stage-art, receipt, popover, and HUD shapes remain independent.
- Plant-detail titles remain 19 px/600; legacy dialog titles remain 20 px/600,
  separate from the screen-title role's 20 px/650.
- Compact receipt labels remain 11 px. Reviewer/receipt sizing, counters,
  animations, and specialized type treatments do not inherit main-window sizes.
- The existing spacing enum and string lookup have different values for some
  names. Do not interchange or normalize them during a styling extraction.
- Legacy palette aliases are ordered substitutions, including existing
  cascades. Compare the resolved styles, not just the literals in source.
  Home CSS is bound when its module loads; this adds no runtime theme switching.

Reuse a role when the decisions should change together. Keep a named variant or
commented local exception when they should remain independent, even if today's
values match. Never fill an inherited property simply to complete a token, move
styles higher in the widget tree, or route behavior through a styling helper.
Artwork coordinates, animation parameters, and one-off responsive measurements
remain local. The foundation tests check declaration boundaries, control-token
consumption, and ordered palette binding; they do not ban literals repo-wide.

See the [styling refactor validation record](ui/styling-foundation-refactor-20260912.md)
for the immutable baseline, candidate, captures, and retained limitations.

For product contracts and dated validation reports, use the
[documentation index](README.md).
