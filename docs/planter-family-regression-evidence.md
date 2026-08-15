# Planter Family Regression Evidence

Implemented and re-audited on 2026-08-12 against the immutable geometry in
`docs/planter-family-geometry-baseline.md`.

## Corrected rendering contract

All six fixed garden slots draw one `storybook_stone_planter_v1` family:

- slots 0-1 use the shallow, horizontally compressed back planter;
- slots 2-3 use the medium planter;
- slots 4-5 use the largest planter and deepest front wall.

The earlier doubled-bed result had two independent causes. The original soil
beds were painted into every scenery bitmap, and the Qt renderer still drew a
legacy combined occlusion plate before drawing the new planter sprites. The
correction removes both sources instead of covering them:

- nine scenery themes x three responsive variants now use 27 approved
  `bedless_v1` background masters;
- the Qt renderer fail-closes the planter family unless the background declares
  `bedless_v1`, then suppresses every legacy surface-occlusion path;
- the Home renderer uses the same contract and never emits legacy combined,
  rear, or front bed layers while the planter family is active;
- each band renders planter base, unchanged plant layer, then planter
  foreground rim.

The manifest keeps the existing six bed IDs and all eight scenery reskins
inherit the one global family through their existing `placement_ref`. No
per-bed preference or saved-state field was added.

## Plant geometry comparison

`scripts/render_planter_geometry_regression.py` renders an identical six-stage
fixture before and after the artwork change at 75%, 100%, 125%, and 150%. For
every slot it records the bed ID, plant assignment, ground anchor, scale,
soil-contact transform origin, z-index, draw rectangle, visible rectangle,
plant hitbox and center, label anchor, information-card anchor, bed footprint,
and deterministic render trace.

`build/planter-geometry-regression/before-vs-after/comparison.json` reports:

- logical geometry identical: `true`;
- 75%: 0 changed plant pixels, maximum channel difference 0;
- 100%: 0 changed plant pixels, maximum channel difference 0;
- 125%: 0 changed plant pixels, maximum channel difference 0;
- 150%: 0 changed plant pixels, maximum channel difference 0.

The comparison includes transparent plant overlays and plant-only difference
images. The planter paths and draw boxes never feed plant anchors, scale,
hitboxes, labels, or assignments.

## Appearance review

`scripts/install_bedless_backgrounds.py` records the source and runtime hashes
for all 27 background masters and creates one bedless-background sheet per
aspect. `scripts/render_planter_scene_review.py` then composites the actual six
slot boxes and planter assets on every scenery/aspect combination.

The final review covered:

- Verdant Twilight, Spring, Summer, Autumn, Snowy, Rainbow Horizon,
  Halloween, Full Moon, and Eclipse;
- 4:3, 16:9, and Home crops;
- empty planters in all six slots;
- Seed, Sprout, Young, Mature, Flowering, and Rare assets in one six-slot scene;
- the alpha-following plant hover contour.

No residual circular bed, doubled rim, clipped planter, or unrelated background
change is visible in the reviewed sheets. The hover contour follows plant alpha
only; it does not outline the planter or reuse the selection ellipse. Its final
logical width is 1.65 px at 55% opacity so it remains restrained but visible at
normal viewing size.

Review artifacts are under `build/planter-background-cleanup/`:

- `bedless-backgrounds-{4x3,16x9,home}-review.png`;
- `planter-family-{4x3,16x9,home}-all-scenes.png`;
- `hover-outline-final-review.png`.

## Automated validation

- Planter, scene, Home, plant-layout, interaction, capture-contract, package,
  asset, storage-migration, and engine coverage is included in the final
  repository-wide run: 1,536 passed.
- Full catalog layout matrix: 5,760 scenarios, 0 failures, 0 warnings.
- Asset audit: 9 backgrounds, 1 decoration, 60 plants, 9 UI assets, and 7
  weather assets; all passed.
- Package audit: all 27 responsive backgrounds and all 6 planter layers are in
  `dist/anki_garden.ankiaddon`.
- Current package SHA-256:
  `9d60b0d1b9523ca3f8c2b9e14be186c8b5ca19137f63064d1edfe15c99aa5b79`.
- Package integrity and exact source/archive parity passed for all 262
  production files; the explicit capture build contains one additional harness
  file and cannot overwrite production.

## Live-Anki boundary

The complete pre-freeze post-planter visual candidate passed capture contract v8
with 146/146 ordered surfaces, including the explicit `hover-outline` state, at
150% UI scaling with zero failures and zero layout warnings. Package/performance
hardening changed no artwork, geometry, copy, or scene composition, and the
post-freeze pixel/geometry suite remains clean. The exact final-source run saved
139/146 uniform-primary frames with zero layout warnings and safely omitted
seven Home frames after macOS refused exact-window pixels; the owner approved
that release boundary. The separate explicit capture archive preserves the
production/capture capability split.

## Saved-state boundary

No state schema, save-file field, bed ID, slot index, growth rule, unlock rule,
or plant-to-bed assignment changed. Existing saved gardens load without
migration or remapping.
