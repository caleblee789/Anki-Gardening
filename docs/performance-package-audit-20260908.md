# Performance and package audit

The rebuilt add-on is **92.12 MiB**, down from **102.97 MiB**: **10.85 MiB / 10.53% smaller**. The baseline was built from the current working tree before this audit, including the existing UI work. The audit preserves active artwork, layout, controls, reward rules, and saved-state values.

| Package | Bytes | Entries |
| --- | ---: | ---: |
| Baseline | 107,971,694 | 273 |
| Optimized | 96,598,301 | 263 |

The installable result is [dist/anki_garden.ankiaddon](../dist/anki_garden.ankiaddon), SHA-256 `4dc24e569a73fb1a5371b7782df2111ea0fed05c5559aec4168a640660be0216`.

## Package findings

- Six Landmark images and four Mastery overlays contributed **8,631,206 compressed bytes** despite both features being disabled. Their Collection entries, rendering, and reward presentation are guarded by the existing release flags. Packaging now omits these manifest rows and images while disabled. Their source artwork, backend, and saved progress remain intact. Enabling either flag restores its artwork on the next build. Production and capture use the same filtered manifest.
- Seven newer reward icons were PNGs. Exact lossless WebP encodings save **2,740,121 compressed payload bytes**. Dimensions, every RGBA pixel, transparency, and relevant embedded metadata match. Asset identities remain unchanged; filenames and manifest checksums were updated. Current and historical standard Find presentation resolves these identities through the registry.
- Active plants, scenery, decorations, and trophy artwork remain packaged. No byte-identical duplicate image files were found. Build outputs, capture-only code, authoring assets, and dormant wide scenery layouts were already excluded.
- **54 legacy occlusion images, about 1.50 MiB, were retained.** The current bedless rendering path bypasses them, but renderer compatibility paths still reference them. Removing those references would expand the rendering contract beyond this conservative pass.

Only three runtime Python files changed relative to the frozen baseline: `models/state.py`, `storage.py`, and `ui/reviewer_hud_widget.py`. Every other shared archive payload except the asset manifest is byte-identical. All active non-UI manifest rows also match the baseline.

## Runtime improvements

Collapsed reward feedback no longer resolves, decodes, masks, and crops artwork that its renderer never displays. Captions, colors, event order, timing, the plant tile, and expanded artwork are unchanged. Offscreen Qt comparisons matched all six representative frame renders and a four-step reward sequence. A synthetic six-frame bundle dropped from **37.52 to 0.024 ms** median; single Full Bloom frame generation dropped from **1.338 to 0.002 ms**.

Persistence avoids a redundant deep copy immediately before synchronous JSON serialization and SQLite commit. Default detached snapshots and rollback behavior are preserved. The JSON copy still completes before the transaction. Eight alternating samples after warmup measured:

| Synthetic state serialization + commit | Before | After |
| --- | ---: | ---: |
| 12 plants | 0.545 ms | 0.264 ms |
| 500 plants | 12.670 ms | 5.216 ms |

Every compared payload matched exactly and the source state remained unchanged. These are component measurements, not end-to-end review latency guarantees.

## Validation and evidence

**190 unique existing checks passed, one skipped; no tests were added.** This covers persistence, rollback, reviewer behavior, package reproducibility, production/capture parity, and asset contracts. Existing asset checks were updated for the seven already-present icons and registered scenery building contours. Only failed asset checks were repeated after correction.

All **106 active catalog entries** resolved from the extracted final package. The seven converted icons passed **28 native Qt full-size/scaled pixel comparisons**. Final icon and reviewer source hashes match that evidence. Scoped compilation and `git diff --check` passed. Full live Anki, whole-add-on visual acceptance, and cross-platform QA were not run; this audit did not install into a normal profile or publish a release.

[Audit evidence](../build/performance/package-runtime-audit-20260908/audit-summary.json) includes the [package comparison](../build/performance/package-runtime-audit-20260908/package-comparison.json), [persistence measurements](../build/performance/package-runtime-audit-20260908/persistence-benchmark.json), [reviewer measurements](../build/performance/package-runtime-audit-20260908/ui/probe-results.json), test logs, hashes, and an isolated `audit-changes.patch`. The baseline source/archive, previous distribution, and optimized archive are preserved in the same directory.
