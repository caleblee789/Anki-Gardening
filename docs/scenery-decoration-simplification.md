# Scenery and decoration simplification

Follow-up verification and description fixes are recorded in the [complete catalog audit](scenery-decoration-audit.md).

The final model has one complete effect per item. Equipping saves the item's artwork and bonus together. Previewing does not activate the bonus, and hiding artwork does not disable it. Completion means the existing all-due predicate, with its existing day boundary and once-per-day guard. Multi-day rewards repeat and do not require consecutive days.

| Item ID | Name | Final effect | Change |
|---|---|---|---|
| default | Verdant Twilight | Appearance only | Copy |
| spring | Spring Bloom | First 20 cards daily: +2 Growth each | Copy |
| summer | Golden Summer | First 120 cards daily: +1 Growth per 2 cards | Copy |
| autumn | Autumn Hearth | Earn 15% more Coins | Gameplay |
| snowy | Snow-Covered Garden | Finish all cards due today: +50 Growth | Gameplay |
| rainbow_horizon | Rainbow Horizon | First 75 cards daily: +1 Growth each | Copy |
| halloween | Halloween Garden | Finish all cards due today: 1 mystery gift | Copy |
| full_moon | Full Moon Garden | Finish all cards due on 4 days: +1 Booster Potion | Gameplay |
| eclipse | Celestial Eclipse | First 125 cards daily: +1 Growth each | Copy |
| seedling_sign | Seedling Sign | Appearance only | Copy |
| wind_chime | Wind Chime | +1 Growth every 5 cards | Copy |
| harvest_bell | Harvest Bell | Finish all cards due today: +5 Coins | Copy |
| watering_station | Watering Station | First 200 cards daily: +1 Growth per 2 cards | Copy |
| herbalist_hourglass | Herbalist's Hourglass | Finish all cards due on 15 days: +1 Booster Potion | Gameplay |
| firefly_lantern | Firefly Lantern | +3 Growth every 5 cards | Copy |
| prism_trellis | Prism Trellis | Finish all cards due today: +100 Growth | Copy |

The copy-only daily maxima remain 40/60/75/100/125 Growth for Spring/Summer/Rainbow/Watering Station/Eclipse. Grouped payouts, card positions, and active counters are unchanged. Halloween guarantees one gift: Small Growth Charge 95%, Standard Growth Charge 4%, Booster Potion 1%.

## Balance comparison

Autumn previously paid 4 Coins per completed day plus 50% of milestone Coins. The replacement pays 15% of all newly earned gameplay Coins and retains hundredths across awards. It includes Bell, trophies, achievements and finds; balances, refunds, reversals and replay are not earned income.

These illustrative reward baskets use the coordinated Study economy (4 Coins for studying, 16 for completion). They are sensitivity calculations, not measured player outcomes. Bonus amounts include fractional carry.

| Activity | Study/completed days | Milestone/find/other Coins | Old Autumn | New Autumn | New with Bell |
|---|---|---|---:|---:|---:|
| Low | 20/12 | 5/20/0 | 50.50 | 44.55 | 53.55 |
| Medium | 30/30 | 100/300/25 | 170.00 | 153.75 | 176.25 |
| High | 30/30 | 200/600/100 | 220.00 | 225.00 | 247.50 |

Incomplete days now receive a bonus on their earnings; milestone-heavy days can receive less, while large achievement rewards receive more. Bell itself still pays 5 Coins. Its interaction with Autumn adds 0.75 Coins per completion before integer settlement.

A Potion supplies 500 Growth (5 per card for 100 cards); each old ownership extension supplied another 125 Growth. At external Potion rates of 0/0.05/0.15 per completed day, Hourglass's old incremental value was 20.83/27.08/39.58 Growth per day; its 15-day replacement supplies 33.33. Full Moon's old value was 104.17/110.42/122.92; its 4-day replacement supplies 125. With both active, the old combined value was 150/162.5/187.5, versus 158.33 now. These long-run comparisons assume every Potion card is eventually used. Frequent outside Potion rewards and inactive ownership lose more value.

Snow previously supplied one stored 100-Growth charge every two completed days. Its 50 direct Growth each completed day preserves average nominal value but arrives earlier and loses storage and targeting flexibility. Delivery follows existing direct Growth routing, including no eligible plant.

No development-save conversion, compensation, duration grandfathering or automatic reset is part of this change.

## Layout and verification

Shop uses compact artwork and up to three columns when measured effect widths fit. Owned and Equipped badges sit at the top right. Collection Decorations uses two cards per row, while Scenery retains one. Collection reserves viewport height for both equipped cards and limits the preview to 450 px wide. Where the catalog and preview cannot fit alongside each other, a 270 px preview and the equipped summaries sit above the catalog. Effect typography is unchanged. Purchase confirmations now include the same authoritative effect.

Focused verification passed: 71 mechanics/catalog/sync checks, 12 registry/state checks, four existing purchase-presentation cases, and 10 existing engine cases. No new testing framework or compatibility tests were introduced.

The seven-surface targeted macOS acquisition is `build/appearance-effect-captures/20260907-213918/20260907-214044/manifest.json`, with all seven surface acceptance checks and 110 supplemental checks passing at 1280×800, 1040×720 and 860×580. Those checks cover every catalog effect, both equipped cards visible at scroll-top, and the Snow/Hourglass purchase confirmations. Screenshots were reviewed for badge placement, readable complete lines, preview sizing and three-column Shop layout.

The final two-column Decoration refinement was recaptured in `build/appearance-effect-captures/20260907-214445/20260907-214559/manifest.json`: four Collection/preview surfaces and 66 supplemental checks across the same three sizes. The longest Hourglass and Watering Station strings were visually checked at 860×580. Its immutable production archive is `build/appearance-effect-captures/20260907-214445/anki_garden.ankiaddon`, SHA-256 `c354415b3edc6c3de1a3264cfdfb53e28fbf81020d482623fedd567b73022c07`.

This is targeted evidence, not a complete release audit: the generic full-run scroll matrix reports missing no-overflow/one-row-list scenarios outside this selection. The immutable production archive for this acquisition is `build/appearance-effect-captures/20260907-213918/anki_garden.ankiaddon`, SHA-256 `14c4d0db0c036c70418176fba61c8e9702d859b1b010c5560a59b3ab105accec`. Captures used a disposable, sync-disabled profile; the normal Anki profile was not changed.
