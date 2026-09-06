# Foxglove redraw — 5 September 2026

Six original ImageGen assets replace the Foxglove line while retaining the storybook gouache theme and canonical stage IDs. The visual sequence is a ridged seed cluster, four-leaf sprout, basal rosette, closed bud spike, coral spotted bells, and three violet-blue Full Bloom spires. `rare` remains the internal Full Bloom key.

`generated/` preserves the six selected unaltered generator outputs. `generation-record.json` retains the prompts and source paths for all attempts, including rejected RGB checkerboard outputs. `foxglove_*_alpha.png` files are the final normalized RGBA masters. The exported WebPs are lossless and decode to those exact RGBA pixels.

The user authorized script-based extraction, background removal, alpha correction, and edge cleanup. `build_line.py` uses the existing repository chroma processor, removes connected residual magenta gradients, restores contaminated edge RGB from nearby clean pigment, crops without stretching, and exports at 1254 × 1254. Mature uses the generator's native alpha. Opaque pigment at least eight pixels inside the extracted subject is unchanged. The final edge RGB pass preserves its input alpha bytes. No detached effects, ground shadow, scenery tint, or backdrop is baked into the sprites.

`placement.json` is the Foxglove-only integration proposal. It holds scene scale, icon safe padding, and the 0.90 icon envelopes needed to retain margins at 16 px. The coordinator owns integration into the current installer and six current manifest rows. No shared renderer or catalog file is supplied as a replacement.

Review and handoff: `build/foxglove-redesign/20260905-190632/README.md`. The dated staging directory contains the six canonical WebPs, six compatibility chroma sources, manifest replacements keyed by asset ID, prior entry hashes, calibration proposal, validation, and visual evidence. Live canonical assets are deliberately left for the coordinator to install together with their metadata.

To reproduce the asset exports from the repository root, use the existing run's generation record:

```sh
.venv/bin/python artwork_source/plants/v6/foxglove/redesign_20260905/build_line.py --run build/foxglove-redesign/20260905-190632
```

The selected original paths in the generation record are only needed when the matching `generated/` master is absent. Preserve those six masters. Source hashes and the helper versions used for the reviewed export are recorded in the dated handoff. Do not treat a later regeneration or newer renderer as identical evidence without checking its hashes.
