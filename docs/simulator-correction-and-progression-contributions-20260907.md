# Simulator correction and progression contributions — 7 September 2026

The simulator now agrees with the production engine in all six selected extended cases, including all three failures from the final progression audit. Gameplay rewards, prices, thresholds, odds, and feature availability were not changed by this work.

## What contributes most to Growth

These are shares of **Growth actually delivered during the first 30 calendar days**, using 50 fresh seeds at each volume, daily completion, a collection-first purchase strategy, earned supplies, and one daily bed-fill/replacement visit. All generated Growth in these 150 runs went to plants; none became Stored Growth.

| Source | 100 answers/day | 200 answers/day | 400 answers/day |
|---|---:|---:|---:|
| Base card Growth | 74.59% | 70.54% | 67.00% |
| Shared Growth from occupied beds | 11.08% | 14.93% | 18.84% |
| Garden Finds: direct Growth | 4.20% | 3.85% | 3.65% |
| Scenery and decoration effects | 2.03% | 3.12% | 3.60% |
| Permanent streak bonus | 3.11% | 2.94% | 2.79% |
| Growth Charges used | 2.96% | 2.73% | 2.17% |
| Booster Potions used | 1.81% | 1.62% | 1.69% |
| Fertilizer used | 0.22% | 0.27% | 0.26% |

Base cards plus Shared Growth contribute approximately **85–86%** at each volume. Average total Growth per modeled player was **40,220.4 / 85,054.6 / 179,111.6**, respectively.

The categories are disjoint and reconcile exactly to generated Growth before rounding. A Potion or Charge awarded by a Find is counted under the supply when used, not again under Finds. Shared Growth is the additional output from other occupied beds; the primary award remains in its own source category. The 100-Growth welcome opening is excluded. Trophy and direct-achievement Growth are zero in this window and omitted from the table.

This is contribution accounting for the stated play pattern, not an estimate of how much removing each mechanic would delay collection completion. Buying equipment or supplies before species would change the distribution.

## What funds further species purchases

These are shares of earned Coins during the same window, excluding the opening balance.

| Source | 100 answers/day | 200 answers/day | 400 answers/day |
|---|---:|---:|---:|
| Finish all cards due today | 45.84% | 34.58% | 22.75% |
| Garden Finds: Coins | 14.20% | 22.99% | 31.71% |
| Plant checkpoints and stages | 13.70% | 22.62% | 30.13% |
| One-time achievements | 14.80% | 11.17% | 9.72% |
| First card of the day | 11.46% | 8.65% | 5.69% |

At 100 answers/day, finishing the daily workload supplies the largest Coin share. At 400/day, Finds and plant milestones together supply approximately **62%**, explaining why high-volume users can acquire further species rapidly. Collection-first users in this sample did not yet earn Coin income from paid appearance equipment; the Coin-focused parity case separately exercises Autumn.

## Simulator corrections

- **Bed visits and replacement order:** fill empty beds with owned plants in the same order as the production replay, including stored Full Blooms. Fill before purchases, after each species purchase, and after replacement. Full Bloom beds continue producing Shared lanes, so omitting them understated Growth and changed species allocation.
- **Equipment valuation:** include Autumn's 15% earned-Coin effect using a recurring-income forecast. Include current occupied-bed Shared Growth and trophy rates when comparing ordinary Growth and Potion output against direct Growth. Reconsider equipped choices after bed/trophy changes, not only new ownership.
- **Answer ordering:** retain the direct Find's already sampled answer position without changing random draws. Use per-answer processing where a Full Bloom crossing or fractional Shared lane makes whole-day aggregation inaccurate; keep batching for linear days.
- **Contribution accounting:** expose exact, non-overlapping `growth.source.*` totals, retain exact integer pooled totals in reports, and require source totals to equal all generated Growth.

The equipment strategies remain heuristics. Autumn's forecast includes recurring study/completion income, guarantee-adjusted Finds, and applicable Bell/Journal rewards; it deliberately does not forecast finite achievement or milestone windfalls. Permanent purchase order uses the opening state. The corrected scorer is not a claim of globally optimal play.

## Verification

**475 daily production comparisons across 130,000 eligible answers passed**, with exact Growth, Coins, plant allocations, and the state fields covered by the existing replay harness.

| Production replay | Days | Answers | Result |
|---|---:|---:|---|
| Fresh, collection first, 400/day | 60 | 24,000 | Pass |
| Fresh, collection first, 1000/day | 35 | 35,000 | Pass |
| Established, collection first, 1000/day | 30 | 30,000 | Pass |
| Fresh, collection first, 100/day | 200 | 20,000 | Pass |
| Fresh, Coin focused, 100/day | 90 | 9,000 | Pass |
| Fresh, Growth focused, 200/day | 60 | 12,000 | Pass |

The existing focused suite covered 58 checks, with the two initial failures corrected and rechecked; the parallel-equivalence check also passed again. The comprehensive release-manifest test was deselected. Existing tests were extended for newly earned beds, meaningful Autumn/Shared Growth equipment choices, and source-total reconciliation; no new test file or testing framework was added.

The 150 contribution simulations passed every model accounting assertion. Their source is frozen under the evidence directory. Native Anki, the user's normal profile, installation, packaging, and the complete annual release matrix were not part of this task. Correcting the simulator does not itself change the previously observed day-23/day-18 production completion outcomes or resolve the release's separate pacing decision.

The earlier full-audit model timing table has not been regenerated here. Its model-confidence findings are superseded by this scoped correction and verification; its original evidence is retained.

## Evidence

- [Exact source snapshot manifest](../build/simulator-correction-20260907/source-manifest.json)
- [Six passing production comparisons](../build/simulator-correction-20260907/final-parity.json)
- [Raw contribution samples and source totals](../build/simulator-correction-20260907/contributions.json)
- [Growth CSV, including mean amounts](../build/simulator-correction-20260907/growth-contributions.csv)
- [Coin CSV, including mean amounts](../build/simulator-correction-20260907/coins-contributions.csv)
- [Contribution runner](../build/simulator-correction-20260907/run_contributions.py)
- [Production parity runner](../build/simulator-correction-20260907/run_parity.py)
- [Changed-file verification](../build/simulator-correction-20260907/verification.json)

Run the contribution script from the adjacent frozen `source` directory with the repository's Python environment. It refuses to overwrite its existing output; use a separate output location or copy of the evidence directory for a new run.
