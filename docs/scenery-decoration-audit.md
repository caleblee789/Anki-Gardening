# Scenery and decoration audit

Audited all 9 scenery and 7 decoration definitions against the current engine. No reward-calculation mismatch was found. The [complete catalog mapping](scenery-decoration-simplification.md) matches the implemented rates, limits, and recurring rewards.

## Fixed description gaps

- Reviewer effect details previously used independent progress text for decorations, omitted Watering Station's daily cap there, and omitted complete scenery descriptions. They now use the shared catalog formatter for every item. Compact chips show item names; **View effects** opens a measured native panel with names separate from complete, unwrapped effect lines.
- The setup projection now says **Appearance only** for the two default items, matching the catalog, instead of **No bonus**.
- Two old capture expectations and the independent capture validator still described Watering Station's retired 5-card/100-card values. They now expect the current 2-card/200-card effect.

No item mechanics, prices, acquisition requirements, reward pools, or ownership rules changed during this audit.

## Mechanics evidence

The bounded engine exercise used the existing fake-storage fixture: 205 real review calls and 30 nonconsecutive completed days per item. Each completion was attempted twice to verify rewards were not duplicated.

| Item | Observed result |
|---|---|
| Verdant Twilight | No item rewards |
| Spring Bloom | 40 Growth; exactly the first 20 cards pay 2 each |
| Golden Summer | 60 Growth; every second card through card 120 |
| Autumn Hearth | Existing fractional-Coin test: twenty 1-Coin earned rewards pay 23 Coins total; replay and quoting preserve state |
| Snow-Covered Garden | 1,500 direct Growth across 30 completed days |
| Rainbow Horizon | 75 Growth; exactly the first 75 cards |
| Halloween Garden | 30 gifts across 30 completed days; source thresholds match the catalog's 95%/4%/1% pool |
| Full Moon Garden | 7 Potions across 30 completed days, repeating every 4 days |
| Celestial Eclipse | 125 Growth; exactly the first 125 cards |
| Seedling Sign | No item rewards |
| Wind Chime | 41 Growth across 205 cards; one every 5 cards |
| Harvest Bell | 150 item Coins across 30 completed days |
| Watering Station | 100 Growth; every second card through card 200 |
| Herbalist's Hourglass | 2 Potions across 30 completed days, repeating every 15 days |
| Firefly Lantern | 123 direct Growth across 205 cards; three every 5 cards |
| Prism Trellis | 3,000 direct Growth across 30 completed days |

Additional no-plant checks confirmed Snow stores 50 Growth and Prism stores 100 Growth. Existing tests cover activation/switching, counter persistence, Potion duration, live completion eligibility, replay and synchronization. Static tracing confirmed restored balances and reversals do not pass through the earned-reward grant path, and no retired Snow schedule or Potion-extension branches remain in the add-on.

The reproducible exercise is `build/audit_appearance_effects.py`; its per-item results are `build/appearance-effect-audit.json`.

## Surface coverage

All 16 items pass a registry-driven contract check across the runtime catalog, descriptors, Collection registry, catalog projections, purchase presentations where purchasable, setup summaries and Reviewer projections. Shop, Collection cards, equipped summaries and previews use `AppearanceEffectGroups`; decoration details use `garden_bonus_summary`. Both resolve through `appearance_effect_copy` and the authoritative parameter-driven formatter. Purchase confirmations consume the same descriptor effect. Reward receipts retain their actual awarded quantities rather than substituting the item rule.

Focused checks passed: 67 existing mechanics/catalog checks; 124 item/Reviewer/presentation/sync checks including the new 16-item surface contract; seven completion/replay/Potion checks; and a final 79-check Reviewer/presentation rerun after the popup visibility fix. These runs overlap and are not a summed unique-test count.

Native evidence: `build/appearance-effect-captures/20260907-230445/20260907-230606`. All 16 Reviewer detail panels pass visibility, exact-copy, line-width and screen-bound checks. All 20 accompanying Shop/purchase checks pass, and the Shop surface passes its individual capture audit. The longest Hourglass and Watering Station panels were visually inspected. This is targeted component/surface evidence in a disposable, sync-disabled Anki profile, not a complete Reviewer workflow or release audit. The generic full-suite scroll matrix remains outside this one-surface selection.

## Stable Collection category layout

Scenery and Decorations now share the catalog-width budget, toolbar wrap threshold, fixed tab widths and reserved scrollbar gutter. Switching categories therefore keeps the preview, category tabs and equipped panel in place. Decorations retain two columns; Scenery retains one.

Native evidence: `build/appearance-effect-captures/20260907-232229/20260907-232423`. All 72 targeted checks pass at 1280×800, 1040×720 and 860×580, including exact geometry equality across Scenery → Decorations → Scenery, all effect lines and both equipped cards at scroll position zero. Wide Decorations and compact Scenery screenshots were visually reviewed. Syntax and whitespace checks pass.

This is targeted layout evidence, not a clean full capture audit: the generic no-overflow scroll check flags the intentionally reserved scrollbar gutter for the short Decorations fixture, and the full four-state scroll matrix is outside the selected run. The surface's copy, fixture, native-layout, pixel and visual-contract checks pass; no text clipping or control overlap is reported.
