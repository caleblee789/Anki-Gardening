# Continuous scenery backgrounds — 2026-09-06

All nine scenery themes now use dedicated 1448 × 1086 continuous Garden
paintings. Eight new images preserve each theme's palette, season, sky features,
Nursery, cottage, path and open planting area. Verdant Twilight's existing
painting is unchanged. The canonical background, native Garden background and
4:3 variant resolve to the same image, including scenery previews and fallback
background resolution.

All nine 1942 × 809 Home banners, all 60 plant sprites, normalized planting
geometry, landmark metadata and saved-state identifiers remain unchanged.

## Background-only package baseline

The background-only archive was **104,358,569 bytes
(99.52 MiB)** with **259 files**, below the existing 100 MiB cap.

SHA-256: `dc74a3c04cb7f030d2223d3ce394843e4d4764980956eb5e8bdef06077851c9a`.

| Package stage | Background images | Total files | Archive size |
| --- | ---: | ---: | ---: |
| Before layout cleanup | 145 | 332 | 115,329,175 bytes (109.99 MiB) |
| After removing unused 16:9 layouts | 97 | 284 | 100,330,257 bytes (95.68 MiB) |
| Continuous backgrounds and final cleanup | 72 | 259 | 104,358,569 bytes (99.52 MiB) |

This step removes nine older 4:3 paintings and 24 authoring mask PNGs from the
package, adds eight continuous paintings, and retains the existing continuous
Verdant Twilight painting. The final 72 background images are nine continuous
Garden paintings, nine Home banners, and 54 occlusion overlays used by fallback
rendering. Source artwork and source catalog references remain in the repository.

The new paintings add 4,028,312 bytes over the prior trimmed package. The final
archive is 10,970,606 bytes smaller than the original package. The two largest
contributors remain plants (47,980,046 compressed payload bytes) and backgrounds
(33,454,300 compressed payload bytes).

## Validation and evidence

The existing asset audit passed. The seven relevant package, asset selection,
surface profile, responsive Garden, Home and migration test files passed:
**284 passed, 10 environment-dependent skips**. No new test files were added.

The final production archive is byte-identical to the production archive built
by the tests. Its capture derivative passed the existing production-payload
parity validator. All PNG masters and their lossless WebPs have identical RGBA
pixels under Pillow. Every pre-existing background and plant source file still
matches its baseline hash. All nine Home metadata records and normalized
geometry records match the baseline.

The independent plant audit found all **60 of 60** packaged plant images used:
ten available species with six growth stages each. The filename stage `rare`
is the current Full Bloom stage and must remain packaged.

Codex reviewed all eight generated images, the nine-image overview and all four
before/after comparison sheets. The planting ground is continuous and the
individual themes remain recognizable.

The Mac was subsequently unlocked. The [comprehensive UI review](comprehensive-ui-review-20260906.md)
completed the current 50-surface native Anki contract, including Garden,
Appearance previews, Home, and all Shop scenery rows. A supplemental production
Qt artwork audit reviewed all nine sceneries, 720 thumbnails, and 9,720 plant
placements with no remaining crop or placement warnings. Those renderer audits
are separate from native Anki window captures; the earlier proposed nine-theme
empty/populated/Home window matrix was not run as a second redundant inventory.

The final combined UI/background package is **104,361,845 bytes (99.53 MiB)**,
with 259 entries and SHA-256
`43639b9a539a98d4630aa637451bc500a5276d20638f1348d44c97b351556a6d`.
The size table above records the earlier background-only stages.

- [Artwork overview](../../build/continuous-backgrounds-20260906-124638/review/all-backgrounds.png)
- [Review index and detailed package evidence](../../build/continuous-backgrounds-20260906-124638/REVIEW.md)
- [Retained PNG masters and generation provenance](../../artwork_source/backgrounds/continuous/README.md)

This is a local implementation and package rebuild. No release was published.
