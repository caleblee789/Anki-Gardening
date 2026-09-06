# Combined Garden integration — 2026-09-06

This integration brings together all five UI lanes, the Garden/reviewer performance improvements, and the approved uncapped Find, Firefly, Prism, Today, and Mastery work. Anki Garden 2.2.0 remains an **unreleased candidate**.

## Public release hold

The approved progression plan requires zero all-ten-species finishes by day 30 in every protected tested scenario. Both the frozen capped baseline and the combined candidate fail that guardrail. The source integration does not waive it, change the tested odds or rewards, or approve public distribution.

| Protected scenario | Day-30 finishers, baseline → candidate |
| --- | --- |
| Fresh, 1,000 answers/day, Collection first | 7/25 → 25/25 |
| Fresh, 1,000 answers/day, Coin focused | 0/25 → 22/25 |
| Established, 1,000 answers/day, Collection first | 25/25 → 25/25 |
| Established, 1,000 answers/day, Coin focused | 25/25 → 25/25 |

The targeted 200-seed comparisons found 68/200 → 200/200 fresh Collection-first finishers and 0/200 → 173/200 fresh Coin-focused finishers. An uncapping-only comparison reproduces the acceleration. The normal paired audit covered 875 runs per version. Full per-seed results and reproducible commands are retained in `build/uncapped-progression-20260906-003030/`.

## Included interface changes

- Garden and onboarding: compact starter selection, clear placement/nurture steps, floating plant inspectors, continuous lawn artwork, grounded plant and decoration assets.
- Collection and Appearance: one species/plant detail panel, one preview and equipment workflow, and removal of the redundant other-bonuses section.
- Shop and supplies: consistent card spacing, complete effects, clear affordability and charge confirmation/receipt actions.
- Progress and Settings: cleaner Today, achievements, Coins, trophy presentation, settings drafts, and artwork diagnostics.
- Review and rewards: compact in-place reward sequencing; shared three-box totals; consistent discovery cards and rarity accents; pulse-only item glow; session details always visible; removed Today and next-card rows from the reviewer.
- Performance: short hover transitions, settled-scene idle behavior, bounded artwork caches, and reuse of unchanged collection/navigation content.

The README describes the actual current controls and reward displays. Historical lane reports and their immutable native evidence remain intact.

## Combined verification

Current contract: v29, **50 full surfaces in five grouped sheets**, with a 22-surface representative preflight. The removed Appearance bonus panel retains its reserved ID and is absent from the active inventory.

Evidence root: `build/final-integration-20260906/`.

The combined suite exercised 2,494 existing checks, with 38 environment-dependent skips and the separate comprehensive annual parity gate deselected. Its last three failures concerned the preserved source PNG living inside the runtime asset directory and stale documentation assertions. The PNG was moved intact to `artwork_source/backgrounds/verdant_twilight/`; all 12 affected asset/documentation checks then passed. The full annual parity gate remains unrun in this integration and is separate from the completed bounded pacing audit.

Integration also corrected capture containment bookkeeping for partially visible Collection cards, JSON-compatible welcome receipt serialization, and the Home readability floor for young plant artwork. Settings now describes the reviewer as showing plant progress and rewards, matching the removed Today bar. Existing placement assertions now measure rendered silhouettes and authored ground anchors instead of assuming equal image-canvas scale factors or symmetric roots. The full 5,760-scenario artwork layout matrix passed. The independent screenshot content check now examines the reviewer overlay’s verified pixel bounds, preserving the complete image digest and rejecting an empty HUD without mistaking the intentionally empty Anki workspace for missing content. All 67 affected existing capture checks passed. No new test files were created.

The continuous lawn uses a lossless WebP runtime encoding. PIL and Anki’s actual Qt decoder produce the same 1448 × 1086 RGBA pixels as the retained PNG master; the encoding saves 588,322 installed bytes. The final 115,329,175-byte archive remains within the existing 110 MiB budget. Generation and conversion provenance is retained beside the master.

The final-package 22-surface representative preflight and **50-surface full capture both passed** every independent capture and contact-sheet validator, with no capture, text-layout, or geometry errors or advisories. The full run refreshed 24 affected views and reused 26 exact compatible captures, preserving their immutable lineage. All 50 raw surfaces and five assembled sheets were visually inspected by Codex. This records visual review of the captured states, not human release approval.

Capture used Anki 26.8.1 on the primary Built-in Retina Display at 100% UI scale (2× device pixels), in fresh sync-disabled disposable profiles. The capture processes exited gracefully; the normal Anki process was not used.

[Open the complete contact-sheet handoff](../../build/final-integration-20260906/CONTACT-SHEETS.md). It links all five sheets, the raw manifest, capture report, ZIP, package parity, and visual-review records. The final full run is `capture-sequence-20260906-021539`; its capture ZIP SHA-256 is `ec207894c930a4c2ddf04bbb3e0c001f424011aa812a340276d949a89afd9682`.

The runtime and README integration is committed on main as `1ceca9e2375b342e465a9187f4e60952a5d695c7`. The frozen QA archive is `build/final-integration-20260906/candidate-final.ankiaddon`; its 332 production payloads match the source. Capture evidence and original artwork remain preserved without replacing historical reports.

Production-format QA archive SHA-256: `545f95deb3191103fae86a959aa54f5199d12a3e30c6d3bd8c6eeddde5dcb8a0`.

Capture derivative SHA-256: `eb2d19cb90337551b9246340dbf9a35ff11e91786b8d3a99ff663d134b4944b2`. All 331 shared payload entries are byte-identical; the capture harness is excluded from the production-format archive.

GitHub Actions was already unable to start jobs on main: its failure annotation reports failed account payments or a spending limit that needs attention. No billing setting was changed. Local tests and isolated native capture evidence are reported independently of hosted CI.
