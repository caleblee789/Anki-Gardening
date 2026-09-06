# Storybook gouache asset direction

## Visual language

Anki Garden uses warm storybook gouache: restrained paper-and-pigment texture,
organic edges, readable silhouettes, amber cottage light, muted botanical
greens, and teal shadows. Assets should feel tactile and calm rather than
glossy, photorealistic, neon, or geometrically flat.

## Verdant Twilight V6 environment

`verdant_twilight_surface_v6` is the release-preferred canonical environment.
All nine scenery themes use dedicated 1448 × 1086 lossless WebP paintings with
continuous planting ground. The native 3:2 Garden covers these 4:3 source images;
scenery previews use the same paintings. Home retains its separate 1942 × 809
banners and composition.

The installable archive contains 72 background images: nine continuous Garden
paintings, nine Home banners, and 54 reachable occlusion overlays. The source
catalog retains the 16:9 layouts, older 4:3 paintings (`source_garden_file`), and
authoring masks. Packaging omits those source-only references and files.

The same V6 profile is authoritative for background resolution, the full
Garden, the noninteractive home preview, the Settings scenery thumbnail, hit
testing, shadows, occlusion, movement, and validation. It defines six named direct-soil spaces in
far, middle, and near depth bands. Every space supplies a normalized support
line, contact plane, shadow plane, scale, footprint, depth, and occlusion masks.
Runtime plants may be scaled to fit but their semantic soil contact stays on the
painted support-line center.

Eight shipped Scenery reskins—Spring Bloom, Golden Summer, Autumn Hearth,
Snow-Covered Garden, Rainbow Horizon, Halloween Garden, Full Moon Garden, and
Celestial Eclipse—preserve the camera, path, cottage, Nursery, all six spaces,
anchors, alpha masks, landmark geometry, and occlusion topology. Compact
manifest rows use `placement_ref` to inherit the canonical V6 contract and
substitute the theme's continuous Garden and Home artwork/occlusion files. An artwork-specific
`landmark_overrides` entry may refine only a visual contour and its forgiving
hit bounds when a scenery repaint shifts the visible building edge; planting
surfaces and saved geometry remain canonical. Garden Decorations are independent
static transparent props for Home and native 3:2-on-4:3. They do not modify a
background raster or require a scene overlay.

## Garden landmarks

The Nursery entrance and cottage are declared with `garden.nursery.open` and
`garden.collection.open`. Each responsive variant supplies a forgiving accessible
hit rectangle, shaped visual polygon, and label anchor. Runtime hover/focus
draws the warm outline around the illustrated silhouette and places an in-scene
label; it never exposes the transparent control rectangle as the visual effect.
Both landmarks exist only in the interactive full Garden and are disabled while
a plant is moving. Home and Settings variants never expose a hotspot.

The back, middle, and front planter variants also declare normalized opaque
`accessory_exclusions` measured from their alpha bounds. These shared records
keep watering accessories off painted soil and stone without treating the
transparent 1024 by 512 sprite canvas as artwork or adding per-bed offsets.

Additional landmarks may reuse the manifest-backed action registry later, but
unknown actions must fail closed.

## Plant release-readiness

Plants use transparent, pixel-lossless WebP with clean edges, no baked ground shadow, and
geometry-v2 visible bounds, interaction bounds, and soil-contact metadata.
Runtime grounding—contact shadow, contact line, foreground vegetation, and
occlusion—belongs to the scene renderer rather than the bitmap.

Every placement record also serializes an authored
`visual_scale_correction`. Scene layout combines it with the canonical scene
scale without changing soil contact. Catalog and dialog art use an independent
explicit or optically calibrated `thumbnail_scale`, so large transparent
margins do not make Seed art appear undersized and thumbnail tuning cannot move
a plant in the Garden.

A species enters **Available now** only when all six stages are present locally
as release-preferred Verdant Twilight V6 `direct_soil` assets and every entry
passes geometry validation. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony,
Foxglove, Japanese Maple, Wisteria, and Dahlia currently satisfy the
complete-line contract. Retired or incomplete lines are not bundled and remain
hidden from starter selection and purchase. A previously owned plant is never
removed or damaged; if its old bitmap is unavailable, the renderer keeps its
name and stage and uses the code-native plant fallback.

The release audit treats the ten species by six stages as 60 independent asset
contracts and validates each against all six bed positions. Missing or implicit
`visual_scale_correction`, uncalibrated thumbnail scale, invalid alpha/contact
geometry, or an incomplete species line fails closed.

The shipped asset tree is deliberately small: current V6 backgrounds, reskins,
plant sprites, item art, and eight Garden Decoration assets live under
`assets/v6_storybook_gouache/`. Garden Decoration cards and scenes reuse the
same standardized static assets. Retired overlays, development candidates, previous scene
generations, migration catalogs, and placeholder bitmaps do not belong in the
add-on archive.

Growth must read clearly at small sizes. Every adjacent stage needs a distinct
height, branch, leaf, bud, or bloom change rather than a color-only change. Seed
remains visibly alive, and artwork-detail settings must not change composition.

Catalog item art is square transparent storybook gouache. Basic, Quality, and
Magical Fertilizer bag names are composited deterministically for exact
spelling; the Booster Potion is visually distinct; and Small, Standard, and
Grand Growth Charges use one, two, and three luminous pips. Surrounding UI owns
the catalog labels. The retained Nurturing artwork is a sage-and-teal watering
can. Its paired spout-left and spout-right variants come from the same
unlettered source; the exact word `Nurturing` is recomposed upright in bold,
centered type after mirroring. Both transparent 512-pixel lossless WebP assets
remain bundled, manifest-resolvable, and available for compact **Nurtured**
badge iconography. Garden, Customize, Settings, Deck Browser, and Overview
scenes intentionally do not place either variant beside a plant. The dormant
placement metadata remains with the assets for compatibility and future reuse.
The asset audit continues to enforce canonical paths, dimensions, RGBA
transparency, and at least one visible pixel plus transparent background.

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

## v26 visual evidence

Capture contract v26 uses contract schema 2 and scenario schema 3 with 18
representative and 38 full surfaces, producing two and six sheets. Scenario
ID, fixture ID, and one-based step persist through every evidence layer; v25
reuse is rejected. Asset mapping, visible-copy, overflow, progress, Reviewer
exclusion, scroll-state, and lineage checks are hard gates.

Current run paths, archive and capture hashes, artifact sizes, and validation
totals are recorded in the
[final 2.2.0 UI audit](ui/final-ui-audit-2.2.0.md) and its
[five-page contact-sheet index](../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json).
The evidence remains
`quality_status: review-required` and `release_ready: false`; manual macOS,
cross-platform, mixed-DPI, forced-colors, screen-reader, keyboard, and human
approval gates remain open.
