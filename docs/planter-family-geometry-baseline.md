# Planter family geometry contract

Status: current geometry authority for the six fixed Verdant Twilight V6 garden
slots. Planter artwork may change, but every value that positions, scales,
orders, or targets a plant is invariant unless a separately approved scene
migration changes the contract.

All nine Scenery families use geometry-compatible `bedless_v1` backgrounds.
Slots 0-1 use the shallow back planter, slots 2-3 use the medium planter, and
slots 4-5 use the largest front planter. Each depth band renders planter base,
the unchanged plant layer, and then the matching foreground rim. Legacy painted
bed and combined occlusion paths remain disabled while the planter family is
active.

## Runtime geometry

- `GardenScene.heightForWidth()` uses a 4:3 scene below 620 px, 16:9 from 620 through 1399 px, and a 12:5 home-like scene at 1400 px and above. The registered surface profile selects its 4:3 bitmap at aspect ratios up to 1.42, its home bitmap from 2.05 upward, and its 16:9 bitmap in between.
- The three native background canvases are 1280 x 960 (4:3), 1672 x 941 (16:9), and 1942 x 809 (home). There was no independent bed asset before this change: every bed was painted into these full-scene bitmaps and repeated in their scenery reskins.
- `plant_layout()` resolves six explicit `BedAnchor` records from `verdant_twilight_surface_v6`. A plant's ground point is the slot support-line point, not the background or planter bitmap center.
- Plant draw position is `stable slot ground anchor - asset soil_contact * plant draw size`. Plant draw size is calculated only from plant metadata, slot depth scale, responsive fit, canvas aspect, and the serialized per-asset `visual_scale_correction`.
- `visual_scale_correction` is required manifest data and round-trips through placement serialization. Catalog thumbnails use a separately calibrated `thumbnail_scale`; thumbnail calibration never changes soil-plane geometry, saved anchors, or hit regions.
- Plant hitboxes come from the plant asset's semantic `interaction_bounds` plus motion/44 px accessibility padding. Empty-bed and move-mode targets use `bed_footprint` separately.
- Selection rings use `bed_footprint`; hover/keyboard outlines follow plant alpha; information cards use `smart_card_anchor` and the plant hit rectangle. Retained watering-can metadata is dormant and is neither rendered nor reserved by scene layout.
- Runtime order is deterministic: background, decorations, rear shadows 0-3, rear plants 0-3, rear occlusion, front shadows 4-5, front plants 4-5, front occlusion, interaction/selection/labels.
- Bed IDs and render order are `far_left_soil_bed`, `far_right_soil_bed`, `middle_left_soil_bed`, `middle_right_soil_bed`, `near_left_soil_bed`, `near_right_soil_bed` for saved `slot_index` values 0 through 5. No state migration is involved.

## Canonical 100% fixture

Canonical scene: native 16:9 surface, 1672 x 941 px. The fixed fixture deliberately covers all six stages: Bonsai Seed, Rose Sprout, Sunflower Young, Lavender Mature, Hydrangea Flowering, and Wisteria internal `rare` (player-facing Full Bloom).

Coordinates and rectangles are `[x, y]` or `[left, top, width, height]` in scene pixels. `slot scale` is the immutable perspective coefficient. `resolved scale` is the fixture plant's calculated draw width and must also remain exactly unchanged for the same fixture.

| Slot | Bed ID | Row | Bed footprint | Plant ground anchor | Slot scale | Resolved scale | Plant transform origin (`soil_contact`) | Plant z | Plant hitbox | Hit center | Label anchor | Background asset |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | --- | --- | --- | --- |
| 0 | `far_left_soil_bed` | back | `[563.4640, 403.8960, 187.2640, 42.3450]` | `[657.0960, 425.0685]` | 0.84 | 294.851394 | `[0.5, 0.866826]` | 425.0685 | `[622.7022, 356.3488, 68.0823, 71.8389]` | `[656.7434, 392.2682]` | `[657.0960, 474.2640]` | 1672 x 941 |
| 1 | `far_right_soil_bed` | back | `[927.9600, 403.8960, 187.2640, 42.3450]` | `[1021.5920, 425.0685]` | 0.84 | 307.931482 | `[0.5, 0.866826]` | 425.0685 | `[982.6337, 367.2734, 75.2152, 61.0763]` | `[1020.2413, 397.8115]` | `[1021.5920, 474.2640]` | 1672 x 941 |
| 2 | `middle_left_soil_bed` | middle | `[416.3280, 540.3034, 237.4240, 64.9290]` | `[535.0400, 572.7679]` | 0.92 | 239.752337 | `[0.5, 0.905901]` | 572.7679 | `[491.8170, 407.3594, 85.8724, 168.4967]` | `[534.7533, 491.6078]` | `[535.0400, 632.3520]` | 1672 x 941 |
| 3 | `middle_right_soil_bed` | middle | `[780.8240, 540.3034, 237.4240, 64.9290]` | `[899.5360, 572.7679]` | 0.92 | 144.372344 | `[0.5, 0.917065]` | 572.7679 | `[830.6777, 447.8030, 137.1411, 129.1590]` | `[899.2483, 512.3825]` | `[899.5360, 632.3520]` | 1672 x 941 |
| 4 | `near_left_soil_bed` | front | `[638.7040, 705.1289, 274.2080, 74.3390]` | `[775.8080, 742.2984]` | 1.00 | 179.490573 | `[0.5, 0.893939]` | 742.2984 | `[682.2289, 596.0248, 187.8739, 150.1286]` | `[776.1658, 671.0891]` | `[775.8080, 805.4960]` | 1672 x 941 |
| 5 | `near_right_soil_bed` | front | `[1003.2000, 705.1289, 274.2080, 74.3390]` | `[1140.3040, 742.2984]` | 1.00 | 228.348215 | `[0.5, 0.811802]` | 742.2984 | `[1048.8255, 588.7084, 187.8739, 157.1334]` | `[1142.7624, 667.2751]` | `[1140.3040, 805.4960]` | 1672 x 941 |

## Registered normalized slot geometry

These values are the source-of-truth geometry before cover projection. `anchor` is the plant ground anchor. `bed footprint` is width x height. Planter art must fit these slots and must never replace these values.

### 4:3 variant (1280 x 960)

| Slot | Bed ID | Anchor | Bed footprint | Label anchor |
| --- | --- | --- | --- | --- |
| 0 | `far_left_soil_bed` | `[0.3520, 0.42224]` | `[0.1540, 0.0460]` | `[0.3520, 0.4750]` |
| 1 | `far_right_soil_bed` | `[0.6520, 0.42224]` | `[0.1540, 0.0460]` | `[0.6520, 0.4750]` |
| 2 | `middle_left_soil_bed` | `[0.2495, 0.58268]` | `[0.1920, 0.0680]` | `[0.2495, 0.6460]` |
| 3 | `middle_right_soil_bed` | `[0.5495, 0.58268]` | `[0.1920, 0.0680]` | `[0.5495, 0.6460]` |
| 4 | `near_left_soil_bed` | `[0.4510, 0.77024]` | `[0.2220, 0.0750]` | `[0.4510, 0.8350]` |
| 5 | `near_right_soil_bed` | `[0.7510, 0.77024]` | `[0.2220, 0.0750]` | `[0.7510, 0.8350]` |

### 16:9 variant (1672 x 941)

| Slot | Bed ID | Anchor | Bed footprint | Label anchor |
| --- | --- | --- | --- | --- |
| 0 | `far_left_soil_bed` | `[0.3930, 0.45172]` | `[0.1120, 0.0450]` | `[0.3930, 0.5040]` |
| 1 | `far_right_soil_bed` | `[0.6110, 0.45172]` | `[0.1120, 0.0450]` | `[0.6110, 0.5040]` |
| 2 | `middle_left_soil_bed` | `[0.3200, 0.60868]` | `[0.1420, 0.0690]` | `[0.3200, 0.6720]` |
| 3 | `middle_right_soil_bed` | `[0.5380, 0.60868]` | `[0.1420, 0.0690]` | `[0.5380, 0.6720]` |
| 4 | `near_left_soil_bed` | `[0.4640, 0.78884]` | `[0.1640, 0.0790]` | `[0.4640, 0.8560]` |
| 5 | `near_right_soil_bed` | `[0.6820, 0.78884]` | `[0.1640, 0.0790]` | `[0.6820, 0.8560]` |

### Home variant (1942 x 809)

| Slot | Bed ID | Anchor | Bed footprint | Label anchor |
| --- | --- | --- | --- | --- |
| 0 | `far_left_soil_bed` | `[0.4115, 0.46480]` | `[0.0900, 0.0500]` | `[0.4115, 0.5190]` |
| 1 | `far_right_soil_bed` | `[0.5865, 0.46480]` | `[0.0900, 0.0500]` | `[0.5865, 0.5190]` |
| 2 | `middle_left_soil_bed` | `[0.3540, 0.63632]` | `[0.1120, 0.0780]` | `[0.3540, 0.7030]` |
| 3 | `middle_right_soil_bed` | `[0.5290, 0.63632]` | `[0.1120, 0.0780]` | `[0.5290, 0.7030]` |
| 4 | `near_left_soil_bed` | `[0.4700, 0.82704]` | `[0.1300, 0.0910]` | `[0.4700, 0.8990]` |
| 5 | `near_right_soil_bed` | `[0.6450, 0.82704]` | `[0.1300, 0.0910]` | `[0.6450, 0.8990]` |

## Forbidden dependencies and validation

No plant coordinate is read from the full-scene background's natural width,
height, alpha bounds, or visible bed silhouette. The planter layer must preserve
that separation: planter paths and draw boxes may be revised, but they must not
feed plant anchors, plant scale, plant hitboxes, plant labels, or render order.

`tests/test_planter_family_contract.py`, the scene surface fixture, the asset
audit, responsive geometry matrices, and package parity are the executable
authorities. The audit covers all 60 species-stage assets, requires serialized
`visual_scale_correction` plus calibrated thumbnail scale, and exercises every
asset across all six bed positions.

Capture contract v26 (contract schema 2, scenario schema 3) is the current
visual-evidence boundary. It rejects v25 reuse and requires scenario/fixture/
one-based-step lineage plus hard gates for asset mapping and clipping. Current
run paths, archive and capture hashes, artifact sizes, and validation totals
are recorded in the
[final 2.2.0 UI audit](ui/final-ui-audit-2.2.0.md) and its
[five-page contact-sheet index](../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json).
These artifacts remain
review evidence, not release approval: `quality_status: review-required`,
`release_ready: false`, with manual and platform gates open.
