# Study rewards simplification

Activity now has one compact Study rewards panel. Its daily rows are **Study 1
card** and **Finish all cards due today**, with core rewards of 4 and 16 Coins.
Amounts come from the shared reward engine, including equipped Coin effects;
earned rows read the committed reward and remain earned after reopening,
reconciliation, or a later change to the workload or equipment.

The existing streak achievements retain total permanent base-card Growth bonuses
of 5%, 10%, 15%, and 20% at 7, 30, 100, and 365 consecutive study days. Activity
reads those unlock records to show the retained percentage and next higher
achievement. A restarted six-day streak with the 30-day achievement unlocked
shows +10% and +15% at 100 days. Repeating an unlocked milestone pays nothing.

The seven-day achievement has no Coin payout. Other achievement rewards remain.
Garden Rhythm, the global five-completion cycle, and independent recurring
weekly Coins have been removed. There are no conversions, compensation grants,
or parallel old and new schedules.

## Reward authority and item coordination

The existing answer eligibility, Anki day boundary, collection-wide completion
verification, learning-step handling, and empty/buried/suspended-card rules are
unchanged. A visible zero-due count never substitutes for the completion check.
Daily event identities, answer records, and achievement unlocks retain their
normal persistent duplicate protection.

The retained percentage adds to base card Growth once. Equipment, fertilizer,
and Potion additions remain independent, direct Growth does not receive the
percentage, and Shared Growth distributes the resulting award without another
multiplier. Exact hundredth-Growth handling is preserved.

The scenery implementation owns its values and counters. Its common Coin quote
and grant pipeline applies Autumn Hearth's finalized 15% once, with fractional
carry; the daily panel consumes that quote and reads committed base and Autumn
events afterward. Snow's 50 Growth uses completion-Growth delivery. Hourglass's
15-day counter, Full Moon's four-day counter, and Bell/Prism/Halloween completion
awards retain the same authoritative completion trigger. Multi-day copy uses
**Finish all cards due on 15 days: +1 Booster Potion**. Item balance details are
in [Scenery and decoration simplification](scenery-decoration-simplification.md).

## Core Coin comparison

The actual retired core was 4 Coins for the first card, 8 for completion,
30 every five completed days, and 10 every seven consecutive study days. The
first weekly payment also served as the old seven-day achievement payout and
must not be counted twice. Unchanged other achievements, items, Finds, and plant
Coins are excluded from this core comparison.

For uninterrupted complete days, retired Coins are
`12 × days + 30 × floor(days / 5) + 10 × floor(days / 7)`;
new Coins are `20 × days`.

| Consecutive complete days | Retired core Coins | New core Coins |
|---:|---:|---:|
| 1 | 12 | 20 |
| 7 | 124 | 140 |
| 30 | 580 | 600 |
| 100 | 1,940 | 2,000 |
| 365 | 7,090 | 7,300 |

| Regular study pattern | Retired average Coins per study day | New average |
|---|---:|---:|
| Finish every day | 19.43 | 20.00 |
| Finish on half the days | 12.43 | 12.00 |
| Study but never finish | 5.43 | 4.00 |

These long-run averages assume an uninterrupted study streak. The larger daily
payment arrives earlier than the removed five-day reward. Incomplete days lose
the independent weekly Coin payout while continuing to earn streak progress.
After a break, recurring core earnings depend only on that day's two actions.
The 4/16 starting values are retained; no additional core adjustment was made.

## Card-earned Growth comparison

The retired live card pipeline used Garden Rhythm, based on completions among
the prior seven study days: 0–1 completions gave 0%, then 2%, 4%, 6%, 8%, and 10%.
The old separate streak tier table was not an additional active card multiplier
and is not counted here. The new ladder replaces both obsolete definitions.

| Earned streak tier | Base-card Growth per answer | Compared with established 10% Rhythm |
|---|---:|---:|
| Before seven days: 0% | 10.0 | −9.09% |
| Seven days: 5% | 10.5 | −4.55% |
| 30 days: 10% | 11.0 | Same |
| 100 days: 15% | 11.5 | +4.55% |
| 365 days: 20% | 12.0 | +9.09% |

For a new user studying and finishing 100 cards each day, the cumulative
base-card totals include the old Rhythm ramp and each exact new milestone:

| Through day | Retired card Growth | New card Growth | Change |
|---:|---:|---:|---:|
| 7 | 7,300 | 7,050 | −3.42% |
| 30 | 32,600 | 31,250 | −4.14% |
| 100 | 109,600 | 108,300 | −1.19% |
| 365 | 401,100 | 413,100 | +2.99% |

For 20 or 400 answers per day these base-only totals scale by 0.2 or 4. Equipment,
supplies, direct Growth, and Shared Growth are excluded from this comparison.
Incomplete study days earn the same new streak progress; a never-completing
user previously had 0% Rhythm. A returning user with the 100-day achievement
keeps 11.5 base-card Growth per answer, even at a one-day current streak. Two
separate 15-day streaks retain only the seven-day tier. Old Rhythm depended on
completion history; a calendar break alone did not erase that history.

## Plant-stage Coin sensitivity

The actual catalog still has stage thresholds of 400, 2,000, 6,000, 15,000, and
35,000 Growth and stage pools of 5, 10, 20, 35, and 50 Coins. The quarter-stage
checkpoints distribute those pools; the total remains **120 Coins per plant**.

For one continuously nurtured plant, with no items, supplies, Finds, additional
beds, or replacement plant, crossing 35,000 Growth occurs on:

| Cards studied and finished daily | Retired first Full Bloom day | New day |
|---:|---:|---:|
| 20 | 160 | 158 |
| 100 | 33 | 34 |
| 400 | 9 | 9 |

At the seven-, 30-, 100-, and 365-day comparison checkpoints these three patterns
cross the same Coin checkpoint totals on that first plant. Growth changes timing,
not the plant's eventual Coin budget. This is a bounded sensitivity calculation,
not a forecast of an entire player's garden. The coordinated Autumn comparison
separately accounts for its change from a flat completion bonus plus 50% of
milestone Coins to 15% of all earned gameplay Coins.

## Validation

Existing focused checks cover first-answer eligibility, authoritative completion
and repeated claims, exact tier thresholds, separate and broken streaks, saved
achievement progress, fractional and Shared Growth, pure versus committed Coin
amounts, item interactions, and reward history. Existing capture fixtures are
reused by stable IDs: `progress-today-page`, `progress-today-details` (now the
retained-bonus state), and `progress-achievements-page`.

The existing reward/achievement/persistence/catalog/kernel run passed 301 tests.
The existing capture-contract checks also passed. The subsequently updated
achievement-history, presentation, and state fixtures passed 43 checks, followed
by 10 focused checks after the final readback and obsolete-summary cleanup.
These are overlapping runs, not an aggregate count of distinct tests.

The final scoped native run is
`build/appearance-effect-captures/20260907-220427/20260907-220542`.
All three requested surfaces passed their individual audits with no text
warnings. Activity was checked at 1440×1000 and 860×580. Achievements was checked
at 1040×720 with three columns and at 860×580 with two columns, all labels
fitting and the final row reachable. Both Activity links revealed the actual
target achievement without changing reward state. The disposable Anki profile
passed isolation checks and exited normally.

This was a three-surface run. Its full-suite manifest still reports the generic
four-state scroll-matrix gate as missing because the other release surfaces
were not requested. It is not a complete release audit or release approval.

The captured production archive SHA-256 is
`42eef2570d204ebc39b83afb0a7353cef6bbcab74985b86c1fb3f8087ca95db0`;
the capture derivative is
`6585c3133efb4859aa66b0cacb4848557bdaeb19a76c2d04cc9913b157b01e88`.
All 265 shared payload entries matched. The later removal of one trailing
blank line in `activity.py` does not alter the captured behavior.

Screenshots: [Study rewards with a retained bonus](../build/appearance-effect-captures/20260907-220427/20260907-220542/24-progress-today-details.png),
[three-column Achievements](../build/appearance-effect-captures/20260907-220427/20260907-220542/25-progress-achievements-page.png),
[minimum-size Achievements](../build/appearance-effect-captures/20260907-220427/20260907-220542/progress-narrow/achievements-top.png).
