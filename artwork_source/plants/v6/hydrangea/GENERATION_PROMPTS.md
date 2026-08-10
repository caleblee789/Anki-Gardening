# Hydrangea V6 generation prompts

This ledger supplements the shared V6 provenance with the selected Flowering
revision made on 2026-08-10. The other five stages retain the baseline prompt
and output history referenced by `../PROVENANCE.md`.

## Flowering revision

- Mode: built-in ImageGen reference edit
- Edit target: the previous selected Hydrangea Flowering source master
- Selected output: `G4/exec-d128f04f-6b38-4332-98cd-1bb8e538a7a2.png`
- Canonical source RGB pixel SHA-256:
  `276aa34fa0a81ad2f824045cf0fc305ffdd68a2955f8d59ba9e5ede20bd5cb22`
- Runtime RGBA pixel SHA-256:
  `aef1326353b619d641eaf9417b7b673f8b10e5ce9b16402ba3f62a7af8ed4c65`

```text
Use case: precise-object-edit
Asset type: Anki Garden V6 hydrangea Flowering source-master sprite
Input image: edit target; preserve its established subject identity, storybook-gouache rendering, and composition.
Primary request: Make only the five natural blue hydrangea flower heads visibly fuller and slightly more outward-spreading so the Flowering plant has a clearly different outer silhouette from its budded Mature stage. Enlarge and organically reshape the flower heads by roughly 12-15%, allowing petals to extend beyond nearby leaf tips at the upper-center and outer left/right crowns. Keep this a natural Flowering hydrangea, not a supernatural Rare variant.
Scene/backdrop: perfectly flat, uniform solid #FF00FF chroma-key background.
Composition/framing: square 1254 x 1254 source-master framing; keep the shrub centered; preserve generous transparent-key padding; preserve the exact bottom-center trunk/soil contact position.
Style/medium: match the existing polished storybook gouache exactly; detailed blue mophead blooms and natural green foliage.
Constraints: Change the flower heads only. Preserve the trunk, branches, leaves, lower silhouette, bottom-center soil-contact pixel, lighting, palette, canvas framing, and all non-flower anatomy. No added stems, no detached petals, no glow, no sparkles, no shadow, no pot, no planter, no mound, no scenery, no text, no logo, no watermark.
Avoid: changing the mature framework, shifting or scaling the whole plant, cropping, edge contact, gradients or texture in the #FF00FF background.
```

The selected output was normalized to exact `#FF00FF` with
`scripts/normalize_v6_chroma_sources.py`'s content-preserving `_normalize`
path, then extracted with the canonical soft-matte, despill, threshold 12/220
command documented in `../PROVENANCE.md`. The resulting ground-contact row is
1121, unchanged from both the previous Flowering asset and Mature.
