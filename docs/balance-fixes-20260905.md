# Balance fixes and verification — 5 September 2026

Implemented the approved late-reward and decoration changes. The 525 original paired runs plus 50 established-user checks produced no first-month all-ten completions. The 400-answer Collection first median remains 55 days.

## All ten plants at Full Bloom

Calendar-day medians include every seed. `>180` means the median was not observed by day 180; it is not an estimated finish date. Observed ranges below cover finishers only.

| Answers/day | Spending policy | Before | After | After observed range | Unfinished before → after |
|---:|---|---:|---:|---:|---:|
| 100 | Collection first | >180 | >180 | — | 50/50 → 50/50 |
| 100 | Growth spending | >180 | >180 | — | 50/50 → 50/50 |
| 100 | Coin focused | >180 | >180 | — | 50/50 → 50/50 |
| 200 | Collection first | 106 | 106 | 102–108 | 0/50 → 0/50 |
| 200 | Growth spending | >180 | >180 | — | 50/50 → 50/50 |
| 200 | Coin focused | 124 | 122 | 118–125 | 0/50 → 0/50 |
| 400 | Collection first | 55 | 55 | 54–57 | 0/50 → 0/50 |
| 400 | Growth spending | 167 | 166 | 156–175 | 1/50 → 2/50 |
| 400 | Coin focused | 73 | 71 | 69–74 | 0/50 → 0/50 |

At 100 answers/day, the three policies have median 8, 3, and 7 Full Blooms by day 180. The unfinished 200/day Growth spending group has 6. Growth spending at 400/day finishes sooner at the median, but has two unfinished users instead of one. These spending heuristics can delay buying species; no purchase restrictions were introduced.

| Spot check | Before all ten | After all ten | After range | Unfinished after |
|---|---:|---:|---:|---:|
| 25/day, light | >90 | >90 | — | 25/25 |
| 200/day, inconsistent | 114 | 113 | 111–115 | 0/25 |
| 1000/day, stress | >30 | >30 | — | 25/25 |
| 200/day, established | — | >30 | — | 25/25 |
| 400/day, established | — | >30 | — | 25/25 |

Established users start from the production 100,000-review/365-day historical reward fixture, including Golden Trowel and historical rewards. Their 30-day median Full Bloom counts are 2 at 200 answers/day and 4 at 400/day.

## Changes delivered

- All current species at Full Bloom unlock garden-wide supplies regardless of displayed plants. Charges send their exact 100/500/2,000 Growth to the selected eligible Mastery project and then Stored Growth, without modifiers or Shared Growth.
- Fertilizer and Booster queues survive the final bloom, save/reload, and delayed reviews. Existing batch identities, timestamps, cards, and order remain intact. Each eligible answer consumes one contributing dose per family. New activations keep the five-dose limit; larger inherited queues drain without being discarded.
- Wind Chime grants +1 Growth every 5 eligible answers. Watering Station grants +1 every 2 among the first 200 eligible answers each Anki day. Carried old-cadence credit settles once on the next qualifying equipped answer.
- Owning Hourglass and Full Moon grants +25 Potion cards each: 100/125/150 on activation. Existing doses keep their duration. Their periodic gifts still require equipping.
- Schema 30 preserves existing rewards, balances, claims, and onboarding. Runtime projections and simulation retain the catalog active-only distinction. Shop eligibility and receipts use engine targets and committed allocations.
- Plant thresholds, species prices, achievement requirements, and discovery strength are unchanged. Canonical snapshot comparison found only the approved equipment effects and their copy, plus an existing cosmetic wording change.

## Equipped items and scaling trophies

Every run retains earned discoveries, equipment selection, achievement rewards, and scaling trophies. At the final checkpoint:

| Cohort / policy | Decoration | Scenery | Active scaling trophies |
|---|---|---|---|
| 100/day Collection first (main) | prism_trellis: 50 | eclipse: 8, full_moon: 6, halloween: 23, rainbow_horizon: 13 | None |
| 100/day Growth spending (main) | prism_trellis: 50 | eclipse: 8, full_moon: 6, halloween: 23, rainbow_horizon: 13 | None |
| 100/day Coin focused (main) | harvest_bell: 50 | autumn: 50 | None |
| 200/day Collection first (main) | firefly_lantern: 50 | eclipse: 15, full_moon: 2, halloween: 32, rainbow_horizon: 1 | botanists_plaque: 50 |
| 200/day Growth spending (main) | firefly_lantern: 50 | eclipse: 15, full_moon: 2, halloween: 32, rainbow_horizon: 1 | None |
| 200/day Coin focused (main) | harvest_bell: 50 | autumn: 50 | botanists_plaque: 50 |
| 400/day Collection first (main) | firefly_lantern: 50 | eclipse: 44, halloween: 6 | botanists_plaque: 50 |
| 400/day Growth spending (main) | firefly_lantern: 50 | eclipse: 44, halloween: 6 | botanists_plaque: 48 |
| 400/day Coin focused (main) | harvest_bell: 50 | autumn: 50 | botanists_plaque: 50 |
| 25/day Collection first (light) | firefly_lantern: 17, prism_trellis: 8 | default: 16, full_moon: 1, halloween: 1, rainbow_horizon: 7 | None |
| 200/day Collection first (inconsistent) | firefly_lantern: 25 | eclipse: 10, halloween: 14, rainbow_horizon: 1 | botanists_plaque: 25 |
| 1000/day Growth spending (stress) | firefly_lantern: 25 | eclipse: 7, full_moon: 3, halloween: 14, rainbow_horizon: 1 | None |
| 200/day Collection first (established) | firefly_lantern: 25 | default: 1, full_moon: 8, halloween: 2, rainbow_horizon: 14 | golden_trowel: 25 |
| 400/day Collection first (established) | firefly_lantern: 25 | eclipse: 3, halloween: 5, rainbow_horizon: 17 | golden_trowel: 25 |

The comparison JSON includes both before and after equipment counts at day 30 and each horizon, plus every paired completion date. Coin focused keeps Harvest Bell and Autumn Hearth equipped; owned Potion extensions still apply. Botanist’s Plaque is active only after earning ten Full Blooms, and the established-user checks retain Golden Trowel.

## Runtime and scope

The original audit took 106.2 seconds for 525 runs and 88,500 scenario-days. The updated run took 112.6 seconds for 575 runs and 90,000 scenario-days. Production onboarding is projected once per opening profile, while daily runs remain in the fast kernel. Policies, cohort identities, and seed indices remain paired. Opening rewards and the immediate achievement timing correction are included in the combined before/after result.

No all-ten completion fell between days 25–35, so the conditional 200-seed reruns were unnecessary. The earliest observed all-ten finish was day 54. This bounded audit supports the pacing guardrail; it does not prove that every possible real-world play style will avoid first-month completion.

## Validation

- Essential regression suite: 548 passed, 2 long/release scenarios deselected (33.18 seconds). Coverage includes catalog-completion transitions, display-only/empty gardens, supplies, ownership combinations, cadence boundaries, scaling trophies, SQLite migration, save/reload, delayed sync, stale quotes, replay, rollback, and conservation.
- Production engine parity: 5 scenarios, 35 daily checkpoints, 8,400 eligible answers; all matched. Cases cover fresh policies, established onboarding, and completed-garden effects.
- Native checks and dialog regression review: see the linked native verification record. The reported oversized garden preview/receipt was corrected with compact profiles and top-aligned content. Broader checks also found and corrected an older conflicting shared height cap that clipped plant previews, and a completed-starter home fallback that displayed zero Growth. Thirty-six targeted dialog/UI checks and 64 home checks passed.
- Three broader Settings geometry assertions fail identically against the frozen pre-layout-fix source. They are recorded as pre-existing in `preexisting-dialog-tests.log`; Settings behavior was not changed. One existing home CSS breakpoint assertion also fails on the frozen source; the fallback correction changes no CSS. Full release, packaging, and cross-platform acceptance were not run.

## Evidence

- [Original audit](</Users/test/Documents/Anki Gardening.nosync/build/quick-balance-audit-20260905-214846/results/quick-audit.md>)
- [Updated quick audit](</Users/test/Documents/Anki Gardening.nosync/build/balance-fixes-20260905-224034/results/quick-audit.md>)
- [Paired comparison and equipment counts](</Users/test/Documents/Anki Gardening.nosync/build/balance-fixes-20260905-224034/comparison.json>)
- [Production parity](</Users/test/Documents/Anki Gardening.nosync/build/balance-fixes-20260905-224034/production-parity.json>)
- [Essential tests](</Users/test/Documents/Anki Gardening.nosync/build/balance-fixes-20260905-224034/essential-tests-final.log>)
- [Native verification](</Users/test/Documents/Anki Gardening.nosync/build/balance-fixes-20260905-224034/native-verification.md>)

Audit catalog SHA-256: `463d6d24158c8e31dd5629988c71911e56d97891aac67ac1cd4974637d93092b`. Numerical audit source SHA-256: `6dc4e161403cefc4268c294dc136a62ef3f718b4865c4d28e308c33756151fde`. The immutable audit source is retained in `source-final/`; later changes are limited to the three UI files described in the native verification record. Concurrent capture-tool edits in the working tree are outside the numerical audit.
