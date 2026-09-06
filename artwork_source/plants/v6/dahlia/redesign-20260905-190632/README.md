# Dahlia targeted redesign masters

The selected release-source candidates are the six `dahlia_<stage>_normalized_rgba_v1.png` files (`rare` is displayed as Full Bloom). They are 1254×1254 transparent PNGs with preserved aspect ratios and a centered final root/stem contact at x=627, y=1166. No contact shadows or scenery-dependent grading are baked in.

`generation-provenance.json` retains the exact ImageGen prompts and output paths. The raw generated images are retained here for provenance. `dahlia_mature_rgba_v1.png` was rejected because of a baked checkerboard. The selected Mature image is `dahlia_mature_extract_rgba_v1.png`, whose true transparency was verified before normalization. Do not select the rejected file for regeneration or installation.

The original six unversioned chroma masters in the parent folder are unchanged. The new Flowering asset restores the multicolor petals visible in the original source but damaged in the old extracted runtime image. Mature has five larger closed buds and fuller foliage. Full Bloom preserves the crimson/gold centerpiece, three secondary flowers, and restrained small glints.

The implementation and review evidence are in `build/dahlia-redesign/20260905-190632` at the repository root. Its `handoff/manifest-replacements.json`, `handoff/installer-calibration.json`, and `handoff/pixel-fixture-replacements.json` contain the exact six-entry integration changes. `processing-report.json` records alpha cleanup, crop/scale/translation, source/runtime hashes, and decoded lossless-pixel verification.

The six canonical runtime WebPs have been installed, but their shared manifest, installer calibration, pixel fixture, and final combined release checks must be integrated centrally before release.
