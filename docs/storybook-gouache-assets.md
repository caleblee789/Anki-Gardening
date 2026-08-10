# Storybook gouache asset direction

## Visual language

Anki Garden uses warm storybook gouache: restrained paper-and-pigment texture,
organic edges, readable silhouettes, amber cottage light, muted botanical
greens, and teal shadows. Assets should feel tactile and calm rather than
glossy, photorealistic, neon, or geometrically flat.

## Verdant Twilight V6 environment

`verdant_twilight_surface_v6` is the release-preferred environment and the only
current selectable style. Opaque 4:3, 16:9, and home masters use high-quality
WebP and locked composition so cover-cropping never shifts a planting space.

The same V6 profile is authoritative for background resolution, the full
Garden, noninteractive home and Settings previews, hit testing, shadows,
occlusion, movement, and validation. It defines six named direct-soil spaces in
far, middle, and near depth bands. Every space supplies a normalized support
line, contact plane, shadow plane, scale, footprint, depth, and occlusion masks.
Runtime plants may be scaled to fit but their semantic soil contact stays on the
painted support-line center.

Future seasonal or local-clock plates must preserve the camera, cottage,
Nursery, all six spaces, anchors, masks, landmark geometry, and occlusion
topology. Weather remains a separate overlay.

## Nursery landmark

The Nursery entrance is declared in the manifest with action
`garden.nursery.open` and responsive 4:3 and 16:9 geometry. The registered
action supplies the accessible **Nursery** label and **Open Nursery** tooltip.
It is available only in the interactive full Garden and is disabled while a
plant is moving. The home and Settings variants must never expose a hotspot.

Additional landmarks may reuse the manifest-backed action registry later, but
unknown actions must fail closed and no second landmark ships in this release.

## Plant release-readiness

Plants use transparent alpha PNG with clean edges, no baked ground shadow, and
geometry-v2 visible bounds, interaction bounds, and soil-contact metadata.
Runtime grounding—contact shadow, contact line, foreground vegetation, and
occlusion—belongs to the scene renderer rather than the bitmap.

A species enters **Available now** only when all six stages are present locally
as release-preferred Verdant Twilight V6 `direct_soil` assets and every entry
passes geometry validation. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony,
Foxglove, Japanese Maple, Wisteria, and Dahlia currently satisfy the
complete-line contract. Retired or incomplete lines are not bundled and remain
hidden from starter selection and purchase. A previously owned plant is never
removed or damaged; if its old bitmap is unavailable, the renderer keeps its
name and stage and uses the code-native plant fallback.

The shipped asset tree is deliberately small: current V6 backgrounds and plant
sprites live under `assets/v6_storybook_gouache/`, while the reusable weather
and lantern files live under `assets/support/`. Development candidates,
previous scene generations, migration catalogs, and placeholder bitmaps do not
belong in the add-on archive.

Growth must read clearly at small sizes. Every adjacent stage needs a distinct
height, branch, leaf, bud, or bloom change rather than a color-only change. Seed
remains visibly alive, and artwork-detail settings must not change composition.

## Generation and validation

Use a flowering identity master to establish each species, then derive the
remaining stages while locking camera angle, light direction, soil contact,
silhouette family, and intended footprint. Specify warm upper-right amber light,
cool left fill, muted botanical colors, tactile matte texture, clear small-size
silhouettes, and no text or watermark.

Generate cutouts on a uniform removable background, convert to clean alpha, and
inspect for fringe, cropped foliage, false shadows, and base drift. Acceptance
requires the asset audit, complete-line readiness check, all-stage/all-space
geometry matrix, responsive renders, package parity, and the exact-package
isolated-Anki visual pass.
