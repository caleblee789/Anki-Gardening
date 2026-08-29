# Garden Decoration generation source

Generated with the built-in OpenAI image tool using the shipped Verdant
Twilight 4:3 background as a style-only reference. Each prop requested genuine
transparency, painterly storybook gouache shading, a single centered object,
soft local contact shadow, no text or UI, and a bottom-center ground contact at
`(0.500, 0.880)` on a square canvas.

The seven subjects are Seedling Sign, Wind Chime, Harvest Bell, Watering
Station, Herbalist's Hourglass, Firefly Lantern, and Prism Trellis, following
the material and effect restrictions in the Garden Decoration specification. The
pad prompt requests a low, muted gray-green oval stone setting with restrained
moss and no podium, icon, rarity treatment, or rectangular boundary.

`scripts/normalize_garden_feature_assets.py` is the deterministic preprocessing
authority. It places all prop art inside one 1024 square runtime canvas at the
shared contact point, and produces the reusable 1024 by 256 pad.
