# Final progression balance audit — 7 September 2026

> Simulator follow-up: the model defects below were corrected and the six selected production comparisons now pass. See [corrections and contribution tables](simulator-correction-and-progression-contributions-20260907.md). The original audit remains as historical evidence; its model timing table has not been regenerated.

**Balance sign-off is withheld.** The current plant loop remains reasonable for much of the intended 100–400-answer audience, but the protected first-month completion limit still fails at 1,000 answers/day. Growth rewards also lose their progression purpose after the collection is complete. Separately, the simulator does not match longer production-engine traces, so its population timings below are provisional.

This audits the current dirty working tree, based on commit `332c978`, including the new 4/16 daily Coins, permanent streak bonuses, simplified appearance effects, and disabled Landmark/Mastery/Legacy features. No gameplay code, prices, odds, thresholds, installed add-on, or normal Anki profile was changed.

## Measured pacing

The existing simulator ran 875 scenario/seed executions over 26 fresh, established, light, and inconsistent cases. A further 125 executions extended light cohorts and the 100-answer collection strategy to 365 days. These are hypothetical seeded runs, with some repeated seed identities across horizons; they are not 1,000 independent players.

All timings are calendar days. Collection-first play buys species before appearances, uses earned supplies, fills beds, and replaces completed plants once per day. Medians retain unfinished runs as beyond the horizon.

| Fresh study pattern | Seeds | First Full Bloom, model median | All ten, model median |
|---|---:|---:|---:|
| 10 answers, 5 days/week, 80% completion | 25 | 351 days | Beyond 365 days |
| 25 answers, 6 days/week, 90% completion | 25 | 135 days | Beyond 365 days |
| 50 answers every day, 90% completion | 25 | 56 days | 363 days |
| 100 answers and completion every day | 50 | 30 days | 196 days |
| 200 answers and completion every day | 50 | 15 days | 105 days |
| 400 answers and completion every day | 50 | 8 days | 55 days |
| 1,000 answers and completion every day | 25 | 4 days | 23 days |

There were no first-month finishers in the 450 fresh 100/200/400-answer executions across collection-first, Growth-focused, and Coin-focused heuristics. The established 100/200/400 scenarios also had none. The established opening is the existing production onboarding fixture with 100,000 historical answers across 365 days; it is not representative of every returning user.

The 1,000-answer collection-first and Coin-focused cells each had 25/25 first-month finishers, both fresh and established. Established collection-first completion had a model median of 18 days. The inconsistent 200-answer case, with 80% completion and a missed week, had a model median of 113 days versus 105 with daily completion.

**Direct production observations:** after the strict comparisons failed, a separate diagnostic replay continued executing the real `GardenGameEngine`, recording comparison failures rather than stopping. No reward logic was replaced.

| Production case, seed 0 | First Full Bloom | All ten Full Blooms |
|---|---:|---:|
| Fresh, 400 answers/day | Day 8 | Day 53 |
| Fresh, 1,000 answers/day | Day 4 | Day 23 |
| Established, 1,000 answers/day | Day 3 | Day 18 |

These three in-memory observations confirm that early completion is possible under current production mechanics. They are not population medians, a passed parity result, or native/SQLite release acceptance.

## Findings, in priority order

### 1. High-volume play still violates the existing first-month guardrail

The day-23 fresh and day-18 established production observations independently demonstrate the failure documented in the previous uncapped audit. The new simplifications do not resolve it.

Uncapped Finds now make Coin income meaningfully card-volume dependent. Catalog analysis gives approximately one Find per 48.06 answers and 2.703 Coins per Find after accounting for the guarantee. That is roughly 5.6 / 11.2 / 22.5 / 56.2 Find Coins per day at 100 / 200 / 400 / 1,000 answers, before Autumn and other income. At high volume, species become affordable much faster alongside accelerated Growth.

**Recommendation:** retain the release hold under the existing guardrail. Do not raise every plant's 35,000-Growth threshold to fix only the stress cohort: 100-answer users already take about six months to finish the collection, and lighter users take substantially longer. Resolve the intended high-volume completion policy explicitly before choosing a balance change. This audit does not authorize restoring caps or enabling deferred systems.

### 2. Completing the collection removes the purpose of subsequent Growth rewards

[Feature availability](../ankigarden/feature_availability.py) disables Landmarks, Mastery, and Legacy. The [current reference](progression-rewards-effects-reference.md) explicitly states that Stored Growth has no spending option.

Botanical Collection still awards a Grand Growth Charge and the Botanist's Plaque, whose bonus is more Growth. Later supplies, Growth Finds, streak bonuses, and many rare appearance effects continue generating Growth, but cannot advance a visible project once all ten species bloom. Consumables can be consumed into storage; that preserves accounting without restoring progression value.

The provisional 400-answer collection-first model has about 44,754 Stored Growth by day 60 and 982,739 by day 180. The amounts depend on the simulator; the absence of any spending destination is directly established by current production policy.

**Recommendation:** treat the collection finish as the actual end of the Growth progression in this release. Reconcile late reward usefulness with that finite endpoint before claiming long-term progression. Do not count dormant Mastery/Legacy costs or an increasing storage balance as playable longevity.

### 3. The balance model cannot support final numerical sign-off yet

All three longer strict production comparisons failed:

| Scenario | First mismatch | Concrete difference |
|---|---|---|
| Fresh, 400/day | Day 21 | Production has 121,067.5 generated Growth; kernel has 120,597.5. Production also has 4 more milestone Coins. |
| Fresh, 1,000/day | Day 10 | Production has 138,607.5 generated Growth; kernel has 137,550. Production also has 4 more milestone Coins. |
| Established, 1,000/day | Day 9 | Peony allocation differs: kernel expects 2,706.25 Growth, production has 1,845. |

The same discrepancies recur in the final frozen-source diagnostic replay and are preserved in the evidence. They establish divergence in Growth, checkpoint income, and allocation; the exact underlying cause was not fixed or fully isolated in this audit.

There is also a separately reproduced valuation defect in [`_environment_daily_value()`](../scripts/balance_analysis/kernel.py): it only credits flat Coin grants, so Autumn's `earned_coin_percent` effect evaluates to zero. The Coin-focused selector keeps the default scenery when Autumn is owned, although granting 16 base Coins with Autumn produces 18 Coins plus 0.40 fractional carry. Both buying priorities and equipped choices use this valuation.

The scorer also compares ordinary and Instant Growth without current Shared Growth. For example, at 200 answers and six occupied beds without Golden Trowel, Watering Station produces 150 total Growth while Firefly produces 120; their nominal scores are only 100 and 120.

**Recommendation:** repair the simulator/replay discrepancies and income/Shared Growth valuation, then rerun the affected cases. Keep these strategies labeled as heuristics. Passing short tests or reproducing the same model outputs does not establish production parity.

### 4. Supplies can delay species purchases while funding unusable storage

The 400-answer Growth-spending heuristic has a median of only one Full Bloom at day 30, versus four for collection-first, while already accumulating about 106,634 Stored Growth. Its all-ten median is 139 days rather than 55. This is a provisional scripted outcome, not a claim about how actual learners behave.

The structural risk is real: spending Coins on acceleration can leave fewer unfinished species available, and excess Growth cannot be spent back onto future plants in this version.

**Recommendation:** keep species availability and useful Growth destinations clear when offering supplies. Do not interpret a supply-heavy strategy's slower completion as healthy additional content or successful pacing.

### 5. Light-user pacing and premium scenery deserve explicit positioning

The intended 100–400-answer audience has frequent early progress, but the lighter collection-first cohorts take roughly 4.5 months or almost a year to reach their first Full Bloom. Earlier stages and checkpoints still occur; the final bloom is not their only reward. Light-user support is therefore a product-positioning concern, not evidence that all Growth should be slowed.

Snow costs 1,200 Coins for 50 direct Growth per completed day. Spring costs 400 Coins and provides up to 40 primary Growth after 20 answers—52–60 total with four to six occupied beds. Summer costs 600 Coins and provides up to 60 primary Growth. Snow remains useful at low card counts and offers different artwork, but its price is a premium appearance choice rather than a generally stronger Growth upgrade.

**Recommendation:** retain the varied item identities, but make premium appearance pricing and low-volume expectations deliberate. No blanket item nerf is supported by this audit.

## What remains sound

- All ten species have identical 250-Coin acquisition and 35,000-Growth requirements; no species is an economic trap.
- Stage checkpoint payouts still sum to 120 base Coins per plant.
- The 4/16 daily Coin model is simpler and has broadly comparable complete-day income to the retired cycle system.
- Permanent streak tiers preserve an earned bonus after a break and apply only once to base card Growth.
- Fertilizer/Potions retain card-counted value; Charges retain their immediate delivery tradeoff.
- Harvest Bell's 175-Coin price repays over 35 equipped completion days, before Autumn interactions.
- Uncapped Finds preserve continued rewards and the 75-answer guarantee. Their increased high-volume income must be included honestly in pacing decisions.

## Verification and evidence

**87 existing focused tests passed; one comprehensive release-manifest test was deselected.** The run covered catalog, kernel, bounded annual/engine parity, achievements, and appearance mechanics. No tests were added or changed.

The three longer strict parity checks failed. Diagnostic continuation deliberately recorded those failures and must never be reported as a parity pass. Native Anki, real profiles, packaging, the full annual matrix, and release approval were outside this audit.

The final simulation and diagnostic runs use the immutable source snapshot in `build/final-progression-audit-20260907/source`. Its manifest is `aab08cebdc28dfe28a1aed47eb001b868e965a337b72b558022e6e5dc09b57f4`.

A concurrent kernel edit moved use of existing supplies before that day's streak reward grants. The complete matrix and extended horizons were refreshed on the final snapshot; headline medians were unchanged. Unrelated concurrent presentation/HUD edits caused intermediate whole-tree manifest checks to fail, so those attempts were not accepted as final evidence. The initial successful evidence is retained separately. At handoff, live changes relative to the final snapshot are confined to reviewer HUD/UI-state files; the balance catalog, engine, feature availability, and simulator still match.

The original 87-test run preceded that kernel edit. The 36 affected existing kernel/annual/engine tests were rerun afterward and passed, with the comprehensive release-manifest test again deselected. These test counts overlap.

Evidence:
- [875-run current matrix](../build/final-progression-audit-20260907/final-current.json)
- [125-run extended horizons](../build/final-progression-audit-20260907/final-extended.json)
- [Strict production comparisons](../build/final-progression-audit-20260907/production-parity.json)
- [Exact mismatch diagnostics](../build/final-progression-audit-20260907/parity-diagnostics.json)
- [Production completion observations](../build/final-progression-audit-20260907/final-production-observations.json)
- [Diagnostic replay script](../build/final-progression-audit-20260907/observe_production.py)
- [Valuation probes and verification record](../build/final-progression-audit-20260907/verification.json)

The final recommendation is to address model accuracy and the collection endpoint before tuning global Growth. Main-audience pacing gives no reason for an across-the-board slowdown.
