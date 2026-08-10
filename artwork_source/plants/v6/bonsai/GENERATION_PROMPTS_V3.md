# Bonsai V6 revision 3 ImageGen prompts

Mode: built-in ImageGen with project-local magenta chroma-key removal. Seed
used the V2 Seed as its edit target and Sprout as a line-continuity reference.
Rare used Flowering as its exact line, style, and base-anchor reference. The
selected outputs are preserved as `bonsai_seed_chroma_v3.png` and
`bonsai_rare_chroma_v3.png`; those files also supply the canonical chroma
sources for the two stages.

## Seed

```text
Use case: precise-object-edit
Asset type: revised Seed-stage direct-soil Bonsai game sprite
Input images: Image 1 is the Seed edit target and rendering reference. Image 2 is the same Bonsai line's Sprout and is a species/style continuity reference only.
Primary request: replace the subject in Image 1 with a more bonsai-specific germinating tree nut/seed. Make the seed visibly shorter and wider than the current upright form: one small irregular warm chestnut-brown woody nut, angled about 25 to 35 degrees rather than standing vertically. Nestle only its lower edge into a very shallow, restrained local soil indentation made of two or three tiny muted-brown painterly strokes hugging the shell; this is not a mound, patch, platform, or ground plane.
Germination structure: show a natural split in one end of the shell. From that split, create one continuous believable transition: a short cream radicle curls downward into the exact bottom-center contact point, while a separate emerging shoot begins beside it, shifts from pale green into a slightly woody warm-brown miniature S-curve, and ends in one tiny folded deep-sage leaf tip. Shell, root, and shoot must visibly connect with no seam, floating gap, or decorative flame shape.
Style/medium: preserve the polished hand-painted storybook-gouache finish, soft brush texture, warm natural palette, botanical detail, and slightly whimsical realism of both references.
Composition/framing: one compact subject centered low on a square canvas; bottommost contact remains exactly at horizontal canvas center; generous empty padding on every side. It must remain visible when rendered in the smallest Home widget but stay clearly smaller and simpler than Image 2.
Scene/backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background. Every empty area must show the identical flat magenta.
Constraints: change only the Seed subject; no pot, planter, broad soil patch, dirt mound, rock, floor, cast shadow, glow, aura, motes, flower, fruit, branch canopy, text, logo, or watermark. Do not use magenta, hot pink, or fuchsia in the subject. Background has no gradient, texture, lighting variation, haze, halo, reflection, or shadow. Crisp clean edges. Avoid an acorn cap, bean shape, bulb shape, candle-flame silhouette, generic decorative icon, or upright seed pod.
```

Built-in output:
`/Users/test/.codex/generated_images/019fe824-43bd-7870-99e7-bdbf7a51afae/exec-822f6bce-fdc8-4500-b9a8-2d1e6a5a375f.png`

## Rare

```text
Use case: precise-object-edit
Asset type: revised Rare-stage direct-soil Bonsai game sprite
Input images: Image 1 is the exact Flowering-stage line, style, species, and bottom-anchor reference.
Primary request: transform Image 1 into an ancient enchanted RARE bonsai that is clearly related but structurally unique. This must not be a recolor of Flowering. Redesign the trunk, primary branches, foliage-pad positions, and outer contour so the Rare silhouette remains unmistakably different when viewed in grayscale and at the smallest Home-widget size.
Structural direction: preserve the identical bottom-center root flare, lowest trunk origin, and planting contact coordinates from Image 1. Above that fixed base, build a more ancient, strongly tapered and gnarled trunk with a distinct irregular bend and visible knots, then divide it into an intricate exposed branch network. Create a controlled windswept asymmetry: one dominant off-center upper-left crown pad, one smaller high-right pad, one open middle-left pad, one compact middle-right pad, and one restrained low cascading branch/pad that turns downward before lifting slightly. Make all pads unequal in size and elevation. Preserve generous, intentional negative-space windows between trunk, branch forks, and pads. The cascading branch must remain close enough to the trunk to keep total width about 5 to 8 percent narrower than Flowering. Keep approximately the same height envelope.
Lineage: retain the same small oval leaf language, sculpted foliage-pad treatment, warm woody bark, delicate blossom scale, polished storybook-gouache brushwork, and direct-soil bonsai identity as Image 1. It must read as the ancient prestige counterpart to Flowering, not another species and not a Japanese maple.
Palette and prestige: foliage is predominantly deep natural teal, blue-green, emerald, and shadowed forest green—never cyan-dominant or fully blue. Add restrained jewel-toned blossoms in deep amethyst, muted sapphire accents, and warm antique gold. Use fine warm-gold highlights following selected trunk grain and branch edges, subtle pinpoint luminosity on a small number of leaf tips, and only 5 to 7 tiny warm-gold or pale-aqua motes kept close to the upper canopy. Detail and branch craftsmanship create prestige; glow must remain secondary.
Composition/framing: one plant centered on a square canvas, upright front three-quarter view, exact bottom-center contact inherited from Image 1, generous padding on every side. The main masses, gaps, and asymmetric branch gesture must remain readable at small UI scale.
Scene/backdrop: perfectly uniform solid pure magenta #FF00FF chroma-key background. Every negative-space opening and all space outside the plant must show the identical flat magenta.
Constraints: change the upper structure while preserving the base anchor; no pot, planter, soil patch, dirt mound, rock, floor, cast shadow, fruit, cyan canopy, electric-blue foliage, topiary triangle, copied five-pad Flowering silhouette, symmetrical tier stack, excessive width, large aura, halo ring, beams, dense particle field, text, logo, or watermark. Do not use magenta, hot pink, or fuchsia in the subject or effects. Background has no gradient, texture, lighting variation, haze, halo, reflection, or shadow. Crisp clean edges.
```

Built-in output:
`/Users/test/.codex/generated_images/019fe824-43bd-7870-99e7-bdbf7a51afae/exec-f44719c3-3a0f-4e76-9c0e-4da331b81271.png`
