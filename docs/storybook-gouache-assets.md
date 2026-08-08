# Storybook Gouache Asset Direction

## Visual language

Anki Garden's premium illustration style is warm storybook gouache: restrained paper-and-pigment texture, organic edges, readable silhouettes, and amber cottage lighting balanced with muted botanical greens and teal shadows. Assets should feel tactile and calm rather than glossy, photorealistic, neon, or geometrically vector-flat.

## Runtime formats

- Opaque scene backgrounds use high-quality WebP at a 4:3 aspect ratio with a generous crop-safe zone.
- Plants and decorations use alpha PNG with clean edges and no baked ground shadow.
- UI frames, badges, and reusable weather overlays remain SVG.
- Every v3 manifest entry names its format, dimensions, alpha behavior, style family, and v2 fallback asset.

## Composition rules

- Backgrounds reserve a quiet lower-center area for runtime plants and keep important details away from cover-crop edges.
- Background and terrace metadata define the same six permanent normalized beds: position, depth, plant scale, footprint, and a label anchor used only by move mode. Older backgrounds fall back to that shared contract.
- Theme-aware transparent terrace overlays sit between the painted scene and runtime plants. Normal mode shows physical soil beds without instructional labels.
- Potted families share the same pot, camera angle, baseline, light direction, and framing.
- Dirt-mound families share a compact oval mound and fixed ground baseline while their plant silhouettes expand dramatically within a stable full-size canvas. The mound must not scale between stages.
- Growth must remain obvious at small UI sizes; each adjacent stage needs a distinct height, branching, leaf, bud, or bloom change rather than a color-only change.
- Seed remains the first progression stage but always renders a visible living shoot. All quality tiers share the same stage-scale sequence so artwork detail never changes composition.
- Runtime grounding belongs to the scene renderer rather than the transparent plant bitmap: contact shadow, soil contact, and foreground grass use the same baseline for PNG and SVG families.
- Interactive separation is restrained at rest and strengthened only for hover, keyboard focus, pinned selection, or a stage transition.
- Decorations use isolated silhouettes outside the planting terrace. `none` is the default; the lantern remains optional at a restrained scale.
- Weather remains a reusable overlay; do not bake separate weather variants into every painted background.

## Curated v3 slice

The approved slice contains summer masters for all three themes, theme-matched terrace overlays, all six stages for Rose, Sunbloom, and Bonsai, and the optional lantern under `assets/v3_storybook_gouache/`. Other species intentionally continue to use the v2 SVG set until matching v3 families are produced and validated; their placement metadata still conforms to the same stage, alpha-bound, baseline, shadow, and scale contract.

## Generation prompt foundation

Use `stylized-concept` for the flowering identity master and `precise-object-edit` for the remaining growth stages. Specify storybook gouache, warm upper-right amber light, cool left fill, muted botanical colors, tactile matte texture, clear small-size silhouettes, and no text or watermark. For mound-based plants, lock the mound width, baseline, camera angle, and light direction while changing the plant's occupied height and fullness. Transparent cutouts are generated on a uniform chroma-key field, converted to alpha PNG, and inspected for fringes before inclusion.
