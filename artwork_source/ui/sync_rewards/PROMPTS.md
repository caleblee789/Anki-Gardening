# Sync Rewards UI artwork

Generated with the built-in OpenAI image generation tool for the native
Post-Sync Rewards receipt. Each source requests a genuinely transparent
background, a centered Retina-readable cutout, the established botanical
storybook-gouache style, and no text, emoji, device branding, or watermark.

| Source | Final prompt subject |
|---|---|
| `sync_review_cards.png` | Two overlapping ivory botanical review cards with sage borders and abstract answer marks. |
| `growth_resource.png` | A mint leaf-shaped energy droplet with an inner sprout vein, distinct from Growth Charge inventory. |
| `garden_coin.png` | One antique-gold coin embossed with a sprouting leaf and no currency characters. |
| `shared_growth.png` | Two leaf stems linked by a single mint energy ribbon. |
| `stored_growth.png` | A corked glass seed vial containing a mint Growth droplet and resting seed. |
| `checkpoint_badge.png` | A neutral sage-and-antique-gold botanical milestone ring without a star or trophy. |
| `garden_placeholder.png` | A subdued sage leaf over a warm-ivory seed-shaped backing for missing art. |

The runtime derivatives are normalized to 256 x 256 lossless WebP files with
alpha, more than five times their largest rendered dimension, and registered
under distinct non-inventory `ui_id` values. Existing
plants, environments, Growth Charges, Fertilizers, Booster Potion, and Garden
Find items retain their established assets and resolver identities.
