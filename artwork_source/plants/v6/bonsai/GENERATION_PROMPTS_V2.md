# Bonsai V6 revision 2 ImageGen prompts

Mode: built-in ImageGen with project-local magenta chroma-key removal. Each
revision was a reference-based edit. The canonical `bonsai_*_chroma.png` files
contain these V2 selections; the prior selections are preserved as V1 siblings.

## Seed

```text
Use case: precise-object-edit
Asset type: Seed-stage direct-soil Bonsai game sprite
Input images: Image 1 is the edit target and painterly style reference.
Primary request: replace the generic round seed with a small, naturally germinating woody tree seed/nut that better foreshadows a bonsai tree.
Show one compact warm chestnut-brown tree nut resting at the centered ground-contact point, slightly irregular and textured rather than bean-like. The shell should be split along one end. From the split, create one continuous believable germination transition: a cream-colored radicle emerges first, curves downward and lightly hooks into the exact bottom contact point; immediately beside it a short pale-green hypocotyl curves upward in a subtle S-shape, carrying one tiny folded leaf tip. Root, shell, and shoot must visibly connect without an artificial seam or floating gap. Keep the seed simple and smaller than Sprout, but large enough to read in the dashboard.
Preserve the centered square composition, hand-painted storybook-gouache finish, warm natural palette, and generous padding. Anchor the bottommost root tip exactly at canvas center.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background.
Constraints: one seed only; no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, multiple developed leaves, branch, flower, fruit, wire, label, glow, aura, motes, text, logo, or watermark. Do not use magenta in the seed. Background has no gradient, texture, halo, haze, reflection, or lighting variation. Crisp edges.
```

## Sprout

```text
Use case: precise-object-edit
Asset type: Sprout-stage direct-soil Bonsai game sprite
Input images: Image 1 is the edit target and painterly style reference.
Primary request: make this Sprout read as the earliest stage of a bonsai tree rather than a generic leafy seedling.
Preserve the exact centered ground-contact position, compact overall scale, square framing, front three-quarter view, warm brown/deep sage palette, and hand-painted storybook-gouache style.
Growth-stage direction: replace the simple three-leaf stem with a short slightly woody warm-brown stem that already has subtle bark texture and a gentle S-curve. Add a tiny centered root flare. Near the upper third, form one small fork into two short unequal early branches. Carry only 4 to 6 compact oval leaves total plus one tiny emerging bud, arranged sparsely so the forked structure remains visible. It must still feel delicate and newly established—clearly more developed than Seed and much simpler than Young.
Composition: one sprout only, centered low on a square canvas, exact narrow root contact at bottom center, generous padding.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background.
Constraints: no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, dense foliage pad, thick trunk, large branches, flowers, fruit, wire, glow, aura, motes, text, logo, or watermark. No magenta in the plant. Background has no gradient, texture, halo, haze, reflection, or lighting variation. Crisp edges.
```

## Young

```text
Use case: precise-object-edit
Asset type: Young-stage direct-soil Bonsai game sprite
Input images: Image 1 is the later-stage structure and line-style reference.
Primary request: derive a clearly YOUNG Bonsai from Image 1. It must be much thinner, sparser, and less architecturally developed than Mature while remaining unmistakably part of the same line.
Preserve the exact centered soil-contact point, root-flare placement, trunk-origin direction, square framing, warm bark/deep sage palette, and hand-painted storybook-gouache style. Keep the base at the same canvas coordinates as Image 1.
Growth-stage direction: use a slim gently S-curved sapling trunk with early but visible taper; only 3 main branches; one small off-center top foliage pad and two much smaller unequal side pads. Show ample open air, exposed branch lengths, and a light juvenile canopy. Remove the massive lower branches, thick trunk, and broad five-pad Mature structure. Make the Young silhouette distinctly narrower and lighter, not a miniaturized mature tree. No flowers.
Composition: one plant centered on a square canvas, front three-quarter view, same narrow centered root contact at bottom as Image 1, generous padding.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background; every gap must show the same flat magenta.
Constraints: no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, flower, fruit, glow, aura, motes, text, logo, or watermark. No magenta in the plant. Background has no gradient, texture, halo, haze, reflection, or lighting variation. Crisp edges.
```

## Mature

```text
Use case: precise-object-edit
Asset type: Mature-stage direct-soil Bonsai game sprite
Input images: Image 1 is the edit target and line-style reference.
Primary request: revise the Mature Bonsai so it has a broader, more intentional, asymmetric bonsai silhouette with clearly developed trunk taper, visible primary branch structure, and larger negative spaces between foliage pads.
Change only the upper trunk, branching, and canopy development. Preserve the centered soil-contact point, complete root flare, lowest trunk section, warm bark palette, front three-quarter view, square framing, painterly storybook-gouache rendering, and species identity.
Growth-stage direction: Mature must be clearly more structurally developed than Young but leave Flowering as the natural peak. Use a strong tapered S-curved trunk that narrows convincingly toward the crown. Arrange 5 distinct foliage pads: one broad off-center crown, two unequal lateral pads, and two smaller lower pads. Extend one lateral branch farther than the other for asymmetry. Thin the foliage enough to expose elegant branch forks and intentional open air between every pad. Avoid a compact stacked triangle or dense topiary mass. Keep overall height similar to the input while making the natural canopy moderately broader.
Anchor invariant: keep the entire root flare, exact lowest trunk origin, and centered base/contact position visually identical to Image 1. The plant must grow directly from soil with no container.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background. Every opening between roots, trunk, branches, and foliage must show the same flat magenta.
Constraints: one plant only; no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, flowers, fruit, glow, aura, motes, text, logo, or watermark. Do not use magenta in the plant. Background has no gradient, texture, halo, haze, reflection, or lighting variation. Crisp edges and generous padding.
```

## Flowering

```text
Use case: precise-object-edit
Asset type: Flowering-stage direct-soil Bonsai game sprite
Input images: Image 1 is the exact Mature edit target and structural reference.
Primary request: turn Image 1 into the clearly distinct FLOWERING stage while preserving its mature bonsai structure and size envelope.
Keep the centered soil-contact point, root flare, lower trunk, trunk origin, overall height, moderate canopy width, asymmetric silhouette, warm bark, deep sage/olive foliage, square framing, and hand-painted storybook-gouache style unchanged. The root/base anchor must remain at exactly the same canvas position as Image 1.
Flowering distinction: slightly enrich the secondary branch network inside the existing five-pad structure and make each foliage pad only modestly fuller, while retaining clear negative space between pads and visible branch forks. Add a visibly abundant but balanced display of small blossoms—roughly 45 to 60 blossoms distributed across every foliage pad—in warm ivory, soft blush, and restrained pale peach. Use varied blossom sizes and a few buds so this reads immediately as Flowering at dashboard scale. Do not materially increase the plant's height or width.
Composition: one plant only, centered on a square canvas, front three-quarter view, same root contact and generous padding as Image 1.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background; every opening must show the same flat magenta.
Constraints: no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, fruit, magical glow, aura, motes, text, logo, or watermark. Do not use magenta in the plant or blossoms. Background has no gradient, texture, halo, haze, reflection, or lighting variation. Crisp edges.
```

## Rare

```text
Use case: precise-object-edit
Asset type: Rare-stage direct-soil Bonsai game sprite
Input images: Image 1 is the exact Flowering edit target and structural reference.
Primary request: create the RARE enchanted prestige version of Image 1 without making it larger or changing species.
Preserve the exact centered soil-contact point, root flare, lower trunk, trunk origin, S-curve, overall height, five-pad bonsai identity, square framing, and storybook-gouache rendering. Keep the root/base anchor at exactly the same canvas position as Image 1.
Silhouette and width: retain the asymmetric five-pad structure but shorten the farthest left and right foliage/branch extensions so the visible canopy is approximately 5% narrower than Flowering. Preserve strong negative spaces. Add finer, more intricate secondary and tertiary branch forks visible beneath the pads.
Color correction: foliage must remain predominantly deep natural teal-green, blue-green, emerald, and shadowed forest green—not cyan and not fully blue. Only a small minority of leaf tips may carry restrained turquoise or cool blue luminous accents. Use jewel-toned blossoms in deep amethyst, sapphire accents, and warm gold, but keep green/teal foliage visually dominant.
Prestige details: add subtle pinpoint glows on selected leaf tips, refined warm golden highlights following the trunk grain and a few branch edges, a soft close-fitting enchanted luminosity, and only 8 to 10 small floating gold or pale aqua motes near the canopy. Keep all effects painterly, delicate, and contained. Rare should feel more intricate and precious than Flowering, not louder or bulkier.
Backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background. Every branch gap and all space outside the close-fitting effects must show the same flat magenta.
Constraints: one plant only; no pot, planter, dirt mound, soil patch, rock, floor, cast shadow, fruit, cyan-dominant foliage, electric-blue canopy, large aura, halo rings, beams, magical pedestal, dense particles, text, logo, or watermark. Do not use magenta or hot pink in the subject or effects. Background has no gradient, texture, haze, reflection, or lighting variation. Crisp edges and generous padding.
```
