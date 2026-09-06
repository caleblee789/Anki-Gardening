# Bonsai redesign, 2026-09-05

Six ImageGen-authored stages retain the storybook gouache style, winding trunk, green foliage, peach flowers, and purple final bloom. The source canvas is 1254 × 1254 RGBA. Runtime exports use the existing asset IDs and lossless WebP paths.

The original line made Sprout and Young difficult to distinguish. Mature and Flowering relied heavily on small color details, while narrow metadata root bounds understated the contact shadow of the mature tree. The replacement line makes growth readable through silhouette and canopy structure:

| Stage | Design | Reviewed scene height |
| --- | --- | ---: |
| Seed | Compact chestnut shell with a short green shoot | 34 px |
| Sprout | Three leaves on a slim winding stem | 50 px |
| Young | Three green canopy pads on a juvenile trunk | 72 px |
| Mature | Five green canopy pads and stronger roots | 100 px |
| Flowering | Peach and ivory blossom clusters on five pads | 120 px |
| Full Bloom | Seven purple flowering pads and an intertwined trunk | 124 px |

Heights are measured at the 1260 × 840 reference scene in the frozen review renderer. Flowering and Full Bloom share a 115.14 px visible width. Other viewports use the shared layout engine. Header art in the contact sheets is individually fitted and is not evidence of relative garden scale.

## Sources and processing

`generation-records.json` records the six selected ImageGen files and hashes. `generated/` preserves these original outputs, and `prompts.json` preserves the creative prompts and refinements. All creative illustration changes were made with ImageGen.

Sprout and Mature supplied native alpha. Seed, Young, Flowering, and Full Bloom supplied a cyan matte and were extracted with the existing `scripts/process_direct_soil_asset.py` using `--transparent-threshold 18 --connection-threshold 70`. The resulting files are retained in `alpha/`.

`prepare_bonsai.py` performs the approved alpha and boundary cleanup, normalizes the production canvas, measures contact and thumbnail geometry, and exports the final masters and WebPs. It removes negligible alpha residue and replaces contaminated edge RGB with adjacent foreground RGB; opaque interior colors remain unchanged. Resizing uses premultiplied alpha. Full Bloom has a recorded 1.05 vertical normalization factor to retain the approved common width with a modest height increase. The measured root baseline is y = 1179 on the 1254 px canvas.

No ground shadow, scenery tint, ground plane, sparkle halo, or pot is baked into any sprite. Contact-shadow dimensions come from measured root support. Runtime lighting remains the coordinating task's responsibility.

Use the six `bonsai_<stage>_master_v1.png` files as the production sources. `bonsai-calibration.json` records source paths and complete reviewed placement overrides for the central installer. The older `bonsai_<stage>_chroma.png` files remain preserved historical sources; do not rebuild this redesign from them.

## Evidence and integration

The review is in `build/bonsai-redesign/20260905-v1/`: 54 scenery/stage crops, 240 native Qt icon renders at 20 sizes and two pixel ratios, 18 dense six-plant scenes, 1296 placement checks, two contact sheets, a before/after comparison, and an actual-size icon sheet. The 296-file application snapshot is derived from the user's original contact-sheet snapshot with only the six Bonsai sprites and their manifest entries replaced.

The targeted existing test modules passed with 55 passed and five intentional dormant-route skips. Existing plant catalog and retina density validators passed across all 60 plant records. PNG masters and decoded WebPs have exact RGBA pixel parity.

These are native Qt offscreen artwork checks, not captures of an Anki application window or release acceptance. Central manifest/installer integration, scenery lighting and seed draw-anchor fixes, Home/Qt shadow parity, and post-integration isolated-Anki visual QA remain with the coordinating task. The six canonical runtime sprites are installed separately with prior-hash guards; the shared manifest and installer are not edited by this species task.

`COMPLETE.json` seals the review output. Preserve it and use a new output version for subsequent work. `prepare_bonsai.py` refuses to overwrite a sealed review.
