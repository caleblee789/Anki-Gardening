# Garden Decorations implementation

Garden Decorations directly replace the former Weather customization through
the legacy migration path. Normal runtime rendering draws one static prop and one
shared stone pad; it does not request a scene overlay, create particles, or run
a decoration animation loop.

See the [illustrated Garden Decorations reference](references/garden-decorations-reference.docx)
for the current catalog, acquisition methods, Garden Find rates, bonuses, and
runtime artwork.

## Registry and preserved value

| ID | Rarity | Source | Price | Effect key |
|---|---|---|---:|---|
| `seedling_sign` | Common | Included | — | `none` |
| `wind_chime` | Common | Nursery | 100 | `growth_every_10_plus_1` |
| `harvest_bell` | Common | Nursery | 175 | `completion_coins_plus_5` |
| `watering_station` | Uncommon | Nursery | 250 | `growth_every_5_plus_1` |
| `herbalist_hourglass` | Uncommon | Nursery | 350 | `booster_cards_multiplier_1_25` |
| `firefly_lantern` | Rare | Garden Find | — | `growth_every_4_plus_3` |
| `prism_trellis` | Very Rare | Garden Find | — | `prism_bank_per_answer_1_5` |

Names, prices, rarity, acquisition paths, and ownership value are preserved
from the migrated catalog; the revised recurring effects are authoritative in
the reward engine. Cards, previews, and summaries display its committed data.

## One layout contract

- Anchor: `(0.215, 0.830)` in visible-scene coordinates.
- Square decoration canvas: `sceneHeight × 0.25`.
- Asset contact point: `(0.500, 0.880)`.
- Pad center: `(0.215, 0.842)`; size `0.28h × 0.07h`.
- Decoration and pad ignore pointer input and inherit scene clipping.
- All seven decoration masters are transparent 1024 × 1024 images normalized to
  the same contact line. No item or theme stores an offset or rarity scale.

Home uses its dedicated artwork and container-query units, so placement follows
the actual visible scene height. Native Garden uses an exact 3:2 canvas. The
existing 4:3 scenery image covers it at `50% 48%`, preserving the full width and
cropping only the top and bottom. There is no active 16:9 or standalone 4:3
Garden Decoration presentation.

## Migration and compatibility

The state migration maps the seven legacy IDs, ownership, displayed selection,
active Garden Bonus, queued bonus, visibility, reward records, Garden Find records, and purchase
records. The transform is idempotent, never charges again, and never emits a
discovery. Missing or invalid IDs fall back to Seedling Sign.

Legacy IDs and the old `weather` purchase kind are accepted only at migration
boundaries. Canonical saves contain `garden_features`,
`displayed_garden_feature_id`, `active_bonus_garden_feature_id`,
`pending_garden_feature_id`, and `garden_feature`
visibility. Migration maps the old IDs directly and does not require legacy
visual assets.

## Intentional limitations

- One displayed decoration and one active Garden Bonus; no bonus stacking,
  multiple slots, scene click target, or
  per-theme/per-decoration position.
- One light/dark local contrast treatment; no recolored scene variants.
- No decoration opacity, intensity, particle, or animation control.
- Decoration visibility is cosmetic. The Anki-day-locked Garden Bonus remains
  active when the art is hidden or a different prop is displayed.
- Manual visual approval remains required before release.

## Implementation report

### Primary files changed

- Registry and effect authority: `ankigarden/environment.py`,
  `ankigarden/garden_features.py`, `ankigarden/collectibles.py`, and
  `ankigarden/garden_finds.py`.
- Persistence and compatibility: `ankigarden/models/state.py`,
  `ankigarden/storage.py`, and `ankigarden/purchases.py`.
- Reward behavior and Anki-day Garden Bonus/Scenery locks: `ankigarden/game.py` and
  `ankigarden/hooks/reviewer.py`.
- Shared placement and rendering: `ankigarden/ui/garden_feature_layout.py`,
  `ankigarden/ui/scene.py`, `ankigarden/ui/plant_display.py`, and
  `ankigarden/ui/home_widget.py`.
- Nursery, Collection, Garden Bonus, preview, and Settings surfaces:
  `ankigarden/ui/dashboard.py`, `ankigarden/ui/environment_art.py`, and
  `ankigarden/ui/garden_studio.py`.
- Asset registration and validation: `ankigarden/assets/manifest.json`,
  `scripts/normalize_garden_feature_assets.py`, and `scripts/audit_assets.py`.
- Deterministic evidence and packaging:
  `scripts/build_garden_feature_evidence.py` and `scripts/package_addon.py`.

### Assets

Eight runtime WebP assets were added under
`ankigarden/assets/v6_storybook_gouache/garden_features/`: seven transparent
decoration canvases and one shared pad. Generation masters and prompts are retained
under `artwork_source/garden_features/`. Retired Weather visual assets are not
part of the runtime bundle.

### Removed and retired Weather behavior

Production painting and Home markup no longer invoke a Weather plan compiler,
overlay compositor, particles, opacity, or Weather animation path. The retired
compiler, capture matrix, evidence builder, tests, documentation, SVG assets,
and scene-painting helpers have been removed.

### UI and reward surfaces

Nursery and Collection use the Garden Decorations category. Collection keeps
the displayed decoration and Garden Bonus controls independent; Settings does
not expose Decoration selection or visibility. There is no decoration opacity
or animation control. Rare and Very Rare reward reveals use the static
decoration art and Garden Bonus copy. Session Summary uses engine-confirmed
Growth and Garden Coin totals and does not create an empty decoration section.

### Tests and evidence

`tests/test_garden_features.py` covers registry resolution, recurring cadence,
Prism banking, Hourglass doses, idempotent migration, legacy aliases, shared geometry,
normalized assets, hidden-bonus behavior, and Anki-day locking. Retired
Weather-compositor tests were deleted instead of being treated as active product
requirements. Deterministic decoration-matrix raw frames remain available, but
their superseded review sheets were removed. The current retained full UI
contact-sheet set and its remaining acceptance gates are recorded in the
[2.1.0 UI evidence record](ui/final-ui-audit-2.1.0.md). It remains review
evidence rather than release approval.
