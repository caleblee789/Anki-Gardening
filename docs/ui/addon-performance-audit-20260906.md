# Add-on performance audit — 2026-09-06

Reduced repeated reviewer rendering and collection lookup work while retaining the existing artwork, layout, controls, and state semantics. This extends the Garden navigation work documented in `garden-navigation-performance-20260906.md`.

## Changes and audit findings

- Reviewer plant art now reuses its three compact sizes and alpha-derived visible bounds. The pixel cache belongs to the widget, is capped at 2 MiB, and is cleared on artwork changes and disposal. Source pixmap identity, physical size, and device pixel ratio identify reusable images; current layout offsets and stage-specific shadows are still recomputed.
- Reviewer plant alternatives previously called the engine's linear `plant_story()` lookup for every stored plant, producing quadratic work as the collection grew. When reading the engine's own state, the projection now narrows the candidates to planted plants before confirming each with the engine. Older snapshots retain the previous confirmation path. Sorting, active-plant exclusion, Full Bloom exclusion, and missing-plant handling remain intact.
- Ordinary receipt thumbnails no longer perform an unused preview load before loading the same artwork for containment. Environment and normalized plant preview rendering remain unchanged. Measured warm thumbnail/scenery work was already small, so no additional shared image cache was introduced.
- Home/Overview injection, asset resolution, and normalized plant thumbnails already have revision/content-aware caches. Their invalidation and committed reward/storage paths were retained. This audit did not change saved data or reward calculations.

## Measurements

Local medians from saved baseline modules and the candidate in the same offscreen Qt process, using the installed Anki libraries at DPR 2. Reposition/update samples used a mounted native reviewer widget; collection selection used 50-, 500-, and 2,000-plant fixtures with six planted candidates. These are application-operation timings, not physical input-to-display latency or cross-machine guarantees.

| Operation | Baseline ms | Candidate ms |
| --- | ---: | ---: |
| Unchanged reviewer update | 55.180 | 1.164 |
| Reviewer reposition | 26.894 | 0.203 |
| Repeated plant-art sizing | 26.869 | 0.012 |
| Plant alternatives, 2,000 stored/planted plants | 70.181 | 0.246 |
| Full Bloom reviewer update | 25.583 | 1.318 |

The principal update samples use 10 repetitions, art sizing uses 20, and each collection size uses 5. Scenery and thumbnail timings are retained in the raw results; no material thumbnail speedup is claimed.

## Verification

- Existing reviewer, scene performance, Today’s cards, interaction, Session Summary, and sync-summary tests: **121 passed, 2 skipped**. The existing plant-choice test now also verifies an older snapshot with outdated planted flags.
- Existing live Qt layout tests: **3 passed**.
- **160 additional native Qt checks passed**: full viewport pixel parity at three sizes in expanded/collapsed and seed/young/Full Bloom/no-target states; all six plant stages at DPR 1, 1.5, and 2; compact-size and grounding-offset changes; changed source pixels; cache disposal/bounds; and every current UI catalog thumbnail at three sizes.
- Initial reviewer rendering and choices at 50, 500, and 2,000 plants also matched the baseline. Representative normal and Full Bloom native renders were inspected.
- No new persistent test suite was added. Temporary probes and source snapshots are retained with the evidence. The broad release suite and live collection/physical comfort acceptance were not run in this pass.

Evidence: `build/performance/addon-audit-20260906/`. `runtime-changes.patch` isolates this audit's runtime edits from the surrounding work in progress; `provenance.json` records source hashes. The probes compare the saved baseline with the workspace source, so verify those candidate hashes before rerunning them later. Existing unrelated edits remain in the working tree. No release archive, normal-profile installation, or publication was performed.
