# Bedless V6 Background Masters

These 27 source masters were created on 2026-08-12 with the built-in ImageGen
editing workflow from the corresponding nine existing V6 scenery backgrounds
at 4:3, 16:9, and Home aspect ratios.

## Edit contract

Use case: precise-object-edit

Asset type: Anki Garden responsive background master

Primary request: Remove only the six empty garden beds or soil plots from the
open ground: two small rear beds, two medium middle beds, and two large front
beds. Reconstruct each removed footprint as seamless uninterrupted local
ground matching the exact nearby painterly gouache texture, color, seasonal
surface treatment, lighting, perspective, and depth band. Leave no soil,
stones, rims, holes, planters, outlines, shadows, halos, seams, smudges, or
clone patterns.

Constraints: Preserve the exact input dimensions, aspect, crop, framing,
horizon, greenhouse, cottage, path, trees, bushes, sky, edge foliage, palette,
lighting, and every object outside the six bed footprints. Do not add plants,
pots, objects, text, or watermarks. Change only the six baked bed regions.

## Normalization

The source outputs are normalized deterministically by
`scripts/install_bedless_backgrounds.py` to the existing rendering contract:

- 4:3: 1280 x 960
- 16:9: 1672 x 941
- Home: 1942 x 809

The installer preserves these canvas sizes, writes lossless runtime WebP
masters to the existing manifest paths, records all hashes in
`bedless-backgrounds.json`, and creates one nine-scene review sheet per aspect.

`scripts/render_planter_scene_review.py` performs the second review pass by
compositing the actual planter assets in the six fixed slot boxes for all 27
scene/aspect combinations. It also creates the representative six-stage and
hover-outline appearance check without changing runtime geometry.
