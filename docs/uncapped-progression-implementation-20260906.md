**Uncapped Finds and clearer progression — implemented, release held**

The source changes are complete. The required pacing acceptance failed: protected 1,000-answer/day scenarios finish all ten plants within 30 days. Keep this candidate unreleased. No odds, reward amounts, plant thresholds, purchase restrictions, hidden caps, or additional progression rewards were changed to force the audit to pass. Source integration as an unreleased candidate is separate from release approval.

Standard Finds are unlimited, with `None` in catalog, runtime, presentation, and simulation interfaces. Every newly eligible answer continues the existing deterministic chance/75-answer guarantee sequence. Saved drought progress survives the upgrade. Actual daily totals survive persistence, fallback deserialization, delayed sync, and reload; recorded outcomes recover previously clamped counts where evidence exists. Historical outcomes and processed-answer identities remain intact. State schema 30 and ledger schema 3 are unchanged.

Firefly Lantern still grants +3 direct Growth every five equipped answers, now to the nurtured plant through normal overflow. Prism Trellis grants the approved fixed +100 direct Growth on valid Today’s Cards completion while equipped. Legacy Prism bank fields remain readable and inert; the approved unreleased-data decision adds no conversion or compensation. These direct rewards do not create Shared Growth.

The existing Today summary shows the reward and five-completion bonus progress, with automatic Rhythm details in a tooltip. Finds use “X Finds today” and retain “Next card guaranteed.” Shop supply tooltips/accessibility describe total primary Growth using the engine’s actual Potion duration. Existing prices and “Need X more Coins” labels refresh after commits. The inspector gets its next checkpoint and base Coin reward from a domain projection; Full Blooms show the overflow destination. Mastery remains in species details: select the species, receive overflow, optionally add Stored Growth, then explicitly pay the existing Coin cost to unlock its next appearance.

Native QA also found and fixed a receipt projection defect: SQLite Find outcomes were missing from committed answer results, and direct Find/completion Growth was omitted from Mastery allocations. Results now read the authoritative outcomes and all committed funding deltas. The existing integration test covers the combined Find, ordinary/Shared Growth, and Prism reward.

The frozen capped baseline and candidate used identical seed identities, production opening states, equipment logic, and policies. Each version ran 875 samples: 450 fresh 100/200/400-answer cases over 180 days, 75 fresh 1,000-answer cases over 45 days, 300 established cases over 45 days, and the preserved 50 light/inconsistent checks. Established openings retain the production 100,000-review/365-day fixture. Batched sampling, earned equipment and ownership buffs, scaling trophies, supplies, replacement, and welcome rewards remain active.

| Protected scenario | Day-30 finishers: capped → candidate | Completion median: capped → candidate |
|---|---:|---:|
| Fresh, 1,000/day, Collection first | 7/25 → 25/25 | 32 → 22 days |
| Fresh, 1,000/day, Coin focused | 0/25 → 22/25 | 41 → 30 days |
| Established, 1,000/day, Collection first | 25/25 → 25/25 | 21 → 20 days |
| Established, 1,000/day, Coin focused | 25/25 → 25/25 | 21 → 20 days |

Every other protected tested cell had zero day-30 finishers. At fresh 400/day, Collection first moved from the historical 55-day median to 54 days. Unfinished populations are retained, not discarded when computing completion medians.

Only the two fresh 1,000/day cells with finishes around days 25–35 received 200-seed paired expansions. Collection first changed from 68/200 to 200/200 day-30 finishers (median 31 → 22; earliest 28 → 22). Coin focused changed from 0/200 to 173/200 (median 41 → 30; earliest 38 → 28). Separate uncapping-only comparisons reproduce the failing 25-seed results. Uncapping worsens the existing Collection first failure, introduces the fresh Coin-focused failure, and advances the established failures by about one day.

The normal pair took 318.1 seconds: baseline 153.8, candidate 164.3. Targeted expansions took 325.8 seconds separately: baseline 181.4, candidate 144.4, reusing the original 25 seeds per cell. Attribution diagnostics took 68.3 seconds separately. A verification rerun reproduced all 875 original candidate samples exactly. The final receipt-only correction leaves the numerical catalog/kernel and other engine reward methods unchanged; its applicability check is preserved.

Evidence is under [build/uncapped-progression-20260906-003030](../build/uncapped-progression-20260906-003030):

- [Paired completion report](../build/uncapped-progression-20260906-003030/paired-audit.md), [200-seed report](../build/uncapped-progression-20260906-003030/paired-targeted.md), and full baseline/candidate per-seed JSON.
- [Metric medians and paired deltas](../build/uncapped-progression-20260906-003030/paired-metric-medians.csv), including Finds, Coins, Growth, every supply, and species purchase days; [equipment choices](../build/uncapped-progression-20260906-003030/paired-equipment-choices.csv).
- Immutable baseline/candidate source manifests, [audit applicability](../build/uncapped-progression-20260906-003030/audit-applicability.json), and [native evidence index](../build/uncapped-progression-20260906-003030/native/index.html).

Existing focused suites passed: 269 reward/persistence tests; 309 receipt/engine/ledger tests; 221 UI/domain tests with 6 skips; and 36 bounded kernel/annual/trace tests with the comprehensive release matrix deselected. These suites overlap. Durable SQLite parity passed five cases/13 checkpoints; focused kernel parity passed nine cases/27 checkpoints, with additional 1,000-answer, completed-garden, and established-opening traces. Two simulator adapter defects exposed by uncapping were corrected: newly unlocked beds plant at the end-of-day visit, and Potion extension accounting includes effects transferred to the completed garden. The affected 365-day checks pass.

The optional comprehensive 66 × 365-day per-answer release matrix was stopped after 20 minutes 53 seconds. It is not claimed passed and remains a separate broader release gate. The requested batched pacing audit and bounded parity checks completed. No new narrow test files were added; existing tests were updated, including removing an unrelated brittle welcome-copy assertion while retaining its reward/history invariants.

Focused native QA used Anki 26.8.1 in `/private/tmp/anki-release-qa.mbc7sang`, profile `Codex Uncapped QA 20260906`, with automatic/media sync off and no login. Process, window, filesystem, and sync gates passed after each launch. Seven Finds and drought 74 survived a controlled restart with Coins and Mastery unchanged. Later committed answers reached nine Finds. The corrected completed-garden receipt shows one Find and all 211 Growth credited to Mastery; SQLite independently records Prism’s exact 100 Growth. Mastery selection and Stored Growth spending required no Coin payment; clicking Bronze Unlock spent exactly 50 Coins. The 860 × 600 layouts, checkpoint tooltip, visible guarantee, affordability updates, long supply descriptions, and completed-garden supplies were checked. Fertilizer totals were 100/400/1,200 primary Growth; the 150-card Potion totaled 750, excluding Shared Growth.

Final local QA archive: `candidate-verified.ankiaddon`, SHA-256 `9323e1853379e983ec4b5dc341bc80db632def90ff42d71abb144d9a5572d148`. Its source and package manifests are preserved. This task made no normal-profile changes, dist replacement, commit, tag, or publication. Concurrent UI work and historical evidence were preserved. Passing these bounded checks does not establish safety for every player strategy, and the failed pacing guardrail remains the release blocker.
