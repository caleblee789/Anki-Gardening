# Sunflower production source masters

Final six-stage source set. The user requested the partly buried seed; sunflower_seed_buried_alpha.png is the selected seed master. Earlier seed files are retained history.

| Stage | Selected master | Reference layout height |
| --- | --- | --- |
| Seed | sunflower_seed_buried_alpha.png | 24 px |
| Sprout | sunflower_sprout_alpha.png | 50 px |
| Young | sunflower_young_alpha.png | 102 px |
| Mature | sunflower_mature_alpha.png | 150 px |
| Flowering | sunflower_flowering_alpha.png | 170 px |
| Full Bloom | sunflower_rare_alpha.png | 190 px |

Manifest-fragment.json contains only six keyed replacements, prior-entry hashes and staged runtime hashes. Installer-overrides.json carries source names and measured placement, thumbnail and shadow calibration for central integration.

Generation-record.json preserves prompts and selected raw paths. Matching generated PNGs retain the raw outputs, extracted PNGs retain the cleanup intermediate, and alpha PNGs are the normalized transparent masters. The user explicitly authorized technical cleanup in prepare_assets.py. Runtime WebPs decode pixel-for-pixel identically to the selected masters.

Full review and validation: /Users/test/Documents/Anki Gardening.nosync/build/sunflower-redesign/20260905-190549/README.md.

The coordinator owns the shared installer, renderer and final manifest. Per-scenery lighting, Home crop/seed-transform parity and isolated live Anki acceptance remain central gates.
