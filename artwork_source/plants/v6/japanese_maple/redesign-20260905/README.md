# Japanese Maple artwork, September 5, 2026

Six stages retain Anki Garden's painted gouache theme. A gentle windswept trunk develops from a short palmate seedling into a tiered green tree, red-tipped Flowering, and a fuller natural crimson Full Bloom. Full Bloom uses copper accents and a few small falling leaves, with no magical glow.

The selected originals are the six `*-chroma-v1.png` images in this directory. They were painted with the built-in ImageGen tool against cyan. `generation-prompts.json` records the creative prompts. `flowering-master-v1.png` is an earlier style concept with a rendered checkerboard; it is not a runtime source.

The six `*-rgba-master.png` files are the final 1254 by 1254 transparent masters. Each has a centered semantic root contact near 94 percent canvas height. They contain no planter, soil plate, or baked contact shadow. Keep these canvases square for all Garden layouts, Home, and icons.

The approved cleanup uses the existing `scripts/process_direct_soil_asset.py` connected-chroma removal with thresholds 80/180, a uniform fit and translation to the root anchor, then the existing alpha-preserving boundary despill pass with a 32-pixel boundary window, a 48-pixel maximum color search, and slightly broader cyan recognition. The wider boundary window reaches residue inside fine leaf gaps. RGB under zero alpha is cleared. `build/japanese-maple-redesign/20260905-190604/prepare_maple.py` records the complete recipe. Creative shapes and colors were painted with ImageGen; scripts only removed backgrounds, aligned canvases, and cleaned edges.

The canonical `../japanese_maple_*_chroma.png` files are flat-magenta compatibility masters composited from these clean RGBA images for the existing source-audit contract. For future exports, use the versioned RGBA masters here rather than rekeying those magenta compatibility images. Canonical WebP exports use lossless encoding and decode to identical RGBA pixels.

Manifest replacements, measured root support widths, scale corrections, before/after artwork, nine-scenery contact sheets, shared icon previews, and verification records are in `build/japanese-maple-redesign/20260905-190604`. The coordinator owns merging the keyed metadata and installer calibration into shared files. Artwork preview evidence is separate from final package and isolated Anki acceptance.
