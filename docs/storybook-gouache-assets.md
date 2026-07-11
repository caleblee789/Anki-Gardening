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
- Plant stages share the same pot, camera angle, baseline, light direction, and framing. Growth must remain obvious at small UI sizes.
- Decorations use isolated, centered silhouettes with generous padding.
- Weather remains a reusable overlay; do not bake separate weather variants into every painted background.

## Curated v3 slice

The first approved slice contains the summer Verdant Dusk master scene, all six rose stages, and the lantern decoration under `assets/v3_storybook_gouache/`. Other catalog slots intentionally continue to use the v2 SVG set until matching v3 families are produced and validated.

## Generation prompt foundation

Use `stylized-concept` for new artwork and `precise-object-edit` when advancing a growth series. Specify storybook gouache, warm upper-right amber light, cool left fill, muted botanical colors, tactile matte texture, clear small-size silhouettes, and no text or watermark. Transparent cutouts are generated on a uniform chroma-key field, converted to alpha PNG, and inspected for fringes before inclusion.
