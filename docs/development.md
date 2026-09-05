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

# Package, capture, artwork, and live-Qt release evidence:
./.venv/bin/pytest -q -o addopts='' -m release_evidence

# Explicit union of both lanes:
./.venv/bin/pytest -q -o addopts=''

# Non-mutating v27 capture diagnostics and registry inspection:
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

The runtime target is Anki 25.07 through 26.08. Release acceptance installs the exact rebuilt archive into a separately keyed, disposable Anki 26.08 base/profile with sync disabled.

The full product and QA contracts are in [`feature-evidence-matrix.md`](feature-evidence-matrix.md), [`ui/data_contracts.md`](ui/data_contracts.md), and [`ui/state_scenarios.md`](ui/state_scenarios.md).

The [UI review report](ui/release-quality-20260904.md) records the latest screenshots and verification.
