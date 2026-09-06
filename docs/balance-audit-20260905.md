# Anki Garden progression audit — September 5, 2026

**No first-month collection exhaustion appeared in the main-audience simulations. Improve weak and unusable rewards before considering any progression slowdown.**

The quick audit ran **525 seeded scenarios across 12 study patterns in 106.2 seconds**. Its 88,500 simulated days replace the earlier proposed 240.9 million; this is a reduction in planned simulation work, not a measured comparison with the full release run.

The audit includes equipped scenery and decoration effects, Garden Rhythm, consumables, achievements, earned beds, and permanent trophy bonuses. Gameplay values were not changed.

## Main results

The agreed audience is 100–400 eligible answers/day. The main concern is completing the plant collection within 30 calendar days; 90–180 days is a softer design target. These figures describe collection-first play, including replacing finished plants with owned seedlings once per day.

| Answers/day | First Full Bloom, median | Full Blooms at day 30 | All ten, median | All ten, observed range | Paid catalog, median |
|---:|---:|---:|---:|---:|---:|
| 100 | 29 days | 1 | Beyond 180 days | None finished within the run | 171 days |
| 200 | 15 days | 2 | 106 days | 103–109 days | 135 days |
| 400 | 8 days | 4 | 55 days | 54–57 days | 119 days |

There were **0 first-month finishers among 450 main-audience scenario outcomes** across collection-first, Growth-focused, and Coin-focused strategies. These are paired hypothetical users, not independent observations of real users or a statistical guarantee against rare fast finishes.

At 100 answers/day, collection-first users had a median eight Full Blooms by day 180. At 400/day, the plant loop finishes earlier than the preferred 3–6 months, while paid collection goals continue. Given the enjoyment priority and the absence of first-month completion, the audit does **not** recommend raising plant thresholds or slowing all Growth.

The incomplete-day case reached all ten at a median 114 days, versus 106 with regular completion. The 25-answer case had not reached its first Full Bloom by day 90, making early stages and affordable items especially important for light users. The 1,000-answer stress case used the Growth-spending heuristic; it is not a search for the fastest possible high-volume route.

## Prioritized findings

### 1. Some end-of-collection rewards cannot be used

Prepared production-engine checks confirmed that a complete ten-species collection cannot use a Grand Growth Charge, Fertilizer, or Booster Potion on its Full Blooms. Buying another copy of an owned species is also rejected. Inventory is preserved, but the reward has no usable current plant target.

This affects the Grand Charge awarded by Botanical Collection itself, plus later rewards from Snow-Covered Garden, Halloween Garden, Full Moon Garden, and consumable Finds. It matters more than small efficiency differences: a rare reward can become unusable precisely when it is finally earned.

**Recommendation:** after every current species reaches Full Bloom, allow Charges to become their existing amount of Stored Growth and allow Fertilizer/Booster cards to enhance normal overflow Growth. Preserve item values, single consumption, and the existing distinction between instant and shared Answer Growth. This is a proposed gameplay follow-up, not an implemented change.

### 2. Purchased Growth decorations are weak, especially at higher volumes

Wind Chime adds only 10 primary Growth per 100 answers: about one extra base answer. Watering Station costs 250 Coins versus the Chime's 100, but its 100-answer cap makes it weaker than the Chime at 400 answers/day: 20 versus 40 primary Growth.

A modest candidate was tested without modifying the runtime catalog:

| Item | Current | Candidate | Current → candidate at 100 / 400 answers |
|---|---|---|---|
| Wind Chime | +1 every 10 answers | +1 every 5 answers; retain 100-Coin price | 10 → 20 / 40 → 80 Growth |
| Watering Station | +1 every 5 of the first 100/day | +1 every 2 of the first 200/day; retain 250-Coin price | 20 → 50 / 20 → 100 Growth |

Across **300 paired runs**, the candidate produced no first-month finishers and did not change the reported all-ten medians. Collection-first samples were unchanged because those users bought the items later and favored discovered alternatives. Growth-focused users received roughly 143–186 additional total Growth by day 30 on average, depending on volume.

**Recommendation:** these buffs are reasonable modest improvements. They do not solve every pacing issue, and the simulated choices do not establish a universal optimum. Keep stronger discoveries enjoyable rather than reducing them to match weak purchases.

### 3. Heavy consumable spending can crowd out new plants

At day 180, the Growth-focused heuristic had only three Full Blooms at 100 answers/day and six at 200/day. It repeatedly spends toward short-term Growth while expensive next purchases remain unaffordable. Significant Growth accumulates in storage while fewer species are available to plant.

This is a real purchase tradeoff demonstrated by a scripted behavior, not proof that real users will follow it. Label these strategies as heuristics, keep consumables optional, and avoid using their long completion times as evidence that ordinary progression lasts long enough.

## Remaining feature review

| Feature | Assessment |
|---|---|
| Plant stages and earned beds | Early Full Blooms are satisfying at 200–400/day. Full Bloom replacement must be modeled: the old fixed-placement simulation could stall at five completed plants. All earned Growth remains accounted for. |
| Rhythm, streaks, Today’s Cards, Garden Cycle | Positive rewards and preserved progress fit an Anki companion. The missed-week case still progresses. Do not add missed-day penalties or answer-quality incentives. |
| Fertilizer and Charges | Quality and Magical Fertilizer both provide four primary Growth per Coin; Magical provides stronger, longer coverage. Charges trade Shared Growth for immediate progress. Different convenience and timing can justify unequal returns. |
| Harvest Bell and Autumn Hearth | Useful income choices. Bell repays 175 Coins over 35 equipped completion days. Autumn includes both +4 completion Coins and +50% milestone Coins; its benefit is greater than the flat Coin column alone. No nerf recommended. |
| Herbalist’s Hourglass | Include both the 30-completion Potion and +25 cards at activation. Equipping it only when activating a Potion can retain the extension after switching away; this deserves attention as possible busywork. |
| Firefly Lantern and Prism Trellis | Useful direct Growth and distinct targeting/banking behavior. Keep them rewarding. Prism retains its bank across incomplete days; direct Growth does not receive Shared fan-out. |
| Spring and Summer | Modest boosts concentrated on early daily answers. Their maximum daily additions are 40 and 60 primary Growth. At higher volumes, their artwork and early-session benefit matter more than total efficiency. |
| Snow, Halloween, Full Moon | Recurring useful gifts before plant completion; the unusable-consumable finding is the major late-game concern. Expected gift values alone omit target availability and Booster interactions. |
| Rainbow and Eclipse | Guaranteed early-answer boosts; Eclipse benefits up to 125 answers/day. Their art and rarity do not require identical reward efficiency. |
| Finds and discovery pity | Retain frequent Finds and protection against long droughts. The small simulation models daily reward batches; direct catalog calculations document caps and guarantees. Rare-tail acquisition timing is outside this audit's precision. |
| Mastery and Stored Growth | Reachable, optional later goals. A species' four Mastery ranks require 375,000 Growth and 750 Coins; all ten require 3.75 million Growth and 7,500 Coins. These are substantial aspirational goals, not evidence that the plant loop remains unfinished. |
| Landmarks and Legacy | Landmarks are disabled. Fresh saves cannot fulfill Legacy's Landmark prerequisite, so neither is credited toward current longevity. |

## Scaling achievements and equipment verification

- **Botanist’s Plaque:** earned after all ten Full Blooms; +1 Growth per eligible answer. It accelerates later progress without accelerating its own first unlock.
- **Golden Trowel:** earned after 100,000 answers; increases each other planted bed's share from 10% to 15%. With six occupied beds, total output rises from 150% to 175% of primary Growth, approximately a 16.7% increase.
- **Garden Journal:** earned after 365 completed days; +5 completion Coins. It is outside the 180-day fresh-start run and was checked using a prepared unlocked state.

Production comparisons covered each trophy and all three together while scenery and a decoration were equipped. The JSON also records actual equipment, achievement ownership, and active trophies at every checkpoint; owning an item does not automatically grant its equipped effect.

**97 focused tests passed**, including model accounting, reproducible parallel runs, placement preservation, consumables, equipment, and trophy behavior. Three short production traces matched across **21 daily checkpoints and 4,900 answers**. Native Anki UI, full annual parity, the comprehensive release matrix, and package/release acceptance were not run.

## Reproduce and inspect

Run from the repository root, using a fresh output directory:

```sh
ANKI_GARDEN_SKIP_STARTUP=1 ./.venv/bin/python scripts/simulate_balance_profiles.py --quick --output-dir build/quick-audit-new
```

Use `--quick --seeds 2 --days 7 --workers 1` for a short development run. The normal comprehensive mode remains available without `--quick`.

- [Simulation report](../build/quick-balance-audit-20260905-214846/results/quick-audit.md), [JSON](../build/quick-balance-audit-20260905-214846/results/quick-audit.json), [statistics CSV](../build/quick-balance-audit-20260905-214846/results/quick-statistics.csv), [item values CSV](../build/quick-balance-audit-20260905-214846/results/quick-items.csv).
- [Candidate comparison](../build/quick-balance-audit-20260905-214846/candidate-decoration-buffs/quick-audit.json) and [reproduction script](../build/quick-balance-audit-20260905-214846/compare_candidate.py). Candidate values are simulation-only.
- [Production trace evidence](../build/quick-balance-audit-20260905-214846/short-engine-parity.json) and [late-consumable evidence](../build/quick-balance-audit-20260905-214846/late-consumable-check-verified.json).
- [Frozen source manifest](../build/quick-balance-audit-20260905-214846/audit-source-manifest.json), [plant-availability asset hashes](../build/quick-balance-audit-20260905-214846/availability-assets.json), and the adjacent `source/` copy preserve the exact inputs. An earlier pre-asset diagnostic is retained separately.

The working tree contains concurrent changes. These findings describe the frozen audit snapshot, not later edits. The raw quick-report validation field deliberately does not self-certify the separately executed tests and production checks.
