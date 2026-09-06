# Garden Decorations and Gardening Trophies

The full Garden and Garden Setup preview show the equipped decoration as a
static, grounded object. The Home banner omits decoration artwork. Equipment
and permanent trophy bonuses still apply while using Home.

## Outdoor catalog

| Decoration | Source | Price | Effect |
|---|---|---:|---|
| Seedling Sign | Included | — | No study bonus |
| Wind Chime | Shop | 100 Coins | +1 Growth every 5 cards |
| Harvest Bell | Shop | 175 Coins | +5 Coins per Today’s Cards completion |
| Watering Station | Shop | 250 Coins | +1 Growth every 2 cards, first 200 each day |
| Herbalist’s Hourglass | Shop | 350 Coins | 1 Booster Potion every 30 completed days; Potions last 25 extra cards |
| Firefly Lantern | Garden Find | — | +3 Growth every 5 cards to the unfinished plant closest to a checkpoint |
| Prism Trellis | Garden Find | — | Banks 1 Growth per card for release on completion |

The catalog and committed engine results remain authoritative. Scenery and
decoration artwork match the equipped items; previews do not change equipment.
There is one outdoor decoration slot, and the Seedling Sign is its neutral
fallback.

## Placement and depth

`ui/garden_feature_layout.py` projects the common ground point `(0.215, 0.830)`.
The base canvas is `0.25 × scene height`, adjusted by each asset’s measured scale.
The asset manifest records its physical ground contact, footprint, support and
art bounds, and contact-shadow dimensions. These values do not change by theme.

A subtle elliptical shadow sits under the actual support. The old common stone
pad is retired; each object keeps its original support artwork. Decoration
painting follows the bed and plant layers, so tall pieces such as the Wind
Chime’s hook stay visible in front of the middle bed. Plant, bed, building, and
interaction geometry are unchanged. Garden Setup uses the same scene renderer.

Foreground color and brightness follow each scenery: warm daylight, cool snow
and moonlight, and subdued eclipse lighting. The Firefly Lantern keeps its glow.
Each object has its own physical scale: the hourglass and lantern are smaller
than the barrel, while the chime and trellis stay tall.

Hover or keyboard focus outlines the actual artwork. Clicking or pressing Enter
opens a compact **Garden Decoration** menu with its name, **Garden Bonus:** and
**Date obtained:**. Escape or clicking outside closes it. The single-column menu
uses the same concise description as Collection, Shop, purchase confirmations,
and equipped-item panels, from `bonus_copy.py`.

Acquisition dates come from the permanent purchase/discovery ledger, with saved
history as a fallback. The included sign uses its starter plant's date. Missing
legacy dates display **Not recorded**; opening a menu never fabricates one.

The native Garden retains its 3:2 canvas and the existing scenery cover crop at
`50% 48%`. No placement adjustment or decoration asset is needed for Home.

## Gardening Trophies

The house and Progress → Trophy Room open the same page, headed **Gardening
Trophies**. A walnut case holds the Plaque, Journal, and Trowel in that order.
Each bay has inline **Unlock Requirement:**, **Permanent Bonus:**, and
**Date obtained:** details. Dates use the saved achievement unlock record. Locked trophies appear
muted with progress; unlocked trophies use full-color artwork. No trophy has an
Equip action or an outdoor placement.

| Trophy | Unlock requirement | Permanent bonus |
|---|---|---|
| Botanist’s Plaque | All 10 species at Full Bloom | +1 Growth per eligible card |
| Garden Journal | 365 verified completed review days | +5 Coins per subsequent Today’s Cards completion |
| Golden Trowel | 100,000 eligible answers | 15% Shared Growth for every other planted bed, up from 10% |

All three bonuses work together and stack with equipped scenery and the outdoor
decoration. The Plaque contributes before Shared Growth: a plain 10-Growth card
becomes 11, and the Trowel adds 1.65 to each other planted bed. Full Bloom lanes
retain normal redirection and overflow conservation. Growth Charges keep their
fixed values, with no trophy multiplier or Shared Growth fanout.

The trophy activation timestamp, introduced in schema 29, remains in schema 30. The unlocking event receives
no new bonus; later eligible events do. Upgrading an already earned trophy
initializes this timestamp once. Old events receive no backpay, existing one-off
achievement rewards are not reissued, and the Journal’s reward is deduplicated
by Anki day. Transactions restore activations and rewards together on save failure.

## Retired artwork and migration

Garden Bench, Birdhouse, Butterfly House, Stone Lantern, and Sundial are absent
from Shop, Collection, equipment, and the runtime package. Original artwork is
saved byte-for-byte under `artwork_source/retired_cosmetics/`. Historical
ownership and purchase records remain intact. A retired prop or trophy saved in
the outdoor slot falls back to Seedling Sign.

The three original trophy images, replacement masters, generation notes, and
original manifest entries are preserved under
`artwork_source/achievement_trophies/`. The runtime includes only the remade
transparent trophy artwork, sized and aligned to rest naturally in the case.

## Verification

Existing engine tests cover all eight trophy combinations, actual unlock
thresholds, duplicate reviews/completions, restart and upgrade, transaction
rollback, unchanged Growth Charges, and zero/one/six-bed overflow. Asset and
package checks preserve original hashes and exclude retired files.

`scripts/build_garden_feature_evidence.py --captures <native-run> <output>`
assembles review sheets from completed isolated-Anki captures. It does not
recreate the garden with a separate renderer. The targeted matrix contains 63
visible native combinations, nine native hidden baselines, and nine actual Home
banners without decorations. Raw screenshots are authoritative; review sheets
are navigation aids, and targeted QA does not constitute release approval.
